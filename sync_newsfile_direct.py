#!/usr/bin/env python3
"""sync_newsfile_direct.py - direct Newsfile (TMX Newsfile) mining collector. NFDIRECT_V4, 2026-10-27.

V4 (NFSTUB_V1; Justin 11:58 Toronto: "Yes build step 1 & 2"):
  Step 1, short version. While Newsfile's website blocks us, a new release seen in the feeds is published at once as a
  short version: headline, ticker, Newsfile's time, the feed's ~500-character opening and a link to the full release
  on Newsfile. Its own event id (stub_event_id), classifier_model 'newsfile_feed_stub_v1'. The rules readers are told
  to skip it (an 'ok', 0-record fx_runs row per active reader version, error 'NFSTUB_V1 ...'), so data pages only ever
  read full text. On only while data/newsfile_stubs.on exists.
  Step 2, full text takes over. Checked every run, cheapest first:
    a. a copy already on MNT from another source (same ticker, within 2 days, >= FILL_OVERLAP of the opening's 8-word
       phrases found in its text) -> that copy is kept;
    b. a TSX/CSE (or other) copy the duplicate guard held back because the short version was there
       (dup_guard_log 'skipped_new', kept_id = the stub) -> that copy is put back, as the guard's own restore does;
    c. Newsfile's page reads again -> the full release is stored under its normal id (event_id_for(url)).
  In each case the short version is removed: logged in dup_guard_log ('stub_replaced', full row), its reader rows
  deleted, the row deleted, and its address forwarded to the kept release (event_slug_aliases, source NFSTUB_V1) when
  the address differs. For c the stub is removed first (MNT's older headline matcher ignores review_status, so even a
  hidden stub would make it refuse the full release) and put back from its logged row if the full release is not
  stored ('stub_restored').
  A short version is never made when the release is already on MNT, has no Canadian ticker, or looks non-mining.

History
  V1/V2 2026-10-16 (claude/NFDIRECT_FINDINGS_2026-10-16.md): metals RSS feeds, then the release page for the text.
  V3    2026-10-27 (claude/NEWSFILE_BLOCK_FINDINGS_2026-10-27.md). Justin: "Could we do it so that we go through their
        feed server first, and then only check their website for the new news releases that weve recieved from their
        feed server? Is there a way to mitigate the feed showing only its latest 10 releases?" -> "yes please build and
        test on a dry run."

Why V3. Since 2026-10-21 00:00 UTC Newsfile's website (www.newsfilecorp.com, AWS WAF) answers this server only with
"202, empty body, x-amzn-waf-action: challenge". Its feed server (feeds.newsfilecorp.com) still answers normally.
V2 also had a head-of-line stall: it tried releases oldest first and stopped at the first blocked page, so one stuck
release was retried every run and the rest never got a turn.

What a run does (timer, every 2 minutes):
  1. Read the three metals feeds (feed server: cheap, not blocked).
     Overflow check: each feed holds only its last 10 releases. If a feed's new list shares nothing with what the
     previous run saw, releases may have fallen off in between -> logged as OVERFLOW and the backstop is run.
  2. Pick the releases not handled yet. Fresh ones first (fewest tries, then newest), so nothing blocks the queue.
  3. Read release pages on the website ONLY for those, and only while the website is not on back-off:
       - at most PAGE_BUDGET pages a run, PAGE_GAP seconds apart;
       - the first challenged page puts the WEBSITE on back-off (state file): 30 min, doubling to 4 h, reset by the
         next page that reads fine. While on back-off, a run reads feeds only. So while Newsfile blocks us we make a
         handful of website requests a day instead of hundreds, and when it lifts we are back within one back-off.
  4. Duplicate check against MNT and POST to the portal's /ingest webhook, exactly as V2. A release is never stored
     without its text (unchanged rule).
Backstop (--backstop; own timer twice a day, and after an OVERFLOW): read the per-company feed
feeds.newsfilecorp.com/company/<id> for each company in tickers.json that has a Newsfile company_id, a few seconds
apart, and queue anything the industry feeds did not show. Feed server only; pages are then read under the same
back-off as above.

The per-company website reads in mnt-scraper (sources/newsfile.list_recent, 89 companies every 30 min) are switched off
separately by the flag file data/newsfile_company_pages.off (sources/newsfile.py, NFCP_OFF_V1).

Run:
  python3 sync_newsfile_direct.py                       live run (timer)
  python3 sync_newsfile_direct.py --dry-run             feeds + (back-off permitting) pages + MNT read-only; writes nothing
  python3 sync_newsfile_direct.py --backstop [--dry-run] [--limit N]
  python3 sync_newsfile_direct.py --no-pages ...        never touch the website (feeds and MNT only)
  python3 sync_newsfile_direct.py --test-urls URL [URL ...]
  python3 sync_newsfile_direct.py --self-test           offline tests
  ... --stubs                                           V4: make (or, with --dry-run, preview) short versions even
                                                        without data/newsfile_stubs.on
Source-name: newsfile. classifier_model newsfile_direct_v1 (unchanged, so V1-V3 rows are found the same way).
"""
from __future__ import annotations

import email.utils
import hashlib
import html as _html
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, "/opt/mnt/app")

VERSION = "NFDIRECT_V4"
STUB_MODEL = "newsfile_feed_stub_v1"
STUBS_FLAG = Path(os.environ.get("NFDIRECT_STUBS_FLAG", "/opt/mnt/app/data/newsfile_stubs.on"))
STUB_MAX_AGE_DAYS = 4         # no short version for a release older than this
FILL_DAYS = 2                 # a copy within this many days of the release can replace its short version
FILL_OVERLAP = 0.5            # share of the opening's 8-word phrases that must be found in the copy
FEEDS = [
    "https://feeds.newsfilecorp.com/industry/mining-metals",
    "https://feeds.newsfilecorp.com/industry/precious-metals",
    "https://feeds.newsfilecorp.com/industry/non-ferrous-metals",
]
COMPANY_FEED = "https://feeds.newsfilecorp.com/company/{cid}"
UA = "Mozilla/5.0 (compatible; MNT-newsfile-direct/1.0; +https://miningnewsterminal.com)"
APP = Path(os.environ.get("MNT_APP", "/opt/mnt/app"))
PORTAL_DB = os.environ.get("PORTAL_DB", str(APP / "portal" / "portal.db"))
TICKERS_JSON = Path(os.environ.get("NFDIRECT_TICKERS", str(APP / "tickers.json")))
SEEN_FILE = Path(os.environ.get("NFDIRECT_SEEN", str(APP / "data" / "seen_newsfile_direct.json")))
STATE_FILE = Path(os.environ.get("NFDIRECT_STATE", str(APP / "data" / "newsfile_direct_state.json")))
MAX_TRIES = 30                                                     # page attempts per release (back-off paces them)
PAGE_BUDGET = int(os.environ.get("NFDIRECT_PAGE_BUDGET", "3"))    # release pages read per run
PAGE_GAP = float(os.environ.get("NFDIRECT_PAGE_GAP", "20"))       # seconds between release-page reads
BACKOFF_START = int(os.environ.get("NFDIRECT_BACKOFF_START", "1800"))   # 30 min after the first challenge
BACKOFF_MAX = int(os.environ.get("NFDIRECT_BACKOFF_MAX", "14400"))      # doubling, capped at 4 h
BACKSTOP_GAP = float(os.environ.get("NFDIRECT_BACKSTOP_GAP", "3"))      # seconds between company-feed reads
FEED_SIZE = 10        # Newsfile industry feeds hold the last 10 releases
TWIN_DAYS = 3
MAX_AGE_DAYS = 4      # ignore feed items older than this; the TSX/CSE copy covers anything older
TIMEOUT = 25

