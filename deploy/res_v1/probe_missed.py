#!/usr/bin/env python3
"""Classify the releases the line-run table locator misses (RES_V1, 2026-09-17).

The first locator found 119 of 642 tagged releases; the live reader has rows for 179, 122 of which
the locator does not see. Those 122 are the whole question: what shape do they state resources in?
This buckets every tagged release by shape and prints raw lines from a few of the missed ones.

Usage: probe_missed.py <start> <count> [--bucket NAME] [--quiet]
"""
import collections
import gzip
import json
import re
import sys

sys.path.insert(0, "/var/tmp/mnt-res")
from probe_tables import CAT, NUM, find_tables, lines_of  # noqa: E402

SRC = "/var/tmp/mnt-res/corpus.json.gz"

CATWORD = re.compile(r"(?i)\b(measured|indicated|inferred|proven|probable)\b")
# a whole row on one line: "Indicated   754,514   13.03   334,825"
ROWLINE = re.compile(r"(?i)^\s*(?:total\s+)?(measured|indicated|inferred|proven|probable|m\s*&\s*i)"
                     r"[^\d\n]{0,40}?((?:[\d][\d,\.]*\s*(?:%|g/t|gpt|oz|koz|moz|kt|mt|t|lbs?|ppm)?[\s|,]+){2,})")
# prose: "Inferred Mineral Resource of 6.5 Mt at 1.02% Sb"
PROSE = re.compile(r"(?i)\b(measured|indicated|inferred)\b[^.\n]{0,60}?\bresources?\b[^.\n]{0,40}?"
                   r"\b(?:of|totalling|totaling|totals?|comprising|containing|estimated at)\b[^.\n]{0,30}?[\d]")
# loose prose: category word and a number close together in the same sentence
LOOSE = re.compile(r"(?i)\b(measured|indicated|inferred)\b[^.\n]{0,120}?[\d][\d,\.]*\s*"
                   r"(?:%|g/t|gpt|mt\b|kt\b|tonnes|t\b|oz|koz|moz|million)")


def shape(r):
    b = r["body"] or ""
    if find_tables(b)[0]:
        return "A_table_lines"
    for ln in lines_of(b):
        if ROWLINE.match(ln):
            return "B_row_on_one_line"
    if PROSE.search(b):
        return "C_prose_statement"
    if LOOSE.search(b):
        return "D_loose_prose"
    if CATWORD.search(b):
        return "E_category_word_only"
    return "F_no_category_word"


def main(argv):
    start = int(argv[0]) if argv else 0
    count = int(argv[1]) if len(argv) > 1 else 3
    bucket = None
    if "--bucket" in argv:
        bucket = argv[argv.index("--bucket") + 1]
    quiet = "--quiet" in argv

    d = json.loads(gzip.open(SRC, "rb").read().decode())
    tagged = d["tagged"]
    tagged.sort(key=lambda r: ((r["published_at"] or ""), r["event_id"]), reverse=True)
    legacy_ids = {r["event_id"] for r in d["legacy_rows"]}

    buckets = collections.Counter()
    legacy_by_bucket = collections.Counter()
    for r in tagged:
        s = shape(r)
        r["_shape"] = s
        buckets[s] += 1
        if r["event_id"] in legacy_ids:
            legacy_by_bucket[s] += 1
    for k in sorted(buckets):
        print("%-22s %4d  of which the live reader has rows for %4d" % (k, buckets[k], legacy_by_bucket[k]))

    ctrl = collections.Counter(shape(r) for r in d["control"])
    print("control:", dict(sorted(ctrl.items())))
    if quiet:
        return 0

    rows = [r for r in tagged if (bucket is None or r["_shape"] == bucket)]
    if bucket is None:
        rows = [r for r in rows if r["_shape"] != "A_table_lines" and r["event_id"] in legacy_ids]
    print("showing", start, "..", start + count, "of", len(rows))
    for r in rows[start:start + count]:
        b = r["body"] or ""
        ls = lines_of(b)
        anchor = 0
        for i, ln in enumerate(ls):
            if ROWLINE.match(ln) or LOOSE.search(ln):
                anchor = i
                break
        print("=" * 78)
        print(r["event_id"][:12], r["ticker"], (r["published_at"] or "")[:10], r["_shape"],
              "legacy" if r["event_id"] in legacy_ids else "-")
        print("H:", (r["headline"] or "")[:160])
        for k in range(max(0, anchor - 6), min(len(ls), anchor + 30)):
            if ls[k]:
                print("%4d| %s" % (k, ls[k][:130]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
