"""Publish the new financings reader into the tables /financings reads (FIN_PUBLISH_V1, 2026-09-17).

The facts store holds what FIN_V1 (portal/extractors/financings.py) found in every release. Pages do
not read the facts store directly: /financings, /api/financings/recent.json, the sidebar's recent
financings and the MTP company pages read `financings` and `financing_events`. This module turns the
ACTIVE financings version into:

  financings        one row per deal (announcement, upsizes, amendments, tranches and close grouped)
  financing_events  one row per tagged release, with the deal it belongs to (NULL when it is not the
                    company's own financing, or an update that cannot be placed in a deal)

Grouping, per ticker, oldest first (compute() is pure, so the accuracy gate can score a candidate):
  1. a copy of a release already placed (same headline within 7 days, or same role, amounts and
     price within 3 days) joins that deal and is not counted twice
  2. an announcement starts a new deal unless it continues an open one: a prospectus filing,
     "previously announced", pricing, an amended announcement, or the same price and size within
     45 days
  3. every other release joins the open deal it fits best: a referenced release date (+/- 5 days)
     decides; otherwise price, size, type and recency are scored, and a price that differs, a type
     that cannot mix (debenture vs flow-through shares, debt vs equity) or a close for a deal that
     already closed two months earlier rule a deal out
  4. a close, upsize, amendment or termination that fits no deal starts its own row; an update with
     no deal to join and no figures is not shown

Deal values: status follows the latest release that changes it (updates do not), size announced is
the latest size offered, size closed is a running total (a stated aggregate replaces it, a tranche
adds to it), price, warrant and currency come from the earliest release that states them.

Timer use (sync_structured.py): python3 -m portal.financing_publish
  - an active financings version exists  -> publish it
  - none yet                             -> run the legacy financing_backfill.py (unchanged)
Once a version is active the legacy backfill never runs again (Justin, 2026-09-17: supersede the
old reader, iterate on the new one, never revert).

Self-tests: python3 -m portal.financing_publish --selftest   (in-memory; touches nothing live)
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import time
from datetime import date

EXTRACTOR = "financings"
TAG = "Financings"
DB = "/opt/mnt/app/portal/portal.db"
LEGACY = "/opt/mnt/app/financing_backfill.py"

SCHEMA = """
CREATE TABLE IF NOT EXISTS financings (
    financing_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker            TEXT NOT NULL,
    announced_at      TEXT,
    last_update_at    TEXT,
    kind              TEXT,
    status            TEXT,
    gross_announced   REAL,
    gross_closed      REAL,
    unit_price        REAL,
    unit_comp         TEXT,
    warrant_strike    REAL,
    warrant_term_months INTEGER,
    unit_count        INTEGER,
    n_tranches        INTEGER DEFAULT 0,
    n_events          INTEGER DEFAULT 0,
    seed_event_id     TEXT
);
CREATE INDEX IF NOT EXISTS ix_financings_ticker ON financings(ticker);
CREATE INDEX IF NOT EXISTS ix_financings_status ON financings(status);
CREATE INDEX IF NOT EXISTS ix_financings_announced_at ON financings(announced_at);
CREATE TABLE IF NOT EXISTS financing_events (
    event_id          TEXT PRIMARY KEY,
    financing_id      INTEGER,
    ticker            TEXT NOT NULL,
    role              TEXT,
    tranche_label     TEXT,
    kind              TEXT,
    gross_total       REAL,
    unit_count        INTEGER,
    unit_price        REAL,
    unit_comp         TEXT,
    warrant_strike    REAL,
    warrant_term_months INTEGER,
    ref_dates         TEXT,
    event_date        TEXT,
    raw_headline      TEXT,
    FOREIGN KEY (financing_id) REFERENCES financings(financing_id)
);
CREATE INDEX IF NOT EXISTS ix_finev_ticker ON financing_events(ticker);
CREATE INDEX IF NOT EXISTS ix_finev_event_date ON financing_events(event_date);
CREATE INDEX IF NOT EXISTS ix_finev_role ON financing_events(role);
"""
ADD_COLS = {
    "financings": [("currency", "TEXT"), ("extractor_version", "TEXT"), ("gross_offered_max", "REAL"),
                   ("unit_prices", "TEXT")],
    "financing_events": [("currency", "TEXT"), ("is_deal", "INTEGER"), ("amount_offered", "REAL"),
                         ("amount_this_close", "REAL"), ("amount_closed_total", "REAL"), ("is_duplicate", "INTEGER"),
                         ("reason", "TEXT"), ("unit_prices", "TEXT"), ("extractor_version", "TEXT"),
                         ("second_financing_id", "INTEGER"), ("second_amount_this_close", "REAL"),
                         ("second_amount_closed_total", "REAL"), ("second_currency", "TEXT"), ("second_kind", "TEXT")],
}

STATUS_OF = {"announcement": "announced", "upsize": "upsized", "amendment": "amended",
             "tranche_close": "tranche_closed", "final_close": "closed", "terminated": "terminated"}
EQUITY_SHARES = {"FT", "LIFE"}
DEBTISH = {"DEBT", "STREAM"}


# ------------------------------------------------------------------ helpers
def _d(s):
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def _days(a, b):
    da, db = _d(a), _d(b)
    return (db - da).days if da and db else None


def norm_head(h):
    h = (h or "").lower()
    h = re.sub(r"\(amended\)|/?not for (?:distribution|dissemination).*$|news release\s*-?|- \w+newswire\.com$|"
               r"- [a-z]+\.com$", " ", h)
    return re.sub(r"[^a-z0-9]", "", h)[:80]


def same_price(p, q, rel=0.02):
    return bool(p and q and abs(p - q) <= max(0.0005, rel * max(p, q)))


def same_amount(x, y, rel=0.01):
    return bool(x and y and abs(x - y) <= rel * max(x, y))


def unit_comp(per):
    if per is None:
        return None
    if abs(per - 0.5) < 1e-6:
        return "share + half warrant"
    if abs(per - 1.0) < 1e-6:
        return "share + warrant"
    if abs(per - 1 / 3) < 1e-3:
        return "share + third warrant"
    if abs(per - 0.25) < 1e-6:
        return "share + quarter warrant"
    return "share + %g warrant" % per


def types_compatible(deal_types, rel_types, headline=""):
    a, b = set(deal_types), set(rel_types)
    if not a or not b:
        return True
    if ("CD" in a) != ("CD" in b) and ((a if "CD" in b else b) & EQUITY_SHARES):
        return False
    fam = lambda t: "debt" if t and t <= DEBTISH else ("equity" if not (t & (DEBTISH | {"CD"})) else None)
    fa, fb = fam(a), fam(b)
    if fa and fb and fa != fb:
        return bool(re.search(r"(?i)\b(?:notes?|debentures?|loans?|bonds?|credit|facility|stream|prepay)", headline or "")) and fa == "debt"
    return True


_REPRICE = re.compile(r"(?i)\b(?:re-?pric\w*|repris\w*|price\s+(?:adjustment|change|amendment)|amend\w*|revised\s+terms)\b")
_CONTINUES = re.compile(
    r"(?i)\b(?:previously[\s\-]+announced|(?:final|amended)\s+(?:base\s+shelf\s+)?(?:short[\s\-]+form\s+)?prospectus"
    r"|prospectus\s+supplement|files?\s+(?:a\s+|the\s+|its\s+)?(?:final|amended)|amend(?:s|ed|ment)\s+(?:to\s+)?(?:the\s+)?"
    r"(?:terms|private|offering|financing)|pricing\s+of|prices\s+(?:its\s+)?(?:previously|offering|bought)|update\s+on|"
    r"upsiz\w*|increas(?:es|ed|e)\s+(?:the\s+)?(?:size\s+of\s+)?(?:its\s+)?(?:previously|private|bought|offering|financing|non))")


def _role_family(role):
    """1.0.2: two same-day copies of one release can be read with different roles (announcement / upsize)."""
    return "close" if role in ("tranche_close", "final_close") else "terminated" if role == "terminated" else "open"


# ------------------------------------------------------------------ grouping
def compute(items):
    """items: iterable of (event, a); event = {event_id, ticker, published_at, raw_headline};
    a = financings.parse_facts() output. Returns (deals, releases, stats); releases include every
    item (deal_id None when not shown)."""
    items = sorted(items, key=lambda x: (x[0].get("ticker") or "", (x[0].get("published_at") or "")[:10],
                                         # 1.0.2: a French copy is read after its English twin the same day
                                         1 if (x[1].get("lang") or "en") == "fr" else 0,
                                         x[0].get("published_at") or "", x[0]["event_id"]))
    deals, releases = [], []
    st = {"releases": 0, "not_financing": 0, "hidden_updates": 0, "duplicates": 0, "deals": 0, "joined": 0,
          "continued": 0, "orphans": 0, "split_closes": 0}
    by_ticker = {}
    for ev, a in items:
        st["releases"] += 1
        rel = {"event": ev, "a": a, "deal": None, "duplicate": False}
        releases.append(rel)
        if not a.get("is_financing"):
            st["not_financing"] += 1
            continue
        tk = ev.get("ticker") or ""
        dt = (ev.get("published_at") or "")[:10]
        head = norm_head(ev.get("raw_headline"))
        mine = by_ticker.setdefault(tk, [])
        role = a.get("role") or "update"
        price = (a.get("prices") or [None])[0]

        # 1. copies
        dup = None
        for d in reversed(mine):
            for r in d["releases"]:
                dd = _days(r["date"], dt)
                if dd is None or abs(dd) > 7:
                    continue
                if (len(head) >= 15 and (r["head"] == head or (abs(dd) <= 3 and _similar(r["head"], head)))) or (
                        abs(dd) <= 3 and _role_family(r["role"]) == _role_family(role) and (r["price"] == price or not r["price"] or not price)
                        and _same_amounts(r["amounts"], _amounts(a), 0.01 if dd == 0 else 0.002) and (r["amounts"] != (None, None, None) or price)) or (
                        # 1.0.2: the French copy of a release filed the same day in English
                        abs(dd) <= 1 and (a.get("lang") or "en") == "fr" and r.get("lang", "en") != "fr"):
                    dup = d
                    break
            if dup:
                break
        if dup:
            _attach(dup, rel, a, dt, head, duplicate=True)
            st["duplicates"] += 1
            continue

        # 1b. one release closing two separate deals that are already on the page (1.0.1)
        if role in ("tranche_close", "final_close") and len(a.get("parts") or []) >= 2:
            sp = _split_close(mine, a, ev, dt)
            if sp:
                (d1, a1), (d2, a2) = sp
                rel["a_full"] = a
                rel["a"] = a1
                _attach(d1, rel, a1, dt, head)
                _attach(d2, rel, a2, dt, head, secondary=True)
                st["joined"] += 1
                st["split_closes"] += 1
                continue

        # 2./3. candidate deals
        best, best_score = None, None
        for d in mine:
            gap = _days(d["last_date"], dt)
            if gap is None or gap < -3 or gap > 400:
                continue
            if d["terminated"] and role not in ("update", "terminated"):
                continue
            if not types_compatible(d["types"], a.get("types") or [], ev.get("raw_headline")):
                continue
            score = 0.0
            ref_hit = any(_days(ref, r["date"]) is not None and abs(_days(ref, r["date"])) <= 5
                          for ref in (a.get("refs") or []) for r in d["releases"])
            if ref_hit:
                score += 10
            prices = [p for r in d["releases"] for p in (r["prices"] or [])]
            aprices = a.get("prices") or []
            hl = ev.get("raw_headline") or ""
            repricing = role in ("amendment", "update", "upsize") or bool(_REPRICE.search(hl))
            if aprices and prices:
                if any(same_price(p, q) for p in aprices for q in prices):
                    score += 4
                elif not ((ref_hit and repricing) or (_REPRICE.search(hl) and gap is not None and gap <= 45 and not d["final"])):
                    continue                                  # another price is another deal
            concurrent = bool(re.search(r"(?i)\b(?:clos\w*|announc\w*|complet\w*)\s+(?:(?:the|its|a|an|of|of\s+the)\s+)*(?:(?:US|C|CA)?\$[\d.,]+\s*(?:million|m)?\s+)?concurrent\b", hl))
            if a.get("offering") and d["offering"] and a["offering"] != d["offering"] and \
                    ({a["offering"], d["offering"]} & {"NON_BROKERED"}):
                if concurrent or role == "announcement":
                    continue                                  # a concurrent non-brokered placement is its own deal
                score -= 4
            off = d["offered"]
            if a.get("offered") and off and same_amount(a["offered"], off, 0.02):
                score += 3
            if role in ("tranche_close", "final_close"):
                if d["final"]:
                    last_close = max((r["date"] for r in d["releases"] if r["role"] in ("tranche_close", "final_close")), default=None)
                    g2 = _days(last_close, dt) if last_close else None
                    option = bool(re.search(r"(?i)over[\s\-]allotment|(?:agents?|underwriters?)'?\s*'?s?\s+option|greenshoe"
                                            r"|exercise\s+of\s+(?:the\s+|its\s+)?(?:\w+\s+)?option", hl))
                    amt = a.get("closed_total") or a.get("this_close")
                    same_px = (not aprices or not prices or any(same_price(p, q) for p in aprices for q in prices))
                    late_copy = g2 is not None and same_px and (g2 <= 3 or (g2 <= 14 and amt and d["closed"] and amt >= 0.5 * d["closed"]))
                    if g2 is None or not ((option and g2 <= 45) or (ref_hit and g2 <= 30) or late_copy):
                        continue                              # a closed deal takes its option exercise, a referenced late copy or a same-price restatement
                    score -= 1
                amt = a.get("this_close") or a.get("closed_total")
                if amt and off and amt > off * 2.2 and not ref_hit and not a.get("offered"):
                    score -= 3
                if not d["final"]:
                    score += 2
            if role in ("update", "upsize", "amendment") and d["final"] and not ref_hit:
                continue
            if role == "announcement":
                if concurrent and not ref_hit:
                    continue
                same_types = set(a.get("types") or []) - {"PP"} == set(d["types"]) - {"PP"}
                cont = bool(_CONTINUES.search(hl)) or (ref_hit and (not aprices or not prices or repricing or any(same_price(p, q) for p in aprices for q in prices))) or (
                    gap is not None and gap <= 45 and aprices and prices and any(same_price(p, q, 0.01) for p in aprices for q in prices)
                    and (not a.get("offered") or not off or same_amount(a["offered"], off, 0.02))) or (
                    gap is not None and gap <= 7 and same_types and not (aprices and prices) and (
                        not a.get("offered") or not off or same_amount(a["offered"], off, 0.05)))
                if not cont or gap > 120 or d["final"]:
                    continue
                score += 3
            # recency: a close 10 months after the announcement is rarely the same deal
            limit = 240 if ref_hit else (180 if role in ("tranche_close", "final_close", "upsize", "amendment", "terminated") else 120)
            if gap > limit:
                continue
            evidence = ref_hit or (aprices and prices) or (a.get("offered") and off and same_amount(a["offered"], off, 0.02))
            if gap > 60 and not evidence:
                continue                                      # two months on, only a price, size or reference joins
            score += max(0.0, 3.0 - gap / 60.0)
            if best_score is None or score > best_score:
                best, best_score = d, score
        min_score = 0.5
        if best is not None and best_score >= min_score:
            _attach(best, rel, a, dt, head)
            st["continued" if role == "announcement" else "joined"] += 1
            continue
        if role == "update" and not (_amounts(a) != (None, None, None) or a.get("prices")):
            st["hidden_updates"] += 1
            continue
        d = {"id": None, "ticker": tk, "seed": ev["event_id"], "first_date": dt, "last_date": dt, "releases": [],
             "types": list(a.get("types") or []), "offering": a.get("offering"), "currency": None, "offered": None,
             "offered_alt": [], "final": False, "terminated": False, "status": None, "closed": None,
             "n_tranches": 0, "price": None, "prices": [], "warrant": None, "orphan": role != "announcement"}
        deals.append(d)
        mine.append(d)
        st["deals"] += 1
        st["orphans"] += 1 if role != "announcement" else 0
        _attach(d, rel, a, dt, head)
    for i, d in enumerate(deals, 1):
        d["id"] = i
        if d["status"] is None:
            d["status"] = "announced"
    return deals, releases, st


def _part_analysis(a, p):
    """The release's facts narrowed to one separately closed part."""
    q = dict(a)
    q["types"] = list(p.get("types") or a.get("types") or [])
    q["offering"] = p.get("offering")
    q["currency"] = p.get("currency") or a.get("currency")
    q["offered"], q["offered_alt"] = None, []
    q["this_close"] = p.get("amount")
    q["closed_total"] = p.get("amount") if a.get("role") == "final_close" else None
    q["prices"] = [p["price"]] if p.get("price") else []
    q["conversion"] = p.get("price") if "CD" in q["types"] else None
    q["warrants"] = [] if set(q["types"]) & ({"CD"} | DEBTISH) else list(a.get("warrants") or [])
    q["parts"] = []
    return q


