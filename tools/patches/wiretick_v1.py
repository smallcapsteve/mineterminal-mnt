#!/usr/bin/env python3
"""WIRETICK_V1 (2026-11-03, Justin: "Majors and big misses"). Google-News wire collectors (GlobeNewswire, Business Wire,
PR Newswire, CNW) drop releases from dual-listed companies because their ticker reader only accepts a lone "(TSX: K)",
and drop results/dividend/call notices whose headline has no mining word. This adds /opt/mnt/app/wireticker.py and, in
each of the four sources/*_gnews.py:
  1. extract_ticker(): when the old reader finds nothing, try the relaxed reader (first bracket with a TSX/TSXV/CSE tag).
  2. list_mining_events(): a headline with no mining word goes on only if it starts with a coverage-list company's
     name, and is then kept only if the ticker read from the release is that company.
Anything that worked before is unchanged (old reader and old gate run first). Fails open to the old behaviour.
  patch_wiretick.py --build OUT | --install OUT"""
import datetime as dt, hashlib, os, py_compile, shutil, sys
APP = "/opt/mnt/app"; SRC = os.path.dirname(os.path.abspath(__file__))
MODS = ["globenewswire_gnews", "businesswire_gnews", "prnewswire_gnews", "cnw_gnews"]
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
def sub1(s, old, new, f):
    if s.count(old) != 1: sys.exit("REFUSED: %s: expected text found %d times: %r" % (f, s.count(old), old[:60]))
    return s.replace(old, new)
def build(out):
    os.makedirs(out + "/sources", exist_ok=True)
    if os.path.exists(f"{APP}/wireticker.py"): sys.exit("REFUSED: wireticker.py already exists")
    shutil.copyfile(f"{SRC}/wireticker.py", f"{out}/wireticker.py")
    py_compile.compile(f"{out}/wireticker.py", doraise=True, cfile=f"{out}/__pycache__/wireticker.pyc")
    for m in MODS:
        p = f"{APP}/sources/{m}.py"; s = open(p).read()
        if "WIRETICK_V1" in s: sys.exit("REFUSED: %s already patched" % m)
        s = sub1(s, "\nimport httpx\n", "\nimport httpx\ntry:\n    import wireticker as _WT                           # WIRETICK_V1\nexcept Exception:\n    _WT = None\n", m)
        s = sub1(s, '            return f"{t}.{suffix}", ex\n    return None, None\n',
                 '            return f"{t}.{suffix}", ex\n'
                 '    try:                                                # WIRETICK_V1: dual-listed datelines\n'
                 '        return _WT.extract_ticker_relaxed(text) if _WT else (None, None)\n'
                 '    except Exception:\n'
                 '        return None, None\n', m)
        s = sub1(s, "            if not is_mining_headline(title):\n                continue\n",
                 "            _wt_bares = set()                           # WIRETICK_V1\n"
                 "            if not is_mining_headline(title):\n"
                 "                try:\n"
                 "                    _wt_bares = _WT.names_company(title) if _WT else set()\n"
                 "                except Exception:\n"
                 "                    _wt_bares = set()\n"
                 "                if not _wt_bares:\n"
                 "                    continue\n", m)
        s = sub1(s, "            ticker, exch = extract_ticker(body_text)\n",
                 "            ticker, exch = extract_ticker(body_text)\n"
                 "            if ticker and _wt_bares and not _WT.company_matches(ticker, _wt_bares):\n"
                 "                continue                                # WIRETICK_V1: headline names another company\n", m)
        open(f"{out}/sources/{m}.py", "w").write(s)
        py_compile.compile(f"{out}/sources/{m}.py", doraise=True, cfile=f"{out}/sources/__pycache__/{m}.pyc")
        print("built", m, sha(p), "=>", sha(f"{out}/sources/{m}.py"))
    print("built wireticker.py", sha(f"{out}/wireticker.py"))
def install(out):
    TS = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"); B = f"/var/backups/mnt/wiretick-{TS}"; os.makedirs(B + "/sources")
    undo = ["#!/bin/sh", "set -e"]
    for m in MODS:
        p = f"{APP}/sources/{m}.py"
        if "WIRETICK_V1" in open(p).read(): sys.exit("REFUSED: %s already patched" % m)
        shutil.copy2(p, f"{B}/sources/{m}.py"); undo.append(f"cp -p {B}/sources/{m}.py {p}")
    undo += [f"rm -f {APP}/wireticker.py", "echo 'WIRETICK_V1 undone'"]
    open(f"{B}/undo.sh", "w").write("\n".join(undo) + "\n")
    st = os.stat(f"{APP}/sources/{MODS[0]}.py")
    tmp = f"{APP}/.wireticker.py.tmp"; shutil.copyfile(f"{out}/wireticker.py", tmp)
    os.chown(tmp, st.st_uid, st.st_gid); os.chmod(tmp, 0o644); os.replace(tmp, f"{APP}/wireticker.py")
    for m in MODS:
        p = f"{APP}/sources/{m}.py"; st = os.stat(p); tmp = f"{APP}/sources/.{m}.wt.tmp"
        shutil.copyfile(f"{out}/sources/{m}.py", tmp); os.chown(tmp, st.st_uid, st.st_gid); os.chmod(tmp, st.st_mode & 0o777)
        os.replace(tmp, p); print("installed", m, sha(p))
    print("installed wireticker.py", sha(f"{APP}/wireticker.py"), "| backup", B, "| undo: sh", B + "/undo.sh")
if __name__ == "__main__":
    if os.uname().nodename != "mnt-scraper-01": sys.exit("REFUSED: wrong host")
    {"--build": build, "--install": install}[sys.argv[1]](sys.argv[2])
