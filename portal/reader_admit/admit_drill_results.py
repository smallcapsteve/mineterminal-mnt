"""Outside-tag admission rule for the Drill Results reader (miningnewsterminal.com), round 7 (2026-10-04); built on round 6
(2026-10-04) and round 4 (2026-09-30, with reader 1.0.8).

admit(headline, text, categories, out) -> (bool, short_reason)

Reader 1.0.8 decides for itself whether a release announces NEW drill assays (its NEWS_V1 gate). Round 3 therefore kept
only two release-level rules. The fresh conf3 sample (round-3 rule + reader 1.0.8) showed one kind the reader gate lets
through: releases whose own news is NOT assays, but drilling logistics, target work, a look back or an investment
portfolio, and which quote an intercept released earlier (or by another company) as context. Round 4 adds rule 3 for it.
  1. exploration releases only: the release carries the "Exploration Programs" category;
  2. not somebody else's results: paid commentary, a royalty / streaming holder or shareholder reporting on another
     company's project, or an investor's update on its portfolio of junior equities;
  3. the company's own statement is not about drilling logistics, target work or a look back (a rig added or now
     operational, drill crews, progress of a program, the first holes completed and samples sent to the lab, preparations
     for the next phase; targets defined or refined from re-logging or re-sampling; a review of last year's results with
     goals for the next) unless the headline, the deck (sub-headline, highlight bullets) or that statement claims new
     results (new / drill / assay results not pending, assays received or "assays from", a hole that intersected or
     returned a graded interval) that is not marked as earlier work ("previous", "historic", "see", "review of").

Round 6 (FIX5 item 6, 2026-10-04)
Set dev9 (80 outside-tag finds of the new reader, drawn site-wide with no rule) showed the round-4 rule admitting 11
releases whose own news is not new drill assays. Kinds refused now:
  4. the reader's top intercept is quoted as earlier or someone else's work: the intercept is located in the text
     (grade with its length, else its hole id) and the two sentences before it plus its own sentence mark it as
     (a) earlier work ("previous drilling", "historic holes", "prior results", "legacy data"),
     (b) published before ("as reported", "has disclosed", "reported by", "released on May 3", "On May 3 ... announced",
         "see news release dated"), or someone else's ground (third parties, a neighbouring or adjacent property), or
     (c) dated three or more years before the release date ("Drilling in 1991 and 1992 ...");
     a claim of new results in the headline, the deck or the company's statement outweighs it (the release then has
     news of its own and the row is right even when the top intercept is an older one);
  5. no drill hole, core or drilled interval anywhere in the first 4,000 characters: surface work only (grab, channel,
     chip, auger / till, riverbed samples) whose sample intervals the reader reads as intercepts;
  rule 3 widened: the program is starting or under way ("drilling has resumed", "commences / initiates its drill
     program", "an update regarding the ongoing drilling program");
  claims narrowed: "exploration results" alone (also used for mapping and surface work) and results "announced /
     reported by" another company no longer count as a claim of new drill results.
Rule 1 widened (rule 1b): a release filed under another category (corporate update, resource or study update, technical
report) is admitted when its opening (headline plus the first 800 characters) itself states a drilled interval
("6.4 m @ 11.6 g/t") not marked as earlier work, never when it carries a financing, deal, option, royalty or insider
category. Rules 2 to 5 then apply as for exploration releases.
Round 7 (FIX5 item 6, 2026-10-04)
The fresh confirm 10 (60 releases the round-6 rule admits) had rows right 93.3% but the shown top intercept right on only
73.3%: in 16 of 60 it was an interval released before, a surface or rock sample, or another hole's figure. Confirm 10 is
now dev data (set c10; dev9 + c10 = set both). Round 7 adds rule 6, which checks the reader's top intercept itself. It
looks at every place the text states it (its grade with its length), not only the first, and no claim of new results in
the headline, deck or statement outweighs it (round 6's rule 4 let such a claim win, and so admitted new-results
releases whose shown figure was an old one). Kinds refused:
  6a. quoted as earlier or someone else's work: an earlier-work marker leads into the figure inside its own sentence or
      bullet ("previously reported results (see releases dated ...): <bullet> DD0001 ... 18.15 m at 4.9 g/t",
      "historical drilling have returned 9.8 g/t", "results ... announced last week, including ... 126 g/t"), or a
      citation follows it ("(see press release ... dated", "(*Previously reported)"); the marker does not count when the
      words between hand over to new results ("and today's results of"), compare ("lower-grade than previous
      drillholes", "historic versus re-assay"), close a parenthesis the marker sits in, or cross table rows of other holes;
      a bullet starts a new item unless it follows a lead-in ending in a colon;
  6b. drilling of an earlier year, in the figure's own sentence ("drilled in the winter of 2022", "2021 drill hole");
  6c. surface work: a surface-sampling marker leads into the figure in its sentence or bullet (outcrop, trench, grab,
      chip, channel, rock or float samples, boulders, exposed veins, "sampled on surface"), or a sample number follows it
      ("sample AB-036"); a company name containing such a word does not count;
  6d. the top intercept's hole is not one of the release's new holes: it is named for a year 2 to 12 years before the
      release ("23XY-001" in 2025), it is marked as published before ("19AB-002 and 19AB-005 previously released",
      "AB-22-005 (released on January 5, 2023)", "-039 were reported previously"), or it falls outside the range of holes
      the release says it reports ("results from Holes XY25-53 through -56"; same prefix, not named in that sentence,
      not a range of pending holes);
  6e. the figure (grade with its length) is not stated anywhere in the text: the reader computed or misread it;
  rule 3 widened: a plan for the coming work ("outline the next stages of exploration", "next phase of exploration").
Text repairs: "p revious" / "h istorical" (a stray space from PDF extraction) count as the words; a date written
"April 19 , 2023" gives the release year.
Standard library only; deterministic; no I/O; ASCII-only source.
"""
import re

