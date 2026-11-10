"""thenewswire_wire — TheNewswire master RSS firehose, mining-only.

Reads https://www.thenewswire.com/rss (rolling ~60 items), classifies each
release as mining or not, extracts the primary Canadian ticker, and yields
event summaries.

Mining classification (strict):
  Tier 1: ticker already in tickers.json AND that ticker is currently active
          for mining ingestion → mining
  Tier 2: heavy mining keyword density in the body (≥ 4 distinct mining
          keywords, none of the negative keywords dominant) → mining
  Otherwise → skipped.

Ticker extraction: scans body for Canadian exchange tags in priority order:
  CSE > TSXV > TSX. First hit wins.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import html as _html
import re
from typing import Iterator, Iterable
from xml.etree import ElementTree as ET

import httpx

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
WIRE_URL = "https://www.thenewswire.com/rss"

# ---------- ticker extraction ----------

# Canadian exchange tags. Order = priority for picking the canonical ticker.
# CSE first, then TSXV (variants), then TSX (rarer for juniors).
_TICKER_RES = [
    ("CN",  re.compile(r"\(\s*CSE\s*[:\-]\s*([A-Z][A-Z0-9.]{0,7})\s*\)", re.I)),
    ("V",   re.compile(r"\(\s*(?:TSX[\.\-]?V|TSX\s*Venture|TSX-Venture)\s*[:\-]\s*([A-Z][A-Z0-9.]{0,7})\s*\)", re.I)),
    ("TO",  re.compile(r"\(\s*TSX\s*[:\-]\s*([A-Z][A-Z0-9.]{0,7})\s*\)", re.I)),
]


def extract_ticker(text: str) -> tuple[str | None, str | None]:
    """Return (suffixed_ticker, exchange) from the body. e.g. ('SCM.CN', 'CSE')."""
    for suffix, rx in _TICKER_RES:
        m = rx.search(text or "")
        if m:
            t = m.group(1).upper()
            ex = {"CN": "CSE", "V": "TSXV", "TO": "TSX"}[suffix]
            return f"{t}.{suffix}", ex
    return None, None


# ---------- mining classification ----------

_POS_KEYWORDS = {
    # Materials
    "gold", "silver", "copper", "zinc", "nickel", "lithium", "cobalt",
    "uranium", "graphite", "manganese", "tungsten", "molybdenum", "vanadium",
    "platinum", "palladium", "rare earth", "rare-earth", "ree", "antimony",
    "tin", "lead", "iron ore", "potash", "phosphate", "tellurium", "tantalum",
    "scandium", "niobium", "germanium", "gallium",
    # Activities
    "drilling", "drill program", "drill hole", "drilling program",
    "drill core", "drilled", "drill results", "drill target",
    "exploration", "explorer", "exploring",
    "assay", "assayed", "assays", "metallurgical", "metallurgy",
    "mineralization", "mineralized", "mineral resource",
    "mineral", "mineralogy",
    "deposit", "ore body", "orebody", "ore deposit", "stockpile",
    "mine", "mining", "miner", "mined",
    "open pit", "underground mine", "shaft",
    "tonnes", "g/t", "ppm", "ounces of", "kilograms of",
    "claim", "mining claim", "mineral claim", "stake", "staking",
    "geophysical", "geochemical", "trenching", "soil sampling",
    "ni 43-101", "ni43-101", "43-101",
    "feasibility study", "preliminary economic assessment", "pea ",
    "resource estimate", "indicated resource", "inferred resource", "measured resource",
    "concentrate", "tailings", "smelter",
    "royalty", "earn-in", "joint venture", "jv ",  # less specific, lower weight
    "claims package", "exploration target",
}

# Negative keywords that suggest NON-mining (and dominate if seen)
_NEG_KEYWORDS = {
    "manufacturing", "manufactures", "pharmaceutical", "biotech",
    "biopharm", "drug development", "clinical trial",
    "ai corp", "saas", "software-as-a-service", "fintech",
    "cannabis", "psychedelic",
    "the globe and mail", "editorial", "opinion piece",
    "financial services", "asset management firm",
    "real estate investment trust", "reit ",
    "blockchain", "cryptocurrency", "crypto-asset",
}


def _kw_count(text: str, kws: Iterable[str]) -> int:
    """Distinct keyword matches in text (not counts; uniqueness)."""
    if not text:
        return 0
    t = text.lower()
    n = 0
    for k in kws:
        if k in t:
            n += 1
    return n


def is_mining(headline: str, body: str, *, known_mining_tickers: set[str] | None = None,
              ticker: str | None = None) -> tuple[bool, str]:
    """Return (is_mining, reason)."""
    if ticker and known_mining_tickers and ticker in known_mining_tickers:
        return True, "known-mining-ticker"
    text = (headline or "") + "\n" + (body or "")
    if not text.strip():
        return False, "empty"
    pos = _kw_count(text, _POS_KEYWORDS)
    neg = _kw_count(text, _NEG_KEYWORDS)
    if neg >= 2 and pos < 5:
        return False, f"non-mining (neg={neg}, pos={pos})"
    if pos >= 4:
        return True, f"mining-keywords (pos={pos}, neg={neg})"
    return False, f"insufficient signal (pos={pos}, neg={neg})"


# ---------- RSS fetch + parsing ----------

_RFC822_FMTS = [
    "%a, %d %b %Y %H:%M:%S %Z",
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S",
    "%d %b %Y %H:%M:%S %Z",
    "%d %b %Y %H:%M:%S %z",
]
_TZ_OFFSETS = {
    # MDT, MST, EDT, EST, PDT, PST, ADT, AST, etc. (RFC 822 named zones)
    "GMT": 0, "UTC": 0,
    "EST": -5, "EDT": -4, "CST": -6, "CDT": -5,
    "MST": -7, "MDT": -6, "PST": -8, "PDT": -7,
    "AST": -4, "ADT": -3, "NST": -3.5, "NDT": -2.5,
}


def _parse_rfc822(s: str) -> str | None:
    if not s:
        return None
    s = s.strip()
    # Replace named TZ with numeric offset for strict %z parsing
    m = re.search(r"\b([A-Z]{2,4})$", s)
    if m and m.group(1) in _TZ_OFFSETS:
        off = _TZ_OFFSETS[m.group(1)]
        sign = "+" if off >= 0 else "-"
        h = int(abs(off))
        mn = int(round((abs(off) - h) * 60))
        s2 = s[:m.start()] + f"{sign}{h:02d}{mn:02d}"
    else:
        s2 = s
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%d %b %Y %H:%M:%S %z"):
        try:
            d = dt.datetime.strptime(s2, fmt)
            return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return None


def _strip_html(html_text: str) -> str:
    """Decode entities + strip tags, collapse whitespace."""
    if not html_text:
        return ""
    text = _html.unescape(html_text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _event_id(url: str, published_at: str | None) -> str:
    h = hashlib.sha256()
    h.update((url or "").encode())
    h.update(b"|")
    h.update((published_at or "").encode())
    return h.hexdigest()


_TNWTICK_LISTED: dict = {}
_TNWTICK_SUFFIX = {"inc", "corp", "corporation", "ltd", "limited", "plc", "co", "company", "the"}


def _tnwtick_words(s: str) -> list:
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in _TNWTICK_SUFFIX]


def _relaxed_ticker(title: str, body: str):
    """TNWTICK_V1 (2026-11-10): extract_ticker() wants a lone "(CSE: ABC)". Releases that write
    "(TSXV: NAM; OTCQX: NMTLF)" or "(CSE: CEXY | OTCQB: CEXYF)" got no ticker and were dropped although they were in the
    feed. Read such datelines with the shared reader (wireticker, WIRETICK_V1) and keep the ticker only when that exact
    ticker is on the coverage list and the headline starts with that same company's name (the shared name test, or the
    first two words of that company's listed name, for names made of common words such as "Silver North"), so a release
    is never filed under a company it merely mentions. Any error: no ticker, as before."""
    try:
        import json as _json
        import wireticker as _WT
        t, ex = _WT.extract_ticker_relaxed(body)
        if not t:
            return None, None
        if not _TNWTICK_LISTED:
            for r in _json.load(open("/opt/mnt/app/tickers.json")):
                if isinstance(r, dict) and r.get("ticker") and not (r.get("excluded") or r.get("exclude_auto")):
                    w = _tnwtick_words(r.get("name"))
                    _TNWTICK_LISTED[r["ticker"].upper()] = " ".join(w[:2]) if len(w) >= 2 and len(" ".join(w[:2])) >= 8 else ""
        if t.upper() not in _TNWTICK_LISTED:
            return None, None
        if _WT.company_matches(t, _WT.names_company(title)):
            return t, ex
        key = _TNWTICK_LISTED[t.upper()]
        if key and (" ".join(_tnwtick_words(title)) + " ").startswith(key + " "):
            return t, ex
    except Exception:
        pass
    return None, None


_TNWTICK_ALL: dict = {}          # ticker -> (name words without Inc/Corp/Ltd, on the coverage list?)
_TNWTICK_SUF = re.compile(r"\(\s*([A-Z][A-Z0-9]{0,5})\.(V|TO|CN)\s*\)")
_TNWTICK_EX = {"V": "TSXV", "TO": "TSX", "CN": "CSE"}


def _tnwtick_names() -> dict:
    if not _TNWTICK_ALL:
        import json as _json
        for r in _json.load(open("/opt/mnt/app/tickers.json")):
            if isinstance(r, dict) and r.get("ticker"):
                _TNWTICK_ALL[r["ticker"].upper()] = (_tnwtick_words(r.get("name")),
                                                     not (r.get("excluded") or r.get("exclude_auto")))
    return _TNWTICK_ALL


def _tnwtick_starts(title: str, ticker: str) -> bool:
    """True when the headline starts with this ticker's company name (shared name test, or its first two name words)."""
    import wireticker as _WT
    if _WT.company_matches(ticker, _WT.names_company(title)):
        return True
    w = (_tnwtick_names().get((ticker or "").upper()) or ([], False))[0]
    key = " ".join(w[:2])
    return len(w) >= 2 and len(key) >= 8 and (" ".join(_tnwtick_words(title)) + " ").startswith(key + " ")


