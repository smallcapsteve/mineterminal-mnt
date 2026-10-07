"""ECON_V1 -- reading an economic study out of a news release.

Written against the 50-release set Justin confirmed on 2026-09-20. The rules below are not
invented; each one exists because a release in that set breaks the naive version of it.
"""
import re

VERSION = "1.0.1"   # 1.0.1 = economics 1.0.14 (FIX8, 2026-10-06): throughput, annual production, unit costs (b: figures glued to their unit, linking words, per-year figures, currency and footnote forms)
TEXT_LIMIT = 20000

# ---------------------------------------------------------------- what part of a release to read
_RE_FLS = re.compile(r"(?i)(forward[\s-]looking\s+(?:statements?|information)|"
                     r"cautionary\s+(?:note|statement)|caution\s+regarding|safe\s+harbou?r)")


def readable(body, keep_all=False):
    """The release minus its legal disclaimer.

    That paragraph names every metric an economic study reports -- 'estimates of life of mine,
    capital and operating costs, IRR, NPV and cash flows' -- and states none of them, so it is the
    densest run of economics vocabulary in most releases. Century Lithium's permitting update has
    NPV and IRR in it and not one figure. Cut at the disclaimer unless it starts in the first
    quarter of the body, which would mean the release opens with it and there is nothing to keep."""
    if keep_all:
        return body or ""
    m = _RE_FLS.search(body or "")
    return (body or "")[:m.start()] if m and m.start() > len(body or "") * 0.25 else (body or "")


# ---------------------------------------------------------------- numbers
_MULT = {"k": 1e3, "thousand": 1e3, "thousands": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6,
         "millions": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9, "billions": 1e9}
# Every result figure a release states is millions of dollars at least. A currency amount with no
# magnitude and under a hundred thousand is a price, a unit cost or a fragment of a number the
# release broke across lines -- Westhaven's 'US$2 ,400 per ounce' was published as a US$2 NPV,
# Cascadia's 'US$3.75 /lb copper' as a US$3.75 one.
_MIN_BARE = 1e5
# ...and no junior's study is worth a hundred billion: PMET writes '~$1,594 billion' once for the
# ~$1,594 million it states everywhere else.
_MAX_RESULT = 1e11
# 1.0.10: a figure followed by a quantity unit is a quantity, not money: Tocantinzinho's '1.1 million tonnes' was published
# as a US$1.1 million NPV, OceanaGold's '2.2 million gold ounces' as a US$2.2 million one
_RE_QTY_AFTER = re.compile(r"(?i)^\s*(?:of\s+)?(?:gold\s+|silver\s+|copper\s+|lithium\s+)?(?:equivalent\s+)?"
                           r"(?:tonnes|tons|t\b|ounces|oz\b|lbs?\b|pounds|metres|meters|km\b|hectares|ha\b|carats|cubic|barrels|boe)")
# 1.0.10: a table's unit header before a bare cell - 'NPV5% USD MM $409' (millions), 'Capital K US$ 278,092' (thousands)
_RE_SCALE_M = re.compile(r"(?i)(?:\b(?:US|USD|C|CAD|CA|A|AUD)\s*\$?\s*|\$\s*)?\b(?:MM|mn|millions?)\s*$|\(\s*(?:US|C|CA|A)?\$\s*(?:M|MM|millions?)\s*\)\s*$")
_RE_SCALE_K = re.compile(r"(?i)\bK\s*$|\(\s*(?:US|C|CA|A)?\$\s*000'?s?\s*\)\s*$")


def _qty_after(text, end):
    return bool(_RE_QTY_AFTER.match(text[end:end + 30]))


def _repair(text):
    """1.0.10: words and numbers a PDF split - OceanaGold's 'NPV of $665 mi llion' was read without its magnitude, and
    Sigma's 'US$12 3.1 million' as US$3.1 million (the joined figure is stated elsewhere in the release: '123.1 million')."""
    t = re.sub(r"(?i)\b(mi|bi)\s(llion)\b", r"\1\2", text or "")
    t = re.sub(r"(?i)\b(mil|bil)\s(lion)\b", r"\1\2", t)

    def join(m):
        joined = m.group(2) + m.group(3)
        return m.group(1) + joined + m.group(4) if re.search(r"(?<![\d.,])" + re.escape(joined) + r"\s*(?:million|billion|M\b)", t) else m.group(0)
    return re.sub(r"((?:US|C|CA|A)?\$\s?)(\d{1,2}) (\d{1,2}\.\d+)(\s*(?:million|billion))", join, t)
_RE_MONEY = re.compile(r"""(?ix)
    (?<![A-Za-z])                # 'CA$' must not be entered at its 'A$': Lomiko writes CA$797.5 M
    (?:(?P<cur>CDN\s*\$?|CA\$|CAD\s*\$?|C\$|US\$|USD\s*\$?|AUD\s*\$?|A\$|\$)
       (?:\s*(?P<neg>[-−]))?)?\s*   # Arizona Metals' base case is 'US$-6 million': a loss, not a gain
    (?<![\d.,])                  # never start inside a number: Doubleview's typo 'C13.53 billion'
                                 # was read from its second digit as 3.53 billion
    (?P<num>\d[\d,]*(?:\.\d+)?)\s*
    (?:(?P<mult>billions?|millions?|thousands?|bn|mm|[KMB])\d?)?\b
                                 # 'C$992 million3' carries a footnote digit on its magnitude,
                                 # and without it the capital cost was read as C$992
    (?!\s*%)                    # a percentage is not money: 'NPV (5%) of C$24.27 million'
                                 # would otherwise return 5, which is the discount rate
    """)


def _signed(m, v):
    return -v if m.groupdict().get("neg") else v


