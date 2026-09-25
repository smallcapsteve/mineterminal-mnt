# GLUETRIM_V1 (2026-09-25): cut the release's opening line off the end of a headline.
#
# Exchange PDFs often put the headline and the first line of the release on the
# same text run, so the stored headline reads "Title Vancouver, B.C. - Company
# Corp. (TSX-V: X) is pleased ...". trim_glued(h) returns the title alone, or h
# unchanged when no cut is safe. Pure function, no I/O; is_hollow is injected so
# the live extractor's own rule decides what is too short to be a headline.
import re

_SP = r"[ \t\u00a0]"
_DASH = "\\-\u2010\u2011\u2012\u2013\u2014\u2015"
_SEP = "[" + _DASH + r":/|,.]"
_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
          r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|J\s?u\s?ly|J\s?une|M\s?ay)")
_DATE = (r"(?:\(?\s*" + _MONTH + r"\.?\s*\d\s?\d?(?:\s?(?:st|nd|rd|th))?\s*,?\s*(?:2\s?0\s?\d\s?\d)?"
         r"|\(?\s*\d{1,2}\s?(?:st|nd|rd|th)?\s+" + _MONTH + r"\.?,?\s*(?:2\s?0\s?\d\s?\d)?"
         r"|" + _MONTH + r"\s?\d{1,2},?\s?\d{4})")
_REGION = (r"(?:British\s+Columbia|B\s?\.?\s?C\s?\.?(?![a-z])|BC\b|Ontario|ON\b|Ont\.|Alberta|AB\b|Saskatchewan|SK\b|"
           r"Manitoba|MB\b|Qu\s?[eé\u00c9]\s?bec|QC\b|Que\.|Nova\s+Scotia|NS\b|New\s+Brunswick|NB\b|"
           r"Newfoundland(?:\s+and\s+Labrador)?|NL\b|Yukon(?:\s+Territory)?|YT\b|Nunavut|Northwest\s+Territories|NWT\b|"
           r"Canada|Western\s+Australia|Australia|W\.?A\.?(?![a-z])|Queensland|New\s+South\s+Wales|Victoria|"
           r"Nevada|NV\b|Arizona|AZ\b|Colorado|CO\b|Idaho|ID\b|Utah|UT\b|Alaska|AK\b|Montana|Washington|"
           r"Wyoming|New\s+Mexico|California|Texas|New\s+York|NY\b|Florida|Minnesota|"
           r"U\.?S\.?A\.?|United\s+States|United\s+Kingdom|U\.?K\.?|England|Ireland|Scotland|Mexico|Peru|Chile|"
           r"Brazil|Argentina|Colombia|Ecuador|South\s+Africa|China|Hong\s+Kong|Singapore|Germany|Switzerland|"
           r"Nev\.|Ariz\.|Colo\.|Democratic\s+Republic\s+of\s+(?:the\s+)?Congo|DRC|Peru|Portugal|Spain|"
           r"France|Sweden|Finland|Norway|Turkey|Mongolia|Ghana|Kazakhstan|Bermuda|Cayman\s+Islands|Barbados|Guyana|"
           r"Suriname|Panama|Nicaragua|Honduras|Guatemala|Bolivia|Paraguay|Uruguay|Mali|Burkina\s+Faso|Tanzania|Zambia|"
           r"Namibia|Botswana|Kenya|Serbia|Greece|Bulgaria|Philippines|Indonesia|Papua\s+New\s+Guinea|New\s+Zealand|"
           r"Japan|India|Israel|Saudi\s+Arabia|Armenia)")
_KNOWN = (r"(?:Vancouver|North\s+Vancouver|West\s+Vancouver|Toronto|Montr[eé\u00c9]\s?al|MONTR[EÉ]AL|Calgary|Edmonton|"
          r"Kelowna|Halifax|Winnipeg|Saskatoon|Regina|Ottawa|Sudbury|Timmins|Thunder\s+Bay|"
          r"Rouyn-Noranda|Val-d['\u2019]Or|Quebec\s+City|Qu[eé]bec\s+City|St\.\s*John['\u2019]s|Perth|Sydney|"
          r"Melbourne|Brisbane|London|Denver|Reno|Tucson|Phoenix|Spokane|Johannesburg|Lima|Santiago|"
          r"Mexico\s+City|Hong\s+Kong|Beijing|Cranbrook|Kamloops|Smithers|Whitehorse|Yellowknife|"
          r"Mississauga|Oakville|Burlington|Longueuil|Chibougamau|Rimouski|Sherbrooke|Gatineau|Saguenay|Boise)")
