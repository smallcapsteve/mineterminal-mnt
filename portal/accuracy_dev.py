"""How the Mine Development & Operations page is scored (DEV_SPEC_V1, 2026-09-28).

The page shows ONE ROW PER EVENT a release reports for the issuer's own mine, plant or project: build milestones,
operating status changes, incidents, and offtakes, shipments and contracts (Justin, 2026-09-27/28). A release is judged
as a set of rows; a predicted row is paired with the labelled row it claims to be before any field is scored.

Pairing, strongest first over the whole grid: a pair needs the same event type, or the same mine with both types in
the same group (build / status / incident / commercial). The score adds the same type (4), an agreeing mine (3), the
same status (1) and an agreeing date (1). Leftovers stay unpaired: a predicted row with no partner is a false row, a
label with no partner a missed one.

Key fields (Justin: event type and mine; date, actual or targeted; early figures; capex and % complete): event_type,
mine, status, event_date, figures, capex, pct_complete. A mine agrees when the shared project-name helper calls the
names the same, or their core words overlap. A date agrees to the precision both give (2017-10 agrees with 2017-10-07;
a quarter agrees with a month inside it). Capex agrees within 2% on the low end (and the high end when both give one);
% complete within one point. Each figure is a claim: it agrees when the label has a figure of the same metric within
2%. The label states every key field, blank where the release does not say, so a value the reader claims where the
label is blank is a false claim (both blank is set aside). Reported fields (incident_kind, counterparty) are set aside
when the label has none.

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

# Justin 2026-09-28 (after honest sample 2): the narrowed reader gates event type, mine and status; the date, figures,
# capex and % complete are measured and reported but not gated until they measure well.
DEV_KEY_FIELDS = ("row", "event_type", "mine", "status")
DEV_REPORT_FIELDS = ("event_date", "figures", "capex", "pct_complete", "incident_kind", "counterparty")

GROUP = {}
for _t in ("construction_decision", "construction_start", "construction_progress", "infrastructure", "site_cleanup", "commissioning",
           "first_production", "commercial_production", "ramp_up", "expansion"):
    GROUP[_t] = "build"
for _t in ("restart", "suspension", "care_maintenance", "closure", "status_update"):
    GROUP[_t] = "status"
GROUP["incident"] = "incident"
for _t in ("offtake", "shipment", "contract"):
    GROUP[_t] = "commercial"

_GENERIC = {"the", "mine", "mines", "project", "projects", "property", "gold", "silver", "copper", "complex", "operation",
            "operations", "deposit", "mill", "plant", "and", "of", "de", "la", "del", "phase", "underground"}


def _fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    return "".join(c for c in s if not unicodedata.combining(c))


def mine_agrees(a, b):
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


def _q_of(month):
    return (int(month) - 1) // 3 + 1


def date_agrees(p, l):
    """Agree to the precision both give; a quarter or half agrees with a month or day inside it."""
    if not p or not l:
        return False
    p, l = str(p), str(l)
    if p[:4] != l[:4]:
        return False
    ps, ls = p[5:], l[5:]
    if not ps or not ls:
        return True
    def span(x):
        if x.startswith("Q"):
            q = int(x[1]); return (3 * q - 2, 3 * q)
        if x.startswith("H"):
            h = int(x[1]); return (1, 6) if h == 1 else (7, 12)
        m = int(x[:2]); return (m, m)
    (a1, a2), (b1, b2) = span(ps), span(ls)
    if not (a1 <= b2 and b1 <= a2):
        return False
    if len(ps) >= 5 and len(ls) >= 5 and ps[:2] == ls[:2] and not ps.startswith(("Q", "H")) and not ls.startswith(("Q", "H")):
        return ps[:5] == ls[:5]
    return True


def _num_agrees(a, b, rel=0.02, abs_=0.0):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= max(rel * abs(b), abs_, 0.005)


def _empty(v):
    return v in (None, "", [], {})


def _pair_score(lab, pr):
    same_t = lab.get("event_type") == pr.get("event_type")
    ma = mine_agrees(lab.get("mine"), pr.get("mine"))
    if not same_t and not (ma and GROUP.get(lab.get("event_type")) == GROUP.get(pr.get("event_type"))):
        return None
    n = 1 + (4 if same_t else 0) + (3 if ma else 0)
    if lab.get("status") == pr.get("status"):
        n += 1
    if date_agrees(pr.get("event_date"), lab.get("event_date")):
        n += 1
    return n


def dev_match(labels, preds):
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


def _capex_agrees(p, l):
    if not p or not l:
        return False
    if not _num_agrees(p.get("value"), l.get("value")):
        return False
    if p.get("value_high") and l.get("value_high"):
        return _num_agrees(p.get("value_high"), l.get("value_high"))
    return True


def _judge_figures(lab, pr):
    out = []
    lf = list(lab.get("figures") or [])
    pf = list(pr.get("figures") or [])
    used = set()
    for f in pf:
        hit = None
        for j, g in enumerate(lf):
            if j in used:
                continue
            if (f.get("metric") == g.get("metric") or {f.get("metric"), g.get("metric")} <= {"output", "shipment"}) and \
                    _num_agrees(f.get("value"), g.get("value")):
                hit = j
                break
        if hit is None:
            out.append("fp")
        else:
            used.add(hit)
            out.append("tp")
    out.extend(["fn"] * (len(lf) - len(used)))
    return out


def _judge_field(f, lab, pr):
    """True / False / None (set aside)."""
    lv, pv = lab.get(f), pr.get(f)
    if f in ("event_type", "status"):
        return lv == pv
    if _empty(lv):
        if f in ("mine", "event_date", "capex", "pct_complete") and not _empty(pv):
            return False
        return None
    if _empty(pv):
        return False
    if f == "mine":
        return mine_agrees(lv, pv)
    if f == "event_date":
        return date_agrees(pv, lv)
    if f == "capex":
        return _capex_agrees(pv, lv)
    if f == "pct_complete":
        return _num_agrees(pv, lv, 0.0, 1.0)
    if f in ("incident_kind",):
        return str(lv) == str(pv)
    if f == "counterparty":
        return mine_agrees(lv, pv)
    return lv == pv


def judge_dev(pred, expect):
    """pred: None or {rows: [...]}; expect: {complete, rows: [...]}."""
    fields = DEV_KEY_FIELDS + DEV_REPORT_FIELDS
    out = {f: [] for f in fields}
    gold = list(expect.get("rows") or [])
    shown = list((pred or {}).get("rows") or [])
    if not shown:
        out["row"].extend(["fn"] * len(gold))
        return out
    if not gold:
        out["row"].extend(["fp"] * len(shown))
        return out
    pairs, extra = dev_match(gold, shown)
    for li, pi in pairs:
        lab = gold[li]
        if pi is None:
            out["row"].append("fn")
            continue
        pr = shown[pi]
        out["row"].append("tp")
        out["figures"].extend(_judge_figures(lab, pr))
        for f in fields[1:]:
            if f == "figures":
                continue
            ok = _judge_field(f, lab, pr)
            if ok is None:
                continue
            claimed = not _empty(pr.get(f))
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

    L = {"event_type": "construction_progress", "mine": "Blackwater Mine", "status": "underway", "event_date": "2024-06-30",
         "figures": [], "capex": {"value": 730e6, "value_high": 750e6, "currency": "CAD", "basis": "budget"}, "pct_complete": 87}
    P = dict(L, mine="Blackwater", capex={"value": 730e6, "value_high": 750e6, "currency": "CAD", "basis": "budget"}, pct_complete=87.0)
    r = judge_dev({"rows": [P]}, {"rows": [L]})
    eq("all right", [r[f] for f in DEV_KEY_FIELDS + DEV_REPORT_FIELDS[:4]], [["tp"], ["tp"], ["tp"], ["tp"], ["tp"], [], ["tp"], ["tp"]])
    r = judge_dev({"rows": [dict(P, status="achieved", event_date="2024-07-15")]}, {"rows": [L]})
    eq("wrong status and date", (r["status"], r["event_date"]), (["fp", "fn"], ["fp", "fn"]))
    r = judge_dev({"rows": [dict(P, event_type="expansion")]}, {"rows": [L]})
    eq("same mine, same group: paired, type wrong", (r["row"], r["event_type"]), (["tp"], ["fp", "fn"]))
    r = judge_dev({"rows": [dict(P, event_type="incident")]}, {"rows": [L]})
    eq("different group never pairs", r["row"], ["fn", "fp"])
    r = judge_dev({"rows": [P]}, {"rows": []})
    eq("no event", r["row"], ["fp"])
    eq("dates", (date_agrees("2017-10-07", "2017-10"), date_agrees("2024-08", "2024-Q3"), date_agrees("2024-Q4", "2024-Q3"),
                 date_agrees("2021", "2021-Q4"), date_agrees("2023-09-30", "2023-09-29")), (True, True, False, True, False))
    r = judge_dev({"rows": [dict(P, figures=[{"metric": "output", "value": 111450, "unit": "oz"}])]},
                  {"rows": [dict(L, figures=[{"metric": "output", "value": 111450, "unit": "oz"}, {"metric": "throughput",
                                                                                                    "value": 1000}])]})
    eq("figures", r["figures"], ["tp", "fn"])
    print("accuracy_dev: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


def stored_dev(conn, event_id):
    """What /mine-development shows for one release today (the published table), as a prediction. Untagged releases
    are not on the page, so they read as no rows."""
    import json as _json
    try:
        rs = conn.execute("SELECT event_type, mine, status, event_date, pct_complete, incident_kind, counterparty, "
                          "figures_json, capex, capex_high, capex_currency, capex_basis FROM mine_dev_events "
                          "WHERE event_id=? AND event_type IS NOT NULL ORDER BY ordinal", (event_id,)).fetchall()
    except Exception:  # noqa: BLE001  (no table before the first publish)
        return None
    if not rs:
        return None
    rows = []
    for et, mine, st, ed, pct, ik, cp, fj, cx, cxh, cxc, cxb in rs:
        rows.append({"event_type": et, "mine": mine, "status": st, "event_date": ed, "pct_complete": pct,
                     "incident_kind": ik, "counterparty": cp, "figures": _json.loads(fj) if fj else [],
                     "capex": ({"value": cx, "value_high": cxh, "currency": cxc, "basis": cxb} if cx is not None
                               else None)})
    return {"rows": rows}


def _dev_from_records(records):
    from portal.extractors import mine_dev as X
    return X.to_prediction(records)


if register_spec is not None:
    register_spec(TagSpec(
        name="mine_dev", tag="Mine Development & Operations", key_fields=DEV_KEY_FIELDS,
        report_fields=DEV_REPORT_FIELDS, judge=judge_dev, stored=stored_dev, from_records=_dev_from_records,
        project_labels=("rows", "mine"),
        describe={"row": "every row on the page is one mine-development or operations event a release reports for the issuer's own "
                         "mine, plant or project",
                  "event_type": "construction decision, construction start or progress, infrastructure, site cleanup, commissioning, "
                                "first production, commercial production, ramp-up, expansion, restart, suspension, care and "
                                "maintenance, closure, status update, incident, offtake, shipment or contract",
                  "mine": "the mine, plant or project as the release names it",
                  "status": "achieved, underway or planned",
                  "event_date": "the event date (the target date for a planned event, the 'as at' date for one underway)",
                  "figures": "numbers stated with the milestone: output, throughput, % of nameplate, shipment tonnes",
                  "capex": "the construction, initial or expansion capital stated with the event (budget, spent or committed)",
                  "pct_complete": "overall % complete",
                  "incident_kind": "the kind of incident (reported)",
                  "counterparty": "the offtaker, contractor or buyer (reported)"}))

if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test() else 0)
