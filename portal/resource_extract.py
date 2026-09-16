"""resource_extract.py v3.3.1 — multi-format MRE extractor.

Handles all of these patterns we found in the wild:

A. "Indicated Mineral Resource of 3.124 Mt at 1.20 g/t Au"
   "Pit-constrained Indicated: 1.944 Mt grading 1.50 g/t AuEq"

B. "Total Indicated Mineral Resource Estimate of 2,113,000 t with an average
    grade of 1.8 g/t gold for 123,400 oz of contained gold"
   "1.01 million indicated ounces of gold at 0.98 g/t contained in 31.74 Million tonnes"

C. "50 Mt @ 608 ppm Li for 161,000 indicated tonnes of LCE"  (inverted: tonnage first)

D. "Indicated Resources: 81,888,000 tonnes with grades of 0.83 g/t Au"

Detects MRE type from headline:
  Maiden | Updated | Increase | Filing | Initial | Restated
"""
from __future__ import annotations
import bisect
import re

_NAME_TO_SYMBOL = {
    "gold": "Au", "silver": "Ag", "copper": "Cu", "nickel": "Ni",
    "zinc": "Zn", "lead": "Pb", "cobalt": "Co", "uranium": "U",
    "molybdenum": "Mo", "manganese": "Mn", "vanadium": "V",
    "lithium": "Li", "tungsten": "W", "tin": "Sn", "antimony": "Sb",
    "platinum": "Pt", "palladium": "Pd",
    "lithium carbonate equivalent": "LCE",
    "gold equivalent": "AuEq", "copper equivalent": "CuEq",
}

_METAL_TOKEN = (
    # v3.3: equivalents FIRST. Alternation is leftmost-first, so with "copper"
    # listed before "copper\s+equivalent" the grade "0.39% copper equivalent"
    # was stored as Cu (Kodiak MPD x4, NexMetals Selkirk, ATEX Valeriano).
    r"(?:gold|silver|copper|nickel|zinc)[\s\-]+equivalent|"
    r"lithium\s+carbonate\s+equivalent|lithium\s+oxide|"
    r"(?:Au|Ag|Cu|Ni|Zn)\.?\s*Eq(?:uivalent)?|"
    r"U3O8|Li2O|P2O5|WO3|TREO|REE|LCE|Cg|"
    r"Au|Ag|Cu|Ni|Zn|Pb|Co|U|Mn|V|Li|W|Mo|Sb|Sn|Pt|Pd|"
    r"gold|silver|copper|nickel|zinc|lead|cobalt|uranium|molybdenum|manganese|"
    r"vanadium|lithium|tungsten|tin|antimony|platinum|palladium"
)

# A number as printed: thousands-grouped ("21,310,000") or plain, optional
# decimals. It never starts inside another number and never ends before
# ",4" -- so a European decimal comma ("5,46 million tonnes") does not match
# at all instead of being read as 546.
_NUM = r"(?<![\d.,])(?<!\d\.\s)(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\d|,\d)"

_CAT_TOKEN = (
    r"Measured\s+(?:and|&|\+)\s+Indicated|Measured|Indicated|Inferred|"
    r"M&I|M\+I|Total|Combined"
)


# ---------- Format A/B: <Category> ... <tonnage> ... <grade> <unit> <metal> ----------

_RE_A = re.compile(
    r"(?:Pit[\s\-]constrained\s+|Underground\s+|Open[\s\-]pit\s+|Total\s+|Pit\s+)?"
    rf"(?P<cat>{_CAT_TOKEN})"
    r"(?:\s+(?:Mineral\s+)?Resource[s]?(?:\s+Estimate)?)?"
    r"\s*(?:[:\-—,]|of)?\s*"
    rf"(?P<tonnage>{_NUM})\s*"
    r"(?P<tunit>Mt\b|Million\s+tonnes?\b|billion\s+tonnes?\b|kt\b|thousand\s+tonnes?\b|t\b|tonnes?\b)"
    # v3.3: "2.03 million tonnes of contained nickel" is metal, not ore
    r"(?!\s*(?:\([^)]{0,12}\)\s*)?(?:of\s+)?(?:contained|in[\s\-]situ)\b)"
    # connector: "at | @ | of | grading | with [.. words ..] of | with grades of"
    # v3.3: the gap may not cross a sentence end or another category word --
    # "total of 2.03 million tonnes of contained nickel. Inferred Mineral
    # Resources now total 1.45 billion tonnes grading 0.22% nickel" was stored
    # as 2.03 Mt at 0.22% Ni.
    r"(?:(?:(?!\.\s|;|\b(?:Measured|Indicated|Inferred)\b)[\s\S]){0,80}?"
    r"(?:at|@|grading|of|with(?:\s+grades)?\s+of)\s*)"
    r"(?P<grade>\d+(?:\.\d+)?)\s*"
    r"(?P<gunit>g/t|gpt|g/tonne|grams?\s*/\s*t(?:onne)?|grams?\s+per\s+tonne|%|ppm)\s*"
    rf"(?P<metal>{_METAL_TOKEN})\b(?![\s\-]*(?:equivalent|eq)\b)"
    r"(?!\s*(?:\w+\s+){0,2}cut[\s\-]?off)",
    re.I | re.S,
)


# ---------- Format C: <tonnage> <unit> @ <grade> <unit> <metal> for <count> <category> ----------

_RE_C = re.compile(
    rf"(?P<tonnage>{_NUM})\s*"
    r"(?P<tunit>Mt|Million\s+tonnes?|kt|thousand\s+tonnes?|t\b|tonnes?)\s*"
    r"(?:@|at|grading)\s*"
    r"(?P<grade>\d+(?:\.\d+)?)\s*"
    r"(?P<gunit>g/t|gpt|g/tonne|grams?\s*/\s*t(?:onne)?|grams?\s+per\s+tonne|%|ppm)\s*"
    rf"(?P<metal>{_METAL_TOKEN})\b(?![\s\-]*(?:equivalent|eq)\b)\s+"
    r"(?:for|yielding|containing)\s+"
    r"(?P<count>\d+(?:[.,]\d+)?)\s*"
    r"(?:Moz|Million\s+ounces?|koz|thousand\s+ounces?|Mt|Million\s+tonnes?|kt|thousand\s+tonnes?|tonnes?|ounces?|oz)?\s*"
    r"(?:of\s+)?"
    rf"(?P<cat>{_CAT_TOKEN})",
    re.I | re.S,
)


# ---------- Format B-bis: "<count> million indicated ounces of gold at <grade>" ----------
# e.g. "1.01 million indicated ounces of gold at 0.98 g/t contained in 31.74 Million tonnes"

_RE_B2 = re.compile(
    rf"(?P<count>{_NUM})\s*"
    r"(?P<mult>million|thousand)?\s*"
    rf"(?P<cat>{_CAT_TOKEN})"
    r"\s+(?P<cunit>ounces|oz|tonnes|t\b)\s+"
    r"(?:of\s+)?"
    rf"(?P<metal>{_METAL_TOKEN})\b\s*"
    r"(?:at|@)\s*"
    r"(?P<grade>\d+(?:\.\d+)?)\s*"
    r"(?P<gunit>g/t|gpt|g/tonne|grams?\s*/\s*t(?:onne)?|grams?\s+per\s+tonne|%|ppm)"
    # the contained ounces can BE the headline number, with no tonnage stated
    # v3.3: a tonnage is only a tonnage when it carries a unit
    r"(?:\s+(?:contained\s+in\s+)?"
    rf"(?P<tonnage>{_NUM})\s*"
    r"(?P<tunit>Mt|Million\s+tonnes?|kt|thousand\s+tonnes?|tonnes?|t\b))?",
    re.I | re.S,
)


# ---------- Skip-list (only for clearly non-MRE) ----------

_SKIP_HEADLINE_RE = re.compile(
    r"(?:targets?\s+(?:maiden\s+)?resource|"
    r"hires?\s+\w+\s+consult|"
    r"retains?\s+\w+\s+(?:mining\s+)?consult|"
    r"work\s+on\s+maiden\s+(?:mineral\s+)?resource|"
    r"congratulates|"
    r"(?:mre\s+)?forthcoming|"
    # v3: announcing an INTENTION to produce an estimate is not an estimate.
    # "Emperor Commences Maiden Mineral Resource Estimate" quoted a HISTORICAL
    # 727,000 oz resource in its body and would otherwise have been stored.
    r"(?:commenc|initiat|engag|commission|undertak)\w*\s+(?:\w+\s+){0,3}?"
    r"(?:maiden\s+|updated\s+|initial\s+)?(?:mineral\s+)?resource|"
    r"work\s+towards?\s+(?:a\s+)?(?:maiden\s+)?(?:mineral\s+)?resource|"
    r"plans?\s+to\s+(?:complete|upgrade|prepare|deliver)|"
    r"to\s+(?:complete|prepare)\s+(?:a\s+)?(?:maiden|updated|new))",
    re.I,
)

