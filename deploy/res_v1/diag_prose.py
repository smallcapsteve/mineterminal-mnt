#!/usr/bin/env python3
"""Show each row the prose reader builds and the sentence it came from (RES_V1, 2026-09-18).

Three releases are left where the reader is at fault rather than the labels -- Adyton reads the
wrong project's paragraph, Patriot's two deposits both fall back to the project name, and
Silvercorp's two deposits do the same. All three are prose, so this prints the sentence behind
every prose row.

Usage: diag_prose.py <id-prefix> [<id-prefix> ...]
"""
import gzip
import importlib.util
import json
import sys

sys.path.insert(0, "/opt/mnt/app")
SRC = "/var/tmp/mnt-res/corpus.json.gz"
MOD = "/var/tmp/mnt-res/resources.py"

spec = importlib.util.spec_from_file_location("res_v1", MOD)
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def main(argv):
    d = json.loads(gzip.open(SRC, "rb").read().decode())
    by_id = {r["event_id"]: r for r in d["tagged"]}
    for p in argv:
        hit = [e for e in by_id if e.startswith(p)]
        if len(hit) != 1:
            print("!!", p, "matches", len(hit))
            continue
        r = by_id[hit[0]]
        head = R.clean(r["headline"])
        text = R.clean(r["body"])
        print("#" * 70)
        print(r["event_id"][:12], r["ticker"], head[:110])
        print("release project:", R.release_project(head, text[:1500]),
              " metal:", R.release_metal(head, text), " announces:", R.release_announces(head, text))
        for row in R.read_prose(R.reflow(text)):
            print("-" * 70)
            print("  %-22s t=%-12s proj=%r" % (row["category"],
                  ("%d" % row["tonnes"]) if row["tonnes"] else "-", row.get("_proj")))
            print("  grades:", [(g["metal"], g["value"], g["unit"]) for g in row["grades"]])
            print("  contained:", [(c["metal"], c["value"], c["unit"]) for c in row["contained"]])
            print("  from: " + (row.get("_win") or "")[:300])
        print("=" * 70)
        print("FINAL ROWS")
        for row in R.analyse(r["headline"], r["body"])["rows"]:
            print("  %-34s %-22s t=%-12s ctx=%-18s src=%s" % (
                str(row["deposit"])[:34], row["category"],
                ("%d" % row["tonnes"]) if row["tonnes"] else "-", row["context"], row["source"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
