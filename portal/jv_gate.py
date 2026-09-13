#!/usr/bin/env python3
"""_JV_GATE (2026-09-13) — tag a co-issued release with its partner at ingest.

Installed by portal/__init__.py alongside the universe gate, and for the same
reason: every collector imports portal.db, so one wrapper here covers the wire
firehose, the per-company adapters and the exchange path at once, including
collectors that do not exist yet.

Why this is a second write rather than a field on the row: `portal.db`'s
`upsert_event` has a fixed column list and `additional_tickers` is not in it,
and its `ON CONFLICT DO UPDATE` only assigns the columns in that list. That is
actually the behaviour we want — a tag applied by hand in the admin screen
survives the event being re-upserted by a later run — so rather than widen the
column list, this wraps the call and writes the tag afterwards.

**It only ever fills an empty field.** If an event already carries additional
tickers, from the admin screen or from `jv_tag.py --apply`, this leaves them
alone. A person's judgement outranks the matcher.

Fail-open, like the universe gate: any failure to work out the partners, or to
write them, is swallowed. A release must still be collected even if it cannot
be cross-filed.
"""
from __future__ import annotations

import logging
import sys

if "/opt/mnt/app" not in sys.path:
    sys.path.insert(0, "/opt/mnt/app")

log = logging.getLogger("jv.gate")


def install() -> None:
    """Wrap portal.db.upsert_event. Idempotent."""
    from portal import db

    if getattr(db, "_jv_gate_installed", False):
        return

    _inner = db.upsert_event

    def upsert_event(row):
        result = _inner(row)
        try:
            import jv_tag
            partners = jv_tag.tags_for(row.get("raw_headline") or "",
                                       row.get("ticker") or "")
            if partners:
                eid = row.get("event_id")
                if eid:
                    c = db.get_conn()
                    # Only fill an empty field, and only if the row is really
                    # there — the fuzzy-dupe guard upstream may have skipped it.
                    cur = c.execute(
                        "UPDATE events SET additional_tickers=? "
                        "WHERE event_id=? AND COALESCE(additional_tickers,'')=''",
                        (jv_tag.pipe(partners), eid))
                    if cur.rowcount:
                        c.commit()
                        log.info("jv gate: %s also filed under %s",
                                 row.get("ticker"), ",".join(partners))
        except Exception as e:                   # noqa: BLE001
            log.warning("jv gate: could not tag %s (%s)", row.get("ticker"), e)
        return result

    db.upsert_event = upsert_event
    db._jv_gate_installed = True
    log.info("jv gate: installed")
