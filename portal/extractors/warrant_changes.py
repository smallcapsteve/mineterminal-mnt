"""Warrant Changes reader, facts-store version (WCH_V1, 2026-10-07).

What changes a warrant AFTER it is issued: extensions, accelerations (and waivers of them), repricings, early-exercise
incentive programmes, exercises, stated expiries and withdrawn amendments. The Financings reader skips these releases
on purpose (_RE_NOT_FIN_HEAD), so nothing stored them; Mine Terminal Pro's warrant-expiry events only knew closing
date + term. Written against the 50-release key Justin confirmed on 2026-10-07 (rule calls WA-WM,
claude/MNT_EVENTS_READERS_2026-10-07.md).

Justin's rules (2026-10-07):
  WA  warrant terms of an offering that has not closed yet are a financing amendment: no row.
  WB  "subject to acceleration" / "may accelerate" in a financing is a clause, not a notice: no row.
  WC  a waiver of an acceleration right is a row (acceleration_waived); events unchanged.
  WD  an incentive programme is a row with its end date; the incentive warrants it issues are a new series.
  WE  exercises are rows; a series 100% exercised, or whose balance is stated as expired, is retired.
  WF  "intends to / applies to extend", subject to exchange approval, is `proposed` (the site shows the new date,
      labelled "Extension proposed").
  WS  one row per group the release gives a count for; tranche dates kept as lists.
  WM  (publisher) a change finds its financing by ticker + strike + issue date (+-7 days), else ticker + old expiry.

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per row
to_prediction(records) -> dict|None    what the accuracy judge compares

Self-tests: python3 -m portal.extractors.warrant_changes
"""
from __future__ import annotations

import re
from datetime import date, timedelta

try:
    from portal import facts as F
    from portal import fingerprint as FP
except Exception:  # pragma: no cover - standalone development outside the app
    F = FP = None

NAME = "warrant_changes"
VERSION = "1.0.0"
KIND = "warrant_change"
TAG = "Financings"          # no tag of its own; tag_confirmed only records whether the release carries this one
TEXT_CAP = 30000

CHANGES = ("extension", "acceleration", "acceleration_waived", "repricing", "incentive", "exercise", "expired",
           "withdrawn")
TXT_FIELDS = ("change", "status", "issued", "expiry_old", "expiry_new", "program_end", "new_series_expiry")
NUM_FIELDS = ("n_warrants", "strike_old", "strike_new", "n_exercised", "proceeds", "n_remaining", "new_series_n",
              "new_series_strike", "new_series_term_months")

# ------------------------------------------------------------------ text
_TAIL = re.compile(r"(?:\bAbout [A-Z][A-Za-z0-9.&'\- ]{2,60}(?=\s|:)|\bABOUT [A-Z]|Forward[- ]Looking (?:Statements|Information)"
                   r"|FORWARD[- ]LOOKING|Cautionary (?:Note|Statement)|CAUTIONARY|Neither (?:the )?TSX|Neither the Canadian"
                   r"|For further information|FOR FURTHER INFORMATION|For more information,? please contact"
                   r"|ON BEHALF OF THE BOARD|On behalf of the Board|To view the source version"
                   r"|(?i:this\s+news\s+release\s+(?:contains|may\s+contain|includes)\s+(?:certain\s+)?\"?forward)"
                   r"|(?i:CSE\s+has\s+not\s+reviewed)|(?i:neither\s+the\s+(?:TSX|canadian\s+securities|CSE)))")
_WS = re.compile(r"[ \t ​]+")


def _clean(headline, body):
    b = (body or "")[:TEXT_CAP]
    cut = None
    for m in _TAIL.finditer(b):
        if m.start() >= 600:
            cut = m.start()
            break
    if cut is not None:
        b = b[:cut]
    b = b.replace("“", '"').replace("”", '"').replace("’", "'").replace("–", "-").replace("—", "-")
    b = re.sub(r"\b(?:CAN|CA|CAD|Cdn|CDN|C)\s?\$", "$", b)                    # Canadian dollars are the default
    b = re.sub(r"\s*\n\s*", " ", b)
    b = _WS.sub(" ", b)
    b = re.sub(r"(\$\s?\d+)\s(\.\d)", r"\1\2", b)                       # "$0 .10"
    b = re.sub(r"(\$\s?\d+\.\d*)\s(\d{2,4})\b(?![,\d])", r"\1\2", b)     # "US$0.0 588"
    b = re.sub(r"\b([0-3]) (\d)(?=,?\s+(?:19|20)\d\d)", r"\1\2", b)        # "Nov. 0 3, 2022"
    b = re.sub(r"(\d{1,2},?\s+)(20[0-9]) ([0-9])\b", r"\1\2\3", b)            # "October 29, 202 7"
    b = re.sub(r"\b(\d) (\d{1,2},\d{3})\b", r"\1\2", b)                       # "1 0,361,183"
    b = re.sub(r"\b(Ju|Ma|Ap|Au|Se|Oc|No|De|Fe|Ja) ([a-z]{1,6})\s(?=\d)", lambda m: m.group(1) + m.group(2) + " "
               if (m.group(1) + m.group(2)).lower().rstrip(".") in MONTHS or (m.group(1) + m.group(2)).lower()[:3] in _MON_ALT else m.group(0), b)
    for w in _MEND:
        b = w.sub(lambda m: m.group(0).replace(" ", ""), b)
    h = _WS.sub(" ", (headline or "").replace("\n", " ")).strip()
    return h, b.strip()


# words a PDF break split with one space ("e xtended", "pri ce", "warr ants")
_MEND = [re.compile(r"(?i)\b" + " ?".join(w) + r"\b") for w in ("extended", "extension", "warrants", "exercise", "expiry", "exercisable")] + \
        [re.compile(r"(?i)\bpri ce\b"), re.compile(r"(?i)\bsh ares\b")]


_SENT = re.compile(r"(?<=[.;])(?<![ap]\.m\.)(?<!\bNo\.)\s+(?=[A-Z(•\-])|\s+(?=•)|\s+(?=\(?[ivx]{1,4}\)\s)|\s+(?=\([a-f]\)\s)")


def _sentences(t):
    return [s.strip() for s in _SENT.split(t) if s.strip()]


# ------------------------------------------------------------------ numbers and dates
MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"), 1)}
_MON_ALT = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
            "nov": 11, "dec": 12}
_MON = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?"
_ORD = r"(?:\s?(?:st|nd|rd|th)\b)?"
DATE_RX = re.compile(r"(?i)\b(?:(?P<m1>" + _MON + r")\s+(?P<d1>\d{1,2})" + _ORD + r",?\s+(?P<y1>(?:19|20)\d\d)"
                     r"|(?P<d2>\d{1,2})" + _ORD + r"\s+(?:day\s+of\s+)?(?P<m2>" + _MON + r"),?\s+(?P<y2>(?:19|20)\d\d)"
                     r"|(?P<y3>20\d\d)-(?P<mm3>[01]\d)-(?P<d3>[0-3]\d))\b")
# "March 21st and April 7th 2023": two days, one year
DATE_PAIR_RX = re.compile(r"(?i)\b(?P<m1>" + _MON + r")\s+(?P<d1>\d{1,2})" + _ORD + r",?\s+and\s+(?P<m2>" + _MON +
                          r")\s+(?P<d2>\d{1,2})" + _ORD + r",?\s+(?P<y>(?:19|20)\d\d)\b")


def _mon(s):
    s = s.lower().rstrip(".")
    return MONTHS.get(s) or _MON_ALT.get(s) or _MON_ALT.get(s[:3])


def _mk(y, m, d):
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except (TypeError, ValueError):
        return None


def dates_in(s):
    """[(start, end, iso)] for every full date in s, in order."""
    out = []
    for m in DATE_PAIR_RX.finditer(s):
        a = _mk(m["y"], _mon(m["m1"]), m["d1"])
        b = _mk(m["y"], _mon(m["m2"]), m["d2"])
        if a:
            out.append((m.start(), m.start("m2"), a))
        if b:
            out.append((m.start("m2"), m.end(), b))
    taken = [(a, b) for a, b, _ in out]
    for m in DATE_RX.finditer(s):
        if any(a <= m.start() < b for a, b in taken):
            continue
        if m["m1"]:
            v = _mk(m["y1"], _mon(m["m1"]), m["d1"])
        elif m["m2"]:
            v = _mk(m["y2"], _mon(m["m2"]), m["d2"])
        else:
            v = _mk(m["y3"], m["mm3"], m["d3"])
        if v:
            out.append((m.start(), m.end(), v))
    return sorted(out)


_NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
COUNT_RX = re.compile(r"(?i)\b" + _NUM + r"(\s*(?:million|M)\b)?\s+(?:\w+[\s-]+){0,9}?(?:warrants?)\b")


def _num(s, scale=None):
    v = float(s.replace(",", ""))
    if scale and scale.strip().lower() in ("million", "m"):
        v *= 1e6
    return v


def counts_in(s):
    out = []
    for m in COUNT_RX.finditer(s):
        pre = s[max(0, m.start() - 12):m.start()]
        if re.search(r"[$]\s*$|\bUS\$\s*$", pre):
            continue
        between = s[m.end(1):m.end()]
        if re.search(r"(?i)\b(?:finder|broker|compensation|agent|options?|shares\s+of|years?|months?|days?|per\s+cent|percent|%)\b", between):
            continue
        v = _num(m.group(1), m.group(2))
        if "," not in m.group(1) and not m.group(2) and 1900 <= v <= 2100:
            continue
        if v >= 1000 or (m.group(2)):
            out.append((m.start(), v))
    return out


PRICE_RX = re.compile(r"(?i)(?:C\$|CDN\$|CAD\s*\$?|US\$|USD\s*\$?|\$)\s?(\d+(?:\.\d+)?|\.\d+)(?:\s*(?:per|a)\s+(?:common\s+)?(?:share|Common Share|Share|Warrant Share))?")


def prices_in(s):
    return [(m.start(), float(m.group(1)), m.group(0)) for m in PRICE_RX.finditer(s)]


def _strike_in(s):
    """The exercise price a warrant sentence states (warrant wording first, then a bare 'at a price of')."""
    for rx in (r"(?i)exercise\s+price\s+(?:of\s+)?(?:C\$|CDN\$|CAD\s?\$?|US\$|USD\s?\$?|\$)\s?(\d*\.\d+|\d+(?:\.\d+)?)",
               r"(?i)exercisable\s+(?:\w+\s+){0,6}?at\s+(?:a\s+price\s+of\s+)?(?:C\$|CDN\$|CAD\s?\$?|US\$|USD\s?\$?|\$)\s?(\d*\.\d+|\d+(?:\.\d+)?)"):
        m = re.search(rx, s)
        if m:
            return float(m.group(1))
    if re.search(r"(?i)prices?\s+ranging\s+(?:between|from)\s+\$", s):
        return None
    m = re.search(r"(?i)(?:purchase|acquire)\s+one\s+(?:additional\s+)?(?:\w+\s+){0,3}(?:common\s+)?share[^$]{0,80}?at\s+a\s+price\s+of\s+(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+)", s)
    if m:
        return float(m.group(1))
    m = re.search(r"(?i)(?:exercisable|to\s+purchase)[^.$]{0,90}?\b(?:at|for)\s+(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+|\d+(?:\.\d+)?)", s)
    if m:
        return float(m.group(1))
    m = re.search(r"(?i)(?:at|priced\s+at)\s+(?:an?\s+(?:exercise\s+)?price\s+of\s+)?(?:C\$|CDN\$|CAD\s?\$?|US\$|USD\s?\$?|\$)\s?"
                  r"(\d*\.\d+|\d+(?:\.\d+)?)", s)
    if m:
        return float(m.group(1))
    m = re.search(r"(?i)(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+|\d+(?:\.\d+)?)\s+per\s+(?:common\s+)?(?:share|Common Share|Warrant Share)", s)
    return float(m.group(1)) if m else None


def _strikes_stated(s):
    """Distinct exercise prices a text states for warrants."""
    return sorted({float(x) for x in re.findall(r"(?i)exercisable\s+at\s+(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+)", s)})


def _date_run(s, pos, lead=18):
    """The dates that start within `lead` characters of pos, joined by 'and' / commas / 'respectively'."""
    ds = dates_in(s[pos:pos + 260])
    if not ds or ds[0][0] > lead:
        return []
    got, last = [ds[0][2]], ds[0][1]
    seg = s[pos:pos + 260]
    for a, b, v in ds[1:]:
        if re.fullmatch(r"\s*,?\s*(?:and\s+|&\s+)?(?:,\s*)?", seg[last:a]):
            got.append(v)
            last = b
        else:
            break
    return got


MONEY_RX = re.compile(r"(?i)(?:C\$|CDN\$|CAD\s*\$|US\$|USD\s*\$?|\$)\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(million|M\b)?")


def _money(s):
    m = MONEY_RX.search(s)
    if not m:
        return None
    return _num(m.group(1), m.group(2))


