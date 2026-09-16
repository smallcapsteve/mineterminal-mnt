"""drill_extract.py - pull structured intercept data from drill release events.

For each event tagged "Drill Results", parse the headline + body for:
  intercepts: list of (length_m, grade, unit, metal)
  top_intercept: the release's headline number (see score_intercept)
  project: e.g. "Tesla Zone", "Begin-Lamarche", "Goose Project"
  sample_type: "drill" | "surface" | None  (flag only; nothing is dropped)

Events with no parseable intercept are SKIPPED (drill plans, program
announcements, etc. - same category but not actual results).

v2, 2026-09-14. v1 read the ENTIRE body, so it harvested intercepts that the
release was merely quoting. v2 reads the headline plus the LEDE of the body
only, drops intercepts beside historical language, and refuses a release whose
headline announces a plan rather than a result.

v2.4, 2026-09-15 (offline audit; measure.py reproduces every number below
against the 3,891 releases tagged Drill Results). Changes, each measured
leave-one-out against the full corpus in both directions:

  metal_boundary   "Co" matched the "co" of "copper" (and "W" the "w" of
                   "with"), and "gold equivalent" matched as plain "gold".
                   428 stored intercepts were labelled cobalt; most were copper.
  metal_infer      a grade with no metal after it defaulted to Au, so
                   "15,372 g/t over 3.34 m" in a silver release was stored as
                   gold, and "0.24% over 1,763 m" in a nickel release as "0.24%
                   Au". The metal is now read from a parenthetical after the
                   unit or the nearest metal earlier in the same sentence; a
                   non-g/t grade with no metal anywhere is dropped.
  number_bounds    a grade could start in the middle of a number: ".95%
                   Copper" was read as 95%, "0. 63% U3O8" (PDF spacing) as 63%.
  units_spelled    "grams per tonne", "grams/tonne", "oz/ton" were not units;
                   "oz/ton" was read as "oz/t" + metal "on" -> default Au.
  vocab            oxide/element grades (Cs2O, Sc2O3, P2O5, Fe2O3, TiO2 ...)
                   and unicode subscripts (Li₂O, WO₃, U₃O₈) were cut to a bare
                   element or defaulted to Au.
  connective       "30 m true width of 33.2%", "136.51m (447.87 ft) of 1.46 g/t",
                   "5.51 g/t gold ("Au") over 4.60 metres", "(7.52 gpt AuEq)
                   over 8.58m", "7.5 meters @276 ppm".
  chain            "0.44% Ni, 0.51% Cu and 0.69 g/t PGE over 18.50 Metres"
                   gave only the PGE grade; every listed grade now gets the length.
  score            grade x length compared 540 ppm with 5%, so a trace-element
                   ppb/ppm grade could become the "top" intercept. The top is now
                   the release's primary metal (first reported), headline first.
  project          single commodity words ("Gold", "Main") and fragments with a
                   newline or a verb were accepted as project names.

    python3 drill_extract.py     # run the self-test
"""
from __future__ import annotations
import re
import sys

# Every change is behind a flag so measure.py can attribute rows gained/lost
# to exactly one change (leave-one-out). All True is the shipped behaviour.
FLAGS = {
    "metal_boundary": True,
    "metal_infer": True,
    "number_bounds": True,
    "units_spelled": True,
    "vocab": True,
    "connective": True,
    "chain": True,
    "score": True,
    "project": True,
    "sample_type": True,
    "historical_ref": True,
    "headline_metal_from_body": True,
    "ceiling_silver": True,
    "within_guard": True,
    "depth_guard": True,
}

# ---------- vocabulary ----------

_NAME_TO_SYMBOL = {
    "gold": "Au", "silver": "Ag", "copper": "Cu", "nickel": "Ni",
    "zinc": "Zn", "lead": "Pb", "cobalt": "Co", "uranium": "U",
    "molybdenum": "Mo", "manganese": "Mn", "vanadium": "V",
    "lithium": "Li", "tungsten": "W", "tin": "Sn", "antimony": "Sb",
    "platinum": "Pt", "palladium": "Pd", "graphite": "Cg",
    "total copper": "Cu", "total rare earth": "TREO",
    "copper equivalent": "CuEq", "gold equivalent": "AuEq",
    "nickel equivalent": "NiEq", "zinc equivalent": "ZnEq",
    "silver equivalent": "AgEq", "lead equivalent": "PbEq",
    "palladium equivalent": "PdEq", "tin equivalent": "SnEq",
    # v2.4 vocab
    "chromium": "Cr", "cesium": "Cs", "caesium": "Cs", "rubidium": "Rb",
    "scandium": "Sc", "gallium": "Ga", "germanium": "Ge", "tellurium": "Te",
    "bismuth": "Bi", "niobium": "Nb", "tantalum": "Ta", "titanium": "Ti",
    "lithium oxide": "Li2O", "cesium oxide": "Cs2O", "caesium oxide": "Cs2O",
    "tungsten trioxide": "WO3", "graphitic carbon": "Cg",
    "rhodium": "Rh", "ruthenium": "Ru", "iridium": "Ir", "osmium": "Os",
}

_EQ_BASE = r"Au|Ag|Cu|Ni|Zn|Pb|Sn|Pd|Pt|Mo|W|U3O8|Li2O"
_METAL_NAMES_NEW = sorted(
    [k.replace(" ", r"[\s\-]+") for k in _NAME_TO_SYMBOL] + [
        r"gold[\s\-]+eq(?:uiv(?:alent)?)?\.?", r"silver[\s\-]+eq(?:uiv(?:alent)?)?\.?",
        r"copper[\s\-]+eq(?:uiv(?:alent)?)?\.?", r"zinc[\s\-]+eq(?:uiv(?:alent)?)?\.?",
    ], key=len, reverse=True)
_OXIDES_NEW = (
    r"eU3O8|U3O8|Li2O|Ta2O5|Nb2O5|V2O5|WO3|MoS2|Cs2O|Rb2O|Sc2O3|P2O5|Fe2O3|TiO2"
    r"|Cr2O3|Ga2O3|K2O|KCl|CoO|MnO|SnO2"
    r"|TREOs?|MREO|HREO|LREO|REOs?|TREEs?|REEs?|NdPr|PGEs?|PGMs?|2PGE|CuT|TCu"
)
_SYMBOLS_NEW = r"Au|Ag|Cu|Ni|Zn|Pb|Co|Mo|Sb|Sn|Pt|Pd|Rh|Ru|Ir|Cg|Mn|Li|Ga|Ge|Sc|Te|Bi|Cs|Rb|Cr|Nb|Ta|Ti|Fe|W|V|U"
_EQ_NEW = rf"(?:{_EQ_BASE})[\s.\-]*Eq(?:uiv(?:alent)?)?\.?"
# names/equivalents first, so "copper equivalent" beats "copper" beats "Co"
_METAL_ALT_NEW = (rf"{_EQ_NEW}|{_OXIDES_NEW}|total[\s\-]+copper"
                  rf"|total[\s\-]+rare[\s\-]+earth(?:[\s\-]+oxides?)?"
                  rf"|{'|'.join(_METAL_NAMES_NEW)}|{_SYMBOLS_NEW}")
# v2.3 vocabulary, verbatim
_METAL_ALT_OLD = (
    r"AuEq|CuEq|NiEq|ZnEq|AgEq|PbEq|SnEq"
    r"|TREO|REO|TREE|REE|U3O8|eU3O8|Li2O|Ta2O5|Nb2O5|V2O5|WO3|MoS2"
    r"|Au|Ag|Cu|Ni|Zn|Pb|Co|Mo|Sb|Sn|Pt|Pd|Cg|Mn|Li|Ga|Ge|Sc|Te|Bi|Cs|Rb|W|V|U"
    r"|total\s+copper|total\s+rare\s+earth"
    r"|gold|silver|copper|nickel|zinc|lead|cobalt|uranium|molybdenum|manganese"
    r"|vanadium|lithium|tungsten|tin|antimony|platinum|palladium|graphite"
    r"|copper\s+equivalent|gold\s+equivalent|silver\s+equivalent"
)
# the v2.3 vocabulary reordered so a boundary can do its job
_METAL_ALT_OLD_ORDERED = (
    r"AuEq|CuEq|NiEq|ZnEq|AgEq|PbEq|SnEq"
    r"|TREO|REO|TREE|REE|eU3O8|U3O8|Li2O|Ta2O5|Nb2O5|V2O5|WO3|MoS2"
    r"|total\s+copper|total\s+rare\s+earth"
    r"|copper\s+equivalent|gold\s+equivalent|silver\s+equivalent"
    r"|gold|silver|copper|nickel|zinc|lead|cobalt|uranium|molybdenum|manganese"
    r"|vanadium|lithium|tungsten|tin|antimony|platinum|palladium|graphite"
    r"|Au|Ag|Cu|Ni|Zn|Pb|Co|Mo|Sb|Sn|Pt|Pd|Cg|Mn|Li|Ga|Ge|Sc|Te|Bi|Cs|Rb|W|V|U"
)
# For inferring a missing metal from the sentence: symbols are case-SENSITIVE
# there, so "as", "in", "v" in prose are never read as metals.
_METAL_INFER_RX = re.compile(
    rf"(?<![A-Za-z])(?P<metal>(?i:{_EQ_NEW})|{_OXIDES_NEW}|(?i:total[\s\-]+copper)"
    rf"|(?i:{'|'.join(_METAL_NAMES_NEW)})|{_SYMBOLS_NEW})(?![A-Za-z])")


