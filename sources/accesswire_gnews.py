"""accesswire_gnews — Accesswire (accessnewswire.com) discovery via Google News RSS.

Cloudflare blocks direct scraping of accessnewswire.com, so we use GNews to
discover mining press releases from that origin, then store link-only entries
that point at the real article.

Mining classifier: strict — requires either (a) ticker resolution against
known tickers.json by fuzzy company-name match, or (b) clear mining keywords
in the headline.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import html as _html
import json
import re
import urllib.parse
from typing import Iterator
from xml.etree import ElementTree as ET

import httpx

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15"
)

# Strong mining keywords for headline-only classification
_HEADLINE_MINING = re.compile(
    r"\b("
    r"gold|silver|copper|zinc|nickel|lithium|cobalt|uranium|graphite|manganese|"
    r"tungsten|molybdenum|vanadium|platinum|palladium|rare\s+earth|antimony|"
    r"tin|lead|iron\s+ore|potash|phosphate|tellurium|tantalum|scandium|"
    r"niobium|germanium|gallium|"
    r"drilling|drill\s+program|drill\s+results|exploration|"
    r"mineralization|mineralized|mineral\s+resource|"
    r"deposit|orebody|ore\s+deposit|"
    r"\bmining\b|\bminer(?:s|als?)?\b|\bmined\b|\bmine\b|"
    r"\bmetals?\b|royalties|royalty|"
    r"43-101|feasibility\s+study|preliminary\s+economic\s+assessment|"
    r"resource\s+estimate|smelter|tailings|stockpile"
    r")\b",
    re.I,
)

_NEG_HEADLINE = re.compile(
    r"\b(?:pic-?time|photographer|wedding|software|fintech|crypto|biotech|"
    r"pharmaceutical|cannabis|psychedelic|saas|real\s+estate)\b",
    re.I,
)


def is_mining_headline(title: str) -> bool:
    if not title:
        return False
    if _NEG_HEADLINE.search(title):
        return False
    return bool(_HEADLINE_MINING.search(title))


def gnews_query_url(days: int = 14) -> str:
    q = (
        "site:accessnewswire.com (mining OR gold OR silver OR copper OR "
        "lithium OR nickel OR uranium OR cobalt OR rare earth OR exploration "
        "OR drilling OR mineralization OR deposit OR ounces OR tonnes)"
        f" when:{days}d"
    )
    return (
        "https://news.google.com/rss/search?"
        f"q={urllib.parse.quote(q)}"
        "&hl=en-CA&gl=CA&ceid=CA:en"
    )


def _parse_pubdate(s: str) -> str | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S"):
        try:
            d = dt.datetime.strptime(s, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return None


# Title cleanup: GNews appends " - ACCESS Newswire" / " - Source Name"
_TITLE_SUFFIX = re.compile(r"\s+-\s+(?:ACCESS\s+Newswire|Yahoo\s+Finance|GlobeNewswire)\s*$", re.I)


def _clean_title(t: str) -> str:
    return _TITLE_SUFFIX.sub("", _html.unescape(t).strip()).strip()


# Pull explicit OTC/NASDAQ/NYSE/CSE/TSXV tickers if present in title
_TITLE_TICKER = re.compile(
    r"\(\s*(?:CSE|TSX[\.\-]?V|TSX-?Venture|TSX|NYSE\s*American|NYSE|NASDAQ|OTCQB|OTCQX|OTC|OTCMKTS)\s*[:\-]\s*([A-Z][A-Z0-9.]{0,7})\s*\)",
    re.I,
)


def _extract_ticker_from_title(t: str) -> str | None:
    """Attempt to extract a Canadian (CSE/TSXV/TSX) ticker from the headline.
    Returns suffixed ticker like 'XYZ.V' or None."""
    if not t:
        return None
    # Look for any (EXCH: TICK) marker
    for m in _TITLE_TICKER.finditer(t):
        symbol = m.group(1).upper()
        # Detect exchange
        ctx = t[max(0, m.start() - 30):m.start()]
        if re.search(r"CSE", ctx, re.I):
            return f"{symbol}.CN"
        if re.search(r"TSX[\.\-]?V|TSX-?Venture", ctx, re.I):
            return f"{symbol}.V"
        if re.search(r"\bTSX\b", ctx, re.I):
            return f"{symbol}.TO"
        # OTC/NYSE/NASDAQ — we don't tag these (we only track Canadian listings)
        return None
    return None


# ----- company-name → ticker fuzzy match -----

def _norm_name(s: str) -> str:
    """Normalize a company name for matching."""
    s = (s or "").lower()
    # Strip common suffixes
    s = re.sub(r"\b(?:inc|corp|corporation|ltd|limited|co|company|plc|n\.?v\.?|s\.?a\.?)\b\.?", "", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _company_from_title(title: str) -> str:
    """Take the leading company-name portion of the title. Heuristic: stop at common verb phrases."""
    if not title:
        return ""
    # Action verbs that typically come after the company name
    stop = re.compile(
        r"\s+(?:announces?|reports?|provides?|enters?|signs?|completes?|"
        r"closes?|secures?|grants?|files?|releases?|engages?|appoints?|"
        r"updates?|kicks?\s+off|begins?|launches?|delivers?|achieves?|"
        r"intersects?|acquires?|expands?|raises?|presents?|discovers?|"
        r"identifies?|confirms?|enters?\s+into|to\s+acquire|to\s+launch|"
        r"to\s+begin|expects?|anticipates?|plans?|mobilizes?|kicks)\b",
        re.I,
    )
    m = stop.search(title)
    if m:
        return title[:m.start()].strip().rstrip(":,–—-")
    # Fallback: take first 60 chars
    return title[:60].strip()


def build_company_index(tickers: list[dict]) -> dict[str, str]:
    """Map normalized company name → ticker for fuzzy match."""
    idx = {}
    for r in tickers:
        if not isinstance(r, dict):
            continue
        ticker = r.get("ticker")
        name = r.get("name") or ""
        if not ticker or not name:
            continue
        n = _norm_name(name)
        if n:
            idx[n] = ticker
            # Also index by first 2 words and 3 words
            parts = n.split()
            if len(parts) >= 2:
                idx.setdefault(" ".join(parts[:2]), ticker)
            if len(parts) >= 3:
                idx.setdefault(" ".join(parts[:3]), ticker)
    return idx


def resolve_ticker(title: str, name_index: dict[str, str]) -> str | None:
    """Try title-marker first, then fuzzy company-name lookup."""
    # 1. Explicit ticker tag in title
    t = _extract_ticker_from_title(title)
    if t:
        return t
    # 2. Fuzzy: take leading company name and look up in index
    company = _norm_name(_company_from_title(title))
    if not company:
        return None
    # Exact match
    if company in name_index:
        return name_index[company]
    # Prefix match: try longest leading substring
    parts = company.split()
    for k in range(min(len(parts), 5), 1, -1):
        prefix = " ".join(parts[:k])
        if prefix in name_index:
            return name_index[prefix]
    return None


# ----- main fetch + parse -----

def _event_id(url: str, pub: str) -> str:
    h = hashlib.sha256()
    h.update((url or "").encode())
    h.update(b"|")
    h.update((pub or "").encode())
    return h.hexdigest()


def fetch_gnews_items(days: int = 14) -> list[dict]:
    url = gnews_query_url(days)
    with httpx.Client(headers={"User-Agent": UA}, timeout=30) as c:
        r = c.get(url)
        r.raise_for_status()
        xml_text = r.text
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []
    out = []
    for it in channel.findall("item"):
        title = (it.findtext("title") or "").strip()
        link  = (it.findtext("link") or "").strip()
        pub   = (it.findtext("pubDate") or "").strip()
        out.append({
            "title_raw": title,
            "title":     _clean_title(title),
            "gnews_url": link,
            "pub":       pub,
        })
    return out


def list_mining_events(name_index: dict[str, str], days: int = 14) -> Iterator[dict]:
    """Discover Accesswire mining items via GNews and yield event dicts.

    Each event has the headline, date, and a placeholder body that points
    the reader to the original Accesswire URL once we resolve it.
    """
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError:
        gnewsdecoder = None

    items = fetch_gnews_items(days)
    for raw in items:
        title = raw["title"]
        if not is_mining_headline(title):
            continue
        ticker = resolve_ticker(title, name_index)
        if not ticker:
            # Strict mode: skip if we can't identify a known Canadian ticker
            continue
        pub_iso = _parse_pubdate(raw["pub"]) or ""
        # Decode GNews redirect URL
        real_url = raw["gnews_url"]
        if gnewsdecoder:
            try:
                d = gnewsdecoder(raw["gnews_url"])
                if d.get("status") and d.get("decoded_url"):
                    real_url = d["decoded_url"]
            except Exception:
                pass
        # Best-effort body fetch (likely 403 due to Cloudflare)
        body_text = (
            f"This release is published on Accesswire. "
            f"Click 'Original source ↗' to read the full release."
        )
        body_html = f"<p>{body_text}</p>"
        try:
            with httpx.Client(headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            }, timeout=10, follow_redirects=True) as c:
                r = c.get(real_url)
                if r.status_code == 200 and "Just a moment" not in r.text[:1000]:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(r.text, "html.parser")
                    for tag in soup(["script","style","nav","header","footer","aside","form","noscript","iframe"]):
                        tag.decompose()
                    for sel in ["article", "div.article-body", "div.entry-content", "main", ".release-body"]:
                        for el in soup.select(sel):
                            txt = el.get_text("\n\n", strip=True)
                            if len(txt) > 400:
                                body_text = txt
                                body_html = str(el)
                                break
                        else:
                            continue
                        break
        except Exception:
            pass  # keep placeholder
        yield {
            "event_id":     _event_id(real_url, pub_iso),
            "ticker":       ticker,
            "event_type":   "news_release",
            "source_name":  "accessnewswire",
            "source_url":   real_url,
            "raw_headline": title,
            "raw_body":     body_text,
            "raw_html":     body_html,
            "published_at": pub_iso,
            "review_status":"auto_approved",
        }
