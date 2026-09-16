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


def classify_kind(headline: str, body: str) -> str:
    text = (headline or "") + "\n" + (body or "")[:3000]
    h = headline or ""
    is_life = bool(_RE_LIFE.search(text))
    is_ft = bool(_RE_FT.search(text))
    is_bd = bool(_RE_BOUGHT_DEAL.search(text))
    is_brk = bool(_RE_BROKERED.search(text))
    is_nbk = bool(_RE_NON_BROKERED.search(text))
    is_cd = bool(_RE_CD.search(text))
    flags = []
    if FLAGS["new_instruments"]:
        # headline only: "proceeds will repay the credit facility" in a
        # placement's body does not make the placement a loan.
        if _RE_K_DEBT.search(h) and not _RE_CD.search(h):
            flags.append("DEBT")
        if _RE_K_IPO.search(h):
            flags.append("IPO")
        if _RE_K_ATM.search(h):
            flags.append("ATM")
        if _RE_K_STREAM.search(h):
            flags.append("STREAM")
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


def _orig_gross(h: str, b: str, out: dict) -> None:
    """The shipped gross logic, kept verbatim for money_parse=False."""
    m_up = _RE_UPSIZE_INCREASED_FROM_TO.search(b)
    if m_up:
        out["gross_total"] = _parse_money(m_up.group(1), m_up.group(2))
    m = _RE_GROSS.search(b)
    if m and "gross_total" not in out:
        out["gross_total"] = _parse_money(m.group(1), m.group(2))
    else:
        m = _RE_HEADLINE_GROSS.search(h)
        if m:
            raw = m.group(0)
            out["gross_total"] = _parse_money(
                m.group(1),
                "M" if re.search(r"M\b|million", raw, re.I) else None,
            )


def _headline_amounts(h: str):
    for m in _RE_CUR_DIGIT.finditer(h):
        v, end = read_amount(h, m.end())
        if plausible_gross(v) and not _RE_PER_AFTER.match(h, end):
            to = bool(re.search(r"(?i)\bto\s+(?:up\s+to\s+|an?\s+aggregate\s+of\s+)?$", h[max(0, m.start() - 25):m.start()]))
            yield v, _cur_code(m.group("cur")), to


def _new_gross(h: str, b: str, out: dict, role: Optional[str] = None) -> None:
    """Gross amount with repaired number parsing, a plausibility floor and the
    currency next to it. Precedence is the shipped one made explicit:
    an upsize takes the headline's (last) amount, else the body's "from $X to $Y";
    everything else takes the body's first "gross proceeds of", else the headline."""
    def put(v, cur, src):
        out["gross_total"], out["currency"], out["gross_source"] = v, cur, src

    if role == "upsize":
        hs = list(_headline_amounts(h))
        if hs:
            pick = next((x for x in hs if x[2]), hs[0])     # "to $4 Million", else the first
            put(pick[0], pick[1], "headline")
            return
        m_up = _RE_UPSIZE_INCREASED_FROM_TO.search(b)
        if m_up:
            v, _ = read_amount(b, m_up.start(1))
            if plausible_gross(v):
                cm = list(_RE_CUR_DIGIT.finditer(b, m_up.start(), m_up.start(1)))
                put(v, _cur_code(cm[-1].group("cur")) if cm else None, "body_upsize")
                return
    for m in _RE_GROSS2.finditer(b):
        v, end = read_amount(b, m.end())
        if plausible_gross(v):
            put(v, _cur_code(m.group("cur")), "body_gross")
            return
    for v, cur, _to in _headline_amounts(h):
        put(v, cur, "headline")
        return


def extract_fields(headline: str, body: str, role: Optional[str] = None) -> dict:
    """Pull structured fields from a financing release. Returns a dict
    (missing keys → None)."""
    h = headline or ""
    b = body or ""
    text = h + "\n" + b
    out: dict = {}

    if FLAGS["money_parse"]:
        _new_gross(h, b, out, role)
    else:
        _orig_gross(h, b, out)

    # unit count — first body match (not the shares outstanding)
    for m in _RE_UNIT_COUNT.finditer(b):
        if FLAGS["outstanding_guard"] and _RE_OUTSTANDING_AFTER.match(b, m.end()):
            continue
        try:
            out["unit_count"] = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
        break

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


