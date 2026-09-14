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

# The same credentials with no comma in front: "Marcio Fonseca P.Geo to Board".
# Restricted to the dotted forms so ordinary words are never eaten.
_CRED_BARE_RE = re.compile(
    r"\s+(?:P\.\s?Geo(?:l)?|P\.\s?Eng|Ph\.\s?D|M\.\s?Sc|B\.\s?Sc|C\.P\.G)\.?(?=\s|$)",
    re.I)

# A particle keeps its lowercase: "Marina Fagundes de Freitas", "Stuart Van Bibber".
_PARTICLE = r"(?:de|del|da|das|dos|van|von|der|den|la|le|du|di|bin|al)"

# Function words are never name tokens. Checked explicitly because an ALL-CAPS
# headline makes them the same shape as a surname.
_STOP = (r"as|and|to|the|of|for|with|its|his|her|our|new|from|at|in|on|a|an|is|"
         r"has|been|who|will|that|effective|announces|appoints|appointment|names")

# Accented names: "Guy Bedard", "Jean-Francois Meilleur", "Eric Lemieux" -- all
# of them spelled with accents in the real headline. Half of Canadian mining is
# Quebecois and [A-Za-z] does not spell their names.
_U = r"A-Z\u00c0-\u00d6\u00d8-\u00de"
_L = r"a-z\u00df-\u00f6\u00f8-\u00ff"
# The lookahead below blocks a stop word only at the exact offset it is tried.
# Without a left boundary the engine simply advances one character and tries
# again: "ANNOUNCES" is rejected, "NNOUNCES" is not, and the corpus grew a
# person called "NNOUNCES BOARD".
_NT = (rf"(?:(?<![{_U}{_L}])"
       rf"(?:(?!(?i:{_STOP})\b)[{_U}][{_U}{_L}'’\-]+\.?|[{_U}]\.|{_PARTICLE}))")

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
    # "CanAlaska Announces Senior Management Change Nathan Bridge Resigns" made
    # all four leading words part of the name; "board" is why NNOUNCES BOARD
    # got past _is_person.
    "board", "boards", "management", "senior", "change", "changes",
    "announces", "announce", "announced", "appointment", "appointments",
    "resignation", "retirement", "departure", "vice", "chief", "head",
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
    r"Strategic\s+Advis[oe]r", r"Special\s+Advis[oe]r",
    r"(?:Scientific|Technical|Strategic)\s+Advisory\s+Board", r"Advisory\s+Board",
    r"Technical\s+Manager", r"Exploration\s+Manager", r"Project\s+Manager",
    r"Head\s+of\s+[A-Z][A-Za-z]+(?:\s+[A-Za-z]+){0,3}",
    r"President\s+and\s+CEO", r"President\s+&\s+CEO",
    r"Interim\s+C[EFO]O", r"Interim\s+Chief\s+[A-Za-z]+\s+Officer",
    r"Board\s+of\s+Directors",
    r"CEO", r"CFO", r"COO", r"CTO",
    r"V\.?P\.?\s+[A-Za-z&]+(?:\s+[A-Za-z&]+){0,3}", r"V\.?P\.?",
    r"President", r"Chair(?:man|woman|person)?", r"Directors?",
    r"Treasurer", r"Secretary", r"Geologist", r"Advis[oe]r", r"Board",
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
           r"promot(?:es|ed)|elect(?:s|ed)|add(?:s|ed)|"
           r"nominat(?:es|ed|ions?\s+of)|expand(?:s|ed)")
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
    rf"elect(?:s|ed)|add(?:s|ed)|nominat(?:es|ed|ions?\s+of)|expand(?:s|ed))\s*"
    rf"(?:[A-Za-z'’\-]+\s+){{0,6}}?(?P<role>(?i:{_ROLE}))\b")

# A reshuffle with nobody named: "Announces Changes to Board of Directors".
# Neither a joining nor a leaving. v3 folded these into the appointment verbs,
# which reported 23 board shuffles as appointments. _ROLE_ONLY is tried first,
# so "Changes To The Board - Appoints New Interim CEO" is still an appointment.
_ROLE_CHANGED = re.compile(
    rf"\b(?i:changes?\s+to|restructur(?:es|ed|ing))\s*"
    rf"(?:[A-Za-z'’\-]+\s+){{0,6}}?(?P<role>(?i:{_ROLE}))\b")