def _tnwtick_by_name(title: str, body: str):
    """The one coverage-list company whose name starts the headline AND whose full listed name is in the opening of the
    text (first 600 characters); else nothing."""
    import wireticker as _WT
    names = _tnwtick_names()
    bares = _WT.names_company(title)
    cands = [k for k, v in names.items() if v[1] and k.rsplit(".", 1)[0] in bares]
    if len(cands) == 1:
        full = " ".join(names[cands[0]][0])
        if len(full) >= 12 and full in " ".join(_tnwtick_words((body or "")[:600])):
            return cands[0], _TNWTICK_EX.get(cands[0].rsplit(".", 1)[1])
    return None, None


def _tnwtick_v2(title: str, body: str, t0, ex0):
    """TNWTICK_V2 (2026-11-10). t0/ex0 = extract_ticker()'s result (first lone "(TSX: ABC)"), possibly None.
    a. t0 found but the headline does not start with its company: if the shared dateline reader and the V1 name test
       point at another coverage-list company (dateline and headline both), file the release there (Sama's release that
       mentions "(TSX: AYA)" was filed under Aya); the same when the headline starts with exactly one coverage-list
       company's name and its full listed name opens the text (ZincX, filed under Teck). Otherwise t0 stands.
    b. nothing found: V1's fallback; then "(TBK.V)"; then, with no ticker anywhere, a headline that starts with exactly
       one coverage-list company's name whose full listed name is in the opening of the text.
    Any error: t0/ex0, as before."""
    try:
        names = _tnwtick_names()
        if t0:
            if _tnwtick_starts(title, t0):
                return t0, ex0
            t, ex = _relaxed_ticker(title, body)
            if not t:
                t, ex = _tnwtick_by_name(title, body)
            return (t, ex) if t and t.upper() != t0.upper() else (t0, ex0)
        t, ex = _relaxed_ticker(title, body)
        if t:
            return t, ex
        m = _TNWTICK_SUF.search((body or "")[:1500])
        if m:
            c = m.group(1).upper() + "." + m.group(2)
            if names.get(c, ([], False))[1] and _tnwtick_starts(title, c):
                return c, _TNWTICK_EX[m.group(2)]
        t, ex = _tnwtick_by_name(title, body)
        if t:
            return t, ex
    except Exception:
        pass
    return t0, ex0


