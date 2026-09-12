"""
Company IR (WordPress) source.

Scrapes WordPress-powered investor-relations pages via the standard /feed/ RSS endpoint.
Covers ~114 CSE mining juniors whose IR pages are built on WordPress (as of 2026-04).

Each ticker config in tickers.json points here via:
  {
    "ticker": "AA.CN",
    "source": "company_ir_wp",
    "source_params": {
      "website": "https://avventuraresources.com"
    }
  }

Uniform source-module interface:
  list_recent(cfg, limit)   -> Iterator[summary dict]
  fetch_body(summary)       -> summary dict (adds raw_body/raw_excerpt/raw_html)
  event_id_for(url, date)   -> sha256 hex
  list_historical(cfg, ...) -> Iterator[summary dict]  # via ?paged=N
"""
from __future__ import annotations
import datetime as dt
import hashlib
import re
from typing import Iterator
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

NS = {
    "dc":      "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom":    "http://www.w3.org/2005/Atom",
}

_CLEAN_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _CLEAN_WS.sub(" ", text or "").strip()


def _normalize_site(url: str) -> str:
    """Normalize website URL: https, no trailing slash."""
    if not url:
        return ""
    url = url.strip().rstrip("/")
    if url.startswith("http://"):
        url = "https://" + url[7:]
    if not url.startswith("https://"):
        url = "https://" + url
    return url


# RFC 822 date from WP RSS: "Mon, 12 Jan 2026 07:20:00 +0000"
_RFC822_FMTS = [
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%a, %d %b %Y %H:%M:%S GMT",
    "%d %b %Y %H:%M:%S %z",
    "%d %b %Y %H:%M:%S %Z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
]


def _parse_date(s: str) -> str | None:
    if not s:
        return None
    s = s.strip()
    for fmt in _RFC822_FMTS:
        try:
            dtv = dt.datetime.strptime(s, fmt)
            if dtv.tzinfo is None:
                dtv = dtv.replace(tzinfo=dt.timezone.utc)
            return dtv.astimezone(dt.timezone.utc).isoformat()
        except Exception:
            continue
    try:
        dtv = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dtv.tzinfo is None:
            dtv = dtv.replace(tzinfo=dt.timezone.utc)
        return dtv.astimezone(dt.timezone.utc).isoformat()
    except Exception:
        return None


