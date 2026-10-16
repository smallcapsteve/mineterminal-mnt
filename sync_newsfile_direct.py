#!/usr/bin/env python3
"""sync_newsfile_direct.py - direct Newsfile (TMX Newsfile) mining collector. NFDIRECT_V1, 2026-10-16.

Justin, 2026-10-16: "Yes please build and test a direct newsfile collector". Newsfile is the busiest mining wire, but
sync_newsfile.py finds its releases through Google News, which surfaces only a handful a day; most Newsfile releases
reached MNT the next morning through the TMX/CSE exchange collector instead, dated with a 12:00 placeholder (findings:
claude/MNT_MEMSWAP_FINDINGS_2026-10-15.md, "Correction").

Newsfile publishes official RSS feeds per industry (the last 10 releases each). The newsfilecorp.com list pages sit
behind an AWS WAF challenge for the server, but the feeds and the individual release pages (GET) answer normally
(checked 2026-10-16, relay payloads nfdirect/probe1.sh, probe2.sh). So, every run:
  1. read the metals feeds below (title, link, pubDate with its Eastern offset);
  2. skip releases already handled (data/seen_newsfile_direct.json, keyed by Newsfile's release number);
  3. open the release page with sources/newsfile.fetch_body (the per-company Newsfile collector's body reader and
     sanitizer), take the ticker from the dateline ("(TSXV: ABC)"; a Canadian listing first);
  4. if MNT already shows the same release (same Newsfile release number, or the same company within 3 days with
     the headline / opening-text rule sync_newswire_ca uses), skip it;
  5. otherwise POST it to the portal's /ingest webhook - the same path sync_newswire_ca uses - so the portal's quality
     gate, duplicate guard, categorisation, auto-onboard and coverage-list (universe) gate all apply.
A release whose page cannot be read is retried on later runs (up to MAX_TRIES), not marked seen.

Pacing (dry run 1, 2026-10-16): Newsfile's WAF answers "202 challenge, empty body" once a few pages are read in quick
succession, and lifts after about two minutes. So each run reads at most PAGE_BUDGET release pages, PAGE_GAP seconds
apart, and stops reading pages for the run at the first empty answer. A release is never stored without its text.

Run:
  python3 sync_newsfile_direct.py               live run (timer)
  python3 sync_newsfile_direct.py --dry-run     read feeds + pages + MNT read-only; print what it would do; write nothing
  python3 sync_newsfile_direct.py --test-urls URL [URL ...]   same as dry run, for given release pages
  python3 sync_newsfile_direct.py --self-test   offline parser tests
Source-name: newsfile (the same as the per-company Newsfile adapter).
"""
from __future__ import annotations

import email.utils
import hashlib
import html as _html
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, "/opt/mnt/app")

FEEDS = [
    "https://feeds.newsfilecorp.com/industry/mining-metals",
    "https://feeds.newsfilecorp.com/industry/precious-metals",
    "https://feeds.newsfilecorp.com/industry/non-ferrous-metals",
]
UA = "Mozilla/5.0 (compatible; MNT-newsfile-direct/1.0; +https://miningnewsterminal.com)"
PORTAL_DB = os.environ.get("PORTAL_DB", "/opt/mnt/app/portal/portal.db")
SEEN_FILE = Path(os.environ.get("NFDIRECT_SEEN", "/opt/mnt/app/data/seen_newsfile_direct.json"))
MAX_TRIES = 12         # a release page that cannot be read is retried on this many runs (about 2 h at 10-min runs)
PAGE_BUDGET = int(os.environ.get("NFDIRECT_PAGE_BUDGET", "3"))    # release pages read per run
PAGE_GAP = float(os.environ.get("NFDIRECT_PAGE_GAP", "20"))       # seconds between release-page reads
TWIN_DAYS = 3
MAX_AGE_DAYS = 4       # ignore feed items older than this (a feed only holds the last 10 anyway)
TIMEOUT = 25

