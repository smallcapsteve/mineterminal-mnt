"""MNT Sampling & Geoscience API v1: read-only JSON for cross-site use (MTP company pages).

MNT_SAMPLING_API_V1 (2026-09-29). Serves what SMP_V1 publishes into `sampling_results`, one item per RELEASE with its
result rows (one per sample type per project: grab / chip / channel / trench rock samples, soil / till / sediment
geochemistry, geophysics by survey method, bulk and brine samples, mapping), newest first. Marker rows (a tagged
release where the reader found no result) are skipped. Anomaly and sample count are stored by the reader but not served
yet (Justin 2026-09-29: early version; those two fields measured under 65%).

  /api/v1/sampling      releases with their results, newest first, filterable

List parameters
  ticker     exact symbol (GT.V) or bare (GT); an exact symbol ignores namesakes on other exchanges
  scope      tagged (default: releases tagged Sampling & Geoscience Results, as /sampling-geoscience shows) | all
  group      rock | geochem | geophysics | bulk_brine | mapping          (filters the result rows)
  type       grab | chip | channel | trench | soil | till | sediment | other_geochem | geophysics | bulk | brine | mapping
  hist       all (default) | new | historical
  days       only releases in the last N days
  page, limit    1-based page, limit 1..200 (default 50) - counted in releases
  universe   all (default) | mtp -> only companies on MTP's list (fails open)

Registered from portal.serve via sampling_api.register(app).
Self-tests: python3 -m portal.sampling_api --selftest   (in-memory; touches nothing live)
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
SCOPES = ("tagged", "all")
HISTS = ("all", "new", "historical")
# the publisher's labels (portal/sampling_publish.py), copied so this module imports nothing from the reader
GROUP = {"grab": "rock", "chip": "rock", "channel": "rock", "trench": "rock", "soil": "geochem", "till": "geochem",
         "sediment": "geochem", "other_geochem": "geochem", "geophysics": "geophysics", "bulk": "bulk_brine",
         "brine": "bulk_brine", "mapping": "mapping"}
TYPE_LABELS = {"grab": "Grab / rock", "chip": "Chip", "channel": "Channel", "trench": "Trench", "soil": "Soil",
               "till": "Till", "sediment": "Stream / lake sediment", "other_geochem": "Other geochemistry",
               "geophysics": "Geophysics", "bulk": "Bulk sample", "brine": "Brine", "mapping": "Mapping / prospecting"}
GROUP_LABELS = {"rock": "Rock samples", "geochem": "Soil, till & sediment", "geophysics": "Geophysics",
                "bulk_brine": "Bulk & brine", "mapping": "Mapping"}
SURVEY_LABELS = {"IP": "IP", "magnetics": "Magnetics", "EM": "EM", "MT": "MT", "gravity": "Gravity",
                 "radiometric": "Radiometric", "lidar": "LiDAR", "hyperspectral": "Hyperspectral", "seismic": "Seismic",
                 "remote_sensing": "Remote sensing", "other": "Other"}
WIDTH_TYPES = ("chip", "channel", "trench")

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")

_COLS = ("sr_id, event_id, ordinal, ticker, slug, sample_type, sample_group, survey_type, project, historical, grade, "
         "grade_unit, grade_metal, width_m, tag_confirmed, raw_headline, published_at, sample_count, anomaly_json, "
         "bulk_tonnes, line_km")


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


def num_text(v) -> str:
    """up to 4 decimals, thousands commas, no trailing zeros (as the /sampling-geoscience page)"""
    if v is None:
        return ""
    s = "{:,.4f}".format(float(v)).rstrip("0").rstrip(".")
    return s or "0"


def grade_text(sample_type, grade, unit, metal, width) -> str:
    if grade is None:
        return ""
    g = "%s %s %s" % (num_text(grade), unit or "", metal or "")
    if width is not None and sample_type in WIDTH_TYPES:
        g += " over %s m" % num_text(width)
    return " ".join(g.split())


# --------------------------------------------------------------------------- params

class BadRequest(ValueError):
    pass


def parse_params(ticker=None, scope=None, group=None, type=None, hist=None, days=None, page=None, limit=None,
                 universe=None, today=None) -> dict:
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
    g = (group or "").strip().lower().replace("-", "_")
    if g:
        if g not in GROUP_LABELS:
            raise BadRequest("group: " + ", ".join(GROUP_LABELS))
        p["group"] = g
    ty = (type or "").strip().lower().replace("-", "_")
    if ty:
        if ty not in TYPE_LABELS:
            raise BadRequest("type: " + ", ".join(TYPE_LABELS))
        p["type"] = ty
    h = (hist or "all").strip().lower()
    if h not in HISTS:
        raise BadRequest("hist: all, new or historical")
    p["hist"] = h
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
    """MNT_FIX8B_API: the sampling reader's counts and sizes (an early reading; the page labels them so)."""
    k = r.keys() if hasattr(r, "keys") else ()
    g = lambda c: r[c] if c in k else None
    n = _fin(g("sample_count"), 1, 200000)
    an = _small_json(g("anomaly_json"))
    if isinstance(an, list):
        an = an[0] if an else None
    if an:
        an = {x: y for x, y in an.items() if not (isinstance(y, float) and y <= 0)} or None
    return {"sample_count": int(n) if n is not None else None, "anomaly": an,
            "bulk_tonnes": _fin(g("bulk_tonnes"), 0.01, 5e6), "line_km": _fin(g("line_km"), 0.01, 1e5)}


