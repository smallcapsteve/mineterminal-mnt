"""Shared normalisers for MNT extractors (NORMALIZE_V1, 2026-09-16). Step 1d of the
revised plan (claude/MNT_INGESTION_PIPELINE_PLAN_REVISED_2026-09-16.md).

Consolidation, not invention. Every rule here already existed in one of the
extractors, usually in a slightly different form in each:

  metals, equivalents, oxides, families  drill_extract (_NAME_TO_SYMBOL, _CANON,
                                         _FAMILY, _normalize_metal) + resource_extract
                                         (_NAME_TO_SYMBOL, _SPECIAL_METALS, _EQ_BASE)
  grade units, ppm scale, plausibility   drill_extract (_UNIT_NEW, _TO_PPM, _plausible)
                                         + resource_extract (_grade_ok)
  tonnes, ounces, contained metal        resource_extract (_to_tonnes, _to_oz, _entry)
  PDF-damage repair                      drill_extract._prep + resource_extract._prep
  numbers, magnitudes, money, currency   drill/resource _num, resource _mult,
                                         financing_extract (read_amount, _cur_code)
  resource categories, dates             resource_extract._norm_cat, financing_extract._parse_date

Where the extractors disagreed, the choice made is written next to the rule.
The four existing extractors do NOT import this module yet (plan, change 3);
new extractors (step 4 onwards) must. The bug class this exists to end:
CuEq stored as Cu, Li2O as Li, U3O8 as U (resource_extract v3.3.1, 2026-09-16).

Pure functions, standard library only. Self-tests: python3 -m portal.normalize
"""
from __future__ import annotations

import re
from datetime import datetime

# ============================================================== metals

# Plain names -> symbols. Union of drill_extract and resource_extract.
METAL_NAMES = {
    "gold": "Au", "silver": "Ag", "copper": "Cu", "nickel": "Ni", "zinc": "Zn",
    "lead": "Pb", "cobalt": "Co", "uranium": "U", "molybdenum": "Mo",
    "manganese": "Mn", "vanadium": "V", "lithium": "Li", "tungsten": "W",
    "tin": "Sn", "antimony": "Sb", "platinum": "Pt", "palladium": "Pd",
    "rhodium": "Rh", "ruthenium": "Ru", "iridium": "Ir", "osmium": "Os",
    "chromium": "Cr", "cesium": "Cs", "caesium": "Cs", "rubidium": "Rb",
    "scandium": "Sc", "gallium": "Ga", "germanium": "Ge", "tellurium": "Te",
    "bismuth": "Bi", "niobium": "Nb", "tantalum": "Ta", "titanium": "Ti",
    # "iron" is deliberately absent: neither extractor had it, and in these releases it is
    # geology ("banded iron formation"), not a grade (566 false tokens in the 1d check).
    "graphite": "Cg", "graphitic carbon": "Cg",
    "total copper": "Cu",
    "lithium oxide": "Li2O", "cesium oxide": "Cs2O", "caesium oxide": "Cs2O",
    "tungsten trioxide": "WO3", "lithium carbonate equivalent": "LCE",
    "total rare earth": "TREO", "total rare earth oxide": "TREO", "total rare earth oxides": "TREO",
}

# Element symbols matched case-sensitively in prose, so "as", "in", "v" are never metals.
SYMBOLS = ("Au", "Ag", "Cu", "Ni", "Zn", "Pb", "Co", "Mo", "Sb", "Sn", "Pt", "Pd", "Rh",
           "Ru", "Ir", "Cg", "Mn", "Li", "Ga", "Ge", "Sc", "Te", "Bi", "Cs", "Rb",
           "Cr", "Nb", "Ta", "Ti", "Fe", "W", "V", "U")
# Choice: K and P are not matched as bare symbols ("750K", "2P reserves"); potassium
# and phosphorus arrive as KCl, K2O or P2O5, which are in COMPOUNDS.

# Compounds, aggregates and aliases, keyed lower-case. drill_extract._CANON plus
# resource_extract's LCE. CuT / TCu are total copper, reported as Cu (drill rule).
COMPOUNDS = {
    "u3o8": "U3O8", "eu3o8": "eU3O8", "li2o": "Li2O", "ta2o5": "Ta2O5", "nb2o5": "Nb2O5",
    "v2o5": "V2O5", "wo3": "WO3", "mos2": "MoS2", "cs2o": "Cs2O", "rb2o": "Rb2O",
    "sc2o3": "Sc2O3", "p2o5": "P2O5", "fe2o3": "Fe2O3", "tio2": "TiO2", "cr2o3": "Cr2O3",
    "ga2o3": "Ga2O3", "k2o": "K2O", "kcl": "KCl", "coo": "CoO", "mno": "MnO", "sno2": "SnO2",
    "treo": "TREO", "treos": "TREO", "reo": "REO", "reos": "REO", "ree": "REE", "rees": "REE",
    "tree": "TREE", "trees": "TREE", "mreo": "MREO", "hreo": "HREO", "lreo": "LREO",
    "ndpr": "NdPr", "pge": "PGE", "pges": "PGE", "pgm": "PGM", "pgms": "PGM", "2pge": "2PGE",
    "3e": "3E", "lce": "LCE", "cut": "Cu", "tcu": "Cu", "cg": "Cg",
}

