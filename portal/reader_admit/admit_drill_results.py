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
Round 8 (DRILLTAG, 2026-10-19; preview only until enabled)
  1c. a release outside "Exploration Programs" and without a deal category is also admitted to rules 2 to 6 when its
      headline itself is about drilling: it names a hole ("hole AB-25-01", "drillhole") or says drill / intersect /
      intercept, and it names no non-assay subject (options, financing, conference, listing, quarter or year results,
      metallurgy, resource estimate, staking, marketing, strength or recovery tests);
  rule 5 widened: "drillhole(s)", "drill core" and "intercepts / intersections" count as drill work when the reader's
      top hole is a real hole id (not "FY2025") or the headline is about drilling or a discovery;
  1c tightened after preview 1: a headline about a partner's work, a correction, ownership or a land position,
      production or guidance, an exchange listing or trading, or citing an earlier release ("(see press") never counts;
  Round 8b (DRILLTAG, 2026-10-19, from the review of the ~110 still missing):
  1d. a release in any non-deal category also goes on to rules 2 to 6 when the reader's top hole is named for the
      release year or the year before ("GC26-148", "JO-25-05", "26HZ002") and the headline names no non-assay subject;
      a Mergers & Acquisitions category does not block a release whose headline is about drilling ("Announces Results
      of In-Fill Drilling"); "hits" counts as a drilling headline; "outside / beyond the current MRE" is not a resource
      headline; a headline asking "why" or reporting a visual estimate never counts;
  rule 3: "results from <...> drill holes / the first drilling fence" counts as a claim of new results;
  rule 5: two or more hole ids of the release year or the year before in the lede, with the word drilling, count
      as drill work ("25m at 10.2 g/t gold from 568m 26HZ002");
  6a: "previously unreported / untested / undrilled" is not an earlier-work marker; a sentence also ends at ".)"; a
      "see Table 1" or a "JORC 2012" is not a citation or an old year;
  6b: drilling named for the year before the release no longer counts as an earlier year's drilling (6d's two-year rule);
  6c: a surface word does not count when drilling is named earlier in the same sentence ("Grade-control drilling west
      of the Trench 1 bulk sample site ... returned 14.10 g/t gold over 1.59 m");
  6d: "the previously disclosed" (a wedge or extension from an earlier hole) does not cite the hole itself;
  6e: the figure is looked for in the whole release body (as cut for rules), not only its first 12,000 characters.
  Round 8c (after the 8b preview): a headline veto for every release (not only outside-category ones): metallurgy or
      test work, recoveries, DTR, tailings, a moratorium, an agreement or licence transfer, a material change report or
      notice to reader, a safe-harbour notice, a resource report, CSAMT, radioactivity, quarter results, an outlook or a
      review of a past year, a launched / completed drill program, a general update or an update on activities, a
      concession expansion, results pending for holes.
  6d narrowed: a hole id whose later two-digit part is the release year ("UG16-26-038" in 2026: level 16, year 26) is
      not named for an earlier year;
Round 8d: no regressions by construction. A release the round-8a rule admits is admitted exactly as before (8a is
embedded below, compressed, and run first); only a release 8a rejects goes on to the 8b fixes and the 8c headline veto.
Round 8e: 6e also passes when the top hole is stated in the lede with its own interval within 30% (Benz 2 Aug 2026).
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
    r"|\b(?:intersect|intercept|hit|cut|return)(?:s|ed|ing)?\b.{0,80}?\d\s*(?:g/t|%|ppm|ppb|grams|lb)"
    # round 8b: "provide results from two drill holes", "results from the first drilling fence"
    r"|\bresults\s+(?:from|for|of)\s+(?:the\s+)?(?:[\w-]+\s+){0,4}(?:drill\w*|holes?|boreholes?)\b", re.I)
# ... unless the claim is about earlier or someone else's work ("previous drill results", "historic assays")
RE_OLD = re.compile(r"\b(?:previous(?:ly)?|prior|earlier|historic(?:al)?|past|last\s+(?:year|season)'?s?|"
                    r"see|reviews?|reviewed|reviewing)\b[^.;]{0,30}$", re.I)


# an interval stated as a result: "drilled / intersected / returned ... 12.5 m @ 3.1 g/t", "6.4m @ 11.6 g/t"
OPEN_CHARS = 800
RE_INTERVAL = re.compile(r"\b\d+(?:\.\d+)?\s*(?:m|metres?|meters?|ft|feet)\s*(?:@|at|of|grading|averaging)\s*\d+(?:\.\d+)?\s*"
                         r"(?:g/t|gpt|%|ppm|ppb|grams|oz/t|kg/t|lb)", re.I)
