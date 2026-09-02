"""cnw_gnews — Canada Newswire (newswire.ca) mining discovery via Google News RSS.

Same proven pattern as newsfile_gnews / globenewswire_gnews. CNW is the
Canadian wire (Cision-owned) at newswire.ca and is the highest-volume
source for CSE/TSXV mining releases.

source_name="cnw" — same as the per-company adapter at sources/cnw.py,
so the fuzzy_dupe_guard correctly merges across both paths.
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
    return None, None


def gnews_query_url(days: int = 7) -> str:
    q = (
        "site:newswire.ca (mining OR gold OR silver OR copper OR "
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


_TITLE_SUFFIX = re.compile(r"\s+-\s+(?:CNW|Canada\s+Newswire|PR\s+Newswire|Cision)\s*$", re.I)


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
    """Fetch a CNW release page and extract title + body HTML.

    Selectors mirror the proven per-company adapter (sources/cnw.py).
    """
    r = client.get(real_url, follow_redirects=True, timeout=20)
    if r.status_code != 200:
        return "", ""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside",
                     "form", "noscript", "iframe"]):
        tag.decompose()
    for sel in [
        "section.release-body",
        "div.release-body",
        "div#release-body",
        "article",
        "main article",
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


def list_mining_events(days: int = 7) -> Iterator[dict]:
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError:
        gnewsdecoder = None

    items = fetch_gnews_items(days)
    with httpx.Client(headers={"User-Agent": UA}, timeout=25) as client:
        for raw in items:
            title = raw["title"]
            if not is_mining_headline(title):
                continue
            real_url = raw["gnews_url"]
            if gnewsdecoder and "news.google.com" in real_url:
                try:
                    d = gnewsdecoder(raw["gnews_url"])
                    if d.get("status") and d.get("decoded_url"):
                        real_url = d["decoded_url"]
                except Exception:
                    pass
            body_text, body_html = _extract_body_html(real_url, client)
            if not body_text:
                continue
            ticker, exch = extract_ticker(body_text)
            if not ticker:
                continue
            pub_iso = _parse_pubdate(raw["pub"]) or ""
            yield {
                "event_id":     _event_id(real_url, pub_iso),
                "ticker":       ticker,
                "event_type":   "news_release",
                "source_name":  "cnw",
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
