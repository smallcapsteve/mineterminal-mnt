"""drill_extract.py - pull structured intercept data from drill release events.

For each event tagged "Drill Results", parse the headline + body for:
  intercepts: list of (length_m, grade, unit, metal)
  top_intercept: highest grade*length composite
  project: e.g. "Tesla Zone", "Begin-Lamarche", "Goose Project"

Events with no parseable intercept are SKIPPED (drill plans, program
announcements, etc. - same category but not actual results).

v2, 2026-09-14. v1 read the ENTIRE body, so it harvested intercepts that the
release was merely quoting. Measured against the 1,805 stored rows:

    359  winning intercept sat >2,500 characters into the body
    143  winning intercept sat beside "historic" / "previously reported"
     52  headline was a plan, not results

The visible consequence: GSTR.CN rendered the SAME intercept, 3.77% Cu / 1.18m,
as four separate drill results - under "RECEIVES DRILL PERMIT", "PHASE 2
COMMENCES", "PHASE 2 COMPLETED" and "HIRES ALLOY DRILLING" - because every one
of those releases repeated it in the boilerplate. FNI.CN had rows built on a
hole drilled in 1966.

So v2 reads the headline, plus the LEDE of the body only (above "About the
Company" and the disclaimers), drops any intercept sitting next to historical
language, and refuses a release whose headline announces a plan rather than a
result.

    python3 drill_extract.py     # run the self-test
"""
from __future__ import annotations
import re
import sys

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
}

# Longest first so "CuEq" wins over "Cu" and "TREO" over "RE".
_METAL_RX = (
    r"AuEq|CuEq|NiEq|ZnEq|AgEq|PbEq|SnEq"
    r"|TREO|REO|TREE|REE|U3O8|eU3O8|Li2O|Ta2O5|Nb2O5|V2O5|WO3|MoS2"
    r"|Au|Ag|Cu|Ni|Zn|Pb|Co|Mo|Sb|Sn|Pt|Pd|Cg|Mn|Li|Ga|Ge|Sc|Te|Bi|Cs|Rb|W|V|U"
    r"|total\s+copper|total\s+rare\s+earth"
    r"|gold|silver|copper|nickel|zinc|lead|cobalt|uranium|molybdenum|manganese"
    r"|vanadium|lithium|tungsten|tin|antimony|platinum|palladium|graphite"
    r"|copper\s+equivalent|gold\s+equivalent|silver\s+equivalent"
)

# "1,712 g/t" - a comma is a thousands separator, not the end of the number.
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"

# g/tonne is as common as g/t in Canadian releases and was not listed.
_UNIT = r"g/tonne|g/t|gpt|g\s*/\s*t|%|ppm|ppb|gms|opt|oz/t|kg/t"

_LEN_UNIT = r"metres|meters|metre|meter|m|feet|foot|ft"

# "3.48% Zn+Pb", "2.8 g/t PGM+Au", "1.2% Cu/Au" - one grade, two metals.
_METAL_PAIR = rf"(?:{_METAL_RX})(?:\s*[+/]\s*(?:{_METAL_RX}))?"


def _num(s: str) -> float:
    return float((s or "0").replace(",", ""))


def _to_metres(value: float, unit: str) -> float:
    return value * 0.3048 if (unit or "").lower() in ("ft", "feet", "foot") else value


# Pattern A: "2.30% Li2O over 3.84m" / "23.97 % Cg over 5.15 Metres"
_RE_GRADE_OVER_LENGTH = re.compile(
    rf"(?P<grade>{_NUM})\s*(?P<unit>{_UNIT})\s*(?P<metal>{_METAL_PAIR})"
    rf"(?:\s+[A-Za-z\-]+){{0,3}}?\s+(?:over|across|within)(?:\s+(?:a|an|the))?\s+"
    rf"(?P<length>{_NUM})\s*(?P<lenunit>{_LEN_UNIT})\b",
    re.I)

# Pattern B: "300m at 2.55% TREO" / "287 ft at 0.73% Total Copper"
#            "661.5 Metres of Continuous Gold Mineralization Averaging 0.554 g/t Au"
# Up to four filler words are allowed between the length and the grade; that is
# what "Metres of Continuous Gold Mineralization Averaging" needs, and it is
# bounded so it cannot wander into the next sentence.
_RE_LENGTH_AT_GRADE = re.compile(
    rf"(?P<length>{_NUM})\s*(?P<lenunit>{_LEN_UNIT})\b"
    rf"(?:\s+(?:of|@|at|grading|averaging|returning|containing|with|assaying))"
    rf"(?:\s+[A-Za-z\-]+){{0,4}}?\s+"
    rf"(?P<grade>{_NUM})\s*(?P<unit>{_UNIT})\s*(?P<metal>{_METAL_PAIR})?",
    re.I)