def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _result(r) -> dict:
    st = _s(r["sample_type"])
    grp = _s(r["sample_group"]) or GROUP.get(st, "")
    sv = _s(r["survey_type"])
    g, w = _num(r["grade"]), _num(r["width_m"])
    return {"sample_type": st, "type_label": TYPE_LABELS.get(st, st.replace("_", " ").capitalize()),
            "group": grp, "group_label": GROUP_LABELS.get(grp, ""),
            "survey_type": sv, "survey_label": SURVEY_LABELS.get(sv, sv) if st == "geophysics" else "",
            "project": _s(r["project"]), "historical": str(r["historical"]) == "1",
            "grade": g, "grade_unit": _s(r["grade_unit"]), "grade_metal": _s(r["grade_metal"]), "width_m": w,
            "grade_text": grade_text(st, g, _s(r["grade_unit"]), _s(r["grade_metal"]), w), **_early(r)}


def build_releases(rows, names: dict, p: dict) -> list[dict]:
    """rows newest first (published_at DESC, event_id, ordinal) -> releases with their filtered results."""
    by: dict[str, dict] = {}
    order: list[str] = []
    for r in rows:
        if not r["sample_type"]:
            continue                                   # marker row: a tagged release with no result read
        if p["scope"] == "tagged" and str(r["tag_confirmed"]) != "1":
            continue
        x = _result(r)
        if p.get("group") and x["group"] != p["group"]:
            continue
        if p.get("type") and x["sample_type"] != p["type"]:
            continue
        if p["hist"] == "new" and x["historical"]:
            continue
        if p["hist"] == "historical" and not x["historical"]:
            continue
        e = r["event_id"]
        if e not in by:
            t = _s(r["ticker"])
            by[e] = {"event_id": e, "ticker": t, "bare_ticker": bare(t), "company": company_name(t, names),
                     "date": _s(r["published_at"])[:10], "published_at": _s(r["published_at"]),
                     "tagged": str(r["tag_confirmed"]) == "1", "headline": _title(_s(r["raw_headline"])),
                     "release_url": release_url(t, r["slug"], e), "results": []}
            order.append(e)
        by[e]["results"].append(x)
    out = [by[e] for e in order]
    for x in out:
        x["n_results"] = len(x["results"])
    return out


