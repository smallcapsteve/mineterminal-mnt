"""MNT Economic Studies API v1: read-only JSON for cross-site use (MTP company pages).

MNT_ECONOMICS_API_V1 (2026-09-21). Serves what ECON_V1 publishes into `economic_studies`, grouped
the way a company page needs it: one item per STUDY, not per release.

  /api/v1/economics      studies, newest first, filterable

Why grouped: about four releases in five that state economics are restating an old study (a PEA
repeated in every news release for two years). A company page listing each restatement would show
the same NPV twenty times. So releases whose base-case figures match are one study; the item is the
release that announced it (or, when the announcement predates our coverage, the earliest release
that carried it), and says how many later releases restated it.

List parameters
  ticker     exact symbol (NCF.TO) or bare (NCF)
  study      PEA | PFS | FS
  days       only studies first seen in the last N days
  page, limit    1-based page, limit 1..100 (default 20) - counted in studies
  universe   all (default) | mtp -> only companies on MTP's list (fails open, like the other APIs)

Each study carries its scenarios (base, spot, named price decks) with after-tax and pre-tax NPV,
the discount rate, IRR, initial capex, payback, AISC and mine life, in the study's own currency.
Rows attributed to another company's study (other_owner) and marker rows with no figures are left
out. A project name that is plainly not a name ("PEA outlines an open") is dropped rather than shown.

Registered from portal.serve via economics_api.register(app).
Self-tests: python3 -m portal.economics_api --selftest   (in-memory; touches nothing live)
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
IRR_TOL = 0.5          # IRR points two releases of one study may differ by (rounding)
MAX_LIMIT = 100
DEFAULT_LIMIT = 20
STUDIES = ("PEA", "PFS", "FS")

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,16}$")

_COLS = ("event_id, ordinal, ticker, slug, raw_headline, published_at, project, study_type, context, "
         "scenario, basis, currency, discount_pct, npv_pre_tax, npv_after_tax, irr_pre_tax_pct, "
         "irr_after_tax_pct, payback_years, initial_capex, capex_sensitivity, aisc, aisc_unit, "
         "mine_life_years, tag_confirmed")


# --------------------------------------------------------------------------- helpers (pure)

def bare(ticker: Optional[str]) -> str:
    return (ticker or "").strip().upper().split(".")[0]


_NOT_A_NAME = re.compile(r"\b(PEA|PFS|FS|feasibility|study|economic|outlines?|operationali[sz]ed)\b", re.I)


def clean_project(p: Optional[str]) -> str:
    """A project name, or '' when the reader picked up words that are plainly not one."""
    s = (p or "").strip()
    if not s:
        return ""
    if s[0].islower() or _NOT_A_NAME.search(s):
        return ""
    return s


def _sig(v, digits=3):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v == 0 or not math.isfinite(v):
        return v
    return round(v, -int(math.floor(math.log10(abs(v)))) + (digits - 1))


def fingerprint(ticker: str, study_type: Optional[str], base: dict) -> Optional[tuple]:
    """Two releases carry the same study when the base case's after-tax NPV (to three significant
    figures), IRR (to 0.1) and discount rate agree for the same company and study type. With neither
    NPV nor IRR there is nothing to match on, and the release stands alone."""
    npv, irr = _sig(base.get("npv_after_tax")), base.get("irr_after_tax_pct")
    if npv is None and irr is None:
        return None
    return (bare(ticker), (study_type or "").upper(), npv,
            None if irr is None else round(float(irr), 1), base.get("discount_pct"))


def release_url(ticker: Optional[str], slug: Optional[str], event_id: Optional[str]) -> str:
    t, sl = (ticker or "").strip(), (slug or "").strip()
    if t and sl:
        return f"{SITE_BASE}/news/{t.lower()}/{sl}"
    return f"{SITE_BASE}/event/{event_id}" if event_id else ""


class BadRequest(ValueError):
    pass


def parse_params(ticker=None, study=None, days=None, page=None, limit=None, universe=None,
                 today=None) -> dict:
    p: dict[str, Any] = {}
    t = (ticker or "").strip()
    if t:
        if not _TICKER_RE.match(t):
            raise BadRequest("ticker: letters, digits, '.' or '-' only")
        p["ticker"] = t.upper()
    st = (study or "").strip().upper()
    if st:
        if st not in STUDIES:
            raise BadRequest("study: PEA, PFS or FS")
        p["study"] = st
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


# --------------------------------------------------------------------------- cached side data

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


# --------------------------------------------------------------------------- queries

def _scenario(r) -> dict:
    return {
        "scenario": r["scenario"] or "",
        "basis": r["basis"] or "",
        "currency": (r["currency"] or "").upper(),
        "discount_pct": r["discount_pct"],
        "npv_after_tax": r["npv_after_tax"],
        "npv_pre_tax": r["npv_pre_tax"],
        "irr_after_tax_pct": r["irr_after_tax_pct"],
        "irr_pre_tax_pct": r["irr_pre_tax_pct"],
        "initial_capex": r["initial_capex"],
        "capex_sensitivity": r["capex_sensitivity"],
        "payback_years": r["payback_years"],
        "aisc": r["aisc"],
        "aisc_unit": r["aisc_unit"] or "",
        "mine_life_years": r["mine_life_years"],
    }


_STAGE = {"PEA": 0, "PFS": 1, "FS": 2}
_NOT_RESULT = re.compile(r"commenc|update|begin|initiat|launch|underway|progress|toward|contract|award|"
                         r"engag|\bstart|\bplans?\b|expect|to complete|\bwork", re.I)
# Checked by hand against the company's own release where the releases we hold cannot settle the type:
# (bare ticker, after-tax NPV to three significant figures) -> type.
TYPE_OVERRIDES = {
    ("GPH", 5.03e9): "FS",     # Graphite One bankable feasibility study, 2025 (our releases label it PFS/FS)
}


def _headline_type(headline: Optional[str]) -> str:
    """The study type a headline announces, or ''. 'Commences feasibility study' and 'provides DFS update'
    announce nothing."""
    h = (headline or "")
    if not h or _NOT_RESULT.search(h):
        return ""
    low = h.lower()
    if re.search(r"pre[- ]?feasibility|\bpfs\b", low):
        return "PFS"
    if re.search(r"\bpea\b|preliminary economic assessment", low):
        return "PEA"
    if re.search(r"feasibility|\bdfs\b|\bbfs\b|\bfs\b", low):
        return "FS"
    return ""


def _study_type(members: list) -> str:
    """members: (published_at, label, announced, headline) in date order. When the releases of one study
    disagree on its type, the announcement whose headline names that same type decides; otherwise the
    earliest-stage label wins, because a restatement is mislabelled toward the study the company is
    working on next (a PFS restated in a 'DFS update'), not back toward an earlier one."""
    labels = {m[1] for m in members if m[1]}
    if len(labels) <= 1:
        return next(iter(labels), "")
    for _, label, announced, headline in members:
        if announced and label and _headline_type(headline) == label:
            return label
    return min(labels, key=lambda x: _STAGE.get(x, 9))


_FILL = ("discount_pct", "npv_pre_tax", "irr_after_tax_pct", "irr_pre_tax_pct", "initial_capex", "payback_years",
         "aisc", "mine_life_years")


def _filled(rep: dict, rels: list) -> list:
    """The representative release's scenarios, with gaps in its base case filled from the other releases
    of the same study (earliest first, same currency): an announcement headline often carries NPV and IRR
    while a later restatement gives capex and mine life."""
    out = [dict(x) for x in rep["scenarios"]]
    if not out:
        return out
    base = out[0]
    for other in rels:
        if other is rep or not other["scenarios"]:
            continue
        ob = other["scenarios"][0]
        if base["currency"] and ob["currency"] and base["currency"] != ob["currency"]:
            continue
        for k in _FILL:
            if base.get(k) is None and ob.get(k) is not None:
                base[k] = ob[k]
                if k == "aisc":
                    base["aisc_unit"] = ob.get("aisc_unit") or base.get("aisc_unit") or ""
    return out


def build_studies(rows, names: dict) -> list[dict]:
    """rows in (published_at, event_id, ordinal) order -> studies, newest first."""
    releases: dict[str, dict] = {}
    order: list[str] = []
    for r in rows:
        eid = r["event_id"]
        rel = releases.get(eid)
        if rel is None:
            rel = releases[eid] = {
                "event_id": eid, "ticker": (r["ticker"] or "").strip(), "slug": r["slug"],
                "headline": r["raw_headline"], "published_at": r["published_at"] or "",
                "study_type": None, "project": "", "announced": False, "scenarios": []}
            order.append(eid)
        if r["context"] == "announced":
            rel["announced"] = True
        if not rel["study_type"] and r["study_type"]:
            rel["study_type"] = r["study_type"]
        if not rel["project"]:
            rel["project"] = clean_project(r["project"])
        rel["scenarios"].append(_scenario(r))

    # Matching (v1.2, 2026-09-21). A study's after-tax NPV to three significant figures is close to
    # unique within one company, so releases that share it are the same study when their IRRs agree to
    # within 0.5 points (restatements round: 61.2% vs 61%) and their discount rates agree where both
    # state one. The study TYPE is not part of the match: restatements are often labelled with the study
    # the company is working on next ("provides DFS update" restating PFS figures); _study_type() settles
    # the type. With no NPV, releases match on IRR (to 0.1) and a compatible type, as before.
    studies: list[dict] = []
    by_key: dict[Any, list] = {}
    for eid in order:                      # chronological
        rel = releases[eid]
        base = rel["scenarios"][0] if rel["scenarios"] else {}
        fp = fingerprint(rel["ticker"], rel["study_type"], base) if rel["scenarios"] else None
        st, key = None, None
        if fp is not None:
            tk, typ, npv, irr, disc = fp
            key = (tk, "npv", npv) if npv is not None else (tk, "irr", irr)
            for cand in by_key.get(key, []):
                if npv is not None:
                    ok_irr = irr is None or cand["irr"] is None or abs(irr - cand["irr"]) <= IRR_TOL + 1e-9
                    ok_typ = True
                else:
                    ok_irr = True
                    ok_typ = not typ or not cand["type"] or typ == cand["type"]
                ok_disc = disc is None or cand["disc"] is None or float(disc) == float(cand["disc"])
                if ok_irr and ok_typ and ok_disc:
                    st = cand
                    break
        if st is None:
            st = {"rep": rel, "first": rel["published_at"], "last": rel["published_at"], "n": 1,
                  "type": fp[1] if fp else (rel["study_type"] or "").upper(), "irr": fp[3] if fp else None,
                  "disc": fp[4] if fp else None, "project": rel["project"], "labels": set(), "members": [],
                  "rels": [rel]}
            if st["type"]:
                st["labels"].add(st["type"])
            st["members"].append((rel["published_at"], st["type"], rel["announced"], rel["headline"]))
            studies.append(st)
            if key is not None:
                by_key.setdefault(key, []).append(st)
            continue
        typ = fp[1]
        if typ:
            st["labels"].add(typ)
        st["members"].append((rel["published_at"], typ or "", rel["announced"], rel["headline"]))
        st["rels"].append(rel)
        st["irr"] = st["irr"] if st["irr"] is not None else fp[3]
        st["disc"] = st["disc"] if st["disc"] is not None else fp[4]
        st["project"] = st["project"] or rel["project"]
        st["n"] += 1
        st["last"] = rel["published_at"]
        # the announcement is the best source; before it, the earliest release that carried the study
        if rel["announced"] and not st["rep"]["announced"]:
            st["rep"] = rel

    out = []
    for st in studies:
        st["type"] = _study_type(st["members"]) or st["type"]
        rel = st["rep"]
        base = rel["scenarios"][0] if rel["scenarios"] else {}
        st["type"] = TYPE_OVERRIDES.get((bare(rel["ticker"]), _sig(base.get("npv_after_tax"))), st["type"])
        t = rel["ticker"]
        out.append({
            "study_id": rel["event_id"],
            "ticker": t,
            "bare_ticker": bare(t),
            "company": company_name(t, names),
            "study_type": st["type"] or "",
            "other_labels": sorted(st["labels"] - {st["type"]}),
            "project": rel["project"] or st["project"] or "",
            "source": "announced" if rel["announced"] else "restated",
            "date": rel["published_at"][:10],
            "published_at": rel["published_at"],
            "first_seen": st["first"][:10],
            "last_seen": st["last"][:10],
            "releases": st["n"],
            "restated": st["n"] - 1,
            "headline": _title(rel["headline"] or ""),
            "release_url": release_url(t, rel["slug"], rel["event_id"]),
            "scenarios": _filled(rel, st["rels"]),
        })
    out.sort(key=lambda s: (s["published_at"], s["study_id"]), reverse=True)
    return out


def query_studies(conn, p: dict, names: dict, universe: Optional[frozenset]) -> dict:
    where = ["scenario IS NOT NULL", "(other_owner IS NULL OR other_owner = '')"]
    args: list = []
    t = p.get("ticker")
    if t:
        where.append("(upper(ticker) = ? OR upper(ticker) LIKE ?)")
        args += [t, bare(t) + ".%"]
    if universe:
        where.append("(CASE WHEN instr(ticker, '.') > 0 THEN upper(substr(ticker, 1, instr(ticker, '.') - 1)) "
                     "ELSE upper(ticker) END) IN (SELECT value FROM json_each(?))")
        args.append(json.dumps(sorted(universe)))
    rows = conn.execute("SELECT " + _COLS + " FROM economic_studies WHERE " + " AND ".join(where) +
                        " ORDER BY published_at, event_id, ordinal", args).fetchall()
    studies = build_studies(rows, names)
    if p.get("since"):
        studies = [s for s in studies if s["date"] >= p["since"]]
    if p.get("study"):                     # on the study's own type, after grouping (v1.2)
        studies = [s for s in studies if s["study_type"] == p["study"]]
    total, limit, page = len(studies), p["limit"], p["page"]
    items = studies[(page - 1) * limit: page * limit]
    return {
        "ok": True,
        "api_version": API_VERSION,
        "total": total,
        "page": page,
        "pages": max(1, math.ceil(total / limit)) if total else 0,
        "limit": limit,
        "filters": {k: p[k] for k in ("ticker", "study", "since") if p.get(k)},
        "universe": p["universe"],
        "universe_applied": bool(universe),
        "items": items,
    }


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

    @app.get("/api/v1/economics")
    def economics_list(ticker: Optional[str] = None, study: Optional[str] = None,
                       days: Optional[str] = None, page: Optional[str] = None,
                       limit: Optional[str] = None, universe: Optional[str] = None):
        try:
            p = parse_params(ticker, study, days, page, limit, universe)
        except BadRequest as e:
            return _err(str(e), 400)
        uni = None
        if p["universe"] == "mtp":
            uni = _universe.get() or None
        with closing(_conn()) as conn:
            have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='economic_studies'").fetchone()
            if not have:
                return JSONResponse({"ok": True, "api_version": API_VERSION, "total": 0, "page": 1, "pages": 0,
                                     "limit": p["limit"], "items": []}, headers=_headers())
            out = query_studies(conn, p, _names.get(), uni)
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
    CREATE TABLE economic_studies (es_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL DEFAULT 0, ticker TEXT, slug TEXT, project TEXT, study_type TEXT,
        context TEXT, scenario TEXT, basis TEXT, currency TEXT, discount_pct REAL, npv_pre_tax REAL,
        npv_after_tax REAL, irr_pre_tax_pct REAL, irr_after_tax_pct REAL, payback_years REAL,
        initial_capex REAL, capex_sensitivity REAL, opex REAL, opex_unit TEXT, aisc REAL, aisc_unit TEXT,
        mine_life_years REAL, throughput_tpd REAL, annual_production REAL, production_unit TEXT,
        n_rows INTEGER NOT NULL DEFAULT 1, tag_confirmed INTEGER NOT NULL DEFAULT 0, raw_headline TEXT,
        published_at TEXT, other_owner TEXT, extractor_version TEXT);
    """)

    def row(eid, t, date, ordn=0, ctx="announced", st="PEA", project="Big Creek", scen="base case",
            npv=500e6, irr=25.0, disc=8.0, cur="USD", capex=300e6, other=None, head="ACME ANNOUNCES PEA"):
        conn.execute("INSERT INTO economic_studies (event_id, ordinal, ticker, slug, project, study_type, context, "
                     "scenario, basis, currency, discount_pct, npv_pre_tax, npv_after_tax, irr_pre_tax_pct, "
                     "irr_after_tax_pct, payback_years, initial_capex, aisc, aisc_unit, mine_life_years, "
                     "raw_headline, published_at, other_owner) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (eid, ordn, t, "s-" + eid, project, st, ctx, scen, "real", cur, disc,
                      None if npv is None else npv * 1.4, npv, None if irr is None else irr + 5, irr, 2.5, capex,
                      1100.0, "/oz", 12.0, head, date + "T12:00:00", other))

    # AAA.V: a PEA announced 2025-01-10 with a base and a spot case, then restated twice word for word
    row("a1", "AAA.V", "2025-01-10"); row("a1", "AAA.V", "2025-01-10", ordn=1, scen="spot", npv=800e6, irr=35.0)
    row("a2", "AAA.V", "2025-03-01", ctx="background")
    row("a3", "AAA.V", "2025-06-01", ctx="background", npv=500.4e6)       # same to three figures
    # AAA.V: then a PFS with different numbers, announced 2026-02-01
    row("a4", "AAA.V", "2026-02-01", st="PFS", npv=700e6, irr=28.0)
    # BBB.CN: we only ever saw the study restated - the announcement predates coverage
    row("b1", "BBB.CN", "2025-05-05", ctx="background", st="FS", project="operationalized PEA", npv=1.2e9, irr=40.0)
    row("b2", "BBB.CN", "2025-09-09", ctx="background", st="FS", npv=1.2e9, irr=40.0)
    # CCC.TO: the restatement arrives before the announcement row in our data (announcement back-filled)
    row("c1", "CCC.TO", "2024-11-01", ctx="background", npv=90e6, irr=18.0, project="Sisson")
    row("c2", "CCC.TO", "2024-12-01", ctx="announced", npv=90e6, irr=18.0, project="Sisson")
    # DDD.V: no NPV or IRR - nothing to match on, each stands alone
    row("d1", "DDD.V", "2026-01-01", npv=None, irr=None, capex=50e6)
    row("d2", "DDD.V", "2026-02-01", npv=None, irr=None, capex=50e6)
    # EEE.V: someone else's study, and a marker row with no scenario
    row("e1", "EEE.V", "2026-03-01", other="Surge Battery Metals")
    conn.execute("INSERT INTO economic_studies (event_id, ticker, context, published_at) VALUES ('e2','EEE.V','', '2026-03-02')")

    names = {"AAA.V": "Acme Gold Corp.", "BBB.CN": "Bbb", "CCC.TO": "Cee Metals"}
    P = lambda **kw: parse_params(today=_dt.date(2026, 9, 21), **kw)

    ok("clean project keeps a name", clean_project("Big Creek") == "Big Creek" and clean_project("SISSON") == "SISSON")
    ok("clean project drops junk", clean_project("PEA outlines an open") == "" and clean_project("operationalized PEA") == ""
       and clean_project("the project") == "" and clean_project(None) == "")
    ok("sig figs", _sig(500.4e6) == 500e6 and _sig(1234) == 1230 and _sig(None) is None)
    ok("fingerprint needs a figure", fingerprint("A.V", "PEA", {"npv_after_tax": None, "irr_after_tax_pct": None}) is None)

    def bad(**kw):
        try:
            parse_params(**kw)
            return False
        except BadRequest:
            return True
    ok("bad study", bad(study="scoping"))
    ok("bad ticker", bad(ticker="A'--"))
    ok("bad universe", bad(universe="x"))
    ok("limit capped", P(limit="999")["limit"] == MAX_LIMIT)

    r = query_studies(conn, P(ticker="AAA"), names, None)
    ids = [s["study_id"] for s in r["items"]]
    ok("restatements fold into one study", ids == ["a4", "a1"] and r["total"] == 2)
    pea = r["items"][1]
    ok("the study is the announcement, with its count of restatements",
       pea["source"] == "announced" and pea["releases"] == 3 and pea["restated"] == 2
       and pea["first_seen"] == "2025-01-10" and pea["last_seen"] == "2025-06-01")
    ok("scenarios kept in order", [x["scenario"] for x in pea["scenarios"]] == ["base case", "spot"]
       and pea["scenarios"][1]["npv_after_tax"] == 800e6)
    ok("fields", pea["company"] == "Acme Gold Corp." and pea["study_type"] == "PEA" and pea["project"] == "Big Creek"
       and pea["scenarios"][0]["currency"] == "USD" and pea["scenarios"][0]["aisc_unit"] == "/oz")
    ok("release url", pea["release_url"] == SITE_BASE + "/news/aaa.v/s-a1")
    ok("a new study with new numbers is its own item", r["items"][0]["study_type"] == "PFS")
    r = query_studies(conn, P(ticker="BBB.CN"), names, None)
    ok("seen only restated: source says so", r["total"] == 1 and r["items"][0]["source"] == "restated"
       and r["items"][0]["study_id"] == "b1" and r["items"][0]["releases"] == 2)
    ok("junk project name dropped, a later release's real one used", r["items"][0]["project"] == "Big Creek")
    ok("stub company name dropped", r["items"][0]["company"] == "")

    r = query_studies(conn, P(ticker="CCC"), names, None)
    ok("an announcement outranks an earlier restatement", r["total"] == 1 and r["items"][0]["study_id"] == "c2"
       and r["items"][0]["source"] == "announced" and r["items"][0]["first_seen"] == "2024-11-01")

    r = query_studies(conn, P(ticker="DDD"), names, None)
    ok("no figures to match: each release stands alone", r["total"] == 2)

    r = query_studies(conn, P(ticker="EEE"), names, None)
    ok("someone else's study and marker rows are left out", r["total"] == 0 and r["items"] == [])

    r = query_studies(conn, P(), names, None)
    ok("everything, newest first (same-day ties by id)", [s["study_id"] for s in r["items"]] == ["d2", "a4", "d1", "b1", "a1", "c2"])
    r = query_studies(conn, P(study="pfs"), names, None)
    ok("study filter", [s["study_id"] for s in r["items"]] == ["a4"])
    r = query_studies(conn, P(days="300"), names, None)
    ok("days filter on the study date", [s["study_id"] for s in r["items"]] == ["d2", "a4", "d1"])
    r = query_studies(conn, P(limit="2", page="2"), names, None)
    ok("paging counts studies", [s["study_id"] for s in r["items"]] == ["d1", "b1"] and r["pages"] == 3)
    r = query_studies(conn, P(universe="mtp"), names, frozenset({"AAA", "CCC"}))
    ok("universe", [s["study_id"] for s in r["items"]] == ["a4", "a1", "c2"] and r["universe_applied"])

    # FFF.TO: the announcement states FS at 5%; a later release restates the same NPV/IRR with no type or rate
    row("f1", "FFF.TO", "2026-05-27", st="FS", npv=984e6, irr=61.2, disc=5.0, project="Cabacal", head="FFF Feasibility Study Results")
    row("f2", "FFF.TO", "2026-06-01", ctx="background", st="", npv=984e6, irr=61.2, disc=None, project="")
    # ...a later release labels the same figures PEA (mislabelled) and one rounds IRR to 61%: all one study
    row("f3", "FFF.TO", "2026-07-01", st="PEA", npv=984e6, irr=61.2, disc=5.0, head="FFF Corporate Update")
    row("f4", "FFF.TO", "2026-08-01", ctx="background", st="FS", npv=984e6, irr=61.0, disc=5.0)
    # ...and a genuinely new study (new NPV) stays separate
    row("f5", "FFF.TO", "2026-09-01", st="FS", npv=1.31e9, irr=48.0, disc=5.0)
    r = query_studies(conn, P(ticker="FFF.TO"), names, None)
    ok("same NPV and IRR within 0.5: one study whatever the label", [s["study_id"] for s in r["items"]] == ["f5", "f1"]
       and r["items"][1]["releases"] == 4 and r["items"][1]["study_type"] == "FS"
       and r["items"][1]["other_labels"] == ["PEA"])
    ok("study filter uses the study's own type", [s["study_id"] for s in query_studies(conn, P(ticker="FFF.TO", study="pea"), names, None)["items"]] == [])
    # HHH.V: the PFS is announced first; later "DFS update" releases restate its figures labelled FS
    row("h1", "HHH.V", "2025-03-10", st="PFS", npv=984e6, irr=61.2, disc=5.0, head="HHH Pre-Feasibility Study Delivers US$984M NPV")
    row("h2", "HHH.V", "2025-04-15", ctx="background", st="FS", npv=984e6, irr=61.2, disc=5.0)
    row("h3", "HHH.V", "2026-05-27", ctx="announced", st="FS", npv=984e6, irr=61.2, disc=5.0, head="HHH Provides DFS Update")
    row("h4", "HHH.V", "2026-04-27", ctx="background", st="", npv=984e6, irr=61.0, disc=None)
    r = query_studies(conn, P(ticker="HHH.V"), names, None)
    ok("the original announcement and its label win", r["total"] == 1 and r["items"][0]["study_id"] == "h1"
       and r["items"][0]["study_type"] == "PFS" and r["items"][0]["releases"] == 4 and r["items"][0]["other_labels"] == ["FS"])
    # JJJ.V: first seen labelled FS in a restatement, later PEA; no announcement names it - the earlier stage wins
    row("j1", "JJJ.V", "2025-01-08", ctx="background", st="FS", npv=1.1e9, irr=86.0, head="JJJ Royalties Update On Principal Asset")
    row("j2", "JJJ.V", "2025-02-20", ctx="background", st="PEA", npv=1.1e9, irr=86.0, head="JJJ Files Technical Report")
    r = query_studies(conn, P(ticker="JJJ.V"), names, None)
    ok("no deciding announcement: earliest-stage label", r["total"] == 1 and r["items"][0]["study_type"] == "PEA"
       and r["items"][0]["other_labels"] == ["FS"])
    # KKK.V: the real FS announcement outranks an earlier PFS label in a restatement
    row("k1", "KKK.V", "2025-01-01", ctx="background", st="PFS", npv=5.03e9, irr=27.0)
    row("k2", "KKK.V", "2025-03-01", ctx="announced", st="FS", npv=5.03e9, irr=27.0, head="KKK Announces Positive Feasibility Study")
    ok("an announcement naming the type decides", query_studies(conn, P(ticker="KKK.V"), names, None)["items"][0]["study_type"] == "FS")
    ok("headline types", _headline_type("Avalon Announces the Commencement of Feasibility Study") == ""
       and _headline_type("Graphite One Advances its Supply Chain with Completion of a Bankable Feasibility Study") == "FS"
       and _headline_type("Canadian Copper Discusses the Murray Brook Project and Past-Producing Caribou Plant PEA") == "PEA"
       and _headline_type("Meridian's Cabacal Pre-Feasibility Study Delivers") == "PFS"
       and _headline_type("RPX Gold Delivers Robust Preliminary Economic Assessment") == "PEA"
       and _headline_type("Positive Definitive Feasibility Study") == "FS")
    # LLL.V: the announcement has NPV/IRR only; a restatement adds capex and mine life -> filled in
    conn.execute("INSERT INTO economic_studies (event_id, ticker, slug, study_type, context, scenario, currency, "
                 "npv_after_tax, irr_after_tax_pct, raw_headline, published_at) VALUES "
                 "('l1','LLL.V','s-l1','PFS','announced','base case','USD',984e6,61.2,'LLL PFS Delivers','2025-03-10T12:00:00')")
    row("l2", "LLL.V", "2025-06-01", ctx="background", st="FS", npv=984e6, irr=61.0, disc=None, capex=248e6)
    r = query_studies(conn, P(ticker="LLL.V"), names, None)["items"]
    ok("base case gaps filled from restatements", len(r) == 1 and r[0]["study_id"] == "l1"
       and r[0]["scenarios"][0]["initial_capex"] == 248e6 and r[0]["scenarios"][0]["mine_life_years"] == 12.0
       and r[0]["scenarios"][0]["irr_after_tax_pct"] == 61.2 and r[0]["scenarios"][0]["aisc_unit"] == "/oz")
    # III.V: same NPV but IRR 5 points apart - not the same study
    row("i1", "III.V", "2025-01-01", npv=200e6, irr=20.0)
    row("i2", "III.V", "2026-01-01", npv=200e6, irr=25.0)
    ok("IRR far apart stays separate", query_studies(conn, P(ticker="III.V"), names, None)["total"] == 2)
    # GGG.V: the only release we have left out the type; a later one names it
    row("g1", "GGG.V", "2026-01-01", ctx="background", st="", npv=50e6, irr=20.0, disc=None, project="")
    row("g2", "GGG.V", "2026-02-01", ctx="background", st="PFS", npv=50e6, irr=20.0, disc=8.0, project="Gee Hill")
    r = query_studies(conn, P(ticker="GGG.V"), names, None)
    ok("type and project filled from a later release", r["total"] == 1 and r["items"][0]["study_type"] == "PFS"
       and r["items"][0]["project"] == "Gee Hill" and r["items"][0]["study_id"] == "g1")

    print("economics_api selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        if "/opt/mnt/app" not in sys.path and os.path.isdir("/opt/mnt/app"):
            sys.path.insert(0, "/opt/mnt/app")
        sys.exit(_selftest())
    print(__doc__)
