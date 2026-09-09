"""
AccessWire source.

Fetches recent press releases for configured companies by scraping
AccessWire's company newsroom pages. URL patterns:
  https://www.accesswire.com/newsroom/v/{company_slug}
  https://www.accesswire.com/company/{company_slug}
  Individual releases: https://www.accesswire.com/{release_id}/{slug}
                    or https://www.accesswire.com/viewarticle.aspx?id={id}

Ticker config:
  {
    "ticker": "XYZ.CN",
    "source": "accesswire",
    "source_params": {
      "company_slug": "some-company-slug",
      "organization_url": "https://www.accesswire.com/newsroom/v/some-company-slug"
    }
  }

If organization_url is present, use it. Otherwise search the API or fall back
to web search.
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
BASE = "https://www.accessnewswire.com"


# ============ Low-level helpers ============

def _clean(text: str) -> str:
    """Collapse whitespace."""
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
    """Parse date strings like 'March 15, 2026 at 9:00 AM EDT'."""
    if not s:
        return None
    s = s.strip().rstrip(",")
    s = _TZ_STRIP.sub("", s).strip().rstrip(",")
    # Remove leading "at"
    s = re.sub(r"^\s*at\s+", "", s, flags=re.I)
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
                # AccessWire is US-based; assume ET (DST-ish)
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


_PW = None
_BROWSER = None


def _browser():
    """One browser per process, reused across every page in a run.

    A7: playwright is what pins this box to ~117 MB free RAM during the
    SediTracker scrape. Launching one browser per release would be far worse
    than launching one per run, so callers must call close_browser() when done.
    """
    global _PW, _BROWSER
    if _BROWSER is None:
        from playwright.sync_api import sync_playwright
        _PW = sync_playwright().start()
        _BROWSER = _PW.chromium.launch(headless=True, args=["--no-sandbox"])
    return _BROWSER


def close_browser():
    global _PW, _BROWSER
    try:
        if _BROWSER is not None:
            _BROWSER.close()
    except Exception:
        pass
    try:
        if _PW is not None:
            _PW.stop()
    except Exception:
        pass
    _BROWSER = None
    _PW = None


def _fetch_plain(url: str) -> str:
    """Plain HTTP. Kept for callers that do not need the challenge cleared."""
    with httpx.Client(headers={"User-Agent": UA}, timeout=25, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


def _fetch_rendered(url: str, wait_ms: int = 5000, wait_until: str = "domcontentloaded") -> str:
    """Load the page in a real browser so Cloudflare's challenge resolves.

    The listing page needs networkidle -- that is the state it was proven
    against on 2026-09-09 -- but networkidle can hang on a page holding a
    connection open, so a timeout there falls back rather than failing.
    """
    pg = _browser().new_page(user_agent=UA)
    try:
        try:
            pg.goto(url, wait_until=wait_until, timeout=45000)
        except Exception:
            if wait_until == "domcontentloaded":
                raise
            pg.goto(url, wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_timeout(wait_ms)
        return pg.content()
    finally:
        try:
            pg.close()
        except Exception:
            pass


def _fetch(url: str, render: bool = True) -> str:
    """Fetch URL and return HTML. Rendered by default -- accessnewswire.com
    returns a 403 challenge page to anything that is not a browser."""
    if render:
        return _fetch_rendered(url)
    return _fetch_plain(url)


# Release URLs look like /newsroom/en/<sector-slug>/<title-slug>-<id>.
# The sector is in the path, so mining releases are a path filter rather than
# a keyword guess -- which is what the Google News path had to do.
RELEASE_RE = re.compile(r"^/newsroom/[a-z]{2}/([a-z0-9-]+)/(.+?)-(\d{5,})$")
SECTOR = "metals-and-mining"


def list_sector_recent(sector: str = SECTOR, pages: int = 1, limit: int = 60) -> list[dict]:
    """Recent releases from Accesswire's own per-sector newsroom listing.

    This replaces Google News as the discovery mechanism: it is Accesswire's
    own index of the sector, so nothing is lost to a search ranking, a result
    cap, or a keyword list.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for pnum in range(1, max(1, pages) + 1):
        url = f"{BASE}/newsroom/industry/{sector}"
        if pnum > 1:
            url += f"?page={pnum}"
        try:
            html = _fetch_rendered(url, wait_ms=9000, wait_until="networkidle")
        except Exception as e:
            print(f"[accesswire] listing fetch failed {url}: {e}")
            break
        soup = BeautifulSoup(html, "lxml")
        found = 0
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            if href.startswith(BASE):
                href = href[len(BASE):]
            href = href.split("?")[0].split("#")[0]
            m = RELEASE_RE.match(href)
            if not m or m.group(1) != sector:
                continue
            full = BASE + href
            if full in seen:
                continue
            seen.add(full)
            found += 1
            out.append({
                "source_url":   full,
                "source_name":  "accessnewswire",
                "published_at": None,
                "raw_headline": _clean(a.get_text(" ", strip=True)),
                "release_id":   m.group(3),
            })
            if len(out) >= limit:
                return out
        print(f"[accesswire] listing page {pnum}: {found} release links")
        if found == 0:
            break
    return out


