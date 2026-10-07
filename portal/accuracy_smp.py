"""How the Sampling & Geoscience Results page is scored (SMP_SPEC_V1, 2026-09-29).

The page shows ONE ROW PER SAMPLE TYPE per project a release reports results for (Justin, 2026-09-28/29): rock samples
(grab, chip, channel, trench), geochemistry (soil, till, sediment, other), geophysics (one row per survey method),
bulk and brine samples, and mapping findings. Historical results with a value are rows too, flagged historical, kept
apart from the new ones. A release is judged as a set of rows; a predicted row is paired with the labelled row it
claims to be before any field is scored.

Pairing, strongest first over the whole grid: a pair needs the same historical flag and either the same sample type,
or the same project with both types in the same group (rock / geochemistry / geophysics / other). For geophysics the
survey method counts as part of the type. The score adds the same type (4), an agreeing project (3) and an agreeing
best grade (1). Leftovers stay unpaired: a predicted row with no partner is a false row, a label with no partner a
missed one.

Key fields. Justin chose seven (sample type and project; best grade and metal; width for channel, chip and trench; the
anomaly or survey finding; the sample count). After four tuning rounds, each confirmed on a fresh blind sample, the
rules reader measured rows 89.7%, sample type 97.4%, project 90.8%, best grade 74.8%, width 77.3%, anomaly 46.3% and
sample count 61.4% on the last one, and Justin released it as an EARLY VERSION (2026-09-29): the gate holds row,
sample_type and project; best_grade, width_m, anomaly and sample_count are scored and reported on every run but do not
gate (SMP_EARLY_V1), with survey_type and historical.
- project agrees when the shared project-name helper calls the names the same, or their core words overlap;
- best_grade agrees on metal (letters compared, case and "+" ignored), unit (g/t = gpt = g/tonne; ppm, ppb, %, mg/L,
  oz/t kept apart) and value within 1.5% or one rounding step (0.05 of the last shown digit);
- width_m agrees within 1.5% or 0.05 m;
- anomaly agrees when the kinds of finding line up (both rows state one), the metal agrees where both give one, and
  the length and width agree within 5% where the label gives them;
- sample_count agrees exactly.
The label states every key field, blank where the release does not say, so a value the reader claims where the label
is blank is a false claim (both blank is set aside).

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

import re
import unicodedata

try:
    from portal.accuracy import TagSpec, register_spec
except Exception:  # pragma: no cover - standalone use of the judge
    TagSpec = register_spec = None

try:
    from portal import project_names as PN
except Exception:  # pragma: no cover
    PN = None

SMP_KEY_FIELDS = ("row", "sample_type", "project")
SMP_REPORT_FIELDS = ("best_grade", "width_m", "anomaly", "sample_count", "survey_type", "historical")

GROUP = {"grab": "rock", "chip": "rock", "channel": "rock", "trench": "rock", "soil": "geochem", "till": "geochem",
         "sediment": "geochem", "other_geochem": "geochem", "geophysics": "geophysics", "bulk": "other", "brine": "other",
         "mapping": "other"}

_GENERIC = {"the", "mine", "mines", "project", "projects", "property", "properties", "gold", "silver", "copper", "complex",
            "claims", "claim", "deposit", "and", "of", "de", "la", "del", "district", "area", "prospect", "block"}
_UNIT = {"g/t": "g/t", "gpt": "g/t", "g/tonne": "g/t", "grams per tonne": "g/t", "gram per tonne": "g/t", "ppm": "ppm",
         "ppb": "ppb", "%": "%", "mg/l": "mg/L", "oz/t": "oz/t", "opt": "oz/t", "oz/ton": "oz/t", "g/t pgm": "g/t"}


def _fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    return "".join(c for c in s if not unicodedata.combining(c))


def project_agrees(a, b):
    if not a or not b:
        return False
    if PN is not None:
        try:
            if PN.same(a, b):
                return True
        except Exception:  # pragma: no cover
            pass
    wa = {w for w in re.findall(r"[a-z0-9]+", _fold(a)) if w not in _GENERIC and len(w) > 1}
    wb = {w for w in re.findall(r"[a-z0-9]+", _fold(b)) if w not in _GENERIC and len(w) > 1}
    return bool(wa & wb)


def unit_key(u):
    u = (u or "").strip().lower()
    return _UNIT.get(u, u)


def metal_key(m):
    return re.sub(r"[^a-z0-9]", "", _fold(m)).replace("eq", "eq")


def _num_agrees(a, b, rel=0.015, abs_=0.0, rounding=False):
    """Within rel of b, or abs_, or (rounding) half a unit of b's last shown digit: a headline's 58 g/t agrees with the
    text's 58.07."""
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    step = 0.0
    if rounding:
        sb = ("%r" % b).rstrip("0").rstrip(".")
        step = 0.5 * 10 ** -(len(sb.split(".")[1]) if "." in sb else 0)
    return abs(a - b) <= max(rel * abs(b), abs_, step, 1e-9)


