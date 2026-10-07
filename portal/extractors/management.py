"""Management changes extractor, facts-store version (MGMT_V1). Phase 2b #4 of the revised plan.

Replaces management_extract.py v9 + management_backfill.py as the source of /management-changes once it
passes the accuracy gate. The measured baseline for v9 (2026-09-17, 50-release set confirmed by Justin):

  detection     43 right, 1 wrong, 3 missed of 50          -- the tag is fine
  people        29 of 79 named, 38.7% recall               -- the real defect
  role exact    30 of 42, and written six ways on the page
  scope         39 of 43        action 39 of 43

and across the whole table, 1,859 of 3,030 rows named nobody at all, 666 were inferred from a headline
phrase with nothing behind them, and every release produced exactly one row, so 52 announced changes sat
invisible inside a JSON column.

What this reader does differently:

  1. ONE RECORD PER PERSON. A release that appoints three people is three records (Justin, 2026-09-17:
     one row per person on the page), so nothing is hidden behind the first name.
  2. VERB-ANCHORED, NOT NAME-ANCHORED. A change is built from an action verb ("appoints", "has resigned"),
     then the person and the role are read out of that verb's own clause. Reading from names instead is
     what put quoted executives and prior employers on the page: "said John Smith, CEO" states a role but
     announces nothing, and "appoints former Barrick chief geologist Dr. X" is one appointment, not two.
  3. ROLES COME FROM A VOCABULARY (portal/extractors/mgmt_roles.py), never from "the next few words", and
     each carries its canonical spelling and its scope. A bare Director is a board seat; a Director of
     Capital Markets is an officer.
  4. NO EMPTY ROWS. A change needs a person or a role; a release that only says the team was strengthened
     produces no record, and the release is still tagged, just not shown.

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per change (ordinal 0..n-1)
to_prediction(records) -> dict|None    what the accuracy judge compares

1.1.1 (2026-09-30, ACC150 blind audit + outside-tag samples). The kinds of error fixed, in the order they cost:

  5. THINGS READ AS PEOPLE. Headings, deal and table words ("Resulting Issuer", "Option Agreement", "Sets Date",
     "Selected Drill"), company names (a ticker word, a foreign company form such as S.A., the organisation after
     "join"/"from"), places and nationalities are refused; so is a "name" whose first word the release uses as an
     ordinary lower-case word, or that only ever follows "a", "an" or "the".
  6. ACTION WORDS THAT ANNOUNCE NOTHING claim the names beside them and change nobody: the noun "name", a
     "strengthened" balance sheet, "join CEO X for a webinar", '," added Mr. X', biography ("Prior to joining",
     "joined Haywood in 2003", "is a retired executive"), board committees, an AGM electing its slate or re-appointing
     its officers, a lender's right to nominate, a requisitioned resolution, an appointment to an outside council,
     a firm engaged or someone appointed to do a piece of work, "its recently-appointed Chair", "In addition to".
  7. SPEAKERS AND ANNOUNCERS: more speech verbs, attributions broken by a PDF line, and "X and Y announce today".
  8. ROLES THAT BELONG TO SOMEONE ELSE: a title held at another company, a title between the name and the action
     word (the one already held), and a title after someone else's name ("..., with Mr. Anderson appointed as
     Chairman") are not given out; "President, CEO and Director" is two rows, "SVP, General Counsel and Corporate
     Secretary" one.
  9. MISSED PEOPLE AND DEPARTURES: "Mr. Surname" after a full mention, "Ing." and middle initials, split surnames,
     "replacing the Company's CFO, Robert Suttie", "thanks former CEO X", the office a named successor fills,
     "stepping down", memorials, "appointment of two directors. Mr. A ... Mr. B ...".
 10. INTERNAL MOVES: an officer who already holds a post and takes another is "changed" ("promoted" when senior).
     Key gate (reviewed answer key): an officer who also takes on Corporate Secretary or Treasurer keeps the old
     post and is "appointed"; a title met in biography ("In his role as CEO and President, Mr. X was ...") is not a
     post held here; an interim post is its own office in a list; "the appointment of a new director" that is still
     being sought ("identifying and evaluating alternatives") names no one.

 11. FULL-TEXT LOSSES (FIX3, 2026-10-01; the production texts, where 1.1.1 dropped rows the live reader showed).
     Names: initials first ("J.P. Dau"), "des"/"dos" particles, a place or word as a name after Mr./Ms. or before the
     person's title ("Ms. Victoria Vargas", "Jeremy South, Chief Financial Officer"), "retirement from X", a title
     printed in front of a name ("Secretary of Homeland Security Kirstjen Nielsen"), a given name split by the PDF and
     confirmed by "Mr. Surname", "Exploration Manager" after a name, letter-spaced text, accent apostrophes, a given name
     alone beside "join"/"welcome" ("have Boen join our Technical Advisory Committee").
     Changes no longer discarded: joining a board next to a conference, "who was appointed ... today", one person
     elected at a meeting, a release's own "has announced his retirement", "was not re-elected" (a departure),
     advisory and project management committees, "the role will be assumed by X", "board extended to include X",
     a stock option plan approved in the paragraph before, "elevated" as an adjective (no longer a promotion).
     Rows: the title next to the name in a long lead, the seat after the action when every earlier title is an aside,
     a board seat as the action's own object with no readable name ("JOINS BOARD OF DIRECTORS", "passing of Board
     member X"; not "the appointment of the Board", a vacancy or a board "strengthened"), bulleted lists after a
     colon, a headline post given to the one person the body welcomes, names that are the subject of their own verb,
     a bracketed post not shared down a list, a signature's title line not read as a post already held.

 12. FIX5 (2026-10-04, ACC150c dev half). Dates: a change "effective immediately" / "with immediate effect" / "as of
     today's date" takes the date of the release it is in (the dateline; on a page of several releases, the wire dateline
     before the change; none when the dateline's year is behind the text's own "upcoming" year). People: a second post
     in one sentence ("President and CEO as well as Director", "as CEO and as a director", "CEO ("CEO") and a Director",
     "..., and has been appointed as CEO"); departures told indirectly ("will not be seeking / running for re-election",
     "did not stand for re-" across a line, "thanks X, our previous CFO"). Not people or not changes: a meeting's vote
     tally lines and the board elected "for the ensuing year", a change the release only recaps ("As previously announced
     on ...", "Earlier this year"), a sentence-opening "If", vote-table, fund and headline industry words, a town before
     its province, two announcers before "are pleased to announce", the press contact, a retirement elsewhere dated to a
     past month and year, one given name spelled two ways, a short name two different longer names fit.

Self-tests: python3 -m portal.extractors.management
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from portal import facts as F
from portal.extractors import mgmt_roles as R

NAME = "management"
VERSION = "1.1.2"  # 2026-09-30: ACC150 fix: things read as people, firms, quoted speakers, AGM slates, missed departures; 2026-10-01: names, seats and lists the full text hides; full-text losses fixed; 2026-10-04 FIX5: effective-now dates from the dateline, second posts and indirect departures, vote tallies, recaps, fragments and announcers not read as people
KIND = "management_change"
TAG = "Management Changes"
TEXT_CAP = 9000

ACTIONS = ("appointed", "departed", "changed", "other")


# ------------------------------------------------------------------ text
_WS = re.compile("[ \\t\\xa0\\u2000-\\u200b\\u202f\\u205f\\u3000]+")


def clean(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "").replace("\r\n", "\n").replace("\r", " ")   # 1.1.1: "Mr. \r Alexander"
    for dash in (0x2010, 0x2011, 0x2012, 0x2013, 0x2212):
        t = t.replace(chr(dash), "-")
    t = t.replace(chr(0x2014), " - ").replace(chr(0xad), "")
    t = t.replace(chr(0x2018), "'").replace(chr(0x2019), "'")
    t = t.replace(chr(0x201c), '"').replace(chr(0x201d), '"')
    t = _WS.sub(" ", t)
    # a release lifted out of a PDF wraps mid-sentence, so a single line break is not a sentence break;
    # two or more are a paragraph, and only that is treated as the end of one.
    t = re.sub(r"[ ]*\n[ ]*\n[\s\n]*", "\n\n", t)
    t = re.sub(r"(?<!\n)[ ]*\n[ ]*(?!\n)", "\n", t)
    t = re.sub(r"(?<=[a-z,])\n\n(?=[a-z])", " ", t)            # 1.1.1: a PDF that double-spaces every line
    t = re.sub(r"(\b[A-Z][a-z]{2,15} )([A-Z])[ ]([a-z]{3,}[\w'\-]*)", r"\1\2\3", t)
    t = re.sub(r"(\b[A-Z][a-z']{2,15})[ ](?!a\b|i\b|o\b)([a-z])(?![\w'\-])", r"\1\2", t)
    t = re.sub(r"\b([Rr]e) (sign(?:s|ed|ing|ation|ations)?)\b", r"\1\2", t)   # 1.1.1: "is re signing from the Board"
    if "e -" in t or "e- " in t:                              # FIX3: "was not re -elected", "re- election"
        t = re.sub(r"\b([Rr]e) ?- ?((?:elect|appoint|nominat)\w*)", r"\1-\2", t)
    if _RE_SPACED_ANY.search(t):                              # FIX3: "were a p p o i n t e d t o t h e b o a r d"
        t = _RE_SPACED.sub(_unspace, t)
    if "\u00b4" in t or "\u0301" in t:                        # FIX3: a PDF's acute-accent apostrophe ("Company \u0301s")
        t = re.sub("(?<=[A-Za-z]) ?[\u00b4\u0301](?=s\\b)", "'", t)
    # 1.1.1: "Higson -Smith", "Higson- Smith", "Higson-\nSmith": one hyphenated surname split by the PDF
    t = re.sub("(?<=[a-z\u00e0-\u00ff])(?: -|- |-\n)(?=[A-Z][a-z])", "-", t)
    # 1.1.1: "Sarah Morri son", "Mr. Paul Ank corn": a name broken in two is joined when the release prints the
    # whole word elsewhere ("Ms. Morrison", "Mr. Ankcorn")
    caps = set(re.findall(r"\b[A-Z][a-z]{3,}\b", t))
    if caps:
        t = _RE_SPLIT_NAME.sub(lambda m: m.group(1) + m.group(2) if m.group(1) + m.group(2) in caps else m.group(0), t)
    # FIX3: "Ba rry Girling", "Mr. A ndrew Cook": a given name broken after its first letters, read as one when the
    # release names the same person as "Mr. Girling" / "Mr. Cook"
    titled = set(re.findall(r"\b(?:Mr|Ms|Mrs|Dr)\.?[ \n]+([A-Z][a-z]{2,})\b(?![ \n]+[A-Z][a-z])", t))
    if titled:
        t = _RE_SPLIT_GIVEN.sub(lambda m: m.group(1) + m.group(2) + m.group(3)
                                if m.group(4) in titled and m.group(2) not in _SHORT_WORDS else m.group(0), t)
    return t


# FIX3: a PDF that prints a stretch letter by letter ("a p p o i n t e d t o t h e b o a r d o f d i r e c t o r s"). The
# letters are read back as words when the whole stretch splits into words of a small board-and-office vocabulary;
# otherwise the text is left as it is.
_RE_SPACED = re.compile(r"(?<![A-Za-z])(?:[A-Za-z] ){6,}[A-Za-z](?![A-Za-z])")
_RE_SPACED_ANY = re.compile(r"[A-Za-z] [A-Za-z] [A-Za-z] [A-Za-z] [A-Za-z] [A-Za-z] [A-Za-z]")   # a quick test first
_SPACED_WORDS = {"a", "an", "and", "as", "at", "be", "been", "board", "by", "chair", "chairman", "chief", "company",
                 "corporation", "director", "directors", "effective", "elected", "executive", "financial", "has", "have",
                 "his", "her", "in", "is", "its", "new", "of", "officer", "on", "operating", "president", "resigned",
                 "retired", "the", "to", "was", "were", "will", "with", "appointed", "appointment", "member", "members",
                 "committee", "audit", "vice", "secretary", "corporate", "advisory", "named", "joined", "immediately"}


def _unspace(m):
    letters = m.group(0).replace(" ", "")
    low = letters.lower()
    best = [None] * (len(low) + 1)
    best[0] = []
    for i in range(len(low)):
        if best[i] is None:
            continue
        for j in range(i + 1, min(len(low), i + 12) + 1):
            if low[i:j] in _SPACED_WORDS and (best[j] is None or len(best[j]) > len(best[i]) + 1):
                best[j] = best[i] + [(i, j)]
    if best[-1] is None:
        return m.group(0)
    return " ".join(letters[i:j] for i, j in best[-1])


_RE_SPLIT_NAME = re.compile(r"\b([A-Z][a-z]{2,12})[ ]([a-z]{2,6})\b")
_SHORT_WORDS = {"new", "and", "the", "non", "key", "top", "few", "all", "one", "two", "for", "our", "its", "his", "her",
                "with", "from", "into", "only", "also", "very", "more", "most", "lead", "past", "next", "last", "full", "sole"}
_RE_SPLIT_GIVEN = re.compile(r"\b([A-Z][a-z]?)[ ]([a-z]{2,6})(\b[ ]+)(?=([A-Z][a-z]{2,})\b)")   # FIX3


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


_RE_TAIL = re.compile(
    r"(?i)(?:neither\s+(?:the\s+)?(?:tsx|canadian\s+securities\s+exchange|cse)\b"
    r"|this\s+news\s+release\s+(?:does\s+not|shall\s+not)"
    r"|\bfor\s+(?:further|more)\s+information\s*,?\s*(?:please\s+)?(?:contact|visit)"
    r"|\babout\s+(?:the\s+company|[A-Z][\w&.\-]+(?:\s+[A-Z][\w&.\-]+){0,4})\s*[\n:])")
# a quarterly-results release states its forward-looking caution in the opening paragraph, so that
# marker only ends the news once the release is under way (Centerra, 2025-10-28: the board-chair
# transition sat 6,000 characters below a caution printed at character 300).
_RE_TAIL_LATE = re.compile(
    r"(?i)(?:forward[\-\s]looking\s+(?:statements?|information)\b"
    r"|cautionary\s+(?:note|statement)s?\b"
    r"|this\s+news\s+release\s+contains\s+forward)")


def news_window(body: str, cap: int = 8000) -> str:
    """The part of the release that is news: above the disclaimers and the About section."""
    b = (body or "")[:TEXT_CAP]
    m = _RE_TAIL.search(b, 200)
    if m:
        b = b[:m.start()]
    m = _RE_TAIL_LATE.search(b, 1500)
    if m:
        b = b[:m.start()]
    return b[:cap]


# ------------------------------------------------------------------ people
_PARTICLE = r"(?:van|von|de|des|del|della|di|da|das|dos|du|la|le|den|der|ten|bin|al)"   # 1.1.1 FIX3: des, dos
_U = "\\u00c0-\\u00d6\\u00d8-\\u00de\\u0100-\\u017f"          # accented capitals (Felix, Etienne, Lukasz)
_L = "\\u00df-\\u00f6\\u00f8-\\u00ff\\u0100-\\u017f"
_TOKEN = (r"(?:[A-Z" + _U + r"][a-z'\-" + _L + r"]{1,20}|[A-Z]\.(?:\s?[A-Z]\.)?|[A-Z" + _U + r"]{2,14}(?![a-z])"
          r"|[A-Z](?=[ ][A-Z" + _U + r"][A-Za-z" + _L + r"]))")
_RE_NAME = re.compile(r"(?<![A-Za-z'\-])(" + _TOKEN + r"(?:[ ]+(?:" + _PARTICLE + r"[ ]+)?" + _TOKEN + r"){1,3})")
_HONORIFIC = re.compile(r"(?i)^(?:the\s+|de\s+|du\s+)?(?:mr|mrs|ms|miss|dr|prof(?:essor)?|sir|hon(?:ourable|orable)?"
                        r"|madam|gen|col|capt|sen|rev|mme|mlle)\.?\s+")
_POSTNOM = re.compile(
    r"(?i)[,\s]+(?:P\.?\s?Geo\.?|P\.?\s?Eng\.?|C\.?P\.?A\.?|CA|CFA|MBA|B\.?\s?Sc\.?|M\.?\s?Sc\.?|Ph\.?\s?D\.?|"
    r"ICD\.?D|LL\.?B|LL\.?M|CIM|FCPA|FCA|CPG|QP|MAusIMM|FAusIMM|P\.?\s?Chem\.?|B\.?\s?Eng\.?|M\.?\s?Eng\.?|"
    r"B\.?\s?A\.?|M\.?\s?A\.?|CGA|CMA|CIA|RPBio|PMP)\b\.?")
_COMPANY_TAIL = re.compile(
    r"(?i)^\s*(?:inc|corp|corporation|ltd|limited|llc|llp|plc|company|co|resources|mining|metals|gold|silver|copper|"
    r"lithium|uranium|exploration|minerals|capital|partners|securities|advisors|advisers|associates|group|holdings|"
    r"ventures|markets|bank|trust|fund|energy|technologies|solutions|consulting|geoscience|laboratories|labs)\b[.,)]?")
_TITLE_WORDS = re.compile(
    r"(?i)\b(?:chief|officers?|presidents?|directors?|chair(?:man|men|woman|women|person|persons)?|boards?|vice|"
    r"managers?|secretar(?:y|ies)|treasurers?|controllers?|advis[oe]rs?|advisory|counsel|geologists?|engineers?|"
    r"metallurgists?|geophysicists?|principals?|heads?|executives?|senior|interim|acting|committees?|management|"
    r"leadership|teams?|corporate|exploration|operations?)\b")
_PLACES = {
    "vancouver", "toronto", "calgary", "montreal", "ottawa", "edmonton", "winnipeg", "halifax", "victoria",
    "kelowna", "sudbury", "timmins", "val", "rouyn", "noranda", "quebec", "ontario", "alberta", "manitoba",
    "saskatchewan", "columbia", "british", "brunswick", "scotia", "newfoundland", "labrador", "yukon", "nunavut",
    "canada", "london", "denver", "reno", "nevada", "arizona", "utah", "alaska", "perth", "sydney", "york",
    "chile", "peru", "mexico", "brazil", "argentina", "ghana", "tanzania", "guinea", "zealand", "australia",
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "news", "press", "release", "company", "corporation", "exchange", "venture",
    "tsx", "cse", "otcqb", "otc", "frankfurt", "nasdaq", "newsfile", "accesswire", "globe", "wire",
}
# "Appoints Former Barrick Chief Geologist Dr. X": Barrick is the prior employer, X is the appointee,
# so only a name close behind a former/ex/previously is skipped -- never one merely preceded by "of".
_MONTHS_SET = {"january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
               "november", "december"}
_RE_PRIOR = re.compile(r"(?i)\b(?:former(?:ly)?|ex|previously|prior|retired)\b[\w\s\.,'-]{0,14}$")


_RE_CASE_JOIN = re.compile("([-'\\u2019])([a-z])")


def _case_fix(name: str) -> str:
    """EIRA THOMAS and Eira Thomas are one person: a shouted headline name is written out in name case."""
    letters = [c for c in name if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) <= len(letters) * 0.8:
        return name
    out = []
    for w in name.split(" "):
        if len(w.rstrip(".")) <= 2 and w.endswith("."):
            out.append(w.upper())
        elif w.upper() in ("CPA", "CA", "CFA", "MBA", "PHD", "II", "III", "IV", "JR", "SR"):
            out.append(w if w.upper() != "PHD" else "PhD")
        else:
            lead = len(w) - len(w.lstrip(_QUOTES_OPEN + "("))
            out.append(w[:lead] + w[lead:lead + 1].upper() + w[lead + 1:].lower())
    s = " ".join(out)
    s = _RE_CASE_JOIN.sub(lambda m: m.group(1) + m.group(2).upper(), s)
    s = re.sub(r"\b(Mc|Mac|O')([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)
    return s


_QUOTES_OPEN = "\u201c\u2018\""
_QUOTES_CLOSE = "\u201d\u2019\""


def _cut_open_quote(s: str) -> str:
    """'Brian Bosse "We' loses its tail; Charles \u201cChuck\u201d Westgard keeps his nickname."""
    straight = s.count('"')
    curly_open = sum(s.count(q) for q in "\u201c\u2018")
    curly_close = sum(s.count(q) for q in "\u201d\u2019")
    if straight % 2 == 1:
        s = s[:s.rfind('"')]
    if curly_open > curly_close:
        s = s[:max(s.rfind("\u201c"), s.rfind("\u2018"))]
    return s.rstrip()


def _strip_name(s: str) -> str:
    s = _HONORIFIC.sub("", re.sub(r"\s+", " ", s or "").strip())
    s = re.sub(r"\s*[(\[][^)\]]*$", "", s)                    # 1.1: "David Bellon (USMC"
    s = _cut_open_quote(s)                                  # 1.1: 'Brian Bosse "We'
    parts = s.split(" ")
    if len(parts) >= 3 and re.fullmatch(r"[A-Z]{2,5}", parts[-1]) and any(re.search(r"[a-z]", w) for w in parts[:-1]):
        s = " ".join(parts[:-1])                                # 1.1: "Thomas G. Klein BMM"
    s = _POSTNOM.sub("", s)
    return _case_fix(s.strip(" ,.;:-"))


# words that appear capitalised in a Title Case headline but can never be part of a person's name
_STOP_TOKENS = {
    "appoint", "appoints", "appointed", "appointing", "appointment", "appointments", "announce", "announces",
    "announced", "announcement", "name", "names", "named", "join", "joins", "joined", "joining", "welcome",
    "welcomes", "welcomed", "add", "adds", "added", "addition", "strengthen", "strengthens", "strengthening",
    "complete", "completes", "completed", "close", "closes", "closed", "report", "reports", "provide", "provides",
    "resign", "resigns", "resigned", "resignation", "retire", "retires", "retired", "retirement", "step", "steps",
    "stepping", "down", "elect", "elects", "elected", "election", "promote", "promotes", "promoted", "promotion",
    "transition", "transitions", "depart", "departs", "departure", "change", "changes", "grants",
    "granted", "expand", "expands", "hire", "hires", "hired", "engage", "engages", "engaged",
    "new", "its", "his", "her", "their", "the", "to", "as", "and", "of", "for", "with", "from", "at", "in", "on",
    "a", "an", "is", "are", "has", "have", "been", "be", "will", "that", "this", "these", "by", "into", "up",
    "ceo", "cfo", "coo", "cto", "vp", "svp", "evp", "esg", "ir", "qp", "llc", "llp", "plc", "inc", "corp", "ltd",
    "mr", "mrs", "ms", "dr", "prof", "sir", "hon", "former", "formerly", "ex", "previously", "interim", "acting",
    "further", "additional", "other", "certain", "all", "both", "effective", "immediately", "pursuant", "such",
    "project", "property", "gold", "silver", "copper", "lithium", "uranium", "nickel", "zinc", "cobalt",
    "resources", "mining", "minerals", "metals", "energy", "exploration", "corporation", "limited", "holdings",
    "capital", "partners", "securities", "markets", "group", "ventures", "technologies", "solutions",
    # institutions and awards: the biography paragraph after an appointment is full of these
    "university", "college", "school", "institute", "academy", "faculty", "army", "navy", "corps", "command",
    "force", "forces", "regiment", "brigade", "division", "fraternity", "sorority", "medal", "award", "awards",
    "association", "society", "foundation", "ministry", "department", "agency", "bureau", "council", "committee",
    "hospital", "clinic", "centre", "center", "program", "programme", "pathway", "facility", "laboratory",
    "surgery", "medicine", "science", "sciences", "arts", "business", "law", "engineering", "geology",
    "bank", "media", "news", "journal", "times", "post", "review", "magazine", "network", "systems",
    "services", "consulting", "advisory", "international", "global", "national", "american", "canadian",
    "royal", "state", "federal", "united", "states", "kingdom", "task", "quantum", "age", "top", "pre",
    # phrases that describe a role or a document rather than name anybody
    "member", "members", "qualified", "person", "persons", "seasoned", "accomplished", "innovator",
    "veteran", "expert", "specialist", "professional", "entrepreneur", "leader", "pioneer", "founder",
    "co", "public", "relations", "direction", "outstanding", "young", "men", "women", "retains",
    "retained", "retain", "contact", "information", "notice", "appendix", "rule", "symbol", "telephone",
    "email", "website", "release", "private", "placement", "brokered", "offering", "financing", "closing",
    "communications", "association", "industries", "enterprises", "retail", "industry", "unattended",
    "mine", "mines", "deposit", "discovery", "webinar", "presentation", "update", "results", "quarter",
    "upcoming", "agm", "annual", "meeting", "general", "eng", "geo", "geol", "sc", "phd", "cpa", "cfa",
    "mba", "oiq", "apegbc", "peng", "pgeo", "icd", "llb", "llm", "cim", "qp", "pmp", "ing", "msc", "bsc",
    "pays", "pay", "paid", "tribute", "late", "acknowledges", "acknowledge", "acknowledged", "receipt",
    "receives", "receive", "received", "reinforces", "commitment", "ownership", "nomination", "nominates", "nominated",
    "agree", "agrees", "agreed", "act", "acts", "acting", "accept", "accepts", "accepted", "serve",
    "serves", "served", "assume", "assumes", "assumed", "succeed", "succeeds", "succeeded", "replace",
    "replaces", "replaced", "terminate", "terminates", "terminated", "termination", "continue",
    "continues", "continued", "passes", "passing", "passed", "away", "mourns", "mourning", "commercial", "deployment", "technology",
    "research", "innovation", "production", "processing", "operational", "development", "strategy",
    "strategic", "resignation", "resignations", "appointment", "appointments", "successor", "succession",
    # 1.1: headline verbs and nouns the blind audit caught being read as people
    "issues", "issue", "defers", "defer", "accelerates", "bolstering", "bolsters", "expertise", "tranche",
    "chartered", "accountant", "accountants", "analyst", "infrastructure", "stated", "consideration",
    "resource", "finance", "rare", "earth", "earths", "brings", "more", "than", "lieutenant", "ambassador",
    "incumbent", "shares", "units", "incentive", "independent", "major", "non",
    "africa", "saharan", "survey", "course", "education", "affairs", "commencement", "formal", "highlights",
    "video", "vms",
}
_STOP_111 = {
    # 1.1.1: heading, deal, table and document words the ACC150 audit caught read as people ("Resulting Issuer",
    # "Option Agreement", "Sets Date", "Record Date", "Selected Drill", "Proposed Consolidation", "Pdac Booth")
    "issuer", "agreement", "agreements", "option", "options", "loan", "warrant", "warrants", "claims", "consortium",
    "nation", "auditor", "auditors", "legislation", "drill", "drilling", "drilled", "assay", "assays", "width",
    "table", "area", "depth", "historical", "composite", "studies", "study", "easting", "northing", "elevation",
    "azimuth", "dip", "deep", "confirms", "confirm", "electing", "acquire", "acquires", "acquisition",
    "consolidation", "transaction", "proposed", "date", "record", "sets", "contract", "contractor", "miner",
    "government", "office", "phase", "prospect", "interview", "dissemination", "immediate", "celebrating", "welcoming",
    "remarkable", "journey", "having", "meanwhile", "justice", "social", "next", "final", "commissioning", "letter",
    "share", "preliminary", "economic", "assessment", "valuer", "authorised", "authorized", "land", "district",
    "special", "technical", "including", "ratio", "partnership", "joint", "defense", "industrial", "base", "first",
    "credit", "local", "projects", "south", "north", "east", "northern", "southern", "african", "fort",
    "diamond", "diamonds", "minera", "mineros", "minerales", "mineracao", "companies", "performing",
    "selected", "sampling", "samples", "sample", "metres", "meters", "grade", "grades", "total", "estimate",
    "stream", "royalty", "royalties", "financial", "statements", "circular", "proxy", "resolution", "resolutions",
    "proposes", "propose", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "commences", "commence", "commenced", "el", "los", "las", "sur", "norte", "metis", "professionals", "governance",
    "experts", "leaders", "executives", "veterans", "excellency", "mill", "plant", "smelter", "refinery", "concentrator",
    "amounts", "deferred", "permit", "permits", "renewal",
}
_NOT_NAME = _STOP_TOKENS | _STOP_111
# FIX5: a conjunction opening a sentence ("If ABC is successful"), vote-table words ("Votes Against"), fund and
# industry words in a headline ("... Capital Fund VI L.P.", "Leading Battery Materials ... Investors")
_STOP_FIX5 = {"if", "upon", "when", "whereas", "unless", "although", "vote", "votes", "voted", "fund", "funds", "materials",
              "investors", "investor", "leading"}
_NOT_NAME = _NOT_NAME | _STOP_FIX5
# FIX5: a town in a dateline or an address ("Port Town, British Columbia, July 19, 2022", "Port Town, B.C. V1A 1A1")
_RE_PLACE_AFTER = re.compile(r"(?i)^\s*,\s*(?:british\s+columbia|b\.\s?c\.|bc\b|alberta|ab\b|saskatchewan|manitoba|ontario|"
                             r"on\b|quebec|qc\b|qu\u00e9bec|nova\s+scotia|new\s+brunswick|newfoundland|yukon|nunavut|"
                             r"northwest\s+territories|nevada|arizona|colorado|utah|alaska|idaho|montana|wyoming|"
                             r"california|texas|australia|canada|mexico|peru|chile)\b")
# 1.1.1: given names that are also ordinary words, left out of the common-word test in _common_phrase
_WORD_NAMES = set(
    "will mark grant bill frank rich dawn hope guy pat rob don art chase gene max joy faith grace drew jack carol "
    "lance cliff bob ray sandy rusty penny ruby amber crystal jean jay dean wade hunter sterling earl duke glen dale "
    "clay heath rock stone summer april june may august rose brook gray grey miles warren norman victor pierce reed "
    "rod nick sue bud ward lane wood holly ivy iris sky river autumn jade pearl skip chip ford carter mason baker "
    "cole bay page kit sunny rex heather robin buck hardy young long bond wells price hall mills".split())
# 1.1: a run holding one of these is a place, never a person, and is dropped whole
_GEO_WORDS = {"island", "islands", "creek", "valley", "peninsula", "mountain", "mountains", "river", "lake", "lakes",
              "bay", "canyon", "basin", "belt", "trend", "zone", "brook", "zones"}
# 1.1: a run of capitalised words containing one of these is an address, never a person
_ADDRESS_WORDS = {"street", "avenue", "ave", "road", "drive", "suite", "floor", "boulevard",
                  "blvd", "crescent", "highway", "hwy", "parkway", "plaza", "tower", "building"}


_CORP_WORD = (r"inc|corp|corporation|incorporated|ltd|limited|llc|llp|plc|company|holdings|group|"
              r"resources|mining|minerals|metals|energy|exploration|ventures|communications|technologies|"
              r"systems|industries|enterprises|association|laboratories|university|college|institute|"
              r"bank|partners|capital|securities|fund|trust|gold|silver|copper|lithium|uranium|nickel|"
              r"graphite|cobalt|zinc|potash|petroleum|pharma|centre|center|council|research|academy|"
              r"society|foundation|school|hospital|agency|bureau|oil|steel|aluminum|platinum")
_RE_CORP_WORD = re.compile(r"(?i)\b(" + _CORP_WORD + r")\b\.?")
_RE_BACK_TOKEN = re.compile(r"(?:[A-Z" + _U + r"][\w'\-" + _L + r"]*|[A-Z" + _U + r"]{2,})[ ]*\Z")
_BACK_STOP = {"the", "a", "an", "of", "and", "for", "to", "at", "in", "on", "with", "from", "by", "its",
              "his", "her", "their", "new", "as", "into", "about", "or"}


# 1.1.1: nouns that sit inside a company's name ("Talent Infinity Resource Developments Inc.")
_BIZ_NOUNS = {"resource", "development", "developments", "infrastructure", "international", "global", "national",
              "american", "canadian", "royal", "united", "commercial", "industries", "enterprises", "services",
              "technologies", "solutions", "systems", "media", "network", "consulting", "advisory", "finance"}


def company_names(text: str):
    """Token lists for the company names the release prints, so the issuer is never read as a person.

    Found by walking back from a corporate word ("Inc.", "Minerals", "Silver") over the capitalised words
    in front of it: NORTH ARROW MINERALS INC. gives [north, arrow, minerals, inc], which is how
    "NORTH ARROW APPOINTS ..." stops producing a person called North Arrow."""
    out = []
    titled = None                                         # 1.1.1: the names the release writes after Mr./Ms./Dr.
    for m in _RE_CORP_WORD.finditer(text):
        if re.match(r"(?i)[ \n]+(?:manager|director|geologist|officer|engineer|superintendent|supervisor|coordinator|"
                    r"lead|consultant|advisor|adviser|vice|head)\b", text[m.end():m.end() + 20]) \
                and m.group(1).lower() in ("exploration", "mining", "energy", "research"):
            continue                                      # FIX3: "Names Lori Paslawski Exploration Manager": a title
        toks = [re.sub(r"[^a-z]", "", m.group(1).lower())]
        i = m.start()
        for _ in range(6):
            mm = _RE_BACK_TOKEN.search(text, max(0, i - 120), i)   # 1.1.1: a window, not a copy of the text
            if mm is None:
                break
            w = re.sub(r"[^a-z]", "", mm.group(0).lower().replace("'s", "").replace(chr(0x2019) + "s", ""))
            if not w or w in _BACK_STOP:
                break
            if w in _STOP_TOKENS and not _RE_CORP_WORD.fullmatch(w) and w not in _BIZ_NOUNS:
                break                                     # 1.1: "Vincent Chen Joins Lancaster Resources"
            toks.append(w)
            i = mm.start()
        if len(toks) < 2 or _RE_TITLED_END.search(text[max(0, i - 6):i]):
            continue                                      # 1.1.1: not "Mr. Alain Bureau"
        if titled is None:
            titled = {" ".join(_name_words(x)) for x in _RE_TITLED_NAME.findall(text)}
        if " ".join(toks[:0:-1] + toks[:1]) in titled:
            continue
        out.append(toks)
    return out


_RE_TITLED_END = re.compile(r"(?i)\b(?:mr|mrs|ms|dr)\.?\s+\Z")
_RE_TITLED_NAME = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|MR|MRS|MS|DR)\.?\s+((?:[A-Z][\w'\-]*\.?\s+){0,3}[A-Z][\w'\-]+)")


def _tok_in(tok: str, bag) -> bool:
    for t in bag:
        if tok == t or (len(tok) >= 3 and t.startswith(tok)) or (len(t) >= 4 and tok.startswith(t)):
            return True
    return False


def _is_company(cand: str, companies) -> bool:
    toks = [re.sub(r"[^a-z]", "", w.lower()) for w in cand.split()]
    toks = [t for t in toks if t]
    if not toks:
        return False
    return any(all(_tok_in(t, bag) for t in toks) for bag in companies)


# 1.1.1: foreign company forms ("Vale S.A.", "El Huasco SpA", "African Star Minerals (Pty) Ltd", "Iceland Resources EHF")
_COMPANY_SUFFIX = re.compile(r"(?:^|[\s,])(?:S\.\s?A\.?(?:\s?[CS]\.?)?|SpA|Sp|S\.?A\.?S|SAS|SARL|GmbH|AG|Pty|PTY|EHF|ehf|"
                             r"AB|ASA|NV|BV|Ltda|LTDA|S\.?L|SRL|SAC|SAB|KK|PLC)(?:\.|\b|$)")
_COMPANY_AFTER = re.compile(r"^[\s,(]*(?:S\.\s?A\b|SpA\b|Sp\b|S\.?A\.?S\b|SAS\b|SARL\b|GmbH\b|AG\b|Pty\b|PTY\b|EHF\b|"
                            r"ehf\b|ASA\b|Ltda\b|LTDA\b|SRL\b|SAC\b|SAB\b|PLC\b)")
_RE_TICKER_LEAD = re.compile(r"(?i)(?:CSE|TSXV?|NYSE|NASDAQ|FSE|FRA|OTC\w*|WKN|ISIN|SEDAR|AMEX|LSE|ASX)\s*"
                             r"[:\-]\s*[\(\[]?\s*$")


def _titled_after(after: str) -> bool:
    """FIX3: the words after a name are ", <the person's title>" ("Jeremy South, Chief Financial Officer")."""
    m = re.match(r",[ \n]*(?:the[ \n]+)?(?:company['\u2019]s[ \n]+)?(?=[A-Z])", after)
    if not m:
        return False
    r = R.match(after, m.end())
    return r is not None and r[3][0] == m.end() and r[1] not in ("Director",)


def _looks_like_person(cand: str, before: str, after: str) -> bool:
    if not cand or len(cand) < 4:
        return False
    if _RE_TICKER_LEAD.search(before[-20:]):
        return False
    if _TITLE_WORDS.search(cand):
        return False
    if _COMPANY_TAIL.match(after):
        return False
    if re.search("(?i)['\\u2019]s\\b", cand):                      # "Focus Graphite's", "MAX Power's"
        return False
    if re.match(r"\s?:\s?[A-Z0-9]{2,6}\b", after):
        return False                                          # 1.1.1: an exchange label, "OT CQX:MNSAF"
    if _COMPANY_SUFFIX.search(cand) or _COMPANY_AFTER.match(after):
        return False                                          # 1.1.1: "Vale S.A.", "Minera CAPPEX S.A.C."
    if (_RE_PLACE_AFTER.match(after) or re.search(r"\bL\.\s?P\.?", cand)):
        return False
    words = [w for w in re.split(r"\s+", cand) if w]
    if len(words) < 2:
        return False
    real = 0
    for w in words:
        lw = re.sub(r"[^a-z]", "", w.lower())
        if not lw:
            return False
        if re.fullmatch(r"[A-Z]\.", w) and real:
            continue                                          # 1.1.1: middle initial
        if lw in _NOT_NAME or lw in _PLACES or lw.endswith("based"):
            titled = re.search(r"(?i)\b(?:mr|mrs|ms|dr|prof)\.?\s+\Z", before)
            if not (w is words[-1] and lw in _SURNAME_WORDS and (titled or _titled_after(after))) \
                    and not (titled and len(words) == 2 and (lw in _PLACES or lw in _SURNAME_WORDS) and lw not in _MONTHS_SET):
                return False                                  # 1.1.1: "Mr. Alain Bureau" keeps his surname (FIX3: and
                                                              # "Ms. Victoria Vargas", "Mr. Jeremy South")
        if lw not in ("van", "von", "de", "des", "del", "della", "di", "da", "das", "dos", "du", "la", "le", "den", "der",
                      "ten", "bin", "al") \
                and len(lw) > 1:
            real += 1
    if real < 2:
        return False
    if re.search(r"(?i)\b(?:corp|inc|ltd|llp|llc)\b", cand):
        return False
    return True


_RE_TOKEN = re.compile(r"[A-Z" + _U + r"][a-z'\-" + _L + r"]{1,20}|[A-Z]\.(?:\s?[A-Z]\.)?|"
                       r"[A-Z" + _U + r"]{2,14}(?![a-z])|"
                       r"[A-Z](?=[ ][A-Z" + _U + r"][A-Za-z" + _L + r"])|"
                       r"(?<![A-Za-z])(?:van|von|de|des|del|della|di|da|das|dos|du|la|le|den|der|ten|bin|al)(?![a-z])")
# (FIX3: a particle is a word of its own, not the end of "include" or "made")
# one space, or a parenthesised nickname -- "Peter Jonathan (PJ) Murphy" is one person, and
# re.match would have accepted a newline here, which is how "James Schweitzer Passes\nAway" became a name.
_RE_GAP_OK = re.compile("[ \\n]?|[ \\n]?[(\\[][ \\n]?|[ \\n]?[)\\]][ \\n]?"
                        "|[ \\n]?[\u201c\u201d\"\u2018\u2019'][ \\n]?|[ ]?-(?=[A-Z])")


def _token_runs(text: str):
    """Runs of capitalised tokens separated by single spaces: [(tokens, start, end)].

    Scanned token by token rather than matched as one pattern, so a rejected candidate never swallows the
    name beside it -- "Former Barrick Chief Geologist Dr. Alice Stone" gives up Barrick and keeps Alice Stone."""
    runs, cur = [], []
    last_end = -1
    for m in _RE_TOKEN.finditer(text):
        if cur and _RE_GAP_OK.fullmatch(text[last_end:m.start()]):
            cur.append(m)
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = [m]
        last_end = m.end()
    if len(cur) >= 2:
        runs.append(cur)
    return runs


def people(text: str, companies=None):
    """[(name, start, end)] for every person named in `text`, in order.

    A run of capitalised tokens is split at any word that cannot belong to a name (a verb from the headline,
    a company suffix, a place, an institution), and each remaining stretch of two to four tokens is a
    candidate. Honorifics and post-nominals are trimmed off the ends."""
    out = []
    companies = company_names(text) if companies is None else companies
    tickers = {t for t in _RE_TICKER.findall(text)}                   # 1.1.1: "BGD Moore", "MNSAF Mineros"
    words = _lower_words(text)
    for run in _token_runs(text):
        if any(re.sub(r"[^a-z]", "", m.group(0).lower()) in (_ADDRESS_WORDS | _GEO_WORDS) for m in run):
            continue                                          # 1.1: "1500 West Georgia Street", "Suite 1200"
        mixed = any(re.search(r"[a-z]", m.group(0)) for m in run)
        piece = []
        for i, m in enumerate(run + [None]):
            word = None if m is None else re.sub(r"[^a-z]", "", m.group(0).lower())
            bad = m is None or word in _NOT_NAME or word in _PLACES or _TITLE_WORDS.fullmatch(m.group(0) or "") \
                or m.group(0) in tickers or (len(m.group(0)) >= 4 and m.group(0).upper() in tickers) \
                or m.group(0).lower().endswith("-based")
            if bad and m is not None and piece and re.fullmatch(r"[A-Z]\.", m.group(0)):
                bad = False                                   # 1.1.1: a middle initial "A." is not the word "a"
            # 1.1.1: an organisation's acronym in front of a name written in ordinary case ("SOQUEM Danielle")
            if not bad and not piece and mixed and len(m.group(0)) >= 3 and m.group(0).isupper() \
                    and m.group(0) not in ("III", "JR", "SR") and not (re.fullmatch(r"[A-Z]\.\s?[A-Z]\.", m.group(0))
                             and re.sub(r"\W", "", m.group(0)) not in ("BC", "US", "UK", "NS", "NB", "PE", "NL", "NT", "SA", "PO")):
                bad = True                                    # (FIX3: initials "J.P. Dau", "C.L. Otter" are not one)
            # FIX3: "Ms. Victoria Vargas", "Mr. Christian Timmins": after a title, a given name or surname that is also
            # a place or an ordinary word is part of the name
            if bad and m is not None and m.group(0)[:1].isupper() and re.search(r"[a-z]", m.group(0)) \
                    and (word in _PLACES or word in _SURNAME_WORDS) and word not in _MONTHS_SET and len(piece) <= 1 \
                    and _RE_TITLED_END.search(text[max(0, (piece[0] if piece else m).start() - 6):(piece[0] if piece else m).start()]) \
                    and (piece or (i + 1 < len(run) and re.search(r"[a-z]", run[i + 1].group(0)))):
                bad = False
            # 1.1.1: "Mr. Alain Bureau": after a title and a given name, a word that is also a surname is one
            # (FIX3: so is one followed by the person's title, "Jeremy South, Chief Financial Officer since 2018")
            if bad and m is not None and len(piece) == 1 and word in _SURNAME_WORDS and m.group(0)[:1].isupper() \
                    and (re.search(r"(?i)\b(?:mr|mrs|ms|dr|prof)\.?\s+\Z", text[max(0, piece[0].start() - 6):piece[0].start()])
                         or _titled_after(text[m.end():m.end() + 40])):
                bad = False
            if not bad:
                piece.append(m)
                continue
            # 1.1.1: "CRAIG BROWN P.ENG.", "Andrew Ramcharan Ph.D.": the last token opens a post-nominal
            if len(piece) >= 3 and len(piece[-1].group(0).rstrip(".")) <= 2 \
                    and _RE_POSTNOM_OPEN.match(text, piece[-1].end() - (1 if piece[-1].group(0).endswith(".") else 0)):
                piece = piece[:-1]
            # FIX3: when a long run fails, its last two words (three with a middle initial) may still be the person
            # ("Secretary of Homeland Security Kirstjen M. Nielsen": the office in front of the name)
            tries = [piece] if len(piece) >= 2 else []
            if len(piece) >= 4 or (len(piece) == 3 and not re.fullmatch(r"[A-Z]\.", piece[1].group(0))):
                tries.append(piece[-3:] if re.fullmatch(r"[A-Z]\.", piece[-2].group(0)) else piece[-2:])
            for k, cut in enumerate(tries):
                a, b = cut[0].start(), cut[-1].end()
                cand = text[a:b]
                name = _strip_name(cand)
                before = text[max(0, a - 40):a]
                after = text[b:b + 30]
                prior = _RE_PRIOR.search(before[-26:])
                if prior and R.match(prior.group(0)) and not _RE_CORP_WORD.search(prior.group(0)):
                    prior = None                              # 1.1.1: "former CEO James Sykes" is the former holder
                if _looks_like_person(name, before, after) and not prior \
                        and not _is_company(name, companies) and not _RE_ORG_LEAD.search(before) \
                        and not _common_phrase(name, text, words) \
                        and (k == 0 or (all(re.fullmatch(r"[A-Z][a-z'\-" + _L + r"]{2,}|[A-Z]\.", x.group(0)) for x in cut)
                                        and not _is_company(text[piece[0].start():b], companies))):
                    # the honorific is part of the run only when it was written as one ("Dr. Alice Stone")
                    shift = len(cand) - len(_HONORIFIC.sub("", cand))
                    out.append((name, a + shift, b))
                    break
            piece = []
    out.sort(key=lambda t: t[1])
    keep = []
    for name, a, b in out:
        if keep and a < keep[-1][2]:
            continue
        keep.append((name, a, b))
    return keep


# 1.1.1: "Mr. Weinig will be assuming a new role", "Dr Hennigh as a Special Technical Advisor", "Mr. Higson-Smith will
# serve as Chairman": after the first full mention a release names people by title and surname.  Such a mention is
# read as the person whose full name the release gives, when exactly one full name ends in that surname.
_RE_TITLED_SURNAME = re.compile("\\b(?:Mr|Mrs|Ms|Dr|Prof|MM|Messrs)\\.?[ \\n]+([A-Z" + _U + "][a-z'\\-" + _L + "]+(?:-[A-Z][a-z]+)?)"
                                "(?![ \\n]*[A-Z" + _U + "][a-z])")


def _surname_mentions(text, keep):
    """[(full name, start, end)] for each "Mr. Surname" mention of a person named in full elsewhere."""
    if not keep:
        return []
    by_last = {}
    for name, _a, _b in keep:
        last = _name_words(name)[-1:] or [""]
        by_last.setdefault(last[0], set()).add(name)
    extra = []
    j = 0
    for m in _RE_TITLED_SURNAME.finditer(text):
        a, b = m.start(1), m.end(1)
        while j < len(keep) and keep[j][2] <= a:
            j += 1
        if j < len(keep) and keep[j][1] <= a < keep[j][2]:
            continue                                          # part of a full mention already
        names = by_last.get((_name_words(m.group(1)) or [""])[-1])
        if not names:
            continue
        full = max(names, key=len)
        if not all(same_person(full, n) for n in names):
            continue                                          # two people share the surname
        extra.append((full, a, b))
    return extra


# FIX3: "to have Boen join our Technical Advisory Committee", "Todd has also joined Pancon's Technical Advisory
# Committee", "pleased to welcome Derek to our Board": after the full mention a release may use the given name alone,
# right beside the action. Read only there, and only when one person named in full has that given name.
_RE_GIVEN_ACTION = re.compile(r"(?i)^[ \n]+(?:has[ \n]+(?:also[ \n]+)?|will[ \n]+(?:also[ \n]+)?)?(?:join(?:s|ed)?|joined)\b"
                              r"(?=\s+(?:the\s+|its\s+|our\s+|their\s+|[A-Z][\w&\-]*['\u2019]s\s+)?(?:[A-Z][\w&\-]*\s+){0,3}"
                              r"(?:board|advisory|technical\s+(?:advisory|committee)|team|management)\b)"
                              r"|^[ \n]+to[ \n]+(?:our|the|its|their)[ \n]+(?:[A-Z][\w&'\-]*[ \n]+){0,2}(?:board|advisory|technical|team)\b")


def _given_mentions(text, keep):
    """[(full name, start, end)] for a given name used alone beside a join or welcome (see above)."""
    acts = [m.start() for m in re.finditer(r"(?i)\b(?:join|welcom)", text)]
    if not keep or not acts:
        return []
    by_first = {}
    for name, a, _b in keep:
        w = _name_words(name)
        if len(w) >= 2 and len(w[0]) >= 3:
            by_first.setdefault(w[0], set()).add(name)
    extra, seen = [], set()
    for at in acts:
        for m in re.finditer(r"\b[A-Z][a-z]{2,}\b(?![ \n]*[A-Z(])", text[max(0, at - 30):at + 30]):
            a = max(0, at - 30) + m.start()
            b = a + len(m.group(0))
            names = by_first.get(m.group(0).lower())
            if a in seen or not names or len({tuple(_name_words(n)[-1:]) for n in names}) != 1:
                continue                                      # (two people sharing the given name are left alone)
            seen.add(a)
            if a < min(ka for n, ka, _kb in keep if n in names) or any(ka <= a < kb for _n, ka, kb in keep):
                continue                                      # only after the full mention, and not part of one
            before = text[max(0, a - 14):a]
            after = text[b:b + 60]
            if (re.search(r"(?i)\bhave[ \n]+\Z", before) and _RE_GIVEN_ACTION.match(after)) \
                    or (re.search(r"(?i)\bwelcom\w*[ \n]+\Z", before) and _RE_GIVEN_ACTION.match(after) and after.lstrip().startswith("to")) \
                    or (not re.search(r"(?i)\b(?:have|welcom\w*)[ \n]+\Z", before) and _RE_GIVEN_ACTION.match(after)
                        and not after.lstrip().startswith("to")):
                extra.append((max(names, key=len), a, b))
    extra.sort(key=lambda t: t[1])
    return extra


# 1.1.1 ---------------------------------------------------------------- is it a person at all?
_SURNAME_WORDS = {"bureau", "law", "post", "bank", "young", "king", "land", "north", "south", "east", "royal", "state",
                  "page", "price", "bond", "hall", "power", "field", "deep", "best", "diamond", "miner", "fort", "first",
                  "rich", "booth", "best", "white", "black", "brown", "green", "gold", "silver", "stone", "hill"}
_RE_TICKER = re.compile(r"(?:TSX[\s\-]?V?|TSXV|CSE|NYSE(?:\s?American)?|NASDAQ|OTC\w*|ASX|AIM|FSE|FRA|LSE|BVL|BVC|JSE|NEO)"
                        r"\s*[.:\-]?\s*[:\-]\s*([A-Z][A-Z0-9]{1,5})\b")
_RE_POSTNOM_OPEN = re.compile(r"\.\s?(?:Eng|ENG|Geo|GEO|D\b|Sc|SC|Chem|Geol|A\b)")
# a name right after these words is the organisation someone joined or came from ("delighted to join Atlas Salt",
# "joins Surge from Rio Tinto", "began her career at Vale"), never the person being appointed
_RE_ORG_LEAD = re.compile(r"(?i)(?:\bjoin(?:s|ed|ing)?|(?<!over\s)(?<!retirement\s)(?<!resignation\s)(?<!departure\s)\bfrom|\bcareer\s+(?:at|with)|\bleaving|\bworked\s+(?:at|for|with))"
                          r"\s+(?:the\s+)?\Z")
_STRIP = ".,;:()[]{}!?\"'"


def _lower_words(text):
    """The ordinary lower-case words of the release (e-mail addresses and web links left out)."""
    return {w for w in (t.strip(_STRIP) for t in text.split() if "@" not in t and "/" not in t)
            if w.islower() and w.isalpha()}


def _common_phrase(name, text, words):
    """A heading, a job title or a common phrase read as a name.  Two signs, both judged on the release itself:
    - the first word is used in the release as an ordinary lower-case word ("Geotechnical Drilling", "Discussions
      Continuing", "District Valuer"); given names that are also words (Grant, Mark, Will) are exempt;
    - every mention is preceded by an article ("the Resulting Issuer", "an Authorised Land Officer"): people's
      names do not take "a", "an" or "the"."""
    first = re.sub(r"[^a-z]", "", name.split()[0].lower())
    if len(first) >= 3 and first not in _WORD_NAMES and first in words:
        return True
    at, k = [], text.find(name)
    while k >= 0 and len(at) < 50:
        at.append(k)
        k = text.find(name, k + 1)
    return bool(at) and all(_RE_ARTICLE_END.search(text[max(0, k - 5):k]) for k in at)


_RE_ARTICLE_END = re.compile(r"(?i)\b(?:a|an|the)\s+[\"\u201c]?\s*\Z")


# ------------------------------------------------------------------ actions
_RE_APPOINT = re.compile(
    r"(?i)\b(?:appoint(?:s|ed|ing|ment|ments)?|names?|named|naming|nominat(?:es|ed|ion|ions)\b|announc(?:es|ed|ing)(?=[^.\n]{0,80}?\b(?:as|to)\s+(?:its\s+|the\s+|a\s+|an\s+)?(?:new\s+|incoming\s+)?(?:chief|president|vice[\s\-]president|s?e?vp\b|director|chair|board|advisor|adviser|advisory|technical|strategic|head\s+of|general|corporate|interim|senior|executive|managing))"
    r"|announce(?=\s+(?:to|as)\s+(?:its|the|our)\s+(?:new\s+)?(?:board|advisory|technical\s+advisory))"   # FIX3
    r"|(?<=board\s)(?:has\s+been|was|is|will\s+be)\s+(?:extended|expanded|enlarged|increased)\s+to\s+(?:now\s+)?include"   # FIX3
    r"|elect(?:s|ed|ing)\b(?!\s+to\s+(?!the\b|its\b|serve\b|join\b|a\b)[a-z])|joins?\b|joined\b|joining\b|welcom(?:e|es|ed|ing)|add(?:s|ed|ition)\s+(?:of\s+)?(?!to\s+its\s+cash)"
    r"|bring(?:s|ing)?\s+on(?:board)?|hir(?:es|ed|ing)|engages?\s+(?!in\b)|engaged\s+(?!in\b|with\b|to\b|by\b|as\b|on\b|for\b|the\s+services)|strengthen(?:s|ed|ing)?|agree(?:s|d)\s+to\s+(?:serve|join|act)|(?:has|have)\s+agreed\s+to\s+(?:serve|join|act)|(?:been\s+)?retained\s+as|will\s+serve\s+as\s+(?:a\s+|an\s+|the\s+)?(?!financial|legal)"
    r"|expand(?:s|ed|ing)\s+(?:its\s+)?(?:board|team|leadership|management)|accept(?:s|ed|ing)?\s+(?:a|an|the)\s+(?:position|role|appointment|seat|nomination|invitation)"
    r"|(?:has|have|had)\s+taken\s+on\s+the\s+(?:role|position)\s+(?:as|of)"
    r"|(?<=role\s)(?:will\s+be|has\s+been|was|is\s+being)\s+(?:assumed|taken\s+(?:on|over))(?=\s+by\b))\b")   # FIX3
_RE_DEPART = re.compile(
    r"(?i)\b(?:resign(?:s|ed|ation|ations|ing)?|retir(?:e|es|ed|ement|ing)|steps?\s+(?:down|aside)|stepp(?:ed|ing)\s+(?:down|aside)"
    r"|depart(?:s|ed|ure|ures|ing)?(?!\s+(?:for|to)\b)|not\s+seek(?:ing)?\s+re[\s\-]?election|complet(?:ed|es|ing)\s+(?:his|her|their)\s+term|leav(?:es|ing)\b|left\s+the\s+(?:board|company)|no\s+longer\s+(?:serves?|be|the|with|an?\b)"
    r"|ceas(?:es|ed)\s+to\s+(?:be|serve)|vacat(?:es|ed)|terminat(?:es|ed|ion|ions)\b"
    r"|(?:will|did|does|would)\s+not\s+(?:be\s+)?stand(?:ing)?\s+for\s+re[\s\-]?election|not\s+(?:to\s+)?(?:be\s+)?stand(?:ing)?\s+for\s+re[\s\-]?election|declin\w*\s+to\s+stand\s+for\s+re[\s\-]?election|passing\s+of|passed\s+away|dismiss(?:es|ed)"
    r"|relinquish(?:es|ed|ing)?|passes?\s+away|vacanc(?:y|ies)|pass(?:es|ed|ing)\s+of|pays?\s+tribute|paid\s+tribute"
    r"|pay(?:s|ing)?\s+(?:a\s+|as\s+)?(?:posthumous|final|last)\s+tribute|in\s+memoriam"
    r"|(?:was|were)\s+not\s+re[\s\-]?elected"                       # FIX3: "Feisal Somji was not re-elected to the Board"
    # FIX5: "will not be seeking re-election", "who will not be running for re-election", "did not stand for re-\nelection"
    r"|not\s+(?:be\s+)?(?:seek(?:ing)?|run(?:ning)?)\s+for\s+re(?:[\s\-]|-\s+)?election"
    r"|not\s+(?:be\s+)?seek(?:ing)?\s+re(?:[\s\-]|-\s+)?election|not\s+(?:to\s+)?(?:be\s+)?stand(?:ing)?\s+for\s+re-\s+election)\b")
_RE_CHANGE = re.compile(
    r"(?i)\b(?:promot(?:es|ed|ion|ing)|transition(?:s|ed|ing)?\s+(?:to|from|into)|assum(?:e|es|ed|ing)\s+(?:the\s+|a\s+)?(?:new\s+)?role"
    r"|mov(?:es|ed|ing)\s+(?:in)?to\s+the\s+role|takes?\s+(?:on|over)\s+(?:as|the\s+role)|elevat(?:es|ed)"
    r"|change\s+of\s+(?:role|title)|expand(?:s|ed)\s+(?:his|her|their)\s+role|re[\s\-]?designat\w*|(?:will\s+)?mov(?:e|es|ed|ing)\s+(?:in)?to\s+(?:the\s+(?:role|position)\s+of\s+|the\s+)?(?=[A-Za-z]))\b")
# 1.1: an AGM re-election or a re-appointment keeps someone where they already were
_RE_REELECT = re.compile(r"(?i)\b(?:(?<!for\s)re[\s\-]?elect\w*|continue(?:s)?\s+to\s+serve\s+as|(?:will\s+)?remain(?:s)?\s+(?:as\s+)?(?:a\s+|an\s+)?(?=director|chair|member)|re[\s\-]?appoint\w*|re[\s\-]?nominat\w*|incumbent)\b")
# 1.1: "Kelly replaces Mr. Ryan Cheung as the CFO", "succeeding Hugh Maddin", "upon the resignation of Barry Hartley"
_RE_SUCCEEDS = re.compile(
    r"(?i)\b(?:succeed(?:s|ed|ing)?|replac(?:e|es|ed|ing)|in\s+place\s+of|tak(?:es|ing)\s+over\s+from"
    r"|upon\s+the\s+(?:resignation|retirement|departure)\s+of|following\s+the\s+(?:resignation|retirement|departure)\s+of)"
    r"[\s,]+(?!by\b)(?:the\s+(?:late|outgoing|retiring|former)\s+)?(?:(?:mr|mrs|ms|dr)\.?\s+)?")
# the release is about a change, but the sentence is not an announcement of one
_RE_NOT_A_CHANGE = re.compile(
    r"(?i)\b(?:stock\s+options?|option\s+grant|restricted\s+share\s+units?|\bRSUs?\b|\bDSUs?\b|deferred\s+share\s+units?"
    r"|grant(?:s|ed|ing)?\s+(?:of\s+)?(?:\d[\d,]*\s+)?(?:incentive\s+)?(?:stock\s+)?options"
    r"|will\s+be\s+(?:proposed|nominated)\s+for\s+election|(?<!not\s)(?<!not\sbe\s)standing\s+for\s+(?:re[\s\-]?)?election\s+at"
    r"|annual\s+(?:and\s+special\s+)?(?:general\s+)?meeting\s+of\s+shareholders\s+(?:to\s+be\s+)?held"
    r"|management\s+cease\s+trade|cease\s+trade\s+order|\bMCTO\b"
    r"|financial\s+advis\w*|as\s+(?:its\s+|the\s+)?(?:financial|legal)\s+advis\w*"
    r"|(?:investor|public|media)\s+relations\s+(?:firm|agreement|services|support|provider)"
    r"|communications\s+(?:firm|agreement|services|support|provider)"
    r"|market\s+making|drill(?:ing)?\s+contractor"
    r"|receipt\s+of\s+(?:the\s+)?(?:director\s+)?nominations?|nomination\s+notice|shareholder\s+requisition"
    r"|resignation\s+offer|offer\s+to\s+resign|declined\s+to\s+accept"
    r"|change\s+of\s+director'?s\s+interest|appendix\s+3y|director'?s\s+interest\s+notice"
    r"|qualified\s+person\s+(?:as\s+)?defined|\bNI\s+43[\s\-]101"
    r"|board(?:\s+of\s+directors)?\s+(?:now\s+|will\s+now\s+)?(?:consists|comprises|is\s+(?:now\s+)?(?:comprised|composed|made\s+up))\s+of"
    r"|(?:nomination\s+and\s+)?election\s+of\s+(?:the\s+)?(?:board|directors)|slate\s+of\s+(?:directors|nominees)|nominees?(?!\s+(?:of|to)\b)|(?:being|been|are|is)\s+proposed\s+(?:to\s+join|for\s+(?:election|appointment)))\b")
# an appointment stated without a role: "appoints Jane Doe", "Jane Doe joins the company"
_RE_AND_OTHER = re.compile(r"(?i)[,;]?\s*\b(?:and|&)\s+(?:also\s+)?(?:grants?|issues?|closes?|announces?|approves?"
                           r"|reports?|provides?|defers?|completes?|acquires?|updates?|launches?|commences?|files?)\b")
_RE_GAP_NAMES = re.compile("(?:[\\s,&]|\\band\\b|\\bhave\\b|\\bhas\\b"
                          r"|\bhad\b|\bboth\b|\beach\b|\bwill\b|\bwere\b|\bwas\b|\bare\b|\bis\b|\balso\b"
                          "|\\brespectively\\b|(?=(?P<gn>[A-Z][\\w.'\\u2019\\-]*))(?P=gn)){0,14}")
_RE_DIRECT = re.compile(r"(?i)\b(?:appoint\w*|names?|named|welcom\w*|joins?|joined|elect\w*|resign\w*|retir\w*"
                        r"|depart\w*|steps?\s+down|nominat(?:es|ed|ion|ions)\b|pass(?:es|ed|ing)\b|tribute|retained\s+as"
                        r"|agreed?\s+to\s+(?:act|serve|join)|terminat\w*|role\s+(?:will\s+be|has\s+been|was)\s+assumed\s+by)\b")
_RE_QUOTE_LEAD = re.compile(r"(?i)\b(?:said|says|stated|commented|comments|added|noted|concluded|"
                            r"continued|continues|remarked|explained|observed|emphasi[sz]ed|according\s+to)\b")
# "... ," said John Smith, CEO  -- the attribution sits immediately in front of the name
# 1.1.1: more speech verbs ("remarks", "explains", "highlighted"), and a PDF line break may sit anywhere in the
# attribution ("Terry Harbort\n, President & CEO of Talisker stated")
_SPEECH = (r"said|says|stated|states|commented|comments|added|adds|noted|notes|concluded|continued|continues|remarked|"
           r"remarks|explained|explains|observed|observes|emphasi[sz]ed|emphasi[sz]es|elaborated|summari[sz]ed|echoed|"
           r"stating|commenting")
_RE_QUOTE_BEFORE = re.compile(r"(?i)\b(?:" + _SPEECH + r"|according\s+to)\W{0,4}"
                              r"(?:(?:mr|mrs|ms|dr|prof)\.?\s+)?\Z")
# Chad Williams, Executive Chairman of Honey Badger, commented "..."  -- and sometimes behind it
_ABBR_DOT = r"(?:(?<=Inc)|(?<=Corp)|(?<=Ltd)|(?<=\bCo)|(?<=\bJr)|(?<=\bSr)|(?<=\bMr)|(?<=\bMs)|(?<=\bDr)|(?<=\b[A-Z]))\."
_RE_QUOTE_AFTER = re.compile(r"(?i)^(?:[^.!?\n]|\n(?!\n)|\.(?=[A-Za-z,]))(?:[^.!?\n]|\n(?!\n)|\.(?=[A-Za-z,])|"
                             + _ABBR_DOT + r"(?=\s)){0,110}?\b(?:" + _SPEECH + r")\b(?!\s+(?:to|as)\b)")   # not "added to the Board"


_RE_QUOTE_BEFORE_TITLE = re.compile(r"(?i)\b(?:" + _SPEECH + r")"
                                    "(?:[^.!?\\n\u201c\u201d\"]|\\n(?!\\n)){1,60}$")
# 1.1.1: "Executive Co-Chair Robert Friedland and President Marna Cloete announce today the appointment of ...",
# "Kenneth E. MacNeill, President and CEO of Star Diamond Corporation is pleased to confirm": the announcer
# (FIX3: but "X, Vice President and COO has announced his retirement" announces his own change)
_RE_ANNOUNCER_AFTER = re.compile(r"(?i)^(?:,[^.;\n]{0,90}?,?)?(?:\s+and\s+(?:[A-Z][\w.'\-]*\s+){1,6})?\s+"
                                 r"(?:(?:today|also|jointly)\s+)?(?:(?:announces?|announced)(?!\s+(?:his|her|their)\s+(?:retirement|"
                                 r"resignation|departure|decision|intention))|(?:is|are)\s+(?:very\s+)?"
                                 r"(?:pleased|delighted|happy|excited|proud)|wish(?:es)?\s+to\s+announce)\b")


# FIX5: "Co-Chairman John Smith and President Jane Doe also are very pleased to announce" (the second name's
# last word is followed by the verb), and the press contact ("For further information, please contact: X")
_RE_ANNOUNCERS_AFTER = re.compile(r"(?i)^(?:,[^.;\n]{0,90}?,?)?\s+and\s+(?:[A-Z][\w.'\-]*\s+){0,5}[A-Z][\w.'\-]*\s+"
                                  r"(?:(?:today|also|jointly)\s+)?(?:announce|(?:is|are)\s+(?:very\s+)?"
                                  r"(?:pleased|delighted|happy|excited|proud)|wish\s+to\s+announce)\b")
_RE_CONTACT_BEFORE = re.compile(r"(?i)\b(?:for\s+(?:further|more|additional)\s+information|media\s+contact|investor\s+contact|"
                                r"please\s+contact|contact\s+information)\b[^\n]{0,40}\n?[^\n]{0,10}\Z")


def _is_attribution(text: str, ns: int, ne: int) -> bool:
    """True when this mention of a person only introduces a quotation (or announces someone else's change)."""
    if _RE_ANNOUNCER_AFTER.match(text[ne:ne + 160]):
        return True                                           # 1.1.1: the executive announcing, not the appointee
    if (_RE_ANNOUNCERS_AFTER.match(text[ne:ne + 160]) or _RE_CONTACT_BEFORE.search(text[max(0, ns - 90):ns])):
        return True
    lead = text[max(0, ns - 70):ns]
    if _RE_QUOTE_BEFORE.search(lead[-24:]):
        return True
    m = _RE_QUOTE_BEFORE_TITLE.search(lead)
    if m and not _RE_DIRECT.search(lead[m.end():]):
        return True                                           # 1.1: "commented Corcel CEO, Jon Ward"
    m = _RE_QUOTE_AFTER.search(text[ne:ne + 130])
    near = re.split(r"\n\s*\n|(?<!\bMr)(?<!\bMs)(?<!\bMrs)(?<!\bDr)[.!?]\s", lead[-40:])[-1]   # 1.1: not the headline
    # above ("Power Appoints Mark"); FIX3: "we are pleased to welcome Ms. X and Ms. Y to the board," said ...
    if m and not _RE_DIRECT.search(text[ne:ne + m.end()]) and not _RE_DIRECT.search(near):
        return True
    return False


# a full stop that really ends a sentence: not the one in "Dr.", "Inc.", "U.S." or an initial
_RE_SENT_END = re.compile(r"(?<![A-Z])(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)(?<!\bSt)(?<!\bJr)(?<!\bSr)"
                          r"(?<!\bInc)(?<!\bCorp)(?<!\bLtd)(?<!\bNo)(?<!\bvs)(?<!\bApprox)(?<!\bapprox)"
                          r"(?<!\bHon)(?<!\bGen)(?<!\bSen)(?<!\bRev)(?<!\bCol)(?<!\bCapt)(?<!\bProf)"
                          r"(?<!\bMme)(?<!\bMessrs)(?<!\bPh)(?<!\bEsq)(?<!\bAve)(?<!\bMt)(?<!\bIng)(?<!\bLic)(?<!\bMM)"
                          '[.!?](?=[\\s\\n])|;|\\n\\n|(?<=[.!?:\\u201d"])(?<!\\bCorp\\.)(?<!\\bInc\\.)(?<!\\bLtd\\.)(?<!\\bMr\\.)'
                          '(?<!\\bMs\\.)(?<!\\bDr\\.)(?<!\\bCo\\.)(?<!\\b[A-Z]\\.)\\n'   # 1.1.1: "Filo Corp.\\n("Filo"), will be"
                          "|\\n(?=[\\u2022\\u25cf*])")


def _clause(text: str, a: int, b: int, back: int = 280, fwd: int = 420):
    """The sentence-bounded stretch of text around [a, b)."""
    lo = max(0, a - back)
    for m in _RE_SENT_END.finditer(text, lo, a):
        lo = m.end()
    hi = min(len(text), b + fwd)
    m = _RE_SENT_END.search(text, b, hi)
    if m:
        hi = m.start()
    while lo < len(text) and text[lo] in " \n\t":
        lo += 1
    return text[lo:hi], lo


# ------------------------------------------------------------------ dates
_MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december"
           "|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
_MONTH_NUM = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_RE_EFFECTIVE = re.compile(
    r"(?i)\b(?:effective|with\s+effect\s+from|commencing|as\s+of|beginning)\s+(?:as\s+of\s+|on\s+|from\s+)?"
    r"\b(" + _MONTHS + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)")


def effective_date(clause: str):
    m = _RE_EFFECTIVE.search(clause)
    if not m:
        return None
    mon = _MONTH_NUM.get(m.group(1).lower()[:3])
    try:
        return date(int(m.group(3)), mon, int(m.group(2))).isoformat() if mon else None
    except ValueError:
        return None


_RE_INTERIM = re.compile(r"(?i)\b(?:interim|acting)\b")

# FIX5 ---------------------------------------------------------------- the date a change takes effect
# the release's own date: the dateline at the top of the body ("TORONTO, April 29, 2024 -", "(Newsfile Corp. - July
# 10, 2024)", "31 July 2019"), not a date the opening sentence talks about ("held December 14, 2021")
_RE_DATELINE = re.compile(r"(?i)(?<![\w,])(?:(" + _MONTHS + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*((?:19|20)\d\d)"
                          r"|(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MONTHS + r")\.?,?\s+((?:19|20)\d\d))\b")
_RE_DATE_LEAD = re.compile(r"(?i)\b(?:on|held|ended|ending|dated|until|since|from|before|after|by|of|to|through|at|as|"
                           r"effective|between|and|in|during|than|for)\s*\Z")
# "effective immediately", "with immediate effect", "as of today's date", "effective as of the date herein"
_RE_NOW = re.compile(r"(?i)\b(?:effective[\s,]+(?:as\s+(?:of|at)\s+|from\s+)?(?:immediately|today|forthwith|"
                     r"the\s+date\s+(?:hereof|herein|of\s+this\s+(?:news\s+|press\s+)?release))|with\s+immediate\s+effect|"
                     r"immediately\s+effective|as\s+(?:of|at)\s+(?:today|the\s+date\s+(?:hereof|herein)))\b")

# a dateline whose year is behind the text's own "upcoming 2025 shareholder meeting" is a typo, not the release's date
_RE_UPCOMING_YEAR = re.compile(r"(?i)\b(?:upcoming|forthcoming)\s+((?:19|20)\d\d)\b")


# a page that carries several releases has a wire dateline before each ("--(Newsfile Corp. - April 2, 2026)",
# "Sept. 3, 2025 /CNW/", "July 13, 2021 (GLOBE NEWSWIRE)", "/ ACCESS Newswire / September 15, 2026"): the change takes
# the date of the release it is in
_RE_WIRE = re.compile(r"(?i)(?:newsfile\s+corp\.?\s*-\s*|access\s*(?:wire|newswire)\s*/\s*|globe\s*newswire\)?\s*-*\s*)\Z")
_RE_WIRE_AFTER = re.compile(r"(?i)^\s*(?:/\s*cnw\s*/|/\s*prnewswire\s*/|\(\s*globe\s*newswire\s*\)|-+\s*\(?\s*(?:globe\s*newswire|business\s*wire))")


def _dateline(text, head_len, at=None):
    first = None
    for m in _RE_DATELINE.finditer(text, head_len, head_len + 600):
        if _RE_DATE_LEAD.search(text[max(head_len, m.start() - 12):m.start()]):
            continue
        first = m
        break
    if first is not None and at is not None:
        for m in _RE_DATELINE.finditer(text, first.end(), at):
            if _RE_WIRE.search(text[max(0, m.start() - 30):m.start()]) or _RE_WIRE_AFTER.match(text[m.end():m.end() + 30]):
                first = m
    if first is None:
        return None
    m = first
    mon, day, yr = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(5), m.group(4), m.group(6))
    if any(int(y) > int(yr) for y in _RE_UPCOMING_YEAR.findall(text)):
        return None                                   # "TORONTO, April 29, 2024" over "our upcoming 2025 meeting"
    try:
        return date(int(yr), _MONTH_NUM[mon.lower()[:3]], int(day)).isoformat()
    except (KeyError, ValueError):
        return None


