"""How /resources is scored (RES_SPEC_V1, 2026-09-18).

The page shows ONE ROW PER DEPOSIT PER CATEGORY (Justin, 2026-09-18), a different shape again from
the other tags, so a release is judged as a set of figures rather than as one row. A predicted row is
paired with an expected one by category and basis first, then by deposit name and tonnage, and only
then are its figures scored. A predicted row that pairs with nothing is a figure the page invented.

Two rules matter as much as the pairing, and both exist because an early version of this scorer
measured the labels rather than the reader:

  * A field the label does not state cannot be judged. A label that gives a tonnage and no grade
    says nothing about the grade, so a grade the reader found there is set aside, not counted wrong.
  * Fourteen of the fifty items have `complete: false`: their row list is known to be partial, so
    unmatched predicted rows on those items are unjudgeable and they are left out of recall. Their
    matched rows are still scored for precision, which is what the gate reads -- so `row` carries
    every claim, and the reported field `row_complete` repeats the exercise over the 36 fully
    labelled items alone, where precision and recall are both honest.

Deposit names are compared as names, not transcriptions: accents folded, one- and two-letter tokens
dropped ("East Bull in-pit" was failing on the word "in"), one name allowed to refine the other
("Gate" against "MPD - Gate"), and a single-character difference forgiven on words of five letters
or more, because Silvercorp spells one deposit "Soledad" and then "Soldedad" in the same release.

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

import json
import re
import unicodedata

from portal.accuracy import TagSpec, register_spec

RES_KEY_FIELDS = ("row", "deposit", "category", "tonnes", "grade", "context")
RES_REPORT_FIELDS = ("row_complete",)

_DEP_NOISE = re.compile(r"(?i)\b(project|deposit|mine|property|zone|prospect|the|mineral|resources?|"
                        r"open\s*pit|op|underground|ug)\b")


def norm_dep(d):
    if not d:
        return ""
    s = "".join(c for c in unicodedata.normalize("NFKD", str(d)) if not unicodedata.combining(c))
    s = _DEP_NOISE.sub(" ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    # one- and two-letter tokens are prepositions, not names: "East Bull in-pit" against
    # "EAST BULL PALLADIUM (Pit Constrained)" was failing on the word "in"
    toks = [t for t in re.sub(r"\s+", " ", s).strip().lower().split() if len(t) > 2 or t.isdigit()]
    return " ".join(toks)


def _near(x, y):
    """True when x and y differ by one character: one swap, one insertion or one deletion."""
    if abs(len(x) - len(y)) > 1:
        return False
    if len(x) == len(y):
        return sum(1 for p, q in zip(x, y) if p != q) == 1
    short, long_ = (x, y) if len(x) < len(y) else (y, x)
    for i in range(len(long_)):
        if long_[:i] + long_[i + 1:] == short:
            return True
    return False


def dep_ok(want, got):
    """Right when one name refines the other: 'Gate' against 'MPD - Gate', 'True North' against
    'True North Gold'. A deposit name has no single correct spelling, and holding the reader to the
    label's exact wording measures transcription, not reading."""
    a, b = set(norm_dep(want).split()), set(norm_dep(got).split())
    if not a and not b:
        return True
    if not a or not b:
        return False

    def covered(x, ys):
        return any(x == y or (min(len(x), len(y)) >= 5 and _near(x, y)) for y in ys)

    return all(covered(x, b) for x in a) or all(covered(x, a) for x in b)


def res_close(a, b, tol=0.02):
    if a is None or b is None:
        return a is None and b is None
    hi = max(abs(a), abs(b))
    return hi == 0 or abs(a - b) <= tol * hi


def _fig(x):
    """A grade or contained figure, whether it arrives as a dict or as [metal, value, unit]."""
    if isinstance(x, dict):
        return x.get("metal"), x.get("value"), x.get("unit")
    x = list(x) + [None, None, None]
    return x[0], x[1], x[2]


