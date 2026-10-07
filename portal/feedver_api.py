"""SPEEDFIX_FEEDVER_V1 (2026-10-07): /api/v1/feed-versions.

Each published table's version (feed_versions, bumped by portal/rowsync.py inside the publisher's transaction whenever
a publish changes rows). Mine Terminal Pro polls this and drops its saved copy of a feed as soon as the feed's table
changes. Read-only; answers from a 5-second in-process copy so a burst of callers costs one tiny query.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing

DB_PATH = "/opt/mnt/app/portal/portal.db"
_STATE = {"t": 0.0, "body": None}
_LOCK = threading.Lock()


def read_versions(db_path: str = DB_PATH) -> dict:
    with closing(sqlite3.connect("file:%s?mode=ro" % db_path, uri=True, timeout=10)) as c:
        rows = c.execute("SELECT tbl, v, changed_at FROM feed_versions").fetchall()
    return {r[0]: {"v": r[1], "changed_at": r[2]} for r in rows}


def register(app) -> None:
    from fastapi.responses import JSONResponse

    @app.get("/api/v1/feed-versions")
    def feed_versions():
        now = time.monotonic()
        with _LOCK:
            if _STATE["body"] is None or now - _STATE["t"] > 5.0:
                try:
                    _STATE["body"] = {"ok": True, "tables": read_versions()}
                except Exception as exc:  # noqa: BLE001
                    return JSONResponse({"ok": False, "error": type(exc).__name__}, status_code=503,
                                        headers={"Cache-Control": "no-store"})
                _STATE["t"] = now
            body = dict(_STATE["body"], read_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        return JSONResponse(body, headers={"Cache-Control": "no-store", "X-MNT-API-Version": "1"})