# "(TSXV: ABC)", "(TSX-V: ABC)", "(TSX VENTURE: ABC)", "(CSE: ABC)", "(TSX: ABC)", "(NEO: ABC)", "(Cboe Canada: ABC)"
_CAN_RE = re.compile(
    r"\(\s*(TSX[\s\-.]?V(?:enture)?(?:\s+Exchange)?|TSX(?:\s+Venture(?:\s+Exchange)?)?|CSE|CNSX|CNQ|NEO|Cboe\s+Canada)"
    r"\s*[:\-]\s*([A-Z][A-Z0-9]{0,6}(?:\.[A-Z]{1,2})?)\s*[,;)]",
    re.I)
_SUFFIX = {"V": ".V", "TO": ".TO", "CN": ".CN", "NE": ".NE"}
_RID_RE = re.compile(r"/release/(\d+)(?:/|$)")


# ------------------------------------------------------------------ parsing (pure, self-tested)
def exchange_suffix(ex: str) -> str:
    e = re.sub(r"[\s\-.]+", "", ex.upper())
    if e.startswith("TSXV") or "VENTURE" in e:
        return "V"
    if e == "TSX":
        return "TO"
    if e in ("CSE", "CNSX", "CNQ"):
        return "CN"
    if e in ("NEO", "CBOECANADA"):
        return "NE"
    return ""


def extract_ticker(text: str):
    """First Canadian listing in the release's opening text -> ('ABC.V', 'TSXV') or (None, None)."""
    for m in _CAN_RE.finditer((text or "")[:3000]):
        suf = exchange_suffix(m.group(1))
        if not suf:
            continue
        sym = m.group(2).upper()
        # "ABC.U" (US-dollar line) -> keep as is; a symbol that already carries the suffix is left alone
        tk = sym if sym.endswith(_SUFFIX[suf]) else sym + _SUFFIX[suf]
        ex = {"V": "TSXV", "TO": "TSX", "CN": "CSE", "NE": "NEO"}[suf]
        return tk, ex
    return None, None


def pubdate_utc(s: str):
    """RSS pubDate 'Fri, 16 Oct 2026 07:30:00 -0400' -> '2026-10-16T11:30:00Z' (UTC with a Z, like the other wires)."""
    try:
        d = email.utils.parsedate_to_datetime((s or "").strip())
    except (TypeError, ValueError, IndexError):
        return None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone(timedelta(hours=-4)))
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def release_id(url: str):
    m = _RID_RE.search(url or "")
    return m.group(1) if m else None


def parse_feed(xml_bytes: bytes):
    """[{rid, url, headline, published_at, teaser}] from a Newsfile RSS 2.0 feed."""
    out = []
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        url = (it.findtext("link") or it.findtext("guid") or "").strip()
        rid = release_id(url)
        if not rid:
            continue
        url = re.sub(r"[?#].*$", "", url)
        desc = re.sub(r"<[^>]+>", " ", _html.unescape(it.findtext("description") or ""))
        out.append({"rid": rid, "url": url, "headline": _html.unescape((it.findtext("title") or "").strip()),
                    "published_at": pubdate_utc(it.findtext("pubDate") or ""),
                    "teaser": re.sub(r"\s+", " ", desc).strip()})
    return out


# ------------------------------------------------------------------ MNT side (read-only)
_ro_con = None


def _ro():
    global _ro_con
    if _ro_con is None:
        _ro_con = sqlite3.connect(f"file:{PORTAL_DB}?mode=ro", uri=True, timeout=60)
        _ro_con.execute("PRAGMA busy_timeout=30000")
    return _ro_con