# ------------------------------------------------------------------ cues
_W = r"(?:(?:common\s+)?share\s+purchase\s+|incentive\s+|outstanding\s+|eligible\s+|the\s+|its\s+|of\s+)*warrants?"
CUE = {
    "acceleration_waived": re.compile(r"(?i)\bwaive[sd]?\b[^.]{0,80}\baccelerat|\bwill\s+not\s+(?:exercise\s+its\s+right\s+to\s+)?accelerate\b"),
    "acceleration": re.compile(r"(?i)\b(?:(?:has\s+)?elect(?:ed|ing|s)\s+to\s+accelerate|is\s+exercising\s+its\s+right\s+to\s+accelerate|"
                               r"exercised\s+its\s+right\s+to\s+accelerate|hereby\s+provides\s+notice|this\s+news\s+release\s+constitutes\s+notice|"
                               r"accelerated\s+expiry\s+date|expiry\s+date\s+of\s+the\s+warrants\s+was\s+accelerated|"
                               r"completed\s+the\s+acceleration|following\s+(?:the\s+)?(?:company's\s+)?(?:previously\s+announced\s+)?(?:warrant\s+(?:expiry\s+)?)?acceleration|"
                               r"pursuant\s+to\s+(?:its|the)\s+(?:recent\s+)?notice\s+of\s+warrant\s+acceleration|"
                               r"now\s+be\s+subject\s+to\s+their\s+accelerat\w*\s+(?:exercise\s+)?clause|which\s+now\s+expire\s+\w+\s+\d|"
                               r"(?:has|have)\s+been\s+accelerated|is\s+being\s+accelerated|acceleration\s+(?:clause|provision|right)\s+(?:has\s+been|was)\s+triggered|"
                               r"exercise\s+period\s+of\s+the\s+warrants\s+(?:is|has\s+been)\s+reduced|warrants\s+will\s+now\s+expire)"),
    "extension": re.compile(r"(?i)\b(?:extend(?:s|ed|ing)?\s+(?:the\s+)?(?:expiry|exercise\s+period|exercise\s+term|term|expiration|expiry\s+dates?)\b|"
                            r"extension\s+of\s+(?:the\s+)?(?:original\s+)?(?:expiry|term|exercise|warrants)|extension\s+of\s+(?:\w+\s+){1,2}warrants|warrant\s+(?:term\s+)?extension|"
                            r"(?:modify|amend)\s+the\s+(?:expiry|exercise\s+term|exercise\s+period)|"
                            r"proposed\s+expiry\s+of\s+the\s+warrants\s+will\s+be\s+amended|amended\s+expiry\s+dates?|"
                            r"extend\s+(?:the\s+)?(?:\w+\s+){0,3}warrants|one-year\s+extension|extension,?\s+by\s+one\s+year|"
                            r"(?:has|have)\s+been\s+extended\s+(?:from|to|for|by|until)|extends?\s+(?:[\w,.$]+\s+){0,3}warrants|"
                            r"amend(?:s|ed|ing)?\s+the\s+(?:expiry|term|exercise\s+term|exercise\s+period)|extend\s+(?:the\s+)?warrant\s+(?:expiry|term)|"
                            r"(?:will\s+be|is|are)\s+extended\s+by|amends?\s+warrants\s+to\s+extend)"),
    "repricing": re.compile(r"(?i)\b(?:(?<!were\s)(?<!was\s)repric(?:e|es|ed|ing)\b|reduce\s+the\s+exercise\s+price|"
                            r"amend(?:s|ed|ing|ment\s+of)?\s+the\s+(?:warrant\s+)?exercise\s+price)"),
    "incentive": re.compile(r"(?i)\b(?:(?:warrant\s+)?(?:exercise\s+)?incentive\s+program(?:me)?|early\s+(?:warrant\s+)?exercise\s+(?:incentive\s+)?(?:period|program)|early\s+incentive\s+program)"),
    "exercise": re.compile(r"(?i)\b(?:(?:have|has|had)\s+been\s+exercised|(?:were|was)\s+exercised|exercise\s+of\s+(?:an\s+aggregate\s+of\s+)?\d[\d,]*\s+(?:\w+\s+){0,4}warrants|"
                           r"(?:from|following)\s+the\s+(?:early\s+)?exercise\s+of\s+(?:the\s+)?warrants|^exercise\s+of\s+(?:all\s+)?warrants|"
                           r"(?<!assuming\s)exercise\s+of\s+all\s+warrants|warrants?\s+exercises|holders\s+exercised|exercised\s+an\s+aggregate|"
                           r"following\s+an\s+exercise\s+of|following\s+the\s+early\s+exercise|"
                           r"exercise\s+by\s+(?:[A-Z][\w.&-]*\s+){1,5}(?:\([^)]*\)\s+)?of\s+\d[\d,]*\s+(?:\w+\s+){0,4}warrants|exercise\s+of\s+warrants\s+over\s+\d|"
                           r"(?:received|raised)\s+(?:\w+\s+){0,3}(?:through|from)\s+the\s+exercise\s+of\s+(?:\w+\s+){0,2}warrants|has\s+been\s+received\s+through\s+the\s+exercise)"),
    "withdrawn": re.compile(r"(?i)\b(?:will\s+not\s+be\s+proceeding|not\s+(?:be\s+)?proceed(?:ing)?\s+with|withdraw(?:s|n)?)\b[^.]{0,200}\b(?:amendment|repricing|extension|exercise\s+price)"),
}
WARRANT = re.compile(r"(?i)\bwarrants?\b")
H_ACC = re.compile(r"(?i)accelerat\w*\s+(?:of\s+)?(?:the\s+)?(?:\w+\s+){0,2}(?:warrant|expiry)|warrant\s+(?:expiry\s+)?(?:date\s+)?acceleration")
ACC_NOTICE = re.compile(r"(?i)\bhereby\b|\belect(?:ed|ing)\s+to\s+accelerate|\b(?:is\s+exercising|has\s+exercised|exercised)\s+its\s+right\s+to\s+accelerate|"
                        r"constitutes\s+notice|completed\s+the\s+acceleration|following\s+(?:the\s+)?(?:company's\s+)?(?:previously\s+announced\s+)?"
                        r"(?:warrant\s+)?(?:expiry\s+)?acceleration\b|will\s+now\s+be\s+subject\s+to\s+their\s+accelerat|which\s+now\s+expire|"
                        r"accelerated\s+to\s+(?:5:00|\d{1,2}:\d{2}|twenty|thirty|\(?\d+\)?\s+(?:calendar\s+)?days)|(?:has|have)\s+been\s+(?:accelerated|triggered)|"
                        r"is\s+being\s+accelerated|will\s+now\s+expire|provides\s+notice")
CLAUSE = re.compile(r"(?i)\b(?:may\s+(?:elect\s+to\s+)?accelerate|subject\s+to\s+(?:an?\s+|the\s+)?(?:early\s+)?acceleration|right\s+to\s+accelerate|"
                    r"entitled\s+to\s+accelerate|will\s+have\s+the\s+right|in\s+the\s+event\s+that|acceleration\s+(?:provision|clause|right|trigger)|"
                    r"if\s+(?:,\s+)?(?:after|at\s+any\s+time|the\s+(?:daily\s+|volume|closing))|may\s+be\s+accelerated|"
                    r"provided\s+that\s+if|is\s+subject\s+to\s+acceleration|accelerating\s+the\s+development|to\s+accelerate\s+(?:exploration|drilling|development)|"
                    r"subject\s+to\s+an?\s+accelerated|comes\s+into\s+effect\s+at\s+such\s+time|will\s+contain\s+an\s+acceleration|shall\s+be\s+entitled\s+to\s+accelerate|"
                    r"\bif\b[^.]{0,60}\belects?\s+to\s+accelerate|any\s+such\s+accelerat|will\s+announce|must\s+(?:also\s+)?be\s+(?:amended|announced)|"
                    r"would\s+be\s+(?:modified|reduced|accelerated)|can\s+be\s+accelerated|shall\s+be\s+accelerated\s+in\s+accordance|\bif\s+required|as\s+amended,\s+will\s+be\s+subject)")
NEW_OFFERING = re.compile(r"(?i)\b(?:to\s+be\s+issued\s+(?:under|pursuant\s+to)\s+the\s+(?:offering|placement)|"
                          r"previously\s+announced\s+(?:non-brokered\s+)?(?:private\s+placement|offering)\s*\([^)]*\)\s*\.?\s*the\s+company\s+has\s+extended|"
                          r"amendment\s+to\s+the\s+terms\s+of\s+its\s+(?:non-brokered\s+)?(?:private\s+placement|offering)|"
                          r"will\s+now\s+be\s+exercisable\s+for\s+a\s+period\s+of\s+\d+\s+months\s+from\s+the\s+date\s+of\s+issuance)")
PROPOSED = re.compile(r"(?i)\b(?:intends?\s+to|proposes?\s+to|proposed|propose\b|applied\s+to|applying\s+to|has\s+made\s+application|made\s+application|application\s+to|"
                      r"apply\s+to|will\s+file\s+an\s+application|file\s+an\s+application|wishes\s+to|is\s+intending|"
                      r"subject\s+to\s+(?:the\s+)?(?:final\s+)?(?:approval|acceptance)\s+(?:of|by|from)\s+the\s+(?:TSX|exchange|CSE|canadian)|"
                      r"remains\s+subject\s+to\s+(?:the\s+)?(?:final\s+)?(?:approval|acceptance)|"
                      r"upon\s+(?:the\s+)?approval\s+of\s+the\s+TSX|subject\s+to\s+TSX\s+Venture\s+Exchange\s+(?:acceptance|approval)|"
                      r"subject\s+to\s+(?:the\s+)?(?:TSXV|TSX-V|TSX\.V|CSE|exchange)\s+(?:acceptance|approval)|subject\s+to\s+(?:the\s+)?(?:approval|acceptance|consent)\s+(?:of|by)\s+the\s+(?:TSXV|TSX-V|warrant\s*holders|holders)|"
                      r"subject\s+to\s+(?:the\s+)?(?:consent|approval)\s+of\s+(?:the\s+)?warrant|awaits?\s+(?:final\s+)?approval|"
                      r"proposes\b|subject\s+to\s+(?:all\s+)?(?:required\s+)?regulatory\s+(?:approval|acceptance)|seeks\s+(?:an\s+)?extension|is\s+seeking\s+to)")
EFFECTIVE = re.compile(r"(?i)\b(?:was|has\s+been|were|have\s+been)\s+(?:accepted|approved)\s+by\s+the\s+(?:TSX|exchange|CSE|canadian)|"
                       r"received\s+(?:final\s+)?(?:approval|acceptance)\s+from\s+the\s+(?:TSX|exchange|CSE|canadian)|"
                       r"(?:has|have)\s+been\s+extended\s+to|(?:are|is)\s+now\s+(?:extended|set\s+to\s+expire)|has\s+extended\s+the\s+expiry|"
                       r"have\s+been\s+extended\s+for|announces\s+the\s+extension\s+of\s+the\s+warrant\s+expiry")
DONE = re.compile(r"(?i)\b(?:completed|closes|closed|close\s+of|completion\s+of|received\s+proceeds|receives\s+\$|were\s+exercised|have\s+been\s+exercised|"
                  r"expired\s+unexercised|announces\s+the\s+close)\b")


INC_DONE = re.compile(r"(?i)\b(?:complet(?:ed|es|ion\s+of)|clos(?:es|ed|ing\s+of)|close\s+of)\s+(?:its\s+|the\s+)?(?:\w+\s+){0,5}?(?:incentive\s+)?program|"
                      r"\bwere\s+exercised|have\s+been\s+exercised|received\s+proceeds|expiring\s+unexercised|proceeds\s+from\s+warrant\s+incentive|"
                      r"has\s+completed\s+its\s+warrant")


# ------------------------------------------------------------------ analysis
_DEFINED = re.compile(r"(?i)\((?:the\s+|each,?\s+an?\s+)?\"[^\"]{0,40}\"\)|\(please\s+see[^)]*\)")
_HISTORY = re.compile(r"(?i)\s*On\s+\w+\.?\s+\d{1,2},?\s+\d{4},?\s+(?:the\s+company\s+)?announced")


