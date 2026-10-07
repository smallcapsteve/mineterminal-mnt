"""MNT Mine Development & Operations API v1: read-only JSON for cross-site use (MTP company pages).

MNT_MINE_DEV_API_V1 (2026-09-29, reader review fix 7). Serves what the mine_dev reader (1.0.0, an early version:
80.9% of rows right on fresh data) publishes into `mine_dev_events`: one row per event a tagged release's headline
announces for the issuer's own mine, plant or project. Marker rows (a tagged release with no event) are skipped.
Only the fields the /mine-development page shows are served (event, mine, status); the stored event date stays out.
MNT_FIX8B_API (2026-10-06, Justin: publish now, labelled): capex (and its high end, currency, basis), % complete,
incident kind and operating figures are served as an early reading, inside bounds a mine can have.

  /api/v1/mine-development      events, newest first, filterable

List parameters
  ticker     exact symbol (TXG.TO) or bare (TXG); an exact symbol ignores namesakes on other exchanges
  type       an event type (construction_start, first_production, restart, incident, offtake, ...)
  group      build | status | incident | commercial
  status     achieved | underway | planned
  days       only events from the last N days
  page, limit    1-based page, limit 1..200 (default 50)
  universe   all (default) | mtp -> only companies on MTP's list (fails open)

Registered from portal.serve via mine_dev_api.register(app).
Self-tests: python3 -m portal.mine_dev_api --selftest   (in-memory; touches nothing live)
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
from typing import Any, Optional

DB_PATH = "/opt/mnt/app/portal/portal.db"
TICKERS_PATH = "/opt/mnt/app/tickers.json"
MTP_UNIVERSE_PATH = "/var/lib/mnt-portal/mtp-companies.json"
SITE_BASE = "https://miningnewsterminal.com"
API_VERSION = "1"
MAX_LIMIT = 200
DEFAULT_LIMIT = 50
EARLY_NOTE = ("Early version: read by rules from the release headline; about 4 in 5 rows were right on a fresh "
              "sample (2026-09-28).")

# the publisher's labels and groups, copied so this module imports nothing from the reader
TYPE_LABELS = {"construction_decision": "Construction decision", "construction_start": "Construction start",
               "construction_progress": "Construction progress", "infrastructure": "Infrastructure",
               "site_cleanup": "Site cleanup", "commissioning": "Commissioning", "first_production": "First production",
               "commercial_production": "Commercial production", "ramp_up": "Ramp-up", "expansion": "Expansion",
               "restart": "Restart", "suspension": "Suspension", "care_maintenance": "Care & maintenance",
               "closure": "Closure", "status_update": "Operations update", "incident": "Incident",
               "offtake": "Offtake", "shipment": "Shipment / sale", "contract": "Contract"}
GROUP = {}
for _t in ("construction_decision", "construction_start", "construction_progress", "infrastructure", "site_cleanup",
           "commissioning", "first_production", "commercial_production", "ramp_up", "expansion"):
    GROUP[_t] = "build"
for _t in ("restart", "suspension", "care_maintenance", "closure", "status_update"):
    GROUP[_t] = "status"
GROUP["incident"] = "incident"
for _t in ("offtake", "shipment", "contract"):
    GROUP[_t] = "commercial"
GROUP_LABELS = {"build": "Build milestones", "status": "Operating status", "incident": "Incidents",
                "commercial": "Offtake, sales & contracts"}
STATUS_LABELS = {"achieved": "Achieved", "underway": "Underway", "planned": "Planned"}

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")
_COLS = ("md_id, event_id, ordinal, ticker, slug, event_type, event_group, mine, status, date, tag_confirmed, "
         "raw_headline, published_at, capex, capex_high, capex_currency, capex_basis, pct_complete, figures_json, "
         "incident_kind")


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
        if not isinstance(r, dict) or not r.get("ticker"):
            continue
        nm = (r.get("name") or "").strip()
        idx[r["ticker"]] = nm
        for prev in (r.get("previous_tickers") or []):
            pt = (prev or {}).get("ticker") if isinstance(prev, dict) else None
            if pt:
                idx.setdefault(pt, nm)
    return idx


def _parse_universe(data) -> frozenset:
    if not isinstance(data, dict):
        return frozenset()
    return frozenset(bare(t) for t in (data.get("tickers") or []) if bare(t))


_names = _FileCache(TICKERS_PATH, _parse_names)
_universe = _FileCache(MTP_UNIVERSE_PATH, _parse_universe)


def company_name(ticker: Optional[str], names: dict) -> str:
    nm = names.get(ticker or "", "")
    if nm and ticker and nm.upper() in (bare(ticker), ticker.upper()):
        return ""
    return nm


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
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Cache-Control": "public, max-age=%d" % max_age,
        "X-MNT-API-Version": API_VERSION,
    }


class BadRequest(ValueError):
    pass


def parse_params(ticker=None, type=None, group=None, status=None, days=None, page=None, limit=None, universe=None,
                 today=None) -> dict:
    p: dict[str, Any] = {}
    t = (ticker or "").strip()
    if t:
        if not _TICKER_RE.match(t):
            raise BadRequest("ticker: letters, digits, '.' or '-' only")
        p["ticker"] = t.upper()
    ty = (type or "").strip().lower().replace("-", "_")
    if ty:
        if ty not in TYPE_LABELS:
            raise BadRequest("type: " + ", ".join(TYPE_LABELS))
        p["type"] = ty
    g = (group or "").strip().lower()
    if g:
        if g not in GROUP_LABELS:
            raise BadRequest("group: " + ", ".join(GROUP_LABELS))
        p["group"] = g
    st = (status or "").strip().lower()
    if st:
        if st not in STATUS_LABELS:
            raise BadRequest("status: achieved, underway or planned")
        p["status"] = st
    if days not in (None, "", 0, "0"):
        try:
            d = int(days)
        except (TypeError, ValueError):
            raise BadRequest("days: a whole number")
        if d < 0 or d > 36500:
            raise BadRequest("days: 0..36500")
        if d:
            base = today or _dt.datetime.utcnow().date()
            p["since"] = (base - _dt.timedelta(days=d)).isoformat()
    try:
        p["page"] = max(1, int(page or 1))
        lim = int(limit or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        raise BadRequest("page and limit: whole numbers")
    p["limit"] = max(1, min(lim, MAX_LIMIT))
    u = (universe or "all").strip().lower()
    if u not in ("all", "mtp"):
        raise BadRequest("universe: all or mtp")
    p["universe"] = u
    return p


def _s(v) -> str:
    return "" if v is None else str(v).strip()


# MNT_FIX8B_API (2026-10-06): stored JSON detail is served only in a known shape, with figures no deposit,
# survey or mine can have dropped, so a bad reading never reaches a page as a number.
def _fin(v, lo=None, hi=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or (lo is not None and f < lo) or (hi is not None and f > hi):
        return None
    return f


def _small_json(raw, max_items=12):
    """A JSON object or list of objects -> the same, keeping short text and finite numbers only."""
    try:
        v = json.loads(raw) if isinstance(raw, str) and raw.strip() else None
    except ValueError:
        return None
    def one(d):
        if not isinstance(d, dict):
            return None
        o = {}
        for k, x in list(d.items())[:16]:
            if not isinstance(k, str) or len(k) > 40:
                continue
            if isinstance(x, bool) or x is None:
                continue
            if isinstance(x, (int, float)):
                f = _fin(x)
                if f is not None:
                    o[k] = f
            elif isinstance(x, str) and len(x.strip()) <= 60:
                o[k] = x.strip()
        return o or None
    if isinstance(v, list):
        out = [y for y in (one(d) for d in v[:max_items]) if y]
        return out or None
    return one(v)


def _early(r) -> dict:
    """MNT_FIX8B_API: capex, % complete, incident kind and operating figures (an early reading; labelled on the page)."""
    k = r.keys() if hasattr(r, "keys") else ()
    g = lambda c: r[c] if c in k else None
    lo = _fin(g("capex"), 1e5, 3e10)
    hi = _fin(g("capex_high"), 1e5, 3e10)
    if lo is None or (hi is not None and hi < lo):
        hi = None
    figs = _small_json(g("figures_json"), 8)
    if isinstance(figs, dict):
        figs = [figs]
    return {"capex": lo, "capex_high": hi, "capex_currency": _s(g("capex_currency")) if lo is not None else "",
            "capex_basis": _s(g("capex_basis")) if lo is not None else "", "pct_complete": _fin(g("pct_complete"), 0.1, 100),
            "incident_kind": _s(g("incident_kind")), "figures": figs or []}


def build_items(rows, names: dict) -> list[dict]:
    out = []
    for r in rows:
        et = _s(r["event_type"])
        if not et:
            continue                                  # marker row: a tagged release with no headline event
        if str(r["tag_confirmed"]) != "1":
            continue                                  # the page shows tagged releases only
        t = _s(r["ticker"])
        grp = _s(r["event_group"]) or GROUP.get(et, "")
        st = _s(r["status"])
        out.append({
            "event_row_id": r["md_id"], "event_id": _s(r["event_id"]), "ticker": t, "bare_ticker": bare(t),
            "company": company_name(t, names),
            "event_type": et, "event_type_label": TYPE_LABELS.get(et, et.replace("_", " ").capitalize()),
            "event_group": grp, "event_group_label": GROUP_LABELS.get(grp, grp),
            "mine": _s(r["mine"]), "status": st, "status_label": STATUS_LABELS.get(st, st),
            "date": _s(r["published_at"])[:10], "published_at": _s(r["published_at"]),
            "headline": _title(_s(r["raw_headline"])),
            "release_url": release_url(t, r["slug"], r["event_id"]),
            **_early(r),
        })
    out.sort(key=lambda x: (x["published_at"], x["event_row_id"]), reverse=True)
    return out


def query_events(conn, p: dict, names: dict, universe: Optional[frozenset]) -> dict:
    sql = "SELECT " + _COLS + " FROM mine_dev_events WHERE event_type IS NOT NULL AND tag_confirmed = 1"
    args: list = []
    t = p.get("ticker")
    if t:
        b = bare(t)
        sql += " AND (UPPER(ticker) = ? OR UPPER(ticker) = ? OR UPPER(ticker) LIKE ?)"
        args += [t, b, b + ".%"]
    if p.get("type"):
        sql += " AND event_type = ?"
        args.append(p["type"])
    if p.get("status"):
        sql += " AND status = ?"
        args.append(p["status"])
    if p.get("since"):
        sql += " AND substr(published_at, 1, 10) >= ?"
        args.append(p["since"])
    rows = conn.execute(sql + " ORDER BY published_at, event_id, ordinal", args).fetchall()
    if t and "." in t and any(_s(r["ticker"]).upper() == t for r in rows):
        rows = [r for r in rows if _s(r["ticker"]).upper() == t]
    items = build_items(rows, names)
    if p.get("group"):
        items = [x for x in items if x["event_group"] == p["group"]]
    if universe and not t:
        items = [x for x in items if x["bare_ticker"] in universe]
    total, limit, page = len(items), p["limit"], p["page"]
    return {
        "ok": True, "api_version": API_VERSION, "early_version": True, "note": EARLY_NOTE,
        "total": total, "page": page, "pages": max(1, math.ceil(total / limit)) if total else 0, "limit": limit,
        "filters": {k: p[k] for k in ("ticker", "type", "group", "status", "since") if p.get(k)},
        "universe": p["universe"], "universe_applied": bool(universe) and not t,
        "items": items[(page - 1) * limit: page * limit],
    }


def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    @app.get("/api/v1/mine-development")
    def mine_dev_list(ticker: Optional[str] = None, type: Optional[str] = None, group: Optional[str] = None,
                      status: Optional[str] = None, days: Optional[str] = None, page: Optional[str] = None,
                      limit: Optional[str] = None, universe: Optional[str] = None):
        try:
            p = parse_params(ticker, type, group, status, days, page, limit, universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = _universe.get() or None if p["universe"] == "mtp" else None
        with closing(_conn()) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='mine_dev_events'").fetchone():
                return JSONResponse({"ok": True, "api_version": API_VERSION, "total": 0, "page": 1, "pages": 0,
                                     "limit": p["limit"], "items": []}, headers=_headers())
            out = query_events(conn, p, _names.get(), uni)
        return JSONResponse(out, headers=_headers())


def _selftest() -> int:
    fails = []

    def ok(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE mine_dev_events (md_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL DEFAULT 0, ticker TEXT, slug TEXT, event_type TEXT, event_group TEXT, mine TEXT,
        status TEXT, event_date TEXT, capex REAL, capex_high REAL, capex_currency TEXT, capex_basis TEXT,
        pct_complete REAL, figures_json TEXT, incident_kind TEXT, counterparty TEXT, evidence TEXT, date TEXT,
        n_rows INTEGER NOT NULL DEFAULT 1, tag_confirmed INTEGER NOT NULL DEFAULT 1, raw_headline TEXT,
        published_at TEXT, extractor_version TEXT);
    """)

    def row(eid, t, date, et="first_production", st="achieved", mine="Alpha Mine", tagged=1, ordinal=0, grp=None):
        conn.execute("INSERT INTO mine_dev_events (event_id, ordinal, ticker, slug, event_type, event_group, mine, "
                     "status, date, tag_confirmed, raw_headline, published_at, capex) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, ordinal, t, "s-" + eid, et, grp if grp is not None else (GROUP.get(et) if et else None),
                      mine if et else None, st if et else None, date, tagged, "HEADLINE " + eid, date + "T12:00:00",
                      123.0))

    row("a1", "ABC.V", "2026-03-01", et="construction_start", st="underway")
    row("a2", "ABC.V", "2026-06-01", et="first_production")
    row("a2", "ABC.V", "2026-06-01", et="offtake", st="achieved", mine="", ordinal=1)
    row("m1", "ABC.V", "2026-07-01", et=None)                                  # marker
    row("u1", "ABC.V", "2026-08-01", et="restart", st="planned", tagged=0)     # untagged
    row("x1", "ABC.CN", "2026-02-01", et="incident")
    row("t1", "TXG.TO", "2026-09-10", et="commercial_production", mine="Media Luna")
    names = {"ABC.V": "ABC Gold Corp.", "TXG.TO": "Torex Gold Resources Inc."}
    P = lambda **kw: parse_params(today=_dt.date(2026, 9, 29), **kw)

    r = query_events(conn, P(), names, None)
    ok("tagged events only, markers skipped, newest first",
       [x["event_id"] for x in r["items"]] == ["t1", "a2", "a2", "a1", "x1"] and r["total"] == 5)
    ok("labels and groups", r["items"][0]["event_type_label"] == "Commercial production"
       and r["items"][0]["event_group"] == "build" and r["items"][0]["status_label"] == "Achieved"
       and r["items"][0]["company"] == "Torex Gold Resources Inc.")
    ok("event date still not served; FIX8B early fields present", "event_date" not in r["items"][0]
       and r["items"][0]["capex"] is None and r["items"][0]["figures"] == [] and r["items"][0]["pct_complete"] is None)
    ok("FIX8B early fields bounded", _early({"capex": 1.2e9, "capex_high": 1.0e9, "capex_currency": "USD",
       "capex_basis": "budget", "pct_complete": 140, "figures_json": '{"metric":"throughput","value":5000,"unit":"tpd"}',
       "incident_kind": "fatality"}) == {"capex": 1.2e9, "capex_high": None, "capex_currency": "USD", "capex_basis": "budget",
       "pct_complete": None, "incident_kind": "fatality", "figures": [{"metric": "throughput", "value": 5000.0, "unit": "tpd"}]}
       and _early({"capex": 5e12})["capex"] is None)
    ok("early-version note", r["early_version"] is True and "Early version" in r["note"])
    ok("exact listing wins over a namesake", query_events(conn, P(ticker="ABC.V"), names, None)["total"] == 3)
    ok("bare ticker matches both", query_events(conn, P(ticker="ABC"), names, None)["total"] == 4)
    ok("type / group / status", query_events(conn, P(type="offtake"), names, None)["total"] == 1
       and query_events(conn, P(group="build"), names, None)["total"] == 3
       and query_events(conn, P(status="underway"), names, None)["total"] == 1)
    ok("days", query_events(conn, P(days="30"), names, None)["total"] == 1)
    ok("universe", query_events(conn, P(universe="mtp"), names, frozenset({"TXG"}))["total"] == 1)
    ok("paging", query_events(conn, P(limit="2", page="3"), names, None)["items"][0]["event_id"] == "x1")
    ok("release url", r["items"][0]["release_url"] == SITE_BASE + "/news/txg.to/s-t1")

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad params", bad(type="x") and bad(group="x") and bad(status="x") and bad(ticker="A'--")
       and bad(universe="x") and bad(days="x"))
    print("mine_dev_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        if "/opt/mnt/app" not in sys.path and os.path.isdir("/opt/mnt/app"):
            sys.path.insert(0, "/opt/mnt/app")
        sys.exit(_selftest())
    print(__doc__)
