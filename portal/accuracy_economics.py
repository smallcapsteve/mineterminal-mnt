"""How /economic-studies is scored (ECON_SPEC_V1, 2026-09-21).

The page shows ONE ROW PER SCENARIO (Justin, 2026-09-18): pre-tax and after-tax are columns of the
same row, a named case is a row, a percentage sweep is not. So a release is judged as a set of
scenarios, and a predicted row has to be paired with the labelled row it is claiming to be before
any of its figures can be scored.

Pairing is by the figures themselves -- the after-tax and pre-tax NPV and IRR and the payback -- not
by the scenario's name. Radisson's base case is "base case US$2,550/oz" to the reader and "base case
US$2,550/oz Au" to the label, and a name match would be scoring spelling. A row that shares no figure
with any remaining label is paired with the first one left, which is how a wrong figure gets counted
as wrong rather than quietly set aside.

Two rules decide what counts as a claim, both carried over from the Resource Estimates scorer:

  * A field the label does not state cannot be judged. A label with no payback says nothing about the
    payback, so a payback the reader found there is set aside rather than counted wrong.
  * An item marked `complete: false` has a row list known to be partial, so unpaired predicted rows
    on it are not counted against the reader. Three of the fifty are marked that way.

Attribution: a release that quotes ANOTHER company's study -- Peloton (PMC.CN) relaying Surge's Nevada
North PEA -- is left out by the publisher. Scored through the publisher, PMC.CN therefore shows no row,
which is exactly what the label for that release says: it states no economics of its own.

Money is compared within 2%. A release that writes "$1.4 billion" in its prose and 1,380 in its table
is stating one figure twice; GCU's 2,000 against 1,952 is 2.4% and is still counted wrong, which is
where the line is drawn. Percentages and years must agree to within 0.05.

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

from portal.accuracy import TagSpec, register_spec

ECON_KEY_FIELDS = ("row", "study_type", "context", "basis", "currency", "discount_pct", "npv_after_tax",
                   "irr_after_tax_pct", "initial_capex", "payback_years", "mine_life_years")
# Too few of these in the set to reach the gate's ten claims, so they are reported, not gated.
ECON_REPORT_FIELDS = ("npv_pre_tax", "irr_pre_tax_pct", "capex_sensitivity")

_MONEY = ("npv_after_tax", "npv_pre_tax", "initial_capex", "capex_sensitivity")
_PAIR_ON = ("npv_after_tax", "npv_pre_tax", "irr_after_tax_pct", "irr_pre_tax_pct", "payback_years")


def econ_close(field, a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, str) or isinstance(b, str):
        return str(a).strip().lower() == str(b).strip().lower()
    if field in _MONEY:
        hi = max(abs(a), abs(b))
        return hi == 0 or abs(a - b) <= 0.02 * hi
    return abs(a - b) <= 0.051


def econ_match(labels, preds):
    """Pair labelled rows with predicted rows, strongest figure matches first.

    Greedy over the whole grid rather than label by label: taking labels in order let a label with
    no match claim the first free row by default, before the label that row actually matches got
    its turn -- which is how Allied Critical Metals' high case was once scored against its base
    case label. Only after every figure-matched pair is made are the leftovers paired in order."""
    scored = []
    for li, lab in enumerate(labels):
        for pi, pr in enumerate(preds):
            n = sum(1 for k in _PAIR_ON
                    if lab.get(k) is not None and econ_close(k, pr.get(k), lab.get(k)))
            if n:
                scored.append((-n, li, pi))
    scored.sort()
    got, used = {}, set()
    for _n, li, pi in scored:
        if li in got or pi in used:
            continue
        got[li] = pi
        used.add(pi)
    pool = [pi for pi in range(len(preds)) if pi not in used]
    pairs = []
    for li in range(len(labels)):
        if li not in got and pool:
            got[li] = pool.pop(0)
        pairs.append((li, got.get(li)))
    return pairs, pool


def judge_economics(pred, expect):
    """pred: None or {rows: [{scenario, study_type, context, basis, currency, discount_pct,
    npv_pre_tax, npv_after_tax, irr_pre_tax_pct, irr_after_tax_pct, payback_years, initial_capex,
    capex_sensitivity, mine_life_years}]}
    expect: {is_economic_study, complete, rows: [the same shape]}"""
    fields = ECON_KEY_FIELDS + ECON_REPORT_FIELDS
    out = {f: [] for f in fields}
    gold = list(expect.get("rows") or [])
    want = bool(expect.get("is_economic_study")) and bool(gold)
    complete = bool(expect.get("complete", True))
    shown = list((pred or {}).get("rows") or [])

    if not shown:
        if want:
            out["row"].extend(["fn"] * len(gold))
        return out
    if not want:
        out["row"].extend(["fp"] * len(shown))
        return out

    pairs, extra = econ_match(gold, shown)
    for li, pi in pairs:
        lab = gold[li]
        if pi is None:
            out["row"].append("fn")
            continue
        pr = shown[pi]
        out["row"].append("tp")
        for f in fields[1:]:
            has_label = lab.get(f) is not None
            has_pred = pr.get(f) is not None
            if has_label and has_pred:
                ok = econ_close(f, pr.get(f), lab.get(f))
                out[f].append("tp" if ok else "fp")
                if not ok:
                    out[f].append("fn")
            elif has_label:
                out[f].append("fn")
            # a claim the label says nothing about is set aside: judging it would measure the label
    if complete:
        out["row"].extend(["fp"] * len(extra))
    return out


_ROW_FIELDS = ("scenario", "study_type", "context", "basis", "currency", "discount_pct", "npv_pre_tax",
               "npv_after_tax", "irr_pre_tax_pct", "irr_after_tax_pct", "payback_years", "initial_capex",
               "capex_sensitivity", "mine_life_years")


def _table_exists(conn):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name='economic_studies'").fetchone() is not None


def stored_economics(conn, event_id):
    """What /economic-studies shows for one release. A marker row (scenario NULL) states nothing."""
    if not _table_exists(conn):
        return None
    rows = list(conn.execute(
        "SELECT " + ", ".join(_ROW_FIELDS) + " FROM economic_studies "
        "WHERE event_id=? AND scenario IS NOT NULL ORDER BY ordinal", (event_id,)))
    if not rows:
        return None
    return {"rows": [dict(zip(_ROW_FIELDS, r)) for r in rows]}


def _econ_from_records(records):
    from portal.extractors import economics as X
    p = X.to_prediction(records)
    return {"rows": p["scenarios"]} if p else None


def _econ_candidate_predictor(conn, extractor, version):
    """Scored through the publisher, so attribution and markers are tested with the reader rather
    than sitting untested between them."""
    from portal import economics_publish as P
    rows, _st = P.compute(P.load_items(conn, version), P.company_names())
    by_event = {}
    for r in rows:
        if r["scenario"] is None:
            continue
        by_event.setdefault(r["event_id"], []).append({k: r.get(k) for k in _ROW_FIELDS})
    return lambda it, ev: ({"rows": by_event[it["event_id"]]} if it["event_id"] in by_event else None)


register_spec(TagSpec(
    name="economics", tag="Economic Studies", key_fields=ECON_KEY_FIELDS,
    report_fields=ECON_REPORT_FIELDS, judge=judge_economics, stored=stored_economics,
    from_records=_econ_from_records, candidate_predictor=_econ_candidate_predictor,
    describe={"row": "every scenario on the page is one the release states, and every one it states is on "
                     "the page -- a named case is a row, a percentage sweep is not",
              "study_type": "PEA, PFS or FS: the kind of study the figures belong to",
              "context": "a study this release announces is separated from one it restates",
              "basis": "real or nominal, where a release states both",
              "currency": "the currency the release reports the scenario in",
              "discount_pct": "the rate the NPV is discounted at",
              "npv_after_tax": "the after-tax NPV, within 2%",
              "irr_after_tax_pct": "the after-tax IRR",
              "initial_capex": "the initial capital cost the release states, within 2%",
              "payback_years": "the payback period, in years",
              "mine_life_years": "the mine life, in years",
              "npv_pre_tax": "the pre-tax NPV, within 2% (reported: too few in the set to gate)",
              "irr_pre_tax_pct": "the pre-tax IRR (reported: too few in the set to gate)",
              "capex_sensitivity": "the unswung row of a CAPEX sensitivity table (reported)"}))