def grades_agree(want, got):
    """Every grade the label names is present with the same value; extra metals are allowed."""
    if not want:
        return True
    gm = {}
    for g in got or []:
        met, val, _u = _fig(g)
        if met is not None:
            gm.setdefault(met, []).append(val)
    for w in want:
        met, val, _u = _fig(w)
        if val is None:
            continue
        if met not in gm or not any(res_close(val, v, 0.011) for v in gm[met]):
            return False
    return True


def res_match(labels, preds):
    """Pair predicted rows to labelled rows: category and basis must agree, then deposit and tonnage
    decide which of several candidates it is."""
    pairs, used = [], set()
    for li, lab in enumerate(labels):
        best = None
        for pi, p in enumerate(preds):
            if pi in used or p.get("category") != lab.get("category") \
                    or (p.get("basis") or "resource") != (lab.get("basis") or "resource"):
                continue
            score = 0
            if dep_ok(lab.get("deposit"), p.get("deposit")):
                score += 2
            if lab.get("tonnes") and res_close(p.get("tonnes"), lab.get("tonnes")):
                score += 2
            elif lab.get("tonnes") is None and p.get("tonnes") is None:
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


def judge_resources(pred, expect):
    """pred: None or {mre_type, rows: [{deposit, category, tonnes, grades, contained, cut_off,
    basis, context}]}; expect: {is_resource_estimate, complete, rows: [the same shape]}

    row       a figure on the page is one the release states, and every one it states is shown
    deposit   the figure is filed under the deposit the release attributes it to
    category  measured / indicated / inferred / proven / probable / total matches
    tonnes    the ore tonnage, within 2%
    grade     every grade the label names is on the row with the same value
    context   announced by this release, or a previously reported estimate it restates
    """
    out = {f: [] for f in RES_KEY_FIELDS + RES_REPORT_FIELDS}
    gold = list(expect.get("rows") or [])
    want = bool(expect.get("is_resource_estimate")) and bool(gold)
    complete = bool(expect.get("complete"))
    shown = list((pred or {}).get("rows") or [])

    if not shown:
        if want:
            for _ in gold:
                out["row"].append("fn")
                if complete:
                    out["row_complete"].append("fn")
        return out
    if not want:
        for _ in shown:
            out["row"].append("fp")
            if complete:
                out["row_complete"].append("fp")
        return out

    pairs, extra = res_match(gold, shown)
    for li, pi in pairs:
        lab = gold[li]
        if pi is None:
            if complete:
                out["row"].append("fn")
                out["row_complete"].append("fn")
            continue
        pr = shown[pi]
        out["row"].append("tp")
        if complete:
            out["row_complete"].append("tp")
        for f, ok, has_label, has_pred in (
                ("deposit", dep_ok(lab.get("deposit"), pr.get("deposit")),
                 bool(lab.get("deposit")), bool(pr.get("deposit"))),
                ("category", pr.get("category") == lab.get("category"), True, True),
                ("tonnes", res_close(pr.get("tonnes"), lab.get("tonnes")),
                 lab.get("tonnes") is not None, pr.get("tonnes") is not None),
                ("grade", grades_agree(lab.get("grades"), pr.get("grades")),
                 bool(lab.get("grades")), bool(pr.get("grades"))),
                ("context", pr.get("context") == lab.get("context"), True, True)):
            if has_pred and has_label:
                out[f].append("tp" if ok else "fp")
                if not ok and complete:
                    out[f].append("fn")
            elif has_label and complete:
                out[f].append("fn")
            # a claim the label says nothing about is set aside: judging it would measure the label
    for _pi in extra:
        if complete:
            out["row"].append("fp")
            out["row_complete"].append("fp")
        # on a partial item an unmatched row may well be real, so it is not counted at all
    return out


