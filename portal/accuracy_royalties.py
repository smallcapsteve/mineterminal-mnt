"""How /royalties-streams is scored (ROY_SPEC_V1, 2026-09-21).

The page shows ONE ROW PER ROYALTY OR STREAM INTEREST a release reports as news (Justin, 2026-09-21). A
release is judged as a set of rows; a predicted row is paired with the labelled row it claims to be before
any field is scored.

Pairing, strongest first over the whole grid: same property (5), same type and rate (3), same type (1).
Leftovers are paired in order, so a row with a wrong property AND a wrong rate is counted wrong on both.

Names (property, operator, buyer, seller) are compared as sets of words once generic words are dropped
('Spanish Mountain Gold Project' = 'Spanish Mountain Gold'; 'Wheaton Precious Metals Corp.' = 'Wheaton
Precious Metals'): they agree when one set holds the other, or when both start with the same distinctive word
('Panuco-Copala' and 'Panuco (Silverstone concessions)'; not 'West Cache' and 'West Timmins'). A party list
('Franco-Nevada; EMX Royalty') agrees when every name on each side has a partner on the other.

Rates agree within 0.005 points, prices within 1%. A field the label does not state is set aside rather than
judged (the Resource Estimates rule): 'a prospector' as the seller says nothing about a name a reader found.

Registered by portal/accuracy.py, which imports this module at the end of its own definitions.
"""
from __future__ import annotations

import re
import unicodedata

from portal.accuracy import TagSpec, register_spec

ROY_KEY_FIELDS = ("row", "type", "property", "buyer", "seller", "action")
ROY_REPORT_FIELDS = ("rate", "price", "currency", "operator", "metal", "status")

_ROW_FIELDS = ("type", "rate_pct", "metal", "property", "operator", "buyer", "seller", "price", "currency",
               "action", "status", "price_note")

_GENERIC = {"the", "a", "an", "of", "and", "de", "del", "la", "project", "projects", "mine", "mines", "property",
            "properties", "deposit", "concession", "concessions", "claim", "claims", "operation", "operations",
            "complex", "district", "mineral", "lease", "inc", "corp", "corporation", "ltd", "limited", "plc", "llc",
            "lp", "co", "company", "sa", "cv", "gold", "silver", "copper", "tin", "tantalum", "tungsten", "mining",
            "metals", "minerals", "resources", "royalty", "royalties", "streaming", "stream", "private", "resource",
            "group", "holdings", "holding", "fund", "funds", "subsidiary", "its", "flagship", "existing", "test",
            "plant", "pilot"}


def _words(s):
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]+", s) if w not in _GENERIC}


_WEAK = {"los", "las", "el", "san", "santa", "lake", "lakes", "river", "mountain", "hill", "hills", "creek", "north",
         "south", "east", "west", "northern", "southern", "big", "little", "new", "red", "black", "white", "grand"}


def _first_word(s):
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    for w in re.findall(r"[a-z0-9]+", s):
        if w not in _GENERIC:
            return w
    return None


def name_agrees(a, b):
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    if wa <= wb or wb <= wa:
        return True
    fa, fb = _first_word(a), _first_word(b)
    return bool(fa) and fa == fb and fa not in _WEAK


def parties_agree(a, b):
    la = [x for x in re.split(r"\s*(?:;|\band\b|&)\s*", str(a or "")) if _words(x)]
    lb = [x for x in re.split(r"\s*(?:;|\band\b|&)\s*", str(b or "")) if _words(x)]
    if not la or not lb:
        return False
    return all(any(name_agrees(x, y) for y in lb) for x in la) and all(any(name_agrees(y, x) for x in la) for y in lb)


def _close(a, b, rel=0.01, absol=0.0):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= max(rel * max(abs(a), abs(b)), absol)


def _unnamed(v):
    return v is None or bool(re.match(r"(?i)\s*(?:a|an)\s", str(v)))


def roy_match(labels, preds):
    scored = []
    for li, lab in enumerate(labels):
        for pi, pr in enumerate(preds):
            n = 0
            if lab.get("property") and name_agrees(lab.get("property"), pr.get("property")):
                n = 5 + (1 if lab.get("rate_pct") is not None and _close(lab.get("rate_pct"), pr.get("rate_pct"), 0, 0.005) else 0)
            elif lab.get("type") == pr.get("type"):
                n = 3 if (lab.get("rate_pct") is not None and _close(lab.get("rate_pct"), pr.get("rate_pct"), 0, 0.005)) else 1
            if n:
                scored.append((-n, li, pi))
    scored.sort()
    got, used = {}, set()
    for _n, li, pi in scored:
        if li in got or pi in used:
            continue
        got[li] = pi
        used.add(pi)
    for li in range(len(labels)):
        if li in got:
            continue
        for pi in range(len(preds)):
            if pi not in used:
                got[li] = pi
                used.add(pi)
                break
    extra = [pi for pi in range(len(preds)) if pi not in used]
    return [(li, got.get(li)) for li in range(len(labels))], extra


