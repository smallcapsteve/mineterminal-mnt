"""Technical-report project names (TRX_PN1, 2026-10-07): the project-naming step of the technical-report reader
(TRX v0.7f), and the technical-report part of the shared project-name test.

Justin, 2026-10-07: "Can we add this technical report reader to the Project-name helper?" (he chose "Reader uses the
helper"), then "Can you do both follow ups?". So:
  * the reader names a report's project through portal/project_names.py, with the steps below;
  * `accuracy_run.py project-names` also scores those names on 176 labelled reports
    (accuracy/report_names/technical_reports.json), so a helper change that makes a report name worse shows up in the
    same check as the release labels. The file is not in accuracy/sets on purpose: report items have no MNT event.

    name_project(title, reader_name, reader_kind) -> (name, kind, how)   reader_name: the reader's own title rule
    report_name_check()                           -> {"items", "right", "changed", "changes", ...}

The reader's own name is kept unless (1) PN.clean() only removed non-name words ("2013-2014 Cayenne" -> "Cayenne"),
(2) it has a kind word inside it, when the helper's finder on the title names the project ("Candelones Extension
Deposit Candelones" -> "Candelones"), or (3) it is empty, when the helper's finder on the title is used ("Ruby Hill").
Names are shown without the kind word (returned separately) and without a trailing commodity chain.
Measured: claude/MTP_TR_PN_2026-10-07.md (project names right 165 -> 169 of 176, none worse).
The commodity word lists are frozen from the reader (trx7.COMMOD7 / METAL_NAMES7) on 2026-10-07."""
import json
import os
import re
import unicodedata

from portal import project_names as PN

VERSION = "1.0.0"
READER = "trx-0.7f"
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "accuracy", "report_names", "technical_reports.json")

COMMOD = frozenset(['(ree)', 'ag', 'anthracite', 'antimony', 'au', 'au-cu', 'barite', 'base', 'base-metal', 'bauxite', 'beryllium', 'bismuth', 'borate', 'boron', 'brine', 'caesium', 'cesium', 'chrome', 'chromite', 'co', 'coal', 'cobalt', 'copper', 'copper-gold', 'copper-nickel', 'cu', 'cu-au', 'cu-ni-pge', 'diamond', 'diamonds', 'earth', 'earths', 'element', 'elements', 'fluorspar', 'gallium', 'germanium', 'gold', 'gold-copper', 'gold-silver', 'graphite', 'gypsum', 'heap', 'heavy', 'helium', 'hms', 'ilmenite', 'indium', 'iron', 'iron-ore', 'kaolin', 'leach', 'lead', 'lead-zinc', 'li', 'lithium', 'magnesium', 'manganese', 'metal', 'metallurgical', 'metals', 'mineral-sands', 'mining', 'molybdenum', 'ni', 'ni-cu', 'ni-cu-pge', 'nickel', 'nickel-copper', 'niobium', 'open', 'ore', 'oxide', 'palladium', 'pb', 'pge', 'pges', 'pgm', 'pgms', 'phosphate', 'pit', 'platinum', 'polymetallic', 'porphyry', 'potash', 'precious', 'precious-metal', 'rare', 'rare-earth', 'rare-earths', 'ree', 'rees', 'rutile', 'salt', 'sands', 'scandium', 'silica', 'silver', 'silver-gold', 'sulfide', 'sulphide', 'taconite', 'tantalum', 'tellurium', 'thermal', 'tin', 'titanium', 'tungsten', 'u', 'underground', 'uranium', 'vanadium', 'zinc', 'zinc-lead', 'zircon', 'zn'])
METALS = frozenset(['ag', 'antimony', 'au', 'bismuth', 'co', 'cobalt', 'copper', 'cu', 'fe', 'gold', 'graphite', 'iron', 'lead', 'li', 'lithium', 'manganese', 'mn', 'mo', 'molybdenum', 'ni', 'nickel', 'palladium', 'pb', 'pd', 'platinum', 'pt', 'rhodium', 'sb', 'silver', 'sn', 'tellurium', 'tin', 'tungsten', 'u', 'uranium', 'v', 'vanadium', 'w', 'zinc', 'zn'])

_KINDSUF = {"project": "Project", "property": "Property", "mine": "Mine", "deposit": "Deposit", "complex": "Complex",
            "prospect": "Prospect", "claim group": "Claim Group", "claims": "Claims", "concession": "Concession",
            "camp": "Camp", "operation": "Operation"}
_SUF_RX = re.compile(r"(?i)\s+(projects?|property|properties|mines?|deposits?|claims|claim\s+groups?|prospects?|"
                     r"concessions?|complex|camp|operations?)$")
_KIND_IN = re.compile(r"(?i)\b(?:projects?|property|properties|deposits?|mines?)\b")


def _is_commod(w):
    w = w.lower().strip(".,()")
    if w in COMMOD:
        return True
    parts = [x for x in re.split(r"[-/]", w) if x]
    return len(parts) >= 2 and all(x in METALS or x in COMMOD for x in parts)