_BOARD_ROLE = re.compile(r"\b(?:board|director|chair)", re.I)
_ADVISORY_ROLE = re.compile(r"\badvis", re.I)
# "Alma Gold Inc. Announces Director Resignation" / "Appoints New Director" --
# a bare role with an appointment or departure verb beside it is a management
# change even with nobody named. Rejecting these cost 453 real releases.
_ROLE_THEN_VERB = re.compile(
    rf"(?P<role>(?i:{_ROLE}))\s+(?:[A-Za-z&]+\s+){{0,3}}?"
    rf"(?i:resignation|appointment|change|transition|departure|nomination)s?\b")

_TITLE_WORDS = {
    # rank
    "chief", "senior", "executive", "vice", "president", "vice-president",
    "non-executive", "deputy", "assistant", "interim", "acting", "lead",
    "leading", "managing", "general", "global", "group", "principal",
    "chair", "chairman", "chairwoman", "chairperson", "director", "directors",
    "officer", "manager", "head", "advisor", "adviser", "advisory", "board",
    "counsel", "secretary", "treasurer", "controller", "partner", "associate",
    "vp", "v.p.", "evp", "svp", "ceo", "cfo", "coo", "cto", "cio", "cso",
    # function
    "exploration", "operations", "operating", "development", "finance",
    "financial", "technical", "technology", "corporate", "commercial",
    "business", "strategy", "strategic", "growth", "capital", "markets",
    "investor", "investors", "relations", "communications", "marketing",
    "sustainability", "regulatory", "affairs", "external", "internal",
    "esg", "environment", "environmental", "social", "governance", "community",
    "health", "safety", "security", "legal", "compliance", "risk", "audit",
    "accounting", "administration", "administrative", "information", "data",
    "digital", "innovation", "engineering", "metallurgy", "metallurgical",
    "geology", "geological", "geoscience", "geologist", "mining", "mine",
    "mines", "projects", "project", "process", "processing", "production",
    "resource", "resources", "reserves", "supply", "chain", "procurement",
    "permitting", "land", "lands", "tenements", "indigenous", "government",
    "public", "stakeholder", "people", "culture", "talent", "human",
    "sales", "country", "regional", "special", "scientific", "geotechnical",
}
# A connector survives only when a title word follows it. "to" is absent on
# purpose: it let "VP of Exploration To Head Up Exploration at Bleasdell"
# through, because "Head" is a real title word and the connector skipped past
# the word that actually ended the title.
_TITLE_JOIN = {"of", "and", "&", "the", "its", "for", ",", "-"}


def _trim_role_tail(role: str) -> str:
    """Cut a captured role at the first word that cannot belong to a job title.

    The role patterns take up to five arbitrary words, which is what a real
    title needs ("Senior Vice President of Corporate Development and Growth")
    and also what carries them out of the title and into whatever follows it.
    Trimming once here beats bounding five regexes, and an unrecognised word
    ends the title, so the failure mode is a role that is too short rather than
    one that is wrong.
    """
    toks = role.split()
    if len(toks) < 2:
        return role
    last_kept = 0  # the first token is the anchor and is always kept
    for i in range(1, len(toks)):
        w = toks[i].lower().strip(".,;:()&")
        if not w:
            continue
        if w in _TITLE_WORDS or all(
                p in _TITLE_WORDS for p in w.split("-") if p):
            last_kept = i
        elif w in _TITLE_JOIN:
            continue  # provisional: kept only if a title word follows
        else:
            break
    return " ".join(toks[:last_kept + 1])


MAX_PERSON_CHARS = 60

MAX_ROLE_CHARS = 70


# "Jacques Trottier Phd" -- _CRED_BARE_RE deliberately requires the dots so that
# ordinary words are never eaten, which leaves the undotted spellings behind.
# Trimming them off the end of a name is safe in a way that a text-wide regex
# is not.
_TRAILING_CRED = {
    "phd", "ph.d", "ph.d.", "mba", "m.b.a", "cpa", "cfa", "pgeo", "p.geo",
    "peng", "p.eng", "msc", "m.sc", "bsc", "b.sc", "meng", "m.eng",
    "icdd", "icd.d", "llb", "ll.b", "cpg", "c.p.g", "ausimm", "fausimm",
    "jr", "sr", "ii", "iii", "iv",
}


# A headline titles a person before naming them: "Secretary Kristi L. Noem",
# "Major General Eldon Regua", "Former Noront CEO Alan Coutts". Every title word
# is also leading junk, or v6's rule below throws the name away with the title.
_PRIOR_AFFILIATION = re.compile(r"\s*(?:former|ex)\b[\s\-]", re.I)

