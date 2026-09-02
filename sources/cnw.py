"""
Canada Newswire (CNW/Cision) source.

Fetches recent press releases from CNW's company pages or search results.
Individual releases are at: https://www.newswire.ca/news-releases/{slug}-{id}.html

Config:
  {
    "ticker": "SUR.CN",
    "source": "cnw",
    "source_params": {
      "company_slug": "surface-metals-inc",
      "organization_url": "https://www.newswire.ca/news-releases/surface-metals-inc-news-releases.html"
    }
  }
"""
from __future__ import annotations
import datetime as dt
import hashlib
import re
from typing import Iterator
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
BASE = "https://www.newswire.ca"


# ---- low-level helpers ----

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def _strip_lead_date(text: str) -> str:
    """Remove a CNW-style date prefix such as 'Apr 06, 2026, 03:30 ET '."""
    if not text:
        return text
    return re.sub(
        r"^[A-Z][a-zA-Z]{2,9}\\.?\\s+\\d{1,2},\\s+\\d{4}"
        r"(?:,?\\s+\\d{1,2}:\\d{2}(?:\\s*[AP]\\.?M\\.?)?(?:\\s+[A-Za-z.]{1,20})?)?\\s*[-\u2013\u2014]?\\s*",
        "", text
    ).strip()




_TZ_STRIP = re.compile(
    r"\s+(ET|PT|CT|MT|EDT|EST|PDT|PST|CDT|CST|MDT|MST|GMT|UTC|"
    r"Eastern\s+Time|Pacific\s+Time|Central\s+Time|Mountain\s+Time)\.?\s*$",
    re.I,
)

# Matches "April 18, 2026", "Apr 18, 2026 10:30 AM ET", "April 18, 2026, 10:30 a.m."
DATE_RE = re.compile(
    r"([A-Z][a-zA-Z]{2,9}\.?\s+\d{1,2},\s+\d{4}"
    r"(?:,?\s+\d{1,2}:\d{2}(?:\s*[AP]\.?M\.?)?(?:\s+[A-Za-z.]{1,20})?)?)"
)


