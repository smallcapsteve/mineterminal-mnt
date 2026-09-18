#!/usr/bin/env python3
"""Turn the RES_V1 draft-2 labels into accuracy/sets/resources.json (2026-09-18).

The label file carries 12-character event ids and no body hash, because it was written off the
droplet from an extract. The accuracy set needs the full event id and the sha1 of the body the label
was written against, so that a set silently scoring a re-ingested body is caught. Both come from the
corpus here, which is why this runs on the box.

Shape follows accuracy/sets/management.json, which portal/accuracy.py already knows how to read.

Usage: build_res_set.py <labels.json> <out.json>
"""
import gzip
import hashlib
import json
import sys

CORPUS = "/var/tmp/mnt-res/corpus.json.gz"
SAMPLE = "/var/tmp/mnt-res/sample.json"

ROW_FIELDS = ("deposit", "category", "tonnes", "grades", "contained", "cut_off", "basis", "context")


def main(argv):
    labels = json.load(open(argv[0], encoding="utf-8"))
    out_path = argv[1]
    corpus = json.loads(gzip.open(CORPUS, "rb").read().decode())
    by_full = {r["event_id"]: r for r in corpus["tagged"]}
    by_short = {}
    for eid, r in by_full.items():
        by_short.setdefault(eid[:12], []).append(eid)

    sample = json.load(open(SAMPLE, encoding="utf-8"))
    strata = sample.get("strata") or {}

    items, missing, ambiguous = [], [], []
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
        rel = by_full[eid]
        rows = []
        for r in lab["rows"]:
            rows.append({k: r.get(k) for k in ROW_FIELDS})
        items.append({
            "n": n,
            "event_id": eid,
            "ticker": lab["ticker"],
            "published_at": rel.get("published_at"),
            "stratum": strata.get(eid) or strata.get(short) or lab.get("stratum") or "sample",
            "body_sha1": hashlib.sha1((rel.get("body") or "").encode("utf-8")).hexdigest(),
            "review": "confirmed",
            "expect": {
                "is_resource_estimate": bool(lab["estimate"]),
                "mre_type": lab.get("mre_type"),
                "complete": bool(lab.get("complete")),
                "rows": rows,
                "confidence": lab.get("confidence"),
            },
            "note": lab.get("note") or "",
        })

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
                         "rather than counted wrong, and they are left out of recall entirely.",
        "notes_live_in": "claude/MNT_RES_SET_LABELS_DRAFT_2026-09-17.json in the project, and the "
                         "corrections in claude/MNT_RES_V1_BUILD_2026-09-18.md",
        "items": items,
    }
    blob = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(blob + "\n")
    print("items %d   missing %d %s   ambiguous %d %s"
          % (len(items), len(missing), missing[:5], len(ambiguous), ambiguous[:5]))
    print("rows labelled %d   items stating figures %d   partial %d"
          % (sum(len(i["expect"]["rows"]) for i in items),
             sum(1 for i in items if i["expect"]["is_resource_estimate"]),
             sum(1 for i in items if not i["expect"]["complete"])))
    print("%s bytes %d sha256 %s"
          % (out_path, len(blob) + 1, hashlib.sha256((blob + "\n").encode("utf-8")).hexdigest()))
    return 0 if not missing and not ambiguous else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
