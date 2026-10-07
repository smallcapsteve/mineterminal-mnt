#!/usr/bin/env python3
"""sync_newswire_ca.py - direct newswire.ca mining firehose.

Fetches the 3 mining-only category URLs every cycle, parses article
URLs, fetches each body, extracts ticker, and POSTs to the local
/ingest webhook (the same path the relay daemon uses). The portal's
/ingest handler does quality gating, fuzzy dedupe, categorization,
auto-onboard and upsert to events.db.

Run: python3 sync_newswire_ca.py [days]   # days arg currently unused
Source-name: newswire_ca   (so events.source_name='newswire_ca')
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

CATEGORIES = [
    "https://www.newswire.ca/news-releases/energy-latest-news/mining-list/",
    "https://www.newswire.ca/news-releases/energy-latest-news/mining-metals-list/",
    "https://www.newswire.ca/news-releases/heavy-industry-manufacturing-latest-news/precious-metals-list/",
]

USER_AGENT = "Mozilla/5.0 (compatible; MNT-newswire-ca/1.0; +https://miningnewsterminal.com)"
INGEST_URL = os.environ.get("PORTAL_INGEST_URL", "http://127.0.0.1:8001/ingest").rstrip("/")
HMAC_SECRET = os.environ.get("MNT_HMAC_SECRET", "")
SEEN_FILE = Path("/opt/mnt/app/data/seen_newswire_ca.json")
TIMEOUT = 25

# Ticker regexes — try strict-first, then loose. Prefix order = exchange resolution priority.
# Captures things like: (TSXV: ABC), (TSX: XYZ), (CSE: PQR), (TSX-V: ABC).
TICKER_RE = re.compile(
    r"\(\s*(TSXV?|TSX-?V|CSE|CNQ|NEO|TSXM|TSX|OTC[A-Z]*|NYSE[A-Z]*|NASDAQ)\s*[:\-]?\s*([A-Z][A-Z0-9.\-]{0,5})\s*\)",
    re.IGNORECASE,
)

EXCHANGE_TO_SUFFIX = {
    "TSXV": ".V",
    "TSX-V": ".V",
    "TSX": ".TO",
    "CSE": ".CN",
    "CNQ": ".CN",
    "NEO": ".NE",
    "TSXM": ".TO",
}

NON_MINING_HINTS = re.compile(
    r"\b(cannabis|marijuana|psychedelic|mushroom|crypto|bitcoin|ethereum|sport|hockey|food|cosmetic|beverage)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------- NWFIX_V1 (2026-09-28)
# Justin, 2026-09-28: fix the newswire.ca collector so the coverage list decides what is visible. Until now every
# release it collected was parked for review (hard-coded), nobody reviewed them, and 635 releases from companies on
# the list were never shown. Now: publish, unless MNT already shows the same release from another wire (then it is
# stored as duplicate_of_wire); the portal's universe gate still parks companies that are not on the list.
import difflib as _nw_difflib
import sqlite3 as _nw_sqlite3
from datetime import timedelta as _nw_td
try:
    from zoneinfo import ZoneInfo as _NwZone
    _ET = _NwZone("America/Toronto")
except Exception:  # noqa: BLE001
    _ET = timezone(_nw_td(hours=-4))

PORTAL_DB = os.environ.get("PORTAL_DB", "/opt/mnt/app/portal/portal.db")
TWIN_DAYS = 3          # same company, within 3 days of the release date
SWEEP_DAYS = 3         # re-check releases published by this collector in the last 3 days
SWEEP_MAX = 25         # refuse to hide more than this many in one run (something would be wrong)
_MON = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
_DATE_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),\s+(20\d{2})"
                      r"(?:,\s+(\d{1,2}):(\d{2})\s*ET)?")
_STOPW = set("the a an of and to in for on at with by from its is as inc corp ltd limited corporation".split())
_ro_con = None


def _now_et() -> str:
    return datetime.now(_ET).strftime("%Y-%m-%dT%H:%M:%S")


def _now_utc() -> str:
    """MNT_FIX_20261003: stored when a page gives no time at all - now, in UTC with a 'Z'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_from_et_text(s: str):
    """MNT_FIX_20261003: _date_text's Eastern wall clock -> UTC with a 'Z'; a date with no time -> MNT's date-only form
    'YYYY-MM-DDT12:00:00+00:00'; a date more than a day ahead (one the release merely mentions) -> None."""
    m = _DATE_RE.search(s or "")
    v = _date_text(s)
    if not v or not m:
        return None
    d = datetime.fromisoformat(v)
    if d.date() > (datetime.now(timezone.utc) + _nw_td(days=1)).date():
        return None
    if m.group(4) is None:
        return d.strftime("%Y-%m-%dT12:00:00+00:00")
    return d.replace(tzinfo=_ET).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date_text(s: str):
    """'Sep 23, 2026, 17:00 ET' / 'Sept. 23, 2026' / 'May 1, 2026' -> ET wall clock ISO, or None."""
    m = _DATE_RE.search(s or "")
    if not m:
        return None
    try:
        d = datetime(int(m.group(3)), _MON[m.group(1).lower()[:3]], int(m.group(2)),
                     int(m.group(4) or 0), int(m.group(5) or 0))
    except ValueError:
        return None
    return d.strftime("%Y-%m-%dT%H:%M:%S")


