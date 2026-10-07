"""Outside-tag admission rule for the Production Results reader (miningnewsterminal.com).

admit(headline, text, categories, out) -> (bool, short_reason)

A release that lacks the Production Results tag is admitted only when
  (A) it is a company's own periodic report (results / production / guidance / operations update), not a
      financing, deal, study, drill, meeting or conference-call notice that quotes production as background;
  (B) the company is a producer (not a developer / explorer, and a royalty company only when it reports GEOs);
  (C) the reader's rows look like one reporting period's company figures, each one actually printed in the text.
Standard library only; no names, tickers or ids.  See NOTES_production.md.
"""
import re
from bisect import bisect_left, bisect_right

# ---------------------------------------------------------------- (A) what kind of release is it?

# "Q2 2025 results", "first quarter production", "2026 guidance", "results for the year ended ..."
_S = r"[^.\n;:]{0,60}?"
PERIOD = (r"(?:\bQ[1-4]\b|\bH[12]\b|\bfirst\b|\bsecond\b|\bthird\b|\bfourth\b|\bquarter(?:ly)?\b|full[- ]year|"
          r"year[- ]end|\bannual\b|\bhalf\b|nine months|\bfiscal\b|\bFY\s?\d{2,4}\b|\b(?:19|20)\d\d\b)")
REPORT = (r"(?:\bresults\b|\bproduction\b|\bproduces\b|\bproduced\b|\bguidance\b|\boutlook\b|\boperating\b|"
          r"\boperations\b|\bfinancial performance\b)")
RESULTS_RE = re.compile(PERIOD + _S + REPORT + "|" + REPORT + _S + PERIOD, re.I)

# "Provides Company Update", "Provides an Update on <mine> Operations", "<mine> gold mine update"
UPDATE_RE = re.compile(r"\b(?:operations?|operating|operational|production|company|corporate|mine|business) update\b"
                       r"|\bupdate on\b[^.;\n]{0,40}\boperations?\b", re.I)

# Conference-call / results-date notices: the production figures in them are old or boilerplate.
NOTICE_RE = re.compile(r"\bnotice of\b|\brelease date\b|\bwill (?:report|release|announce|host)\b"
                       r"|(?<!pleased )(?<!happy )(?<!proud )\bto (?:report|release|announce|host)\b", re.I)

# AGM / meeting results: figures are the company description, not news.
MEETING_RE = re.compile(r"\b(?:annual|special|general) (?:general )?meeting\b|\bAGM\b|\bvoting results\b", re.I)

# Studies, resources, technical reports, drilling, exploration: production numbers there are study
# averages, life-of-mine totals, historic district production or another company's mine.
STUDY_RE = re.compile(r"\b(?:PEA|preliminary economic|pre-?feasibility|feasibility|technical report|mineral resource|"
                      r"resource estimate|reserve|drill\w*|intercepts?|assays?|exploration)\b", re.I)

# Financings, deals, streams, options, dividends: production is quoted as background (the target's
# history, the company's guidance in the About paragraph) unless the headline itself reports results.
DEAL_RE = re.compile(r"\b(?:private placement|financing|offering|prepayment|acquir\w*|acquisition|sale of|streams?|"
                     r"option|dividend|prospectus|warrants?|agreement|merger|arrangement|bought deal|flow-through)\b",
                     re.I)
RESULTS_HEAD_RE = re.compile(r"\bresults\b|\bproduc(?:tion|es|ed)\b", re.I)

# ---------------------------------------------------------------- (B) whose production is it?

# Developers / explorers report study production, not production results.
DEVELOPER_RE = re.compile(r"\b(?:developer|development[- ]stage|pre-production|explorer)\b", re.I)
# Royalty / streaming companies are in scope only when they report GEOs (label guide, decision 4).
ROYALTY_RE = re.compile(r"\broyalt(?:y|ies)\b|\bstreaming\b", re.I)

# ---------------------------------------------------------------- (C) do the rows hold together?

WS = re.compile(r"\s+")
RANGE_SEP = r"\s?(?:-|–|‐|—|to)\s?"