def _dates(text, head_len, found):
    """A change with no date of its own takes the date of the release it is in when its sentence says it is effective
    now ("effective immediately", "with immediate effect", "as of today's date"): the labels date it so."""
    for f in found:
        ns = f.get("_pos")
        if f["effective_date"] or ns is None or ns < head_len:
            continue
        cl, _b = _clause(text, ns, f.get("_ne") or ns)
        if _RE_NOW.search(cl):
            f["effective_date"] = _dateline(text, head_len, ns)




# ------------------------------------------------------------------ the analysis
_RE_ASIDE = re.compile(r"(?i)\b(?:former(?:ly)?|past|previously|prior(?:\s+to)?|ex|until|who\s+(?:was|served|as)|"
                       r"retiring|outgoing|(?:remains?|will\s+(?:remain|continue))(?:\s+(?:his|her|their|to\s+be)?\s*\w+){0,2}\s+(?:on\b|as\b)|"
                       r"continues?\s+(?:to\s+serve\s+)?as)\b")
# "Stephen Brohman, CPA, CA, the Company's Chief Financial Officer, has been appointed as Corporate
# Secretary": the title inside the commas is the job he already holds, and the change comes after it.
_RE_ASIDE_APPOS = re.compile(r"(?i)^[\s,]*(?:[A-Z]\.?[A-Za-z.]{0,5},\s*){0,3}"
                             r"(?:the\s+(?:company|corporation|firm)'?s?|currently|current|incoming|outgoing|"
                             r"who\s+(?:is|was|has|serves|served)|a\s+(?:current|long|distinguished|founding))\b")


