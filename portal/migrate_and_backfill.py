"""
Idempotent migration + backfill for news-release categorizer.

- Ensures `categories TEXT` column + index on events table.
- Computes categories for every event with NULL categories using
  categorize(raw_headline, raw_body | raw_excerpt) from portal.categorize.
- Prints per-category distribution at the end.

Safe to re-run.
"""
from __future__ import annotations
import os
import sqlite3
import sys
import time

DB_PATH = os.environ.get("MNT_PORTAL_DB", "/opt/mnt/app/portal/portal.db")

sys.path.insert(0, "/opt/mnt/app")
from portal.categorize import categorize, format_categories, CATEGORIES  # noqa: E402


def ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(events)")
    cols = {r[1] for r in cur.fetchall()}
    if "categories" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN categories TEXT")
        conn.commit()
        print("[migrate] added categories column", flush=True)
    else:
        print("[migrate] categories column already present", flush=True)
    # Index (idempotent)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_categories ON events(categories)")
    conn.commit()


def backfill(conn: sqlite3.Connection, only_null: bool = True) -> int:
    if only_null:
        q = ("SELECT event_id, raw_headline, raw_body, raw_excerpt "
             "FROM events WHERE categories IS NULL OR categories = ''")
    else:
        q = ("SELECT event_id, raw_headline, raw_body, raw_excerpt FROM events")

    rows = conn.execute(q).fetchall()
    print(f"[backfill] rows to process: {len(rows)}", flush=True)
    updated = 0
    t0 = time.time()
    for i, (event_id, headline, body, excerpt) in enumerate(rows):
        text = body or excerpt or ""
        cats = categorize(headline, text)
        val = format_categories(cats) or ""
        conn.execute("UPDATE events SET categories = ? WHERE event_id = ?", (val, event_id))
        updated += 1
        if (i + 1) % 500 == 0:
            conn.commit()
            print(f"  ... {i+1}/{len(rows)} ({(time.time()-t0):.1f}s)", flush=True)
    conn.commit()
    print(f"[backfill] committed {updated} rows in {time.time()-t0:.1f}s", flush=True)
    return updated


def print_distribution(conn: sqlite3.Connection) -> None:
    total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    uncat = conn.execute(
        "SELECT COUNT(*) FROM events WHERE categories IS NULL OR categories = ''"
    ).fetchone()[0]
    print(f"[dist] total events: {total}, uncategorized: {uncat}", flush=True)
    for name in CATEGORIES:
        # Each event stores pipe-delimited names; use 4-pattern match.
        n = conn.execute(
            "SELECT COUNT(*) FROM events WHERE "
            "categories = ? OR categories LIKE ? OR categories LIKE ? OR categories LIKE ?",
            (name, f"{name}|%", f"%|{name}", f"%|{name}|%"),
        ).fetchone()[0]
        print(f"  {name:<32s} {n:>6d}", flush=True)


def main() -> int:
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}", file=sys.stderr)
        return 2
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_schema(conn)
    backfill(conn, only_null=True)
    print_distribution(conn)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
