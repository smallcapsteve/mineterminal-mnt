#!/usr/bin/env python3
"""EXCHANGE_NEWS_V1 — the exchange as the register of what each company published.

Justin, 2026-09-13: *"can we also make a new path, which will be the first
path/checklist which is scraping thecse.com company specific links for CSE
listed companies and money.tmx.com for TSX & TSXV companies?"*

**Why this exists.** Every other collector infers which company a release
belongs to. The wire firehose reads a whole newswire and works the ticker out of
the text; the per-company adapters at least start from the company but reach it
through Google News. That inference is the root of H5 (25 of 40 Accesswire
releases credited to nobody), H7, the 82 events attributed to companies nobody
watched, and the misattribution guard that costs a price and a description in
C25.

The exchanges do not infer. A release on the CSE's own feed for ACRE carries
`mainSymbol: "ACRE"`; a filing in TMX's list for LUN is LUN's. **This path is the
only one in the system where the ticker is stated by the authority rather than
guessed.**

**What it does — a checklist, not a fourth firehose** (Justin's choice):

  1. Ask each exchange what the company published in the window.
  2. Match each release against what MNT already collected.
  3. Where a wire got there first, record the match — and flag it if the wire
     filed it under a different ticker, because that is an attribution error we
     could not otherwise see.
  4. Only where nothing matched: fetch the PDF, extract the text, classify, and
     ingest it.

So it re-collects nothing the wires already deliver, and the count it reports —
"the wires missed N of M releases" — is a coverage measure that has never
existed.

**Sources.**
  CSE      website-data-api-v2.thecse.com/api/news-releases?companyId=<id>
           company ids come from the CSE filings collector's own `symbols`
           table, already maintained for ~348 companies.
  TSX/TSXV `data/tmx_filings.db`, category "News releases" — the company's own
           disclosure as filed, already refreshed every 4 hours.
           **Deliberately NOT money.tmx.com's News tab**, which returns
           SeekingAlpha and Motley Fool commentary via QuoteMedia ("Best 3
           Copper Stocks To Buy For The AI Boom" was the top item for Lundin).
           That is not issuer news and must not be ingested as if it were.

Run:
    python3 exchange_news.py --dry-run           # look, change nothing
    python3 exchange_news.py --apply             # reconcile + fill gaps
    python3 exchange_news.py --apply --no-ingest # reconcile only
    python3 exchange_news.py --stats
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request

APP_ROOT = "/opt/mnt/app"
sys.path.insert(0, APP_ROOT)

import universe_client  # noqa: E402

DB_PATH = os.environ.get("EXCHANGE_NEWS_DB", f"{APP_ROOT}/data/exchange_news.db")
PORTAL_DB = "/opt/mnt/app/portal/portal.db"
CSE_SYMBOLS_DB = "/root/minetracker/data/cse_filings.db"
TMX_FILINGS_DB = "/root/minetracker/data/tmx_filings.db"
CSE_API = "https://website-data-api-v2.thecse.com/api/news-releases?companyId={}&locale=en"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.2 Safari/605.1.15")

DEFAULT_DAYS = 14
DEFAULT_MAX_INGEST = 25      # a first run must not flood the site
FETCH_TIMEOUT_S = 25
PDF_MAX_BYTES = 12 * 1024 * 1024

SCHEMA = """
CREATE TABLE IF NOT EXISTS releases (
    uid            TEXT PRIMARY KEY,
    ticker         TEXT NOT NULL,      -- universe symbol, e.g. ACRE.CN
    bare           TEXT NOT NULL,
    exchange       TEXT,
    source         TEXT NOT NULL,      -- 'cse' | 'tmx'
    published_date TEXT NOT NULL,
    title          TEXT,
    url            TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',
       -- pending | matched | ingested | no_body | error | skipped
    matched_event  TEXT,
    wrong_ticker   TEXT,               -- the ticker a wire filed it under, if different
    note           TEXT,
    first_seen     TEXT DEFAULT CURRENT_TIMESTAMP,
    acted_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_rel_status ON releases(status, published_date DESC);
CREATE INDEX IF NOT EXISTS idx_rel_ticker ON releases(bare, published_date DESC);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, mode TEXT,
    seen INTEGER, matched INTEGER, ingested INTEGER, failed INTEGER,
    wrong_ticker INTEGER, note TEXT
);
"""


def log(msg: str) -> None:
    print(f"[{dt.datetime.utcnow().isoformat()}Z] {msg}", flush=True)


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def bare(sym: str) -> str:
    return (sym or "").split(".")[0].upper()


def uid_for(source: str, ticker: str, date: str, title: str) -> str:
    import hashlib
    h = hashlib.sha1()
    h.update("|".join([source, ticker, date[:10], norm(title)[:80]]).encode())
    return h.hexdigest()


def http_get(url: str, timeout: int = FETCH_TIMEOUT_S) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(PDF_MAX_BYTES)


# --------------------------------------------------------------------------
# who is on which exchange
# --------------------------------------------------------------------------

def universe_by_exchange() -> tuple[dict, dict]:
    """(cse, tsx) mapping bare ticker -> universe row."""
    cse, tsx = {}, {}
    for c in universe_client.load():
        ex = (c.get("exchange") or "").upper()
        b = bare(c.get("ticker") or "")
        if not b:
            continue
        if ex == "CSE":
            cse[b] = c
        elif ex in ("TSX", "TSXV", "TSX-V"):
            tsx[b] = c
    return cse, tsx


def cse_company_ids() -> dict:
    """bare ticker -> CSE listing id, from the CSE filings collector's store."""
    out = {}
    try:
        con = sqlite3.connect(f"file:{CSE_SYMBOLS_DB}?mode=ro", uri=True)
        for r in con.execute("SELECT ticker, company_id FROM symbols"):
            if r[1]:
                out[bare(r[0])] = r[1]
        con.close()
    except sqlite3.Error as e:
        log(f"WARNING: could not read CSE company ids ({e}) — CSE half will be empty")
    return out