def _get_organization_url(cfg: dict, ticker: str) -> str | None:
    """
    Resolve organization URL from config or search API.
    Returns None if unable to determine.
    """
    params = cfg.get("source_params") or {}
    # If organization_url is provided, use it directly
    if params.get("organization_url"):
        return params["organization_url"]

    company_slug = params.get("company_slug")
    if company_slug:
        # Build newsroom URL from slug
        return f"{BASE}/newsroom/v/{company_slug}"

    # Fallback: search API
    ticker_no_suffix = ticker.split(".")[0] if ticker else ""
    if not ticker_no_suffix:
        return None

    try:
        search_url = f"{BASE}/api/search/?q={ticker_no_suffix}"
        html = _fetch(search_url)
        soup = BeautifulSoup(html, "lxml")
        # Look for company link in search results
        for a in soup.select("a[href*='/newsroom/'], a[href*='/company/']"):
            return urljoin(BASE, a.get("href", ""))
    except Exception:
        pass

    # Last fallback: web search
    try:
        search_url = f"{BASE}/search?q={ticker}"
        html = _fetch(search_url)
        soup = BeautifulSoup(html, "lxml")
        for a in soup.select("a[href*='/newsroom/'], a[href*='/company/']"):
            return urljoin(BASE, a.get("href", ""))
    except Exception:
        pass

    return None


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
    """Sanitize release HTML: keep allowed tags, unwrap others, drop media."""
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


# ============ Public interface ============

def list_recent(cfg: dict, limit: int = 25) -> Iterator[dict]:
    """Yield recent release summaries for configured AccessWire company."""
    ticker = cfg.get("ticker", "")
    org_url = _get_organization_url(cfg, ticker)

    if not org_url:
        print(f"[accesswire] cannot determine organization URL for {ticker}; skipping")
        return

    try:
        html = _fetch(org_url)
    except Exception as e:
        print(f"[accesswire] fetch organization page failed {org_url}: {e}")
        return

    soup = BeautifulSoup(html, "lxml")
    yielded = 0
    seen_hrefs: set[str] = set()

    # Find all release links: patterns like /<digits>/<slug> or /viewarticle.aspx?id=<id>
    for a in soup.select("a[href]"):
        if yielded >= limit:
            break
        href = a.get("href", "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = urljoin(BASE, href)
        if not href.startswith(BASE):
            continue

        # Match release patterns
        if not (re.search(r"/\d+/", href) or re.search(r"viewarticle\.aspx\?id=", href, re.I)):
            continue

        # Canonicalize
        href = re.sub(r"[?#].*$", "", href)
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        headline = _clean(a.get_text())
        if not headline or len(headline) < 8:
            headline = _clean(a.get("title") or "")
        if not headline:
            continue

        # Hunt for date in parent context
        pub = None
        parent = a.find_parent(["tr", "li", "article", "div"])
        if parent:
            txt = _clean(parent.get_text(" ", strip=True))
            m = DATE_RE.search(txt)
            if m:
                pub = _parse_date(m.group(1))

        yield {
            "source_url": href,
            "source_name": "accesswire",
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
        soup.select_one("#replace-me")
        or soup.select_one("div.article-body")
        or soup.select_one("#content")
        or soup.select_one("div.press-release")
        or soup.select_one("article")
        or soup.select_one("main")
        or soup.body
        or soup
    )

    # There are no date meta tags on the current template, but every release
    # opens with a dateline: "VANCOUVER, BC / ACCESS Newswire / September 9, 2026 /"
    if not summary.get("published_at"):
        from datetime import datetime as _dt
        head_txt = re.sub(r"\s+", " ", body_el.get_text(" ", strip=True))[:700]
        m = (re.search(r"ACCESS\s*Newswire\s*/\s*([A-Z][a-z]+ \d{1,2}, \d{4})", head_txt)
             or re.search(r"\b(\d{1,2} [A-Z][a-z]+ \d{4})\b", head_txt)
             or re.search(r"\b([A-Z][a-z]+ \d{1,2}, \d{4})\b", head_txt))
        if m:
            for _fmt in ("%B %d, %Y", "%d %B %Y"):
                try:
                    summary["published_at"] = _dt.strptime(m.group(1), _fmt).strftime("%Y-%m-%dT%H:%M:%S")
                    break
                except ValueError:
                    pass

    # Drop chrome + decorative elements before sanitization.
    # Materialise the list and skip tags already removed with an ancestor --
    # a decomposed tag has attrs None and any further access raises.
    def _strip(tags):
        for tag in list(tags):
            try:
                if tag.attrs is None or tag.parent is None:
                    continue
                yield tag
            except Exception:
                continue

    for tag in _strip(body_el.find_all([
        "script", "style", "nav", "footer", "header", "aside", "form",
        "iframe", "object", "embed", "svg", "canvas", "noscript", "button",
        "input", "select", "textarea", "meta", "link",
    ])):
        try:
            tag.decompose()
        except Exception:
            pass

    # Drop site chrome by id/class heuristic
    CHROME_RE = r"(social|share|newsletter|subscribe|related|sidebar|menu|cookie|breadcrumb|footer|header)"
    for tag in _strip(body_el.find_all(True)):
        try:
            cls = " ".join(tag.get("class") or [])
            ident = tag.get("id") or ""
            if re.search(CHROME_RE, cls + " " + ident, re.I):
                tag.decompose()
        except Exception:
            continue

    # Sanitized HTML
    raw_html = _sanitize_release_html(body_el, page_url=summary.get("source_url", ""))

    # Plain-text view: <br> as soft line break
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
    """Generate SHA256 event ID from URL and publication timestamp."""
    h = hashlib.sha256()
    h.update(source_url.encode("utf-8"))
    h.update(b"|")
    h.update((published_at or "").encode("utf-8"))
    return h.hexdigest()
