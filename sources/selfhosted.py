"""
Self-hosted source -- generic scraper for company-owned websites.

Handles company websites (WordPress, Squarespace, Wix, custom CMS) that publish
press releases on their own domains. Crawls /news/, /press/, /investors/, /media/
paths to find individual release URLs, then extracts bodies.

Config in tickers.json:
  {
    "ticker": "AFF.CN",
    "source": "selfhosted",
    "source_params": {
      "news_urls": ["https://www.affinity-metals.com/news/", ...],
      "website": "https://www.affinity-metals.com"  # fallback if news_urls absent
    }
  }
"""
from __future__ import annotations
import copy as _copy
import datetime as dt
import hashlib
import re
from typing import Iterator
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ---- low-level helpers ----

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


_TZ_STRIP = re.compile(
    r"\s+(ET|PT|CT|MT|EDT|EST|PDT|PST|CDT|CST|MDT|MST|GMT|UTC|"
    r"Eastern\s+Time|Pacific\s+Time|Central\s+Time|Mountain\s+Time)\.?\s*$",
    re.I,
)

DATE_RE = re.compile(
    r"([A-Z][a-zA-Z]{2,9}\.?\s+\d{1,2},\s+\d{4}"
    r"(?:,?\s+\d{1,2}:\d{2}(?:\s*[AP]\.?M\.?)?(?:\s+[A-Za-z.]{1,20})?)?)"
)


