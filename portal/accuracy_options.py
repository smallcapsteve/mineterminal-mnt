"""How /property-options is scored (OPT_SPEC_V1, 2026-09-23).

The page shows ONE ROW PER LAND DEAL an item reports: options in and out (earn-ins included), staking, claim
purchases, property purchases and property sales, each at its stage as of the item -- proposed, signed, payment,
completed, amended or terminated. Justin, 2026-09-23. A release is judged as a set of rows; a predicted row is paired
with the labelled row it claims to be before any field is scored.

Pairing, strongest first over the whole grid: a row can only pair with a label on an agreeing property (or either
property unstated); among those, the score adds the same deal type (3), stage (3), an agreeing counterparty (2) and
the same interest (1). A pair with neither property stated needs an agreeing counterparty or the same deal type.
Leftovers stay unpaired: a predicted row with no partner is a false row, a label with no partner a missed one.

Property names are compared as sets of words once generic words ('Property', 'Project', 'Claims', commodity words)
are dropped; a one-letter difference still agrees. A counterparty agrees when the core words of its name overlap
(legal and generic words -- Inc, Corp, Resources, Mining, Gold -- dropped). Numbers agree within 2%.

What is judged when the label states nothing: deal_type and stage are always stated. For property, counterparty and
interest_pct a label with no value means the release does not name one (an unnamed property, an arm's-length
vendor), so a value the reader claims there is a false claim; both empty is set aside. The reported terms (cash,
shares, work, nsr, term, area) are set aside when the label has none.

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

import re
import unicodedata

try:
    from portal.accuracy import TagSpec, register_spec
except Exception:  # pragma: no cover - standalone use of the judge
    TagSpec = register_spec = None

OPT_KEY_FIELDS = ("row", "deal_type", "stage", "property", "counterparty", "interest_pct")
OPT_REPORT_FIELDS = ("cash", "shares", "work", "nsr", "term", "area")

_ROW_FIELDS = ("deal_type", "stage", "property", "counterparty", "interest_pct", "cash", "currency", "shares", "work",
               "nsr", "term", "area", "date", "metal", "chain_key", "stage_rank", "latest")

_GENERIC = {"the", "a", "an", "of", "and", "de", "del", "la", "project", "projects", "property", "properties",
            "claims", "claim", "block", "blocks", "area", "mine", "mines", "deposit", "deposits", "gold", "silver",
            "copper", "lithium", "uranium", "nickel", "zinc", "lead", "tenements", "tenement", "licence", "licences",
            "license", "licenses", "package", "mineral", "minerals", "metals", "critical", "polymetallic", "rare",
            "earth", "earths", "cu", "au", "ag", "ni", "north", "south", "east", "west", "extension"}
_CO_GENERIC = {"inc", "ltd", "corp", "corporation", "limited", "llc", "resources", "the", "mining", "minerals", "metals",
               "gold", "exploration", "explorations", "ventures", "b", "c", "and", "of", "co", "company", "pty", "s", "a",
               "sa", "de", "cv", "holdings", "group", "canada", "silver", "copper", "uranium", "lithium", "mines"}


def _fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    return "".join(c for c in s if not unicodedata.combining(c))


def _words(s, generic=_GENERIC):
    return {w for w in re.findall(r"[a-z0-9&]+", _fold(s)) if w not in generic}


def _one_edit(x, y):
    if abs(len(x) - len(y)) > 1 or min(len(x), len(y)) < 4:
        return False
    if len(x) == len(y):
        return sum(a != b for a, b in zip(x, y)) == 1
    if len(x) > len(y):
        x, y = y, x
    return any(y[:i] + y[i + 1:] == x for i in range(len(y)))


def name_agrees(a, b):
    """Property names: the same core words (either inside the other, or overlapping on a multi-property label such as
    'A / B / C'); a one-letter typo still agrees."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return _fold(a).strip() == _fold(b).strip()
    if wa <= wb or wb <= wa:
        return True
    if all(any(w == v or _one_edit(w, v) for v in wb) for w in wa) or all(any(w == v or _one_edit(w, v) for v in wa)
                                                                           for w in wb):
        return True
    parts_a = [p for p in re.split(r"\s*(?:/|,|\band\b|&)\s*", str(a or "")) if _words(p)]
    parts_b = [p for p in re.split(r"\s*(?:/|,|\band\b|&)\s*", str(b or "")) if _words(p)]
    if len(parts_a) > 1 or len(parts_b) > 1:
        return any(_words(x) <= _words(y) or _words(y) <= _words(x) for x in parts_a for y in parts_b)
    return False


