"""Outside-tag admission rule for the Resource Estimates reader (resources).  ROUND 4 (2026-09-30), on reader
1.0.22.  Round 4 keeps every round-3 rule and adds, for the kinds the fresh conf3 sample showed:
  - more ways another company's deposit is introduced (rule 3: a distance FROM our ground, peer and
    comparison lists, "(source: ...)", "held by X", a parenthesis that credits the figures to another
    company's report, the owner read as the deposit name; the issuer's own tickers are now read from the
    first 1,200 characters only, and a royalty word inside a company or place name ("X Royalties Inc.",
    "<Name> Stream") no longer exempts the release as a royalty release);
  - the same figures filed under two deposit names (rule 2c);
  - wordings around a restated own estimate that the reader turns into wrong rows (rule 5: exploration
    target, a subset inside a larger estimate, "indicated and inferred" stated together, a tonnage in kt / Mt
    in front of the category that the reader did not read).
Earlier history: round 2, revised for reader 1.0.22
(2026-09-30): the "bare tonnage" refusal (no deposit, no grade, no contained) is removed. Reader 1.0.22 blanks a
deposit name that is a sentence fragment or column label instead of emitting it, so a row with no deposit is now
usually a real row whose name the release does not give; "deposit is not a name" still refuses garbage names.
On the harness: +3 true rtag releases admitted for 1 wrong row; in-tag sanity 79/84 true releases at 98.2%.

When the resources reader finds rows in a release that does NOT carry the "Resource Estimates" tag, this rule
decides whether the release gets the tag and its rows go on the page.

For this reader a restated resource in an About paragraph is a legitimate row (the label guide publishes every
figure and marks it `background`), so background by itself is not a reason to refuse.  What goes wrong outside
the tag is different:

  1. the reader reads figures that are not in the text we have (it saw the boilerplate tail / About section that
     the body passed here has cut, or it invented them);
  2. malformed rows: a grade or a "2028" read as a tonnage, a sentence fragment or footnote read as the deposit,
     a row with no deposit and no tonnage, the same row copied under a second category, "Total" rows;
  3. somebody else's deposit: a neighbour, an analogue, the famous deposits of the belt, a figure credited to
     another company's report.  Round 1 caught this only through a few location words; on the fresh sample it
     was the largest error (11 of 60 admitted releases), so round 2 also looks for another company NAMED next
     to the figures;
  4. a study or results release where the reader caught one summary line and not the table.

Each check refuses the WHOLE release (rows cannot be dropped one by one here).  Standard library only.
"""
import bisect
import re

# ---------------------------------------------------------------------------------------------------------
# Rule 1 -- every figure on every row must be in the headline or body.
# For: financings, AGM results, appointments, drill results, etc. whose resource figures sit in an About
# paragraph that is not part of the text (the reader read the tail), and rows with invented numbers.
# ---------------------------------------------------------------------------------------------------------
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_PDF_SPLIT = re.compile(r"\d+(?:[.,]\d+)*[ \u00a0]\d{1,2}\b(?![.,]\d)")   # "141,00 0": a number split by the pdf
_T_SCALES = (1, 1e3, 1e6, 1e9, 1e-3, 0.90718474, 907.18474, 907184.74)  # t, kt, Mt, Bt; short tons
_C_SCALES = (1, 1e3, 1e6, 1e9, 1e-3, 1e-6)                              # oz/koz/Moz, lb/Mlb/Blb, t/kt/Mt
_TOL = 0.006

_THOUS = re.compile(r"\d{1,3}(,\d{3})+(\.\d+)?")
_EURO = re.compile(r"\d{1,3}(\.\d{3})+(,\d+)?")
_DECCOMMA = re.compile(r"\d+,\d+")