def fetch_rss() -> list[dict]:
    """Pull master RSS, return list of raw item dicts (unfiltered)."""
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as c:
        r = c.get(WIRE_URL)
        r.raise_for_status()
        xml_text = r.text
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []
    out = []
    for it in channel.findall("item"):
        title = (it.findtext("title") or "").strip()
        link  = (it.findtext("link") or "").strip()
        pub   = (it.findtext("pubDate") or "").strip()
        desc  = it.findtext("description") or ""
        # description has HTML-encoded body, decode once
        raw_html = _html.unescape(desc)
        raw_body = _strip_html(desc)
        published_at = _parse_rfc822(pub)
        ticker, exch = extract_ticker(raw_body)
        ticker, exch = _tnwtick_v2(title, raw_body, ticker, exch)   # TNWTICK_V2 (2026-11-10; V1's fallback is inside)
        out.append({
            "raw_headline": title,
            "source_url":   link,
            "raw_html":     raw_html,
            "raw_body":     raw_body,
            "published_at": published_at,
            "raw_pub":      pub,
            "ticker":       ticker,
            "exchange":     exch,
        })
    return out


def list_mining_events(known_mining_tickers: set[str] | None = None) -> Iterator[dict]:
    """Yield event-shaped dicts for mining items only.

    The event_id is keyed off the source_url so re-pulling the RSS won't
    create duplicates of the same wire item.
    """
    for raw in fetch_rss():
        if not raw["ticker"]:
            # No Canadian ticker found → skip (we don't track US-only stocks)
            continue
        ok, reason = is_mining(
            raw["raw_headline"], raw["raw_body"],
            known_mining_tickers=known_mining_tickers,
            ticker=raw["ticker"],
        )
        if not ok:
            continue
        yield {
            "event_id":     _event_id(raw["source_url"], raw["published_at"]),
            "ticker":       raw["ticker"],
            "event_type":   "news_release",
            "source_name":  "thenewswire",
            "source_url":   raw["source_url"],
            "raw_headline": raw["raw_headline"],
            "raw_body":     raw["raw_body"],
            "raw_html":     raw["raw_html"],
            "published_at": raw["published_at"],
            "review_status":"auto_approved",
            "_classify_reason": reason,
            "_exchange":    raw["exchange"],
        }