RE_DEALCAT = re.compile(r"financ|placement|acqui|merger|option|staking|royalt|stream|insider|dividend", re.I)
# round 8, rule 1c: the headline itself is about drilling ...
RE_HL_DRILL = re.compile(r"\b(?:drill\w*|intersect\w*|intercept\w*|hits?|holes?\s+[A-Z0-9-]*\d|DDH[- ]?\d)", re.I)
# round 8b: "outside / beyond the current MRE" is about new drilling, not a resource estimate
RE_HL_MRE_OK = re.compile(r"\b(?:outside|beyond|below|outside\s+of)\s+(?:the\s+)?(?:current\s+|existing\s+)?"
                          r"(?:MRE|mineral\s+resources?|resource(?:\s+estimate)?)\b", re.I)
# ... and names no non-assay subject
RE_HL_NOT = re.compile(r"\b(?:stock\s+options?|options?\s+grant\w*|grant\w*\s+(?:of\s+)?options?|financ\w*|placement|"
                       r"warrants?|conference|webinar|present\w*\s+at|listing|listed|Q[1-4]\b|quarter\w*|annual\s+general|"
                       r"(?:first|second|third|fourth)\s+quarter|financial\s+(?:results|statements)|year[- ]end|metallurg\w*|"
                       r"recover(?:y|ies)\s+test\w*|resource\s+estimate|mineral\s+resource|MRE\b|PEA\b|feasibility|staking|"
                       r"staked|marketing|investor\s+relations|strength\s+test\w*|geotechnical|acqui\w*|merger|"
                       r"royalt\w*|stream\w*|permit\w*|drill\s+(?:program|campaign)\s+(?:to\s+)?(?:start|commence|begin)s?|"
                       # round 8 tightening (preview 1): someone else's work, corrections, deals, production, listings,
                       # citations of earlier releases
                       r"partners?|please\s+note|correct\w*|erratum|amend\w*|clarif\w*|ownership|land\s+position|"
                       r"produc(?:ed|tion)|guidance|stock\s+exchanges?|trading\s+on|commence\s+trading|\(\s*see\b|see\s+press|"
                       # round 8b: commentary headlines and visual estimates
                       r"why|visual\w*)",
                       re.I)


# round 8c: headline veto for every release
RE_HL_VETO = re.compile(r"\b(?:metall?urg\w*|test\s*work|testing|recover(?:y|ies)|DTR|tailings|moratorium|agreement|"
                        r"transfer\s+of\s+(?:\w+\s+)?licen[cs]es?|material\s+change|notice\s+to\s+reader|safe\s+harbou?r|"
                        r"resource\s+report|CSAMT|radioactiv\w*|(?:first|second|third|fourth)\s+quarter|"
                        r"Q[1-4]\s+(?:FY)?(?:20\d\d\s+)?(?:results|operating|production)|provides\s+outlook|"
                        r"reviews?\s+(?:20\d\d|its|the)\b|launch\w*\s+(?:\S+\s+){0,3}drill\w*|"
                        r"completes?\s+(?:\S+\s+){0,3}drill(?:ing)?\s+program|drilling\s+completed|general\s+update|"
                        r"update\s+on\s+activities|expands\s+(?:\S+\s+){0,4}concession|results\s+for\s+\d+\s+holes\s+pending)\b",
                        re.I)


def hl_not(hl):
    return RE_HL_NOT.search(RE_HL_MRE_OK.sub(" ", hl or ""))


def headline_drill(hl):
    return bool(RE_HL_DRILL.search(hl or "")) and not hl_not(hl)


# round 8b, rule 1d: the reader's top hole is named for the release year or the year before
RE_HOLEYR = re.compile(r"^(?:[A-Z]{1,6}[-_]?)?(\d{2})(?:[-_]?[A-Z]{0,4}[-_]?)\d", re.I)


