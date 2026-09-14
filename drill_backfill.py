"""drill_backfill.py — create drill_results table + populate from existing events."""
from __future__ import annotations
import sqlite3
import sys

sys.path.insert(0, "/opt/mnt/app")
sys.path.insert(0, "/opt/mnt/app/portal")

from drill_extract import extract, score_intercept, format_intercept  # type: ignore

DB = "/opt/mnt/app/portal/portal.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS drill_results (
    drill_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT NOT NULL UNIQUE,
    ticker        TEXT,
    project       TEXT,
    top_hole_id   TEXT,
    top_grade     REAL,
    top_unit      TEXT,
    top_metal     TEXT,
    top_length_m  REAL,
    top_summary   TEXT,
    n_intercepts  INTEGER,
    raw_headline  TEXT,
    published_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_drill_ticker      ON drill_results(ticker);
CREATE INDEX IF NOT EXISTS ix_drill_published   ON drill_results(published_at);
CREATE INDEX IF NOT EXISTS ix_drill_topscore    ON drill_results(top_grade, top_length_m);
"""


def main() -> int:
    con = sqlite3.connect(DB); con.execute("PRAGMA busy_timeout = 30000")
    con.executescript(SCHEMA)
    con.commit()
    con.execute("DELETE FROM drill_results")
    con.commit()

    # Oldest first, so the release that FIRST reported an intercept keeps it.
    rows = list(con.execute(
        "SELECT event_id, ticker, raw_headline, raw_body, published_at "
        "FROM events WHERE categories LIKE ? AND review_status='auto_approved' "
        "ORDER BY COALESCE(published_at, '') ASC, event_id ASC",
        ("%Drill Results%",),
    ))
    print(f"[drill_backfill] events to scan: {len(rows)}")

    inserted = no_intercept = all_repeats = 0
    seen_by_ticker = {}
    cur = con.cursor()
    for r in rows:
        eid, ticker, hl, body, pub = r
        x = extract(hl or "", body or "")
        if not x.get("intercepts"):
            no_intercept += 1
            continue

        seen = seen_by_ticker.setdefault(ticker or "", set())
        fresh = [it for it in x["intercepts"]
                 if (round(it["length_m"], 1), round(it["grade"], 2), it["metal"]) not in seen]
        if not fresh:
            # every number here has already been reported by this company:
            # a recap, not new results
            all_repeats += 1
            continue
        for it in fresh:
            seen.add((round(it["length_m"], 1), round(it["grade"], 2), it["metal"]))

        fresh.sort(key=score_intercept, reverse=True)
        top = fresh[0]
        x = dict(x)
        x["intercepts"] = fresh
        x["top_grade"] = top.get("grade")
        x["top_length_m"] = top.get("length_m")
        x["top_unit"] = top.get("unit")
        x["top_metal"] = top.get("metal")
        x["top_summary"] = format_intercept(top)

        cur.execute(
            "INSERT INTO drill_results("
            " event_id, ticker, project, top_hole_id, top_grade, top_unit, top_metal,"
            " top_length_m, top_summary, n_intercepts, raw_headline, published_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                eid, ticker, x.get("project"), x.get("top_hole_id"),
                x.get("top_grade"), x.get("top_unit"), x.get("top_metal"),
                x.get("top_length_m"), x.get("top_summary"),
                len(x.get("intercepts") or []),
                (hl or "")[:500], pub,
            ),
        )
        inserted += 1
    con.commit()

    print(f"[drill_backfill] inserted: {inserted}")
    print(f"[drill_backfill] skipped (no intercept): {no_intercept}")
    print(f"[drill_backfill] skipped (only repeats of earlier intercepts): {all_repeats}")

    print("\n=== top 10 by grade*length ===")
    for r in con.execute(
        "SELECT ticker, top_summary, project, top_hole_id, raw_headline, published_at "
        "FROM drill_results "
        "ORDER BY (top_grade * top_length_m) DESC LIMIT 10"
    ):
        print(" ", dict(r) if hasattr(r, "keys") else r)

    return 0


if __name__ == "__main__":
    sys.exit(main())