def _split_close(mine, a, ev, dt):
    """[(deal, part analysis), (deal, part analysis)] when two parts of a close release match two different open
    deals of this ticker, each on its own evidence (type plus size, price or referenced release). Else None."""
    parts = (a.get("parts") or [])[:3]
    matches = []
    for p in parts:
        q = _part_analysis(a, p)
        best, best_score = None, 0.0
        for d in mine:
            gap = _days(d["last_date"], dt)
            if gap is None or gap < 0 or gap > 180 or d["terminated"] or d["final"]:
                continue
            if not d["types"] or not q["types"] or not types_compatible(d["types"], q["types"]):
                continue
            fam = lambda t: "debt" if set(t) & (DEBTISH | {"CD"}) else "equity"
            if fam(d["types"]) != fam(q["types"]):
                continue
            score = 0.0
            if d["offered"] and 0.6 * d["offered"] <= q["this_close"] <= 1.6 * d["offered"] and (
                    not d["currency"] or not q["currency"] or d["currency"] == q["currency"]):
                score += 3 + (2 if same_amount(d["offered"], q["this_close"], 0.02) else 0)
            if q["prices"] and d["prices"]:
                if any(same_price(x, y) for x in q["prices"] for y in d["prices"]):
                    score += 3
                else:
                    continue
            if any(_days(ref, r["date"]) is not None and abs(_days(ref, r["date"])) <= 5
                   for ref in (a.get("refs") or []) for r in d["releases"]):
                score += 2
            if set(q["types"]) - {"PP"} and set(q["types"]) - {"PP"} <= set(d["types"]):
                score += 1
            if score >= 3 and score > best_score:
                best, best_score = d, score
        if best is not None:
            matches.append((best, q, best_score))
    for i in range(len(matches)):
        for j in range(i + 1, len(matches)):
            if matches[i][0] is not matches[j][0]:
                return (matches[i][0], matches[i][1]), (matches[j][0], matches[j][1])
    return None