def _values(s):
    """All plausible readings of one number token: 1,234.5 / 1.234,5 / 12,5 (decimal comma)."""
    if "," not in s:
        if s.count(".") <= 1:
            return (float(s),)                     # the common case: 12 / 0.45
        out = set()
        if _EURO.fullmatch(s):
            out.add(float(s.replace(".", "")))
        return out
    if _THOUS.fullmatch(s):
        return (float(s.replace(",", "")),)
    out = set()
    if _EURO.fullmatch(s):
        out.add(float(s.replace(".", "").replace(",", ".")))
    if _DECCOMMA.fullmatch(s):
        out.add(float(s.replace(",", ".")))
    try:
        out.add(float(s.replace(",", "")))
    except ValueError:
        pass
    return out


def _tokens(text):
    """Sorted index [(value, position)] of every number in the text, plus the pdf-split joins (position -1)."""
    idx = []
    for m in _NUM.finditer(text):
        g = m.group()
        if "," not in g and g.count(".") <= 1:
            idx.append((float(g), m.start()))
        else:
            idx += [(v, m.start()) for v in _values(g)]
    for m in _PDF_SPLIT.finditer(text):
        idx += [(v, -1) for v in _values(re.sub(r"[ \u00a0]", "", m.group()))]
    idx.sort()
    return idx, [v for v, _p in idx]


def _positions(v, scales, index):
    """Positions of the numbers that equal v (within _TOL) in any of the given units."""
    idx, keys = index
    out = []
    for k in scales:
        lo, hi = v * (1 - _TOL) / k, v * (1 + _TOL) / k
        if lo > hi:
            lo, hi = hi, lo
        i = bisect.bisect_left(keys, lo)
        while i < len(keys) and keys[i] <= hi:
            out.append(idx[i][1])
            i += 1
    return out


def _figures(r):
    f = []
    if r.get("tonnes"):
        f.append((r["tonnes"], _T_SCALES))
    for g in r.get("grades") or []:
        if isinstance(g, dict) and g.get("value"):
            f.append((g["value"], (1,)))
    for c in r.get("contained") or []:
        if isinstance(c, dict) and c.get("value"):
            f.append((c["value"], _C_SCALES))
    return f


def _grounding(r, index):
    """-> (all figures found?, [for each figure, the positions where it was found])."""
    figs = _figures(r)
    if not figs:
        return False, []
    per = []
    for v, sc in figs:
        hit = _positions(v, sc, index)
        if not hit:
            return False, []
        per.append(sorted({p for p in hit if p >= 0}))
    return True, per


# ---------------------------------------------------------------------------------------------------------
# Rule 2 -- malformed rows.  These are reader misreads, not real estimates.
# For: a grade or "1.9" taken as the tonnage (no resource is under 10,000 t); a date, a footnote or a sentence
# fragment read as the deposit ("2028 Minto", "( , December 20, 2019)", "Ontario. The newly acquired": a
# deposit name starts with a letter and does not run across a full stop); orphan figures with neither deposit
# nor tonnage (a contained total from a summary sentence); a bare tonnage with no deposit and no grade; and
# "Total" rows (on this reader a Total row has not once matched a labelled row, in or outside the tag).
# ---------------------------------------------------------------------------------------------------------
def _malformed(r):
    t = r.get("tonnes")
    dep = str(r.get("deposit") or "").strip()
    if t is not None and t < 10000:
        return "tonnage too small"
    if dep and (not re.match(r"[^\W\d_]", dep) or re.search(r"[a-z]\.\s+[A-Z]", dep)):
        return "deposit is not a name"
    # Round 4: the owner read as the deposit -- a name ending in a possessive ("X Lithium's") is the company
    # that owns the figures, which on this page is another company ("host to X Lithium's deposit with ...").
    if dep and re.search(r"['\u2019]s?$", dep):
        return "deposit is an owner's name"
    if not dep and t is None:
        return "no deposit, no tonnage"
    if r.get("category") == "Total":
        return "total row"
    return None


