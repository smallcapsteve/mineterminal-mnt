#!/usr/bin/env python3
"""Turn RES_V1 1.0.6 into 1.0.7 (2026-09-18).

Measured at 1.0.6: detection 25/0/0/25; row 89.0%, deposit 82.2%, category 100.0%, tonnes 95.8%,
grade 81.8%, context 89.0%.

  Y   two readings of one row are one row. Kenorland's table names the deposit and its prose names
      the project, so the same 14.5 Mt was published twice under two names. Where the category,
      the basis and the figures agree, the more specific name wins and the duplicate goes.
  Z   the base case is the one the release says it is. Cruz states its estimate at 300 ppm first
      and calls the 500 ppm case its base case, and taking the first one marked the base case as
      an alternative and the alternative as the base.
  AA  a deposit name does not end on a dangling connective: stripping " at Dec 31, 2024" off
      "Ermitano and at Dec 31, 2024" left "Ermitano and" on the page.
  AB  a deposit read out of the category cell now gets the same scrutiny as one read off a
      heading. "new" was reaching the page as a deposit because that path skipped the checks.

Usage: patch_res_v107.py <resources.py>
"""
import hashlib
import sys

EDITS = [
    ('VERSION = "1.0.6"', 'VERSION = "1.0.7"'),
    ('''    # a deposit has a name: "new" is what was left of a sentence, not a place
    if not any(t[:1].isupper() for t in toks):
        return None''',
     '''    # a deposit has a name: "new" is what was left of a sentence, not a place
    if not any(t[:1].isupper() for t in toks):
        return None
    # stripping " at Dec 31, 2024" off "Ermitano and at Dec 31, 2024" leaves a dangling "and"
    s = re.sub(r"(?i)[\\s,]+(?:and|or|&|with|plus|inclusive)\\s*$", "", s).strip(" ,.;:-")
    if len(s) < 2:
        return None'''),
    ('                r = _row(cat[1] or deposit, cat[0], "table", i)',
     '                r = _row((deposit_name(cat[1]) if cat[1] else None) or deposit, cat[0], "table", i)'),
    ('            r = _row(tail or deposit, canon, "rowline", i)',
     '            r = _row((deposit_name(tail) if tail else None) or deposit, canon, "rowline", i)'),
    ('def _dedupe(rows):',
     '''def _merge_same_figures(rows):
    """Two readings of one row are one row.

    Kenorland's table names the deposit and its prose names the project, so the same 14.5 Mt was
    published twice under two names. Where the category, the basis and the figures agree, the more
    specific name wins and the duplicate goes."""
    out = []
    for r in rows:
        twin = None
        for k in out:
            if k["category"] != r["category"] or k["basis"] != r["basis"]:
                continue
            if k["tonnes"] and r["tonnes"] and _same_figures(k, r):
                twin = k
                break
        if twin is None:
            out.append(r)
            continue
        if len(_norm_dep(r["deposit"]).split()) > len(_norm_dep(twin["deposit"]).split()):
            twin["deposit"] = r["deposit"]
        if not twin["grades"] and r["grades"]:
            twin["grades"] = r["grades"]
        if not twin["contained"] and r["contained"]:
            twin["contained"] = r["contained"]
    return out


def _dedupe(rows):'''),
    ('''    rows = [r for r in rows if not _figureless(r)]
    rows = _dedupe(rows)[:MAX_ROWS]''',
     '''    rows = [r for r in rows if not _figureless(r)]
    rows = _merge_same_figures(sorted(rows, key=lambda r: (_SRC_RANK.get(r["source"], 9), r["pos"])))
    rows = _dedupe(rows)[:MAX_ROWS]'''),
    ('''        base = next((r for r in kept if r["source"] in ("prose", "headline")), kept[0] if kept else None)''',
     '''        # Cruz states its estimate at 300 ppm first and calls the 500 ppm case its base case.
        # The base case is the one the release says it is, not the one that comes first.
        base = next((r for r in kept if re.search(r"(?i)\\bbase[\\s-]?case\\b", r.get("_win") or "")),
                    None)
        if base is None:
            base = next((r for r in kept if r["source"] in ("prose", "headline")),
                        kept[0] if kept else None)'''),
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
