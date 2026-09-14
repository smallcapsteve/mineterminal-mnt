#!/usr/bin/env python3
"""Who joined, who left, and what job they took.

There is no "Management Changes" category — `categorize.py` has nine and none of
them is this — so appointments and resignations sit inside Corporate Updates
(8,851 releases). This module is therefore a **detector as well as an
extractor**: it decides whether a release announces a management change, and
that decision is simply whether it can name a person and a role.

**The precision problem is companies, not people.** A junior miner "appoints" an
auditor, a transfer agent, a market maker and an IR firm far more often than it
appoints a CFO, and those read identically at the grammar level:

    Cameo Appoints Duranya Sebabili Director and Country Manager   <- a person
    Terra Clean Energy Engages Independent Trading Group as Market Maker
    Golden Cariboo Appoints Computershare as Transfer Agent

So an appointee that looks like a company, or a role belonging to a service
provider, is rejected outright. That one rule is what separates this from a
keyword search.

**Names are matched case-sensitively, and that is deliberate.** The first draft
matched everything with `re.I`, which makes "AS", "AND" and "THE" as good a
surname as any in an ALL-CAPS headline — it turned "Resignation of Jane Smith as
Chief Financial Officer" into a person called "Jane Smith as Ch". The verbs and
roles carry their own `(?i:)` so ALL-CAPS headlines still match.

    python3 management_extract.py       # run the self-test
"""
from __future__ import annotations

import re
import sys

# --------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------

# Credentials trail a name: "Ken Wheatley, P.Geol., M.Sc., as Senior Advisor".
# They sit BETWEEN the name and the role, so they are stripped from the text
# before matching — stripping after cannot help, the match never happens.
_CRED = (r"P\.?\s?Geo(?:l)?\.?|P\.?\s?Eng\.?|Ph\.?\s?D\.?|M\.?\s?Sc\.?|B\.?\s?Sc\.?"
         r"|M\.?B\.?A\.?|C\.?P\.?A\.?|C\.?F\.?A\.?|ICD\.?D|LL\.?B|M\.?\s?Eng\.?"
         r"|F?AusIMM|C\.?P\.?G\.?|P\.?Geo")
_CRED_RE = re.compile(rf"\s*,\s*(?:{_CRED})\.?(?=\s*[,\s])", re.I)

# A particle keeps its lowercase: "Marina Fagundes de Freitas", "Stuart Van Bibber".
_PARTICLE = r"(?:de|del|da|das|dos|van|von|der|den|la|le|du|di|bin|al)"

# Function words are never name tokens. Checked explicitly because an ALL-CAPS
# headline makes them the same shape as a surname.
_STOP = (r"as|and|to|the|of|for|with|its|his|her|our|new|from|at|in|on|a|an|is|"
         r"has|been|who|will|that|effective|announces|appoints|appointment|names")

_NT = rf"(?:(?!(?i:{_STOP})\b)[A-Z][A-Za-z'’\-]+\.?|[A-Z]\.|{_PARTICLE})"

# A headline introduces a person by describing them first: "Veteran Explorer Ross
# Brown", "Director Jean-Marc Gagnon", "Three Highly Experienced Industry Experts".
# The description is not the name. Leading descriptors are stripped; a name that
# still contains one is not a name at all.
_DESCRIPTOR = {
    "veteran", "experienced", "highly", "industry", "expert", "experts",
    "seasoned", "respected", "renowned", "accomplished", "leading",
    "director", "directors", "chairman", "chairwoman", "chair", "president",
    "ceo", "cfo", "coo", "cto", "officer", "manager", "advisor", "adviser",
    "explorer", "geologist", "engineer", "executive", "interim", "new",
    "transaction", "oriented", "technical", "corporate", "mining", "team",
    "three", "two", "four", "five", "several", "additional", "co-founder",
    "founder", "mr", "mrs", "ms", "dr", "prof",
}
_NAME = rf"(?:(?i:Dr|Mr|Ms|Mrs)\.?\s+)?{_NT}(?:\s+{_NT}){{1,4}}"
_NAME_LAZY = rf"{_NT}(?:\s+{_NT}){{1,2}}?"

