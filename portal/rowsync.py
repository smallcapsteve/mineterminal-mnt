"""OPSFIX item 1 (2026-10-05): write only the rows that changed.

The readers' publish step used to DELETE every row of its table and INSERT them all again, every 30 minutes, even
when nothing had changed. That rewrote ~70,000 rows for Exploration alone each time, grew the database and its
write-ahead file, and made every page cache keyed on the table think the data had changed.

sync_rows() gives the table exactly the same contents (compared on every published column) but leaves unchanged
rows alone: rows that are no longer produced are deleted, new or changed rows are inserted, everything else keeps
its row and id. Must be called inside the publisher's own transaction.

Kill switch: create /opt/mnt/app/portal/rowsync_OFF (or set MNT_ROWSYNC_OFF=1) and every publisher using this goes
back to delete-everything-and-reinsert on its next run.
"""
from __future__ import annotations

import os
from collections import defaultdict

OFF_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rowsync_OFF")


def _off() -> bool:
    return os.environ.get("MNT_ROWSYNC_OFF") == "1" or os.path.exists(OFF_FILE)


def _affinities(conn, table: str) -> dict:
    out = {}
    for r in conn.execute("PRAGMA table_info(%s)" % table):
        t = (r[2] or "").upper()
        out[r[1]] = ("INTEGER" if "INT" in t else "TEXT" if ("CHAR" in t or "CLOB" in t or "TEXT" in t)
                     else "REAL" if ("REAL" in t or "FLOA" in t or "DOUB" in t) else "NUMERIC" if t else "BLOB")
    return out


def _as_stored(v, aff: str):
    """The value SQLite will hand back after storing v in a column of this affinity (enough for comparison)."""
    if v is None:
        return None
    if isinstance(v, bool):
        v = int(v)
    if aff == "TEXT" and isinstance(v, (int, float)):
        return str(v)
    if aff in ("INTEGER", "NUMERIC", "REAL"):
        if isinstance(v, str):
            s = v.strip()
            try:
                f = float(s)
                v = int(s) if s.lstrip("+-").isdigit() else f
            except ValueError:
                return v
        if isinstance(v, float) and aff in ("INTEGER", "NUMERIC") and v.is_integer() and abs(v) < 2 ** 63:
            return int(v)
        if isinstance(v, int) and aff == "REAL":
            return float(v)
    return v


def _sync_rows_now(conn, table: str, id_col: str, cols, rows, const: dict | None = None) -> dict:
    cols = list(cols)
    const = dict(const or {})
    allc = cols + list(const)
    ins_sql = "INSERT INTO %s(%s) VALUES (%s)" % (table, ", ".join(allc), ", ".join(":" + c for c in allc))
    params = [dict({c: r[c] for c in cols}, **const) for r in rows]
    if _off():
        conn.execute("DELETE FROM %s" % table)
        conn.executemany(ins_sql, params)
        return {"mode": "rewrite (rowsync_OFF)", "inserted": len(params)}
    aff = _affinities(conn, table)
    existing = defaultdict(list)
    for r in conn.execute("SELECT %s, %s FROM %s ORDER BY %s" % (id_col, ", ".join(allc), table, id_col)):
        t = tuple(r)
        existing[tuple(_as_stored(v, aff.get(c, "BLOB")) for c, v in zip(allc, t[1:]))].append(t[0])
    to_insert, kept = [], 0
    for p in params:
        key = tuple(_as_stored(p[c], aff.get(c, "BLOB")) for c in allc)
        ids = existing.get(key)
        if ids:
            ids.pop(0)
            kept += 1
            if not ids:
                del existing[key]
        else:
            to_insert.append(p)
    dead = [i for ids in existing.values() for i in ids]
    if dead:
        conn.executemany("DELETE FROM %s WHERE %s=?" % (table, id_col), [(i,) for i in dead])
    if to_insert:
        conn.executemany(ins_sql, to_insert)
    return {"mode": "changed rows only", "kept": kept, "inserted": len(to_insert), "deleted": len(dead)}


