#!/usr/bin/env python3
"""Backfill BLLG with full press-release bodies from TheNewswire.

Uses a curated list of TheNewswire URLs (collected via Google site:search).
For each URL: fetch HTML, extract article body, match against existing BLLG
event in MNT by headline similarity, UPDATE that row's source_url, raw_html,
raw_body, source_name.

Falls back to INSERTing a new row if no match found.
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

# Confirmed BLLG TheNewswire URLs from Google site:search
URLS = [
    "https://www.thenewswire.com/press-releases/1AMqFavVb-blue-lagoon-resources-forms-mining-committee-to-oversee-transition-to-production.html",
    "https://www.thenewswire.com/press-releases/1AdyF4O9R-blue-lagoon-engages-hillside-media-for-corporate-awareness-digital-marketing.html",
    "https://www.thenewswire.com/press-releases/1AlpFDo4y-blue-lagoon-s-underground-production-ramps-up.html",
    "https://www.thenewswire.com/press-releases/1AlpFvovQ-blue-lagoon-secures-2-million-line-of-credit-from-nicola-mining-enhancing-financial-flexibility-ahead-of-production.html",
    "https://www.thenewswire.com/press-releases/1AqRF0g31-blue-lagoon-announces-commissioning-of-mbbr-water-treatment-system-and-start-of-underground-operations-at-dome-mountain.html",
    "https://www.thenewswire.com/press-releases/1ArbFmRDX-blue-lagoon-announces-major-steps-toward-production-fully-funded-government-inspections-passed-and-water-treatment-plant-completed.html",
    "https://www.thenewswire.com/press-releases/1BNMFVdlw-blue-lagoon-resources-officially-opens-dome-mountain-gold-mine-in-british-columbia.html",
    "https://www.thenewswire.com/press-releases/1BNMF1joV-blue-lagoon-closes-final-tranche-of-financing-fully-funded-to-commence-production.html",
    "https://www.thenewswire.com/press-releases/1BQPFEmGp-blue-lagoon-resources-completes-second-sale-of-1-4-million-of-dome-mountain-mineralized-material-milling-now-underway.html",
    "https://www.thenewswire.com/press-releases/1BglFbJdv-blue-lagoon-reaches-100-tonnes-per-day-milestone-doubles-production-crew-with-second-mining-contractor-and-advances-toward-150-tonnes-per-day.html",
    "https://www.thenewswire.com/press-releases/1BglFox12-blue-lagoon-receives-final-mine-permits-for-its-dome-mountain-gold-project-in-british-columbia-poised-to-become-bcs-next-gold-producer.html",
    "https://www.thenewswire.com/press-releases/1Bz4FlzYE-blue-lagoon-delivers-1-000-tonnes-to-milling-partner-processing-expected-to-begin-by-week-s-end.html",
    "https://www.thenewswire.com/press-releases/1Bz4FYEXW-blue-lagoon-extends-milling-agreement-with-nicola-mining-to-10-years-securing-long-term-processing-of-dome-mountain-mineralized-material.html",
    "https://www.thenewswire.com/press-releases/1LaPFZV7Q-blue-lagoon-adds-second-underground-shift-as-dome-mountain-moves-into-higher-throughput-phase.html",
    "https://www.thenewswire.com/press-releases/1LmPFdoya-message-from-the-president-ceo-of-blue-lagoon-resources.html",
    "https://www.thenewswire.com/press-releases/1k1vFOodY-blue-lagoon-marks-one-year-anniversary-of-mining-permit-receipt-as-gold-silver-price-outlook-strengthens-and-operational-milestones-accelerate.html",
    "https://www.thenewswire.com/press-releases/1k1vFlvEN-blue-lagoon-receives-first-delivery-of-blasting-material-at-dome-mountain-underground-mining-commences.html",
    "https://www.thenewswire.com/press-releases/1k49F4jlo-blue-lagoon-milling-partner-nicola-mining-shifts-focus-exclusively-to-blue-lagoon-s-gold-silver-mineralized-material.html",
    "https://www.thenewswire.com/press-releases/1k98Feajy-blue-lagoon-resources-wins-prestigious-2026-pdac-sustainability-award.html",
    "https://www.thenewswire.com/press-releases/1kVGFnDyp-blue-lagoon-sells-c-1-million-of-gold-and-silver-from-dome-mountain-s-initial-production-to-ocean-partners.html",
    "https://www.thenewswire.com/press-releases/1kWVFjX56-blue-lagoon-resources-president-s-update.html",
    "https://www.thenewswire.com/press-releases/1kogFw1pb-blue-lagoon-resources-strengthens-mining-committee.html",
]


def fetch_thenewswire_body(url: str, timeout: int = 20) -> tuple[str, str]:
    try:
        r = requests.get(url, headers=HEAD, timeout=timeout)
        if r.status_code != 200:
            print("    fetch http=%d" % r.status_code)
            return "", ""
    except Exception as e:
        print("    fetch err:", e)
        return "", ""
    soup = BeautifulSoup(r.text, "html5lib")
    # TheNewswire content typically lives in <article> or div.press-release-body / .pr-body
    candidates = []
    for sel in [
        ("div", {"class": re.compile(r"press-release|pr-body|release-body|article-body|content-area", re.I)}),
        ("article", {}),
        ("main", {}),
    ]:
        tag, attrs = sel
        for el in soup.find_all(tag, **attrs):
            txt = el.get_text(" ", strip=True)
            if len(txt) > 400:
                candidates.append((len(txt), el))
        if candidates:
            break
    # Fallback: largest body div
    if not candidates:
        body = soup.find("body")
        if body:
            for div in body.find_all("div", recursive=True):
                txt = div.get_text(" ", strip=True)
                if 800 < len(txt) < 60000:
                    candidates.append((len(txt), div))
    if not candidates:
        return "", ""
    candidates.sort(key=lambda x: -x[0])
    body = candidates[0][1]
    for bad in body.find_all(["script", "style", "nav", "header", "footer", "aside", "form", "iframe"]):
        bad.decompose()
    raw_html = str(body)
    raw_text = body.get_text("\n").strip()
    raw_text = re.sub(r"\n{3,}", "\n\n", raw_text)
    return raw_html, raw_text


def extract_headline_from_url(url: str) -> str:
    """Extract a normalized headline-fragment from URL slug for fuzzy match."""
    m = re.search(r"/press-releases/[A-Za-z0-9]+-([a-z0-9\-]+)\.html", url)
    if not m:
        return ""
    slug = m.group(1)
    # First ~6 word-tokens of the slug, joined with spaces
    words = slug.split("-")[:8]
    return " ".join(words).lower()


def slug_tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def match_event_id(con: sqlite3.Connection, url: str) -> str | None:
    """Find the BLLG event whose headline overlaps most with this URL slug."""
    target = slug_tokens(extract_headline_from_url(url))
    if not target:
        return None
    rows = con.execute(
        "SELECT event_id, raw_headline FROM events WHERE upper(ticker) IN ('BLLG.CN','BLLG')"
    ).fetchall()
    best = None
    best_score = 0
    for r in rows:
        ht = slug_tokens(r["raw_headline"])
        common = target & ht
        score = len(common)
        if score > best_score:
            best_score = score
            best = r["event_id"]
    if best_score >= 4:
        return best
    return None


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    print("  candidates: %d URLs" % len(URLS))

    fetched = 0
    matched = 0
    inserted = 0
    failed = 0

    for i, url in enumerate(URLS, 1):
        print("[%2d] %s" % (i, url[-90:]))
        nh, nt = fetch_thenewswire_body(url)
        if not nh or len(nh) < 800:
            print("     FAILED body extraction (h=%d)" % len(nh))
            failed += 1
            time.sleep(1.0)
            continue
        fetched += 1
        ev = match_event_id(con, url)
        if ev:
            con.execute(
                "UPDATE events SET source_url=?, raw_html=?, raw_body=?, source_name=?, review_status='auto_approved' WHERE event_id=?",
                (url, nh, nt, SOURCE_NAME, ev),
            )
            con.commit()
            matched += 1
            print("     MATCHED event=%s body=%d text=%d" % (ev[:14], len(nh), len(nt)))
        else:
            # Insert fresh
            new_ev = hashlib.sha256(url.encode("utf-8")).hexdigest()
            slug = re.search(r"/press-releases/[A-Za-z0-9]+-([a-z0-9\-]+)\.html", url)
            slug_str = slug.group(1) if slug else ""
            # Headline guess: derive from slug
            headline = " ".join(w.capitalize() for w in slug_str.split("-"))[:200]
            row = (
                new_ev, "news_release", TICKER, "BLLG", None, url, SOURCE_NAME,
                "", datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", ""),
                "backfill", 1.0, "auto_approved", headline, "", nt, nh,
                json.dumps({"source": "bllg_thenewswire_backfill_v2"}), "", slug_str,
            )
            try:
                con.execute(
                    "INSERT OR IGNORE INTO events (event_id, event_type, ticker, company_id, property_id, "
                    "source_url, source_name, published_at, classified_at, classifier_model, "
                    "classifier_confidence, review_status, raw_headline, raw_excerpt, raw_body, "
                    "raw_html, payload_json, categories, slug) VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    row,
                )
                con.commit()
                inserted += 1
                print("     INSERTED-NEW body=%d text=%d slug=%s" % (len(nh), len(nt), slug_str[:50]))
            except Exception as e:
                print("     INSERT err:", e)
                failed += 1
        time.sleep(0.8)

    print()
    print("  SUMMARY: fetched=%d matched-update=%d new-insert=%d failed=%d" %
          (fetched, matched, inserted, failed))


if __name__ == "__main__":
    sys.exit(main() or 0)
