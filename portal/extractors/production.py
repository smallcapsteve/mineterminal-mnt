"""Production Results reader, facts-store version (PROD_V1, 2026-09-21).

The source of the Production Results page once it passes the accuracy gate. Written against the
50-release set Justin confirmed on 2026-09-21 (45 items count, 83 rows).

The row shape and the rules are Justin's (2026-09-21), and each one is here because a release forced it:

  1. ONE ROW PER METAL PER PERIOD. Company totals, or a single named mine where that is all the release
     reports (Imperial's Mount Polley, Nickel 28's Ramu), with sold and AISC on the row when stated.
  2. THREE KINDS OF ROW. 'actual' (what was produced), 'guidance' (a low-high range; a single figure is
     low = high; "above 375,000 oz" is low only), 'milestone' (commercial production, first pour, first
     production or shipment, a resumption) with no figures.
  3. THE COMPANY'S OWN MEASURE. Torex reports PAYABLE production, Thor gold POURED, Luca payable metal.
     The reader takes the figure the release calls production and never swaps in 'recovered' ounces,
     ounces 'before payable deductions' or contained ounces mined.
  4. SOLD IS NOT PRODUCED. Sierra Madre headlines 128,827 AgEq ounces SOLD; Allied produced 84,040 and
     sold 131,520. A sold figure goes on the produced row, never in its place -- except for a royalty
     company, whose production IS its attributable GEOs sold (Versamet).
  5. PRECISION FIRST. A figure is only a row when the release says, in one clause, what it is, which metal
     and which period. A year-to-date total, a multi-year average, a run-rate, a comparative
     ("compared to 70,176 ounces in Q1 2025"), a study's average production and a plan are not rows.
  6. MINED METALS ONLY. Oil and gas are out of scope, and a release reading like an oil and gas
     producer's gives no rows at all.

Guidance for a period that has already ended belongs on the actual row (Justin, 2026-09-21); the reader
cannot know the release date, so it emits the guidance row and portal/production_publish.py folds it.

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per row (ordinal 0..n-1)
to_prediction(records) -> dict|None    what the accuracy judge compares

Self-tests: python3 -m portal.extractors.production
"""
from __future__ import annotations

import re

from portal import facts as F

NAME = "production"
VERSION = "1.0.0"
KIND = "production_row"
TAG = "Production Results"
TEXT_CAP = 40000

NUM_FIELDS = ("qty", "low", "high", "sold", "aisc")
TXT_FIELDS = ("kind", "period", "metal", "unit", "milestone", "asset", "basis")

# ------------------------------------------------------------------ vocabulary
_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_MULT = r"(?:\s*(million|thousand|mm|m|k)\b)?"

# unit token -> (unit, multiplier, implied metal)
_UNITS = [
    (r"koz\s*(?:au\b)?", "oz", 1e3, None),
    (r"moz", "oz", 1e6, None),
    (r"thousand\s+ounces", "oz", 1e3, None),
    (r"million\s+ounces", "oz", 1e6, None),
    (r"(?:troy\s+)?ounces|ounce|oz\b", "oz", 1, None),
    (r"million\s+pounds|mlbs?\b", "lb", 1e6, None),
    (r"pounds|lbs?\b", "lb", 1, None),
    (r"tonnes|tonne|metric\s+tons", "t", 1, None),
    (r"t\b", "t", 1, None),                 # only when glued to the number ('35,000t'), see _mentions
    (r"geos?\b", "oz", 1, "GEO"),
    (r"gold\s+equivalent\s+ounces?", "oz", 1, "AuEq"),
    (r"silver\s+equivalent\s+ounces?", "oz", 1, "AgEq"),
]
_UNIT_RE = "|".join("(?:%s)" % u[0] for u in _UNITS)

_METALS = [
    (r"gold\s+equivalent|\bgeos?\b", None),     # resolved by the unit
    (r"\bauEq\b|oz\s+aueq", "AuEq"),
    (r"\bagEq\b|oz\s+ageq", "AgEq"),
    (r"lithium(?:\s+oxide)?\s+concentrate|spodumene\s+concentrate|\bsc6\b", "lithium concentrate"),
    (r"graphite\s+concentrates?", "graphite concentrate"),
    (r"\bu3o8\b|\buranium\b", "U3O8"),
    (r"\bgold\b|\bau\b", "gold"),
    (r"\bsilver\b|\bag\b", "silver"),
    (r"\bcopper\b|\bcu\b", "copper"),
    (r"\bzinc\b|\bzn\b", "zinc"),
    (r"\blead\b|\bpb\b", "lead"),
    (r"\bnickel\b", "nickel"),
    (r"\bcobalt\b", "cobalt"),
    (r"\bmolybdenum\b", "molybdenum"),
    (r"\bpalladium\b", "palladium"),
    (r"\bplatinum\b", "platinum"),
    (r"\bantimony\b", "antimony"),
]
_METAL_RE = re.compile("|".join("(%s)" % m[0] for m in _METALS), re.I)

_OIL_GAS = re.compile(r"(?i)\b(boe(?:/d)?|bbls?(?:/d)?|barrels|natural\s+gas|mcf|mmcf|crude\s+oil|oil\s+and\s+gas|ngls?)\b")
_ANY_PROD = re.compile(r"(?i)produc|poured|guidance|commercial\s+production|\bgeos?\b|first\s+(?:gold\s+)?pour|resum|restart")

_ORD = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}
_MONTH_Q = {"march": 1, "june": 2, "september": 3, "december": 4}
_MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december")