def numval(raw):
    """A number as written. '5,323' is five thousand three hundred and twenty-three; Tantalex
    writes its capital cost as 'US$147,7M', where the comma is a decimal point -- read as a
    thousands separator that is a capital cost ten times too large."""
    raw = (raw or "").strip()
    if re.fullmatch(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?", raw):
        return float(raw.replace(",", ""))
    m = re.fullmatch(r"(\d+),(\d{1,2})", raw)
    if m:
        return float(m.group(1) + "." + m.group(2))
    return float(raw.replace(",", ""))


def money(text, scale=None):
    """The first currency amount in `text`, as (value, currency-or-None).

    'C$24.27 million' -> (24270000.0, 'CAD'); 'US$1.49B' -> (1.49e9, 'USD').

    A bare number is NOT money. It must carry a currency mark or a magnitude word, or two things
    break: 'Post-Tax NPV8 of US$2.0 Billion' returns 8 (the discount rate glued to the label), and
    'IRR of 55.2% and initial capital of US$290 million' returns 55 (the regex backtracks around
    the percent guard and matches the integer part). A flattened table cell has neither mark nor
    word -- its magnitude lives in a header like '$ million' -- so the caller passes `scale`."""
    for m in _RE_MONEY.finditer(text or ""):
        cur_raw = (m.group("cur") or "").upper().replace("$", "").strip() or None
        mult = (m.group("mult") or "").lower()
        if not cur_raw and not mult and scale is None:
            continue
        try:
            v = numval(m.group("num"))
        except ValueError:
            continue
        v *= _MULT.get(mult, 1.0) if mult else (scale or 1.0)
        return _signed(m, v), {"C": "CAD", "CA": "CAD", "CAD": "CAD", "CDN": "CAD",
                   "US": "USD", "USD": "USD", "A": "AUD", "AUD": "AUD"}.get(cur_raw)
    return None, None


_RE_PCT = re.compile(r"(?P<num>\d{1,3}(?:\.\d+)?)\s*%")
# STLLR states every figure twice: 'Base Case After-Tax NPV5% of C$1.36 billion (US$1.01
# billion)'. The bracketed one is the same money in another currency, not a second scenario.
_RE_CONVERSION = re.compile(r"(?i)^[\d,.]*\s*(?:billion|million|thousand|bn|mm|[KMB])?\s*\(\s*$")


def percent(text):
    m = _RE_PCT.search(text or "")
    return float(m.group("num")) if m else None


_RE_YEARS = re.compile(r"(?i)(?P<num>\d{1,3}(?:\.\d+)?)[\s-]*(?P<unit>years?|yrs?|months?|mths?)\b")
# a flattened table puts the unit in its own cell BEFORE the value: 'Payback Period (months) 30',
# 'Mine Life yrs 7.25'. Desert Gold does this in one release and writes '3.3 years' in another.
# The unit must be bracketed or sitting in a header cell of its own. Without that, 'Peak
# Production of 109,100 tonnes LCE in Year 6' reads as a six-year mine.
_RE_YEARS_REV = re.compile(r"""(?ix)
    (?: \( \s* (?P<unit>years?|yrs?|months?|mths?) \s* \)
      | (?<=[|\t]) \s* (?P<unit2>years?|yrs?|months?|mths?) \s* (?=[|\t\s])
      | (?<!\d)(?<!\d\ ) \b (?P<unit3>yrs?|mths?) \b \s* (?=\d) )
    [\s|]{0,14} (?P<num>\d{1,3}(?:\.\d+)?)\b""")


def years(text):
    """Payback and mine life, normalised to years. Desert Gold states payback in months in one
    release and years in another, for the same project."""
    m = _RE_YEARS.search(text or "") or _RE_YEARS_REV.search(text or "")
    if not m:
        return None
    v = float(m.group("num"))
    g = m.groupdict()
    unit = g.get("unit") or g.get("unit2") or g.get("unit3") or "years"
    return round(v / 12.0, 2) if unit.lower().startswith(("month", "mth")) else v


# ---------------------------------------------------------------- which basis a figure is on
_RE_AFTER = re.compile(r"(?i)\b(after[\s-]{0,2}tax|post[\s-]{0,2}tax)\b")   # TRX writes 'pre -tax'
_RE_PRE = re.compile(r"(?i)\bpre[\s-]{0,2}tax\b")
_RE_NOMINAL = re.compile(r"(?i)\bnominal\b")
_RE_REAL = re.compile(r"(?i)\breal\b(?!\s*estate)")


def tax_basis(text, default=None):
    """after / pre / None. Every release in the set states both, and they differ enormously --
    ESGold's Montauban is C$24.27M after tax against C$44.53M before, 1.8x apart. Publishing the
    pre-tax figure as the headline number is this reader's equivalent of folding inferred
    resources into reserves."""
    a, p = _RE_AFTER.search(text or ""), _RE_PRE.search(text or "")
    if a and p:
        return "after" if a.start() < p.start() else "pre"
    if a:
        return "after"
    if p:
        return "pre"
    return default


def value_basis(text):
    """nominal / real. Tantalex states its pre-tax NPV both ways -- $764M nominal, $638M real --
    and Euro Manganese says 'a real discount rate of 8%'. Real is what a release means when it
    does not say (Justin, 2026-09-20)."""
    if _RE_NOMINAL.search(text or ""):
        return "nominal"
    return "real"


# ---------------------------------------------------------------- the discount rate on an NPV
_RE_DISCOUNT = re.compile(r"""(?ix)
    (?: NPV \s* \(? (?P<a>\d{1,2}(?:\.\d+)?) \s*%? \)?          # NPV5  NPV(8%)  NPV8%
      | NPV \s* (?:@|at) \s* (?P<b>\d{1,2}(?:\.\d+)?) \s*%      # NPV @ 7%
      | (?P<c>\d{1,2}(?:\.\d+)?) \s*% \s* discount              # 8% discount
      | discount \s+ rate \D{0,12} (?P<d>\d{1,2}(?:\.\d+)?) \s*% # discount rate of 8%
      | net \s+ present \s+ value \D{0,18} (?P<e>\d{1,2}(?:\.\d+)?) \s*% )""")


def discount_of(text):
    """An NPV without its rate is not comparable to anything. The rate is usually welded to the
    label -- NPV5, NPV10%, NPV @ 7%, 'using an 8% discount' -- and West Red Lake states it only in
    prose, never in the table its NPV sits in."""
    # Buffalo Potash footnotes its label -- 'After-tax NPV (1) (8) of US$1.1B' -- and the (1) is not
    # a one per cent rate. No study discounts below three.
    for m in _RE_DISCOUNT.finditer(text or ""):
        for g in ("a", "b", "c", "d", "e"):
            if m.group(g):
                v = float(m.group(g))
                if 3 <= v <= 25:
                    return v
                break
    return None


# ---------------------------------------------------------------- what kind of study
# 1.0.2: "feasibility study" inside "Pre-feasibility Study" is not a second, feasibility-level study. It used to
# be found four characters after the PFS hit, so the "nearest kind" rule called MNO.TO's Cabacal PFS an FS in 26
# restatements (and SURG, TAU, HCH the same way). "Pre -Feasibility" (a stray space) is a PFS too.
_RE_FS = re.compile(r"(?i)(?<![\w-])(?:(?:definitive|bankable|final)\s+)?feasibility\s+study\b|\b[DB]?FS\b|\bbankable\s+(?:project\s+)?study\b")   # 1.0.10: Rock Tech's 'Bankable Project Study' 
_RE_PFS = re.compile(r"(?i)pre\s?-?\s?feasibility|\bPFS\b|preliminary\s+feasibility")
_RE_PEA = re.compile(r"(?i)preliminary\s+economic\s+(?:assessment|study|analysis)|\bPEA\b|economic\s+assessment|\bscoping[\s-]+(?:level\s+)?study\b")   # 1.0.10: a scoping study is a PEA (FPX)


# 'to initiate a Pre-Feasibility Study', 'engaged Technica to complete a PFS' -- a study the
# company says it WILL do. Magna Mining's headline announces one of those and its figures are
# from 'the Preliminary Economic Assessment that was completed in 2024'.
_RE_INTENT = re.compile(r"""(?ix)\b(?:to|will|shall|intends?\s+to|plans?\s+to|expects?\s+to|
      initiat\w+|commenc\w+|engag\w+|begin\w*|undertak\w+|award\w+|launch\w+)\b
    [^.\n]{0,40}$""")


def _kind_hits(text, every=False):
    """Every study kind the text names, in order, minus the ones it only intends to do. With every=True, each
    mention (1.0.2); otherwise the first mention of each kind, as before."""
    out = []
    # 1.0.2: an FS found inside a PFS ('Pre - Feasibility Study', however it is spaced) is that PFS
    pfs_spans = [m.span() for m in _RE_PFS.finditer(text)]
    for rx, kind in ((_RE_PFS, "PFS"), (_RE_FS, "FS"), (_RE_PEA, "PEA")):
        for m in rx.finditer(text):
            if kind == "FS" and any(a <= m.start() < b + 3 for a, b in pfs_spans):
                continue
            lead = text[max(0, m.start() - 60):m.start()]
            if (_RE_INTENT.search(lead) and not _RE_BUILDS_ON.search(lead)) or _RE_INTENT_AFTER.match(text, m.end()):
                continue
            out.append((m.start(), kind))
            if not every:
                break
    return sorted(out)


# 1.0.2: a study named as what comes next -- 'build towards a Feasibility Study next year', 'Feasibility Study
# is underway' -- is not the study the figures come from.
_RE_INTENT_AFTER = re.compile(r"(?i)[^.\n]{0,25}?\b(?:next\s+year|is\s+(?:now\s+)?(?:underway|under\s+way|ongoing|in\s+progress"
                              r"|expected|planned|scheduled|targeted)|(?:expected|planned|scheduled|targeted)\s+(?:for|in|to)"
                              r"|work\s*streams?|launch)\b")
# 'The FS will build on the Prefeasibility Study': the study built on is a finished one (TAU.V)
_RE_BUILDS_ON = re.compile(r"(?i)\b(?:build\w*\s+(?:on|upon)|based\s+on|following|supersed\w*|replac\w*)\b[^.\n]{0,30}$")
_RE_TOWARD = re.compile(r"(?i)\b(?:towards?|advancing\s+(?:to|into|the)|progress\w*\s+(?:to|towards?)|working\s+on"
                        r"|next\s+steps?|(?:to|will)\s+advance)\b[^.\n]{0,40}$")


# 1.0.2: a figure broken over lines ('NPV\n8\n% US $9.17 Billion', NILI.V; 'NPV\n8\n after-tax of US$1.0 billion', GRD.V)
# is still the figure; only a full stop ends the search.
_RE_FIG_ANCHOR = re.compile(r"(?ix)(?:NPV|net\s+present\s+value|\bIRR\b)[^.]{0,60}?"
                            r"(?:US|C|CA|A)?\s?\$\s?\d|\d{1,3}(?:\.\d+)?\s?%\s?(?:IRR|return)")


def study_type(headline, body=""):
    """The kind of study the figures belong to.

    The headline decides when it names one, because a body often recites the whole ladder --
    'advancing toward a Pre-Feasibility Study' inside a PEA release. But a headline that says
    the company is about to START a study is not naming the study its figures come from, so
    those mentions are dropped on both passes and the next kind named stands."""
    # Buffalo Potash's headline is about a drill hole and Freeman's is about a conference; both
    # recite a PEA, and both bodies use the words 'feasibility study' elsewhere. The kind named
    # nearest the figures is the kind the figures belong to.
    # unwrapped, because these bodies wrap mid-sentence and the anchor must not stop at a line
    # break: Freeman writes 'an after-tax net present value (5%) of' and then 'US$329 million'.
    flat_body = unwrap(body or "")
    anchor = _RE_FIG_ANCHOR.search(flat_body)
    if anchor:
        lo = max(0, anchor.start() - 700)
        win = flat_body[lo:anchor.start() + 300]
        a0 = anchor.start() - lo
        hits = _kind_hits(win, every=True)
        near = [(p, k) for p, k in hits if not _RE_TOWARD.search(win[max(0, p - 60):p])] or hits
        if near:
            head = [k for _, k in _kind_hits(headline or "")]
            kinds = {k for _, k in near}
            # 1.0.2: the kind named in the figures' own sentence, before the figures, is the study they come from
            # ('Cabacal's Pre-Feasibility Study ... delivered ... NPV5 of USD 984 million') -- even when the headline
            # is about the next study ('Appoints Ausenco as Lead Engineer for the Definitive Feasibility Study').
            # a heading line ('LSLi PEA Project Highlights:') belongs to the figures under it, so a single line
            # break does not end the sentence; a full stop, a bullet or a blank line does
            sent0 = max(win.rfind(". ", 0, a0), win.rfind("\n\n", 0, a0), win.rfind(chr(0x2022), 0, a0), a0 - 250) + 1
            own = [h for h in near if sent0 <= h[0] < a0]
            if own:
                return own[-1][1]
            # The headline is only the answer when the figures agree with it. Freeman's headline
            # is about drilling 'FOR Q1 2026 FEASIBILITY STUDY' -- a study that has not happened
            # -- while the figures beside it are the 2023 PEA, and it is the PEA that goes on
            # the page. Otherwise take the kind nearest the figures; 1.0.2: one named before them
            # over one named after (Surge's 'The Company is currently advancing feasibility-level work').
            if head and head[0] in kinds:
                return head[0]
            before = [h for h in near if h[0] < a0]
            if before:
                return before[-1][1]
            return min(near, key=lambda h: abs(h[0] - a0))[1]
    for text in (headline or "", (headline or "") + " " + (body or "")[:2500]):
        hits = _kind_hits(text)
        if hits:
            # a fixed PFS-then-FS-then-PEA order reads a PEA release that mentions 'advancing
            # toward a Pre-Feasibility Study' as a PFS. Whichever kind the text names first is
            # the one it is about.
            return hits[0][1]
    return None



def _fig_pattern(v):
    """A figure as a release may write it: '$2.7 billion', '2,700 million', '$1.1B', '984 M'."""
    alts = []
    for div, unit in ((1e9, r"(?:billion|bn|B)\b"), (1e6, r"(?:million|mm|M)\b")):
        if v < div:
            continue
        t = "%.10g" % (v / div)
        forms = {t}
        if "." not in t:
            forms.add("{:,}".format(int(float(t))))
        for f in forms:
            alts.append(r"(?<![\d.,])" + re.escape(f) + r"\s?" + unit)
    return re.compile("|".join(alts)) if alts else None


_RE_NPV_WORD = re.compile(r"(?i)NPV|net\s+present\s+value")


def figure_kind(flat, value):
    """1.0.3: the study kind named in the sentence of the NPV figure `value`, before the figure, or None.
    Ivanhoe's Platreef update: 'the NPV8% of the Phase 2 feasibility study at current spot prices is ... $2.7
    billion. In addition, the sensitivity tables in the Preliminary Economic Assessment (PEA) ... to over $5.0
    billion' -- two studies, one release."""
    if not value:
        return None
    rx = _fig_pattern(value)
    if rx is None:
        return None
    for m in rx.finditer(flat):
        lead = flat[max(0, m.start() - 250):m.start()]
        if not _RE_NPV_WORD.search(lead[-200:]):
            continue
        s0 = max(lead.rfind(". "), lead.rfind("\n\n"), lead.rfind(chr(0x2022))) + 1
        seg = lead[s0:]
        hits = [(p, k) for p, k in _kind_hits(seg, every=True) if not _RE_TOWARD.search(seg[max(0, p - 60):p])]
        return hits[-1][1] if hits else None
    return None

# ---------------------------------------------------------------- announcing, or just recapping
# A back-reference only settles the question when it points at THE RESULTS BEING SHOWN. Euro
# Manganese says its PEA "is a result of the Optimization Program previously announced" -- the
# programme is old, the PEA is new. Gunnison says its 2026 PEA "supersedes the previous PEA
# released in December 2024" -- naming the old one is how it tells you this one is new. A blanket
# search for "previously announced" calls both of those background, and both are announcements.
_RE_BACK_STRONG = re.compile(r"""(?ix)
      no \s+ material \s+ (?:difference|change)
    | results? [^.]{0,60} disclosed \s+ in [^.]{0,40} (?:news|press) \s+ release
    | disclosed \s+ in \s+ (?:its|the|a) [^.]{0,30} (?:news|press) \s+ release \s+ dated
    | results? \s+ previously \s+ (?:announced|disclosed|reported)
    | supports \s+ the [^.]{0,40} results
    | \( \s* see [^)]{0,70} (?:news|press) \s+ release [^)]{0,30} \)
    | see \s+ [A-Z][^.]{0,40}? (?:news|press) \s+ release \s+ dated
    """)
# weaker forms: true of a recap, but also true of an announcement that cites its own history
_RE_BACK_WEAK = re.compile(r"(?ix)previously\s+announced|20\d\d\s+(?:PEA|PFS|FS|DFS|BFS)|"
                           r"(?:news|press)\s+release\s+dated")
_RE_SUPERSEDES = re.compile(r"(?i)supersede|replaces?\s+the\s+(?:previous|prior)")

# A headline that announces RESULTS. 'Files', 'launches', 'initiates' deliberately absent: those
# are the filing of a report or the start of a study, and both carry old numbers or none.
_RE_HEAD_ANNOUNCES = re.compile(r"""(?ix)
    \b(announc\w+|deliver\w+|report\w+|present\w+|releas\w+|unveil\w+|publish\w+|
       defin\w+|demonstrat\w+|highlight\w+|yield\w+|return\w+)\b
    [^\n]{0,90}?          # NOT [^.]: '61.2% IRR' has a decimal point in it, and Meridian's
                          # headline -- 'Delivers USD 984 million NPV5 & 61.2% IRR' -- was read
                          # as a recap because the search stopped at the point in 61.2
    \b(PEA|PFS|DFS|BFS|preliminary\s+economic|pre[\s-]?feasibility|feasibility|economic\s+assessment|
       NPV|IRR|economics|study\s+results)\b""")

# A headline whose subject is NOT the study, however many of its figures the body recites.
_RE_HEAD_OTHER = re.compile(r"""(?ix)
    \b(files?|filing|launch\w*|initiat\w+|commenc\w+|select\w+|engag\w+|contract\w+|appoint\w+|
       award\w+|webinar|conference|attend\w*|invit\w+|grant\w+|options?\b|placement|offering|
       meeting|drill\w*|interse\w+|assay|permit\w*|earn[\s-]?in|acquisit\w+|acquir\w+|
       arrangement|update\s+on|progress|expiry|congratulat\w+)\b""")


# 'Files NI 43-101 Technical Report', 'Announces Filing of PEA Technical Report', 'with Filing
# of Quartz Mountain PEA Technical Report'
_RE_HEAD_FILING = re.compile(r"""(?ix)\b(?:files?|filed|filing)\b[^\n]{0,60}?
    \b(?:NI\s*43-?101|technical\s+report|PEA|PFS|DFS|BFS|
       preliminary\s+economic\s+assessment|pre[\s-]?feasibility\s+study|feasibility\s+study)\b""")

_RE_STUDY_HEAD = re.compile(r"(?ix)\b(PEA|PFS|DFS|BFS|preliminary\s+economic\s+assessment|"
                            r"pre[\s-]?feasibility\s+study|feasibility\s+study)\b")


def release_announces(headline, body=""):
    """Is this release announcing a study, or reciting one it announced before?

    Most releases that state economics are reciting. The question is settled in this order:

      1. A STRONG back-reference -- 'no material differences', 'disclosed in its news release
         dated' -- points at the results being shown, and settles it.
      1a. A NI 43-101 technical report filing is the authoritative statement of a study, so it
         is announced and its figures are the ones to publish (Justin, 2026-09-20). It says so
         even while saying there are "no material differences" from the release that broke the
         study -- that sentence is a filing describing itself, not a company recapping old news.
      2. Otherwise the headline decides, and whichever kind of phrase comes FIRST in it wins.
         Euro Manganese's headline announces a PEA and ends with 'New Commercial Plant
         Optionality'; a blanket veto on option words called that a recap of its own study.
      3. A headline that names a study kind and nothing else -- 'A Positive Gold-Antimony PEA
         Just Landed' -- is announcing it. Nothing in the release points anywhere else.
      4. A body that says it supersedes an earlier study is announcing this one.
    """
    head = headline or ""
    text = readable(body)[:6000]
    if _RE_HEAD_FILING.search(head):
        return True
    if _RE_BACK_STRONG.search(text):
        return False
    other = _RE_HEAD_OTHER.search(head)
    ann = _RE_HEAD_ANNOUNCES.search(head)
    if other and ann:
        # 'Announces Filing of Preliminary Economic Assessment Technical Report' -- what is being
        # announced is the filing. When the other word follows the verb immediately it is the
        # object of it; when it is off at the end of the headline it is a separate item, which
        # is why Euro Manganese's closing 'New Commercial Plant Optionality' does not count.
        if other.start() - ann.end() <= 12:
            return False
        return ann.start() < other.start()
    if other:
        return False
    if ann:
        return True
    if _RE_STUDY_HEAD.search(head):
        return True
    if _RE_SUPERSEDES.search(text):
        return True
    return False


# ---------------------------------------------------------------- whose study is it
# Every EXCHANGE: SYMBOL pair, wherever it sits. The first version only read a pair standing alone
# in its own brackets, so '(TSX-V: XYZ; OTCQB: XYZF)' named nobody -- and a company whose own
# symbol goes unread can have its study credited to a partner named elsewhere in the release. The
# exchange is matched in any case; the symbol only in capitals, so ordinary words never qualify.
_RE_TICKER = re.compile(r"""(?x)
    (?i:\b(?:TSX[\s.\-]?V(?:enture)?(?:\s+Exchange)?|TSXV|TSX|CSE|NEO|CBOE(?:\s+Canada)?|
            NYSE(?:\s+American|\s+MKT)?|NASDAQ|OTCQ[XB]|OTC(?:\s+Pink)?|FSE|FRA|ASX|LSE|AIM|JSE))
    \s*[:\-]\s*
    (?P<sym>[A-Z][A-Z0-9]{0,5}(?:\.[A-Z]{1,2})?)\b""")


def named_tickers(headline, body, limit=6):
    """Every exchange symbol the release names, in the order it names them.

    The reader cannot decide attribution on its own: extract() is a pure function of the text and
    is never told which company issued the release. So it records what it saw and the publisher,
    which has the event row, settles it with owner_from()."""
    text = (headline or "") + " " + readable(body)[:4000]
    out = []
    for m in _RE_TICKER.finditer(text):
        sym = m.group("sym").split(".")[0].upper()
        if sym not in out:
            out.append(sym)
        if len(out) >= limit:
            break
    return out


def owner_from(named, own_ticker):
    """The ticker a study belongs to, when the release credits one that is not the issuer's own.

    PMC.CN announces a webinar and quotes SURGE BATTERY METALS' Nevada North PEA -- US$9.21
    billion, 22.8% IRR. Published under PMC that is a nine-billion-dollar project credited to the
    wrong company. Vizsla Royalties congratulating Vizsla Silver on a feasibility study is the
    same shape. Returns None when the study is the issuer's own or cannot be told apart."""
    own = (own_ticker or "").split(".")[0].upper()
    syms = [s.split(".")[0].upper() for s in (named or [])]
    if not syms or (own and own in syms):
        return None
    return syms[0]


_OWNER_STUDY = (r"(?:PEA|PFS|DFS|BFS|Preliminary\s+Economic\s+Assessment|Pre[\s-]?Feasibility\s+Study|"
                r"Feasibility\s+Study|Economic\s+Assessment)")
_OWNER_NAME = r"(?P<name>[A-Z][\w&.'\u2019-]*(?:\s+(?:[A-Z][\w&.'\u2019-]*|&|and|of)){0,5})"
# 'Surge Battery Metals Presents Their Preliminary Economic Assessment' -- the headline's subject
# presenting a study that is THEIR/ITS own.
_RE_OWNER_HEAD = re.compile(r"^\s*" + _OWNER_NAME + r"\s+(?:Presents|Releases|Publishes|Unveils|Delivers|"
                            r"Reports|Announces)\s+(?:Their|Its)\s+(?:[\w-]+\s+){0,3}?" + _OWNER_STUDY)
# 'Analyst Note: Positive PEA Delivered -- Rua Gold's Auld Creek' and 'Rua Gold's Positive PEA Lands in a
# Fast-Track Jurisdiction', both published under other issuers' tickers: a headline that names a company
# and gives it the study with a possessive. Settled against the issuer by name, so Rua's own copy stays.
_RE_OWNER_POSS = re.compile(r"(?:^|[:—–-]\s*|\b(?:Delivered|Landed|Lands|Unveiled|Released)\s*[—–-]*\s*)"
                            + _OWNER_NAME + r"[’']s\s+(?:(?:Positive|Updated|New|Maiden|Robust|Strong)\s+)?"
                            + _OWNER_STUDY + r"\b")
_RE_HEAD_VERB = re.compile(r"\b(?:Publishes|Presents|Files|Announces|Delivers|Reports|Releases|Completes|Unveils|Provides)\b")
# 'Surge Battery Metals (Surge) released a Preliminary Economic Assessment (PEA) on their ...'
_RE_OWNER_BODY = re.compile(_OWNER_NAME + r"\s*(?:\((?:the\s+)?[\"\u201c]?(?P<alias>[A-Z][\w-]+)[\"\u201d]?\)\s*)?"
                            # a commentary piece writes the tickers and the defined name first: 'Rua Gold Inc.
                            # (TSX: RUA) (NZX: RGI) ("RUA GOLD" or the "Company") has released the results of a
                            # positive Preliminary Economic Assessment'
                            r"(?:\([^()\n]{1,60}\)\s*){0,5}"
                            r"(?:has\s+|have\s+)?(?:released|published|completed|delivered|announced|presented)\s+"
                            r"(?:the\s+(?:positive\s+)?results\s+of\s+)?"
                            r"(?:a|an|its|their)\s+(?:[\w-]+\s+){0,2}?" + _OWNER_STUDY)
# a paid piece says whose it is in its first line: 'Issued on behalf of Rua Gold Inc.'
_RE_OWNER_BEHALF = re.compile(r"(?i:^\W{0,6}(?:issued|published|disseminated|paid\s+for)\s+on\s+behalf\s+of)\s+" + _OWNER_NAME)


def study_owner_name(headline, body):
    """The company the release says the study belongs to, when it says so outright.

    Peloton's release about Surge's PEA is headlined 'Surge Battery Metals Presents Their
    Preliminary Economic Assessment' and opens 'Surge Battery Metals (Surge) released a Preliminary
    Economic Assessment (PEA) on their Nevada North Lithium Project'. It names no exchange symbol at
    all, so symbols cannot settle this; names can. Returns 'Surge Battery Metals (Surge)'-style text
    (name plus alias), or None when the release does not credit the study to a named company --
    which is the usual case, and means the issuer's own.

    Only these two explicit forms count. 'the Madsen PFS' names a project, not a company, and
    reading it as an owner would take West Red Lake's own study off the page."""
    m = _RE_OWNER_HEAD.search(headline or "")
    if m and _one_name(m.group("name")):
        return m.group("name").strip()
    for m in _RE_OWNER_POSS.finditer(headline or ""):
        name = m.group("name").strip()
        if _one_name(name) and _name_tokens(name) and not _RE_HEAD_VERB.search(name):
            return name
    m = _RE_OWNER_BEHALF.search(readable(body)[:300])
    if m:
        name = m.group("name").split("\n")[0].strip()
        suf = re.match(r".*?\b(?:Inc|Corp|Ltd|Limited|Corporation|plc|LLC)\b\.?", name)
        name = suf.group(0) if suf else name          # 'Greenland Mines Ltd. Wheaton ...' runs on into the text
        if _name_tokens(name):
            return name
    for m in _RE_OWNER_BODY.finditer(readable(body)[:2500]):
        # A name is one run of words on one line. Omai Gold's standing paragraph reads '... the
        # Eastern Flats Mining\nPermits. The Company has completed a PEA', and read across the
        # line break and the full stop that became an owner called 'Eastern Flats Mining Permits.
        # The Company' -- and Omai's own study was left off the page as somebody else's.
        if not _one_name(m.group("name")):
            continue
        name = m.group("name").strip()
        # '("RUA GOLD" or the "Company") has released ...' names nobody: read on for the real name
        if not _name_tokens(name):
            continue
        return name + (" (%s)" % m.group("alias") if m.group("alias") else "")
    return None


def _one_name(name):
    return not re.search(r"\n|[.;:]\s", name or "")


# words that say what kind of company it is, not which one
_GENERIC_CO = set("""inc incorporated corp corporation ltd limited llc plc co company the and of
    metals metal mining mines minerals mineral resources resource gold golds silver copper lithium battery
    energy exploration explorations ventures venture capital holdings holding group nickel uranium zinc
    graphite royalty royalties critical rare earth earths precious base international global north south
    east west american america canada canadian mines mining developments development technologies
    presents releases publishes unveils delivers reports announces their its""".split())


def _name_tokens(name):
    return {t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if t not in _GENERIC_CO and len(t) > 1}


def same_company(a, b):
    """True unless both names are known and share no distinguishing word. 'Radisson' and 'Radisson
    Mining Resources' are one company; 'Surge Battery Metals (Surge)' and 'Peloton Minerals' are two.
    Unknown means the same: this only ever removes a row when the evidence is explicit."""
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return True
    return any(x == y or (min(len(x), len(y)) >= 4 and (x.startswith(y) or y.startswith(x)))
               for x in ta for y in tb)


def study_owner(headline, body, own_ticker):
    """named_tickers() and owner_from() in one call, for tests and for callers that have both."""
    return owner_from(named_tickers(headline, body), own_ticker)


# ---------------------------------------------------------------- which scenario a figure belongs to
_RE_NPV_AT = re.compile(r"(?i)(?:NPV|net\s+present\s+value)")
_RE_IRR_AT = re.compile(r"(?i)\bIRR\b|internal\s+rate\s+of\s+return")
_RE_PAY_AT = re.compile(r"(?i)\bpay[\s-]?back\b")
_RE_PAY_OF_CAPITAL = re.compile(r"(?ix)^\s*(?:period\s+)?of\s+(?:the\s+)?"
                                r"(?:initial|pre[\s-]?production|upfront)\s+cap")

# what a company calls a case, in the order it prefers them
# A case word has to be used AS a case. 'High-grade', 'base metals', 'low capex' and 'scandium oxide
# upside' each put a phantom scenario on the page before this: Gunnison's 'high' row, ESGold's 'base'
# row and Doubleview's 'upside' row were all ordinary words. Spot and consensus stand alone ('leveraged
# to spot at US$4,700/oz', 'at consensus prices'); the rest need case, price or scenario after them.
_RE_CASE = re.compile(r"""(?ix)\b(
      base[\s-]+(?:case|price|prices|scenario)
    | spot(?:[\s-]+(?:case|price|prices|scenario))?
    | (?:low|high|medium|upside|downside)[\s-]+(?:case|price|prices|scenario)
    | consensus)\b""")
# a price deck is a scenario too, and is how most releases name theirs
_RE_DECK = re.compile(r"""(?ix)
    (?:US|C|CA|A)?\$\s*[\d,]+(?:\.\d+)?\s*(?:/|\s+per\s+)\s*
    (?:oz|ounce|lb|pound|t|tonne|mtu)\b
    (?:\s*(?:Au|Ag|Cu|Li|Ni|Zn|Pb|Mo|Cg|LCE|U3O8))?""")   # 'US$1,524/t Cg' names the metal too
# a base case says which price it is on, and it usually says so somewhere other than the sentence
# stating the NPV: Surge writes 'the base case uses a lithium price of US$24,000/t LCE' a
# paragraph below its economics table. Without it the row is called 'base case' and says nothing.
_RE_DECK_CUE = re.compile(r"(?ix)\b(base\s+case|assum\w+|price\s+(?:of|deck|assumption)|"
                          r"long[\s-]term\s+price|at\s+a\s+\w+\s+price)\b")
# Doubleview tags its flowsheets inline: 'C$4.96 billion (A1), C$6.73 billion (A2), or C$7.27 (B)'
_RE_OPTION = re.compile(r"\(\s*([A-Z]\d?)\s*\)")
# a sweep row carries no name, only a swing -- '-20% | $2,000 | 6 | 17%'. Never a scenario.
_RE_SWING = re.compile(r"(?<![\d.])[-+\u00b1]\s?\d{1,2}\s?%")   # Doubleview writes '\u00b140% metal price'

_RE_SEG = re.compile(r"(?:\|\s*){1,}|[.;]\s+|\n+|\u2022|\uf0b7")


# A flattened table writes one figure across several cells. Three is the common shape --
#   NPV (After-Tax) | $ million | 4,992
# but Surge writes four, putting the discount rate in a cell of its own and the tax basis in a
# bare cell above the whole block:
#   Pre-Tax | Net Present Value (NPV) | (8%) | $ M | 11,395
# so the reflow is label + one to three qualifier cells + a value, not a fixed window.
# A rate in brackets is a qualifier on the row above it, not the row's value: '(8%)' says what
# discount the 11,395 beside it is on. A bare '25.5%' IS the value. Surge drops the opening
# bracket on one of its two rows -- '8%)' -- so one bracket on either side is enough.
_RE_PCT_CELL = re.compile(r"^\s*(?:\(\s*\d{1,2}(?:\.\d+)?\s*%\s*\)?"
                          r"|\d{1,2}(?:\.\d+)?\s*%\s*\))\s*$")
_RE_MAG_CELL = re.compile(r"""(?ix)^\s*\(?\s*
    (?: (?P<cur>US\$|C\$|CA\$|A\$|\$) \s*
        (?P<mag1>millions?|billions?|thousands?|M|B|bn)? |
        (?P<mag2>millions?|billions?|thousands?|M|B|bn|%|years?|yrs?|months?|mths?|
           t|tpd|tpa|Mtpa|oz|koz|Moz|klbs?|lbs?|\$/t|/t|\$/oz|\$/lb|/lb) )
    (?:\s*(?:LCE|Au|Ag|Cu|Li|Ni|Zn|Pb|Mo|U3O8|eq))?     # '$/t LCE' is one header cell
    \s*\)?\s*$""")
_RE_VAL_CELL = re.compile(r"(?i)^\s*\(?\s*(?:US\$|C\$|CA\$|A\$|\$)?\s*"
                          r"[\d][\d,]*(?:\.\d+)?\s*%?\s*\)?\s*$")
_RE_TAX_CELL = re.compile(r"(?ix)^\s*\(?\s*(pre[\s-]?tax|post[\s-]?tax|after[\s-]?tax)\s*\)?\s*$")
_RE_HAS_ALPHA = re.compile(r"[A-Za-z]{3}")
_MAG_WORD = {"m": "million", "b": "billion", "bn": "billion", "millions": "million", "billions": "billion",
             "thousands": "thousand", "million": "million", "billion": "billion", "thousand": "thousand"}


def _reflow(label, quals, val):
    """One table row written back as a sentence a parser can read.

    'Net Present Value (NPV)', '(8%)', '$ M', '11,395' -> 'Net Present Value (NPV) (8%) $11,395
    million'. The magnitude has to move from its header cell onto the number, because a bare
    number is not money and would be thrown away."""
    num = val.strip().strip("()").strip()
    lead = re.match(r"(?i)^(US\$|C\$|CA\$|A\$|\$)\s*", num)
    lead_cur = lead.group(1) if lead else ""
    if lead:
        num = num[lead.end():]
    pct = [q for q in quals if _RE_PCT_CELL.match(q)]
    cur, mag = "", ""
    for q in quals:
        m = _RE_MAG_CELL.match(q)
        if m and not _RE_PCT_CELL.match(q):
            cur = cur or (m.group("cur") or "") or lead_cur
            w = (m.group("mag1") or m.group("mag2") or "").lower()
            mag = mag or _MAG_WORD.get(w, w)
    head = label.strip()
    if pct:
        head += " (" + pct[0].strip().strip("()") + ")"
    if num.endswith("%") or mag == "%":
        return "%s %s" % (head, num if num.endswith("%") else num + "%")
    if mag in ("million", "billion", "thousand"):
        return "%s %s%s %s" % (head, cur or lead_cur or "$", num, mag)
    if cur:
        return "%s %s%s" % (head, cur, num)
    return "%s %s %s" % (head, num, mag) if mag else "%s %s" % (head, num)


_MIN_WRAP = 35
# words no table cell and no sentence ends on
_RE_HANGING = re.compile(r"""(?ix)\b(of|at|and|or|to|for|in|with|on|from|than|by|over|under|
    a|an|the|is|are|was|were|be|per|plus|about|approximately|approx)\s*$""")


def unwrap(text):
    """Put hard-wrapped prose back onto one line before anything is split into clauses.

    Euro Manganese's body wraps mid-sentence: '...underpinned by a pre-tax\nNPV of $740M and
    post-tax NPV of $492M'. Split on the newline, the clause holding the $740M no longer says
    'pre-tax', and a seven-hundred-and-forty-million pre-tax NPV is published as the after-tax
    figure -- the exact error this reader exists to prevent.

    A table's cells are short and must stay apart, so two lines are only joined when BOTH are
    long enough to be prose and the first does not end a sentence."""
    # 'US$1.74\nbillion', 'US$696\n\nmillion': a magnitude a line break took from its figure, which
    # left Frontier's NPV as US$1.74. And US Copper's 'US$1.075 billio n'.
    text = re.sub(r"(?i)(\d)[ \t]*(?:\n[ \t]*)+(billions?|millions?)\b", r"\1 \2", text or "")
    text = re.sub(r"(?i)\b(billi|milli)o\s+n\b", r"\1on", text)
    text = re.sub(r"(\d) ,(\d{3})\b", r"\1,\2", text)          # Westhaven's 'US$2 ,400'

    lines = text.split("\n")
    out = []
    for ln in lines:
        t = ln.rstrip()
        prev = out[-1] if out else ""
        # A line ending in a preposition or a conjunction has not finished its sentence, whatever
        # length the next line is. AbraSilver wraps after 'an after-tax NPV5% of' and puts
        # 'US$3.0 billion' on a line of its own; requiring both lines to be long left the NPV in
        # a clause of its own and the release reading as though it stated no economics at all.
        hanging = bool(_RE_HANGING.search(prev))
        if (out and (hanging or (len(prev.strip()) >= _MIN_WRAP
                                 and len(t.strip()) >= _MIN_WRAP))
                and not re.search(r"[.;:!?\u2022|]\s*$", prev)):
            out[-1] = out[-1].rstrip() + " " + t.lstrip()
        else:
            out.append(t)
    return "\n".join(out)


def segments(text):
    """The release cut into clauses. A figure belongs to the clause it is written in, which is a
    far better guide than a character window: Radisson states its base case and its spot case in
    consecutive sentences, and a window centred on the second still sees the first one's price.

    A flattened table is put back together first, and a bare 'Pre-Tax' cell is carried onto the
    rows beneath it -- in Surge's table that cell is the only thing saying which basis the
    11,395 belongs to, and dropped it files an eleven-billion-dollar pre-tax NPV as after-tax."""
    raw = [s for s in _RE_SEG.split(unwrap(text or "")) if s and s.strip()]
    out, i = [], 0
    tax_ctx, tax_at = "", -99
    while i < len(raw):
        cell = raw[i]
        if _RE_TAX_CELL.match(cell):
            tax_ctx, tax_at = cell.strip().strip("()"), i
            out.append(cell)
            i += 1
            continue
        if _RE_HAS_ALPHA.search(cell) and not _RE_VAL_CELL.match(cell):
            j, quals = i + 1, []
            while j < len(raw) and len(quals) < 3 \
                    and (_RE_PCT_CELL.match(raw[j])
                         or (_RE_MAG_CELL.match(raw[j]) and not _RE_VAL_CELL.match(raw[j]))):
                quals.append(raw[j])
                j += 1
            # A row with a figure per column is a case table and is read as one (column_tables):
            # reflowing it here glued XXIX's base-case NPV to its label and left the spot figure
            # standing alone, so the spot case lost its NPV.
            if quals and j < len(raw) and _RE_VAL_CELL.match(raw[j]) \
                    and not (j + 1 < len(raw) and _RE_VAL_CELL.match(raw[j + 1])):
                seg = _reflow(cell, quals, raw[j])
                if tax_ctx and i - tax_at <= 8 and not _RE_AFTER.search(seg) \
                        and not _RE_PRE.search(seg):
                    seg = tax_ctx + " " + seg
                out.append(seg)
                i = j + 1
                continue
        out.append(cell)
        i += 1
    return out


def _tax_near(seg, start, end, val_start=None):
    """The tax label that governs a value is the one NEAREST it, and it can sit on either side.

    Lomiko writes it before: 'Pre-tax NPV (8%) of CA$797.5 M. After-tax NPV (8%) of CA$617.4 M'
    -- a window around the second figure still contains 'Pre-tax', and taking the FIRST marker
    files both under pre-tax and throws the after-tax figure away.

    Smackover writes it after, inside the label: 'NPV (After-Tax) | $ million | 4,992'. Looking
    only backwards finds nothing there and defaults the figure to after-tax, which is right by
    luck for that row and wrong for the pre-tax row above it."""
    if val_start is not None and val_start > end:
        mid = seg[end:val_start]
        a, p = list(_RE_AFTER.finditer(mid)), list(_RE_PRE.finditer(mid))
        if a and p:
            return "after" if a[-1].start() > p[-1].start() else "pre"
        if a:
            return "after"
        if p:
            return "pre"
    head = seg[max(0, start - 60):start]
    a = list(_RE_AFTER.finditer(head))
    p = list(_RE_PRE.finditer(head))
    if a and p:
        return "after" if a[-1].start() > p[-1].start() else "pre"
    if a:
        return "after"
    if p:
        return "pre"
    return None


_RE_COL_TAX = re.compile(r"(?i)\b(pre|after|post)[\s-]{0,2}tax\b[\s|()]{1,8}\b(pre|after|post)[\s-]{0,2}tax\b")


def _col_tax_header(seg, pos, reach=220):
    """1.0.10: a flattened two-column table - 'Metric Pre-Tax After-Tax Net Present Value (NPV) $464 million $344
    million Internal Rate of Return (IRR) 168% 137%' (Voyageur). The nearest tax word before either figure is the
    header's second column, which filed the pre-tax $464M as after-tax. Returns the columns' order, e.g.
    ['pre', 'after'], when such a header is the last tax wording before the label, else None."""
    head = seg[max(0, pos - reach):pos]
    ms = list(_RE_COL_TAX.finditer(head))
    if not ms:
        return None
    m = ms[-1]
    if _RE_AFTER.search(head[m.end():]) or _RE_PRE.search(head[m.end():]):
        return None
    cols = ["pre" if g.lower() == "pre" else "after" for g in (m.group(1), m.group(2))]
    return cols if cols[0] != cols[1] else None


def _basis_near(seg, pos):
    """Tantalex states the same scenario twice in one sentence -- '$764 million and 87.4% IRR on
    a nominal basis, and a pre-tax NPV10% of approximately $638 million and 82.3% IRR on a real
    basis' -- so reading the clause once files both figures under whichever word came first."""
    if pos is None:
        return value_basis(seg)
    fwd = seg[pos:pos + 70]
    n, r = _RE_NOMINAL.search(fwd), _RE_REAL.search(fwd)
    if n and r:
        return "nominal" if n.start() < r.start() else "real"
    if n:
        return "nominal"
    if r:
        return "real"
    back = seg[max(0, pos - 60):pos]
    return "nominal" if _RE_NOMINAL.search(back) else "real"


def _sig(v):
    """How many significant digits a figure was written with. 'US$2.0 billion' has two; the body
    that states the same number as $1,952 million has four."""
    t = ("%.10g" % abs(v)).replace(".", "").lstrip("0")
    return len(t.rstrip("0")) or 1


def _more_precise(new, old):
    """Gunnison headlines 'US$2.0 Billion' and states US$1,952 million in the body. Both are the
    same figure; only one of them is the figure. Replace only within a rounding distance, so a
    genuinely different number never overwrites the first one seen."""
    if not isinstance(new, (int, float)) or not isinstance(old, (int, float)):
        return False
    if old == 0:
        return False
    return abs(new - old) / abs(old) <= 0.06 and _sig(new) > _sig(old)


_RE_BYPRODUCT_LEAD = re.compile(r"(?i)^\W{0,3}(?:Ag|Cu|Zn|Pb|Mo|Ni|Co|silver|copper|zinc|lead|molybdenum|nickel|cobalt)\s*[:=]")


def _scenario_key(seg):
    """A name for the case this clause is about. A case with a NAME is a row; a row identified
    only by a percentage swing is a sweep (Justin, 2026-09-20)."""
    if _RE_SWING.search(seg) and not _RE_CASE.search(seg):
        return None
    bits = []
    case = _RE_CASE.search(seg)
    deck = deck_in(seg)
    if deck and _RE_BYPRODUCT_LEAD.match(seg):
        deck = None       # 1.0.10: 'Ag: $23/oz) After-tax NPV ...' is the tail of a metal price list (Troilus), not the case
    if case:
        bits.append(" ".join(case.group(1).replace("-", " ").split()).lower())
    if deck:
        bits.append(" ".join(deck.group(0).split()))
    return " ".join(bits) if bits else "base case"


# 'Operating Cost (OPEX): US$5,097 per tonne LCE' has the shape of a price deck and is a cost. Surge's
# base case was being named after its operating cost until this.
_RE_COST_BEFORE = re.compile(r"(?i)\b(?:costs?|opex|capex|aisc|c1|cash(?!\s+flow)|operating|sustaining|"
                             r"all[\s-]in|capital|breakeven|break[\s-]even)\b[^.$]{0,30}$")


# ...and the label can follow the figure: Lafleur writes 'US$1,569/oz AISC ... at a US$2,750/oz gold
# base case', and its base case was being named after its sustaining cost.
_RE_COST_AFTER = re.compile(r"(?i)^[\s(\u201c\"]{0,4}(?:gold\s+|silver\s+)?(?:AISC|all[\s-]in|C1\b|cash\s+costs?|"
                            r"operating\s+costs?|opex|sustaining|site\s+costs?|breakeven|break[\s-]even)")


def deck_in(text):
    """The first price deck in `text` that is not a unit cost."""
    text = text or ""
    for m in _RE_DECK.finditer(text):
        if _RE_COST_BEFORE.search(text[max(0, m.start() - 45):m.start()]):
            continue
        if _RE_COST_AFTER.search(text[m.end():m.end() + 24]):
            continue
        return m
    return None


def base_deck(text):
    """The price the base case is on, stated anywhere in the release."""
    for seg in segments(text or ""):
        if _RE_DECK_CUE.search(seg):
            m = deck_in(seg)
            if m:
                return " ".join(m.group(0).split())
    return None


# 'US$2,550/oz gold' is a price assumption, not a result. Desert Gold's headline reads
# 'USD $24M After-Tax NPV (10%) and 34% IRR at USD $2,500/oz Gold', and a reader that takes the
# first amount after the NPV token publishes the gold price as the net present value.
# NOT r"\s+per\s+": the money match has already eaten the space after the figure, so a rule
# that needs one never fires and 'US$2,400 per ounce gold' is counted as a result.
_RE_UNIT_TAIL = re.compile(r"""(?ix)^\s*(?:/|\bper\b\s*)\s*
    (?:oz|ounce|t|tonne|lb|pound|klb|mtu|unit|LCE|kg|g|dmt|wmt)\d?\b""")


_RE_PRICE_WORD = re.compile(r"(?i)^[^.;|]{0,26}?\bprice\b")


def _is_unit_price(text, end, mult=None):
    """A price assumption, not a result.

    Two shapes. 'US$2,550/oz gold' wears its unit. Canagold writes 'a US$2,500 base case Gold
    Price per ounce', which does not -- but a price is always a bare number, and a result always
    carries its magnitude, so '$425 million ... at a gold price' stays a result while the
    US$2,500 does not."""
    if _RE_UNIT_TAIL.match(text[end:end + 14]):
        return True
    return not mult and bool(_RE_PRICE_WORD.match(text[end:end + 30]))


# The amount belongs to the label BEFORE it as often as to the one after, and headlines are
# written that way almost without exception: 'C$532M After-Tax NPV5%, C$175M Initial Capital'.
# The test is what lies between them -- a tax label and punctuation, and nothing else. In
# 'capital cost of US$290 million and an after-tax NPV of US$24 million' the words 'and an' are
# that difference, and without the test the capital cost is published as the NPV.
_RE_ONLY_TAX = re.compile(r"""(?ix)^[\s,;:\-\u2013\u2014()\[\]]*
    (?:(?:after|post|pre)[\s-]?tax)?[\s,;:\-\u2013\u2014()\[\]]*$""")


def _money_just_before(seg, pos, reach=48):
    """The amount this label is the name of, when the release writes it first."""
    head = seg[max(0, pos - reach):pos]
    base = max(0, pos - reach)
    best = None
    for m in _RE_MONEY.finditer(head):
        cur_raw = (m.group("cur") or "").upper().replace("$", "").strip() or None
        mult = (m.group("mult") or "").lower()
        if not cur_raw and not mult:
            continue
        if _is_unit_price(seg, base + m.end(), mult):
            continue
        if not _RE_ONLY_TAX.match(seg[base + m.end():pos]):
            continue
        try:
            v = numval(m.group("num")) * (_MULT.get(mult, 1.0) if mult else 1.0)
        except ValueError:
            continue
        if (not mult and v < _MIN_BARE) or v > _MAX_RESULT:
            continue
        best = (_signed(m, v), {"C": "CAD", "CA": "CAD", "CAD": "CAD", "CDN": "CAD", "US": "USD", "USD": "USD",
                    "A": "AUD", "AUD": "AUD"}.get(cur_raw), None, base + m.start())
    return best


# 'Cdn$454 million after- tax NPV6%': a tax label with a stray space in it is still only a tax label
_RE_ONLY_TAX = re.compile(_RE_ONLY_TAX.pattern.replace(r"[\s-]?tax", r"[\s-]{0,2}tax"), _RE_ONLY_TAX.flags)


def _only_real_lists(vals, tag_at):
    """A bracketed letter is a flowsheet tag only when the release lists two or more of them.
    Doubleview's '(A1), (A2), or (B)' is a list; Westhaven's '$730 million (M)' is the word million
    said again, and read as a tag it split the pre-tax NPV onto a scenario of its own."""
    tags = {v[tag_at] for v in vals if v[tag_at]}
    if len(tags) >= 2:
        return [v for v in vals if v[tag_at]]
    if not vals:
        return vals
    first = list(vals[0])
    first[tag_at] = None
    return [tuple(first)]


def _tagged_money(after, limit=220):
    """A single label can govern a LIST of values, each named by its own tag: Doubleview writes
    'After-Tax NPV(5%) of C$4.96 billion (A1), C$6.73 billion (A2), or C$7.27 billion (B)'.
    Returns [(value, currency, tag, offset)], one entry when there is no list. The offset is
    where the figure starts, which is what tells the tax lookup whether a label like
    '(After-Tax)' lies between the NPV token and this particular number."""
    out, seg = [], after[:limit]
    for m in _RE_MONEY.finditer(seg):
        cur_raw = (m.group("cur") or "").upper().replace("$", "").strip() or None
        mult = (m.group("mult") or "").lower()
        if not cur_raw and not mult:
            continue
        if not m.group("cur") and (mult == "k" or _qty_after(seg, m.end())):
            continue                      # 1.0.10: 'Tasiast 24k', '1.1 million tonnes' are not money
        try:
            v = numval(m.group("num")) * (_MULT.get(mult, 1.0) if mult else 1.0)
        except ValueError:
            continue
        if _is_unit_price(seg, m.end(), mult):
            continue                      # a price per ounce is an assumption, not a result
        if v > _MAX_RESULT:
            break                         # the label's figure, misprinted; not the one after it
        if not mult and v < _MIN_BARE and m.group("cur") and _RE_SCALE_M.search(seg[max(0, m.start() - 14):m.start()]) \
                and not re.match(r"\s*\(?\s*(?:US|C|CA|A)?\$?\s*\d", seg[m.end():m.end() + 6]):
            v *= 1e6                      # 1.0.10: 'After Tax NPV5% USD MM $409' (one cell, not a row of columns)
        if not mult and v < _MIN_BARE:
            continue
        if out and _RE_CONVERSION.match(seg[out[-1][3]:m.start()]):
            continue                      # 'C$1.36 billion (US$1.01 billion)' is one figure
        tag = _RE_OPTION.search(seg[m.end():m.end() + 14])
        cur = {"C": "CAD", "CA": "CAD", "CAD": "CAD", "CDN": "CAD", "US": "USD", "USD": "USD",
               "A": "AUD", "AUD": "AUD"}.get(cur_raw)
        out.append((_signed(m, v), cur, tag.group(1) if tag else None, m.start()))
        if not out[-1][2] and len(out) == 1:
            break                      # no tag on the first value means there is no list
    return _only_real_lists(out, 2)


def _pct_just_before(seg, pos, reach=30):
    """'87.4% IRR on a nominal basis' -- Tantalex writes every return that way, and reading only
    forward takes the 10 out of the NPV10% in the next clause as the rate of return."""
    head = seg[max(0, pos - reach):pos]
    base = max(0, pos - reach)
    best = None
    for m in _RE_PCT.finditer(head):
        if not _RE_ONLY_TAX.match(seg[base + m.end():pos]):
            continue
        best = (float(m.group("num")), None, None)
    return best


def _tagged_percents(after, limit=220):
    out, seg = [], after[:limit]
    for m in _RE_PCT.finditer(seg):
        tag = _RE_OPTION.search(seg[m.end():m.end() + 14])
        out.append((float(m.group("num")), tag.group(1) if tag else None, m.start()))
        if not out[-1][1] and len(out) == 1:
            break
    return _only_real_lists(out, 1)


# ---------------------------------------------------------------- tables with a case per column
# Canagold and STLLR both state their cases across the top and their metrics down the side:
#
#   Low Case  Base Case  High Case  Spot Case
#   Gold Price (US$/oz)       $2,200 $2,500 $2,800 $3,300
#   After-Tax NPV (5%) (C$M)  $287   $425   $564   $793
#   After-Tax IRR (%)         23.5   30.9   37.5   47.3
#
# Read clause by clause this is one scenario with four NPVs, which is how Canagold's Low and High
# cases went missing and its Base case took the Spot case's payback. The columns have to be read
# as columns.
# Gunnison marks its spot column with a footnote -- 'SPOT2' -- and a plain word boundary does
# not see a case name there at all.
_RE_CASE_NAME = re.compile(r"(?ix)\b(base|spot|low|high|medium|consensus|upside|downside|"
                           r"current)\d?\s*(?:case|price|scenario)?\b")
_RE_NUM_TOK = re.compile(r"""(?ix)(?<![\w.])
    (?P<neg>[-−](?=[\d$]))?(?P<cur>US\$|C\$|CA\$|A\$|\$)?\s?(?P<num>\d[\d,]*(?:\.\d+)?)
    (?:\s?(?P<mag>M|B|million|billion)\b)?\s?(?P<suf>%|x)?(?![\w.])""")
_RE_PAREN_PCT = re.compile(r"\(\s*\d{1,2}(?:\.\d+)?\s*%\s*\)")
_RE_RATIO_ROW = re.compile(r"(?i)(?:NPV|IRR)\s*(?:/|per\b)|ratio|\bper\s+share\b")
_ROW_FIELDS = (
    (re.compile(r"(?i)NPV|net\s+present\s+value"), "npv"),
    (re.compile(r"(?i)\bIRR\b|internal\s+rate\s+of\s+return"), "irr"),
    (re.compile(r"(?i)\bpay[\s-]?back\b"), "payback"),
)


def _case_headers(flat):
    """Every run of two or more case names close enough together to be a header row.

    STLLR writes 'Base Case US$3,200/oz Spot' -- a price deck sits between the two names, which
    is why a run is allowed a gap rather than requiring the names to be adjacent. Minera Alamos
    names its two cases sixty characters apart in prose, and that gap is what keeps a sentence
    from being read as a table."""
    runs, cur, end = [], [], 0
    for m in _RE_CASE_NAME.finditer(flat):
        if cur and m.start() - end > 26:
            if len(cur) >= 2:
                runs.append((cur, end))
            cur = []
        raw = " ".join(m.group(0).split())
        # 'low Capex and low AISC' in a quote is not a header row. A column heading either says
        # what it is -- 'Low Case', 'Spot Price' -- or is capitalised. Canagold's chief executive
        # supplied both those lowercase 'low's, and read as a header they put the Low case's net
        # present value in the Spot column.
        if not re.search(r"(?i)\b(case|price|scenario)\b", raw) and not raw[:1].isupper():
            if cur and len(cur) >= 2:
                runs.append((cur, end))
            cur = []
            continue
        # the footnote digit is not part of the name: Gunnison's 'SPOT2' is the Spot column
        label = re.sub(r"^([a-z]+)\d", r"\1", raw.lower())
        win = flat[max(0, m.start() - 26):m.start()]
        deck = _RE_DECK.search(win)
        if deck and not re.fullmatch(r"[\s|]*", win[deck.end():]):
            deck = None      # the price has to head this column, not end the sentence before it
        cur.append((label + " " + " ".join(deck.group(0).split())).strip() if deck else label)
        end = m.end()
    if len(cur) >= 2:
        runs.append((cur, end))
    return runs


def column_tables(text):
    """Every case table in the release, read as columns.

    Scanned over the whole release rather than clause by clause, because the header row and the
    rows beneath it do not always land in the same clause: STLLR's cases sit in one and its net
    present values in the next."""
    flat = " | ".join(segments(text or ""))
    out = []
    for names, end in _case_headers(flat):
        if len(set(names)) != len(names):
            continue                      # a header does not name the same case twice
        rows = column_table(names, flat[end:end + 1100])
        if rows:
            out.append(rows)
    # A table whose two columns are the TAX BASES of one scenario: Northcliff heads its results
    # 'Pre-Tax | Post-Tax' and writes 'Net Present Value (8%) | $ 12,290 M | $ 6,915 M'. Read as a
    # stranded label, the pre-tax C$12.29 billion became an after-tax figure on a scenario of its own.
    for m in _RE_TAX_HEADER.finditer(flat):
        rows = column_table(["pre", "post"], flat[m.end():m.end() + 900])
        if not rows:
            continue
        pre, post = rows
        one = {"scenario": "base case", "currency": post["currency"] or pre["currency"],
               "discount_pct": post["discount_pct"] or pre["discount_pct"],
               "npv_pre_tax": pre["npv_after_tax"] if pre["npv_pre_tax"] is None else pre["npv_pre_tax"],
               "npv_after_tax": post["npv_after_tax"],
               "irr_pre_tax_pct": pre["irr_after_tax_pct"] if pre["irr_pre_tax_pct"] is None else pre["irr_pre_tax_pct"],
               "irr_after_tax_pct": post["irr_after_tax_pct"],
               "payback_years": post["payback_years"]}
        if one["npv_after_tax"] is not None:
            out.append([one])
    return out


_RE_TAX_HEADER = re.compile(r"(?i)\bpre[\s-]{0,2}tax\s*\|\s*(?:post|after)[\s-]{0,2}tax\s*\|")


def column_table(names, body):
    """One row per column of a case table, or None when this clause is not one.

    A metric row is a label followed by exactly as many figures as there are cases. Anything with
    a different count -- a note, a sentence, a row the table did not finish -- is skipped rather
    than guessed at, because a miscounted row silently files every case's figure under its
    neighbour."""
    n = len(names)
    rows = [{"scenario": nm, "currency": None, "discount_pct": None,
             "npv_pre_tax": None, "npv_after_tax": None, "irr_pre_tax_pct": None,
             "irr_after_tax_pct": None, "payback_years": None} for nm in names]
    # A rate written into a label -- 'After-Tax NPV (5%) (C$M)' -- is part of the label, not the
    # row's first figure. Masking it keeps the offsets, so labels still come from the real text.
    masked = _RE_PAREN_PCT.sub(lambda m: "(" + "r" * (len(m.group(0)) - 2) + ")", body)
    got = False
    pos = label_start = 0
    while pos < len(body):
        toks = list(_RE_NUM_TOK.finditer(masked, pos))
        if not toks:
            break
        # The label runs from the end of the last row to this row's figures, and a stray number
        # inside it does not restart it. STLLR writes 'Pre-tax net present value at 5% discount
        # rate ("NPV5%")(C$M) C$2,118 C$4,961': the 5 and the 5 in NPV5% are each a lone figure
        # where two are needed, and cutting the label at them loses both the word 'Pre-tax' and
        # the words 'net present value', which is the whole of what the row says it is.
        first = toks[0]
        label = body[label_start:first.start()]
        run = [first]
        for a, b in zip(toks, toks[1:]):
            if re.fullmatch(r"[\s|,()]*", masked[a.end():b.start()]):
                run.append(b)
            else:
                break
        if len(run) != n or len(label) > 160:
            pos = run[-1].end()
            continue
        # The metric is named by the row's own label cell, the last worded cell before its figures
        # that is not a unit. The label as a whole can run back over a row that did not parse:
        # XXIX's 'Payback | years | 2.3 | 1.8' is reflowed to 'Payback 2.3 years | 1.8', neither
        # half is a full row, and 'LOM Annual Cash Flow' two cells on was being read as payback --
        # 67.7 and 108.5 years.
        cells = [c for c in label.split("|") if _RE_HAS_ALPHA.search(c) and not _RE_MAG_CELL.match(c)]
        key_cell = cells[-1] if cells else label
        field = next((f for rx, f in _ROW_FIELDS if rx.search(key_cell)), None)
        if field == "npv" and re.search(r"(?i)NPV\s*(?:@|at)?\s*\(?\s*0(?:\.0+)?\s*%|undiscounted", key_cell):
            field = None     # undiscounted: a cash flow, not a net present value
        if field is not None and _RE_RATIO_ROW.search(label):
            field = None     # 'After-Tax NPV/Initial Capex 1.1 1.7 2.3 3.2' is a ratio, not an NPV
        if field is None:
            pos = label_start = run[-1].end()
            continue
        tax = "pre" if _RE_PRE.search(label) else ("after" if _RE_AFTER.search(label) else "after")
        disc = discount_of(label)
        mult = 1e6 if re.search(r"(?i)\(?[A-Z]{0,2}\$?\s?M\)?\b|million", label) else 1.0
        if re.search(r"(?i)\bbillion|\$?\s?B\b", label):
            mult = 1e9
        cur = None
        cm = re.search(r"(?i)(US|CA?)\s?\$", label)
        if cm:
            cur = "USD" if cm.group(1).upper() == "US" else "CAD"
        for r, tk in zip(rows, run):
            try:
                v = numval(tk.group("num"))
            except ValueError:
                continue
            if tk.group("neg") and field == "npv":
                v = -v
            # Northcliff's '$ 12,290 M  $ 6,915 M' carries its magnitude on each figure
            tmag = (tk.group("mag") or "").lower()
            tmult = {"m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}.get(tmag)
            if field == "npv":
                mk = tk.group("cur")
                key = "npv_pre_tax" if tax == "pre" else "npv_after_tax"
                # RPX's summary table writes '$523  $935' with no magnitude anywhere on the row: a
                # figure the row does not scale is left to the prose, which states it in millions
                if r[key] is None and tmult:
                    r[key] = v * tmult
                elif r[key] is None and not (mult == 1.0 and abs(v) < _MIN_BARE):
                    r[key] = v * mult
                r["currency"] = r["currency"] or cur or (
                    {"US$": "USD", "C$": "CAD", "CA$": "CAD", "A$": "AUD"}.get(mk or ""))
                r["discount_pct"] = r["discount_pct"] or disc
            elif field == "irr":
                key = "irr_pre_tax_pct" if tax == "pre" else "irr_after_tax_pct"
                if r[key] is None:
                    r[key] = v
            elif field == "payback":
                y = v / 12.0 if re.search(r"(?i)month", key_cell) else v
                if y <= _MAX_PAYBACK and (r["payback_years"] is None or tax != "pre"):
                    r["payback_years"] = y
        got = True
        pos = label_start = run[-1].end()
    # a case table whose net present values could not be read is left to the prose
    if not any(r["npv_after_tax"] is not None or r["npv_pre_tax"] is not None for r in rows):
        return None
    return rows if got else None


_RE_DECK_NUM = re.compile(r"(?i)(?:US|C|CA|A)?\$\s*(?P<num>[\d,]+(?:\.\d+)?)")
_RE_CASE_WORD = re.compile(r"(?ix)\b(base|spot|low|high|medium|consensus|upside|downside|current)\b")


_RE_OPT_TAG = re.compile(r"\b([A-Z]\d?)\s*$")


def _merge_key(name):
    """What two differently-worded names have to share to be the same scenario.

    Smackover's base case arrives once as '$22,400 per tonne' and once as 'base case $22,400 per
    tonne'; Desert Gold's arrives four ways. A release states one set of figures per price deck,
    so the deck is the identity when there is one, and the case word when there is not."""
    # Doubleview tags three flowsheets A1, A2 and B at one price deck. The tag is the whole
    # difference between them, so it is part of the identity and not a spelling of it.
    t = _RE_OPT_TAG.search(name or "")
    tag = t.group(1) if t else ""
    d = _RE_DECK_NUM.search(name or "")
    if d:
        return ("deck", d.group("num").replace(",", ""), tag)
    c = _RE_CASE_WORD.search(name or "")
    if c:
        return ("case", c.group(1).lower(), tag)
    return ("name", (name or "").strip().lower(), tag)


def _merge_scenarios(order, rows):
    """Collapse rows that are the same scenario, keeping the fullest name and every figure."""
    seen, out = {}, []
    for k in order:
        r = rows[k]
        mk = (_merge_key(r["scenario"]), r["basis"])
        if mk not in seen:
            seen[mk] = r
            out.append(r)
            continue
        first = seen[mk]
        # Two rows that disagree about a figure are two scenarios, whatever they are called --
        # unless the disagreement is only that one release rounded its own number. Gunnison
        # headlines 'US$2.0 Billion' and tabulates 1,952; those are one row, not two.
        if any(first.get(f) is not None and v is not None and first[f] != v
               and not _more_precise(v, first[f]) and not _more_precise(first[f], v)
               for f, v in r.items() if f not in ("scenario", "basis", "_pay_pre")):
            seen[("distinct", id(r), "")] = r
            out.append(r)
            continue
        for f, v in r.items():
            if v is None:
                continue
            if first.get(f) is None or _more_precise(v, first[f]):
                first[f] = v
        if len(r["scenario"] or "") > len(first["scenario"] or ""):
            first["scenario"] = r["scenario"]
    return out


_FIG_FIELDS = ("npv_after_tax", "npv_pre_tax", "irr_after_tax_pct", "irr_pre_tax_pct")
# a clause that carries on the sentence before it rather than starting a new one
_RE_CONTINUES = re.compile(r"""^\s*(?:[\d(\[)\]"'\u201c\u201d\u2019,;:%$]|[a-z]|US\$|C\$|CA\$|A\$)""")


# ...and a clause that opens with a unit is still the sentence before it: Cascadia breaks 'US$3.75'
# from '/lb copper', and the price was read as the NPV
_RE_CONTINUES = re.compile(_RE_CONTINUES.pattern.replace("%$]", "%$/]"))


def _same_scenario(a, b):
    """Two rows agree on at least one figure and disagree on none (a rounding is not a
    disagreement)."""
    shared = 0
    for f in _FIG_FIELDS + ("payback_years", "discount_pct"):
        x, y = a.get(f), b.get(f)
        if x is None or y is None:
            continue
        if x == y or _more_precise(x, y) or _more_precise(y, x):
            shared += 1 if f in _FIG_FIELDS else 0
        else:
            return False
    return shared > 0


def _name_parts(name):
    d = _RE_DECK_NUM.search(name or "")
    c = _RE_CASE_WORD.search(name or "")
    t = _RE_OPT_TAG.search(name or "")
    case = c.group(1).lower() if c else None
    return (d.group("num").replace(",", "") if d else None,
            "base" if case == "consensus" else case,
            t.group(1) if t else None)


def _names_compatible(a, b):
    """Nothing in either name contradicts the other: no two different price decks, no two different
    case words, no two different flowsheet tags. A release's consensus prices are its base case."""
    pa, pb = _name_parts(a), _name_parts(b)
    return all(x is None or y is None or x == y for x, y in zip(pa, pb))


def _richness(name):
    d, c, t = _name_parts(name)
    return (t is not None, d is not None, c is not None, len(name or ""))


def _consolidate(rows):
    """Rows that are one scenario written several ways become one row.

    Surge states its base case in a table (US$9,214 million), in prose ('US$9.21 billion') and in its
    headline; STLLR tabulates C$3,298 million under 'US$3,200/oz Spot' and writes 'Spot Price ...
    C$3.30 billion' in its highlights. Two rows are merged only when their names do not contradict
    each other AND they agree on at least one figure and disagree on none (a rounding is not a
    disagreement). The fuller name survives."""
    rows = list(rows)
    merged = True
    while merged:
        merged = False
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                if a["basis"] != b["basis"] or not _names_compatible(a["scenario"], b["scenario"]):
                    continue
                if not _same_scenario(a, b):
                    continue
                keep, drop = (a, b) if _richness(a["scenario"]) >= _richness(b["scenario"]) else (b, a)
                for f, v in drop.items():
                    if f in ("scenario",) or v is None:
                        continue
                    if keep.get(f) is None or _more_precise(v, keep[f]):
                        keep[f] = v
                rows[i] = keep
                del rows[j]
                merged = True
                break
            if merged:
                break
    return rows


def _fmt_fig(v):
    """A figure as a release writes it, so the clause it came from can be recognised and left to
    the table that already read it."""
    m = v / 1e6 if v >= 1e6 else v
    t = "%.10g" % m
    return "{:,}".format(int(float(t))) if float(t) == int(float(t)) else t


_RE_FROM_TO_YEARS = re.compile(r"(?ix)^[^.;]{0,30}?\bfrom\s+\d{1,3}(?:\.\d+)?\s*(?:years?|yrs?|months?)?\s+"
                               r"(?P<to>to)\s+\d")


# no study pays back after a quarter of a century; a bigger figure is some other row's
_MAX_PAYBACK = 25

# Thor writes 'an anticipated payback of nine months'. Only a number word directly before a year or
# month unit is turned into digits, and the text keeps its length so offsets still line up.
_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
              "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "eighteen": 18, "twenty-four": 24}
# QGold's "a sub-two-year payback" is a boast, not a figure, and is left as words
_RE_NUM_WORD_UNIT = re.compile(r"(?i)(?<!sub-)\b(" + "|".join(sorted(_NUM_WORDS, key=len, reverse=True)) +
                               r")(?=[\s-]+(?:years?|months?)\b)")


def _num_words(text):
    return _RE_NUM_WORD_UNIT.sub(lambda m: str(_NUM_WORDS[m.group(1).lower()]).ljust(len(m.group(1))), text)


# Abasca's table writes 'After-Tax Simple Payback Year 4.7': the unit is the row's label, directly
# after the word payback. Only that adjacent shape is read -- 'Peak Production ... in Year 6' is not
# a payback, and nothing here reaches it.
_RE_PAY_YEAR_CELL = re.compile(r"(?i)^\s*(?:period\s*)?\(?\s*(?:years?|yrs?)\s*\)?\s*[:=]?\s*(?P<num>\d{1,2}(?:\.\d+)?)\b(?!\s*%)")
# a label with nothing after it but punctuation: its value is the next line
_RE_PAY_BARE = re.compile(r"(?i)\bpay[\s-]?back\b(?:\s+period)?(?:\s*\((?:after|post|pre)[\s-]?tax\))?\s*(?:within|of|is|:|=|-)?\s*$")
_RE_YEARS_LEAD = re.compile(r"(?i)^\s*(?:approximately\s+|about\s+|~\s*)?\d{1,3}(?:\.\d+)?[\s-]*(?:years?|yrs?|months?)\b")


def _pay_joined(segs):
    """Each clause, with a bare payback label joined to the figure on the next line. Scottie writes
    'After-tax payback period:' and then '1.7 years (standalone DSO case ...)' on a line of its own;
    Sage writes 'rapid investment payback within' and '5 years' on the next."""
    out = []
    for i, seg in enumerate(segs):
        if i + 1 < len(segs) and _RE_PAY_BARE.search(seg) and _RE_YEARS_LEAD.match(_num_words(segs[i + 1])):
            out.append(seg + " " + segs[i + 1])
        else:
            out.append(seg)
    return out


def _apply_payback(seg, rows, order, key0=""):
    """The payback figures in a clause, filed onto every row the clause is about.

    Two traps, both from releases in the set. Westhaven headlines 'PAYBACK OF INITIAL CAPITAL
    COSTS OF 2.1 YEARS' and states a total project payback of 4.1 years in the body: those are
    two different measures and the page shows the project's. Smackover states both tax bases --
    'Payback Period (Pre-Tax) years 3.0 Payback Period (After-Tax) years 3.1' -- and the
    after-tax one is the one that happened."""
    seg = _num_words(seg)
    for pm in _RE_PAY_AT.finditer(seg):
        after = seg[pm.end():pm.end() + 70]
        if _RE_PAY_OF_CAPITAL.match(after):
            continue
        # 'a 1.5-year payback': the figure written first, adjacent to the word. Bravada does this,
        # and reading forward took the '11.2-year mine life' of the next clause as the payback.
        head = seg[max(0, pm.start() - 24):pm.start()]
        adj = None
        for mm in _RE_YEARS.finditer(head):
            if re.fullmatch(r"[\s-]*", head[mm.end():]):
                adj = mm
        if adj is not None:
            v = float(adj.group("num"))
            y = round(v / 12.0, 2) if adj.group("unit").lower().startswith(("month", "mth")) else v
            if y > _MAX_PAYBACK:
                continue
            pre = _tax_near(seg, pm.start(), pm.end()) == "pre"
            for k in order:
                if key0 and not k[0].startswith(key0):
                    continue
                if rows[k]["payback_years"] is None or (not pre and rows[k].get("_pay_pre")):
                    rows[k]["payback_years"] = y
                    rows[k]["_pay_pre"] = pre
            continue
        # 'payback shortened from 3.3 years to 2.2 years' -- Rua's spot case; the new figure is the
        # one after 'to'
        ft = _RE_FROM_TO_YEARS.match(after)
        if ft:
            after = after[ft.start("to"):]
        ym = _RE_YEARS.search(after) or _RE_YEARS_REV.search(after)
        y = years(after)
        yc = _RE_PAY_YEAR_CELL.match(after)
        if yc and (ym is None or ym.start() > yc.start("num")):
            ym, y = yc, float(yc.group("num"))
        if y is None or ym is None or y > _MAX_PAYBACK:
            continue
        # the basis is written inside the label, after the word: 'Payback Period (After-Tax)'
        pre = _tax_near(seg, pm.start(), pm.end(), pm.end() + ym.start()) == "pre"
        for k in order:
            if key0 and not k[0].startswith(key0):
                continue
            if rows[k]["payback_years"] is None or (not pre and rows[k].get("_pay_pre")):
                rows[k]["payback_years"] = y
                rows[k]["_pay_pre"] = pre


# 'replaces the Company's previous 2023 PEA, which reported a base-case after-tax NPV (5%) of C$6.99
# million' -- ESGold announcing its new PEA and quoting the one it replaces. Only the old study's
# figures sit after a phrase like that; the new ones do not.
_RE_PRIOR_REPORTED = re.compile(r"""(?ix)\b(?:previous|prior|earlier|former|original|superseded|
      (?:19|20)\d\d)\s+(?:[\w-]+\s+){0,3}?(?:PEA|PFS|DFS|BFS|FS|feasibility\s+study|study|assessment)\b
    [^.]{0,40}?\b(?:which|that)\s+(?:reported|had|showed|estimated|outlined|demonstrated|returned|
      generated|delivered|indicated)\b""")


# 'a US$0.25/lb increase in copper price increased the after-tax NPV by approximately US$90 million'
# -- Copper Fox describing a sensitivity. The figure is a change, and the price is a change too.
_RE_NPV_DELTA = re.compile(r"(?i)^\s*(?:\(\s*\d{1,2}\s*%?\s*\)\s*)?by\b")


# 'NPV @0% Discount rate (millions, after tax) $71 M' is Desert Gold's undiscounted cash flow, not a
# net present value of anything, and read as one it became a third base case
_RE_NPV_ZERO = re.compile(r"(?i)^\s*(?:@|at)?\s*\(?\s*0(?:\.0+)?\s*%")


_RE_TAX_LEAD = re.compile(r"(?i)(?:\b(?:and|with|an?|the|of)\s+)*(?:(?:after|post|pre)[\s-]{0,2}tax\s*)?$")


def _split_cases(segs):
    """One clause stating two scenarios becomes two clauses.

    RPX writes 'After-tax NPV5% C$523 million and after-tax IRR of 99.7% at a base case gold price
    of US$3,500/ounce and an after-tax NPV5% of C$935 million and IRR of 181% at an upside gold price
    of US$4,550/ounce' -- one clause, so both NPVs were filed under the first price and the second
    was dropped as a duplicate. Split only where each NPV carries its own figure after it and each
    part names a different case or price; otherwise the clause is left whole."""
    out = []
    for seg in segs:
        ms = list(_RE_NPV_AT.finditer(seg))
        if len(ms) < 2:
            out.append(seg)
            continue
        cuts = []
        for m in ms[1:]:
            if _money_just_before(seg, m.start()) or not _tagged_money(seg[m.end():m.end() + 80]):
                cuts = []
                break
            lead = _RE_TAX_LEAD.search(seg[:m.start()])
            cuts.append(lead.start() if lead else m.start())
        parts = [seg[a:b] for a, b in zip([0] + cuts, cuts + [len(seg)])] if cuts else [seg]
        keys = [_scenario_key(p_) for p_ in parts]
        if len(parts) > 1 and None not in keys and len(set(keys)) == len(keys) \
                and all(_tagged_money(p_[_RE_NPV_AT.search(p_).end():]) or _money_just_before(p_, _RE_NPV_AT.search(p_).start())
                        for p_ in parts if _RE_NPV_AT.search(p_)):
            out.extend(parts)
        else:
            out.append(seg)
    return out


_RE_CHANGE_TO = re.compile(r"(?i)\b(?:increas|ris|grow|improv|climb|jump|ris)\w*\s+to\s*$")
_RE_AT_PRICE = re.compile(r"(?i)^[\s,/]*(?:at|using|with)\b[^.;]{0,30}$")


def scenarios(text, skip_prior=False):
    """One row per scenario, pre-tax and after-tax on the same row (Justin, 2026-09-18).

    Desert Gold's three sensitivity sweeps -- gold price, then operating cost, then capital cost --
    carry no case name, only swings, so they are dropped here rather than becoming twenty-two rows.
    Doubleview tags three flowsheets inline in one sentence and gets three."""
    rows, order, _done = {}, [], set()

    def row_for(key):
        if key not in rows:
            order.append(key)
            rows[key] = {"scenario": key[0], "basis": key[1], "currency": None,
                         "discount_pct": None, "npv_pre_tax": None, "npv_after_tax": None,
                         "irr_pre_tax_pct": None, "irr_after_tax_pct": None,
                         "payback_years": None, "_pay_pre": False}
        return rows[key]

    # A table with a case per column is read as columns first, and the clauses it occupies are
    # then left alone. Read as prose, Canagold's four-column table is one scenario with four net
    # present values in it, which is how its Low and High cases went missing and its Base case
    # took the Spot case's payback.
    for cols in column_tables(text):
        for c in cols:
            r = row_for((c["scenario"], "real"))
            for k, v in c.items():
                if k != "scenario" and v is not None and r.get(k) is None:
                    r[k] = v
        figs = [_fmt_fig(c["npv_after_tax"]) for c in cols if c["npv_after_tax"] is not None]
        if figs:
            _done.update(sg for sg in segments(text) if any(f in sg for f in figs))

    segs = _split_cases(segments(text))
    stranded = []
    for i, seg in enumerate(segs):
        if seg in _done:
            continue
        if not _RE_NPV_AT.search(seg):
            continue
        # A label left stranded at the end of a clause takes its value from the start of the next
        # one. Surge writes 'After-tax NPV' and then the 8, the % and the figure each on a line
        # of its own, because the 8% is a superscript; Radisson breaks its label at the quote in
        # '("NPV 5% ") of $532 million'. Read clause by clause, both releases state no economics.
        # The sentence the stranded label began: the clauses after it for as long as they read as
        # a continuation -- a digit, a bracket, a quote, a comma, a currency mark or a lower-case
        # word -- and no further. Radisson states its base case and its spot case in consecutive
        # line-broken sentences; Surge follows its NPV line with 'Operating cost' and then a
        # 'High-grade' bullet, which a looser boundary read as a High case.
        j = i + 1
        while j < len(segs) and j < i + 14 and _RE_CONTINUES.match(segs[j]):
            j += 1
        sentence = " ".join(segs[i:j])
        tail = sentence if j > i + 1 else " ".join([seg] + segs[i + 1:i + 2])
        key0 = _scenario_key(seg)
        # A clause that names no case of its own takes its name from the sentence it belongs to,
        # backwards as well as forwards. Rua writes 'Leveraged to spot at US$4,700/oz gold' and then
        # ', NPV5% rises to US$113 million' on the next line; Bravada puts its price after the
        # figure; Allied Critical Metals splits 'NPV(8%) of $963.8 million' from 'at USD
        # $1,500/mtu'. Named from the fragment alone, each became 'base case', collided with the
        # real base case and was thrown away. Capped, so a run of table cells cannot become one
        # long 'sentence'.
        widened = None
        if key0 == "base case":
            a = i
            while a > max(0, i - 4) and _RE_CONTINUES.match(segs[a]):
                a -= 1
            b = i + 1
            while b < min(len(segs), i + 6) and _RE_CONTINUES.match(segs[b]):
                b += 1
            around = " ".join(segs[a:b])
            if len(around) <= 420:
                named = _scenario_key(around)
                if named and named != "base case":
                    key0, widened = named, around
        if key0 is None:
            continue
        for m in _RE_NPV_AT.finditer(seg):
            if skip_prior and _RE_PRIOR_REPORTED.search(seg[max(0, m.start() - 160):m.start()]):
                continue
            if _RE_NPV_DELTA.match(seg[m.end():m.end() + 30]) or _RE_NPV_ZERO.match(seg[m.end():m.end() + 14]):
                continue
            back = _money_just_before(seg, m.start())
            vals = [back[:3] + (back[3] - m.end(),)] if back else _tagged_money(seg[m.end():])
            look = seg
            if not vals and len(seg) - m.end() <= 12:
                # Reaching into the next clause means the clause the label is really in is wider
                # than the one it was split into, so the sweep test has to be re-run over that
                # wider text. Desert Gold's sensitivity table puts each swing, each 'NPV' and
                # each figure in a cell of its own: read one cell at a time, no cell carries a
                # swing, and every sweep row looks like a scenario.
                if _scenario_key(" ".join(segs[max(0, i - 1):i + 4])) is None:
                    continue
                look, vals = tail, _tagged_money(tail[m.end():])
                if not vals and i > 0 and _RE_ONLY_TAX.match(seg[:m.start()]) \
                        and _RE_HAS_ALPHA.search(re.sub(r"(?i)\b(?:million|billion|US|CAD|USD)\b", "", segs[i - 1])):
                    # the figure written first and the label on the next line: Cascadia's 'with a
                    # $230.4 M' then 'post-tax NPV', with nothing after the label but its rate and the
                    # IRR. Only from a line of words -- a bare '$71 M' cell is the row above's value
                    prev = segs[i - 1]
                    b2 = _money_just_before(prev + " " + seg, len(prev) + 1 + m.start())
                    if b2:
                        look, vals = seg, [b2[:3] + (None,)]
                named = _scenario_key(sentence)
                if named and named != "base case":
                    key0 = named
                stranded.append((sentence, key0))
            if not vals:
                continue
            # Omai: '$4.0 billion after-tax net present value at a 5% discount rate at base case
            # $3,600/oz gold, increasing to $5.5 billion at $4,200/oz gold'. The figure after
            # 'increasing to' is the NPV at the price that follows it, not at the base case, which
            # was published at $5.5 billion. That figure goes to its own price's row, and this label
            # keeps the one written before it.
            moved = None
            if not back and len(vals) == 1 and vals[0][3] is not None:
                vstart = m.end() + vals[0][3]
                if _RE_CHANGE_TO.search(look[m.end():vstart]):
                    vm = _RE_MONEY.match(look, vstart)
                    rest = (look[vm.end():] if vm else "") + " " + " ".join(segs[i + 1:j])
                    d2 = deck_in(rest[:60])
                    if d2 and _RE_AT_PRICE.match(rest[:d2.start()]):
                        moved = (" ".join(d2.group(0).split()), vals[0])
                        prev = segs[i - 1] if i > 0 else ""
                        b2 = _money_just_before(prev + " " + seg, len(prev) + 1 + m.start()) \
                            if prev and _RE_ONLY_TAX.match(seg[:m.start()]) else None
                        vals = [b2[:3] + (None,)] if b2 else []
            if moved:
                r2 = row_for((moved[0], _basis_near(look, None)))
                fld2 = "npv_pre_tax" if _tax_near(look, m.start(), m.end()) == "pre" else "npv_after_tax"
                if r2[fld2] is None:
                    r2[fld2] = moved[1][0]
                r2["currency"] = r2["currency"] or moved[1][1]
                r2["discount_pct"] = r2["discount_pct"] or discount_of(look[max(0, m.start() - 20):m.end() + 60])
            if not vals:
                continue
            disc = discount_of(look[max(0, m.start() - 20):m.end() + 60])
            if widened:
                stranded.append((widened, key0))
            colh = None
            if not back and len(vals) == 1 and not vals[0][2] and vals[0][3] is not None and _col_tax_header(look, m.start()):
                # 1.0.10: the second column's figure right after the first ('$464 million $344 million')
                v0m = _RE_MONEY.match(look, m.end() + vals[0][3])
                gap_ = re.match(r"\s*[|]?\s*(?=US\$|C\$|CA\$|A\$|\$)", look[v0m.end():v0m.end() + 8]) if v0m else None
                v1m = _RE_MONEY.match(look, v0m.end() + gap_.end()) if gap_ else None
                if v1m and (v1m.group("mult") or "").lower():
                    try:
                        v1 = numval(v1m.group("num")) * _MULT.get(v1m.group("mult").lower(), 1.0)
                        vals = [vals[0], (_signed(v1m, v1), vals[0][1], None, v1m.start() - m.end())]
                    except ValueError:
                        pass
            if not back and len(vals) == 2 and not any(x[2] for x in vals):
                colh = _col_tax_header(look, m.start())
            for vi, item in enumerate(vals):
                v, cur, tag = item[0], item[1], item[2]
                off = item[3] if len(item) > 3 else None
                at = None if off is None else m.end() + off
                tax = colh[vi] if colh else _tax_near(look, m.start(), m.end(), at if at and at > m.end() else None)
                r = row_for((key0 + (" " + tag if tag else ""), _basis_near(look, at)))
                fld = "npv_pre_tax" if tax == "pre" else "npv_after_tax"
                if r[fld] is None or _more_precise(v, r[fld]):
                    r[fld] = v
                r["currency"] = r["currency"] or cur
                r["discount_pct"] = r["discount_pct"] or disc
        for m in _RE_IRR_AT.finditer(seg):
            pb = _pct_just_before(seg, m.start())
            items_ = [pb] if pb else _tagged_percents(seg[m.end():])
            if not pb and len(items_) == 1 and not items_[0][1] and _col_tax_header(seg, m.start(), 400):
                # 1.0.10: the second column's rate right after the first ('IRR 168% 137%', Voyageur)
                at0 = m.end() + items_[0][2]
                p1 = re.match(r"\d{1,3}(?:\.\d+)?\s*%", seg[at0:])
                p2 = re.match(r"\s*[|]?\s*(\d{1,3}(?:\.\d+)?)\s*%", seg[at0 + p1.end():]) if p1 else None
                if p2:
                    items_ = [items_[0], (float(p2.group(1)), None, items_[0][2] + p1.end() + p2.start(1))]
            colh = _col_tax_header(seg, m.start(), 400) if not pb and len(items_) == 2 and not any(x[1] for x in items_) else None
            for vi, item in enumerate(items_):
                v, tag = item[0], item[1]
                off = item[2] if len(item) > 2 else None
                at = m.start() - 6 if off is None else m.end() + off
                tax = colh[vi] if colh else _tax_near(seg, m.start(), m.end(), at if at > m.end() else None)
                fld = "irr_pre_tax_pct" if tax == "pre" else "irr_after_tax_pct"
                r = row_for((key0 + (" " + tag if tag else ""), _basis_near(seg, at)))
                if r[fld] is None:
                    r[fld] = v
        _apply_payback(seg, rows, order, key0)

    # A figure found by reaching past a stranded label brings its sentence with it, and that
    # sentence's IRR and payback belong to the same scenario: Radisson writes ', Internal Rate of
    # Return of 48%, and payback of 2.0 years' on lines of their own after the NPV.
    for sentence, key in stranded:
        mine = [k for k in order if k[0] == key or k[0].startswith(key + " ")]
        if len(mine) != 1:
            continue
        r = rows[mine[0]]
        for m in _RE_IRR_AT.finditer(sentence):
            pb = _pct_just_before(sentence, m.start())
            for item in ([pb] if pb else _tagged_percents(sentence[m.end():])[:1]):
                off = item[2] if len(item) > 2 else None
                at = m.start() - 6 if off is None else m.end() + off
                tax = _tax_near(sentence, m.start(), m.end(), at if at > m.end() else None)
                fld = "irr_pre_tax_pct" if tax == "pre" else "irr_after_tax_pct"
                if r[fld] is None:
                    r[fld] = item[0]
        _apply_payback(sentence, rows, mine)

    # A release states its discount rate once and every NPV in it is on that rate. West Red Lake
    # writes 'all net present values are stated at a 5% discount rate' in a sentence that states
    # no figure, so neither the window around an NPV nor the orphan pass above ever reaches it.
    fallback = discount_of(text)
    if fallback is not None:
        for k in order:
            if rows[k]["discount_pct"] is None:
                rows[k]["discount_pct"] = fallback

    # 'base case' is the name a row gets when the clause stating its NPV named no case and no
    # price. It is not a name -- every study has a base case -- so where the release states the
    # price that base case is on, it goes on the row. Rows that named their own case or deck are
    # left alone: Radisson's two rows already say 'base case US$2,550/oz' and 'spot US$3,300/oz'.
    # A plain 'base case' row -- typically the headline's, which names no price -- is the same
    # scenario as the one decked row whose figures it matches. Radisson headlines 'C$532M
    # After-Tax NPV5%' and states the same C$532M 'at US$2,550/oz gold' in the body; named apart,
    # the page showed the base case twice, once under the spot price.
    for k in [k for k in order if rows[k]["scenario"] == "base case"]:
        cands = [k2 for k2 in order if k2 != k and rows[k2]["scenario"] != "base case"
                 and rows[k2]["basis"] == rows[k]["basis"] and _same_scenario(rows[k], rows[k2])]
        if len(cands) == 1:
            dst = rows[cands[0]]
            for f, v in rows[k].items():
                if v is not None and dst.get(f) is None:
                    dst[f] = v
            order.remove(k)
    plain = [k for k in order if rows[k]["scenario"] == "base case"]
    if plain:
        deck = base_deck(text)
        if deck:
            for k in plain:
                rows[k]["scenario"] = "base case " + deck
    out = _consolidate(_merge_scenarios(order, rows))
    # An IRR or a payback often sits in its own clause, away from the NPV it belongs to: Lomiko
    # and ESGold both put every figure on its own bullet. Attach those afterwards, by tax basis,
    # and only when there is no ambiguity about which scenario is meant. Counted after the rows
    # that are one scenario written twice have been merged: West Red Lake headlines '$315M
    # After-Tax NPV' and states the same $315 million at US$2,200 per oz in its highlights, which is
    # one scenario, and its '255%' IRR sits in a table row of its own.
    if len(out) == 1:
        r = out[0]
        one = {0: r}
        for seg in _pay_joined(segments(text)):
            if _RE_NPV_AT.search(seg):
                # a clause a table already read is skipped above, payback and all: Northcliff's
                # '...49.8% and a 1.6-year payback' sits in the clause its table figures came from
                if seg in _done:
                    _apply_payback(seg, one, [0])
                continue
            for m in _RE_IRR_AT.finditer(seg):
                for v, _tag, off in _tagged_percents(seg[m.end():], limit=60):
                    tax = _tax_near(seg, m.start(), m.end(), m.end() + off)
                    fld = "irr_pre_tax_pct" if tax == "pre" else "irr_after_tax_pct"
                    if r[fld] is None:
                        r[fld] = v
            _apply_payback(seg, one, [0])
            if r["discount_pct"] is None:
                d = discount_of(seg)
                if d is not None:
                    r["discount_pct"] = d
    for r in out:
        r.pop("_pay_pre", None)
    return out


# ---------------------------------------------------------------- the rest of the study
# These do not vary by scenario in any release in the set -- Mag One states one capital cost and
# one AISC above two gold-price cases, and the labels carry the same figure on both rows -- so
# they are read once per release and copied onto every scenario.
_RE_CAPEX = re.compile(r"""(?ix)
    (?: (?:initial|upfront|pre[\s-]?production|development|start[\s-]?up|construction)
        (?:\s*\|)? \s+ (?:project \s+ (?:\|\s*)?)? cap(?:ital|ex) (?:\s+ (?:cost|expenditure|requirement))? s?
      | cap(?:ital|ex) \s+ cost s? (?!\s+ per)
      | initial \s+ investment )""")
_RE_SUSTAIN = re.compile(r"(?i)\bsustaining\b")
_RE_OPEX = re.compile(r"""(?ix)
    (?: (?:average|life[\s-]of[\s-]mine|LOM|total|cash|operating|processing|site) \s+ )*
    (?: operating \s+ cost s? | opex | cash \s+ (?:operating\s+)? cost s? | \bOPEX\b )""")
_RE_AISC = re.compile(r"(?ix)\bAISC\b|all[\s-]in\s+sustaining\s+cost s?")
_RE_LOM = re.compile(r"""(?ix)
    (?: (?:mine|project) \s+ life | life \s+ of \s+ (?:mine|the\s+mine|project) | \bLOM\b )""")
_RE_TPD = re.compile(r"""(?ix)
    (?<![\d.,])(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?) \s*
    (?: tpd | t/d | tonnes? [\s-]+ per [\s-]+ day | t \s+ per \s+ day | tons? [\s-]+ per [\s-]+ day )\b""")   # 1.0.14b: '750 tonne-per-day' 
# 1.0.14: 'million' and 'thousand' written out ('54 million tonnes per annum') are magnitudes too
_RE_TPA = re.compile(r"""(?ix)
    (?<![\d.,])(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?) \s* (?P<mag>million|thousand|M|k)? \s*
    (?: tpa | t/(?:a|y|yr) | tonnes? \s+ per \s+ (?:annum|year) | tons? \s+ per \s+ (?:annum|year) )\b""")
# 1.0.14 (FIX8, 2026-10-06): a throughput is ore through a plant. Without these checks a product's output was read as
# the mill's: Leading Edge's '248tpa Dysprosium' oxide became a 0.7 t/d mill, Energy Fuels' 1,000 tpa of NdPr 2.7 t/d,
# E3's '100 tonnes per year of lithium carbonate' 0.3 t/d; and a mining rate (waste included) as the processing rate:
# Champion's '81.0 Mtpa' peak mining rate became 221,918 t/d.
_RE_TP_PRODUCT = re.compile(r"""(?ix)^[\s()"“”,]*(?:\(?\s*["“]?\s*(?:tp[ad]|Mtpa)\s*["”]?\s*\)\s*)?(?:of\s+)?
    (?:[A-Za-z-]+\s+){0,2}?(?:oxides?|carbonate|hydroxide|LCE|concentrates?|NdFeB|NdPr|magnets?|alloys?|metals?|cathodes?|
    sulphate|sulfate|Dy|Tb|dysprosium|terbium|spodumene|anode|graphite|salt|potash|products?|HPMO|HPMSM|pellets?|
    briquettes?|SOP|fertili[sz]er|steel|ingots?|powder)\b""")
_RE_TP_ORE = re.compile(r"(?i)\b(?:process\w*|mill(?:s|ed|ing)?|plant|throughput|concentrator|feed|treat\w*|leach\w*|ores?|nameplate|"
                        r"crush\w*|flotation|CIL|CIP|heap)\b")
# 1.0.14b: the plant named right after the figure: Defense Metals' '1.8 Mtpa ("million tonnes per year") mill throughput',
# Leading Edge's '15 Mtpa of plant feed'
_RE_TP_ORE_AFTER = re.compile(r"(?i)^\s*(?:\([^()]{0,40}\)\s*)?(?:of\s+)?(?:(?:ore|plant|mill)\s+)?(?:mill\w*|plant|process\w*|throughput|ore|feed|concentrator)\b")
_RE_TP_MINING = re.compile(r"(?i)\b(?:mining\s+rates?|material\s+mov\w+|total\s+material|waste|strip\w*|mined|mining\s+of)\b")
# 1.0.14 (FIX8): annual production is the figure the label states, in a unit. The old pattern let any twenty characters
# sit between the label and the number, so 'average annual gold production in the first 5 years' was stored as 5,
# 'annual production over an initial 9.4-year mine life' as 9.4, 'average annual gold production, and $1.8 billion
# after-tax NPV' as 1.8 billion; and a magnitude or unit without a word boundary read Northcliff's '598,000 MTU' as 598
# billion tonnes and '750 metric tons' as 750 million. Only linking words now sit between label and figure; money,
# years and percentages are never the figure; magnitude and unit are whole words; a figure without a unit is dropped.
_PROD_WORD = (r"(?:gold|silver|copper|lithium|nickel|zinc|lead|uranium|molybdenum|cobalt|tungsten|antimony|graphite|"
              r"vanadium|LCE|payable|metals?|mine|mill|recovered|AuEq|AgEq|CuEq|ZnEq|GEOs?|equivalent|eq\.?|"
              r"U3O8|U₃O₈|WO3|concentrate|Au|Ag|Cu)")
_PROD_UNIT = (r"(?P<unit>koz|Moz|ozs|oz|ounces?|Mlbs?|klbs?|lbs?|pounds?|kt|Mt|tonnes?|metric\s+tonnes?|metric\s+tons?|"
              r"tons?|t|MTU|wmt|dmt)\b")
# 1.0.14b (FIX8, 2026-10-06): a tonnage of ore, rock or mill feed is a mining or processing rate, never a year's production:
# Azarga's 'annual production rate of 2 million tonnes of ore per year'
_PROD_NOT_ORE = r"(?!\s*(?:of\s+)?(?:ore|mineraliz\w*|mineralis\w*|material|rock|feed|mill\s+feed|waste)\b)"
_PROD_NUM = r"(?<![\d.,$])(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
# 1.0.14b: the magnitude is optional AS A WHOLE WORD. '(?P<mag>...)?(?![a-z])' also refused a figure glued to its unit
# ('207koz', '16,000oz', '217,700t', '~100kt'), so those releases lost their production
_PROD_MAG = r"(?:(?P<mag>million|billion|thousand|mm|M|k)(?![a-z]))?"
_RE_PROD = re.compile(r"""(?ix)
    (?: average \s+ )? (?: annual | yearly | per[\s-]annum | LOM \s+ average | LOM \s+ annual ) \s+
    (?: """ + _PROD_WORD + r""" [\s-]+ )*
    production (?: \s+ (?:rate|profile|capacity|levels?) )?
    (?: \s* \( [^()]{0,40} \) )?
    (?: \s* (?: : | = | \| | – | — | of | is | was | will \s+ be | (?:is\s+|are\s+)?(?:expected|projected|estimated|forecast)
              \s+ (?:to \s+ be|at) | averag\w* | totall?ing | approximately | approx\.? | about | ~ | up \s+ to | more \s+ than
              | over | above | in \s+ excess \s+ of | nearly | almost | approaching | roughly | around | to | between ) )*
    \s* """ + _PROD_NUM + r"""
    (?: \s* (?:-|–|to|and) \s* (?P<num2>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?) )?
    (?! [\s-]* (?:years?|yrs?)\b | \s*% )
    (?: \s* \| \s* (?: \[\d{1,2}\] \s* \| \s* )? )?
    \s* """ + _PROD_MAG + r"""
    \s* (?: """ + _PROD_WORD + r""" [\s-]+ )*
    """ + _PROD_UNIT + _PROD_NOT_ORE)
# the figure written before the label: '235 koz of average annual gold production', '17.4 Moz AgEq annual production'
_RE_PROD_BEFORE = re.compile(r"""(?ix)
    """ + _PROD_NUM + r""" \s* """ + _PROD_MAG + r""" \s* (?: """ + _PROD_WORD + r""" [\s-]+ )* """ + _PROD_UNIT + r"""
    \s* (?: (?: """ + _PROD_WORD + r""" ) [\s-]+ )* (?: of \s+ )? (?: average \s+ )? (?: annual | yearly ) \s+
    (?: """ + _PROD_WORD + r""" [\s-]+ )* production\b""")
# 1.0.14b: an ounce or pound figure 'per year' with no label: Revival's 'an average of 95,600 ounces of gold per year',
# Kore's '146,000 ounces gold per year', Montage's '207koz/year'. Ounces and pounds only: a tonnage per year is as often
# ore through the mill as metal out of it. Read last, after both labelled forms.
_RE_PROD_PER_YEAR = re.compile(r"""(?ix)
    """ + _PROD_NUM + r""" \s* """ + _PROD_MAG + r""" \s* (?: """ + _PROD_WORD + r""" [\s-]+ )*
    (?P<unit>koz|Moz|ozs|oz|ounces?|Mlbs?|klbs?|lbs?|pounds?)\b
    \s* (?: of \s+ )? (?: (?: """ + _PROD_WORD + r""" ) [\s-]* )* (?: \([^()]{0,12}\) \s* )?
    (?: per \s+ (?:year|annum) | / \s? (?:year|yr|annum) | annually | a \s+ year | each \s+ year )\b""")
_RE_PROD_NOT_OUTPUT = re.compile(r"(?i)\b(?:royalt\w*|stream\w*|deliver\w*|purchas\w*|offtake|sell\w*|sold|hedg\w*|forward)\b")
_PROD_UNIT_SCALE = {"koz": ("oz", 1e3), "moz": ("oz", 1e6), "oz": ("oz", 1), "ozs": ("oz", 1), "ounce": ("oz", 1), "ounces": ("oz", 1),
                    "mlb": ("lb", 1e6), "mlbs": ("lb", 1e6), "klb": ("lb", 1e3), "klbs": ("lb", 1e3), "lb": ("lb", 1),
                    "lbs": ("lb", 1), "pound": ("lb", 1), "pounds": ("lb", 1), "kt": ("t", 1e3), "mt": ("t", 1e6),
                    "t": ("t", 1), "tonne": ("t", 1), "tonnes": ("t", 1), "ton": ("t", 1), "tons": ("t", 1),
                    "wmt": ("t", 1), "dmt": ("t", 1), "mtu": ("mtu", 1)}
# what a year's production can be, by unit: outside these it is a misread, not a mine
_PROD_BOUNDS = {"oz": (500.0, 6e7), "lb": (1e4, 3e9), "t": (1.0, 3e8), "mtu": (1e3, 1e7)}


def _production(m):
    """(value, unit) from a production match, or (None, None) when it cannot be a year's production."""
    try:
        v = float(m.group("num").replace(",", ""))
        if m.groupdict().get("num2"):
            v = (v + float(m.group("num2").replace(",", ""))) / 2.0   # '70,000 to 75,000 ounces': the middle
    except ValueError:
        return None, None
    u = re.sub(r"\s+", " ", (m.group("unit") or "").lower())
    u = {"metric tonne": "t", "metric tonnes": "t", "metric ton": "t", "metric tons": "t"}.get(u, u)
    unit, scale = _PROD_UNIT_SCALE.get(u, (None, 1))
    if unit is None:
        return None, None
    v *= scale * _MULT.get((m.group("mag") or "").lower(), 1.0)
    lo, hi = _PROD_BOUNDS[unit]
    if not lo <= v <= hi:
        return None, None
    return v, unit


# a unit cost is written '/oz', 'per tonne', '$/t LCE' -- the number alone is meaningless
# 1.0.14 (FIX8, 2026-10-06): the number is a whole number. '[\d,]*' let a footnote digit and its comma be the figure --
# Endeavour's 'Total Cash Cost1, $/oz 1,593' was stored as an operating cost of $1/oz -- and a figure glued to a word is a
# footnote ('Cost1'). A table that puts the unit in a header cell ('$/oz 1,516', '$/oz (1.51)') is read from the header;
# 'negative $121/lb' and a bracketed figure keep their sign; the commodity after the unit is named one way ('/lb Mo').
_UC_OF = (r"Au|Ag|Cu|Li|LCE|Ni|Zn|Pb|Mo|Co|U3O8|U₃O₈|eU3O8|WO3|AuEq|AgEq|CuEq|GEO|gold|silver|copper|"
          r"lithium(?:\s+carbonate(?:\s+equivalent)?)?|nickel|zinc|molybdenum|uranium|cobalt|concentrate")
_UC_NUM = r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
# 1.0.14b (FIX8, 2026-10-06): '$US892/oz', 'US $10.23', 'USD $6,807' are currencies too; 'per ton' and '/ton' are tonnes;
# 'per tr oz' is an ounce; and a footnote digit on the UNIT ('$925/oz1', '$18.39 per pound2', '$5,618 per tonne3') is not
# part of it. Each of these lost a stated cost.
_RE_UNIT_COST = re.compile(r"""(?ix)
    (?P<cur>US\s?\$|C\$|CA\$|A\$|\$\s?US|USD\s?\$?|CAD\s?\$?|\$)? \s* (?:(?<=\$US)|(?<=\$\sUS)|(?<![A-Za-z\d.,])) """ + _UC_NUM + r""" (?![\d,]) \s*
    (?: (?:/|\s+per\s+) \s? (?:tr(?:oy)?\.?\s+)? (?P<unit>ounce|oz|tonnes?|tons?|t|pound|lb|klb|Mlb|LCE|unit)(?:\d(?![\d.,]))?\b
      | \s? / (?P<unit2>oz|tonnes?|tons?|t|lb)(?:\d(?![\d.,]))?\b )
    (?: \s* (?:of\s+)? (?P<of>""" + _UC_OF + r""")\b )?""")
_RE_UNIT_COST_HEAD = re.compile(r"""(?ix)
    (?:\(\s*)? (?P<cur>US|C|CA|A)?\$ \s? / \s? (?P<unit>oz|ounce|t|tonne|lb|pound)\b (?:\s*\))?
    (?: \s* (?P<of>""" + _UC_OF + r""")\b )? \s* (?:\|\s*)? (?P<paren>\()? \s* (?<![A-Za-z\d.,]) """ + _UC_NUM + r""" (?![\d,])""")
_UC_OF_NAME = {"gold": "Au", "silver": "Ag", "copper": "Cu", "nickel": "Ni", "zinc": "Zn", "molybdenum": "Mo",
               "cobalt": "Co", "uranium": "U3O8", "u₃o₈": "U3O8", "lithium": "LCE", "lithium carbonate": "LCE",
               "lithium carbonate equivalent": "LCE", "li": "LCE", "concentrate": "conc."}
# what a cost per unit can be: outside these it is a misread
_UC_BOUNDS = {"oz": (-500.0, 8000.0), "t": (0.5, 60000.0), "lb": (-300.0, 300.0)}


def result_money(text):
    """money(), minus the price assumptions. A capital cost is never quoted per ounce."""
    for m in _RE_MONEY.finditer(text or ""):
        cur_raw = (m.group("cur") or "").upper().replace("$", "").strip() or None
        mult = (m.group("mult") or "").lower()
        if not cur_raw and not mult:
            continue
        if _is_unit_price(text, m.end(), mult):
            continue
        if not m.group("cur") and (mult == "k" or _qty_after(text, m.end())):
            continue                      # 1.0.10: a quantity, or a name like 'Tasiast 24k'
        try:
            v = numval(m.group("num")) * (_MULT.get(mult, 1.0) if mult else 1.0)
        except ValueError:
            continue
        if m.group("neg"):
            continue
        if not mult and _RE_SCALE_K.search(text[max(0, m.start() - 6):m.start()]):
            v *= 1e3                      # 1.0.10: 'Pre-production Capital K US$ 278,092' is US$278 million (Integra)
        # Salazar's 'Initial Capital Cost (US$ M) US$248 US$283.7' is the old study beside the new
        # one, and Bravo's 'Total Initial Capex M US$ 496 677.6' two cases: a bare figure is left
        # to the prose, which states the capital with its magnitude
        if (not mult and v < _MIN_BARE) or v > _MAX_RESULT:
            continue
        return v, {"C": "CAD", "CA": "CAD", "CAD": "CAD", "CDN": "CAD", "US": "USD", "USD": "USD",
                   "A": "AUD", "AUD": "AUD"}.get(cur_raw)
    return None, None


def _near(text, m, span=180):
    """The clause a label governs: what follows it, capped, and cut at the next sentence end.

    A cost label reaches forward to its figure and no further. 'Initial capital of US$58 million.
    Operating costs of US$1,070/oz' read with a flat 180-character window puts the operating cost
    inside the capital cost's reach and the capital figure inside the operating one's."""
    tail = text[m.end():m.end() + span]
    # a label's reach ends at its own clause. Canagold writes 'payback of pre-production capital
    # expenditures ("CAPEX") of 2.4 years' and then, two bullets later, '$793 million'; without
    # the clause cut the first capital label reaches that figure and publishes it as the capex.
    cut = re.search(r"[.;]\s+[A-Z]|\n\n|\s\|\s|\u2022", tail)
    return tail[:cut.start()] if cut else tail


# the qualifier has to follow the capital figure itself: MAI's 'initial capital cost of $58 M and
# sustaining capex of $77 M over the LOM' puts it on the sustaining figure, not the initial one
_RE_OVER_LIFE = re.compile(r"(?i)^\s*(?:\([^)]{0,40}\)\s*)?over\s+(?:the\s+)?(?:life\s+of\s+(?:the\s+)?(?:mine|project)|LOM|mine\s+life|project\s+life)\b")
_RE_FIG_LEAD = re.compile(r"(?i)^\s*\(?\s*(?:US|USD|C|CA|CAD|A|AUD)?\s?\$\s?\d|^\s*\d[\d,.]*\s*(?:million|billion|M|B)\b")


def _over_life(clause):
    """True when the first capital figure in a clause is a life-of-mine total."""
    for m in _RE_MONEY.finditer(clause):
        return bool(_RE_OVER_LIFE.match(clause[m.end():m.end() + 60]))
    return False
_RE_EMPTY_CLAUSE = re.compile(r"^[\s:=\-–—(),]*$")


def _near_or_next(text, m, span=180):
    """_near(), or -- when the label's own clause holds nothing but punctuation -- the line after it.
    Scottie writes 'Initial capital cost:' and '$128.6M' on the next line; the clause cut at the
    line break left the label with no figure at all."""
    c = _near(text, m, span)
    if not _RE_EMPTY_CLAUSE.match(c):
        return c
    tail = text[m.end():m.end() + span]
    sep = re.search(r"\s\|\s", tail)
    if not sep or not _RE_EMPTY_CLAUSE.match(tail[:sep.start()]):
        return c
    nxt = tail[sep.end():]
    if not _RE_FIG_LEAD.match(nxt):
        return c              # a heading over a table ('Total Capital Costs') is not this figure's label
    cut = re.search(r"[.;]\s+[A-Z]|\n\n|\s\|\s|•", nxt)
    return nxt[:cut.start()] if cut else nxt


def unit_cost(text):
    """A per-unit cost as (value, currency, unit). '$1,070/oz' -> (1070.0, None, 'oz').

    Never falls back to a bare number: Desert Gold's US$35/t and Surge's US$5,097/t LCE are the
    same shape, and a release that states a cost only as a total would otherwise have its total
    published in the per-tonne column."""
    text = text or ""
    m = _RE_UNIT_COST.search(text)
    h = _RE_UNIT_COST_HEAD.search(text)
    if h is not None and (m is None or h.start() < m.start()):
        m = h
    if not m:
        return None, None, None
    try:
        v = float(m.group("num").replace(",", ""))
    except ValueError:
        return None, None, None
    if m.re is _RE_UNIT_COST_HEAD:
        if m.group("paren") and text[m.end():m.end() + 2].lstrip().startswith(")"):
            v = -v                        # '(1.51)': an accounting negative
    elif re.search(r"(?i)(?:negative|minus)\s*(?:US|C|CA|A)?\$?\s*$", text[max(0, m.start() - 14):m.start() + len(m.group("cur") or "")]):
        v = -v                            # 'negative $121/lb', net of by-product credits
    cur_raw = (m.group("cur") or "").upper().replace("$", "").strip() or None
    unit = (m.group("unit") or (m.groupdict().get("unit2") or "")).lower()
    unit = {"ounce": "oz", "tonne": "t", "tonnes": "t", "ton": "t", "tons": "t", "pound": "lb"}.get(unit, unit)
    if m.group("of"):
        of = re.sub(r"\s+", " ", m.group("of"))
        unit = unit + " " + _UC_OF_NAME.get(of.lower(), of)
    base = unit.split(" ")[0] if unit else ""
    if base in _UC_BOUNDS:
        lo, hi = _UC_BOUNDS[base]
        if not lo <= v <= hi or v == 0:
            return None, None, None
    return v, {"C": "CAD", "CA": "CAD", "CAD": "CAD", "CDN": "CAD", "US": "USD", "USD": "USD",
               "A": "AUD", "AUD": "AUD"}.get(cur_raw), unit or None


_RE_AISC_BEFORE = re.compile(r"""(?ix)(?:US\$|C\$|CA\$|A\$|\$)\s?(?P<num>\d[\d,]*(?:\.\d+)?)\s*
    (?:/|per\s+)(?P<unit>oz|ounce|lb|pound|t|tonne)\b(?:\s*(?:Au|Ag|Cu|gold|silver|copper))?
    [\s(\u201c\u201d"]{0,4}$""")
_RE_AISC_PER = re.compile(r"(?i)^[^$\d]{0,6}?\bper\s+(oz|ounce|lb|pound|tonne|t)\b")
_RE_AISC_AFTER = re.compile(r"""(?ix)^[^$\d.;]{0,30}?(?:US|USD|C|CAD|CDN|A|AUD)?\s?\$\s?
    (?P<num>\d[\d,]*(?:\.\d+)?)(?!\s*(?:million|billion|M\b|B\b|[\d,]))""")


def aisc_near(flat, m):
    """All-in sustaining cost as (value, unit), from the figure the label is attached to.

    Three shapes, each seen: Lafleur puts the figure first ('US$1,569/oz AISC'); Desert Gold puts
    the unit in the label ('All in sustaining cost per oz ("AISC") of USD $1,352'), so the figure
    wears none -- and reaching past it for one that does published its $2,850/oz gold price as its
    AISC; everyone else writes 'AISC of US$1,681 per oz'. The last is read only close to the label."""
    b = _RE_AISC_BEFORE.search(flat[max(0, m.start() - 40):m.start()])
    if b:
        u = b.group("unit").lower()
        return float(b.group("num").replace(",", "")), {"ounce": "oz", "tonne": "t", "pound": "lb"}.get(u, u)
    tail = flat[m.end():m.end() + 70]
    per = _RE_AISC_PER.search(tail)
    if per:
        a = _RE_AISC_AFTER.search(tail[per.end():])
        if a and not _RE_UNIT_TAIL.match(tail[per.end() + a.end():per.end() + a.end() + 14]):
            u = per.group(1).lower()
            return float(a.group("num").replace(",", "")), {"ounce": "oz", "tonne": "t", "pound": "lb"}.get(u, u)
    v, cur, unit = unit_cost(_near(flat, m, 70))
    return (v, unit) if v is not None else (None, None)


_RE_PHASE = re.compile(r"(?ix)\b(?:phase\s*[12]|\bP[12]\b|stage\s*[12]|first\s+phase|"
                       r"second\s+phase|expansion)\b")
_RE_TOTAL = re.compile(r"(?i)\btotal\b")
_RE_TOTAL_OF = re.compile(r"(?i)\btotal(?:ling|ing|s)?\s+of\s+")


def project_economics(text):
    """Capital, operating cost, AISC, mine life, throughput and annual production.

    Read from the first label that has a figure in its own clause. A flattened table is reflowed
    first, exactly as the scenario splitter does it, so 'Initial Capital | $ M | 5,323' is read
    rather than skipped for want of a currency mark."""
    out = {"initial_capex": None, "capex_currency": None, "opex": None, "opex_unit": None,
           "aisc": None, "aisc_unit": None, "mine_life_years": None,
           "throughput_tpd": None, "annual_production": None, "production_unit": None}
    flat = " | ".join(segments(text or ""))

    caps, lom_totals = [], []
    for m in _RE_CAPEX.finditer(flat):
        # 'sustaining' has to be qualifying THIS label, not sitting in the sentence before it:
        # 'Sustaining capital of US$40 million and initial capital cost of US$290 million' is a
        # release that states both, and a 40-character lookback throws the initial figure away.
        if _RE_SUSTAIN.search(flat[max(0, m.start() - 14):m.start()]):
            continue
        # 'C$175M Initial Capital' writes the figure first, exactly as the NPV headline does
        back = _money_just_before(flat, m.start())
        v, cur = (back[0], back[1]) if back else result_money(_near_or_next(flat, m))
        if v is None:
            continue
        # Lithium Argentina: 'Stage 1 initial capital cost estimated at $1.1 billion ... Total
        # capital cost of $3.3 billion over life of project'. A figure spent over the life of the
        # mine is not what it costs to build it.
        if _over_life(_near_or_next(flat, m)):
            lom_totals.append(v)
            continue
        # the qualifier has to be attached to THIS label. Surge's totals line reads
        # '... P2 | $ M | $2,350 | Total Capital Cost (CAPEX) $5,323 million', and a 26-character
        # lookback reaches back over the separator into the previous cell's P2, marking the
        # total as a phase and leaving the reader with the first phase's 2.97 billion.
        tail = flat[m.end():m.end() + 26].split("|")[0]
        around = flat[max(0, m.start() - 14):m.start()] + flat[m.start():m.end()] + tail
        phase = bool(_RE_PHASE.search(around))
        total = bool(_RE_TOTAL.search(flat[max(0, m.start() - 20):m.start()]))
        caps.append((v, cur, phase, total, m.end()))

    # the same life-of-project figure restated in a table without its qualifier ('Capital Costs $3.3 B')
    if lom_totals:
        caps = [c for c in caps if not any(abs(c[0] - t) <= 0.02 * t for t in lom_totals)]
    # Surge builds its lithium plant in two phases and states all three figures: 'Capital Cost
    # (CAPEX) P1 $M 2,973', 'P2 $M 2,350', 'Total Capital Cost (CAPEX) $M 5,323'. The first one
    # read is a phase, and publishing it understates the project by two and a half billion.
    pick = (next((c for c in caps if c[3] and not c[2]), None)
            or next((c for c in caps if not c[2]), None)
            or (caps[0] if caps else None))
    if pick is not None and pick[2]:
        # Surge's filing states the total without giving it a label of its own: 'Phase 1 CAPEX:
        # US$2.97 Billion, Phase 2 CAPEX: US$2.35 Billion, total of US$5.32 Billion'. Every
        # labelled figure there is a phase, and the project's capital is the trailing phrase.
        for c in caps:
            tm = _RE_TOTAL_OF.search(flat[c[4]:c[4] + 150])
            if tm:
                tv, tcur = result_money(flat[c[4] + tm.end():c[4] + tm.end() + 40])
                if tv is not None:
                    pick = (tv, tcur or pick[1], False, True, c[4])
                    break
    if pick is not None:
        out["initial_capex"], out["capex_currency"] = pick[0], pick[1]

    for m in _RE_OPEX.finditer(flat):
        if _RE_AISC.search(flat[max(0, m.start() - 30):m.end() + 10]):
            continue
        v, cur, unit = unit_cost(_near(flat, m, 140))
        if v is not None:
            out["opex"], out["opex_unit"] = v, unit
            break

    # the first mention is often a heading ('High Grade, Low CAPEX and Low AISC') or a label cut
    # off by a footnote marker ('all-in sustaining costs\n\n1\n\n("AISC") of $1,314/oz'): the
    # first mention that carries a figure is the one.
    for m in list(_RE_AISC.finditer(flat))[:6]:
        v, unit = aisc_near(flat, m)
        if v is not None:
            out["aisc"], out["aisc_unit"] = v, unit
            break

    lives = []
    for m in _RE_LOM.finditer(flat):
        # The figure sits on either side, and the ADJACENT one wins. 'over a 28 year mine life'
        # puts it first; Surge writes 'over the 42-year life of mine' and then, forty characters
        # on, 'Peak Production ... in Year 6', so looking forward first reads a six-year mine.
        # Tantalex is the other trap: 'Rapid payback of 1 year after first production using a
        # Life of Mine spodumene concentrate price' -- a loose look back publishes a one-year
        # mine, which is why the figure must be adjacent to the label and not merely near it.
        head = flat[max(0, m.start() - 40):m.start()]
        ym = None
        for mm in _RE_YEARS.finditer(head):
            if re.fullmatch(r"[\s,\-()]*", head[mm.end():]):
                ym = mm
        if ym is not None:
            v = float(ym.group("num"))
            y = round(v / 12.0, 2) if ym.group("unit").lower().startswith(("month", "mth")) else v
        else:
            y = years(_near(flat, m, 120))
        if y is not None and 0 < y <= 100:
            lives.append(y)
    # West Red Lake says '7.2- year mine life' in one bullet, '7-year mine life' in another and
    # 'Mine Life yrs 7.25' in its table. Those are one number written three ways, so the most
    # precisely written one wins -- but only among figures close enough to be the same number.
    if lives:
        near = [v for v in lives if abs(v - lives[0]) <= max(0.5, lives[0] * 0.15)]
        out["mine_life_years"] = max(near, key=lambda v: (len(("%.10g" % v).replace(".", "")), -v))

    # 1.0.14 (FIX8): the first throughput that is ore through a plant, in a range a plant can run at
    for m in _RE_TPD.finditer(flat):
        if _RE_TP_PRODUCT.match(flat[m.end():m.end() + 60]):
            continue
        v = float(m.group("num").replace(",", ""))
        if 10 <= v <= 500000:
            out["throughput_tpd"] = v
            break
    if out["throughput_tpd"] is None:
        for m in _RE_TPA.finditer(flat):
            before = flat[max(0, m.start() - 100):m.start()]
            if (_RE_TP_PRODUCT.match(flat[m.end():m.end() + 60])
                    or not (_RE_TP_ORE.search(before) or _RE_TP_ORE_AFTER.match(flat[m.end():m.end() + 70]))
                    or _RE_TP_MINING.search(before[-60:])):
                continue
            mult = _MULT.get((m.group("mag") or "").lower(), 1.0)
            v = round(float(m.group("num").replace(",", "")) * mult / 365.0, 1)
            if 20 <= v <= 500000:
                out["throughput_tpd"] = v
                break

    # 1.0.14 (FIX8): the first production figure, label first or figure first, that can be a year's production
    for rx in (_RE_PROD, _RE_PROD_BEFORE, _RE_PROD_PER_YEAR):
        for m in rx.finditer(flat):
            if rx is _RE_PROD_PER_YEAR and _RE_PROD_NOT_OUTPUT.search(flat[max(0, m.start() - 80):m.start()]):
                continue
            v, unit = _production(m)
            if v is not None:
                out["annual_production"], out["production_unit"] = v, unit
                break
        if out["annual_production"] is not None:
            break
    return out


# ---------------------------------------------------------------- does this release state economics
_RE_CUR_MARK = re.compile(r"(?i)(?<![A-Za-z])(CA\$|C\$|CAD|US\$|USD|A\$|AUD)")


_RE_CUR_STATED = re.compile(r"""(?ix)
    \b(?:all|unless\s+otherwise)[^.\n]{0,70}?
    \b(?:amounts?|figures?|dollars?|currency|values?|costs?)\b[^.\n]{0,40}?
    \b(?:in|are\s+in|expressed\s+in|stated\s+in|reported\s+in)\s+
    (?P<cur>canadian|cdn|CAD|C\$|CA\$|U\.?S\.?|US\$|USD|United\s+States|
       australian|A\$|AUD)\b""")


def stated_currency(text):
    """The currency a release says it reports in.

    Westhaven writes 'All amounts are in Canadian Dollars unless otherwise noted' directly under
    a headline whose only currency marks are US gold prices. Counting marks makes that release
    American; reading the sentence makes it what it says it is."""
    m = _RE_CUR_STATED.search(text or "")
    if not m:
        return None
    c = re.sub(r"[\s.]", "", m.group("cur")).upper()
    if c.startswith(("CANADIAN", "CDN", "CAD", "C$", "CA$")):
        return "CAD"
    if c.startswith(("US", "U.S", "UNITEDSTATES", "USD")):
        return "USD"
    if c.startswith(("AUSTRALIAN", "A$", "AUD")):
        return "AUD"
    return None


_CUR_WORD = {"CDN": "CAD", "CAD": "CAD", "CA": "CAD", "C": "CAD",
             "US": "USD", "USD": "USD", "A": "AUD", "AUD": "AUD"}
# 'CDN$1.00=US$0.72'. The side written as one unit is the currency the model is denominated in;
# the other is what it is being converted to. Westhaven's two recaps carry no other mark at all
# -- their gold and silver prices are US$ assumptions -- so without this they read as American.
_RE_FX_BASE = re.compile(r"""(?ix)
    (?P<a>CDN\$?|CAD\$?|CA\$|C\$|US\$|USD\$?|A\$|AUD\$?)\s*
    1(?:\.0{1,2})?\s*(?:=|:|\sto\s|\sequals?\s)\s*
    (?P<b>CDN\$?|CAD\$?|CA\$|C\$|US\$|USD\$?|A\$|AUD\$?)\s*\d""")
# an exchange rate is a conversion, not a figure the release is reporting
_RE_FX_NEAR = re.compile(r"(?i)exchange\s+rate|\bFX\b|foreign\s+exchange")


def exchange_base(text):
    """The currency a release's model is in, when it states its exchange rate."""
    m = _RE_FX_BASE.search(text or "")
    if not m:
        return None
    return _CUR_WORD.get(re.sub(r"[$\s]", "", m.group("a")).upper())


def dominant_currency(text):
    """The currency a release is written in, for a figure that carries no mark of its own.

    Surge's economics table says '$ M' and nothing else; the release is in US dollars and says so
    everywhere around the table. Radisson is the warning attached to this: it states NPV and capex
    in C$ and cash cost and AISC in US$, so this is a FALLBACK for a figure with no mark, never an
    override of one that has its own."""
    marks = {"CA$": "CAD", "C$": "CAD", "CAD": "CAD", "CDN$": "CAD", "CDN": "CAD",
             "US$": "USD", "USD": "USD", "A$": "AUD", "AUD": "AUD"}
    counts = {}
    for m in _RE_MONEY.finditer(text or ""):
        cur_raw = (m.group("cur") or "").upper()
        if cur_raw not in marks or _is_unit_price(text, m.end(), (m.group("mult") or "").lower()):
            continue                      # Radisson reports in C$ and quotes gold in US$
        if _RE_FX_NEAR.search(text[max(0, m.start() - 60):m.start()]) or _RE_FX_BASE.search(
                text[max(0, m.start() - 20):m.end() + 20]):
            continue                      # 'CDN$1.00=US$0.72' is a rate, not a result
        k = marks[cur_raw]
        counts[k] = counts.get(k, 0) + 1
    if not counts:
        return None
    best = max(counts.values())
    winners = [k for k, v in counts.items() if v == best]
    return winners[0] if len(winners) == 1 else None


def economics_text(headline, body):
    """The part of the release to read for figures.

    Normally everything before the legal disclaimer. But Buffalo Potash states its whole PEA in a
    numbered footnote BELOW that disclaimer, and a cut that loses it loses the release. The
    disclaimer is cut to stop its vocabulary inventing a study, and it states no figures at all,
    so when the cut text yields nothing there is nothing to lose by reading the rest."""
    head = headline or ""
    cut = _repair(readable((body or "")[:TEXT_LIMIT]))
    if scenarios(head + "\n" + cut):
        return cut
    full = _repair((body or "")[:TEXT_LIMIT])
    return full if scenarios(head + "\n" + full) else cut


def states_economics(headline, body):
    """True when the release states a study's economics, not merely the words for them.

    Justin, 2026-09-18: the page shows any release stating real economics, tagged or not. The test
    is a figure attached to an NPV or an IRR, because the vocabulary on its own proves nothing --
    Century Lithium's permitting update names NPV, IRR, capital and operating costs and states not
    one number, and the forward-looking-statements paragraph of almost every release does the
    same, which is why readable() cuts it before any of this runs."""
    rows = scenarios((headline or "") + "\n" + readable(body))
    return any(r["npv_after_tax"] is not None or r["npv_pre_tax"] is not None
               or r["irr_after_tax_pct"] is not None or r["irr_pre_tax_pct"] is not None
               for r in rows)


# ---------------------------------------------------------------- the capital a sensitivity varies
# Justin, 2026-09-20: show both. Desert Gold's highlights and summary table state an initial
# capital of $15 million; the base row of its CAPEX sensitivity table says 20.9. Those are two
# different numbers in one document, and picking one silently is a judgement the page should not
# be making on the reader's behalf.
# A sensitivity table declares what it varies in the cell after 'Range':
#   'CAPEX Sensitivity | Range | CAPEX ($) | After Tax NPV (10%) ($M) | IRR | Payback'
# Desert Gold spells one of its two 'CAPX', so the test is a 'cap' prefix, not a word.
_RE_SENS_VAR = re.compile(r"(?i)sensitivity\s*\|\s*Range\s*\|\s*(?P<var>[^|]{1,28})\|")
# the unswung row: a bare zero followed by the value the table is varying
_RE_BASE_ROW = re.compile(r"(?<![\d.,%-])0\s*%?\s*\|?\s*(?P<num>\d[\d,]*(?:\.\d+)?)\b")


def capex_sensitivity_base(text, stated=None):
    """The capital cost at the unswung row of a CAPEX sensitivity table.

    Returned on the same scale as the stated capital, because a sensitivity table varies that
    same figure and writes it in whatever unit its header declares -- Desert Gold's header says
    'CAPEX ($)' and its values are millions. When no scale makes the two the same figure, this
    returns nothing rather than guessing."""
    flat = " | ".join(segments(text or ""))
    for m in _RE_SENS_VAR.finditer(flat):
        if not re.match(r"(?i)\s*\(?\s*cap", m.group("var")):
            continue
        b = _RE_BASE_ROW.search(flat[m.end():m.end() + 600])
        if not b:
            continue
        try:
            v = numval(b.group("num"))
        except ValueError:
            continue
        if not stated:
            return v * 1e6 if v < 10000 else v
        for k in (1.0, 1e3, 1e6, 1e9):
            if 0.2 <= (v * k) / stated <= 5.0:
                return v * k
        return None
    return None