_RE_ROLE_JOIN = re.compile(r"(?i)\s*(?:,\s*and|,|and|&|/)\s*(?:a|an|the)?\s*")
_RE_ROLE_COMMA = re.compile(r",")
# FIX5: "President and CEO as well as Director", "as Chief Executive Officer and as a director", and a title's own
# abbreviation in brackets before the next one ("Chief Executive Officer ("CEO") and a Director")
_RE_ROLE_JOIN_AS = re.compile(r"(?i)\s*(?:,\s*)?(?:as\s+well\s+as|and\s+(?:also\s+)?as|and(?=\s+(?:a\s+|the\s+)?former\b))\s*(?:a|an|the)?\s*(?:former\s+)?")
_RE_ROLE_ABBR = re.compile("\\s*\\(\\s*[\"\u201c]?\\s*[A-Z][A-Za-z&]{1,5}\\s*[\"\u201d]?\\s*\\)")


def _chain_roles(clause: str, role):
    """Every title this stretch of the clause gives the person, and whether it was written as a list.

    "stepped down as Director, Corporate Secretary, Chief Operating Officer and Interim President" is a
    list of four offices; "appointed President and CEO" is one office with a two-part name. The comma is
    what separates them."""
    chain, at, listed = [role], role[3][1], False
    for _ in range(4):
        ab = _RE_ROLE_ABBR.match(clause, at)
        if ab:
            at = ab.end()
        nxt = R.match(clause, at)
        if nxt is None:
            break
        join = clause[at:nxt[3][0]]
        if not _RE_ROLE_JOIN.fullmatch(join) and not _RE_ROLE_JOIN_AS.fullmatch(join):
            break
        listed = listed or bool(_RE_ROLE_COMMA.search(join))
        chain.append(nxt)
        at = nxt[3][1]
    return chain, listed