def _cue_kinds(h, sents):
    """{kind: [sentence indexes]} for sentences that state a change to existing warrants (headline = index -1)."""
    found = {}
    allsents = [h] + sents
    for i, s in enumerate(allsents):
        if not WARRANT.search(s) and not re.search(r"(?i)incentive\s+program|early\s+exercise\s+period|accelerated\s+expiry", s):
            continue
        # defined terms and cross-references are not statements: (the "Warrant Repricing"), (please see ...)
        s = _DEFINED.sub(" ", s)
        history = i > 0 and _HISTORY.match(s)
        for k, rx in CUE.items():
            if not rx.search(s):
                continue
            if history and not rx.search(h):
                continue
            if k == "repricing" and i > 0 and not re.search(r"(?i)\$|\brepric(?:e|es|ed)\b|repricing\s+of|(?:reduce|amend\w*)\s+the\s+(?:warrant\s+)?exercise\s+price", s):
                continue
            if k == "repricing" and i > 0 and re.search(r"(?:the|Warrant)\s+Repricing\b", s) and not re.search(
                    r"(?i)\brepric(?:e|es|ed)\b|repricing\s+of|(?:reduce|amend\w*)\s+the\s+(?:warrant\s+)?exercise\s+price|\bto\s+\$", s):
                continue
            if k == "incentive" and re.search(r"(?i)(?:were\s+)?issued\s+(?:on\s+\w+\s+\d{1,2},?\s+\d{4}\s+)?(?:under|pursuant\s+to|in\s+connection\s+with)\s+"
                                             r"(?:the\s+company's\s+)?(?:\w+\s+){0,4}incentive\s+program", s):
                continue
            if k == "acceleration" and CLAUSE.search(s) and not ACC_NOTICE.search(s):
                continue
            if k == "exercise" and re.search(r"(?i)\bno\s+(?:\w+\s+){0,6}warrants|assuming\s+(?:the\s+)?exercise|issuable\s+upon\s+the\s+exercise|"
                                             r"special\s+warrants|upon\s+the\s+exercise\s+of|if\s+all\s+(?:of\s+the\s+)?warrants", s):
                continue
            if k == "extension" and re.search(r"(?i)price\s+protection|clos(?:e|ing)\s+(?:date|of\s+the\s+(?:offering|placement|second|first))|"
                                              r"the\s+offer\b|partial\s+revocation|take-?over|incentive\s+program|early\s+exercise\s+period|"
                                              r"early\s+incentive", s) \
                    and not re.search(r"(?i)expiry\s+date\s+of\s+(?:the\s+)?(?:\w+\s+){0,3}warrants|extend\s+the\s+expiry", s):
                continue
            found.setdefault(k, []).append(i - 1)
    return found


def _status(text, kind):
    if kind in ("exercise", "expired", "withdrawn", "acceleration", "acceleration_waived"):
        return "effective"
    if kind == "incentive":
        if INC_DONE.search(text):
            return "effective"
        return "proposed" if re.search(r"(?i)subject\s+to\s+(?:the\s+)?(?:\w+\s+){0,3}(?:approval|acceptance)|upon\s+(?:the\s+)?approval|granting\s+the\s+extension|"
                                       r"applied\s+for\s+(?:a|an|the)\s+(?:\w+\s+){0,3}incentive|awaits?\s+(?:final\s+)?approval|proposed\s+incentive|"
                                       r"if\s+it\s+obtains|will\s+institute", text) \
            and not re.search(r"(?i)pleased\s+to\s+announce\s+the\s+initiation", text) else "effective"
    if EFFECTIVE.search(text):
        return "effective"
    return "proposed" if PROPOSED.search(text) else "effective"


def _issued_dates(s):
    """Dates the release gives for the ORIGINAL financing (closed / issued / completed on)."""
    out = []
    for m in re.finditer(r"(?i)(?:originally\s+issued\s+(?:by\s+the\s+company\s+)?(?:on\s+)?|warrants\s+granted\s+on\s+|issued\s+(?:on\s+)?|that\s+closed\s+(?:on\s+)?|which\s+closed\s+(?:on\s+)?|closed\s+on\s+|"
                         r"completed\s+on\s+|closing\s+of\s+a\s+private\s+placement\s+on\s+|pursuant\s+to\s+(?:a\s+)?(?:non-brokered\s+)?(?:private\s+placements?|financings?)\s+(?:that\s+)?closed\s+(?:on\s+)?|"
                         r"private\s+placement\s+completed\s+on\s+|tranches\s+of\s+(?:the\s+|a\s+)?private\s+placement\s+which\s+closed\s+on\s+|"
                         r"in\s+connection\s+with\s+the\s+company's\s+|(?:private\s+)?placement\s+dated\s+|"
                         r"(?:in\s+four\s+tranches\s+)?\(please\s+see[^)]*?dated\s+)", s):
        if re.match(r"(?i)completed|closed", m.group(0)) and \
                re.search(r"(?i)consolidation|split|program(?:me)?\s+(?:was\s+)?$|acquisition|transaction\s+$", s[max(0, m.start() - 70):m.start()]):
            continue
        out.extend(_date_run(s, m.end(), lead=6))
    seen, res = set(), []
    for v in out:
        if v not in seen:
            seen.add(v)
            res.append(v)
    return res


def _from_to(s):
    """(old, new) from 'from DATE to DATE' / 'DATE ... to DATE' / 'until DATE will be exercisable until DATE'."""
    ds = dates_in(s)
    m = re.search(r"(?i)\bfrom\s+(.{0,40}?)\s+(?:to|until)\s+", s)
    if m and len(ds) >= 2:
        for i in range(len(ds) - 1):
            a, b, v = ds[i]
            if m.start() <= a <= m.end() + 5:
                return v, ds[i + 1][2]
    m = re.search(r"(?i)\buntil\s+5:00\s*pm\s+on\s+(.+?)\s+will\s+be\s+exercisable\s+until", s)
    if m and len(ds) >= 2:
        return ds[0][2], ds[1][2]
    return None, None


def _new_dates_after(s, rx):
    m = re.search(rx, s)
    if not m:
        return []
    return _date_run(s, m.end(), lead=40)


def _expiry_old(s):
    m = re.search(r"(?i)previously\s+extended[^.]{0,60}?\bto\s+", s)
    if m:
        run = _date_run(s, m.end(), lead=4)
        if run:
            return run[0]
    m = re.search(r"(?i)(?:due\s+to\s+expire|set\s+to\s+expire|(?:were|was)\s+(?:originally\s+|initially\s+)?(?:set\s+to\s+)?expire|"
                  r"with\s+an\s+expiry\s+date\s+of|expiring|expire[sd]?\s+on|until)\s+(?:on\s+)?", s)
    if not m:
        return None
    ds = dates_in(s[m.end():m.end() + 60])
    return ds[0][2] if ds and ds[0][0] < 12 else None


# ------------------------------------------------------------------ generic group reading (r5)
# Every date in a change passage gets a role from the nearest keyword before it: NEW (the changed expiry),
# OLD (the expiry before the change) or ISS (when the series was issued). Counts of warrants split the passage
# into series; dates and prices are then read per series, or shared when the passage states them once.
_MONX = r"(?=(?:" + _MON + r")\s*\d|\d{1,2}(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?(?:" + _MON + r"))"
_KW = [
    ("NEW", r"\bto\s+(?=(?:" + _MON + r")\s*\d|\d|a\s+new|the\s+new)"),
    ("NEW", r"(?:falls|fall)\s+on\s+"),
    ("NEW", r"new\s+(?:warrant\s+)?expiry\s+dates?(?:\s+(?:for|of)\s+(?:the\s+|these\s+|such\s+)?(?:\w+\s+){0,2}warrants)?(?:\s+(?:will\s+be|is|are|of|being|shall\s+be))?\s*"),
    ("NEW", r"amended\s+expiry\s+dates?(?:\s+(?:of|being|will\s+be))?\s*"),
    ("NEW", r"(?:will\s+)?now\s+(?:set\s+to\s+)?expire(?:\s+(?:on|at))?\s*"),
    ("NEW", r"will\s+(?:then\s+)?expire\s+(?:if\s+(?:not\s+)?(?:unexercised\s+|exercised\s+)?)?(?:by|on|at)\s+"),
    ("NEW", r"accelerated\s+(?:expiry\s+date\s+(?:of|is|will\s+be)\s+|to\s+)"),
    ("NEW", r"(?:has|have|will\s+be|be|is|are)\s+extended\s+(?:\w+\s+){0,3}?to\s+"),
    ("NEW", r"new\s+expiry\s+date\s+of\s+"),
    ("OLD", r"\bfrom\s+(?=(?:" + _MON + r")\s*\d)"),
    ("OLD", r"(?:original|current|present|existing)\w*\s+expiry\s+dates?\s+(?:of|is|was)?\s*"),
    ("OLD", r"expir(?:y|ation)\s+(?:date|time)?\s*(?:of|on|is|was)?\s*"),
    ("OLD", r"expir(?:ing|es|ed|e)\s+(?:on\s+)?"),
    ("OLD", r"(?:set|due|scheduled)\s+to\s+expire\s+(?:on\s+)?"),
    ("OLD", r"bear\s+an\s+expiry\s+date\s+of\s+"),
    ("ISS", r"issued\s+(?:on\s+|in\s+)?"),
    ("ISS", r"(?:closed|completed|closing)\s+(?:on\s+)?"),
    ("ISS", r"tranches\s+on\s+"),
    ("ISS", r"(?:placements?|financings?|certificates?|indenture)\s+(?:\w+\s+){0,2}?(?:dated|on)\s+"),
    # dates of other acts: they end any expiry / issue phrase before them
    ("NONE", r"(?:amended|announced|approved|accepted|signed|entered\s+into|(?:news|press)\s+releases?)\s+(?:on\s+|dated\s+|of\s+)?"),
    ("NONE", r"trading\s+days?\s+(?:ended|ending)\s+(?:on\s+)?|as\s+of\s+"),
]
_KW = [(role, re.compile(r"(?i)" + rx)) for role, rx in _KW]
_PRIO = {"NEW": 3, "ISS": 2, "OLD": 1, "NONE": 0}


def _runs(s):
    """[(start, end, [iso...])] - dates joined by 'and' / commas form one run."""
    ds = dates_in(s)
    out = []
    for a, b, v in ds:
        if out and re.fullmatch(r"\s*(?:,\s*(?:and\s+)?|and\s+|&\s+)?", s[out[-1][1]:a]):
            out[-1] = (out[-1][0], b, out[-1][2] + [v])
        else:
            out.append((a, b, [v]))
    return out


def _roles(s, kind):
    """[(start, end, [iso...], role)] for every date run in s (role None when no keyword is near)."""
    out, lo = [], 0
    for a, b, vs in _runs(s):
        win_lo = max(lo, a - 110)
        win = s[win_lo:a]
        best = None
        for role, rx in _KW:
            for m in rx.finditer(s, win_lo, min(len(s), a + 40)):
                if m.end() > a:
                    break
                key = (m.end() - win_lo, _PRIO[role])
                if best is None or key > best[0]:
                    best = (key, role, m)
        role = None
        if best is not None and len(win) - best[0][0] <= 48 and not re.search(r"[;]", win[best[0][0]:]) and best[1] != "NONE":
            role = best[1]
            kw = best[2].group(0).lower()
            pre = s[max(0, best[2].start() - 160):best[2].start()]
            if role == "ISS" and re.match(r"(?:closed|completed|closing)", kw) and (not re.search(
                    r"(?i)placement|financing|offering|tranche|units|issuance|warrants", pre[-120:]) or re.search(
                    r"(?i)consolidation|split|program|acquisition|transaction", pre[-70:])):
                role = None
            if role == "ISS" and re.match(r"issued", kw) and re.search(r"(?i)(?:news|press)\s+releases?\s*$", pre):
                role = None
        # 'until': the changed date after an extension verb or 'now'; otherwise the current expiry
        m = re.search(r"(?i)\buntil\s+(?:\d{1,2}:\d{2}\s*[ap]\.?m\.?\s*(?:\([^)]*\)\s*)?(?:on\s+)?)?(?:\w+day,?\s+)?$", win)
        if m and (best is None or win_lo + m.start() >= best[2].start()):
            ctx = s[max(0, win_lo + m.start() - 90):win_lo + m.start()]
            if re.search(r"(?i)current|present|original|as\s+they\s+existed|on\s+their", ctx):
                role = "OLD"
            elif kind == "acceleration" or re.search(r"(?i)\bnow\b|extended|\bextend|will\s+be\s+exercisable|amended\s+to", ctx):
                role = "NEW"
            elif kind in ("repricing", "extension", "incentive"):
                role = "OLD"
        # a dateline ('( January 3rd, 2020) -', 'August 17, 2020 - Vancouver') is the release date, not a warrant date
        if re.match(r"\s*\)?\s*(?:[-–—/]\s|--|\(GLOBE|/CNW)", s[b:b + 14]) or re.search(r"\(\s*$", s[max(0, a - 3):a]):
            role = None
        out.append((a, b, vs, role))
        lo = b
    return out


_WORDN = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "eleven": 11, "twelve": 12, "eighteen": 18, "twenty-four": 24, "thirty": 30, "thirty-six": 36, "sixty": 60,
          "ninety": 90, "a": 1, "another": 1, "an": 1}


def _offset(s):
    """(n, unit) from 'extended by an additional twelve (12) months' / 'for an additional 2 years' / 'by another year'."""
    m = re.search(r"(?i)(?:extend\w*|extension|extended|term)\b[^.;]{0,140}?\b(?:by|for)\s+(?:a\s+(?:further\s+|period\s+of\s+)|an\s+additional\s+|an\s+extra\s+|"
                  r"a\s+further\s+|another\s+|additional\s+|a\s+period\s+of\s+)?(?:period\s+of\s+)?(\d+|[a-z]+(?:-[a-z]+)?)\s*(?:\(\d+\)\s*)?(years?|months?|days?)\b", s)
    if not m:
        m = re.search(r"(?i)(?:extend\w*|extended)\b[^.;]{0,60}?\bby\s+(another|a|one)\s+(year)\b", s)
    if not m:
        return None
    w = m.group(1).lower()
    n = int(w) if w.isdigit() else _WORDN.get(w)
    if not n:
        return None
    return n, m.group(2).lower().rstrip("s")


