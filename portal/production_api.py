"""MNT Production Results API v1: read-only JSON for cross-site use (MTP company pages).

MNT_PRODUCTION_API_V1 (2026-09-21). Serves what PROD_V1 publishes into `production_results`, shaped the
way a company page needs it: one item per FIGURE, not per release.

  /api/v1/production     production, guidance and milestones, newest period first, filterable

Why grouped: a producer states each quarter twice (the production release, then the results) and
repeats its annual guidance in every release until it changes. A company page listing each statement
would show Q2 three times and the same guidance six times. So:
  actual     one item per (period, metal, unit, asset); the latest release's figures, with sold, AISC and
             the guidance it was measured against filled in from the other releases where the latest
             leaves them out;
  guidance   one item per (period, metal, unit, asset); the LATEST range, and when an earlier release gave
             a different range, that range as prior_low / prior_high (guidance raised or cut);
  milestone  one item per (milestone, asset): first gold pour, commercial production, restart...
Marker rows (tagged releases with no figures) are left out.

List parameters
  ticker     exact symbol (TXG.TO) or bare (TXG)
  kind       actual | guidance | milestone
  metal      e.g. gold, silver, copper, AuEq (case-insensitive)
  days       only items whose latest release is in the last N days
  page, limit    1-based page, limit 1..200 (default 50) - counted in items
  universe   all (default) | mtp -> only companies on MTP's list (fails open, like the other APIs)

Registered from portal.serve via production_api.register(app).
Self-tests: python3 -m portal.production_api --selftest   (in-memory; touches nothing live)
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
KINDS = ("actual", "guidance", "milestone")
_KIND_ORDER = {"actual": 0, "guidance": 1, "milestone": 2}

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")
_METAL_RE = re.compile(r"^[A-Za-z0-9 _-]{1,24}$")

_COLS = ("pr_id, event_id, ordinal, ticker, slug, kind, period, period_end, metal, unit, qty, low, high, sold, "
         "aisc, guided_low, guided_high, milestone, asset, basis, approx, raw_headline, published_at")


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




class BadRequest(ValueError):
    pass


def parse_params(ticker=None, kind=None, metal=None, days=None, page=None, limit=None, universe=None,
                 today=None) -> dict:
    p: dict[str, Any] = {}
    t = (ticker or "").strip()
    if t:
        if not _TICKER_RE.match(t):
            raise BadRequest("ticker: letters, digits, '.' or '-' only")
        p["ticker"] = t.upper()
    k = (kind or "").strip().lower()
    if k:
        if k not in KINDS:
            raise BadRequest("kind: actual, guidance or milestone")
        p["kind"] = k
    m = (metal or "").strip()
    if m:
        if not _METAL_RE.match(m):
            raise BadRequest("metal: letters and digits only")
        p["metal"] = m.lower()
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


def guidance_fits(qty, low, high) -> bool:
    """Is a 'measured against' range plausibly about the same figure? The reader sometimes carries a
    single mine's guidance onto a company total (922,827 oz against 225,000-250,000). A range the actual
    misses by more than half is not shown as the comparison."""
    q, lo, hi = _num(qty), _num(low), _num(high)
    if q is None or (lo is None and hi is None):
        return False
    lo = lo if lo is not None else hi
    hi = hi if hi is not None else lo
    return 0.5 * lo <= q <= 2.0 * hi


def _key(r) -> tuple:
    kind = r["kind"]
    asset = (r["asset"] or "").strip().lower()
    if kind == "milestone":
        return (bare(r["ticker"]), kind, (r["milestone"] or "").lower(), asset)
    return (bare(r["ticker"]), kind, r["period"] or "", (r["metal"] or "").lower(), (r["unit"] or "").lower(), asset)


_FILL = ("sold", "aisc", "guided_low", "guided_high", "basis")


def build_items(rows, names: dict) -> list[dict]:
    """rows in (published_at, event_id, ordinal) order -> items, newest period first."""
    groups: dict[tuple, dict] = {}
    for r in rows:
        if not r["kind"]:
            continue
        k = _key(r)
        g = groups.get(k)
        if g is None:
            groups[k] = g = {"rows": []}
        g["rows"].append(r)
    out = []
    for g in groups.values():
        rs = g["rows"]                         # chronological
        last = rs[-1]
        item = {
            "item_id": last["pr_id"], "ticker": (last["ticker"] or "").strip(), "kind": last["kind"],
            "period": last["period"] or "", "period_end": last["period_end"] or "",
            "metal": last["metal"] or "", "unit": last["unit"] or "",
            "qty": _num(last["qty"]), "low": _num(last["low"]), "high": _num(last["high"]),
            "sold": _num(last["sold"]), "aisc": _num(last["aisc"]),
            "guided_low": _num(last["guided_low"]), "guided_high": _num(last["guided_high"]),
            "milestone": last["milestone"] or "", "asset": last["asset"] or "", "basis": last["basis"] or "",
            "approx": bool(last["approx"]),
        }
        # the latest statement's gaps, filled from the earlier ones (newest first)
        for r in reversed(rs[:-1]):
            for f in _FILL:
                if item.get(f) in (None, "") and r[f] not in (None, ""):
                    item[f] = _num(r[f]) if f != "basis" else r[f]
            if item["kind"] == "actual" and item["qty"] is None and r["qty"] is not None:
                item["qty"] = _num(r["qty"])
        if item["kind"] == "actual" and not guidance_fits(item["qty"], item["guided_low"], item["guided_high"]):
            item["guided_low"] = item["guided_high"] = None
        prior_low = prior_high = None
        if item["kind"] == "guidance":
            for r in reversed(rs[:-1]):
                lo, hi = _num(r["low"]), _num(r["high"])
                if (lo, hi) != (item["low"], item["high"]) and (lo is not None or hi is not None):
                    prior_low, prior_high = lo, hi
                    break
        t = item["ticker"]
        item.update({
            "bare_ticker": bare(t), "company": company_name(t, names),
            "prior_low": prior_low, "prior_high": prior_high,
            "date": (last["published_at"] or "")[:10], "published_at": last["published_at"] or "",
            "first_seen": (rs[0]["published_at"] or "")[:10], "releases": len({r["event_id"] for r in rs}),
            "headline": _title(last["raw_headline"] or ""),
            "release_url": release_url(t, last["slug"], last["event_id"]),
        })
        item["sort_date"] = item["period_end"] or item["date"]
        out.append(item)
    out.sort(key=lambda i: (i["sort_date"], i["published_at"], -_KIND_ORDER.get(i["kind"], 9), i["metal"],
                            i["item_id"]), reverse=True)
    for i in out:
        i.pop("sort_date", None)
    return out


def query_items(conn, p: dict, names: dict, universe: Optional[frozenset]) -> dict:
    where = ["kind IS NOT NULL"]
    args: list = []
    t = p.get("ticker")
    if t:
        where.append("(upper(ticker) = ? OR upper(ticker) LIKE ?)")
        args += [t, bare(t) + ".%"]
    if p.get("kind"):
        where.append("kind = ?")
        args.append(p["kind"])
    if p.get("metal"):
        where.append("lower(COALESCE(metal, '')) = ?")
        args.append(p["metal"])
    if universe:
        where.append("(CASE WHEN instr(ticker, '.') > 0 THEN upper(substr(ticker, 1, instr(ticker, '.') - 1)) "
                     "ELSE upper(ticker) END) IN (SELECT value FROM json_each(?))")
        args.append(json.dumps(sorted(universe)))
    rows = conn.execute("SELECT " + _COLS + " FROM production_results WHERE " + " AND ".join(where) +
                        " ORDER BY published_at, event_id, ordinal", args).fetchall()
    items = build_items(rows, names)
    if p.get("since"):
        items = [i for i in items if i["date"] >= p["since"]]
    total, limit, page = len(items), p["limit"], p["page"]
    return {
        "ok": True, "api_version": API_VERSION, "total": total, "page": page,
        "pages": max(1, math.ceil(total / limit)) if total else 0, "limit": limit,
        "filters": {k: p[k] for k in ("ticker", "kind", "metal", "since") if p.get(k)},
        "universe": p["universe"], "universe_applied": bool(universe),
        "items": items[(page - 1) * limit: page * limit],
    }


# --------------------------------------------------------------------------- web


def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    @app.get("/api/v1/production")
    def production_list(ticker: Optional[str] = None, kind: Optional[str] = None, metal: Optional[str] = None,
                        days: Optional[str] = None, page: Optional[str] = None,
                        limit: Optional[str] = None, universe: Optional[str] = None):
        try:
            p = parse_params(ticker, kind, metal, days, page, limit, universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = None
        if p["universe"] == "mtp":
            uni = _universe.get() or None
        with closing(_conn()) as conn:
            have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='production_results'").fetchone()
            if not have:
                return JSONResponse({"ok": True, "api_version": API_VERSION, "total": 0, "page": 1, "pages": 0,
                                     "limit": p["limit"], "items": []}, headers=_headers())
            out = query_items(conn, p, _names.get(), uni)
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
    CREATE TABLE production_results (pr_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL DEFAULT 0, ticker TEXT, slug TEXT, kind TEXT, period TEXT, period_end TEXT,
        metal TEXT, unit TEXT, qty REAL, low REAL, high REAL, sold REAL, aisc REAL, guided_low REAL,
        guided_high REAL, milestone TEXT, asset TEXT, basis TEXT, approx INTEGER NOT NULL DEFAULT 0,
        n_rows INTEGER NOT NULL DEFAULT 1, tag_confirmed INTEGER NOT NULL DEFAULT 0, raw_headline TEXT,
        published_at TEXT, extractor_version TEXT);
    """)
    seq = {"n": 0}

    def row(eid, t, date, kind, period=None, pend=None, metal="gold", unit="oz", qty=None, low=None, high=None,
            sold=None, aisc=None, glo=None, ghi=None, ms=None, asset=None, head="HEADLINE"):
        seq["n"] += 1
        conn.execute("INSERT INTO production_results (event_id, ordinal, ticker, slug, kind, period, period_end, metal, "
                     "unit, qty, low, high, sold, aisc, guided_low, guided_high, milestone, asset, raw_headline, "
                     "published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, seq["n"], t, "s-" + eid, kind, period, pend, None if kind == "milestone" else metal,
                      None if kind == "milestone" else unit, qty, low, high, sold, aisc, glo, ghi, ms, asset, head,
                      date + "T12:00:00"))

    # TTT.TO: Q2 in the production release (with ounces sold), then again in the results (without)
    row("t1", "TTT.TO", "2026-07-07", "actual", "Q2 2026", "2026-06-30", qty=96297, sold=91646)
    row("t1", "TTT.TO", "2026-07-07", "guidance", "FY 2026", "2026-12-31", low=420000, high=470000)
    row("t2", "TTT.TO", "2026-08-06", "actual", "Q2 2026", "2026-06-30", qty=96297, aisc=1650)
    row("t2", "TTT.TO", "2026-08-06", "guidance", "FY 2026", "2026-12-31", low=450000, high=480000)
    row("t2", "TTT.TO", "2026-08-06", "actual", "Q2 2026", "2026-06-30", metal="copper", unit="lb", qty=12.6e6)
    row("t0", "TTT.TO", "2026-02-18", "actual", "FY 2025", "2025-12-31", qty=376364, glo=400000, ghi=450000)
    row("t0", "TTT.TO", "2026-02-18", "actual", "Q4 2025", "2025-12-31", qty=114844)
    # EEE.V: a company total measured against one mine's guidance -> the comparison is dropped
    row("e1", "EEE.V", "2026-01-14", "actual", "FY 2025", "2025-12-31", qty=922827, glo=225000, ghi=250000)
    row("e2", "EEE.V", "2025-11-18", "milestone", ms="commercial_production", asset="Valentine")
    row("e3", "EEE.V", "2025-12-01", "milestone", ms="commercial_production", asset="Valentine")
    row("x1", "EEE.V", "2025-12-02", None)                      # marker row
    names = {"TTT.TO": "Tee Gold Corp."}
    P = lambda **kw: parse_params(today=_dt.date(2026, 9, 21), **kw)

    r = query_items(conn, P(ticker="TTT"), names, None)
    got = [(i["kind"], i["period"], i["metal"]) for i in r["items"]]
    ok("one item per figure, newest period first",
       got == [("guidance", "FY 2026", "gold"), ("actual", "Q2 2026", "gold"), ("actual", "Q2 2026", "copper"),
               ("actual", "Q4 2025", "gold"), ("actual", "FY 2025", "gold")] and r["total"] == 5)
    q2 = r["items"][1]
    ok("restated quarter: latest figures, sold filled in, releases counted",
       q2["qty"] == 96297 and q2["sold"] == 91646 and q2["aisc"] == 1650 and q2["releases"] == 2
       and q2["first_seen"] == "2026-07-07" and q2["date"] == "2026-08-06" and q2["company"] == "Tee Gold Corp.")
    g = r["items"][0]
    ok("guidance: latest range with the prior one", g["low"] == 450000 and g["high"] == 480000
       and g["prior_low"] == 420000 and g["prior_high"] == 470000)
    fy = r["items"][4]
    ok("actual keeps a plausible guided range", fy["guided_low"] == 400000 and fy["guided_high"] == 450000)
    ok("release url", q2["release_url"] == SITE_BASE + "/news/ttt.to/s-t2")
    r = query_items(conn, P(ticker="EEE.V"), names, None)
    ok("implausible guided range dropped, markers left out, milestone once",
       r["total"] == 2 and r["items"][0]["guided_low"] is None
       and [i["kind"] for i in r["items"]] == ["actual", "milestone"] and r["items"][1]["releases"] == 2
       and r["items"][1]["date"] == "2025-12-01")
    ok("kind filter", [i["kind"] for i in query_items(conn, P(ticker="TTT", kind="guidance"), names, None)["items"]] == ["guidance"])
    ok("metal filter", len(query_items(conn, P(metal="Copper"), names, None)["items"]) == 1)
    ok("universe", query_items(conn, P(universe="mtp"), names, frozenset({"EEE"}))["total"] == 2)
    ok("days", query_items(conn, P(days="100"), names, None)["total"] == 3)
    ok("paging", query_items(conn, P(limit="2", page="3"), names, None)["pages"] == 4)
    ok("guidance_fits", guidance_fits(376364, 400000, 450000) and not guidance_fits(922827, 225000, 250000)
       and not guidance_fits(None, 1, 2))

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad params", bad(kind="x") and bad(ticker="A'--") and bad(universe="x") and bad(metal="<b>"))
    ok("limit capped", P(limit="9999")["limit"] == MAX_LIMIT)
    print("production_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        if "/opt/mnt/app" not in sys.path and os.path.isdir("/opt/mnt/app"):
            sys.path.insert(0, "/opt/mnt/app")
        sys.exit(_selftest())
    print(__doc__)
