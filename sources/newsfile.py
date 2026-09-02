"""
Newsfile Corp source.

Canonical wire for most CSE and TSX-V juniors. A company's release list lives at:
    https://www.newsfilecorp.com/company/{company_id}/...
and individual releases at:
    https://www.newsfilecorp.com/release/{release_id}/{slug}

Each ticker config in tickers.json points here via:

  {
    "ticker": "CCI.CN",
    "source": "newsfile",
    "source_params": { "company_id": 9218 }
  }

Uniform source-module interface:
  list_recent(cfg, limit)   -> Iterator[summary dict]
  fetch_body(summary)       -> summary dict (adds raw_body/raw_excerpt)
  event_id_for(url, date)   -> sha256 hex
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
BASE = "https://www.newsfilecorp.com"


# ---------------- low-level helpers ----------------

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


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
                # Newsfile is Toronto-based; assume ET (DST-ish approximation)
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


def _company_url(company_id) -> str:
    # The slug after the id is optional -- Newsfile resolves /company/{id}/ regardless.
    return f"{BASE}/company/{company_id}/"


# Tags we keep when sanitizing a release body for display. Everything else is
# unwrapped (children preserved) so we don't drop text accidentally.
_ALLOWED_TAGS = {
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "strong", "em", "b", "i", "u",
    "blockquote", "a", "sup", "sub",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption",
    "img", "figure", "figcaption",
}
# Tags to remove entirely (drop children too)
_DROP_TAGS = {"picture", "source", "video", "audio"}
# Attribute whitelist per tag
_ALLOWED_ATTRS = {
    "a":   {"href"},
    "img": {"src", "alt", "title"},
}


def _sanitize_release_html(root, page_url: str = "") -> str:
    """Return a sanitized HTML string representing the cleaned-up release body.

    Strategy: copy, then walk every descendant. If the tag is in _DROP_TAGS
    decompose it. If it's in _ALLOWED_TAGS keep it with a restricted attr set
    (and only http(s) links). Otherwise unwrap it so its children survive.

    Images: src resolved against page_url, restricted to http(s), data: URIs
    dropped (potential exfil/privacy footgun).
    """
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
                # unsupported protocol (data:, javascript:, etc.) -- drop the img
                tag.decompose()
                continue
            tag["src"] = src
            # strip tracking pixels: 1x1 images usually have width/height 1
            # (but those attrs are stripped by our whitelist; leave as-is)

    # Collapse runs of empty paragraphs / leading whitespace
    html = str(el)
    # The wrapping <div>/<article> tag itself isn't in the allowed set -- strip it.
    # After the unwrap pass, the outermost tag may still be the original container.
    # Remove its outer tags but preserve innerHTML.
    m = re.match(r"^\s*<([a-z][a-z0-9]*)[^>]*>(.*)</\1>\s*$", html, re.I | re.S)
    if m:
        html = m.group(2)
    # Tidy up excessive whitespace
    html = re.sub(r"\n\s*\n+", "\n", html).strip()
    # Drop a leading heading -- the dashboard shows the headline above the body,
    # so a duplicate h1/h2 at the top of the release looks redundant.
    html = re.sub(r"^\s*<h[1-3][^>]*>.*?</h[1-3]>\s*", "", html, count=1, flags=re.I | re.S)
    return html


# ---------------- public interface ----------------

def list_recent(cfg: dict, limit: int = 25) -> Iterator[dict]:
    """Yield recent release summaries for the configured Newsfile company_id."""
    params = cfg.get("source_params") or {}
    company_id = params.get("company_id")
    if company_id is None:
        print(f"[newsfile] no source_params.company_id for {cfg.get('ticker')}; skipping")
        return

    ticker = cfg.get("ticker", "")
    url = _company_url(company_id)
    try:
        html = _fetch(url)
    except Exception as e:
        print(f"[newsfile] fetch company page failed {url}: {e}")
        return

    soup = BeautifulSoup(html, "lxml")
    yielded = 0
    seen_hrefs: set[str] = set()

    # Newsfile renders the release list as a table / list of links.
    # Primary selector: any anchor pointing at a /release/ URL.
    for a in soup.select('a[href*="/release/"]'):
        if yielded >= limit:
            break
        href = a.get("href", "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = urljoin(BASE, href)
        if not href.startswith(BASE) or "/release/" not in href:
            continue
        # Canonicalize: strip query + fragment
        href = re.sub(r"[?#].*$", "", href)
        if href in seen_hrefs:
            continue
        # Ignore obvious non-release links (e.g. anchors labeled "View all")
        path_match = re.search(r"/release/\d+", href)
        if not path_match:
            continue
        seen_hrefs.add(href)

        headline = _clean(a.get_text())
        if not headline or len(headline) < 8:
            # Sometimes anchors wrap image thumbnails; fall back to title attr
            headline = _clean(a.get("title") or "")
        if not headline:
            continue

        # Hunt for a date in the enclosing row/list-item text
        pub = None
        parent = a.find_parent(["tr", "li", "article", "div"])
        if parent:
            txt = _clean(parent.get_text(" ", strip=True))
            m = DATE_RE.search(txt)
            if m:
                pub = _parse_date(m.group(1))

        yield {
            "source_url": href,
            "source_name": "newsfile",
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

    # Strengthen headline from og:title if weak
    if not summary.get("raw_headline") or len(summary["raw_headline"]) < 10:
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            summary["raw_headline"] = _clean(og["content"])

    # Body extraction -- try known containers, fall back progressively
    body_el = (
        soup.select_one("div.news-release")
        or soup.select_one("div.release-body")
        or soup.select_one("div#releaseBody")
        or soup.select_one("div.press-release")
        or soup.select_one("article")
        or soup.select_one("main")
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
        if re.search(r"(social|share|newsletter|subscribe|related|sidebar|menu|cookie|breadcrumb|footer|header)", cls + " " + ident, re.I):
            tag.decompose()

    # ---- sanitized HTML for reader view ----
    raw_html = _sanitize_release_html(body_el, page_url=summary.get("source_url", ""))

    # ---- plain-text view for classifier / excerpt ----
    # <br> acts as a soft line break within a paragraph
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


# Back-compat shim -- callers still using the old GNW-shaped API get a clear error
def list_recent_for_ticker(ticker: str, limit: int = 25):
    raise NotImplementedError(
        "newsfile.list_recent_for_ticker(ticker, limit) is not supported -- "
        "call list_recent(cfg, limit) with source_params.company_id set"
    )

# --- HISTORICAL PAGINATION (list_historical) ---
# This block is appended to the end of /opt/mnt/app/sources/newsfile.py
# It adds list_historical(cfg, cutoff_date) that walks ?pg=N backwards through
# a company's Newsfile archive, yielding release summaries older than cutoff_date.
#
# Contract mirrors list_recent: yields dicts of
#   {source_url, source_name="newsfile", published_at, ticker, raw_headline}
#
# Termination conditions (in order of precedence):
#   1. Page has no /release/ anchors (end of archive / empty page)
#   2. Page explicitly says "no stories available"
#   3. Every release on the page is older than cutoff_date AND we've already
#      emitted at least one release (guards against sparse date parsing)
#   4. Safety cap: max_pages pages (default 40 -> up to 1000 releases)


from datetime import datetime, timedelta, timezone
import time


def _parse_page_date_str(s):
    """Best-effort ISO-aware comparison: try _parse_date -> datetime."""
    if not s:
        return None
    try:
        parsed = _parse_date(s)
    except Exception:
        return None
    if not parsed:
        return None
    # _parse_date returns a string like "2024-08-15 14:30:00" or "2024-08-15"
    for fmt in (
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(parsed, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None


def list_historical(cfg: dict, cutoff_date=None, max_pages: int = 40, sleep_secs: float = 1.2):
    """Yield release summaries dating back to cutoff_date (default: 5 years ago).

    Iterates Newsfile's ?pg=N pagination starting at pg=1 (base URL).
    Stops when pages run out, or when all releases on a page are older than cutoff_date.
    """
    params = cfg.get("source_params") or {}
    company_id = params.get("company_id")
    if company_id is None:
        print(f"[newsfile] no source_params.company_id for {cfg.get('ticker')}; skipping")
        return

    ticker = cfg.get("ticker", "")

    if cutoff_date is None:
        cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=365 * 5)
    elif isinstance(cutoff_date, str):
        cutoff_date = _parse_page_date_str(cutoff_date) or (
            datetime.now(tz=timezone.utc) - timedelta(days=365 * 5)
        )
    if cutoff_date.tzinfo is None:
        cutoff_date = cutoff_date.replace(tzinfo=timezone.utc)

    base = _company_url(company_id)
    seen_hrefs: set[str] = set()
    total_yielded = 0

    for pg in range(1, max_pages + 1):
        url = base if pg == 1 else f"{base}?pg={pg}"
        try:
            html = _fetch(url)
        except Exception as e:
            print(f"[newsfile] historical fetch failed {url}: {e}")
            break

        # Fast empty-page check
        if "no stories available" in html.lower():
            print(f"[newsfile] {ticker} pg={pg} empty (no stories), stopping")
            break

        soup = BeautifulSoup(html, "lxml")
        page_items = 0
        page_oldest_dt = None

        for a in soup.select('a[href*="/release/"]'):
            href = a.get("href", "").strip()
            if not href:
                continue
            if href.startswith("/"):
                href = urljoin(BASE, href)
            if not href.startswith(BASE) or "/release/" not in href:
                continue
            href = re.sub(r"[?#].*$", "", href)
            if href in seen_hrefs:
                continue
            if not re.search(r"/release/\d+", href):
                continue
            seen_hrefs.add(href)

            headline = _clean(a.get_text())
            if not headline or len(headline) < 8:
                headline = _clean(a.get("title") or "")
            if not headline:
                continue

            pub = None
            parent = a.find_parent(["tr", "li", "article", "div"])
            if parent:
                txt = _clean(parent.get_text(" ", strip=True))
                m = DATE_RE.search(txt)
                if m:
                    pub = _parse_date(m.group(1))

            pub_dt = _parse_page_date_str(pub) if pub else None
            if pub_dt is not None:
                if page_oldest_dt is None or pub_dt < page_oldest_dt:
                    page_oldest_dt = pub_dt

            # Hard cutoff: drop releases older than cutoff when we know the date
            if pub_dt is not None and pub_dt < cutoff_date:
                continue

            yield {
                "source_url": href,
                "source_name": "newsfile",
                "published_at": pub,
                "ticker": ticker,
                "raw_headline": headline,
            }
            page_items += 1
            total_yielded += 1

        # Termination: nothing found on this page means archive is exhausted
        # (BeautifulSoup may find 0 anchors on a terminal "Back" page)
        if page_items == 0 and pg > 1:
            print(f"[newsfile] {ticker} pg={pg} yielded 0 items, stopping")
            break

        # Termination: entire page is older than cutoff (and we've emitted items)
        if (
            page_oldest_dt is not None
            and page_oldest_dt < cutoff_date
            and total_yielded > 0
        ):
            print(
                f"[newsfile] {ticker} pg={pg} oldest={page_oldest_dt.date()} < cutoff={cutoff_date.date()}, stopping"
            )
            break

        if pg < max_pages:
            time.sleep(sleep_secs)

    print(f"[newsfile] {ticker} historical walk yielded {total_yielded} releases across {pg} page(s)")