_CITY_PRE = (r"(?:(?:St\.?|Ste\.?|Saint|Thunder|Port|Fort|Mount|Mt\.|New|North|West|East|South|Red|Grand|Salt\s+Lake|"
             r"Lac|Baie|Sault|Coeur|Mexico|Buenos|Rio|Belo|San|Santa|Hong|Kuala|Cape|Prince|Rankin|Flin|Swift|"
             r"Rocky|Sioux|Happy|Val|Quebec|Qu\u00e9bec)" + _SP + r"+)")
_CITY = r"(?:" + _CITY_PRE + r"{0,2}[A-Z][\w.'\u2019\-]*(?![\w'\u2019\-]))"
_RG = r"(?<![\w])(?i:" + _REGION + r")(?![\w])"
_KN = r"(?<![\w])(?i:" + _KNOWN + r")(?![\w])"
_NOT_CITY = re.compile(r"^(?:Projects?|Property|Properties|Mine|Mines|Deposit|Zone|District|Camp|Claims?|Area|Trend|"
                       r"Belt|Prospect|Complex|Operations?|Region|Province|Territory|Targets?|Discovery|Showing|"
                       r"Block|Concessions?|Licen[cs]es?|Gold|Silver|Copper|Lithium|Uranium|Update|Results?|"
                       r"Financing|Placement|Program|Programs|Drilling|Assays?|Company|Corporation)$", re.I)
_PLACE = re.compile(
    r"(?:(?<=\s)|^)(?P<p>"
    r"\(" + _SP + r"*" + _KN + r"(?:" + _SP + r"*/" + _SP + r"*[A-Z][\w\-]+)?(?:" + _SP + r"*," + _SP + r"*" + _RG + r")?" + _SP + r"*\)"         # (MELBOURNE), (Vancouver/Johannesburg)
    r"|" + _KN + r"(?:" + _SP + r"*(?:/|and|&)" + _SP + r"*" + _KN + r")?"
    r"(?P<kreg>" + _SP + r"*,?" + _SP + r"*\(?" + _RG + r"\)?(?:" + _SP + r"*,?" + _SP + r"*" + _RG + r")?)?"
    r"(?:" + _SP + r"*\((?i:qu\s?[eé\u00c9]\s?bec)\))?"
    r"(?:" + _SP + r"+(?:and|&)" + _SP + r"+" + _KN + r"(?:" + _SP + r"*,?" + _SP + r"*" + _RG + r")?)?"
    r"|(?P<city>" + _CITY + r")" + _SP + r"*," + _SP + r"*" + _RG +
    r"(?:" + _SP + r"*,?" + _SP + r"*" + _RG + r")?"
    r"(?:" + _SP + r"+and" + _SP + r"+[A-Z][\w]+,?" + _SP + r"*" + _RG + r")?"
    r")", re.U)
_KNOWN_RX = re.compile(r"^\(?" + _SP + r"*(?:" + _KNOWN + r")(?![\w])", re.I)
_DATE_SEP = re.compile(r"(?<=\s)(?P<p>" + _DATE + r")" + _SP + r"*[" + _DASH + r":]", re.I)
_SUFFIX = (r"(?:Corp(?:oration|\s?oration)?|Inc|Ltd|L\s?td|Limited|Lt[ée]e|Plc|PLC|LLC|S\.A\.|N\.L\.|Mines|Mining|"
           r"Minerals|Resources|Metals|Gold|Silver|Copper|Energy|Exploration|Industries|Holdings|Capital|"
           r"Royalties|Materials|Group|Uranium|Lithium|Ventures)")
