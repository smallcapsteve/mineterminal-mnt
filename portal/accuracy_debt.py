"""How the Debt & Credit page is scored (DEBT_SPEC_V1, 2026-09-24).

The page shows ONE ROW PER DEBT INSTRUMENT an item reports -- convertible debentures and notes, loans, credit
facilities, notes and bonds, gold loans and prepayments -- at its stage as of the item (proposed, signed, closed,
drawn, amended, converted, repaid or terminated), with the issuer as borrower or, where it lends or holds the debt,
as lender (Justin, 2026-09-24). A release is judged as a set of rows; a predicted row is paired with the labelled row
it claims to be before any field is scored.

Pairing, strongest first over the whole grid: a pair needs the same side, and the same instrument or an agreeing
principal. The score adds the same instrument (3), the same stage (3), an agreeing principal (3) and an agreeing
lender (2). Leftovers stay unpaired: a predicted row with no partner is a false row, a label with no partner a missed
one.

Key fields (Justin: amount, type and stage; interest rate and maturity; lender and security; conversion terms):
instrument, stage, principal, rate_pct, maturity, lender, secured, conversion_price. Numbers agree within 2%. A
maturity agrees when the dates agree to the precision the label gives ("2032" agrees with "2032-06-15"); a label that
states only a term in months is matched on term_months. A lender agrees when the core words of its name overlap
(legal and generic words dropped). The label states every key field, blank where the release does not say, so a
value the reader claims where the label is blank is a false claim (both blank is set aside). Reported fields
(currency, principal_total, term_months, warrants, warrant_strike, related_party) are set aside when the label has
none.

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

import re
import unicodedata

try:
    from portal.accuracy import TagSpec, register_spec
except Exception:  # pragma: no cover - standalone use of the judge
    TagSpec = register_spec = None

DEBT_KEY_FIELDS = ("row", "instrument", "stage", "principal", "rate_pct", "maturity", "lender", "secured",
                   "conversion_price")
DEBT_REPORT_FIELDS = ("side", "currency", "principal_total", "warrants", "warrant_strike", "related_party")

_ROW_FIELDS = ("instrument", "stage", "side", "principal", "currency", "principal_total", "rate_pct", "rate_text",
               "maturity", "term_months", "lender", "borrower", "related_party", "secured", "conversion_price",
               "conversion_text", "warrants", "warrant_strike", "project", "date", "chain_key", "stage_rank", "latest")

_CO_GENERIC = {"inc", "ltd", "corp", "corporation", "limited", "llc", "lp", "l", "p", "the", "and", "of", "co", "company",
               "pty", "s", "a", "sa", "ag", "plc", "de", "holdings", "group", "canada", "fund", "funds", "capital", "partners",
               "management", "managed", "by", "funds", "international", "investment", "investments", "resources", "mining",
               "bank", "ii", "iii", "iv", "lenders", "other"}


def _fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    return "".join(c for c in s if not unicodedata.combining(c))


def _words(s):
    return {w for w in re.findall(r"[a-z0-9&]+", _fold(s)) if w not in _CO_GENERIC and len(w) > 1}


def lender_agrees(a, b):
    if not a or not b:
        return False
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return _fold(a).strip() == _fold(b).strip()
    return bool(wa & wb)


def _num_agrees(a, b, rel=0.02):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= max(rel * abs(b), 0.005)


def maturity_agrees(pred, lab):
    """pred/lab: row dicts. A label maturity is matched to its own precision; a term-only label on term_months."""
    lm, pm = lab.get("maturity"), pred.get("maturity")
    if lm:
        if not pm:
            return False
        lm, pm = str(lm), str(pm)
        n = min(len(lm), len(pm))
        return lm[:n] == pm[:n] and (len(pm) >= 4)
    lt, pt = lab.get("term_months"), pred.get("term_months")
    if lt is not None:
        return pt is not None and _num_agrees(pt, lt, 0.0)
    return None


def _empty(v):
    return v in (None, "", [])


def _pair_score(lab, pr):
    if (lab.get("side") or "borrower") != (pr.get("side") or "borrower"):
        return None
    same_i = lab.get("instrument") == pr.get("instrument")
    pa = not _empty(lab.get("principal")) and _num_agrees(pr.get("principal"), lab.get("principal"))
    if not (same_i or pa):
        return None
    n = 1
    if same_i:
        n += 3
    if lab.get("stage") == pr.get("stage"):
        n += 3
    if pa:
        n += 3
    if lender_agrees(lab.get("lender") or lab.get("borrower"), pr.get("lender") or pr.get("borrower")):
        n += 2
    return n


def debt_match(labels, preds):
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


_STRICT = ("principal", "rate_pct", "lender", "secured", "conversion_price")


def _judge_field(f, lab, pr):
    """True / False / None (set aside)."""
    if f in ("instrument", "stage"):
        return lab.get(f) == pr.get(f)
    if f == "side":
        return (lab.get("side") or "borrower") == (pr.get("side") or "borrower")
    if f == "maturity":
        ok = maturity_agrees(pr, lab)
        if ok is None:
            return False if (pr.get("maturity") or pr.get("term_months") is not None) else None
        return ok
    lv, pv = lab.get(f), pr.get(f)
    if f == "lender" and (lab.get("side") == "lender"):
        lv, pv = lab.get("borrower"), pr.get("borrower")
    if f == "rate_pct" and _empty(lv) and not _empty(lab.get("rate_text")):
        return None if _empty(pv) else False
    if _empty(lv):
        if f in _STRICT and not _empty(pv):
            return False
        return None
    if _empty(pv):
        return False
    if f == "lender":
        return lender_agrees(lv, pv)
    if f in ("secured", "related_party"):
        return bool(lv) == bool(pv)
    if f == "currency":
        return str(lv).upper() == str(pv).upper()
    return _num_agrees(pv, lv)


def judge_debt(pred, expect):
    """pred: None or {rows: [...]}; expect: {complete, rows: [...]}."""
    fields = DEBT_KEY_FIELDS + DEBT_REPORT_FIELDS
    out = {f: [] for f in fields}
    gold = list(expect.get("rows") or [])
    shown = list((pred or {}).get("rows") or [])
    if not shown:
        out["row"].extend(["fn"] * len(gold))
        return out
    if not gold:
        out["row"].extend(["fp"] * len(shown))
        return out
    pairs, extra = debt_match(gold, shown)
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
            claimed = not _empty(pr.get(f)) or (f == "maturity" and pr.get("term_months") is not None)
            if f == "lender" and lab.get("side") == "lender":
                claimed = not _empty(pr.get("borrower"))
            if ok:
                out[f].append("tp")
            elif claimed:
                labelled = not _empty(lab.get(f)) or (f == "maturity" and lab.get("term_months") is not None)
                if f == "lender" and lab.get("side") == "lender":
                    labelled = not _empty(lab.get("borrower"))
                out[f].extend(["fp", "fn"] if labelled else ["fp"])
            else:
                out[f].append("fn")
    if expect.get("complete", True):
        out["row"].extend(["fp"] * len(extra))
    return out


def _table_exists(conn):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name='debt_deals'").fetchone() is not None


def stored_debt(conn, event_id):
    """What the Debt & Credit page shows for one item. A marker row (instrument NULL) states nothing."""
    if not _table_exists(conn):
        return None
    rows = list(conn.execute(
        "SELECT " + ", ".join(_ROW_FIELDS) + " FROM debt_deals WHERE event_id=? AND instrument IS NOT NULL "
        "ORDER BY ordinal", (event_id,)))
    return {"rows": [dict(zip(_ROW_FIELDS, r)) for r in rows]} if rows else None


def _debt_from_records(records):
    from portal.extractors import debt as X
    return X.to_prediction(records)


def _debt_candidate_predictor(conn, extractor, version):
    """Scored through the publisher, item by item (no chain fill-in), so what the page would show for the item is
    what is tested."""
    from portal import debt_publish as P
    items = P.load_items(conn, version)
    by_event = {}
    for ev, p in items:
        rows, _st = P.compute([(ev, p)])
        rows = [{k: r.get(k) for k in _ROW_FIELDS} for r in rows if r.get("instrument")]
        if rows:
            by_event[ev["event_id"]] = rows
    return lambda it, ev: ({"rows": by_event[it["event_id"]]} if it["event_id"] in by_event else None)


def self_test():
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))

    L = {"instrument": "loan", "stage": "closed", "side": "borrower", "principal": 5000000, "currency": "USD",
         "rate_pct": 12, "maturity": "2027-12-31", "term_months": None, "lender": "Delta Capital LLC", "secured": True,
         "conversion_price": None}
    P = {"instrument": "loan", "stage": "closed", "side": "borrower", "principal": 5000000.0, "currency": "USD",
         "rate_pct": 12.0, "maturity": "2027-12-31", "term_months": None, "lender": "Delta Capital", "secured": True,
         "conversion_price": None}
    r = judge_debt({"rows": [P]}, {"rows": [L]})
    eq("all right", [r[f] for f in ("row", "instrument", "stage", "principal", "rate_pct", "maturity", "lender", "secured",
                                    "conversion_price")],
       [["tp"], ["tp"], ["tp"], ["tp"], ["tp"], ["tp"], ["tp"], ["tp"], []])
    r = judge_debt({"rows": [dict(P, lender="Omega Bank", stage="signed")]}, {"rows": [L]})
    eq("wrong lender and stage", (r["lender"], r["stage"]), (["fp", "fn"], ["fp", "fn"]))
    r = judge_debt({"rows": [dict(P, conversion_price=0.2)]}, {"rows": [L]})
    eq("a value the label leaves blank is a false claim", r["conversion_price"], ["fp"])
    r = judge_debt({"rows": [P, dict(P, instrument="notes", principal=1.0)]}, {"rows": [L]})
    eq("an extra row is a false row", r["row"], ["tp", "fp"])
    r = judge_debt(None, {"rows": [L]})
    eq("missed", r["row"], ["fn"])
    r = judge_debt({"rows": [P]}, {"rows": []})
    eq("no debt", r["row"], ["fp"])
    r = judge_debt({"rows": [dict(P, maturity="2027")]}, {"rows": [dict(L, maturity="2027")]})
    eq("year maturity", r["maturity"], ["tp"])
    r = judge_debt({"rows": [dict(P, maturity=None, term_months=24)]}, {"rows": [dict(L, maturity=None, term_months=24)]})
    eq("term-only maturity", r["maturity"], ["tp"])
    r = judge_debt({"rows": [dict(P, side="lender")]}, {"rows": [L]})
    eq("sides never pair", r["row"], ["fn", "fp"])
    eq("lender words", (lender_agrees("Sprott Resource Streaming and Royalty Corp.", "Sprott Streaming"),
                        lender_agrees("Bank of Montreal", "National Bank of Canada")), (True, False))
    print("accuracy_debt: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if register_spec is not None:
    register_spec(TagSpec(
        name="debt", tag="Debt & Credit Facilities", key_fields=DEBT_KEY_FIELDS,
        report_fields=DEBT_REPORT_FIELDS, judge=judge_debt, stored=stored_debt,
        from_records=_debt_from_records, candidate_predictor=_debt_candidate_predictor,
        project_labels=("rows", "project"),     # ACC2 / PN_V1: the key's project labels join the shared test set
        describe={"row": "every row on the page is a debt instrument an item reports -- a convertible debenture or note, "
                         "a loan, a credit facility, notes or bonds, a gold loan or a prepayment -- with the issuer as "
                         "borrower, or as lender where it lends or holds the debt",
                  "instrument": "convertible debenture, convertible note, loan, credit facility, notes, gold loan or "
                                "prepayment",
                  "stage": "the stage as of the item: proposed, signed, closed, drawn, amended, converted, repaid, interest_paid or "
                           "terminated",
                  "principal": "the amount at this stage (the offering, the tranche closed, the amount repaid, the interest paid)",
                  "rate_pct": "the annual interest rate (a floating rate is shown as text and not scored here)",
                  "maturity": "the maturity date, or the term when only a term is given",
                  "lender": "the lender or holder, blank when the release does not name one (for a row where the "
                            "company is the lender: the borrower)",
                  "secured": "secured or unsecured, when the release says",
                  "conversion_price": "the price per share it converts at (blank when a unit holds several shares)",
                  "side": "the company as borrower or as lender (reported)",
                  "currency": "the principal's currency (reported)",
                  "principal_total": "the running total of tranches (reported)",
                  "warrants": "warrants attached (reported)",
                  "warrant_strike": "the warrants' exercise price (reported)",
                  "related_party": "an insider or related party lends (reported)"}))

if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test() else 0)