def _metal_rx() -> str:
    if FLAGS["vocab"]:
        alt = _METAL_ALT_NEW
    else:
        alt = _METAL_ALT_OLD_ORDERED if FLAGS["metal_boundary"] else _METAL_ALT_OLD
    if FLAGS["metal_boundary"]:
        # every alternative must END at a non-letter: "Co" is never the start of
        # "copper", "W" never the start of "with"
        return rf"(?:{alt})(?![A-Za-z])"
    return alt


def _num_rx() -> str:
    if FLAGS["number_bounds"]:
        # never start inside another number (".95" -> "95", "2,8" -> "8");
        # a leading-dot decimal ".95" is a number in its own right.
        return (r"(?<![\d.,])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)")
    return r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"


_UNIT_OLD = r"g/tonne|g/t|gpt|g\s*/\s*t|%|ppm|ppb|gms|opt|oz/t|kg/t"
# "oz/ton" is tried before "oz/t" so the "on" is not left over as a metal
_UNIT_NEW = r"g/tonne|g/t|gpt|g\s*/\s*t|%|ppm|ppb|gms(?![A-Za-z])|opt(?![A-Za-z])|oz/ton|oz/t|kg/t"

_LEN_UNIT = r"metres|meters|metre|meter|m|feet|foot|ft"


def _num(s: str) -> float:
    s = s or "0"
    return float(("0" + s) if s.startswith(".") else s.replace(",", ""))


def _to_metres(value: float, unit: str) -> float:
    return value * 0.3048 if (unit or "").lower() in ("ft", "feet", "foot") else value


_PAREN = r"\s*\([^()\n]{0,60}\)"
_WIDTH_QUAL = (r"(?:\s*\(?(?:estimated\s+|est\.?\s+|approximate\s+)?"
               r"(?:true\s+(?:width|thickness)|ETW|core\s+length|down[\-\s]?hole\s+(?:length|width)"
               r"|drilled\s+(?:width|length|thickness)|apparent\s+(?:width|thickness)"
               r"|interval|intercept|section)\)?\*?)?")
_LEN_PAREN = (r"(?:\s*\(\s*(?:[\d.,]+\s*(?:ft|feet|foot|m|metres?|meters?)"
              r"|[“\"']?[A-Za-z]{1,4}[”\"']?)\s*\))?")
# "1.00 m from 606.25 to 607.25 m grading", "16.7 meters (41.2-57.9 m) grading"
_RANGE = (r"(?:\s*,?\s*(?:from\s+)?(?:\(\s*)?[\d.,]+\s*(?:m|metres?|meters?|ft|feet)?\s*"
          r"(?:to|-|\u2013)\s*[\d.,]+\s*(?:m|metres?|meters?|ft|feet)\b\s*\)?)?")
_OVER_WIDTH = (r"(?:\s+(?:an?\s+)?(?:estimated\s+)?(?:true|drilled|core|down[\-\s]?hole|apparent)"
               r"\s+(?:width|length|thickness)\s+of)?")


def _build():
    """Compile the patterns for the current FLAGS."""
    N = _num_rx()
    U = _UNIT_NEW if FLAGS["units_spelled"] else _UNIT_OLD
    M = _metal_rx()
    if FLAGS["vocab"]:
        MP = rf"(?:{M})(?:\s*[+/\-]\s*(?:{M})){{0,2}}"
    else:
        MP = rf"(?:{M})(?:\s*[+/]\s*(?:{M}))?"
    con = FLAGS["connective"]
    parq = f"(?:{_PAREN})?" if con else ""
    hy = r"\s*-?\s*" if con else r"\s*"
    ow = _OVER_WIDTH if con else ""
    # "(... 0.84 G/T Au) Over 15.10m": the list closes before the connector
    rb = r"\s*\)?" if con else ""

    a = re.compile(
        rf"(?P<grade>{N})\s*(?P<unit>{U}){parq}\s*(?P<metal>{MP})"
        rf"{parq}(?:\s+[A-Za-z\-]+){{0,3}}?{parq}{rb}\s+(?:over|across|within)(?:\s+(?:a|an|the))?{ow}\s+"
        rf"(?P<length>{N}){hy}(?P<lenunit>{_LEN_UNIT})\b",
        re.I)
    if con:
        b = re.compile(
            rf"(?P<length>{N}){hy}(?P<lenunit>{_LEN_UNIT})\b{_LEN_PAREN}{_WIDTH_QUAL}{_LEN_PAREN}{_RANGE}"
            rf"(?:\s*@\s*|\s+(?:of|at|grading|averaging|returning|containing|with|assaying)"
            rf"(?:\s+[A-Za-z\-]+){{0,4}}?\s+)"
            rf"(?P<grade>{N})\s*(?P<unit>{U})\s*(?P<metal>{MP})?",
            re.I)
    else:
        b = re.compile(
            rf"(?P<length>{N})\s*(?P<lenunit>{_LEN_UNIT})\b"
            rf"(?:\s+(?:of|@|at|grading|averaging|returning|containing|with|assaying))"
            rf"(?:\s+[A-Za-z\-]+){{0,4}}?\s+"
            rf"(?P<grade>{N})\s*(?P<unit>{U})\s*(?P<metal>{MP})?",
            re.I)
    c = re.compile(
        rf"(?P<grade>{N})\s*(?P<unit>{U}){parq}\s+(?P<metal>{MP})?{parq}\s*"
        rf"{rb}(?:over|across|within)(?:\s+(?:a|an|the))?{ow}\s+(?P<length>{N}){hy}(?P<lenunit>{_LEN_UNIT})\b",
        re.I)
    # one item of a grade list that ends where the anchored intercept begins
    chain_back = re.compile(
        rf"(?P<grade>{N})\s*(?P<unit>{U})\s*(?P<metal>{MP}){parq}\s*(?:,\s*(?:and\s+|&\s*)?|\s+and\s+|\s*&\s*)$",
        re.I)
    # one item of a grade list continuing after "26 m of 1.0% CuEq"; an item
    # that is followed by its own "over X m" belongs to that length instead
    chain_fwd = re.compile(
        rf"^{parq}\s*(?:,\s*(?:and\s+|&\s*)?|\s+and\s+|\s*&\s*)(?P<grade>{N})\s*(?P<unit>{U})\s*(?P<metal>{MP})"
        rf"(?![\w/])(?!{parq}\s*(?:over|across|within)\b)",
        re.I)
    metal_after = re.compile(
        rf"^(?:\s*\(\s*[\d.,]+\s*(?:%|g/t|oz/t|opt|ppm|ppb)\s*(?P<pmetal>(?:{_METAL_ALT_NEW})(?![A-Za-z]))\s*\)"
        rf"|(?:{_PAREN})?\s*(?:of\s+|in\s+)?(?:(?:combined|total|contained|calculated)\s+)?"
        rf"(?P<metal>(?:{_METAL_ALT_NEW})(?![A-Za-z])))", re.I)
    return a, b, c, chain_back, chain_fwd, _METAL_INFER_RX, metal_after


_COMPILED: dict = {}


def _patterns():
    key = tuple(sorted(FLAGS.items()))
    if key not in _COMPILED:
        _COMPILED[key] = _build()
    return _COMPILED[key]


# kept as module attributes for anything that imported them
_RE_GRADE_OVER_LENGTH, _RE_LENGTH_AT_GRADE, _RE_HEADLINE_OVER = _build()[:3]

_RE_HOLE = re.compile(
    r"\b(?:Hole|drillhole|drill\s+hole|DDH|DH|HQ|RC|BH)\s*[#:]?\s*"
    r"([A-Z]{1,5}[\-: ]?\d{1,4}[\-A-Z0-9]*)\b",
    re.I)

# ---------- where an intercept may be read from ----------

