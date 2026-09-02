"""
Company-site source.

Generic scraper for companies that publish press releases directly on their
own corporate website rather than via a wire service. Configurable per ticker
via source_params so one module handles N different company sites.

Uniform source-module interface matches sources/newsfile.py:
  list_recent(cfg, limit)   -> Iterator[summary dict]
  fetch_body(summary)       -> summary dict (adds raw_body/raw_excerpt/raw_html)
  event_id_for(url, date)   -> sha256 hex

source_params schema (all keys optional except news_index):
  news_index:           URL of the index page that lists releases (required)
  article_link_pattern: substring an article link URL must contain
                        (default: "/news")
  article_selector:     CSS selector for the release body on the article page
                        (default: "article, main, .entry-content, .post-content")
  title_selector:       CSS selector for the release title
                        (default: "h1")
  date_selector:        optional CSS selector for the release date. If omitted
                        we scan the article text for the first date-like string.
  link_exclude:         optional substring; anchors containing it are skipped
  site_name:            human-readable source name written on events
                        (default: derived from the news_index host)
"""
from __future__ import annotations
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

# Matches "April 18, 2026", "Apr 18, 2026 10:30 AM ET", "2026-04-18"
DATE_RE = re.compile(
    r"([A-Z][a-zA-Z]{2,9}\.?\s+\d{1,2},\s+\d{4}"
    r"(?:,?\s+\d{1,2}:\d{2}(?:\s*[AP]\.?M\.?)?(?:\s+[A-Za-z.]{1,20})?)?)"
)
ISO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?)")

