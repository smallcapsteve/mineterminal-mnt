"""Corporate calendar reader, facts-store version (CAL_V1, 2026-10-12). Rules only.

Dated corporate events a company's own release reports: shareholder meetings, results release dates, results calls and
webcasts, dividends (record + payment), normal course issuer bids, conference presentations, and the corporate actions
- consolidations, name and symbol changes, arrangements / amalgamations, spin-outs, listings / delistings, take-over
bids, rights offerings. Written against the 90-release key (seed 20261012) and measured on two fresh blind draws
(claude/MNT_EVENTS_READERS_2026-10-07.md section 8).

Rule calls: CA-CH (defaults in the brief), Justin 2026-10-12: CD1 a dividend is one row with its record date (the page
shows both dates), CO1 OTC / Frankfurt symbol changes and quotations are stored with show = 0, CP1 presentations carry
role presenting / attending, CN1 a future event with no stated day is a row with no date ("date to be announced"),
name changes already made but trading later are scheduled on the trading date. 1.0.2 (2026-10-19): CM1 an "Upcoming
marketing" list of conferences with no role stated is Attending with the conference dates; CV1 a vertical
amalgamation with the company's own wholly-owned subsidiary is stored with show = 0.

A release date is needed to finish a row: "today", a date with no year, and the status (completed / scheduled) depend
on it. extract() is a pure function of the text, so it stores the dateline the text gives (when it gives one) and the
status cues as letters; resolve(row, published_at) finishes each row the same way for the publisher and the scorer.

analyse(headline, body) -> {"dl": date|None, "events": [event]}      (pure; no database, no clock)
extract(headline, body) -> [Record]                                   one record per event, or one no-event record
parse_records(rows_by_ordinal) -> {"dl": iso|None, "events": [...]}  back from the facts store
resolve(event, published_at, dateline) -> row                         {kind, status, date, exact, end_date, time,
                                                                       record_date, detail, venue, role, show}
read(headline, body, published_at) -> [row]                           all of it, through the facts layer

Self-tests: python3 -m portal.extractors.corp_calendar
"""
from __future__ import annotations

try:
    from portal import facts as F
    from portal import fingerprint as FP
except Exception:  # pragma: no cover - standalone development outside the app
    F = FP = None

NAME = "calendar"
VERSION = "1.0.2"
KIND = "calendar_event"
TAG = "Corporate Actions"     # the events come from many tags; tag_confirmed only records whether a release carries this one
TEXT_CAP = 40000

import re
from datetime import date, timedelta

MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split())}
for _k, _v in list(MONTHS.items()):
    MONTHS[_k[:3]] = _v
MONTHS["sept"] = 9
_MON = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DAY = r"(?:Mon|Tues?|Wed(?:nes)?|Thu(?:rs?)?|Fri|Sat(?:ur)?|Sun)(?:day)?\.?,?\s+"
_ORD = r"(?:st|nd|rd|th)?"
# Month D[-D2][, YYYY]   |   D[-D2] Month[,] [YYYY]   |   YYYY-MM-DD
DATE_RE = re.compile(
    r"(?:" + _DAY + r")?\b(?P<mon>" + _MON + r")\.?\s+(?P<d>\d{1,2})" + _ORD +
    r"(?:\s*(?:-|\u2013|\u2014|to|and|&|through)\s*(?:(?P<mon2>" + _MON + r")\.?\s+)?(?P<d2>\d{1,2})" + _ORD + r")?"
    r"(?![\d:])(?:,?\s+(?P<y>20\d\d)\b)?"
    r"|(?:" + _DAY + r")?\b(?P<dA>\d{1,2})" + _ORD + r"(?:\s*(?:-|\u2013|to|and)\s*(?P<d2A>\d{1,2})" + _ORD + r")?\s+(?:of\s+)?"
    r"(?P<monA>" + _MON + r")\b(?!\.?,?\s+\d{1,2}(?:st|nd|rd|th)?\b(?!\d))\.?,?(?:\s+(?P<yA>20\d\d)\b)?"
    r"|(?<![.#/])\b(?P<yI>20\d\d)-(?P<mI>[01]\d)-(?P<dI>[0-3]\d)\b", re.I)
MONTH_ONLY_RE = re.compile(r"\b(?:(?P<q>early|mid|late|end of|the end of|beginning of)[\s-]+)?(?P<mon>" + _MON +
                           r")\.?,?\s+(?P<y>20\d\d)\b", re.I)
REL_RE = re.compile(r"\b(today|tomorrow|yesterday|this (?:morning|afternoon|evening))\b", re.I)
TIME_RE = re.compile(
    r"\b\d{1,2}(?:[:.]\d{2})?\s*(?:a\.?\s?m\.?|p\.?\s?m\.?|noon)(?:\s*(?:-|\u2013|to)\s*\d{1,2}(?:[:.]\d{2})?\s*(?:a\.?m\.?|p\.?m\.?))?"
    r"(?:\s*\(?(?:ET|EST|EDT|PT|PST|PDT|MT|MST|MDT|CT|CST|CDT|AEST|AEDT|AWST|AWDT|GMT|UTC|BST|CET|CEST|Eastern|Pacific|Mountain|Central|"
    r"Vancouver|Toronto|Perth|Sydney)(?:\s+(?:Standard|Daylight))?(?:\s+Time)?\)?)?"
    r"|\bnoon\b(?:\s*\(?(?:ET|EST|EDT|PT|Eastern|Pacific)(?:\s+Time)?\)?)?", re.I)
MONEY_RE = re.compile(r"(?P<cur>US|U\.S\.|C|CA|CAD|CDN|Cdn|A|AU|AUD)?\s?\$\s?(?P<amt>\d+(?:\.\d+)?)(?:\s*(?P<cents>cents?))?"
                      r"|(?P<amt2>\d+(?:\.\d+)?)\s*(?P<cur2>cents?|\u00a2)", re.I)
VENUES = [("TSXV", r"TSX[\s.-]?V(?:enture)?(?:\s+Exchange)?|TSX Venture Exchange|\bTSXV\b|\bthe Exchange\b(?=[^.]{0,0})"),
          ("TSX", r"Toronto Stock Exchange|\bTSX\b(?![\s.-]?V)"), ("CSE", r"Canadian Securities Exchange|\bCSE\b"),
          ("NYSE", r"NYSE(?: American)?|New York Stock Exchange"), ("NASDAQ", r"\bNasdaq\b"),
          ("OTC", r"\bOTC(?:QX|QB|PK|\s+Markets?|\s+Pink)?\b|\bOTCQ[XB]\b|\bPink Sheets\b"),
          ("FSE", r"Frankfurt|\bFSE\b|\bFWB\b|\bFRA\b"), ("ASX", r"\bASX\b|Australian Securities Exchange"),
          ("LSE", r"London Stock Exchange|\bAIM\b|\bLSE\b")]
NUMW = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                     "fifteen sixteen seventeen eighteen nineteen twenty".split())}
NUMW.update({"twenty-five": 25, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100, "one hundred": 100})


# ------------------------------------------------------------------ text
def _norm(t):
    t = (t or "").replace("\u00a0", " ").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"') \
        .replace("\u201d", '"').replace("\u2013", "-").replace("\u2014", "-")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\b(20[0-3]) (\d)\b", r"\1\2", t)           # "202 5" (PDF breaks inside years)
    t = re.sub(r"\b(FY20[0-3]) (\d)\b", r"\1\2", t)
    t = re.sub(r"(\w) -(\w)", r"\1-\2", t)                    # "post -consolidation", "one -for-three"
    t = re.sub(r"(\w)- (\w)", r"\1-\2", t)
    t = re.sub(r"\b(\d{1,2}) (st|nd|rd|th)\b", r"\1\2", t)         # CAL 1.0.2: "January 23 rd 2026", "October 16 th"
    return t.strip()


def _sentences(t):
    """Sentence-ish units with their offsets. Also breaks before bold-style labels ("Date:", "Time:")."""
    out, start = [], 0
    for m in re.finditer(r"(?<=[.!?;])\s+(?=[A-Z\"(\u2022])|\s+(?=\u2022\s)|\s+(?=(?:[A-Z][A-Za-z ]{2,40}):\s)", t):
        if m.start() - start > 0:
            out.append((start, t[start:m.start()]))
        start = m.end()
    out.append((start, t[start:]))
    out = [(o, s) for o, s in out if s.strip()]
    # an abbreviation is not the end of a sentence ("10:00 a.m. ET", "Alpha Gold Corp. Announces")
    merged = []
    for o, s in out:
        if merged and (re.search(r"(?:\b[ap]\.\s?m\.|\b(?:Inc|Corp|Ltd|Co|No|St|Mr|Ms|Mrs|Dr|U\.S|approx|Ave|Jr)\.)\s*$",
                                 merged[-1][1]) or (re.fullmatch(r"(?:Upcoming|Recent|Future)", merged[-1][1].strip()) and
                                                    re.match(r"[A-Z][A-Za-z ]{2,40}:", s))):
            po, ps = merged[-1]
            merged[-1] = (po, ps + " " + s)
        else:
            merged.append((o, s))
    return merged


def _iso(y, m, d):
    try:
        return date(y, m, d).isoformat()
    except (TypeError, ValueError):
        return None