def already_on_mnt(ticker, headline, body, published, rid):
    """(event_id, why) of a release MNT already holds that is this one, else (None, None). Indexed lookups only:
    the ticker (and its base symbol) within TWIN_DAYS of the release date."""
    import sync_newswire_ca as NW   # same_release() and its tokeniser: the rule the newswire.ca collector uses
    base = (ticker or "").split(".")[0].upper()
    if not base or not published:
        return None, None
    d = datetime.fromisoformat(published[:10])
    lo = (d - timedelta(days=TWIN_DAYS)).strftime("%Y-%m-%d")
    hi = (d + timedelta(days=TWIN_DAYS + 1)).strftime("%Y-%m-%d")
    t1 = NW._nw_toks((body or "")[:2500])
    for eid, h2, b2, url2, st in _ro().execute(
            "SELECT event_id, raw_headline, substr(COALESCE(raw_body,''),1,2500), COALESCE(source_url,''), review_status "
            "FROM events WHERE (ticker = ? OR ticker LIKE ?) AND published_at >= ? AND published_at < ?",
            (base, base + ".%", lo, hi)):
        if rid and f"/release/{rid}/" in url2 + "/":
            return eid, "same Newsfile release (%s)" % st
        if st in ("auto_approved", "pending_review") and NW.same_release(headline, t1, h2 or "", NW._nw_toks(b2)):
            return eid, "same release from another source (%s)" % st
    return None, None


# ------------------------------------------------------------------ network
def fetch_feed(url: str) -> bytes:
    import requests
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


def read_release(item: dict) -> dict:
    """sources/newsfile.fetch_body on the release page; adds raw_body / raw_html / raw_excerpt / ticker."""
    from sources import newsfile as NF
    s = {"source_url": item["url"], "published_at": item["published_at"], "raw_headline": item["headline"]}
    s = NF.fetch_body(s)
    body = s.get("raw_body") or ""
    tk, ex = extract_ticker(body)
    if not tk:
        tk, ex = extract_ticker(item.get("teaser") or "")
    s.update(ticker=tk, exchange=ex, published_at=item["published_at"] or s.get("published_at"))
    return s


def event_id_for(url: str) -> str:
    return hashlib.sha256(("newsfile:" + url).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ seen state
def load_seen() -> dict:
    try:
        v = json.loads(SEEN_FILE.read_text())
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def save_seen(seen: dict) -> None:
    keep = dict(sorted(seen.items(), key=lambda kv: int(kv[0]))[-6000:])
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SEEN_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(keep, sort_keys=True))
    os.replace(tmp, SEEN_FILE)


