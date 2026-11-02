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


# AW_BODYTICK_V1: fallback ticker from the exchange tag in the release body.
_EX_TAG = re.compile(r"\b(TSX[\s\-]?V(?:enture)?(?:\s+Exchange)?|TSXV|TSX|CSE|CNSX)\s*[:\-]\s*([A-Z][A-Z0-9]{0,5}(?:\.[A-Z])?)\b")
_SUF = {"TSXV": ".V", "TSX": ".TO", "CSE": ".CN", "CNSX": ".CN"}
_STOPW = {"the", "inc", "corp", "corporation", "ltd", "limited", "resources", "mining", "minerals", "gold", "silver",
          "metals", "exploration", "energy", "copper", "company", "group", "plc", "capital", "ventures", "royalties",
          "royalty", "lithium", "uranium"}


def _name_word(name: str) -> str:
    ws = [w for w in re.findall(r"[A-Za-z0-9]+", name or "") if len(w) >= 3 and w.lower() not in _STOPW]
    return ws[0].lower() if ws else ""


def body_ticker(headline: str, body: str, names: dict) -> str | None:
    """AW_BODYTICK_V1: {ticker: name} from tickers.json -> the issuer's ticker from the FIRST exchange tag in the
    body, if it is a known company whose name word appears in the headline or in the 150 characters before the tag."""
    text = (body or "")[:1500]
    m = _EX_TAG.search(text)
    if not m:
        return None
    up = m.group(1).upper()
    ex = "CSE" if up in ("CSE", "CNSX") else ("TSXV" if "V" in up[3:] else "TSX")
    t = m.group(2).upper() + _SUF.get(ex, "")
    if t not in names:
        return None
    w = _name_word(names[t])
    near = ((headline or "") + " " + text[max(0, m.start() - 150):m.start()]).lower()
    return t if w and w in near else None


NOTICK_FILE = "/opt/mnt/app/data/accesswire_noticker.json"   # AW_NOTICK_MEMO_V1
NOTICK_TTL_S = 3 * 86400


def _notick_load() -> dict:
    try:
        d = json.load(open(NOTICK_FILE))
        now = time.time()
        return {u: t for u, t in d.items() if now - float(t) < NOTICK_TTL_S}
    except Exception:
        return {}


def _notick_save(d: dict) -> None:
    try:
        import os as _os
        tmp = NOTICK_FILE + ".tmp"
        json.dump(d, open(tmp, "w"))
        _os.replace(tmp, NOTICK_FILE)
    except Exception as e:
        print(f"[accesswire] no-ticker memo not saved: {e}")


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
    tick_names = {r.get("ticker"): r.get("name") or "" for r in tickers if isinstance(r, dict) and r.get("ticker")}  # AW_BODYTICK_V1

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
    notick = _notick_load()                              # AW_NOTICK_MEMO_V1
    n_memo = 0

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
        if url in notick:                                # AW_NOTICK_MEMO_V1
            n_memo += 1
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
        if not ticker:                                   # AW_BODYTICK_V1
            ticker = body_ticker(headline, ev.get("raw_body") or "", tick_names)
            if ticker:
                print(f"  ~ ticker from body tag {ticker}: {headline[:60]}")
        if not ticker:
            n_no_ticker += 1
            print(f"  - no ticker: {headline[:80]}")
            notick[url] = time.time()                    # AW_NOTICK_MEMO_V1
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

    if not dry_run:                                      # AW_NOTICK_MEMO_V1
        _notick_save(notick)
    print(f"[accesswire] no-ticker memo: {len(notick)} remembered, {n_memo} skipped this run")
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
        # INGEST_FIX3_V1 (2026-10-12): this path stores a placeholder body when the plain fetch is refused
        # (Cloudflare); 115 of 236 AccessNewswire releases since June had no text. Try the rendered fetch the main
        # path uses first. A placeholder still stored is re-fetched by body_repair.py at the end of a later run.
        if (ev.get("raw_body") or "").startswith("This release is published on Accesswire.") \
                and "accessnewswire.com" in (ev.get("source_url") or ""):
            try:
                got = aw.fetch_body({"source_url": ev["source_url"], "raw_headline": ev.get("raw_headline"),
                                     "published_at": ev.get("published_at")})
                if not got.get("fetch_error") and len(got.get("raw_body") or "") > 400:
                    ev["raw_body"] = got["raw_body"]
                    ev["raw_html"] = got.get("raw_html") or ev.get("raw_html")
                    ev["raw_excerpt"] = got.get("raw_excerpt") or ev.get("raw_excerpt")
            except Exception as e:
                print(f"  ! rendered fetch {ev['source_url'][:80]}: {e}")
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
        # INGEST_FIX3_V1 (2026-10-12): placeholders stored by the fallback (in this run or earlier) are re-fetched with
        # the rendered fetch, a few per run. Old text kept in data/body_repair.db; undo: body_repair.py --restore TAG.
        if not dry_run:
            try:
                import body_repair
                body_repair.main(["--accesswire", "--since", (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d"),
                                  "--tag", "fix3-aw-auto-" + datetime.utcnow().strftime("%Y%m%d"),
                                  "--limit", "15", "--show", "5", "--sleep", "1"])
            except Exception as e:  # noqa: BLE001
                print(f"[accesswire] placeholder repair skipped: {type(e).__name__}: {e}")
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
