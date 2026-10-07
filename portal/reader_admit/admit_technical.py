"""Outside-tag admission rule for the Technical Reports (NI 43-101) reader (/technical-reports).  Round 4.

admit(headline, text, categories, out) -> (bool, reason).  Called only for releases that do NOT carry the
"Technical Reports (NI 43-101)" tag but where the reader found rows.  A release is admitted only when every row the
reader found is backed by a sentence that reports the report as this release's news, and the row is one the page
can show correctly:

  R1 filed row        a sentence says the company has filed / files / announces the filing of a report, and the
                      thing filed is the report (round 2: "has filed a title opinion ..., and is preparing a 43-101
                      report" files something else); not a citation ("was filed", "see ...", "previously filed").  A
                      non-amended report whose effective date is more than 10 months before the release is an old
                      report being cited again.
  R2 commissioned row a sentence names a report (technical report, 43-101, resource estimate/MRE, PEA, PFS, FS) and
                      either strong language (within 45 days, will be filed/released/completed, engaged/retained/
                      selected a consultant, is preparing, nearing completion) or weaker language (expected,
                      planned, underway, on track...) with a stated timing.  Sentences about an EIA/ESIA are skipped.
  R3 same project     the row's project name (core words) is in that sentence, the next one, or the headline.
                      (round 3, reader 1.0.4) A name the reader writes as "Full Name Project (SF)" matches on either
                      form: the full name's core words, or the short form the release defines.
  R4 a real project   the row's project name must be a project the release names as such, not:
                      - a common phrase or headline fragment ("Target Project", "Pipeline Projects"): the release
                        writes the name's first distinctive word in lower case (round 2: widened);
                      - a name starting with a headline verb ("Selects Mine");
                      - a short form the release defines for a longer, different name ("LRS", "LK Project");
                      - a company: the issuer itself or a firm written with a company form ("DRA Projects SA")
                        (round 2);
                      - a zone or deposit the release never calls a project, property or mine (round 2).
  R5 not a royalty    releases from royalty / streaming companies relay operators' reports: refused.
  R6 has a project    (round 2) a row with no project cannot be placed on the page; in the labelled sets such
                      studies were either someone else's or the reader missed the project the label names.
  R7 fresh study      (round 2) a commissioned (future) report cannot have an effective date more than 12 months
                      before the release: the reader copied an earlier report the release cites as background.
  R8 a report, not a  (round 4) a sentence whose only report word is a resource estimate ("the maiden MRE is nearing
     result to come   completion", "the resource estimate is on track to be released in June") announces results to
                      come, not a report: it is no commissioning cue unless it (or the sentence before it, or the
                      headline) also speaks of a technical report / NI 43-101, a filing, the 45-day rule or a
                      consultant engaged.
  R9 not stale        (round 4) "the technical report dated <over 12 months before the release> will be filed": a
                      sentence carried over from an earlier release (or a reference note citing one) is no cue.
  R10 same study      (round 4) a commissioned row's cue must name the row's kind of study (its own words, e.g. PEA
                      for a PEA row) or a report document; a resource row backed only by a PEA sentence, or a
                      resource-typed row on an FS sentence, is a misread row.
  R13 own passage     (round 4) a cue that names no project and reaches the row's project only through the
                      headline must not sit in a passage about another project (the 2,500 characters before it never
                      name the row's project and name another project at least three times).
Only the text before the "About <company>" boilerplate paragraph is read for cues.
Standard library only; no names of companies, projects or people."""
import bisect
import re
import unicodedata


def _ci(pattern):
    """Case-insensitive pattern compiled for lower-cased text (much faster than re.I on long releases)."""
    return re.compile(pattern.lower())


# ---- vocabulary ---------------------------------------------------------------------------------------------------
# words that name a technical report or study (all patterns below run on lower-cased text)
_REPORT = _ci(
    r"technical\s+report|43\s*-\s*101|resource\s+(?:estimat|update)|\bmre\b|preliminary\s+economic|\bpea\b|"
    r"pre\s*-?\s*feasibility|\bpfs\b|feasibility\s+stud|\bdfs\b|\bbfs\b")
