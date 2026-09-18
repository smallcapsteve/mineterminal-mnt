#!/usr/bin/env python3
"""Turn RES_V1 1.0.5 into 1.0.6 (2026-09-18).

Measured at 1.0.5: detection 25/0/0/25; row 88.9%, deposit 81.9%, category 100.0%, tonnes 92.9%,
grade 76.1%, context 93.1%.

  T  an oxide whose subscript was lost at ingestion is still an oxide. Imagine Lithium's body has
     "0.85% Li" on one line and "O in the Indicated category" on the next, and a grade of lithium
     metal is not a grade of lithium oxide.
  U  "... for 128,000 indicated tonnes of LCE" labels the tonnes; the estimate is in the clause in
     front of it. Reading forward from the category took Cruz's 103 Mt inferred figure and filed
     it as the indicated one.
  V  Military Metals' headline carries the grades and no tonnage and its table carries both. That
     is one row, not two.
  W  a deposit has a name. "new" -- what was left of a sentence after the boilerplate came out --
     was reaching the page as one.
  X  "at a 500 ppm cut-off grade" states the cut-off, not the grade. The phrase has to follow the
     figure directly, with no other number and no clause break in between, or the Au grade in
     "1.06 g/t Au, estimated at a break-even cut-off grade of 0.8% SbEq" goes with it too.

Usage: patch_res_v106.py <resources.py>
"""
import hashlib
import sys

EDITS = [
    ('VERSION = "1.0.5"', 'VERSION = "1.0.6"'),
    ('_EQ_SUFFIX = re.compile(',
     '''# the oxide each element is reported as, for bodies that lost the subscript
_OXIDE = {"Li": "Li2O", "Cs": "Cs2O", "Ta": "Ta2O5", "Nb": "Nb2O5", "V": "V2O5", "U": "U3O8",
          "P": "P2O5", "Ti": "TiO2", "Sc": "Sc2O3", "Cr": "Cr2O3", "Nd": "Nd2O3", "Pr": "Pr6O11",
          "Dy": "Dy2O3", "Tb": "Tb4O7", "W": "WO3", "Sn": "SnO2", "Mo": "MoO3", "Be": "BeO",
          "Zr": "ZrO2", "Al": "Al2O3", "Si": "SiO2", "Fe": "Fe2O3", "Mn": "MnO"}
_EQ_SUFFIX = re.compile('''),
    ('''    t = re.sub(r"([A-Za-z])\\s*\\n\\s*(\\d)\\s*\\n\\s*([A-Z][a-z]?\\d?)(?=\\b)", r"\\1\\2\\3", t)
    t = re.sub(r"\\b([A-Z][a-z]?)\\s*\\n\\s*(\\d[A-Z][a-z]?\\d*)(?=\\b)", r"\\1\\2", t)''',
     '''    t = re.sub(r"([A-Za-z])\\s*\\n\\s*(\\d)\\s*\\n\\s*([A-Z][a-z]?\\d?)(?=\\b)", r"\\1\\2\\3", t)
    t = re.sub(r"\\b([A-Z][a-z]?)\\s*\\n\\s*(\\d[A-Z][a-z]?\\d*)(?=\\b)", r"\\1\\2", t)
    # Imagine Lithium's body lost the subscript altogether and left "0.85% Li" on one line and
    # "O in the Indicated category" on the next. A grade of lithium metal and a grade of lithium
    # oxide are different numbers, so the element is restored to the oxide the industry reports.
    t = re.sub(r"\\b([A-Z][a-z]?)\\s*\\n\\s*\\d?O\\d?(?=\\b)",
               lambda m: _OXIDE.get(m.group(1), m.group(1)), t)'''),
    ('''_RE_TRAILING = re.compile(r"(?i)^\\s*(?:[,;.)]|and\\b|category\\b|classification\\b|$)")''',
     '''# "... for 128,000 indicated tonnes of LCE" labels the tonnes; the estimate is in front of it
_RE_TRAILING = re.compile(r"(?i)^\\s*(?:[,;.)]|and\\b|category\\b|classification\\b|"
                          r"tonnes?\\b|ounces\\b|oz\\b|pounds\\b|lbs?\\b|t\\b|$)")'''),
    ('''    for m in _RE_P_GRADE.finditer(win):
        v = _num(m.group("n"))
        if v is None:
            continue''',
     '''    for m in _RE_P_GRADE.finditer(win):
        v = _num(m.group("n"))
        if v is None:
            continue
        # "at a 500 ppm cut-off grade" states the cut-off, not the grade of the resource. The
        # phrase has to be the next thing after the figure, with no other number in between, or
        # every grade in "697 ppm Li at a 500 ppm cut-off" would go with it.
        after = win[m.end("u"):m.end("u") + 30]
        mm = re.search(r"(?i)cut[\\s-]?off|\\bcog\\b", after)
        if (mm and not re.search(r"[\\d,;]", after[:mm.start()])) \\
                or _RE_CUTOFF.search(win[max(0, m.start() - 22):m.start()]):
            continue'''),
    ('''def _same_figures(a, b):
    # a headline that names a category but no figure is the same row as the table that has them
    if _figureless(a) or _figureless(b):
        return True''',
     '''def _same_figures(a, b):
    # a headline that names a category but no figure is the same row as the table that has them
    if _figureless(a) or _figureless(b):
        return True
    # Military Metals' headline carries the grades and no tonnage; the table carries both. One row.
    if (a["tonnes"] is None) != (b["tonnes"] is None):
        pairs_a = {(g["metal"], g["value"]) for g in a["grades"]}
        pairs_b = {(g["metal"], g["value"]) for g in b["grades"]}
        if pairs_a & pairs_b:
            return True'''),
    ('''    unitish = sum(1 for t in toks
                  if _RE_BARE_UNIT.match(t.strip(".,")) or t.strip(".,").isdigit())
    if unitish * 2 >= len(toks):
        return None''',
     '''    unitish = sum(1 for t in toks
                  if _RE_BARE_UNIT.match(t.strip(".,")) or t.strip(".,").isdigit())
    if unitish * 2 >= len(toks):
        return None
    # a deposit has a name: "new" is what was left of a sentence, not a place
    if not any(t[:1].isupper() for t in toks):
        return None'''),
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