def grade_agrees(p, l):
    if not p or not l:
        return False
    if metal_key(p.get("metal")) != metal_key(l.get("metal")):
        return False
    if unit_key(p.get("unit")) != unit_key(l.get("unit")):
        return False
    return _num_agrees(p.get("value"), l.get("value"), rounding=True)


def anomaly_agrees(p, l):
    if not p or not l:
        return False
    if l.get("metal") and p.get("metal") and metal_key(p["metal"]) != metal_key(l["metal"]):
        return False
    for k in ("length_m", "width_m"):
        if l.get(k) is not None:
            if p.get(k) is None or not _num_agrees(p[k], l[k], 0.05):
                return False
    return True


def _empty(v):
    return v in (None, "", [], {})


def _type_of(r):
    t = r.get("sample_type")
    if t == "geophysics":
        return "geophysics:%s" % (r.get("survey_type") or "")
    return t


def _pair_score(lab, pr):
    if bool(lab.get("historical")) != bool(pr.get("historical")):
        return None
    same_t = lab.get("sample_type") == pr.get("sample_type")
    pa = project_agrees(lab.get("project"), pr.get("project")) or (not lab.get("project") and not pr.get("project"))
    if not same_t and not (pa and GROUP.get(lab.get("sample_type")) == GROUP.get(pr.get("sample_type"))):
        return None
    n = 1 + (4 if same_t else 0) + (3 if pa else 0)
    if same_t and _type_of(lab) == _type_of(pr):
        n += 2
    if grade_agrees(pr.get("best_grade"), lab.get("best_grade")):
        n += 1
    return n


def smp_match(labels, preds):
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
    """True / False / None (set aside)."""
    lv, pv = lab.get(f), pr.get(f)
    if f == "sample_type":
        return _type_of(lab) == _type_of(pr) if lv == "geophysics" and pv == "geophysics" else lv == pv
    if f == "historical":
        return bool(lv) == bool(pv)
    if _empty(lv):
        if f in ("project", "best_grade", "width_m", "anomaly", "sample_count") and not _empty(pv):
            return False
        return None
    if _empty(pv):
        return False
    if f == "project":
        return project_agrees(lv, pv)
    if f == "best_grade":
        return grade_agrees(pv, lv)
    if f == "width_m":
        return _num_agrees(pv, lv, 0.015, 0.05)
    if f == "anomaly":
        return anomaly_agrees(pv, lv)
    if f == "sample_count":
        try:
            return int(round(float(pv))) == int(round(float(lv)))
        except (TypeError, ValueError):
            return False
    return lv == pv


def judge_smp(pred, expect):
    """pred: None or {rows: [...]}; expect: {complete, rows: [...]}."""
    fields = SMP_KEY_FIELDS + SMP_REPORT_FIELDS
    out = {f: [] for f in fields}
    gold = list(expect.get("rows") or [])
    shown = list((pred or {}).get("rows") or [])
    if not shown:
        out["row"].extend(["fn"] * len(gold))
        return out
    if not gold:
        out["row"].extend(["fp"] * len(shown))
        return out
    pairs, extra = smp_match(gold, shown)
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
            claimed = not _empty(pr.get(f)) or f in ("sample_type", "historical")
            if ok:
                out[f].append("tp")
            elif claimed:
                out[f].extend(["fp", "fn"] if not _empty(lab.get(f)) else ["fp"])
            else:
                out[f].append("fn")
    if expect.get("complete", True):
        out["row"].extend(["fp"] * len(extra))
    return out