def release_time(soup, body_text: str):
    """When the release went out. MNT_FIX_20261003: in UTC with a 'Z' ('YYYY-MM-DDTHH:MM:SSZ'), the time every other
    wire's rows mean. Until 2026-10-03 this returned Eastern wall clock, which MNT and MTP both read as UTC, so
    newswire.ca releases showed four hours early (CNW and GlobeNewswire rows are UTC, not Eastern). A date with no
    time is 'YYYY-MM-DDT12:00:00+00:00'. The page's own <meta name="date"> first, then its 'Sep 23, 2026, 17:00 ET'
    line, then the dateline."""
    m = soup.select_one('meta[name="date"]')
    v = (m.get("content") or "").strip() if m else ""
    if v:
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            d = d if d.tzinfo else d.replace(tzinfo=_ET)
            return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    for el in soup.select("p.mb-no"):
        s = _utc_from_et_text(el.get_text(" ", strip=True))
        if s:
            return s
    return _utc_from_et_text((body_text or "")[:600])


def _nw_norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (s or "").lower())).strip()


def _nw_toks(s: str, n: int = 150) -> set:
    return set([w for w in _nw_norm(s).split() if w not in _STOPW and len(w) > 2][:n])


def same_release(h1: str, t1: set, h2: str, t2: set) -> bool:
    """The rule the 2026-09-28 check used: headline similarity >= 0.85, or opening-text overlap >= 0.5."""
    hs = _nw_difflib.SequenceMatcher(None, _nw_norm(h1)[:200], _nw_norm(h2)[:200]).ratio() if h2 else 0.0
    js = len(t1 & t2) / len(t1 | t2) if t1 and t2 else 0.0
    return hs >= 0.85 or js >= 0.5


def _ro():
    global _ro_con
    if _ro_con is None:
        _ro_con = _nw_sqlite3.connect(f"file:{PORTAL_DB}?mode=ro", uri=True, timeout=60)
    return _ro_con


def visible_twin(con, ticker, headline, body, published, exclude_id=None):
    """event_id of a VISIBLE release on MNT from another source that is this same release, else None."""
    b = (ticker or "").split(".")[0].upper().strip()
    try:
        d = datetime.fromisoformat((published or "")[:10])
    except ValueError:
        return None
    if not b:
        return None
    lo = (d - _nw_td(days=TWIN_DAYS)).strftime("%Y-%m-%d")
    hi = (d + _nw_td(days=TWIN_DAYS + 1)).strftime("%Y-%m-%d")
    t1 = _nw_toks((body or "")[:2500])
    for eid, h2, b2 in con.execute(
            "SELECT event_id, raw_headline, substr(COALESCE(raw_body,''),1,2500) FROM events "
            "WHERE review_status = 'auto_approved' AND (ticker = ? OR ticker LIKE ?) "
            "AND COALESCE(source_name,'') <> 'newswire_ca' AND published_at >= ? AND published_at < ?",
            (b, b + ".%", lo, hi)):
        if eid != exclude_id and same_release(headline, t1, h2 or "", _nw_toks(b2)):
            return eid
    return None


