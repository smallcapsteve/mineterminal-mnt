"""sync_accesswire.py -- collect Accesswire mining releases.

Primary path (2026-09-09): render Accesswire's own metals-and-mining newsroom
with the browser already installed on this box, and fetch each release body the
same way. Cloudflare returns a 403 challenge to a plain fetch; a rendered page
returns the article. This replaces Google News as the discovery mechanism and
gives us real article bodies instead of a placeholder sentence.

Fallback: the previous Google News path, kept deliberately. If rendering ever
stops working the collector degrades to the old behaviour rather than to
nothing.

Run:  sync_accesswire.py [days] [--dry-run] [--limit N] [--pages N]
"""
from __future__ import annotations
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, "/opt/mnt/app")

from sources import accesswire as aw            # noqa: E402
from sources import accesswire_gnews as anw     # noqa: E402
from portal import db as pdb                    # noqa: E402

TICKERS_PATH = "/opt/mnt/app/tickers.json"
TIME_BUDGET_S = 480          # a run must not outlast its hourly timer
DEFAULT_LIMIT = 40
DEFAULT_PAGES = 2


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())[:120]


def find_fuzzy_dupe(conn: sqlite3.Connection, ticker: str, headline: str,
                    published_at: str, window_hours: int = 48) -> str | None:
    """Same-story check. Needed because the old Google News path stored some of
    these releases already, under a different URL."""
    if not ticker or not headline or not published_at:
        return None
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    lo = (dt - timedelta(hours=window_hours)).strftime("%Y-%m-%dT%H:%M:%S")
    hi = (dt + timedelta(hours=window_hours)).strftime("%Y-%m-%dT%H:%M:%S")
    norm = _normalize(headline)
    rows = conn.execute(
        "SELECT event_id, raw_headline FROM events "
        "WHERE ticker = ? AND published_at >= ? AND published_at <= ?",
        (ticker, lo, hi),
    ).fetchall()
    for eid, rhl in rows:
        rnorm = _normalize(rhl)
        if not rnorm:
            continue
        if len(norm) >= 30 and len(rnorm) >= 30 and norm[:60] == rnorm[:60]:
            return eid
        if rnorm.startswith(norm[:50]) or norm.startswith(rnorm[:50]):
            return eid
    return None


def _known_urls(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT source_url FROM events WHERE source_name LIKE '%access%' AND source_url IS NOT NULL"
    )}


def run_rendered(days: int, dry_run: bool, limit: int, pages: int) -> int:
    """Returns the number of releases ingested; -1 if discovery itself failed."""
    started = time.time()
    tickers = json.load(open(TICKERS_PATH))
    name_index = anw.build_company_index(tickers)
    print(f"[accesswire] company-name index: {len(name_index)} entries")

    try:
        items = aw.list_sector_recent(pages=pages, limit=limit)
    except Exception as e:
        print(f"[accesswire] RENDERED DISCOVERY FAILED: {e}")
        return -1
    print(f"[accesswire] discovered {len(items)} mining releases from the sector newsroom")
    if not items:
        return -1

    conn = pdb.get_conn()
    seen_urls = _known_urls(conn)

    # Every stage counts what it dropped. The old collector counted only what it
    # ingested, which is why an 87% loss went unnoticed for months.
    n_known = n_body_fail = n_no_ticker = n_dupe = n_ingested = n_err = 0

    for it in items:
        if time.time() - started > TIME_BUDGET_S:
            print("[accesswire] time budget reached; stopping this run early")
            break
        url = it["source_url"]
        if url in seen_urls:
            n_known += 1
            continue
        try:
            ev = aw.fetch_body(dict(it))
        except Exception as e:
            n_err += 1
            print(f"  ! fetch_body {url[:80]}: {e}")
            continue
        if ev.get("fetch_error") or not ev.get("raw_body"):
            n_body_fail += 1
            print(f"  ! no body {url[:80]} {ev.get('fetch_error', '')}")
            continue

        headline = ev.get("raw_headline") or ""
        ticker = anw.resolve_ticker(headline, name_index)
        if not ticker:
            n_no_ticker += 1
            print(f"  - no ticker: {headline[:80]}")
            continue

        published = ev.get("published_at") or ""
        if find_fuzzy_dupe(conn, ticker, headline, published):
            n_dupe += 1
            continue

        record = {
            "event_id":      aw.event_id_for(url, published),
            "ticker":        ticker,
            "event_type":    "news_release",
            "source_name":   "accessnewswire",
            "source_url":    url,
            "raw_headline":  headline,
            "raw_body":      ev.get("raw_body", ""),
            "raw_html":      ev.get("raw_html", ""),
            "raw_excerpt":   ev.get("raw_excerpt", ""),
            "published_at":  published,
            "review_status": "auto_approved",
        }
        if dry_run:
            n_ingested += 1
            print(f"  [dry-run] {ticker:10s} {len(record['raw_body']):6d} chars  {headline[:66]}")
            continue
        try:
            pdb.upsert_event(record)
            n_ingested += 1
            print(f"  + {ticker:10s} {len(record['raw_body']):6d} chars  {headline[:66]}")
        except Exception as e:
            n_err += 1
            print(f"  X {ticker}: {e}")

    print(f"[accesswire] RENDERED DONE  ingested={n_ingested} already_held={n_known} "
          f"no_ticker={n_no_ticker} no_body={n_body_fail} dupe={n_dupe} errors={n_err} "
          f"elapsed={time.time() - started:.0f}s")
    return n_ingested


def run_gnews_fallback(days: int, dry_run: bool) -> int:
    """The pre-2026-09-09 path. Discovery via Google News, placeholder bodies."""
    print("[accesswire] FALLING BACK to Google News discovery")
    tickers = json.load(open(TICKERS_PATH))
    name_index = anw.build_company_index(tickers)
    items = list(anw.list_mining_events(name_index, days=days))
    print(f"[accesswire] gnews items resolved to known tickers: {len(items)}")
    conn = pdb.get_conn()
    ingested = dup_skip = 0
    for ev in items:
        if find_fuzzy_dupe(conn, ev["ticker"], ev["raw_headline"], ev["published_at"]):
            dup_skip += 1
            continue
        if dry_run:
            ingested += 1
            continue
        try:
            pdb.upsert_event(ev)
            ingested += 1
        except Exception as e:
            print(f"  X {ev['ticker']}: {e}")
    print(f"[accesswire] GNEWS DONE  ingested={ingested}  fuzzy_dup_skip={dup_skip}")
    return ingested


def main(days: int = 14, dry_run: bool = False,
         limit: int = DEFAULT_LIMIT, pages: int = DEFAULT_PAGES) -> int:
    print(f"[sync_accesswire] start days={days} dry_run={dry_run} limit={limit} pages={pages}")
    try:
        n = run_rendered(days, dry_run, limit, pages)
        if n < 0:
            run_gnews_fallback(days, dry_run)
    finally:
        aw.close_browser()
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    dry = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    consumed = set()

    def _opt(flag, default):
        if flag in args:
            i = args.index(flag)
            if i + 1 < len(args):
                consumed.add(i + 1)
                return int(args[i + 1])
        return default

    lim = _opt("--limit", DEFAULT_LIMIT)
    pg = _opt("--pages", DEFAULT_PAGES)
    positional = [a for i, a in enumerate(args)
                  if i not in consumed and not a.startswith("--") and a.isdigit()]
    d = int(positional[0]) if positional else 14
    sys.exit(main(days=d, dry_run=dry, limit=lim, pages=pg))