# Everything from here down is furniture, not news.
_RE_BOILERPLATE_START = re.compile(
    r"(?i)(about\s+(?:the\s+company|us)\b"
    r"|forward[\-\s]looking\s+(?:statement|information)"
    r"|cautionary\s+(?:note|statement)"
    r"|qualified\s+person"
    r"|neither\s+the\s+(?:tsx|canadian\s+securities)"
    r"|for\s+(?:further|more)\s+information"
    r"|on\s+behalf\s+of\s+the\s+board)")

# An intercept quoted from somebody else's programme, or from the company's own
# past. FNI.CN had a row built on a hole drilled in 1966.
_RE_HISTORICAL = re.compile(
    r"(?i)\b(historic(?:al|ally)?|previously\s+(?:report|announc|releas|drill)"
    r"|press\s+release\s+dated|news\s+release\s+dated|see\s+(?:the\s+)?(?:news|press)\s+release"
    r"|assessment\s+report|prior\s+(?:drilling|program|hole)|drilled\s+in\s+(?:19|20)\d{2}"
    r"|non[\-\s]compliant|past\s+producer|former\s+operator|reported\s+by\s+[A-Z])\b")
# v2.4: "(ref. press releases of 2021)", "(refer to news release of May 5)"
_RE_HISTORICAL_REF = re.compile(
    r"(?i)\b(?:ref(?:\.|er\s+to|erence)?|as\s+per)\s+(?:the\s+)?(?:company'?s\s+)?(?:press|news)\s+releases?\b")

_RE_RESULTS_STRONG = re.compile(
    r"(?i)\b(intersect\w*|intercept\w*|assay\w*|grading|returns?|returned"
    r"|hits?|encounter\w*|yields?|step[\-\s]out\s+results?|drill\s+results?"
    r"|final\s+results?|results?\s+from\s+(?:hole|the\s+\w+\s+program))\b")

_RE_PLAN_ONLY = re.compile(
    r"(?i)\b(mobiliz\w*|commenc\w*|begins?|beginning|initiat\w*|prepar\w*|plans?\s+to"
    r"|upcoming|permit\w*|finaliz\w*|engages?|hires?|anticipat\w*|to\s+commence"
    r"|set\s+to\s+drill|about\s+to|schedul\w*|award\w*\s+contract|contracts?\s+\w+\s+drilling)\b")

# Plausibility is a fact, not a taste: a % grade cannot exceed 100, and gold
# quoted as a percentage above a few percent is a recovery rate or a stake.
_MAX_PCT = {"au": 5.0, "ag": 20.0, "pt": 5.0, "pd": 5.0, "u": 30.0}
_MAX_BY_UNIT = {"%": 100.0, "g/t": 20000.0, "ppm": 100000.0,
                "ppb": 1000000.0, "opt": 600.0, "oz/t": 600.0, "kg/t": 50.0}


# Silver is reported far higher than gold: Kuya's 74,418 g/t Ag over 0.30 m and
# Nord's 61,389 g/t Ag over 0.3 m are real, and the 20,000 g/t cap dropped them.
# 100,000 g/t is 10% silver. Only for a metal the text actually names.
_MAX_SILVER = {"g/t": 100000.0, "oz/t": 3000.0, "opt": 3000.0}


def _plausible(grade: float, unit: str, metal: str, explicit: bool = False) -> bool:
    u = (unit or "").lower()
    m = (metal or "").split("+")[0].strip().lower()
    cap = _MAX_BY_UNIT.get(u)
    if FLAGS["ceiling_silver"] and explicit and m in ("ag", "ageq") and u in _MAX_SILVER:
        cap = _MAX_SILVER[u]
    if cap is not None and grade > cap:
        return False
    if u == "%" and m in _MAX_PCT and grade > _MAX_PCT[m]:
        return False
    return True


LEDE_CHARS = 6000
HIST_WINDOW = 260


def lede(body: str, n: int = LEDE_CHARS) -> str:
    """The part of the release that is actually the news."""
    b = body or ""
    m = _RE_BOILERPLATE_START.search(b)
    if m:
        b = b[:m.start()]
    return b[:n]


_CANON = {
    "treo": "TREO", "reo": "REO", "ree": "REE", "tree": "TREE", "mreo": "MREO",
    "treos": "TREO", "reos": "REO", "rees": "REE", "trees": "TREE", "pges": "PGE", "pgms": "PGM",
    "hreo": "HREO", "lreo": "LREO", "ndpr": "NdPr", "pge": "PGE", "pgm": "PGM",
    "2pge": "2PGE", "3e": "3E",
    "li2o": "Li2O", "u3o8": "U3O8", "eu3o8": "eU3O8", "ta2o5": "Ta2O5",
    "nb2o5": "Nb2O5", "v2o5": "V2O5", "wo3": "WO3", "mos2": "MoS2",
    "cs2o": "Cs2O", "rb2o": "Rb2O", "sc2o3": "Sc2O3", "p2o5": "P2O5",
    "fe2o3": "Fe2O3", "tio2": "TiO2", "cr2o3": "Cr2O3", "ga2o3": "Ga2O3",
    "cut": "Cu", "tcu": "Cu",
    "k2o": "K2O", "kcl": "KCl", "coo": "CoO", "mno": "MnO", "sno2": "SnO2",
    "aueq": "AuEq", "cueq": "CuEq", "nieq": "NiEq", "zneq": "ZnEq",
    "ageq": "AgEq", "pbeq": "PbEq", "sneq": "SnEq", "pdeq": "PdEq", "cg": "Cg",
}
_SYM_CASE = {s.lower(): s for s in _SYMBOLS_NEW.split("|")}


def _normalize_one(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip().lower())
    if FLAGS["vocab"] or FLAGS["metal_boundary"]:
        s = re.sub(r"[\s\-]+", " ", s).rstrip(".")
        m = re.fullmatch(r"([a-z0-9]+?)[ .]*eq(?:uiv(?:alent)?)?", s)
        if m:
            base = _NAME_TO_SYMBOL.get(m.group(1), m.group(1))
            base = _CANON.get(base.lower(), _SYM_CASE.get(base.lower(), base.title()))
            return f"{base}Eq"
    if s in _NAME_TO_SYMBOL:
        return _NAME_TO_SYMBOL[s]
    if s in _CANON:
        return _CANON[s]
    if s in _SYM_CASE:
        return _SYM_CASE[s]
    return s.title() if len(s) <= 3 else s.upper()


def _normalize_metal(s: str) -> str:
    sep = r"\s*[+/\-]\s*" if FLAGS["vocab"] else r"\s*[+/]\s*"
    raw = (s or "").strip()
    if FLAGS["vocab"] and re.search(r"(?i)[\s\-]eq", raw):
        # "Au eq", "gold-equivalent" is one token, not a pair
        return _normalize_one(raw)
    parts = re.split(sep, raw)
    return "+".join(_normalize_one(p) for p in parts if p)


_RE_SPACED_OXIDE = re.compile(
    r"\b(?:eU\s+3\s*O\s*8|U\s+3\s*O\s*8|U3O\s+8|Li\s+2\s*O|WO\s+3|Cs\s+2\s*O|Rb\s+2\s*O"
    r"|V\s+2\s*O\s*5|Nb\s+2\s*O\s*5|Ta\s+2\s*O\s*5|P\s+2\s*O\s*5|Sc\s+2\s*O\s*3|Fe\s+2\s*O\s*3|TiO\s+2)\b")
_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_RE_SPELLED_GPT = re.compile(r"(?i)\bgrams?\s*(?:per|/)\s*(?:metric\s+)?tonnes?\b")
_RE_SPELLED_PPM = re.compile(r"(?i)\bparts\s+per\s+million\b(?:\s*\(\s*[\u201c\"]?ppm[\u201d\"]?\s*\))?")
_RE_SPELLED_PPB = re.compile(r"(?i)\bparts\s+per\s+billion\b(?:\s*\(\s*[\u201c\"]?ppb[\u201d\"]?\s*\))?")
_RE_SPELLED_OPT = re.compile(r"(?i)\b(?:ounces?|oz)\s*(?:per|/)\s*(?:short\s+)?ton\b")
# "5.3 Grams Au over 3.8 Meters", "3.1 Grams Gold"
_RE_BARE_GRAMS = re.compile(r"(?i)(?<=\d)\s*grams?(?=\s+(?:Au|gold)\b)")