# Rule 2b -- the same row copied under a second category.
# For: releases that give "an Indicated Resource of A t and an Inferred Resource of B t" where the reader filed
# B under both categories.  One tonnage and grade never belong to two different categories; the exception is
# a combined category equal to one of its parts (Proven & Probable = Probable when there is no Proven), which
# is legitimate and not caught.  Never seen in ~2,100 labelled rows.
def _duplicated(rows):
    seen = {}
    for r in rows:
        if not r.get("tonnes"):
            continue
        k = (r["tonnes"], r.get("basis"),
             tuple(sorted((str(g.get("metal")), g.get("value") or 0) for g in r.get("grades") or []
                          if isinstance(g, dict))))
        cat = str(r.get("category"))
        for other in seen.get(k, ()):
            if cat not in other and other not in cat:
                return True
        seen.setdefault(k, set()).add(cat)
    return False


# ---------------------------------------------------------------------------------------------------------
# Rule 3 -- somebody else's deposit, judged from the words around the row's figures.
# For: exploration, staking, financing, warrant-extension and management releases that describe the company's
# ground by the resources of the ground next door or of well-known deposits in the same belt.
#
# a. Wording that puts the figures on other ground or offers them as a comparison (700 characters before):
#    "analog\u2026", "for example", "notable deposits (of the belt) include" (the regional-peer list), and
#    "neighbouring", "bordering", "within N km of", "near the known".
#    (Plain "adjacent" or "N km east of" were tried and dropped: they describe the company's own project far
#    more often than a neighbour's.)
# b. Wording that disowns or credits the figures: "cannot verify", "not (necessarily) indicative" (700 before /
#    400 after), a "Source:" footnote (500 after), "see X's news release" (400 either side).
# c. Another company is NAMED as the owner, close to the figures:
#      - "X's [Name] project/deposit/mine/property" (a possessive proper name),
#      - "X Metals has identified ...", "X Corp., [Name] Project where ..." (a name with a legal suffix),
#      - "(X, December 31, 2020)" (a figure credited to another company's dated report),
#      - a stock ticker "(TSX: ABC)" that is not the issuer's.
#    X counts as another company only when none of its words belong to the issuer (the names in the lead's
#    '("X" or the "Company")' parenthesis, the name in front of the issuer's ticker, the first words of the
#    headline) or to the row's own deposit name.  The name must be within 300 characters before the figures,
#    or further back when the project it owns is named again between it and the figures ("X's Valentine Gold
#    Project contains ... The Valentine Gold Project has reserves of ...").  Not counted: a name after "by"
#    (the consultant or the vendor), after "the" or before Island/Lake/River/... (a place: "the historic
#    Pilley's Island Mine"), and releases about a royalty or stream, where the operator is necessarily another
#    company and the label guide still publishes the deposit's figures.
# ---------------------------------------------------------------------------------------------------------
_OTHER_BEFORE = re.compile(r"\b(analog\w*|neighbou?ring|bordering|near the known|"
                           r"notable deposits|for example|"
                           r"within \d+ ?(?:k ?m|kms|kilomet\w+) of)\b")
_OTHER_AROUND = re.compile(r"\b(cannot verify|not (?:necessarily )?indicative)\b")
_OTHER_SOURCE = re.compile(r"\bSource:")
_OTHER_CITE = re.compile(r"(?i)\bsee\s+(?!the\s+company|our\b|its\b)[A-Z][\w\-]*(?:\s+[A-Z][\w\-]*){0,4}\s*['\u2019]s?"
                         r"\s+(?:\w+\s+){0,2}(?:news|press)\s+release")