def find_dates(s):
    """Dates in s: list of dicts {s, e, y, m, d, y2, m2, d2}. y may be None."""
    out = []
    for m in DATE_RE.finditer(s):
        g = m.groupdict()
        if g["mon"]:
            mo, d, d2, y, mo2 = MONTHS[g["mon"].lower().rstrip(".")[:4] if g["mon"].lower().startswith("sept") else
                                     g["mon"].lower()[:3]], int(g["d"]), g["d2"], g["y"], g["mon2"]
            # "May 2026" is a month, not May 20 -- a 2-digit "day" followed by more digits is excluded by (?![\d:])
        elif g["monA"]:
            mo, d, d2, y, mo2 = MONTHS[g["monA"].lower()[:3]], int(g["dA"]), g["d2A"], g["yA"], None
        else:
            mo, d, d2, y, mo2 = int(g["mI"]), int(g["dI"]), None, g["yI"], None
        if not 1 <= d <= 31:
            continue
        y = int(y) if y else None
        m2 = MONTHS[mo2.lower()[:3]] if mo2 else mo
        dd2 = int(d2) if d2 and 1 <= int(d2) <= 31 else None
        if dd2 is not None and m2 == mo and dd2 <= d:      # "May 5 and 2" -- not a range
            dd2 = None
        out.append({"s": m.start(), "e": m.end(), "y": y, "m": mo, "d": d, "m2": m2 if dd2 else None, "d2": dd2})
    return out


def split_header(t):
    """(header, rest, dateline): the release date as the text gives it is the first full date in the first 900
    characters that does not read as an event date ("... results on October 30, 2025"); the header (letterhead, repeated
    headline, dateline) ends there. No dateline: header empty."""
    for dt in find_dates(t[:900]):
        if not dt["y"] or not _iso(dt["y"], dt["m"], dt["d"]) or dt.get("d2"):
            continue
        pre = t[max(0, dt["s"] - 14):dt["s"]].lower()
        if re.search(r"\b(?:on|by|until|before|after|of|from|held|dated|ended|ending|to|at|effective|than)\s*[:(]?\s*$", pre):
            continue
        return t[:dt["e"]], t[dt["e"]:], date(dt["y"], dt["m"], dt["d"])
    return "", t, None


def find_dateline(t):
    return split_header(t)[2]


def _venue(s):
    for name, pat in VENUES:
        if re.search(pat, s):
            return name
    return None


def _times(s):
    return [m.group(0).strip() for m in TIME_RE.finditer(s)]



# CAL 1.0.1 (2026-10-18): fixes from the 10-14 spot check of live events (claude/MNT_EVENTS_READERS_2026-10-07.md s.8)
# website navigation saved inside a release body (Kinross: the site's "Annual Meeting" menu link and "Events Calendar")
NAV = re.compile(r"Skip to (?:main )?content|Events Calendar\s+Upcoming Events|Upcoming Events\s+Past Events|"
                 r"RSS Feeds|Receive (?:Email )?Alerts|Help Centre|Fraud Alert|Media Gallery|Stock Info\b|Analyst Coverage|"
                 r"Privacy Policy\s+Terms", re.I)
# an industry body's meeting in a list of events the company will attend (PGE.V: "AEMA Annual Meeting - Sparks, NV")
MEET_THIRD = re.compile(r"\b[A-Z]{2,6}\s+(?:Annual|Winter|Summer|Fall|Spring|General)\s+(?:General\s+)?Meeting\b|"
                        r"\b(?:Association|Society|Institute|Council|Chamber|Federation|Club)\b[^.]{0,30}\bMeeting\b|"
                        r"\bMeeting\s*[-\N{EN DASH}\N{EM DASH}]\s*[A-Z][a-z]+,")
LIST_INTRO = re.compile(r"\b(?:attend(?:ing)?|participat(?:e|ing) in|present(?:ing)? at|exhibiting at|be at)\s+the following\b|"
                        r"\bthe following (?:upcoming )?(?:investor )?(?:conferences|events|shows|marketing events)\b|"
                        r"\bUpcoming (?:Events|Marketing|Conferences)\s*:", re.I)
GENERIC_CONF = re.compile(r"^(?:(?:the|our|these|upcoming|following|other|recent|several|various|industry|investor|"
                          r"marketing)\s+)*(?:events?|conferences?|meetings?|shows?)$", re.I)
NA_ZONE = r"(?:EDT|EST|ET|PDT|PST|PT|MDT|MST|MT|CDT|CST|CT|Eastern|Pacific|Mountain|Central|Toronto|Vancouver|New York)"
FOREIGN_ZONE = re.compile(r"\b(?:AEDT|AEST|AWST|AWDT|ACST|ACDT|NZDT|NZST|GMT|BST|CET|CEST|SAST|HKT|SGT|JST|Perth|Sydney|"
                          r"Melbourne|Brisbane|London|Johannesburg|Hong Kong)(?![A-Za-z])")
BULLET = re.compile(r"\s*[\N{BULLET}\N{MIDDLE DOT}*\N{EN DASH}-]")


def _na_when(text):
    """A call given in an overseas zone and in a North American one -> (date, time) of the North American one
    ("11.00am AEDT (Tuesday, 13 October 2026, at 8.00pm EDT)"; "Toronto, Canada 7:00pm EDT, Thursday, 22 October
    2026"). None when the text names no overseas zone or gives no North American time with a date near it."""
    if not FOREIGN_ZONE.search(text):
        return None
    ds = find_dates(text)
    for m in TIME_RE.finditer(text):
        tm = m.group(0)
        z = re.match(r"\s*\(?(" + NA_ZONE + r")\b", text[m.end():m.end() + 14])
        if not re.search(r"\b" + NA_ZONE + r"\b", tm) and not z:
            continue
        gap = lambda x: min(abs(x["s"] - m.end()), abs(m.start() - x["e"]))
        near = sorted([x for x in ds if gap(x) <= 60], key=gap)
        if near:
            tm = tm.strip()
            if tm.endswith(")") and "(" not in tm:
                tm = tm[:-1].rstrip()
            return near[0], tm + (" " + z.group(1) if z else "")
    return None


CONF_AT = re.compile(r"\b(?:at|in)\s+(?:the\s+)?([A-Z0-9][\w&'.-]*(?:\s+(?:[A-Z0-9][\w&'.+-]*|the|of|and|for|on|in|&)){0,9}?"
                     r"\s+(?:Conference|Summit|Forum|Symposium|Show|Expo|Roundup|Convention|Showcase|Investor Day)"
                     r"(?:\s+(?:[A-Z][\w&'-]*|20\d\d)){0,3})")


def _conf_name(s, after=0):
    """The conference's own name, not a heading like "Upcoming Events" (Q2 Metals, Stallion on 10-14)."""
    m = CONF_AT.search(s, after)
    if m and not GENERIC_CONF.match(m.group(1)):
        return m.group(1).strip()
    best = None
    for m in CONF_NAME.finditer(s):
        nm = m.group(1).strip()
        nm2 = re.sub(r"^(?:Upcoming|Recent|Following)\s+(?:Events?|Conferences?)\s*:?\s*", "", nm).strip()
        if not nm2 or GENERIC_CONF.match(nm2) or GENERIC_CONF.match(nm):
            continue
        if best is None or (m.start() >= after and best[0] < after):
            best = (m.start(), nm2)
        if m.start() >= after:
            break
    return best[1] if best else None


def _list_items(block):
    """Each "<name> [place] <date or date range>" item of a list of events -> [(name, date)]."""
    out, prev = [], 0
    for x in find_dates(block):
        nm = block[prev:x["s"]]
        prev = x["e"]
        nm = re.sub(r"^[\s,.;:\N{BULLET}\N{MIDDLE DOT}*-]+|[\s,.;:(\N{EN DASH}\N{EM DASH}-]+$", "", nm)
        nm = re.sub(r"^(?:and|&)\s+", "", nm)
        nm = re.sub(r"^(?:upcoming\s+)?(?:investor\s+)?(?:conferences?|events?|shows?)(?:\s+and\s+(?:conferences?|events?))?"
                    r"\s*:\s*", "", nm, flags=re.I)
        nm = re.sub(r"\s+[-\N{EN DASH}\N{EM DASH}]\s+(?:[A-Z][\w.]*,?\s*){1,5}$", "", nm)
        if 3 <= len(nm) <= 110 and re.search(r"[A-Z]", nm) and not re.search(
                r"\b(?:will|would|shall|has|have|are|is|was|were|on|at)\s*$|\b(?:will|would|shall)\b", nm):
            out.append((nm.strip(), x))
    return out


# ------------------------------------------------------------------ status
PROPOSED = re.compile(r"\b(?:subject to (?:the )?(?:receipt of |obtaining |final )?(?:all )?(?:shareholder|TSX|exchange|"
                      r"regulatory|court|board|the approval|approval|acceptance|CSE|the (?:TSXV|TSX|CSE|Exchange))|"
                      r"propos(?:es|ed|ing)|intends? to|intention to|plans? to|seek(?:s|ing)? (?:shareholder )?approval|"
                      r"will seek|anticipated to|expected to (?:be|occur|close|take|complete)|expects? to|if approved|"
                      r"would (?:be|result))\b", re.I)
DONE_PROPOSAL = re.compile(r"\b(?:received|obtained|approved by|accepted)\b[^.]{0,60}\b(?:approval|acceptance|"
                           r"shareholders)\b", re.I)
CANCEL = re.compile(r"\b(?:cancel(?:led|s|ling)?|will not (?:proceed|be proceeding)|not (?:to )?proceed|withdr[ae]w[ns]?|"
                    r"terminat(?:ed|es|ion of)|abandon)", re.I)
POSTPONE = re.compile(r"\b(?:postpone[ds]?|adjourn(?:ed|s|ment)|delay(?:ed|s)|reschedul(?:ed|es))\b", re.I)
PAST = re.compile(r"\b(?:was held|were held|held (?:on|earlier|today|yesterday)|has (?:been )?(?:completed|closed|"
                  r"effected|implemented)|have been (?:consolidated|completed)|completed (?:the|its)|is pleased to "
                  r"(?:confirm|report) (?:the )?(?:completion|closing)|voting results|were (?:elected|approved|"
                  r"re-elected)|was (?:approved|completed|effected|closed)|commenced trading|began trading|"
                  r"took effect|became effective|has changed its name)\b", re.I)
FUTURE = re.compile(r"\b(?:will|to be held|shall|scheduled|is expected|are expected|expects|anticipated|upcoming|"
                    r"effective (?:as )?(?:of|on|at)|at the opening|at market open|payable|on or about)\b", re.I)