# ---------- ticker auto-onboarding ----------

def extract_company_name(headline: str, body: str) -> str | None:
    """Heuristic: pull the company name from body header.

    TheNewswire releases typically open with: 'CITY, COUNTRY - DATE - TheNewswire - <CompanyName> ("Foo")'.
    We grab whatever is between 'TheNewswire' and the first '("'.
    """
    text = body or ""
    # Pattern 1: '... TheNewswire - CompanyName ("..."' or 'TheNewswire CompanyName ("...'
    m = re.search(r"TheNewswire\s*[-:]\s*([A-Z][^()]{2,80}?)\s+\(\s*[\"“]", text)
    if m:
        return m.group(1).strip().rstrip(".,")
    # Pattern 2: '... – TheNewswire - CompanyName Inc.'
    m = re.search(r"TheNewswire\s*[-:]\s*([A-Z][A-Za-z0-9 .,&'\-]{4,80}?(?:\s+(?:Inc|Corp|Ltd|Limited|Co|Company|Resources|Mining|Minerals|Metals|Gold|Silver|Lithium))\b\.?)", text)
    if m:
        return m.group(1).strip()
    # Pattern 3: 'XYZ Corp. ("XYZ"' — in body, before first "
    m = re.search(r"([A-Z][A-Za-z0-9 .,&'\-]{4,80}?(?:\s+(?:Inc|Corp|Ltd|Limited|Co|Resources|Mining|Minerals|Metals|Gold|Silver|Lithium))\.?)\s*\(\s*[\"“]", text[:1500])
    if m:
        return m.group(1).strip()
    return None