def _prep(text: str) -> str:
    t = text or ""
    if FLAGS["vocab"]:
        t = t.translate(_SUBSCRIPTS)
        # PDF-spaced formulas: "eU 3 O 8", "Li 2 O", "WO 3", "Nb 2 O 5"
        t = _RE_SPACED_OXIDE.sub(lambda m: re.sub(r"\s+", "", m.group(0)), t)
    if FLAGS["number_bounds"]:
        # PDF spacing: "0. 63% U3O8", "25. 5 METRES"
        t = re.sub(r"(?<=\d)\. (?=\d)", ".", t)
    if FLAGS["units_spelled"]:
        t = _RE_SPELLED_GPT.sub("g/t", t)
        t = _RE_SPELLED_OPT.sub("oz/t", t)
        t = _RE_SPELLED_PPM.sub("ppm", t)
        t = _RE_SPELLED_PPB.sub("ppb", t)
        t = _RE_BARE_GRAMS.sub(" g/t", t)
    return t


_SENT_BREAK = re.compile(r"(?:[.;!?](?:\s|$)|\n\s*\n|[•●▪]|\n\s*[-*o]\s)")
_PRECEDED_BY_DEPTH = re.compile(r"(?i)(?:\bat|\bfrom|(?<!up )\bto|depth\s+of|between)\s*$")


# A grade followed by a mineral or a non-metal commodity is a mineral
# percentage ("20.1% Magnesium", "11.82% Igneous Phosphate", "20% visible
# spodumene"), not a metal grade, and must not inherit a metal from the sentence.
_RE_NOT_A_METAL = re.compile(
    r"(?i)^(?:\s*\([^()\n]{0,60}\))?\s*(?:(?:visible|massive|semi[\-\s]massive|disseminated|"
    r"net[\-\s]textured|igneous|total|combined|coarse|fine)\s+)*"
    r"(?:magnesium|mg|mgo|phosphate|apatite|sulph\w*|sulf\w*|s\b|iron|barite|baso4|fluorite|caf2"
    r"|potash|carbon|silica|sio2|al2o3|alumina|zircon\w*|zro2|helium|kaolin\w*|halloysite|feldspar"
    r"|mica|quartz|pyrite|pyrrhotite|chalcopyrite|arsenopyrite|stibnite|spodumene|petalite|lepidolite"
    r"|magnetite|hematite|ilmenite|recover\w*|mass\s+pull|rqd|moisture|clay|concentrate|ash)\b")


_GENERIC_NEXT = {
    "mineralization", "mineralisation", "mineralized", "mineralised", "grade", "grades",
    "value", "values", "intercept", "intercepts", "intersection", "intersections",
    "assay", "assays", "result", "results", "equivalent", "eq", "over", "and", "with",
    "in", "at", "of", "discovery", "drilling", "zone", "zones", "system", "vein", "veins",
    "oxide", "sulphide", "sulfide", "bearing", "rich", "enriched", "grading", "averaging",
}
_HEADLINE_PREV = {
    "intersects", "intersected", "intercepts", "drills", "drilled", "reports", "returns",
    "hits", "of", "and", "significant", "high-grade", "high", "grade", "new", "visible",
    "massive", "continuous", "near-surface", "broad", "wide", "thick", "encounters",
    "confirms", "expands", "extends", "discovers", "samples", "assays", "including",
    "incl", "with", "total", "oxide", "sulphide", "sulfide", "the", "its", "at", "in",
    "on", "from", "critical", "grams", "tonne", "per", "g/t", "metres", "meters", "m",
}


def _name_is_proper(seg: str, mm) -> bool:
    """A metal NAME inside a proper noun ("Tin Cup", "Quesnel Nickel Project",
    "Argenta Silver") is a name, not the grade's metal. A title-case headline
    ("Intersects Copper Mineralization of 0.5%") is not a proper noun."""
    word = mm.group("metal")
    if not word[:1].isupper() or len(word) <= 3 or word.isupper():
        return False
    pm = re.search(r"([A-Z][\w\u2019'\-]*)\s*$", seg[:mm.start()])
    nm = re.match(r"\s*([A-Z][a-z][\w\-]*)", seg[mm.end():])
    prev_proper = bool(pm) and pm.group(1).lower() not in _HEADLINE_PREV
    next_proper = bool(nm) and nm.group(1).lower() not in _GENERIC_NEXT
    return prev_proper or next_proper


def _infer_metal(t: str, gstart: int, uend: int, unit: str):
    """Metal for a grade written without one, or None to drop the grade."""
    pats = _patterns()
    tail = t[uend:uend + 80]
    after = pats[6].match(tail)
    if after:
        # "6100 g/t (0.61% Cu)": the conversion in brackets names the metal
        return after.group("pmetal") or after.group("metal")
    if _RE_NOT_A_METAL.match(tail):
        return None
    lo = max(0, gstart - 160)
    seg = t[lo:gstart]
    cut = 0
    for sb in _SENT_BREAK.finditer(seg):
        cut = sb.end()
    seg = seg[cut:]
    last = None
    for mm in pats[5].finditer(seg):
        if _name_is_proper(seg, mm):
            continue
        last = mm.group("metal")
    if last:
        return last
    if unit in ("g/t", "oz/t", "opt", "gms", "kg/t"):
        return "Au"
    return None


def find_intercepts(text: str, drop_historical: bool = False) -> list[dict]:
    """Intercepts in text. With drop_historical, one sitting next to "historic"
    or "previously reported" is somebody else's result and is left alone."""
    out, seen = [], set()
    t = _prep(text)
    a, b, c, chain_back, chain_fwd, _, _ = _patterns()

    def add(grade_s, unit_s, metal_s, length, pos, gstart, uend, span):
        try:
            grade = _num(grade_s)
        except (ValueError, TypeError):
            return
        if drop_historical:
            win = t[max(0, span[0] - HIST_WINDOW):span[1] + HIST_WINDOW]
            if _RE_HISTORICAL.search(win) or (FLAGS["historical_ref"] and _RE_HISTORICAL_REF.search(win)):
                return
        unit_raw = (unit_s or "").lower().replace(" ", "")
        unit_raw = "g/t" if unit_raw in ("gpt", "g/tonne", "g/t") else unit_raw
        if unit_raw == "oz/ton":
            unit_raw = "oz/t"
        how = "explicit"
        if metal_s:
            metal_raw = metal_s
        elif FLAGS["metal_infer"]:
            metal_raw = _infer_metal(t, gstart, uend, unit_raw)
            if metal_raw is None:
                return
            how = "inferred"
        else:
            metal_raw = "Au"
            how = "default"
        metal = _normalize_metal(metal_raw)
        if length < 0.1 or length > 2000:
            return
        if grade < 0.01 or grade > 100000:
            return
        if not _plausible(grade, unit_raw, metal, how == "explicit"):
            return
        key = (round(length, 1), round(grade, 2), metal)
        if key in seen:
            return
        seen.add(key)
        out.append({"length_m": length, "grade": grade,
                    "unit": "%" if unit_raw == "%" else unit_raw or "g/t",
                    "metal": metal, "pos": pos, "metal_how": how})

    for rx in (a, b, c):
        for m in rx.finditer(t):
            try:
                length = _to_metres(_num(m.group("length")), m.group("lenunit"))
            except (ValueError, IndexError, TypeError):
                continue
            # "2 feet from 257 to 259 feet @ 4.22% Cu": 259 ft is a depth, not a length
            if FLAGS["depth_guard"] and rx is b and _PRECEDED_BY_DEPTH.search(t[max(0, m.start() - 14):m.start()]):
                continue
            # "5.04 g/t Gold Within 94.0 m of 1.79 g/t Gold": 94 m belongs to the
            # enclosing interval's own grade, not to 5.04 g/t (which has its own
            # length earlier); and "within 250 m of the property" is a distance.
            if rx is not b and FLAGS["within_guard"] \
                    and re.match(r"(?i)\s*(?:\([^()\n]{0,40}\)\s*)?(?:of|from|at|@|grading|averaging|returning)\b|\s*@",
                                 t[m.end():m.end() + 50]) \
                    and re.search(r"(?i)\bwithin\b", t[m.start():m.start("length")]):
                continue
            try:
                metal_s = m.group("metal")
            except IndexError:
                metal_s = None
            add(m.group("grade"), m.group("unit"), metal_s, length,
                m.start("grade"), m.start("grade"), m.end("unit"), (m.start(), m.end()))
            if not FLAGS["chain"]:
                continue
            if rx is b:
                # "26 m of 1.0% CuEq, 0.255% Cu and 498 ppb Au" (metal required)
                if not metal_s:
                    continue
                k, cur = 0, m.end()
                while k < 6:
                    f = chain_fwd.match(t[cur:cur + 120])
                    if not f:
                        break
                    add(f.group("grade"), f.group("unit"), f.group("metal"), length,
                        cur + f.start("grade"), cur + f.start("grade"), cur + f.end("unit"),
                        (m.start(), cur + f.end()))
                    cur += f.end()
                    k += 1
            else:
                if not metal_s:
                    continue
                k, cur = 0, m.start()
                while k < 6:
                    seg = t[max(0, cur - 120):cur]
                    g = chain_back.search(seg)
                    if not g:
                        break
                    base = cur - len(seg)
                    add(g.group("grade"), g.group("unit"), g.group("metal"), length,
                        base + g.start("grade"), base + g.start("grade"), base + g.end("unit"),
                        (base + g.start(), m.end()))
                    cur = base + g.start()
                    k += 1
    return out


