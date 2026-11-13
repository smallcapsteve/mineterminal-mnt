"""MNTLEAK_V1 (2026-10-28): close the SQLite connections of threads that have ended.

Why. portal/db.py and portal/release_format.py keep one SQLite connection per thread (threading.local). FastAPI runs
each request on a thread from anyio's pool, and anyio retires a thread after 10 s idle and starts a new one when
traffic picks up again, so a web worker goes through threads all day. When a thread ends, its connection is NOT
closed: in Python 3.12 a sqlite3.Connection holds a reference cycle with its own statement cache, so only a full
garbage collection frees it, and in a worker holding millions of long-lived cached objects full collections are
rare. Measured 2026-10-28: workers held 74-80 portal.db and 57 release_html.db connections with 6 threads alive,
each keeping its page cache, and grew from ~180 MB to 1.1 GB in 1-1.5 h. Record: claude/MNTLEAK_FINDINGS_2026-10-28.md.

What. adopt(conn) records which thread a new connection belongs to and, in the same step, closes every recorded
connection whose thread has ended. It runs only when a thread opens its connection, i.e. rarely, and the count of
open connections stays at most the number of live threads (+ the one being added). A dead thread's connection is
never in use (each connection is used only by the thread that opened it), so closing it changes no result.

Undo: drop the adopt() calls in db.get_conn() and release_format._con() (the old behaviour returns exactly).
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_registry: list = []          # [(threading.Thread, sqlite3.Connection, label)]
_closed_total = 0


def _alive(th) -> bool:
    try:
        return th.is_alive()
    except Exception:  # noqa: BLE001 - a thread we cannot judge is kept, never closed under it
        return True


def adopt(conn, label: str = ""):
    """Record conn as the current thread's connection; close those of threads that have ended. Returns conn."""
    global _closed_total
    me = threading.current_thread()
    stale = []
    with _lock:
        keep = []
        for entry in _registry:
            (keep if _alive(entry[0]) else stale).append(entry)
        keep.append((me, conn, label))
        _registry[:] = keep
        _closed_total += len(stale)
    for _th, c, _label in stale:
        try:
            c.close()
        except Exception:  # noqa: BLE001
            pass
    return conn


def stats() -> dict:
    with _lock:
        by = {}
        for _th, _c, label in _registry:
            by[label] = by.get(label, 0) + 1
        return {"open": len(_registry), "by_label": by, "closed_total": _closed_total}


def _self_test() -> None:
    import os
    import sqlite3
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "t.db")
    sqlite3.connect(path).close()
    local = threading.local()
    seen = []

    def work():
        c = getattr(local, "c", None)
        if c is None:
            local.c = c = adopt(sqlite3.connect(path, check_same_thread=False), "t")
        seen.append(c.execute("select 1").fetchone()[0])

    for _ in range(20):
        t = threading.Thread(target=work)
        t.start()
        t.join()
    s = stats()
    assert seen == [1] * 20, seen
    assert s["by_label"].get("t", 0) <= 2, s           # the last thread's, plus at most one not yet swept
    assert s["closed_total"] >= 18, s
    # the current (alive) thread's connection is never closed
    mine = adopt(sqlite3.connect(path, check_same_thread=False), "t")
    assert mine.execute("select 1").fetchone()[0] == 1


if __name__ == "__main__":
    _self_test()
    print("conn_reaper self-test ok", stats())