_FORMAL = re.compile(r"\b(?:Corp(?:oration)?|Inc|Ltd|L\s?td|Limited|Lt[ée]e|Plc|LLC|S\.A\.)\b\.?", re.I)
_EXCH = r"(?:TSX(?:[\s.\-]?V(?:enture)?)?|TSXV|CSE|CNSX|NEX|NYSE|ASX|OTC\w*|NASDAQ|Nasdaq|AIM|FSE|Frankfurt|FRA|LSE|JSE)"
_INTRO_BRACKET = re.compile(r"\(" + _SP + r"*(?:the" + _SP + r"+)?[\"\u201c\u2018'`]{1,2}" + _SP + r"*[A-Z0-9]"
                            r"|\(" + _SP + r"*" + _EXCH + r"\b"
                            r"|\(" + _SP + r"*[A-Z]{2,6}" + _SP + r"*(?::|" + _SP + r"[" + _DASH + r"])" + _SP + r"*" + _EXCH, re.U)
_INTRO_WORDS = re.compile(r"\b(?:is\s+pleased|pleased\s+to|announces?|announced|reports?|today|has\s+|will\s+|"
                          r"management\s+of|further\s+to|provides?|confirms?|wishes)\b|/CNW/|Newsfile|Marketwired|"
                          r"GLOBE\s*NEWSWIRE|PR\s?Newswire|ACCESSWIRE|Business\s+Wire", re.I)
_QUOTED = re.compile("[\"\u201c\u2018]" + _SP + r"*([A-Z][\w\-]{1,})")
_NOT_NAME = {"company", "corporation", "corp", "issuer", "partnership", "the", "trust", "fund"}
_DANGLING = re.compile(r"(?:\b(?:and|or|of|the|to|for|at|in|on|with|a|an|by|from|its|their|as|into|over|under|"
                       r"between|near|than|held|dated|until|before|after|effective|ended|ending|since)|[&" + _DASH + r",:;(/])\s*$", re.I)
