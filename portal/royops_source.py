"""MNT_ROYOPS_AI_LIVE_V1 (2026-10-26): where each royalty's terms (/api/v1/royalties, /api/v1/royalty-terms) and the option
payment schedules (/api/v1/option-payments) are read from.

While royalty terms and option schedules are switched to the AI reader (plan: claude/AIREADER_HYBRID_PLAN_2026-10-22.md;
Justin 2026-10-26), /opt/mnt-royops/royops_live.py writes the hybrid hourly to /var/lib/mnt-aireader-pub/royops_live.db:
  royalty_terms     one record per release: the AI's royalties and payments, the rules reader's other terms; each
                    interest carries _label agreed | AI-read
  land_deal_items   the live table's columns plus ai_label agreed | AI-read | rules (not read by the AI yet)
The APIs read that file while it exists and was built in the last 12 hours; otherwise portal.db exactly as before.

Undo, instantly: systemctl disable --now aireader-royops-live.timer; rm /var/lib/mnt-aireader-pub/royops_live.db"""
import calendar
import logging
import os
import sqlite3
import time

LIVE_DB = os.environ.get("MNT_ROYOPS_LIVE_DB", "/var/lib/mnt-aireader-pub/royops_live.db")
TABLES = ("royalty_terms", "land_deal_items")
MAX_AGE_S = 12 * 3600
log = logging.getLogger(__name__)


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
        r = c.execute("SELECT v FROM preview_meta WHERE k='royops_built_at'").fetchone()
        b = calendar.timegm(time.strptime(r[0], "%Y-%m-%dT%H:%M:%SZ")) if r and r[0] else None
        if b is None or time.time() - b > MAX_AGE_S:
            c.close()
            return None
        return c
    except Exception:  # noqa: BLE001 - any trouble with the file: serve the rules tables
        log.exception("royops_source: live AI file unreadable")
        if c is not None:
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
        return None


def ai_cols(conn, table="land_deal_items"):
    """', ai_label' when the connection is the hybrid file (its table has the column), else ''."""
    try:
        return ", ai_label" if any(r[1] == "ai_label" for r in conn.execute("PRAGMA table_info(%s)" % table)) else ""
    except Exception:  # noqa: BLE001
        return ""