# Roles, longest first so "Chief Executive Officer" beats "Officer".
_ROLES = [
    r"Chief\s+Executive\s+Officer", r"Chief\s+Financial\s+Officer",
    r"Chief\s+Operating\s+Officer", r"Chief\s+Technical\s+Officer",
    r"Chief\s+Geologist", r"Chief\s+Exploration\s+Officer",
    r"Chief\s+Development\s+Officer", r"Chief\s+Legal\s+Officer",
    r"Executive\s+Chair(?:man|woman|person)?",
    r"Non[\-\s]Executive\s+Chair(?:man|woman|person)?",
    r"Chair(?:man|woman|person)?\s+of\s+the\s+Board",
    r"Lead\s+Director", r"Independent\s+Director", r"Managing\s+Director",
    r"Executive\s+Vice[\-\s]President(?:\s+[A-Za-z&]+(?:\s+[A-Za-z&]+){0,4})?",
    r"Senior\s+Vice[\-\s]President(?:\s+[A-Za-z&]+(?:\s+[A-Za-z&]+){0,4})?",
    r"Vice[\-\s]President(?:\s+of)?(?:\s+[A-Za-z&]+(?:\s+[A-Za-z&]+){0,4})?",
    r"General\s+Counsel", r"Corporate\s+Secretary", r"Company\s+Secretary",
    r"Country\s+Manager(?:,?\s+[A-Z][A-Za-z]+)?", r"General\s+Manager",
    r"Technical\s+Advis[oe]r", r"Senior\s+Geological\s+Advis[oe]r",
    r"Strategic\s+Advis[oe]r", r"Special\s+Advis[oe]r", r"Advisory\s+Board",
    r"Technical\s+Manager", r"Exploration\s+Manager", r"Project\s+Manager",
    r"Head\s+of\s+[A-Z][A-Za-z]+(?:\s+[A-Za-z]+){0,3}",
    r"President\s+and\s+CEO", r"President\s+&\s+CEO",
    r"Interim\s+C[EFO]O", r"Interim\s+Chief\s+[A-Za-z]+\s+Officer",
    r"Board\s+of\s+Directors",
    r"CEO", r"CFO", r"COO", r"CTO",
    r"VP\s+[A-Za-z&]+(?:\s+[A-Za-z&]+){0,3}", r"VP",
    r"President", r"Chair(?:man|woman|person)?", r"Directors?",
    r"Treasurer", r"Secretary", r"Geologist", r"Advis[oe]r",
]
_ROLE = "(?:" + "|".join(_ROLES) + ")"

# An appointee that is a company, not a person.
_COMPANY_TAIL = re.compile(
    r"\b(?:Inc|Ltd|Limited|Corp|Corporation|LLC|LLP|PLC|Group|Capital|Partners|"
    r"Holdings|Securities|Trust|Services|Solutions|Media|Communications|"
    r"Associates|Consulting|Consultants|Advisors|Advisers|Company|Co)\b\.?",
    re.I)

# A role belonging to a service provider, not an officer of the company.
_SERVICE_ROLE = re.compile(
    r"\b(?:auditor|transfer\s+agent|market\s+maker|market[\-\s]mak(?:ing|er)|"
    r"investor\s+relations|IR\s+firm|registrar|trustee|escrow\s+agent|"
    r"underwriter|sponsor|promotional\s+services)\b", re.I)

# "joins" is deliberately absent: in "Thompson Hickey Joins Canadian Copper's
# Board" the person comes BEFORE the verb, and treating it like "appoints" made
# the company the appointee. It has its own pattern below.
APPOINT = (r"appoint(?:s|ed|ments?\s+of|ment\s+of)?|names?|welcom(?:es|ed)|"
           r"promot(?:es|ed)|elect(?:s|ed)")
DEPART = (r"(?:resign(?:s|ed|ation)?|retir(?:es|ed|ement)?|step(?:s|ped)\s+down|"
          r"depart(?:s|ure)?)\b")

