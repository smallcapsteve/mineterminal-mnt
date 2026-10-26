"""MNT_DEV_AI_LIVE_V1 (2026-10-26): where /mine-development and /api/v1/mine-development read their rows.

While Mine Development is switched to the AI reader (`python -m aireader switch dev show` on the server; plan:
claude/AIREADER_HYBRID_PLAN_2026-10-22.md, approved preview 2026-10-26), the AI harness writes the hybrid rows every
30 minutes to /var/lib/mnt-aireader-pub/site_live.db: a table named mine_dev_events with the live table's columns plus
  ai_label   "agreed" (both readers found the event), "AI-read" (only the AI found it), "rules" (the AI has not read
             the release yet, or a rules marker row: the rules' row as before)
  withheld   figures left blank because the readers disagree.
The page and the API read that file while it exists and was built in the last 12 hours; otherwise they read portal.db's
mine_dev_events exactly as before. /api/v1/feed-versions folds the file's build time into mine_dev_events' version so
Mine Terminal Pro refreshes its copy when the file changes.

Undo, instantly: `python -m aireader switch dev shadow` (removes the file; the next request reads the rules table).
Remove entirely: the backup folder named in the install output holds app.py, mine_dev_api.py, feedver_api.py and the
template as they were."""
import calendar
import logging
import os
import sqlite3
import time

LIVE_DB = os.environ.get("MNT_AI_LIVE_DB", "/var/lib/mnt-aireader-pub/site_live.db")
MAX_AGE_S = 12 * 3600
log = logging.getLogger(__name__)


def _built_epoch(c):
    r = c.execute("SELECT v FROM preview_meta WHERE k='dev_built_at'").fetchone()
    return calendar.timegm(time.strptime(r[0], "%Y-%m-%dT%H:%M:%SZ")) if r and r[0] else None


def ai_conn():
    """A read-only connection to the live AI file, or None (no file, not fresh, or unreadable)."""
    if not os.path.exists(LIVE_DB):
        return None
    c = None
    try:
        c = sqlite3.connect("file:%s?mode=ro" % LIVE_DB, uri=True, timeout=5)
        c.row_factory = sqlite3.Row
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='mine_dev_events'").fetchone():
            c.close()
            return None
        b = _built_epoch(c)
        if b is None or time.time() - b > MAX_AGE_S:
            c.close()
            return None
        return c
    except Exception:  # noqa: BLE001 - any trouble with the file: serve the rules table
        log.exception("mine_dev_source: live AI file unreadable")
        if c is not None:
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
        return None


def fold_version(tables):
    """/api/v1/feed-versions: while the AI file is in use, mine_dev_events' version also changes with each rebuild."""
    try:
        md = tables.get("mine_dev_events")
        c = ai_conn()
        if md is None or c is None:
            return tables
        try:
            b = _built_epoch(c)
        finally:
            c.close()
        out = dict(tables)
        out["mine_dev_events"] = {"v": int(md["v"]) * 100000 + int(b // 60) % 100000,
                                  "changed_at": max(str(md.get("changed_at") or ""),
                                                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(b)))}
        return out
    except Exception:  # noqa: BLE001
        log.exception("mine_dev_source: fold_version")
        return tables
