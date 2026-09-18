#!/usr/bin/env python3
"""Turn RES_V1 1.0.1 into 1.0.2, and fix one thing in the scorer (2026-09-18).

Measured at 1.0.1 on the 50-release set: detection 25 right, 0 missed, 1 spurious; row 85.9%,
deposit 86.1%, category 100.0%, tonnes 80.5%, grade 71.6%, context 86.1%.

  reader
    B  a headline that names a category but no figure was kept as a second row beside the table
       that had the figures, and then marked an alternative cut-off
    C  "alternative cut-off" now needs the cut-offs to actually differ. Silvercorp's two deposits
       both came back as "Condor", and the second was marked an alternative of the first -- a
       wrong mark on a row whose only fault was being under-named
    D  a filing release always says "report dated", so that phrase cannot mean background; it put
       1911 Gold's own updated estimate in background
    E  "the Inferred resource increased by 2.57 million tonnes" states a change, not a level, and
       was being published as a resource
    F  a row needs a category and at least one figure. A drill-depth table produced a bare "Total"
       row with nothing in it.
    G  a wrapped line can be shorter than 55 characters: Imagine Lithium's "0.85% Li" and its "2O"
       sat on either side of a 55-character break, so the grade read as Li rather than Li2O

  scorer
    H  pairing a predicted row to a labelled one weighted the deposit name as heavily as the
       tonnage, so two zones of one project with the same category paired at random

Usage: patch_res_v102.py <resources.py> [score_res.py]
"""
import hashlib
import sys

READER = [
    ('VERSION = "1.0.1"', 'VERSION = "1.0.2"'),
    ('''def _same_figures(a, b):
    if a["tonnes"] and b["tonnes"]:''',
     '''def _figureless(r):
    return r["tonnes"] is None and not r["grades"] and not r["contained"]


def _same_figures(a, b):
    # a headline that names a category but no figure is the same row as the table that has them
    if _figureless(a) or _figureless(b):
        return True
    if a["tonnes"] and b["tonnes"]:'''),
    ('''        # the figure the release states in prose is the base case; the rest are other cut-offs
        base = next((r for r in kept if r["source"] in ("prose", "headline")), kept[0] if kept else None)
        for r in kept:
            if r is not base and r["context"] == "announced":
                r["context"] = "alternative cut-off"''',
     '''        # The figure the release states in prose is the base case. A second figure for the same
        # deposit and category is only an alternative cut-off when the cut-off actually differs;
        # otherwise it is a deposit this reader failed to tell apart, and calling it an
        # alternative would put a wrong mark on a row that is simply under-named.
        base = next((r for r in kept if r["source"] in ("prose", "headline")), kept[0] if kept else None)
        for r in kept:
            if r is base or r["context"] != "announced":
                continue
            if base is not None and r["cut_off"] and base["cut_off"] and r["cut_off"] != base["cut_off"]:
                r["context"] = "alternative cut-off"'''),
    ('''    r"inventory\\b|portfolio\\s+of\\s+projects|across\\s+its\\s+projects|"
    r"announcement\\s+dated|report\\s+dated|estimate\\s+dated|in\\s+accordance\\s+with\\s+ni\\s*43\\s*-?\\s*101\\s*,?\\s*dated)\\b")''',
     '''    r"inventory\\b|portfolio\\s+of\\s+projects|across\\s+its\\s+projects)\\b")'''),
    ('_RE_CONTAINED_MARK = re.compile(',
     '''# "increased by 2.57 million tonnes of ore" states a change, not a level
_RE_DELTA = re.compile(r"(?i)\\b(increas\\w+\\s+by|decreas\\w+\\s+by|grew\\s+by|fell\\s+by|"
                       r"year[\\s-]on[\\s-]year|net\\s+of|depletion|compared\\s+(?:to|with)|"
                       r"versus|up\\s+from|down\\s+from|addition\\s+of)\\b")
_RE_CONTAINED_MARK = re.compile('''),
    ('''            if len(part) < 20 or len(part) > 460 or not _RE_RES_WORD.search(part):
                continue''',
     '''            if len(part) < 20 or len(part) > 460 or not _RE_RES_WORD.search(part):
                continue
            if _RE_DELTA.search(part):
                continue'''),
    ('    rows = _dedupe(rows)[:MAX_ROWS]',
     '''    rows = [r for r in rows if not _figureless(r)]
    rows = _dedupe(rows)[:MAX_ROWS]'''),
    ('def reflow(text: str, min_len: int = 55) -> str:',
     'def reflow(text: str, min_len: int = 45) -> str:'),
]

SCORER = [
    ('''            if dep_ok(lab["deposit"], p["deposit"]):
                score += 2
            if lab["tonnes"] and close(p["tonnes"], lab["tonnes"]):
                score += 2''',
     '''            if dep_ok(lab["deposit"], p["deposit"]):
                score += 2
            # the tonnage identifies a row more reliably than its deposit name does
            if lab["tonnes"] and close(p["tonnes"], lab["tonnes"]):
                score += 3'''),
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