_RE_GAP_DATE = re.compile(r"(?i)\beffective\s*,?\s*(?:as\s+of\s+|on\s+|from\s+)?(?:immediately|[A-Z][a-z]{2,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?"
                          r",?\s+\d{4})?|\b(?:respectively|both|each|also)\b")
_RE_SOLE_SUBJECT = re.compile(r"(?i)^\s*,?\s*(?:(?:has|is|was)\b|(?:will|shall)\s+(?:be\s+)?(?:appointed|named|serve|join|become|assume|take)\w*"
                              r"(?:\s+as)?\s+(?:the\s+|its\s+|a\s+|an\s+|our\s+)?(?:new\s+|interim\s+)?(?!directors\b)\S)")


def _blocked(clause, pend, r0, others):
    """1.1.1: a role that comes after someone else's name belongs to that person ("... Nick Tintor and Dino Titaro,
    with Mr. David Anderson appointed as Chairman and CEO"; "..., and Mr. Claude Dufresne will be appointed Chief
    Executive Officer"), unless the names are one list that shares it ("appoints A, B and C as directors")."""
    between = [(a, b) for a, b, same in others if pend <= a and b <= r0 and not (same and a < pend + 12)]
    if not between:                                       # (not the same person's defined name, ' ("Mr. Zhang")')
        return False
    a, b = max(between)
    gap = re.sub(r"^[^()]*\)", " ", _RE_GAP_DATE.sub(" ", clause[pend:a]))   # "(Sandspring, Macquarie) and"
    if not _RE_LIST_GAP.fullmatch(gap):
        return True
    return bool(_RE_SOLE_SUBJECT.match(re.sub(r"^[^()]*\)", " ", clause[b:r0 + 1])))


def _roles_for(clause: str, pstart: int, pend: int, issuer=None, others=()):
    """The roles that belong to the person at [pstart, pend) in this clause: one entry per row.

    A role inside a "formerly chief geologist at Barrick" aside, or inside the commas of "Jane Doe, the
    Company's CFO, has been appointed Corporate Secretary", belongs to the job she already had, not to
    the change being announced, so the search steps over it and keeps looking.  1.1.1: so does a role held
    at another company ("Chief Operating Officer, Grove Corporate Services", "CEO of the Kamoa Copper Joint
    Venture")."""
    at = pend
    aside = False
    for _ in range(4):
        after = R.match(clause, at)
        if after is None:
            break
        gap = clause[at:after[3][0]]
        if _RE_ASIDE.search(gap) or (at == pend and _RE_ASIDE_APPOS.match(gap)) \
                or _other_org(clause, after[3][1], issuer) or _honorary(clause, after[3][1]) \
                or (at == pend and re.fullmatch(r"\s*,\s*(?:the\s+)?(?:current\s+|existing\s+|sitting\s+)?", gap)
                    and re.match(r"[^,;.]{0,60},\s*as\s+", clause[after[3][1]:])) \
                or (aside and re.fullmatch(r"(?i)\s*(?:of\s+directors\s+)?as\s+(?:a\s+|an\s+|the\s+)?", gap)):
            at = after[3][1]                                  # step over "formerly chief geologist at X"
            aside = bool(re.search(r"(?i)\b(?:remains?|continue)\s+on(?:\s+the)?\s*$", gap))
            continue                                          # 1.1.1: "remains on the board as a director"
        aside = False
        if any(0 <= a - after[3][1] <= 12 for a, _b, _s in others) and re.match(r"\s*,", clause[after[3][1]:]) \
                and not re.search(r"(?i)\b(?:as|to)\b", gap):
            break                                             # 1.1.1: "a new VP Corporate Development, Mr. Tyron Rees"
        if after[3][0] - pend <= 130 and not _blocked(clause, pend, after[3][0], others):
            return _resolve(*_chain_roles(clause, after))
        break
    head = R.match(clause[:pstart])
    if head is not None and pstart - head[3][1] > 25 and head[3][0] < pstart - 120:
        # FIX3: near the name, not the first title of a long lead ("Board ... announces the resignation of board member,
        # George Heras"), unless that title is the one a new holder takes ("hand-over to Noram's new CEO, Greg McCunn")
        head = R.match(clause[:pstart], pstart - 120)
        if head is not None and (re.search(r"(?i)\b(?:new|incoming|successor)\s+\Z", clause[max(0, head[3][0] - 12):head[3][0]])
                                 or re.search(r"(?i)\b(?:of|at|for|with)\s+(?:the\s+)?\Z", clause[head[3][1]:pstart])):
            head = None                                   # (nor "Chairman and CEO of High Tide": the company)
    if head is not None and pstart - head[3][1] <= 25 and not _RE_ASIDE.search(clause[head[3][1]:pstart]) \
            and not any(head[3][1] <= a < pstart and not same for a, _b, same in others) \
            and not _other_org(clause, head[3][1], issuer):
        return [_row(head)]
    after = R.match(clause, pend)
    if after is not None and after[3][0] - pend <= 200 and not _RE_ASIDE.search(clause[pend:after[3][0]]) \
            and not _other_org(clause, after[3][1], issuer) and not _blocked(clause, pend, after[3][0], others):
        return [_row(after)]
    return []


# 1.1.1 ---------------------------------------------------------------- whose company is it?
_RE_ROLE_ORG = re.compile(r"^\s*(?:(?:of|at|with|for)\s+(?:the\s+)?((?:[A-Z][\w&'.\-]*[ \n]*){1,6})"
                          r"|,\s*((?:[A-Z][\w&'.\-]*[ \n]+){0,4}(?:Inc|Corp|Corporation|Ltd|Limited|LLC|LLP|PLC|Services|Group|"
                          r"Partners|Capital|Holdings|Consulting|Advisors|Associates|Securities|Bank)\b))")
_RE_ISSUER_AT = re.compile(r"\s*,?\s*\((?:the\s+)?[\"\u201c]|\s*\((?:TSX|CSE|NYSE|ASX|NASDAQ|OTC|TSXV|NEO|LSE|AIM)")


def issuer_words(text: str, head_len: int):
    """The words of the issuer's own name: the company the release defines as "the Company" or prints with its
    ticker, and the first word of the headline."""
    out = set()
    for m in re.finditer(r"((?:[A-Z][\w&'\-]*\.?[ \n]+){1,5})(?=\((?:the\s+)?[\"\u201c]|\((?:TSX|CSE|NYSE|ASX|NASDAQ|OTC))",
                         text[:3000]):
        out.update(re.sub(r"[^a-z]", "", w.lower()) for w in m.group(1).split())
    for m in re.finditer(r"(?i)\(\s*(?:the\s+)?[\"\u201c]\s*(?:company|corporation)\s*[\"\u201d]\s+or\s+[\"\u201c]\s*([A-Z][\w\-]+)",
                         text[:3000]):
        out.add(m.group(1).lower())                       # ("the Company" or "Teako")
    for m in re.finditer(r"\(\s*[\"\u201c]\s*([A-Z][\w\-]+)\s*[\"\u201d]\s+or\s+the\s+[\"\u201c]", text[:3000]):
        out.add(m.group(1).lower())                       # ("Teako" or the "Company")
    first = re.match(r"\s*([A-Z][\w\-]+)", text[:head_len])
    if first:
        out.add(re.sub(r"[^a-z]", "", first.group(1).lower()))
    return {w for w in out if len(w) >= 3 and not _RE_CORP_WORD.fullmatch(w)}


def _other_org(clause, rend, issuer):
    """True when the role ending at `rend` is followed by the name of a company other than the issuer."""
    if not issuer:
        return False
    m = _RE_ROLE_ORG.match(clause[rend:rend + 90])
    if not m:
        return False
    run = m.group(1) or m.group(2)
    if not (_RE_CORP_WORD.search(run) or re.search(r"(?i)\bjoint\s+venture\b", run)):
        return False
    toks = [re.sub(r"[^a-z]", "", re.sub(r"['\u2019]s$", "", w).lower()) for w in run.split()]
    if toks and toks[0] in ("company", "corporation", "board", "issuer", "group", "resulting"):
        return False
    return not any(t in issuer for t in toks if len(t) >= 3 and not _RE_CORP_WORD.fullmatch(t))


def _resolve(chain, listed):
    """One row per office. Two titles joined by a bare "and" are one office when they sit at the same
    level of the same part of the company -- President and CEO -- and the senior one when they nest,
    because a Chair of the Board is already a director."""
    if len(chain) == 1:
        return [_row(chain[0])]
    if listed and chain[0][1] == "Vice President" and chain[0][2] == "management":
        # 1.1.1: "Senior Vice President, General Counsel and Corporate Secretary" is one executive title: a vice
        # president with no department of his own takes the titles listed after him as its department
        k = 1
        while k < len(chain) and chain[k][2] == "management":
            k += 1
        if k > 1:
            end = chain[k - 1][3][1]
            printed = R.tidy(chain[0][0] + ", " + ", ".join(c[0] for c in chain[1:k - 1]) + (", " if k > 2 else "")
                             + chain[k - 1][0]) if k > 2 else chain[0][0] + ", " + chain[1][0]
            return [(printed, chain[0][1], "management", end)] + [_row(c) for c in chain[k:]]
    if listed:
        # 1.1.1: "President, CEO and Director" is two offices: the compound title President and CEO, and the board seat
        rows, i = [], 0
        while i < len(chain):
            a = chain[i]
            b = chain[i + 1] if i + 1 < len(chain) else None
            pair = b is not None and a[2] == b[2] == "management" and {_is_president(a[1]), _is_president(b[1])} == {True, False} \
                and any(re.match(r"(?i)chief\s+(?:executive|operating)", x[1]) for x in (a, b)) \
                and not any(re.search(r"(?i)\b(?:interim|acting)\b", x[0]) for x in (a, b))   # an interim post is its own office
            if pair:
                printed = a[0] + " and " + b[0]
                rows.append((printed, R.canonical(printed)[0] or a[1], a[2], b[3][1]))
                i += 2
                continue
            rows.append(_row(a))
            i += 1
        return rows
    rows, used = [], set()
    for i, c in enumerate(chain):
        if i in used:
            continue
        mate = next((j for j in range(i + 1, len(chain))
                     if j not in used and chain[j][2] == c[2] and abs(R.rank(chain[j][1]) - R.rank(c[1])) <= 10), None)
        if mate is None:
            same = [j for j in range(i + 1, len(chain)) if j not in used and chain[j][2] == c[2]]
            if same:                                          # they nest: keep the senior title only
                best = max([i] + same, key=lambda j: R.rank(chain[j][1]))
                used.update(same + [i])
                rows.append(_row(chain[best]))
                continue
            rows.append(_row(c))
            continue
        used.add(mate)
        a, b = chain[i], chain[mate]
        printed = a[0] + " and " + b[0]
        rows.append((printed, R.canonical(printed)[0] or a[1], a[2], b[3][1]))
    return rows


def _is_president(canon):
    return bool(re.match(r"(?i)president\b", canon or ""))


_RE_BODY_ONLY = re.compile(r"(?i)^(?:the\s+)?(?:board(?:\s+of\s+directors)?|directors?)$")


def _honorary(clause, rend):
    """1.1.1: "Chair Emeritus", "Director Emeritus": an honorary title, not a position (the labels agree)."""
    return bool(re.match(r"(?i)\s+emerit(?:us|a)\b", clause[rend:rend + 12]))


def _row(m):
    """(printed, canon, scope, where it ends in the clause)."""
    printed = m[0]
    if m[1] == "Director" and _RE_BODY_ONLY.match(printed or ""):
        printed = "Director"                              # 1.1: "to the Board of Directors" -> Director
    elif m[1] == "Advisory Board" and re.fullmatch(r"(?i)advisory\s+(?:board|committee|council)", printed or ""):
        printed = "Advisory Board Member"
    return (printed, m[1], m[2], m[3][1])


def _action_of(word: str, verb: str):
    """1.1: six actions. The word that announced the change decides which (Justin, 2026-09-21)."""
    w = (word or "").lower()
    if verb == "depart":
        if re.match(r"resign|steps?\s|stepped\s|stepping\s|relinquish", w):
            return "resigned"
        if w.startswith("retir"):
            return "retired"
        return "departed"
    if verb == "change":
        return "promoted" if re.match(r"promot|elevat", w) else "changed"
    if verb == "none":
        return None
    return "appointed"