def extract(event: dict) -> dict:
    """Top-level: classify role, kind, fields. Returns a single dict ready
    for the financings/financing_events tables."""
    h = event.get("raw_headline") or ""
    b = event.get("raw_body") or ""
    role, tranche = classify_role(h, b)
    kind = classify_kind(h, b)
    fields = extract_fields(h, b, role)
    if FLAGS["lede_amount"] and role != "mention" and not fields.get("gross_total"):
        got = lede_amount(b, closing=role in ("final_close", "tranche_close"))
        if got:
            fields["gross_total"], fields["currency"], fields["gross_source"] = got
    return {
        "role": role,
        "kind": kind,
        "tranche_label": tranche,
        "is_deal": 1 if is_about_financing(h, b) else 0,
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


# =============================================================================
# Self-test. Every headline is a real one from the corpus (2026-09-15 audit).
# Run: python3 financing_extract.py
# =============================================================================
_ROLE_CASES = [
    # E1 plurals
    ("GoldHaven Announces Private Placements", "announcement"),
    ("Muzhu Completes Private Placements", "final_close"),
    # E3 future / extension / schedule / non-financing object
    ("First Phosphate Announces Intention to Complete $2,000,000 Non-Brokered Private Placement", "announcement"),
    ("SIXTY NORTH GOLD TO CLOSE NON-BROKERED $1,500,000 UNIT OFFERING", "announcement"),
    ("Goldrea to close $433,746 first tranche of financing", "mention"),
    ("POWR Lithium Extends Closing of Private Placement", "amendment"),
    ("Mayo Lake Share Consolidation and Life Offering Closing Dates Extended", "amendment"),
    ("Appia Announces Closing Scheduled for Final Tranche of Non-Brokered Private Placement", "mention"),
    ("Mosaic Exits Lithium Exploration, Completes Acquisition of Amanda Property and Announces Private Placement", "announcement"),
    ("Renegade Gold Closes BobJo Acquisition and Issues First Tranche of Shares towards Keystone Acquisition", "mention"),
    # ... and the closes it must leave alone
    ("LEVEL 14 ANNOUNCES COMPLETION OF COLPAYOC ACQUISITION AND FINANCING", "final_close"),
    ("GOLD’N FUTURES ANNOUNCES PRIVATE PLACEMENT CLOSES AND OPTIONS AND RESTRICTED SHARE UNITS GRANTED", "final_close"),
    ("Lux Metals Closes Acquisition of High-Grade Gold La Grande Project in Quebec and Final Tranche of $4 Million Private Placement", "final_close"),
    ("Bold Ventures Announces Increase and Extension of Non-Brokered Private Placement and Closing of Third Tranche, and Signs Agreement with Investor News Network", "tranche_close"),
    ("Medaro Mining Announces Closing of Second and Final Tranche of Private Placement", "final_close"),
    ("Alma Gold Inc. Closes $750,000 Private Placement", "final_close"),
    ("KO Gold Closes $200,000 in Convertible Promissory Notes", "final_close"),
    # E4 announcement / upsize wording
    ("Gander Gold Arranges $3.2 Million Private Placement", "announcement"),
    ("US Copper Corp Proposes $750,000 Non-Brokered Private Placement", "announcement"),
    ("ETRUSCUS INCREASES PRIVATE PLACEMENT TO $2.7 MILLION", "upsize"),
    ("Nuinsco Expands Private Placement", "upsize"),
    ("Ares Accelerates Flotation Plant Construction Following U.S. Defense Contract Award and New $10M Private Placement", "announcement"),
    ("Stuve Gold Corp. Provides Update on Proposed Private Placement", "mention"),
    ("Vizsla Royalties Congratulates Vizsla Silver Corp on US$100M Financing", "mention"),
    # E7 new instruments
    ("Seabridge Gold Arranges US$100M Credit Facility to Support Ongoing Activities at KSM", "announcement"),
    ("Founders Metals Closes $50,000,000 Strategic Investment by Gold Fields", "final_close"),
    ("IsoEnergy Announces Launch of At-The-Market Equity Program", "announcement"),
    ("Reflex Announces Strategic Investment in Cleantech Graphene Producer", "mention"),
    ("Austral Gold Announces Repayment of Related Party Loan", "mention"),
    # E9 tranche labels
    ("Norsemont Announces Closing of 3rd Tranche of Private Placement Led by Crescat Capital and Equity Management Associates", "tranche_close"),
    ("Black Tusk Resources Inc. Closes Tranche 1 of Private Placement", "tranche_close"),
    ("Critical One Energy Closes CDN$5.6 Million Tranche of Flow-Through Private Placement", "tranche_close"),
    ("Silver Elephant Closes 2 nd and Final Tranche of Non- Brokered Private Placement", "final_close"),
    # E10
    ("C2C Gold Closes Upsized $1.7 Million Private Placement", "final_close"),
    ("Quimbaya Gold Announces Upsize of Bought Deal Financing to $12.5 Million", "upsize"),
    # unchanged non-financings
    ("Aben Gold Announces 2026 Exploration Program", "mention"),
    ("Mcfarlane Lake Announces Warrant Extension", "mention"),
]

_AMOUNT_CASES = [
    # (text with the first digit after the currency, expected value)
    ("gross proceeds of up to $1, 500,000 (the", 1_500_000),
    ("gross proceeds of up to $3-million, consisting", 3_000_000),
    ("gross proceeds of a minimum of $2,000,000 million (the", 2_000_000),
    ("total gross proceeds of approximately US$900K pursuant", 900_000),
    ("gross proceeds of $4 15,000 (the", 415_000),
    ("gross proceeds of up to $2.500,000 through", None),
    ("COMPLETION OF $1,500 MILLION SENIOR NOTES", 1_500_000_000),
]


def self_test(verbose: bool = False) -> int:
    saved = dict(FLAGS)
    FLAGS.update({k: True for k in FLAGS})
    bad = 0
    try:
        for h, want in _ROLE_CASES:
            got = classify_role(h, "")[0]
            if got != want:
                bad += 1
                print(f"ROLE FAIL: {got!r} != {want!r}  | {h}")
        for text, want in _AMOUNT_CASES:
            i = text.index("$") + 1 if "$" in text else 0
            while i < len(text) and not text[i].isdigit():
                i += 1
            got, _ = read_amount(text, i)
            if got is not None and not plausible_gross(got):
                got = None
            if (got is None) != (want is None) or (got and abs(got - want) > 0.5):
                bad += 1
                print(f"AMOUNT FAIL: {got!r} != {want!r}  | {text}")
        # headline gross must not be a unit price, a gold price or an AISC
        cases = [
            ("King Announces Exercise of 7,201,778 Warrants at $0.45/Share for Proceeds of $3,240,800", 3_240_800),
            ("Artemis Gold Reports Q2 2025 Results Consistent with Guidance: Post-commercial AISC US$805 per ounce", None),
            ("Hot Chili Closes A$40 Million Private Placement", 40_000_000),
        ]
        for h, want in cases:
            got = extract_fields(h, "").get("gross_total")
            if got != want:
                bad += 1
                print(f"HEADLINE GROSS FAIL: {got!r} != {want!r} | {h}")
        if extract_fields("Hot Chili Closes A$40 Million Private Placement", "").get("currency") != "AUD":
            bad += 1
            print("CURRENCY FAIL: A$ -> AUD")
        # E8: shares outstanding is not the offering
        b = ("Altius has 58,748,220 common shares issued and outstanding. The Company issued "
             "2,000,000 common shares at $0.50 per share.")
        if extract_fields("x", b).get("unit_count") != 2_000_000:
            bad += 1
            print("OUTSTANDING FAIL")
        # E6: lede amount, and the guards
        if lede_amount("The Company is pleased to announce a non-brokered private placement of up to $500,000 "
                       "by the issuance of units.") != (500_000, None, "lede_p1"):
            bad += 1
            print("LEDE FAIL: basic")
        if lede_amount("Insiders participated in the Offering for $40,000.", closing=True) is not None:
            bad += 1
            print("LEDE FAIL: insider participation")
        if lede_amount("Following the successful closing of our $11.1 million financing, drilling began.") is not None:
            bad += 1
            print("LEDE FAIL: past financing")
        # is_about_financing
        for h, want in [("Maple Gold Raises $3,256,096 in Warrant Acceleration Program", False),
                        ("Casa Minerals Inc. Receives Proceeds of $432,777 from Warrant Exercises", False),
                        ("Eminent To Raise $5 Million Led by Strategic Investor, Kinross Gold Corp.", True),
                        ("Irving Resources Reports Non-Brokered Private Placement", True)]:
            if is_about_financing(h, "") != want:
                bad += 1
                print(f"DEAL FAIL: {not want} | {h}")
    finally:
        FLAGS.clear()
        FLAGS.update(saved)
    n = len(_ROLE_CASES) + len(_AMOUNT_CASES) + 12
    print(f"self_test: {n - bad}/{n} passed")
    return bad


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(1 if self_test() else 0)
