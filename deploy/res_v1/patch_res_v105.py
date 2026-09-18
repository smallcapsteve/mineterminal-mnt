#!/usr/bin/env python3
"""Turn RES_V1 1.0.4 into 1.0.5 (2026-09-18).

Measured at 1.0.4: detection 25/0/0/25; row 89.8%, deposit 83.5%, category 100.0%, tonnes 83.1%,
grade 67.6%, context 93.7%. Two releases carried sixteen of the twenty-four figure errors, and a
trace of the table reader showed both were the same thing.

  Q  "Au Ounces" then "(koz)" is one column. Reading "Ounces" as the unit and "(koz)" as a column
     of its own made eight columns out of seven, and the mapping then ran a place out: RUA Gold's
     tonnage came back as its contained ounces, and its grade as its tonnage.
  R  where the header has more columns than the row has values, the reader was keeping the last n
     of them and dropping the leading ones silently. That is how Fireweed's 6.3 Mt of ore came
     back as 94. A header that does not fit is a header this reader has not understood, and the
     row now states its deposit and its category and no figures.
  S  a PDF subscript can sit across blank lines as well as single line breaks.

Usage: patch_res_v105.py <resources.py>
"""
import hashlib
import sys

EDITS = [
    ('VERSION = "1.0.4"', 'VERSION = "1.0.5"'),
    ('''    col = {"label": label, "kind": "other", "metal": None, "eq": False, "unit": None, "mult": 1.0}''',
     '''    col = {"label": label, "kind": "other", "metal": None, "eq": False, "unit": None, "mult": 1.0,
           "paren_unit": False}'''),
    ('''    kind, unit, mult = _unit_in(inner if inner else s)
    if kind is None and inner:
        kind, unit, mult = _unit_in(outer)''',
     '''    kind, unit, mult = _unit_in(inner if inner else s)
    col["paren_unit"] = bool(inner and kind)
    if kind is None and inner:
        kind, unit, mult = _unit_in(outer)'''),
    ('''        if _RE_BARE_UNIT.match(ln) and merged and merged[-1]["unit"] is None \\
                and (merged[-1]["metal"] or _TONNAGE_WORD.search(merged[-1]["label"])):''',
     '''        # "Au Ounces" then "(koz)" is one column. Reading "Ounces" as the unit and "(koz)" as a
        # column of its own made an eighth column out of seven, and the mapping then ran a place
        # out -- RUA Gold's tonnage came back as its contained ounces.
        if _RE_BARE_UNIT.match(ln) and merged \\
                and (merged[-1]["unit"] is None or not merged[-1]["paren_unit"]) \\
                and (merged[-1]["metal"] or _TONNAGE_WORD.search(merged[-1]["label"])):'''),
    ('''    if len(usable) > n_values:
        return _one_tonnage(usable[-n_values:])
    return []''',
     '''    # A header with more columns than the row has values is a header this reader has not
    # understood. Taking the last n of them drops the leading columns silently, which is how
    # Fireweed's 6.3 Mt of ore came back as 94. Better to state no figures than the wrong ones.
    return []'''),
    ('''        if len(without) == n_values:
            return _one_tonnage(without)
        return _one_tonnage(usable[-n_values:])''',
     '''        if len(without) == n_values:
            return _one_tonnage(without)
        return []'''),
    ('''    t = re.sub(r"(?m)([A-Za-z])[ ]*\\n[ ]*(\\d)[ ]*\\n[ ]*([A-Z][a-z]?\\d?)(?=\\b)", r"\\1\\2\\3", t)
    t = re.sub(r"(?m)\\b([A-Z][a-z]?)[ ]*\\n[ ]*(\\d[A-Z][a-z]?\\d*)(?=\\b)", r"\\1\\2", t)''',
     '''    t = re.sub(r"([A-Za-z])\\s*\\n\\s*(\\d)\\s*\\n\\s*([A-Z][a-z]?\\d?)(?=\\b)", r"\\1\\2\\3", t)
    t = re.sub(r"\\b([A-Z][a-z]?)\\s*\\n\\s*(\\d[A-Z][a-z]?\\d*)(?=\\b)", r"\\1\\2", t)'''),
]


def main(argv):
    path = argv[0] if argv else "resources.py"
    s = open(path, encoding="utf-8").read()
    for i, (old, new) in enumerate(EDITS, 1):
        if s.count(old) != 1:
            print("edit %d: anchor appears %d times, expected 1" % (i, s.count(old)))
            return 1
        s = s.replace(old, new, 1)
    open(path, "w", encoding="utf-8").write(s)
    print("patched", path, len(EDITS), "edits, sha256",
          hashlib.sha256(s.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
