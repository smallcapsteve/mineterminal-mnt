"""How /management-changes is scored (MGMT_SPEC_V1, 2026-09-17).

The page shows ONE ROW PER PERSON (Justin, 2026-09-17), a different shape from the other tags, so a
release is judged as a set of changes rather than as one row. A predicted change is paired with an
expected one by name -- the whole name folded, or the surname, because releases shorten and shout
names -- and only then are its role, action and scope scored. A predicted change that pairs with
nobody is a person the page invented.

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

import re
import unicodedata

from portal.accuracy import TagSpec, register_spec

MGMT_KEY_FIELDS = ("row", "person", "role", "action", "scope")


def _mgmt_name(s):
    t = unicodedata.normalize("NFKD", s or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z ]", " ", t.lower()).split()


def _mgmt_same_person(a, b):
    wa, wb = _mgmt_name(a), _mgmt_name(b)
    if not wa or not wb:
        return False
    if wa == wb:
        return True
    la = [w for w in wa if len(w) > 1]
    lb = [w for w in wb if len(w) > 1]
    if not la or not lb:
        return False
    if la[-1] == lb[-1]:
        return True
    return wa[0] == wb[0] and (set(wa) < set(wb) or set(wb) < set(wa))


def _mgmt_same_role(a, b):
    from portal.extractors import mgmt_roles as R
    if not a and not b:
        return True
    if not a or not b:
        return False
    return R.same_role(a, b)


def judge_management(pred, expect):
    """pred: None or {changes: [{action, person, role, scope, effective_date, interim}]}
    expect: {is_management_change, changes: [{action, person, role, scope}]}

    row     the release is shown at all, and only when it announces a change
    person  every person shown is one the release names, and every one it names is shown
    role    the paired change's role names the same position
    action  joined / left / changed matches
    scope   board / management / advisory matches"""
    out = {f: [] for f in MGMT_KEY_FIELDS}
    want = bool(expect.get("is_management_change")) and bool(expect.get("changes"))
    shown = bool(pred and pred.get("changes"))
    if not shown:
        if want:
            out["row"].append("fn")
            for _ in expect.get("changes") or []:
                out["person"].append("fn")
        return out
    out["row"].append("tp" if want else "fp")
    if not want:
        return out
    gold = list(expect.get("changes") or [])
    used = set()
    for p in pred["changes"]:
        j = None
        for i, g in enumerate(gold):
            if i in used:
                continue
            if p.get("person") and g.get("person") and _mgmt_same_person(p["person"], g["person"]):
                j = i
                break
        if j is None:                                         # a role with no person pairs with a nameless change
            for i, g in enumerate(gold):
                if i not in used and not g.get("person") and not p.get("person"):
                    j = i
                    break
        if j is None:
            out["person"].append("fp")
            continue
        used.add(j)
        g = gold[j]
        out["person"].append("tp")
        out["role"].append("tp" if _mgmt_same_role(p.get("role"), g.get("role")) else "fp")
        out["action"].append("tp" if p.get("action") == g.get("action") else "fp")
        out["scope"].append("tp" if p.get("scope") == g.get("scope") else "fp")
    for i, _g in enumerate(gold):
        if i not in used:
            out["person"].append("fn")
    return out


def stored_management(conn, event_id):
    """What /management-changes shows for one release today, legacy table or published alike."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(management_changes)")}
    sel = "action, person, role, scope" + (", effective_date, interim" if "effective_date" in cols else "")
    rows = list(conn.execute(f"SELECT {sel} FROM management_changes WHERE event_id=?", (event_id,)))
    if not rows:
        return None
    changes = []
    for r in rows:
        c = {"action": r[0], "person": r[1], "role": r[2], "scope": r[3]}
        if len(r) > 4:
            c["effective_date"], c["interim"] = r[4], bool(r[5])
        changes.append(c)
    return {"changes": changes}


def _mgmt_from_records(records):
    from portal.extractors import management as X
    return X.to_prediction(records)


def _mgmt_rows(conn, version):
    from portal import management_publish as P
    rows, _st = P.compute(P.load_items(conn, version))
    return rows


def _mgmt_candidate(conn, extractor, version):
    return {r["event_id"] for r in _mgmt_rows(conn, version)}


def _mgmt_current(conn):
    return {r[0] for r in conn.execute("SELECT DISTINCT event_id FROM management_changes")}


def _mgmt_describe(conn, event_ids):
    out = []
    for eid in event_ids:
        r = conn.execute("SELECT ticker, substr(published_at, 1, 10), action, person, role, raw_headline "
                         "FROM management_changes WHERE event_id=? LIMIT 1", (eid,)).fetchone()
        if r:
            out.append(f"{eid[:8]} {r[0]} {r[1]} | was {r[2]} {r[3] or '(nobody)'} / {r[4] or '(no role)'} "
                       f"| {(r[5] or '')[:90]}")
    return out


def _mgmt_candidate_predictor(conn, extractor, version):
    """The page is judged through its publisher, so the wire-copy rule is scored with the reader."""
    rows = _mgmt_rows(conn, version)
    by_event = {}
    for r in rows:
        by_event.setdefault(r["event_id"], []).append(
            {"action": r["action"], "person": r["person"], "role": r["role"], "scope": r["scope"],
             "effective_date": r["effective_date"], "interim": bool(r["interim"])})
    return lambda it, ev: ({"changes": by_event[it["event_id"]]} if it["event_id"] in by_event else None)


register_spec(TagSpec(
    name="management", tag="Management Changes", key_fields=MGMT_KEY_FIELDS, judge=judge_management,
    stored=stored_management, from_records=_mgmt_from_records, candidate_predictor=_mgmt_candidate_predictor,
    replaces={"page": "management", "min_row_recall": 0.950, "candidate": _mgmt_candidate,
              "current": _mgmt_current, "describe": _mgmt_describe},
    describe={"row": "a release is shown only when it announces a change of management, board or advisors",
              "person": "every person on the page is named by the release, and everyone it names is on the page",
              "role": "the role shown is the position that person took or left",
              "action": "joined, left or changed role matches what the release announced",
              "scope": "board, management or advisory matches the position"}))