# "(TSXV: ABC)", "(TSX-V: ABC)", "(TSX VENTURE: ABC)", "(CSE: ABC)", "(TSX: ABC)", "(NEO: ABC)", "(Cboe Canada: ABC)"
_CAN_RE = re.compile(
    r"\(\s*(TSX[\s\-.]?V(?:enture)?(?:\s+Exchange)?|TSX(?:\s+Venture(?:\s+Exchange)?)?|CSE|CNSX|CNQ|NEO|Cboe\s+Canada)"
    r"\s*[:\-]\s*([A-Z][A-Z0-9]{0,6}(?:\.[A-Z]{1,2})?)\s*[,;)]",
    re.I)
_SUFFIX = {"V": ".V", "TO": ".TO", "CN": ".CN", "NE": ".NE"}
_RID_RE = re.compile(r"/release/(\d+)(?:/|$)")


# ------------------------------------------------------------------ time helpers
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ parsing (pure, self-tested)
def exchange_suffix(ex: str) -> str:
    e = re.sub(r"[\s\-.]+", "", ex.upper())
    if e.startswith("TSXV") or "VENTURE" in e:
        return "V"
    if e == "TSX":
        return "TO"
    if e in ("CSE", "CNSX", "CNQ"):
        return "CN"
    if e in ("NEO", "CBOECANADA"):
        return "NE"
    return ""


def extract_ticker(text: str):
    """First Canadian listing in the release's opening text -> ('ABC.V', 'TSXV') or (None, None)."""
    for m in _CAN_RE.finditer((text or "")[:3000]):
        suf = exchange_suffix(m.group(1))
        if not suf:
            continue
        sym = m.group(2).upper()
        tk = sym if sym.endswith(_SUFFIX[suf]) else sym + _SUFFIX[suf]
        ex = {"V": "TSXV", "TO": "TSX", "CN": "CSE", "NE": "NEO"}[suf]
        return tk, ex
    return None, None


def pubdate_utc(s: str):
    """RSS pubDate 'Fri, 16 Oct 2026 07:30:00 -0400' -> '2026-10-16T11:30:00Z'."""
    try:
        d = email.utils.parsedate_to_datetime((s or "").strip())
    except (TypeError, ValueError, IndexError):
        return None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone(timedelta(hours=-4)))
    return _iso(d.astimezone(timezone.utc))


def release_id(url: str):
    m = _RID_RE.search(url or "")
    return m.group(1) if m else None


def parse_feed(xml_bytes: bytes):
    """[{rid, url, headline, published_at, teaser}] from a Newsfile RSS 2.0 feed."""
    out = []
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        url = (it.findtext("link") or it.findtext("guid") or "").strip()
        rid = release_id(url)
        if not rid:
            continue
        url = re.sub(r"[?#].*$", "", url)
        desc = re.sub(r"<[^>]+>", " ", _html.unescape(it.findtext("description") or ""))
        out.append({"rid": rid, "url": url, "headline": _html.unescape((it.findtext("title") or "").strip()),
                    "published_at": pubdate_utc(it.findtext("pubDate") or ""),
                    "teaser": re.sub(r"\s+", " ", desc).strip()})
    return out


def feed_overflowed(prev_rids, new_rids) -> bool:
    """True when a full feed shares no release with the previous read: releases may have fallen off in between.
    No previous read (first run) is not an overflow."""
    prev, new = set(prev_rids or []), set(new_rids or [])
    return bool(prev) and len(new) >= FEED_SIZE and not (prev & new)


def queue_order(items, seen):
    """Fresh releases first: fewest tries, then newest. A release that keeps failing cannot block the others."""
    def key(it):
        tries = int((seen.get(it["rid"]) or {}).get("tries", 0))
        return (tries, "~" if not it.get("published_at") else "", _neg(it.get("published_at") or ""))
    return sorted(items, key=key)


def _neg(s: str) -> str:
    # sort key that orders ISO timestamps newest first inside an ascending sort
    return "".join(chr(0x10FFFF - ord(c)) for c in s)


def next_backoff(prev_s: int) -> int:
    return min(max(prev_s * 2, BACKOFF_START), BACKOFF_MAX) if prev_s else BACKOFF_START


def company_feed_targets(rows):
    """[(cid, ticker)] for tickers.json rows that carry a Newsfile company_id (source newsfile*)."""
    out, seen_c = [], set()
    for r in rows or []:
        if not isinstance(r, dict) or not str(r.get("source") or "").startswith("newsfile"):
            continue
        if r.get("exclude_auto") or r.get("excluded"):
            continue
        cid = (r.get("source_params") or {}).get("company_id")
        if cid is None or not str(cid).isdigit() or str(cid) in seen_c:
            continue
        seen_c.add(str(cid))
        out.append((str(cid), r.get("ticker") or ""))
    return out


# ------------------------------------------------------------------ state files
def _load_json(p: Path) -> dict:
    try:
        v = json.loads(p.read_text())
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_json(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, sort_keys=True))
    os.replace(tmp, p)


def load_seen() -> dict:
    return _load_json(SEEN_FILE)


def save_seen(seen: dict) -> None:
    _save_json(SEEN_FILE, dict(sorted(seen.items(), key=lambda kv: int(kv[0]))[-6000:]))


# ------------------------------------------------------------------ MNT side (read-only)
_ro_con = None


def _ro():
    global _ro_con
    if _ro_con is None:
        _ro_con = sqlite3.connect(f"file:{PORTAL_DB}?mode=ro", uri=True, timeout=60)
        _ro_con.execute("PRAGMA busy_timeout=30000")
    return _ro_con


def already_on_mnt(ticker, headline, body, published, rid):
    """(event_id, why) of a release MNT already holds that is this one, else (None, None). Indexed lookups only."""
    import sync_newswire_ca as NW
    base = (ticker or "").split(".")[0].upper()
    if not base or not published:
        return None, None
    d = datetime.fromisoformat(published[:10])
    lo = (d - timedelta(days=TWIN_DAYS)).strftime("%Y-%m-%d")
    hi = (d + timedelta(days=TWIN_DAYS + 1)).strftime("%Y-%m-%d")
    t1 = NW._nw_toks((body or "")[:2500])
    for eid, h2, b2, url2, st in _ro().execute(
            "SELECT event_id, raw_headline, substr(COALESCE(raw_body,''),1,2500), COALESCE(source_url,''), review_status "
            "FROM events WHERE (ticker = ? OR ticker LIKE ?) AND published_at >= ? AND published_at < ? "
            "AND COALESCE(classifier_model,'') != ?",
            (base, base + ".%", lo, hi, STUB_MODEL)):
        if rid and f"/release/{rid}/" in url2 + "/":
            return eid, "same Newsfile release (%s)" % st
        if st in ("auto_approved", "pending_review") and NW.same_release(headline, t1, h2 or "", NW._nw_toks(b2)):
            return eid, "same release from another source (%s)" % st
    return None, None


