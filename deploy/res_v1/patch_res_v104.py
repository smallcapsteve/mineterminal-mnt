#!/usr/bin/env python3
"""Turn RES_V1 1.0.3 into 1.0.4 (2026-09-18).

Measured at 1.0.3: detection 25/0/0/25; row 88.8%, deposit 83.5%, category 100.0%, tonnes 83.1%,
grade 66.2%, context 93.7%.

  M  a table's columns did not survive the end of that table. Fireweed prints eleven tables with
     paragraphs between them, and the first table's meanings were still being applied to the
     fourth -- 6.3 Mt of ore read as 94.
  N  a table caption is not a deposit name until its leading connectives are stripped: "Summary
     of maiden Mineral Resource Estimate for the Regnault gold deposit" was reaching the page as
     "maiden for the Regnault gold deposit".
  O  1.0.3 widened project detection too far and "in Canada" became a project. The prepositions
     are back to the narrow set; what 1.0.3 added and keeps is "The Wapolu Gold Project has ...",
     a project named with no preposition in front of it.
  P  one metal in the headline names the columns the table did not label. A gold company's table
     often labels its grade column "Grade (g/t)" and nothing else, and a grade with no metal
     against it is a figure a reader cannot use. Only applied where the release names exactly one
     metal, so a polymetallic release is never guessed at.

Usage: patch_res_v104.py <resources.py>
"""
import hashlib
import sys

EDITS = [
    ('VERSION = "1.0.3"', 'VERSION = "1.0.4"'),
    ('''        if _RE_STOP.match(ln) or (len(ln) > 90 and not _is_header_material(ln)):
            header, deposit, dep_cut, dep_basis, dirty = [], None, None, None, False''',
     '''        if _RE_STOP.match(ln) or (len(ln) > 90 and not _is_header_material(ln)):
            # Fireweed prints eleven tables with paragraphs between them. Once a table has ended,
            # its columns are gone: carrying them to the next table read 6.3 Mt of ore as 94.
            header, deposit, dep_cut, dep_basis, dirty = [], None, None, None, False
            last_cols, last_n = [], 0'''),
    ('''    if s.count("(") != s.count(")"):
        return None''',
     '''    if s.count("(") != s.count(")"):
        return None
    # "Summary of maiden Mineral Resource Estimate for the Regnault gold deposit" leaves
    # "maiden for the Regnault gold deposit" once the boilerplate is out; the name starts where
    # the lower-case connectives stop.
    while True:
        m = re.match(r"^([a-z][\\w'-]*)\\s+(?=\\S)", s)
        if not m:
            break
        s = s[m.end():]
    s = s.strip(" ,.;:-")
    if len(s) < 2 or len(s) > 70:
        return None'''),
    ('''    r"(?i)(?:^|\\b)(?:at|for|on|of|to|in|the|its|their|our|company's)\\s+"
    r"(?:its|the|their|our|100%[\\s-]?owned|wholly[\\s-]?owned)?\\s*"''',
     '''    r"(?i)(?:^|\\b)(?:at|for|on|of|to|the|its|their|our)\\s+"
    r"(?:its|the|their|our|100%[\\s-]?owned|wholly[\\s-]?owned)?\\s*"'''),
    ('def release_announces(headline: str, body_head: str = "") -> bool:',
     '''def release_metal(headline: str, body_head: str = "") -> str | None:
    """The metal a release is about, when it is about exactly one.

    A gold company's table often labels its grade column "Grade (g/t)" and nothing else, and a
    grade with no metal against it is a figure a reader cannot use. Where the headline names one
    metal and only one, that is the metal."""
    found = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9]{0,8}", (headline or "") + " " + (body_head or "")[:300]):
        got = metal_of(w)
        if got and not got[1]:
            found.add(got[0])
    return next(iter(found)) if len(found) == 1 else None


def release_announces(headline: str, body_head: str = "") -> bool:'''),
    ('''    doc_cut = cutoff_in(text) or cutoff_in(head)
    for r in rows:''',
     '''    doc_cut = cutoff_in(text) or cutoff_in(head)
    only_metal = release_metal(head, text)
    for r in rows:
        if only_metal:
            for fig in r["grades"] + r["contained"]:
                if fig["metal"] is None:
                    fig["metal"] = only_metal'''),
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
