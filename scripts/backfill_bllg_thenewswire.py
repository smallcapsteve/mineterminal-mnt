#!/usr/bin/env python3
"""For each existing BLLG.CN event with empty body, find its canonical
TheNewswire URL via DuckDuckGo HTML search, fetch the body, and UPDATE
the row in place.

DuckDuckGo HTML (`html.duckduckgo.com/html/`) is preferred over Google
because it has no CAPTCHA and works fine for site-restricted queries.
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
SOURCE_NAME = "thenewswire"
UA = "Mozilla/5.0 (compatible; MNTBackfill/1.0; +mnt-relay)"
HEAD = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}


def _normalize(s: str) -> str:
    # Map smart quotes/dashes to ASCII so search engines match titles consistently.
    return (s
        .replace("\u2019", "'").replace("\u2018", "'")
        .replace("\u201c", '"').replace("\u201d", '"')
        .replace("\u2013", "-").replace("\u2014", "-")
        .replace("\u00a0", " "))


def _extract_thenewswire_url(html: str) -> str | None:
    """Find the first thenewswire.com/press-releases URL in arbitrary HTML."""
    from urllib.parse import unquote
    # Direct match
    m = re.search(r'https?://(?:www\.)?thenewswire\.com/press-releases/[^\s"<>&]+', html)
    if m:
        return m.group(0).split("#")[0].rstrip("/")
    # DDG-wrapped redirect
    m = re.search(r'uddg=([^&"]+thenewswire[^&"]+)', html)
    if m:
        return unquote(m.group(1)).split("#")[0].rstrip("/")
    # Bing wraps redirects: /a?d=... — but the target is plaintext in the result anchor
    return None


def search_thenewswire(headline: str, timeout: int = 12) -> str | None:
    """Try DDG → Bing → Brave to find the first thenewswire.com hit."""
    h = _normalize(headline).replace('"', "")
    # Trim very long titles (engines truncate; first ~120 chars is the unique part)
    h_short = h[:140].strip()

    engines = [
        ("DDG", "https://html.duckduckgo.com/html/", {"q": '"%s" site:thenewswire.com' % h_short}),
        ("Bing", "https://www.bing.com/search?q=%s" % requests.utils.quote('"%s" site:thenewswire.com' % h_short), None),
    ]
    for name, url, data in engines:
        try:
            if data:
                r = requests.post(url, data=data, headers=HEAD, timeout=timeout)
            else:
                r = requests.get(url, headers=HEAD, timeout=timeout)
            if r.status_code != 200:
                continue
            hit = _extract_thenewswire_url(r.text)
            if hit:
                return hit
        except Exception as e:
            print("    %s err: %s" % (name, e))
            continue
    return None


# Backwards-compat alias
ddg_first_thenewswire = search_thenewswire


def fetch_thenewswire_body(url: str, timeout: int = 20) -> tuple[str, str]:
    """Fetch a TheNewswire press release page, extract body HTML + text."""
    try:
        r = requests.get(url, headers=HEAD, timeout=timeout)
        if r.status_code != 200:
            return "", ""
    except Exception as e:
        print("    fetch err:", e)
        return "", ""
    soup = BeautifulSoup(r.text, "html5lib")
    # TheNewswire press release containers (common selectors):
    #   <article>
    #   <div class="press-release"> / <div class="article-body">
    candidates = []
    for sel in [
        ("div", {"class": re.compile(r"press-release|article-body|release-body|main-content", re.I)}),
        ("article", {}),
        ("main", {}),
        ("div", {"id": re.compile(r"content|main", re.I)}),
    ]:
        tag, attrs = sel
        for el in soup.find_all(tag, **attrs):
            txt = el.get_text(" ", strip=True)
            if len(txt) > 400:
                candidates.append((len(txt), el))
        if candidates:
            break
    # Fallback: largest <div> with most text
    if not candidates:
        for div in soup.find_all("div"):
            txt = div.get_text(" ", strip=True)
            if 600 < len(txt) < 80000:  # avoid the whole-page wrapper
                candidates.append((len(txt), div))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            # pick smallest above threshold (most specific)
            candidates = [candidates[0]]
    if not candidates:
        return "", ""
    candidates.sort(key=lambda x: -x[0])
    body = candidates[0][1]
    # Strip script/style/nav/aside
    for bad in body.find_all(["script", "style", "nav", "header", "footer", "aside", "form"]):
        bad.decompose()
    raw_html = str(body)
    raw_text = body.get_text("\n").strip()
    raw_text = re.sub(r"\n{3,}", "\n\n", raw_text)
    return raw_html, raw_text


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--sleep", type=float, default=2.0,
                   help="Sleep between DDG searches (be polite)")
    args = p.parse_args()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    rows = con.execute(
        "SELECT event_id, raw_headline, published_at, source_url, length(coalesce(raw_html,'')) AS h "
        "FROM events WHERE upper(ticker) IN ('BLLG.CN','BLLG') "
        "ORDER BY published_at DESC LIMIT ?", (args.limit,)
    ).fetchall()

    print("  candidate BLLG events:", len(rows))
    found = 0
    not_found = 0
    fetched = 0
    skipped = 0

    for i, r in enumerate(rows, 1):
        if r["h"] >= 1500:
            print("  [%3d] SKIP (already has body, h=%d) %s" % (i, r["h"], (r["raw_headline"] or "")[:70]))
            skipped += 1
            continue
        headline = r["raw_headline"] or ""
        if not headline or len(headline) < 20:
            print("  [%3d] SKIP (no headline)" % i)
            skipped += 1
            continue
        print("  [%3d] SEARCH %s" % (i, headline[:80]))
        url = ddg_first_thenewswire(headline)
        time.sleep(args.sleep)
        if not url:
            print("        no DDG hit on thenewswire")
            not_found += 1
            continue
        print("        URL: %s" % url[:120])
        found += 1

        nh, nt = fetch_thenewswire_body(url)
        if not nh or len(nh) < 800:
            print("        body extraction failed (h=%d)" % len(nh))
            not_found += 1
            time.sleep(0.5)
            continue
        if args.dry_run:
            print("        WOULD-UPDATE  body=%d  text=%d" % (len(nh), len(nt)))
        else:
            con.execute(
                "UPDATE events SET source_url=?, raw_html=?, raw_body=?, source_name=? WHERE event_id=?",
                (url, nh, nt, SOURCE_NAME, r["event_id"]),
            )
            con.commit()
            print("        UPDATED  body=%d  text=%d" % (len(nh), len(nt)))
            fetched += 1
        time.sleep(0.5)

    print()
    print("  SUMMARY: searched=%d  found=%d  fetched=%d  not_found=%d  skipped=%d" %
          (len(rows) - skipped, found, fetched, not_found, skipped))


if __name__ == "__main__":
    sys.exit(main() or 0)