def _shift(iso, off):
    if not iso or not off:
        return None
    y, mth, d = (int(x) for x in iso.split("-"))
    n, unit = off
    if unit == "day":
        return (date(y, mth, d) + timedelta(days=n)).isoformat()
    if unit == "year":
        y += n
    else:
        mth += n
        y += (mth - 1) // 12
        mth = (mth - 1) % 12 + 1
    for dd in (d, 30, 29, 28):
        v = _mk(y, mth, min(d, dd))
        if v:
            return v
    return None


COUNT2_RX = re.compile(r"(?i)(?:of\s+which|a\s+further|and)\s+(\d{1,3}(?:,\d{3})+)\s+(?:are|were|will|have|has)\b")
_OFFERING_SENT = re.compile(r"(?i)\beach\s+(?:full\s+|whole\s+)?unit\b|\bunits?\s+(?:priced|at\s+a\s+price)|per\s+unit|\bthe\s+offering\s+consists|"
                            r"over-allotment|finder'?s?\s+fee|stock\s+options|restricted\s+share\s+units|\beach\s+(?:full\s+|whole\s+)?warrant\b[^.]{0,220}?(?:from\s+the\s+(?:date\s+of\s+)?clos|"
                            r"of\s+the\s+offering|following\s+the\s+clos|from\s+the\s+date\s+of\s+issu|months\s+from|years\s+from)")


def _zone(sents, idxs, cue_rx=None):
    """The change passage: each cue sentence and the two after it (offering terms left out unless they carry the cue)."""
    keep = []
    for i in idxs:
        if i < 0:
            continue
        hi = min(len(sents), i + 4)
        while hi < len(sents) and re.match(r"\s*(?:\(?[ivx]{1,4}\)|\([a-f]\)|•|-\s)", sents[hi]):
            hi += 1                      # a list that continues the passage
        for j in range(max(0, i - 1), hi):
            s = sents[j]
            if j != i and _OFFERING_SENT.search(s) and not (cue_rx and cue_rx.search(s)):
                continue
            if j == i - 1 and not (WARRANT.search(s) and (counts_in(s) or "$" in s or dates_in(s))):
                continue
            if j not in keep:
                keep.append(j)
    return " ".join(sents[j] for j in sorted(keep))


def _zone_counts(z):
    """Distinct warrant counts in the passage, in order, without aggregates, holdings and restatements."""
    found = [(p, v) for p, v in counts_in(z)] + [(m.start(1), _num(m.group(1))) for m in COUNT2_RX.finditer(z)]
    found.sort()
    out = []
    for p, v in found:
        pre = z[max(0, p - 70):p]
        if re.search(r"(?i)\b(?:hold|holds|held|insiders?|related\s+part\w*|up\s+to|assuming|remaining|balance\s+of\s+(?:the\s+)?)\s*(?:\w+\s+){0,4}$", pre):
            continue
        if re.search(r"(?i)(?:agents?|brokers?|finders?|compensation)'?\s*$", pre) or re.search(r"\d[-.)]\s?$", pre):
            continue
        if re.match(r"(?i)[\d,]*\s+(?:\w+\s+){0,3}?(?:warrants?\s+)?(?:are|is|were)\s+(?:held|owned|beneficially)", z[p:p + 60]):
            continue
        if any(abs(v - w) < 0.5 for _, w in out):
            continue
        out.append((p, v))
    if len(out) >= 3:
        for k, (p, v) in enumerate(out):
            rest = sum(w for j, (_, w) in enumerate(out) if j != k)
            if abs(rest - v) < 0.5:
                out.pop(k)
                break
    if len(out) == 2 and out[0][1] > out[1][1] and re.search(r"(?i)of\s+which\s*$|of\s+these\s*$", z[max(0, out[1][0] - 20):out[1][0]]):
        out.pop(0)
    return out


def _first(roles, want):
    for a, b, vs, r in roles:
        if r == want:
            return vs
    return []


def _all(roles, want):
    return [v for a, b, vs, r in roles if r == want for v in vs]


def _strike_new_in(s):
    for rx in (r"(?i)(?:repric\w*|amend\w*|reduc\w*|chang\w*)\s+(?:the\s+)?(?:\w+\s+){0,12}?(?:exercise\s+)?price[^.]{0,120}?\bto\s+(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+)",
               r"(?i)(?:repric\w*|reduc\w*)\s+(?:the\s+|these\s+|such\s+)?(?:\w+\s+){0,12}?warrants?[^.]{0,80}?\bto\s+(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+)",
               r"(?i)will\s+have\s+an\s+(?:amended\s+)?exercise\s+price\s+of\s+(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+)",
               r"(?i)(?:new|amended|reduced)\s+exercise\s+price\s+(?:of|will\s+be|is)\s+(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+)",
               r"(?i)\bfrom\s+(?:C\$|CDN\$|US\$|\$)\s?\d*\.\d+[^.$]{0,60}?\bto\s+(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+)"):
        m = re.search(rx, s)
        if m:
            return float(m.group(1)), m.start(1)
    return None, None


_TRIGGER = re.compile(r"(?i)volume[\s-]+weighted|closing\s+price|consecutive\s+trading|in\s+excess\s+of|at\s+or\s+above|threshold|\bVWAP\b|trades?\s+(?:at|above)")


def _strike_free(s):
    """The exercise price, ignoring sentences that only state an acceleration trigger price."""
    keep = [x for x in _sentences(s) if not _TRIGGER.search(x) or re.search(r"(?i)exercise\s+price|exercisable\s+at", x)]
    return _strike_in(" ".join(keep))


def _strike_old_in(s, new_at=None):
    """The exercise price before a change (the new-price clause left out)."""
    if new_at is not None:
        s = s[:max(0, new_at - 6)] + " " + s[new_at + 8:]
    for rx in (r"(?i)\bfrom\s+(?:the\s+current\s+exercise\s+price\s+of\s+)?(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+)",
               r"(?i)(?:had|have|has|with)\s+an\s+(?:original\s+)?exercise\s+price\s+of\s+(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+)",
               r"(?i)(?:were|are|currently)\s+exercisable\s+at\s+(?:a\s+price\s+of\s+)?(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+)",
               r"(?i)warrants\s+were\s+issued\s+at\s+(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+)",
               r"(?i)\bthe\s+(?:C\$|CDN\$|US\$|\$)\s?(\d*\.\d+)\s+warrants"):
        m = re.search(rx, s)
        if m:
            return float(m.group(1))
    return _strike_in(s)


def _read_groups(zone, text, kind):
    """Rows of fields for each series the passage names (one dict per series)."""
    counts = _zone_counts(zone)
    roles = _roles(zone, kind)
    off = _offset(zone) if kind == "extension" else None
    strike_new, new_at = _strike_new_in(zone) if kind == "repricing" else (None, None)
    zone_strike = _strike_old_in(zone, new_at) if kind == "repricing" else _strike_free(zone)
    if zone_strike is None and kind != "repricing":
        wsents = [x for x in _sentences(text) if WARRANT.search(x) and not _OFFERING_SENT.search(x)
                  and not re.search(r"(?i)incentive\s+warrant|new\s+warrant|stock\s+option", x)]
        zone_strike = _strike_free(" ".join(wsents))
    news, olds, isss = _all(roles, "NEW"), _all(roles, "OLD"), _all(roles, "ISS")
    if not isss:
        isss = [d for d in _issued_dates(text)]
    groups = []
    multi = len(counts) >= 2
    if multi:
        segs = []
        for k, (p, v) in enumerate(counts):
            end = counts[k + 1][0] if k + 1 < len(counts) else len(zone)
            segs.append((p, end, v))
        prices = {_strike_in(zone[p:e]) for p, e, _ in segs} - {None}
        seg_roles = [_roles(zone[p:e], kind) for p, e, _ in segs]
        distinct = lambda xs: list(dict.fromkeys(xs))
        if not (len(prices) >= 2 or len(distinct(news)) >= 2 or len(distinct(olds)) >= 2 or len(distinct(isss)) >= 2
                or sum(1 for r in seg_roles if _first(r, "NEW") or _first(r, "OLD")) >= 2):
            multi = False
    if not multi:
        if len(_strikes_stated(zone)) > 1:
            zone_strike = None
        g = {"n_warrants": counts[0][1] if counts else None, "strike_old": zone_strike,
             "expiry_new": _first(roles, "NEW")[:4], "expiry_old": (_first(roles, "OLD") or [None])[0],
             "issued": list(dict.fromkeys(isss))}
        if not g["expiry_new"] and off and g["expiry_old"]:
            g["expiry_new"] = [_shift(g["expiry_old"], off)]
        if kind == "repricing":
            g["strike_new"] = strike_new
        return [g]
    n = len(segs)

    def spread(flat, per_seg):
        flat = list(dict.fromkeys(flat))
        if len(flat) == n and not all(per_seg):
            return [[x] for x in flat]
        if all(per_seg):
            return per_seg
        if len(flat) == n:
            return [[x] for x in flat]
        if len(flat) == 1:
            return [ps or flat for ps in per_seg]
        return per_seg

    seg_new = [_first(r, "NEW")[:1] for r in seg_roles]
    seg_old = [_first(r, "OLD")[:1] for r in seg_roles]
    seg_iss = [_first(r, "ISS")[:1] for r in seg_roles]
    # 'DATE whereby the Company (also) issued N'
    for k, (p, e, v) in enumerate(segs):
        m = re.search(r"(?i)(" + _MON + r"\s+\d{1,2},?\s+\d{4}),?\s+(?:whereby\s+)?the\s+company\s+(?:also\s+)?issued\s+$", zone[max(0, p - 80):p])
        if m:
            seg_iss[k] = [dates_in(m.group(1))[0][2]]
    # per-series pairs stated in order ('(i) ... from A to B; and (ii) ... from C to D')
    seq = [(r, vs) for a, b, vs, r in roles if r in ("OLD", "NEW")]
    runpair = [(seq[i][1], seq[i + 1][1]) for i in range(len(seq) - 1)
               if seq[i][0] == "OLD" and seq[i + 1][0] == "NEW" and len(seq[i][1]) == n and len(seq[i + 1][1]) == n]
    pairs = [(seq[i][1], seq[i + 1][1]) for i in range(len(seq) - 1)
             if seq[i][0] == "OLD" and seq[i + 1][0] == "NEW" and len(seq[i][1]) == 1 and len(seq[i + 1][1]) == 1]
    if runpair:                       # 'from A and B to C and D (respectively)'
        olds_l, news_l = [[x] for x in runpair[0][0]], [[x] for x in runpair[0][1]]
    elif len(pairs) == n:             # '(i) ... from A to B; and (ii) ... from C to D'
        olds_l, news_l = [p[0] for p in pairs], [p[1] for p in pairs]
    else:
        news_l, olds_l = spread(news, seg_new), spread(olds, seg_old)
    iss_l = spread(isss, seg_iss)
    for k, (p, e, v) in enumerate(segs):
        seg = zone[p:e]
        g = {"n_warrants": v, "strike_old": (_strike_old_in(seg) if kind == "repricing" else _strike_in(seg)) or zone_strike,
             "expiry_new": news_l[k][:1] if k < len(news_l) else [],
             "expiry_old": (olds_l[k] or [None])[0] if k < len(olds_l) else None,
             "issued": iss_l[k][:1] if k < len(iss_l) else []}
        if kind == "repricing":
            g["strike_new"] = strike_new
            if g["strike_old"] == strike_new:
                g["strike_old"] = zone_strike
        if not g["expiry_new"] and off and g["expiry_old"]:
            g["expiry_new"] = [_shift(g["expiry_old"], off)]
        groups.append(g)
    return groups


def _fill(row, g):
    for k, v in g.items():
        if row.get(k) in (None, []) and v not in (None, [], [None]):
            row[k] = v
    return row