_LEAD = [
    re.compile(r"^(?:For" + _SP + r"+Immediate" + _SP + r"+(?:Release|Distribution)|For" + _SP + r"+immediate"
               r"" + _SP + r"+distribution|Release" + _SP + r"*:" + _SP + r"*Immediate|Immediate" + _SP + r"+Release|"
               r"For" + _SP + r"+Release|For" + _SP + r"+immediate" + _SP + r"+dissemination)" + _SP + r"*[:" + _DASH + r"]?" + _SP + r"*", re.I),
    re.compile(r"^[A-Z]{2,6}" + _SP + r"*:" + _SP + r"*" + _EXCH + r"[\w\-]*" + _SP + r"+(?=[A-Z])"),
    re.compile(r"^S\.E\.C\." + _SP + r"*Exemption" + _SP + r"*:?" + _SP + r"*12" + _SP + r"*\(g\)" + _SP + r"*3-2"
               r"" + _SP + r"*\(b\)" + _SP + r"*", re.I),
    re.compile(r"^(?:[A-Z][\w&.,'\u2019 ]{0,50}?" + _SP + r"[" + _DASH + r"]" + _SP + r")?(?:" + _EXCH + r"(?:" + _SP
               + r"+Exchange)?|Trading)?" + _SP + r"*Symbols?" + _SP + r"*:" + _SP + r"*(?:" + _EXCH + r"[\w.\s\-]{0,6}:"
               r"" + _SP + r"*)?[A-Z][A-Z0-9.]{1,7}" + _SP + r"+", re.I),
    re.compile(r"^T" + _SP + r"?SX[\w.\-]*" + _SP + r"*:" + _SP + r"*[A-Z][A-Z0-9.]{1,7}" + _SP + r"+"),
    re.compile(r"^(?:(?:" + _EXCH + r")(?:" + _SP + r"+(?:Stock" + _SP + r"+)?Exchange)?" + _SP + r"*[:" + _DASH + r"]" + _SP
               + r"*(?!Venture\b)[A-Z0-9][A-Z0-9.]{1,7}(?:" + _SP + r"?\.?" + _SP + r"?V\b)?[,;]?" + _SP + r"+)+", re.I),
    re.compile(r"^Shares" + _SP + r"+(?:Issued" + _SP + r"+and" + _SP + r"+)?Outstanding" + _SP + r"*:?" + _SP + r"*[\d,]{4,}"
               + _SP + r"*", re.I),
    re.compile(r"^(?:\d{1,2}" + _SP + r"?(?:st|nd|rd|th)?" + _SP + r"+(?:of" + _SP + r"+)?" + _MONTH + r"|" + _MONTH + _SP
               + r"+\d{1,2}(?:st|nd|rd|th)?),?" + _SP + r"+20\d\d" + _SP + r"*[" + _DASH + r":,]?" + _SP + r"+(?=[A-Z])", re.I),
    re.compile(r"^Date" + _SP + r"*:" + _SP + r"*\S+" + _SP + r"+", re.I),
    re.compile(r"^(?:Designated|Amended)" + _SP + r"+News" + _SP + r"+Release" + _SP + r"*[:" + _DASH + r"]?" + _SP + r"*", re.I),
    re.compile(r"^(?:\(" + _SP + r"*" + _EXCH + r"[^)]{0,30}\)" + _SP + r"*)+", re.I),
    re.compile(r"^" + _DATE + r"\s*[" + _DASH + r":,]+\s*", re.I),
]
_TRAIL = [
    re.compile(r"\s*\(" + _SP + r"*" + _EXCH + r"[^)]{0,40}\)\s*$", re.I),
    re.compile(r"[\s,]*" + _DATE + r"[\s" + _DASH + r":,.]*$", re.I),
    re.compile(r"[\s" + _DASH + r"|:,(]+$"),
    re.compile(r"\s+For" + _SP + r"+Immediate" + _SP + r"+(?:Release|Distribution)\s*$", re.I),
    re.compile(r"\s+(?:(?:TSX|Venture|Stock|Frankfurt|OTCQB|OTCQX|OTC|Canadian|Securities|CSE|NEX|Toronto)" + _SP
               + r"+){0,3}(?:" + _EXCH + r"|Exchange|Market)(?:" + _SP + r"*\([A-Z\-]+\))?" + _SP
               + r"*:" + _SP + r"*[A-Z0-9][A-Z0-9.]{1,7}\s*$"),
    re.compile(r"\s+(?:AMENDED" + _SP + r"+|Amended" + _SP + r"+|Designated" + _SP + r"+|DESIGNATED" + _SP + r"+)?(?:News|NEWS)" + _SP
               + r"+(?:Release|RELEASE)\s*$"),
    re.compile(r"\s[A-Z]\.?$"),
]
_LEAD_PLACE = re.compile(
    r"^(?:(?:" + _KN + r"|" + _CITY + r")" + _SP + r"*," + _SP + r"*" + _RG + r"(?:" + _SP + r"*,?" + _SP + r"*" + _RG + r")?"
    r"|" + _KN + r"(?=" + _SP + r"*[" + _DASH + r":]))" + _SP + r"*[" + _DASH + r":,.]?" + _SP + r"+(?=[A-Z(])", re.U)
_FIGURE = re.compile(r"\s(?:Figure|Photo|Table|Image|Map)" + _SP + r"*\d+" + _SP + r"*[:.\-" + _DASH[2:] + r"]", re.I)
_TAIL_MARK = re.compile(r"\sThis" + _SP + r"+(?:Announcement|announcement|news" + _SP + r"+release|press" + _SP
                        + r"+release)" + _SP + r"+(?:contains|is" + _SP + r"+not)"
                        r"|\s(?:(?:TSX" + _SP + r"+)?Venture" + _SP + r"+Exchange|TSX" + _SP + r"+Exchange|Toronto" + _SP
                        + r"+Stock" + _SP + r"+Exchange)" + _SP + r"*(?:\([^)]{1,10}\))?" + _SP + r"*:" + _SP + r"*[A-Z]{2,5}\b"
                        r"|\s[\uf0b7\u2022\u25cf\u25aa\u25a0\u25a1\u2023\u25e6\u2043\u2219](?=\s)"
                        r"|\sThis" + _SP + r"+(?:news" + _SP + r"+)?release" + _SP + r"+should" + _SP + r"+be" + _SP + r"+read")