# Metals an "equivalent" can be expressed in. drill_extract's list (the wider one);
# resource_extract only knew Au, Ag, Cu, Ni, Zn.
EQUIVALENT_BASES = ("Au", "Ag", "Cu", "Ni", "Zn", "Pb", "Sn", "Pd", "Pt", "Mo", "W", "U3O8", "Li2O")

FAMILY = {
    "U3O8": "U", "eU3O8": "U", "Li2O": "Li", "LCE": "Li", "WO3": "W", "Cs2O": "Cs", "Rb2O": "Rb",
    "Nb2O5": "Nb", "Ta2O5": "Ta", "V2O5": "V", "Fe2O3": "Fe", "TiO2": "Ti", "P2O5": "P",
    "MoS2": "Mo", "Sc2O3": "Sc", "Ga2O3": "Ga", "Cr2O3": "Cr", "SnO2": "Sn", "CoO": "Co",
    "MnO": "Mn", "KCl": "K", "K2O": "K", "TREO": "REE", "REO": "REE", "MREO": "REE",
    "HREO": "REE", "LREO": "REE", "TREE": "REE", "NdPr": "REE", "Cg": "C",
    "PGE": "PGE", "PGM": "PGE", "2PGE": "PGE", "3E": "PGE", "Pt": "PGE", "Pd": "PGE",
    "Rh": "PGE", "Ru": "PGE", "Ir": "PGE", "Os": "PGE",
}

_SYM_BY_LOWER = {s.lower(): s for s in SYMBOLS}
_EQ_BY_LOWER = {b.lower(): b for b in EQUIVALENT_BASES}
_RE_EQ_TAIL = re.compile(r"^(?P<base>.+?)[ .]*eq(?:uiv(?:alent)?)?$")


def _canon_one(token):
    """One metal token -> canonical symbol, or None if it is not a metal we know.

    Choice: unknown tokens return None. drill_extract title-cased them and
    resource_extract returned them lower-case, so both stored junk like "Total"
    or "graphite"; a new extractor should drop what it cannot name."""
    s = re.sub(r"[\s\-]+", " ", (token or "").strip()).rstrip(".").strip()
    if not s:
        return None
    low = s.lower()
    if low in METAL_NAMES and not METAL_NAMES[low].endswith("Eq"):
        return METAL_NAMES[low]
    m = _RE_EQ_TAIL.match(low)
    if m and m.group("base").strip() not in ("lithium carbonate",):
        base = m.group("base").strip()
        base = METAL_NAMES.get(base, base)
        base = _EQ_BY_LOWER.get(base.lower())
        if base:
            return base + "Eq"
        return None
    if low in COMPOUNDS:
        return COMPOUNDS[low]
    if low.replace(" ", "") in COMPOUNDS:
        return COMPOUNDS[low.replace(" ", "")]
    if s in SYMBOLS:
        return s
    if len(s) <= 2 and low in _SYM_BY_LOWER:
        # "AU", "au" as a token already isolated by a pattern
        return _SYM_BY_LOWER[low]
    if low.endswith("eq") and low[:-2] in _EQ_BY_LOWER:
        return _EQ_BY_LOWER[low[:-2]] + "Eq"
    return None


def metals(token):
    """A metal token that may name several: "Au+Ag", "Cu/Au", "Cu-Au" -> ["Au", "Ag"] ...
    An equivalent written with a hyphen ("gold-equivalent", "Au-Eq") stays one token.
    Returns [] if any part is not a known metal."""
    raw = (token or "").strip()
    if not raw:
        return []
    if re.search(r"(?i)[\s\-.]eq", raw) or re.search(r"(?i)equivalent", raw):
        one = _canon_one(raw)
        return [one] if one else []
    whole = _canon_one(raw)
    if whole:
        # a hyphenated name is one metal, not a pair: "total rare-earth" (the
        # differential check found drill_extract storing it as "TOTAL RARE+EARTH")
        return [whole]
    parts = [p for p in re.split(r"\s*[+/\-]\s*|\s+and\s+", raw) if p]
    out = [_canon_one(p) for p in parts]
    return out if out and all(out) else []


