"""MNT_ROWS_AI_LIVE_V1 (2026-10-26): where /permits-approvals, /exploration-programs, /sampling-geoscience and their
APIs (/api/v1/permits, /api/v1/exploration, /api/v1/sampling) read their rows.

While Permits, Exploration and Sampling are switched to the AI reader (plan: claude/AIREADER_HYBRID_PLAN_2026-10-22.md;
Justin 2026-10-26), /opt/mnt-rowslive/rows_live.py writes the hybrid rows hourly to
/var/lib/mnt-aireader-pub/rows_live.db: tables permits, exploration_programs and sampling_results with the live
tables' columns plus
  ai_label   agreed | AI-read (only the AI found the row) | rules (not read by the AI yet) | NULL (marker row)
  withheld   figures left blank because the readers disagree.
The pages and APIs read that file while it exists and was built in the last 12 hours; otherwise portal.db exactly as
before. /api/v1/feed-versions folds the file's build time into those tables' versions so Mine Terminal Pro refreshes.

Undo, instantly: systemctl disable --now aireader-rows-live.timer; rm /var/lib/mnt-aireader-pub/rows_live.db
(the next request reads the rules tables)."""
import calendar
import logging
import os
import sqlite3
import time

LIVE_DB = os.environ.get("MNT_ROWS_LIVE_DB", "/var/lib/mnt-aireader-pub/rows_live.db")
TABLES = ("permits", "exploration_programs", "sampling_results")
MAX_AGE_S = 12 * 3600
log = logging.getLogger(__name__)


def _built_epoch(c):
    r = c.execute("SELECT v FROM preview_meta WHERE k='rows_built_at'").fetchone()
    return calendar.timegm(time.strptime(r[0], "%Y-%m-%dT%H:%M:%SZ")) if r and r[0] else None


def ai_conn(table):
    """A read-only connection to the hybrid file holding `table`, or None (no file, not fresh, or unreadable)."""
    if table not in TABLES or not os.path.exists(LIVE_DB):
        return None
    c = None
    try:
        c = sqlite3.connect("file:%s?mode=ro" % LIVE_DB, uri=True, timeout=5)
        c.row_factory = sqlite3.Row
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
            c.close()
            return None
        b = _built_epoch(c)
        if b is None or time.time() - b > MAX_AGE_S:
            c.close()
            return None
        return c
    except Exception:  # noqa: BLE001 - any trouble with the file: serve the rules table
        log.exception("rows_source: live AI file unreadable")
        if c is not None:
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
        return None


def ai_cols(conn, table):
    """', ai_label' when the connection is the hybrid file (its table has the column), else ''."""
    try:
        return ", ai_label" if any(r[1] == "ai_label" for r in conn.execute("PRAGMA table_info(%s)" % table)) else ""
    except Exception:  # noqa: BLE001
        return ""


def fold_version(tables):
    """/api/v1/feed-versions: while the hybrid file is in use, its tables' versions also change with each rebuild."""
    try:
        c = ai_conn("permits")
        if c is None:
            return tables
        try:
            b = _built_epoch(c)
        finally:
            c.close()
        out = dict(tables)
        for t in TABLES:
            md = out.get(t)
            if md is None:
                continue
            out[t] = {"v": int(md["v"]) * 100000 + int(b // 60) % 100000,
                      "changed_at": max(str(md.get("changed_at") or ""), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(b)))}
        return out
    except Exception:  # noqa: BLE001
        log.exception("rows_source: fold_version")
        return tables
