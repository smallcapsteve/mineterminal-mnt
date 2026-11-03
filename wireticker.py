"""wireticker.py — WIRETICK_V1.1 (2026-11-03; V1.1: the listed share class when a dateline names two, Justin: "Majors and big misses").

Shared helpers for the Google-News-based wire collectors (GlobeNewswire, Business Wire, PR Newswire, CNW):

1. extract_ticker_relaxed(text): read a Canadian ticker from datelines the old reader could not, used ONLY when the old
   reader found nothing. The old reader wants a lone "(TSX: K)"; dual-listed companies write "(TSX: K, NYSE: KGC)",
   "(TSX:AGI; NYSE:AGI)", "(LSE:EDV, TSX:EDV, OTCQX:EDVMF)", "(TSX, NYSE: HBM)", "(TSX-V: ASE | GSE: ASG)", so their
   releases were dropped after the page had been read.
2. names_company(title): when a headline has no mining word ("Kinross reports 2026 third-quarter results"), let it
   through only if it STARTS with a coverage-list company's name; the caller then keeps the release only if the ticker
   read from the release is that same company (company_matches).
"""
from __future__ import annotations
import json, re, time

_EXCH = r"(TSX[\.\-\s]?V(?:enture)?|TSXV|TSX-Venture|CSE|TSX)"
_OTHER = r"(?:NYSE(?:\s*American|\s*MKT)?|NASDAQ|Nasdaq|LSE|AIM|ASX|JSE|GSE|OTCQX|OTCQB|OTC(?:\s*Pink|\s*Markets?)?|FSE|Frankfurt|BVL|BMV)"
# "TSX: K" / "TSX-V:LI" / "TSX, NYSE: HBM" / "TSX/NYSE: X" / "TSX and NYSE: X"; the ticker must end at , ; | / ) or space+)
_TAG = re.compile(r"(?<![A-Za-z])" + _EXCH + r"(?:\s*(?:,|/|and|&)\s*" + _OTHER + r")*\s*[:\-]\s*([A-Z][A-Z0-9]{0,6}(?:\.[A-Z]{1,2})?)(?=\s*[,;|/)]|\s+and\b|\s*$)")
_PAREN = re.compile(r"\(([^()]{2,160})\)")
_SUF = {"CSE": ("CN", "CSE"), "TSX": ("TO", "TSX")}


def _suffix(exch: str):
    e = re.sub(r"[\s.\-]", "", exch.upper())
    if e.startswith("TSXV") or "VENTURE" in e:
        return "V", "TSXV"
    return _SUF.get(e, ("TO", "TSX"))


_CLS = re.compile(r"(?:,|&|\band\b)\s*([A-Z][A-Z0-9]{0,6}\.[A-Z]{1,2})(?=\s*[,;|/)]|\s+and\b|\s*$)")
_COV = {"t": 0, "s": set()}


def _covered(path: str = "/opt/mnt/app/tickers.json") -> set:
    """WIRETICK_V1.1: coverage-list tickers without the exchange suffix ("TECK.B"); reloaded every 10 minutes."""
    if time.time() - _COV["t"] < 600 and _COV["s"]:
        return _COV["s"]
    try:
        s = {r["ticker"].rsplit(".", 1)[0].upper() for r in json.load(open(path)) if isinstance(r, dict) and r.get("ticker")}
    except Exception:
        return _COV["s"]
    _COV.update(t=time.time(), s=s)
    return s


def extract_ticker_relaxed(text: str):
    """First parenthesised group (in the first 4,000 characters) that carries a Canadian exchange tag.
    WIRETICK_V1.1: "(TSX: TECK.A and TECK.B, NYSE: TECK)" names two share classes; take the one on the coverage list."""
    head = (text or "")[:4000]
    for m in _PAREN.finditer(head):
        g = m.group(1)
        t = _TAG.search(g)
        if t:
            suf, ex = _suffix(t.group(1))
            tick = t.group(2).upper()
            if "." in tick:
                try:
                    cov = _covered()
                    if cov and tick not in cov:
                        for alt in _CLS.findall(g[t.end():]):
                            if alt.upper() in cov:
                                tick = alt.upper()
                                break
                except Exception:
                    pass
            return f"{tick}.{suf}", ex
    return None, None


_GEN = set(("first new north northern south southern west western east eastern american canadian canada global great royal "
            "golden gold silver copper metals minerals mining resources energy lithium uranium nickel black blue green red "
            "white grey gray united international pacific atlantic central star big rock stone mountain river lake bay "
            "the a sierra rio san santa st premier prime alpha nova fortune power total china form man group market "
            "battery liquid rare world national digital smart advanced enhanced standard general capital "
            "true high life core link next open data home post fire iron zinc lead best city park news form").split())
_SUFX = re.compile(r"\b(inc|corp|corporation|ltd|limited|plc|co|company|s\.a\.|sa|ag|nl|llc|lp)\b\.?", re.I)
_CACHE = {"t": 0, "keys": {}}


def _keys(path: str = "/opt/mnt/app/tickers.json") -> dict:
    """{name key (lower): bare ticker} for every non-excluded coverage-list company; reloaded every 10 minutes."""
    if time.time() - _CACHE["t"] < 600 and _CACHE["keys"]:
        return _CACHE["keys"]
    keys = {}
    try:
        rows = json.load(open(path))
    except Exception:
        return _CACHE["keys"]
    for r in rows:
        if not isinstance(r, dict) or not r.get("ticker") or r.get("excluded") or r.get("exclude_auto"):
            continue
        nm = re.sub(r"\s+", " ", _SUFX.sub("", r.get("name") or "").replace(",", " ")).strip(" .")
        w = nm.split()
        if not w:
            continue
        key = w[0] if (len(w[0]) >= 4 and w[0].lower() not in _GEN) else " ".join(w[:2])   # V1.1: 4 letters (Teck)
        if len(key) < 4 or key.lower() in _GEN or all(x.lower() in _GEN for x in key.split()):
            continue
        keys.setdefault(key.lower(), set()).add(r["ticker"].split(".")[0].upper())
    _CACHE.update(t=time.time(), keys=keys)
    return keys


def names_company(title: str):
    """Bare tickers of the coverage-list company whose name STARTS the headline, else empty set."""
    tl = re.sub(r"^[\W_]+", "", (title or "").lower())
    for k, bares in _keys().items():
        if tl.startswith(k) and (len(tl) == len(k) or not tl[len(k)].isalnum()):
            return bares
    return set()


def company_matches(ticker: str | None, bares) -> bool:
    return bool(ticker) and ticker.split(".")[0].upper() in (bares or ())
