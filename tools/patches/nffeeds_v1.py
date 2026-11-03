#!/usr/bin/env python3
"""NFFEEDS_V1 (2026-11-03, Justin: "More sources"). The Newsfile collector read three industry feeds (mining-metals,
precious-metals, non-ferrous-metals). A read-only probe on 2026-11-03 found two more Newsfile industry feeds full of
companies on MNT's coverage list that are in none of the three: energy-metals (7 of its last 10: PMI, GIGA, CVW, OSM,
RBZ, MN) and rare-earths (7 of 10: SCD, SAGA, XIM, MAV, SCLT, NEXX); and 'energy' (3 of 10: STND, GEL, CVW, the rest
oil and gas). Those releases were found only by the company-feed backstop (466 feeds, ~93 min a cycle), after the
exchange path had already published the PDF (e.g. CVW Nov 2, found 5 h later).
This reads them too, every 2 minutes like the others, but keeps only releases whose ticker (from the feed's opening
text) is on the coverage list (tickers.json), so oil-and-gas releases never reach MNT, and never triggers the
overflow backstop from these feeds. Everything after that (short versions, page reads, duplicate checks) is unchanged.
  patch_nffeeds.py --build OUT | --install OUT"""
import datetime as dt, hashlib, os, py_compile, shutil, sys
APP = "/opt/mnt/app"; F = "sync_newsfile_direct.py"; EXPECT = "d8fdc9a3c9ccad22"
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
def sub1(s, old, new):
    if s.count(old) != 1: sys.exit("REFUSED: expected text found %d times: %r" % (s.count(old), old[:70]))
    return s.replace(old, new)
def build(out):
    if sha(f"{APP}/{F}") != EXPECT: sys.exit("REFUSED: live %s is %s" % (F, sha(f"{APP}/{F}")))
    os.makedirs(out, exist_ok=True); s = open(f"{APP}/{F}").read()
    s = sub1(s, 'COMPANY_FEED = "https://feeds.newsfilecorp.com/company/{cid}"\n',
             '# NFFEEDS_V1 (2026-11-03): more industry feeds; only releases from companies on the coverage list are kept.\n'
             'EXTRA_FEEDS = [\n'
             '    "https://feeds.newsfilecorp.com/industry/energy-metals",\n'
             '    "https://feeds.newsfilecorp.com/industry/rare-earths",\n'
             '    "https://feeds.newsfilecorp.com/industry/energy",\n'
             ']\n'
             'COMPANY_FEED = "https://feeds.newsfilecorp.com/company/{cid}"\n')
    s = sub1(s, '        for f in FEEDS:\n            try:\n                got = parse_feed(fetch_feed(f))\n',
             '        covered = _covered_bares()                       # NFFEEDS_V1\n'
             '        for f in FEEDS + EXTRA_FEEDS:\n            try:\n                got = parse_feed(fetch_feed(f))\n'
             '                if f in EXTRA_FEEDS:                       # NFFEEDS_V1: coverage-list companies only\n'
             '                    got = [g for g in got if (extract_ticker(g.get("teaser") or "")[0] or "").split(".")[0].upper()\n'
             '                           in covered]\n')
    s = sub1(s, '            if feed_overflowed(last.get(f), rids):\n',
             '            if f not in EXTRA_FEEDS and feed_overflowed(last.get(f), rids):\n')
    s = sub1(s, '# ------------------------------------------------------------------ feeds run (timer, every 2 min)\n',
             'def _covered_bares() -> set:\n'
             '    """NFFEEDS_V1: bare tickers of the coverage list (tickers.json, not excluded); empty set if unreadable."""\n'
             '    try:\n'
             '        rows = json.loads(TICKERS_JSON.read_text())\n'
             '        rows = rows.get("tickers") or list(rows.values()) if isinstance(rows, dict) else rows\n'
             '        return {str(r.get("ticker") or "").split(".")[0].upper() for r in rows\n'
             '                if isinstance(r, dict) and r.get("ticker") and not (r.get("exclude_auto") or r.get("excluded"))}\n'
             '    except (OSError, ValueError):\n'
             '        return set()\n\n\n'
             '# ------------------------------------------------------------------ feeds run (timer, every 2 min)\n')
    open(f"{out}/{F}", "w").write(s)
    py_compile.compile(f"{out}/{F}", doraise=True, cfile=f"{out}/__pycache__/{F}c")
    print("built", out, sha(f"{out}/{F}"))
def install(out):
    if sha(f"{APP}/{F}") != EXPECT: sys.exit("REFUSED: live %s changed (%s)" % (F, sha(f"{APP}/{F}")))
    TS = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"); B = f"/var/backups/mnt/nffeeds-{TS}"; os.makedirs(B)
    shutil.copy2(f"{APP}/{F}", f"{B}/{F}")
    open(f"{B}/undo.sh", "w").write(f"#!/bin/sh\nset -e\ncp -p {B}/{F} {APP}/{F}\necho 'NFFEEDS_V1 undone'\n")
    st = os.stat(f"{APP}/{F}"); tmp = f"{APP}/.{F}.nf.tmp"
    shutil.copyfile(f"{out}/{F}", tmp); os.chown(tmp, st.st_uid, st.st_gid); os.chmod(tmp, st.st_mode & 0o777)
    os.replace(tmp, f"{APP}/{F}")
    print("installed", sha(f"{APP}/{F}"), "backup", B, "| undo: sh", B + "/undo.sh")
if __name__ == "__main__":
    if os.uname().nodename != "mnt-scraper-01": sys.exit("REFUSED: wrong host")
    {"--build": build, "--install": install}[sys.argv[1]](sys.argv[2])