MEET_PAST = re.compile(r"(?<!to be )(?<!will be )\bheld\b|voting results|results of (?:the |its )?(?:annual|special|AGM|"
                       r"meeting)|\b(?:were|was) (?:elected|approved|re-elected|passed)|approved (?:all|each|every)|"
                       r"shareholders (?:approved|elected|voted)|at the (?:annual|special|AGM)[^.]{0,80}(?:approved|elected)",
                       re.I)


def _flags(sent, kind):
    """The status cues of a sentence, as letters (stored with the event so the status can be decided again once the
    release date is known): M meeting held, C cancelled, P postponed, R proposal pending, E effective/commencing,
    A past tense, W later the same day."""
    f = ""
    if kind == "meeting" and MEET_PAST.search(sent) and not re.search(r"\b(?:will be|to be) held\b", sent, re.I):
        f += "M"
    if CANCEL.search(sent) and kind not in ("ncib",) and not re.search(r"\brisks?\b|\bmay not\b|\bcould\b|uncertaint|"
                                                                      r"no assurance|in the event", sent, re.I):
        f += "C"
    if POSTPONE.search(sent) and kind in ("meeting", "conference_call", "results_release", "presentation"):
        f += "P"
    if PROPOSED.search(sent) and not DONE_PROPOSAL.search(sent):
        f += "R"
    if re.search(r"\b(?:effective|will (?:commence|begin)|expected to (?:begin|commence))", sent, re.I):
        f += "E"
    if PAST.search(sent):
        f += "A"
    if re.search(r"\b(?:will|later today|this (?:morning|afternoon))\b", sent, re.I):
        f += "W"
    return f


def status_from(f, kind, dt_iso, dl, has_date):
    """Status from the cue letters and the event date against the release date."""
    if "M" in f and (not dt_iso or not dl or date.fromisoformat(dt_iso) <= dl):
        return "completed"
    if "C" in f:
        return "cancelled"
    if "P" in f:
        return "postponed"
    prop = "R" in f
    if dt_iso and dl:
        d = date.fromisoformat(dt_iso)
        if d < dl:
            return "completed"
        if d > dl:
            if prop and kind in CORPORATE and "E" not in f:
                return "proposed"
            return "scheduled"
        if "A" in f and "W" not in f:      # the release date itself
            return "completed"
        return "scheduled"
    if not has_date:
        if "A" in f:
            return "completed"
        if kind in ("meeting", "conference_call", "presentation") and not prop:
            return "scheduled"
        return "proposed"
    if "A" in f:
        return "completed"
    return "proposed" if prop else "scheduled"


def _status(sent, kind, dt_iso, dl, has_date):
    return status_from(_flags(sent, kind), kind, dt_iso, dl, has_date)


CORPORATE = ("consolidation", "name_change", "symbol_change", "arrangement", "spinout", "listing", "rights_offering",
             "takeover_bid")
DATED = ("meeting", "results_release", "conference_call", "dividend", "presentation", "ncib")


# ------------------------------------------------------------------ cues per kind
RESULTS_FUT = re.compile(r"\b(?:will|to|plans? to|expects? to|intends? to|is scheduled to|anticipates?)\s+(?:be\s+)?"
                         r"(?:release|report|publish|announce|issue|file|disclose)\w*\b|\bresults? release(?:\s+date)?\b|"
                         r"\b(?:release|reporting) date\b|\bearnings release\b|\bnotice of (?:the )?release\b", re.I)
RESULTS_OBJ = re.compile(r"(?:quarter(?:ly)?|year[\s-]end|full[\s-]year|annual|fiscal|financial|operating|interim|"
                         r"half[\s-]year|Q[1-4]|FY\s?20\d\d|20\d\d)\b[^.]{0,60}?\b(?:results|earnings)|\bearnings\b|"
                         r"\bfinancial statements\b|\bfinancials\b", re.I)
CALL = re.compile(r"\b(?:conference call|teleconference|earnings call|webcast|investor call|analyst call|"
                  r"call and webcast|live call)\b", re.I)
MEETING = re.compile(r"\b(?:annual(?: general)?(?: and special)?(?: general)? meeting|special(?: general)? meeting|"
                     r"annual and special meeting|annual general and special meeting|\bAGM\b|\bAGSM\b|\bASM\b|"
                     r"meeting of (?:the )?(?:shareholders|securityholders|unitholders|holders)|shareholders'? meeting)",
                     re.I)
DIVIDEND = re.compile(r"\bdividends?\b", re.I)
NCIB = re.compile(r"\bnormal course issuer bid\b|\bNCIB\b|\bshare (?:buyback|repurchase) (?:program|plan)", re.I)
CONSOL = re.compile(r"\b(?:share )?consolidat(?:e|ion|ed|ing)\b|\breverse (?:stock |share )?split\b", re.I)
NAMECHG = re.compile(r"\bchange (?:of )?its (?:corporate )?name\b|\bname change\b|\bchanged its name\b|"
                     r"\b(?:new|corporate) name\b|\brenam(?:e|ed|ing)\b", re.I)
SYMBOL = re.compile(r"\b(?:new )?(?:trading |ticker |stock )?symbol\b|\bticker\b", re.I)
ARRANGE = re.compile(r"\bplan of arrangement\b|\bamalgamat(?:e|ion|ed)\b|\bbusiness combination\b|\bmerger\b|"
                     r"\barrangement agreement\b|\bacquisition of all of the (?:issued and )?outstanding\b", re.I)
SPIN = re.compile(r"\bspin[\s-]?out\b|\bspinout\b|\bspin[\s-]?off\b", re.I)
LISTING = re.compile(r"\bgraduat(?:e|ion|ed|ing)\b|\bdelist(?:ed|ing)?\b|\b(?:begin|commence|start)s? trading\b|"
                     r"\bto list\b|\bnew listing\b|\buplist(?:ing)?\b|\blisting (?:of|on)\b|\bhalt(?:ed)? (?:will be )?"
                     r"lifted|\bresum(?:e|ption of) trading\b", re.I)
PRESENT = re.compile(r"\b(?:present(?:ing|s)? at|to present|will present|presentation at|participat(?:e|ion|ing) (?:in|at)|"
                     r"attend(?:ance|ing)?\b|moderat(?:e|or|ing)|panel(?:ist)?\b|showcase|exhibit(?:ing)? at|booth|investor day|keynote|speak(?:ing|er) at|"
                     r"fireside chat|join (?:us|management) at|visit (?:us|the company) at|sponsor(?:ship|ing)?)\b", re.I)
CONF_NAME = re.compile(r"(?:the\s+)?((?:[A-Z0-9][\w&'.-]*\s+){0,9}?(?:Conference|Summit|Forum|Symposium|Show|Expo|"
                       r"Investor Day|Roundup|Convention|Showcase|Event|Meeting|PDAC|VRIC)(?:\s+(?:[A-Z][\w&'-]*|20\d\d)){0,3})")
SYMCHG = re.compile(r"\bsymbol change\b|\bnew (?:trading |ticker |stock )?symbol\b|\bsymbol (?:will )?(?:change|be changed)|"
                    r"\bchange (?:of |in |its |to its )?(?:the )?(?:trading |ticker |stock )?symbol|ticker (?:symbol )?(?:will )?"
                    r"change|\bsymbol (?:has been |was )?changed|\b(?:name|symbol) change\b|\bchange its name\b|"
                    r"\bnew name\b", re.I)
RIGHTS = re.compile(r"\brights offering\b", re.I)
TAKEOVER = re.compile(r"\btake[\s-]?over bid\b|\btender offer\b", re.I)


NOT_EVENT_DATE = re.compile(r"(?:dated|ended|ending|period end(?:ed|ing)?|as at|news release (?:of|on|issued on)|"
                            r"press release (?:of|on|issued on)|announced on|circular dated|until|archived until|"
                            r"available until|Newsfile Corp\.?\s*-|Newswire\s*[-/]|NEWSWIRE\s*[-/)]?|/CNW/|"
                            r"Newswire\s*/)\s*[:(]?\s*$", re.I)


def _pick_date(s, after=0, dates=None):
    ds = dates if dates is not None else find_dates(s)
    for dt in ds:
        if dt["s"] >= after and not NOT_EVENT_DATE.search(s[max(0, dt["s"] - 40):dt["s"]]):
            return dt
    return None


_NUM_W = r"(?:\d+(?:\.\d+)?|(?:(?:twenty|thirty|forty|fifty)[\s-]?)?(?:one|two|three|four|five|six|seven|eight|nine)|ten|" \
         r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|" \
         r"one hundred|hundred)(?:\s+and\s+(?:one[\s-]half|a half))?(?:\s*\(\s*\d+(?:\.\d+)?\s*\))?"
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}


def _num(x):
    """'twenty-five (25)' -> 25, 'three and one-half (3.5)' -> 3.5, '10' -> 10."""
    m = re.search(r"\(\s*(\d+(?:\.\d+)?)\s*\)", x)
    if m:
        return float(m.group(1))
    x = x.lower().strip()
    if re.match(r"\d", x):
        return float(re.match(r"\d+(?:\.\d+)?", x).group(0))
    half = 0.5 if re.search(r"half", x) else 0.0
    x = re.split(r"\s+and\s+", x)[0]
    if x in ("one hundred", "hundred"):
        return 100.0 + half
    parts = re.split(r"[\s-]+", x)
    v = 0
    for p in parts:
        v += _TENS.get(p, NUMW.get(p, 0))
    return float(v) + half if v else None