def metal(token):
    """Exactly one canonical metal, or None (unknown, or a combination)."""
    got = metals(token)
    return got[0] if len(got) == 1 else None


def is_equivalent(sym):
    return bool(sym) and sym.endswith("Eq") and sym[:-2] in EQUIVALENT_BASES


def family(sym):
    """Au, AuEq and Au+Ag are one family; so are U, U3O8 and eU3O8 (drill_extract._family)."""
    m = (sym or "").split("+")[0]
    if m.endswith("Eq"):
        m = m[:-2]
    return FAMILY.get(m, m)


def _alt(words):
    return "|".join(sorted(words, key=len, reverse=True))


_EQ_ALT = r"(?:" + _alt([re.escape(b) for b in EQUIVALENT_BASES]
                        + [n for n, s in METAL_NAMES.items() if s in EQUIVALENT_BASES and " " not in n]) \
          + r")[\s.\-]*eq(?:uiv(?:alent)?)?\.?"
_NAME_ALT = _alt([n.replace(" ", r"[\s\-]+") for n in METAL_NAMES])
_COMPOUND_ALT = _alt([v for v in set(COMPOUNDS.values()) if v not in SYMBOLS] + ["CuT", "TCu", "eU3O8"]
                     + ["PGEs", "PGMs", "REEs", "REOs", "TREEs", "TREOs"])
_SYMBOL_ALT = _alt(SYMBOLS)

# One pattern for a metal token in prose. Order matters and is the v3.3 lesson:
# equivalents before names before symbols, so "copper equivalent" is never read as
# "copper", and "copper" never as "Co". Names and equivalents are case-insensitive;
# symbols and compounds are case-sensitive; every alternative ends at a non-letter.
METAL_PATTERN = (r"(?<![A-Za-z])(?:(?i:" + _EQ_ALT + r")|(?i:" + _NAME_ALT + r")|(?:"
                 + _COMPOUND_ALT + r")|(?:" + _SYMBOL_ALT + r"))(?![A-Za-z])")
METAL_RX = re.compile(METAL_PATTERN)


# ============================================================== text repair

_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SPACES = {0x00a0: " ", 0x202f: " ", 0x2009: " ", 0x2011: "-"}
_RE_SPACED_OXIDE = re.compile(
    r"\b(?:eU\s*3\s*O\s*8|U\s*3\s*O\s*8|Li\s*2\s*O(?![a-z])|WO\s+3|Cs\s+2\s*O|Rb\s+2\s*O|V\s+2\s*O\s*5"
    r"|Nb\s+2\s*O\s*5|Ta\s+2\s*O\s*5|P\s*2\s*O\s*5|Sc\s+2\s*O\s*3|Fe\s+2\s*O\s*3|TiO\s+2)\b")
_RE_SPELLED_GPT = re.compile(r"(?i)\bgrams?\s*(?:per|/)\s*(?:metric\s+)?tonnes?\b")
_RE_SPELLED_PPM = re.compile(r"(?i)\bparts\s+per\s+million\b(?:\s*\(\s*[“\"]?ppm[”\"]?\s*\))?")
_RE_SPELLED_PPB = re.compile(r"(?i)\bparts\s+per\s+billion\b(?:\s*\(\s*[“\"]?ppb[”\"]?\s*\))?")
_RE_SPELLED_OPT = re.compile(r"(?i)\b(?:ounces?|oz)\s*(?:per|/)\s*(?:short\s+)?ton\b")
_RE_BARE_GRAMS = re.compile(r"(?i)(?<=\d)\s*grams?(?=\s+(?:Au|gold)\b)")
# Choice: a decimal split by a PDF space is rejoined only when a unit follows.
# drill_extract rejoined every "digit. digit", which also joins "Figure 2. 5 holes".
_RE_SPLIT_DECIMAL = re.compile(
    r"(?<![\d.,])(\d{1,4})\. (\d{1,4})(?=\s*(?:g/t|gpt|%|ppm|ppb|oz|grams?|m\b|metres?|meters?|Mt\b|kt\b|million))")


def prep_text(text):
    """Undo PDF-to-text damage that hides metals and grades, and spell units one way.
    Length-preserving it is not: run extraction on the prepared text, then map
    spans back with a separate find on the original if a span is needed."""
    t = (text or "").translate(_SUBSCRIPTS).translate(_SPACES)
    t = _RE_SPACED_OXIDE.sub(lambda m: re.sub(r"\s+", "", m.group(0)), t)
    t = re.sub(r"(\d)M\s+million\b", r"\1 million", t)
    t = _RE_SPLIT_DECIMAL.sub(r"\1.\2", t)
    t = _RE_SPELLED_GPT.sub("g/t", t)
    t = _RE_SPELLED_OPT.sub("oz/t", t)
    t = _RE_SPELLED_PPM.sub("ppm", t)
    t = _RE_SPELLED_PPB.sub("ppb", t)
    t = _RE_BARE_GRAMS.sub(" g/t", t)
    return t


