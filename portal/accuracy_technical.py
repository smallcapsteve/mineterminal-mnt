"""How /technical-reports is scored (TECH_SPEC_V1, 2026-09-22).

The page shows ONE ROW PER NI 43-101 TECHNICAL REPORT an item reports: filed, commissioned or withdrawn, from news
releases and from the SEDAR+ documents themselves (a consent of a qualified person, a report's cover pages).
Justin, 2026-09-22. A release is judged as a set of rows; a predicted row is paired with the labelled row it claims
to be before any field is scored.

Pairing, strongest first over the whole grid: a row can only pair with a label on an agreeing project (or either
project unstated); among those, the score adds the same status (3), report type (2), effective date (2) and amended
flag (1). Leftovers stay unpaired: a predicted row with no partner is a false row, a label with no partner a missed
one.

Project names are compared as sets of words once generic words ('Project', 'Property', 'Mine', commodity words) are
dropped, so 'Powerline Uranium Project' = 'Powerline'. A firm agrees when the predicted lead firm is one of the
labelled firms. A field the label does not state is set aside rather than judged.

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

import re
import unicodedata

try:
    from portal.accuracy import TagSpec, register_spec
except Exception:  # pragma: no cover - standalone use of the judge
    TagSpec = register_spec = None

TECH_KEY_FIELDS = ("row", "report_type", "project", "status", "effective_date", "author_firm")
TECH_REPORT_FIELDS = ("title", "report_date", "filing_date", "amended", "qps", "metal", "expected", "npv", "irr", "capex")

_ROW_FIELDS = ("report_type", "project", "status", "effective_date", "author_firm", "title", "report_date",
               "filing_date", "expected", "qps", "amended", "metal", "resource_json", "npv", "npv_discount", "irr",
               "capex", "currency", "after_tax", "mine_life_years", "payback_years", "supports_release", "doc_kind")

_GENERIC = {"the", "a", "an", "of", "and", "de", "del", "la", "project", "projects", "property", "properties",
            "claims", "claim", "block", "area", "mine", "mines", "deposit", "deposits", "gold", "silver", "copper",
            "lithium", "uranium", "nickel", "antimony", "tungsten", "potash", "phosphate", "molybdenum", "graphite",
            "critical", "minerals", "mineral", "metals", "polymetallic", "pge", "zinc", "lead", "cu", "au", "ni",
            "co", "1", "north", "south", "east", "west"}
_FIRM_GENERIC = {"inc", "ltd", "limited", "corp", "corporation", "llc", "ulc", "pty", "co", "consulting", "consultants",
                 "consultant", "engineering", "group", "services", "canada", "international", "geological", "geoscience",
                 "geosciences", "the", "and", "of", "mining", "geosolutions", "enterprises", "sa", "europe", "projects",
                 "advisors", "resources", "resource", "usa", "us"}


def _fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    return "".join(c for c in s if not unicodedata.combining(c))


def _words(s, generic=_GENERIC):
    return {w for w in re.findall(r"[a-z0-9&]+", _fold(s)) if w not in generic}


def name_agrees(a, b):
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return _fold(a).strip() == _fold(b).strip()
    return wa <= wb or wb <= wa


def firm_agrees(lab, pred):
    labs = [_words(x, _FIRM_GENERIC) for x in str(lab or "").split(";") if x.strip()]
    lead = next((x for x in str(pred or "").split(";") if x.strip()), None)
    if not lead:
        return False
    wp = _words(lead, _FIRM_GENERIC)
    if not wp:
        return False
    return any(w and (wp <= w or w <= wp) for w in labs)


def _close(a, b, rel=0.01):
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= rel * max(abs(float(a)), abs(float(b)))


def _surnames(qs):
    if isinstance(qs, str):
        qs = [q for q in qs.split(";")]
    return {_fold(q).split()[-1] for q in (qs or []) if q and q.strip()}


def _title_agrees(a, b):
    wa, wb = _words(a, set()), _words(b, set())
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= 0.7


def _pair_score(lab, pr):
    lp, pp = lab.get("project"), pr.get("project")
    if lp and pp and not name_agrees(lp, pp):
        return None
    n = 1
    if lab.get("status") == pr.get("status"):
        n += 3
    if lab.get("report_type") and lab.get("report_type") == pr.get("report_type"):
        n += 2
    if lab.get("effective_date") and lab.get("effective_date") == pr.get("effective_date"):
        n += 2
    if bool(lab.get("amended")) == bool(pr.get("amended")):
        n += 1
    return n


def tech_match(labels, preds):
    scored = []
    for li, lab in enumerate(labels):
        for pi, pr in enumerate(preds):
            n = _pair_score(lab, pr)
            if n is not None:
                scored.append((-n, li, pi))
    scored.sort()
    got, used = {}, set()
    for _n, li, pi in scored:
        if li in got or pi in used:
            continue
        got[li] = pi
        used.add(pi)
    extra = [pi for pi in range(len(preds)) if pi not in used]
    return [(li, got.get(li)) for li in range(len(labels))], extra


def _judge_field(f, lab, pr):
    lv, pv = lab.get(f), pr.get(f)
    if f == "status":
        return lv == pv
    if f == "amended":
        return bool(lv) == bool(pv)
    if lv is None or lv == "" or lv == []:
        return None
    if f == "project":
        return pv is not None and name_agrees(lv, pv)
    if f == "author_firm":
        return pv is not None and firm_agrees(lv, pv)
    if f == "title":
        return pv is not None and _title_agrees(lv, pv)
    if f == "qps":
        a, b = _surnames(lv), _surnames(pv)
        return bool(b) and len(a & b) / len(a | b) >= 0.5
    if f == "metal":
        return pv is not None and bool(set(_fold(lv).split("+")) & set(_fold(pv).split("+")))
    if f in ("npv", "capex"):
        return _close(lv, pv)
    if f == "irr":
        return pv is not None and abs(float(lv) - float(pv)) <= 0.5
    if f == "expected":
        return pv is not None and (_fold(lv) in _fold(pv) or _fold(pv) in _fold(lv))
    return _fold(lv) == _fold(pv)


def judge_technical(pred, expect):
    """pred: None or {rows: [...]}; expect: {complete, rows: [...]}."""
    fields = TECH_KEY_FIELDS + TECH_REPORT_FIELDS
    out = {f: [] for f in fields}
    gold = list(expect.get("rows") or [])
    shown = list((pred or {}).get("rows") or [])
    if not shown:
        out["row"].extend(["fn"] * len(gold))
        return out
    if not gold:
        out["row"].extend(["fp"] * len(shown))
        return out
    pairs, extra = tech_match(gold, shown)
    for li, pi in pairs:
        lab = gold[li]
        if pi is None:
            out["row"].append("fn")
            continue
        pr = shown[pi]
        out["row"].append("tp")
        for f in fields[1:]:
            ok = _judge_field(f, lab, pr)
            if ok is None:
                continue
            if ok:
                out[f].append("tp")
            elif pr.get(f) not in (None, "", []):
                out[f].extend(["fp", "fn"])
            else:
                out[f].append("fn")
    if expect.get("complete", True):
        out["row"].extend(["fp"] * len(extra))
    return out


def _table_exists(conn):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name='technical_reports'").fetchone() is not None


def stored_technical(conn, event_id):
    """What /technical-reports shows for one item. A marker row (status NULL) states nothing."""
    if not _table_exists(conn):
        return None
    rows = list(conn.execute(
        "SELECT " + ", ".join(_ROW_FIELDS) + " FROM technical_reports WHERE event_id=? AND status IS NOT NULL "
        "ORDER BY ordinal", (event_id,)))
    return {"rows": [dict(zip(_ROW_FIELDS, r)) for r in rows]} if rows else None


def _tech_from_records(records):
    from portal.extractors import technical as X
    return X.to_prediction(records)


def _tech_candidate_predictor(conn, extractor, version):
    """Scored through the publisher, so what the page would show is what is tested -- but per item, before the
    lead row of a report borrows fields from the report's other items (those are the other items' facts)."""
    from portal import technical_publish as P
    items = P.load_items(conn, version)
    by_event = {}
    for ev, p in items:
        rows, _st = P.compute([(ev, p)])
        rows = [{k: r.get(k) for k in _ROW_FIELDS} for r in rows if r.get("status")]
        if rows:
            by_event[ev["event_id"]] = rows
    return lambda it, ev: ({"rows": by_event[it["event_id"]]} if it["event_id"] in by_event else None)


if register_spec is not None:
    register_spec(TagSpec(
        name="technical", tag="Technical Reports (NI 43-101)", key_fields=TECH_KEY_FIELDS,
        report_fields=TECH_REPORT_FIELDS, judge=judge_technical, stored=stored_technical,
        from_records=_tech_from_records, candidate_predictor=_tech_candidate_predictor,
        describe={"row": "every row on the page is an NI 43-101 technical report an item reports -- filed, commissioned "
                         "or withdrawn, from a news release or a SEDAR+ filing",
                  "report_type": "property, resource, PEA, PFS, FS or other",
                  "project": "the project the report is on",
                  "status": "filed, commissioned or withdrawn, as of the item",
                  "effective_date": "the report's effective date",
                  "author_firm": "the firm that prepared the report",
                  "title": "the report's title (reported)",
                  "report_date": "the report's signing or issue date (reported)",
                  "filing_date": "when it was filed; a consent's signing date (reported)",
                  "amended": "an amended or revised report (reported)",
                  "qps": "the qualified persons who wrote it (reported)",
                  "metal": "the commodity (reported)",
                  "expected": "when a commissioned report is due (reported)",
                  "npv": "the study's NPV (reported)",
                  "irr": "the study's IRR (reported)",
                  "capex": "the study's initial capital (reported)"}))
