#!/usr/bin/env python3
"""RES_V1 1.0.18 -- a positional mapping that cannot be right, and a clause that is not a place.

TWO FIXES, both found by reading what 1.0.17 actually published rather than by measuring the
50-release set, which contains neither shape.

1. THE COLUMN MAPPING CAN BE SILENTLY OUT BY ONE

   Class 1 Nickel's table is Tonnage | Ni % | Cu % | Co % | NiEq % | NSR C$/t | Ni klbs | Cu klbs |
   Co klbs -- nine value columns. `build_columns` keeps only the columns whose unit it can parse,
   and it cannot parse "NSR" / "(C$/t)", so it drops them and returns EIGHT columns. The data row
   also has eight values, because one cell is blank. Eight equals eight, so the mapping is accepted
   and every value from the dropped column onward lands one place out:

       published            truth
       Co    0.44 %         Co    0.02 %
       NiEq  88   %         NiEq  0.44 %
                            NSR   88   C$/t

   and on another row the contained nickel and copper swapped, so 390 kt at 0.57% Ni was published
   as 120 klb of nickel when 390,000 x 0.57% is 4,900 klb. A third row put a 2,710,000 t tonnage in
   a grade column and published 2,710,000% Ni.

   The real repair is for an unparseable column to hold its position instead of vanishing, so the
   count no longer matches by coincidence -- but that is surgery on the mapper that sixteen versions
   went into stabilising, and it wants the whole table corpus as evidence. What goes in here is the
   check that needs no such evidence, because the release states enough to catch the error itself:

       no ore is 100% metal
       contained metal is tonnage x grade

   When either says the mapping is wrong, the row states no figures rather than wrong ones. That is
   this reader's rule everywhere else -- "Better to state no figures than the wrong ones", from the
   comment that refuses a header with more columns than the row has values.

   The arithmetic check runs on the metals where the release gives both halves, within a factor of
   three, which is wide enough for contained metal quoted after recovery and for rounding, and far
   inside the 40x error it is there to catch.

2. A CLAUSE IS NOT A PLACE

   Ten deposit names on the page are fragments of sentences -- five from the row-line path, three
   from prose, two from tables, so it is not one path's bug but the absence of a shared test:

       Accompany the Hollinger MRE" for additional information
       Consulting (Canada) Inc., effective July 31, 2026
       - The pit shell selected as the limit has a revenue factor of 1.00
       Acquire the Mirado - North Zone and South
       The Banio Potash Project Updated has an
       position of the Shaakichiuwaanaan
       tonnes in Alexo North / tonnes in Alexo South
       Reported at the Expanded Silicon Project1
       Guillermina Deposit (effective March 31, 2025)

   `qualify()` is the one place every row's deposit passes through, so the test goes there. A name
   that opens on a verb, opens on a lower-case word that is not a name particle, carries a finite
   verb, carries company or qualified-person vocabulary, opens on a bullet or has an unbalanced
   quote is a clause; the row falls back to the project name, which is what the ninety-eight rows
   with no deposit at all already do and which the page already renders.

   The last one is not a clause, only a name wearing a date, so an "effective <date>" tail is
   stripped rather than the whole name rejected.

Usage:  patch_res_v118.py resources.py
"""
import hashlib
import sys

OLD_VERSION = '''VERSION = "1.0.17"'''
NEW_VERSION = '''VERSION = "1.0.18"'''

OLD_FILL_HEAD = '''def _fill(row, cols, vals):'''

NEW_FILL_HEAD = '''_LB_PER_T = 2204.62262


def _checked(row):
    """Refuse a positional mapping the release itself contradicts (RES 1.0.18, 2026-09-18).

    `build_columns` keeps only the header columns whose unit it can parse, so a column it does not
    understand -- Class 1 Nickel's "NSR (C$/t)", sitting between the grade group and the contained
    group -- vanishes instead of holding its place. The column count can then match the value count
    by coincidence and every value after the gap lands one place out. Two things the release states
    catch it: no ore is 100% metal, and contained metal is tonnage times grade."""
    if any(g["unit"] == "%" and (g["value"] or 0) >= 100 for g in row["grades"]):
        row["tonnes"], row["grades"], row["contained"] = None, [], []
        row["confidence"] = "low"
        return row
    t, grades = row["tonnes"], {}
    for g in row["grades"]:
        if g["metal"] and g["value"]:
            grades.setdefault(g["metal"], (g["value"], g["unit"]))
    worst = 1.0
    if t:
        for c in row["contained"]:
            got, want = c.get("value"), None
            g = grades.get(c.get("metal"))
            if not got or not g:
                continue
            if g[1] == "%" and c["unit"] in ("t", "lb"):
                want = t * g[0] / 100.0 * (_LB_PER_T if c["unit"] == "lb" else 1.0)
            elif g[1] == "g/t" and c["unit"] == "oz":
                want = t * g[0] / 31.1034768
            if want:
                r = got / want
                worst = max(worst, r, 1.0 / r)
    # Within 3x is agreement: contained metal is often quoted after recovery, and the grade is
    # rounded. Beyond 20x nothing about ore explains it and the positional mapping is simply out,
    # so the row states no figures -- including the grades, because a shifted block shifts them
    # too: Class 1 Nickel's 0.44% cobalt is really its nickel-equivalent, and the 88% beside it is
    # a C$/t net smelter return. In between, only the contained block is condemned.
    if worst > 20.0:
        row["tonnes"], row["grades"], row["contained"] = None, [], []
        row["confidence"] = "low"
    elif worst > 3.0:
        row["contained"] = []
        row["confidence"] = "low"
    return row


def _fill(row, cols, vals):'''

