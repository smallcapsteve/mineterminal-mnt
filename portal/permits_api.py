"""MNT Permits & Approvals API v1: read-only JSON for cross-site use (MTP company pages).

MNT_PERMITS_API_V1 (2026-09-23). Serves what PERMIT_V1 publishes into `permits`, one item per PERMIT: the release
saying a company applied, the one saying the permit is in review and the one saying it was granted are one permit
(the publisher's chain_key), shown from its lead row (latest=1, which the publisher has already filled from the
chain's other items), with every stage behind it. Marker rows (a tagged release with no permit) are skipped.

  /api/v1/permits      permits, newest first, filterable

List parameters
  ticker     exact symbol (TXG.TO) or bare (TXG); an exact symbol ignores namesakes on other exchanges
  scope      tagged (default: the lead release carries the Permits & Approvals tag, as /permits-approvals shows)
             | all (also permits read from untagged releases; less checked)
  type       drill_exploration | environmental_assessment | plan_of_operations | mining_licence |
             construction_operating | water | land_community | government_policy | other
  status     planned | applied | in_review | granted | renewed | contested   (of the lead row)
  days       only permits whose lead item is in the last N days
  page, limit    1-based page, limit 1..200 (default 50) - counted in permits
  universe   all (default) | mtp -> only companies on MTP's list (fails open)

Registered from portal.serve via permits_api.register(app).
Self-tests: python3 -m portal.permits_api --selftest   (in-memory; touches nothing live)
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
TYPES = ("drill_exploration", "environmental_assessment", "plan_of_operations", "mining_licence",
         "construction_operating", "water", "land_community", "government_policy", "other")
STATUSES = ("planned", "applied", "in_review", "granted", "renewed", "contested")
SCOPES = ("tagged", "all")
# the publisher's labels, copied so this module imports nothing from the reader
TYPE_LABELS = {"drill_exploration": "Drill / exploration", "environmental_assessment": "Environmental assessment",
               "plan_of_operations": "Plan of operations / notice", "mining_licence": "Mining licence / lease",
               "construction_operating": "Construction / operating", "water": "Water",
               "land_community": "Land access / community", "government_policy": "Government / policy",
               "other": "Other"}
STATUS_LABELS = {"planned": "Planned", "applied": "Applied", "in_review": "In review", "granted": "Granted",
                 "renewed": "Renewed / amended", "contested": "Contested"}

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")

_COLS = ("pm_id, event_id, ordinal, ticker, slug, permit_type, project, status, authority, date, permit_name, "
         "permit_id, term, expiry, scope, holder, jurisdiction, metal, chain_key, chain_items, first_reported, latest, "
         "tag_confirmed, raw_headline, published_at")


# --------------------------------------------------------------------------- helpers (pure)

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


# --------------------------------------------------------------------------- params

class BadRequest(ValueError):
    pass


def parse_params(ticker=None, scope=None, type=None, status=None, days=None, page=None, limit=None, universe=None,
                 today=None) -> dict:
    p: dict[str, Any] = {}
    t = (ticker or "").strip()
    if t:
        if not _TICKER_RE.match(t):
            raise BadRequest("ticker: letters, digits, '.' or '-' only")
        p["ticker"] = t.upper()
    sc = (scope or "tagged").strip().lower()
    if sc not in SCOPES:
        raise BadRequest("scope: tagged or all")
    p["scope"] = sc
    ty = (type or "").strip().lower()
    if ty:
        if ty not in TYPES:
            raise BadRequest("type: " + ", ".join(TYPES))
        p["type"] = ty
    stt = (status or "").strip().lower().replace("-", "_").replace(" ", "_")
    if stt:
        if stt not in STATUSES:
            raise BadRequest("status: " + ", ".join(STATUSES))
        p["status"] = stt
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


def build_permits(rows, names: dict) -> list[dict]:
    """rows in (published_at, event_id, ordinal) order -> permits, newest first."""
    groups: dict[str, list] = {}
    order: list[str] = []
    for r in rows:
        if not r["status"]:
            continue                            # marker row: a tagged release with no permit
        k = r["chain_key"] or ("row:%s" % r["pm_id"])
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(r)
    out = []
    for k in order:
        rs = groups[k]                          # chronological
        leads = [r for r in rs if str(r["latest"]) == "1"]
        last = leads[-1] if leads else rs[-1]
        t = _s(last["ticker"])
        stages, seen = [], set()
        for r in rs:
            if r["event_id"] in seen:
                continue
            seen.add(r["event_id"])
            stages.append({"date": _s(r["published_at"])[:10], "status": _s(r["status"]),
                           "status_label": STATUS_LABELS.get(_s(r["status"]), _s(r["status"])),
                           "tagged": str(r["tag_confirmed"]) == "1", "headline": _title(_s(r["raw_headline"])),
                           "release_url": release_url(r["ticker"], r["slug"], r["event_id"])})
        pt = _s(last["permit_type"])
        st = _s(last["status"])
        out.append({
            "permit_key": _s(last["chain_key"]) or ("row:%s" % last["pm_id"]), "row_id": last["pm_id"],
            "ticker": t, "bare_ticker": bare(t), "company": company_name(t, names),
            "type": pt, "type_label": TYPE_LABELS.get(pt, "Permit"),
            "status": st, "status_label": STATUS_LABELS.get(st, st),
            "project": _s(last["project"]), "authority": _s(last["authority"]), "stage_date": _s(last["date"]),
            "permit_name": _s(last["permit_name"]), "permit_id": _s(last["permit_id"]), "term": _s(last["term"]),
            "expiry": _s(last["expiry"]), "scope": _s(last["scope"]), "holder": _s(last["holder"]),
            "jurisdiction": _s(last["jurisdiction"]), "metal": _s(last["metal"]),
            "tagged": str(last["tag_confirmed"]) == "1",
            "date": _s(last["published_at"])[:10], "published_at": _s(last["published_at"]),
            "first_reported": _s(rs[0]["published_at"])[:10], "releases": len(stages),
            "headline": _title(_s(last["raw_headline"])),
            "release_url": release_url(t, last["slug"], last["event_id"]),
            "stages": stages[::-1],
        })
    out.sort(key=lambda x: (x["published_at"], x["row_id"]), reverse=True)
    return out


def query_permits(conn, p: dict, names: dict, universe: Optional[frozenset]) -> dict:
    sql = "SELECT " + _COLS + " FROM permits WHERE status IS NOT NULL"
    args: list = []
    t = p.get("ticker")
    if t:
        b = bare(t)
        sql += " AND (UPPER(ticker) = ? OR UPPER(ticker) = ? OR UPPER(ticker) LIKE ?)"
        args += [t, b, b + ".%"]
    rows = conn.execute(sql + " ORDER BY published_at, event_id, ordinal", args).fetchall()
    if t and "." in t and any(_s(r["ticker"]).upper() == t for r in rows):
        rows = [r for r in rows if _s(r["ticker"]).upper() == t]    # the listing asked for, not a namesake
    pms = build_permits(rows, names)
    if p["scope"] == "tagged":
        pms = [x for x in pms if x["tagged"]]      # same rule as /permits-approvals: the lead release is tagged
    if universe and not t:
        pms = [x for x in pms if x["bare_ticker"] in universe]
    if p.get("type"):
        pms = [x for x in pms if x["type"] == p["type"]]
    if p.get("status"):
        pms = [x for x in pms if x["status"] == p["status"]]
    if p.get("since"):
        pms = [x for x in pms if x["date"] >= p["since"]]
    total, limit, page = len(pms), p["limit"], p["page"]
    return {
        "ok": True, "api_version": API_VERSION, "total": total, "page": page,
        "pages": max(1, math.ceil(total / limit)) if total else 0, "limit": limit,
        "filters": {k: p[k] for k in ("ticker", "type", "status", "since") if p.get(k)},
        "scope": p["scope"], "universe": p["universe"], "universe_applied": bool(universe) and not t,
        "items": pms[(page - 1) * limit: page * limit],
    }


# --------------------------------------------------------------------------- web

def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    @app.get("/api/v1/permits")
    def permits_list(ticker: Optional[str] = None, scope: Optional[str] = None, type: Optional[str] = None,
                     status: Optional[str] = None, days: Optional[str] = None, page: Optional[str] = None,
                     limit: Optional[str] = None, universe: Optional[str] = None):
        try:
            p = parse_params(ticker, scope, type, status, days, page, limit, universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = None
        if p["universe"] == "mtp":
            uni = _universe.get() or None
        with closing(_conn()) as conn:
            have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='permits'").fetchone()
            if not have:
                return JSONResponse({"ok": True, "api_version": API_VERSION, "total": 0, "page": 1, "pages": 0,
                                     "limit": p["limit"], "scope": p["scope"], "items": []}, headers=_headers())
            out = query_permits(conn, p, _names.get(), uni)
        return JSONResponse(out, headers=_headers())


# --------------------------------------------------------------------------- self-tests

def _selftest() -> int:
    fails = []

    def ok(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE permits (pm_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL DEFAULT 0, ticker TEXT, slug TEXT, permit_type TEXT, project TEXT, status TEXT,
        authority TEXT, date TEXT, permit_name TEXT, permit_id TEXT, term TEXT, expiry TEXT, scope TEXT, holder TEXT,
        jurisdiction TEXT, metal TEXT, evidence TEXT, filled_from TEXT, chain_key TEXT,
        chain_items INTEGER NOT NULL DEFAULT 1, first_reported TEXT, stage_rank INTEGER,
        latest INTEGER NOT NULL DEFAULT 1, n_rows INTEGER NOT NULL DEFAULT 1, tag_confirmed INTEGER NOT NULL DEFAULT 0,
        raw_headline TEXT, published_at TEXT, extractor_version TEXT);
    """)

    def row(eid, t, date, typ="drill_exploration", proj=None, status="granted", key=None, latest=1, auth=None,
            tagged=1, term=None, ordinal=0):
        conn.execute("INSERT INTO permits (event_id, ordinal, ticker, slug, permit_type, project, status, authority, "
                     "date, term, chain_key, latest, tag_confirmed, raw_headline, published_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, ordinal, t, "s-" + eid, typ, proj, status, auth, date, term, key, latest, tagged,
                      "HEADLINE " + eid, date + "T12:00:00"))

    # one permit over two releases: applied -> granted (the publisher filled the lead's authority)
    row("a1", "ABC.V", "2026-03-02", proj="Alpha", status="applied", key="ABC.V:alpha:drill_exploration#1", latest=0,
        auth="Ontario Ministry of Mines")
    row("a2", "ABC.V", "2026-05-15", proj="Alpha", status="granted", key="ABC.V:alpha:drill_exploration#1",
        auth="Ontario Ministry of Mines", term="3 years")
    row("a3", "ABC.V", "2026-05-15", typ="water", proj="Alpha", status="applied", key="ABC.V:alpha:water#2", ordinal=1)
    row("m0", "ABC.V", "2026-06-01", typ=None, status=None)                                   # marker
    row("u1", "ABC.V", "2026-07-01", typ="mining_licence", proj="Beta", status="in_review", key="ABC.V:beta:ml#3",
        tagged=0)                                                                              # untagged release
    row("t1", "TXG.TO", "2026-09-10", typ="environmental_assessment", proj="Media Luna", status="granted",
        key="TXG.TO:media luna:ea#4", auth="SEMARNAT")
    row("x1", "ABC.CN", "2026-02-01", proj="Namesake", key="ABC.CN:n:d#5")
    names = {"ABC.V": "ABC Gold Corp.", "TXG.TO": "Torex Gold Resources Inc."}
    P = lambda **kw: parse_params(today=_dt.date(2026, 9, 23), **kw)

    r = query_permits(conn, P(), names, None)
    ok("one item per permit, tagged only, newest first, markers skipped",
       [x["project"] for x in r["items"]] == ["Media Luna", "Alpha", "Alpha", "Namesake"] and r["total"] == 4)
    al = [x for x in r["items"] if x["type"] == "drill_exploration" and x["project"] == "Alpha"][0]
    ok("the lead row leads, stages listed newest first",
       al["status"] == "granted" and al["releases"] == 2 and al["first_reported"] == "2026-03-02"
       and al["authority"] == "Ontario Ministry of Mines" and al["term"] == "3 years"
       and [s["status"] for s in al["stages"]] == ["granted", "applied"] and al["type_label"] == "Drill / exploration"
       and al["release_url"].endswith("/news/abc.v/s-a2"))
    ok("scope=all adds untagged", query_permits(conn, P(scope="all"), names, None)["total"] == 5)
    ok("exact listing wins over a namesake", query_permits(conn, P(ticker="ABC.V"), names, None)["total"] == 2)
    ok("bare ticker matches both", query_permits(conn, P(ticker="ABC"), names, None)["total"] == 3)
    ok("type / status filters", query_permits(conn, P(type="water"), names, None)["total"] == 1
       and query_permits(conn, P(status="granted"), names, None)["total"] == 3
       and query_permits(conn, P(status="in-review", scope="all"), names, None)["items"][0]["project"] == "Beta")
    ok("universe", query_permits(conn, P(universe="mtp"), names, frozenset({"TXG"}))["total"] == 1)
    ok("days", query_permits(conn, P(days="30"), names, None)["total"] == 1)
    ok("company names", r["items"][0]["company"] == "Torex Gold Resources Inc.")

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad params", bad(type="x") and bad(status="x") and bad(ticker="A'--") and bad(universe="x") and bad(scope="x"))
    print("permits_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        if "/opt/mnt/app" not in sys.path and os.path.isdir("/opt/mnt/app"):
            sys.path.insert(0, "/opt/mnt/app")
        sys.exit(_selftest())
    print(__doc__)