_PATTERNS = [
    # "... Appoints Harold Gibson as Technical Advisor"
    ("appointed", re.compile(
        rf"\b(?i:{APPOINT})\s+(?P<person>{_NAME})\s*,?\s+"
        rf"(?i:as|to\s+(?:the\s+)?(?:position\s+of\s+)?)\s*"
        rf"(?i:its\s+|our\s+|the\s+|a\s+|an\s+|new\s+)*(?P<role>(?i:{_ROLE}))")),

    # "... Appointment of Pierre-Philippe Dupont as Senior Vice President ..."
    ("appointed", re.compile(
        rf"\b(?i:appointment\s+of)\s+(?P<person>{_NAME})\s*,?\s+(?i:as|to)\s+"
        rf"(?i:its\s+|our\s+|the\s+|a\s+|an\s+|new\s+)*(?P<role>(?i:{_ROLE}))")),

    # "... Appoints Garland Scott to the Board of Directors"
    ("appointed", re.compile(
        rf"\b(?i:{APPOINT})\s+(?P<person>{_NAME})\s+(?i:to)\s+(?i:its\s+|the\s+)?"
        rf"(?P<role>(?i:Board\s+of\s+Directors|Board|Advisory\s+Board))")),

    # "... Appoints Duranya Sebabili Director and Country Manager"  (no "as").
    # The name is lazy so the shortest name that still leaves a role wins;
    # greedy matching made the person "Duranya Sebabili Director".
    ("appointed", re.compile(
        rf"\b(?i:{APPOINT})\s+(?P<person>{_NAME_LAZY})\s+(?P<role>(?i:{_ROLE}))\b")),

    # "... announces the resignation of Jane Smith as CFO"
    ("departed", re.compile(
        rf"\b(?i:resignation|retirement|departure)\s+(?i:of)\s+(?P<person>{_NAME})"
        rf"(?:\s*,?\s+(?i:as|from)\s+(?i:its\s+|the\s+)?(?P<role>(?i:{_ROLE})))?")),

    # "Jane Smith resigns as CFO"
    ("departed", re.compile(
        rf"(?P<person>{_NAME})\s+(?i:has\s+)?(?i:{DEPART})"
        rf"(?:\s*,?\s+(?i:as|from)\s+(?i:its\s+|the\s+)?(?P<role>(?i:{_ROLE})))?")),

    # "Thompson Hickey Joins Canadian Copper's Board of Directors"
    # "Miguel Paucar Joins Lancaster Resources Advisory Board"
    ("appointed", re.compile(
        rf"(?P<person>{_NAME})\s+(?i:joins)\s+(?:[^,]{{0,44}}?\s+)?"
        rf"(?P<role>(?i:{_ROLE}))\b")),

    # "Jane Smith has been appointed Chief Financial Officer"
    ("appointed", re.compile(
        rf"(?P<person>{_NAME})\s+(?i:has\s+been\s+|was\s+|is\s+)?"
        rf"(?i:appointed|named|promoted)\s+(?i:as\s+|to\s+)?"
        rf"(?i:its\s+|our\s+|the\s+|a\s+|an\s+|new\s+)*(?P<role>(?i:{_ROLE}))")),
]

# A role-only announcement with nobody named: "ANNOUNCES APPOINTMENT OF INTERIM CFO"
# The verb and the role are often separated by the description of the person,
# and sometimes nobody is named at all:
#   "Appoints Transaction Oriented CEO and Director"
#   "Welcomes Three Highly Experienced Industry Experts to Advisory Board"
#   "Announces Appointments of Chief Financial Officer"
#   "Emperor Metals CEO Appointed to Board of Directors of McEwen Inc."
# Up to six filler words are allowed between the two — bounded, and only ever
# after an appointment verb.
_ROLE_ONLY = re.compile(
    rf"\b(?i:appointments?\s+of|appoint(?:s|ed|ment)?|names?|welcom(?:es|ed)|"
    rf"elect(?:s|ed))\s+"
    rf"(?:[A-Za-z'’\-]+\s+){{0,6}}?(?P<role>(?i:{_ROLE}))\b")

_BOARD_ROLE = re.compile(r"\b(?:board|director|chair)", re.I)
_ADVISORY_ROLE = re.compile(r"\badvis", re.I)
# "Alma Gold Inc. Announces Director Resignation" / "Appoints New Director" --
# a bare role with an appointment or departure verb beside it is a management
# change even with nobody named. Rejecting these cost 453 real releases.
_ROLE_THEN_VERB = re.compile(
    rf"(?P<role>(?i:{_ROLE}))\s+(?i:resignation|appointment|change|transition|departure)s?\b")

MAX_PERSON_CHARS = 60
MAX_ROLE_CHARS = 70


def _clean_person(s: str) -> str:
    toks = (s or "").strip().split()
    while toks and toks[0].lower().strip(".,") in _DESCRIPTOR:
        toks.pop(0)
    return " ".join(toks).strip(" ,;–—-")[:MAX_PERSON_CHARS]


