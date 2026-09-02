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

    # Published time
    published_at = None
    time_el = soup.select_one("time[datetime], [datetime]")
    if time_el:
        published_at = time_el.get("datetime") or None
    if not published_at:
        # Pattern: "/CNW/ - VANCOUVER, BC, May 1, 2026 /CNW/" — best-effort
        m = re.search(r"([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})", body_text[:600])
        if m:
            try:
                published_at = datetime.strptime(m.group(1), "%B %d, %Y").replace(tzinfo=timezone.utc).isoformat()
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
    seen = load_seen()
    discovered = 0
    skipped_no_ticker = 0
    skipped_non_mining = 0
    ingested_ok = 0
    ingested_err = 0

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
                "published_at": detail["published_at"],
                "categories": ["news"],
                "_exchange": detail.get("exchange"),
                "_cfg_website": cat,
                "_source_name": "newswire_ca",
                "review_status": "pending_review",
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

    save_seen(seen)
    print(
        f"[sync_newswire_ca] DONE  discovered={discovered}  ingested={ingested_ok}  "
        f"err={ingested_err}  no_ticker={skipped_no_ticker}  non_mining={skipped_non_mining}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
