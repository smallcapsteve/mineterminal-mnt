# -*- coding: utf-8 -*-
"""Turn RES_V1 1.0.13 into 1.0.14 (2026-09-18).

Measured at 1.0.13: row 92.4%, deposit 88.7%, category 100.0%, tonnes 100.0%, grade 95.5%,
context 95.9%. Deposit was one row short of the gate and four of the eight misses were one thing.

  AR  "Pit 1" and "Zone 2" are names. The numeral on the end was being read two ways at once --
      as a figure by the units test and as a footnote marker by the trailing-digit strip -- so
      both of McFarlane Lake's pits were rejected and their rows stayed under the block heading
      above them. A numeral now stays when it numbers a block and goes when it marks a footnote
      ("Auld 3").

Usage: patch_res_v114.py <resources.py>
"""
import hashlib
import sys

EDITS = [
    ('VERSION = "1.0.13"', 'VERSION = "1.0.14"'),
    ('    s = re.sub(r"\\s+\\d\\s*$", "", s)',
     '''    # a trailing digit is a footnote marker ("Auld 3") unless it numbers a block ("Pit 1")
    if not re.search(r"(?i)\\b(pit|zone|block|area|lens|stage|phase|target|domain|pushback|"
                     r"panel|level|shoot)\\s+\\d{1,3}\\s*$", s):
        s = re.sub(r"\\s+\\d\\s*$", "", s)'''),
    ('''    unitish = sum(1 for t in toks
                  if _RE_BARE_UNIT.match(t.strip(".,")) or re.fullmatch(r"[\\d.,]+", t))''',
     '''    # "Pit 1" and "Zone 2" are names; the numeral on the end of a name is part of the name, and
    # counting it as a figure rejected McFarlane Lake's two pits and left both rows under the
    # block heading above them.
    numbered = len(toks) >= 2 and re.fullmatch(r"\\d{1,3}", toks[-1])
    body = toks[:-1] if numbered else toks
    unitish = sum(1 for t in body
                  if _RE_BARE_UNIT.match(t.strip(".,")) or re.fullmatch(r"[\\d.,]+", t))
    toks = body or toks'''),
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
