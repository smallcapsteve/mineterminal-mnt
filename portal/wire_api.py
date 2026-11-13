"""MNT Wire API v1: the news tape behind Mine Terminal Pro's "MTP Wire" homepage panel.

MNT_WIRE_API_V1 (2026-10-19, Justin); scoring WIRE_SCORE_V3 from his 94-release review. One endpoint, GET, CORS-allowed:

  /api/v1/wire?hours=72&limit=150&min=1

One row per approved release, newest first, joined to what the readers already found in it:

  importance  1 routine, 2 material, 3 market-moving: rule-based (see score()), with `reasons`
  group       DRILLS | FINANCINGS | RESOURCES & STUDIES | M&A | PRODUCTION | CORPORATE
  fact        the one-line key fact ("59.44 m @ 2.41 g/t Au", "C$35.0M closed @ $10.00")
  facts       label/value pairs for the story pane

Rules first, by design: Justin labels a sample, the rules are tuned to it, and only then is anything
smarter added. Amounts are never converted for display; a fixed rate is used only to rank sizes.

Registered from portal.serve via wire_api.register(app). Read-only; sqlite3 only.
Self-test: python3 -m portal.wire_api --selftest  (in-memory)
           python3 -m portal.wire_api --sample 72  (live, read-only: prints the last 72 hours scored)
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import threading
import time
from typing import Any, Optional

DB_PATH = "/opt/mnt/app/portal/portal.db"
SITE_BASE = "https://miningnewsterminal.com"
RANK_FX = {"CAD": 1.0, "USD": 1.38, "AUD": 0.90, "GBP": 1.85, "EUR": 1.60}
_CACHE: dict = {}
_LOCK = threading.Lock()
CACHE_SECONDS = 60

try:
    from portal.text_helpers import smart_title  # type: ignore
except Exception:  # selftest outside the app
    def smart_title(s: str) -> str:
        return s


# ---------------------------------------------------------------- formatting helpers

def _num(x) -> Optional[float]:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _money(v: Optional[float], cur: Optional[str]) -> str:
    if v is None:
        return ""
    sym = {"CAD": "C$", "USD": "US$", "AUD": "A$", "GBP": "£", "EUR": "€"}.get((cur or "CAD").upper(), (cur or "") + " ")
    a = abs(v)
    if a >= 1e9:
        s = f"{v / 1e9:.2f}B"
    elif a >= 1e6:
        s = f"{v / 1e6:.1f}M"
    elif a >= 1e3:
        s = f"{v / 1e3:.0f}K"
    else:
        s = f"{v:,.0f}"
    return sym + s


def _price(v: Optional[float]) -> str:
    if v is None:
        return ""
    return f"${v:.3f}" if v < 1 else f"${v:,.2f}"


def _g(v: Optional[float]) -> str:
    if v is None:
        return ""
    return f"{v:,.0f}" if abs(v) >= 100 else (f"{v:.2f}".rstrip("0").rstrip(".") if v % 1 else f"{v:.0f}")


def _rank_cad(v: Optional[float], cur: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    return v * RANK_FX.get((cur or "CAD").upper(), 1.0)


# ---------------------------------------------------------------- groups and scoring

GROUP_RULES = [  # (substring of a category label, group, base importance)
    ("merger", "M&A", 2), ("acquisition", "M&A", 2), ("partnership", "M&A", 2), ("joint venture", "M&A", 2),
    ("royalt", "M&A", 2), ("stream", "M&A", 2), ("option", "M&A", 2), ("staking", "M&A", 2),
    ("drill", "DRILLS", 2),
    ("financ", "FINANCINGS", 1), ("debt", "FINANCINGS", 1), ("credit", "FINANCINGS", 1),
    ("resource", "RESOURCES & STUDIES", 3), ("economic", "RESOURCES & STUDIES", 3), ("feasibility", "RESOURCES & STUDIES", 3),
    ("technical report", "RESOURCES & STUDIES", 2), ("metallurg", "RESOURCES & STUDIES", 2),
    ("production", "PRODUCTION", 2), ("mine development", "PRODUCTION", 2), ("operations", "PRODUCTION", 2),
    ("permit", "CORPORATE", 2), ("listing", "CORPORATE", 2), ("management", "CORPORATE", 1),
    ("sampling", "DRILLS", 2), ("exploration", "DRILLS", 2),
    ("marketing", "CORPORATE", 1), ("corporate", "CORPORATE", 1),
]
GROUP_ORDER = ["M&A", "RESOURCES & STUDIES", "DRILLS", "FINANCINGS", "PRODUCTION", "CORPORATE"]
_MNA_STRONG = re.compile(r"\b(definitive (?:arrangement|merger|agreement)|merger|amalgamation|to be acquired|"
                         r"takeover|take-over|business combination|plan of arrangement|arrangement agreement|"
                         r"unsolicited|tender offer|all of the (?:issued and )?outstanding shares)\b", re.I)
_MNA_ASSET = re.compile(r"\b(to acquire|acquires|acquisition|acquired|sale of|divest|sells)\b", re.I)
_SOFT = re.compile(r"\b(update|provides an update|letter of intent|loi|non-binding|term sheet|extends|extension)\b", re.I)
_STUDY_WORDS = re.compile(r"\b(resource|mre|pea|pfs|feasibility|economic assessment|reserve|study|npv)\b", re.I)
_TR_FILED = re.compile(r"\bfil(?:es|ed|ing)\b.{0,60}\btechnical report\b|\btechnical report\b.{0,40}\bfiled\b", re.I)
_HEAD_DRILL = [
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:m|metres|meters)\b[^.;]{0,40}?(?:of|at|grading|averaging|@)\s*(\d+(?:\.\d+)?)\s*(g/t|gpt|%)\s*(gold|au|silver|ag|copper|cu|aueq|ageq|cueq)?", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*(g/t|gpt|%)\s*(gold|au|silver|ag|copper|cu|aueq|ageq|cueq)?\s*(?:over|across)\s*(\d+(?:\.\d+)?)\s*(?:m|metres|meters)\b", re.I),
]
# WIRE_SCORE_V3 (Justin's 94-release review, 2026-10-19): 1 is only for routine noise.
_DRILL_LOW = re.compile(r"\b(visible gold|satellite|spectral)\b", re.I)
_DISCOVERY = re.compile(r"\b(announces (?:a |the |new )?discovery|discovers|new discovery|makes (?:a |new )?discovery)\b(?!\s+potential)", re.I)
_DRILL_ACTIVE = re.compile(r"(commenc|begin|start|complet|under ?way|initial)\w*\b.{0,40}\bdrill|\bdrill\w*\b.{0,40}\b(commenc|under ?way|complet|begin|start)", re.I)
_DRILL_PLAN = re.compile(r"\b(survey|geophysic|induced polarization|field programs?|outlines|mapping|soil sampling program)\b", re.I)
_CORP_ROUTINE = re.compile(r"\b(highlights|collaborat|about [A-Z]|advisor|advisory|appoint|director|video|clips|webinar|newsletter|annual general meeting)", re.I)
_HALT = re.compile(r"\b(cease trade order|trading halt|halted)\b", re.I)
_MARKETING = re.compile(r"\b(to (?:present|participate|attend|exhibit)|presenting at|investor (?:conference|forum|summit|webinar)|"
                        r"virtual investor|webinar|podcast|interview|marketing services|investor awareness)\b", re.I)
_TOP_ROLE = re.compile(r"\b(ceo|chief executive|(?<!vice )(?<!vice-)president|cfo|chief financial)\b", re.I)


def _cats(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    return [c.strip() for c in re.split(r"[|,]", raw) if c.strip()]


def _group_and_base(cats: list[str]) -> tuple[str, int, list[str]]:
    hits = []
    for c in cats:
        cl = c.lower()
        for sub, grp, base in GROUP_RULES:
            if sub in cl:
                hits.append((grp, base, c))
                break
    if not hits:
        return "CORPORATE", 1, []
    best = max(hits, key=lambda h: (h[1], -GROUP_ORDER.index(h[0])))
    return best[0], best[1], [h[2] for h in hits]


def _drill_gm(d: dict) -> tuple[Optional[str], Optional[float]]:
    """Grade x length in the metal's own unit, and which threshold family applies."""
    g, L, u, m = _num(d.get("top_grade")), _num(d.get("top_length_m")), (d.get("top_unit") or "").lower(), (d.get("top_metal") or "")
    if g is None or L is None:
        return None, None
    ml = m.lower()
    if u == "ppm" and (ml.startswith("au") or ml.startswith("ag")):
        u = "g/t"
    if u in ("g/t", "gpt") and ml.startswith("au"):
        return "au_gm", g * L
    if u in ("g/t", "gpt") and ml.startswith("ag"):
        return "ag_gm", g * L
    if u == "%" and ml.startswith("cu"):
        return "cu_pm", g * L
    if u in ("g/t", "gpt"):
        return "other_gt", g * L
    if u == "%":
        return "other_pct", g * L
    return "other", g * L


