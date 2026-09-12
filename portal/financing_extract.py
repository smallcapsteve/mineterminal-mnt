"""financing_extract.py — extract structured financing data from events.

For each event tagged "Financings", extract:
  kind          : PP, LIFE, FT, BROKERED, NON_BROKERED, BOUGHT_DEAL, MIXED
  role          : announcement | upsize | tranche_close | final_close | amendment | terminated
  tranche_label : first|second|third|final|initial|None
  gross_total   : float dollars (CDN)
  unit_count    : int
  unit_price    : float
  unit_comp     : "share + warrant" | "share + half warrant" | "FT share" | None
  warrant_strike: float
  warrant_term_months: int
  ref_dates     : list[date strings] back-referenced via "further to news release dated X"

A financing lifecycle row in `financings` aggregates one announcement plus
all its tranches/closes/upsizes/amendments. Linkage uses (ticker,
ref_date_match) — close events with "further to news release dated X" find
the announcement whose published_at falls on/near that date.
"""
from __future__ import annotations
import re
from datetime import datetime
from typing import Optional

# ---------- headline-driven role classifiers ----------

_RE_TRANCHE_LABEL = re.compile(
    r"\b(first|second|third|fourth|fifth|sixth|final|initial|interim)\s+tranche\b",
    re.I,
)
_RE_UPSIZE = re.compile(
    r"\b(?:upsiz(?:e|es|ed|ing)|increases?\s+size\s+of|increase\s+to\s+the\s+size)\b",
    re.I,
)
# "increased the [non-brokered] convertible debenture financing from $3M to $3.8M"
_RE_UPSIZE_INCREASED_FROM_TO = re.compile(
    r"\bincreas(?:e|es|ed|ing)\b[\s\S]{0,180}?\bfrom\b[\s\S]{0,80}?(?:CDN?\$?|C\$|US\$|\$)\s*[\d,.]+\s*(?:million|M\b)?[\s\S]{0,30}?\bto\b[\s\S]{0,30}?(?:CDN?\$?|C\$|US\$|\$)\s*([\d,.]+)\s*(million|M\b)?",
    re.I,
)
_RE_AMEND = re.compile(r"\b(?:amends?|amendment\s+to|amends\s+terms\s+of)\b", re.I)
_RE_TERMINATE = re.compile(r"\b(?:terminat(?:e|es|ed|ion)|cancels?\s+(?:offering|placement|financing))\b", re.I)
_RE_CLOSE_VERB = re.compile(
    r"\b(?:close[sd]?|closing|completes?|completed|completion\s+of)\b",
    re.I,
)
_RE_FIN_NOUN = re.compile(
    r"\b(?:private\s+placement|placement|offering|financing|tranche|life\s+offering|"
    r"flow[- ]through|charity\s+flow[- ]through|bought\s+deal|public\s+offering|"
    r"prospectus\s+offering)\b",
    re.I,
)
_RE_ANNOUNCE_VERB = re.compile(
    r"\b(?:announces?|launches?|to\s+(?:offer|conduct|undertake)|to\s+raise|"
    r"plans?\s+to\s+(?:offer|raise|conduct))\b",
    re.I,
)

# ---------- kind classifiers ----------

_RE_LIFE = re.compile(r"\bLIFE\s+(?:offering|exemption|financing|unit)|listed\s+issuer\s+financing", re.I)
_RE_FT = re.compile(r"\b(?:flow[- ]through|FT\s+(?:share|unit)|charity\s+flow[- ]through)", re.I)
_RE_BROKERED = re.compile(r"\b(?<!non-)brokered\s+(?:private\s+)?(?:placement|offering)", re.I)
_RE_NON_BROKERED = re.compile(r"\bnon[- ]brokered\s+(?:private\s+)?(?:placement|offering)", re.I)
_RE_BOUGHT_DEAL = re.compile(r"\bbought\s+deal\b", re.I)
_RE_CD = re.compile(r"\bconvertible\s+debenture(?:s)?\b", re.I)

# ---------- field extractors ----------

# "$1,500,000" or "approximately $6.3 million" or "$2,121,229.06" or "CDN $1,500,000"
_RE_GROSS = re.compile(
    r"(?:aggregate\s+)?gross\s+proceeds\s+(?:of\s+)?(?:approximately\s+)?(?:up\s+to\s+)?"
    r"(?:(?:not|no)\s+less\s+than\s+|(?:of\s+)?at\s+least\s+|a\s+minimum\s+of\s+)?"
    r"(?:CDN?\$?|C\$|US\$|\$)\s*([\d,]+(?:\.\d+)?)\s*(million|M\b|MM\b|billion|B\b)?",
    re.I,
)
# Headline form: "Closes $4,500,000 Private Placement" or "Closes $1.5M Financing"
_RE_HEADLINE_GROSS = re.compile(
    r"\$([\d,]+(?:\.\d+)?)\s*(?:M\b|MM\b|million|MILLION|billion)?",
    re.I,
)