_REPORT_KEYS = ("technical", "43", "resource", "mre", "preliminary", "pea", "feasib", "pfs", "dfs", "bfs")
# report words used as the name of a drill program, not a report
_NOT_REPORT = _ci(r"(?:resource|MRE)\s+(?:estimate\s+)?(?:drill|drilling|infill)")
# a sentence about an environmental / permitting document: its "will be filed" is not about a 43-101 report
_ENVIRO = _ci(r"\bE?S?IA\b|\bEIS\b|environmental\s+(?:and\s+social\s+)?impact|environmental\s+assessment")

# the company itself has filed a report now
_FILED = _ci(r"\b(?:has|have)\s+(?:now\s+|today\s+|recently\s+)?(?:re-?)?filed\b|(?<![/\w])(?:re-?)?files\b(?!/)|"
             r"\bis\s+(?:re-?)?filing\b|"
             r"\b(?:announces|reports|confirms|completes|provides\s+notice\s+of)\s+(?:the\s+)?(?:sedar\+?\s+)?(?:re-?\s*)?filing\b|"
             r"\breleases\s+(?:its\s+|a\s+)?(?:(?:new|updated|amended|independent)\s+)?(?:ni\s*43\s*-\s*101\s+)?technical\s+report|"
             r"technical\s+report[^.]{0,120}\bfiled\s*$")
# R1 (round 2): the end of the clause that follows a filing verb ("has filed a title opinion ..., and is preparing a
# 43-101 report": the report belongs to the second clause, not to the filing)
_CLAUSE_END = re.compile(r",\s*and\b|;|\band\s+(?:is|are|has|have|will)\b")

# strong commissioning language: needs no timing
_COMMISSION = _ci(
    r"within\s+(?:the\s+next\s+)?(?:45|forty[\s-]*five)|"
    r"\b(?:will|to)\s+be\s+(?:filed|published|posted|made\s+available|completed|released|delivered|issued)\b|"
    r"\b(?:engaged|engages|retained|retains|selected|selects|appointed|appoints|contracted|contracts|hired|hires|"
    r"commissioned|commissions|mandated)\b|"
    r"\b(?:is|are)\s+(?:currently\s+|now\s+)?(?:preparing|being\s+prepared)|\bnearing\s+completion")
# weaker language (underway, expected, planned...) that needs a stated timing in the same sentence
_TIMED = _ci(
    r"\b(?:expected|anticipated|scheduled|targeted|planned|slated|due(?!\s+to\b)|underway|under\s+way|in\s+progress|"
    r"on\s+track|on\s+schedule|progressing|advancing)\b[^.;]{0,80}?"
    r"(?:\b(?:Q[1-4]|H[12]|20\d\d|quarter|half|month|months|weeks|spring|summer|fall|autumn|winter|year[\s-]end|"
    r"end\s+of|early|mid|late|shortly|January|February|March|April|June|July|August|September|October|November|"
    r"December)\b|\b(?:in|by|during|mid-?|early|late|end\s+of)\s*May\b)")

# R8 (round 4): words for a report document or a full study, as opposed to a resource estimate (a result) alone
_STUDY_DOC = _ci(r"technical\s+report|43\s*-\s*101|preliminary\s+economic|\bpea\b|pre\s*-?\s*feasibility|\bpfs\b|"
                 r"feasibility\s+stud|\bdfs\b|\bbfs\b|\breport\b|\bfil(?:e|ed|ing)\b|sedar|"
                 r"within\s+(?:the\s+next\s+)?(?:45|forty[\s-]*five)|\b(?:engaged|engages|retained|retains|"
                 r"commissioned|commissions|appointed|appoints|contracted|contracts|hired|hires|mandated)\b")
