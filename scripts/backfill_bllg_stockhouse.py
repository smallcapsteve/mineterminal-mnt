#!/usr/bin/env python3
"""Backfill BLLG bodies from Stockhouse press-release pages.

Stockhouse aggregates wire releases (TheNewswire etc.) and serves the
full text in their own HTML — even though they don't link out, the body
content IS in their rendered article pages.

Strategy:
  1. Walk paginated /companies/news?symbol=c.bllg listings, harvest all
     /news/press-releases/YYYY/MM/DD/{slug} URLs.
  2. For each, GET the article page, extract the article body region.
  3. Match against existing BLLG events by headline overlap; UPDATE
     source_url, raw_html, raw_body, source_name. INSERT a new row if
     no match found.
"""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

DB = "/opt/mnt/app/portal/portal.db"
TICKER = "BLLG.CN"
SOURCE_NAME = "stockhouse"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
HEAD = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}

LISTING_URL_PATTERN = "https://stockhouse.com/companies/news?symbol=c.bllg&page={n}"
ARTICLE_URL_RE = re.compile(r"/news/press-releases/(\d{4})/(\d{2})/(\d{2})/[a-z0-9\-]+")


def _abs(path: str) -> str:
    if path.startswith("http"):
        return path
    return "https://stockhouse.com" + path


def harvest_listing_urls(max_pages: int = 12) -> list[str]:
    urls = []
    seen = set()
    for n in range(1, max_pages + 1):
        try:
            r = requests.get(LISTING_URL_PATTERN.format(n=n), headers=HEAD, timeout=15)
            if r.status_code != 200:
                break
        except Exception as e:
            print("    listing err: %s" % e)
            break
        before = len(seen)
        for m in ARTICLE_URL_RE.findall(r.text):
            # Need full match too
            pass
        for m in re.finditer(r"/news/press-releases/\d{4}/\d{2}/\d{2}/[a-z0-9\-]+", r.text):
            path = m.group(0)
            full = _abs(path)
            if full not in seen:
                seen.add(full)
                urls.append(full)
        added = len(seen) - before
        print("  page %d: +%d (total %d)" % (n, added, len(seen)))
        if added == 0:
            break
        time.sleep(1.0)
    return urls


def fetch_article_body(url: str, timeout: int = 20) -> tuple[str, str, str]:
    """Returns (headline, body_html, body_text)."""
    try:
        r = requests.get(url, headers=HEAD, timeout=timeout)
        if r.status_code != 200:
            return "", "", ""
    except Exception as e:
        print("    fetch err:", e)
        return "", "", ""
    soup = BeautifulSoup(r.text, "html5lib")
    # Title from <h1> or <title>
    h1 = soup.find("h1")
    headline = h1.get_text(" ", strip=True) if h1 else (soup.title.get_text() if soup.title else "")
    # Strip the date prefix that Stockhouse adds to <title>
    headline = re.sub(r"^\d{4}-\d{2}-\d{2}\s*\|\s*", "", headline)
    headline = re.sub(r"\s*\|\s*[CSE\.A-Z:]+\s*\|\s*Press Release.*$", "", headline)
    headline = headline.strip()

    # Body: stockhouse wraps the press release in a container — try several selectors
    candidates = []
    for sel in [
        ("div", {"class": re.compile(r"article-body|press-release-body|news-body|article__body|main-content", re.I)}),
        ("article", {}),
        ("section", {"class": re.compile(r"article|content", re.I)}),
        ("main", {}),
    ]:
        tag, attrs = sel
        for el in soup.find_all(tag, **attrs):
            txt = el.get_text(" ", strip=True)
            if len(txt) > 1000:
                candidates.append((len(txt), el))
        if candidates:
            break
    if not candidates:
        # Fallback: walk all div/section, pick the densest text block in middle of page
        for el in soup.find_all(["div", "section"]):
            txt = el.get_text(" ", strip=True)
            if 1500 < len(txt) < 60000:
                candidates.append((len(txt), el))
    if not candidates:
        return headline, "", ""
    candidates.sort(key=lambda x: -x[0])
    body = candidates[0][1]
    # Strip nav, footer, comment areas, recommended widgets, stock-screen ads
    for bad in body.find_all(["script", "style", "nav", "header", "footer", "aside", "form", "iframe", "noscript"]):
        bad.decompose()
    # Strip common Stockhouse chrome by class
    for div in body.find_all(True, class_=re.compile(r"comment|sidebar|related|recommend|breadcrumb|share|cookie|advert|cta|banner", re.I)):
        div.decompose()
    raw_html = str(body)
    raw_text = body.get_text("\n").strip()
    raw_text = re.sub(r"\n{3,}", "\n\n", raw_text)
    # Trim Stockhouse cookie banner that often leaks into innerText
    for prefix in ("Stockhouse.com uses cookies",):
        idx = raw_text.find("\nC.BLLG")
        if idx > 0:
            raw_text = raw_text[idx:].strip()
            break
    return headline, raw_html, raw_text