def find_hole_id(text: str) -> str | None:
    if not text:
        return None
    m = _RE_HOLE.search(text)
    return m.group(1).upper() if m else None


# ---------- surface vs drill ----------

# The Drill Results category deliberately includes surface sampling, so this is
# a flag, never a filter.
_RE_SURFACE = re.compile(
    r"(?i)\b(grab|chip|channel\w*|trench\w*|rock\s+samples?|outcrop\w*|soils?|boulders?|float"
    r"|surface\s+sampl\w+|panel\s+samples?|prospecting|dump\s+samples?|stockpile)\b")
_RE_DRILL = re.compile(
    r"(?i)\b(drill\w*|holes?|DDH|core|intersect\w*|intercept\w*|hits?|RC|reverse\s+circulation"
    r"|diamond|step[\-\s]?out|infill|down[\-\s]?hole|borehole)\b")


def classify_sample(headline: str, text: str, pos: int) -> str | None:
    """"surface" when the nearest sampling word before the intercept is a
    surface word, "drill" when it is a drill word; the headline decides when
    the local text is silent."""
    seg = text[max(0, pos - 300):pos] if pos >= 0 else ""
    last_s = max((m.end() for m in _RE_SURFACE.finditer(seg)), default=-1)
    last_d = max((m.end() for m in _RE_DRILL.finditer(seg)), default=-1)
    if last_s > last_d:
        return "surface"
    if last_d > last_s:
        return "drill"
    hs, hd = _RE_SURFACE.search(headline or ""), _RE_DRILL.search(headline or "")
    if hs and not hd:
        return "surface"
    if hd and not hs:
        return "drill"
    return None


# ---------- project name ----------

_PROJ_TOKEN = r"[A-Z][A-Za-z0-9'’\-]*"
_RE_PROJECT = re.compile(
    rf"\b(?:at|from|on|within|across)\s+(?:(?i:the|its|our|a)\s+)*"
    rf"(?P<name>(?:{_PROJ_TOKEN}\s+){{0,3}}{_PROJ_TOKEN})\s+"
    r"(?:Property|Project|Prospect|Deposit|Discovery|Zone|Vein|Trend|Target|Camp|Mine)\b")
_RE_PROJECT_BARE = re.compile(
    rf"\b(?P<name>(?:{_PROJ_TOKEN}\s+){{0,3}}{_PROJ_TOKEN})\s+"
    r"(?:Property|Project|Prospect|Deposit|Discovery)\b")
# v2.4: tokens may be separated by at most one line break (PDF wrapping,
# "Duck \nCreek"), never a blank line; the name is re-joined with single spaces.
_PSEP = r"(?:[ \t]+|[ \t]*\n[ \t]*)"
_RE_PROJECT_NL = re.compile(
    rf"\b(?:[Aa]t|[Ff]rom|[Oo]n|[Ww]ithin|[Aa]cross){_PSEP}(?:(?i:the|its|our|a){_PSEP})*"
    rf"(?P<name>(?:{_PROJ_TOKEN}{_PSEP}){{0,3}}{_PROJ_TOKEN}){_PSEP}"
    r"(?:Property|Project|Prospect|Deposit|Discovery|Zone|Vein|Trend|Target|Camp|Mine)\b")
_RE_PROJECT_BARE_NL = re.compile(
    rf"\b(?P<name>(?:{_PROJ_TOKEN}{_PSEP}){{0,3}}{_PROJ_TOKEN}){_PSEP}"
    r"(?:Property|Project|Prospect|Deposit|Discovery)\b")
_PROJECT_LEADING_JUNK = {"flagship", "on", "the", "its", "our", "high-grade", "wholly-owned"}

_PROJECT_STOP = {
    "company", "corporation", "corp", "inc", "ltd", "ceo", "president",
    "shareholders", "annual", "general", "press", "release", "joint", "venture",
    "agreement", "letter", "intent", "offering", "placement", "financing",
    "drilling", "drill", "results", "result", "program", "programme", "phase",
    "exploration", "mobilization", "strike", "identification", "underway",
    "largest", "work", "completion", "update", "news", "its", "the", "and",
    "successful", "maiden", "initial", "new", "further", "additional", "area",
}
# v2.4: verbs of the headline sentence are never part of a name
_PROJECT_STOP_NEW = _PROJECT_STOP | {
    "extends", "extend", "known", "mineralized", "mineralised", "discovers",
    "intersects", "drills", "reports", "expands", "confirms", "announces",
    "returns", "hits", "encounters", "identifies", "samples",
    "at", "of", "over", "feet", "metres", "meters", "grading",
}
# a single token that is only a commodity or a generic word is not a name
_PROJECT_BARE_WORDS = {
    "gold", "silver", "copper", "nickel", "zinc", "lithium", "uranium", "main",
    "first", "second", "third", "north", "south", "east", "west", "central",
    "deep", "high-grade", "flagship", "district", "polymetallic", "critical",
}


def _project_ok(name: str) -> bool:
    toks = [t.lower().strip(".,;'’") for t in (name or "").split()]
    if not 1 <= len(toks) <= 4:
        return False
    stop = _PROJECT_STOP_NEW if FLAGS["project"] else _PROJECT_STOP
    if any(t in stop for t in toks):
        return False
    if FLAGS["project"] and len(toks) == 1 and toks[0] in _PROJECT_BARE_WORDS:
        return False
    return 3 <= len(name) <= 60


def find_project(headline: str, body: str) -> str | None:
    rxs = (_RE_PROJECT_NL, _RE_PROJECT_BARE_NL) if FLAGS["project"] else (_RE_PROJECT, _RE_PROJECT_BARE)
    for rx in rxs:
        for src in (headline or "", lede(body, 1500)):
            for m in rx.finditer(src):
                name = m.group("name").strip().rstrip(",;.")
                if FLAGS["project"]:
                    name = re.sub(r"\s+", " ", name)
                    # "STLLR Gold's Tower Gold" -> "Tower Gold"
                    name = re.split(r"\S+['’]s\s+", name)[-1]
                    toks = name.split(" ")
                    while len(toks) > 1 and toks[0].lower() in _PROJECT_LEADING_JUNK:
                        toks = toks[1:]
                    name = " ".join(toks)
                if _project_ok(name):
                    return name
    return None


# ---------- top intercept selection ----------

# grade expressed in ppm (= g/t) so grades in different units can be compared
_TO_PPM = {"g/t": 1.0, "ppm": 1.0, "ppb": 0.001, "%": 10000.0,
           "oz/t": 34.2857, "opt": 34.2857, "kg/t": 1000.0, "gms": 1.0}


def score_intercept(it: dict) -> float:
    """Sort key for the top intercept.

    v2.3 was grade x length regardless of unit, so "60 ppb Pd over 13.68 m"
    outranked "1.0% CuEq over 13.68 m". extract() now stamps each intercept with
    a rank tier (headline-and-primary-metal > primary metal > the rest); within a
    tier the order is grade x length. Dicts without the stamp score as before.
    """
    base = (it.get("grade") or 0) * (it.get("length_m") or 0)
    tier = it.get("tier")
    if tier is None:
        return base
    return tier * 1e13 + min(it.get("value", base), 1e12)


def format_intercept(it: dict) -> str:
    g, l = it.get("grade"), it.get("length_m")
    u = it.get("unit") or "g/t"
    m = it.get("metal") or ""
    if g is None or l is None:
        return ""
    gstr = f"{g:.2f}%" if u == "%" else f"{g:.2f} {u}"
    return f"{gstr} {m} / {l:g}m"


