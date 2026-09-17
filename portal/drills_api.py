"""MNT Drill Results API v1: read-only JSON for cross-site use (MTP /drilling and company pages).

MNT_DRILLS_API_V1 (2026-09-17). Three endpoints, all GET, CORS-allowed, same visibility as the
/drills page with has=data (approved releases tagged Drill Results that the active DRILL_V1 version
published into drill_results):

  /api/v1/drills                 paged list of releases, filterable and sortable
  /api/v1/drills/metals          metal families with release and interval counts (for filters)
  /api/v1/drills/{event_id}      one release with every interval

List parameters
  ticker     exact symbol (RRI.V) or bare (RRI); also matches releases cross-filed under it
             through events.additional_tickers, like /api/v1/news/by-ticker
  metal      metal family: Au matches Au and AuEq, Cu matches Cu and CuEq. Only releases with a
             fresh (not reported_before) interval of that family. Each item then carries
             metal_best, the release's best interval of that family by value.
  since, until   YYYY-MM-DD on the release date (inclusive)
  days       shorthand for since = today - days
  sort       date (default) | value | grade | length. value/grade/length need metal.
  page, limit    1-based page, limit 1..200 (default 50)
  include    intervals -> every interval of each item
  universe   all (default) | mtp -> only companies on MTP's list
             (/var/lib/mnt-portal/mtp-companies.json). If that list can't be read the filter is
             not applied and the response says universe_applied: false (fail open, like the
             universe gate).

value is grade x length in one unit per metal class: precious metals (Au, Ag, Pt, Pd, Rh) in
g/t x m (gram-metres); everything else in % x m. Intervals already reported by an earlier release
are listed but never rank. value is null, and the interval never ranks, when the grade can't be
real: a precious metal in % (GOLD.TO "100% AuEq", SIG.V "0.115% Au" over 128 m, AXO.V Pt in %; all
reader errors) or any grade above 100%, or a unit outside the conversion table.

Speed: every query drives from drill_results (2.7k rows) into events by primary key (CROSS JOIN
fixes the order). Left to the planner, SQLite scanned the 44k approved events first: 0.58 s vs
0.09 s for the same count on the server, 2026-09-17.

Registered from portal.app via drills_api.register(app). Depends only on sqlite3, the tickers file
and portal.text_helpers.smart_title.

Self-tests: python3 -m portal.drills_api --selftest   (in-memory; touches nothing live)
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
TAG = "Drill Results"
API_VERSION = "1"
MAX_LIMIT = 200
DEFAULT_LIMIT = 50
SORTS = ("date", "value", "grade", "length")

PRECIOUS = {"AU", "AG", "PT", "PD", "RH"}
# Unit -> multiplier to ppm (g/t). Same table as portal.drill_publish.TO_PPM.
TO_PPM = {"g/t": 1.0, "ppm": 1.0, "ppb": 0.001, "%": 10000.0, "oz/t": 34.2857, "opt": 34.2857,
          "kg/t": 1000.0, "gms": 1.0}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")
_METAL_RE = re.compile(r"^[A-Za-z0-9+]{1,24}$")
_EVENT_RE = re.compile(r"^[A-Za-z0-9_\-]{6,80}$")


# --------------------------------------------------------------------------- helpers (pure)

def family(metal: Optional[str]) -> str:
    """Au, AuEq -> AU; Zn+Pb stays ZN+PB. Unlike portal.drill_publish.family (which picks a
    fallback best interval), a combined grade is its own family here: ranking 'Pt+Pd+Au' as
    platinum would put a three-metal total above single-metal grades."""
    parts = []
    for m in (metal or "").strip().split("+"):
        m = m.strip()
        if m[-2:].lower() == "eq":
            m = m[:-2]
        if m:
            parts.append(m.upper())
    return "+".join(parts)


def is_precious(metal: Optional[str]) -> bool:
    fam = family(metal)
    return bool(fam) and all(x in PRECIOUS for x in fam.split("+"))


def value_unit(metal: Optional[str]) -> str:
    return "g/t*m" if is_precious(metal) else "%*m"


def unit_factor(unit: Optional[str], metal: Optional[str]) -> Optional[float]:
    """Multiplier from the interval's unit to the metal class's display unit (g/t or %).
    None for a unit outside the table, and for a precious metal reported in % (never real here)."""
    u = (unit or "").strip()
    ppm = TO_PPM.get(u)
    if ppm is None:
        return None
    if is_precious(metal):
        return None if u == "%" else ppm
    return ppm / 10000.0


def interval_value(grade, unit, metal, length_m) -> Optional[float]:
    f = unit_factor(unit, metal)
    if f is None or grade is None or length_m is None:
        return None
    if (unit or "").strip() == "%" and float(grade) > 100:
        return None
    v = float(grade) * f * float(length_m)
    return round(v, 6) if math.isfinite(v) else None


def bare(ticker: Optional[str]) -> str:
    return (ticker or "").strip().upper().split(".")[0]


def _factor_sql(unit_col: str, grade_col: str, metal_is_precious: bool) -> str:
    """SQL CASE mirroring unit_factor() plus interval_value()'s >100% rule, metal class known up front."""
    if metal_is_precious:
        parts = " ".join("WHEN '%s' THEN %r" % (u, f) for u, f in TO_PPM.items() if u != "%")
        return "(CASE %s %s ELSE NULL END)" % (unit_col, parts)
    parts = " ".join("WHEN '%s' THEN %r" % (u, f / 10000.0) for u, f in TO_PPM.items() if u != "%")
    return "(CASE %s WHEN '%%' THEN (CASE WHEN %s > 100 THEN NULL ELSE 1.0 END) %s ELSE NULL END)" % (
        unit_col, grade_col, parts)