def _similar(x, y):
    import difflib
    return len(x) >= 20 and len(y) >= 20 and difflib.SequenceMatcher(None, x, y).ratio() >= 0.9


def _same_amounts(p, q, rel=0.002):
    if p == q:
        return True
    return all((a is None and b is None) or (a is not None and b is not None and same_amount(a, b, rel)) for a, b in zip(p, q))


def _amounts(a):
    return (a.get("offered"), a.get("this_close"), a.get("closed_total"))


def _attach(d, rel, a, dt, head, duplicate=False, secondary=False):
    role = a.get("role") or "update"
    if secondary:
        rel["second_deal"] = d
        rel["a2"] = a
    else:
        rel["deal"] = d
        rel["duplicate"] = duplicate
    d["releases"].append({"event_id": rel["event"]["event_id"], "date": dt, "head": head, "role": role,
                          "price": (a.get("prices") or [None])[0], "prices": a.get("prices") or [],
                          "lang": a.get("lang") or "en",
                          "amounts": _amounts(a), "duplicate": duplicate, "secondary": secondary})
    if dt > d["last_date"]:
        d["last_date"] = dt
    if duplicate:
        # 1.0.2: a copy that words the same close as final ("Closes Oversubscribed Financing" beside
        # "2nd Tranche Closed") still tells us the deal is done, so the status follows the stronger wording.
        if role == "final_close" and not d["final"] and any(
                r["role"] in ("tranche_close", "final_close") and r["date"] == dt for r in d["releases"] if not r["duplicate"]):
            d["final"] = True
            d["status"] = STATUS_OF["final_close"]
        return
    if not d["types"] and a.get("types"):
        d["types"] = list(a["types"])
    elif role in ("upsize", "amendment") and a.get("types"):
        d["types"] = sorted(set(d["types"]) | set(a["types"]))
    if not d["offering"] and a.get("offering"):
        d["offering"] = a["offering"]
    if not d["currency"] and (a.get("offered") or a.get("this_close") or a.get("closed_total")):
        d["currency"] = a.get("currency")
    if a.get("offered") and (role in ("announcement", "upsize", "amendment", "update") or d["offered"] is None):
        if role in ("announcement", "update") and d["offered"] and role != "update" and a["offered"] < d["offered"] and d["status"] == "upsized":
            pass
        else:
            d["offered"] = a["offered"]
            d["offered_alt"] = list(a.get("offered_alt") or [])
    if a.get("prices"):
        for p in a["prices"]:
            if all(not same_price(p, q, 0.001) for q in d["prices"]):
                d["prices"].append(p)
        if d["price"] is None:
            d["price"] = a["prices"][0]
    if d["warrant"] is None and a.get("warrants"):
        d["warrant"] = a["warrants"][0]
    if role in ("tranche_close", "final_close"):
        d["n_tranches"] += 1
        if a.get("closed_total"):
            d["closed"] = max(a["closed_total"], d["closed"] or 0) if d["closed"] and a.get("this_close") is None else a["closed_total"]
            if d["closed"] is not None and a.get("closed_total") and d["closed"] < a["closed_total"]:
                d["closed"] = a["closed_total"]
        elif a.get("this_close"):
            d["closed"] = (d["closed"] or 0) + a["this_close"]
        if role == "final_close":
            d["final"] = True
        new = STATUS_OF[role]
        if not (d["final"] and role == "tranche_close"):
            d["status"] = new
    elif role in STATUS_OF:
        if role == "terminated":
            d["terminated"] = True
            d["status"] = "terminated"
        elif not d["final"] and not d["terminated"]:
            if role == "announcement" and d["status"] not in (None,):
                pass
            else:
                d["status"] = STATUS_OF[role]