def _rows_extension(text, sents, idxs, status):
    """WS: one row per counted group."""
    rows = []
    # (i) N of the Warrants, originally issued on DATE, to DATE  /  N warrants issued on DATE ... from X to Y
    groups = re.findall(r"(?i)\(\s*[ivx]+\s*\)\s*(\d[\d,]*)\s+of\s+(?:these\s+|the\s+)?warrants,?\s+originally\s+issued\s+on\s+(" + _MON + r"\s+\d{1,2},?\s+\d{4}),?\s+to\s+(" + _MON + r"\s+\d{1,2},?\s+\d{4})", text)
    if len(groups) >= 2:
        many = _strikes_stated(text)
        for n, iss, new in groups:
            r = _base("extension", status)
            r["n_warrants"] = _num(n)
            r["strike_old"] = many[0] if len(many) == 1 else None
            r["issued"] = [d for _, _, d in dates_in(iss)][:1]
            r["expiry_new"] = [d for _, _, d in dates_in(new)][:1]
            rows.append(r)
        return rows
    # "originally issued on January 24, 2023 for 7,040,000 Warrants and February 21, 2023 for 1,000,000 Warrants ... from A and B to C and D"
    m = re.search(r"(?i)issued\s+on\s+(" + _MON + r"\s+\d{1,2},?\s+\d{4})\s+for\s+(\d[\d,]*)\s+warrants\s+and\s+(" + _MON +
                  r"\s+\d{1,2},?\s+\d{4})\s+for\s+(\d[\d,]*)\s+warrants", text)
    if m:
        olds = new = []
        mm = re.search(r"(?i)amended\s+from\s+", text)
        if mm:
            olds = _date_run(text, mm.end(), lead=4)
            m2 = re.search(r"(?i)\s+to\s+", text[mm.end():mm.end() + 120])
            new = _date_run(text, mm.end() + m2.end(), lead=4) if m2 else []
        strike = _strike_in(text)
        for k, (iss, n) in enumerate(((m.group(1), m.group(2)), (m.group(3), m.group(4)))):
            r = _base("extension", status)
            r["n_warrants"] = _num(n)
            r["strike_old"] = strike
            r["issued"] = [d for _, _, d in dates_in(iss)]
            if k < len(olds):
                r["expiry_old"] = olds[k]
            if k < len(new):
                r["expiry_new"] = [new[k]]
            rows.append(r)
        return rows
    # "13,000,000 warrants are set to expire on November 03rd, 2024 and 8,875,000 warrants set to expire on November 29th, 2024"
    m = re.findall(r"(?i)(\d[\d,]*)\s+warrants\s+(?:are\s+)?set\s+to\s+expire\s+on\s+(" + _MON + r"\s+\d{1,2}" + _ORD + r",?\s+\d{4})", text)
    if len(m) >= 2:
        mm = re.search(r"(?i)amended\s+expiry\s+dates\s+of\s+", text)
        new = _date_run(text, mm.end(), lead=4) if mm else []
        iss = _issued_dates(text)
        strike = _strike_in(text)
        for k, (n, old) in enumerate(m):
            r = _base("extension", status)
            r["n_warrants"] = _num(n)
            r["strike_old"] = strike
            r["expiry_old"] = dates_in(old)[0][2] if dates_in(old) else None
            if k < len(new):
                r["expiry_new"] = [new[k]]
            if k < len(iss):
                r["issued"] = [iss[k]]
            rows.append(r)
        return rows
    # Halcones-style: several named series, each "A total of N ... (the "YYYY Warrants") ... to DATE"
    series = re.findall(r"(?i)A\s+total\s+of\s+(\d[\d,]*)\s+common\s+share\s+purchase\s+warrants\s+\(the\s+\"(\d{4})\s+Warrants\"\)(.*?)(?=A\s+total\s+of\s+\d|$)", text)
    if len(series) >= 2:
        for n, yr, rest in series:
            r = _base("extension", status)
            r["n_warrants"] = _num(n)
            r["strike_old"] = _strike_in(rest[:200]) or _strike_in(text)
            r["expiry_old"] = _expiry_old(rest)
            mm = re.search(r"(?i)extend\s+the\s+expiry\s+dates?\s+of\s+the\s+" + yr + r"\s+Warrants\s+to\s+", rest)
            r["expiry_new"] = [d for _, _, d in dates_in(rest[mm.end():mm.end() + 120])] if mm else []
            mm = re.search(r"(?i)press\s+releases?\s+dated\s+", rest)
            r["issued"] = [d for _, _, d in dates_in(rest[mm.end():mm.end() + 160])] if mm else []
            if r["expiry_old"] and len(r["issued"]) > 1:
                r["issued"] = r["issued"][:1]
            rows.append(r)
        return rows
    # r5: series by count, read generically
    z = _zone(sents, idxs, CUE["extension"]) or text
    groups = _read_groups(z, text, "extension")
    if len(groups) >= 2:
        for g in groups:
            r = _fill(_base("extension", status), g)
            r["issued"] = [d for d in r["issued"] if d not in r["expiry_new"] and d != r["expiry_old"]]
            rows.append(r)
        return rows
    # one group: the specific readings first, the generic one fills the gaps
    r = _base("extension", status)
    sent = " ".join(sents[i] if i >= 0 else "" for i in idxs)
    whole = text
    near = " ".join(sents[j] for i in idxs if i >= 0 for j in range(i, min(i + 3, len(sents))))
    cs = counts_in(near) or counts_in(whole)
    r["n_warrants"] = cs[0][1] if cs else None
    many = _strikes_stated(near or whole)
    r["strike_old"] = None if len(many) > 1 else (_strike_in(near) if near else None) or _strike_in(whole)
    old, new = _from_to(sent)
    if not new:
        old2, new2 = _from_to(whole)
        old, new = old or old2, new2
    news = [new] if new else []
    if not news:
        for rx in (r"(?i)(?:are|is)\s+now\s+extended\s+to\s+expire\s+on\s+", r"(?i)(?:are|is)\s+now\s+set\s+to\s+expire\s+on\s+",
                   r"(?i)will\s+be\s+extended\s+to\s+", r"(?i)amended\s+expiry\s+being\s+", r"(?i)now\s+exercisable\s+[^;]{0,40}?\buntil\s+",
                   r"(?i)(?:has|have)\s+been\s+extended\s+to\s+", r"(?i)new\s+(?:warrant\s+)?expiry\s+date\s+(?:is|will\s+be)\s+",
                   r"(?i)extend(?:ing|ed)?\s+the\s+expiry\s+date\s+of\s+the\s+warrants\s+to\s+",
                   r"(?i)new\s+expiry\s+dates?\s+for\s+the\s+warrants\s+will\s+be\s+",
                   r"(?i)(?:new\s+expiry\s+dates?\s+(?:will\s+be|of)|extend\s+(?:the\s+)?expiry\s+dates?\s+(?:of|for)\s+(?:\w+\s+){0,10}?to|"
                   r"extend\s+the\s+expiry\s+date\s+(?:for|by)\s+[^.]{0,40}?\bto|"
                   r"extend\s+the\s+expiry\s+date\s+to|intending\s+to\s+extend\s+the\s+expiry\s+date\s+to|to\s+extend\s+the\s+deadline[^.]{0,80}?until|"
                   r"by\s+an\s+additional\s+\d+\s+months\s+to|will\s+be\s+exercisable\s+until|will\s+have\s+respectively\s+amended\s+expiry\s+dates\s+of|"
                   r"accordingly,?\s+the\s+new\s+expiry\s+dates?\s+(?:for\s+these\s+warrants\s+)?will\s+be|"
                   r"extend\s+the\s+expiry\s+date\s+of\s+(?:an\s+aggregate\s+of\s+)?[\d,]+\s+(?:\w+\s+){0,4}warrants\s+(?:\([^)]*\)\s+)?to)\s*"):
            ds = _new_dates_after(whole, rx)
            if ds:
                news = ds[:4]
                break
    r["expiry_new"] = news
    r["expiry_old"] = old or _expiry_old(whole)
    if r["expiry_old"] in news:
        r["expiry_old"] = None
    r["issued"] = _issued_dates(whole)
    g = groups[0]
    sn, at = _strike_new_in(z)
    if sn is not None and r["strike_old"] == sn:          # a repricing in the same passage: the price before it
        r["strike_old"] = _strike_old_in(z, at)
        if r["strike_old"] == sn:
            r["strike_old"] = None
    if g.get("strike_old") == sn:
        g["strike_old"] = None
    if g.get("strike_old") and r["strike_old"] and g["strike_old"] != r["strike_old"] and _strike_in(z) == g["strike_old"]:
        r["strike_old"] = g["strike_old"]          # the passage's own price beats one found elsewhere in the release
    _fill(r, g)
    # an issue date is never one of the new dates
    r["issued"] = [d for d in r["issued"] if d not in r["expiry_new"] and d != r["expiry_old"]]
    if r["expiry_old"] in r["expiry_new"]:
        r["expiry_old"] = None
    rows.append(r)
    return rows


def _base(kind, status):
    return {"change": kind, "status": status, "n_warrants": None, "strike_old": None, "strike_new": None, "issued": [],
            "expiry_old": None, "expiry_new": [], "program_end": None, "n_exercised": None, "proceeds": None,
            "n_remaining": None, "new_series_n": None, "new_series_strike": None, "new_series_expiry": None,
            "new_series_term_months": None}


def _term_months(s):
    m = re.search(r"(?i)(?:for\s+a\s+period\s+of|for)\s+(\w+(?:-\w+)?)\s*(?:\(\d+\)\s*)?(years?|months?)\s+from\s+the\s+date\s+of\s+issuance", s)
    if not m:
        return None
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "twelve": 12, "eighteen": 18, "twenty-four": 24,
             "thirty-six": 36}
    w = m.group(1).lower()
    n = float(w) if re.fullmatch(r"\d+", w) else words.get(w)
    if n is None:
        return None
    return n * 12 if m.group(2).lower().startswith("year") else n


