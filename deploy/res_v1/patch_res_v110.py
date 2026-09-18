# -*- coding: utf-8 -*-
"""Turn RES_V1 1.0.9 into 1.0.10 (2026-09-18).

Measured at 1.0.9: detection 25/0/0/25; row 92.4%, deposit 78.9%, category 100.0%, tonnes 100.0%,
grade 89.4%, context 95.9%. Traced the two releases behind the remaining grade errors.

  AJ  a data row is not a header row. Canadian Palladium prints one header line and then five
      one-line rows, and from the second row on the reader was reading the row above -- another
      row of figures -- as the column labels, so every grade came back with no metal on it.
  AK  within one table the last good mapping still applies. Two cases now allow it: a header run
      with no units in it at all (Orogen prints a group label between the two halves of one
      table), and a header run that has not changed since the last row that mapped cleanly.
  AL  every resource row states a tonnage. A mapping of four columns or more that finds none has
      not understood the header, and refusing it is better than publishing XXIX's 62,706 kt of
      ore as contained copper.

Usage: patch_res_v110.py <resources.py>
"""
import hashlib
import sys

EDITS = [
    ('VERSION = "1.0.9"', 'VERSION = "1.0.10"'),
    ('''    cands = []
    for ln in prev_lines:
        toks = [t for t in re.split(r"\\s{1,}", ln.strip()) if t]
        if len(toks) >= max(3, n_values - 1) and not all(is_number(t) for t in toks):
            cands.append(toks)''',
     '''    cands = []
    for ln in prev_lines:
        toks = [t for t in re.split(r"\\s{1,}", ln.strip()) if t]
        if len(toks) < max(3, n_values - 1):
            continue
        # the row above a one-line row is usually another one-line row, and reading its figures
        # as column labels left every grade in Canadian Palladium's table with no metal on it
        if rowline_of(ln) or category_of(toks[0]):
            continue
        if sum(1 for t in toks if is_number(t)) * 2 >= len(toks):
            continue
        cands.append(toks)'''),
    ('''    last_cols, last_n = [], 0
    i = 0''',
     '''    last_cols, last_n, last_header = [], 0, None
    i = 0'''),
    ('''                last_cols if (not header_strength(header) and len(vals) == last_n) else []])
            r = _row((deposit_name(tail) if tail else None) or deposit, canon, "rowline", i)''',
     '''                last_cols if _may_reuse(header, last_header, len(vals), last_n) else []])
            r = _row((deposit_name(tail) if tail else None) or deposit, canon, "rowline", i)'''),
    ('''                cols = _best_columns([build_columns(header, len(vals)),
                                      last_cols if (not header_strength(header)
                                                    and len(vals) == last_n) else []])''',
     '''                cols = _best_columns([build_columns(header, len(vals)),
                                      last_cols if _may_reuse(header, last_header, len(vals),
                                                              last_n) else []])'''),
    ('''                last_cols, last_n = cols, len(vals)
            else:
                r["confidence"] = "low"''',
     '''                last_cols, last_n, last_header = cols, len(vals), list(header)
            else:
                r["confidence"] = "low"'''),
    ('''                    last_cols, last_n = cols, len(vals)
                else:
                    r["confidence"] = "low"''',
     '''                    last_cols, last_n, last_header = cols, len(vals), list(header)
                else:
                    r["confidence"] = "low"'''),
    ('''            header, deposit, dep_cut, dep_basis, dirty = [], None, None, None, False
            last_cols, last_n = [], 0''',
     '''            header, deposit, dep_cut, dep_basis, dirty = [], None, None, None, False
            last_cols, last_n, last_header = [], 0, None'''),
    ('def header_strength(run):',
     '''def _may_reuse(header, last_header, n_values, last_n):
    """Whether the previous row's columns still apply to this one.

    Two cases. Orogen prints a group label between the two halves of one table, so the header run
    in force has no units in it at all and the real header is above both. Canadian Palladium
    prints one header line and then five rows, and by the third the header is out of the look-back
    window -- but the header run has not changed, so the mapping has not either."""
    if n_values != last_n or not last_n:
        return False
    return not header_strength(header) or list(header) == (last_header or [])


def header_strength(run):'''),
    ('    return _borrow_metals(best)',
     '''    best = _borrow_metals(best)
    # Every resource row states a tonnage. A mapping of four columns or more that finds none has
    # not understood the header -- XXIX's 62,706 kt of ore was being read as contained copper.
    if len(best) >= 4 and not any(c["kind"] == "tonnage" for c in best):
        return []
    return best'''),
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
