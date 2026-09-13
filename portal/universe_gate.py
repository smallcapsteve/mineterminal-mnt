#!/usr/bin/env python3
"""_UNIVERSE_GATE (2026-09-13) — MinePortal decides who is on this site.

Installed by portal/__init__.py, so every importer of portal.db gets it: the
web app, the pipeline, and all six wire scrapers. One chokepoint rather than
six near-identical edits, and it covers ingest paths that do not exist yet.

Two behaviours, both wrapping functions in portal.db:

  upsert_event   An event whose ticker is not in the universe is stored with
                 review_status 'pending_review' instead of 'auto_approved',
                 and the ticker is proposed to MinePortal's candidate queue
                 once per process. The event is NOT discarded — MNT's public
                 pages read auto_approved only, so parking keeps it off the
                 site while leaving it in the review queue that E6 already
                 built.

  list_tickers   The company dropdown is intersected with the universe. This
                 is what makes MNT's visible company list the same list as
                 MTP's and SediTracker's.

Fail-open is deliberate. If the universe cannot be loaded at all — MinePortal
down and no cache — every ticker passes and a loud line goes to the log.
Failing closed would stop news collection across the entire site, which is a
much worse failure than briefly showing a company that has left the list.
"""
from __future__ import annotations

import logging
import sys
import time

if "/opt/mnt/app" not in sys.path:
    sys.path.insert(0, "/opt/mnt/app")

log = logging.getLogger("universe.gate")

# Short TTL: the universe client holds the real 6-hour cache, this only avoids
# rebuilding two sets on every row of a 1,000-row page.
_SET_TTL_S = 300.0
_sets: tuple = ()          # (monotonic_at, symbols, bare_tickers)
_proposed: set = set()     # tickers already sent to the queue this process
_warned_empty = False


def _universe_sets() -> tuple[set, set]:
    """(symbols, bare tickers). Both empty means 'we do not know' — the callers
    below then let everything through."""
    global _sets, _warned_empty
    now = time.monotonic()
    if _sets and (now - _sets[0]) < _SET_TTL_S:
        return _sets[1], _sets[2]

    symbols, bares = set(), set()
    try:
        import universe_client
        for c in universe_client.load():
            s = (c.get("symbol") or "").strip().upper()
            b = (c.get("ticker") or "").strip().upper()
            if s:
                symbols.add(s)
            if b:
                bares.add(b)
    except Exception as e:                       # noqa: BLE001
        log.error("universe gate: could not load the universe (%s) — "
                  "gate is OPEN, everything passes", e)
        symbols, bares = set(), set()

    if not symbols and not _warned_empty:
        log.error("universe gate: empty universe — gate is OPEN, everything passes")
        _warned_empty = True
    elif symbols:
        _warned_empty = False

    _sets = (now, symbols, bares)
    return symbols, bares


def in_universe(ticker: str | None) -> bool:
    symbols, bares = _universe_sets()
    if not symbols:
        return True                              # fail open
    t = (ticker or "").strip().upper()
    if not t:
        return True                              # untickered events are not ours to judge
    return t in symbols or t.split(".")[0] in bares


def _propose_once(ticker: str, row: dict) -> None:
    t = (ticker or "").strip().upper()
    if not t or t in _proposed:
        return
    _proposed.add(t)
    try:
        import universe_client
        # No name is sent. The only name available here is derived from the
        # press-release headline, and that is precisely the input that put
        # "ZincX Resources Corp" on Teck. The evidence URL is enough for a
        # person to identify the company properly.
        status = universe_client.propose(
            ticker=t,
            source=row.get("source_name"),
            discovered_by="mnt-ingest",
            evidence_url=row.get("source_url"),
        )
        log.info("universe gate: proposed %s (%s)", t, status)
    except Exception as e:                       # noqa: BLE001
        log.warning("universe gate: could not propose %s: %s", t, e)


def install() -> None:
    """Wrap portal.db. Idempotent — a second call is a no-op."""
    from portal import db

    if getattr(db, "_universe_gate_installed", False):
        return

    _inner_upsert = db.upsert_event
    _inner_list_tickers = db.list_tickers

    def upsert_event(row):
        ticker = row.get("ticker")
        if ticker and not in_universe(ticker):
            if (row.get("review_status") or "") == "auto_approved":
                row = dict(row)                  # never mutate the caller's dict
                row["review_status"] = "pending_review"
            _propose_once(ticker, row)
        return _inner_upsert(row)

    def list_tickers():
        rows = _inner_list_tickers()
        symbols, _ = _universe_sets()
        if not symbols:
            return rows                          # fail open
        return [(t, n) for (t, n) in rows if in_universe(t)]

    db.upsert_event = upsert_event
    db.list_tickers = list_tickers
    db._universe_gate_installed = True
    log.info("universe gate: installed")
