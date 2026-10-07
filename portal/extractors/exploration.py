"""Exploration Programs reader, facts-store version (EXPL_V1, 2026-09-21).

The source of the Exploration Programs page once it passes the accuracy gate. Written against the 50-release
set Justin confirmed on 2026-09-21 (46 releases with rows, 155 rows).

The row shape and the rules are Justin's (2026-09-21):

  1. ONE ROW PER FIELD PROGRAM a release reports: drilling, geophysics (IP, magnetics, EM, gravity, LiDAR,
     radiometrics, MT) or ground work (soil, till, rock or channel sampling, mapping, prospecting, trenching).
  2. STATUS as of the release: planned, started, underway or completed.
  3. COMPLETED PROGRAMS COUNT even when mentioned as background, and so do PREVIOUS OWNERS' programs
     (historical = True, operator = the company that ran them) when the release gives a fact about them: the
     company, a year, metres, holes or line-km.
  4. NOT ROWS: mine development, resource or study work, option work commitments, government surveys, other
     properties, the company's About paragraph, and one-line intentions with no fact.

The reader favours precision. It emits a row for the program the headline is about, and for body sentences that
state a program with a clear status and a distinguishing fact (a year, a phase, metres or holes). A sentence that
only names a kind of work in passing is not read as a program.

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per row (ordinal 0..n-1)
to_prediction(records) -> dict|None    what the accuracy judge compares

1.2.2 (2026-09-26): onto the shared project-name helper portal/project_names.py, conservatively. The release's main
project stays 1.2.1's choice (its own finder, headline first, tuned to this page: helper-first names made worse
names in the full comparison -- pits and zones such as "Wenot" for Omai, rows split by sub-project names); when 1.2.1
finds none, the helper's main project (PN.primary) in this page's form (no trailing Project/Property/Claims or metal
words, trimmed as before: "Hemlo Gold Project" -> "Hemlo"; a name 1.2.1 would not keep, such as "RC Gold Project",
is dropped), and only when 1.2.1's own finder also names it (a region or a word like "Development" is not taken).
The fingerprint follows the helper (portal/fingerprint.py). self_test returns the number of failures.

1.2.3 (2026-09-30, ACC150 fix-list item 2: 64.8% of tagged releases picked up, rows 75% right). By error kind:
  - Property names. Commodity words however listed come off ("Nicobi Nickel, Copper & Cobalt Project" is Nicobi, not
    "Cobalt"); a leading commodity word that starts the name stays ("Silver Queen", "Gold Standard"); a trailing
    direction stays ("Great Northern"); more title-case headline words end a name ("Include", "Well", "To Sell",
    "Further Delineates"); a headline name the body never uses is a fragment and is not taken; people's adjectives
    ("Mongolian"), licence kinds, company names and names led by another company's name ("Kinross Bald Mountain")
    are not properties; licences, tenements and patents are landholdings; a property named by its initials gets its
    name ("EDM" -> El Dorado Monserrat).
  - Whose property. With the issuer's name words, another company's possessive ("Wallbridge's Fenelon", "Aris Mining's
    Juby") is not the issuer's property: a program on it is not emitted; the issuer's own or a common word's comes off.
    A sentence naming another company by its ticker off the release's property is that company's program.
  - Which property. A program is filed under the property named nearest before it in its sentence (a bare "At
    Cervantes, ..." counts); a deposit, mine or prospect inside the release's property is that property; a mine or
    deposit in the headline gives way to the property the body calls a project; the headline program's facts are not
    taken from a sentence about another property.
  - One row per program. One program read twice (the same metres, or the same four-plus holes, with no season, phase
    or operator telling them apart; started/underway/planned, or underway and done) is one row; a drilling and a
    ground row from one sentence, or one program sentence naming several kinds of work, are one row (drilling if it
    drills); a general field program of the same status and season is the drilling program; the headline's "Drilling
    Underway" and the body's figures to date are one underway row; later planned phases are one row, the first's.
  - Sizes from the text. Not an intercept's width ("Over 72 m"), a working's length (adits, trenches), a results batch
    ("results of the remaining 6 holes", "All three drillholes intercepted"), earlier holes, or the next sentence's
    other program; "N of the planned M holes" is M; an enlarged program has its new size; a program underway is sized
    by its planned total ("3,721 m ... out of the planned 5,728 m").
  - Not programs. The drilling database behind a resource estimate or study, an obligation or earn-in requirement, a
    plan that depends on a condition ("If successful, ... the option to"), a marketing or housekeeping release's
    program without a size, a testwork release's "field program", a program ahead on a property the headline says is
    sold.
  - Programs in results, financing and corporate releases. A program the release says is going on now ("Drilling is
    ongoing", "the drilling program currently underway") is a row without a size; a program sized in metres is
    drilling; the headline's "at X" names the property when the body does.
  - Status. An "update" headline takes the lead's own status; "Arrival of Drill Rig" is a start; "Completes Three
    Additional Holes" is underway; a survey that found something is finished; "Expands Strategic Position" and
    "Continues to Return High Grade" are not a program's state; holes "now completed" or the first holes of a current
    program are underway; a verb about something else in the headline (a PEA underway) is not the program's.
  - Season. A program started or underway at the release date is that year's.
  Key gate (same version, answer-key review): a program underway and one planned for a later year than the release
    are two rows; "all four drill holes intersected ..." counts the phase's holes (four or more, not a batch the text
    names as first/remaining/latest, not "holes for which assays have been received"); "500 metres completed of the
    planned campaign of up to 5,000 metres" is progress, sized 5,000; a headline group of patents, claims or licences
    that the body places inside a named project or property ("the Burnthut Project, which is composed of ... patents",
    "located entirely within the Eliza Project claim block") is that project.
  Only this file changes; no other reader imports or fingerprints it.
  Full-text losses (2026-10-01, same version; FIX3: on the box's full release texts 1.2.3 dropped releases that live
    showed, most of them real news). By kind:
  - Whose property, on full texts. A subsidiary or operating company named after the property ("Golden Promise Mines
    Inc.", "Ruddock Creek Mining Corporation") is not another company; nor is one named across a sentence end or led by
    "Golden"; a place both are named after, with a direction ("Troilus East"), stays; the issuer's short name and the
    lead's subject ("Playfair is now drilling") and two-character names ("E3") are the issuer's; a headline possessive
    is the issuer's unless the release names that company ("Patriot Gold's Windy Peak"), and a person's or place's
    possessive is part of the name ("Tom's Pediment", "Lewis Pilley's"); a royalty holder's release does not take the
    operator's drilling as its own.
  - Names. A place or licence word ends a name ("Root Spring", "Mesa Well", "Tay Exploration License"), commodity words
    in lower case and a quoted nickname come off ("Deer Horn polymetallic property", 'Pardo "River of Gold" Project'),
    "Prospect Valley", "J&L", "Battery Hill", a lower-case "permit", a brine "Salar"; not "Land Use", a direction or
    holding alone, "A MAJOR INCREASE IN PROJECT", "Yukon Metals'", "Miocene-aged"; a zone by its property's possessive
    ("Opemiska's Saddle Zone"), the name before a "drill program" ("Murphy Lake"), the start of a headline place the body
    uses ("Thor", "Nickel Mountain", "Nisk"), the issuer's lower-case "complex", a portfolio update's property heading;
    a headline prospect keeps its name against a project the body names once, late.
  - Releases with no text (a feed stub, a disclaimer only): the headline's name and program stand alone.
  - Sizes. The program's own figure after a results batch ("the final nine holes completed during the 10,217-metre
    winter drill campaign"); a size in a budget's or a plan's words.
  - Status and facts. "Ground Geophysical Survey" is a program, not "ground"; "Nearly Complete", "Planning",
    "Delayed", "Updates", "Finds"; a quarter that times a program ("the Q2 RC Drilling Program") is not quarterly news;
    a regulator's "Water Board" is not the company's; "planning to conduct"; the continuing or ongoing drilling a release
    reports results from or is about, a campaign that "continues"; "The program comprised 14 holes" is finished; a season
    that names the program ("winter drill program"), a permit for a planned one, a survey "just completed"; "the dry
    season has started ... will carry out" is still ahead; going on now does not turn the headline's start into
    underway; a survey to guide drilling is the headline's program.
  - Not programs, more exactly. Drilling for a mine's construction ("sterilization", "pre-construction", "pilot hole")
    when it is the drilling named; a resource "supported by N m of drilling"; but a database sentence that also says the
    drilling goes on is read; a marketing headline that also reports a discovery keeps its rows.
  - Text formats. "To view an enhanced version of Figure 1 ... <link>" and a caption run into the next sentence are
    sentence breaks; a word split in a PDF ("will next carry o ut") is still read.

1.2.4 (2026-10-02, FIX4: one release with a 30,832-character list of long hyphenated links took 14 s off-box and 49 s on
the box; ACC150b re-check: rows 88-90% right but only ~30% of labelled rows captured, 41 tagged releases with labelled
rows given none). By kind:
  - Speed. A token of 40+ non-space characters (a URL, a file name) is masked, offsets kept, before any property-name
    pattern runs over the text (_projects and every other _PROJ_RX / _CAPNAME search): the name pattern backtracked on
    long hyphenated tokens. Outputs are unchanged on every labelled set, the answer key and the lost releases.
  - Drill-results releases. A headline that reports drill intercepts ("Intersects 0.54% Cu Eq over 180.8m", "Drills
    VMS ... On Its California Lake Project", "hits 25 metres of Massive Sulfides") and gives no drilling row gets one
    row for the release's drilling: underway when the release says the drilling goes on ("advancing with two drill rigs
    in operation", "scheduled to continue", "is still being drilled", "first hole of the fall program"), else
    completed; no size. Not for historical data, re-assays, resource or study news, a royalty holder's or optionor's
    release (the operator's or optionee's drilling), or a sampling headline.
  - Programs named in passing. A finished survey named by kind no longer needs "recently" ("a DCIP survey conducted
    earlier this year"); a finished survey or field program, or any program that has started, named without a year or
    size is one row when the release gives no other row of that kind on the property ("Soil samples were collected
    over the grid", "field crews have mobilized to its Golden Frac Sand Property"); not work on survey data
    (interpretation, models, compilations), procedure or disclaimer sentences, negations, older or other companies'
    work, or a mine's construction drilling; a start told with its end is completed, one still ahead ("when the drill
    rig mobilizes in mid-June") planned; field work at the same stage as a drill program is that program.
  - Several mentions in one sentence. When the first mention of a kind of work says nothing of its state, a later one
    that does is read ("intersected by drill hole ST22-10 in the 2022 drill campaign").
  - Programs named by year. "the 2022 drilling at the Dayton target", "Drilling during 2021", "Scout drilling of 5
    holes in 2022", "a survey in 2021", "(2023)" name that year's finished program (not "prior" drilling, not with a
    company's name between year and drill word, not tables); a count between the year and the drill word is the
    program's ("2023 14 HQ drill holes").
  - Programs ahead. A start timing is the guide's fact for a planned program ("scheduled to commence July 22nd",
    "planned for the second half of 2023", "Q3 of this year", "to begin shortly"), also for a planned survey without a
    season; "will be followed up with drilling", "will be drill tested", "will follow up" are plans.
  - Headlines and words. "Initiates NWT Exploration", "Exploration and Technical Program", "Exploration Activities" are
    the release's field program (drilling when the lead says drilling begins); "has drilled N metres", "N holes have
    been completed" (not historical holes), "Drill Mobilization", "gravity gradiometric survey".
  - Text formats. Symbol-font bullets (private-use glyphs), squares, arrows and check marks end a sentence, so a bullet
    list is read item by item.
  - Names. A property known by three capitals ("Origen LGM and Wishbone Update", "its 100% owned LGM property") can be
    the headline's property, as a longer name can (not an alias in brackets, "Ball Creek West (BAM)").
  Only this file changes; no other reader imports or fingerprints it.

Self-tests: python3 -m portal.extractors.exploration
"""
from __future__ import annotations

import re
import unicodedata

from portal import facts as F
from portal import fingerprint as FP
from portal import project_names as PN   # 1.2.2: the shared project-name helper

NAME = "exploration"
VERSION = "1.2.4"  # 2026-09-30: ACC150 fix-list item 2: property names, one row per program, sizes from the text, programs in results releases; 2026-10-01: names, sizes, status cues and text formats on the full release text; full-text losses fixed; 2026-10-02: long link lists masked before name patterns (speed); capture: drill-results releases, finished surveys and started programs named in passing, programs named by year or with a start timing, bullet lists, three-capital property names
KIND = "expl_program"
TAG = "Exploration Programs"
TEXT_CAP = 40000

TXT_FIELDS = ("program_type", "project", "status", "season", "phase", "operator", "drill_method", "survey_type",
              "currency", "target_metal", "contractor")
NUM_FIELDS = ("metres", "holes", "line_km", "budget", "rigs", "historical")

# ------------------------------------------------------------------ text preparation
_FLS = re.compile(r"(?i)\b(?:cautionary\s+(?:note|statement)s?\s+(?:regarding|on|concerning)\s+forward|forward[\s\-]+"
                  r"looking\s+(?:statements?|information)\s*(?:and|&)?\s*(?:cautionary)?[^.]{0,40}?(?:\n|:|This\s+"
                  r"(?:news\s+)?release)|neither\s+(?:the\s+)?(?:tsx|canadian\s+securities)|references?\s*:?\s*\n)")
_ABOUT = re.compile(r"(?:^|\s)About\s+(?:the\s+Company|[A-Z][\w&.'’\-]*(?:\s+[A-Z][\w&.'’\-]*){0,5})\s*(?::|\s(?=[A-Z][a-z]+\s"
                    r"(?:is|was|Inc|Corp|Ltd|Limited|Resources|Metals|Mining|Gold|Silver|Copper|Energy|Minerals)\b))")


_MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
_DATE = re.compile(r"(?i)\b(" + _MONTH + r"\s+\d{1,2}(?:\s*(?:st|nd|rd|th))?\s*,?\s*)((?:19|20)\d\d)\b|\b(\d{1,2}\s+" + _MONTH +
                   r"\s*,?\s*)((?:19|20)\d\d)\b")


def _release_year(b):
    m = _DATE.search(b[:2500])
    if m:
        return int(m.group(2) or m.group(4))
    return None


def _undate(b):
    """Dates ('May 20, 2025', 'see news release dated July 18, 2024') are not programme years."""
    return _DATE.sub(lambda m: (m.group(1) or m.group(3)).rstrip(" ,") + " DATE", b)


def _prepare(headline, body):
    b = (body or "")[:TEXT_CAP]
    m = _FLS.search(b, 600)
    if m:
        b = b[:m.start()]
    b = unicodedata.normalize("NFKC", b).replace(chr(160), " ")
    m = _ABOUT.search(b, 800)
    if m:
        b = b[:m.start()]
    # (2026-10-01, full text: also "To view an enhanced version of Figure 1, please visit: <link>", which runs a caption
    # into the next sentence)
    b = re.sub(r"(?i)To\s+view\s+an\s+enhanced\s+version\s+of\s+(?:(?:this|the)\s+\w+|fig(?:ure|\.)?\s*[\w.\-]*)[^.]{0,40}?"
               r"https?://\S+", " . ", b)
    b = re.sub(r"https?://\S+", " ", b)
    b = re.sub(r"\s+", " ", b)
    # 1.2.1: a PDF body breaks a figure at its comma ("up to 3 ,000 metres of diamond drilling", AUEN.V)
    b = re.sub(r"(?<=\d) ,(?=\d{3}\b)", ",", b)
    b = re.sub(r"\b(CDN|CAD) \$", r"\1$", b)       # "This CDN $1,000,000 winter drilling program" (TRAC.CN)
    # 1.2.3: a hyphenated name or commodity pair broken at the hyphen ("Vardenis Cu- Au Property", "Shasta Gold
    # -Silver Project") is joined again
    b = re.sub(r"(?<=[A-Za-z])(?:- | -)(?=[A-Z])", "-", b)
    h = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", headline or ""))
    h = re.sub(r"(?<=[A-Za-z])(?:- | -)(?=[A-Z])", "-", h)     # 1.2.3
    # 1.2: a PDF body splits a word after its capital ("the V olney Project"); where the headline carries the
    # whole word, the body gets it back, and the project has a name (ROAR.V)
    hl = h.lower()
    b = re.sub(r"\b([B-HJ-Z]) ([a-z]{2,})\b",
               lambda m: m.group(1) + m.group(2) if re.search(r"\b" + (m.group(1) + m.group(2)).lower() + r"\b", hl)
               else m.group(0), b)
    return h.strip(), b.strip()


def _drop_title(b, title):
    """The headline is usually repeated at the top of the body, run into the dateline and the lead sentence."""
    if len(title) < 12:
        return b
    words = re.findall(r"\S+", title)[:14]
    rx = r"\s*".join(re.escape(w) for w in words)
    m = re.search(rx, b[:3000], flags=re.I)
    if not m:
        return b
    rest = b[m.end():]
    # the rest of the title and the dateline, up to the lead's first verb
    d = re.search(r"(?i)\b(?:DATE|/CNW/|/PRNewswire/|Newsfile\s+Corp\.?|ACCESSWIRE|GLOBE\s+NEWSWIRE)\b[^.]{0,80}?(?:–|-|—|:)\s", rest[:600])
    if d:
        rest = rest[d.end():]
    return b[:m.start()] + " . " + rest


_ACRO = {"IP", "EM", "RC", "JV", "NI", "CU", "PGE", "REE", "VMS", "TSX", "CSE", "BC", "B.C.", "MT", "VTEM", "ZTEM",
         "HQ", "NQ", "RAB", "LIDAR", "UAV", "NI-CU-PGE", "CU-AU", "AU", "AG", "U3O8", "Q1", "Q2", "Q3", "Q4", "USA", "US",
         "NWT", "NT", "NU", "BC's"}


def _title(h):
    """The headline without the lead some feeds append to it."""
    m = re.search(r"\s(?:is\s+pleased\s+to|announces?\s+that|\(\s*[\"“]|\((?:TSX|CSE|NYSE|NASDAQ|OTC)|[A-Z][\w&.'’\-]*"
                  r"(?:\s+[A-Z][\w&.'’\-]*){0,4}\s+(?:Inc|Corp|Ltd|Limited)\.?\s*\()", h[15:])
    t = (h[:15 + m.start()] if m else h).strip()
    letters = [c for c in t if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) > 0.8 * len(letters):
        t = " ".join(w if w in _ACRO or re.match(r"^(?:\d.*|I{1,3}V?|[A-Z]+\d.*)$", w) else
                     "-".join(p.capitalize() for p in w.split("-")) for w in t.split())
    return t


_BULLETS = "\u25e6\u2023\u2043\u2219\u25a0\u25a1\u25c6\u2666\u27a2\u27a4\u2713\u2714\uf020-\uf0ff"


def _sentences(text):
    # 1.2.4: more bullet glyphs end a sentence -- a PDF's Symbol-font bullet (U+F0B7 and its kin), squares, diamonds,
    # arrows, check marks -- so a bullet list is read item by item, not as one 2,000-character sentence
    text = re.sub(r"\s+[" + _BULLETS + r"]\s+", " \u2022 ", text)
    parts = re.split(r"(?<=[.;!?])\s+(?=[A-Z“\"•▪(])|\s+[•▪●]\s+|\s+-\s+(?=[A-Z])", text)
    return [p.strip() for p in parts if len(p.strip()) > 12]


# ------------------------------------------------------------------ vocabulary
_NUMW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
         "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "a single": 1,
         "single": 1}
_NUM = r"(?<![\d,.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|" + "|".join(sorted(_NUMW, key=len, reverse=True)) + r")"

_DRILL = re.compile(r"(?i)\b(?:drill(?:ing)?\s+(?:program(?:me)?|campaign|plan)|(?:diamond|core|RC|reverse\s+circulation|"
                    r"sonic|aircore|air\s+core|RAB|auger|percussion)\s+drill(?:ing|holes?)?|drill\s*holes?|drilling|"
                    r"drill\s+(?:crews?|rigs?|test\w*)|(?:maiden|inaugural|first|initial)\s+drill\w*|"
                    # 1.2.3: a program sized in metres is drilling ("the ongoing 5,000-metre campaign", "10,000 metres of
                    # the 15,000 metre program"), and so are metres drilled ("92,000 metres have been drilled to date")
                    r"[\d,.]+\s*(?:-\s*)?(?:metres?|meters?|m)\s+(?:(?:RC|diamond|core|drill(?:ing)?|exploration)\s+)?"
                    r"(?:program(?:me)?|campaign)|(?:metres?|meters?|holes?)\s+(?:have|has)\s+(?:now\s+)?been\s+drilled|"
                    # 1.2.4: metres or holes the company has drilled ("it has drilled approximately 2700 meters of its
                    # planned 3700 meter summer exploration program", "Ten holes have now been completed"), and the
                    # drill's mobilization ("Drill Mobilization Underway")
                    r"(?:has|have)\s+(?:now\s+)?drilled\s+(?:approximately\s+|about\s+|over\s+|a\s+total\s+of\s+)?[\d,.]+\s*"
                    r"(?:metres?|meters?|m|holes?)|(?<!historical\s)(?<!historic\s)holes?\s+(?:have|has)\s+(?:now\s+)?been\s+(?:completed|drilled)|"
                    r"drill\s+mobili[sz]ation)\b")
_GEO = re.compile(r"(?i)\b(?:geophysic\w*|induced\s+polari[sz]ation|IP\s+(?:survey|program|lines?|geophysic\w*)|"
                  r"magnetic\s+survey|mag\s+survey|aeromagnetic\s+survey|magnetometer\s+survey|drone\s+mag\w*|VTEM|ZTEM|"
                  r"TDEM|MLEM|electromagnetic\s+survey|EM\s+survey|gravity\s+(?:gradiometr\w+\s+)?survey|lidar\s+survey|lidar|radiometric\s+"
                  r"survey|magnetotelluric|mobile\s*mt|airborne\s+(?:\w+\s+){0,3}?survey)\b")
_GRD = re.compile(r"(?i)\b(?:soil\s+(?:sampl\w+|geochem\w*|survey|grid|program)|till\s+(?:sampl\w+|survey)|HMC\s+sampl\w+|"
                  r"prospecting(?:\s+program)?|geological\s+mapping|mapping\s+program|trench(?:es|ing)?(?:\s+program)?|"
                  r"channel\s+sampl\w+|rock\s+(?:chip\s+|grab\s+)?sampl\w+|grab\s+sampl\w+|field\s+(?:program(?:me)?|work|"
                  r"season|campaign|crews?)|fieldwork|sampling\s+program|geochemical\s+(?:survey|sampling|program)|"
                  r"surface\s+(?:sampl\w+|exploration)|ground\s+exploration(?:\s+program)?)\b")
# 1.2.4 (capture): more headline names for the release's field program ("Commences Advanced 2026 Exploration and
# Technical Program", "Outlines Upcoming Exploration Activities At", "Initiates NWT Exploration")
_EXPL_HL2 = re.compile(r"(?i)\b(?:exploration\s+(?:and\s+[\w-]+\s+)?(?:program(?:me)?s?|activities)|"
                       r"(?:initiates|begins|starts|launches|commences|resumes)\s+(?:[\w-]+\s+){0,2}?exploration)\b")
_EXPLPROG = re.compile(r"(?i)\b(?:exploration\s+(?:program(?:me)?|campaign|work\s+program)|work\s+program)\b")

_ST = {
    "completed": re.compile(r"(?i)\b(?:successful(?:ly)?(?!\s+(?:in\s+)?(?:intercept|intersect|return|hit|encounter|confirm|identif|"
                            r"delineat|test|target|locat|expand|extend|defin))|complet(?:ed|es|ion)|concluded|finished|wrapped\s+up|were\s+(?:collected|drilled|"
                            r"completed)|was\s+(?:flown|completed|conducted)|has\s+drilled|drilled\s+(?:in\s+)?(?:19|20)\d\d|"
                            r"carried\s+out|conducted|totall?(?:ing|ed))\b"),
    "started": re.compile(r"(?i)\b(?:commenc(?:ed|es|ing|ement)|began|begun|begins|started|starts|mobiliz\w+|mobilis\w+|"
                          r"launch(?:ed|es|ing)?|initiat(?:ed|es|e)|kick(?:ed|s)?\s+off|resum(?:ed|es|ption)|is\s+now\s+"
                          r"underway|has\s+begun|have\s+begun)\b"),
    "underway": re.compile(r"(?i)\b(?:(?:nearly|almost|substantially)\s+complete\w*|underway|under\s+way|ongoing|in\s+progress|continu(?:es|ing)|to\s+date|progressing|"
                           r"currently\s+(?:being|drilling|testing|conducting|carrying\s+out|undertaking|running))\b"),
    "planned": re.compile(r"(?i)\b(?:plan(?:s|ned)?\s+(?:to|for|a|an|the)|planned|"
                          # 2026-10-01 (full text): "is also planning to conduct a 3,000 metre drill program"
                          r"planning\s+(?:to\s+(?:conduct|commence|begin|start|drill|complete|carry\s+out|undertake)|a|an)\b|will\s+(?:commence|begin|start|test|"
                          r"include|consist|comprise|drill|be\s+(?:drilled|conducted|carried|completed|drill[\s-]+tested|followed[\s-]+up)|"
                          # 1.2.4: "will be followed up with diamond drilling programs during the second half of 2022",
                          # "Targets will be drill tested in Q3 of 2022", "Our H2 2019 drill program will follow up on"
                          r"follow\s+up)|to\s+(?:commence|"
                          r"begin|start)|proposed|upcoming|scheduled|expected\s+to\s+(?:commence|begin|start)|intends?\s+"
                          r"to|prepar(?:es|ing|ations?)\s+for|fully\s+(?:funded|permitted)|permitted|budget(?:ed)?\s+(?:of|"
                          r"for)|design(?:ed|ing)\s+(?:a|the)|ready\s+for|finaliz\w+)\b"),
}
_HL_ST = [
    ("completed", re.compile(r"(?i)\b(?:complet(?:es|ed|ion\s+of)|concludes|finishes|wraps\s+up)\b")),
    ("started", re.compile(r"(?i)\b(?:arriv(?:al|es|ed)\s+of|arrives|commenc(?:es|ed|ement\s+of|ing)|begins|began|starts|started|start\s+of|mobiliz\w+|"
                           r"mobilis\w+|launch(?:es|ed)|initiat(?:es|ed)|kicks\s+off|resum(?:es|ption)|underway|is\s+on)\b")),
    ("underway", re.compile(r"(?i)\b(?:updates?|continues|progress|progressing|ongoing|expands|advances(?=\s+(?:[\w-]+\s+){0,3}drill)|"
                            # 2026-10-01 (full text): "First Phase of Trenching Nearly Complete"
                            r"(?:nearly|almost|substantially)\s+complete|nearing\s+completion)\b")),
    # (2026-10-01, full text: "Also Planning 3,000 Metre Drill Program", "Drilling Delayed Due To Wildfire")
    ("planned", re.compile(r"(?i)\b(?:plans?|planned|planning|delayed|postponed|prepares|preparations|to\s+commence|to\s+begin|to\s+start|ready\s+for|"
                           r"announces\s+(?:(?:its|a|an|the|new|\d{4})\s+)*(?:[\w-]+\s+){0,2}(?:drill(?:ing)?\s+(?:program|plans?|campaign)|exploration\s+program|field\s+program|sampling\s+program|survey)|receives\s+"
                           r"(?:\w+\s+){0,3}permit|permit\s+to\s+drill|financing\s+for|funded\s+for|ahead\s+of|approval\s+"
                           r"for|designs|proposed|upcoming|strategy|to\s+(?:drill|test)|returns?\s+to)\b")),
]
_RESULTS_HL = re.compile(r"(?i)(?:g/t|gms?/t\w*|grams?\s+per\s+t\w*|\d\s?%\s?(?:Cu|Ni|Li2?O?|Zn|Pb|U3O8|Sb|WO3)|\bppm\b|intersect\w*|intercept\w*|"
                         r"assays?|results?|grading|returns?\s+up\s+to|discover\w*)")
_NOT_PROGRAM = re.compile(r"(?i)\b(?:resource\s+estimate|feasibility|pre-feasibility|PEA|metallurg\w*|bulk\s+sampl\w+|"
                          r"test\s+mining|mine\s+(?:plan|development|construction)|underground\s+development|"
                          r"production|processing\s+plant|option\s+agreement|work\s+commitments?|expenditures?\s+of|"
                          r"exploration\s+expenditures?|must\s+(?:incur|spend)|geotechnical|hydrogeolog\w*|condemnation|site\s+prep\w*|"
                          r"resampl\w*|re-sampl\w*|re-?logg\w*|royalt\w*|NSR)\b")
# 2026-10-01 (full text): drilling for a mine's construction is not an exploration program, even when called a "drilling
# program" ("a ~21-day sterilization drilling program", "Pre-construction drilling underway", "Pilot Drilling for
# Underground Decline Development")
_MINE_DRILL = re.compile(r"(?i)\b(?:sterili[sz]ation|pre-?construction|pilot[\s-]+(?:hole\s+)?drill\w*|pilot\s+holes?)\b")
# (2026-10-01: or the sentence is about that drilling: "The ongoing drilling targeting the intersection ... continues")
_ONGOING_SUBJECT = re.compile(r"(?i)^\W*(?:the|our|its)\s+(?:ongoing|current|continuing)\s+(?:[\w-]+\s+){0,2}?drill(?:ing)?\b")
_RESULTS_OF_CURRENT = re.compile(r"(?i)\b(?:results?|assays?)\s+(?:\w+\s+){0,2}?(?:from|of|for)\s+(?:the|its|our)\s+(?:ongoing|"
                                 r"continuing|current)\s+(?:[\w-]+\s+){0,4}?drill\w*")
_HIST = re.compile(r"(?i)(?!historic\w*\s+(?:\w+\s+){0,2}?drill\w*\s+(?:samples?|core|data|logs?|results?|intercepts?|assays?)\b)\b(?:historically\s+(?:been\s+)?(?:drill\w*|complet\w*|conduct\w*|carried|explor\w*|sampl\w*)|historic(?:al)?\s+(?:\w+\s+){0,2}?(?:drill\w*|diamond\s+drill\w*|trench\w*|soil\s+\w+|"
                   r"surveys?|sampling|geophysic\w*|mapping|exploration\s+(?:work|programs?))|(?:by|from)\s+(?:the\s+|a\s+)?"
                   r"previous\s+(?:operators?|owners?|explorers?)|previous\s+(?:operators?|owners?|explorers?)\s+(?:\w+\s+)"
                   r"{0,3}?(?:drill\w*|complet\w*|conduct\w*|carried)|predecessors?|prior\s+(?:operators?|owners?))\b")
_METALS = ("gold", "silver", "copper", "nickel", "zinc", "lead", "cobalt", "lithium", "uranium", "antimony", "tungsten",
           "molybdenum", "rare earths", "graphite", "tin", "platinum", "palladium", "hydrogen", "vanadium", "manganese")


# ------------------------------------------------------------------ small parsers
def _num(s):
    s = s.strip().lower()
    if s in _NUMW:
        return float(_NUMW[s])
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