JOIN_RE = re.compile(r"(\d)(?: ([.,]) ?| ?([.,]) )(?=\d)")


def _norm(text):
    """Collapse whitespace (tabs, nbsp) and re-join numbers split around a separator ("1 ,234" -> "1,234")."""
    t = WS.sub(" ", text)
    return JOIN_RE.sub(lambda m: m.group(1) + (m.group(2) or m.group(3)), t)


NUM_TOKEN_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
SPACED_TOKEN_RE = re.compile(r"\b\d{1,3}(?: \d{3})+\b(?![.,]\d)")      # "1 262 064" (also table columns)
MILLION_AFTER_RE = re.compile(r" ?(?:million|mm?\b|m ?lbs?|m ?oz|mt\b)", re.I)
RANGE_AFTER_RE = re.compile(RANGE_SEP + r"\d")
RANGE_BEFORE_RE = re.compile(r"\d" + RANGE_SEP + r"$")
TONNES_AFTER_RE = re.compile(r" ?(?:tonnes|t\b|dmt|wmt)", re.I)


def _numbers(t):
    """Every number printed in the text, sorted by value: (value, start, end).
    Thousands may be grouped by commas or by spaces ("1 262 064"; also tried digit group by digit group)."""
    out = [(float(m.group().replace(",", "")), m.start(), m.end()) for m in NUM_TOKEN_RE.finditer(t)]
    out += [(float(m.group().replace(" ", "")), m.start(), m.end()) for m in SPACED_TOKEN_RE.finditer(t)]
    out.sort()
    return out, [v for v, _, _ in out]


def _near(nums, x):
    # printed numbers equal to x up to their own rounding (never more than 0.15%)
    if x <= 0:
        return []
    toks, keys = nums
    return toks[bisect_left(keys, x * 0.9985):bisect_right(keys, x * 1.0015)]


def _found(t, nums, v, part):
    """Is figure v stated in the text (as written, in millions, or in a '000s table)?"""
    if v is None or v <= 0:
        return True
    if _near(nums, v) or (v >= 1e3 and _near(nums, v / 1e3)):
        return True
    if v >= 1e5:
        for _, a, b in _near(nums, v / 1e6):
            if MILLION_AFTER_RE.match(t, b):
                return True
            if part == "low" and RANGE_AFTER_RE.match(t, b):       # "2.0 - 2.5 million ounces"
                return True
            if part == "high" and RANGE_BEFORE_RE.search(t[max(0, a - 6):a]):
                return True
    return False


def _unsupported(t, nums, rows):
    # A figure the release never prints: carried over from another release, computed, or misread.
    for r in rows:
        if r.get("kind") == "milestone":
            continue
        for k in ("qty", "low", "high"):
            if not _found(t, nums, r.get(k), k):
                return True
    return False


NUM = r"(\d[\d,]*(?:\.\d+)?)"
SENT_RANGE_RE = re.compile(NUM + RANGE_SEP + NUM + r" ?(million|thousand)? ?(?:tonnes|ounces|pounds|lbs|oz|t)\b"
                           r"(?: of)? ([a-z]+)(?! ?eq)", re.I)
_SCALE = {"million": 1e6, "thousand": 1e3}


def _sub_company_guidance(t, nums, rows):
    # Multi-mine producer: a guidance row taken from a sentence that also gives a *different* range for a
    # metal whose company guidance the reader already holds -> that sentence is one operation's outlook.
    guid = {}
    for r in rows:
        if r.get("kind") == "guidance" and r.get("low"):
            guid[(r.get("metal") or "").lower()] = r["low"]
    if len(guid) < 2:
        return False
    for r in rows:
        if r.get("kind") != "guidance" or not r.get("low"):
            continue
        lo = r["low"]
        for _, a, b in _near(nums, lo) + _near(nums, lo / 1e6):
            s0 = max(t.rfind(". ", 0, a), t.rfind("•", 0, a)) + 1
            s1 = t.find(". ", b)
            for x in SENT_RANGE_RE.finditer(t, s0, s1 if s1 > 0 else len(t)):
                metal = x.group(4).lower()
                if metal == (r.get("metal") or "").lower() or metal not in guid:
                    continue
                other = float(x.group(1).replace(",", "")) * _SCALE.get((x.group(3) or "").lower(), 1)
                if abs(other - guid[metal]) > 0.01 * guid[metal]:
                    return True
    return False


