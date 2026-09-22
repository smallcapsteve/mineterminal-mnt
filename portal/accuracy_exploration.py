"""How /exploration-programs is scored (EXPL_SPEC_V1, 2026-09-21).

The page shows ONE ROW PER FIELD PROGRAM a release reports: drilling, geophysics or ground work (sampling,
mapping, prospecting, trenching), planned, started, underway or completed -- the issuer's own programs and, with
`historical` set, those of previous owners (Justin, 2026-09-21). A release is judged as a set of rows; a
predicted row is paired with the labelled row it claims to be before any field is scored.

Pairing, strongest first over the whole grid: a row can only pair with a label of the same program_type on an
agreeing project (or either project unstated); among those, the score adds agreeing season (3), status (2),
phase (2), metres within 1% (2), holes (1) and the same historical flag (2). Leftovers stay unpaired: a predicted
row with no partner is a false row, a label with no partner a missed one.

Project names are compared as sets of words once generic words are dropped ('Kendal Ridge' = 'Kendal'; 'Golden
Culvert-WIN' = 'Golden Culvert'), or when both start with the same distinctive word. Metres agree within 1%,
holes exactly. A field the label does not state is set aside rather than judged.

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

import re
import unicodedata

from portal.accuracy import TagSpec, register_spec

EXPL_KEY_FIELDS = ("row", "program_type", "project", "status", "metres", "holes")
EXPL_REPORT_FIELDS = ("season", "phase", "historical", "operator", "drill_method", "survey_type", "line_km",
                      "budget", "target_metal", "contractor", "rigs")

_ROW_FIELDS = ("program_type", "project", "status", "metres", "holes", "season", "phase", "historical", "operator",
               "drill_method", "survey_type", "line_km", "budget", "currency", "target_metal", "contractor", "rigs",
               "start_date", "end_date", "best_grade", "best_unit", "best_metal", "best_sample_type")

_GENERIC = {"the", "a", "an", "of", "and", "de", "del", "la", "project", "projects", "property", "properties",
            "claims", "claim", "block", "area", "areas", "target", "targets", "zone", "zones", "prospect", "mine",
            "deposit", "ep", "permit", "permits", "license", "licence", "gold", "silver", "copper", "lithium",
            "uranium", "nickel", "antimony", "tungsten", "critical", "minerals", "mineral", "polymetallic", "vms",
            "exploration", "trend", "belt", "district", "camp", "range", "ridge", "north", "south", "east", "west",
            "main", "central", "upper", "lower", "greater"}
_WEAK = {"los", "las", "el", "san", "santa", "lake", "lakes", "river", "mountain", "hill", "hills", "creek", "big",
         "little", "new", "red", "black", "white", "grand", "golden", "cerro", "mount", "mt"}


def _fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    return "".join(c for c in s if not unicodedata.combining(c))


def _words(s):
    return {w for w in re.findall(r"[a-z0-9]+", _fold(s)) if w not in _GENERIC}


def _first_word(s):
    for w in re.findall(r"[a-z0-9]+", _fold(s)):
        if w not in _GENERIC:
            return w
    return None


def name_agrees(a, b):
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    if wa <= wb or wb <= wa:
        return True
    fa, fb = _first_word(a), _first_word(b)
    return bool(fa) and fa == fb and fa not in _WEAK


def _close(a, b, rel=0.01):
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= rel * max(abs(float(a)), abs(float(b)))


def _years(s):
    return set(re.findall(r"(?:19|20)\d\d", str(s or "")))


def season_agrees(a, b):
    ya, yb = _years(a), _years(b)
    if ya and yb:
        return bool(ya & yb)
    return _fold(a).strip() == _fold(b).strip()


def _phase_num(s):
    m = re.search(r"(\d+|i{1,3}v?|one|two|three|four)\b", _fold(s))
    if not m:
        return None
    v = m.group(1)
    return {"i": "1", "ii": "2", "iii": "3", "iv": "4", "one": "1", "two": "2", "three": "3", "four": "4"}.get(v, v)


def _pair_score(lab, pr):
    if lab.get("program_type") != pr.get("program_type"):
        return None
    lp, pp = lab.get("project"), pr.get("project")
    if lp and pp and not name_agrees(lp, pp):
        return None
    n = 1
    if lab.get("season") and pr.get("season") and season_agrees(lab["season"], pr["season"]):
        n += 3
    if lab.get("status") == pr.get("status"):
        n += 2
    if lab.get("phase") and pr.get("phase") and _phase_num(lab["phase"]) == _phase_num(pr["phase"]):
        n += 2
    if lab.get("metres") is not None and _close(lab.get("metres"), pr.get("metres")):
        n += 2
    if lab.get("holes") is not None and pr.get("holes") is not None and int(lab["holes"]) == int(pr["holes"]):
        n += 1
    if bool(lab.get("historical")) == bool(pr.get("historical")):
        n += 2
    return n


def expl_match(labels, preds):
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
    if f == "program_type":
        return lv == pv
    if f == "historical":
        return bool(lv) == bool(pv)
    if lv is None or lv == "":
        return None
    if f in ("project", "contractor", "operator"):
        return name_agrees(lv, pv)
    if f in ("metres", "line_km", "budget"):
        return _close(lv, pv)
    if f in ("holes", "rigs"):
        return pv is not None and int(lv) == int(pv)
    if f == "season":
        return pv is not None and season_agrees(lv, pv)
    if f == "phase":
        return pv is not None and _phase_num(lv) == _phase_num(pv)
    if f == "target_metal":
        return pv is not None and bool(set(_fold(lv).split("+")) & set(_fold(pv).split("+")))
    return _fold(lv) == _fold(pv)


def judge_exploration(pred, expect):
    """pred: None or {rows: [...]}; expect: {complete, rows: [...]} (the fields in _ROW_FIELDS)."""
    fields = EXPL_KEY_FIELDS + EXPL_REPORT_FIELDS
    out = {f: [] for f in fields}
    gold = list(expect.get("rows") or [])
    shown = list((pred or {}).get("rows") or [])
    if not shown:
        out["row"].extend(["fn"] * len(gold))
        return out
    if not gold:
        out["row"].extend(["fp"] * len(shown))
        return out
    pairs, extra = expl_match(gold, shown)
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
            elif pr.get(f) not in (None, ""):
                out[f].extend(["fp", "fn"])
            else:
                out[f].append("fn")
    if expect.get("complete", True):
        out["row"].extend(["fp"] * len(extra))
    return out


def _table_exists(conn):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name='exploration_programs'").fetchone() is not None


def stored_exploration(conn, event_id):
    """What /exploration-programs shows for one release. A marker row (program_type NULL) states nothing."""
    if not _table_exists(conn):
        return None
    rows = list(conn.execute(
        "SELECT " + ", ".join(_ROW_FIELDS) + " FROM exploration_programs WHERE event_id=? AND program_type IS NOT NULL "
        "ORDER BY ordinal", (event_id,)))
    return {"rows": [dict(zip(_ROW_FIELDS, r)) for r in rows]} if rows else None


def _expl_from_records(records):
    from portal.extractors import exploration as X
    return X.to_prediction(records)


def _expl_candidate_predictor(conn, extractor, version):
    """Scored through the publisher, so what the page would show is what is tested."""
    from portal import exploration_publish as P
    rows, _st = P.compute(P.load_items(conn, version))
    by_event = {}
    for r in rows:
        if r["program_type"] is None:
            continue
        by_event.setdefault(r["event_id"], []).append({k: r.get(k) for k in _ROW_FIELDS})
    return lambda it, ev: ({"rows": by_event[it["event_id"]]} if it["event_id"] in by_event else None)


register_spec(TagSpec(
    name="exploration", tag="Exploration Programs", key_fields=EXPL_KEY_FIELDS, report_fields=EXPL_REPORT_FIELDS,
    judge=judge_exploration, stored=stored_exploration, from_records=_expl_from_records,
    candidate_predictor=_expl_candidate_predictor,
    describe={"row": "every row on the page is a field program the release reports -- drilling, geophysics or ground "
                     "work, planned, started, underway or completed, the issuer's or a previous owner's",
              "program_type": "drilling, geophysics or ground",
              "project": "the project or property the program is on",
              "status": "planned, started, underway or completed, as of the release",
              "metres": "the program's metres (planned, drilled to date, or completed)",
              "holes": "the program's holes",
              "season": "the season or year (reported)",
              "phase": "the phase (reported)",
              "historical": "a previous owner's program (reported)",
              "operator": "the previous owner that ran it (reported)",
              "drill_method": "diamond, RC and so on (reported)",
              "survey_type": "IP, magnetic, soil, mapping and so on (reported)",
              "line_km": "the survey size (reported)",
              "budget": "the program budget (reported)",
              "target_metal": "the commodity targeted (reported)",
              "contractor": "the drill or survey contractor (reported)",
              "rigs": "the number of rigs (reported)"}))
