"""Role grammar, money reading and the deal test carried over from portal/financing_extract.py v3
(blob 6551bce9, 2026-09-16) for FIN_V1. Kept byte-for-byte where FIN_V1 relies on the same behaviour;
FIN_V1 (portal/extractors/financings.py) builds on it and changes what the audit found wrong.
Nothing here reads a database or the clock."""
from __future__ import annotations
import re
from datetime import datetime
from typing import Optional

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
_RE_CD_HEAD = re.compile(r"\b(?:debentures?|convertible|notes?)\b", re.I)
_RE_LIFE_HEAD = re.compile(r"\bLIFE\b|listed\s+issuer\s+financing", re.I)

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



# --- the lede is the news; everything below the disclaimer heading is not -----
_RE_FLS_START = re.compile(
    r"(?i)(forward[\-\s]looking\s+(?:statement|information)"
    r"|cautionary\s+(?:note|statement)"
    r"|neither\s+the\s+(?:tsx|canadian\s+securities)"
    r"|this\s+news\s+release\s+(?:contains|includes)\s+forward)")

# Past-tense completion of THIS release's financing.
_RE_CLOSED_NOW = re.compile(
    r"(?i)\b(?:has|have)\s+(?:now\s+)?(?:successfully\s+)?closed\b"
    r"|\bannounces?\s+(?:the\s+)?(?:successful\s+)?clos(?:ing|ure)\s+of\b"
    r"|\b(?:has|have)\s+completed\s+(?:the|its)\b"
    r"|\bis\s+pleased\s+to\s+announce\s+(?:the\s+)?(?:successful\s+)?clos(?:ing|ure)\b"
    r"|\bcompletion\s+of\s+(?:the|its)\s+(?:previously\s+announced\s+)?"
    r"(?:non[\-\s]brokered\s+)?(?:private\s+placement|offering|financing)\b")

# If these sit beside the match it is a close that has not happened yet.
_RE_CLOSE_FUTURE = re.compile(
    r"(?i)\b(?:prior\s+to|before|upon|anticipated|expects?\s+to|intends?\s+to"
    r"|will\s+close|subject\s+to)\b")

# _RE_FIN_NOUN does not know every instrument ("Convertible Promissory Notes"),
# but a close verb next to an amount in the HEADLINE is not ambiguous.
_RE_HEADLINE_MONEY = re.compile(
    r"\$\s?[\d,]+(?:\.\d+)?\s*(?:million|billion|m\b|bn\b)?", re.I)


def _lede(body: str, n: int = 900) -> str:
    """The body above the forward-looking-statements heading, capped."""
    b = body or ""
    m = _RE_FLS_START.search(b)
    if m:
        b = b[:m.start()]
    return b[:n]


# A company closes acquisitions, earn-ins and property options as readily as it
# closes placements. _RE_FIN_NOUN is the discriminator the headline path already
# uses; these are the instruments it does not list.
_RE_INSTRUMENT = re.compile(
    r"(?i)\b(?:private\s+placement|offering|financing|placement|subscription\s+receipt"
    r"|convertible\s+(?:debenture|note|promissory\s+note)|debenture|promissory\s+note"
    r"|flow[\-\s]through|LIFE\s+offering|unit\s+offering|bought\s+deal"
    r"|credit\s+facility|loan\s+facility|equity\s+raise|capital\s+raise"
    # plurals: "PRIVATE PLACEMENTS", "Convertible Promissory Notes"
    r")e?s?\b")

# ... and the things a close verb attaches to that are NOT a financing.
_RE_NOT_A_FINANCING = re.compile(
    r"(?i)\b(?:acquisition|earn[\-\s]?in|option\s+agreement|amalgamation|arrangement"
    r"|merger|name\s+change|consolidation|sale\s+of|disposition|joint\s+venture)\b")


def _close_is_financing(window: str) -> bool:
    """True only if the close language is about a financing instrument."""
    if _RE_NOT_A_FINANCING.search(window):
        return False
    return bool(_RE_INSTRUMENT.search(window) or _RE_FIN_NOUN.search(window))


def _body_reports_a_close(body: str) -> bool:
    L = _lede(body)
    for m in _RE_CLOSED_NOW.finditer(L):
        window = L[max(0, m.start() - 110):m.end() + 130]
        if _RE_CLOSE_FUTURE.search(L[max(0, m.start() - 90):m.end() + 90]):
            continue
        if _close_is_financing(window):
            return True
    return False