def party_agrees(a, b):
    if not a or not b:
        return False
    wa, wb = _words(a, _CO_GENERIC), _words(b, _CO_GENERIC)
    if not wa or not wb:
        return _fold(a).strip() == _fold(b).strip()
    return bool(wa & wb)


def _num_agrees(a, b, rel=0.02):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= max(rel * abs(b), 0.01)


def _pair_score(lab, pr):
    lp, pp = lab.get("property"), pr.get("property")
    if lp and pp and not name_agrees(lp, pp):
        return None
    cp = party_agrees(lab.get("counterparty"), pr.get("counterparty"))
    same_type = lab.get("deal_type") == pr.get("deal_type")
    if not (lp and pp) and not (cp or same_type):
        return None
    n = 1
    if same_type:
        n += 3
    if lab.get("stage") == pr.get("stage"):
        n += 3
    if cp:
        n += 2
    if lab.get("interest_pct") is not None and _num_agrees(pr.get("interest_pct"), lab.get("interest_pct")):
        n += 1
    return n


def deal_match(labels, preds):
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


_STRICT = ("property", "counterparty", "interest_pct")


def _judge_field(f, lab, pr):
    """True / False / None (set aside)."""
    lv, pv = lab.get(f), pr.get(f)
    empty_l, empty_p = lv in (None, "", []), pv in (None, "", [])
    if f in ("deal_type", "stage"):
        return lv == pv
    if empty_l:
        if f in _STRICT and not empty_p:
            return False
        return None
    if empty_p:
        return False
    if f == "property":
        return name_agrees(lv, pv)
    if f == "counterparty":
        return party_agrees(lv, pv)
    return _num_agrees(pv, lv)


def judge_options(pred, expect):
    """pred: None or {rows: [...]}; expect: {complete, rows: [...]}."""
    fields = OPT_KEY_FIELDS + OPT_REPORT_FIELDS
    out = {f: [] for f in fields}
    gold = list(expect.get("rows") or [])
    shown = list((pred or {}).get("rows") or [])
    if not shown:
        out["row"].extend(["fn"] * len(gold))
        return out
    if not gold:
        out["row"].extend(["fp"] * len(shown))
        return out
    pairs, extra = deal_match(gold, shown)
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
            if ok:
                out[f].append("tp")
            elif pr.get(f) not in (None, "", []):
                out[f].extend(["fp"] if lab.get(f) in (None, "", []) else ["fp", "fn"])
            else:
                out[f].append("fn")
    if expect.get("complete", True):
        out["row"].extend(["fp"] * len(extra))
    return out


def _table_exists(conn):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name='land_deals'").fetchone() is not None


def stored_options(conn, event_id):
    """What /property-options shows for one item. A marker row (deal_type NULL) states nothing."""
    if not _table_exists(conn):
        return None
    rows = list(conn.execute(
        "SELECT " + ", ".join(_ROW_FIELDS) + " FROM land_deals WHERE event_id=? AND deal_type IS NOT NULL "
        "ORDER BY ordinal", (event_id,)))
    return {"rows": [dict(zip(_ROW_FIELDS, r)) for r in rows]} if rows else None


def _options_from_records(records):
    from portal.extractors import options as X
    return X.to_prediction(records)


