"""MNT Option Payments API v1: read-only JSON for cross-site use (Mine Terminal Pro's "Option payment due" events).

MNT_OPS_API_V1 (C9, 2026-10-12). Serves what OPS_PUBLISH_V1 writes into `land_deal_items`: the payment schedule of each
property option or earn-in a release states, one item per due date (rule calls OE-ON, Justin 2026-10-07).

  /api/v1/option-payments      schedule items, soonest due first

List parameters
  scope      upcoming (default: due today or later, not paid, the deal still live, from the schedule in force, and
               the schedule passed the totals gate OPS_GATE_V1 -- its items add up to the totals the release states)
             | review (upcoming items whose schedule the gate held, with hold_reason: not shown on MTP)
             | all (every item of every release, history included, published or not)
  kind       payment (default) | any | one of KINDS
  ticker     exact symbol (ABC.V) or bare (ABC); an exact symbol ignores namesakes on other exchanges
  days       upcoming only: due within the next N days
  page, limit    1-based page, limit 1..500 (default 100)

Registered from portal.serve via option_payments_api.register(app).
Self-tests: python3 -m portal.option_payments_api --selftest   (in-memory; touches nothing live)
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
from typing import Optional

DB_PATH = "/opt/mnt/app/portal/portal.db"
TICKERS_PATH = "/opt/mnt/app/tickers.json"
SITE_BASE = "https://miningnewsterminal.com"
API_VERSION = "1"
MAX_LIMIT = 500
DEFAULT_LIMIT = 100
KINDS = ("payment", "work", "deadline", "cure", "exercise", "milestone")
SCOPES = ("upcoming", "review", "all")
KIND_LABELS = {"payment": "Option payment due", "work": "Exploration spending due", "deadline": "Option deadline",
               "cure": "Cure period ends", "exercise": "Option exercise price", "milestone": "Milestone payment"}
TYPE_LABELS = {"option_in": "Option in / earn-in", "option_out": "Option out"}
_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")
_COLS = ("ldi_id, event_id, ordinal, seq, ticker, slug, chain_key, deal_type, stage, property, counterparty, due, due_date, "
         "exact, est_from, kind, cash, currency, sh_n, sh_v, work, paid, paid_by, payer, current, live, publish, hold_reason, "
         "raw_headline, published_at")


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
        if isinstance(r, dict) and r.get("ticker"):
            idx[r["ticker"]] = (r.get("name") or "").strip()
    return idx


_names = _FileCache(TICKERS_PATH, _parse_names)


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


def _ops_ai_cols(conn) -> str:
    """MNT_ROYOPS_AI_LIVE_V1 (2026-10-26): ', ai_label' when the connection is the AI reader's hybrid file."""
    try:
        from portal import royops_source
        return royops_source.ai_cols(conn)
    except Exception:  # noqa: BLE001
        return ""


def _headers(max_age: int = 300) -> dict:
    return {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type", "Cache-Control": "public, max-age=%d" % max_age,
            "X-MNT-API-Version": API_VERSION}


class BadRequest(ValueError):
    pass