# --------------------------------------------------------------------------
# pull
# --------------------------------------------------------------------------

def pull_cse(cse_universe: dict, ids: dict, cutoff: str, only: set | None) -> list[dict]:
    rows, n_err = [], 0
    targets = [(b, ids[b]) for b in sorted(cse_universe) if b in ids]
    if only:
        targets = [t for t in targets if t[0] in only]
    log(f"CSE: {len(targets)} companies to ask "
        f"({len(cse_universe) - len(targets)} of ours have no CSE listing id)")
    for b, cid in targets:
        try:
            d = json.loads(http_get(CSE_API.format(cid)))
        except Exception as e:                       # noqa: BLE001
            n_err += 1
            if n_err <= 3:
                log(f"  CSE {b}: {type(e).__name__} {str(e)[:70]}")
            continue
        for x in d.get("list") or []:
            date = (x.get("date") or "")[:10]
            if not date or date < cutoff:
                continue
            # The exchange states the ticker. Trust it, and only take releases
            # it actually attributes to this company.
            syms = {bare(s) for s in (x.get("symbols") or [])}
            if x.get("mainSymbol"):
                syms.add(bare(x["mainSymbol"]))
            if b not in syms:
                continue
            rows.append({
                "source": "cse", "bare": b,
                "ticker": cse_universe[b].get("symbol") or b,
                "exchange": "CSE", "published_date": date,
                "title": (x.get("title") or "").strip(),
                "url": x.get("fileUrl") or "",
            })
    if n_err:
        log(f"CSE: {n_err} companies could not be read")
    return rows


def pull_tmx(tsx_universe: dict, cutoff: str, only: set | None) -> list[dict]:
    """The company's own news releases, out of the filings store that already
    refreshes every 4 hours. No new scraping, and no commentary."""
    rows = []
    try:
        con = sqlite3.connect(f"file:{TMX_FILINGS_DB}?mode=ro", uri=True)
    except sqlite3.Error as e:
        log(f"WARNING: could not read the TMX filings store ({e}) — TSX/TSXV half will be empty")
        return rows
    q = ("SELECT ticker, filing_date, name, url FROM filings "
         "WHERE lower(category) LIKE ? AND filing_date >= ? ORDER BY filing_date DESC")
    for t, d, name, url in con.execute(q, ("%news release%", cutoff)):
        b = bare(t)
        if b not in tsx_universe:
            continue
        if only and b not in only:
            continue
        rows.append({
            "source": "tmx", "bare": b,
            "ticker": tsx_universe[b].get("symbol") or b,
            "exchange": tsx_universe[b].get("exchange") or "TSX",
            "published_date": d[:10],
            # TMX names the document type, not the headline. The headline comes
            # from the PDF when we ingest it; until then this is the best label.
            "title": (name or "News release").strip(),
            "url": url or "",
        })
    con.close()
    return rows


# --------------------------------------------------------------------------
# reconcile
# --------------------------------------------------------------------------