def _sync_rows_pk_now(conn, table: str, pk, cols, rows) -> dict:
    """Same idea for a table whose rows are identified by their own key columns (e.g. WITHOUT ROWID tables, or
    tables whose id the reader assigns itself). Rows whose key disappeared are deleted; rows whose key is new, or
    whose other columns changed, are (re)written; the rest are left alone."""
    pk = list(pk)
    rows = list(rows)
    cols = list(cols) if cols else (list(rows[0].keys()) if rows else [])
    if not rows:
        n = conn.execute("SELECT count(*) FROM %s" % table).fetchone()[0]
        conn.execute("DELETE FROM %s" % table)
        return {"mode": "changed rows only", "kept": 0, "inserted": 0, "deleted": n}
    ins_sql = "INSERT INTO %s(%s) VALUES (%s)" % (table, ", ".join(cols), ", ".join(":" + c for c in cols))
    params = [{c: r[c] for c in cols} for r in rows]
    if _off() or not all(k in cols for k in pk):
        conn.execute("DELETE FROM %s" % table)
        conn.executemany(ins_sql, params)
        return {"mode": "rewrite" + (" (rowsync_OFF)" if _off() else " (key not in columns)"), "inserted": len(params)}
    aff = _affinities(conn, table)
    norm = lambda c, v: _as_stored(v, aff.get(c, "BLOB"))
    existing = {}
    for r in conn.execute("SELECT %s FROM %s" % (", ".join(cols), table)):
        t = tuple(norm(c, v) for c, v in zip(cols, tuple(r)))
        existing[tuple(t[cols.index(k)] for k in pk)] = t
    kept, write, seen = 0, [], set()
    for p in params:
        t = tuple(norm(c, p[c]) for c in cols)
        k = tuple(t[cols.index(x)] for x in pk)
        seen.add(k)
        if existing.get(k) == t:
            kept += 1
        else:
            write.append((k, p, k in existing))
    gone = [k for k in existing if k not in seen]
    where = " AND ".join("%s=?" % k for k in pk)
    stale = gone + [k for k, _, had in write if had]
    if stale:
        conn.executemany("DELETE FROM %s WHERE %s" % (table, where), stale)
    if write:
        conn.executemany(ins_sql, [p for _, p, _ in write])
    return {"mode": "changed rows only", "kept": kept, "inserted": len(write),
            "deleted": len(gone), "replaced": sum(1 for _, _, had in write if had)}


def _stable_ids_now(conn, table: str, id_col: str, rows, refs=()) -> dict:
    """OPSFIX item 1b (2026-10-05): keep a reader-assigned id stable across runs. A reader that numbers its rows
    1, 2, 3 ... on every run shifts every number after a new row, so every later row (and every row pointing at it)
    looks changed. Here a row whose other columns match a stored row takes that row's id; any other row gets a new
    id above every stored one. refs = [(other_rows, (column, ...)), ...] are rewritten through the same mapping.
    Call inside the publisher's transaction, before sync_rows_pk."""
    rows = list(rows)
    if not rows or _off():
        return {"mode": "unchanged (no rows)" if rows == [] else "unchanged (rowsync_OFF)"}
    cols = [c for c in rows[0].keys() if c != id_col]
    aff = _affinities(conn, table)
    have = {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}
    cols = [c for c in cols if c in have]
    existing = defaultdict(list)
    max_id = 0
    for r in conn.execute("SELECT %s, %s FROM %s ORDER BY %s" % (id_col, ", ".join(cols), table, id_col)):
        t = tuple(r)
        max_id = max(max_id, t[0] or 0)
        existing[tuple(_as_stored(v, aff.get(c, "BLOB")) for c, v in zip(cols, t[1:]))].append(t[0])
    mapping, reused = {}, 0
    nxt = max(max_id, max((r[id_col] or 0) for r in rows)) + 1
    for r in rows:                      # pass 1: exact matches keep their stored id
        ids = existing.get(tuple(_as_stored(r[c], aff.get(c, "BLOB")) for c in cols))
        if ids:
            mapping[r[id_col]] = ids.pop(0)
            reused += 1
    for r in rows:                      # pass 2: everything else gets a fresh id
        if r[id_col] not in mapping:
            mapping[r[id_col]] = nxt
            nxt += 1
    for r in rows:
        r[id_col] = mapping[r[id_col]]
    for other, ref_cols in refs:
        for o in other:
            for c in ref_cols:
                if c in o and o[c] is not None and o[c] in mapping:
                    o[c] = mapping[o[c]]
    return {"mode": "stable ids", "reused": reused, "new": len(rows) - reused}


# -------------------------------------------------------------------------------------------------------------
# OPTD step A (2026-10-06, Justin: "go ahead with both steps"): work out the differences BEFORE the write lock.
#
# Each publisher now runs its rowsync calls twice. First inside `with rowsync.planning(conn):`, before
# BEGIN IMMEDIATE: the same functions run against a recorder that answers SELECT / PRAGMA from the database but
# only records the DELETE / INSERT statements. Then, as before, inside BEGIN IMMEDIATE: a call whose plan is
# still valid (same call in the same order, the same row list, the table's count and max(rowid) unchanged since
# the plan was made) replays the recorded statements instead of reading and comparing the whole table again
# while every other writer waits. Anything else is worked out inside the lock exactly as before, so the table
# always ends up the same as it would have.
#
# Kill switch: create /opt/mnt/app/portal/rowsync_plan_OFF (or set MNT_ROWSYNC_PLAN_OFF=1): the planning pass
# does nothing and every call is worked out inside the lock, as before.
# -------------------------------------------------------------------------------------------------------------
import sys as _sys
from contextlib import contextmanager as _contextmanager