# Pattern C: "238 g/t Gold over 0.40 m" with the metal optional
_RE_HEADLINE_OVER = re.compile(
    rf"(?P<grade>{_NUM})\s*(?P<unit>{_UNIT})\s+(?P<metal>{_METAL_PAIR})?\s*"
    rf"(?:over|across|within)(?:\s+(?:a|an|the))?\s+(?P<length>{_NUM})\s*(?P<lenunit>{_LEN_UNIT})\b",
    re.I)

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

# The release is telling you about results it actually has. Deliberately
# narrow: v2 used a broad list that matched the bare word "Drill" inside "Drill
# Program" and "Discovery" inside "Drill Plan to Offset High-Grade Gold
# Discovery", so every plan release overrode its own plan test.
_RE_RESULTS_STRONG = re.compile(
    r"(?i)\b(intersect\w*|intercept\w*|assay\w*|grading|returns?|returned"
    r"|hits?|encounter\w*|yields?|step[\-\s]out\s+results?|drill\s+results?"
    r"|final\s+results?|results?\s+from\s+(?:hole|the\s+\w+\s+program))\b")

# The release is telling you about drilling it has not done yet.
_RE_PLAN_ONLY = re.compile(
    r"(?i)\b(mobiliz\w*|commenc\w*|begins?|beginning|initiat\w*|prepar\w*|plans?\s+to"
    r"|upcoming|permit\w*|finaliz\w*|engages?|hires?|anticipat\w*|to\s+commence"
    r"|set\s+to\s+drill|about\s+to|schedul\w*|award\w*\s+contract|contracts?\s+\w+\s+drilling)\b")

# Gold is quoted in g/t. A percentage grade of gold above a few percent is not
# a grade at all, it is a recovery rate, an ownership stake or a coincidence.
_MAX_PCT = {"au": 5.0, "ag": 20.0, "pt": 5.0, "pd": 5.0, "u": 30.0}
_MAX_BY_UNIT = {"%": 100.0, "g/t": 20000.0, "ppm": 100000.0,
                "ppb": 1000000.0, "opt": 600.0, "oz/t": 600.0, "kg/t": 50.0}


def _plausible(grade: float, unit: str, metal: str) -> bool:
    u = (unit or "").lower()
    m = (metal or "").split("+")[0].strip().lower()
    cap = _MAX_BY_UNIT.get(u)
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
    "treo": "TREO", "reo": "REO", "ree": "REE", "tree": "TREE",
    "li2o": "Li2O", "u3o8": "U3O8", "eu3o8": "eU3O8", "ta2o5": "Ta2O5",
    "nb2o5": "Nb2O5", "v2o5": "V2O5", "wo3": "WO3", "mos2": "MoS2",
    "aueq": "AuEq", "cueq": "CuEq", "nieq": "NiEq", "zneq": "ZnEq",
    "ageq": "AgEq", "pbeq": "PbEq", "sneq": "SnEq", "cg": "Cg",
}


def _normalize_one(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip().lower())
    if s in _NAME_TO_SYMBOL:
        return _NAME_TO_SYMBOL[s]
    if s in _CANON:
        return _CANON[s]
    return s.title() if len(s) <= 3 else s.upper()


def _normalize_metal(s: str) -> str:
    parts = re.split(r"\s*[+/]\s*", (s or "").strip())
    return "+".join(_normalize_one(p) for p in parts if p)


def find_intercepts(text: str, drop_historical: bool = False) -> list[dict]:
    """Intercepts in text. With drop_historical, one sitting next to "historic"
    or "previously reported" is somebody else's result and is left alone."""
    out, seen = [], set()
    t = text or ""
    for rx in (_RE_GRADE_OVER_LENGTH, _RE_LENGTH_AT_GRADE, _RE_HEADLINE_OVER):
        for m in rx.finditer(t):
            try:
                grade = _num(m.group("grade"))
                length = _to_metres(_num(m.group("length")), m.group("lenunit"))
            except (ValueError, IndexError, TypeError):
                continue
            if drop_historical and _RE_HISTORICAL.search(
                    t[max(0, m.start() - HIST_WINDOW):m.end() + HIST_WINDOW]):
                continue
            unit_raw = (m.group("unit") or "").lower().replace(" ", "")
            unit_raw = "g/t" if unit_raw in ("gpt", "g/tonne", "g/t") else unit_raw
            try:
                metal_raw = m.group("metal") or "Au"
            except IndexError:
                metal_raw = "Au"
            metal = _normalize_metal(metal_raw)
            if length < 0.1 or length > 2000:
                continue
            if grade < 0.01 or grade > 100000:
                continue
            if not _plausible(grade, unit_raw, metal):
                continue
            key = (round(length, 1), round(grade, 2), metal)
            if key in seen:
                continue
            seen.add(key)
            out.append({"length_m": length, "grade": grade,
                        "unit": "%" if unit_raw == "%" else unit_raw or "g/t",
                        "metal": metal})
    return out