# Round 4 additions to 3a/3b (fresh sample conf3: 8 of 58 admitted releases showed only a neighbour's deposit).
#  - "notable <metal> projects / deposits / discoveries including" (the regional-peer list, not only "notable
#    deposits"), "deposits worldwide" (a comparison list), "the following references" (a list of other
#    parties' occurrences);
#  - a lower-case "(source: ...)" credit after the figures, as well as "Source:";
#  - the place of the figures given as a distance FROM the company's ground: "located 4 km south of the
#    Licenses", "located 26 km to the south" (what lies N km from our property is not our property).  The
#    reverse, "our property is located 25 km north of <town / mine>", is not caught: it describes our ground.
#    ("proximal to" was tried and dropped: it refused two releases whose own estimate followed it.)
_OTHER_BEFORE4 = re.compile(r"\b(notable (?:\w+ ){0,2}(?:deposits|projects|mines|discoveries)|"
                            r"(?:deposits|projects|mines) worldwide|following references)\b")
_OTHER_SOURCE4 = re.compile(r"\(source:")
_DISTANCE_FROM_OURS = re.compile(r"\blocated\s+(?:approximately\s+|about\s+|some\s+)?\d+(?:\.\d+)?\s?(?:km|kms|kilomet\w+)\s+"
                                 r"(?:to\s+the\s+(?:north|south|east|west)\w*\b|(?:north|south|east|west)\w*\s+of\s+the\s+"
                                 r"(?:\w+\s+){0,2}?(?:property|properties|project|licen[cs]es|claims?|tenements?|"
                                 r"concessions?)\b)")

_PARAGRAPH = re.compile(r"\n[ \t]*\n")
_SP = r"[ \u00a0\n]+"
_NAME = r"[A-Z][\w&\-]*(?:" + _SP + r"[A-Z][\w&\-]*){0,3}"
_MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_POSS = re.compile(r"\b(" + _NAME + r")[ \u00a0]?(?:['\u2019]s|s['\u2019])" + _SP + r"(?:\([^()]{0,30}\)" + _SP + r")?"
                   r"((?:[A-Z0-9][\w\-]*" + _SP + r"){0,4})"
                   r"(?i:project|deposit|mine|property|discovery|claims|operation|filings)\b")
_CORP = re.compile(r"\b(" + _NAME + r")" + _SP + r"(?:Corp\w*|Inc|Ltd|Limited|plc|Metals|Mining)\b\.?,?" + _SP +
                   r"(?:has|have|had|where|((?:[A-Z][\w\-]*" + _SP + r"){1,2})(?i:project|deposit|mine|property))\b")
_DATED = re.compile(r"\((" + _NAME + r"),[ \u00a0]+" + _MONTH + r"[ \u00a0]+\d")
_TICKER = re.compile(r"\((?:TSX[\-.]?V?|ASX|CSE|NYSE(?: American)?|NASDAQ|AIM|LSE|JSE|OTC\w*)\s*[:\-]\s*([A-Z0-9.]{2,6})\)")
# Round 4 additions to 3c (another company named as the owner):
#  - "is held / owned / operated by X" in front of the figures ("the Y deposit lies just east of our ground
#    and is held by X"); not a name starting with "The" (a land-holding body, "owned by The X Corporation"),
#    and not a partner's share ("the remaining 49% interest is held by X": the project is still ours);
#  - after the figures (within 500 characters), a parenthesis that credits them to another company's report:
#    "(December 2023 Quarterly Report, X Resources Limited, 29 January 2024)", "(X Finance Corp., 2017)".
#    Only a name that opens the parenthesis or follows a comma counts, so "(prepared by X Consulting Inc.)"
#    does not; nor a consultant's or a newswire's name ("(..., X Consulting Canada Ltd, June 19, 2023)",
#    "(Newsfile Corp. - <date>)"); nor a figure the issuer holds an interest in ("a 50% interest in the Y
#    Inferred Resource of ... (X Inc., Technical Report)"), nor a historical estimate credited to the
#    explorer who made it ("a historical inferred resource of ... (X Ltd., filed in 2008)"): the label guide
#    publishes both as the company's background.
_HELD = re.compile(r"\b(?:held|owned|operated|controlled)" + _SP + r"by" + _SP + r"(" + _NAME + r")")
_CITED = re.compile(r"\((?:[^()]{0,80}?,[ \u00a0\n]*)?(" + _NAME + r")" + _SP + r"(?:Corp\w*|Inc|Ltd|Limited|plc)\b")
_NOT_OWNER = re.compile(r"(?i)consult|geoscien|engineer|associates|services|laborator|newsfile|newswire|wire\b|globe")
_HISTORIC = re.compile(r"(?i)\bhistoric")
_STAKE = re.compile(r"(?i)\binterests?\b[^.;]{0,40}?\b(?:in|of)\b")
_PLACE = re.compile(r"(?:Island|Lake|River|Bay|Creek|Point|Cove|Harbou?r|Mountain|Hill|Peak|Valley|Brook|Pond|"
                    r"Falls|Landing|Arm)\b")