PLAN_OFF_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rowsync_plan_OFF")
_MODE = None      # None = normal (locked pass or no planning), "plan", "skip"
_PLANS = []       # (fn, table, rows object, len(rows), signature, table fingerprint, recorded ops, result, undo)


def _plan_off() -> bool:
    return os.environ.get("MNT_ROWSYNC_PLAN_OFF") == "1" or os.path.exists(PLAN_OFF_FILE)


class _NoWrite:
    rowcount = 0

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __iter__(self):
        return iter(())


class _Recorder:
    """Runs reads on the real connection; records writes instead of running them."""

    def __init__(self, conn):
        self._conn = conn
        self.ops = []

    @staticmethod
    def _is_read(sql):
        s = sql.lstrip().upper()
        return s.startswith("SELECT") or s.startswith("PRAGMA TABLE_INFO")

    def execute(self, sql, params=()):
        if self._is_read(sql):
            return self._conn.execute(sql, params)
        self.ops.append(("one", sql, params))
        return _NoWrite()

    def executemany(self, sql, seq):
        if self._is_read(sql):
            raise RuntimeError("rowsync planning: unexpected executemany read")
        self.ops.append(("many", sql, list(seq)))
        return _NoWrite()


def _table_fp(conn, table):
    try:
        return tuple(conn.execute("SELECT count(*), max(rowid) FROM %s" % table).fetchone())
    except Exception:  # WITHOUT ROWID table
        return (conn.execute("SELECT count(*) FROM %s" % table).fetchone()[0], None)


@_contextmanager
def planning(conn=None):
    """Wrap a publisher's rowsync calls, run once before BEGIN IMMEDIATE. Never raises."""
    global _MODE
    _PLANS.clear()
    _MODE = "skip" if _plan_off() else "plan"
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - planning is an optimisation; the locked pass decides
        _discard()
        print("[rowsync] planning before the lock failed (%s: %s); working it out inside the lock"
              % (type(exc).__name__, exc), file=_sys.stderr)
    finally:
        _MODE = None


def _discard():
    """Drop plans that will not be replayed; put back any ids stable_ids changed while planning, so the
    locked pass starts from exactly the rows it would have had without planning."""
    for p in reversed(_PLANS):
        for obj, k, v in reversed(p[8]):
            obj[k] = v
    _PLANS.clear()


def _planned(fn, conn, table, rows, sig, call, undo=()):
    if _MODE == "skip":
        return {"mode": "not planned (rowsync_plan_OFF)"}
    if _MODE == "plan":
        n = len(rows)                    # a generator has no len(): planning stops before consuming it
        fp = _table_fp(conn, table)
        rec = _Recorder(conn)
        undo = list(undo)
        try:
            res = call(rec)
        except BaseException:
            for obj, k, v in reversed(undo):
                obj[k] = v
            raise
        _PLANS.append((fn, table, rows, n, sig, fp, rec.ops, res, undo))   # holds rows so it is the same object
        return dict(res, planned=len(rec.ops)) if isinstance(res, dict) else res
    if _PLANS:
        p = _PLANS.pop(0)
        if p[2] is rows and (p[0], p[1], p[3], p[4]) == (fn, table, len(rows), sig) and _table_fp(conn, table) == p[5]:
            for kind, sql, params in p[6]:
                if kind == "one":
                    conn.execute(sql, params)
                else:
                    conn.executemany(sql, params)
            res = p[7]
            if isinstance(res, dict):
                res = dict(res, mode=str(res.get("mode", "")) + ", worked out before the lock")
            return res
        _PLANS.insert(0, p)
        _discard()       # out of step: work everything left out inside the lock
    return call(conn)


def sync_rows(conn, table: str, id_col: str, cols, rows, const: dict | None = None) -> dict:
    cols = tuple(cols)
    sig = repr((id_col, cols, sorted((const or {}).items())))
    return _planned("sync_rows", conn, table, rows, sig,
                    lambda c: _sync_rows_now(c, table, id_col, cols, rows, const))


def sync_rows_pk(conn, table: str, pk, cols, rows) -> dict:
    pk = tuple(pk)
    cols = tuple(cols) if cols else cols
    sig = repr((pk, cols))
    return _planned("sync_rows_pk", conn, table, rows, sig,
                    lambda c: _sync_rows_pk_now(c, table, pk, cols, rows))


def stable_ids(conn, table: str, id_col: str, rows, refs=()) -> dict:
    refs = list(refs)
    sig = repr((id_col, [(id(o), len(o), tuple(rc)) for o, rc in refs]))
    undo = ()
    if _MODE == "plan" and isinstance(rows, (list, tuple)):   # stable_ids rewrites ids in place: remember them
        undo = [(r, id_col, r[id_col]) for r in rows if id_col in r]
        undo += [(o, c, o[c]) for other, rc in refs for o in other for c in rc if c in o]
    return _planned("stable_ids", conn, table, rows, sig,
                    lambda c: _stable_ids_now(c, table, id_col, rows, refs), undo)