def _ratio(s):
    """'one new for every ten old' -> '10:1'; 'up to 20:1' kept as 'up to 20:1'."""
    OLD = r"(?:old|pre[\s-]?consolidat\w*|existing|issued and outstanding|outstanding|current)"
    NEW = r"(?:new|post[\s-]?consolidat\w*)"
    pats = [
        r"\b(?:one|1)\s*(?:\(1\)\s*)?" + NEW + r"[^.]{0,140}?(?:for|per)\s+(?:every|each)\s+(?P<v>" + _NUM_W + r")\s*" + OLD,
        r"(?P<v>" + _NUM_W + r")\s*" + OLD + r"[^.]{0,100}?(?:for|into|to)\s+(?:each\s+|every\s+)?(?:one|1)\s*(?:\(1\)\s*)?"
        r"(?:" + NEW + r"|common|share)",
        r"ratio of (?:up to )?(?P<v>" + _NUM_W + r")\s*(?:" + OLD + r")?[^.]{0,40}?(?:to|for)\s+(?:one|1)\b",
        r"\b(?P<v>\d+(?:\.\d+)?)\s*(?::|-for-|\s+for\s+|\s+to\s+)\s*1\b(?!\d|[.,]\d)",
        r"\b1\s*(?::|-for-)\s*(?P<v>\d+(?:\.\d+)?)\b",
        r"\bone[\s-]for[\s-](?P<v>" + _NUM_W + r")\b",
    ]
    for p in pats:
        m = re.search(p, s, re.I)
        if m:
            v = _num(m.group("v"))
            if v and 1 < v <= 1000:
                up = re.search(r"\bup to\b|\bmaximum (?:ratio )?of\b|\bnot (?:to )?exceed", s[max(0, m.start() - 60):m.start() + 30], re.I)
                return ("up to " if up else "") + ("%g:1" % v)
    return None


def _name_after(s, pat):
    m = re.search(pat + r"""\s*(?:to\s+)?(?:the name\s+)?["']?\s*([A-Z][\w&.'\- ]{2,70}?(?:Corp(?:oration)?|Inc|Ltd|"""
                  r"""Limited|Resources|Metals|Mining|Minerals|Gold|Silver|Uranium|Royalties|Group|Holdings|Ventures|Co)"""
                  r"""\.?)(?:\s*/\s*([A-Z][^"']{2,60}?))?\s*["']?(?=[\s,.(;]|$)""", s)
    return m.group(1).strip() if m else None


def _symbol_after(s):
    m = re.search(r"""(?:new|change to|changed to|under the (?:new )?(?:trading |ticker |stock )?symbol|symbol (?:will )?"""
                  r"""(?:change|be changed) (?:from [^.]{1,30}? )?to|ticker(?: symbol)? (?:will )?(?:change|be changed)"""
                  r"""(?: from \W*[A-Z.]{1,8}\W*)? to|trade under(?: the (?:new )?(?:symbol|ticker))?)\s*:?\s*["'(]?\s*"""
                  r"""([A-Z][A-Z0-9.]{0,7})\b""", s)
    if m and m.group(1) not in ("THE", "TSX", "TSXV", "CSE", "OTC", "A", "I"):
        return m.group(1)
    return None


def _period(s):
    s2 = s
    m = re.search(r"\b(first|second|third|fourth|1st|2nd|3rd|4th)[\s-]+quarter(?:\s+(?:of\s+)?(?:fiscal\s+|FY\s*)?(20\d\d))?",
                  s2, re.I)
    q = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}
    parts = []
    if m:
        ym = re.search(r"\b(20\d\d)\b", s2[max(0, m.start() - 15):m.end() + 40])
        y = m.group(2) or (ym.group(1) if ym else None)
        parts.append(("Q%d %s" % (q[m.group(1).lower()], y or "")).strip())
    else:
        m = re.search(r"\bQ([1-4])[\s-]*(?:FY\s*)?(20\d\d)?\b|\b(20\d\d)\s+Q([1-4])\b", s2)
        if m:
            parts.append(("Q%s %s" % (m.group(1), m.group(2) or "") if m.group(1) else "Q%s %s" % (m.group(4), m.group(3))).strip())
    m = re.search(r"\b(?:full[\s-]year|year[\s-]end|annual|fiscal(?: year)?)\s+(20\d\d)|\b(20\d\d)\s+(?:full[\s-]year|year[\s-]end|annual)",
                  s2, re.I)
    if m:
        parts.append("FY %s" % (m.group(1) or m.group(2)))
    return " / ".join(parts) or None


# ------------------------------------------------------------------ CAL 1.0.2 helpers
VOTE_HL = re.compile(r"\bvoting results\b|\bresults? of (?:the |its )?(?:20\d\d )?(?:annual|special|AGM|AGSM|shareholder|"
                     r"meeting)|\b(?:AGM|AGSM|meeting) results\b|shareholders approve", re.I)
WEBCAST_PRES = re.compile(r"\bpresentation at (?:the )?[^.]{0,90}?\b(?:conference|summit|forum|showcase)\b(?!\s+call)|"
                          r"\bvirtual (?:investor )?(?:conference|summit)\b(?!\s+call)", re.I)
MEET_VIA_WEBCAST = re.compile(r"meeting[^.]{0,120}?\b(?:held |conducted )?(?:virtually |online )?(?:via|by) (?:live )?"
                              r"(?:audio )?webcast", re.I)
SAME_DAY = re.compile(r"\b(?:the same day|that same day|later that day|that (?:morning|afternoon|day)|on the same day|"
                      r"the following (?:morning|day)|the next (?:morning|day))\b", re.I)
_EXCH = r"(?:TSX[\s.-]?V(?:enture)?|TSX|CSE|NEO|Cboe|NYSE(?: American)?|NASDAQ|Nasdaq|ASX|AIM|OTC\w*|FSE|FRA|Frankfurt)"
_CO_END = r"(?:Corp(?:oration)?|Inc|Ltd|Limited|Resources|Metals|Mining|Minerals|Gold|Silver|Uranium|Energy|Copper|Royalt\w+|Group|Holdings|Ventures|Mines|Exploration)"


def _issuer(text):
    """The name of the company the release is from: the name just before the first "(EXCH: SYM" in the text."""
    m = re.search(r"([A-Z][\w&'.-]*(?:\s+[A-Z&][\w&'.-]*){0,5})\s*,?\s*\(\s*\"?[^)]{0,30}?\b" + _EXCH + r"\s*[:-]", text)
    if not m:
        return None
    nm = re.sub(r"^(?:.*\b(?:Newswire|NEWSWIRE|CNW|Corp\. -|20\d\d)\s*[-/]?\s*)", "", m.group(1)).strip()
    return nm or None


def _other_party(s, issuer):
    """True when the meeting in s is plainly another company's: "meeting of shareholders of Rush", "meeting of ER
    shareholders", "Gold Basin's special meeting" - named, and not the issuer (rule CE)."""
    if not issuer:
        return False
    m = re.search(r"meeting of (?:the )?(?:share|security|unit)holders of ([A-Z][\w&'.-]*)", s) or \
        re.search(r"meeting of (?:the )?([A-Z][\w&'.-]*(?:\s+[A-Z][\w&'.-]*){0,3})(?:'s)?\s+(?:share|security|unit)holders", s) or \
        re.search(r"([A-Z][\w&'.-]*(?:\s+[A-Z][\w&'.-]*){0,3})'s\s+(?:annual|special|annual general|annual and special)"
                  r"(?: general)?(?: and special)? meeting", s)
    if not m:
        return False
    nm = m.group(1).strip()
    if nm.lower() in ("the", "its", "our", "company", "the company", "corporation", "the corporation") or \
            re.match(r"(?:The|Its|Our|Company|Corporation|Issuer|Shareholders?)\b", nm):
        return False
    a = re.sub(r"[^a-z0-9 ]", "", nm.lower()).split()
    b = re.sub(r"[^a-z0-9 ]", "", issuer.lower()).split()
    return bool(a) and bool(b) and a[0] != b[0] and a[0] not in b


def _conf_lower(s, after=0):
    """"at the John Tumazos Very Independent Research, LLC virtual conference" -> the capitalised name."""
    m = re.search(r"\bat (?:the )?([A-Z][\w&'.,-]*(?:\s+[A-Z&][\w&'.,-]*){1,8})\s+(?:virtual |online |investor |mining )*"
                  r"(?:conference|summit|forum|event|show)\b", s[after:])
    return re.match(r"(.*)", m.group(1).rstrip(" ,")) and m.group(1).rstrip(" ,") if m else None


def _list_month_items(block):
    """List items given with a month only ("John Tumazos Very Independent Research, Virtual Conference March 2026")."""
    out = []
    last = 0
    for x in find_dates(block):
        last = x["e"]
    tail = block[last:]
    for m in MONTH_ONLY_RE.finditer(tail):
        nm = re.sub(r"^[\s,.;:\u2022*-]+|[\s,.;:(\u2013\u2014-]+$", "", tail[:m.start()]).strip()
        nm = re.sub(r"^(?:and|&)\s+", "", nm)
        if 3 <= len(nm) <= 110 and re.search(r"[A-Z]", nm) and re.search(r"Conference|Summit|Forum|Show|Expo|Roundup|"
                                                                           r"Convention|Showcase|Event|Research", nm):
            out.append(nm + " (" + m.group(0) + ")")
        break
    return out


# ------------------------------------------------------------------ the reader
def _ev(kind, sent, dt, dl, **kw):
    e = {"kind": kind, "y": None, "m": None, "d": None, "exact": False, "end": None, "month_only": None, "rel": None,
         "time": None, "record": None, "detail": None, "venue": None, "role": None, "show": True}
    if dt:
        e.update(y=dt["y"], m=dt["m"], d=dt["d"], exact=True)
        if dt.get("d2"):
            e["end"] = (dt["y"], dt["m2"], dt["d2"])
    e.update(kw)
    iso = _iso(*_ymd(e, dl)) if e["m"] else None
    e["status"] = kw.get("status") or _status(sent, kind, iso, dl, bool(dt) or e["rel"] is not None)
    e["fixed"] = bool(kw.get("status"))
    e["flags"] = _flags(sent, kind)
    e["cue"] = sent[:160]
    return e