def rows_for(deals, releases, version):
    fin_rows = []
    for d in deals:
        w = d["warrant"] or {}
        kind = "+".join(list(d["types"]) + ([d["offering"]] if d["offering"] else [])) or None
        fin_rows.append({
            "financing_id": d["id"], "ticker": d["ticker"], "announced_at": d["first_date"], "last_update_at": d["last_date"],
            "kind": kind, "status": d["status"], "gross_announced": d["offered"], "gross_closed": d["closed"],
            "unit_price": d["price"], "unit_comp": unit_comp(w.get("per_unit")), "warrant_strike": w.get("strike"),
            "warrant_term_months": w.get("term_months"), "unit_count": None, "n_tranches": d["n_tranches"],
            "n_events": len(d["releases"]), "seed_event_id": d["seed"], "currency": d["currency"] or "CAD",
            "extractor_version": version,
            "gross_offered_max": max(d["offered_alt"]) if d["offered_alt"] else None,
            "unit_prices": "|".join("%g" % p for p in d["prices"]) or None})
    ev_rows = []
    for r in releases:
        a, ev = r["a"], r["event"]
        w = (a.get("warrants") or [{}])[0] or {}
        role = a.get("role") if a.get("is_financing") else "not_financing"
        closing = role in ("tranche_close", "final_close")
        gross = (a.get("this_close") or a.get("closed_total")) if closing else a.get("offered")
        ev_rows.append({
            "event_id": ev["event_id"], "financing_id": r["deal"]["id"] if r["deal"] else None, "ticker": ev.get("ticker") or "",
            "role": role, "tranche_label": a.get("tranche"),
            "kind": "+".join(list(a.get("types") or []) + ([a["offering"]] if a.get("offering") else [])) or None,
            "gross_total": gross, "unit_count": None, "unit_price": (a.get("prices") or [None])[0],
            "unit_comp": unit_comp(w.get("per_unit")), "warrant_strike": w.get("strike"),
            "warrant_term_months": w.get("term_months"), "ref_dates": "|".join(a.get("refs") or []),
            "event_date": (ev.get("published_at") or "")[:10], "raw_headline": (ev.get("raw_headline") or "")[:500],
            "currency": a.get("currency") if a.get("is_financing") else None, "is_deal": 1 if a.get("is_financing") else 0,
            "amount_offered": a.get("offered"), "amount_this_close": a.get("this_close"),
            "amount_closed_total": a.get("closed_total"), "is_duplicate": 1 if r["duplicate"] else 0,
            "reason": a.get("reason"), "unit_prices": "|".join("%g" % p for p in (a.get("prices") or [])) or None,
            "extractor_version": version,
            "second_financing_id": r["second_deal"]["id"] if r.get("second_deal") else None,
            "second_amount_this_close": (r.get("a2") or {}).get("this_close"),
            "second_amount_closed_total": (r.get("a2") or {}).get("closed_total"),
            "second_currency": (r.get("a2") or {}).get("currency"),
            "second_kind": "+".join(list((r.get("a2") or {}).get("types") or []) + ([r["a2"]["offering"]] if (r.get("a2") or {}).get("offering") else [])) or None})
    return fin_rows, ev_rows