def _options_candidate_predictor(conn, extractor, version):
    """Scored through the publisher, item by item (no chain fill-in), so what the page would show for the item is
    what is tested."""
    from portal import options_publish as P
    items = P.load_items(conn, version)
    by_event = {}
    for ev, p in items:
        rows, _st = P.compute([(ev, p)])
        rows = [{k: r.get(k) for k in _ROW_FIELDS} for r in rows if r.get("deal_type")]
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

    L = {"deal_type": "option_in", "stage": "signed", "property": "Alpha", "counterparty": "Beta Minerals Inc.",
         "interest_pct": 100, "cash": 250000, "shares": None}
    P = {"deal_type": "option_in", "stage": "signed", "property": "Alpha Property", "counterparty": "Beta Minerals",
         "interest_pct": 100.0, "cash": 250000.0, "shares": 5.0}
    r = judge_options({"rows": [P]}, {"rows": [L]})
    eq("all right", [r[f] for f in ("row", "deal_type", "stage", "property", "counterparty", "interest_pct", "cash",
                                    "shares")], [["tp"], ["tp"], ["tp"], ["tp"], ["tp"], ["tp"], ["tp"], []])
    r = judge_options({"rows": [dict(P, counterparty="Gamma Corp", stage="payment")]}, {"rows": [L]})
    eq("wrong counterparty and stage", (r["counterparty"], r["stage"]), (["fp", "fn"], ["fp", "fn"]))
    r = judge_options({"rows": [dict(P, counterparty="Gamma Corp")]}, {"rows": [dict(L, counterparty=None)]})
    eq("a counterparty the release does not name is a false claim", r["counterparty"], ["fp"])
    r = judge_options({"rows": [P, dict(P, property="Kappa")]}, {"rows": [L]})
    eq("an extra row is a false row", r["row"], ["tp", "fp"])
    r = judge_options({"rows": [dict(P, property="Kappa")]}, {"rows": [L]})
    eq("another property never pairs", r["row"], ["fn", "fp"])
    r = judge_options(None, {"rows": [L]})
    eq("missed", r["row"], ["fn"])
    r = judge_options({"rows": [P]}, {"rows": []})
    eq("no deal", r["row"], ["fp"])
    r = judge_options({"rows": [dict(P, property=None)]}, {"rows": [dict(L, property=None)]})
    eq("unnamed property pairs on type", (r["row"], r["property"]), (["tp"], []))
    eq("multi-property label", name_agrees("Hawk Ridge / Lac Leo / Tex Pro", "Lac Leo"), True)
    eq("typo agrees", name_agrees("Lago Grande", "Lagoa Grande"), True)
    print("accuracy_options: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if register_spec is not None:
    register_spec(TagSpec(
        name="options", tag="Property Options & Staking", key_fields=OPT_KEY_FIELDS,
        report_fields=OPT_REPORT_FIELDS, judge=judge_options, stored=stored_options,
        from_records=_options_from_records, candidate_predictor=_options_candidate_predictor,
        project_labels=("rows", "property"),     # ACC2 / PN_V1: the key's property labels join the shared test set
        describe={"row": "every row on the page is a land deal an item reports -- an option in or out, an earn-in, "
                         "staking, a claim or property purchase, or a property sale",
                  "deal_type": "option in, option out, staking, claim purchase, property purchase or property sale",
                  "stage": "the deal's stage as of the item: proposed, signed, payment, completed, amended or terminated",
                  "property": "the property the deal is for (blank only when the release does not name it)",
                  "counterparty": "the optionor, optionee, vendor or buyer (blank when the release does not name one)",
                  "interest_pct": "the interest earned or bought (the maximum for a staged option)",
                  "cash": "total cash consideration (reported)",
                  "shares": "total shares to be issued (reported)",
                  "work": "total exploration spending committed (reported)",
                  "nsr": "NSR royalty to the vendor, % (reported)",
                  "term": "option term in years (reported)",
                  "area": "hectares (reported)"}))

if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test() else 0)