LEDE_CHARS = 2000
FULL_CHARS = 12000

RE_COMMENTARY = re.compile(r"\b(?:news commentary|paid (?:for|advertis\w*|commentary)|sponsored content|"
                           r"disseminated on behalf)\b", re.I)
RE_HOLDER = re.compile(r"\b(?:royalty|streaming)\s+(?:and\s+streaming\s+)?compan(?:y|ies)\b|\broyalty holder\b"
                       r"|\broyalty operating partners?\b"
                       r"|\b(?:still\s+)?(?:holds?|retains?)\s+(?:a|an|approximately|about)\s+(?:[^.]|\.\d){0,40}?"
                       r"(?:royalty|shares of)\b"
                       # rule 2, round 4: an investor's update on its portfolio of junior equities; the drill figures
                       # in it are its investees' or partners' earlier news
                       r"|\bequit(?:y|ies)\s+(?:portfolio|holdings)\b", re.I)

# --- rule 3: the company's own statement ---------------------------------------------------------------------------
Q = "[\"'\u201c\u201d\u2018\u2019]"
# where the company's statement starts: "is pleased to ...", or the clause right after the defined company name
RE_ANCHOR = re.compile(r"\b(?:is|are)\s+(?:very\s+|extremely\s+)?(?:pleased|delighted|excited|proud|happy)\s+to\b"
                       r"|\(\s*(?:the\s+)?" + Q + r"?\s*(?:Company|Corporation)\s*" + Q + r"?[^)]{0,60}\)", re.I)
RE_SENT_END = re.compile(r"(?<!\b[A-Z])(?<!\bInc)(?<!\bCorp)(?<!\bLtd)(?<!\bNo)(?<!\bapprox)\.\s+(?=[A-Z\"\u201c(])")