_METRES = re.compile(r"(?i)(?<![\w.])" + _NUM + r"(?:\+)?\s*(?:-\s*)?(?:line[\s-]*)?(?:metres?|meters?|m)\b(?!\s*(?:wide|"
                     r"long|deep|thick|below|above|depth|interval|of\s+\d|at\s+\d|grading|@|\(|apart|spacings?|east|west|"
                     r"north|south|from|to\s+the|drilled\s+depth|down[\s-]*hole|vertical)|\s*\w*\s*(?:g/t|%))")
_HOLES = re.compile(r"(?i)(?<![\w.#\-/])" + _NUM + r"\s+(?:\d+(?:,\d{3})*\s*(?:-\s*)?(?:m|metres?|meters?)\s+(?:long\s+|deep\s+)?)?(?:(?!(?:metres?|meters?|m|km|deep|long)\b)[a-z][\w-]*[\s-]+){0,3}?(?:drill\s*)?holes?\b|(?<![\w.])" + _NUM +
                    r"-hole\b|(?<![\w.])" + _NUM + r"\s+drillholes?\b")
_LINEKM = re.compile(r"(?i)(?<![\w.])" + _NUM + r"\s*(?:-\s*)?line[\s-]*(?:kilomet(?:re|er)s?|km)\b|(?<![\w.])" + _NUM +
                     r"\s*(?:kilomet(?:re|er)s?|km)\s+of\s+(?:IP\s+)?lines?\b")
_BUDGET = re.compile(r"(?i)(?:(C|CA|CDN|US|A|AU)\$|\$)\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)\s*(million|M|k|thousand)?\b(?=[^.]{0,60}?"
                     r"\b(?:program|budget|exploration|drill))")
_YEAR = re.compile(r"\b((?:19[5-9]|20[0-3])\d)\b")
_PHASE = re.compile(r"(?i)\bphase\s+(\d|I{1,3}V?|one|two|three|four)\b")
_SEASON = re.compile(r"(?i)\b(?:(winter|spring|summer|fall|autumn)\s+(?:of\s+)?((?:19|20)\d\d)|((?:19|20)\d\d)\s+(winter|"
                     r"spring|summer|fall|autumn)|(Q[1-4])\s+(?:of\s+)?((?:19|20)\d\d))\b")


_PROG_M = [
    re.compile(r"(?i)(?<![\w.])" + _NUM + r"\+?\s*(?:-\s*)?(?:metres?|meters?|m)\b,?[\s-]+(?:(?:of\s+)?(?:diamond\s+|core\s+|RC\s+|"
               r"reverse\s+circulation\s+|exploration\s+|infill\s+|surface\s+|underground\s+)?(?:drill(?:ing)?(?!ed\s+depth)|drillholes?|"
               r"holes?)|(?:\w+\s+){0,2}(?:drill\s+)?(?:program(?:me)?|campaign))"),
    re.compile(r"(?i)" + _NUM + r"\+?\s*(?:metres?|meters?|m)\s+(?:planned|drilled(?!\s+depth)|completed|of\s+(?:\w+\s+)?drilling)\b"),
    re.compile(r"(?i)(?:program(?:me)?\s+of|campaign\s+of|drilling\s+of|drilled|completed|totall?ing|comprised|comprising|consisting\s+of|"
               r"total\s+of|minimum\s+of)\s+(?:up\s+to\s+|approximately\s+|a\s+total\s+of\s+|"
               r"a\s+minimum\s+of\s+|over\s+|about\s+|~)?" + _NUM + r"\+?\s*(?:metres?|meters?|m)\b(?!\s*(?:wide|long|"
               r"deep|below|depth|of\s+\d|grading|@|at\s+\d))"),
]

# 1.2.1: shapes read only where the clause states no size in the shapes above, so no figure the reader already
# publishes moves: the size as a table cell or after the holes -- "2025 Diamond Drill Program Minimum 4,000m" (HML),
# "Total planned drilling: approximately 1,800 meters" (GRBM), "12 holes totaling a length of ~3,000 metres" (EPG),
# "10 drill holes and approximately 6,000m" (LMS) -- and a bracket after the unit, "14,230 feet (about 4,300 metres)
# of drilling" (KING), "15,240 metre (50,000 ft) drill program"
_PROG_M_MORE = [
    re.compile(r"(?i)(?:\b(?:program(?:me)?|campaign)\s+(?:of\s+)?(?:a\s+)?minimum(?:\s+of)?|"
               r"\b(?:total\s+)?planned\s+drilling\s*:|\btotall?ing\s+a\s+(?:total\s+)?length\s+of|"
               r"\bholes\s+(?:and|for)\s+(?=approximately|about|~))\s*(?:approximately\s+|about\s+|~\s*)?"
               + _NUM + r"\+?\s*(?:metres?|meters?|m)\b(?!\s*(?:wide|long|deep|below|depth|grading|@))"),
    re.compile(r"(?i)(?<![\w.])" + _NUM + r"\+?\s*(?:-\s*)?(?:metres?|meters?|m)\b(?:\s*\((?:[\"“”']?m[\"“”']?|[^()]{0,12}"
               r"\b(?:ft|feet))\)|\))[\s-]+(?:of\s+)?(?:(?:diamond|core|RC|surface|underground)\s+)?(?:drill(?:ing)?\b|"
               r"(?:\w+\s+){0,2}(?:drill\s+)?program(?:me)?|campaign)"),
]


def _metres(s, status=None):
    order = _PROG_M if status not in ("started", "planned") else [_PROG_M[2], _PROG_M[0], _PROG_M[1]]
    return _first_size(s, order)


_EXPANDED = re.compile(r"(?i)\b(?:increas|expand|extend|upsiz|enlarg)\w*\s+(?:(?:the|its|our|this)\s+)?(?:\w+\s+){0,3}?to\s+"
                       r"(?:approximately\s+|about\s+|~\s*)?" + _NUM + r"\s*(?:-\s*)?(?:m\b|metres?|meters?|(?:drill\s*)?holes?\b)")


def _EXPANDED_HOLES(s):
    m = _EXPANDED.search(s)
    if m and re.search(r"(?i)holes?$", m.group(0)):
        v = _num(next(x for x in m.groups() if x))
        return int(v) if v and v == int(v) else None
    return None


def _metres_more(s):
    """1.2.1: the program's size in the shapes _metres() does not read (see _PROG_M_MORE)."""
    return _first_size(s, _PROG_M_MORE)


def _first_size(s, order):
    for rx in order:
        for m in rx.finditer(s):
            g = next(x for x in m.groups() if x)
            v = _num(g)
            if v is None or v < 50 or v > 400000:
                continue
            tail = s[m.end():m.end() + 30].lower()
            if re.search(r"^\s*(?:\w+\s+){0,2}(?:g/t|%|ppm|grading)", tail):
                continue
            if not _size_context_ok(s, m.start(), m.end()):
                continue
            return v
    return None


# 1.2.3: a figure that is not the program's size, from the words before it: an intercept's width ("Intersects Gold
# Mineralization Over 72 m and Starts Drill Program"), a working's length ("two exploration adits totaling 152 m and
# 22 short diamond drillholes"), or the part of a program a results release reports ("results of the remaining 6 HQ
# diamond drill holes totaling 1,143 m")
_INTERCEPT_HEAD = re.compile(r"(?i)(?:g/t|gpt|%|ppm|ppb|intersect\w*|intercept\w*|mineraliz\w*|mineralis\w*|grading|"
                             r"averaging|assay\w*)[^.;]{0,25}\b(?:over|across|of)\s+(?:approximately\s+|about\s+)?$")
_WORKING_HEAD = re.compile(r"(?i)\b(?:adits?|tunnels?|drifts?|ramps?|declines?|shafts?|cross-?cuts?|raises?|trench\w*|"
                           r"channels?|workings|lines?|grids?)\b(?![^.;]*\bdrill)[^.;]{0,40}$")
_DRILL_TAIL = re.compile(r"(?i)^[\s,]*(?:\+\s*)?(?:\([^)]{0,20}\)\s*)?(?:of\s+)?(?:[\w-]+\s+){0,3}?(?:drill|core|RC\b|holes?)")
_SUBSET_HEAD = re.compile(r"(?i)\b(?:results?|assays?)\s+(?:\w+\s+){0,2}(?:from|of|for|on)\s+(?:the\s+)?(?:remaining|final|"
                          r"last|latest|first)\b[^.;]{0,60}$")


# 2026-10-01 (full text): the program's own size named after the batch a results release reports ("results from the
# final nine holes completed during the 10,217-metre winter drill campaign", "the first two drill holes of a seven hole
# 2,600 metre exploration program"): the figure that opens "the/a ... program" is the program's, not the batch's
_OWN_PROG_HEAD = re.compile(r"(?i)\b(?:of|during|from|in|within|as\s+part\s+of)\s+(?:the|a|an|its|our|this)\s+"
                            r"(?:(?:recently|now|successfully|just)\s+)?(?:(?:completed|finished|current|ongoing|planned|"
                            r"maiden|initial|inaugural|first|second|phase\s+\w+|[\w-]+-hole|\w+\s+holes?|(?:19|20)\d\d)[\s,]+){0,2}$")
_OWN_PROG_TAIL = re.compile(r"(?i)^[^.;]{0,50}?\b(?:program(?:me)?|campaign)\b")


def _own_program_size(s, i, j):
    return bool(_OWN_PROG_HEAD.search(s[max(0, i - 60):i]) and _OWN_PROG_TAIL.match(s[i:i + 70]))


def _size_context_ok(s, i, j):
    head = s[max(0, i - 90):i]
    if _INTERCEPT_HEAD.search(head[-60:]) or (_SUBSET_HEAD.search(head) and not _own_program_size(s, i, j)):
        return False
    # "trenching and 4,700 m of diamond drilling" is the drilling's size
    after = re.sub(r"(?i)^[^\s]*?[\d,.]+\s*\+?\s*(?:-\s*)?(?:metres?|meters?|m)\b", "", s[i:i + 80])
    return not (_WORKING_HEAD.search(head[-50:]) and not _DRILL_TAIL.match(after))


def _metres_loose(s):
    for m in _METRES.finditer(s):
        tail = s[m.end():m.end() + 45].lower()
        head = s[max(0, m.start() - 30):m.start()].lower()
        if re.search(r"line", m.group(0), re.I):
            continue
        v = _num(m.group(1))
        if v is None or v < 20 or v > 400000:
            continue
        if re.search(r"(?:over|@|of)\s*$", head) and re.search(r"(?:g/t|%|ppm)", s[m.end():m.end() + 25]):
            continue
        if re.search(r"^\s*(?:\w+\s+){0,2}(?:g/t|%|ppm|grading)", tail):
            continue
        if re.search(r"(?:depth\s+of|deep|elevation|down\s+to|to\s+a\s+depth|vertical|masl|spacings?|intervals?|"
                     r"approximately\s+\d+\s*m\s+(?:east|west|north|south))\s*$", head):
            continue
        return v
    return None


def _holes(s, historical=True):
    for m in _HOLES.finditer(s):
        g = next(x for x in m.groups() if x)
        v = _num(g)
        if v is None or v < 1 or v > 1500 or v != int(v):
            continue
        tail = s[m.end():m.end() + 25].lower()
        if re.search(r"^\s*(?:returned|intersected|of\s+the|grading|with)", tail) and v <= 3:
            continue
        # 1.2.3: holes counted by what they found are a results batch, not the program ("All three drillholes
        # successfully intercepted high-grade mineralization")
        if re.search(r"^\s*(?:for\s+which|with)\s+(?:\w+\s+)?(?:assays?|results?)\b", tail):
            continue
        if re.search(r"^\s*(?:(?:have|has|were|all)\s+)?(?:\w+ly\s+)?(?:intersected|intercepted|encountered|returned|hit|"
                     r"cut|confirmed|delineated)\b", tail):
            # (key gate: "all four drill holes intersected high-grade gold", said of a finished phase, counts every
            # hole of it; only when the text does not name those holes as a batch -- "the first three drillholes")
            if not (re.search(r"(?i)\ball\s+(?:of\s+the\s+)?$", s[max(0, m.start() - 12):m.start()]) and v >= 4
                    and not re.search(r"(?i)\b(?:first|initial|remaining|last|latest|final|next|additional|results\s+"
                                      r"(?:from|of|for))\s+(?:the\s+)?" + re.escape(g) + r"\b", s)):
                continue
        seg = m.group(0).lower()
        if re.search(r"(?i)\b(?:these|those|both|standout|discovery|best|deepest|third|fourth|fifth|last|first|remaining|latest)\s+(?:\w+\s+)?$",
                     s[max(0, m.start() - 22):m.start()]):
            continue
        if _SUBSET_HEAD.search(s[max(0, m.start() - 90):m.start()]) and not _own_program_size(s, m.start(), m.end()):
            continue                                # 1.2.3: the holes a results release reports
        # 1.2.3: "Four holes totaling 1,422 metres of the planned 18 hole, 6,000 metre program": the program's holes
        pm = re.match(r"(?i)[^.;]{0,60}?\bof\s+(?:the|a|its|our)\s+(?:planned|proposed|budgeted)\s+" + _NUM +
                      r"(?:\s*-\s*|\s+)(?:drill\s*)?holes?\b", s[m.end():m.end() + 90])
        if pm:
            pv = _num(next(x for x in pm.groups() if x))
            if pv and pv == int(pv) and pv > v:
                return int(pv)
        if re.search(r"\b(?:historic|previous|last|first|final|remaining|pending|deepening|reported|assayed)\b", seg):
            if ("historic" in seg or "previous" in seg) and historical:
                pass
            else:
                continue                            # (1.2.3: earlier holes are not a current program's)
        return int(v)
    return None


def _linekm(s):
    m = _LINEKM.search(s)
    if not m:
        return None
    g = next(x for x in m.groups() if x)
    return _num(g)


# 1.2.1: the budget written before its figure -- "a record high exploration budget of $10 million" (OGC.TO), "This first
# phase exploration program is budgeted at $375,000" (AURR.CN), "established a budget of $3.0 million" (PRIZ.CN)
_BUDGET_BEFORE = re.compile(r"(?i)\bbudget(?:ed)?\s+(?:of|at|is|totall?ing|for\s+(?:the\s+)?(?:[\w-]+\s+){0,3}(?:is|of))\s+"
                            r"(?:approximately\s+|about\s+|~\s*)?(?:(C|CA|CDN|US|A|AU)\$|\$)\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)\s*"
                            r"(million|M|mm|k|thousand)?\b(?![.,]?\d|\s*-\s*\d)")
# money that is the company's, not the program's
_NOT_BUDGET = re.compile(r"(?i)\b(?:treasury|cash|raised?|financing|placement|flow[\s-]*through|offering|grants?|payments?|"
                         r"expenditures?\s+of|option|warrants?|per\s+share|market\s+cap\w*|royalt\w+|acquisition|consideration|"
                         r"over\s+the\s+(?:next|coming)\s+(?:\w+\s+)?years)\b")


def _budget(s):
    m = _BUDGET.search(s)
    if not m:
        m = _BUDGET_BEFORE.search(s)
    if not m:
        return None, None
    v = _num(m.group(2))
    if v is None:
        return None, None
    mul = (m.group(3) or "").lower()
    v *= 1e6 if mul in ("million", "m", "mm") else 1e3 if mul in ("k", "thousand") else 1
    if v < 20000:
        return None, None
    cur = {"US": "USD", "A": "AUD", "AU": "AUD"}.get((m.group(1) or "").upper(), "CAD")
    return v, cur


def _phase(s):
    m = _PHASE.search(s)
    if not m:
        return None
    v = m.group(1).lower()
    v = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "one": "1", "two": "2", "three": "3", "four": "4"}.get(v, v)
    return "Phase " + v


def _season(s, date_year=None):
    m = _SEASON.search(s)
    if m:
        g = m.groups()
        if g[0]:
            return "%s %s" % (g[0].lower(), g[1])
        if g[2]:
            return "%s %s" % (g[2], g[3].lower())
        return "%s %s" % (g[4].upper(), g[5])
    ys = [y for y in _YEAR.findall(s)]
    if len(set(ys)) == 1:
        return ys[0]
    return None


def _method(s):
    t = s.lower()
    for k, v in (("reverse circulation", "RC"), (" rc ", "RC"), ("rc drill", "RC"), ("diamond", "diamond"),
                 ("core drill", "diamond"), ("core hole", "diamond"), ("sonic", "sonic"), ("aircore", "aircore"),
                 ("air core", "aircore"), ("rab ", "RAB"), ("auger", "auger")):
        if k in " " + t + " ":
            return v
    return None


def _survey(s, ptype):
    t = s.lower()
    if ptype == "geophysics":
        for k, v in (("induced polari", "IP"), ("ip survey", "IP"), ("ip program", "IP"), ("ip line", "IP"),
                     ("vtem", "VTEM"), ("ztem", "EM"), ("tdem", "EM"), ("mlem", "EM"), ("electromagnetic", "EM"),
                     ("em survey", "EM"), ("magnetotelluric", "other"), ("mobilemt", "other"), ("mobile mt", "other"),
                     ("gravity", "gravity"), ("radiometric", "radiometric"), ("lidar", "LiDAR"), ("magnetic", "magnetic"),
                     ("mag survey", "magnetic")):
            if k in t:
                return v
        return None
    if ptype == "ground":
        kinds = [v for k, v in (("soil", "soil"), ("till", "till"), ("hmc", "till"), ("trench", "trenching"),
                                ("channel", "channel"), ("rock", "rock"), ("grab", "rock"), ("mapping", "mapping"),
                                ("prospecting", "prospecting")) if k in t]
        kinds = list(dict.fromkeys(kinds))
        if len(kinds) == 1:
            return kinds[0]
        return "mixed" if kinds else None
    return None


def _metal(text):
    t = text.lower()
    found = []
    for m in _METALS:
        if re.search(r"\b" + m + r"\b", t):
            found.append(m)
    if re.search(r"\bu3o8\b", t) and "uranium" not in found:
        found.append("uranium")
    if re.search(r"\b(?:ree|rare\s+earth)", t) and "rare earths" not in found:
        found.append("rare earths")
    return found


def _contractor(s):
    m = re.search(r"(?:contracted|awarded\s+(?:the\s+)?(?:drill(?:ing)?\s+)?contract\s+to|retained|engaged|selected|"
                  r"by|with|contractor,?)\s+((?:[A-Z][\w&'’\-]*\s+){0,4}(?:Drilling|Geophysics|Geophysical|Geotech|"
                  r"Forages?|Diamond\s+Drilling|Exploration\s+Services)(?:\s+(?:Ltd|Inc|Corp|Limited|Group|LLC|S\.A\.))?"
                  r"\.?)", s)
    if m:
        return m.group(1).strip(" .")
    return None


def _rigs(s):
    m = re.search(r"(?i)(?<![\w.])" + _NUM + r"\s+(?:\w+\s+){0,2}?(?:drill\s+)?rigs?\b|(?<![\w.])" + _NUM +
                  r"\s+(?:diamond\s+|core\s+|RC\s+)?drills\b", s)
    if not m:
        return None
    v = _num(next(x for x in m.groups() if x))
    return int(v) if v and v < 30 else None


# ------------------------------------------------------------------ project names
# (2026-10-01, full text: "Prospect" followed by a name word starts the name -- "Prospect Valley Gold Property" -- and a
# lower-case "permit" follows a name too -- "the Kimoukro permit")
_PROJ_WORD = (r"(?:(?i:project|property|properties|licen[cs]es?|tenements?)|Prospect(?!\s+[A-Z])|Claims?|Claim\s+Block|"
              r"Deposit|EP|Permit|permit|Concessions?|Mine|Patents?|Salar)")   # (2026-10-01: a brine "Salar")
# (2026-10-01, full text: an ampersand inside a name, "the J&L Gold-Polymetallic Project")
_CAPNAME = r"([A-Z\u00c0-\u00dd](?:&[A-Z])?[\w'\u2019\u00c0-\u00ff\-]*(?:[\s\-](?:[A-Z\u00c0-\u00dd][\w'\u2019\u00c0-\u00ff\-]*|de|del|la|di|du|des|y|and|&)){0,4})"
# 1.2.3: the commodity words between a name and its "Project", however they are listed -- "Nicobi Nickel, Copper &
# Cobalt Project", "Greenwood District Precious and Battery Metals Project", "Mel Zinc-Lead-Barite Property" -- so
# the last commodity word is not taken for the name ("Cobalt", "Lead-Barite", "Precious and Battery")
_METALW = (r"(?:Gold|Silver|Copper|Uranium|Lithium|Nickel|Cobalt|Zinc|Lead|Antimony|Tungsten|Tin|Molybdenum|Moly|"
           r"Graphite|Vanadium|Manganese|Platinum|Palladium|PGEs?|PGMs?|Iron|Barite|Fluorite|Fluorspar|Phosphate|Potash|"
           r"Boron|Cesium|Tantalum|Niobium|Helium|Hydrogen|Magnesium|Scandium|Titanium|Rare[\s-]+Earths?(?:\s+Elements?)?|"
           r"REEs?|Critical\s+(?:Minerals?|Metals?)|Battery\s+Metals?|Base\s+Metals?|Precious\s+Metals?|Energy\s+Metals?|"
           r"Precious|Battery|Polymetallic|Porphyry|VMS|Brine|Iron\s+Ore|Hematite|Magnetite|Au|Ag|Cu|Ni|Zn|Pb|Co|Mo|Li|Sb|Sn|W|U)")
# 2026-10-01 (full text): the commodity words in lower case too ("the Deer Horn polymetallic property", "the Rajapalot
# gold-cobalt project", "its Golden Promise gold property")
_METALW_LC = (r"(?:gold|silver|copper|uranium|lithium|nickel|cobalt|zinc|lead|antimony|tungsten|molybdenum|graphite|"
              r"vanadium|manganese|platinum|palladium|polymetallic|porphyry|base\s+metals?|precious\s+metals?|"
              r"battery\s+metals?|critical\s+minerals?|rare[\s-]+earths?(?:\s+elements?)?)")
_METAL_ANY = r"(?:" + _METALW + r"|" + _METALW_LC + r")"
_METAL_RUN = _METAL_ANY + r"(?:(?:\s*(?:,|&|/|-)\s*|\s+and\s+|\s+)" + _METAL_ANY + r")*"
# (2026-10-01, full text: a quoted nickname between the name and its "Project" -- 'Pardo "River of Gold" Project')
_PROJ_RX = re.compile(_CAPNAME + r"(?:\s+[\"\u201c][^\"\u201c\u201d]{2,30}[\"\u201d])?\s+(?:" + _METAL_RUN + r"\s+)?" + _PROJ_WORD + r"\b")
# 1.2.4 (2026-10-02, speed): a token of 40 or more non-space characters (a URL, a file name, a run of hyphenated words
# in a link list) is never a property name, but the name pattern backtracks on long hyphenated ones (a 30,000-character
# list of links took 14 s). Such tokens are masked, keeping every offset, before any name pattern runs over the text.
_LONG_TOKEN = re.compile(r"\S{40,}")


def _mask_long(text):
    """Every token of 40+ non-space characters replaced by as many '#' (not a word, space or quote character), so a
    name pattern neither starts, runs through nor ends inside one; positions are unchanged."""
    if not text or len(text) < 40 or not _LONG_TOKEN.search(text):
        return text
    return _LONG_TOKEN.sub(lambda m: "#" * len(m.group(0)), text)


def _proj_iter(text):
    """_PROJ_RX over the text with long tokens masked (groups read from the masked copy; offsets are the text's)."""
    return _PROJ_RX.finditer(_mask_long(text))
_METAL_TOKEN = re.compile(r"^" + _METALW + r"(?:[-/]" + _METALW + r")*$")
_LANDHOLDING = re.compile(r"(?i)^\s*(?:project|property|properties|claims?|claim\s+block|EP|permit|concessions?|licen[cs]es?|tenements?|patents?)\b")
_BAD_PROJ = {"The", "Our", "This", "Its", "Company", "Company's", "Company’s", "Each", "All", "New", "First", "Maiden",
             "Flagship", "Wholly", "Owned", "Option", "Optioned", "Drill", "Exploration", "Phase", "Winter", "Summer",
             "Spring", "Fall", "Autumn", "Gold", "Silver", "Copper", "Uranium", "Lithium", "Nickel", "Critical", "Mineral",
             "Minerals", "Canadian", "Nevada", "Ontario", "Quebec", "Québec", "Yukon", "British", "Columbia", "Saskatchewan",
             "Manitoba", "Newfoundland", "Labrador", "Nunavut", "Brazil", "Mexico", "Peru", "Argentina", "Chile", "Idaho",
             "Wisconsin", "Advanced", "Stage", "Historic", "Historical", "Additional", "Two", "Three", "Both", "These",
             "Other", "Mining", "Mines", "Owned", "Road", "Accessible", "Adjacent", "Neighbouring", "Past", "Producing",
             "Former", "RC", "Successfully", "Program", "Past-Producing", "Wholly-Owned", "Wholly-owned", "100%-Owned", "Large", "District", "Scale", "High", "Grade", "Underexplored", "Under", "Explored", "Key",
             "Several", "Multiple", "Such", "Operating", "Current", "Early", "Northern", "Southern", "Western", "Eastern",
             "Central", "Rich", "Ni", "Co", "Energy", "Metals", "Resources", "Corp", "Inc", "Ltd", "Group", "Tsx", "TSX",
             "CSE", "Newfoundland’s", "Sb", "Ag", "Au", "Cu", "Zn", "Pb", "REE", "VMS", "In", "At", "On", "For", "To",
             "And", "With", "From",
             # 2026-10-01: "On It's Dome Mountain Gold Project" (a misspelt "its"); a holding is not a name ("its
             # District Scale Land Package")
             "It", "Land", "Package", "Packages", "Portfolio", "Holdings", "Metal",
             # (and a market is not a property: "Applies to List on the OTCQX Market")
             "Otcqx", "OTCQX", "Otcqb", "OTCQB", "OTC", "Market", "Markets", "Exchange", "Nasdaq", "NASDAQ", "NYSE",
             # 1.2.3: a people's or a country's adjective alone is a region, not a property ("Mongolian portfolio")
             "Mongolian", "Peruvian", "Brazilian", "Chilean", "Colombian", "Mexican", "Ecuadorian", "Argentinian",
             "Argentine", "Australian", "American", "African", "Alaskan", "Finnish", "Swedish", "Norwegian", "Irish",
             "Scottish", "Spanish", "Portuguese", "Chinese", "Guyanese", "Ghanaian", "Malian", "Tanzanian", "Zambian",
             "Namibian", "Bolivian", "Guatemalan", "Honduran", "Nicaraguan", "Panamanian", "Serbian", "Bosnian",
             "Turkish", "Moroccan", "Egyptian", "Greenlandic", "Nevadan", "Cobalt", "Ore", "Hematite", "Magnetite", "Zinc", "Lead", "Tin", "Graphite",
             "Vanadium", "Antimony", "Tungsten", "Precious", "Battery", "Base", "Polymetallic",
             # kinds of licence, not names ("Uranium Exclusive Prospecting Licence")
             "Exclusive", "Prospecting", "Exploitation", "Tenure", "Development", "Expansion", "Infill", "Definition"}
# 1.2.3: a leading commodity word that is the first word of the property's name ("Silver Queen", "Gold Standard",
# "Nickel Mountain"), kept when a name word follows it
_NAME_METALS = {"Gold", "Silver", "Copper", "Nickel", "Lithium", "Uranium", "Cobalt", "Zinc", "Lead", "Tin", "Graphite",
                "Iron", "Diamond", "Golden",
                # (and an adjective that starts a name: "Mexican Hat", "American Girl")
                "Mexican", "American", "African", "Australian", "Canadian", "Spanish", "Irish", "Scottish", "Chinese"}
# 1.2.3: possessive owners that are places or common words, not another company ("Today's Kibi", "Quebec's ...")
_GEO_NOUN = {"Brook", "Creek", "Lake", "Lakes", "Point", "Hill", "Hills", "Bay", "River", "Cove", "Pond", "Island", "Harbour",
             "Harbor", "Mountain", "Mountains", "Ridge", "Peak", "Valley", "Gulch", "Canyon", "Arm", "Landing", "Falls",
             "Head", "Knob", "Flat", "Flats", "Meadow", "Meadows", "Crossing", "Pass", "Bluff", "Spring", "Springs",
             "Well", "Wells", "Gully", "Rock", "Rocks", "Butte", "Mesa", "Dome", "Basin", "Gap", "Notch", "Pit", "Reef"}
_OWNER_COMMON = {"Today", "Company", "Corporation", "Canada", "America", "Africa", "World", "Province", "State", "Nation",
                 "Region", "District", "Camp", "Belt", "Trend", "Year", "BC", "B.C.", "Issuer", "Partnership", "Country"}


_HL_VERB = {"Receives", "Expands", "Announces", "Announce", "Commences", "Completes", "Launches", "Begins", "Starts",
            "Reports", "Provides", "Update", "Updates", "Results", "Field", "Work", "Program", "Programs", "Drilling", "Drill",
            "Following", "Plans", "Prepares", "Preparations", "Mobilizes", "Initiates", "Identifies", "Confirms",
            "Discovers", "Intersects", "Returns", "Closes", "Financing", "Continues", "Resumes", "Resumption", "Options",
            "Acquires", "Test", "Tests", "Testing", "Target", "Targets", "At", "The", "Of", "Its", "Their", "Sampling",
            "Survey", "Geophysics", "Trenching", "Soil", "Channel", "Underground", "Surface", "Airborne", "Maiden",
            "Inaugural", "Delineate", "Potential", "Highgrade", "High-Grade", "Mineralization", "Crews", "Drill-Ready",
            "Receipt", "Permit", "Permits", "Approval", "Approvals", "Ahead", "Area", "Areas", "Strategy", "Achievements",
            "Reviews", "Ready", "First", "Ever", "Exploration", "From", "Recent", "Ongoing", "Additional", "Summer",
            "Winter", "Spring", "Fall", "Q1", "Q2", "Q3", "Q4", "Deep-Test", "Return", "Returns", "Metres", "Meters",
            "Geophysical", "Strategically", "Locate", "Located", "Positive", "Past-Producing", "Producing",
            "Completion", "Commencement", "Completed", "Commenced", "Advances", "Advancing", "Outlines", "Defines",
            "Expanded", "Extends", "Significant", "Encouraging", "Robust", "Strong", "Successful", "Kicks", "Off",
            "Wraps", "Up", "Engages", "Over", "Confirm", "Confirms", "Spodumene", "Newly", "Acquired", "About", "Multi-Year", "Controlled", "Owned", "Hosted", "Signs", "Welcomes", "Adds", "Enters", "Mobilization", "Mobilisation", "Its",
            "On", "Across", "New", "Assays", "Assay", "Rig", "Rigs", "Diamond", "Core",
            # 1.2.3: more headline verbs and connectives in title case ("Xtra-Gold Further Delineates Kibi", "Agreement
            # To Sell Great Northern Project", "to Include Adjacent Claims", "Exploration Well Permit", "Near-Term Mine")
            "Further", "Delineates", "Demonstrates", "Drills", "Hits", "Cuts", "Highlights", "Unveils", "Stakes",
            "Secures", "Grants", "Samples", "Doubles", "Increases", "Upgrades", "Encounters", "Finalizes", "Retains",
            "Files", "To", "For", "With", "In", "Into", "Near", "Sell", "Sells", "Sale", "Agreement", "Agreements",
            "Acquire", "Acquisition", "Purchase", "Include", "Includes", "Including", "Well", "Wells", "Near-Term",
            "Long-Term", "Short-Term", "Term", "Plan", "Update:", "Arrival", "Mobilized", "Mobilised", "Expanding",
            "Resource", "Resources", "Estimate", "Joins", "Appoints", "Congratulates", "Welcomes", "Zone", "Zones",
            "Beyond", "Below", "Above", "Along", "Growth", "Continued", "Workings", "Submits", "Applies", "Obtains",
            "Reaches", "Achieves", "Hires", "Names", "Delivers", "Issues", "Reaffirms", "Renegotiates", "Executes",
            "Amends", "Extends", "Enlarges", "Consolidates", "Strengthens", "Summarizes", "Outlines", "Stakes",
            # 2026-10-01 (full text): "Newly Identified Caribe Gold Prospect", "Recieves McKenzie East Gold Project"
            "Identified", "Discovered", "Defined", "Received", "Recieves", "Recieved"}
