"""MNT Property Options & Staking API v1: read-only JSON for cross-site use (MTP company pages).

MNT_PROPERTY_OPTIONS_API_V1 (2026-09-23). Serves what OPT_V1 publishes into `land_deals`, one item per DEAL: the
release announcing an option, the payment releases and the one saying the option was exercised are one deal (the
publisher's chain_key), shown from its lead row (latest=1, which the publisher has already filled from the chain's
other items), with every stage behind it. Staking is always its own item. Marker rows (a tagged release with no
deal) are skipped.

  /api/v1/property-options      deals, newest first, filterable

List parameters
  ticker     exact symbol (AMQ.V) or bare (AMQ); an exact symbol ignores namesakes on other exchanges
  scope      tagged (default: the lead release carries the Property Options & Staking tag, as /property-options shows)
             | all (also deals read from untagged releases; less checked)
  type       option_in | option_out | staking | claim_purchase | property_purchase | property_sale
  stage      proposed | signed | payment | completed | amended | terminated   (of the lead row)
  days       only deals whose lead item is in the last N days
  page, limit    1-based page, limit 1..200 (default 50) - counted in deals
  universe   all (default) | mtp -> only companies on MTP's list (fails open)

Registered from portal.serve via property_options_api.register(app).
Self-tests: python3 -m portal.property_options_api --selftest   (in-memory; touches nothing live)
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
TYPES = ("option_in", "option_out", "staking", "claim_purchase", "property_purchase", "property_sale")
STAGES = ("proposed", "signed", "payment", "completed", "amended", "terminated")
SCOPES = ("tagged", "all")
# the publisher's labels, copied so this module imports nothing from the reader
TYPE_LABELS = {"option_in": "Option in / earn-in", "option_out": "Option out", "staking": "Staking",
               "claim_purchase": "Claim purchase", "property_purchase": "Property purchase",
               "property_sale": "Property sale"}
STAGE_LABELS = {"proposed": "Proposed (LOI)", "signed": "Signed", "payment": "Payment made", "completed": "Completed",
                "amended": "Amended", "terminated": "Terminated"}

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")

_COLS = ("ld_id, event_id, ordinal, ticker, slug, deal_type, stage, property, counterparty, interest_pct, cash, "
         "currency, shares, work, nsr, term, area, date, metal, jurisdiction, chain_key, chain_items, first_reported, "
         "latest, tag_confirmed, raw_headline, published_at")


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


def parse_params(ticker=None, scope=None, type=None, stage=None, days=None, page=None, limit=None, universe=None,
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
    ty = (type or "").strip().lower().replace("-", "_")
    if ty:
        if ty not in TYPES:
            raise BadRequest("type: " + ", ".join(TYPES))
        p["type"] = ty
    sg = (stage or "").strip().lower()
    if sg:
        if sg not in STAGES:
            raise BadRequest("stage: " + ", ".join(STAGES))
        p["stage"] = sg
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


def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def build_deals(rows, names: dict) -> list[dict]:
    """rows in (published_at, event_id, ordinal) order -> deals, newest first."""
    groups: dict[str, list] = {}
    order: list[str] = []
    for r in rows:
        if not r["deal_type"]:
            continue                            # marker row: a tagged release with no deal
        k = r["chain_key"] or ("row:%s" % r["ld_id"])
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
            stages.append({"date": _s(r["published_at"])[:10], "stage": _s(r["stage"]),
                           "stage_label": STAGE_LABELS.get(_s(r["stage"]), _s(r["stage"])),
                           "tagged": str(r["tag_confirmed"]) == "1", "headline": _title(_s(r["raw_headline"])),
                           "release_url": release_url(r["ticker"], r["slug"], r["event_id"])})
        dt = _s(last["deal_type"])
        sg = _s(last["stage"])
        out.append({
            "deal_key": _s(last["chain_key"]) or ("row:%s" % last["ld_id"]), "row_id": last["ld_id"],
            "ticker": t, "bare_ticker": bare(t), "company": company_name(t, names),
            "type": dt, "type_label": TYPE_LABELS.get(dt, "Land deal"),
            "stage": sg, "stage_label": STAGE_LABELS.get(sg, sg),
            "property": _s(last["property"]), "counterparty": _s(last["counterparty"]),
            "interest_pct": _num(last["interest_pct"]), "cash": _num(last["cash"]), "currency": _s(last["currency"]),
            "shares": _num(last["shares"]), "work": _num(last["work"]), "nsr": _num(last["nsr"]),
            "term_years": _num(last["term"]), "area_ha": _num(last["area"]), "agreement_date": _s(last["date"]),
            "metal": _s(last["metal"]), "jurisdiction": _s(last["jurisdiction"]),
            "tagged": str(last["tag_confirmed"]) == "1",
            "date": _s(last["published_at"])[:10], "published_at": _s(last["published_at"]),
            "first_reported": _s(rs[0]["published_at"])[:10], "releases": len(stages),
            "headline": _title(_s(last["raw_headline"])),
            "release_url": release_url(t, last["slug"], last["event_id"]),
            "stages": stages[::-1],
        })
    out.sort(key=lambda x: (x["published_at"], x["row_id"]), reverse=True)
    return out


def query_deals(conn, p: dict, names: dict, universe: Optional[frozenset]) -> dict:
    sql = "SELECT " + _COLS + " FROM land_deals WHERE deal_type IS NOT NULL"
    args: list = []
    t = p.get("ticker")
    if t:
        b = bare(t)
        sql += " AND (UPPER(ticker) = ? OR UPPER(ticker) = ? OR UPPER(ticker) LIKE ?)"
        args += [t, b, b + ".%"]
    rows = conn.execute(sql + " ORDER BY published_at, event_id, ordinal", args).fetchall()
    if t and "." in t and any(_s(r["ticker"]).upper() == t for r in rows):
        rows = [r for r in rows if _s(r["ticker"]).upper() == t]    # the listing asked for, not a namesake
    ds = build_deals(rows, names)
    if p["scope"] == "tagged":
        ds = [x for x in ds if x["tagged"]]        # same rule as /property-options: the lead release is tagged
    if universe and not t:
        ds = [x for x in ds if x["bare_ticker"] in universe]
    if p.get("type"):
        ds = [x for x in ds if x["type"] == p["type"]]
    if p.get("stage"):
        ds = [x for x in ds if x["stage"] == p["stage"]]
    if p.get("since"):
        ds = [x for x in ds if x["date"] >= p["since"]]
    total, limit, page = len(ds), p["limit"], p["page"]
    return {
        "ok": True, "api_version": API_VERSION, "total": total, "page": page,
        "pages": max(1, math.ceil(total / limit)) if total else 0, "limit": limit,
        "filters": {k: p[k] for k in ("ticker", "type", "stage", "since") if p.get(k)},
        "scope": p["scope"], "universe": p["universe"], "universe_applied": bool(universe) and not t,
        "items": ds[(page - 1) * limit: page * limit],
    }


# --------------------------------------------------------------------------- web

def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    @app.get("/api/v1/property-options")
    def property_options_list(ticker: Optional[str] = None, scope: Optional[str] = None, type: Optional[str] = None,
                              stage: Optional[str] = None, days: Optional[str] = None, page: Optional[str] = None,
                              limit: Optional[str] = None, universe: Optional[str] = None):
        try:
            p = parse_params(ticker, scope, type, stage, days, page, limit, universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = None
        if p["universe"] == "mtp":
            uni = _universe.get() or None
        with closing(_conn()) as conn:
            have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='land_deals'").fetchone()
            if not have:
                return JSONResponse({"ok": True, "api_version": API_VERSION, "total": 0, "page": 1, "pages": 0,
                                     "limit": p["limit"], "scope": p["scope"], "items": []}, headers=_headers())
            out = query_deals(conn, p, _names.get(), uni)
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
    CREATE TABLE land_deals (ld_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL DEFAULT 0, ticker TEXT, slug TEXT, deal_type TEXT, stage TEXT, property TEXT,
        counterparty TEXT, interest_pct REAL, cash REAL, currency TEXT, shares REAL, work REAL, nsr REAL, term REAL,
        area REAL, date TEXT, metal TEXT, jurisdiction TEXT, filled_from TEXT, chain_key TEXT,
        chain_items INTEGER NOT NULL DEFAULT 1, first_reported TEXT, stage_rank INTEGER,
        latest INTEGER NOT NULL DEFAULT 1, n_rows INTEGER NOT NULL DEFAULT 1, tag_confirmed INTEGER NOT NULL DEFAULT 0,
        raw_headline TEXT, published_at TEXT, extractor_version TEXT);
    """)

    def row(eid, t, date, typ="option_in", prop=None, stage="signed", key=None, latest=1, cp=None, tagged=1,
            cash=None, pct=None, area=None, ordinal=0):
        conn.execute("INSERT INTO land_deals (event_id, ordinal, ticker, slug, deal_type, stage, property, counterparty, "
                     "interest_pct, cash, currency, area, date, chain_key, latest, tag_confirmed, raw_headline, "
                     "published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, ordinal, t, "s-" + eid, typ, None if typ is None else stage, prop, cp, pct, cash,
                      "CAD" if cash else None, area, date, key, latest, tagged, "HEADLINE " + eid, date + "T12:00:00"))

    # one option over two releases: signed -> completed (the publisher filled the lead's cash)
    row("a1", "ABC.V", "2026-03-02", prop="Alpha", key="ABC.V:in:alpha#1", latest=0, cp="Beta Minerals", cash=250000,
        pct=100)
    row("a2", "ABC.V", "2027-05-15", prop="Alpha", stage="completed", key="ABC.V:in:alpha#1", cp="Beta Minerals",
        cash=250000, pct=100)
    row("a3", "ABC.V", "2027-05-15", typ="staking", prop="Gamma Lake", key="ABC.V:stake:x#2", area=2300, ordinal=1)
    row("m0", "ABC.V", "2026-06-01", typ=None)                                                    # marker
    row("u1", "ABC.V", "2026-07-01", typ="property_sale", prop="Beta", stage="proposed", key="ABC.V:sell:beta#3",
        tagged=0)                                                                                  # untagged
    row("t1", "AMQ.V", "2026-09-10", typ="option_out", prop="B26 Deposit", stage="signed", key="AMQ.V:out:b26#4")
    row("x1", "ABC.CN", "2026-02-01", prop="Namesake", key="ABC.CN:in:n#5")
    names = {"ABC.V": "ABC Gold Corp.", "AMQ.V": "AMQ Mining Ltd."}
    P = lambda **kw: parse_params(today=_dt.date(2027, 5, 20), **kw)

    r = query_deals(conn, P(), names, None)
    ok("one item per deal, tagged only, newest first, markers skipped",
       [x["property"] for x in r["items"]] == ["Gamma Lake", "Alpha", "B26 Deposit", "Namesake"] and r["total"] == 4)
    al = [x for x in r["items"] if x["property"] == "Alpha"][0]
    ok("the lead row leads, stages listed newest first",
       al["stage"] == "completed" and al["releases"] == 2 and al["first_reported"] == "2026-03-02"
       and al["counterparty"] == "Beta Minerals" and al["cash"] == 250000.0 and al["interest_pct"] == 100.0
       and [s["stage"] for s in al["stages"]] == ["completed", "signed"] and al["type_label"] == "Option in / earn-in"
       and al["release_url"].endswith("/news/abc.v/s-a2"))
    ok("staking carries its area", r["items"][0]["type"] == "staking" and r["items"][0]["area_ha"] == 2300.0)
    ok("scope=all adds untagged", query_deals(conn, P(scope="all"), names, None)["total"] == 5)
    ok("exact listing wins over a namesake", query_deals(conn, P(ticker="ABC.V"), names, None)["total"] == 2)
    ok("bare ticker matches both", query_deals(conn, P(ticker="ABC"), names, None)["total"] == 3)
    ok("type / stage filters", query_deals(conn, P(type="staking"), names, None)["total"] == 1
       and query_deals(conn, P(type="option-out"), names, None)["total"] == 1
       and query_deals(conn, P(stage="completed"), names, None)["total"] == 1
       and query_deals(conn, P(stage="proposed", scope="all"), names, None)["items"][0]["property"] == "Beta")
    ok("universe", query_deals(conn, P(universe="mtp"), names, frozenset({"AMQ"}))["total"] == 1)
    ok("days", query_deals(conn, P(days="30"), names, None)["total"] == 2)
    ok("company names", [x for x in r["items"] if x["ticker"] == "AMQ.V"][0]["company"] == "AMQ Mining Ltd.")

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad params", bad(type="x") and bad(stage="x") and bad(ticker="A'--") and bad(universe="x") and bad(scope="x"))
    print("property_options_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        if "/opt/mnt/app" not in sys.path and os.path.isdir("/opt/mnt/app"):
            sys.path.insert(0, "/opt/mnt/app")
        sys.exit(_selftest())
    print(__doc__)