class BadRequest(ValueError):
    pass


def parse_params(ticker=None, metal=None, since=None, until=None, days=None, sort=None,
                 page=None, limit=None, include=None, universe=None, today=None) -> dict:
    p: dict[str, Any] = {}
    t = (ticker or "").strip()
    if t:
        if not _TICKER_RE.match(t):
            raise BadRequest("ticker: letters, digits, '.' or '-' only")
        p["ticker"] = t.upper()
    m = re.sub(r"\s+", "+", (metal or "").strip())   # a '+' in a query string arrives as a space
    if m:
        if not _METAL_RE.match(m):
            raise BadRequest("metal: letters, digits and '+' only, e.g. Au, Cu, Zn+Pb")
        p["metal"] = family(m)
    for k, v in (("since", since), ("until", until)):
        v = (v or "").strip()
        if v:
            if not _DATE_RE.match(v):
                raise BadRequest(k + ": YYYY-MM-DD")
            p[k] = v
    if days not in (None, "", 0, "0"):
        try:
            d = int(days)
        except (TypeError, ValueError):
            raise BadRequest("days: a whole number")
        if d < 0 or d > 36500:
            raise BadRequest("days: 0..36500")
        if d:
            base = today or _dt.datetime.utcnow().date()
            cut = (base - _dt.timedelta(days=d)).isoformat()
            p["since"] = max(p.get("since", ""), cut)
    s = (sort or "date").strip().lower()
    if s not in SORTS:
        raise BadRequest("sort: one of " + ", ".join(SORTS))
    if s != "date" and "metal" not in p:
        raise BadRequest("sort=%s needs metal (grades of different metals don't compare)" % s)
    p["sort"] = s
    try:
        p["page"] = max(1, int(page or 1))
        lim = int(limit or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        raise BadRequest("page and limit: whole numbers")
    p["limit"] = max(1, min(lim, MAX_LIMIT))
    inc = {x.strip().lower() for x in (include or "").split(",") if x.strip()}
    if inc - {"intervals"}:
        raise BadRequest("include: intervals")
    p["intervals"] = "intervals" in inc
    u = (universe or "all").strip().lower()
    if u not in ("all", "mtp"):
        raise BadRequest("universe: all or mtp")
    p["universe"] = u
    return p


# --------------------------------------------------------------------------- cached side data

class _FileCache:
    """Re-read a JSON file when its mtime changes, at most every `ttl` seconds."""

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
        return ""  # auto-discovered stub name ("Txg" for TXG.TO)
    return nm


# --------------------------------------------------------------------------- queries

_VISIBLE = (
    "e.review_status = 'auto_approved' "
    "AND ('|' || COALESCE(e.categories, '') || '|') LIKE '%|" + TAG + "|%'"
)

_ITEM_COLS = (
    "d.event_id, d.ticker, d.project, d.top_hole_id, d.top_grade, d.top_unit, d.top_metal, "
    "d.top_length_m, d.top_summary, d.n_intercepts, d.sample_type, d.extractor_version, "
    "COALESCE(d.published_at, e.published_at, e.classified_at) AS published_at, "
    "COALESCE(e.raw_headline, d.raw_headline) AS headline, e.slug, e.source_url, e.source_name, "
    "e.additional_tickers"
)

_IV_COLS = ("event_id, seq, hole_id, from_m, to_m, length_m, grade, unit, metal, summary, including, "
            "is_best, reported_before")


def _metals_in_family(conn, fam: str) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT metal FROM drill_intervals WHERE metal IS NOT NULL")
            if family(r[0]) == fam]


