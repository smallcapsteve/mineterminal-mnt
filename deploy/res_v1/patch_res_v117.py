#!/usr/bin/env python3
"""RES_V1 1.0.17 -- a percentage after a figure can be a change or a share, not only a grade.

Found by auditing the 1,098 rows RES_V1 1.0.16 actually published, which is a thing worth doing
every time: 41 of the 973 rows carrying a grade held a percentage no ore can have. Class 1 Nickel
writes every highlight the same way --

    "Inferred Resources (open pit and underground) of 125 kt at 0.54% Ni (1.5M lbs Ni)
     -- 693% increase in Inferred tonnes and 419% increase in nickel pounds."

-- so the row came out with TWO nickel grades: the correct 0.54%, and 693%. Elsewhere the same
sentence shape produced 781% Ni and one row at 2,710,000% Ni.

`_RE_DELTA` already knows a change is not a level, but it looks for the delta word BEFORE the
figure ("increased by 2.57 million tonnes"). In this construction the figure comes first and the
noun follows it, so nothing was looking there. Two guards, both in the grade loop, both next to the
cut-off guard that solves the same class of problem in the same place:

  1. a percentage immediately followed by increase / decrease / growth / reduction and friends is
     a change, not a grade
  2. no ore is 100% metal, so a percentage at or above 100 is a share, a recovery or a change
     whatever follows it -- the second guard catches what the first one's vocabulary misses

Usage:  patch_res_v117.py resources.py
"""
import hashlib
import re
import sys

OLD_VERSION = '''VERSION = "1.0.16"'''
NEW_VERSION = '''VERSION = "1.0.17"'''

OLD_DELTA = '''# "increased by 2.57 million tonnes of ore" states a change, not a level
_RE_DELTA = re.compile(r"(?i)\\b(increas\\w+\\s+by|decreas\\w+\\s+by|grew\\s+by|fell\\s+by|"
                       r"year[\\s-]on[\\s-]year|net\\s+of|depletion|compared\\s+(?:to|with)|"
                       r"versus|up\\s+from|down\\s+from|addition\\s+of)\\b")'''

NEW_DELTA = '''# "increased by 2.57 million tonnes of ore" states a change, not a level
_RE_DELTA = re.compile(r"(?i)\\b(increas\\w+\\s+by|decreas\\w+\\s+by|grew\\s+by|fell\\s+by|"
                       r"year[\\s-]on[\\s-]year|net\\s+of|depletion|compared\\s+(?:to|with)|"
                       r"versus|up\\s+from|down\\s+from|addition\\s+of)\\b")
# A percentage is only a grade when nothing after it says otherwise. Two families sit right after
# the figure, where _RE_DELTA never looked because it reads the words BEFORE one:
#   a change  -- "693% increase in Inferred tonnes", how Class 1 Nickel writes every highlight
#   a share   -- "99.5% recovery", "63% of the contained metal", a recovery or a proportion
# The match is anchored at the character after the unit, so a real grade is never caught: in
# "1.02% Ni of the Indicated category" the metal sits in between (RES 1.0.17, 2026-09-18).
_RE_DELTA_AFTER = re.compile(r"(?i)^\\s*(?:increase|decrease|growth|reduction|gain|decline|drop|"
                             r"rise|fall|improvement|uplift|higher|lower|greater|more|less|"
                             r"above|below|recovery|recoveries|recovered|recovery\\s+rate|"
                             r"dilution|payable|of\\s+the|of\\s+total|of\\s+all)\\b")'''

OLD_GUARD = '''        after = win[m.end("u"):m.end("u") + 30]
        mm = re.search(r"(?i)cut[\\s-]?off|\\bcog\\b", after)
        if (mm and not re.search(r"[\\d,;]", after[:mm.start()])) \\
                or _RE_CUTOFF.search(win[max(0, m.start() - 22):m.start()]):
            continue'''

NEW_GUARD = '''        after = win[m.end("u"):m.end("u") + 30]
        mm = re.search(r"(?i)cut[\\s-]?off|\\bcog\\b", after)
        if (mm and not re.search(r"[\\d,;]", after[:mm.start()])) \\
                or _RE_CUTOFF.search(win[max(0, m.start() - 22):m.start()]):
            continue
        # "693% increase in Inferred tonnes" is a change, not a grade
        if _RE_DELTA_AFTER.match(after):
            continue
        # no ore is 100% metal: a percentage that high is a share, a recovery or a change,
        # whatever word follows it
        if "%" in (m.group("u") or "") and v >= 100:
            continue'''


def main():
    if len(sys.argv) < 2:
        print("usage: patch_res_v117.py resources.py")
        return 2
    path = sys.argv[1]
    with open(path, encoding="utf-8") as fh:
        s = fh.read()
    for name, old, new in (("VERSION", OLD_VERSION, NEW_VERSION),
                           ("_RE_DELTA_AFTER", OLD_DELTA, NEW_DELTA),
                           ("grade guards", OLD_GUARD, NEW_GUARD)):
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
