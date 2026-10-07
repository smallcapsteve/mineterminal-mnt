"""How /permits is scored (PERMIT_SPEC_V1, 2026-09-22).

The page shows ONE ROW PER PERMIT OR GOVERNMENT APPROVAL an item reports: drill and exploration permits, environmental
assessments, plans of operations and notices, mining licences, construction and operating permits, water permits,
land-access and community agreements and government actions, each at its stage as of the item -- planned, applied,
in review, granted, renewed or contested. Justin, 2026-09-22. A release is judged as a set of rows; a predicted row is
paired with the labelled row it claims to be before any field is scored.

Pairing, strongest first over the whole grid: a row can only pair with a label on an agreeing project (or either
project unstated); among those, the score adds the same permit type (3), status (3), agreeing authority (2) and an
overlapping permit name (1). Leftovers stay unpaired: a predicted row with no partner is a false row, a label with no
partner a missed one.

Project names are compared as sets of words once generic words ('Project', 'Property', 'Mine', commodity words) are
dropped. An authority agrees when one name's core words fall inside the other's, or when an acronym one of them
gives ('BLM', 'SEMARNAT', 'APA') appears in the other. A field the label does not state is set aside rather than judged.

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

import re
import unicodedata

try:
    from portal.accuracy import TagSpec, register_spec
except Exception:  # pragma: no cover - standalone use of the judge
    TagSpec = register_spec = None

PERMIT_KEY_FIELDS = ("row", "permit_type", "project", "status", "authority", "date")
PERMIT_REPORT_FIELDS = ("permit_name", "permit_id", "expiry", "jurisdiction", "metal", "term")  # ACC_COLS_V1: term is on the page

_ROW_FIELDS = ("permit_type", "project", "status", "authority", "date", "permit_name", "permit_id", "term", "expiry",
               "scope", "holder", "jurisdiction", "metal", "evidence", "chain_key", "stage_rank", "latest")

_GENERIC = {"the", "a", "an", "of", "and", "de", "del", "la", "project", "projects", "property", "properties",
            "claims", "claim", "block", "area", "mine", "mines", "deposit", "deposits", "gold", "silver", "copper",
            "lithium", "uranium", "nickel", "antimony", "tungsten", "potash", "phosphate", "molybdenum", "graphite",
            "critical", "minerals", "mineral", "metals", "polymetallic", "pge", "zinc", "lead", "cu", "au", "ni",
            "co", "1", "north", "south", "east", "west", "ep", "brine", "silica", "rare", "earths", "earth"}
_AUTH_GENERIC = {"the", "of", "and", "for", "de", "del", "la", "do", "da", "des", "du", "et", "ministry", "ministere",
                 "department", "government", "province", "state", "provincial", "federal", "secretariat", "secretaria",
                 "agency", "office", "u", "s", "us", "usa", "canada", "canadian", "national", "general", "directorate",
                 "commission", "nacional", "administration", "authority", "bureau", "service", "services", "council"}


def _fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    return "".join(c for c in s if not unicodedata.combining(c))


def _words(s, generic=_GENERIC):
    return {w for w in re.findall(r"[a-z0-9&]+", _fold(s)) if w not in generic}


def _one_edit(x, y):
    if abs(len(x) - len(y)) > 1 or min(len(x), len(y)) < 4:
        return False
    if len(x) == len(y):
        return sum(a != b for a, b in zip(x, y)) == 1
    if len(x) > len(y):
        x, y = y, x
    return any(y[:i] + y[i + 1:] == x for i in range(len(y)))


def _within(small, big):
    return all(w in big or any(_one_edit(w, v) for v in big) for w in small)


def name_agrees(a, b):
    """Same words once generic ones are dropped; a one-letter typo ('Lago'/'Lagoa') still agrees."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return _fold(a).strip() == _fold(b).strip()
    return wa <= wb or wb <= wa or _within(wa, wb) or _within(wb, wa)


def _acronyms(s):
    s = str(s or "")
    out = {x.lower() for x in re.findall(r"\b([A-Z][A-Z0-9&]{1,9})\b", s)}
    ws = [w for w in re.findall(r"[A-Za-z]+", s) if w[0].isupper() and w.lower() not in ("of", "and", "the", "for")]
    if len(ws) >= 2:
        out.add("".join(w[0] for w in ws).lower())
    return out


def authority_agrees(lab, pred):
    if not lab or not pred:
        return False
    fl, fp = _fold(lab), _fold(pred)
    if fl.strip() == fp.strip():
        return True
    al, ap = _acronyms(lab), _acronyms(pred)
    wl, wp = _words(lab, _AUTH_GENERIC), _words(pred, _AUTH_GENERIC)
    if (al & ap) or (al & wp) or (ap & wl):
        return True
    if not wl or not wp:
        return False
    return wl <= wp or wp <= wl or len(wl & wp) / len(wl | wp) >= 0.5


