"""
Wire-service rediscovery.

For each ticker in tickers.all.json:
  1. Fetch the company's website (homepage + common news paths)
  2. Extract outbound links that match known wire services:
       - newsfilecorp.com/release/NNN   -> newsfile (company_id from release page)
       - newsfilecorp.com/company/NNN   -> newsfile (direct)
       - accesswire.com/newsroom?SymbolName=... -> accesswire
       - accesswire.com/viewarticle.aspx?id=... -> accesswire
       - globenewswire.com/news-release/...  -> globenewswire
       - newswire.ca/news-releases/...  -> cnw/cision
  3. For newsfile, follow a release URL to extract its company_id.
  4. Validate the discovered company_id by fetching /company/{id}/ and
     confirming >= 1 release link.
  5. Write validated mappings to tickers.discovered.json; fall back to
     keeping the existing selfhosted entry if nothing discovered.

Concurrency: ThreadPoolExecutor(max_workers=20) — 300 companies / ~10s each.
"""
from __future__ import annotations
import json, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
TIMEOUT = 15

SRC = Path("/opt/mnt/app/tickers.all.json")
DST = Path("/opt/mnt/app/tickers.discovered.json")
LOG = Path("/opt/mnt/app/data/logs/rediscover.log")

NEWS_PATHS = [
    "", "news", "news/", "press", "press/",
    "press-releases", "press-releases/",
    "news-releases", "news-releases/",
    "investors", "investors/news", "investors/news-releases",
    "media", "media/news",
    "en/news", "en/press-releases",
]

RE_NF_RELEASE = re.compile(r"newsfilecorp\.com/release/(\d+)", re.I)
RE_NF_COMPANY = re.compile(r"newsfilecorp\.com/company/(\d+)", re.I)
RE_AW_NEWSROOM = re.compile(
    r"accesswire\.com/newsroom\??[^\s\"']*?SymbolName=([A-Za-z0-9.\-]+)",
    re.I,
)
RE_AW_SLUG = re.compile(r"accesswire\.com/([A-Za-z0-9\-]+)/news", re.I)
RE_GNW = re.compile(r"globenewswire\.com/(?:en/)?news-release/", re.I)
RE_GNW_ORG = re.compile(r"globenewswire\.com/(?:organization|search/organization)/([^/\"\s]+)", re.I)
RE_CNW = re.compile(r"newswire\.ca/(?:en/)?news-releases/", re.I)
RE_CNW_ORG = re.compile(
    r"newswire\.ca/(?:en/)?news-releases/([a-z0-9\-]+-[0-9]{6,})", re.I,
)


def fetch(url: str) -> str | None:
    try:
        with httpx.Client(
            headers=HEADERS, timeout=TIMEOUT, follow_redirects=True, verify=False
        ) as c:
            r = c.get(url)
            if r.status_code != 200:
                return None
            return r.text
    except Exception:
        return None


