#!/usr/bin/env python3
"""facts_sync.py: incremental extraction into the facts store (FACTS_V1, 2026-09-16).

Timer mode (no arguments; called by sync_structured.py every 30 minutes):
  for each extractor in portal.extractors.REGISTRY, process approved events its
  current version has not seen, newest first, at most --limit (default 2000)
  per extractor per run. With an empty registry it only confirms the schema.

Backfill mode (--backfill NAME): process every pending event for that
extractor, 500 events per read, 200 per write transaction. A full run over
the corpus belongs under systemd-run, never inside the timer:
  systemd-run --unit fx-backfill-NAME -p User=mnt -p WorkingDirectory=/opt/mnt/app /opt/mnt/app/.venv/bin/python3 /opt/mnt/app/facts_sync.py --backfill NAME

Never activates a version. Activation is a separate, gated step.
"""
import argparse
import sys
import time

sys.path.insert(0, "/opt/mnt/app")

from portal import facts  # noqa: E402
from portal.extractors import REGISTRY  # noqa: E402

DB = "/opt/mnt/app/portal/portal.db"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", metavar="NAME")
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--since", help="only events published on/after YYYY-MM-DD")
    ap.add_argument("--db", default=DB)
    args = ap.parse_args(argv)

    conn = facts.connect(args.db)
    facts.ensure_schema(conn)
    specs = [s for s in REGISTRY if not args.backfill or s.name == args.backfill]
    if args.backfill and not specs:
        print(f"[facts_sync] no registered extractor named {args.backfill!r}")
        return 2
    if not specs:
        print("[facts_sync] schema ok; no extractors registered")
        return 0

    rc = 0
    for spec in specs:
        t0 = time.time()
        total = {"events": 0, "records": 0, "errors": 0, "max_txn_ms": 0.0}
        remaining = None if args.backfill else args.limit
        while True:
            page = 500 if remaining is None else min(500, remaining)
            if page <= 0:
                break
            events = facts.pending_events(conn, spec.name, spec.version, limit=page, since=args.since)
            if not events:
                break
            c = facts.run_batch(conn, spec, events, batch=200)
            if c["skipped"]:
                print(f"[facts_sync] {spec.name} {spec.version} is {c['skipped']}; skipped (roll the registry back too)")
                break
            for k in ("events", "records", "errors"):
                total[k] += c[k]
            total["max_txn_ms"] = max(total["max_txn_ms"], c["max_txn_ms"])
            if remaining is not None:
                remaining -= len(events)
            if args.backfill:
                print(f"[facts_sync] {spec.name} {spec.version}: {total['events']} events so far", flush=True)
        st = facts.stats(conn, spec.name, spec.version)
        status = facts.version_status(conn, spec.name, spec.version)
        print(f"[facts_sync] {spec.name} {spec.version} ({status}): +{total['events']} events, "
              f"+{total['records']} records, {total['errors']} errors, longest write {total['max_txn_ms']} ms, "
              f"{time.time() - t0:.1f}s | totals: {st['runs']} runs, {st['records']} records, "
              f"in-tag coverage {st['coverage_in_tag']}, fired outside tag {st['fired_untagged']}")
        if total["errors"]:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