def _name_words(name: str):
    t = unicodedata.normalize("NFKD", name or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [w for w in re.sub(r"[^a-z ]", " ", t.lower()).split() if w]


def same_person(a: str, b: str) -> bool:
    """One person, however the release spelled them: PJ Murphy is Peter Jonathan (PJ) Murphy, and
    Kevin Keough is Kevin M. Keough. The surname has to agree and one name has to sit inside the other,
    so two directors who share a surname stay two people."""
    wa, wb = _name_words(a), _name_words(b)
    if not wa or not wb:
        return False
    if wa == wb:
        return True
    la = [w for w in wa if len(w) > 1]
    lb = [w for w in wb if len(w) > 1]
    if la[-1] == lb[-1]:
        if len(wa[0]) >= 3 and len(wb[0]) >= 3 and (wa[0].startswith(wb[0]) or wb[0].startswith(wa[0])) \
                and len(wa) == len(wb):
            return True                                       # 1.1.1: "Tim Heenan" is "Timothy Heenan"
        return set(wa) <= set(wb) or set(wb) <= set(wa)
    # "Daniel Muniz" for Daniel Muniz Quintanilla: the given name agrees and the short form is contained
    return wa[0] == wb[0] and (set(wa) < set(wb) or set(wb) < set(wa))


def _spelled_twice(a, b):
    """FIX5: one given name spelled two ways beside the same surname ("Jesse" / "Jessy"): same length, one letter apart."""
    wa, wb = _name_words(a), _name_words(b)
    if len(wa) != 2 or len(wb) != 2 or wa[1] != wb[1] or wa[0] == wb[0] or len(wa[0]) != len(wb[0]) or len(wa[0]) < 4:
        return False
    return sum(x != y for x, y in zip(wa[0], wb[0])) == 1 and wa[0][0] == wb[0][0]


def _dedupe(changes):
    """One row per person per scope. A person named in the headline and again in the body is one change:
    the body is the authority on the title and on what happened, the headline only summarises it, so
    "KEN ARMSTRONG APPOINTED CHAIRMAN" plus "Ken Armstrong transitioning to Chair of the Board" is one
    row that says he moved to Chair of the Board."""
    out = []
    for c in changes:
        same = None
        for o in out:
            if c["person"] and o["person"] and _spelled_twice(o["person"], c["person"]) \
                    and o["action"] == c["action"] and o["role"] and c["role"] and R.same_role(o["role"], c["role"]):
                c["person"] = o["person"]                     # FIX5: "Jesse Doe" in the headline, "Jessy Doe" below
            if c["person"] and o["person"] and same_person(o["person"], c["person"]) \
                    and (not o["role"] or not c["role"] or R.same_role(o["role"], c["role"])
                         or (o["scope"] == c["scope"]
                             and not (o["_list"] is not None and o["_list"] == c["_list"]))):
                same = o
                break
            if not c["person"] and not o["person"] and o["action"] == c["action"] \
                    and o["role"] and c["role"] and R.same_role(o["role"], c["role"]):
                same = o
                break
        if same is not None:
            if len(_name_words(c["person"] or "")) > len(_name_words(same["person"] or "")):
                same["person"] = c["person"]
            body = c["_src"] == "body" and same["_src"] == "head"
            if c["role"] and (body or not same["role"]
                              or (c["_src"] == same["_src"] and R.rank(c["role_canon"]) > R.rank(same["role_canon"]))):
                same["role"], same["role_canon"], same["scope"] = c["role"], c["role_canon"], c["scope"]
                same["action"] = c["action"]                  # the wording that named the title also said
                same["_list"] = c["_list"]                    # what happened to it
            if body:
                same["action"] = c["action"]
                same["_src"] = "body"
            elif same["action"] == "departed" and c["action"] in ("resigned", "retired"):
                same["action"] = c["action"]                  # 1.1.1: the more precise wording of the same exit
            if not same["effective_date"] and c["effective_date"]:
                same["effective_date"] = c["effective_date"]
            same["interim"] = same["interim"] or c["interim"]
            continue
        if c["person"] is None and any(o["role"] and c["role"] and R.same_role(o["role"], c["role"])
                                       and o["action"] == c["action"] for o in out):
            continue
        out.append(c)
    # a role-only row is noise once the same role is filled by a named person
    out = [c for c in out if c["person"] or not any(
        o["person"] and o["role"] and c["role"] and R.same_role(o["role"], c["role"]) for o in out)]
    return out


def _verbs(text):
    """[(start, end, action)] for every action word in the text, earliest first."""
    out = []
    re_spans = [(m.start(), m.end()) for m in _RE_REELECT.finditer(text)]
    year = _release_year(text)
    for rx, verb in ((_RE_APPOINT, "appoint"), (_RE_DEPART, "depart"), (_RE_CHANGE, "change")):
        for m in rx.finditer(text):
            if any(a <= m.start() < b for a, b in re_spans):
                continue                                  # "re-electing" is not "electing"
            if _not_news(text, m.start(), m.end(), year):
                re_spans.append((m.start(), m.end()))     # 1.1.1: claims the names beside it, announces nothing
                continue
            out.append((m.start(), m.end(), _action_of(m.group(0), verb)))
    out.extend((a, b, None) for a, b in re_spans)         # claims the names beside it, announces nothing
    out.sort(key=lambda v: (v[0], v[1]))
    return out


# 1.1.1 ---------------------------------------------------------------- action words that announce nothing
# a sentence about someone's career rather than this release's change
_RE_BIO_CONTEXT = re.compile(r"(?i)\b(?:currently|previously|formerly|prior\s+to|served|serves|has\s+held|held|career|"
                             r"experience|years|brings|holds|worked|spent|was\s+(?:the|a|an)|is\s+(?:the|a|an))\b")
_RE_FORMER_APPOS = re.compile(r"(?i),\s*(?:the\s+|its\s+|our\s+)?(?:company['\u2019]s\s+)?(?:former|outgoing|departing|retiring)\s+")
_RE_ROLE_OBJECT = re.compile(r"(?i)\s*(?:of\s+|as\s+|to\s+)?(?:(?:a|an|the|its|our|their|his|her|new|interim|acting|permanent|"
                             r"additional|two|three|incoming|senior|independent)\s+)*")
_RE_REPLACED_LEAD = re.compile(r"(?i)\b(?:replac(?:e|es|ed|ing)|succeed(?:s|ed|ing)?|in\s+place\s+of|tak(?:es|ing)\s+over\s+from)"
                               r"[\s,]+(?:the\s+(?:late|outgoing|retiring|former)\s+)?(?:(?:mr|mrs|ms|dr)\.?\s+)?\Z")
# "his appointment", "Mr. Campbell's appointment": the action noun already has its person
_RE_OWNED_NOUN = re.compile(r"(?i)(?:['\u2019]s|\b(?:his|her|their))\s+\Z")
# the person after "chaired by", "nominated by", "signed by" acts; the one after "replaced by" or "joined by" is the change
_RE_BY_AGENT = re.compile(r"(?i)(?<!replaced)(?<!succeeded)(?<!joined)(?<!followed)(?<!filled)(?<!assumed)(?<!taken\sover)"
                          r"(?<!taken)\s+by\s+"                 # FIX3: "the role will be assumed by Joe Graziano"
                          r"(?:(?:mr|ms|mrs|dr|prof)\.?\s+)?\Z")
# board committees: joining or chairing one is not a change of position (the advisory kind is: see the guide)
_RE_COMMITTEE_OBJ = re.compile(r"(?i)^(?:(?!\bboard\b|\bdirectors?\b)(?:[^.;\n]|\n(?!\n))){0,100}?"
                               r"(?<!advisory\s)(?<!technical\s)(?<!scientific\s)(?<!advisor\s)(?<!advisors\s)(?<!technology\s)"
                               r"(?<!management\s)(?<!executive\s)\bcommittees?\b")   # FIX3: advisory and management committees count
_RE_YEAR_LINE = re.compile(r"(?i)\b(?:" + _MONTHS + r")\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+((?:19|20)\d\d)\b")


def _release_year(text):
    """The year of the dateline, so that "joined Haywood in 2003" can be told from "will retire in 2026"."""
    m = _RE_YEAR_LINE.search(text[:2500])
    return int(m.group(1)) if m else None


# "the new name", "name change", "the Company's name and symbol": the noun, not the verb "names X as CEO"
_RE_NAME_NOUN_BEFORE = re.compile(r"(?i)(?:\b(?:new|the|its|our|a|corporate|trading|his|her|their|same|brand|legal|"
                                  r"domain|former|previous|full|company'?s?|corporation'?s?|issuer'?s?|whose|user|file|"
                                  r"project|property)|['\u2019]s)\s+\Z")
_RE_NAME_NOUN_AFTER = re.compile(r"(?i)^\s*(?:changes?\b|of\b|and\b|is\b|was\b|will\b|under\b|in\b|for\b|on\b|with\b|"
                                 r"to\s+be\b|has\b|had\b|\"|[,.;:)(])")
# "strengthens the confidence", "strengthening its balance sheet": only a board or a team is strengthened by a hire
_RE_STRENGTH_OBJ = re.compile(r"(?i)^\s+(?:(?:its|the|our|their)\s+)?(?:[A-Z][\w'\-]*\s+|further\s+|senior\s+|executive\s+|"
                              r"technical\s+|management\s+|leadership\s+){0,4}(?:board|team|management|leadership|"
                              r"executive|directors|advisory|bench|governance|operations\s+and)")
# "join CEO David Stein for a live webinar", "join us at the PDAC booth": an invitation, not a hire
_RE_EVENT = re.compile(r"(?i)\b(?:webinar|webcast|live\s+event|live\s+stream|presentation|panel|conference|fireside|"
                       r"interview|podcast|booth|virtual\s+event|investor\s+event|session|register|registration|"
                       r"q\s?&\s?a|town\s+hall|site\s+visit|tour|call\s+at)\b")
# FIX3: "who was appointed as a director of the Company today": the change this release reports
_RE_TODAY = re.compile(r"(?i)^(?:[^.;\n]|\n(?!\n)){0,110}?\b(?:today|effective\s+(?:immediately|today)|"
                       r"(?:up)?on\s+(?:the\s+)?(?:closing|completion)\b|in\s+connection\s+with\s+the\s+(?:closing|completion))")
# FIX3: the object of "join" is a seat: the board, an advisory body, the company or its team, or "as <title>"
_RE_JOIN_SEAT = re.compile(r"(?i)\s+(?:the\s+|its\s+|our\s+|their\s+|[A-Z][\w&\-]*['\u2019]s\s+)?(?:[A-Z][\w&\-]*\s+){0,3}"
                           r"(?:board\b|advisory\b|technical\s+(?:advisory|committee)|management\s+team|executive\s+team|"
                           r"leadership\s+team|as\s+(?:a\s+|an\s+|the\s+|its\s+)?(?:new\s+)?(?:[A-Z]|director|chief|vice|"
                           r"president|chair|advis|independent|non-executive))")
_RE_WELCOME_OBJ = re.compile(r"(?i)^\s+(?:all\s+)?(?:investors|shareholders|you|everyone|attendees|visitors|questions|participants|"
                             r"the\s+(?:opportunity|news|decision|announcement|support|investment|participation|results?|"
                             r"government|approval|addition\s+of\s+[A-Z][\w&]+\s+(?:Inc|Corp|Ltd|Capital|Group)))")
# biography: "Prior to joining Ivanhoe", "Before retiring, Mr. X was CFO", "Since leaving SOQUEM", "is a retired
# executive", "joined Haywood Securities in 2003"
_RE_BIO_BEFORE = re.compile(r"(?i)(?:\b(?:prior\s+to|before|after|since|until|upon|following|while)\s+(?:his\s+|her\s+|their\s+)?"
                            r"|\bculminat\w+\s+in\s+(?:his|her)\s+)\Z")
_RE_RETIRED_ADJ = re.compile(r"(?i)\b(?:is|was|a|currently|now|semi)[\s\-]+(?:a\s+)?\Z")
_RE_BIO_YEAR = re.compile(r"(?i)^(?:[^.;\n]|\n(?!\n)){0,70}?\b(?:in|since|from|until|between)\s+(?:early\s+|late\s+|mid-?\s?)?"
                          r"((?:19|20)\d\d)\b(?!\s*(?:annual|agm|general))")
# FIX5: "retired from Other Mines Limited in January 2021 as Senior Vice-President" (a month before the year)
_RE_BIO_MONTH_YEAR = re.compile(r"(?i)^(?:[^.;\n]|\n(?!\n)){0,70}?\b(?:in|since|from|until)\s+(?:early\s+|late\s+|mid-?\s?)?"
                                r"(?:" + _MONTHS + r")\.?\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?((?:19|20)\d\d)\b(?!\s*(?:annual|agm|general))")
# "In December 2015, Mr. Hean retired from his position as ..." (the year opens the sentence)
_RE_BIO_YEAR_BEFORE = re.compile(r"(?i)(?:^|[.;]\s|\n\n)\s*(?:in|from|during|since|between)\s+(?:early\s+|late\s+|mid-?\s?)?"
                                 r"(?:(?:" + _MONTHS + r")\.?\s+)?((?:19|20)\d\d)\b(?:[^.;]|(?<=\bM[rs])\.|(?<=\bDr)\.|(?<=Mrs)\.){0,90}\Z")


# an AGM that elects its slate changes nobody: only a director said to be new, or one who leaves, is a change
_RE_MEETING = re.compile(r"(?i)\b(?:annual(?:\s+general)?(?:\s+and\s+special)?\s+meeting|special\s+meeting|AGM|AGSM|"
                         r"shareholders'?\s+meeting|meeting\s+of\s+(?:the\s+)?(?:share|stock)holders)\b")
_RE_NEW_MEMBER = re.compile(r"(?i)\b(?:new|newly|first[\s\-]time|for\s+the\s+first\s+time|join(?:s|ed|ing)?|addition|welcom\w*|"
                            r"replac\w*|succeed\w*|additional|incoming|not\s+previously)\b")
_RE_SLATE_VERB = re.compile(r"(?i)^(?:elect(?:s|ed|ing)?|election|appointing)$")


def _slate(text, vs, ve):
    """"Electing A, B, C and D as directors", "shareholders elected board members A, B ...", "appointing A, B and C
    as directors" among the matters voted at a meeting: the slate, re-elected."""
    if not _RE_SLATE_VERB.match(text[vs:ve]):
        return False
    cl, base = _clause(text, vs, ve, back=200, fwd=300)
    if _RE_NEW_MEMBER.search(cl) or re.search(r"(?i)(?<!or\s)\bre[\s\-]?elect\w*(?!\s+or\s+elect)", cl):
        return False                                      # "re-electing A and B, and electing C": C is new
    if text[vs:ve].lower() == "appointing" and not re.search(r"(?i)\bas\s+directors\b", cl):
        return False
    # FIX3: one person elected to the board or to a post ("shareholders elected Mr. Kenneth Johnson to the Board",
    # "Mr. Derrick Armstrong was elected to the board of directors at the annual general meeting", "the Board members
    # elected Bill McWilliam as the Chairman") is not a slate: a release does not single out a re-elected director
    near = cl[max(0, vs - base - 160):vs - base + 200]
    if len({n for n, _a, _b in people(near)}) == 1 and text[base + len(cl):base + len(cl) + 1] != ";" \
            and not re.search(r"(?i)(?<!board\sof\s)\bdirectors\b|\b(?:nominees|following|slate)\b|[:;]", near):
        return False
    return bool(_RE_MEETING.search(text[:4000]))


# a lender's or investor's right to put someone on the board, or a resolution a shareholder proposes: a possibility,
# not a change ("will be entitled to nominate X for appointment and election as a director", "a requisition ... for
# an ordinary resolution ... to appoint A, B and C to the Board")
_RE_RIGHT_TO = re.compile(r"(?i)\b(?:entitled|right|rights|entitlement)\s+to\s+(?:nominate|appoint|designate|elect)\b")
_RE_PROPOSAL = re.compile(r"(?i)\b(?:requisition\w*|dissident|activist|proxy\s+(?:contest|fight)|concerned\s+shareholders?)\b")
# an appointment to a body outside the company ("has been appointed to the Mining Advisory Council of PNG")
_RE_OUTSIDE_BODY = re.compile(r"(?i)\s*(?:as\s+(?:a\s+)?(?:member|chair\w*)\s+of|to)\s+(?:the\s+|a\s+|an\s+)?(?:[\w'&\-]+\s+){0,6}"
                              r"(?:council|commission|association|chamber|institute|society|authority|agency|federation|"
                              r"foundation|ministry|panel|forum|tribunal|senate|parliament|cabinet|government|university)\b")
# "its recently-appointed Chair, Terry Lyons": the holder of a post, named in passing
_RE_ADJ_APPOINTED = re.compile(r"(?i)(?:\b(?:its|the|our|a|an|his|her|their|company['\u2019]s)\s+|(?:^|[.!?\n\"]\s*))(?:newly|recently)[\s\-]+\Z")
# the object of the action is a firm, or the action is a piece of work ("has appointed Terrane Geoscience Inc. and
# GEMTEC Consulting Engineers ... to lead the investigation", "ILF Group, appointed to complete the study", "the
# appointment of Baker Tilly US, LLP as the independent auditors", "contractors have been appointed to extend ...")
_RE_ORG_OBJECT = re.compile(r"(?:\s+of)?[\s,]*(?:(?:the|a)\s+)?(?:[A-Z][\w&'.\-]*,?\s+){1,5}(?:Inc|Ltd|Limited|Corp|Corporation|LLC|LLP|"
                            r"SpA|S\.?A|GmbH|Pty|Group|Consulting|Consultants|Engineers|Engineering|Geoscience|Geosciences|"
                            r"Partners|Associates|Laboratories|Labs)\b"
                            r"|[^.;\n]{0,70}?\bas\s+(?:the\s+|its\s+)?(?:company['\u2019]s\s+)?(?:new\s+)?(?:independent\s+)?"
                            r"(?:auditors?|contractors?|consultants?|engineers?\s+of\s+record|transfer\s+agent|market[\s\-]maker)\b")
_RE_TASK = re.compile(r"(?i)\s+to\s+(?:complete|conduct|undertake|carry\s+out|perform|prepare|deliver|review|audit|design|build|"
                      r"extend|construct|drill|manage\s+the\s+(?:drill|construction|study|program)|lead\s+the\s+(?:\w+\s+){0,3}"
                      r"(?:investigation|study|program|work|drilling)|assist\s+(?:with|in))\b")


_RE_AFTER_MEETING = re.compile(r"(?i)\b(?:following|after|subsequent\s+to|at\s+a\s+(?:board\s+)?meeting\s+(?:of\s+the\s+board\s+)?"
                               r"(?:held\s+)?(?:after|following))\s+(?:the|its)\s+(?:annual\s+(?:general\s+)?)?(?:meeting|agm|agsm)\b")


def _officer_slate(text, vs, ve):
    """"Following the Meeting, the directors appointed Mr. X as President and CEO, Mr. Y as CFO ...": the board
    re-appointing its officers after an AGM is routine (the labels, and the admission rule, agree)."""
    if not re.match(r"(?i)(?:re[\s\-]?)?appoint", text[vs:ve]):
        return False
    para = text[max(0, text.rfind("\n\n", 0, vs)):vs]
    cl, _b = _clause(text, vs, ve, back=200, fwd=300)
    return bool(_RE_AFTER_MEETING.search(para[-400:])) and not _RE_NEW_MEMBER.search(cl) \
        and not _RE_NEW_MEMBER.search(text[vs:vs + 400])


# FIX5: a line of a meeting's voting results ("Appoint John Smith as director | Votes For Votes Withheld"), or
# the board a meeting elected "for the ensuing year": the slate voted on, not a change
_RE_VOTE_TALLY = re.compile(r"(?i)\bvotes?\s+(?:for|against|withheld|cast)\b|\b(?:for|against)\s+(?:votes\s+)?withheld\b")
_RE_ENSUING = re.compile(r"(?i)\bfor\s+the\s+(?:ensuing|coming|following)\s+year\b|\buntil\s+the\s+next\s+annual\s+(?:general\s+)?meeting\b")


# FIX5: a change the release only recaps (Justin, Oct 2): "As previously announced on January 24, 2023, in connection
# with the appointment of X as Interim CEO", "Earlier this year, the Company promoted X to Project Manager"
_RE_RECAP_LEAD = re.compile(r"(?i)\b(?:as\s+(?:was\s+)?(?:previously|earlier)\s+announced|as\s+announced\s+(?:on|in)\b|"
                            r"previously\s+announced\s+on|earlier\s+(?:this|in\s+the)\s+year|earlier\s+in\s+(?:19|20)\d\d|"
                            r"(?:^|[.;]\s+|\n)(?:last|during\s+the)\s+(?:year|month|quarter))\b")
_RE_RECAP_NOW = re.compile(r"(?i)\b(?:will|shall|effective|today|upon|now|following|subject\s+to)\b")


def _recap(text, vs, ve):
    cl, base = _clause(text, vs, ve, back=220, fwd=160)
    return bool(_RE_RECAP_LEAD.search(cl)) and not _RE_RECAP_NOW.search(cl[vs - base:])


def _vote_item(text, vs, ve):
    line = text[ve:ve + 160].split("\n\n")[0]
    if _RE_VOTE_TALLY.search(line[:110]) and _RE_MEETING.search(text[:4000]):
        return True
    cl, _b = _clause(text, vs, ve, back=200, fwd=200)
    return bool(_RE_ENSUING.search(cl)) and not _RE_NEW_MEMBER.search(cl) and bool(re.search(r"(?i)\bmeeting\b", cl)) \
        and bool(_RE_MEETING.search(text[:4000]))


def _not_news(text, vs, ve, year):
    """True for an action word that does not announce a change of position in this release."""
    word = text[vs:ve].lower()
    before = text[max(0, vs - 40):vs]
    after = text[ve:ve + 120]
    if _slate(text, vs, ve) or _officer_slate(text, vs, ve):
        return True
    if re.match(r"(?i)appoint|elect", word) and _vote_item(text, vs, ve):
        return True
    if _recap(text, vs, ve):
        return True
    cl, _b = _clause(text, vs, ve, back=220, fwd=220)
    if _RE_RIGHT_TO.search(cl):
        return True
    if re.match(r"(?i)appoint|elect|remov|nominat", word) and re.search(r"(?i)\bto\s+\Z", text[max(0, vs - 4):vs]) \
            and (_RE_PROPOSAL.search(cl) or re.search(r"(?i)\bresolutions?\b", cl)):
        return True                                       # "a resolution ... to appoint A, B and C"
    if re.match(r"(?i)appoint|nam|elect|nominat", word) and _RE_OUTSIDE_BODY.match(text, ve) \
            and not re.match(r"(?i)\s*to\s+(?:the\s+|its\s+)?(?:company['\u2019]s\s+)?(?:[\w'&\-]+\s+){0,3}advisory\s+(?:board|council)\s+of\s+the\s+company",
                             text[ve:ve + 80]):
        return True
    if word.startswith("elevat") and not re.match(r"(?i)[^.;\n]{0,50}?\b(?:to|as)\b", after):
        return True                                       # FIX3: "elevated gold values" is an adjective
    if word.startswith("addition") and re.search(r"(?i)\bin\s+\Z", before):
        return True                                       # "In addition to the Orfo Loan"
    if re.match(r"(?i)appoint|engag|retain|hir|select|nam", word) and (_RE_ORG_OBJECT.match(text, ve) or _RE_TASK.match(text, ve)):
        return True                                       # a firm engaged, or someone appointed to do a piece of work
    if re.match(r"(?i)(?:joined|appointed|named|elected)$", word) \
            and re.search(r"(?i)\bwho\s+(?:was\s+|had\s+been\s+|has\s+)?(?:recently\s+|previously\s+)?\Z", before) \
            and not re.search(r"\(\s*who\s+(?:was\s+)?\Z", before) and not _RE_TODAY.match(after):
        return True                                       # (FIX3: not "who was appointed ... today", nor the
                                                          # "(who was appointed Chair)" of a roster of the new board)                                       # "Mr. Lyons, who joined the refreshed Board in August"
    if word == "appointed" and _RE_ADJ_APPOINTED.search(text[max(0, vs - 40):vs]) \
            and not re.match(r"(?i)\s+(?:as|to)\b", text[ve:ve + 5]):
        return True
    if re.match(r"names?$", word):
        if _RE_NAME_NOUN_BEFORE.search(before) or _RE_NAME_NOUN_AFTER.match(after):
            return True
    if word.startswith("strengthen") and not _RE_STRENGTH_OBJ.match(after):
        return True
    if not re.match(r"(?i)resign|retir|step|depart|leav|pass", word) and _RE_COMMITTEE_OBJ.match(after):
        return True                                       # "will also join the Technical Committee", "members of the Audit Committee"
    if word.startswith("join"):
        if re.match(r"(?i)\s+(?:us|me|them)\b", after):
            return True
        cl, _b = _clause(text, vs, ve, back=160, fwd=200)
        if _RE_EVENT.search(cl) and not _RE_JOIN_SEAT.match(after):
            return True                                   # (FIX3: "joins Board of Directors & announces attendance
                                                          # at PDAC": joining a board is news whatever follows)
    if word.startswith("welcom") and _RE_WELCOME_OBJ.match(after):
        return True
    if word.startswith("add") and re.search(r"(?i)(?:[\"\u201d,]\s*|\b(?:he|she|they|who|and)\s+)\Z", before):
        return True                                       # '," added Mr. Larsen' is a quotation
    if _RE_BIO_BEFORE.search(before) and (word.endswith("ing") or re.search(r"(?i)(?:culminat|since|prior)", before[-30:])):
        return True
    if word == "retired" and _RE_RETIRED_ADJ.search(before) and not re.match(r"(?i)\s+(?:as|from)\b", after):
        return True                                       # "is a retired business executive"
    if year:
        m = _RE_BIO_YEAR.match(after)
        if m and int(m.group(1)) < year:
            return True
        m = _RE_BIO_MONTH_YEAR.match(after)
        if m and int(m.group(1)) < year:
            return True
        m = _RE_BIO_YEAR_BEFORE.search(text[max(0, vs - 110):vs])
        if m and int(m.group(1)) < year:
            return True
    return False


# 1.1 ---------------------------------------------------------------- lists, rosters, successors
_RE_LIST_GAP = re.compile("(?:[\\s,;&.]|\\band\\b|\\([^)]{0,40}\\)|[\u201c\u201d\"][^\u201c\u201d\"]{1,15}[\u201c\u201d\"]"
                          "|(?=(?P<ln>[A-Z][\\w.'\u2019\\-]*))(?P=ln))*")
_RE_ROSTER_JOIN = re.compile(r"\s*[,\u2013\u2014\-:]\s*")


def _row_for(nm, ns, ne, action, role, text, cl, head_len, vs=None):
    printed, canon, scope, _rend = role if role else (None, None, None, 0)
    return {"action": action, "person": nm, "role": printed, "role_canon": canon, "scope": scope,
            "effective_date": effective_date(cl), "interim": bool(_RE_INTERIM.search(text[max(0, ns - 80):ne + 90])),
            "_pos": ns, "_src": "head" if ns < head_len else "body", "_list": None, "_ne": ne, "_vs": vs}


_RE_FIRM_OBJECT = re.compile(r"\s*(?:[A-Z][\w&.\-]*\s+){0,4}(?:Partners|Advisors|Advisers|Advisory|Finance|Capital|Group|LLC|LLP|Inc\.?|Corp\.?"
                             r"|Ltd\.?|Consulting|Securities|Associates|Strategies|Communications|Media)\b", re.I)
_RE_BOARD_NOW = re.compile(r"(?i)board(?:\s+of\s+directors)?\s+(?:now\s+|will\s+now\s+)?(?:consists|comprises|is\s+(?:now\s+)?(?:comprised|composed|made\s+up))\s+of")


def _extends(short, long):
    """Rishy -> Rishy-Maharaj, Michael Chin -> Michael C.L. Chin: same first word, and the last word kept or
    lengthened."""
    a, b = _name_words(short), _name_words(long)
    ra, rb = short.split(), long.split()
    if not a or not b or a[0] != b[0]:
        return False
    return a[-1] == b[-1] or (rb[-1].lower().startswith(ra[-1].lower().rstrip("-")) and "-" in rb[-1])


def _share_lists(text, found, pending, head_len):
    """"the Addition of Ronald Butler Jr., Michael Jalonen, and Steven Yopps" to the board: three people, one
    office. A name listed beside someone who was given a role, under the same verb, shares that role; a list
    after a colon takes the role named before the colon ("named ... as inaugural members: A, B and C")."""
    for nm, ns, ne, vs, ve, action, cl, base in pending:
        if any(same_person(f["person"] or "", nm) for f in found):
            continue
        mates = [f for f in found if f["role"] and f["person"] and f.get("_ne") is not None
                 and not re.match(r"\s*\((?:who|appointed|named|as)\b", text[f["_ne"]:f["_ne"] + 12])]   # FIX3: "John
        # Williamson (who was appointed Chair), Keith Peck, Peter Gundy": the post in the brackets is his alone
        mate = None
        for f in mates:
            a, b = (f["_ne"], ns) if f["_pos"] < ns else (ne, f["_pos"])
            if 0 <= b - a <= 160 and _RE_LIST_GAP.fullmatch(text[a:b]) \
                    and not _RE_BOARD_NOW.search(text[max(0, min(a, b) - 160):max(a, b)]):
                mate = f
                break
        if mate is not None:
            for f in [x for x in mates if x["person"] == mate["person"]]:
                found.append(dict(_row_for(nm, ns, ne, f["action"], (f["role"], f["role_canon"], f["scope"], 0),
                                           text, cl, head_len, vs)))
            continue
        colon = text.rfind(":", ve, ns)
        if colon < 0 or ns - colon > 400 or not _RE_LIST_GAP.fullmatch(text[colon + 1:ns]):
            continue
        role = R.match(text[max(base, vs - 120):colon])
        if role is None:
            continue
        found.append(_row_for(nm, ns, ne, action, _row(role), text, cl, head_len, vs))


def _rosters(text, plist, found, verbs, head_len):
    """"The team ... is comprised of: Tim Cribb, Chief Operating Officer Wessel Hamman, Chief Financial
    Officer ...": three or more names each followed by its own title, after an appointment, are appointments."""
    chain = []
    def flush():
        if len(chain) >= 3 and any(a == "appointed" and 0 <= chain[0][1] - ve <= 800 for vs, ve, a in verbs):
            for nm, ns, ne, role in chain:
                if not any(f["person"] and same_person(f["person"], nm) for f in found):
                    cl, _b = _clause(text, ns, ne)
                    found.append(_row_for(nm, ns, ne, "appointed", _row(role), text, cl, head_len))
        chain.clear()
    for nm, ns, ne in plist:
        j = _RE_ROSTER_JOIN.match(text, ne)
        role = R.match(text[:ne + 90], j.end()) if j else None
        if role is None or role[3][0] != j.end():
            flush()
            continue
        if chain and ns - (chain[-1][3][3][1]) > 4:
            flush()
        chain.append((nm, ns, ne, role))
    flush()


# FIX3 ---------------------------------------------------------------- bulleted lists after a colon
_RE_BULLET = re.compile("[\u2022\u25cf\u25aa\u25e6\u2023\u2043\u2219*]")


def _bullets(text, plist, found, verbs, head_len):
    """"The following directors and officers have resigned from the Company:\n\u2022 Jamal Amin (Director);\n\u2022
    James Macintosh (Chief Executive Officer)", "the appointment of the following directors and officers:\n\u2022 Edward
    Yew (Director & Chief Executive Officer)": each bullet after the colon that ends the action's sentence is one
    person's change, with the title printed in the bullet."""
    for vs, ve, action in verbs:
        if action is None:
            continue
        m = re.match("(?:[^.;:\n]|\n(?!\n)){0,120}?:[\s]*(?=[\u2022\u25cf\u25aa\u25e6\u2023\u2043\u2219*])", text[ve:ve + 200])
        if not m or (_RE_AFTER_MEETING.search(text[max(0, vs - 200):vs]) and not _RE_NEW_MEMBER.search(text[vs:ve + m.end()])):
            continue                                      # the officers named again after an AGM: routine
        at = ve + m.end()
        for _ in range(12):
            if not _RE_BULLET.match(text, at):
                break
            nxt = _RE_BULLET.search(text, at + 1)
            para = text.find("\n\n", at)
            end = min([x for x in (nxt.start() if nxt else -1, para if para > at else -1, at + 200) if x > at])
            seg = text[at + 1:end]
            names = [(nm, ns, ne) for nm, ns, ne in plist if at < ns and ne <= end]
            role = R.match(seg)
            if len(names) == 1 and role is not None:
                nm, ns, ne = names[0]
                if not any(f["person"] and same_person(f["person"], nm) and f["action"] == action for f in found):
                    for r in _resolve(*_chain_roles(seg, role)):
                        found.append(_row_for(nm, ns, ne, action, r, text, seg, head_len, vs))
            nb = re.compile("[\\s;,.]*(?:and\\s*)?").match(text, end).end()
            at = nb if nb < len(text) and _RE_BULLET.match(text, nb) else len(text)


def _successors(text, plist, found, head_len, issuer=None, year=None):
    """"Kelly replaces Mr. Ryan Cheung as the CFO", "succeeding Hugh Maddin", "upon the resignation of Barry
    Hartley": the person named after the word is leaving, and the office is the one being filled.  1.1.1: the office
    may be named just before the word ("take on the role of CFO, replacing Mr. Jonathan Hamel"), the person named
    just before "replaces" takes it ("Mr. Hughes replaced Ning Wu as a director"), and a replacement dated to an
    earlier year is history, not news."""
    for m in _RE_SUCCEEDS.finditer(text):
        p = next(((nm, ns, ne) for nm, ns, ne in plist if 0 <= ns - m.end() <= 3), None)
        titled = None
        if p is None:                                         # 1.1.1: "replacing the Company's CFO, Robert Suttie",
            t0 = _RE_SUCC_TITLE.match(text, m.end())          # "succeeding long-serving CEO Jean Martineau"
            r = R.match(text[:m.end() + 120], t0.end()) if t0 else None
            if r is not None and r[3][0] == t0.end():
                g = re.match(r"(?i),?\s+(?:(?:mr|mrs|ms|dr)\.?\s+)?", text[r[3][1]:r[3][1] + 12])
                at = r[3][1] + (g.end() if g else 0)
                p = next(((nm, ns, ne) for nm, ns, ne in plist if ns == at), None)
                titled = _row(r) if p is not None else None
        if p is None:
            continue
        nm, ns, ne = p
        if any(f["person"] and same_person(f["person"], nm) and f["action"] not in ("appointed", "promoted") for f in found):
            continue
        cl, base = _clause(text, m.start(), ne)
        if year and any(int(y) < year for y in re.findall(r"(?i)\bin\s+(?:" + _MONTHS + r")?\.?\s*((?:19|20)\d\d)\b", cl)):
            continue
        if re.match(r"(?i)\s*as\s+(?:previously\s+)?announced\b", cl):
            continue                                          # 1.1.1: "As previously announced, X replaced Y ..."
        said = (m.group(0) + " " + text[ne:ne + 140]).lower()
        action = ("resigned" if re.search(r"resign|step(?:s|ped|ping)?\s+down", said)
                  else "retired" if "retir" in said else "departed")
        roles = [titled] if titled else _roles_for(cl, ns - base, ne - base, issuer)
        if not roles:
            before = [r for r in _all_roles(cl[max(0, m.start() - base - 150):m.start() - base])]
            if before and not _other_org(cl, max(0, m.start() - base - 150) + before[-1][3][1], issuer):
                roles = [_row(before[-1])]
        if not roles:
            succ = [f for f in found if f["person"] and f["role"] and f["action"] in ("appointed", "promoted", "changed")
                    and base - 400 <= f["_pos"] <= ns]
            if succ:
                last = succ[-1]["person"]
                roles = [(f["role"], f["role_canon"], f["scope"], 0) for f in succ if f["person"] == last]
        for role in roles or [None]:
            found.append(_row_for(nm, ns, ne, action, role, text, cl, head_len))
        # the one named just before "replaces" / "succeeds" takes the office
        if roles and re.match(r"(?i)(?:replac|succeed|tak)", m.group(0)):
            q = next(((pn, ps, pe) for pn, ps, pe in plist if 0 <= m.start() - pe <= 4), None)
            if q is not None and not any(f["person"] and same_person(f["person"], q[0]) and f["action"] == "appointed"
                                         for f in found):
                for role in roles:
                    found.append(_row_for(q[0], q[1], q[2], "appointed", role, text, cl, head_len))


_RE_SUCC_TITLE = re.compile(r"(?i)(?:the\s+(?:company|corporation)['\u2019]s\s+|its\s+|our\s+|the\s+)?(?:long[\s\-]serving\s+|"
                            r"long[\s\-]time\s+|current\s+|outgoing\s+|former\s+|interim\s+|acting\s+|founding\s+|retiring\s+)?")


def _all_roles(s):
    out, at = [], 0
    while True:
        r = R.match(s, at)
        if r is None:
            return out
        out.append(r)
        at = r[3][1]


# 1.1.1: "thanks former CEO James Sykes", "thank Mr. Robert Suttie, our former Chief Financial Officer", "thanks John
# William Barr for his service as chief executive officer": the person who held the office being filled today
_RE_THANK = re.compile(r"(?i)\bthank(?:s|ed|ing)?\s+(?:(former|outgoing|departing)\s+)?")
_RE_THANK_FOR = re.compile(r"(?i),?\s+for\s+(?:his|her|their)\s+(?:many\s+years\s+of\s+)?(?:service|contributions?|leadership|"
                           r"tenure|dedication|time|work)\s+(?:to\s+the\s+company\s+)?as\s+(?:a\s+|an\s+|the\s+|its\s+|our\s+)?")
# FIX5: also "thanks John Smith, our previous CFO"
_RE_THANK_APPOS = re.compile(r"(?i),\s+(?:our|the\s+company['\u2019]s|its)\s+(?:former|outgoing|departing|previous|retiring)\s+")


def _thanked(text, plist, found, head_len):
    filled = [f for f in found if f["role"] and f["action"] in ("appointed", "promoted", "changed")]
    if not filled:
        return
    for m in _RE_THANK.finditer(text):
        p = r = None
        if m.group(1):                                        # "thanks former CEO James Sykes"
            r = R.match(text[:m.end() + 80], m.end())
            if r is None or r[3][0] != m.end():
                continue
            p = next(((nm, ns, ne) for nm, ns, ne in plist if 0 <= ns - r[3][1] <= 8), None)
        else:
            p = next(((nm, ns, ne) for nm, ns, ne in plist if 0 <= ns - m.end() <= 5), None)
            if p is None:
                continue
            k = _RE_THANK_FOR.match(text, p[2]) or _RE_THANK_APPOS.match(text, p[2])
            if k is None:
                continue
            r = R.match(text[:k.end() + 80], k.end())
            if r is None or r[3][0] != k.end():
                continue
        if p is None:
            continue
        nm, ns, ne = p
        chain, listed = _chain_roles(text[:r[3][1] + 80], r)
        roles = [x for x in _resolve(chain, listed) if any(R.same_role(f["role"], x[0]) and f["person"] != nm for f in filled)]
        for role in roles:
            if any(f["person"] and same_person(f["person"], nm) and R.same_role(f["role"] or "", role[0]) for f in found):
                continue
            cl, _b = _clause(text, m.start(), ne)
            found.append(_row_for(nm, ns, ne, "departed", role, text, cl, head_len))


# 1.1.1: an officer or director who already holds a post at the company and takes another has changed role
# ("Paul Robertson, the current Chief Financial Officer of the Company, has accepted the position of interim CEO",
# "COO Daniel Misiano was appointed President & CEO", "Mr. Leisman is currently a director of Mako", "Ms. Lin has
# served the Company as Controller", "following his appointment as interim COO")
_RE_HELD_APPOS = re.compile(r"(?i)^[\s,]*(?:(?:[A-Z]\.?[A-Za-z.]{0,5},\s*){0,3})(?:the\s+(?:company|corporation)['\u2019]s\s+|"
                            r"(?:currently\s+)?the\s+current\s+|currently\s+(?:the\s+|a\s+|an\s+)?|an?\s+(?:existing|current|sitting)\s+|"
                            r"its\s+(?:current\s+)?|our\s+(?:current\s+)?|the\s+)?")
_RE_HELD_SENT = re.compile(r"(?i)\b(?:is\s+currently|currently\s+serves\s+as|has\s+(?:been\s+)?serv(?:ed|ing)\s+(?:the\s+company\s+)?as|"
                           r"has\s+been|was\s+previously|previously\s+served\s+as|serves\s+as|following\s+(?:his|her)\s+"
                           r"appointment\s+as)\s+(?:(?:a|an|the)\s+)?(?:(?:company|corporation)['\u2019]s\s+)?")
_RE_HELD_HERE = re.compile(r"(?i)^[^.;]{0,40}?\b(?:of|with|at)\s+(?:the\s+(?:company|corporation)\b(?!\s+of\b))")


def _held_role(text, row, issuer):
    """The post the person already holds at the company, if the release says so, else None."""
    nm = row["person"]
    last = (_name_words(nm) or [""])[-1]
    if not last:
        return None
    names = [re.escape(nm)] + ([r"(?:Mr|Ms|Mrs|Dr)\.?\s+" + re.escape(nm.split()[-1])] if len(nm.split()) > 1 else [])
    for m in re.finditer("(?:" + "|".join(names) + ")", text):
        # an appositive right behind the name, before the action word: "X, the current CFO of the Company, has ..."
        # (FIX3: not the title printed on the line under a signature, "Brooke Clements\nPresident, Chief Executive ...")
        a = _RE_HELD_APPOS.match(text[m.end():m.end() + 80])
        r = R.match(text[:m.end() + 120], m.end() + a.end()) if a else None
        if r is not None and r[3][0] == m.end() + a.end() and a.end() > 0 \
                and not ("\n" in a.group(0) and "," not in a.group(0)) \
                and re.match(r"(?i)[\s,]*(?:of\s+the\s+(?:company|corporation)\s*,?\s*)?(?:has|have|is|was|will|as\b|,)", text[r[3][1]:r[3][1] + 40]) \
                and not _other_org(text, r[3][1], issuer) and not R.same_role(r[1], row["role_canon"] or ""):
            return r
        # a title in front of the name, the action after it: "COO Daniel Misiano was appointed"
        pre = text[max(0, m.start() - 40):m.start()]
        r = None
        for x in _all_roles(pre):
            r = x
        if r is not None and re.fullmatch(r"(?i)[\s,]*(?:and\s+)?", pre[r[3][1]:]) \
                and not re.search(r"(?i)\b(?:former|ex|outgoing|new|incoming)\b[\s\-]*$", pre[:r[3][0]]) \
                and not (re.search(r"(?i)\bas\b[^,.;:]{0,40}$", pre[:r[3][0]]) and "," in pre[r[3][1]:]) \
                and not re.search(r"(?i)\b(?:role|capacity|position|tenure)\s+(?:as|of)\b[^,.;:]{0,40}$", pre[:r[3][0]]) \
                and re.match(r"(?i)[\s,]*(?:has|have|was|is|will)\b", text[m.end():m.end() + 20]) \
                and not R.same_role(r[1], row["role_canon"] or ""):
            return r
        # a sentence saying so: "Mr. Leisman is currently a director of Mako", "has served the Company as Controller"
        h = _RE_HELD_SENT.match(text, m.end() + (1 if text[m.end():m.end() + 1] == " " else 0))
        if h:
            r = R.match(text[:h.end() + 80], h.end())
            if r is not None and r[3][0] == h.end() and not R.same_role(r[1], row["role_canon"] or "") \
                    and not _other_org(text, r[3][1], issuer) \
                    and (_RE_HELD_HERE.match(text[r[3][1]:r[3][1] + 60]) or re.search(r"(?i)company|serv(?:ed|ing)\s+the", h.group(0))
                         or "interim" in h.group(0).lower() + text[h.end() - 10:h.end()].lower()):
                return r
    return None


_NUMBER = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5}
_RE_COUNTED = re.compile(r"(?i)\s+(?:of\s+)?(a|an|one|two|three|four|five|[1-5])\s+(?:new\s+)?(?:independent\s+)?(?:non[\s\-]executive\s+)?"
                         r"(directors?|board\s+members?|members?\s+(?:of|to)\s+(?:the|its)\s+board)\b")