def _where(p: dict, universe: Optional[frozenset]) -> tuple[list[str], list]:
    where, args = [_VISIBLE], []
    t = p.get("ticker")
    if t:
        b = bare(t)
        where.append(
            "(upper(d.ticker) = ? OR upper(d.ticker) LIKE ? "
            " OR ('|' || upper(COALESCE(e.additional_tickers, '')) || '|') LIKE ? "
            " OR ('|' || upper(COALESCE(e.additional_tickers, '')) || '|') LIKE ?)")
        args += [t, b + ".%", "%|" + t + "|%", "%|" + b + ".%|%"]
    if p.get("since"):
        where.append("substr(COALESCE(d.published_at, e.published_at, e.classified_at), 1, 10) >= ?")
        args.append(p["since"])
    if p.get("until"):
        where.append("substr(COALESCE(d.published_at, e.published_at, e.classified_at), 1, 10) <= ?")
        args.append(p["until"])
    if universe:
        where.append(
            "(CASE WHEN instr(d.ticker, '.') > 0 THEN upper(substr(d.ticker, 1, instr(d.ticker, '.') - 1)) "
            "ELSE upper(d.ticker) END) IN (SELECT value FROM json_each(?))")
        args.append(json.dumps(sorted(universe)))
    return where, args


def _interval_dict(r) -> dict:
    return {
        "seq": r["seq"],
        "hole_id": r["hole_id"],
        "from_m": r["from_m"],
        "to_m": r["to_m"],
        "length_m": r["length_m"],
        "grade": r["grade"],
        "unit": r["unit"],
        "metal": r["metal"],
        "summary": r["summary"] or "",
        "including": bool(r["including"]),
        "is_best": bool(r["is_best"]),
        "reported_before": bool(r["reported_before"]),
        "value": interval_value(r["grade"], r["unit"], r["metal"], r["length_m"]),
        "value_unit": value_unit(r["metal"]),
    }


def _item_dict(r, names: dict, universe: Optional[frozenset]) -> dict:
    from portal.text_helpers import smart_title
    t = (r["ticker"] or "").strip()
    slug = (r["slug"] or "").strip()
    pub = r["published_at"] or ""
    extra = [x for x in (r["additional_tickers"] or "").strip("|").split("|") if x]
    best = None
    if r["top_grade"] is not None or r["top_summary"]:
        best = {
            "hole_id": r["top_hole_id"],
            "length_m": r["top_length_m"],
            "grade": r["top_grade"],
            "unit": r["top_unit"],
            "metal": r["top_metal"],
            "summary": r["top_summary"] or "",
            "value": interval_value(r["top_grade"], r["top_unit"], r["top_metal"], r["top_length_m"]),
            "value_unit": value_unit(r["top_metal"]),
        }
    return {
        "event_id": r["event_id"],
        "ticker": t,
        "bare_ticker": bare(t),
        "additional_tickers": extra,
        "company": company_name(t, names),
        "headline": smart_title(r["headline"] or "") if r["headline"] else "",
        "published_at": pub,
        "date": pub[:10],
        "project": r["project"] or "",
        "sample_type": r["sample_type"] or "",
        "extractor_version": r["extractor_version"] or "",
        "n_intercepts": r["n_intercepts"],
        "best": best,
        "release_url": (f"{SITE_BASE}/news/{t.lower()}/{slug}" if t and slug
                        else f"{SITE_BASE}/event/{r['event_id']}"),
        "source_url": r["source_url"] or "",
        "source_name": r["source_name"] or "",
    }


