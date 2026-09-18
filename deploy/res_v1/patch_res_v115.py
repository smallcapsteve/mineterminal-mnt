# -*- coding: utf-8 -*-
"""Turn RES_V1 1.0.14 into 1.0.15, and stop the scorer counting prepositions (2026-09-18).

Measured at 1.0.14: row 92.4%, deposit 88.7%, category 100.0%, tonnes 100.0%, grade 95.5%,
context 95.9%. Six deposit misses left, and they are two things.

  reader
    AS  "Pit 1" is a block heading, not a column label. Both its words are header vocabulary, so
        1.0.14's fix to the name test never got a chance -- the line was filed with the header run
        and McFarlane Lake's two pits never became deposits at all.

  scorer
    AT  "East Bull in-pit" against "EAST BULL PALLADIUM (Pit Constrained)" failed on the word
        "in". One- and two-letter tokens are prepositions, not names, and holding a deposit name
        to them measures grammar.

Usage: patch_res_v115.py <resources.py> [score_res.py]
"""
import hashlib
import sys

READER = [
    ('VERSION = "1.0.14"', 'VERSION = "1.0.15"'),
    ('def _is_header_material(ln: str) -> bool:',
     '''_RE_NUMBERED_BLOCK = re.compile(r"(?i)^\\s*(?:pit|zone|block|area|lens|stage|phase|target|domain|"
                                r"pushback|panel|level|shoot)\\s+\\d{1,3}\\s*$")


def _is_header_material(ln: str) -> bool:'''),
    ('''    if not ln or len(ln) > 60:
        return False
    if _CLASS_WORD.match(ln) or _RE_BARE_UNIT.match(ln):
        return True''',
     '''    if not ln or len(ln) > 60:
        return False
    # "Pit 1" is a block heading, not a column label. Both its words are header vocabulary, so
    # the line was being filed with the header run and McFarlane Lake's two pits never became
    # deposits at all.
    if _RE_NUMBERED_BLOCK.match(ln):
        return False
    if _CLASS_WORD.match(ln) or _RE_BARE_UNIT.match(ln):
        return True'''),
]

SCORER = [
    ('''    s = _DEP_NOISE.sub(" ", s)
    s = re.sub(r"[^\\w\\s]", " ", s)
    return re.sub(r"\\s+", " ", s).strip().lower()''',
     '''    s = _DEP_NOISE.sub(" ", s)
    s = re.sub(r"[^\\w\\s]", " ", s)
    # one- and two-letter tokens are prepositions, not names: "East Bull in-pit" against
    # "EAST BULL PALLADIUM (Pit Constrained)" was failing on the word "in"
    toks = [t for t in re.sub(r"\\s+", " ", s).strip().lower().split() if len(t) > 2 or t.isdigit()]
    return " ".join(toks)'''),
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
