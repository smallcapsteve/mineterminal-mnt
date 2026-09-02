"""drill_extract.py — pull structured intercept data from drill release events.

For each event tagged "Drill Results", parse the headline + body for:
  intercepts: list of (length_m, grade, unit, metal, hole_id?)
  top_intercept: highest grade*length composite
  project: e.g. "Tesla Zone", "Begin-Lamarche", "Goose Project"

Events with no parseable intercept are SKIPPED (drill plans, program
announcements, etc. — same category but not actual results).
"""
from __future__ import annotations
import re
from typing import Iterable

# ---------- intercept patterns ----------

# Metal/commodity tokens — order matters (longer first)
_METALS = (
    "AuEq", "CuEq", "NiEq", "ZnEq",
    "U3O8", "REE", "Sb", "Sn", "Mo",
    "Au", "Ag", "Cu", "Ni", "Zn", "Pb", "Co", "U", "Mn", "V", "Li", "W",
)

# Friendly names → short symbol (used for "Gold", "Silver", etc.)
_NAME_TO_SYMBOL = {
    "gold": "Au", "silver": "Ag", "copper": "Cu", "nickel": "Ni",
    "zinc": "Zn", "lead": "Pb", "cobalt": "Co", "uranium": "U",
    "molybdenum": "Mo", "manganese": "Mn", "vanadium": "V",
    "lithium": "Li", "tungsten": "W", "tin": "Sn", "antimony": "Sb",
    "platinum": "Pt", "palladium": "Pd",
    "copper equivalent": "CuEq", "gold equivalent": "AuEq",
    "nickel equivalent": "NiEq", "zinc equivalent": "ZnEq",
}

# Pattern A: "X.X g/t Au over Y.Y m"  /  "X.X% Cu over Y.Y m"
_RE_GRADE_OVER_LENGTH = re.compile(
    r"(?P<grade>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>g/t|gpt|%|ppm|gms)\s*"
    r"(?P<metal>AuEq|CuEq|NiEq|ZnEq|U3O8|REE|Au|Ag|Cu|Ni|Zn|Pb|Co|U|Mn|V|Li|W|Mo|Sb|Sn|Pt|Pd|"
    r"gold|silver|copper|nickel|zinc|lead|cobalt|uranium|molybdenum|manganese|"
    r"vanadium|lithium|tungsten|tin|antimony|platinum|palladium|copper\s+equivalent|"
    r"gold\s+equivalent)\s+"
    r"(?:over|across)\s+"
    r"(?P<length>\d+(?:\.\d+)?)\s*"
    r"(?:m|metres|meters|metre|meter)\b",
    re.I,
)

# Pattern B: "Y.Y m @ X.X g/t Au"  /  "Y.Y m of X.X g/t Au"
_RE_LENGTH_AT_GRADE = re.compile(
    r"(?P<length>\d+(?:\.\d+)?)\s*(?:m|metres|meters|metre|meter)\b"
    r"\s*(?:@|of|grading|at)\s*"
    r"(?P<grade>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>g/t|gpt|%|ppm|gms)\s*"
    r"(?P<metal>AuEq|CuEq|NiEq|ZnEq|U3O8|REE|Au|Ag|Cu|Ni|Zn|Pb|Co|U|Mn|V|Li|W|Mo|Sb|Sn|Pt|Pd|"
    r"gold|silver|copper|nickel|zinc|lead|cobalt|uranium|molybdenum|manganese|"
    r"vanadium|lithium|tungsten|tin|antimony|platinum|palladium)",
    re.I,
)

# Pattern C: headline-style "X.X g/t over Y.Y m" (metal omitted, deduce later)
_RE_HEADLINE_OVER = re.compile(
    r"(?P<grade>\d+(?:\.\d+)?)\s*(?P<unit>g/t|%)\s+"
    r"(?P<metal>gold|silver|copper|nickel|zinc|lead|cobalt|uranium)?\s*"
    r"(?:over|across)\s+(?P<length>\d+(?:\.\d+)?)\s*(?:m|metres|meters)",
    re.I,
)

_RE_HOLE = re.compile(
    r"\b(?:Hole|drillhole|drill\s+hole|DDH|DH|HQ|RC|BH)\s*[#:]?\s*"
    r"([A-Z]{1,5}[\-: ]?\d{1,4}[\-A-Z0-9]*)\b",
    re.I,
)


def _normalize_metal(s: str) -> str:
    s = (s or "").strip().lower()
    return _NAME_TO_SYMBOL.get(s, s.title() if len(s) <= 3 else s)


