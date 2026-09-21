#!/usr/bin/env python3
"""Build accuracy/sets/royalties.json from the labels Justin confirmed (ROY_SET_V1, 2026-09-21).

  build_roy_set.py LABELS OUT [--db PATH]

Reads portal.db READ-ONLY. Each label's 12-character id is resolved to the live event_id by prefix (exactly
one match or it refuses), and body_sha1 is computed with portal.facts.text_sha1 over the LIVE raw_headline
and raw_body -- never a hash of a working extract.

Review: all 50 confirmed on Justin's review page (2026-09-21), 22 with rows (25 rows) and 28 confirmed
negatives, which count against false rows. His three rule calls were confirmed as drafted: the NSR a buyer
grants the vendor in a property deal is a mention in passing; a promotional recap is not a row; a closing is
a row of its own and a recap inside results or a letter is not.
"""
import json
import sqlite3
import sys

sys.path.insert(0, "/opt/mnt/app")
from portal import facts  # noqa: E402

args = sys.argv[1:]
db = args[args.index("--db") + 1] if "--db" in args else "/opt/mnt/app/portal/portal.db"
labels_path, out_path = args[0], args[1]
lab = json.load(open(labels_path, encoding="utf-8"))
conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
ROW_KEYS = ("type", "rate_pct", "metal", "property", "operator", "buyer", "seller", "price", "currency", "price_note",
            "action", "status")

items, problems = [], []
for it in lab["items"]:
    rs = conn.execute("SELECT event_id, raw_headline, raw_body FROM events WHERE event_id LIKE ?",
                      (it["event_id"] + "%",)).fetchall()
    if len(rs) != 1:
        problems.append("%s: %d matches" % (it["event_id"], len(rs)))
        continue
    full, hl, body = rs[0]
    rows = [{k: r.get(k) for k in ROW_KEYS if r.get(k) is not None} for r in (it.get("rows") or [])]
    items.append({
        "n": it["n"], "event_id": full, "ticker": it["ticker"], "stratum": it.get("stratum"),
        "body_sha1": facts.text_sha1(hl, body), "review": it["review"],
        "note": it.get("note") or "see claude/MNT_ROY_SET_LABELS_CONFIRMED_2026-09-21.json",
        "expect": {"is_royalty": bool(rows), "complete": it.get("complete", True), "rows": rows}})
if problems:
    raise SystemExit("REFUSED: " + "; ".join(problems))

aset = {"schema": 1, "name": "royalties", "tag": "Royalties & Streams", "status": "confirmed",
        "created": "2026-09-21", "reviewer": "Justin", "reviewed_at": lab.get("confirmed"),
        "row_shape": "one row per royalty or stream interest a release reports as news: bought, sold, granted, "
                     "bought back or amended",
        "items": items}
json.dump(aset, open(out_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("royalties set: %d items (%d excluded), %d rows -> %s" % (
    len(items), sum(1 for i in items if i["review"] == "excluded"),
    sum(len(i["expect"]["rows"]) for i in items if i["review"] != "excluded"), out_path))