def _name_overlap(a, b):
    wa, wb = _words(a, {"the", "of", "a", "an", "and", "for"}), _words(b, {"the", "of", "a", "an", "and", "for"})
    return bool(wa and wb and (wa & wb))


def _pair_score(lab, pr):
    lp, pp = lab.get("project"), pr.get("project")
    if lp and pp and not name_agrees(lp, pp):
        return None
    n = 1
    if lab.get("permit_type") == pr.get("permit_type"):
        n += 3
    if lab.get("status") == pr.get("status"):
        n += 3
    if authority_agrees(lab.get("authority"), pr.get("authority")):
        n += 2
    if _name_overlap(lab.get("permit_name"), pr.get("permit_name")):
        n += 1
    return n


def permit_match(labels, preds):
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
    if f in ("status", "permit_type"):
        return lv == pv
    if lv is None or lv == "" or lv == []:
        return None
    if f == "project":
        return pv is not None and name_agrees(lv, pv)
    if f == "authority":
        return pv is not None and authority_agrees(lv, pv)
    if f == "permit_name":
        return pv is not None and _name_overlap(lv, pv)
    if f == "permit_id":
        return pv is not None and bool(set(re.findall(r"\d{3,}", str(lv))) & set(re.findall(r"\d{3,}", str(pv))))
    if f == "jurisdiction":
        return pv is not None and bool(_words(lv, {"usa", "us", "the", "of"}) & _words(pv, {"usa", "us", "the", "of"}))
    if f == "metal":
        return pv is not None and bool(set(_fold(lv).split("+")) & set(_fold(pv).split("+")))
    if f == "term":  # ACC_COLS_V1: "20 years" / "a 20-year permit" / "until August 21, 2040": the numbers agree
        nums = lambda x: set(re.findall(r"\d+", str(x))) | ({w for w in re.findall(r"[a-z]+", _fold(str(x)))} &
                         {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"})
        return pv is not None and (_fold(lv) == _fold(pv) or bool(nums(lv) & nums(pv)))
    return _fold(lv) == _fold(pv)


def judge_permits(pred, expect):
    """pred: None or {rows: [...]}; expect: {complete, rows: [...]}."""
    fields = PERMIT_KEY_FIELDS + PERMIT_REPORT_FIELDS
    out = {f: [] for f in fields}
    gold = list(expect.get("rows") or [])
    shown = list((pred or {}).get("rows") or [])
    if not shown:
        out["row"].extend(["fn"] * len(gold))
        return out
    if not gold:
        out["row"].extend(["fp"] * len(shown))
        return out
    pairs, extra = permit_match(gold, shown)
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
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name='permits'").fetchone() is not None


def stored_permits(conn, event_id):
    """What /permits shows for one item. A marker row (status NULL) states nothing."""
    if not _table_exists(conn):
        return None
    rows = list(conn.execute(
        "SELECT " + ", ".join(_ROW_FIELDS) + " FROM permits WHERE event_id=? AND status IS NOT NULL "
        "ORDER BY ordinal", (event_id,)))
    return {"rows": [dict(zip(_ROW_FIELDS, r)) for r in rows]} if rows else None


def _permits_from_records(records):
    from portal.extractors import permits as X
    return X.to_prediction(records)


def _permits_candidate_predictor(conn, extractor, version):
    """Scored through the publisher, so what the page would show is what is tested."""
    from portal import permits_publish as P
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
        name="permits", tag="Permits & Approvals", key_fields=PERMIT_KEY_FIELDS,
        report_fields=PERMIT_REPORT_FIELDS, judge=judge_permits, stored=stored_permits,
        from_records=_permits_from_records, candidate_predictor=_permits_candidate_predictor,
        describe={"row": "every row on the page is a permit or government approval an item reports -- planned, applied, "
                         "in review, granted, renewed or contested",
                  "permit_type": "drill/exploration, environmental assessment, plan of operations, mining licence, "
                                 "construction/operating, water, land/community, government/policy or other",
                  "project": "the project the permit is for",
                  "status": "the permit's stage as of the item",
                  "authority": "the body that issues or reviews it (or the community, for an agreement)",
                  "date": "the date of the stage (the item's date unless another is stated)",
                  "permit_name": "the permit as the item names it (reported)",
                  "permit_id": "a permit or file number (reported)",
                  "expiry": "when it expires (reported)",
                  "jurisdiction": "province/state and country (reported)",
                  "metal": "the commodity (reported)"}))
