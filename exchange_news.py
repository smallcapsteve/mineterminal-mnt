#!/usr/bin/env python3
"""EXCHANGE_NEWS_V5 — the exchange as the register of what each company published.

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
  3. Where a wire got there first, record the match — and correct it if the wire
     filed it under a different ticker.
  4. Only where nothing matched: fetch the PDF, extract the text, classify, and
     ingest it.

So it re-collects nothing the wires already deliver, and the count it reports —
"the wires missed N of M releases" — is a coverage measure that has never
existed.

**Sources.**
  CSE      website-data-api-v2.thecse.com/api/news-releases?companyId=<id>
           company ids come from the CSE filings collector's own `symbols`
           table, already maintained for ~348 companies. V5 adds the
           whole-market feed for the fast lane.
  TSX/TSXV `data/tmx_filings.db`, category "News releases" — the company's own
           disclosure as filed.
           **Deliberately NOT money.tmx.com's News tab**, which returns
           SeekingAlpha and Motley Fool commentary via QuoteMedia ("Best 3
           Copper Stocks To Buy For The AI Boom" was the top item for Lundin).
           That is not issuer news and must not be ingested as if it were.

--- V2, 2026-09-13 (same day, before anything was published) -------------------
V1's first dry run reported 587 gaps out of 641 releases — a 92% miss rate that
was not believable, and it was not true. The cause is that TMX's filings store
has no headline in it. `name` is the *document category*: 22,571 of the 22,839
news-release rows say literally "News release". V1 matched on title, so every
TMX release compared "News release" against MNT's real headlines, matched
nothing, and was counted as missed. An --apply run would have ingested 25
duplicates per run forever.

The headline for a TMX release exists in exactly one place: inside the PDF. So
the reconcile is now two stages, cheap first:

  1. **Count, per (ticker, day).** If MNT already holds as many events for that
     company that day as the exchange lists, the release is covered. No fetch.
     This alone accounts for 164 of 473 TMX releases in a 14-day window.
  2. **Headline, from the document.** Only for what stage 1 leaves over: fetch
     the PDF, take the real headline out of it, and *then* run the title match —
     own ticker first, then cross-ticker, which is what detects a wire filing a
     release under the wrong company. Ingest only if that also finds nothing.

Stage 2 costs a fetch, but only for releases that already look uncovered, and
the PDF has to be fetched to ingest anyway. A dry run does stage 2 on a bounded
sample (--max-ingest) so the number it prints is measured, not assumed.

CSE is unchanged: its feed carries real titles, so stage 1 does not apply to it.

--- V3, 2026-09-13 (same day, still before anything was published) -------------
The V2 dry run worked, and the sample it printed showed the next problem: the
headlines it had pulled out of the PDFs. Seven of twenty-five were a street
address or a U.S. distribution disclaimer, because "the first line over 25
characters" is not where a release keeps its headline. Those would have gone
onto three public sites as headlines. `headline_from` is rewritten below and
checked against 45 real releases: 44 correct.

--- V4, 2026-09-13 (same day) --------------------------------------------------
Deployment only. The first --apply run failed at the first publish with
`PermissionError: /opt/mnt/app/.env`: the unit ran as root with an empty
CapabilityBoundingSet, and root without CAP_DAC_OVERRIDE cannot read a 0600 file
it does not own. Widening the capability set was the wrong fix — running this as
root at all would scatter root-owned files through /opt/mnt/app/data, which is
how data/seen_events.json ended up root-owned and unwritable by the mnt-run jobs
that need it. So the job runs as `mnt` like every other MNT job, and the two
filing-store paths became environment variables so the unit can bind-mount the
stores into its own namespace instead.

--- V5, 2026-09-14 -------------------------------------------------------------
Justin: *"Can you make it so Path C is the first check, AKA it being Path A?"*

Measured first, because taken literally it is the wrong thing to build. For 162
releases both paths have, **the wire arrived first in 155**. The TMX filings
store runs a median **52 hours** behind the wires (p90 ten days), and its
collector is not refreshing on the four-hourly cadence its own documentation
claims — 25 new rows across two days against 966 releases in 30 days. Putting
TMX in front would delay TSX/TSXV news by about two days.

So "first" splits in two, and V5 does both halves of what is actually possible:

  * **First in authority, everywhere.** The exchange states the issuer; the
    wires guess. Where they disagree, the exchange now wins —
    `correct_attribution` re-files the event under the ticker the exchange
    states. It reuses `jv_tag.names_primary` to tell the two cases apart: if the
    company it is currently filed under is *also* named in the headline that is
    a co-issue, so keep the primary and cross-file; if it is not named at all
    the wire simply guessed wrong, so re-file and drop the wrong ticker rather
    than demoting it. Every correction is recorded in `corrections` and
    `--undo-corrections` puts them all back exactly.
  * **First in time, for CSE.** The CSE feed is live, and it turns out to have a
    whole-market endpoint. It returns all 97,737 releases as 43 MB and ignores
    limit/page — but it is ordered newest first and the server streams it, so
    reading only the head costs one request. Measured: 300 KB gives 271
    releases spanning 12 days in 3 seconds, against 337 requests and 190 seconds
    for the per-company sweep. `--fast` uses it, and that lane can run ahead of
    the wires for the ~346 CSE companies.

TMX stays on the slow reconcile lane, because no amount of scheduling fixes a
source that is two days late.

Run:
    python3 exchange_news.py --dry-run           # look, change nothing
    python3 exchange_news.py --apply --fast --days 3   # the CSE lead lane
    python3 exchange_news.py --apply             # reconcile + fill gaps
    python3 exchange_news.py --apply --no-ingest # reconcile only
    python3 exchange_news.py --undo-corrections  # exact rollback of re-filings
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
# The CSE and TMX filing stores belong to the MTP collector and live under
# /root, which is mode 700 - the `mnt` user this job runs as cannot traverse
# into it. Rather than run the collector as root (which would leave root-owned
# files all through /opt/mnt/app/data, a failure this box has already had once
# with seen_events.json), the systemd unit bind-mounts that directory into the
# unit's own namespace read-only and points these at it. Defaults are the real
# paths, so the script still works when run by hand as root.
CSE_SYMBOLS_DB = os.environ.get(
    "CSE_FILINGS_DB", "/root/minetracker/data/cse_filings.db")
TMX_FILINGS_DB = os.environ.get(
    "TMX_FILINGS_DB", "/root/minetracker/data/tmx_filings.db")
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
       -- pending | covered | matched | ingested | no_body | error | skipped
    matched_event  TEXT,
    wrong_ticker   TEXT,               -- the ticker a wire filed it under, if different
    note           TEXT,
    first_seen     TEXT DEFAULT CURRENT_TIMESTAMP,
    acted_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_rel_status ON releases(status, published_date DESC);
CREATE INDEX IF NOT EXISTS idx_rel_ticker ON releases(bare, published_date DESC);
CREATE TABLE IF NOT EXISTS corrections (
    event_id     TEXT PRIMARY KEY,
    from_ticker  TEXT NOT NULL,
    to_ticker    TEXT NOT NULL,
    kind         TEXT NOT NULL,     -- 'refiled' | 'co_issue'
    dropped      TEXT,              -- the ticker removed, when it was refiled
    headline     TEXT,
    source       TEXT,
    at           TEXT DEFAULT CURRENT_TIMESTAMP
);
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


def _unescape_title(s: str | None) -> str:
    """Feed titles are HTML-escaped. "Fe &amp; 112.6 Metres" is a headline the
    site would otherwise publish with the entity still in it."""
    import html as _html
    return _html.unescape((s or "")).strip()


def pull_cse(cse_universe: dict, ids: dict, cutoff: str, only: set | None) -> list[dict]:
    rows, n_err = [], 0
    targets = [(b, ids[b]) for b in sorted(cse_universe) if b in ids]
    if only:
        targets = [t for t in targets if t[0] in only]
    log(f"CSE: {len(targets)} companies to ask "
        f"({len(cse_universe) - len(targets)} of ours have no CSE listing id)")
    for i, (b, cid) in enumerate(targets, 1):
        if i % 75 == 0:
            log(f"  CSE: {i}/{len(targets)} asked, {len(rows)} releases so far")
        time.sleep(0.05)          # ~0.5s per call already; this is courtesy
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
                "title": _unescape_title(x.get("title")),
                "url": x.get("fileUrl") or "",
            })
    if n_err:
        log(f"CSE: {n_err} companies could not be read")
    return rows


CSE_ALL = "https://website-data-api-v2.thecse.com/api/news-releases?locale=en"
# The whole-market feed is one response of every CSE release ever — 43 MB and
# 97,737 items — and it ignores limit/page. But it is ordered newest first and
# the server streams it, so reading only the head gets the newest releases for
# one request. Measured: 300 KB = 271 releases spanning 12 days, in 3 seconds,
# against 337 requests and 190 seconds for the per-company sweep.
CSE_HEAD_BYTES = int(os.environ.get("CSE_HEAD_BYTES", 300_000))


def pull_cse_fast(cse_universe: dict, cutoff: str, only: set | None) -> list[dict]:
    """Every CSE issuer's newest releases, in one request.

    This is the half of the system that can genuinely be *first* — the CSE feed
    is live, where the TMX filings store runs a median 52 hours behind the
    wires. Used by the fast lane; the per-company sweep remains the backstop for
    the reconcile lane, because the head only reaches back about twelve days.
    """
    req = urllib.request.Request(CSE_ALL, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as r:
            raw = r.read(CSE_HEAD_BYTES).decode("utf-8", "ignore")
    except Exception as e:                       # noqa: BLE001
        log(f"WARNING: CSE fast feed unreachable ({type(e).__name__} {str(e)[:60]})")
        return []

    i = raw.find("[")
    if i < 0:
        log("WARNING: CSE fast feed did not look like a list")
        return []
    dec, pos, rows, seen = json.JSONDecoder(), i + 1, [], 0
    while True:
        while pos < len(raw) and raw[pos] in " \n\r\t,":
            pos += 1
        try:
            obj, pos = dec.raw_decode(raw, pos)
        except Exception:                        # noqa: BLE001
            break                                # the truncated tail object
        seen += 1
        date = (obj.get("date") or "")[:10]
        if not date or date < cutoff:
            continue
        syms = {bare(x) for x in (obj.get("symbols") or [])}
        if obj.get("mainSymbol"):
            syms.add(bare(obj["mainSymbol"]))
        hit = syms & set(cse_universe)
        if not hit:
            continue
        b = bare(obj.get("mainSymbol") or "") or sorted(hit)[0]
        if b not in cse_universe:
            b = sorted(hit)[0]
        if only and b not in only:
            continue
        rows.append({
            "source": "cse", "bare": b,
            "ticker": cse_universe[b].get("symbol") or b,
            "exchange": "CSE", "published_date": date,
            "title": _unescape_title(obj.get("title")),
            "url": obj.get("fileUrl") or "",
        })
    log(f"CSE fast feed: read {seen} releases, {len(rows)} are ours since {cutoff}")
    return rows


# --------------------------------------------------------------------------
# the exchange is the authority on who a release belongs to
# --------------------------------------------------------------------------

_JV = None


def _jv_index():
    """(jv_tag module, by_sym, short_forms) — the same company-name matcher the
    cross-filing feature uses, reused here to tell a co-issue from an error."""
    global _JV
    if _JV is None:
        import jv_tag
        _, by_sym, short = jv_tag.build_index()
        _JV = (jv_tag, by_sym, short)
    return _JV


def correct_attribution(con, pdb_rw, eid: str, want: str, headline: str,
                        source: str, apply_it: bool) -> str | None:
    """The exchange says this release is `want`'s. MNT filed it elsewhere.

    Two cases, and telling them apart is the whole job:

      * **Co-issue.** The company it is filed under is also named in the
        headline — a joint venture, a merger, an option agreement. Both
        attributions are true. Keep the existing primary and add ours.
      * **Misattribution.** The headline never mentions the company it is filed
        under. The wire guessed and guessed wrong. Re-file it under the ticker
        the exchange states, and drop the wrong one rather than demoting it —
        leaving it on would keep somebody else's news on that company's page.

    Returns 'co_issue', 'refiled', or None when nothing needed doing.
    """
    row = pdb_rw.execute(
        "SELECT ticker, COALESCE(additional_tickers,'') FROM events WHERE event_id=?",
        (eid,)).fetchone()
    if not row:
        return None
    cur, addl = (row[0] or "").upper(), row[1]
    want = (want or "").upper()
    if not want or cur == want:
        return None

    jv, by_sym, short = _jv_index()
    have = [t for t in addl.strip("|").split("|") if t]
    co = jv.names_primary(headline, cur, by_sym, short)

    if co:
        if want in have:
            return None
        have.append(want)
        new_primary, dropped, kind = cur, None, "co_issue"
    else:
        new_primary, dropped, kind = want, cur, "refiled"
        have = [t for t in have if t not in (want, cur)]

    if apply_it:
        pdb_rw.execute(
            "UPDATE events SET ticker=?, company_id=?, additional_tickers=? "
            "WHERE event_id=?",
            (new_primary, new_primary.split(".")[0], jv.pipe(have), eid))
        con.execute(
            "INSERT INTO corrections (event_id,from_ticker,to_ticker,kind,dropped,"
            "headline,source) VALUES (?,?,?,?,?,?,?) ON CONFLICT(event_id) DO NOTHING",
            (eid, cur, new_primary, kind, dropped, headline[:220], source))
    return kind


def undo_corrections(con, limit: int | None = None) -> int:
    """Put every corrected event back exactly where it was. The `corrections`
    table records the ticker each one came from, so this is exact rather than
    reconstructed — the lesson from applying the JV backfill without a working
    backup."""
    rows = con.execute(
        "SELECT event_id, from_ticker, to_ticker, kind, dropped FROM corrections"
        + (f" LIMIT {int(limit)}" if limit else "")).fetchall()
    if not rows:
        print("no corrections to undo")
        return 0
    p = sqlite3.connect(PORTAL_DB)
    jv, _, _ = _jv_index()
    n = 0
    for r in rows:
        cur = p.execute("SELECT COALESCE(additional_tickers,'') FROM events "
                        "WHERE event_id=?", (r["event_id"],)).fetchone()
        if not cur:
            continue
        have = [t for t in cur[0].strip("|").split("|") if t]
        if r["kind"] == "co_issue":
            have = [t for t in have if t != r["to_ticker"]]
            primary = r["from_ticker"]
        else:
            have = [t for t in have if t != r["from_ticker"]]
            primary = r["from_ticker"]
        p.execute("UPDATE events SET ticker=?, company_id=?, additional_tickers=? "
                  "WHERE event_id=?",
                  (primary, primary.split(".")[0], jv.pipe(have), r["event_id"]))
        con.execute("DELETE FROM corrections WHERE event_id=?", (r["event_id"],))
        n += 1
    p.commit()
    con.commit()
    log(f"undid {n} corrections")
    return n


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

def _win(d: str, back: int, fwd: int):
    """Half-open [lo, hi) date window as plain ISO strings, or None.

    published_at is 'YYYY-MM-DDT12:00:00Z', so string comparison is equivalent
    to date() comparison and, unlike date(), can use idx_events_published_at.
    Returns None if the date will not parse; the caller then falls back to the
    original date() form, so behaviour is never worse than before.
    """
    import datetime as _dt
    try:
        base = _dt.date.fromisoformat((d or "")[:10])
    except Exception:                                # noqa: BLE001
        return None
    return ((base - _dt.timedelta(days=back)).isoformat(),
            (base + _dt.timedelta(days=fwd + 1)).isoformat())



def find_match(pcon: sqlite3.Connection, rel: dict,
               title: str | None = None) -> tuple[str | None, str | None]:
    """(event_id, ticker_it_was_filed_under). Looks for this release among the
    events MNT already has — first under the right ticker, then under any.

    `title` overrides rel["title"]. That is how a TMX release is matched: the
    caller pulls the real headline out of the PDF and passes it here, because
    rel["title"] is the string "News release" for every TMX row in the store."""
    d = rel["published_date"]
    n1 = norm(title if title is not None else rel["title"])
    if not n1 or n1 in ("newsrelease", "newsreleases"):
        # Nothing to match on. Say so rather than reporting "not found", which
        # is what V1 did and why it called 587 covered releases missing.
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

    _w = _win(d, 3, 3)
    if _w:
        own = pcon.execute(
            "SELECT event_id, raw_headline, ticker FROM events "
            "WHERE ticker LIKE ? AND published_at >= ? AND published_at < ?",
            (rel["bare"] + "%", _w[0], _w[1]),
        ).fetchall()
    else:
        own = pcon.execute(
            "SELECT event_id, raw_headline, ticker FROM events "
            "WHERE ticker LIKE ? AND date(published_at) BETWEEN date(?,'-3 day') AND date(?,'+3 day')",
            (rel["bare"] + "%", d, d),
        ).fetchall()
    eid, tk = scan(own)
    if eid:
        return eid, None

    _w = _win(d, 2, 2)
    if _w:
        other = pcon.execute(
            "SELECT event_id, raw_headline, ticker FROM events "
            "WHERE published_at >= ? AND published_at < ?",
            (_w[0], _w[1]),
        ).fetchall()
    else:
        other = pcon.execute(
            "SELECT event_id, raw_headline, ticker FROM events "
            "WHERE date(published_at) BETWEEN date(?,'-2 day') AND date(?,'+2 day')",
            (d, d),
        ).fetchall()
    eid, tk = scan(other)
    if eid:
        return eid, tk           # found, but filed under the wrong company
    return None, None


def covered_by_count(pcon: sqlite3.Connection, rels: list[dict]) -> set:
    """Stage 1 — the cheap half of the reconcile, for TMX only.

    TMX tells us *that* a company filed a release on a day, never what it said.
    So instead of asking "is this headline on the site", ask the only question
    the data supports: **does MNT already hold as many events for this company
    that day as the exchange lists?** If it does, there is nothing missing.

    Deliberately conservative in the direction that costs a fetch rather than a
    duplicate: two releases on one day with only one event on the site leaves
    the day a candidate, and stage 2 sorts out which one is the new one.

    +/- 1 day, because an evening release is routinely dated the next morning by
    a wire and vice versa.

    Returns the uids that need no further work.
    """
    by_day = {}
    for r in rels:
        by_day.setdefault((r["bare"], r["published_date"]), []).append(r)
    out = set()
    for (b, d), group in by_day.items():
        _w = _win(d, 1, 1)
        if _w:
            have = pcon.execute(
                "SELECT COUNT(*) FROM events WHERE ticker LIKE ? "
                "AND published_at >= ? AND published_at < ?",
                (b + "%", _w[0], _w[1]),
            ).fetchone()[0]
        else:
            have = pcon.execute(
                "SELECT COUNT(*) FROM events WHERE ticker LIKE ? "
                "AND date(published_at) BETWEEN date(?,'-1 day') AND date(?,'+1 day')",
                (b + "%", d, d),
            ).fetchone()[0]
        if have >= len(group):
            for r in group:
                out.add(uid_for(r["source"], r["ticker"], r["published_date"],
                                r["title"]))
    return out


# --------------------------------------------------------------------------
# ingest what nothing else caught
# --------------------------------------------------------------------------

class NoPdfExtractor(RuntimeError):
    """No pypdf / PyPDF2 on this interpreter.

    V5c. Until now this returned an empty string, which is exactly what a
    scanned, image-only PDF returns. The two are indistinguishable downstream:
    every candidate reports "pdf text too short (0 chars)", stage 2 concludes
    0% of candidates are genuine gaps, and the run publishes nothing and exits
    0. A run under the wrong interpreter therefore looked like a clean run with
    nothing to do — silently, on every timer tick, forever. Found 2026-09-14
    when a dry run under /usr/bin/python3 (the service uses
    /opt/mnt/app/.venv/bin/python) read 0 chars from 8 of 8 releases."""


def _pdf_reader():
    try:
        from pypdf import PdfReader
        return PdfReader
    except ImportError:
        pass
    try:
        from PyPDF2 import PdfReader           # type: ignore
        return PdfReader
    except ImportError:
        raise NoPdfExtractor(
            "no PDF text extractor (pypdf / PyPDF2) on "
            f"{sys.executable}. The service runs "
            "/opt/mnt/app/.venv/bin/python — use that, or pip install pypdf.")


def pdf_text(data: bytes, max_pages: int = 8) -> str:
    PdfReader = _pdf_reader()
    try:
        rd = PdfReader(io.BytesIO(data))
        out = []
        for page in rd.pages[:max_pages]:
            out.append(page.extract_text() or "")
        return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    except Exception:                            # noqa: BLE001
        return ""


_MONTH = (r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
          r"Jul(?:y)?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|"
          r"Dec(?:ember)?")
# A dateline carries a full calendar date. A headline almost never does.
_DATELINE = re.compile(
    rf"(\b({_MONTH})\.?\s+\d{{1,2}}\s*,?\s*20\d{{2}}\b"     # September 9, 2026
    rf"|\b\d{{1,2}}\s+({_MONTH})\.?\s*,?\s*20\d{{2}}\b)", re.I)   # 10 SEPTEMBER, 2026

_LETTERHEAD = re.compile(
    r"([A-Z]\d[A-Z]\s?\d[A-Z]\d"                      # Canadian postal code
    r"|\bsuite\b|\bstreet\b|\bavenue\b|\bboulevard\b|\broad\b|\bfloor\b"
    r"|^\s*t:\s|^\s*e:\s|\btel\b|\bphone\b|\bemail\b|@|www\.|https?://"
    r"|\bPO Box\b)", re.I)

_LABEL = re.compile(
    r"^\s*[\W_]*(press\s+release|news\s+release|for\s+immediate\s+release"
    r"|news|media\s+release"
    r"|not\s+for\s+(distribution|dissemination|release)"
    r"|for\s+dissemination|this\s+news\s+release\s+is\s+not)", re.I)

_LISTING = re.compile(
    r"^\s*(TSX[-.\s]?V?|CSE|NEO|OTC\w*|FSE|Frankfurt|NYSE|NASDAQ|ASX|AIM)\s*[:\-]",
    re.I)
_TICKER_COLON = re.compile(r"\b[A-Z][A-Z.]{1,9}\s*:\s*[A-Z0-9.]{1,8}\b")
# The same thing without the colon: "TSXV TRBC OTCQB TRRCF" across the top of a
# filed corporate deck.
_LISTING_BARE = re.compile(
    r"^\s*(TSXV?|TSX[-.]V|CSE|NEO|OTCQ[BX]|OTC|NYSE|NASDAQ|ASX|AIM)\s+[A-Z]{2,6}\b", re.I)
# A line that is only the company's name is the top of the letterhead, not the
# headline: "Wesdome Gold Mines Ltd", "Surge Copper Corp."
_NAME_ONLY = re.compile(
    r"^[\w'&.,\- ]{3,45}\b(inc|ltd|corp|corporation|limited|plc|llc|company|"
    r"resources|metals|mining|minerals)\.?$", re.I)
# Disclaimer text that ran onto the same extracted line as the headline. Cut it
# off rather than discarding the line: "DISSEMINATION IN THE UNITED STATES LAKE
# WINN ANNOUNCES PRIVATE PLACEMENT".
_DISCLAIMER_RUN = re.compile(
    r"^.{0,120}?(?:u\.?s\.?\s+newswire\s+services?|newswire\s+services?"
    r"|(?:in|into|to)\s+the\s+united\s+states)\b[\s,.:;\-]*", re.I)
_FILENAME = re.compile(r"\.(docx?|pdf|html?|txt)\s*$", re.I)
_BULLET = re.compile(r"^\s*[\u25cf\u2022\u25aa\u2023\-\*\u2013]\s")

MAX_CHARS = 200          # a headline plus its subhead; beyond this it is body
MAX_SCAN = 22            # lines of letterhead worth walking past


def _is_noise(s: str) -> bool:
    """True for anything that is not part of the headline: letterhead, the
    'NEWS RELEASE' label, exchange listings, disclaimers, taglines, datelines."""
    if len(s) < 12:
        return True
    if _LABEL.match(s) or _LISTING.match(s) or _FILENAME.search(s):
        return True
    if _LISTING_BARE.match(s) or _NAME_ONLY.match(s):
        return True
    if _LETTERHEAD.search(s):
        return True
    if _DATELINE.search(s):                  # a date header, or the dateline
        return True
    if s.count("|") >= 2:                    # "Trust | Respect | Integrity"
        return True
    if len(_TICKER_COLON.findall(s)) >= 2:
        return True
    letters = sum(c.isalpha() for c in s)
    return letters < len(s) * 0.4            # mostly digits and punctuation


def headline_from(body: str, fallback: str) -> str:
    """The headline of a news-release PDF.

    TMX's filings store has no headline in it — `name` is the document
    category, "News release", on 22,571 of 22,839 rows — so for a TSX/TSXV
    release the headline has to come out of the document itself.

    A release PDF is laid out the same way everywhere: letterhead (address,
    phone, exchange listings, a "NEWS RELEASE" label, sometimes a U.S.
    distribution disclaimer), then the headline, usually wrapped over two or
    three lines and sometimes followed by a subhead, then the dateline —
    "September 9, 2026 - Vancouver, BC:" — and then the body.

    So: walk down past everything that is recognisably letterhead, take the
    first line that is not, and keep taking lines until the dateline or the
    body starts. Checked against 45 real releases: 44 correct.

    Two earlier attempts are worth recording, because both looked fine until
    they met real documents:

      * "first line over 25 characters" put street addresses and
        "THIS NEWS RELEASE IS NOT FOR DISTRIBUTION TO U.S. NEWSWIRE SERVICES"
        on about a third of a 25-release sample.
      * anchoring on the dateline and reading *backwards* failed whenever the
        dateline was abbreviated ("Sept. 11, 2026"), absent, or itself looked
        like letterhead — the search then found a date in the body and read
        back into the middle of a paragraph.

    The junk filter, not the anchor, was always the real work.
    """
    if re.sub(r"[^a-z0-9]+", "", (fallback or "").lower()) not in (
            "newsrelease", "newsreleases", ""):
        return fallback                      # CSE gives a real title already

    lines = [l.strip() for l in body.split("\n")]
    lines = [l for l in lines if l][:MAX_SCAN]

    start = None
    for i, l in enumerate(lines):
        if not _is_noise(l):
            start = i
            break

    out = ""
    if start is not None:
        block, chars = [], 0
        for l in lines[start:]:
            if _BULLET.match(l) or _is_noise(l):
                break                        # dateline, bullets, or body
            block.append(l)
            chars += len(l) + 1
            if chars >= MAX_CHARS:
                break
        out = re.sub(r"\s+", " ", " ".join(block))

    if not out:
        # Nothing survived the filter — some releases put the headline on a
        # line that also carries a phone number or an address. Better a rough
        # headline than the literal words "News release" on the site.
        for l in lines:
            if len(l) > 25 and not _LABEL.match(l) and not _LISTING.match(l):
                out = l
                break

    out = _DISCLAIMER_RUN.sub("", out).strip()
    return out[:300] or fallback



# --------------------------------------------------------------------------
# .docx
#
# The CSE stores a slice of its filings as Word documents -- 137 of 179
# failures on 2026-09-15, 76.5% of them. A .docx is XML in a zip, so this
# needs no dependency beyond the standard library.
#
# Runs inside a paragraph are joined with NOTHING. Word splits a sentence
# across many <w:t> runs and frequently splits mid-number, because a bold or
# differently-kerned digit becomes its own run; joining with a space produced
# "2 7 . 2 %" for "27.2%". Only paragraph ends become newlines, so the output
# has the same shape as pdf_text() -- which headline_from() and the dateline
# date extractor both depend on.
# --------------------------------------------------------------------------

_DOCX_P   = re.compile(r"</w:p\s*>", re.I)
_DOCX_BR  = re.compile(r"<w:(?:br|cr)\b[^>]*/?>", re.I)
_DOCX_TAB = re.compile(r"<w:tab\b[^>]*/?>", re.I)
_DOCX_RUN = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.I | re.S)


def is_docx(data: bytes) -> bool:
    """A zip whose listing contains word/document.xml."""
    if not data[:4] == b"PK\x03\x04":
        return False
    import zipfile
    try:
        return "word/document.xml" in zipfile.ZipFile(io.BytesIO(data)).namelist()
    except Exception:                            # noqa: BLE001
        return False


def docx_text(data: bytes, max_chars: int = 400_000) -> str:
    """Body text of a .docx, one paragraph per line. '' if unreadable."""
    import html as _html
    import zipfile
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        if "word/document.xml" not in z.namelist():
            return ""
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except Exception:                            # noqa: BLE001
        return ""
    xml = _DOCX_TAB.sub(" ", xml)
    xml = _DOCX_BR.sub("</w:p>", xml)            # a manual break ends a line too
    lines = []
    for chunk in _DOCX_P.split(xml):
        text = "".join(_DOCX_RUN.findall(chunk))
        if not text:
            continue
        text = _html.unescape(text)
        text = re.sub(r"[ \t\u00a0]+", " ", text).strip()
        if text:
            lines.append(text)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()[:max_chars]


def docx_self_test(verbose: bool = False) -> int:
    """Build a .docx in memory and prove the run-joining rule.

    The failure this guards against is silent: a reader that joins runs with a
    space still returns plausible-looking text, and every grade and length in
    it is corrupted.
    """
    import zipfile
    body = (
        '<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
        '<w:p><w:r><w:t>High Tide Reports </w:t></w:r>'
        '<w:r><w:t>91.</w:t></w:r><w:r><w:t>4</w:t></w:r>'
        '<w:r><w:t> Metres of </w:t></w:r>'
        '<w:r><w:t>2</w:t></w:r><w:r><w:t>8</w:t></w:r>'
        '<w:r><w:t>.7</w:t></w:r><w:r><w:t>% Fe</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Vancouver, B.C. &amp; Toronto</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Line<w:tab/>after tab</w:t></w:r></w:p>'
        '</w:body></w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", body)
    raw = buf.getvalue()

    got = docx_text(raw)
    fails = []
    if not is_docx(raw):
        fails.append("is_docx did not recognise a real docx")
    if "91.4 Metres of 28.7% Fe" not in got:
        fails.append(f"runs were not joined cleanly: {got[:80]!r}")
    if "Vancouver, B.C. & Toronto" not in got:
        fails.append("xml entities were not unescaped")
    if len(got.splitlines()) != 3:
        fails.append(f"expected 3 paragraphs, got {len(got.splitlines())}")
    if is_docx(b"%PDF-1.4 not a zip"):
        fails.append("is_docx accepted a PDF")
    if docx_text(b"garbage") != "":
        fails.append("docx_text did not return '' for garbage")

    if verbose or fails:
        for f in fails:
            print("  docx FAIL:", f)
    return 1 if fails else 0


def fetch_release(rel: dict) -> tuple[str, str, str]:
    """(body, headline, error). Fetches the PDF and reads it; publishes nothing.

    Split out of ingest() in V2 because the headline is needed *before* the
    match decision for TMX, not after it."""
    if not rel["url"]:
        return "", "", "no url"
    try:
        data = http_get(rel["url"])
    except Exception as e:                       # noqa: BLE001
        return "", "", f"fetch: {type(e).__name__} {str(e)[:60]}"
    if is_docx(data):
        body = docx_text(data)
        if len(body) < 200:
            return "", "", f"docx text too short ({len(body)} chars)"
        return body, headline_from(body, rel["title"]), ""
    if not data[:5].startswith(b"%PDF"):
        return "", "", f"not a pdf ({data[:8]!r})"
    try:
        body = pdf_text(data)
    except NoPdfExtractor as e:
        return "", "", f"NO EXTRACTOR: {e}"
    if len(body) < 200:
        return "", "", f"pdf text too short ({len(body)} chars)"
    return body, headline_from(body, rel["title"]), ""


def publish(rel: dict, body: str, headline: str) -> tuple[bool, str]:
    """Classify an already-fetched release and post it to MNT's ingest."""
    from pipeline.run import build_envelope, sign_and_post, archive_envelope
    from classify.classifier import classify as classify_event

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
    ap.add_argument("--source", choices=("both", "cse", "tmx"), default="both",
                    help="which exchange to read")
    ap.add_argument("--fast", action="store_true",
                    help="CSE only, via the whole-market feed: the lane that "
                         "runs ahead of the wires")
    ap.add_argument("--no-correct", action="store_true",
                    help="do not re-file releases the exchange attributes elsewhere")
    ap.add_argument("--max-correct", type=int, default=25)
    ap.add_argument("--undo-corrections", action="store_true")
    args = ap.parse_args()

    con = db()

    if args.undo_corrections:
        undo_corrections(con)
        return 0

    if args.stats:
        tot = con.execute("SELECT COUNT(*) FROM releases").fetchone()[0]
        print(f"releases on file: {tot}")
        for r in con.execute("SELECT status, COUNT(*) FROM releases GROUP BY 1 ORDER BY 2 DESC"):
            print(f"  {r[0]:<12} {r[1]}")
        for r in con.execute("SELECT source, COUNT(*) FROM releases GROUP BY 1"):
            print(f"  source {r[0]:<6} {r[1]}")
        w = con.execute("SELECT COUNT(*) FROM releases WHERE wrong_ticker IS NOT NULL").fetchone()[0]
        print(f"  filed under the wrong ticker by a wire: {w}")
        for r in con.execute("SELECT kind, COUNT(*) c FROM corrections GROUP BY 1"):
            print(f"  corrected ({r[0]}): {r['c']}")
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

    # The extractor is checked up front, not on the first PDF. Stage 2 is the
    # only thing that decides a candidate is a real gap; without an extractor
    # it decides "no gaps" about everything, which is a wrong answer wearing a
    # successful run's clothes.
    if not args.no_ingest:
        try:
            _pdf_reader()
        except NoPdfExtractor as e:
            log(f"ABORT: {e}")
            return 4

    log(f"EXCHANGE_NEWS_V5c ({'APPLY' if args.apply else 'DRY RUN'}) "
        f"{'FAST/cse-lead' if args.fast else args.source} "
        f"window={args.days}d since {cutoff}")
    log(f"universe: {len(cse_u)} CSE, {len(tsx_u)} TSX/TSXV")

    if args.fast:
        args.source = "cse"
    releases = []
    if args.source in ("both", "tmx"):
        releases += pull_tmx(tsx_u, cutoff, only)
    if args.source in ("both", "cse"):
        releases += (pull_cse_fast(cse_u, cutoff, only) if args.fast
                     else pull_cse(cse_u, cse_company_ids(), cutoff, only))
    log(f"exchanges list {len(releases)} releases in the window "
        f"({sum(1 for r in releases if r['source'] == 'tmx')} TMX, "
        f"{sum(1 for r in releases if r['source'] == 'cse')} CSE)")

    pcon = sqlite3.connect(f"file:{PORTAL_DB}?mode=ro", uri=True)
    now = dt.datetime.utcnow().isoformat()

    # Anything already settled in a previous run is left alone. An unreadable
    # PDF is held back for three days too: without that, a handful of
    # permanently broken documents would eat the whole --max-ingest budget on
    # every run and nothing new would ever be looked at.
    settled = {r[0] for r in con.execute(
        "SELECT uid FROM releases WHERE status IN "
        "('covered','matched','ingested','skipped') "
        "OR (status='error' AND acted_at > datetime('now','-3 day'))")}
    fresh = [r for r in releases
             if uid_for(r["source"], r["ticker"], r["published_date"], r["title"])
             not in settled]
    log(f"{len(releases) - len(fresh)} were settled by an earlier run; "
        f"{len(fresh)} to look at")

    def record(rel, status, **kw):
        if not args.apply:
            return
        uid = uid_for(rel["source"], rel["ticker"], rel["published_date"], rel["title"])
        con.execute(
            "INSERT INTO releases (uid,ticker,bare,exchange,source,published_date,"
            "title,url,status,matched_event,wrong_ticker,note,acted_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(uid) DO UPDATE SET status=excluded.status, "
            "matched_event=excluded.matched_event, wrong_ticker=excluded.wrong_ticker, "
            "note=excluded.note, acted_at=excluded.acted_at",
            (uid, rel["ticker"], rel["bare"], rel["exchange"], rel["source"],
             rel["published_date"], rel["title"], rel["url"], status,
             kw.get("event"), kw.get("wrong"), kw.get("note"), now))

    # ---- stage 1 ---------------------------------------------------------
    # TMX by count (it has no headline to match on); CSE by its real title.
    tmx_fresh = [r for r in fresh if r["source"] == "tmx"]
    cov = covered_by_count(pcon, tmx_fresh)

    n_covered = n_matched = n_wrong = 0
    n_corr: dict = {}
    pdb_rw = sqlite3.connect(PORTAL_DB) if args.apply else None

    def maybe_correct(con_, eid, rel, headline, args_):
        """The exchange states the issuer. Where MNT disagrees, make it agree."""
        if args_.no_correct:
            return None
        if sum(n_corr.values()) >= args_.max_correct:
            return None
        kind = correct_attribution(con_, pdb_rw or pcon, eid, rel["ticker"],
                                   headline or "", rel["source"], bool(args_.apply))
        if kind:
            log(f"   {'CORRECTED' if args_.apply else 'WOULD CORRECT'} "
                f"{kind:<9} -> {rel['ticker']:<10} {(headline or '')[:56]}")
        return kind

    candidates = []
    for rel in fresh:
        uid = uid_for(rel["source"], rel["ticker"], rel["published_date"], rel["title"])
        if rel["source"] == "tmx":
            if uid in cov:
                n_covered += 1
                record(rel, "covered", note="MNT already had that day's events")
            else:
                candidates.append(rel)
            continue
        eid, wrong = find_match(pcon, rel)       # CSE: real title, match now
        if eid:
            n_matched += 1
            if wrong:
                n_wrong += 1
                k = maybe_correct(con, eid, rel, rel["title"], args)
                if k:
                    n_corr[k] = n_corr.get(k, 0) + 1
            record(rel, "matched", event=eid, wrong=wrong)
        else:
            candidates.append(rel)

    log(f"stage 1 — already covered: {n_covered} TMX (by that day's event count), "
        f"{n_matched} CSE (by headline; {n_wrong} of them under the WRONG ticker)")
    log(f"stage 1 leaves {len(candidates)} candidates "
        f"({sum(1 for r in candidates if r['source'] == 'tmx')} TMX, "
        f"{sum(1 for r in candidates if r['source'] == 'cse')} CSE)")

    # ---- stage 2 ---------------------------------------------------------
    # Open the document, take the real headline, and only then decide. Bounded
    # in both modes: a dry run confirms a sample so its number is measured.
    cap = args.max_ingest
    n_late = n_late_wrong = n_ing = n_fail = n_gap = 0
    for rel in candidates[:cap]:
        body, headline, err = fetch_release(rel)
        if err:
            n_fail += 1
            record(rel, "error", note=err)
            log(f"   UNREADABLE {rel['bare']:<7} {rel['published_date']} {err[:60]}")
            continue
        eid, wrong = find_match(pcon, rel, title=headline)
        if eid:
            n_late += 1
            if wrong:
                n_late_wrong += 1
                k = maybe_correct(con, eid, rel, headline, args)
                if k:
                    n_corr[k] = n_corr.get(k, 0) + 1
            record(rel, "matched", event=eid, wrong=wrong, note="matched on the PDF headline")
            log(f"   ON SITE    {rel['bare']:<7} {rel['published_date']} "
                f"{'[WRONG TICKER: ' + wrong + '] ' if wrong else ''}{headline[:60]}")
            continue
        n_gap += 1
        if args.apply and not args.no_ingest:
            ok, note = publish(rel, body, headline)
            if ok:
                n_ing += 1
                record(rel, "ingested", note=note)
            else:
                n_fail += 1
                record(rel, "error", note=note)
            log(f"   {'INGESTED' if ok else 'FAILED  '} {rel['bare']:<7} "
                f"{rel['published_date']} {headline[:45]} — {note[:45]}")
        else:
            record(rel, "pending", note="confirmed gap, not published")
            log(f"   GAP        {rel['bare']:<7} {rel['published_date']} {headline[:60]}")

    checked = min(len(candidates), cap)
    if checked:
        log(f"stage 2 — opened {checked} of {len(candidates)} candidates: "
            f"{n_late} were already on the site after all "
            f"({n_late_wrong} under the wrong ticker), {n_gap} are real gaps, "
            f"{n_fail} could not be read")
        rate = n_gap / checked
        log(f"          on that sample, {rate:.0%} of candidates are genuine gaps "
            f"-> roughly {round(len(candidates) * rate)} of {len(candidates)} "
            f"over the {args.days}-day window")
    if len(candidates) > cap:
        log(f"          {len(candidates) - cap} candidates left for the next run "
            f"(--max-ingest {cap})")

    if n_corr:
        log(f"attribution: {n_corr.get('refiled', 0)} re-filed under the ticker the "
            f"exchange states, {n_corr.get('co_issue', 0)} cross-filed as co-issues")
    if pdb_rw is not None:
        pdb_rw.commit()
        pdb_rw.close()

    if args.apply:
        con.commit()
        con.execute("INSERT INTO runs (started_at,finished_at,mode,seen,matched,ingested,"
                    "failed,wrong_ticker,note) VALUES (?,?,?,?,?,?,?,?,?)",
                    (started, dt.datetime.utcnow().isoformat(), "apply", len(releases),
                     n_covered + n_matched + n_late, n_ing, n_fail,
                     n_wrong + n_late_wrong, f"window={args.days}d"))
        con.commit()

    log(f"done in {time.monotonic() - t0:.0f}s — seen={len(releases)} "
        f"covered={n_covered} matched={n_matched + n_late} "
        f"wrong_ticker={n_wrong + n_late_wrong} confirmed_gaps={n_gap} "
        f"ingested={n_ing} failed={n_fail}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