_FAMILY = {
    "U3O8": "U", "eU3O8": "U", "Li2O": "Li", "WO3": "W", "Cs2O": "Cs", "Rb2O": "Rb",
    "Nb2O5": "Nb", "Ta2O5": "Ta", "V2O5": "V", "Fe2O3": "Fe", "TiO2": "Ti", "P2O5": "P",
    "MoS2": "Mo", "Sc2O3": "Sc", "Ga2O3": "Ga", "Cr2O3": "Cr", "SnO2": "Sn", "CoO": "Co",
    "MnO": "Mn", "KCl": "K", "K2O": "K", "TREO": "REE", "REO": "REE", "MREO": "REE",
    "HREO": "REE", "LREO": "REE", "TREE": "REE", "NdPr": "REE", "Cg": "C",
    "PGE": "PGE", "PGM": "PGE", "2PGE": "PGE", "3E": "PGE", "Pt": "PGE", "Pd": "PGE",
    "Rh": "PGE", "Ru": "PGE", "Ir": "PGE", "Os": "PGE",
}


def _family(metal: str) -> str:
    """Au, AuEq and Au+Ag are one family; so are U, U3O8 and eU3O8."""
    m = (metal or "").split("+")[0]
    if m.endswith("Eq"):
        m = m[:-2]
    return _FAMILY.get(m, m)


def _stamp_tiers(intercepts: list[dict]) -> None:
    """Rank tier per intercept: the release's primary metal family first.

    Primary = the family of the first intercept in the headline; without one,
    the family the body reports most often (ties -> reported first). Within a
    tier the order is grade x length with the grade in one scale (ppm), so
    "3,730 ppm Cu" and "0.37% Cu" compare equal and 540 ppm never beats 5%.
    """
    if not intercepts:
        return
    hl = [i for i in intercepts if i.get("src", 1) == 0]
    if hl:
        prim = _family(min(hl, key=lambda i: i.get("pos", 0))["metal"])
    else:
        cnt, first = {}, {}
        for i in intercepts:
            f = _family(i["metal"])
            cnt[f] = cnt.get(f, 0) + 1
            first.setdefault(f, i.get("pos", 0))
            first[f] = min(first[f], i.get("pos", 0))
        prim = max(cnt, key=lambda f: (cnt[f], -first[f]))
    for it in intercepts:
        same = _family(it["metal"]) == prim
        head = it.get("src", 1) == 0
        it["tier"] = (3 if head else 2) if same else (1 if head else 0)
        it["value"] = (it.get("grade") or 0) * _TO_PPM.get(it.get("unit"), 1.0) * (it.get("length_m") or 0)


def extract(headline: str, body: str) -> dict:
    """All extracted fields from a drill release, or {"intercepts": []}."""
    hl = headline or ""
    hl_ints = find_intercepts(hl)

    # A release that announces a plan and carries no number of its own is not
    # reporting results, however many old ones its boilerplate repeats.
    if not hl_ints and _RE_PLAN_ONLY.search(hl) and not _RE_RESULTS_STRONG.search(hl):
        return {"intercepts": []}

    ld = lede(body)
    body_ints = find_intercepts(ld, drop_historical=True)
    for it in hl_ints:
        it["src"] = 0
    for it in body_ints:
        it["src"] = 1

    if FLAGS["headline_metal_from_body"]:
        # "Intersects 983 g/t over 3.4m" (no metal) is the body's "983 g/t
        # Silver Over 3.44 Metres": the body names the metal the headline omits.
        for it in hl_ints:
            if it.get("metal_how") == "explicit":
                continue
            for bi in body_ints:
                if bi.get("metal_how") == "explicit" and abs(bi["grade"] - it["grade"]) < 0.005 \
                        and abs(bi["length_m"] - it["length_m"]) <= max(0.06, 0.02 * it["length_m"]) \
                        and bi["unit"] == it["unit"]:
                    it["metal"] = bi["metal"]
                    it["metal_how"] = "from_body"
                    break

    intercepts, seen = [], set()
    for it in hl_ints + body_ints:
        key = (round(it["length_m"], 1), round(it["grade"], 2), it["metal"])
        if key in seen:
            continue
        seen.add(key)
        intercepts.append(it)

    if not intercepts:
        return {"intercepts": []}
    if FLAGS["score"]:
        _stamp_tiers(intercepts)
    if FLAGS["sample_type"]:
        pl = _prep(ld)
        for it in intercepts:
            it["sample_type"] = classify_sample(
                hl, _prep(hl) if it["src"] == 0 else pl, it["pos"])
            if FLAGS["score"] and it.get("tier") is not None:
                # a drill intercept outranks a channel/grab sample in the same tier
                it["tier"] = it["tier"] * 2 + (0 if it["sample_type"] == "surface" else 1)
    intercepts.sort(key=score_intercept, reverse=True)
    top = intercepts[0]
    return {
        "intercepts":   intercepts,
        "top":          top,
        "top_summary":  format_intercept(top),
        "top_grade":    top.get("grade"),
        "top_length_m": top.get("length_m"),
        "top_unit":     top.get("unit"),
        "top_metal":    top.get("metal"),
        "top_hole_id":  find_hole_id(hl) or find_hole_id(ld),
        "project":      find_project(hl, body),
        "sample_type":  top.get("sample_type"),
    }

# ---------------------------------------------------------------- self-test --
# Every headline below is real, taken from the stored corpus.

FIND_TEST = [
    # (headline, expected length_m, expected grade, expected metal)
    ("Appia Reports Diamond Drilling on ULTRA HARD ROCK Carbonatite Target "
     "Intercepts 300m at 2.55% TREO", 300.0, 2.55, "TREO"),
    ("Beyond Lithium Intersects 2.30% Li2O over 3.84m in Wider Pegmatites",
     3.84, 2.30, "Li2O"),
    ("E-Power Drills 23.97 % Cg over 5.15 Metres at the Tetepisca Graphite Property",
     5.15, 23.97, "Cg"),
    ("Patriot Gold's Bruner Project Intersects 25.9 Meters Grading 2.37 g/tonne Gold",
     25.9, 2.37, "Au"),
    ("Silverco Mining Intersects 1,712 g/t AgEq over 1.4 metres", 1.4, 1712.0, "AgEq"),
    ("Thunder Gold Intersects 661.5 Metres of Continuous Gold Mineralization "
     "Averaging 0.554 g/t Au", 661.5, 0.554, "Au"),
    ("Apex Drills 4.48% REO over 8.0 m and 5.27% REO over 10.2 m", 8.0, 4.48, "REO"),
    ("Great Atlantic Resources First Hole Intersects 238 g/t Gold over 0.40 m",
     0.40, 238.0, "Au"),
    ("Volta Drills Widest TREO-Mineralized Interval to Date 0.95% TREO over 438.9m",
     438.9, 0.95, "TREO"),
    # an article between the connector and the number is still an intercept
    ("Glenstar Intersects over 30% Zinc and 5.7 oz/t Silver Within a 4.5 m Interval",
     4.5, 5.7, "Ag"),
    ("Company Reports 12.4 g/t Au over the 8.5 metre Main Zone", 8.5, 12.4, "Au"),
    # regressions: these already worked in v1 and must keep working
    ("NexGold Intersects 14.10 g/t Gold Over 6.0 Metres", 6.0, 14.10, "Au"),
    ("Eagle Plains Expands George Lake Deposit, Reports 3.48% Zn+Pb over 45.1m",
     45.1, 3.48, "Zn+Pb"),
]

# 287 ft is 87.4776 m; checked separately so the conversion is explicit.
FEET_TEST = ("Edge Copper Intersects 287 ft at 0.73% Total Copper", 87.4776, 0.73)

REJECT_TEST = [
    # 21% gold is 210,000 g/t. These are numbers that happened to sit near a
    # length, and v2.1 stored all three.
    ("SIGNIFICANT GALLIUM AND SCANDIUM CONFIRMED AT LA BLACHE",
     "The sample returned 83.70% of the total over 73 m of strike."),
    ("Carlyle Commodities Provides Update at Newton Gold Silver Project",
     "The Company now owns 100.00% of the property, which covers 1000 m of strike."),
    # a plan, with a real old intercept quoted in the body
    ("Leocor Gold Mobilizes for Upcoming Drill Program at the Baie Verte Project",
     "Previously reported results include 10.20 g/t Au over 1.52 m from the 2023 programme."),
    ("GLENSTAR RECEIVES DRILL PERMIT FOR PHASE 2 PROGRAM AT GREEN MONSTER PROJECT",
     "Phase 1 drilling returned 3.77% Cu over 1.18 m. Phase 2 will follow."),
    ("Bayridge Resources Receives Drilling Permit for Waterbury East Project",
     "Historic drilling returned 324.00 g/t U over 0.6 m."),
    ("Headwater Gold Announces Drill Plan to Offset High-Grade Gold Discovery",
     "The 2024 programme previously reported 6.34 g/t Au over 14.54 m."),
    ("FATHOM ANTICIPATES GOCHAGER LAKE EXPLORATION PERMIT WEEK OF JANUARY 23",
     "Historic drillhole I-12 that was drilled in 1966 returned 0.58% Ni over 290.4 m."),
    # nothing to find at all
    ("Scottie Announces $27 Million Non-Brokered Financing", ""),
    ("Company Provides Corporate Update", "The Company continues to advance its projects."),
]