def self_test():
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))

    L = {"sample_type": "channel", "project": "Terragold", "best_grade": {"value": 22.2, "unit": "g/t", "metal": "Au"},
         "width_m": 1.0, "anomaly": None, "sample_count": None, "historical": False}
    P = dict(L, project="Terragold Project", best_grade={"value": 22.2, "unit": "gpt", "metal": "au"})
    r = judge_smp({"rows": [P]}, {"rows": [L]})
    eq("all right", [r[f] for f in ("row", "sample_type", "project", "best_grade", "width_m", "anomaly", "sample_count")],
       [["tp"], ["tp"], ["tp"], ["tp"], ["tp"], [], []])
    eq("early version: row, type and project gate", SMP_KEY_FIELDS, ("row", "sample_type", "project"))
    r = judge_smp({"rows": [dict(P, sample_count=22, width_m=1.5)]}, {"rows": [L]})
    eq("count claimed on a blank label; wrong width", (r["sample_count"], r["width_m"]), (["fp"], ["fp", "fn"]))
    r = judge_smp({"rows": [dict(P, sample_type="grab")]}, {"rows": [L]})
    eq("same project, same group: paired, type wrong", (r["row"], r["sample_type"]), (["tp"], ["fp", "fn"]))
    r = judge_smp({"rows": [dict(P, historical=True)]}, {"rows": [L]})
    eq("historical never pairs with new", r["row"], ["fn", "fp"])
    r = judge_smp({"rows": [dict(P, sample_type="soil", project="Other")]}, {"rows": [L]})
    eq("different group never pairs", r["row"], ["fn", "fp"])
    eq("rounding", (grade_agrees({"value": 58.07, "unit": "g/t", "metal": "Au"}, {"value": 58, "unit": "g/t", "metal": "Au"}),
                    grade_agrees({"value": 5.4, "unit": "g/t", "metal": "Au"}, {"value": 5.26, "unit": "g/t", "metal": "Au"}),
                    grade_agrees({"value": 1.7, "unit": "%", "metal": "Cu"}, {"value": 17000, "unit": "ppm", "metal": "Cu"})),
       (True, False, False))
    A = {"sample_type": "soil", "project": "Khaleesi", "best_grade": None, "width_m": None, "sample_count": 400,
         "anomaly": {"kind": "anomaly", "metal": "Cu", "length_m": 1900, "width_m": 650}, "historical": False}
    r = judge_smp({"rows": [dict(A, anomaly={"kind": "anomaly", "metal": "Cu", "length_m": 1900, "width_m": None})]}, {"rows": [A]})
    eq("anomaly width missing", r["anomaly"], ["fp", "fn"])
    G = {"sample_type": "geophysics", "survey_type": "IP", "project": "Oakes", "best_grade": None, "width_m": None,
         "sample_count": None, "anomaly": {"kind": "anomaly", "metal": None, "length_m": None, "width_m": None}, "historical": False}
    r = judge_smp({"rows": [dict(G, survey_type="magnetics"), G]}, {"rows": [G]})
    eq("geophysics method picks the pair", (r["row"], r["sample_type"]), (["tp", "fp"], ["tp"]))
    print("accuracy_smp: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


def stored_smp(conn, event_id):
    """What /sampling shows for one release today (the published table), as a prediction."""
    import json as _json
    try:
        rs = conn.execute("SELECT sample_type, survey_type, project, historical, grade, grade_unit, grade_metal, width_m, "
                          "anomaly_json, sample_count FROM sampling_results WHERE event_id=? AND sample_type IS NOT NULL "
                          "ORDER BY ordinal", (event_id,)).fetchall()
    except Exception:  # noqa: BLE001  (no table before the first publish)
        return None
    if not rs:
        return None
    rows = []
    for st, sv, pj, hist, g, gu, gm, w, aj, n in rs:
        rows.append({"sample_type": st, "survey_type": sv, "project": pj, "historical": bool(hist),
                     "best_grade": ({"value": g, "unit": gu, "metal": gm} if g is not None else None), "width_m": w,
                     "anomaly": _json.loads(aj) if aj else None, "sample_count": n})
    return {"rows": rows}


def _smp_from_records(records):
    from portal.extractors import sampling as X
    return X.to_prediction(records)


if register_spec is not None:
    register_spec(TagSpec(
        name="sampling", tag="Sampling & Geoscience Results", key_fields=SMP_KEY_FIELDS,
        report_fields=SMP_REPORT_FIELDS, judge=judge_smp, stored=stored_smp, from_records=_smp_from_records,
        project_labels=("rows", "project"),
        describe={"row": "every row on the page is one sample type's results on one project in a release (historical results "
                         "with a value are their own rows)",
                  "sample_type": "grab, chip, channel, trench, soil, till, sediment, other geochemistry, geophysics (by survey "
                                 "method), bulk, brine or mapping",
                  "project": "the project or property as the release names it",
                  "best_grade": "the best grade for that sample type, with its unit and metal",
                  "width_m": "the length a channel, chip or trench grade is over, in metres",
                  "anomaly": "the anomaly or conductor a geochemical or geophysical survey found: metal and size",
                  "sample_count": "how many samples the results come from",
                  "survey_type": "the geophysical method (reported)",
                  "historical": "historical results (reported; part of the row key)"}))

if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test() else 0)