# a period expression, in the order they are tried at each position
_PERIOD_RES = [
    ("fq", re.compile(r"(?i)\bQ([1-4])\s+fiscal\s+(?:year\s+)?(20\d\d)\b")),
    ("fq", re.compile(r"(?i)\b(first|second|third|fourth)\s+quarter\s+(?:of\s+)?fiscal\s+(?:year\s+)?(20\d\d)\b")),
    ("q", re.compile(r"(?i)\bQ([1-4])[\s\-/]*(?:FY\s*)?(20\d\d)\b")),
    ("q2", re.compile(r"(?i)\b([1-4])Q[\s\-]*(\d\d(?:\d\d)?)\b")),
    ("q", re.compile(r"(?i)\b(first|second|third|fourth|1st|2nd|3rd|4th)[\s\-]+quarter\s+(?:of\s+|ended\s+\w+\s+\d+,?\s+)?(20\d\d)\b")),
    ("m3", re.compile(r"(?i)\bthree\s+months\s+ended\s+(march|june|september|december)\s+3[01],?\s+(20\d\d)\b")),
    ("h", re.compile(r"(?i)\bH([12])[\s\-]*(20\d\d)\b")),
    ("h", re.compile(r"(?i)\b(first|second)\s+half\s+(?:of\s+)?(20\d\d)\b")),
    ("fy", re.compile(r"(?i)\b(?:full[\s\-]*year|fiscal\s+year|financial\s+year|FY|year[\s\-]+end(?:ed)?|annual)[\s\-]*(20\d\d)\b")),
    ("fy", re.compile(r"(?i)\bFY\s*'?(\d\d)\b")),
    ("fy2", re.compile(r"(?i)\b(20\d\d)\s+(?:full[\s\-]*year|annual|fiscal\s+year)\b")),
    ("mon", re.compile(r"(?i)\b(?:month\s+of\s+)(" + _MONTHS + r")\s+(20\d\d)\b")),
    # without a year: resolved against the release's own period
    ("qn", re.compile(r"(?i)\bQ([1-4])\b(?!\s*(?:20\d\d|fiscal))")),
    ("qn", re.compile(r"(?i)\b(first|second|third|fourth|1st|2nd|3rd|4th)[\s\-]+quarter\b(?!\s+(?:of\s+)?(?:20\d\d|fiscal))")),
    ("qd", re.compile(r"(?i)\b(?:the|this)\s+quarter\b|\bquarterly\b")),
    ("hn", re.compile(r"(?i)\bH([12])\b(?!\s*20\d\d)")),
    ("fyn", re.compile(r"(?i)\b(?:full[\s\-]*year|for\s+the\s+year|annual|fiscal\s+year)\b(?!\s*20\d\d)")),
    ("span", re.compile(r"(?i)\b(?:two|three|four|five|seven|eight|nine|ten|eleven|\d+)\s+months\b(?:[^.;]{0,70}?(?:ending|ended)\s+\w+\s+\d{1,2},?\s+20\d\d)?|month\s+of\s+(?:" + _MONTHS + r")\b(?!\s+20\d\d)|year[\s\-]+to[\s\-]+date|\bYTD\b|\b(?:first|last)\s+(?:two|three|four|five|seven|eight|nine|ten|eleven)\s+months\b|since\s+(?:the\s+)?(?:commencement|start)")),
    ("yr", re.compile(r"(?<![\d$.,])(20\d\d)(?!\d|,\d)")),
]

# a figure in a clause with any of these just before it is not this period's production
_NOT_PRODUCTION = re.compile(
    r"(?i)(compared\s+(?:to|with)|\bvs\.?|versus|relative\s+to|\bprior\b|last\s+year|same\s+period|previous\s+(?:year|quarter)"
    r"|up\s+from|down\s+from|increase\s+from|from\s+(?:the\s+)?(?:previous|prior)|\bmined\b|contained\s+ounces|recover(?:ed|able)"
    r"|\bplaced\b|(?-i:\b(?:resources?|reserves?)\b)|mineral\s+(?:resources?|reserves?)|inventor|capacity|per\s+annum|annual(?:ly)?\s+average|average|cumulative"
    r"|to\s+date|life[\s\-]+of[\s\-]+mine|\bLOM\b|stockpil|before\s+payable|purchase|put\s+options?|protection|hedg"
    r"|stream|\bPEA\b|feasibility|study|over\s+the\s+next|nameplate|run[\s\-]+rate|historical|since\s+(?:the\s+)?(?:start|commence)"
    r"|expected\s+to\s+average|design)")
_SUFFIX_NOT = re.compile(r"(?i)^\W{0,3}(?:\w+\s+){0,4}?(per\s+(?:year|annum|day|month|week)|annually|a\s+year|/\s*(?:year|yr|day|d)\b|over\s+the\s+(?:next|life))")
_SUFFIX_ORE = re.compile(r"(?i)^\s*(?:\(\W*\w+\W*\)\s*)?(?:of\s+)?(?:ore\b|milled|processed|mined|moved|hauled|placed|stacked|at\s+(?:an\s+)?average\s+grade)|^[^.]{0,30}?at\s+guidance\s+(?:metal\s+)?prices")
_SUFFIX_MONEY = re.compile(r"(?i)^\s*(?:per\s+(?:ounce|oz|tonne|pound|lb)|/\s*(?:oz|t|lb))")

_GUIDE = re.compile(r"(?i)guidance|guided|\bexpects?\b|\bexpected\b|forecast|outlook|target|projected|\bplans?\s+to\s+produce|on\s+track|anticipat")
_GUIDE_PAST = re.compile(r"(?i)\b(?:were|previous(?:ly)?|original(?:ly)?|prior|initial)\b")
_MINE_FOR = re.compile(r"\b(?:for|at)\s+(?:the\s+)?(?!Q[1-4]\b|H[12]\b|FY|Fiscal|The\b|Company|Group|Corporation|Guidance|Production|Full|Year)[A-Z][a-z][\w'’\-]*(?:\s+[A-Z][\w'’\-]+){0,2}")
_MINE_NAMED = re.compile(r"\b(?:[A-Z][\w'’\-]+\s+){1,3}(?:Mine|Operations?)\b|\b(?:at|for|from)\s+(?:the\s+)?(?:[A-Z][\w'’\-]+\s*){1,3}(?:mine|Mine)\b")
_PLAN = re.compile(r"(?i)estimat|expect|forecast|\bwill\b|target|anticipat|\bplans?\b|reiterat|outlook|guidance|guided|projected|on\s+track|potential|could|would")
_SOLD = re.compile(r"(?i)\bsold\b|\bsales?\b|\bdelivered\b")
_PRODUCED = re.compile(r"(?i)produc|poured|\bpour\b|\boutput\b")