# =============================================================================
# 2026-09-15 audit additions (see FINDINGS.md). Every change sits behind a FLAG
# so measure.py can run the original and each change on its own against the
# corpus. The defaults are the recommended behaviour.
# =============================================================================
FLAGS = dict(
    plural_nouns=True,             # E1 "Private Placements", "Offerings"
    close_before_body_upsize=True, # E2 a headline close beats a body "increased from $X to $Y"
    headline_close_guard=True,     # E3 "to Close", "Intention to Complete", "Completes Acquisition ... and Announces PP"
    announce_verbs=True,           # E4 arranges/proposes/secures/"Increases Private Placement"/"$3M Financing"
    money_parse=True,              # E5 "$1, 500,000", "$3-million", "US$", plausibility, upsize overwrite
    lede_amount=True,              # E6 amount from the body lede when there is no "gross proceeds" figure
    new_instruments=True,          # E7 DEBT / IPO / ATM / STREAM kinds and their headline roles
    outstanding_guard=True,        # E8 "58,748,220 common shares issued and outstanding" is not the offering
    closes_upsized=True,           # E10 "Closes Upsized $1.7M Private Placement" is a close, not an upsize
    tranche_labels=True,           # E9 "2nd Tranche", "Tranche 1", "Closes $1M Tranche of" are tranches, not final closes
    cd_headline_priority=True,     # E11 a headline naming flow-through / LIFE shares is not a debenture deal because the body mentions one
)

_ORD = {"1st": "first", "2nd": "second", "3rd": "third", "4th": "fourth", "5th": "fifth",
        "1": "first", "2": "second", "3": "third", "4": "fourth", "one": "first", "two": "second",
        "three": "third", "four": "fourth", "i": "first", "ii": "second", "iii": "third", "iv": "fourth"}
_RE_TRANCHE_NUM = re.compile(
    r"(?i)\b(?:(1st|2nd|3rd|4th|5th|[1-5]\s(?:st|nd|rd|th))\s+(?:and\s+final\s+)?(?:financing\s+)?tranche"
    r"|tranche\s+(?:#\s*|no\.?\s*)?(1|2|3|4|one|two|three|four|i{1,3}|iv)\b)")
_RE_TRANCHE_BARE = re.compile(r"(?i)\btranches?\b")

_RE_FIN_NOUN_PL = re.compile(
    r"\b(?:private\s+placement|placement|offering|financing|tranche|life\s+offering|"
    r"flow[- ]through|charity\s+flow[- ]through|bought\s+deal|public\s+offering|"
    r"prospectus\s+offering)s?\b",
    re.I,
)

# Instruments the v7 categoriser adds to Financings. Headline only.
_RE_NEW_INSTR = re.compile(
    r"(?i)\b(?:(?:senior\s+)?(?:secured\s+|unsecured\s+)?notes?\s+offerings?"
    r"|senior\s+(?:secured\s+|unsecured\s+)?notes"
    r"|convertible\s+(?:senior\s+)?notes"
    r"|credit\s+facilit(?:y|ies)|loan\s+facilit(?:y|ies)|debt\s+facilit(?:y|ies)|standby\s+facilit(?:y|ies)"
    r"|(?:term|bridge|gold|project|related[\s-]party|secured|convertible|shareholder)\s+loans?"
    r"|loan\s+agreements?|new\s+loan|(?:US|C|CA)?\$[\d.,]+\s*(?:million|m)?\s+loan"
    r"|debt\s+financing|project\s+financing|financing\s+package"
    r"|initial\s+public\s+offering|IPO"
    r"|at[\s-]the[\s-]market\s+(?:equity\s+)?(?:program(?:me)?|offering)s?|ATM\s+(?:equity\s+)?program(?:me)?"
    r"|equity\s+distribution\s+agreement|controlled\s+equity\s+offering"
    r"|(?:gold|silver|copper|precious\s+metals?)\s+stream(?:ing)?(?:\s+agreement)?|stream(?:ing)?\s+(?:agreement|financing)"
    r"|(?:gold\s+)?pre[\s-]?pay(?:ment)?\s+(?:facility|agreement|arrangement|financing)s?"
    r"|strategic\s+(?:equity\s+)?investments?|equity\s+investments?"
    r"|subscription\s+receipts?|convertible\s+debentures?)\b")