def find_intercepts(text: str) -> list[dict]:
    """Return list of intercept dicts found in text."""
    out = []
    seen_keys = set()
    for rx in (_RE_GRADE_OVER_LENGTH, _RE_LENGTH_AT_GRADE, _RE_HEADLINE_OVER):
        for m in rx.finditer(text or ""):
            try:
                grade = float(m.group("grade"))
                length = float(m.group("length"))
            except (ValueError, IndexError):
                continue
            unit_raw = (m.group("unit") or "").lower().replace("gpt", "g/t")
            try:
                metal_raw = m.group("metal") or "Au"
            except IndexError:
                metal_raw = "Au"
            metal = _normalize_metal(metal_raw)
            # Skip implausibly large/small values
            if length < 0.5 or length > 2000:
                continue
            if grade < 0.01 or grade > 100000:
                continue
            # Dedup by (round, round, metal)
            key = (round(length, 1), round(grade, 2), metal)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            out.append({
                "length_m": length,
                "grade":    grade,
                "unit":     "%" if unit_raw == "%" else "g/t",
                "metal":    metal,
            })
    return out


def find_hole_id(text: str) -> str | None:
    if not text:
        return None
    m = _RE_HOLE.search(text)
    if m:
        return m.group(1).upper()
    return None


# ---------- project name ----------

_RE_PROJECT = re.compile(
    r"\b(?:at|from|on|within|across)\s+(?:the\s+)?"
    r"([A-Z][A-Za-z0-9' \-]{2,50}?)\s+"
    r"(?:Property|Project|Prospect|Deposit|Discovery|Zone|Vein|Trend|Target|Camp|Mine)\b",
)
_RE_PROJECT_BARE = re.compile(
    r"\b([A-Z][A-Za-z0-9' \-]{2,50}?)\s+(?:Property|Project|Prospect|Deposit|Discovery)\b"
)


def find_project(headline: str, body: str) -> str | None:
    for src in (headline or "", (body or "")[:1500]):
        m = _RE_PROJECT.search(src)
        if m:
            name = m.group(1).strip().rstrip(",;.")
            # Reject obviously-not-projects
            if any(w in name.lower() for w in (
                "company", "corporation", "the company", "ceo", "president",
                "shareholders", "annual general", "press release", "joint venture",
                "agreement", "letter of intent",
            )):
                continue
            if 3 <= len(name) <= 60:
                return name
    for src in (headline or "", (body or "")[:1500]):
        m = _RE_PROJECT_BARE.search(src)
        if m:
            name = m.group(1).strip().rstrip(",;.")
            if any(w in name.lower() for w in (
                "company", "corporation", "the company",
                "press release", "joint venture",
            )):
                continue
            if 3 <= len(name) <= 60:
                return name
    return None


# ---------- top intercept selection ----------

def score_intercept(it: dict) -> float:
    """Composite score for ranking — grade × length normalized for unit."""
    g = it.get("grade") or 0
    l = it.get("length_m") or 0
    unit = (it.get("unit") or "").lower()
    # Convert % to g/t-equivalent (rough, for ranking only): 1% = 10000 g/t for base metals
    # But for ranking just use raw multiplier; results are within-event comparison anyway
    return g * l


def format_intercept(it: dict) -> str:
    """e.g. '7.97% CuEq / 14.4m'  or  '6.10 g/t Au / 19.0m'"""
    g = it.get("grade")
    l = it.get("length_m")
    u = it.get("unit") or "g/t"
    m = it.get("metal") or ""
    if g is None or l is None:
        return ""
    # Format grade: integer % vs decimal g/t
    if u == "%":
        gstr = f"{g:.2f}%"
    else:
        gstr = f"{g:.2f} g/t"
    return f"{gstr} {m} / {l:g}m"


def extract(headline: str, body: str) -> dict:
    """Return all extracted fields from a drill release."""
    text = (headline or "") + "\n" + (body or "")
    intercepts = find_intercepts(text)
    if not intercepts:
        return {"intercepts": []}
    intercepts.sort(key=score_intercept, reverse=True)
    top = intercepts[0]
    return {
        "intercepts":     intercepts,
        "top":            top,
        "top_summary":    format_intercept(top),
        "top_grade":      top.get("grade"),
        "top_length_m":   top.get("length_m"),
        "top_unit":       top.get("unit"),
        "top_metal":      top.get("metal"),
        "top_hole_id":    find_hole_id(headline) or find_hole_id((body or "")[:3000]),
        "project":        find_project(headline, body),
    }
