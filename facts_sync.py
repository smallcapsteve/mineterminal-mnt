#!/usr/bin/env python3
"""facts_sync.py: incremental extraction into the facts store (FACTS_V1, 2026-09-16).

Timer mode (no arguments; called by sync_structured.py every 30 minutes):
  for each extractor in portal.extractors.REGISTRY, process approved events its
  current version has not seen, newest first, at most --limit (default 2000)
  per extractor per run. With an empty registry it only confirms the schema.

Backfill mode (--backfill NAME): process every pending event for that
extractor, 500 events per read, 200 per write transaction. A full run over
the corpus belongs under systemd-run, never inside the timer:
  systemd-run --unit fx-backfill-NAME -p User=mnt -p WorkingDirectory=/opt/mnt/app /opt/mnt/app/.venv/bin/python3 /opt/mnt/app/facts_sync.py --backfill NAME

FACTS_PAR_V1 (2026-09-23, Justin: "make the re-reads and initial reads parallel and queued to 3 cores at low
priority"):
  * Reading is done by up to 3 worker processes at the lowest CPU priority (nice 19). Writing stays in this one
    process, in the same order and the same transactions, so the store gets exactly what one process would write.
  * No worker is ever given more cores than the unit it runs in: under systemd-run -p CPUQuota=100% it reads with
    one process, as before. fx_backfill.sh starts backfills with CPUQuota=300%.
  * Backfills are queued: one runs at a time (a lock file); the next waits its turn and says so. While a backfill
    runs, the 30-minute timer reads with one process, so the box never has more than 3 readers plus one.
  * A release that takes a reader longer than --per-release seconds (default 30) is recorded as an error run
    ("Timeout: ...") instead of holding the whole run up.
  * --workers N overrides the number of processes (1 = the old single-process way).

Never activates a version. Activation is a separate, gated step.
"""
import argparse
import errno
import fcntl
import multiprocessing
import os
import signal
import sys
import time

sys.path.insert(0, "/opt/mnt/app")

from portal import facts  # noqa: E402
from portal.extractors import REGISTRY  # noqa: E402

DB = "/opt/mnt/app/portal/portal.db"
MAX_WORKERS = 3
PER_RELEASE_S = 30
QUEUE_LOCK = "/var/tmp/mnt-facts-backfill.lock"
SMALL = 40          # fewer events than this in a batch: read them here, a pool is not worth starting up

_SPECS = {}         # name -> ExtractorSpec, inherited by the forked workers
_LIMIT_S = PER_RELEASE_S


class _Timeout(Exception):
    pass


def _on_alarm(_signum, _frame):
    raise _Timeout()


def _init_worker(limit_s):
    global _LIMIT_S
    _LIMIT_S = limit_s
    try:
        os.nice(19 - os.nice(0))
    except OSError:
        pass
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGALRM, _on_alarm)


def _read_one(job):
    """One release through one reader, in a worker. Returns (records, error or None)."""
    name, headline, body = job
    signal.alarm(_LIMIT_S)
    try:
        return _SPECS[name].extract(headline, body), None
    except _Timeout:
        return [], f"Timeout: over {_LIMIT_S} s"
    except Exception as exc:  # noqa: BLE001  (recorded as an error run, as the inline loop does)
        return [], f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)


def cgroup_cores():
    """How many whole cores this process's cgroup may use (cgroup v2 cpu.max), or None when unlimited/unknown."""
    try:
        rel = ""
        with open("/proc/self/cgroup") as fh:
            for line in fh:
                if line.startswith("0::"):
                    rel = line.strip()[3:]
        with open("/sys/fs/cgroup" + rel + "/cpu.max") as fh:
            quota, period = fh.read().split()[:2]
        if quota == "max":
            return None
        return max(1, int(int(quota) / int(period)))
    except (OSError, ValueError):
        return None