# 1.2.3: words that end a drilling phrase in a headline ("Diamond Drill Program") but can start a property's name
# ("Diamond Mountain", "Core Lake"): a cut only before a drilling word
_HL_VERB_IF_DRILL = {"Diamond", "Core", "Rig", "Rigs"}
_DRILLWORD_TOK = {"Drill", "Drilling", "Drillhole", "Drillholes", "Hole", "Holes", "Program", "Programme", "Rig", "Rigs",
                  "Campaign", "Results", "Assays"}


_DIRECTION_WORDS = {"East", "West", "North", "South", "Northeast", "Northwest", "Southeast", "Southwest", "NE", "NW", "SE",
                    "SW", "Extension", "Northern", "Southern", "Eastern", "Western", "Central", "Upper", "Lower"}
_CORP_SUFFIX = {"Corporation", "Corp", "Inc", "Ltd", "Limited", "LLC", "plc", "PLC", "Pty", "Incorporated"}
_PLACE_PREFIX = {"St.", "St", "Saint", "Mt.", "Mt", "Mount", "Port", "Fort", "Lake", "Cape", "Ste.", "Sainte"}


def _name_word(w):
    """2026-10-01: a word that can be part of a property's name (capitalised, not a headline or generic word)."""
    return bool(re.match(r"^[A-Z\u00c0-\u00dd]", w)) and w not in _HL_VERB and w not in _BAD_PROJ and w not in _HL_VERB_IF_DRILL \
        and not w.endswith(("'s", "\u2019s"))


def _clean_proj(name, iw=None):
    """A name as the page shows it. 1.2.3: with the issuer's words (iw), a name another company owns ("Wallbridge's
    Fenelon", "Aris Mining's Juby") is None; the issuer's own possessive and a common word's come off ("Nuvau's
    Matagami", "Today's Kibi"). A leading commodity word stays when it starts the name ("Silver Queen"), and trailing
    commodity symbols come off ("Silver Queen Ag-Au" -> "Silver Queen")."""
    # 1.2: a headline repeated in capitals in the body ("PROGRAM AT THE GOCHAGER LAKE", "DEPTH AT ITS RC GOLD")
    # is read in title case, so the verbs and connectives in front of the name come off as they do in the headline
    letters = [c for c in name if c.isalpha()]
    if len(letters) > 3 and all(c.isupper() for c in letters):
        name = " ".join(w if w in _ACRO or (len(w) <= 2 and w.lower() not in ("at", "of", "in", "on", "to", "by", "an", "a", "de", "la", "y"))
                        else "-".join(p.capitalize() for p in w.split("-")) for w in name.split())
    toks = [w for w in name.strip().split()]
    # 2026-10-01 (full text): a preposition right before "Project" means no name is attached to it ("A MAJOR
    # INCREASE IN PROJECT ...")
    if toks and toks[-1] in ("In", "At", "On", "For", "To", "Of", "With", "From", "The", "Its", "Our", "A", "An"):
        return None
    cut = 0
    for i, w in enumerate(toks):
        if w in _HL_VERB_IF_DRILL:
            if i == len(toks) - 1 or toks[i + 1] in _DRILLWORD_TOK:
                cut = i + 1
        elif w in _HL_VERB or re.match(r"^(?:19|20)\d\d$", w):
            # 2026-10-01 (full text): the last word of a name that is also a place word or a licence kind -- "Root
            # Spring", "Mesa Well", "Tay Exploration (License)" -- is not a headline word when a name word comes
            # before it
            if i >= 1 and all(_METAL_TOKEN.match(x) for x in toks[i + 1:]) and (w in _GEO_NOUN or w in _BAD_PROJ or
                                                                                w in ("Zone", "Zones")) \
                    and _name_word(toks[i - 1]):
                continue
            cut = i + 1
        elif w.endswith(("’s", "'s", "s’", "s'")) and i < len(toks) - 1 and toks[0] not in _PLACE_PREFIX \
                and toks[i + 1] not in _GEO_NOUN:        # 1.2.3: "Clark's Brook" is a place
            owner = [re.sub(r"['’]s?$", "", x) for x in toks[cut:i + 1]]
            if iw is not None:
                distinct = [x for x in owner if x.lower() not in _GENERIC_CO]
                if distinct and not ({x.lower() for x in distinct} & iw) and \
                        not all(x in _OWNER_COMMON or x in _BAD_PROJ for x in distinct):
                    return None                     # 1.2.3: another company's property
                cut = i + 1
            elif i >= 1 or w[:-2] in ("Gold", "Metals", "Resources", "Mining", "Power", "Energy", "Minerals", "Copper",
                                      "Silver", "Uranium", "Lithium", "Exploration", "Ventures", "Company"):
                cut = i + 1
    toks = toks[cut:]
    # 1.2.3: a company, not a property ("Barrick Mining Corporation’s", "Silver Mines Limited")
    # (2026-10-01: "Yukon Metals' silver-lead-zinc-gold project" too; but a place named with a person's possessive --
    # "the Company's Lewis Pilley's Project" -- is a name: two or more words, none a company word or the issuer's)
    if toks and (toks[-1].endswith(("\u2019s", "'s", "s\u2019", "s'")) or any(re.sub(r"[\u2019'.,]s?$", "", x) in _CORP_SUFFIX for x in toks)):
        owner = {_fold_words(re.sub(r"['\u2019]s?$", "", x)) for x in toks}
        if not (len(toks) >= 2 and toks[-1].endswith(("\u2019s", "'s")) and not owner & _GENERIC_CO
                and not any(re.sub(r"[\u2019'.,]s?$", "", x) in _CORP_SUFFIX for x in toks)
                and (iw is None or not any(w in iw or "!" + w in iw for w in owner))):
            return None
    # 2026-10-01: a leading adjective made of a name and a lower-case word ("the Miocene-aged Esperanza porphyry
    # copper-gold project", "Carlin-type") is not part of the name
    while len(toks) >= 2 and re.match(r"^[A-Z][\w'\u2019]*-[a-z]+$", toks[0]):
        toks = toks[1:]
    if iw is not None and len(toks) >= 2 and "!" + _fold_words(toks[0]) in iw \
            and not all(x in _DIRECTION_WORDS for x in toks[1:]):
        # (2026-10-01: but a place both are named after, with a direction -- "Troilus East", "Rincon West" -- is not)
        return None                                 # 1.2.3: named after another company ("Kinross Bald Mountain")
    while toks and toks[0] in ("and", "&", "of", "de", "la", "del", "y"):
        toks = toks[1:]
    while toks and (toks[0].strip("’'s") in _BAD_PROJ or re.match(r"^\d", toks[0])):
        # 2026-10-01: a name of one word and a place word ("Battery Hill") keeps its first word
        if len(toks) == 2 and toks[1] in _GEO_NOUN and toks[0][:1].isupper() and not toks[0].endswith(("'s", "\u2019s")) \
                and toks[0] not in _HL_VERB and toks[0] not in ("The", "Our", "Its", "This", "New", "First", "All", "Each"):
            break
        # 1.2.3: "Silver Queen", "Gold Standard": the commodity word is the name's first word
        if toks[0] in _NAME_METALS and len(toks) >= 2 and toks[1][:1].isupper() and toks[1] not in _BAD_PROJ \
                and toks[1] not in _HL_VERB and not _METAL_TOKEN.match(toks[1]):
            break
        toks = toks[1:]
    while toks and (toks[-1] in _BAD_PROJ or toks[-1] in ("JV", "Joint", "Venture", "and", "&", "of", "de", "la", "del", "y")
                    or _METAL_TOKEN.match(toks[-1])):
        # 2026-10-01: a place word after a name word is part of the name ("Root Spring")
        if toks[-1] in _GEO_NOUN and len(toks) >= 2 and _name_word(toks[-2]):
            break
        # 1.2.3: "Great Northern": a direction after a name word is part of the name
        if toks[-1] in ("Northern", "Southern", "Eastern", "Western", "Central") and len(toks) >= 2 \
                and toks[-2] not in _BAD_PROJ and toks[-2] not in _NAME_METALS:
            break
        toks = toks[:-1]
    # 1.2.3: "Crown Granted" claims are a kind of claim, not a name
    if len(toks) >= 2 and toks[-2:] == ["Crown", "Granted"]:
        toks = toks[:-2]
    # 1.2: "Gold and Silver Properties" leaves only the connector once the metals are gone
    while toks and toks[0] in ("and", "&", "of", "de", "la", "del", "y"):
        toks = toks[1:]
    while toks and toks[-1] in ("and", "&", "of", "de", "la", "del", "y"):
        toks = toks[:-1]
    if not toks:
        return None
    if toks[-1] == "Use":
        return None                                 # 2026-10-01: a "Land Use Permit" is a permit, not a property
    if len(toks) == 1 and toks[0] in _DIRECTION_WORDS:
        return None                                 # 2026-10-01: a direction alone ("the East project") is not a name
    n = " ".join(toks).strip(" -,")
    n = re.sub(r"(?i)^(?:the|its|our)\s+", "", n)
    if len(n) < 2 or n.lower() in ("project", "property"):
        return None
    return n


def _projects(text, iw=None, kinds=False):
    """(position, name) of every "X Project/Property/Claims/Deposit/Mine..." in the text; 1.2.3: with kinds, a third
    item says whether the word after the name is a landholding (project, property, claims, concession, permit) rather
    than a feature inside one (deposit, mine, prospect)."""
    out = []
    for m in _proj_iter(text):
        # (2026-10-01: a lower-case "permit" follows a proper name, not an acronym of a permit kind -- "ITS permit")
        if text[m.end() - 6:m.end()] == "permit" and not re.search(r"[a-z]", m.group(1)):
            continue
        n = _clean_proj(m.group(1), iw)
        # 1.2.3: "Kincora's licences" are the company's, not a property named Kincora
        if n and iw and re.match(r"(?i)\s+(?:licen|tenement|patent|permit)", text[m.end(1):m.end()]) and \
                set(re.findall(r"[a-z0-9]{3,}", _fold_words(n))) <= iw:
            continue
        if n:
            if kinds:
                tail = text[m.end(1):m.end()]
                tail = re.sub(r"^\s+(?:" + _METAL_RUN + r"\s+)?", "", tail)
                out.append((m.start(), n, bool(_LANDHOLDING.match(tail))))
            else:
                out.append((m.start(), n))
    return out


_GENERIC_CO = {"inc", "corp", "ltd", "the", "resources", "mining", "metals", "gold", "minerals", "exploration", "limited",
               "silver", "copper", "corporation", "ventures", "company", "co", "plc", "llc", "group", "holdings", "and",
               "energy", "capital", "international", "global", "mines", "explorations", "lithium", "uranium", "nickel"}


def _issuer_words(title, b):
    """1.2.3: the issuer's distinctive name words: the dateline company, the first company named before a ticker in
    the lead, and the headline's first two words ("Midland Identifies ...", "Xtra-Gold Further ...")."""
    names = [_issuer(b) or ""]
    m = _ISSUER2.search(b[:700])
    if m:
        names.append(m.group(1))
    names.append(" ".join((title or "").split()[:2]))
    # 2026-10-01 (full text): the short name the release defines for the issuer ('("Playfair" or the "Company")'),
    # for a headline that does not start with it ("Drilling Update at Playfair's RKV Project")
    m = re.search(r"\(\s*(?:the\s+)?[\"\u201c]\s*([^\"\u201c\u201d]{2,40}?)\s*[\"\u201d]\s*(?:,|or\b|and/or\b)", b[:1500])
    if m:
        names.append(m.group(1))
    # ... and the issuer as the lead's subject, when the release defines no short name ("Playfair is now drilling")
    m = re.search(r"(?:^|[.:]\s+)([A-Z][\w&'\u2019\-]+(?:\s+[A-Z][\w&'\u2019\-]+){0,2})\s+(?:is|has|have|announces?|reports?|confirms?|"
                  r"provides?)\s+(?:now\s+|pleased\s+|today\s+)?(?:drilling|completed|commenced|begun|started|pleased|"
                  r"announc|report|provid)", b[:800])
    if m:
        names.append(m.group(1))
    out = set()
    for n in names:
        # (2026-10-01: a two-character name with a digit counts too: "E3's Clearwater Project")
        out |= {w for w in re.findall(r"[a-z0-9][a-z0-9\-]{2,}|\b[a-z][0-9]\b", _fold_words(n)) if w not in _GENERIC_CO}
    # other companies named with a corporate suffix ("Kinross Gold Corporation"): a property named after one ("Kinross
    # Bald Mountain") is theirs; marked "!word"
    own = None
    for m in _CO_NAME.finditer(b):
        w = _fold_words(m.group(1))
        # (not an operating company named after the property: "Oyu Tolgoi LLC" runs the Oyu Tolgoi project)
        co = re.sub(r"\s+(?:Corp(?:oration)?|Inc|Ltd|Limited|plc|PLC|LLC|Pty|S\.A|SA|AB|ASA)$", "", m.group(0))
        if w not in out and w not in _GENERIC_CO and m.group(1) not in _BAD_PROJ and m.group(1) not in _HL_VERB \
                and not re.search(re.escape(co) + r"\s+(?:" + _METAL_RUN + r"\s+)?" + _PROJ_WORD, b):
            # 2026-10-01 (full text): not a company named across a sentence end ("... the East Preston. Geotech Ltd"),
            # nor one whose first word is an adjective that starts names ("Golden Predator Mining Corp"), nor a
            # subsidiary or operating company named after a property of the release ("Golden
            # Promise Mines Inc." holds the Golden Promise Property, "Ruddock Creek Mining Corporation" the Ruddock
            # Creek Project, "Ivana Minerales S.A." the Ivana Project)
            if re.search(r"\.\s", m.group(0)) or m.group(1) in _NAME_METALS:
                continue
            if own is None:
                # (property names only: not a company's own name taken for one -- "Alto Ventures' property")
                own = {_name_words(n) for _p, n in _projects(b) + _projects(title or "")
                       if not set(re.findall(r"[a-z]+", _fold_words(n))) & _GENERIC_CO}
            if _name_words(co) in own:
                continue
            out.add("!" + w)
    return out


_CO_GENERIC = {"mine", "mines", "minerales", "mineracao", "minera\u00e7\u00e3o", "mineira", "mineria", "miner\u00eda", "development",
               "developments", "exploraciones", "exploracoes", "recursos", "uranium", "pty", "sa", "sac", "sas", "ltda",
               "deposit", "project", "property", "co"}


def _name_words(n):
    """2026-10-01: a company's or a property's distinctive words ("Golden Promise Mines" and "Golden Promise" give the
    same)."""
    return frozenset(w for w in re.findall(r"[a-z0-9]{2,}", _fold_words(n)) if w not in _GENERIC_CO and w not in _CO_GENERIC)


_CO_NAME = re.compile(r"\b([A-Z][a-z][\w&'’\-]+)\s+(?:[A-Z][\w&.'’\-]*\s+){0,2}(?:Corp(?:oration)?|Inc|Ltd|Limited|plc|PLC|LLC|"
                      r"Pty|S\.A|SA|AB|ASA)\b")


_PN_SUFFIX = re.compile(r"(?i)(?:\s+(?:gold|silver|copper|uranium|lithium|nickel|antimony|tungsten|zinc|graphite|cobalt|"
                        r"polymetallic|porphyry|vms|ree|critical\s+minerals?|rare\s+earths?|base\s+metals?|"
                        r"(?:gold|silver|copper|cu|au|ag|ni|zn|pb|pge)(?:-(?:gold|silver|copper|cu|au|ag|ni|zn|pb|pge|zinc|lead))+))*"
                        r"\s+(?:projects?|property|properties|prospects?|claims?|claim\s+block|deposits?|concessions?|mines?|"
                        r"complex|permit|EP)$")


def _page_name(n):
    """1.2.2: a helper name in this page's form: no trailing suffix or metal words, trimmed as 1.2.1 trimmed its own
    names ("Hemlo Gold Project" -> "Hemlo", "Centrefire Copper-Gold Project" -> "Centrefire")."""
    b = _PN_SUFFIX.sub("", n or "").strip()
    return _clean_proj(b) if b else None


def _proj_key(n):
    s = unicodedata.normalize("NFKD", n or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    w = [x for x in re.findall(r"[a-z0-9]+", s) if x not in ("the", "project", "property", "gold", "silver", "copper")]
    return w[0] if w else s


def _primary_project(title, body, iw=None):
    """1.2.2: 1.2.1's choice (its own finder, the headline first); when it finds none, the shared helper's main
    project (PN.primary) in this page's form, if 1.2.1's own finder also names it in the headline or the body (so a
    region, a zone or a word such as "Development" is not taken for a project)."""
    p = _primary_project_121(title, body, iw)
    if p:
        return p
    q = PN.primary(title, body, _issuer(body))
    n = _page_name(q) if q else None
    if n and any(_proj_key(x) == _proj_key(n) for _p, x in _projects(title, iw) + _projects(body, iw)):
        return n
    return None


def _in_body(name, body):
    """1.2.3: the body names it too, whole and with a capital (a headline fragment such as "Include" or "Well", or
    "Glenstar Minerals Submits", is not)."""
    toks = re.findall(r"[\w'\u2019\u00c0-\u00ff]+", (name or "").replace("\u2019", "'"))
    if not toks or all(t.lower() in _GENERIC_CO or t in _BAD_PROJ for t in toks):
        return False
    rx = r"(?i)(?<![\w-])" + r"[\s\-]+".join(re.escape(t) for t in toks) + r"(?![\w-])"
    # (2026-10-01: either apostrophe, "Tom's Pediment" and "Tom's Pediment")
    return any(m.group(0)[:1].isupper() for m in re.finditer(rx, (body or "").replace("\u2019", "'")))


def _title_projects(title, iw=None):
    """2026-10-01 (full text): the headline's names; a possessive in the headline is the issuer's unless the release
    names that company ("Drilling Commencing at Patriot Gold's Windy Peak Gold Project" is Windy Peak)."""
    out = _projects(title, iw)
    if iw is None:
        return out
    for m in _proj_iter(title):
        if any(p == m.start() for p, _n in out):
            continue
        # (the owner is the words just before the possessive, after any headline verb: "Black Mammoth Metals
        # Acquires Tom's Pediment")
        po = re.search(r"((?:[A-Z][\w&\-]*\s+){0,2}[A-Z][\w&\-]*)['\u2019]s\s", m.group(1))
        if not po:
            continue
        ws = po.group(1).split()
        while ws and (ws[0] in _HL_VERB or len(ws) > 1 and any(w in _HL_VERB for w in ws[1:])):
            ws = ws[1:]
        po_words = " ".join(ws)
        ow = set(re.findall(r"[a-z0-9][a-z0-9\-]{2,}|\b[a-z][0-9]\b", _fold_words(po_words)))
        if any("!" + w in iw for w in ow):
            continue
        if len(ws) == 1 and not ow & _GENERIC_CO and not ow & iw:
            # a single plain word, not the issuer's: a person's or a place's possessive, part of the name ("Tom's
            # Pediment")
            n = _clean_proj(m.group(1)[m.group(1).find(po_words):])
        else:
            n = _clean_proj(m.group(1), iw | ow)
        if n:
            out.append((m.start(), n))
    return sorted(out)


def _stub(title, body):
    """2026-10-01 (full text): the feed carried no release text, only a stub or boilerplate ("This release is published
    on Accesswire ...", a list of links, or a disclaimer and nothing else): no name word of the headline is in it, or
    it opens with the disclaimer."""
    if re.match(r"(?i)^\W*(?:[\w-]+\s+){0,3}?(?:disclaimer|forward[\s-]+looking|cautionary\s+(?:note|statement)|this\s+(?:news\s+)?"
                r"release\s+is\s+published)\b", body or ""):
        return True
    words = [w for w in re.findall(r"\b[A-Z][\w'\u2019\-]{3,}", title or "") if w not in _HL_VERB and w not in _BAD_PROJ
             and w.lower() not in _GENERIC_CO]
    return bool(words) and not any(re.search(r"(?i)(?<![\w-])" + re.escape(w) + r"(?![\w-])", body or "") for w in words)


def _primary_project_121(title, body, iw=None):
    # 1.2.3: a headline name the body never uses is a headline fragment ("Include", "Well"), not the property
    # (2026-10-01: unless the feed carried no release text)
    stub = _stub(title, body)
    # (2026-10-01: or, for a name led by a possessive, the body uses the owner's word: "Acquires Tom's Pediment
    # Gold-Silver Property" and "the geophysical target at Tom")
    ps = [x for x in _title_projects(title, iw) if stub or _in_body(x[1], body) or (
        len(x[1].split()) >= 2 and re.search(r"['\u2019]s$", x[1].split()[0]) and len(re.sub(r"['\u2019]s$", "", x[1].split()[0])) >= 3 and
        re.sub(r"['\u2019]s$", "", x[1].split()[0]) not in _QUALIFIERS and _in_body(re.sub(r"['\u2019]s$", "", x[1].split()[0]), body))]
    counts = {}
    land = set()
    for _p, n, lh in _projects(body, iw, kinds=True):
        counts.setdefault(_proj_key(n), [n, 0])[1] += 1
        if lh:
            land.add(_proj_key(n))
    if ps:
        n = ps[0][1]
        mt = re.search(re.escape(n) + r"\s+(?:\w+\s+){0,3}?(Mine|Deposit|Prospect|Zone|Target)\b", title)
        if mt and counts:
            # 1.2.3: a mine or deposit in the headline gives way to the property the body names most, and to one the
            # body calls a project or property when there is one ("Near-Term Mine Development" is not)
            pool = [v for k, v in counts.items() if k in land]
            best = max(pool or list(counts.values()), key=lambda v: v[1])
            # (2026-10-01, full text: a prospect -- often the company's own early-stage property -- does not give way
            # to a project the body names once, far from the lead: "the Los Andes porphyry project in the west", quoted
            # near the end, beside the "Newly Identified Caribe Gold Prospect")
            if _proj_key(best[0]) != _proj_key(n) and _proj_key(n) not in land and best[1] >= (1 if pool else 2) and \
                    (mt.group(1) != "Prospect" or best[1] >= 2 or _in_body(best[0], body[:1200])):
                return best[0]
        return n
    # 1.2: "Closes Financing For Burnthut Drilling Program", "Kremer-2 Grab Sample Results": the headline names
    # a project the body calls a project, without the word "project" itself
    if not ps and counts:
        tf = " ".join(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()))
        for n, _c in sorted(counts.values(), key=lambda v: -v[1]):
            n = re.sub(r"^[\w.&\-]+['’]s\s+", "", n)      # "IsoEnergy’s Hurricane" is Hurricane
            k = _proj_key(n)
            # the headline's first word is the issuer ("Headwater Gold Commences ...", "Star Copper Concludes ...")
            # ... and "the historic Foley Shaft area" of the Mine Centre Project is a place in it, not the project
            # (1.2.4: or a property known by its capitals -- "Origen LGM and Wishbone Update" and "its 100% owned LGM
            # property" -- which the body calls a property)
            if (len(k) >= 4 or len(k) == 3 and k in land and re.search(r"(?<!\()\b" + re.escape(k.upper()) + r"\b(?!\))", title) and
                    re.search(r"\b" + re.escape(k.upper()) + r"\s+(?:[Pp]roject|[Pp]roperty|[Cc]laims)\b", body)) and \
                    re.search(r"\b" + re.escape(k) + r"\b(?!\s+(?:\w+\s+)?(?:shaft|area|zone|target|showing|trend|vein)s?\b)", tf) \
                    and not tf.startswith(k + " "):
                # 1.2.3: "Continues to Intersect ... in Airstrip": a deposit the body places in its one property
                others = [v[0] for kk, v in counts.items() if kk in land and kk != k]
                if k not in land and len(others) == 1:
                    return others[0]
                return n
    if len(counts) >= 3 and not re.search(r"(?i)\b(?:at|on)\s+(?:the\s+|its\s+)?[A-Z]", title):
        top = sorted(counts.values(), key=lambda v: -v[1])
        if top[0][1] < 2 * top[1][1]:
            return None
    # 1.2.3: "at", "on" and "of" as words ("Exploration Program With JOGMEC" has no "on"), in any case
    m = re.search(r"\b(?i:at|on|of)\s+(?:(?i:the|its)\s+)?" + _CAPNAME + r"\s*(?:,|$|\s+(?i:in)\s+|\s+(?:Area|Zone|Target))", title)
    cands = _projects(body[:4000], iw)
    if cands:
        cnt = {}
        for _p, n in _projects(body, iw):
            k = _proj_key(n)
            cnt[k] = cnt.get(k, 0) + 1
        best = max(cands, key=lambda c: (cnt.get(_proj_key(c[1]), 0), -c[0]))
        return best[1]
    if m:
        n = _clean_proj(m.group(1), iw)
        if n and stub:
            return n                                # 2026-10-01: no release text to check the name against
        if not (n and _in_body(n, body)) and m.group(1).split()[0][:1].isupper():
            q = _program_named(m.group(1).split()[0], body, iw) or _body_prefix(n, body, iw)
            if q:
                return q
        # 2026-10-01 (full text): a zone or target the headline names by its property's possessive ("Begins Drilling at
        # Opemiska's Saddle Zone") is on that property, when no company of that name is in the release
        po = re.match(r"^([A-Z][\w\-]+)['\u2019]s\s", m.group(1))
        if n is None and po and re.search(r"\s(?:Area|Zone|Target)$", m.group(1) + title[m.end(1):m.end(1) + 8].rstrip()) and \
                "!" + _fold_words(po.group(1)) not in iw and _clean_proj(po.group(1), iw) and _in_body(po.group(1), body):
            return _clean_proj(po.group(1), iw)
        return n if n and _in_body(n, body) else _own_complex(body, iw)
    # 1.2.3: "Expands Gold Mineralization at Kabaya Drilling highlights ...": the words after "at" up to the first
    # headline word, when the body names the place too
    m = re.search(r"\b(?i:at|on)\s+(?:(?i:the|its)\s+)?" + _CAPNAME, title)
    if m:
        toks = m.group(1).split()
        k = next((i for i, w in enumerate(toks) if w in _HL_VERB or w in _BAD_PROJ or w in _HL_VERB_IF_DRILL), len(toks))
        n = _clean_proj(" ".join(toks[:k]), iw) if k else None
        if n and (stub or _in_body(n, body)):
            return n
        return _program_named(toks[0], body, iw) or _body_prefix(n, body, iw) or _own_complex(body, iw)
    return _own_complex(body, iw)


def _own_complex(body, iw):
    """2026-10-01 (full text): the company's own mining complex named in lower case ("the Chame target ... within the
    Company's Paciencia complex", "the nine DoE leases which comprise our West Slope complex"), when nothing else names
    the release's property."""
    m = re.search(r"(?:\b[Tt]he\s+Company['\u2019]s|\b[Ii]ts|\b[Oo]ur)\s+" + _CAPNAME + r"\s+(?:mining\s+)?complex\b", _mask_long(body[:4000]))
    return _clean_proj(m.group(1), iw) if m else None


def _body_prefix(n, body, iw):
    """2026-10-01 (full text): the headline runs the place into other words ("at Thor Connecting Megagossan", "at Nickel
    Mountain Discovery"); the longest start of it that the body uses, capitalised, is the place ("Thor", "Nickel
    Mountain")."""
    toks = (n or "").split()
    while len(toks) > 1 and toks[-1] in ("Deposit", "Deposits", "Zone", "Zones", "Target", "Prospect", "Discovery",
                                         "Showing", "Area", "Trend"):
        toks = toks[:-1]
        if _in_body(" ".join(toks), body) and _clean_proj(" ".join(toks), iw):
            return _clean_proj(" ".join(toks), iw)
    # (the end of it only after words that just qualify the name: "Main Nisk" -> "Nisk")
    spans = [toks[:k] for k in range(len(toks) - 1, 0, -1)] + [toks[k:] for k in range(1, len(toks))
                                                                if all(x in _QUALIFIERS for x in toks[:k])]
    for sp in spans:
        q = _clean_proj(" ".join(sp), iw)
        # (not a word that only qualifies a name: "Main" of "its Main Nisk Deposit", which the body calls "Nisk Main")
        if q and len(q) >= 3 and q.split()[-1] not in _BAD_PROJ and not (len(q.split()) == 1 and q in _QUALIFIERS) \
                and _in_body(q, body):
            return q
    return None


_QUALIFIERS = _DIRECTION_WORDS | {"Main", "New", "Old", "Big", "Little", "Great", "Grand", "Upper", "Lower", "Deep"}


def _program_named(first, body, iw):
    """2026-10-01 (full text): the body names the property only before its program ("initial results from the first two
    drillholes of the ongoing Murphy Lake drill program"), and the headline's place starts that name ("... at Murphy
    Visually Identified Pitchblende")."""
    for mp in re.finditer(r"\b(?:the|its|our)\s+(?:(?:ongoing|current|planned|recent|initial|maiden|(?:19|20)\d\d|"
                          r"winter|summer|spring|fall)\s+)*" + _CAPNAME + r"\s+(?:(?:diamond|core|RC)\s+)?(?:drill(?:ing)?|"
                          r"exploration|field)\s+(?:program(?:me)?|campaign)\b", _mask_long(body[:3000])):
        q = _clean_proj(mp.group(1), iw)
        if q and len(q) >= 4 and q.split()[0] == first:
            return q
    return None


FOREIGN = "\x00foreign"


def _heading_property(sents, i, iw):
    """2026-10-01 (full text): in a portfolio update that names no main project, a program sentence that names no
    property is on the property the update last named, in its heading or the sentences just before ("Golden Arrow
    Gold and Silver Property, NV ... York Canyon Property, NV ... The Company just completed an airborne magnetic
    and radiometric geophysical survey"). Only a property, project or claims that opens one of the five sentences
    before, as a heading does."""
    for j in range(i - 1, max(-1, i - 6), -1):
        ps = [n for _p, n, lh in _projects(sents[j], iw, kinds=True) if lh and _p <= 2]
        if ps:
            return ps[-1]
    return None


def _own_landholdings(body, iw, primary):
    """1.2.3: the properties the release calls the company's (project, property, claims, concession), not another
    company's, not a deposit or mine inside one."""
    out = [primary] if primary else []
    for _p, n, lh in _projects(body, iw, kinds=True):
        if lh and all(_proj_key(n) != _proj_key(q) for q in out):
            out.append(n)
    return out