def on_mnt_by_rid(rid: str, ticker_hint: str, published: str):
    """Cheap pre-check without the page: is this exact Newsfile release already on MNT (by its URL)?"""
    base = (ticker_hint or "").split(".")[0].upper()
    if not base or not published:
        return None
    d = datetime.fromisoformat(published[:10])
    lo = (d - timedelta(days=1)).strftime("%Y-%m-%d")
    hi = (d + timedelta(days=2)).strftime("%Y-%m-%d")
    for (eid,) in _ro().execute(
            "SELECT event_id FROM events WHERE (ticker = ? OR ticker LIKE ?) AND published_at >= ? AND published_at < ? "
            "AND source_url LIKE ? AND COALESCE(classifier_model,'') != ?",
            (base, base + ".%", lo, hi, f"%/release/{rid}/%", STUB_MODEL)):
        return eid
    return None


# ------------------------------------------------------------------ network
def fetch_feed(url: str) -> bytes:
    import requests
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


def read_release(item: dict) -> dict:
    """sources/newsfile.fetch_body on the release page; adds raw_body / raw_html / raw_excerpt / ticker."""
    from sources import newsfile as NF
    s = {"source_url": item["url"], "published_at": item["published_at"], "raw_headline": item["headline"]}
    s = NF.fetch_body(s)
    body = s.get("raw_body") or ""
    tk, ex = extract_ticker(body)
    if not tk:
        tk, ex = extract_ticker(item.get("teaser") or "")
    if not tk and item.get("ticker_hint"):
        tk = item["ticker_hint"]
        ex = {".V": "TSXV", ".TO": "TSX", ".CN": "CSE", ".NE": "NEO"}.get("." + tk.split(".")[-1]) if "." in tk else None
    s.update(ticker=tk, exchange=ex, published_at=item["published_at"] or s.get("published_at"))
    return s