_NI_DOC = _ci(r"technical\s+report|43\s*-\s*101")
# R10 (round 4): the cue must name the row's kind of study.  A report document (technical report, 43-101, a filing,
# the 45-day rule, a consultant engaged) fits any kind; otherwise the study's own words must be there
_GENERIC_DOC = _ci(r"technical\s+report|43\s*-\s*101|\breport\b|\bfil(?:e|ed|ing)\b|sedar|"
                   r"within\s+(?:the\s+next\s+)?(?:45|forty[\s-]*five)|\b(?:engaged|engages|retained|retains|"
                   r"commissioned|commissions|appointed|appoints|contracted|contracts|hired|hires|mandated)\b")
_TYPE_WORDS = {
    "resource": _ci(r"resource\s+(?:estimat|update)|\bmre\b"),
    "PEA": _ci(r"preliminary\s+economic|\bpea\b|scoping\s+stud"),
    "PFS": _ci(r"pre\s*-?\s*feasibility|\bpfs\b"),
    "FS": _ci(r"(?<!pre-)(?<!pre)(?<!pre\s)feasibility\s+stud|\bdfs\b|\bbfs\b|\bfs\b"),
}


def _names_type(s, rtype):
    """R10: a commissioning sentence fits a row of this report type (s is lower case)."""
    w = _TYPE_WORDS.get(rtype)
    return w is None or bool(w.search(s)) or bool(_GENERIC_DOC.search(s))


# R9 (round 4): a report dated / effective on a stated date
_DATED = re.compile(r"\b(?:dated|effective(?:\s+date)?(?:\s+of)?|as\s+(?:of|at))\s*[:,]?\s*(?:on\s+)?"
                    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(\d{1,2})\s*,\s*(\d{4})")


def _old_dated(s, rel_m):
    """R9: the sentence dates its report more than 12 months before the release."""
    for m in _DATED.finditer(s):
        if rel_m - (int(m.group(3)) * 12 + _MON[m.group(1)[:3].title()]) > 12:
            return True
    return False


# sentence is a citation of an existing / earlier report
_CITE = _ci(r"\(\s*see\b|\bsee\s+(?:the\s+|our\s+|its\s+)?(?:news|press|technical|report|company|\w+[\u2019']s\s+(?:news|press))|"
            r"\bpreviously\s+(?:filed|reported|disclosed|published|issued)\b|\bwas\s+filed\b|"
            r"\bfiled\s+on\s+SEDAR\+?\s+on\b|\bread\s+in\s+conjunction")

# R5: a royalty / streaming company (its release recaps the operators' studies and reports)
_ROYALTY_CO = _ci(r"royalt(?:y|ies)\s+(?:and|&)\s+stream|stream(?:ing)?\s+(?:and|&)\s+royalt|"
                  r"royalty\s+(?:company|corporation|holder|portfolio)|precious\s+metals?\s+streaming")

# a report withdrawn / retracted (status "withdrawn")
_WITHDRAWN = _ci(r"\bwithdr[ae]wn?\b|\bwithdrawing\b|\bretract|\bremov\w*\b[^.]{0,60}technical\s+report|"
                 r"no\s+longer\s+(?:be\s+)?relied")

# start of the "About the company" boilerplate paragraph
_ABOUT = re.compile(r"\b(?:About|ABOUT)\s+(?!the\s+(?:Project|Property|Deposit)|THE\s+(?:PROJECT|PROPERTY|DEPOSIT))"
                    r"(?:the\s+Company|THE\s+COMPANY|[A-Z][\w&.'\-]*)")

_DATE = re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*(\d{1,2})\s*,\s*(\d{4})")
_MON = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}

_GENERIC = set("the a an of and de del la project projects property properties claims claim block area mine mines "
               "deposit deposits complex operation operations gold silver copper lithium uranium nickel zinc lead "
               "tungsten potash graphite critical minerals mineral metals polymetallic north south east west "
               "underground open pit".split())

