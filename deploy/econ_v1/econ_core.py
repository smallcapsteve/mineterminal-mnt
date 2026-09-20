"""ECON_V1 -- reading an economic study out of a news release.

Written against the 50-release set Justin confirmed on 2026-09-20. The rules below are not
invented; each one exists because a release in that set breaks the naive version of it.
"""
import re

VERSION = "1.0.0"

# ---------------------------------------------------------------- what part of a release to read
_RE_FLS = re.compile(r"(?i)(forward[\s-]looking\s+(?:statements?|information)|"
                     r"cautionary\s+(?:note|statement)|caution\s+regarding|safe\s+harbou?r)")


def readable(body):
    """The release minus its legal disclaimer.

    That paragraph names every metric an economic study reports -- 'estimates of life of mine,
    capital and operating costs, IRR, NPV and cash flows' -- and states none of them, so it is the
    densest run of economics vocabulary in most releases. Century Lithium's permitting update has
    NPV and IRR in it and not one figure. Cut at the disclaimer unless it starts in the first
    quarter of the body, which would mean the release opens with it and there is nothing to keep."""
    m = _RE_FLS.search(body or "")
    return (body or "")[:m.start()] if m and m.start() > len(body or "") * 0.25 else (body or "")


# ---------------------------------------------------------------- numbers
_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6,
         "b": 1e9, "bn": 1e9, "billion": 1e9}
_RE_MONEY = re.compile(r"""(?ix)
    (?<![A-Za-z])                # 'CA$' must not be entered at its 'A$': Lomiko writes CA$797.5 M
    (?P<cur>CA\$|CAD\s*\$?|C\$|US\$|USD\s*\$?|AUD\s*\$?|A\$|\$)?\s*
    (?P<num>\d[\d,]*(?:\.\d+)?)\s*
    (?P<mult>billion|million|thousand|bn|mm|[KMB])?\b
    (?!\s*%)                    # a percentage is not money: 'NPV (5%) of C$24.27 million'
                                 # would otherwise return 5, which is the discount rate
    """)


def money(text, scale=None):
    """The first currency amount in `text`, as (value, currency-or-None).

    'C$24.27 million' -> (24270000.0, 'CAD'); 'US$1.49B' -> (1.49e9, 'USD').

    A bare number is NOT money. It must carry a currency mark or a magnitude word, or two things
    break: 'Post-Tax NPV8 of US$2.0 Billion' returns 8 (the discount rate glued to the label), and
    'IRR of 55.2% and initial capital of US$290 million' returns 55 (the regex backtracks around
    the percent guard and matches the integer part). A flattened table cell has neither mark nor
    word -- its magnitude lives in a header like '$ million' -- so the caller passes `scale`."""
    for m in _RE_MONEY.finditer(text or ""):
        cur_raw = (m.group("cur") or "").upper().replace("$", "").strip() or None
        mult = (m.group("mult") or "").lower()
        if not cur_raw and not mult and scale is None:
            continue
        try:
            v = float(m.group("num").replace(",", ""))
        except ValueError:
            continue
        v *= _MULT.get(mult, 1.0) if mult else (scale or 1.0)
        return v, {"C": "CAD", "CA": "CAD", "CAD": "CAD",
                   "US": "USD", "USD": "USD", "A": "AUD", "AUD": "AUD"}.get(cur_raw)
    return None, None


_RE_PCT = re.compile(r"(?P<num>\d{1,3}(?:\.\d+)?)\s*%")


def percent(text):
    m = _RE_PCT.search(text or "")
    return float(m.group("num")) if m else None


_RE_YEARS = re.compile(r"(?i)(?P<num>\d{1,3}(?:\.\d+)?)[\s-]*(?P<unit>years?|yrs?|months?|mths?)\b")
# a flattened table puts the unit in its own cell BEFORE the value: 'Payback Period (months) 30',
# 'Mine Life yrs 7.25'. Desert Gold does this in one release and writes '3.3 years' in another.
_RE_YEARS_REV = re.compile(r"(?i)\(?(?P<unit>years?|yrs?|months?|mths?)\)?[\s|]{0,14}"
                           r"(?P<num>\d{1,3}(?:\.\d+)?)\b")


