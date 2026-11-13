"""How the Warrant Changes reader is scored (WCH_SPEC_V1, 2026-10-07).

The reader stores ONE ROW PER CHANGE to one group of already-issued warrants (or one incentive programme) a release
reports: extension, acceleration, acceleration_waived, repricing, incentive, exercise, expired, withdrawn; status
proposed or effective (rule calls WA-WM, Justin 2026-10-07, claude/MNT_EVENTS_READERS_2026-10-07.md). It has no page
of its own: Mine Terminal Pro uses it to move, retire or relabel warrant-expiry events, and only rows that also match
a financing MNT stores are used there (the publisher's financing gate, Justin: "Gate it, then ship").

Pairing (same as the held-back scorer hb_wch.py): each labelled row takes the unused predicted row that scores best;
same change 3, plus 1 for each of n_warrants, n_exercised, strike_old, issued, expiry_new that agree. A pair needs 3.
Leftover predictions are false rows, leftover labels missed rows.

Key fields (gate at 90% precision on 10+ claims): row, change, status, expiry_new, issued, strike_old.
Reported only: program_end, n_warrants, n_exercised, proceeds, n_remaining, expiry_old, strike_new.
- dates and date lists agree exactly (lists as a whole, in order);
- strikes agree within 2% (or 0.0001); counts and money are rounded and agree within 2%;
- a value the reader states where the label is blank is a false claim; both blank is set aside.

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

try:
    from portal.accuracy import TagSpec, register_spec
except Exception:  # pragma: no cover - standalone use of the judge
    TagSpec = register_spec = None

WCH_KEY_FIELDS = ("row", "change", "status", "expiry_new", "issued", "strike_old")
WCH_REPORT_FIELDS = ("program_end", "n_warrants", "n_exercised", "proceeds", "n_remaining", "expiry_old", "strike_new")
_PAIR_FIELDS = ("n_warrants", "n_exercised", "strike_old", "issued", "expiry_new")
_STRIKES = ("strike_old", "strike_new")


def _norm(f, v):
    if v in (None, [], ""):
        return None
    if isinstance(v, list):
        return tuple(v)
    if isinstance(v, float) and f not in _STRIKES:
        return round(v)
    return v


def agree(f, a, b):
    """True / False, or None when both are blank."""
    a, b = _norm(f, a), _norm(f, b)
    if a is None and b is None:
        return None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= max(0.02 * abs(b), 0.0001)
    return a == b


def wch_match(labels, preds):
    pairs, used = [], set()
    for li, L in enumerate(labels):
        best, bs = None, -1
        for pi, P in enumerate(preds):
            if pi in used:
                continue
            s = 3 if P.get("change") == L.get("change") else 0
            s += sum(1 for f in _PAIR_FIELDS if agree(f, P.get(f), L.get(f)))
            if s > bs:
                best, bs = pi, s
        if best is not None and bs >= 3:
            used.add(best)
            pairs.append((li, best))
    got = dict(pairs)
    extra = [pi for pi in range(len(preds)) if pi not in used]
    return [(li, got.get(li)) for li in range(len(labels))], extra


def judge_wch(pred, expect):
    """pred: None or {rows: [...]}; expect: {complete, rows: [...]} -> {field: ['tp'|'fp'|'fn', ...]}."""
    fields = WCH_KEY_FIELDS + WCH_REPORT_FIELDS
    out = {f: [] for f in fields}
    gold = list(expect.get("rows") or [])
    shown = list((pred or {}).get("rows") or [])
    if not shown:
        out["row"].extend(["fn"] * len(gold))
        return out
    if not gold:
        out["row"].extend(["fp"] * len(shown))
        return out
    pairs, extra = wch_match(gold, shown)
    for li, pi in pairs:
        if pi is None:
            out["row"].append("fn")
            continue
        L, P = gold[li], shown[pi]
        out["row"].append("tp")
        for f in fields[1:]:
            a = agree(f, P.get(f), L.get(f))
            if a is None:
                continue
            if _norm(f, L.get(f)) is None:
                out[f].append("fp")
            elif _norm(f, P.get(f)) is None:
                out[f].append("fn")
            elif a:
                out[f].append("tp")
            else:
                out[f].extend(["fp", "fn"])
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

    L = {"change": "extension", "status": "effective", "n_warrants": 3440849, "strike_old": 0.32,
         "issued": ["2018-10-27"], "expiry_old": "2019-10-27", "expiry_new": ["2020-10-27"]}
    r = judge_wch({"rows": [dict(L, n_warrants=3440849.0)]}, {"rows": [L]})
    eq("all right", [r[f] for f in ("row", "change", "status", "expiry_new", "issued", "strike_old", "n_warrants",
                                    "program_end")], [["tp"], ["tp"], ["tp"], ["tp"], ["tp"], ["tp"], ["tp"], []])
    r = judge_wch({"rows": [dict(L, status="proposed", expiry_new=["2020-11-27"], strike_new=0.25)]}, {"rows": [L]})
    eq("wrong status and date; strike_new claimed on a blank label",
       (r["status"], r["expiry_new"], r["strike_new"]), (["fp", "fn"], ["fp", "fn"], ["fp"]))
    r = judge_wch({"rows": [dict(L, issued=None)]}, {"rows": [L]})
    eq("issue date missed", r["issued"], ["fn"])
    r = judge_wch({"rows": [L, dict(L, change="repricing", n_warrants=5, strike_old=0.5, issued=None, expiry_new=None)]},
                  {"rows": [L]})
    eq("extra row is a false row", r["row"], ["tp", "fp"])
    r = judge_wch({"rows": [{"change": "repricing", "status": "effective"}]}, {"rows": [L]})
    eq("no pair under 3", r["row"], ["fn", "fp"])
    eq("no prediction", judge_wch(None, {"rows": [L, L]})["row"], ["fn", "fn"])
    eq("prediction on an empty key", judge_wch({"rows": [L]}, {"rows": []})["row"], ["fp"])
    eq("nothing either side", judge_wch(None, {"rows": []})["row"], [])
    eq("strike within 2%", (agree("strike_old", 0.32, 0.325), agree("strike_old", 0.30, 0.325)), (True, False))
    eq("tranche lists in order", agree("issued", ["2020-01-01", "2020-02-01"], ["2020-01-01", "2020-02-01"]), True)
    print("accuracy_wch: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


def stored_wch(conn, event_id):
    """What the published table holds for one release today, as a prediction."""
    try:
        rs = conn.execute("SELECT change, status, n_warrants, strike_old, strike_new, issued, expiry_old, expiry_new, "
                          "program_end, n_exercised, proceeds, n_remaining FROM warrant_changes WHERE event_id=? "
                          "ORDER BY ordinal", (event_id,)).fetchall()
    except Exception:  # noqa: BLE001  (no table before the first publish)
        return None
    if not rs:
        return None
    rows = []
    for ch, st, n, so, sn, iss, eo, en, pe, nx, pr, nr in rs:
        rows.append({"change": ch, "status": st, "n_warrants": n, "strike_old": so, "strike_new": sn,
                     "issued": iss.split("|") if iss else None, "expiry_old": eo,
                     "expiry_new": en.split("|") if en else None, "program_end": pe, "n_exercised": nx,
                     "proceeds": pr, "n_remaining": nr})
    return {"rows": rows}


def _wch_from_records(records):
    from portal.extractors import warrant_changes as X
    return X.to_prediction(records)


if register_spec is not None:
    register_spec(TagSpec(
        name="warrant_changes", tag="Financings", key_fields=WCH_KEY_FIELDS, report_fields=WCH_REPORT_FIELDS,
        judge=judge_wch, stored=stored_wch, from_records=_wch_from_records,
        describe={"row": "every row is one change to one group of already-issued warrants (or one incentive programme) "
                         "a release reports",
                  "change": "extension, acceleration, acceleration_waived, repricing, incentive, exercise, expired or "
                            "withdrawn",
                  "status": "proposed (subject to approval, or 'intends to') or effective",
                  "expiry_new": "the new expiry date(s) an extension or acceleration sets",
                  "issued": "the issue date(s) of the warrants changed, as the release gives them",
                  "strike_old": "the exercise price before the change",
                  "program_end": "the date an early-exercise incentive programme ends (reported)",
                  "n_warrants": "how many warrants the change covers (reported)",
                  "n_exercised": "how many were exercised (reported)",
                  "proceeds": "what the exercises raised (reported)",
                  "n_remaining": "how many of the group are left; 0 retires the expiry event (reported)",
                  "expiry_old": "the expiry before the change (reported)",
                  "strike_new": "the exercise price after a repricing or incentive (reported)"}))

if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test() else 0)
