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

Self-tests: python3 -m portal.extractors.exploration
"""
from __future__ import annotations

import re
import unicodedata

from portal import facts as F

NAME = "exploration"
VERSION = "1.0.0"
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
    b = re.sub(r"\s+", " ", b)
    h = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", headline or ""))
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


def _title(h):
    """The headline without the lead some feeds append to it."""
    m = re.search(r"\s(?:is\s+pleased\s+to|announces?\s+that|\(\s*[\"“]|\((?:TSX|CSE|NYSE|NASDAQ|OTC)|[A-Z][\w&.'’\-]*"
                  r"(?:\s+[A-Z][\w&.'’\-]*){0,4}\s+(?:Inc|Corp|Ltd|Limited)\.?\s*\()", h[15:])
    return (h[:15 + m.start()] if m else h).strip()


def _sentences(text):
    parts = re.split(r"(?<=[.;!?])\s+(?=[A-Z“\"•▪(])|\s+[•▪●]\s+|\s+-\s+(?=[A-Z])", text)
    return [p.strip() for p in parts if len(p.strip()) > 12]


# ------------------------------------------------------------------ vocabulary
_NUMW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
         "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "a single": 1,
         "single": 1}
_NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?|" + "|".join(sorted(_NUMW, key=len, reverse=True)) + r")"

_DRILL = re.compile(r"(?i)\b(?:drill(?:ing)?\s+(?:program(?:me)?|campaign|plan)|(?:diamond|core|RC|reverse\s+circulation|"
                    r"sonic|aircore|air\s+core|RAB|auger|percussion)\s+drill(?:ing|holes?)?|drill\s*holes?|drilling|"
                    r"drill\s+(?:crews?|rigs?|test\w*)|(?:maiden|inaugural|first|initial)\s+drill\w*)\b")
_GEO = re.compile(r"(?i)\b(?:geophysic\w*|induced\s+polari[sz]ation|IP\s+(?:survey|program|lines?|geophysic\w*)|"
                  r"magnetic\s+survey|mag\s+survey|aeromagnetic\s+survey|magnetometer\s+survey|drone\s+mag\w*|VTEM|ZTEM|"
                  r"TDEM|MLEM|electromagnetic\s+survey|EM\s+survey|gravity\s+survey|lidar\s+survey|lidar|radiometric\s+"
                  r"survey|magnetotelluric|mobile\s*mt|airborne\s+(?:\w+\s+){0,3}?survey)\b")
_GRD = re.compile(r"(?i)\b(?:soil\s+(?:sampl\w+|geochem\w*|survey|grid|program)|till\s+(?:sampl\w+|survey)|HMC\s+sampl\w+|"
                  r"prospecting(?:\s+program)?|geological\s+mapping|mapping\s+program|trench(?:es|ing)?(?:\s+program)?|"
                  r"channel\s+sampl\w+|rock\s+(?:chip\s+|grab\s+)?sampl\w+|grab\s+sampl\w+|field\s+(?:program(?:me)?|work|"
                  r"season|campaign|crews?)|fieldwork|sampling\s+program|geochemical\s+(?:survey|sampling|program)|"
                  r"surface\s+(?:sampl\w+|exploration))\b")
_EXPLPROG = re.compile(r"(?i)\b(?:exploration\s+(?:program(?:me)?|campaign|work\s+program)|work\s+program)\b")

_ST = {
    "completed": re.compile(r"(?i)\b(?:successful(?:ly)?|complet(?:ed|es|ion)|concluded|finished|wrapped\s+up|were\s+(?:collected|drilled|"
                            r"completed)|was\s+(?:flown|completed|conducted)|has\s+drilled|drilled\s+(?:in\s+)?(?:19|20)\d\d|"
                            r"carried\s+out|conducted|totall?ing)\b"),
    "started": re.compile(r"(?i)\b(?:commenc(?:ed|es|ing|ement)|began|begun|begins|started|starts|mobiliz\w+|mobilis\w+|"
                          r"launch(?:ed|es|ing)?|initiat(?:ed|es|e)|kick(?:ed|s)?\s+off|resum(?:ed|es|ption)|is\s+now\s+"
                          r"underway|has\s+begun|have\s+begun)\b"),
    "underway": re.compile(r"(?i)\b(?:(?:nearly|almost|substantially)\s+complete\w*|underway|under\s+way|ongoing|in\s+progress|continu(?:es|ing)|to\s+date|progressing|"
                           r"currently\s+(?:being|drilling|testing))\b"),
    "planned": re.compile(r"(?i)\b(?:plan(?:s|ned)?\s+(?:to|for|a|an|the)|planned|will\s+(?:commence|begin|start|test|"
                          r"include|consist|comprise|drill|be\s+(?:drilled|conducted|carried|completed))|to\s+(?:commence|"
                          r"begin|start)|proposed|upcoming|scheduled|expected\s+to\s+(?:commence|begin|start)|intends?\s+"
                          r"to|prepar(?:es|ing|ations?)\s+for|fully\s+(?:funded|permitted)|permitted|budget(?:ed)?\s+(?:of|"
                          r"for)|design(?:ed|ing)\s+(?:a|the)|ready\s+for|finaliz\w+)\b"),
}
_HL_ST = [
    ("completed", re.compile(r"(?i)\b(?:complet(?:es|ed|ion\s+of)|concludes|finishes|wraps\s+up)\b")),
    ("started", re.compile(r"(?i)\b(?:commenc(?:es|ed|ement\s+of|ing)|begins|began|starts|started|start\s+of|mobiliz\w+|"
                           r"mobilis\w+|launch(?:es|ed)|initiat(?:es|ed)|kicks\s+off|resum(?:es|ption)|underway|is\s+on)\b")),
    ("underway", re.compile(r"(?i)\b(?:update|continues|progress|progressing|ongoing|expands)\b")),
    ("planned", re.compile(r"(?i)\b(?:plans?|planned|prepares|preparations|to\s+commence|to\s+begin|to\s+start|ready\s+for|"
                           r"announces\s+(?:(?:its|a|an|the|new|\d{4})\s+)*(?:[\w-]+\s+){0,2}(?:drill(?:ing)?\s+(?:program|plans?|campaign)|exploration\s+program|field\s+program|sampling\s+program|survey)|receives\s+"
                           r"(?:\w+\s+){0,3}permit|permit\s+to\s+drill|financing\s+for|funded\s+for|ahead\s+of|approval\s+"
                           r"for|designs|proposed|upcoming|strategy|to\s+(?:drill|test)|returns?\s+to)\b")),
]
_RESULTS_HL = re.compile(r"(?i)(?:g/t|\d\s?%\s?(?:Cu|Ni|Li2?O?|Zn|Pb|U3O8|Sb|WO3)|\bppm\b|intersect\w*|intercept\w*|"
                         r"assays?|results?|grading|returns?\s+up\s+to|discover\w*)")
_NOT_PROGRAM = re.compile(r"(?i)\b(?:resource\s+estimate|feasibility|pre-feasibility|PEA|metallurg\w*|bulk\s+sampl\w+|"
                          r"test\s+mining|mine\s+(?:plan|development|construction)|underground\s+development|"
                          r"production|processing\s+plant|option\s+agreement|work\s+commitments?|expenditures?\s+of|"
                          r"exploration\s+expenditures?|must\s+(?:incur|spend))\b")
_HIST = re.compile(r"(?i)\b(?:historic(?:al)?\s+(?:\w+\s+){0,2}?(?:drill\w*|diamond\s+drill\w*|trench\w*|soil\s+\w+|"
                   r"surveys?|sampling|geophysic\w*|mapping|exploration\s+(?:work|programs?))|(?:by|from)\s+(?:the\s+)?"
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
                     r"north|south|from|to\s+the)|\s*\w*\s*(?:g/t|%))")
_HOLES = re.compile(r"(?i)(?<![\w.#])" + _NUM + r"\s+(?:\d+(?:,\d{3})*\s*(?:-\s*)?(?:m|metres?|meters?)\s+(?:long\s+|deep\s+)?)?(?:(?!(?:metres?|meters?|m|km|deep|long)\b)[a-z][\w-]*[\s-]+){0,3}?(?:drill\s*)?holes?\b|(?<![\w.])" + _NUM +
                    r"-hole\b|(?<![\w.])" + _NUM + r"\s+drillholes?\b")
_LINEKM = re.compile(r"(?i)(?<![\w.])" + _NUM + r"\s*(?:-\s*)?line[\s-]*(?:kilomet(?:re|er)s?|km)\b|(?<![\w.])" + _NUM +
                     r"\s*(?:kilomet(?:re|er)s?|km)\s+of\s+(?:IP\s+)?lines?\b")
_BUDGET = re.compile(r"(?i)(?:(C|CA|CDN|US|A|AU)\$|\$)\s?(\d+(?:[.,]\d+)?)\s*(million|M|k|thousand)?\b(?=[^.]{0,60}?"
                     r"\b(?:program|budget|exploration|drill))")
_YEAR = re.compile(r"\b((?:19[5-9]|20[0-3])\d)\b")
_PHASE = re.compile(r"(?i)\bphase\s+(\d|I{1,3}V?|one|two|three|four)\b")
_SEASON = re.compile(r"(?i)\b(?:(winter|spring|summer|fall|autumn)\s+(?:of\s+)?((?:19|20)\d\d)|((?:19|20)\d\d)\s+(winter|"
                     r"spring|summer|fall|autumn)|(Q[1-4])\s+(?:of\s+)?((?:19|20)\d\d))\b")


_PROG_M = [
    re.compile(r"(?i)(?<![\w.])" + _NUM + r"\+?\s*(?:-\s*)?(?:metres?|meters?|m)\b,?[\s-]+(?:(?:of\s+)?(?:diamond\s+|core\s+|RC\s+|"
               r"reverse\s+circulation\s+|exploration\s+|infill\s+|surface\s+|underground\s+)?(?:drill(?:ing)?|drillholes?|"
               r"holes?)|(?:\w+\s+){0,2}(?:drill\s+)?(?:program(?:me)?|campaign))"),
    re.compile(r"(?i)" + _NUM + r"\+?\s*(?:metres?|meters?|m)\s+(?:planned|drilled|completed|of\s+(?:\w+\s+)?drilling)\b"),
    re.compile(r"(?i)(?:program(?:me)?\s+of|campaign\s+of|drilling\s+of|drilled|completed|totall?ing|comprised|comprising|consisting\s+of|"
               r"total\s+of|minimum\s+of)\s+(?:up\s+to\s+|approximately\s+|a\s+total\s+of\s+|"
               r"a\s+minimum\s+of\s+|over\s+|about\s+|~)?" + _NUM + r"\+?\s*(?:metres?|meters?|m)\b(?!\s*(?:wide|long|"
               r"deep|below|depth|of\s+\d|grading|@|at\s+\d))"),
]


def _metres(s, status=None):
    order = _PROG_M if status not in ("started", "planned") else [_PROG_M[2], _PROG_M[0], _PROG_M[1]]
    for rx in order:
        for m in rx.finditer(s):
            g = next(x for x in m.groups() if x)
            v = _num(g)
            if v is None or v < 50 or v > 400000:
                continue
            tail = s[m.end():m.end() + 30].lower()
            if re.search(r"^\s*(?:\w+\s+){0,2}(?:g/t|%|ppm|grading)", tail):
                continue
            return v
    return None


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


def _holes(s):
    for m in _HOLES.finditer(s):
        g = next(x for x in m.groups() if x)
        v = _num(g)
        if v is None or v < 1 or v > 1500 or v != int(v):
            continue
        tail = s[m.end():m.end() + 25].lower()
        if re.search(r"^\s*(?:returned|intersected|of\s+the|grading|with)", tail) and v <= 3:
            continue
        seg = m.group(0).lower()
        if re.search(r"\b(?:historic|previous|last|first|final|remaining|pending|deepening|reported|assayed)\b", seg):
            if "historic" in seg or "previous" in seg:
                pass
            else:
                continue
        return int(v)
    return None


def _linekm(s):
    m = _LINEKM.search(s)
    if not m:
        return None
    g = next(x for x in m.groups() if x)
    return _num(g)


def _budget(s):
    m = _BUDGET.search(s)
    if not m:
        return None, None
    v = _num(m.group(2))
    if v is None:
        return None, None
    mul = (m.group(3) or "").lower()
    v *= 1e6 if mul in ("million", "m") else 1e3 if mul in ("k", "thousand") else 1
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
_PROJ_WORD = r"(?:(?i:project|property|properties)|Prospect|Claims?|Claim\s+Block|Deposit|EP|Permit|Concessions?|Mine)"
_CAPNAME = r"([A-ZÀ-Ý][\w'’À-ÿ\-]*(?:[\s\-](?:[A-ZÀ-Ý][\w'’À-ÿ\-]*|de|del|la|di|du|des|y|and|&)){0,4})"
_PROJ_RX = re.compile(_CAPNAME + r"\s+(?:(?:Gold|Silver|Copper|Uranium|Lithium|Nickel|Antimony|Tungsten|Critical\s+"
                      r"Minerals?|Polymetallic|Copper-Gold|Gold-Silver|Silver-Gold|Gold-Copper|Rare\s+Earth|REE|VMS|"
                      r"Porphyry|Base\s+Metals?|Zinc|Graphite|Ni-Cu(?:-PGE)?|Cu-Au|Au|Ag|Cu)\s+)*" + _PROJ_WORD + r"\b")
_BAD_PROJ = {"The", "Our", "This", "Its", "Company", "Company's", "Company’s", "Each", "All", "New", "First", "Maiden",
             "Flagship", "Wholly", "Owned", "Option", "Optioned", "Drill", "Exploration", "Phase", "Winter", "Summer",
             "Spring", "Fall", "Autumn", "Gold", "Silver", "Copper", "Uranium", "Lithium", "Nickel", "Critical", "Mineral",
             "Minerals", "Canadian", "Nevada", "Ontario", "Quebec", "Québec", "Yukon", "British", "Columbia", "Saskatchewan",
             "Manitoba", "Newfoundland", "Labrador", "Nunavut", "Brazil", "Mexico", "Peru", "Argentina", "Chile", "Idaho",
             "Wisconsin", "Advanced", "Stage", "Historic", "Historical", "Additional", "Two", "Three", "Both", "These",
             "Other", "Mining", "Mines", "Owned", "Road", "Accessible", "Adjacent", "Neighbouring", "Past", "Producing",
             "Former", "Large", "District", "Scale", "High", "Grade", "Underexplored", "Under", "Explored", "Key",
             "Several", "Multiple", "Such", "Operating", "Current", "Early", "Northern", "Southern", "Western", "Eastern",
             "Central", "Rich", "Ni", "Co", "Energy", "Metals", "Resources", "Corp", "Inc", "Ltd", "Group", "Tsx", "TSX",
             "CSE", "Newfoundland’s", "Sb", "Ag", "Au", "Cu", "Zn", "Pb", "REE", "VMS", "In", "At", "On", "For", "To",
             "And", "With", "From"}


_HL_VERB = {"Receives", "Expands", "Announces", "Announce", "Commences", "Completes", "Launches", "Begins", "Starts",
            "Reports", "Provides", "Update", "Updates", "Results", "Field", "Work", "Program", "Programs", "Drilling", "Drill",
            "Following", "Plans", "Prepares", "Preparations", "Mobilizes", "Initiates", "Identifies", "Confirms",
            "Discovers", "Intersects", "Returns", "Closes", "Financing", "Continues", "Resumes", "Resumption", "Options",
            "Acquires", "Test", "Tests", "Testing", "Target", "Targets", "At", "The", "Of", "Its", "Their", "Sampling",
            "Survey", "Geophysics", "Trenching", "Soil", "Channel", "Underground", "Surface", "Airborne", "Maiden",
            "Inaugural", "Delineate", "Potential", "Highgrade", "High-Grade", "Mineralization", "Crews", "Drill-Ready",
            "Receipt", "Permit", "Permits", "Approval", "Approvals", "Ahead", "Area", "Areas", "Strategy", "Achievements",
            "Reviews", "Ready", "First", "Ever", "Exploration", "From", "Recent", "Ongoing", "Additional", "Summer",
            "Winter", "Spring", "Fall", "Q1", "Q2", "Q3", "Q4", "Deep-Test", "Return", "Returns"}


def _clean_proj(name):
    toks = [w for w in name.strip().split()]
    cut = 0
    for i, w in enumerate(toks):
        if w in _HL_VERB or re.match(r"^(?:19|20)\d\d$", w):
            cut = i + 1
    toks = toks[cut:]
    while toks and (toks[0].strip("’'s") in _BAD_PROJ or re.match(r"^\d", toks[0]) or toks[0].endswith(("’s", "'s"))):
        toks = toks[1:]
    while toks and toks[-1] in _BAD_PROJ:
        toks = toks[:-1]
    if not toks:
        return None
    n = " ".join(toks).strip(" -,")
    n = re.sub(r"(?i)^(?:the|its|our)\s+", "", n)
    if len(n) < 2 or n.lower() in ("project", "property"):
        return None
    return n


def _projects(text):
    out = []
    for m in _PROJ_RX.finditer(text):
        n = _clean_proj(m.group(1))
        if n:
            out.append((m.start(), n))
    return out


def _proj_key(n):
    s = unicodedata.normalize("NFKD", n or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    w = [x for x in re.findall(r"[a-z0-9]+", s) if x not in ("the", "project", "property", "gold", "silver", "copper")]
    return w[0] if w else s


def _primary_project(title, body):
    ps = _projects(title)
    counts = {}
    for _p, n in _projects(body):
        counts.setdefault(_proj_key(n), [n, 0])[1] += 1
    if ps:
        n = ps[0][1]
        mt = re.search(re.escape(n) + r"\s+(?:\w+\s+){0,3}?(Mine|Deposit|Prospect|Zone|Target)\b", title)
        if mt and counts:
            best = max(counts.values(), key=lambda v: v[1])
            if _proj_key(best[0]) != _proj_key(n) and best[1] >= 2:
                return best[0]
        return n
    if len(counts) >= 3 and not re.search(r"(?i)\b(?:at|on)\s+(?:the\s+|its\s+)?[A-Z]", title):
        top = sorted(counts.values(), key=lambda v: -v[1])
        if top[0][1] < 2 * top[1][1]:
            return None
    m = re.search(r"(?:at|on|of)\s+(?:the\s+|its\s+)?" + _CAPNAME + r"\s*(?:,|$|\s+in\s+|\s+(?:Area|Zone|Target))", title)
    cands = _projects(body[:4000])
    if cands:
        cnt = {}
        for _p, n in _projects(body):
            k = _proj_key(n)
            cnt[k] = cnt.get(k, 0) + 1
        best = max(cands, key=lambda c: (cnt.get(_proj_key(c[1]), 0), -c[0]))
        return best[1]
    if m:
        return _clean_proj(m.group(1))
    return None


def _project_in(s, projects, primary):
    for _p, n in _projects(s):
        for q in projects:
            if _proj_key(q) == _proj_key(n):
                return q
        return n
    return primary


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


def _hl_status(t):
    for st, rx in _HL_ST:
        if rx.search(t):
            if st == "completed" and re.search(r"(?i)\b(?:update|progress\w*|to\s+date|nearly|so\s+far)\b", t):
                return "underway"
            return st
    return None


def _hl_type(t, body):
    m_d, m_g, m_r = _DRILL.search(t), _GEO.search(t), _GRD.search(t)
    if m_d:
        return "drilling"
    if m_g:
        return "geophysics"
    if m_r:
        return "ground"
    if _EXPLPROG.search(t) or re.search(r"(?i)\bexploration\s+(?:at|on)\b|\bcommences\s+exploration\b", t):
        for s in _sentences(body[:4000])[:8]:
            if re.search(r"(?i)\bprogram|campaign|field\s*work\b", s) and _status(s) and not _HIST.search(s):
                ts = _types(s)
                if ts:
                    return ts[0]
        lead = body[:3000]
        if re.search(r"(?i)\bdrill(?:ing)?\s+(?:program|campaign)|\bdrill\s+holes?\b|\bmetres?\s+of\s+drilling", lead):
            return "drilling"
        if _GEO.search(lead) and not _GRD.search(lead):
            return "geophysics"
        return "ground"
    return None


def _fact_window(sents, i, ptype):
    """The sentence and the next one, when the next continues the same program."""
    s = sents[i]
    if i + 1 < len(sents):
        nxt = sents[i + 1]
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
        r["metres"] = _metres(text, status)
        r["holes"] = _holes(text)
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


def _same_program(a, b):
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
    if bool(ya) != bool(yb) and a["status"] != b["status"]:
        und = a if not ya else b
        oth = b if und is a else a
        return und["status"] == "planned" and oth["status"] in ("started", "underway", "planned")
    return True


_OPERATOR = re.compile(r"(?:by|for)\s+((?:[A-Z][\w&'’.\-]*\s+){0,4}?(?:[A-Z][\w&'’.\-]*)\s+(?:Inc|Corp(?:oration)?|Ltd|"
                       r"Limited|Resources|Mines|Mining|Exploration|Explorations|Gold|Metals|Minerals|Ventures)\.?)")


def _hist_operator(s):
    m = _OPERATOR.search(s)
    if m:
        return m.group(1).strip(" .")
    return "previous owner (unnamed)"


def _nearest(rx, s, a, b, span=110):
    best = None
    for m in rx.finditer(s):
        d = a - m.end() if m.end() <= a else m.start() - b if m.start() >= b else 0
        if d <= span and (best is None or d < best[0]):
            best = (d, m)
    return best[1] if best else None


_WILL = re.compile(r"(?i)\b(?:plan(?:s|ned)?\s+to|expects?\s+to|intends?\s+to|will|to\s+be|would|anticipat\w+\s+to|scheduled\s+to|"
                   r"aims?\s+to|looks?\s+forward\s+to|prepar\w+\s+to|in\s+order\s+to|to)\s+(?:\w+\s+){0,3}$")


def _near_status(s, a, b):
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


# ------------------------------------------------------------------ the reader
def analyse(headline, body):
    h, b = _prepare(headline, body)
    title = _title(h)
    rel_year = _release_year(b)
    b = _drop_title(_undate(b), title)
    title = _undate(title)
    if len(b) < 200 and not title:
        return {"rows": [], "reason": "no text"}
    primary = _primary_project(title, b)
    sents = _sentences(b)
    date_year = None
    rows = []
    reason = None

    # 1. the program the headline is about
    ptype = _hl_type(title, b)
    hl_results = bool(_RESULTS_HL.search(title))
    if ptype and not re.search(r"(?i)\b(?:resource\s+estimate|feasibility|PEA|technical\s+report|production)\b", title):
        st = _hl_status(title)
        if st is None and hl_results:
            st = "completed" if ptype != "drilling" else None
        if st:
            # the body sentences about this program give its facts
            text = title
            for i, s in enumerate(sents[:25]):
                own = _status(s)
                if own and ((own == "completed") != (st == "completed")) and st != "underway":
                    continue
                if ptype in _types(s) and not _HIST.search(s) and not _RESULTS_HL.search(s[:60]):
                    text += " " + _fact_window(sents, i, ptype)
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
    for i, s in enumerate(sents):
        if _NOT_PROGRAM.search(s) and not re.search(r"(?i)drill(?:ing)?\s+program", s):
            continue
        if re.match(r"(?i)^(?:figure|fig\.|table|photo|plate|map|source|note)\b", s):
            continue
        seen = set()
        for t, rx in (("drilling", _DRILL), ("geophysics", _GEO), ("ground", _GRD)):
            m = rx.search(s)
            if not m or t in seen:
                continue
            seen.add(t)
            a0, a1 = max(0, m.start() - 110), min(len(s), m.end() + 110)
            w = s[a0:a1]
            hm = _HIST.search(s)
            hist = bool(hm) and abs(hm.start() - m.start()) < 90
            st = _near_status(s, m.start(), m.end())
            if hist:
                years = sorted(set(y.group(1) for y in _YEAR.finditer(s)
                                   if a0 <= y.start() < a1 and (now is None or int(y.group(1)) < now - 1)
                                   and not re.search(r"(?i)(?:acquir\w*|since|option\w*|staked?)\s+(?:the\s+\w+\s+)?(?:in\s+)?(?:\w+\s+)?$",
                                                     s[max(0, y.start() - 45):y.start()])))
                has_fact = bool(years) or _metres(w) or _holes(w) or _OPERATOR.search(w)
                if not has_fact or (t != "drilling" and not years):
                    continue
                if re.search(r"(?i)\b(?:adjacent|neighbou?ring|nearby|along\s+strike\s+from|government|geological\s+"
                             r"survey|GSC|OGS|provincial)\b", w):
                    continue
                season = years[0] if len(years) == 1 else None
                r = _row(t, _project_in(s, [primary] if primary else [], primary), "completed", w,
                         historical=True, operator=_hist_operator(w), season=season)
                r["season"] = season
                if r["metres"] is None and r["holes"] is None and season is None and r["operator"].startswith("previous"):
                    continue
                r["_src"] = s
                rows.append(r)
                continue
            if st is None:
                continue
            if re.search(r"(?i)\b(?:talks|discussions|negotiat\w*|contractors?\s+to\s+undertake)\b", w) and st != "completed":
                continue
            yr = _near_year(s, m.start(), m.end())
            fact = (yr or _PHASE.search(w) or (t == "drilling" and (_metres(w) or _holes(w))) or
                    (t == "geophysics" and _linekm(w)))
            if not fact:
                continue
            if st != "completed" and yr and now and int(yr[-4:]) < now - 1:
                continue
            if st == "planned" and not re.search(r"(?i)\b(?:program(?:me)?|campaign|survey|drill(?:ing)?)\b", w):
                continue
            text = w
            if t == "drilling" and not (_metres(w) or _holes(w)) and i + 1 < len(sents) and not _types(sents[i + 1])[1:]:
                text = w + " " + sents[i + 1][:200]
            r = _row(t, _project_in(s, [primary] if primary else [], primary), st, text)
            r["season"] = _near_season(s, m.start(), m.end()) or yr
            if t != "drilling" and st == "planned" and not (r["season"] or r["phase"]):
                continue
            r["_src"] = s
            rows.append(r)

    # 3. one row per program
    out = []
    for r in rows:
        if not r["project"]:
            r["project"] = primary
        for o in out:
            if _same_program(o, r):
                _merge(o, r)
                break
        else:
            out.append(r)
    metals = _metal(title + " " + b[:2500])
    for r in out:
        if metals and not r["historical"]:
            r["target_metal"] = "+".join(metals[:2])
    if not out and reason is None:
        reason = "no program with a status and a fact"
    return {"rows": out, "reason": reason, "project": primary}


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
    import hashlib
    h = hashlib.sha1()
    with open(__file__, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


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

    eq("metres not a depth", _metres("to a depth of 450 m below surface"), None)
    eq("metres of drilling", _metres("a 5,000 metre drill program"), 5000.0)
    eq("holes word", _holes("completed five diamond drill holes totalling 2,548 m"), 5)
    eq("line km", _linekm("a 73.5 line-kilometre induced polarization survey"), 73.5)
    eq("phase", _phase("Phase II drilling"), "Phase 2")
    print("exploration self-test: %s" % ("PASS" if not bad else "%d FAILED" % bad))
    return bad == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test("-v" in sys.argv) else 1)
