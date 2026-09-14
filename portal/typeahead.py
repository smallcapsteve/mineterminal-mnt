"""MNT_TYPEAHEAD_V1 (2026-09-14) — /api/search, the company type-ahead.

What it is for: MineTerminalPro's search box drops a list of matching companies
under it as you type (MTP_SEARCH_V1). MNT's and SediTracker's did not. This is
the MNT half of giving all three sites the same behaviour, and it answers with
MTP's own /api/search payload, item for item —

    {"results": [{"kind": ..., "label": ..., "sub": ..., "url": ...}, ...]}

— so the browser side is literally the same file on all three sites
(/static/typeahead.js, shared with SediTracker through the static symlink).

Why a module of its own rather than another block at the end of app.py, which
is this codebase's usual habit: app.py is 2,000 lines, and the only way a
change reaches the repo from here is by sending the whole file's text, which is
exactly how a 2,000-line file picks up a transcription error nobody notices. A
new module is sent in full, precisely as written. portal/serve.py — the process
entry point — wires it onto the app.

Scope, Justin's call on 2026-09-14: companies MNT actually holds news for, and
nothing else. The alternative was to offer the whole 1,043-company universe,
and a suggestion that lands the reader on an empty page is worse than no
suggestion.

Names come from app.py's own _ticker_to_name, so a company is named here
exactly as it is named in the feed — including the stub-name filter that drops
"Txg" for TXG.TO, and the previous-ticker mapping.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from fastapi.responses import JSONResponse

from portal import db

# The index is a scan of every approved event (list_tickers already walks the
# additional_tickers column), so it is rebuilt on a timer rather than per
# keystroke. Five minutes: a company that publishes its first release is
# searchable within one coffee, and a reader typing four characters costs one
# dict scan, not four table scans.
_TTL_S = 300

_lock = threading.Lock()
_state: dict[str, Any] = {"rows": [], "built_at": 0.0, "refreshing": False}


def _name_for(ticker: str) -> str:
    """app.py's resolver, imported at call time.

    Deferred because portal.app imports nothing from here and must not have to:
    the entry point imports portal.app first, and a module-level import in the
    other direction would make that ordering load-bearing.
    """
    try:
        from portal.app import _ticker_to_name
        return _ticker_to_name(ticker) or ""
    except Exception:
        return ""


def _build_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticker, n in db.list_tickers():
        t = (ticker or "").strip().upper()
        if not t:
            continue
        bare = t.split(".")[0]
        name = _name_for(t)
        rows.append({
            "ticker": t,
            "bare": bare,
            "name": name,
            "n": int(n or 0),
            "_bare_l": bare.lower(),
            "_full_l": t.lower(),
            "_name_l": name.lower(),
            "_words": [w for w in name.lower().replace("-", " ").replace("/", " ").split() if w],
        })
    return rows


def _refresh() -> list[dict[str, Any]]:
    """Rebuild and store. Returns whatever the index holds afterwards."""
    try:
        built = _build_rows()
    except Exception:
        # Fails OPEN on staleness, closed on nothing: an old index answers
        # yesterday's tickers, an empty one makes the box look broken.
        built = None
    with _lock:
        if built is not None:
            _state["rows"] = built
            _state["built_at"] = time.monotonic()
        _state["refreshing"] = False
        return _state["rows"]


def _rows() -> list[dict[str, Any]]:
    """Never makes a reader wait for a rebuild if there is anything to answer
    with. Fresh index: answer it. Stale index: answer it anyway and rebuild
    behind them — five-minute-old ticker names are not worth a visible pause in
    a box that is supposed to respond to a keystroke. Only the very first call
    of a worker's life builds in line, and register() has already started that
    in the background at import.
    """
    now = time.monotonic()
    with _lock:
        cached = _state["rows"]
        if cached and (now - _state["built_at"]) < _TTL_S:
            return cached
        if cached:
            if not _state["refreshing"]:
                _state["refreshing"] = True
                threading.Thread(target=_refresh, daemon=True).start()
            return cached
    return _refresh()


def _score(row: dict[str, Any], q: str) -> Optional[int]:
    """Lower is better; None means no match.

    The ordering is the one a reader expects from a ticker box: what they typed,
    then things starting with it, then things merely containing it. Company
    names are matched word by word as well as from the front, so "gold" finds
    "New Found Gold" and not only companies whose name begins with it.
    """
    if row["_bare_l"] == q or row["_full_l"] == q:
        return 0
    if row["_bare_l"].startswith(q) or row["_full_l"].startswith(q):
        return 1
    if row["_name_l"].startswith(q):
        return 2
    for w in row["_words"]:
        if w.startswith(q):
            return 3
    if q in row["_bare_l"]:
        return 4
    if q in row["_name_l"]:
        return 5
    return None


def search(q: str, limit: int = 14) -> list[dict[str, str]]:
    q = (q or "").strip().lower()
    if not q:
        return []
    hits = []
    for row in _rows():
        s = _score(row, q)
        if s is None:
            continue
        # Busiest company wins a tie: with two equally good matches, the one
        # with 60 releases is the one being looked for far more often than the
        # one with 1.
        hits.append((s, -row["n"], row["name"] or row["bare"], row))
    hits.sort(key=lambda h: (h[0], h[1], h[2]))

    out = []
    for _, _, _, row in hits[:limit]:
        out.append({
            "kind": "company",
            "label": row["name"] or row["bare"],
            # Rendered as the red chip on the right, same as MTP. The suffix is
            # worth showing: it is the only place on MNT the exchange appears.
            "sub": row["ticker"],
            "url": "/company/" + row["ticker"].lower(),
        })
    return out


def register(app) -> None:
    # Build the index at import, off the request path, so the first reader to
    # type does not pay for the first scan.
    threading.Thread(target=_rows, daemon=True).start()

    @app.get("/api/search")
    def api_search(q: str = "", limit: int = 14):
        """Type-ahead for the nav search box. Same payload shape as MTP's."""
        try:
            limit = max(1, min(int(limit or 14), 25))
        except (TypeError, ValueError):
            limit = 14
        results = search(q, limit)
        return JSONResponse(
            {
                "ok": True,
                "q": (q or "").strip(),
                "count": len(results),
                "indexed": len(_state["rows"]),
                "results": results,
            },
            headers={"Cache-Control": "public, max-age=60"},
        )
