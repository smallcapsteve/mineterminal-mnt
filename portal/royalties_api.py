"""MNT Royalties & Streams API v1: read-only JSON for cross-site use (MTP company pages).

MNT_ROYALTIES_API_V1 (2026-09-21). Serves what ROY_V1 publishes into `royalty_deals`, one item per DEAL:
the announcement and the closing, or the seller's and the buyer's release of the same stream, are one
deal (the publisher's deal_key), shown from its latest release with the number of releases and the date
it was first reported. Gaps in the latest release (price, rate, a party) are filled from the earlier ones.

  /api/v1/royalties      deals, newest first, filterable

A company is part of a deal when it issued one of the deal's releases OR is named in it as buyer, seller
or operator - Wheaton's page shows the royalty it bought from Spanish Mountain even though Spanish
Mountain issued the release. With `ticker`, each item says how (`roles`: issuer, buyer, seller, operator).
Name matching is conservative: company names are compared with the corporate suffixes removed, and a
one-word name only matches a one-word party if it is not a generic word (Gold, Royalties, Metals...).

List parameters
  ticker     exact symbol (SPA.V) or bare (SPA)
  type       NSR | GRR | NPI | stream | other
  action     new | transfer | buyback | amendment
  days       only deals whose latest release is in the last N days
  page, limit    1-based page, limit 1..200 (default 50) - counted in deals
  universe   all (default) | mtp -> only deals issued by companies on MTP's list (fails open)

Registered from portal.serve via royalties_api.register(app).
Self-tests: python3 -m portal.royalties_api --selftest   (in-memory; touches nothing live)
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
import unicodedata
from contextlib import closing
from typing import Any, Optional

DB_PATH = "/opt/mnt/app/portal/portal.db"
TICKERS_PATH = "/opt/mnt/app/tickers.json"
MTP_UNIVERSE_PATH = "/var/lib/mnt-portal/mtp-companies.json"
SITE_BASE = "https://miningnewsterminal.com"
API_VERSION = "1"
MAX_LIMIT = 200
DEFAULT_LIMIT = 50
TYPES = {"nsr": "NSR", "grr": "GRR", "npi": "NPI", "stream": "stream", "other": "other"}
ACTIONS = ("new", "transfer", "buyback", "amendment")
TYPE_LABELS = {"NSR": "NSR", "GRR": "GRR", "NPI": "NPI", "stream": "Stream", "other": "Royalty"}
ACTION_LABELS = {"new": "New / granted", "transfer": "Bought / sold", "buyback": "Buyback / buy-down",
                 "amendment": "Amended"}

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")

_COLS = ("rd_id, event_id, ordinal, ticker, slug, type, rate_pct, metal, property, operator, buyer, seller, price, "
         "currency, price_note, action, status, deal_key, raw_headline, published_at")


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





# --------------------------------------------------------------------------- company names

_SUFFIX = {"inc", "incorporated", "corp", "corporation", "ltd", "limited", "llc", "plc", "co", "company", "the",
           "sa", "se", "ag", "nl", "pty", "lp", "ltda", "sac", "cv", "de"}
_GENERIC_ONE = {"gold", "silver", "copper", "royalties", "royalty", "metals", "metal", "mining", "mines", "resources",
                "minerals", "capital", "energy", "streaming", "holdings", "group", "ventures", "exploration",
                "uranium", "lithium", "nickel", "zinc", "precious", "critical", "global", "international"}


def name_key(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", s or "").lower()
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    words = [w for w in re.findall(r"[a-z0-9]+", s) if w not in _SUFFIX]
    return " ".join(words)


def same_name(a: Optional[str], b: Optional[str]) -> bool:
    """Is party name `a` the company named `b`? Equal once suffixes are dropped, or one is the other's
    leading words - with the shorter at least two words, or one word that is not generic."""
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    short, long_ = (ka, kb) if len(ka) <= len(kb) else (kb, ka)
    if not long_.startswith(short + " "):
        return False
    words = short.split()
    return len(words) >= 2 or (len(words[0]) >= 5 and words[0] not in _GENERIC_ONE)


# --------------------------------------------------------------------------- params

class BadRequest(ValueError):
    pass


def parse_params(ticker=None, type=None, action=None, days=None, page=None, limit=None, universe=None,
                 today=None) -> dict:
    p: dict[str, Any] = {}
    t = (ticker or "").strip()
    if t:
        if not _TICKER_RE.match(t):
            raise BadRequest("ticker: letters, digits, '.' or '-' only")
        p["ticker"] = t.upper()
    ty = (type or "").strip().lower()
    if ty:
        if ty not in TYPES:
            raise BadRequest("type: NSR, GRR, NPI, stream or other")
        p["type"] = TYPES[ty]
    ac = (action or "").strip().lower()
    if ac:
        if ac not in ACTIONS:
            raise BadRequest("action: new, transfer, buyback or amendment")
        p["action"] = ac
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


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


_FILL = ("rate_pct", "metal", "property", "operator", "buyer", "seller", "price", "currency", "price_note", "status")


def build_deals(rows, names: dict) -> list[dict]:
    """rows in (published_at, event_id, ordinal) order -> deals, newest first."""
    groups: dict[str, list] = {}
    order: list[str] = []
    for r in rows:
        if not r["type"]:
            continue
        k = r["deal_key"] or ("row:%s" % r["rd_id"])
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(r)
    out = []
    for k in order:
        rs = groups[k]                          # chronological
        last = rs[-1]
        d = {f: last[f] for f in _FILL}
        for r in reversed(rs[:-1]):
            for f in _FILL:
                if d.get(f) in (None, "") and r[f] not in (None, ""):
                    d[f] = r[f]
        t = (last["ticker"] or "").strip()
        releases = []
        seen = set()
        for r in rs:
            if r["event_id"] in seen:
                continue
            seen.add(r["event_id"])
            releases.append({"ticker": (r["ticker"] or "").strip(), "date": (r["published_at"] or "")[:10],
                             "headline": _title(r["raw_headline"] or ""),
                             "release_url": release_url(r["ticker"], r["slug"], r["event_id"])})
        out.append({
            "deal_id": last["rd_id"], "ticker": t, "bare_ticker": bare(t), "company": company_name(t, names),
            "type": last["type"], "type_label": TYPE_LABELS.get(last["type"], last["type"] or ""),
            "rate_pct": _num(d["rate_pct"]), "metal": d["metal"] or "", "property": d["property"] or "",
            "operator": d["operator"] or "", "buyer": d["buyer"] or "", "seller": d["seller"] or "",
            "price": _num(d["price"]), "currency": d["currency"] or "", "price_note": d["price_note"] or "",
            "action": last["action"] or "", "action_label": ACTION_LABELS.get(last["action"] or "", last["action"] or ""),
            "status": d["status"] or "",
            "date": (last["published_at"] or "")[:10], "published_at": last["published_at"] or "",
            "first_reported": (rs[0]["published_at"] or "")[:10], "releases": len(releases),
            "headline": _title(last["raw_headline"] or ""),
            "release_url": release_url(t, last["slug"], last["event_id"]),
            "all_releases": releases[::-1],
            "_issuers": {bare(r["ticker"]) for r in rs if r["ticker"]},
        })
    out.sort(key=lambda x: (x["published_at"], x["deal_id"]), reverse=True)
    return out


def roles_for(deal: dict, ticker: str, company: str) -> list:
    roles = []
    if bare(ticker) in deal["_issuers"]:
        roles.append("issuer")
    for f in ("buyer", "seller", "operator"):
        if company and same_name(deal.get(f), company):
            roles.append(f)
    return roles


def query_deals(conn, p: dict, names: dict, universe: Optional[frozenset]) -> dict:
    rows = conn.execute("SELECT " + _COLS + " FROM royalty_deals WHERE type IS NOT NULL "
                        "ORDER BY published_at, event_id, ordinal").fetchall()
    deals = build_deals(rows, names)
    t = p.get("ticker")
    if t:
        company = ""
        for k, v in names.items():
            if k.upper() == t or bare(k) == bare(t):
                company = v
                if k.upper() == t:
                    break
        keep = []
        for d in deals:
            rl = roles_for(d, t, company)
            if rl:
                d["roles"] = rl
                keep.append(d)
        deals = keep
    elif universe:
        deals = [d for d in deals if d["_issuers"] & universe]
    if p.get("type"):
        deals = [d for d in deals if d["type"] == p["type"]]
    if p.get("action"):
        deals = [d for d in deals if d["action"] == p["action"]]
    if p.get("since"):
        deals = [d for d in deals if d["date"] >= p["since"]]
    for d in deals:
        d.pop("_issuers", None)
    total, limit, page = len(deals), p["limit"], p["page"]
    return {
        "ok": True, "api_version": API_VERSION, "total": total, "page": page,
        "pages": max(1, math.ceil(total / limit)) if total else 0, "limit": limit,
        "filters": {k: p[k] for k in ("ticker", "type", "action", "since") if p.get(k)},
        "universe": p["universe"], "universe_applied": bool(universe) and not t,
        "items": deals[(page - 1) * limit: page * limit],
    }


# --------------------------------------------------------------------------- web

def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    @app.get("/api/v1/royalties")
    def royalties_list(ticker: Optional[str] = None, type: Optional[str] = None, action: Optional[str] = None,
                       days: Optional[str] = None, page: Optional[str] = None,
                       limit: Optional[str] = None, universe: Optional[str] = None):
        try:
            p = parse_params(ticker, type, action, days, page, limit, universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = None
        if p["universe"] == "mtp":
            uni = _universe.get() or None
        with closing(_conn()) as conn:
            have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='royalty_deals'").fetchone()
            if not have:
                return JSONResponse({"ok": True, "api_version": API_VERSION, "total": 0, "page": 1, "pages": 0,
                                     "limit": p["limit"], "items": []}, headers=_headers())
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
    CREATE TABLE royalty_deals (rd_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL DEFAULT 0, ticker TEXT, slug TEXT, type TEXT, rate_pct REAL, metal TEXT,
        property TEXT, operator TEXT, buyer TEXT, seller TEXT, price REAL, currency TEXT, price_note TEXT,
        action TEXT, status TEXT, deal_key TEXT, deal_releases INTEGER NOT NULL DEFAULT 1, first_reported TEXT,
        is_latest INTEGER NOT NULL DEFAULT 1, n_rows INTEGER NOT NULL DEFAULT 1, tag_confirmed INTEGER NOT NULL DEFAULT 0,
        raw_headline TEXT, published_at TEXT, extractor_version TEXT);
    """)

    def row(eid, t, date, typ="NSR", rate=None, prop=None, op=None, buyer=None, seller=None, price=None, cur=None,
            action="new", status=None, key=None, head="HEADLINE"):
        conn.execute("INSERT INTO royalty_deals (event_id, ticker, slug, type, rate_pct, property, operator, buyer, seller, "
                     "price, currency, action, status, deal_key, raw_headline, published_at) VALUES "
                     "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, t, "s-" + eid, typ, rate, prop, op, buyer, seller, price, cur, action, status, key, head,
                      date + "T12:00:00"))

    # an announcement by the buyer, then the seller's closing release of the same deal
    row("e1", "EVR.CN", "2026-05-14", rate=0.5, prop="Sunnyside", seller="Evolve", price=2.25e6, cur="USD",
        status="agreed", key="NSR:sunnyside#48")
    row("e2", "EVR.CN", "2026-06-24", rate=0.5, prop="Sunnyside", op="Barksdale Resources", buyer="Evolve Royalties",
        seller="MinQuest", action="transfer", status="closed", key="NSR:sunnyside#48")
    # a royalty sold by Spanish Mountain to Wheaton - Wheaton issued nothing
    row("s1", "SPA.V", "2026-04-21", rate=1.5, prop="Spanish Mountain", op="Spanish Mountain Gold",
        buyer="Wheaton Precious Metals", seller="Spanish Mountain Gold", price=55e6, cur="USD", key="NSR:spanish#43")
    # no property -> no deal_key: stands alone
    row("t1", "TITI.V", "2026-09-16", rate=1.0, buyer="Silver Crown Royalties", price=2e6, cur="USD",
        action="transfer", status="closed")
    row("m1", "SPA.V", "2026-05-01", typ=None)            # marker
    names = {"EVR.CN": "Evolve Royalties Ltd.", "SPA.V": "Spanish Mountain Gold Ltd.",
             "WPM.TO": "Wheaton Precious Metals Corp.", "GOLD.V": "Gold Corp"}
    P = lambda **kw: parse_params(today=_dt.date(2026, 9, 21), **kw)

    r = query_deals(conn, P(), names, None)
    ok("one item per deal, newest first", [d["deal_id"] for d in r["items"]] == [4, 2, 3] and r["total"] == 3)
    ev = r["items"][1]
    ok("deal: latest release, gaps filled, releases counted",
       ev["status"] == "closed" and ev["price"] == 2.25e6 and ev["currency"] == "USD" and ev["releases"] == 2
       and ev["first_reported"] == "2026-05-14" and ev["date"] == "2026-06-24" and ev["seller"] == "MinQuest"
       and ev["all_releases"][0]["date"] == "2026-06-24" and ev["type_label"] == "NSR"
       and ev["action_label"] == "Bought / sold")
    r = query_deals(conn, P(ticker="WPM.TO"), names, None)
    ok("a company named as buyer sees the deal", r["total"] == 1 and r["items"][0]["roles"] == ["buyer"]
       and r["items"][0]["ticker"] == "SPA.V")
    r = query_deals(conn, P(ticker="SPA"), names, None)
    ok("issuer and named party", r["total"] == 1 and r["items"][0]["roles"] == ["issuer", "seller", "operator"])
    r = query_deals(conn, P(ticker="EVR.CN"), names, None)
    ok("issuer of a chained deal", r["total"] == 1 and "issuer" in r["items"][0]["roles"] and "buyer" in r["items"][0]["roles"])
    ok("generic one-word names do not match", not same_name("Gold", "Gold Standard Ventures")
       and not same_name("Royalties", "Royalties Inc Holdings"))
    ok("same_name", same_name("Newmont", "Newmont Corporation") and same_name("Evolve", "Evolve Royalties Ltd.")
       and not same_name("Silver", "Silver North Resources") and not same_name("Gold X2 Mining", "Gold Standard Ventures")
       and same_name("Wheaton Precious Metals", "Wheaton Precious Metals Corp."))
    ok("type / action filters", query_deals(conn, P(type="nsr", action="transfer"), names, None)["total"] == 2)
    ok("universe", query_deals(conn, P(universe="mtp"), names, frozenset({"SPA"}))["total"] == 1)
    ok("days", query_deals(conn, P(days="120"), names, None)["total"] == 2)

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad params", bad(type="x") and bad(action="x") and bad(ticker="A'--") and bad(universe="x"))
    print("royalties_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        if "/opt/mnt/app" not in sys.path and os.path.isdir("/opt/mnt/app"):
            sys.path.insert(0, "/opt/mnt/app")
        sys.exit(_selftest())
    print(__doc__)