_METAL = {"gold": "Au", "au": "Au", "silver": "Ag", "ag": "Ag", "copper": "Cu", "cu": "Cu",
          "aueq": "AuEq", "ageq": "AgEq", "cueq": "CuEq"}


def _head_drill(headline: str) -> Optional[dict]:
    """An interval stated in the headline, used only when the drill reader stored nothing for the release."""
    h = headline or ""
    m = _HEAD_DRILL[0].search(h)
    if m:
        L, g, u, met = m.group(1), m.group(2), m.group(3), m.group(4)
    else:
        m = _HEAD_DRILL[1].search(h)
        if not m:
            return None
        g, u, met, L = m.group(1), m.group(2), m.group(3), m.group(4)
    met = _METAL.get((met or "").lower(), "Au" if u.lower() in ("g/t", "gpt") else "Cu")
    try:
        return {"top_grade": float(g), "top_length_m": float(L), "top_unit": "g/t" if u.lower() == "gpt" else u, "top_metal": met,
                "_from_headline": True}
    except ValueError:
        return None


def score(group: str, base: int, headline: str, cats: list[str], drill: Optional[dict], fin: Optional[dict],
          mgmt: Optional[dict]) -> tuple[int, list[str]]:
    s, why = base, [f"{group.lower()} base {base}"]
    if _HALT.search(headline or ""):
        return 3, why + ["trading halt / cease trade in headline"]
    if group == "M&A":
        if _SOFT.search(headline or ""):
            s = 2
            why.append("update / LOI / non-binding wording")
        elif _MNA_STRONG.search(headline or "") or _MNA_ASSET.search(headline or ""):
            s = 3
            why.append("acquisition / merger wording")

    if group == "DRILLS" and drill is None:
        drill = _head_drill(headline)
        if drill:
            why.append("interval read from the headline")
    if group == "DRILLS" and drill:
        fam, gm = _drill_gm(drill)
        if fam and gm is not None:
            hi, mid = {"au_gm": (80, 30), "ag_gm": (7000, 1500), "cu_pm": (50, 15),
                       "other_gt": (100, 30), "other_pct": (50, 15)}.get(fam, (None, None))
            if hi is not None:
                s = 3 if gm >= hi else 2
                why.append(f"{fam} {gm:,.0f} (3 at >={hi}, else 2)")
    if group == "DRILLS" and not drill:
        h = headline or ""
        if _DRILL_LOW.search(h):
            s = 1; why.append("visible gold / satellite work, no assays")
        elif _DISCOVERY.search(h):
            s = 3; why.append("discovery announced")
        elif re.search(r"\b(drill(ing)?|assay) results\b", h, re.I):
            s = 3; why.append("drill results released (figures in release)")
        elif _DRILL_ACTIVE.search(h):
            s = 2; why.append("drilling started / completed")
        elif _DRILL_PLAN.search(h):
            s = 1; why.append("survey / plan, no results")
        else:
            s = 2; why.append("exploration news without figures")
    if group == "FINANCINGS":
        amt = None
        if fin:
            amt = _rank_cad(fin.get("_amount"), fin.get("currency"))
        if amt is not None:
            s = 3 if amt >= 20e6 else 2
            why.append(f"size C${amt / 1e6:,.1f}M ranked (3 at >=20M, else 2)")
        else:
            s = max(s, 2)
            why.append("financing news")
    if mgmt and _TOP_ROLE.search(mgmt.get("role") or ""):
        s = max(s, 2)
        why.append("CEO/CFO/President change")
    elif group == "CORPORATE":
        if mgmt or _CORP_ROUTINE.search(headline or ""):
            s = 1; why.append("board / advisor / promotional item")
        else:
            s = max(s, 2); why.append("company or project news")
    if _MARKETING.search(headline or "") and s >= 2 and group in ("CORPORATE", "RESOURCES & STUDIES", "PRODUCTION"):
        s = 1
        why.append("conference / marketing wording")
    if any("marketing" in c.lower() for c in cats) and len(cats) == 1:
        s = 1
    return max(1, min(3, s)), why


