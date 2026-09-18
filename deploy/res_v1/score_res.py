# -*- coding: utf-8 -*-
"""Score RES_V1's answers against the draft labels (2026-09-17).

Reports precision and recall per key field, plus every disagreement, so one relay round trip is a
complete iteration.

Items marked `complete: false` in the labels have a known-partial row list. Their matched rows are
scored for precision and their unmatched predicted rows are set aside as unjudgeable rather than
counted wrong; they are left out of recall entirely, so a partial list cannot flatter the score.

Usage: score_res.py <predictions.json>
"""
import json
import re
import sys

KEY_FIELDS = ("row", "deposit", "category", "tonnes", "grade", "context")
_DEP_NOISE = re.compile(r"(?i)\b(project|deposit|mine|property|zone|prospect|the|mineral|resources?|"
                        r"open\s*pit|op|underground|ug)\b")


def norm_dep(d):
    if not d:
        return ""
    s = _DEP_NOISE.sub(" ", str(d))
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def close(a, b, tol=0.02):
    if a is None or b is None:
        return a is None and b is None
    hi = max(abs(a), abs(b))
    return hi == 0 or abs(a - b) <= tol * hi


_UNIT_BASE = {"oz": 1.0, "koz": 1e3, "moz": 1e6, "lb": 1.0, "mlb": 1e6, "mlbs": 1e6, "lbs": 1.0,
              "klb": 1e3, "t": 1.0, "kt": 1e3, "mt": 1e6, "kg": 1.0, "ct": 1.0}


def base_of(v, unit):
    if v is None:
        return None
    u = (unit or "").lower()
    mult = _UNIT_BASE.get(u, 1.0)
    fam = {"koz": "oz", "moz": "oz", "mlb": "lb", "mlbs": "lb", "lbs": "lb", "klb": "lb",
           "kt": "t", "mt": "t"}.get(u, u)
    return (fam, v * mult)


def grades_agree(want, got):
    """Every grade the label names is present with the same value; extra metals are allowed."""
    if not want:
        return True
    gm = {}
    for x in got or []:
        if x[0] is not None:
            gm.setdefault(x[0], []).append(x[1])
    for w in want:
        met, val = w.get("metal"), w.get("value")
        if val is None:
            continue
        if met not in gm or not any(close(val, v, 0.011) for v in gm[met]):
            return False
    return True


def load_pred(path):
    raw = open(path).read()
    if "###SET###" in raw:
        raw = raw.split("###SET###", 1)[1]
    raw = raw.split("###COUNTS###", 1)[0].strip()
    out = {}
    for item in json.loads(raw):
        rows = []
        for r in item["r"]:
            rows.append({"deposit": r[0], "category": r[1], "tonnes": r[2], "grades": r[3],
                         "contained": r[4], "cut_off": r[5], "basis": r[6], "context": r[7],
                         "source": r[8]})
        out[item["e"]] = {"ticker": item["t"], "mre_type": item["m"], "announces": item["a"],
                          "project": item["p"], "rows": rows}
    return out


def match(labels, preds):
    """Pair predicted rows to labelled rows: deposit and category first, then tonnage."""
    pairs, used = [], set()
    for li, lab in enumerate(labels):
        best = None
        for pi, p in enumerate(preds):
            if pi in used or p["category"] != lab["category"] or p["basis"] != lab["basis"]:
                continue
            score = 0
            if norm_dep(p["deposit"]) == norm_dep(lab["deposit"]):
                score += 2
            if lab["tonnes"] and close(p["tonnes"], lab["tonnes"]):
                score += 2
            elif lab["tonnes"] is None and p["tonnes"] is None:
                score += 1
            if score and (best is None or score > best[0]):
                best = (score, pi)
        if best:
            used.add(best[1])
            pairs.append((li, best[1]))
        else:
            pairs.append((li, None))
    extra = [pi for pi in range(len(preds)) if pi not in used]
    return pairs, extra


