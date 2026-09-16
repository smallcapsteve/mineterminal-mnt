#!/usr/bin/env python3
"""accuracy_run.py: measure extractors against accuracy sets, and gate installs (ACCURACY_V1).

  accuracy_run.py measure SET [--set-file PATH] [--details]
      Score what the site stores today (the spec's stored() reader) against SET.
      Records one fx_eval_runs row. A draft set measures fine; it just can't gate.

  accuracy_run.py daily            (also what runs with no arguments)
      Called by sync_structured.py. For every set in accuracy/sets/ whose last
      measurement is older than 20 hours: measure again. Cheap (about 50 lookups
      per set). This is the standing check that catches an extractor, a re-ingest
      or a categoriser change quietly making a page worse. Always exits 0 so a
      problem here never fails the sync job; problems are printed.

  accuracy_run.py gate EXTRACTOR [--set NAME]
      The auto-install step for a facts-store extractor: the registry's version of
      EXTRACTOR must be registered, fully backfilled and not active. Runs the
      self-tests, evaluates in memory, checks row counts and pages, activates,
      re-checks and undoes if anything got worse. Exit 0 installed, 3 not installed.

Writes only fx_eval_runs (and fx_extractor_versions.status on a gate). Short autocommit writes.
"""
import argparse
import json
import os
import subprocess
import sys

APP = os.path.dirname(os.path.abspath(__file__))
if APP not in sys.path:
    sys.path.insert(0, APP)

from portal import accuracy as A  # noqa: E402

DB = os.path.join(APP, "portal", "portal.db")
PY = sys.executable


def connect(path):
    import sqlite3
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def measure(conn, name, set_file=None, details=False, quiet=False, record=True):
    spec = A.SPECS.get(name)
    if spec is None:
        print(f"[accuracy] no spec named {name!r}; known: {sorted(A.SPECS)}")
        return 2
    aset = A.load_set(set_file or name)
    rep = A.evaluate(spec, aset, A.stored_predictor(spec, conn), A.load_events(conn, aset))
    run_id = A.record_run(conn, rep, f"stored:{name}", "measure") if record else "not recorded"
    head = f"[accuracy] {name} run {run_id}: set {aset['status']}"
    if not rep["set_usable"]:
        head += " (not usable for a gate: " + "; ".join(rep["set_unusable_reasons"]) + ")"
    print(head)
    if not quiet:
        for line in A.summary_lines(rep):
            print("  " + line)
    if details:
        print(json.dumps({"mistakes": rep["mistakes"], "stale": rep["stale"]}, indent=1, default=str))
    return 0


def daily(conn):
    A.ensure_eval_schema(conn)
    if not os.path.isdir(A.SETS_DIR):
        print("[accuracy] no accuracy sets yet")
        return 0
    n_sets = 0
    n_run = 0
    for fn in sorted(os.listdir(A.SETS_DIR)):
        if not fn.endswith(".json"):
            continue
        name = fn[:-5]
        spec = A.SPECS.get(name)
        if spec is None or spec.stored is None:
            continue
        n_sets += 1
        row = conn.execute("SELECT MAX(run_at) FROM fx_eval_runs WHERE set_name=? AND purpose='measure' "
                           "AND run_at > datetime('now', '-20 hours')", (name,)).fetchone()
        if row[0]:
            continue
        n_run += 1
        try:
            measure(conn, name, quiet=False)
        except Exception as e:  # noqa: BLE001  (one bad set must not stop the others or the sync job)
            print(f"[accuracy] {name}: {type(e).__name__}: {e}")
    if not n_sets:
        print("[accuracy] no measurable accuracy sets")
    elif not n_run:
        print(f"[accuracy] {n_sets} set(s) measured within 20 hours; nothing to do")
    return 0


def selftests(modules):
    ok = True
    for m in modules:
        r = subprocess.run([PY, "-m", m], cwd=APP, capture_output=True, text=True, timeout=600)
        last = (r.stdout.strip().splitlines() or [""])[-1]
        print(f"[gate] selftest {m}: rc={r.returncode} {last}")
        ok = ok and r.returncode == 0
    return ok


def gate(conn, extractor, set_name=None):
    from portal import facts
    from portal.extractors import REGISTRY
    specs = [s for s in REGISTRY if s.name == extractor]
    if not specs:
        print(f"[gate] {extractor!r} is not in portal/extractors REGISTRY")
        return 2
    ex = specs[0]
    tagspec = next((t for t in A.SPECS.values() if (set_name and t.name == set_name) or
                    (not set_name and t.tag == ex.tag and t.from_records)), None)
    if tagspec is None:
        print(f"[gate] no accuracy spec for tag {ex.tag!r}")
        return 2
    aset = A.load_set(tagspec.name)
    mods = ["portal.facts", "portal.normalize", "portal.accuracy"]
    ex_mod = getattr(ex.extract, "__module__", "")
    if ex_mod.startswith("portal.") and ex_mod not in mods:
        mods.append(ex_mod)
    ok = selftests(mods)
    result = A.gate_and_activate(conn, facts, tagspec, ex, aset, selftest_ok=ok)
    for c in result["checks"]:
        print(f"[gate]   {'PASS' if c['passed'] else 'FAIL'} {c['name']}: {c['detail']}")
    return 0 if result["passed"] else 3


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("set")
    m.add_argument("--set-file")
    m.add_argument("--details", action="store_true")
    m.add_argument("--no-record", action="store_true", help="read-only: do not write fx_eval_runs")
    sub.add_parser("daily")
    g = sub.add_parser("gate")
    g.add_argument("extractor")
    g.add_argument("--set")
    ap.add_argument("--db", default=DB)
    argv = sys.argv[1:] if argv is None else argv
    if not any(a in ("measure", "daily", "gate") for a in argv):
        argv = list(argv) + ["daily"]
    args = ap.parse_args(argv)
    conn = connect(args.db)
    if args.cmd == "measure":
        return measure(conn, args.set, args.set_file, args.details, record=not args.no_record)
    if args.cmd == "daily":
        return daily(conn)
    return gate(conn, args.extractor, args.set)


if __name__ == "__main__":
    sys.exit(main())