# "5,899,501 Units" / "8,333,334 flow-through shares" / "10,000,000 common shares"
_RE_UNIT_COUNT = re.compile(
    r"([\d,]{4,})\s+(?:Units|FT\s+Shares|FT\s+Units|common\s+shares|flow[- ]through\s+shares|"
    r"flow[- ]through\s+units|charity\s+(?:flow[- ]through\s+)?(?:shares|units))",
    re.I,
)

# "$0.42 per Unit" / "$0.18 per FT Share"
_RE_UNIT_PRICE = re.compile(
    r"(?:price\s+of\s+)?(?:CDN?\$?|C\$|US\$|\$)\s*(\d+(?:\.\d+)?)\s+per\s+"
    r"(?:Unit|FT\s+Share|FT\s+Unit|Share|Common\s+Share|flow[- ]through\s+share)",
    re.I,
)

# "one-half (1/2)" / "one-half of one" / "½"
_RE_HALF_WARRANT = re.compile(
    r"(?:one[- ]half|½|0\.5\s+of\s+one)(?:\s+\(\s*(?:1\s*/\s*2|0\.5)\s*\))?\s+"
    r"(?:of\s+one\s+)?(?:Common\s+Share\s+)?(?:purchase\s+)?[Ww]arrant",
    re.I,
)
# "one Common Share purchase warrant" — must NOT be preceded by "half"
_RE_FULL_WARRANT_HINT = re.compile(
    r"\bone\s+(?:Common\s+Share\s+)?(?:purchase\s+)?[Ww]arrant\b",
    re.I,
)

# "exercise price of $0.50"
_RE_WARRANT_STRIKE = re.compile(
    r"(?:[Ww]arrant|[Ww]arrants).{0,200}?exercise\s+price\s+of\s+(?:CDN?\$?|C\$|\$)?\s*([\d.]+)",
    re.I | re.S,
)
# "for a period of 24 months" or "for a term of 2 years"
_RE_WARRANT_TERM = re.compile(
    r"(?:[Ww]arrant|[Ww]arrants).{0,300}?(?:period|term)\s+of\s+(\d+)\s+(months?|years?)",
    re.I | re.S,
)

# ---------- close→announcement back-reference ----------

_MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)"
_RE_REF_BACK = re.compile(
    r"further\s+to\s+(?:its|the\s+Company.{0,2}s|our|the)\s+(?:previously[- ]announced\s+)?"
    r"news\s+release[s]?\s+dated\s+(" + _MONTH + r"\.?\s+\d{1,2},?\s+\d{4})",
    re.I,
)


def _parse_money(num_str: str, mag: Optional[str]) -> float:
    n = float(num_str.replace(",", ""))
    if not mag:
        return n
    m = mag.upper()
    if m.startswith("M") or m == "MILLION":
        return n * 1_000_000
    if m.startswith("B") or m == "BILLION":
        return n * 1_000_000_000
    return n