# 1.1.1: "The Board is ... identifying and evaluating alternatives with respect to the appointment of a new independent
# director to fill the vacancy": an appointment still being sought names no one.
_RE_SOUGHT = re.compile(r"(?i)\b(?:identify(?:ing)?|evaluat(?:e|ing)|search(?:ing)?\s+for|seek(?:ing|s)?|look(?:ing)?\s+for|"
                        r"consider(?:ing)?|in\s+due\s+course|intends?\s+to|"
                        r"plans?\s+to|expects?\s+to)\b")


def _counted(text, plist, found, verbs, head_len):
    """1.1.1: "The Company is pleased to announce the appointment of two directors. Mr. William (Bill) Feyerabend has
    ... Mr. Richard Barnett, C.P.A., is ...": the new directors are the people the next sentences begin with."""
    for vs, ve, action in verbs:
        if action != "appointed" or vs < head_len:
            continue
        m = _RE_COUNTED.match(text, ve)
        if m is None:
            continue
        k = _NUMBER[m.group(1).lower()]
        end = _RE_SENT_END.search(text, m.end())
        if end is None:
            continue
        cl, _b = _clause(text, vs, ve)
        if _RE_SOUGHT.search(cl):
            continue                                          # a seat still to be filled: the next name is not the new director
        starts = []
        for nm, ns, ne in plist:
            if ns < end.end() or ns > m.end() + 1500 or any(same_person(nm, x[0]) for x in starts):
                continue
            lead = text[max(0, ns - 8):ns]
            if re.search(r"(?:^|[.!?\n]\s*)(?:(?:Mr|Ms|Mrs|Dr)\.?\s+)?\Z", lead):
                starts.append((nm, ns, ne))
            if len(starts) == k:
                break
        if len(starts) != k or any(f["person"] and any(same_person(f["person"], x[0]) for x in starts) for f in found):
            continue
        cl, _b = _clause(text, vs, ve)
        for nm, ns, ne in starts:
            found.append(_row_for(nm, ns, ne, "appointed", ("Director", "Director", "board", 0), text, cl, head_len, vs))


def _vacated_roles(text, found):
    """1.1.1: "Mr. Clarke replaces Mr. Perry Grunenberg", "Concurrent with Mr. Bennett's appointment, the Board has accepted
    the resignation of Mr. Moe Dillon", "hired Mr. Oliver Foeste as CFO, following the departure of Mr. Jamie Lewin": a
    departure that names no office leaves the one filled, in the same sentence, by the person it names."""
    for f in found:
        if f["role"] or not f["person"] or f["action"] not in ("departed", "resigned", "retired"):
            continue
        cl, base = _clause(text, f["_pos"], f.get("_ne") or f["_pos"])
        for g in found:
            if g is f or not g["role"] or not g["person"] or g["action"] not in ("appointed", "promoted", "changed") \
                    or same_person(g["person"], f["person"]):
                continue
            last = g["person"].split()[-1]
            if re.search(r"\b" + re.escape(last) + r"\b", cl):
                f["role"], f["role_canon"], f["scope"] = g["role"], g["role_canon"], g["scope"]
                break


# the offices an officer takes on beside the post already held ("Stephen Brohman, CPA, CA, the Company's Chief
# Financial Officer, has been appointed as Corporate Secretary"): the old post is kept, so this is an appointment, not
# a change of role; the key labels it so. When the same person also moves to a new main post ("Ms. Lin has served the
# Company as Controller" and is appointed CFO and Corporate Secretary) both are part of the move.
_ADDED_POSTS = ("Corporate Secretary", "Treasurer")


def _internal_moves(text, found, issuer):
    for f in found:
        if f["action"] != "appointed" or not f["person"] or not f["role"] or f["role_canon"] == "Director":
            continue
        held = _held_role(text, f, issuer)
        if held is None or held[2] != f["scope"] or held[2] == "advisory":
            continue                                          # a director who becomes CEO is appointed (the labels)
        if f["role_canon"] in _ADDED_POSTS and held[1] not in _ADDED_POSTS \
                and not any(g is not f and g["person"] == f["person"] and g["action"] in ("appointed", "promoted", "changed")
                            and g["role_canon"] not in _ADDED_POSTS for g in found):
            continue                                          # a CFO who also becomes Corporate Secretary adds a post
        up = held[2] == f["scope"] == "management" and R.rank(f["role_canon"]) > R.rank(held[1]) + 4
        f["action"] = "promoted" if up else "changed"


_RE_OUTGOING = re.compile(r"(?i)\b(outgoing|departing|retiring)\s+")
# FIX5: also "has been appointed to its Board of Directors ..., and has been appointed as Chief Executive Officer"
_RE_ALSO = re.compile(r"(?i)(?:,\s*)?\band\s+(?:has\s+|have\s+|will\s+|had\s+)?(?:also\s+)?(?:been\s+|be\s+)?$")
_RE_REMAINS = re.compile(r"(?i)\b(?:will\s+)?(?:remain|continue|stay)(?:s|ing)?\b[^.;]{0,70}?\bas\s+(?:a|an|the)\s+")


def _outgoing(text, plist, found, head_len):
    """"Outgoing Vice President of Exploration, Ben Kuzmich" and "Outgoing CEO, Mr. Hugh Maddin": the office is
    named first and the person leaving it after."""
    for m in _RE_OUTGOING.finditer(text):
        role = R.match(text[:m.end() + 80], m.end())
        if role is None or role[3][0] != m.end():
            continue
        p = next(((nm, ns, ne) for nm, ns, ne in plist if 0 <= ns - role[3][1] <= 8), None)
        if p is None:
            continue
        nm, ns, ne = p
        if any(f["person"] and same_person(f["person"], nm) and f["scope"] == role[2]
               and f["action"] not in ("appointed", "promoted") for f in found):
            continue
        found[:] = [f for f in found if not (f["person"] and same_person(f["person"], nm) and f["role"] is None)]
        cl, _b = _clause(text, m.start(), ne)
        action = "retired" if m.group(1).lower() == "retiring" else "departed"
        said = text[ne:ne + 200].lower()
        if re.search(r"resign|step(?:s|ped|ping)?\s+down", said):
            action = "resigned"
        found.append(_row_for(nm, ns, ne, action, _row(role), text, cl, head_len))


def _also(text, found, verbs):
    """"Mark Gibson has resigned ... as Chief Operating Officer ... and has also resigned as a Director": the
    second verb has no name of its own and belongs to the person the sentence is about."""
    for vs, ve, action in verbs:
        if action is None or any(f.get("_vs") == vs for f in found):
            continue
        if not _RE_ALSO.search(text[max(0, vs - 30):vs]):
            continue
        prev = [f for f in found if f["person"] and f["_pos"] < vs and vs - f["_pos"] <= 260 and f["action"] == action]
        if not prev:
            continue
        role = R.match(text[:ve + 70], ve)
        if role is None or role[3][0] - ve > 25:
            continue
        who = prev[-1]
        if any(same_person(f["person"] or "", who["person"]) and f["scope"] == role[2] for f in found):
            continue
        row = dict(who)
        row["role"], row["role_canon"], row["scope"], _e = _row(role)
        row["_vs"] = vs
        found.append(row)


def _remains_advisory(text, plist, found, head_len):
    """"will remain active with the Company as a Technical Advisor": staying on in an advisory seat is a new
    advisory role. Staying on as a director is not a change and is left alone."""
    for m in _RE_REMAINS.finditer(text):
        role = R.match(text[:m.end() + 70], m.end())
        if role is None or role[3][0] != m.end() or role[2] != "advisory":
            continue
        cl, base = _clause(text, m.start(), m.end())
        who = [(nm, ns, ne) for nm, ns, ne in plist if base <= ns < m.start() and m.start() - ne <= 200]
        if not who:
            prev = [f for f in found if f["person"] and 0 <= m.start() - f["_pos"] <= 400]
            if not prev:
                continue
            who = [(prev[-1]["person"], prev[-1]["_pos"], prev[-1].get("_ne") or prev[-1]["_pos"])]
        nm, ns, ne = who[-1]
        if any(f["person"] and same_person(f["person"], nm) and f["scope"] == "advisory" for f in found):
            continue
        found.append(_row_for(nm, ns, ne, "appointed", _row(role), text, cl, head_len))


_RE_OWN_SUBJECT = re.compile(r"[ \n]*(?:(?:,|and|[A-Z][\w'\-]*\.?)[ \n]+){0,10}(?:were|was|has[ \n]+been|have[ \n]+been|will[ \n]+be)"
                             r"[ \n]+(?:appointed|elected|named)\b")