# ============================================================== numbers

# As printed: grouped ("21,310,000") or plain, optional decimals, or a leading-dot
# decimal (".95"). Never starts inside another number; never ends before ",4", so a
# European decimal comma ("5,46") does not match at all rather than reading as 546.
NUMBER_PATTERN = r"(?<![\d.,])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?!\d|,\d)"
_RE_NUMBER_FULL = re.compile(r"^(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)$")

MAGNITUDES = {"thousand": 1e3, "k": 1e3, "million": 1e6, "mm": 1e6, "mln": 1e6, "m": 1e6,
              "billion": 1e9, "bn": 1e9, "b": 1e9}


def number(s):
    """"1,234.5" -> 1234.5, ".95" -> 0.95. None for anything else, including "5,46"."""
    s = (s or "").strip()
    if not _RE_NUMBER_FULL.match(s):
        return None
    return float(("0" + s) if s.startswith(".") else s.replace(",", ""))


def magnitude(word):
    """"million", "M", "mm", "bn", "k" ... -> multiplier; 1.0 for none; None if unrecognised."""
    if word is None or not str(word).strip():
        return 1.0
    return MAGNITUDES.get(str(word).strip().lower().rstrip("."))


def percent(s):
    """"31%", "31 %", "31.5 percent" -> 31.5 (the number, not a fraction)."""
    m = re.fullmatch(r"\s*(" + NUMBER_PATTERN + r")\s*(?:%|per\s*cent|percent)\s*", s or "", re.I)
    return number(m.group(1)) if m else None


# ============================================================== grades

GRADE_UNITS = {
    "g/t": "g/t", "gpt": "g/t", "g/tonne": "g/t", "g / t": "g/t", "gms": "g/t", "gm/t": "g/t",
    "%": "%", "percent": "%", "pct": "%",
    "ppm": "ppm", "ppb": "ppb",
    "oz/t": "oz/t", "opt": "oz/t", "oz/ton": "oz/t", "oz/st": "oz/t",
    "kg/t": "kg/t",
}
GRADE_UNIT_PATTERN = r"(?:g/tonne|g\s*/\s*t|gpt|gms(?![A-Za-z])|%|ppm|ppb|oz/ton|oz/t|opt(?![A-Za-z])|kg/t)"

# grade expressed in ppm (= g/t) so grades in different units compare (drill _TO_PPM)
TO_PPM = {"g/t": 1.0, "ppm": 1.0, "ppb": 0.001, "%": 10000.0, "oz/t": 34.2857, "kg/t": 1000.0}

# Plausibility caps. Two contexts because the extractors legitimately differ: a
# single intercept can be spectacular (drill_extract), a resource grade is an
# average over millions of tonnes (resource_extract).
_CAPS = {
    "intercept": {"%": 100.0, "g/t": 20000.0, "ppm": 100000.0, "ppb": 1000000.0, "oz/t": 600.0, "kg/t": 50.0},
    "resource": {"%": 100.0, "g/t": 5000.0, "ppm": 1000000.0},
}
_SILVER_CAPS = {"g/t": 100000.0, "oz/t": 3000.0}     # Kuya 74,418 g/t Ag was real
_PCT_CAPS = {"Au": 5.0, "Ag": 20.0, "Pt": 5.0, "Pd": 5.0, "U": 30.0}  # "gold at 90%" is a recovery


def grade_unit(token):
    s = re.sub(r"\s+", " ", (token or "").strip().lower())
    if s in GRADE_UNITS:
        return GRADE_UNITS[s]
    if re.fullmatch(r"grams? (?:per|/) (?:metric )?tonnes?", s):
        return "g/t"
    if re.fullmatch(r"(?:ounces?|oz) (?:per|/) (?:short )?ton", s):
        return "oz/t"
    return GRADE_UNITS.get(s.replace(" ", ""))


def grade_to_ppm(value, unit):
    f = TO_PPM.get(unit)
    return None if f is None or value is None else value * f


def plausible_grade(value, unit, metal_sym=None, context="intercept", named=True):
    """False when a grade cannot be what it claims. named=False means the metal was
    inferred, not written, so the silver allowance does not apply (drill rule)."""
    if value is None or value <= 0:
        return False
    caps = _CAPS[context]
    cap = caps.get(unit)
    m = (metal_sym or "").split("+")[0]
    if context == "intercept" and named and m in ("Ag", "AgEq") and unit in _SILVER_CAPS:
        cap = _SILVER_CAPS[unit]
    if cap is not None and value > cap:
        return False
    if context == "intercept" and unit == "%" and m in _PCT_CAPS and value > _PCT_CAPS[m]:
        return False
    return True