_FIELD_OF = {"rate": "rate_pct"}


def _judge_field(f, lab, pr):
    k = _FIELD_OF.get(f, f)
    lv, pv = lab.get(k), pr.get(k)
    if f in ("property", "operator", "metal"):
        if _unnamed(lv):
            return None
        return name_agrees(lv, pv) if f != "metal" else _words(lv) == _words(pv) or name_agrees(lv, pv)
    if f in ("buyer", "seller"):
        if _unnamed(lv):
            return None
        return parties_agree(lv, pv)
    if f == "rate":
        if lv is None:
            return None
        return _close(lv, pv, 0, 0.005)
    if f == "price":
        if lv is None:
            return None
        return _close(lv, pv, 0.01)
    if lv is None:
        return None
    return str(lv).lower() == str(pv or "").lower()


def judge_royalties(pred, expect):
    """pred: None or {rows: [...]}; expect: {complete, rows: [...]} (the fields in _ROW_FIELDS)."""
    fields = ROY_KEY_FIELDS + ROY_REPORT_FIELDS
    out = {f: [] for f in fields}
    gold = list(expect.get("rows") or [])
    shown = list((pred or {}).get("rows") or [])
    if not shown:
        out["row"].extend(["fn"] * len(gold))
        return out
    if not gold:
        out["row"].extend(["fp"] * len(shown))
        return out
    pairs, extra = roy_match(gold, shown)
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
            elif pr.get(_FIELD_OF.get(f, f)) is not None:
                out[f].extend(["fp", "fn"])
            else:
                out[f].append("fn")
    if expect.get("complete", True):
        out["row"].extend(["fp"] * len(extra))
    return out


def _table_exists(conn):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name='royalty_deals'").fetchone() is not None


def stored_royalties(conn, event_id):
    """What /royalties-streams shows for one release. A marker row (type NULL) states nothing."""
    if not _table_exists(conn):
        return None
    rows = list(conn.execute(
        "SELECT " + ", ".join(_ROW_FIELDS) + " FROM royalty_deals WHERE event_id=? AND type IS NOT NULL ORDER BY ordinal",
        (event_id,)))
    return {"rows": [dict(zip(_ROW_FIELDS, r)) for r in rows]} if rows else None


def _roy_from_records(records):
    from portal.extractors import royalties as X
    return X.to_prediction(records)


def _roy_candidate_predictor(conn, extractor, version):
    """Scored through the publisher, so what the page would show is what is tested."""
    from portal import royalties_publish as P
    rows, _st = P.compute(P.load_items(conn, version))
    by_event = {}
    for r in rows:
        if r["type"] is None:
            continue
        by_event.setdefault(r["event_id"], []).append({k: r.get(k) for k in _ROW_FIELDS})
    return lambda it, ev: ({"rows": by_event[it["event_id"]]} if it["event_id"] in by_event else None)


register_spec(TagSpec(
    name="royalties", tag="Royalties & Streams", key_fields=ROY_KEY_FIELDS, report_fields=ROY_REPORT_FIELDS,
    judge=judge_royalties, stored=stored_royalties, from_records=_roy_from_records,
    candidate_predictor=_roy_candidate_predictor,
    describe={"row": "every row on the page is a royalty or stream deal the release reports -- bought, sold, granted, "
                     "bought back or amended -- and every one it reports is on the page",
              "type": "NSR, GRR, NPI, stream or other",
              "property": "the mine or project the interest sits on",
              "buyer": "the holder of the interest after the deal",
              "seller": "the party that gave the interest up or granted it",
              "action": "new, transfer, buyback or amendment",
              "rate": "the royalty rate or stream percentage (reported)",
              "price": "the cash price (reported)",
              "currency": "USD or CAD (reported)",
              "operator": "the company that owns or operates the property (reported)",
              "metal": "the metal the interest pays in (reported)",
              "status": "agreed or closed (reported)"}))