def _parse_date(s: str) -> str | None:
    if not s:
        return None
    s = s.strip().rstrip(",")
    s = _TZ_STRIP.sub("", s).strip().rstrip(",")
    s = re.sub(r"\b([AaPp])\.?\s*[Mm]\.?", lambda m: m.group(1).upper() + "M", s)
    s = re.sub(r"\s+", " ", s)

    patterns = [
        "%B %d, %Y %I:%M %p",
        "%B %d, %Y, %I:%M %p",
        "%B %d, %Y %H:%M",
        "%B %d, %Y, %H:%M",
        "%B %d, %Y",
        "%b %d, %Y %I:%M %p",
        "%b %d, %Y, %I:%M %p",
        "%b %d, %Y %H:%M",
        "%b %d, %Y, %H:%M",
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
                dtv = dtv.replace(tzinfo=dt.timezone(dt.timedelta(hours=-4)))
            return dtv.astimezone(dt.timezone.utc).isoformat()
        except Exception:
            continue
    try:
        dtv = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dtv.tzinfo is None:
            dtv = dtv.replace(tzinfo=dt.timezone.utc)
        return dtv.astimezone(dt.timezone.utc).isoformat()
    except Exception:
        pass
    # Final fallback: parse just the leading date portion (Mon DD, YYYY)
    m2 = re.match(r"([A-Z][a-zA-Z]{2,9}\.?\s+\d{1,2},?\s+\d{4})", s)
    if m2:
        ds = m2.group(1).replace(".", "").replace(",", "")
        for p in ("%B %d %Y", "%b %d %Y"):
            try:
                dtv = dt.datetime.strptime(ds, p)
                dtv = dtv.replace(tzinfo=dt.timezone(dt.timedelta(hours=-4)))
                return dtv.astimezone(dt.timezone.utc).isoformat()
            except Exception:
                continue
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
                # CNW is Toronto-based; assume ET
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
    """Sanitize HTML per newsfile.py pattern."""
    import copy as _copy
    el = _copy.copy(root)
    base = page_url or BASE

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
    m = re.match(r"^\s*<([a-z][a-z0-9]*)[^>]*>(.*)</\1>\s*$", html, re.I | re.S)
    if m:
        html = m.group(2)
    html = re.sub(r"\n\s*\n+", "\n", html).strip()
    html = re.sub(r"^\s*<h[1-3][^>]*>.*?</h[1-3]>\s*", "", html, count=1, flags=re.I | re.S)
    return html


# ---- public interface ----

def list_recent(cfg: dict, limit: int = 25) -> Iterator[dict]:
    """Yield recent release summaries for the configured CNW company."""
    params = cfg.get("source_params") or {}
    ticker = cfg.get("ticker", "")
    organization_url = params.get("organization_url")
    company_slug = params.get("company_slug")

    # Prefer organization_url, fall back to search
    if organization_url:
        url = organization_url
    elif ticker:
        # Search by ticker (strip suffix like .CN)
        ticker_bare = ticker.split(".")[0].upper()
        url = f"{BASE}/search/?keyword={ticker_bare}"
    else:
        print(f"[cnw] no organization_url or ticker for {cfg}; skipping")
        return

    try:
        html = _fetch(url)
    except Exception as e:
        print(f"[cnw] fetch failed {url}: {e}")
        return

    soup = BeautifulSoup(html, "lxml")
    yielded = 0
    seen_hrefs: set[str] = set()

    # Look for anchors linking to /news-releases/*.html
    for a in soup.select('a[href*="/news-releases/"]'):
        if yielded >= limit:
            break
        href = a.get("href", "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = urljoin(BASE, href)
        if not href.startswith(BASE) or "/news-releases/" not in href:
            continue
        # Canonicalize: strip query + fragment
        href = re.sub(r"[?#].*$", "", href)
        # Require an article-shaped URL (ends with -<digits>.html). Rejects section
        # index/nav URLs like /news-releases/multimedia/ which previously slipped
        # through and were mis-ingested as "Multimedia Gallery" etc.
        if not re.search(r"-\d{4,}\.html?$", href, re.I):
            continue
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        headline = clean_headline_cnw_v2(_clean(a.get_text()))
        if not headline or len(headline) < 8:
            headline = clean_headline_cnw_v2(_clean(a.get("title") or ""))
        if not headline:
            continue

        # Hunt for a date in parent row/list/article/div
        pub = None
        parent = a.find_parent(["tr", "li", "article", "div"])
        if parent:
            txt = _clean(parent.get_text(" ", strip=True))
            m = DATE_RE.search(txt)
            if m:
                pub = _parse_date(m.group(1))

        yield {
            "source_url": href,
            "source_name": "cnw",
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

    # Canonicalize published_at from meta tags if missing
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

    # Strengthen headline from og:title if weak
    if not summary.get("raw_headline") or len(summary["raw_headline"]) < 10:
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            summary["raw_headline"] = _clean(og["content"])

    # Body extraction -- progressive fallback
    body_el = (
        soup.select_one("section.release-body")
        or soup.select_one("div.release-body")
        or soup.select_one("article")
        or soup.select_one("main")
        or soup.body
        or soup
    )
    # Drop chrome + decorative elements
    for tag in body_el.find_all([
        "script", "style", "nav", "footer", "header", "aside", "form",
        "iframe", "object", "embed", "svg", "canvas", "noscript", "button",
        "input", "select", "textarea", "meta", "link",
    ]):
        tag.decompose()
    # Drop known site chrome by class/id heuristic
    for tag in body_el.find_all(True):
        cls = " ".join(tag.get("class") or [])
        ident = tag.get("id") or ""
        if re.search(r"(social|share|newsletter|subscribe|related|sidebar|menu|cookie|breadcrumb|footer|header)", cls + " " + ident, re.I):
            tag.decompose()

    # ---- sanitized HTML ----
    raw_html = _sanitize_release_html(body_el, page_url=summary.get("source_url", ""))

    # ---- plain-text view ----
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
    h = hashlib.sha256()
    h.update(source_url.encode("utf-8"))
    h.update(b"|")
    h.update((published_at or "").encode("utf-8"))
    return h.hexdigest()


def _organization_page_url(base_url: str, page: int) -> str:
    """Return organization_url with ?page=N (or page=1 == base)."""
    if page <= 1:
        return base_url
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}page={page}"


def _date_obj_from_iso(iso: str | None):
    if not iso:
        return None
    try:
        s = iso.replace("Z", "+00:00") if iso.endswith("Z") else iso
        d = dt.datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except Exception:
        return None


def list_historical(cfg: dict, cutoff_date=None, max_pages: int = 40, sleep_secs: float = 1.5):
    """Yield release summaries dating back to cutoff_date (default: 5 years ago).

    Iterates the organization_url pagination (?page=N) starting at 1.
    Stops when a page yields no new in-range items, or when all releases on a
    page predate cutoff_date.
    """
    import time
    params = cfg.get("source_params") or {}
    ticker = cfg.get("ticker", "")
    base_url = params.get("organization_url")
    if not base_url:
        # fall back to deriving from company_slug
        slug = params.get("company_slug")
        if slug:
            base_url = f"{BASE}/news/{slug}/"
        else:
            print(f"[cnw] no organization_url or company_slug for {ticker}; skipping")
            return

    if cutoff_date is None:
        cutoff_date = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(days=365 * 5)
    elif isinstance(cutoff_date, str):
        cutoff_date = _date_obj_from_iso(cutoff_date) or (
            dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(days=365 * 5)
        )
    if cutoff_date.tzinfo is None:
        cutoff_date = cutoff_date.replace(tzinfo=dt.timezone.utc)

    seen_hrefs: set[str] = set()
    total_yielded = 0

    for pg in range(1, max_pages + 1):
        url = _organization_page_url(base_url, pg)
        try:
            html = _fetch(url)
        except Exception as e:
            print(f"[cnw] historical fetch failed {url}: {e}")
            break

        soup = BeautifulSoup(html, "lxml")
        page_items = 0
        page_oldest_dt = None

        for a in soup.select('a[href*="/news-releases/"]'):
            href = a.get("href", "").strip()
            if not href:
                continue
            if href.startswith("/"):
                href = urljoin(BASE, href)
            if not href.startswith(BASE) or "/news-releases/" not in href:
                continue
            href = re.sub(r"[?#].*$", "", href)
            if not re.search(r"-\d{4,}\.html?$", href, re.I):
                continue
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)

            headline = clean_headline_cnw_v2(_clean(a.get_text()))
            if not headline or len(headline) < 8:
                headline = clean_headline_cnw_v2(_clean(a.get("title") or ""))
            if not headline:
                continue

            pub_iso = None
            parent = a.find_parent(["tr", "li", "article", "div"])
            if parent:
                txt = _clean(parent.get_text(" ", strip=True))
                m = DATE_RE.search(txt)
                if m:
                    pub_iso = _parse_date(m.group(1))

            pub_dt = _date_obj_from_iso(pub_iso) if pub_iso else None
            if pub_dt is not None:
                if page_oldest_dt is None or pub_dt < page_oldest_dt:
                    page_oldest_dt = pub_dt
                if pub_dt < cutoff_date:
                    continue

            yield {
                "source_url": href,
                "source_name": "cnw",
                "published_at": pub_iso,
                "ticker": ticker,
                "raw_headline": headline,
            }
            page_items += 1
            total_yielded += 1

        print(f"[cnw] {ticker} pg={pg} new={page_items} total={total_yielded} oldest={page_oldest_dt}")

        if page_items == 0:
            print(f"[cnw] {ticker} pg={pg} no new items; stopping")
            break
        if page_oldest_dt is not None and page_oldest_dt < cutoff_date:
            print(f"[cnw] {ticker} pg={pg} oldest predates cutoff; stopping")
            break
        time.sleep(sleep_secs)


_LEAD_DATE_CNW = re.compile(
    r"^[A-Z][a-zA-Z]{2,9}\.?\s+\d{1,2},\s+\d{4}"
    r"(?:,?\s+\d{1,2}:\d{2}(?:\s*[AP]\.?M\.?)?(?:\s+[A-Za-z.]{1,20})?)?\s*[-\u2013\u2014]?\s*",
    re.I,
)
_TRAILING_DATELINE_CNW = re.compile(
    r"\s+[A-Z][A-Z \-]{2,30}(?:,\s*[A-Z]{2,3})?,?\s*$"
)


def clean_headline_cnw(text: str) -> str:
    if not text:
        return text
    s = _LEAD_DATE_CNW.sub("", text).strip()
    s = _TRAILING_DATELINE_CNW.sub("", s).strip()
    return s


_TRAILING_DATELINE_FULL_CNW = re.compile(r"\s+/?CNW/?.*$")
_TRAILING_CITY_CNW = re.compile(
    r"\s+[A-Z][A-Z][A-Z]+(?:\s+[A-Z][A-Z]+)?"
    r"(?:,\s*[A-Z][A-Za-z\.]+(?:\s+[A-Za-z\.]+)?)?"
    r"(?:,\s*[A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})?"
    r"(?:,?\s+\d{1,2}:\d{2}(?:\s*[AP]\.?M\.?)?(?:\s+[A-Za-z.]{1,20})?)?"
    r"\s*$"
)


def clean_headline_cnw_v2(text: str) -> str:
    if not text:
        return text
    s = _LEAD_DATE_CNW.sub("", text).strip()
    s = _TRAILING_DATELINE_FULL_CNW.sub("", s).strip()
    s = _TRAILING_CITY_CNW.sub("", s).strip()
    s = re.sub(r"[\s,.\-\u2013\u2014]+$", "", s).strip()
    return s