# ------------------------------------------------------------------ run
def handle(item: dict, apply: bool, seen: dict, counts: dict) -> str:
    """'' normally; 'blocked' when the release page came back empty (the WAF), so the run stops reading pages."""
    import sync_newswire_ca as NW
    rid = item["rid"]
    tag = f"{rid} {item['headline'][:70]}"
    if NW.NON_MINING_HINTS.search(item["headline"]):
        counts["non_mining"] += 1
        print(f"  - non-mining  {tag}", flush=True)
        seen[rid] = {"st": "non_mining"}
        return ""
    counts["pages_read"] += 1
    try:
        s = read_release(item)
    except Exception as e:  # noqa: BLE001
        s = {"fetch_error": f"{type(e).__name__}: {e}"}
    body = s.get("raw_body") or ""
    if s.get("fetch_error") or len(body) < 200:
        tries = int((seen.get(rid) or {}).get("tries", 0)) + 1
        counts["page_unreadable"] += 1
        print(f"  ! unreadable ({s.get('fetch_error') or 'body %d chars' % len(body)}; try {tries}/{MAX_TRIES}) {tag}",
              flush=True)
        seen[rid] = {"st": "gave_up" if tries >= MAX_TRIES else "retry", "tries": tries}
        return "blocked"
    tk = s.get("ticker")
    if not tk:
        counts["no_ticker"] += 1
        print(f"  - no Canadian ticker  {tag}", flush=True)
        seen[rid] = {"st": "no_ticker"}
        return ""
    try:
        twin, why = already_on_mnt(tk, item["headline"], body, item["published_at"], rid)
    except Exception as e:  # noqa: BLE001 - if the check fails, do not risk a duplicate: retry next run
        counts["check_failed"] += 1
        print(f"  ! duplicate check failed ({type(e).__name__}: {e}); will retry  {tag}", flush=True)
        return ""
    if twin:
        counts["already_on_mnt"] += 1
        print(f"  = {tk:10s} already on MNT as {twin[:12]} ({why})  {tag}", flush=True)
        seen[rid] = {"st": "on_mnt", "event": twin[:12]}
        return ""
    env = {
        "event_id": event_id_for(item["url"]),
        "event_type": "news_release",
        "ticker": tk,
        "source_name": "newsfile",
        "source_url": item["url"],
        "raw_headline": item["headline"][:500],
        "raw_excerpt": (s.get("raw_excerpt") or body)[:1500],
        "raw_body": body[:50000],
        "raw_html": (s.get("raw_html") or "")[:200000],
        "published_at": item["published_at"] or NW._now_utc(),
        "categories": ["news"],
        "_exchange": s.get("exchange"),
        "_cfg_website": item["url"],
        "_source_name": "newsfile",
        "review_status": "auto_approved",
        "classifier_model": "newsfile_direct_v1",
        "classifier_confidence": 0.85,
    }
    if not apply:
        counts["would_ingest"] += 1
        print(f"  + WOULD INGEST {tk:10s} {item['published_at']}  body {len(body)} chars  {tag}", flush=True)
        return ""
    code = NW.post_to_ingest(env)
    if code in (200, 201, 202):
        counts["ingested"] += 1
        seen[rid] = {"st": "ingested", "code": code}
        print(f"  + {tk:10s} {item['published_at']}  {tag}", flush=True)
    else:
        counts["post_failed"] += 1
        tries = int((seen.get(rid) or {}).get("tries", 0)) + 1
        seen[rid] = {"st": "gave_up" if tries >= MAX_TRIES else "retry", "tries": tries, "code": code}
        print(f"  X HTTP {code} (try {tries}/{MAX_TRIES})  {tag}", flush=True)
    return ""


def run(apply: bool, items=None) -> int:
    seen = load_seen()
    counts = {k: 0 for k in ("feed_items", "new", "ingested", "would_ingest", "already_on_mnt", "no_ticker",
                             "non_mining", "page_unreadable", "check_failed", "post_failed", "too_old", "feed_errors",
                             "pages_read", "left_for_next_run")}
    if items is None:
        items, ids = [], set()
        for f in FEEDS:
            try:
                got = parse_feed(fetch_feed(f))
            except Exception as e:  # noqa: BLE001
                counts["feed_errors"] += 1
                print(f"[newsfile_direct] FEED FAIL {f}: {type(e).__name__}: {e}", flush=True)
                continue
            print(f"[newsfile_direct] {f} -> {len(got)} items", flush=True)
            for it in got:
                if it["rid"] not in ids:
                    ids.add(it["rid"])
                    items.append(it)
    counts["feed_items"] = len(items)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    stop = False
    for it in sorted(items, key=lambda x: x.get("published_at") or ""):
        st = (seen.get(it["rid"]) or {}).get("st")
        if apply and st and st != "retry":
            continue
        if it.get("published_at") and it["published_at"] < cutoff:
            counts["too_old"] += 1
            continue
        counts["new"] += 1
        if stop or counts["pages_read"] >= PAGE_BUDGET:
            counts["left_for_next_run"] += 1
            continue
        if counts["pages_read"]:
            time.sleep(PAGE_GAP)
        if handle(it, apply, seen, counts) == "blocked":
            stop = True
    if apply:
        save_seen(seen)
    print("[newsfile_direct] %s  %s" % ("DONE" if apply else "DRY RUN (nothing written)",
                                         "  ".join(f"{k}={v}" for k, v in counts.items())), flush=True)
    return 0