# A figure the release is quoting rather than reporting: somebody else's
# estimate, or the company's own superseded one.
_RE_HISTORICAL = re.compile(
    r"(?i)\b(historic(?:al|ally)?|predates?|non[\-\s]compliant|past\s+produc"
    r"|previously\s+(?:report|announc|releas|disclos)|superseded"
    r"|press\s+release\s+dated|news\s+release\s+dated|technical\s+report\s+dated"
    r"|reported\s+by\s+[A-Z])\b")

HIST_WINDOW = 250


def _quoted_historical(text: str, m) -> bool:
    """True when this figure sits beside language marking it as not the news."""
    return bool(_RE_HISTORICAL.search(
        text[max(0, m.start() - HIST_WINDOW):m.end() + HIST_WINDOW]))


# ---------- MRE type (Maiden / Updated / Increase / Filing) ----------

def detect_mre_type(headline: str, body: str) -> str:
    h = (headline or "").lower()
    # v3.3: the headline decides first. The body often recalls the company's
    # earlier maiden estimate ("Laramide Announces an Increase in Mineral
    # Resource Estimate" was typed Maiden), and "inaugural" was not recognised.
    # ("Updated MRE ... Including a Maiden Joutel Resource" is an update)
    if re.search(r"\b(?:updat\w*|increas\w*|expand\w*|grow\w*|upgrad\w*|revised)\b", h):
        return "Update"
    if re.search(r"\b(?:maiden|initial|inaugural|first)\b[^.]{0,40}?\b(?:mineral\s+)?(?:resource|mre\b|reserve)", h):
        return "Maiden"
    b = (body or "")[:2000].lower()
    text = h + " " + b
    if re.search(r"\bmaiden\s+(?:inferred\s+|indicated\s+)?(?:mineral\s+)?resource", text):
        return "Maiden"
    if re.search(r"\binitial\s+(?:mineral\s+)?resource", text):
        return "Maiden"
    # Headline-driven first
    if re.search(r"\b(?:significant|major)?\s*increase\s+(?:in|to)", text):
        return "Update"
    if re.search(r"\bupdated?\s+(?:mineral\s+)?resource", text):
        return "Update"
    if re.search(r"\bnew\s+(?:\d{4}\s+)?(?:mineral\s+)?resource", text):
        return "Update"
    if re.search(r"\b(?:files|filed|filing\s+of)\s+(?:.{0,30})?(?:ni\s*43-?101|technical\s+report|mineral\s+resource)", text):
        return "Update"
    if re.search(r"\bcompletes?\s+(?:mineral\s+)?resource", text):
        return "Update"
    if re.search(r"\bdelivers?\s+(?:.{0,30})?(?:mineral\s+)?resource", text):
        return "Update"
    if re.search(r"\b(?:announces|reports)\s+(?:.{0,30})?(?:mineral\s+)?resource\s+estimate", text):
        return "Update"
    return "Update"


# ---------- helpers ----------

_OZ_METALS = ("Au", "Ag", "AuEq", "AgEq")
_BASE_LB = ("Cu", "Ni", "Zn", "Pb")

_SPECIAL_METALS = {"u3o8": "U3O8", "li2o": "Li2O", "p2o5": "P2O5", "wo3": "WO3", "treo": "TREO",
                   "ree": "REE", "lce": "LCE", "cg": "Cg", "lithiumoxide": "Li2O",
                   "lithiumcarbonateequivalent": "LCE"}
_EQ_BASE = {"au": "Au", "gold": "Au", "ag": "Ag", "silver": "Ag", "cu": "Cu",
            "copper": "Cu", "ni": "Ni", "nickel": "Ni", "zn": "Zn", "zinc": "Zn"}


def _norm_metal(s: str) -> str:
    s = (s or "").strip().lower()
    k = re.sub(r"[\s.\-]+", "", s)
    if k in _SPECIAL_METALS:
        return _SPECIAL_METALS[k]
    for suf in ("equivalent", "eq"):
        if k.endswith(suf) and k[: -len(suf)] in _EQ_BASE:
            return _EQ_BASE[k[: -len(suf)]] + "Eq"
    if s in _NAME_TO_SYMBOL:
        return _NAME_TO_SYMBOL[s]
    return s.title() if len(s) <= 3 else s