# A release that repays, converts or reports on an existing instrument is not a
# new financing, even though it names one.
_RE_NOT_NEW = re.compile(
    r"(?i)\b(?:repa(?:y|ys|id|yment)|interest\s+payments?|conversion|converts?|redemption|redeems?"
    r"|draw(?:s|down)?|sales\s+update|quarterly|maturity|extension|extends?|default|waiver"
    r"|investments?\s+(?:in|into|with)|acquisition\s+of|tender\s+offer|amend\w*|settlement|interest"
    r"|existing|replacement|exchange\s+of|expiry|updates?)\b")

_RE_K_DEBT = re.compile(
    r"(?i)\b(?:senior\s+(?:secured\s+|unsecured\s+)?notes|notes?\s+offering|credit\s+facilit|loan"
    r"|debt\s+financing|debt\s+facilit|term\s+facilit|revolving|bonds?\b|project\s+financing)")
_RE_K_IPO = re.compile(r"(?i)\b(?:initial\s+public\s+offering|IPO)\b")
_RE_K_ATM = re.compile(
    r"(?i)\b(?:at[\s-]the[\s-]market|ATM\s+(?:equity\s+)?program|equity\s+distribution\s+agreement"
    r"|controlled\s+equity\s+offering)")
_RE_K_STREAM = re.compile(
    r"(?i)\b(?:stream(?:ing)?\s+(?:agreement|financing|transaction)|(?:gold|silver|copper|precious\s+metals?)\s+stream"
    r"|pre[\s-]?pay(?:ment)?\s+(?:facility|agreement|arrangement|financing))")

# --- E4: announcement wording the original verb list missed -------------------
_RE_ANNOUNCE_VERB2 = re.compile(
    r"(?i)\b(?:arrang(?:es|ed|ing)|propos(?:es|ed|ing)|undertak(?:es|ing)|initiat(?:es|ing)|secur(?:es|ing)"
    r"|anounces|annouces|announcement\s+of|announcing|enters\s+into|establish(?:es|ing)"
    r"|sets\s+(?:terms|price)|pric(?:es|ing)\b|files\s+(?:(?:an?\s+)?(?:amended\s+|preliminary\s+|final\s+)?(?:short\s+form\s+)?prospectus)"
    r"|plans|intends?\s+to|intention\s+to|obtains?|signs?)\b")
# ... but not a release that only reports on, corrects or congratulates.
_RE_NOT_ANNOUNCE = re.compile(
    r"(?i)\b(?:updat(?:e|es|ed)|additional\s+information|clarif\w*|congratulat\w*|objection|correct\w*"
    r"|achievements|recap)\b")
_ADJ = (r"(?:(?:non[\-\s]?brokered|brokered|flow[\-\s]through|hard[\-\s]dollar|LIFE|unit|units|equity|charity"
        r"|critical\s+minerals?|over[\-\s]?subscribed|strategic|concurrent|its|the|previously\s+announced"
        r"|proposed|size\s+of(?:\s+the|\s+its)?)\s+){0,4}")
_RE_UPSIZE2 = re.compile(
    r"(?i)\b(?:increas(?:es|ed|ing)|expands?|doubles?)\s+" + _ADJ +
    r"(?:private\s+placement|placement|offering|financing|flow[\-\s]through\s+(?:financing|offering|placement))s?\b")
# "$3M Financing", "New $10M Private Placement": an amount that names the deal
_RE_MONEY_NOUN = re.compile(
    r"(?i)\$\s?[\d,.]+\s*(?:-?\s*(?:million|m\b|mm\b))?\s+" + _ADJ +
    r"(?:private\s+placement|placement|offering|financing)s?\b")

# --- E3: a close verb in the headline that is not this release's financing ----
# NB: patterns used with .match(text, pos) must not start with "^" -- "^" does
# not match at pos > 0, which silently disabled three guards in the first cut.
_RE_HCLOSE = re.compile(r"(?i)\b(?:close[sd]?|closing|completes?|completed|completion|finali[sz]es)\b")
_RE_HFUT_BEFORE = re.compile(
    r"(?i)\b(?:to|will|intends?\s+to|intention\s+to|intent\s+to|expects?\s+to|plans?\s+to|approved\s+to"
    r"|acceptance\s+to|anticipated\s+to|upon|prior\s+to|before|in\s+preparation\s+for)\s+(?:the\s+|its\s+)?$")
