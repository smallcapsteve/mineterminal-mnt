#!/usr/bin/env python3
"""
rediscover_v2 — name-search-based wire discovery with verification.

For each company in cse_miners.json, search Newsfile by company name,
then for each top-candidate company_id verify by calling
sources.newsfile.list_recent() and checking headlines include a
distinctive substring of the company name.

Writes /opt/mnt/app/data/rediscover_v2_newsfile.json with:
  [
    {
      "ticker": "KBX.CN",
      "company_name": "Kobrea Exploration Corp.",
      "candidates_searched": [ {"company_id":10375, "name":"Kobrea-Exploration-Corp"}, ... ],
      "verified": {"company_id": 10375, "name": "Kobrea Exploration Corp",
                   "sample_headlines": ["..."], "release_count_last_25": 8},
      "status": "verified" | "search_no_match" | "no_releases" | "name_mismatch"
    },
    ...
  ]

Rate limit: Newsfile says 8 searches/minute. We pace to 6/min with jitter.
"""
from __future__ import annotations
import json
import re


class RateLimited(Exception):
    pass

import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

import httpx

# Local adapter (for verification via list_recent)
sys.path.insert(0, "/opt/mnt/app")
from sources import newsfile  # noqa: E402

DATA_DIR = Path("/opt/mnt/app/data")
OUTPUT = DATA_DIR / "rediscover_v2_newsfile.json"
PROGRESS = DATA_DIR / "rediscover_v2_progress.json"
CSE = DATA_DIR / "cse_miners.json"
TICKERS_ACTIVE = Path("/opt/mnt/app/tickers.json")
TICKERS_DISCOVERED = Path("/opt/mnt/app/tickers.discovered.json")

BASE = "https://www.newsfilecorp.com"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

SEARCH_DELAY_S = 15.0  # => ~5.7/min, under 8/min limit
VERIFY_DELAY_S = 1.0

# Companies that appear in EVERY search result (generic/infra). Always skip.
GENERIC_COMPANY_IDS = {
    5318,   # Canadian Securities Exchange (CSE)
    7397,   # The Rosen Law Firm PA
    11802,  # The Canadian Depository for Securities Limited (CDS Ltd)
    10895,  # New Orleans Investment Conference
    690,    # Austral Gold (shows up as generic hit)
    10569,  # HealthPlus Staffing
    10984,  # StoneCo Ltd
    12354,  # Vitelize Health
    5460,   # Pacific Ridge Exploration (frequent false hit)
}

# Stop words to drop when building a search query / name-match token
STOPWORDS = {
    "corp", "corporation", "inc", "incorporated", "ltd", "limited",
    "co", "company", "holdings", "holding", "resources", "resource",
    "mining", "minerals", "metals", "the", "and", "&",
}


@dataclass
class Result:
    ticker: str
    company_name: str
    search_query: str = ""
    candidates: list = field(default_factory=list)
    verified: dict | None = None
    status: str = "pending"
    note: str = ""