def _norm_cat(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s*(?:\band\b|&|\+|/)\s*", " & ", s)
    s = re.sub(r"\s+", " ", s).strip().replace("probabl e", "probable")
    return {
        "measured":               "Measured",
        "indicated":              "Indicated",
        "inferred":               "Inferred",
        "measured & indicated":   "M&I",
        "m & i":                  "M&I",
        "total":                  "Total",
        "combined":               "Total",
        "proven":                 "Proven",
        "probable":               "Probable",
        "proven & probable":      "P&P",
        "p & p":                  "P&P",
    }.get(s, s.title())


def _to_tonnes(amt: float, unit: str) -> float:
    u = re.sub(r"\s+", " ", (unit or "").lower().strip())
    if u.startswith("billion"):
        return amt * 1_000_000_000
    if u in ("mt", "million tonnes", "million tonne") or u.startswith("million") or u.startswith("m "):
        return amt * 1_000_000
    if u in ("kt", "thousand tonnes", "thousand tonne") or u.startswith("thousand"):
        return amt * 1_000
    return amt


def _to_oz(amt: float, unit: str | None) -> float | None:
    if unit is None:
        return None
    u = unit.lower().strip()
    if "moz" in u or "million ounce" in u or "million oz" in u:
        return amt * 1_000_000
    if "koz" in u or "thousand ounce" in u or "thousand oz" in u:
        return amt * 1_000
    if u in ("ounces", "oz"):
        return amt
    return None


def _prep(text: str) -> str:
    """v3.3: undo PDF-to-text damage that hid the metal. Subscripts arrive as
    separate lines ("0.85% Li\\nO", "770 ppm U\\n3\\nO\\n8") and were stored as
    Li and U."""
    t = (text or "").translate({0x2082: "2", 0x2083: "3", 0x2085: "5", 0x2088: "8",
                                0x00a0: " ", 0x202f: " ", 0x2011: "-"})
    t = re.sub(r"\bLi\s*2?\s*O\b(?!\w)", "Li2O", t)
    t = re.sub(r"\bU\s*3\s*O\s*8\b", "U3O8", t)
    t = re.sub(r"\bP\s*2\s*O\s*5\b", "P2O5", t)
    # "10.5M million tonnes"
    t = re.sub(r"(\d)M\s+million\b", r"\1 million", t)
    # "0. 96 g/t Au": a decimal split by a stray space
    t = re.sub(r"(?<![\d.,])(\d{1,3})\. (\d{1,3}\s*(?:g/t|gpt|%|ppm|grams))", r"\1.\2", t)
    return t


def _entry(cat, metal, tonnes, grade, gunit, fmt):
    contained_oz = contained_t = contained_lb = None
    if gunit == "g/t":
        if metal in _OZ_METALS and tonnes:
            contained_oz = tonnes * grade / 31.1035
    elif gunit == "%":
        contained_t = tonnes * grade / 100
        if metal in _BASE_LB:
            contained_lb = contained_t * 2204.62
    elif gunit == "ppm":
        contained_t = tonnes * grade / 1_000_000
    return {
        "category": cat, "metal": metal,
        "tonnes": tonnes, "grade": grade, "grade_unit": gunit,
        "contained_oz": contained_oz, "contained_t": contained_t, "contained_lb": contained_lb,
        "_fmt": fmt,
    }


def _grade_ok(grade: float, gunit: str) -> bool:
    """Plausibility is a fact: a percentage cannot exceed 100."""
    if gunit == "%":
        return 0 < grade <= 100
    if gunit == "g/t":
        return 0 < grade <= 5_000
    if gunit == "ppm":
        return 0 < grade <= 1_000_000
    return grade > 0


# "M&I Mineral Resources total 73.1 Mt" -- "total" is a verb there, and the
# category is the one before it. 11 of 13 stored "Total" categories were this.
_RE_TOTAL_NOUN = re.compile(r"(?:total|combined)\s+(?:mineral\s+)?resources?", re.I)
_RE_CAT_WORD = re.compile(
    r"(?<![\w&])(Measured\s*(?:and|&|\+)\s*Indicated|M\s?&\s?I|Measured|Indicated|Inferred|"
    r"Proven\s*(?:and|&|\+)\s*Probable|Reserves?)(?![\w&])", re.I)


def _fix_total(text: str, m) -> str | None:
    """Return the real category for a Format-A 'Total', or None to drop it."""
    s = m.start("cat")
    if _RE_TOTAL_NOUN.match(text, s):
        return "Total"
    before = text[max(0, s - 110):s]
    before = re.split(r"(?<!\d)\.\s|;|•", before)[-1]
    found = list(_RE_CAT_WORD.finditer(before))
    after = text[m.end("tunit"):m.end("tunit") + 30]
    if re.match(r"\s*(?:\([^)]{0,12}\)\s*)?(?:of\s+)?Prove[nd]", after, re.I):
        return "P&P"
    # "a total of 6.1 Mt at 1.87% Li2O of Indicated Resources"
    tail = re.match(r"[^.;\u2022]{0,40}?\bof\s+(Measured\s*(?:and|&|\+)\s*Indicated|M\s?&\s?I|Measured|Indicated|Inferred)\b",
                    text[m.end():m.end() + 60], re.I)
    if tail:
        return _norm_cat(tail.group(1))
    if found:
        c = found[-1].group(1)
        return "P&P" if c.lower().startswith("reserve") else _norm_cat(c)
    return "Total"


# ---------- Format E (v3.3): category-anchored clause ----------
# One sentence-bounded clause around a resource category, with the tonnage,
# grade and (optional) contained metal in any order:
#   "Indicated Mineral Resource of 441,000 ounces of gold at an average grade of
#    1.16 g/t Au and totalling 11,787,000 tonnes"
#   "2.458 million ounces of Indicated gold resources at 1.04 g/t Au, contained
#    within 73.8 million tonnes"
#   "16.8 million tonnes at an average grade of 3.02 g/t Au for 1.63 million
#    ounces of Measured and Indicated Mineral Resources"     (category after)
#   "the indicated mineral resource contains 773,000 oz of gold (21,310,000
#    tonnes at 1.13 g/t gold)"
# When tonnage, grade and stated contained metal are all present they must
# agree within 25%, otherwise the clause was mis-read and nothing is stored.

_CAT_E = re.compile(
    r"(?<![\w&])(?P<cat>Measured\s*(?:and|&|\+|/)\s*Indicated|M\s?&\s?I|M\+I|"
    r"Proven\s*(?:and|&|\+|/)\s*Probabl\s?e|P\s?&\s?P|Measured|Indicated|Inferred|"
    r"Proven|Probable)(?![\w&])", re.I)

_CAT_CONTEXT = re.compile(
    r"^[^.;•]{0,60}?\b(?:resources?|reserves?|MRE|categor(?:y|ies)|ounces|oz)\b"
    r"|^\s*(?:\)|[:\-–—]\s*\d)"
    # "Indicated totals 3.391 Mt grading 3.15 g/t gold"
    r"|^\s*(?:totals?|totall?ing|comprises?|of)\s+\d", re.I)

_BOUND_E = re.compile(r"(?<!\d)\.(?=\s)|(?<=\d)\.(?=\s+[A-Z(•])|;|•|▪|●|\n\s*[\-–o]\s+|\bTable\s+\d", re.I)

_TON_E = re.compile(
    rf"(?P<n>{_NUM})\s*"
    # "tonnes?\b", never "tonnes?": the engine would back off to "tonne" and
    # the contained-metal lookahead below would then see "s of contained"
    r"(?P<u>(?:billion|million|thousand)\s*(?:\(\W{0,3}[MBk]\W{0,3}\)\s*)?(?:metric\s+)?(?:tonnes?\b|t\b)"
    r"|M\s+(?:metric\s+)?tonnes?\b|Mt\b|kt\b|(?:metric\s+)?tonnes?\b|t\b(?![/\-]))"
    r"(?:\s*\(\W{0,3}(?:Mt|kt|t|tonnes|M\s?t)\W{0,3}\))?"
    r"(?!\s*(?:of\s+)?(?:contained|in[\s\-]situ|LCE|lithium\s+carbonate|Cg\b|"
    r"(?:copper|nickel|zinc|lead|antimony|lithium|cobalt|U3O8|uranium|metal)\b)"
    r"|\s*(?:per|/)\s*(?:day|d\b|year|yr|annum|hour|h\b)"
    r"|\s*(?:of\s+)?(?:ore\s+)?(?:processed|milled|mined|treated))",
    re.I)

_GRADE_E = re.compile(
    r"(?<![\d.,])(?<!\d\.\s)(?P<g>\d+(?:\.\d+)?)\s*"
    r"(?P<gu>g/t|gpt|g/tonne|grams?\s*(?:per|/)\s*(?:metric\s+)?tonne|%|ppm)"
    r"(?:\s*\(\W{0,3}(?:g/t|gpt)\W{0,3}\))?\s*(?:of\s+)?"
    rf"(?P<metal>{_METAL_TOKEN})\b(?![\s\-]*(?:equivalent|eq)\b)",
    re.I)

_OZ_E = re.compile(
    rf"(?P<n>{_NUM})\s*(?P<m>million|thousand|billion|M|k)?\s*"
    r"(?:(?:measured|indicated|inferred|M&I)\s+)?"
    rf"(?:(?P<metal2>{_METAL_TOKEN})\s+)?"
    r"(?P<u>Mozs?|koz|(?:troy\s+)?ounces|oz)\b"
    r"(?:\s*\(\W{0,3}(?:Mozs?|koz|oz)\W{0,3}\))?"
    rf"(?:\s+(?:of\s+)?(?:contained\s+)?(?:(?P<metal>{_METAL_TOKEN})\b))?",
    re.I)

_LB_E = re.compile(
    rf"(?P<n>{_NUM})\s*(?P<m>million|billion|M|B)?\s*"
    r"(?:\(\W{0,3}\w{1,4}\W{0,3}\)\s*)?(?P<u>pounds|lbs?\.?|Mlbs?|Blbs?)\b"
    r"(?:\s*\(\W{0,3}\w{1,4}\W{0,3}\))?"
    rf"(?:\s+(?:of\s+)?(?:contained\s+)?(?:(?P<metal>{_METAL_TOKEN})\b))?",
    re.I)

# A category written AFTER its figures: "... 1.63 Moz of Measured and Indicated",
# "18.7 Mt at 1.84 g/t Au (Indicated)", "50.4Mt @ 2.0% CuEq in the M&I".
_OXIDE = r"[A-Z][a-z]?\s?\d\s?O\s?\d?"
_BACK_STYLE = re.compile(
    r"(?:(?:tonnes|Mt|kt|oz|ounces|Mozs?|koz)\b\s*(?:\([^)]{0,30}\)\s*)?"
    rf"(?:(?:of\s+)?(?:contained\s+)?(?:{_METAL_TOKEN}|{_OXIDE})\b)?"
    rf"|(?:g/t|gpt|%|ppm)\s*(?:\([^)]{{0,30}}\)\s*)?(?:of\s+)?(?:{_METAL_TOKEN}|{_OXIDE})\b)"
    r"\s*(?:respectively\s*)?(?:\([^)]{0,30}\)\s*)?,?\s*(?:of\s+|in\s+(?:the\s+)?|as\s+|\(\s*)?(?:total\s+)?$",
    re.I)

# where one category's figures end and the next one's begin
_JOINER = re.compile(r"(?:,\s*|\s)(?:and|plus|while|with\s+an?\s+additional|as\s+well\s+as|in\s+addition\s+to)\s", re.I)

# a forward segment that opens with a joiner: this category's figures were
# written before it ("... (Indicated), and 33.4 Mt at 1.33% Li2O (Inferred)")
_FWD_OPENS_JOINER = re.compile(
    r"^\W*(?:(?:mineral\s+)?(?:resources?|reserves?|categor(?:y|ies)|MRE|classification)\b)?\W*"
    r"(?:and|plus|as\s+well\s+as|while|with\s+an?\s+additional|in\s+addition\s+to)\b", re.I)

# a grade-shaped number with no metal after it ("1.25 Mt at 0.99%, 0.04% Cu")
_BARE_GRADE = re.compile(r"(?<![\d.,])\d+(?:\.\d+)?\s*(?:g/t|gpt|%|ppm)", re.I)

# figures quoted for comparison with an older estimate, in the same sentence
_RE_PRIOR = re.compile(r"\b(?:previous|prior|former|for\s+comparison)\b", re.I)
# a sensitivity case or a subset quoted inside the estimate, not the estimate
_RE_NOT_BASE = re.compile(r"\bsensitivit(?:y|ies)\b", re.I)
_RE_SUBSET_BEFORE = re.compile(r"\b(?:including|includes|of\s+which)\b[^.;\u2022]{0,40}$", re.I)
_RE_CHANGE = re.compile(r"\b(?:increas\w*|decreas\w*|grew|growth|up\s+\d|expand\w*|added|adds|convert\w*)\b", re.I)

# Somebody else's deposit, named right before the figure: "Copper Mountain
# Mining Corporation's ... Mine ("Copper Mountain"), which hosts a Proven and
# Probable Mineral Reserve of 702 Mt", "Western Copper and Gold Corporation's
# (TSX: WRN, NYSE: WRN), Casino project which has Measured and Indicated
# Resources", "The adjacent Moss Lake gold deposit hosts an Indicated ...".
# Deliberately narrow: "adjacent" or "which contains" alone also describe the
# company's own deposits (Omai's Gilt Creek, Kenorland's Regnault).
_RE_THIRD_PARTY = re.compile(
    r"(?:(?:mine|project|deposit|property)\b[^.;\u2022]{0,40}?,?\s*which\s+(?:hosts?|has)"
    r"|\badjacent\s+(?:[\w'\u2019\-]+\s+){0,4}(?:deposit|project|mine|property)\s+(?:hosts?|has|contains)"
    r"|\((?:TSXV?|TSX-V|NYSE|NASDAQ|ASX|CSE|OTCQ[XB])\s*:[^)]{0,40}\)\s*,?\s*(?:[\w'\u2019\-]+\s+){0,3}?"
    r"(?:with|which\s+(?:hosts?|has)))"
    r"\s+(?:an?\s+|the\s+)?(?:(?:total|combined|current|global)\s+)?$",
    re.I)


_RE_THIRD_PARTY_SENT = re.compile(
    r"(?:Corporation|Corp|Inc|Ltd|Limited|plc|Mining|Mines|Resources|Metals|Gold|Copper)(?:\u2019|')s\b"
    r"[^;\u2022]{0,200}?\bwhich\s+(?:hosts?|has)\b"
    r"|\badjacent\s+(?:[\w'\u2019\-]+\s+){0,4}(?:deposit|project|mine|property)\s+(?:hosts?|has|contains)\b"
    r"|\((?:TSXV?|TSX-V|NYSE|NASDAQ|ASX|CSE|OTCQ[XB])\s*:[^)]{0,40}\)\s*,?\s*(?:[\w'\u2019\-]+\s+){0,3}?"
    r"(?:with|which\s+(?:hosts?|has))\s",
    re.I)


# v3.3.1: "The updated Auld Creek MRE includes an Indicated Mineral Resource of
# 0.3Mt @ 3.18g/t Au" -- when the thing doing the including is the estimate
# itself, "includes" lists its categories; it does not introduce a subset.
_ESTIMATE_INCLUDES = re.compile(r"\b(?:MRE|estimates?|resources?|update)\s*$", re.I)


def _subset(text: str, start: int) -> bool:
    """'Including Mountain Zone: Indicated Mineral Resource of 9.3 Mt' is a part of
    the estimate; when the whole is stated too, Format E stores the whole."""
    win = text[max(0, start - 60):start]
    m = re.search(r"\b(?:including|includes|of\s+which)\b[^.;\u2022\n]{0,40}$", win, re.I)
    return bool(m) and not _ESTIMATE_INCLUDES.search(win[:m.start()])


def _third_party(text: str, start: int) -> bool:
    if _RE_THIRD_PARTY.search(text[max(0, start - 160):start]):
        return True
    # ... or earlier in the same sentence ("... Casino project which has M&I
    # Resources of 2,490.7 Mt ..., and Inferred Resources of 1.4 Mt ...")
    win = text[max(0, start - 400):start]
    cut = [m.end() for m in re.finditer(r"(?<!\d)\.\s|;|\u2022", win)]
    win = win[cut[-1]:] if cut else win
    return bool(_RE_THIRD_PARTY_SENT.search(win))

_E_SEG_FWD = 200
_E_SEG_BACK = 160


def _mult(m: str | None) -> float:
    m = (m or "").lower()
    return {"billion": 1e9, "b": 1e9, "million": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}.get(m, 1.0)


def _cutoff_near(seg: str, s: int, e: int) -> bool:
    return bool(re.search(r"cut[\s\-]?off(?:\s+grade)?(?:\s+of)?\s*(?:\(\w+\)\s*)?$", seg[max(0, s - 30):s], re.I)
                or re.match(r"\s*(?:[\w()\"'\u201c\u201d]+\s+){0,3}(?:cut[\s\-]?off|recover)", seg[e:e + 40], re.I))


def _stated_agrees(seg: str, metal: str, tonnes: float, grade: float, gunit: str,
                   near: tuple[int, int] | None = None) -> bool:
    """False only when the clause states contained metal close to the figures
    (within 100 chars) and none of it is within 25% of tonnes x grade."""
    lo, hi = (0, len(seg)) if near is None else (max(0, near[0] - 100), near[1] + 100)
    cands = []
    if gunit == "g/t" and metal in _OZ_METALS:
        calc = tonnes * grade / 31.1035
        for o in _OZ_E.finditer(seg):
            if not (lo <= o.start() <= hi):
                continue
            sm = o.group("metal") or o.group("metal2")
            if sm and _norm_metal(sm) != metal:
                continue
            if not sm and metal.endswith("Eq"):
                continue
            u = o.group("u").lower()
            v = float(o.group("n").replace(",", "")) * _mult(o.group("m"))
            if u.startswith("moz"):
                v *= 1e6
            elif u == "koz":
                v *= 1e3
            if v >= 1_000:
                cands.append(v)
    elif gunit == "%" and metal in _BASE_LB:
        calc = tonnes * grade / 100 * 2204.62
        for o in _LB_E.finditer(seg):
            if not (lo <= o.start() <= hi):
                continue
            sm = o.group("metal")
            if not sm or _norm_metal(sm) != metal:
                continue
            u = o.group("u").lower()
            v = float(o.group("n").replace(",", "")) * _mult(o.group("m"))
            if u.startswith("mlb"):
                v *= 1e6
            elif u.startswith("blb"):
                v *= 1e9
            cands.append(v)
    else:
        return True
    if not cands:
        return True
    return any(abs(v - calc) / calc <= 0.25 for v in cands)


def _pick(seg: str, back: bool, grade_seg: str | None = None):
    """Tonnage and grade for one category from one segment. With grade_seg,
    the tonnage comes from seg (written before the category) and the grade from
    grade_seg (written after it): "4.831 billion tonnes of Measured and
    Indicated Resources at 0.48% copper"."""
    tons = []
    for t in _TON_E.finditer(seg):
        pre = seg[max(0, t.start() - 30):t.start()]
        if re.search(r"contain\w*\s+(?:approximately\s+|about\s+)?$", pre, re.I):
            continue
        try:
            v = _to_tonnes(float(t.group("n").replace(",", "")), t.group("u"))
        except ValueError:
            continue
        if 1_000 <= v <= 10_000_000_000:
            tons.append((v, t))
    if not tons:
        return None
    if back:
        # "..., and 194,000 ounces of gold (2.50 Mt at 2.42 g/t Au) in the Inferred":
        # start after the last joiner that precedes the last tonnage
        last = tons[-1][1]
        js = [j for j in _JOINER.finditer(seg) if j.end() <= last.start()]
        if js:
            cut = js[-1].end()
            seg = seg[cut:]
            tons = [(v, t) for v, t in tons if t.start() >= cut]
            tons = [(v, _Span(t.start() - cut, t.end() - cut)) for v, t in tons]
        tonnes, tm = tons[-1]
        # a joiner between the tonnage and the category: the tonnage closes
        # the previous clause ("(6.0 Mt @ 1.04 g/t Au) plus another 210,000
        # ounces of gold in the inferred")
        # ... but "0.15% copper, 0.26 g/t gold, and 0.95 g/t silver in the
        # Inferred" is one clause: only a new QUANTITY after the joiner counts
        if grade_seg is None:
            for j in _JOINER.finditer(seg, tm.end()):
                rest = seg[j.end():]
                if _TON_E.search(rest) or _OZ_E.search(rest):
                    return None
    else:
        tonnes, tm = tons[0]
    gseg = seg if grade_seg is None else grade_seg
    grades = []
    for g in _GRADE_E.finditer(gseg):
        if _cutoff_near(gseg, g.start(), g.end()):
            continue
        gunit = g.group("gu").lower().replace("gpt", "g/t")
        if gunit.startswith("gram") or gunit == "g/tonne":
            gunit = "g/t"
        try:
            grade = float(g.group("g"))
        except ValueError:
            continue
        if _grade_ok(grade, gunit):
            grades.append((grade, gunit, _norm_metal(g.group("metal")), g))
    if not grades:
        return None
    if grade_seg is not None:
        # tonnage must end the before-segment, grade must open the after-segment
        if not re.fullmatch(r"\s*(?:\([^)]{0,30}\)\s*)?(?:of\s+|in\s+(?:the\s+)?)?(?:total\s+)?", seg[tm.end():]) \
                or grades[0][3].start() > 60:
            return None
        grade, gunit, metal, gm = grades[0]
        return seg + " " + grade_seg, tonnes, tm, grade, gunit, metal, gm
    after = [x for x in grades if tm.end() <= x[3].start() <= tm.end() + 80]
    grade, gunit, metal, gm = after[0] if after else grades[0]
    if after:
        # the first grade after the tonnage must be the one with the metal
        bare = _BARE_GRADE.search(seg, tm.end())
        if bare and bare.start() < gm.start() and not _cutoff_near(seg, bare.start(), bare.end()):
            return None
    elif back and tm.start() - gm.end() > 15:
        # "... and 1.8 g/t Ag An additional 16.9 million tonnes of Inferred"
        return None
    return seg, tonnes, tm, grade, gunit, metal, gm


def _extract_e(text: str) -> list[dict]:
    """Format E over already-prepared text. Returns entries in text order."""
    cats = []
    for c in _CAT_E.finditer(text):
        after = text[c.end():c.end() + 80]
        before = text[max(0, c.start() - 60):c.start()]
        # "Inferred:" labels the figures that FOLLOW it
        back_style = bool(_BACK_STYLE.search(before)) and not re.match(
            r"\s*(?:[\w\-]+\s+){0,2}?(?:mineral\s+)?(?:resources?|MRE)?\s*:", after, re.I)
        ctx_ok = bool(_CAT_CONTEXT.search(after)) or back_style
        cats.append((c, ctx_ok, back_style))
    bounds = [b.start() for b in _BOUND_E.finditer(text)]
    out = []
    for i, (c, ctx_ok, back_style) in enumerate(cats):
        if not ctx_ok:
            continue
        cat = _norm_cat(c.group("cat"))
        # "Indicated and Inferred Mineral Resources of 12 Mt": a combined figure
        if cat == "Inferred" and re.search(r"Indicated\s*(?:and|&|\+)\s*$", text[max(0, c.start() - 20):c.start()], re.I):
            continue
        # next/previous category mention that is not a restatement of this one
        # ("Measured and Indicated ("M&I")")
        nxt, nxt_back = len(text), False
        for c2, ok2, b2 in cats[i + 1:]:
            if _norm_cat(c2.group("cat")) == cat and c2.start() - c.end() <= 15:
                continue
            nxt, nxt_back = c2.start(), b2
            break
        prv = 0
        for c0, _, _ in reversed(cats[:i]):
            if _norm_cat(c0.group("cat")) == cat and c.start() - c0.end() <= 15:
                continue
            prv = c0.end()
            break
        bi = bisect.bisect_right(bounds, c.end())
        fwd_end = min(bounds[bi] if bi < len(bounds) else len(text), nxt, c.end() + _E_SEG_FWD)
        bj = bisect.bisect_left(bounds, c.start()) - 1
        back_start = max(bounds[bj] + 1 if bj >= 0 else 0, prv, c.start() - _E_SEG_BACK)
        if back_start == c.start() - _E_SEG_BACK:
            # never start or end a segment inside a number ("3.71" -> "71")
            ws = re.search(r"\s", text[back_start:c.start()])
            back_start = back_start + ws.end() if ws else c.start()
        if fwd_end == c.end() + _E_SEG_FWD:
            ws = text.rfind(" ", c.end(), fwd_end)
            fwd_end = ws if ws > c.end() else fwd_end
        fwd = text[c.end():fwd_end]
        back = text[back_start:c.start()]
        if fwd_end == nxt and nxt_back:
            # the next category owns the figures written just before it:
            # cut at the last joiner ("and", "plus"), else before its number
            js = list(_JOINER.finditer(fwd))
            if js:
                fwd = fwd[:js[-1].start()]
            else:
                ns = list(re.finditer(_NUM, fwd))
                fwd = fwd[:ns[-1].start()] if ns else ""
        # Figures written before a category belong to it only when the text
        # says so ("... Moz of Indicated", "(Indicated)"); otherwise reading
        # backwards picks up the previous category's figures (IAMGOLD Nelligan
        # stored Indicated tonnage and grade as Inferred).
        if _FWD_OPENS_JOINER.match(fwd):
            fwd = ""
        order = ((back, True), (back, "split"), (fwd, False)) if back_style else ((fwd, False),)
        rejected = None
        for seg, is_back in order:
            got = _pick(seg, True, fwd) if is_back == "split" else _pick(seg, is_back)
            if not got:
                continue
            seg2, tonnes, tm, grade, gunit, metal, gm = got
            # the figures must start close to the category in forward mode
            if is_back is False and min(tm.start(), gm.start()) > 120:
                continue
            span = (back_start, c.end()) if is_back is True else \
                (back_start, fwd_end) if is_back == "split" else (c.start(), fwd_end)
            # the whole sentence the figures sit in
            s0 = bisect.bisect_right(bounds, span[0]) - 1
            s1 = bisect.bisect_left(bounds, span[1])
            sentence = text[bounds[s0] if s0 >= 0 else 0: bounds[s1] if s1 < len(bounds) else len(text)]
            sub = _RE_SUBSET_BEFORE.search(text[max(0, span[0] - 60):span[0]])
            if sub and _ESTIMATE_INCLUDES.search(text[max(0, span[0] - 60):span[0]][:sub.start()]):
                sub = None
            if _RE_NOT_BASE.search(text[span[0]:span[1]]) or sub:
                rejected = {"_rejected": "subset_or_sensitivity", "category": cat, "metal": metal, "_span": span}
                break
            if _RE_PRIOR.search(sentence) and not _RE_CHANGE.search(sentence):
                rejected = {"_rejected": "prior_estimate", "category": cat, "metal": metal, "_span": span}
                break
            if _third_party(text, c.start() if is_back is False else span[0]) or \
                    (is_back is not False and _third_party(text, c.start())):
                rejected = {"_rejected": "third_party", "category": cat, "metal": metal, "_span": span}
                break
            pre = text[max(0, c.start() - 60):c.start()] if (is_back is False and back_style) else ""
            near = (len(pre) + min(tm.start(), gm.start()), len(pre) + max(tm.end(), gm.end())) \
                if is_back != "split" else None
            if not _stated_agrees(pre + seg2, metal, tonnes, grade, gunit, near):
                rejected = {"_rejected": "stated_mismatch", "category": cat, "metal": metal, "_span": span}
                continue
            e = _entry(cat, metal, tonnes, grade, gunit, {True: "E<", False: "E>", "split": "E<>"}[is_back])
            e["_span"] = span
            out.append(e)
            rejected = None
            break
        if rejected:
            out.append(rejected)
    return out


class _Span:
    def __init__(self, s, e):
        self._s, self._e = s, e

    def start(self):
        return self._s

    def end(self):
        return self._e


# ---------- gate + extractor ----------

# ---------- Format D: tonnage-first then category, e.g.
#   "3,299 thousand tonnes (\"kt\") Measured and Indicated grading 1.28% nickel"
#   "132 kt Inferred grading 0.93% nickel"
_RE_D = re.compile(
    rf"(?P<tonnage>{_NUM})\s*"
    r"(?P<tunit>Mt|Million\s+tonnes?|kt|thousand\s+tonnes?|t\b|tonnes?)"
    # narrow gap: optional whitespace, optional parenthetical like ("kt"), optional quotes
    r"(?:\s*\([^)]{0,20}\))?\s*[\"\'\s]{0,5}"
    rf"(?P<cat>{_CAT_TOKEN})"
    r"\s+(?:grading|grades?\s+of|with\s+grades?\s+of|at|@)\s+"
    r"(?P<grade>\d+(?:\.\d+)?)\s*"
    r"(?P<gunit>g/t|gpt|g/tonne|grams?\s*/\s*t(?:onne)?|grams?\s+per\s+tonne|%|ppm)\s*"
    rf"(?P<metal>{_METAL_TOKEN})\b(?![\s\-]*(?:equivalent|eq)\b)",
    re.I | re.S,
)

# Format E only runs when the headline is about a resource/reserve/report --
# drill and financing releases quote the company's standing resource.
_E_HEADLINE = re.compile(
    r"resource|reserve|\bMRE\b|43[\s\-]?101|technical\s+report|ounces|\boz\b|\bMoz\b|tonnes|\bMt\b",
    re.I)
# ... but not a drill-result headline that quotes the standing resource
# ("Carlyle Intercepts 689 Metres of 0.51 G/T Gold", "FireFly: Outstanding
# drilling results ... to drive impending resource update")
_E_HEADLINE_DRILL = re.compile(
    r"\b(?:intercepts?|intersects?|intersecting|intersections?|assays?|drill(?:ing|hole)?\s+results?)\b"
    # "689 Metres", "12.5 m of" -- but "20.3M AgEq Ounces" and "10.8 M lbs" are not metres
    r"|\d(?:\.\d+)?\s*(?:metres|meters)\b|(?-i:\d(?:\.\d+)?\s?m\b)",
    re.I)


def _e_allowed(headline: str) -> bool:
    h = headline or ""
    return bool(_E_HEADLINE.search(h)) and not _E_HEADLINE_DRILL.search(h)


USE_FORMAT_E = True
COLLISION_KEEPS_LARGER = True
EXTRACT_WINDOW = 8000


def is_real_mre(headline: str, body: str) -> bool:
    h = headline or ""
    if _SKIP_HEADLINE_RE.search(h):
        return False
    text = _prep(h + "\n" + (body or ""))
    if _RE_A.search(text) or _RE_C.search(text) or _RE_B2.search(text) or _RE_D.search(text):
        return True
    if USE_FORMAT_E and _e_allowed(h):
        etext = _prep(h + "\n\n" + (body or "")[:EXTRACT_WINDOW])
        return any("_rejected" not in e for e in _extract_e(etext))
    return False


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def extract_resources(headline: str, body: str) -> dict:
    if not is_real_mre(headline, body):
        return {"categories": {}, "mre_type": None}

    text = _prep((headline or "") + "\n\n" + (body or "")[:EXTRACT_WINDOW])
    by_cat: dict[tuple[str, str], dict] = {}

    def _put(cat, metal, tonnes, grade, gunit, fmt, m=None):
        if not _grade_ok(grade, gunit):
            return
        if tonnes and (tonnes < 1_000 or tonnes > 10_000_000_000):
            return
        key = (cat, metal)
        # v3.3.1: the same category and metal twice in one release is a part
        # and the whole ("Indicated oxide Resources for the two deposits total
        # 12.09 Mt" before "Santa Fe Deposit: Indicated Mineral Resources of
        # 31.15 Mt"). Keep the larger tonnage instead of the first mention.
        if key in by_cat and not (COLLISION_KEEPS_LARGER and tonnes and
                                  tonnes > (by_cat[key].get("tonnes") or 0)):
            return
        by_cat[key] = _entry(cat, metal, tonnes, grade, gunit, fmt)
        by_cat[key]["_span"] = (m.start(), m.end()) if m is not None else None
        return by_cat[key]

    def _gunit(m):
        g = m.group("gunit").lower().replace("gpt", "g/t")
        if g.startswith("gram") or g == "g/tonne":
            g = "g/t"
        return g

    # Format A/B (cat-first)
    for m in _RE_A.finditer(text):
        if _quoted_historical(text, m) or _third_party(text, m.start()) or _subset(text, m.start()):
            continue
        try:
            tonnage = _num(m.group("tonnage"))
            grade = float(m.group("grade"))
        except (ValueError, IndexError):
            continue
        cat = _norm_cat(m.group("cat"))
        if cat == "Total":
            cat = _fix_total(text, m)
        _put(cat, _norm_metal(m.group("metal")), _to_tonnes(tonnage, m.group("tunit")),
             grade, _gunit(m), "A", m)

    # Format C (tonnage-first, category trailing)
    for m in _RE_C.finditer(text):
        if _quoted_historical(text, m) or _third_party(text, m.start()) or _subset(text, m.start()):
            continue
        try:
            tonnage = _num(m.group("tonnage"))
            grade = float(m.group("grade"))
        except (ValueError, IndexError):
            continue
        _put(_norm_cat(m.group("cat")), _norm_metal(m.group("metal")),
             _to_tonnes(tonnage, m.group("tunit")), grade, _gunit(m), "C", m)

    # Format D (inverted: tonnage UNIT [parenthetical] CATEGORY grading GRADE UNIT METAL)
    for m in _RE_D.finditer(text):
        if _quoted_historical(text, m) or _third_party(text, m.start()) or _subset(text, m.start()):
            continue
        try:
            tonnage = _num(m.group("tonnage"))
            grade = float(m.group("grade"))
        except (ValueError, IndexError):
            continue
        _put(_norm_cat(m.group("cat")), _norm_metal(m.group("metal")),
             _to_tonnes(tonnage, m.group("tunit")), grade, _gunit(m), "D", m)

    # Format B2 (count million ounces of gold at grade contained in tonnage)
    for m in _RE_B2.finditer(text):
        if _quoted_historical(text, m) or _third_party(text, m.start()) or _subset(text, m.start()):
            continue
        try:
            count = _num(m.group("count"))
            grade = float(m.group("grade"))
            tonnage = _num(m.group("tonnage")) if m.group("tonnage") else None
            tunit = m.group("tunit") if m.group("tunit") else None
        except (ValueError, IndexError):
            continue
        cat = _norm_cat(m.group("cat"))
        metal = _norm_metal(m.group("metal"))
        gunit = _gunit(m)
        mult = (m.group("mult") or "").lower()
        oz_count = count * {"million": 1_000_000, "thousand": 1_000}.get(mult, 1)
        is_oz = m.group("cunit").lower() in ("ounces", "oz")
        tonnes = _to_tonnes(tonnage, tunit) if tonnage else None
        if tonnes and (tonnes < 1_000 or tonnes > 10_000_000_000):
            continue
        if not _grade_ok(grade, gunit):
            continue
        key = (cat, metal)
        if key in by_cat:
            continue
        # v3.3: a count of OUNCES was being stored as tonnes of base metal
        by_cat[key] = {
            "category": cat, "metal": metal,
            "tonnes": tonnes or 0, "grade": grade, "grade_unit": gunit,
            "contained_oz": oz_count if (is_oz and metal in _OZ_METALS) else None,
            "contained_t": oz_count if not is_oz else None,
            "contained_lb": None, "_fmt": "B2", "_span": (m.start(), m.end()),
        }

    # Format E (clause) -- fills only what A/B2/C/D did not find
    if USE_FORMAT_E and _e_allowed(headline):
        for e in _extract_e(text):
            if "_rejected" in e:
                continue
            if _quoted_historical(text, _Span(*e["_span"])):
                continue
            key = (e["category"], e["metal"])
            if key in by_cat:
                continue
            by_cat[key] = e

    mre_type = detect_mre_type(headline, body) if by_cat else None
    return {"categories": by_cat, "mre_type": mre_type}


# ---------- formatting helpers (unchanged from v1) ----------

def fmt_count(n: float | None, unit_short: str) -> str | None:
    if n is None:
        return None
    n = float(n)
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.1f}M {unit_short}"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.0f}K {unit_short}"
    return f"{n:.0f} {unit_short}"