def stored_resources(conn, event_id):
    """What /resources shows for one release today, legacy table or published alike.

    The legacy table held one row per release with every category folded into categories_json and no
    parsed figures, so it can only answer the category and the project. That is not a flaw in this
    function: it is the shape being replaced, and the gate should see it as it is."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(resource_estimates)")}
    if "category" in cols:
        sel = ("deposit, category, tonnes, grades_json, contained_json, cut_off, basis, context, "
               "ordinal")
        rows = list(conn.execute(
            "SELECT %s FROM resource_estimates WHERE event_id=? ORDER BY ordinal" % sel, (event_id,)))
        if not rows:
            return None
        out = []
        for r in rows:
            out.append({"deposit": r[0], "category": r[1], "tonnes": r[2],
                        "grades": json.loads(r[3] or "[]"), "contained": json.loads(r[4] or "[]"),
                        "cut_off": r[5], "basis": r[6] or "resource", "context": r[7] or "announced"})
        return {"rows": out}
    r = conn.execute("SELECT project, categories_json, mre_type FROM resource_estimates "
                     "WHERE event_id=? LIMIT 1", (event_id,)).fetchone()
    if not r:
        return None
    cats = []
    try:
        cats = json.loads(r[1] or "[]")
    except (TypeError, ValueError):
        cats = []
    out = []
    for c in cats:
        out.append({"deposit": r[0], "category": (c or {}).get("category"), "tonnes": None,
                    "grades": [], "contained": [], "cut_off": None, "basis": "resource",
                    "context": "announced"})
    return {"rows": out, "mre_type": r[2]} if out else None


def _res_from_records(records):
    from portal.extractors import resources as X
    return X.to_prediction(records)


def _res_rows(conn, version):
    from portal import resources_publish as P
    rows, _st = P.compute(P.load_items(conn, version))
    return rows


def _res_candidate(conn, extractor, version):
    return {r["event_id"] for r in _res_rows(conn, version)}


def _res_current(conn):
    return {r[0] for r in conn.execute("SELECT DISTINCT event_id FROM resource_estimates")}


def _res_describe(conn, event_ids):
    """A removed release, said the way the page said it, so a dropped row can be judged by eye."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(resource_estimates)")}
    sel = "ticker, substr(published_at, 1, 10), summary, raw_headline"
    out = []
    for eid in event_ids:
        r = conn.execute("SELECT %s FROM resource_estimates WHERE event_id=? LIMIT 1" % sel,
                         (eid,)).fetchone()
        if r:
            out.append("%s %s %s | was %s | %s" % (eid[:8], r[0], r[1], (r[2] or "(nothing)")[:70],
                                                   (r[3] or "")[:90]))
    return out


def _res_candidate_predictor(conn, extractor, version):
    """The page is judged through its publisher, so the rule that a row needs a category is scored
    with the reader rather than sitting untested between them."""
    rows = _res_rows(conn, version)
    by_event = {}
    for r in rows:
        by_event.setdefault(r["event_id"], []).append(
            {"deposit": r["deposit"], "category": r["category"], "tonnes": r["tonnes"],
             "grades": json.loads(r["grades_json"] or "[]"),
             "contained": json.loads(r["contained_json"] or "[]"),
             "cut_off": r["cut_off"], "basis": r["basis"], "context": r["context"]})
    return lambda it, ev: ({"rows": by_event[it["event_id"]]} if it["event_id"] in by_event else None)


register_spec(TagSpec(
    name="resources", tag="Resource Estimates", key_fields=RES_KEY_FIELDS,
    report_fields=RES_REPORT_FIELDS, judge=judge_resources, stored=stored_resources,
    from_records=_res_from_records, candidate_predictor=_res_candidate_predictor,
    replaces={"page": "resources", "min_row_recall": 0.950, "candidate": _res_candidate,
              "current": _res_current, "describe": _res_describe},
    describe={"row": "every resource figure on the page is one the release states, and every figure "
                     "it states is on the page",
              "deposit": "the figure is filed under the deposit the release attributes it to",
              "category": "measured, indicated, inferred, proven, probable or total matches",
              "tonnes": "the ore tonnage, within 2% -- not the contained metal",
              "grade": "every grade the release states for that row is shown with the same value",
              "context": "a figure this release announces is separated from one it merely restates",
              "row_complete": "the same as row, over the 36 items whose row list is known to be "
                              "complete, where recall is honest as well as precision"}))