# ---------------------------------------------------------------- key facts per reader

def _fact_drill(d: dict) -> tuple[str, list]:
    g, L, u, m = _num(d.get("top_grade")), _num(d.get("top_length_m")), d.get("top_unit") or "", d.get("top_metal") or ""
    gu = f"{_g(g)}{u}" if u == "%" else f"{_g(g)} {u}"
    one = f"{_g(L)} m @ {gu} {m}".strip() if g is not None and L is not None else (d.get("top_summary") or "")
    facts = [["Best interval", one]]
    if d.get("top_hole_id"):
        facts.append(["Hole", d["top_hole_id"]])
    if d.get("project"):
        facts.append(["Project", d["project"]])
    if d.get("n_intercepts"):
        facts.append(["Intervals read", str(d["n_intercepts"])])
    if d.get("sample_type") and d["sample_type"] != "drill":
        facts.append(["Sample type", d["sample_type"]])
    return one, facts


_ROLE_WORD = {"announcement": "announced", "final_close": "closed", "tranche_close": "tranche closed",
              "upsize": "upsized", "amendment": "amended", "termination": "terminated", "close": "closed"}


def _fact_fin(f: dict) -> tuple[str, list]:
    cur = f.get("currency")
    amt = f.get("_amount")
    word = _ROLE_WORD.get((f.get("role") or "").lower(), (f.get("role") or "").replace("_", " "))
    up = _num(f.get("unit_price"))
    kind = (f.get("kind") or "").replace("+", " · ").replace("_", "-").lower()
    parts = [p for p in (_money(amt, cur), word) if p]
    one = " ".join(parts)
    if up is not None:
        one += f" @ {_price(up)}"
    facts = [["Amount", (_money(amt, cur) + (f" ({word})" if word else "")).strip()]]
    if up is not None:
        facts.append(["Price", _price(up)])
    if kind:
        facts.append(["Type", kind])
    ws, wt = _num(f.get("warrant_strike")), _num(f.get("warrant_term_months"))
    if ws is not None:
        facts.append(["Warrants", f"{_price(ws)}" + (f" for {wt:.0f} months" if wt else "")])
    if f.get("tranche_label"):
        facts.append(["Tranche", str(f["tranche_label"])])
    return one, facts