_LEADING_JUNK = _DESCRIPTOR | _TITLE_WORDS | {
    "leader", "minister", "ambassador", "governor", "senator", "premier",
    "mayor", "specialist", "strategist", "entrepreneur", "financier",
    "major", "colonel", "captain", "general", "hon", "honourable", "honorable",
    "sir", "former", "retired", "outgoing", "incoming", "current", "longtime",
}


def _clean_person(s: str) -> str:
    toks = (s or "").strip().split()
    while toks and toks[0].lower().strip(".,") in _LEADING_JUNK:
        toks.pop(0)
    while len(toks) > 2 and toks[-1].lower().strip(".,") in _TRAILING_CRED:
        toks.pop()
    return " ".join(toks).strip(" ,;–—-")[:MAX_PERSON_CHARS]



def _is_person(name: str) -> bool:
    """A name that still contains a descriptor was never a name."""
    toks = [t.lower().strip(".,'’") for t in (name or "").split()]
    if len(toks) < 2 or len(toks) > 5:
        return False
    if any(t in _DESCRIPTOR for t in toks):
        return False
    # A title word is not a name. Bare "Board" in _ROLES gave the lazy-name
    # pattern a place to stop, and "EXPANDS SCIENTIFIC ADVISORY BOARD" became a
    # person called "SCIENTIFIC ADVISORY".
    if any(t in _TITLE_WORDS for t in toks):
        return False
    if _COMPANY_TAIL.search(name):
        return False
    # "Canadian Copper's Board" -- a possessive is a company, not a person
    return not any(t.endswith("'s") or t.endswith("’s") for t in (name or "").split())


def _clean_role(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    s = re.sub(r"\s+(?i:and|&)\s+(?i:announces|provides|begins|commences|reports).*$", "", s)
    s = _trim_role_tail(s)
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
    # "Jean – Marc Gagnon" -- a spaced dash inside a name is still one name.
    text = re.sub(r"(?<=[A-Za-z])\s+[–—]\s+(?=[A-Z])", "-", text)
    # "Marcio Fonseca P.Geo to Board" -- a credential with no comma before it.
    text = _CRED_BARE_RE.sub("", text)

    seen: set[str] = set()
    changes = []
    for action, pat in _PATTERNS:
        for m in pat.finditer(text):
            if _SERVICE_ROLE.search(m.group(0)):
                # "engages X as market maker" and friends are not management
                # changes, however identical the grammar. Judged on the match,
                # not on the whole headline.
                continue
            raw_person = m.groupdict().get("person") or ""
            if _PRIOR_AFFILIATION.match(raw_person):
                # "Former Gold Fields", "Former Electronic Arts", "Former Las
                # Bambas" -- a previous employer, not the appointee.
                continue
            person = _clean_person(raw_person)
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
        for pat, action in ((_ROLE_ONLY, "appointed"),
                            (_ROLE_CHANGED, "changed"),
                            (_ROLE_THEN_VERB, None)):
            m = pat.search(text)
            if not m or _SERVICE_ROLE.search(m.group(0)):
                continue
            role = _clean_role(m.group("role"))
            if not role or len(role) < 3:
                continue
            if action:
                act = action
            elif re.search(r"(?i:resignation|departure|retirement)", m.group(0)):
                act = "departed"
            elif re.search(r"(?i:changes?|transition)", m.group(0)):
                act = "changed"
            else:
                act = "appointed"
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
    # --- v5: found by auditing the 807 rows the page actually rendered. Every
    # --- one of the 35 tests above passed on the version that produced them.
    ("PROSPECT RIDGE ANNOUNCES BOARD RESIGNATION", None, "BOARD", "departed"),
    ("CanAlaska Announces Senior Management Change Nathan Bridge Resigns as "
     "Vice-President Exploration Following Completion of the Summer Drilling "
     "Program", "Nathan Bridge", "Vice-President Exploration", "departed"),
    ("Renforth Appoints Martin Demers VP of Exploration and Completes Final "
     "Closing of Private Placement.", "Martin Demers", "VP of Exploration",
     "appointed"),
    ("Dark Star Announces Appointment of VP of Exploration To Head Up Exploration "
     "at Bleasdell Historical Uranium Deposit, Saskatchewan", None,
     "VP of Exploration", "appointed"),
    ("Myriad Announces Changes to Board of Directors", None, "Board of Directors",
     "changed"),
    ("Carmanah Announces Changes To The Board – Appoints New Interim CEO", None,
     "Interim CEO", "appointed"),
    ("Precore Gold Announces Appointment Of Jacques Trottier Phd As Head Of Its "
     "Advisory Board", "Jacques Trottier", "Advisory Board", "appointed"),
]