def _rows_incentive(h, text, status):
    r = _base("incentive", status)
    for rx in (r"(?i)holders\s+of\s+(\d+(?:\.\d+)?\s+million|\d[\d,]*)\s+(?:\w+\s+){0,6}?warrants[^.]{0,60}?were\s+eligible",
               r"(?i)(?:encourage\s+the\s+(?:early\s+)?exercise\s+of\s+(?:up\s+to\s+|the\s+)?|exercise\s+of\s+up\s+to)\s*(\d+(?:\.\d+)?\s+million|\d[\d,]*)\s+(?:\w+\s+){0,6}?warrants",
               r"(?i)\bOf\s+the\s+(\d+(?:\.\d+)?\s+million|\d[\d,]*)\s+eligible\s+warrants"):
        m = re.search(rx, text)
        if m:
            g = m.group(1)
            r["n_warrants"] = _num(g.split()[0], "million" if "million" in g else None)
            break
    m = re.search(r"(?i)(\d[\d,]*)\s+(?:common\s+shares\s+(?:\(each,?\s+a\s+\"Share\"\)\s+)?of\s+the\s+company\s+were\s+issued\s+upon\s+the\s+exercise\s+of\s+\d[\d,]*|"
                  r"(?:\w+\s+){0,3}warrants\s+(?:\(the\s+\"[^\"]+\"\)\s+)?(?:were|have\s+been)\s+exercised|(?:eligible\s+)?warrants?\s+for\s+proceeds|"
                  r"were\s+exercised)", text)
    m2 = re.search(r"(?i)\d[\d,]*\s+common\s+shares[^.]{0,140}?were\s+issued\s+upon\s+the\s+exercise\s+of\s+(\d[\d,]*)", text)
    if m2:
        m = m2
    if not m:
        m = re.search(r"(?i)exercise\s+of\s+(\d[\d,]*)\s+(?:(?:common\s+)?share\s+purchase\s+|outstanding\s+(?:share\s+purchase\s+)?)?warrants", text)
    if not m:
        m = re.search(r"(?i)the\s+holders\s+(\d[\d,]*)\s+eligible\s+warrants|holders\s+exercised\s+(\d[\d,]*)", text)
    if m:
        r["n_exercised"] = _num(next(g for g in m.groups() if g))
    elif re.search(r"(?i)\bno\s+(?:\w+\s+){0,5}warrants\s+(?:of\s+the\s+company\s+)?were\s+exercised", text):
        r["n_exercised"] = 0
    for m in re.finditer(r"(?i)(?:gross\s+)?proceeds\s+(?:totall?ing\s+|of\s+)(?:approximately\s+)?(?:CAD\s*|C)?(\$\s?[\d,]+(?:\.\d+)?)|received\s+proceeds\s+totall?ing\s+(\$[\d,]+)|"
                         r"for\s+proceeds\s+of\s+(?:CAD\s+)?(\$\s?[\d,]+)", text):
        if re.search(r"(?i)\bif\s+all|would\s+receive|assuming|up\s+to\s*$|potential", text[max(0, m.start() - 120):m.start()]):
            continue
        r["proceeds"] = _money(next(g for g in m.groups() if g))
        break
    # programme end
    pe = None
    for rx in (r"(?i)(?:early\s+exercise\s+period|exercise\s+period)[^.]{0,80}?(?:shall\s+now\s+terminate|terminate)\s+at\s+[^.]{0,40}?\bon\s+",
               r"(?i)(?:extend|extension)[^.]{0,120}?(?:early\s+exercise\s+period|incentive\s+program)[^.]{0,120}?\b(?:to|until)\s+",
               r"(?i)opportunity\s+to\s+exercise\s+to\s+",
               r"(?i)terminate\s+on\s+",
               r"(?i)during\s+the\s+\d+-day\s+period\s+from\s+[^.]{0,30}?\bto\s+",
               r"(?i)(?:on\s+or\s+before\s+the\s+exercise\s+deadline\s+of|exercise\s+deadline\s+of)\s+",
               r"(?i)as\s+of\s+\d{1,2}:\d{2}\s*[ap]\.?m\.?\s*\([A-Z]+\)\s+on\s+",
               r"(?i)prior\s+to\s+or\s+on\s+",
               r"(?i)(?:incentive\s+)?program(?:me)?\s+(?:was\s+)?(?:completed|closed|ended|expired|terminated)\s+on\s+",
               r"(?i)(?:prior\s+to\s+)?(?:its|the\s+program(?:me)?'?s?)\s+(?:expiry|expiration)\s+(?:date\s+)?(?:on|of)\s+"):
        m = re.search(rx, text)
        if m:
            ds = dates_in(text[m.end():m.end() + 60])
            if ds and ds[0][0] < 8:
                pe = ds[0][2]
                break
    m = re.search(r'(?i)(' + _MON + r'\s+\d{1,2},?\s+\d{4})\s*\(the\s+"\s*(?:Program(?:me)?\s+End\s+Date|Early\s+Exercise\s+Deadline|Incentive\s+Deadline)', text)
    if m:
        pe = dates_in(m.group(1))[0][2]
    if not pe:
        m = re.search(r"(?i)Early\s+Exercise\s+Period\s+will\s+commence\s+on\s+[^.]{0,30}?and\s+terminate\s+on\s+", text)
        if m:
            ds = dates_in(text[m.end():m.end() + 40])
            pe = ds[0][2] if ds else None
    r["program_end"] = pe
    r["strike_old"] = None
    m = re.search(r"(?i)(?:eligible\s+warrants?|outstanding\s+warrants?)[^.]{0,200}?(?:at\s+a\s+price\s+of|price\s+of|exercisable\s+at\s+a\s+price\s+of)\s+\$\s?(\d*\.\d+)", text)
    if not m:
        m = re.search(r"(?i)exercise\s+of\s+[\d,]+\s+(?:\w+\s+){0,4}warrants\s+at\s+(?:an?\s+(?:exercise\s+)?price\s+of\s+)?(?:C\$|\$)\s?(\d*\.\d+)", text) or \
            re.search(r"(?i)(?:had|have|has)\s+an\s+(?:original\s+)?exercise\s+price\s+of\s+(?:C\$|\$)\s?(\d*\.\d+)", text) or \
            re.search(r"(?i)\(at\s+(?:C\$|\$)\s?(\d*\.\d+)\s+per\s+(?:outstanding\s+|eligible\s+)?warrant\)", text)
    if not m:
        m = re.search(r"(?i)exercisable\s+(?:to\s+acquire\s+one\s+common\s+share[^.]{0,80}?|(?:into|for)\s+common\s+shares[^.$]{0,60}?)?at\s+a\s+price\s+of\s+\$\s?(\d*\.\d+)\s+per\s+(?:\w+\s+){0,2}share", text)
        if m and re.search(r"(?i)(?:incentive|new)\s+warrants?", text[max(0, m.start() - 120):m.start()]):
            m = None
    if m:
        r["strike_old"] = float(m.group(1))
    m = re.search(r"(?i)temporary\s+repricing\s+of\s+the\s+warrant\s+exercise\s+price\s+to\s+\$\s?(\d*\.\d+)", text) or \
        re.search(r"(?i)repric\w*\s+(?:the\s+)?(?:eligible\s+)?warrants?\s+from\s+[^;]{0,90}?\bto\s+(?:C\$|\$)\s?(\d*\.\d+)", text)
    if m:
        r["strike_new"] = float(m.group(1))
    m = re.search(r"(?i)balance\s+of\s+(?:the\s+)?(\d[\d,]*)\s+warrants\s+not\s+exercised", text)
    if m:
        r["n_remaining"] = _num(m.group(1))
    # the incentive warrants (a new series)
    m = re.search(r"(?i)(?:each\s+)?(?:incentive\s+warrant|new\s+warrant)s?\s+(?:will\s+)?(?:entitles?|is|are|will\s+be)[^.]{0,200}", text)
    if m:
        seg = text[m.start():m.end() + 160]
        s2 = _strike_in(seg)
        r["new_series_strike"] = s2
        dd = re.search(r"(?i)(?:until|on\s+or\s+before)\s+(" + _MON + r"\s+\d{1,2},?\s+\d{4})", seg)
        if dd:
            r["new_series_expiry"] = dates_in(dd.group(1))[0][2]
        tm = _term_months(seg) or (lambda mm: (float(mm.group(1)) * (12 if mm.group(2).lower().startswith("y") else 1)) if mm else None)(
            re.search(r"(?i)for\s+a\s+period\s+of\s+(?:\w+\s+)?\(?(\d+)\)?\s+(years?|months?)", seg))
        if not tm:
            mm = re.search(r"(?i)for\s+(\w+)\s+years", seg)
            words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
            if mm and mm.group(1).lower() in words:
                tm = words[mm.group(1).lower()] * 12
        r["new_series_term_months"] = tm
    m = re.search(r"(?i)(?:will\s+issue|were\s+issued|total\s+of)\s+(\d[\d,]*)\s+Incentive\s+Warrants", text) or \
        re.search(r"(?i)issued\s+(\d[\d,]*)\s+additional\s+common\s+share\s+purchase\s+warrant", text)
    if m:
        r["new_series_n"] = _num(m.group(1))
    m = re.search(r"(?i)Incentive\s+Warrants\s+that\s+will\s+expire\s+on\s+", text)
    if m:
        ds = dates_in(text[m.end():m.end() + 30])
        if ds:
            r["new_series_expiry"] = ds[0][2]
    if re.search(r"(?i)100%\s+of\s+(?:its|the)\s+outstanding\s+warrants\s+exercised|no\s+outstanding\s+warrants\s+remain|"
                 r"remaining\s+[\d,]+\s+warrants\s+expiring\s+unexercised", text):
        r["n_remaining"] = 0
    r["issued"] = [d for d in _issued_dates(text) if d != r["program_end"]]
    m = re.search(r"(?i)(?:until|expiry\s+date\s+of)\s+(" + _MON + r"\s+\d{1,2},?\s+\d{4})\s+\(the\s+\"Expiry\s+Date\"\)", text) or \
        re.search(r"(?i)with\s+an\s+expiry\s+(?:date\s+)?of\s+(" + _MON + r"\s+\d{1,2},?\s+\d{4})", text) or \
        re.search(r"(?i)(?:will\s+be|remain|continue\s+to\s+be)\s+exercisable\s+[^;]{0,140}?\buntil\s+(" + _MON + r"\s+\d{1,2},?\s+\d{4})", text)
    if m and re.search(r"(?i)(?:new|incentive|bonus)\s+warrants?", text[max(0, m.start() - 90):m.start(1)]):
        m = None
    if m:
        r["expiry_old"] = dates_in(m.group(1))[0][2]
    return [r]


def _exercise_strike(text):
    """The price the exercised warrants carried: stated with the exercise first, else from warrant sentences only."""
    for rx in (r"(?i)exercise\s+(?:by\s+[^.]{0,80}?\s+)?of\s+[\d,]+\s+(?:\w+\s+){0,6}?warrants\s+(?:\([^)]*\)\s+)?at\s+(?:a\s+price\s+of\s+|an\s+exercise\s+price\s+of\s+)?(?:C\$|US\$|\$)\s?(\d*\.\d+)",
               r"(?i)warrants\s+(?:\([^)]*\)\s+)?(?:were|have\s+been)\s+exercised\s+at\s+(?:a\s+price\s+of\s+|an\s+exercise\s+price\s+of\s+)?(?:C\$|US\$|\$)\s?(\d*\.\d+)",
               r"(?i)exercised\s+at\s+(?:a\s+price\s+of\s+|an\s+exercise\s+price\s+of\s+)?(?:C\$|US\$|\$)\s?(\d*\.\d+)"):
        m = re.search(rx, text)
        if m:
            return float(m.group(1))
    ws = [x for x in _sentences(text) if WARRANT.search(x) and not re.search(r"(?i)\boptions?\b|\bRSUs?\b|restricted\s+share|units?\s+(?:priced|at)|each\s+unit", x)]
    return _strike_free(" ".join(ws))