# R4: verbs that open news headlines ("Selects", "Completes", "Start ...")
_HEAD_VERB = re.compile(r"(?:Announce|Report|Provide|Select|Start|Complete|Commence|Receive|Acquire|File|Engage|Retain|"
                        r"Deliver|Advance|Begin|Launch|Update|Upgrade|Close|Expand|Intersect|Initiate|Appoint|"
                        r"Hire|Contract|Sign|Grant|Extend|Increase|Achieve)(?:s|d|ed|es)?")
# R4: company forms, and the issuer as the release introduces it: 'Name Corp. ("Name" or the "Company") (TSX: ...)'
_CORP = r"(?:Corp(?:oration)?|Inc|Incorporated|Ltd|Limited|LLC|Pty|plc|PLC|S\.?A|GmbH|AG|ULC)\b\.?"
_FIRM_TAIL = r"\s*(?:\(\w+\)\s*)?(?:" + _CORP + r"|Consulting|Consultants|Engineering|Associates|Geoscience|Geosystems)"
_ISSUER = re.compile(r"([A-Z][\w&.\-\u2019']*(?:\s+[A-Z][\w&.\-\u2019']*){0,4})\s*\(\s*(?:the\s+)?[\"\u201c\u201d]?\s*"
                     r"(?:Company|Corporation|TSX|TSXV|TSX-V|NYSE|NASDAQ|Nasdaq|CSE|ASX|OTC|AIM|LSE|FSE)")
_CORP_WORDS = {"corp", "corporation", "inc", "incorporated", "ltd", "limited", "llc", "pty", "plc", "sa", "gmbh", "ag",
               "ulc", "the"}
# R4: how a release refers to a project-level unit vs a part of one
_AS_UNIT_RE = re.compile(r"\W+(?:[\w\-]+\W+){0,2}?(?:project|property|properties|mine|complex|district|operation|"
                         r"claims)\b")
_AS_PART_RE = re.compile(r"\W+(?:[\w\-]+\W+)?(?:zone|deposit|deposits|vein|lens|pit)\b")


_SPLIT = re.compile(r"(?<=[.!?])[\"\u201d\u2019]?\s+(?=[A-Z\"\u201c(])|[\u2022\u27a2\u27a4\u25ba\u25aa\u25cf\u25e6\u25a0\uf0b7\uf0a7\uf0d8]|\s[o\u00a7]\s")
_WIDE = re.compile(r"\s{4,}")


def _sentence_spans(text):
    """(start, end) of sentences: split on sentence ends and bullets; very long runs (tables, scrambled PDF text)
    are cut again at wide gaps."""
    spans, pos = [], 0
    for m in list(_SPLIT.finditer(text)) + [None]:
        a, b = pos, (m.start() if m else len(text))
        pos = m.end() if m else len(text)
        if b - a > 600:
            for w in _WIDE.finditer(text, a, b):
                spans.append((a, w.start()))
                a = w.end()
        spans.append((a, b))
    return [(a, b) for a, b in spans if text[a:b].strip()]


def _release_month(text):
    m = _DATE.search(text[:1500])
    if not m:
        return None
    return int(m.group(3)) * 12 + _MON[m.group(1)[:3].title()]


def _body(text):
    """Text before the About-the-company paragraph (only cut when it is past the lead)."""
    for m in _ABOUT.finditer(text):
        if m.start() > 400:
            return text[:m.start()]
    return text


def _core(name):
    return {w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in _GENERIC and len(w) > 2}


def _forms(name):
    """R3 (round 3): the ways a cue may name the row's project: [(words, needs)] -- the full name's core words, and for
    a name written 'Full Name Project (SF)' (reader 1.0.4) the bracketed short form too."""
    m = re.match(r"^(.*?)\s*\(([A-Za-z0-9&]{2,6})\)\s*$", name or "")
    if not m:
        return [_core(name)]
    return [_core(m.group(1)), {m.group(2).lower()}]