def _num(s):
    return float(s.replace(",", ""))


def _norm_unit(tok):
    t = tok.strip().lower()
    for pat, unit, mult, metal in _UNITS:
        if re.fullmatch(pat, t, re.I):
            return unit, mult, metal
    return None, 1, None


def _metal_of(s):
    """The metal a short phrase names (first match), or None."""
    m = _METAL_RE.search(s or "")
    if not m:
        return None
    for i, (_pat, metal) in enumerate(_METALS):
        if m.group(i + 1):
            if metal is None:
                return "GEO" if re.search(r"(?i)geo", m.group(0)) else "AuEq"
            return metal
    return None


def _metal_last(s):
    found = None
    for m in _METAL_RE.finditer(s or ""):
        for i, (_pat, metal) in enumerate(_METALS):
            if m.group(i + 1):
                found = metal if metal else ("GEO" if re.search(r"(?i)geo", m.group(0)) else "AuEq")
                break
    return found


# ------------------------------------------------------------------ text
_FLS = re.compile(r"(?i)cautionary\s+(?:note|statement)s?\b|forward[\s\-]+looking\s+(?:statements?|information)\s*(?:and|\n|$|:|this|certain|except)|"
                  r"this\s+(?:news\s+|press\s+)?release\s+(?:contains|includes)\s+(?:certain\s+)?(?:\"|“)?forward[\s\-]+looking")


def _cut_fls(body):
    """A forward-looking-statements section restates plans ('250,000 ounces in 2026') in the language of fact."""
    b = body or ""
    for m in _FLS.finditer(b):
        if m.start() > 0.3 * len(b):
            return b[:m.start()]
    return b


def _prepare(headline, body):
    text = (headline or "") + "\n\n" + _cut_fls((body or "")[:TEXT_CAP])
    text = text.replace(chr(160), " ")
    # a blank line inside a quote or before a lowercase word or punctuation is a PDF artefact, not a paragraph
    text = re.sub(r"(?<=[(“\"‘])\s*\n\s*\n\s*", "", text)
    text = re.sub(r"\n\s*\n(?=\s*[\"”’)\].,;:]|\s*[a-z])", " ", text)
    # a parenthetical comparative -- '(Q1 2025: 22,790 oz)' -- is the prior period, never this one
    text = re.sub(r"\([^()]{0,80}(?:Q[1-4]|20\d\d|prior|previous)[^()]{0,80}\)", " ", text)
    # 'r ecord', 'full -year', 'Compa ny': PDF extraction splits words; the few that matter are rejoined
    text = re.sub(r"(?i)\bfull\s*-\s*year", "full-year", text)
    return text


_CLAUSE_SPLIT = re.compile(r"\n\s*\n|(?<=[.;!?])\s+(?=[A-Z•“\"(])|[•●▪◦]|\s(?:o|-)\s(?=[A-Z])")


def _clauses(text):
    out, pos = [], 0
    for m in _CLAUSE_SPLIT.finditer(text):
        seg = text[pos:m.start()]
        if seg.strip():
            out.append(" ".join(seg.split()))
        pos = m.end()
    seg = text[pos:]
    if seg.strip():
        out.append(" ".join(seg.split()))
    return out


def _periods(clause):
    """[(start, end, kind, value)] for every period expression, non-overlapping, in order."""
    found = []
    taken = []
    for kind, rx in _PERIOD_RES:
        for m in rx.finditer(clause):
            if any(not (m.end() <= a or m.start() >= b) for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), m.end(), kind, m.groups()))
    found.sort()
    return found


def _resolve(kind, g, doc):
    """A period expression -> 'Q1 2025' | 'H1 2025' | 'FY 2025' | 'Q1 FY2026' | '2025-03' | None."""
    def ordn(x):
        return _ORD.get(str(x).lower(), None) or (int(x) if str(x).isdigit() else None)
    if kind == "fq":
        return "Q%d FY%s" % (ordn(g[0]), g[1])
    if kind == "q":
        return "Q%d %s" % (ordn(g[0]), g[1])
    if kind == "q2":
        y = g[1] if len(g[1]) == 4 else "20" + g[1]
        return "Q%s %s" % (g[0], y)
    if kind == "m3":
        return "Q%d %s" % (_MONTH_Q[g[0].lower()], g[1])
    if kind == "h":
        return "H%d %s" % (1 if g[0].lower() in ("1", "first") else 2, g[1])
    if kind in ("fy", "fy2"):
        y = g[0] if len(g[0]) == 4 else "20" + g[0]
        return "FY %s" % y
    if kind == "mon":
        mi = _MONTHS.split("|").index(g[0].lower()) + 1
        return "%s-%02d" % (g[1], mi)
    if kind == "qn":
        q = ordn(g[0])
        if doc.get("quarter") and doc["quarter"].startswith("Q%d " % q):
            return doc["quarter"]
        if doc.get("fiscal_quarter") and doc["fiscal_quarter"].startswith("Q%d " % q):
            return doc["fiscal_quarter"]
        return ("Q%d %s" % (q, doc["year"])) if doc.get("year") else None
    if kind == "qd":
        return doc.get("quarter") or doc.get("fiscal_quarter")
    if kind == "hn":
        return ("H%s %s" % (g[0], doc["year"])) if doc.get("year") else None
    if kind == "fyn":
        return ("FY %s" % doc["year"]) if doc.get("year") else None
    if kind == "yr":
        return "FY %s" % g[0]
    return None   # 'span': a non-standard span, never a row