def _parse_date(s: str) -> str | None:
    """Parse dates in multiple formats, return ISO UTC string."""
    if not s:
        return None
    s = s.strip().rstrip(",")
    s = _TZ_STRIP.sub("", s).strip().rstrip(",")
    # Normalize "a.m." / "p.m." -> "AM"/"PM"
    s = re.sub(r"\b([AaPp])\.?\s*[Mm]\.?", lambda m: m.group(1).upper() + "M", s)
    # Normalize multiple spaces
    s = re.sub(r"\s+", " ", s)

    patterns = [
        "%B %d, %Y %I:%M %p",
        "%B %d, %Y, %I:%M %p",
        "%B %d, %Y",
        "%b %d, %Y %I:%M %p",
        "%b %d, %Y, %I:%M %p",
        "%b %d, %Y",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for p in patterns:
        try:
            dtv = dt.datetime.strptime(s, p)
            if dtv.tzinfo is None:
                # Assume ET (conservative approximation)
                dtv = dtv.replace(tzinfo=dt.timezone(dt.timedelta(hours=-4)))
            return dtv.astimezone(dt.timezone.utc).isoformat()
        except Exception:
            continue
    # Try ISO fromisoformat as last resort
    try:
        dtv = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dtv.tzinfo is None:
            dtv = dtv.replace(tzinfo=dt.timezone.utc)
        return dtv.astimezone(dt.timezone.utc).isoformat()
    except Exception:
        return None


_JUNK_ANCHOR_PHRASES = {
    "pdf", "read more", "read more >>", "read more »", "read more...",
    "continue reading", "learn more", "more", "view more", "view all",
    "disclaimer", "download", "download pdf", "download now",
    "presentations", "presentation", "investor presentation",
    "stock information", "stock info", "stock quote",
    "contact us", "contact", "subscribe", "sign up",
    "click here", "here", "home", "news", "investors", "investor",
    "media", "about", "team", "careers", "privacy", "terms",
    "prospectus", "factsheet", "corporate presentation",
}

_DATE_IN_URL_PATTERNS = [
    re.compile(r"/(\d{4})/(\d{2})/(\d{2})/"),
    re.compile(r"/(\d{4})/(\d{2})/"),
    re.compile(r"-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*-(\d{1,2})-(\d{4})", re.I),
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
]

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _date_from_url(url):
    for pat in _DATE_IN_URL_PATTERNS:
        m = pat.search(url or "")
        if not m:
            continue
        groups = m.groups()
        try:
            if len(groups) == 3 and groups[0].isalpha():
                mo = _MONTH_MAP.get(groups[0][:3].lower())
                if not mo:
                    continue
                d = int(groups[1])
                y = int(groups[2])
                return f"{y:04d}-{mo:02d}-{d:02d}T12:00:00+00:00"
            if len(groups) == 3 and groups[0].isdigit():
                y, mo, d = map(int, groups)
                if y < 2015 or y > 2030:
                    continue
                return f"{y:04d}-{mo:02d}-{d:02d}T12:00:00+00:00"
            if len(groups) == 2:
                y, mo = map(int, groups)
                if y < 2015 or y > 2030:
                    continue
                return f"{y:04d}-{mo:02d}-01T12:00:00+00:00"
        except Exception:
            continue
    return None


def _headline_from_url_slug(url):
    try:
        from urllib.parse import urlparse
        path = urlparse(url).path.rstrip("/")
        slug = path.rsplit("/", 1)[-1]
        slug = re.sub(r"\.(html?|php|aspx?)$", "", slug, flags=re.I)
        slug = re.sub(r"^\d{4}-\d{2}-\d{2}[-_]?", "", slug)
        slug = re.sub(r"^NR[-_]?", "", slug, flags=re.I)
        words = re.split(r"[-_]+", slug)
        return " ".join(w[:1].upper() + w[1:] if w else "" for w in words if w).strip()
    except Exception:
        return ""


def _looks_like_junk_anchor(text, href):
    t = (text or "").strip().lower()
    if not t:
        return True
    if t in _JUNK_ANCHOR_PHRASES:
        return True
    if len(t) < 15 and t.endswith(">>"):
        return True
    if re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$", t):
        return True
    low_href = (href or "").lower()
    if low_href.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip")):
        return True
    return False

def _fetch(url: str) -> str:
    with httpx.Client(headers={"User-Agent": UA}, timeout=25, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


_ALLOWED_TAGS = {
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "strong", "em", "b", "i", "u",
    "blockquote", "a", "sup", "sub",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption",
    "img", "figure", "figcaption",
}
_DROP_TAGS = {"picture", "source", "video", "audio"}
_ALLOWED_ATTRS = {
    "a":   {"href"},
    "img": {"src", "alt", "title"},
}


def _sanitize_release_html(root, page_url: str = "") -> str:
    """Return sanitized HTML string of the cleaned-up release body.

    Strategy: copy, then walk every descendant. If in _DROP_TAGS decompose it.
    If in _ALLOWED_TAGS keep it with restricted attr set. Otherwise unwrap.
    """
    el = _copy.copy(root)
    base = page_url or "https://example.com"

    for tag in list(el.find_all(True)):
        if tag.name in _DROP_TAGS:
            tag.decompose()
            continue
        if tag.name not in _ALLOWED_TAGS:
            tag.unwrap()
            continue
        allowed = _ALLOWED_ATTRS.get(tag.name, set())
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in allowed}
        if tag.name == "a":
            href = (tag.get("href") or "").strip()
            if href.startswith("/"):
                href = urljoin(base, href)
                tag["href"] = href
            if not (href.startswith("http://") or href.startswith("https://") or href.startswith("mailto:")):
                tag.attrs.pop("href", None)
        elif tag.name == "img":
            src = (tag.get("src") or "").strip()
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/") or not re.match(r"^[a-z]+:", src, re.I):
                src = urljoin(base, src)
            if not (src.startswith("http://") or src.startswith("https://")):
                tag.decompose()
                continue
            tag["src"] = src

    html = str(el)
    # Remove the outermost wrapper but preserve innerHTML
    m = re.match(r"^\s*<([a-z][a-z0-9]*)[^>]*>(.*)</\1>\s*$", html, re.I | re.S)
    if m:
        html = m.group(2)
    # Tidy up excessive whitespace
    html = re.sub(r"\n\s*\n+", "\n", html).strip()
    # Drop leading h1/h2/h3 (dashboard shows headline above)
    html = re.sub(r"^\s*<h[1-3][^>]*>.*?</h[1-3]>\s*", "", html, count=1, flags=re.I | re.S)
    return html


# ---- public interface ----

def list_recent(cfg: dict, limit: int = 25) -> Iterator[dict]:
    """Yield recent release summaries from configured news URLs."""
    params = cfg.get("source_params") or {}
    news_urls = params.get("news_urls") or []

    # Fallback: if no news_urls, derive from website root
    if not news_urls:
        website = params.get("website")
        if website:
            # Try common paths
            base = website.rstrip("/")
            news_urls = [
                f"{base}/news/",
                f"{base}/press/",
                f"{base}/press-releases/",
                f"{base}/investors/",
                f"{base}/media/",
            ]
        else:
            print(f"[selfhosted] no news_urls or website for {cfg.get('ticker')}; skipping")
            return

    ticker = cfg.get("ticker", "")
    seen_hrefs: set[str] = set()
    yielded = 0

    for listing_url in news_urls:
        if yielded >= limit:
            break

        try:
            html = _fetch(listing_url)
        except Exception as e:
            print(f"[selfhosted] fetch listing failed {listing_url}: {e}")
            continue

        soup = BeautifulSoup(html, "lxml")

        # Parse the listing URL to determine domain + depth for heuristics
        parsed_listing = urlparse(listing_url)
        listing_domain = f"{parsed_listing.scheme}://{parsed_listing.netloc}"
        listing_depth = len([p for p in parsed_listing.path.split("/") if p])

        # Find all anchors
        for a in soup.find_all("a", href=True):
            if yielded >= limit:
                break

            href = a.get("href", "").strip()
            if not href:
                continue

            # Resolve relative URLs
            if href.startswith("/"):
                href = urljoin(listing_domain, href)
            elif not href.startswith("http"):
                href = urljoin(listing_url, href)

            # Stay on same domain
            if not href.startswith(listing_domain):
                continue

            # Skip external wire services (they have dedicated modules)
            if any(wire in href for wire in [
                "newsfilecorp.com", "globenewswire.com", "marketwired.com",
                "stockhouse.com", "thestreet.com", "seekingalpha.com"
            ]):
                continue

            # Canonicalize: strip query + fragment, trailing slash
            href = re.sub(r"[?#].*$", "", href)
            if href.endswith("/") and href.count("/") > 3:
                # Keep trailing slash only for domain root
                href = href.rstrip("/")

            if href in seen_hrefs:
                continue

            # Heuristic filters: looks like a press release URL
            # - Matches /news/<slug>, /press/<slug>, /press-releases/<slug>, /media/<slug>, /posts/<slug>
            # - Or WP-style /YYYY/MM/slug/
            # - Or any link whose path depth is listing_depth + 1 and contains year digits
            matches_pattern = (
                re.search(r"/(news|press|press-releases|media|posts)/[^/]+/?$", href, re.I)
                or re.search(r"/\d{4}/\d{2}/[^/]+/?$", href)  # WP date structure
            )

            if not matches_pattern:
                # Fallback: check if path depth is listing_depth + 1 and has year digits
                parsed_href = urlparse(href)
                href_depth = len([p for p in parsed_href.path.split("/") if p])
                has_year = re.search(r"\d{4}", parsed_href.path)
                if not (href_depth == listing_depth + 1 and has_year):
                    continue

            seen_hrefs.add(href)

            # Extract headline from anchor text or fallback to inner h2/h3
            # Extract headline: skip obvious chrome, fall back to URL slug
            anchor_text = _clean(a.get_text())
            if _looks_like_junk_anchor(anchor_text, href):
                continue
            headline = anchor_text
            if not headline or len(headline) < 15:
                h_el = a.find(["h2", "h3", "h4"])
                if h_el:
                    headline = _clean(h_el.get_text())
            if not headline or len(headline) < 15:
                headline = _clean(a.get("title") or "")
            if not headline or len(headline) < 15:
                # Weak anchor text — use URL slug; fetch_body will overwrite with og:title.
                slug_title = _headline_from_url_slug(href)
                if slug_title and len(slug_title) >= 8:
                    headline = slug_title
            if not headline or len(headline) < 8:
                continue

            # Hunt for a date in the enclosing card/row/div
            pub = None
            parent = a.find_parent(["article", "div", "li", "tr", "section"])
            if parent:
                txt = _clean(parent.get_text(" ", strip=True))
                m = DATE_RE.search(txt)
                if m:
                    pub = _parse_date(m.group(1))

            yield {
                "source_url": href,
                "source_name": "selfhosted",
                "published_at": pub,
                "ticker": ticker,
                "raw_headline": headline,
            }
            yielded += 1


def fetch_body(summary: dict) -> dict:
    """Given a summary from list_recent, load the release page and extract body."""
    try:
        html = _fetch(summary["source_url"])
    except Exception as e:
        summary["raw_body"] = ""
        summary["raw_excerpt"] = ""
        summary["fetch_error"] = str(e)
        return summary

    soup = BeautifulSoup(html, "lxml")

    # Canonicalize published_at from meta tags / <time> if missing
    if not summary.get("published_at"):
        meta_date = (
            soup.find("meta", property="article:published_time")
            or soup.find("meta", attrs={"name": "pubdate"})
            or soup.find("meta", attrs={"itemprop": "datePublished"})
            or soup.find("meta", attrs={"name": "date"})
        )
        if meta_date and meta_date.get("content"):
            summary["published_at"] = _parse_date(meta_date["content"]) or summary.get("published_at")
    if not summary.get("published_at"):
        t = soup.find("time")
        if t:
            val = t.get("datetime") or t.get_text()
            summary["published_at"] = _parse_date(val) or summary.get("published_at")

    # Prefer structured title over anchor text (og:title > twitter:title > h1).
    better_title = None
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        better_title = _clean(og["content"])
    if not better_title:
        tw = soup.find("meta", attrs={"name": "twitter:title"})
        if tw and tw.get("content"):
            better_title = _clean(tw["content"])
    if not better_title:
        h1 = soup.find("h1")
        if h1:
            better_title = _clean(h1.get_text())
    if better_title and len(better_title) >= 10:
        summary["raw_headline"] = better_title

    # Body extraction -- try known containers, fall back progressively
    body_el = (
        soup.select_one("article")
        or soup.select_one("main")
        or soup.select_one("div.entry-content")
        or soup.select_one("div.post-content")
        or soup.select_one("div.page-content")
        or soup.select_one("div#content")
        or soup.select_one("div[role='main']")
        or soup.body
        or soup
    )

    # Drop chrome + decorative elements before sanitization
    for tag in body_el.find_all([
        "script", "style", "nav", "footer", "header", "aside", "form",
        "iframe", "object", "embed", "svg", "canvas", "noscript", "button",
        "input", "select", "textarea", "meta", "link",
    ]):
        tag.decompose()

    # Drop known site chrome by id/class heuristic
    for tag in body_el.find_all(True):
        cls = " ".join(tag.get("class") or [])
        ident = tag.get("id") or ""
        if re.search(
            r"(social|share|newsletter|subscribe|related|sidebar|menu|cookie|breadcrumb|footer|header)",
            cls + " " + ident,
            re.I
        ):
            tag.decompose()

    # Sanitized HTML for reader view
    raw_html = _sanitize_release_html(body_el, page_url=summary.get("source_url", ""))

    # Plain-text view for classifier / excerpt
    for br in body_el.find_all("br"):
        br.replace_with(" ")

    PARA_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6",
                 "li", "blockquote", "pre", "dt", "dd")
    paragraphs: list[str] = []
    seen: set[str] = set()
    for node in body_el.find_all(PARA_TAGS):
        t = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if not t or t in seen:
            continue
        if node.name == "li":
            t = "• " + t
        seen.add(t)
        paragraphs.append(t)

    if len(paragraphs) < 2:
        paragraphs = []
        seen = set()
        for d in body_el.find_all("div"):
            if d.find(PARA_TAGS) or d.find("div"):
                continue
            t = re.sub(r"\s+", " ", d.get_text(" ", strip=True)).strip()
            if t and t not in seen:
                seen.add(t)
                paragraphs.append(t)

    if not paragraphs:
        paragraphs = [re.sub(r"\s+", " ", body_el.get_text(" ", strip=True)).strip()]

    text = "\n\n".join(p for p in paragraphs if p)
    flat = re.sub(r"\s+", " ", text).strip()
    summary["raw_html"] = raw_html
    summary["raw_body"] = text
    summary["raw_excerpt"] = flat[:1500]
    return summary


def event_id_for(source_url: str, published_at: str | None) -> str:
    """Generate event ID: sha256(url|date)."""
    h = hashlib.sha256()
    h.update(source_url.encode("utf-8"))
    h.update(b"|")
    h.update((published_at or "").encode("utf-8"))
    return h.hexdigest()