# "Extends Closing of", "Extension of Private Placement Closing", "Closing Date Extended"
_RE_HEXT_BEFORE = re.compile(
    r"(?i)\b(?:extension\s+of(?:\s+(?!and\b)[\w\-]+){0,4}|extends?(?:\s+(?!and\b)[\w\-]+){0,4})\s+$")
_RE_HEXT_AFTER = re.compile(r"(?i)^\s*(?:dates?\s+(?:extended|extension)|extended|extension|deadline)")
_RE_HFUT_AFTER = re.compile(
    r"(?i)^\s*(?:dates?\b|scheduled|details|to\s+coincide)")
_RE_HNOT = re.compile(
    r"(?i)\b(?:acquisition|acquire|earn[\-\s]?in|option\s+(?:agreement|payment)s?|options?\b|amalgamation"
    r"|arrangement|merger|name\s+change|consolidation|sale|disposition|joint\s+venture|propert(?:y|ies)"
    r"|claims?|drill(?:ing)?|program(?:me)?|survey|AGM|annual\s+general|meeting|purchase|transaction"
    r"|business\s+combination|spin[- ]?out|field\s*work|sampling|study|technical\s+report|amendments?"
    r"|payments?|construction|mapping|campaign|asset|milestone|exploration|debt\s+settlement"
    r"|shares\s+for\s+debt|warrant\s+exercise|due\s+diligence|share\s+exchange|change\s+of\s+business)\b")
_RE_HVERB = re.compile(
    r"(?i)\b(?:announces?|provides?|files?|increases?|issues?|arranges?|launch(?:es)?|proposes?|receives?"
    r"|commences?|adds?|appoints?|grants?|extends?|updates?|plans?|intends?|enters?|signs?|reports?|expands?"
    r"|secures?|initiates?|mobilizes?|begins?|starts?|exits?|welcomes?|update|following|preparation)\b")


def _fin_noun(h: str):
    rx = _RE_FIN_NOUN_PL if FLAGS["plural_nouns"] else _RE_FIN_NOUN
    m = rx.search(h)
    if m:
        return m
    if FLAGS["new_instruments"]:
        m = _RE_NEW_INSTR.search(h)
        if m and not _RE_NOT_NEW.search(h):
            return m
    return None


def headline_close_verdict(h: str) -> str:
    """'real' | 'extension' | 'schedule' | 'future' | 'other' for the close verbs in a headline that
    also names a financing. 'real' if ANY close verb is about the financing."""
    kinds = []
    FN = _RE_FIN_NOUN_PL
    for m in _RE_HCLOSE.finditer(h):
        pre = h[max(0, m.start() - 60):m.start()]
        post = h[m.end():]
        if _RE_HEXT_BEFORE.search(pre) or _RE_HEXT_AFTER.search(post):
            kinds.append("extension")
            continue
        if _RE_HFUT_AFTER.search(post) or re.search(r"(?i)\bupdate\s+(?:to|on)\s+(?:the\s+|its\s+)?$", pre):
            kinds.append("schedule")      # "Closing Date for", "Closing Scheduled", "Update to Closing"
            continue
        if _RE_HFUT_BEFORE.search(pre):
            kinds.append("future")
            continue
        # "Private Placement Closes", "PP Tranche Closing" -- the noun is right there
        if re.search(r"(?i)(?:placement|offering|financing|tranche|flow[\s-]through|units?|shares?|pp)s?"
                     r"(?:\s+(?:initial|final|first|second|third|oversubscribed))?\s+$", pre):
            kinds.append("real")
            continue
        obj = re.sub(r"(?i)^\s*of\s+", "", post)[:110]
        n = FN.search(obj) or _RE_NEW_INSTR.search(obj)
        x = _RE_HNOT.search(obj)
        if x and (not n or x.start() < n.start()):
            between = obj[x.end():n.start()] if n else obj[x.end():]
            if not n or _RE_HVERB.search(between):
                kinds.append("other")
                continue
        kinds.append("real")
    if "real" in kinds or not kinds:
        return "real"
    for k in ("extension", "schedule", "future"):
        if k in kinds:
            return k
    return "other"


# --- E5: money --------------------------------------------------------------
_CUR = (r"(?P<cur>(?<![A-Za-z])(?:US|U\.S\.|USD|AUD|AU|A|CAD|CDN|CA|C|NZ|HK)\s?\$|(?<![A-Za-z])(?:USD|CAD|CDN|AUD)\s(?=\d)"
        r"|\$|£|€)")