def _parse_date(s: str) -> Optional[str]:
    s = s.replace(",", "").replace(".", "").strip()
    for fmt in ("%B %d %Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y", "%Sept %d %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Manual handling of "Sept" → "Sep"
    s2 = re.sub(r"\bSept\b", "Sep", s)
    try:
        return datetime.strptime(s2, "%b %d %Y").strftime("%Y-%m-%d")
    except ValueError:
        pass
    return None


def classify_role(headline: str, body: str) -> tuple[str, Optional[str]]:
    """Return (role, tranche_label).

    role ∈ {announcement, upsize, tranche_close, final_close, amendment,
            terminated, mention}
    """
    h = headline or ""
    if _RE_TERMINATE.search(h):
        return "terminated", None
    if _RE_AMEND.search(h):
        return "amendment", None
    if _RE_UPSIZE.search(h):
        return "upsize", None
    # body-side upsize: "increased the financing from $X to $Y"
    if _RE_UPSIZE_INCREASED_FROM_TO.search(body or ""):
        return "upsize", None
    m = _RE_TRANCHE_LABEL.search(h)
    tranche = m.group(1).lower() if m else None
    if _RE_CLOSE_VERB.search(h) and _RE_FIN_NOUN.search(h):
        if tranche == "final":
            return "final_close", "final"
        if tranche:
            return "tranche_close", tranche
        return "final_close", None
    if _RE_ANNOUNCE_VERB.search(h) and _RE_FIN_NOUN.search(h):
        return "announcement", tranche
    # Body fallback
    b = (body or "")[:2000]
    if _RE_CLOSE_VERB.search(b) and "closed" in b.lower():
        return "final_close", tranche
    return "mention", tranche


def classify_kind(headline: str, body: str) -> str:
    text = (headline or "") + "\n" + (body or "")[:3000]
    is_life = bool(_RE_LIFE.search(text))
    is_ft = bool(_RE_FT.search(text))
    is_bd = bool(_RE_BOUGHT_DEAL.search(text))
    is_brk = bool(_RE_BROKERED.search(text))
    is_nbk = bool(_RE_NON_BROKERED.search(text))
    is_cd = bool(_RE_CD.search(text))
    flags = []
    if is_cd:
        flags.append("CD")
    if is_life:
        flags.append("LIFE")
    if is_ft:
        flags.append("FT")
    if is_bd:
        flags.append("BOUGHT_DEAL")
    if is_brk and not is_nbk:
        flags.append("BROKERED")
    if is_nbk:
        flags.append("NON_BROKERED")
    if not flags:
        flags.append("PP")
    return "+".join(flags)


def extract_fields(headline: str, body: str) -> dict:
    """Pull structured fields from a financing release. Returns a dict
    (missing keys → None)."""
    h = headline or ""
    b = body or ""
    text = h + "\n" + b
    out: dict = {}

    # upsize "from $X to $Y" — prefer the higher (new) amount
    m_up = _RE_UPSIZE_INCREASED_FROM_TO.search(b)
    if m_up:
        out["gross_total"] = _parse_money(m_up.group(1), m_up.group(2))
    # gross — prefer body "gross proceeds of $X" form
    m = _RE_GROSS.search(b)
    if m and "gross_total" not in out:
        out["gross_total"] = _parse_money(m.group(1), m.group(2))
    else:
        # Fallback to headline $X
        m = _RE_HEADLINE_GROSS.search(h)
        if m:
            raw = m.group(0)
            out["gross_total"] = _parse_money(
                m.group(1),
                "M" if re.search(r"M\b|million", raw, re.I) else None,
            )

    # unit count — first body match
    m = _RE_UNIT_COUNT.search(b)
    if m:
        try:
            out["unit_count"] = int(m.group(1).replace(",", ""))
        except ValueError:
            pass

    # unit price
    m = _RE_UNIT_PRICE.search(b)
    if m:
        try:
            out["unit_price"] = float(m.group(1))
        except ValueError:
            pass

    # warrant composition
    if _RE_HALF_WARRANT.search(b):
        out["unit_comp"] = "share + half warrant"
    elif _RE_FULL_WARRANT_HINT.search(b) and "warrant" in b.lower():
        out["unit_comp"] = "share + warrant"
    elif _RE_FT.search(text) and "warrant" not in b.lower()[:3000]:
        out["unit_comp"] = "FT share"

    # warrant strike
    m = _RE_WARRANT_STRIKE.search(b)
    if m:
        try:
            out["warrant_strike"] = float(m.group(1))
        except ValueError:
            pass

    # warrant term — normalize to months
    m = _RE_WARRANT_TERM.search(b)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        out["warrant_term_months"] = n * 12 if "year" in unit else n

    # back-references (announcement-date tags for matching closes back)
    refs = []
    for m in _RE_REF_BACK.finditer(b):
        d = _parse_date(m.group(1))
        if d:
            refs.append(d)
    if refs:
        out["ref_dates"] = refs
    return out


def extract(event: dict) -> dict:
    """Top-level: classify role, kind, fields. Returns a single dict ready
    for the financings/financing_events tables."""
    h = event.get("raw_headline") or ""
    b = event.get("raw_body") or ""
    role, tranche = classify_role(h, b)
    kind = classify_kind(h, b)
    fields = extract_fields(h, b)
    return {
        "role": role,
        "kind": kind,
        "tranche_label": tranche,
        **fields,
    }


def fmt_warrant_term(n_months: Optional[int]) -> Optional[str]:
    if not n_months:
        return None
    if n_months % 12 == 0:
        y = n_months // 12
        return f"{y}yr" if y == 1 else f"{y}yr"
    return f"{n_months}mo"


def fmt_warrant_summary(unit_comp: Optional[str], strike: Optional[float],
                        term_months: Optional[int]) -> Optional[str]:
    """e.g. 'half 2yr warrant at $0.65' or '2yr warrant at $0.65'"""
    if not strike or not unit_comp:
        return None
    half = "half " if "half" in unit_comp else ""
    term = fmt_warrant_term(term_months)
    if not term:
        term = ""
    else:
        term = term + " "
    return f"{half}{term}warrant at ${strike:.2f}".strip()


def fmt_money(n: Optional[float]) -> Optional[str]:
    if n is None:
        return None
    if n >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"${n/1_000:.0f}K"
    return f"${n:.0f}"
