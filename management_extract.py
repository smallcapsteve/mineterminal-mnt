#!/usr/bin/env python3
"""Who joined, who left, and what job they took.

v9 (2026-09-15, offline audit -- see extract/management/FINDINGS.md). Since v6
the categoriser DOES have a Management Changes category, and it delegates to
this module OR its own headline rules, so the chip and the /management-changes
page disagreed. v9 keeps extract()'s return shape and adds infer_from_tag(),
which the v9 backfill uses to write a person-less row for tagged releases that
extract() cannot parse. The history below is kept as written.

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
    # v9: "Chief Psychedelic Officer", "Chief Sustainability Officer" -- any
    # one or two words between Chief and Officer is still a C-suite title.
    r"Chief\s+[A-Za-z]+(?:\s+[A-Za-z]+)?\s+Officer",
    # v9: an advisory body's chair is advisory, not board. Before this,
    # "Chair of Its New Technical Advisory Board" was cut to "Chair" (board).
    r"Chair(?:man|woman|person)?\s+of\s+(?:the\s+|its\s+)?(?:new(?:ly\s+\w+)?\s+)?"
    r"(?:\w+\s+){0,2}?Advisory\s+(?:Board|Committee|Council)",
    r"Executive\s+Chair(?:man|woman|person)?",
    r"Non[\-\s]Executive\s+Chair(?:man|woman|person)?",
    r"Chair(?:man|woman|person)?\s+of\s+the\s+Board",
    r"Lead\s+Director", r"Independent\s+Director", r"Managing\s+Director",
    # v9: "Project Director", "Director of Operations" are jobs, not board
    # seats. _scope() reads them as management.
    r"(?:Project|Operations|Technical|Exploration|Sales|Marketing|Commercial|"
    r"Finance|Communications|Mine|Site)\s+Director",
    r"Director\s+of\s+(?!the\s+Board)[A-Za-z&]+(?:\s+[A-Za-z&]+){0,4}",
    # v9: ", Exploration" continues a VP title. _trim_role_tail decides whether
    # what follows the comma is a function ("Exploration") or a second role.
    r"Executive\s+Vice[\-\s]President(?:,?\s+[A-Za-z&]+(?:\s+[A-Za-z&]+){0,4})?",
    r"Senior\s+Vice[\-\s]President(?:,?\s+[A-Za-z&]+(?:\s+[A-Za-z&]+){0,4})?",
    r"Vice[\-\s]President(?:,?\s+of)?(?:,?\s+[A-Za-z&]+(?:\s+[A-Za-z&]+){0,4})?",
    r"General\s+Counsel", r"Corporate\s+Secretary", r"Company\s+Secretary",
    r"Country\s+Manager(?:,?\s+[A-Z][A-Za-z]+)?", r"General\s+Manager",
    r"Technical\s+Advis[oe]r", r"Senior\s+Geological\s+Advis[oe]r",
    r"Strategic\s+Advis[oe]r", r"Special\s+Advis[oe]r",
    # v9: "Board Advisor", "Board of Advisors" were cut to "Board" (board scope)
    r"Board\s+Advis[oe]rs?", r"Board\s+of\s+Advis[oe]rs",
    r"(?:Scientific|Technical|Strategic)\s+Advisory\s+Board", r"Advisory\s+Board",
    r"(?:Scientific|Technical|Strategic)\s+Advisory\s+(?:Committee|Council)",
    r"Advisory\s+(?:Committee|Council)",
    r"Technical\s+Manager", r"Exploration\s+Manager", r"Project\s+Manager",
    r"Head\s+of\s+[A-Z][A-Za-z]+(?:\s+[A-Za-z]+){0,3}",
    r"President\s+and\s+CEO", r"President\s+&\s+CEO",
    r"Interim\s+C[EFO]O", r"Interim\s+Chief\s+[A-Za-z]+\s+Officer",
    r"Board\s+of\s+Directors",
    r"(?:Principal|Senior|Project|Exploration|Chief)\s+Geologist",
    r"CEO", r"CFO", r"COO", r"CTO",
    r"S\.?V\.?P\.?(?:,?\s+[A-Za-z&]+(?:\s+[A-Za-z&]+){0,3})?",
    r"E\.?V\.?P\.?(?:,?\s+[A-Za-z&]+(?:\s+[A-Za-z&]+){0,3})?",
    r"V\.?P\.?(?:,?\s+|-)[A-Za-z&]+(?:\s+[A-Za-z&]+){0,3}", r"V\.?P\.?",
    r"President", r"Chair(?:man|woman|person)?", r"Directors?",
    r"Treasurer", r"Secretary", r"Geologist", r"Advis[oe]r", r"Board",
]
_ROLE = "(?:" + "|".join(_ROLES) + ")"

# v9: words that qualify a title and belong to it: "as Non-Executive Director",
# "as Incoming CEO", "as Permanent Full Time CEO", "as Industry Advisor".
# Enumerated, never arbitrary words, and tried lazily so a title that already
# starts with one ("Senior Vice President", "Independent Director") matches as
# itself first.
_ROLE_MOD = (r"(?:(?:non[\-\s]?executive|incoming|permanent|full[\-\s]time|acting|"
             r"interim|senior|principal|lead|industry|innovation|exploration|esg|"
             r"independent|executive|technical|strategic|corporate|founding|"
             r"inaugural|co-?)[\s\-]+)*?")
_ROLE_Q = rf"(?i:{_ROLE_MOD}{_ROLE})"

# An appointee that is a company, not a person.
_COMPANY_TAIL = re.compile(
    r"\b(?:Inc|Ltd|Limited|Corp|Corporation|LLC|LLP|PLC|Group|Capital|Partners|"
    r"Holdings|Securities|Trust|Services|Solutions|Media|Communications|"
    r"Associates|Consulting|Consultants|Advisors|Advisers|Company|Co)\b\.?",
    re.I)

# A role belonging to a service provider, not an officer of the company.
# v9: a financial / capital-markets advisor is a bank or an IR shop in every
# corpus headline that names one ("McEwen Copper Appoints Societe Generale as
# Financial Advisor", "Avalon Appoints SCP Resource Finance as Strategic Capital
# Advisor", "Military Metals Appoints DGWA as European Financial Markets Advisor").
_SERVICE_ROLE = re.compile(
    r"\b(?:auditor|transfer\s+agent|market\s+maker|market[\-\s]mak(?:ing|er)|"
    r"investor\s+relations|IR\s+firm|registrar|trustee|escrow\s+agent|"
    r"underwriter|sponsor|promotional\s+services|"
    r"(?:financial|capital)(?:\s+markets)?\s+advis[oe]rs?|"
    # First North (Nasdaq Nordic) listing sponsor: "Announces Change of Swedish
    # Certified Adviser to Svensk Kapitalmarknadsgranskning"
    r"certified\s+advis[oe]r)\b", re.I)

# "joins" is deliberately absent: in "Thompson Hickey Joins Canadian Copper's
# Board" the person comes BEFORE the verb, and treating it like "appoints" made
# the company the appointee. It has its own pattern below.
APPOINT = (r"appoint(?:s|ed|ments?\s+of|ment\s+of)?|names?|welcom(?:es|ed)|"
           r"promot(?:es|ed)|elect(?:s|ed)|add(?:s|ed)|"
           r"nominat(?:es|ed|ions?\s+of)|expand(?:s|ed)")
DEPART = (r"(?:resign(?:s|ed|ation)?|retir(?:es|ed|ement)?|step(?:s|ped)\s+down|"
          r"depart(?:s|ure)?)\b")
# v9: articles between "as" and the title. "a"/"an" were missing from the
# departure patterns, so "Resignation of Julio Arce as a Director" lost its role.
_ART = r"(?i:its\s+|our\s+|the\s+|a\s+|an\s+|new\s+|company['’]s\s+|corporation['’]s\s+)*"

_PATTERNS = [
    # "... Appoints Harold Gibson as Technical Advisor"
    ("appointed", re.compile(
        rf"\b(?i:{APPOINT})\s+(?P<person>{_NAME})\s*,?\s+"
        rf"(?i:as|to\s+(?:the\s+)?(?:position\s+of\s+)?)\s*"
        rf"{_ART}(?P<role>{_ROLE_Q})")),

    # "... Appointment of Pierre-Philippe Dupont as Senior Vice President ..."
    # v9: also "Addition of", "Announces NAME as" -- "Loyalist Announces Len
    # Mackenzie as Vice-President Exploration", "Integral Metals Announces the
    # Addition of John David Clark as an Advisor to the Company".
    ("appointed", re.compile(
        rf"\b(?i:appointment\s+of)\s+(?P<person>{_NAME})\s*,?\s+(?i:as|to)\s+"
        rf"{_ART}(?P<role>{_ROLE_Q})")),

    # "... Appoints Garland Scott to the Board of Directors"
    ("appointed", re.compile(
        rf"\b(?i:{APPOINT})\s+(?P<person>{_NAME})\s+(?i:to)\s+(?i:its\s+|the\s+)?"
        rf"(?P<role>(?i:Board\s+of\s+Directors|Board|Advisory\s+Board))")),

    # v9: two or three people, one role -- "Blackrock Silver Announces the
    # Appointment of Bernard Poznanski and Susan Mathieu to the Board of
    # Directors". Before v9 these named nobody (role-only) or were silent.
    ("appointed", re.compile(
        rf"\b(?i:{APPOINT}|appointments?\s+of|announces?|welcom(?:es|ed)\s+"
        rf"(?:the\s+addition\s+of\s+)?)\s+(?:(?i:messrs\.?|mr\.|ms\.|dr\.)\s+)?"
        rf"(?P<person>{_NAME})\s*,\s*(?P<person3>{_NAME})\s*,?\s+(?i:and|&)\s+"
        rf"(?P<person2>{_NAME})\s*,?\s+(?i:as|to)\s+(?:(?i:join)\s+)?{_ART}"
        rf"(?P<role>{_ROLE_Q})")),
    ("appointed", re.compile(
        rf"\b(?i:{APPOINT}|appointments?\s+of|announces?|welcom(?:es|ed)\s+"
        rf"(?:the\s+addition\s+of\s+)?)\s+"
        rf"(?P<person>{_NAME})\s+(?i:and|&)\s+(?P<person2>{_NAME})\s*,?\s+"
        rf"(?i:as|to)\s+(?:(?i:join)\s+)?{_ART}(?P<role>{_ROLE_Q})")),

    # "... Appoints Duranya Sebabili Director and Country Manager"  (no "as").
    # The name is lazy so the shortest name that still leaves a role wins;
    # greedy matching made the person "Duranya Sebabili Director".
    ("appointed", re.compile(
        rf"\b(?P<verb>(?i:{APPOINT}))\s+(?P<person>{_NAME_LAZY})\s+(?P<role>(?i:{_ROLE}))\b")),

    # "... announces the resignation of Jane Smith as CFO"
    # v9: "Resignation of Director Kai Hoffmann" -- the title in front of the
    # name is the role (it used to be discarded as leading junk).
    ("departed", re.compile(
        rf"\b(?i:resignation|retirement|departure)\s+(?i:of)\s+"
        rf"(?:(?i:its\s+|the\s+|our\s+)?(?P<prole>(?i:{_ROLE}))\s*,?\s+)?(?P<person>{_NAME})"
        rf"(?:\s*,?\s+(?i:as|from)\s+{_ART}(?P<role>{_ROLE_Q}))?")),

    # "Jane Smith resigns as CFO"
    ("departed", re.compile(
        rf"(?P<person>{_NAME})\s+(?i:has\s+)?(?i:{DEPART})"
        rf"(?:\s*,?\s+(?i:as|from)\s+{_ART}(?P<role>{_ROLE_Q}))?")),

    # v9: a death is a departure. "BacTech Announces the Passing of Director Jay
    # Richardson", "Xtra-Gold Director James Schweitzer Passes Away". v7 tags
    # these Management Changes; the extractor had no word for them.
    ("departed", re.compile(
        rf"\b(?i:passing\s+of|loss\s+of|tribute\s+to\s+(?:its\s+|our\s+)?late)\s+"
        rf"(?:(?i:its\s+|the\s+|our\s+)?(?i:former\s+|long-?time\s+)?"
        rf"(?P<prole>(?i:(?:co-?)?founder|{_ROLE}))\s*,?\s+)?(?P<person>{_NAME})")),
    ("departed", re.compile(
        rf"(?P<person>{_NAME})\s+(?i:passes\s+away|has\s+passed\s+away|passed\s+away)")),

    # "Thompson Hickey Joins Canadian Copper's Board of Directors"
    # "Miguel Paucar Joins Lancaster Resources Advisory Board"
    # v9: "to Join" -- "Bam Bam Announces Yari Nieken to Join the Board of Directors"
    ("appointed", re.compile(
        rf"(?P<person>{_NAME})\s+(?i:joins|to\s+join)\s+(?:[^,]{{0,44}}?\s+)??"
        rf"(?P<role>(?i:{_ROLE}))\b")),

    # "Jane Smith has been appointed Chief Financial Officer"
    ("appointed", re.compile(
        rf"(?P<person>{_NAME})\s+(?i:has\s+been\s+|was\s+|is\s+)?"
        rf"(?i:appointed|named|promoted)\s+(?i:as\s+|to\s+)?"
        rf"{_ART}(?P<role>{_ROLE_Q})")),

    # v9: "Loyalist Announces Len Mackenzie as Vice-President Exploration",
    # "Integral Metals Announces the Addition of John David Clark as an Advisor",
    # "Supreme Announces Ron Shenton to Advisory Board". Last in the list so a
    # headline that also resigns or appoints someone keeps that as its top
    # change. "to" is accepted only in front of a board -- "Announces Stock
    # Option Grants to Directors" is not an appointment.
    ("appointed", re.compile(
        rf"\b(?i:(?:strategic\s+)?addition\s+of|announces?)\s+"
        rf"(?:(?i:mr\.|ms\.|mrs\.|dr\.)\s+)?(?P<person>{_NAME})\s*,?\s+"
        rf"(?:(?i:as)\s+{_ART}(?P<role>{_ROLE_Q})|"
        rf"(?i:to\s+(?:join\s+)?(?:the\s+|its\s+|the\s+company['’]s\s+)?)"
        rf"(?P<role2>(?i:(?:Scientific\s+|Technical\s+|Strategic\s+)?Advisory\s+"
        rf"(?:Board|Committee|Council)|Board(?:\s+of\s+(?:Directors|Advisors))?)))")),
]

# v9: a capitalised name straight after a title means the words BEFORE the
# title were an employer, not the appointee: "QIMC Appoints Enbridge Gaz Québec
# President Jean-Benoît Trahan to Board of Directors", "Goldera Appoints IAMGOLD
# Founding Director Mahendra Naik to its Board". The real person follows.
_AFTER_TITLE_NAME = re.compile(
    rf"\s*,?\s+(?:(?i:Dr|Mr|Ms|Mrs)\.?\s+)?(?P<person>{_NAME})"
    rf"(?:\s*,?\s+(?i:as|to)\s+{_ART}(?P<role>{_ROLE_Q}))?")

# the same, with no comma: "Joins U.S. President Donald J. Trump" -- but not
# "Joins Lancaster Resources Board of Directors, Bolstering Expertise"
_NAME_AFTER_ROLE = re.compile(rf"\s+(?:(?i:Dr|Mr|Ms|Mrs)\.?\s+)?(?P<person>{_NAME})")

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

# v9: "Appoints Former OPG CEO Ken Hartwick to its Board of Directors" -- the
# first title after the verb describes the person; where the headline also says
# where they are going, that destination is the role.
_DESTINATION = re.compile(
    r"\b(?i:to|joins?)\s+(?i:the\s+|its\s+|their\s+)?(?:[A-Z][\w'’\-]*\s+){0,2}?"
    r"(?P<role>(?i:Board\s+of\s+Directors|(?:Scientific\s+|Technical\s+|Strategic\s+)?"
    r"Advisory\s+(?:Board|Committee|Council)|Board\s+of\s+Advisors|Board))\b")

# v9: a departure with nobody named: "Announces Resignation of Non-Executive
# Director", "Announces the Passing of Director", "Announces Retirement of
# Chairman". _ROLE_THEN_VERB had only the noun-after-title order.
_ROLE_DEPART = re.compile(
    rf"\b(?i:resignations?\s+of|retirement\s+of|departure\s+of|passing\s+of|"
    rf"termination\s+of)\s+(?:(?i:its|the|a|an|our|former|long-?standing|"
    rf"two|one)\s+){{0,2}}(?P<role>{_ROLE_Q})\b")

# A reshuffle with nobody named: "Announces Changes to Board of Directors".
# Neither a joining nor a leaving. v3 folded these into the appointment verbs,
# which reported 23 board shuffles as appointments. _ROLE_ONLY is tried first,
# so "Changes To The Board - Appoints New Interim CEO" is still an appointment.
# v9: "Change of CFO", "Change in Board Leadership".
_ROLE_CHANGED = re.compile(
    rf"\b(?i:changes?\s+(?:to|of|in)|restructur(?:es|ed|ing))\s*"
    rf"(?:[A-Za-z'’\-]+\s+){{0,6}}?(?P<role>(?i:{_ROLE}))\b(?!['’]s)")
# ... the possessive guard is v9: "Change of Director's Interest Notice" (ASX
# Appendix 3Y) is a share-holding filing, and there are seven of them.

_BOARD_ROLE = re.compile(r"\b(?:board|director|chair)", re.I)
_ADVISORY_ROLE = re.compile(r"\badvis", re.I)
# "Alma Gold Inc. Announces Director Resignation" / "Appoints New Director" --
# a bare role with an appointment or departure verb beside it is a management
# change even with nobody named. Rejecting these cost 453 real releases.
# v9: a left boundary -- "Norsemont Announces Update on MCTO Application
# Material Change Report" was a CTO change. Also "Retirement", "Succession".
_ROLE_THEN_VERB = re.compile(
    rf"(?<![A-Za-z])(?P<role>(?i:{_ROLE}))\s+(?:[A-Za-z&]+\s+){{0,3}}?"
    rf"(?i:resignation|appointment|change|transition|departure|nomination|"
    rf"retirement|succession)s?\b")

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
    # v9: an advisory body and the qualifiers _ROLE_MOD lets into a title --
    # "Advisory Committee" was trimmed to "Advisory", "Permanent Full Time CEO"
    # to "Permanent"
    "committee", "council", "member", "members", "permanent", "full", "time",
    "full-time", "incoming", "industry", "inaugural", "independent", "co-ceo",
}
# A connector survives only when a title word follows it. "to" is absent on
# purpose: it let "VP of Exploration To Head Up Exploration at Bleasdell"
# through, because "Head" is a real title word and the connector skipped past
# the word that actually ended the title.
_TITLE_JOIN = {"of", "and", "&", "the", "its", "for", ",", "-"}


_RANK_WORDS = {
    "chief", "senior", "executive", "vice", "president", "vice-president",
    "non-executive", "deputy", "assistant", "interim", "acting", "lead",
    "managing", "general", "principal", "chair", "chairman", "chairwoman",
    "chairperson", "director", "directors", "officer", "manager", "head",
    "advisor", "adviser", "advisory", "board", "counsel", "secretary",
    "treasurer", "controller", "partner", "vp", "v.p.", "evp", "svp", "ceo",
    "cfo", "coo", "cto", "cio", "cso", "geologist",
}


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
        # v9: after a comma only a FUNCTION continues the title ("Vice
        # President, Exploration"); a rank starts a second role ("President,
        # CEO and Director") and the first role ends at the comma.
        if toks[i - 1].endswith(",") and (w in _RANK_WORDS or w not in _TITLE_WORDS):
            break
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
    # v9: "Robert Penczak QP", "Carlos Espinosa Officially Joins RooGold"
    "qp", "officially", "formally",
    # a dateline run into a headline: "Pays Tribute to Its Late Founder,
    # Richard Hughes Vancouver, British Columbia"
    "vancouver", "toronto", "calgary", "montreal", "perth",
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
    # v9: "Retired Federal Minister Seamus O'Regan", "Mining Innovator Michelle
    # Ash", "Executive Management Transition Mirco Wojnarowicz appointed"
    "federal", "provincial", "innovator", "pioneer", "transition", "founding",
    "member", "leadership", "reporting", "operator", "shareholder", "alumnus",
}

# v9: a token no person's name contains. The departure patterns read "Retirement
# of Certain Legacy Debt Obligations", "Retirement of Beedie Facility" and "Oil &
# Gas Geoscientists Depart Canada" as people; "Appoints Energy Leader as New
# CEO" made a person called ENERGY LEADER.
_NOT_NAME = {
    "debt", "debts", "obligations", "facility", "facilities", "loan", "loans",
    "notes", "debentures", "credit", "legacy", "certain", "geoscientists",
    "geologists", "leader", "leaders", "minister", "specialist", "strategist",
    "entrepreneur", "financier", "innovator", "veteran", "builder", "expert",
    "experts", "professor", "scientist", "emeritus", "founding", "officially",
    # verbs a capitalised headline puts right after a name: "Asa East Appointed
    # as", "Mark Reischman Joins as", "Mr. Roy Resigns as Director"
    "appointed", "appoints", "joins", "joined", "resigns", "resigned", "named",
    "retires", "retired", "promoted", "welcomes", "grants", "announces",
    "provides", "closes", "completes", "reports", "extends", "commences",
    # things a headline announces "to Directors" / "as" that are not people
    # ("Grant" and "Key" are left out: Grant Tanaka, Nicky Grant, Katy Grant)
    "option", "options", "grants", "stock", "shares", "rsus", "warrants",
    "units", "additions", "addition", "million", "equity", "financing",
    "listing", "geoscientist", "member", "members", "operator", "shareholder",
    "alumnus", "alumna",
    # a commodity company is not a person: "Cruz Cobalt Joins the Clayton
    # Valley Lithium Advisory Committee". Gold, Silver, Nickel and Copper are
    # left out -- "Steven Gold", "Jason Nickel" are real appointees.
    "cobalt", "lithium", "uranium", "graphite", "metals",
    "minerals", "resources", "mining", "energy", "royalties", "ventures",
    "explorations", "battery",
}


# words that end a description placed in front of a name: "Wall Street Veteran
# Michael Moen", "Xtra-Gold Director James Schweitzer"
_TAIL_MARKERS = _TITLE_WORDS | _DESCRIPTOR | {
    "veteran", "leader", "minister", "specialist", "strategist", "entrepreneur",
    "financier", "innovator", "builder", "geoscientist", "professor", "scientist",
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
    if any(t in _NOT_NAME for t in toks):
        return False
    if _COMPANY_TAIL.search(name):
        return False
    # "Canadian Copper's Board" -- a possessive is a company, not a person
    return not any(t.endswith("'s") or t.endswith("’s") for t in (name or "").split())


def _clean_role(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    s = re.sub(r"\s+(?i:and|&)\s+(?i:announces|provides|begins|commences|reports).*$", "", s)
    # v9: "Chief Psychedelic Officer" -- the word in the middle is whatever the
    # company calls it, and the title is complete as matched
    c = re.match(r"(?i:chief\s+[a-z]+(?:\s+[a-z]+)?\s+officer)\b", s)
    if c:
        return c.group(0)[:MAX_ROLE_CHARS]
    s = _trim_role_tail(s)
    return s.strip(" ,;–—-")[:MAX_ROLE_CHARS]


# v9: a director of a function is staff: "Project Director", "Director of
# Operations", "Executive Technical Director".
_STAFF_DIRECTOR = re.compile(
    r"\b(?:project|operations?|technical|exploration|sales|marketing|commercial|"
    r"finance|communications|mine|site)\s+director\b|\bdirector\s+of\b(?!\s+the\s+board)",
    re.I)


_RANK_LEAD = re.compile(r"(?i:vice|v\.?p|s\.?v\.?p|e\.?v\.?p|senior|executive|director|"
                        r"head|chief|manager)\b")


def _service_text(m, text: str) -> str:
    """The part of a match the service-provider test is judged on.

    v9: "Appoints Farid Mammadov as Vice President, Investor Relations" is an
    officer whose portfolio happens to be IR. When the captured title starts
    with a rank, the words inside the title are its function, not a hired firm,
    so only the text before the title is tested. "Engages X as Investor
    Relations Manager" still starts its title with "Investor" and is rejected.
    """
    try:
        rs = m.start("role")
        role = m.group("role") or ""
    except IndexError:  # a pattern with no role group
        return m.group(0)
    if rs >= 0 and _RANK_LEAD.match(role):
        return text[m.start():rs]
    return m.group(0)


def _scope(role: str) -> str:
    if _ADVISORY_ROLE.search(role or ""):
        return "advisory"
    if _STAFF_DIRECTOR.search(role or ""):
        return "management"
    if _BOARD_ROLE.search(role or ""):
        return "board"
    return "management"


# Diagnostics only (measure.py): when TRACE is a list, extract() appends the
# name of the rule that produced each change. Never part of the return value.
TRACE = None
_PATTERN_NAMES = ["as", "appointment_of", "to_board", "two_names_3", "two_names",
                  "no_as", "departure_of", "resigns", "passing_of", "passes_away",
                  "joins", "was_appointed", "announces_as"]


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

    def _add(action, raw_person, role, prole=""):
        if _PRIOR_AFFILIATION.match(raw_person or ""):
            # "Former Gold Fields", "Former Electronic Arts", "Former Las
            # Bambas" -- a previous employer, not the appointee.
            # v9: unless a title closes the description and a name follows it:
            # "FORMER SASKPOWER MINISTER ROB NORRIS JOINS MAX POWER BOARD".
            toks = raw_person.split()
            last = max((i for i, t in enumerate(toks)
                        if t.lower().strip(".,") in _LEADING_JUNK and i > 0), default=-1)
            if last < 1 or len(toks) - last - 1 < 2:
                return
            raw_person = " ".join(toks[last + 1:])
        person = _clean_person(raw_person)
        if person and not _is_person(person):
            # v9: "Xtra-Gold Director James Schweitzer Passes Away" -- the name
            # regex starts at the company. When a title word sits inside the
            # capture and a full name follows it, the name is what follows and
            # the title is its role.
            toks = person.split()
            last = max((i for i, t in enumerate(toks)
                        if t.lower().strip(".,") in _TAIL_MARKERS), default=-1)
            tail = " ".join(toks[last + 1:]) if last >= 0 else ""
            if tail and len(toks) - last - 1 >= 2 and _is_person(tail):
                prole = prole or toks[last]
                person = tail
            else:
                return
        if not person:
            return
        role = _clean_role(role or "")
        if not role and prole:
            # v9: "Resignation of Director Kai Hoffmann" -- the title in front
            # of the name is the only role the headline gives.
            role = _clean_role(prole)
        key = person.lower()
        if key in seen:
            return
        seen.add(key)
        changes.append({"action": action, "person": person,
                        "role": role or None, "scope": _scope(role)})

    for pi, (action, pat) in enumerate(_PATTERNS):
        for m in pat.finditer(text):
            n_before = len(changes)
            if _SERVICE_ROLE.search(_service_text(m, text)):
                # "engages X as market maker" and friends are not management
                # changes, however identical the grammar. Judged on the match,
                # not on the whole headline.
                continue
            g = m.groupdict()
            raw_person, role = g.get("person") or "", g.get("role") or g.get("role2") or ""
            verb = g.get("verb")
            nxt = _NAME_AFTER_ROLE.match(text, m.end("role")) if (
                _PATTERN_NAMES[pi] == "joins" and g.get("role")) else None
            if nxt and _is_person(_clean_person(nxt.group("person"))):
                # v9: "Robert Friedland Joins U.S. President Donald J. Trump at
                # the White House" -- the title belongs to the next name
                continue
            if verb is not None:
                # the no-"as" pattern: "Appoints NAME ROLE"
                if re.search(r"(?i:ed)$", verb) and re.search(
                        r"[A-Z][\w'’.\-]*\s*$", text[:m.start()]):
                    # v9: "John F. O'Donnell Appointed Montana Gold Chairman of
                    # the Board" -- a past-tense verb straight after a name is
                    # passive; what follows it is the company, not the person.
                    continue
                # where the TRIMMED title ends, not where the regex stopped:
                # "Appoints Martin Demers VP of Exploration and Completes Final
                # Closing" must not read "Completes Final Closing" as a name
                ntok = len(_clean_role(role).split())
                toks = list(re.finditer(r"\S+", role))
                end = m.start("role") + (toks[ntok - 1].end() if 0 < ntok <= len(toks) else len(role))
                after = _AFTER_TITLE_NAME.match(text, end)
                if after and _is_person(_clean_person(after.group("person"))):
                    # v9: "Appoints Enbridge Gaz Québec President Jean-Benoît
                    # Trahan to Board" -- the capture was an employer.
                    raw_person, role = after.group("person"), after.group("role") or ""
            _add(action, raw_person, role, g.get("prole") or "")
            if len(changes) > n_before:
                # only when the first name was a person: in "Appoints Proven
                # Mine Builder and Operator David Bernier" the "and" joins two
                # descriptions of one man, not two appointees
                for extra in ("person3", "person2"):
                    if g.get(extra):
                        _add(action, g[extra], role)
            if TRACE is not None:
                TRACE.extend([_PATTERN_NAMES[pi]] * (len(changes) - n_before))

    if not changes:
        for pat, action in ((_ROLE_ONLY, "appointed"),
                            (_ROLE_DEPART, "departed"),
                            (_ROLE_CHANGED, "changed"),
                            (_ROLE_THEN_VERB, None)):
            rule = {id(_ROLE_ONLY): "role_only", id(_ROLE_DEPART): "role_depart",
                    id(_ROLE_CHANGED): "role_changed", id(_ROLE_THEN_VERB): "role_then_verb"}[id(pat)]
            m = pat.search(text)
            if not m or _SERVICE_ROLE.search(_service_text(m, text)):
                continue
            role = _clean_role(m.group("role"))
            if not role or len(role) < 3:
                continue
            if action == "appointed" and (
                    re.search(r"(?i:\bformer\b)", m.group(0))
                    or re.search(r"(?i:geologist)$", role)):
                # v9: "Appoints Former OPG CEO Ken Hartwick to its Board of
                # Directors", "Appoints Veteran Geologist X to the Board" -- a
                # former title or a profession describes the person; where the
                # headline names a destination, that is the role. Only then:
                # "Appointment of CEO and Changes to Board" keeps CEO.
                d = _DESTINATION.search(text, m.end())
                if d and not _BOARD_ROLE.search(role) and not _ADVISORY_ROLE.search(role):
                    role = _clean_role(d.group("role"))
            if action:
                act = action
            elif re.search(r"(?i:resignation|departure|retirement)", m.group(0)):
                act = "departed"
            elif re.search(r"(?i:changes?|transition|succession)", m.group(0)):
                act = "changed"
            else:
                act = "appointed"
            changes.append({"action": act, "person": None,
                            "role": role, "scope": _scope(role)})
            if TRACE is not None:
                TRACE.append(rule)
            break

    if not changes:
        return {"changes": []}
    top = changes[0]
    return {"changes": changes, "top_person": top["person"],
            "top_role": top["role"], "top_action": top["action"],
            "top_scope": top["scope"]}


# ---------------------------------------------------------------------------
# v9: rows for releases the categoriser tagged but extract() cannot parse
# ---------------------------------------------------------------------------
# The Management Changes chip is built by the categoriser, which accepts a
# leadership headline that names nobody and no parseable role ("Announces
# Leadership Transition", "Strengthens Board", "Announces Passing of Mark
# Gasson"). The page is built from extract(). infer_from_tag() lets the page
# follow the tag: for a TAGGED release it returns a person-less change with the
# action and scope read from the headline's words -- and returns None when the
# headline carries no management evidence at all, because then the tag itself
# is wrong ("News release", "Board Approval of 2026 Budget").

_INF_SUBJECT = re.compile(
    rf"(?i:\b(?:{_ROLE}|officers?|executives?|leadership|leaders|management|team|"
    rf"(?:co-?)?founder|board\s+members?|advis[oe]rs|nominees?|managers?|BOD|"
    rf"organizational|(?:technical|advisory|geological)\s+commit+ee|C[EFOT]O|SVP|EVP)\b)")
_INF_DEPART = re.compile(
    # "retired" is left out: "Appoints Retired U.S. Army Colonel" is an adjective
    r"(?i:\b(?:resign\w*|retire|retires|retirements?|retiring|steps?\s+down|"
    r"stepping\s+down|stepped\s+down|"
    r"depart\w*|passing|passes\s+away|passed\s+away|mourns?|tribute|late|"
    # a termination is a departure only next to a title: "CEO TERMINATION",
    # not "Management Changes and Termination of RSU Plan"
    r"(?:C[EFOT]O|officer|director|president|chair\w*)\s+terminat\w*|"
    r"terminates\s+(?:[A-Z][\w'’\-]*\s+){1,3}as|"
    r"terminat\w*\s+of\s+(?:the\s+|its\s+)?(?:C[EFOT]O|officer|director|president|chair\w*)|"
    r"loss\s+of)\b)")
_INF_CHANGE = re.compile(
    r"(?i:\b(?:changes?|transitions?|succession|updates?|restructur\w*|renewal|"
    r"refresh\w*|evolution|reorganiz\w*|reshuffle)\b)")
_INF_APPOINT = re.compile(
    r"(?i:\b(?:appoint\w*|names?|named|welcom\w*|joins?|joining|adds?|added|"
    r"additions?|new|strengthen\w*|bolster\w*|expan\w*|builds?\s+out|enhanc\w*|"
    r"forms?|formation|establish\w*|creat\w*|hires?|elect\w*|nominat\w*|"
    r"promot\w*|engages?|commences\s+role|assumes|agrees\s+to\s+(?:act|serve|join)|"
    r"streamlin\w*|moves\s+to|attracts|nominees?)\b)")
# "RAIN CITY ANNOUNCES INTERIM CEO", "Steadright Announces Board Chair",
# "FORTY PILLARS ANNOUNCES REYNOLDS AS DIRECTOR" -- "announces" is only an
# appointment when the title closes the clause; "Announces CEO Controlled
# Entity Debt Acquisition" is not one.
_INF_ANNOUNCES = re.compile(
    rf"\b(?i:announces?)\s+(?:(?i:(?:the\s+)?(?:new|interim|acting))\s+)?"
    rf"(?:[A-Z][\w'’\-]*\s+(?:(?i:as)\s+)?){{0,3}}?(?i:{_ROLE})"
    rf"(?=\s*$|\s*[,;.(]|\s+(?i:and)\b)")
# Tagged releases that are not a change in who runs the company. Each is a
# bucket read in the corpus (see FINDINGS.md), not a guess.
_INF_NOT = re.compile(
    r"(?i:\bboard\s+approv\w*|\bapproved\s+by\s+(?:the\s+)?board|"
    r"\bexpert\s+panel\b|\bcourt[\-\s]appointed\b|\bexecutive\s+order\b|"
    r"\bsite\s+visit\b|\bmanagement\s+cease\s+trade|\bMCTO\b|"
    r"\bmanagement['’]?s\s+discussion|\bmanagement\s+information\s+circular\b|"
    r"\bdirector['’]s\s+interest\b|\bPDMR\b|\bPMDR\b|\bdealing\b)")


def infer_from_tag(headline: str) -> dict | None:
    """A person-less change for a release tagged Management Changes, or None.

    Never used as a detector: an untagged release is not rescued by this.
    """
    h = _CRED_RE.sub("", (headline or "").strip())
    if not h or _INF_NOT.search(h) or _SERVICE_ROLE.search(h):
        return None
    subj = _INF_SUBJECT.search(h)
    dep, chg = _INF_DEPART.search(h), _INF_CHANGE.search(h)
    app = _INF_APPOINT.search(h) or _INF_ANNOUNCES.search(h)
    # a death or a resignation names a person and often no role: "Announces
    # Passing of Mark Gasson", "ROCKLAND RESOURCES SUTCLIFFE RESIGNS",
    # "Announces the Resignations of David Drinkwater and Stephen Lewin"
    death = re.search(r"(?i:\bpassing\s+of|passes\s+away|passed\s+away|mourns?|"
                      r"tribute\s+to)", h)
    resign = re.search(r"(?i:\bresigns\b|\bresignations?\s+of\s+(?:mr\.?\s+|ms\.?\s+)?[A-Z])", h)
    if not (dep or chg or app) or not (subj or death or resign):
        return None
    if dep and app and not death:
        action = "changed"        # "Resignation and Appointment of Directors"
    elif dep:                     # "Corporate Update - Alford resigns"
        action = "departed"
    elif chg:
        action = "changed"
    else:
        action = "appointed"
    role = None
    d = _DESTINATION.search(h)
    if d:
        role = _clean_role(d.group("role"))
    else:
        for rm in re.finditer(rf"(?<![A-Za-z])(?P<role>(?i:{_ROLE}))\b", h):
            # "Appoints Former U.S. Secretary of Homeland Security ... as a
            # Director" -- a title after "former" is the person's past
            if re.search(r"(?i:\bformer\b(?:\s+\S+){0,3}\s*)$", h[:rm.start()]):
                continue
            role = _clean_role(rm.group("role"))
            break
    if role and len(role) < 3:
        role = None
    low = h.lower()
    if role:
        scope = _scope(role)
    elif re.search(r"\badvis", low):
        scope = "advisory"
    elif re.search(r"\b(?:board|director|chair)", low):
        scope = "board"
    else:
        scope = "management"
    return {"action": action, "person": None, "role": role, "scope": scope}


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


# --- v9: every case below was found by reading all 2,068 v8 rows and the 1,020
# --- tagged releases v8 was silent on. (headline, person, role, action, scope)
# --- role is compared EXACTLY (None = no role); person None = nobody named.
V9_TEST = [
    # a former employer's title in front of the name, not fatal any more
    ("<br>FORMER SASKPOWER MINISTER ROB NORRIS JOINS MAX POWER BOARD OF DIRECTORS",
     "ROB NORRIS", "BOARD OF DIRECTORS", "appointed", "board"),
    ("Denison Announces Appointment of Former OPG CEO Ken Hartwick to its Board of "
     "Directors", "Ken Hartwick", "Board of Directors", "appointed", "board"),
    # an employer with no "former": the name after the title is the person
    ("QIMC Appoints Enbridge Gaz Québec President Jean-Benoît Trahan to Board of "
     "Directors", "Jean-Benoît Trahan", "Board of Directors", "appointed", "board"),
    ("Goldera Appoints IAMGOLD Founding Director Mahendra Naik to its Board of "
     "Directors Veteran mining executive and investor", "Mahendra Naik",
     "Board of Directors", "appointed", "board"),
    ("Wall Street Veteran Michael Moen Joins Carmanah Board Of Directors",
     "Michael Moen", "Board Of Directors", "appointed", "board"),
    # passive verb: the words after it are the company
    ("John F. O’Donnell Appointed Montana Gold Chairman of the Board", None,
     "Chairman of the Board", "appointed", "board"),
    # a description is not a name
    ("<br>MAX POWER APPOINTS ENERGY LEADER AS NEW CEO TO DRIVE NEXT PHASE OF "
     "NATURAL HYDROGEN GROWTH", None, "CEO", "appointed", "management"),
    ("Great Eagle Gold Corp. Appoints Mining Innovator Michelle Ash as a Director "
     "and Chairwoman of the Board", "Michelle Ash", "Director", "appointed", "board"),
    ("Carlos Espinosa Officially Joins RooGold as Chief Executive Officer",
     "Carlos Espinosa", "Chief Executive Officer", "appointed", "management"),
    ("Power Metallic Appoints Retired Federal Minister Seamus O'Regan to Board",
     "Seamus O'Regan", "Board", "appointed", "board"),
    # surnames that are also words the name filter knows
    ("Interra Copper Corp. Appoints Mr. Jason Nickel, P.Eng., as Chief Executive "
     "Officer & Extends Drill Program", "Jason Nickel", "Chief Executive Officer",
     "appointed", "management"),
    ("Corcel Exploration Appoints Grant Tanaka as Chief Financial Officer",
     "Grant Tanaka", "Chief Financial Officer", "appointed", "management"),
    ("Carolina Rush Appoints Patrick Quigley Vice President of Exploration, Grants "
     "RSUs and Options, Extends Warrants", "Patrick Quigley",
     "Vice President of Exploration", "appointed", "management"),
    # a title continues past a comma only with a function
    ("Athena Gold Appoints Farid Mammadov as Vice President, Investor Relations",
     "Farid Mammadov", "Vice President, Investor Relations", "appointed", "management"),
    ("Canamera Energy Metals Appoints Warren Robb as Vice President, Exploration",
     "Warren Robb", "Vice President, Exploration", "appointed", "management"),
    ("SIXTY NORTH GOLD APPOINTS GAVIN KIRK AS PRESIDENT, CEO AND A DIRECTOR",
     "GAVIN KIRK", "PRESIDENT", "appointed", "management"),
    ("Sanu Gold Appoints Constant Tia as Non-Executive Director", "Constant Tia",
     "Non-Executive Director", "appointed", "board"),
    ("Yukon Metals Appoints Jim Coates as Permanent Full Time CEO", "Jim Coates",
     "Permanent Full Time CEO", "appointed", "management"),
    ("NeonMind Appoints Trevor Millar as Chief Psychedelic Officer", "Trevor Millar",
     "Chief Psychedelic Officer", "appointed", "management"),
    # scope: a director of a function is staff; a board's advisor is advisory
    ("Avalon Advanced Materials Appoints Glen Smith as Project Director for Lake "
     "Superior Lithium Refinery Feasibility & Construction", "Glen Smith",
     "Project Director", "appointed", "management"),
    ("Canadian Goldfields Appoints Harp Gosal as Director of Capital Markets and "
     "Communications", "Harp Gosal", "Director of Capital Markets and Communications",
     "appointed", "management"),
    ("Hi-View Appoints Terry Krepiakevich as Board Advisor", "Terry Krepiakevich",
     "Board Advisor", "appointed", "advisory"),
    ("Gold Strike Resources Corp. Appoints Jim Gowans as Chairman of Advisory Board",
     "Jim Gowans", "Chairman of Advisory Board", "appointed", "advisory"),
    ("Abitibi Metals Announces Appointment of Victor Cantore to Advisory Committee",
     "Victor Cantore", "Advisory Committee", "appointed", "advisory"),
    # departures: the title before the name, "as a", and deaths
    ("LABRADOR GOLD ANNOUNCES RESIGNATION OF DIRECTOR KAI HOFFMANN", "KAI HOFFMANN",
     "DIRECTOR", "departed", "board"),
    ("SILVER MOUNTAIN ANNOUNCES RESIGNATION OF JULIO ARCE AS A DIRECTOR",
     "JULIO ARCE", "DIRECTOR", "departed", "board"),
    ("BacTech Announces the Passing of Director Jay Richardson", "Jay Richardson",
     "Director", "departed", "board"),
    ("Xtra-Gold Director James Schweitzer Passes Away", "James Schweitzer", "Director",
     "departed", "board"),
    # the capture started at the company; the title inside it is the role
    ("<br>MAX Power Director Thomas Clarke Resigns", "Thomas Clarke", "Director",
     "departed", "board"),
    ("Royal Road Minerals Announces Resignation of Non-Executive Director", None,
     "Non-Executive Director", "departed", "board"),
    ("Fuerte Metals Announces CFO Retirement", None, "CFO", "departed", "management"),
    ("Hertz Energy Announces Change of Chief Financial Officer", None,
     "Chief Financial Officer", "changed", "management"),
    # new verbs
    ("Loyalist Announces Len Mackenzie as Vice-President Exploration",
     "Len Mackenzie", "Vice-President Exploration", "appointed", "management"),
    ("Bam Bam Announces Yari Nieken to Join the Board of Directors", "Yari Nieken",
     "Board of Directors", "appointed", "board"),
    ("Crestview Exploration Inc. Announces Brian Brewer to Join Advisory Board",
     "Brian Brewer", "Advisory Board", "appointed", "advisory"),
    ("Vincent Chen Joins Lancaster Resources Board of Directors, Bolstering Expertise "
     "in Corporate Development", "Vincent Chen", "Board of Directors", "appointed",
     "board"),
    # a destination beats a profession or a former title -- but not "Changes to"
    ("Noble Plains Uranium Appoints Veteran Uranium Geologist Chris Healey to Board "
     "of Directors", "Chris Healey", "Board of Directors", "appointed", "board"),
    ("Tintina Announces Appointment of CEO and Changes to Board of Directors", None,
     "CEO", "appointed", "management"),
]

# two or three people named for one role
N_CHANGES_TEST = [
    ("Blackrock Silver Announces the Appointment of Bernard Poznanski and Susan "
     "Mathieu to the Board of Directors", ["Bernard Poznanski", "Susan Mathieu"]),
    ("Fuerte Welcomes Chris Beer, Dawson Proudfoot and Sandip Rana to Its Board of "
     "Directors", ["Chris Beer", "Dawson Proudfoot", "Sandip Rana"]),
    # "and" joining two descriptions of one man is not two people
    ("Abitibi Metals Appoints Proven Mine Builder and Operator David Bernier as Chief "
     "Operating Officer", []),
]

V9_REJECT_TEST = [
    # a departure verb whose object is a loan, not a person
    "i-80 Gold Closes $250 Million Royalty Financing with Franco-Nevada and Completes "
    "Retirement of Certain Legacy Debt Obligations",
    "METALLA ANNOUNCES REVOLVING CREDIT FACILITY OF UP TO $75 MILLION AND RETIREMENT "
    "OF BEEDIE FACILITY",
    "ANGKOR RESOURCES’ OIL & GAS GEOSCIENTISTS DEPART CANADA TO PHNOM PENH TO DEVELOP "
    "ENERCAM’S ONSHORE OIL AND GAS PROJECT, CAMBODIA",
    # CTO inside MCTO
    "Norsemont Mining Inc. Announces Update on MCTO Application Material Change Report",
    # banks and IR shops hired as advisors
    "McEwen Copper Appoints Societe Generale as Financial Advisor for Project Debt "
    "Financing of Los Azules",
    "Avalon Advanced Materials Appoints SCP Resource Finance as Strategic Capital "
    "Advisor for Rare Earth and Lithium Projects",
    "LEADING EDGE MATERIALS ANNOUNCES CHANGE OF SWEDISH CERTIFIED ADVISER TO SVENSK "
    "KAPITALMARKADSGRANSKNING",
    # ASX Appendix 3Y share-holding notice
    "Change of Director’s Interest Notice + See chapter 19 for defined terms.",
    # options granted to directors are not directors appointed
    "Silver Sands Announces Stock Option Grants to Directors and Consultants",
    # joining a person, not a board
    "Ivanhoe Electric Executive Chairman Robert Friedland Joins U.S. President Donald "
    "J. Trump at the White House for Minerals Stockpile Announcement",
]

# (headline, action or None) -- infer_from_tag() on real tagged releases that
# extract() cannot parse. None means the TAG is wrong and no row is written.
INFER_TEST = [
    ("Cascada Announces Senior Leadership Changes", "changed"),
    ("B2Gold Announces Leadership Transition", "changed"),
    ("TEMAS STRENGTHENS BOARD TO SUPPORT GROWTH STRATEGY AND CRITICAL MINERALS "
     "ADVANCEMENT", "appointed"),
    ("Arizona Gold & Silver Continues to Strengthen Advisory Board", "appointed"),
    ("ROCKLAND RESOURCES SUTCLIFFE RESIGNS", "departed"),
    ("Don Whalen - BacTech Mourns the passing", "departed"),
    ("RAIN CITY ANNOUNCES INTERIM CEO", "appointed"),
    ("Corporate Update - Alford resigns", "departed"),
    ("GOLD’N FUTURES ANNOUNCES CEO TERMINATION", "departed"),
    ("CREST ANNOUNCES MANAGEMENT CHANGES AND TERMINATION OF RSU PLAN", "changed"),
    ("MONTEGO - Terminates Cegielski as CEO", "departed"),
    ("BLACK TUSK RESOURCES INC. CREATES GEOLOGICAL ADVISORY COMMITEE", "appointed"),
    ("NovaRed Mining Appoints Retired U.S. Army Colonel Mark A. Calabrese to Advisory "
     "Board", "appointed"),
    ("News release", None),
    ("Gold Reserve Announces Board Approval of Spin-Out Transactions", None),
    ("FREEMAN APPOINTS AUSENCO TO LEAD LEHMI GOLD PROJECT FEASIBILITY STUDY", None),
    ("Marimaca Appoints Stantec to Progress PEA for the Integration of the Pampa "
     "Medina Project", None),
    ("Talent Infinity Announces CEO Controlled Entity Debt Acquisition and Plans for "
     "Consolidation", None),
    ("Thor Explorations Ltd: Announces Director & PMDR Dealing", None),
    ("Military Metals Appoints DGWA as European Financial Markets Advisor", None),
]


def self_test_v9(verbose: bool = True) -> int:
    bad = 0
    for hl, want_p, want_r, want_a, want_s in V9_TEST:
        out = extract(hl)
        got = (out.get("top_person"), out.get("top_role"), out.get("top_action"),
               out.get("top_scope"))
        ok = got == (want_p, want_r, want_a, want_s)
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  v9 {str(got)[:90]}"
                  f"{'' if ok else chr(10) + '        WANTED ' + str((want_p, want_r, want_a, want_s))}")
    for hl, want in N_CHANGES_TEST:
        got = [c["person"] for c in extract(hl).get("changes", []) if c["person"]]
        ok = got == want
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  people {got}")
    for hl in V9_REJECT_TEST:
        ok = not extract(hl).get("changes")
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  reject {hl[:60]!r}")
    for hl, want in INFER_TEST:
        y = infer_from_tag(hl)
        got = y["action"] if y else None
        ok = got == want and not extract(hl).get("changes") if want is not None else got is None
        bad += not ok
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  infer {got!s:<9} {hl[:52]!r}")
    total = len(V9_TEST) + len(N_CHANGES_TEST) + len(V9_REJECT_TEST) + len(INFER_TEST)
    if verbose:
        print(f"\nv9: {total - bad}/{total} passed")
    return 1 if bad else 0


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
    sys.exit(self_test() | self_test_v9())