def _fact_res(r: dict) -> tuple[str, list]:
    summ = r.get("summary") or ""
    one = summ if len(summ) <= 70 else summ[:69].rstrip() + "…"
    facts = [["Estimate", summ]]
    if r.get("project"):
        facts.insert(0, ["Project", r["project"]])
    if r.get("mre_type"):
        facts.append(["Type", r["mre_type"]])
    return one, facts


def _fact_econ(e: dict) -> tuple[str, list]:
    cur = e.get("currency")
    npv, irr, capex = _num(e.get("npv_after_tax")), _num(e.get("irr_after_tax_pct")), _num(e.get("initial_capex"))
    bits = [e.get("study_type") or "Study"]
    if npv is not None:
        bits.append("NPV " + _money(npv, cur))
    if irr is not None:
        bits.append(f"IRR {irr:.1f}%")
    one = " · ".join(bits)
    facts = [["Study", e.get("study_type") or ""], ["Project", e.get("project") or ""]]
    if npv is not None:
        facts.append(["NPV after tax", _money(npv, cur)])
    if irr is not None:
        facts.append(["IRR after tax", f"{irr:.1f}%"])
    if capex is not None:
        facts.append(["Initial capex", _money(capex, cur)])
    if _num(e.get("payback_years")) is not None:
        facts.append(["Payback", f"{_num(e.get('payback_years')):.1f} years"])
    if _num(e.get("mine_life_years")) is not None:
        facts.append(["Mine life", f"{_num(e.get('mine_life_years')):.0f} years"])
    return one, [f for f in facts if f[1]]