def _doc_period(headline, body):
    """The release's own period: the quarter (or year) its headline, or failing that its opening, names."""
    doc = {"quarter": None, "fiscal_quarter": None, "year": None}
    for src in (headline or "", " ".join((body or "")[:900].split())):
        src2 = re.sub(r"(?i)\b(" + _MONTHS + r")\.?\s+\d{1,2},?\s+20\d\d", " ", src)   # a dateline is not a period
        head_year = doc["year"] if src2 is not (headline or "") else None
        for s, e, kind, g in _periods(src2):
            if head_year and re.search(r"20\d\d", src2[s:e]) and head_year not in src2[s:e]:
                continue      # the opening's comparatives ('over Q4 2024') are not the headline year's period
            if kind == "fq" and not doc["fiscal_quarter"]:
                doc["fiscal_quarter"] = _resolve(kind, g, doc)
            elif kind in ("q", "q2", "m3") and not doc["quarter"]:
                doc["quarter"] = _resolve(kind, g, doc)
            if not doc["year"] and kind in ("q", "q2", "m3", "h", "fy", "fy2", "yr", "fq"):
                y = re.search(r"20\d\d", src2[s:e])
                if y:
                    doc["year"] = y.group(0)
                elif kind == "q2":
                    doc["year"] = "20" + g[1][-2:]
        if doc["quarter"] or doc["fiscal_quarter"]:
            break
    if doc["quarter"] and not doc["year"]:
        doc["year"] = doc["quarter"][-4:]
    if doc["fiscal_quarter"] and not doc["year"]:
        doc["year"] = doc["fiscal_quarter"][-4:]
    # a quarter with no year in the headline ('Ramu Q1 Operating Performance') takes the opening's year
    if not doc["quarter"] and headline:
        m = re.search(r"(?i)\bQ([1-4])\b", headline)
        if m and doc["year"]:
            doc["quarter"] = "Q%s %s" % (m.group(1), doc["year"])
    return doc


# ------------------------------------------------------------------ mentions
_MENTION = re.compile(
    r"(?<![\w.,$])(?:(?:approximately|about|over|~)\s*)?" + _NUM + _MULT +
    r"(\s*(?:(?:payable|attributable)\s+)?(?:gold|silver|copper)?\s*)" +
    r"(" + _UNIT_RE + r")", re.I)
_GEO_OF = re.compile(r"(?i)\bgeos?\s+(sold|produced|delivered)?\s*of\s+" + _NUM + r"(?!\d|,\d)")


def _mentions(clause):
    out = []
    for m in _MENTION.finditer(clause):
        num, mult, mid, unit_tok = m.group(1), m.group(2), m.group(3) or "", m.group(4)
        unit, umult, umetal = _norm_unit(unit_tok)
        if unit is None:
            continue
        if unit_tok.lower() == "t" and (mid.strip() or clause[m.start(4) - 1:m.start(4)].isspace()):
            continue          # a bare 't' only glued to the number
        if unit_tok.lower() in ("m", "k"):
            continue
        v = _num(num)
        mm = (mult or "").lower()
        if mm in ("million", "mm") or (mm == "m" and unit == "lb"):
            v *= 1e6
        elif mm in ("thousand", "k"):
            v *= 1e3
        elif mm == "m":
            continue          # '3.4 m' is metres
        v *= umult
        metal = umetal or _metal_of(mid)
        after = clause[m.end():m.end() + 60]
        am = re.match(r"(?i)\s*(?:\(\W*[\w ]{0,12}\W*\)\s*)?(?:of\s+(?:contained\s+|finished\s+|payable\s+|refined\s+)?)?"
                      r"([A-Za-z0-9 ]{2,40})", after)
        if not metal and am:
            if re.match(r"(?i)\s*(?:\(\W*[\w ]{0,12}\W*\)\s*)?of\b", after) or re.match(r"(?i)\s*(au|ag|cu|aueq|ageq)\b", after):
                metal = _metal_of(am.group(1)[:30])
        if not metal:
            m2 = re.match(r"(?i)\s*(gold|silver|copper|zinc|lead|nickel|cobalt|u3o8|au|ag|cu)\b", after)
            if m2:
                metal = _metal_of(m2.group(1))
        if unit == "oz" and re.match(r"(?i)\s*(?:\(\W*[\w ]{0,12}\W*\)\s*)?aueq\b", after):
            metal = "AuEq"
        out.append({"start": m.start(), "end": m.end(), "value": v, "unit": unit, "metal": metal,
                    "approx": bool(re.match(r"(?i)(approximately|about|~)", m.group(0)))})
    for m in _GEO_OF.finditer(clause):
        out.append({"start": m.start(), "end": m.end(), "value": _num(m.group(2)), "unit": "oz", "metal": "GEO",
                    "approx": False, "geo_verb": (m.group(1) or "").lower()})
    out.sort(key=lambda x: x["start"])
    return out


def _period_for(clause, men, periods, doc, nxt, prefer_before=False):
    """The period a figure belongs to: one right after it ('... in Q1 2026') if it is introduced by in/for/
    during, else the nearest one before it in the clause. None if that is a non-standard span."""
    if prefer_before:
        # guidance names its period ahead of the range: 'Issued FY 2025 production guidance of 270,000 tonnes,
        # reinforced by performance achieved in 4Q24' is FY 2025's
        near = [(kind, g) for s, e, kind, g in periods if e <= men["start"] and men["start"] - e <= 70]
        if near:
            return _resolve(near[-1][0], near[-1][1], doc), near[-1][0]
    for s, e, kind, g in periods:
        if s >= men["end"]:
            gap = clause[men["end"]:s]
            # '58,506 ounces of silver and 932 ounces of gold in Q1 2026': a list shares the period after it
            if kind == "span" and len(gap) <= 40:
                return None, "span"      # '160,000 pounds ... in the single month of April'
            listy = (s < nxt and len(gap) <= 45) or (len(gap) <= 120 and not re.search(
                r"(?i)\b(compared|vs|versus|from|sold|sales|up|down|while|with|which|was|were|is|are|had|has|per|at|bringing)\b|[;:$%(]", gap))
            if listy and len(gap) <= 120 and re.search(r"(?i)\b(in|for|during)\s+(?:the\s+)?$", gap) \
                    and not _NOT_PRODUCTION.search(gap) and not re.search(r"(?i)%|increase|decrease|higher|lower", gap):
                return _resolve(kind, g, doc), kind
            break
    best = None
    for s, e, kind, g in periods:
        if e <= men["start"] and men["start"] - e <= 160:
            best = (kind, g)
    if best:
        return _resolve(best[0], best[1], doc), best[0]
    return None, None