def years(text):
    """Payback and mine life, normalised to years. Desert Gold states payback in months in one
    release and years in another, for the same project."""
    m = _RE_YEARS.search(text or "") or _RE_YEARS_REV.search(text or "")
    if not m:
        return None
    v = float(m.group("num"))
    return round(v / 12.0, 2) if m.group("unit").lower().startswith(("month", "mth")) else v


# ---------------------------------------------------------------- which basis a figure is on
_RE_AFTER = re.compile(r"(?i)\b(after[\s-]?tax|post[\s-]?tax)\b")
_RE_PRE = re.compile(r"(?i)\bpre[\s-]?tax\b")
_RE_NOMINAL = re.compile(r"(?i)\bnominal\b")
_RE_REAL = re.compile(r"(?i)\breal\b(?!\s*estate)")


def tax_basis(text, default=None):
    """after / pre / None. Every release in the set states both, and they differ enormously --
    ESGold's Montauban is C$24.27M after tax against C$44.53M before, 1.8x apart. Publishing the
    pre-tax figure as the headline number is this reader's equivalent of folding inferred
    resources into reserves."""
    a, p = _RE_AFTER.search(text or ""), _RE_PRE.search(text or "")
    if a and p:
        return "after" if a.start() < p.start() else "pre"
    if a:
        return "after"
    if p:
        return "pre"
    return default


def value_basis(text):
    """nominal / real. Tantalex states its pre-tax NPV both ways -- $764M nominal, $638M real --
    and Euro Manganese says 'a real discount rate of 8%'. Real is what a release means when it
    does not say (Justin, 2026-09-20)."""
    if _RE_NOMINAL.search(text or ""):
        return "nominal"
    return "real"


# ---------------------------------------------------------------- the discount rate on an NPV
_RE_DISCOUNT = re.compile(r"""(?ix)
    (?: NPV \s* \(? (?P<a>\d{1,2}(?:\.\d+)?) \s*%? \)?          # NPV5  NPV(8%)  NPV8%
      | NPV \s* (?:@|at) \s* (?P<b>\d{1,2}(?:\.\d+)?) \s*%      # NPV @ 7%
      | (?P<c>\d{1,2}(?:\.\d+)?) \s*% \s* discount              # 8% discount
      | discount \s+ rate \D{0,12} (?P<d>\d{1,2}(?:\.\d+)?) \s*% # discount rate of 8%
      | net \s+ present \s+ value \D{0,18} (?P<e>\d{1,2}(?:\.\d+)?) \s*% )""")


def discount_of(text):
    """An NPV without its rate is not comparable to anything. The rate is usually welded to the
    label -- NPV5, NPV10%, NPV @ 7%, 'using an 8% discount' -- and West Red Lake states it only in
    prose, never in the table its NPV sits in."""
    m = _RE_DISCOUNT.search(text or "")
    if not m:
        return None
    for g in ("a", "b", "c", "d", "e"):
        if m.group(g):
            v = float(m.group(g))
            return v if 0 < v <= 25 else None
    return None


# ---------------------------------------------------------------- what kind of study
_RE_FS = re.compile(r"(?i)\b(?:definitive|bankable|final)?\s*feasibility\s+study\b|\bDFS\b|\bBFS\b")
_RE_PFS = re.compile(r"(?i)pre[\s-]?feasibility|\bPFS\b|preliminary\s+feasibility")
_RE_PEA = re.compile(r"(?i)preliminary\s+economic\s+assessment|\bPEA\b|economic\s+assessment")


def study_type(headline, body=""):
    """The headline decides when it names one, because a body often recites the whole ladder --
    'advancing toward a Pre-Feasibility Study' inside a PEA release."""
    for text in (headline or "", (headline or "") + " " + (body or "")[:2500]):
        if _RE_PFS.search(text):
            return "PFS"
        if _RE_FS.search(text):
            return "FS"
        if _RE_PEA.search(text):
            return "PEA"
    return None