_PART_WORD = re.compile(r"(?i)^\s*(?:patents?|(?:mining\s+)?claims?|claim\s+block|licen[cs]es?|tenements?|leases?)\b")
_PART_DASH = re.compile(r"(?i)\s+(?:patents?|claims?|claim\s+block|licen[cs]es?|tenements?|leases?)\s*[-–—:]\s*")


def _part_keys(title, iw=None):
    """Key gate: the headline's names that are a group of patents, claims, licences or leases rather than a project."""
    keys = set()
    for m in _proj_iter(title):
        n = _clean_proj(m.group(1), iw)
        tail = re.sub(r"^\s+(?:" + _METAL_RUN + r"\s+)?", "", title[m.end(1):m.end()])
        if n and _PART_WORD.match(tail):
            keys.add(_proj_key(n))
    return keys


def _part_in_project(primary, title, body, iw=None):
    """Key gate: a headline property that is a group of patents or claims ("Resistive Trend Unveiled on the Tak
    Patents") which the body places inside one named project or property of the company's ("IP Survey Extent in the
    Tak Patents - Burnthut Property", "the Burnthut Project, which is composed of 83 mining claims, 6 patents") is
    that project: rows are filed under the project, as the company names its property."""
    if not primary or _proj_key(primary) not in _part_keys(title, iw):
        return None
    toks = re.findall(r"[\w'’À-ÿ]+", primary)
    rx = re.compile(r"(?<![\w-])" + r"[\s\-]+".join(re.escape(t) for t in toks) + r"(?![\w-])")
    pk = set(re.findall(r"[a-z0-9]{3,}", _fold_words(primary)))
    found = {}
    for s in _sentences(body):
        pm = rx.search(s)
        if not pm:
            continue
        for m in _proj_iter(s):
            n = _clean_proj(m.group(1), iw)
            tail = re.sub(r"^\s+(?:" + _METAL_RUN + r"\s+)?", "", s[m.end(1):m.end()])
            if not n or not re.match(r"(?i)\s*(?:project|property)\b", tail) or _proj_key(n) == _proj_key(primary) \
                    or pk & set(re.findall(r"[a-z0-9]{3,}", _fold_words(n))):
                continue
            # the sentence has to put the one inside the other ("Tak Patents - Burnthut Property", "located entirely
            # within the Eliza Project claim block", "the X Project, which is composed of ... patents"), not compare
            # them ("very similar to what we have seen at our Sagtjarn Property")
            lo, hi = min(pm.start(), m.start()), max(pm.end(), m.end())
            if m.start() > pm.start():
                hi += 40                            # (the project's own clause: "..., which is composed of")
            if re.search(r"(?i)\b(?:within|inside|part\s+of|forms?\s+part|composed\s+of|compris\w+|consists?\s+of|"
                         r"made\s+up\s+of)\b", s[lo:hi]) or \
                    (pm.start() < m.start() and _PART_DASH.fullmatch(s[pm.end():m.start()])):
                found.setdefault(_proj_key(n), n)
    return next(iter(found.values())) if len(found) == 1 else None


def _project_in(s, projects, primary, iw=None, pos=None):
    """The project a sentence's program is on. 1.2.3: the property named nearest before the program (a name after
    it only when none comes before), including a bare mention of one of the release's own properties ("At Cervantes,
    Aztec has drilled ..."); a deposit, mine or prospect inside the release's project is that project; another
    company's property gives FOREIGN."""
    if pos is None:
        for _p, n in _projects(s, iw):
            for q in projects:
                if _proj_key(q) == _proj_key(n):
                    return q
            return n
        if iw is not None and any(_clean_proj(m.group(1)) and not _clean_proj(m.group(1), iw) for m in _proj_iter(s)):
            return FOREIGN
        return primary
    cands = []
    for m in _proj_iter(s):
        n = _clean_proj(m.group(1), iw)
        if n is None:
            if iw is not None and _clean_proj(m.group(1)):
                cands.append((m.start(), FOREIGN))
            continue
        tail = re.sub(r"^\s+(?:" + _METAL_RUN + r"\s+)?", "", s[m.end(1):m.end()])
        q = next((x for x in projects if _proj_key(x) == _proj_key(n)), None)
        if q is None and primary and not _LANDHOLDING.match(tail):
            q = primary                             # a deposit, mine or prospect inside the project
        cands.append((m.start(), q or n))
    for q in projects:
        if q and len(q) >= 3:
            # a bare name only as the place of the work, before it ("At Cervantes, Aztec has drilled ..."), not a
            # distance ("40 km from Whitehorse") or a target the program is designed to test
            for m in re.finditer(r"(?:^|\b(?:[Aa]t|[Oo]n|[Ff]or|[Ww]ithin|[Aa]cross)\s+(?:the\s+)?)(" + re.escape(q) +
                                 r")(?![\w-])", s[:pos + 80]):
                if m.start(1) < pos or re.match(r"[Aa]t|[Oo]n", m.group(0)):
                    cands.append((m.start(1), q))
    if not cands:
        return primary
    before = [c for c in cands if c[0] <= pos]
    if before:
        return max(before, key=lambda c: c[0])[1]
    return min(cands, key=lambda c: c[0])[1]


# ------------------------------------------------------------------ program detection
def _types(s):
    """Program types named in a sentence, in order of appearance."""
    hits = []
    for t, rx in (("drilling", _DRILL), ("geophysics", _GEO), ("ground", _GRD)):
        m = rx.search(s)
        if m:
            hits.append((m.start(), t))
    return [t for _p, t in sorted(hits)]


def _status(s):
    best = None
    for st in ("completed", "started", "underway", "planned"):
        m = _ST[st].search(s)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), st)
    return best[1] if best else None


_TENTATIVE = re.compile(r"(?i)\b(?:(?-i:may|might|could)|potential(?:ly)?|possible|planning|contemplat\w+|consider\w*|"
                        r"propos\w+|evaluat\w+\s+(?:a|the)?\s*(?:potential|possible))\b")


_PREP_HL = re.compile(r"(?i)\b(?:earthworks?|trails?|roads?|camp|pads?|access|permits?|preparations?|site\s+work|line[\s-]*cutting|grid)\s+(?:\w+\s+){0,3}?"
                      r"(?:for|ahead\s+of|in\s+preparation\s+for|to\s+support)\s+(?:the\s+|its\s+|a\s+)?(?:upcoming\s+|planned\s+|"
                      r"\d{4}\s+)?(?:drill\w*|exploration|field|IP|geophysic\w*|survey)")
_PROG_WORD = re.compile(r"(?i)\b(?:program(?:me)?s?|campaign|survey|drill\w*|trench\w*|sampling|field\s*work|fieldwork|"
                        r"exploration|geophysic\w*|mapping|prospecting)\b")


def _hl_status(t, ptype=None, results=False):
    if re.search(r"(?i)\bcomplet\w*\s+(?:the\s+)?(?:\w+\s+)?(?:first|additional|further|another|next|more)\s+(?:\w+\s+){0,2}holes?\b", t):
        return "underway"                       # 1.2.3: some holes of a program done ("Completes Three Additional Holes")
    pm = _PREP_HL.search(t)
    if pm and not re.search(r"(?i)\b(?:launch\w*|commenc\w*|begins?|starts?|initiat\w*|kicks?\s+off|complet\w*|mobiliz\w*)\b"
                            r"(?=.{25,}$)", t[:pm.start()]):
        return "planned"
    verbs = []
    for st, rx in _HL_ST:
        for m in rx.finditer(t):
            if st == "planned" and m.group(0).lower().startswith("announces") and re.search(
                    r"(?i)\b(?:program(?:me)?|campaign|survey)\s+(?:discover\w*|intersect\w*|returns?|confirms?|results?)", t):
                continue
            if re.match(r"(?i)\s+(?:trading|operations|production|construction|mining|processing|milling)\b", t[m.end():m.end() + 16]):
                continue
            # 1.2.3: "Expands Strategic Position", "Continues to Return High Grade": not the program's state
            if re.match(r"(?i)\s+(?:(?:its|the|strategic|land|mineral)\s+)*(?:position|land\w*|holdings?|footprint|claims?|"
                        r"ground|portfolio|property|mineraliz\w*|mineralis\w*|strike|zones?|resources?|to\s+(?:return|intersect|"
                        r"expand|define|deliver|hit|confirm|demonstrate|show))\b(?![\w\s-]{0,25}\b(?:drill|program|exploration|survey|geophysic|magnetic|electromagnetic|sampl|"
                        r"mapping|trench|campaign))",
                        t[m.end():m.end() + 30]):
                continue
            verbs.append((m.start(), m.end(), st))
    verbs = [v for v in verbs if not (v[2] == "planned" and t[v[0]:v[1]].lower().startswith("announces") and any(
        o[2] in ("started", "completed") and v[0] < o[0] < v[1] for o in verbs))]
    if not verbs:
        # 1.2.3: a survey or sampling program that has found something is finished ("Identifies New High-Priority
        # Geophysical Target on Samson")
        if ptype in ("geophysics", "ground") and re.search(r"(?i)\b(?:identif(?:ies|ied)|outlines?|defines?|delineates?|"
                                                           r"reveals?|detects?|discovers?|generates?|finds)\b", t):
            return "completed"
        tm, pw0 = _TENTATIVE.search(t), _PROG_WORD.search(t)
        return "planned" if tm and pw0 and tm.start() < pw0.start() else None
    rx = {"drilling": _DRILL, "geophysics": _GEO, "ground": _GRD}.get(ptype)
    pw = (rx.search(t) if rx else None) or _PROG_WORD.search(t)
    if pw:
        def dist(v):
            if v[1] <= pw.start():
                return pw.start() - v[1]
            if v[0] >= pw.end():
                return (v[0] - pw.end()) + 40
            return 0
        # 1.2.3: not a verb about something else the headline names after the program ("... Exploration Program ...
        # Preliminary Economic Assessment Underway")
        # (2026-10-01: a cue is read in the whole headline, so "Q2" in "the Q2 RC Drilling Program" sees its program)
        near = [v for v in verbs if not any(min(v[1], pw.end()) <= x.start() < max(v[0], pw.start())
                                            for x in _NON_EXPL_HL.finditer(t))]
        if not near:
            return None
        verbs = near
        best = min(verbs, key=lambda v: (dist(v), v[2] not in ("started", "completed"), v[0]))
        if results and dist(best) > 45:
            return None
    else:
        if results:
            return None
        best = min(verbs, key=lambda v: (v[2] not in ("completed", "started"), v[0]))
    tm = _TENTATIVE.search(t)
    if tm and best[2] != "completed" and (tm.start() < best[0] or tm.start() - best[0] < 25) and \
            (not pw or tm.start() < max(pw.end(), best[1]) + 5):
        return "planned"
    st = best[2]
    if st == "completed" and re.search(r"(?i)\b(?:update|progress\w*|to\s+date|nearly|so\s+far)\b", t):
        return "underway"
    if st == "underway" and results and re.search(r"(?i)\bcontinues\s+to\s+(?:intersect|return|expand|define|deliver|hit)", t):
        return None
    return st


_ONGOING = re.compile(r"(?i)\b(?:drill(?:ing)?|program(?:me)?|campaign|survey|sampling)\s+(?:\w+\s+){0,3}?(?:is|are|remains?)\s+"
                      r"(?:currently\s+|now\s+|still\s+)?(?:ongoing|underway|under\s+way|in\s+progress|continuing)\b|"
                      r"\b(?:ongoing|current)\s+(?:[\w,-]+\s+){0,3}?(?:drill(?:ing)?\s+)?(?:program(?:me)?|campaign)\b|"
                      r"\b(?:drill(?:ing)?|program(?:me)?|campaign)\s+(?:currently\s+)?(?:underway|ongoing|in\s+progress)\b|"
                      r"\bdrilling\s+(?:continues|is\s+continuing)\b|\bcurrently\s+(?:conducting|carrying\s+out|undertaking)\b|"
                      r"\b(?:drill(?:ing)?|program(?:me)?|campaign)\s+completed\s+to\s+date\b|\b(?:ongoing|continuing)\s+(?:(?:diamond|"
                      r"core|RC|reverse\s+circulation|surface|underground|infill|step-?out|exploration)\s+(?:and\s+)?){0,3}drill\w*|"
                      r"\b(?:drills?|rigs?)\s+(?:are\s+)?(?:now\s+|currently\s+)?(?:turning|active|operating)\b|\bseason\s+(?:is\s+)?underway\b|"
                      # 2026-10-01 (full text): "The drilling campaign continues at the Tamarack Nickel Project"
                      r"\b(?:drill(?:ing)?\s+)?(?:program(?:me)?|campaign)\s+continues\b")


def _YEAR_BEFORE(s, rel_year):
    """1.2.3: the sentence names an earlier year (an older program)."""
    return bool(rel_year) and any(int(y) < rel_year for y in _YEAR.findall(s))


def _hl_type(t, body):
    if re.search(r"(?i)\b(?:geophysic\w*|survey|geological|geochemical|drill(?:ing)?)\s+(?:data\s+)?(?:interpretation|modell?ing|model|"
                 r"inversion|review|compilation|re-?processing)\b", t):
        return None
    m_d, m_g, m_r = _DRILL.search(t), _GEO.search(t), _GRD.search(t)
    # 2026-10-01 (full text): a survey run to guide later drilling ("Commences Ground Magnetic Survey to Guide Diamond
    # Drilling") is the headline's program, not the drilling
    for m_s, kind in ((m_g, "geophysics"), (m_r, "ground")):
        if m_d and m_s and m_s.start() < m_d.start() and re.search(
                r"(?i)\b(?:to\s+(?:guide|define|refine|generate|identify|prioriti[sz]e)|ahead\s+of|prior\s+to|in\s+preparation\s+"
                r"for|for\s+(?:future|upcoming|follow-?up))\b", t[m_s.end():m_d.start()]):
            return kind
    if m_d:
        return "drilling"
    if m_g:
        return "geophysics"
    if m_r:
        return "ground"
    if _EXPLPROG.search(t) or re.search(r"(?i)\bexploration\s+(?:at|on)\b|\bcommences\s+exploration\b", t) or \
            _EXPL_HL2.search(t):
        found = []
        for s in _sentences(body[:4000])[:8]:
            if re.search(r"(?i)\bprogram|campaign|field\s*work\b", s) and _status(s) and not _HIST.search(s):
                ts = _types(s)
                if ts:
                    found.append(ts[0])
        # 1.2.4: a field season that drills is a drilling program (the guide's combined-program rule): "The 2026 field
        # season has started ..." and "Doubleview expects to begin drilling immediately as part of the 2026 exploration
        # program"
        lead = body[:3000]
        if found:
            if "drilling" in found or (found[0] == "ground" and re.search(
                    r"(?i)\b(?:begin|start|commence)\w*\s+drilling\b|\bdrill(?:ing)?\s+(?:program|campaign)\s+(?:is|has|will)\b", lead)):
                return "drilling"
            return found[0]
        if re.search(r"(?i)\bdrill(?:ing)?\s+(?:program|campaign)|\bdrill\s+holes?\b|\bmetres?\s+of\s+drilling", lead):
            return "drilling"
        if _GEO.search(lead) and not _GRD.search(lead):
            return "geophysics"
        return "ground"
    return None


def _fact_window(sents, i, ptype, status=None):
    """The sentence and the next one, when the next continues the same program. 1.2.3: not when the next is about a
    finished program and this one is not, or the other way round ("The Q1 2022 program will include up to 10,000 m
    ... This program follows the recently completed 17,792 m drill program")."""
    s = sents[i]
    if i + 1 < len(sents):
        nxt = sents[i + 1]
        ns = _status(nxt)
        # (key gate: "Approximately 500 metres completed of the planned campaign of up to 5,000 metres" is this
        # program's progress, not a finished program)
        if ns == "completed" and status != "completed" and _OF_PLANNED.search(nxt):
            ns = None
        if status and ns and (ns == "completed") != (status == "completed"):
            return s
        if not _types(nxt) or _types(nxt)[0] == ptype:
            if not _HIST.search(nxt) and not _YEAR.search(nxt) or _YEAR.findall(nxt) == _YEAR.findall(s):
                s = s + " " + nxt
    return s


def _row(ptype, project, status, text, date_year=None, historical=False, operator=None, season=None):
    r = {"program_type": ptype, "project": project, "status": status, "season": season or _season(text, date_year),
         "phase": _phase(text), "historical": 1.0 if historical else 0.0, "operator": operator,
         "metres": None, "holes": None, "line_km": None, "budget": None, "currency": None, "rigs": None,
         "drill_method": None, "survey_type": _survey(text, ptype), "target_metal": None, "contractor": None}
    if ptype == "drilling":
        r["metres"] = _metres(text, status) or _metres_more(text)
        # 1.2.3: a program enlarged in the release has its new size ("the program was expanded to 1,400 m",
        # "increased to 82 holes (5,329 m of core)")
        ex = _EXPANDED.search(text)
        if ex and not historical:
            v = _num(next(x for x in ex.groups() if x))
            if ex.group(0).lower().rstrip(")").endswith(("hole", "holes")):
                r["_holes_ex"] = int(v) if v and v == int(v) else None
            elif v and v >= 50:
                r["metres"] = v
            mm = re.match(r"\s*\(\s*" + _NUM + r"\s*(?:m|metres?|meters?)\b", text[ex.end():ex.end() + 30])
            if mm:
                r["metres"] = _num(next(x for x in mm.groups() if x))
        r["holes"] = _holes(text, historical)
        if r.pop("_holes_ex", None):
            r["holes"] = _EXPANDED_HOLES(text) or r["holes"]
        r["drill_method"] = _method(text)
        r["rigs"] = _rigs(text)
    elif ptype == "geophysics":
        r["line_km"] = _linekm(text)
    b, c = _budget(text)
    r["budget"], r["currency"] = b, c
    r["contractor"] = _contractor(text)
    return r


def _merge(a, b):
    for k, v in b.items():
        if a.get(k) in (None, "") and v not in (None, ""):
            a[k] = v
    return a


def _same_program(a, b, now=None):
    if a["program_type"] != b["program_type"] or _proj_key(a["project"]) != _proj_key(b["project"]):
        return False
    if a["historical"] != b["historical"]:
        return False
    ya, yb = set(_YEAR.findall(a.get("season") or "")), set(_YEAR.findall(b.get("season") or ""))
    if ya and yb and not ya & yb:
        return False
    pa, pb = a.get("phase"), b.get("phase")
    if pa and pb and pa != pb:
        return False
    if a["historical"]:
        return (a.get("operator") or "") == (b.get("operator") or "") and (ya == yb)
    # 1.2: "the 2022 LiDAR survey" is not the survey this release completes, whatever their kinds share
    if bool(ya) != bool(yb) and (a.get("_yearprog") if ya else b.get("_yearprog")):
        return False
    # 1.2.3: nor is a survey dated two or more years back ("a helicopter-borne magnetic survey conducted in the winter
    # of 2016" in a 2020 release about the IP survey just completed)
    if bool(ya) != bool(yb) and now and all(int(y) < now - 1 for y in (ya or yb)):
        return False
    if bool(ya) != bool(yb) and a["status"] != b["status"]:
        und = a if not ya else b
        oth = b if und is a else a
        # 1.2.3: also the headline's "Drilling Underway" and the body's "the 2025 drill program ... completed to date"
        # (key gate: but not a program planned for a later year than the release's -- "a substantial drill program for
        # the spring of 2025" in a 2024 release about the drilling underway is the next program)
        if und["status"] in ("started", "underway") and oth["status"] == "planned" and now and \
                any(int(y) > now for y in (ya or yb)):
            return False
        return und["status"] in ("planned", "started", "underway") and oth["status"] in ("started", "underway", "planned")
    return True


_OPERATOR = re.compile(r"(?:by|for)\s+((?:[A-Z][\w&'’.\-]*\s+){0,4}?(?:[A-Z][\w&'’.\-]*)\s+(?:Inc|Corp(?:oration)?|Ltd|"
                       r"Limited|Resources|Mines|Mining|Exploration|Explorations|Gold|Metals|Minerals|Ventures)\.?)")


def _hist_operator(s, issuer=None):
    ik = set(re.findall(r"[a-z]{3,}", (issuer or "").lower())) - {"inc", "corp", "ltd", "the", "resources", "mining", "metals",
                                                                   "gold", "minerals", "exploration", "limited", "silver",
                                                                   "copper", "corporation", "ventures"}
    for m in _OPERATOR.finditer(s):
        n = m.group(1).strip(" .")
        if _NOT_OPERATOR.search(n) or re.search(r"(?i)\b(?:project|update|property|news|release)\b", n):
            continue
        if ik and ik & set(re.findall(r"[a-z]{3,}", n.lower())):
            continue
        return n
    return "previous owner (unnamed)"


def _nearest(rx, s, a, b, span=110):
    best = None
    for m in rx.finditer(s):
        d = a - m.end() if m.end() <= a else m.start() - b if m.start() >= b else 0
        if d <= span and (best is None or d < best[0]):
            best = (d, m)
    return best[1] if best else None


_WILL = re.compile(r"(?i)\b(?:plan(?:s|ned)?\s+to|expects?\s+to|intends?\s+to|will|to\s+be|would|anticipat\w+\s+to|scheduled\s+to|"
                   r"aims?\s+to|looks?\s+forward\s+to|prepar\w+\s+to|in\s+order\s+to|to(?!\s+(?:announce|report|provide|update|inform|share|present|disclose|confirm)))\s+(?:(?-i:(?![A-Z0-9]))\w+\s+){0,3}$")


def _near_status(s, a, b):
    st = _near_status1(s, a, b)
    w = s[max(0, a - 120):b + 160]
    # 1.2.3: a count of holes done so far ("With seven holes now completed ... in this campaign") or the first holes
    # of a current program ("the initial 49 drillholes ... of an ongoing exploration initiative", "results from its
    # current drilling program") is a program underway; so is "the ongoing program that was started in June"
    if st == "completed" and (re.search(r"(?i)\b\w+\s+(?:drill\s*)?holes?\s+(?:have\s+(?:now\s+)?been\s+|are\s+)?now\s+"
                                        r"(?:been\s+)?complet", w) or re.search(
            r"(?i)\b(?:current|ongoing|continuing)\s+(?:[\w-]+\s+){0,5}?(?:program(?:me)?|campaign|initiative)\b", w)) \
            and not re.search(r"(?i)\b(?:program(?:me)?|campaign)\s+(?:was|has\s+been|is\s+now)\s+complet", w):
        return "underway"
    if st == "started" and re.search(r"(?i)\bongoing\b|\bcontinu(?:es|ing)\b|\bin\s+progress\b", s[max(0, a - 60):b + 60]) \
            and not _WILL.search(s[max(0, a - 40):a]):
        return "underway"
    # "With our exploration season underway with four drills turning ..., our 2026 drill program will be ..."
    if st == "planned" and re.search(r"(?i)\b(?:drills?|rigs?)\s+(?:are\s+)?(?:now\s+)?(?:turning|active|operating)\b|"
                                     r"\bseason\s+(?:is\s+)?underway\b", w):
        return "underway"
    if st == "completed" and re.search(r"(?i)\b(?:following|upon|after|once|until)\s+(?:the\s+)?complet\w*", w) and \
            re.search(r"(?i)\bwill\b|\bplan(?:s|ned)?\b|\bto\s+(?:commence|begin|start|initiate)\b", w):
        return "planned"
    if st in ("completed", "started") and re.search(r"(?i)\bsince\s+(?:the\s+)?(?:commencement|start|beginning)\s+of\s+(?:the\s+|its\s+)?"
                                                     r"(?:[\w-]+\s+){0,3}?(?:program|campaign|drilling)", w):
        return "underway"
    if st == "planned" and not re.search(r"(?i)\b(?:following|after|upon|once|pending|based\s+on|depending\s+on)\s+(?:\w+\s+){0,3}"
                                         r"(?:results?|evaluation|review|receipt)", w) \
            and re.search(r"(?i)\b(?:assay\s+)?results?\s+(?:from|of)\s+(?:its|the|our)\s+(?:[\w,\-()\"“”]+\s+){0,14}?"
                                     r"(?:program(?:me)?|campaign)", w) and not re.search(r"(?i)\bwill\s+(?:commence|begin|start)", w):
        return "underway"
    if re.search(r"(?i)[\d,.]+\s*(?:m|metres?|meters?)\s+of\s+(?:the\s+)?(?:a\s+)?(?:planned\s+)?[\d,.]+\s*(?:-\s*)?(?:m|metres?|meters?)\b", w) \
            and st in ("completed", "planned", "started"):
        return "underway"
    if st in ("underway", "started") and re.search(r"(?i)\bpermit\w*\s+for\b|\breceived\s+(?:a\s+|the\s+)?(?:drill\w*\s+)?permit", w):
        return "planned"
    if st in ("completed", "planned") and re.search(r"(?i)\bcomplet\w*\s+(?:the\s+)?first\s+(?:\w+\s+){0,2}(?:drill\s*)?holes?\s+of\b|"
                                                   r"\bcomplet\w*\s+(?:over\s+|approximately\s+|about\s+|nearly\s+)?(?:a\s+|one\s+)?"
                                                   r"(?:half|third|quarter|\d+\s*%)\s+of\s+(?:the|its|our)\s+(?:[\w-]+\s+){0,3}?(?:planned|program(?:me)?|campaign)", w):
        return "underway"
    if st == "completed" and re.search(r"(?i)\b(?:if|unless|once|until)\s+(?:\w+\s+){0,5}?(?:is\s+|are\s+)?(?:not\s+)?complet", w):
        return "planned"
    if st in ("completed", "started") and not re.search(r"(?i)\bresults?\s+(?:from|for|of)\s+(?:the\s+)?remaining\b", s) \
            and re.search(r"(?i)\b(?:bringing\s+the\s+total|to\s+date|so\s+far)\b",
                                                     s[max(0, a - 60):b + 160]) and not re.search(
            r"(?i)\b(?:program|campaign)\s+(?:was|has\s+been)\s+complet", s):
        return "underway"
    if st == "underway" and re.search(r"(?i)\b(?:plans?|preparations?|planning|permitting)\s+(?:are|is)\s+(?:now\s+|well\s+)?underway|"
                                      r"\bunderway\s+(?:in\s+preparation|ahead\s+of|for\s+the\s+upcoming)", w):
        return "planned"
    if st in ("underway", "started", "completed") and re.search(
            r"(?i)\b(?:program(?:me)?|campaign|survey|drilling)\s+(?:is|are)\s+(?:now\s+|currently\s+)?(?:planned|scheduled|proposed)\b",
            s[max(0, a - 20):b + 80]):
        return "planned"
    if st in ("planned", "completed") and re.search(r"(?i)\bfirst\s+(?:\w+\s+){0,2}holes?\s+(?:to\s+be\s+)?completed\b|"
                                                   r"\bfirst\s+[\d,.]+\s*(?:m|metres?|meters?)\s+of\s+(?:its|the|our)\s+planned", w):
        return "underway"
    if st in ("planned", "completed") and re.search(
            r"(?i)\bhave\s+been\s+drilled\b|\bstart\s+of\s+(?:a|the|its)\s+planned\b|\bremaining\s+(?:~|approximately\s+|about\s+)?\d+\s*%|"
            r"\b\d+\s*%\s+of\s+the\s+(?:planned|program|total)|\bfirst\s+\w+\s+holes?\s+(?:that\s+)?(?:have\s+been\s+|were\s+)?drilled|"
            r"\bresults?\s+(?:for|from)\s+the\s+first\s+\w+\s+holes", w):
        return "underway"
    if st == "completed" and re.search(r"(?i)\bcomplet\w*\s+(?:all\s+)?(?:the\s+)?preparations?\s+for\b", w):
        return "planned"
    if st == "started" and re.search(
            r"(?i)\b(?:approaching|near-term|upcoming|as\s+the\s+(?:[\w-]+\s+){0,3}(?:program\s+|campaign\s+)?commences|"
            r"commencement\s+(?:[\w(),-]+\s+){0,10}?in\s+(?:early\s+|late\s+|mid-?)?(?:January|February|March|April|June|July|August|"
            r"September|October|November|December)\b(?!\s+(?:19|20)\d\d))", w):
        return "planned"
    if st in ("started", "underway") and _TENTATIVE.search(s[max(0, a - 70):b + 50]):
        return "planned"
    # 2026-10-01 (full text): "the dry season has started, Aztec in early 2023 will next carry out channel sampling":
    # the work itself is still ahead
    if st == "started" and re.search(r"(?i)\bseason\s+(?:has\s+)?(?:started|begun|commenced)\b", s) and \
            re.search(r"(?i)\bwill\s+(?:\w+\s+){0,3}?(?:carry\s+o\s?ut|conduct|undertake|begin|commence|start|complete)\b",
                      s[max(0, a - 60):a]):
        return "planned"
    # 1.1: a program part-way through its planned metres is underway (TXG.TO: 'on track to achieve the planned
    # 12,000 m of drilling ... by the end of the year, with 9,430 m completed by mid-May over 12 drill holes')
    if st in ("planned", "completed") and re.search(
            r"(?i)\bon\s+track\s+to\s+(?:achieve|complete|finish|deliver|meet)\s+(?:the|its|our)\s+(?:planned\s+)?|"
            r"\bwith\s+(?:approximately\s+|about\s+|over\s+)?[\d,.]+\s*(?:m|metres?|meters?|holes?)\s+(?:\w+\s+){0,2}"
            r"(?:completed|drilled)\s+(?:to\s+date|so\s+far|by|as\s+of)", w):
        return "underway"
    return st


def _near_status1(s, a, b):
    if re.search(r"(?i)\b(?:nearly|almost|substantially)\s+complete", s[a:b + 40]):
        return "underway"
    m = re.search(r"(?i)\b(?:survey|program(?:me)?|campaign|work|sampling|drilling|drill\s+program)\s+(?:was\s+|were\s+|has\s+been\s+|have\s+been\s+)?"
                  r"(complet\w+|commenc\w+|underway|ongoing|initiated|launched|conducted|flown)\b", s[a:b + 100])
    if m:
        v = m.group(1).lower()
        return ("completed" if v.startswith(("complet", "conduct", "flown")) else "underway" if v in ("underway", "ongoing")
                else "started")
    m = re.search(r"(?i)^\s*(?:was|were|has\s+been|have\s+been|is|are)?\s*(?:now\s+)?(complet\w+|commenc\w+|initiated|underway|"
                  r"launched|conducted|flown|carried\s+out|planned|ongoing|in\s+progress)", s[b:b + 30])
    if m:
        v = m.group(1).lower()
        st = ("completed" if v.startswith(("complet", "conduct", "flown", "carried")) else "planned" if v == "planned"
              else "underway" if v in ("underway", "ongoing", "in progress") else "started")
        if not (st in ("completed", "started") and _WILL.search(s[max(0, a - 40):a])):
            return st
    got = _near_status0(s, a, b)
    if got in ("started", "completed"):
        for st in (got,):
            mm = _nearest(_ST[st], s, a, b, 80)
            if mm and _WILL.search(s[max(0, mm.start() - 40):mm.start()]):
                return "planned"
    if got == "planned" and re.search(r"(?i)\bcontinu(?:e|es|ing)\b", s[max(0, a - 60):b + 60]):
        return "underway"
    return got


def _near_status0(s, a, b):
    best = None
    for st in ("underway", "completed", "started", "planned"):
        m = _nearest(_ST[st], s, a, b, 80)
        if m:
            d = a - m.end() if m.end() <= a else m.start() - b if m.start() >= b else 0
            if best is None or d < best[0]:
                best = (d, st)
    return best[1] if best else None