def _range_at(clause, men, mentions):
    """A guidance range ending at this figure: 'A to B ounces', 'between A and B', 'A - B GEO'."""
    before = clause[max(0, men["start"] - 40):men["start"]]
    m = re.search(r"(?i)(?:between\s+)?\$?" + _NUM + r"(\s*(?:million|thousand))?(?:\s*(?:ounces|oz|tonnes|pounds))?\s*(?:to|–|—|-|and)\s*\$?$", before)
    if not m:
        return None
    if re.search(r"(?i)\d(?:\s*(?:million|thousand))?\s*and\s*\$?$", before) and \
            not re.search(r"(?i)between\s+\$?[\d,.]+(?:\s*(?:million|thousand))?\s*and\s*\$?$", before):
        return None      # 'A and B' is only a range after 'between'
    low = _num(m.group(1))
    lm = (m.group(2) or "").strip().lower()
    if lm == "million":
        low *= 1e6
    elif lm == "thousand":
        low *= 1e3
    elif men["value"] >= 1e6 and low < 1e3:
        low *= 1e6
    elif men["value"] >= 1e3 and low < men["value"] / 500:
        low *= 1e3
    return low


def _guidance_single(clause, men):
    before = clause[max(0, men["start"] - 70):men["start"]]
    m = re.search(r"(?i)(guidance|guided|target(?:ed)?(?:\s+to\s+be)?|expects?\s+to\s+produce|forecast|projected)"
                  r"(?:\s+\w+){0,3}?\s+(?:of|at|to\s+be|is|to)?\s*(about|approximately|at\s+least|above|more\s+than|in\s+excess\s+of)?\s*$",
                  before)
    if m:
        return "floor" if (m.group(2) or "").lower() in ("at least", "above", "more than", "in excess of") else "point"
    m = re.search(r"(?i)\b(above|at\s+least|more\s+than|in\s+excess\s+of|exceed)\s*$", before)
    if m and _GUIDE.search(clause):
        return "floor"
    return None


# ------------------------------------------------------------------ milestones
_MS = [
    ("commercial_production", re.compile(r"(?i)\b(achiev\w*|declar\w*|announc\w*|reach\w*|attain\w*)\s+(?:of\s+)?commercial\s+production")),
    ("first_pour", re.compile(r"(?i)\bfirst\s+(?:gold\s+|silver\s+|doré\s+|dore\s+)?pour\b|\bpours?\s+first\s+(?:gold|doré|dore)")),
    ("resumption", re.compile(r"(?i)\b(resumes|resumed|restarts|restarted|resumption\s+of\s+\w+\s+(?:achieved|complete))")),
    ("first_production", re.compile(r"(?i)\bproduction\s+(?:and\s+shipment\s+)?of\s+first\b|\bfirst\s+production\b|\bbegins?\s+production\b|\bcommences?\s+production\b")),
    ("first_shipment", re.compile(r"(?i)\bfirst\s+(?:\w+\s+){0,2}shipment\b|\bshipment\s+of\s+first\b|\bfirst\s+\w+\s+(?:\w+\s+)?shipped\b|\bproduction\s+and\s+shipment\s+of\s+first\b")),
]
_MS_NOT = re.compile(r"(?i)\b(toward|towards|on\s+track|expects?|expected|planned|plans|prepar\w*|ahead\s+of|approach\w*|nears?|nearing|moving|path\s+to|targets?|targeting|anticipat\w*|will|decision|update\s+on\s+the\s+restart|suspend\w*)\b")
_ASSET = re.compile(r"\b(?:at|from)\s+(?:the\s+|its\s+)?((?:[A-Z][\w'’\-]+\s+){0,3}[A-Z][\w'’\-]+?)(?:\s+(?:Gold|Graphite|Copper|Silver))?(?:\s+(?:Mine|Project|Operations?|Complex|Plant))?\b")
_ASSET_BEFORE = re.compile(r"\b((?:[A-Z][\w'’\-]+\s+){0,2}[A-Z][\w'’\-]+)\s+(?:Mine|Operations?)\b")


def milestones(headline):
    h = " ".join((headline or "").split())
    if not h or _MS_NOT.search(h):
        return []
    out = []
    for name, rx in _MS:
        if rx.search(h) and not any(o["milestone"] == name for o in out):
            asset = None
            for m in _ASSET.finditer(h):
                cand = m.group(1)
                if cand.lower() not in ("the", "its") and not re.match(r"(?i)^(Q[1-4]|first|record)", cand):
                    asset = cand
                    break
            if not asset:
                m = _ASSET_BEFORE.search(h)
                asset = m.group(1) if m else None
            if asset:
                asset = re.sub(r"(?i)(?:\s+(?:gold|graphite|copper|silver))?\s+(?:mine|project|operations?|complex|plant)$", "", asset).strip() or None
            out.append({"kind": "milestone", "milestone": name, "asset": asset})
    return out


