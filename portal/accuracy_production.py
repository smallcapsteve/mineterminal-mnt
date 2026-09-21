"""How /production-results is scored (PROD_SPEC_V1, 2026-09-21).

The page shows ONE ROW PER METAL PER PERIOD (Justin, 2026-09-21), of three kinds: actual, guidance and
milestone. A release is judged as a set of rows, and a predicted row is paired with the labelled row it
claims to be before any of its fields is scored.

Pairing, strongest first over the whole grid (the ECON lesson: label-by-label pairing lets a label with no
match take a row another label owns):
  * same kind, period and metal, and the figure agrees         -- 5
  * same kind, period and metal                                 -- 3
  * same kind and the figure agrees (wrong period or metal)     -- 2
  * two milestones of the same type                             -- 3
Leftovers of the same kind are then paired in order, so a row with a wrong figure AND a wrong period is
still counted wrong on both rather than set aside. A predicted row of a kind the label does not have is a
false row.

Figures: an actual row's figure is its quantity, a guidance row's is its low and high. They agree within
1% (Torex states 485.2 koz of silver; a reader reading '485,200' and one reading '485.2 thousand' agree),
and a missing end of a one-sided range must be missing on both sides.

A field the label does not state is set aside rather than judged (the Resource Estimates rule): a label
with no AISC says nothing about the AISC a reader found.

Guidance for a period that ended before the release is on the ACTUAL row as guided_low/guided_high
(Justin, 2026-09-21). The publisher does that fold, so the candidate is scored through the publisher.

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

from portal.accuracy import TagSpec, register_spec

PROD_KEY_FIELDS = ("row", "kind", "period", "metal", "unit", "figure")
# Too few in the set to reach the gate's ten claims, or not the row's identity: reported, not gated.
PROD_REPORT_FIELDS = ("sold", "aisc", "guided", "milestone", "basis")

_ROW_FIELDS = ("kind", "period", "metal", "unit", "qty", "low", "high", "sold", "aisc", "guided_low",
               "guided_high", "milestone", "asset", "basis")


def _close(a, b, rel=0.01):
    if a is None or b is None:
        return a is None and b is None
    hi = max(abs(a), abs(b))
    return hi == 0 or abs(a - b) <= rel * hi


def _norm(s):
    return " ".join(str(s).lower().split()) if s is not None else None


def figure_of(r):
    if r.get("kind") == "actual":
        return ("q", r.get("qty"))
    if r.get("kind") == "guidance":
        return ("r", r.get("low"), r.get("high"))
    return None


def figure_close(a, b):
    fa, fb = figure_of(a), figure_of(b)
    if fa is None or fb is None or fa[0] != fb[0]:
        return False
    return all(_close(x, y) for x, y in zip(fa[1:], fb[1:]))


def _same_id(a, b):
    return (a.get("kind") == b.get("kind") and _norm(a.get("period")) == _norm(b.get("period"))
            and _norm(a.get("metal")) == _norm(b.get("metal")))


def prod_match(labels, preds):
    scored = []
    for li, lab in enumerate(labels):
        for pi, pr in enumerate(preds):
            if lab.get("kind") != pr.get("kind"):
                continue
            if lab.get("kind") == "milestone":
                n = 3 if lab.get("milestone") == pr.get("milestone") else 0
            else:
                same, fig = _same_id(lab, pr), figure_close(lab, pr)
                n = 5 if (same and fig) else 3 if same else 2 if fig else 0
            if n:
                scored.append((-n, li, pi))
    scored.sort()
    got, used = {}, set()
    for _n, li, pi in scored:
        if li in got or pi in used:
            continue
        got[li] = pi
        used.add(pi)
    for li, lab in enumerate(labels):
        if li in got:
            continue
        for pi, pr in enumerate(preds):
            if pi not in used and pr.get("kind") == lab.get("kind") and lab.get("kind") != "milestone":
                got[li] = pi
                used.add(pi)
                break
    extra = [pi for pi in range(len(preds)) if pi not in used]
    return [(li, got.get(li)) for li in range(len(labels))], extra


def _judge_field(f, lab, pr):
    """None: not judged. True/False: agreed or not."""
    if f == "figure":
        if figure_of(lab) is None:
            return None
        return figure_close(lab, pr)
    if f == "guided":
        if lab.get("guided_low") is None and lab.get("guided_high") is None:
            return None
        return _close(lab.get("guided_low"), pr.get("guided_low")) and _close(lab.get("guided_high"), pr.get("guided_high"))
    if f in ("sold", "aisc"):
        if lab.get(f) is None:
            return None
        return pr.get(f) is not None and _close(lab.get(f), pr.get(f))
    if f in ("period", "metal", "unit") and lab.get("kind") == "milestone":
        return None
    if lab.get(f) is None:
        return None
    if f == "basis":
        return pr.get(f) is not None
    return _norm(lab.get(f)) == _norm(pr.get(f))


def judge_production(pred, expect):
    """pred: None or {rows: [...]}; expect: {is_production, complete, rows: [...]} (the fields in _ROW_FIELDS)."""
    fields = PROD_KEY_FIELDS + PROD_REPORT_FIELDS
    out = {f: [] for f in fields}
    gold = list(expect.get("rows") or [])
    shown = list((pred or {}).get("rows") or [])
    complete = bool(expect.get("complete", True))
    if not shown:
        out["row"].extend(["fn"] * len(gold))
        return out
    if not gold:
        out["row"].extend(["fp"] * len(shown))
        return out
    pairs, extra = prod_match(gold, shown)
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
            has_pred = (figure_of(pr) is not None and any(v is not None for v in figure_of(pr)[1:])) if f == "figure" \
                else (pr.get("guided_low") is not None or pr.get("guided_high") is not None) if f == "guided" \
                else pr.get(f) is not None
            if ok:
                out[f].append("tp")
            elif has_pred:
                out[f].extend(["fp", "fn"])
            else:
                out[f].append("fn")
    if complete:
        out["row"].extend(["fp"] * len(extra))
    return out


def _table_exists(conn):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name='production_results'").fetchone() is not None


def stored_production(conn, event_id):
    """What /production-results shows for one release. A marker row (kind NULL) states nothing."""
    if not _table_exists(conn):
        return None
    rows = list(conn.execute(
        "SELECT " + ", ".join(_ROW_FIELDS) + " FROM production_results "
        "WHERE event_id=? AND kind IS NOT NULL ORDER BY ordinal", (event_id,)))
    return {"rows": [dict(zip(_ROW_FIELDS, r)) for r in rows]} if rows else None


def _prod_from_records(records):
    from portal.extractors import production as X
    return X.to_prediction(records)


def _prod_candidate_predictor(conn, extractor, version):
    """Scored through the publisher, so the fold of past guidance onto actual rows is tested too."""
    from portal import production_publish as P
    rows, _st = P.compute(P.load_items(conn, version))
    by_event = {}
    for r in rows:
        if r["kind"] is None:
            continue
        by_event.setdefault(r["event_id"], []).append({k: r.get(k) for k in _ROW_FIELDS})
    return lambda it, ev: ({"rows": by_event[it["event_id"]]} if it["event_id"] in by_event else None)


register_spec(TagSpec(
    name="production", tag="Production Results", key_fields=PROD_KEY_FIELDS, report_fields=PROD_REPORT_FIELDS,
    judge=judge_production, stored=stored_production, from_records=_prod_from_records,
    candidate_predictor=_prod_candidate_predictor,
    describe={"row": "every row on the page is one the release states -- a metal's production or guidance for a "
                     "period, or a completed milestone -- and every one it states is on the page",
              "kind": "actual, guidance or milestone",
              "period": "the quarter, half or year the figure is for",
              "metal": "the metal or product, in the release's own measure (gold, GEO, AuEq, lithium concentrate)",
              "unit": "oz, lb or t",
              "figure": "the quantity produced, or the guidance range's low and high, within 1%",
              "sold": "the quantity sold in the same period (reported)",
              "aisc": "the AISC per ounce stated with the figure (reported)",
              "guided": "the guidance a finished period was measured against (reported)",
              "milestone": "the kind of milestone (reported)",
              "basis": "a single mine, a 100% basis or pro forma, where the release reports on one (reported)"}))