# drilling logistics or progress (no assays are the news)
RE_LOGISTICS = re.compile(
    r"\b(?:second|third|fourth|additional|another|one|two|three|new)\s+(?:(?:diamond|core|RC|reverse[- ]circulation|"
    r"sonic|underground|surface)\s+)?drill(?:ing)?\s*(?:rigs?|crews?)\b"
    r"|\b(?:adds?|added|adding|addition\s+of|increases?\s+to|mobili[sz]\w*)\b.{0,40}\bdrill(?:s|\s*rigs?)?\b"
    r"|\brigs?\s+(?:is|are|was|were)\s+(?:now\s+)?(?:operational|mobili[sz]ed|on\s+site|turning)\b"
    r"|\b(?:report|update)\s+on\s+(?:the\s+)?progress\b|\bprogress\s+(?:of|on|for)\s+(?:the|its|our)\b"
    r"|\bcompleted\s+the\s+first\s+(?:\w+\s+){0,2}holes\b"
    r"|\bsamples?\b.{0,60}\b(?:sent|delivered|submitted|shipped)\s+(?:to\s+)?(?:the\s+)?(?:lab|laborator)"
    r"|\bpreparations?\s+for\b"
    # round 6: the program is starting or under way ("drilling has resumed", "commences / initiates its drill program",
    # "an update regarding the ongoing drilling program")
    r"|\b(?:drilling\s+(?:has\s+|have\s+)?(?:now\s+)?(?:resumed|commenced|started|begun|re-?started)|"
    r"(?:resum|commenc|initiat|re-?start|launch)\w*\s+(?:of\s+)?(?:the\s+|its\s+|a\s+)?(?:[\w-]+\s+){0,3}drill(?:ing)?|"
    r"update\s+(?:on|regarding|of|about)\s+(?:the\s+|its\s+|our\s+)?(?:ongoing|current|continuing))\b"
    # round 7: a plan for the coming work ("outline the next stages of exploration")
    r"|\boutlines?\s+(?:the\s+|its\s+)?(?:next|upcoming|planned|proposed)\b"
    r"|\bnext\s+(?:stages?|phases?)\s+of\s+(?:exploration|drilling|work)\b", re.I)
# target work from re-logging, re-sampling or review (no new holes assayed)
RE_TARGETS = re.compile(r"\b(?:defin|refin|identif|prioriti[sz])\w*\s+(?:\w+\s+){0,4}(?:drill|exploration)\s+targets\b"
                        r"|\bre-?logging\b|\bre-?sampling\b", re.I)
# a look back over a past season with goals for the next
RE_RECAP = re.compile(r"\breview(?:s|ed|ing)?\s+(?:of\s+)?(?:its|the|our)\s+(?:\w+\s+){0,3}(?:results|year|season|program)"
                      r"|\byear[- ]in[- ]review\b|\blooks?\s+back\b|\bsets?\s+the\s+stage\b|\bgoals\s+for\b", re.I)
# a claim of new results in the headline, the deck or the statement
RE_RESULTS = re.compile(
    r"\b(?:new|initial|first|final|latest|further|additional|recent|preliminary|complete|continuing|positive|"
    r"assay|analytical|drill(?:ing)?)\s+(?:drill(?:ing)?\s+|assay\s+|analytical\s+)?results\b"
    r"(?!\s+(?:(?:are|is|remain|will\s+be)\s+)?(?:still\s+)?(?:pending|awaited|outstanding|expected|anticipated|due))"
    r"|\breceived\b.{0,40}\b(?:assays?|results)\b|\bassays?\s+(?:results?\s+)?(?:from|for|of)\b"
    r"|\b(?:intersect|intercept|hit|cut|return)(?:s|ed|ing)?\b.{0,80}?\d\s*(?:g/t|%|ppm|ppb|grams|lb)", re.I)
# ... unless the claim is about earlier or someone else's work ("previous drill results", "historic assays")
RE_OLD = re.compile(r"\b(?:previous(?:ly)?|prior|earlier|historic(?:al)?|past|last\s+(?:year|season)'?s?|"
                    r"see|reviews?|reviewed|reviewing)\b[^.;]{0,30}$", re.I)


# an interval stated as a result: "drilled / intersected / returned ... 12.5 m @ 3.1 g/t", "6.4m @ 11.6 g/t"
OPEN_CHARS = 800
RE_INTERVAL = re.compile(r"\b\d+(?:\.\d+)?\s*(?:m|metres?|meters?|ft|feet)\s*(?:@|at|of|grading|averaging)\s*\d+(?:\.\d+)?\s*"
                         r"(?:g/t|gpt|%|ppm|ppb|grams|oz/t|kg/t|lb)", re.I)
RE_DEALCAT = re.compile(r"financ|placement|acqui|merger|option|staking|royalt|stream|insider|dividend", re.I)