_TZ_STRIP = re.compile(
    r"\s+(ET|PT|CT|MT|EDT|EST|PDT|PST|CDT|CST|MDT|MST|GMT|UTC|"
    r"Eastern\s+Time|Pacific\s+Time|Central\s+Time|Mountain\s+Time)\.?\s*$",
    re.I,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


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
                # Most CSE juniors are Toronto-based; assume ET
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
        return None


def _fetch(url: str) -> str:
    with httpx.Client(headers={"User-Agent": UA}, timeout=25, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


# Reuse newsfile's sanitizer shape by copying its constants locally so this
# module stays self-contained.
_ALLOWED_TAGS = {
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "strong", "em", "b", "i", "u",
    "blockquote", "a", "sup", "sub",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption",
    "img", "figure", "figcaption",
}
_DROP_TAGS = {"picture", "source", "video", "audio", "script", "style", "nav", "header", "footer", "aside", "form"}
_ALLOWED_ATTRS = {
    "a":   {"href"},
    "img": {"src", "alt", "title"},
}


def _sanitize_html(root, page_url: str) -> str:
    import copy as _copy
    el = _copy.copy(root)
    base = page_url

    for tag in list(el.find_all(True)):
        # Skip tags that were detached by an earlier decompose/unwrap on an ancestor
        if tag.parent is None:
            continue
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
    # Drop a leading duplicate heading — the dashboard renders the headline
    # separately.
    html = re.sub(r"^\s*<h[1-3][^>]*>.*?</h[1-3]>\s*", "", html, count=1, flags=re.I | re.S)
    return html


# ---------------- public interface ----------------

def _params(cfg: dict) -> dict:
    p = dict(cfg.get("source_params") or {})
    host = ""
    if p.get("news_index"):
        try:
            host = urlparse(p["news_index"]).hostname or ""
        except Exception:
            host = ""
    p.setdefault("article_link_pattern", "/news")
    p.setdefault("article_selector", "article, main, .entry-content, .post-content")
    p.setdefault("title_selector", "h1")
    p.setdefault("date_selector", None)
    p.setdefault("link_exclude", None)
    p.setdefault("site_name", f"companysite:{host}" if host else "companysite")
    return p


def list_recent(cfg: dict, limit: int = 25) -> Iterator[dict]:
    params = _params(cfg)
    index_url = params.get("news_index")
    if not index_url:
        print(f"[companysite] no source_params.news_index for {cfg.get('ticker')}; skipping")
        return

    ticker = cfg.get("ticker", "")
    pattern = params["article_link_pattern"]
    exclude = params.get("link_exclude")
    site_name = params["site_name"]

    try:
        html = _fetch(index_url)
    except Exception as e:
        print(f"[companysite] fetch index failed {index_url}: {e}")
        return

    soup = BeautifulSoup(html, "lxml")
    seen_hrefs: set[str] = set()
    yielded = 0

    for a in soup.select("a[href]"):
        if yielded >= limit:
            break
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        abs_href = urljoin(index_url, href)
        if pattern not in abs_href:
            continue
        if exclude and exclude in abs_href:
            continue
        # Skip obvious non-article targets: must have some non-root path depth
        parsed = urlparse(abs_href)
        if not parsed.path or parsed.path.rstrip("/") == "":
            continue
        # The news index itself often matches the pattern (e.g. /news/).
        # Skip if the link is identical to the index URL.
        if abs_href.rstrip("/") == index_url.rstrip("/"):
            continue
        # Canonicalize
        canon = re.sub(r"[?#].*$", "", abs_href)
        if canon in seen_hrefs:
            continue

        headline = _clean(a.get_text())
        if not headline or len(headline) < 10:
            # Fall back to title attribute
            headline = _clean(a.get("title") or "")
        if not headline:
            continue
        # Skip generic "Read More" / "Read more »" link text
        if headline.lower().strip(" »›>.") in {"read more", "more", "continue reading", "learn more"}:
            continue

        seen_hrefs.add(canon)
        yield {
            "source_url": canon,
            "source_name": site_name,
            "published_at": None,  # filled in by fetch_body
            "ticker": ticker,
            "raw_headline": headline,
            # Stashed so fetch_body can apply the same selectors. Pipeline
            # hands summaries back to fetch_body without cfg, so we have to
            # carry parser config along on the summary itself.
            "_params": {
                "article_selector": params["article_selector"],
                "title_selector":   params["title_selector"],
                "date_selector":    params["date_selector"],
            },
        }
        yielded += 1


def fetch_body(summary: dict) -> dict:
    cfg_params = summary.get("_params") or {}
    # The pipeline hands summaries back to fetch_body without cfg, so re-derive
    # selectors from the URL by using defaults.
    params = {
        "article_selector": cfg_params.get("article_selector") or "article, main, .entry-content, .post-content",
        "title_selector":   cfg_params.get("title_selector") or "h1",
        "date_selector":    cfg_params.get("date_selector"),
    }

    url = summary["source_url"]
    try:
        html = _fetch(url)
    except Exception as e:
        summary["raw_body"] = ""
        summary["raw_excerpt"] = ""
        summary["fetch_error"] = str(e)
        return summary

    soup = BeautifulSoup(html, "lxml")

    # Title — prefer the article H1; fall back to the summary headline
    title_el = soup.select_one(params["title_selector"])
    if title_el:
        title = _clean(title_el.get_text())
        if title and len(title) > 5:
            summary["raw_headline"] = title

    # Date — prefer selector, then meta tags, then text regex over article
    pub = None
    if params["date_selector"]:
        de = soup.select_one(params["date_selector"])
        if de:
            pub = _parse_date(_clean(de.get_text()))
    if not pub:
        for sel in [
            ("meta", {"property": "article:published_time"}),
            ("meta", {"name": "pubdate"}),
            ("meta", {"itemprop": "datePublished"}),
            ("meta", {"name": "date"}),
        ]:
            m = soup.find(*sel)
            if m and m.get("content"):
                pub = _parse_date(m["content"])
                if pub:
                    break
    if not pub:
        t = soup.find("time")
        if t:
            pub = _parse_date(t.get("datetime") or _clean(t.get_text()))

    # Find body container
    body_el = None
    for sel in [s.strip() for s in params["article_selector"].split(",") if s.strip()]:
        body_el = soup.select_one(sel)
        if body_el:
            break

    if not body_el:
        summary["raw_body"] = ""
        summary["raw_excerpt"] = ""
        summary["raw_html"] = ""
        summary["fetch_error"] = "no body container matched"
        if pub:
            summary["published_at"] = pub
        return summary

    # Text + HTML
    raw_text = _clean(body_el.get_text(" ", strip=True))
    # Last resort for date: scan body text
    if not pub:
        m = DATE_RE.search(raw_text[:2000])
        if m:
            pub = _parse_date(m.group(1))

    raw_html = _sanitize_html(body_el, url)

    # Build a short excerpt — first ~400 chars of text
    excerpt = raw_text[:400].rsplit(" ", 1)[0] if len(raw_text) > 400 else raw_text

    summary["raw_body"] = raw_text
    summary["raw_excerpt"] = excerpt
    summary["raw_html"] = raw_html
    if pub:
        summary["published_at"] = pub
    return summary


def event_id_for(url: str, date: str | None) -> str:
    h = hashlib.sha256()
    h.update((url or "").encode("utf-8"))
    h.update(b"|")
    h.update((date or "").encode("utf-8"))
    return h.hexdigest()