def query_releases(conn, p: dict, names: dict, universe: Optional[frozenset]) -> dict:
    sql = "SELECT " + _COLS + " FROM sampling_results WHERE sample_type IS NOT NULL"
    args: list = []
    t = p.get("ticker")
    if t:
        b = bare(t)
        sql += " AND (UPPER(ticker) = ? OR UPPER(ticker) = ? OR UPPER(ticker) LIKE ?)"
        args += [t, b, b + ".%"]
    if p.get("since"):
        sql += " AND published_at >= ?"
        args.append(p["since"])
    rows = conn.execute(sql + " ORDER BY published_at DESC, event_id, ordinal", args).fetchall()
    if t and "." in t and any(_s(r["ticker"]).upper() == t for r in rows):
        rows = [r for r in rows if _s(r["ticker"]).upper() == t]    # the listing asked for, not a namesake
    rs = build_releases(rows, names, p)
    if universe and not t:
        rs = [x for x in rs if x["bare_ticker"] in universe]
    total, limit, page = len(rs), p["limit"], p["page"]
    return {
        "ok": True, "api_version": API_VERSION, "total": total, "results": sum(x["n_results"] for x in rs),
        "page": page, "pages": max(1, math.ceil(total / limit)) if total else 0, "limit": limit,
        "filters": {k: p[k] for k in ("ticker", "group", "type", "since") if p.get(k)},
        "hist": p["hist"], "scope": p["scope"], "universe": p["universe"], "universe_applied": bool(universe) and not t,
        "items": rs[(page - 1) * limit: page * limit],
    }


# --------------------------------------------------------------------------- web