class Readers:
    """A pool of low-priority reader processes, or none (inline) when only one process is allowed."""

    def __init__(self, workers, limit_s):
        self.workers = workers
        self.limit_s = limit_s
        self.pool = None        # started on the first batch big enough to need it (a quiet 30-minute run never forks)

    def extract_all(self, spec, pairs):
        if self.workers <= 1 or len(pairs) < SMALL:
            out = []
            for h, b in pairs:
                try:
                    out.append((spec.extract(h, b), None))
                except Exception as exc:  # noqa: BLE001
                    out.append(([], f"{type(exc).__name__}: {exc}"))
            return out
        if self.pool is None:
            self.pool = multiprocessing.get_context("fork").Pool(self.workers, initializer=_init_worker,
                                                                 initargs=(self.limit_s,))
        return self.pool.map(_read_one, [(spec.name, h, b) for h, b in pairs], chunksize=4)

    def close(self):
        if self.pool is not None:
            self.pool.close()
            self.pool.join()


def queue_turn(name, log=print):
    """Backfills run one at a time. Returns the open lock file (held until this process exits)."""
    fh = open(QUEUE_LOCK, "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        if e.errno not in (errno.EAGAIN, errno.EACCES):
            raise
        fh.seek(0)
        holder = fh.read().strip() or "another backfill"
        log(f"[facts_sync] {name}: queued behind {holder}", flush=True)
        t0 = time.time()
        fcntl.flock(fh, fcntl.LOCK_EX)
        log(f"[facts_sync] {name}: my turn after {time.time() - t0:.0f}s in the queue", flush=True)
    fh.seek(0)
    fh.truncate()
    fh.write(f"backfill {name} (pid {os.getpid()}, since {time.strftime('%H:%M:%S', time.gmtime())} UTC)")
    fh.flush()
    return fh


# ---- BFGUARD_V1 (2026-10-06; Justin: "All three guards") ---------------------------------------------------------
# A backfill writes between pages only while (1) MNT is not slow (the site guard's state says normal) and (2) the
# database's change log (WAL) holds under ~500 MB not yet copied back into the database. On 2026-10-06 21:33-22:27 UTC
# a sampling backfill grew the change log to 1.9 GB and MNT stopped answering. Waiting happens between write
# transactions, never inside one, so no lock is held while paused. Off switch: touch /opt/mnt/app/BFGUARD_OFF.
BFG_STATE = "/var/lib/mnt-health/guard.state"
BFG_OFF = "/opt/mnt/app/BFGUARD_OFF"
BFG_WAL_MAX = 500e6
BFG_SLEEP = 30


def _bfg_wal_backlog(conn):
    """Bytes in the change log not yet copied into the database, after a PASSIVE checkpoint (never blocks)."""
    try:
        busy, n_log, n_ckpt = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        page = conn.execute("PRAGMA page_size").fetchone()[0]
        if n_log < 0:
            return 0
        return max(0, n_log - max(n_ckpt, 0)) * page
    except Exception:  # noqa: BLE001 - a failed check never stops a backfill
        return 0


def _bfg_mnt_slow():
    try:
        with open(BFG_STATE) as fh:
            return "mode=throttled" in fh.read()
    except OSError:
        return False


def _backfill_gate(conn, name, sleep=None, state=None):
    """Wait, between pages of a backfill, while MNT is slow or the change log is too big. Returns seconds waited."""
    global BFG_STATE
    if state is not None:
        BFG_STATE = state
    if os.environ.get("MNT_BFGUARD_OFF") == "1" or os.path.exists(BFG_OFF):
        return 0
    if conn.in_transaction:
        return 0
    waited, last_said = 0, None
    while True:
        why = []
        if _bfg_mnt_slow():
            why.append("MNT is slow")
        backlog = _bfg_wal_backlog(conn)
        if backlog > BFG_WAL_MAX:
            why.append(f"change log {backlog / 1e6:.0f} MB not yet written back")
        if not why:
            if waited:
                print(f"[facts_sync] {name}: resuming after {waited}s paused (BFGUARD)", flush=True)
            return waited
        msg = "; ".join(why)
        if msg != last_said or waited % 600 == 0:
            print(f"[facts_sync] {name}: paused - {msg} (BFGUARD; waited {waited}s)", flush=True)
            last_said = msg
        s = BFG_SLEEP if sleep is None else sleep
        time.sleep(s)
        waited += s


def backfill_running():
    try:
        with open(QUEUE_LOCK, "a+") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_SH | fcntl.LOCK_NB)
                fcntl.flock(fh, fcntl.LOCK_UN)
                return False
            except OSError:
                return True
    except OSError:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", metavar="NAME")
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--since", help="only events published on/after YYYY-MM-DD")
    ap.add_argument("--db", default=DB)
    ap.add_argument("--workers", type=int, default=None, help=f"reader processes (default {MAX_WORKERS})")
    ap.add_argument("--per-release", type=int, default=PER_RELEASE_S, help="seconds before a release is an error")
    args = ap.parse_args(argv)

    conn = facts.connect(args.db)
    facts.ensure_schema(conn)
    specs = [s for s in REGISTRY if not args.backfill or s.name == args.backfill]
    if args.backfill and not specs:
        print(f"[facts_sync] no registered extractor named {args.backfill!r}")
        return 2
    if not specs:
        print("[facts_sync] schema ok; no extractors registered")
        return 0

    lock = None
    if args.backfill:
        lock = queue_turn(args.backfill)
        try:
            if os.nice(0) < 10:
                os.nice(10 - os.nice(0))
        except OSError:
            pass
    workers = MAX_WORKERS if args.workers is None else max(1, args.workers)
    cap = cgroup_cores()
    if cap is not None:
        workers = min(workers, cap)
    if not args.backfill and args.workers is None and backfill_running():
        workers = 1     # a backfill already has the 3 reader cores
    _SPECS.clear()
    _SPECS.update({s.name: s for s in specs})
    readers = Readers(workers, args.per_release)
    print(f"[facts_sync] reading with {workers} process{'es' if workers > 1 else ''}"
          f"{' (cgroup allows ' + str(cap) + ')' if cap is not None else ''}", flush=True)

    rc = 0
    try:
        for spec in specs:
            try:
                rc = max(rc, _run_spec(conn, spec, args, readers))
            except facts.FactsError as e:
                # ECON_FIX (2026-09-23): one extractor's registration problem (a code change without a version bump)
                # must not stop the extractors after it; it is logged, the run still exits 1, the rest carry on
                if conn.in_transaction:
                    conn.rollback()
                print(f"[facts_sync] {spec.name} {spec.version} SKIPPED: {e}", flush=True)
                rc = 1
    finally:
        readers.close()
        if lock is not None:
            lock.close()
    return rc