_GENERIC = {"the", "company", "corporation", "corp", "inc", "ltd", "limited", "plc", "gold", "metals", "metal",
            "mining", "mines", "minerals", "resources", "resource", "silver", "copper", "exploration", "ventures",
            "group", "and", "of", "effective", "date", "project", "mine", "deposit", "new", "north", "south", "east",
            "west", "canada", "canadian"}
_ROYALTY = re.compile(r"(?i)\broyalt(?:y|ies)\b|\bstream(?:s|ing)?\b(?!\s+(?:sediment|bed|flow|channel))")


def _own(headline, text):
    """Name words and tickers of the issuer, from the headline and the lead; and whether it is a royalty release."""
    lead = headline + "\n" + text[:2000]
    names = []
    for m in re.finditer(r"\(([^()]{0,160}?[\u201c\"](?:the\s+)?(?:Company|Corporation|Issuer)[\u201d\"][^()]{0,160})\)",
                         lead, re.I):
        names += re.findall(r"[\u201c\"]([^\u201d\"]{1,50})[\u201d\"]", m.group(1))
    for m in re.finditer(r"(" + _NAME + r")\.?,?[ \u00a0]*\((?:TSX|ASX|CSE|NYSE|NASDAQ|OTC|FSE|AIM|LSE)", lead):
        names.append(m.group(1))
    names.append(" ".join(headline.split()[:3]))
    words = {w.lower() for n in names for w in re.findall(r"[^\W\d_]+", n)} - _GENERIC
    # The issuer's own tickers sit in the dateline / first paragraph.  (Round 4: the window was 2,000
    # characters, which on short releases reached the neighbour's "(ASX: ABC)" in the second paragraph.)
    top = headline + "\n" + text[:1200]
    tickers = set(re.findall(r"\b[A-Z0-9]{2,6}\b", " ".join(re.findall(r"\([^()]{0,120}\)", top))))
    return words, tickers, any(_royalty_word(lead, m) for m in _ROYALTY.finditer(lead))


def _royalty_word(lead, m):
    """Round 4: a royalty / stream release, not a name -- "X Royalties Inc." (the issuer's own name) and a
    place called "<Name> Stream" do not make a release about a royalty."""
    if re.match(r"[ \u00a0]*(?:Inc|Corp\w*|Ltd|Limited|plc)\b", lead[m.end():m.end() + 14]):
        return False
    w = m.group(0)
    if w[:6] == "Stream" and re.search(r"[A-Z][\w\-]*[ \u00a0]+$", lead[max(0, m.start() - 25):m.start()]):
        return False
    return True


def _whole_name(text, m):
    """False when the match starts inside a longer capitalised name, or right after "the" or "by"."""
    before = text[max(0, m.start(1) - 20):m.start(1)].split()
    if m.group(1).split()[0] == "The":
        return False
    if not before:
        return True
    prev = before[-1]
    if prev.lower() in ("the", "by"):
        return False
    return not re.match(r"[A-Z][\w&\-]*$", prev)


