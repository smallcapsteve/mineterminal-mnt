#!/usr/bin/env python3
"""Describe the resource corpus and pick the RES_V1 accuracy sample (2026-09-17).

Reads /var/tmp/mnt-res/corpus.json.gz, writes /var/tmp/mnt-res/sample.json, and prints a summary
small enough to carry back in one relay output. Nothing here touches portal.db.

The sample rule is fixed so it can be reproduced: sort the 642 tagged auto-approved releases by
published_at descending (event_id breaks ties), then take 50 evenly spaced positions across the
whole list. Even spacing keeps the sample representative of the page as a whole -- including the
416 releases the old reader finds nothing in -- rather than over-weighting the ones it handles.
"""
import collections
import gzip
import hashlib
import json
import re

SRC = "/var/tmp/mnt-res/corpus.json.gz"
OUT = "/var/tmp/mnt-res/sample.json"
N = 50

KEY = re.compile(r"(?i)(measured|indicated|inferred)\s+(?:and\s+\w+\s+)?(?:mineral\s+)?resource")
TONNES = re.compile(r"(?i)\b\d[\d,\.]*\s*(?:million\s+)?(?:tonnes|tons|t\b|Mt\b|kt\b)")
GRADE = re.compile(r"(?i)\b\d[\d,\.]*\s*(?:g/t|gpt|g per tonne|%|opt|oz/t)")
CONTAINED = re.compile(r"(?i)\b(?:contained|containing)\b|\b\d[\d,\.]*\s*(?:million\s+)?(?:ounces|oz|lbs|pounds)\b")


def pctl(xs, p):
    if not xs:
        return -1
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


def main():
    d = json.loads(gzip.open(SRC, "rb").read().decode())
    tagged = d["tagged"]
    legacy = d["legacy_rows"]
    cols = sorted(legacy[0].keys()) if legacy else []
    lid = "event_id" if cols and "event_id" in cols else None
    legacy_ids = {r[lid] for r in legacy} if lid else set()

    tagged.sort(key=lambda r: ((r["published_at"] or ""), r["event_id"]), reverse=True)

    print("legacy columns:", ",".join(cols))
    print("tagged", len(tagged), "legacy rows", len(legacy), "legacy distinct releases", len(legacy_ids))
    print("sources:", dict(collections.Counter(r["source"] for r in tagged).most_common(8)))

    lens = [r["body_len"] for r in tagged]
    print("body_len p50/p75/p90/p99/max:", pctl(lens, .5), pctl(lens, .75), pctl(lens, .9), pctl(lens, .99), max(lens))
    print("truncated at cap:", sum(1 for x in lens if x > d["body_cap"]), "of", len(lens))

    pos, nk, nt, ng, nc = [], 0, 0, 0, 0
    for r in tagged:
        b = r["body"] or ""
        m = KEY.search(b)
        if m:
            nk += 1
            pos.append(m.start())
        nt += bool(TONNES.search(b))
        ng += bool(GRADE.search(b))
        nc += bool(CONTAINED.search(b))
    print("body has category word:", nk, " tonnes:", nt, " grade:", ng, " contained metal:", nc)
    print("first category word at char p25/p50/p75/p90:", pctl(pos, .25), pctl(pos, .5), pctl(pos, .75), pctl(pos, .9))

    idx = sorted({round(i * (len(tagged) - 1) / (N - 1)) for i in range(N)})
    sample = [tagged[i] for i in idx]
    ids = [r["event_id"] for r in sample]
    set_sha = hashlib.sha256("\n".join(str(x) for x in ids).encode()).hexdigest()
    json.dump({"rule": "tagged sorted by published_at desc, 50 evenly spaced positions",
               "set_sha": set_sha, "event_ids": ids}, open(OUT, "w"))

    print("set_sha", set_sha)
    print("in legacy:", sum(1 for r in sample if r["event_id"] in legacy_ids), "of", len(sample))
    print("--- sample ---")
    for r in sample:
        b = r["body"] or ""
        m = KEY.search(b)
        print("|".join([str(r["event_id"]), r["ticker"] or "", (r["published_at"] or "")[:10],
                        "L" if r["event_id"] in legacy_ids else "-",
                        str(r["body_len"]), str(m.start() if m else -1),
                        (r["headline"] or "")[:110]]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