def find_match(pcon: sqlite3.Connection, rel: dict) -> tuple[str | None, str | None]:
    """(event_id, ticker_it_was_filed_under). Looks for this release among the
    events MNT already has — first under the right ticker, then under any."""
    d = rel["published_date"]
    n1 = norm(rel["title"])
    if not n1:
        return None, None

    def scan(rows):
        for eid, hl, tk in rows:
            n2 = norm(hl)
            if not n2:
                continue
            if n1[:40] == n2[:40] or (len(n1) >= 30 and n1[:30] in n2) or \
               (len(n2) >= 30 and n2[:30] in n1):
                return eid, tk
        return None, None

    own = pcon.execute(
        "SELECT event_id, raw_headline, ticker FROM events "
        "WHERE ticker LIKE ? AND date(published_at) BETWEEN date(?,'-3 day') AND date(?,'+3 day')",
        (rel["bare"] + "%", d, d),
    ).fetchall()
    eid, tk = scan(own)
    if eid:
        return eid, None

    # TMX gives us "News release" as the title, which matches nothing — so a
    # cross-ticker search on it would be meaningless. Only do it for real titles.
    if rel["source"] == "tmx" and norm(rel["title"]) in ("newsrelease", "newsreleases"):
        return None, None

    other = pcon.execute(
        "SELECT event_id, raw_headline, ticker FROM events "
        "WHERE date(published_at) BETWEEN date(?,'-2 day') AND date(?,'+2 day')",
        (d, d),
    ).fetchall()
    eid, tk = scan(other)
    if eid:
        return eid, tk           # found, but filed under the wrong company
    return None, None


# --------------------------------------------------------------------------
# ingest what nothing else caught
# --------------------------------------------------------------------------

def pdf_text(data: bytes, max_pages: int = 8) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader       # type: ignore
        except ImportError:
            return ""
    try:
        rd = PdfReader(io.BytesIO(data))
        out = []
        for page in rd.pages[:max_pages]:
            out.append(page.extract_text() or "")
        return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    except Exception:                            # noqa: BLE001
        return ""


