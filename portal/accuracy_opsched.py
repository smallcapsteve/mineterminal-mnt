"""How the option payment schedule is scored (OPS_SPEC_V1, C9, 2026-10-12).

The Options reader (portal/extractors/options.py 1.0.11+) gives each option row its payment schedule: one item per due
date the terms state, with the cash, shares (a count or a $ value) and work due then, or a dated condition (rule calls
OE-ON, Justin 2026-10-07; claude/MNT_EVENTS_READERS_2026-10-07.md). Mine Terminal Pro turns the future items of live
options into "Option payment due" events.

A release is judged deal by deal: deals pair as on the options page (portal/accuracy_options.deal_match), then the
items of each option deal pair, strongest first: a date that agrees (3), plus 1 for each of cash, share count, share
value and work that agree. A pair needs an agreeing date, or (both undated) an agreeing amount. Leftover predictions are
false items, leftover labels missed items.

Key fields (gate at 90% precision on 10+ claims): item, item_date, item_cash, item_shares.
Reported only: item_work, item_kind, item_paid, schedule.
- a date agrees within 3 days when the label's date is exact (stated, or counted from a stated date), within 31 days
  when it is estimated (rule OE); both undated is set aside;
- amounts agree within 2%; shares agree only as the same kind (a count with a count, a $ value with a $ value);
- a value the reader states where the label is blank is a false claim; both blank is set aside.

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

from datetime import date

try:
    from portal.accuracy import TagSpec, register_spec
except Exception:  # pragma: no cover - standalone use of the judge
    TagSpec = register_spec = None

OPS_KEY_FIELDS = ("item", "item_date", "item_cash", "item_shares")
OPS_REPORT_FIELDS = ("item_work", "item_kind", "item_paid", "schedule")
OPTION_TYPES = ("option_in", "option_out")


def _d(x):
    if not x:
        return None
    if isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def _num(a, b):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= max(0.02 * abs(b), 0.5)


def date_ok(lab, pred):
    ld, pd = _d(lab.get("date")), _d(pred.get("date"))
    if not ld and not pd:
        return None
    if not ld or not pd:
        return False
    return abs((ld - pd).days) <= (3 if lab.get("exact") else 31)


def _shares(it):
    if it.get("sh_n"):
        return "n", it["sh_n"]
    if it.get("sh_v"):
        return "v", it["sh_v"]
    return None, None


def _pair_score(L, P):
    dk = date_ok(L, P)
    if dk is False:
        return None
    agree = sum(1 for f in ("cash", "sh_n", "sh_v", "work") if L.get(f) and P.get(f) and _num(P[f], L[f]))
    if dk is None and not agree:
        return None
    if dk is None and (L.get("kind") == "milestone") != (P.get("kind") == "milestone"):
        return None
    return (3 if dk else 0) + agree


def item_match(labels, preds):
    sc = []
    for li, L in enumerate(labels):
        for pi, P in enumerate(preds):
            s = _pair_score(L, P)
            if s is not None:
                sc.append((-s, li, pi))
    sc.sort()
    got, used = {}, set()
    for _s, li, pi in sc:
        if li in got or pi in used:
            continue
        got[li] = pi
        used.add(pi)
    return [(li, got.get(li)) for li in range(len(labels))], [pi for pi in range(len(preds)) if pi not in used]


def judge_items(labels, preds, out):
    pairs, extra = item_match(labels, preds)
    for li, pi in pairs:
        L = labels[li]
        if pi is None:
            out["item"].append("fn")
            continue
        P = preds[pi]
        out["item"].append("tp")
        ok = date_ok(L, P)
        if ok is not None:
            out["item_date"].extend(["tp"] if ok else ["fp", "fn"])
        for f, k in (("item_cash", "cash"), ("item_work", "work")):
            lv, pv = L.get(k), P.get(k)
            if lv and pv:
                out[f].extend(["tp"] if _num(pv, lv) else ["fp", "fn"])
            elif pv:
                out[f].append("fp")
            elif lv:
                out[f].append("fn")
        lk, lv = _shares(L)
        pk, pv = _shares(P)
        if lv and pv:
            out["item_shares"].extend(["tp"] if lk == pk and _num(pv, lv) else ["fp", "fn"])
        elif pv:
            out["item_shares"].append("fp")
        elif lv:
            out["item_shares"].append("fn")
        out["item_kind"].extend(["tp"] if L.get("kind") == P.get("kind") else ["fp", "fn"])
        out["item_paid"].extend(["tp"] if bool(L.get("paid")) == bool(P.get("paid")) else ["fp", "fn"])
    out["item"].extend(["fp"] * len(extra))


def judge_opsched(pred, expect):
    """pred: None or {rows: [{deal_type, stage, property, counterparty, interest_pct, schedule, items}]};
    expect: {complete, deals: [{deal_type, stage, property, schedule, items}]}."""
    from portal.accuracy_options import deal_match
    out = {f: [] for f in OPS_KEY_FIELDS + OPS_REPORT_FIELDS}
    gold = [d for d in (expect.get("deals") or [])]
    shown = list((pred or {}).get("rows") or [])
    if not gold:
        for r in shown:     # items read from a release that has no option deal are false items
            out["item"].extend(["fp"] * len(r.get("items") or []))
        return out
    pairs, extra = deal_match(gold, shown) if shown else ([(i, None) for i in range(len(gold))], [])
    # OPS_V1: the one option deal left on each side, same type, is the same deal even when the names are spelt apart
    # ("Hawkridge" / "Hawk Ridge"); the property itself is scored by the Options sets
    lone_g = [li for li, pi in pairs if pi is None and gold[li].get("deal_type") in OPTION_TYPES]
    lone_p = [pi for pi in extra if shown[pi].get("deal_type") in OPTION_TYPES]
    if len(lone_g) == 1 and len(lone_p) == 1 and gold[lone_g[0]].get("deal_type") == shown[lone_p[0]].get("deal_type"):
        pairs = [(li, lone_p[0] if li == lone_g[0] else pi) for li, pi in pairs]
        extra = [pi for pi in extra if pi != lone_p[0]]
    for li, pi in pairs:
        D = gold[li]
        if D.get("deal_type") not in OPTION_TYPES:
            if pi is not None:
                out["item"].extend(["fp"] * len(shown[pi].get("items") or []))
            continue
        P = shown[pi] if pi is not None else {}
        if D.get("schedule") and pi is not None:
            out["schedule"].extend(["tp"] if P.get("schedule") == D["schedule"] else (["fp", "fn"] if P.get("schedule") else ["fn"]))
        judge_items(D.get("items") or [], P.get("items") or [], out)
    if expect.get("complete", True):
        for pi in extra:
            out["item"].extend(["fp"] * len(shown[pi].get("items") or []))
    return out


def stored_opsched(conn, event_id):
    """What land_deal_items holds for one release (the publisher's table)."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='land_deal_items'").fetchone():
        return None
    rows = {}
    for r in conn.execute("SELECT d.ordinal, d.deal_type, d.stage, d.property, d.counterparty, d.interest_pct FROM land_deals d "
                          "WHERE d.event_id=? AND d.deal_type IS NOT NULL ORDER BY d.ordinal", (event_id,)):
        rows[r[0]] = {"deal_type": r[1], "stage": r[2], "property": r[3], "counterparty": r[4], "interest_pct": r[5],
                      "items": []}
    for r in conn.execute("SELECT ordinal, due_date, exact, kind, cash, sh_n, sh_v, work, paid FROM land_deal_items "
                          "WHERE event_id=? ORDER BY ordinal, seq", (event_id,)):
        if r[0] in rows:
            rows[r[0]]["items"].append({"date": r[1], "exact": bool(r[2]), "kind": r[3], "cash": r[4], "sh_n": r[5],
                                        "sh_v": r[6], "work": r[7], "paid": bool(r[8])})
    return {"rows": [rows[k] for k in sorted(rows)]} if rows else None


def _opsched_from_records(records):
    from portal.extractors import options as X
    if not records:
        return None
    p = X.parse_records({i: [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts] for i, rec in enumerate(records)})
    return {"rows": p["rows"]} if p["rows"] else None


def self_test():
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))

    L = {"deal_type": "option_in", "stage": "signed", "property": "Swell Bay", "schedule": "itemized", "items": [
        {"date": "2026-03-10", "exact": True, "kind": "payment", "cash": 5000, "sh_n": 150000},
        {"date": "2027-03-10", "exact": True, "kind": "payment", "cash": 10000, "sh_n": 500000},
        {"date": "2027-04-24", "exact": False, "kind": "work", "work": 250000}]}
    P = {"deal_type": "option_in", "stage": "signed", "property": "Swell Bay Property", "schedule": "itemized", "items": [
        {"date": "2026-03-10", "exact": True, "kind": "payment", "cash": 5000.0, "sh_n": 150000.0},
        {"date": "2027-03-11", "exact": True, "kind": "payment", "cash": 10000.0, "sh_n": 500000.0},
        {"date": "2027-05-10", "exact": False, "kind": "work", "work": 250000.0},
        {"date": "2031-01-01", "exact": True, "kind": "payment", "cash": 7.0}]}
    r = judge_opsched({"rows": [P]}, {"deals": [L]})
    eq("items", (r["item"], r["item_date"], r["item_cash"], r["item_shares"], r["item_work"]),
       (["tp", "tp", "tp", "fp"], ["tp", "tp", "tp"], ["tp", "tp"], ["tp", "tp"], ["tp"]))
    P2 = dict(P, items=[dict(P["items"][0], date="2026-05-01")])
    r = judge_opsched({"rows": [P2]}, {"deals": [L]})
    eq("an exact date 52 days off does not pair", (r["item"], r["item_date"]), (["fn", "fn", "fn", "fp"], []))
    P3 = dict(P, items=[dict(P["items"][0], sh_n=None, sh_v=150000.0)])
    r = judge_opsched({"rows": [P3]}, {"deals": [L]})
    eq("a share value is not a share count", r["item_shares"], ["fp", "fn"])
    r = judge_opsched({"rows": [P]}, {"deals": []})
    eq("no deal: every item is false", r["item"], ["fp"] * 4)
    r = judge_opsched(None, {"deals": [L]})
    eq("nothing read", r["item"], ["fn"] * 3)
    print("accuracy_opsched: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if register_spec is not None:
    register_spec(TagSpec(
        name="option_schedule", tag="Property Options & Staking", key_fields=OPS_KEY_FIELDS, report_fields=OPS_REPORT_FIELDS,
        judge=judge_opsched, stored=stored_opsched, from_records=_opsched_from_records,
        describe={"item": "every item is one due date an option's terms state (cash, shares, work, or a dated condition)",
                  "item_date": "the due date: exact when stated or counted from a stated date, else estimated (within 31 days)",
                  "item_cash": "the cash due on that date",
                  "item_shares": "the shares due on that date, as a count or as a $ value",
                  "item_work": "the exploration spending due by that date (reported)",
                  "item_kind": "payment, work, deadline, cure, exercise or milestone (reported)",
                  "item_paid": "whether the release says the item was already paid (reported)",
                  "schedule": "itemized, totals_only, deadlines, cure, paid_item, anchored_later or none (reported)"}))

if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test() else 0)