def _ymd(e, dl):
    y = e["y"]
    if y is None and dl is not None:
        y = dl.year
        if e["m"] and _iso(y, e["m"], e["d"] or 1) and date(y, e["m"], e["d"] or 1) < dl - timedelta(days=150):
            y += 1
    return y, e["m"], e["d"]


def _rel(sent, dl):
    m = None
    for x in REL_RE.finditer(sent):
        if re.search(r"(?:announc\w*|report\w*|releas\w*|provid\w*|declar\w*|confirm\w*)\s*$", sent[max(0, x.start() - 20):x.start()],
                     re.I) or re.match(r"\s*(?:that|its|the)\b", sent[x.end():], re.I):
            continue
        m = x
        break
    if not m:
        return None
    return {"tomorrow": 1, "yesterday": -1}.get(m.group(1).lower(), 0)


def _events(headline, body):
    hl = _norm(headline or "")
    header, t, dl = split_header(_norm(body or ""))
    ctx = hl + " " + header                     # context only: no events are read from the headline or the header
    hl_post = bool(POSTPONE.search(ctx))
    hl_vote = bool(VOTE_HL.search(hl))                  # CAL 1.0.2: "Voting Results", "Results of Annual General Meeting"
    issuer = _issuer(header + " " + t[:1500])
    list_ctx, list_role = None, None
    sents = _sentences(t)
    hl_len = -1
    evs = []
    for i, (off, s) in enumerate(sents):
        nxt = sents[i + 1][1] if i + 1 < len(sents) else ""
        nxt2 = sents[i + 2][1] if i + 2 < len(sents) else ""
        win = s + " " + nxt          # labels like "Date: May 14" fall into the next unit
        ds = find_dates(s)
        is_hl = off < hl_len
        # forward-looking statements and boilerplate: skip
        if re.search(r"forward[\s-]looking (?:statements|information)|cautionary|about (?:the company|us)\b", s, re.I) \
                and not ds:
            continue
        if re.search(r"forward[\s-]looking (?:statements|information)|neither (?:the )?TSX|no assurance|there can be no|"
                     r"risks? (?:and uncertainties|that)|could cause actual", s, re.I):
            continue
        rel = _rel(s, dl)
        if NAV.search(s):          # CAL 1.0.1: a web page's menus and sidebars, not the release
            continue
        prev3 = " ".join(x[1] for x in sents[max(0, i - 3):i])
        after_colon = bool(i and sents[i - 1][1].rstrip().endswith(":"))
        in_list = bool(LIST_INTRO.search(s) or ((BULLET.match(s) or after_colon) and LIST_INTRO.search(prev3)))
        if not in_list and BULLET.match(s) and list_ctx is not None and i - list_ctx <= 12:
            in_list = True                              # CAL 1.0.2: every bullet of the list, not only the first three
        if LIST_INTRO.search(s):
            list_ctx, list_role = i, ("presenting" if re.search(r"present(?:ing)? at the following", s, re.I)
                                      and not re.search(r"\b(?:or|and/or)\s+present", s, re.I) else "attending")
        elif list_ctx is not None and not BULLET.match(s):
            list_ctx = None
        rr_here = None

        # --- results release (future only) and conference call
        if (RESULTS_OBJ.search(s) or (re.match(r"\s*(?:[\w-]+\s+){0,4}results release\s*:", s, re.I) and
                                      RESULTS_OBJ.search(sents[i - 1][1] + " " + s if i else s))) and \
                RESULTS_FUT.search(s) and not is_hl and not re.search(
                r"pleased to (?:announce|report|provide)[^.]{0,30}(?:voting|meeting|drill|assay)|voting results|"
                r"results of (?:the|its) (?:annual|special|meeting|AGM|vote)", s, re.I):
            mf = RESULTS_FUT.search(s)
            dt = _pick_date(s, mf.start(), ds) or (None if CALL.search(s[:mf.start()]) else None)
            cm = CALL.search(s)
            if dt and cm and cm.start() < dt["s"] and cm.start() > mf.start():
                dt = None        # the date belongs to the call
            if dt or rel is not None or re.search(r"prior to the (?:call|market)|before the call", s, re.I):
                evs.append(_ev("results_release", s, dt, dl, detail=_period(s), rel=None if dt else rel,
                               status="scheduled" if dt or rel is not None else "proposed"))
                rr_here = (mf.start(), dt)
        not_call = bool((MEETING.search(s) and MEET_VIA_WEBCAST.search(s)) or
                        (WEBCAST_PRES.search(s) and not RESULTS_OBJ.search(s) and
                         not re.search(r"conference call|earnings call|teleconference|\b(?:will|to) host\b", s, re.I)))  # CAL 1.0.2
        if CALL.search(s) and not is_hl and not not_call and not (re.search(r"(?:call|webcast)\s+details\b", s, re.I) and
                                                   RESULTS_FUT.search(s) and not re.search(r"\b(?:host|hold)\b", s, re.I)) \
                and not re.search(r"replay|archived|archive|recording|recorded|available (?:until|for)|"
                                                          r"investor day", s, re.I):
            cm = CALL.search(s)
            dt = _pick_date(s, cm.start(), ds)
            if dt and dt["s"] - cm.end() > 200:
                dt = None
            # CAL 1.0.1: "Results Conference Call and Webcast Lundin Gold will publish its results on November 4": a
            # section heading run into the results-date sentence; the call itself is in the next sentence
            heading = bool(rr_here and cm.start() < rr_here[0] and not re.search(r"\b(?:host|hold)\b", s, re.I))
            if not dt:
                before = [x for x in ds if x["s"] < cm.start() and cm.start() - x["e"] < 150]
                if before and not (RESULTS_FUT.search(s) and RESULTS_OBJ.search(s)):
                    dt = before[-1]
            if not dt and re.match(r"\s*(?:Date|When)\s*:", nxt, re.I):
                dt = _pick_date(nxt)
            if not dt and re.search(r"\b(?:Date|Time)\s*:", nxt + nxt2):
                dt = _pick_date(nxt + " " + nxt2)
            tm = _times(s) or _times(nxt)
            nxt3 = sents[i + 3][1] if i + 3 < len(sents) else ""
            if not tm and re.match(r"\s*(?:Date|When|Time)\s*:", nxt + " " + nxt2, re.I):
                tm = _times(nxt2) or _times(nxt3)        # CAL 1.0.2: "Date: ... Time: 10:00 AM ET" detail block
            same = SAME_DAY.search(s)
            rr_last = next((e for e in reversed(evs) if e["kind"] == "results_release" and e["m"]), None)
            if same and rr_last and (not dt or FOREIGN_ZONE.search(s) or "Australia" in s):
                off = 1 if re.search(r"following|next", same.group(0), re.I) else 0
                d0 = date(rr_last["y"] or (dl.year if dl else 2000), rr_last["m"], rr_last["d"]) + timedelta(days=off)
                dt = {"s": same.start(), "e": same.end(), "y": d0.year if rr_last["y"] or dl else None, "m": d0.month,
                      "d": d0.day, "m2": None, "d2": None}
            na = None if same and rr_last else _na_when(s + " " + nxt + " " + nxt2)  # CAL 1.0.1: the North American date
            if na and (dt or tm):
                dt, tm = na[0], [na[1]]
            r = _rel(s, dl) if not dt else None
            if heading:
                pass
            elif (dt or r is not None) and (tm or re.search(r"\bwill (?:\w+ )?(?:host|hold)|\bto (?:host|hold)\b|\bheld\b", s, re.I)):
                purpose = _period(s) or _period(sents[max(0, i - 1)][1])
                if re.search(r"investor day|AGM|year[\s-]end webcast|presentation", s, re.I) and not re.search(
                        r"results|earnings", s, re.I):
                    pass
                evs.append(_ev("conference_call", s, dt, dl, time=tm[0] if tm else None, rel=r, detail=purpose))

        # --- meetings
        mm = MEETING.search(s)
        if mm and (MEET_THIRD.search(s) or in_list):    # CAL 1.0.1: an industry body's meeting the company attends
            mm = None
        if mm and _other_party(s, issuer):              # CAL 1.0.2: another company's meeting (rule CE)
            mm = None
        if mm and not re.search(r"management information circular (?:is|was) available|proxy (?:deadline|cut-?off)", s, re.I) \
                and not re.search(r"record date", s[:mm.start()], re.I):
            typ = mm.group(0).lower()
            det = "annual and special" if ("special" in typ and ("annual" in typ or "agsm" in typ)) else \
                "special" if "special" in typ else "annual" if re.search(r"annual|agm|asm", typ) else None
            if det is None:
                ctx = s[max(0, mm.start() - 40):mm.end()]
                det = "annual and special" if re.search(r"annual(?: general)? and special", ctx, re.I) else \
                    "special" if re.search(r"special", ctx, re.I) else "annual" if re.search(r"annual", ctx, re.I) else None
            # the meeting's date: the first date after the cue that is not a record date
            dt, held_dt = None, False
            for x in ds:
                if re.search(r"(?:held|to be held|will be held|scheduled for|take place|taking place|convened)\s*(?:on|at)?\s*(?:\w+,?\s+)?$",
                             s[max(0, x["s"] - 45):x["s"]], re.I):
                    dt, held_dt = x, True
                    break
            for x in ([] if dt else ds):
                pre = s[max(0, x["s"] - 45):x["s"]].lower()
                if re.search(r"deadline|no later than|received by|mailed|mailing|filed|sedar|before|prior to", pre):
                    continue
                if "record" in pre or "dated" in pre or "circular" in pre or "news release" in pre or "press release" in pre:
                    continue
                if x["s"] > mm.start() - 120:
                    dt = x
                    break
            past = re.search(r"\b(?:held|voting results|results of (?:the |its )?(?:annual|special|AGM)|were (?:elected|"
                             r"approved|re-elected)|approved at|shareholders approved|at the (?:annual|special|AGM|meeting))",
                             s, re.I)
            stale = dt and dt["y"] and dl and _iso(dt["y"], dt["m"], dt["d"]) and \
                date(dt["y"], dt["m"], dt["d"]) < dl - timedelta(days=120)
            if dt and dl and hl_vote and not held_dt and not re.search(r"\b(?:will be|to be) held\b|\bnext\b", s, re.I) and \
                    _iso(*_ymd(dict(y=dt["y"], m=dt["m"], d=dt["d"]), dl)) >= dl.isoformat():
                dt = None                               # CAL 1.0.2: a voting-results release reports a meeting held
            if dt and dl and POSTPONE.search(s) and _iso(*_ymd(dict(y=dt["y"], m=dt["m"], d=dt["d"]), dl)) <= dl.isoformat():
                dt = None                               # CAL 1.0.2: the original (past) date of a postponed meeting
            if not stale and (dt or past or re.search(r"\b(?:will be held|to be held|will hold|scheduled|postpone|adjourn|cancel)", s, re.I)):
                r = _rel(s, dl) if not dt else None
                if not dt and past and r is None and re.search(r"earlier today|held today", s, re.I):
                    r = 0
                st = None
                if not dt and r is None and past:
                    st = "completed"
                if not dt and r is None and hl_vote and not POSTPONE.search(s):
                    st = "completed"
                evs.append(_ev("meeting", s, dt, dl, detail=det, rel=r, status=st))

        # --- dividends
        prev = sents[i - 1][1] if i else ""
        if DIVIDEND.search(s) and (re.search(r"\b(?:declar|approv|confirm)", prev + " " + s, re.I) or re.search(
                r"\b(?:payable|(?:will|to) be paid)\s+on\b", s, re.I)) and not re.search(r"\bha(?:s|ve) paid\b|"
                                                                                 r"anticipated to be paid", s, re.I) and not re.search(
                r"dividend (?:policy|reinvestment|yield)|no dividends|has not (?:paid|declared)|flow[\s-]through|"
                r"stock dividend", s, re.I):
            w2 = s + " " + nxt + " " + nxt2
            pay = re.search(r"(?:payable|paid|payment date|to be paid|will be paid|paid out)\s*(?:on|:|date of|is)?\s*", w2, re.I)
            rec = re.search(r"(?:of record|record date)[^.]{0,60}?", w2, re.I)
            pdt = _pick_date(w2, pay.end()) if pay else None
            rdt = _pick_date(w2, rec.start()) if rec else None
            w4 = w2 + " " + " ".join(x[1] for x in sents[i + 3:i + 6])       # CAL 1.0.2: a dividend timetable
            pl = re.search(r"\bpayment date\s*(?:is|:|of|will be)?\s*", w4, re.I)
            rl = re.search(r"\brecord date\s*(?:is|:|of|will be)?\s*", w4, re.I)
            if pl and _pick_date(w4, pl.end()) and _pick_date(w4, pl.end())["s"] - pl.end() < 30:
                w2, pay, pdt = w4, pl, _pick_date(w4, pl.end())
                rdt = _pick_date(w4, rl.end()) if rl and _pick_date(w4, rl.end()) and _pick_date(w4, rl.end())["s"] - rl.end() < 30 else rdt
                rec = rl or rec
            if pdt and rec and rec.start() < pdt["s"] and re.search(r"record", w2[pay.end():pdt["s"]], re.I):
                # "payable to shareholders of record at the close of business X, and will be paid on Y"
                rdt = pdt
                paid = re.search(r"(?:will be |to be )?paid (?:on|out on)\s*", w2[pdt["e"]:], re.I)
                pdt = _pick_date(w2, pdt["e"] + paid.end()) if paid else None
            elif pdt and rdt and pdt["s"] == rdt["s"]:
                # "payable on X to holders of record on Y": the first date after "payable" is the payment
                later = [x for x in find_dates(w2) if x["s"] > pdt["s"]]
                rdt = later[0] if later else None
            amt = None
            for mo in MONEY_RE.finditer(w2):
                ctx = w2[mo.end():mo.end() + 40].lower()
                if "per" in ctx or "a share" in ctx or "cents" in (mo.group("cents") or "") or "per share" in w2[mo.start() - 30:mo.start()].lower():
                    cur = (mo.group("cur") or "").upper().replace(".", "").replace("CDN", "C").replace("CAD", "C") \
                        .replace("CA", "C").replace("AUD", "A").replace("AU", "A")
                    a = mo.group("amt") or mo.group("amt2")
                    if mo.group("cents") or mo.group("cur2"):
                        a = "%g" % (float(a) / 100)
                    amt = "%s$%s" % (cur, a) if cur else "$%s" % a
                    break
            if pdt and (amt or rdt):
                rec_s = None
                if rdt:
                    rec_s = (rdt["y"], rdt["m"], rdt["d"])
                kind_w = re.search(r"\b(special|variable|interim|final|monthly|quarterly|semi-annual)\b", s, re.I)
                evs.append(_ev("dividend", s, pdt, dl, record=rec_s,
                               detail=(amt or "") + (" (%s)" % kind_w.group(1).lower() if kind_w and kind_w.group(1).lower()
                                                     in ("special", "variable", "interim", "final", "monthly") else "")))

        # --- NCIB
        if NCIB.search(s) and re.search(r"\b(?:commenc|begin|start|effective|terminate|expire|end|accepted|renew|amend)",
                                        win, re.I):
            st = re.search(r"(?:commenc|begin|start|effective)\w*\s*(?:on|as of|at)?\s*", win, re.I)
            en = re.search(r"(?:terminat|expir|end)\w*\s*(?:on|at|the earlier of)?", win, re.I)
            sdt = _pick_date(win, st.end()) if st else None
            edt = _pick_date(win, en.end()) if en else None
            mx = re.search(r"(?:up to|maximum of|purchase)\s+([\d,]{5,})\s+(?:common )?shares", win, re.I)
            if sdt and not any(e["kind"] == "ncib" for e in evs):
                evs.append(_ev("ncib", s, sdt, dl, end=(edt["y"], edt["m"], edt["d"]) if edt and edt is not sdt else None,
                               detail=("max %s shares" % mx.group(1)) if mx else None, venue=_venue(win)))

        # --- consolidation / name change / symbol change: read across the release (see _corp_actions)
        # --- arrangement / spin-out / listing
        if ARRANGE.search(s) and not SPIN.search(s) and not re.search(r"\bloan\b|debenture|matur(?:es|ity)|\bnote\b",
                                                                     s, re.I) and re.search(r"\b(?:close|closing|complet|effective|consummat|implement)", s, re.I) and \
                not re.search(r"private placement|flow[\s-]through|financing|offering", s, re.I):
            dt = None
            for x in ds:
                pre = s[max(0, x["s"] - 70):x["s"]].lower()
                if re.search(r"news release|press release|dated|announced on|agreement dated|entered into", pre):
                    continue
                dt = x
                break
            am = ARRANGE.search(s)
            vert = bool(re.search(r"\bvertical\b|short[\s-]form", s, re.I) and re.search(r"wholly[\s-]owned subsidiar", s, re.I))
            evs.append(_ev("arrangement", s, dt, dl, detail=s[am.start():am.start() + 90], show=not vert))
        if SPIN.search(s) and re.search(r"\b(?:effective|distribut|record|complet|closing|close)", s, re.I):
            dt = _pick_date(s, SPIN.search(s).start(), ds) or (ds[0] if ds else None)
            nm = re.search(r"([A-Z][\w&.'-]+(?:\s+[A-Z][\w&.'-]+){0,4}\s+(?:Corp(?:oration)?|Inc|Ltd|Limited|Royalties|"
                           r"Resources|Metals|Gold)\.?)", s[SPIN.search(s).start():])
            evs.append(_ev("spinout", s, dt, dl, detail=nm.group(1) if nm else None))
        if LISTING.search(s) and not is_hl and not re.search(r"consolidat|new name|name change|symbol", s, re.I) and re.search(r"\b(?:TSX|TSXV|CSE|NYSE|Nasdaq|Exchange|OTC|ASX|AIM)\b", s) and \
                not SYMBOL.search(s[:LISTING.search(s).start()][-60:]):
            lm = LISTING.search(s)
            dt = _pick_date(s, lm.start(), ds)
            ven = _venue(s[lm.start():lm.start() + 120]) or _venue(s)
            what = "delisting" if re.search(r"delist", lm.group(0), re.I) else "graduation" if re.search(
                r"graduat", lm.group(0), re.I) else "listing"
            if re.search(r"graduat\w*\s+(?:\w+\s+){0,3}?to\s+(?:the\s+)?(?:TSX\b(?![\s.-]?V)|Toronto Stock Exchange)", s, re.I):
                what, ven = "graduation", "TSX"     # CAL 1.0.1: the exchange it moves to, not the one it leaves
            if dt and (ven not in ("OTC", "FSE") or what != "listing"):
                evs.append(_ev("listing", s, dt, dl, detail=what, venue=ven, show=ven not in ("OTC", "FSE")))

        # --- presentations
        pm = PRESENT.search(s)
        if in_list:
            # CAL 1.0.1: each item of "will be attending the following events: <name> <dates> <name> <dates> ..."
            role = list_role if list_role else "attending"
            lm2 = LIST_INTRO.search(s)
            blk = s[lm2.end():] if lm2 else s
            if BULLET.match(s) and nxt and not BULLET.match(nxt) and len(nxt) < 60 and find_dates(nxt):
                blk = blk + " " + nxt                    # "121 Mining - Online: October 14 - 15" split at the label
            for nm, x in _list_items(blk):
                evs.append(_ev("presentation", s, x, dl, detail=nm, role=role, list_item=True))
            for nm in _list_month_items(blk):            # CAL 1.0.2: "Virtual Conference March 2026" -> no day (CN1)
                evs.append(_ev("presentation", s, None, dl, detail=nm, role=role, list_item=True))
            pm = None
        if pm and not CALL.search(s[:pm.start()]):
            cn = _conf_name(s, pm.start()) or _conf_name(nxt) or _conf_lower(s, pm.start())
            cn = re.match(r"(.*)", cn) if cn else None
            dt = _pick_date(s, pm.start(), ds) or _pick_date(s, 0, ds) or \
                (_pick_date(nxt) if re.match(r"\s*(?:Date|When)\b", nxt, re.I) or PRESENT.search(nxt) or _times(nxt) else None)
            if cn and dt and not re.search(r"annual (?:general )?meeting|special meeting|conference call", cn.group(1), re.I):
                tm = _times(s) or _times(nxt)
                role = "attending" if re.search(r"booth|attend|visit|exhibit|sponsor|join (?:us|management)", s, re.I) and \
                    not re.search(r"present(?:ing|s)? at|to present|will present|presentation (?:at|on)|keynote|speak", s, re.I) \
                    else "presenting"
                evs.append(_ev("presentation", s, dt, dl, detail=cn.group(1).strip(), time=tm[0] if tm else None,
                               role=role))
    # CAL 1.0.1: a list item is the same event as a presentation the release gives on a day within the item's dates
    def _span(e):
        y, m, d = _ymd(e, dl)
        a = _iso(y, m, d) if m else None
        b = _iso(e["end"][0] or y, e["end"][1], e["end"][2]) if e.get("end") else a
        return a, b
    pres = [e for e in evs if e["kind"] == "presentation" and not e.get("list_item")]
    keep = []
    for e in evs:
        if e.get("list_item"):
            a, b = _span(e)
            if a and any(a <= (_span(p)[0] or "") <= (b or a) for p in pres):
                continue
        keep.append(e)
    evs = keep
    evs.extend(_corp_actions(sents, dl))
    if hl_post:
        for e in evs:
            if e["kind"] in ("meeting", "results_release", "conference_call", "presentation") and e["status"] in (
                    "scheduled", "proposed"):
                e["status"], e["fixed"] = "postponed", True
    return _dedupe(evs, dl)