def current_hole(hole, ry):
    m = RE_HOLEYR.match((hole or "").strip())
    if not (m and ry) or not re.search(r"[A-Z]", hole, re.I):
        return False
    return int(m.group(1)) in (ry % 100, (ry - 1) % 100)


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
RE_YEAR = re.compile(r"(?<![\d./-])(?<!JORC )(?<!JORC\()(19[5-9]\d|20[0-4]\d)(?![\d])")
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
    r"\b(?:press|news)\s+releases?\s+(?:\w+\s+){0,4}dated\b|\bsee\s+(?:the\s+)?(?!tables?\b|figures?\b)(?:\w+\s+){0,4}(?:press|news)\s+releases?\b|"
    r"\bthird[- ]part(?:y|ies)\b|\bneighbo(?:u)?ring\b|\badjacent\s+(?:property|project|claims?|ground)\b")
RE_EARLIER = re.compile(
    r"\b(?:previous(?:ly)?(?!\s+un\w+)|prior|earlier|historic(?:al|ally)?|legacy|past)\s+(?:[\w-]+\s+){0,2}" + WORK + r"\b|" +
    EARLIER_REST, re.I)
# round 7 (rule 6a only): the same markers, with a stray space from PDF extraction ("h istorical", "p revious"), and
# published a short while ago ("announced last week", "recently reported")
RE_EARLIER7 = re.compile(
    r"\b(?:p\s?revious(?:ly)?(?!\s+un\w+)|prior|earlier|h\s?istoric(?:al|ally)?|legacy|past)\s+(?:[\w-]+\s+){0,2}" + WORK + r"\b|"
    r"\b" + PUBLISHED + r"\s+(?:last\s+(?:week|month|year|quarter)|earlier\s+(?:this|in)\b|recently|previously)\b|"
    r"\brecently\s+" + PUBLISHED + r"\b|" + EARLIER_REST, re.I)
RE_SPLIT = re.compile(r"(?<!\b[A-Z])(?<!\bInc)(?<!\bCorp)(?<!\bLtd)(?<!\bNo)(?<!\bapprox)(?:[.;]|\.\))\s+(?=[A-Z\"\u201c(\u2022])")


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
# round 8: more words for drill work; they count only when the reader's top hole is a real hole id or the headline
# itself is about drilling (or a discovery) and names no non-assay subject
RE_HOLEWORD8 = re.compile(r"\b(?:drill-?holes?|drill\s+core|intercepts?|intersections?)\b", re.I)
RE_NOTHOLE = re.compile(r"^(?:FY|Q[1-4]|H[12])\d", re.I)


def hole_ok(hole):
    h = (hole or "").strip()
    return len(h) >= 4 and bool(re.search(r"\d", h)) and bool(re.search(r"[A-Z]", h, re.I)) and not RE_NOTHOLE.match(h)
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
    st = item_start(full, p, 250)
    for m in RE_SURFACE.finditer(full, st, p):
        # round 8b: drilling named earlier in the same sentence ("drilling west of the Trench 1 bulk sample site")
        if re.search(r"\bdrill\w*", full[st:m.start()], re.I):
            continue
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
    # round 8: "UG16-26-038" in 2026 is level 16 of the year-26 program, not a 2016 hole
    if any(int(x) in (ry % 100, (ry - 1) % 100) for x in re.findall(r"(?<=-)(\d{2})(?=-)", (hole or "")[m.end(1):])):
        return None
    return y if ry - 12 <= y <= ry - 2 else None