OLD_FILL_TAIL = '''        elif c["kind"] == "cutoff" and row["cut_off"] is None:
            row["cut_off"] = ("%g" % v) + (c["unit"] or "")
    return row'''

NEW_FILL_TAIL = '''        elif c["kind"] == "cutoff" and row["cut_off"] is None:
            row["cut_off"] = ("%g" % v) + (c["unit"] or "")
    return _checked(row)'''

OLD_QUALIFY = '''    deposit under two mining assumptions have to be recognisable as the same rock."""
    if not deposit or not project:
        return deposit'''

NEW_QUALIFY = '''    deposit under two mining assumptions have to be recognisable as the same rock."""
    deposit = _place(deposit)
    if not deposit or not project:
        return deposit'''

OLD_NAMED = '''def _named(name):'''

NEW_NAMED = '''# A deposit has a name. These say the candidate is a piece of a sentence instead: a verb it opens
# on, a finite verb inside it, the vocabulary of a qualified person or a company, a bullet, or a
# quote that never closes. Ten such fragments reached the page at 1.0.17, through all three of the
# paths that produce a deposit, which is why the test lives in qualify() where they all meet.
_RE_CLAUSE_VERB = re.compile(r"(?i)^(?:accompany|acquire|acquires|announce[sd]?|based|comprise[sd]?|"
                             r"contain[sd]?|filed|includ(?:e|es|ing)|locat(?:e|ed)|please|prepared|"
                             r"present(?:s|ed)?|provide[sd]?|pursuant|refer|report(?:s|ed)?|represent[sd]?|"
                             r"review|see|us(?:e|ed|ing))\\b")
_RE_CLAUSE_IN = re.compile(r"(?i)\\b(?:has\\s+an?|have\\s+an?|is\\s+the|are\\s+in|was\\s+the|were\\s+in|"
                           r"selected\\s+as|for\\s+additional|pursuant\\s+to|refer\\s+to|"
                           r"in\\s+accordance|revenue\\s+factor|per\\s+recovered)\\b")
_RE_CLAUSE_CORP = re.compile(r"(?i)(?:\\bInc\\b|\\bLtd\\b|\\bLLC\\b|\\bLLP\\b|\\bPLC\\b|\\bCorp\\b|"
                             r"\\bConsulting\\b|\\bConsultants\\b|qualified\\s+person)")
_RE_EFFECTIVE = re.compile(r"(?i)[\\s,(-]*\\beffective\\b[^)]*\\)?\\s*$")
_NAME_PARTICLE = {"la", "le", "el", "de", "del", "da", "do", "du", "von", "van", "der", "den"}


def _place(name):
    """The name of a place, or None when the candidate is a piece of a sentence."""
    if not name:
        return name
    # "Guillermina Deposit (effective March 31, 2025)" is a name wearing a date, not a clause
    # NOT "()" in the strip set: that ate the closing bracket off every scenario-qualified name,
    # turning "Opemiska (Pit Constrained)" into "Opemiska (Pit Constrained". _RE_EFFECTIVE already
    # consumes its own opening bracket.
    s = _RE_EFFECTIVE.sub("", name).strip(" ,.;:-")
    if not s:
        return None
    if s[0] in "\\u2022\\u00b7*-\\u2013\\u2014" or s.count('"') % 2 or s.count("\\u201d") != s.count("\\u201c"):
        return None
    if _RE_CLAUSE_VERB.match(s) or _RE_CLAUSE_IN.search(s) or _RE_CLAUSE_CORP.search(s):
        return None
    first = re.split(r"[\\s,;/]+", s)[0]
    if first[:1].islower() and first.lower() not in _NAME_PARTICLE:
        return None
    return s


def _named(name):'''


def main():
    if len(sys.argv) < 2:
        print("usage: patch_res_v118.py resources.py")
        return 2
    path = sys.argv[1]
    with open(path, encoding="utf-8") as fh:
        s = fh.read()
    for name, old, new in (("VERSION", OLD_VERSION, NEW_VERSION),
                           ("_checked", OLD_FILL_HEAD, NEW_FILL_HEAD),
                           ("_fill returns checked", OLD_FILL_TAIL, NEW_FILL_TAIL),
                           ("_place", OLD_NAMED, NEW_NAMED),
                           ("qualify", OLD_QUALIFY, NEW_QUALIFY)):
        n = s.count(old)
        if n != 1:
            print("FAIL %s: anchor found %d times, expected 1" % (name, n))
            return 1
        s = s.replace(old, new)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(s)
    print("patched %s -> sha256 %s" % (path, hashlib.sha256(s.encode("utf-8")).hexdigest()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