ACT_DATE_CUE = re.compile(r"(?:effective|trading|on or about|record date|post-consolidation basis|expected|commence|begin|"
                          r"open(?:ing)?|as of)\b[^.]{0,40}$", re.I)
ACT_DATE_SKIP = re.compile(r"\b(?:offering|private placement|financing|loan|warrants?|options|resolution|board of directors "
                           r"(?:passed|approved)|closing of the (?:offering|placement))\b", re.I)
NOT_ACT_SENT = re.compile(r"consolidated (?:financial|statements|results|net|revenue|cash)|consolidat\w+ (?:of )?(?:the |its |"
                          r"a )?(?:land|claims?|property|properties|district|ownership|position|mineral|tenure|interest|"
                          r"project|camp|holdings|package)|forward[\s-]looking|may not be completed|no name change|no assurance|"
                          r"not (?:be )?(?:changing|change) its name", re.I)


def _act_date(sents_idx, sents):
    """The best effective date among the sentences: the first date preceded by an effective/trading cue."""
    for i in sents_idx:
        s = sents[i][1]
        if ACT_DATE_SKIP.search(s):
            continue
        for x in find_dates(s):
            pre = s[max(0, x["s"] - 80):x["s"]]
            if NOT_EVENT_DATE.search(s[max(0, x["s"] - 40):x["s"]]) or re.search(
                    r"news release|press release|meeting|circular|dated", pre[-50:], re.I):
                continue
            if ACT_DATE_CUE.search(pre):
                return i, x
    return None, None