def _fact_prod(p: dict) -> tuple[str, list]:
    q = _num(p.get("qty"))
    one = ""
    if q is not None:
        one = f"{p.get('period') or ''}: {q:,.0f} {p.get('unit') or ''} {p.get('metal') or ''}".strip(": ")
    facts = [["Period", p.get("period") or ""], ["Metal", p.get("metal") or ""]]
    if q is not None:
        facts.append(["Produced", f"{q:,.0f} {p.get('unit') or ''}"])
    if _num(p.get("aisc")) is not None:
        facts.append(["AISC", f"${_num(p.get('aisc')):,.0f}"])
    return one, [f for f in facts if f[1]]


def _fact_mgmt(m: dict) -> tuple[str, list]:
    one = f"{m.get('role') or 'Role'}: {m.get('person') or ''} {m.get('action') or ''}".strip()
    return one, [["Person", m.get("person") or ""], ["Role", m.get("role") or ""], ["Change", m.get("action") or ""]]


def _fact_permit(p: dict) -> tuple[str, list]:
    name = p.get("permit_name") or p.get("permit_type") or "Permit"
    one = f"{name} {p.get('status') or ''}".strip()
    facts = [["Permit", name], ["Status", p.get("status") or ""], ["Project", p.get("project") or ""],
             ["Authority", p.get("authority") or ""]]
    return one, [f for f in facts if f[1]]


# ---------------------------------------------------------------- the query

_READERS = [
    # table, columns, first-row order
    ("drill_results", "event_id, ticker, project, top_hole_id, top_grade, top_unit, top_metal, top_length_m, top_summary, n_intercepts, sample_type", "drill_id"),
    ("financing_events", "event_id, role, tranche_label, kind, gross_total, amount_offered, amount_this_close, amount_closed_total, unit_price, currency, is_deal, is_duplicate, warrant_strike, warrant_term_months", "rowid"),
    ("resource_estimates", "event_id, project, summary, mre_type, ordinal", "ordinal"),
    ("economic_studies", "event_id, project, study_type, currency, npv_after_tax, irr_after_tax_pct, initial_capex, payback_years, mine_life_years, ordinal", "ordinal"),
    ("production_results", "event_id, kind, period, metal, unit, qty, aisc, ordinal", "ordinal"),
    ("management_changes", "event_id, action, person, role, ordinal", "ordinal"),
    ("permits", "event_id, permit_type, permit_name, status, project, authority, ordinal", "ordinal"),
]