# ------------------------------------------------------------------ analyse
def analyse(headline, body):
    head = " ".join((headline or "").split())
    res = {"is_production": False, "reason": None, "rows": []}
    if not _ANY_PROD.search(head) and not _ANY_PROD.search((body or "")[:TEXT_CAP]):
        res["reason"] = "no_production_language"
        return res
    blob = head + " " + (body or "")[:TEXT_CAP]
    if len(_OIL_GAS.findall(blob)) >= 3:
        res["reason"] = "oil_and_gas"
        return res

    doc = _doc_period(headline, body)
    text = _prepare(headline, body)
    rows = []
    for ci, clause in enumerate(_clauses(text)):
        if len(clause) > 1500 or not re.search(r"\d", clause):
            continue
        mentions = _mentions(clause)
        if not mentions:
            continue
        if len(mentions) >= 3 and not any(m["metal"] for m in mentions) and not re.search(
                r"(?i)\b(gold|silver|copper|zinc|lead|nickel|cobalt|uranium|u3o8|lithium)\b", clause):
            continue      # a flattened table row: its columns are not in the text around it
        periods = _periods(clause)
        guide_clause = bool(_GUIDE.search(clause))
        produced_rows = []
        for i, men in enumerate(mentions):
            nxt = mentions[i + 1]["start"] if i + 1 < len(mentions) else len(clause)
            prev_end = mentions[i - 1]["end"] if i else 0
            pre = clause[max(prev_end, men["start"] - 90):men["start"]]
            pre_long = clause[max(0, men["start"] - 90):men["start"]]
            post = clause[men["end"]:men["end"] + 50]
            if _SUFFIX_NOT.match(post) or _SUFFIX_MONEY.match(post) or _SUFFIX_ORE.match(post):
                continue
            metal = men["metal"]
            if not metal:
                # the metal named just before the figure, within the clause ('copper production of 58,273 tonnes')
                metal = _metal_last(clause[max(0, men["start"] - 70):men["start"]])
            period, pkind = _period_for(clause, men, periods, doc, nxt)
            if pkind == "span":
                continue
            if period is None and not periods and doc.get("quarter") and \
                    not re.search(r"(?i)\byear|annual|months|to\s+date|YTD|since|life", clause):
                period, pkind = doc["quarter"], "doc"

            # ---- guidance
            low = _range_at(clause, men, mentions)
            single = None if low is not None else _guidance_single(clause, men)
            if (low is not None or single) and guide_clause:
                period, pkind = _period_for(clause, men, periods, doc, nxt, prefer_before=True)
                if pkind == "span":
                    continue
                if re.search(r"(?i)inventor|stockpil|to\s+hold|purchase|acqui|\bsales\b|\bsell\b",
                             clause[max(0, men["start"] - 70):men["end"] + 60]):
                    continue      # inventory, purchases and sales ranges are not production guidance
                if _GUIDE_PAST.search(clause[max(0, men["start"] - 110):men["start"]]) or \
                        re.search(r"(?i)annuali[sz]ed|per\s+annum|run[\s\-]+rate|\bper\s+year\b", clause[men["end"]:men["end"] + 40]) or \
                        re.search(r"(?i)including\s+\$?[\d,.]*\s*(?:to|-|–)?\s*$", clause[max(0, men["start"] - 30):men["start"]]):
                    continue
                if _NOT_PRODUCTION.search(clause[max(0, men["start"] - 60):men["start"]]) and \
                        not re.search(r"(?i)guidance", clause[max(0, men["start"] - 60):men["start"]]):
                    continue
                if re.search(r"(?i)\b(cost|aisc|capital|capex|revenue|sales|sold|cash)\b", clause[max(0, men["start"] - 35):men["start"]]):
                    continue
                if not period:
                    continue
                head = clause[:men["start"]]
                if (_MINE_NAMED.search(head[-160:]) or _MINE_FOR.search(head[-170:])) and not re.search(r"(?i)consolidated|total|company|corporate", head[-80:]):
                    continue      # a mine's own guidance is not the company's (B2Gold's Goose, Equinox's Greenstone)
                if low is not None:
                    row = {"kind": "guidance", "period": period, "metal": metal, "low": low, "high": men["value"],
                           "unit": men["unit"]}
                elif single == "floor":
                    row = {"kind": "guidance", "period": period, "metal": metal, "low": men["value"], "high": None,
                           "unit": men["unit"]}
                else:
                    row = {"kind": "guidance", "period": period, "metal": metal, "low": men["value"],
                           "high": men["value"], "unit": men["unit"]}
                rows.append(row)
                continue
            if low is not None:
                continue      # a range outside guidance language is not a figure of anything

            # ---- actual
            if _NOT_PRODUCTION.search(pre_long[-70:]):
                continue
            role = None
            if re.match(r"(?i)\s*(?:\(\W*\w+\W*\)\s*)?(?:were\s+|was\s+|have\s+been\s+)?(sold|delivered)\b", post) or \
                    re.match(r"(?i)\s*(?:of\s+)?sales\b", post):
                role = "sold"
            elif re.match(r"(?i)\s*(?:\(\W*\w+\W*\)\s*)?(?:were\s+|was\s+)?(produced|poured)\b|\s*of\s+production\b", post):
                role = "produced"
            elif men.get("geo_verb"):
                role = "sold" if men["geo_verb"] in ("sold", "delivered") else "produced"
            else:
                kp = [(m.start(), "produced") for m in _PRODUCED.finditer(pre)] + \
                     [(m.start(), "sold") for m in _SOLD.finditer(pre)]
                if kp:
                    role = max(kp)[1]
                elif _PRODUCED.search(pre_long) and not _SOLD.search(pre_long):
                    role = "produced"
            if role is None or not period:
                continue
            if (_GUIDE.search(pre) or _PLAN.search(pre_long)) and not re.search(
                    r"(?i)\b(produced|poured|production\s+(?:was|totall?ed|reached|of\s+(?:approximately\s+)?[\d,.]+\s*\w*\s*(?:in|for|during)\b))", pre + clause[men["start"]:men["end"] + 25]):
                continue      # in a sentence about plans, only a figure the release says was produced is an actual
            row = {"kind": "actual", "period": period, "metal": metal, "qty": men["value"], "unit": men["unit"],
                   "role": role, "approx": men["approx"], "_clause": ci,
                   "_mine": bool(re.search(r"(?i)\b(?:the\s+)?[A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+){0,2}\s+mine\s+(?:has\s+)?(?:produced|production)\b", pre_long)
                                 or re.match(r"(?:At|From)\s+(?:the\s+)?[A-Z]", clause))}
            if role == "produced":
                produced_rows.append(row)
            rows.append(row)
        # AISC stated in the same clause as a single produced figure goes on that row
        if len(produced_rows) == 1:
            m = re.search(r"(?i)\bAISC\b[^.]{0,60}?\$\s?([\d,]+(?:\.\d+)?)\s*(?:per|/)\s*(?:ounce|oz)", clause)
            if m:
                produced_rows[0]["aisc"] = _num(m.group(1))

    g = len(re.findall(r"(?i)\bgold\b", text[:4000]))
    sv = len(re.findall(r"(?i)\bsilver\b", text[:4000]))
    rows = _consolidate(rows, "gold" if g >= 3 * max(sv, 1) else "silver" if sv >= 3 * max(g, 1) else None)
    for ms in milestones(headline):
        rows.append(ms)
    res["rows"] = rows[:40]
    res["is_production"] = bool(rows)
    res["reason"] = "rows" if rows else "no_rows"
    return res