def sweep_duplicates(apply: bool = True, days: int = SWEEP_DAYS) -> int:
    """Hide this collector's visible releases that another wire has since also delivered (the other copy wins)."""
    since = (datetime.now(timezone.utc) - _nw_td(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    ro = _nw_sqlite3.connect(f"file:{PORTAL_DB}?mode=ro", uri=True, timeout=60)
    rows = ro.execute("SELECT event_id, ticker, raw_headline, substr(COALESCE(raw_body,''),1,2500), "
                      "COALESCE(published_at, classified_at, ingested_at) FROM events "
                      "WHERE source_name = 'newswire_ca' AND review_status = 'auto_approved' AND ingested_at >= ?",
                      (since,)).fetchall()
    hits = []
    for eid, tk, h, b, pub in rows:
        tw = visible_twin(ro, tk, h, b, pub, exclude_id=eid)
        if tw:
            hits.append((eid, tk, h, tw))
    ro.close()
    for eid, tk, h, tw in hits:
        print(f"  {'HIDE' if apply else 'WOULD HIDE'} {tk:10s} {eid[:12]} (also on MNT as {tw[:12]}) {(h or '')[:60]}",
              flush=True)
    print(f"[sync_newswire_ca] sweep: {len(rows)} visible newswire.ca releases from the last {days} days, "
          f"{len(hits)} also on MNT from another wire", flush=True)
    if not apply or not hits:
        return len(hits) if not apply else 0
    if len(hits) > SWEEP_MAX:
        print(f"[sync_newswire_ca] sweep: REFUSED - {len(hits)} is more than {SWEEP_MAX}; nothing hidden", flush=True)
        return -1
    con = _nw_sqlite3.connect(PORTAL_DB, timeout=60)
    with con:
        n = sum(con.execute("UPDATE events SET review_status = 'duplicate_of_wire' "
                            "WHERE event_id = ? AND review_status = 'auto_approved'", (e[0],)).rowcount for e in hits)
    con.close()
    return n


def _test_urls(urls) -> int:
    for u in urls:
        det = parse_article(u)
        if not det:
            print(f"TEST {u[-70:]} | fetch/parse failed", flush=True)
            continue
        pub = det["published_at"] or _now_utc()
        tw = visible_twin(_ro(), det["ticker"], det["headline"], det["body_text"], pub) if det.get("ticker") else None
        st = "no ticker (skipped)" if not det.get("ticker") else ("duplicate_of_wire" if tw else "auto_approved")
        print(f"TEST {u[-60:]} | {det.get('ticker')} | {det['published_at']} | {st} | twin {tw or '-'} | "
              f"{det['headline'][:60]}", flush=True)
    return 0


def _self_test() -> int:
    from bs4 import BeautifulSoup as _BS
    cases = [
        ('<html><head><meta name="date" content="2026-09-23T17:00:00-04:00"/></head><body></body></html>', "",
         "2026-09-23T21:00:00Z"),
        ('<html><head><meta name="date" content="2026-01-15T08:00:00-05:00"/></head></html>', "", "2026-01-15T13:00:00Z"),
        ('<html><head><meta name="date" content="2026-06-02T12:30:00Z"/></head></html>', "", "2026-06-02T12:30:00Z"),
        ('<html><body><p class="mb-no">Sep 23, 2026, 17:00 ET</p></body></html>', "", "2026-09-23T21:00:00Z"),
        ('<html><body><p class="mb-no">Jan 15, 2026, 08:00 ET</p></body></html>', "", "2026-01-15T13:00:00Z"),
        ("<html></html>", "VANCOUVER, BC, Sept. 23, 2026 /CNW/ - Acme", "2026-09-23T12:00:00+00:00"),
        ("<html></html>", "TORONTO, May 1, 2026 /CNW/ - Acme Gold", "2026-05-01T12:00:00+00:00"),
        ("<html></html>", "Acme sets a deadline of Jan 1, 2099 for its project", None),   # MNT_FIX_20261003
        ("<html></html>", "No date here at all.", None),
    ]
    bad = 0
    for html, body, want in cases:
        got = release_time(_BS(html, "html5lib"), body)
        if got != want:
            bad += 1
            print(f"SELF-TEST FAIL date: want {want} got {got} for {html[:50]!r} {body[:30]!r}")
    pairs = [("Acme Gold Intersects 12 m of 5 g/t Au at Ridge", "Acme Gold Intersects 12 m of 5 g/t Au at Ridge - Newswire", True),
             ("Acme Gold Announces Private Placement", "Acme Gold Reports Q2 Results", False)]
    for h1, h2, want in pairs:
        if same_release(h1, set(), h2, set()) != want:
            bad += 1
            print(f"SELF-TEST FAIL match: {h1!r} vs {h2!r} want {want}")
    print(f"self-test: {len(cases) + len(pairs) - bad}/{len(cases) + len(pairs)} ok")
    return 1 if bad else 0
# ---------------------------------------------------------------- end NWFIX_V1


def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def list_articles(category_url: str) -> List[Dict]:
    """Return [{url, headline, time_label}] from a newswire.ca category list page."""
    out: List[Dict] = []
    try:
        html = fetch(category_url)
    except Exception as e:
        print(f"[newswire_ca] LIST FAIL {category_url}: {e}", flush=True)
        return out
    soup = BeautifulSoup(html, "html5lib")
    for a in soup.select("a.newsreleaseconsolidatelink"):
        href = a.get("href") or ""
        if not href or not href.endswith(".html"):
            continue
        if href.startswith("/"):
            href = "https://www.newswire.ca" + href
        text = " ".join((a.get_text(" ", strip=True) or "").split())
        # Strip leading "10:09 ET" timestamp if present
        text = re.sub(r"^(\d{1,2}:\d{2}\s*ET)\s*", "", text)
        out.append({"url": href, "headline": text})
    return out


def parse_article(url: str) -> Optional[Dict]:
    """Fetch a release page and extract headline, body, ticker, exchange, published_at."""
    try:
        html = fetch(url)
    except Exception as e:
        print(f"  X fetch err {url}: {e}", flush=True)
        return None
    soup = BeautifulSoup(html, "html5lib")

    # Headline
    h1 = soup.select_one("h1") or soup.select_one(".release-header h1")
    headline = h1.get_text(" ", strip=True) if h1 else ""

    # Body — newswire.ca uses .release-body or .col-sm-12 inside .news-release-content
    body_el = (
        soup.select_one(".release-body")
        or soup.select_one("[class*=release-body]")
        or soup.select_one("article")
        or soup.select_one(".news-release-content")
    )
    body_text = body_el.get_text(" ", strip=True) if body_el else ""
    body_html = str(body_el) if body_el else ""

    # Published time. NWFIX_V1 (2026-09-28): newswire.ca states it in <meta name="date">, which the old
    # selectors never read, so every date came from the body text - 344 releases got none, some got a date the
    # text merely mentions. release_time() reads the page's own date first; the old dateline rule below stays
    # as the last resort.
    published_at = release_time(soup, body_text)
    if not published_at:
        # Pattern: "/CNW/ - VANCOUVER, BC, May 1, 2026 /CNW/" — best-effort
        m = re.search(r"([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})", body_text[:600])
        if m:
            try:
                _d = datetime.strptime(m.group(1), "%B %d, %Y")
                # MNT_FIX_20261003: a date only (MNT's date-only form), never one ahead that the text merely mentions
                published_at = (_d.strftime("%Y-%m-%dT12:00:00+00:00")
                                if _d.date() <= (datetime.now(timezone.utc) + _nw_td(days=1)).date() else None)
            except Exception:
                published_at = None

    # Ticker — search the FIRST paragraph which usually has the company-name + ticker
    ticker = None
    exchange = None
    head_blob = body_text[:1500]
    m = TICKER_RE.search(head_blob)
    if m:
        ex_raw = m.group(1).upper().replace("-", "")
        if ex_raw == "TSXV":
            ex = "TSXV"
        elif ex_raw == "TSXV":
            ex = "TSXV"
        elif ex_raw.startswith("TSX") and "V" in ex_raw:
            ex = "TSXV"
        elif ex_raw == "TSX":
            ex = "TSX"
        elif ex_raw in ("CSE", "CNQ"):
            ex = "CSE"
        elif ex_raw == "NEO":
            ex = "NEO"
        else:
            ex = ex_raw
        sym = m.group(2).upper()
        suffix = EXCHANGE_TO_SUFFIX.get(ex, "")
        ticker = sym + suffix if suffix and not sym.endswith(suffix) else sym
        exchange = ex

    return {
        "headline": headline,
        "body_text": body_text,
        "body_html": body_html,
        "published_at": published_at,
        "ticker": ticker,
        "exchange": exchange,
    }


def event_id_for(url: str) -> str:
    return hashlib.sha256(("newswire_ca:" + url).encode("utf-8")).hexdigest()


def post_to_ingest(envelope: Dict) -> int:
    body = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if HMAC_SECRET:
        ts = str(int(time.time()))
        sig = hmac.new(HMAC_SECRET.encode('utf-8'), (ts + ".").encode("utf-8") + body, hashlib.sha256).hexdigest()
        headers["X-MNT-Timestamp"] = ts
        headers["X-MNT-Signature"] = "sha256=" + sig
    try:
        url = INGEST_URL + '/' + envelope.get('event_type', 'news_release'); r = requests.post(url, data=body, headers=headers, timeout=20)
        return r.status_code
    except Exception as e:
        print(f"  X post err: {e}", flush=True)
        return 0


def load_seen() -> set:
    if not SEEN_FILE.exists():
        return set()
    try:
        return set(json.loads(SEEN_FILE.read_text()))
    except Exception:
        return set()


def save_seen(seen: set) -> None:
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SEEN_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(sorted(seen)[-5000:]))  # cap at 5k newest
    os.replace(tmp, SEEN_FILE)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        return _self_test()
    if len(sys.argv) > 1 and sys.argv[1] == "--test-urls":
        return _test_urls(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "--sweep-dry-run":
        sweep_duplicates(apply=False, days=int(sys.argv[2]) if len(sys.argv) > 2 else SWEEP_DAYS)
        return 0
    seen = load_seen()
    discovered = 0
    skipped_no_ticker = 0
    skipped_non_mining = 0
    ingested_ok = 0
    ingested_err = 0
    n_twin = 0

    for cat in CATEGORIES:
        articles = list_articles(cat)
        print(f"[sync_newswire_ca] {cat} -> {len(articles)} articles", flush=True)
        for art in articles:
            url = art["url"]
            if url in seen:
                continue
            discovered += 1
            seen.add(url)  # mark seen even on failure to avoid retry loops
            time.sleep(0.4)  # be polite

            detail = parse_article(url)
            if not detail or not detail.get("headline"):
                skipped_no_ticker += 1
                continue

            # Drop obvious non-mining noise that occasionally lands in mining categories
            if NON_MINING_HINTS.search(detail["headline"]):
                skipped_non_mining += 1
                continue

            if not detail.get("ticker"):
                # Newswire.ca releases without an obvious ticker tag are usually
                # commentary, IR firms, or service announcements. Skip rather
                # than flood the events table with unattributable rows.
                skipped_no_ticker += 1
                continue

            # NWFIX_V1: publish, unless MNT already shows this release from another wire. The portal's universe
            # gate still parks companies that are not on the coverage list. If the check itself fails, park the
            # release for review as before rather than risk a duplicate.
            status = "auto_approved"
            try:
                twin = visible_twin(_ro(), detail["ticker"], detail["headline"], detail["body_text"],
                                    detail["published_at"] or _now_utc())
            except Exception as e:  # noqa: BLE001
                print(f"  ! twin check failed ({e}); parked for review", flush=True)
                twin, status = None, "pending_review"
            if twin:
                status = "duplicate_of_wire"
                n_twin += 1
                print(f"  = {detail['ticker']:10s} already on MNT as {twin[:12]}: {detail['headline'][:60]}", flush=True)

            envelope = {
                "event_id": event_id_for(url),
                "event_type": "news_release",
                "ticker": detail["ticker"],
                "source_name": "newswire_ca",
                "source_url": url,
                "raw_headline": detail["headline"][:500],
                "raw_excerpt": detail["body_text"][:1500],
                "raw_body": detail["body_text"][:50000],
                "raw_html": detail["body_html"][:200000],
                "published_at": detail["published_at"] or _now_utc(),
                "categories": ["news"],
                "_exchange": detail.get("exchange"),
                "_cfg_website": cat,
                "_source_name": "newswire_ca",
                "review_status": status,
                "classifier_model": "newswire_ca_v1",
                "classifier_confidence": 0.85,
            }
            code = post_to_ingest(envelope)
            if code in (200, 201, 202):
                ingested_ok += 1
                tk = detail["ticker"]
                print(f"  + {tk:10s} {detail['headline'][:80]}", flush=True)
            else:
                ingested_err += 1
                print(f"  X HTTP {code} {detail['headline'][:80]}", flush=True)

    try:
        n_swept = sweep_duplicates(apply=True)
    except Exception as e:  # noqa: BLE001
        print(f"[sync_newswire_ca] sweep failed: {e}", flush=True)
        n_swept = -1
    print(f"[sync_newswire_ca] NWFIX already_on_mnt={n_twin} hidden_later={n_swept}", flush=True)
    save_seen(seen)
    print(
        f"[sync_newswire_ca] DONE  discovered={discovered}  ingested={ingested_ok}  "
        f"err={ingested_err}  no_ticker={skipped_no_ticker}  non_mining={skipped_non_mining}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