def ingest(rel: dict) -> tuple[bool, str]:
    """Fetch, extract, classify and post one release. Returns (ok, note)."""
    if not rel["url"]:
        return False, "no url"
    try:
        data = http_get(rel["url"])
    except Exception as e:                       # noqa: BLE001
        return False, f"fetch: {type(e).__name__} {str(e)[:60]}"
    if not data[:5].startswith(b"%PDF"):
        return False, f"not a pdf ({data[:8]!r})"
    body = pdf_text(data)
    if len(body) < 200:
        return False, f"pdf text too short ({len(body)} chars)"

    from pipeline.run import build_envelope, sign_and_post, archive_envelope
    from classify.classifier import classify as classify_event

    headline = rel["title"]
    if norm(headline) in ("newsrelease", "newsreleases"):
        # TMX labels the document, not the release. The PDF's first real line is
        # the headline; anything else would put "News release" on the site.
        for line in (l.strip() for l in body.split("\n")):
            if len(line) > 25 and not line.lower().startswith(("form ", "page ")):
                headline = line[:300]
                break

    try:
        cls = classify_event(headline, body)
    except Exception as e:                       # noqa: BLE001
        return False, f"classify: {type(e).__name__} {str(e)[:60]}"

    cand = {
        "source_url": rel["url"],
        "source_name": "cse" if rel["source"] == "cse" else "tmx",
        "published_at": rel["published_date"] + "T12:00:00Z",
        "raw_headline": headline,
        "raw_excerpt": body[:1500],
        "raw_body": body,
        "raw_html": "",
        "ticker": rel["ticker"],
    }
    cfg = {"ticker": rel["ticker"], "company_id": rel["bare"], "property_id": None}
    env = build_envelope(cand, cls, cfg, uid_for(rel["source"], rel["ticker"],
                                                 rel["published_date"], headline))
    archive_envelope(env)
    code, text = sign_and_post(env)
    if 200 <= code < 300:
        return True, f"{env['event_type']} conf={cls.get('classifier_confidence'):.2f} {env['review_status']}"
    return False, f"post {code}: {text[:80]}"


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--max-ingest", type=int, default=DEFAULT_MAX_INGEST)
    ap.add_argument("--no-ingest", action="store_true",
                    help="reconcile and record the gaps, publish nothing")
    ap.add_argument("--only", help="comma-separated bare tickers")
    args = ap.parse_args()

    con = db()

    if args.stats:
        tot = con.execute("SELECT COUNT(*) FROM releases").fetchone()[0]
        print(f"releases on file: {tot}")
        for r in con.execute("SELECT status, COUNT(*) FROM releases GROUP BY 1 ORDER BY 2 DESC"):
            print(f"  {r[0]:<12} {r[1]}")
        for r in con.execute("SELECT source, COUNT(*) FROM releases GROUP BY 1"):
            print(f"  source {r[0]:<6} {r[1]}")
        w = con.execute("SELECT COUNT(*) FROM releases WHERE wrong_ticker IS NOT NULL").fetchone()[0]
        print(f"  filed under the wrong ticker by a wire: {w}")
        for r in con.execute("SELECT started_at, mode, seen, matched, ingested, failed "
                             "FROM runs ORDER BY id DESC LIMIT 5"):
            print("  run", dict(r))
        return 0

    if args.apply == args.dry_run:
        print("pass exactly one of --apply or --dry-run", file=sys.stderr)
        return 2

    started = dt.datetime.utcnow().isoformat()
    t0 = time.monotonic()
    only = {bare(x) for x in args.only.split(",")} if args.only else None
    cutoff = (dt.date.today() - dt.timedelta(days=args.days)).isoformat()

    rows = universe_client.load()
    if not rows:
        log("ABORT: the universe is empty and no cache was available")
        return 1
    cse_u, tsx_u = universe_by_exchange()
    log(f"EXCHANGE_NEWS_V1 ({'APPLY' if args.apply else 'DRY RUN'}) "
        f"window={args.days}d since {cutoff}")
    log(f"universe: {len(cse_u)} CSE, {len(tsx_u)} TSX/TSXV")

    releases = pull_tmx(tsx_u, cutoff, only) + pull_cse(cse_u, cse_company_ids(), cutoff, only)
    log(f"exchanges list {len(releases)} releases in the window")

    pcon = sqlite3.connect(f"file:{PORTAL_DB}?mode=ro", uri=True)
    n_new = n_matched = n_wrong = n_gap = 0
    gaps = []
    for rel in releases:
        uid = uid_for(rel["source"], rel["ticker"], rel["published_date"], rel["title"])
        prev = con.execute("SELECT status FROM releases WHERE uid=?", (uid,)).fetchone()
        if prev and prev["status"] in ("matched", "ingested", "skipped"):
            continue
        if not prev:
            n_new += 1

        eid, wrong = find_match(pcon, rel)
        if eid:
            n_matched += 1
            if wrong:
                n_wrong += 1
            if args.apply:
                con.execute(
                    "INSERT INTO releases (uid,ticker,bare,exchange,source,published_date,"
                    "title,url,status,matched_event,wrong_ticker,acted_at) "
                    "VALUES (?,?,?,?,?,?,?,?,'matched',?,?,?) "
                    "ON CONFLICT(uid) DO UPDATE SET status='matched', matched_event=excluded.matched_event,"
                    " wrong_ticker=excluded.wrong_ticker, acted_at=excluded.acted_at",
                    (uid, rel["ticker"], rel["bare"], rel["exchange"], rel["source"],
                     rel["published_date"], rel["title"], rel["url"], eid, wrong,
                     dt.datetime.utcnow().isoformat()))
        else:
            n_gap += 1
            gaps.append(rel)
            if args.apply:
                con.execute(
                    "INSERT OR IGNORE INTO releases (uid,ticker,bare,exchange,source,"
                    "published_date,title,url,status) VALUES (?,?,?,?,?,?,?,?,'pending')",
                    (uid, rel["ticker"], rel["bare"], rel["exchange"], rel["source"],
                     rel["published_date"], rel["title"], rel["url"]))
    if args.apply:
        con.commit()

    log(f"already on the site: {n_matched}  (of which filed under the WRONG ticker: {n_wrong})")
    log(f"the wires missed: {n_gap}")
    for g in gaps[:15]:
        log(f"   GAP {g['bare']:<7} {g['published_date']} [{g['source']}] {g['title'][:70]}")

    n_ing = n_fail = 0
    if args.apply and not args.no_ingest and gaps:
        for rel in gaps[:args.max_ingest]:
            uid = uid_for(rel["source"], rel["ticker"], rel["published_date"], rel["title"])
            ok, note = ingest(rel)
            if ok:
                n_ing += 1
                con.execute("UPDATE releases SET status='ingested', note=?, acted_at=? WHERE uid=?",
                            (note, dt.datetime.utcnow().isoformat(), uid))
            else:
                n_fail += 1
                con.execute("UPDATE releases SET status='error', note=?, acted_at=? WHERE uid=?",
                            (note, dt.datetime.utcnow().isoformat(), uid))
            log(f"   {'INGESTED' if ok else 'FAILED  '} {rel['bare']:<7} {rel['published_date']} {note[:70]}")
        con.commit()
        if len(gaps) > args.max_ingest:
            log(f"   {len(gaps) - args.max_ingest} more gaps left for the next run (--max-ingest)")

    if args.apply:
        con.execute("INSERT INTO runs (started_at,finished_at,mode,seen,matched,ingested,"
                    "failed,wrong_ticker,note) VALUES (?,?,?,?,?,?,?,?,?)",
                    (started, dt.datetime.utcnow().isoformat(), "apply", len(releases),
                     n_matched, n_ing, n_fail, n_wrong, f"window={args.days}d"))
        con.commit()

    log(f"done in {time.monotonic() - t0:.0f}s — seen={len(releases)} new={n_new} "
        f"matched={n_matched} wrong_ticker={n_wrong} gaps={n_gap} "
        f"ingested={n_ing} failed={n_fail}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