def _first_rows(con: sqlite3.Connection, table: str, cols: str, order: str, ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not ids:
        return out
    try:
        for i in range(0, len(ids), 400):
            chunk = ids[i:i + 400]
            q = f"SELECT {cols} FROM {table} WHERE event_id IN ({','.join('?' * len(chunk))}) ORDER BY {order}"
            for r in con.execute(q, chunk).fetchall():
                d = dict(r)
                eid = d["event_id"]
                if table == "production_results":
                    # prefer an actual figure over guidance
                    if eid in out and (out[eid].get("kind") == "actual" or d.get("kind") != "actual"):
                        continue
                    out[eid] = d
                    continue
                if table == "management_changes":
                    if eid in out and _TOP_ROLE.search(out[eid].get("role") or ""):
                        continue
                    if eid not in out or _TOP_ROLE.search(d.get("role") or ""):
                        out[eid] = d
                    continue
                if eid not in out:
                    out[eid] = d
    except sqlite3.Error:
        return out
    return out


def build(con: sqlite3.Connection, hours: int = 72, limit: int = 150, min_imp: int = 1) -> dict[str, Any]:
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - hours * 3600))
    rows = con.execute(
        "SELECT event_id, ticker, additional_tickers, raw_headline, published_at, classified_at, slug, categories, source_name "
        "FROM events WHERE published_at >= ? AND +review_status IN ('auto_approved','approved') "
        "AND coalesce(raw_headline,'') <> '' ORDER BY published_at DESC, ingested_at DESC LIMIT 600",
        (since,),
    ).fetchall()
    ids = [r["event_id"] for r in rows]
    rd = {t: _first_rows(con, t, c, o, ids) for t, c, o in _READERS}
    items, hidden = [], {1: 0, 2: 0, 3: 0}
    for r in rows:
        eid = r["event_id"]
        cats = _cats(r["categories"])
        group, base, _ = _group_and_base(cats)
        head = smart_title(r["raw_headline"] or "")
        drill = rd["drill_results"].get(eid)
        fin = rd["financing_events"].get(eid)
        if fin is not None:
            if fin.get("is_duplicate"):
                fin = None
            else:
                fin["_amount"] = next((v for v in (_num(fin.get("amount_closed_total")), _num(fin.get("amount_this_close")),
                                                   _num(fin.get("gross_total")), _num(fin.get("amount_offered"))) if v), None)
        res, eco, prod = rd["resource_estimates"].get(eid), rd["economic_studies"].get(eid), rd["production_results"].get(eid)
        mg, pm = rd["management_changes"].get(eid), rd["permits"].get(eid)
        # a reader's find is stronger evidence of the group than the tag alone
        if drill and group == "CORPORATE":
            group, base = "DRILLS", 2
        if fin and fin.get("is_deal") and group == "CORPORATE":
            group, base = "FINANCINGS", 1
        if (res or eco) and group not in ("M&A",) and (group == "RESOURCES & STUDIES" or _STUDY_WORDS.search(head)):
            group, base = "RESOURCES & STUDIES", 3
        if _MARKETING.search(head) and group != "RESOURCES & STUDIES":
            res = eco = None
        if group != "RESOURCES & STUDIES":
            res = eco = None
        imp, why = score(group, base, head, cats, drill, fin, mg)
        fact, facts = "", []
        if drill is None and group == "DRILLS":
            drill = _head_drill(head)
        if group != "CORPORATE":
            mg = None if not (mg and _TOP_ROLE.search(mg.get("role") or "")) else mg
        for got, fn in ((eco, _fact_econ), (res, _fact_res), (drill, _fact_drill), (fin, _fact_fin),
                        (prod, _fact_prod), (pm, _fact_permit), (mg, _fact_mgmt)):
            if got:
                fact, facts = fn(got)
                break
        if imp < min_imp:
            hidden[imp] += 1
            continue
        tk = (r["ticker"] or "").strip()
        slug = (r["slug"] or "release").strip()
        items.append({
            "event_id": eid,
            "ticker": tk,
            "additional_tickers": [t for t in (r["additional_tickers"] or "").strip("|").split("|") if t],
            "published_at": r["published_at"] or r["classified_at"] or "",
            "headline": head,
            "url": f"{SITE_BASE}/news/{tk.lower()}/{slug}" if tk else None,
            "source_name": r["source_name"] or "",
            "categories": cats,
            "group": group,
            "importance": imp,
            "reasons": why,
            "fact": fact,
            "facts": facts,
        })
        if len(items) >= limit:
            break
    counts = {1: 0, 2: 0, 3: 0}
    for it in items:
        counts[it["importance"]] += 1
    return {"ok": True, "api": "wire/1", "hours": hours, "since": since, "min": min_imp,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "counts": {str(k): v for k, v in counts.items()}, "hidden": {str(k): v for k, v in hidden.items()},
            "count": len(items), "items": items}


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout = 10000")
    return c


