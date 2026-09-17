"""MNT Financings API v1: read-only JSON for cross-site use (MTP /financings and company pages).

MNT_FINANCINGS_API_V1 (2026-09-17). Three endpoints, all GET, CORS-allowed, serving what the
/financings page serves: the deals FIN_V1 publishes into `financings`, with the releases behind
each one in `financing_events`.

  /api/v1/financings                 paged list of deals, filterable and sortable
  /api/v1/financings/facets          statuses, kinds and currencies with counts (for filters)
  /api/v1/financings/{financing_id}  one deal with every release grouped into it

A financing is a deal, not a release: it is announced, maybe upsized or amended, closes in one or
more tranches, and can be terminated. Each item therefore carries the deal's current state and the
count of releases behind it; ask for them with include=events, or fetch the one deal.

List parameters
  ticker     exact symbol (RRI.V) or bare (RRI)
  status     announced | upsized | tranche_closed | closed | terminated | amended
  state      all (default) | open | closed. Open means announced, upsized or amended and touched
             in the last 60 days; closed is everything else, including stale announcements. Same
             rule as the /financings page.
  kind       one token of the deal's kind set: PP, FT, LIFE, CD, DEBT, BROKERED, NON_BROKERED,
             BOUGHT_DEAL, ... A deal whose kind is "FT+PP+NON_BROKERED" matches all three.
  currency   CAD, USD, ...
  since, until   YYYY-MM-DD on the announcement date (inclusive)
  days       shorthand for since = today - days
  sort       date (default, announcement) | updated (last movement) | size (gross closed, else
             announced). size needs currency: dollars of different currencies don't compare.
  page, limit    1-based page, limit 1..200 (default 50)
  include    events -> every release behind each deal
  universe   all (default) | mtp -> only companies on MTP's list
             (/var/lib/mnt-portal/mtp-companies.json). If that list can't be read the filter is
             not applied and the response says universe_applied: false (fail open).

gross is the money actually raised where it is known (gross_closed), otherwise the amount
announced; gross_basis says which it is, so a caller never adds an announcement to a close by
accident. Amounts are left in the deal's own currency, never converted.

Registered from portal.serve via financings_api.register(app). Depends only on sqlite3, the
tickers file and portal.text_helpers.smart_title.

Self-tests: python3 -m portal.financings_api --selftest   (in-memory; touches nothing live)
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
SORTS = ("date", "updated", "size")
STATES = ("all", "open", "closed")
OPEN_STATUSES = ("announced", "upsized", "amended")
CLOSED_STATUSES = ("closed", "tranche_closed", "final_close", "terminated")
OPEN_WINDOW_DAYS = 60

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{1,24}$")
_STATUS_RE = re.compile(r"^[a-z_]{3,24}$")


# --------------------------------------------------------------------------- helpers (pure)

def bare(ticker: Optional[str]) -> str:
    return (ticker or "").strip().upper().split(".")[0]


def kind_tokens(kind: Optional[str]) -> list[str]:
    """'FT+PP+NON_BROKERED' -> ['FT', 'PP', 'NON_BROKERED']; order kept, duplicates dropped."""
    out: list[str] = []
    for part in re.split(r"[+,/]", (kind or "").strip()):
        t = part.strip().upper()
        if t and t not in out:
            out.append(t)
    return out


def gross_of(gross_closed, gross_announced) -> tuple[Optional[float], str]:
    """The money to show, and which field it came from. Closed wins: it is what was raised."""
    if gross_closed is not None:
        return float(gross_closed), "closed"
    if gross_announced is not None:
        return float(gross_announced), "announced"
    return None, "none"


def deal_state(status: Optional[str], last_update_at: Optional[str], today=None) -> str:
    """open | closed, the /financings page's rule: an announcement nobody has touched in 60 days
    has gone quiet, so it is not an open deal any more."""
    s = (status or "").strip().lower()
    if s not in OPEN_STATUSES:
        return "closed"
    base = today or _dt.datetime.utcnow().date()
    cut = (base - _dt.timedelta(days=OPEN_WINDOW_DAYS)).isoformat()
    return "open" if (last_update_at or "")[:10] >= cut else "closed"


class BadRequest(ValueError):
    pass


def parse_params(ticker=None, status=None, state=None, kind=None, currency=None, since=None,
                 until=None, days=None, sort=None, page=None, limit=None, include=None,
                 universe=None, today=None) -> dict:
    p: dict[str, Any] = {}
    t = (ticker or "").strip()
    if t:
        if not _TICKER_RE.match(t):
            raise BadRequest("ticker: letters, digits, '.' or '-' only")
        p["ticker"] = t.upper()
    st = (status or "").strip().lower()
    if st:
        if not _STATUS_RE.match(st):
            raise BadRequest("status: lower-case letters and '_' only")
        p["status"] = st
    stt = (state or "all").strip().lower()
    if stt not in STATES:
        raise BadRequest("state: one of " + ", ".join(STATES))
    p["state"] = stt
    k = re.sub(r"\s+", "+", (kind or "").strip())
    if k:
        if not _TOKEN_RE.match(k.replace("+", "")) or "+" in k:
            raise BadRequest("kind: one token, e.g. PP, FT, LIFE, BROKERED")
        p["kind"] = k.upper()
    c = (currency or "").strip().upper()
    if c:
        if not re.match(r"^[A-Z]{3}$", c):
            raise BadRequest("currency: a three-letter code, e.g. CAD")
        p["currency"] = c
    for key, v in (("since", since), ("until", until)):
        v = (v or "").strip()
        if v:
            if not _DATE_RE.match(v):
                raise BadRequest(key + ": YYYY-MM-DD")
            p[key] = v
    if days not in (None, "", 0, "0"):
        try:
            d = int(days)
        except (TypeError, ValueError):
            raise BadRequest("days: a whole number")
        if d < 0 or d > 36500:
            raise BadRequest("days: 0..36500")
        if d:
            base = today or _dt.datetime.utcnow().date()
            p["since"] = max(p.get("since", ""), (base - _dt.timedelta(days=d)).isoformat())
    s = (sort or "date").strip().lower()
    if s not in SORTS:
        raise BadRequest("sort: one of " + ", ".join(SORTS))
    if s == "size" and "currency" not in p:
        raise BadRequest("sort=size needs currency (amounts in different currencies don't compare)")
    p["sort"] = s
    try:
        p["page"] = max(1, int(page or 1))
        lim = int(limit or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        raise BadRequest("page and limit: whole numbers")
    p["limit"] = max(1, min(lim, MAX_LIMIT))
    inc = {x.strip().lower() for x in (include or "").split(",") if x.strip()}
    if inc - {"events"}:
        raise BadRequest("include: events")
    p["events"] = "events" in inc
    u = (universe or "all").strip().lower()
    if u not in ("all", "mtp"):
        raise BadRequest("universe: all or mtp")
    p["universe"] = u
    p["today"] = today
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


def _title(s: Optional[str]) -> str:
    if not s:
        return ""
    try:
        from portal.text_helpers import smart_title
        return smart_title(s)
    except Exception:
        return s


def release_url(ticker: Optional[str], slug: Optional[str], event_id: Optional[str]) -> str:
    t = (ticker or "").strip()
    sl = (slug or "").strip()
    if t and sl:
        return f"{SITE_BASE}/news/{t.lower()}/{sl}"
    return f"{SITE_BASE}/event/{event_id}" if event_id else ""


# --------------------------------------------------------------------------- queries

_DEAL_COLS = (
    "f.financing_id, f.ticker, f.announced_at, f.last_update_at, f.kind, f.status, "
    "f.gross_announced, f.gross_closed, f.gross_offered_max, f.unit_price, f.unit_prices, "
    "f.unit_comp, f.warrant_strike, f.warrant_term_months, f.n_tranches, f.n_events, "
    "f.unit_count, f.currency, f.extractor_version, f.seed_event_id, "
    "e.slug AS seed_slug, e.raw_headline AS seed_headline, e.source_url AS seed_source_url, "
    "e.source_name AS seed_source_name"
)

_EVENT_COLS = (
    "fe.event_id, fe.financing_id, fe.ticker, fe.role, fe.tranche_label, fe.kind, fe.gross_total, "
    "fe.amount_offered, fe.amount_this_close, fe.amount_closed_total, fe.unit_count, fe.unit_price, "
    "fe.unit_comp, fe.warrant_strike, fe.warrant_term_months, fe.currency, fe.is_duplicate, "
    "COALESCE(fe.event_date, e.published_at) AS event_date, "
    "COALESCE(e.raw_headline, fe.raw_headline) AS headline, e.slug, e.source_url, e.source_name"
)


def _prices(s) -> list[float]:
    out = []
    for part in re.split(r"[|,;]", str(s or "")):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(float(part))
        except ValueError:
            pass
    return out


def _where(p: dict, universe: Optional[frozenset]) -> tuple[list[str], list]:
    where, args = [], []
    t = p.get("ticker")
    if t:
        where.append("(upper(f.ticker) = ? OR upper(f.ticker) LIKE ?)")
        args += [t, bare(t) + ".%"]
    if p.get("status"):
        where.append("lower(COALESCE(f.status, '')) = ?")
        args.append(p["status"])
    if p.get("kind"):
        where.append("('+' || upper(REPLACE(REPLACE(COALESCE(f.kind, ''), ',', '+'), '/', '+')) || '+') LIKE ?")
        args.append("%+" + p["kind"] + "+%")
    if p.get("currency"):
        where.append("upper(COALESCE(f.currency, '')) = ?")
        args.append(p["currency"])
    if p.get("since"):
        where.append("substr(COALESCE(f.announced_at, ''), 1, 10) >= ?")
        args.append(p["since"])
    if p.get("until"):
        where.append("substr(COALESCE(f.announced_at, ''), 1, 10) <= ?")
        args.append(p["until"])
    state = p.get("state", "all")
    if state in ("open", "closed"):
        base = p.get("today") or _dt.datetime.utcnow().date()
        cut = (base - _dt.timedelta(days=OPEN_WINDOW_DAYS)).isoformat()
        ins = ",".join("?" * len(OPEN_STATUSES))
        if state == "open":
            where.append("(lower(COALESCE(f.status, '')) IN (%s) AND substr(COALESCE(f.last_update_at, ''), 1, 10) >= ?)" % ins)
            args += list(OPEN_STATUSES) + [cut]
        else:
            where.append("(lower(COALESCE(f.status, '')) NOT IN (%s) OR substr(COALESCE(f.last_update_at, ''), 1, 10) < ?)" % ins)
            args += list(OPEN_STATUSES) + [cut]
    if universe:
        where.append(
            "(CASE WHEN instr(f.ticker, '.') > 0 THEN upper(substr(f.ticker, 1, instr(f.ticker, '.') - 1)) "
            "ELSE upper(f.ticker) END) IN (SELECT value FROM json_each(?))")
        args.append(json.dumps(sorted(universe)))
    return where or ["1=1"], args


def _event_dict(r) -> dict:
    t = (r["ticker"] or "").strip()
    d = (r["event_date"] or "")
    return {
        "event_id": r["event_id"],
        "role": r["role"] or "",
        "tranche_label": r["tranche_label"] or "",
        "date": d[:10],
        "event_date": d,
        "kind": r["kind"] or "",
        "kind_tokens": kind_tokens(r["kind"]),
        "gross_total": r["gross_total"],
        "amount_offered": r["amount_offered"],
        "amount_this_close": r["amount_this_close"],
        "amount_closed_total": r["amount_closed_total"],
        "unit_count": r["unit_count"],
        "unit_price": r["unit_price"],
        "unit_comp": r["unit_comp"] or "",
        "warrant_strike": r["warrant_strike"],
        "warrant_term_months": r["warrant_term_months"],
        "currency": (r["currency"] or "").upper(),
        "is_duplicate": bool(r["is_duplicate"]),
        "headline": _title(r["headline"] or ""),
        "release_url": release_url(t, r["slug"], r["event_id"]),
        "source_url": r["source_url"] or "",
        "source_name": r["source_name"] or "",
    }


def _deal_dict(r, names: dict, today=None) -> dict:
    t = (r["ticker"] or "").strip()
    ann = r["announced_at"] or ""
    upd = r["last_update_at"] or ""
    gross, basis = gross_of(r["gross_closed"], r["gross_announced"])
    return {
        "financing_id": r["financing_id"],
        "ticker": t,
        "bare_ticker": bare(t),
        "company": company_name(t, names),
        "announced_at": ann,
        "date": ann[:10],
        "last_update_at": upd,
        "updated": upd[:10],
        "kind": r["kind"] or "",
        "kind_tokens": kind_tokens(r["kind"]),
        "status": r["status"] or "",
        "state": deal_state(r["status"], upd, today),
        "gross": gross,
        "gross_basis": basis,
        "gross_announced": r["gross_announced"],
        "gross_closed": r["gross_closed"],
        "gross_offered_max": r["gross_offered_max"],
        "currency": (r["currency"] or "").upper(),
        "unit_price": r["unit_price"],
        "unit_prices": _prices(r["unit_prices"]),
        "unit_count": r["unit_count"],
        "unit_comp": r["unit_comp"] or "",
        "warrant_strike": r["warrant_strike"],
        "warrant_term_months": r["warrant_term_months"],
        "n_tranches": r["n_tranches"],
        "n_events": r["n_events"],
        "extractor_version": r["extractor_version"] or "",
        "seed_event_id": r["seed_event_id"] or "",
        "headline": _title(r["seed_headline"] or ""),
        "release_url": release_url(t, r["seed_slug"], r["seed_event_id"]),
        "source_url": r["seed_source_url"] or "",
        "source_name": r["seed_source_name"] or "",
    }


def _attach_events(conn, deals: list[dict]) -> None:
    ids = [d["financing_id"] for d in deals]
    if not ids:
        return
    by: dict[int, list] = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        rows = conn.execute(
            "SELECT " + _EVENT_COLS + " FROM financing_events fe "
            "LEFT JOIN events e ON e.event_id = fe.event_id "
            "WHERE fe.financing_id IN (%s) "
            "ORDER BY fe.financing_id, COALESCE(fe.event_date, e.published_at), fe.event_id"
            % ",".join("?" * len(chunk)), chunk).fetchall()
        for r in rows:
            by.setdefault(r["financing_id"], []).append(_event_dict(r))
    for d in deals:
        d["events"] = by.get(d["financing_id"], [])


def query_list(conn, p: dict, names: dict, universe: Optional[frozenset]) -> dict:
    where, args = _where(p, universe)
    order = {
        "date": "COALESCE(f.announced_at, f.last_update_at) DESC, f.financing_id DESC",
        "updated": "COALESCE(f.last_update_at, f.announced_at) DESC, f.financing_id DESC",
        "size": "COALESCE(f.gross_closed, f.gross_announced) DESC, COALESCE(f.announced_at, '') DESC, f.financing_id DESC",
    }[p["sort"]]
    base = ("FROM financings f LEFT JOIN events e ON e.event_id = f.seed_event_id WHERE " + " AND ".join(where))
    total = conn.execute("SELECT COUNT(*) FROM financings f WHERE " + " AND ".join(where), args).fetchone()[0]
    limit, page = p["limit"], p["page"]
    rows = conn.execute("SELECT " + _DEAL_COLS + " " + base + " ORDER BY " + order + " LIMIT ? OFFSET ?",
                        args + [limit, (page - 1) * limit]).fetchall()
    items = [_deal_dict(r, names, p.get("today")) for r in rows]
    if p["events"]:
        _attach_events(conn, items)
    return {
        "ok": True,
        "api_version": API_VERSION,
        "total": total,
        "page": page,
        "pages": max(1, math.ceil(total / limit)) if total else 0,
        "limit": limit,
        "sort": p["sort"],
        "filters": {k: p[k] for k in ("ticker", "status", "kind", "currency", "since", "until") if p.get(k)},
        "state": p["state"],
        "universe": p["universe"],
        "universe_applied": bool(universe),
        "items": items,
    }


def query_one(conn, financing_id: int, names: dict, today=None) -> Optional[dict]:
    r = conn.execute("SELECT " + _DEAL_COLS + " FROM financings f "
                     "LEFT JOIN events e ON e.event_id = f.seed_event_id "
                     "WHERE f.financing_id = ?", (financing_id,)).fetchone()
    if not r:
        return None
    d = _deal_dict(r, names, today)
    _attach_events(conn, [d])
    return d


def query_facets(conn, universe: Optional[frozenset], today=None) -> dict:
    """Statuses, kind tokens and currencies with deal counts - what a filter bar needs."""
    where, args = _where({"state": "all", "today": today}, universe)
    w = " WHERE " + " AND ".join(where)
    statuses = [{"status": (r[0] or ""), "deals": r[1]} for r in conn.execute(
        "SELECT lower(COALESCE(f.status, '')), COUNT(*) FROM financings f" + w +
        " GROUP BY 1 ORDER BY 2 DESC", args)]
    currencies = [{"currency": (r[0] or "").upper(), "deals": r[1]} for r in conn.execute(
        "SELECT upper(COALESCE(f.currency, '')), COUNT(*) FROM financings f" + w +
        " GROUP BY 1 ORDER BY 2 DESC", args)]
    counts: dict[str, int] = {}
    for r in conn.execute("SELECT f.kind, COUNT(*) FROM financings f" + w + " GROUP BY 1", args):
        for tok in kind_tokens(r[0]):
            counts[tok] = counts.get(tok, 0) + r[1]
    kinds = [{"kind": k, "deals": n} for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    states = {"open": 0, "closed": 0}
    for r in conn.execute("SELECT f.status, f.last_update_at FROM financings f" + w, args):
        states[deal_state(r[0], r[1], today)] += 1
    return {"statuses": statuses, "kinds": kinds, "currencies": currencies, "states": states}


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

    # Registered before /{financing_id} so "facets" is never read as an id.
    @app.get("/api/v1/financings/facets")
    def financings_facets(universe: str = "all"):
        try:
            p = parse_params(universe=universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = _universe_for(p["universe"])
        with closing(_conn()) as conn:
            data = query_facets(conn, uni)
        out = {"ok": True, "api_version": API_VERSION, "universe": p["universe"],
               "universe_applied": bool(uni)}
        out.update(data)
        return JSONResponse(out, headers=_headers())

    @app.get("/api/v1/financings/{financing_id}")
    def financings_one(financing_id: str):
        if not re.match(r"^\d{1,12}$", financing_id or ""):
            return _err("financing_id: a whole number", 400)
        with closing(_conn()) as conn:
            it = query_one(conn, int(financing_id), _names.get())
        if not it:
            return _err("not_found", 404)
        return JSONResponse({"ok": True, "api_version": API_VERSION, "item": it}, headers=_headers())

    @app.get("/api/v1/financings")
    def financings_list(ticker: Optional[str] = None, status: Optional[str] = None,
                        state: Optional[str] = None, kind: Optional[str] = None,
                        currency: Optional[str] = None, since: Optional[str] = None,
                        until: Optional[str] = None, days: Optional[str] = None,
                        sort: Optional[str] = None, page: Optional[str] = None,
                        limit: Optional[str] = None, include: Optional[str] = None,
                        universe: Optional[str] = None):
        try:
            p = parse_params(ticker, status, state, kind, currency, since, until, days, sort,
                             page, limit, include, universe)
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
    CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, slug TEXT, raw_headline TEXT,
        published_at TEXT, source_url TEXT, source_name TEXT);
    CREATE TABLE financings (financing_id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, announced_at TEXT,
        last_update_at TEXT, kind TEXT, status TEXT, gross_announced REAL, gross_closed REAL,
        unit_price REAL, unit_comp TEXT, warrant_strike REAL, warrant_term_months INTEGER,
        n_tranches INTEGER, n_events INTEGER, seed_event_id TEXT, unit_count INTEGER, currency TEXT,
        extractor_version TEXT, gross_offered_max REAL, unit_prices TEXT);
    CREATE TABLE financing_events (event_id TEXT PRIMARY KEY, financing_id INTEGER, ticker TEXT NOT NULL,
        role TEXT, tranche_label TEXT, kind TEXT, gross_total REAL, unit_count INTEGER, unit_price REAL,
        unit_comp TEXT, warrant_strike REAL, warrant_term_months INTEGER, ref_dates TEXT, event_date TEXT,
        raw_headline TEXT, currency TEXT, is_deal INTEGER, amount_offered REAL, amount_this_close REAL,
        amount_closed_total REAL, is_duplicate INTEGER, reason TEXT, unit_prices TEXT, extractor_version TEXT);
    """)

    def ev(eid, t, date, slug="s", head="ACME CLOSES PLACEMENT"):
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)",
                     (eid, t, slug, head, date + "T12:00:00", "https://wire/" + eid, "Wire"))

    def deal(fid, t, ann, upd, kind, status, ga, gc, cur="CAD", seed=None, price=0.4,
             strike=0.55, term=24, tranches=0, events=1, prices=None):
        conn.execute("INSERT INTO financings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (fid, t, ann, upd, kind, status, ga, gc, price, "share + half warrant", strike,
                      term, tranches, events, seed, None, cur, "1.0.2", None, prices))

    def fev(eid, fid, t, role, date, close=None, total=None, dup=0, label=""):
        conn.execute("INSERT INTO financing_events (event_id, financing_id, ticker, role, tranche_label,"
                     " kind, gross_total, unit_price, unit_comp, warrant_strike, warrant_term_months,"
                     " event_date, raw_headline, currency, is_deal, amount_offered, amount_this_close,"
                     " amount_closed_total, is_duplicate, extractor_version)"
                     " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, fid, t, role, label, "PP+NON_BROKERED", total, 0.4, "share + half warrant",
                      0.55, 24, date, "ACME CLOSES PLACEMENT", "CAD", 1, None, close, total, dup, "1.0.2"))

    TODAY = _dt.date(2026, 9, 17)
    # d1 AAA.V: announced 2026-09-10, still open, $5M announced, two releases
    ev("e1", "AAA.V", "2026-09-10"); ev("e1b", "AAA.V", "2026-09-12", slug="s2")
    deal(1, "AAA.V", "2026-09-10", "2026-09-12", "PP+NON_BROKERED", "upsized", 5000000.0, None,
         seed="e1", events=2, prices="0.4|0.5")
    fev("e1", 1, "AAA.V", "announcement", "2026-09-10", total=4000000.0)
    fev("e1b", 1, "AAA.V", "upsize", "2026-09-12", total=5000000.0)
    # d2 BBB.CN: closed 2026-08-01, $2.5M closed, USD
    ev("e2", "BBB.CN", "2026-07-01")
    deal(2, "BBB.CN", "2026-07-01", "2026-08-01", "FT+PP+BROKERED", "closed", 2000000.0, 2500000.0,
         cur="USD", seed="e2", tranches=2, events=3)
    fev("e2", 2, "BBB.CN", "announcement", "2026-07-01", total=2000000.0)
    fev("e2b", 2, "BBB.CN", "tranche_close", "2026-07-20", close=1000000.0, total=1000000.0, label="First tranche")
    fev("e2c", 2, "BBB.CN", "final_close", "2026-08-01", close=1500000.0, total=2500000.0, dup=1)
    # d3 CCC.TO: announced 2026-01-02 and untouched since -> stale, counts as closed
    ev("e3", "CCC.TO", "2026-01-02")
    deal(3, "CCC.TO", "2026-01-02", "2026-01-02", "LIFE+NON_BROKERED", "announced", 900000.0, None, seed="e3")
    fev("e3", 3, "CCC.TO", "announcement", "2026-01-02", total=900000.0)
    # d4 AAA.V: terminated, big headline number, no seed release row in events
    deal(4, "AAA.V", "2026-03-05", "2026-04-01", "DEBT", "terminated", 12000000.0, None, seed="gone")
    # d5 DDD.V: closed, largest CAD raise
    ev("e5", "DDD.V", "2026-05-05")
    deal(5, "DDD.V", "2026-05-05", "2026-06-06", "PP+BOUGHT_DEAL", "closed", 8000000.0, 9500000.0, seed="e5")

    names = {"AAA.V": "Acme Gold Corp.", "BBB.CN": "Bbb", "CCC.TO": "Cee Metals"}
    P = lambda **kw: parse_params(today=TODAY, **kw)

    ok("kind tokens", kind_tokens("FT+PP+NON_BROKERED") == ["FT", "PP", "NON_BROKERED"]
       and kind_tokens("") == [] and kind_tokens("PP,PP") == ["PP"])
    ok("gross prefers closed", gross_of(2500000.0, 2000000.0) == (2500000.0, "closed")
       and gross_of(None, 2000000.0) == (2000000.0, "announced") and gross_of(None, None) == (None, "none"))
    ok("state open", deal_state("announced", "2026-09-01", TODAY) == "open")
    ok("state stale announcement is closed", deal_state("announced", "2026-01-02", TODAY) == "closed")
    ok("state closed status", deal_state("closed", "2026-09-16", TODAY) == "closed")
    ok("prices parsed", _prices("0.4|0.5") == [0.4, 0.5] and _prices(None) == [] and _prices("x") == [])
    ok("release url", release_url("AAA.V", "s", "e1") == SITE_BASE + "/news/aaa.v/s"
       and release_url("AAA.V", "", "e1") == SITE_BASE + "/event/e1")

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True

    ok("sort=size needs currency", bad(sort="size"))
    ok("size with currency ok", P(sort="size", currency="cad")["currency"] == "CAD")
    ok("bad sort", bad(sort="drop"))
    ok("bad state", bad(state="maybe"))
    ok("bad ticker", bad(ticker="A'; --"))
    ok("bad status", bad(status="Closed!"))
    ok("bad kind (one token only)", bad(kind="PP+FT"))
    ok("bad currency", bad(currency="dollars"))
    ok("bad include", bad(include="everything"))
    ok("bad universe", bad(universe="x"))
    ok("limit capped", P(limit="5000")["limit"] == MAX_LIMIT)
    ok("page floor", P(page="0")["page"] == 1)
    ok("days -> since", P(days="10")["since"] == "2026-09-07")

    r = query_list(conn, P(), names, None)
    ids = [i["financing_id"] for i in r["items"]]
    ok("newest first", ids == [1, 2, 5, 4, 3] and r["total"] == 5 and r["pages"] == 1)
    it = r["items"][0]
    ok("deal fields", it["ticker"] == "AAA.V" and it["bare_ticker"] == "AAA"
       and it["company"] == "Acme Gold Corp." and it["date"] == "2026-09-10"
       and it["kind_tokens"] == ["PP", "NON_BROKERED"] and it["state"] == "open"
       and it["gross"] == 5000000.0 and it["gross_basis"] == "announced" and it["currency"] == "CAD")
    ok("unit prices", it["unit_prices"] == [0.4, 0.5])
    ok("headline title-cased where smart_title is available", it["headline"].lower().startswith("acme closes"))
    ok("release url on the deal", it["release_url"] == SITE_BASE + "/news/aaa.v/s")
    ok("stub company name dropped", r["items"][1]["company"] == "")
    ok("missing seed release -> event url", r["items"][3]["release_url"] == SITE_BASE + "/event/gone")
    ok("closed deal shows money raised", r["items"][1]["gross"] == 2500000.0
       and r["items"][1]["gross_basis"] == "closed" and r["items"][1]["currency"] == "USD")
    ok("no events unless asked", "events" not in it)

    r = query_list(conn, P(sort="updated"), names, None)
    ok("updated order", [i["financing_id"] for i in r["items"]] == [1, 2, 5, 4, 3])
    r = query_list(conn, P(sort="size", currency="CAD"), names, None)
    ok("size order, one currency", [i["financing_id"] for i in r["items"]] == [4, 5, 1, 3])
    r = query_list(conn, P(limit="2", page="2"), names, None)
    ok("paging", [i["financing_id"] for i in r["items"]] == [5, 4] and r["pages"] == 3)

    r = query_list(conn, P(ticker="aaa"), names, None)
    ok("bare ticker", [i["financing_id"] for i in r["items"]] == [1, 4])
    r = query_list(conn, P(ticker="AAA.V"), names, None)
    ok("full ticker", [i["financing_id"] for i in r["items"]] == [1, 4])
    r = query_list(conn, P(status="closed"), names, None)
    ok("status filter", [i["financing_id"] for i in r["items"]] == [2, 5])
    r = query_list(conn, P(kind="pp"), names, None)
    ok("kind token filter", [i["financing_id"] for i in r["items"]] == [1, 2, 5])
    r = query_list(conn, P(kind="NON_BROKERED"), names, None)
    ok("kind token is not a prefix match", [i["financing_id"] for i in r["items"]] == [1, 3])
    r = query_list(conn, P(currency="USD"), names, None)
    ok("currency filter", [i["financing_id"] for i in r["items"]] == [2])
    r = query_list(conn, P(since="2026-05-01", until="2026-07-31"), names, None)
    ok("date window on the announcement", [i["financing_id"] for i in r["items"]] == [2, 5])
    r = query_list(conn, P(state="open"), names, None)
    ok("open deals", [i["financing_id"] for i in r["items"]] == [1])
    r = query_list(conn, P(state="closed"), names, None)
    ok("closed includes the stale announcement", [i["financing_id"] for i in r["items"]] == [2, 5, 4, 3])
    ok("state echoed", r["state"] == "closed" and r["filters"] == {})

    r = query_list(conn, P(ticker="BBB", include="events"), names, None)
    evs = r["items"][0]["events"]
    ok("events attached in date order", [e["role"] for e in evs] == ["announcement", "tranche_close", "final_close"])
    ok("event fields", evs[1]["tranche_label"] == "First tranche" and evs[1]["amount_this_close"] == 1000000.0
       and evs[1]["date"] == "2026-07-20" and evs[2]["is_duplicate"] is True
       and evs[2]["amount_closed_total"] == 2500000.0)
    ok("event without its release still resolves a url", evs[1]["release_url"] == SITE_BASE + "/event/e2b")

    one = query_one(conn, 2, names, TODAY)
    ok("one deal", one and one["financing_id"] == 2 and len(one["events"]) == 3 and one["n_tranches"] == 2)
    ok("one missing -> None", query_one(conn, 999, names, TODAY) is None)

    uni = frozenset({"AAA", "DDD"})
    r = query_list(conn, P(universe="mtp"), names, uni)
    ok("universe filter", [i["financing_id"] for i in r["items"]] == [1, 5, 4] and r["universe_applied"])
    r = query_list(conn, P(universe="mtp"), names, None)
    ok("universe fail-open", r["total"] == 5 and r["universe_applied"] is False)

    f = query_facets(conn, None, TODAY)
    ok("facet statuses", {x["status"]: x["deals"] for x in f["statuses"]}
       == {"closed": 2, "upsized": 1, "announced": 1, "terminated": 1})
    ok("facet kinds", {x["kind"]: x["deals"] for x in f["kinds"]}
       == {"PP": 3, "NON_BROKERED": 2, "FT": 1, "BROKERED": 1, "LIFE": 1, "DEBT": 1, "BOUGHT_DEAL": 1})
    ok("facet currencies", {x["currency"]: x["deals"] for x in f["currencies"]} == {"CAD": 4, "USD": 1})
    ok("facet states", f["states"] == {"open": 1, "closed": 4})
    f = query_facets(conn, frozenset({"BBB"}), TODAY)
    ok("facets follow the universe", {x["currency"]: x["deals"] for x in f["currencies"]} == {"USD": 1})

    ok("universe parse", _parse_universe({"tickers": ["aaa", "BBB.V"]}) == frozenset({"AAA", "BBB"})
       and _parse_universe(None) == frozenset())
    ok("names parse prev tickers", _parse_names([{"ticker": "N.V", "name": "New",
                                                  "previous_tickers": [{"ticker": "O.V"}]}]) == {"N.V": "New", "O.V": "New"})

    print("financings_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        if "/opt/mnt/app" not in sys.path and os.path.isdir("/opt/mnt/app"):
            sys.path.insert(0, "/opt/mnt/app")
        sys.exit(_selftest())
    print(__doc__)