PROJECT_TEST = [
    ("Glenstar Ventures Granted Permit to Conduct Drilling on Its Green Monster Project",
     "Green Monster"),
    ("Drilling at the Tetepisca Graphite Property returned strong grades", "Tetepisca Graphite"),
    # these produced sentence fragments in v1 and must now produce nothing
    ("Antimony Closes Offering for exploration on its Bald Hill Antimony Project",
     "Bald Hill Antimony"),
    ("Mobilization Underway for Largest Work Program in Company History", None),
]


# ---- v2.4 cases. Every string below is real corpus text (headline, or a body
# excerpt quoted verbatim apart from whitespace). Each names the change it guards.
FIND_TEST_V24 = [
    # (change, headline, body, length_m, grade, metal)
    ("metal_boundary",
     "Kennecott Intersects 1.7 Meters of 69.4 Grams Per Tonne Gold and 23.61 Meters of 2.19% "
     "Copper at American Pacific Mining Corp's Madison Copper-Gold Project in Montana",
     "", 23.61, 2.19, "Cu"),
    ("units_spelled", "Kennecott Intersects 1.7 Meters of 69.4 Grams Per Tonne Gold and 23.61 Meters of 2.19% "
     "Copper at American Pacific Mining Corp's Madison Copper-Gold Project in Montana", "", 1.7, 69.4, "Au"),
    ("units_spelled", "Snowline Gold Drills 534.5 Metres of 0.62 Grams Per Tonne Gold Along Northern Edge of "
     "Its Valley Deposit and Intersects RIRGS Mineralization at Gracie Target, Rogue Project, Yukon",
     "", 534.5, 0.62, "Au"),
    ("units_spelled", "Maxtech Drills 5.3 Grams Au over 3.8 Meters At St Anthony Gold Mine Property",
     "", 3.8, 5.3, "Au"),
    ("units_spelled", "Bunker Hill on Track for June Restart of Operations",
     "Drillhole BHE26-01 returns:\n• 2.3 ft at 11.1 oz/ton silver and 28.4% lead, in broader vein zone",
     0.70104, 11.1, "Ag"),
    ("metal_infer", "Kuya Silver Expands Strike Length of Surface Mineralization at the Campbell-Crawford Area",
     "The southerly vein at Campbell-Crawford is currently interpreted to be the surface exposure of the "
     "Angus Vein, which was drilled in early 2023 with silver assays of 15,372 g/t over 3.34 m (discovery "
     "hole 23-SK-08)", 3.34, 15372.0, "Ag"),
    ("metal_infer", "FIRST ATLANTIC NICKEL EXPANDS RPM ZONE TO 750 METERS IN WIDTH",
     "This results in an average DTR nickel grade of 0.12% and overall recovery of 51.59% from an "
     "average starting grade of 0.24% over 1,763 meters of continuously sampled core.", 1763.0, 0.24, "Ni"),
    ("metal_infer", "Bayhorse Silver Assay Returns 0.61% Copper Average From Two Assay Samples Over 1.5 M "
     "(5ft) Averaging 6100 g/t (0.61% Cu ) Base Metals Mineralization", "", 1.5, 6100.0, "Cu"),
    ("number_bounds", "XXIX Intersects 32.7 g/t Gold, 81.4 g/t Silver and .95% Copper over 7.5 Metres at Cooke",
     "", 7.5, 0.95, "Cu"),
    ("number_bounds", "Skyharbour Intersects High-Grade Uranium",
     "Hole ML24-13 intersected 0.14% U3O8 over 6.4 m starting at 268.5 m, including 0. 63% U3O8 over "
     "1.0 m at 269.0 m", 1.0, 0.63, "U3O8"),
    ("vocab", "IDEX Metals Confirms Significant Tungsten Enrichment at Freeze, Including 180.5 Metres of "
     "0.11% WO₃, 72.2 Metres of 0.13% WO₃", "", 180.5, 0.11, "WO3"),
    ("vocab", "Widest and Highest-Grade Caesium Intercepts to Date at Vega including 28.0 m at 8.05% Cs2O "
     "and 2.2 m at 26.48% Cs2O", "", 28.0, 8.05, "Cs2O"),
    ("vocab", "First Phosphate Drills 9.44% P2O5 Over 89.10 m at Its Begin-Lamarche Project", "",
     89.10, 9.44, "P2O5"),
    ("vocab", "Scandium Canada Intersects 124.9 m at 232 ppm Sc₂O₃ at Crater Lake", "",
     124.9, 232.0, "Sc2O3"),
    ("vocab", "SILVER STORM DRILLS 473 g/t Ag.Eq(1,2) OVER 3.6 m AND 137 g/t Ag.Eq OVER 12.0 m", "",
     12.0, 137.0, "AgEq"),
    ("vocab", "Intrepid Metals Intersects 177.25m of 0.58% Copper Equivalent1 from Ringo Zone at Corral Copper",
     "", 177.25, 0.58, "CuEq"),
    ("vocab", "Marimaca Extends Pampa Medina Norte Discovery – Intersects 68m at 1.20% and 40m at 1.07% CuT "
     "in Dominantly Oxides", "", 40.0, 1.07, "Cu"),
    ("vocab", "CanAlaska Announces Best Uranium Intersection to Date",
     "WMA094-04 has been completed and intersected 4.9 metres at 3.04% eU\n3\nO\n8\n, including 1.5 metres",
     4.9, 3.04, "eU3O8"),
    ("connective", "Fireweed Intersects 30 m True Width of 33.2% Zinc Equivalent in 115 m Step-Out at Tom South",
     "", 30.0, 33.2, "ZnEq"),
    ("connective", "CSE Stock Symbol GCC Golden Cariboo Intersects 136.51m (447.87 ft) of 1.46 g/t Gold Near "
     "Surface at New Discovery in the Halo Zone", "", 136.51, 1.46, "Au"),
    ("connective", "Irving Resources Intersects High-Grade Au-Ag Veins at Omui Mine Site",
     "o 7.39 gpt Au and 10.07 gpt Ag (7.52 gpt Au eq) over 8.58m within 4.44 gpt Au", 8.58, 7.39, "Au"),
    ("connective", "Anteros Metals Reports Assay Results from RM26-01",
     "• 1.00 m from 606.25 to 607.25 m grading 2.27 g/t Pt+Pd (1.02 ppm Pt, 1.25 ppm Pd), with 1660 ppm Cu",
     1.0, 2.27, "Pt+Pd"),
    ("connective", "Carolina Rush Reports Elevated Molybdenum in Deepest Hole Drilled at Brewer",
     "Occurs in discrete zones (e.g. 7.5 meters @276 ppm Mo from 479\n- 486.5m)", 7.5, 276.0, "Mo"),
    ("chain", "Québec Nickel Corp. Intersects 0.44% Ni, 0.51% Cu and 0.69 G/t Pt-Pd-Au Over 18.50 Metres "
     "at Its Ducros Project, Abitibi Québec", "", 18.5, 0.44, "Ni"),
    ("chain", "Hercules Metals Intersects 420 m of 0.60% Copper and 6 g/t Ag, Including 113 m of 1.38% "
     "Copper and 14 g/t Ag at the Leviathan Porphyry System", "", 420.0, 6.0, "Ag"),
    ("chain", "Nine Mile Metals Announces Certified Drill Results Of (10.12 % Cu, 1.00 % Zn, 1.41 % Pb, "
     "91.47 G/T Ag, And 0.84 G/T Au) Over 15.10m", "", 15.10, 10.12, "Cu"),
    ("units_spelled", "Angie Drilling Returns Significant Near Surface Molybdenum Intersections in the Upper "
     "Level of a Chilean Porphyry Discovery", "Drilling encountered significant intervals \nof molybdenum "
     "(\u201cMo\u201d or \u201cmoly\u201d) with drill hole AAS-02 returning 26 metres (\u201cm\u201d) grading 713 "
     "\nparts per million (\u201cppm\u201d) Mo including 8 m, at the end of the hole, grading 1,208 ppm Mo .",
     26.0, 713.0, "Mo"),
    ("headline_metal_from_body", "Exploration Drilling Intersects 983 g/t over 3.4m at Galena, Driving Growth "
     "of Potential New Mining Zone", "New 034 Vein Drilling at Galena Complex Highlighted by Intersection of "
     "983 g/t Silver \nOver 3.44 Metres", 3.4, 983.0, "Ag"),
    ("ceiling_silver", "Nord Intersects 20,675 g/t Silver over 0.3 Metres and 10,413 g/t Silver over 0.3 "
     "Metres at Castle East", "", 0.3, 20675.0, "Ag"),
]