# R13 (round 4): a project the release names: capitalised words, an optional bracketed short form, optional commodity words,
# then project / property / mine
_COMMOD = (r"(?:[A-Za-z]+-)*(?:gold|silver|copper|nickel|zinc|lead|lithium|uranium|graphite|cobalt|tin|tungsten|"
           r"vanadium|antimony|platinum|palladium|pge|ree|rare|earths?|element|potash|phosphate|iron|manganese|"
           r"molybdenum|polymetallic|base|precious|metals?|critical|minerals?)")
_PROJ_MENTION = re.compile(r"(?<![\w\-'])((?:[A-Z][\w'\-]*\s+(?:(?:de|del|la|las|los|y|do|da|dos)\s+)?){1,5})"
                           r"(?:\(\W*[A-Z][\w\-]*\W*\)\s+)?(?:" + _COMMOD + r"\s+){0,2}"
                           r"(?:[Pp]roject|[Pp]roperty|[Mm]ine|PROJECT|PROPERTY|MINE)\b")
_NOT_NAME = {"the", "this", "that", "its", "our", "a", "an", "since", "company", "new", "flagship",
             "advanced", "entire", "each", "both", "and", "of", "for", "at", "on", "in", "to", "with", "pea", "pfs", "fs",
             "dfs", "mre", "au", "ag", "cu", "zn", "pb", "ni", "li", "study", "feasibility", "preliminary", "economic",
             "assessment", "report", "technical", "estimate", "resource", "updated", "maiden"}


def _other_project_before(body, pos, project):
    """R13: the passage before the cue (2,500 characters) is about another project: it never names the row's project
    (none of its distinctive words), and it names another project (with project / property / mine) whose name recurs
    there at least three times."""
    win = _fold(body[max(0, pos - 2500):pos])
    words = set(re.findall(r"[a-z0-9]+", win))
    own = {w for w in re.findall(r"[a-z0-9]+", _fold(project or "")) if w not in _GENERIC and len(w) > 2}
    if own & words:
        return False
    for m in _PROJ_MENTION.finditer(body, max(0, pos - 2500), pos):
        w = [x for x in re.findall(r"[a-z0-9]+", _fold(m.group(1))) if x not in _NOT_NAME and x not in _GENERIC]
        if w and not (set(w) & own) and len(_word_positions(win, w[0])) >= 3:
            return True
    return False


def _names(t, forms):
    """R3 / R13: the text names the row's project (one of its forms)."""
    w = set(re.findall(r"[a-z0-9]+", t.lower()))
    return any(f <= w for f in forms)


def _fold(s):
    """Lower case without accents ("Kandiol\u00e9" = "kandiole", "DeLamar" = "delamar")."""
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def _bad_name(project, text):
    """R4 / R6: project names that are not a project the release names as such."""
    words = (project or "").split()
    # R6: no project.  The study cannot be placed on the page (and in the labelled sets it was either another
    # company's study or the reader missed the project the label names).
    if not words:
        return "no project name"
    first = words[0]
    dist = [w for w in re.findall(r"[A-Za-z][\w\-]*", project) if w.lower() not in _GENERIC and len(w) > 2]
    # a common phrase or headline fragment ("Target Project", "Pipeline Projects", "Premier Undeveloped ...
    # Projects", "Two New Properties"): the release writes the name's first distinctive word in lower case twice, or
    # at least as often as capitalised, so it is an ordinary word, not a proper name
    if dist and first[:1].isupper():
        hits = _word_positions(_lower(text), dist[0].lower())
        up = sum(1 for i in hits if text[i].isupper())
        low = len(hits) - up
        if low >= 2 or (low and low >= up):
            return "name is a common phrase"
    # a headline verb taken as the start of a name ("Selects Mine Development Associates" -> "Selects Mine")
    if _HEAD_VERB.fullmatch(first):
        return "name starts with a headline verb"
    # a short form the release defines for a longer, different name ("Los Ricos South ("LRS")", a project
    # ("LK Project")); the checker keys on the full name.  A short form that is the name itself ("PCH ... project
    # (the "PCH Project")") is fine.
    if re.fullmatch(r"[A-Z]{2,5}", first):
        for m in re.finditer(r"[(\u201c\"]\s*" + first + r"(?:\s+(?:Project|Property|Deposit|Mine))?\s*[)\u201d\"]", text):
            if not re.search(r"\b" + first + r"\b", text[max(0, m.start() - 100):m.start()]):
                return "name is a defined short form"
    # a company taken for the project: the issuer itself ("<Issuer> announces ..." -> project "<Issuer>"), or a firm
    # the release writes with a company form or consultancy word ("... DRA Projects SA (Proprietary) Limited")
    pw = set(re.findall(r"[a-z0-9]+", project.lower())) - _CORP_WORDS
    for m in _ISSUER.finditer(text[:3000]):
        if pw and pw == set(re.findall(r"[a-z0-9]+", m.group(1).lower())) - _CORP_WORDS:
            return "name is a company"
    firm = re.compile(r"\s+".join(re.escape(w) for w in words) + _FIRM_TAIL)
    if any(firm.match(text, i) for i in _positions(text, first)):
        return "name is a company"
    # a zone or deposit, not a project: the release calls the name a zone / deposit / pit and never a project,
    # property or mine (the study is on the project that holds it: "JAC deposit" of a multi-deposit resource)
    if dist:
        low, key = _lower(text), dist[0].lower()
        pos = _word_positions(low, key)
        if any(_AS_PART_RE.match(low, i + len(key)) for i in pos) and \
                not any(_AS_UNIT_RE.match(low, i + len(key)) for i in pos):
            return "name is a deposit within a project"
    return None