def _test_urls(urls) -> int:
    items = []
    for u in urls:
        rid = release_id(u)
        if not rid:
            print(f"not a Newsfile release URL: {u}")
            continue
        items.append({"rid": rid, "url": re.sub(r"[?#].*$", "", u), "headline": "", "published_at": None, "teaser": ""})
    from sources import newsfile as NF
    for n, it in enumerate(items):   # headline and date from the page itself when testing a bare URL
        if n:
            time.sleep(PAGE_GAP)
        s = NF.fetch_body({"source_url": it["url"], "published_at": None, "raw_headline": ""})
        it["headline"] = s.get("raw_headline") or ""
        p = s.get("published_at")
        it["published_at"] = (datetime.fromisoformat(p).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                              if p else None)
    return run(apply=False, items=items)


def _self_test() -> int:
    bad = 0

    def ok(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print(f"FAIL {name}: got {got!r} want {want!r}")

    ok("tsxv", extract_ticker("VANCOUVER, BC (Newsfile Corp.) - Acme Gold Corp. (TSXV: ACM) (OTCQB: ACMGF) is"), ("ACM.V", "TSXV"))
    ok("tsx-v", extract_ticker("Acme (TSX-V: ACM) (FSE: 1A2)"), ("ACM.V", "TSXV"))
    ok("venture", extract_ticker("Acme (TSX Venture Exchange: ACM)"), ("ACM.V", "TSXV"))
    ok("tsx", extract_ticker("Big Mines Inc. (TSX: BIG) (NYSE: BIG)"), ("BIG.TO", "TSX"))
    ok("cse", extract_ticker("Small Co (CSE: SML) (OTC: SMLLF)"), ("SML.CN", "CSE"))
    ok("otc first, cse second", extract_ticker("X (OTCQB: XXXF) (CSE: XX)"), ("XX.CN", "CSE"))
    ok("comma list", extract_ticker("Acme (TSXV: ACM, OTCQB: ACMGF)"), ("ACM.V", "TSXV"))
    ok("none", extract_ticker("Acme (OTCQB: ACMGF) only"), (None, None))
    ok("pub edt", pubdate_utc("Fri, 16 Oct 2026 07:30:00 -0400"), "2026-10-16T11:30:00Z")
    ok("pub est", pubdate_utc("Mon, 12 Jan 2026 08:00:00 -0500"), "2026-01-12T13:00:00Z")
    ok("pub bad", pubdate_utc("yesterday"), None)
    ok("rid", release_id("https://www.newsfilecorp.com/release/319322/Bravada-Gold-Files-PEA"), "319322")
    feed = (b'<?xml version="1.0" ?><rss version="2.0"><channel><item><title>Bravada Gold Files PEA &amp; More</title>'
            b'<link>https://www.newsfilecorp.com/release/319322/Bravada-Gold-Files-PEA?x=1</link>'
            b'<description>&lt;img src="x" /&gt;Vancouver--(Newsfile Corp. - October 16, 2026) - Bravada (TSXV: BVA)'
            b'</description><pubDate>Fri, 16 Oct 2026 07:30:00 -0400</pubDate></item></channel></rss>')
    it = parse_feed(feed)
    ok("feed n", len(it), 1)
    ok("feed fields", (it[0]["rid"], it[0]["url"], it[0]["headline"], it[0]["published_at"]),
       ("319322", "https://www.newsfilecorp.com/release/319322/Bravada-Gold-Files-PEA", "Bravada Gold Files PEA & More",
        "2026-10-16T11:30:00Z"))
    ok("teaser ticker", extract_ticker(it[0]["teaser"]), ("BVA.V", "TSXV"))
    print(f"self-test: {'all ok' if not bad else str(bad) + ' FAILED'}")
    return 1 if bad else 0


def main() -> int:
    a = sys.argv[1:]
    if a[:1] == ["--self-test"]:
        return _self_test()
    if a[:1] == ["--test-urls"]:
        return _test_urls(a[1:])
    return run(apply="--dry-run" not in a)


if __name__ == "__main__":
    sys.exit(main())