_OZ_METALS = {"gold", "silver", "GEO", "AuEq", "AgEq", "palladium", "platinum"}


def _unit_fits(metal, unit):
    if metal in _OZ_METALS:
        return unit == "oz"
    if metal == "U3O8":
        return unit == "lb"
    return unit in ("t", "lb")


def _consolidate(rows, doc_metal=None):
    """One row per (kind, period, metal): the first statement wins (headline and highlights come first),
    a sold figure joins its produced row, and a royalty company's GEOs sold stand in for production."""
    # a figure whose metal the clause never named takes the release's only metal in that unit
    named = {(r["unit"], r["metal"]) for r in rows if r["kind"] == "actual" and r.get("metal")}
    for r in rows:
        if r["kind"] in ("actual", "guidance") and not r.get("metal"):
            ms = {m for u, m in named if u == r["unit"]}
            r["metal"] = ms.pop() if len(ms) == 1 else (doc_metal if r["unit"] == "oz" else None)
    rows = [r for r in rows if r.get("metal") and _unit_fits(r["metal"], r["unit"])]
    # a royalty company reporting GEOs quotes its partners' mines in ounces: those are not its production
    if any(r.get("metal") == "GEO" for r in rows):
        rows = [r for r in rows if r["kind"] != "actual" or r["metal"] in ("GEO", "AuEq")]
    out, seen = [], {}
    sold = {}
    for r in rows:
        if r["kind"] == "actual" and r.get("role") == "sold":
            sold.setdefault((r["period"], r["metal"], r.get("_clause")), r)
            continue
        key = (r["kind"], r["period"], r["metal"])
        if key in seen:
            old = seen[key]
            # two actuals for one metal and period: a named mine's gives way to the company's ('the La Colorada
            # mine produced 58,288' vs Heliostar's 79,710); otherwise the first statement stands
            if r["kind"] == "actual" and old.get("_mine") and not r.get("_mine"):
                out[out.index(old)] = r
                seen[key] = r
            elif r.get("aisc") and not old.get("aisc") and r.get("qty") == old.get("qty"):
                old["aisc"] = r["aisc"]
            continue
        seen[key] = r
        out.append(r)
    for (period, metal, ci), s in sold.items():
        key = ("actual", period, metal)
        if key in seen and seen[key].get("_clause") == ci:
            seen[key].setdefault("sold", s["qty"])
        elif key not in seen and metal == "GEO":
            row = {"kind": "actual", "period": period, "metal": "GEO", "qty": s["qty"], "unit": "oz",
                   "basis": "sold", "role": "produced"}
            seen[key] = row
            out.append(row)
    for r in out:
        r.pop("role", None)
        r.pop("_clause", None)
        r.pop("_mine", None)
        if not r.get("approx"):
            r.pop("approx", None)
    return out


