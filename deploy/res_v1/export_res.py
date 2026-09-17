#!/usr/bin/env python3
"""Export the resource-estimates corpus so the rebuild can be worked on offline (RES_V1, 2026-09-17).

Read-only on portal.db. Writes one gzipped JSON file to /var/tmp/mnt-res/ and prints its size, its
sha256 and how many chunks it takes to carry back.

Bodies are cut at BODY_CAP and the cap is recorded in the file, because a measurement taken on a
truncated body cannot be compared with one taken on the whole text -- which is exactly what cost an
hour on the management rebuild. The cap is set above the longest release in the corpus (98,939
chars on 2026-09-17), so in practice nothing is cut: the first pass at 16,000 truncated 187 of 642
releases, and resource tables sit as deep as char 14,846.
"""
import gzip
import hashlib
import json
import os
import sqlite3

DB = "file:/opt/mnt/app/portal/portal.db?mode=ro"
OUT = "/var/tmp/mnt-res"
BODY_CAP = 200000
CHUNK = 520000
TAG = "Resource Estimates"


def sha1(headline, body):
    h = hashlib.sha1()
    h.update((headline or "").encode())
    h.update(bytes([0]))
    h.update((body or "").encode())
    return h.hexdigest()


def main():
    os.makedirs(OUT, exist_ok=True)
    c = sqlite3.connect(DB, uri=True)

    tagged = []
    for r in c.execute(
            "SELECT event_id, ticker, published_at, raw_headline, raw_body, categories, source_name "
            "FROM events WHERE review_status='auto_approved' "
            "AND ('|' || COALESCE(categories,'') || '|') LIKE ?", ("%|" + TAG + "|%",)):
        body = r[4] or ""
        tagged.append({"event_id": r[0], "ticker": r[1], "published_at": r[2], "headline": r[3],
                       "body": body[:BODY_CAP], "body_len": len(body), "categories": r[5],
                       "source": r[6], "body_sha1": sha1(r[3], body)})

    # releases the tag did not catch but which talk like a resource estimate: the ceiling check
    control = []
    for r in c.execute(
            "SELECT event_id, ticker, published_at, raw_headline, raw_body, categories, source_name "
            "FROM events WHERE review_status='auto_approved' "
            "AND ('|' || COALESCE(categories,'') || '|') NOT LIKE ? "
            "AND (raw_headline LIKE '%esource Estimate%' OR raw_headline LIKE '%ineral Resource%' "
            "     OR raw_body LIKE '%Indicated Mineral Resource%') "
            "ORDER BY published_at DESC LIMIT 400", ("%|" + TAG + "|%",)):
        body = r[4] or ""
        control.append({"event_id": r[0], "ticker": r[1], "published_at": r[2], "headline": r[3],
                        "body": body[:BODY_CAP], "body_len": len(body), "categories": r[5],
                        "source": r[6], "body_sha1": sha1(r[3], body)})

    cols = [x[1] for x in c.execute("PRAGMA table_info(resource_estimates)")]
    legacy = [dict(zip(cols, r)) for r in c.execute("SELECT * FROM resource_estimates")]

    payload = {"tag": TAG, "body_cap": BODY_CAP, "tagged": tagged, "control": control,
               "legacy_rows": legacy}
    raw = gzip.compress(json.dumps(payload, ensure_ascii=False).encode(), 9)
    open(os.path.join(OUT, "corpus.json.gz"), "wb").write(raw)
    print("tagged", len(tagged), "control", len(control), "legacy rows", len(legacy))
    print("gz bytes", len(raw), "sha256", hashlib.sha256(raw).hexdigest())
    print("chunks of", CHUNK, ":", -(-len(raw) // CHUNK))
    print("cut at cap:", sum(1 for x in tagged + control if x["body_len"] > BODY_CAP))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