def _foreign(name, own_words):
    ws = [w for w in (x.lower() for x in re.findall(r"[^\W\d_]+", name)) if w not in _GENERIC]
    return bool(ws) and not any(w in own_words for w in ws)


def _centre(per):
    """Where the row sits in the text.  Anchored on the row's rarest figure (a tonnage like 45.4 is found once;
    a grade like 1 or 7 is found everywhere), at the occurrence with the most of the row's other figures within
    300 characters."""
    per = [p for p in per if p]
    if not per:
        return None
    anchor = min(per, key=len)
    others = sorted(x for p in per for x in p)
    best, best_n = anchor[0], -1
    for x in anchor:
        n = bisect.bisect_right(others, x + 300) - bisect.bisect_left(others, x - 300)
        if n > best_n:
            best, best_n = x, n
    return best


_POSS_MARK = re.compile(r"(?:['\u2019]s|s['\u2019])[ \u00a0\n]")
_CORP_MARK = re.compile(r"\b(?:Corp\w*|Inc|Ltd|Limited|plc|Metals|Mining)\b")


def _scan(rx, marker, text):
    """rx.finditer, but only around the marker words (the possessive, the legal suffix) -- the same matches
    at a fraction of the cost on long, capital-heavy tables."""
    if marker is None:
        yield from rx.finditer(text)
        return
    seen = set()
    for k in marker.finditer(text):
        for m in rx.finditer(text, max(0, k.start() - 80), min(len(text), k.end() + 160)):
            if m.span() not in seen:
                seen.add(m.span())
                yield m


def _mentions(text, own):
    """Every place in the body where another company is named as an owner: [(start, end, name, project, kind)].
    Computed once per release; each row then looks only at the mentions in its own window."""
    words, tickers, royalty = own
    if royalty:
        return []
    out = []
    for rx, marker in ((_POSS, _POSS_MARK), (_CORP, _CORP_MARK), (_DATED, None)):
        for m in _scan(rx, marker, text):
            proj = " ".join((m.group(2) or "").split()) if rx.groups >= 2 else ""
            if rx is _POSS and _PLACE.match(proj):
                continue
            if _whole_name(text, m) and _foreign(m.group(1), words):
                out.append((m.start(), m.end(), " ".join(m.group(1).split()), proj, "named"))
    for m in _TICKER.finditer(text):
        if m.group(1) not in tickers:
            out.append((m.start(), m.end(), m.group(1), "", "ticker"))
    # Round 4: owners named without a possessive or a legal suffix, and credits after the figures.
    for m in _HELD.finditer(text):
        if (m.group(1).split()[0] != "The" and _foreign(m.group(1), words)
                and not re.search(r"(?i)interests?\W+(?:\w+\W+){0,2}$", text[max(0, m.start() - 30):m.start()])):
            out.append((m.start(), m.end(), " ".join(m.group(1).split()), "", "named"))
    for m in _CITED.finditer(text):
        if not _NOT_OWNER.search(m.group(1)) and _foreign(m.group(1), words):
            out.append((m.start(), m.end(), " ".join(m.group(1).split()), "", "cited"))
    return out


# (regex, characters before, characters after, literal words one of which must be present, match on lowercase?)
_PHRASES = ((_OTHER_BEFORE, 700, 60, ("analog", "neighbo", "bordering", "near the known", "notable deposits",
                                      "for example", "within"), True),
            (_OTHER_AROUND, 700, 400, ("cannot verify", "indicative"), True),
            (_OTHER_SOURCE, 0, 500, ("Source:",), False),
            (_OTHER_CITE, 400, 400, ("release",), True),
            (_OTHER_BEFORE4, 700, 60, ("notable", "worldwide", "references"), True),
            (_OTHER_SOURCE4, 0, 500, ("(source:",), True),
            (_DISTANCE_FROM_OURS, 400, 60, ("located",), True)
            )
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def _phrases(text):
    """Every rule-3a/3b phrase in the body with the window (before, after) it applies in.  Computed once."""
    low = text.lower()
    if len(low) != len(text):                     # a character whose lowercase is longer: keep positions exact
        low = text.translate(_ASCII_LOWER)
    out = []
    for rx, a, b, words, lower in _PHRASES:
        if not any(w in (low if lower else text) for w in words):
            continue
        for m in rx.finditer(low if lower and rx is not _OTHER_CITE else text):
            out.append((m.start(), m.end(), a, b, m.group(0).strip().lower()[:30]))
    return out