def _norm_token(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _distinctive_tokens(name: str) -> list[str]:
    """Return distinctive tokens we'll match against headline text."""
    raw = re.sub(r"[^\w\s]+", " ", name)
    toks = [t.lower() for t in raw.split() if t]
    toks = [t for t in toks if t not in STOPWORDS and len(t) > 2]
    return toks or [_norm_token(name)]


def _search_query_for(name: str) -> str:
    """Build a search query -- use most distinctive words, drop generic ones."""
    toks = _distinctive_tokens(name)
    # Limit to first 3 tokens to avoid over-specific queries
    return " ".join(toks[:3])


SEARCH_LINK_RE = re.compile(
    r'href="(/company/(\d+)/([A-Za-z0-9.\-]+))(?:/?"[^>]*)', re.I
)


def newsfile_search(query: str, client: httpx.Client) -> list[tuple[int, str]]:
    """Search Newsfile, return [(company_id, slug_name), ...] unique, in order."""
    q = query.replace(" ", "+")
    url = f"{BASE}/search?k={q}"
    try:
        r = client.get(url, timeout=20, follow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        return []
    html = r.text
    # Rate-limit guard (bounded backoff, then raise)
    if "limited to 8 per minute" in html:
        raise RateLimited("newsfile 8/min hit")

    seen = set()
    out: list[tuple[int, str]] = []
    for m in SEARCH_LINK_RE.finditer(html):
        cid = int(m.group(2))
        slug = m.group(3)
        if cid in seen or cid in GENERIC_COMPANY_IDS:
            continue
        seen.add(cid)
        out.append((cid, slug))
    return out


def _slug_to_pretty(slug: str) -> str:
    return slug.replace("-", " ")


def _name_match(company_name: str, slug: str, headlines: list[str]) -> bool:
    """Decide if a candidate matches the expected company based on slug + headlines.

    We require at least one distinctive token (>3 chars, non-stopword) of
    company_name to appear in either slug or any headline.
    """
    tokens = _distinctive_tokens(company_name)
    if not tokens:
        return False
    hay = (_norm_token(slug) + " ".join(_norm_token(h) for h in headlines)).lower()
    hits = sum(1 for t in tokens[:4] if _norm_token(t) in hay)
    return hits >= 1  # lenient: one distinctive token match


def verify_candidate(cid: int, slug: str, company_name: str, ticker: str) -> dict | None:
    """Call newsfile.list_recent for this cid. Return a verified dict or None."""
    cfg = {"ticker": ticker, "source_params": {"company_id": cid}}
    try:
        items = list(newsfile.list_recent(cfg, limit=5))
    except Exception as e:
        return {"error": f"list_recent raised: {e}"}
    if not items:
        return {"company_id": cid, "slug": slug, "release_count": 0,
                "sample_headlines": [], "matched": False,
                "reason": "no_releases_via_list_recent"}
    headlines = [it.get("raw_headline") or "" for it in items]
    matched = _name_match(company_name, slug, headlines)
    return {
        "company_id": cid,
        "slug": slug,
        "release_count": len(items),
        "sample_headlines": headlines[:3],
        "matched": matched,
        "reason": "name_token_matched" if matched else "name_mismatch",
    }


def load_progress() -> dict:
    if PROGRESS.exists():
        try:
            return json.loads(PROGRESS.read_text())
        except Exception:
            pass
    return {"done_tickers": [], "results": []}


def save_progress(state: dict) -> None:
    PROGRESS.write_text(json.dumps(state, indent=2))


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="process only the first N uncompleted tickers (0 = all)")
    ap.add_argument("--reset", action="store_true", help="start over")
    args = ap.parse_args(argv)

    cse = json.loads(CSE.read_text())
    # Skip already-active tickers and explicitly-excluded discovered ones.
    active_tickers = {t["ticker"] for t in json.loads(TICKERS_ACTIVE.read_text())}
    discovered = json.loads(TICKERS_DISCOVERED.read_text())
    excluded = {d["ticker"] for d in discovered if d.get("exclude_auto")}

    if args.reset and PROGRESS.exists():
        PROGRESS.unlink()
    state = load_progress()
    done = set(state["done_tickers"])

    targets = [c for c in cse
               if c.get("ticker") not in active_tickers
               and c.get("ticker") not in excluded
               and c.get("ticker") not in done]
    if args.limit:
        targets = targets[:args.limit]

    print(f"[v2] {len(targets)} targets to process "
          f"(active={len(active_tickers)} excluded={len(excluded)} done={len(done)})",
          flush=True)

    headers = {"User-Agent": UA, "Accept-Language": "en-CA,en;q=0.9"}
    with httpx.Client(headers=headers, timeout=25, follow_redirects=True) as client:
        for idx, comp in enumerate(targets, 1):
            ticker = comp["ticker"]
            name = comp.get("name") or comp.get("company_name") or ticker
            q = _search_query_for(name)
            r = Result(ticker=ticker, company_name=name, search_query=q)

            # bounded retry on rate-limit
            _backoffs = [30, 120, 300]
            cands = None
            rl_hits = 0
            gave_up_rl = False
            for _delay in _backoffs + [None]:
                try:
                    cands = newsfile_search(q, client)
                    break
                except RateLimited:
                    rl_hits += 1
                    if _delay is None:
                        gave_up_rl = True
                        break
                    print(f"[rate-limit] attempt {rl_hits} on {ticker}; sleeping {_delay}s", flush=True)
                    time.sleep(_delay)
                except Exception as e:
                    r.status = "search_error"
                    r.note = str(e)
                    state["results"].append(asdict(r))
                    state["done_tickers"].append(ticker)
                    save_progress(state)
                    cands = None
                    break
            if gave_up_rl:
                # don't mark ticker done; just record and move on with long cooldown
                r.status = "rate_limited"
                r.note = f"gave up after {rl_hits} rl hits"
                state["results"].append(asdict(r))
                save_progress(state)
                print(f"[rate-limit] giving up on {ticker}; cooling down 10 min", flush=True)
                time.sleep(600)
                continue
            if cands is None:
                # error path already handled
                continue

            r.candidates = [{"company_id": cid, "slug": slug} for cid, slug in cands[:5]]

            # Try top candidates, take first that verifies
            verified = None
            for cid, slug in cands[:4]:
                time.sleep(VERIFY_DELAY_S)
                v = verify_candidate(cid, slug, name, ticker)
                if v and v.get("matched"):
                    verified = v
                    break

            if verified:
                r.verified = verified
                r.status = "verified"
            elif cands:
                r.status = "candidates_but_no_match"
                r.note = "searched returned candidates but none verified by headline"
            else:
                r.status = "search_no_match"

            state["results"].append(asdict(r))
            state["done_tickers"].append(ticker)
            if idx % 5 == 0:
                save_progress(state)
                print(f"[v2] {idx}/{len(targets)} last={ticker} status={r.status}", flush=True)

            time.sleep(SEARCH_DELAY_S)

    save_progress(state)

    # Also write clean output -- verified records only, in a promote-ready shape
    verified_records = []
    for res in state["results"]:
        if res.get("status") == "verified" and res.get("verified"):
            v = res["verified"]
            verified_records.append({
                "ticker": res["ticker"],
                "company_id": v["company_id"].split(".")[0] if isinstance(v["company_id"], str) else res["ticker"].split(".")[0],
                "name": res["company_name"],
                "source": "newsfile",
                "source_params": {"company_id": v["company_id"]},
                "discovery_confidence": "v2_verified_by_headline_match",
                "release_count_probe": v.get("release_count"),
                "sample_headlines": v.get("sample_headlines", [])[:2],
            })
    OUTPUT.write_text(json.dumps(verified_records, indent=2, ensure_ascii=False))
    print(f"[v2] DONE. verified={len(verified_records)} "
          f"total_processed={len(state['done_tickers'])}", flush=True)

    # Summary
    from collections import Counter
    by_status = Counter(r["status"] for r in state["results"])
    print("[v2] status breakdown:")
    for k, v in sorted(by_status.items(), key=lambda kv: -kv[1]):
        print(f"   {k:30s} {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
