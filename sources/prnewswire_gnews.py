"""prnewswire_gnews — PR Newswire (prnewswire.com) mining discovery via Google News RSS.

Same proven pattern as the other firehose adapters. PR Newswire carries
some North American mining releases. Body selector confirmed via probe:
section.release-body.

source_name="prnewswire" — new source label (no per-company adapter exists yet).
"""
from __future__ import annotations
import datetime as dt
import hashlib
import html as _html
import re
import urllib.parse
from typing import Iterator
from xml.etree import ElementTree as ET

import httpx
try:
    import wireticker as _WT                           # WIRETICK_V1
except Exception:
    _WT = None

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15"
)


_HEADLINE_MINING = re.compile(
    r"\b(?:gold|silver|copper|zinc|nickel|lithium|cobalt|uranium|graphite|"
    r"manganese|tungsten|molybdenum|vanadium|platinum|palladium|antimony|"
    r"rare\s+earth|tin|lead|iron\s+ore|potash|phosphate|tellurium|niobium|"
    r"drilling|drill\s+program|drill\s+results|exploration|"
    r"mineralization|mineralized|mineral\s+resource|"
    r"\bmining\b|\bminer(?:s|als?)?\b|\bmined\b|\bmine\b|"
    r"\bmetals?\b|royalt(?:y|ies)|"
    r"43-101|feasibility\s+study|preliminary\s+economic\s+assessment|"
    r"resource\s+estimate)\b",
    re.I,
)

_NEG_HEADLINE = re.compile(
    r"\b(?:shareholder\s+alert|class\s+action|securities\s+class|"
    r"investor\s+alert|investigation\s+of|"
    r"biotech|pharmaceutical|psychedelic|cannabis|"
    r"saas|software-as-a-service|fintech|crypto|blockchain|"
    r"holdings\s+inc[\s.]|driven\s+brands|monday\.com|camping\s+world)\b",
    re.I,
)


def is_mining_headline(title: str) -> bool:
    if not title:
        return False
    if _NEG_HEADLINE.search(title):
        return False
    return bool(_HEADLINE_MINING.search(title))


_TICKER_RES = [
    ("CN",  re.compile(r"\(\s*CSE\s*[:\-]\s*([A-Z][A-Z0-9.]{0,7})\s*\)", re.I)),
    ("V",   re.compile(r"\(\s*(?:TSX[\.\-]?V|TSX\s*Venture|TSX-Venture)\s*[:\-]\s*([A-Z][A-Z0-9.]{0,7})\s*\)", re.I)),
    ("TO",  re.compile(r"\(\s*TSX\s*[:\-]\s*([A-Z][A-Z0-9.]{0,7})\s*\)", re.I)),
]


def extract_ticker(text: str) -> tuple[str | None, str | None]:
    for suffix, rx in _TICKER_RES:
        m = rx.search(text or "")
        if m:
            t = m.group(1).upper()
            ex = {"CN": "CSE", "V": "TSXV", "TO": "TSX"}[suffix]
            return f"{t}.{suffix}", ex
    try:                                                # WIRETICK_V1: dual-listed datelines
        return _WT.extract_ticker_relaxed(text) if _WT else (None, None)
    except Exception:
        return None, None


