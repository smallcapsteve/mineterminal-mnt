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

1.2.1 (2026-09-26): onto the shared project-name helper portal/project_names.py. Production names a project only on a
milestone row (actual and guidance rows are the company's own figures and carry none). The milestone's asset is still
1.2.0's own headline reading (_milestone_asset), and the helper corrects it:
  - a project the helper reads in the headline (PN.find), in this page's form (no trailing Mine/Project/Operations or
    metal words, no leading place: "Saskatchewan Canada Cigar Lake Mine" -> "Cigar Lake"), fills a blank ("Oksut") and
    replaces 1.2.0's name when the two share a word ("Their Salar De Arizaro" -> "Salar De Arizaro", "Underground
    Omagh" -> "Omagh", "Equinox Gold's Greenstone" -> "Greenstone"), or when 1.2.0's name is not a project the release
    names ("Southern Pits" -> "Rosebel", "Fermont" -> "Bloom Lake");
  - with no helper name in the headline, a blank or a name the release never calls a project takes the helper's main
    project (PN.primary) only when it is the one project the opening text names (a regional update such as "resumes
    operations in Ontario" over Springpole and Goldlund names none);
  - a list ("Biox Expansion and Lafigue Growth Projects") or a description ("Only Producing Graphite Mine") is not taken.
The fingerprint follows the helper (portal/fingerprint.py).

1.3.0 (2026-09-28, PROD13):
  - YEAR-TO-DATE ROWS (decision #37, Justin 2026-09-24: half-year and year-to-date figures are rows, labelled H1 /
    YTD). "nine months ended September 30, 2025" and "first nine months of 2025" are period 9M 2025; "year-to-date"
    / "YTD" takes the release's own quarter (Q2 -> H1, Q3 -> 9M, Q4 -> FY; Q1 is the quarter itself, not a row);
    "first six months of 2025" is H1 2025. Rule 5 is narrowed accordingly: a year-to-date total is a row.
  - RECOVERED ROWS (Justin 2026-09-28: "Not production. Make a new line specifically for recovered ounces").
    Rule 3 is unchanged -- a recovered figure is never production. A figure the release says was recovered
    ("9,621 ounces of gold were recovered during the quarter", a table's "Gold Recovered oz" line) is a row of
    kind 'recovered', for its period and metal, shown apart from produced rows. The same period rules apply;
    studies, royalty thresholds ("the first 400,000 ounces recovered"), history and single months are not rows.
    A sold figure joins the recovered row when the release states no produced figure for that period and metal.
    A table whose header runs the quarters up to the release's own (Mako: Q1 2025 ... Q4 2025) is read in its
    last column for recovered and sold lines only.

1.3.1 (2026-09-29, PROD131 - reader review fix 2):
  - "2026 second-quarter results" / "2025 fourth-quarter and full-year" (the year first) are the release's quarter
    (Kinross: its Q2 2026 release was read as FY 2025).
  - "492,326 Au eq. oz." is a gold-equivalent figure ("Ag eq. oz." silver-equivalent).
  - A cell of a flattened table row followed by the next row's label ("Sold 499,035 526,223 993,163 1,050,312
    Attributable gold equivalent ounces") is not a figure of that label (Kinross FY rows; Santacruz's lead read as copper).
  - A period a comparison introduces ("a decrease of 4% over Q3 Fiscal 2025", "compared to 1.8 million ounces in
    Q1 Fiscal 2025", "relative to Q2 2025") is never a figure's own period (Silvercorp's quarters were labelled a year
    early); a parenthetical naming two metals ("silver equivalent (only silver and gold)") is not the figure's metal.
    The compared figure itself is not a row either: "6% higher than Q1-2021 production of 15.5 M lbs" (Amerigo),
    "compared to 2.1 million ounces", "(or 100,102 ounces) greater than", "a 25,000 GEO reduction"; "September 30,
    2023 and 2022" makes 2022 the comparative column.
  - A bullet under a "2023 Highlights" / "Financial Highlights - Q2 2026 compared to Q2 2025" heading takes that
    heading's period -- not a guidance, reserve or study heading, not "Fourth Quarter and Full Year" (either), not a
    fiscal-year release's; under "ANNUAL ... HIGHLIGHTS" / "2018 Annual Review" a Q4 release's undated figure is the
    year's (DPM, Taseko); an "About <Company>" paragraph's figure is never the quarter's; "in the nine months ended
    2025" is 9M; "Silver Equivalent Ounces produced of 3,424,817"; PDF ligatures ("produc \u019fon") are rejoined.
  - Footnote marks glued to a word ("GEOs1 sold", "ounces1", "Production1") are dropped; "earned" GEOs are a royalty
    company's production; a royalty company's '(\u201cGEOs\u201d)' keeps GEO (a producer's stays AuEq); "GEOs of other metals"
    and "in years 2029 to 2033" are not figures; a GEO release is not rejected as oil and gas (Franco-Nevada).
  - A royalty company's partners' guidance ("Equinox Gold expects Greenstone to produce ...") and one segment's GEOs
    ("from our Precious Metal assets") are not the company's ("for the mine", "deliveries", "most recent guidance");
    a figure an "excludes ..." footnote names is not a row ("excluding C\u00f4t\u00e9 Gold, ... is expected" still is);
    "160,000-180,000 ounces for 2018-2019" is not a year's guidance. A royalty company's per-metal guidance must be
    "attributable" or name the company (Wheaton's own, B2Gold's), and "<Partner> has disclosed ... guidance" /
    "guidance for the asset" is not a row. A royalty company is one the release says "is a ... royalty company" (or
    whose name has "Royalt" in it), not one that mentions a counterparty ("payable to Nomad Royalty Company", Mineros).
  - A dropped comparison figure still names the release's metal ("Gold sales decreased from 370koz", Endeavour); a
    figure compared only with last year is the year's in a Q4 / year-end release ("13.2 million ounces, a 13% increase
    over 2018", First Majestic); "increased by 2% (2,972 ounces)" is a change.

1.3.2 (2026-10-03/04, FIX5 - reader fixes round 5, round 2). Round 1 lost precision on the held-back half, so each change
was kept only if the rows it adds on the dev folds (ACC150c dev + ACC150d) were at least 92% right, on 4+ releases, it
removed no right row, and none of its rows was wrong on the reviewed answer key (NOTES_FIX5.md, marginal.py). Kept:
  - TABLE COLUMNS. A table's header is laid out column by column ('Three months ended June 30, Six months ended June 30,
    2026 2025 2026 2025', 'Q2 2026 Q2 2025 H1 2026 H1 2025', 'Q4 2025 Q4 2024 2025 2024'); besides the release's own quarter
    its year to date (H1 / 9M / FY) and, after a fourth quarter, the year are read from a line with as many cells as the
    header has columns, for production, the sales line under it and AISC.
  - GUIDANCE TABLES. '2024 Guidance Copper production (tonnes) 59,000 - 72,000 ...', 'Guidance 2022 2023 2024 Copper (000 t)
    258 - 282 250 - 274 ...': one range per year the header names; in a mine-by-mine table only the Total block. Such a
    range is never read as an actual table cell or an AISC.
  - ENDED GUIDANCE (decision 9). Guidance for a period the release's own quarter shows has ended goes on that period's
    actual row as guided_low / guided_high (new fields) when the two agree in size, and is not a guidance row; so does a
    figure's own '(guidance range: 135,000 - 144,000 oz)'.
  - UNITS. '1.7 million oz silver equivalent' is AgEq; 'silver equivalent oz', 'AuEq Ounces'.
  - COMPARATIVES. 'the same quarter in 2023' and a 'peak annual' rate are not this period's production.
  - BASIS (a field only). A release that states its production on a 100% basis says so on its rows.

Self-tests: python3 -m portal.extractors.production
"""
from __future__ import annotations

import re

from portal import facts as F
from portal import fingerprint as FP
from portal import project_names as PN   # 1.2.1: the shared project-name helper

NAME = "production"
VERSION = "1.3.2"  # 2026-09-29: year-first quarters, Au eq. oz., comparative periods, highlight headings, royalty GEOs (PROD131); 2026-10-03 FIX5 (round 2, marginal-precision rule): half-year / nine-month / year table columns, guidance tables, ended guidance folded onto actuals (guided), equivalent-ounce units, same-quarter and peak-rate comparatives
KIND = "production_row"
TAG = "Production Results"
TEXT_CAP = 40000

NUM_FIELDS = ("qty", "low", "high", "sold", "aisc", "guided_low", "guided_high")   # 1.3.2: guided on the actual row
TXT_FIELDS = ("kind", "period", "metal", "unit", "milestone", "asset", "basis")

# ------------------------------------------------------------------ vocabulary
_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_MULT = r"(?:\s*(million|thousand|mm|m|k)\b)?"

# unit token -> (unit, multiplier, implied metal)
_UNITS = [
    (r"au\s*eq\.?\s*oz\.?", "oz", 1, "AuEq"),          # 1.3.1: '492,326 Au eq. oz.' (Kinross)
    (r"ag\s*eq\.?\s*oz\.?", "oz", 1, "AgEq"),
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
    (r"gold\s+equivalent\s+(?:ounces?|oz\b)", "oz", 1, "AuEq"),
    (r"silver\s+equivalent\s+(?:ounces?|oz\b)", "oz", 1, "AgEq"),     # 1.3.2: '31.1 million silver equivalent oz'
    (r"au\s*eq\s+ounces?", "oz", 1, "AuEq"),          # 1.3.2: '60,000 - 70,000 AuEq Ounces'
    (r"ag\s*eq\s+ounces?", "oz", 1, "AgEq"),
]
_UNIT_RE = "|".join("(?:%s)" % u[0] for u in _UNITS)

_METALS = [
    (r"gold\s+equivalent|\bgeos?\b", None),     # resolved by the unit
    (r"\bauEq\b|oz\s+aueq", "AuEq"),
    (r"\bagEq\b|oz\s+ageq|silver\s+equivalent", "AgEq"),     # 1.3: 'silver equivalent production of 6.8 million ounces' (EDR)
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
    ("span", re.compile(r"(?i)\b(?:first|last|final)\s+\d+\s+days\b(?:\s+of\s+(?:Q[1-4][\s\-]*20\d\d|the\s+quarter|20\d\d)\b)?")),   # 1.3 (USA)
    ("fq", re.compile(r"(?i)\bQ([1-4])\s+fiscal\s+(?:year\s+)?(20\d\d)\b")),
    ("fq", re.compile(r"(?i)\b(first|second|third|fourth)\s+quarter\s+(?:of\s+)?fiscal\s+(?:year\s+)?(20\d\d)\b")),
    ("q", re.compile(r"(?i)\bQ([1-4])(?:[\s\-/]*|,\s*)(?:FY\s*)?(20\d\d)\b")),
    ("q2", re.compile(r"(?i)\b([1-4])Q[\s\-]*(\d\d(?:\d\d)?)\b")),
    ("q", re.compile(r"(?i)\b(first|second|third|fourth|1st|2nd|3rd|4th)[\s\-]+quarter,?\s+(?:of\s+|ended\s+\w+\s+\d+,?\s+)?(20\d\d)\b")),
    # 1.3.1: the year first - 'Kinross reports strong 2026 second-quarter results' (groups swapped in _periods)
    ("qy", re.compile(r"(?i)\b(20\d\d)[\s\-]+(first|second|third|fourth|1st|2nd|3rd|4th)[\s\-]+quarter\b")),
    ("m3", re.compile(r"(?i)\bthree\s+months\s+ended\s+(march|june|september|december)\s+3[01],?\s+(20\d\d)\b")),
    ("h", re.compile(r"(?i)\bH([12])[\s\-]*(20\d\d)\b")),
    ("h", re.compile(r"(?i)\b(first|second)\s+half\s+(?:of\s+)?(20\d\d)\b")),
    # 1.2 (decision #37, Justin 2026-09-24: half-year figures are rows, labelled H1 / H2): 'six months ended June 30, 2025'
    ("h6", re.compile(r"(?i)\b(?:six|6)\s+months\s+ended\s+(june|december)\s+3[01],?\s+(20\d\d)\b")),
    # 1.3 (decision #37: year-to-date figures are rows): 'nine months ended September 30, 2025', 'first nine months of
    # 2022', 'first six months of 2025', 'year-to-date' / 'YTD' (resolved against the release's own quarter)
    ("m9", re.compile(r"(?i)\b(?:nine|9)[\s\-]+months?\s+ended\s+sept(?:ember|\.)?\s+30,?\s+(20\d\d)\b")),
    ("m9", re.compile(r"(?i)\bfirst\s+nine\s+months\s+(?:of\s+)?(20\d\d)\b")),
    ("m9", re.compile(r"(?i)\b(?:nine|9)[\s\-]+months?\s+ended,?\s+(20\d\d)\b")),     # 1.3.1: 'In the nine months ended 2025' (SCZ)
    ("m9", re.compile(r"(?i)\b(?:first\s+)?three\s+quarters\s+(?:ended|of)\s+(?:sept(?:ember|\.)?\s+30,?\s+)?(20\d\d)\b")),   # 'For the three quarters ended 2019' (USA)
    ("h6b", re.compile(r"(?i)\bfirst\s+six\s+months\s+(?:of\s+)?(20\d\d)\b")),
    ("ytdm", re.compile(r"(?i)\byear[\s\-]+to[\s\-]+date(?:\s+basis)?\s+(?:at\s+the\s+end\s+of|through|to)\s+(june|september|december)(?:\s+3[01])?,?\s+(20\d\d)\b")),
    ("span", re.compile(r"(?i)\b(?:over|in|during)\s+(?:the\s+)?(?:first\s+|last\s+|past\s+)?(?:two|three|four)\s+quarters\b")),
    ("ytd", re.compile(r"(?i)\b(?:(20\d\d)\s+)?(?:year[\s\-]+to[\s\-]+date|YTD)\b(?:\s+(20\d\d)\b)?")),
    ("fy", re.compile(r"(?i)\b(?:full[\s\-]*year|fiscal\s+year|financial\s+year|FY|year[\s\-]+end(?:ed)?|annual)[\s\-]*(20\d\d)\b")),
    ("fy", re.compile(r"(?i)\bFY\s*'?(\d\d)\b")),
    ("fy2", re.compile(r"(?i)\b(20\d\d)\s+(?:full[\s\-]*year|annual|fiscal\s+year)\b")),
    ("mon", re.compile(r"(?i)\b(?:month\s+of\s+)(" + _MONTHS + r")\s+(20\d\d)\b")),
    # without a year: resolved against the release's own period
    ("qn", re.compile(r"(?i)\bQ([1-4])\b(?!,?\s*(?:20\d\d|fiscal))")),
    ("qn", re.compile(r"(?i)\b(first|second|third|fourth|1st|2nd|3rd|4th)[\s\-]+quarter\b(?!,?\s+(?:of\s+)?(?:20\d\d|fiscal))")),
    ("qd", re.compile(r"(?i)\b(?:the|this)\s+quarter\b|\bquarterly\b")),
    ("hn", re.compile(r"(?i)\bH([12])\b(?!\s*20\d\d)")),
    ("fyn", re.compile(r"(?i)\b(?:full[\s\-]*year|for\s+the\s+year|annual|fiscal\s+year)\b(?!\s*20\d\d)")),
    ("span", re.compile(r"(?i)\b(?:two|three|four|five|seven|eight|nine|ten|eleven|\d+)\s+months\b(?:[^.;]{0,70}?(?:ending|ended)\s+\w+\s+\d{1,2},?\s+20\d\d)?|month\s+of\s+(?:" + _MONTHS + r")\b(?!\s+20\d\d)|year[\s\-]+to[\s\-]+date|\bYTD\b|\b(?:first|last)\s+(?:two|three|four|five|seven|eight|nine|ten|eleven)\s+months\b|since\s+(?:the\s+)?(?:commencement|start)"
                        # 1.2: 'production from November 26, 2025 to December 31, 2025' (HMMC), 'from January through June 2026'
                        r"|\bfrom\s+(?:" + _MONTHS + r")(?:\s+\d{1,2})?,?(?:\s+20\d\d)?\s+(?:to|through|until)\s+(?:" + _MONTHS + r")\b")),
    ("yr", re.compile(r"(?<![\d$.,])(20\d\d)(?!\d|,\d)")),
]

# a figure in a clause with any of these just before it is not this period's production
_NOT_PRODUCTION = re.compile(
    r"(?i)(compared\s+(?:to|with)|\bvs\.?|versus|relative\s+to|\bprior\b|last\s+year|same\s+(?:period|quarter)|previous\s+(?:year|quarter)"
    r"|up\s+from|down\s+from|increase\s+from|from\s+(?:the\s+)?(?:previous|prior)|\bmined\b|contained\s+ounces|recover(?:ed|able)"
    r"|\bplaced\b|(?-i:\b(?:resources?|reserves?)\b)|mineral\s+(?:resources?|reserves?)|inventor|capacity|per\s+annum|annual(?:ly)?\s+average|average|cumulative"
    r"|(?<!year\s)(?<!year-)to\s+date|life[\s\-]+of[\s\-]+mine|\bLOM\b|stockpil|before\s+payable|purchase|put\s+options?|protection|hedg"
    r"|stream|\bPEA\b|feasibility|study|over\s+the\s+next|nameplate|run[\s\-]+rate|historical|since\s+(?:the\s+)?(?:start|commence)"
    r"|expected\s+to\s+average|design|\bpeak\b"     # 1.3.2: 'same quarter in 2023'; 'peak annual copper production of 800,000 tonnes'
    r"|\b(?:impact\w*|calculation|affect\w*|reduc\w*|increas\w*|decreas\w*|lower\w*|higher)\b[^.;]{0,50}\bby\s+(?:approximately\s+|about\s+|~)?$)")   # 1.3
_SUFFIX_NOT = re.compile(r"(?i)^\W{0,3}(?:\w+\s+){0,4}?(per\s+(?:year|annum|day|month|week)|annually|a\s+year|/\s*(?:year|yr|day|d)\b|over\s+the\s+(?:next|life))")
_SUFFIX_ORE = re.compile(r"(?i)^\s*(?:\(\W*\w+\W*\)\s*)?(?:of\s+)?(?:ore\b|milled|processed|mined|moved|hauled|placed|stacked|at\s+(?:an\s+)?average\s+grade)")
# '269,846 oz AuEq at guidance metal prices' restates an actual; a guidance range may be stated that way (1.1)
_SUFFIX_GPRICE = re.compile(r"(?i)^[^.]{0,30}?at\s+guidance\s+(?:metal\s+)?prices")
_SUFFIX_MONEY = re.compile(r"(?i)^\s*(?:per\s+(?:ounce|oz|tonne|pound|lb)|/\s*(?:oz|t|lb))")

_GUIDE = re.compile(r"(?i)guidance|guided|\bexpects?\b|\bexpected\b|forecast|outlook|target|projected|\bplans?\s+to\s+produce|on\s+track|anticipat")
_GUIDE_PAST = re.compile(r"(?i)\b(?:were|previous(?:ly)?|original(?:ly)?|prior|initial)\b")
_MINE_FOR = re.compile(r"\b(?:for|at)\s+(?:the\s+)?(?!Q[1-4]\b|H[12]\b|FY|Fiscal|The\b|Company|Group|Corporation|Guidance|Production|Full|Year)[A-Z][a-z][\w'\u2019\-]*(?:\s+[A-Z][\w'\u2019\-]+){0,2}")
_MINE_NAMED = re.compile(r"\b(?:[A-Z][\w'\u2019\-]+\s+){1,3}(?:Mine|Operations?)\b|\b(?:at|for|from)\s+(?:the\s+)?(?:[A-Z][\w'\u2019\-]+\s*){1,3}(?:mine|Mine)\b")
_PLAN = re.compile(r"(?i)estimat|expect|forecast|\bwill\b|target|anticipat|\bplans?\b|reiterat|outlook|guidance|guided|projected|on\s+track|potential|could|would")
_SOLD = re.compile(r"(?i)\bsold\b|\bsales?\b|\bdelivered\b")
_PRODUCED = re.compile(r"(?i)produc|poured|\bpour\b|\boutput\b|\bearned\b")   # 1.3.1: 'OR Royalties earned 20,757 ... GEOs' 


def _last_part(s):
    """The part of a window after its last ', and' / ', but' / ';' ('... similar to the previous quarters of 2025,
    and we expect to produce about 40,000 ounces': only 'we expect to produce about') (1.1)."""
    m = list(re.finditer(r",\s+(?:and|but|while|with)\s+|;\s+", s))
    return s[m[-1].end():] if m else s


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
                  r"this\s+(?:news\s+|press\s+)?release\s+(?:contains|includes)\s+(?:certain\s+)?(?:\"|\u201c)?forward[\s\-]+looking")


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
    text = text.replace("\u2010", "-").replace("\u2011", "-")     # 1.3: 'Q3\u20102023', 'Year\u2010to\u2010date' (USA)
    # 1.3.1: a table's 'Other Metals (GEOs)' row is a part of the total (WPM)
    text = re.sub(r"(?i)\bOther\s+Metals\s*\(\s*GEOs?\s*\d?\s*\)[^\n]*", " ", text)
    # 1.3.1: PDF ligatures - 'produc \u019fon', 'a \u01a9ributable', '\ufb01rst' (USA)
    text = re.sub(r"(?<=[a-z])\s?\u019f\s?(?=[a-z])|(?<=\s)\u019f(?=[a-z])", "ti", text)
    text = re.sub(r"(?<=[a-z])\s?\u01a9\s?(?=[a-z])|(?<=\s)\u01a9(?=[a-z])", "tt", text)
    text = text.replace("\ufb01", "fi").replace("\ufb02", "fl").replace("\ufb00", "ff").replace("\ufb03", "ffi").replace("\ufb04", "ffl")
    # a blank line inside a quote or before a lowercase word or punctuation is a PDF artefact, not a paragraph
    text = re.sub(r"(?<=[(\u201c\"\u2018])\s*\n\s*\n\s*", "", text)
    text = re.sub(r"\n\s*\n(?=\s*[\"\u201d\u2019)\].,;:]|\s*[a-z])", " ", text)
    # a parenthetical comparative -- '(Q1 2025: 22,790 oz)' -- is the prior period, never this one
    text = re.sub(r"\([^()]{0,80}(?:Q[1-4]|20\d\d|prior|previous)[^()]{0,80}\)", " ", text)
    # 'r ecord', 'full -year', 'Compa ny': PDF extraction splits words; the few that matter are rejoined
    text = re.sub(r"(?i)\bfull\s*-\s*year", "full-year", text)
    # 1.3.1: a footnote mark glued to a word - '132,405 GEOs1 sold' (FNV), 'gold equivalent ounces1' (OR), 'Production1 of' (K)
    text = re.sub(r"(?i)\b(GEOs?|ounces|oz|tonnes|pounds|production|produced|sold)(\d{1,2})(?=[\s,.;:)(\u201c\"])", r"\1 ", text)
    # 'Consolidated gold production for the second quarter was 4 3,824 ounces': a PDF splits a number (1.1)
    text = re.sub(r"(?i)(\b(?:was|were|of|totall?ed|produced|poured|sold|to)\s+)(\d) (\d{1,2},\d{3}\b)",
                  lambda m: m.group(1) + m.group(2) + m.group(3) if len(m.group(2) + m.group(3).split(",")[0]) <= 3 else m.group(0), text)
    return text


_CLAUSE_SPLIT = re.compile(r"\n\s*\n|(?<=[.;!?])\s+(?=[A-Z\u2022\u201c\"(])|[\u2022\u25cf\u25aa\u25e6\uf0b7\uf0a7\uf0d8\u25a0\u27a2]|\s(?:o|-)\s(?=[A-Z])")   # 1.2: the PDF bullet \uf0b7 (Mineros)


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
            if kind == "yr" and re.search(r"(?i)\b(?:" + _MONTHS + r")\.?\s+\d{1,2},?\s*$", clause[max(0, m.start() - 16):m.start()]):
                continue      # 'On June 17, 2025, ... closed': a date is not a period (1.1)
            if kind == "yr" and re.search(r"(?i)\b(?:" + _MONTHS + r")\.?\s*$", clause[max(0, m.start() - 12):m.start()]) and \
                    not re.match(r"(?i)\s*(?:quarter|half)", clause[m.end():m.end() + 12]):     # 'DECEMBER 2023 QUARTER' (PRU) stays
                # 1.3: 'In October 2018, Segovia's gold production amounted to 16,023 ounces' (ARIS): a month-year is never
                # the year's period (still the release's year for _doc_period)
                taken.append((m.start(), m.end()))
                found.append((m.start(), m.end(), "my", m.groups()))
                continue
            taken.append((m.start(), m.end()))
            if kind == "qy":                                   # 1.3.1: '2026 second-quarter' is a 'q'
                found.append((m.start(), m.end(), "q", (m.group(2), m.group(1))))
                continue
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
    if kind == "h6":
        return "H%d %s" % (1 if g[0].lower() == "june" else 2, g[1])
    if kind == "m9":
        return "9M %s" % g[0]
    if kind == "h6b":
        return "H1 %s" % g[0]
    if kind == "ytdm":
        return {"june": "H1 ", "september": "9M ", "december": "FY "}[g[0].lower()] + g[1]
    if kind == "ytd":
        # 1.3: year-to-date at the release's own calendar quarter; Q1 year-to-date is the quarter itself
        q_ = re.fullmatch(r"Q([2-4]) (20\d\d)", doc.get("quarter") or "")
        y_ = g[0] or g[1]
        if not q_ or (y_ and y_ != q_.group(2)):
            return None
        return {"2": "H1 ", "3": "9M ", "4": "FY "}[q_.group(1)] + q_.group(2)
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


_Q_AND_YEAR = re.compile(r"(?i)\b(first|second|third|fourth|Q[1-4])(?:\s+quarter)?\s+(?:and|&)\s+(?:the\s+)?(?:full[\s\-]*year|year[\s\-]*end(?:ed)?|"
                         r"annual|fiscal\s+year)\s+(?:results\s+)?(?:of\s+|for\s+)?(20\d\d)\b")


def _doc_period(headline, body):
    """The release's own period: the quarter (or year) its headline, or failing that its opening, names."""
    doc = {"quarter": None, "fiscal_quarter": None, "year": None}
    # 1.2: 'LUNDIN GOLD REPORTS FOURTH QUARTER AND FULL YEAR 2024 RESULTS', 'Q4 and Full-Year 2025': the quarter shares
    # the year named after the full year
    qa = _Q_AND_YEAR.search(headline or "")
    if qa:
        q_ = _ORD.get(qa.group(1).lower()) or int(re.sub(r"\D", "", qa.group(1)) or "0")
        if q_:
            doc["quarter"], doc["year"] = "Q%d %s" % (q_, qa.group(2)), qa.group(2)
            return doc
    for src in (headline or "", " ".join((body or "")[:900].split())):
        src2 = re.sub(r"(?i)\b(" + _MONTHS + r")\.?\s+\d{1,2},?\s+20\d\d", " ", src)   # a dateline is not a period
        if src is not (headline or "") and doc["year"]:
            src2 = re.sub(r"(?i)\b(quarter|Q[1-4]),(\s+20\d\d)", r"\1 ,\2", src2)     # 1.3: a year headline's opening (EDR)
        head_year = doc["year"] if src2 is not (headline or "") else None
        for s, e, kind, g in _periods(src2):
            if head_year and re.search(r"20\d\d", src2[s:e]) and head_year not in src2[s:e]:
                continue      # the opening's comparatives ('over Q4 2024') are not the headline year's period
            if kind == "fq" and not doc["fiscal_quarter"]:
                doc["fiscal_quarter"] = _resolve(kind, g, doc)
            elif kind in ("q", "q2", "m3") and not doc["quarter"]:
                doc["quarter"] = _resolve(kind, g, doc)
            if not doc["year"] and kind in ("q", "q2", "m3", "h", "fy", "fy2", "yr", "fq", "h6", "h6b", "m9", "ytdm", "ytd", "my"):   # 1.3
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
_LABEL_NEXT = re.compile(r"(?i)\s*(?:gold|silver|copper|zinc|lead|nickel|cobalt|u3o8|uranium)(?:\s+equivalent)?\s*"
                         r"(?:(?:production|produced|sold|sales|output|payable)\b\s*(?:\([^()]{0,20}\)\s*)?[:(]|\(\s*(?:ounces|oz|tonnes|t|lbs?|pounds)\b)")
_LIST_GAP = re.compile(r"(?i)^\s*(?:of\s+(?:contained\s+|payable\s+)?)?(?:[a-z]+\s+){0,2}?(?:gold|silver|copper|zinc|lead|nickel|cobalt|u3o8)?"
                       r"\s*(?:,\s*(?:and\s+)?|\s+and\s+)$")
# ---- 1.1: multi-mine companies
# a figure that is part of another figure of the same metal ('including 72,823 oz from the Nicaragua operations',
# 'excluding 1,975 oz from Castle Mountain') or an asset's share ('Fekola underground to contribute between ...')
_COMPONENT = re.compile(r"(?i)\b(?:includ(?:es|ing|ed)|exclud(?:es|ing|ed)|of\s+which|contribut\w*(?!\s+to\b))\b")
_CONTRIBUTE = re.compile(r"(?i)\bcontribut\w*\b(?!\s+to\b)")
# a figure the text right after it gives to a named place ('1,975 ounces produced at Castle Mountain')
_AT_ASSET = re.compile(r"^\s*(?:\(\W*[\w ]{0,12}\W*\)\s*)?(?:of\s+(?:[a-z]+\s+){0,3})?(?:(?:were\s+|was\s+)?(?:produced|poured|sold|delivered)\s+)?"
                       r"(?:at|from|by)\s+(?:the\s+|its\s+)?((?:[A-Z][\w'\u2019\-]+\s+){0,3}[A-Z][\w'\u2019\-]+)")
# the names of a release's producing assets: a name that produced something, or that production came from
_PNAME = r"((?:[A-Z][\w'\u2019\-]+\s+){0,3}?[A-Z][\w'\u2019\-]+)"
_ASSET_PRODUCED = re.compile(_PNAME + r"(?:\s+(?:Gold|Silver|Copper))?(?:\s+(?:Mine|Complex|Operations?|mine|operations?))?\s*(?:,\s*)?"
                             r"(?:has\s+|have\s+)?(?:produced|poured|(?:gold\s+|silver\s+|copper\s+)?production\s+(?:was|of|totall?ed|increased|decreased))\b")
_ASSET_FROM = re.compile(r"(?i:produced|poured|ounces|oz|tonnes|pounds)\s+(?:(?:of\s+)?(?:gold|silver|copper|zinc|lead)\s+)?(?:(?:were\s+|was\s+)?(?:produced|poured)\s+)?(?:at|from)\s+(?:the\s+|its\s+)?" + _PNAME)
_ASSET_SUBJ = re.compile(r"\b[A-Z][\w'\u2019\-]+(?:\s+[A-Z][\w'\u2019\-]+){0,2}\s+(?:(?:Gold|Silver|Copper)\s+)?(?:Complex|Regional|[Uu]nderground|Project|Operations?|Mine)\b")
_CONSOLIDATED = re.compile(r"(?i)\bconsolidated\b|\btotal\b|company[\s\-]+wide|\bcombined\b|\baggregate\b|\bthe\s+company\b|\bgroup\b")
_MULTI_CUE = re.compile(r"(?i)\bconsolidated\s+(?:gold\s+|silver\s+|copper\s+|metal\s+|gold\s+equivalent\s+)?(?:production|produced|output)\b|"
                        r"\bon\s+a\s+consolidated\s+basis\b|\breview\s+of\s+operating\s+mines\b|\b(?:two|three|four|five|six)\s+(?:operating\s+)?(?:mines|operations)\b")
_NOT_ASSET = {"the", "our", "its", "this", "company", "gold", "silver", "copper", "open", "pit", "underground", "new",
              "mine", "mines", "mineral", "operations", "operation", "project", "projects", "complex", "total", "all",
              "canadian", "mexican", "producing", "operating", "flagship", "each", "both", "other", "such", "these",
              "commercial", "production", "exploration", "development", "and", "at", "of", "in"}


_COMPANY_CUE = re.compile(r"(?i)\b(?:its|our|the\s+company['\u2019]s|consolidated|total|company[\s\-]+wide|group)\b")
_ASSET_VERB = r"(?:\s+(?:mine|complex|operations?|underground|regional))?(?:['\u2019]s)?\s+(?:\w+\s+){0,3}?(?:is|are|will|to|expects?|anticipat\w*|forecast\w*|guidance|production|remains?|targets?)\b"


def _asset_context(window, assets):
    """The window names an asset as the subject of the figure: 'at the Goose Mine ...', 'Fekola underground is
    anticipated to ...', 'The Fekola Complex is expected to produce ...'."""
    low = window.lower()
    for a in assets:
        if re.search(r"\b(?:at|for|from)\s+(?:the\s+)?" + re.escape(a) + r"\b", low) or \
                re.search(r"\b" + re.escape(a) + _ASSET_VERB, low):
            return True
    for m in _ASSET_SUBJ.finditer(window):
        if re.search(r"(?i)\b(?:at|for|from)\s+(?:the\s+)?$", window[max(0, m.start() - 12):m.start()]) or \
                re.match(r"(?i)" + _ASSET_VERB, window[m.end():m.end() + 60]):
            return True
    return False


_NOT_NAME = {"strong", "quarter", "year", "first", "second", "third", "fourth", "half", "full", "results", "result", "change", "ytd", "total", "operating", "highlights", "grade", "recovery", "record",
             "quarterly", "annual", "production", "consolidated", "attributable", "payable", "which", "this", "these",
             "company", "corporation", "gold", "silver", "copper", "metal", "ounces", "tonnes", "the", "and", "our"}


_ASSET_ATCOMMA = re.compile(r"\b(?:At|From)\s+(?:the\s+)?" + _PNAME + r"(?:\s+(?:Mine|Complex|Operations?|mine))?,\s+(?:\w+\s+){0,3}?(?:gold\s+|silver\s+)?(?:production|produced)\b")
_ASSET_PRODAT = re.compile(r"(?i:production|produced)\s+(?:at|from)\s+(?:the\s+)?" + _PNAME +
                           r"(?:\s+(?:Mine|Complex|Operations?|mine|operations?))?\s+(?:was|were|totall?ed|of|increased|decreased|reached)\b")


def _asset_names(text, issuer):
    names = set()
    for rx in (_ASSET_PRODUCED, _ASSET_FROM, _ASSET_PRODAT, _ASSET_ATCOMMA):
        for m in rx.finditer(text):
            words = [w for w in m.group(1).split() if w.lower() not in _NOT_ASSET]
            if not words or all(w.lower() in issuer for w in words) or re.match(
                    r"(?i)(?:Q[1-4]|H[12]|FY|20\d\d|" + _MONTHS + r"|first|second|third|fourth|record|quarter|year|we|it|which|that|who)$", words[0]):
                continue
            if len(words[0]) < 3 or any(w.lower() in _NOT_NAME or re.fullmatch(r"20\d\d|Q[1-4]", w) for w in words) or \
                    any(w.isupper() and len(w) > 2 for w in words):
                continue      # an ALL-CAPS headline is not a list of names
            names.add(" ".join(words[-2:]).lower())
    # 'florida' and 'florida canyon' are one asset
    return {n for n in names if not any(o != n and (o.startswith(n + " ") or o.endswith(" " + n)) for o in names)}


_GEO_RANGE = re.compile(r"(?i)\bGEOs?\b(?:\s+[\w\-]+){0,4}?\s+(?:between\s+)?" + _NUM + r"\s*(?:to|and|-|\u2013)\s*" + _NUM +
                        r"(?!\d|,\d|\s*(?:%|per\b|/|GEOs?\b|oz\b|ounces|gold))")
# each item is preceded by whitespace or ', ', so a number with commas can only be read one way (no backtracking)
_LIST_VERB = re.compile(r"(?i)^(?:(?:,\s+|\s+)(?:and\s+|of\s+)?(?:\d[\d,.]*\d|\d|gold|silver|copper|zinc|lead|ounces?|oz|tonnes|lbs|pounds|equivalent|payable)\b){0,10}"
                        r"\s+(?:were|was|have\s+been|had\s+been)\s+(sold|produced|poured|delivered)\b")
# 1.3: recovered figures
_REC_POST = re.compile(r"(?i)\s*(?:\(\W*\w+\W*\)\s*)?(?:of\s+(?:(?:gold|silver|copper|payable|contained)\s+){0,2})?"
                       r"(?:(?:were|was|have\s+been|has\s+been)\s+)?recovered\b(?!\s+(?:from\s+(?:a\s+|the\s+)?(?:clean|stockpile|inventory|bulk)|over\s+the\b))")
_REC_PRE = re.compile(r"(?i)\b(?:gold|silver|ounces?|oz)\s+recovered\s*(?:\(\w+\)\s*)?(?:was|were|of|totall?ed|:|-|\u2013)?\s*(?:approximately\s+|about\s+|~)?$|"
                      r"\b(?:the\s+company|we|it)\s+(?:also\s+)?(?:has\s+|have\s+)?recovered\s+(?:a\s+total\s+of\s+)?(?:approximately\s+|about\s+|~)?$")   # EFR
_REC_NOT = re.compile(r"(?i)\bfirst\s+[\d,.]+\s*(?:million\s+)?(?:ounces|oz)|royalt|\bNSR\b|life[\s\-]+of[\s\-]+mine|\bLOM\b|"
                      r"feasibility|\bPEA\b|\bstudy\b|over\s+the\s+(?:life|initial)|historic|to\s+date|bulk\s+sample|\bcumulative|"
                      r"\bin(?:clud|clus|\s+addition)\w*|\bexclud\w*|sludge|cathode|clean[\s\-]*up|residual|recovered\s+(?:at|from)\s+(?:the\s+)?[A-Z]|previously\s+not|not\s+(?:been\s+)?expected\s+to\s+be\s+recovered")
# 1.3: a named asset's figure in a multi-mine release
_ANAME = r"(?:[A-Z\u00c0-\u00de][\w'\u2019\-]+\s+){0,2}[A-Z\u00c0-\u00de][\w'\u2019\-]+"
_NAMED_ASSET = re.compile(r"\b(?:production|produced|output|poured)(?:\s+(?:in|for|during)\s+(?:the\s+)?(?:Q[1-4]\s+)?20\d\d)?\s+(?:at|from)\s+(?:the\s+|its\s+)?(?P<n1>" + _ANAME + r")|"
                          r"(?:^|(?<=[\s,;:]))(?:[Tt]he\s+)?(?P<n2>" + _ANAME + r")(?:\s+(?:mine|Mine|operations?|Operations?|Complex))?"
                          r"\s+(?:has\s+|have\s+)?(?:delivered|produced|poured)\b")
_NOT_ASSET_NAME = re.compile(r"(?i)(?:Q[1-4]|H[12]|FY|YTD|20\d\d|year|nine|six|three|twelve|january|february|march|april|may|june|"
                             r"july|august|september|october|november|december|company|consolidated|total|group|gold|silver|copper|"
                             r"production|operations|it|we|they|this|that|these|both|each|all|record)\b")
_GEO_OF = re.compile(r"(?i)\bgeos?\s+(sold|produced|delivered)?\s*of\s+" + _NUM + r"(?!\d|,\d)")
# 1.3.1: the unit before the figure - 'Silver Equivalent Ounces produced of 3,424,817' (SCZ)
_EQ_OF = re.compile(r"(?i)\b(silver|gold)\s+equivalent\s+ounces\s+(sold|produced)\s+(?:of|was|were|totall?ed)\s+" + _NUM + r"(?!\d|,\d|\s*(?:%|oz|ounces|tonnes))")


def _mentions(clause, geo_quotes=False):
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
        if re.fullmatch(r"20[0-4]\d", num):
            continue          # 'Q1 2026 ... 2025 ounces': a year read as a figure (1.1)
        if re.search(r"\$\s?$", clause[max(0, m.start() - 3):m.start()]):
            continue          # '$ 699.1 Gold oz sold': money in a flattened table (1.1)
        pre_ = re.search(r"(?:\d[\d,.]*\s+){1,}$", clause[max(0, m.start() - 40):m.start()])
        if pre_ and not re.fullmatch(r"\s*20\d\d\s*", pre_.group(0)) and re.match(r"\s+[A-Z][a-z]", clause[m.end(1):m.start(4)] + " x"):
            continue          # 1.3.1: '... Sold 499,035 526,223 993,163 1,050,312 Attributable gold equivalent ounces': the last
                              # cell of a flattened table row, and the words after it are the next row's label (Kinross)
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
        # 'Zinc Production: 21,581 tonnes Lead Production: 2,603 tonnes': a metal right after the unit that opens
        # the next item's label ('Lead Production:', 'Silver (ounces)') is that item's, not this figure's (1.1)
        label_next = bool(_LABEL_NEXT.match(after))
        if not metal and am and not label_next:
            if re.match(r"(?i)\s*(?:\(\W*[\w ]{0,12}\W*\)\s*)?of\b", after) or re.match(r"(?i)\s*(au|ag|cu|aueq|ageq)\b", after):
                metal = _metal_of(am.group(1)[:30])
        if not metal and not label_next:
            m2 = re.match(r"(?i)\s*(gold|silver|copper|zinc|lead|nickel|cobalt|u3o8|au|ag|cu)\b(\s+equivalent\b)?", after)
            if m2:
                metal = _metal_of(m2.group(1))
                if m2.group(2) and metal in ("gold", "silver"):
                    metal = "AuEq" if metal == "gold" else "AgEq"     # 1.3.2: '1.7 million oz silver equivalent'
        if not metal and unit == "oz" and not label_next:
            eq_ = re.match(r"(?i)\s*in\s+(silver|gold)\s+equivalent\b", after)
            if eq_:
                metal = "AgEq" if eq_.group(1).lower() == "silver" else "AuEq"     # 1.3 (USA)
        if unit == "oz" and re.match(r"(?i)\s*(?:\(\W*[\w ]{0,12}\W*\)\s*)?aueq\b", after):
            metal = "AuEq"
        if metal == "AuEq" and re.match(r"(?i)\s*\(\s*GEOs?\s*\)" if not geo_quotes else r"(?i)\s*\(\s*[\u201c\"']?\s*GEOs?\s*[\u201d\"']?\s*\)", after):   # 1.3.1: '(\u201cGEOs\u201d)' (OR), a royalty company's only
            metal = "GEO"         # 1.2: 'Gold Equivalent Ounces (GEOs)' is the company's own name for them (HSTR)
        out.append({"start": m.start(), "end": m.end(), "value": v, "unit": unit, "metal": metal,
                    "approx": bool(re.match(r"(?i)(approximately|about|~)", m.group(0))),
                    # a number glued to table cells ('... 699.1 Gold oz sold 239,311') (1.1)
                    "tabular": bool(re.search(r"[\d%]\)?\s*$", clause[max(0, m.start() - 6):m.start()])
                                    or re.match(r"\s*(?:sold|produced)?\s*\(?\$?\d", clause[m.end():m.end() + 25])
                                    or m.start() == 0 or re.fullmatch(r"\s*(?:Gold|Silver|Copper)\s*", mid))})
    # 'expects 2026 attributable GEOs to be between 20,000 to 23,000': the unit before the range (1.1)
    for m in _GEO_RANGE.finditer(clause):
        if re.fullmatch(r"20\d\d", m.group(2).strip()):
            continue          # 1.3.1: '850,000 GEOs in years 2029 to 2033' (WPM): years, not a range
        if not any(x["start"] <= m.start(2) < x["end"] for x in out):
            out.append({"start": m.start(2), "end": m.end(2), "value": _num(m.group(2)), "unit": "oz", "metal": "GEO",
                        "approx": False, "tabular": False})
    for m in _EQ_OF.finditer(clause):
        if not any(x["start"] <= m.start(3) < x["end"] for x in out):
            out.append({"start": m.start(3), "end": m.end(3), "value": _num(m.group(3)), "unit": "oz",
                        "metal": "AgEq" if m.group(1).lower() == "silver" else "AuEq", "approx": False, "tabular": False,
                        "geo_verb": m.group(2).lower()})
    for m in _GEO_OF.finditer(clause):
        out.append({"start": m.start(), "end": m.end(), "value": _num(m.group(2)), "unit": "oz", "metal": "GEO",
                    "approx": False, "geo_verb": (m.group(1) or "").lower()})
    out.sort(key=lambda x: x["start"])
    return out


# 1.3: between a figure and the year-to-date after it, only its own unit, metal and verb ('174,780 ounces produced
# year-to-date', '2,335,569 ounces in the first nine months'); never across a comma or another figure
_YTD_GAP = re.compile(r"(?i)\s*(?:\(\w+\)\s*)?(?:(?:of\s+)?(?:gold|silver|copper|zinc|lead|payable|contained|equivalent|AuEq|AgEq)\s+){0,3}"
                      r"(?:(?:were|was|have\s+been|has\s+been)\s+)?(?:produced|poured|sold|recovered)?\s*"
                      r"(?:(?:in|for|during|over|on\s+a)\s+)?(?:the\s+)?")


def _period_for(clause, men, periods, doc, nxt, prefer_before=False):
    """The period a figure belongs to: one right after it ('... in Q1 2026') if it is introduced by in/for/
    during, else the nearest one before it in the clause. None if that is a non-standard span."""
    if prefer_before:
        # guidance names its period ahead of the range: 'Issued FY 2025 production guidance of 270,000 tonnes,
        # reinforced by performance achieved in 4Q24' is FY 2025's
        near = [(kind, g) for s, e, kind, g in periods if e <= men["start"] and men["start"] - e <= 70
                and kind not in ("ytd", "ytdm", "m9", "h6b", "h6", "my")]   # 1.3: a year-to-date is never a guidance period
        fy_aft = [(s, kind, g) for s, e, kind, g in periods if s >= men["end"] and s - men["end"] <= 45 and kind in ("fy", "fy2", "fyn")]
        if fy_aft and re.search(r"(?i)\bguidance\s+for\s+(?:the\s+)?$", clause[men["end"]:fy_aft[0][0]]):
            # 1.3: '8,626 oz, in Q1 18 ... the Company's 30,000 - 35,000 oz guidance for the full year' (OMI)
            return _resolve(fy_aft[0][1], fy_aft[0][2], doc), fy_aft[0][1]
        if not near:
            # 1.3: 'the Company's 4.6 to 5.0 million ounce guided range for the year' (ABX): the period just after it
            aft = [(kind, g) for s, e, kind, g in periods if s >= men["end"] and s - men["end"] <= 60
                   and kind not in ("ytd", "ytdm", "m9", "h6b", "h6", "span")]
            if aft and any(k in ("ytd", "ytdm", "m9", "h6b", "h6") for s, e, k, g in periods if e <= men["start"]):
                return _resolve(aft[0][0], aft[0][1], doc), aft[0][0]
        if near:
            return _resolve(near[-1][0], near[-1][1], doc), near[-1][0]
    if any(kind == "span" and e <= men["start"] and not re.search(r"[.;]", clause[e:men["start"]]) and men["start"] - e <= 40
           for s, e, kind, g in periods):
        return None, "span"              # 'during the month of April was 15,799 ounces and ... during Q2 2025' (1.1)
    for s, e, kind, g in periods:
        if s >= men["end"]:
            gap = clause[men["end"]:s]
            # 1.2: '8,459 GEOs (8,180 gold ounces and 21,494 silver ounces) in the three months ended December 31,
            # 2025' (HSTR): a bracketed breakdown between a figure and its period does not break the list
            gap = re.sub(r"\([^()]{0,80}\)", " ", gap)
            if gap.count(")") == 1 and "(" not in gap and re.search(r"\(", clause[max(0, men["start"] - 60):men["start"]]):
                gap = gap.replace(")", " ")
            # '58,506 ounces of silver and 932 ounces of gold in Q1 2026': a list shares the period after it
            if kind == "span" and len(gap) <= 40 and not re.search(r"\d[\d,.]{2,}", gap):   # 1.3: not across another figure (TFPM)
                return None, "span"      # '160,000 pounds ... in the single month of April'
            if kind in ("ytd", "ytdm", "m9", "h6b", "h6") and not prefer_before and _YTD_GAP.fullmatch(clause[men["end"]:s]):
                # 1.3: 'with 174,780 ounces produced year-to-date' (ELD): the year-to-date after the figure is its period
                p_ = _resolve(kind, g, doc)
                return (p_, kind) if p_ else (None, "span")
            listy = ((s < nxt and len(gap) <= 45) and not re.search(r"(?i)\b(?:totall?ing|bringing|includ\w*|exclud\w*|of\s+which|guidance|outlook|forecast\w*|expect\w*)\b", gap)) or \
                (len(gap) <= 120 and not re.search(
                r"(?i)\b(compared|vs|versus|from|sold|sales|up|down|while|with|which|was|were|is|are|had|has|per|at|bringing|totall?ing|includ\w*|exclud\w*|of\s+which|guidance|outlook|forecast\w*|expect\w*)\b|[;:$%(]", gap))
            if listy and len(gap) <= 120 and re.search(r"(?i)\b(in|for|during)\s+(?:the\s+)?$", gap) \
                    and not _NOT_PRODUCTION.search(gap) and not re.search(r"(?i)%|increase|decrease|higher|lower", gap):
                return _resolve(kind, g, doc), kind
            break
    best = None
    for s, e, kind, g in periods:
        if e <= men["start"] and men["start"] - e <= 160:
            best = (kind, g)
    if best and best[0] in ("ytd", "ytdm", "m9", "h6b", "h6") and any(
            s >= men["end"] and s - men["end"] <= 90 and kind not in ("ytd", "ytdm", "m9", "h6b", "h6", "span", "yr")
            and s - men["end"] <= 70 and re.search(r"(?i)\b(?:in|for|during)\s+(?:the\s+)?$", clause[men["end"]:s])
            and not re.search(r"\d[\d,.]{2,}\s*(?:million\s+)?(?:ounces|oz|tonnes|pounds|lbs?)\b|(?i:expect|anticipat|forecast|plan|guid|further|and\s+a\b)", clause[men["end"]:s])
            for s, e, kind, g in periods):
        return None, "span"      # 1.3
    pre_ = [(kind, g) for s, e, kind, g in periods if e <= men["start"] and men["start"] - e <= 160]
    if pre_ and pre_[-1][0] == "my":
        # 1.3: a month-year just before the figure: an actual is that month's, never the year's ('In October 2018, Segovia's
        # gold production amounted to 16,023 ounces', ARIS); guidance looks past it ('the 2020 guidance ... issued in
        # February 2020, including expected gold production of 257,000 to 299,000 ounces', DPM)
        if not prefer_before:
            return None, "my"
        rest_ = [x for x in pre_ if x[0] != "my"]
        if rest_:
            return _resolve(rest_[-1][0], rest_[-1][1], doc), rest_[-1][0]
        aft_ = [(kind, g) for s, e, kind, g in periods if s >= men["end"] and s - men["end"] <= 60 and kind in ("fy", "fy2", "fyn", "yr")]
        if aft_:
            return _resolve(aft_[0][0], aft_[0][1], doc), aft_[0][0]     # '... 250,000 to 300,000 pounds drummed for the year' (URE)
    if men.get("tabular") and not re.search(r"[\d%]\)?\s*$", clause[:men["start"]]):
        # 1.3: 'Consolidated Attributable Production Q1-2023 Q1-2022 ... Silver Production (ounces) 0.5 Moz 0.3 Moz' (USA): a
        # flattened table's header runs its columns side by side; the row's first cell is the first column's
        pre_ = [(s, e, kind, g) for s, e, kind, g in periods if e <= men["start"] and men["start"] - e <= 160]
        i_ = len(pre_) - 1
        while i_ > 0 and re.fullmatch(r"\s*", clause[pre_[i_ - 1][1]:pre_[i_][0]]):
            i_ -= 1
        if 0 <= i_ < len(pre_) - 1:
            return _resolve(pre_[i_][2], pre_[i_][3], doc), pre_[i_][2]
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
    m = re.search(r"(?i)(?:between\s+)?\$?" + _NUM + r"(\s*(?:million|thousand))?(?:\s*(?:ounces|oz|tonnes|pounds))?\s*(?:to|\u2013|\u2014|-|and)\s*\$?$", before)
    if not m:
        return None
    if re.search(r"(?i)\band\s*\$?$", before) and \
            not re.search(r"(?i)between\s+\$?[\d,.]+(?:\s*(?:million|thousand))?(?:\s*(?:ounces|oz|tonnes|pounds))?\s*and\s*\$?$", before) and \
            not re.search(r"(?i)between\s+\$?[\d,.]+(?:\s*(?:million|thousand))?\s*and\s*\$?$", before):
        return None      # 'A and B' is only a range after 'between'
    if re.fullmatch(r"20[0-4]\d", m.group(1)) and not m.group(2):
        return None      # 1.2: 'bringing total production for 2025 to 379,081 ounces': a year, not the low end (AAUC)
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
    if re.search(r"(?i)\b(?:achiev|meet|met\b|reach|exceed|beat|deliver)\w*\s+(?:\w+\s+){0,4}?targets?\s+(?:with|of|at|by)?\s*$", before):
        return None      # 1.2: 'ACHIEVES 1Q25 PRODUCTION TARGET WITH 68,300t' is what was produced (SGML)
    m = re.search(r"(?i)(guidance|guided|target(?:ed)?(?:\s+to\s+be)?|expects?\s+to\s+produce|forecast|projected)"
                  r"(?:\s+\w+){0,3}?\s+(?:of|at|to\s+be|is|to)?\s*(about|approximately|at\s+least|above|more\s+than|in\s+excess\s+of)?\s*$",
                  before)
    if m:
        return "floor" if (m.group(2) or "").lower() in ("at least", "above", "more than", "in excess of") else "point"
    m = re.search(r"(?i)\b(above|at\s+least|more\s+than|in\s+excess\s+of|exceed)\s*$", before)
    if m and _GUIDE.search(clause):
        return "floor"
    return None


_NOT_SUBJECT = {"the", "company", "we", "it", "production", "record", "total", "consolidated", "gold", "silver",
                "copper", "quarterly", "annual", "first", "second", "third", "fourth", "q1", "q2", "q3", "q4", "this",
                "operations", "operation", "group", "corporation", "mine", "mines", "segment", "our", "combined",
                "during", "in", "for", "full", "year", "highlights", "overall", "attributable", "payable"}


def _issuer_words(headline):
    """The first capitalised words of the headline: 'Sierra Madre Reports ...' -> {'sierra', 'madre'}."""
    words = []
    for w in re.findall(r"[A-Za-z][\w'\u2019&\-]*", headline or "")[:4]:
        if w.lower() in ("reports", "announces", "provides", "delivers", "achieves", "presents", "releases", "inc",
                         "corp", "ltd", "the"):
            break
        words.append(w.lower())
    return set(words)


def _subject(pre, issuer):
    """The named asset a clause says produced a figure ('Kiaka produced', 'the La Colorada mine produced', 'At the
    CDI Complex, total production was'), or None when the subject is the company itself."""
    m = re.search(r"(?:^|[,;:.]\s*|\b(?:the|at|from)\s+)((?:[A-Z][\w'\u2019\-]+\s+){0,3}[A-Z][\w'\u2019\-]+)"
                  r"(?:\s+(?:mine|Mine|operations?|Operations?|complex|Complex))?\s*(?:,\s*)?(?:has\s+)?"
                  r"(?:produced|poured|total\s+production|production\s+(?:was|of|totall?ed))", pre)
    if not m:
        # 'Operating Highlights Eagle River produced 26,702 and ...': the name right before the verb (1.1)
        m = re.search(r"([A-Z][\w'\u2019\-]+(?:\s+[A-Z][\w'\u2019\-]+)?)\s+(?:has\s+)?(?:produced|poured)\s*$", pre)
    if not m:
        return None
    words = [w.lower() for w in m.group(1).split()]
    if all(w in _NOT_SUBJECT or w in issuer for w in words):
        return None
    return " ".join(words)


# ------------------------------------------------------------------ milestones
_MS = [
    ("commercial_production", re.compile(r"(?i)\b(achiev\w*|declar\w*|announc\w*|reach\w*|attain\w*)\s+(?:of\s+)?commercial\s+production")),
    ("first_pour", re.compile(r"(?i)\bfirst\s+(?:gold\s+|silver\s+|dor\u00e9\s+|dore\s+)?pour\b|\bpours?\s+first\s+(?:gold|dor\u00e9|dore)")),
    ("resumption", re.compile(r"(?i)\b(?:resumes|resumed|restarts|restarted|resumption\s+of)\s+(?:\w+\s+){0,2}?(?:production|operations?|mining|milling|processing|shipments?)\b"
                                r"|\b(?:mine|operations?|mill|plant)\s+(?:resumes|resumed|restarts|restarted)\b")),
    ("first_production", re.compile(r"(?i)\bproduction\s+(?:and\s+shipment\s+)?of\s+first\b|\bfirst\s+production\b|\bbegins?\s+production\b|\bcommences?\s+production\b")),
    ("first_shipment", re.compile(r"(?i)\bfirst\s+(?:\w+\s+){0,2}shipment\b|\bshipment\s+of\s+first\b|\bfirst\s+\w+\s+(?:\w+\s+)?shipped\b|\bproduction\s+and\s+shipment\s+of\s+first\b")),
]
_MS_NOT = re.compile(r"(?i)\b(toward|towards|on\s+track|expects?|expected|planned|plans|prepar\w*|ahead\s+of|approach\w*|nears?|nearing|moving|path\s+to|targets?|targeting|anticipat\w*|will|decision|update\s+on\s+the\s+restart|suspend\w*|drill\w*|exploration|trading)\b")
_ASSET = re.compile(r"\b(?:at|from)\s+(?:the\s+|its\s+)?((?:[A-Z][\w'\u2019\-]+\s+){0,3}[A-Z][\w'\u2019\-]+?)(?:\s+(?:Gold|Graphite|Copper|Silver))?(?:\s+(?:Mine|Project|Operations?|Complex|Plant))?\b")
_ASSET_BEFORE = re.compile(r"\b((?:[A-Z][\w'\u2019\-]+\s+){0,2}[A-Z][\w'\u2019\-]+)\s+(?:Mine|Operations?)\b")


_GEO_WORDS = {"saskatchewan", "canada", "ontario", "quebec", "qu\u00e9bec", "nunavut", "yukon", "alberta", "manitoba", "nevada",
              "arizona", "idaho", "alaska", "mexico", "peru", "chile", "brazil", "argentina", "durango", "sonora",
              "bolivia", "colombia", "ecuador", "guyana", "ghana", "mali", "tanzania", "australia", "usa", "vancouver",
              "toronto", "montreal", "british", "columbia", "newfoundland", "labrador", "nova", "scotia", "zacatecas",
              "chihuahua", "sinaloa", "jalisco", "nicaragua", "honduras", "guatemala", "burkina", "faso", "africa"}
_NAME_STOP = {"and", "in", "to", "for", "with", "provides", "reports", "announces", "highlights", "marks", "milestone",
              "begins", "restart", "update", "following", "ahead", "after", "on", "under", "as", "mid", "mid-year",
              "engages", "achieves", "today", "&", "of", "from", "at", "the", "its", "resumes", "restarts", "pours",
              "declares", "commences", "receives", "conducts", "notes", "attains", "delivers", "announce", "resume"}
_NAME_TAIL = re.compile(r"(?i)(?:\s+(?:gold|silver|copper|graphite|lithium|uranium|zinc|nickel|antimony|polymetallic|silver-gold|gold-silver))*"
                        r"(?:\s+(?:underground|open\s*-?\s*pit|bulk\s+sample|mine|mines|project|operations?|operational|complex|plant|property|deposit|district))*$")


_NAME_END = {"mine", "mines", "project", "operations", "operation", "operational", "complex", "plant", "property",
             "deposit", "district"}
_METAL_WORDS = {"gold", "silver", "copper", "graphite", "lithium", "uranium", "zinc", "nickel", "antimony"}


def _clean_asset(name, tail=False):
    """'Saskatchewan Canada Cigar Lake' -> 'Cigar Lake'; 'Arizona Moss Gold' -> 'Moss'; 'Phase 1' -> None (1.1).
    tail: the name is the words right before 'Mine' ('South Star Announces Santa Cruz' -> 'Santa Cruz')."""
    words = name.replace("\u2019", "'").split()
    if tail:
        for i in range(len(words) - 1, -1, -1):
            if words[i].lower().strip(",.;:") in _NAME_STOP:
                words = words[i + 1:]
                break
    while words and words[0].lower().strip(",") in _GEO_WORDS:
        words = words[1:]
    out = []
    for w in words:
        lw = w.lower().strip(",.;:")
        if lw in _NAME_STOP or lw in _NAME_END or (out and lw in _GEO_WORDS) or w.endswith(","):
            if w.endswith(",") and lw not in _NAME_STOP and lw not in _NAME_END and lw not in _GEO_WORDS:
                out.append(w.rstrip(","))
            break
        out.append(w)
    while out and (out[0].lower() in _GEO_WORDS or out[0].lower() in ("its", "the", "new")):
        out.pop(0)
    n = _NAME_TAIL.sub("", " ".join(out)).strip(" ,-")
    if not n or re.match(r"(?i)^(?:phase|stage)\b|^(?:q[1-4]|first|record|its|the)$", n) or n.lower() in _GEO_WORDS \
            or n.lower() in _METAL_WORDS:
        return None
    if n.isupper() and len(n) > 3:
        n = n.title()
    return n


_ASSET_AT = re.compile(r"(?i:\b(at|from)\s+(?:the\s+|its\s+)?)((?:(?!(?:At|From|And|In|To|For|With|The|Its|Of|On)\b)[A-Z][\w'\u2019\-/]*\.?\s*-?\s*){1,6})")
_ASSET_LEAD = re.compile(r"((?:[A-Z][\w'\u2019\-/]+\s+){0,4}[A-Z][\w'\u2019\-/]+)\s+(?:(?:Gold|Silver|Copper|Graphite|Uranium)\s+)?(?:Mine|Operations?|Operational|Project)\b")
_ASSET_BODY = re.compile(r"\b(?:at|from)\s+(?:the\s+|its\s+)((?:[A-Z][\w'\u2019\-]+\s+){0,3}[A-Z][\w'\u2019\-]+)\s+(?:(?:Gold|Silver|Copper|Graphite|Uranium|Lithium)\s+)?(?:Mine|Project|Operations?)\b")


def _milestone_asset(h, body=""):
    """The asset a milestone headline names (1.1: 'Phase', 'Canada Cigar Lake', 'Media Luna Milestone' in 1.0)."""
    h2 = h.title() if sum(c.isupper() for c in h) > 0.6 * max(1, sum(c.isalpha() for c in h)) else h
    cands = []
    for m in _ASSET_AT.finditer(h2):
        c = _clean_asset(m.group(2))
        if c:
            cands.append((0 if m.group(1).lower() == "at" else 1, m.start(), c))
    for m in re.finditer(r"\bfor\s+the\s+((?:[A-Z][\w'\u2019\-]+\s+){0,3}[A-Z][\w'\u2019\-]+)\s+(?:(?:Gold|Silver|Copper|Graphite|Uranium|Lithium)\s+)?(?:Mine|Project|Operations?)\b", h2):
        c = _clean_asset(m.group(1))
        if c:
            cands.append((2, m.start(), c))
    if cands:
        return sorted(cands)[0][2]
    for m in _ASSET_LEAD.finditer(h2[:140]):
        c = _clean_asset(m.group(1), tail=True)
        if c:
            return c
    # 'Cabral Gold Announces First Gold Pour at Phase 1 Mine, Cui\u00fa Cui\u00fa Gold District': a stage, then the place
    m = re.search(r",\s+((?:[A-Z][\w'\u2019\-]+\s+){0,3}[A-Z][\w'\u2019\-]+)\s+(?:Gold\s+)?(?:District|Property|Project|Mine)\b", h2)
    if m and _clean_asset(m.group(1)):
        return _clean_asset(m.group(1))
    m = _ASSET_BODY.search(" ".join((body or "")[:1200].split()))
    return _clean_asset(m.group(1)) if m else None


# 1.2.1: the milestone's asset through the shared project-name helper
_PN_NOT_LEAD = {"only", "strong", "formalized", "construction", "grant", "funded", "direct", "first", "new", "its", "the"}
_PN_SUFFIX_NEAR = re.compile(r"(?:\s+[A-Z][\w'\u2019\-]*){0,2}\s+(?:Mine|Mines|Project|Operations?|Complex|Property|Deposit|Mill|Plant)\b")


def _page_asset(name):
    """A helper name in this page's form: 'Kainantu Gold Mine' -> 'Kainantu', 'TVIRD Balabag Gold and Silver Project' ->
    'TVIRD Balabag', 'Saskatchewan Canada Cigar Lake Mine' -> 'Cigar Lake'; a list or a description -> None."""
    if not name:
        return None
    s = re.sub(r"(?i)\b(gold|silver|copper|zinc|lead)\s*(?:and|&|-)\s*(?:gold|silver|copper|zinc|lead)\b", r"\1", name)
    if re.search(r"(?i)\s(?:and|&)\s", s):
        return None
    words = s.replace("\u2019", "'").split()
    while len(words) > 1 and words[0].lower().strip(",") in _GEO_WORDS:
        words = words[1:]
    s = _NAME_TAIL.sub("", " ".join(words)).strip(" ,-")
    if not s or s.lower() in _GEO_WORDS or s.lower() in _METAL_WORDS or s.split()[0].lower() in _PN_NOT_LEAD or \
            re.match(r"(?i)^(?:phase|stage)\b", s):
        return None
    if s.isupper() and len(s) > 3:
        s = s.title()
    return s


def _pn_words(name):
    return set(PN.key(name or "").split())


def _not_a_project(own, text, found):
    """1.2.0's name is not a project the release names: the text never writes it before Mine/Project/Operations...
    and no project the helper finds there shares a word with it ('Southern Pits', 'Fermont', 'Major')."""
    if re.search(re.escape(own) + _PN_SUFFIX_NEAR.pattern, text):
        return False
    w = _pn_words(own)
    return not any(w & _pn_words(n) for _p, n in found)


def _milestone_asset_pn(h, body=""):
    """1.2.1: the milestone's asset -- 1.2.0's own reading, corrected by the shared helper (see the notes above)."""
    own = _milestone_asset(h, body)
    h2 = h.title() if sum(c.isupper() for c in h) > 0.6 * max(1, sum(c.isalpha() for c in h)) else h
    iss = " ".join(sorted(_issuer_words(h)))
    t = " ".join((body or "")[:4000].split())
    head = []
    for _p, n in PN.find(h2, iss):
        pa = _page_asset(n)
        if pa:
            head.append(pa)
    found = PN.find(t, iss)
    if head:
        hn = head[0]
        if not own or _pn_words(own) & _pn_words(hn) or _not_a_project(own, t, found):
            return hn
        return own
    if own and not _not_a_project(own, t, found):
        return own
    opening = PN.find(" ".join((body or "")[:1200].split()), iss)
    keys = {PN.key(n) for _p, n in opening if PN.key(n)}
    if opening and len(keys) == 1:
        p = PN.primary(h2, body or "", iss)
        if p and PN.key(p) == PN.key(opening[0][1]):
            pa = _page_asset(p)
            if pa:
                return pa
    return own


def milestones(headline, body=""):
    h = " ".join((headline or "").split())
    if not h or _MS_NOT.search(h):
        return []
    out = []
    for name, rx in _MS:
        if rx.search(h) and not any(o["milestone"] == name for o in out):
            out.append({"kind": "milestone", "milestone": name, "asset": _milestone_asset_pn(h, body)})
    return out


# 1.3.1: a period a comparison introduces is the comparison's, never a figure's own ('Silver production of 1.9 million ounces,
# a decrease of 4% over Q3 Fiscal 2025; silver equivalent ... production of 2.0 million ounces' - SVM: neither is Q3 FY2025)
_COMPARATIVE = re.compile(r"(?i)(?:(?:\d\s*%|\bincrease|\bdecrease|\bup|\bdown|\bhigher|\blower)[^.;]{0,25}?\b(?:over|than|from)|\bcompared\s+(?:to|with)|\bversus|\bvs\.?|\brelative\s+to)"
                          r"\s+(?:the\s+)?(?:same\s+(?:quarter|period)\s+(?:of\s+|in\s+)?)?(?:last\s+year\s*)?"
                          r"(?:(?:approximately\s+)?[\d.,]+\s*(?:million\s+)?(?:ounces|oz|pounds|lbs?|tonnes|t)\s+(?:in|for|during)\s+(?:the\s+)?)?(?:\(\W*)?$")
_HL_HEAD = re.compile(r"(?i)\bhighlights\b[^.;\u2022]{0,45}?:?\s*$")


def _heading_period(cls, ci, doc):
    """1.3.1: the period of the 'Highlights' heading a bullet sits under ('2023 Highlights' - 'Produced of 22,641,052
    silver equivalent ounces ...', Santacruz's year-end release). Walks back over bullets that name no period."""
    for j in range(ci - 1, max(-1, ci - 9), -1):
        c = cls[j]
        if _HL_HEAD.search(c):
            tail = re.split(r"[.;:]\s+", c[-120:])[-1]
            if re.search(r"(?i)guidance|outlook|forecast|expect|plan|study|PEA|feasibility|reserve|resource", tail):
                return None       # '2024 Guidance Highlights' (ELD): a guidance heading's bullets are not actuals
            ps = [p for p in _periods(tail) if p[2] not in ("span", "qd", "my") and not _COMPARATIVE.search(tail[max(0, p[0] - 70):p[0]])]
            if not ps or (any(p[2] in ("q", "q2", "fq", "m3") for p in ps) and any(p[2] in ("fy", "fy2", "yr", "fyn") for p in ps)) or \
                    (re.search(r"(?i)\bquarter|\bQ[1-4]\b", tail) and re.search(r"(?i)full[\s\-]*year|annual|year[\s\-]*end", tail)):
                return None       # 'Fourth Quarter and Full Year 2025 Operating Highlights' (JAG): either period
            s_, e_, k_, g_ = ps[-1]
            if doc.get("fiscal_quarter"):
                return None       # 1.3.1: 'Q2 FY2023 Orovalle Highlights' (ORV): the release's fiscal quarter stands
            if k_ in ("q", "q2", "fq", "m3"):
                return _resolve(k_, g_, doc), k_
            if k_ in ("fy", "fy2", "yr"):
                y = re.search(r"20\d\d", tail[s_:e_])
                y = y.group(0) if y else None
                if y and doc.get("quarter") in (None, "Q4 " + y) and not doc.get("fiscal_quarter"):
                    return "FY " + y, "fy"
            return None
        if [p for p in _periods(c) if not _COMPARATIVE.search(c[max(0, p[0] - 70):p[0]])] or len(c) > 600:
            return None
    return None


def _descending_year(clause, p):
    """1.3.1: 'For the three months ended September 30, 2023 and 2022' (WDO): the earlier year after 'and' is the
    comparative column."""
    m = re.search(r"\b(20\d\d),?\s+and\s+$", clause[max(0, p[0] - 12):p[0]])
    y = re.match(r"20\d\d", clause[p[0]:p[1]])
    return bool(m and y and int(y.group(0)) < int(m.group(1)))


def _guidance_scope(cls, ci):
    """1.3.1: the bullet sits under a guidance / outlook heading ('2024 Guidance Highlights', ELD)."""
    for j in range(ci, max(-1, ci - 9), -1):
        hs = list(re.finditer(r"(?i)([^.;:\u2022]{0,70})\bhighlights\b", cls[j]))
        if hs:
            return bool(re.search(r"(?i)guidance|outlook|forecast", hs[-1].group(1)))
    return False


def _annual_scope(cls, ci, pre):
    """1.3.1: a figure under an 'ANNUAL FINANCIAL AND OPERATING HIGHLIGHTS' heading, in a fourth-quarter-and-annual
    release, is the year's, never the quarter's (DPM)."""
    for j in range(ci, max(-1, ci - 10), -1):
        c = pre if j == ci else cls[j]
        hs = list(re.finditer(r"(?i)([^.;:\u2022]{0,70})\b(?:highlights|review|summary)\b", c))
        if hs:
            h = hs[-1].group(1)
            return bool(re.search(r"(?i)\bannual|full[\s\-]*year|year[\s\-]*end|twelve\s+months", h)) and \
                not re.search(r"(?i)quarter|\bQ[1-4]\b|three\s+months|guidance|outlook", h)
    return False


# ------------------------------------------------------------------ analyse
def analyse(headline, body):
    head = " ".join((headline or "").split())
    res = {"is_production": False, "reason": None, "rows": []}
    if not _ANY_PROD.search(head) and not _ANY_PROD.search((body or "")[:TEXT_CAP]):
        res["reason"] = "no_production_language"
        return res
    blob = head + " " + (body or "")[:TEXT_CAP]
    if len(_OIL_GAS.findall(blob)) >= 3 and not re.search(r"(?i)\bGEOs?\b|gold\s+equivalent\s+ounces", blob[:6000]):   # 1.3.1: a royalty company's oil & gas (FNV)
        res["reason"] = "oil_and_gas"
        return res

    doc = _doc_period(headline, body)
    text = _prepare(headline, body)
    issuer = _issuer_words(head)
    assets = _asset_names(text, issuer)
    multi = len(assets) >= 2 or bool(_MULTI_CUE.search(text))
    rows = []
    cls = _clauses(text)
    # 1.3.1: the release's own company is a royalty / streaming company ('Wheaton is the world's premier precious metals
    # streaming company', 'OR Royalties is a royalty and streaming company') -- not a counterparty ('payable to Nomad
    # Royalty Company Ltd.', Mineros)
    royalty_ = bool(re.search(r"\b(?:royalty|streaming)\s+(?:(?:and|&)\s+(?:royalty|streaming)\s+)?compan(?:y|ies)\b|\broyalt(?:y|ies)\s+(?:and|&)\s+stream",
                              (body or "")[:3000]) or   # lower case: a description, not a name ('Nomad Royalty Company Ltd.')
                    re.search(r"(?i)\b(?:is|as)\s+(?:a|an|the)\s+(?:[\w\-\u2019']+\s+){0,5}?(?:royalty|streaming)\s+(?:(?:and|&)\s+(?:royalty|streaming)\s+)?compan(?:y|ies)\b",
                              (body or "")[:TEXT_CAP]) or any("royalt" in w for w in issuer))
    cmp_named_ = set()     # 1.3.1: the metals the dropped comparison figures named (they still name the release's metal)
    geo_co_ = bool(re.search(r"(?i)\bGEOs?\b", text[:3000]))
    # a GEO release listing its interests ('Fosterville (2.0% NSR gold royalty)', 'Cerro Lindo (65% silver stream)') is a
    # royalty company's even when the boilerplate that says so comes late (Triple Flag)
    royalty2_ = royalty_ or (geo_co_ and len(re.findall(r"(?i)\b\d+(?:\.\d+)?\s*%\s+(?:[A-Za-z]+\s+){0,3}(?:royalty|stream)\b", text)) >= 3)
    for ci, clause in enumerate(cls):
        if len(clause) > 1500 or not re.search(r"\d", clause):
            continue
        # 1.3.2: '147,433 oz of gold (guidance range: 135,000 - 144,000 oz)': the guidance the figure was measured
        # against, on the figure's row, and not a figure of its own
        gparen_ = {}
        for gp in list(re.finditer(r"(?i)\(\s*(?:revised\s+|updated\s+|original\s+)?guidance(?:\s+range)?\s*(?:of|:|was|-)?\s*([^()]{3,60})\)", clause)):
            inner = gp.group(1)
            gm = _mentions(inner)
            if len(gm) != 1 or _periods(inner):
                continue
            lo_ = _range_at(inner, gm[0], gm)
            if lo_ is None:
                continue
            gparen_[gp.start()] = (lo_, gm[0]["value"], gm[0]["unit"])
            clause = clause[:gp.start()] + " " * (gp.end() - gp.start()) + clause[gp.end():]
        mentions = _mentions(clause, royalty_)
        if not mentions:
            continue
        _resp_metals(clause, mentions)      # 1.3
        resp = _respectively(clause, mentions, doc)
        if resp:
            mentions = resp[0]
        if len(mentions) >= 3 and not any(m["metal"] for m in mentions) and not re.search(
                r"(?i)\b(gold|silver|copper|zinc|lead|nickel|cobalt|uranium|u3o8|lithium)\b", clause):
            continue      # a flattened table row: its columns are not in the text around it
        periods_all = _periods(clause)
        cmp_ = [p_ for p_ in periods_all if _COMPARATIVE.search(clause[max(0, p_[0] - 70):p_[0]]) or _descending_year(clause, p_)]
        periods = [p_ for p_ in periods_all if p_ not in cmp_]   # 1.3.1: a comparison's period is never a figure's own
        guide_clause = bool(_GUIDE.search(clause))
        produced_rows = []
        roles = {}
        cmp_drop_ = None
        for i, men in enumerate(mentions):
            nxt = mentions[i + 1]["start"] if i + 1 < len(mentions) else len(clause)
            prev_end = mentions[i - 1]["end"] if i else 0
            pre = clause[max(prev_end, men["start"] - 90):men["start"]]
            pre_long = clause[max(0, men["start"] - 90):men["start"]]
            post = clause[men["end"]:men["end"] + 50]
            if _SUFFIX_NOT.match(post) or _SUFFIX_MONEY.match(post) or _SUFFIX_ORE.match(post):
                continue
            if re.match(r"(?i)^[^.;]{0,60}?\b(?:on\s+an\s+)?annuali[sz]ed\b|^[^.;]{0,40}?\brun[\s\-]+rate\b", post) or \
                    re.search(r"(?i)\bcurrently\s+produces?\s*$", clause[max(0, men["start"] - 30):men["start"]]):
                continue      # '... currently produces 270,000 tonnes ... on an annualized basis' (1.1)
            if re.match(r"(?i)^[^.;]{0,80}?\b(?:were|was|been)\s+(?:acquired|purchased|bought)\b", post) or \
                    re.search(r"(?i)\b(?:acquired|purchased|bought)\s*$", clause[max(0, men["start"] - 25):men["start"]]):
                continue      # 'Finished products in the amount of 936 oz of gold ... were acquired' (1.1)
            gprice = bool(_SUFFIX_GPRICE.match(post))
            if re.match(r"(?i)\s*of\s+(?:gold\s+|silver\s+)?(?:dor\u00e9|dore)\b", post):
                continue      # '956.8 troy ounces of dor\u00e9': the bars' weight, not the metal in them (1.1)
            metal = men["metal"]
            if not metal:
                # the metal named just before the figure, within the clause ('copper production of 58,273 tonnes')
                metal = _metal_last(re.sub(r"\([^()]{0,40}\)", lambda m_: " " if len(_METAL_RE.findall(m_.group(0))) >= 2 else m_.group(0),
                                          clause[max(0, men["start"] - 70):men["start"]]))   # 1.3.1: '(only silver and gold)' (SVM)
            clause_metal = None
            if not metal:
                # 1.2: 'Attributable silver production of 22.8 million ounces exceeded the updated annual guidance range,
                # with a record 7.3 million ounces produced in Q4 2025' (PAAS): the only metal the clause has named. For
                # an actual only: Cameco's guidance clause names its 100% figure and its share, and leaves the metal to
                # the share
                named_ = {_metal_of(x.group(0)) for x in _METAL_RE.finditer(clause[:men["start"]])} - {None}
                if len(named_) == 1:
                    clause_metal = named_.pop()
            if re.search(r"(?i)(?:\bcompared\s+(?:to|with)|\bversus|\bvs\.?|\brelative\s+to|(?<!more\s)(?<!greater\s)(?<!less\s)(?<!fewer\s)\bthan|\b(?:up|down|increased?|decreased?|rose|fell)\s+(?:[\w%\s]{0,20}?\s)?from)\s+(?:approximately\s+|about\s+|~\s*)?$",
                         clause[max(0, men["start"] - 60):men["start"]]):
                if metal:
                    cmp_named_.add((men["unit"], metal))
                continue      # 1.3.1: the comparison's figure ('a decrease of 5% compared to 2.1 million ounces in Q3 Fiscal 2025')
            if re.search(r"\(\s*or\s*$", clause[max(0, men["start"] - 10):men["start"]]) or \
                    re.search(r"(?i)\b(?:increase[ds]?|decrease[ds]?|up|down|rose|fell|grew|by)\s+(?:by\s+)?[\d.,]+\s*%\s*\(\s*$", clause[max(0, men["start"] - 40):men["start"]]) or \
                    re.match(r"(?i)\s*\)\s*(?:greater|higher|lower|less|more|fewer|above|below)\b|\s+(?:greater|higher|lower|less|more|fewer)\s+than\b|\s*(?:reduction|decrease|increase|decline|shortfall)\b", clause[men["end"]:men["end"] + 30]):
                continue      # 1.3.1: '71% (or 100,102 ounces) greater than the same period in 2016' (BTO): a change, not a figure
            if re.match(r"(?i)\s*(?:of\s+)?(?:other|base)\s+metals\b", clause[men["end"]:men["end"] + 30]):
                continue      # 1.3.1: '12,000 to 15,000 GEOs of other metals' (WPM): a part of the total
            pb_ = [p_ for p_ in periods_all if p_[1] <= men["start"] and men["start"] - p_[1] <= 160]
            if resp and i in resp[1]:
                if resp[1][i] in {_resolve(k_, g_, doc) for s_, e_, k_, g_ in cmp_} - {_resolve(k_, g_, doc) for s_, e_, k_, g_ in periods}:
                    continue      # 1.3.1: '... lower than 2023 with approximately 1.7 million ounces and 2.0 million ounces, respectively' (USA)
                pb_ = []
            gap_ = clause[pb_[-1][1]:men["start"]] if pb_ else ""
            if (pb_ and pb_[-1] in cmp_ and pb_[-1][1] >= prev_end and len(gap_) <= 45 and not re.search(r"[.;,]", gap_) and
                    not re.match(r"(?i)\W*(?:at|to)\b", gap_)) or \
                    (i and cmp_drop_ == i - 1 and re.fullmatch(r"(?i)\s*(?:and|,)\s*(?:approximately\s+)?", clause[prev_end:men["start"]])):
                cmp_drop_ = i
                if metal:
                    cmp_named_.add((men["unit"], metal))
                continue      # 1.3.1: '6% higher than Q1-2021 production of 15.5 M lbs' (ARG): the compared period's figure
            period, pkind = _period_for(clause, men, periods, doc, nxt)
            if resp and i in resp[1]:
                period, pkind = resp[1][i], "resp"
            if pkind == "span":
                continue
            if pkind in ("ytd", "ytdm", "m9", "h6b", "h6") and men.get("tabular"):
                continue      # 1.3: a table's YTD header over flattened cells is not this figure's (AG: tonnes milled)
            if re.search(r"(?i)\bcopper\s+c\s*oncentrate\s+produc\w*\s+(?:during|in|for)?[^.;]{0,60}$", pre_long) and men["unit"] == "t":
                continue      # 1.3: 'Copper concentrate produced ... of 73,751 tonnes' is the concentrate's weight (DPM)
            if re.match(r"(?i)^[^.;]{0,45}?\b(?:vanadium|V\s*2\s*O\s*5)\b", post):
                continue      # 1.3: '1,300,000 pounds of high-purity V2O5' (EFR)
            if re.search(r"(?i)\btrailing\s+(?:12|twelve)[\s\-]+months?", clause[max(0, men["start"] - 220):men["start"]]) and \
                    not _GUIDE.search(clause[max(0, men["start"] - 80):men["start"]]):
                continue      # 1.3: 'the trailing 12 months' total ... increasing 5% over its 2016 annual production to 133,030' (ARIS)
            # a part of the figure before it, of the same metal, or an asset's share of the company's (1.1)
            win = clause[max(prev_end, men["start"] - 60):men["start"]]
            if re.search(r"(?i)\bfrom\s+(?:our\s+|the\s+|its\s+)?(?:precious\s+metals?|diversified|energy|oil\s+(?:and|&)\s+gas|other\s+mining|iron\s+ore)\s+(?:assets|portfolio|segment)",
                         clause[max(0, men["start"] - 90):men["start"]]):
                continue      # 1.3.1: 'GEOs sold from our Precious Metal assets amounted to 114,111 GEOs' (FNV): one segment's
            ex_ = re.search(r"(?i)\bexcludes\b(?P<gap>[^.;]*)$", clause[max(0, men["start"] - 110):men["start"]])
            if not i and ex_ and not re.search(r"(?i)\b(?:is|was|are|were|be|expected|totall?ed|amounted|reached)\b", ex_.group("gap")):
                continue      # 1.3.1: '... excludes payable gold production at La India and Creston Mascota of 1,811 ounces' (AEM)
            if _CONTRIBUTE.search(win) or (_COMPONENT.search(win) and i and (
                    metal is None or mentions[i - 1].get("metal") in (None, metal)) and mentions[i - 1]["unit"] == men["unit"]):
                continue
            dq = doc.get("fiscal_quarter") or doc.get("quarter")     # 1.3 (ORV)
            if period is None and not periods and not re.search(r"(?i)reserves?\b|resources?\b|life[\s\-]+of[\s\-]+mine|mine\s+life|\bNPV|\bIRR\b|\bstudy\b|\bPEA\b|feasibility", clause):
                hp_ = _heading_period(cls, ci, doc)
                if hp_:
                    period, pkind = hp_       # 1.3.1: a bullet under '2023 Highlights' is the year's (SCZ)
            prev = cls[ci - 1][-300:] if ci else ""
            if period is None and not periods and cmp_ and cmp_[-1][2] in ("yr", "fy", "fy2") and not _GUIDE.search(clause[:men["start"]]) and \
                    not _guidance_scope(cls, ci):
                # 1.3.1: 'Silver production reached 13.2 million ounces, a 13% increase over 2018' (AG): compared with a year,
                # the figure is the next year's -- the release's own year in a Q4 / year-end release, else nobody's
                y_ = re.search(r"20\d\d", clause[cmp_[-1][0]:cmp_[-1][1]])
                if y_ and doc.get("year") and int(y_.group(0)) + 1 == int(doc["year"]) and \
                        (doc.get("quarter") in (None, "Q4 " + doc["year"])) and not doc.get("fiscal_quarter"):
                    period, pkind = "FY " + doc["year"], "fy"
                else:
                    continue
            if period is None and dq and _annual_scope(cls, ci, clause[:men["start"]]):
                dq = ("FY " + dq[-4:]) if re.fullmatch(r"Q4 20\d\d", dq) else None     # 1.3.1 (DPM)
            if period is None and dq and (re.search(r"\bABOUT\s+[A-Z]{3,}|(?i:\babout\s+(?:the\s+company|us)\b)", " ".join(cls[max(0, ci - 3):ci])[-600:] + " " + clause[:men["start"]]) or
                                          re.search(r"(?i)\bgoal\b|\bproducing\s+over\b|\bto\s+build\b|\bvision\b", clause)):
                dq = None     # 1.3.1: 'ABOUT WESDOME ... producing over 200,000 ounces from two mines' is not the quarter's
            if period is None and dq and re.search(r"(?i)\b(?:six|nine|6|9)\s+months\s+ended|first\s+half", prev) \
                    and not re.search(r"(?i)\bthree\s+(?:and\s+(?:six|nine)\s+)?months|quarter|\bQ[1-4]\b", prev):
                dq = None     # under a 'Six months ended June 30, 2025' heading, a figure is not the quarter's (1.1)
            if period is None and not periods and dq and \
                    not re.search(r"(?i)\byear|annual|month|to\s+date|YTD|since|life|post[\s\-]*commercial",
                                  re.sub(r"(?i)\b(?:year|quarter)[\s\-]+(?:over|on)[\s\-]+(?:year|quarter)\b", " ", clause)):   # 1.3.1: 'a 30% increase year-over-year' (SCZ)
                period, pkind = dq, "doc"
            elif period is None and pkind is None and dq and ci <= 25 and not re.search(
                    r"(?i)full[\s\-]*year|for\s+the\s+year|to[\s\-]+date|YTD|annual|\bmonth|\bdaily\b|\bper\s+day\b|\bweek|since|life|\b20\d\d\b|(?<!Q[1-4]\s)(?<!Q[1-4])(?<!Q\s[1-4]\s)\bFY\s*'?\d\d|\bH[12]\b|half|\b(?:" + _MONTHS + r")\b",
                    clause[:men["end"] + 40]):
                # 'Produced 197,628 ounces of gold, including ... (2026 guidance)': in the opening, a figure whose
                # sentence names no period before it is the release's own quarter (1.1)
                period, pkind = dq, "doc"

            # ---- guidance
            low = _range_at(clause, men, mentions)
            single = None if low is not None else _guidance_single(clause, men)
            if (low is not None or single) and guide_clause:
                if re.match(r"(?i)^[^.;]{0,40}?\b20\d\d\s*(?:-|\u2013|to|and)\s*20\d\d\b", clause[men["end"]:men["end"] + 60]):
                    continue      # 1.3.1: '160,000-180,000 ounces for 2018-2019' (ELD): two years' guidance
                period, pkind = _period_for(clause, men, periods, doc, nxt, prefer_before=True)
                if pkind == "span":
                    continue
                if pkind in ("ytd", "ytdm", "m9", "h6b", "h6"):
                    continue      # 1.3: guidance is never for a year-to-date
                if pkind in ("fyn", "doc") and re.match(r"(?i)^(?:[^.;]|(?<=\d)\.(?=\d)){0,70}?\bby\s+(?:the\s+)?(?:end\s+of\s+)?20\d\d\b", clause[men["end"]:men["end"] + 90]):
                    continue      # 1.3: '... 1.5 million ounces, respectively, by 2021' (CS): a target
                if re.search(r"(?i)inventor|stockpil|to\s+hold|purchase|acqui|\bsales\b|\bsell\b",
                             clause[max(0, men["start"] - 70):men["end"] + 60]):
                    continue      # inventory, purchases and sales ranges are not production guidance
                if re.search(r"(?i)\bto\s+mine\b|\bmining\s+of\b", clause[max(0, men["start"] - 70):men["start"]]) or \
                        (low is None and re.search(r"(?i)\b(?:top|upper|high|low|bottom)\s+end\s+of\s+(?:[\w-]+\s+){0,5}?guidance\s+(?:to|at)\s*$",
                                                   clause[max(0, men["start"] - 90):men["start"]])) or \
                        re.match(r"(?i)^[^.;]{0,40}?\bin\s+ore\b", post):
                    continue      # 1.2: 'expects to mine ... 750,000 to 850,000 pounds of contained U3O8 in ore' (UUUU); 'raise the top
                                  # end of our guidance to 240,000 ounces' is half a range (MSA)
                gpre = _last_part(clause[max(0, men["start"] - 110):men["start"]])
                if _GUIDE_PAST.search(gpre) or \
                        re.search(r"(?i)annuali[sz]ed|per\s+annum|run[\s\-]+rate|\bper\s+year\b", clause[men["end"]:men["end"] + 40]) or \
                        re.search(r"(?i)including\s+\$?[\d,.]*\s*(?:to|-|\u2013)?\s*$", clause[max(0, men["start"] - 30):men["start"]]):
                    continue
                if _NOT_PRODUCTION.search(_last_part(clause[max(0, men["start"] - 60):men["start"]])) and \
                        not re.search(r"(?i)guidance", clause[max(0, men["start"] - 60):men["start"]]):
                    continue
                if re.search(r"(?i)\b(cost|aisc|capital|capex|revenue|sales|sold|cash)\b", clause[max(0, men["start"] - 35):men["start"]]):
                    continue
                if re.match(r"(?i)^[^.;]{0,60}?\(\s*100\s*%\s*basis\s*;[^)]{0,60}\bshare\b", post + clause[men["end"] + 50:men["end"] + 130]):
                    continue      # 1.2: '14 million and 15 million pounds ... (100% basis; 9.8 million to 10.5 million pounds our share)': the share (CCO)
                if not period:
                    continue
                if resp and i in resp[1]:
                    period = resp[1][i]
                head = clause[:men["start"]]
                pe_ = re.search(r"(?:^|[.;,:]\s*|\band\s+)(?!(?:The|We|Our|It|This|Its|Management|Company)\b)([A-Z][\w&\u2019'.\-]+(?:\s+[A-Z][\w&\u2019'.\-]+){0,3})\s+"
                                r"(?:expects|anticipates|forecasts|projects|guides)\b[^.;]{0,90}?\bto\s+produce\b", head[-220:])
                pd_ = re.search(r"(?<![\w\u2019'])(?!(?:The|We|Our|It|This|Its|Management|Company)\b)([A-Z][\w&\u2019'.\-]+(?:\s+[A-Z][\w&\u2019'.\-]+){0,3})\s+(?:has\s+)?(?:disclosed|reported|reiterated|announced|provided)\b[^.;]{0,130}\bguidance\b", head[-240:])
                if (royalty_ or geo_co_) and ((pe_ and pe_.group(1).split()[0].lower() not in issuer) or
                                 (pd_ and pd_.group(1).split()[0].lower() not in issuer) or
                                 re.search(r"(?i)\bfor\s+the\s+(?:mine|asset|operation)\b|\bthe\s+mine['\u2019]s\b|\boperator|most\s+recent\s+guidance|\bexpect\w*\s+deliveries\s+to\s+be\b", head[-220:])):
                    continue      # 1.3.1: a royalty company's partner's guidance ('Equinox Gold expects Greenstone to produce', FNV)
                if royalty2_ and metal not in ("GEO", "AuEq") and not re.search(r"(?i)\battributable\b", head[-250:] + clause[men["end"]:men["end"] + 60]) and \
                        not any(len(w) > 3 and w not in ("first", "second", "third", "fourth", "quarter", "results", "financial", "record", "annual")
                                and re.search(r"(?i)\b" + re.escape(w) + r"\b", head[-250:]) for w in issuer):
                    continue      # 1.3.1: a royalty company's own guidance is its attributable GEOs or metal ('Wheaton's estimated
                                  # attributable production'); a bare metal range is a partner's mine (Metalla, Triple Flag, FNV's Cobre Panama)
                if (_MINE_NAMED.search(head[-160:]) or _MINE_FOR.search(head[-170:])) and not re.search(r"(?i)consolidated|total|company|corporate", head[-80:]):
                    continue      # a mine's own guidance is not the company's (B2Gold's Goose, Equinox's Greenstone)
                if multi and _asset_context(head[-160:], assets) and not _COMPANY_CUE.search(head[-90:]) and \
                        not re.search(r"(?i)\bconsolidated\b", head[-240:]):
                    continue      # 'The Fekola Complex is expected to produce between 410,000 and 460,000 ounces' (1.1)
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
            # 1.3: a figure the release says was RECOVERED is a row of its own kind (Justin, 2026-09-28), never production
            rec = bool(_REC_POST.match(post)) or bool(_REC_PRE.search(pre_long[-50:]))
            if rec and (_REC_NOT.search(clause[max(0, men["start"] - 120):men["end"] + 90]) or
                        re.match(r"(?i)^[^.;]{0,50}?\bin\s+(?:the\s+)?first\s+\d+\s+days\b", post)):
                continue
            if _NOT_PRODUCTION.search(re.sub(r"(?i)\brecovered\b", " ", pre_long[-70:]) if rec else pre_long[-70:]) or gprice:
                continue
            metal = metal or clause_metal
            if re.search(r"(?i)\b(?:expected|expects?|anticipated|forecast|estimated|projected)\b(?:\s+\w+){0,3}\s*$", pre_long[-60:]) or \
                    re.search(r"(?i)\bexpects?\b[^.;]{0,120}\bto\s+(?:reach|be|total|exceed|produce)\b[^.;]{0,25}$", clause[max(0, men["start"] - 160):men["start"]]):
                continue      # 1.2: 'with an expected 1.6 million pounds of finished U3O8 produced from January through June' (UUUU)
            if re.search(r"(?i)\b(?:less|plus|minus)\s*$", pre_long) or re.search(r"(?i)\bsource\s*:", clause):
                continue      # 1.2: 'calculated from ... 179,000 ounces in 2025, less 94,000 ounces produced during ...' (FRED)
            role = None
            inherit = None
            if rec:
                role = "recovered"
            elif re.match(r"(?i)\s*(?:\(\W*\w+\W*\)\s*)?(?:were\s+|was\s+|have\s+been\s+)?(sold|delivered)\b", post) or \
                    re.match(r"(?i)\s*(?:of\s+)?sales\b", post):
                role = "sold"
            elif re.match(r"(?i)\s*(?:\(\W*\w+\W*\)\s*)?(?:were\s+|was\s+)?(produced|poured)\b|\s*of\s+(?:(?:gold|silver|copper|payable|attributable)\s+){0,2}production\b|"
                          r"\s*of\s+(?:gold|silver|copper)\s+(?:were\s+|was\s+)?(?:produced|poured)\b", post):   # 1.2: '213,245 ounces of gold produced for the full year'
                role = "produced"
            elif _LIST_VERB.match(clause[men["end"]:men["end"] + 120]):
                # 'A total of 11,960 gold ounces and 52,997 silver ounces were sold in Q2': the verb, and the period,
                # after the list (1.1)
                lv = _LIST_VERB.match(clause[men["end"]:men["end"] + 120])
                role = "sold" if lv.group(1).lower() in ("sold", "delivered") else "produced"
                tail = men["end"] + lv.end()
                for s_, e_, kd, gg in periods:
                    if period is None and s_ >= tail and kd != "span" and re.fullmatch(r"\s*(?:in|during|for)\s+(?:the\s+)?", clause[tail:s_]):
                        period = _resolve(kd, gg, doc)
                        break
            elif men.get("geo_verb"):
                role = "sold" if men["geo_verb"] in ("sold", "delivered") else "produced"
            else:
                kp = [(m.start(), "produced") for m in _PRODUCED.finditer(pre)] + \
                     [(m.start(), "sold") for m in _SOLD.finditer(pre)]
                if kp:
                    role = max(kp)[1]
                elif i and roles.get(i - 1) and _LIST_GAP.match(clause[prev_end:men["start"]]):
                    # '... 1,241,929 Ounces of Silver, 21,581 Tonnes of Zinc, 2,603 Tonnes of Lead': an item of a
                    # list shares the verb, and the subject, of the item before it (1.1)
                    role = roles[i - 1][0]
                    inherit = roles[i - 1][1]
                elif _PRODUCED.search(pre_long) and not _SOLD.search(pre_long):
                    role = "produced"
                elif resp and i in resp[1]:
                    # 'Consolidated gold production in Q4 2024 and FY 2024 increased ... to 49,567 ounces and ... to
                    # 172,033 ounces, respectively': the verb opens the sentence (1.1)
                    kp = [(m.start(), "produced") for m in _PRODUCED.finditer(clause[:men["start"]])] + \
                         [(m.start(), "sold") for m in _SOLD.finditer(clause[:men["start"]])]
                    role = max(kp)[1] if kp else None
            if role == "produced" and not period and doc.get("year") and not _PLAN.search(clause[max(0, men["start"] - 200):men["start"]]) and re.match(
                    r"(?i)^[^.;]{0,40}?\b(?:exceed\w*|achiev\w*|met|beat|within|in\s+line\s+with|at\s+the\s+(?:top|upper|high)\s+end\s+of)\s+"
                    r"(?:the\s+|its\s+|our\s+)?(?:\w+\s+){0,2}?(?:annual|full[\s\-]*year|20\d\d)\s+(?:production\s+)?guidance", post + clause[men["end"] + 50:men["end"] + 90]):
                # 1.2: '22.8 million ounces exceeded the updated annual guidance range' (PAAS): measured against the
                # year's guidance, the figure is the year's
                y_ = re.search(r"20\d\d", clause[men["end"]:men["end"] + 90])
                period = "FY %s" % (y_.group(0) if y_ and "guidance" in clause[men["end"]:men["end"] + 90][y_.end():y_.end() + 30] else doc["year"])
            if role is None or not period:
                continue
            if role == "recovered" and re.search(r"(?i)\bmonth\b", clause[max(0, men["start"] - 80):men["end"] + 60]) and \
                    not re.match(r"20\d\d-\d\d$", period):
                continue      # 1.3: '545,491 oz of silver recovered at the plant in a single month' is not the year's
            if role == "sold" and (re.search(r"(?i)\bproduction\s+and\s+sales?\s+of\s*$", clause[max(0, men["start"] - 40):men["start"]]) or
                                   re.search(r"(?i)pre[\s\-]?pay|\bstream(?:ing)?\b|forward\s+(?:sale|contract)", clause[max(0, men["start"] - 80):men["end"] + 60])):
                continue      # 'the production and sale of 54,862 ounces'; 'delivered 264,768 ounces into the Gold Prepay' (1.1)
            if (_GUIDE.search(pre) or _PLAN.search(pre_long)) and not re.search(
                    r"(?i)\b(produced|poured|production\s+(?:\d\s+)?(?:was|totall?ed|reached|of\s+(?:approximately\s+)?[\d,.]+\s*\w*\s*(?:in|for|during)\b))", pre + clause[men["start"]:men["end"] + 25]):
                continue      # in a sentence about plans, only a figure the release says was produced is an actual
            subj = _subject(pre_long, issuer)
            row = {"kind": "recovered" if role == "recovered" else "actual", "period": period, "metal": metal, "qty": men["value"], "unit": men["unit"],
                   "role": role, "approx": men["approx"], "_clause": ci, "_subject": subj, "_tabular": men.get("tabular"), "_doc": pkind == "doc",
                   "_mine": bool(re.search(r"(?i)\b(?:the\s+)?[A-Z][\w'\u2019\-]+(?:\s+[A-Z][\w'\u2019\-]+){0,2}\s+mine\s+(?:has\s+)?(?:produced|production)\b", pre_long)
                                 or re.match(r"(?:At|From)\s+(?:the\s+)?[A-Z]", clause) or bool(subj))}
            if re.search(r"(?i)(?:^|[,;:]\s*|\bthe\s+)mine\s+(?:has\s+)?produced\s*$", pre_long.strip()[-40:] + " ") or \
                    re.search(r"(?i)(?:^|[,;:]\s*)mine\s+(?:has\s+)?produced\b", pre_long[-40:]):
                row["_mine"] = True       # 1.3: 'Year to date, mine produced 12,067 gold ounces' (HSTR): the mine's, not the company's
            if inherit is not None:
                row["_subject"] = row["_subject"] or inherit.get("_subject")
                row["_mine"] = row["_mine"] or inherit.get("_mine")
            fm = re.search(r"(?:production|produced)\s+(?:at|from)\s+(?:the\s+)?((?:[A-Z][\w'\u2019\-]+\s+){0,2}[A-Z][\w'\u2019\-]+)(?:\s+(?:mine|Mine|operations?|Operations?))?\s+(?:was|were|totall?ed|of)\s*(?:approximately\s+)?$", pre_long)
            if fm and fm.group(1).split()[0].lower() not in _NOT_SUBJECT and not re.match(r"(?:Q[1-4]|H[12]|FY|20\d\d)", fm.group(1)):
                row["_mine"] = True       # 'Q3 2025 gold production from Karlawinda were 32,318 ounces' (1.1)
                row["_subject"] = row["_subject"] or fm.group(1).lower()
            na = None
            if multi and not row["_mine"]:
                for na in _NAMED_ASSET.finditer(clause[max(0, men["start"] - 200):men["start"]]):
                    pass
            if multi and not row["_mine"] and pkind in ("ytd", "ytdm", "m9", "h6b", "h6") and \
                    re.search(r"(?i)\bthe\s+mine['\u2019]s\b", clause[men["end"]:men["end"] + 160]):
                row["_mine"] = True           # 1.3: '... totaled 6.3 million ounces and 41,692 ounces respectively; being 13 percent
                                              # above the mine's nine-month projection' (FVI's San Jose section)
            if na and (re.search(r"(?i)\b(?:the\s+company|consolidated|we|our)\b", clause[max(0, men["start"] - 200):men["start"]][na.end():]) or
                       re.search(r"(?i)\bconsolidated\b", clause[max(0, men["start"] - 200):men["start"]][:na.start()])):     # 'consolidated lead production at the Topia mine' (GSVR)
                na = None             # 'including attributable production from the Haile Gold Mine, the Company produced' (OGC)
            if na:
                nm = na.group("n1") or na.group("n2")
                if nm.split()[0].lower() not in _NOT_SUBJECT and not set(w.lower() for w in nm.split()) & issuer and \
                        not _NOT_ASSET_NAME.match(nm):
                    row["_named"] = nm.lower()     # 1.3: weighed in _consolidate
            if multi and not row.get("_named") and not row["_mine"] and pkind in ("ytd", "ytdm", "m9", "h6b", "h6") and \
                    not _COMPANY_CUE.search(clause[:men["start"]]):
                # 1.3: 'Production in the first three quarters of 2025 totaled 50,031 ounces' under a Kiena section (WDO): a
                # year-to-date right after a named asset's figures is that asset's
                sec_ = [o for o in rows if isinstance(o.get("_clause"), int) and ci - 5 <= o["_clause"] < ci and
                        (o.get("_asset_row") or o.get("_named"))]
                if sec_:
                    row["_named"] = sec_[-1].get("_named") or sec_[-1].get("_subject") or "asset"
            at = _AT_ASSET.match(post) if not re.match(r"(?i)\s*(?:\(\W*[\w ]{0,12}\W*\)\s*)?(?:of\s+\w+\s+)?(?:\w+\s+)?(?:in|for|during)\b", post) else None
            if at and (re.fullmatch(r"(?i)[A-Z]{1,2}\d*|AISC|US|C\$|CAD|USD", at.group(1).split()[0])
                       or re.match(r"(?i)\s*(?:cash|costs?|aisc|all[\s\-]+in|grades?|recover\w*|prices?|per\b|average)", post[at.end():])):
                at = None         # '57,416 tonnes at C1 cash costs of $2.45/lb': a cost, not a place (1.1)
            if at and at.group(1).split()[0].lower() not in _NOT_SUBJECT and not re.match(r"(?i)(?:Q[1-4]|H[12]|FY|20\d\d)", at.group(1)):
                row["_mine"] = True       # '1,975 ounces produced at Castle Mountain' (1.1)
                row["_subject"] = row["_subject"] or at.group(1).lower()
            if multi and row["_mine"] and not re.search(r"(?i)consolidated|\btotal\b|company[\s\-]+wide", pre_long):
                row["_asset_row"] = True
            # 1.2: '8,459 Gold Equivalent Ounces (GEOs) (8,180 gold ounces and 21,494 silver ounces)': the metals
            # behind the company's own equivalent figure are its production too (HSTR)
            bk = _BREAKDOWN.search(clause[max(0, men["start"] - 140):men["start"]])
            if metal in ("gold", "silver", "copper") and bk and \
                    not re.search(r"(?i)\b(?:subsidiary|mine|operations?|complex|project|property)\b", clause[:max(0, men["start"] - 140) + bk.start()]):
                row["_brk"] = True    # (not a named mine's: 'Orovalle ... produced 9,827 GEO (8,464 gold ounces, ...)', ORV)
            if role == "sold" and re.search(r"(?i)\brevenue\b", clause[max(0, men["start"] - 120):men["start"]]):
                row["_rev"] = True    # 1.2: 'Revenue for the six months ... was $328.8 million mainly from 71,110 gold ounces sold' (HMMC)
            for gs_, (glo_, ghi_, gu_) in gparen_.items():
                if gs_ >= men["end"] and re.fullmatch(r"[^\d.;]{0,30}", clause[men["end"]:gs_]) and gu_ == men["unit"] and \
                        0.67 <= men["value"] / ((glo_ + ghi_) / 2) <= 1.5:
                    row["guided_low"], row["guided_high"] = glo_, ghi_      # 1.3.2
                    break
            if role == "produced":
                produced_rows.append(row)
            roles[i] = (role, row)
            rows.append(row)
        # AISC stated in the same clause as a single produced figure goes on that row
        if len(produced_rows) == 1:
            m = re.search(r"(?i)\bAISC\b[^.]{0,60}?\$\s?([\d,]+(?:\.\d+)?)\s*(?:per|/)\s*(?:ounce|oz)", clause)
            if m:
                produced_rows[0]["aisc"] = _num(m.group(1))

    # 1.1: tables, after the sentences (a sentence's figure wins over a table's for the same row)
    rows.extend(_table_rows(text, doc, multi, assets))
    rows.extend(_metal_col_rows(text, doc))
    rows.extend(_period_col_rows(text, doc, multi))
    rows.extend(_guide_actual_rows(text, doc, multi, head))
    rows.extend(_guide_table_rows(text, doc, multi))     # 1.3.2
    rows.extend(_last_col_recovered(text, doc, multi))     # 1.3
    g = len(re.findall(r"(?i)\bgold\b", text[:4000]))
    sv = len(re.findall(r"(?i)\bsilver\b", text[:4000]))
    royalty = bool(re.search(r"(?i)\b(?:royalty|streaming)\s+(?:and\s+streaming\s+)?compan(?:y|ies)\b|\broyalt(?:y|ies)\s+(?:and|&)\s+stream",
                             (body or "")[:3000]))
    rows = _consolidate(rows, "gold" if g >= 3 * max(sv, 1) else "silver" if sv >= 3 * max(g, 1) else None, multi, doc, royalty, cmp_named_)
    # 1.1: AISC stated for the release's own period, from a sentence or a table, goes on its actual row
    aisc_p = _prose_aisc(text, doc, multi, assets)
    aisc_t = _table_aisc(text, doc, multi)
    for r in rows:
        if r["kind"] != "actual" or r.get("aisc") is not None:
            continue
        fam = "silver" if r["metal"] in ("silver", "AgEq") else "gold" if r["metal"] in ("gold", "AuEq", "GEO") else None
        if not fam:
            continue
        v = aisc_p.get((r["period"], fam))
        if v is None and fam == "gold" and not any(x["kind"] == "actual" and x["metal"] in ("silver", "AgEq") and x["period"] == r["period"] for x in rows):
            v = aisc_t.get(r["period"])
        if v is not None and not any(x is not r and x["kind"] == "actual" and x["period"] == r["period"] and x.get("aisc") == v for x in rows):
            r["aisc"] = v
    rows = _fold_ended_guidance(rows, doc)     # 1.3.2
    # 1.3.2: basis -- the release states its production on a 100% basis ('Asanko Gold Mine Highlights (100% basis)', 'metal
    # production from Red Chris (100% basis)'): the page says so on its rows (a field only; no row is added or removed)
    if re.search(r"(?i)\b(?:production|produced|operational|operating|highlights|results)\b[^.;$]{0,60}\(\s*100\s*%\s*basis|"
                 r"\b(?:production|produced)\b[^.;$]{0,80}\bon\s+a\s+100\s*%\s*basis", text[:4000]) and not (royalty_ or royalty2_):
        for r in rows:
            if r["kind"] in ("actual", "guidance") and not r.get("basis"):
                r["basis"] = "100% basis"
    for ms in milestones(headline, body):
        rows.append(ms)
    res["rows"] = rows[:40]
    res["is_production"] = bool(rows)
    res["reason"] = "rows" if rows else "no_rows"
    return res


_BREAKDOWN = re.compile(r"(?i)(?:\bGEOs?\b|gold\s+equivalent\s+ounces?|\bAuEq\b|\bAgEq\b|silver\s+equivalent\s+ounces?)\)?\s*"
                        r"(?:\([^()]{0,12}\)\s*)?\(\s*(?:[\d,.]+\s+(?:gold|silver|copper)\s+(?:ounces|oz|pounds|lbs|tonnes)\s*(?:,\s*(?:and\s+)?|and\s+))*$")


_OZ_METALS = {"gold", "silver", "GEO", "AuEq", "AgEq", "palladium", "platinum"}


_CAP = {("oz", "gold"): 8e6, ("oz", "AuEq"): 8e6, ("oz", "GEO"): 3e6, ("oz", "silver"): 1.2e8, ("oz", "AgEq"): 1.5e8,
        ("oz", "palladium"): 4e6, ("oz", "platinum"): 4e6, ("lb", "U3O8"): 4e7, ("t", "copper"): 2.5e6,
        ("lb", "copper"): 5e9, ("t", "lithium concentrate"): 2e6}


def _unit_fits(metal, unit):
    if metal in _OZ_METALS:
        return unit == "oz"
    if metal == "U3O8":
        return unit == "lb"
    return unit in ("t", "lb")


def _plausible(r):
    """A quantity inside what one producer can report for one period (and not a zero or a footnote mark)."""
    vals = [v for v in (r.get("qty"), r.get("low"), r.get("high")) if v is not None]
    if not vals:
        return True
    cap = _CAP.get((r["unit"], r["metal"]), 4e9 if r["unit"] == "lb" else 2e6 if r["unit"] == "t" else 1e8)
    floor = 100 if r["unit"] == "oz" else 1
    return all(floor <= v <= cap for v in vals)


_RESP_BARE = re.compile(r"(?<![\w.,$])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?:,\s*(?:and\s+)?|\s+and\s+)$")


_RESP_METALS = re.compile(r"(?i)\b((?:gold|silver|copper|zinc|lead)(?:\s+equivalent)?(?:\s*,\s*(?:gold|silver|copper|zinc|lead)(?:\s+equivalent)?)*\s+and\s+(?:gold|silver|copper|zinc|lead)(?:\s+equivalent)?)"
                          r"\s+(?:production|produced|output|sales|sold)\b")


def _resp_metals(clause, mentions):
    """1.3: 'Silver and gold production for the first six months of 2022 totaled 3,323,023 ounces and 128,971 ounces,
    respectively' (FVI): the figures take the metals in order."""
    for m in _RESP_METALS.finditer(clause):
        # each metal list takes the first 'respectively' after it (FVI: 'Zinc and lead ... respectively Consolidated
        # gold and silver production ... totaled 182,394 ounces and 2.1 million ounces, respectively')
        r = re.compile(r"(?i)\brespectively\b").search(clause, m.end())
        if not r or _RESP_METALS.search(clause[m.end():r.start()]):
            continue
        metals = [{"silver equivalent": "AgEq", "gold equivalent": "AuEq"}.get(" ".join(w.lower().split()), _metal_of(w))
                  for w in re.findall(r"(?i)(?:gold|silver|copper|zinc|lead)(?:\s+equivalent)?", m.group(1))]
        men = [x for x in mentions if m.end() <= x["start"] and x["end"] <= r.start()]
        if len(men) == len(metals) and len(set(metals)) == len(metals) and all(x["metal"] is None for x in men):
            for x, mt in zip(men, metals):
                x["metal"] = mt


def _respectively(clause, mentions, doc):
    """'... 26,702 and 94,561 ounces of gold in Q4 and FY 2024, respectively': the figures take the periods in order.
    Returns (mentions, {index: period}) or None (1.1)."""
    r = re.search(r"(?i)\brespectively\b", clause)
    if not r:
        return None
    # the sentence that ends in 'respectively': from the last sentence break with two figures after it
    start = 0
    for b in reversed([x.end() for x in re.finditer(r"[.;:](?=\s)|[\u2022\u25cf\u25aa\u25e6]", clause[:r.start()])]):
        if sum(1 for m in mentions if b <= m["start"] and m["end"] <= r.start()) >= 1 and \
                re.search(r"\d", clause[b:r.start()]):
            start = b
            break
    seg = clause[:r.start()]
    men = [m for m in mentions if m["end"] <= r.start() and m["start"] >= start]
    # a bare figure joined to the next one ('26,702 and 94,561 ounces') shares its unit and metal
    extra = []
    for m in men:
        b = _RESP_BARE.search(seg[max(0, m["start"] - 30):m["start"]])
        if b:
            st = max(0, m["start"] - 30) + b.start(1)
            if not any(x["start"] <= st < x["end"] for x in men):
                extra.append(dict(m, start=st, end=st + len(b.group(1)), value=_num(b.group(1))))
    men = sorted(men + extra, key=lambda x: x["start"])
    per = []
    for s_, e, kind, g in _periods(seg):
        if s_ < start:
            continue
        if kind == "qn" and re.match(r"(?i)\s+and\s+(?:FY|full|fiscal|year)", seg[e:e + 20]):
            # 'Q4 and FY 2024': the quarter takes the year that follows
            y = re.search(r"20\d\d", seg[e:e + 30])
            per.append("Q%s %s" % (_ORD.get(g[0].lower(), g[0]) if not g[0].isdigit() else g[0], y.group(0)) if y else _resolve(kind, g, doc))
        elif kind != "span":
            per.append(_resolve(kind, g, doc))
    units = {m["unit"] for m in men}
    if len(men) < 2 or len(per) != len(men) or len(units) != 1 or None in per:
        return None
    rest = [m for m in mentions if m["end"] > r.start()]
    return sorted(men + rest, key=lambda x: x["start"]), {i: per[i] for i in range(len(men))}


# ------------------------------------------------------------------ 1.1: production tables
# A table row: '<metal> produced (ounces) 43,824 42,781 89,127 88,473'. Only the first column is read, and only when
# the nearest header above it shows that the first column is the release's own period (its quarter, or its year).
_TCELL = r"(?:\(?-?\$?\s?\d[\d,]*(?:\.\d+)?\)?%?|-|\u2014|\u2013|n/a|N/A)"
_TMETAL = (r"(?P<metal>Gold\s+equivalent|Silver\s+equivalent|Gold|Silver|Copper|Zinc|Lead|Nickel|Cobalt|Uranium|U3O8|"
           r"AgEq|AuEq|GEOs?)")
_TUNIT = r"(?:ounces?|oz|koz|k-oz|tonnes|t|lbs?|pounds|Mlbs?|000\s*oz|000s?\s*lbs|000'?s\s+(?:oz|lbs))"
_TROW = re.compile(
    r"(?<![\w/$])(?P<pre>(?:Total|Consolidated|Attributable|Payable)\s+)?" + _TMETAL +
    r"(?:\s+(?P<u1>ounces?|oz|tonnes|pounds|lbs)\b)?"
    r"\s+(?P<role>produced|production|payable\s+production|poured|sold|recovered)\b"
    r"(?:\s*[\d\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079](?=\s))?(?:\s*\((?P<u2>[^()]{1,30})\))?(?:\s+(?P<u3>" + _TUNIT + r")\b\.?)?"
    r"(?:\s*\(\d\))?(?:\s*[\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079])?\s+(?P<v1>\d[\d,]*(?:\.\d+)?)(?P<rest>(?:\s+" + _TCELL + r"){0,8})", re.I)
_TAISC = re.compile(r"(?i)(?<![\w])(?:all[\s\-]+in[\s\-]+sustaining\s+costs?|AISC)(?:\s*[\d\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079](?=\s))?"
                    r"(?:\s*\((?:[^()]{0,30})\))*(?:\s+per\s+(?:gold\s+|silver\s+)?(?:ounce|oz)(?:\s+(?:of\s+gold\s+)?sold)?)?"
                    r"(?:\s*\((?:[^()]{0,30})\))*(?:\s+\(?(?:US|C|CA)?\$\s?/\s?oz\)?)?(?:\s*[\d\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079](?=\s))?"
                    r"\s+(?:US|C|CA)?\$?\s?(?P<v1>\d[\d,]*(?:\.\d+)?)(?P<rest>(?:\s+" + _TCELL + r"){1,8})")
_TSALES = re.compile(r"(?i)\s+(?:sales|sold|ounces\s+sold)(?:\s*\(\d\)|\s*[\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079])?\s+(?P<v1>\d[\d,]*(?:\.\d+)?)"
                     r"(?P<rest>(?:\s+" + _TCELL + r"){0,8}?)(?=\s+[A-Za-z(]|\s*$)")
_HQ = re.compile(r"(?i)\b(?:Q([1-4])\s*-?\s*['\u2019]?\s*(?:CY|FY)?\s*((?:20)?\d\d)\b|([1-4])Q\s*['\u2019]?((?:20)?\d\d)\b|(20\d\d)\s*[-\s]?Q([1-4])\b|"
                 r"(first|second|third|fourth)\s+quarter\s+(?:of\s+)?(20\d\d)|(?:three|3)\s+months\s+ended(?:\s+(\w+)\.?\s+\d{1,2},?(?:\s*(20\d\d))?)?|"
                 r"(?:year|twelve\s+months|12\s+months)\s+ended\s+\w+\.?\s+\d{1,2},?(?:\s*(20\d\d))?|(?:FY|full[\s\-]+year|12M)\s*(20\d\d)|"
                 r"H([12])\s*['\u2019]?\s*(20\d\d)|(20\d\d)\s+(?:YTD|year[\s\-]+to[\s\-]+date)|(?:six|6|nine|9)\s+months\s+ended)\b")
_MONQ = {"mar": 1, "march": 1, "jun": 2, "june": 2, "sep": 3, "sept": 3, "september": 3, "dec": 4, "december": 4}


# 1.3.2: every column of a table header, not only the first ('Three months ended June 30, Six months ended June 30, 2026
# 2025 2026 2025', 'Q2 2026 Q2 2025 H1 2026 H1 2025', 'Q4 2025 Q4 2024 2025 2024'), so the half-year, nine-month or year
# column beside the release's own quarter is read too
_HC_TOK = re.compile(
    r"(?i)(?P<t0>\bQ[1-4]\s+(?:YTD|year[\s\-]+to[\s\-]+date)\b(?:\s*(?P<t0y>20\d\d)\b)?)|"     # 'Q2 YTD 2019'
    r"(?P<q>\bQ(?P<qa>[1-4])\s*-?\s*['\u2019]?\s*(?:CY\s*)?(?P<qay>(?:20)?\d\d)\b|\b(?P<qb>[1-4])Q\s*['\u2019]?\s*(?P<qby>(?:20)?\d\d)\b|"
    r"\b(?P<qcy>20\d\d)\s*-?\s*Q(?P<qc>[1-4])\b|\b(?P<qd>first|second|third|fourth)\s+quarter(?:\s+(?:of\s+)?(?P<qdy>20\d\d))?\b|\bQ(?P<qe>[1-4])\b)"
    r"|(?P<m>\b(?P<mn>three|3|six|6|nine|9|twelve|12)[\s\-]+months?(?:\s+(?:ended|ending))?(?:\s+(?P<mm>" + _MONTHS +
    r"|sept?|dec|mar|jun)\.?\s+\d{1,2}\b)?)"
    r"|(?P<y>\b(?:fiscal\s+)?year\s+(?:ended|ending)(?:\s+(?P<ym>" + _MONTHS + r"|dec)\.?\s+\d{1,2}\b)?)"
    r"|(?P<h>\bH(?P<ha>[12])(?:\s*['\u2019]?\s*(?P<hay>(?:20)?\d\d))?\b)"
    r"|(?P<n>\b9M(?:\s*(?P<nay>(?:20)?\d\d))?\b)"
    r"|(?P<t>\b(?:YTD|year[\s\-]+to[\s\-]+date)\b(?:\s*(?P<tay>20\d\d)\b)?)"
    r"|(?P<f>\b(?:FY|full[\s\-]+year|12M)\s*['\u2019]?(?P<fay>(?:20)?\d\d)?\b)"
    r"|(?P<yr>(?<![\d,.])20\d\d(?![\d,]|\.\d))"
    r"|(?P<c>%\s*(?:change|chg|var\w*)|\b(?:change|chg|var(?:iance)?|diff\w*)\b(?:\s*\(?%\)?)?|\+/-|(?<![(\w])%)"
    r"|(?P<fn>\(\d\)|\[\d\]|\b(?:" + _MONTHS + r"|sept?|dec|mar|jun)\.?\s+\d{1,2}\b(?!,?\s*20\d\d)|\.\s*\.)"
    r"|(?P<num>\d[\d,]*(?:\.\d+)?)")
_HC_MONTHQ = {"mar": 1, "march": 1, "jun": 2, "june": 2, "sep": 3, "sept": 3, "september": 3, "dec": 4, "december": 4}


def _y4(y):
    return None if not y else (y if len(y) == 4 else "20" + y)


def _header_toks(seg):
    """1.3.2: the period, year and change tokens of a flattened table header, from the start of the header to its first
    figure."""
    toks = []
    for m in _HC_TOK.finditer(seg):
        k = m.lastgroup
        g = m.groupdict()
        if g["num"] is not None:
            break                                   # the header ends at its first figure
        if g["fn"] is not None:
            continue
        if g["q"] is not None:
            qq = g["qa"] or g["qb"] or g["qc"] or g["qe"] or str(_ORD[g["qd"].lower()])
            yy = _y4(g["qay"] or g["qby"] or g["qcy"] or g["qdy"])
            toks.append(("Q", qq, yy))
        elif g["m"] is not None:
            toks.append(("M" + {"three": "3", "six": "6", "nine": "9", "twelve": "12"}.get(g["mn"].lower(), g["mn"]),
                         (g["mm"] or "").lower()[:3] or None, None))
        elif g["y"] is not None:
            toks.append(("M12", (g["ym"] or "").lower()[:3] or None, None))
        elif g["h"] is not None:
            toks.append(("H", g["ha"], _y4(g["hay"])))
        elif g["n"] is not None:
            toks.append(("9M", None, _y4(g["nay"])))
        elif g["t"] is not None or g["t0"] is not None:
            toks.append(("YTD", None, g["tay"] or g["t0y"]))
        elif g["f"] is not None:
            toks.append(("FY", None, _y4(g["fay"])))
        elif g["yr"] is not None:
            toks.append(("YR", None, m.group(0)))
        elif g["c"] is not None:
            if toks and toks[-1][0] == "C":
                continue                            # '% Change' is one column
            toks.append(("C", None, None))
    return toks


def _cols_from(toks, doc):
    """1.3.2: the column periods a header's tokens lay out (see _header_toks); None when they cannot be laid out."""
    if not toks:
        return None
    q_ = re.fullmatch(r"Q([1-4]) (20\d\d)", doc.get("quarter") or "")
    dqn = int(q_.group(1)) if q_ else None

    def per(t, y):
        kind, a, _y = t
        if not y:
            return None
        if kind == "Q":
            return "Q%s %s" % (a, y)
        if kind == "M3":
            qn = _HC_MONTHQ.get(a) if a else dqn
            return ("Q%d %s" % (qn, y)) if qn else None
        if kind == "M6":
            if a in ("jun", None) and (a or dqn == 2):
                return "H1 " + y
            if a in ("dec", None) and (a or dqn == 4):
                return "H2 " + y
            return None
        if kind == "M9":
            return ("9M " + y) if a in ("sep", None) else None
        if kind == "M12":
            return ("FY " + y) if a in ("dec", None) else None
        if kind == "H":
            return "H%s %s" % (a, y)
        if kind == "9M":
            return "9M " + y
        if kind == "YTD":
            return ({2: "H1 ", 3: "9M ", 4: "FY "}.get(dqn) or "") + y if dqn and dqn > 1 else None
        if kind == "FY":
            return "FY " + y
        return None

    absorbing = lambda t: t[0] in ("M3", "M6", "M9", "M12") or (t[0] in ("Q", "H", "9M", "YTD", "FY") and not t[2])
    cols, i = [], 0
    while i < len(toks):
        t = toks[i]
        if t[0] == "C":
            cols.append(None)
            i += 1
        elif t[0] == "YR":
            cols.append("FY " + t[2] if dqn in (None, 4) else None)     # 'Q4 2025 Q4 2024 2025 2024': the years
            i += 1
        elif not absorbing(t):
            cols.append(per(t, t[2]))
            i += 1
        else:
            labs = []
            while i < len(toks) and absorbing(toks[i]):
                labs.append(toks[i])
                i += 1
            slots = []
            while i < len(toks) and toks[i][0] in ("YR", "C"):
                slots.append(toks[i])
                i += 1
            if not slots or len(slots) % len(labs):
                return None
            w = len(slots) // len(labs)
            for j, sl in enumerate(slots):
                cols.append(None if sl[0] == "C" else per(labs[j // w], sl[2]))
    return cols if len(cols) >= 2 else None


def _wanted_cols(doc):
    """1.3.2: the columns of a table worth a row: the release's own quarter, its year to date (H1 / 9M / FY) and, in a
    fourth-quarter or year release, the year."""
    q = doc.get("quarter")
    m = re.fullmatch(r"Q([1-4]) (20\d\d)", q or "")
    if m:
        w = {q}
        if m.group(1) != "1":
            w.add({"2": "H1 ", "3": "9M ", "4": "FY "}[m.group(1)] + m.group(2))
        return w
    if doc.get("year") and not doc.get("fiscal_quarter"):
        return {"FY " + doc["year"]}
    return set()


_TCELL_RE = re.compile(r"\(?-?\$?\d[\d,]*(?:\.\d+)?\)?\s?%|\(?-?\$?\d[\d,]*(?:\.\d+)?\)?|\(?-?\$\s\d[\d,]*(?:\.\d+)?\)?%?|-|\u2014|\u2013|n/a|N/A|\bNM\b")


def _extra_cols(toks, cells, first, doc):
    """1.3.2: [(period, value)] for the wanted columns after the first, when the row's cells line up with the header. A
    title just before the header ('Second Quarter 2026 Highlights Three months ended ...') is not a column: the header
    is read from the first token that lays out as many columns as the row has cells, the first being the row's period."""
    cols = None
    for k in range(len(toks or ())):
        c_ = _cols_from(toks[k:], doc)
        if c_ and len(c_) == len(cells) and c_[0] == first:
            cols = c_
            break
    if not cols:
        return []
    want = _wanted_cols(doc)
    out, seen = [], {first}
    for per, c in zip(cols[1:], cells[1:]):
        if per in want and per not in seen and re.fullmatch(r"\d[\d,]*(?:\.\d+)?", c):
            seen.add(per)
            out.append((per, _num(c)))
    return out


_HDR_POS = [0]
_HDR_WORDS = {"metrics", "results", "highlights", "summary", "data", "operating", "operations", "operational", "performance",
              "production", "sales", "units", "key", "financial", "statistics", "table", "months", "ended", "quarter", "year"}


def _header_first(win):
    """The first column's period of the last header in the window before a table row, or None."""
    toks = list(_HQ.finditer(win))
    if not toks:
        return None
    # the last cluster of period tokens (a header), its first token
    cl = [toks[-1]]
    for t in reversed(toks[:-1]):
        if cl[0].start() - t.end() <= 80 and not re.search(r"\.\s+[A-Z]", win[t.end():cl[0].start()]):     # 1.3
            cl.insert(0, t)
        else:
            break
    t = cl[0]
    _HDR_POS[0] = t.start()
    if t.group(5) and re.match(r"-\s*20\d\d\b", win[t.end():t.end() + 7]):
        return "FY " + t.group(5)     # 1.3 (ARG)
    if re.search(r"(?i)\b(?:" + _MONTHS + r")\.?\s+\d{1,2}(?:,?\s*20\d\d)?\s*(?:-|\u2013|to|through)\s*(?:" + _MONTHS + r")\.?\s+\d{1,2}\b",
                 win[max(0, cl[0].start() - 120):]):
        return None      # 'May 1-June 30, 2025 (post-commercial production period)': a part of the quarter (1.1)
    g = t.groups()
    y = lambda v: v if v and len(v) == 4 else ("20" + v if v else None)
    if g[0]:
        return "Q%s %s" % (g[0], y(g[1]))
    if g[2]:
        return "Q%s %s" % (g[2], y(g[3]))
    if g[4]:
        return "Q%s %s" % (g[5], g[4])
    if g[6]:
        return "Q%d %s" % (_ORD[g[6].lower()], g[7])
    if re.match(r"(?i)(?:three|3)\s+months", t.group(0)):
        # 'Three months ended [Nine months ended ...] September 30, 2025': the first month and year after it
        after = win[t.start():t.start() + 220]
        mo = g[8] or (re.search(r"(?i)\b(mar|march|jun|june|sep|sept|september|dec|december)\b\.?\s+\d{1,2}", after) or [None, None])[1]
        q = _MONQ.get((mo or "").lower().rstrip("."))
        yy = g[9] or (re.search(r"20\d\d", after) or [None])[0]
        return ("Q%d %s" % (q, yy)) if q and yy else None
    if t.group(0).lower().startswith(("year", "twelve", "12 m")):
        yy = g[10] or (re.search(r"20\d\d", win[t.end():]) or [None])[0]
        return ("FY %s" % yy) if yy else None
    if g[11]:
        return "FY %s" % g[11]
    return None      # a half, a year-to-date or a six-month column comes first: not read


def _unit_of(ut, metal):
    """1.3.2: (multiplier, unit) of a table label's unit: '(k ozs)', "('000s ounces)", '(in thousands of ounces)' ->
    (1e3, 'oz'); '(thousand tonnes)', 'kt' -> (1e3, 't'); "000's pounds" -> (1e3, 'lb'); '(M lbs)' -> (1e6, 'lb')."""
    ut = (ut or "").lower()
    k_ = r"(?:\bk\s*-?\s*|\b000\s*['\u2019]?\s*s?\s*(?:of\s+)?|thousands?\s+(?:of\s+)?)"
    if re.search(k_ + r"(?:ounces?|ozs?)\b|\bkoz\b", ut):
        return 1e3, "oz"
    if re.search(r"\bmoz\b|millions?\s+(?:of\s+)?ounces", ut):
        return 1e6, "oz"
    if re.search(r"\bmlbs?\b|millions?\s+(?:of\s+)?(?:pounds|lbs)|\bm\s+lbs?\b", ut):
        return 1e6, "lb"
    if re.search(k_ + r"(?:pounds|lbs?)\b", ut):
        return 1e3, "lb"
    if re.search(k_ + r"(?:tonnes|t)\b|\bkt\b", ut):
        return 1e3, "t"
    if re.search(r"\bthousand|\b000s?\b", ut):
        return (1e3, "oz") if metal in ("gold", "silver", "AuEq", "AgEq", "GEO") else (1, None)
    if re.search(r"\bounces?\b|\bozs?\b", ut):
        return 1, "oz"
    if re.search(r"\btonnes\b|\bt\b", ut):
        return 1, "t"
    if re.search(r"\blbs?\b|pounds", ut):
        return 1, "lb"
    if metal in ("gold", "silver", "AuEq", "AgEq", "GEO"):
        return 1, "oz"
    return 1, None


def _table_rows(text, doc, multi, assets=()):
    """Rows read from production tables (1.1)."""
    t = " ".join(text.split())
    own = {doc.get("quarter"), doc.get("fiscal_quarter")} - {None}
    out = []
    for m in _TROW.finditer(t):
        if re.search(r"(?i)(?:per|/)\s*(?:ounce|oz|tonne|t|lb|pound)?\s*(?:of\s+)?$|\$\s*$|price\s*$|cost\s*(?:of\s+)?$|margin\s*$", t[max(0, m.start() - 30):m.start()]):
            continue      # 'Cost of sales per ounce of gold sold 1,754': a cost, not a quantity
        unit_txt = " ".join(x for x in (m.group("u1"), m.group("u2"), m.group("u3")) if x).lower()
        if re.search(r"\$|/|%|g/t|grade|price|cost|revenue|recover", unit_txt):
            continue
        rest = m.group("rest").split()
        first = t[m.start("v1") - 1:m.start("v1")]
        if first == "(" or (rest and rest[0].endswith("%") and len(rest) == 1):
            continue
        w0 = max(0, m.start() - 700)
        win = t[w0:m.start()]
        period = _header_first(win)
        if not period:
            continue
        hpos = w0 + _HDR_POS[0]
        if re.match(r"\s*(?:to|-|\u2013|\u2014)\s*\d", t[m.end("v1"):m.end("v1") + 12]) and \
                (_GT_HDR.search(t[hpos:m.start()]) or re.match(r"\s*to\s", t[m.end("v1"):])):
            continue      # 1.3.2: '2024 Guidance ... Copper production (tonnes) 59,000 - 72,000': a guidance range, not a cell
        ac = re.search(r"\b([A-Z][^\W\d_]+)\s+([A-Z][^\W\d_]+)\s+(?:Consolidated|Total)\b", t[hpos:m.start()])
        if ac and not {ac.group(1).lower(), ac.group(2).lower()} & _HDR_WORDS:
            continue      # 'Q2 2026 Production and Sales Galena Cosal\u00e1 Consolidated': the columns are mines (1.1)
        if period.startswith("FY "):
            # the year's own table: only in a release about that year
            if not (doc.get("year") == period[3:] and (doc.get("quarter") in (None, "Q4 " + period[3:]))):
                continue
        elif period not in own:
            continue
        # 1.2: a company-level summary table ('OPERATING RESULTS SUMMARY For three months ended ...', Allied Gold) whose
        # title and header name none of the release's mines is the company's
        summary = re.search(r"(?i)\b(?:operating|operational|production)\s+(?:results\s+)?(?:summary|highlights)\b|\bconsolidated\b",
                            t[max(0, hpos - 120):hpos]) and not any(re.search(r"(?i)\b" + re.escape(a_) + r"\b", t[max(0, hpos - 120):m.start()])
                                                                   for a_ in assets)
        if multi and not summary and not (m.group("pre") and m.group("pre").strip().lower() in ("total", "consolidated")) and \
                not re.search(r"(?i)\bconsolidated\b", t[max(0, m.start() - 60):m.start()]):
            continue      # multi-mine release: only a row the table itself calls consolidated or total is read
        metal = m.group("metal").lower()
        metal = {"gold equivalent": "AuEq", "silver equivalent": "AgEq", "ageq": "AgEq", "aueq": "AuEq", "geo": "GEO",
                 "geos": "GEO", "uranium": "U3O8", "u3o8": "U3O8"}.get(re.sub(r"\s+", " ", metal), metal)
        mult, unit = 1, None
        if re.search(r"\bk\s*-?\s*ozs?\b|000\s*oz|000'?s\s+oz|thousand", unit_txt):     # 1.3: '(k ozs)' (APM)
            mult, unit = 1e3, "oz"
        elif re.search(r"\bmlbs?\b|millions?\s+(?:of\s+)?(?:pounds|lbs)|\bm\s+lbs?\b", unit_txt):     # 1.3: '(millions of pounds)', '(M lbs)' (ARG)
            mult, unit = 1e6, "lb"
        elif re.search(r"000s?\s*lbs|000'?s\s+lbs", unit_txt):
            mult, unit = 1e3, "lb"
        elif re.search(r"\bounces?\b|\boz\b", unit_txt):
            unit = "oz"
        elif re.search(r"\btonnes\b|\bt\b", unit_txt):
            unit = "t"
        elif re.search(r"\blbs?\b|pounds", unit_txt):
            unit = "lb"
        elif metal in ("gold", "silver", "AuEq", "AgEq", "GEO"):
            unit = "oz"
        if not unit:
            continue
        v1 = m.group("v1")
        if re.match(r"(?i)\s*(?:t|tonnes|g/t|%)(?![\w/])", t[m.end("v1"):m.end("v1") + 8]):
            continue      # '500 oz GOLD PRODUCED 24,587 t MATERIAL PROCESSED': a label after its value, not a table row
        if re.fullmatch(r"\d", v1) and rest and re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", rest[0]):
            v1 = rest[0]      # '(Au, oz) 1 11,496': a footnote mark before the first cell
        v = _num(v1) * mult
        role = "sold" if m.group("role").lower() == "sold" else "recovered" if m.group("role").lower() == "recovered" else "produced"
        cells_ = [m.group("v1")] + _TCELL_RE.findall(m.group("rest"))
        if v1 != m.group("v1"):
            cells_ = cells_[1:]           # the footnote mark was not a cell
        hcols_ = _header_toks(t[hpos:m.start()])
        for per_, val_ in [(period, v)] + [(p_, x_ * mult) for p_, x_ in _extra_cols(hcols_, cells_, period, doc)]:   # 1.3.2
            out.append({"kind": "recovered" if role == "recovered" else "actual", "period": per_, "metal": metal, "qty": val_, "unit": unit, "role": role,
                        "approx": False, "_clause": "T%d" % m.start(), "_subject": None, "_mine": False, "_table": True,
                        "_total": bool(m.group("pre") and m.group("pre").strip().lower() in ("total", "consolidated")),
                        "_sum": bool(summary) or bool(re.search(r"(?i)\b(?:total|consolidated|group)\s*$", t[max(0, hpos - 25):hpos])) or
                                (t[hpos:m.start()].lower().rfind("consolidated") >= 0 and not any(
                                    a_ in t[hpos:m.start()].lower()[t[hpos:m.start()].lower().rfind("consolidated"):] for a_ in assets)),     # 1.3: a consolidated summary table's line (APM, SCZ); 'Total Q4 2017 Q3 2017 ...' (FM)
                        "_cells": [_num(x) * mult for x in rest if re.fullmatch(r"\d[\d,]*(?:\.\d+)?", x)]})
        # 1.2: 'Gold ounces Production 117,004 99,632 379,081 358,091 Sales(3) 113,446 64,769 418,168 313,455' (AAUC):
        # the sales line right under a production line, with as many cells, is the same metal's sold row
        sm = _TSALES.match(t, m.end())
        if role == "produced" and sm and len(sm.group("rest").split()) == len(rest):
            scells_ = [sm.group("v1")] + _TCELL_RE.findall(sm.group("rest"))
            for per_, val_ in [(period, _num(sm.group("v1")))] + _extra_cols(hcols_, scells_, period, doc):     # 1.3.2
                out.append({"kind": "actual", "period": per_, "metal": metal, "qty": val_ * mult, "unit": unit,
                            "role": "sold", "approx": False, "_clause": "T%d" % m.start(), "_subject": None, "_mine": False,
                            "_table": True, "_total": out[-1]["_total"], "_cells": []})
    # 'Williams ... Gold produced 24,635 Interlake ... Gold produced 10,129 ... Total gold produced 34,764': when the
    # table itself totals a metal a little further down, its first line of that metal is a section's (1.1)
    keep = []
    for r in out:
        p = int(r["_clause"][1:])
        if not r["_total"] and any(o["_total"] and o["metal"] == r["metal"] and o["role"] == r["role"] and o["period"] == r["period"]
                                   and 0 < int(o["_clause"][1:]) - p <= 800 for o in out):
            continue
        if not r["_total"] and not r.get("_sum") and any(o is not r and not o["_total"] and o["metal"] == r["metal"] and o["role"] == r["role"] and
                                   o["period"] == r["period"] and o["qty"] != r["qty"] and 120 <= abs(int(o["_clause"][1:]) - p) <= 800
                                   for o in out):
            continue      # 1.3 (ARG)
        keep.append(r)
    for r in keep:
        r.pop("_total")
        r.pop("_sum", None)
    return keep


_MCOL_HDR = re.compile(r"\b((?:(?:Au|Ag|Cu|AuEq|Gold|Silver|Copper)\s+(?:\d\s+)?){2,4})")
_MCOL_ROW = re.compile(r"(?i)\b(Produced\s*\((?:after|before)\s+payable\s+deductions\)|Payable\s+(?:production|produced)|"
                       r"Sold(?:\s*\((?:after|before)\s+payable\s+deductions\))?)\s+"
                       r"((?:(?:\d[\d,]*(?:\.\d+)?\s*(?:oz|koz|mlbs?|lbs?|t)\b|-|\u2014)\s*){2,4})")
_MCOL_METAL = {"au": "gold", "gold": "gold", "ag": "silver", "silver": "silver", "cu": "copper", "copper": "copper",
               "aueq": "AuEq"}


def _metal_col_rows(text, doc):
    """'Au Ag Cu AuEq ... Produced (after payable deductions) 95,058 oz 485.2 koz 14.0 mlb 119,034 oz': a table
    whose columns are metals, each cell with its unit, under a title naming the release's own quarter (1.1)."""
    t = " ".join(text.split())
    own = {doc.get("quarter"), doc.get("fiscal_quarter")} - {None}
    out = []
    for h in _MCOL_HDR.finditer(t):
        metals = [_MCOL_METAL.get(w.lower()) for w in h.group(1).split() if not w.isdigit()]
        if None in metals or len(set(metals)) != len(metals):
            continue
        title = t[max(0, h.start() - 700):h.start()]
        ps = [(_resolve(k, g, doc)) for s_, e, k, g in _periods(title) if k in ("q", "q2", "fq")]
        if not ps or ps[0] not in own:
            continue
        found = list(_MCOL_ROW.finditer(t, h.end(), min(len(t), h.end() + 1500)))
        # 1.2: Torex's Q1 2026 table states production only before payable deductions ('Produced (before payable
        # deductions) 73,647 oz 543.0 koz 14.9 mlb 100,874 oz'), and that is the figure it calls production; where a
        # table gives both, the payable one is read (Justin's rule 3)
        payable = any(re.search(r"(?i)after|payable\s+(?:production|produced)", r.group(1)) and not r.group(1).lower().startswith("sold")
                      for r in found)
        for r in found:
            if payable and re.search(r"(?i)before", r.group(1)):
                continue
            cells = re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*(oz|koz|mlbs?|lbs?|t)\b|(-|\u2014)", r.group(2))
            if len(cells) != len(metals):
                continue
            role = "sold" if r.group(1).lower().startswith("sold") else "produced"
            for metal, (num, unit, dash) in zip(metals, cells):
                if dash:
                    continue
                v = _num(num)
                u = unit.lower()
                if u == "koz":
                    v, u = v * 1e3, "oz"
                elif u.startswith("mlb"):
                    v, u = v * 1e6, "lb"
                elif u.startswith("lb"):
                    u = "lb"
                out.append({"kind": "actual", "period": ps[0], "metal": metal, "qty": v, "unit": u, "role": role,
                            "approx": False, "_clause": "M%d" % h.start(), "_subject": None, "_mine": False, "_table": True})
        if out:
            break
    return out


_PCOL = re.compile(r"(?i)(?P<pre>[^|.]{0,40}?)\bProduction\s*\((?P<u>thousand\s+tonnes|tonnes|000\s*t|kt|thousand\s+ounces|koz|000\s*oz|"
                   r"million\s+ounces|moz|million\s+pounds|mlbs?|ounces|oz|pounds|lbs)\)\s+"
                   r"(?P<h>(?:(?:Q[1-4]\s+20\d\d|FY\s*20\d\d)\s+){1,4})"
                   r"(?P<rows>(?:(?:Gold|Silver|Zinc|Lead|Copper|Nickel|Cobalt)\s+(?:\d[\d,]*(?:\.\d+)?|\u2014|-)(?:\s+(?:\d[\d,]*(?:\.\d+)?|\u2014|-)){0,3}\s+){1,7})")
_PCOL_UNIT = {"thousand tonnes": ("t", 1e3), "000 t": ("t", 1e3), "000t": ("t", 1e3), "kt": ("t", 1e3), "tonnes": ("t", 1),
              "thousand ounces": ("oz", 1e3), "koz": ("oz", 1e3), "000 oz": ("oz", 1e3), "000oz": ("oz", 1e3),
              "million ounces": ("oz", 1e6), "moz": ("oz", 1e6), "million pounds": ("lb", 1e6), "mlb": ("lb", 1e6),
              "mlbs": ("lb", 1e6), "ounces": ("oz", 1), "oz": ("oz", 1), "pounds": ("lb", 1), "lbs": ("lb", 1)}


def _period_col_rows(text, doc, multi):
    """1.2: 'Attributable Base Metal Production (thousand tonnes) Q4 2025 FY 2025 Zinc 16.8 55.9 Lead 8.2 27.0 Copper
    0.8 3.0' (PAAS): a table titled with its unit, headed by periods, one row per metal. Only the release's own quarter
    and, in a release about the year's last quarter or the year, the year; in a multi-mine release only a table its
    title calls attributable, consolidated or total."""
    t = " ".join(text.split())
    own = {doc.get("quarter"), doc.get("fiscal_quarter")} - {None}
    y = doc.get("year")
    out = []
    for m in _PCOL.finditer(t):
        if multi and not re.search(r"(?i)\b(?:attributable|consolidated|total)\b", m.group("pre")):
            continue
        unit, mult = _PCOL_UNIT.get(re.sub(r"\s+", " ", m.group("u").lower()), (None, 1))
        if not unit:
            continue
        hdr = [re.sub(r"\s+", " ", h).replace("FY", "FY ").replace("FY  ", "FY ") for h in
               re.findall(r"(?i)Q[1-4]\s+20\d\d|FY\s*20\d\d", m.group("h"))]
        hdr = [("FY " + h[-4:]) if h.upper().startswith("FY") else ("Q%s %s" % (h[1], h[-4:])) for h in hdr]
        for rm in re.finditer(r"(?i)(Gold|Silver|Zinc|Lead|Copper|Nickel|Cobalt)((?:\s+(?:\d[\d,]*(?:\.\d+)?|\u2014|-)){1,4})", m.group("rows")):
            cells = rm.group(2).split()
            if len(cells) != len(hdr):
                continue
            metal = rm.group(1).lower()
            if not _unit_fits(metal, unit):
                continue
            for per, c in zip(hdr, cells):
                if not re.match(r"\d", c):
                    continue
                if per not in own and not (per == "FY " + str(y) and doc.get("quarter") in (None, "Q4 %s" % y)):
                    continue
                out.append({"kind": "actual", "period": per, "metal": metal, "qty": _num(c) * mult, "unit": unit,
                            "role": "produced", "approx": False, "_clause": "C%d" % m.start(), "_subject": None,
                            "_mine": False, "_table": True})
    return out


_GA_HDR = re.compile(r"(?i)\b(20\d\d)\s+(?:revised\s+|updated\s+|original\s+)?guidance\s+(20\d\d)\s+actual(?:\s+(payable|production|produced))?")
_GA_ROW = re.compile(r"\b(Gold|Silver|Lead|Zinc|Copper)\s+" + _NUM + r"\s*[\u2013\u2014-]\s*" + _NUM + r"\s+" + _NUM + r"(?![\d,])")


def _guide_actual_rows(text, doc, multi, headline=""):
    """'Mine Metal 2025 Revised Guidance 2025 Actual Payable ... Consolidated Gold 21,000 \u2013 24,000 21,456': a year's
    guidance-against-actual table; the consolidated block only, when the release has several mines (1.1)."""
    t = " ".join(text.split())
    out = []
    tonnes = bool(re.search(r"(?i)\btonnes\b", t)) and not re.search(r"(?i)\bpounds\b|\blbs?\b", t)
    for h in _GA_HDR.finditer(t):
        y = h.group(2)
        annual = re.search(r"(?i)(?:full[\s\-]*year|annual|year[\s\-]*end|\bFY)\s*" + y, headline or "")
        if h.group(1) != y or doc.get("year") != y or (doc.get("quarter") not in (None, "Q4 " + y) and not annual):
            continue
        nxt = _GA_HDR.search(t, h.end())
        sec = t[h.end():min(nxt.start() if nxt else len(t), h.end() + 1500)]
        c = re.search(r"\b(?:Consolidated|Total)\b", sec)
        if multi or c:
            if not c:
                continue
            sec = sec[c.end():c.end() + 260]
        for m in _GA_ROW.finditer(sec):
            metal = m.group(1).lower()
            unit = "oz" if metal in ("gold", "silver") else ("t" if tonnes else None)
            if not unit:
                continue
            low, high, act = _num(m.group(2)), _num(m.group(3)), _num(m.group(4))
            if not (0.5 <= act / max(high, 1) <= 2):
                continue
            out.append({"kind": "actual", "period": "FY " + y, "metal": metal, "qty": act, "unit": unit,
                        "role": "produced", "approx": False, "_clause": "G%d" % h.start(), "_subject": None,
                        "_mine": False, "_table": True})
            out.append({"kind": "guidance", "period": "FY " + y, "metal": metal, "low": low, "high": high, "unit": unit,
                        "_table": True})
        if out:
            break
    return out


# 1.3.2: a guidance table - '2024 Guidance Copper production (tonnes) 59,000 - 72,000 Gold production (ounces) 55,000 -
# 60,000', 'Guidance 2022 2023 2024 Copper (000 t) 258 - 282 250 - 274 262 - 286': a metal's label with its unit, then
# one low-high range per year the header names
_GT_HDR = re.compile(r"(?i)(?:\b|(?<=FY))(?:(?P<y1>20\d\d)\s*(?:(?:production|operating|operational|annual|full[\s\-]+year|consolidated|updated|revised)\s+){0,2}"
                     r"\(?(?:guidance|outlook|forecast)\)?|(?:guidance|outlook)\s*(?:for\s+)?\(?(?P<y2>20\d\d)\)?)\b")
_GT_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_GT_RANGE = _GT_NUM + r"\s*(?:-|\u2013|\u2014|to)\s*" + _GT_NUM + r"(?![\d,]|\.\d|\s*%)"
_GT_ROW = re.compile(r"(?i)(?<![\w/$])(?P<pre>(?:Total|Consolidated|Attributable|Payable)\s+)?(?P<metal>Gold\s+equivalent|Silver\s+equivalent|Gold|Silver|"
                     r"Copper|Zinc|Lead|Nickel|Cobalt|Uranium|U3O8|GEOs?|AuEq|AgEq)(?:\s+(?:ounces|oz))?"
                     r"(?:\s+(?:production|produced|payable\s+production))?\s*(?:\((?P<u>[^()]{1,25})\))?"
                     r"(?:\s+(?P<u3>koz|Moz|oz|ounces|tonnes|kt|lbs|M\s?lbs?|pounds|000\s*oz|000\s*t|000\s*lbs)\b\.?)?\s+"
                     r"(?P<vals>(?:" + _GT_NUM + r"\s+(?![\-\u2013\u2014]|to\b)){0,4})"     # 1.3.2: actual columns before the guidance range
                     r"(?P<ranges>" + _GT_RANGE + r"(?:\s+" + _GT_RANGE + r"){0,3})")


def _guide_table_rows(text, doc, multi):
    t = " ".join(text.split())
    out = []
    for h in _GT_HDR.finditer(t):
        nxt = _GT_HDR.search(t, h.end())
        end = min(nxt.start() if nxt else len(t), h.end() + 900)
        found_ = list(_GT_ROW.finditer(t, h.end(), end))
        mets_ = [re.sub(r"\s+", " ", m.group("metal").lower()) for m in found_]
        marks_ = [x.start() for x in re.finditer(r"(?i)\b(?:total|consolidated)\b", t[h.end():end])]
        tot_ = []
        for k_, m in enumerate(found_):
            mk_ = [h.end() + x for x in marks_ if h.end() + x <= m.start()]
            # the line follows a 'Total' / 'Consolidated' marker with no other line of its metal in between
            if m.group("pre") or (mk_ and not any(mk_[-1] <= o.start() < m.start() and mets_[j_] == mets_[k_]
                                                  for j_, o in enumerate(found_) if o is not m)):
                tot_.append(m)
        for m in found_:
            mt_ = re.sub(r"\s+", " ", m.group("metal").lower())
            if mets_.count(mt_) > 1 and m not in tot_:
                continue      # 1.3.2: a metal the table states for each mine and for the total: only the total's line
            gap = t[h.end():m.start()]
            if re.search(r"(?i)\bactual\b|\b(?:cash\s+costs?|AISC|grade|recover\w*|price)\s*$", gap) or \
                    re.search(r"\d[\d,.]*\s*(?:-|\u2013|to)\s*\d", re.sub(r"\b20\d\d\b", " ", gap[:max(0, len(gap) - 0)])) and False:
                continue
            if re.search(r"\d[\d,]{2,}(?![\d%])", re.sub(r"(?<!\d)20\d\d(?!\d)", " ", gap)) and not _GT_ROW.search(gap):
                continue      # a figure between the heading and the row: prose, not the heading's table
            if multi and m not in tot_:
                continue      # a multi-mine release: only the total
            ut = " ".join(x for x in (m.group("u"), m.group("u3")) if x).lower()
            if re.search(r"\$|/|%|g/t|grade|price|cost", ut):
                continue
            metal = re.sub(r"\s+", " ", m.group("metal").lower())
            metal = {"gold equivalent": "AuEq", "silver equivalent": "AgEq", "ageq": "AgEq", "aueq": "AuEq", "geo": "GEO",
                     "geos": "GEO", "uranium": "U3O8", "u3o8": "U3O8"}.get(metal, metal)
            mult, unit = _unit_of(ut, metal)
            if not unit or not _unit_fits(metal, unit):
                continue
            rngs = re.findall(_GT_RANGE, m.group("ranges"))
            hy = h.group("y1") or h.group("y2")
            ys = list(dict.fromkeys(re.findall(r"\b20\d\d\b", t[h.start():m.start()])))
            if len(rngs) == 1:
                ys = [hy]
            elif len(ys) != len(rngs) or m.group("vals").strip():
                continue
            for y, (lo, hi) in zip(ys, rngs):
                lo, hi = _num(lo) * mult, _num(hi) * mult
                if not lo < hi:
                    continue
                out.append({"kind": "guidance", "period": "FY " + y, "metal": metal, "low": lo, "high": hi, "unit": unit,
                            "_table": True})
        if out:
            break
    return out


def _table_aisc(text, doc, multi):
    """{period: AISC per ounce} from an AISC table row, first column, header-checked like _table_rows (1.1)."""
    t = " ".join(text.split())
    own = {doc.get("quarter"), doc.get("fiscal_quarter")} - {None}
    res = {}
    for m in _TAISC.finditer(t):
        if re.search(r"(?i)margin|guidance|\bYTD\b", t[max(0, m.start() - 40):m.end()]):
            continue
        w0 = max(0, m.start() - 1200)
        period = _header_first(t[w0:m.start()])
        if not period or (period not in own and not (period.startswith("FY ") and doc.get("year") == period[3:]
                                                      and doc.get("quarter") in (None, "Q4 " + period[3:]))):
            continue
        if multi and not re.search(r"(?i)\bconsolidated\b", t[max(0, m.start() - 600):m.start()]):
            continue
        if re.match(r"\s*(?:to|-|\u2013|\u2014)\s*\$?\d", t[m.end("v1"):m.end("v1") + 12]) and \
                _GT_HDR.search(t[w0 + _HDR_POS[0]:m.start()]):
            continue      # 1.3.2: an AISC guidance range under a guidance heading
        v = _num(m.group("v1"))
        if 400 <= v <= 6000:
            res.setdefault(period, v)
            # 1.3.2: the year-to-date (or year) column of the same row
            cells_ = [m.group("v1")] + [c.lstrip("$") for c in _TCELL_RE.findall(m.group("rest"))]
            for per_, x_ in _extra_cols(_header_toks(t[w0 + _HDR_POS[0]:m.start()]), cells_, period, doc):
                if 400 <= x_ <= 6000:
                    res.setdefault(per_, x_)
    return res


_AISC_PROSE = re.compile(r"(?i)(?:\bAISC\b|all[\s\-]+in[\s\-]+sustaining\s+costs?)(?:\s*\(\W*AISC\W*\))?(?:\s*[\d\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079](?=\s))?"
                         r"[^.$;]{0,50}?(?:US|C|CA)?\$\s?(?P<v>\d[\d,]*(?:\.\d+)?)\s*(?:per|/)\s*(?:gold\s+|silver\s+|AuEq\s+|AgEq\s+)?(?:ounce|oz)\b"
                         r"(?:\s+(?:of\s+)?(?P<mt>gold|silver|AuEq|AgEq|GEO))?")
# 1.2: the unit in the label, the figure after the verb: 'AISC per ounce of gold sold1 was $1,685' (Mineros)
_AISC_PROSE2 = re.compile(r"(?i)(?:\bAISC\b|all[\s\-]+in[\s\-]+sustaining\s+costs?)(?:\s*\(\W*AISC\W*\))?\s*[\d\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079]?\s*"
                          r"per\s+(?:gold\s+|silver\s+)?(?:ounce|oz)(?:\s+of\s+(?P<mt>gold|silver))?(?:\s+sold)?\s*[\d\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079]?\s+"
                          r"(?:was|were|of|totall?ed|amounted\s+to)\s+(?:US|C|CA)?\$\s?(?P<v>\d[\d,]*(?:\.\d+)?)(?![\d,])(?!\s*(?:to|-|\u2013))")


def _prose_aisc(text, doc, multi, assets):
    """{(period, 'gold'|'silver'): AISC} from sentences in the opening of the release (1.1)."""
    res = {}
    head = text[:6000]
    hcls = _clauses(head)
    for hi, cl in enumerate(hcls):
        hprev = hcls[hi - 1][-300:] if hi else ""
        for m in sorted(list(_AISC_PROSE.finditer(cl)) + list(_AISC_PROSE2.finditer(cl)), key=lambda x: x.start()):
            pre = cl[max(0, m.start() - 80):m.start()]
            if re.search(r"(?i)cash\s+costs?\s+and\s+$", pre):
                continue      # 'Total cash costs and AISC were $1,135 per ounce and $1,394 per ounce': the first is cash cost

            seg = cl[m.start():m.end()]
            if re.search(r"(?i)\b(?:with|includ\w*|related|associated|of\s+this|of\s+which|excluding)\b|^\S*\s*,", seg[len(re.match(r"(?i)\S+(?:\s+\S+){0,3}?", seg).group(0)):seg.find("$")] if "$" in seg else "") or \
                    re.search(r"(?i)guidance|between|range|expect|forecast|outlook|target|YTD|year[\s\-]+to[\s\-]+date|"
                         r"six\s+months|nine\s+months|full[\s\-]+year|annual|\bH[12]\b|half|margin|price|realized|royalt|revenue|post[\s\-]*commercial", pre + seg) or \
                    re.search(r"\$\s?[\d,.]+\s*(?:to|-|\u2013)\s*\$?\s?[\d,.]+", seg):
                continue
            if multi and (_asset_context(pre, assets) or any(a in pre.lower() for a in assets)) and \
                    not re.search(r"(?i)consolidated|corporate|company|total", pre + seg):
                continue
            if re.search(r"(?i)\b(?:versus|vs\.?|compared\s+(?:to|with))\s", pre[-60:]):
                continue                                    # the comparative figure of "X versus AISC of $Y"
            pcl = _periods(cl)
            per = [(s_, e, k, g) for s_, e, k, g in pcl if e <= m.start() and k != "span"]
            if not per and re.search(r"(?i)\b(?:six|nine|6|9)\s+months\s+ended|first\s+half", hprev) and \
                    not re.search(r"(?i)\bthree\s+(?:and\s+(?:six|nine)\s+)?months|quarter|\bQ[1-4]\b", hprev):
                continue      # under a 'Six months ended June 30' heading
            period = _resolve(per[-1][2], per[-1][3], doc) if per else (doc.get("quarter") if cl is not None else None)
            if not period:
                continue
            lead = re.match(r"(?i)\s*(?:sold\s+)?(?:for|in|during)\s+(?:the\s+)?", cl[m.end():])
            aft = [(k, g) for s_, e, k, g in pcl if lead and s_ == m.end() + lead.end()]
            if aft and (aft[0][0] == "span" or _resolve(aft[0][0], aft[0][1], doc) not in (None, period)):
                continue                                    # "AISC of $1,936/oz for Q1 2024" in a Q1 2025 release
            metal = "silver" if re.search(r"(?i)silver|AgEq", (m.group("mt") or "") + cl[m.end():m.end() + 30] + seg) else "gold"
            v = _num(m.group("v"))
            if (400 <= v <= 6000) if metal == "gold" else (5 <= v <= 100):
                res.setdefault((period, metal), v)
    return res


_LC_LINE = re.compile(r"(?i)(?<![\w])(?P<metal>Gold\s+Equiv(?:alent|\.)?|Silver\s+Equiv(?:alent|\.)?|Gold|Silver|Copper)\s+"
                      r"(?P<role>Recovered|Sold)(?:\s*\(\d\))?\s+(?P<u>oz|ounces|lbs?|t|tonnes)\s+"
                      r"(?P<cells>(?:\d[\d,]*(?:\.\d+)?(?:\s+|$)){2,8})")
_LC_HDR = re.compile(r"\b(?:Units\s+)?((?:Q[1-4]\s+20\d\d\s+){2,7}Q[1-4]\s+20\d\d)\b")


def _last_col_recovered(text, doc, multi):
    """1.3: 'Units Q1 2025 Q2 2025 Q3 2025 Q4 2025 ... Gold Recovered oz 10,436 8,961 6,879 9,621 ... Gold Sold oz 9,881
    10,104 6,918 9,307' (Mako): a table whose header runs the quarters up to the release's own, read in its LAST
    column, for recovered and sold lines only. Not in a multi-mine release."""
    own = doc.get("quarter")
    if not own or multi:
        return []
    t = " ".join(text.split())
    out = []
    for h in _LC_HDR.finditer(t):
        hdr = re.findall(r"Q[1-4]\s+20\d\d", h.group(1))
        if re.sub(r"\s+", " ", hdr[-1]) != own:
            continue
        for m in _LC_LINE.finditer(t, h.end(), min(len(t), h.end() + 2500)):
            cells = m.group("cells").split()
            if len(cells) != len(hdr):
                continue
            metal = m.group("metal").lower()
            metal = "AuEq" if metal.startswith("gold equiv") else "AgEq" if metal.startswith("silver equiv") else metal
            u = m.group("u").lower()
            unit = "oz" if u in ("oz", "ounces") else "lb" if u.startswith("lb") else "t"
            role = m.group("role").lower()
            out.append({"kind": "recovered" if role == "recovered" else "actual", "period": own, "metal": metal,
                        "qty": _num(cells[-1]), "unit": unit, "role": role, "approx": False, "_clause": "L%d" % h.start(),
                        "_subject": None, "_mine": False, "_table": True})
        if out:
            break
    return out


def _pend(p):
    """1.3.2: a calendar period's end as (year, month): 'Q3 2025' -> (2025, 9), 'H1 2025' -> (2025, 6), '9M 2025' -> (2025, 9),
    'FY 2025' -> (2025, 12), '2025-03' -> (2025, 3); a fiscal period ('Q1 FY2026') -> None."""
    p = p or ""
    m = re.fullmatch(r"Q([1-4]) (20\d\d)", p)
    if m:
        return int(m.group(2)), 3 * int(m.group(1))
    m = re.fullmatch(r"(H[12]|9M|FY) (20\d\d)", p)
    if m:
        return int(m.group(2)), {"H1": 6, "H2": 12, "9M": 9, "FY": 12}[m.group(1)]
    m = re.fullmatch(r"(20\d\d)-(\d\d)", p)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _fold_ended_guidance(rows, doc):
    """1.3.2 (Justin's decision 9): guidance for a period the release's own quarter shows has ended ('2025 guidance of
    14.8 - 15.8 Moz' in a Q4 2025 release) is what the period was measured against: it goes on that period's actual row
    as guided_low / guided_high (when the two agree in size), never as a guidance row. With no quarter of its own, a
    release's guidance is folded only onto an actual for the same period and metal."""
    dq = _pend(doc.get("quarter")) if doc.get("quarter") else None
    act = {(r["period"], r["metal"]): r for r in rows if r.get("kind") == "actual" and r.get("qty")}
    out = []
    for r in rows:
        if r.get("kind") == "guidance":
            pe = _pend(r.get("period"))
            a = act.get((r.get("period"), r.get("metal")))
            vals = [v for v in (r.get("low"), r.get("high")) if v is not None]
            mid = sum(vals) / len(vals) if vals else None
            fits = bool(a and mid and 0.67 <= a["qty"] / mid <= 1.5)
            ended = bool(pe and dq and pe <= dq) or (not dq and not doc.get("fiscal_quarter") and fits)
            if ended and fits:
                if a.get("guided_low") is None and a.get("guided_high") is None:
                    a["guided_low"], a["guided_high"] = r.get("low"), r.get("high")
                continue
        out.append(r)
    return out


def _annual(r):
    p = r.get("period") or ""
    return 4 if p.startswith("Q") else 2 if p.startswith("H") else 4 / 3 if p.startswith("9M") else 12 if re.match(r"20\d\d-\d\d", p) else 1


def _ended(r, doc):
    """False when the release's own quarter shows the row's period had not ended (the publisher drops such a row)."""
    q = re.fullmatch(r"Q([1-4]) (20\d\d)", doc.get("quarter") or "")
    p = r.get("period") or ""
    if not q:
        return True
    dq, dy = int(q.group(1)), q.group(2)
    if p == "FY " + dy:
        return dq == 4
    if p == "H2 " + dy:
        return dq == 4
    if p == "9M " + dy:
        return dq >= 3      # 1.3
    if p == "H1 " + dy:
        return dq >= 2
    m = re.fullmatch(r"Q([1-4]) " + dy, p)
    return not m or int(m.group(1)) <= dq


def _scale_check(rows, doc=None):
    """One company's figures agree in size (1.1). A guidance range under a fifth of what the company's own actuals
    say it produces in a year is an asset's; so is a quarter under a tenth of the same year's total, and a quarter
    larger than its year says one of the two is not the company's."""
    act = [r for r in rows if r["kind"] == "actual" and r.get("qty") and _ended(r, doc or {})]
    scale = {}
    for r in act:
        scale[r["metal"]] = max(scale.get(r["metal"], 0), r["qty"] * _annual(r))
    fy = {(r["metal"], r["period"][-4:]): r["qty"] for r in act if (r.get("period") or "").startswith("FY ")}
    # 1.3: a year smaller than its own half or nine months is not the company's year (DPM: Ada Tepe's 5,351 oz read as FY
    # 2019 beside H1 95,459); it gives way, and the quarters are measured against nothing
    bad_fy = {k for k, v in fy.items() if any(re.match(r"(?:H[12]|9M) ", a.get("period") or "") and a["metal"] == k[0]
                                              and a["period"][-4:] == k[1] and a["qty"] > 1.02 * v for a in act)}
    for k in bad_fy:
        fy.pop(k, None)
    out = []
    for r in rows:
        if r["kind"] == "guidance" and scale.get(r["metal"]):
            g = max(v for v in (r.get("low"), r.get("high")) if v is not None) * _annual(r)
            if g < 0.2 * scale[r["metal"]]:
                continue
        if r["kind"] == "actual" and (r.get("period") or "").startswith("Q") and r.get("qty"):
            t = fy.get((r["metal"], r["period"][-4:]))
            if t and (r["qty"] < 0.1 * t or r["qty"] > 1.02 * t):
                continue
        if r["kind"] == "actual" and re.match(r"(?:H[12]|9M) ", r.get("period") or "") and r.get("qty"):
            # 1.3: a half or nine months smaller than one of its own quarters is some other figure (a mine's)
            inside = {"H1": "12", "H2": "34", "9M": "123"}[r["period"][:2]]
            qs = [a["qty"] for a in act if re.fullmatch(r"Q[" + inside + r"] 20\d\d", a.get("period") or "") and a["metal"] == r["metal"]
                  and a["period"][-4:] == r["period"][-4:]]
            if qs and max(qs) > 1.02 * r["qty"]:
                continue
            last = [a["qty"] for a in act if a["metal"] == r["metal"] and a.get("qty") and
                    a.get("period") == {"H1": "Q2 ", "H2": "Q4 ", "9M": "Q3 "}[r["period"][:2]] + r["period"][-4:]]
            if last and r["qty"] < {"H1": 1.15, "H2": 1.15, "9M": 1.5}[r["period"][:2]] * last[0]:
                continue      # 1.3
        if r["kind"] == "actual" and (r.get("period") or "").startswith("FY ") and (r["metal"], r["period"][-4:]) in bad_fy:
            continue      # 1.3
        if r["kind"] == "actual" and (r.get("period") or "").startswith("FY ") and r.get("qty"):
            qs = [a["qty"] for a in act if (a.get("period") or "").startswith("Q") and a["metal"] == r["metal"]
                  and a["period"][-4:] == r["period"][-4:]]
            if qs and (max(qs) > 1.02 * r["qty"] or any(abs(q - r["qty"]) <= 0.01 * r["qty"] for q in qs)):
                continue
        out.append(r)
    return out


def _tpos(r):
    c = str(r.get("_clause") or "")
    return int(c[1:]) if re.fullmatch(r"T\d+", c) else None


def _table_mismatch(prods, s, a):
    """A table's sold figure belongs to the production row just above it in that table: when that production is not
    the row the sold figure would join, the table is about something else (a mine's section) (1.1)."""
    sp = _tpos(s)
    above = [(_tpos(p), p["qty"]) for p in prods if _tpos(p) is not None and sp is not None and _tpos(p) < sp]
    return bool(above) and abs(max(above)[1] - a["qty"]) > 0.1 * a["qty"]


def _consolidate(rows, doc_metal=None, multi=False, doc=None, royalty=False, extra_named=()):
    """One row per (kind, period, metal): the first statement wins (headline and highlights come first),
    a sold figure joins its produced row, and a royalty company's GEOs sold stand in for production."""
    # a figure whose metal the clause never named takes the release's only metal in that unit
    named = {(r["unit"], r["metal"]) for r in rows if r["kind"] == "actual" and r.get("metal")} | set(extra_named)
    for r in rows:
        if r["kind"] in ("actual", "guidance", "recovered") and not r.get("metal"):
            ms = {m for u, m in named if u == r["unit"]}
            r["metal"] = ms.pop() if len(ms) == 1 else (doc_metal if r["unit"] == "oz" else None)
    rows = [r for r in rows if r.get("metal") and _unit_fits(r["metal"], r["unit"]) and _plausible(r)]
    # in a multi-mine release, a figure a named mine produced is that mine's, never the company's (1.1)
    pool_ = rows
    rows = [r for r in rows if not r.get("_asset_row")]
    def _other_(o, r):
        oid = o.get("_named") or o.get("_subject") or ""
        return not (oid and (oid in r["_named"] or r["_named"] in oid))
    rows = [r for r in rows if not r.get("_named") or not (royalty or r.get("metal") == "GEO" or any(
        o is not r and o["kind"] in ("actual", "recovered") and o.get("role") != "sold" and o.get("metal") == r.get("metal") and
        _other_(o, r) for o in pool_))]     # 1.3: a royalty company's production is never one asset's (TFPM's Renard)
    # a royalty company reporting GEOs quotes its partners' mines in ounces: those are not its production (1.1: also
    # when the release says it is a royalty or streaming company and states no GEO figure of its own)
    if any(r.get("metal") == "GEO" for r in pool_) or royalty:     # 1.3: before the named-asset filter
        rows = [r for r in rows if r["kind"] not in ("actual", "recovered") or r["metal"] in ("GEO", "AuEq") or (r.get("_brk") and not royalty)]
    out, seen = [], {}
    sold, tprod = {}, {}
    for r in rows:
        if r["kind"] == "actual" and r.get("_table") and r.get("role") == "produced":
            tprod.setdefault((r["period"], r["metal"]), []).append(r)
        if r["kind"] == "actual" and r.get("role") == "sold":
            sold.setdefault((r["period"], r["metal"], r.get("_clause")), r)
            continue
        key = (r["kind"], r["period"], r["metal"])
        if key in seen:
            old = seen[key]
            # two actuals for one metal and period: a named mine's gives way to the company's ('the La Colorada
            # mine produced 58,288' vs Heliostar's 79,710); otherwise the first statement stands
            if r["kind"] == "actual" and old.get("_doc") and r.get("_table") and r.get("role") == "produced" and \
                    old.get("qty") in r.get("_cells", ()):
                # 'Gold production was 12,027 ounces' dated only by the release's quarter, while the table puts 12,027
                # in its six-month column and 6,751 in the quarter's: the table's figure stands (1.1)
                out[out.index(old)] = r
                seen[key] = r
                continue
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
        if key not in seen and ("recovered", period, metal) in seen:
            key = ("recovered", period, metal)     # 1.3: no produced figure; the sold figure goes on the recovered row
        if key in seen and seen[key].get("_clause") == ci:
            seen[key].setdefault("sold", s["qty"])
    # 1.2: a sold figure from a revenue sentence joins last, so a table's own sold line for the same production row
    # wins ('Revenue for the six months ... 71,110 gold ounces sold' is the total; the table's attributable line is
    # 59,910, HMMC)
    for (period, metal, ci), s in sorted(sold.items(), key=lambda kv: bool(kv[1].get("_rev"))):
        key = ("actual", period, metal)
        if key not in seen and ("recovered", period, metal) in seen:
            key = ("recovered", period, metal)     # 1.3
        a = seen.get(key)
        if a is not None:
            # 1.1: a sold figure stated elsewhere in the release for the same period and metal ('A total of 11,960
            # gold ounces ... were sold in Q2'), when it is of the same size as the production; a table's sold figure only
            # when that table's own production for the period is this row's (Wesdome's Eagle River table, 27,500)
            if a.get("sold") is None and a.get("qty") and not s.get("_tabular") and 0.5 <= s["qty"] / a["qty"] <= 2 and \
                    not (s.get("_table") and _table_mismatch(tprod.get((period, metal), []), s, a)):
                a["sold"] = s["qty"]
        elif metal == "GEO":
            row = {"kind": "actual", "period": period, "metal": "GEO", "qty": s["qty"], "unit": "oz",
                   "basis": "sold", "role": "produced"}
            seen[key] = row
            out.append(row)
    # a release naming two or more producing assets is a multi-mine company's: an asset's figure is not the total
    subjects = {r.get("_subject") for r in out if r["kind"] == "actual" and r.get("_subject")}
    if len(subjects) >= 2 or multi:
        out = [r for r in out if r["kind"] not in ("actual", "recovered") or not r.get("_mine")]
    out = _scale_check(out, doc)
    for r in out:
        r.pop("role", None)
        r.pop("_clause", None)
        r.pop("_subject", None)
        r.pop("_mine", None)
        r.pop("_asset_row", None)
        r.pop("_tabular", None)
        r.pop("_table", None)
        r.pop("_brk", None)
        r.pop("_named", None)     # 1.3
        r.pop("_rev", None)
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


JUDGED = ("kind", "period", "metal", "unit", "qty", "low", "high", "sold", "aisc", "guided_low", "guided_high", "milestone",
          "asset", "basis")


def to_prediction(records):
    if not records:
        return None
    rows = {i: [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts] for i, rec in enumerate(records)}
    p = parse_records(rows)
    if not p["rows"]:
        return None
    return {"rows": [{k: r.get(k) for k in JUDGED} for r in p["rows"]]}


def _code_sha():
    # 1.2.1: portal/fingerprint.py -- this file plus exactly the helper code it runs, so a helper change bumps it
    return FP.code_sha(__file__)


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
    # ---- 1.1
    # SCZ.V 7375f6cd1714 -- a list of metals shares its verb; 'Zinc Production: 21,581 tonnes Lead Production:' is zinc
    r = rows("Santacruz Silver Produces 3,424,817 Silver Equivalent Ounces in Q3 2025, Comprising of 1,241,929 Ounces "
             "of Silver, 21,581 Tonnes of Zinc, 2,603 Tonnes of Lead, and 331 Tonnes of Copper",
             "Q3 2025 Production Highlights: Silver Production: 1,241,929 ounces Zinc Production: 21,581 tonnes Lead "
             "Production: 2,603 tonnes Copper Production: 331 tonnes")
    eq("SCZ metals", sorted((x["metal"], x["qty"]) for x in r if x["kind"] == "actual"),
       [("AgEq", 3424817.0), ("copper", 331.0), ("lead", 2603.0), ("silver", 1241929.0), ("zinc", 21581.0)])
    # EQX.TO 6b2f2d2b4f -- a part of the total, and a mine's figure, are not the company's
    r = rows("Equinox Gold Delivers Solid Second Quarter 2025 Financial and Operating Results",
             "HIGHLIGHTS FOR Q2 2025 On June 17, 2025, Equinox Gold closed its acquisition of Calibre. Produced 219,122 "
             "ounces of gold, including 72,823 oz of gold from the Nicaragua operations, excluding 1,975 oz from Castle "
             "Mountain and 1,495 oz from Los Filos. Consolidated production is reported on a consolidated basis.")
    eq("EQX consolidated", [(x["period"], x["qty"]) for x in r if x["kind"] == "actual"], [("Q2 2025", 219122.0)])
    # WDO.TO 6c30292fd995 -- a number the PDF split
    r = rows("Wesdome Reports Strong Second Quarter 2026 Results",
             "Consolidated gold production for the second quarter was 4 3,824 ounces, a 2% increase compared to Q2 2025.")
    eq("WDO split number", [(x["period"], x["qty"]) for x in r if x["kind"] == "actual"], [("Q2 2026", 43824.0)])
    # BTO.TO 5da30645ca93 -- an asset's share of the year is not the company's guidance
    eq("BTO contribute", rows("B2Gold Reports Q2 2025 Results",
                              "In 2025, the Company anticipates Fekola underground to contribute between 25,000 to "
                              "35,000 ounces of gold production."), [])
    # WDO.TO 324c04b2ba0b -- 'respectively'
    r = rows("Wesdome Reports Fourth Quarter and Year-End 2024 Financial Results",
             "Record annual production: Consolidated gold production in Q4 2024 and FY 2024 increased year-over-year by "
             "37% to 49,567 ounces and 39% to 172,033 ounces of gold, respectively.")
    eq("respectively", sorted((x["period"], x["qty"]) for x in r if x["kind"] == "actual"),
       [("FY 2024", 172033.0), ("Q4 2024", 49567.0)])
    # milestone asset names
    eq("asset names", [_milestone_asset(h) for h in (
        "Cabral Gold Announces First Gold Pour at Phase 1 Mine, Cui\u00fa Cui\u00fa Gold District, Brazil",
        "Saskatchewan Canada Cigar Lake Mine Resumes Production",
        "Torex Gold Declares Commercial Production at Media Luna Milestone marks the Company's official transition",
        "South Star Announces Santa Cruz Operational Update; First Shipment of Graphite Shipped")],
       ["Cui\u00fa Cui\u00fa", "Cigar Lake", "Media Luna", "Santa Cruz"])
    # a table's first column, under a header naming the release's own quarter
    r = rows("Heliostar Presents Q2 2026 Financial and Operating Results",
             "Key Performance Metrics Q2 2026 Q1 2026 Q2 2025 Operational Gold produced (ounces) 14,803 11,743 7,262 "
             "Gold sold (ounces) 11,960 9,980 8,375")
    eq("table", [(x["period"], x["qty"], x.get("sold")) for x in r if x["kind"] == "actual"], [("Q2 2026", 14803.0, 11960.0)])
    # APM.TO a73afb3d91 -- last year's comparative AISC is not this quarter's; SM.V 48f6e9c7f8 -- this one is
    r = rows("Andean Precious Metals Reports First Quarter 2025 Financial Results",
             "Consolidated Q1 2025 production of 21,361 gold equivalent ounces. Golden Queen OCC of $1,459/oz and AISC of "
             "$2,213/oz for Q1 2025 versus OCC of $1,762/oz and AISC of $1,936/oz for Q1 2024.")
    eq("AISC comparative", [x.get("aisc") for x in r if x["kind"] == "actual"], [2213.0])
    r = rows("Sierra Madre Announces Positive Q1 2025 Financial Results",
             "Q1 2025 silver production of 70,176 ounces. All-in-sustaining costs per AgEq ounce sold of $28.98 per ounce, "
             "compared to $32.18 in Q4 2024.")
    eq("AISC with comparison", [x.get("aisc") for x in r if x["kind"] == "actual"], [28.98])
    # ARTG.V 3b67f8f16a -- a month's figure does not take the quarter named after it
    r = rows("Artemis Gold Reports Q2 2025 Results",
             "Gold production during the month of April was 15,799 ounces and gold production during Q2 2025 totaled 50,623 ounces.")
    eq("month then quarter", [(x["period"], x["qty"]) for x in r if x["kind"] == "actual"], [("Q2 2025", 50623.0)])
    eq("partial-period table", rows("Artemis Gold Reports Q2 2025 Results",
        "Q2 2025 Highlights. Operating Results Units May 1-June 30, 2025 (post-commercial production period) Milled tonnes "
        "988,588 Gold produced ounces 34,824 Gold sold ounces 34,112 Cash costs US$ per ounce $690"), [])
    # USA.TO 8fcfc01936 -- a table whose columns are mines: its first column is a mine's
    r = rows("Americas Gold and Silver Announces Second Quarter Production",
             "Table 1: Q2 2026 Production and Sales Galena Cosal\u00e1 Consolidated Silver Produced (oz) 327,701 337,270 664,971 "
             "Total Silver Equivalent Produced (oz) 400,654 400,081 800,735")
    eq("mine columns", [x["qty"] for x in r if x["kind"] == "actual" and x["metal"] == "AgEq"], [])
    # BTO.TO 3996b06147 -- prepay deliveries are not the quarter's sales; MSA.TO 6321969878 -- 'production and sale'
    r = rows("B2Gold Reports Q2 2026 Results", "Q2 2026 gold production of 203,648 ounces. As of June 30, 2026, the Company "
             "had delivered all 264,768 ounces into the Gold Prepay contracts.")
    eq("prepay", [(x["qty"], x.get("sold")) for x in r if x["kind"] == "actual"], [(203648.0, None)])
    # MJS.V 8a492179b6 -- under a 'Six months ended' heading, a figure is not the quarter's
    r = rows("Majestic Gold Corp. Announces 2025 Q2 Results", "FINANCIAL AND OPERATIONAL HIGHLIGHTS Six months ended June 30, 2025. "
             "Gold production was 15,879 ounces, a 2% decrease over the 16,207 ounces produced for the FY2024 comparative period;")
    eq("six-month heading", [x["qty"] for x in r if x["kind"] == "actual" and x["period"] == "Q2 2025"], [])
    # HMMC.V e87c2cecff -- a table's section line is not its total
    r = rows("Hemlo Mining Corp. Reports First Quarter 2026 Operating Results",
             "Q1 2026 Operating Highlights Three months ended Hemlo Mine Unit March 31, 2026 Williams Ore processed 000t 230 "
             "Gold produced 1 oz. 24,635 Interlake Ore processed 000t 92 Gold produced oz. 10,129 Total gold produced 1 oz. "
             "34,764 Total gold sold 38,685")
    eq("table total", [(x["qty"], x.get("sold")) for x in r if x["kind"] == "actual"], [(34764.0, 38685.0)])
    # MJS.V 88e044a710 -- a figure dated only by the release's quarter, found in the table's six-month column
    r = rows("Majestic Gold Corp. Announces Q2 2026 Results",
             "Gold production was 12,027 ounces, a 24.3% decrease from the 15,879 ounces produced in the prior period. "
             "SELECTED RESULTS Three months ended June 30, Six months ended June 30, 2026 2025 2026 2025 Operating data "
             "Gold produced (ozs) 6,751 7,649 12,027 15,879 Gold sold (ozs) 6,292 7,309 11,235 14,288")
    eq("doc row vs table", [(x["period"], x["qty"], x.get("sold")) for x in r if x["kind"] == "actual"],
       [("Q2 2026", 6751.0, 6292.0), ("H1 2026", 12027.0, 11235.0)])     # 1.3.2: the six-month column is a row too
    # MKO.V f98dbfe0bb -- inventory bought with a mine is not production
    eq("acquired", rows("Mako Mining Reports First Quarter 2025 Financial Results",
                        "Finished products in the amount of 936 oz of gold and 8,562 oz of silver were acquired at the time of acquisition."), [])
    # 1.2: breakdowns behind an equivalent figure, metal-column and period-column tables, half years, and guards
    r = rows("Heliostar Achieves Full-Year 2025 Production Guidance",
             "Heliostar Metals Ltd. is pleased to announce that it produced 8,459 Gold Equivalent Ounces (GEOs) (8,180 gold "
             "ounces and 21,494 silver ounces) in the three months ended December 31, 2025.")
    eq("HSTR breakdown", sorted((x["metal"], x["qty"]) for x in r if x["kind"] == "actual"),
       [("GEO", 8459.0), ("gold", 8180.0), ("silver", 21494.0)])
    r = rows("Orvana Reports Q2 FY2026 Production Results",
             "Orovalle, the Company's subsidiary in Spain, produced 9,827 GEO (8,464 gold ounces, 0.8 million copper pounds "
             "and 25,424 silver ounces) in Q2 2026.")
    eq("a mine's breakdown is not the company's", [x["metal"] for x in r if x["kind"] == "actual" and x["metal"] == "gold"], [])
    r = rows("Torex Gold Reports Q1 2026 Production Results",
             "TABLE 1: PRELIMINARY FIRST QUARTER 2026 OPERATING RESULTS Au Ag Cu AuEq 2 Grade processed 2.79 gpt 22.68 gpt "
             "0.79% - Produced (before payable deductions) 73,647 oz 543.0 koz 14.9 mlb 100,874 oz Sold (after payable "
             "deductions) 81,233 oz 539.0 koz 15.6 mlb 109,222 oz")
    eq("TXG metal columns", sorted((x["metal"], x["qty"], x.get("sold")) for x in r if x["kind"] == "actual"),
       [("AuEq", 100874.0, 109222.0), ("copper", 14900000.0, 15600000.0), ("gold", 73647.0, 81233.0),
        ("silver", 543000.0, 539000.0)])
    r = rows("Pan American Silver achieves 2025 production guidance",
             "2025 Attributable Base Metal Production (thousand tonnes) Q4 2025 FY 2025 Zinc 16.8 55.9 Lead 8.2 27.0 Copper "
             "0.8 3.0 PAN AMERICAN SILVER CORP.")
    eq("PAAS period columns", sorted((x["period"], x["metal"], x["qty"]) for x in r if x["kind"] == "actual")[:2],
       [("FY 2025", "copper", 3000.0), ("FY 2025", "lead", 27000.0)])
    eq("quarter and full year headline", _doc_period("LUNDIN GOLD REPORTS FOURTH QUARTER AND FULL YEAR 2024 RESULTS", "")["quarter"], "Q4 2024")
    eq("six months ended", _resolve("h6", ("June", "2025"), {}), "H1 2025")
    r = rows("Allied Gold Reports Record Q4 Production",
             "The Company produced 117,004 ounces of gold in the fourth quarter, bringing total production for 2025 to "
             "379,081 ounces, exceeding the Company's annual production guidance of above 375,000 ounces.")
    eq("a year is not a range's low end", [(x["period"], x.get("guided_low"), x.get("guided_high")) for x in r if x["kind"] == "actual"
                                          and x["period"] == "FY 2025"], [("FY 2025", 375000.0, None)])     # 1.3.2: folded onto the year
    r = rows("Energy Fuels Expects to Achieve Full-Year Uranium Production Guidance by Mid-Year",
             "The Company expects finished uranium production at its White Mesa Mill to reach approximately 1.6 million "
             "pounds by June 30, which falls within the previously published full-year guidance range.")
    eq("an expected figure is not an actual", [x for x in r if x["kind"] == "actual"], [])
    # 1.2.1: milestone assets through the shared helper
    eq("page form", [_page_asset(n) for n in ("Kainantu Gold Mine", "TVIRD Balabag Gold and Silver Project",
                                             "Saskatchewan Canada Cigar Lake Mine", "Songjiagou Underground Mine",
                                             "Only Producing Graphite Mine", "Biox Expansion And Lafigu\u00e9 Growth Projects")],
       ["Kainantu", "TVIRD Balabag", "Cigar Lake", "Songjiagou", None, None])
    eq("helper fills a blank", [x["asset"] for x in rows("Centerra Gold Announces First Gold Pour at the \u00d6ks\u00fct Mine")],
       ["\u00d6ks\u00fct"])
    eq("helper trims 1.2.0's name", _milestone_asset_pn(
        "Galantas Confirms First Shipment of Gold and Silver Concentrates From Underground Omagh Mine"), "Omagh")
    eq("helper replaces a name that is no project", [x["asset"] for x in rows(
        "IAMGOLD ANNOUNCES THE RESUMPTION OF MINING OPERATIONS AT THE SOUTHERN PITS OF ITS ROSEBEL GOLD MINE",
        "IAMGOLD Corporation announced today the resumption of mining at the southern pits of the Rosebel Gold Mine "
        "in Suriname.") if x["kind"] == "milestone"], ["Rosebel"])
    eq("1.2.0's name stays when the helper has none", _milestone_asset_pn(
        "Saskatchewan Canada Cameco Announces McArthur River/Key Lake Operation Resumes Production",
        "The McArthur River mine and Key Lake mill have resumed production."), "McArthur River/Key Lake")
    eq("fingerprint follows the helper", FP.uses(__file__, "portal.project_names"), True)
    print("production %s (1.0-1.2.1 tests): %s" % (VERSION, "ok" if not bad else "%d FAILURES" % bad))
    # 1.3 -- year-to-date rows and recovered rows
    r = rows("Company Reports Third Quarter 2025 Production",
             "The Company produced 46,360 ounces of gold during Q3 2025, bringing production year-to-date to 124,525 ounces of gold.")
    eq("1.3 YTD at Q3 is 9M", sorted((x["period"], x.get("qty")) for x in r if x["kind"] == "actual"),
       [("9M 2025", 124525.0), ("Q3 2025", 46360.0)])
    r = rows("Endeavour Silver Q3 2018 Production",
             "For the nine months ended September 30, 2018, silver production was 4,135,563 oz and gold production was 39,850 oz.")
    eq("1.3 nine months ended", sorted((x["period"], x["metal"], x.get("qty")) for x in r if x["kind"] == "actual"),
       [("9M 2018", "gold", 39850.0), ("9M 2018", "silver", 4135563.0)])
    r = rows("Mako Mining Announces Q4 2025 Production Results",
             "A total of 9,621 ounces of gold were recovered during the quarter at a mill recovery of 81.8%. "
             "Units Q1 2025 Q2 2025 Q3 2025 Q4 2025 Gold Recovered oz 10,436 8,961 6,879 9,621 Gold Equiv. Recovered (2) oz "
             "10,553 9,063 6,961 9,745 Silver Recovered oz 10,677 10,269 7,226 9,442 Gold Sold oz 9,881 10,104 6,918 9,307")
    eq("1.3 recovered rows", sorted((x["kind"], x["period"], x["metal"], x.get("qty"), x.get("sold")) for x in r),
       [("recovered", "Q4 2025", "AuEq", 9745.0, None), ("recovered", "Q4 2025", "gold", 9621.0, 9307.0),
        ("recovered", "Q4 2025", "silver", 9442.0, None)])
    r = rows("Sailfish Royalty Update", "The NSR is not payable on the first 500,000 ounces of gold recovered from any "
             "commercial production in 2026.")
    eq("1.3 royalty threshold is not recovered", r, [])
    r = rows("Company Reports Q1 2026 Production", "Gold production was 20,000 ounces in Q1 2026. Year-to-date production "
             "is 20,000 ounces.")
    eq("1.3 Q1 YTD is not a row", [(x["period"]) for x in r], ["Q1 2026"])
    r = rows("Alamos Reports Third Quarter 2019 Results", "Third Quarter 2019 \u2022 Produced 121,900 ounces of gold, bringing "
             "year-to-date production to 372,400 ounces.")
    eq("1.3 bringing year-to-date to", sorted((x["period"], x.get("qty")) for x in r if x["kind"] == "actual"),
       [("9M 2019", 372400.0)])      # the quarter's figure here has no period of its own (as in 1.2.1)
    r = rows("Eldorado Gold Reports Q2 2019 Results", "Gold production for the quarter totalled 91,803 ounces with 174,780 "
             "ounces produced year-to-date.")
    eq("1.3 produced year-to-date", sorted((x["period"], x.get("qty")) for x in r if x["kind"] == "actual"),
       [("H1 2019", 174780.0), ("Q2 2019", 91803.0)])
    r = rows("Wheaton Reports Q3 2025", "The Company remains on track to achieve our 2025 GEOs guidance of 105,000 to 115,000 "
             "ounces, with 84,480 GEOs sold over the first three quarters of the year.")
    eq("1.3 guidance before a span", [(x["kind"], x["period"], x.get("low")) for x in r], [("guidance", "FY 2025", 105000.0)])
    r = rows("OceanaGold Reports Third Quarter 2018 Results", "For the nine months ended September 30, 2018, the Company "
             "produced 406,631 ounces of gold including 138,034 ounces in the third quarter.")
    eq("1.3 a list never runs through including", [(x["period"], x.get("qty")) for x in r if x["kind"] == "actual"],
       [("9M 2018", 406631.0)])
    r = rows("SSR Mining Reports Third Quarter 2021 Results", "Puna continues to achieve record production year-to-date: "
             "Produced 2.2 million ounces of silver at cash costs of $7.65 per ounce in the third quarter.")
    eq("1.3 year-to-date before, quarter after", [x for x in r if x["kind"] == "actual"], [])
    r = rows("Energy Fuels Announces Q3 2019 Results", "During the nine months ended September 30, 2019, the Company "
             "recovered approximately 56,000 pounds of U3O8. The Company also recovered approximately 1,300,000 pounds of "
             "high-purity vanadium pentoxide during the nine months ended September 30, 2019.")
    eq("1.3 vanadium is not uranium", [x for x in r if x.get("qty") == 1300000.0], [])
    r = rows("Capstone Provides 2020 Guidance", "Cozamin is expected to achieve a 50% increase to annual copper and silver "
             "production of 50 to 55 million pounds and 1.5 million ounces, respectively, by 2021.")
    eq("1.3 a target by a year is not guidance", [x for x in r if x["kind"] == "guidance"], [])
    r = rows("Endeavour Silver Reports 2016 Production", "Silver production in the Fourth Quarter, 2016 was 1,088,845 oz "
             "and gold production was 44,402 oz, for silver equivalent production of 1.9 million oz.")
    eq("1.3 Fourth Quarter, 2016", sorted((x["period"], x["metal"]) for x in r if x["kind"] == "actual"),
       [("Q4 2016", "AgEq"), ("Q4 2016", "gold"), ("Q4 2016", "silver")])
    r = rows("OceanaGold Reports Third Quarter 2021 Results", "Consolidated gold production was 101,000 ounces in the third "
             "quarter from our four operating mines. In New Zealand, Macraes delivered YTD gold production of 92,902 ounces.")
    eq("1.3 a named asset's year-to-date in a multi-mine release", [(x["period"], x.get("qty")) for x in r if x["kind"] == "actual"],
       [("Q3 2021", 101000.0)])
    r = rows("Alamos Gold Reports Third Quarter 2022 Results", "With year-to-date production of 326,200 ounces of gold and a "
             "further increase in production expected in the fourth quarter, the Company remains on track.")
    eq("1.3 year-to-date with a forecast after", [(x["period"], x.get("qty")) for x in r if x["kind"] == "actual"], [("9M 2022", 326200.0)])
    r = rows("OceanaGold Reports Third Quarter 2017 Results", "Our four operating mines performed well. On a consolidated basis, "
             "including attributable production from the Haile Gold Mine, the Company produced 408,394 ounces of gold in the first "
             "nine months of 2017.")
    eq("1.3 the company after a named asset", [(x["period"], x.get("qty")) for x in r if x["kind"] == "actual"], [("9M 2017", 408394.0)])
    # ---- 1.3.1
    r = rows("Kinross reports strong 2026 second-quarter results",
             "2026 second-quarter highlights: \u2022 Production1 of 492,326 gold equivalent ounces (\u201cAu eq. oz.\u201d). "
             "\u2022 Production cost of sales of $1,352 per Au eq. oz. sold.")
    eq("1.3.1 year-first quarter", [(x["period"], x["metal"], x.get("qty")) for x in r if x["kind"] == "actual"], [("Q2 2026", "AuEq", 492326.0)])
    r = rows("Kinross reports 2025 fourth-quarter and full-year results",
             "Production: Kinross produced 483,582 Au eq. oz. in Q4 2025, compared with 501,209 Au eq. oz. in Q4 2024.")
    eq("1.3.1 Au eq. oz.", [(x["period"], x["metal"], x.get("qty")) for x in r if x["kind"] == "actual"], [("Q4 2025", "AuEq", 483582.0)])
    r = rows("Kinross reports strong 2026 first-quarter results",
             "Three months ended March 31, 2026 2025 Operating Highlights (a) Total gold equivalent ounces(b) Produced 500,941 "
             "529,861 Sold 494,128 524,089 Attributable gold equivalent ounces(b) Produced 492,563 512,088 Sold 485,855 506,000.")
    eq("1.3.1 a table cell before the next row's label", [x.get("qty") for x in r if x["kind"] == "actual" and x.get("qty") == 524089.0], [])
    r = rows("Silvercorp Reports Operational Results for the Third Quarter, Fiscal 2026",
             "Q3 Fiscal 2026 Operational Highlights \u2022 Silver production of 1.9 million ounces, a decrease of 4% over Q3 Fiscal 2025; "
             "silver equivalent (only silver and gold) i production of 2.0 million ounces, a decrease of 5% compared to 2.1 million "
             "ounces in Q3 Fiscal 2025;")
    eq("1.3.1 comparative periods", sorted((x["period"], x["metal"], x.get("qty")) for x in r if x["kind"] == "actual"),
       [("Q3 FY2026", "AgEq", 2000000.0), ("Q3 FY2026", "silver", 1900000.0)])
    r = rows("Santacruz Silver Reports Fourth Quarter and Year End 2023 Financial Results",
             "2023 Highlights\n\nProcessed 1,883,446 tonnes of material, a 14% increase year-over-year\n\n"
             "Produced of 22,641,052 silver equivalent ounces, a 25% increase year-over-year")
    eq("1.3.1 a highlights heading's year", [(x["period"], x.get("qty")) for x in r if x["kind"] == "actual"], [("FY 2023", 22641052.0)])
    r = rows("Amerigo Announces Q1-2022 Results", "Q1-2022 production was 16.5 million pounds of copper 6% higher than "
             "Q1-2021 production of 15.5 M lbs due to higher tonnage.")
    eq("1.3.1 the compared period's figure", [(x["period"], x.get("qty")) for x in r if x["kind"] == "actual"], [("Q1 2022", 16500000.0)])
    r = rows("DUNDEE PRECIOUS METALS ANNOUNCES 2018 FOURTH QUARTER AND ANNUAL RESULTS",
             "ANNUAL FINANCIAL AND OPERATING HIGHLIGHTS: Metals production \u2013 Achieved record gold production of 201,095 "
             "ounces and outperformed 2018 guidance. Copper production of 36.7 million pounds was in line with guidance;")
    eq("1.3.1 annual highlights", sorted((x["period"], x["metal"], x.get("qty")) for x in r if x["kind"] == "actual"),
       [("FY 2018", "copper", 36700000.0), ("FY 2018", "gold", 201095.0)])
    r = rows("Eldorado Announces 2024 Detailed Production & Cost Guidance", "2024 Guidance Highlights\n\n"
             "Gold production of 505,000 to 55 5,000 ounces, representing a 9% increase from 2023 gold production")
    eq("1.3.1 a guidance heading's bullets", [x for x in r if x["kind"] == "actual"], [])
    r = rows("Jaguar Mining Reports Fourth Quarter and Full Year 2025 Operating Results",
             "Fourth Quarter and Full Year 2025 Operating Highlights\n\n\u2022 Consolidated gold production: Totaled 9,356 ounces, "
             "compared with 14,787 ounces in the fourth quarter of 2024.")
    eq("1.3.1 a quarter-and-year heading", [(x["period"], x.get("qty")) for x in r if x["kind"] == "actual"], [("Q4 2025", 9356.0)])
    r = rows("IAMGOLD REPORTS FOURTH QUARTER AND YEAR-END 2023 RESULTS", "Attributable gold production, excluding C\u00f4t\u00e9 Gold, "
             "for 2024 is expected to be in the range of 430,000 to 490,000 ounces.")
    eq("1.3.1 'excluding' is an aside", [(x["period"], x.get("low"), x.get("high")) for x in r if x["kind"] == "guidance"], [("FY 2024", 430000.0, 490000.0)])
    r = rows("Wheaton Precious Metals Announces First Quarter Results", "Wheaton is the world's premier precious metals "
             "streaming company. Wheaton's estimated attributable production in 2024 is forecast to be 325,000 to 370,000 "
             "ounces of gold, 18.5 to 20.5 million ounces of silver, and 12,000 to 15,000 GEOs3 of other metals, resulting in "
             "annual production of approximately 550,000 to 620,000 GEOs. Average annual production is forecast to grow to "
             "over 850,000 GEOs3 in years 2029 to 2033.")
    eq("1.3.1 GEOs of other metals", sorted((x["kind"], x["period"], x["metal"], x.get("low")) for x in r if x["metal"] == "GEO"),
       [("guidance", "FY 2024", "GEO", 550000.0)])
    r = rows("ENDEAVOUR REPORTS STRONG Q1-2022 RESULTS", "Q1-2022 production from continuing operations amounted to 357koz. "
             "Gold sales decreased from 370koz in Q4-2021 to 359koz in Q1-2022.")
    eq("1.3.1 a dropped comparison still names the metal", [(x["period"], x["metal"], x.get("qty")) for x in r if x["kind"] == "actual" and x.get("role") != "sold"][:1],
       [("Q1 2022", "gold", 357000.0)])
    r = rows("First Majestic Announces Financial Results for Q4 and Year End 2019", "2019 HIGHLIGHTS Total production reached 25.6 "
             "million silver equivalent ounces. Silver production reached 13.2 million ounces of silver, a 13% increase over 2018.")
    eq("1.3.1 compared with last year, the figure is the year's", [(x["period"], x["metal"], x.get("qty")) for x in r if x["kind"] == "actual" and x["metal"] == "silver"],
       [("FY 2019", "silver", 13200000.0)])
    r = rows("Triple Flag Announces Strong Q1 2024 Results", "Fosterville (2.0% NSR gold royalty): Royalties equated to 1,051 GEOs. Agnico "
             "Eagle has disclosed that first quarter performance was in line with plan, and reiterated production guidance of 200,000 to "
             "220,000 ounces of gold in 2024. Cerro Lindo (65% silver stream): Sales were 6,585 GEOs. Buritic\u00e1 (100% silver stream).")
    eq("1.3.1 a partner's guidance", [x for x in r if x["kind"] == "guidance"], [])
    r = rows("Heliostar Presents Fiscal 2025 Financial Results", "The combined 2025 production of 34,098 GEOs achieved guidance. On "
             "January 13, 2026, Heliostar provided 2026 production guidance of 50,000-55,000 ounces of gold.")
    eq("1.3.1 the company's own guidance stays", [(x["period"], x.get("low")) for x in r if x["kind"] == "guidance"], [("FY 2026", 50000.0)])
    r = rows("OR ROYALTIES ANNOUNCES PRELIMINARY Q2 2026 GEO DELIVERIES",
             "OR Royalties is a royalty and streaming company. OR Royalties earned 20,757 attributable gold equivalent ounces1 "
             "(\u201cGEOs\u201d) in the second quarter of 2026.")
    eq("1.3.1 earned GEOs", [(x["period"], x["metal"], x.get("qty")) for x in r if x["kind"] == "actual"], [("Q2 2026", "GEO", 20757.0)])
    # ---- 1.3.2 (FIX5, round 2: only changes whose added rows were right on the dev folds and the answer key)
    pad = "The Company reported its results for the period and discussed its operations in detail. " * 4
    r = rows("Company Reports Fourth Quarter and Full Year 2025 Results",
             "Gold production in the fourth quarter was 70,266 ounces and full-year 2025 gold production was 244,979 ounces, "
             "within the Company's 2025 guidance of 240,000 to 260,000 ounces.")
    eq("1.3.2 a finished year's guidance goes on its actual row", [(x["kind"], x["period"], x.get("guided_low"), x.get("guided_high"))
                                                               for x in r if x["period"] == "FY 2025"], [("actual", "FY 2025", 240000.0, 260000.0)])
    r = rows("Company Reports Third Quarter 2024 Results",
             pad + "For three months ended September 30, For nine months ended September 30, 2024 2023 2024 2023 "
             "Gold produced (ounces) 85,147 84,473 258,459 249,062 Gold sold (ounces) 78,939 80,001 250,100 245,000")
    eq("1.3.2 the nine-month column of a table", sorted((x["period"], x["qty"], x.get("sold")) for x in r if x["kind"] == "actual"),
       [("9M 2024", 258459.0, 250100.0), ("Q3 2024", 85147.0, 78939.0)])
    eq("1.3.2 header layouts", [_cols_from(_header_toks(h_), {"quarter": "Q2 2026", "year": "2026"}) for h_ in (
        "Three months ended June 30, Six months ended June 30, 2026 2025 2026 2025 ",
        "Three months ended June 30, 2026 2025 Six months ended June 30, 2026 2025 ",
        "Q2 2026 Q1 2026 Q2 2025 YTD 2026 YTD 2025 Gold ")],
       [["Q2 2026", "Q2 2025", "H1 2026", "H1 2025"], ["Q2 2026", "Q2 2025", "H1 2026", "H1 2025"],
        ["Q2 2026", "Q1 2026", "Q2 2025", "H1 2026", "H1 2025"]])
    r = rows("Company Reports Fourth Quarter and Full Year 2023 Results", pad + "2024 Guidance\n\nCopper production (tonnes) "
             "59,000 - 72,000 Gold production (ounces) 55,000 - 60,000 AISC ($/oz) 1,100 - 1,200")
    eq("1.3.2 a guidance table (and never an actual row or an AISC)", sorted((x["kind"], x["period"], x["metal"], x.get("low"), x.get("aisc"))
                                                                           for x in r),
       [("guidance", "FY 2024", "copper", 59000.0, None), ("guidance", "FY 2024", "gold", 55000.0, None)])
    r = rows("Company Reports Third Quarter 2017 Results", pad + "FY 2017 Production and Cost Guidance YTD 2017 Actual FY 2017 Guidance "
             "El Valle Production Gold (oz) 36,345 50,000 \u2013 55,000 Copper (million lbs) 4.2 6.0 \u2013 6.5 Don Mario Production Gold "
             "(oz) 26,281 35,000 \u2013 40,000 Copper (million lbs) 6.1 7.0 \u2013 7.5 Total Production Gold (oz) 62,626 85,000 \u2013 95,000 "
             "Copper (million lbs) 10.3 13.0 \u2013 14.0 Total capital expenditures $15,514 $27,000 \u2013 $30,000")
    eq("1.3.2 a guidance table by mine: only the total's lines", sorted((x["metal"], x["low"], x["high"]) for x in r if x["kind"] == "guidance"),
       [("copper", 13000000.0, 14000000.0), ("gold", 85000.0, 95000.0)])
    r = rows("First Majestic Announces Q4 and Full Year 2025 Results", "Full year 2025 production of 15.4 million oz of silver "
             "(guidance range: 14.8 - 15.8 million oz), 147,433 oz of gold (guidance range: 135,000 - 144,000 oz).")
    eq("1.3.2 a figure's own guidance range goes on its row", sorted((x["metal"], x["qty"], x.get("guided_low")) for x in r),
       [("gold", 147433.0, 135000.0), ("silver", 15400000.0, 14800000.0)])
    r = rows("Endeavour Silver Reports Q4 2019 Results", "Metal Production: Q4 production of 939,511 oz silver and 9,578 oz gold for 1.7 "
             "million oz silver equivalent (AgEq).")
    eq("1.3.2 'oz silver equivalent' is AgEq", sorted((x["metal"], x["qty"]) for x in r if x["kind"] == "actual"),
       [("AgEq", 1700000.0), ("gold", 9578.0), ("silver", 939511.0)])
    r = rows("Luca Sets up for a Strong 2H 2024", "Production Guidance of 60,000 \u2013 70,000 AuEq Ounces for the Full Year 2024.")
    eq("1.3.2 'AuEq Ounces'", [(x["kind"], x["period"], x["metal"], x.get("low")) for x in r], [("guidance", "FY 2024", "AuEq", 60000.0)])
    r = rows("Lundin Gold Reports Q3 2024 Results", "Gold production in Q3 2024 was 122,154 oz. During the same quarter in 2023, the "
             "Company produced 112,212 oz of gold.")
    eq("1.3.2 'the same quarter in 2023' is the comparison", [(x["period"], x["qty"]) for x in r if x["kind"] == "actual"], [("Q3 2024", 122154.0)])
    r = rows("Ivanhoe Mines Issues Q1 2021 Results", "The phased expansion would position Kamoa-Kakula as the second-largest copper complex, "
             "with peak annual copper production of more than 800,000 tonnes.")
    eq("1.3.2 a peak rate is not a row", r, [])
    print("production %s (all tests): %s" % (VERSION, "ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if self_test(verbose=True) else 0)
