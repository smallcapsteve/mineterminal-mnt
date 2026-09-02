"""
GlobeNewswire source -- Phase 0.

Fetches recent press releases for configured tickers by scraping
GlobeNewswire's ticker-filtered news pages. Returns normalized raw
press-release dicts ready for the classifier.

Output shape:
  {
    "source_name":  "globenewswire",
    "source_url":   "https://www.globenewswire.com/news-release/2026/...",
    "published_at": "2026-04-15T13:00:00Z",
    "ticker":       "CCI.CN",
    "raw_headline": "Canadian Copper Reports ...",
    "raw_excerpt":  "first ~1500 chars of press release body",
    "raw_body":     "full body text"
  }
"""
from __future__ import annotations
import datetime as dt
import hashlib
import re
from typing import Iterator

import httpx
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (MiningNewsTracker/0.1) -- contact via portal"
BASE = "https://www.globenewswire.com"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _parse_published(s: str) -> str | None:
    """GNW typically shows 'April 15, 2026 06:00 ET' style."""
    if not s: return None
    try:
        # Strip trailing tz label, parse what we can
        cleaned = re.sub(r"\s+(ET|PT|CT|EDT|EST|PDT|PST|GMT|UTC)\s*$", "", s.strip())
        parsed = dt.datetime.strptime(cleaned, "%B %d, %Y %H:%M")
        # Treat as ET -> convert to UTC (approximation; refine in Phase 1)
        return parsed.replace(tzinfo=dt.timezone(dt.timedelta(hours=-4))).astimezone(dt.timezone.utc).isoformat()
    except Exception:
        return None


def _fetch(url: str) -> str:
    with httpx.Client(headers={"User-Agent": UA}, timeout=20, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


def list_recent_for_ticker(ticker: str, limit: int = 20) -> Iterator[dict]:
    """
    ticker: e.g. 'CCI.CN' or 'CCI'. GNW search URL uses stock-symbol filter.
    Yields candidate PR summary dicts; caller follows through to load body.
    """
    # Normalize: GNW uses bare symbol for many; fall back to full for Canadian listings
    q = ticker.split(".")[0]
    search_url = f"{BASE}/search/organization/{q}?pageSize={limit}"
    try:
        html = _fetch(search_url)
    except Exception as e:
        print(f"[globenewswire] search failed for {ticker}: {e}")
        return

    soup = BeautifulSoup(html, "lxml")
    for card in soup.select("div.mainLink, article, div[class*=article]")[:limit]:
        a = card.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if not href.startswith("http"):
            href = BASE + href
        if "/news-release/" not in href:
            continue
        headline = _clean(a.get_text())
        time_tag = card.find("time")
        pub = None
        if time_tag and time_tag.has_attr("datetime"):
            pub = time_tag["datetime"]
        else:
            pub_text = None
            date_span = card.find(class_=re.compile(r"(date|time|posted)", re.I))
            if date_span:
                pub_text = _clean(date_span.get_text())
                pub = _parse_published(pub_text)
        yield {
            "source_url": href,
            "source_name": "globenewswire",
            "published_at": pub,
            "ticker": ticker,
            "raw_headline": headline,
        }


def fetch_body(summary: dict) -> dict:
    """Given a summary dict from list_recent_for_ticker, fetch the full body."""
    try:
        html = _fetch(summary["source_url"])
    except Exception as e:
        summary["raw_body"]    = ""
        summary["raw_excerpt"] = ""
        summary["fetch_error"] = str(e)
        return summary

    soup = BeautifulSoup(html, "lxml")
    body_el = (
        soup.select_one("article .main-body-container") or
        soup.select_one("article") or
        soup.select_one("main") or
        soup
    )
    text = _clean(body_el.get_text(" "))
    summary["raw_body"]    = text
    summary["raw_excerpt"] = text[:1500]
    if not summary.get("published_at"):
        tt = soup.find("time")
        if tt and tt.has_attr("datetime"):
            summary["published_at"] = tt["datetime"]
    return summary


def event_id_for(source_url: str, published_at: str | None) -> str:
    h = hashlib.sha256()
    h.update(source_url.encode("utf-8"))
    h.update(b"|")
    h.update((published_at or "").encode("utf-8"))
    return h.hexdigest()


# Uniform source-module interface -- dispatches to list_recent_for_ticker using
# the ticker value in the per-ticker config dict.
def list_recent(cfg: dict, limit: int = 25):
    yield from list_recent_for_ticker(cfg.get("ticker", ""), limit=limit)