def fmt_grade(grade: float, unit: str) -> str:
    if unit == "%":
        return f"{grade:.2f}%"
    if unit == "ppm":
        return f"{grade:.0f} ppm"
    return f"{grade:.2f} g/t"


def fmt_category_line(cat_data: dict) -> str:
    cat = cat_data.get("category", "")
    metal = cat_data.get("metal", "")
    grade = cat_data.get("grade")
    grade_unit = cat_data.get("grade_unit", "g/t")
    tonnes = cat_data.get("tonnes")
    if cat_data.get("contained_oz"):
        amt = fmt_count(cat_data["contained_oz"], "oz")
    elif cat_data.get("contained_lb"):
        amt = fmt_count(cat_data["contained_lb"], "lb")
    elif cat_data.get("contained_t"):
        amt = fmt_count(cat_data["contained_t"], "t")
    else:
        amt = None
    g = fmt_grade(grade or 0, grade_unit)
    t = fmt_count(tonnes, "t") if tonnes else None
    if amt and t:
        return f"{cat} {amt} {metal} @ {g} ({t})"
    if amt:
        return f"{cat} {amt} {metal} @ {g}"
    if t:
        return f"{cat} {t} @ {g} {metal}"
    return f"{cat} @ {g} {metal}"


# ---------- project name ----------