def _strip_commodity_tail(words):
    """drop a trailing commodity chain, connectors included ("Potash and Lithium", "Rare Earths and Mineral Sands")"""
    changed = True
    while changed and words:
        changed = False
        if len(words) >= 2 and words[-1].lower() in ("sands", "earths", "earth", "elements") and \
                words[-2].lower() in ("mineral", "rare", "heavy"):
            words = words[:-2]
            changed = True
        elif _is_commod(words[-1]) or (words[-1].lower() in ("and", "&", ",") and len(words) > 1) or \
                (len(words) > 1 and re.fullmatch(r"(?i)projects?|property|mines?|deposits?", words[-1])):
            words = words[:-1]
            changed = True
    return words


def _with_suffix(v, kind):
    suf = _KINDSUF.get((kind or "").lower())
    if v and suf and not re.search(r"(?i)\b" + re.escape(suf) + r"s?$", v):
        return v + " " + suf
    return v


def _split_suffix(v):
    if not v:
        return None, None
    m = _SUF_RX.search(v)
    kind = None
    if m:
        k = m.group(1).lower()
        kind = "claim group" if k.startswith("claim group") else "property" if k == "properties" else \
            k if k == "claims" else k.rstrip("s")
        v = v[:m.start()].strip()
    v = " ".join(_strip_commodity_tail(v.split())).strip(" -")
    return (v or None), kind


def _noise_only(before, after):
    kept = {w.lower() for w in after.split()}
    gone = [w for w in before.split() if w.lower() not in kept]
    return bool(gone) and all(not re.search(r"[A-Z]", w) or not re.search(r"[A-Za-z]{2}", w) for w in gone)


def _from_title(title):
    found = PN.find_with(title or "")
    return _split_suffix(found[0][1]) if found else (None, None)


def name_project(title, reader_name, reader_kind=None):
    """(name, kind, how): how is None when the reader's own name is kept."""
    a, kind = reader_name, reader_kind
    if a:
        c = PN.clean(_with_suffix(a, kind))
        cb, ck = _split_suffix(c) if c else (None, None)
        if cb and cb != a and _noise_only(a, cb):
            return cb, (ck or kind), "helper clean"
        if _KIND_IN.search(a):
            tv, tk = _from_title(title)
            if tv:
                return tv, (tk or kind), "helper find on the title"
        return a, kind, None
    tv, tk = _from_title(title)
    if tv:
        return tv, tk, "helper find on the title"
    return None, None, None


# ---------------------------------------------------------------- scoring: the report reader's own project rule
_APOS = "'`" + chr(0x2019) + chr(0x2018)
_COMMOD_RX = r"\b(gold|silver|copper|tin|zinc|nickel|lithium|uranium|manganese|molybdenum|copper molybdenum|iron|polymetallic)\b"


def _fold(s):
    s = re.sub("[" + _APOS + "]", "", str(s or ""))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def _norm(s):
    p = " ".join(re.sub(r"\b(project|projects|property|properties|deposit|deposits|mine|the)\b", " ", _fold(s)).split())
    return " ".join(re.sub(_COMMOD_RX, " ", p).split())


def is_right(name, labels):
    """Right when the name equals a labelled name, ignoring kind words and metal words (Justin, 2026-10-06)."""
    g = _norm(name)
    return bool(g) and g in [_norm(x) for x in (labels if isinstance(labels, list) else [labels]) if x]


def report_name_check(path=DATA):
    d = json.load(open(path))
    n = right = 0
    changes = []
    for it in d["items"]:
        name, _, _ = name_project(it.get("title"), it.get("reader_name"), it.get("reader_kind"))
        n += 1
        right += is_right(name, it.get("labels") or [])
        if (name or None) != (it.get("expect") or None):
            changes.append(f"{it.get('set')} G{it.get('g')} {it.get('ticker')}: {it.get('expect')!r} -> {name!r} "
                           f"(label {it.get('labels')!r})")
    return {"set": d.get("name"), "items": n, "right": right, "changed": len(changes), "changes": changes,
            "frozen_right": d.get("frozen_right"), "reader": READER, "helper": getattr(PN, "VERSION", None)}


def _selftest():
    cases = [
        (("2013-2014 Cayenne Project NI 43-101", "2013-2014 Cayenne", "project"), "Cayenne"),
        (("Da Tambuk Project", "Da Tambuk", "project"), "Da Tambuk"),
        (("Technical Report on the Candelones Project, Dominican Republic", "Candelones Extension Deposit Candelones",
          "project"), "Candelones"),
        (("Garrcon Deposit- Garrison Gold Project, Ontario", "Garrcon Deposit- Garrison", "project"), "Garrison"),
        (("Ruby Hill Project, Eureka County Nevada", None, None), "Ruby Hill"),
        (("Update for Don Deposit Mineral Resource Estimate Howard’s Pass Property", "Howard’s Pass", "property"),
         "Howard’s Pass"),
        (("Technical Report On The Brazil Lake Lithium-Bearing Pegmatite Property",
          "Brazil Lake Lithium-Bearing Pegmatite", "property"), "Brazil Lake Lithium-Bearing Pegmatite"),
    ]
    bad = [(args, want, name_project(*args)[0]) for args, want in cases if name_project(*args)[0] != want]
    assert is_right("Bisie", ["Bisie Tin"]) and not is_right("Rakita", ["Coka Rakita"])
    return bad


if __name__ == "__main__":
    b = _selftest()
    print("selftest", "ok" if not b else b)
    if os.path.exists(DATA):
        r = report_name_check()
        print({k: v for k, v in r.items() if k != "changes"})
        for c in r["changes"][:20]:
            print("  ", c)