def _other_company(text, per, phrases, mentions, deposit):
    c = _centre(per)
    if c is None:
        return None
    for start, end, a, b, label in phrases:
        if start >= c - a and end <= c + b:
            # the distance wording must sit in the figures' own paragraph: "(the X mine is located 80 km to
            # the south)" two paragraphs above our own estimate places the mine, not our figures
            if label.startswith("located") and _PARAGRAPH.search(text, end, c):
                continue
            return label
    dep = {w.lower() for w in re.findall(r"[^\W\d_]+", str(deposit or ""))}
    lo = max(0, c - 700)
    for start, end, name, proj, kind in mentions:
        if kind == "cited":                       # a credit after the figures
            if (c <= start <= c + 500 and _foreign(name, dep) and not _STAKE.search(text, max(0, c - 400), c)
                    and not _HISTORIC.search(text, max(0, c - 400), start)):
                return "cited: " + name[:24]
            continue
        if start < lo or end > c + 60:
            continue
        if kind == "named" and not _foreign(name, dep):
            continue                              # the name is part of the row's own deposit name
        if c - end <= 300:
            return kind + ": " + name[:24]
        # further back: only when the project it owns is named again between it and the figures
        if kind == "named" and len(proj) >= 4 and proj in " ".join(text[end:c].split()):
            return kind + ": " + name[:24]
    return None


# Rule 2c (round 4) -- the same figures filed under two deposit names.
# For: an About paragraph that states the company total ("a total of 16.0 Mt LCE Measured and Indicated") and
# a footnote that credits the same figure to the one project it comes from; the reader files it twice, once
# under each name.  One figure of one category never belongs to two different deposits.
def _two_names(rows):
    seen = {}
    for r in rows:
        figs = (r.get("tonnes"),) if r.get("tonnes") else tuple(sorted(
            c.get("value") for c in r.get("contained") or [] if isinstance(c, dict) and c.get("value")))
        if not figs:
            continue
        k = (str(r.get("category")), figs)
        dep = str(r.get("deposit") or "").strip().lower()
        if k in seen and seen[k] != dep:
            return True
        seen.setdefault(k, dep)
    return False


# ---------------------------------------------------------------------------------------------------------
# Rule 5 (round 4) -- a restated estimate the reader misreads, judged from the words right around a row.
# On this reader a restated own estimate is a valid background row, so these releases are worth having; but
# each of these wordings marks a figure the reader turns into a wrong row, and a row cannot be dropped here.
#   a. "exploration target" earlier in the same sentence as a row's tonnage: a conceptual range, never a
#      classified estimate, even when the sentence says "an Inferred Resource Estimate of between 19 and 23 Mt".
#   b. a higher-grade subset quoted inside a larger estimate ("Included within the global resource is ...",
#      "a subset of", guide s.4); the reader publishes the subset as a second row.
#   c. a figure stated for "indicated and inferred" together, with no split, filed under one category: the
#      label guide files it as Total.  Only when no other row sits next to it (a pair of rows next to
#      "indicated and inferred resources of A and B respectively" is the split and is fine).
#   d. a grade-and-metal row with no tonnage when a tonnage in kt / Mt / tonnes stands right in front of the
#      category ("270 kt of Proven Mineral Reserves averaging 2.70 g/t"): the reader missed the unit and the
#      row comes out without its tonnage.
# ---------------------------------------------------------------------------------------------------------
_TARGET = re.compile(r"(?i)\bexploration\s+target")
_SENTENCE_END = re.compile(r"[.;:]\s|\n\s*\n|\u2022")
_SUBSET = re.compile(r"(?i)\b(?:included\s+within\s+(?:the|this|these)|(?:a|is\s+a)\s+subset\s+of)\b")
_COMBINED = re.compile(r"(?i)\b(?:measured,?\s+)?indicated\s+(?:and|&|\+)\s+inferred\b")
_TONNAGE_BEFORE = re.compile(r"(?i)\d[\d,.]*\s*(?:kt|mt|t|kilotonnes|tonnes|tons)\s+(?:of\s+)?(?:\w+\s+){0,2}"
                             r"(?:proven|probable|measured|indicated|inferred)")