_RE_PROJECT = re.compile(
    # "on its Solar Lithium Project" - the article guard was lowercase-only
    # and attached to one alternative at a time, so "its" was never skipped.
    r"\b(?:at|for|on|of|from|within)\s+"
    r"(?:(?i:the|its|our|a|an)\s+)*"
    r"(?:(?i:wholly\s+owned|100%\s+owned|flagship)\s+)*"
    r"([A-Z][A-Za-z0-9' \-]{2,50}?)\s+"
    r"(?:Property|Project|Prospect|Deposit|Discovery|Mine)\b",
)


_RE_PROJECT_HL = re.compile(
    r"\b(?:Announces?|Reports?|Files|Provides|Updates?|Releases?)\s+"
    r"(?:results?\s+of\s+|the\s+|an?\s+)?"
    r"(?:Updated\s+|Revised\s+|Maiden\s+|Initial\s+|New\s+)?"
    r"([A-Z][A-Za-z0-9'&\- ]{2,50}?)\s+"
    r"(?:NI\s*43[\s-]?101|Technical\s+Report|Mineral\s+Resource(?:\s+Estimate)?|MRE\b|Resource\s+Estimate)",
    re.I,
)


_PROJECT_STOP = {
    "company", "corporation", "corp", "inc", "ltd", "ceo", "press", "release",
    "joint", "venture", "annual", "mineral", "maiden", "initial", "updated",
    "independent", "positive", "results", "announces", "reports", "files",
    "its", "the", "new", "ni", "43-101", "technical", "report", "resource",
    "estimate", "mre", "filing", "completes", "issues",
}


