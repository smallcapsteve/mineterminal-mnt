# -*- coding: utf-8 -*-
"""Correct two deposit labels in the RES_V1 accuracy set (2026-09-18).

Both were mine, not the reader's, and both were flagged low-confidence and partial when the set
was drafted. Justin settled the rule on 2026-09-18: a row is named project, then zone, then
mining scenario in brackets.

  Greenland Mines (NEO.TO)  was "Sarfartoq ST1". The release models three scenarios -- open pit,
      underground and hybrid -- and the table these figures come from is the underground one. The
      project is Sarfartoq; "ST1" came from a prose mention, not from the table.

  Patriot (PMET.TO, both releases)  was "Shaakichiuwaanaan CV5" and "Shaakichiuwaanaan CV13/Vega".
      The release says the 108.0 Mt figure is the consolidated CV5 + CV13 estimate and the 0.69 Mt
      figure is the Rigel and Vega caesium zones. The first labels had the names crossed.

The set version goes to draft-2 so a measurement taken against it cannot be confused with one
taken against the first draft.

Usage: fix_labels_v2.py <make_labels.py>
"""
import hashlib
import sys

EDITS = [
    ('''    R("Sarfartoq ST1", "Indicated", 7475000, [{"metal": "TREO", "value": 1.56, "unit": "%"}]),
    R("Sarfartoq ST1", "Inferred", 2603000, [{"metal": "TREO", "value": 1.36, "unit": "%"}]),
    R("Sarfartoq ST1", "Total", 10078000, [{"metal": "TREO", "value": 1.51, "unit": "%"}]),
], "Update", "low", False,
    "three scenario tables (open pit, underground, hybrid); only one was read back, so the scenario on these rows is unconfirmed. Filed under NEO.TO but the company in the body is Nasdaq: GRML -- wrong-ticker attribution")''',
     '''    R("Sarfartoq (Underground Mining Scenario)", "Indicated", 7475000, [{"metal": "TREO", "value": 1.56, "unit": "%"}]),
    R("Sarfartoq (Underground Mining Scenario)", "Inferred", 2603000, [{"metal": "TREO", "value": 1.36, "unit": "%"}]),
    R("Sarfartoq (Underground Mining Scenario)", "Total", 10078000, [{"metal": "TREO", "value": 1.51, "unit": "%"}]),
], "Update", "low", False,
    "CORRECTED 2026-09-18: was labelled 'Sarfartoq ST1'. The release models three scenarios -- open pit, underground and hybrid -- and this is the underground one; the project is Sarfartoq and ST1 came from a prose mention rather than the table. Filed under NEO.TO but the company in the body is Nasdaq: GRML -- wrong-ticker attribution")'''),
    ('"version": "draft-1"', '"version": "draft-2"'),
    ('"Restated", "low", False, "feasibility-study filing; the resource is restated, not announced")',
     '"Restated", "low", False, "feasibility-study filing; the resource is restated, not announced. '
     'CORRECTED 2026-09-18: the 108.0 Mt figure is the consolidated CV5 + CV13 estimate and the 0.69 Mt '
     'figure is the Rigel and Vega caesium zones -- the release says so and the first labels did not")'),
    ('"Restated", "high", False, "technical report filing on the resource estimate itself, so the figures are the subject of the release")',
     '"Restated", "high", False, "technical report filing on the resource estimate itself, so the figures '
     'are the subject of the release. CORRECTED 2026-09-18: same two deposit names as the November release")'),
]

RENAMES = [
    ('    R("Shaakichiuwaanaan CV5", "Indicated", 108000000',
     '    R("Shaakichiuwaanaan CV5 + CV13", "Indicated", 108000000'),
    ('    R("Shaakichiuwaanaan CV5", "Inferred", 33400000',
     '    R("Shaakichiuwaanaan CV5 + CV13", "Inferred", 33400000'),
    ('    R("Shaakichiuwaanaan CV13/Vega", "Indicated", 690000',
     '    R("Shaakichiuwaanaan - Rigel and Vega", "Indicated", 690000'),
    ('    R("Shaakichiuwaanaan CV13/Vega", "Inferred", 1700000',
     '    R("Shaakichiuwaanaan - Rigel and Vega", "Inferred", 1700000'),
]


def main(argv):
    path = argv[0] if argv else "make_labels.py"
    s = open(path, encoding="utf-8").read()
    for i, (old, new) in enumerate(EDITS, 1):
        if s.count(old) != 1:
            print("edit %d: anchor appears %d times, expected 1" % (i, s.count(old)))
            return 1
        s = s.replace(old, new, 1)
    for old, new in RENAMES:          # the same two names appear in both Patriot releases
        if not s.count(old):
            print("rename anchor missing:", old[:48])
            return 1
        s = s.replace(old, new)
    open(path, "w", encoding="utf-8").write(s)
    print("corrected", path, "sha256", hashlib.sha256(s.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
