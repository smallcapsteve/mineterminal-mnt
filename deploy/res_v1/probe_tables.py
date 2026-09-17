#!/usr/bin/env python3
"""Locate resource tables in the corpus and show them as raw lines (RES_V1, 2026-09-17).

Releases reach us with the HTML table flattened to one cell per line, so a resource table looks
like a run of short lines: column labels, a units row, then a category name followed by its
numbers. This finds that run. It prints a corpus-wide count first -- the real ceiling for how many
of the 642 tagged releases carry an estimate at all -- then the raw lines of a few of them.

Usage: probe_tables.py <start> <count> [--all|--sample] [--quiet]
"""
import gzip
import json
import re
import sys

SRC = "/var/tmp/mnt-res/corpus.json.gz"
SET = "/var/tmp/mnt-res/sample.json"

CAT = re.compile(
    r"(?ix)^\s*(?:total\s+)?(?:"
    r"measured(?:\s*(?:&|and|\+|,)\s*indicated)?|indicated|inferred|"
    r"m\s*&\s*i|m\s*\+\s*i|proven|proved|probable|"
    r"proven\s*(?:&|and|\+)\s*probable|p\s*&\s*p|total"
    r")\s*(?:mineral\s*)?(?:resources?|reserves?)?\s*(?:\(.*?\))?\s*[:\-]?\s*$")

NUM = re.compile(r"(?ix)^\s*[<>~]?\s*\(?\s*[\d][\d,\.\s]*\s*\)?\s*"
                 r"(?:%|g\s*/\s*t|gpt|oz|koz|moz|kt|mt|t|lbs?|mlbs?|ppm|m|km)?\s*$")


def lines_of(body):
    return [ln.strip() for ln in (body or "").split("\n")]


def find_tables(body, lookahead=12, need=2):
    ls = lines_of(body)
    hits = []
    for i, ln in enumerate(ls):
        if not ln or not CAT.match(ln):
            continue
        nums = 0
        for j in range(i + 1, min(len(ls), i + 1 + lookahead)):
            if not ls[j]:
                continue
            if NUM.match(ls[j]):
                nums += 1
            elif CAT.match(ls[j]):
                break
            elif nums:
                break
        if nums >= need:
            if hits and i - hits[-1][1] <= lookahead + 2:
                hits[-1] = (hits[-1][0], i)
            else:
                hits.append((i, i))
    return hits, ls


def main(argv):
    start = int(argv[0]) if argv else 0
    count = int(argv[1]) if len(argv) > 1 else 3
    scope = "sample"
    quiet = "--quiet" in argv
    if "--all" in argv:
        scope = "all"

    d = json.loads(gzip.open(SRC, "rb").read().decode())
    tagged = d["tagged"]
    tagged.sort(key=lambda r: ((r["published_at"] or ""), r["event_id"]), reverse=True)
    legacy_ids = {r["event_id"] for r in d["legacy_rows"]}

    with_table = [r for r in tagged if find_tables(r["body"])[0]]
    print("tagged", len(tagged), "with a located table:", len(with_table),
          " legacy rows exist for", len(legacy_ids))
    print("located but not in legacy:", len([r for r in with_table if r["event_id"] not in legacy_ids]),
          " in legacy but not located:", len([r for r in tagged if r["event_id"] in legacy_ids
                                              and not find_tables(r["body"])[0]]))
    ctrl = [r for r in d["control"] if find_tables(r["body"])[0]]
    print("control (untagged lookalikes)", len(d["control"]), "with a located table:", len(ctrl))
    if quiet:
        return 0

    if scope == "sample":
        want = json.load(open(SET))["event_ids"]
        order = {e: n for n, e in enumerate(want)}
        rows = sorted([r for r in with_table if r["event_id"] in order], key=lambda r: order[r["event_id"]])
        print("sample releases with a located table:", len(rows), "of", len(order))
    else:
        rows = with_table

    for r in rows[start:start + count]:
        hits, ls = find_tables(r["body"])
        print("=" * 78)
        print(r["event_id"][:12], r["ticker"], (r["published_at"] or "")[:10],
              "tables", len(hits), "legacy" if r["event_id"] in legacy_ids else "-")
        print("H:", (r["headline"] or "")[:160])
        a, b = hits[0]
        lo, hi = max(0, a - 16), min(len(ls), b + 34)
        for k in range(lo, hi):
            if ls[k]:
                print("%4d| %s" % (k, ls[k][:120]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