def _corp_actions(sents, dl):
    """Consolidation, name change and symbol change, each read once per release: the terms from the first sentence
    that gives them, the date from any sentence about the same action that gives an effective / trading date."""
    out = []
    con = [i for i, (_, s) in enumerate(sents) if CONSOL.search(s) and not NOT_ACT_SENT.search(s)]
    ratio = next((r for r in (_ratio(sents[i][1]) for i in con) if r), None)
    if ratio:
        di, dt = _act_date(con, sents)
        s0 = sents[di][1] if di is not None else sents[con[0]][1]
        if di is None:
            first_r = next(i for i in con if _ratio(sents[i][1]))
            s0 = sents[first_r][1]
        out.append(_ev("consolidation", s0 + " " + " ".join(sents[i][1] for i in con[:3]), dt, dl, detail=ratio))
    nmi = [i for i, (_, s) in enumerate(sents) if NAMECHG.search(s) and not NOT_ACT_SENT.search(s) and not re.search(
        r"\b(?:project|property|deposit|subsidiary|mine)\s+(?:name|renamed)", s, re.I)]
    nm = None
    for i in nmi:
        nm = _name_after(sents[i][1], r"(?:change (?:of )?its (?:corporate )?name|name change|changed its name|new name|"
                                      r"renamed|to be renamed|rename (?:itself|the company))(?:\s+(?:from\s+[^.]{2,60}?\s+)?to)?")
        if nm:
            break
    if nm:
        di, dt = _act_date(nmi, sents)
        s0 = sents[di][1] if di is not None else sents[nmi[0]][1]
        out.append(_ev("name_change", s0 + " " + " ".join(sents[i][1] for i in nmi[:3]), dt, dl, detail=nm))
    syi = [i for i, (_, s) in enumerate(sents) if SYMBOL.search(s) and SYMCHG.search(s) and not re.search(
        r"(?:existing|current|same) (?:trading |ticker |stock )?symbol|continue to trade under", s, re.I)]
    for i in syi:
        s = sents[i][1]
        sym = _symbol_after(s)
        if not sym:
            continue
        vm = re.search(r"(?:on|in) (?:the )?(" + "|".join(p for _, p in VENUES) + r")", s)
        ven = _venue(vm.group(0)) if vm else _venue(s)
        di, dt = _act_date([i] + [j for j in syi + nmi if j != i], sents)
        out.append(_ev("symbol_change", s, dt, dl, detail=sym, venue=ven, show=ven not in ("OTC", "FSE")))
    return out


def _key(e, dl):
    y, m, d = _ymd(e, dl)
    return (e["kind"], _iso(y, m, d) if m else None)


def _dedupe(evs, dl):
    out = []
    for e in evs:
        k = _key(e, dl)
        same = [o for o in out if _key(o, dl) == k]
        if k[1] is None:
            same = [o for o in out if o["kind"] == e["kind"] and (o["detail"] or "") == (e["detail"] or "")] or \
                   ([o for o in out if o["kind"] == e["kind"]] if e["kind"] not in ("ncib",) else [])
        if not same:
            # a dated event of the same kind and detail already known: the undated mention is the same event
            if k[1] is None and any(o["kind"] == e["kind"] for o in out):
                continue
            # an undated earlier mention gives way to the dated one
            und = [o for o in out if o["kind"] == e["kind"] and _key(o, dl)[1] is None and
                   ((o["detail"] or "") == (e["detail"] or "") or e["kind"] in ("consolidation", "name_change",
                                                                                 "symbol_change", "meeting"))]
            for o in und:
                out.remove(o)
            out.append(e)
            continue
        o = same[0]
        for f in ("time", "record", "detail", "venue", "end", "role"):
            if not o.get(f) and e.get(f):
                o[f] = e[f]
    return out


# ------------------------------------------------------------------ resolve against the release date
def resolve(e, published_at=None, dateline=None):
    """The answer-key row for one extracted event."""
    dl = dateline
    if dl is None and published_at:
        dl = date.fromisoformat(str(published_at)[:10])
    y, m, d = _ymd(e, dl)
    iso = _iso(y, m, d) if m else None
    exact = bool(e["exact"]) and iso is not None
    if iso is None and e.get("rel") is not None and dl:
        iso, exact = (dl + timedelta(days=e["rel"])).isoformat(), True
    status = e["status"]
    if not e.get("fixed") and dl is not None:
        status = status_from(e.get("flags") or "", e["kind"], iso, dl, iso is not None)
    if iso is None and status == "completed" and dl:
        iso, exact = dl.isoformat(), False
    row = {"kind": e["kind"], "status": status, "date": iso, "exact": exact}
    if e.get("end"):
        ey, em, ed = e["end"]
        if ey is None and y:
            ey = y
        row["end_date"] = _iso(ey, em, ed)
    if e.get("record"):
        ry, rm, rd = e["record"]
        if ry is None and dl:
            ry = _ymd({"y": None, "m": rm, "d": rd}, dl)[0]
        row["record_date"] = _iso(ry, rm, rd)
    for f in ("time", "detail", "venue", "role"):
        if e.get(f):
            row[f] = e[f]
    if not e.get("show", True):
        row["show"] = False
    row["_cue"] = e.get("cue")
    return row


def analyse(headline, body):
    body = (body or "")[:TEXT_CAP]
    dl = split_header(_norm(body))[2]
    return {"dl": dl, "events": _events(headline, body)}


# ------------------------------------------------------------------ facts store
TXT = ("kind", "status", "flags", "time", "detail", "venue", "role")


def _part(t):
    """(y, m, d) with y possibly None -> 'YYYY-MM-DD' or '--MM-DD'."""
    if not t or t[1] is None:
        return None
    y, m, d = t
    return "%04d-%02d-%02d" % (y, m, d or 1) if y else "--%02d-%02d" % (m, d or 1)


def _unpart(s):
    if not s:
        return None
    if s.startswith("--"):
        return (None, int(s[2:4]), int(s[5:7]))
    return (int(s[:4]), int(s[5:7]), int(s[8:10]))


