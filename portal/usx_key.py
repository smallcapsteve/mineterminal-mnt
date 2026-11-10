"""USX_FEEDKEY_V1 (2026-11-10): one rule for every mining-data feed's ?ticker= filter.

The feeds match a company by the letters before the dot (RGLD matches RGLD.CN and RGLD.US). Once US-listed companies
arrived that put Royal Gold's (RGLD.US) production on Red Lake Gold's (RGLD.CN) page, and MTP's own form of a US
listing ("RGLD-US") matched nothing. norm() gives each feed:
  - the ticker with "-US" read as ".US";
  - for a symbol listed both as .US and on another exchange in tickers.json (RGLD, AU today), one more SQL test:
    the .US form keeps only .US rows, any other form leaves .US rows out.
Every other ticker is returned untouched with no extra test, so those answers do not change.
"""
import json
import os
import time

TICKERS_PATH = "/opt/mnt/app/tickers.json"
_C = {"ts": 0.0, "mt": None, "set": frozenset()}


def clash_bases() -> frozenset:
    now = time.time()
    if now - _C["ts"] < 60:
        return _C["set"]
    _C["ts"] = now
    try:
        mt = os.path.getmtime(TICKERS_PATH)
        if mt != _C["mt"]:
            us, other = set(), set()
            for x in json.load(open(TICKERS_PATH)):
                t = str((x or {}).get("ticker") or "").upper()
                b, _, suf = t.partition(".")
                if b:
                    (us if suf == "US" else other).add(b)
            _C["set"], _C["mt"] = frozenset(us & other), mt
    except Exception:  # noqa: BLE001
        pass
    return _C["set"]


def norm(t):
    """-> (ticker, sql) where sql is '' or a test with one %s for the ticker column."""
    if not t:
        return t, ""
    u = str(t).strip().upper()
    if u.endswith("-US") and len(u) > 3:
        u = u[:-3] + ".US"
    base, _, suf = u.partition(".")
    if base in clash_bases():
        return u, ("upper(%s) LIKE '%%.US'" if suf == "US" else "upper(%s) NOT LIKE '%%.US'")
    return (u if u.endswith(".US") and not str(t).strip().upper().endswith(".US") else t), ""


def keeps(row_ticker, sql) -> bool:
    """The same rule for rows filtered in Python: does this row belong to the side of the symbol that was asked for?"""
    if not sql:
        return True
    return str(row_ticker or "").upper().endswith(".US") == (" NOT " not in sql)


def universe(bares):
    """V1.1: MTP's list names a US listing "AU-US"; its rows here are AU.US, whose letters before the dot are "AU".
    Adds that form so the universe test lets a US company's own rows through."""
    try:
        return frozenset(bares) | frozenset(b[:-3] for b in bares if b.endswith("-US") and len(b) > 3)
    except Exception:  # noqa: BLE001
        return bares
