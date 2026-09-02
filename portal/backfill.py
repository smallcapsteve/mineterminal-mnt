from __future__ import annotations
import json
import logging
from pathlib import Path

from portal import db

log = logging.getLogger("portal.backfill")

EVENT_DIRS = [
    Path("/opt/mnt/app/data/events/auto"),
    Path("/opt/mnt/app/data/events/pending"),
]


def _row_from_envelope(env: dict) -> dict:
    # payload may be a complex dict; serialize it
    payload = env.get("payload")
    if payload is not None and not isinstance(payload, str):
        try:
            payload = json.dumps(payload, default=str)
        except Exception:
            payload = None
    return {
        "event_id":               env.get("event_id"),
        "event_type":             env.get("event_type"),
        "ticker":                 env.get("ticker"),
        "company_id":             env.get("company_id"),
        "property_id":            env.get("property_id"),
        "source_url":             env.get("source_url"),
        "source_name":            env.get("source_name"),
        "published_at":           env.get("published_at"),
        "classified_at":          env.get("classified_at"),
        "classifier_model":       env.get("classifier_model"),
        "classifier_confidence":  env.get("classifier_confidence"),
        "review_status":          env.get("review_status"),
        "raw_headline":           env.get("raw_headline"),
        "raw_excerpt":            env.get("raw_excerpt"),
        "raw_body":               env.get("raw_body"),
        "raw_html":               env.get("raw_html"),
        "payload_json":           payload,
    }


def run(force: bool = False) -> int:
    db.init_schema()
    existing = db.count_events()
    if existing and not force:
        log.info("backfill skipped; %d events already present", existing)
        return 0
    n = 0
    for d in EVENT_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                env = json.loads(p.read_text())
            except Exception:
                log.warning("skipped unparseable file: %s", p)
                continue
            row = _row_from_envelope(env)
            if not row["event_id"]:
                continue
            db.upsert_event(row)
            n += 1
    log.info("backfill wrote %d events", n)
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    force = "--force" in sys.argv
    print("backfilled:", run(force=force))