ORE_RE = re.compile(r"(?:throughput|milled|processed|mined|treated|mill feed|\bore\b)(?:(?!produc)[^.]){0,25}$", re.I)


def _ore_tonnes(t, nums, rows):
    # A metal row in tonnes whose figure the text gives as ore milled / mined / processed.
    for r in rows:
        if r.get("unit") != "t" or not r.get("qty"):
            continue
        for _, a, b in _near(nums, r["qty"]):
            if TONNES_AFTER_RE.match(t, b) and t[a - 1:a] != "$" \
                    and ORE_RE.search(t[max(0, a - 60):a]):
                return True
    return False


def _year(period):
    m = re.search(r"(?:19|20)\d\d", period or "")
    return int(m.group()) if m else None


def _row_problem(rows):
    # A periodic report covers one period plus next year's guidance: rows spanning more than two calendar
    # years mean historic figures, prior-year comparatives or multi-year outlooks were picked up.
    years = [y for y in (_year(r.get("period")) for r in rows) if y]
    if years and max(years) - min(years) > 1:
        return "rows span >2 years"
    ranges = {}
    for r in rows:
        if r.get("kind") != "guidance":
            continue
        lo, hi = r.get("low"), r.get("high")
        # A guidance range wider than +50% (or inverted) is two unrelated numbers glued together.
        if lo and hi and (hi < lo or hi > 1.5 * lo):
            return "implausible guidance range"
        # The same range filed under two periods / metals: the reader copied one range around.
        if lo:
            key = (lo, hi)
            if key in ranges and ranges[key] != (r.get("period"), r.get("metal")):
                return "same range on two rows"
            ranges[key] = (r.get("period"), r.get("metal"))
    # The same figure stored as both 'recovered' and 'actual' for one period: the reader double-filed it.
    seen = {}
    for r in rows:
        if r.get("kind") in ("actual", "recovered") and r.get("qty"):
            key = (r.get("period"), r.get("qty"))
            if key in seen and seen[key] != r.get("kind"):
                return "recovered duplicates actual"
            seen[key] = r.get("kind")
    return None


# ---------------------------------------------------------------- the rule

def admit(headline, text, categories, out):
    rows = (out or {}).get("rows") or []
    if not rows:
        return False, "no rows"
    h = headline or ""
    lead = h + "\n" + (text or "")[:800]          # junk headlines ("NOTICE TO READERS", addresses) -> lead

    # (A) release kind
    mn = NOTICE_RE.search(h)
    if mn and not (RESULTS_RE.search(h[:mn.start()]) or UPDATE_RE.search(h[:mn.start()])):
        return False, "notice"
    if MEETING_RE.search(h):
        return False, "meeting"
    if STUDY_RE.search(h):
        return False, "study/exploration headline"
    if DEAL_RE.search(h) and not RESULTS_HEAD_RE.search(h):
        return False, "deal headline"
    if not (RESULTS_RE.search(lead) or UPDATE_RE.search(h)):
        return False, "no results language"

    # (B) producer?
    if DEVELOPER_RE.search(lead):
        return False, "developer"
    if ROYALTY_RE.search(lead) and not any(r.get("metal") == "GEO" for r in rows):
        return False, "royalty co, no GEO"

    # (C) rows
    if all(r.get("kind") == "milestone" for r in rows):
        return False, "milestone only"
    p = _row_problem(rows)
    if p:
        return False, p
    t = _norm(text or "")
    nums = _numbers(t)
    if _unsupported(t, nums, rows):
        return False, "figure not in text"
    if _sub_company_guidance(t, nums, rows):
        return False, "mine-level guidance"
    if _ore_tonnes(t, nums, rows):
        return False, "ore tonnes read as metal"
    return True, "results release"