def _rows_exercise(h, text, status):
    """One row per strike the release counts (WS)."""
    rows = []
    # "N at $X per share and M at $Y per share"
    pairs = re.findall(r"(?i)(\d[\d,]{4,})\s+(?:warrants\s+)?at\s+(?:an\s+exercise\s+price\s+of\s+)?(?:US)?\$\s?(\d*\.\d+)", text)
    pairs += [(n, p) for n, p in re.findall(r"(?i)exercise\s+of\s+(\d[\d,]{4,})\s+warrants\s+at\s+an\s+exercise\s+price\s+of\s+US\$\s?(\d*\.\d+)", text)]
    pairs += [(n, p) for n, p in re.findall(r"(?i)(\d[\d,]{4,})\s+common\s+share\s+purchase\s+warrants\s+\([^)]*\)\s+at\s+an\s+exercise\s+price\s+of\s+\$(\d*\.\d+)", text)]
    pairs += [(n, p) for n, p in re.findall(r"(?i)(\d[\d,]{4,})\s+warrants[^$]{0,80}?(?:strike|exercise)\s+price\s+of\s+\$(\d*\.\d+)", text)]
    seen, uniq = set(), []
    for n, p in pairs:
        key = (_num(n), float(p))
        if key not in seen and key[0] >= 1000:
            seen.add(key)
            uniq.append(key)
    # keep only exercised counts (drop "warrants remain outstanding" and expired)
    keep = []
    for n, p in uniq:
        i = text.find("{:,}".format(int(n)))
        ctx = text[i:i + 170] if i >= 0 else ""
        pre = text[max(0, i - 130):i] if i >= 0 else ""
        nxt = re.search(r"\d{1,3}(?:,\d{3})+", ctx[10:])
        own = ctx[:10 + nxt.start()] if nxt else ctx
        if re.search(r"(?i)expired\s+unexercised|remain\s+outstanding|remaining", ctx[:170]) and not re.search(r"(?i)exercised\s+(?:for|resulting)", own) \
                or re.search(r"(?i)remain\w*\s+outstanding|outstanding,\s+including", pre):
            continue
        keep.append((n, p))
    if len(keep) >= 2:
        for n, p in keep:
            r = _base("exercise", status)
            r["n_exercised"] = n
            r["strike_old"] = p
            i = text.find("{:,}".format(int(n)))
            win = text[i:i + 260]
            nxt = re.search(r"(?<=\s)\d{1,3}(?:,\d{3})+", win[12:])
            own = win[:12 + nxt.start()] if nxt else win
            if re.search(r"(?i)not\s+part\s+of\s+the\s+acceleration", own):
                r["_not_acc"] = True
                ds = re.search(r"(?i)expiry\s+date\s+of\s+", own)
                if ds:
                    run = _date_run(own, ds.end(), lead=4)
                    r["expiry_old"] = run[0] if run else None
            mp = re.search(r"(?i)proceeds\s+of\s+(\$[\d,]+)", own)
            if mp and not re.search(r"(?i)\band\s*$", text[max(0, i - 40):i]):
                r["proceeds"] = _money(mp.group(1))
            rem = re.search(r"(?i)(\d[\d,]*)\s+warrants\s+remain\s+outstanding\s+at\s+an\s+exercise\s+price\s+of\s+\$" + re.escape(("%g" % p)), text)
            if rem:
                r["n_remaining"] = _num(rem.group(1))
            elif re.search(r"(?i)\$" + re.escape("%g" % p) + r"[^.]{0,80}?(?:per\s+share\s+)?expired\s+unexercised|expired\s+unexercised", text) and \
                    re.search(r"(?i)following\s+the\s+accelerated|accelerat", text):
                r["n_remaining"] = 0
            rows.append(r)
    else:
        r = _base("exercise", status)
        m = re.search(r"(?i)(?:exercise\s+of|exercised\s+an\s+aggregate\s+of|aggregate\s+of|following\s+an\s+exercise\s+of|a\s+total\s+of)\s+(\d[\d,]*)\s+(?:\w+\s+){0,5}?warrants", text) or \
            re.search(r"(?i)(\d+(?:\.\d+)?\s+million|\d[\d,]*)\s+(?:\w+\s+){0,5}?warrants\s+(?:\([^)]*\)\s+)?(?:\([^)]*\)\s+)?(?:issued[^.]{0,80}?)?(?:have\s+been|were|had\s+been)\s+exercised", text) or \
            re.search(r"(?i)The\s+(\d[\d,]*)\s+warrants,?\s+priced\s+at", text) or \
            re.search(r"(?i)issued\s+(\d[\d,]*)\s+common\s+shares\s+to\s+investors\s+following\s+the\s+early\s+exercise", text) or \
            re.search(r"(?i)exercise\s+by\s+[^.]{0,80}?\bof\s+(\d[\d,]*)\s+(?:\w+\s+){0,4}warrants", text) or \
            re.search(r"(?i)warrants\s+over\s+(\d[\d,]*)\s+(?:common\s+|ordinary\s+|new\s+)?shares", text) or \
            re.search(r"(?i)(\d[\d,]*)\s+(?:\w+\s+){0,5}?warrants\s+(?:of\s+the\s+company\s+)?(?:held\s+by\s+[^.]{0,60}?)?(?:\([^)]*\)\s*)?(?:have\s+been|were|had\s+been)\s+exercised", text) or \
            re.search(r"(?i)(\d[\d,]*)\s+(?:\w+\s+){0,5}?warrants\s+issued(?:[^.()]|\([^)]*\)){0,220}?(?:have\s+been|were|had\s+been)\s+exercised", text)
        if m:
            g = m.group(1)
            r["n_exercised"] = _num(g.split()[0], "million" if "million" in g else None)
        r["strike_old"] = keep[0][1] if keep else _exercise_strike(text)
        rows.append(r)
    m = None
    for m in re.finditer(r"(?i)(?:gross\s+proceeds|total\s+proceeds|aggregate\s+gross\s+proceeds|proceeds)\s+(?:to\s+the\s+company\s+)?(?:of|totall?ing)\s+(?:approximately\s+)?(?:CDN\s*|C)?(\$\s?[\d,]+(?:\.\d+)?(?:\s*million)?)|"
                         r"generated\s+(?:CDN|C)?(\$[\d,]+(?:\.\d+)?)|total\s+consideration\s+of\s+(US\$\s?[\d,]+)|Receives\s+(\$[\d,]+)|Raises\s+(\$[\d,]+)|"
                         r"consideration\s+of\s+£\s?([\d,]+)|(?:C)?(\$\s?[\d,.]+(?:\s*million)?)\s+(?:has|have)\s+been\s+received\s+(?:through|from)\s+the\s+exercise", text):
        if re.search(r"(?i)assuming|\bif\s+all|would\s+(?:receive|be)|will\s+receive|potential", text[max(0, m.start() - 60):m.start()]):
            m = None
            continue
        break
    m = m or re.search(r"(?i)Receives\s+C\$([\d.]+)\s+Million", h)
    if m:
        g = next(x for x in m.groups() if x)
        v = _money(g) if "$" in g else (_num(g) * 1e6 if "million" in m.group(0).lower() and "$" not in g else _num(g))
        if len(rows) == 1:
            rows[0]["proceeds"] = v
    acc_new = None
    m = re.search(r"(?i)(?:accelerated\s+to|accelerated\s+to\s+5:00\s*p\.?m\.?[^.]{0,30}?on|expiry\s+date\s+of\s+the\s+warrants\s+was\s+accelerated\s+to[^$]{0,60}?being)\s+", text)
    if m:
        ds = dates_in(text[m.end():m.end() + 80])
        if ds and ds[0][0] < 50:
            acc_new = ds[0][2]
    if acc_new:
        for r in rows:
            if not r.get("_not_acc"):
                r["expiry_new"] = [acc_new]
    if re.search(r"(?i)all\s+warrants\s+from|100%\s+of\s+the\s+warrants|balance\s+of\s+the\s+unexercised\s+warrants\s+have\s+expired|"
                 r"100%\s+of\s+the\s+warrants\s+were\s+exercised", text):
        for r in rows:
            if not r.get("_not_acc") and r["n_remaining"] is None:
                r["n_remaining"] = 0
    for r in rows:
        r.pop("_not_acc", None)
    m = re.search(r"(?i)currently\s+has\s+(\d[\d,]*)\s+outstanding\s+warrants", text)
    if m and len(rows) == 1:
        rows[0]["n_remaining"] = _num(m.group(1))
    if len(rows) == 1:
        r0 = rows[0]
        m = re.search(r"(?i)(?:a\s+total\s+of\s+)?(\d[\d,]*)\s+warrants\s+were\s+originally\s+issued|all\s+of\s+the\s+(\d[\d,]*)\s+(?:\w+\s+){0,3}warrants|"
                      r"portion\s+of\s+the\s+(\d[\d,]*)\s+(?:\w+\s+){0,3}warrants", text)
        if m and r0["n_warrants"] is None:
            r0["n_warrants"] = _num(next(g for g in m.groups() if g))
        if r0["n_remaining"] is None:
            if re.search(r"(?i)remaining\s+[\d,]+\s+warrants\s+(?:have\s+|were\s+|had\s+)?(?:expired|been\s+cancelled|cancelled|were\s+cancelled)|all\s+of\s+the\s+[\d,]+\s+(?:\w+\s+){0,3}warrants|full\s+exercise\s+of\s+(?!the\s+remaining)", text + " " + h):
                r0["n_remaining"] = 0
            m = re.search(r"(?i)(?:of\s+the\s+)?remaining\s+(\d[\d,]*)\s+warrants(?!\s+(?:have\s+|were\s+|had\s+)?(?:been\s+)?(?:expired|cancel))", text)
            if m:
                r0["n_remaining"] = _num(m.group(1))
    m = re.search(r"(?i)(?:were\s+set\s+to\s+expire\s+on|expiry\s+date\s+of)\s+", text)
    if m and len(rows) == 1:
        ds = dates_in(text[m.end():m.end() + 40])
        if ds and ds[0][0] < 4:
            rows[0]["expiry_old"] = ds[0][2]
    iss = _issued_dates(text)
    if len(rows) == 1 and iss and not re.search(r"(?i)various\s+private\s+placements", text):
        rows[0]["issued"] = iss[:1]
    return rows


def _rows_acceleration(h, text, status, sents=None, idxs=None):
    rows = []
    newd = None
    for rx in (r"(?i)accelerate\s+the\s+expiry\s+of\s+the\s+warrants\s+to\s+[^.]{0,40}?on\s+", r"(?i)Accelerated\s+Expiry\s+Date[^.]{0,10}",
               r"(?i)accelerate\s+the\s+expiry\s+date\s+of\s+the\s+warrants\s+originally\s+issued\s+under\s+the\s+financing\s+to\s+[^.]{0,40}?on\s+",
               r"(?i)now\s+set\s+to\s+expire\s+at\s+[^.]{0,30}?on\s+", r"(?i)accelerated\s+to\s+[^.]{0,40}?on\s+"):
        m = re.search(rx, text)
        if m:
            ds = dates_in(text[m.end() - 40 if "Accelerated" in rx else m.end():m.end() + 80])
            if ds:
                newd = ds[0][2]
                break
    old = None
    m = re.search(r"(?i)now\s+expire\s+(?:on\s+)?", text)
    if not newd and m:
        run = _date_run(text, m.end(), lead=4)
        newd = run[0] if run else None
        mm = re.search(r"(?i)instead\s+of\s+", text[m.end():m.end() + 60])
        if mm:
            run = _date_run(text, m.end() + mm.end(), lead=4)
            old = run[0] if run else None
    if not newd:
        m = re.search(r"(?i)(?:expire\s+at\s+)?5:00\s*p\.?m\.?[^.]{0,30}?\bon\s+(" + _MON + r"\s+\d{1,2},?\s+\d{4})", text)
        if m:
            newd = dates_in(m.group(1))[0][2]
    # bullet list "DATE - N at $X"
    items = re.findall(r"(?i)(" + _MON + r"\s+\d{1,2},?\s+\d{4})\s*-\s*(\d[\d,]*)\s+at\s+\$(\d*\.\d+)", text)
    if len(items) >= 2:
        for d, n, p in items:
            r = _base("acceleration", status)
            r["issued"] = [dates_in(d)[0][2]]
            r["n_warrants"] = _num(n)
            r["strike_old"] = float(p)
            r["expiry_new"] = [newd] if newd else []
            rows.append(r)
        return rows
    z = _zone(sents, [i for i in idxs if i >= 0], CUE["acceleration"]) if sents and idxs else ""
    if not z or not (counts_in(z) or dates_in(z)):
        z = text
    groups = _read_groups(z, text, "acceleration")
    if len(groups) >= 2:
        for g in groups:
            r = _fill(_base("acceleration", status), g)
            if not r["expiry_new"] and newd:
                r["expiry_new"] = [newd]
            rows.append(r)
        return rows
    r = _base("acceleration", status)
    r["expiry_new"] = [newd] if newd else []
    r["expiry_old"] = old
    r["issued"] = _issued_dates(text)
    m = re.search(r"(?i)affects\s+(\d[\d,]*)\s+warrants\s+with\s+an\s+exercise\s+price\s+of\s+\$(\d*\.\d+)", text)
    if m:
        r["n_warrants"], r["strike_old"] = _num(m.group(1)), float(m.group(2))
    _fill(r, groups[0])
    if r["expiry_old"] in r["expiry_new"]:
        r["expiry_old"] = None
    return [r]


def _rows_waived(text):
    r = _base("acceleration_waived", "effective")
    m = re.search(r"(?i)with\s+respect\s+to\s+(\d[\d,]*)\s+outstanding\s+warrants", text)
    if m:
        r["n_warrants"] = _num(m.group(1))
    r["strike_old"] = _strike_in(text)
    r["issued"] = _issued_dates(text)
    return [r]


def _rows_repricing(text, status, sents=None, idxs=None):
    r = _base("repricing", status)
    m = re.search(r"(?i)repricing\s+of\s+(\d[\d,]*)\s+(?:common\s+share\s+purchase\s+)?warrants\s+with\s+an\s+exercise\s+price\s+of\s+\$(\d*\.\d+)\s+and\s+an\s+expiry\s+date\s+of\s+("
                  + _MON + r"\s+\d{1,2},?\s+\d{4})[^.]{0,80}?to\s+\$(\d*\.\d+)", text)
    if m:
        r["n_warrants"] = _num(m.group(1))
        r["strike_old"] = float(m.group(2))
        r["expiry_old"] = dates_in(m.group(3))[0][2]
        r["strike_new"] = float(m.group(4))
        return [r]
    z = _zone(sents, idxs, CUE["repricing"]) if sents and idxs else ""
    groups = _read_groups(z or text, text, "repricing")
    rows = []
    for g in groups:
        g = dict(g)
        g.pop("expiry_new", None)            # a repricing does not move the expiry
        rr = _fill(_base("repricing", status), g)
        rr["issued"] = [d for d in rr["issued"] if d != rr["expiry_old"]]
        rows.append(rr)
    return rows or [r]


def _rows_withdrawn(text):
    rows = [_base("withdrawn", "effective")]
    m = re.search(r"(?i)amendment\s+of\s+the\s+exercise\s+price\s+of\s+(\d[\d,]*)\s+[^.]{0,80}?from\s+(?:CAD\s+)?\$(\d*\.\d+)[^.]{0,30}?to\s+(?:CAD\s+)?\$(\d*\.\d+)", text)
    if m:
        rows[0]["n_warrants"] = _num(m.group(1))
        rows[0]["strike_old"] = float(m.group(2))
        rows[0]["strike_new"] = float(m.group(3))
    for n, d in re.findall(r"(?i)(\d[\d,]*)\s+Warrants\s+expired\s+on\s+(" + _MON + r"\s+\d{1,2},?\s+\d{4})", text):
        e = _base("expired", "effective")
        e["n_warrants"] = _num(n)
        e["expiry_old"] = dates_in(d)[0][2]
        rows.append(e)
    return rows