def _project_ok(name: str) -> bool:
    """7 of 29 stored project names were not projects: Mineral, Maiden,
    NI 43-101, Independent, Positive Updated MRE Results at Its Iska Iska."""
    toks = [t.lower().strip(".,;\u2019'") for t in (name or "").split()]
    if not 1 <= len(toks) <= 4:
        return False
    if any(t in _PROJECT_STOP for t in toks):
        return False
    return 3 <= len(name) <= 60


def find_project(headline: str, body: str) -> str | None:
    # 1) Existing strategy: "at/for/on/of <NAME> Property|Project|Mine|..."
    for src in (headline or "", (body or "")[:1500]):
        m = _RE_PROJECT.search(src)
        if m:
            name = m.group(1).strip().rstrip(",;.")
            if _project_ok(name):
                return name
    # 2) Headline strategy: "Announces <NAME> NI 43-101 / Technical Report / MRE"
    m = _RE_PROJECT_HL.search(headline or "")
    if m:
        name = m.group(1).strip().rstrip(",;.")
        if _project_ok(name):
            return name
    return None


# ---------------------------------------------------------------- self-test --
# Every case below is real, from the stored corpus.

EXTRACT_TEST = [
    # "Co" must not match the "co" in "copper": Ivanhoe's copper discovery was
    # stored as cobalt
    ("Ivanhoe Mines increases the size of the Western Forelands copper discovery",
     "Inferred Mineral Resource of 612.0 Mt at 1.80% copper", "Inferred"),
    ("McFarlane Issues NI 43-101 Mineral Resource Estimate on Its Juby Gold Project",
     "Highlights of Mineral Resource estimate 3.17 million inferred ounces gold "
     "at 0.89 gram per tonne (gpt or g/t) gold", "Inferred"),
    ("Galloper Delivers New 2026 Mineral Resource Estimate for LPSE Deposit",
     "Indicated Mineral Resource of 3.124 Mt at 1.20 g/t Au", "Indicated"),
]

