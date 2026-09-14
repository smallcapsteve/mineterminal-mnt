#!/usr/bin/env python3
"""management_backfill.py — populate management_changes from events.

Unlike the other three backfills this one does NOT select on a category, because
there is no "Management Changes" category to select on. `management_extract` is
the detector: a release is a management change exactly when the extractor can
name a role, and usually a person. It reads headlines only, so a full pass over
18,209 approved releases takes a couple of seconds.

Safe to re-run: DELETE then re-INSERT, same as its siblings.
"""
from __future__ import annotations
import json as _json
import sqlite3
import sys

sys.path.insert(0, "/opt/mnt/app")
sys.path.insert(0, "/opt/mnt/app/portal")

from management_extract import extract  # type: ignore

DB = "/opt/mnt/app/portal/portal.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS management_changes (
    mgmt_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT NOT NULL UNIQUE,
    ticker        TEXT,
    action        TEXT,
    person        TEXT,
    role          TEXT,
    scope         TEXT,
    n_changes     INTEGER,
    changes_json  TEXT,
    raw_headline  TEXT,
    published_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_mgmt_ticker    ON management_changes(ticker);
CREATE INDEX IF NOT EXISTS ix_mgmt_published ON management_changes(published_at);
CREATE INDEX IF NOT EXISTS ix_mgmt_scope     ON management_changes(scope);
"""


def main() -> int:
    con = sqlite3.connect(DB)
    con.execute("PRAGMA busy_timeout = 30000")
    con.executescript(SCHEMA)
    con.commit()

    rows = list(con.execute(
        "SELECT event_id, ticker, raw_headline, published_at FROM events "
        "WHERE review_status='auto_approved' AND raw_headline IS NOT NULL"
    ))
    print(f"[management_backfill] events to scan: {len(rows)}")

    keep = []
    for eid, ticker, hl, pub in rows:
        x = extract(hl or "")
        if not x.get("changes"):
            continue
        keep.append((
            eid, ticker, x["top_action"], x["top_person"], x["top_role"],
            x["top_scope"], len(x["changes"]),
            _json.dumps(x["changes"], ensure_ascii=False),
            (hl or "")[:500], pub,
        ))

    con.execute("DELETE FROM management_changes")
    con.executemany(
        "INSERT INTO management_changes("
        " event_id, ticker, action, person, role, scope, n_changes,"
        " changes_json, raw_headline, published_at"
        ") VALUES (?,?,?,?,?,?,?,?,?,?)", keep)
    con.commit()

    print(f"[management_backfill] inserted: {len(keep)}")
    for label, sql in (
        ("by action", "SELECT action, COUNT(*) FROM management_changes GROUP BY 1 ORDER BY 2 DESC"),
        ("by scope",  "SELECT scope,  COUNT(*) FROM management_changes GROUP BY 1 ORDER BY 2 DESC"),
    ):
        print(f"  {label}: " + ", ".join(f"{a}={b}" for a, b in con.execute(sql)))
    named = con.execute("SELECT COUNT(*) FROM management_changes WHERE person IS NOT NULL").fetchone()[0]
    print(f"  with a named person: {named}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
