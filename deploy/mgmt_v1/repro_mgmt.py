#!/usr/bin/env python3
"""Reproduce the workspace measurement of MGMT_V1 1.0.0 on the droplet, in memory (MGMT_V1, 2026-09-17).

Run from the candidate tree. Reads portal.db read-only and writes nothing:

  1. the accuracy set loads, is usable for a gate, and carries the expected set_sha
  2. the candidate reader, scored against that set through the management spec
  3. the same fingerprint the workspace computed over every tagged release, so a file that
     travelled badly is caught before anything is installed

Two things have to match for the fingerprint to mean anything. The releases are those
published up to CUTOFF, the moment the workspace exported its copy of the corpus; anything
ingested since is real news, not a difference in the reader. And the text is cut at BODY_CAP,
because that is how much of each release the workspace copy held. The live reader reads more.
"""
import hashlib
import json
import sqlite3
import sys

sys.path.insert(0, ".")

from portal import accuracy as A            # noqa: E402
from portal.extractors import management as X   # noqa: E402

DB = "file:/opt/mnt/app/portal/portal.db?mode=ro"
WORKSPACE_SET_SHA = "0b60368fc2458bb3fbffa4d750c9bc2b89925937fa94af146996ba163c99f8a0"
WORKSPACE_CORPUS_SHA = "6c9bc39912eecd9e76f467ae9f288c29cab0777b5b503a315990dc268968546d"
WORKSPACE_RELEASES = 3107
CUTOFF = "2026-09-17T13:00:00"
BODY_CAP = 4000


def main():
    conn = sqlite3.connect(DB, uri=True)
    conn.row_factory = sqlite3.Row
    aset = A.load_set("accuracy/sets/management.json")
    print("set_sha       ", A.set_sha(aset), "MATCH" if A.set_sha(aset) == WORKSPACE_SET_SHA else "DIFFERENT")
    print("set usable    ", A.set_usable(aset))

    spec = A.SPECS["management"]
    events = A.load_events(conn, aset)
    rep = A.evaluate(spec, aset, lambda it, ev: spec.from_records(
        X.SPEC.extract(ev["raw_headline"] or "", ev["raw_body"] or "")), events)
    print("scored %d, stale %d, missing %d, errors %d"
          % (rep["n_scored"], rep["n_stale"], rep["n_missing"], rep["n_errors"]))
    for f, v in rep["fields"].items():
        print("  %-8s tp %3d  fp %3d  fn %3d   precision %s  recall %s"
              % (f, v["tp"], v["fp"], v["fn"], v["precision"], v["recall"]))

    parts = []
    for r in conn.execute("SELECT event_id, raw_headline, raw_body FROM events "
                          "WHERE review_status='auto_approved' "
                          "AND ('|' || COALESCE(categories,'') || '|') LIKE '%|Management Changes|%' "
                          "AND published_at <= ?", (CUTOFF,)):
        a = X.analyse(r[1] or "", (r[2] or "")[:BODY_CAP])
        parts.append(str(r[0]) + ":" + hashlib.sha1(
            json.dumps(a["changes"], sort_keys=True, ensure_ascii=False).encode()).hexdigest())
    parts.sort()
    got = hashlib.sha256("\n".join(parts).encode()).hexdigest()
    ok = got == WORKSPACE_CORPUS_SHA and len(parts) == WORKSPACE_RELEASES
    print("corpus        ", len(parts), "releases up to", CUTOFF, "fingerprint", got,
          "MATCH" if ok else "DIFFERENT from the workspace")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
