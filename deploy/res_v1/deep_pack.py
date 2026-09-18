#!/usr/bin/env python3
"""Print the full figure-bearing region of named releases (RES_V1, 2026-09-17).

The labelling pack keeps excerpts short so the whole set fits in one look; a dozen or so releases
need more than that -- several tables, a deposit heading above the rows, an annual statement that
covers six mines. This prints those in full, by event_id prefix.

Usage: deep_pack.py <id-prefix> [<id-prefix> ...] [--lines N]
"""
import gzip
import json
import re
import sys

sys.path.insert(0, "/var/tmp/mnt-res")
from probe_tables import find_tables, lines_of  # noqa: E402
from probe_missed import ROWLINE, PROSE, LOOSE  # noqa: E402

SRC = "/var/tmp/mnt-res/corpus.json.gz"


def main(argv):
    n_lines = 120
    if "--lines" in argv:
        i = argv.index("--lines")
        n_lines = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    prefixes = [a for a in argv if not a.startswith("--")]

    d = json.loads(gzip.open(SRC, "rb").read().decode())
    by_id = {r["event_id"]: r for r in d["tagged"]}
    legacy = {r["event_id"]: r for r in d["legacy_rows"]}

    for p in prefixes:
        match = [e for e in by_id if e.startswith(p)]
        if len(match) != 1:
            print("!! prefix", p, "matches", len(match))
            continue
        r = by_id[match[0]]
        ls = lines_of(r["body"] or "")
        hits, _ = find_tables(r["body"])
        print("#" * 70)
        print(r["event_id"][:12], r["ticker"], (r["published_at"] or "")[:10], "tables", len(hits))
        print("H: " + " ".join((r["headline"] or "").split()))
        lg = legacy.get(r["event_id"])
        if lg:
            print("LIVE:", str(lg.get("categories_json"))[:300])
        keep = set()
        for a, z in hits:
            for k in range(max(0, a - 14), min(len(ls), z + 16)):
                keep.add(k)
        for k, ln in enumerate(ls):
            if ROWLINE.match(ln) or PROSE.search(ln) or LOOSE.search(ln):
                for j in range(max(0, k - 2), min(len(ls), k + 3)):
                    keep.add(j)
        out = [k for k in sorted(keep) if ls[k]][:n_lines]
        prev = None
        for k in out:
            if prev is not None and k > prev + 1:
                print("   ...")
            print("%4d| %s" % (k, ls[k][:150]))
            prev = k
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