def length_m(value, unit):
    """Metres; feet converted (0.3048). None for an unknown unit."""
    u = (unit or "m").strip().lower()
    if u in ("m", "metre", "metres", "meter", "meters"):
        return value
    if u in ("ft", "foot", "feet"):
        return value * 0.3048
    return None


# ============================================================== quantities

TROY_OZ_G = 31.1035
LB_PER_T = 2204.62
SHORT_TON_T = 0.90718474


def tonnes(value, unit):
    """t, tonnes, kt, thousand tonnes, Mt, M tonnes, million tonnes, billion tonnes.
    Choice: "short tons" convert; a bare "tons" is ambiguous in these releases and
    returns None rather than a guess."""
    u = re.sub(r"\s+", " ", (unit or "").strip().lower()).replace("metric ", "")
    if value is None:
        return None
    if u in ("t", "tonne", "tonnes"):
        return value
    if u in ("kt", "k t", "thousand tonnes", "thousand tonne", "thousand t"):
        return value * 1e3
    if u in ("mt", "m t", "m tonnes", "m tonne", "million tonnes", "million tonne", "million t"):
        return value * 1e6
    if u in ("bt", "billion tonnes", "billion tonne", "billion t"):
        return value * 1e9
    if u in ("short ton", "short tons"):
        return value * SHORT_TON_T
    return None


def ounces(value, unit):
    """oz, ounces, troy ounces, koz, thousand ounces, Moz, million ounces."""
    u = re.sub(r"\s+", " ", (unit or "").strip().lower()).replace("troy ", "")
    if value is None:
        return None
    if u in ("oz", "ounce", "ounces"):
        return value
    if u in ("koz", "thousand oz", "thousand ounces"):
        return value * 1e3
    if u in ("moz", "mozs", "million oz", "million ounces"):
        return value * 1e6
    return None


def pounds(value, unit):
    """lb, lbs, pounds, Mlb, million pounds, Blb, billion pounds."""
    u = re.sub(r"\s+", " ", (unit or "").strip().lower()).rstrip(".")
    if value is None:
        return None
    if u in ("lb", "lbs", "pound", "pounds"):
        return value
    if u in ("mlb", "mlbs", "million lb", "million lbs", "million pounds"):
        return value * 1e6
    if u in ("blb", "blbs", "billion lb", "billion lbs", "billion pounds"):
        return value * 1e9
    return None


OZ_METALS = ("Au", "Ag", "AuEq", "AgEq", "Pt", "Pd", "PGE", "PGM", "2PGE", "3E")
LB_METALS = ("Cu", "Ni", "Zn", "Pb", "CuEq", "NiEq", "ZnEq", "U3O8", "Mo", "Co")


def contained(tonnage, grade, unit, metal_sym):
    """Contained metal from tonnes and grade: {"oz", "t", "lb"} (None where n/a).

    Consolidated from resource_extract._entry, which only did oz for Au/Ag/AuEq/AgEq
    and lb for Cu/Ni/Zn/Pb. Choice: PGEs report in ounces and U3O8, Mo, Co and the
    base-metal equivalents in pounds, as releases do; the arithmetic is unchanged."""
    out = {"oz": None, "t": None, "lb": None}
    if not tonnage or grade is None:
        return out
    ppm = grade_to_ppm(grade, unit)
    if ppm is None:
        return out
    metal_t = tonnage * ppm / 1e6
    out["t"] = metal_t
    if metal_sym in OZ_METALS:
        out["oz"] = metal_t * 1e6 / TROY_OZ_G
    if metal_sym in LB_METALS:
        out["lb"] = metal_t * LB_PER_T
    return out


# ============================================================== money

CURRENCY_PATTERN = (r"(?P<cur>(?<![A-Za-z])(?:US|U\.S\.|USD|AUD|AU|A|CAD|CDN|CA|C|NZ|HK)\s?\$"
                    r"|(?<![A-Za-z])(?:USD|CAD|CDN|AUD)\s(?=\d)|\$|£|€)")
_RE_NUM_RUN = re.compile(r"\d[\d,. ]{0,18}")
_RE_MAG = re.compile(r"(?i)\s*-?\s*(million|mm\b|mln\b|m\b|billion|bn\b|b\b|thousand|k\b)")
DEFAULT_CURRENCY = "CAD"