def slug_tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def match_event_id(con: sqlite3.Connection, headline: str) -> str | None:
    target = slug_tokens(headline)
    if len(target) < 4:
        return None
    rows = con.execute(
        "SELECT event_id, raw_headline, length(coalesce(raw_html,'')) AS h "
        "FROM events WHERE upper(ticker) IN ('BLLG.CN','BLLG')"
    ).fetchall()
    best = None
    best_score = 0
    for r in rows:
        ht = slug_tokens(r["raw_headline"])
        common = target & ht
        score = len(common)
        if score > best_score:
            best_score = score
            best = r
    if best and best_score >= 5:
        return best["event_id"]
    return None


def main():
    print("== harvesting Stockhouse BLLG listings ==")
    urls = harvest_listing_urls(max_pages=12)
    print("  total unique article URLs: %d" % len(urls))
    print()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    matched, inserted, failed, skipped_short = 0, 0, 0, 0
    for i, url in enumerate(urls, 1):
        print("[%3d] %s" % (i, url[-90:]))
        headline, raw_html, raw_text = fetch_article_body(url)
        if not raw_html or len(raw_html) < 1500:
            print("     FAILED extract (h=%d)" % len(raw_html))
            failed += 1
            time.sleep(0.5)
            continue
        ev = match_event_id(con, headline)
        if ev:
            # Don't overwrite if existing has a longer body (e.g., from TheNewswire backfill)
            existing = con.execute("SELECT length(coalesce(raw_html,'')) AS h FROM events WHERE event_id=?", (ev,)).fetchone()
            if existing and existing["h"] >= len(raw_html):
                print("     SKIP (existing body longer: %d >= %d)" % (existing["h"], len(raw_html)))
                skipped_short += 1
                time.sleep(0.7)
                continue
            con.execute(
                "UPDATE events SET source_url=?, raw_html=?, raw_body=?, source_name=?, review_status='auto_approved' WHERE event_id=?",
                (url, raw_html, raw_text, SOURCE_NAME, ev),
            )
            con.commit()
            matched += 1
            print("     MATCHED ev=%s body=%d" % (ev[:14], len(raw_html)))
        else:
            new_ev = hashlib.sha256(url.encode("utf-8")).hexdigest()
            slug_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/([a-z0-9\-]+)", url)
            published = ""
            if slug_match:
                published = "%s-%s-%sT12:00:00" % (slug_match.group(1), slug_match.group(2), slug_match.group(3))
            try:
                con.execute(
                    "INSERT OR IGNORE INTO events (event_id, event_type, ticker, company_id, source_url, "
                    "source_name, published_at, classified_at, classifier_model, classifier_confidence, "
                    "review_status, raw_headline, raw_excerpt, raw_body, raw_html, payload_json, slug) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (new_ev, "news_release", TICKER, "BLLG", url, SOURCE_NAME, published,
                     datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", ""),
                     "backfill", 1.0, "auto_approved", headline, "", raw_text, raw_html,
                     json.dumps({"source": "stockhouse_backfill"}),
                     (slug_match.group(4) if slug_match else "")),
                )
                con.commit()
                inserted += 1
                print("     INSERTED-NEW body=%d" % len(raw_html))
            except Exception as e:
                print("     INSERT err:", e)
                failed += 1
        time.sleep(0.7)

    print()
    print("  SUMMARY: fetched=%d matched-update=%d inserted-new=%d failed=%d skipped(longer-existing)=%d" %
          (len(urls), matched, inserted, failed, skipped_short))


if __name__ == "__main__":
    sys.exit(main() or 0)
