#!/usr/bin/env python3
"""PDFHTML_V1 job — rebuild HTML for exchange-path releases (MNT, 2026-10-02).

For every event with no raw_html whose source_url is a PDF/DOCX (TMX filings,
CSE), fetch the document, run pdf_html.pdf_to_html, sanitise it, and store it
in /opt/mnt/app/data/release_html.db (table release_html). Nothing in
portal.db is written. The page reads the side store through
release_format.pdf_html_for().

  pdfhtml_job.py --dry-run --limit 20 --show 3   # convert, print, store nothing
  pdfhtml_job.py --apply --limit 400             # convert and store
  pdfhtml_job.py --apply --since-days 3          # what the timer runs
  pdfhtml_job.py --stats
  pdfhtml_job.py --apply --since-days 4 --catch-up --limit 300   # timer, CATCHUP_V1
  pdfhtml_job.py --list --since-days 4 --catch-up                # what the timer would take; converts nothing

CATCHUP_V1 (2026-10-06): --catch-up also takes rows that were ADDED to portal.db
since the last run (rowid above a high-water mark kept in release_html.db,
table job_meta) and have no store row at all, whatever their published date -
e.g. old releases back-imported by another job. Rows already 'failed' are not
retried outside the --since-days window, so dead links are fetched once.
Skipped while a full backfill/second pass unit is running (they cover it).

Undo: delete /opt/mnt/app/data/release_html.db (pages fall back to the text
reflow) — or set status='off' for a row.

Quality gate per release (status 'rejected' rather than shown):
  * the rebuilt text must keep >= 90% of the stored raw_body's letters/digits
    (we never show less of a release than before);
  * it must be non-trivial (>= 200 chars of text).
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import re
import sqlite3
import sys
import time
import urllib.request

sys.path.insert(0, "/opt/mnt/app")
try:                                   # a copy beside this script wins (dry runs from a payload dir)
    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
    import pdf_html                                          # noqa: E402
except ImportError:
    from portal import pdf_html                              # noqa: E402
from portal.html_sanitize import sanitize_release_html      # noqa: E402

PORTAL_DB = "/opt/mnt/app/portal/portal.db"
STORE = "/opt/mnt/app/data/release_html.db"
UA = "Mozilla/5.0 (compatible; MiningNewsTerminal/1.0; +https://miningnewsterminal.com)"
PAUSE_S = 1.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS release_html (
  event_id   TEXT PRIMARY KEY,
  status     TEXT NOT NULL,         -- ok | rejected | failed | off
  html       TEXT,
  version    TEXT,
  reason     TEXT,
  text_ratio REAL,
  n_tables   INTEGER,
  made_at    TEXT
);
"""