def currency(token, default=None):
    """"US$" -> USD, "C$"/"CDN$"/"CAD" -> CAD, "A$" -> AUD, "NZ$", "HK$", "£", "€".
    A bare "$" returns `default` (None unless given): financing_extract treats it as
    the site's Canadian default, but that is a caller's decision, not a parse."""
    if not token:
        return default
    c = token.upper().replace(".", "").replace(" ", "").rstrip("$")
    if token.strip() == "£":
        return "GBP"
    if token.strip() == "€":
        return "EUR"
    if c.startswith("US"):
        return "USD"
    if c.startswith("NZ"):
        return "NZD"
    if c.startswith("HK"):
        return "HKD"
    if c.startswith("A"):
        return "AUD"
    if c.startswith("C"):
        return "CAD"
    return default


def money_at(text, pos):
    """Read a money figure whose first digit is at text[pos] -> (value, end), or
    (None, pos). financing_extract.read_amount, verbatim in behaviour: repairs PDF
    spacing ("$1, 500,000", "$1,250 ,000"), reads "-million", and treats
    "$2,000,000 million" as a typo rather than two trillion dollars."""
    m = _RE_NUM_RUN.match(text, pos)
    if not m:
        return None, pos
    run = m.group(0).rstrip(" ,.")
    first = re.match(r"[\d,.]+", run).group(0).rstrip(",.")
    val = None
    end = pos
    for s in (run.replace(" ", ""), first):
        if re.match(r"^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$", s):
            val = float(s.replace(",", ""))
            end = pos + (len(run) if s != first else len(first))
            break
    if val is None:
        return None, pos
    mg = _RE_MAG.match(text, end)
    if mg:
        u = mg.group(1).lower()
        mult = 1_000_000 if u in ("million", "mm", "mln", "m") else (
            1_000_000_000 if u in ("billion", "bn", "b") else 1_000)
        if not (val >= 100_000 and mult >= 1_000_000):
            val *= mult
        end = mg.end()
    return val, end


_RE_MONEY_ANY = re.compile(CURRENCY_PATTERN + r"\s?(?=\d)")


def find_money(text):
    """Every currency-marked amount: [(value, currency_or_None, start, end)]."""
    out = []
    for m in _RE_MONEY_ANY.finditer(text or ""):
        v, end = money_at(text, m.end())
        if v is not None:
            out.append((v, currency(m.group("cur")), m.start(), end))
    return out


# ============================================================== categories, dates

_CATEGORIES = {
    "measured": "Measured", "indicated": "Indicated", "inferred": "Inferred",
    "measured & indicated": "M&I", "m & i": "M&I", "m&i": "M&I",
    "total": "Total", "combined": "Total",
    "proven": "Proven", "proved": "Proven", "probable": "Probable",
    "proven & probable": "P&P", "proved & probable": "P&P", "p & p": "P&P", "p&p": "P&P",
}


def resource_category(s):
    """resource_extract._norm_cat, plus "proved". None for an unknown category
    (resource_extract title-cased it)."""
    s = (s or "").strip().lower()
    s = re.sub(r"\s*(?:\band\b|&|\+|/)\s*", " & ", s)
    s = re.sub(r"\s+", " ", s).strip().replace("probabl e", "probable")
    return _CATEGORIES.get(s) or _CATEGORIES.get(s.replace(" ", ""))