def _fetch(url: str, *, accept: str = "application/rss+xml,application/xml;q=0.9,text/html;q=0.8,*/*;q=0.7") -> str:
    headers = {"User-Agent": UA, "Accept": accept}
    with httpx.Client(headers=headers, timeout=25, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


def _parse_feed(xml_text: str) -> list[dict]:
    """Parse WP RSS 2.0 feed (with Atom fallback)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    out: list[dict] = []

    # RSS 2.0: <rss><channel><item>
    for it in root.findall(".//item"):
        title_el = it.find("title")
        link_el = it.find("link")
        pub_el = it.find("pubDate")
        # Atom-style fallbacks inside RSS
        if link_el is None:
            link_el = it.find("{http://www.w3.org/2005/Atom}link")
            href = link_el.get("href") if link_el is not None else ""
        else:
            href = (link_el.text or "").strip()
        if pub_el is None:
            pub_el = it.find("dc:date", NS)

        title = (title_el.text or "").strip() if title_el is not None else ""
        pub = (pub_el.text or "").strip() if pub_el is not None else ""

        # content:encoded is a richer body than <description>
        ce = it.find("content:encoded", NS)
        desc = (ce.text or "").strip() if ce is not None and ce.text else ""
        if not desc:
            d = it.find("description")
            desc = (d.text or "").strip() if d is not None and d.text else ""

        if title and href:
            out.append({
                "title": _clean(title),
                "link": href,
                "pubDate": pub,
                "content_html": desc,
            })

    # Atom fallback
    if not out:
        for it in root.findall("atom:entry", NS):
            title_el = it.find("atom:title", NS)
            link_el = it.find("atom:link", NS)
            pub_el = it.find("atom:published", NS) or it.find("atom:updated", NS)
            content_el = it.find("atom:content", NS) or it.find("atom:summary", NS)

            title = (title_el.text or "").strip() if title_el is not None else ""
            href = link_el.get("href") if link_el is not None else ""
            pub = (pub_el.text or "").strip() if pub_el is not None else ""
            content = (content_el.text or "").strip() if content_el is not None and content_el.text else ""

            if title and href:
                out.append({
                    "title": _clean(title),
                    "link": href,
                    "pubDate": pub,
                    "content_html": content,
                })

    return out


# ---------------- public interface ----------------

# ---------------- WP REST API (5-year backfill) ----------------

import html as _htmlmod  # alias to avoid shadowing local 'html' vars


def list_via_rest(
    cfg: dict,
    years: int = 5,
    max_posts: int = 2000,
    per_page: int = 100,
) -> Iterator[dict]:
    """Paginate /wp-json/wp/v2/posts for up to `years` of history.

    Yields the same summary shape as list_recent, but carries the full post
    content in `_rest_inline_body` so fetch_body can skip the HTTP fetch.
    """
    params = cfg.get("source_params") or {}
    website = _normalize_site(params.get("website") or "")
    if not website:
        return
    ticker = cfg.get("ticker", "")

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=years * 365 + 1)
    after = cutoff.isoformat().replace("+00:00", "")

    rest_base = website.rstrip("/") + "/wp-json/wp/v2/" + (params.get("rest_post_type") or "posts")
    page = 1
    yielded = 0

    with httpx.Client(
        headers={"User-Agent": UA, "Accept": "application/json"},
        timeout=30,
        follow_redirects=True,
    ) as c:
        while yielded < max_posts and page <= 60:
            url = (
                f"{rest_base}?per_page={per_page}&page={page}"
                f"&orderby=date&order=desc&after={after}"
            )
            try:
                r = c.get(url)
            except Exception as e:
                print(f"[company_ir_wp.rest] {website} p{page} fetch err: {e}")
                return
            if r.status_code == 400 and "rest_post_invalid_page_number" in (r.text or ""):
                return
            if r.status_code != 200:
                print(f"[company_ir_wp.rest] {website} p{page} http={r.status_code}")
                return
            try:
                posts = r.json()
            except Exception as e:
                print(f"[company_ir_wp.rest] {website} p{page} decode err: {e}")
                return
            if not isinstance(posts, list) or not posts:
                return
            for p in posts:
                link = (p.get("link") or "").strip()
                title_raw = ((p.get("title") or {}).get("rendered") or "").strip()
                if not link or not title_raw:
                    continue
                title = _htmlmod.unescape(title_raw)
                link = re.sub(r"[#].*$", "", link)
                date = p.get("date_gmt") or p.get("date") or ""
                pub = _parse_date(date)
                content_html = (p.get("content") or {}).get("rendered") or ""
                excerpt_html = (p.get("excerpt") or {}).get("rendered") or ""

                yield {
                    "source_url": link,
                    "source_name": "company_ir_wp",
                    "published_at": pub,
                    "ticker": ticker,
                    "raw_headline": _clean(title),
                    "_rest_inline_body": content_html,
                    "_rest_excerpt": excerpt_html, "_cfg_website": website,
                }
                yielded += 1
                if yielded >= max_posts:
                    return
            if len(posts) < per_page:
                return
            page += 1


def _fetch_body_from_rest(summary: dict) -> bool:
    """Populate raw_body/raw_html from a REST inline body carried in summary."""
    rest_body = summary.pop("_rest_inline_body", None)
    rest_excerpt = summary.pop("_rest_excerpt", "") or ""
    if not rest_body:
        return False
    try:
        soup = BeautifulSoup(rest_body, "html.parser")
    except Exception:
        return False
    for tag in soup.find_all(["script", "style", "iframe", "noscript"]):
        tag.decompose()
    for tag in list(soup.find_all(True)):
        if tag.parent is None:
            continue
        attrs = tag.attrs or {}
        cls = " ".join(attrs.get("class") or [])
        ident = attrs.get("id") or ""
        blob = (cls + " " + ident).lower()
        if re.search(
            r"(social|share|newsletter|subscribe|sidebar|cookie|breadcrumb|comment-form)",
            blob,
        ):
            tag.decompose()
    summary["raw_body"] = soup.get_text("\n\n", strip=True)[:50000]
    summary["raw_html"] = str(soup)[:200000]
    if rest_excerpt:
        try:
            summary["raw_excerpt"] = BeautifulSoup(
                rest_excerpt, "html.parser"
            ).get_text(" ", strip=True)[:1500]
        except Exception:
            summary["raw_excerpt"] = rest_excerpt[:1500]
    return True


def list_recent(cfg: dict, limit: int = 25) -> Iterator[dict]:
    """Yield recent release summaries from the configured company's WP feed."""
    params = cfg.get("source_params") or {}
    website = _normalize_site(params.get("website") or "")
    if not website:
        print(f"[company_ir_wp] no source_params.website for {cfg.get('ticker')}; skipping")
        return

    ticker = cfg.get("ticker", "")
    feed_url = f"{website}/feed/"
    try:
        xml = _fetch(feed_url)
    except Exception as e:
        print(f"[company_ir_wp] fetch feed failed {feed_url}: {e}")
        return

    items = _parse_feed(xml)
    yielded = 0
    seen: set[str] = set()

    for it in items:
        if yielded >= limit:
            break
        href = (it.get("link") or "").strip()
        if not href:
            continue
        href = re.sub(r"[#].*$", "", href)  # strip fragment
        if href in seen:
            continue
        seen.add(href)

        headline = it.get("title") or ""
        if not headline or len(headline) < 4:
            continue
        pub = _parse_date(it.get("pubDate") or "")

        yield {
            "source_url": href,
            "source_name": "company_ir_wp",
            "published_at": pub,
            "ticker": ticker,
            "raw_headline": headline,
            # Carry the feed's inline content as a hint; fetch_body may override
            "_feed_content_html": it.get("content_html") or "", "_cfg_website": website,
        }
        yielded += 1


def fetch_body(summary: dict) -> dict:
    """Load the release page and extract a clean body.

    Paths: (1) REST inline body from list_via_rest, (2) HTML page fetch,
    (3) RSS feed content_html fallback.
    """
    # Path 1: REST inline body (no HTTP fetch)
    if _fetch_body_from_rest(summary):
        return summary
    url = summary.get("source_url", "")
    feed_content = summary.pop("_feed_content_html", "") or ""

    html = ""
    try:
        html = _fetch(url, accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.8")
    except Exception as e:
        summary["fetch_error"] = str(e)

    # --- prefer full page if available, else feed content ---
    body_html = html or (f"<div>{feed_content}</div>" if feed_content else "")
    if not body_html:
        summary["raw_body"] = ""
        summary["raw_excerpt"] = ""
        summary["raw_html"] = ""
        return summary

    soup = BeautifulSoup(body_html, "lxml")

    # Canonicalize published_at from meta if missing
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
            summary["published_at"] = _parse_date(t.get("datetime") or t.get_text()) or summary.get("published_at")

    # Strengthen headline from og:title if weak
    if not summary.get("raw_headline") or len(summary.get("raw_headline", "")) < 10:
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            summary["raw_headline"] = _clean(og["content"])

    # Body extraction — WordPress conventions first, then progressive fallbacks
    body_el = (
        soup.select_one("article .entry-content")
        or soup.select_one(".entry-content")
        or soup.select_one("article")
        or soup.select_one("main")
        or soup.select_one(".post-content")
        or soup.select_one(".news-article")
        or soup.body
        or soup
    )

    # Drop site chrome
    for tag in body_el.find_all([
        "script", "style", "nav", "footer", "header", "aside", "form",
        "iframe", "object", "embed", "svg", "canvas", "noscript", "button",
        "input", "select", "textarea", "meta", "link",
    ]):
        tag.decompose()
    for tag in body_el.find_all(True):
        attrs = tag.attrs or {}
        cls = " ".join(attrs.get("class") or [])
        ident = attrs.get("id") or ""
        if re.search(r"(social|share|newsletter|subscribe|related|sidebar|menu|cookie|breadcrumb|footer|header)", cls + " " + ident, re.I):
            tag.decompose()

    # Sanitized HTML
    raw_html = str(body_el)
    m = re.match(r"^\s*<([a-z][a-z0-9]*)[^>]*>(.*)</\1>\s*$", raw_html, re.I | re.S)
    if m:
        raw_html = m.group(2)
    raw_html = re.sub(r"\n\s*\n+", "\n", raw_html).strip()

    # Text view
    for br in body_el.find_all("br"):
        br.replace_with(" ")
    paragraphs: list[str] = []
    seen_p: set[str] = set()
    for node in body_el.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"]):
        t = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if not t or t in seen_p:
            continue
        if node.name == "li":
            t = "• " + t
        seen_p.add(t)
        paragraphs.append(t)
    if not paragraphs:
        paragraphs = [re.sub(r"\s+", " ", body_el.get_text(" ", strip=True)).strip()]

    text = "\n\n".join(p for p in paragraphs if p)
    summary["raw_html"] = raw_html
    summary["raw_body"] = text
    summary["raw_excerpt"] = re.sub(r"\s+", " ", text).strip()[:1500]
    return summary


def event_id_for(source_url: str, published_at: str | None) -> str:
    h = hashlib.sha256()
    h.update(source_url.encode("utf-8"))
    h.update(b"|")
    h.update((published_at or "").encode("utf-8"))
    return h.hexdigest()


def list_historical(cfg: dict, cutoff_date=None, max_pages: int = 20, sleep_secs: float = 1.0):
    """Walk WP's ?paged=N pagination backwards to pull older releases."""
    import time as _time
    params = cfg.get("source_params") or {}
    website = _normalize_site(params.get("website") or "")
    if not website:
        return

    ticker = cfg.get("ticker", "")
    if cutoff_date is None:
        cutoff_date = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(days=365 * 5)
    elif isinstance(cutoff_date, str):
        parsed = _parse_date(cutoff_date)
        cutoff_date = dt.datetime.fromisoformat(parsed) if parsed else (
            dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(days=365 * 5)
        )
    if cutoff_date.tzinfo is None:
        cutoff_date = cutoff_date.replace(tzinfo=dt.timezone.utc)

    seen: set[str] = set()
    total = 0

    for pg in range(1, max_pages + 1):
        url = f"{website}/feed/" if pg == 1 else f"{website}/feed/?paged={pg}"
        try:
            xml = _fetch(url)
        except Exception as e:
            print(f"[company_ir_wp] historical fetch failed {url}: {e}")
            break

        items = _parse_feed(xml)
        if not items:
            break

        page_oldest = None
        page_yielded = 0
        for it in items:
            href = (it.get("link") or "").strip()
            if not href or href in seen:
                continue
            seen.add(href)
            pub = _parse_date(it.get("pubDate") or "")
            pub_dt = None
            if pub:
                try:
                    pub_dt = dt.datetime.fromisoformat(pub)
                except Exception:
                    pub_dt = None

            if pub_dt is not None:
                if page_oldest is None or pub_dt < page_oldest:
                    page_oldest = pub_dt
                if pub_dt < cutoff_date:
                    continue

            headline = it.get("title") or ""
            if not headline:
                continue
            yield {
                "source_url": href,
                "source_name": "company_ir_wp",
                "published_at": pub,
                "ticker": ticker,
                "raw_headline": headline,
                "_feed_content_html": it.get("content_html") or "", "_cfg_website": website,
            }
            page_yielded += 1
            total += 1

        if page_yielded == 0 and pg > 1:
            break
        if page_oldest is not None and page_oldest < cutoff_date and total > 0:
            break
        if sleep_secs:
            _time.sleep(sleep_secs)


def list_recent_for_ticker(ticker: str, limit: int = 25):
    raise NotImplementedError(
        "company_ir_wp.list_recent_for_ticker not supported — "
        "call list_recent(cfg, limit) with source_params.website set"
    )