REJECT_TEST = [
    ("Emperor Commences Maiden Mineral Resource Estimate for Duquesne West Gold",
     "The Property currently hosts a historical inferred mineral resource estimate "
     "of 727,000 ounces of gold at a grade of 5.42 g/t Au. The historical mineral "
     "resource estimate predates modern standards."),
    ("Pan American Energy Initiates Work Toward Mineral Resource Estimate",
     "Indicated Mineral Resource of 3.0 Mt at 1.1 g/t Au was reported historically."),
    ("Getchell Gold Corp. Plans to Upgrade Mineral Resource Estimate at Fondaway",
     "Inferred Mineral Resource of 2.0 Mt at 1.5 g/t Au"),
    ("Star Copper Congratulates Doubleview Gold Mineral Resource Estimate",
     "Indicated Mineral Resource of 9.0 Mt at 0.5 g/t Au"),
]

PROJECT_TEST = [
    ("Galloper Delivers New 2026 Mineral Resource Estimate for LPSE Deposit", "LPSE"),
    ("Cruz Battery Metals Announces Maiden Mineral Resource Estimate on its "
     "Solar Lithium Project in Nevada", "Solar Lithium"),
    ("NexMetals Files NI 43-101 Technical Report for 2026 Selkirk Mineral "
     "Resource Estimate", None),
]



# v3.3 field-level cases. (headline, body, category, metal, tonnes, grade) --
# every body is verbatim release text from the corpus. tonnes=None means the
# (category, metal) pair must NOT be produced with the tonnage in `grade`.
FIELD_TEST = [
    # copper equivalent was stored as Cu
    ("Kodiak Files NI 43-101 Technical Report: Initial Mineral Resource Estimate at the MPD Copper-Gold Project",
     "Total Indicated Mineral Resource: 82.9 million tonnes (Mt) grading 0.39% copper\nequivalent (CuEq) for "
     "519 million pounds (Mlb) of copper (Cu) and 0.39 million o",
     "Indicated", "CuEq", 82_900_000, 0.39),
    # contained nickel was read as ore tonnage across a sentence end; billion tonnes
    ("Canada Nickel Announces 46% Increase in Measured & Indicated Resource at Reid Nickel Sulphide Project",
     "Indicated Mineral Resources \nnow total 0.87 billion tonnes grading 0.23% nickel, for a total of 2.03 million "
     "tonnes of contained nickel. \nInferred Mineral Resources now total 1.45 billion tonnes grading 0.22% nickel, "
     "for a total of 3.22 mi",
     "Inferred", "Ni", 1_450_000_000, 0.22),
    # "Resources total" is a verb: the category is M&I, not Total
    ("AbraSilver Substantially Increases Total Diablillos Mineral Resources to 199 Million Ounces Contained Silver",
     "M&I Mineral Resources total \n73.1 Mt grading 79 g/t Ag and 0.66 g/t Au (139 g/t AgEq).\nTot",
     "M&I", "Ag", 73_100_000, 79.0),
    # reserves were stored as a resource "Total"
    ("Talon Metals Announces Eagle Mine NI 43-101 Technical Report Results; Provides Highlights and Strategic Takeaways",
     "Updated Mineral Reserves total 3,486 kt Proven and Probable, grading 1.06% nickel and 0.82% copper, including ",
     "P&P", "Ni", 3_486_000, 1.06),
    # PDF subscript on its own line: Li2O was stored as Li
    ("Imagine Lithium Highlights Robust Initial Mineral Resource, Strong Metallurgy and Upcoming Drill Program at Jackpot Property",
     "Indicated Resource: 3.1 million tonnes grading 0.85% Li\nO (26,200 t contained Li\nO)\nInferred Resource: "
     "5.3 million tonnes grading 0.91% Li\nO",
     "Indicated", "Li2O", 3_100_000, 0.85),
    # Format E: ounces, grade, then tonnage
    ("PELANGIO EXPLORATION INC. ANNOUNCES AN UPDATED MINERAL RESOURCE ESTIMATE FOR ITS MANFO GOLD PROJECT, GHANA",
     "Defines a total Indicated Mineral Resource of 441,000 ounces of gold at an average grade of 1.16 \ng/t Au and "
     "totalling 11,787,000 tonnes; and \n\u2022 Defines a total Inferred Mineral Resource of 396,000 ounces of gold at "
     "an average grade of 0. 77 \ng/t Au and totall",
     "Indicated", "Au", 11_787_000, 1.16),
    # Format E, category written after its figures
    ("Bonterra Files NI 43-101 Technical Report for the Bachelor and Moroy Deposits",
     'collectively hold 16.8 million tonnes ("\n\nMt\n\n") at an average grade of 3.02 g/t Au for 1.63 million '
     'ounces ("\n\nMoz\n\n") of Measured and Indicated Mineral Resources, plus 15.6 Mt at an average grade of '
     '4.32 g/t Au for 2.17 Moz Au of Inferred Mineral Resources.\n\nIn November 2023, the Company entered i',
     "Inferred", "Au", 15_600_000, 4.32),
    # the Inferred must not inherit the Indicated tonnage; "0. 96" is one number
    ("lAMGOLD ANNOUNCES SIGNIFICANT INCREASE IN NELLIGAN OUNCES & UPDATE OF GLOBAL MINERAL RESERVES AND RESOURCES",
     "3.1 million Indicated gold ounces in \n102.8 million tonnes (\u201cMt\u201d) at 0.95 grams per tonne gold "
     "(\u201cg/t Au\u201d), and 5.2 million Inferred ounces (166.4 \nMt at 0. 96 g/t Au). This represents a  56%",
     "Inferred", "Au", 166_400_000, 0.96),
    # ounces, category, then (tonnes at grade)
    ("Maple Gold Files Technical Report and Updated Mineral Resource Estimate for the Douay/Joutel Gold Project, Qu\u00e9bec",
     '905,000 ounces ("oz") of gold ("Au") Indicated\n\n(19.1 million tonnes ("\n\nMt\n\n") at 1.48 grams per '
     'tonne ("\n\ng/t\n\n") Au\n\n1\n\n) and\n\n4,279,000 oz Au Inferred\n\n(130.2 Mt at 1.03 g/t Au\n\n1\n\n) '
     'including:\n\nAn updated Douay pit-constraine',
     "Indicated", "Au", 19_100_000, 1.48),
    # tonnage before the category, grade after it; contained copper is not ore
    ("First Quantum Files NI 43-101 Technical Report for La Granja",
     "approximately 4.831 billion tonnes of Measured and Indicated Resources at 0.48% copper (\u201cCu\u201d), "
     "comprising 23.0 million tonnes of contained copper, and approximately 5.206 billion tonnes of Inferred "
     "Resources at 0.40% Cu, comprising an additional 20.7 million tonnes of contained copper (0.16% Cu cut-",
     "Inferred", "Cu", 5_206_000_000, 0.40),
    # "(6.0 Mt @ 1.04 g/t Au) plus another ... inferred": the joiner ends the clause
    ("Carolina Rush Announces Filing of Maiden Mineral Resource Technical Report for Brewer Gold-Copper Project",
     "tive date of May 2, 2025, outlines\n202,000\n \nounces of gold in the indicated category (6.0 Mt @ 1.04 g/t Au) "
     "plus another 210,000\nounces of gold in the inferred category (7.8 Mt @ 0.84 g/t Au)\n, with significant "
     "expansion potential\nin multiple directions. In a",
     "Inferred", "Au", 7_800_000, 0.84),
    # stated 33 koz cannot be 12.7 Mt at 0.97 g/t: that tonnage is the inferred's
    ("ADYTON REPORTS ~200% INCREASE TO WAPOLU UPDATED INFERRED MINERAL RESOURCE ESTIMATE",
     "The updated MRE is comprised of 1.0 million tonnes \ngrading 1.00 g/t Au for an indicated resource of 33 koz "
     "Au and 12.7 million tonnes grading 0.97 g/t Au for an \ninferred resource of 393 koz Au. The estimate was "
     "prepared by Minin",
     "Indicated", "Au", None, 12_700_000),
    # v3.3.1: "the MRE includes an Indicated ..." lists the estimate, it is not a subset
    ("RUA GOLD Files 43-101 Technical Reports for the Reefton and Glamorgan Projects in New Zealand",
     "The updated Auld Creek MRE includes an Indicated Mineral Resource of 0.3Mt @ 3.18g/t Au and\n12% Sb, "
     "containing 31koz of gold and 3kt antimony (54koz AuEq\n2\n). Also, an Inferred Resource of\n1.25Mt @ "
     "2.0g/t Au and 0.8% Sb, containing 79koz of Au and 10kt of Sb (148koz AuEq\n2\n).",
     "Indicated", "Au", 300_000, 3.18),
    # v3.3.1: a part (two oxide deposits) then the whole deposit: keep the larger
    ("Lahontan Announces 22% Increase in Mineral Resources at Santa Fe: 1,195,000 Au Eq oz Indicated, and 1,190,000 Au Eq oz Inferred",
     "Indicated oxide Resources for the two deposits total \n12.09 Mt grading 0.33 g/t Au Eq for 128,000 Au Eq "
     "ounces and Inferred oxide Resources total 8.34 Mt grading 0.36 g/t Au \nEq for 96,000 Au Eq ounces, an "
     "increase of over 37%  compared to the resources reported in the 2024 MRE (please see \nTable One).\n\u2022 "
     "Santa Fe Deposit resources increase by over 26%:  Indicated Mineral Resources of 31.15 Mt grading 0.99 g/t "
     "Au Eq \ntotaling 993,000 Au Eq ounces and Inferred Mineral Resources of 41.60 Mt grading 0.71 g/t Au Eq "
     "totaling 954,000 Au Eq \nounces (please see Table One). ",
     "Indicated", "AuEq", 31_150_000, 0.99),
]