def store():
    c = sqlite3.connect(STORE, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    return c


def letters(s: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]", s or ""))


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read(25_000_000)


FULL = "SELECT event_id, raw_headline, raw_body, source_url, source_name, published_at FROM events WHERE event_id=?"


def candidates(pcon, since_days: int | None, limit: int, redo: bool, st):
    """Event ids only (newest first) - the full backfill is ~123K rows, so bodies are read one at a time."""
    q = ("SELECT event_id FROM events "
         "WHERE (raw_html IS NULL OR raw_html='') AND raw_body IS NOT NULL AND raw_body!='' "
         "AND source_url IS NOT NULL AND source_url!='' ")
    args = []
    if since_days is not None:
        q += "AND published_at >= ? "
        args.append((dt.datetime.utcnow() - dt.timedelta(days=since_days)).strftime("%Y-%m-%d"))
    q += "ORDER BY published_at DESC"
    done = set() if redo else {r[0] for r in st.execute("SELECT event_id FROM release_html WHERE status IN ('ok','rejected','off')")}
    n = 0
    for r in pcon.execute(q, args):
        if r[0] in done:
            continue
        yield r
        n += 1
        if limit and n >= limit:
            return


META = "CREATE TABLE IF NOT EXISTS job_meta (k TEXT PRIMARY KEY, v TEXT);"
CATCHUP_INITIAL_HWM = 140000      # below every row the 10-06 second pass picked up (lowest 140,668)
CATCHUP_MARGIN = 2000             # re-look this many rowids below the mark (rowid reuse, slow writers)
OTHER_JOBS = ("mnt-pdfhtml-backfill", "mnt-pdfhtml-pass2")
CAND_WHERE = ("(raw_html IS NULL OR raw_html='') AND raw_body IS NOT NULL AND raw_body!='' "
              "AND source_url IS NOT NULL AND source_url!=''")


def other_job_running() -> str | None:
    import subprocess
    for u in OTHER_JOBS:
        try:
            if subprocess.run(["systemctl", "is-active", "--quiet", u], timeout=10,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                return u
        except Exception:  # noqa: BLE001
            pass
    return None


def catchup_ids(pcon, st):
    """Rows added since the last completed catch-up (rowid > mark - margin) with no store row at all."""
    try:
        r = st.execute("SELECT v FROM job_meta WHERE k='catchup_hwm'").fetchone()
    except sqlite3.OperationalError:
        r = None
    hwm = int(r[0]) if r else CATCHUP_INITIAL_HWM
    top = pcon.execute("SELECT max(rowid) FROM events").fetchone()[0] or 0
    seen = {x[0] for x in st.execute("SELECT event_id FROM release_html")}
    # rowid range only - no ORDER BY in SQL, so SQLite walks the rowid range, not the 15 GB table
    rows = pcon.execute(f"SELECT event_id, published_at FROM events WHERE rowid > ? AND {CAND_WHERE}",
                        (max(0, hwm - CATCHUP_MARGIN),)).fetchall()
    ids = [e for e, p in sorted(rows, key=lambda x: x[1] or "", reverse=True) if e not in seen]
    return ids, hwm, top


def convert(row) -> tuple[str, str, str, float, int]:
    eid, headline, body, url, src, pub = row
    try:
        data = fetch(url)
    except Exception as e:  # noqa: BLE001
        return "failed", "", f"fetch {type(e).__name__}: {str(e)[:80]}", 0.0, 0
    if not data[:5].startswith(b"%PDF"):
        return "failed", "", f"not a pdf ({data[:6]!r})", 0.0, 0
    try:
        h = pdf_html.pdf_to_html(data, headline or "")
    except Exception as e:  # noqa: BLE001
        return "failed", "", f"convert {type(e).__name__}: {str(e)[:80]}", 0.0, 0
    h = sanitize_release_html(h)
    txt = re.sub(r"<[^>]+>", " ", h)
    ratio = letters(txt) / max(1, letters(body) - letters(headline or ""))
    ntab = h.count("<table")
    if letters(txt) < 150:
        return "rejected", h, "too little text", ratio, ntab
    if ratio < 0.90:
        return "rejected", h, f"kept only {ratio:.0%} of the stored text", ratio, ntab
    return "ok", h, "", ratio, ntab


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--stats", action="store_true")
    g.add_argument("--list", action="store_true", help="print the candidates and stop (reads the real store read-only)")
    ap.add_argument("--catch-up", action="store_true", help="also take newly added rows of any date (CATCHUP_V1)")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--since-days", type=int)
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--event")
    ap.add_argument("--show-tables", action="store_true", help="--show only releases that produced a table")
    a = ap.parse_args()

    if a.list:                         # read-only view of the real store
        st = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True, timeout=30)
    elif a.dry_run:                    # never create the store from a dry run (or as root)
        st = sqlite3.connect(":memory:")
        st.executescript(SCHEMA)
    else:
        st = store()
        st.executescript(META)
    if a.stats:
        for r in st.execute("SELECT status, count(*), round(avg(text_ratio),3), sum(n_tables) FROM release_html GROUP BY status"):
            print(r)
        return 0
    pcon = sqlite3.connect(f"file:{PORTAL_DB}?mode=ro", uri=True, timeout=30)
    advance_to = None
    if a.event:
        ids = [a.event]
    else:
        ids = [r[0] for r in candidates(pcon, a.since_days, a.limit, a.redo, st)]
        if a.catch_up:
            busy = other_job_running()
            if busy and not a.list:
                print(f"CATCHUP skipped: {busy} is running", flush=True)
            else:
                extra, hwm, top = catchup_ids(pcon, st)
                have = set(ids)
                extra = [e for e in extra if e not in have]
                room = (a.limit - len(ids)) if a.limit else len(extra)
                take = extra[:max(0, room)]
                ids += take
                if len(take) == len(extra):    # every new row gets tried this run -> move the mark
                    advance_to = top
                print(f"CATCHUP mark={hwm} top={top} new_unseen={len(extra)} taken={len(take)}"
                      f"{' busy=' + busy if busy else ''}", flush=True)
    print(f"CANDIDATES {len(ids)}", flush=True)
    if a.list:
        for eid in ids[:15]:
            r = pcon.execute("SELECT published_at, source_name, rowid, substr(raw_headline,1,60) FROM events WHERE event_id=?", (eid,)).fetchone()
            print("  ", eid[:12], r)
        return 0
    tally = {}
    shown = 0
    t0 = time.time()
    for n, eid in enumerate(ids, 1):
        row = pcon.execute(FULL, (eid,)).fetchone()
        if row is None:
            continue
        status, h, reason, ratio, ntab = convert(row)
        tally[status] = tally.get(status, 0) + 1
        print(f"{n:6} {status:8} {ratio:5.2f} tables={ntab} {row[4]} {(row[5] or '')[:10]} {row[0][:12]} {(row[1] or '')[:60]!r} {reason}", flush=True)
        if n % 500 == 0:
            print("PROGRESS", n, len(ids), tally, "secs", round(time.time() - t0), flush=True)
        if a.show and shown < a.show and (ntab or not a.show_tables):
            print("-----8<-----\n" + h[:6000] + "\n-----8<-----")
            shown += 1
        if a.apply:
            st.execute("INSERT OR REPLACE INTO release_html VALUES (?,?,?,?,?,?,?,?)",
                       (row[0], status, h if status != "failed" else None, pdf_html.VERSION, reason,
                        round(ratio, 4), ntab, dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"))
            st.commit()
        time.sleep(PAUSE_S)
    if a.apply and advance_to is not None:
        st.execute("INSERT OR REPLACE INTO job_meta VALUES ('catchup_hwm', ?)", (str(advance_to),))
        st.commit()
        print("CATCHUP mark ->", advance_to, flush=True)
    print("TALLY", tally, "secs", round(time.time() - t0, 1), "mode", "apply" if a.apply else "dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