def analyse(headline: str, body: str) -> dict:
    """Every change the release announces, one entry per person.

    Each person is attached to the ONE action word nearest to them, so "Jane Doe has resigned as CFO and
    John Roe has been appointed CFO" is two changes rather than the four a verb-by-verb reading produces,
    and "appoints A, B and C to the board" is three, because all three names sit nearest the same verb."""
    h = flat(clean(headline or ""))
    w = clean(news_window(body or ""))
    text = h + "\n\n" + w if h else w
    head_len = len(h) + 2 if h else 0
    res = {"is_management_change": False, "reason": None, "headline_used": h, "changes": []}

    verbs = _verbs(text)
    if not verbs:
        res["reason"] = "no_action_word"
        return res

    found, pending = [], []
    sentences = [(_clause(text, vs, ve), (vs, ve, action)) for vs, ve, action in verbs]
    plist = people(text, company_names(text))
    issuer = issuer_words(text, head_len)
    later = _surname_mentions(text, plist)
    given = [g for g in _given_mentions(text, plist) if not any(g[1] == x[1] for x in later)]   # FIX3
    later += given
    given = {ns for _n, ns, _e in given}
    short = {ns for _n, ns, _e in later}
    plist = sorted(plist + later, key=lambda t: t[1])
    for nm, ns, ne in plist:
        near = None
        # FIX3: "were re-elected and Messrs. A and B were appointed to the board": A and B are the subject of their
        # own verb, so the list rule below does not hand them to the verb before
        subject = _RE_OWN_SUBJECT.match(text, ne, ne + 120)
        for (cl, base), (vs, ve, action) in sentences:
            if not (base <= ns and ne <= base + len(cl)):
                continue                                      # the person must be in the verb's own sentence
            d = max(0, ns - ve if ns >= ve else vs - ne)
            if d > 200:
                continue
            owned = bool(_RE_OWNED_NOUN.search(text[max(0, vs - 12):vs]))
            if subject and ve <= ns:
                d += 100                                  # FIX3: not the verb before the subject's own verb
            elif ns >= ve and _RE_GAP_NAMES.fullmatch(text[ve:ns]) and not owned:
                d = 0                                     # 1.1: "re-electing A and B, and electing C"
            if re.match(r"(?i)announc", text[vs:ve]):
                d += 25                                   # 1.1: a weak verb loses a tie
            if owned and ns >= ve:
                d += 40                                   # 1.1.1: "Campbell's appointment, Mr. Tafel has resigned"
            if near is None or d < near[0]:
                near = (d, vs, ve, action, cl, base)
        if near is None:
            continue
        if _RE_BY_AGENT.search(text[max(0, ns - 24):ns]):
            continue                                          # 1.1.1: "chaired by Mr. Alan Wilson", "nominated by X"
        if _RE_REPLACED_LEAD.search(text[max(0, ns - 60):ns]):
            continue                                          # 1.1.1: "replacing Stephen Dunn": _successors reads him
        if re.match(r"(?i)[\s,]*(?:and\s+(?:[A-Z][\w'\-]*\s+){1,3})?,?\s*who\s+(?:shall|will|would)\s+(?:continue|remain)", text[ne:ne + 60]) \
                or re.search(r"(?i)\bother\s+than\s+(?:(?:mr|ms|mrs|dr)\.?\s+)?\Z", text[max(0, ns - 16):ns]):
            continue                                          # 1.1.1: "other than X and Y, who shall continue to act as directors"
        if re.match("['\u2019][sS]\\b", text[ne:ne + 2]) and not re.match(
                r"(?i)['\u2019]s\s+(?:appointment|resignation|retirement|departure|passing|promotion|election)", text[ne:ne + 20]):
            continue                                          # 1.1.1: "Ron Hochstein's remarkable journey"
        d, vs, ve, action, cl, base = near
        if _is_attribution(text, ns, ne):
            continue                                          # "said John Smith, CEO" states a role, announces nothing
        others = [(ps - base, pe - base, same_person(pn, nm)) for pn, ps, pe in plist
                  if base <= ps and pe <= base + len(cl) and ps != ns]
        roles = _roles_for(cl, ns - base, ne - base, issuer, others)
        hi = max([ve, ne] + [base + r[3] for r in roles]) + 80
        lo_end = max([ve, ne] + [base + r[3] for r in roles])
        nxt = _RE_AND_OTHER.search(text, lo_end, hi)
        if nxt:
            hi = nxt.start()                                  # 1.1: "... as CFO and Grants Stock Options"
        end = _RE_SENT_END.search(text, lo_end, hi)
        if end and lo_end >= head_len:
            hi = end.start()                                  # 1.1.1: not the heading of the next paragraph
        if action is None:
            continue                                          # 1.1: re-elected, re-appointed: no change
        if ns in short and (d > 15 or (ns not in given and _RE_BIO_CONTEXT.search(cl))):
            continue                                          # 1.1.1: a later "Mr. Surname" needs the action beside it
        if ns in short:
            roles = [r for r in roles if not (base + r[3] > ne + 90 and base + r[3] > ve + 90)]
        if ns in given:                                       # FIX3: not the speaker's title after the quotation
            roles = [r for r in roles if base + r[3] > ne and base + r[3] <= max(ve, ne) + 60
                     and not re.search('["\u201d,;]|\\b(?:said|stated|commented)\\b', text[ne:base + r[3]])]
        if ns < vs and action in ("appointed", "promoted", "changed") and all(base + r[3] <= vs for r in roles) \
                and (roles or (action == "appointed" and not _RE_SENT_END.search(text, ne, vs)
                               and not any(ne <= ps < vs for _pn, ps, _pe in plist))):
            # FIX3: also when every title between the name and the action word was stepped over ("Glenn Nolan, former
            # Chief of ... and past President of ..., has agreed to join the Company's Board of Directors")
            # 1.1.1: "Mr. Rob Scargill, MAusIMM, Mining Engineer ..., has joined Dajin's Technical Advisory Board": the
            # title between the name and the action word is the one already held; the new one follows the action
            nxt = R.match(cl, ve - base)
            if nxt is not None and nxt[3][0] - (ve - base) <= 60 and not _other_org(cl, nxt[3][1], issuer) \
                    and not _honorary(cl, nxt[3][1]) \
                    and _RE_ROLE_OBJECT.fullmatch(re.sub(r"(?i)^\s*(?:\w+['\u2019\u00b4]s|the\s+company['\u2019\u00b4]s)\s+", " ",
                                                        cl[ve - base:nxt[3][0]])):
                roles = _resolve(*_chain_roles(cl, nxt))
        if re.match(r"(?i)(?:has\s+been|was|is|will\s+be)\s+(?:extended|expanded|enlarged|increased)\s+to", text[vs:ve]) and ns > ve:
            roles = [("Director", "Director", "board", ne - base)]   # FIX3: "our board has been extended to now include X"
        if not roles and action in ("departed", "resigned", "retired"):
            k = _RE_FORMER_APPOS.match(text, ne)              # 1.1.1: "terminated ... Ms. Claudia Herrera, the former
            r = R.match(text[:k.end() + 60], k.end()) if k else None   # President of the Company's Colombian subsidiary"
            if r is not None and r[3][0] == k.end() and not _other_org(text, r[3][1], issuer):
                roles = [_row(r)[:3] + (r[3][1] - base,)]
        # FIX3: the window starts at the paragraph's own start, not in the stock option plan approved the paragraph before
        if _RE_NOT_A_CHANGE.search(text[max(0, min(vs, ns) - 80, text.rfind("\n\n", 0, min(vs, ns)) + 2):hi]):
            continue                                          # the words around this change disown it
        gap = text[ne:vs] if ns < vs else text[ve:ns]
        reach = 60 if _RE_GAP_NAMES.fullmatch(gap) else 12
        if ns < vs and re.fullmatch(r"\s*,(?:[^.;:\n\"\u201c\u201d]|\n(?!\n)){0,170},\s*(?:has\s+|have\s+|will\s+)?",
                                    re.sub(r"\([^()\n]{0,60}\)", "", gap)) \
                and not re.match(r"(?i)welcom|add|strength|nam", text[vs:ve]):
            reach = len(gap)                                  # FIX3: "Eugen Popitiu, former advisor to ..., has agreed to join"
        if ns > ve and not roles and re.match(r"(?i)appoint|elect|welcom", text[vs:ve]) \
                and re.fullmatch(r"\s+(?:of\s+)?(?:(?:[A-Z][A-Za-z.'\-]*|\((?i:ret|retd|retired)\.?\))\s+){1,4}", gap) \
                and not any(ve <= ps < ns for _pn, ps, _pe in plist):
            reach = len(gap)                                  # FIX3: "appointment of Brigadier General (Ret.) Rudolf Warouw"
        if not roles and (re.match(r"(?i)welcom", text[vs:ve])
                          or not (d <= reach and _RE_DIRECT.search(text[max(0, min(vs, ns) - 10):max(ve, ne) + 40]))):
            pending.append((nm, ns, ne, vs, ve, action, cl, base))
            continue                                          # a name near a verb is not a change on its own
        if not roles and action in ("departed", "resigned", "retired") and re.search(r"(?i)re(?:[\s\-]|-\s+)?elect", text[vs:ve]):
            roles = [("Director", "Director", "board", 0)]    # 1.1: "did not stand for re-election"
        listed = len(roles) > 1
        for printed, canon, scope, _rend in (roles or [(None, None, None, 0)]):
            found.append({"action": action, "person": nm, "role": printed, "role_canon": canon, "scope": scope,
                          "effective_date": effective_date(cl),
                          "interim": bool(_RE_INTERIM.search(text[max(0, ns - 80):ne + 90])),
                          "_pos": ns, "_src": "head" if ns < head_len else "body",
                          "_list": (base, ns) if listed else None, "_ne": ne, "_vs": vs})

    _share_lists(text, found, pending, head_len)
    _rosters(text, plist, found, verbs, head_len)
    _bullets(text, plist, found, verbs, head_len)                # FIX3
    _successors(text, plist, found, head_len, issuer, _release_year(text))
    _outgoing(text, plist, found, head_len)
    _thanked(text, plist, found, head_len)
    _counted(text, plist, found, verbs, head_len)
    _internal_moves(text, found, issuer)
    _vacated_roles(text, found)
    _also(text, found, verbs)
    _remains_advisory(text, plist, found, head_len)

    # FIX3: the headline names the post and no one ("Appoints Air Solutions Specialist to Subsidiary Advisory Board"),
    # the body welcomes exactly one person ("pleased to welcome Lino G. Morris, a globally recognized expert"): his post
    if not found and pending and not any(ps < head_len for _pn, ps, _pe in plist):
        welcomed = {nm for nm, ns, ne, vs, ve, action, cl, base in pending
                    if ns >= head_len and action == "appointed" and re.match(r"(?i)welcom", text[vs:ve]) and 0 <= ns - ve <= 12}
        heads = [R.match(text[:head_len], ve) for vs, ve, action in verbs if ve < head_len and action == "appointed"]
        heads = [h for h in heads if h is not None and h[3][1] <= head_len and not re.search(r"(?i)\bthe\s+board\s+of\b", text[h[3][0] - 1:h[3][1] + 4])]
        if len(welcomed) == 1 and len({h[1] for h in heads}) == 1:
            nm, ns, ne, vs, ve, action, cl, base = next(p for p in pending if p[0] in welcomed and p[1] >= head_len)
            found.append(_row_for(nm, ns, ne, "appointed", _row(heads[0]), text, cl, head_len, vs))

    # a release that names a role but no person ("appointed a new Chief Financial Officer") still counts
    if not found:
        for vs, ve, action in verbs:
            if action is None:
                continue
            cl, base = _clause(text, vs, ve)
            role = R.match(cl, max(0, ve - base))
            # FIX3: a seat on the board taken or left, with the board as the action's own object ("Andrew Ing JOINS
            # BOARD OF DIRECTORS", "Appoints New Board Chair", "the sudden passing of Board member X", "welcomed to the
            # Board of Directors") is one director's change even when the name cannot be read
            seat = _seat(text, vs, ve, cl, base, role, issuer) if role is not None else None
            if seat is None and _RE_FIRM_OBJECT.match(text[ve:ve + 90]):
                continue                                      # 1.1: "Appoints SCP Resource Finance as Strategic Consultant"
            if role is None or role[3][0] - (ve - base) > 90:
                continue
            if seat is not None:
                role = seat
            # 1.1.1: the office has to be the action's own object ("Appoints New CFO", "the resignation of its Chief
            # Financial Officer"), a single titled post, not "the board of directors" at large or a profession
            elif not _RE_ROLE_OBJECT.fullmatch(cl[max(0, ve - base):role[3][0]]) \
                    or re.fullmatch(r"(?i)(?:the\s+)?(?:board(?:\s+of\s+directors)?|directors|advisory\s+board)", role[0]) \
                    or role[0].islower() and re.fullmatch(r"(?i)(?:\w+\s+)?(?:geologist|engineer|metallurgist|geophysicist)s?", role[0]):
                continue
            if re.search(r'(?i)["' + chr(0x201d) + r']|\b(?:said|says|stated|states|commented|added|adds|noted|notes)\b',
                         cl[max(0, ve - base):role[3][0]]):
                continue                                      # 1.1: the speaker's title after a quotation
            if _RE_NOT_A_CHANGE.search(text[max(0, vs - 80):base + role[3][1] + 80]):
                continue
            found.append({"action": action, "person": None, "role": role[0], "role_canon": role[1],
                          "scope": role[2], "effective_date": effective_date(cl),
                          "interim": bool(_RE_INTERIM.search(cl)), "_pos": vs,
                          "_src": "head" if vs < head_len else "body", "_list": None})

    _dates(text, head_len, found)
    for f in found:
        if f["person"]:
            longer = [nm for nm, _a, _b in plist if len(nm) > len(f["person"]) and same_person(nm, f["person"])
                      and _extends(f["person"], nm)]
            if longer and any(not same_person(a, b) for a in longer for b in longer):
                longer = []                                   # FIX5: "Jane Doe" is not both "Jane A. Doe" and "Jane B.C. Doe"
            if longer:
                f["person"] = max(longer, key=len)
    found.sort(key=lambda c: c["_pos"])
    changes = _dedupe(found)
    for c in changes:
        c.pop("_pos", None)
        c.pop("_src", None)
        c.pop("_list", None)
        c.pop("_ne", None)
        c.pop("_vs", None)
    changes = [c for c in changes if c["person"] or c["role"]]
    res["changes"] = changes[:12]
    res["is_management_change"] = bool(changes)
    res["reason"] = "changes" if changes else "no_named_change"
    return res


# FIX3 ---------------------------------------------------------------- a board seat with no readable name
_RE_SEAT_GAP = re.compile(r"(?i)\s*(?:(?:to|from|on|of)\s+)?(?:the\s+|its\s+|it['\u2019]s\s+|our\s+|their\s+|a\s+)?(?:company['\u2019]s\s+)?"
                          r"(?:new\s+|initial\s+|inaugural\s+|first\s+)?")


def _seat(text, vs, ve, cl, base, role, issuer):
    """The role row for "joins the Board", "Appoints New Board Chair", "passing of Board member X", "appointed to its
    advisory board": the board (or advisory board) itself is the object of the action, so the change is one seat.
    None when the role is not the board or is not the action's own object."""
    if not re.fullmatch(r"(?i)(?:the\s+)?board(?:\s+of\s+directors)?|advisory\s+board", role[0]):
        return None
    if re.match(r"(?i)vacan|nominat|elections?\b|strength|expand", text[vs:ve]) \
            or re.search(r"(?i)\b(?:anticipated|proposed|expected|planned|intended|future|potential|possible|any)\s+\Z",
                         text[max(0, vs - 20):vs]):
        return None                                       # a seat still to be filled, or a board "strengthened", is no one's change
    gap = cl[max(0, ve - base):role[3][0]]
    if not _RE_SEAT_GAP.fullmatch(gap) or _other_org(cl, role[3][1], issuer):
        return None
    if re.search(r"(?i)(?:ment|tion|ing|of)$", text[vs:ve]) and re.match(r"(?i)\s*of\b", gap) \
            and not re.match(r"(?i)\s+member\b", cl[role[3][1]:role[3][1] + 10]):
        return None                                       # "the appointment of the Board of Directors": the whole board
    tail = cl[role[3][1]:role[3][1] + 40]
    if re.match(r"(?i)\s+(?:of\s+(?!directors\b|the\s+(?:company|corporation)\b)|meeting|approv|resolution|minutes|has\b|have\b|will\b|of\s+directors\s+(?:of|has|have|will|approv))", tail):
        return None                                       # "the Board of X Corp", "the Board meeting", "the Board has"
    if re.match(r"(?i)advisory", role[0]):
        return ("Advisory Board Member", "Advisory Board", "advisory", role[3])
    if re.match(r"(?i)\s+chair(?:man|person|woman)?\b", tail):
        return ("Chair", "Chair", "board", role[3])
    return ("Director", "Director", "board", role[3])