def analyse(headline, body):
    h, t = _clean(headline, body)
    res = {"rows": [], "reason": None}
    if not WARRANT.search(h + " " + t):
        res["reason"] = "no warrants"
        return res
    sents = _sentences(t)
    kinds = _cue_kinds(h, sents)
    if not kinds:
        res["reason"] = "no change cue"
        return res
    # WA: terms of an offering that has not closed
    if NEW_OFFERING.search(t) and not re.search(r"(?i)outstanding\s+(?:common\s+share\s+purchase\s+)?warrants|originally\s+issued", t):
        res["reason"] = "WA: offering not closed"
        return res
    # an acceleration headline is an acceleration, unless it reports what was exercised
    if H_ACC.search(h) and not re.search(r"(?i)exercis|proceeds|raises|receives|complet|results|successful", h):
        kinds.setdefault("acceleration", []).insert(0, -1)
        kinds.pop("exercise", None)
    if not WARRANT.search(h) and re.search(r"(?i)\bresults\b|financial\s+statements|\bQ[1-4]\b|quarter|annual\s+(?:and\s+special\s+)?(?:general\s+)?meeting|\bAGM\b", h):
        res["reason"] = "results or meeting release"
        return res
    # a financing or other release whose headline is not about warrants: only clearly stated changes to EXISTING warrants
    if not WARRANT.search(h) and not re.search(r"(?i)incentive\s+program", h):
        kinds.pop("exercise", None)
        for k in list(kinds):
            ok = [i for i in kinds[k] if i >= 0 and re.search(
                r"(?i)outstanding|previously\s+issued|originally\s+issued|existing|(?:were|was)\s+issued|issued\s+(?:on|in|pursuant|by)|granted\s+on|"
                r"expir\w*\s+on\s+\w+\s+\d|certain\s+warrants|incentive\s+program|early\s+exercise", sents[i])]
            if ok:
                kinds[k] = ok
            else:
                kinds.pop(k)
        if not kinds:
            res["reason"] = "not about existing warrants"
            return res
    rows = []
    if "incentive" in kinds and -1 not in kinds["incentive"] and -1 in kinds.get("extension", []):
        kinds.pop("incentive")
    if "acceleration_waived" in kinds:
        return {"rows": _rows_waived(t), "reason": None}
    # a release that both accelerated and reports what was exercised reports the exercises
    if "incentive" in kinds and not ("exercise" in kinds and re.search(r"(?i)acceleration", h) and not re.search(r"(?i)incentive", h)):
        st = _status(h + " " + t, "incentive")
        rows += _rows_incentive(h, t, st)
        kinds.pop("exercise", None)
        _prog = re.compile(r"(?i)incentive|program|early\s+exercise|for\s+the\s+term\s+of|temporar")
        ext = [i for i in kinds.get("extension", []) if i >= 0 and not _prog.search(sents[i])]
        if ext and not (-1 in kinds.get("extension", []) and re.search(r"(?i)incentive|program", h) and not re.search(r"(?i)extends?\s+warrants|reprices", h)):
            kinds["extension"] = ext
        else:
            kinds.pop("extension", None)
        if "repricing" in kinds and (re.search(r"(?i)temporary\s+repricing", t) and not re.search(r"(?i)require[sd]?\s+that\s+the\s+company\s+include", t)
                                     or all(i < 0 or _prog.search(sents[i]) for i in kinds["repricing"])):
            kinds.pop("repricing")
    if "withdrawn" in kinds:
        rows += _rows_withdrawn(t)
        kinds.pop("repricing", None)
        kinds.pop("extension", None)
    retro = "acceleration" in kinds and re.search(r"(?i)following\s+(?:the\s+)?|pursuant\s+to\s+its\s+(?:recent\s+)?notice|further\s+to|previously\s+announced|completed\s+the\s+acceleration",
                                                  " ".join(([h] + sents)[i + 1] for i in kinds["acceleration"]))
    if "exercise" in kinds and (re.search(r"(?i)exercis|raises|receives|proceeds", h) or retro or not ({"extension", "acceleration"} & set(kinds))):
        rows += _rows_exercise(h, t, "effective")
        kinds.pop("acceleration", None)
    elif "acceleration" in kinds:
        rows += _rows_acceleration(h, t, "effective", sents, kinds["acceleration"])
    if "extension" in kinds:
        ctx = h + " " + " ".join(sents[i] for i in kinds["extension"] if i >= 0)
        st = _status(ctx + " " + t, "extension")
        rows += _rows_extension(t, sents, kinds["extension"], st)
    if "repricing" in kinds:
        st = _status(t, "repricing")
        rows += _rows_repricing(t, st, sents, kinds["repricing"])
    rows = [r for r in rows if r["change"] != "exercise" or r["n_exercised"] or r["proceeds"]]
    res["rows"] = rows
    if not rows:
        res["reason"] = "cue without a readable change"
    return res


# ------------------------------------------------------------------ facts store
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["rows"]:
        return [F.Record(KIND, facts=[F.Fact("is_change", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"] or "none")], confidence=0.0)]
    out = []
    for r in a["rows"]:
        fs = [F.Fact("is_change", value_num=1.0)]
        for k in TXT_FIELDS:
            v = r.get(k)
            if isinstance(v, list):
                v = "|".join(v)
            if v not in (None, ""):
                fs.append(F.Fact(k, value_text=str(v)[:300]))
        for k in NUM_FIELDS:
            v = r.get(k)
            if v is not None:
                fs.append(F.Fact(k, value_num=float(v)))
        out.append(F.Record(KIND, facts=fs, confidence=1.0))
    return out


LIST_FIELDS = ("issued", "expiry_new")


def parse_records(rows_by_ordinal):
    rows = []
    for ordinal in sorted(rows_by_ordinal):
        r = {k: None for k in TXT_FIELDS + NUM_FIELDS}
        yes = False
        for field_, seq, num, text in rows_by_ordinal[ordinal]:
            if field_ == "is_change":
                yes = num == 1.0
            elif field_ in TXT_FIELDS:
                r[field_] = text.split("|") if field_ in LIST_FIELDS and text else text
            elif field_ in NUM_FIELDS:
                r[field_] = num
        if yes and r["change"]:
            rows.append(r)
    return {"is_change": bool(rows), "rows": rows}


def to_prediction(records):
    if not records:
        return None
    rows = {i: [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts] for i, rec in enumerate(records)}
    p = parse_records(rows)
    if not p["rows"]:
        return None
    return {"rows": p["rows"]}


SPEC = F.ExtractorSpec(NAME, VERSION, KIND, TAG, extract, FP.code_sha(__file__)) if F else None


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

    a = analyse("Extension of Warrant Expiry Date",
                "Peloton Minerals Corporation will modify the expiry time of certain outstanding warrants of the Company as "
                "follows: 7,614,446 warrants exercisable at a price of CDN$0.10 until 5:00 pm on December 10, 2024 will be "
                "exercisable until 5:00 pm on December 10, 2026.")
    eq("extension read", [(r["change"], r["status"], r["expiry_new"], r["expiry_old"]) for r in a["rows"]],
       [("extension", "effective", ["2026-12-10"], "2024-12-10")])
    a = analyse("Prince Silver Announces $3.0 Million Non-Brokered Private Placement",
                "Each Warrant is exercisable at $1.00 for 24 months from the date of issuance; provided that if the closing "
                "price is $1.40 or higher, the Company will have the right to accelerate the expiry date of the Warrants upon "
                "notice given by press release.")
    eq("WB: an acceleration clause is not a notice", a["rows"], [])
    a = analyse("Lahontan Announces Warrant Acceleration",
                "The Company is electing to accelerate the expiry of outstanding common share purchase warrants issued on "
                "November 25, 2025. The Company is exercising its right to accelerate the expiry of the Warrants to 5:00 p.m. "
                "(Toronto Time) on June 3, 2026 (the \"Accelerated Expiry Date\").")
    eq("acceleration notice", [(r["change"], r["expiry_new"]) for r in a["rows"]], [("acceleration", ["2026-06-03"])])
    a = analyse("Sego Intends to Extend Warrants",
                "Sego Resources Inc. announces it is intending to extend the expiry date of 8,075,000 share purchase warrants "
                "that were issued as part of a private placement completed on May 1, 2024. The original term of each Warrant "
                "entitled the holder to purchase one common share at a price of $0.05 with an expiry date of May 1, 2026. The "
                "Company is intending to extend the expiry date to November 1, 2026. The extension is subject to TSX Venture "
                "Exchange Approval.")
    r = a["rows"][0] if a["rows"] else {}
    eq("proposed extension", (r.get("status"), r.get("expiry_new"), r.get("expiry_old"), r.get("issued"), r.get("strike_old")),
       ("proposed", ["2026-11-01"], "2026-05-01", ["2024-05-01"], 0.05))
    eq("dates: pair with one year", [v for _, _, v in dates_in("March 21st and April 7th 2023")], ["2023-03-21", "2023-04-07"])
    eq("date run across a pair", _date_run("will be March 22nd and April 8th, 2026. All", 7), ["2026-03-22", "2026-04-08"])
    eq("date run, two full dates", _date_run("of November 03, 2025, and November 29, 2025. All", 3), ["2025-11-03", "2025-11-29"])
    eq("a year is not a warrant count", [v for _, v in counts_in("September 2025 Warrant Extension of 11,165,282 outstanding one-half of one "
                                                                  "common share purchase warrants")], [11165282.0])
    h_, t_ = _clean("x", "price of US$0.0 588 each, Nov. 0 3, 2022, Ju ne 24, 2025 and $0\n.10")
    eq("PDF breaks mended", t_, "price of US$0.0588 each, Nov. 03, 2022, June 24, 2025 and $0.10")
    eq("warrant price before an offering price", _strike_in("units at a price of $0.1125 per Share. 6,403,750 warrants, all of which "
                                                           "are exercisable at $0.65 per common share"), 0.65)
    a = analyse("PRISM RESOURCES INC. ANNOUNCES A NON BROKERED UNIT PRIVATE PLACEMENT",
                "Each Warrant is exercisable at a price of $0.35 for a period of three years from issuance, provided however that the "
                "Company shall be entitled to accelerate the expiry date of the Warrants to the date that is 30 days following the date a "
                "notice is provided to the holder announcing the accelerated Expiry Date in the event that the volume weighted average "
                "price exceeds $0.50 for any twenty (20) consecutive trading days.")
    eq("a placement's acceleration clause is not a notice", a["rows"], [])
    a = analyse("Vanguard Mining Corp. Accelerates Warrant Expiry Across Three Financings Following Share Price Strength",
                "The Company is pleased to announce that it has exercised its right to accelerate the expiry of three series of "
                "outstanding common share purchase warrants issued in connection with three previously completed financings.")
    eq("'has exercised its right to accelerate' is an acceleration", [r["change"] for r in a["rows"]], ["acceleration"])
    a = analyse("Golden Goliath Extends Warrants",
                "The Company has applied to the TSX Venture Exchange for acceptance to amend the terms of an aggregate of 7,860,000 "
                "common share purchase warrants issued pursuant to a non-brokered private placement which closed on June 7, 2020. The "
                "Warrants are exercisable at an exercise price of $0.10 per common share, with the Warrants expiring on June 8, 2021. These "
                "Warrants will be amended by extending the expiry date of the Warrants to June 8, 2022. No Warrants issued under the "
                "Private Placement have been exercised in the last 6 months.")
    eq("extension read, 'no warrants have been exercised' is no exercise",
       [(r["change"], r["expiry_new"], r["expiry_old"], r["issued"]) for r in a["rows"]],
       [("extension", ["2022-06-08"], "2021-06-08", ["2020-06-07"])])
    a = analyse("Hard Creek Nickel Accelerated Warrant Exercise Clause",
                "The Company's shares have traded at more than $0.065 per share for 10 consecutive trading days, and certain warrants will "
                "now be subject to their accelerated exercise clause. The warrants in question were repriced from an exercise price of $0.08 "
                "per share, as detailed in a news release dated November 16, 2015. The accelerated clause affects 1,686,693 warrants with an "
                "exercise price of $0.05 which now expire April 1, 2017 instead of November 27, 2017.")
    eq("acceleration with 'now expire X instead of Y'", [(r["change"], r["expiry_new"], r["expiry_old"], r["n_warrants"]) for r in a["rows"]],
       [("acceleration", ["2017-04-01"], "2017-11-27", 1686693.0)])
    a = analyse("ANGKOR Extends Warrant Expiry Date",
                "ANGKOR GOLD CORP. announces that further to the Company's news release of April 11, 2017 that its application to extend "
                "the expiry date of its warrants was accepted by the TSX Venture Exchange. Accordingly, the expiry date for the 1,563,000 "
                "common share warrants previously set to expire on July 29, 2017 has been extended to July 29, 2018.")
    eq("an accepted extension is effective", [(r["status"], r["expiry_new"], r["expiry_old"]) for r in a["rows"]],
       [("effective", ["2018-07-29"], "2017-07-29")])
    a = analyse("American Critical Minerals Extends Warrant Exercise Incentive Program",
                "The Program is intended to encourage the early exercise of up to 4,620,800 warrants previously issued in connection with "
                "a private placement and which are currently exercisable at a price of $0.1875 per share. The Company has elected to extend "
                "the deadline for the Program until August 15, 2025 (the \"Program End Date\"). Each New Warrant will be exercisable at a "
                "price of $0.28 until August 6, 2027.")
    eq("programme end date named as such", [(r["change"], r["program_end"], r["strike_old"]) for r in a["rows"]],
       [("incentive", "2025-08-15", 0.1875)])
    eq("a unit price never beats the warrant's", _strike_in("units priced at $0.25 each. Each full warrant entitling the holder to purchase "
                                                            "one additional common share of the Company at a price of $0.40 per share"), 0.40)
    a = analyse("New Break Receives $2,000,520 from the Early Exercise of Warrants",
                "On completion of the Acceleration, 100% of the Warrants were exercised including 14,546,000 at $0.12 per share and "
                "1,250,000 at $0.15 per share for aggregate gross proceeds of $1,933,020. In addition, 337,500 warrants that were not "
                "part of the Acceleration, having a strike price of $0.20 per share and an expiry date of June 23, 2026, were exercised "
                "for aggregate gross proceeds of $67,500. Only 2,236,350 common share purchase warrants remain outstanding, including "
                "736,350 at $0.20 per share and 1,500,000 at $0.25 per share. The expiry date of the Warrants was accelerated to twenty "
                "(20) calendar days after the date of the notice, being October 14, 2025.")
    eq("exercise rows by strike", [(r["n_exercised"], r["strike_old"], r["expiry_new"], r["n_remaining"], r["proceeds"], r["expiry_old"])
                                   for r in a["rows"]],
       [(14546000.0, 0.12, ["2025-10-14"], 0, None, None), (1250000.0, 0.15, ["2025-10-14"], 0, None, None),
        (337500.0, 0.2, [], None, 67500.0, "2026-06-23")])
    print("warrant_changes: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test(verbose="-v" in sys.argv) else 0)
