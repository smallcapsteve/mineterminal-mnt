"""MNT Exploration Programs API v1: read-only JSON for cross-site use (MTP company pages).

MNT_EXPLORATION_API_V1 (2026-09-22). Serves what EXPL_V1 publishes into `exploration_programs`, one item per
PROGRAM: a drill program announced, started and completed across three releases is one item (the publisher's
program_key), shown from its latest release with the number of releases and the date it was first reported.
Facts the latest release leaves out (project, drill method, target metal...) come from the earlier releases;
sizes carried over that way (metres, holes, line-km, budget, rigs) are named in `filled`, because a planned
15,000 m is not 15,000 m drilled. Marker rows (a release with no program) are skipped.

  /api/v1/exploration    programs, newest first, filterable

List parameters
  ticker     exact symbol (TXG.TO) or bare (TXG); an exact symbol ignores namesakes on other exchanges
  type       drilling | geophysics | ground
  status     planned | started | underway | completed   (of the latest release)
  work       all (default) | own | historical   (historical = a previous owner's work, with operator)
  days       only programs whose latest release is in the last N days
  page, limit    1-based page, limit 1..200 (default 50) - counted in programs
  universe   all (default) | mtp -> only companies on MTP's list (fails open)

Registered from portal.serve via exploration_api.register(app).
Self-tests: python3 -m portal.exploration_api --selftest   (in-memory; touches nothing live)
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
TYPES = ("drilling", "geophysics", "ground")
STATUSES = ("planned", "started", "underway", "completed")
TYPE_LABELS = {"drilling": "Drilling", "geophysics": "Geophysics", "ground": "Ground work"}
STATUS_LABELS = {"planned": "Planned", "started": "Started", "underway": "Underway", "completed": "Completed"}

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")

_COLS = ("ep_id, event_id, ordinal, ticker, slug, program_type, project, status, metres, holes, line_km, season, "
         "phase, historical, operator, drill_method, survey_type, budget, currency, target_metal, contractor, rigs, "
         "program_key, raw_headline, published_at")


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


def parse_params(ticker=None, type=None, status=None, work=None, days=None, page=None, limit=None, universe=None,
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
            raise BadRequest("type: drilling, geophysics or ground")
        p["type"] = ty
    stt = (status or "").strip().lower()
    if stt:
        if stt not in STATUSES:
            raise BadRequest("status: planned, started, underway or completed")
        p["status"] = stt
    w = (work or "all").strip().lower()
    if w not in ("all", "own", "historical"):
        raise BadRequest("work: own, historical or all")
    p["work"] = w
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


def _int(v):
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


# Descriptive facts carry over from earlier releases of the same program when the latest one leaves them out.
_DESC = ("project", "season", "phase", "operator", "drill_method", "survey_type", "target_metal", "contractor")
# Sizes carry over too, but are flagged in `filled`: a planned 15,000 m is not the same fact as 15,000 m drilled.
_SIZE = ("metres", "holes", "line_km", "budget", "rigs")


def build_programs(rows, names: dict) -> list[dict]:
    """rows in (published_at, event_id, ordinal) order -> programs, newest first."""
    groups: dict[str, list] = {}
    order: list[str] = []
    for r in rows:
        if not r["program_type"]:
            continue
        k = r["program_key"] or ("row:%s" % r["ep_id"])
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(r)
    out = []
    for k in order:
        rs = groups[k]                          # chronological
        last = rs[-1]
        d = {f: last[f] for f in _DESC + _SIZE}
        cur = last["currency"]
        filled = []
        for r in reversed(rs[:-1]):
            for f in _DESC + _SIZE:
                if d.get(f) in (None, "") and r[f] not in (None, ""):
                    d[f] = r[f]
                    if f in _SIZE:
                        filled.append(f)
                    if f == "budget":
                        cur = r["currency"]
        t = (last["ticker"] or "").strip()
        releases, history, seen = [], [], set()
        for r in rs:
            if r["event_id"] in seen:
                continue
            seen.add(r["event_id"])
            releases.append({"date": (r["published_at"] or "")[:10], "status": r["status"] or "",
                             # MNT_FIX8B_API: the size this release gave, so a page can show a program growing
                             "metres": _num(r["metres"]), "holes": _int(r["holes"]), "line_km": _num(r["line_km"]),
                             "budget": _num(r["budget"]), "currency": (r["currency"] or "") if r["budget"] is not None else "",
                             "headline": _title(r["raw_headline"] or ""),
                             "release_url": release_url(r["ticker"], r["slug"], r["event_id"])})
        out.append({
            "program_id": last["ep_id"], "ticker": t, "bare_ticker": bare(t), "company": company_name(t, names),
            "type": last["program_type"], "type_label": TYPE_LABELS.get(last["program_type"], last["program_type"] or ""),
            "status": last["status"] or "", "status_label": STATUS_LABELS.get(last["status"] or "", last["status"] or ""),
            "historical": bool(last["historical"]),
            "project": d["project"] or "", "season": d["season"] or "", "phase": d["phase"] or "",
            "operator": d["operator"] or "", "drill_method": d["drill_method"] or "",
            "survey_type": d["survey_type"] or "", "target_metal": d["target_metal"] or "",
            "contractor": d["contractor"] or "",
            "metres": _num(d["metres"]), "holes": _int(d["holes"]), "line_km": _num(d["line_km"]),
            "budget": _num(d["budget"]), "currency": (cur or "") if d["budget"] is not None else "",
            "rigs": _int(d["rigs"]), "filled": sorted(set(filled)),
            "date": (last["published_at"] or "")[:10], "published_at": last["published_at"] or "",
            "first_reported": (rs[0]["published_at"] or "")[:10], "releases": len(releases),
            "headline": _title(last["raw_headline"] or ""),
            "release_url": release_url(t, last["slug"], last["event_id"]),
            "all_releases": releases[::-1],
        })
    out.sort(key=lambda x: (x["published_at"], x["program_id"]), reverse=True)
    return out


# MNT_SPEED_V2 (2026-09-25): without a ticker the whole table was rebuilt on every call (~4 s for exploration at
# ~50k rows). The built list is kept per worker while the table is unchanged (row count and max rowid) and for at
# most 5 minutes; filters and paging still run per call on a copy of the list. Only for a database file, so the
# in-memory self-tests always build fresh.
# OPSFIX item 3 (2026-10-05): the build took 11 s for exploration (69,903 rows) and ran once per worker after every
# update and every 5 minutes. Now: in memory for up to 30 minutes (the row-count/max-rowid fingerprint still
# invalidates it on any change), one build at a time per worker, and the result is shared with the other worker
# through a file in _DISK_DIR keyed on the table, query, fingerprint and company names, so each data change costs
# one build in total. Any file problem falls back to building, exactly as before.
import os as _o3
import pickle as _p3
import hashlib as _h3

_BUILT_CACHE: dict = {}
_BUILT_TTL = 1800.0
_BUILT_LOCK = threading.Lock()
_BUILD_LOCKS: dict = {}
_DISK_DIR = _o3.environ.get("MNT_LISTCACHE_DIR", "/opt/mnt/app/data/listcache")


def _disk_path(table: str, sql: str, args: list, names: dict, fp) -> str:
    h = _h3.sha256(repr((table, sql, tuple(args), tuple(fp))).encode("utf-8"))
    try:
        h.update(repr(sorted(names.items())).encode("utf-8"))
    except Exception:
        h.update(repr(id(names)).encode("utf-8"))
    return _o3.path.join(_DISK_DIR, "%s-%s.pkl" % (table, h.hexdigest()[:24]))


def _disk_load(path: str):
    try:
        with open(path, "rb") as f:
            return _p3.load(f)
    except Exception:
        return None


def _disk_save(path: str, built, table: str) -> None:
    try:
        _o3.makedirs(_DISK_DIR, exist_ok=True)
        tmp = "%s.%d.tmp" % (path, _o3.getpid())
        with open(tmp, "wb") as f:
            _p3.dump(built, f, protocol=_p3.HIGHEST_PROTOCOL)
        _o3.replace(tmp, path)
        now = time.time()
        for name in _o3.listdir(_DISK_DIR):          # drop this table's older builds after an hour
            p = _o3.path.join(_DISK_DIR, name)
            if name.startswith(table + "-") and p != path and now - _o3.path.getmtime(p) > 3600:
                _o3.remove(p)
    except Exception:
        pass


def _built_all(conn, sql: str, args: list, names: dict, build, table: str) -> list:
    # OPSFIX item 3b+3c (2026-10-05): the in-memory copy was keyed on id(names), and the company-name map is a new
    # object every time tickers.json is rewritten (several times an hour), so each rewrite added another full copy
    # of the list (~250 MB for exploration) until 17 had piled up; workers grew to 1.2-1.6 GB. Now there is one
    # copy per query, replaced in place, and it is reused while the table and the names of the tickers it shows
    # are unchanged (a rename elsewhere in tickers.json no longer forces an 11 s rebuild).
    def fresh():
        return build(conn.execute(sql + " ORDER BY published_at, event_id, ordinal", args).fetchall(), names)
    try:
        dbfile = conn.execute("PRAGMA database_list").fetchone()[2] or ""
    except Exception:
        dbfile = ""
    if not dbfile:
        return fresh()
    fp = tuple(conn.execute("SELECT count(*), max(rowid) FROM " + table).fetchone())
    nkey = _names_key(conn, table, fp, names)
    key = (dbfile, sql, tuple(args))
    with _BUILT_LOCK:
        hit = _BUILT_CACHE.get(key)
        lock = _BUILD_LOCKS.setdefault(key, threading.Lock())
    if hit is not None and hit[1] == fp and hit[2] == nkey and time.monotonic() - hit[0] < _BUILT_TTL:
        return list(hit[3])
    # OPSFIX item 3c (2026-10-05): when this worker already holds a copy and the data or names moved on, hand the
    # visitor that copy at once and rebuild it in the background on a read-only connection of its own (one rebuild
    # at a time per query). Only a worker's very first request for a list waits for a build.
    if hit is not None and lock.acquire(blocking=False):
        try:
            _th3.Thread(target=_refresh_bg, args=(dbfile, conn.row_factory, sql, args, names, build, table, key, lock),
                        name="listcache-refresh", daemon=True).start()
        except Exception:
            lock.release()
            raise
        return list(hit[3])
    if hit is not None:
        return list(hit[3])            # a refresh is already running
    with lock:
        with _BUILT_LOCK:
            hit = _BUILT_CACHE.get(key)
        if hit is not None and hit[1] == fp and hit[2] == nkey and time.monotonic() - hit[0] < _BUILT_TTL:
            return list(hit[3])
        path = _o3.path.join(_DISK_DIR, "%s-%s.pkl" % (table, _h3.sha256(
            repr((table, sql, tuple(args), tuple(fp), nkey)).encode("utf-8")).hexdigest()[:24]))
        built = _disk_load(path)
        if built is None:
            built = fresh()
            _disk_save(path, built, table)
        _store_built(key, (time.monotonic(), fp, nkey, built))
    return list(built)


_BUILT_MAX = 8


def _store_built(key, entry) -> None:
    # at most _BUILT_MAX lists per worker; the oldest-built goes first (filtered variants of a list are separate keys)
    with _BUILT_LOCK:
        _BUILT_CACHE[key] = entry
        while len(_BUILT_CACHE) > _BUILT_MAX:
            _BUILT_CACHE.pop(min(_BUILT_CACHE, key=lambda k: _BUILT_CACHE[k][0]), None)


_NKEY_CACHE: dict = {}


def _names_key(conn, table: str, fp, names: dict) -> str:
    """Fingerprint of the company names of the tickers this table holds (the only names a list row shows)."""
    k = (table, fp, id(names), len(names))
    with _BUILT_LOCK:
        v = _NKEY_CACHE.get(k)
    if v is None:
        tickers = sorted((r[0] or "") for r in conn.execute("SELECT DISTINCT ticker FROM " + table))
        v = _h3.sha256(repr([(t, names.get(t, "")) for t in tickers]).encode("utf-8")).hexdigest()[:24]
        with _BUILT_LOCK:
            if len(_NKEY_CACHE) > 64:
                _NKEY_CACHE.clear()
            _NKEY_CACHE[k] = v
    return v


import threading as _th3
import sqlite3 as _sq3


def _refresh_bg(dbfile, row_factory, sql, args, names, build, table, key, lock):
    try:
        c = _sq3.connect("file:%s?mode=ro" % dbfile, uri=True, timeout=30)
        try:
            c.row_factory = row_factory
            fp = tuple(c.execute("SELECT count(*), max(rowid) FROM " + table).fetchone())
            nkey = _names_key(c, table, fp, names)
            path = _o3.path.join(_DISK_DIR, "%s-%s.pkl" % (table, _h3.sha256(
                repr((table, sql, tuple(args), tuple(fp), nkey)).encode("utf-8")).hexdigest()[:24]))
            built = _disk_load(path)
            if built is None:
                built = build(c.execute(sql + " ORDER BY published_at, event_id, ordinal", args).fetchall(), names)
                _disk_save(path, built, table)
            _store_built(key, (time.monotonic(), fp, nkey, built))
        finally:
            c.close()
    except Exception:
        pass
    finally:
        lock.release()


def query_programs(conn, p: dict, names: dict, universe: Optional[frozenset]) -> dict:
    sql = "SELECT " + _COLS + " FROM exploration_programs WHERE program_type IS NOT NULL"
    args: list = []
    t = p.get("ticker")
    if t:
        b = bare(t)
        sql += " AND (UPPER(ticker) = ? OR UPPER(ticker) = ? OR UPPER(ticker) LIKE ?)"
        args += [t, b, b + ".%"]
    if not t:
        progs = _built_all(conn, sql, args, names, build_programs, "exploration_programs")    # MNT_SPEED_V2
    else:
        rows = conn.execute(sql + " ORDER BY published_at, event_id, ordinal", args).fetchall()
        if "." in t and any((r["ticker"] or "").upper() == t for r in rows):
            rows = [r for r in rows if (r["ticker"] or "").upper() == t]    # the listing asked for, not a namesake
        progs = build_programs(rows, names)
    if universe and not t:
        progs = [x for x in progs if x["bare_ticker"] in universe]
    if p.get("type"):
        progs = [x for x in progs if x["type"] == p["type"]]
    if p.get("status"):
        progs = [x for x in progs if x["status"] == p["status"]]
    if p["work"] == "own":
        progs = [x for x in progs if not x["historical"]]
    elif p["work"] == "historical":
        progs = [x for x in progs if x["historical"]]
    if p.get("since"):
        progs = [x for x in progs if x["date"] >= p["since"]]
    total, limit, page = len(progs), p["limit"], p["page"]
    return {
        "ok": True, "api_version": API_VERSION, "total": total, "page": page,
        "pages": max(1, math.ceil(total / limit)) if total else 0, "limit": limit,
        "filters": {k: p[k] for k in ("ticker", "type", "status", "since") if p.get(k)},
        "work": p["work"], "universe": p["universe"], "universe_applied": bool(universe) and not t,
        "items": progs[(page - 1) * limit: page * limit],
    }


# --------------------------------------------------------------------------- web

def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    @app.get("/api/v1/exploration")
    def exploration_list(ticker: Optional[str] = None, type: Optional[str] = None, status: Optional[str] = None,
                         work: Optional[str] = None, days: Optional[str] = None, page: Optional[str] = None,
                         limit: Optional[str] = None, universe: Optional[str] = None):
        try:
            p = parse_params(ticker, type, status, work, days, page, limit, universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = None
        if p["universe"] == "mtp":
            uni = _universe.get() or None
        with closing(_conn()) as conn:
            have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='exploration_programs'").fetchone()
            if not have:
                return JSONResponse({"ok": True, "api_version": API_VERSION, "total": 0, "page": 1, "pages": 0,
                                     "limit": p["limit"], "items": []}, headers=_headers())
            out = query_programs(conn, p, _names.get(), uni)
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
    CREATE TABLE exploration_programs (ep_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL DEFAULT 0, ticker TEXT, slug TEXT, program_type TEXT, project TEXT, status TEXT,
        metres REAL, holes INTEGER, line_km REAL, season TEXT, phase TEXT, historical INTEGER NOT NULL DEFAULT 0,
        operator TEXT, drill_method TEXT, survey_type TEXT, budget REAL, currency TEXT, target_metal TEXT,
        contractor TEXT, rigs INTEGER, program_key TEXT, program_releases INTEGER NOT NULL DEFAULT 1,
        first_reported TEXT, is_latest INTEGER NOT NULL DEFAULT 1, n_rows INTEGER NOT NULL DEFAULT 1,
        tag_confirmed INTEGER NOT NULL DEFAULT 0, raw_headline TEXT, published_at TEXT, extractor_version TEXT);
    """)

    def row(eid, t, date, typ="drilling", proj=None, status="planned", metres=None, holes=None, hist=0, op=None,
            method=None, budget=None, cur=None, metal=None, key=None, ordinal=0):
        conn.execute("INSERT INTO exploration_programs (event_id, ordinal, ticker, slug, program_type, project, status, "
                     "metres, holes, historical, operator, drill_method, budget, currency, target_metal, program_key, "
                     "raw_headline, published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, ordinal, t, "s-" + eid, typ, proj, status, metres, holes, hist, op, method, budget, cur,
                      metal, key, "HEADLINE " + eid, date + "T12:00:00"))

    # one program over three releases: planned 15,000 m -> started -> completed with holes but no metres
    row("m1", "TXG.TO", "2025-07-16", proj="Morelos", metres=15000, budget=12e6, cur="USD", metal="gold",
        key="TXG.TO:drilling:morelos:cur#1")
    row("m2", "TXG.TO", "2026-01-10", proj="Morelos", status="started", method="diamond", key="TXG.TO:drilling:morelos:cur#1")
    row("m3", "TXG.TO", "2026-04-30", proj="Morelos", status="completed", holes=40, key="TXG.TO:drilling:morelos:cur#1")
    # a geophysics survey without a key stands alone; a historical program by a previous owner
    row("g1", "TXG.TO", "2026-05-01", typ="geophysics", proj="Reyes", status="completed")
    row("m3", "TXG.TO", "2026-04-30", typ="drilling", proj="El Limon", status="completed", hist=1, op="Teck",
        metres=8000, ordinal=1)
    row("x1", "TXG.TO", "2026-06-01", typ=None, status=None)            # marker row: no program
    row("o1", "OGW.V", "2026-09-17", proj="Belmont", status="completed", metres=1979, holes=20)
    row("o2", "TXG.V", "2026-09-18", proj="Namesake", status="started")   # a different company with the same root
    names = {"TXG.TO": "Torex Gold Resources Inc.", "OGW.V": "Ongwe Minerals"}
    P = lambda **kw: parse_params(today=_dt.date(2026, 9, 22), **kw)

    r = query_programs(conn, P(), names, None)
    ok("one item per program, newest first, markers skipped",
       [x["project"] for x in r["items"]] == ["Namesake", "Belmont", "Reyes", "El Limon", "Morelos"] and r["total"] == 5)
    mo = [x for x in r["items"] if x["project"] == "Morelos"][0]
    ok("latest release leads; sizes carried over are flagged",
       mo["status"] == "completed" and mo["holes"] == 40 and mo["metres"] == 15000 and mo["filled"] == ["budget", "metres"]
       and mo["budget"] == 12e6 and mo["currency"] == "USD" and mo["drill_method"] == "diamond"
       and mo["target_metal"] == "gold" and mo["releases"] == 3 and mo["first_reported"] == "2025-07-16"
       and [h["status"] for h in mo["all_releases"]] == ["completed", "started", "planned"]
       and [(h["metres"], h["holes"], h["budget"]) for h in mo["all_releases"]] == [(None, 40, None), (None, None, None), (15000.0, None, 12e6)]
       and mo["all_releases"][2]["currency"] == "USD"
       and mo["type_label"] == "Drilling" and mo["status_label"] == "Completed")
    r = query_programs(conn, P(ticker="TXG.TO"), names, None)
    ok("exact listing wins over a namesake", r["total"] == 3 and all(x["ticker"] == "TXG.TO" for x in r["items"]))
    ok("bare ticker matches both", query_programs(conn, P(ticker="TXG"), names, None)["total"] == 4)
    ok("work filter", query_programs(conn, P(ticker="TXG.TO", work="historical"), names, None)["items"][0]["operator"] == "Teck"
       and query_programs(conn, P(ticker="TXG.TO", work="own"), names, None)["total"] == 2)
    ok("type / status filters", query_programs(conn, P(type="geophysics"), names, None)["total"] == 1
       and query_programs(conn, P(status="completed"), names, None)["total"] == 4)
    ok("universe", query_programs(conn, P(universe="mtp"), names, frozenset({"OGW"}))["total"] == 1)
    ok("days", query_programs(conn, P(days="30"), names, None)["total"] == 2)
    ok("paging", query_programs(conn, P(limit="2", page="3"), names, None)["items"][0]["project"] == "Morelos")

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad params", bad(type="x") and bad(status="x") and bad(work="x") and bad(ticker="A'--") and bad(universe="x"))
    print("exploration_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        if "/opt/mnt/app" not in sys.path and os.path.isdir("/opt/mnt/app"):
            sys.path.insert(0, "/opt/mnt/app")
        sys.exit(_selftest())
    print(__doc__)