def main(argv):
    preds = load_pred(argv[0])
    labels = json.load(open(argv[1] if len(argv) > 1 else "res_labels_draft.json"))
    hit = {k: 0 for k in KEY_FIELDS}
    claimed = {k: 0 for k in KEY_FIELDS}
    want = {k: 0 for k in KEY_FIELDS}
    found = {k: 0 for k in KEY_FIELDS}
    unjudged = 0
    det = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    notes = []

    for item in labels["items"]:
        eid = item["event_id"]
        p = preds.get(eid)
        if p is None:
            notes.append("MISSING prediction for %s %s" % (eid, item["ticker"]))
            continue
        lab_rows, pr_rows = item["rows"], p["rows"]
        if lab_rows and pr_rows:
            det["tp"] += 1
        elif lab_rows and not pr_rows:
            det["fn"] += 1
            notes.append("MISSED  %s %s  %d labelled rows, none found" % (eid, item["ticker"], len(lab_rows)))
        elif pr_rows and not lab_rows:
            det["fp"] += 1
            notes.append("EXTRA   %s %s  no estimate labelled, %d rows found: %s"
                         % (eid, item["ticker"], len(pr_rows),
                            "; ".join("%s/%s" % (r["deposit"], r["category"]) for r in pr_rows[:3])))
        else:
            det["tn"] += 1

        pairs, extra = match(lab_rows, pr_rows)
        for li, pi in pairs:
            lab = lab_rows[li]
            if item["complete"]:
                want["row"] += 1
            if pi is None:
                if item["complete"]:
                    notes.append("no row  %s %s  %s / %s" % (eid, item["ticker"], lab["deposit"], lab["category"]))
                continue
            pr = pr_rows[pi]
            claimed["row"] += 1
            hit["row"] += 1
            if item["complete"]:
                found["row"] += 1
            for f, ok, has_label, has_pred in (
                    ("deposit", norm_dep(pr["deposit"]) == norm_dep(lab["deposit"]),
                     bool(lab["deposit"]), bool(pr["deposit"])),
                    ("category", pr["category"] == lab["category"], True, True),
                    ("tonnes", close(pr["tonnes"], lab["tonnes"]),
                     lab["tonnes"] is not None, pr["tonnes"] is not None),
                    ("grade", grades_agree(lab["grades"], pr["grades"]),
                     bool(lab["grades"]), bool(pr["grades"])),
                    ("context", pr["context"] == lab["context"], True, True)):
                if has_pred:
                    claimed[f] += 1
                    hit[f] += 1 if ok else 0
                if has_label and item["complete"]:
                    want[f] += 1
                    found[f] += 1 if (has_pred and ok) else 0
                if has_label and has_pred and not ok:
                    notes.append("%-8s %s %s  %s/%s: want %r got %r" % (
                        f, eid, item["ticker"], lab["deposit"], lab["category"],
                        lab[f] if f != "grade" else [(g.get("metal"), g.get("value")) for g in lab["grades"]],
                        pr[f] if f != "grade" else [(g[0], g[1]) for g in pr["grades"]]))
        for pi in extra:
            if item["complete"]:
                claimed["row"] += 1
                pr = pr_rows[pi]
                notes.append("extra   %s %s  %s / %s  t=%s ctx=%s src=%s" % (
                    eid, item["ticker"], pr["deposit"], pr["category"], pr["tonnes"],
                    pr["context"], pr["source"]))
            else:
                unjudged += 1

    print("detection: right %d, missed %d, spurious %d, correctly empty %d"
          % (det["tp"], det["fn"], det["fp"], det["tn"]))
    print("%-9s %9s %9s" % ("field", "precision", "recall"))
    for f in KEY_FIELDS:
        pr = 100.0 * hit[f] / claimed[f] if claimed[f] else 0.0
        rc = 100.0 * found[f] / want[f] if want[f] else 0.0
        flag = "" if pr >= 90 else "   <-- under 90"
        print("%-9s %6.1f%% (%d/%d) %6.1f%% (%d/%d)%s"
              % (f, pr, hit[f], claimed[f], rc, found[f], want[f], flag))
    print("unjudgeable rows on partial items:", unjudged)
    print("\n--- disagreements (%d) ---" % len(notes))
    for n in notes:
        print(n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