# A substring check cannot prove that a role STOPPED where it should have. These
# assert the exact string, which is the only way to test a trimming rule.
MORE_SELF_TEST = [
    # v6: adding bare "Board" to _ROLES let title words be read as names
    ("TEMAS RESOURCES EXPANDS SCIENTIFIC ADVISORY BOARD", None,
     "SCIENTIFIC ADVISORY BOARD", "appointed"),
    # a board reshuffle by either wording
    ("Prospect Ridge Announces Board Changes", None, "Board", "changed"),
    ("McFarlane Lake Mining Announces Board Changes", None, "Board", "changed"),
    ("Mosaic Minerals Announces Board and Management Changes", None, "Board",
     "changed"),
    # ... and a real appointment is still an appointment
    ("Western Star Resources Appoints Garland Scott to the Board of Directors",
     "Garland Scott", "Board of Directors", "appointed"),
    # v7: a title in front of the name must be trimmed, not fatal
    ("Secretary Kristi L. Noem Joins NovaRed Mining Advisory Board",
     "Kristi L. Noem", "Advisory Board", "appointed"),
    ("Arya Resources Appoints Capital Markets Leader Cathy Hume to the Board",
     "Cathy Hume", "Board", "appointed"),
]

# A prior employer is never the appointee. Before v8 these produced people
# called "Gold Fields", "Electronic Arts", "Las Bambas" and "White House".
PRIOR_AFFILIATION_TEST = [
    "Pirate Gold Appoints Former Gold Fields Chief Geologist Dr. Alan Reid",
    "Yocale.ai Appoints Former Electronic Arts CTO Marija Radulovic",
    "Kuya Silver Appoints Former Las Bambas General Manager Edgar Vasquez",
    "Origen Appoints Former Serra Verde Board Member Mark Riccio",
]
SELF_TEST += MORE_SELF_TEST

ROLE_EXACT_TEST = [
    ("OCEANIC ANNOUNCES THE APPOINTMENT OF PIERRE-PHILIPPE DUPONT AS SENIOR VICE "
     "PRESIDENT EXTERNAL AFFAIRS AND ESG Vancouver, BC - Oceanic Iron Ore Corp.",
     "SENIOR VICE PRESIDENT EXTERNAL AFFAIRS AND ESG"),
    ("Metalite Announces Appointment of Carey Galeschuk as VP Exploration and "
     "Launch of New Website", "VP Exploration"),
    ("Volta Metals Strengthens Senior Team with Appointments of Philip Ng as VP "
     "Projects and Dr. Julie Selway as VP Exploration", "VP Projects"),
    ("Silver Hammer Mining Appoints Former Coeur Mining Senior Vice-President "
     "Exploration and Bill Dennis Prospector of the Year Award Recipient as Board "
     "Advisor", "Senior Vice-President Exploration"),
    # a genuine multi-word title must survive intact
    ("Abitibi Metals Continues to Strengthen Leadership Team with the Appointment "
     "of Ben Pullinger as Senior Vice President of Corporate Development and "
     "Growth", "Senior Vice President of Corporate Development and Growth"),
    ("Cascadia Strengthens Management Team with the Appointment of Stuart Van "
     "Bibber as VP Sustainability and Regulatory Affairs",
     "VP Sustainability and Regulatory Affairs"),
    ("Forge Resources Announces Appointment of Vice President of Finance and "
     "Special Advisor", "Vice President of Finance and Special Advisor"),
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
    for hl in PRIOR_AFFILIATION_TEST:
        got = extract(hl).get("top_person")
        ok = got is None or (" " in got and got.split()[0].lower() not in
                             {"gold", "electronic", "las", "serra", "white", "former"})
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  prior-affiliation -> person={got!r}")
    for hl, want in ROLE_EXACT_TEST:
        got = extract(hl).get("top_role")
        ok = got == want
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  role== {str(got)[:52]!r}"
                  f"{'' if ok else f'{chr(10)}        WANTED {want!r}'}")
    for hl in REJECT_TEST:
        out = extract(hl)
        ok = not out.get("changes")
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  reject {hl[:56]!r}")
    total = (len(SELF_TEST) + len(PRIOR_AFFILIATION_TEST)
             + len(ROLE_EXACT_TEST) + len(REJECT_TEST))
    if verbose:
        print(f"\n{total - bad}/{total} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(self_test())