_QUOTE_OPEN = re.compile(r"\s[\u201c\"](?=[A-Z][a-z]+\s+[a-z])")
_JUNK_RESULT = re.compile(r"For" + _SP + r"+Further" + _SP + r"+Information|Contact" + _SP + r"*:|^Shares" + _SP
                          + r"+(?:Issued|Outstanding)|Total" + _SP + r"+Basic" + _SP + r"+Shares|O/S" + _SP + r"*\(M\)|"
                          r"is" + _SP + r"+pleased|pleased" + _SP + r"+to" + _SP + r"+(?:announce|report|provide)|\b\d{3}[.\-" + _SP[1:-1]
                          + r"]\d{3}[.\-" + _SP[1:-1] + r"]\d{4}\b", re.I)
MIN_REMOVED = 8
_NOT_TITLE_START = re.compile(r"^(?:[a-z](?![A-Z\-])|[(\"\u201c\u2018/\\|]|\d[\d,.]*\s*(?:,|for\b|of\b|and\b))")

MIN_CUT_POS = 12


def _norm(h: str) -> str:
    h = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", h or "")
    h = re.sub(r"_{3,}", " ", h)
    return re.sub(r"\s+", " ", h).strip()


def _intro_follows(rest: str, full_rest_is_end: bool) -> bool:
    r = rest.lstrip(" " + _DASH + ":,./|")
    head = r[:110]
    if re.match(r"^\(?\s*" + _DATE, head, re.I) or re.match(r"^\(?\s*\d{4}\b", head):
        return True
    if _FORMAL.search(head) or _INTRO_BRACKET.search(head) or _INTRO_WORDS.search(head):
        return True
    return full_rest_is_end and len(r) < 40


def _ok(kept: str, is_hollow) -> bool:
    kept = kept.strip()
    dangling = _DANGLING.search(kept) and not re.search(r",\s*ON$", kept)     # "Kenora, ON" is a province
    return bool(kept) and not is_hollow(kept) and not dangling


def _clean_kept(kept: str) -> str:
    kept = kept.rstrip(" " + _DASH + "|:,;(/")
    m = _TRAIL[1].search(kept)                      # a date just before the dateline belongs to it
    if m and m.start() > 0:
        kept = kept[:m.start()]
    return kept.rstrip(" " + _DASH + "|:,;(/")


def _dateline_cut(h: str, is_hollow):
    cands = []
    for m in _PLACE.finditer(h):
        p = m.start("p")
        if p < MIN_CUT_POS:
            continue
        city = m.group("city")
        if city and _NOT_CITY.match(city.split()[-1]):
            continue
        ptxt = m.group("p")
        known = bool(_KNOWN_RX.match(ptxt))
        has_region = bool(city) or bool(m.group("kreg")) or ptxt.startswith("(")
        rest = h[m.end("p"):]
        at_end = not rest.strip(" " + _DASH + ":,./|")
        sep = re.match(r"^\s*(?:" + _SEP + r"|\()", rest)
        if at_end:
            trailing_comma = rest.lstrip().startswith(",")
            prev = h[:p].rstrip()
            own_location = prev.endswith(",") or re.search(r"\b(?:in|at|near|of|on|from|to|and|for|the)$", prev, re.I)
            known_any = known or bool(re.search(_KN, ptxt))
            if own_location or not (known_any and (has_region or trailing_comma)):
                continue
        elif sep:
            if h[:p].rstrip().endswith(",") or not _intro_follows(rest, True):   # "... at NWOPA, Thunder Bay - April 8"
                continue
        else:
            # no separator: a known city with its region (or in brackets), directly followed by the company
            if not (known and has_region) or not re.match(r"^\s*[A-Z]", rest) or not (
                    _FORMAL.search(rest[:80]) or _INTRO_BRACKET.search(rest[:90])):
                continue
        cands.append(p)
    for m in _DATE_SEP.finditer(h):                  # "... UPDATE March 26 th, 2018 - Standard Lithium Ltd."
        if m.start("p") >= MIN_CUT_POS and _intro_follows(h[m.end():], False) and (
                _FORMAL.search(h[m.end():m.end() + 80]) or _INTRO_BRACKET.search(h[m.end():m.end() + 90])):
            cands.append(m.start("p"))
    for p in sorted(cands):
        kept = _clean_kept(h[:p])
        if _ok(kept, is_hollow):
            return kept
    return None