# ------------------------------------------------------------------ facts store adapter
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["rows"]:
        return [F.Record(KIND, facts=[F.Fact("is_production", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"])], confidence=0.0)]
    out = []
    for r in a["rows"]:
        fs = [F.Fact("is_production", value_num=1.0)]
        for k in TXT_FIELDS:
            if r.get(k):
                fs.append(F.Fact(k, value_text=str(r[k])[:120]))
        for k in NUM_FIELDS:
            if r.get(k) is not None:
                fs.append(F.Fact(k, value_num=float(r[k])))
        if r.get("approx"):
            fs.append(F.Fact("approx", value_num=1.0))
        out.append(F.Record(KIND, facts=fs, confidence=1.0))
    return out


def parse_records(rows_by_ordinal):
    """{ordinal: [(field, seq, value_num, value_text)]} -> the analyse()-shaped dict."""
    rows = []
    for ordinal in sorted(rows_by_ordinal):
        r = {k: None for k in TXT_FIELDS + NUM_FIELDS}
        is_p = False
        for field_, seq, num, text in rows_by_ordinal[ordinal]:
            if field_ == "is_production":
                is_p = num == 1.0
            elif field_ in NUM_FIELDS:
                r[field_] = num
            elif field_ in TXT_FIELDS:
                r[field_] = text
            elif field_ == "approx":
                r["approx"] = True
        if is_p and r["kind"]:
            rows.append(r)
    return {"is_production": bool(rows), "rows": rows}


JUDGED = ("kind", "period", "metal", "unit", "qty", "low", "high", "sold", "aisc", "milestone", "asset", "basis")


def to_prediction(records):
    if not records:
        return None
    rows = {i: [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts] for i, rec in enumerate(records)}
    p = parse_records(rows)
    if not p["rows"]:
        return None
    return {"rows": [{k: r.get(k) for k in JUDGED} for r in p["rows"]]}


def _code_sha():
    import hashlib
    h = hashlib.sha1()
    with open(__file__, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


SPEC = F.ExtractorSpec(NAME, VERSION, KIND, TAG, extract, _code_sha())


# ------------------------------------------------------------------ self-test
def self_test(verbose=False):
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))
        elif verbose:
            print("  ok   %s" % name)

    def rows(h, b=""):
        return [{k: v for k, v in r.items() if v is not None} for r in analyse(h, b)["rows"]]

    # TXG.TO 2bad6ed8b104 -- two periods in one sentence, the year only in the headline
    r = rows("Torex Gold Delivers on Full-Year Production Guidance 2024 marks the sixth consecutive year",
             "Torex Gold Resources Inc. reports fourth quarter gold production of 103,795 ounces (\"oz\") and "
             "full-year gold production of 452,523 oz, within the Company's revised guidance range of 450,000 to "
             "470,000 oz (original guidance of 400,000 to 450,000 oz). Fourth quarter and full-year gold sold were "
             "108,647 oz and 455,932 oz, respectively.")
    eq("TXG actuals", [(x["kind"], x["period"], x["metal"], x.get("qty")) for x in r if x["kind"] == "actual"],
       [("actual", "Q4 2024", "gold", 103795.0), ("actual", "FY 2024", "gold", 452523.0)])
    # EQX.TO 8a6c98feb70b -- the headline states both
    r = rows("Equinox Gold Reports Record Quarterly and Annual Gold Production: Produced 213,960 Ounces of Gold in "
             "Q4 2024 and 621,870 Ounces of Gold for Full-Year 2024")
    eq("EQX headline", [(x["period"], x["qty"]) for x in r], [("Q4 2024", 213960.0), ("FY 2024", 621870.0)])
    # AAUC.TO f22e73961e8c -- 'during the quarter' takes the headline's quarter; sold after 'and sold'
    r = rows("ALLIED GOLD REPORTS THIRD QUARTER 2025 RESULTS",
             "The Company produced 87,020 ounces of gold during the quarter and sold 92,099 ounces of gold during "
             "the same period. Annual production is expected to be above 375,000 gold ounces which is in line with "
             "the Company's guidance and consistent with Allied's broader production outlook from its producing "
             "mines of 375,000 to 400,000 ounces of gold per annum.")
    eq("AAUC actual", [(x["period"], x["qty"], x.get("sold")) for x in r if x["kind"] == "actual"],
       [("Q3 2025", 87020.0, 92099.0)])
    eq("AAUC floor guidance, and no per-annum outlook",
       [(x["period"], x.get("low"), x.get("high")) for x in r if x["kind"] == "guidance"], [("FY 2025", 375000.0, None)])
    # SM.V 64f3e2da9534 -- produced vs sold, and the comparative after it
    r = rows("Sierra Madre Reports Strong Q1 2026 Financial Results, Record Quarterly Revenues 128,827 Silver "
             "Equivalent Ounces Sold in Q1 2026",
             "Production: Sierra Madre produced 58,506 ounces of silver and 932 ounces of gold in Q1 2026, compared "
             "to production of 70,176 ounces of silver and 1,001 ounces of gold in Q1 2025.")
    eq("SM produced, not sold, not comparative", sorted((x["metal"], x["qty"]) for x in r if x["kind"] == "actual"),
       [("gold", 932.0), ("silver", 58506.0)])
    # VMET.TO bc1f6ad9743f -- a royalty company's GEOs sold are its production
    r = rows("Versamet Royalties Delivers Record GEOs for 2025 and Provides 2026 Guidance",
             "Record Q4 attributable GEOs sold of 4,430, an increase of 260% over Q4 2024; Record annual attributable "
             "GEOs sold of 9,815, an increase of 94% over 2024. Versamet expects 2026 attributable GEOs to be between "
             "20,000 to 23,000 at an average cash cost margin of approximately 93%.")
    eq("VMET GEO", [(x["kind"], x["period"], x.get("qty")) for x in r if x["kind"] == "actual"],
       [("actual", "Q4 2025", 4430.0), ("actual", "FY 2025", 9815.0)])
    # a study's average production is not production (PUR.V 7463a2c43368)
    eq("PEA average", rows("Premier American Uranium Announces Preliminary Economic Assessment",
                           "PEA outlines base case production averaging 1.4 Mlb U3O8 annually over a 13-year mine life "
                           "for total output of 18.1 Mlb"), [])
    # EQX.TO cd4b1332829f -- a ten-year average in the headline
    eq("ten-year average", rows("Equinox Gold Updates Canadian Operations Technical Outlook: Average 540,000 Ounces "
                                "Gold Production per Year for Next 10 Years"), [])
    # oil and gas is out of scope
    eq("oil and gas", rows("Lotus Creek Announces First Quarter 2026 Operating Results",
                           "Production averaged 1,250 boe/d in Q1 2026 (62% crude oil and NGLs); natural gas 2.1 mmcf/d. "
                           "Produced 112,500 barrels of oil."), [])
    # milestones: a completed event is a row; one that is still ahead is not
    eq("commercial production", [(x["milestone"], x["asset"]) for x in rows("B2Gold Achieves Commercial Production at the Goose Mine")],
       [("commercial_production", "Goose")])
    eq("first pour", [(x["milestone"], x["asset"]) for x in rows("Abcourt Announces First Gold Pour at Sleeping Giant Mine")],
       [("first_pour", "Sleeping Giant")])
    eq("moving toward a first pour", rows("Royalty Update: Moss Mine Moving Toward First Pour"), [])
    eq("on track for a restart", rows("Bunker Hill on Track for June Restart of Operations"), [])
    # the facts-store round trip
    back = to_prediction(extract("Artemis Gold Announces Q1 2026 Production Results",
                                 "Blackwater produced 61,923 ounces of gold in Q1 2026. The Company is maintaining its "
                                 "full year production guidance of 265,000 to 290,000 ounces of gold."))
    eq("round trip", [(x["kind"], x["period"], x["qty"], x["low"], x["high"]) for x in back["rows"]],
       [("actual", "Q1 2026", 61923.0, None, None), ("guidance", "FY 2026", None, 265000.0, 290000.0)])
    print("production %s: %s" % (VERSION, "ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if self_test(verbose=True) else 0)