def _near_year(s, a, b):
    m = _nearest(_YEAR, s, a, b, 60)
    return m.group(1) if m else None


def _near_season(s, a, b):
    m = _nearest(_SEASON, s, a, b, 60)
    return _season(m.group(0)) if m else None


_ELSEWHERE = re.compile(r"(?i)(?:\b(?:on|at)\s+(?:the\s+)?(?:adjacent|adjoining|neighbou?ring|nearby)\b|\bthe\s+nearby\b|"
                        r"\b(?:adjacent|adjoining|neighbou?ring)\s+(?:property|properties|claims?|projects?)\b|"
                        r"\balong\s+strike\s+(?:from|of)\b|\blocated\s+[\d.]+\s*km\s+(?:along|from|away|to)\b|\banalogous\b)")
_ISSUER = re.compile(r"^\W*(?:[\w./\-]+\s*,\s*[\w ./\-]+\s*[-–—:(/]?\s*)?(?:DATE\s*)?(?:/\w+/\s*)?[-–—:]?\s*"
                     r"([A-Z][\w&'’.\-]*(?:\s+[A-Z][\w&'’.\-]*){0,5})\s*\(")
_CUMULATIVE = re.compile(r"(?i)\b(?:since\s+(?:its\s+|the\s+)?(?:(?:19|20)\d\d|inception|acquisition|discovery)|to\s+date|"
                         r"historically|over\s+the\s+(?:past|last)\s+(?:\w+\s+)?(?:years|decades)|"
                         # 1.2.3: "cumulative" only as a running total ("a cumulative drilling of 2,805 metres" in 13 holes is
                         # the program's size)
                         r"cumulative(?=[^.;]{0,40}\b(?:since|to\s+date|over\s+the|history|historical|all\s+(?:drilling|programs)))|in\s+total\s+"
                         r"since|over\s+the\s+(?:life|history)|a\s+total\s+of\s+[\d,.]+\s*(?:m|metres?|meters?)\s+(?:\w+\s+)"
                         r"{0,4}since|(?:was|were)\s+(?:first\s+)?discovered)\b")
_DISCLAIM = re.compile(r"(?i)\b(?:for\s+information(?:al)?\s+purposes|(?:has|have)\s+not\s+(?:been\s+)?(?:independently\s+)?"
                       r"verif\w+|not\s+been\s+verified|should\s+not\s+be\s+relied|cannot\s+be\s+relied|not\s+necessarily\s+"
                       r"indicative|is\s+not\s+(?:necessarily\s+)?indicative)\b")
_NON_EXPL_HL = re.compile(r"(?i)\b(?:resource\s+estimate|mineral\s+resource|feasibility|PEA|preliminary\s+economic|"
                          r"private\s+placement|financing|flow[\s-]*through|bought\s+deal|offering|royalt\w*|stream|"
                          r"acqui(?:re|res|red|sition)|arrangement|merger|amalgamation|option\s+agreement|quarter(?:ly)?|"
                          r"financial\s+(?:results|statements)|MD&A|annual\s+(?:general\s+)?meeting|AGM|shareholder|"
                          r"warrants?|listing|grant\s+of\s+options|stock\s+options|name\s+change|webinar|conference|"
                          r"production\s+(?:results|update)|"
                          # (2026-10-01: not a quarter that times a program -- "Completion Of The Q2 RC Drilling Program")
                          r"Q[1-4]\b(?!\s+(?:(?:19|20)\d\d\s+)?(?:[\w-]+\s+){0,2}(?:drill\w*|program\w*|campaign|survey|"
                          r"exploration|field|sampling))|reserves?|construction|advisory|appoint\w*|"
                          # (2026-10-01: a regulator's board -- "Mackenzie Valley Land and Water Board" -- is not the
                          # company's)
                          r"(?<!water\s)(?<!review\s)(?<!impact\s)(?<!licensing\s)(?<!planning\s)board|director|CEO|CFO|"
                          r"symbol|OTCQB|DTC|tenures?|clarif\w*|corporate\s+update|metallurg\w*)\b")
_OTHER_OP = re.compile(r"(?:(?:completed|conducted|drilled|carried\s+out|undertaken|performed|flown|operated)\s+(?:[\w,]+\s+){0,3}?by|"
                       r"(?:owned|held)\s+by)\s+(?:the\s+)?([A-Z][\w&'’.\-]*(?:\s+(?:[A-Z][\w&'’.\-]*|and|&)){0,4})|"
                       r"\b([A-Z][\w&'’.\-]+(?:\s+[A-Z][\w&'’.\-]+){0,3})\s+(?:conducted|completed|drilled|carried\s+out|"
                       r"undertook|flew)\b")
_NOT_OPERATOR = re.compile(r"(?i)^(?:the\s+)?(?:company|corporation|we|it|our|they|management|DATE|in|during|between|"
                           r"geologists?|crews?|teams?|contractors?)\b|drill|geophys|survey|geotech|consult|service|"
                           r"forage|laborator|labs?\b|geoscien|helicopter|aviation|expert|geolog|\bQP\b|qualified")


_ISSUER2 = re.compile(r"([A-Z][\w&'’.\-]*(?:\s+[A-Z][\w&'’.\-]*){0,5})\s*\((?:[\"“]|the\s+|TSX|CSE|NYSE|NASDAQ|"
                      r"OTC|ASX|AIM|NEO|Cboe|FSE|FRA)")


_PP = re.compile(r"(?i)(?:\bdrill(?:ing)?\s+(?:program(?:me)?|campaign|phase)|\b(?:diamond|core|RC|reverse\s+circulation|sonic|"
                 r"auger|aircore|air\s+core|RAB)\s+(?:drill(?:ing)?\s+)?(?:program(?:me)?|campaign)|[\d,.]+\s*(?:-\s*)?(?:m|metres?|meters?)"
                 r"\s+(?:of\s+)?(?:\w+\s+){0,2}drill(?:ing)?\b|\b\d+\s*(?:-\s*)?(?:\w+\s+){0,2}(?:drill\s*)?holes?\b|\b\w+-hole\b|"
                 # 1.2.3: a spelled-out count ("thirteen diamond drill holes were drilled")
                 r"\b(?:" + "|".join(sorted(_NUMW, key=len, reverse=True)) + r")\s+(?:\w+\s+){0,2}(?:drill\s*)?holes?\b|"
                 r"\b(?:survey|trenching|sampling|mapping|prospecting|field|exploration|work|geophysical|geochemical)\s+"
                 r"(?:program(?:me)?|campaign|season)|\bsurveys?\b|\bfield\s*work\b|\bfieldwork\b|\bprogram(?:me)?\b|\bcampaign\b|"
                 # 2026-10-01 (full text): "completed further surface sampling on Megagossan Zone in 2022"
                 r"\b(?:surface|soil|rock|channel|till)\s+sampling\b)")
_ANY_ST = re.compile("|".join("(?:%s)" % rx.pattern.replace("(?i)", "") for rx in _ST.values()), re.I)
_SINCE_EVENT = re.compile(r"(?i)^\W*since\s+(?:[\w.&-]+['’]s\s+|[\w.&-]+\s+){0,5}?(?:(?:19|20)\d\d|initial\s+|first\s+)?"
                          r"(?:acquisition|acquir\w+|inception|discovery|option\w*|IPO|listing|commencement|(?:19|20)\d\d)")
_THIS_YEAR = re.compile(r"(?i)\b(?:this|the\s+current)\s+(?:calendar\s+|field\s+)?(?:year|season)\b|"
                        r"\b(?:by|before)\s+(?:the\s+)?end\s+of\s+(?:the|this)\s+year\b|\bfor\s+the\s+(?:calendar\s+)?year\b|"
                        r"\b(?:later|earlier)\s+(?:in\s+)?(?:the|this)\s+year\b")
_SUBAREA_AT = re.compile(r"\b(?:[Pp]lanned|[Dd]rill(?:ing|ed)?|[Mm]etres|[Mm]eters|m)\b[^.;]{0,60}?\b(?:at|on)\s+(?:the\s+)?"
                         r"([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){0,2})\s+(?:and|&)\s+([A-Z][\w'-]+)")
_SUBAREA_TO = re.compile(r"(?i)\bspecific(?:ally)?\s+to\s+(?:the\s+)?(?:[\w-]+\s+){0,3}?(?:of\s+)?(?:the\s+)?(?-i:([A-Z][\w'-]+))")
_NOT_AREA = re.compile(r"(?i)^(?:the|property|project|company|phase|DATE|Q[1-4]|January|February|March|April|May|June|July|"
                       r"August|September|October|November|December)$")


def _part_of_property(s, project):
    """1.1: metres stated for named parts of a larger property are that part's program, not the property's. TXG.TO:
    'More broadly across the Morelos Property, approximately 15,000 m of drilling is planned for this year at El
    Naranjo and Atzcala'; 'the planned 12,000 m of drilling specific to the northern extension of EPO'. The row keeps
    its status and season; its size is left to the release that states the property's program."""
    pk = _proj_key(project or "")
    if not pk:
        return False
    m = _SUBAREA_TO.search(s)
    if m and _proj_key(m.group(1)) != pk and not _NOT_AREA.match(m.group(1)):
        return True
    m = _SUBAREA_AT.search(s)
    whole = re.search(r"(?i)\b(?:across|throughout)\s+(?:the\s+)?(?:broader\s+|wider\s+|entire\s+)?([\w'-]+)", s)
    if m and whole and _proj_key(whole.group(1)) == pk and not re.search(
            r"(?i)\b(?:includ\w*|compris\w*|such\s+as|consist\w*)\b", s[whole.end():m.end()]) and all(_proj_key(g) != pk and not _NOT_AREA.match(g.split()[0]) for g in m.groups()):
        return True
    return False


# 1.1.1: 'With approximately 125,000 metres of drilling planned in 2025' is the program even when the same sentence
# talks about production (TXG.TO's year-end reserves release)
_METRES_PLANNED = re.compile(r"(?i)\b[\d,.]+\s*(?:m|metres?|meters?)\s+of\s+(?:\w+\s+)?drilling\s+(?:is\s+|are\s+)?"
                             r"planned\s+(?:in|for)\s+(?:19|20)\d\d\b")
_HL_TARGET = re.compile(r"\b(?:[Ff]rom|[Aa]t)\s+(?:the\s+)?([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){0,3})")
_NOT_TARGET = re.compile(r"(?i)^(?:surface|depth|the|results?|drill\w*|new|high|its|our|DATE|Q[1-4]|\d)")


def _target_of_complex(title, project, s, body):
    """1.1.1: a release headlined on one target of a multi-deposit complex reports that target's drilling, not the
    project's. TXG.TO 'Reports Promising Drill Results from Media Luna West': 'A total of 10,744 m of drilling was
    conducted across 23 drill holes during 2025' is Media Luna West's ('The Media Luna West target is part of the Media
    Luna Cluster'), not the Morelos Property's 2025 program. Returns the target's name, used as the row's project, or
    None. Only when the headline and the sentence do not name the project, and the release says the target is part of
    a cluster, complex, district or camp."""
    pk = _proj_key(project or "")
    if not pk or pk in re.findall(r"[a-z0-9]+", _fold_words(title)) or pk in re.findall(r"[a-z0-9]+", _fold_words(s)):
        return None
    for m in _HL_TARGET.finditer(title or ""):
        name = m.group(1).strip()
        name = re.sub(r"\s+(?:Results?|Drill\w*|Program\w*|Target|Deposit|Zone)\b.*$", "", name)
        if not name or _NOT_TARGET.match(name) or _proj_key(name) == pk:
            continue
        if re.search(re.escape(name) + r"\s+(?:target|deposit|zone|prospect|area)?\s*(?:is|forms)\s+(?:a\s+)?(?:part\s+of|"
                     r"within|located\s+(?:with)?in)\s+the\s+(?:[\w'-]+\s+){0,4}?(?:Cluster|Complex|District|Camp)\b", body or ""):
            return name
    return None


def _fold_words(t):
    t = unicodedata.normalize("NFKD", t or "").lower()
    return "".join(c for c in t if not unicodedata.combining(c))


_CUMUL2 = re.compile(r"(?i)\b(?:invested|in\s+aggregate|there\s+has\s+been|have\s+been\s+drilled\s+on\s+the\s+(?:project|property)|"
                     r"over\s+the\s+(?:years|life)|historical\s+total|including\s+the\s+recent)\b")


def _strong(w):
    """A program phrase with a status word close to it, and no running-total wording."""
    if _CUMUL2.search(w):
        return False
    sts = [m.start() for m in _ANY_ST.finditer(w)]
    for m in _PP.finditer(w):
        if any(abs(p - m.start()) < 70 or abs(p - m.end()) < 70 for p in sts):
            return True
    return False


def _issuer(b):
    m = _ISSUER.search(b[:400]) or _ISSUER2.search(b[:1500])
    return m.group(1) if m else None


def _other_operator(s, issuer):
    """A company other than the issuer that ran the work ("drilled by Kennecott in 2022", "Ethos conducted ...")."""
    ik = set(re.findall(r"[a-z]{3,}", (issuer or "").lower())) - {"inc", "corp", "ltd", "the", "resources", "mining",
                                                                   "metals", "gold", "minerals", "exploration", "limited",
                                                                   "silver", "copper", "corporation", "ventures"}
    ms = sorted([m for i in range(len(s)) for m in [_OTHER_OP.match(s, i)] if m and (m.group(1) or m.group(2))
                 and (i == 0 or not s[i - 1].isalnum())], key=lambda m: (m.group(1) is None, m.start()))
    for m in ms:
        n = (m.group(1) or m.group(2) or "").strip(" .,")
        if not n or _NOT_OPERATOR.search(n) or n.split()[0] in _BAD_PROJ or n.split()[0] in _HL_VERB:
            continue
        if re.match(r"^(?:19|20)\d\d$", n) or len(n) < 3 or re.match(r"^[A-Z]{2,5}$", n):
            continue
        if m.group(2) and len(n.split()) < 2 and not re.search(r"(?:Gold|Mines|Mining|Resources|Metals|Minerals|Corp|Inc|Ltd)$", n):
            continue
        if ik and ik & set(re.findall(r"[a-z]{3,}", n.lower())):
            continue
        return n, m.start()
    return None


# 1.2.3 exclusions (see analyse)
_DATABASE = re.compile(r"(?i)\bdata\s*base\s+for\s+the\s+(?:\w+\s+){0,2}?resource\b|\b(?:MRE|(?:mineral\s+)?resources?\s+estimat\w*|(?:the|this|current)\s+estimate|block\s+model|"
                       r"resource\s+model|(?:19|20)\d\d\s+update)\b[^.;]{0,60}?\b(?:is|was|were|are|has\s+been|have\s+been)?"
                       r"\s*(?:based\s+(?:on|upon)\s+(?:a\s+|the\s+)?(?:validated\s+)?(?:data\s*base|data|drill\w*|reverse|"
                       r"diamond|RC|historic\w*)|constructed\s+(?:from|using)|underpinned\s+by|built\s+(?:on|from|using)|"
                       r"derived\s+from|carried\s+out\s+on)\b|\bintersected\s+by\s+[\d,.]+\s*m\s+of\s+drilling|"
                       r"\b(?:historic\w*\s+)?drilling\s+and\s+the\s+[\w\s]{0,20}?(?:update|estimate)\s+support|"
                       # 2026-10-01 (full text): "The Resource ... is supported by 224,000 m of drilling", "Supporting
                       # drill dataset consists of ..."
                       r"\b(?:resources?|estimate|MRE)\b[^.;]{0,100}?\bsupported\s+by\s+[\d,.]+\s*(?:m|metres?|meters?)\s+of\s+"
                       r"(?:\w+\s+){0,2}drill|\bdrill(?:ing|hole)?\s+data\s*(?:set|base)\s+(?:consists|comprises|includes)\b")
_COMMITMENT = re.compile(r"(?i)\bobligat(?:ed|ion)\s+to\s+(?:complete|spend|incur|drill|fund|carry)|"
                         r"\brequired\s+to\s+(?:complete|spend|incur|drill|fund|carry)|\bin\s+order\s+to\s+(?:earn|maintain|exercise)|"
                         r"\bto\s+earn\s+(?:a|an|its|their|the|up\s+to)\b|\bfirm\s+commitment|\bwork\s+commitments?")
_CONDITIONAL = re.compile(r"(?i)\b(?:if|should|provided\s+that|assuming)\s+(?:\w+\s+){0,4}?(?:successful|warranted|positive|"
                          r"justified|favourable|favorable)\b|\b(?:has|have|holds?|with)\s+the\s+(?:right|option)\s+to\b|"
                          r"\bat\s+(?:its|their)\s+(?:sole\s+)?(?:option|discretion)\b|\bcontingent\s+(?:up)?on\b|"
                          r"\bdepending\s+(?:up)?on\s+(?:the\s+)?(?:results?|success|funding|financing)")
# a release about marketing, investor relations or corporate housekeeping reports a program only with a size
_MARKETING_HL = re.compile(r"(?i)\b(?:investor\s+relations|corporate\s+communications|marketing|market[\s-]+mak\w+|"
                           r"consult\w+|advisor\w*|analyst\s+coverage|to\s+present|presents?\s+at|"
                           r"conference|webinar|interview|podcast|video|website|newsletter|joins\s+(?:the\s+)?"
                           r"board|board\s+of\s+directors|appoint\w*|name\s+change|changes\s+(?:its\s+)?name|annual\s+"
                           r"(?:general\s+)?meeting|AGM|voting\s+results|stock\s+options|grant\s+of\s+options|share\s+"
                           r"consolidation|DTC|OTCQB|OTCQX)\b")
# a testwork release: its "field program" is the tests, not ground exploration
_TESTWORK_HL = re.compile(r"(?i)\b(?:metallurg\w*|test\s*work|field\s+tests?|pilot\s+(?:plant|test\w*)|bench[\s-]+scale|"
                          r"leach\w*|recover(?:y|ies)|carbon\s+(?:capture|sequestration|storage|mineralization|neutral))\b")
_TICKER = re.compile(r"([A-Z][\w&.'’\-]*(?:\s+[A-Z][\w&.'’\-]*){0,4})\s*\((?:TSX|TSXV|TSX-V|ASX|NYSE|NASDAQ|CSE|LSE|AIM|"
                     r"JSE|OTC\w*|NEO)\s*[:\-]")