def interval_claim(s):
    for m in RE_INTERVAL.finditer(s or ""):
        if not RE_OLD.search(s[max(0, m.start() - 60):m.start()]):
            return True
    return False


# ... or someone else's ("results announced by" another company)
PUBLISHED = r"(?:reported|announced|disclosed|released|published)"
RE_BY = re.compile(r"\s*(?:[\w-]+\s+){0,2}" + PUBLISHED + r"\s+by\b", re.I)


def claims(s):
    for m in RE_RESULTS.finditer(s or ""):
        if not RE_OLD.search(s[max(0, m.start() - 40):m.start()]) and not RE_BY.match(s, m.end()):
            return True
    return False


def statement(body):
    """-> (deck, statement): the text before the company's statement (repeated headline, sub-headline, highlight
    bullets; at most 1000 chars) and the statement sentence the anchor opens (at most 400 chars)."""
    m = RE_ANCHOR.search(body)
    if not m:
        return "", ""
    s = body[m.end():m.end() + 400]
    e = RE_SENT_END.search(s)
    return body[max(0, m.start() - 1000):m.start()], (s[:e.start()] if e else s)


# --- rule 4 (round 6): where the reader's top intercept sits ---------------------------------------------------------
MONTHS = (r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
          r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?")
RE_NUM = re.compile(r"(?<![\d.])\d+(?:,\d{3})*(?:\.\d+)?")
RE_YEAR = re.compile(r"(?<![\d./-])(19[5-9]\d|20[0-4]\d)(?![\d])")
# lead-in (the two sentences before and the intercept's own sentence) that marks the figure as earlier or someone
# else's work: (a) earlier work ("previous drilling", "historic holes", "prior results"); (b) published before, a
# reporting verb marked as past or as someone else's ("reported by", "as announced", "has disclosed", "released on May 3",
# "On May 3 ... reported") or a citation ("see news release dated"); (c) someone else's ground (third parties, a neighbouring or adjacent property)
WORK = (r"(?:drill\w*|holes?|results?|intercepts?|intersections?|assays?|work|programs?|campaigns?|exploration|data|"
        r"operators?|owners?|reported|announced|released|disclosed|published)")
EARLIER_REST = (
    r"\b(?:has|have|had|as|previously)\s+(?:previously\s+|been\s+)?" + PUBLISHED + r"\b|"
    r"\b" + PUBLISHED + r"\s+(?:by\b|(?:on|in)\s+(?:" + MONTHS + r"|\d{4}))|"
    r"\bon\s+" + MONTHS + r"\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+and\s+\d{1,2}(?:st|nd|rd|th)?)?,?\s+(?:\d{4},?\s+)?"
    r"(?:[\w.&-]+\s+){0,4}" + PUBLISHED + r"\b|"
    r"\b(?:press|news)\s+releases?\s+(?:\w+\s+){0,4}dated\b|\bsee\s+(?:the\s+)?(?:\w+\s+){0,4}(?:press|news)\s+releases?\b|"
    r"\bthird[- ]part(?:y|ies)\b|\bneighbo(?:u)?ring\b|\badjacent\s+(?:property|project|claims?|ground)\b")
RE_EARLIER = re.compile(
    r"\b(?:previous(?:ly)?|prior|earlier|historic(?:al|ally)?|legacy|past)\s+(?:[\w-]+\s+){0,2}" + WORK + r"\b|" +
    EARLIER_REST, re.I)
# round 7 (rule 6a only): the same markers, with a stray space from PDF extraction ("h istorical", "p revious"), and
# published a short while ago ("announced last week", "recently reported")
RE_EARLIER7 = re.compile(
    r"\b(?:p\s?revious(?:ly)?|prior|earlier|h\s?istoric(?:al|ally)?|legacy|past)\s+(?:[\w-]+\s+){0,2}" + WORK + r"\b|"
    r"\b" + PUBLISHED + r"\s+(?:last\s+(?:week|month|year|quarter)|earlier\s+(?:this|in)\b|recently|previously)\b|"
    r"\brecently\s+" + PUBLISHED + r"\b|" + EARLIER_REST, re.I)
RE_SPLIT = re.compile(r"(?<!\b[A-Z])(?<!\bInc)(?<!\bCorp)(?<!\bLtd)(?<!\bNo)(?<!\bapprox)[.;]\s+(?=[A-Z\"\u201c(\u2022])")


def _near(a, b):
    return abs(a - b) <= max(0.011, 0.005 * abs(b))


def locate(body, out):
    """-> position in body of the reader's top intercept (grade with its length within 120 chars), else of its hole id,
    else -1."""
    try:
        g = float(out.get("grade")); L = float(out.get("length_m") or 0)
    except (TypeError, ValueError, AttributeError):
        return -1
    toks = [(m.start(), float(m.group().replace(",", ""))) for m in RE_NUM.finditer(body)]
    lens = [L, L / 0.3048] if L else []
    islen = [any(_near(v, x) for x in lens) for _, v in toks]
    for i, (p, v) in enumerate(toks):
        if _near(v, g):
            if not lens or any(islen[j] and abs(toks[j][0] - p) <= 120
                               for j in range(max(0, i - 25), min(len(toks), i + 26)) if j != i):
                return p
    hole = (out.get("hole") or "").strip()
    if len(hole) >= 3:
        return body.find(hole)
    return -1


def around(body, pos):
    """-> the two sentences before the intercept, its own sentence up to it and the rest of that sentence (at most 500
    chars before and 160 after)."""
    cuts = [m.end() for m in RE_SPLIT.finditer(body, max(0, pos - 900), pos)]
    start = cuts[-3] if len(cuts) >= 3 else 0
    start = max(start, pos - 500)
    e = RE_SPLIT.search(body, pos + 1, pos + 160)
    return body[start:(e.start() if e else min(len(body), pos + 160))]


RE_HOLEWORD = re.compile(r"\b(?:holes?|cores?|drilled|DDH|RC|reverse[- ]circulation|down-?hole|drill\s+results?|"
                         r"drill(?:ing)?\s+(?:returned|intersected|intercepted|encountered))\b", re.I)
HOLE_CHARS = 4000
RE_DATE = re.compile(MONTHS + r"\s+\d{1,2}(?:st|nd|rd|th)?\s?,?\s+((?:19|20)\d\s?\d)\b|\b\d{1,2}\s+" + MONTHS +
                     r",?\s+((?:19|20)\d\s?\d)\b|\b((?:19|20)\d\d)-\d\d-\d\d\b", re.I)


def release_year(lede):
    """-> the latest year written as a date (Month day, year) in the lede, or None."""
    ys = [int("".join(g.split())) for m in RE_DATE.finditer(lede) for g in m.groups() if g]
    return max(ys) if ys else None


def old_figure(full, out):
    pos = locate(full, out)
    if pos < 0:
        return ""
    ctx = around(full, pos)
    m = RE_EARLIER.search(ctx)
    if m:
        return m.group(0)
    ry = release_year(full[:LEDE_CHARS])
    if ry:
        for y in RE_YEAR.findall(ctx):
            if int(y) <= ry - 3:
                return y
    return ""


# --- round 7: is the reader's top intercept the release's own new drill figure? ---------------------------------------
def locate_all(body, out):
    """-> every position in body where the reader's top intercept is stated (its grade with its length within 120
    chars, the length in metres or feet; with no length, the grade alone)."""
    try:
        g = float(out.get("grade")); L = float(out.get("length_m") or 0)
    except (TypeError, ValueError, AttributeError):
        return []
    toks = [(m.start(), float(m.group().replace(",", ""))) for m in RE_NUM.finditer(body)]
    lens = [L, L / 0.3048] if L else []
    islen = [any(_near(v, x) for x in lens) for _, v in toks]
    found = []
    for i, (p, v) in enumerate(toks):
        if _near(v, g):
            if not lens or any(islen[j] and abs(toks[j][0] - p) <= 120
                               for j in range(max(0, i - 25), min(len(toks), i + 26)) if j != i):
                found.append(p)
    return found


# a bullet starts a new item, unless it follows a list lead-in ending in a colon ("previously reported results (see
# releases dated ...): <bullet> DD0001 ...")
RE_BULLET = re.compile(r"(?<![:\s])\s*[\u2022\u25aa\u25a0\u25e6\u27a2\uf0b7]\s*")


def item_start(body, pos, back):
    """-> where the sentence or bullet holding pos starts (at most `back` chars before it)."""
    cuts = [m.end() for m in RE_SPLIT.finditer(body, max(0, pos - back), pos)]
    cuts += [m.end() for m in RE_BULLET.finditer(body, max(0, pos - back), pos)]
    return max(cuts) if cuts else max(0, pos - back)


def own_sentence(body, pos, back=250, ahead=160):
    """-> the intercept's own sentence (or bullet), at most `back` chars before it and `ahead` chars after."""
    start = item_start(body, pos, back)
    e = RE_SPLIT.search(body, pos + 1, pos + ahead)
    return body[start:(e.start() if e else min(len(body), pos + ahead))]


# (a) earlier work: the marker leads into the figure in its own sentence or bullet ...
#     ... unless the words between hand over to new results, compare, close a parenthesis, or cross table rows
RE_NOWWORD = re.compile(r"\b(?:today'?s?|this\s+(?:release|news)|new|latest|current|now|versus|vs\.?|compared|"
                        r"re-?assay\w*)\b", re.I)
RE_COMPARE = re.compile(r"\b(?:than|to|with)\s+(?:the\s+|those\s+(?:of|from|in)\s+)?$", re.I)
RE_DASHID = re.compile(r"\b(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)[A-Z0-9]+-[A-Z0-9-]*[A-Z0-9]\b", re.I)
#     ... or a citation right after the figure: "(see press release by the Company dated ...)", "(*Previously
#     reported)", "(released on January 5, 2023)"
RE_CITE_AFTER = re.compile(r"^[^()]{0,120}?\(\s*\*?\s*(?:see\s+(?:the\s+)?(?:[\w-]+\s+){0,3}(?:press|news)\s+releases?|"
                           r"(?:as\s+)?p\s?reviously\s+" + PUBLISHED + r"|" + PUBLISHED + r"\s+(?:on|in)\s+(?:" + MONTHS +
                           r"|\d{4}))", re.I)


def lead_marker(full, p):
    """-> the earlier-work marker that leads into the figure at p within its own sentence or bullet ("previously reported
    results (see releases dated ...): DD0001 ... 18.15 m at 4.9 g/t", "historical drilling have returned 9.8 g/t"),
    or a citation that follows it, else ""."""
    start = item_start(full, p, 300)
    lead = full[start:p]
    ms = list(RE_EARLIER7.finditer(lead))
    if ms:
        m = ms[-1]
        between = lead[m.end():]
        if not (RE_NOWWORD.search(between) or RE_COMPARE.search(lead[:m.start()])
                or between.count(")") > between.count("(")
                or len(set(x.upper() for x in RE_DASHID.findall(between))) >= 2):
            return m.group(0)
    m = RE_CITE_AFTER.search(full[p:p + 200])
    return m.group(0)[-60:] if m else ""


# (b) drilling of an earlier year: "drilled in the winter of 2022", "2021 drill hole"
RE_YEARWORK = re.compile(
    r"\b(?:drilled|completed|intersected|encountered|reported|announced|released)\s+(?:in|during)\s+(?:the\s+)?"
    r"(?:(?:winter|spring|summer|fall|autumn|early|late|first|second|third|fourth|Q[1-4])\s+(?:half\s+|quarter\s+)?"
    r"(?:of\s+)?)?((?:19|20)\d\d)\b|\b((?:19|20)\d\d)\s+(?:drill\s+|discovery\s+)?hole\b", re.I)

# (c) surface work: grab, chip, channel or rock samples, outcrop, trench, float or boulder sampling
RE_SURFACE = re.compile(
    r"\b(?:surface\s+(?:samples?|sampling|grabs?|rocks?|channels?|chips?)|sampled\s+(?:on|at|from)\s+(?:the\s+)?surface|"
    r"outcrop\w*|grab\s+samples?|channel\s+samples?|chip\s+samples?|rock\s+(?:chip\s+|grab\s+)?samples?|"
    r"trench(?:es|ing)?|float\s+samples?|boulders?|exposed\s+(?:veins?|structures?))", re.I)
RE_SAMPLEID = re.compile(r"\bsamples?\s+(?:no\.?\s+)?[A-Z]{2,}-?\d", re.I)
RE_COMPANYNAME = re.compile(r"\s+(?:[A-Z][\w&]*\s+){0,3}(?:Corp\w*|Inc|Ltd|Limited|Resources|Mining|Metals|Gold|Silver|"
                            r"Minerals|Exploration)\b")


def surface_marker(full, p):
    """-> a surface-work marker leading into the figure in its own sentence or bullet ("Results from outcropping lodes
    include ...", "the quartz veining sampled on surface (25 metres of 0.9 g/t"), or a sample number right after it
    ("0.8 m @ 127 g/t AuEq from Main Vein sample AB-036"); a company name (e.g. a company named after an outcrop) does not count."""
    for m in RE_SURFACE.finditer(full, item_start(full, p, 250), p):
        if not RE_COMPANYNAME.match(full, m.end()):
            return m.group(0)
    m = RE_SAMPLEID.search(full, p, p + 80)
    return m.group(0) if m else ""


# (d) the top intercept's hole: named for an earlier year, cited as published before, or outside the holes reported
HOLE_ID = r"(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)[A-Z0-9]{1,8}(?:-[A-Z0-9]{1,6}){0,3}"
RE_RANGE = re.compile(r"\b(" + HOLE_ID + r")\s*(?:to|through|thru|\u2013)\s*(?:holes?\s+)?(" + HOLE_ID + r"|-\d{1,4})\b")
RE_PENDING = re.compile(r"\b(?:pending|in\s+progress|awaited|outstanding|expected)\b", re.I)
RANGE_CHARS = 3000


def split_id(s):
    """-> (prefix, number) of a hole id: "AB-21-017" and "AB21-017" -> ("AB21", 17); "DDH221" -> ("DDH", 221)."""
    s = s.upper()
    if "-" in s:
        head, _, tail = s.rpartition("-")
        m = re.match(r"^(\d+)[A-Z]?$", tail)
        return (head.replace("-", ""), int(m.group(1))) if m else (None, None)
    m = re.match(r"^([A-Z]+)(\d+)[A-Z]?$", s)
    return (m.group(1), int(m.group(2))) if m else (None, None)


def hole_year(hole, ry):
    """-> the year a hole id is named for ("AB-22-01", "23XY-001", "XY25-47") when it is 2 to 12 years before the
    release year, else None."""
    m = re.match(r"^(?:[A-Z]{1,5}-?)?(\d{2})[-A-Z]", (hole or "").upper())
    if not (m and ry):
        return None
    y = int(m.group(1)); y += 2000 if y <= ry % 100 else 1900
    return y if ry - 12 <= y <= ry - 2 else None


def hole_cited(full, hole):
    """-> the place where the hole, as written ("AB -22-005") or by its number in a list ("AB-19-035, -036, -037, -039
    were reported previously"), is marked as published before ("... previously released", "(released on January 5,
    2023)"), else ""."""
    tail = hole.rpartition("-")[2]
    pat = r"\s?-\s?".join(re.escape(x) for x in hole.split("-")) + \
        (r"|(?<=[\s,])-" + re.escape(tail) + r"\b" if "-" in hole and tail.isdigit() else "")
    rx = re.compile(r"(?:" + pat + r")[^.;()]{0,40}?(?:p\s?reviously\s+" + PUBLISHED + r"|" + PUBLISHED +
                    r"\s+previously)\b(?!\s+(?:holes?\s+)?" + HOLE_ID + r")"
                    r"|(?:" + pat + r")\s*\(\s*" + PUBLISHED + r"\s+(?:on|in)\s+(?:" + MONTHS + r"|\d{4})", re.I)
    m = rx.search(full)
    return m.group(0)[-60:] if m else ""


def outside_range(full, hole):
    """-> the stated range of reported holes ("results from holes XY25-53 through -56") when the top intercept's hole
    has the same prefix, lies outside it and is not named in that sentence; a range of pending holes does not count."""
    p, n = split_id(hole or "")
    if p is None:
        return ""
    head = full[:RANGE_CHARS]
    mine = []
    for m in RE_RANGE.finditer(head):
        p1, a = split_id(m.group(1))
        if m.group(2).startswith("-"):
            p2, b = p1, int(m.group(2)[1:])
        else:
            p2, b = split_id(m.group(2))
        if not (p1 == p and p2 == p and a is not None and b is not None and 0 < b - a <= 200):
            continue
        cuts = [x.end() for x in RE_SPLIT.finditer(head, max(0, m.start() - 400), m.start())]
        e = RE_SPLIT.search(head, m.end())
        sent = head[(cuts[-1] if cuts else max(0, m.start() - 400)):(e.start() if e else len(head))]
        if RE_PENDING.search(sent) or any(split_id(t) == (p, n) for t in re.findall(HOLE_ID, sent)):
            return ""
        mine.append((a, b, m.group(0)))
    if mine and not any(a <= n <= b for a, b, _ in mine):
        return mine[0][2]
    return ""


def figure_reasons(full, out):
    """-> [(kind, reason)] for every sign that the reader's top intercept is not the release's own new drill figure."""
    R = []
    ry = release_year(full[:LEDE_CHARS])
    hole = (out.get("hole") or "").strip()
    pos = locate_all(full, out)
    if not pos and out.get("grade") is not None:
        R.append(("notstated", "top intercept (grade with its length) is not stated in the release"))
    for p in pos:
        w = lead_marker(full, p)
        if w:
            R.append(("earlier", "top intercept quoted as earlier or someone else's work: " + w))
        for m in RE_YEARWORK.finditer(own_sentence(full, p)):
            if ry and int(m.group(1) or m.group(2)) < ry:
                R.append(("year", "top intercept from an earlier year's drilling: " + m.group(0)))
        w = surface_marker(full, p)
        if w:
            R.append(("surface", "top intercept is surface work: " + w))
    if len(hole) >= 3:
        y = hole_year(hole, ry)
        if y:
            R.append(("holeyear", "top intercept's hole is named for an earlier year: %s (%d)" % (hole, y)))
        w = hole_cited(full, hole)
        if w:
            R.append(("holecited", "top intercept's hole is cited as published before: " + w))
        w = outside_range(full, hole)
        if w:
            R.append(("range", "top intercept's hole is outside the holes the release reports: " + w))
    return R


def admit(headline, text, categories, out):
    cats = set(categories or [])
    hl = " ".join((headline or "").split())
    if "Exploration Programs" not in cats:
        # rule 1b (round 6): a release filed under another category (a corporate update, a resource or study update,
        # a technical report) whose opening (headline, deck, first paragraph) itself states a drilled interval; never a
        # financing, deal or property-option release
        opening = hl + " . " + " ".join((text or "")[:OPEN_CHARS].split())
        if any(RE_DEALCAT.search(c) for c in cats) or not interval_claim(opening):
            return False, "not an exploration release"
    body = " ".join((text or "")[:LEDE_CHARS].split())
    if RE_COMMENTARY.search(hl + " . " + body):
        return False, "commentary"
    if RE_HOLDER.search(body):
        return False, "royalty holder, shareholder or portfolio investor on another company's results"
    # rule 3: one kind, three vocabularies; a claim of new results in the headline, the deck (sub-headline, highlight
    # bullets) or the statement itself outweighs them
    deck, st = statement(body)
    if any(rx.search(hl) or rx.search(st) for rx in (RE_LOGISTICS, RE_TARGETS, RE_RECAP)):
        if not (claims(hl) or claims(deck) or claims(st)):
            return False, "statement is drilling logistics, target work or a look back, not new assays"
    # rule 5 (round 6): no drill hole or core anywhere in the lede: surface sampling (grab, channel, chip, soil, till)
    if not RE_HOLEWORD.search(hl + " . " + (text or "")[:HOLE_CHARS]):
        return False, "no drill hole or core in the lede: surface sampling, not drill assays"
    full = " ".join((text or "")[:FULL_CHARS].split())
    w = old_figure(full, out or {})
    if w and not (claims(hl) or claims(deck) or claims(st)):
        return False, "top intercept quoted as earlier or someone else's work: " + w
    # rule 6 (round 7): the top intercept must be the release's own new drill figure; no claim outweighs it
    R = figure_reasons(full, out or {})
    if R:
        return False, R[0][1]
    return True, "reader reports new drill results"
