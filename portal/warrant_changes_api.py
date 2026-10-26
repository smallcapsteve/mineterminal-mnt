"""MNT Warrant Changes API v1: read-only JSON for cross-site use (Mine Terminal Pro's warrant-expiry events).

MNT_WCH_API_V1 (2026-10-07). Serves what WCH_PUBLISH_V1 writes into `warrant_changes`: one item per change to one
group of already-issued warrants a release reports (extension, acceleration, acceleration_waived, repricing,
incentive, exercise, expired, withdrawn; proposed or effective), with the financing it was matched to.

  /api/v1/warrant-changes      changes, newest first, filterable

List parameters
  gate       published (default: rows that passed the financing gate and may change an MTP event)
             | review (rows that would change an event but were held back, with hold_reason) | all
  ticker     exact symbol (ABC.V) or bare (ABC); an exact symbol ignores namesakes on other exchanges
  change     one of CHANGES          status   proposed | effective
  financing  a financing_id (as /api/v1/financings gives it)
  days       only changes published in the last N days
  page, limit    1-based page, limit 1..500 (default 100)

Registered from portal.serve via warrant_changes_api.register(app).
Self-tests: python3 -m portal.warrant_changes_api --selftest   (in-memory; touches nothing live)
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import re
import sqlite3
import sys
import threading
import time
from contextlib import closing
from typing import Optional

DB_PATH = "/opt/mnt/app/portal/portal.db"
# MNT_WCH_AI_LIVE_V1 (2026-10-26): the AI-reader hybrid for Warrants, served while fresh (wch_live.py writes it)
LIVE_PATH = os.environ.get("MNT_WCH_LIVE_DB", "/var/lib/mnt-aireader-pub/wch_live.db")
LIVE_MAX_AGE = 12 * 3600
TICKERS_PATH = "/opt/mnt/app/tickers.json"
SITE_BASE = "https://miningnewsterminal.com"
API_VERSION = "1"
MAX_LIMIT = 500
DEFAULT_LIMIT = 100
CHANGES = ("extension", "acceleration", "acceleration_waived", "repricing", "incentive", "exercise", "expired",
           "withdrawn")
STATUSES = ("proposed", "effective")
GATES = ("published", "review", "all")
CHANGE_LABELS = {"extension": "Expiry extended", "acceleration": "Expiry accelerated",
                 "acceleration_waived": "Acceleration waived", "repricing": "Repriced",
                 "incentive": "Early-exercise incentive", "exercise": "Exercised", "expired": "Expired",
                 "withdrawn": "Change withdrawn"}
_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")
_COLS = ("wc_id, event_id, ordinal, ticker, slug, change, status, n_warrants, strike_old, strike_new, issued, "
         "expiry_old, expiry_new, program_end, n_exercised, proceeds, n_remaining, new_series_n, new_series_strike, "
         "new_series_term_months, new_series_expiry, affects, financing_id, close_date, term_months, expiry_before, "
         "matched_by, publish, hold_reason, tag_confirmed, raw_headline, published_at")


def bare(ticker: Optional[str]) -> str:
    return (ticker or "").strip().upper().split(".")[0]


def release_url(ticker: Optional[str], slug: Optional[str], event_id: Optional[str]) -> str:
    t, sl = (ticker or "").strip(), (slug or "").strip()
    if t and sl:
        return f"{SITE_BASE}/news/{t.lower()}/{sl}"
    return f"{SITE_BASE}/event/{event_id}" if event_id else ""


class _FileCache:
    def __init__(self, path: str, parse, ttl: float = 60.0):
        self.path, self.parse, self.ttl = path, parse, ttl
        self._lock = threading.Lock()
        self._checked = 0.0
        self._mtime = None
        self._value = None

    def get(self):
        now = time.monotonic()
        with self._lock:
            if self._value is not None and now - self._checked < self.ttl:
                return self._value
            self._checked = now
            try:
                mt = os.stat(self.path).st_mtime
                if mt != self._mtime or self._value is None:
                    with open(self.path) as fh:
                        self._value = self.parse(json.load(fh))
                    self._mtime = mt
            except Exception:
                if self._value is None:
                    self._value = self.parse(None)
            return self._value


def _parse_names(data) -> dict:
    idx: dict[str, str] = {}
    for r in data or []:
        if isinstance(r, dict) and r.get("ticker"):
            idx[r["ticker"]] = (r.get("name") or "").strip()
    return idx


_names = _FileCache(TICKERS_PATH, _parse_names)


def _title(s: Optional[str]) -> str:
    if not s:
        return ""
    try:
        from portal.text_helpers import smart_title
        return smart_title(s)
    except Exception:
        return s


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout = 30000")
    c.execute("PRAGMA query_only = 1")
    return c


def _live_conn():
    """MNT_WCH_AI_LIVE_V1: the hybrid file, read-only, when it exists and is under 12 hours old; else None."""
    try:
        if time.time() - os.stat(LIVE_PATH).st_mtime > LIVE_MAX_AGE:
            return None
        c = sqlite3.connect("file:%s?mode=ro" % LIVE_PATH, uri=True, timeout=5)
        c.row_factory = sqlite3.Row
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='warrant_changes'").fetchone():
            c.close()
            return None
        return c
    except Exception:
        return None


def _headers(max_age: int = 300) -> dict:
    return {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type", "Cache-Control": "public, max-age=%d" % max_age,
            "X-MNT-API-Version": API_VERSION}


class BadRequest(ValueError):
    pass


def parse_params(gate=None, ticker=None, change=None, status=None, financing=None, days=None, page=None, limit=None,
                 today=None) -> dict:
    p: dict = {}
    g = (gate or "published").strip().lower()
    if g not in GATES:
        raise BadRequest("gate: published, review or all")
    p["gate"] = g
    t = (ticker or "").strip()
    if t:
        if not _TICKER_RE.match(t):
            raise BadRequest("ticker: letters, digits, '.' or '-' only")
        p["ticker"] = t.upper()
    ch = (change or "").strip().lower().replace("-", "_")
    if ch:
        if ch not in CHANGES:
            raise BadRequest("change: " + ", ".join(CHANGES))
        p["change"] = ch
    s = (status or "").strip().lower()
    if s:
        if s not in STATUSES:
            raise BadRequest("status: proposed or effective")
        p["status"] = s
    f = (financing or "").strip()
    if f:
        if not re.match(r"^[A-Za-z0-9_\-]{1,40}$", f):
            raise BadRequest("financing: an id")
        p["financing"] = f
    if days not in (None, "", 0, "0"):
        try:
            d = int(days)
        except (TypeError, ValueError):
            raise BadRequest("days: a whole number")
        if d < 0 or d > 36500:
            raise BadRequest("days: 0..36500")
        base = today or _dt.datetime.utcnow().date()
        p["since"] = (base - _dt.timedelta(days=d)).isoformat()
    try:
        p["page"] = max(1, int(page or 1))
        lim = int(limit or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        raise BadRequest("page and limit: whole numbers")
    p["limit"] = max(1, min(lim, MAX_LIMIT))
    return p


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _list(v):
    return [x for x in _s(v).split("|") if x]


def item(r, names: dict) -> dict:
    t = _s(r["ticker"])
    ch = _s(r["change"])
    nm = names.get(t, "")
    return {
        "id": r["wc_id"], "event_id": r["event_id"], "ordinal": r["ordinal"], "ticker": t, "bare_ticker": bare(t),
        "company": "" if nm.upper() in (bare(t), t.upper()) else nm,
        "change": ch, "change_label": CHANGE_LABELS.get(ch, ch), "status": _s(r["status"]),
        "n_warrants": _num(r["n_warrants"]), "strike_old": _num(r["strike_old"]), "strike_new": _num(r["strike_new"]),
        "issued": _list(r["issued"]), "expiry_old": _s(r["expiry_old"]), "expiry_new": _list(r["expiry_new"]),
        "program_end": _s(r["program_end"]), "n_exercised": _num(r["n_exercised"]), "proceeds": _num(r["proceeds"]),
        "n_remaining": _num(r["n_remaining"]),
        "new_series": ({"n": _num(r["new_series_n"]), "strike": _num(r["new_series_strike"]),
                        "term_months": _num(r["new_series_term_months"]), "expiry": _s(r["new_series_expiry"])}
                       if r["new_series_n"] is not None or r["new_series_strike"] is not None else None),
        "changes_event": str(r["affects"]) == "1", "published": str(r["publish"]) == "1",
        "financing_id": _s(r["financing_id"]), "close_date": _s(r["close_date"]),
        "term_months": r["term_months"], "expiry_before": _s(r["expiry_before"]), "matched_by": _s(r["matched_by"]),
        "hold_reason": _s(r["hold_reason"]), "tagged": str(r["tag_confirmed"]) == "1",
        "date": _s(r["published_at"])[:10], "published_at": _s(r["published_at"]),
        "headline": _title(_s(r["raw_headline"])), "release_url": release_url(t, r["slug"], r["event_id"]),
        "ai_label": r["ai_label"] if "ai_label" in r.keys() else None,  # MNT_WCH_AI_LIVE_V1
    }


def query(conn, p: dict, names: dict, extra: str = "") -> dict:
    sql = "SELECT " + _COLS + extra + " FROM warrant_changes WHERE 1=1"
    args: list = []
    if p["gate"] == "published":
        sql += " AND publish = 1"
    elif p["gate"] == "review":
        sql += " AND affects = 1 AND publish = 0"
    t = p.get("ticker")
    if t:
        b = bare(t)
        sql += " AND (UPPER(ticker) = ? OR UPPER(ticker) = ? OR UPPER(ticker) LIKE ?)"
        args += [t, b, b + ".%"]
    for k, col in (("change", "change"), ("status", "status"), ("financing", "financing_id")):
        if p.get(k):
            sql += " AND %s = ?" % col
            args.append(p[k])
    if p.get("since"):
        sql += " AND substr(published_at, 1, 10) >= ?"
        args.append(p["since"])
    rows = conn.execute(sql + " ORDER BY published_at DESC, event_id, ordinal", args).fetchall()
    if t and "." in t and any(_s(r["ticker"]).upper() == t for r in rows):
        rows = [r for r in rows if _s(r["ticker"]).upper() == t]
    total, limit, page = len(rows), p["limit"], p["page"]
    return {"ok": True, "api_version": API_VERSION, "total": total, "page": page,
            "pages": max(1, math.ceil(total / limit)) if total else 0, "limit": limit, "gate": p["gate"],
            "filters": {k: p[k] for k in ("ticker", "change", "status", "financing", "since") if p.get(k)},
            "items": [item(r, names) for r in rows[(page - 1) * limit: page * limit]]}


def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    @app.get("/api/v1/warrant-changes")
    def warrant_changes_list(gate: Optional[str] = None, ticker: Optional[str] = None, change: Optional[str] = None,
                             status: Optional[str] = None, financing: Optional[str] = None,
                             days: Optional[str] = None, page: Optional[str] = None, limit: Optional[str] = None):
        try:
            p = parse_params(gate, ticker, change, status, financing, days, page, limit)
        except BadRequest as e:
            return _err(str(e), 400)
        live = _live_conn()   # MNT_WCH_AI_LIVE_V1: the hybrid while it is fresh, portal.db otherwise
        if live is not None:
            try:
                with closing(live) as conn:
                    out = query(conn, p, _names.get(), ", ai_label")
                out["reader"] = "hybrid"
                return JSONResponse(out, headers=_headers())
            except Exception:
                pass   # fall through to the rules table
        with closing(_conn()) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='warrant_changes'").fetchone():
                return JSONResponse({"ok": True, "api_version": API_VERSION, "total": 0, "page": 1, "pages": 0,
                                     "limit": p["limit"], "gate": p["gate"], "items": [], "reader": "rules"},
                                    headers=_headers())
            out = query(conn, p, _names.get())
        out["reader"] = "rules"
        return JSONResponse(out, headers=_headers())


def _selftest() -> int:
    fails = []

    def ok(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    sys.path.insert(0, "/opt/mnt/app")
    from portal import warrant_changes_publish as WP
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(WP.TABLE_SQL)

    def row(eid, t, pub, change, status="effective", publish=0, affects=0, fid=None, expiry_new=None, hold=None,
            strike_new=None, ordinal=0):
        conn.execute("INSERT INTO warrant_changes (event_id, ordinal, ticker, slug, change, status, strike_old, "
                     "strike_new, issued, expiry_new, affects, financing_id, publish, hold_reason, tag_confirmed, "
                     "raw_headline, published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, ordinal, t, "s-" + eid, change, status, 0.25, strike_new, "2024-03-01|2024-03-08",
                      expiry_new, affects, fid, publish, hold, 0, "HEADLINE " + eid, pub + "T12:00:00"))
    row("a", "ABC.V", "2026-02-01", "extension", "proposed", 1, 1, "F1", "2027-03-01")
    row("b", "ABC.V", "2026-05-01", "extension", "effective", 1, 1, "F1", "2027-03-01")
    row("c", "ABC.CN", "2026-05-02", "repricing", publish=0, affects=1, hold="ambiguous: 2 financings fit", strike_new=0.1)
    row("d", "XYZ.TO", "2026-09-30", "incentive")
    names = {"ABC.V": "ABC Gold Corp."}
    P = lambda **kw: parse_params(today=_dt.date(2026, 10, 7), **kw)
    r = query(conn, P(), names)
    ok("published only, newest first", [i["event_id"] for i in r["items"]] == ["b", "a"] and r["total"] == 2)
    i = r["items"][1]
    ok("item shape", i["expiry_new"] == ["2027-03-01"] and i["issued"] == ["2024-03-01", "2024-03-08"]
       and i["financing_id"] == "F1" and i["published"] and i["changes_event"] and i["company"] == "ABC Gold Corp."
       and i["status"] == "proposed" and i["release_url"].endswith("/news/abc.v/s-a") and i["change_label"] == "Expiry extended")
    rv = query(conn, P(gate="review"), names)
    ok("review list", [x["event_id"] for x in rv["items"]] == ["c"] and rv["items"][0]["hold_reason"].startswith("ambiguous"))
    ok("all", query(conn, P(gate="all"), names)["total"] == 4)
    ok("exact listing wins over a namesake", query(conn, P(gate="all", ticker="ABC.V"), names)["total"] == 2)
    ok("bare ticker", query(conn, P(gate="all", ticker="ABC"), names)["total"] == 3)
    ok("filters", query(conn, P(financing="F1", status="effective"), names)["total"] == 1
       and query(conn, P(gate="all", change="incentive"), names)["total"] == 1
       and query(conn, P(gate="all", days="30"), names)["total"] == 1)

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad params", bad(gate="x") and bad(change="x") and bad(status="x") and bad(ticker="A'--")
       and bad(financing="1;drop") and bad(days="x"))
    print("warrant_changes_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