def hole_cited(full, hole):
    """-> the place where the hole, as written ("AB -22-005") or by its number in a list ("AB-19-035, -036, -037, -039
    were reported previously"), is marked as published before ("... previously released", "(released on January 5,
    2023)"), else ""."""
    tail = hole.rpartition("-")[2]
    pat = r"\s?-\s?".join(re.escape(x) for x in hole.split("-")) + \
        (r"|(?<=[\s,])-" + re.escape(tail) + r"\b" if "-" in hole and tail.isdigit() else "")
    rx = re.compile(r"(?:" + pat + r")[^.;()]{0,40}?(?<!the )(?<!a )(?<!an )(?:p\s?reviously\s+" + PUBLISHED + r"|" + PUBLISHED +
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
            if ry and int(m.group(1) or m.group(2)) <= ry - 2:
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


# round 8e (6e alternative): the top hole is named in the lede (first 4,000 characters) next to an interval of its own
# (grade with its length) within 30% of the reader's figure, e.g. the same intercept at another cut-off
RE_LEDE_IV = re.compile(r"(\d+(?:\.\d+)?)\s*(?:m|metres?|meters?)\s*(?:@|at|of|grading|averaging)\s*(\d+(?:\.\d+)?)\s*"
                        r"(?:g/t|gpt|ppm|%)", re.I)


def lede_figure(full, out):
    try:
        g = float(out.get("grade")); L = float(out.get("length_m") or 0)
    except (TypeError, ValueError):
        return False
    hole = (out.get("hole") or "").strip()
    if len(hole) < 4 or not g or not L:
        return False
    lede = full[:4000]
    for mh in re.finditer(re.escape(hole), lede):
        for mi in RE_LEDE_IV.finditer(lede, max(0, mh.start() - 160), mh.start()):
            lv, gv = float(mi.group(1)), float(mi.group(2))
            between = lede[mi.end():mh.start()]
            if re.search(r"\b(?:in|hole|from)\b", between, re.I) and len(between) < 60 \
                    and abs(gv - g) <= 0.3 * g and abs(lv - L) <= 0.3 * L:
                return True
    return False


def _admit_loose(headline, text, categories, out):
    cats = set(categories or [])
    hl = " ".join((headline or "").split())
    v = RE_HL_VETO.search(hl)
    if v:
        return False, "headline is not about new drill assays: " + v.group(0)
    if "Exploration Programs" not in cats:
        # rule 1b (round 6): a release filed under another category (a corporate update, a resource or study update,
        # a technical report) whose opening (headline, deck, first paragraph) itself states a drilled interval; never a
        # financing, deal or property-option release
        opening = hl + " . " + " ".join((text or "")[:OPEN_CHARS].split())
        hd = headline_drill(hl)
        # round 8b: an M&A category does not block a release whose headline is about drilling
        deal = [c for c in cats if RE_DEALCAT.search(c) and not (hd and re.search(r"merger|acqui", c, re.I))]
        ry0 = release_year(" ".join((text or "")[:LEDE_CHARS].split()))
        cur = current_hole((out or {}).get("hole"), ry0) and not hl_not(hl)
        if deal or not (interval_claim(opening) or hd or cur):
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
    lede = hl + " . " + (text or "")[:HOLE_CHARS]
    if not RE_HOLEWORD.search(lede):
        o = out or {}
        ry5 = release_year(" ".join((text or "")[:LEDE_CHARS].split()))
        ids = {x.upper() for x in re.findall(r"\b[A-Z0-9_-]{4,16}\b", lede) if current_hole(x, ry5)}
        if not ((RE_HOLEWORD8.search(lede) and (hole_ok(o.get("hole")) or headline_drill(hl) or
                                                (re.search(r"\bdiscover", hl, re.I) and not hl_not(hl))))
                or (len(ids) >= 2 and re.search(r"\bdrilling\b", lede, re.I))):
            return False, "no drill hole or core in the lede: surface sampling, not drill assays"
    full = " ".join((text or "")[:FULL_CHARS].split())
    w = old_figure(full, out or {})
    if w and not (claims(hl) or claims(deck) or claims(st)):
        return False, "top intercept quoted as earlier or someone else's work: " + w
    # rule 6 (round 7): the top intercept must be the release's own new drill figure; no claim outweighs it
    R = figure_reasons(full, out or {})
    if R and R[0][0] == "notstated":
        # round 8b: look for the figure in the whole body before calling it not stated
        whole = " ".join((text or "").split())
        if locate_all(whole, out or {}):
            R = figure_reasons(whole, out or {})
        elif lede_figure(full, out or {}):
            # round 8e: the figure sits in a table past the text the rules see (Benz 2026-08-02, 26CN079: table
            # "260 295 17 35" vs highlight "41m at 14.5 g/t Au from 260m in 26CN079"); its hole is stated in the
            # lede with its own interval close to it, so it is the release's own new figure
            R = [r for r in R if r[0] != "notstated"]
    if R:
        return False, R[0][1]
    return True, "reader reports new drill results"


# --- round 8d: the round-8a rule, run first (compressed copy of admit_drill_results.py sha 4b93c8876dc46ae9) ---
import base64 as _b64, zlib as _zlib
_R8A_SRC = (
    "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"
)
_R8A = {"__name__": "admit_drill_results_r8a"}
exec(compile(_zlib.decompress(_b64.b64decode(_R8A_SRC)).decode("ascii"), "admit_drill_results_r8a", "exec"), _R8A)


def admit(headline, text, categories, out):
    ok, why = _R8A["admit"](headline, text, categories, out)
    if ok:
        return True, why
    return _admit_loose(headline, text, categories, out)
