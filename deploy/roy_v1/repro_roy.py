#!/usr/bin/env python3
"""ROY_V1 corpus review (read-only, 2026-09-21): run the Royalties & Streams reader over every approved release
in memory, publish nothing, and print what the page would show: counts, the reasons tagged releases give no
row, and EVERY row, compressed, so each can be read by eye.

Run from the candidate tree: python3 repro_roy.py [--db PATH]
"""
import base64
import json
import sqlite3
import sys
import time
import zlib
from collections import Counter

sys.path.insert(0, ".")
from portal.extractors import royalties as X   # noqa: E402
from portal import royalties_publish as P      # noqa: E402

db = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else "/opt/mnt/app/portal/portal.db"
conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
t0 = time.time()
items, reasons, n, tagged_total, errors = [], Counter(), 0, 0, 0
for eid, tk, pub, hl, body, cats, slug in conn.execute(
        "SELECT event_id, ticker, COALESCE(published_at, classified_at), raw_headline, raw_body, categories, slug "
        "FROM events WHERE review_status='auto_approved'"):
    n += 1
    tagged = ("|" + (cats or "") + "|").find("|Royalties & Streams|") >= 0
    tagged_total += tagged
    try:
        a = X.analyse(hl or "", body or "")
    except Exception as exc:  # noqa: BLE001
        errors += 1
        print("ERROR", eid[:12], type(exc).__name__, str(exc)[:120])
        continue
    if not a["rows"]:
        if tagged:
            reasons[a["reason"]] += 1
        continue
    recs = X.extract(hl or "", body or "")
    parsed = X.parse_records({i: [(f.field, f.seq, f.value_num, f.value_text) for f in r.facts] for i, r in enumerate(recs)})
    items.append(({"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl, "slug": slug,
                   "tagged": tagged, "cats": cats}, parsed))
rows, st = P.compute(items)
print("SECONDS", round(time.time() - t0, 1), "releases", n, "tagged", tagged_total, "errors", errors)
print("STATS", json.dumps(st))
print("TAGGED_NO_ROWS_REASONS", dict(reasons))
real = [r for r in rows if r["type"]]
print("TYPES", dict(Counter(r["type"] for r in real)), "ACTIONS", dict(Counter(r["action"] for r in real)))
print("FILLED", {k: sum(1 for r in real if r.get(k) is not None) for k in
                 ("rate_pct", "property", "operator", "buyer", "seller", "price", "metal", "status")}, "of", len(real))
print("UNTAGGED_CATS", Counter(c for e, p in items if not e["tagged"]
                               for c in (e["cats"] or "").split("|") if c).most_common(12))
dump = [[r["event_id"][:12], r["ticker"], (r["published_at"] or "")[:10], r["tag_confirmed"], (r["raw_headline"] or "")[:150],
         r["type"], r["rate_pct"], r["metal"], r["property"], r["operator"], r["buyer"], r["seller"], r["price"],
         r["currency"], r["action"], r["status"], r["deal_releases"], r["is_latest"]] for r in real]
blob = base64.b64encode(zlib.compress(json.dumps(dump).encode(), 9)).decode()
print("ROWS_B64", len(blob))
for i in range(0, len(blob), 60000):
    print(blob[i:i + 60000])
print("DONE")