def event_id_for(url: str) -> str:
    return hashlib.sha256(("newsfile:" + url).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ V4: short versions (NFSTUB_V1)
def stub_event_id(url: str) -> str:
    return hashlib.sha256(("newsfile-stub:" + url).encode("utf-8")).hexdigest()


def stubs_on() -> bool:
    return STUBS_FLAG.exists()


def clean_teaser(t: str) -> str:
    """The feed's opening, without a trailing '...' and cut back to the last full sentence when one ends late enough."""
    t = re.sub(r"\s+", " ", (t or "")).strip()
    t = re.sub(r"\s*(\.\.\.|…)\s*$", "", t)
    t = re.sub(r"([a-z)][.!?][\"”]?)([A-Z])", r"\1 \2", t)   # the feed drops the gap between paragraphs
    m = list(re.finditer(r"[.!?](?=\s|$)", t))
    if m and m[-1].end() >= 0.6 * len(t):
        t = t[:m[-1].end()]
    return t


def stub_html(teaser: str, url: str) -> str:
    esc = _html.escape
    return ('<p>%s</p>\n<p class="nf-stub-note"><em>This is the opening of the release. The full text will appear '
            'here as soon as it is available; meanwhile, <a href="%s">read the full release on Newsfile</a>.</em></p>'
            % (esc(teaser), esc(url, quote=True)))


def stub_envelope(item: dict, tk: str) -> dict:
    t = clean_teaser(item.get("teaser") or "")
    return {
        "event_id": stub_event_id(item["url"]),
        "event_type": "news_release",
        "ticker": tk,
        "source_name": "newsfile",
        "source_url": item["url"],
        "raw_headline": item["headline"][:500],
        "raw_excerpt": t[:1500],
        "raw_body": t,
        "raw_html": stub_html(t, item["url"]),
        "published_at": item["published_at"],
        "review_status": "auto_approved",
        "classifier_model": STUB_MODEL,
        "classifier_confidence": 0.5,
    }


_rw_con = None


def _rw():
    global _rw_con
    if _rw_con is None:
        _rw_con = sqlite3.connect(PORTAL_DB, timeout=60)
        _rw_con.execute("PRAGMA busy_timeout=30000")
    return _rw_con


def get_stub(url: str):
    """The stored short version of this release (any status), as a dict of dupguard.EVENT_COLS, else None."""
    from portal import dupguard as G
    r = _ro().execute("SELECT %s FROM events WHERE event_id = ?" % ",".join(G.EVENT_COLS),
                      (stub_event_id(url),)).fetchone()
    return dict(zip(G.EVENT_COLS, tuple(r))) if r else None


def copy_on_mnt(ticker: str, opening: str, published: str, exclude=()):
    """A visible release of the same company within FILL_DAYS whose text holds the opening (8-word phrases), else None.
    Short versions never count."""
    from portal import dupguard as G
    base = (ticker or "").split(".")[0].upper()
    if not base or not published or len((opening or "").split()) < 25:
        return None
    d = datetime.fromisoformat(published[:10])
    lo = (d - timedelta(days=FILL_DAYS)).strftime("%Y-%m-%d")
    hi = (d + timedelta(days=FILL_DAYS + 1)).strftime("%Y-%m-%d")
    best = None
    for row in _ro().execute(
            "SELECT %s FROM events WHERE (ticker = ? OR ticker LIKE ?) AND published_at >= ? AND published_at < ? "
            "AND review_status IN ('auto_approved','approved') AND COALESCE(classifier_model,'') != ?"
            % ",".join(G.EVENT_COLS), (base, base + ".%", lo, hi, STUB_MODEL)):
        r = dict(zip(G.EVENT_COLS, tuple(row)))
        if r["event_id"] in exclude:
            continue
        ov = G.body_overlap(opening, r.get("raw_body") or re.sub(r"<[^>]+>", " ", r.get("raw_html") or ""))
        if ov >= FILL_OVERLAP and (best is None or ov > best[0]):
            best = (ov, r)
    return best[1] if best else None


def held_back_copy(stub_id: str):
    """The newest copy the duplicate guard held back because the short version was there (full row), else None."""
    r = _ro().execute("SELECT row_json FROM dup_guard_log WHERE action='skipped_new' AND kept_id=? AND row_json IS NOT NULL "
                      "ORDER BY id DESC LIMIT 1", (stub_id,)).fetchone()
    if not r:
        return None
    try:
        row = json.loads(r[0])
    except ValueError:
        return None
    if _ro().execute("SELECT 1 FROM events WHERE event_id=?", (row.get("event_id"),)).fetchone():
        return None
    return row


def block_readers(conn, eid: str) -> int:
    """The rules readers skip the short version: one 'ok', 0-record run per active reader version."""
    n = 0
    for ext, ver in conn.execute("SELECT extractor, version FROM fx_extractor_versions WHERE status='active'").fetchall():
        n += conn.execute("INSERT OR IGNORE INTO fx_runs(event_id, extractor, version, tag_confirmed, n_records, status, "
                          "error, body_sha1) VALUES (?,?,?,0,0,'ok','NFSTUB_V1: short version, not read',NULL)",
                          (eid, ext, ver)).rowcount
    return n


def remove_stub(conn, stub: dict, kept: dict, action: str = "stub_replaced") -> None:
    """Log the short version in full, delete it and everything read from it, forward its address to `kept`."""
    from portal import dupguard as G
    sid = stub["event_id"]
    G.ensure_log(conn)                 # executescript commits, so it must run before the savepoint
    conn.execute("SAVEPOINT nfstub")
    try:
        G.log(conn, action, stub, kept, True)
        conn.execute("DELETE FROM fx_facts WHERE record_id IN (SELECT record_id FROM fx_records WHERE event_id=?)", (sid,))
        conn.execute("DELETE FROM fx_record_events WHERE record_id IN (SELECT record_id FROM fx_records WHERE event_id=?)",
                     (sid,))
        conn.execute("DELETE FROM fx_record_events WHERE event_id=?", (sid,))
        conn.execute("DELETE FROM fx_records WHERE event_id=?", (sid,))
        conn.execute("DELETE FROM fx_runs WHERE event_id=?", (sid,))
        conn.execute("DELETE FROM reader_tags WHERE event_id=?", (sid,))
        conn.execute("DELETE FROM events WHERE event_id=?", (sid,))
        if stub.get("slug") and stub.get("ticker") and \
                (stub["slug"] != kept.get("slug") or (stub["ticker"] or "").upper() != (kept.get("ticker") or "").upper()):
            conn.execute("INSERT OR IGNORE INTO event_slug_aliases (ticker, old_slug, event_id, source) VALUES (?,?,?,?)",
                         (stub["ticker"].lower(), stub["slug"].lower(), kept["event_id"], "NFSTUB_V1"))
        conn.execute("RELEASE nfstub")
        conn.commit()
    except Exception:
        conn.execute("ROLLBACK TO nfstub")
        conn.execute("RELEASE nfstub")
        raise


def make_stub(item: dict, apply: bool, seen: dict, counts: dict) -> str:
    """Step 1. Returns 'made', 'exists', 'on_mnt' (the release is already there: seen updated) or a skip reason."""
    import sync_newswire_ca as NW
    url, rid = item["url"], item["rid"]
    if not item.get("published_at") or item["published_at"] < _iso(_now() - timedelta(days=STUB_MAX_AGE_DAYS)):
        return "too_old"
    if get_stub(url):
        return "exists"
    if NW.NON_MINING_HINTS.search(item["headline"]):
        return "non_mining"
    tk = extract_ticker(item.get("teaser") or "")[0] or item.get("ticker_hint")
    if not tk:
        counts["stub_no_ticker"] += 1
        return "no_ticker"
    opening = clean_teaser(item.get("teaser") or "")
    tag = f"{rid} {item['headline'][:60]}"
    try:
        eid = on_mnt_by_rid(rid, tk, item["published_at"])
        twin = None
        if not eid:
            twin, _why = already_on_mnt(tk, item["headline"], opening, item["published_at"], rid)
        if not eid and not twin:
            c = copy_on_mnt(tk, opening, item["published_at"])
            twin = c["event_id"] if c else None
    except Exception as e:  # noqa: BLE001 - if the check fails, make nothing this run
        print(f"  ! stub check failed ({type(e).__name__}: {e})  {tag}", flush=True)
        return "check_failed"
    if eid or twin:
        counts["already_on_mnt"] += 1
        seen[rid] = {"st": "on_mnt", "event": (eid or twin)[:12]}
        print(f"  = {tk:10s} already on MNT as {(eid or twin)[:12]} (no short version, no page read)  {tag}", flush=True)
        return "on_mnt"
    env = stub_envelope(item, tk)
    if not apply:
        counts["would_stub"] += 1
        print(f"  ~ WOULD PUBLISH SHORT VERSION {tk:10s} {item['published_at']}  {len(opening)} chars  {tag}", flush=True)
        print(f"      opening: {opening[:300]}{'…' if len(opening) > 300 else ''}", flush=True)
        return "would"
    code = NW.post_to_ingest(env)
    if code not in (200, 201, 202):
        counts["post_failed"] += 1
        print(f"  X short version HTTP {code}  {tag}", flush=True)
        return "post_failed"
    conn = _rw()
    row = conn.execute("SELECT review_status FROM events WHERE event_id=?", (env["event_id"],)).fetchone()
    if not row:
        counts["stub_refused"] += 1
        print(f"  - short version not stored (duplicate guard or gate)  {tk:10s} {tag}", flush=True)
        return "refused"
    block_readers(conn, env["event_id"])
    conn.commit()
    counts["stubbed"] += 1
    print(f"  ~ short version published {tk:10s} {item['published_at']} ({row[0]})  {tag}", flush=True)
    return "made"


def fill_stubs(apply: bool, counts: dict) -> None:
    """Step 2, a and b: a full copy already on MNT, or one the duplicate guard held back, takes over each short version.
    Also puts back a short version left hidden by an interrupted page take-over."""
    from portal import dupguard as G
    since = _iso(_now() - timedelta(days=STUB_MAX_AGE_DAYS + FILL_DAYS + 1))
    stubs = [dict(zip(G.EVENT_COLS, tuple(r))) for r in _ro().execute(
        "SELECT %s FROM events WHERE classifier_model=? AND published_at >= ?" % ",".join(G.EVENT_COLS),
        (STUB_MODEL, since)).fetchall()]
    counts["stubs_live"] = sum(1 for s in stubs if s["review_status"] in ("auto_approved", "pending_review"))
    for s in stubs:
        tag = f"{s['ticker']:10s} {(s['raw_headline'] or '')[:60]}"
        if s["review_status"] == "superseded_stub":
            full = _ro().execute("SELECT event_id, slug, ticker, source_name FROM events WHERE event_id=?",
                                 (event_id_for(s["source_url"]),)).fetchone()
            if apply:
                conn = _rw()
                if full:
                    remove_stub(conn, s, dict(zip(("event_id", "slug", "ticker", "source_name"), full)))
                else:
                    conn.execute("UPDATE events SET review_status='auto_approved' WHERE event_id=?", (s["event_id"],))
                    conn.commit()
            print(f"  ! interrupted take-over tidied ({'full release kept' if full else 'short version shown again'})  {tag}",
                  flush=True)
            continue
        kept, how = copy_on_mnt(s["ticker"], s["raw_body"], s["published_at"], exclude=(s["event_id"],)), "copy on MNT"
        if not kept:
            row = held_back_copy(s["event_id"])
            if row:
                kept, how = row, "held-back %s copy" % (row.get("source_name") or "?")
        if not kept:
            continue
        counts["filled"] += 1
        if not apply:
            print(f"  ^ WOULD REPLACE short version by {how} {kept['event_id'][:12]}  {tag}", flush=True)
            continue
        conn = _rw()
        if how.startswith("held-back"):
            from portal import db as PDB
            kept = dict(kept)
            kept["slug"] = kept.get("slug") or PDB._auto_slug(kept.get("raw_headline") or "")
            kept["categories"] = kept.get("categories") or PDB._auto_categorize(kept)
            G.restore_row(conn, kept)
            G.log(conn, "restored", kept, s, False)
            conn.commit()
            if not conn.execute("SELECT 1 FROM events WHERE event_id=?", (kept["event_id"],)).fetchone():
                print(f"  ! could not put back the held-back copy; short version stays  {tag}", flush=True)
                continue
        remove_stub(conn, s, kept)
        print(f"  ^ short version replaced by {how} {kept['event_id'][:12]}  {tag}", flush=True)


def take_over_from_page(item: dict, env: dict, apply: bool, counts: dict):
    """Step 2c, around the normal post: remove the short version (logged in full), post the full release, and put the
    short version back if the full release was not stored. Removing first matters: MNT's older headline matcher
    (_find_fuzzy_dupe) ignores review_status, so even a hidden short version would make it refuse the full release.
    Returns the HTTP code, or None when there is no short version (the caller posts as before)."""
    import sync_newswire_ca as NW
    from portal import dupguard as G
    stub = get_stub(item["url"])
    if not stub:
        return None
    if not apply:
        counts["would_take_over"] += 1
        print(f"  ^ WOULD REPLACE short version {stub['event_id'][:12]} with the full release", flush=True)
        return 200
    conn = _rw()
    remove_stub(conn, stub, {"event_id": env["event_id"], "slug": stub.get("slug"), "ticker": stub.get("ticker"),
                             "source_name": "newsfile"})            # same slug passed: no address forward yet
    try:
        code = NW.post_to_ingest(env)
    except Exception as e:  # noqa: BLE001
        code = "%s: %s" % (type(e).__name__, e)
    full = conn.execute("SELECT event_id, slug, ticker FROM events WHERE event_id=?", (env["event_id"],)).fetchone()
    if code in (200, 201, 202) and full:
        if stub.get("slug") and stub.get("ticker") and full[1] and full[1] != stub["slug"]:
            conn.execute("INSERT OR IGNORE INTO event_slug_aliases (ticker, old_slug, event_id, source) VALUES (?,?,?,?)",
                         (stub["ticker"].lower(), stub["slug"].lower(), full[0], "NFSTUB_V1"))
            conn.commit()
        counts["taken_over"] += 1
        print(f"  ^ full release replaced its short version {stub['event_id'][:12]}", flush=True)
    else:
        G.restore_row(conn, stub)
        block_readers(conn, stub["event_id"])
        G.log(conn, "stub_restored", stub, None, False)
        conn.commit()
        print(f"  ! full release not stored (HTTP {code}); short version put back", flush=True)
    return code


# ------------------------------------------------------------------ one release
def handle(item: dict, apply: bool, seen: dict, counts: dict) -> str:
    """'' normally; 'blocked' when the release page came back empty (the WAF)."""
    import sync_newswire_ca as NW
    rid = item["rid"]
    tag = f"{rid} {item['headline'][:70]}"
    if NW.NON_MINING_HINTS.search(item["headline"]):
        counts["non_mining"] += 1
        print(f"  - non-mining  {tag}", flush=True)
        seen[rid] = {"st": "non_mining"}
        return ""
    counts["pages_read"] += 1
    try:
        s = read_release(item)
    except Exception as e:  # noqa: BLE001
        s = {"fetch_error": f"{type(e).__name__}: {e}"}
    body = s.get("raw_body") or ""
    if s.get("fetch_error") or len(body) < 200:
        tries = int((seen.get(rid) or {}).get("tries", 0)) + 1
        counts["page_unreadable"] += 1
        print(f"  ! unreadable ({s.get('fetch_error') or 'body %d chars' % len(body)}; try {tries}/{MAX_TRIES}) {tag}",
              flush=True)
        seen[rid] = {"st": "gave_up" if tries >= MAX_TRIES else "retry", "tries": tries}
        return "blocked"
    counts["pages_ok"] += 1
    tk = s.get("ticker")
    if not tk:
        counts["no_ticker"] += 1
        print(f"  - no Canadian ticker  {tag}", flush=True)
        seen[rid] = {"st": "no_ticker"}
        return ""
    try:
        twin, why = already_on_mnt(tk, item["headline"], body, item["published_at"], rid)
    except Exception as e:  # noqa: BLE001 - if the check fails, do not risk a duplicate: retry next run
        counts["check_failed"] += 1
        print(f"  ! duplicate check failed ({type(e).__name__}: {e}); will retry  {tag}", flush=True)
        return ""
    if twin:
        counts["already_on_mnt"] += 1
        print(f"  = {tk:10s} already on MNT as {twin[:12]} ({why})  {tag}", flush=True)
        seen[rid] = {"st": "on_mnt", "event": twin[:12]}
        return ""
    env = {
        "event_id": event_id_for(item["url"]),
        "event_type": "news_release",
        "ticker": tk,
        "source_name": "newsfile",
        "source_url": item["url"],
        "raw_headline": item["headline"][:500],
        "raw_excerpt": (s.get("raw_excerpt") or body)[:1500],
        "raw_body": body[:50000],
        "raw_html": (s.get("raw_html") or "")[:200000],
        "published_at": item["published_at"] or NW._now_utc(),
        "categories": ["news"],
        "_exchange": s.get("exchange"),
        "_cfg_website": item["url"],
        "_source_name": "newsfile",
        "review_status": "auto_approved",
        "classifier_model": "newsfile_direct_v1",
        "classifier_confidence": 0.85,
    }
    if not apply:
        counts["would_ingest"] += 1
        print(f"  + WOULD INGEST {tk:10s} {item['published_at']}  body {len(body)} chars  {tag}", flush=True)
        take_over_from_page(item, env, False, counts)
        return ""
    code = take_over_from_page(item, env, True, counts)      # V4: replaces the short version when there is one
    if code is None:
        code = NW.post_to_ingest(env)
    if code in (200, 201, 202):
        counts["ingested"] += 1
        seen[rid] = {"st": "ingested", "code": code}
        print(f"  + {tk:10s} {item['published_at']}  {tag}", flush=True)
    else:
        counts["post_failed"] += 1
        tries = int((seen.get(rid) or {}).get("tries", 0)) + 1
        seen[rid] = {"st": "gave_up" if tries >= MAX_TRIES else "retry", "tries": tries, "code": code}
        print(f"  X HTTP {code} (try {tries}/{MAX_TRIES})  {tag}", flush=True)
    return ""


# ------------------------------------------------------------------ the queue (shared by feeds and backstop)
def work_queue(items, apply: bool, pages: bool, seen: dict, state: dict, counts: dict, stubs: bool = False) -> None:
    cutoff = _iso(_now() - timedelta(days=MAX_AGE_DAYS))
    todo = []
    for it in items:
        st = (seen.get(it["rid"]) or {}).get("st")
        if st and st != "retry":
            continue
        if it.get("published_at") and it["published_at"] < cutoff:
            counts["too_old"] += 1
            continue
        todo.append(it)
    counts["new"] += len(todo)
    if stubs and todo:                          # V4 step 1: short versions first; needs no website request
        keep = []
        for it in queue_order(todo, seen):
            if make_stub(it, apply, seen, counts) != "on_mnt":
                keep.append(it)
        todo = keep
    if not todo:
        return
    if not pages:
        counts["left_for_next_run"] += len(todo)
        print(f"[newsfile_direct] website reads off (--no-pages): {len(todo)} release(s) queued", flush=True)
        return
    until = _parse_iso(state.get("backoff_until"))
    if until and _now() < until:
        counts["left_for_next_run"] += len(todo)
        counts["backoff_skip"] = 1
        print(f"[newsfile_direct] website on back-off until {state['backoff_until']} "
              f"({state.get('backoff_s', 0) // 60} min); {len(todo)} release(s) wait, feeds only this run", flush=True)
        return
    read = 0
    for n, it in enumerate(queue_order(todo, seen)):
        if read >= PAGE_BUDGET:
            counts["left_for_next_run"] += len(todo) - n
            break
        if read:
            time.sleep(PAGE_GAP)
        # cheap duplicate pre-check first: a release already on MNT needs no website read at all
        if it.get("ticker_hint") or extract_ticker(it.get("teaser") or "")[0]:
            hint = it.get("ticker_hint") or extract_ticker(it.get("teaser") or "")[0]
            try:
                eid = on_mnt_by_rid(it["rid"], hint, it.get("published_at"))
            except Exception:  # noqa: BLE001
                eid = None
            if eid:
                counts["already_on_mnt"] += 1
                seen[it["rid"]] = {"st": "on_mnt", "event": eid[:12]}
                print(f"  = {hint:10s} already on MNT as {eid[:12]} (same Newsfile release, no page read)  "
                      f"{it['rid']} {it['headline'][:60]}", flush=True)
                continue
        read += 1
        if handle(it, apply, seen, counts) == "blocked":
            b = next_backoff(int(state.get("backoff_s") or 0))
            state.update(backoff_s=b, backoff_until=_iso(_now() + timedelta(seconds=b)), last_block=_iso(_now()))
            counts["left_for_next_run"] += len(todo) - n - 1
            print(f"[newsfile_direct] website challenged -> back-off {b // 60} min (until {state['backoff_until']})",
                  flush=True)
            break
        if counts["pages_ok"]:
            if state.get("backoff_s"):
                print("[newsfile_direct] website reads fine again -> back-off cleared", flush=True)
            state.update(backoff_s=0, backoff_until=None, last_page_ok=_iso(_now()))


def _counts():
    return {k: 0 for k in ("feed_items", "new", "ingested", "would_ingest", "already_on_mnt", "no_ticker",
                           "non_mining", "page_unreadable", "pages_ok", "check_failed", "post_failed", "too_old",
                           "feed_errors", "pages_read", "left_for_next_run", "overflow", "backoff_skip",
                           "would_stub", "stubbed", "stub_refused", "stub_no_ticker", "stubs_live", "filled",
                           "would_take_over", "taken_over")}


def _finish(apply, seen, state, counts, label) -> None:
    if apply:
        save_seen(seen)
        _save_json(STATE_FILE, state)
    print("[newsfile_direct] %s %s  %s" % (label, "DONE" if apply else "DRY RUN (nothing written)",
                                           "  ".join(f"{k}={v}" for k, v in counts.items())), flush=True)


# ------------------------------------------------------------------ feeds run (timer, every 2 min)
def run(apply: bool, pages: bool = True, items=None, stubs=None) -> int:
    stubs = stubs_on() if stubs is None else stubs
    seen, state, counts = load_seen(), _load_json(STATE_FILE), _counts()
    if items is None:
        items, ids = [], set()
        last = state.setdefault("last_feed_rids", {})
        for f in FEEDS:
            try:
                got = parse_feed(fetch_feed(f))
            except Exception as e:  # noqa: BLE001
                counts["feed_errors"] += 1
                print(f"[newsfile_direct] FEED FAIL {f}: {type(e).__name__}: {e}", flush=True)
                continue
            rids = [g["rid"] for g in got]
            if feed_overflowed(last.get(f), rids):
                counts["overflow"] += 1
                state["backstop_due"] = True
                print(f"[newsfile_direct] OVERFLOW {f}: none of the previous {len(last.get(f) or [])} releases is "
                      f"still listed; some may have been missed -> backstop due", flush=True)
            last[f] = rids
            print(f"[newsfile_direct] {f} -> {len(got)} items", flush=True)
            for it in got:
                if it["rid"] not in ids:
                    ids.add(it["rid"])
                    items.append(it)
    counts["feed_items"] = len(items)
    work_queue(items, apply, pages, seen, state, counts, stubs=stubs)
    try:                                        # V4 step 2a/2b: copies that take over short versions
        fill_stubs(apply, counts)
    except Exception as e:  # noqa: BLE001 - never let the take-over stop collection
        print(f"[newsfile_direct] fill_stubs failed: {type(e).__name__}: {e}", flush=True)
    state["last_run"] = _iso(_now())
    _finish(apply, seen, state, counts, VERSION)
    if apply and state.get("backstop_due"):
        print("[newsfile_direct] running the company-feed backstop after an overflow", flush=True)
        return backstop(apply, pages, stubs=stubs)
    return 0


# ------------------------------------------------------------------ backstop (twice a day, or after an overflow)
def backstop(apply: bool, pages: bool = True, limit: int = 0, stubs=None) -> int:
    stubs = stubs_on() if stubs is None else stubs
    seen, state, counts = load_seen(), _load_json(STATE_FILE), _counts()
    try:
        rows = json.loads(TICKERS_JSON.read_text())
    except (OSError, ValueError) as e:
        print(f"[newsfile_direct] BACKSTOP cannot read {TICKERS_JSON}: {e}", flush=True)
        return 1
    if isinstance(rows, dict):
        rows = rows.get("tickers") or list(rows.values())
    targets = company_feed_targets(rows)
    if limit:
        targets = targets[:limit]
    print(f"[newsfile_direct] BACKSTOP {len(targets)} company feeds, {BACKSTOP_GAP:.0f} s apart", flush=True)
    cutoff = _iso(_now() - timedelta(days=MAX_AGE_DAYS))
    found, ids, feeds_ok, feeds_bad, recent = [], set(), 0, 0, 0
    for n, (cid, tk) in enumerate(targets):
        if n:
            time.sleep(BACKSTOP_GAP)
        try:
            got = parse_feed(fetch_feed(COMPANY_FEED.format(cid=cid)))
            feeds_ok += 1
        except Exception as e:  # noqa: BLE001
            feeds_bad += 1
            counts["feed_errors"] += 1
            print(f"  ! company feed {cid} ({tk}): {type(e).__name__}: {str(e)[:80]}", flush=True)
            if feeds_bad >= 5 and feeds_ok == 0:
                print("[newsfile_direct] BACKSTOP: first 5 company feeds all failed; stopping", flush=True)
                break
            continue
        for it in got:
            if it["rid"] in ids or (it.get("published_at") or "") < cutoff:
                continue
            recent += 1
            if (seen.get(it["rid"]) or {}).get("st") not in (None, "retry"):
                continue
            ids.add(it["rid"])
            it["ticker_hint"] = tk
            found.append(it)
            print(f"  ? not seen in the industry feeds: {tk:10s} {it['published_at']}  {it['rid']} "
                  f"{it['headline'][:60]}", flush=True)
    print(f"[newsfile_direct] BACKSTOP feeds ok={feeds_ok} failed={feeds_bad}; releases in the last "
          f"{MAX_AGE_DAYS} days={recent}; not yet handled={len(found)}", flush=True)
    counts["feed_items"] = len(found)
    work_queue(found, apply, pages, seen, state, counts, stubs=stubs)
    state["backstop_due"] = False
    state["last_backstop"] = _iso(_now())
    _finish(apply, seen, state, counts, VERSION + " BACKSTOP")
    return 0


# ------------------------------------------------------------------ manual URL test
def _test_urls(urls) -> int:
    items = []
    for u in urls:
        rid = release_id(u)
        if not rid:
            print(f"not a Newsfile release URL: {u}")
            continue
        items.append({"rid": rid, "url": re.sub(r"[?#].*$", "", u), "headline": "", "published_at": None, "teaser": ""})
    from sources import newsfile as NF
    for n, it in enumerate(items):
        if n:
            time.sleep(PAGE_GAP)
        s = NF.fetch_body({"source_url": it["url"], "published_at": None, "raw_headline": ""})
        it["headline"] = s.get("raw_headline") or ""
        p = s.get("published_at")
        it["published_at"] = (_iso(datetime.fromisoformat(p).astimezone(timezone.utc)) if p else None)
    return run(apply=False, items=items)


# ------------------------------------------------------------------ self-test (offline)
def _self_test() -> int:
    bad = 0

    def ok(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print(f"FAIL {name}: got {got!r} want {want!r}")

    ok("tsxv", extract_ticker("VANCOUVER, BC (Newsfile Corp.) - Acme Gold Corp. (TSXV: ACM) (OTCQB: ACMGF) is"), ("ACM.V", "TSXV"))
    ok("tsx-v", extract_ticker("Acme (TSX-V: ACM) (FSE: 1A2)"), ("ACM.V", "TSXV"))
    ok("venture", extract_ticker("Acme (TSX Venture Exchange: ACM)"), ("ACM.V", "TSXV"))
    ok("tsx", extract_ticker("Big Mines Inc. (TSX: BIG) (NYSE: BIG)"), ("BIG.TO", "TSX"))
    ok("cse", extract_ticker("Small Co (CSE: SML) (OTC: SMLLF)"), ("SML.CN", "CSE"))
    ok("otc first, cse second", extract_ticker("X (OTCQB: XXXF) (CSE: XX)"), ("XX.CN", "CSE"))
    ok("comma list", extract_ticker("Acme (TSXV: ACM, OTCQB: ACMGF)"), ("ACM.V", "TSXV"))
    ok("none", extract_ticker("Acme (OTCQB: ACMGF) only"), (None, None))
    ok("pub edt", pubdate_utc("Fri, 16 Oct 2026 07:30:00 -0400"), "2026-10-16T11:30:00Z")
    ok("pub est", pubdate_utc("Mon, 12 Jan 2026 08:00:00 -0500"), "2026-01-12T13:00:00Z")
    ok("pub bad", pubdate_utc("yesterday"), None)
    ok("rid", release_id("https://www.newsfilecorp.com/release/319322/Bravada-Gold-Files-PEA"), "319322")
    feed = (b'<?xml version="1.0" ?><rss version="2.0"><channel><item><title>Bravada Gold Files PEA &amp; More</title>'
            b'<link>https://www.newsfilecorp.com/release/319322/Bravada-Gold-Files-PEA?x=1</link>'
            b'<description>&lt;img src="x" /&gt;Vancouver--(Newsfile Corp. - October 16, 2026) - Bravada (TSXV: BVA)'
            b'</description><pubDate>Fri, 16 Oct 2026 07:30:00 -0400</pubDate></item></channel></rss>')
    it = parse_feed(feed)
    ok("feed n", len(it), 1)
    ok("feed fields", (it[0]["rid"], it[0]["url"], it[0]["headline"], it[0]["published_at"]),
       ("319322", "https://www.newsfilecorp.com/release/319322/Bravada-Gold-Files-PEA", "Bravada Gold Files PEA & More",
        "2026-10-16T11:30:00Z"))
    ok("teaser ticker", extract_ticker(it[0]["teaser"]), ("BVA.V", "TSXV"))
    # V3: overflow detection
    ten = [str(i) for i in range(100, 110)]
    ok("overflow first run", feed_overflowed(None, ten), False)
    ok("overflow overlap", feed_overflowed(ten, ten[3:] + ["200", "201", "202"]), False)
    ok("overflow none shared", feed_overflowed(ten, [str(i) for i in range(300, 310)]), True)
    ok("overflow short feed", feed_overflowed(ten, ["300", "301"]), False)
    # V3: queue order - fresh first (fewest tries), newest first among equals; a stuck release goes last
    q = [{"rid": "1", "published_at": "2026-10-20T10:00:00Z"}, {"rid": "2", "published_at": "2026-10-27T10:00:00Z"},
         {"rid": "3", "published_at": "2026-10-26T10:00:00Z"}]
    ok("queue order", [x["rid"] for x in queue_order(q, {"1": {"st": "retry", "tries": 10}})], ["2", "3", "1"])
    ok("queue order no date last", [x["rid"] for x in queue_order(q + [{"rid": "4", "published_at": None}], {})],
       ["2", "3", "1", "4"])
    # V3: back-off doubles from 30 min to a 4 h cap
    ok("backoff first", next_backoff(0), 1800)
    ok("backoff double", next_backoff(1800), 3600)
    ok("backoff cap", next_backoff(14400), 14400)
    # V3: company feed targets
    rows = [{"ticker": "ACDX.CN", "source": "newsfile", "source_params": {"company_id": 8445}},
            {"ticker": "X.V", "source": "newsfile_gnews", "source_params": {"company_id": "123"}},
            {"ticker": "DEAD.CN", "source": "newsfile", "source_params": {"company_id": 1}, "exclude_auto": True},
            {"ticker": "Y.V", "source": "thenewswire"},
            {"ticker": "Z.V", "source": "newsfile", "source_params": {}},
            {"ticker": "ACDX2.CN", "source": "newsfile", "source_params": {"company_id": 8445}}]
    ok("company targets", company_feed_targets(rows), [("8445", "ACDX.CN"), ("123", "X.V")])
    # V3: work_queue honours the back-off without touching the network
    st = {"backoff_until": _iso(_now() + timedelta(minutes=10)), "backoff_s": 1800}
    c = _counts()
    work_queue([{"rid": "9", "url": "u", "headline": "h", "published_at": _iso(_now()), "teaser": ""}],
               False, True, {}, st, c)
    ok("backoff skip", (c["new"], c["pages_read"], c["left_for_next_run"], c["backoff_skip"]), (1, 0, 1, 1))
    c = _counts()
    work_queue([{"rid": "9", "url": "u", "headline": "h", "published_at": "2020-01-01T00:00:00Z", "teaser": ""}],
               False, True, {}, {}, c)
    ok("too old", (c["new"], c["too_old"]), (0, 1))
    # V4: short versions
    ok("teaser cut", clean_teaser("Vancouver - Acme (TSXV: ACM) is pleased to report drilling. Hole 1 cut 2 m of 5 g/t gold. More..."),
       "Vancouver - Acme (TSXV: ACM) is pleased to report drilling. Hole 1 cut 2 m of 5 g/t gold.")
    ok("teaser paragraph gap", clean_teaser("to focus on other business opportunities.The Company thanks them. In U.S. dollars."),
       "to focus on other business opportunities. The Company thanks them. In U.S. dollars.")
    ok("teaser keep", clean_teaser("Short one. Then a very long trailing fragment that goes on and on without any end at all ..."),
       "Short one. Then a very long trailing fragment that goes on and on without any end at all")
    u = "https://www.newsfilecorp.com/release/321076/Sankamap-Discovers"
    ok("stub id differs", stub_event_id(u) != event_id_for(u), True)
    ok("stub html escaped", "&lt;b&gt;" in stub_html("<b>x</b>", u) and 'href="' + u + '"' in stub_html("x", u), True)
    env = stub_envelope({"url": u, "headline": "Sankamap Discovers Gold", "published_at": "2026-10-27T12:00:00Z",
                         "teaser": "Toronto - Sankamap (CSE: SCU) discovers gold. ..."}, "SCU.CN")
    ok("stub env", (env["event_id"], env["classifier_model"], env["ticker"], env["raw_body"]),
       (stub_event_id(u), STUB_MODEL, "SCU.CN", "Toronto - Sankamap (CSE: SCU) discovers gold."))
    try:                                         # DB pieces: need portal.dupguard (on the server, or a clone on the path)
        from portal import dupguard as G
    except ImportError:
        G = None
        print("self-test: portal not importable here; DB tests skipped")
    if G:
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE events (%s, PRIMARY KEY(event_id))" % ",".join(G.EVENT_COLS))
        con.executescript("""CREATE TABLE fx_extractor_versions (extractor TEXT, version TEXT, status TEXT);
            CREATE TABLE fx_runs (event_id TEXT, extractor TEXT, version TEXT, tag_confirmed INT, n_records INT,
              status TEXT CHECK (status IN ('ok','error')), error TEXT, body_sha1 TEXT, ran_at TEXT DEFAULT (datetime('now')),
              PRIMARY KEY (extractor, version, event_id));
            CREATE TABLE fx_records (record_id INTEGER PRIMARY KEY, event_id TEXT);
            CREATE TABLE fx_facts (record_id INT, field TEXT);
            CREATE TABLE fx_record_events (record_id INT, event_id TEXT);
            CREATE TABLE reader_tags (event_id TEXT, tag TEXT);
            CREATE TABLE event_slug_aliases (ticker TEXT, old_slug TEXT, event_id TEXT, source TEXT, PRIMARY KEY(ticker, old_slug));
            INSERT INTO fx_extractor_versions VALUES ('drill_results','1.1.4','active'),('permits','1.0.13','active'),
              ('permits','1.0.12','retired');""")
        sid = stub_event_id(u)
        con.execute("INSERT INTO events (event_id, ticker, slug, source_name, raw_headline, classifier_model) VALUES (?,?,?,?,?,?)",
                    (sid, "SCU.CN", "sankamap-discovers-gold", "newsfile", "Sankamap Discovers Gold", STUB_MODEL))
        ok("block readers", block_readers(con, sid), 2)
        con.execute("INSERT INTO fx_records (record_id, event_id) VALUES (7, ?)", (sid,))
        con.execute("INSERT INTO fx_facts VALUES (7, 'x')")
        con.execute("INSERT INTO reader_tags VALUES (?, 'Drill Results')", (sid,))
        stub = dict(zip(G.EVENT_COLS, con.execute("SELECT %s FROM events" % ",".join(G.EVENT_COLS)).fetchone()))
        remove_stub(con, stub, {"event_id": "cse123", "slug": "scu-news-release", "ticker": "SCU.CN", "source_name": "cse"})
        left = [con.execute(q, (sid,)).fetchone()[0] for q in (
            "SELECT COUNT(*) FROM events WHERE event_id=?", "SELECT COUNT(*) FROM fx_runs WHERE event_id=?",
            "SELECT COUNT(*) FROM fx_records WHERE event_id=?", "SELECT COUNT(*) FROM reader_tags WHERE event_id=?")]
        left.append(con.execute("SELECT COUNT(*) FROM fx_facts").fetchone()[0])
        ok("stub removed cleanly", left, [0, 0, 0, 0, 0])
        ok("address forwarded", con.execute("SELECT event_id, source FROM event_slug_aliases WHERE old_slug='sankamap-discovers-gold'")
           .fetchone(), ("cse123", "NFSTUB_V1"))
        lg = con.execute("SELECT action, event_id, kept_id, row_json IS NOT NULL FROM dup_guard_log").fetchone()
        ok("stub logged in full", lg, ("stub_replaced", sid, "cse123", 1))
        # take-over from the page, both outcomes, with a stand-in for the portal's /ingest
        import types
        g = globals()
        saved = (g["_ro"], g["_rw"], sys.modules.get("sync_newswire_ca"))
        g["_ro"] = g["_rw"] = lambda: con
        fake = types.ModuleType("sync_newswire_ca")
        sys.modules["sync_newswire_ca"] = fake
        try:
            con.execute("DELETE FROM event_slug_aliases")          # the remove_stub test above filed one for this slug
            item = {"url": u, "rid": "321076", "headline": "Sankamap Discovers Gold"}
            full_env = {"event_id": event_id_for(u)}
            for outcome in ("refused", "stored"):
                con.execute("INSERT INTO events (event_id, ticker, slug, source_name, raw_headline, classifier_model) "
                            "VALUES (?,?,?,?,?,?)", (sid, "SCU.CN", "sankamap-discovers-gold", "newsfile",
                                                     "Sankamap Discovers Gold", STUB_MODEL))
                con.commit()

                def post(env, _o=outcome):
                    if _o == "stored":
                        con.execute("INSERT INTO events (event_id, ticker, slug, source_name) VALUES (?,?,?,?)",
                                    (env["event_id"], "SCU.CN", "sankamap-discovers-gold-2", "newsfile"))
                        return 200
                    return 500
                fake.post_to_ingest = post
                cc = _counts()
                take_over_from_page(item, full_env, True, cc)
                has_stub = con.execute("SELECT COUNT(*) FROM events WHERE event_id=?", (sid,)).fetchone()[0]
                has_full = con.execute("SELECT COUNT(*) FROM events WHERE event_id=?", (full_env["event_id"],)).fetchone()[0]
                if outcome == "refused":
                    ok("take-over refused: short version put back, readers still blocked",
                       (has_stub, has_full, con.execute("SELECT COUNT(*) FROM fx_runs WHERE event_id=?", (sid,)).fetchone()[0]),
                       (1, 0, 2))
                    con.execute("DELETE FROM events WHERE event_id=?", (sid,))
                    con.execute("DELETE FROM fx_runs WHERE event_id=?", (sid,))
                else:
                    ok("take-over stored: short version gone, full kept, address forwarded",
                       (has_stub, has_full, cc["taken_over"], con.execute(
                           "SELECT event_id FROM event_slug_aliases WHERE ticker='scu.cn' AND old_slug='sankamap-discovers-gold'"
                           " AND source='NFSTUB_V1' ORDER BY rowid DESC").fetchone()[0]),
                       (0, 1, 1, full_env["event_id"]))
        finally:
            g["_ro"], g["_rw"] = saved[0], saved[1]
            if saved[2] is None:
                sys.modules.pop("sync_newswire_ca", None)
            else:
                sys.modules["sync_newswire_ca"] = saved[2]
    print(f"self-test: {'all ok' if not bad else str(bad) + ' FAILED'}")
    return 1 if bad else 0


def main() -> int:
    a = sys.argv[1:]
    if a[:1] == ["--self-test"]:
        return _self_test()
    if a[:1] == ["--test-urls"]:
        return _test_urls(a[1:])
    apply = "--dry-run" not in a
    pages = "--no-pages" not in a
    stubs = True if "--stubs" in a else None     # V4: preview or force short versions regardless of the flag file
    if "--backstop" in a:
        lim = int(a[a.index("--limit") + 1]) if "--limit" in a else 0
        return backstop(apply, pages, lim, stubs=stubs)
    return run(apply, pages, stubs=stubs)


if __name__ == "__main__":
    sys.exit(main())