def predictions(deals, releases):
    """event_id -> the accuracy judge's prediction for that release (None when not shown)."""
    out = {}
    for r in releases:
        a, d = r["a"], r["deal"]
        if d is None or not a.get("is_financing"):
            out[r["event"]["event_id"]] = None
            continue
        w = (a.get("warrants") or [None])[0]
        out[r["event"]["event_id"]] = {
            "ticker": d["ticker"], "role": a.get("role"),
            "kind": list(a.get("types") or []) + ([a["offering"]] if a.get("offering") else []),
            "amounts": [x for x in (a.get("offered"), a.get("this_close"), a.get("closed_total")) if x],
            "unit_price": (a.get("prices") or [None])[0] if a.get("prices") else a.get("conversion"),
            "warrant": dict(w) if w else None, "members": [x["event_id"] for x in d["releases"]]}
    return out


# ------------------------------------------------------------------ database
def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def active_version(conn):
    if not _has_table(conn, "fx_extractor_versions"):
        return None
    r = conn.execute("SELECT version FROM fx_extractor_versions WHERE extractor=? AND status='active'", (EXTRACTOR,)).fetchone()
    return r[0] if r else None


def load_items(conn, version):
    from portal.extractors import financings as X
    evs = {}
    for eid, tk, pub, hl in conn.execute(
            "SELECT e.event_id, e.ticker, e.published_at, e.raw_headline FROM events e "
            "JOIN fx_records r ON r.event_id=e.event_id AND r.extractor=? AND r.version=? AND r.ordinal=0 "
            "WHERE e.review_status='auto_approved' AND ('|' || COALESCE(e.categories,'') || '|') LIKE ?",
            (EXTRACTOR, version, "%|" + TAG + "|%")):
        evs[eid] = {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl}
    facts = {}
    for eid, field, seq, num, text in conn.execute(
            "SELECT r.event_id, f.field, f.seq, f.value_num, f.value_text FROM fx_records r "
            "JOIN fx_facts f ON f.record_id=r.record_id WHERE r.extractor=? AND r.version=? AND r.ordinal=0",
            (EXTRACTOR, version)):
        if eid in evs:
            facts.setdefault(eid, []).append((field, seq, num, text))
    return [(evs[e], X.parse_facts(facts.get(e, []))) for e in evs]


