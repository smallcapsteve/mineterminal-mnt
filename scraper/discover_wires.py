#!/usr/bin/env python3
"""
Wire-service discovery for CSE mining companies.

For each company in data/cse_miners.json, tries to figure out which press
release distribution wire they use (Newsfile, GlobeNewswire, CNW/Cision,
AccessWire, Businesswire, or self-hosted).

Strategy:
  1. Fetch company.website root
  2. Find links whose anchor text or path looks like a news/press page
     (e.g. /news, /press, /media, /investors)
  3. Follow up to 2 such pages, collect outgoing URLs
  4. Count hits per wire domain. Pick the top hit.
  5. Also try searching for wire-identifier URL patterns embedded on the
     root page itself (newsfilecorp.com/company/NNNN is a strong tell).

Writes data/company_sources.json — list of
  {"ticker","name","website","press_source","wire_company_id","press_url",
   "evidence":[url,...], "note": str}

Meant to be re-runnable; skips network errors gracefully.
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
INPUT_FILE = DATA / "cse_miners.json"
OUTPUT_FILE = DATA / "company_sources.json"

WIRE_DOMAINS = {
    "newsfile":      re.compile(r"newsfilecorp\.com", re.I),
    "globenewswire": re.compile(r"globenewswire\.com", re.I),
    "cnw":           re.compile(r"(?:prnewswire\.com|newswire\.ca)", re.I),
    "accesswire":    re.compile(r"accesswire\.com", re.I),
    "businesswire":  re.compile(r"businesswire\.com", re.I),
    "stockhouse":    re.compile(r"stockhouse\.com", re.I),
    "sedar":         re.compile(r"sedarplus\.ca", re.I),
}

NEWS_HINTS = re.compile(
    r"\b(news|press|release|media|investor|announcement)\b", re.I
)

NEWSFILE_COMPANY = re.compile(
    r"newsfilecorp\.com/(?:company|release)/(\d+)", re.I
)

UA = ("Mozilla/5.0 (compatible; MNT-WireDiscovery/1.0; "
      "+https://miningnewstracker.local)")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "en-CA,en;q=0.9"})

TIMEOUT = 12


def _get(url: str) -> str | None:
    try:
        r = SESSION.get(url, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code >= 400:
            return None
        ct = r.headers.get("Content-Type", "")
        if "text" not in ct and "html" not in ct:
            return None
        return r.text[:500_000]  # cap each page
    except Exception:
        return None


def _candidate_news_urls(root_url: str, html: str) -> list[str]:
    """Return up to ~8 links on the page that look news/press/investor-ish."""
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[str] = []
    base = root_url
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        full = urljoin(base, href)
        # keep same host OR jump to a known wire — both useful
        text = (a.get_text() or "")[:80]
        hay = f"{href} {text}"
        if NEWS_HINTS.search(hay) or any(rx.search(hay) for rx in WIRE_DOMAINS.values()):
            if full not in seen:
                seen.add(full)
                out.append(full)
                if len(out) >= 8:
                    break
    return out


def _wire_hits(html: str) -> dict[str, int]:
    hits: dict[str, int] = {}
    for name, rx in WIRE_DOMAINS.items():
        n = len(rx.findall(html))
        if n:
            hits[name] = n
    return hits


def _newsfile_company_id(html: str) -> str | None:
    m = NEWSFILE_COMPANY.search(html)
    return m.group(1) if m else None


def discover_one(company: dict) -> dict:
    ticker = company.get("ticker", "")
    name = company.get("name", "")
    website = (company.get("website") or "").strip()
    out = {
        "ticker": ticker,
        "name": name,
        "website": website,
        "press_source": None,
        "wire_company_id": None,
        "press_url": None,
        "evidence": [],
        "note": "",
    }
    if not website:
        out["note"] = "no_website"
        return out

    # normalize
    if not website.startswith("http"):
        website = "https://" + website

    root_html = _get(website)
    if not root_html:
        out["note"] = "root_fetch_failed"
        return out

    all_hits: dict[str, int] = dict(_wire_hits(root_html))
    evidence: list[str] = []
    nf_id = _newsfile_company_id(root_html)
    if nf_id:
        evidence.append(f"newsfile_id_on_root:{nf_id}")
        out["wire_company_id"] = nf_id

    # Explore up to 2 news-ish subpages
    subs = _candidate_news_urls(website, root_html)[:2]
    for sub in subs:
        sub_html = _get(sub)
        if not sub_html:
            continue
        evidence.append(sub)
        sub_hits = _wire_hits(sub_html)
        for k, v in sub_hits.items():
            all_hits[k] = all_hits.get(k, 0) + v
        if not out["wire_company_id"]:
            nf_id2 = _newsfile_company_id(sub_html)
            if nf_id2:
                out["wire_company_id"] = nf_id2
                evidence.append(f"newsfile_id_on_sub:{nf_id2}")
        # set a press_url — prefer the subpage that had hits or looks canonical
        if not out["press_url"] and (sub_hits or NEWS_HINTS.search(sub)):
            out["press_url"] = sub

    out["evidence"] = evidence[:10]

    if all_hits:
        # pick the wire with the most hits; tie-break by preferred order
        order = ["newsfile", "globenewswire", "cnw", "accesswire",
                 "businesswire", "stockhouse", "sedar"]
        best = max(all_hits.items(),
                   key=lambda kv: (kv[1], -order.index(kv[0]) if kv[0] in order else 0))
        out["press_source"] = best[0]
        out["note"] = f"hits={all_hits}"
    else:
        out["note"] = "no_wire_detected"

    return out


def main(concurrency: int = 16) -> None:
    companies = json.loads(INPUT_FILE.read_text())
    print(f"[discover] {len(companies)} companies, concurrency={concurrency}", file=sys.stderr)

    results: list[dict] = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = {pool.submit(discover_one, c): c for c in companies}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                r = fut.result()
            except Exception as e:
                c = futs[fut]
                r = {
                    "ticker": c.get("ticker", ""),
                    "name": c.get("name", ""),
                    "website": c.get("website", ""),
                    "press_source": None,
                    "wire_company_id": None,
                    "press_url": None,
                    "evidence": [],
                    "note": f"exception:{type(e).__name__}",
                }
            results.append(r)
            if i % 25 == 0 or i == len(companies):
                elapsed = time.time() - started
                print(f"[discover] {i}/{len(companies)} "
                      f"({elapsed:.0f}s)", file=sys.stderr)

    # keep ticker order
    ticker_order = {c.get("ticker"): idx for idx, c in enumerate(companies)}
    results.sort(key=lambda r: ticker_order.get(r["ticker"], 999999))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    # summary
    by_source: dict[str, int] = {}
    for r in results:
        s = r["press_source"] or "(none)"
        by_source[s] = by_source.get(s, 0) + 1
    print("[discover] done:", file=sys.stderr)
    for s, n in sorted(by_source.items(), key=lambda kv: -kv[1]):
        print(f"  {s:15s} {n:3d}", file=sys.stderr)


if __name__ == "__main__":
    main()