def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    dl = a["dl"].isoformat() if a["dl"] else None
    if not a["events"]:
        fs = [F.Fact("is_event", value_num=0.0)]
        if dl:
            fs.append(F.Fact("dateline", value_text=dl))
        return [F.Record(KIND, facts=fs, confidence=0.0)]
    out = []
    for e in a["events"]:
        fs = [F.Fact("is_event", value_num=1.0)]
        if dl:
            fs.append(F.Fact("dateline", value_text=dl))
        for k in TXT:
            if e.get(k) not in (None, ""):
                fs.append(F.Fact(k, value_text=str(e[k])[:300]))
        for k, v in (("date", _part((e["y"], e["m"], e["d"]))), ("end", _part(e.get("end"))),
                     ("record", _part(e.get("record")))):
            if v:
                fs.append(F.Fact(k, value_text=v))
        fs.append(F.Fact("exact", value_num=1.0 if e.get("exact") else 0.0))
        fs.append(F.Fact("fixed", value_num=1.0 if e.get("fixed") else 0.0))
        fs.append(F.Fact("show", value_num=0.0 if e.get("show") is False else 1.0))
        if e.get("rel") is not None:
            fs.append(F.Fact("rel", value_num=float(e["rel"])))
        out.append(F.Record(KIND, facts=fs, confidence=1.0))
    return out


def parse_records(rows_by_ordinal):
    """{ordinal: [(field, seq, value_num, value_text)]} -> {"dl": iso|None, "events": [event]} (the analyse() shape)."""
    evs, dl = [], None
    for ordinal in sorted(rows_by_ordinal):
        r, yes = {}, False
        for field_, _seq, num, text in rows_by_ordinal[ordinal]:
            if field_ == "is_event":
                yes = num == 1.0
            elif field_ == "dateline":
                dl = text
            else:
                r[field_] = text if text is not None else num
        if not yes or not r.get("kind"):
            continue
        y, m, d = _unpart(r.get("date")) or (None, None, None)
        evs.append({"kind": r["kind"], "status": r.get("status"), "flags": r.get("flags") or "",
                    "fixed": bool(r.get("fixed")), "y": y, "m": m, "d": d, "exact": bool(r.get("exact")),
                    "end": _unpart(r.get("end")), "record": _unpart(r.get("record")),
                    "rel": int(r["rel"]) if r.get("rel") is not None else None, "time": r.get("time"),
                    "detail": r.get("detail"), "venue": r.get("venue"), "role": r.get("role"),
                    "show": r.get("show") != 0.0, "cue": None})
    return {"dl": dl, "events": evs}


def release_date(dateline, published_at):
    """The date a release's relative dates count from: the dateline the text gives, unless it is more than 10 days
    from when MNT saw the release (a letterhead or report date), else published_at."""
    pub = None
    if published_at:
        try:
            pub = date.fromisoformat(str(published_at)[:10])
        except ValueError:
            pub = None
    dl = None
    if dateline:
        dl = dateline if isinstance(dateline, date) else date.fromisoformat(str(dateline)[:10])
    if dl is None or (pub is not None and abs((pub - dl).days) > 10):
        return pub
    return dl


def rows_from(parsed, published_at):
    """parse_records() output + the release's published_at -> finished rows."""
    dl = release_date(parsed.get("dl"), published_at)
    return [resolve(e, published_at, dl) for e in parsed.get("events") or []]


def read(headline, body, published_at=None):
    recs = extract(headline, body)
    p = parse_records({i: [(f.field, f.seq, f.value_num, f.value_text) for f in r.facts] for i, r in enumerate(recs)})
    return rows_from(p, published_at)


def to_prediction(records):
    if not records:
        return None
    p = parse_records({i: [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts] for i, rec in enumerate(records)})
    return p if p["events"] else None


SPEC = F.ExtractorSpec(NAME, VERSION, KIND, TAG, extract, FP.code_sha(__file__)) if F else None


# ------------------------------------------------------------------ self-test
_LEAD = "Vancouver, British Columbia, %s - Alpha Gold Corp. (TSXV: ALP) (\"Alpha\" or the \"Company\") "
_FILL = " The Company continues to advance its projects in British Columbia." * 3


def self_test(verbose=False):
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))

    def rows(hl, body, pub):
        return [{k: v for k, v in r.items() if k != "_cue"} for r in read(hl, body, pub)]

    r = rows("Alpha Gold to Release Third Quarter 2026 Results", _LEAD % "October 1, 2026" + "will release its third "
             "quarter 2026 financial results after market close on Thursday, November 5, 2026. Management will host a "
             "conference call on Friday, November 6, 2026 at 10:00 a.m. ET to discuss the results." + _FILL,
             "2026-10-01T12:00:00Z")
    eq("results date and call", [(x["kind"], x["status"], x["date"]) for x in r],
       [("results_release", "scheduled", "2026-11-05"), ("conference_call", "scheduled", "2026-11-06")])
    eq("call time", r[1].get("time"), "10:00 a.m. ET")
    r = rows("Alpha Gold Declares Quarterly Dividend", _LEAD % "April 2, 2026" + "announces that its Board of Directors "
             "has declared a quarterly dividend of US$0.04 per common share, payable on May 15, 2026 to shareholders of "
             "record at the close of business on April 30, 2026." + _FILL, "2026-04-02T21:00:00Z")
    eq("dividend: one row, paid + record", [(x["kind"], x["status"], x["date"], x.get("record_date"), x.get("detail"))
                                           for x in r],
       [("dividend", "scheduled", "2026-05-15", "2026-04-30", "US$0.04")])
    r = rows("Alpha Gold Announces Voting Results", _LEAD % "June 12, 2026" + "is pleased to announce the voting results "
             "of its annual general and special meeting of shareholders held on June 11, 2026." + _FILL,
             "2026-06-12T20:00:00Z")
    eq("meeting held", [(x["kind"], x["status"], x["date"], x.get("detail")) for x in r],
       [("meeting", "completed", "2026-06-11", "annual and special")])
    r = rows("Alpha Gold Announces Share Consolidation", _LEAD % "March 3, 2026" + "announces that the TSX Venture "
             "Exchange has accepted the consolidation of its common shares on the basis of one (1) post-consolidation "
             "share for every ten (10) pre-consolidation shares. The post-consolidation shares are expected to begin "
             "trading on the TSXV at market open on March 9, 2026." + _FILL, "2026-03-03T13:00:00Z")
    eq("consolidation", [(x["kind"], x["status"], x["date"], x.get("detail")) for x in r],
       [("consolidation", "scheduled", "2026-03-09", "10:1")])
    r = rows("Alpha Gold Announces Ticker Change on OTC Markets", _LEAD % "May 4, 2026" + "announces that its common "
             "shares will begin trading on the OTC Markets under the new ticker symbol \"ALPGF\" effective May 6, "
             "2026." + _FILL, "2026-05-04T13:00:00Z")
    eq("OTC symbol change stored, not shown", [(x["kind"], x.get("venue"), x.get("show")) for x in r],
       [("symbol_change", "OTC", False)])
    r = rows("Alpha Gold to Present at the Precious Metals Summit", _LEAD % "September 1, 2026" + "is pleased to "
             "announce that it will be presenting at the Precious Metals Summit Beaver Creek on September 9, 2026 at "
             "2:30 p.m. MT." + _FILL, "2026-09-01T13:00:00Z")
    eq("presentation", [(x["kind"], x.get("role"), x["date"]) for x in r], [("presentation", "presenting", "2026-09-09")])
    r = rows("Alpha Gold Reports Drill Results", _LEAD % "July 7, 2026" + "reports assays of 5.2 g/t gold over 12.0 "
             "metres from hole AG-26-014." + _FILL, "2026-07-07T13:00:00Z")
    eq("a drill release has no events", r, [])
    # the facts layer round-trips; a date with no year takes the release's year
    r = rows("Alpha Gold Announces Date of Annual Meeting", "Alpha Gold Corp. (TSXV: ALP) announces that its annual "
             "general meeting of shareholders will be held on June 18 in Vancouver." + _FILL, "2026-05-20T13:00:00Z")
    eq("no dateline: year from published_at", [(x["kind"], x["status"], x["date"]) for x in r],
       [("meeting", "scheduled", "2026-06-18")])
    eq("status cue letters", (_flags("The meeting was held on June 3.", "meeting"),
                              _flags("subject to shareholder approval", "consolidation")), ("MA", "R"))
    # CAL 1.0.1: the 10-14 spot-check cases
    r = rows("Alpha Gold to Announce Q3 Results", _LEAD % "October 6, 2026" + "will release its Q3 results on October "
             "28, 2026. Skip to main content Investors Events Calendar Upcoming Events Past Events Nov 10 Annual Meeting "
             "Stock Info Analyst Coverage RSS Feeds." + _FILL, "2026-10-06T13:00:00Z")
    eq("website menu is not an event", [(x["kind"], x["date"]) for x in r], [("results_release", "2026-10-28")])
    r = rows("Alpha Gold Upgrades to OTCQX", _LEAD % "October 9, 2026" + "Company representatives will be attending "
             "the following events: \N{BULLET} AEMA Annual Meeting - Sparks, NV, USA, December 6-11, 2026. "
             "\N{BULLET} VRIC 2027 - Vancouver, BC, Canada, January 24-25, 2027." + _FILL, "2026-10-09T13:00:00Z")
    eq("industry meeting in an events list", [(x["kind"], x.get("role"), x["date"]) for x in r],
       [("presentation", "attending", "2026-12-06"), ("presentation", "attending", "2027-01-24")])
    r = rows("Alpha Gold Quarterly Report", _LEAD % "October 13, 2026" + "The Company will hold a conference call on "
             "Wednesday, 14 October 2026, at 11.00am AEDT (Tuesday, 13 October 2026, at 8.00pm EDT)." + _FILL,
             "2026-10-13T08:00:00Z")
    eq("North American date and dotted time", [(x["kind"], x["date"], x.get("time")) for x in r],
       [("conference_call", "2026-10-13", "8.00pm EDT")])
    r = rows("Alpha Gold Announces Graduation to the TSX", _LEAD % "October 13, 2026" + "In connection with the "
             "graduation to the TSX, the Common Shares will be voluntarily delisted from the TSX Venture Exchange "
             "effective as of October 15, 2026." + _FILL, "2026-10-13T13:00:00Z")
    eq("graduation venue", [(x["kind"], x.get("venue"), x["date"]) for x in r], [("listing", "TSX", "2026-10-15")])
    print("corp_calendar: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test("-v" in sys.argv) else 0)