# (change, headline, body, (length_m, grade) that must NOT be produced, or None = no intercept at all)
REJECT_TEST_V24 = [
    ("metal_infer", "First Phosphate Intersects 92.5 m of 11.82% Igneous Phosphate Starting at Surface at Its "
     "Begin-Lamarche Project in Saguenay-Lac-St-Jean, Quebec, Canada", "", None),
    ("metal_infer", "Green River Gold Corp. Continues to Expand Its Critical Minerals Discovery at the Quesnel "
     "Nickel Project Hitting 79 Meters of 20.1% Magnesium, 0.177% Nickel, 0.138% Chromium and 0.01% Cobalt",
     "", (79.0, 20.1)),
    ("number_bounds", "XXIX Intersects 32.7 g/t Gold, 81.4 g/t Silver and .95% Copper over 7.5 Metres at Cooke",
     "", (7.5, 95.0)),
    ("connective", "Bam Bam Drilling Returns Significant Copper and Silver at Majuba Hill",
     "including 5 feet from 242 to 247 feet @ 1.26% Cu and 17.4 ppm Ag \nand 2 feet from 257 to 259 feet "
     "@ 4.22% Cu and 103 ppm Ag", (78.9432, 4.22)),
    ("connective", "Opawica Explorations Intersects a 60 Meter Mineralized Zone at its Bazooka Property",
     "exhibited strong silicification and sericitization with visible arsenopyrite, with an XRF reading at "
     "196 m of 66 g/t Au.", None),
    ("connective", "Nova Pacific Metals Extends the Strike Length of the Lara Project to 17 km",
     "A jasper-rich ± magnetite iron formation, with up to\n\n0.72 g/t Au, 0.51% Cu\n\n\n2.9 g/t Ag\n\n"
     "(different samples) is within 250 m of the property to the west (ARIS 16802).", None),
    ("connective", "Sitka Drills 19.3 Metres of 5.04 g/t Gold Within 94.0 m of 1.79 g/t Gold, Expanding "
     "High-Grade Gold Zone", "", (94.0, 5.04)),
    ("connective", "NGEx Drills 19.00m at 25.84% CuEq Within 57.75m at 9.41% CuEq at Lunahuasi", "", (57.75, 25.84)),
    ("historical_ref", "Sirios discovers high-potential gold halo in western sector of Aquilon project",
     "Some drill intercepts from the Aquilon project are among the highest grades obtained in Quebec, "
     "including 12,906.5 g/t Au over 0.2 m (Lingo showing), 3,527.4 g/t Au over 0.4 m (Moman showing) "
     "(ref. press releases of 2021)", (0.2, 12906.5)),
]

# (change, headline, body, expected top metal)
TOP_TEST_V24 = [
    ("score", "Golden Independence Intersects 1.11 g/t Gold and 7.8 g/t Silver over 20 Feet at Independence "
     "Project", "", "Au"),
    ("score", "Gladiator Intersects 40.0m @ 1.98% Cu, 0.31 g/t Au, 13.29 g/t Ag & 920 ppm Mo Adding Broad "
     "High-Grade Copper and Molybdenum at Cowley - newsfilecorp.com", "", "Cu"),
    ("vocab", "Nuinsco Announces Seventh Intersection of More than 100m of Continuous Critical Elements & "
     "Phosphate Mineralization at Prairie Lake", "of note this most recent intersection contains 118.6m "
     "grading more than 2000g/t combined REEs (see below for tabulated individual REE values)", "REE"),
]

SAMPLE_TEST_V24 = [
    ("Precipitate’s Latest Trench Sampling Yields 7.2 g/t Gold over 2.0m, Further Expanding the CN Zone "
     "at the Juan de Herrera Project, Dominican Republic", "surface"),
    ("NexGold Intersects 14.10 g/t Gold Over 6.0 Metres", "drill"),
]

PROJECT_TEST_V24 = [
    ("Golden Independence Intersects 1.89 g/t Gold And 6.9 g/t Silver Over 50 Feet At Independence Project",
     "Independence"),
    ("A.I.-Targeted Infill Drilling Intersects 9.01 g/t Au over 19.0 m at STLLR Gold’s Tower Gold Project",
     "Tower Gold"),
]


def self_test_v24(verbose: bool = True) -> int:
    bad = 0
    for change, hl, body, L, G, M in FIND_TEST_V24:
        its = extract(hl, body).get("intercepts") or []
        hit = any(abs(i["length_m"] - L) < 0.05 and abs(i["grade"] - G) < 0.005
                  and i["metal"].lower() == M.lower() for i in its)
        bad += not hit
        if verbose or not hit:
            got = ", ".join(f"{i['length_m']:g}m/{i['grade']:g}{i['unit']}/{i['metal']}" for i in its[:4])
            print(f"  {'ok  ' if hit else 'FAIL'}  v2.4 find [{change}] {hl[:44]:<44} -> {got[:60]}")
    for change, hl, body, forbid in REJECT_TEST_V24:
        its = extract(hl, body).get("intercepts") or []
        if forbid is None:
            ok = not its
        else:
            ok = not any(abs(i["length_m"] - forbid[0]) < 0.05 and abs(i["grade"] - forbid[1]) < 0.005
                         for i in its)
        bad += not ok
        if verbose or not ok:
            got = ", ".join(f"{i['length_m']:g}m/{i['grade']:g}{i['unit']}/{i['metal']}" for i in its[:3])
            print(f"  {'ok  ' if ok else 'FAIL'}  v2.4 reject [{change}] {hl[:44]:<44} {got[:50]}")
    for change, hl, body, want in TOP_TEST_V24:
        got = extract(hl, body).get("top_metal")
        ok = got == want
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  v2.4 top [{change}] {hl[:48]:<48} {got!r} (wanted {want!r})")
    for hl, want in SAMPLE_TEST_V24:
        got = extract(hl, "").get("sample_type")
        ok = got == want
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  v2.4 sample_type {hl[:48]:<48} {got!r} (wanted {want!r})")
    for src, want in PROJECT_TEST_V24:
        got = find_project(src, "")
        ok = got == want
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  v2.4 project {got!r:<26} (wanted {want!r})")
    total = (len(FIND_TEST_V24) + len(REJECT_TEST_V24) + len(TOP_TEST_V24)
             + len(SAMPLE_TEST_V24) + len(PROJECT_TEST_V24))
    if verbose:
        print(f"\nv2.4: {total - bad}/{total} passed")
    return bad



def self_test(verbose: bool = True) -> int:
    bad = 0
    for hl, want_len, want_grade, want_metal in FIND_TEST:
        o = extract(hl, "")
        its = o.get("intercepts") or []
        hit = any(abs(i["length_m"] - want_len) < 0.05
                  and abs(i["grade"] - want_grade) < 0.005
                  and i["metal"].lower() == want_metal.lower() for i in its)
        bad += not hit
        if verbose or not hit:
            got = ", ".join(f"{i['length_m']:g}m/{i['grade']:g}{i['unit']}/{i['metal']}" for i in its[:3])
            print(f"  {'ok  ' if hit else 'FAIL'}  find  {hl[:58]:<58} -> {got[:52]}")
            if not hit:
                print(f"        WANTED {want_len}m / {want_grade} / {want_metal}")

    hl, want_len, want_grade = FEET_TEST
    its = extract(hl, "").get("intercepts") or []
    hit = any(abs(i["length_m"] - want_len) < 0.05 and abs(i["grade"] - want_grade) < 0.005
              for i in its)
    bad += not hit
    if verbose or not hit:
        print(f"  {'ok  ' if hit else 'FAIL'}  feet  287 ft -> {want_len:.4f} m")

    for hl, body in REJECT_TEST:
        o = extract(hl, body)
        ok = not o.get("intercepts")
        bad += not ok
        if verbose or not ok:
            got = (o.get("top_summary") or "") if not ok else ""
            print(f"  {'ok  ' if ok else 'FAIL'}  reject {hl[:56]:<56} {got}")

    for src, want in PROJECT_TEST:
        got = find_project(src, "")
        ok = (got == want)
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  project {str(got)!r:<26} (wanted {want!r})")

    total = len(FIND_TEST) + 1 + len(REJECT_TEST) + len(PROJECT_TEST)
    if verbose:
        print(f"\n{total - bad}/{total} passed")
    bad += self_test_v24(verbose)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(self_test())
