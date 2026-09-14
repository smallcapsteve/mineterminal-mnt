"""resource_extract.py v2 — multi-format MRE extractor.

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
    r"AuEq|CuEq|NiEq|ZnEq|U3O8|REE|LCE|Au|Ag|Cu|Ni|Zn|Pb|Co|U|Mn|V|Li|W|Mo|Sb|Sn|Pt|Pd|"
    r"gold|silver|copper|nickel|zinc|lead|cobalt|uranium|molybdenum|manganese|"
    r"vanadium|lithium|tungsten|tin|antimony|platinum|palladium|"
    r"gold\s+equivalent|copper\s+equivalent|lithium\s+carbonate\s+equivalent"
)

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
    r"(?P<tonnage>\d+(?:[.,]\d+)?)\s*"
    r"(?P<tunit>Mt|Million\s+tonnes?|kt|thousand\s+tonnes?|t\b|tonnes?)"
    # connector: "at | @ | of | grading | with [.. words ..] of | with grades of"
    r"(?:.{0,80}?(?:at|@|grading|of|with(?:\s+grades)?\s+of)\s*)"
    r"(?P<grade>\d+(?:\.\d+)?)\s*"
    r"(?P<gunit>g/t|gpt|g/tonne|grams?\s*/\s*t(?:onne)?|grams?\s+per\s+tonne|%|ppm)\s*"
    rf"(?P<metal>{_METAL_TOKEN})\b",
    re.I | re.S,
)


# ---------- Format C: <tonnage> <unit> @ <grade> <unit> <metal> for <count> <category> ----------

_RE_C = re.compile(
    r"(?P<tonnage>\d+(?:[.,]\d+)?)\s*"
    r"(?P<tunit>Mt|Million\s+tonnes?|kt|thousand\s+tonnes?|t\b|tonnes?)\s*"
    r"(?:@|at|grading)\s*"
    r"(?P<grade>\d+(?:\.\d+)?)\s*"
    r"(?P<gunit>g/t|gpt|g/tonne|grams?\s*/\s*t(?:onne)?|grams?\s+per\s+tonne|%|ppm)\s*"
    rf"(?P<metal>{_METAL_TOKEN})\b\s+"
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
    r"(?P<count>\d+(?:[.,]\d+)?)\s*"
    r"(?:million|thousand)?\s*"
    rf"(?P<cat>{_CAT_TOKEN})"
    r"\s+(?:ounces|oz|tonnes|t\b)\s+"
    r"(?:of\s+)?"
    rf"(?P<metal>{_METAL_TOKEN})\b\s*"
    r"(?:at|@)\s*"
    r"(?P<grade>\d+(?:\.\d+)?)\s*"
    r"(?P<gunit>g/t|gpt|g/tonne|grams?\s*/\s*t(?:onne)?|grams?\s+per\s+tonne|%|ppm)"
    # the contained ounces can BE the headline number, with no tonnage stated
    r"(?:\s+(?:contained\s+in\s+)?"
    r"(?P<tonnage>\d+(?:[.,]\d+)?)\s*"
    r"(?P<tunit>Mt|Million\s+tonnes?|kt|thousand\s+tonnes?|t\b|tonnes?)?)?",
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

def _norm_metal(s: str) -> str:
    s = (s or "").strip().lower()
    if s in _NAME_TO_SYMBOL:
        return _NAME_TO_SYMBOL[s]
    if s in ("aueq", "cueq", "nieq", "zneq", "u3o8", "ree", "lce"):
        return {"aueq": "AuEq", "cueq": "CuEq", "nieq": "NiEq",
                "zneq": "ZnEq", "u3o8": "U3O8", "ree": "REE", "lce": "LCE"}[s]
    return s.title() if len(s) <= 3 else s


def _norm_cat(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return {
        "measured":               "Measured",
        "indicated":              "Indicated",
        "inferred":               "Inferred",
        "measured and indicated": "M&I",
        "measured & indicated":   "M&I",
        "measured + indicated":   "M&I",
        "m&i":                    "M&I",
        "m+i":                    "M&I",
        "total":                  "Total",
        "combined":               "Total",
    }.get(s, s.title())


def _to_tonnes(amt: float, unit: str) -> float:
    u = (unit or "").lower().strip()
    if u in ("mt", "million tonnes", "million tonne"):
        return amt * 1_000_000
    if u in ("kt", "thousand tonnes", "thousand tonne"):
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


# ---------- gate + extractor ----------

# ---------- Format D: tonnage-first then category, e.g.
#   "3,299 thousand tonnes (\"kt\") Measured and Indicated grading 1.28% nickel"
#   "132 kt Inferred grading 0.93% nickel"
_RE_D = re.compile(
    r"(?P<tonnage>[\d,]+(?:\.\d+)?)\s*"
    r"(?P<tunit>Mt|Million\s+tonnes?|kt|thousand\s+tonnes?|t\b|tonnes?)"
    # narrow gap: optional whitespace, optional parenthetical like ("kt"), optional quotes
    r"(?:\s*\([^)]{0,20}\))?\s*[\"\'\s]{0,5}"
    rf"(?P<cat>{_CAT_TOKEN})"
    r"\s+(?:grading|grades?\s+of|with\s+grades?\s+of|at|@)\s+"
    r"(?P<grade>\d+(?:\.\d+)?)\s*"
    r"(?P<gunit>g/t|gpt|g/tonne|grams?\s*/\s*t(?:onne)?|grams?\s+per\s+tonne|%|ppm)\s*"
    rf"(?P<metal>{_METAL_TOKEN})\b",
    re.I | re.S,
)


def is_real_mre(headline: str, body: str) -> bool:
    h = headline or ""
    if _SKIP_HEADLINE_RE.search(h):
        return False
    text = h + "\n" + (body or "")
    return bool(_RE_A.search(text) or _RE_C.search(text) or _RE_B2.search(text) or _RE_D.search(text))


def extract_resources(headline: str, body: str) -> dict:
    if not is_real_mre(headline, body):
        return {"categories": {}, "mre_type": None}

    text = (headline or "") + "\n\n" + (body or "")[:8000]
    by_cat: dict[tuple[str, str], dict] = {}

    # Format A/B (cat-first)
    for m in _RE_A.finditer(text):
        if _quoted_historical(text, m):
            continue
        try:
            tonnage = float(m.group("tonnage").replace(",", ""))
            grade = float(m.group("grade"))
        except (ValueError, IndexError):
            continue
        cat = _norm_cat(m.group("cat"))
        tunit = m.group("tunit").lower()
        gunit = m.group("gunit").lower().replace("gpt", "g/t")
        metal = _norm_metal(m.group("metal"))
        tonnes = _to_tonnes(tonnage, tunit)
        if tonnes < 1_000 or tonnes > 10_000_000_000:
            continue
        key = (cat, metal)
        if key in by_cat:
            continue
        contained_oz = contained_t = contained_lb = None
        if gunit == "g/t":
            if metal in ("Au", "Ag", "AuEq"):
                contained_oz = tonnes * grade / 31.1035
        elif gunit == "%":
            contained_t = tonnes * grade / 100
            if metal in ("Cu", "Ni", "Zn", "Pb"):
                contained_lb = contained_t * 2204.62
        elif gunit == "ppm":
            contained_t = tonnes * grade / 1_000_000
        by_cat[key] = {
            "category": cat, "metal": metal,
            "tonnes": tonnes, "grade": grade, "grade_unit": gunit,
            "contained_oz": contained_oz, "contained_t": contained_t, "contained_lb": contained_lb,
        }

    # Format C (tonnage-first, category trailing)
    for m in _RE_C.finditer(text):
        if _quoted_historical(text, m):
            continue
        try:
            tonnage = float(m.group("tonnage").replace(",", ""))
            grade = float(m.group("grade"))
        except (ValueError, IndexError):
            continue
        cat = _norm_cat(m.group("cat"))
        tunit = m.group("tunit").lower()
        gunit = m.group("gunit").lower().replace("gpt", "g/t")
        metal = _norm_metal(m.group("metal"))
        tonnes = _to_tonnes(tonnage, tunit)
        if tonnes < 1_000 or tonnes > 10_000_000_000:
            continue
        key = (cat, metal)
        if key in by_cat:
            continue
        contained_oz = contained_t = contained_lb = None
        if gunit == "g/t":
            if metal in ("Au", "Ag", "AuEq"):
                contained_oz = tonnes * grade / 31.1035
        elif gunit == "%":
            contained_t = tonnes * grade / 100
        elif gunit == "ppm":
            contained_t = tonnes * grade / 1_000_000
        by_cat[key] = {
            "category": cat, "metal": metal,
            "tonnes": tonnes, "grade": grade, "grade_unit": gunit,
            "contained_oz": contained_oz, "contained_t": contained_t, "contained_lb": contained_lb,
        }

    # Format D (inverted: tonnage UNIT [parenthetical] CATEGORY grading GRADE UNIT METAL)
    for m in _RE_D.finditer(text):
        if _quoted_historical(text, m):
            continue
        try:
            tonnage = float(m.group("tonnage").replace(",", ""))
            grade = float(m.group("grade"))
        except (ValueError, IndexError):
            continue
        cat = _norm_cat(m.group("cat"))
        tunit = m.group("tunit").lower()
        gunit = m.group("gunit").lower().replace("gpt", "g/t")
        metal = _norm_metal(m.group("metal"))
        tonnes = _to_tonnes(tonnage, tunit)
        if tonnes < 1_000 or tonnes > 10_000_000_000:
            continue
        key = (cat, metal)
        if key in by_cat:
            continue
        contained_oz = contained_t = contained_lb = None
        if gunit == "g/t":
            if metal in ("Au", "Ag", "AuEq"):
                contained_oz = tonnes * grade / 31.1035
        elif gunit == "%":
            contained_t = tonnes * grade / 100
            if metal in ("Cu", "Ni", "Zn", "Pb"):
                contained_lb = contained_t * 2204.62
        elif gunit == "ppm":
            contained_t = tonnes * grade / 1_000_000
        by_cat[key] = {
            "category": cat, "metal": metal,
            "tonnes": tonnes, "grade": grade, "grade_unit": gunit,
            "contained_oz": contained_oz, "contained_t": contained_t, "contained_lb": contained_lb,
        }

    # Format B2 (count million ounces of gold at grade contained in tonnage)
    for m in _RE_B2.finditer(text):
        if _quoted_historical(text, m):
            continue
        try:
            count = float(m.group("count").replace(",", ""))
            grade = float(m.group("grade"))
            tonnage = float(m.group("tonnage").replace(",", "")) if m.group("tonnage") else None
            tunit = m.group("tunit") if m.group("tunit") else None
        except (ValueError, IndexError):
            continue
        cat = _norm_cat(m.group("cat"))
        metal = _norm_metal(m.group("metal"))
        gunit = m.group("gunit").lower().replace("gpt", "g/t")
        # If "million" appears before/after count, scale up
        full_match = m.group(0)
        is_million = bool(re.search(r"\bmillion\b", full_match[:60], re.I))
        oz_count = count * (1_000_000 if is_million else 1)
        tonnes = _to_tonnes(tonnage, tunit) if tonnage else None
        if tonnes and (tonnes < 1_000 or tonnes > 10_000_000_000):
            continue
        key = (cat, metal)
        if key in by_cat:
            continue
        contained_oz = oz_count if metal in ("Au", "Ag", "AuEq") else None
        contained_t = oz_count if metal in ("Sb", "Cu", "Ni", "Zn", "Pb") else None
        by_cat[key] = {
            "category": cat, "metal": metal,
            "tonnes": tonnes or 0, "grade": grade, "grade_unit": gunit,
            "contained_oz": contained_oz, "contained_t": contained_t, "contained_lb": None,
        }

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


def self_test(verbose: bool = True) -> int:
    bad = 0
    for hl, body, want in EXTRACT_TEST:
        got = extract_resources(hl, body).get("categories") or {}
        cats = {c.get("category") for c in got.values()}
        ok = want in cats
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  extract {sorted(cats)!s:<26} (wanted {want}) | {hl[:42]}")
    for hl, body in REJECT_TEST:
        got = extract_resources(hl, body).get("categories") or {}
        ok = not got
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  reject  {hl[:62]}")
    for hl, want in PROJECT_TEST:
        got = find_project(hl, "")
        ok = got == want
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  project {str(got)!r:<22} (wanted {want!r})")
    total = len(EXTRACT_TEST) + len(REJECT_TEST) + len(PROJECT_TEST)
    if verbose:
        print(f"\n{total - bad}/{total} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    import sys as _s
    _s.exit(self_test())
