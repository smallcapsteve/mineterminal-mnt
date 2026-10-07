"""MNT Management Changes API v1: read-only JSON for cross-site use (MTP's company Management tab).

MNT_MGMT_API_V1 (2026-09-28, MTP site audit: "Management changes ... MNT /management-changes: 6,046 rows ... No" on
MTP; checklist C4 / D8 - a joined / left log). Serves what the management reader (MGMT_PUBLISH_V1, one row per
PERSON per release) writes into `management_changes`: who was appointed, resigned, departed, retired, changed role
or was promoted, to which role, on the board, in management or as an adviser, and from which release.

  /api/v1/management-changes     one item per person per release, newest first, filterable

List parameters
  ticker     exact symbol (GGM.V) or bare (GGM)
  action     appointed | resigned | departed | retired | changed | promoted (comma list allowed)
  scope      board | management | advisory
  person     part of a name (at least 3 letters)
  days       only changes published in the last N days
  page, limit    1-based page, limit 1..500 (default 100)
  universe   all (default) | mtp -> only companies on MTP's list (fails open, like the other APIs)

Registered from portal.serve via mgmt_api.register(app).
Self-tests: python3 -m portal.mgmt_api --selftest   (in-memory; touches nothing live)
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
MAX_LIMIT = 500
DEFAULT_LIMIT = 100
ACTIONS = ("appointed", "resigned", "departed", "retired", "changed", "promoted")
SCOPES = ("board", "management", "advisory")
_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")
_COLS = ("mgmt_id, event_id, ordinal, ticker, action, person, role, role_canon, scope, effective_date, interim, "
         "raw_headline, published_at, extractor_version")


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


def parse_params(ticker=None, action=None, scope=None, person=None, days=None, page=None, limit=None, universe=None,
                 today=None) -> dict:
    p: dict[str, Any] = {}
    t = (ticker or "").strip()
    if t:
        if not _TICKER_RE.match(t):
            raise BadRequest("ticker: letters, digits, '.' or '-' only")
        p["ticker"] = t.upper()
    acts = [a.strip().lower() for a in str(action or "").split(",") if a.strip()]
    for a in acts:
        if a not in ACTIONS:
            raise BadRequest("action: " + ", ".join(ACTIONS))
    if acts:
        p["actions"] = acts
    s = (scope or "").strip().lower()
    if s:
        if s not in SCOPES:
            raise BadRequest("scope: board, management or advisory")
        p["scope"] = s
    who = re.sub(r"\s+", " ", (person or "").strip())
    if who:
        if len(who) < 3 or len(who) > 60 or not re.match(r"^[\w .'\-]+$", who):
            raise BadRequest("person: 3 to 60 letters")
        p["person"] = who.lower()
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


ACTION_LABELS = {"appointed": "Appointed", "resigned": "Resigned", "departed": "Departed", "retired": "Retired",
                 "changed": "Role changed", "promoted": "Promoted"}
SCOPE_LABELS = {"board": "Board", "management": "Management", "advisory": "Advisory"}


def to_item(r, names: dict) -> dict:
    t = (r["ticker"] or "").strip()
    a = (r["action"] or "").strip().lower()
    s = (r["scope"] or "").strip().lower()
    return {
        "change_id": r["mgmt_id"], "event_id": r["event_id"], "ticker": t, "bare_ticker": bare(t),
        "company": company_name(t, names), "person": (r["person"] or "").strip(),
        "action": a, "action_label": ACTION_LABELS.get(a, a.capitalize()),
        "role": (r["role"] or "").strip(), "role_canon": (r["role_canon"] or "").strip(),
        "scope": s, "scope_label": SCOPE_LABELS.get(s, ""), "interim": bool(r["interim"]),
        "effective_date": (r["effective_date"] or "")[:10],
        "date": (r["published_at"] or "")[:10], "published_at": r["published_at"] or "",
        "headline": _title(r["raw_headline"] or ""),
        "release_url": release_url(t, None, r["event_id"]),
    }


def query_rows(conn, p: dict, names: dict, universe: Optional[frozenset]) -> dict:
    where = ["COALESCE(person, '') <> ''", "COALESCE(action, '') <> ''"]
    args: list = []
    t = p.get("ticker")
    if t:
        where.append("(upper(ticker) = ? OR upper(ticker) LIKE ?)")
        args += [t, bare(t) + ".%"]
    if p.get("actions"):
        where.append("lower(action) IN (%s)" % ",".join("?" * len(p["actions"])))
        args += p["actions"]
    if p.get("scope"):
        where.append("lower(COALESCE(scope, '')) = ?")
        args.append(p["scope"])
    if p.get("person"):
        where.append("lower(person) LIKE ?")
        args.append("%" + p["person"].replace("%", "").replace("_", "") + "%")
    if p.get("since"):
        where.append("published_at >= ?")
        args.append(p["since"])
    if universe:
        where.append("(CASE WHEN instr(ticker, '.') > 0 THEN upper(substr(ticker, 1, instr(ticker, '.') - 1)) "
                     "ELSE upper(ticker) END) IN (SELECT value FROM json_each(?))")
        args.append(json.dumps(sorted(universe)))
    w = " AND ".join(where)
    total = conn.execute("SELECT COUNT(*) FROM management_changes WHERE " + w, args).fetchone()[0]
    limit, page = p["limit"], p["page"]
    rows = conn.execute("SELECT " + _COLS + " FROM management_changes WHERE " + w +
                        " ORDER BY published_at DESC, event_id, ordinal LIMIT ? OFFSET ?",
                        args + [limit, (page - 1) * limit]).fetchall()
    slugs = {}
    ev = [r["event_id"] for r in rows]
    if ev:
        try:
            for e in conn.execute("SELECT event_id, ticker, slug FROM events WHERE event_id IN (%s)" % ",".join("?" * len(ev)), ev):
                slugs[e["event_id"]] = (e["ticker"], e["slug"])
        except sqlite3.Error:
            pass
    items = []
    for r in rows:
        it = to_item(r, names)
        tk, sl = slugs.get(r["event_id"], (None, None))
        it["release_url"] = release_url(tk or it["ticker"], sl, r["event_id"])
        items.append(it)
    return {
        "ok": True, "api_version": API_VERSION, "total": total, "page": page,
        "pages": max(1, math.ceil(total / limit)) if total else 0, "limit": limit,
        "filters": {k: p[k] for k in ("ticker", "actions", "scope", "person", "since") if p.get(k)},
        "universe": p["universe"], "universe_applied": bool(universe),
        "items": items,
    }


def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    @app.get("/api/v1/management-changes")
    def management_changes_list(ticker: Optional[str] = None, action: Optional[str] = None, scope: Optional[str] = None,
                                person: Optional[str] = None, days: Optional[str] = None, page: Optional[str] = None,
                                limit: Optional[str] = None, universe: Optional[str] = None):
        try:
            p = parse_params(ticker, action, scope, person, days, page, limit, universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = None
        if p["universe"] == "mtp":
            uni = _universe.get() or None
        with closing(_conn()) as conn:
            have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='management_changes'").fetchone()
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
    CREATE TABLE management_changes (mgmt_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL DEFAULT 0, ticker TEXT, action TEXT, person TEXT, role TEXT, role_canon TEXT, scope TEXT,
        effective_date TEXT, interim INTEGER NOT NULL DEFAULT 0, n_changes INTEGER NOT NULL DEFAULT 1, raw_headline TEXT,
        published_at TEXT, extractor_version TEXT);
    CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, slug TEXT);
    """)
    seq = {"n": 0}

    def row(eid, t, date, action, person, role="CEO", scope="management", interim=0):
        seq["n"] += 1
        conn.execute("INSERT INTO management_changes (event_id, ordinal, ticker, action, person, role, role_canon, scope, "
                     "interim, raw_headline, published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, seq["n"], t, action, person, role, role, scope, interim, "HEADLINE", date + "T12:00:00"))
    row("e1", "GGM.V", "2026-09-28", "appointed", "J.W. Dumont", "President")
    row("e2", "GGM.V", "2026-03-01", "resigned", "Ann Smith", "Director", "board")
    row("e3", "KIRO.V", "2026-09-28", "resigned", "Michelle DeCecco", "COO")
    row("e4", "KIRO.V", "2026-09-20", "appointed", "", "COO")          # no person: not a change we can show
    conn.execute("INSERT INTO events VALUES ('e1','GGM.V','granada-appoints')")
    names = {"GGM.V": "Granada Gold Mine Inc."}
    P = lambda **kw: parse_params(today=_dt.date(2026, 9, 28), **kw)

    r = query_rows(conn, P(), names, None)
    ok("rows without a person left out, newest first", r["total"] == 3 and r["items"][0]["person"] in ("J.W. Dumont", "Michelle DeCecco"))
    g = query_rows(conn, P(ticker="GGM"), names, None)
    ok("ticker bare + labels + release url", g["total"] == 2 and g["items"][0]["action_label"] == "Appointed"
       and g["items"][0]["company"] == "Granada Gold Mine Inc." and g["items"][0]["release_url"].endswith("/news/ggm.v/granada-appoints")
       and g["items"][1]["scope_label"] == "Board")
    ok("action filter", query_rows(conn, P(action="resigned"), names, None)["total"] == 2)
    ok("scope filter", query_rows(conn, P(scope="board"), names, None)["total"] == 1)
    ok("person filter", query_rows(conn, P(person="dumont"), names, None)["total"] == 1)
    ok("days", query_rows(conn, P(days="30"), names, None)["total"] == 2)
    ok("universe", query_rows(conn, P(universe="mtp"), names, frozenset({"KIRO"}))["total"] == 1)
    ok("paging", query_rows(conn, P(limit="1", page="2"), names, None)["pages"] == 3)

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad params", bad(action="x") and bad(scope="x") and bad(person="a") and bad(ticker="A'--") and bad(universe="x"))
    print("mgmt_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        if "/opt/mnt/app" not in sys.path and os.path.isdir("/opt/mnt/app"):
            sys.path.insert(0, "/opt/mnt/app")
        sys.exit(_selftest())
    print(__doc__)
