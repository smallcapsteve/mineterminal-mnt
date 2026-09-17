#!/usr/bin/env python3
"""Print just enough of each set release to label it (RES_V1, 2026-09-17).

One block per release: identifiers, the shape bucket, the full headline (the headline is a source
in its own right -- some releases put every figure there and almost nothing in the body), and a
focused excerpt. Excerpts are kept short on purpose so the whole 50-release set can be reviewed
without carrying the corpus off the droplet.

Usage: label_pack.py <start> <count>
"""
import gzip
import json
import re
import sys

sys.path.insert(0, "/var/tmp/mnt-res")
from probe_tables import find_tables, lines_of, NUM  # noqa: E402
from probe_missed import ROWLINE, PROSE, LOOSE, shape  # noqa: E402

SRC = "/var/tmp/mnt-res/corpus.json.gz"
SET = "/var/tmp/mnt-res/sample.json"

SENT = re.compile(r"[^.\n]{0,400}?[.\n]")


def excerpt(r):
    b = r["body"] or ""
    ls = lines_of(b)
    hits, _ = find_tables(b)
    if hits:
        a, z = hits[0]
        lo = max(0, a - 10)
        hi = min(len(ls), z + 14)
        out = [ls[k] for k in range(lo, hi) if ls[k]]
        return "TABLE\n" + "\n".join(out[:46])
    rows = [ln for ln in ls if ROWLINE.match(ln)]
    if rows:
        return "ROWS\n" + "\n".join(x[:200] for x in rows[:12])
    sents = []
    for m in re.finditer(r"[^\n]+", b):
        ln = m.group(0)
        if PROSE.search(ln) or LOOSE.search(ln):
            sents.append(ln.strip()[:300])
        if len(sents) >= 6:
            break
    if sents:
        return "PROSE\n" + "\n".join(sents)
    head = " ".join((b[:400] or "").split())
    return "NONE\n" + head


def main(argv):
    start = int(argv[0]) if argv else 0
    count = int(argv[1]) if len(argv) > 1 else 25

    d = json.loads(gzip.open(SRC, "rb").read().decode())
    tagged = d["tagged"]
    tagged.sort(key=lambda r: ((r["published_at"] or ""), r["event_id"]), reverse=True)
    legacy = {r["event_id"]: r for r in d["legacy_rows"]}
    want = json.load(open(SET))["event_ids"]
    order = {e: n for n, e in enumerate(want)}
    rows = sorted([r for r in tagged if r["event_id"] in order], key=lambda r: order[r["event_id"]])

    print("set of", len(rows), "showing", start, "..", start + count)
    for n, r in enumerate(rows[start:start + count], start):
        lg = legacy.get(r["event_id"])
        print("#" * 70)
        print("[%02d] %s %s %s %s %s" % (n, r["event_id"][:12], r["ticker"] or "?",
                                         (r["published_at"] or "")[:10], shape(r),
                                         "len=%d" % len(r["body"] or "")))
        print("H: " + " ".join((r["headline"] or "").split()))
        if lg:
            print("LIVE: project=%r metal=%r type=%r n_cat=%s cats=%s" % (
                lg.get("project"), lg.get("metal_focus"), lg.get("mre_type"),
                lg.get("n_categories"), str(lg.get("categories_json"))[:260]))
        print(excerpt(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
