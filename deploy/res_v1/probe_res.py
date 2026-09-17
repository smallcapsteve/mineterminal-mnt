#!/usr/bin/env python3
"""Print the resource-table region of chosen releases so the reader can be designed against the
real text (RES_V1, 2026-09-17).

Usage: probe_res.py <start> <count> [--all|--sample] [--before N] [--after N]

Defaults to the 50-release sample, releases that contain a category word, ordered as the sample is.
Prints a window around the first category word; where there is none, the head of the body.
"""
import gzip
import json
import re
import sys

SRC = "/var/tmp/mnt-res/corpus.json.gz"
SET = "/var/tmp/mnt-res/sample.json"
KEY = re.compile(r"(?i)(measured|indicated|inferred)\s+(?:and\s+\w+\s+)?(?:mineral\s+)?resource")


def main(argv):
    start = int(argv[0]) if argv else 0
    count = int(argv[1]) if len(argv) > 1 else 5
    before = 600
    after = 1600
    scope = "sample"
    rest = argv[2:]
    i = 0
    while i < len(rest):
        if rest[i] == "--all":
            scope = "all"
        elif rest[i] == "--sample":
            scope = "sample"
        elif rest[i] == "--before":
            i += 1
            before = int(rest[i])
        elif rest[i] == "--after":
            i += 1
            after = int(rest[i])
        i += 1

    d = json.loads(gzip.open(SRC, "rb").read().decode())
    tagged = d["tagged"]
    tagged.sort(key=lambda r: ((r["published_at"] or ""), r["event_id"]), reverse=True)
    if scope == "sample":
        want = json.load(open(SET))["event_ids"]
        order = {e: n for n, e in enumerate(want)}
        rows = sorted([r for r in tagged if r["event_id"] in order], key=lambda r: order[r["event_id"]])
    else:
        rows = tagged

    rows = [r for r in rows if KEY.search(r["body"] or "")]
    print("candidates with a category word:", len(rows), " showing", start, "..", start + count)
    for r in rows[start:start + count]:
        b = r["body"] or ""
        m = KEY.search(b)
        s = max(0, m.start() - before)
        e = min(len(b), m.start() + after)
        print("=" * 78)
        print(r["event_id"][:12], r["ticker"], (r["published_at"] or "")[:10], "len", len(b), "at", m.start())
        print("H:", (r["headline"] or "")[:200])
        print("-" * 78)
        print(("..." if s else "") + b[s:e] + ("..." if e < len(b) else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