def _attach_intervals(conn, items: list[dict], want_all: bool, fam: Optional[str]) -> None:
    ids = [it["event_id"] for it in items]
    if not ids or not (want_all or fam):
        return
    by: dict[str, list] = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for r in conn.execute("SELECT %s FROM drill_intervals WHERE event_id IN (%s) ORDER BY event_id, seq"
                              % (_IV_COLS, ",".join("?" * len(chunk))), chunk):
            by.setdefault(r["event_id"], []).append(_interval_dict(r))
    for it in items:
        ivs = by.get(it["event_id"], [])
        if want_all:
            it["intervals"] = ivs
        if fam:
            cands = [iv for iv in ivs if family(iv["metal"]) == fam and not iv["reported_before"]
                     and iv["value"] is not None]
            it["metal_best"] = max(cands, key=lambda iv: (iv["value"], iv["length_m"] or 0, -iv["seq"])) \
                if cands else None


def query_list(conn, p: dict, names: dict, universe: Optional[frozenset]) -> dict:
    where, args = _where(p, universe)
    join, order, jargs = "", "published_at DESC, d.event_id DESC", []
    fam = p.get("metal")
    if fam:
        metals = _metals_in_family(conn, fam)
        prec = is_precious(fam)
        f = _factor_sql("unit", "grade", prec)
        join = (
            " JOIN (SELECT event_id, MAX(grade * %s * length_m) AS v, MAX(grade * %s) AS g, MAX(length_m) AS l "
            "       FROM drill_intervals "
            "       WHERE reported_before = 0 AND grade IS NOT NULL AND length_m IS NOT NULL "
            "         AND metal IN (SELECT value FROM json_each(?)) AND %s IS NOT NULL "
            "       GROUP BY event_id) m ON m.event_id = d.event_id " % (f, f, f))
        jargs = [json.dumps(metals)]
        col = {"value": "m.v", "grade": "m.g", "length": "m.l"}.get(p["sort"])
        if col:
            order = col + " DESC, published_at DESC, d.event_id DESC"
    base = ("FROM drill_results d CROSS JOIN events e ON e.event_id = d.event_id" + join +
            " WHERE " + " AND ".join(where))
    total = conn.execute("SELECT COUNT(*) " + base, jargs + args).fetchone()[0]
    limit, page = p["limit"], p["page"]
    rows = conn.execute("SELECT " + _ITEM_COLS + " " + base + " ORDER BY " + order + " LIMIT ? OFFSET ?",
                        jargs + args + [limit, (page - 1) * limit]).fetchall()
    items = [_item_dict(r, names, universe) for r in rows]
    _attach_intervals(conn, items, p["intervals"], fam)
    return {
        "ok": True,
        "api_version": API_VERSION,
        "total": total,
        "page": page,
        "pages": max(1, math.ceil(total / limit)) if total else 0,
        "limit": limit,
        "sort": p["sort"],
        "filters": {k: p[k] for k in ("ticker", "metal", "since", "until") if p.get(k)},
        "universe": p["universe"],
        "universe_applied": bool(universe),
        "value_unit": value_unit(fam) if fam else None,
        "items": items,
    }


def query_one(conn, event_id: str, names: dict) -> Optional[dict]:
    r = conn.execute("SELECT " + _ITEM_COLS + " FROM drill_results d CROSS JOIN events e ON e.event_id = d.event_id "
                     "WHERE d.event_id = ? AND " + _VISIBLE, (event_id,)).fetchone()
    if not r:
        return None
    it = _item_dict(r, names, None)
    _attach_intervals(conn, [it], True, None)
    return it