def cached(hours: int, limit: int, min_imp: int) -> dict[str, Any]:
    key = (hours, limit, min_imp)
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    con = _conn()
    try:
        data = build(con, hours, limit, min_imp)
    finally:
        con.close()
    with _LOCK:
        _CACHE[key] = (now, data)
        if len(_CACHE) > 40:
            for k in sorted(_CACHE, key=lambda k: _CACHE[k][0])[:20]:
                _CACHE.pop(k, None)
    return data


def register(app) -> None:
    from fastapi.responses import JSONResponse

    @app.get("/api/v1/wire")
    def wire(hours: int = 72, limit: int = 150, min: int = 1):  # noqa: A002
        hours = max(1, min_(int(hours or 72), 24 * 14))
        limit = max(1, min_(int(limit or 150), 300))
        m = max(1, min_(int(min or 1), 3))
        try:
            data = cached(hours, limit, m)
            status = 200
        except Exception as e:  # pragma: no cover
            data, status = {"ok": False, "error": type(e).__name__}, 503
        return JSONResponse(data, status_code=status, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Cache-Control": "public, max-age=30",
            "X-MNT-API-Version": "1",
        })


def min_(a, b):
    return a if a < b else b


# ---------------------------------------------------------------- self-test

def _selftest() -> int:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE events(event_id TEXT, ticker TEXT, additional_tickers TEXT, raw_headline TEXT, published_at TEXT,
      classified_at TEXT, slug TEXT, categories TEXT, source_name TEXT, review_status TEXT, ingested_at TEXT);
    CREATE TABLE drill_results(drill_id INTEGER, event_id TEXT, ticker TEXT, project TEXT, top_hole_id TEXT, top_grade REAL,
      top_unit TEXT, top_metal TEXT, top_length_m REAL, top_summary TEXT, n_intercepts INTEGER, sample_type TEXT);
    CREATE TABLE financing_events(event_id TEXT, role TEXT, tranche_label TEXT, kind TEXT, gross_total REAL, amount_offered REAL,
      amount_this_close REAL, amount_closed_total REAL, unit_price REAL, currency TEXT, is_deal INTEGER, is_duplicate INTEGER,
      warrant_strike REAL, warrant_term_months REAL);
    CREATE TABLE resource_estimates(event_id TEXT, project TEXT, summary TEXT, mre_type TEXT, ordinal INTEGER);
    CREATE TABLE economic_studies(event_id TEXT, project TEXT, study_type TEXT, currency TEXT, npv_after_tax REAL,
      irr_after_tax_pct REAL, initial_capex REAL, payback_years REAL, mine_life_years REAL, ordinal INTEGER);
    CREATE TABLE production_results(event_id TEXT, kind TEXT, period TEXT, metal TEXT, unit TEXT, qty REAL, aisc REAL, ordinal INTEGER);
    CREATE TABLE management_changes(event_id TEXT, action TEXT, person TEXT, role TEXT, ordinal INTEGER);
    CREATE TABLE permits(event_id TEXT, permit_type TEXT, permit_name TEXT, status TEXT, project TEXT, authority TEXT, ordinal INTEGER);
    """)
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    ev = [
        ("e1", "TECT.V", "Tectonic Metals Drills 2.41 g/t Au over 59.44 metres", "Drill Results"),
        ("e2", "MOON.V", "Blue Moon Metals Closes C$35 Million Private Placement", "Financing"),
        ("e3", "NSJ.CN", "NSJ Antimony Announces Flow-Through Placement", "Financing"),
        ("e4", "ZNX.V", "ZincX Resources To Present At The Bahamas Summit", "Marketing Announcement"),
        ("e5", "HHH.V", "Helius Announces Definitive Agreement to Acquire Serra Pelada", "Mergers & Acquisitions|Property Options & Staking"),
        ("e6", "TALA.TO", "Talisker Announces PEA for Coffee Gold", "Economic Studies"),
        ("e7", "SCMI.V", "Selkirk Copper Drills 44.7 metres Grading 2.12% Cu", "Drill Results"),
        ("e8", "HSTR.V", "Heliostar Reports 52.4m Grading 5.84 g/t Gold from the High Grade Panel", "Drill Results"),
        ("e9", "FMAN.V", "Freeman Gold to Attend the Idaho Mining Conference", "Marketing Announcement|Economic Studies"),
        ("e10", "CADY.TO", "Cadillac Mines Announces Appointment Of Two New Officers", "Management Changes"),
        ("e11", "WCU.V", "World Copper Signs Letter of Intent to Acquire the Hot Tip Property", "Mergers & Acquisitions"),
    ]
    for eid, tk, h, c in ev:
        con.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)", (eid, tk, "", h, now, now, eid, c, "test", "auto_approved", now))
    con.execute("INSERT INTO drill_results VALUES (1,'e1','TECT.V','Flat','CMR26-170',2.41,'g/t','Au',59.44,'2.41 g/t Au / 59.44m',26,'drill')")
    con.execute("INSERT INTO drill_results VALUES (2,'e7','SCMI.V','Minto','26SCM237',2.12,'%','Cu',44.7,'2.12% Cu / 44.7m',68,'drill')")
    con.execute("INSERT INTO financing_events VALUES ('e2','final_close',NULL,'PP+NON_BROKERED',35000000,NULL,35000000,35000000,10.0,'CAD',1,0,NULL,NULL)")
    con.execute("INSERT INTO financing_events VALUES ('e3','announcement',NULL,'FT',924000,924000,NULL,NULL,0.66,'CAD',1,0,NULL,NULL)")
    con.execute("INSERT INTO economic_studies VALUES ('e6','Coffee Gold','PEA','USD',2300000000,47.8,NULL,NULL,NULL,1)")
    con.execute("INSERT INTO economic_studies VALUES ('e9','Idaho','FS','USD',696000000,34.4,NULL,NULL,NULL,1)")
    con.execute("INSERT INTO management_changes VALUES ('e10','appointed','Jay Henry','Vice President, People',1)")
    data = build(con, 72, 50, 1)
    got = {it["ticker"]: (it["importance"], it["group"], it["fact"]) for it in data["items"]}
    want = {
        "TECT.V": (3, "DRILLS", "59.44 m @ 2.41 g/t Au"),
        "MOON.V": (3, "FINANCINGS", "C$35.0M closed @ $10.00"),
        "NSJ.CN": (2, "FINANCINGS", "C$924K announced @ $0.660"),
        "ZNX.V": (1, "CORPORATE", ""),
        "HHH.V": (3, "M&A", ""),
        "TALA.TO": (3, "RESOURCES & STUDIES", "PEA · NPV US$2.30B · IRR 47.8%"),
        "SCMI.V": (3, "DRILLS", "44.7 m @ 2.12% Cu"),
        "HSTR.V": (3, "DRILLS", "52.4 m @ 5.84 g/t Au"),
        "FMAN.V": (1, "RESOURCES & STUDIES", "FS · NPV US$696.0M · IRR 34.4%"),
        "CADY.TO": (1, "CORPORATE", "Vice President, People: Jay Henry appointed"),
        "WCU.V": (2, "M&A", ""),
    }
    bad = 0
    for k, v in want.items():
        ok = got.get(k) == v
        bad += 0 if ok else 1
        print(("ok  " if ok else "BAD ") + k, got.get(k), "" if ok else f"want {v}")
    d2 = build(con, 72, 50, 2)
    print("min=2:", d2["count"], "items, hidden", d2["hidden"])
    bad += 0 if d2["count"] == 8 and d2["hidden"]["1"] == 3 else 1
    print("SELFTEST", "PASS" if not bad else f"FAIL ({bad})")
    return 1 if bad else 0


def _sample(hours: int) -> int:
    con = _conn()
    t = time.time()
    data = build(con, hours, 300, 1)
    print(f"built {data['count']} items in {time.time() - t:.2f}s; counts {data['counts']}")
    for it in data["items"]:
        print("\t".join([it["published_at"][:16], str(it["importance"]), it["group"], it["ticker"],
                         it["headline"][:90], it["fact"][:50], "; ".join(it["reasons"])[:120]]))
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if "--sample" in sys.argv:
        i = sys.argv.index("--sample")
        sys.exit(_sample(int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 72))
    print(__doc__)