def parse_date(s):
    """"September 16, 2026", "Sept. 16 2026", "Sep 16, 2026" -> "2026-09-16"; else None.
    financing_extract._parse_date, without its one invalid format string."""
    t = re.sub(r"\bSept\b", "Sep", (s or "").replace(",", " ").replace(".", " "))
    t = re.sub(r"\s+", " ", t).strip()
    for fmt in ("%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# ============================================================== self-tests

def _selftest():
    passed = []

    def eq(name, got, want):
        if got != want:
            raise AssertionError(f"selftest failed: {name}: got {got!r}, want {want!r}")
        passed.append(name)

    # metals: this morning's bug class first
    for tok, want in [("copper equivalent", "CuEq"), ("CuEq", "CuEq"), ("Cu Eq", "CuEq"), ("Cu.Eq", "CuEq"),
                      ("gold-equivalent", "AuEq"), ("AuEq", "AuEq"), ("Au eq.", "AuEq"), ("silver equivalent", "AgEq"),
                      ("U3O8", "U3O8"), ("u3o8", "U3O8"), ("eU3O8", "eU3O8"), ("Li2O", "Li2O"), ("lithium oxide", "Li2O"),
                      ("lithium carbonate equivalent", "LCE"), ("LCE", "LCE"), ("gold", "Au"), ("Gold", "Au"),
                      ("Au", "Au"), ("AU", "Au"), ("copper", "Cu"), ("total copper", "Cu"), ("CuT", "Cu"), ("TCu", "Cu"),
                      ("graphite", "Cg"), ("Cg", "Cg"), ("TREO", "TREO"), ("total rare earth oxides", "TREO"),
                      ("NdPr", "NdPr"), ("WO3", "WO3"), ("Pd", "Pd"), ("U3O8 eq", "U3O8Eq"), ("Li2O Eq", "Li2OEq"),
                      ("molybdenum", "Mo"), ("tin equivalent", "SnEq")]:
        eq("metal " + tok, metal(tok), want)
    for tok in ("Total", "Resources", "in", "as", "iron ore concentrate", "", None, "Kg", "unobtainium equivalent"):
        eq("not a metal " + repr(tok), metal(tok), None)
    eq("pair plus", metals("Au+Ag"), ["Au", "Ag"])
    eq("pair slash", metals("Cu/Au"), ["Cu", "Au"])
    eq("pair hyphen", metals("Cu-Au"), ["Cu", "Au"])
    eq("pair with junk", metals("Au+Total"), [])
    eq("hyphenated name is one metal", metals("total rare-earth"), ["TREO"])
    eq("upper-case stored name", metal("TOTAL RARE EARTH OXIDES"), "TREO")
    eq("pair is not one metal", metal("Au+Ag"), None)
    eq("family AuEq", family("AuEq"), "Au")
    eq("family U3O8", family("U3O8"), "U")
    eq("family LCE", family("LCE"), "Li")
    eq("family Pd", family("Pd"), "PGE")
    eq("is_equivalent", (is_equivalent("CuEq"), is_equivalent("Cu"), is_equivalent("LCE")), (True, False, False))

    def found(text):
        return [m.group(0) for m in METAL_RX.finditer(text)]
    eq("rx equivalent beats name", found("0.39% copper equivalent over 12 m"), ["copper equivalent"])
    eq("rx copper not Co", found("copper and cobalt"), ["copper", "cobalt"])
    eq("rx symbols case-sensitive", found("as in v Au as Ag"), ["Au", "Ag"])
    eq("rx W not with", found("with W and WO3"), ["W", "WO3"])
    eq("rx oxide not U", found("0.25% U3O8 and 2.1% Li2O"), ["U3O8", "Li2O"])
    eq("rx AuEq", found("1.2 g/t AuEq and 3 g/t gold-equivalent"), ["AuEq", "gold-equivalent"])
    eq("rx plural aggregates", found("elevated PGEs and REEs"), ["PGEs", "REEs"])
    eq("rx iron is geology, not a metal", found("banded iron formation"), [])
    eq("metal PGEs", metal("PGEs"), "PGE")
    eq("rx no single-letter K or P", found("$750K raise and a 2P reserve of 12% P2O5"), ["P2O5"])
    eq("rx lead as a verb still matches (inherited)", found("to lead the program"), ["lead"])

    # text repair
    eq("prep subscripts", prep_text("0.85% Li₂O and 770 ppm U₃O₈"), "0.85% Li2O and 770 ppm U3O8")
    eq("prep spaced oxide", prep_text("0.63% U 3 O 8 and 1.1% Li 2 O"), "0.63% U3O8 and 1.1% Li2O")
    eq("prep split decimal with unit", prep_text("0. 96 g/t Au over 25. 5 m"), "0.96 g/t Au over 25.5 m")
    eq("prep split decimal without unit untouched", prep_text("Figure 2. 5 holes"), "Figure 2. 5 holes")
    eq("prep spelled units", prep_text("5 grams per tonne gold, 2 ounces per ton, 40 parts per million (ppm)"),
       "5 g/t gold, 2 oz/t, 40 ppm")
    eq("prep bare grams", prep_text("5.3 Grams Au over 3.8 m"), "5.3 g/t Au over 3.8 m")
    eq("prep M million", prep_text("10.5M million tonnes"), "10.5 million tonnes")
    eq("prep nbsp", prep_text("1.2" + chr(0xa0) + "g/t"), "1.2 g/t")

    # numbers
    eq("number grouped", number("21,310,000"), 21310000.0)
    eq("number decimal", number("1,234.5"), 1234.5)
    eq("number leading dot", number(".95"), 0.95)
    eq("number european comma rejected", number("5,46"), None)
    eq("number junk", number("1.2.3"), None)
    eq("number rx no european", re.findall(NUMBER_PATTERN, "5,46 million tonnes"), [])
    eq("number rx not inside", re.findall(NUMBER_PATTERN, "grade 0.95 and 2,800"), ["0.95", "2,800"])
    eq("magnitude", [magnitude(w) for w in ("million", "M", "bn", "k", None, "gazillion")], [1e6, 1e6, 1e9, 1e3, 1.0, None])
    eq("percent", (percent("31%"), percent("31.5 percent"), percent("x")), (31.0, 31.5, None))

    # grades
    eq("units", [grade_unit(u) for u in ("g/t", "gpt", "G/T", "g/tonne", "grams per tonne", "opt", "oz/ton",
                                          "ounces per ton", "%", "ppm", "ppb", "kg/t", "lbs")],
       ["g/t", "g/t", "g/t", "g/t", "g/t", "oz/t", "oz/t", "oz/t", "%", "ppm", "ppb", "kg/t", None])
    eq("to ppm", (grade_to_ppm(1.0, "%"), grade_to_ppm(1.0, "oz/t"), grade_to_ppm(5, "ppb")), (10000.0, 34.2857, 0.005))
    eq("plausible gold %", plausible_grade(90.0, "%", "Au"), False)
    eq("plausible copper %", plausible_grade(2.5, "%", "Cu"), True)
    eq("plausible silver huge named", plausible_grade(74418.0, "g/t", "Ag"), True)
    eq("plausible silver huge inferred", plausible_grade(74418.0, "g/t", "Ag", named=False), False)
    eq("plausible resource g/t cap", plausible_grade(6000.0, "g/t", "Au", context="resource"), False)
    eq("plausible resource gold % allowed", plausible_grade(6.0, "%", "Au", context="resource"), True)
    eq("plausible zero", plausible_grade(0.0, "g/t", "Au"), False)
    eq("length", (length_m(10.0, "m"), round(length_m(100.0, "ft"), 2), length_m(3.0, "yd")), (10.0, 30.48, None))

    # quantities
    eq("tonnes", [tonnes(1.5, u) for u in ("Mt", "million tonnes", "kt", "t", "billion tonnes", "M tonnes", "tons")],
       [1.5e6, 1.5e6, 1500.0, 1.5, 1.5e9, 1.5e6, None])
    eq("short tons", round(tonnes(1000.0, "short tons"), 2), 907.18)
    eq("ounces", [ounces(2.0, u) for u in ("Moz", "koz", "oz", "troy ounces", "million ounces", "tonnes")],
       [2e6, 2e3, 2.0, 2.0, 2e6, None])
    eq("pounds", [pounds(3.0, u) for u in ("Mlb", "lbs", "billion pounds", "kg")], [3e6, 3.0, 3e9, None])
    c = contained(10_000_000, 1.0, "g/t", "Au")
    eq("contained gold oz", round(c["oz"]), 321507)
    c = contained(10_000_000, 0.5, "%", "Cu")
    eq("contained copper", (round(c["t"]), round(c["lb"])), (50000, 110231000))
    eq("contained CuEq has lb", contained(1_000_000, 1.0, "%", "CuEq")["lb"] is not None, True)
    eq("contained unknown unit", contained(1e6, 1.0, "lbs", "Cu"), {"oz": None, "t": None, "lb": None})

    # money
    eq("currency", [currency(t) for t in ("US$", "U.S.$", "C$", "CDN$", "CAD", "A$", "AUD", "NZ$", "HK$", "£", "€", "$")],
       ["USD", "USD", "CAD", "CAD", "CAD", "AUD", "AUD", "NZD", "HKD", "GBP", "EUR", None])
    eq("currency default", currency("$", default="CAD"), "CAD")
    eq("money million", money_at("$5.5 million", 1)[0], 5_500_000.0)
    eq("money hyphen million", money_at("$5-million", 1)[0], 5_000_000.0)
    eq("money pdf spacing", money_at("$1, 500,000 in", 1)[0], 1_500_000.0)
    eq("money typo guard", money_at("$2,000,000 million", 1)[0], 2_000_000.0)
    eq("money k", money_at("$750k", 1)[0], 750_000.0)
    eq("money not a number", money_at("$abc", 1), (None, 1))
    eq("find money", [(v, cur) for v, cur, s, e in find_money("raising US$8 million and C$3,000,000 at $0.05")],
       [(8e6, "USD"), (3e6, "CAD"), (0.05, None)])
    t = "an after-tax NPV of US$412.5 million"
    fm = find_money(t)[0]
    eq("find money span", t[fm[2]:fm[3]], "US$412.5 million")

    # categories, dates
    eq("categories", [resource_category(s) for s in ("Measured and Indicated", "M&I", "inferred", "Proven + Probable",
                                                       "proved and probable", "Total", "Historic")],
       ["M&I", "M&I", "Inferred", "P&P", "P&P", "Total", None])
    eq("dates", [parse_date(s) for s in ("September 16, 2026", "Sept. 16, 2026", "Sep 16 2026", "16 September 2026",
                                         "2026-09-16", "soon")],
       ["2026-09-16", "2026-09-16", "2026-09-16", "2026-09-16", "2026-09-16", None])
    return passed


if __name__ == "__main__":
    p = _selftest()
    print(f"normalize selftest: {len(p)}/{len(p)} passed")