def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    @app.get("/api/v1/sampling")
    def sampling_list(ticker: Optional[str] = None, scope: Optional[str] = None, group: Optional[str] = None,
                      type: Optional[str] = None, hist: Optional[str] = None, days: Optional[str] = None,
                      page: Optional[str] = None, limit: Optional[str] = None, universe: Optional[str] = None):
        try:
            p = parse_params(ticker, scope, group, type, hist, days, page, limit, universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = None
        if p["universe"] == "mtp":
            uni = _universe.get() or None
        with closing(_conn()) as conn:
            have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='sampling_results'").fetchone()
            if not have:
                return JSONResponse({"ok": True, "api_version": API_VERSION, "total": 0, "results": 0, "page": 1,
                                     "pages": 0, "limit": p["limit"], "scope": p["scope"], "items": []},
                                    headers=_headers())
            out = query_releases(conn, p, _names.get(), uni)
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
    CREATE TABLE sampling_results (sr_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL DEFAULT 0, ticker TEXT, slug TEXT, sample_type TEXT, sample_group TEXT,
        survey_type TEXT, project TEXT, historical INTEGER NOT NULL DEFAULT 0, grade REAL, grade_unit TEXT,
        grade_metal TEXT, width_m REAL, anomaly_json TEXT, sample_count INTEGER, line_km REAL, bulk_tonnes REAL,
        evidence TEXT, date TEXT, n_rows INTEGER NOT NULL DEFAULT 1, tag_confirmed INTEGER NOT NULL DEFAULT 1,
        raw_headline TEXT, published_at TEXT, extractor_version TEXT);
    """)

    def row(eid, t, date, st, proj="Alpha", ordinal=0, grade=None, unit=None, metal=None, width=None, hist=0,
            survey=None, tagged=1):
        conn.execute("INSERT INTO sampling_results (event_id, ordinal, ticker, slug, sample_type, sample_group, "
                     "survey_type, project, historical, grade, grade_unit, grade_metal, width_m, tag_confirmed, "
                     "raw_headline, published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, ordinal, t, "s-" + eid, st, GROUP.get(st) if st else None, survey, proj, hist, grade, unit,
                      metal, width, tagged, "HEADLINE " + eid, date + "T12:00:00Z"))

    row("a1", "ABC.V", "2027-05-10", "channel", grade=1523.54, unit="g/t", metal="Au", width=1.5)
    row("a1", "ABC.V", "2027-05-10", "soil", ordinal=1, grade=0.141, unit="ppm", metal="Au", hist=1)
    row("a2", "ABC.V", "2027-01-02", "geophysics", survey="IP", proj="Beta")
    row("m0", "ABC.V", "2026-12-01", None)                                                 # marker
    row("u1", "ABC.V", "2026-11-01", "grab", tagged=0)                                     # look-alike
    row("t1", "AMQ.V", "2026-09-10", "grab", grade=4.77, unit="g/t", metal="Au")
    row("x1", "ABC.CN", "2026-02-01", "till", proj="Namesake")
    names = {"ABC.V": "ABC Gold Corp.", "AMQ.V": "AMQ Mining Ltd."}
    P = lambda **kw: parse_params(today=_dt.date(2027, 5, 20), **kw)

    r = query_releases(conn, P(), names, None)
    ok("one item per release, tagged only, newest first, markers skipped",
       [x["event_id"] for x in r["items"]] == ["a1", "a2", "t1", "x1"] and r["total"] == 4 and r["results"] == 5)
    a1 = r["items"][0]
    ok("results in release order with labels and grade text",
       [x["sample_type"] for x in a1["results"]] == ["channel", "soil"] and a1["n_results"] == 2
       and a1["results"][0]["grade_text"] == "1,523.54 g/t Au over 1.5 m"
       and a1["results"][1]["grade_text"] == "0.141 ppm Au" and a1["results"][1]["historical"] is True
       and a1["results"][0]["type_label"] == "Channel" and a1["results"][0]["group"] == "rock"
       and a1["company"] == "ABC Gold Corp." and a1["release_url"].endswith("/news/abc.v/s-a1")
       and a1["date"] == "2027-05-10")
    ok("FIX8B early fields present", all(k in a1["results"][0] for k in ("sample_count", "anomaly", "bulk_tonnes")))
    ok("FIX8B early fields bounded", _early({"sample_count": 50000, "anomaly_json": '{"kind":"trend","length_m":90,'
       '"width_m":0,"metal":"Au"}', "bulk_tonnes": -3, "line_km": None}) == {"sample_count": 50000,
       "anomaly": {"kind": "trend", "length_m": 90.0, "metal": "Au"}, "bulk_tonnes": None, "line_km": None})
    ok("geophysics carries its survey label", r["items"][1]["results"][0]["survey_label"] == "IP")
    ok("width only on chip / channel / trench", grade_text("grab", 2.0, "g/t", "Au", 3.0) == "2 g/t Au"
       and grade_text("trench", 0.5, "%", "Cu", 12.0) == "0.5 % Cu over 12 m" and grade_text("soil", None, "", "", 1) == "")
    ok("scope=all adds look-alikes", query_releases(conn, P(scope="all"), names, None)["total"] == 5)
    ok("exact listing wins over a namesake", query_releases(conn, P(ticker="ABC.V"), names, None)["total"] == 2)
    ok("bare ticker matches both", query_releases(conn, P(ticker="ABC"), names, None)["total"] == 3)
    ok("group / type / hist filters",
       query_releases(conn, P(group="geochem"), names, None)["results"] == 2
       and query_releases(conn, P(type="channel"), names, None)["total"] == 1
       and query_releases(conn, P(hist="historical"), names, None)["items"][0]["results"][0]["sample_type"] == "soil"
       and query_releases(conn, P(hist="new", ticker="ABC.V"), names, None)["results"] == 2)
    ok("universe", query_releases(conn, P(universe="mtp"), names, frozenset({"AMQ"}))["total"] == 1)
    ok("days", query_releases(conn, P(days="30"), names, None)["total"] == 1)
    ok("paging", query_releases(conn, P(limit="2", page="2"), names, None)["items"][0]["event_id"] == "t1")

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad params", bad(type="x") and bad(group="x") and bad(hist="x") and bad(ticker="A'--") and bad(universe="x")
       and bad(scope="x") and bad(days="x"))
    print("sampling_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        if "/opt/mnt/app" not in sys.path and os.path.isdir("/opt/mnt/app"):
            sys.path.insert(0, "/opt/mnt/app")
        sys.exit(_selftest())
    print(__doc__)
