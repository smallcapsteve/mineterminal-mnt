#!/usr/bin/env python3
"""Turn the RES_V1 draft-2 labels into accuracy/sets/resources.json (2026-09-18).

The label file carries 12-character event ids and no body hash, because it was written off the
droplet from an extract. The set needs the full event id and the hash the accuracy framework uses
to detect a re-ingested body, which is facts.text_sha1(raw_headline, raw_body) over the LIVE events
table -- not a hash of the extract. The first version of this script hashed the extract's body
alone, and the gate refused the version with all 50 items stale, which is exactly what that check
is for.

Shape follows accuracy/sets/management.json, which portal/accuracy.py already knows how to read.

Usage: build_res_set.py <labels.json> <out.json>
"""
import hashlib
import json
import sqlite3
import sys

sys.path.insert(0, "/opt/mnt/app")

from portal import facts as F  # noqa: E402

DB = "file:/opt/mnt/app/portal/portal.db?mode=ro"
SAMPLE = "/var/tmp/mnt-res/sample.json"

ROW_FIELDS = ("deposit", "category", "tonnes", "grades", "contained", "cut_off", "basis", "context")


def main(argv):
    labels = json.load(open(argv[0], encoding="utf-8"))
    out_path = argv[1]
    conn = sqlite3.connect(DB, uri=True)

    sample = json.load(open(SAMPLE, encoding="utf-8"))
    by_short = {}
    for eid in sample["event_ids"]:
        by_short.setdefault(eid[:12], []).append(eid)

    items, missing, ambiguous, absent = [], [], [], []
    for n, lab in enumerate(labels["items"]):
        short = lab["event_id"]
        full = by_short.get(short) or []
        if not full:
            missing.append(short)
            continue
        if len(full) > 1:
            ambiguous.append(short)
            continue
        eid = full[0]
        row = conn.execute("SELECT ticker, published_at, raw_headline, raw_body, review_status, "
                           "categories FROM events WHERE event_id=?", (eid,)).fetchone()
        if row is None:
            absent.append(eid[:12])
            continue
        ticker, published_at, headline, body, review_status, categories = row
        items.append({
            "n": n,
            "event_id": eid,
            "ticker": lab["ticker"],
            "published_at": published_at,
            "stratum": lab.get("stratum") or "sample",
            "body_sha1": F.text_sha1(headline, body),
            "review": "confirmed",
            "expect": {
                "is_resource_estimate": bool(lab["estimate"]),
                "mre_type": lab.get("mre_type"),
                "complete": bool(lab.get("complete")),
                "rows": [{k: r.get(k) for k in ROW_FIELDS} for r in lab["rows"]],
                "confidence": lab.get("confidence"),
            },
            "note": lab.get("note") or "",
        })
        if review_status != "auto_approved":
            print("  NOTE %s %s is %s, not auto_approved" % (eid[:12], lab["ticker"], review_status))
        if "Resource Estimates" not in (categories or ""):
            print("  NOTE %s %s no longer carries the tag: %r" % (eid[:12], lab["ticker"], categories))

    doc = {
        "schema": 1,
        "name": "resources",
        "tag": "Resource Estimates",
        "status": "confirmed",
        "created": "2026-09-18",
        "drafted_by": "Claude, from the headline and body of each release without extractor output; "
                      "guide claude/MNT_RES_LABEL_GUIDE_2026-09-17.md",
        "reviewer": "Justin",
        "reviewed_at": "2026-09-18",
        "review_process": "Justin set the row shape (one row per deposit per category), the scope "
                          "(publish every figure, mark the ones that are background) and the deposit "
                          "naming rule (project, zone, scenario). Two labels were found wrong while "
                          "measuring and corrected as draft-2, both flagged low-confidence and "
                          "partial when drafted: Greenland Mines' Sarfartoq underground scenario, "
                          "and Patriot's CV5+CV13 and Rigel-and-Vega figures, which were crossed.",
        "sampling": "50 of the 642 releases carrying the Resource Estimates tag, stratified by the "
                    "six shapes a resource release takes (table, wide table, row line, prose, "
                    "headline only, no figures at all); 25 of the 50 state no figures, which is the "
                    "proportion in the tag.",
        "row_shape": "one row per deposit per category (Justin, 2026-09-18)",
        "partial_items": "14 of 50 items have complete=false: their row list is known to be "
                         "incomplete, so unmatched predicted rows are set aside as unjudgeable "
                         "rather than counted wrong, and they are left out of recall entirely. The "
                         "reported field row_complete repeats the row score over the 36 fully "
                         "labelled items alone, where recall is honest as well as precision.",
        "notes_live_in": "claude/MNT_RES_SET_LABELS_DRAFT_2026-09-17.json in the project, and the "
                         "corrections in claude/MNT_RES_V1_BUILD_2026-09-18.md",
        "items": items,
    }
    blob = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(blob + "\n")
    print("items %d   missing %d %s   ambiguous %d %s   not in events %d %s"
          % (len(items), len(missing), missing[:5], len(ambiguous), ambiguous[:5],
             len(absent), absent[:5]))
    print("rows labelled %d   items stating figures %d   partial %d"
          % (sum(len(i["expect"]["rows"]) for i in items),
             sum(1 for i in items if i["expect"]["is_resource_estimate"]),
             sum(1 for i in items if not i["expect"]["complete"])))
    print("%s bytes %d sha256 %s"
          % (out_path, len(blob) + 1, hashlib.sha256((blob + "\n").encode("utf-8")).hexdigest()))
    return 0 if not (missing or ambiguous or absent) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
