#!/usr/bin/env python3
"""What the live resource reader does with the tagged releases (RES_V1 baseline, 2026-09-17).

Read-only on portal.db, writes nothing. 642 approved releases carry the Resource Estimates tag and
/resources shows 179 rows; this says where the rest go, so the rebuild starts from a measurement
rather than an impression.
"""
import collections
import re
import sqlite3
import sys

sys.path.insert(0, "/opt/mnt/app")
sys.path.insert(0, "/opt/mnt/app/portal")

from resource_extract import extract_resources, find_project  # noqa: E402

DB = "file:/opt/mnt/app/portal/portal.db?mode=ro"

# wording that means the release really does carry a resource table
HAS_TABLE = re.compile(r"(?i)\b(?:measured|indicated|inferred|proven|probable)\b")
HAS_TONNES = re.compile(r"(?i)\b(?:tonnes|tons|Mt\b|million\s+tonnes)\b")
HAS_GRADE = re.compile(r"(?i)\b(?:g/t|gpt|%\s*(?:cu|zn|pb|ni|li|u3o8)|oz/t)\b")


def main():
    conn = sqlite3.connect(DB, uri=True)
    rows = list(conn.execute(
        "SELECT event_id, ticker, raw_headline, raw_body, published_at, categories FROM events "
        "WHERE review_status='auto_approved' AND categories LIKE '%Resource Estimates%'"))
    live = {r[0] for r in conn.execute("SELECT event_id FROM resource_estimates")}
    print("tagged approved releases:", len(rows))
    print("rows on the page        :", len(live))

    found, missing = {}, []
    ncat = collections.Counter()
    mre = collections.Counter()
    metals = collections.Counter()
    noproj = 0
    for eid, tk, hl, body, pub, cat in rows:
        x = extract_resources(hl or "", body or "")
        cats = x.get("categories") or {}
        if not cats:
            looks_real = bool(HAS_TABLE.search(body or "")) and bool(HAS_TONNES.search(body or "")) \
                and bool(HAS_GRADE.search(body or ""))
            missing.append((tk, (hl or "")[:88], looks_real, len(body or "")))
            continue
        found[eid] = (tk, hl, pub)
        ncat[len(cats)] += 1
        mre[x.get("mre_type")] += 1
        for c in cats.values():
            metals[(c.get("metal") or "?")] += 1
        if not find_project(hl or "", body or ""):
            noproj += 1

    print()
    print("the reader finds a resource table in :", len(found))
    print("  ... and no table at all in         :", len(missing))
    real = [m for m in missing if m[2]]
    print("  of those, the text still carries a category word, tonnes and a grade:", len(real))
    print()
    print("of the", len(found), "with a table:")
    print("  reach the page        :", len(set(found) & live))
    print("  dropped by deduplication:", len(set(found) - live))
    print("  on the page but no table found now:", len(live - set(found)))
    print()
    print("categories per release:", dict(sorted(ncat.items())))
    print("mre_type              :", dict(mre.most_common(8)))
    print("metals                :", dict(metals.most_common(10)))
    print("no project named      :", noproj, "of", len(found))
    print()
    print("--- 12 releases the reader finds nothing in, though the text looks like it has a table")
    for tk, hl, looks, blen in real[:12]:
        print("   %-10s %6d chars  %s" % (tk or "?", blen, hl))
    print()
    print("--- 8 releases the reader finds nothing in and probably has nothing to find")
    for tk, hl, looks, blen in [m for m in missing if not m[2]][:8]:
        print("   %-10s %6d chars  %s" % (tk or "?", blen, hl))
    print()
    dropped = sorted(set(found) - live)
    print("--- 12 releases with a table that deduplication removed")
    for eid in dropped[:12]:
        tk, hl, pub = found[eid]
        print("   %-10s %s  %s" % (tk or "?", (pub or "")[:10], (hl or "")[:80]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
