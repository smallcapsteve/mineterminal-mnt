#!/usr/bin/env python3
"""Turn RES_V1 1.0.2 into 1.0.3 (2026-09-18).

Measured at 1.0.2 on the 50-release set: detection 25 right, 0 missed, 0 spurious, 25 correctly
empty; row 88.8%, deposit 86.1%, category 100.0%, tonnes 80.5%, grade 71.6%, context 92.4%.

  I  one table's columns were being carried into the next table. RUA Gold's tonnage came back as
     its contained ounces that way, and Fireweed's 6.3 Mt came back as 94. A header that is
     present but does not fit is this table's header read wrongly, and the previous table's
     meanings must not stand in for it; where the mapping cannot be established the row keeps its
     deposit and its category and states no figures. A header run with no units at all is a
     different thing -- Orogen prints a group label between two halves of one table -- and there
     the last good mapping still applies.
  J  a sentence that names its own project owns its figures. Adyton restates Feni Island beside
     the Wapolu estimate it is announcing, and the release-level fallback put Feni Island's
     60.4 Mt under Wapolu.
  K  a subscript that a PDF put on its own line is part of the formula: "0.85% Li" / "2" / "O" is
     a lithium-oxide grade, not a lithium grade.
  L  a project named without a preposition in front of it ("The Wapolu Gold Project has ...") was
     not being found at all.

Usage: patch_res_v103.py <resources.py>
"""
import hashlib
import sys

EDITS = [
    ('VERSION = "1.0.2"', 'VERSION = "1.0.3"'),
    ('def _best_columns(cands):',
     '''def header_strength(run):
    """How many of a header run's lines actually carry a unit.

    Zero means there is no header here -- Orogen prints "Resources (inclusive of reserve)" between
    its reserve rows and its resource rows, and the table's real header is above both. A header
    with units that simply does not fit the row is a different thing: it is this table's header,
    read wrongly, and the previous table's columns must not stand in for it.
    """
    return sum(1 for ln in run if ln and not _CLASS_WORD.match(ln) and parse_col(ln)["unit"])


def _best_columns(cands):'''),
    ('''                last_cols if len(vals) == last_n else []])
            r = _row(tail or deposit, canon, "rowline", i)''',
     '''                last_cols if (not header_strength(header) and len(vals) == last_n) else []])
            r = _row(tail or deposit, canon, "rowline", i)'''),
    ('''                cols = _best_columns([build_columns(header, len(vals)),
                                      last_cols if len(vals) == last_n else []])''',
     '''                # A header that is present but does not fit is a header this reader cannot read.
                # Borrowing the previous table's columns then puts the previous table's meanings
                # on these numbers -- RUA Gold's tonnage came back as its contained ounces that
                # way. Where the mapping cannot be established the row keeps its deposit and its
                # category and states no figures.
                cols = _best_columns([build_columns(header, len(vals)),
                                      last_cols if (not header_strength(header)
                                                    and len(vals) == last_n) else []])'''),
    ('''                r = _row(None, canon, "prose", h.start())
                r["_win"] = part''',
     '''                r = _row(None, canon, "prose", h.start())
                r["_win"] = part
                # Adyton restates Feni Island beside the Wapolu estimate it is announcing. Falling
                # back to the release's project put Feni Island's 60.4 Mt under Wapolu.
                r["_proj"] = release_project(part)'''),
    ('''        if not r["deposit"] and project:
            r["deposit"] = project''',
     '''        if not r["deposit"]:
            r["deposit"] = r.get("_proj") or project'''),
    ('''    for r in rows:
        r.pop("_win", None)''',
     '''    for r in rows:
        r.pop("_win", None)
        r.pop("_proj", None)'''),
    ('''    t = re.sub(r"\\r\\n?", "\\n", t)
    t = _WS.sub(" ", t)''',
     '''    t = re.sub(r"\\r\\n?", "\\n", t)
    t = _WS.sub(" ", t)
    # "0.85% Li" / "2" / "O" is one grade, not lithium. A PDF puts the subscript on its own line.
    t = re.sub(r"(?m)([A-Za-z])[ ]*\\n[ ]*(\\d)[ ]*\\n[ ]*([A-Z][a-z]?\\d?)(?=\\b)", r"\\1\\2\\3", t)
    t = re.sub(r"(?m)\\b([A-Z][a-z]?)[ ]*\\n[ ]*(\\d[A-Z][a-z]?\\d*)(?=\\b)", r"\\1\\2", t)'''),
    ('''    r"(?i)\\b(?:at|for|on|of|to)\\s+(?:its|the|their|our)?\\s*"''',
     '''    r"(?i)(?:^|\\b)(?:at|for|on|of|to|in|the|its|their|our|company's)\\s+"
    r"(?:its|the|their|our|100%[\\s-]?owned|wholly[\\s-]?owned)?\\s*"'''),
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