def _intro_cut(h: str, first_word: str, is_hollow):
    for b in _INTRO_BRACKET.finditer(h):
        pos = b.start()
        if pos < MIN_CUT_POS + 8:
            continue
        before = h[:pos].rstrip(" ,")
        tail_words = before.split()[-3:]
        if not any(re.fullmatch(_SUFFIX + r"\.?,?", w, re.I) for w in tail_words) and not re.search(
                r"\b(?:Corp|Inc|Ltd|Limited|L td|Lt[ée]e)\.?\s*$", before, re.I):
            continue
        words = {first_word.lower()} if first_word and len(first_word) >= 2 else set()
        for q in _QUOTED.findall(h[pos:pos + 160]):
            if q.lower() not in _NOT_NAME:
                words.add(q.lower())
        best = None
        for w in words:
            for mm in re.finditer(r"(?<![\w\-])" + re.escape(w) + r"(?![\w\-])", before, re.I):
                if mm.start() >= MIN_CUT_POS and pos - mm.start() <= 75:
                    best = mm.start() if best is None else max(best, mm.start())
        if best is None and before.upper() != before:
            # ALL-CAPS title followed by a Title-case company name: "... SIGNED Earthworks Industries Inc."
            cap = re.search(r"((?:[A-Z][a-z][\w&'\u2019\-]*\.?,?\s+){1,4})" + r"\S*\s*$", before)
            head = before[:cap.start()] if cap else ""
            if cap and head and head.upper() == head and re.search(r"[A-Z]{3}", head):
                best = cap.start()
        if best is None:
            continue
        kept = h[:best]
        if _ok(kept, is_hollow):
            return kept
    return None


def _strip_lead(h: str, is_hollow) -> str:
    """Leading junk: labels, symbol lines, share counts, datelines, dates."""
    for _ in range(6):
        before = h
        for rx in _LEAD:
            m = rx.match(h)
            if m and m.end() < len(h) and not is_hollow(h[m.end():].lstrip(" " + _DASH + ":,.")):
                h = h[m.end():].lstrip(" " + _DASH + ":,.")
        m = _LEAD_PLACE.match(h)
        if m and not is_hollow(h[m.end():]):
            h = h[m.end():]
        if h == before:
            break
    return h


def trim_glued(headline: str, is_hollow) -> str:
    """The headline with the release's opening line (and junk prefixes) removed; unchanged if no safe cut."""
    orig = headline or ""
    h = _norm(orig)
    if not h or _NOT_TITLE_START.match(h):
        return orig
    h = _strip_lead(h, is_hollow)
    first = re.match(r"[A-Za-z][\w\-]*", h)
    first_word = first.group(0) if first else ""
    cut_made = False
    for _ in range(3):                                   # the glued opening line
        cut = _dateline_cut(h, is_hollow)
        if cut is None:
            cut = _intro_cut(h, first_word, is_hollow)
        if cut is None:
            for rx in (_FIGURE, _TAIL_MARK):
                fm = rx.search(h)
                if fm and fm.start() >= MIN_CUT_POS and _ok(h[:fm.start()], is_hollow):
                    cut = h[:fm.start()]
                    break
        if cut is None:
            qm = _QUOTE_OPEN.search(h)
            if qm and qm.start() >= 30 and len(h) - qm.start() >= 60 and not re.search(
                    "[\u201d\"]", h[qm.end():qm.end() + 45]) and _ok(h[:qm.start()], is_hollow):
                cut = h[:qm.start()]
        if cut is None:
            break
        h = cut.strip()
        cut_made = True
    h = _strip_lead(h, is_hollow)
    for _ in range(4):
        before = h
        for i, rx in enumerate(_TRAIL):
            if i in (1, 6) and not cut_made:         # a headline may legitimately END in a date or "Class A"
                continue
            m = rx.search(h)
            if m and m.start() > 0 and _ok(h[:m.start()], is_hollow):
                h = h[:m.start()].rstrip()
        if h == before:
            break
    h = h.strip(" " + _DASH + "|:,;(")
    if not h or _NOT_TITLE_START.match(h) or is_hollow(h) or _JUNK_RESULT.search(h) or len(_norm(orig)) - len(h) < MIN_REMOVED:
        return orig
    return h
