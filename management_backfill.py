#!/usr/bin/env python3
"""management_backfill.py (v9) — populate management_changes from events.

The /management-changes page and the Management Changes chip used to disagree
(2,068 page rows vs 2,534 tagged releases; 3,088 under v7 tags) because the
page was built by management_extract alone, over every approved headline, while
the chip is built by the categoriser, which also accepts leadership headlines
that name nobody ("Announces Leadership Transition", "Strengthens Board").

v9 makes the page follow the tag:

  1. every approved release where extract() parses a change gets a row, exactly
     as before (the categoriser delegates to extract(), so these are tagged, or
     will be the next time the categoriser runs);
  2. every approved release TAGGED Management Changes that extract() cannot
     parse gets a person-less row from infer_from_tag(): action and scope read
     from the headline's words, person NULL, "inferred": true in changes_json;
  3. a tagged release whose headline carries no management evidence at all
     ("News release", "Board Approval of 2026 Budget", "Appoints Stantec to
     Progress PEA") gets NO row. Those are categoriser false positives; the
     count is printed so they can be fixed at the tag.

Schema is unchanged. Safe to re-run: DELETE then re-INSERT, same as siblings.
"""
from __future__ import annotations
import json as _json
import sqlite3
import sys

sys.path.insert(0, "/opt/mnt/app")
sys.path.insert(0, "/opt/mnt/app/portal")

DB = "/opt/mnt/app/portal/portal.db"
TAG = "Management Changes"

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


def is_tagged(categories: str | None) -> bool:
    return TAG in [c.strip() for c in (categories or "").split("|")]


def build_rows(events, extract, infer_from_tag):
    """events: iterable of (event_id, ticker, raw_headline, published_at, categories).

    Returns (rows, stats). Pure: measure.py runs this exact function over the
    offline corpus, so the numbers it reports are the numbers this script writes.
    """
    rows = []
    stats = {"scanned": 0, "parsed_tagged": 0, "parsed_untagged": 0,
             "inferred": 0, "tagged_no_evidence": 0, "tagged_no_evidence_ids": []}
    for eid, ticker, hl, pub, cats in events:
        stats["scanned"] += 1
        tagged = is_tagged(cats)
        x = extract(hl or "")
        changes = x.get("changes") or []
        if changes:
            stats["parsed_tagged" if tagged else "parsed_untagged"] += 1
            top = (x["top_action"], x["top_person"], x["top_role"], x["top_scope"])
        elif tagged:
            y = infer_from_tag(hl or "")
            if not y:
                stats["tagged_no_evidence"] += 1
                stats["tagged_no_evidence_ids"].append(eid)
                continue
            stats["inferred"] += 1
            changes = [dict(y, inferred=True)]
            top = (y["action"], None, y["role"], y["scope"])
        else:
            continue
        rows.append((eid, ticker, top[0], top[1], top[2], top[3], len(changes),
                     _json.dumps(changes, ensure_ascii=False), (hl or "")[:500], pub))
    return rows, stats


def main() -> int:
    from management_extract import extract, infer_from_tag  # type: ignore

    con = sqlite3.connect(DB)
    con.execute("PRAGMA busy_timeout = 30000")
    con.executescript(SCHEMA)
    con.commit()

    events = list(con.execute(
        "SELECT event_id, ticker, raw_headline, published_at, categories FROM events "
        "WHERE review_status='auto_approved' AND raw_headline IS NOT NULL"
    ))
    rows, st = build_rows(events, extract, infer_from_tag)

    con.execute("DELETE FROM management_changes")
    con.executemany(
        "INSERT INTO management_changes("
        " event_id, ticker, action, person, role, scope, n_changes,"
        " changes_json, raw_headline, published_at"
        ") VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()

    print(f"[management_backfill] events scanned: {st['scanned']}")
    print(f"[management_backfill] inserted: {len(rows)}  "
          f"(parsed+tagged {st['parsed_tagged']}, parsed+untagged "
          f"{st['parsed_untagged']}, inferred from tag {st['inferred']})")
    print(f"[management_backfill] tagged but no management evidence (no row, "
          f"categoriser false positive?): {st['tagged_no_evidence']}")
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