def gnews_query_url(days: int = 7) -> str:
    q = (
        "site:prnewswire.com (mining OR gold OR silver OR copper OR "
        "lithium OR nickel OR uranium OR cobalt OR exploration OR drilling OR "
        "mineralization OR \"resource estimate\" OR \"43-101\")"
        f" when:{days}d"
    )
    return (
        "https://news.google.com/rss/search?"
        f"q={urllib.parse.quote(q)}&hl=en-CA&gl=CA&ceid=CA:en"
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


_TITLE_SUFFIX = re.compile(r"\s+-\s+(?:PR\s+Newswire|Cision\s+(?:Canada|US|UK))\s*$", re.I)


def _clean_title(t: str) -> str:
    return _TITLE_SUFFIX.sub("", _html.unescape(t).strip()).strip()


def fetch_gnews_items(days: int = 7) -> list[dict]:
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
        out.append({
            "title":     _clean_title(it.findtext("title") or ""),
            "gnews_url": (it.findtext("link") or "").strip(),
            "pub":       (it.findtext("pubDate") or "").strip(),
        })
    return out


def _extract_body_html(real_url: str, client: httpx.Client) -> tuple[str, str]:
    """Body selector confirmed via probe: section.release-body."""
    r = client.get(real_url, follow_redirects=True, timeout=20)
    if r.status_code != 200:
        return "", ""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html5lib")   # INGEST_FIX3_V1 (2026-10-12): html5lib, as sync_newswire_ca.py. The page markup is broken around the image
    # gallery; html.parser and lxml close section.release-body there and kept ~1,000 characters of the release
    # (dateline, first paragraph, figure captions). html5lib reads it the way a browser does: the whole release.
    for tag in soup(["script", "style", "nav", "header", "footer", "aside",
                     "form", "noscript", "iframe"]):
        tag.decompose()
    for sel in [
        "section.release-body",
        "div.release-body",
        "div.release-body-text",
        "section[data-module='release-body']",
        "article",
        "main",
    ]:
        for el in soup.select(sel):
            txt = el.get_text("\n\n", strip=True)
            if len(txt) > 400:
                return txt, str(el)
    return "", ""


def _event_id(url: str, pub: str) -> str:
    h = hashlib.sha256()
    h.update((url or "").encode())
    h.update(b"|")
    h.update((pub or "").encode())
    return h.hexdigest()


# AUDIT1110_PRN_INTAKE (2026-11-13): the search also returns listing pages (category pages, company newsrooms) and
# sponsored market articles; both were being stored as company releases. Only release pages are read, and a text that
# opens as a sponsored article is skipped. Checked against the 173 stored rows (49 listings, 15 sponsored, 108 releases).
_PRN_RELEASE_URL = re.compile(r"^https?://(?:www\.)?prnewswire\.com/(?:[a-z]{2,5}/)?news-releases/[^/?#]+-\d{6,}\.html(?:[?#].*)?$", re.I)
_PRN_SPONSORED = re.compile(r"News Commentary|Market News Updates|Issued on behalf of", re.I)


def list_mining_events(days: int = 7) -> Iterator[dict]:
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError:
        gnewsdecoder = None

    items = fetch_gnews_items(days)
    with httpx.Client(headers={"User-Agent": UA}, timeout=25) as client:
        for raw in items:
            title = raw["title"]
            _wt_bares = set()                           # WIRETICK_V1
            if not is_mining_headline(title):
                try:
                    _wt_bares = _WT.names_company(title) if _WT else set()
                except Exception:
                    _wt_bares = set()
                if not _wt_bares:
                    continue
            real_url = raw["gnews_url"]
            if gnewsdecoder and "news.google.com" in real_url:
                try:
                    d = gnewsdecoder(raw["gnews_url"])
                    if d.get("status") and d.get("decoded_url"):
                        real_url = d["decoded_url"]
                except Exception:
                    pass
            if not _PRN_RELEASE_URL.match(real_url or ""):
                continue                                # AUDIT1110_PRN_INTAKE: a listing page, not a release
            body_text, body_html = _extract_body_html(real_url, client)
            if not body_text:
                continue
            if _PRN_SPONSORED.search(title + " " + body_text[:900]):
                continue                                # AUDIT1110_PRN_INTAKE: sponsored article, not a company release
            ticker, exch = extract_ticker(body_text)
            if ticker and _wt_bares and not _WT.company_matches(ticker, _wt_bares):
                continue                                # WIRETICK_V1: headline names another company
            if not ticker:
                continue
            pub_iso = _parse_pubdate(raw["pub"]) or ""
            yield {
                "event_id":     _event_id(real_url, pub_iso),
                "ticker":       ticker,
                "event_type":   "news_release",
                "source_name":  "prnewswire",
                "source_url":   real_url,
                "raw_headline": title,
                "raw_body":     body_text,
                "raw_html":     body_html,
                "published_at": pub_iso,
                "review_status":"auto_approved",
                "_exchange":    exch,
            }


def extract_company_name(headline: str, body: str) -> str | None:
    text = body or ""
    m = re.search(
        r"([A-Z][A-Za-z0-9 .,&'\-]{4,80}?(?:\s+(?:Inc|Corp|Ltd|Limited|Co|Resources|Mining|Minerals|Metals|Gold|Silver|Lithium))\.?)\s*"
        r"\(\s*(?:CSE|TSX[\.\-]?V|TSX-?Venture|TSX)\s*:",
        text[:2000],
    )
    if m:
        return m.group(1).strip().rstrip(".,–—-")
    return None
