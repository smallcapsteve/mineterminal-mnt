#!/usr/bin/env python3
"""ROYTERMS_V1 (2026-10-12) - read royalty & stream terms from every release with a royalty row (C8 step 3).

For each release in royalty_deals (type set), takes the release text the way the labelled sets were built
(longest of raw_body / raw_excerpt / raw_html with tags removed, page-builder shortcodes dropped, trailing
boilerplate cut after 35% of the text, whitespace collapsed), runs portal/royterms_reader.py's read(), and stores
the record in portal.db `royalty_terms` (one row per release; re-read when the reader file changes).

  royterms_job.py              new releases and releases read by an older reader version (default; for the timer)
  royterms_job.py --all        re-read everything
  royterms_job.py --dry-run    read, print a summary, write nothing
  royterms_job.py --event ID   one release, printed (no write)

Justin, 2026-10-12: "The rules reader as-is" (blind check: royalties P 92 / R 69, payments P 54 / R 30, terms P 81
/ R 44). Writes are short transactions of up to 100 rows; waits while the backfill guard says the sites are slow.
"""
import argparse
import hashlib
import html
import json
import os
import re
import signal
import sqlite3
import sys
import time

APP = os.environ.get("ROYTERMS_APP", "/opt/mnt/app")
DB = APP + "/portal/portal.db"
READER = APP + "/portal/royterms_reader.py"
GUARD = "/var/lib/mnt-health/guard.state"
VERSION = "royterms-1.0.0"
sys.path.insert(0, APP + "/portal")

DDL = """CREATE TABLE IF NOT EXISTS royalty_terms (
  event_id TEXT PRIMARY KEY, ticker TEXT, version TEXT, reader_sha TEXT, read_at TEXT,
  n_interests INTEGER, n_considerations INTEGER, n_terms INTEGER, secs REAL, doc TEXT, error TEXT)"""

TAG = re.compile(r"<[^>]+>")
CUT = re.compile(r"(?:Cautionary (?:Note|Statement)[^.]{0,80}Forward|Forward[- ]Looking (?:Statements|Information)\s*(?:This|Certain|Except|Some|All|Statements)"
                 r"|Neither (?:the )?TSX Venture Exchange nor its Regulation Services Provider|Neither the Canadian Securities Exchange"
                 r"|NOT FOR DISTRIBUTION TO U\.S\.|For further information(?:, please contact)?\s*:?)", re.I)
SHORT = re.compile(r"\[/?vc_[^\]]*\]|\[/?et_pb[^\]]*\]")


def clean(s):
    if s and s.lstrip().startswith("<"):
        s = TAG.sub(" ", s)
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def release_text(body, excerpt, raw_html):
    parts = [clean(x) for x in (body, excerpt, raw_html) if x]
    t = max(parts, key=len) if parts else ""
    t = SHORT.sub(" ", t)
    for m in CUT.finditer(t):
        if m.start() > 0.35 * len(t):
            t = t[:m.start()] + " [... boilerplate removed ...]"
            break
    return re.sub(r"\s+", " ", t).strip()


class Slow(Exception):
    pass


def _alarm(*_):
    raise Slow()


def guard_wait():
    for _ in range(40):
        try:
            if "mode=throttled" not in open(GUARD).read():
                return
        except OSError:
            return
        time.sleep(30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--event")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    import royterms_reader as R
    sha = hashlib.sha256(open(READER, "rb").read()).hexdigest()[:16]
    c = sqlite3.connect(DB, timeout=60)
    c.execute("PRAGMA busy_timeout=60000")
    if not a.dry_run and not a.event:
        c.execute(DDL)
        c.commit()
    if a.event:
        ids = [a.event]
    else:
        ids = [r[0] for r in c.execute("SELECT DISTINCT event_id FROM royalty_deals WHERE type IS NOT NULL")]
        if not a.all and not a.dry_run:
            done = {r[0] for r in c.execute("SELECT event_id FROM royalty_terms WHERE reader_sha=?", (sha,))}
            ids = [e for e in ids if e not in done]
    if a.limit:
        ids = ids[:a.limit]
    print("reader", sha, VERSION, "releases to read:", len(ids), flush=True)
    signal.signal(signal.SIGALRM, _alarm)
    t0 = time.time()
    stats = {"read": 0, "with_interest": 0, "with_terms": 0, "with_paid": 0, "errors": 0, "empty_text": 0}
    times = []
    buf = []

    def flush():
        if buf and not a.dry_run and not a.event:
            guard_wait()
            c.executemany("INSERT OR REPLACE INTO royalty_terms (event_id, ticker, version, reader_sha, read_at, n_interests,"
                          " n_considerations, n_terms, secs, doc, error) VALUES (?,?,?,?,?,?,?,?,?,?,?)", buf)
            c.commit()
        buf.clear()

    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        rows = c.execute("SELECT event_id, ticker, raw_headline, raw_body, raw_excerpt, raw_html FROM events WHERE event_id IN (%s)"
                         % ",".join("?" * len(chunk)), chunk).fetchall()
        for ev, tk, hl, body, ex, rh in rows:
            text = release_text(body, ex, rh)
            err, doc, secs = None, {"interests": [], "considerations": [], "terms": []}, 0.0
            if not text:
                stats["empty_text"] += 1
            else:
                t1 = time.time()
                signal.alarm(30)
                try:
                    r = R.read(hl or "", text, tk or "")
                    doc = {"interests": r.get("interests") or [], "considerations": r.get("considerations") or [],
                           "terms": r.get("terms") or []}
                except Slow:
                    err = "timeout 30s"
                except Exception as e:   # one bad release must not stop the run
                    err = "%s: %s" % (type(e).__name__, str(e)[:200])
                finally:
                    signal.alarm(0)
                secs = time.time() - t1
                times.append(secs)
            stats["read"] += 1
            stats["errors"] += bool(err)
            stats["with_interest"] += bool(doc["interests"])
            stats["with_terms"] += bool(doc["terms"])
            stats["with_paid"] += bool(doc["considerations"])
            if a.event:
                print(json.dumps({"event_id": ev, "headline": hl, "chars": len(text), "error": err, "doc": doc}, indent=1))
            buf.append((ev, tk, VERSION, sha, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), len(doc["interests"]),
                        len(doc["considerations"]), len(doc["terms"]), round(secs, 4), json.dumps(doc, ensure_ascii=False), err))
            if len(buf) >= 100:
                flush()
        print("..", min(i + 200, len(ids)), "of", len(ids), "secs", round(time.time() - t0, 1), flush=True)
    flush()
    if times:
        times.sort()
        stats["mean_s"] = round(sum(times) / len(times), 4)
        stats["max_s"] = round(times[-1], 3)
    stats["secs"] = round(time.time() - t0, 1)
    print("ROYTERMS_DONE", json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