def query_metals(conn, universe: Optional[frozenset]) -> list[dict]:
    """Metal families with fresh intervals: one pass over (metal, release) pairs, grouped here."""
    where, args = _where({}, universe)
    rows = conn.execute(
        "SELECT i.metal, i.event_id, COUNT(*) AS n "
        "FROM drill_results d CROSS JOIN events e ON e.event_id = d.event_id "
        "JOIN drill_intervals i ON i.event_id = d.event_id "
        "WHERE i.reported_before = 0 AND i.metal IS NOT NULL AND " + " AND ".join(where) +
        " GROUP BY i.metal, i.event_id", args).fetchall()
    agg: dict[str, dict] = {}
    for r in rows:
        fam = family(r["metal"])
        if not fam:
            continue
        a = agg.setdefault(fam, {"members": set(), "events": set(), "intervals": 0})
        a["members"].add(r["metal"])
        a["events"].add(r["event_id"])
        a["intervals"] += r["n"]
    out = []
    for fam, a in agg.items():
        members = sorted(a["members"])
        # Display name: the member spelled like the family (Au for AU/AuEq), else the first member minus Eq.
        name = next((m for m in members if m.upper() == fam),
                    "+".join(x[:-2] if x.endswith("Eq") else x for x in members[0].split("+")))
        out.append({"metal": name, "family": fam, "members": members, "releases": len(a["events"]),
                    "intervals": a["intervals"], "value_unit": value_unit(fam)})
    return sorted(out, key=lambda x: (-x["releases"], x["metal"]))


# --------------------------------------------------------------------------- web

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