def _is_person(name: str) -> bool:
    """A name that still contains a descriptor was never a name."""
    toks = [t.lower().strip(".,'’") for t in (name or "").split()]
    if len(toks) < 2 or len(toks) > 5:
        return False
    if any(t in _DESCRIPTOR for t in toks):
        return False
    if _COMPANY_TAIL.search(name):
        return False
    # "Canadian Copper's Board" -- a possessive is a company, not a person
    return not any(t.endswith("'s") or t.endswith("’s") for t in (name or "").split())


def _clean_role(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    s = re.sub(r"\s+(?i:and|&)\s+(?i:announces|provides|begins|commences|reports).*$", "", s)
    return s.strip(" ,;–—-")[:MAX_ROLE_CHARS]


def _scope(role: str) -> str:
    if _ADVISORY_ROLE.search(role or ""):
        return "advisory"
    if _BOARD_ROLE.search(role or ""):
        return "board"
    return "management"


def extract(headline: str, body: str = "") -> dict:
    """{'changes': [...], 'top_person', 'top_role', 'top_action', 'top_scope'}
    — an empty 'changes' means this release is not a management change."""
    hl = (headline or "").strip()
    text = hl if hl else (body or "")[:1200]
    if not text:
        return {"changes": []}
    text = _CRED_RE.sub("", text)

    if _SERVICE_ROLE.search(text):
        # "engages X as market maker" and friends are not management changes,
        # however identical the grammar.
        return {"changes": []}

    seen: set[str] = set()
    changes = []
    for action, pat in _PATTERNS:
        for m in pat.finditer(text):
            person = _clean_person(m.groupdict().get("person") or "")
            role = _clean_role(m.groupdict().get("role") or "")
            if not person or not _is_person(person):
                continue
            key = person.lower()
            if key in seen:
                continue
            seen.add(key)
            changes.append({"action": action, "person": person,
                            "role": role or None, "scope": _scope(role)})

    if not changes:
        for pat, action in ((_ROLE_ONLY, "appointed"), (_ROLE_THEN_VERB, None)):
            m = pat.search(text)
            if not m or _SERVICE_ROLE.search(m.group(0)):
                continue
            role = _clean_role(m.group("role"))
            if not role or len(role) < 3:
                continue
            act = action or ("departed" if re.search(
                r"(?i:resignation|departure)", m.group(0)) else "appointed")
            changes.append({"action": act, "person": None,
                            "role": role, "scope": _scope(role)})
            break

    if not changes:
        return {"changes": []}
    top = changes[0]
    return {"changes": changes, "top_person": top["person"],
            "top_role": top["role"], "top_action": top["action"],
            "top_scope": top["scope"]}


SELF_TEST = [
    # (headline, person, role must contain, action) — all real MNT headlines
    ("OCEANIC ANNOUNCES THE APPOINTMENT OF PIERRE-PHILIPPE DUPONT AS SENIOR VICE "
     "PRESIDENT EXTERNAL AFFAIRS AND ESG",
     "PIERRE-PHILIPPE DUPONT", "SENIOR VICE PRESIDENT", "appointed"),
    ("Errington Metals appoints Harold Gibson as Technical Advisor and Begins Fall "
     "Drill Campaign", "Harold Gibson", "Technical Advisor", "appointed"),
    ("Western Star Resources Appoints Garland Scott to the Board of Directors",
     "Garland Scott", "Board of Directors", "appointed"),
    ("Zodiac Gold Appoints Brett Richards as Chairman and Announces AGSM Results",
     "Brett Richards", "Chairman", "appointed"),
    ("Eastport Critical Metals Appoints Dr. Robert Bowell as Technical Manager",
     "Robert Bowell", "Technical Manager", "appointed"),
    ("Cascadia Strengthens Management Team with the Appointment of Stuart Van Bibber "
     "as VP Sustainability", "Stuart Van Bibber", "VP", "appointed"),
    # credentials sit between the name and the role
    ("Belmont Resources Appoints Ken Wheatley, P.Geol., M.Sc., as Senior Geological "
     "Advisor", "Ken Wheatley", "Senior Geological Advisor", "appointed"),
    # no "as", and the role must not be swallowed into the name
    ("Cameo Appoints Duranya Sebabili Director and Country Manager, Tanzania",
     "Duranya Sebabili", "Director", "appointed"),
    ("Abitibi Metals Appoints Keith Gorman as Chief Financial Officer",
     "Keith Gorman", "Chief Financial Officer", "appointed"),
    ("Spark Energy Minerals Appoints Marina Fagundes de Freitas to its Board of "
     "Directors", "Marina Fagundes de Freitas", "Board of Directors", "appointed"),
    ("Cameo Resources Appoints Duranya Sebabili as Director & Country Manager, "
     "Tanzania", "Duranya Sebabili", "Director", "appointed"),
    # a role with nobody named is still a management change
    ("GOLCAP ANNOUNCES APPOINTMENT OF INTERIM CFO", None, "INTERIM CFO", "appointed"),
    # ALL-CAPS "AS" is not a surname — this was a real bug
    ("Example Gold Announces the Resignation of Jane Alexander Smith as Chief "
     "Financial Officer", "Jane Alexander Smith", "Chief Financial Officer", "departed"),
    ("John Robert Doe resigns as Chief Executive Officer of Example Mining",
     "John Robert Doe", "Chief Executive Officer", "departed"),
    # --- everything below was found by running v1 over all 18,209 approved
    # --- releases and reading the output. None of it failed the tests above.
    # the person comes before "joins", and the company after it
    ("Thompson Hickey Joins Canadian Copper's Board of Directors",
     "Thompson Hickey", "Board of Directors", "appointed"),
    ("Miguel Paucar Joins Lancaster Resources Advisory Board to Propel Growth",
     "Miguel Paucar", "Advisory Board", "appointed"),
    # a headline describes the person before naming them
    ("Lancaster Resources Appoints Veteran Explorer Ross Brown as VP, Exploration",
     "Ross Brown", "VP", "appointed"),
    ("Alma Gold Announces the Retirement of Director Jean-Marc Gagnon",
     "Jean-Marc Gagnon", "", "departed"),
    # nobody is named, but it is still a management change
    ("Highrock Resources Appoints Transaction Oriented CEO and Director",
     None, "CEO", "appointed"),
    ("Lancaster Resources Welcomes Three Highly Experienced Industry Experts to "
     "Advisory Board", None, "Advisory Board", "appointed"),
    ("Emperor Metals CEO Appointed to Board of Directors of McEwen Inc.",
     None, "Board of Directors", "appointed"),
    ("Ameriwest Lithium Announces Appointments of Chief Financial Officer and a "
     "Veteran Mining Engineer", None, "Chief Financial Officer", "appointed"),
    ("Alma Gold Inc. Announces Director Resignation", None, "Director", "departed"),
    ("Oakley Ventures Inc. Appoints New Director", None, "Director", "appointed"),
    ("Alma Gold Inc. Focusses on Guinea, Appoints New Directors and Chief Financial "
     "Officer", None, "Director", "appointed"),
]

REJECT_TEST = [
    # the precision problem: a company appointed to a service role
    "Terra Clean Energy Corp. Engages Independent Trading Group as Market Maker",
    "Western Star Engages Baystreet.ca Media Corp. for Investor Relations",
    "Golden Cariboo Appoints Computershare Trust Company as Transfer Agent",
    "Example Gold Appoints Smith LLP as Auditor",
    # and releases that are simply about something else
    "Scottie Announces $27 Million Non-Brokered Financing",
    "Bravo Intercepts 54m at 2.8 g/t PGM+Au + 0.16% Ni, including 5m at 10.7 g/t",
    "Metalite Announces Upsizing of Private Placement to up to $700,000",
    "IBN Promotional Services Contract",
    # a company called Departures Capital is not a departure
    "UPSIDE GOLD ENGAGES DEPARTURES CAPITAL FOR DIGITAL MARKETING SERVICES",
    "Myriad Engages Departures Capital to Conduct Digital Marketing Program",
]


def self_test(verbose: bool = True) -> int:
    bad = 0
    for hl, want_p, want_r, want_a in SELF_TEST:
        out = extract(hl)
        got_p, got_r = out.get("top_person"), out.get("top_role") or ""
        got_a = out.get("top_action")
        ok = (got_p == want_p) and (want_r.lower() in got_r.lower()) and (got_a == want_a)
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  {str(got_p)[:26]:<26} | {got_r[:34]:<34} | {got_a}"
                  f"{'' if ok else f'{chr(10)}        WANTED {want_p!r} | role~{want_r!r} | {want_a}'}")
    for hl in REJECT_TEST:
        out = extract(hl)
        ok = not out.get("changes")
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  reject {hl[:56]!r}")
    total = len(SELF_TEST) + len(REJECT_TEST)
    if verbose:
        print(f"\n{total - bad}/{total} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(self_test())
