"""MNT Calendar API v1: read-only JSON for cross-site use (Mine Terminal Pro's events page).

MNT_CAL_API_V1 (2026-10-12). Serves what CAL_PUBLISH_V1 writes into `calendar_events`: the dated corporate events a
company's own release reports (meetings, results dates, calls, dividends, NCIBs, presentations, and the corporate
actions: consolidations, name / symbol changes, arrangements, spin-outs, listings, take-over bids, rights offerings).

  /api/v1/calendar     events, filterable

List parameters
  scope      upcoming (default: current rows dated today or later, scheduled / proposed / postponed)
             | tba (current rows with no date yet and a future status, from releases of the last 365 days:
               "date to be announced", rule CN1) | recent (current rows of releases in the last N days, any status)
             | all (every row, superseded ones included, newest release first)
  ticker     exact symbol (ABC.V) or bare (ABC); an exact symbol ignores namesakes on other exchanges
  kind       one of KINDS, or "dated" / "corporate"
  confirmed  1 (kinds measured >= 90% right on fresh releases) | 0 (corporate actions, shown "unconfirmed")
  hidden     1 to include rows stored but not shown (OTC / Frankfurt symbols, rule CO1)
  days       recent: releases of the last N days (default 30)
  page, limit    1-based page, limit 1..500 (default 100)

Upcoming and tba are sorted by date (tba by release), the others newest release first.
Registered from portal.serve via calendar_api.register(app).
Self-tests: python3 -m portal.calendar_api --selftest   (in-memory; touches nothing live)
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
TICKERS_PATH = "/opt/mnt/app/tickers.json"
SITE_BASE = "https://miningnewsterminal.com"
API_VERSION = "1"
MAX_LIMIT = 500
DEFAULT_LIMIT = 100
DATED = ("meeting", "results_release", "conference_call", "dividend", "presentation", "ncib")
CORPORATE = ("consolidation", "name_change", "symbol_change", "arrangement", "spinout", "listing", "takeover_bid",
             "rights_offering")
KINDS = DATED + CORPORATE
SCOPES = ("upcoming", "tba", "recent", "all")
FUTURE = ("scheduled", "proposed", "postponed")
KIND_LABELS = {"meeting": "Shareholder meeting", "results_release": "Results release", "conference_call": "Results call",
               "dividend": "Dividend", "presentation": "Conference", "ncib": "Share buyback (NCIB)",
               "consolidation": "Share consolidation", "name_change": "Name change", "symbol_change": "Symbol change",
               "arrangement": "Arrangement / amalgamation", "spinout": "Spin-out", "listing": "Listing",
               "takeover_bid": "Take-over bid", "rights_offering": "Rights offering"}
_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")
_COLS = ("cal_id, event_id, ordinal, ticker, slug, kind, status, event_date, exact, end_date, record_date, time, "
         "detail, venue, role, show, confirmed, current, superseded_by, tag_confirmed, raw_headline, published_at")


from portal import usx_key as _usxk   # USX_FEEDKEY_V1


def bare(ticker: Optional[str]) -> str:
    return (ticker or "").strip().upper().split(".")[0]


def release_url(ticker: Optional[str], slug: Optional[str], event_id: Optional[str]) -> str:
    t, sl = (ticker or "").strip(), (slug or "").strip()
    if sl.startswith("https://") or sl.startswith("http://"):   # BULL_PUBLISH_V1: an exchange bulletin's own page
        return sl
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


def _headers(max_age: int = 300) -> dict:
    return {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type", "Cache-Control": "public, max-age=%d" % max_age,
            "X-MNT-API-Version": API_VERSION}


class BadRequest(ValueError):
    pass


def parse_params(scope=None, ticker=None, kind=None, confirmed=None, hidden=None, days=None, page=None, limit=None,
                 today=None) -> dict:
    p: dict = {}
    s = (scope or "upcoming").strip().lower()
    if s not in SCOPES:
        raise BadRequest("scope: " + ", ".join(SCOPES))
    p["scope"] = s
    p["today"] = (today or _dt.datetime.now(_dt.timezone.utc).date()).isoformat()
    t = (ticker or "").strip()
    if t:
        if not _TICKER_RE.match(t):
            raise BadRequest("ticker: letters, digits, '.' or '-' only")
        p["ticker"] = t.upper()
    k = (kind or "").strip().lower().replace("-", "_")
    if k:
        if k not in KINDS + ("dated", "corporate"):
            raise BadRequest("kind: " + ", ".join(KINDS) + ", dated or corporate")
        p["kinds"] = DATED if k == "dated" else CORPORATE if k == "corporate" else (k,)
    c = (confirmed or "").strip()
    if c:
        if c not in ("0", "1"):
            raise BadRequest("confirmed: 0 or 1")
        p["confirmed"] = int(c)
    p["hidden"] = (hidden or "").strip() == "1"
    try:
        d = int(days) if days not in (None, "") else 30
    except (TypeError, ValueError):
        raise BadRequest("days: a whole number")
    if d < 0 or d > 36500:
        raise BadRequest("days: 0..36500")
    p["days"] = d
    try:
        p["page"] = max(1, int(page or 1))
        lim = int(limit or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        raise BadRequest("page and limit: whole numbers")
    p["limit"] = max(1, min(lim, MAX_LIMIT))
    return p


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def item(r, names: dict) -> dict:
    t = _s(r["ticker"])
    k = _s(r["kind"])
    nm = names.get(t, "")
    return {
        "id": r["cal_id"], "event_id": r["event_id"], "ordinal": r["ordinal"], "ticker": t, "bare_ticker": bare(t),
        "company": "" if nm.upper() in (bare(t), t.upper()) else nm,
        "kind": k, "kind_label": KIND_LABELS.get(k, k), "status": _s(r["status"]),
        "date": _s(r["event_date"]), "exact": str(r["exact"]) == "1", "tba": not _s(r["event_date"]),
        "end_date": _s(r["end_date"]), "record_date": _s(r["record_date"]), "time": _s(r["time"]),
        "detail": _s(r["detail"]), "venue": _s(r["venue"]), "role": _s(r["role"]),
        "confirmed": str(r["confirmed"]) == "1", "shown": str(r["show"]) == "1", "current": str(r["current"]) == "1",
        "superseded_by": _s(r["superseded_by"]), "tagged": str(r["tag_confirmed"]) == "1",
        "published_at": _s(r["published_at"]), "headline": _title(_s(r["raw_headline"])),
        "release_url": release_url(t, r["slug"], r["event_id"]),
        "source": "exchange bulletin" if _s(r["event_id"]).startswith("bulletin:") else "company release",
    }


def query(conn, p: dict, names: dict) -> dict:
    sql = "SELECT " + _COLS + " FROM calendar_events WHERE 1=1"
    args: list = []
    today = p["today"]
    if p["scope"] != "all":
        sql += " AND current = 1"
    if not p["hidden"]:
        sql += " AND show = 1"
    if p["scope"] == "upcoming":
        sql += " AND event_date IS NOT NULL AND event_date >= ? AND status IN ('scheduled','proposed','postponed')"
        args.append(today)
        order = " ORDER BY event_date, ticker, kind"
    elif p["scope"] == "tba":
        since = (_dt.date.fromisoformat(today) - _dt.timedelta(days=365)).isoformat()
        sql += " AND event_date IS NULL AND status IN ('scheduled','proposed','postponed') AND substr(published_at,1,10) >= ?"
        args.append(since)
        order = " ORDER BY published_at DESC, event_id, ordinal"
    else:
        if p["scope"] == "recent":
            since = (_dt.date.fromisoformat(today) - _dt.timedelta(days=p["days"])).isoformat()
            sql += " AND substr(published_at,1,10) >= ?"
            args.append(since)
        order = " ORDER BY published_at DESC, event_id, ordinal"
    t = p.get("ticker")
    t, _usx = _usxk.norm(t)   # USX_FEEDKEY_V1: "-US" form; a symbol listed both in the US and elsewhere
    if t:
        b = bare(t)
        sql += " AND (UPPER(ticker) = ? OR UPPER(ticker) = ? OR UPPER(ticker) LIKE ?)"
        args += [t, b, b + ".%"]
        if _usx:
            sql += " AND " + _usx % "ticker"
    if p.get("kinds"):
        sql += " AND kind IN (%s)" % ",".join("?" * len(p["kinds"]))
        args += list(p["kinds"])
    if "confirmed" in p:
        sql += " AND confirmed = ?"
        args.append(p["confirmed"])
    rows = conn.execute(sql + order, args).fetchall()
    if t and "." in t and any(_s(r["ticker"]).upper() == t for r in rows):
        rows = [r for r in rows if _s(r["ticker"]).upper() == t]
    total, limit, page = len(rows), p["limit"], p["page"]
    return {"ok": True, "api_version": API_VERSION, "total": total, "page": page,
            "pages": max(1, math.ceil(total / limit)) if total else 0, "limit": limit, "scope": p["scope"],
            "filters": {k: p[k] for k in ("ticker", "kinds", "confirmed") if k in p},
            "items": [item(r, names) for r in rows[(page - 1) * limit: page * limit]]}


def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    @app.get("/api/v1/calendar")
    def calendar_list(scope: Optional[str] = None, ticker: Optional[str] = None, kind: Optional[str] = None,
                      confirmed: Optional[str] = None, hidden: Optional[str] = None, days: Optional[str] = None,
                      page: Optional[str] = None, limit: Optional[str] = None):
        try:
            p = parse_params(scope, ticker, kind, confirmed, hidden, days, page, limit)
        except BadRequest as e:
            return _err(str(e), 400)
        with closing(_conn()) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='calendar_events'").fetchone():
                return JSONResponse({"ok": True, "api_version": API_VERSION, "total": 0, "page": 1, "pages": 0,
                                     "limit": p["limit"], "scope": p["scope"], "items": []}, headers=_headers())
            out = query(conn, p, _names.get())
        return JSONResponse(out, headers=_headers())


def _selftest() -> int:
    fails = []

    def ok(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    sys.path.insert(0, "/opt/mnt/app")
    from portal import calendar_publish as CP
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(CP.TABLE_SQL)

    def row(eid, t, pub, kind, d, status="scheduled", current=1, show=1, confirmed=None):
        conn.execute("INSERT INTO calendar_events (event_id, ordinal, ticker, slug, kind, status, event_date, exact, "
                     "show, confirmed, current, raw_headline, published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, 0, t, "s-" + eid, kind, status, d, 1 if d else 0, show,
                      (1 if kind in DATED else 0) if confirmed is None else confirmed, current, "HEADLINE " + eid,
                      pub + "T12:00:00"))
    row("a", "ABC.V", "2026-09-01", "meeting", "2026-10-20")
    row("b", "ABC.V", "2026-09-02", "meeting", "2026-10-21", current=0)
    row("c", "ABC.CN", "2026-09-03", "consolidation", None, "proposed")
    row("d", "XYZ.TO", "2026-09-04", "dividend", "2026-10-15")
    row("e", "XYZ.TO", "2026-09-05", "symbol_change", "2026-10-16", show=0)
    row("f", "XYZ.TO", "2026-08-01", "conference_call", "2026-08-05", "completed")
    names = {"ABC.V": "ABC Gold Corp."}
    P = lambda **kw: parse_params(today=_dt.date(2026, 10, 12), **kw)
    r = query(conn, P(), names)
    ok("upcoming: current, shown, dated, by date", [i["event_id"] for i in r["items"]] == ["d", "a"])
    i = r["items"][1]
    ok("item shape", i["kind_label"] == "Shareholder meeting" and i["confirmed"] and i["company"] == "ABC Gold Corp."
       and i["release_url"].endswith("/news/abc.v/s-a") and not i["tba"])
    rt = query(conn, P(scope="tba"), names)
    ok("tba", [x["event_id"] for x in rt["items"]] == ["c"] and rt["items"][0]["tba"] and not rt["items"][0]["confirmed"])
    ok("hidden", [x["event_id"] for x in query(conn, P(hidden="1"), names)["items"]] == ["d", "e", "a"])
    ok("all includes superseded", query(conn, P(scope="all"), names)["total"] == 5)
    ok("recent: current, shown, last N days", query(conn, P(scope="recent", days="60"), names)["total"] == 3)
    ok("kind groups", query(conn, P(scope="all", kind="corporate", hidden="1"), names)["total"] == 2
       and query(conn, P(kind="dividend"), names)["total"] == 1)
    ok("ticker", query(conn, P(scope="all", ticker="ABC.V"), names)["total"] == 2
       and query(conn, P(scope="all", ticker="ABC"), names)["total"] == 3)
    ok("confirmed filter", query(conn, P(scope="tba", confirmed="0"), names)["total"] == 1)

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad params", bad(scope="x") and bad(kind="x") and bad(confirmed="2") and bad(ticker="A'--") and bad(days="x"))
    print("calendar_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
