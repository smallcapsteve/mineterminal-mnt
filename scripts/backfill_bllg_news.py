#!/usr/bin/env python3
"""One-off backfill: fetch Blue Lagoon's /news/feed/ RSS (100 items) and ingest
each press release into the MNT events DB.

Uses the existing events schema. Computes event_id deterministically from
source_url so re-runs are idempotent.
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
COMPANY = "Blue Lagoon Resources Inc."
RSS_URL = "https://bluelagoonresources.com/news/feed/"
SOURCE_NAME = "company_ir_rss"
UA = "Mozilla/5.0 (compatible; MNTBackfill/1.0; +mnt-relay)"
HEAD = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}


def to_iso(rfc822: str) -> str:
    """RSS pubDate (e.g. 'Fri, 17 Apr 2026 14:33:21 +0000') -> ISO."""
    if not rfc822:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(rfc822)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "")
    except Exception:
        return ""


def slug_from_url(url: str) -> str:
    m = re.search(r"/news/([^/?#]+)", url or "")
    return m.group(1) if m else ""


def event_id(url: str) -> str:
    return hashlib.sha256((url or "").encode("utf-8")).hexdigest()


def parse_rss(text: str) -> list[dict]:
    """Parse RSS feed using stdlib ElementTree (XML-safe)."""
    import xml.etree.ElementTree as ET
    NS = {"content": "http://purl.org/rss/1.0/modules/content/",
          "dc": "http://purl.org/dc/elements/1.1/"}
    items = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        print(f"    XML parse err: {e}")
        return items
    # rss/channel/item
    for it in root.iter("item"):
        def _t(tag, ns=None):
            if ns:
                el = it.find(f"{{{ns}}}{tag}")
            else:
                el = it.find(tag)
            return (el.text or "").strip() if (el is not None and el.text) else ""
        items.append({
            "title": _t("title"),
            "link": _t("link"),
            "pubdate": _t("pubDate"),
            "description": _t("description"),
            "content": _t("encoded", NS["content"]),
        })
    return items


def fetch_article_body(url: str) -> tuple[str, str]:
    """Fetch single press release page, extract body HTML + text.
    Returns (raw_html, raw_body_text)."""
    try:
        r = requests.get(url, headers=HEAD, timeout=20)
        if r.status_code != 200:
            return "", ""
    except Exception as e:
        print(f"    fetch err: {e}")
        return "", ""
    soup = BeautifulSoup(r.text, "html5lib")
    # Typical WP: <div class="entry-content">, <article>, <div class="post-content">
    candidates = []
    for sel in [
        ("div", {"class": re.compile(r"entry-content|post-content|article-content|content-wrap", re.I)}),
        ("article", {}),
        ("div", {"class": re.compile(r"single-post|post-body", re.I)}),
        ("main", {}),
    ]:
        tag, attrs = sel
        for el in soup.find_all(tag, **attrs):
            txt = el.get_text(" ", strip=True)
            if len(txt) > 200:
                candidates.append((len(txt), el))
        if candidates:
            break
    if not candidates:
        return "", ""
    # pick the largest
    candidates.sort(key=lambda x: -x[0])
    body = candidates[0][1]
    # Strip script/style/nav
    for bad in body.find_all(["script", "style", "nav", "header", "footer", "aside"]):
        bad.decompose()
    raw_html = str(body)
    raw_text = body.get_text("\n").strip()
    raw_text = re.sub(r"\n{3,}", "\n\n", raw_text)
    return raw_html, raw_text


def main():
    # 1. fetch RSS
    print(f"  fetching {RSS_URL}")
    r = requests.get(RSS_URL, headers=HEAD, timeout=20)
    r.raise_for_status()
    items = parse_rss(r.text)
    print(f"  parsed {len(items)} items from RSS")

    # 2. open DB
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    inserted, updated, skipped = 0, 0, 0
    for i, it in enumerate(items, 1):
        url = it["link"]
        title = it["title"]
        if not url or not title:
            skipped += 1
            continue
        ev = event_id(url)
        slug = slug_from_url(url)
        published = to_iso(it["pubdate"])

        existing = con.execute("SELECT length(coalesce(raw_html,'')) AS h FROM events WHERE event_id=?", (ev,)).fetchone()
        if existing and existing["h"] >= 1500:
            skipped += 1
            print(f"  [{i:>3d}] SKIP (already have)  {title[:80]}")
            continue

        # 3. fetch body
        print(f"  [{i:>3d}] FETCH {url[:90]}")
        raw_html, raw_body = fetch_article_body(url)
        if not raw_html:
            # fall back to RSS content:encoded
            raw_html = it.get("content") or ""
            raw_body = re.sub(r"<[^>]+>", " ", raw_html).strip()
        if not raw_html:
            print(f"          (no body — using description)")
            raw_html = "<p>" + (it.get("description") or "").strip() + "</p>"
            raw_body = re.sub(r"<[^>]+>", " ", raw_html).strip()

        row = {
            "event_id": ev,
            "event_type": "news_release",
            "ticker": TICKER,
            "company_id": "BLLG",
            "property_id": None,
            "source_url": url,
            "source_name": SOURCE_NAME,
            "published_at": published,
            "classified_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", ""),
            "classifier_model": "backfill",
            "classifier_confidence": 1.0,
            "review_status": "auto_approved",
            "raw_headline": title,
            "raw_excerpt": (it.get("description") or "")[:500],
            "raw_body": raw_body,
            "raw_html": raw_html,
            "payload_json": json.dumps({"source": "bllg_backfill", "rss": RSS_URL}),
            "categories": "",
            "slug": slug,
        }

        if existing:
            con.execute(
                "UPDATE events SET raw_html=?, raw_body=?, raw_headline=?, published_at=?, slug=?, source_name=?, review_status=? WHERE event_id=?",
                (raw_html, raw_body, title, published, slug, SOURCE_NAME, "auto_approved", ev),
            )
            updated += 1
            print(f"          UPDATED  body={len(raw_html):,}b text={len(raw_body):,}c")
        else:
            cols = ",".join(row.keys())
            placeholders = ",".join(["?"] * len(row))
            con.execute(f"INSERT OR IGNORE INTO events ({cols}) VALUES ({placeholders})", tuple(row.values()))
            inserted += 1
            print(f"          INSERTED body={len(raw_html):,}b text={len(raw_body):,}c")

        con.commit()
        time.sleep(0.5)  # be polite

    print()
    print(f"  SUMMARY: inserted={inserted}  updated={updated}  skipped={skipped}  total={len(items)}")


if __name__ == "__main__":
    sys.exit(main() or 0)