def _lower(s):
    """Lower case that keeps offsets aligned with the original text."""
    low = s.lower()
    return low if len(low) == len(s) else "".join(c if len(c.lower()) != 1 else c.lower() for c in s)


def _positions(s, word):
    """Start offsets of `word` in `s` (plain substring search, fast on long releases)."""
    out, i = [], s.find(word)
    while i >= 0:
        out.append(i)
        i = s.find(word, i + 1)
    return out


def _word_positions(s, word):
    """Start offsets of `word` as a whole word in `s`."""
    n = len(word)
    return [i for i in _positions(s, word)
            if not (i and (s[i - 1].isalnum() or s[i - 1] == "_")) and not (s[i + n:i + n + 1].isalnum() or
                                                                           s[i + n:i + n + 1] == "_")]


def _filed_report(s):
    """R1: a filing verb whose object is the report (in the verb phrase itself or later in the same clause)."""
    for m in _FILED.finditer(s):
        if _REPORT.search(m.group(0)):          # "releases ... technical report", "technical report ... filed"
            return True
        tail = s[m.end():m.end() + 160]
        cut = _CLAUSE_END.search(tail)
        if _REPORT.search(tail[:cut.start()] if cut else tail):
            return True
    return False


_BEFORE, _AFTER = 0, 1