def _other_company_named(s, iw):
    """1.2.3: a sentence that names a company other than the issuer by its ticker ("Silver Mines Limited (ASX: SVL)")."""
    for m in _TICKER.finditer(s):
        w = {x for x in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", _fold_words(m.group(1))) if x not in _GENERIC_CO}
        if w and not (w & iw):
            return True
    return False


def _same_size(a, b):
    """1.2.3: two rows that give the same program's size -- the same metres, or the same holes (4 or more) -- with
    nothing that tells them apart (season, phase, operator), are one program read twice: as started and as completed,
    under a zone's and the property's name, or from the headline and the body."""
    if a["program_type"] != b["program_type"] or bool(a["historical"]) != bool(b["historical"]):
        return False
    ma, mb, ha, hb = a.get("metres"), b.get("metres"), a.get("holes"), b.get("holes")
    same_m = bool(ma and mb) and abs(ma - mb) <= 0.01 * max(ma, mb)
    same_h = bool(ha and hb) and ha == hb and ha >= 4
    if not (same_m or same_h) or (ma and mb and not same_m) or (ha and hb and ha != hb):
        return False
    ya, yb = set(_YEAR.findall(a.get("season") or "")), set(_YEAR.findall(b.get("season") or ""))
    if ya and yb and not ya & yb:
        return False
    if a.get("phase") and b.get("phase") and a["phase"] != b["phase"]:
        return False
    oa, ob = a.get("operator") or "", b.get("operator") or ""
    if oa and ob and oa != ob and not oa.startswith("previous owner") and not ob.startswith("previous owner"):
        return False
    sa, sb = a["status"], b["status"]
    # (an underway program's figures to date read once as underway and once as done)
    return sa == sb or {sa, sb} <= {"planned", "started", "underway"} or {sa, sb} == {"underway", "completed"}


def _one_program(a, b):
    """(see _one_program_121 below; 1.2.3 adds: a drilling and a ground row from one sentence with the same status and
    season -- "the 2023 drilling and trenching programs" -- are one program, as the guide makes them)"""
    if a.get("_src") and a.get("_src") == b.get("_src") and a["status"] == b["status"] and \
            not a["historical"] and not b["historical"] and _proj_key(a["project"]) == _proj_key(b["project"]) and \
            {a["program_type"], b["program_type"]} == {"drilling", "ground"} and (a.get("season") or None) == (b.get("season") or None):
        return True
    return _one_program_121(a, b)


def _field_program_of(g, d):
    """1.2.3: a general field or exploration program (no one kind of ground work named) and a drilling program on the
    same project with the same status, and no season or phase that tells them apart, are one program: its drilling row
    ("the Phase 1 exploration fieldwork program" and "thirteen diamond drill holes were drilled", "the remaining drill
    holes from the 2023 Field Program")."""
    if g["program_type"] != "ground" or d["program_type"] != "drilling" or g["historical"] or d["historical"]:
        return False
    if g.get("survey_type") not in (None, "mixed") or g["status"] != d["status"] or \
            _proj_key(g["project"]) != _proj_key(d["project"]):
        return False
    if not re.search(r"(?i)\b(?:field\s*(?:program(?:me)?|work|season|campaign)|fieldwork|exploration\s+(?:program(?:me)?|work|"
                     r"campaign))\b", g.get("_src") or ""):
        return False
    ya, yb = set(_YEAR.findall(g.get("season") or "")), set(_YEAR.findall(d.get("season") or ""))
    if ya and yb and not ya & yb:
        return False
    if g.get("phase") and d.get("phase") and g["phase"] != d["phase"]:
        return False
    return True


def _one_program_121(a, b):
    """1.2.3: a sentence that names one program of several kinds of work ("Phase 1 program consisting of soil
    geochemistry and a ground IP survey", "The proposed work program will include trenching and up to 8,000 m of
    diamond drilling") gives one row, not a row per kind: drilling when drilling is part of it, else ground."""
    return bool(a.get("_src")) and a.get("_src") == b.get("_src") and a["status"] == b["status"] and \
        not a["historical"] and not b["historical"] and _proj_key(a["project"]) == _proj_key(b["project"]) and \
        a["program_type"] != b["program_type"] and (a.get("season") or None) == (b.get("season") or None) and \
        bool(_COMBINED.search(a["_src"])) and not re.search(r"(?i)\b(?:programs|campaigns|surveys\s+and|"
                                                             r"and\s+(?:a|an|the)\s+(?:separate|second|additional))\b", a["_src"])


_COMBINED = re.compile(r"(?i)\b(?:program(?:me)?|campaign|work|phase|exploration)\b[^.;]{0,60}?\b(?:will\s+|to\s+)?"
                       r"(?:includ\w*|consist\w*\s+of|compris\w*|involv\w*|entail\w*|combin\w*)\b|"
                       r"\b(?:program(?:me)?|campaign)\s+of\b")


# ------------------------------------------------------------------ the reader
# a survey by a government body or a university is not the issuer's program (1.2)
_RE_GOV = re.compile(r"(?i)\b(?:government|USGS|USBM|universit\w+|academic|geological\s+survey|GSC|OGS|MERN|MRNF|"
                     r"provincial|federal|ministry)\b")


def analyse(headline, body):
    h, b = _prepare(headline, body)
    title = _title(h)
    rel_year = _release_year(b)
    b = _drop_title(_undate(b), title)
    title = _undate(title)
    if len(b) < 200 and not title:
        return {"rows": [], "reason": "no text"}
    iw = _issuer_words(title, b)                    # 1.2.3
    if _stub(title, b):
        iw = {w for w in iw if not w.startswith("!")}  # 2026-10-01: a stub's company names are the issuer's
    primary = _primary_project(title, b, iw)
    part_of = _part_in_project(primary, title, b, iw)   # key gate
    if part_of:
        primary = part_of
    issuer = _issuer(b)
    known = _own_landholdings(b, iw, primary)
    sents = _sentences(b)
    date_year = None
    rows = []
    weak_rows = []
    reason = None

    # 1. the program the headline is about
    ptype = _hl_type(title, b)
    if ptype and _MINE_DRILL.search(title):
        ptype = None                                # 2026-10-01: drilling for a mine's construction
    other_news = bool(_NON_EXPL_HL.search(title)) and not ptype
    acq_hl = bool(re.search(r"(?i)\b(?:to\s+acquire|acquires|acquisition\s+of|agreement\s+to\s+acquire|options?\s+(?:the|its|a)\b|"
                            r"definitive\s+agreement|purchase\s+agreement)", title))
    deal_hl = bool(re.search(r"(?i)\b(?:options?|optioned|acquir\w+|acquisition|agreement|earn-?in|purchase\w*|LOI)\b", title))
    hl_results = bool(_RESULTS_HL.search(title))
    if ptype and not re.search(r"(?i)\b(?:resource\s+estimate|feasibility|PEA|technical\s+report|production|"
                               r"(?:mineral\s+)?reserves?\s*(?:&|and)\s*(?:mineral\s+)?resources?|"
                               r"year[\s-]+end\s+(?:19|20)\d\d\s+(?:results|reserves?|financial|mineral)|"
                               r"(?:first|second|third|fourth|Q[1-4])\s+quarter|annual\s+results)\b", title) \
            and not re.search(r"(?i)\bhistoric\w*\s+(?:\w+\s+){0,2}(?:drill\w*|samples?|sampling|trench\w*|data|work|surveys?)",
                              title):
        st = _hl_status(title, ptype, hl_results)
        if st is None and hl_results:
            st = "completed" if ptype != "drilling" or re.search(
                r"(?i)\b(?:final|complete|all|remaining)\s+(?:\w+\s+){0,2}(?:results|assays)\b", title) else None
        # 1.2: "Assay Results from Maiden Diamond Drill Program": results do not say whether the drilling is over;
        # the body's own sentence about the program does ("the recently completed Phase 1 drill program")
        if st is None and hl_results:
            prx = {"drilling": _DRILL, "geophysics": _GEO, "ground": _GRD}[ptype]
            for s0 in sents[:20]:
                m0 = prx.search(s0)
                # the sentence has to be about the program ("program", "campaign", a size), not one hole
                # ("completed drill hole #1 and has begun drilling hole #2") or the targeting around it
                if m0 and not _HIST.search(s0) and not _ELSEWHERE.search(s0) \
                        and (re.search(r"(?i)\b(?:program(?:me)?|campaign|phase)\b", s0) or _metres(s0) or _holes(s0)
                             or _ONGOING.search(s0)) \
                        and not re.search(r"(?i)\bcomplet\w*\s+(?:the\s+)?(?:first\s+)?(?:drill\s*)?hole\b", s0):
                    own = _near_status(s0, m0.start(), m0.end())
                    # "The program comprised 4,089 metres in nine diamond drill holes" (KLD.V) is a finished program
                    if own is None and re.search(r"(?i)\b(?:program(?:me)?|campaign)\s+(?:comprised|consisted\s+of|"
                                                 r"totall?ed|included)\b", s0) and (_metres(s0) or _holes(s0)):
                        own = "completed"
                    if own in ("completed", "underway"):
                        st = own
                        break
        # 1.2.3: "Provides Update on Drilling" says only that there is news; the lead's own sentence about the program
        # says whether it is finished ("has now completed 1,374 metres of sonic drilling") or yet to start ("the maiden
        # program ... is expected to commence in mid-March")
        if st == "underway" and re.search(r"(?i)\bupdates?\b", title) and not re.search(
                r"(?i)\b(?:continues|ongoing|progress\w*|underway|expands|advances)\b", title):
            prx = {"drilling": _DRILL, "geophysics": _GEO, "ground": _GRD}[ptype]
            for s0 in sents[:8]:
                m0 = prx.search(s0)
                if m0 and not _HIST.search(s0) and not _ELSEWHERE.search(s0) and not _YEAR_BEFORE(s0, rel_year):
                    own = _near_status(s0, m0.start(), m0.end())
                    # (one hole finished -- "the third hole (CL-20-03) has been completed" -- is a program underway)
                    if own == "completed" and re.search(r"(?i)\b(?:complet\w*\s+(?:[\w-]+\s+){0,6}?(?:drill\s*)?"
                                                        r"hole\b(?!s)|hole\b(?!s)[^.;]{0,40}\bcomplet)", s0):
                        break
                    if own in ("completed", "planned"):
                        st = own
                    if own:
                        break
        if st:
            # the body sentences about this program give its facts
            text = title
            for i, s in enumerate(sents[:25]):
                own = _status(s)
                if own and ((own == "completed") != (st == "completed")) and st != "underway":
                    continue
                if ptype in _types(s) and not _HIST.search(s) and not _RESULTS_HL.search(s[:60]) and not _ELSEWHERE.search(s):
                    # 1.2.3: not a sentence about another of the company's properties, or another company's
                    tm = {"drilling": _DRILL, "geophysics": _GEO, "ground": _GRD}[ptype].search(s)
                    if primary and _proj_key(_project_in(s, known, primary, iw, tm.start())) != _proj_key(primary):
                        continue
                    text += " " + _fact_window(sents, i, ptype, st)
                    if _metres(s) or _holes(s) or _linekm(s):
                        break
            text = text[len(title):] + " " + title
            r = _row(ptype, primary, st, text)
            ts = _season(title)
            if not ts and r["season"] and (not rel_year or not all(int(y) >= rel_year for y in _YEAR.findall(r["season"]))):
                ts = None
                r["season"] = None
            r["season"] = ts or r["season"]
            if primary:
                rows.append(r)
    elif not ptype:
        reason = "the headline names no program"

    # 2. programs the body states with a clear status and a distinguishing fact
    now = rel_year
    royalty_rel = bool(re.search(r"(?i)\broyalt\w*|\bNSR\b", title + " " + b[:1500]))   # 2026-10-01
    test_hl = bool(_TESTWORK_HL.search(title)) and not ptype
    for i, s in enumerate(sents):
        if _NOT_PROGRAM.search(s) and not re.search(r"(?i)drill(?:ing)?\s+program", s) and not _METRES_PLANNED.search(s):
            continue
        mm, md = _MINE_DRILL.search(s), _DRILL.search(s)
        if mm and (not md or md.start() >= mm.start() - 40):
            continue                                # 2026-10-01: drilling for a mine's construction (the first named)
        if re.match(r"(?i)^(?:figure|fig\.|table|photo|plate|map|source|note|plan\s+view|cross[\s-]+section|long[\s-]+section|"
                    r"location\s+of|image)\b", s):
            # 2026-10-01 (full text): a caption run into the next sentence, with no full stop between them ("Figure 1
            # US Grant Schematic Long Section ... (Red Dots) Drill Results The surface drill program comprised 14
            # holes for a total of 1,457 metres."): the sentence after the caption is read
            mc = re.search(r"(?<=[\w)\]] )(?=(?:The|This|A|An)\s+(?:[\w-]+\s+){0,3}?(?:drill(?:ing)?\s+)?(?:program(?:me)?|"
                           r"campaign)\s+(?:comprised|consisted|totall?ed|was|has|included|will)\b)", s[20:])
            if not mc:
                continue
            s = s[20 + mc.start():]
        if re.search(r"(?i)\bno\s+(?:additional\s+|further\s+|new\s+)?"
                     r"(?:drill|exploration)", s):
            continue
        if re.search(r"(?i)\b(?:included|reported|presented)\s+(?:in|with)\s+this\s+(?:news\s+)?release\b|\breported\s+here(?:in)?\b", s):
            continue
        if _DISCLAIM.search(s) and not (_metres(s) or _holes(s)):
            continue
        # 1.2.3: the drilling database behind a resource estimate or study, an agreement's work commitment, and a
        # program that depends on a condition ("If successful, the Company has the option to ...") are not programs
        # (2026-10-01, full text: not when the sentence also says the drilling goes on -- "MRE drilling program
        # continues: the 2022 MRE is based on drilling to the end of 2021, with ongoing drilling aimed at expanding")
        if (_DATABASE.search(s) and not _ONGOING.search(s)) or _COMMITMENT.search(s) or _CONDITIONAL.search(s):
            continue
        seen = set()
        for t, rx in (("drilling", _DRILL), ("geophysics", _GEO), ("ground", _GRD)):
            m = rx.search(s)
            while m and re.match(r"(?i)\s*(?:\w+\s+)?(?:anomal\w*|targets?|results?|data(?:\s*sets?)?|highs?|lows?|responses?|signatures?|"
                                 r"interpretation|models?|inversions?|features?|compilations?|re-?processing|modell?ing)\b",
                                 s[m.end():m.end() + 30]):
                m = rx.search(s, m.end())
            if not m or t in seen:
                continue
            seen.add(t)
            if _near_status(s, m.start(), m.end()) is None:
                m = _later_program_mention(s, rx, m) or m
            a0, a1 = max(0, m.start() - 110), min(len(s), m.end() + 110)
            w = s[a0:a1]
            hm = _HIST.search(s)
            hist = bool(hm) and abs(hm.start() - m.start()) < 90
            if hist and hm.group(0).lower().startswith("historic") and hm.start() > m.start() + 15 and \
                    re.search(r"(?i)\b(?:targeted|tested|followed\s+up|test|follow|twin\w*|confirm\w*|validat\w*|extend\w*)\b",
                              s[m.start():hm.start()]):
                hist = False
            if hist and re.search(r"(?i)\b(?:tested|targeted|test|follow\w*|twin\w*|confirm\w*|where|near)\b", s[max(0, hm.start() - 60):hm.start()]) \
                    and (_metres(s[:hm.start()]) or _holes(s[:hm.start()])):
                continue
            st = _near_status(s, m.start(), m.end())
            # 1.2: "The Company's first systematic, 73.5 line-kilometre IP survey identified a 75-125 metre wide
            # anomaly": a survey that has found something is a finished survey
            found = False
            fv = re.match(r"(?i)([^.;]{0,25}?)\b(?:has\s+|have\s+)?(?:identified|outlined|revealed|delineated|defined|highlighted|"
                          r"detected|generated|returned|confirmed)\b", s[m.end():m.end() + 60])
            # the survey has to be what found it: "a soil survey within the area outlined in Figure 1" found nothing
            if st is None and t != "drilling" and fv and not re.search(
                    r"(?i)\b(?:within|area|figure|fig|zone|which|that|where|map|plan)\b", fv.group(1)) \
                    and not s[m.end():m.end() + 1] == "-" \
                    and not re.search(r"(?i)\b(?:re-?model\w*|re-?interpret\w*|compil\w*|re-?process\w*|review\w*|"
                                      r"integrat\w*|historic\w*)\b", s[max(0, m.start() - 60):m.start()]) \
                    and not _RE_GOV.search(s[max(0, m.start() - 110):m.end() + 110]):
                # (a "geophysically-generated target" found nothing; nor did "re-interpreted and modelled the EM and
                # magnetic geophysics", work on someone's data; nor a government survey)
                st, found = "completed", True
                if now and any(int(y) < now - 1 for y in _YEAR.findall(s[max(0, m.start() - 110):m.end() + 110])):
                    st, found = None, False       # an older survey's findings are background, not this season's work
            # 1.2: "identified from the 2023 and 2025 rock sampling programs", "the 2024 drill program": a program
            # named by an earlier year is a finished one, one row per year named
            yearprog = []
            yearprog_owner = None
            yp_start = m.start()
            if st is None and now:
                my = re.search(r"\b((?:19|20)\d\d)(?:\s*(?:and|&|,)\s*((?:19|20)\d\d))?\s+(?:[\w-]+\s+){0,2}$",
                               s[max(0, m.start() - 40):m.start()])
                # (a year before one drill hole -- "the 1986 Noranda drill hole" -- names a hole, not a program; and
                # "their 2021 diamond drill campaign" is a neighbour's)
                if my and (re.match(r"(?i)[^.;]{0,30}?\b(?:program(?:me)?s?|campaigns?|surveys?|season)\b", s[m.start():m.end() + 30])
                           or (re.match(r"(?i)(?:[\w-]+\s+)?(?:drill\s*)?holes\b", s[m.start():m.start() + 30])
                               and re.search(r"\b\d+\s+(?:[\w-]+\s+)?$", s[max(0, m.start() - 20):m.start()]))) \
                        and not re.search(r"(?i)\btheir\b", s[max(0, m.start() - 60):m.start()]):
                    # this year's sampling with results in hand is done; this year's drilling may well not be
                    cur_ok = t != "drilling" and re.search(r"(?i)\b(?:results?|assays?|returned|collected|highlight\w*)\b", s)
                    yearprog = [y for y in my.groups() if y and (int(y) < now or (int(y) == now and cur_ok))]
                    yp_start = max(0, m.start() - 40) + my.start()
                    if yearprog:
                        st = "completed"
                        # "Cosa's 2024 VTEM survey" is another company's work; "Westward's 2021 field program" is not
                        ys = max(0, m.start() - 40) + my.start()
                        mo = re.search(r"\b([A-Z][\w&\-]*)['’]s\s*$", s[max(0, ys - 40):ys])
                        if mo:
                            ow = mo.group(1)
                            # the issuer's own name: its parsed name when that parse worked, else the headline and
                            # dateline ("Clarity Metals Selects ...", "Clarity Metals Corp. (CSE: CMET)")
                            ik = set(re.findall(r"[a-z]{3,}", (issuer or "").lower())) | \
                                set(re.findall(r"[a-z]{3,}", title.lower()))
                            xm = re.search(r"\((?:TSX|CSE|NEO|CBOE|NYSE|NASDAQ|OTC|ASX|AIM|FSE|Frankfurt)", b[:600])
                            dl = b[:xm.start()] if xm else b[:150]
                            if ow.lower() not in ik and not re.search(r"(?i)(?<![\w-])" + re.escape(ow) + r"(?![\w-])",
                                                                      title + " " + dl) and ow.lower() not in (
                                    "company", "corporation", "project", "property", "issuer", "partnership") \
                                    and not (primary and ow.lower() in _proj_key(primary)):
                                yearprog_owner = ow
            # 1.2.4 (capture): a drilling program named by an earlier year in other ways -- "the 2022 drilling at the
            # Dayton IP2 target", "Drilling during 2021 successfully intersected", "a maiden drill program in 2020",
            # "the last drilling campaign at Nisk (2023)" -- is that year's finished program
            if st is None and now and not yearprog and \
                    not re.search(r"(?i)\btable\s*\d|\btabulation\b|\bsummary\s+of\s+(?:all\s+)?(?:\w+\s+)?results\b", s):
                yy = _year_named_drilling(s, m, my if t == "drilling" else None)
                if yy and int(yy) < now and not _names_other_company(s, iw) and not re.search(r"(?i)\b(?:their|its\s+neighbou?r\w*)\b|['\u2019]s\s+(?:19|20)\d\d",
                                                           s[max(0, m.start() - 60):m.start()]):
                    yearprog, st = [yy], "completed"
                    if my and yy in my.groups():
                        yp_start = max(0, m.start() - 40) + my.start()
            oper = None
            if yearprog_owner and not hist:
                hist, oper = True, yearprog_owner
            yr0 = _near_year(s, m.start(), m.end())
            if not hist and st == "completed" and deal_hl and not (yr0 and now and int(yr0) >= now - 1):
                oo = _other_operator(s[a0:a1], issuer)
                if oo:
                    hist, oper = True, oo[0]
            if not hist and st == "completed" and yr0 and now and int(yr0) < now - 1 and acq_hl:
                hist = True
            if not hist and st == "completed" and yr0 and now and int(yr0) < now - 1:
                oo = _other_operator(s[a0:a1], issuer)
                if oo:
                    hist, oper = True, oo[0]
                elif int(yr0) < now - 15:
                    hist = True
            if not hist and st == "completed" and re.search(r"(?i)\bsince\s+(?:the\s+)?(?:19[0-8]\d|199[0-5])s?\b", w):
                hist = True
            if not hist and st == "completed" and _CUMULATIVE.search(w):
                continue
            # 1.1: a sentence that opens 'Since <an event two or more years back>, the Company has completed ...' is a
            # running total over several seasons, however far the event is from the drilling words (AEM.TO Hope Bay: 'Since Agnico Eagle's acquisition of the Hope
            # Bay project in February 2021, the Company has completed more than 1,239 diamond drill holes')
            if not hist and st == "completed" and now and _SINCE_EVENT.match(s) and any(
                    int(y) <= now - 2 for y in _YEAR.findall(s[:m.end() + 110])):
                continue
            if hist:
                years = sorted(set(y.group(1) for y in _YEAR.finditer(s)
                                   if a0 <= y.start() < a1 and (now is None or int(y.group(1)) < now - 1)
                                   and not re.search(r"(?i)(?:acquir\w*|since|option\w*|staked?)\s+(?:the\s+\w+\s+)?(?:in\s+)?(?:\w+\s+)?$",
                                                     s[max(0, y.start() - 45):y.start()])))
                has_fact = bool(years) or _metres(w) or _holes(w) or _OPERATOR.search(w)
                if not has_fact or (t != "drilling" and not years):
                    continue
                if re.search(r"(?i)\b(?:adjacent|neighbou?ring|nearby|along\s+strike\s+from|government|USGS|USBM|"
                             r"universit\w+|academic|geological\s+"
                             r"survey|GSC|OGS|provincial)\b", w):
                    continue
                season = years[0] if len(years) == 1 else None
                if other_news and not (_metres(w) or _holes(w) or _linekm(w)):
                    continue
                pj = _project_in(s, known, primary, iw, m.start())
                if pj == FOREIGN:
                    continue
                r = _row(t, pj, "completed", w,
                         historical=True, operator=oper or _hist_operator(w, issuer), season=season)
                r["season"] = season
                if r["metres"] is None and r["holes"] is None and season is None and r["operator"].startswith("previous"):
                    continue
                r["_src"] = s
                rows.append(r)
                continue
            # 2026-10-01 (full text): "The surface drill program comprised 14 holes for a total of 1,457 metres" is a
            # finished program, as in the headline's results path
            comprised = False
            if st is None and re.search(r"(?i)\b(?:program(?:me)?|campaign)\s+(?:comprised|consisted\s+of|totall?ed)\b",
                                        s[m.start():m.end() + 60]) and (_metres(w) or _holes(w)):
                st, comprised = "completed", True
            if st is None:
                continue
            if _ELSEWHERE.search(w):
                continue
            # 2026-10-01 (full text): in a royalty holder's release, the operator named as the sentence's subject
            # reports its own drilling ("Manganese X has reported 12 new drill holes ..."); an option partner's work
            # on the issuer's project still counts
            sm = re.match(r"^\W*([A-Z][\w&'\u2019\-]+)(?:\s+[A-Z][\w&'\u2019\-]*){0,3}\s+(?:has|have|had|is|was|were|reported|"
                          r"completed|drilled|announced|conducted|commenced)\b", s)
            if sm and "!" + _fold_words(sm.group(1)) in iw and royalty_rel:
                continue
            if re.search(r"(?i)\b(?:talks|discussions|negotiat\w*|contractors?\s+to\s+undertake)\b", w) and st != "completed":
                continue
            yr = _near_year(s, m.start(), m.end())
            fact = (yr or _PHASE.search(w) or (t == "drilling" and (_metres(w) or _holes(w))) or
                    (t == "geophysics" and _linekm(w)))
            # 2026-10-01 (full text): a season that names the program ("Winter drilling is now complete", "Fall And
            # Winter Drill Program Planned", "samples were collected over the summer") or a size in a plan's or a
            # budget's words ("has been budgeted for 5,000 metres") distinguishes it as well
            if not fact and (any(sp.start() <= m.end() and sp.end() >= m.start() for sp in _SEASON_PROG.finditer(s))
                             or (t != "drilling" and _SEASON_WHEN.search(w))
                             or (t == "drilling" and _PLAN_SIZE.search(w))
                             # (a permit or approval for a planned program: "is now authorized to commence an active
                             # program of surface exploration", as the guide's permit rule)
                             or (st == "planned" and _PERMIT_FACT.search(w))
                             # 1.2.4: a start timing -- a month, a half-year or quarter, "later in the season" -- is the
                             # guide's concrete fact for a program ahead ("scheduled to commence July 22nd", "planned for the
                             # second half of 2023", "a drill program planned in Q3 of this year")
                             or (st == "planned" and _TIMING.search(s[max(0, m.start() - 50):m.end() + 80]))):
                fact = True
            # 1.2: a finished survey the release names by kind ("the Company's recently completed drone magnetic and
            # hyperspectral surveys", "the 2-km soil sampling program was completed") is a program though no year or
            # size is given; the kind is the distinguishing fact. Nothing in the window may point back more than a year.
            # (1.2.4: whatever words tell that it is finished -- "a DCIP geophysical survey conducted earlier this year",
            # "Lunasonde has completed its airborne survey", "A soil geochemical survey has been carried out over" --
            # not only "recently completed")
            if not fact and t != "drilling" and st == "completed" and _survey(w, t) not in (None, "mixed") \
                    and not _YEAR.search(w) and not re.search(r"(?i)\b(?:previous(?:ly)?|prior|historic\w*|former)\b", w) \
                    and not _RE_GOV.search(w):
                fact = True
            # 1.2.3: a program the release says is going on now ("Drilling is ongoing", "the drilling program currently
            # underway at Eclipse", "our current drill program") is a row though it gives no size or year
            factless = False
            if not fact and st in ("underway", "started") and _ONGOING.search(w) and not _YEAR_BEFORE(w, now) \
                    and not _TENTATIVE.search(w) and not _WILL.search(s[max(0, m.start() - 40):m.start()]):
                fact = factless = True
            weak = False
            if not fact:
                if not _weak_mention(t, st, w, s, hist, now, iw):
                    continue
                weak = True
            if st != "completed" and yr and now and int(yr[-4:]) < now - 1:
                continue
            if other_news and not (yr and (_PHASE.search(w) or (t == "drilling" and (_metres(w) or _holes(w))) or
                                           (t == "geophysics" and _linekm(w)))):
                continue
            if st == "planned" and not re.search(r"(?i)\b(?:program(?:me)?|campaign|survey|drill(?:ing)?)\b", w):
                continue
            text = w
            if t == "drilling" and not factless and not (_metres(w) or _holes(w)) and i + 1 < len(sents) \
                    and not _types(sents[i + 1])[1:]:
                text = w + " " + sents[i + 1][:200]
            pj = _project_in(s, known, primary, iw, m.start())
            if pj is None and not primary:
                pj = _heading_property(sents, i, iw)    # 2026-10-01: a portfolio update's property heading
            if pj == FOREIGN:
                continue                            # 1.2.3: another company's property
            if pj and primary and _proj_key(pj) != _proj_key(primary) and _other_company_named(s, iw):
                continue                            # 1.2.3: another company's program on its own property
            if test_hl and t == "ground":
                continue                            # 1.2.3: a testwork release's field program is the tests
            r = _row(t, pj, st, text)
            r["season"] = _near_season(s, m.start(), m.end()) or yr
            if yearprog:
                # the year that names the program is its season ("the 2025 summer field program, as well as the 2024
                # drill program": the drilling is 2024's)
                if not (r["season"] and yearprog[0] in str(r["season"])):
                    r["season"] = yearprog[0]
            if not r["season"] and st == "completed":
                mc = re.search(r"(?i)\bcomplet\w*\s+in\s+(?:early\s+|late\s+|mid-?\s*)?((?:19|20)\d\d)\b", w)
                if mc:
                    r["season"] = mc.group(1)
            if not r["season"] and now and _THIS_YEAR.search(w):
                r["season"] = str(now)
            if t == "drilling" and (r["metres"] or r["holes"]) and _part_of_property(s, r["project"]):
                r["metres"] = r["holes"] = None
            tgt = _target_of_complex(title, r["project"], s, b) if t == "drilling" else None
            if tgt:
                r["project"] = tgt
            if t != "drilling" and st == "planned" and not (r["season"] or r["phase"]) and \
                    not _TIMING.search(s[max(0, m.start() - 50):m.end() + 80]):
                continue
            # (2026-10-01, full text: results the release reports from drilling going on now -- "results from the
            # continuing diamond drilling of the Kora North Extension" -- are a program underway)
            if not _strong(w) and not found and not yearprog and not comprised and \
                    not (factless and (_RESULTS_OF_CURRENT.search(w) or _ONGOING_SUBJECT.match(s))):
                if not _weak_mention(t, st, w, s, hist, now, iw):
                    continue
                weak = True
            r["_src"] = s
            if weak:
                weak_rows.append(r)                 # 1.2.4: kept only if no row of its kind is on its property
                continue
            r["_factless"] = factless
            if yearprog:
                r["_yearprog"] = True
                # the sizes in the window may belong to this season's work ("Hole ES-337 ... discovered in the 2021
                # drill program and will total a minimum of 600 metres"); only the program's own clause counts
                # (1.2.4: from the year that names it, so a count between the two is the program's -- "2023 14 HQ drill
                # holes" in a table of seasons)
                own = s[min(yp_start, m.start()):m.end() + 70]
                own = re.split(r"(?i)\b(?:will|planned|designed|expected|proposed)\b|[;.]", own)[0]
                r["metres"], r["holes"] = _metres(own), _holes(own)
            rows.append(r)
            if len(yearprog) == 2:
                r2 = dict(r)
                r2["season"] = [y for y in yearprog if y != r["season"]][0] if r["season"] in yearprog else yearprog[1]
                rows.append(r2)

    # 3. one row per program
    out = []
    for r in rows:
        if not r["project"]:
            r["project"] = primary
        if not r["project"]:
            continue
        for o in out:
            if _one_program(o, r):
                # 1.2.3: one program of several kinds of work
                if "drilling" in (o["program_type"], r["program_type"]) or "ground" in (o["program_type"], r["program_type"]):
                    kind = "drilling" if "drilling" in (o["program_type"], r["program_type"]) else "ground"
                    if o["program_type"] != kind:
                        keep = dict(r)
                        _merge(keep, o)
                        o.clear()
                        o.update(keep)
                    else:
                        _merge(o, r)
                    o["survey_type"] = _survey(o.get("_src") or "", kind) if kind == "ground" else None
                    break
            if _same_program(o, r, rel_year):
                # 1.2.3: "Drilling Underway" in the headline and the body's figures to date: a program underway
                if {o["status"], r["status"]} == {"started", "underway"} and not o["historical"] and \
                        not (r.get("_factless") and o["status"] == "started"):
                    o["status"] = "underway"
                # 1.2.3: a current program's size is its total, not the metres drilled so far ("has drilled 2,551 m in
                # the first fourteen holes" and "the drilling of a planned 14,000-metre drilling campaign")
                if o["status"] in ("started", "underway") and r["status"] in ("planned", "started", "underway") \
                        and o.get("metres") and r.get("metres") and r["metres"] > o["metres"]:
                    o["metres"], o["holes"] = r["metres"], r.get("holes") or o.get("holes")
                # 1.2.3: a sentence that only says the program is going on gives way to the one with its figures
                if o.get("_factless") and not r.get("_factless"):
                    for k in ("metres", "holes", "line_km", "phase", "season"):
                        if r.get(k) not in (None, ""):
                            o[k] = r[k]
                    o["_factless"] = False
                _merge(o, r)
                break
        else:
            out.append(r)
    # 1.2.3: a general field program is the drilling program of the same season
    for g in [r for r in out if r["program_type"] == "ground"]:
        d = next((x for x in out if _field_program_of(g, x)), None)
        if d is not None:
            _merge(d, g)
            out.remove(g)
    # 1.2.3: one program read twice (same size)
    ded = []
    for r in out:
        for o in ded:
            if _same_size(o, r):
                if primary and _proj_key(r["project"]) == _proj_key(primary) and _proj_key(o["project"]) != _proj_key(primary):
                    o["project"] = r["project"]
                if {o["status"], r["status"]} == {"underway", "completed"}:
                    o["status"] = "underway"
                _merge(o, r)
                break
        else:
            ded.append(r)
    out = ded
    # 1.2.3: several planned phases of one program are one row, the first phase's ("Phase 1 drill program of 1,050 m
    # ... the Company has planned a Phase 2 drill program of 1,450 m")
    keep = []
    for r in out:
        if r["status"] == "planned" and not r["historical"] and r.get("phase") and any(
                o["status"] == "planned" and not o["historical"] and o.get("phase") and o["phase"] != r["phase"]
                and o["program_type"] == r["program_type"] and _proj_key(o["project"]) == _proj_key(r["project"])
                for o in keep):
            continue
        keep.append(r)
    out = keep
    # 1.2.4 (capture): a finished program of a kind the release reports nothing else of, on that property, stated
    # without a year or size ("the gravity survey conducted at Storm this spring by our partners", "Soil samples were
    # collected from holes dug 10 to 30 cm deep"): one row per kind and property
    # (and a program the release says has started, without a size or date: "field crews have mobilized to its Golden
    # Frac Sand Property", "drilling has recently begun" at the other property)
    res_row = _results_drilling(title, sents, primary, royalty_rel or _OPTIONED_OUT.search(b[:1500]), now) \
        if primary and not any(r["program_type"] == "drilling" for r in out) else None
    for r in weak_rows:
        if not r["project"]:
            r["project"] = primary
        if res_row and r["program_type"] == "drilling":
            continue                                # (the results release's own drilling row, below, is that program)
        if r["project"] and not any(o["program_type"] == r["program_type"] and _proj_key(o["project"]) == _proj_key(r["project"])
                                    for o in out):
            if r["status"] == "started":
                src = r.get("_src") or ""
                # a start told as the whole finished story ("The program commenced with ... and ended with ...", "was
                # started on July 20, but was halted"), or one still ahead ("when the drill rig mobilizes in mid-June",
                # "as contractors are secured and field work commences")
                if re.search(r"(?i)\b(?:ended|completed|concluded|finished|halted|suspended)\b", src):
                    r["status"] = "completed"
                elif re.search(r"(?i)\b(?:will|when|once|as\s+soon\s+as|after|as)\b[^.;]{0,60}?\b(?:mobili[sz]es|commences|"
                               r"begins|starts|launches)\b", src):
                    r["status"] = "planned"
                    r["season"] = None
            # (field work starting or ahead beside a drill program at the same stage is that program: the guide's
            # combined program is one drilling row)
            if r["program_type"] != "drilling" and r["status"] != "completed" and any(
                    o["program_type"] == "drilling" and o["status"] == r["status"] and
                    _proj_key(o["project"]) == _proj_key(r["project"]) for o in out):
                continue
            out.append(r)
    # 1.2.3: a property the headline says is sold or given up has no program ahead of it
    sold = {_proj_key(n) for p0, n in _projects(title, iw) if re.search(
        r"(?i)\b(?:sale\s+of|sells?|sold|to\s+sell|dispos\w+\s+of|divest\w*|relinquish\w*|terminat\w+)\s+(?:the\s+|its\s+)?"
        r"(?:[\w%-]+\s+){0,3}$", title[:p0])}
    out = [r for r in out if not (r["status"] != "completed" and not r["historical"] and _proj_key(r["project"]) in sold)]
    # 1.2.3: a property named by its initials ("El Dorado Monserrat Project ("EDM")") gets its name
    for m in re.finditer(r"([A-Z][\w'’À-ÿ\-]+(?:\s+[A-Z][\w'’À-ÿ\-]+){0,4})\s+(?:(?:[Pp]roject|[Pp]roperty)\s*)?\(\s*(?:the\s+)?"
                         r"[\"“”']\s*([A-Z]{2,6})\s*[\"“”']", b):
        full = _clean_proj(m.group(1), iw)
        if full:
            for r in out:
                if r["project"] == m.group(2):
                    r["project"] = full
    # (key gate: the patents or claims inside the project are the project)
    if part_of:
        for r in out:
            if r["project"] and _proj_key(r["project"]) in _part_keys(title):
                r["project"] = part_of
    # 1.2.3: a marketing or corporate-housekeeping release reports a program only with its size
    # (2026-10-01, full text: not when the headline also reports field news -- "Now Trading on OTCQX ... New uranium
    # discovery in Athabasca Basin advancing")
    if _MARKETING_HL.search(title) and not ptype and not re.search(r"(?i)\b(?:exploration|drill\w*|program|update|"
                                                                   r"progress|field|discover\w*|assays?)\b", title):
        out = [r for r in out if r.get("metres") or r.get("holes") or r.get("line_km")]
    # 1.2.3: a program started or underway at the release's date is that year's
    for r in out:
        if not r["historical"] and r["status"] in ("started", "underway") and not r.get("season") and rel_year \
                and not _YEAR_BEFORE(r.get("_src") or "", rel_year):
            r["season"] = str(rel_year)
    _program_sizes(out, sents, now)
    _progress_size(out, sents, now)
    _program_budget(out, sents, now)
    # 1.2.4: a drill-results release is news about the drilling that produced the results: when no drilling row
    # came out, the release's own drilling program is one row, going on now if the release says so
    if res_row and not any(r["program_type"] == "drilling" for r in out):
        out.append(res_row)
    metals = _metal(title + " " + b[:2500])
    for r in out:
        if metals and not r["historical"]:
            r["target_metal"] = "+".join(metals[:2])
    if not out and reason is None:
        reason = "no program with a status and a fact"
    return {"rows": out, "reason": reason, "project": primary}


# 1.2.4: a headline that reports drill intercepts ("Intersects 0.54% Cu Eq over 180.8m", "Drills 3.05 Metres of 73.60
# g/t Gold", "Discovery hole at Rivard confirms ...") -- not a resource, study, re-assay or historical-data release
_DRILL_RESULTS_HL = re.compile(r"(?i)\b(?:drill\w*|intersect\w*|intercept\w*|holes?|cuts|hits)\b|(?<![\w.])\d+(?:\.\d+)?\s*"
                               r"(?:m|metres?|meters?)\s+(?:of|at|grading)\b|\bover\s+\d+(?:\.\d+)?\s*(?:m|metres?|meters?)\b")
_RESULTS_SHAPE_HL = re.compile(r"(?i)(?<![\w.])\d+(?:\.\d+)?\s*(?:m|metres?|meters?)\s+(?:of\s+(?:\w+\s+){0,4}?(?:sulphides?|sulfides?|"
                               r"mineralization|mineralisation|pegmatite|spodumene)|(?:copper|nickel|gold|zinc|lithium)\s+(?:\w+\s+)?"
                               r"(?:core\s+)?interval)\b|\bdrills\s+(?:[\w()-]+\s+){1,4}?(?:on|at)\s+(?:its|the)\b")
_NOT_NEW_DRILLING_HL = re.compile(r"(?i)\b(?:historic\w*\s+(?:drill\w*|data|results?|core|assays?|holes?)|re-?assay\w*|"
                                  r"re-?sampl\w*|re-?logg\w*|core\s+assay|(?:mineral\s+)?resource\s+(?:estimate|update|statement)|"
                                  r"MRE|reserves?|PEA|feasibility|preliminary\s+economic|metallurg\w*|quarter\w*|annual|"
                                  r"year[\s-]+end|financial|royalt\w*|stream)\b")
# the release says the drilling goes on ("Drilling ... is advancing with two drill rigs in operation", "drilling
# scheduled to continue until the end of 2025", "Our focus now is to continue drilling", "The Company's drill program
# has been paused for ... spring break-up", "regional test drill holes are being conducted currently")
_DRILL_GOES_ON = re.compile(
    r"(?i)\b(?:drill(?:ing)?|drill\s+program(?:me)?|campaign|rigs?)\b[^.;]{0,60}?\b(?:continu\w*|ongoing|underway|under\s+way|"
    r"in\s+operation|in\s+progress|advancing|paused|resum\w*|turning|being\s+conducted\s+currently|currently\s+being)\b|"
    r"\b(?:continu\w*|ongoing|current|currently)\s+(?:to\s+)?(?:[\w-]+\s+){0,2}?(?:drill(?:ing)?|campaign|program(?:me)?)\b|"
    r"\b(?:remaining|next|last)\s+(?:[\w-]+\s+){0,2}?(?:drill\s*)?holes?\s+(?:will|are\s+(?:planned|being))\b|"
    # ("Lion One is concurrently undertaking a two-pronged exploration drill campaign", "hole TUG-141 is still being
    # drilled", "this first hole of the fall drilling program", "these initial few holes of our fall campaign")
    r"\b(?:is|are)\s+(?:currently\s+|concurrently\s+|now\s+)?(?:undertaking|conducting|carrying\s+out|running)\s+(?:[\w-]+\s+){0,4}?"
    r"(?:drill\w*|campaign|program(?:me)?)\b|\b(?:still|currently)\s+being\s+drilled\b|"
    r"\b(?:first|initial)\s+(?:few\s+|two\s+|three\s+)?holes?\s+of\s+(?:the|our|its|this)\s+(?:[\w-]+\s+){0,3}?(?:program(?:me)?|campaign)\b")


def _results_drilling(title, sents, primary, royalty_rel, now):
    """1.2.4 (capture): the drilling program of a drill-results release that gave no drilling row: one row on the
    release's property, underway when a sentence of the release says the drilling goes on, otherwise completed. No
    size (results releases give batch sizes, not the program's). Not in a royalty holder's release (the operator's
    drilling), not for historical data, re-assays, resource or study news."""
    if not (_RESULTS_HL.search(title) and _DRILL_RESULTS_HL.search(title) or _RESULTS_SHAPE_HL.search(title)) \
            or _NOT_NEW_DRILLING_HL.search(title) or royalty_rel or \
            (_GRD.search(title) or re.search(r"(?i)\bsampl\w*|\bchannels?\b|\btrench\w*", title)) and not _DRILL.search(title):
        return None
    goes_on = False
    for s in sents:
        if _HIST.search(s) or _ELSEWHERE.search(s) or _DISCLAIM.search(s) or _YEAR_BEFORE(s, now) or \
                re.search(r"(?i)\bforward[\s-]+looking|\bQA/?QC\b|quality\s+(?:assurance|control)", s):
            continue
        if _DRILL_GOES_ON.search(s):
            goes_on = True
            break
    r = _row("drilling", primary, "underway" if goes_on else "completed", "")
    r["season"] = str(now) if goes_on and now else None
    r["_src"] = title
    return r

_MONTHS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_TIMING = re.compile(r"(?i)\b(?:in|by|during|from|until|starting|beginning|on|for)\s+(?:early\s+|mid-?\s*|late\s+)?(?-i:" + _MONTHS + r")\b|"
                     r"\bmid-(?-i:" + _MONTHS + r")\b|(?<![\w,])(?-i:" + _MONTHS + r")\s+\d{1,2}(?:st|nd|rd|th)?\b(?!\s*,?\s*(?:19|20)\d\d)|"
                     r"\b(?:first|second|1st|2nd|latter|later)\s+half\s+of\s+(?:the\s+year|this\s+year|(?:19|20)\d\d)\b|"
                     r"\bH[12]\s*(?:of\s+)?(?:19|20)\d\d\b|\bQ[1-4]\b|\b(?:first|second|third|fourth)\s+quarter\b|"
                     r"\b(?:later|early)\s+(?:in\s+)?(?:the|this)\s+(?:season|year)\b|"
                     r"\b(?:this|next|coming|upcoming)\s+(?:winter|spring|summer|fall|autumn|field\s+season|season)\b|"
                     r"\b(?:early|late|mid-?)\s*(?:winter|spring|summer|fall|autumn)\b|"
                     r"\b(?:shortly|imminently|in\s+the\s+(?:coming|next)\s+(?:few\s+)?(?:days|weeks|months))\b")
# 1.2.4: sampling, assaying and QA/QC procedure sentences say how samples were handled, not that a program ran
_PROCEDURE = re.compile(r"(?i)\b(?:laborator\w*|QA/?QC|quality\s+(?:control|assurance)|assay(?:ed|ing)?\s+(?:by|at|for)|certified|"
                        r"ISO\s*\d|sample\s+prep\w*|pulveri[sz]\w*|crushed|standards|blanks|duplicates|chain\s+of\s+custody|"
                        r"qualified\s+person|NI\s*43-101|forward[\s-]+looking|cautionary|not\s+necessarily\s+indicative)\b")


def _weak_mention(t, st, w, s, hist, now, iw):
    """1.2.4 (capture): a finished program of this kind named without a distinguishing fact -- a row candidate only,
    kept when the release gives no other row of this kind on the property. Not a previous owner's (they need a fact),
    not a procedure or disclaimer sentence, not a government or regional survey, not older work."""
    return (t in ("geophysics", "ground") and st == "completed" or st == "started") and not hist and not _PROCEDURE.search(s) and not _RE_GOV.search(w) \
        and not re.search(r"(?i)\b(?:previous(?:ly)?|prior|past|historic\w*|former|regional\s+(?:government|data))\b", w) \
        and not _DATA_WORK.search(w) and not _YEAR_BEFORE(s, (now or 0) - 1) and not _MINE_DRILL.search(s) \
        and not _names_other_company(s, iw) \
        and not re.search(r"(?i)\bno\s+(?:[\w-]+\s+){0,2}?(?:field\s*work|work|exploration|sampling|surveys?|programs?)\b", s)


# 1.2.4: work on survey data rather than a survey (interpretation, models, inversions, re-processing, compilations), or a
# kind of work named in general ("drone Lidar has been used ... throughout Newfoundland"), or work still going on
_DATA_WORK = re.compile(r"(?i)\b(?:data(?:\s*sets?)?|models?|modell?ing|inversions?|interpret\w*|re-?interpret\w*|re-?process\w*|"
                        r"compil\w*|review\w*|re-?analy\w*|used|utili[sz]\w*|being\s+(?:conducted|carried\s+out|completed)|"
                        r"throughout|trends?\s+defined)\b")
_NOT_PROG_AFTER = re.compile(r"(?i)\s*(?:\w+\s+)?(?:anomal\w*|targets?|results?|data(?:\s*sets?)?|highs?|lows?|responses?|"
                             r"signatures?|interpretation|models?|inversions?|features?|compilations?|re-?processing|"
                             r"modell?ing)\b")


def _later_program_mention(s, rx, m):
    """1.2.4 (capture): the sentence's first mention of a kind of work says nothing of its state ("intersected by drill
    hole ST22-10 in the 2022 drill campaign"); a later mention of the same kind that does (a status near it, or a
    year naming the program) is the program the sentence reports."""
    k = m
    for _ in range(4):
        k = rx.search(s, k.end())
        if not k:
            return None
        if _NOT_PROG_AFTER.match(s[k.end():k.end() + 30]):
            continue
        if _near_status(s, k.start(), k.end()) is not None or \
                re.search(r"\b(?:19|20)\d\d\s+(?:[\w-]+\s+){0,2}$", s[max(0, k.start() - 40):k.start()]):
            return k
    return None


# 1.2.4: the issuer has optioned the property out: the drilling it reports is the optionee's ("CAVU holds the Hopper
# project under option and can acquire a 70% interest")
_OPTIONED_OUT = re.compile(r"(?i)\b(?:holds?|has)\s+(?:the\s+)?(?:[\w-]+\s+){0,3}?(?:project|property|claims)\s+under\s+option\b|"
                           r"\bthe\s+optionee\b")


def _names_other_company(s, iw):
    """1.2.4: the sentence names a company the release names with a corporate suffix that is not the issuer ("The
    Escape Deposit underwent 37,000m of expansion drilling in 2021, which Clean Air expects ...")."""
    f = _fold_words(s)
    return any(w.startswith("!") and re.search(r"(?<![a-z0-9])" + re.escape(w[1:]) + r"(?![a-z0-9])", f) for w in iw or ())


def _year_named_drilling(s, m, my):
    """1.2.4: the year that names a drilling mention: a year just before "drilling" or "drill program/campaign" (not
    before a drill hole), or "in/during <year>" or "(<year>)" just after it."""
    # (not with a company's name between the year and the drilling: "from 2010 Auramex Resources drilling" is a
    # previous owner's)
    if my and re.match(r"(?i)(?:[\w-]+\s+){0,2}?drill(?:ing)?\b(?!\s*(?:holes?|core|results?|intercepts?|assays?|data))",
                       s[m.start():m.end() + 20]) and not re.search(
                r"\b(?:19|20)\d\d\s+(?:(?!(?:Phase|Winter|Summer|Spring|Fall|Autumn|RC|Diamond|Core|Exploration|Drill\w*)\b)"
                r"[A-Z][\w&-]+\s+)+$", s[max(0, m.start() - 40):m.start()]):
        return my.group(2) or my.group(1)
    ma = re.match(r"(?i)[^.;]{0,30}?\b(?:in|during)\s+(?:early\s+|late\s+|mid-?\s*)?(?:" + _MONTHS + r"\s+)?((?:19|20)\d\d)\b(?!\s*(?:-|to|and)\s*\d)",
                  s[m.end():m.end() + 50]) or \
        re.match(r"(?i)\s*(?:(?:at|on)\s+(?:the\s+)?[\w'\u2019-]+(?:\s+[\w'\u2019-]+)?\s+)?\(((?:19|20)\d\d)\)", s[m.end():m.end() + 40])
    # (not "prior" or "historical" drilling: an earlier owner's, which needs its own facts)
    if ma and not re.search(r"(?i)\b(?:will|planned|plans?|expected|scheduled|proposed|upcoming)\b", s[m.start():m.end() + ma.end()]) \
            and not re.search(r"(?i)\b(?:prior|previous(?:ly)?|historic\w*|former|earlier)\s+(?:[\w-]+\s+){0,2}$", s[max(0, m.start() - 40):m.start()]) \
            and not re.search(r"(?i)\bsince\s+(?:the\s+)?(?:[\w-]+\s+){0,3}$", s[max(0, m.start() - 40):m.start()]):
        return ma.group(1)
    return None

_SEASON_PROG = re.compile(r"(?i)\b(?:winter|spring|summer|fall|autumn)\s+(?:and\s+(?:winter|spring|summer|fall|autumn)\s+)?"
                          r"(?:[\w-]+\s+){0,2}?(?:drill\w*|program(?:me)?|campaign|field\s*work|exploration|sampling|survey)")
_PERMIT_FACT = re.compile(r"(?i)\b(?:authori[sz]ed|permitted|approved)\s+to\s+(?:commence|begin|start|conduct|carry\s+out|"
                          r"undertake|drill)\b|\b(?:permits?|approvals?)\s+(?:has\s+been\s+|have\s+been\s+|was\s+|were\s+)?"
                          r"(?:received|granted|issued)\b|\breceived\s+(?:the\s+|a\s+|all\s+)?(?:\w+\s+){0,2}?(?:permits?|approvals?)\b")
_SEASON_WHEN = re.compile(r"(?i)\b(?:over|during|in)\s+the\s+(?:winter|spring|summer|fall|autumn)\b")
_PLAN_SIZE = re.compile(r"(?i)\b(?:budgeted\s+for|plans?\s+to\s+(?:complete|drill)|to\s+complete)\s+(?:approximately\s+|about\s+|"
                        r"up\s+to\s+|over\s+)?[\d,.]{3,}\s*(?:m|metres?|meters?)\b")
_SIZE_PROG = re.compile(r"(?i)\b(?:program(?:me)?|campaign|planned|drilling\s+of|totall?ing|total\s+of|comprise|consist)\w*\b")


def _program_sizes(out, sents, now):
    """1.2.1: the size of a drill program, from the release's own sentence about it, when the row's clause did not
    carry one. Val-d'Or Mining's row comes from its headline and 'the commencement of a planned 5,000 metre diamond
    drilling program' is two sentences down; Moneta's 'a new drilling program of approximately 1,500 meters' is
    the lead. Only when the release has exactly one current drill program without a size, and every sentence that
    sizes a program at that status agrees on the figure -- 'more than 4,700 m of the planned 7,000 m program'
    (ECU.V) sizes the planned program at 7,000 and says nothing definite about the rest."""
    need = [r for r in out if r["program_type"] == "drilling" and not r["historical"] and r["metres"] is None]
    cur = [r for r in out if r["program_type"] == "drilling" and not r["historical"]]
    if len(need) != 1 or len(cur) != 1:
        return
    r = need[0]
    want = ("planned", "started", "underway") if r["status"] in ("planned", "started", "underway") else ("completed",)
    found = set()
    for s in sents:
        if not _DRILL.search(s) or not _SIZE_PROG.search(s) or _HIST.search(s) or _ELSEWHERE.search(s) \
                or _CUMULATIVE.search(s) or _DISCLAIM.search(s):
            continue
        # a sentence about an older season is not this program
        if now and any(int(y) < now - 1 for y in _YEAR.findall(s)):
            continue
        st = _status(s)
        if st is None and re.search(r"(?i)\bplanned\b", s):
            st = "planned"
        if st not in want:
            continue
        # the program's size, not a hole's depth ("the initial hole being abandoned at 393 metres")
        v = _metres(s, st) or _metres_more(s)
        if v is None or v < 200:
            continue
        # 'X m of the planned Y m program': the planned size is the program's
        if want[0] == "planned":
            pm = re.search(r"(?i)\bplanned\s+" + _NUM + r"\s*(?:-\s*)?(?:metres?|meters?|m)\b", s)
            if pm:
                v = _num(next(x for x in pm.groups() if x)) or v
        found.add(v)
    if len(found) == 1:
        r["metres"] = found.pop()
        r["_size_from"] = "release"


_OF_PLANNED = re.compile(r"(?i)(?<![\w.])" + _NUM + r"\s*(?:-\s*)?(?:m|metres?|meters?)\b[^.;]{0,60}?\b(?:of|out\s+of|as\s+part\s+of)\s+"
                         r"(?:the|a|its|our)\s+(?:(?:planned|proposed|budgeted|expanded|total|current|ongoing)\s+)*"
                         # (key gate: "of the planned campaign of up to 5,000 metres")
                         r"(?:(?:drill(?:ing)?\s+)?(?:program(?:me)?|campaign)\s+of\s+)?"
                         r"(?:approximately\s+|about\s+|up\s+to\s+|~\s*)?" + _NUM + r"\s*\+?\s*(?:-\s*)?(?:m|metres?|meters?)\b")


def _progress_size(out, sents, now):
    """1.2.3: a program underway is sized by its planned total, as the release's progress sentence gives it ("To date,
    3,721 metres of RC drilling have been completed out of the planned 5,728 metres"), not by the figure its first
    mention carries. Only when the release has one current drill program and one such total."""
    cur = [r for r in out if r["program_type"] == "drilling" and not r["historical"] and r["status"] != "completed"]
    if len(cur) != 1 or cur[0]["status"] not in ("underway", "started"):
        return
    found = set()
    for s in sents:
        if now and any(int(y) < now - 1 for y in _YEAR.findall(s)):
            continue
        for m in _OF_PLANNED.finditer(s):
            g = [x for x in m.groups() if x]
            a, b = _num(g[0]), _num(g[-1])
            if a and b and b > a >= 1:
                found.add(b)
    if len(found) == 1:
        cur[0]["metres"] = found.pop()


def _program_budget(out, sents, now):
    """1.2.1: a budget the release states for its current program, put on the headline's program row (the first
    current row). Only when exactly one figure is stated as a budget and nothing in its sentence makes it the
    company's money rather than the program's ("a treasury of over $9 million", a flow-through financing)."""
    cur = [r for r in out if not r["historical"]]
    if not cur or any(r["budget"] for r in cur):
        return
    found = set()
    for s in sents:
        if not re.search(r"(?i)\b(?:budget\w*|program(?:me)?s?|campaign)\b", s) or _NOT_BUDGET.search(s) \
                or _HIST.search(s) or _ELSEWHERE.search(s):
            continue
        if now and any(int(y) < now - 1 for y in _YEAR.findall(s)):
            continue
        v, c = _budget(s)
        if v is not None:
            found.add((v, c))
    if len(found) == 1:
        cur[0]["budget"], cur[0]["currency"] = found.pop()


def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["rows"]:
        return [F.Record(KIND, facts=[F.Fact("is_program", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"] or "none")], confidence=0.0)]
    out = []
    for r in a["rows"]:
        fs = [F.Fact("is_program", value_num=1.0)]
        for k in TXT_FIELDS:
            if r.get(k):
                fs.append(F.Fact(k, value_text=str(r[k])[:160]))
        for k in NUM_FIELDS:
            if r.get(k) is not None:
                fs.append(F.Fact(k, value_num=float(r[k])))
        out.append(F.Record(KIND, facts=fs, confidence=1.0))
    return out


def parse_records(rows_by_ordinal):
    """{ordinal: [(field, seq, value_num, value_text)]} -> the analyse()-shaped dict."""
    rows = []
    for ordinal in sorted(rows_by_ordinal):
        r = {k: None for k in TXT_FIELDS + NUM_FIELDS}
        yes = False
        for field_, seq, num, text in rows_by_ordinal[ordinal]:
            if field_ == "is_program":
                yes = num == 1.0
            elif field_ in NUM_FIELDS:
                r[field_] = num
            elif field_ in TXT_FIELDS:
                r[field_] = text
        if yes and r["program_type"]:
            r["historical"] = bool(r["historical"])
            for k in ("holes", "rigs"):
                if r[k] is not None:
                    r[k] = int(r[k])
            rows.append(r)
    return {"is_program": bool(rows), "rows": rows}


JUDGED = TXT_FIELDS + NUM_FIELDS


def to_prediction(records):
    if not records:
        return None
    rows = {i: [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts] for i, rec in enumerate(records)}
    p = parse_records(rows)
    if not p["rows"]:
        return None
    return {"rows": [{k: r.get(k) for k in JUDGED} for r in p["rows"]]}


def _code_sha():
    # 1.2.2: portal/fingerprint.py -- this file plus exactly the helper code it runs, so a helper change bumps it
    return FP.code_sha(__file__)


SPEC = F.ExtractorSpec(NAME, VERSION, KIND, TAG, extract, _code_sha())


# ------------------------------------------------------------------ self-test
def self_test(verbose=False):
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))
        elif verbose:
            print("  ok   %s" % name)

    def rows(h, b):
        return analyse(h, b)["rows"]

    r = rows("Total Metals Completes 25 Hole, 8,408 metre Exploration Drilling Program on its Electrolode Critical "
             "Minerals Project",
             "Total Metals Corp. is pleased to announce it has completed the 25 hole, 8,408 metre drill program on the "
             "Company's 100% owned Electrolode Critical Minerals Project in Ontario. Two rigs were used this winter. "
             + "Filler text about the geology of the area and the targets tested. " * 5)
    eq("TT completed row", [(x["program_type"], x["status"], x["metres"], x["holes"]) for x in r][:1],
       [("drilling", "completed", 8408.0, 25)])
    eq("TT project", r[0]["project"] if r else None, "Electrolode")

    r = rows("Appia Begins Diamond Drilling to Delineate Potential Highgrade Mineralization at PCH Target IV",
             "Appia Rare Earths & Uranium Corp. announces the start of diamond drilling at the PCH Project. The program "
             "will include up to 450 meters of drilling in three 150 metres drillholes. " + "Geology filler. " * 20)
    eq("API started", [(x["program_type"], x["status"], x["metres"], x["holes"]) for x in r][:1],
       [("drilling", "started", 450.0, 3)])

    r = rows("Company Reports Drill Results", "Historical drilling by Noranda Mines Ltd. in 1988 comprised 12 holes "
             "totalling 2,400 m on the Alpha Property. " + "Filler text. " * 20)
    eq("historical row", [(x["program_type"], x["historical"], x["season"], x["holes"], x["metres"]) for x in r],
       [("drilling", 1.0, "1988", 12, 2400.0)])

    r = rows("Company Closes Private Placement", "The Company closed a private placement. " * 20)
    eq("financing, no rows", r, [])

    r = rows("Company Reports Results", "The option agreement requires exploration expenditures of $1,000,000 including "
             "a drilling program by 2027. " + "Filler. " * 20)
    eq("work commitment, no rows", r, [])

    # 1.1 (Justin, 2026-09-22): a running total is not a program; 'this year' is the release's year; part of a
    # property is not the property's program; part-way through planned metres is underway
    r = rows("Agnico Eagle Approves Hope Bay Investment Decision",
             "TORONTO, May 19, 2026 -- Agnico Eagle Mines Limited announced today its decision to build Hope Bay. "
             "Between August 2025 and the end of April 2026, the Company completed more than 130 diamond drill holes at "
             "Madrid and across the broader project area, totalling more than 100,000 metres of drilling. Since Agnico "
             "Eagle's acquisition of the Hope Bay project in February 2021, the Company has completed more than 1,239 "
             "diamond drill holes totalling 522,634 metres. " + "Filler about the mine plan. " * 12)
    eq("AEM running total is not a row", sorted(x["holes"] for x in r if x["holes"]), [130])
    eq("TXG part of the property", _part_of_property(
        "More broadly across the Morelos Property, approximately 15,000 m of drilling is planned for this year at El "
        "Naranjo and Atzcala, focused on confirming the continuity of mineralization.", "Morelos"), True)
    r = rows("Torex Gold Reports Excellent Drilling Results from EPO",
             "TORONTO, July 16, 2025 -- Torex Gold Resources Inc. reports results from the Morelos Property. The Company is "
             "on track to achieve the planned 12,000 m of drilling specific to the northern extension of EPO by the end "
             "of the year, with 9,430 m completed by mid-May over 12 drill holes. " + "Filler geology. " * 12)
    eq("TXG part-way is underway", [(x["status"], x["season"]) for x in r if x["program_type"] == "drilling"][-1:],
       [("underway", "2025")])
    eq("this year pattern", bool(_THIS_YEAR.search("planned for this year at El Naranjo")), True)
    eq("drilling that includes named deposits is the whole program", _part_of_property(
        "We are now excited to complete our 7,000 m drill program across the Cassiar Gold Property that will include "
        "drilling at the Taurus Deposit and Newcoast.", "Cassiar"), False)
    eq("a sub-area needs the whole property named", _part_of_property(
        "Follow up drilling at Balla Balla Project is planned with 6,000 m of Aircore drilling at the Babbage and Ramquarry "
        "Prospects.", "Balla Balla"), False)
    r = rows("Abitibi Metals Drills 9.75 Metres at 3.97% CuEq at the B26 Deposit",
             "MONTREAL, June 20, 2024 -- Abitibi Metals Corp. reports results. Phase 1 Highlights: Since optioning B26, the "
             "Company completed 13,529 metres of drilling in 44 holes. " + "Filler geology. " * 12)
    eq("headline on a target of a complex", _target_of_complex(
        "Torex Gold Reports Promising Drill Results from Media Luna West", "Morelos",
        "A total of 10,744 m of drilling was conducted across 23 drill holes (including eight parent holes) during 2025.",
        "The Media Luna West target is part of the Media Luna Cluster, which also includes EPO."), "Media Luna West")
    eq("a target not said to be part of a complex keeps the project", _target_of_complex(
        "Goliath Reports Drill Results from Surebet", "Golddigger",
        "The fully funded drill program will include approximately 50,000 meters of systematic drilling.",
        "The Surebet discovery is on the Golddigger Property."), None)
    eq("metres planned in a year", bool(_METRES_PLANNED.search(
        "With approximately 125,000 metres of drilling planned in 2025, almost double the metres drilled in 2024")), True)
    eq("a recent 'since' is the program, not a running total", [x["holes"] for x in r if x["holes"]], [44])

    # 1.2 -- recall
    r = rows("Kenorland Minerals Reports Assay Results from Maiden Diamond Drill Program at the Western Wabigoon Project",
             "TORONTO, September 3, 2026 -- Kenorland Minerals Ltd. is pleased to announce assay results from its maiden "
             "diamond drill program at the Western Wabigoon Project. The program comprised 4,089 metres in nine diamond "
             "drill holes testing the W2 target area. " + "Filler geology. " * 12)
    eq("results headline takes the body's status", [(x["program_type"], x["status"], x["metres"], x["holes"]) for x in r],
       [("drilling", "completed", 4089.0, 9)])
    r = rows("XXIX Receives Permit to Drill Thierry",
             "TORONTO, July 6, 2026 -- XXIX Metal Corp. received its permit at the Thierry Project. The Company's first "
             "systematic, 73.5 line-kilometre induced polarization (IP) survey identified a 75-125 metre wide anomaly "
             "extending more than 2.5 km between K1 and K2. " + "Filler geology. " * 12)
    eq("a survey that found something is finished", [(x["program_type"], x["status"], x["survey_type"]) for x in r
                                                      if x["program_type"] == "geophysics"], [("geophysics", "completed", "IP")])
    r = rows("Super Copper Updates Castilla",
             "VANCOUVER, September 8, 2026 -- Super Copper Corp. reports on the Castilla Project. The IP lines are grouped "
             "over six target areas identified from the 2023 and 2025 rock sampling programs at the Castilla Project. "
             + "Filler geology. " * 12)
    eq("a program named by an earlier year, one row a year", sorted(x["season"] for x in r if x["program_type"] == "ground"),
       ["2023", "2025"])
    r = rows("Trace Metals Samples Eagle",
             "VANCOUVER, August 4, 2026 -- Trace Metals Corp. (CSE: TRAC) reports on the Eagle Project. Targets were refined using "
             "Cosa's 2024 VTEM survey over the eastern claims. " + "Filler geology. " * 12)
    eq("another company's program named by a year is not the issuer's",
       [x for x in r if x["program_type"] == "geophysics" and not x["historical"]], [])
    r = rows("Goldcliff Starts Fieldwork at Pinto Ridge Project",
             "RENO, August 4, 2026 -- Goldcliff Resource Corp. reports on the Pinto Ridge Project. Targets were refined "
             "from the 2025 summer field program, as well as the 2024 drill program. "
             + "Filler geology. " * 12)
    eq("a program's season is the year that names it", [x["season"] for x in r if x["program_type"] == "drilling"],
       ["2024"])
    eq("capitals read as a title", _clean_proj("PROGRAM AT THE GOCHAGER LAKE"), "Gochager Lake")
    eq("a word split after its capital", "Volney Project" in _prepare("RESULTS AT THE VOLNEY PEGMATITE",
                                                                     "drill results at its V olney Project")[1], True)
    eq("metres not a drilled depth", _metres("a pegmatite at 72.7 m drilled depth"), None)

    eq("metres not a depth", _metres("to a depth of 450 m below surface"), None)
    eq("metres of drilling", _metres("a 5,000 metre drill program"), 5000.0)
    eq("holes word", _holes("completed five diamond drill holes totalling 2,548 m"), 5)
    eq("line km", _linekm("a 73.5 line-kilometre induced polarization survey"), 73.5)
    eq("phase", _phase("Phase II drilling"), "Phase 2")
    # 1.2.1: program sizes in table cells and brackets, sizes stated elsewhere in the release, and budgets
    eq("size as a table cell", _metres_more("Labour Contract - 2025 Diamond Drill Program Minimum 4,000m and D5 Dozer Lease"), 4000.0)
    eq("size after a colon", _metres_more("Total planned drilling: approximately 1,800 meters."), 1800.0)
    eq("size as a length", _metres_more("permits for 12 holes totaling a length of ~3,000 metres at Schooner"), 3000.0)
    eq("size after the holes", _metres_more("This Phase I program will consist of 10 drill holes and approximately 6,000m."), 6000.0)
    eq("size in a bracket", _metres_more("will comprise approximately 14,230 feet (about 4,300 metres) of drilling"), 4300.0)
    eq("a hole's length is not a size", _metres_more("with average hole lengths of approximately 150 m."), None)
    eq("PDF comma", _prepare("", "up to 3 ,000 metres of diamond drilling")[1], "up to 3,000 metres of diamond drilling")
    r = rows("Gray Rock Adds Second Drill Rig at Titac",
             "Gray Rock Resources Ltd. announces the mobilization of a second drill rig to the Titac Project. Drilling "
             "is underway with the first rig. The second rig is part of the Company's plan to complete approximately "
             "5,000 metres of core drilling this season. " + "Filler geology. " * 12)
    eq("size from the release", [x["metres"] for x in r if x["program_type"] == "drilling"][:1], [5000.0])
    eq("budget before the figure", _budget("a record high exploration budget of $10 million at Haile this year"), (10e6, "CAD"))
    eq("budgeted at", _budget("This first phase exploration program is budgeted at $375,000."), (375000.0, "CAD"))
    eq("an article is not a currency", _budget("the start of a $3.5 million exploration program")[1], "CAD")
    eq("CDN written apart", _budget(_prepare("", "This CDN $1,000,000 winter drilling program")[1]), (1e6, "CAD"))
    eq("treasury is not a budget", bool(_NOT_BUDGET.search("a treasury of over $9 million, fully funded for its 2026 "
                                                           "exploration programs")), True)
    # 1.2.2: names from the shared helper, in this page's form
    eq("helper name, page form", _page_name("Hemlo Gold Project"), "Hemlo")
    eq("a helper name 1.2.1 would not keep", _page_name("RC Gold Project"), None)
    eq("page form trims as 1.2.1 did", _page_name("Electrolode Critical Minerals Project"), "Electrolode")
    eq("page form drops a metal pair", _page_name("Centrefire Copper-Gold Project"), "Centrefire")
    eq("page form keeps a plain name", _page_name("Kendal Property"), "Kendal")
    eq("the headline's project stays 1.2.1's", _primary_project("Kremer Resources Starts Drilling at the Kremer Gold Project",
                                                                 "Drilling at the Kremer Gold Project started. The nearby Hemlo Mine "
                                                                 "is 20 km away. The Hemlo Mine produced gold."), "Kremer")
    # 1.2.3 (2026-09-30, ACC150 fix-list item 2): project names, one row per program, sizes from the text, no rows for
    # study databases, commitments, conditions, marketing or testwork, programs inside results releases, seasons
    eq("commodity list before Project", [n for _p, n in _projects("drilling at the Nicobi Nickel, Copper & Cobalt Project")],
       ["Nicobi"])
    eq("commodity words and a district", [n for _p, n in _projects("the Greenwood District Precious and Battery Metals Project")],
       ["Greenwood"])
    eq("a leading commodity word that starts the name", _clean_proj("Silver Queen Ag-Au"), "Silver Queen")
    eq("a direction that ends the name", _clean_proj("Great Northern"), "Great Northern")
    eq("another company's property", _clean_proj("Wallbridge’s Fenelon", {"midland"}), None)
    eq("the issuer's own possessive", _clean_proj("Nuvau's Matagami", {"nuvau"}), "Matagami")
    eq("a common word's possessive", _clean_proj("Today's Kibi", {"xtra-gold"}), "Kibi")
    eq("a place with a possessive", _clean_proj("Clark's Brook", {"general"}), "Clark's Brook")
    eq("a property named after another company", _clean_proj("Kinross Bald Mountain", {"fremont", "!kinross"}), None)
    eq("a company is not a property", _clean_proj("Barrick Mining Corporation’s"), None)
    eq("a people's adjective is not a property", _clean_proj("Mongolian"), None)
    eq("a licence kind is not a name", _clean_proj("Uranium Exclusive Prospecting"), None)
    eq("a headline verb before the name", _clean_proj("Xtra-Gold Further Delineates Kibi"), "Kibi")
    eq("Diamond starts a name unless a drill word follows", (_clean_proj("Diamond Mountain Phosphate"),
                                                             _clean_proj("Maiden Diamond Drill Program Mel")), ("Diamond Mountain", "Mel"))
    eq("a headline fragment is not the project", _primary_project(
        "Para Resources Expands Holdings in Arizona to Include Adjacent Claims in the Oatman District",
        "Para Resources Inc. has staked claims in the Oatman District. The Oatman Project hosts historic mines. "
        "The Oatman Project is road accessible."), "Oatman")
    eq("a mine in the headline gives way to the property", _primary_project(
        "1911 Gold Initiates Surface Drill Program at the True North Gold Mine",
        "1911 Gold Corporation reports on its Rice Lake Gold Property. Targets at the True North Gold Mine were drilled.",
        {"1911"}), "Rice Lake")
    eq("a bare mention of another own property", _project_in(
        "At Cervantes, Aztec has drilled over 12,200 meters across 73 drill holes.", ["Tombstone", "Cervantes"],
        "Tombstone", {"aztec"}, 30), "Cervantes")
    eq("a deposit inside the project is the project", _project_in(
        "A minimum of 10,000 meters of drilling is planned near the Goldstorm Deposit.", ["Treaty Creek"],
        "Treaty Creek", {"tudor"}, 20), "Treaty Creek")
    eq("another company's property is FOREIGN", _project_in(
        "contiguous to Aris Mining's Juby Project, where approximately 4,600m of drilling was completed.", ["Gowganda"],
        "Gowganda", {"imetal"}, 60), FOREIGN)
    r = rows("Tudor Gold Commences Drill Program at Treaty Creek",
             "VANCOUVER, May 21, 2026 -- Tudor Gold Corp. announces the start of its 10,000 metre drill program at the Treaty "
             "Creek Project. A minimum of 10,000 meters of drilling is planned to follow up zones near the Goldstorm "
             "Deposit. " + "Filler geology. " * 12)
    eq("one program read twice is one row", [(x["project"], x["status"], x["metres"]) for x in r if x["program_type"] == "drilling"],
       [("Treaty Creek", "started", 10000.0)])
    r = rows("Benz Mining Corp. Provides Update",
             "VANCOUVER, June 21, 2017 -- Benz Mining Corp. reports on the Mel Project. The proposed work program is scheduled "
             "to start in mid-July and will include excavator trenching and up to 8,000 m of diamond drilling. "
             + "Filler geology. " * 12)
    eq("one program of several kinds is one drilling row", [(x["program_type"], x["metres"]) for x in r], [("drilling", 8000.0)])
    eq("a results batch is not the program", (_holes("results of the remaining 6 HQ diamond drill holes totaling 1,143 m"),
                                              _metres("results of the remaining 6 HQ diamond drill holes totaling 1,143 m")), (None, None))
    eq("holes counted by what they found", _holes("All three drillholes successfully intercepted high-grade mineralization"), None)
    eq("an intercept's width is not a size", _metres("Intersects Gold Mineralization Over 72 m and Starts Drill Program"), None)
    eq("a working's length is not a size", _metres("driving two exploration adits totaling 152 meters and 22 short holes"), None)
    eq("drilling after trenching keeps its size", _metres("mapping, trenching and 4700m of diamond drilling"), 4700.0)
    eq("holes of the planned program", _holes("Four holes totaling 1,422 metres of the planned 18 hole, 6,000 metre 2025 drill "
                                              "program have been completed"), 18)
    eq("earlier holes are not a current program's", _holes("Five previous drill holes delineated a body", historical=False), None)
    eq("a study's drilling database is not a program", rows(
        "Silverco Files Updated Mineral Resource Report on the Cusi Project",
        "VANCOUVER, January 14, 2026 -- Silverco reports. The Cusi Project MRE is based on a validated database which includes "
        "data from 2,052 drillholes totalling 360,237 m completed between 2006 and October 2025. " + "Filler. " * 20), [])
    eq("an obligation is not a program", rows(
        "Condor Updates Ocros", "LIMA, January 30, 2017 -- Condor reports on the Ocros Project. Under their earn-in options, "
        "Casapalca were obligated to complete an aggregate of 3,000m of diamond drilling over the two projects. " + "Filler. " * 20), [])
    eq("a conditional plan is not a program", rows(
        "Diamond Fields Announces Extension to Beravina Project Agreement",
        "VANCOUVER, September 29, 2020 -- Diamond Fields reports on the Beravina Project. If successful, the Company has the "
        "option to engage in a drilling campaign on the Project to delineate such deposits. " + "Filler. " * 20), [])
    eq("a marketing release needs a size", rows(
        "Sun Summit Retains Jasper Gatrill for Corporate Communications",
        "VANCOUVER, April 14, 2022 -- Sun Summit Minerals Corp. reports on the Buck Project. The Company intends to complete "
        "a significant drill program in 2022 on the Buck Project. " + "Filler. " * 20), [])
    eq("a testwork release has no ground row", [x for x in rows(
        "FPX Nickel Reports Expanded Field Tests at the Baptiste Deposit",
        "VANCOUVER, June 9, 2021 -- FPX Nickel reports on the Baptiste Project. The Phase 1 field program was conducted at an "
        "outdoor site from August 5-29, 2020. " + "Filler. " * 20) if x["program_type"] == "ground"], [])
    r = rows("Allied Critical Metals Expands High Grade Footprint at Borralha Tungsten Project",
             "LISBON, September 29, 2025 -- Allied Critical Metals reports assays from its ongoing 5,000-metre campaign at the "
             "Borralha Tungsten Project. To date, 3,721 metres of RC drilling have been completed out of the planned 5,728 "
             "metres. Drilling is ongoing. " + "Filler geology. " * 12)
    eq("a program underway in a results release, its total and year",
       [(x["status"], x["metres"], x["season"]) for x in r if x["program_type"] == "drilling"], [("underway", 5728.0, "2025")])
    eq("a program sized in metres is drilling", bool(_DRILL.search("from its ongoing 5,000-metre campaign")), True)
    eq("an enlarged program's size", _row("drilling", "Silver Hill", "underway",
                                          "the program was expanded to 1,400 m from 800 m")["metres"], 1400.0)
    eq("an update headline takes the lead's status", [x["status"] for x in rows(
        "Norsemont Provides Update on Choquelimpie Sonic Drilling",
        "VANCOUVER, November 2, 2021 -- Norsemont is pleased to announce that it has now completed 1,374 meters of sonic "
        "drilling across all historic dumps on the Choquelimpie Project. " + "Filler geology. " * 12)], ["completed"])
    eq("a drill rig's arrival is a start", _hl_status("Usha Resources Announces Arrival of Drill Rig to the Jackpot Lake "
                                                        "Project", "drilling"), "started")
    eq("expanding a land position is not a program's state", _hl_status(
        "Midland Identifies New Geophysical Target on Samson and Expands Strategic Position", "geophysics"), "completed")
    eq("some holes of a program done", _hl_status("Lithium Chile Completes Three Additional Holes On Salar De Arizaro Drill "
                                                    "Program", "drilling"), "underway")
    r = rows("Canasil Applies for Drill Permit for the Vizcaino Project",
             "VANCOUVER, February 18, 2026 -- Canasil plans to begin the Phase 1 drill program of 1,050 metres in 6 holes at "
             "the Vizcaino Project in Q2 2026. Following evaluation of the results from the Phase 1 program, the Company has "
             "planned a Phase 2 drill program of 1,450 metres in 8 holes. " + "Filler geology. " * 12)
    eq("planned phases are one row, the first phase's", [(x["phase"], x["metres"]) for x in r], [("Phase 1", 1050.0)])
    eq("no program ahead on a sold property", rows(
        "Storm Completes Sale of Miminiska Project and Outlines Plans for 2026",
        "VANCOUVER, February 13, 2026 -- Storm Exploration reports. The Miminiska Project was sold. A drill program is planned "
        "at the Miminiska Project in 2026 by the buyer. " + "Filler. " * 20), [])
    r = rows("Fredonia Mining Completes Phase III Drilling at the El Dorado Monserrat Project",
             "BUENOS AIRES, January 20, 2022 -- Fredonia Mining Inc. announces completion of its phase III drilling program "
             "of 2,955 m in 12 holes at its flagship El Dorado Monserrat (“EDM”) project. The program at its EDM project was "
             "completed. " + "Filler geology. " * 12)
    eq("a property named by its initials", sorted({x["project"] for x in r}), ["El Dorado Monserrat"])
    r = rows("Medaro Mining Completes Phase 1 Exploration Work On The Rapide Lithium Property",
             "VANCOUVER, December 22, 2022 -- Medaro announces the completion of its Phase 1 exploration fieldwork program on "
             "its Rapide Lithium Property. A total of thirteen diamond drill holes were drilled with a cumulative drilling "
             "of 2,805 metres. " + "Filler geology. " * 12)
    eq("a general field program is the drilling program", [(x["program_type"], x["metres"], x["holes"]) for x in r],
       [("drilling", 2805.0, 13)])
    eq("a licence is a landholding", [n for _p, n in _projects("on Angkor’s Oyadao South license", {"angkor"})], ["Oyadao South"])
    eq("a name broken at its hyphen", "Vardenis Cu-Au Property" in _prepare("", "the Vardenis Cu- Au Property")[1], True)
    # key gate (2026-09-30)
    r = rows("Provenance Gold Provides Drilling Update at Eldorado",
             "VANCOUVER, October 29, 2024 -- Provenance Gold Corp. provides an update on its core drilling program at the "
             "Eldorado Project. Two core holes have been completed and a third is in progress with the completion of over "
             "500m of core drilling to date. The results will help design and initiate a substantial drill program for the "
             "spring of 2025. " + "Filler geology. " * 12)
    eq("a program underway and one planned for a later year are two rows",
       sorted((x["status"], x["season"]) for x in r), [("planned", "spring 2025"), ("underway", "2024")])
    eq("all four holes of a finished phase", _holes("As expected, all four drill holes intersected high-grade gold."), 4)
    eq("all three holes of a first batch are not the program", _holes(
        "results from the first three drillholes. All three drillholes successfully intercepted high-grade gold"), None)
    eq("all nine holes with assays are a batch", _holes("intersected gold in all nine holes for which assays have been "
                                                        "received"), None)
    r = rows("GoldMining Commences Exploration Drilling at Sao Jorge Project",
             "VANCOUVER, May 12, 2025 -- GoldMining Inc. has commenced drilling with two diamond core drills at its Sao "
             "Jorge Project. • Commenced drilling at Sao Jorge with two diamond core drills • Approximately 500 metres "
             "completed of the planned campaign of up to 5,000 metres • " + "Filler geology. " * 12)
    eq("progress on a campaign of up to M metres", [(x["status"], x["metres"]) for x in r], [("started", 5000.0)])
    r = rows("Ashley Gold Provides Interim IP Data on the Tak Patents",
             "CALGARY, March 14, 2026 -- Ashley Gold Corp. announces the completion of the IP survey on the Tak Patents. "
             "Project Overview: Burnthut & Tak Patents The Company holds a 100% stake in the Burnthut Project, which is "
             "composed of 83 mining claims and 6 patents. " + "Filler geology. " * 12)
    eq("patents inside a named project are the project", [x["project"] for x in r], ["Burnthut"])
    eq("a property named for comparison is not the container", _part_in_project(
        "Nianfors", "District Receives Approval of Nianfors Mineral License Applications",
        "The two styles of mineralization at Nianfors are very similar to what we have seen at our Sagtjarn Property.",
        {"district"}), None)
    # 2026-10-01: full-text losses (releases the box reads whole)
    F = " Filler geology text about the rocks." * 12
    eq("ft: the program's size after a results batch", _metres(
        "is pleased to report results from the final nine holes completed during the 10,217-metre winter drill campaign "
        "at the Douay Gold Project"), 10217.0)
    eq("ft: the program's holes after a results batch", _holes(
        "assay results from the first two drill holes of a seven hole 2,600 metre exploration program"), 7)
    eq("ft: 'Ground Geophysical Survey' is a program", _hl_status(
        "Trench Metals Commences Ground Geophysical Survey At Carter Lake Uranium Project", "geophysics"), "started")
    r = rows("K92 Mining Announces Latest High-Grade Drill Results From Kora",
             "VANCOUVER, September 9, 2019 -- K92 Mining Inc. is pleased to announce results from the continuing diamond "
             "drilling of the Kora North Extension of the Kainantu Gold Project in Papua New Guinea." + F)
    eq("ft: results from the continuing drilling", [(x["project"], x["status"]) for x in r], [("Kainantu", "underway")])
    r = rows("Transatlantic Mining Intercepts 2.8 m of 19.3 g/t Gold at the US Grant Project",
             "VANCOUVER, January 19, 2017 -- Transatlantic Mining Corp. announces surface drill results from the US Grant "
             "Project. Figure 1 US Grant Schematic Long Section (Red Dots) Drill Results The surface drill program comprised "
             "14 holes for a total of 1,457 metres." + F)
    eq("ft: a caption run into 'The program comprised ...'", [(x["status"], x["metres"], x["holes"]) for x in r],
       [("completed", 1457.0, 14)])
    r = rows("Great Atlantic Completes Seventh and Eighth Holes of 2024 Diamond Drilling Program",
             "VANCOUVER, October 28, 2024 -- Great Atlantic Resources Corp. announces its wholly owned subsidiary, Golden "
             "Promise Mines Inc., has completed the seventh and eighth holes of the 2024 diamond drilling program at its "
             "Golden Promise Gold Property." + F)
    eq("ft: a subsidiary named after the property is not another company", sorted({x["project"] for x in r}), ["Golden Promise"])
    eq("ft: a place both are named after, with a direction", _clean_proj("Troilus East", {"!troilus"}), "Troilus East")
    eq("ft: still another company's property", _clean_proj("Kinross Bald Mountain", {"!kinross"}), None)
    eq("ft: drilling for a mine's construction", rows(
        "LVG Mobilizes Rigs to Imwelo", "DAR ES SALAAM, May 7, 2026 -- LVG has confirmed the mobilization of RC drill rigs "
        "to the Imwelo Gold Project, with a ~21-day sterilization drilling program scheduled. Pre-construction drilling "
        "underway." + F), [])
    eq("ft: a place word ends a name", [n for _p, n in _projects(
        "at its High Grade Root Spring Gold-Silver Project and the Mesa Well Copper Property")], ["Root Spring", "Mesa Well"])
    eq("ft: a licence kind ends a name", [n for _p, n in _projects("Commences Drilling on Its Tay Exploration License")], ["Tay"])
    eq("ft: lower-case commodity words", [n for _p, n in _projects("at the Deer Horn polymetallic property")], ["Deer Horn"])
    eq("ft: a quoted nickname", [n for _p, n in _projects('at its Pardo "River of Gold" Project')], ["Pardo"])
    eq("ft: Prospect starts a name", [n for _p, n in _projects("at Prospect Valley Gold Property")], ["Prospect Valley"])
    eq("ft: a lower-case permit", [n for _p, n in _projects("work on the Kimoukro permit and the ITS permit")], ["Kimoukro"])
    eq("ft: not a land use permit", [n for _p, n in _projects("receives Land Use Permit")], [])
    eq("ft: a misspelt its", [n for _p, n in _projects("Drill Program On It\u2019s Dome Mountain Gold Project")], ["Dome Mountain"])
    eq("ft: an ampersand in a name", [n for _p, n in _projects("to Acquire the J&L Gold-Polymetallic Project")], ["J&L"])
    eq("ft: a leading adjective", [n for _p, n in _projects("The Miocene-aged Esperanza porphyry copper-gold project")],
       ["Esperanza"])
    eq("ft: a company's plural possessive", [n for _p, n in _projects("Yukon Metals\u2019 silver-lead-zinc project")], [])
    eq("ft: a preposition before Project", [n for _p, n in _projects("A MAJOR INCREASE IN PROJECT VALUE")], [])
    eq("ft: one name word and a place word", _clean_proj("Battery Hill"), "Battery Hill")
    eq("ft: a direction alone", _clean_proj("East"), None)
    eq("ft: a market is not a property", _clean_proj("OTCQX Market"), None)
    eq("ft: a person's possessive in a name", _clean_proj("Lewis Pilley\u2019s", {"hm"}), "Lewis Pilley\u2019s")
    r = rows("Drilling Update at Playfair\u2019s RKV Project in Norway",
             "NEWS RELEASE August 12, 2022. Playfair is now drilling the main target at RKV, with 11 holes drilled to date "
             "and drilling continuing." + F)
    eq("ft: the issuer as the lead's subject", sorted({x["project"] for x in r}), ["RKV"])
    eq("ft: a two-character issuer name", "e3" in _issuer_words("E3 Lithium begins drilling",
                                                                '(the "Company" or "E3") is pleased'), True)
    eq("ft: a zone by its property's possessive", _primary_project(
        "XXIX Begins Drilling at Opemiska's Saddle Zone", "XXIX has commenced its 20-hole drill program at the Saddle Zone, "
        "a key target within the Opemiska open pit." + F, {"xxix"}), "Opemiska")
    eq("ft: a regulator's board", bool(_NON_EXPL_HL.search("Permit from the Mackenzie Valley Land and Water Board")), False)
    eq("ft: nearly complete", _hl_status("Compass Completes Offering - First Phase of Trenching Nearly Complete at Tarabala",
                                         "ground"), "underway")
    eq("ft: a quarter that times a program", _hl_status(
        "Arizona Silver Announces Completion Of The Q2 RC Drilling Program At Philadelphia Property", "drilling"), "completed")
    r = rows("Emgold Provides Exploration Update For Its Nevada Properties",
             "VANCOUVER, February 23, 2021 -- Emgold provides the following update. Golden Arrow Gold and Silver Property, NV "
             "The Golden Arrow property is an advanced stage property. The Company just completed an airborne magnetic and "
             "radiometric geophysical survey." + F)
    eq("ft: a portfolio update's property heading", [(x["project"], x["program_type"], x["status"]) for x in r],
       [("Golden Arrow", "geophysics", "completed")])
    eq("ft: the property named before its program", _primary_project(
        "F4 Reports Anomalous Radioactivity at Murphy Visually Identified Pitchblende",
        "F4 Uranium Corp is pleased to announce initial results from the first two drillholes of the ongoing Murphy Lake "
        "drill program." + F, {"f4"}), "Murphy Lake")
    eq("ft: the issuer's mining complex", _own_complex("the Chame target, within the Company\u2019s Paciencia complex in Brazil",
                                                       set()), "Paciencia")
    eq("ft: the place a headline runs into other words", _body_prefix("Thor Connecting Megagossan",
                                                                      "work on the Thor project", set()), "Thor")
    eq("ft: after a qualifier", _body_prefix("Main Nisk Deposit", "the knowledge acquired at Nisk Main", set()), "Nisk")
    eq("ft: a caption link is a break", " . " in _prepare("", "Figure 1: Map To view an enhanced version of Figure 1, "
                                                          "please visit: https://x.com/a.jpg The drilling campaign continues")[1],
       True)
    eq("ft: planning to conduct", _status("The company is also planning to conduct a 3,000 metre drill program"), "planned")
    eq("ft: planning and delay in a headline", (_hl_status("Mexican Gold Also Planning 3,000 Metre Drill Program", "drilling"),
                                                _hl_status("Sego Plans Financing - Drilling Delayed Due To Wildfire",
                                                           "drilling")), ("planned", "planned"))
    eq("ft: a campaign that continues", bool(_ONGOING.search("The drilling campaign continues at the Tamarack Project")), True)
    eq("ft: a survey to guide drilling", _hl_type("Tower Commences Ground Magnetic Survey to Guide Diamond Drilling", ""),
       "geophysics")
    r = rows("IsoEnergy Intersects 4.0m of 20.5% U3O8 at Larocque East",
             "TORONTO, March 18, 2020 -- IsoEnergy reports results. The winter drilling program has been completed at the "
             "Larocque East property." + F)
    eq("ft: a season names the program", [(x["project"], x["status"]) for x in r], [("Larocque East", "completed")])
    eq("ft: a size in a budget's words", bool(_PLAN_SIZE.search("The drill program has been budgeted for 5,000 metres")), True)
    eq("ft: the ongoing drilling as subject", bool(_ONGOING_SUBJECT.match("The ongoing drilling targeting the fault "
                                                                          "continues to deliver")), True)
    r = rows("Foremost Commences 2026 Winter Diamond Drill Program at Hatchet Lake Uranium Project",
             "VANCOUVER, February 23, 2026 -- Foremost announces the commencement of its planned ~5,000-metre winter diamond "
             "drill program at the Hatchet Lake Uranium Project. Drilling is currently underway at the Tuning Fork target."
             + F)
    eq("ft: going on now does not turn a start into underway", [x["status"] for x in r], ["started"])
    eq("ft: a zone word before Deposit", _clean_proj("Mel Main Zone"), "Mel Main Zone")
    eq("ft: a royalty holder's release", rows(
        "More Drilling on Globex\u2019s Battery Hill", "ROUYN-NORANDA, April 10, 2025 -- Globex holds a royalty on the Battery "
        "Hill Property, operated by Manganese X Energy Corp. Manganese X has reported 12 new drill holes totalling 1,393 "
        "metres on the property." + F), [])
    eq("ft: a release with no text", [(x["project"], x["status"]) for x in rows(
        "Four Nines Gold Begins Maiden Drill Program at Hayden Hill",
        "This release is published on Accesswire. Click 'Original source' to read the full release.")],
       [("Hayden Hill", "started")])
    eq("ft: a headline possessive is the issuer's", [n for _p, n in _title_projects(
        "Drilling Commencing at Patriot Gold's Windy Peak Gold Project in Nevada", {"drilling"})], ["Windy Peak"])
    eq("ft: a person's possessive in a headline", [n for _p, n in _title_projects(
        "Black Mammoth Metals Acquires Tom's Pediment Gold-Silver Property", {"black", "mammoth"})], ["Tom's Pediment"])
    eq("ft: the season has started", _near_status(
        "Now that drilling has concluded and the dry season has started, Aztec in early 2023 will next carry out channel "
        "sampling", 107, 123), "planned")
    eq("ft: a permit for a planned program", bool(_PERMIT_FACT.search("is now authorized to commence an active program")),
       True)
    eq("ft: a headline with field news", [x["project"] for x in rows(
        "CanAlaska Now Trading on OTCQX; New uranium discovery advancing",
        "SASKATOON, July 28, 2022 -- On the Company's Manibridge project, its partner is continuing work on the phase two "
        "summer drill program." + F)], ["Manibridge"])
    eq("ft: updates and finds in headlines", (_hl_status("Lancaster Updates 2026 Exploration Program", "ground"),
                                             _hl_status("Black Mammoth Finds Geophysical Target", "geophysics")),
       ("underway", "completed"))
    eq("ft: a database sentence that also says drilling goes on", len(rows(
        "Solaris Confirms Second Porphyry Center at Warintza East",
        "VANCOUVER, May 2, 2023 -- Solaris reports. MRE drilling program continues: the 2022 MRE is based on drilling to "
        "the end of 2021, with ongoing drilling aimed at expanding the resource at the Warintza Project." + F)), 1)
    eq("ft: a salar", [n for _p, n in _projects("Prepares For Drilling at Incahuasi Lithium Salar")], ["Incahuasi"])
    eq("ft: a resource supported by its drilling", bool(_DATABASE.search(
        "The Resource is pit-constrained and is supported by 224,000 m of drilling in 517 drill holes")), True)
    eq("ft: surface sampling is a program phrase", _strong("Taranis completed further surface sampling on the zone in 2022"),
       True)
    # ---- 1.2.4 (2026-10-02): speed on long link lists; capture
    lst = " ".join("https://example.com/" + "-".join(["Some-Long-Hyphenated-Name"] * 12) + "-%d" % k for k in range(200))
    eq("f4: a long token is masked, offsets kept", (len(_mask_long("ab " + "x" * 45 + " cd")),
                                                   _mask_long("ab " + "x" * 45 + " cd")[:4]), (51, "ab #"))
    eq("f4: names around a link list", [n for _p, n in _projects(lst + " work on the Foo Lake Project")], ["Foo Lake"])
    eq("f4: no name inside a link", [n for _p, n in _projects("see https://x.com/Big-Lake-Gold-Project-Drilling-Update-2024")],
       [])
    r = rows("Pirate Gold Intersects 0.54% Cu Eq over 180.8m at its Treasure Island Project",
             "TORONTO, March 18, 2026 -- Pirate Gold reports results from the Treasure Island Project. Drilling to test the "
             "extension is advancing with two drill rigs in operation." + F)
    eq("f4: a results release's drilling goes on", [(x["program_type"], x["project"], x["status"]) for x in r],
       [("drilling", "Treasure Island", "underway")])
    r = rows("Benchmark Drills 3.05 Metres of 73.60 g/t Gold at the Cliff Creek Project",
             "VANCOUVER, March 18, 2022 -- Benchmark reports new drill results from the Cliff Creek Project. The new results "
             "fill gaps in the modelled pit shell." + F)
    eq("f4: a results release's drilling, finished", [(x["program_type"], x["status"]) for x in r], [("drilling", "completed")])
    eq("f4: not the optionee's results", rows(
        "Strategic Metals receives drill results from its Hopper Cu-Au-Ag project, Yukon",
        "VANCOUVER, September 28, 2021 -- Strategic reports that CAVU announced excellent drill results at the Hopper "
        "project. CAVU holds the Hopper project under option and can acquire a 70% interest." + F), [])
    eq("f4: a sampling headline is not drill results", rows(
        "Prismo Metals Samples 14.35 g/t Gold over 0.5 meters at Los Pavitos Project",
        "TUCSON, March 18, 2023 -- Prismo reports channel samples from the Los Pavitos Project." + F), [])
    eq("f4: drilling goes on, more ways", [bool(_DRILL_GOES_ON.search(x)) for x in (
        "Lion One is concurrently undertaking a two-pronged exploration drill campaign",
        "At the time of writing, hole TUG-141 is still being drilled",
        "the massive sulphides intercepted in this first hole of the fall drilling program",
        "The drill holes intersected massive sulphides")], [True, True, True, False])
    r = rows("Equity Metals Drilling Underway on the Silver Queen Property",
             "VANCOUVER, March 18, 2025 -- Equity Metals reports drilling is underway at the Silver Queen Property. "
             "Geophysical features identified in a DCIP geophysical survey conducted earlier this year have enhanced "
             "targeting at the Silver Queen Property." + F)
    eq("f4: a finished survey without 'recently'", sorted((x["program_type"], x["status"]) for x in r),
       [("drilling", "started"), ("geophysics", "completed")])
    r = rows("Aston Bay Identifies Copper Targets at the Storm Copper Project",
             "TORONTO, March 18, 2023 -- Aston Bay reports gravity results at the Storm Copper Project. The anomaly was "
             "intersected by drill hole ST22-10 in the 2022 drill campaign at the Storm Copper Project." + F)
    eq("f4: a later mention names the program", [(x["program_type"], x["status"], x["season"]) for x in r
                                                 if x["program_type"] == "drilling"], [("drilling", "completed", "2022")])
    r = rows("Altamira Gold Commences Drill Program at Cajueiro Project",
             "TORONTO, March 18, 2017 -- Altamira has commenced a 2,000 metre drill program at the Cajueiro Project. "
             "Soil samples were collected over the Cajueiro Project grid." + F)
    eq("f4: a finished field program named in passing", sorted((x["program_type"], x["status"]) for x in r),
       [("drilling", "started"), ("ground", "completed")])
    r = rows("Altamira Gold Commences Drill Program at Cajueiro Project",
             "TORONTO, March 18, 2017 -- Altamira has commenced a 2,000 metre drill program at the Cajueiro Project. "
             "Re-interpretation of the geophysical data was completed over the Cajueiro Project." + F)
    eq("f4: work on survey data is not a survey", [x["program_type"] for x in r], ["drilling"])
    eq("f4: no field work is not a program", _weak_mention("ground", "completed", "no field work was carried out",
                                                           "Since the earn-in, no field work was carried out by them.",
                                                           False, 2025, set()), False)
    r = rows("Golden Frac Sand Update",
             "VANCOUVER, March 18, 2017 -- Northern Tiger is pleased to announce that field crews have mobilized to its "
             "Golden Frac Sand Property." + F)
    eq("f4: a field program started", [(x["program_type"], x["project"], x["status"]) for x in r],
       [("ground", "Golden Frac Sand", "started")])
    r = rows("Big Ridge Commences IP Survey at the Hope Brook Gold Project",
             "ST. JOHN'S, May 20, 2026 -- Big Ridge has commenced an IP survey at the Hope Brook Gold Project. The team will "
             "be fully equipped when the drill rig mobilizes in mid-June at the Hope Brook Gold Project." + F)
    eq("f4: a start still ahead", sorted((x["program_type"], x["status"]) for x in r),
       [("drilling", "planned"), ("geophysics", "started")])
    eq("f4: exploration headlines", [_hl_type(t, "") is not None for t in (
        "Slave Lake Zinc Initiates NWT Exploration", "CopAur Outlines Upcoming Exploration Activities At Williams Project",
        "Doubleview Commences Advanced 2026 Exploration and Technical Program", "Kincora Provides Exploration Update")],
       [True, True, True, False])
    eq("f4: a field season that drills", _hl_type(
        "Doubleview Commences 2026 Exploration and Technical Program at the Hat Project",
        "The 2026 field season has started a coordinated program at Hat. Doubleview expects to begin drilling immediately "
        "as part of the 2026 exploration program."), "drilling")
    eq("f4: drill words", [bool(_DRILL.search(x)) for x in (
        "it has drilled approximately 2700 meters of its planned 3700 meter summer program",
        "Ten holes have now been completed from three pads", "Camp Construction and Drill Mobilization Underway",
        "Nearly 80 historical holes have been completed south of the creek")], [True, True, True, False])
    eq("f4: a gravity gradiometric survey", bool(_GEO.search("Announces Gravity Gradiometric Survey on East Sudbury")), True)
    r = rows("Sky Gold Contracts Diamond Driller for Clone Gold Project",
             "VANCOUVER, July 2, 2019 -- Sky Gold has contracted a driller for the Clone Gold Project. The Clone drill "
             "program is scheduled to commence July 22nd." + F)
    eq("f4: a start timing is a fact", [(x["program_type"], x["status"]) for x in r if x["program_type"] == "drilling"],
       [("drilling", "planned")])
    eq("f4: timings", [bool(_TIMING.search(x)) for x in (
        "planned for the second half of 2023", "a drill program planned in Q3 of this year", "commence in mid-June",
        "an IP survey to begin shortly", "news release dated May 5, 2023")], [True, True, True, True, False])
    eq("f4: more plan verbs", _near_status("The targets will be followed up with diamond drilling programs", 51, 66),
       "planned")
    r = rows("Grizzly Reports Exploration Results for the Greenwood Project",
             "CALGARY, March 18, 2024 -- Grizzly reports results at the Greenwood Project. Comparable sulphide zones were "
             "intersected in the 2022 drilling at the Dayton target on the Greenwood Project. Scout drilling of 5 holes in "
             "2021 noted porphyry dykes on the Greenwood Project." + F)
    eq("f4: drilling named by its year", sorted((x["status"], x["season"], x["holes"]) for x in r
                                                if x["program_type"] == "drilling"),
       [("completed", "2021", 5), ("completed", "2022", None)])
    eq("f4: not an earlier owner's drilling", [_year_named_drilling(s, _DRILL.search(s), None) for s in (
        "Prior drilling at Soledad in 2016 produced compelling results", "Drilling during 2021 intersected intrusive")],
       [None, "2021"])
    s4 = "visible gold in historic core from 2010 Auramex Resources drilling"
    eq("f4: a company between year and drilling", _year_named_drilling(
        s4, _DRILL.search(s4), re.search(r"\b((?:19|20)\d\d)(?:\s*(?:and|&|,)\s*((?:19|20)\d\d))?\s+(?:[\w-]+\s+){0,2}$",
                                         s4[max(0, _DRILL.search(s4).start() - 40):_DRILL.search(s4).start()])), None)
    r = rows("Transatlantic Reports on the Monitor Project",
             "VANCOUVER, March 18, 2025 -- Transatlantic summarizes work at the Monitor Project. Work by season: 2023 14 HQ "
             "drill holes at the Monitor Project, assayed by a laboratory." + F)
    eq("f4: a count between the year and the drill word", [(x["season"], x["holes"]) for x in r
                                                            if x["program_type"] == "drilling"], [("2023", 14)])
    eq("f4: Symbol-font bullets split sentences", _sentences(
        "Highlights: \uf03e Completed an 1,800m drill program at the project \uf03e Results included 112m grading 5.9 g/t"),
       ["Completed an 1,800m drill program at the project", "Results included 112m grading 5.9 g/t"])
    eq("f4: a data compilation is not a survey", _NOT_PROG_AFTER.match(" compilation and interpretation program") is not None,
       True)
    b4 = ("VANCOUVER, June 29, 2023 -- Origen provides an update on its 100% owned LGM property. Origen also owns the "
          "Wishbone property, west of the LGM property. The LGM property hosts porphyry targets.")
    eq("f4: a property known by its capitals", (_primary_project("Origen LGM and Wishbone Update", b4, set()),
                                               _primary_project("Kingfisher Closes Acquisition of the Ball Creek West (BAM) Project",
                                                                "Kingfisher acquires the Ball Creek West Project, called BAM. The "
                                                                "BAM property and the Ball Creek West Project are one.", set())),
       ("LGM", "Ball Creek West"))
    eq("f4: another company named", (_names_other_company("which Clean Air expects to add", {"benton", "!clean air"}),
                                     _names_other_company("which Benton expects to add", {"benton", "!clean air"})),
       (True, False))
    eq("fingerprint follows the helper", FP.uses(__file__, "portal.project_names"), True)
    print("exploration self-test: %s" % ("PASS" if not bad else "%d FAILED" % bad))
    return bad


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test("-v" in sys.argv) == 0 else 1)