def _run_spec(conn, spec, args, readers=None):
    rc = 0
    t0 = time.time()
    total = {"events": 0, "records": 0, "errors": 0, "max_txn_ms": 0.0}
    remaining = None if args.backfill else args.limit
    while True:
        if args.backfill:
            _backfill_gate(conn, spec.name)
        page = 500 if remaining is None else min(500, remaining)
        if page <= 0:
            break
        events = facts.pending_events(conn, spec.name, spec.version, limit=page, since=args.since)
        if not events:
            break
        c = facts.run_batch(conn, spec, events, batch=200,
                            extract_all=readers.extract_all if readers is not None and readers.workers > 1 else None)
        if c["skipped"]:
            print(f"[facts_sync] {spec.name} {spec.version} is {c['skipped']}; skipped (roll the registry back too)")
            break
        for k in ("events", "records", "errors"):
            total[k] += c[k]
        total["max_txn_ms"] = max(total["max_txn_ms"], c["max_txn_ms"])
        if remaining is not None:
            remaining -= len(events)
        if args.backfill:
            print(f"[facts_sync] {spec.name} {spec.version}: {total['events']} events so far", flush=True)
    st = facts.stats(conn, spec.name, spec.version)
    status = facts.version_status(conn, spec.name, spec.version)
    print(f"[facts_sync] {spec.name} {spec.version} ({status}): +{total['events']} events, "
          f"+{total['records']} records, {total['errors']} errors, longest write {total['max_txn_ms']} ms, "
          f"{time.time() - t0:.1f}s | totals: {st['runs']} runs, {st['records']} records, "
          f"in-tag coverage {st['coverage_in_tag']}, fired outside tag {st['fired_untagged']}")
    if total["errors"]:
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