def cues(headline, text):
    """-> list of (kind, context, sentence, own, start, body) for sentences that report a technical report as news
    (R1, R2, R8, R9): context is the headline, the sentence and the one after it (where R3 looks for the project), own
    the same without the headline, sentence the lower-cased sentence, start its offset in body (the text before the
    About paragraph)."""
    body = _body(text or "")
    spans = _sentence_spans(body)
    starts = [a for a, _ in spans]
    # only sentences holding a report keyword are examined (plain substring search keeps this fast)
    low, hits = body.lower(), set()
    for kw in _REPORT_KEYS:
        i = low.find(kw)
        while i >= 0:
            hits.add(bisect.bisect_right(starts, i) - 1)
            i = low.find(kw, i + 1)
    rel_m = _release_month(text or "")
    sents = [(headline or "", True)] + [(body[a:b], (k in hits)) for k, (a, b) in enumerate(spans)]
    found = []
    for k, (s, has_report) in enumerate(sents):
        if not has_report:
            continue
        s = s.lower()
        kinds = []
        if _filed_report(s):
            kinds.append("filed")
        if (_COMMISSION.search(s) or _TIMED.search(s)) and not _ENVIRO.search(s):
            kinds.append("commissioned")
        if _WITHDRAWN.search(s):
            kinds.append("withdrawn")
        if not kinds or not _REPORT.search(_NOT_REPORT.sub(" ", s)) or _CITE.search(s):
            continue
        # R8 (round 4): a resource estimate to be announced is a results release to come, not a report: a sentence
        # whose only report word is the estimate ("the maiden resource estimate is nearing completion", "the MRE is on
        # track to be released in June") is no commissioning cue unless it also speaks of a report document (a
        # technical report, a filing, the 45-day rule, a consultant engaged)
        # the report may be named just before: "Work is underway on an updated NI 43-101 MRE ... The MRE is expected
        # to be completed next quarter", or in the headline ("... to Deliver NI 43-101 Resource Estimate")
        if "commissioned" in kinds and not _STUDY_DOC.search(s) and \
                not _NI_DOC.search((sents[0][0] + " " + (sents[k - 1][0] if k > 1 else "")).lower()):
            kinds.remove("commissioned")
        # R9 (round 4): "the technical report dated <a date over a year before the release> will be filed": a stale
        # sentence carried over from an earlier release, not a report still to come
        if "commissioned" in kinds and rel_m and _old_dated(s, rel_m):
            kinds.remove("commissioned")
        if not kinds:
            continue
        ctx = " ".join([sents[0][0]] + [x for x, _ in sents[max(1, k - _BEFORE):k + 1 + _AFTER]])
        own = " ".join(x for x, _ in sents[max(1, k - _BEFORE):k + 1 + _AFTER]) if k else ""
        pos = spans[k - 1][0] if k else 0
        found.extend((kind, ctx, s, own, pos, body) for kind in kinds)
    return found


def admit(headline, text, categories, out):
    rows = (out or {}).get("rows") or []
    if not rows:
        return False, "no rows"
    text = text or ""
    # R5: royalty / streaming companies (other tag, or described so in the lead)
    if any("royalt" in c.lower() for c in categories or []) or \
            _ROYALTY_CO.search(((headline or "") + " " + text[:1000]).lower()):
        return False, "royalty company"
    found = cues(headline, text)
    rel_m = _release_month(text)

    for r in rows:
        st = r.get("status")
        if st not in ("filed", "commissioned", "withdrawn"):
            return False, "unknown status"
        cand = [f for f in found if f[0] == st and (st != "commissioned" or _names_type(f[2], r.get("report_type")))]
        mine = [f[1] for f in cand]
        if not mine:
            return False, st + ": no cue"
        bad = _bad_name(r.get("project"), text)
        if bad:
            return False, bad
        forms = [f for f in _forms(r.get("project")) if f]
        if forms and not any(f <= set(re.findall(r"[a-z0-9]+", s.lower())) for f in forms for s in mine):
            return False, st + ": project not in cue"
        # R13 (round 4): a cue that names no project and reaches the row's project only through the headline must
        # not sit in a passage about another project ("<Other> Updates ... The Company will be filing an updated
        # technical report ... within 45 days" in an exploration release about the headline project)
        if forms and cand and not any(_names(f[3], forms) for f in cand) and \
                all(_other_project_before(f[5], f[4], r.get("project")) for f in cand if _names(f[1], forms)):
            return False, st + ": cue is in a passage about another project"
        ed = re.match(r"(\d{4})-(\d{2})", str(r.get("effective_date") or ""))
        age = rel_m - (int(ed.group(1)) * 12 + int(ed.group(2))) if ed and rel_m else None
        # R1: a non-amended filed report dated well before the release is an old report being cited again
        if st == "filed" and age is not None and age > 10 and not r.get("amended"):
            return False, "filed: old report"
        # R7: a report still to come cannot carry an effective date over a year old; the reader took it from an
        # earlier report the release cites as background, so the row mixes the two
        if st == "commissioned" and age is not None and age > 12:
            return False, "commissioned: old effective date"
    return True, "cue"
