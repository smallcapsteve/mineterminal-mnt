#!/usr/bin/env python3
"""PROD_V1 corpus review (read-only, 2026-09-21): run the Production Results reader over every approved
release in memory, publish nothing, and print what the page would show -- counts, the shapes of what it
reads, the outliers, and random samples of tagged and untagged rows to read by eye.

Run from the candidate tree: python3 repro_prod.py [--db PATH]
"""
import json
import random
import re
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, ".")
from portal.extractors import production as X   # noqa: E402
from portal import production_publish as P      # noqa: E402

db = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else "/opt/mnt/app/portal/portal.db"
conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
t0 = time.time()
items, reasons, n = [], Counter(), 0
tagged_total = 0
for eid, tk, pub, hl, body, cats, slug in conn.execute(
        "SELECT event_id, ticker, COALESCE(published_at, classified_at), raw_headline, raw_body, categories, slug "
        "FROM events WHERE review_status='auto_approved'"):
    n += 1
    tagged = ("|" + (cats or "") + "|").find("|Production Results|") >= 0
    tagged_total += tagged
    a = X.analyse(hl or "", body or "")
    if not a["rows"]:
        if tagged:
            reasons[a["reason"]] += 1
        if not tagged:
            continue
    recs = X.extract(hl or "", body or "")
    parsed = X.parse_records({i: [(f.field, f.seq, f.value_num, f.value_text) for f in r.facts] for i, r in enumerate(recs)})
    items.append(({"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl, "slug": slug,
                   "tagged": tagged, "cats": cats}, parsed))
rows, st = P.compute([(e, p) for e, p in items])
print("SECONDS", round(time.time() - t0, 1), "releases", n, "tagged", tagged_total)
print("STATS", json.dumps(st))
print("TAGGED_NO_ROWS_REASONS", dict(reasons))
real = [r for r in rows if r["kind"]]
print("KINDS", dict(Counter(r["kind"] for r in real)))
print("METALS", Counter((r["metal"], r["unit"]) for r in real if r["kind"] != "milestone").most_common(25))
print("PERIODS", Counter((r["period"] or "")[:2] for r in real if r["kind"] != "milestone").most_common(12))
print("MILESTONES", Counter(r["milestone"] for r in real if r["kind"] == "milestone").most_common())
print("YEARS", sorted(Counter((r["published_at"] or "")[:4] for r in real).items()))
print("UNTAGGED_CATS", Counter(c for e, p in items if not e["tagged"] and p["rows"]
                               for c in (e["cats"] or "").split("|") if c).most_common(12))

# outliers: implausibly large figures per metal and unit
LIM = {("gold", "oz"): 3e6, ("silver", "oz"): 5e7, ("AuEq", "oz"): 3e6, ("GEO", "oz"): 1e6, ("AgEq", "oz"): 6e7,
       ("copper", "t"): 1.5e6, ("copper", "lb"): 3e9, ("U3O8", "lb"): 4e7}
out = [r for r in real if r["kind"] != "milestone" and (r.get("qty") or r.get("high") or r.get("low") or 0) >
       LIM.get((r["metal"], r["unit"]), 1e12)]
print("OUTLIERS", len(out))
for r in out[:12]:
    print("   ", r["ticker"], r["published_at"][:10], r["kind"], r["period"], r["metal"], r.get("qty"), r.get("low"),
          r.get("high"), "|", (r["raw_headline"] or "")[:80])
small = [r for r in real if r["kind"] == "actual" and r["unit"] == "oz" and (r.get("qty") or 0) < 50]
print("TINY", len(small), [(r["ticker"], r["qty"], r["metal"]) for r in small[:10]])

by = {}
for r in real:
    by.setdefault(r["event_id"], []).append(r)
rnd = random.Random(20260921)
ev = {e["event_id"]: e for e, p in items}


def show(eids, label, k):
    print("SAMPLE", label, len(eids))
    for e in rnd.sample(sorted(eids), min(k, len(eids))):
        rr = by[e]
        print("  ##", ev[e]["ticker"], (ev[e]["published_at"] or "")[:10], e[:12], "|", (ev[e]["raw_headline"] or "")[:110])
        for r in rr[:8]:
            if r["kind"] == "milestone":
                print("       M", r["milestone"], r["asset"])
            elif r["kind"] == "guidance":
                print("       G", r["period"], r["metal"], r["low"], r["high"], r["unit"])
            else:
                print("       A", r["period"], r["metal"], r["qty"], r["unit"], "sold=%s" % r["sold"] if r["sold"] else "",
                      "guided=%s-%s" % (r["guided_low"], r["guided_high"]) if r["guided_low"] or r["guided_high"] else "")


show({e for e in by if ev[e]["tagged"]}, "TAGGED", 28)
show({e for e in by if not ev[e]["tagged"]}, "UNTAGGED", 32)
print("DONE")
