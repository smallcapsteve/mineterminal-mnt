#!/usr/bin/env python3
"""RES_V1 1.0.16 -- a tonnage is ore or contained metal by what FOLLOWS the unit, not by the verb.

Found while writing the publisher's self-test, not by the labelled set: "Indicated Mineral Resources
TOTAL 6.3 million tonnes grading 1.85 g/t Au" published no tonnage at all, and then published the
6.3 million tonnes a second time as 6,300,000 tonnes of contained gold. "Resources OF 6.3 million
tonnes" was right all along, so the defect hid behind one preposition.

_RE_P_TONNES skipped any tonnage preceded by containing / contains / comprising / including /
includes / for / totalling / totaling / totals / of contained, on the grounds that such a figure is
contained metal. Half that list is unambiguous ("containing 67,000 tonnes of antimony"); the other
half -- for, total, totals, totalling, totaling -- is ordinary English for stating an ore tonnage.
What actually decides it is whether a metal follows the unit.

Usage:  patch_res_v116.py resources.py
"""
import hashlib
import re
import sys

OLD_VERSION = '''VERSION = "1.0.15"'''
NEW_VERSION = '''VERSION = "1.0.16"'''

OLD_RE = '''_RE_P_TONNES = re.compile(
    r"(?i)(?P<pre>\\b(?:containing|contains|comprising|including|includes|for|totalling|totaling|"
    r"totals?|of\\s+contained)\\b[^.]{0,24})?"
    r"\\b(?P<n>\\d[\\d,.]*)\\s*(?P<mult>million|billion|thousand)?\\s*"
    r"(?P<u>tonnes|tonne|tons|ton|mt|kt|t)\\b")'''

NEW_RE = '''# "totalling 67,000 tonnes of antimony" is contained metal; "Resources total 6.3 million tonnes"
# is ore. The verb does not decide it -- the word after the unit does (RES 1.0.16, 2026-09-18).
_RE_AFTER_TONNES = re.compile(r"(?i)^\\s*(?:of\\s+)?(?:contained\\s+)?(?P<m>[A-Za-z][A-Za-z0-9]{0,8})\\b")


def _tonnes_are_metal(after: str) -> bool:
    m = _RE_AFTER_TONNES.match(after or "")
    return bool(m and metal_of(m.group("m")))


_RE_P_TONNES = re.compile(
    r"(?i)(?P<pre>\\b(?:containing|contains|comprising|including|includes|of\\s+contained)\\b[^.]{0,24}"
    r"|(?P<soft>\\b(?:for|totalling|totaling|totals?)\\b[^.]{0,24}))?"
    r"\\b(?P<n>\\d[\\d,.]*)\\s*(?P<mult>million|billion|thousand)?\\s*"
    r"(?P<u>tonnes|tonne|tons|ton|mt|kt|t)\\b")'''

OLD_SKIP = '''    for m in _RE_P_TONNES.finditer(win):
        if m.group("pre"):
            continue'''

NEW_SKIP = '''    for m in _RE_P_TONNES.finditer(win):
        if m.group("pre") and not m.group("soft"):
            continue
        if m.group("soft") and _tonnes_are_metal(win[m.end("u"):m.end("u") + 24]):
            continue'''

OLD_CONT = '''            met, _eq = _metal_near(m.group("m"), win, m.start(), win[m.end():m.end() + 16])
            out["contained"].append({"metal": met, "value": v, "unit": base})'''

NEW_CONT = '''            # a tonne-unit figure is contained METAL only when a metal follows it. Without this
            # the ore tonnage is published twice: once as tonnes and once as tonnes of the metal
            # the release happens to be about, because _metal_near falls back to the nearest
            # metal BEFORE the figure when nothing follows it.
            if base == "t" and not _tonnes_are_metal(win[m.end("u"):m.end("u") + 24]):
                continue
            met, _eq = _metal_near(m.group("m"), win, m.start(), win[m.end():m.end() + 16])
            out["contained"].append({"metal": met, "value": v, "unit": base})'''


def main():
    if len(sys.argv) < 2:
        print("usage: patch_res_v116.py resources.py")
        return 2
    path = sys.argv[1]
    with open(path, encoding="utf-8") as fh:
        s = fh.read()
    for name, old, new in (("VERSION", OLD_VERSION, NEW_VERSION),
                           ("_RE_P_TONNES", OLD_RE, NEW_RE),
                           ("tonnage skip", OLD_SKIP, NEW_SKIP),
                           ("contained guard", OLD_CONT, NEW_CONT)):
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