# v3.3 rejections: somebody else's deposit, or a superseded estimate
REJECT_TEST_V33 = [
    ("Collective Metals Commissions Derrick Strickland to Complete NI 43-101 Technical Report on its Princeton "
     "Copper Project & Announces a Private Placement",
     "Copper Mountain Mining Corporation\u2019s currently producing Copper Mountain Mine (\u201c\n\nCopper "
     "Mountain\n\n\u201d), which hosts a\n\nProven and Probable Mineral Reserve of 702 Mt of 0.24% Copper\n\n."),
    ("Metallica Metals Files NI 43-101 Technical Report and Earns 100% Interest in the Starr Gold-Silver Project",
     "The adjacent Moss Lake gold deposit hosts an Indicated Mineral Resource of 39,797,000 tonnes grading 1.1 g/t "
     "Au for 1,377,300 contained ounces of gold and an Inferred Mineral Resource of 50,364,000 tonnes grading 1.1 "
     "g/t Au for 1,751,600 contained ounces of gold, and is currently under care and maintenance (source: NI 43-101 Tec"),
    ("GoldMining Updates Mineral Resource Estimate with Inclusion of Antimony at its Crucero Gold Project, Peru",
     "*For comparison, the previous MRE (Effective Date \nDecember 20, 2017\n) comprised 30.6 Mt at 1.0 g/t Au for "
     "0.99 Moz Au Indicated resources, and 35.8 Mt at\n1.0 g/t Au for 1.1 Moz Au Inferred resources, at a gold "
     "price of \n$1,500\n per ounce and a 0.40 g/t Au cut-"),
    ("White Gold Corp. Files Technical Report Demonstrating Significant 44% Increase in Indicated Resources",
     "Western Copper and Gold Corporation\u2019s (TSX: WRN, NYSE: WRN),  Casino project which has Measured \nand "
     "Indicated Resources of 2,490.7 Mt grading 0.18 g/t Au, 0.14% Cu for 14.8 million ounces of gold and \n7.6 "
     "billion pounds of copper, and Inferred Resources of 1.4 Mt grading 0.14 g/t Au, 0.14% Cu for 6.3 \nmillion "
     "ounces of gold and"),
    # drill-result headline quoting the standing resource: Format E does not run
    ("Carlyle Intercepts 689 Metres of 0.51 G/T Gold at Newton Project, British Columbia",
     "The inferred mineral resource contains 861,400 oz of Au, and 4,678,000 oz of Ag with an average grade of "
     "0.63 g/t Au, a cut off of 0.25 g/t Au throughout 42,396,600 tonnes."),
    # the handover's "773,000 oz (21,310,000 tonnes at 1.13 g/t)" example is itself historical
    ("McFarlane Comments on Its Proposed Acquisition of One of Ontario\u2019s Largest Undeveloped Gold Projects",
     "Juby Gold Project Highlights \u2013\n\n2020 Historical Indicated mineral resource of 773,000 oz of gold in "
     "21,310,000 tonnes with an average grade of 1.13 g/t gold"),
]


def self_test(verbose: bool = True) -> int:
    bad = 0
    for hl, body, want in EXTRACT_TEST:
        got = extract_resources(hl, body).get("categories") or {}
        cats = {c.get("category") for c in got.values()}
        ok = want in cats
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  extract {sorted(cats)!s:<26} (wanted {want}) | {hl[:42]}")
    for hl, body in REJECT_TEST + REJECT_TEST_V33:
        got = extract_resources(hl, body).get("categories") or {}
        ok = not got
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  reject  {hl[:62]}  {[fmt_category_line(c) for c in got.values()] if got else ''}")
    for hl, body, cat, metal, tonnes, grade in FIELD_TEST:
        got = (extract_resources(hl, body).get("categories") or {}).get((cat, metal))
        if tonnes is None:
            ok = not got or abs(got["tonnes"] - grade) > 1
        else:
            ok = bool(got) and abs(got["tonnes"] - tonnes) < 1 and abs(got["grade"] - grade) < 1e-9
        bad += not ok
        if verbose or not ok:
            shown = fmt_category_line(got) if got else None
            print(f"  {'ok  ' if ok else 'FAIL'}  field   {cat}/{metal} -> {shown} | {hl[:40]}")
    for hl, want in PROJECT_TEST:
        got = find_project(hl, "")
        ok = got == want
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  project {str(got)!r:<22} (wanted {want!r})")
    total = len(EXTRACT_TEST) + len(REJECT_TEST) + len(REJECT_TEST_V33) + len(FIELD_TEST) + len(PROJECT_TEST)
    if verbose:
        print(f"\n{total - bad}/{total} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    import sys as _s
    _s.exit(self_test())