def _same_sentence_before(rx, text, positions, reach):
    """True when rx occurs before one of the positions, within reach characters and in the same sentence."""
    for p in positions:
        for m in rx.finditer(text, max(0, p - reach), p):
            if not _SENTENCE_END.search(text, m.end(), p):
                return True
    return False


def _misread(text, rows, centres, bodies):
    for i, (r, c, body) in enumerate(zip(rows, centres, bodies)):
        if c is None:
            continue
        if r.get("tonnes") and body and _same_sentence_before(_TARGET, text, body[0], 300):
            return "exploration target"
        if _SUBSET.search(text, max(0, c - 250), c + 20):
            return "subset of a larger estimate"
        if r.get("category") in ("Indicated", "Inferred", "Measured") and _COMBINED.search(text, max(0, c - 200), c + 60):
            if not any(j != i and d is not None and abs(d - c) < 400 for j, d in enumerate(centres)):
                return "indicated and inferred stated together"
        if r.get("tonnes") is None and r.get("grades") and _TONNAGE_BEFORE.search(text, max(0, c - 200), c + 20):
            return "tonnage in front of the category not read"
    return None


# ---------------------------------------------------------------------------------------------------------
# Rule 4 -- the release's own ("announced") estimate must have a tonnage.
# For: feasibility-study / PEA / quarterly releases where the reader caught a single summary line
# ("over 1 Moz at 0.64 g/t") and missed the table: an announced estimate is always published with tonnes.
# Background rows quoting contained ounces only are fine and are not affected.
# ---------------------------------------------------------------------------------------------------------
def _announced_without_tonnage(rows):
    ann = [r for r in rows if r.get("context") == "announced"]
    return bool(ann) and all(r.get("tonnes") is None for r in ann)


def admit(headline, text, categories, out):
    """-> (bool, short_reason)"""
    rows = (out or {}).get("rows") if isinstance(out, dict) else out
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    if not rows:
        return False, "no rows"
    headline, text = headline or "", text or ""
    index = _tokens(headline + "\n" + text)
    context = None                                # (phrases, mentions): built on first need
    off = len(headline) + 1                       # body positions for the context windows
    centres, bodies = [], []
    for r in rows:
        ok, per = _grounding(r, index)
        if not ok:
            return False, "figure not in text"
        why = _malformed(r)
        if why:
            return False, "malformed: " + why
        if context is None:
            context = (_phrases(text), _mentions(text, _own(headline, text)))
        body = [[p - off for p in ps if p >= off] for ps in per]
        who = _other_company(text, body, context[0], context[1], r.get("deposit"))
        if who:
            return False, "other company: " + who
        centres.append(_centre(body))
        bodies.append(body)
    if _duplicated(rows):
        return False, "malformed: row duplicated under two categories"
    if _two_names(rows):
        return False, "malformed: the same figures under two deposit names"
    why = _misread(text, rows, centres, bodies)
    if why:
        return False, "misread: " + why
    if _announced_without_tonnage(rows):
        return False, "announced without tonnage"
    return True, "figures in text"