def log(msg: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(msg + "\n")


def newsfile_company_from_release(release_id: str) -> int | None:
    """Follow a newsfile release URL and extract the company_id from its page."""
    html = fetch(f"https://www.newsfilecorp.com/release/{release_id}")
    if not html:
        return None
    m = RE_NF_COMPANY.search(html)
    if m:
        return int(m.group(1))
    return None


def validate_newsfile(cid: int) -> int:
    """Return release count on /company/{cid}/ page (0 if invalid)."""
    html = fetch(f"https://www.newsfilecorp.com/company/{cid}/")
    if not html:
        return 0
    hits = set(RE_NF_RELEASE.findall(html))
    return len(hits)


def discover_one(entry: dict) -> dict:
    """Return an updated ticker entry with best-known source mapping."""
    ticker = entry["ticker"]
    name = entry.get("name", "")
    website = (entry.get("source_params") or {}).get("website") or ""
    if not website:
        return {**entry, "discovery_status": "no_website"}

    # Collect candidate links from homepage + a few news paths
    candidates: list[str] = []
    seen_urls: set[str] = set()
    for path in ["", "news", "news/", "press", "press/",
                 "press-releases", "press-releases/",
                 "news-releases", "news-releases/", "investors"]:
        url = urljoin(website.rstrip("/") + "/", path)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        html = fetch(url)
        if not html:
            continue
        # newsfile
        for rid in RE_NF_RELEASE.findall(html):
            candidates.append(("newsfile_release", rid))
        for cid in RE_NF_COMPANY.findall(html):
            candidates.append(("newsfile_company", cid))
        # accesswire
        for sym in RE_AW_NEWSROOM.findall(html):
            candidates.append(("accesswire_sym", sym))
        for slug in RE_AW_SLUG.findall(html):
            candidates.append(("accesswire_slug", slug))
        # globenewswire
        for org in RE_GNW_ORG.findall(html):
            candidates.append(("gnw_org", org))
        if RE_GNW.search(html):
            candidates.append(("gnw_hit", ""))
        # cnw
        for org in RE_CNW_ORG.findall(html):
            candidates.append(("cnw_org", org))
        if RE_CNW.search(html):
            candidates.append(("cnw_hit", ""))
        # Enough evidence already — stop crawling paths
        if len(candidates) >= 3:
            break
        time.sleep(0.2)

    # Prioritize newsfile > accesswire > cnw > globenewswire
    # -- newsfile
    nf_cids: list[int] = []
    for kind, val in candidates:
        if kind == "newsfile_company":
            nf_cids.append(int(val))
    if not nf_cids:
        for kind, val in candidates:
            if kind == "newsfile_release":
                cid = newsfile_company_from_release(val)
                if cid:
                    nf_cids.append(cid)
                    break
    for cid in nf_cids:
        count = validate_newsfile(cid)
        if count > 0:
            return {
                "ticker": ticker,
                "company_id": entry.get("company_id") or ticker.split(".")[0],
                "name": name,
                "source": "newsfile",
                "source_params": {"company_id": cid},
                "discovery_status": f"newsfile_validated_{count}",
            }

    # -- accesswire
    for kind, val in candidates:
        if kind == "accesswire_sym":
            return {
                "ticker": ticker,
                "company_id": entry.get("company_id") or ticker.split(".")[0],
                "name": name,
                "source": "accesswire",
                "source_params": {"symbol_name": val},
                "discovery_status": "accesswire_sym_unvalidated",
            }
        if kind == "accesswire_slug":
            return {
                "ticker": ticker,
                "company_id": entry.get("company_id") or ticker.split(".")[0],
                "name": name,
                "source": "accesswire",
                "source_params": {"slug": val},
                "discovery_status": "accesswire_slug_unvalidated",
            }

    # -- cnw / cision
    for kind, val in candidates:
        if kind in ("cnw_org", "cnw_hit"):
            return {
                "ticker": ticker,
                "company_id": entry.get("company_id") or ticker.split(".")[0],
                "name": name,
                "source": "cnw",
                "source_params": {"organization_url": website},
                "discovery_status": "cnw_detected",
            }

    # -- globenewswire
    for kind, val in candidates:
        if kind == "gnw_org":
            return {
                "ticker": ticker,
                "company_id": entry.get("company_id") or ticker.split(".")[0],
                "name": name,
                "source": "globenewswire",
                "source_params": {"organization": val},
                "discovery_status": "gnw_org_detected",
            }
        if kind == "gnw_hit":
            return {
                "ticker": ticker,
                "company_id": entry.get("company_id") or ticker.split(".")[0],
                "name": name,
                "source": "globenewswire",
                "source_params": {"ticker": ticker},
                "discovery_status": "gnw_hit_detected",
            }

    # Fallback: keep selfhosted but record any news_urls we probed successfully
    return {
        "ticker": ticker,
        "company_id": entry.get("company_id") or ticker.split(".")[0],
        "name": name,
        "source": "selfhosted",
        "source_params": {"website": website},
        "discovery_status": "no_wire_found",
    }


def main():
    entries = json.loads(SRC.read_text())
    print(f"rediscovering {len(entries)} tickers with 20 workers", flush=True)
    results: list[dict] = []
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = {ex.submit(discover_one, e): e for e in entries}
        for i, fut in enumerate(as_completed(futs), 1):
            e = futs[fut]
            try:
                res = fut.result()
            except Exception as err:
                res = {**e, "discovery_status": f"error:{err}"}
            results.append(res)
            if i % 10 == 0 or i == len(entries):
                elapsed = time.time() - t0
                print(
                    f"[{i}/{len(entries)}] t={elapsed:.0f}s "
                    f"{res['ticker']} -> {res.get('source')} ({res.get('discovery_status')})",
                    flush=True,
                )

    # Stable order by ticker
    results.sort(key=lambda r: r.get("ticker", ""))
    DST.write_text(json.dumps(results, indent=2))

    # Summary
    from collections import Counter
    by_src = Counter(r.get("source") for r in results)
    by_status = Counter(r.get("discovery_status") for r in results)
    print(f"\nwrote {DST}")
    print(f"by source: {dict(by_src)}")
    print(f"by status: {dict(by_status)}")


if __name__ == "__main__":
    main()
