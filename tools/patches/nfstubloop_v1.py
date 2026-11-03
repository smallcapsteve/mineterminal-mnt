#!/usr/bin/env python3
"""NFSTUBLOOP_V1 (2026-11-03, Justin: "Fix the Manganese X loop"). Two short versions (Newsfile feed stubs) of one release
took turns replacing each other: fill_stubs() put back a copy the duplicate guard had held back against the live short
version, but that held-back copy was itself the other short version; the next run the collector re-posted the first
one, the guard held it back against the second, and so on (MN.V: 361 swaps a day, each logged in full).
  1. held_back_copy(): a held-back short version never takes over another short version.
  2. make_stub(): a short version the duplicate guard refuses is remembered as 'stub_refused' in the seen file, so it is
     not re-posted every run.
  patch_stubloop.py --build OUT | --install OUT"""
import datetime as dt, hashlib, os, py_compile, shutil, sys
APP = "/opt/mnt/app"; F = "sync_newsfile_direct.py"; EXPECT = "8103f2c34918f3ce"
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
def sub1(s, old, new):
    if s.count(old) != 1: sys.exit("REFUSED: expected text found %d times: %r" % (s.count(old), old[:70]))
    return s.replace(old, new)
def build(out):
    if sha(f"{APP}/{F}") != EXPECT: sys.exit("REFUSED: live %s is %s" % (F, sha(f"{APP}/{F}")))
    os.makedirs(out, exist_ok=True); s = open(f"{APP}/{F}").read()
    s = sub1(s, '    if _ro().execute("SELECT 1 FROM events WHERE event_id=?", (row.get("event_id"),)).fetchone():\n',
             '    if row.get("classifier_model") == STUB_MODEL:     # NFSTUBLOOP_V1: never swap one short version for another\n'
             '        return None\n'
             '    if _ro().execute("SELECT 1 FROM events WHERE event_id=?", (row.get("event_id"),)).fetchone():\n')
    s = sub1(s, '        return "refused"\n',
             '        seen[rid] = {"st": "stub_refused"}             # NFSTUBLOOP_V1: do not re-post it every run\n'
             '        return "refused"\n')
    open(f"{out}/{F}", "w").write(s)
    py_compile.compile(f"{out}/{F}", doraise=True, cfile=f"{out}/__pycache__/{F}c")
    print("built", out, sha(f"{out}/{F}"))
def install(out):
    if sha(f"{APP}/{F}") != EXPECT: sys.exit("REFUSED: live %s changed (%s)" % (F, sha(f"{APP}/{F}")))
    TS = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"); B = f"/var/backups/mnt/nfstubloop-{TS}"; os.makedirs(B)
    shutil.copy2(f"{APP}/{F}", f"{B}/{F}")
    open(f"{B}/undo.sh", "w").write(f"#!/bin/sh\nset -e\ncp -p {B}/{F} {APP}/{F}\necho 'NFSTUBLOOP_V1 undone'\n")
    st = os.stat(f"{APP}/{F}"); tmp = f"{APP}/.{F}.sl.tmp"
    shutil.copyfile(f"{out}/{F}", tmp); os.chown(tmp, st.st_uid, st.st_gid); os.chmod(tmp, st.st_mode & 0o777)
    os.replace(tmp, f"{APP}/{F}")
    print("installed", sha(f"{APP}/{F}"), "backup", B, "| undo: sh", B + "/undo.sh")
if __name__ == "__main__":
    if os.uname().nodename != "mnt-scraper-01": sys.exit("REFUSED: wrong host")
    {"--build": build, "--install": install}[sys.argv[1]](sys.argv[2])
