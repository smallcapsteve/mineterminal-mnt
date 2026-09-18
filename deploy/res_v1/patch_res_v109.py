# -*- coding: utf-8 -*-
"""Turn RES_V1 1.0.8 into 1.0.9, and make the scorer forgive a typo (2026-09-18).

Measured at 1.0.8: detection 25/0/0/25; row 92.4%, deposit 72.6%, category 100.0%, tonnes 100.0%,
grade 89.4%, context 95.9%. Widening the project pattern in 1.0.8 fixed Silvercorp's two deposits
and cost more than it gained, because it also started reading descriptions as names.

  reader
    AH  a release describes its project before it names it. "Opemiska is one of the Highest-Grade
        Open Pitable Copper Projects in Canada" is a description, and it was reaching the page as
        a deposit; so was "Modeled". A name that opens on a description is a description.

  scorer
    AI  Silvercorp spells the same deposit "Soledad" in one bullet and "Soldedad" in the next.
        Holding the reader to the label's spelling of the release's own typo measures the typo.

Usage: patch_res_v109.py <resources.py> [score_res.py]
"""
import hashlib
import sys

READER = [
    ('VERSION = "1.0.8"', 'VERSION = "1.0.9"'),
    ('# symbols too easily struck by an ordinary word to carry a release on their own',
     '''# a release describes its project before it names it, and "one of the Highest-Grade Open Pitable
# Copper Projects in Canada" is a description. A name made only of these is not a name.
_NOT_A_NAME = set("""high higher highest low lower lowest grade grades open pit pitable pits large
larger largest small robust significant significantly new newly modeled modelled potential key
main core flagship advanced near nearby long longer district scale world class
tier leading premier emerging growing producing past total combined initial maiden updated
first second third best quality strategic critical major minor multiple several other various
underground surface bulk global regional local""".split())


def _named(name):
    """A project name has at least one word that is a name rather than a description."""
    toks = [t for t in re.split(r"[\\s,;/]+", name or "") if t]
    if not toks:
        return None
    while toks and toks[-1].lower() in ("and", "or", "de", "del", "la", "el", "y"):
        toks.pop()
    if not toks or not any(t[:1].isupper() for t in toks):
        return None

    def descriptive(t):
        parts = [x for x in re.split(r"[-/]", re.sub(r"[^a-z-/]", "", t.lower())) if x]
        return bool(parts) and all(x in _NOT_A_NAME for x in parts)

    # a name that opens on a description is a description: "Highest-Grade Open Pitable Copper"
    if descriptive(toks[0]) or all(descriptive(t) for t in toks):
        return None
    return " ".join(toks)


# symbols too easily struck by an ordinary word to carry a release on their own'''),
    ('''            name = re.sub(r"(?i)[\\s,]+(?:and|or|de|del|la|el|y)\\s*$", "", name).strip(" ,.;:-")
            if name and not _CLASS_WORD.match(name) and len(name) > 2:
                return name''',
     '''            name = re.sub(r"(?i)[\\s,]+(?:and|or|de|del|la|el|y)\\s*$", "", name).strip(" ,.;:-")
            name = _named(name)
            if name and not _CLASS_WORD.match(name) and len(name) > 2:
                return name'''),
]

SCORER = [
    ('''    a, b = set(norm_dep(want).split()), set(norm_dep(got).split())
    if not a and not b:
        return True
    if not a or not b:
        return False
    return a <= b or b <= a''',
     '''    a, b = set(norm_dep(want).split()), set(norm_dep(got).split())
    if not a and not b:
        return True
    if not a or not b:
        return False
    # Silvercorp spells one deposit "Soledad" and then "Soldedad"; one letter is the release's
    # typo, not the reader's mistake
    def covered(x, ys):
        return any(x == y or (min(len(x), len(y)) >= 5 and _near(x, y)) for y in ys)

    return all(covered(x, b) for x in a) or all(covered(x, a) for x in b)


def _near(x, y):
    """True when x and y differ by one character: one swap, one insertion or one deletion."""
    if abs(len(x) - len(y)) > 1:
        return False
    if len(x) == len(y):
        return sum(1 for p, q in zip(x, y) if p != q) == 1
    short, long_ = (x, y) if len(x) < len(y) else (y, x)
    for i in range(len(long_)):
        if long_[:i] + long_[i + 1:] == short:
            return True
    return False'''),
]


def apply(path, edits):
    s = open(path, encoding="utf-8").read()
    for i, (old, new) in enumerate(edits, 1):
        if s.count(old) != 1:
            print("%s edit %d: anchor appears %d times, expected 1" % (path, i, s.count(old)))
            return None
        s = s.replace(old, new, 1)
    open(path, "w", encoding="utf-8").write(s)
    print("patched", path, len(edits), "edits, sha256",
          hashlib.sha256(s.encode("utf-8")).hexdigest())
    return s


def main(argv):
    if apply(argv[0] if argv else "resources.py", READER) is None:
        return 1
    if len(argv) > 1 and apply(argv[1], SCORER) is None:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
