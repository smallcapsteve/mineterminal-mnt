"""MNT Debt & Credit Facilities API v1: read-only JSON for cross-site use (MTP company pages).

MNT_DEBT_API_V1 (2026-09-25). Serves what DEBT_V1 publishes into `debt_deals`, one item per DEBT: the release
announcing a convertible or a loan, its closing, drawdowns, amendments and its conversion or repayment are one debt
(the publisher's chain_key), shown from its lead row (latest=1, which the publisher has already filled from the chain's
other items; an interest payment is never the lead unless it stands alone), with every stage behind it, interest
payments included. Marker rows (a tagged release with no debt) are skipped.

  /api/v1/debt      debts, newest first, filterable

List parameters
  ticker     exact symbol (FNV.TO) or bare (FNV); an exact symbol ignores namesakes on other exchanges
  scope      tagged (default: the lead release carries the Debt & Credit Facilities tag, as /debt-credit shows)
             | all (also debts read from untagged releases; less checked)
  side       all (default) | borrower (the company borrows) | lender (the company lends or buys debt)
  type       convertible_debenture | convertible_note | loan | credit_facility | notes | gold_loan | prepayment | other
  stage      proposed | signed | closed | drawn | amended | converted | repaid | terminated | interest_paid  (lead row)
  days       only debts whose lead item is in the last N days
  page, limit    1-based page, limit 1..200 (default 50) - counted in debts
  universe   all (default) | mtp -> only companies on MTP's list (fails open)

Registered from portal.serve via debt_api.register(app).
Self-tests: python3 -m portal.debt_api --selftest   (in-memory; touches nothing live)
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
TYPES = ("convertible_debenture", "convertible_note", "loan", "credit_facility", "notes", "gold_loan", "prepayment",
         "other")
STAGES = ("proposed", "signed", "closed", "drawn", "amended", "converted", "repaid", "terminated", "interest_paid")
SCOPES = ("tagged", "all")
SIDES = ("all", "borrower", "lender")
# the publisher's labels, copied so this module imports nothing from the reader
TYPE_LABELS = {"convertible_debenture": "Convertible debenture", "convertible_note": "Convertible note / loan",
               "loan": "Loan", "credit_facility": "Credit facility", "notes": "Notes / bonds",
               "gold_loan": "Gold loan", "prepayment": "Prepayment", "other": "Other debt"}
STAGE_LABELS = {"proposed": "Proposed", "signed": "Signed", "closed": "Closed / funded", "drawn": "Drawdown",
                "amended": "Amended", "converted": "Converted", "repaid": "Repaid / settled",
                "terminated": "Terminated", "interest_paid": "Interest paid"}
SIDE_LABELS = {"borrower": "Company borrowing", "lender": "Company lending"}

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")

_COLS = ("dd_id, event_id, ordinal, ticker, slug, instrument, stage, side, principal, principal_total, currency, "
         "rate_pct, rate_text, maturity, term_months, lender, borrower, related_party, secured, conversion_price, "
         "conversion_text, warrants, warrant_strike, project, purpose, date, chain_key, chain_items, first_reported, "
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


def parse_params(ticker=None, scope=None, side=None, type=None, stage=None, days=None, page=None, limit=None,
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
    sd = (side or "all").strip().lower()
    if sd not in SIDES:
        raise BadRequest("side: all, borrower or lender")
    p["side"] = sd
    ty = (type or "").strip().lower().replace("-", "_")
    if ty:
        if ty not in TYPES:
            raise BadRequest("type: " + ", ".join(TYPES))
        p["type"] = ty
    sg = (stage or "").strip().lower().replace("-", "_")
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


def _flag(v):
    return None if v in (None, "") else str(v) == "1"


def build_debts(rows, names: dict) -> list[dict]:
    """rows in (published_at, event_id, ordinal) order -> debts, newest first."""
    groups: dict[str, list] = {}
    order: list[str] = []
    for r in rows:
        if not r["instrument"]:
            continue                            # marker row: a tagged release with no debt
        k = r["chain_key"] or ("row:%s" % r["dd_id"])
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
            key = (r["event_id"], _s(r["stage"]))
            if key in seen:
                continue
            seen.add(key)
            stages.append({"date": _s(r["published_at"])[:10], "stage": _s(r["stage"]),
                           "stage_label": STAGE_LABELS.get(_s(r["stage"]), _s(r["stage"])),
                           "amount": _num(r["principal"]), "currency": _s(r["currency"]),
                           "note": _s(r["conversion_text"]) if _s(r["stage"]) in ("interest_paid", "converted") else "",
                           "tagged": str(r["tag_confirmed"]) == "1", "headline": _title(_s(r["raw_headline"])),
                           "release_url": release_url(r["ticker"], r["slug"], r["event_id"])})
        ins = _s(last["instrument"])
        sg = _s(last["stage"])
        sd = _s(last["side"]) or "borrower"
        out.append({
            "debt_key": _s(last["chain_key"]) or ("row:%s" % last["dd_id"]), "row_id": last["dd_id"],
            "ticker": t, "bare_ticker": bare(t), "company": company_name(t, names),
            "type": ins, "type_label": TYPE_LABELS.get(ins, "Debt"),
            "stage": sg, "stage_label": STAGE_LABELS.get(sg, sg),
            "side": sd, "side_label": SIDE_LABELS.get(sd, sd),
            "principal": _num(last["principal"]), "principal_total": _num(last["principal_total"]),
            "currency": _s(last["currency"]), "rate_pct": _num(last["rate_pct"]), "rate_text": _s(last["rate_text"]),
            "maturity": _s(last["maturity"]), "term_months": _num(last["term_months"]),
            "lender": _s(last["lender"]), "borrower": _s(last["borrower"]),
            "related_party": _flag(last["related_party"]), "secured": _flag(last["secured"]),
            "conversion_price": _num(last["conversion_price"]), "conversion_text": _s(last["conversion_text"]),
            "warrants": _num(last["warrants"]), "warrant_strike": _num(last["warrant_strike"]),
            "project": _s(last["project"]), "purpose": _s(last["purpose"]), "event_date": _s(last["date"]),
            "tagged": str(last["tag_confirmed"]) == "1",
            "date": _s(last["published_at"])[:10], "published_at": _s(last["published_at"]),
            "first_reported": _s(rs[0]["published_at"])[:10], "releases": len({r["event_id"] for r in rs}),
            "interest_payments": sum(1 for r in rs if _s(r["stage"]) == "interest_paid"),
            "headline": _title(_s(last["raw_headline"])),
            "release_url": release_url(t, last["slug"], last["event_id"]),
            "stages": stages[::-1],
        })
    out.sort(key=lambda x: (x["published_at"], x["row_id"]), reverse=True)
    return out


def query_debts(conn, p: dict, names: dict, universe: Optional[frozenset]) -> dict:
    sql = "SELECT " + _COLS + " FROM debt_deals WHERE instrument IS NOT NULL"
    args: list = []
    t = p.get("ticker")
    if t:
        b = bare(t)
        sql += " AND (UPPER(ticker) = ? OR UPPER(ticker) = ? OR UPPER(ticker) LIKE ?)"
        args += [t, b, b + ".%"]
    rows = conn.execute(sql + " ORDER BY published_at, event_id, ordinal", args).fetchall()
    if t and "." in t and any(_s(r["ticker"]).upper() == t for r in rows):
        rows = [r for r in rows if _s(r["ticker"]).upper() == t]    # the listing asked for, not a namesake
    ds = build_debts(rows, names)
    if p["scope"] == "tagged":
        ds = [x for x in ds if x["tagged"]]        # same rule as /debt-credit: the lead release is tagged
    if universe and not t:
        ds = [x for x in ds if x["bare_ticker"] in universe]
    if p["side"] != "all":
        ds = [x for x in ds if x["side"] == p["side"]]
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
        "scope": p["scope"], "side": p["side"], "universe": p["universe"],
        "universe_applied": bool(universe) and not t,
        "items": ds[(page - 1) * limit: page * limit],
    }


# --------------------------------------------------------------------------- web

def register(app) -> None:
    from fastapi.responses import JSONResponse

    def _err(msg: str, status: int) -> JSONResponse:
        return JSONResponse({"ok": False, "error": msg}, status_code=status, headers=_headers(60))

    @app.get("/api/v1/debt")
    def debt_list(ticker: Optional[str] = None, scope: Optional[str] = None, side: Optional[str] = None,
                  type: Optional[str] = None, stage: Optional[str] = None, days: Optional[str] = None,
                  page: Optional[str] = None, limit: Optional[str] = None, universe: Optional[str] = None):
        try:
            p = parse_params(ticker, scope, side, type, stage, days, page, limit, universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = None
        if p["universe"] == "mtp":
            uni = _universe.get() or None
        with closing(_conn()) as conn:
            have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='debt_deals'").fetchone()
            if not have:
                return JSONResponse({"ok": True, "api_version": API_VERSION, "total": 0, "page": 1, "pages": 0,
                                     "limit": p["limit"], "scope": p["scope"], "items": []}, headers=_headers())
            out = query_debts(conn, p, _names.get(), uni)
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
    CREATE TABLE debt_deals (dd_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL DEFAULT 0, ticker TEXT, slug TEXT, instrument TEXT, stage TEXT, side TEXT,
        principal REAL, principal_total REAL, currency TEXT, rate_pct REAL, rate_text TEXT, maturity TEXT,
        term_months REAL, lender TEXT, borrower TEXT, related_party INTEGER, secured INTEGER, conversion_price REAL,
        conversion_text TEXT, warrants REAL, warrant_strike REAL, project TEXT, purpose TEXT, date TEXT,
        filled_from TEXT, chain_key TEXT, chain_items INTEGER NOT NULL DEFAULT 1, first_reported TEXT,
        stage_rank INTEGER, latest INTEGER NOT NULL DEFAULT 1, n_rows INTEGER NOT NULL DEFAULT 1,
        tag_confirmed INTEGER NOT NULL DEFAULT 0, raw_headline TEXT, published_at TEXT, extractor_version TEXT);
    """)

    def row(eid, t, date, ins="loan", stage="closed", key=None, latest=1, side="borrower", tagged=1, principal=None,
            cur=None, rate=None, maturity=None, lender=None, borrower=None, secured=None, conv=None, ctext=None,
            ordinal=0):
        conn.execute("INSERT INTO debt_deals (event_id, ordinal, ticker, slug, instrument, stage, side, principal, "
                     "currency, rate_pct, maturity, lender, borrower, secured, conversion_price, conversion_text, "
                     "date, chain_key, latest, tag_confirmed, raw_headline, published_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, ordinal, t, "s-" + eid, ins, None if ins is None else stage, side, principal, cur, rate,
                      maturity, lender, borrower, secured, conv, ctext, date, key, latest, tagged,
                      "HEADLINE " + eid, date + "T12:00:00"))

    # one convertible: closed -> interest paid -> converted (the publisher filled the lead's terms)
    row("c1", "ABC.V", "2025-01-10", ins="convertible_debenture", key="ABC.V:B:conv#1", latest=0, principal=1e6,
        cur="CAD", rate=10.0, maturity="2027-01-10", secured=0, conv=0.10)
    row("c2", "ABC.V", "2025-12-31", ins="convertible_debenture", stage="interest_paid", key="ABC.V:B:conv#1",
        latest=0, principal=5e4, cur="CAD", ctext="interest paid in 500,000 shares")
    row("c3", "ABC.V", "2026-06-01", ins="convertible_debenture", stage="converted", key="ABC.V:B:conv#1",
        principal=1e6, cur="CAD", rate=10.0, maturity="2027-01-10", secured=0, conv=0.10)
    row("l1", "ABC.V", "2026-06-01", ins="loan", stage="closed", key="ABC.V:L:loan:cp=target#2", side="lender",
        principal=2e6, cur="CAD", borrower="Target Co", ordinal=1)
    row("m0", "ABC.V", "2026-02-01", ins=None)                                                   # marker
    row("u1", "ABC.V", "2026-07-01", ins="credit_facility", stage="signed", key="ABC.V:B:loan:cp=omega#3",
        lender="Omega Bank", tagged=0)                                                            # untagged
    row("f1", "FNV.TO", "2026-09-10", ins="credit_facility", stage="amended", key="FNV.TO:B:loan#4",
        principal=1.5e9, cur="USD", lender="Syndicate of banks", secured=0)
    row("x1", "ABC.CN", "2026-02-02", ins="notes", stage="closed", key="ABC.CN:B:notes#5", principal=1e5)
    names = {"ABC.V": "ABC Gold Corp.", "FNV.TO": "Franco-Nevada Corporation"}
    P = lambda **kw: parse_params(today=_dt.date(2026, 9, 25), **kw)

    r = query_debts(conn, P(), names, None)
    ok("one item per debt, tagged only, newest first, markers skipped",
       [x["type"] for x in r["items"]] == ["credit_facility", "loan", "convertible_debenture", "notes"]
       and r["total"] == 4)
    cv = [x for x in r["items"] if x["type"] == "convertible_debenture"][0]
    ok("the lead row leads; interest payment is a stage, not the lead",
       cv["stage"] == "converted" and cv["releases"] == 3 and cv["interest_payments"] == 1
       and cv["first_reported"] == "2025-01-10" and cv["conversion_price"] == 0.1 and cv["secured"] is False
       and [s["stage"] for s in cv["stages"]] == ["converted", "interest_paid", "closed"]
       and cv["stages"][1]["amount"] == 5e4 and cv["stages"][1]["note"].startswith("interest paid")
       and cv["release_url"].endswith("/news/abc.v/s-c3"))
    ln = [x for x in r["items"] if x["type"] == "loan"][0]
    ok("lender rows carry the side", ln["side"] == "lender" and ln["side_label"] == "Company lending"
       and ln["borrower"] == "Target Co")
    ok("side filter", query_debts(conn, P(side="lender"), names, None)["total"] == 1
       and query_debts(conn, P(side="borrower"), names, None)["total"] == 3)
    ok("scope=all adds untagged", query_debts(conn, P(scope="all"), names, None)["total"] == 5)
    ok("exact listing wins over a namesake", query_debts(conn, P(ticker="ABC.V"), names, None)["total"] == 2)
    ok("bare ticker matches both", query_debts(conn, P(ticker="ABC"), names, None)["total"] == 3)
    ok("type / stage filters", query_debts(conn, P(type="credit-facility"), names, None)["total"] == 1
       and query_debts(conn, P(stage="converted"), names, None)["total"] == 1
       and query_debts(conn, P(stage="signed", scope="all"), names, None)["items"][0]["lender"] == "Omega Bank")
    ok("universe", query_debts(conn, P(universe="mtp"), names, frozenset({"FNV"}))["total"] == 1)
    ok("days", query_debts(conn, P(days="30"), names, None)["total"] == 1)
    ok("company names", r["items"][0]["company"] == "Franco-Nevada Corporation" and r["items"][0]["principal"] == 1.5e9)

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad params", bad(type="x") and bad(stage="x") and bad(ticker="A'--") and bad(universe="x")
       and bad(scope="x") and bad(side="x"))
    print("debt_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        if "/opt/mnt/app" not in sys.path and os.path.isdir("/opt/mnt/app"):
            sys.path.insert(0, "/opt/mnt/app")
        sys.exit(_selftest())
    print(__doc__)