def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    def _universe_for(u: str) -> Optional[frozenset]:
        if u != "mtp":
            return None
        s = _universe.get()
        return s or None

    # Registered before /{event_id} so "metals" is never read as an event id.
    @app.get("/api/v1/drills/metals")
    def drills_metals(universe: str = "all"):
        try:
            p = parse_params(universe=universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = _universe_for(p["universe"])
        with closing(_conn()) as conn:
            data = query_metals(conn, uni)
        return JSONResponse({"ok": True, "api_version": API_VERSION, "universe": p["universe"],
                             "universe_applied": bool(uni), "metals": data}, headers=_headers())

    @app.get("/api/v1/drills/{event_id}")
    def drills_one(event_id: str):
        if not _EVENT_RE.match(event_id or ""):
            return _err("event_id: 6-80 letters, digits, '-' or '_'", 400)
        with closing(_conn()) as conn:
            it = query_one(conn, event_id, _names.get())
        if not it:
            return _err("not_found", 404)
        return JSONResponse({"ok": True, "api_version": API_VERSION, "item": it}, headers=_headers())

    @app.get("/api/v1/drills")
    def drills_list(ticker: Optional[str] = None, metal: Optional[str] = None, since: Optional[str] = None,
                    until: Optional[str] = None, days: Optional[str] = None, sort: Optional[str] = None,
                    page: Optional[str] = None, limit: Optional[str] = None, include: Optional[str] = None,
                    universe: Optional[str] = None):
        try:
            p = parse_params(ticker, metal, since, until, days, sort, page, limit, include, universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = _universe_for(p["universe"])
        with closing(_conn()) as conn:
            out = query_list(conn, p, _names.get(), uni)
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
    CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, slug TEXT, raw_headline TEXT, published_at TEXT,
        classified_at TEXT, source_url TEXT, source_name TEXT, additional_tickers TEXT, categories TEXT,
        review_status TEXT);
    CREATE TABLE drill_results (drill_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
        ticker TEXT, project TEXT, top_hole_id TEXT, top_grade REAL, top_unit TEXT, top_metal TEXT,
        top_length_m REAL, top_summary TEXT, n_intercepts INTEGER, raw_headline TEXT, published_at TEXT,
        sample_type TEXT, extractor_version TEXT);
    CREATE TABLE drill_intervals (event_id TEXT NOT NULL, seq INTEGER NOT NULL, hole_id TEXT, from_m REAL,
        to_m REAL, length_m REAL, grade REAL, unit TEXT, metal TEXT, summary TEXT,
        including INTEGER NOT NULL DEFAULT 0, is_best INTEGER NOT NULL DEFAULT 0,
        reported_before INTEGER NOT NULL DEFAULT 0, src TEXT, PRIMARY KEY (event_id, seq)) WITHOUT ROWID;
    """)

    def ev(eid, t, date, cats="Drill Results", status="auto_approved", extra=None, slug="s"):
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, t, slug, "ACME INTERSECTS GOLD", date + "T12:00:00", None, "https://w/x", "Wire",
                      extra, cats, status))

    def dr(eid, t, date, g, u, m, l, hole="H1", project="P"):
        conn.execute("INSERT INTO drill_results(event_id,ticker,project,top_hole_id,top_grade,top_unit,top_metal,"
                     "top_length_m,top_summary,n_intercepts,raw_headline,published_at,sample_type,extractor_version)"
                     " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, t, project, hole, g, u, m, l, "summary", 2, "h", date + "T12:00:00", "drill", "1.0.1"))

    def iv(eid, seq, g, u, m, l, rb=0, best=0, incl=0, hole="H1"):
        conn.execute("INSERT INTO drill_intervals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, seq, hole, None, None, l, g, u, m, "s", incl, best, rb, "body"))

    # e1 AAA.V gold 2026-09-01: 10 m @ 2 g/t (20 gm), incl 1 m @ 15 g/t (15 gm)
    ev("e1aaaa", "AAA.V", "2026-09-01"); dr("e1aaaa", "AAA.V", "2026-09-01", 2.0, "g/t", "Au", 10)
    iv("e1aaaa", 1, 2.0, "g/t", "Au", 10, best=1); iv("e1aaaa", 2, 15.0, "g/t", "Au", 1, incl=1)
    # e2 BBB.CN copper 2026-08-01: 100 m @ 0.5% Cu (50 %m); also Au 0.2 g/t over 100 m (20 gm) reported before
    ev("e2bbbb", "BBB.CN", "2026-08-01"); dr("e2bbbb", "BBB.CN", "2026-08-01", 0.5, "%", "Cu", 100)
    iv("e2bbbb", 1, 0.5, "%", "Cu", 100, best=1); iv("e2bbbb", 2, 0.2, "g/t", "Au", 100, rb=1)
    iv("e2bbbb", 3, 3.0, "g/t", "Pt+Pd+Au", 10)
    # e3 CCC.TO AuEq 2025-01-10: 5 m @ 30 g/t AuEq (150 gm); cross-filed under AAA.V
    ev("e3cccc", "CCC.TO", "2025-01-10", extra="|AAA.V|"); dr("e3cccc", "CCC.TO", "2025-01-10", 30, "g/t", "AuEq", 5)
    iv("e3cccc", 1, 30, "g/t", "AuEq", 5, best=1)
    # e4 DDD.V Au in ppb 2026-02-01: 20 m @ 500 ppb = 0.5 g/t (10 gm)
    ev("e4dddd", "DDD.V", "2026-02-01", slug=""); dr("e4dddd", "DDD.V", "2026-02-01", 500, "ppb", "Au", 20)
    iv("e4dddd", 1, 500, "ppb", "Au", 20, best=1)
    # hidden: pending review; untagged
    ev("e5eeee", "AAA.V", "2026-09-02", status="pending_review"); dr("e5eeee", "AAA.V", "2026-09-02", 9, "g/t", "Au", 9)
    iv("e5eeee", 1, 9, "g/t", "Au", 9)
    ev("e6ffff", "AAA.V", "2026-09-03", cats="Financings"); dr("e6ffff", "AAA.V", "2026-09-03", 9, "g/t", "Au", 9)
    # substring tag must not match
    ev("e7gggg", "AAA.V", "2026-09-04", cats="Drill Results Pending"); dr("e7gggg", "AAA.V", "2026-09-04", 1, "g/t", "Au", 1)
    # odd unit never ranks
    ev("e8hhhh", "EEE.V", "2026-03-01"); dr("e8hhhh", "EEE.V", "2026-03-01", 99, "g\n/t", "Au", 99)
    iv("e8hhhh", 1, 99, "g\n/t", "Au", 99, best=1)
    iv("e8hhhh", 2, 0.115, "%", "Au", 128)
    iv("e8hhhh", 3, 350.0, "%", "Cu", 57)

    names = {"AAA.V": "Acme Gold Corp.", "BBB.CN": "Bbb", "CCC.TO": "Cee Metals"}
    P = lambda **kw: parse_params(**kw)

    ok("family AuEq -> AU", family("AuEq") == "AU")
    ok("family combos kept", family("Pt+Pd+Au") == "PT+PD+AU" and family("ZnEq+Pb") == "ZN+PB")
    ok("precious combos", is_precious("Pt+Pd+Au") and not is_precious("Zn+Pb") and not is_precious(""))
    ok("oxide is its own family", family("Li2O") == "LI2O")
    ok("value g/t", interval_value(2, "g/t", "Au", 10) == 20)
    ok("value ppb -> g/t", interval_value(500, "ppb", "Au", 20) == 10)
    ok("value % Cu", interval_value(0.5, "%", "Cu", 100) == 50)
    ok("value ppm Cu -> %", interval_value(5000, "ppm", "Cu", 10) == 5)
    ok("value unknown unit", interval_value(1, "g\n/t", "Au", 1) is None)
    ok("precious in % never ranks", interval_value(0.115, "%", "Au", 128) is None and interval_value(100, "%", "AuEq", 1) is None)
    ok("grade over 100% never ranks", interval_value(101, "%", "Zn", 1) is None and interval_value(100, "%", "Zn", 1) == 100)
    ok("value_unit", value_unit("AgEq") == "g/t*m" and value_unit("Zn") == "%*m")

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True

    ok("sort=value needs metal", bad(sort="value"))
    ok("bad sort", bad(sort="drop table"))
    ok("bad date", bad(since="2026/01/01"))
    ok("bad ticker", bad(ticker="AAA'; --"))
    ok("bad include", bad(include="body"))
    ok("bad universe", bad(universe="x"))
    ok("limit capped", P(limit="5000")["limit"] == MAX_LIMIT)
    ok("page floor", P(page="-3")["page"] == 1)
    ok("days -> since", P(days="10", today=_dt.date(2026, 9, 17))["since"] == "2026-09-07")
    ok("metal case", P(metal="au")["metal"] == "AU" and P(metal="AUEQ")["metal"] == "AU")
    ok("metal + from query string", P(metal="Zn Pb")["metal"] == "ZN+PB")

    r = query_list(conn, P(), names, None)
    ids = [i["event_id"] for i in r["items"]]
    ok("visible only (approved, exact tag)", ids == ["e1aaaa", "e2bbbb", "e8hhhh", "e4dddd", "e3cccc"])
    ok("total", r["total"] == 5 and r["pages"] == 1)
    it = r["items"][0]
    ok("item fields", it["ticker"] == "AAA.V" and it["bare_ticker"] == "AAA" and it["company"] == "Acme Gold Corp."
       and it["date"] == "2026-09-01" and it["best"]["value"] == 20 and it["best"]["value_unit"] == "g/t*m")
    ok("headline smart-titled", it["headline"].startswith("Acme Intersects"))
    ok("release url", it["release_url"] == SITE_BASE + "/news/aaa.v/s")
    ok("release url without slug", r["items"][3]["release_url"] == SITE_BASE + "/event/e4dddd")
    ok("stub company name dropped", r["items"][1]["company"] == "")
    ok("no intervals unless asked", "intervals" not in it and "metal_best" not in it)

    r = query_list(conn, P(limit="2", page="2"), names, None)
    ok("paging", [i["event_id"] for i in r["items"]] == ["e8hhhh", "e4dddd"] and r["pages"] == 3)

    r = query_list(conn, P(ticker="AAA"), names, None)
    ok("bare ticker + cross-filed", [i["event_id"] for i in r["items"]] == ["e1aaaa", "e3cccc"])
    r = query_list(conn, P(ticker="aaa.v"), names, None)
    ok("full ticker + cross-filed", [i["event_id"] for i in r["items"]] == ["e1aaaa", "e3cccc"])
    ok("cross-filed listed", r["items"][1]["additional_tickers"] == ["AAA.V"])

    r = query_list(conn, P(since="2026-01-01", until="2026-08-31"), names, None)
    ok("date window", [i["event_id"] for i in r["items"]] == ["e2bbbb", "e8hhhh", "e4dddd"])

    r = query_list(conn, P(metal="Au", sort="value"), names, None)
    ok("gold rank: AuEq in family, ppb converted, reported-before and odd unit excluded",
       [i["event_id"] for i in r["items"]] == ["e3cccc", "e1aaaa", "e4dddd"])
    ok("metal_best picks value, not grade", r["items"][1]["metal_best"]["seq"] == 1
       and r["items"][1]["metal_best"]["value"] == 20)
    ok("value_unit top-level", r["value_unit"] == "g/t*m")
    r = query_list(conn, P(metal="Au", sort="grade"), names, None)
    ok("grade rank", [i["event_id"] for i in r["items"]][:2] == ["e3cccc", "e1aaaa"])
    r = query_list(conn, P(metal="Au", sort="length"), names, None)
    ok("length rank", [i["event_id"] for i in r["items"]][0] == "e4dddd")
    r = query_list(conn, P(metal="Cu", sort="value"), names, None)
    ok("copper rank (over-100% excluded)", [i["event_id"] for i in r["items"]] == ["e2bbbb"] and r["value_unit"] == "%*m")
    r = query_list(conn, P(metal="Au"), names, None)
    ok("metal filter, date order", [i["event_id"] for i in r["items"]] == ["e1aaaa", "e4dddd", "e3cccc"])
    r = query_list(conn, P(metal="Li"), names, None)
    ok("metal with no data", r["total"] == 0 and r["items"] == [] and r["pages"] == 0)

    r = query_list(conn, P(include="intervals"), names, None)
    ivs = r["items"][0]["intervals"]
    ok("intervals attached", len(ivs) == 2 and ivs[1]["including"] is True and ivs[0]["is_best"] is True
       and ivs[1]["value"] == 15)
    ok("reported_before flagged", r["items"][1]["intervals"][1]["reported_before"] is True)

    uni = frozenset({"AAA", "CCC"})
    r = query_list(conn, P(universe="mtp"), names, uni)
    ok("universe filter", [i["event_id"] for i in r["items"]] == ["e1aaaa", "e3cccc"] and r["universe_applied"])
    r = query_list(conn, P(universe="mtp"), names, None)
    ok("universe fail-open", r["total"] == 5 and r["universe_applied"] is False)

    one = query_one(conn, "e2bbbb", names)
    ok("one release", one and len(one["intervals"]) == 3 and one["best"]["metal"] == "Cu")
    ok("one hidden -> None", query_one(conn, "e5eeee", names) is None and query_one(conn, "nope00", names) is None)

    ms = {m["metal"]: m for m in query_metals(conn, None)}
    ok("metals families", set(ms) == {"Au", "Cu", "Pt+Pd+Au"} and ms["Au"]["releases"] == 4
       and ms["Au"]["members"] == ["Au", "AuEq"] and ms["Cu"]["releases"] == 2 and ms["Pt+Pd+Au"]["value_unit"] == "g/t*m")
    r = query_list(conn, P(metal="Pt+Pd+Au", sort="value"), names, None)
    ok("combo rank", [i["event_id"] for i in r["items"]] == ["e2bbbb"] and r["items"][0]["metal_best"]["value"] == 30)
    ms = {m["metal"]: m for m in query_metals(conn, frozenset({"BBB"}))}
    ok("metals universe", set(ms) == {"Cu", "Pt+Pd+Au"})

    ok("universe parse", _parse_universe({"tickers": ["aaa", "BBB.V"]}) == frozenset({"AAA", "BBB"})
       and _parse_universe(None) == frozenset())
    ok("names parse prev tickers", _parse_names([{"ticker": "N.V", "name": "New",
                                                  "previous_tickers": [{"ticker": "O.V"}]}]) == {"N.V": "New", "O.V": "New"})

    # SQL factor agrees with the Python value for every unit in the table, plus the implausible cases
    for u in list(TO_PPM) + ["g\n/t"]:
        for m in ("Au", "Cu"):
            for g in (2.0, 150.0):
                lit = "'%s'" % u
                sqlv = conn.execute("SELECT %r * %s * 3.0" % (g, _factor_sql(lit, repr(g), is_precious(m)))).fetchone()[0]
                py = interval_value(g, u, m, 3.0)
                ok("sql factor %s %s %g" % (u.replace("\n", "\\n"), m, g),
                   (sqlv is None and py is None) or (sqlv is not None and py is not None and abs(sqlv - py) < 1e-5))

    print("drills_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        if "/opt/mnt/app" not in sys.path and os.path.isdir("/opt/mnt/app"):
            sys.path.insert(0, "/opt/mnt/app")
        sys.exit(_selftest())
    print(__doc__)