def parse_params(scope=None, kind=None, ticker=None, days=None, page=None, limit=None, today=None) -> dict:
    p: dict = {"today": (today or _dt.datetime.utcnow().date()).isoformat()}
    sc = (scope or "upcoming").strip().lower()
    if sc not in SCOPES:
        raise BadRequest("scope: upcoming, review or all")
    p["scope"] = sc
    k = (kind or "payment").strip().lower()
    if k != "any" and k not in KINDS:
        raise BadRequest("kind: any, " + ", ".join(KINDS))
    p["kind"] = k
    t = (ticker or "").strip()
    if t:
        if not _TICKER_RE.match(t):
            raise BadRequest("ticker: letters, digits, '.' or '-' only")
        p["ticker"] = t.upper()
    if days not in (None, "", 0, "0"):
        try:
            d = int(days)
        except (TypeError, ValueError):
            raise BadRequest("days: a whole number")
        if d < 0 or d > 36500:
            raise BadRequest("days: 0..36500")
        p["until"] = (_dt.date.fromisoformat(p["today"]) + _dt.timedelta(days=d)).isoformat()
    try:
        p["page"] = max(1, int(page or 1))
        lim = int(limit or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        raise BadRequest("page and limit: whole numbers")
    p["limit"] = max(1, min(lim, MAX_LIMIT))
    return p


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def item(r, names: dict) -> dict:
    t = _s(r["ticker"])
    nm = names.get(t, "")
    k = _s(r["kind"])
    return {
        "id": r["ldi_id"], "event_id": r["event_id"], "ordinal": r["ordinal"], "seq": r["seq"], "ticker": t,
        "bare_ticker": bare(t), "company": "" if nm.upper() in (bare(t), t.upper()) else nm,
        "deal_type": _s(r["deal_type"]), "deal_type_label": TYPE_LABELS.get(_s(r["deal_type"]), _s(r["deal_type"])),
        "stage": _s(r["stage"]), "property": _s(r["property"]), "counterparty": _s(r["counterparty"]),
        "chain_key": _s(r["chain_key"]), "kind": k, "kind_label": KIND_LABELS.get(k, k), "due": _s(r["due"]),
        "due_date": _s(r["due_date"]), "exact": str(r["exact"]) == "1", "estimated_from": _s(r["est_from"]),
        "cash": _num(r["cash"]), "currency": _s(r["currency"]), "shares": _num(r["sh_n"]), "share_value": _num(r["sh_v"]),
        "work": _num(r["work"]), "paid": str(r["paid"]) == "1", "paid_by": _s(r["paid_by"]), "payer": _s(r["payer"]),
        "current": str(r["current"]) == "1", "live": str(r["live"]) == "1",
        "published": str(r["publish"]) == "1", "hold_reason": _s(r["hold_reason"]),
        "date": _s(r["published_at"])[:10], "published_at": _s(r["published_at"]),
        "headline": _title(_s(r["raw_headline"])), "release_url": release_url(t, r["slug"], r["event_id"]),
        "ai_label": (r["ai_label"] if "ai_label" in r.keys() else "") or "",   # MNT_ROYOPS_AI_LIVE_V1
    }


def query(conn, p: dict, names: dict) -> dict:
    sql = "SELECT " + _COLS + _ops_ai_cols(conn) + " FROM land_deal_items WHERE 1=1"   # MNT_ROYOPS_AI_LIVE_V1
    args: list = []
    if p["scope"] in ("upcoming", "review"):
        sql += " AND current = 1 AND live = 1 AND paid = 0 AND due_date IS NOT NULL AND due_date >= ? AND publish = ?"
        args += [p["today"], 1 if p["scope"] == "upcoming" else 0]      # OPS_GATE_V1
        if p.get("until"):
            sql += " AND due_date <= ?"
            args.append(p["until"])
    if p["kind"] != "any":
        sql += " AND kind = ?"
        args.append(p["kind"])
    t = p.get("ticker")
    if t:
        b = bare(t)
        sql += " AND (UPPER(ticker) = ? OR UPPER(ticker) = ? OR UPPER(ticker) LIKE ?)"
        args += [t, b, b + ".%"]
    order = " ORDER BY due_date, ticker, event_id, ordinal, seq" if p["scope"] != "all" else \
        " ORDER BY published_at DESC, event_id, ordinal, seq"
    rows = conn.execute(sql + order, args).fetchall()
    if t and "." in t and any(_s(r["ticker"]).upper() == t for r in rows):
        rows = [r for r in rows if _s(r["ticker"]).upper() == t]
    total, limit, page = len(rows), p["limit"], p["page"]
    return {"ok": True, "api_version": API_VERSION, "total": total, "page": page,
            "pages": max(1, math.ceil(total / limit)) if total else 0, "limit": limit, "scope": p["scope"],
            "filters": {k: p[k] for k in ("kind", "ticker", "until") if p.get(k)},
            "items": [item(r, names) for r in rows[(page - 1) * limit: page * limit]]}


def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    @app.get("/api/v1/option-payments")
    def option_payments_list(scope: Optional[str] = None, kind: Optional[str] = None, ticker: Optional[str] = None,
                             days: Optional[str] = None, page: Optional[str] = None, limit: Optional[str] = None):
        try:
            p = parse_params(scope, kind, ticker, days, page, limit)
        except BadRequest as e:
            return _err(str(e), 400)
        try:   # MNT_ROYOPS_AI_LIVE_V1: the AI reader's hybrid file while option schedules are switched to it
            from portal import royops_source as _ros
            _aic = _ros.ai_conn("land_deal_items")
        except Exception:  # noqa: BLE001
            _aic = None
        with closing(_aic or _conn()) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='land_deal_items'").fetchone():
                return JSONResponse({"ok": True, "api_version": API_VERSION, "total": 0, "page": 1, "pages": 0,
                                     "limit": p["limit"], "scope": p["scope"], "items": []}, headers=_headers())
            out = query(conn, p, _names.get())
        out["reader"] = "hybrid" if _aic is not None else "rules"   # MNT_ROYOPS_AI_LIVE_V1
        return JSONResponse(out, headers=_headers())


def _selftest() -> int:
    fails = []

    def ok(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    sys.path.insert(0, "/opt/mnt/app")
    from portal import options_publish as OP
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(OP.ITEMS_SQL)

    def row(eid, t, due, kind="payment", cash=10000.0, paid=0, current=1, live=1, seq=0, pub="2026-01-05", publish=1):
        conn.execute("INSERT INTO land_deal_items (event_id, ordinal, seq, ticker, slug, chain_key, deal_type, stage, property, "
                     "due, due_date, exact, kind, cash, currency, paid, current, live, publish, hold_reason, raw_headline, published_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, 0, seq, t, "s-" + eid, "ck-" + eid, "option_in", "signed", "Alpha", "x", due, 1, kind, cash, "CAD",
                      paid, current, live, publish, None if publish else "hold:no_total:cash", "HEADLINE " + eid, pub + "T12:00:00"))
    row("a", "ABC.V", "2026-11-01")
    row("a", "ABC.V", "2027-11-01", seq=1)
    row("a", "ABC.V", "2025-11-01", seq=2)                       # past
    row("b", "ABC.CN", "2026-12-01", paid=1)                     # paid
    row("c", "XYZ.V", "2026-10-20", current=0)                   # superseded
    row("d", "XYZ.V", "2026-10-21", live=0)                      # terminated deal
    row("e", "QQQ.V", "2026-10-30", kind="work", cash=None)
    row("h", "HLD.V", "2026-11-15", publish=0)                   # held by the gate
    names = {"ABC.V": "ABC Gold Corp."}
    P = lambda **kw: parse_params(today=_dt.date(2026, 10, 12), **kw)
    r = query(conn, P(), names)
    ok("upcoming payments, soonest first", [(i["event_id"], i["due_date"]) for i in r["items"]] == [("a", "2026-11-01"), ("a", "2027-11-01")])
    i = r["items"][0]
    ok("item shape", i["company"] == "ABC Gold Corp." and i["kind_label"] == "Option payment due" and i["exact"]
       and i["release_url"].endswith("/news/abc.v/s-a") and i["cash"] == 10000.0 and i["live"] and i["current"])
    ok("days", query(conn, P(days="30"), names)["total"] == 1)
    ok("kind any", query(conn, P(kind="any"), names)["total"] == 3)
    ok("scope all", query(conn, P(scope="all", kind="any"), names)["total"] == 8)
    rv = query(conn, P(scope="review"), names)
    ok("review: the held schedule only", [(i["event_id"], i["published"], i["hold_reason"]) for i in rv["items"]] == [("h", False, "hold:no_total:cash")])
    ok("exact listing wins over a namesake", query(conn, P(scope="all", ticker="ABC.V"), names)["total"] == 3)

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad params", bad(scope="x") and bad(kind="x") and bad(ticker="A'--") and bad(days="x"))
    print("option_payments_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