# ------------------------------------------------------------------ facts store adapter
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["changes"]:
        return [F.Record(KIND, facts=[F.Fact("is_management_change", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"])], confidence=0.0)]
    out = []
    for i, c in enumerate(a["changes"]):
        fs = [F.Fact("is_management_change", value_num=1.0), F.Fact("action", value_text=c["action"])]
        if c["person"]:
            fs.append(F.Fact("person", value_text=c["person"]))
        if c["role"]:
            fs.append(F.Fact("role", value_text=c["role"]))
            fs.append(F.Fact("role_canon", value_text=c["role_canon"]))
        if c["scope"]:
            fs.append(F.Fact("scope", value_text=c["scope"]))
        if c["effective_date"]:
            fs.append(F.Fact("effective_date", value_text=c["effective_date"]))
        if c["interim"]:
            fs.append(F.Fact("interim", value_num=1.0))
        out.append(F.Record(KIND, facts=fs, confidence=1.0))
    return out


def parse_records(rows_by_ordinal):
    """{ordinal: [(field, seq, value_num, value_text)]} -> the analyse()-shaped dict."""
    changes = []
    is_mc = False
    for ordinal in sorted(rows_by_ordinal):
        c = {"action": None, "person": None, "role": None, "role_canon": None, "scope": None,
             "effective_date": None, "interim": False}
        for field_, seq, num, text in rows_by_ordinal[ordinal]:
            if field_ == "is_management_change":
                is_mc = is_mc or num == 1.0
            elif field_ == "interim":
                c["interim"] = num == 1.0
            elif field_ in c:
                c[field_] = text
        if c["action"]:
            changes.append(c)
    return {"is_management_change": is_mc and bool(changes), "changes": changes}


def to_prediction(records):
    """The per-release view the accuracy judge scores."""
    if not records:
        return None
    rows = {}
    for i, rec in enumerate(records):
        rows[i] = [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts]
    a = parse_records(rows)
    return prediction_from(a)


def prediction_from(a):
    if not a.get("is_management_change") or not a.get("changes"):
        return None
    return {"changes": [{"action": c["action"], "person": c["person"], "role": c["role"],
                         "scope": c["scope"], "effective_date": c.get("effective_date"),
                         "interim": bool(c.get("interim"))} for c in a["changes"]]}


def _code_sha():
    import hashlib
    import os
    h = hashlib.sha1()
    for p in (__file__, R.__file__):
        with open(p, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest() + "-" + os.path.basename(R.__file__)


SPEC = F.ExtractorSpec(NAME, VERSION, KIND, TAG, extract, _code_sha())


# ------------------------------------------------------------------ self-test
def self_test(verbose=False):
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print(f"  FAIL {name}: got {got!r}, want {want!r}")
        elif verbose:
            print(f"  ok   {name}")

    def sig(a):
        return [(c["action"], c["person"], c["role"], c["scope"]) for c in a["changes"]]

    a = analyse("Western Star Resources Appoints Garland Scott to the Board of Directors",
                "Vancouver, British Columbia - Western Star Resources Inc. is pleased to announce the appointment of "
                "Garland Scott to the Board of Directors, effective June 1, 2026.")
    eq("board appointment", sig(a), [("appointed", "Garland Scott", "Director", "board")])
    eq("board effective date", a["changes"][0]["effective_date"], "2026-06-01")

    a = analyse("Belmont Resources Appoints Ken Wheatley, P.Geol., M.Sc., as Senior Geological Advisor",
                "Belmont Resources Inc. announces the appointment of Ken Wheatley, P.Geo., as Senior Geological "
                "Advisor for the Crackingstone Uranium Project.")
    eq("advisor scope", [(c["person"], c["scope"]) for c in a["changes"]], [("Ken Wheatley", "advisory")])

    a = analyse("Company Announces CFO Transition",
                "The Company announces that Jane Doe has resigned as Chief Financial Officer and that John Roe has "
                "been appointed Chief Financial Officer.")
    eq("two changes, one release", sorted((c["action"], c["person"]) for c in a["changes"]),
       [("appointed", "John Roe"), ("resigned", "Jane Doe")])

    a = analyse("Miner Appoints Former Barrick Chief Geologist Dr. Alice Stone as VP Exploration",
                "Miner Corp. is pleased to announce that Dr. Alice Stone, formerly chief geologist at Barrick, has "
                "been appointed Vice President, Exploration.")
    eq("prior employer is not a person", [c["person"] for c in a["changes"]], ["Alice Stone"])

    eq("options grant is not a change",
       analyse("Abcourt Grants Stock Options to its Chief Financial Officer",
               "The Company granted 100,000 stock options to its Chief Financial Officer.")["is_management_change"], False)
    eq("quoted executive is not a change",
       analyse("Company Reports Drill Results",
               "\"These results are excellent,\" said John Smith, Chief Executive Officer of the Company.")["is_management_change"], False)
    eq("team strengthened with nobody named produces nothing",
       analyse("Vortex Metals Strengthens Executive Leadership Team",
               "Vortex Metals Corp. announces that it has strengthened its executive leadership team.")["changes"], [])

    a = analyse("Genius Metals Appoints Marc Bernard as Director of Capital Markets", "")
    eq("Director of X is management", [(c["role_canon"], c["scope"]) for c in a["changes"]],
       [("Director, Capital Markets", "management")])

    eq("role canon collapses spellings", (R.canonical("BOARD OF DIRECTORS")[0], R.canonical("Directors")[0],
                                          R.canonical("CFO")[0], R.canonical("Chief Financial Officer")[0]),
       ("Director", "Director", "Chief Financial Officer", "Chief Financial Officer"))
    eq("same_role", (R.same_role("CFO", "Chief Financial Officer"), R.same_role("Director", "CEO")), (True, False))

    recs = extract("Western Star Resources Appoints Garland Scott to the Board of Directors",
                   "Western Star Resources Inc. announces the appointment of Garland Scott to the Board of Directors.")
    eq("one record per change", len(recs), 1)
    p = to_prediction(recs)
    eq("prediction shape", (p["changes"][0]["person"], p["changes"][0]["scope"]), ("Garland Scott", "board"))

    # ---------------------------------------------------------------- 1.1
    def who(a):
        return sorted((c["action"], c["person"], c["scope"]) for c in a["changes"])

    a = analyse("Company Appoints Grant Tanaka as CFO and Grants Stock Options",
                "Corcel Exploration Inc. is pleased to announce the appointment of Grant Tanaka as Chief Financial "
                "Officer. Mr. Tanaka succeeds Kyle Nazareth.")
    eq("11 Grant is a first name, and the man he succeeds leaves", who(a),
       [("appointed", "Grant Tanaka", "management"), ("departed", "Kyle Nazareth", "management")])

    a = analyse("New CFO Appointed",
                "Maxtech Ventures Inc. today announced the appointment of Mr. Kelly McQuiggan to the role of Chief "
                "Financial Officer of the Company. Kelly replaces Mr. Ryan Cheung as the CFO.")
    eq("11 replaces", who(a), [("appointed", "Kelly McQuiggan", "management"), ("departed", "Ryan Cheung", "management")])

    a = analyse("StrategX Elements Corp. Confirms AGM Results",
                "All resolutions at the AGM were approved as follows: re-electing Darren Bahrey and Ryan McEachern, "
                "and electing Michael Chin and Guy Templeton as directors of the Company (Paula Caldwell St-Onge "
                "did not stand for re-election).")
    eq("11 an AGM re-election is not a change; a new director and a retiring one are", who(a),
       [("appointed", "Guy Templeton", "board"), ("appointed", "Michael Chin", "board"),
        ("departed", "Paula Caldwell St-Onge", "board")])

    a = analyse("Avalon Appoints Lorin Crenshaw as Chief Financial Officer",
                "Avalon Advanced Materials Inc. announces that Jim Andersen will retire as Chief Financial Officer, "
                "and that Lorin Crenshaw has been appointed Chief Financial Officer.")
    eq("11 retired is its own action", who(a),
       [("appointed", "Lorin Crenshaw", "management"), ("retired", "Jim Andersen", "management")])

    a = analyse("Barrick Announces Executive Appointments",
                "Barrick has appointed the leadership team for the new company. The team is comprised of: "
                "Tim Cribb, Chief Operating Officer Wessel Hamman, Chief Financial Officer Megan Tibbals, "
                "Chief Technical Officer.")
    eq("11 a roster of names and titles", [c["person"] for c in a["changes"]],
       ["Tim Cribb", "Wessel Hamman", "Megan Tibbals"])

    a = analyse("Aftermath Silver Forms Advisory Board",
                "Aftermath has formed an Advisory Board and named three founding partners as inaugural members: "
                "Lieutenant General David Bellon (USMC, Ret.), Lieutenant General Michael S. Groen (USMC, Ret.), "
                "and Ambassador James \u201cJimmy\u201d Story (Ret.).")
    eq("11 a colon list takes the role before the colon", sorted((c["person"], c["scope"]) for c in a["changes"]),
       [("David Bellon", "advisory"), ('James "Jimmy" Story', "advisory"), ("Michael S. Groen", "advisory")])

    a = analyse("Canamera Appoints Ehsan Agahi to Board of Directors",
                "Canamera Energy Metals Corp., 1500 West Georgia Street, Vancouver, announces the appointment of "
                "Ehsan Agahi to its Board of Directors.")
    eq("11 an address is not a person", [c["person"] for c in a["changes"]], ["Ehsan Agahi"])

    a = analyse("Libra Energy Appoints Dr. Jeremie Pfister as Vice President of Exploration",
                "Libra Energy is pleased to announce the appointment of Dr. Jeremie Pfister as Vice President of "
                "Exploration. Outgoing Vice President of Exploration, Ben Kuzmich, will remain active with the "
                "Company as a Technical Advisor.")
    eq("11 the outgoing officer leaves and stays on as an adviser", who(a),
       [("appointed", "Ben Kuzmich", "advisory"), ("appointed", "Jeremie Pfister", "management"),
        ("departed", "Ben Kuzmich", "management")])

    # ---------------------------------------------------------------- 1.1.1
    a = analyse("Company Reports Drill Results",
                "Selected Drill Results\nArea Depth Width Composite Assay\nThe Resulting Issuer will be renamed. Peter "
                "Tallman, President & CEO of Klondike Gold remarks \"The results are strong.\"")
    eq("111 headings, deal words and a quoted CEO are not changes", a["changes"], [])

    a = analyse("NexGold Announces Participation in Mining Investment Event",
                "CFO Orin Baranowsky will present on June 2 and join the panel on June 4. Join Kuya Silver CEO, David "
                "Stein, for a live investor webinar on Thursday.")
    eq("111 presenters and webinar hosts are not changes", a["changes"], [])

    a = analyse("Osisko Metals Announces Voting Results of Annual and Special Meeting of Shareholders",
                "All matters put forward at the annual meeting were approved as follows: Electing Robert Wares, John "
                "Burzynski and Amy Satov as directors of the Company. Following the Meeting, the directors appointed "
                "Mr. Robert Wares as Chief Executive Officer.")
    eq("111 an AGM slate and the officers re-appointed after it are not changes", a["changes"], [])

    a = analyse("Search Minerals Announces Convertible Loan",
                "For so long as the Loan is outstanding, Petra will be entitled to nominate Michael Pearson for "
                "appointment and election as a director of the Company.")
    eq("111 a right to nominate is not a change", a["changes"], [])

    a = analyse("Freeport Announces Licence Renewal",
                "Freeport announces that Tobias Kulang Thomas, a member of the Company's Advisory Board, has been "
                "appointed to the Mining Advisory Council of PNG.")
    eq("111 an appointment to an outside council is not a change", a["changes"], [])

    a = analyse("Atlas Salt Commences Geotechnical Drilling",
                "Atlas Salt has appointed Terrane Geoscience Inc. and GEMTEC Consulting Engineers Ltd. to lead the "
                "geotechnical investigation. ILF Group was appointed to complete the study.")
    eq("111 firms engaged for a piece of work are not changes", a["changes"], [])

    a = analyse("Avidian Announces Spinout",
                "High Tide's board will mirror the current board of Avidian comprised of Messrs David Anderson, Doug "
                "Kirwin and Dino Titaro, with Mr. David Anderson appointed as Chairman and CEO of High Tide.")
    eq("111 a role after someone else's name is not spread over a list",
       sorted((c["person"], c["role"]) for c in a["changes"]), [("David Anderson", "CEO"), ("David Anderson", "Chairman")])

    a = analyse("Nord Precious Metals Announces Appointment of CFO",
                "Nord is pleased to announce that Heidi Gutte has been appointed as Chief Financial Officer of the "
                "Company, replacing the Company's CFO, Robert Suttie.")
    eq("111 the officer replaced is found behind his title", who(a),
       [("appointed", "Heidi Gutte", "management"), ("departed", "Robert Suttie", "management")])

    a = analyse("Pure Energy Receives Water Right",
                "Mr. Walter Weinig, Vice President of Projects, has also agreed to a new contract. Mr. Weinig will be "
                "assuming a new role as Technical Director. Dr. Quinton Hennigh has taken on the role as special "
                "technical advisor to the Company.")
    eq("111 'Mr. Surname' after a full mention, and 'has taken on the role'",
       sorted(c["person"] for c in a["changes"]), ["Quinton Hennigh", "Walter Weinig"])

    a = analyse("Mako Mining Announces Resignation of CEO",
                "Mako's board of directors has appointed Mr. Paul Robertson, the current Chief Financial Officer of "
                "the Company, as Chief Executive Officer. Ms. Elif Levesque is stepping down as a director.")
    eq("111 an officer taking another post has changed role; 'stepping down' is a departure", who(a),
       [("promoted", "Paul Robertson", "management"), ("resigned", "Elif Levesque", "board")])

    a = analyse("Metal Energy Appoints Charlie Greig as CEO",
                "Metal Energy appoints Charlie Greig as Chief Executive Officer. The Company sincerely thanks former "
                "CEO James Sykes for his leadership.")
    eq("111 the former holder thanked is the one leaving", who(a),
       [("appointed", "Charlie Greig", "management"), ("departed", "James Sykes", "management")])

    a = analyse("Lundin Gold Announces CEO Transition",
                "Ron Hochstein will step down as President, CEO and Director of the Company.")
    eq("111 President and CEO is one office, the board seat another",
       [(c["role"], c["scope"]) for c in a["changes"]], [("President and CEO", "management"), ("Director", "board")])

    a = analyse("Northfield Metals Announces Management Changes",
                "Northfield Metals Corp. announces that Ana Ruiz has stepped down as Director, Chief Operating Officer "
                "and Interim President of the Company.")
    eq("111 key: an interim post is its own office, not half of 'President and COO'",
       [c["role"] for c in a["changes"]], ["Director", "Chief Operating Officer", "Interim President"])

    a = analyse("Northfield Metals Announces Corporate Secretary",
                "Northfield Metals Corp. is pleased to announce that Paul Ng, the Company's Chief Financial Officer, "
                "has been appointed as Corporate Secretary effective immediately.")
    eq("111 key: an officer who also becomes Corporate Secretary adds a post (appointed)", who(a),
       [("appointed", "Paul Ng", "management")])

    a = analyse("Northfield Metals Appoints Tom Reyes as CEO",
                "Northfield Metals Corp. announces that Tom Reyes will serve as Chief Executive Officer of the Company. "
                "Mr. Reyes was appointed to the Company's board of directors in May. In his role as CEO and President, "
                "Mr. Reyes was responsible for a large utility.")
    eq("111 key: a title held elsewhere 'in his role as' is not a post held here",
       [x for x in who(a) if x[2] == "management"], [("appointed", "Tom Reyes", "management")])

    a = analyse("Northfield Metals Announces Resignation of Director",
                "Northfield Metals Corp. announces that Lena Park has resigned from the Board of Directors. The Board "
                "is identifying and evaluating alternatives with respect to the appointment of a new independent "
                "director. Omar Diaz, the Company's Chief Executive Officer, will replace Ms. Park on the Audit "
                "Committee.")
    eq("111 key: a director still being sought names no one", who(a), [("resigned", "Lena Park", "board")])

    # ---- FIX3 (2026-10-01): full-text losses. Invented names; each case is one kind of release the base dropped.
    def rows(a):
        return [(c["action"], c["person"], c["role"]) for c in a["changes"]]

    a = analyse("Northfield Metals Management Change",
                "Northfield Metals Management Change\nTORONTO, Dec. 10, 2025 -- Northfield Metals Corp. (TSXV: NFM)\n"
                "announces that Northfield President, J.P. Lavoie, has stepped down from his position effective "
                "immediately. The Company also announces the resignation of Anne des Moulins as a member of the Board.")
    eq("FIX3 initials-first names and the particle 'des'", rows(a),
       [("resigned", "J.P. Lavoie", "President"), ("resigned", "Anne des Moulins", "Director")])

    a = analyse("Northfield Metals Welcomes Victoria Lane to the Board of Directors",
                "Northfield Metals Corp. is pleased to announce the appointment of Ms. Victoria Lane to its board of "
                "directors, effective immediately.")
    eq("FIX3 a given name that is also a place, after Ms.", rows(a), [("appointed", "Victoria Lane", "Director")])

    a = analyse("Northfield Metals Announces Change in Chief Financial Officer",
                "Northfield Metals Corp. announces a change in Chief Financial Officer. Jeremy North, Chief Financial "
                "Officer since 2018, will step down from the role with effect from July 8 and the role will be assumed "
                "by Joel Marlow.")
    eq("FIX3 a surname that is also a word, before the title; 'the role will be assumed by'",
       [x[:2] for x in rows(a)], [("resigned", "Jeremy North"), ("appointed", "Joel Marlow")])

    a = analyse("Northfield Metals Announces Commencement of Management Transition",
                "Northfield Metals Corp. reports that the Board has accepted a notice of retirement from Tom "
                "Haverford, President and CEO.")
    eq("FIX3 'retirement from X' names the person, not an organisation", rows(a),
       [("retired", "Tom Haverford", "President and CEO")])

    a = analyse("Northfield Metals Corp. Announces Board Change",
                "Northfield Metals Corp. Announces Board\nChange\nVancouver, British Columbia--(Newsfile Corp. - "
                "November 2, 2022) -\nNorthfield Metals\nCorp.\n(TSXV: NFM) (\"Northfield\" or the \"Company\") announces "
                "the resignation of board member,\nGeorge Hallam. Northfield thanks George for his contributions.")
    eq("FIX3 the title next to the name, not the first one of a long lead", rows(a),
       [("resigned", "George Hallam", "Director")])

    a = analyse("NORTHFIELD: PAUL OKAFOR JOINS BOARD OF DIRECTORS & ANNOUNCES ATTENDANCE AT PDAC 2026 CONFERENCE",
                "Northfield Metals Corp. advises that Paul Okafor has joined the Board of Directors. Northfield is also "
                "pleased to announce its attendance at the PDAC 2026 Conference.")
    eq("FIX3 joining the board next to a conference is still news", rows(a),
       [("appointed", "Paul Okafor", "Director")])

    a = analyse("Northfield Metals Closes Qualifying Transaction",
                "Mr. Brian Castell, who was appointed as a director of the Company today, subscribed for 30,000 shares.")
    eq("FIX3 'who was appointed ... today' is this release's change", rows(a),
       [("appointed", "Brian Castell", "Director")])

    a = analyse("Northfield Metals Provides an Operational Update",
                "Northfield Metals also announces that Mr. Derrick Amberly was elected to the board of directors at "
                "the annual general meeting held on August 20, 2024. Mr. Amberly practiced corporate law for 34 years.")
    eq("FIX3 one person elected at an AGM is not a slate", rows(a), [("appointed", "Derrick Amberly", "Director")])

    a = analyse("Northfield Metals Announces Change to Board of Directors",
                "The shareholders elected incumbent directors Ann Coyle and Bo Lindqvist. Feisal Marwan was not re -elected "
                "to the Board, and the Company thanks Mr. Marwan for his service as a director.")
    eq("FIX3 'was not re -elected' is a departure", rows(a), [("departed", "Feisal Marwan", "Director")])

    a = analyse("Northfield Metals Reports Third Quarter Results",
                "Highlights:\n- Gordon D. Ryle, Vice President and Chief Operating Officer has announced his retirement "
                "effective January 1, 2027.")
    eq("FIX3 someone announcing his own retirement is not the announcer", rows(a),
       [("retired", "Gordon D. Ryle", "Vice President and Chief Operating Officer")])

    a = analyse("Northfield Metals Announces Board Changes",
                "Northfield Metals Corp. announces that Glenn Norquay, former Chief of the Moose Creek First Nation and "
                "past President of the Prospectors Association, has agreed to join the Company's Board of Directors "
                "effective immediately.")
    eq("FIX3 every title before the verb stepped over: the seat after it", rows(a),
       [("appointed", "Glenn Norquay", "Director")])

    a = analyse("Cross Bay Names Lara Petrova Exploration Manager",
                "Cross Bay Ventures Corp. is pleased to announce the appointment of Lara Petrova, MSc, to the position "
                "of Exploration Manager.")
    eq("FIX3 'Exploration Manager' after a name is a title, not a company", rows(a),
       [("appointed", "Lara Petrova", "Exploration Manager")])

    a = analyse("Northfield Metals Appoints Technical Advisory Committee",
                "We are honored to have Boris Tanaka join our Technical Advisory Committee. Mr. Tanaka discovered two "
                "deposits.\nThe Company has appointed Andre Bayer as General Manager to its project management "
                "committee.")
    eq("FIX3 advisory and project management committees count", rows(a),
       [("appointed", "Boris Tanaka", "Technical Advisory Committee"), ("appointed", "Andre Bayer", "General Manager")])

    a = analyse("Northfield Metals Strengthens Technical Team",
                "Mr. Todd Kessel, P.Geo., is a project geologist with 20 years of experience. Todd has also joined "
                "Northfield's Technical Advisory Committee.\n\"We are pleased to welcome Judy to the Northfield team,\" "
                "said the Company's President and Chief Executive Officer, Wojtek Varga, of Judy Amsel, the new "
                "Corporate Secretary.")
    eq("FIX3 a given name alone beside 'joined'; not the speaker's title", [x[:2] for x in rows(a)][:1],
       [("appointed", "Todd Kessel")])

    a = analyse("NORTHFIELD: PAUL ING JOINS BOARD OF DIRECTORS",
                "Northfield Metals Corp. advises that Paul Ing (CEO) has joined the Board of Directors.")
    eq("FIX3 a board seat with no readable name is one director's row", rows(a), [("appointed", None, "Director")])

    a = analyse("Northfield Metals Announces AGM Results",
                "Shareholders voted in favour of all items:\n- The appointment of the Board of Directors and fixing the "
                "Board size to five.\n- Plans to fill any existing vacancy on the board.")
    eq("FIX3 'the appointment of the Board' and a vacancy are no one's seat", rows(a), [])

    a = analyse("Northfield Metals Announced Board and Management Changes",
                "Northfield Metals Ltd. announces key management changes, effective February 25, 2025.\n\nThe following "
                "directors and officers have resigned from the Company:\n\n\u2022 Jamal Amari (Director);\n\n\u2022 James "
                "Macklin (Chief Executive Officer).\n\nThe Board thanks them.")
    eq("FIX3 a bulleted list after the colon", rows(a),
       [("resigned", "Jamal Amari", "Director"), ("resigned", "James Macklin", "Chief Executive Officer")])

    a = analyse("Northfield Metals Announces Election of Directors",
                "\"Additionally, we are pleased to welcome Ms. Elise Marten and Ms. Nadia Garon to the board,\" said "
                "Benoit Lasalle, President & CEO.")
    eq("FIX3 'welcome Ms. X ... to the board,' said: Ms. is not a sentence end", rows(a)[:1],
       [("appointed", "Elise Marten", "Director")])

    a = analyse("Northfield Metals Announces Results of Annual General Meeting and Appoints New Senior Officer",
                "The continuation of the Company's stock option plan was approved.\n\nNorthfield is also pleased to "
                "announce the appointment of Mr. Takeshi Kuroda as a senior officer of the Company.")
    eq("FIX3 the stock option plan of the paragraph before does not disown the change", [x[:2] for x in rows(a)],
       [("appointed", "Takeshi Kuroda")])

    a = analyse("Northfield Metals Announces Results of AGM and Additions to Board",
                "We are happy that our board has been extended to now include Simon Hollis, a mining engineer, and Joel "
                "Montero who is the current CEO of a smelter.")
    eq("FIX3 'board extended to include'; a particle is a word of its own", rows(a),
       [("appointed", "Simon Hollis", "Director"), ("appointed", "Joel Montero", "Director")])

    a = analyse("Northfield Metals Appoints Former Secretary of Homeland Security Karin Nilsson as a Director",
                "Northfield Metals is pleased to announce the appointment of former Secretary of Homeland Security "
                "Karin M. Nilsson as a Director. Her experience in homeland security will help.")
    eq("FIX3 the office in front of a name is cut off the name", rows(a)[:1],
       [("appointed", "Karin M. Nilsson", "Director")])

    a = analyse("Northfield Metals Appoints Advisor",
                "In additional news, the Company announces the appointment of Ba rry Gilman to its advisory board. "
                "Mr.\nGilman is an independent consultant.")
    eq("FIX3 a given name split by the PDF, confirmed by 'Mr. Surname'", rows(a),
       [("appointed", "Barry Gilman", "Advisory Board Member")])

    a = analyse("NORTHFIELD ANNOUNCES APPOINTMENT OF BRIGADIER GENERAL (RET.) RUDI WARSONO AS COMMISSIONER",
                "Northfield Metals announces the appointment of Brigadier General (Ret.) Rudi Samuel Warsono as "
                "Commissioner of its Indonesian subsidiary.")
    eq("FIX3 ranks in front of the name", [x[:2] for x in rows(a)], [("appointed", "Rudi Samuel Warsono")])

    a = analyse("Northfield Appoints Air Quality Specialist to Subsidiary Advisory Board",
                "Northfield Metals is pleased to welcome Lino G. Morello, a globally recognized expert in air quality.")
    eq("FIX3 the headline names the post, the body welcomes one person", rows(a),
       [("appointed", "Lino G. Morello", "Advisory Board Member")])

    a = analyse("Northfield Closes Qualifying Transaction",
                "The directors and officers of the Company are now:\n- Bruce Clemmons - President and Chief Executive "
                "Officer\nMr. Bruce Clemmons, who was appointed as Chief Executive Officer of the Company today, "
                "subscribed for shares.\n\nON BEHALF OF THE BOARD\n\nBruce Clemmons\nPresident, Chief Executive Officer")
    eq("FIX3 the title under a signature is not a post held before", rows(a)[:1],
       [("appointed", "Bruce Clemmons", "Chief Executive Officer")])

    a = analyse("Northfield Completes Merger",
                "The combined board has four directors nominated by Northfield, consisting of John Wilmot (who was "
                "appointed Chair), Keith Perry, Peter Gandy and Jody Shim.")
    eq("FIX3 the post in brackets after one name is not shared down the list", [x for x in rows(a) if x[2] == "Chair"],
       [("appointed", "John Wilmot", "Chair")])

    a = analyse("Northfield Samples 14.2% Cs2O",
                "The result and elevated gold values prove the potential at the property\" Shawn Westover, CEO of "
                "Northfield Metals.")
    eq("FIX3 'elevated gold values' is an adjective", rows(a), [])

    a = analyse("Northfield Announces Results of AGM - New Board of Directors",
                "At the AGM, Messrs. Gerald Shiel and Stuart Avery were re-elected and Messrs. Nicholas Nikolaou and "
                "James Clare were a p p o i n t e d t o t h e b o a r d o f d i r e c t o r s o f t h e C o m p a n y .")
    eq("FIX3 letter-spaced PDF text; names that are the subject of their own verb", rows(a),
       [("appointed", "Nicholas Nikolaou", "Director"), ("appointed", "James Clare", "Director")])

    a = analyse("Northfield Announces Board Changes",
                "Graeme Lyle, a Consulting Geologist with over 30 years' experience, will be joining the Company \u00b4s "
                "Board.")
    eq("FIX3 a PDF's accent apostrophe", rows(a), [("appointed", "Graeme Lyle", "Director")])

    # FIX5 (2026-10-04)
    a = analyse("Northfield Announces Resignation of Director",
                "TORONTO, March 12, 2025 -- Northfield Metals Inc. announces that Jane Doe has resigned from the board of "
                "directors effective immediately.")
    eq("FIX5 effective immediately takes the dateline", [c["effective_date"] for c in a["changes"]], ["2025-03-12"])
    a = analyse("Northfield Corp.",
                "Vancouver, British Columbia--(Newsfile Corp. - June 15, 2026) - Northfield closes a financing.\n\n"
                "Northfield Appoints CFO\n\nVancouver, British Columbia--(Newsfile Corp. - April 2, 2026) - Northfield "
                "announces that John Roe has been appointed, effective today's date, as Chief Financial Officer.")
    eq("FIX5 a page of several releases: the date of the release the change is in",
       [c["effective_date"] for c in a["changes"]], ["2026-04-02"])
    a = analyse("Northfield Appoints John Roe to its Board",
                "TORONTO, April 29, 2024 - Northfield is pleased to announce the appointment of John Roe to its Board of "
                "Directors effective today. He will succeed Jane Doe who is not seeking re-election at the upcoming 2025 "
                "shareholder meeting.")
    eq("FIX5 a dateline behind an 'upcoming' year gives no date", [c["effective_date"] for c in a["changes"]][:1], [None])
    a = analyse("Northfield Appoints John Roe as President and CEO",
                "Northfield is pleased to announce the appointment of John Roe, as President, Chief Executive Officer "
                "(\u201cCEO\u201d) and a Director.")
    eq("FIX5 a title's bracketed abbreviation does not end the list", rows(a),
       [("appointed", "John Roe", "President and Chief Executive Officer"), ("appointed", "John Roe", "Director")])
    a = analyse("Northfield Announces CEO Transition",
                "Northfield announces the appointment of John Roe as Chief Executive Officer and as a director of the Company.")
    eq("FIX5 'and as a director' is a second post", rows(a),
       [("appointed", "John Roe", "Chief Executive Officer"), ("appointed", "John Roe", "Director")])
    a = analyse("Northfield Appoints John Roe to Board",
                "Mr. John Roe has been appointed to its Board of Directors to fill the vacancy, and has been appointed as "
                "Chief Executive Officer.")
    eq("FIX5 'and has been appointed as' gives the same person a second post", sorted(rows(a)),
       [("appointed", "John Roe", "Chief Executive Officer"), ("appointed", "John Roe", "Director")])
    a = analyse("Northfield Announces Changes to the Board of Directors",
                "Northfield is pleased to announce the appointment of John Roe to the Board. The Company also announces "
                "that Director Jane Doe will not be seeking re-election at the 2024 Annual Meeting of Shareholders.")
    eq("FIX5 'will not be seeking re-election' is a departure", sorted(rows(a)),
       [("appointed", "John Roe", "Director"), ("departed", "Jane Doe", "Director")])
    a = analyse("Northfield Welcomes Two Directors",
                "Northfield is pleased to announce the appointment of John Roe and Mary Major to the board as independent "
                "directors. Mr. Peter Pan and Ms. Wendy Moira did not stand for re-\nelection.")
    eq("FIX5 'did not stand for re-' broken by a line is a departure", sorted(x[1] for x in rows(a) if x[0] == "departed"),
       ["Peter Pan", "Wendy Moira"])
    a = analyse("Northfield Announces Appointment of Chief Financial Officer",
                "Northfield is pleased to announce the appointment of John Roe as Chief Financial Officer. The Company "
                "thanks Jane Doe, our previous CFO, for her dedicated service.")
    eq("FIX5 the previous holder thanked has left", sorted(rows(a)),
       [("appointed", "John Roe", "Chief Financial Officer"), ("departed", "Jane Doe", "CFO")])
    a = analyse("Northfield Reports Annual Meeting Voting Results",
                "Northfield announces the voting results from its annual general meeting.\nItem Voted Upon Result of Vote\n"
                "Appoint John Roe as director\nVotes For Votes Withheld\n62,574,166 (94.70%) 3,503,659 (5.30%)\n"
                "Appoint Jane Doe as director\nVotes For Votes Withheld\n62,684,253 (94.86%) 3,393,572 (5.14%)")
    eq("FIX5 a meeting's vote tally is not a change", rows(a), [])
    a = analyse("Northfield Announces Results of Annual General Meeting",
                "Northfield announces the results of its annual general meeting. At the meeting John Roe, Jane Doe and "
                "Peter Pan were appointed Directors of the Corporation for the ensuing year.")
    eq("FIX5 the board elected for the ensuing year is the slate", rows(a), [])
    a = analyse("Northfield Appoints Director",
                "Northfield has optioned the property to ABC. If ABC is successful, Northfield has appointed a director.")
    eq("FIX5 'If ABC' is not a person", [c["person"] for c in a["changes"]], [None])
    a = analyse("NORTHFIELD APPOINTS JOHN ROE AS VICE PRESIDENT EXPLORATION",
                "Northfield Gold Corp.\nUnit 1 - 100 Marine Drive\nPort Town, B.C. V1A 1A1\n\nNORTHFIELD APPOINTS JOHN ROE AS "
                "VICE PRESIDENT EXPLORATION\nPort Town, British Columbia, July 19, 2022. Northfield is pleased to announce "
                "the appointment effective July 19, 2022, of John Roe as Vice President Exploration.")
    eq("FIX5 a dateline town is not a person", [c["person"] for c in a["changes"]], ["John Roe"])
    a = analyse("Northfield Announces Appointment of Jesse Roe as VP Exploration",
                "Northfield is pleased to announce it has appointed Jessy Roe as VP Exploration.")
    eq("FIX5 one name spelled two ways is one person", len(a["changes"]), 1)
    a = analyse("Northfield Announces Appointment of Technical Advisors",
                "At the annual general meeting the number of directors was set at three with the following nominees elected as "
                "directors: John Roe, Jane B.C. Doe and Peter Pan.\n\nNorthfield is also pleased to announce the "
                "appointment of Mr. Paul Kerr and Ms. Jane A. Doe as technical advisors. \"We welcome Paul Kerr and Jane "
                "Doe as Technical Advisors,\" said Peter Pan.")
    eq("FIX5 a short name two longer names fit is not lengthened", sorted(c["person"] for c in a["changes"]),
       ["Jane A. Doe", "Paul Kerr"])
    a = analyse("Northfield Welcomes Two Directors",
                "Northfield Co-Chairman John Smith and President Jane Major also are very pleased to announce the "
                "appointment of Mary Roe to the company's board as an independent director.")
    eq("FIX5 two announcers are not appointees", rows(a), [("appointed", "Mary Roe", "Director")])
    a = analyse("Northfield Appoints Jane Doe to Board of Directors",
                "TORONTO, Feb. 01, 2023 -- Northfield is pleased to announce the appointment of Jane Doe to the Company's "
                "Board of Directors. Ms. Doe retired from Other Mines Limited in January 2021 as Senior Vice-President, People.")
    eq("FIX5 a retirement elsewhere in a past month is biography", rows(a), [("appointed", "Jane Doe", "Director")])
    a = analyse("Northfield Announces Appointment of Jane Doe to Board of Directors",
                "TORONTO, Feb. 01, 2023 -- Northfield is pleased to announce the appointment of Jane Doe to the Company's "
                "Board of Directors.\n\nAs previously announced on January 24, 2023, in connection with the appointment "
                "of Mr. John Roe as Interim CEO of the Company, the Board wishes to announce committee changes.")
    eq("FIX5 a change the release only recaps is not a row", [x[1] for x in rows(a)], ["Jane Doe"])

    print(f"management self-test: {'ok' if not bad else str(bad) + ' failures'}")
    return bad


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(1 if self_test() else 0)
