#!/usr/bin/env python3
"""Build accuracy/sets/economics.json from the confirmed labels (ECON_SET_V1, 2026-09-21).

  build_econ_set.py LABELS OUT [--db PATH]

Reads portal.db READ-ONLY. For each labelled release it resolves the label's 12-character id to the
live 64-character event_id by prefix (exactly one match or it refuses), and stores the body_sha1 the
gate checks, computed with portal.facts.text_sha1 over the LIVE raw_headline and raw_body -- never a
hash of a working extract, which is how the Resource Estimates set once went stale on all 50 items.

Every item is reviewed: 'confirmed' where the label stands as Justin confirmed it on 2026-09-20,
'corrected' where a later correction changed it (the set's own `corrections` block says which, why,
and on whose word).
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

corrected = set()
for c in lab.get("corrections") or []:
    for eid in (c.get("evidence") or {}):
        corrected.add(eid)
    for m in (c.get("moved") or []):
        corrected.add(m.split()[1])
    txt = c.get("effect") or ""
    for it in lab["items"]:
        if it["event_id"] in txt:
            corrected.add(it["event_id"])

items, problems = [], []
for n, it in enumerate(lab["items"], 1):
    rs = conn.execute("SELECT event_id, raw_headline, raw_body FROM events WHERE event_id LIKE ?",
                      (it["event_id"] + "%",)).fetchall()
    if len(rs) != 1:
        problems.append("%s: %d matches" % (it["event_id"], len(rs)))
        continue
    full, hl, body = rs[0]
    rows = it.get("rows") or []
    items.append({
        "n": n, "event_id": full, "ticker": it["ticker"], "stratum": it.get("stratum"),
        "body_sha1": facts.text_sha1(hl, body),
        "review": "corrected" if it["event_id"] in corrected else "confirmed",
        "note": it.get("note"),
        "expect": {"is_economic_study": bool(rows), "complete": it.get("complete", True), "rows": rows}})
if problems:
    raise SystemExit("REFUSED: " + "; ".join(problems))

aset = {"schema": 1, "name": "economics", "tag": "Economic Studies", "status": "confirmed",
        "created": lab.get("created"), "reviewer": lab.get("reviewer"), "reviewed_at": lab.get("reviewed_at"),
        "rules": lab.get("rules"), "row_shape": lab.get("row_shape"), "corrections": lab.get("corrections"),
        "items": items}
json.dump(aset, open(out_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("economics set: %d items, %d rows, %d corrected -> %s" % (
    len(items), sum(len(i["expect"]["rows"]) for i in items),
    sum(1 for i in items if i["review"] == "corrected"), out_path))
