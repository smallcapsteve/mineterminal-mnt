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

Self-tests: python3 -m portal.extractors.management
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from portal import facts as F
from portal.extractors import mgmt_roles as R

NAME = "management"
VERSION = "1.0.0"
KIND = "management_change"
TAG = "Management Changes"
TEXT_CAP = 9000

ACTIONS = ("appointed", "departed", "changed", "other")


# ------------------------------------------------------------------ text
_WS = re.compile("[ \\t\\xa0\\u2000-\\u200b\\u202f\\u205f\\u3000]+")


def clean(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
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
    t = re.sub(r"(\b[A-Z][a-z]{2,15} )([A-Z])[ ]([a-z]{3,}[\w'\-]*)", r"\1\2\3", t)
    t = re.sub(r"(\b[A-Z][a-z']{2,15})[ ](?!a\b|i\b|o\b)([a-z])(?![\w'\-])", r"\1\2", t)
    return t


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
_PARTICLE = r"(?:van|von|de|del|della|di|da|du|la|le|den|der|ten|bin|al)"
_U = "\\u00c0-\\u00d6\\u00d8-\\u00de\\u0100-\\u017f"          # accented capitals (Felix, Etienne, Lukasz)
_L = "\\u00df-\\u00f6\\u00f8-\\u00ff\\u0100-\\u017f"
_TOKEN = (r"(?:[A-Z" + _U + r"][a-z'\-" + _L + r"]{1,20}|[A-Z]\.(?:\s?[A-Z]\.)?|[A-Z" + _U + r"]{2,14}(?![a-z]))")
_RE_NAME = re.compile(r"(?<![A-Za-z'\-])(" + _TOKEN + r"(?:[ ]+(?:" + _PARTICLE + r"[ ]+)?" + _TOKEN + r"){1,3})")
_HONORIFIC = re.compile(r"(?i)^(?:the\s+)?(?:mr|mrs|ms|miss|dr|prof(?:essor)?|sir|hon(?:ourable|orable)?"
                        r"|madam|gen|col|capt|sen|rev)\.?\s+")
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
_RE_PRIOR = re.compile(r"(?i)\b(?:former(?:ly)?|ex|previously|prior|retired|outgoing|departing)\b[\w\s\.,'-]{0,14}$")


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
            out.append(w[:1].upper() + w[1:].lower())
    s = " ".join(out)
    s = _RE_CASE_JOIN.sub(lambda m: m.group(1) + m.group(2).upper(), s)
    s = re.sub(r"\b(Mc|Mac|O')([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)
    return s


def _strip_name(s: str) -> str:
    s = _HONORIFIC.sub("", re.sub(r"\s+", " ", s or "").strip())
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
    "transition", "transitions", "depart", "departs", "departure", "change", "changes", "grant", "grants",
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
}


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


def company_names(text: str):
    """Token lists for the company names the release prints, so the issuer is never read as a person.

    Found by walking back from a corporate word ("Inc.", "Minerals", "Silver") over the capitalised words
    in front of it: NORTH ARROW MINERALS INC. gives [north, arrow, minerals, inc], which is how
    "NORTH ARROW APPOINTS ..." stops producing a person called North Arrow."""
    out = []
    for m in _RE_CORP_WORD.finditer(text):
        toks = [re.sub(r"[^a-z]", "", m.group(1).lower())]
        i = m.start()
        for _ in range(6):
            mm = _RE_BACK_TOKEN.search(text[:i])
            if mm is None:
                break
            w = re.sub(r"[^a-z]", "", mm.group(0).lower().replace("'s", "").replace(chr(0x2019) + "s", ""))
            if not w or w in _BACK_STOP:
                break
            toks.append(w)
            i = mm.start()
        if len(toks) >= 2:
            out.append(toks)
    return out


def _tok_in(tok: str, bag) -> bool:
    for t in bag:
        if tok == t or (len(tok) >= 4 and t.startswith(tok)) or (len(t) >= 4 and tok.startswith(t)):
            return True
    return False


def _is_company(cand: str, companies) -> bool:
    toks = [re.sub(r"[^a-z]", "", w.lower()) for w in cand.split()]
    toks = [t for t in toks if t]
    if not toks:
        return False
    return any(all(_tok_in(t, bag) for t in toks) for bag in companies)


_RE_TICKER_LEAD = re.compile(r"(?i)(?:CSE|TSXV?|NYSE|NASDAQ|FSE|FRA|OTC\w*|WKN|ISIN|SEDAR|AMEX|LSE|ASX)\s*"
                             r"[:\-]\s*[\(\[]?\s*$")


def _looks_like_person(cand: str, before: str, after: str) -> bool:
    if not cand or len(cand) < 4:
        return False
    if _RE_TICKER_LEAD.search(before[-20:]):
        return False
    if _TITLE_WORDS.search(cand):
        return False
    if _COMPANY_TAIL.match(after):
        return False
    if re.search("['\\u2019]s\\b", cand):                          # "Focus Graphite's", "MAX Power's"
        return False
    words = [w for w in re.split(r"\s+", cand) if w]
    if len(words) < 2:
        return False
    real = 0
    for w in words:
        lw = re.sub(r"[^a-z]", "", w.lower())
        if not lw:
            return False
        if lw in _STOP_TOKENS or lw in _PLACES:
            return False
        if lw not in ("van", "von", "de", "del", "della", "di", "da", "du", "la", "le", "den", "der", "ten", "bin", "al") \
                and len(lw) > 1:
            real += 1
    if real < 2:
        return False
    if re.search(r"(?i)\b(?:corp|inc|ltd|llp|llc)\b", cand):
        return False
    return True


_RE_TOKEN = re.compile(r"[A-Z" + _U + r"][a-z'\-" + _L + r"]{1,20}|[A-Z]\.(?:\s?[A-Z]\.)?|"
                       r"[A-Z" + _U + r"]{2,14}(?![a-z])|"
                       r"(?:van|von|de|del|della|di|da|du|la|le|den|der|ten|bin|al)(?![a-z])")
# one space, or a parenthesised nickname -- "Peter Jonathan (PJ) Murphy" is one person, and
# re.match would have accepted a newline here, which is how "James Schweitzer Passes\nAway" became a name.
_RE_GAP_OK = re.compile(r"[ \n]?|[ \n]?[(\[][ \n]?|[ \n]?[)\]][ \n]?")


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
    for run in _token_runs(text):
        piece = []
        for m in run + [None]:
            word = None if m is None else re.sub(r"[^a-z]", "", m.group(0).lower())
            bad = m is None or word in _STOP_TOKENS or word in _PLACES or _TITLE_WORDS.fullmatch(m.group(0) or "")
            if not bad:
                piece.append(m)
                continue
            if len(piece) >= 2:
                a, b = piece[0].start(), piece[-1].end()
                cand = text[a:b]
                name = _strip_name(cand)
                before = text[max(0, a - 40):a]
                after = text[b:b + 30]
                if _looks_like_person(name, before, after) and not _RE_PRIOR.search(before[-26:]) \
                        and not _is_company(name, companies):
                    # the honorific is part of the run only when it was written as one ("Dr. Alice Stone")
                    shift = len(cand) - len(_HONORIFIC.sub("", cand))
                    out.append((name, a + shift, b))
            piece = []
    out.sort(key=lambda t: t[1])
    keep = []
    for name, a, b in out:
        if keep and a < keep[-1][2]:
            continue
        keep.append((name, a, b))
    return keep


# ------------------------------------------------------------------ actions
_RE_APPOINT = re.compile(
    r"(?i)\b(?:appoint(?:s|ed|ing|ment|ments)?|re[\s\-]?appoint\w*|names?|named|naming|nominat(?:es|ed|ion|ions)\b|announc(?:es|ed|ing)(?=[^.\n]{0,80}?\b(?:as|to)\s+(?:its\s+|the\s+|a\s+|an\s+)?(?:new\s+|incoming\s+)?(?:chief|president|vice[\s\-]president|s?e?vp\b|director|chair|board|advisor|adviser|advisory|technical|strategic|head\s+of|general|corporate|interim|senior|executive|managing))"
    r"|elect(?:s|ed)\b|joins?\b|joined\b|joining\b|welcom(?:es|ed|ing)|add(?:s|ed|ition)\s+(?:of\s+)?(?!to\s+its\s+cash)"
    r"|bring(?:s|ing)?\s+on(?:board)?|hir(?:es|ed|ing)|engages?\s+(?!in\b)|strengthen(?:s|ed|ing)?|agree(?:s|d)\s+to\s+(?:serve|join|act)|(?:has|have)\s+agreed\s+to\s+(?:serve|join|act)|(?:been\s+)?retained\s+as|will\s+serve\s+as\s+(?:a\s+|an\s+|the\s+)?(?!financial|legal)"
    r"|expand(?:s|ed|ing)\s+(?:its\s+)?(?:board|team|leadership|management))\b")
_RE_DEPART = re.compile(
    r"(?i)\b(?:resign(?:s|ed|ation|ations|ing)?|retir(?:es|ed|ement|ing)|steps?\s+(?:down|aside)|stepped\s+(?:down|aside)"
    r"|depart(?:s|ed|ure|ures|ing)?|leav(?:es|ing)\b|left\s+the\s+(?:board|company)|no\s+longer\s+(?:serves?|be|the|with|an?\b)"
    r"|ceas(?:es|ed)\s+to\s+(?:be|serve)|vacat(?:es|ed)|terminat(?:es|ed|ion|ions)\b"
    r"|will\s+not\s+(?:be\s+)?stand(?:ing)?\s+for\s+re[\s\-]?election|passing\s+of|passed\s+away|dismiss(?:es|ed)"
    r"|relinquish(?:es|ed|ing)?|passes?\s+away|vacanc(?:y|ies)|pass(?:es|ed|ing)\s+of|pays?\s+tribute|paid\s+tribute)\b")
_RE_CHANGE = re.compile(
    r"(?i)\b(?:promot(?:es|ed|ion|ing)|transition(?:s|ed|ing)?\s+(?:to|from|into)|assum(?:e|es|ed|ing)\s+(?:the\s+)?role"
    r"|mov(?:es|ed|ing)\s+(?:in)?to\s+the\s+role|takes?\s+(?:on|over)\s+(?:as|the\s+role)|elevat(?:es|ed)"
    r"|change\s+of\s+(?:role|title)|expand(?:s|ed)\s+(?:his|her|their)\s+role|re[\s\-]?designat\w*|(?:will\s+)?mov(?:e|es|ed|ing)\s+(?:in)?to\s+(?:the\s+(?:role|position)\s+of\s+|the\s+)?(?=[A-Za-z])|continue(?:s)?\s+to\s+serve\s+as|succeed(?:s|ed|ing)?\b)\b")
# the release is about a change, but the sentence is not an announcement of one
_RE_NOT_A_CHANGE = re.compile(
    r"(?i)\b(?:stock\s+options?|option\s+grant|restricted\s+share\s+units?|\bRSUs?\b|\bDSUs?\b|deferred\s+share\s+units?"
    r"|grant(?:s|ed|ing)?\s+(?:of\s+)?(?:\d[\d,]*\s+)?(?:incentive\s+)?(?:stock\s+)?options"
    r"|will\s+be\s+(?:proposed|nominated)\s+for\s+election|standing\s+for\s+(?:re[\s\-]?)?election\s+at"
    r"|annual\s+(?:and\s+special\s+)?(?:general\s+)?meeting\s+of\s+shareholders\s+(?:to\s+be\s+)?held"
    r"|management\s+cease\s+trade|cease\s+trade\s+order|\bMCTO\b"
    r"|financial\s+advis\w*|as\s+(?:its\s+|the\s+)?(?:financial|legal)\s+advis\w*"
    r"|(?:investor|public|media)\s+relations\s+(?:firm|agreement|services|support|provider)"
    r"|communications\s+(?:firm|agreement|services|support|provider)"
    r"|market\s+making|drill(?:ing)?\s+contractor"
    r"|receipt\s+of\s+(?:the\s+)?(?:director\s+)?nominations?|nomination\s+notice|shareholder\s+requisition"
    r"|change\s+of\s+director'?s\s+interest|appendix\s+3y|director'?s\s+interest\s+notice"
    r"|qualified\s+person\s+(?:as\s+)?defined|\bNI\s+43[\s\-]101)\b")
# an appointment stated without a role: "appoints Jane Doe", "Jane Doe joins the company"
_RE_GAP_NAMES = re.compile("(?:[\\s,&]|\\band\\b|\\bMr\\.?|\\bMrs\\.?|\\bMs\\.?|\\bDr\\.?|\\bProf\\.?|\\bhave\\b|\\bhas\\b"
                          r"|\bhad\b|\bboth\b|\beach\b|\bwill\b|\bwere\b|\bwas\b|\bare\b|\bis\b|\balso\b"
                          "|\\brespectively\\b|[A-Z][\\w.'\\u2019\\-]*){0,14}")
_RE_DIRECT = re.compile(r"(?i)\b(?:appoint\w*|names?|named|welcom\w*|joins?|joined|elect\w*|resign\w*|retir\w*"
                        r"|depart\w*|steps?\s+down|nominat(?:es|ed|ion|ions)\b|pass(?:es|ed|ing)\b|tribute|retained\s+as"
                        r"|agreed?\s+to\s+(?:act|serve|join)|terminat\w*)\b")
_RE_QUOTE_LEAD = re.compile(r"(?i)\b(?:said|says|stated|commented|comments|added|noted|concluded|"
                            r"continued|continues|remarked|explained|observed|emphasi[sz]ed|according\s+to)\b")
# "... ," said John Smith, CEO  -- the attribution sits immediately in front of the name
_RE_QUOTE_BEFORE = re.compile(r"(?i)\b(?:said|says|stated|commented|comments|added|noted|concluded|"
                              r"continued|continues|remarked|explained|observed|emphasi[sz]ed|according\s+to)\W{0,4}\Z")
# Chad Williams, Executive Chairman of Honey Badger, commented "..."  -- and sometimes behind it
_RE_QUOTE_AFTER = re.compile(r"(?i)^[^.!?\n]{0,110}?\b(?:said|says|stated|commented|comments|added|noted|"
                             r"concluded|continued|continues|remarked|explained|observed|emphasi[sz]ed)\b")


def _is_attribution(text: str, ns: int, ne: int) -> bool:
    """True when this mention of a person only introduces a quotation."""
    lead = text[max(0, ns - 70):ns]
    if _RE_QUOTE_BEFORE.search(lead[-24:]):
        return True
    m = _RE_QUOTE_AFTER.search(text[ne:ne + 130])
    if m and not _RE_DIRECT.search(text[ne:ne + m.end()]) and not _RE_DIRECT.search(lead[-40:]):
        return True
    return False


# a full stop that really ends a sentence: not the one in "Dr.", "Inc.", "U.S." or an initial
_RE_SENT_END = re.compile(r"(?<![A-Z])(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)(?<!\bSt)(?<!\bJr)(?<!\bSr)"
                          r"(?<!\bInc)(?<!\bCorp)(?<!\bLtd)(?<!\bNo)(?<!\bvs)(?<!\bApprox)(?<!\bapprox)"
                          r"(?<!\bHon)(?<!\bGen)(?<!\bSen)(?<!\bRev)(?<!\bCol)(?<!\bCapt)(?<!\bProf)"
                          r"(?<!\bMme)(?<!\bMessrs)(?<!\bPh)(?<!\bEsq)(?<!\bAve)(?<!\bMt)"
                          '[.!?](?=[\\s\\n])|;|\\n\\n|(?<=[.!?:\\u201d"])\\n'
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


# ------------------------------------------------------------------ the analysis
_RE_ASIDE = re.compile(r"(?i)\b(?:former(?:ly)?|previously|prior(?:\s+to)?|ex|until|who\s+(?:was|served|as)|"
                       r"retiring|outgoing)\b")
# "Stephen Brohman, CPA, CA, the Company's Chief Financial Officer, has been appointed as Corporate
# Secretary": the title inside the commas is the job he already holds, and the change comes after it.
_RE_ASIDE_APPOS = re.compile(r"(?i)^[\s,]*(?:[A-Z]\.?[A-Za-z.]{0,5},\s*){0,3}"
                             r"(?:the\s+(?:company|corporation|firm)'?s?|currently|current|incoming|outgoing|"
                             r"who\s+(?:is|was|has|serves|served)|a\s+(?:current|long|distinguished|founding))\b")


_RE_ROLE_JOIN = re.compile(r"(?i)\s*(?:,\s*and|,|and|&|/)\s*(?:a|an|the)?\s*")
_RE_ROLE_COMMA = re.compile(r",")


def _chain_roles(clause: str, role):
    """Every title this stretch of the clause gives the person, and whether it was written as a list.

    "stepped down as Director, Corporate Secretary, Chief Operating Officer and Interim President" is a
    list of four offices; "appointed President and CEO" is one office with a two-part name. The comma is
    what separates them."""
    chain, at, listed = [role], role[3][1], False
    for _ in range(4):
        nxt = R.match(clause, at)
        if nxt is None:
            break
        join = clause[at:nxt[3][0]]
        if not _RE_ROLE_JOIN.fullmatch(join):
            break
        listed = listed or bool(_RE_ROLE_COMMA.search(join))
        chain.append(nxt)
        at = nxt[3][1]
    return chain, listed


def _roles_for(clause: str, pstart: int, pend: int):
    """The roles that belong to the person at [pstart, pend) in this clause: one entry per row.

    A role inside a "formerly chief geologist at Barrick" aside, or inside the commas of "Jane Doe, the
    Company's CFO, has been appointed Corporate Secretary", belongs to the job she already had, not to
    the change being announced, so the search steps over it and keeps looking."""
    at = pend
    for _ in range(4):
        after = R.match(clause, at)
        if after is None:
            break
        gap = clause[at:after[3][0]]
        if _RE_ASIDE.search(gap) or (at == pend and _RE_ASIDE_APPOS.match(gap)):
            at = after[3][1]                                  # step over "formerly chief geologist at X"
            continue
        if after[3][0] - pend <= 130:
            return _resolve(*_chain_roles(clause, after))
        break
    head = R.match(clause[:pstart])
    if head is not None and pstart - head[3][1] <= 25 and not _RE_ASIDE.search(clause[head[3][1]:pstart]):
        return [_row(head)]
    after = R.match(clause, pend)
    if after is not None and after[3][0] - pend <= 200 and not _RE_ASIDE.search(clause[pend:after[3][0]]):
        return [_row(after)]
    return []


def _resolve(chain, listed):
    """One row per office. Two titles joined by a bare "and" are one office when they sit at the same
    level of the same part of the company -- President and CEO -- and the senior one when they nest,
    because a Chair of the Board is already a director."""
    if len(chain) == 1:
        return [_row(chain[0])]
    if listed:
        return [_row(c) for c in chain]
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


def _row(m):
    """(printed, canon, scope, where it ends in the clause)."""
    return (m[0], m[1], m[2], m[3][1])


def _action_of(clause: str, verb: str):
    if verb == "depart":
        return "departed"
    if verb == "change":
        return "changed"
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
        return set(wa) <= set(wb) or set(wb) <= set(wa)
    # "Daniel Muniz" for Daniel Muniz Quintanilla: the given name agrees and the short form is contained
    return wa[0] == wb[0] and (set(wa) < set(wb) or set(wb) < set(wa))


def _dedupe(changes):
    """One row per person per scope. A person named in the headline and again in the body is one change:
    the body is the authority on the title and on what happened, the headline only summarises it, so
    "KEN ARMSTRONG APPOINTED CHAIRMAN" plus "Ken Armstrong transitioning to Chair of the Board" is one
    row that says he moved to Chair of the Board."""
    out = []
    for c in changes:
        same = None
        for o in out:
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
    for rx, verb in ((_RE_APPOINT, "appoint"), (_RE_DEPART, "depart"), (_RE_CHANGE, "change")):
        for m in rx.finditer(text):
            out.append((m.start(), m.end(), _action_of(text, verb)))
    out.sort()
    return out


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

    found = []
    sentences = [(_clause(text, vs, ve), (vs, ve, action)) for vs, ve, action in verbs]
    for nm, ns, ne in people(text, company_names(text)):
        near = None
        for (cl, base), (vs, ve, action) in sentences:
            if not (base <= ns and ne <= base + len(cl)):
                continue                                      # the person must be in the verb's own sentence
            d = max(0, ns - ve if ns >= ve else vs - ne)
            if d > 200:
                continue
            if near is None or d < near[0]:
                near = (d, vs, ve, action, cl, base)
        if near is None:
            continue
        d, vs, ve, action, cl, base = near
        if _is_attribution(text, ns, ne):
            continue                                          # "said John Smith, CEO" states a role, announces nothing
        roles = _roles_for(cl, ns - base, ne - base)
        hi = max([ve, ne] + [base + r[3] for r in roles]) + 80
        if _RE_NOT_A_CHANGE.search(text[max(0, min(vs, ns) - 80):hi]):
            continue                                          # the words around this change disown it
        gap = text[ne:vs] if ns < vs else text[ve:ns]
        reach = 60 if _RE_GAP_NAMES.fullmatch(gap) else 12
        if not roles and not (d <= reach and _RE_DIRECT.search(text[max(0, min(vs, ns) - 10):max(ve, ne) + 40])):
            continue                                          # a name near a verb is not a change on its own
        listed = len(roles) > 1
        for printed, canon, scope, _rend in (roles or [(None, None, None, 0)]):
            found.append({"action": action, "person": nm, "role": printed, "role_canon": canon, "scope": scope,
                          "effective_date": effective_date(cl),
                          "interim": bool(_RE_INTERIM.search(text[max(0, ns - 80):ne + 90])),
                          "_pos": ns, "_src": "head" if ns < head_len else "body",
                          "_list": (base, ns) if listed else None})

    # a release that names a role but no person ("appointed a new Chief Financial Officer") still counts
    if not found:
        for vs, ve, action in verbs:
            cl, base = _clause(text, vs, ve)
            role = R.match(cl, max(0, ve - base))
            if role is None or role[3][0] - (ve - base) > 90:
                continue
            if _RE_NOT_A_CHANGE.search(text[max(0, vs - 80):base + role[3][1] + 80]):
                continue
            found.append({"action": action, "person": None, "role": role[0], "role_canon": role[1],
                          "scope": role[2], "effective_date": effective_date(cl),
                          "interim": bool(_RE_INTERIM.search(cl)), "_pos": vs,
                          "_src": "head" if vs < head_len else "body", "_list": None})

    found.sort(key=lambda c: c["_pos"])
    changes = _dedupe(found)
    for c in changes:
        c.pop("_pos", None)
        c.pop("_src", None)
        c.pop("_list", None)
    changes = [c for c in changes if c["person"] or c["role"]]
    res["changes"] = changes[:12]
    res["is_management_change"] = bool(changes)
    res["reason"] = "changes" if changes else "no_named_change"
    return res


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
    eq("board appointment", sig(a), [("appointed", "Garland Scott", "Board of Directors", "board")])
    eq("board effective date", a["changes"][0]["effective_date"], "2026-06-01")

    a = analyse("Belmont Resources Appoints Ken Wheatley, P.Geol., M.Sc., as Senior Geological Advisor",
                "Belmont Resources Inc. announces the appointment of Ken Wheatley, P.Geo., as Senior Geological "
                "Advisor for the Crackingstone Uranium Project.")
    eq("advisor scope", [(c["person"], c["scope"]) for c in a["changes"]], [("Ken Wheatley", "advisory")])

    a = analyse("Company Announces CFO Transition",
                "The Company announces that Jane Doe has resigned as Chief Financial Officer and that John Roe has "
                "been appointed Chief Financial Officer.")
    eq("two changes, one release", sorted((c["action"], c["person"]) for c in a["changes"]),
       [("appointed", "John Roe"), ("departed", "Jane Doe")])

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

    print(f"management self-test: {'ok' if not bad else str(bad) + ' failures'}")
    return bad


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(1 if self_test() else 0)