_RE_NUM_RUN = re.compile(r"\d[\d,. ]{0,18}")
_RE_NUM_OK = re.compile(r"^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
_RE_MAG = re.compile(r"(?i)\s*-?\s*(million|mm\b|mln\b|m\b|billion|bn\b|b\b|thousand|k\b)")
_RE_PER_AFTER = re.compile(r"(?i)\s*(?:per\b|/|each\b|an?\s+(?:ounce|share|unit)|oz\b)")


def _cur_code(cur: Optional[str]) -> Optional[str]:
    if not cur:
        return None
    c = cur.upper().replace(".", "").replace(" ", "")
    if c.startswith("US"):
        return "USD"
    if c.startswith("A"):
        return "AUD"
    if c.startswith("C"):
        return "CAD"
    if c.startswith("NZ"):
        return "NZD"
    if c.startswith("HK"):
        return "HKD"
    if c == "£":
        return "GBP"
    if c == "€":
        return "EUR"
    return None      # bare "$": the site's default (Canadian) dollars


def read_amount(text: str, pos: int):
    """Read a money figure whose first digit is at text[pos].
    Returns (value, end) or (None, pos). Repairs PDF-extraction spacing
    ("$1, 500,000", "$4 15,000", "$1,250 ,000") and "-million"."""
    m = _RE_NUM_RUN.match(text, pos)
    if not m:
        return None, pos
    run = m.group(0).rstrip(" ,.")
    first = re.match(r"[\d,.]+", run).group(0).rstrip(",.")
    val = None
    end = pos
    for s in (run.replace(" ", ""), first):
        if _RE_NUM_OK.match(s):
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
        # "$2,000,000 million" is a typo, not two trillion dollars
        if not (val >= 100_000 and mult >= 1_000_000):
            val *= mult
        end = mg.end()
    return val, end


def plausible_gross(v: Optional[float]) -> bool:
    """A raise is at least $1,000 and at most $50B. A figure outside that is a
    unit price, a gold price or a parsing error, not the size of a financing."""
    return v is not None and 1_000 <= v <= 5e10


_RE_GROSS2 = re.compile(
    r"(?:aggregate\s+)?gross\s+proceeds\s+(?:of\s+)?(?:approximately\s+)?(?:up\s+to\s+)?"
    r"(?:(?:not|no)\s+less\s+than\s+|(?:of\s+)?at\s+least\s+|a\s+minimum\s+of\s+)?"
    + _CUR + r"\s?(?=\d)",
    re.I,
)
_RE_CUR_DIGIT = re.compile(_CUR + r"\s?(?=\d)")

# --- E6: amount in the body lede -------------------------------------------
_LEDE_NOUN = r"(?:private\s+placement|placement|offering|financing)s?"
_LEDE_Q = r"(?:up\s+to\s+|approximately\s+|an\s+aggregate\s+of\s+|a\s+(?:minimum|maximum)\s+of\s+|total\s+|aggregate\s+)*"
_RE_LEDE_AMTS = [
    re.compile(r"(?i)\b" + _LEDE_NOUN + r"\b[^$;\n]{0,80}?\b(?:of|for|totall?ing|raising)\s+"
               r"(?:(?:total|aggregate|gross)\s+)?(?:proceeds\s+of\s+)?" + _LEDE_Q + _CUR + r"\s?(?=\d)"),
    re.compile(r"(?i)\b(?:to\s+)?rais(?:e|es|ed|ing)\s+(?:(?:total|aggregate|gross)\s+)?(?:proceeds\s+of\s+)?"
               + _LEDE_Q + _CUR + r"\s?(?=\d)"),
    re.compile(r"(?i)\b(?:total|aggregate)\s+(?:gross\s+)?proceeds\s+(?:of\s+)?" + _LEDE_Q + _CUR + r"\s?(?=\d)"),
]
_RE_LEDE_MONEY_NOUN_TAIL = re.compile(
    r"(?i)\s+(?:(?:non[\-\s]?brokered|brokered|flow[\-\s]through|hard[\-\s]dollar|LIFE|unit|equity|charity"
    r"|best[\-\s]efforts|over[\-\s]?subscribed|strategic)\s+){0,3}" + _LEDE_NOUN + r"\b")
_RE_LEDE_OTHER = re.compile(
    r"(?i)(?:previously\s+(?:closed|completed)|following\s+(?:the\s+|its\s+)?(?:successful\s+)?(?:closing|completion)"
    r"|last\s+year|recently\s+(?:closed|completed)|in\s+addition\s+to|bringing\s+(?:the\s+)?total|to\s+date"
    r"|cash\s+(?:position|balance)|treasury|working\s+capital\s+of|since\s+(?:inception|20\d\d))[^.]{0,80}$")


def lede_amount(body: str, closing: bool = False):
    """(value, currency_code, trigger) from the body lede, or None.
    For a close, an "up to $X" figure is the offering's size, not what closed."""
    L = _lede(body)
    hits = []
    for i, rx in enumerate(_RE_LEDE_AMTS):
        for m in rx.finditer(L):
            hits.append((m.end(), m.start(), m.group("cur"), "lede_p%d" % (i + 1)))
    for m in _RE_CUR_DIGIT.finditer(L):
        v, end = read_amount(L, m.end())
        if v is not None and _RE_LEDE_MONEY_NOUN_TAIL.match(L, end):
            hits.append((m.end(), m.start(), m.group("cur"), "lede_money_noun"))
    for pos, start, cur, trig in sorted(hits):
        v, end = read_amount(L, pos)
        if not plausible_gross(v):
            continue
        if _RE_PER_AFTER.match(L, end):
            continue
        if _RE_LEDE_OTHER.search(L[max(0, start - 120):start]):
            continue
        if closing and re.search(r"(?i)\b(?:up\s+to|maximum|minimum)\b", L[start:pos]):
            continue
        # "Insiders participated in the Offering for $40,000" is a part, not the deal
        if re.search(r"(?i)\b(?:insiders?|directors?|officers?|participat\w*|finder|commission|fees?)\b",
                     L[max(0, start - 80):pos]):
            continue
        return v, _cur_code(cur), trig
    return None


# --- E8 ---------------------------------------------------------------------
_RE_OUTSTANDING_AFTER = re.compile(
    r"(?i)\s*(?:of\s+the\s+company\s+)?(?:are\s+|were\s+)?(?:currently\s+|now\s+)?(?:issued\s+and\s+)?outstanding")

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
        # "C2C Gold Closes Upsized $1.7 Million Private Placement": the adjective
        # describes the deal that closed.
        if not (FLAGS["closes_upsized"] and re.search(r"(?i)\bupsized\b", h)
                and not re.search(r"(?i)\bupsiz(?:e|es|ing)\b|increases?\s+size", h)
                and _RE_CLOSE_VERB.search(h) and _fin_noun(h)
                and headline_close_verdict(h) == "real"):
            return "upsize", None
    body_upsize = bool(_RE_UPSIZE_INCREASED_FROM_TO.search(body or ""))
    # body-side upsize: "increased the financing from $X to $Y"
    if body_upsize and not FLAGS["close_before_body_upsize"]:
        return "upsize", None
    m = _RE_TRANCHE_LABEL.search(h)
    tranche = m.group(1).lower() if m else None
    bare_tranche = False
    if tranche is None and FLAGS["tranche_labels"]:
        mn = _RE_TRANCHE_NUM.search(h)
        if mn:
            raw = (mn.group(1) or mn.group(2)).lower().replace(" ", "")
            tranche = _ORD.get(raw, _ORD.get(raw[:1], None))
            if re.search(r"(?i)\band\s+final\b", mn.group(0)):
                tranche = "final"
        elif _RE_TRANCHE_BARE.search(h) and not re.search(r"(?i)\bfinal\b", h):
            bare_tranche = True
    rx_old = _RE_FIN_NOUN_PL if FLAGS["plural_nouns"] else _RE_FIN_NOUN
    noun_old = rx_old.search(h)
    noun_any = _fin_noun(h)            # + DEBT/IPO/ATM/STREAM/strategic investment (E7)
    verdict = "real"
    head_close = bool(_RE_CLOSE_VERB.search(h) and noun_any)
    if head_close and FLAGS["headline_close_guard"]:
        verdict = headline_close_verdict(h)
        head_close = verdict == "real"
    if head_close:
        if tranche == "final":
            return "final_close", "final"
        if tranche or bare_tranche:
            return "tranche_close", tranche
        return "final_close", None
    if FLAGS["headline_close_guard"] and verdict == "extension":
        return "amendment", tranche          # "Extends Closing of Private Placement"
    if FLAGS["headline_close_guard"] and verdict == "schedule":
        return "mention", tranche            # "Announces Closing Date for ..." -- attaches, no status
    if body_upsize:
        return "upsize", None
    if _RE_ANNOUNCE_VERB.search(h) and noun_old:
        return "announcement", tranche
    # A close verb plus an amount in the headline, for instruments
    # _RE_FIN_NOUN does not list: "KO Gold Closes $200,000 in Convertible
    # Promissory Notes".
    if (_RE_CLOSE_VERB.search(h) and _RE_HEADLINE_MONEY.search(h)
            and _close_is_financing(h)
            and not (FLAGS["headline_close_guard"] and headline_close_verdict(h) != "real")):
        if tranche and tranche != "final":
            return "tranche_close", tranche
        return "final_close", tranche

    # Body fallback -- the lede only, above the disclaimer, past tense.
    # Reading 2,000 characters here put 97 AGM results, booth announcements and
    # warrant extensions into the closed-financings table.
    if _body_reports_a_close(body):
        return "final_close", tranche
    # --- weaker headline cues, only once the body has not reported a close ---
    if FLAGS["announce_verbs"] and _RE_UPSIZE2.search(h):
        return "upsize", None
    if (_RE_ANNOUNCE_VERB.search(h) and noun_any) or (
            FLAGS["announce_verbs"] and noun_any and not _RE_NOT_ANNOUNCE.search(h)
            and (_RE_ANNOUNCE_VERB2.search(h) or _RE_MONEY_NOUN.search(h))):
        return "announcement", tranche
    if FLAGS["headline_close_guard"] and verdict == "future" and noun_any:
        # "Intention to Complete $2M PP" announces; "to Close First Tranche" follows one
        return ("mention", tranche) if tranche else ("announcement", None)
    return "mention", tranche



_RE_DEAL_EXTRA = re.compile(
    r"(?i)\b(?:investment\s+(?:by|from|led\s+by|in\s+the\s+company)"
    r"|(?:US|C|CA|CAD)?\$\s?[\d.,]+\s*(?:million|m\b)?\s+(?:strategic\s+|equity\s+)?investment"
    r"|rais(?:e|es|ed|ing)\s+(?:\w+\s+){0,2}(?:US|C|CA|CAD|CDN)?\$|secures\s+(?:\w+\s+){0,2}(?:US|C|CA|CAD|CDN)?\$"
    r"|convertible\s+(?:note|debenture|loan)s?|lead\s+order|subscription\s+receipts?)")
_RE_NOT_DEAL_HEAD = re.compile(
    r"(?i)\b(?:warrants?|exercis\w*|interest\s+payment|conver(?:sion|ts?)|repay\w*|shares?\s+for\s+debt"
    r"|debt\s+settlement|draw(?:down)?s?)\b")
_RE_OTHER_TOPIC = re.compile(
    r"(?i)\b(?:options?|prospectus|results|interest|settlement|drill\w*|exploration|production|AGM|meeting"
    r"|appoint\w*|extension|listing|trading|lists|commences|updates?|financial|sale|sells|acquisition|acquires?"
    r"|royalty|joint\s+venture|permits?|survey|program(?:me)?|voting|early\s+warning|renames|funding\s+agreement"
    r"|government|discover\w*|intercepts?|resource|plans?\s+to\s+advance)\b")


def is_about_financing(headline: str, body: str) -> bool:
    """Does this release describe a financing of its own, as opposed to a
    warrant exercise, interest payment, prospectus filing or drill update that
    merely carries the tag? Decided on the headline; the body lede is read only
    when the headline is uninformative (wire boilerplate, a bare company name)."""
    h = headline or ""
    if _fin_noun(h) or _RE_MONEY_NOUN.search(h):
        return True
    if _RE_NOT_DEAL_HEAD.search(h):
        return False
    if _RE_DEAL_EXTRA.search(h):
        return True
    if _RE_OTHER_TOPIC.search(h):
        return False
    # Uninformative headline ("News release", "WEST HIGH YIELD (W.H.Y.) RESOURCES LTD.",
    # wire boilerplate): the real headline is usually the first line of the body.
    L = _lede(body)
    return bool(_RE_FIN_NOUN_PL.search(L))