def ensure_schema(conn):
    conn.executescript(SCHEMA)
    for table, cols in ADD_COLS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for c, t in cols:
            if c not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {c} {t}")


def publish(conn, version, log=print):
    if not re.match(r"^[0-9]+[.][0-9]+[.][0-9]+$", version or ""):
        raise ValueError(f"bad version {version!r}")
    t0 = time.time()
    deals, releases, st = compute(load_items(conn, version))
    fin_rows, ev_rows = rows_for(deals, releases, version)
    ensure_schema(conn)
    fcols = list(fin_rows[0].keys()) if fin_rows else None
    ecols = list(ev_rows[0].keys()) if ev_rows else None
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM financing_events")
        conn.execute("DELETE FROM financings")
        if fin_rows:
            conn.executemany("INSERT INTO financings(%s) VALUES (%s)" % (",".join(fcols), ",".join(":" + c for c in fcols)), fin_rows)
        if ev_rows:
            conn.executemany("INSERT INTO financing_events(%s) VALUES (%s)" % (",".join(ecols), ",".join(":" + c for c in ecols)), ev_rows)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st.update(seconds=round(time.time() - t0, 2), version=version, rows=len(fin_rows), events=len(ev_rows))
    log("[financing_publish] " + json.dumps(st))
    return st


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv:
        return _selftest()
    db = argv[argv.index("--db") + 1] if "--db" in argv else DB
    conn = sqlite3.connect(db, timeout=30, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=30000")
    version = active_version(conn)
    if "--dry-run" in argv:
        v = argv[argv.index("--version") + 1] if "--version" in argv else version
        deals, releases, st = compute(load_items(conn, v))
        cur = conn.execute("SELECT COUNT(*) FROM financings").fetchone()[0]
        st.update(version=v, current_rows=cur, new_rows=len(deals))
        print("[financing_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[financing_publish] no active financings version; running the legacy financing_backfill.py")
        return subprocess.call([sys.executable, LEGACY])
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        # never fall back to the legacy reader after the switch: the last published tables stay
        print(f"[financing_publish] FAILED publishing {version}: {type(exc).__name__}: {exc}")
        return 1


# ------------------------------------------------------------------ self-tests
def _selftest():
    bad = 0

    def ok(name, cond):
        nonlocal bad
        bad += not cond
        print(("  ok    " if cond else "  FAIL  ") + name)

    def A(role, offered=None, close=None, total=None, prices=(), types=("PP",), refs=(), fin=True, offering="NON_BROKERED", w=None):
        return {"is_financing": fin, "role": role, "tranche": None, "types": list(types), "offering": offering, "currency": "CAD",
                "offered": offered, "offered_alt": [], "this_close": close, "closed_total": total, "prices": list(prices),
                "conversion": None, "warrants": [w] if w else [], "refs": list(refs), "reason": "t"}

    def E(eid, tk, d, h):
        return {"event_id": eid, "ticker": tk, "published_at": d, "raw_headline": h}

    items = [
        (E("a1", "AAA", "2026-01-05", "AAA Announces $1M Private Placement"), A("announcement", 1_000_000, prices=[0.10])),
        (E("a1w", "AAA", "2026-01-05", "AAA Announces $1M Private Placement"), A("announcement", 1_000_000, prices=[0.10])),
        (E("a2", "AAA", "2026-01-20", "AAA Upsizes Private Placement to $1.5M"), A("upsize", 1_500_000, prices=[0.10])),
        (E("a3", "AAA", "2026-02-01", "AAA Closes First Tranche"), A("tranche_close", None, 600_000, 600_000, prices=[0.10], refs=["2026-01-05"])),
        (E("a4", "AAA", "2026-02-20", "AAA Closes Final Tranche"), A("final_close", None, 900_000, None, prices=[0.10])),
        (E("a5", "AAA", "2026-06-01", "AAA Announces New $2M Flow-Through Placement"), A("announcement", 2_000_000, prices=[0.20], types=("FT",))),
        (E("a6", "AAA", "2026-06-20", "AAA Closes Flow-Through Placement"), A("final_close", None, 2_000_000, None, prices=[0.20], types=("FT",))),
        (E("a7", "AAA", "2026-06-25", "AAA Closes $5M Convertible Debenture"), A("final_close", None, 5_000_000, None, types=("CD",))),
        (E("n1", "AAA", "2026-03-01", "AAA Reports Q4 Results"), A(None, fin=False)),
        (E("u1", "AAA", "2026-07-01", "AAA Provides Update"), A("update")),
        (E("b1", "BBB", "2026-01-10", "BBB Closes $300,000 Private Placement"), A("final_close", None, 300_000, 300_000, prices=[0.05])),
        (E("b2", "BBB", "2026-01-11", "Press Release"), A("final_close", None, 300_000, 300_000, prices=[0.05])),
    ]
    deals, rels, st = compute(items)
    did = {r["event"]["event_id"]: (r["deal"]["id"] if r["deal"] else None) for r in rels}
    by = {d["id"]: d for d in deals}
    ok("wire copy joins and is a duplicate", did["a1w"] == did["a1"] and st["duplicates"] >= 1)
    ok("upsize and tranches join the $1M deal", did["a2"] == did["a3"] == did["a4"] == did["a1"])
    ok("status closed, size $1.5M, closed $1.5M running total", (by[did["a1"]]["status"], by[did["a1"]]["offered"], by[did["a1"]]["closed"]) == ("closed", 1_500_000, 1_500_000))
    ok("a new FT placement is a new deal", did["a5"] != did["a1"] and did["a6"] == did["a5"])
    ok("a debenture close does not join the FT deal", did["a7"] not in (None, did["a5"]))
    ok("results release not shown", did["n1"] is None)
    ok("figure-less update with no deal is hidden", did["u1"] is None)
    ok("two copies of one close are one row", did["b1"] == did["b2"] and by[did["b1"]]["closed"] == 300_000)
    preds = predictions(deals, rels)
    ok("prediction members", set(preds["a3"]["members"]) == {"a1", "a1w", "a2", "a3", "a4"} and preds["n1"] is None)

    # 1.0.1: one release closing two separately announced deals is listed under both
    parts = [{"types": ["CD"], "offering": None, "currency": "USD", "amount": 25_000_000.0, "price": None},
             {"types": ["FT", "LIFE"], "offering": "BROKERED", "currency": "CAD", "amount": 28_750_230.0, "price": None}]
    close = A("final_close", None, 63_000_000, 63_000_000, types=("FT", "LIFE"), offering=None)
    close["parts"] = parts
    cd_up = A("upsize", 25_000_000, types=("CD",), offering=None)
    cd_up["currency"] = "USD"
    items2 = [(E("s1", "SSS", "2026-01-15", "SSS Announces $25 Million LIFE Private Placement of Flow-Through Shares"),
               A("announcement", 25_000_200, prices=[1.02], types=("FT", "LIFE"), offering="BROKERED")),
              (E("s2", "SSS", "2026-01-22", "SSS Announces Upsizing of Convertible Debenture Financing to USD$25 Million"), cd_up),
              (E("s3", "SSS", "2026-02-05", "SSS Closes $63 Million In Financings"), close)]
    deals2, rels2, st2 = compute(items2)
    by2 = {d["seed"]: d for d in deals2}
    r3 = [r for r in rels2 if r["event"]["event_id"] == "s3"][0]
    ok("split close: joins the FT deal and the debenture deal", st2["split_closes"] == 1 and {r3["deal"]["seed"], r3["second_deal"]["seed"]} == {"s1", "s2"})
    ok("split close: each deal has its own closed amount", (by2["s1"]["closed"], by2["s2"]["closed"], by2["s1"]["status"], by2["s2"]["status"])
       == (28_750_230.0, 25_000_000.0, "closed", "closed"))
    _f, ev2 = rows_for(deals2, rels2, "9.9.9")
    e3 = [e for e in ev2 if e["event_id"] == "s3"][0]
    ok("split close: release row carries the second deal", e3["second_financing_id"] is not None and e3["second_financing_id"] != e3["financing_id"]
       and e3["second_amount_this_close"] in (25_000_000.0, 28_750_230.0))
    lone = A("final_close", None, 5_000_000, 5_000_000, types=("PP",))
    lone["parts"] = [{"types": ["PP"], "offering": "BROKERED", "currency": "CAD", "amount": 4_000_000.0, "price": None},
                     {"types": ["PP"], "offering": "NON_BROKERED", "currency": "CAD", "amount": 1_000_000.0, "price": None}]
    deals3, rels3, st3 = compute([(E("t1", "TTT", "2026-03-01", "TTT Announces Bought Deal and Concurrent Private Placement"), A("announcement", 5_000_000, types=("PP",))),
                                  (E("t2", "TTT", "2026-03-20", "TTT Closes Bought Deal and Concurrent Private Placement"), lone)])
    ok("parts without two matching deals do not split", st3["split_closes"] == 0 and len(deals3) == 1 and deals3[0]["closed"] == 5_000_000)

    # database path on an in-memory store
    from portal import facts as F
    from portal.extractors import financings as X
    conn = F.connect(":memory:")
    F.ensure_schema(conn)
    conn.execute("CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, published_at TEXT, raw_headline TEXT, "
                 "raw_body TEXT, categories TEXT, review_status TEXT)")
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO financings(ticker, status) VALUES ('OLD','mention')")
    spec = F.ExtractorSpec(EXTRACTOR, "9.9.9", X.KIND, TAG, X.extract)
    rows = [("x1", "T1", "2026-01-02", "T1 Announces $500,000 Non-Brokered Private Placement",
             "T1 Corp. announces a non-brokered private placement of units at a price of $0.05 per unit for gross proceeds of up to $500,000.", "Financings"),
            ("x2", "T1", "2026-01-30", "T1 Closes $500,000 Private Placement",
             "T1 Corp. has closed its non-brokered private placement of 10,000,000 units at $0.05 per unit for gross proceeds of $500,000.", "Financings"),
            ("x3", "T2", "2026-01-03", "T2 Reports Q3 Results", "Cash of $2,000,000.", "Financings"),
            ("x4", "T3", "2026-01-03", "T3 Closes $900,000 Private Placement", "T3 has closed a private placement for gross proceeds of $900,000.", "Drill Results")]
    for r in rows:
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?, 'auto_approved')", r)
    F.run_batch(conn, spec, F.pending_events(conn, EXTRACTOR, "9.9.9"))
    ok("no active version yet", active_version(conn) is None)
    F.activate(conn, EXTRACTOR, "9.9.9")
    s = publish(conn, "9.9.9", log=lambda _: None)
    got = [tuple(r) for r in conn.execute("SELECT ticker, status, gross_announced, gross_closed, unit_price, extractor_version FROM financings")]
    ok("one deal published from tagged releases, legacy row gone", got == [("T1", "closed", 500000.0, 500000.0, 0.05, "9.9.9")])
    ev = {r[0]: r[1:] for r in conn.execute("SELECT event_id, financing_id, role, is_deal FROM financing_events")}
    ok("events table covers tagged releases only", sorted(ev) == ["x1", "x2", "x3"])
    ok("results release kept with no deal", ev["x3"] == (None, "not_financing", 0))
    ok("publish is repeatable", publish(conn, "9.9.9", log=lambda _: None)["rows"] == 1)
    print(f"failures: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
