"""MNT Resource Estimates API v1: read-only JSON for cross-site use (MTP's $/oz screener, Compare, company pages).

MNT_RESOURCES_API_V1 (2026-09-28, MTP site audit C27). Serves every row the resource reader publishes into
`resource_estimates` - one row per deposit per category (Measured, Indicated, Inferred, M&I, Proven, Probable,
P&P, Total) - where the only feed MTP had, /api/resources/recent.json, returns the 50 newest releases' first row.

  /api/v1/resources      rows, newest release first, filterable

Each item is one category of one deposit in one release: tonnes, grades and contained metal as parsed lists, the
cut-off, whether it is a resource or a reserve, what kind of estimate it is (Maiden / Update / Restated), and a
`historic` flag: true when the release restates the figure as background (a previously reported, prior or
historical estimate) rather than announcing it - such a row is not the company's current estimate and must never
be ranked as one (checklist C19). Marker rows (tagged releases that state no figures) are left out.

List parameters
  ticker     exact symbol (PDI.TO) or bare (PDI)
  category   measured | indicated | inferred | mi | proven | probable | pp | total (comma list allowed)
  basis      resource | reserve
  metal      metal focus, e.g. Au, Cu, Li (case-insensitive)
  historic   include (default) | exclude | only
  days       only rows published in the last N days
  latest     1 -> for each company keep only its newest release that states figures (per project when named)
  page, limit    1-based page, limit 1..1000 (default 200) - counted in rows
  universe   all (default) | mtp -> only companies on MTP's list (fails open, like the other APIs)

Registered from portal.serve via resources_api.register(app).
Self-tests: python3 -m portal.resources_api --selftest   (in-memory; touches nothing live)
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
MAX_LIMIT = 1000
DEFAULT_LIMIT = 200
CATEGORIES = {
    "measured": ["Measured"], "indicated": ["Indicated"], "inferred": ["Inferred"],
    "mi": ["Measured & Indicated"], "proven": ["Proven"], "probable": ["Probable"],
    "pp": ["Proven & Probable"], "total": ["Total"],
}
_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")
_METAL_RE = re.compile(r"^[A-Za-z0-9]{1,12}$")
_COLS = ("res_id, event_id, ordinal, ticker, slug, deposit, project, category, tonnes, grades_json, contained_json, "
         "cut_off, basis, context, mre_type, metal_focus, headline_oz_au, headline_t_metal, summary, raw_headline, "
         "published_at, extractor_version")


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


def parse_params(ticker=None, category=None, basis=None, metal=None, historic=None, days=None, latest=None,
                 page=None, limit=None, universe=None, today=None) -> dict:
    p: dict[str, Any] = {}
    t = (ticker or "").strip()
    if t:
        if not _TICKER_RE.match(t):
            raise BadRequest("ticker: letters, digits, '.' or '-' only")
        p["ticker"] = t.upper()
    cats = [c.strip().lower() for c in str(category or "").split(",") if c.strip()]
    if cats:
        out = []
        for c in cats:
            if c not in CATEGORIES:
                raise BadRequest("category: measured, indicated, inferred, mi, proven, probable, pp or total")
            out += CATEGORIES[c]
        p["categories"] = out
    b = (basis or "").strip().lower()
    if b:
        if b not in ("resource", "reserve"):
            raise BadRequest("basis: resource or reserve")
        p["basis"] = b
    m = (metal or "").strip()
    if m:
        if not _METAL_RE.match(m):
            raise BadRequest("metal: letters and digits only")
        p["metal"] = m.lower()
    h = (historic or "include").strip().lower()
    if h not in ("include", "exclude", "only"):
        raise BadRequest("historic: include, exclude or only")
    p["historic"] = h
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
    p["latest"] = str(latest or "").strip().lower() in ("1", "true", "yes")
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


def _js(v) -> list:
    if not v:
        return []
    try:
        x = json.loads(v)
    except (TypeError, ValueError):
        return []
    return x if isinstance(x, list) else []


def is_historic(r) -> bool:
    return (r["context"] or "").strip().lower() == "background"


def to_item(r, names: dict) -> dict:
    t = (r["ticker"] or "").strip()
    return {
        "row_id": r["res_id"], "event_id": r["event_id"], "ordinal": r["ordinal"],
        "ticker": t, "bare_ticker": bare(t), "company": company_name(t, names),
        "project": r["project"] or "", "deposit": r["deposit"] or "",
        "category": r["category"] or "", "basis": r["basis"] or "",
        "tonnes": _num(r["tonnes"]), "grades": _js(r["grades_json"]), "contained": _js(r["contained_json"]),
        "cut_off": r["cut_off"] or "", "context": r["context"] or "", "estimate_type": r["mre_type"] or "",
        "historic": is_historic(r),
        "metal_focus": r["metal_focus"] or "", "headline_oz_au": _num(r["headline_oz_au"]),
        "headline_t_metal": _num(r["headline_t_metal"]), "summary": r["summary"] or "",
        "date": (r["published_at"] or "")[:10], "published_at": r["published_at"] or "",
        "headline": _title(r["raw_headline"] or ""),
        "release_url": release_url(t, r["slug"], r["event_id"]),
        "extractor_version": r["extractor_version"] or "",
    }


def query_rows(conn, p: dict, names: dict, universe: Optional[frozenset]) -> dict:
    where = ["category IS NOT NULL"]
    args: list = []
    t = p.get("ticker")
    if t:
        where.append("(upper(ticker) = ? OR upper(ticker) LIKE ?)")
        args += [t, bare(t) + ".%"]
    if p.get("categories"):
        where.append("category IN (%s)" % ",".join("?" * len(p["categories"])))
        args += p["categories"]
    if p.get("basis"):
        where.append("lower(COALESCE(basis, '')) = ?")
        args.append(p["basis"])
    if p.get("metal"):
        where.append("lower(COALESCE(metal_focus, '')) = ?")
        args.append(p["metal"])
    if p.get("historic") == "exclude":
        where.append("lower(COALESCE(context, '')) <> 'background'")
    elif p.get("historic") == "only":
        where.append("lower(COALESCE(context, '')) = 'background'")
    if p.get("since"):
        where.append("published_at >= ?")
        args.append(p["since"])
    if universe:
        where.append("(CASE WHEN instr(ticker, '.') > 0 THEN upper(substr(ticker, 1, instr(ticker, '.') - 1)) "
                     "ELSE upper(ticker) END) IN (SELECT value FROM json_each(?))")
        args.append(json.dumps(sorted(universe)))
    rows = conn.execute("SELECT " + _COLS + " FROM resource_estimates WHERE " + " AND ".join(where) +
                        " ORDER BY published_at DESC, event_id, ordinal", args).fetchall()
    if p.get("latest"):
        # per company (and per project where the release names one): the newest release that states figures
        keep_event: dict[tuple, str] = {}
        for r in rows:                                        # newest first
            k = (bare(r["ticker"]), (r["project"] or "").strip().lower())
            keep_event.setdefault(k, r["event_id"])
        rows = [r for r in rows if keep_event.get((bare(r["ticker"]), (r["project"] or "").strip().lower())) == r["event_id"]]
    total, limit, page = len(rows), p["limit"], p["page"]
    sel = rows[(page - 1) * limit: page * limit]
    return {
        "ok": True, "api_version": API_VERSION, "total": total, "page": page,
        "pages": max(1, math.ceil(total / limit)) if total else 0, "limit": limit,
        "releases": len({r["event_id"] for r in rows}),
        "filters": {k: p[k] for k in ("ticker", "categories", "basis", "metal", "since") if p.get(k)},
        "historic": p.get("historic", "include"), "latest": bool(p.get("latest")),
        "universe": p["universe"], "universe_applied": bool(universe),
        "items": [to_item(r, names) for r in sel],
    }


def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    @app.get("/api/v1/resources")
    def resources_list(ticker: Optional[str] = None, category: Optional[str] = None, basis: Optional[str] = None,
                       metal: Optional[str] = None, historic: Optional[str] = None, days: Optional[str] = None,
                       latest: Optional[str] = None, page: Optional[str] = None, limit: Optional[str] = None,
                       universe: Optional[str] = None):
        try:
            p = parse_params(ticker, category, basis, metal, historic, days, latest, page, limit, universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = None
        if p["universe"] == "mtp":
            uni = _universe.get() or None
        with closing(_conn()) as conn:
            have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='resource_estimates'").fetchone()
            if not have:
                return JSONResponse({"ok": True, "api_version": API_VERSION, "total": 0, "page": 1, "pages": 0,
                                     "limit": p["limit"], "items": []}, headers=_headers())
            out = query_rows(conn, p, _names.get(), uni)
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
    CREATE TABLE resource_estimates (res_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL DEFAULT 0, ticker TEXT, deposit TEXT, project TEXT, category TEXT, tonnes REAL,
        grades_json TEXT, contained_json TEXT, cut_off TEXT, basis TEXT, context TEXT, source_shape TEXT,
        mre_type TEXT, n_rows INTEGER NOT NULL DEFAULT 1, summary TEXT, metal_focus TEXT, headline_oz_au REAL,
        headline_t_metal REAL, n_categories INTEGER, categories_json TEXT, raw_headline TEXT, published_at TEXT,
        extractor_version TEXT, slug TEXT);
    """)
    seq = {"n": 0}

    def row(eid, t, date, cat, tonnes=None, g=None, c=None, basis="resource", ctx="announced", proj=None, metal="Au",
            mre="Update"):
        seq["n"] += 1
        conn.execute("INSERT INTO resource_estimates (event_id, ordinal, ticker, project, category, tonnes, grades_json, "
                     "contained_json, basis, context, mre_type, metal_focus, raw_headline, published_at, slug) VALUES "
                     "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, seq["n"], t, proj, cat, tonnes, json.dumps(g) if g else None, json.dumps(c) if c else None,
                      basis, ctx, mre, metal, "HEADLINE", date + "T12:00:00Z", "s-" + eid))

    row("a1", "AAA.V", "2026-01-10", "Indicated", 1e6, [{"metal": "Au", "value": 1.2, "unit": "g/t"}],
        [{"metal": "Au", "value": 38000, "unit": "oz"}], proj="North")
    row("a1", "AAA.V", "2026-01-10", "Inferred", 2e6, None, [{"metal": "Au", "value": 50000, "unit": "oz"}], proj="North")
    row("a2", "AAA.V", "2026-06-10", "Indicated", 1.5e6, None, [{"metal": "Au", "value": 60000, "unit": "oz"}], proj="North")
    row("a2", "AAA.V", "2026-06-10", "Inferred", 1e5, None, [{"metal": "Au", "value": 4000, "unit": "oz"}], proj="North",
        ctx="background")
    row("b1", "BBB.TO", "2026-05-01", "Probable", 9e6, None, [{"metal": "Cu", "value": 1e8, "unit": "lb"}], basis="reserve",
        metal="Cu")
    row("m1", "BBB.TO", "2026-05-02", None)                 # marker
    names = {"AAA.V": "Aye Gold Corp."}
    P = lambda **kw: parse_params(today=_dt.date(2026, 9, 28), **kw)

    r = query_rows(conn, P(), names, None)
    ok("every row, markers left out, newest first", r["total"] == 5 and r["items"][0]["event_id"] == "a2"
       and r["releases"] == 3)
    ok("parsed lists and flags", r["items"][0]["contained"][0]["value"] == 60000 and r["items"][1]["historic"] is True
       and r["items"][0]["historic"] is False and r["items"][0]["company"] == "Aye Gold Corp.")
    ok("historic exclude/only", query_rows(conn, P(historic="exclude"), names, None)["total"] == 4
       and query_rows(conn, P(historic="only"), names, None)["total"] == 1)
    ok("category filter", query_rows(conn, P(category="indicated,probable"), names, None)["total"] == 3)
    ok("basis filter", query_rows(conn, P(basis="reserve"), names, None)["total"] == 1)
    ok("metal filter", query_rows(conn, P(metal="cu"), names, None)["total"] == 1)
    ok("ticker bare", query_rows(conn, P(ticker="AAA"), names, None)["total"] == 4)
    ok("latest per company+project", [i["event_id"] for i in query_rows(conn, P(latest="1"), names, None)["items"]]
       == ["a2", "a2", "b1"])
    ok("universe", query_rows(conn, P(universe="mtp"), names, frozenset({"BBB"}))["total"] == 1)
    ok("days", query_rows(conn, P(days="30"), names, None)["total"] == 0 and query_rows(conn, P(days="150"), names, None)["total"] == 3)
    ok("paging", query_rows(conn, P(limit="2", page="3"), names, None)["pages"] == 3)

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad params", bad(category="x") and bad(basis="x") and bad(historic="x") and bad(ticker="A'--")
       and bad(universe="x") and bad(metal="<b>"))
    ok("limit capped", P(limit="99999")["limit"] == MAX_LIMIT)
    print("resources_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        if "/opt/mnt/app" not in sys.path and os.path.isdir("/opt/mnt/app"):
            sys.path.insert(0, "/opt/mnt/app")
        sys.exit(_selftest())
    print(__doc__)