def find_hole_id(text: str) -> str | None:
    if not text:
        return None
    m = _RE_HOLE.search(text)
    return m.group(1).upper() if m else None


# ---------- project name ----------

# Every captured token must start with a capital, so "Offering for exploration
# on its Bald Hill Antimony" cannot be a project name: "for", "on" and "its"
# are lowercase and stop the capture. 278 of 1,464 project values were sentence
# fragments of exactly that shape.
_PROJ_TOKEN = r"[A-Z][A-Za-z0-9'\u2019\-]*"
_RE_PROJECT = re.compile(
    rf"\b(?:at|from|on|within|across)\s+(?:(?i:the|its|our|a)\s+)*"
    rf"(?P<name>(?:{_PROJ_TOKEN}\s+){{0,3}}{_PROJ_TOKEN})\s+"
    r"(?:Property|Project|Prospect|Deposit|Discovery|Zone|Vein|Trend|Target|Camp|Mine)\b")
_RE_PROJECT_BARE = re.compile(
    rf"\b(?P<name>(?:{_PROJ_TOKEN}\s+){{0,3}}{_PROJ_TOKEN})\s+"
    r"(?:Property|Project|Prospect|Deposit|Discovery)\b")

_PROJECT_STOP = {
    "company", "corporation", "corp", "inc", "ltd", "ceo", "president",
    "shareholders", "annual", "general", "press", "release", "joint", "venture",
    "agreement", "letter", "intent", "offering", "placement", "financing",
    "drilling", "drill", "results", "result", "program", "programme", "phase",
    "exploration", "mobilization", "strike", "identification", "underway",
    "largest", "work", "completion", "update", "news", "its", "the", "and",
    "successful", "maiden", "initial", "new", "further", "additional", "area",
}


def _project_ok(name: str) -> bool:
    toks = [t.lower().strip(".,;'\u2019") for t in (name or "").split()]
    if not 1 <= len(toks) <= 4:
        return False
    if any(t in _PROJECT_STOP for t in toks):
        return False
    return 3 <= len(name) <= 60


def find_project(headline: str, body: str) -> str | None:
    for rx in (_RE_PROJECT, _RE_PROJECT_BARE):
        for src in (headline or "", lede(body, 1500)):
            for m in rx.finditer(src):
                name = m.group("name").strip().rstrip(",;.")
                if _project_ok(name):
                    return name
    return None


# ---------- top intercept selection ----------

def score_intercept(it: dict) -> float:
    return (it.get("grade") or 0) * (it.get("length_m") or 0)


def format_intercept(it: dict) -> str:
    g, l = it.get("grade"), it.get("length_m")
    u = it.get("unit") or "g/t"
    m = it.get("metal") or ""
    if g is None or l is None:
        return ""
    gstr = f"{g:.2f}%" if u == "%" else f"{g:.2f} {u}"
    return f"{gstr} {m} / {l:g}m"


def extract(headline: str, body: str) -> dict:
    """All extracted fields from a drill release, or {"intercepts": []}."""
    hl = headline or ""
    hl_ints = find_intercepts(hl)

    # A release that announces a plan and carries no number of its own is not
    # reporting results, however many old ones its boilerplate repeats.
    if not hl_ints and _RE_PLAN_ONLY.search(hl) and not _RE_RESULTS_STRONG.search(hl):
        return {"intercepts": []}

    body_ints = find_intercepts(lede(body), drop_historical=True)

    intercepts, seen = [], set()
    for it in hl_ints + body_ints:
        key = (round(it["length_m"], 1), round(it["grade"], 2), it["metal"])
        if key in seen:
            continue
        seen.add(key)
        intercepts.append(it)

    if not intercepts:
        return {"intercepts": []}
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
        "top_hole_id":  find_hole_id(hl) or find_hole_id(lede(body)),
        "project":      find_project(hl, body),
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
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(self_test())
