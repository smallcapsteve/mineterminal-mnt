"""Economic studies extractor, facts-store version (ECON_V1).

The new source of the Economic Studies page once it passes the accuracy gate. Written against the
50-release set Justin confirmed on 2026-09-20 (53 rows).

What this reader does, and why each of them is a rule rather than a preference:

  1. ONE RECORD PER SCENARIO (Justin, 2026-09-18), with pre-tax and after-tax as columns on the
     same record. A study states four to six numbered outcomes -- Canagold names four cases,
     Doubleview states three flowsheets at two price decks -- and the page that shows one of them
     is showing the one the company chose to headline.
  2a. WHERE A RELEASE STATES ITS CAPITAL TWO WAYS, BOTH ARE SHOWN (Justin, 2026-09-20): the
     figure the release states, and the base row of its CAPEX sensitivity table.
  2. A SCENARIO IS A NAMED CASE (Justin, 2026-09-20). Low, Base, High, Spot, A1, A2, B, a price
     deck. A row identified only by a percentage swing is a sensitivity sweep, and Desert Gold's
     three sweeps would otherwise publish twenty-two rows for a study with two cases.
  3. ANNOUNCED OR BACKGROUND. Most releases that state economics are restating an old study while
     announcing something else. A page that does not separate them is a page where a five-year-old
     PEA outranks this morning's feasibility study.
  4. THE STUDY BELONGS TO WHOEVER IT IS ABOUT, not to whoever issued the release. Peloton (PMC.CN)
     relays Surge's webinar and quotes Surge's Nevada North PEA; published under PMC that is a
     nine-billion-dollar project credited to the wrong company. The reader records the company a
     release credits the study to (owner_name); the publisher, which knows the issuer, leaves out a
     study that is plainly someone else's. Surge's own release already carries it.
  5. TAG PLUS DETECTION (Justin, 2026-09-18). The page shows any release stating real economics,
     whether or not the categoriser tagged it.

  6. NOT EVERY NPV IS A MINING STUDY OF THE COMPANY'S OWN (1.0.10, Justin 2026-09-29: "drop bad, label rest"). A paid
     article or sector commentary, an oil and gas reserve report's NPV-10 (not a mine's natural-gas power or a lithium
     brine in an oil field: Mt Todd, E3, Smackover), a lawsuit's valuation and figures under "In other industry
     developments" (not a company's own "In other news") are not rows; restated studies that remain are labelled "mentioned in" by the
     pages. Also 1.0.10: a flattened "Metric Pre-Tax After-Tax" table is read by column; a table's "K US$" / "USD MM"
     header scales its cells; "Tasiast 24k" and "1.1 million tonnes" are not money; a PDF's "mi llion" and
     "US$12 3.1 million" are rejoined; a by-product's price ("Ag: $23/oz") does not name a case; the same scenario
     stated twice at one price is one row; a scoping study is a PEA and a bankable study an FS.
  7. ACC150 QUICK FIX (1.0.11, 2026-09-30; economics.py only, econ_core.py untouched). Rows: a row named only by a price
     beside the base case is dropped when the release marks it as a point on a sensitivity curve -- a change ('the
     NPV increases to', 'a 20% increase in metal prices'), an aside ('($1.75 billion at $1,500/oz gold)'), a sensitivity
     heading or 'leveraged to the gold price', or the base case's own price -- unless the words beside it name a case
     (spot, current, upside, 'A second case', 'as of <date>', 'reserve price') or the release calls it a higher or lower
     price of its own ('At a higher gold price of US$3,000 per ounce, the after-tax NPV increases to ...', Justin's key:
     a higher-price case stated in prose); a bare price stated as a result in its own right stays a row. An IRR equal to the discount rate, of 0%, or on the wrong
     side of the rate for its NPV is the rate, not a return; an after-tax IRR copied from the pre-tax one is re-read
     beside the after-tax NPV. One scenario name is one row. Figures spelled in a URL slug are not stated. Whose study:
     a royalty or streaming issuer and a release relaying another company's release state no study of their own.
     Context: a back-reference to a resource estimate, deal or property is not a recap; a headline about another kind
     of study, or commissioning/tendering one, is not an announcement; a headline announcing results in words
     econ_core does not read, or a lead announcing 'the results of' / 'the completion of' a study, is; a reference whose
     own sentence names nothing ('please see the news release dated ...') follows the sentence before it. Currency: 'All
     results herein are reported in Canadian dollars'. Restated studies of the company's own project stay 'background'
     rows (Justin 2026-09-29).
  8. FIX4 (1.0.12, 2026-10-02; economics.py only, econ_core.py untouched). Rows the core misses: a case the release names in
     words the core's case vocabulary does not hold ('In the flotation only scenario ... NPV (8%) of $863 million',
     'alternative Toll Milling development option with after-tax NPV5% of C$197 million', '... NPV of ~US$2.2 billion ...
     pursuant to the incentive price forecast') is a row when its NPV is on no row yet and the case word belongs to that
     statement; a payback stated only in that case's clause leaves the base case. Text the core misreads: a word a PDF split
     ('di scount'), a bullet glyph the core does not split on ('\u25cf' -- one '- 65%' in the run-on list read as a sweep), and
     metres written 'm' ('a 19,000 m drill program' read as a US$19 billion NPV). Wrong rows: money whose nearest label is
     another metric ('EBITDA of $233 million, after-tax NPV of $803 million') is not the NPV and the NPV is re-read from the
     label after it; a figure every mention of which sits in a sentence about another named company (a neighbour, an
     investee, a former employer; not the firm that prepared the study) is not the issuer's study; two rows at one price
     that share a figure, or of which one has no NPV, are one scenario (the row reading both tax bases apart is kept); a row
     named only by a price at another discount rate than the base case's, on the same commodity, is a rate-sensitivity
     point; a holder's attributable share of the NPV is not a case.
  9. FIX5 (1.0.13, 2026-10-04; economics.py only, econ_core.py untouched). Mine life written in words ('a nine year mine
     life', 'Life of mine is forecast at nine years'), with a hyphenated label ('life-of-mine of 11.2 years'), as an
     operating life, or as the mine's 'N-year life'. Payback: the study's after-tax payback where the core has none or took
     a pre-tax or sensitivity one, including 'payback of initial capital within 2 years' and 'a 1.53-year payback (1.82
     year after-tax)'. Tax basis: an unlabelled IRR takes its sentence's basis, a tax word written after the figures
     governs them, a bracketed figure on the other basis is that basis ('34.1% (25.2% post-tax)'). A rounded headline
     figure is replaced by the one figure in the results table that rounds to it. Currency: the release's own statement
     read across a line break or 'in thousands of US dollars', else the NPV label's unit ('(US$ millions)', '(M CAD)').
     Text: U+2010 hyphens, 'Ta x', 'I RR', 'pa yback', 'Pre - Tax', '3. 6 years', 'IRR1'. Capital: '$6 92 million'
     rejoined, direct/indirect capital costs are components. 'Cashflow' is another metric. A release restating several
     studies gives each row its own sentence's mine life and capital.
  9. FIX8 (1.0.14, 2026-10-06; econ_core.py only, these tests added). Impossible operating figures, fixed where they are
     read: annual production is the number the label states, in a unit ('in the first 5 years' was stored as 5, Northcliff's
     '598,000 MTU' as 598 billion tonnes, '$1.8 billion after-tax NPV' as production) and inside a range a year's output can
     be; throughput is ore through a plant, not a product's output ('248tpa Dysprosium', '100 tonnes per year of lithium
     carbonate') or a mining rate ('81.0 Mtpa'); a unit cost is a whole number ('Cost1, $/oz 1,593' was $1/oz), read from a
     table's '$/oz' header, keeps its sign ('negative $121/lb') and names its commodity ('/lb Mo', '/t LCE').

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per scenario (ordinal 0..n-1)
to_prediction(records) -> dict|None    what the accuracy judge compares

Self-tests: python3 -m portal.extractors.economics
"""
from __future__ import annotations

import re

from portal import facts as F
from portal.extractors import econ_core as C
from portal import fingerprint as FP
from portal import project_names as PN

NAME = "economics"
VERSION = "1.0.14"  # 2026-10-06 FIX8: throughput, annual production and unit costs that cannot be right (econ_core; b: without losing the real ones written as 207koz, 149,000 ozs, more than, per year, $US892/oz1, per ton); 2026-09-30: ACC150 quick fix (sweep points, rate read as IRR, duplicate rows, context, whose study, study type); 2026-10-02: FIX4 (named cases the core misses, another company's study, other metrics read as the NPV, one price written twice, rate sweeps, PDF-split words and bullets, metres); 2026-10-04 FIX5: mine life in words or hyphenated, payback (after-tax, of initial capital, not a sweep), figures under the wrong tax basis, rounded figures stated exactly in the table, currency the release states, more PDF-split words, split or component capital, each restated study's own mine life and capital
KIND = "economic_study"
TAG = "Economic Studies"
TEXT_CAP = 20000

# the per-scenario columns, in the order the page shows them
NUM_FIELDS = ("discount_pct", "npv_pre_tax", "npv_after_tax", "irr_pre_tax_pct",
              "irr_after_tax_pct", "payback_years", "initial_capex", "capex_sensitivity",
              "opex", "aisc", "mine_life_years", "throughput_tpd", "annual_production")
TXT_FIELDS = ("scenario", "study_type", "currency", "context", "basis", "project",
              "opex_unit", "aisc_unit", "production_unit")


# Every row the reader can produce hangs off an NPV or an IRR, so a release that never mentions
# either states no economics. The facts runner puts all ~43,600 approved releases through every
# registered reader, and this check is what keeps the other 42,500 cheap.
_RE_ANY_ECON = re.compile(r"(?i)NPV|net\s+present\s+value|\bIRR\b|internal\s+rate\s+of\s+return")


# 1.0.10 (Justin, 2026-09-29: "drop bad, label rest"): a paid article or sector commentary is not the company's own
# release (Rua's promoted recaps of its Auld Creek PEA; American News Group quoting Perpetua's Stibnite study under RUA);
# an oil and gas release's NPV-10 of a reserve report (Journey, Trillion) and a claim's valuation (Royalties Inc.'s lawsuit)
# are not mining studies; and figures under 'In other industry developments' are other companies'.
_RE_PAID = re.compile(r"(?i)issued\s+on\s+behalf\s+of|provided\s+by\s+[\w .]{2,40}?\s+on\s+behalf\s+of|companies\s+mentioned|"
                      r"(?:news|sector|market)\s+commentary|\banalyst\s+note\b|paid\s+advertis|\bsponsored\s+content")
_RE_OIL_GAS = re.compile(r"(?i)\bMMbbls?\b|\bbbl/d\b|\bboe(?:/d)?\b|\bmmcf|\bbcf\b|contingent\s+resources?|prospective\s+resources?|"
                         r"\bCOGEH\b|\bNI\s+51-101\b|\bDuvernay\b|crude\s+oil|natural\s+gas|\bnet\s+pay\b|oil\s+(?:field|pay|wells?)")
_RE_MINING_WORDS = re.compile(r"(?i)NI\s*43-101|mineral\s+(?:resources?|reserves?)|\blithium\b|\bLCE\b|\bounces\b|\bg/t\b|\bore\b|"
                              r"\bmill(?:ing)?\b|\bconcentrate\b|\bopen[\s\-]+pit\b|\bmine\b")
_RE_CLAIM = re.compile(r"(?i)\blawsuit|\blitigation|\barbitration|\bdamages\b|\bcriminal\b|\b(?:estimated|total)\s+claim\b|\bclaim\s+(?:amount|value)\b")   # not 'mining claims' 
_RE_OTHER_NEWS = re.compile(r"(?i)\bin\s+other\s+industry\s+(?:news|developments)\b|\bother\s+industry\s+developments\b")   # not a company's own 'In other news' (GQC)


def _claim_figure(flat, value):
    if not value:
        return False
    rx = C._fig_pattern(value)
    if rx is None:
        return False
    hits = list(rx.finditer(flat))
    return bool(hits) and all(_RE_CLAIM.search(flat[max(0, m.start() - 400):m.end() + 300]) for m in hits)


def _same_deck(a, b):
    pa = [float(x.replace(",", "")) for x in re.findall(r"\$\s*([\d,]+(?:\.\d+)?)", a or "")]
    pb = [float(x.replace(",", "")) for x in re.findall(r"\$\s*([\d,]+(?:\.\d+)?)", b or "")]
    if not pa or not pb:
        return True
    return abs(pa[0] - pb[0]) <= 0.01 * max(pa[0], pb[0])


def not_own_study(headline, body):
    """1.0.10: the reason a release's economics are not a mining study of its own, or None."""
    lead = (headline or "") + " " + " ".join((body or "")[:900].split())
    if _RE_PAID.search(lead):
        return "paid_article"
    blob = (headline or "") + " " + (body or "")[:TEXT_CAP]
    og = len(_RE_OIL_GAS.findall(blob))
    if og >= 3 and len(_RE_MINING_WORDS.findall(blob)) < 2 * og:
        return "not_mining"      # a mine's natural-gas power or a lithium brine's oil-field wells is still a mining study (Mt Todd, E3, Smackover)
    # 1.0.11: a royalty or streaming company restating its operators' studies (whose study is it?)
    lead2 = " ".join((body or "")[:1500].split())
    sd = _RE_SELF_DEF.search(lead2)
    if sd and _RE_ROYALTY_CO.search(lead2[max(0, sd.start() - 90):sd.start()]):
        return "royalty_holder"
    # 1.0.11: another company's release, relayed (whose study is it?)
    rl = _RE_RELAYS.search(lead2)
    if rl:
        own = " ".join(lead2[max(0, sd.start() - 90):sd.start()].split()[-5:]) if sd else ""
        if not own or not C.same_company(rl.group("co"), own):
            return "relayed_release"
    return None


# ------------------------------------------------------------------ 1.0.11 (ACC150 quick fix, 2026-09-30)
# A link is not a statement. A release that links its earlier study release has the old figures spelled in the
# URL slug ('...-us-501m-after-tax-npv5-21-irr-48-month-payback/'), and read as text they became a row.
_RE_URL = re.compile(r"(?:https?://|www\.)\S+|\S*[a-z0-9](?:-[a-z0-9]+){4,}\S*")

# a royalty or streaming company's portfolio update recaps its operators' studies: the lead defines the issuer
# ('... Royalties Ltd (the "Corporation" or ...)', '... Royalty & Streaming Ltd. ("..." or the "Company")')
_RE_SELF_DEF = re.compile(r"\([^()]{0,60}?(?:\bthe\s+)?[\"\u201c\u201d]?\s*\b(?:Company|Corporation|Issuer)\b[^()]{0,40}\)")
_RE_ROYALTY_CO = re.compile(r"(?i)\broyalt(?:y|ies)\b|\bstreaming\b")

# a release relaying another company's release: '... ("the Company") advises that <Other> Inc. (TSX-V: X), a related
# company, has released the results of ...', '... is pleased to announce that <Other> Inc., an affiliated company, has released'
_RE_RELAYS = re.compile(r"\b(?:advises|announces?|announced|is\s+pleased\s+to\s+announce|reports?)\s+that\s+"
                        r"(?P<co>[A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,4}?\s+(?:Inc|Corp|Corporation|Ltd|Limited|LLC|plc)\b\.?)"
                        r"[^.]{0,80}?\bhas\s+(?:released|announced|completed|published|filed)\b")

def _fig_rx(v):
    """C._fig_pattern, plus the thousands-separated form of a figure with decimals ('$1,822.4 million')."""
    base = C._fig_pattern(v)
    alts = [base.pattern] if base is not None else []
    for div, unit in ((1e9, r"(?:billion|bn|B)\b"), (1e6, r"(?:million|mm|M)\b")):
        if v >= div * 1000:
            t = "%.10g" % (v / div)
            if "." in t:
                ip, dp = t.split(".")
                alts.append(r"(?<![\d.,])" + re.escape("{:,}".format(int(ip)) + "." + dp) + r"\s?" + unit)
    return re.compile("|".join(alts)) if alts else None


# a clause, for the sweep test: a sentence end, a bullet or a blank line closes it (a semicolon does not --
# 'Enhanced case at $4,500 per ounce gold: cash costs ...; post-tax NPV (5%) of $841 million' is one case)
_RE_CLAUSE_END = re.compile(r"[.!?](?=\s+[A-Z(\u2022])|[\u2022\uf0b7]|\n\s*\n|\n\s*o\s+(?=[A-Z])")
# what a row named only by a price is, going by the words around its figure
_RE_SWEEP_CHANGE = re.compile(r"(?i)\b(?:increas|ris|grow|improv|climb|jump|lift|boost|decreas|fall|drop|declin|reduc)\w*\b[^.;\n]{0,45}$")
_RE_SWEEP_SWING = re.compile(r"(?i)\d\s*%\s+(?:increase|decrease|rise|drop|higher|lower)\b")
_RE_CASE_CUE = re.compile(r"(?i)\b(?:case|scenario|spot|current|upside|downside|consensus|street|trailing|incentive|"
                          r"as\s+of|reserve\s+price)\b")
_RE_BASE_CASE = re.compile(r"(?i)\bbase[\s-]+case\b")
# the company presenting a second price as a case of its own: 'At a higher gold price of US$3,000 per ounce, the
# after-tax NPV increases to US$41 million' is its High case in words (Justin's key), not a point read off a curve
_RE_PRICE_CASE = re.compile(r"(?i)\b(?:a|an|the)\s+(?:higher|lower|elevated|reduced)\s+(?:[a-z]+\s+){0,2}?prices?\s+(?:of|at)\b")
_RE_SENSITIVITY = re.compile(r"(?i)\bsensitivit(?:y|ies)\b|\bleverag\w*\s+to\s+(?:the\s+)?(?:\w+\s+)?prices?\b")   # 'Highly leveraged to the gold price'
_RE_ASIDE = re.compile(r"\(\s*(?:US|C|CA|A)?\$?\s*$")        # '($1.75 billion at $1,500/oz gold)' -- the figure opens an aside
_RE_ROW_NAMED = re.compile(r"(?i)\b(?:base|spot|low|high|medium|consensus|upside|downside|current|enhanced|case|scenario|"
                           r"option|phase|alternative|street|trailing|incentive|optimi[sz]ed|expan\w*|bull\w*|bear\w*|reserve)\b")
_RE_ROW_BASE = re.compile(r"(?i)\bbase\b")


def _clause_around(flat, a, b):
    lead = flat[max(0, a - 250):a]
    ends = list(_RE_CLAUSE_END.finditer(lead))
    if ends:
        lead = lead[ends[-1].end():] if len(lead) - ends[-1].end() >= 40 else lead[-150:]   # a table cell: the lines above head it
    tail = flat[b:b + 200]
    e = _RE_CLAUSE_END.search(tail)
    return lead, (tail[:e.start()] if e else tail)


def _sweep_point(flat, row, base):
    """1.0.11: a row named only by a price, beside the release's base case, is a point on a sensitivity curve when the
    release says so: its figure is a change ('At $4.50/lb copper, the after-tax NPV increases to $103.3 million',
    'Post-tax NPV rises to $239M at US$3,250 per oz', 'A 20% increase in metal prices ... increased the NPV to'), an
    aside to the base figure ('$1.23 billion pre-tax NPV5% ($1.75 billion at $1,500/oz gold)'), or it sits under a
    sensitivity heading ('Sensitivities ... At a gold price of US$3,000/oz ... an after-tax NPV of $1,381 million').
    A row at the base case's own price is not another case at all. The words beside the figure can still make it
    a case: 'at approximately the current price of US$3,350', 'Enhanced case at $4,500', 'A second case evaluated
    at $4.25/lb', 'metal prices as of January 22'. A price the release itself calls a higher or lower price of its own
    ('At a higher gold price of US$3,000 per ounce, the after-tax NPV increases to US$41 million') is a case even
    though its figure is a change: Justin's answer key keeps it as a row. A bare price stated as a result in its own
    right, with none of these, stays a row too."""
    weak = bool(C._RE_DECK.search(base.get("scenario") or "")) and _same_deck(base.get("scenario"), row.get("scenario"))
    change = named = priced = False
    v = row.get("npv_after_tax") or row.get("npv_pre_tax")
    rx = _fig_rx(abs(v)) if v else None
    for m in (rx.finditer(flat) if rx else ()):
        lead, tail = _clause_around(flat, m.start(), m.end())
        change = change or bool(_RE_SWEEP_CHANGE.search(lead) or _RE_SWEEP_SWING.search(lead + " " + tail))
        named = named or bool(_RE_CASE_CUE.search(_RE_BASE_CASE.sub(" ", lead + " " + tail)))
        priced = priced or bool(_RE_PRICE_CASE.search(lead))
        above = flat[max(0, m.start() - len(lead) - 400):m.start()]
        weak = weak or bool(_RE_SENSITIVITY.search(above) or _RE_ASIDE.search(lead))
    return not priced and (change or (weak and not named))


def _drop_sweep_points(flat, rows):
    # the base case is the first scenario the release states; a row the reader calls 'base case' may only be one
    # whose own clause named nothing
    if len(rows) < 2:
        return rows
    base = rows[0]
    return [r for r in rows if r is base or _RE_ROW_NAMED.search(r.get("scenario") or "")
            or not C._RE_DECK.search(r.get("scenario") or "") or not _sweep_point(flat, r, base)]


def _fix_rates(row):
    """1.0.11: an IRR equal to the discount rate is the rate, not the return -- at an IRR equal to the rate the
    NPV is nil, and 'NPV (5%) of $941 million ... IRR' does not state a 5% IRR. The same holds for an IRR on the
    wrong side of the rate for the NPV beside it, and for an IRR of exactly 0%."""
    d = row.get("discount_pct")
    for irr_k, npv_k in (("irr_after_tax_pct", "npv_after_tax"), ("irr_pre_tax_pct", "npv_pre_tax")):
        irr = row.get(irr_k)
        if irr is None:
            continue
        npv = row.get(npv_k)
        if irr == 0.0:
            row[irr_k] = None
        elif d is not None and abs(irr - d) < 0.051:
            row[irr_k] = None
        elif d is not None and npv is not None and ((npv > 0 and irr < d) or (npv < 0 and irr > d)):
            row[irr_k] = None
    return row


_RE_IRR_AFTER_FIG = re.compile(r"(?i)[^.\n\u2022]{0,60}?\b(?:IRR|internal\s+rate\s+of\s+return)\b[^%\d.]{0,25}(\d{1,3}(?:\.\d+)?)\s*%")


def _fix_copied_irr(flat, row):
    """1.0.11: 'Pre-tax NPV5% of C$921M, IRR 30.5% ... After-tax NPV5% of C$577M, IRR 23.5%' -- when the two NPVs
    differ the two IRRs cannot be the same figure; the after-tax IRR is the one stated with the after-tax NPV."""
    pre, post = row.get("npv_pre_tax"), row.get("npv_after_tax")
    ip, ia = row.get("irr_pre_tax_pct"), row.get("irr_after_tax_pct")
    if None in (pre, post, ip, ia) or ip != ia or not (0 < post < 0.95 * pre):
        return row
    rx = _fig_rx(post)
    found = None
    for m in (rx.finditer(flat) if rx else []):
        g = _RE_IRR_AFTER_FIG.match(flat, m.end())
        if g and float(g.group(1)) != ip:
            found = float(g.group(1))
            break
    row["irr_after_tax_pct"] = found
    return row


_SIG = ("npv_pre_tax", "npv_after_tax", "irr_pre_tax_pct", "irr_after_tax_pct")


def _merge_same_name(rows):
    """1.0.11: two rows under the one scenario name on the one basis are one scenario written twice (a headline
    figure, a table row, a figure read under the other tax label); the row stating more figures is kept, and it
    takes the other's figures where it has none."""
    out = []
    for r in rows:
        twin = next((u for u in out if u.get("scenario") == r.get("scenario") and u.get("basis") == r.get("basis")), None)
        if twin is None:
            out.append(r)
            continue
        if sum(r.get(k) is not None for k in _SIG) > sum(twin.get(k) is not None for k in _SIG):
            out[out.index(twin)] = r
            r, twin = twin, r
        for k, v in r.items():
            if v is not None and twin.get(k) is None and k not in _SIG:
                twin[k] = v
    return out


_RE_POINTS_AT_STUDY = re.compile(r"(?i)NPV|IRR|net\s+present|econom\w+|\bPEA\b|\bPFS\b|\b[DB]FS\b|feasibility|stud(?:y|ies)|results?")
_RE_POINTS_ELSEWHERE = re.compile(r"(?i)resources?\b|\bMRE\b|\breserves?\b|\bestimate|\bagreement|\binterest\b|\boption\b|drill|"
                                  r"acqui\w+|financing|placement|offering|permit|deposits?\b|propert(?:y|ies)\b")
_RE_ECON_WORDS = re.compile(r"(?i)\bNPV|\bIRR\b|net\s+present|econom\w+|payback|cash[\s-]+flows?\b|capital\s+(?:costs?|intensity|efficien\w*)|"
                            r"\b(?:PEA|PFS|DFS|BFS)\b|feasibility")
def _back_ref_elsewhere(text):
    """1.0.11: the text with every strong back-reference blanked out that points at something other than the
    study -- '(see news release dated May 10, 2018)' after a resource estimate or an option agreement, 'No material
    changes were made to the Mineral Resource ...' -- which say nothing about whether the economics are new. What a
    reference points at is what is written right beside it; only when that names nothing is its sentence read."""
    out = text
    for m in reversed(list(C._RE_BACK_STRONG.finditer(text))):
        if _RE_POINTS_AT_STUDY.search(m.group(0)):
            continue             # 'results previously announced', 'supports the ... results'
        lead = text[max(0, m.start() - 200):m.start()]
        cut = max(lead.rfind(". "), lead.rfind("\n\n"))
        lead = lead[cut + 1:] if cut >= 0 else lead
        tail = text[m.end():m.end() + 60]
        stop = tail.find(". ")
        tail = tail[:stop] if stop >= 0 else tail
        near = " ".join(lead.split())[-60:] + " " + " ".join(tail.split())[:60]
        if not _RE_POINTS_ELSEWHERE.search(near) and (_RE_POINTS_AT_STUDY.search(near) or _RE_POINTS_AT_STUDY.search(lead + " " + tail)):
            continue
        # a reference whose own sentence names nothing ('For additional information, please see the news release
        # dated ...') refers to what the sentence before it was about: when that is the economics ('the additional
        # metrics below ... capital intensity, cash flow generation and payback'), the figures are a recap
        if cut >= 0 and not _RE_POINTS_ELSEWHERE.search(lead + " " + tail):
            prev = text[max(0, m.start() - len(lead) - 300):m.start() - len(lead)].rstrip(" .")
            pcut = max(prev.rfind(". "), prev.rfind("\n\n"))
            prev = prev[pcut + 1:] if pcut >= 0 else prev
            if _RE_ECON_WORDS.search(prev) and not _RE_POINTS_ELSEWHERE.search(prev):
                continue
        out = out[:m.start()] + " " * (m.end() - m.start()) + out[m.end():]
    return out


# 1.0.11: what a release says it reports in, in the wordings econ_core.stated_currency does not read: 'All results
# herein are reported in Canadian dollars', 'All amounts are Millions of Canadian Dollars' (a table note)
_RE_CUR_SAID = re.compile(r"""(?ix)
    \b(?:all|unless\s+otherwise)[^.\n]{0,70}?
    \b(?:results?|amounts?|figures?|numbers?|dollars?|values?)\b[^.\n]{0,40}?
    \b(?:(?:are\s+)?(?:in|expressed\s+in|stated\s+in|reported\s+in|presented\s+in)|are\s+(?:millions?|thousands?|billions?)\s+of)\s+
    (?P<cur>canadian|cdn|CAD|C\$|CA\$|U\.?S\.?|US\$|USD|United\s+States|australian|A\$|AUD)\b""")


def _said_currency(text):
    return _said_currency_rx(_RE_CUR_SAID, text)


def _head_kinds(headline):
    h = headline or ""
    pfs = [m.span() for m in C._RE_PFS.finditer(h)]
    kinds = {"PFS"} if pfs else set()
    if any(not any(a <= m.start() < b + 3 for a, b in pfs) for m in C._RE_FS.finditer(h)):
        kinds.add("FS")
    if C._RE_PEA.search(h):
        kinds.add("PEA")
    return kinds


# a headline announcing results in words econ_core's headline test does not read: 'Completes ... PEA', 'Reports ...
# Results of ... Scoping Study', '... Mine Plan ... With an NPV5% of $824M' (NPV welded to its rate)
_RE_HEAD_ANN2 = re.compile(r"(?i)\b(?:announc|deliver|report|present|releas|unveil|publish|complet|show)\w*\b[^\n]{0,90}?"
                           r"(?:\bNPV\d*|\bIRR\b|\bscoping\s+study|\b(?:PEA|PFS|DFS|BFS)\b|feasibility\s+study|economic\s+assessment)")


_STUDY_WORDS = (r"(?:PEA|PFS|DFS|BFS|preliminary\s+economic\s+assessment|pre[\s-]?feasibility\s+study|feasibility\s+study|"
                r"bankable\s+(?:project\s+)?study|scoping\s+study)")
# the company's own opening sentence announcing the study, when the headline says nothing usable about it ('Kinross
# ... today announced the results of a pre-feasibility study', '... is pleased to announce the completion of a bankable
# project study', '... is pleased to announce the results of a positive Preliminary Economic Assessment')
_RE_LEAD_ANN = re.compile(r"(?i)\bannounc\w*\s+(?:that\s+it\s+has\s+completed\s+|the\s+(?:positive\s+)?(?:results?|completion)\s+of\s+)"
                          r"[^.]{0,60}?\b" + _STUDY_WORDS + r"\b")
# a headline about commissioning or tendering the next study ('Commissions Update of the PEA')
_RE_HEAD_NEXT = re.compile(r"(?i)\b(?:commission(?:s|ed|ing)?|tender(?:s|ed|ing)?)\b")


def _context(head, text, study):
    """announced / background (1.0.11 on top of econ_core.release_announces)."""
    ann = C.release_announces(head, text)
    if not ann:
        t2 = _back_ref_elsewhere(text)
        if t2 != text:
            ann = C.release_announces(head, t2)
        quiet = not C._RE_HEAD_OTHER.search(head) and not C._RE_BACK_STRONG.search(C.readable(t2)[:6000])
        if not ann and quiet and (_RE_HEAD_ANN2.search(head) or _RE_LEAD_ANN.search(" ".join(C.readable(t2)[:1500].split()))):
            ann = True
    if ann and _RE_HEAD_NEXT.search(head):
        ann = False
    # a headline about a different kind of study -- 'Tenders Proposals for New Feasibility Study' over the
    # PEA's figures, 'Announces Feasibility Study is Underway' over the PFS's -- is not announcing these figures
    if ann and study:
        hk = _head_kinds(head)
        if hk and study not in hk:
            ann = False
    return "announced" if ann else "background"


# ------------------------------------------------------------------ 1.0.12 (FIX4, 2026-10-02)
# A word a PDF split across a gap ('Net Present Value with 5% di scount rate') hides the rate from the core, which then
# reads the 5% as the return and the row is lost. The words an NPV statement leans on are rejoined; 'mi llion' already is.
_SPLIT_WORDS = ("discount", "present", "internal", "economic", "feasibility", "assessment")
_RE_SPLIT_WORD = re.compile(r"(?i)\b(?:" + "|".join(w[:i] + " " + w[i:] for w in _SPLIT_WORDS for i in range(2, len(w) - 1)) + r")\b")
# metres written 'm' are not millions: '... economic indicators of NPV and IRR. The Company is commencing a 19,000 m
# drill program' was read as a US$19 billion NPV
_RE_METRES = re.compile(r"(?<![$\d.,])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?m\b(?=\s*(?:of\s+)?(?:diamond\s+|core\s+|RC\s+)?"
                        r"(?:drill\w*|program\w*|campaign|holes?|step-?outs?|depth|deep|below|above|long|wide|thick|"
                        r"intervals?|strike|vertical|elevation|of\s+(?:drilling|core|trenching)))", re.I)


# a bullet drawn with a glyph the core does not split on ('\u25cf', '\u25aa', '\u25a0', '\u25e6', '\u27a2', '\u2713') runs a list of
# highlights into one clause, and one '- 65%' in it ('Assumed Purchase Prices of Concentrate - 65% of the contained gold
# value') made the whole list read as a sensitivity sweep: BacTech's pre-tax NPV and IRR were lost
_RE_BULLET_GLYPH = re.compile("[\u25cf\u25aa\u25a0\u25e6\u27a2\u2713]")


def _clean_body(body):
    body = _RE_BULLET_GLYPH.sub("\u2022", body)
    body = _fix5_text(body)                        # 1.0.13: more PDF-split words and hyphens
    body = _RE_SPLIT_WORD.sub(lambda m: m.group(0).replace(" ", ""), body)
    body = _fix5_life(body)                        # 1.0.13: a mine life in words or with a hyphenated label
    body = _fix5_capex(body)                       # 1.0.13: a split capital figure, a component of the capital
    return _RE_METRES.sub(lambda m: m.group(1) + " metres" if m.group(0)[-1] == "m" else m.group(0), body)


# ------------------------------------------------------------------ 1.0.13 (FIX5, 2026-10-04)
# TEXT: more of what a PDF does to the words the core leans on. A hyphen drawn as U+2010/U+2011 ('13\u2010year
# mine\u2010life', 'pre\u2010tax'); 'Pre - Ta x NPV8', 'I RR', 'pa yback', 'pay -back period'; a decimal split from its
# digit ('payback period of 3. 6 years'); a footnote digit welded to the IRR label ('an 18% IRR1'); 'Pre - Tax'.
_RE_TEXT_SPLITS = (
    (re.compile(r"[\u2010\u2011]"), "-"),
    (re.compile(r"(?i)\b(?:Ta\s+x|T\s+ax)\b"), lambda m: m.group(0)[0] + "ax"),
    (re.compile(r"(?i)\b(pre|post|after)\s+-\s*(tax)\b|\b(pre|post|after)\s*-\s+(tax)\b"),
     lambda m: "-".join(g for g in m.groups() if g)),
    (re.compile(r"\bI\s(RR)\b|\b(IR)\s(R)\b"), "IRR"),
    (re.compile(r"(?i)\bpa\s?y\s?(?:-\s?|\s-\s?)?b\s?a\s?c\s?k\b"),
     lambda m: m.group(0) if not re.search(r"[\s-]", m.group(0)) else m.group(0)[0] + "ayback"),
    (re.compile(r"(?<![\d.,])(\d{1,2})\.\s(\d)(?=\s*(?:-\s*)?(?:years?|yrs?|months?|%))"), r"\1.\2"),
    (re.compile(r"\b(IRR)\d\b(?!\s*%)"), r"\1 "),
)


def _fix5_text(body):
    for rx, rep in _RE_TEXT_SPLITS:
        body = rx.sub(rep, body)
    return body


# CAPEX: the capital figure the core reads first is not the initial capital when it is a PDF-split number ('Revised
# pre-production capital cost is now estimated to be $6 92 million', stated elsewhere as '$692 million') or a component of
# it ('Total Direct Capital Costs C$M 634.3 ... Total Initial Capital C$M 998.2': direct and indirect costs add up to it).
_RE_CAPEX_SPLIT = re.compile(r"((?:US|C|CA|A)?\$\s?)(\d{1,2}) (\d{1,3})(\s*(?:million|billion)\b)")
_RE_CAPEX_PART = re.compile(r"(?i)\b((?:total\s+)?(?:in)?direct)(\s+)capital(\s+costs?)\b")


def _fix5_capex(body):
    def join(m):
        j = m.group(2) + m.group(3)
        return m.group(1) + j + m.group(4) if re.search(r"(?<![\d.,])" + j + r"\s*(?:million|billion|M\b)", body) else m.group(0)
    body = _RE_CAPEX_SPLIT.sub(join, body)
    return _RE_CAPEX_PART.sub(lambda m: m.group(1) + m.group(3), body)


# LIFE: a mine life written in words or with a hyphenated label: 'over a seven-year mine life', 'support a nine year
# mine life', 'Life of mine is forecast at nine years', 'a total life-of-mine of 11.2 years', 'an initial 6-year
# life-of-mine (LOM)' -- the core reads only digits and 'life of mine' written with spaces.
_LIFE_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
               "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
               "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "twenty-five": 25, "thirty": 30}
_LIFE_LABEL = r"(?:mine|operating|production|LOM)[\s-]+life|life[\s-]+of[\s-]+(?:the\s+)?mine|LOM\b"
_RE_LIFE_HYPH = re.compile(r"(?i)(?:(?<=year\s)|(?<=year-)|(?<=years\s))(?:(life)-(of)-(mine)|(mine)-(life))\b|"
                           r"\b(?:(life)-(of)-(mine)|(mine)-(life))(?=\s*(?:\(\W*LOM\W*\)\s*)?(?:of|is|:|=|was)?\s*(?:approximately\s+)?\d)")
_RE_LIFE_WORD_BEFORE = re.compile(r"(?i)\b(" + "|".join(sorted(_LIFE_WORDS, key=len, reverse=True)) + r")(?=[\s-]+years?\b"
                                  r"[\s-]+(?:[a-z]+[\s-]+)?(?:" + _LIFE_LABEL + r"))")
_RE_LIFE_WORD_AFTER = re.compile(r"(?i)(\b(?:mine\s+life|life\s+of\s+mine)\s+(?:is|of|will\s+be)\s+(?:\w+\s+){0,2}?(?:at\s+)?)("
                                 + "|".join(sorted(_LIFE_WORDS, key=len, reverse=True)) + r")(?=\s+years?\b)")


# an operating life is the mine life ('six-year operating life'), and so is the life a sentence about the mine gives it
# ('The mine will have an 18-year life')
_RE_LIFE_OTHER = re.compile(r"(?i)(\b\d{1,2}(?:\.\d)?[\s-]+years?[\s-]+)operating(\s+life)\b|"
                            r"(\bmine\s+(?:will|would|could)\s+have\s+an?\s+\d{1,2}(?:\.\d)?[\s-]*years?[\s-]+)(life)\b")


def _fix5_life(body):
    body = _RE_LIFE_HYPH.sub(lambda m: " ".join(g for g in m.groups() if g), body)
    body = _RE_LIFE_WORD_BEFORE.sub(lambda m: str(_LIFE_WORDS[m.group(1).lower()]), body)
    body = _RE_LIFE_WORD_AFTER.sub(lambda m: m.group(1) + str(_LIFE_WORDS[m.group(2).lower()]), body)
    return _RE_LIFE_OTHER.sub(lambda m: (m.group(1) + "mine" + m.group(2)) if m.group(1) else (m.group(3) + "mine " + m.group(4)), body)


# A case the release names in words the core's case vocabulary does not hold -- 'In the flotation only scenario, the
# project has an after-tax NPV (8%) of $863 million', 'alternative Toll Milling development option with after-tax NPV5%
# of C$197 million', 'After-tax NPV of ~US$2.2 billion ... pursuant to the incentive price forecast'. The core folds such
# a clause into the base case or drops it; it is a scenario of its own when its NPV is on no row yet.
_RE_ALT_KIND = re.compile(r"(?i)\b(?:scenario|option|alternative|price\s+forecast|case)\b(?!\s+(?:to|agreement|holder|payment|"
                          r"price\s+of\s+C?\$?\s*[\d.]+\s+per\s+share))")
_ALT_SKIP = set("""the a an in of for this that these those its our their his her each every any one other same which under
    using with to and or at on by pursuant considering assuming when where as is was""".split())
_ALT_NOT_NAME = re.compile(r"(?i)^(?:base|spot|low|high|medium|upside|downside|consensus|current|sensitivit\w*|previous|prior|"
                           r"original|former|earlier|historic\w*|worst|best|business|investment|share|stock|purchase|earn\w*|"
                           r"[\d$%.,()-]+)(?:$|-)")       # 'base-case' too
_RE_NPV_WORD = re.compile(r"(?i)\bNPV\d*%?|net\s+present\s+value")
_RE_IRR_PCT = re.compile(r"(?i)\b(?:IRR|internal\s+rate\s+of\s+return)\b[^%\d.;]{0,30}?(\d{1,3}(?:\.\d+)?)\s*%|"
                         r"(\d{1,3}(?:\.\d+)?)\s*%\s+(?:(?:after|post|pre)[\s-]{0,2}tax\s+)?(?:IRR|internal\s+rate)")
_RE_PAYBACK_YRS = re.compile(r"(?i)\bpay[\s-]?back(?:\s+period)?\s+(?:of\s+|is\s+)?(?:approximately\s+|about\s+)?(\d{1,2}(?:\.\d+)?)\s*years?")
_RE_OWN_CAPEX = re.compile(r"(?i)\binitial\s+capital(?:\s+costs?)?\s+(?:of\s+|is\s+)?((?:US|C|CA|A)?\$\s?[\d,.]+\s*(?:million|billion|M\b|B\b))")
_RE_NOT_RESULT = re.compile(r"(?i)\bsensitivit|\bprevious|\bprior\b|\boriginal\b|\bhistoric|\bformer\b|\bsuperseded\b|"
                            r"\battributable\b|\d\s*%\s+(?:interest|share|ownership)\b")   # a holder's share of the NPV is not a case


def _big_money(text):
    return any(m.group("mult") for m in C._RE_MONEY.finditer(text or ""))


def _alt_name(clause, kind):
    """The words before the case word, back to the first stop word: 'Toll Milling development', 'flotation only',
    'incentive'; None when they name nothing of its own."""
    lead = clause[max(0, kind.start() - 60):kind.start()]
    words = re.findall(r"[\w$.,%-]+", lead if kind.start() <= 60 else lead.split(None, 1)[-1] if " " in lead else "")[-3:]
    keep = []
    for w in reversed(words):
        if w.lower() in _ALT_SKIP or not re.search(r"[A-Za-z]", w):
            break
        keep.insert(0, w)
    if not keep or any(_ALT_NOT_NAME.match(w.strip("-.,")) for w in keep):
        return None
    return " ".join(keep + [" ".join(kind.group(0).split())]).lower()


def _npv_windows(flat):
    """(npv match, its window): the text around one NPV label, cut at a sentence end and at the next or previous NPV
    label, so a run of unmarked bullets that unwrap() joined is still read one statement at a time."""
    ms = list(_RE_NPV_WORD.finditer(flat))
    for i, m in enumerate(ms):
        lo = max(ms[i - 1].end() + 25 if i else 0, m.start() - 160)
        hi = min(ms[i + 1].start() if i + 1 < len(ms) else len(flat), m.end() + 200)
        lead = flat[lo:m.start()]
        e = list(_RE_CLAUSE_END.finditer(lead))
        if e:
            lo += e[-1].end()
        e = _RE_CLAUSE_END.search(flat, m.end(), hi)
        if e:
            hi = e.start() + 1
        yield m, lo, flat[lo:hi]


def _named_cases(flat, rows, study):
    """1.0.12: rows for cases the release names in words the core does not read (see _RE_ALT_KIND)."""
    if not rows:
        return []
    have = [v for r in rows for v in (r.get("npv_after_tax"), r.get("npv_pre_tax")) if v]
    base = rows[0]
    out = []
    for npv, lo, cl in _npv_windows(flat):
        if len(out) >= 3:
            break
        if _RE_NOT_RESULT.search(cl) or _RE_SWEEP_SWING.search(cl) or C._RE_PRIOR_REPORTED.search(cl):
            continue
        at = npv.start() - lo
        kinds = [k for k in _RE_ALT_KIND.finditer(cl) if _alt_name(cl, k)]
        if not kinds:
            continue
        tail = cl[at + len(npv.group(0)):][:70]
        v, cur = C.money(tail)
        if not v or abs(v) < 1e6:
            continue
        mm = C._RE_MONEY.search(tail)
        if mm and C._is_unit_price(tail, mm.end()):
            continue
        if mm and _RE_OTHER_METRIC.search(tail[:mm.start()]):
            continue                     # 'NPV 5% and average annual EBITDA of US$88 million': the money is not the NPV
        fig_at = at + len(npv.group(0)) + (mm.end() if mm else 0)
        if _RE_SWEEP_CHANGE.search(cl[:at + len(npv.group(0)) + (mm.start() if mm else 0)]):
            continue                     # 'the flotation only NPV (8%) increases to $1.5 billion' -- a sweep point
        if any(abs(v - h) <= 0.02 * max(abs(v), abs(h)) for h in have):
            continue
        if C.figure_kind(flat, v) not in (None, study):
            continue
        # the case word has to belong to this statement: no other amount in millions lies between it and the figure
        # ('... after tax NPV5% of C$423 million and 47% IRR at US$1,900 per ounce gold Initial capital of C$144 million
        # Attractive alternative Toll Milling development option' -- the option is the next statement's)
        kinds = [k for k in kinds if not _big_money(cl[k.end():at] if k.start() < at else cl[fig_at:k.start()])]
        if not kinds:
            continue
        name = _alt_name(cl, min(kinds, key=lambda k: abs(k.start() - at)))
        deck = C.deck_in(cl)
        if deck and not C._RE_DECK.search(name):
            name += " " + " ".join(deck.group(0).split())
        tax = C.tax_basis(cl[max(0, at - 30):at + len(npv.group(0))]) or C.tax_basis(cl[:at]) or "after"
        row = {k: None for k in base}
        row.update(scenario=name, basis=C.value_basis(cl), currency=cur, payback_years=None,
                   discount_pct=C.discount_of(cl[at:]) or C.discount_of(cl) or base.get("discount_pct"))
        row["npv_pre_tax" if tax == "pre" else "npv_after_tax"] = v
        ir = _RE_IRR_PCT.search(cl, fig_at)
        if ir:
            row["irr_pre_tax_pct" if tax == "pre" else "irr_after_tax_pct"] = float(ir.group(1) or ir.group(2))
        pb = _RE_PAYBACK_YRS.search(cl, fig_at)
        if pb:
            row["payback_years"] = float(pb.group(1))
        cx = _RE_OWN_CAPEX.search(cl, fig_at)
        if cx:
            row["initial_capex"] = C.money(cx.group(1))[0]
        hk = _head_kinds(name)
        row["_kind"] = next(iter(hk)) if len(hk) == 1 else None    # 'the PEA case' beside a PFS's base case is the PEA's
        out.append(_fix_rates(row))
        have.append(v)
    # a payback stated only in a named case's clause is that case's, not the base case's
    for r in out:
        p = r.get("payback_years")
        if p is not None and len(re.findall(r"(?i)\bpay[\s-]?back[^.;]{0,40}?(?<![\d.])" + re.escape("%g" % p) + r"\s*years?", flat)) == 1:
            for b in rows:
                if b.get("payback_years") == p:
                    b["payback_years"] = None
    return out


# Money labelled as another metric is not the NPV: 'Average annual EBITDA of $233 million, after-tax NPV of $803 million'
# (1.0.13: 'Pre-tax Cashflow = CAD$709.4 million, NPV = CAD$385.1 million' -- cash flow written as one word)
# gave the row 233; 'Average Annual EBITDA (per year) $1,176 million $1,094 million' gave a second row 1,094. When every
# place a row's NPV is written has another metric as its nearest label, the NPV is re-read from the NPV label right
# after it, or left empty.
_RE_OTHER_METRIC = re.compile(r"(?i)\b(?:EBITDA|EBITA|EBIT|cash[\s-]*flows?|revenues?|sales|capex|opex|operating\s+costs?|"
                              r"(?:initial|sustaining|development|construction|project|pre-?production)\s+capital(?:\s+costs?)?|"
                              r"capital\s+costs?|net\s+income|earnings|profits?)\b")


def _fix_other_metric(flat, row, others):
    for k in ("npv_after_tax", "npv_pre_tax"):
        v = row.get(k)
        rx = _fig_rx(abs(v)) if v else None
        hits = list(rx.finditer(flat)) if rx else []
        if not hits:
            continue
        def other(m):
            back = flat[max(0, m.start() - 60):m.start()]
            o, n = list(_RE_OTHER_METRIC.finditer(back)), list(_RE_NPV_WORD.finditer(back))
            after = re.match(r"(?i)[\s)(\]|,]*(?:(?:pre|after|post)[\s-]{0,2}tax\s+)?\(?\s*(?:NPV|net\s+present\s+value)", flat[m.end():m.end() + 40])
            if after and C.money(flat[m.end() + after.end():m.end() + after.end() + 30])[0]:
                after = None              # 'EBITDA of $233 million, after-tax NPV of $803 million': that label is the next figure's
            return bool(o) and (not n or o[-1].start() > n[-1].end()) and not after   # '(C$315 million) NPV5%' names it
        if not all(other(m) for m in hits):
            continue
        new = None
        nxt = _RE_NPV_WORD.search(flat, hits[0].end(), hits[0].end() + 60)
        if nxt and C.tax_basis(flat[max(0, nxt.start() - 12):nxt.end()], "after" if k == "npv_after_tax" else "pre") == k[4:-4]:
            v2, _cur = C.money(flat[nxt.end():nxt.end() + 60])
            if v2 and abs(v2) >= 1e6 and not any(v2 in (o.get("npv_after_tax"), o.get("npv_pre_tax")) for o in others):
                new = v2
        row[k] = new
    return row


# Another company's study quoted in passing: the issuer's neighbour ('the adjacent Cypress Development Corp.'s Clayton
# Valley project ... giving the company a US$1.03B NPV'), a company it holds shares in ('Abrasilver Resource Corp. (TSX:
# ABRA) released results from its preliminary feasibility study ... US$494 million after-tax NPV'), or the owner of the
# ground next door ('CNC's Crawford Project where a preliminary economic assessment indicates ... NPV'). A figure is the
# issuer's own unless every place it is written is in such a sentence.
_CO_SUFFIX = r"(?:Corp(?:oration)?|Inc(?:orporated)?|Ltd|Limited|LLC|plc|S\.A|AG|Company)\b\.?"
_RE_OTHER_CO = re.compile(r"(?P<name>\b[A-Z][\w&'\u2019.-]*(?:[ \t]+[A-Z][\w&'\u2019.-]*){0,3}),?[ \t]+" + _CO_SUFFIX +
                          r"|(?P<pname>\b[A-Z][A-Za-z&-]{1,30})['\u2019]s\)?\s+(?:[A-Z][\w-]*\s+){0,3}(?:Project|project|Property|property|"
                          r"Deposit|deposit|Mine|mine)\b")
_RE_OWN_WORDS = re.compile(r"\b(?:the\s+Company|the\s+Corporation|our|we|us)\b")


# the firm a study was prepared by is its author, not its owner ('PEA for the Disley Project, prepared by Micon
# International Co Limited')
_RE_BY_CONSULTANT = re.compile(r"(?i)\b(?!(?:owned|held|operated|controlled|acquired|optioned|managed)\b)[a-z]+\s+by\s+(?:the\s+)?$|"
                               r"\bconsultants?\s*,?\s*$")


def _issuer_names(head, body):
    lead = " ".join((body or "")[:1500].split())
    sd = _RE_SELF_DEF.search(lead)
    names = [" ".join(lead[max(0, sd.start() - 90):sd.start()].split()[-5:])] if sd else []
    if sd:
        names += re.findall(r"[\"\u201c]\s*([^\"\u201c\u201d]{2,40}?)\s*[\"\u201d]", sd.group(0))
    names.append(" ".join((head or "").split()[:3]))
    return [n for n in names if n and not re.fullmatch(r"(?i)(?:the\s+)?(?:company|corporation|issuer)", n.strip())]


def _sentence_back(flat, pos, reach=350):
    """(from the start of the sentence before the one at `pos`, from the start of its own sentence), both to `pos`."""
    seg = flat[max(0, pos - reach):pos]
    ends = list(_RE_CLAUSE_END.finditer(seg))
    return (seg[ends[-2].end():] if len(ends) >= 2 else seg), (seg[ends[-1].end():] if ends else seg)


def _others_figure(flat, v, issuer):
    rx = _fig_rx(abs(v)) if v else None
    hits = list(rx.finditer(flat)) if rx else []
    if not hits or not issuer:
        return False
    for m in hits:
        lead, own = _sentence_back(flat, m.start())
        if _RE_OWN_WORDS.search(lead) or any(n.lower() in own.lower() for n in issuer[:-1]):
            return False
        names = [g.group("name") or g.group("pname") for g in _RE_OTHER_CO.finditer(lead)
                 if not _RE_BY_CONSULTANT.search(lead[max(0, g.start() - 40):g.start()])]
        if not [n for n in names if n and not re.match(r"(?i)(?:the|company|corporation|issuer)\b", n)
                and not any(C.same_company(n, i) for i in issuer)]:
            return False
    return True


def _one_scenario(a, b):
    """Two rows at one price state one scenario when they share a figure, when one of them has no NPV of its own, or when
    no figure of one contradicts the other's; two different sets of NPVs at one price are two cases the core gave the
    same price (a base case and a spot case)."""
    if any(a.get(k) is not None and a.get(k) == b.get(k) for k in _SIG):
        return True
    if not any(a.get(k) for k in ("npv_after_tax", "npv_pre_tax")) or not any(b.get(k) for k in ("npv_after_tax", "npv_pre_tax")):
        return True               # a row with a return and no NPV ('base case $1,450 per ounce': IRR only)
    return not any(a.get(k) is not None and b.get(k) is not None for k in _SIG)


def _tax_split(r):
    """A row stating its pre-tax and after-tax NPV as two different figures has read its tax labels."""
    return r.get("npv_pre_tax") is not None and r.get("npv_after_tax") is not None and r["npv_pre_tax"] != r["npv_after_tax"]


def _merge_same_price(rows):
    """1.0.12: a row named only by a price and another at that same price ('$1,200/oz' and 'base case $1,200 per
    ounce'; 'US$1,450 /oz' and 'base case $1,450 per ounce') are one scenario written twice -- a headline and a
    table, or a sensitivity table's base line. The row that reads both tax bases apart is kept, else the first stated
    unless the other states more figures; the kept row takes the other's figures where it has none."""
    def bare(r):
        n = _RE_BASE_CASE.sub(" ", r.get("scenario") or "")
        return n if C._RE_DECK.search(n) and not _RE_ROW_NAMED.search(n) else None
    out = []
    for r in rows:
        nm = bare(r)
        twin = next((u for u in out if nm and bare(u) and _same_deck(bare(u), nm) and u.get("basis") == r.get("basis")
                     and (None in (u.get("discount_pct"), r.get("discount_pct")) or u.get("discount_pct") == r.get("discount_pct"))
                     and _one_scenario(u, r)), None)
        if twin is None:
            out.append(r)
            continue
        if (_tax_split(r), sum(r.get(k) is not None for k in _SIG)) > (_tax_split(twin), sum(twin.get(k) is not None for k in _SIG)):
            out[out.index(twin)] = r
            r, twin = twin, r
        for k, v in r.items():
            if v is not None and twin.get(k) is None:
                twin[k] = v
    return out


# PAY: the payback the release states for its study, where the core has none or took a pre-tax or sensitivity one.
# 'Pre-tax payback of 3.8 years; after-tax payback of 4.8 years', 'a 1.53-year payback (1.82 year after-tax)',
# 'After-Tax NPV ... with a payback of 1.8 years' (the sentence's tax basis), 'payback of $440 million initial capital
# within 5 years', 'paying back the initial expansion capital in approximately two years', 'Payback Period(2) 7.2 years'.
# A payback in a clause at another price ('At $2.00/lb copper, after-tax payback is 3 years') or stated as a change is a
# point on a sensitivity curve; an after-tax payback is preferred to an untaxed one, which is preferred to a pre-tax one.
_PB_TAX = r"(?:(?:pre|after|post)[\s-]{0,2}tax\s+(?:and\s+(?:pre|after|post)[\s-]{0,2}tax\s+)?)"
_PB_NUM = r"(?:approximately\s+|about\s+|~\s*|just\s+)?(?P<n>\d{1,2}(?:\.\d+)?)[\s-]*(?P<u>years?|yrs?|months?)\b"
_RE_PB_STATED = re.compile(r"(?i)(?P<lab>" + _PB_TAX + r"?(?:\w+\s+){0,2}?pay[\s-]?back(?:\s+period)?(?:\s*\(\d\))?"
                           r"(?:\s*\((?:after|post|pre)[\s-]{0,2}tax\))?)"
                           r"(?:\s+(?:of\s+|on\s+)?(?:the\s+)?(?:(?:US|C|CA|A)?\$\s?[\d,.]+\s*(?:million|billion|M|B)\s+)?"
                           r"(?:initial|pre-?production|upfront|invested|total)?\s*(?:expansion\s+)?(?:capital|capex|investment)"
                           r"(?:\s+costs?)?)?"
                           r"\s*(?:is\s+|of\s+|:\s*|=\s*|-\s*|within\s+|in\s+|after\s+|estimated\s+at\s+)?" + _PB_NUM)
_RE_PB_FIRST = re.compile(r"(?i)(?<![\d.])" + _PB_NUM + r"\s+(?P<lab>" + _PB_TAX + r"?pay[\s-]?back)\b")
_RE_PB_PAREN = re.compile(r"(?i)pay[\s-]?back[^.;()]{0,60}?\(\s*" + _PB_NUM + r"\s+(?P<lab>after|post)[\s-]{0,2}tax\s*\)")
_RE_PB_PAYING = re.compile(r"(?i)\bpaying\s+back\s+(?:the\s+)?(?:initial\s+)?(?:\w+\s+)?capital\s+(?:in|within)\s+" + _PB_NUM)


def _pb_tax(flat, m):
    lab = m.group("lab") or ""
    if C._RE_AFTER.search(lab):
        return "after"
    if C._RE_PRE.search(lab):
        return "pre"
    lead, own = _sentence_back(flat, m.start(), 250)
    own = re.sub(r"\([^()]*\)", " ", own)          # '(after-tax US$268.3 million)' is the other figure's
    a, p = list(C._RE_AFTER.finditer(own)), list(C._RE_PRE.finditer(own))
    if a and (not p or a[-1].start() > p[-1].start()):
        return "after"
    return "pre" if p else None


def _pb_statements(flat):
    flat = C._num_words(flat)
    out, paren = [], []
    for rx in (_RE_PB_PAREN, _RE_PB_STATED, _RE_PB_FIRST, _RE_PB_PAYING):
        for m in rx.finditer(flat):
            if any(a <= m.start("n") < b for a, b, *_r in out):
                continue
            v = float(m.group("n"))
            y = round(v / 12.0, 2) if m.group("u").lower().startswith("month") else v
            if not 0 < y <= 25:
                continue
            if rx is _RE_PB_PAREN:
                tax = "after"
                paren.append((m.start(), m.start("n")))
            elif rx is _RE_PB_PAYING:
                tax = None
            else:
                tax = _pb_tax(flat, m)
                # 'a 1.53-year payback (1.82 year after-tax)': the figure beside a bracketed after-tax one is the other
                if tax != "pre" and not C._RE_AFTER.search(m.group("lab") or "") and \
                        any(m.start() - 30 <= a and m.end("n") <= b for a, b in paren):
                    tax = "pre"
            out.append((m.start("n"), m.end("n"), y, tax, m.start()))
    return flat, sorted(out)


def _pb_sweep(flat, at, base_name):
    """A payback stated at another price than the base case's, or as a change, is a sensitivity point."""
    lead, own = _sentence_back(flat, at, 250)
    clause = own[-200:]
    if _RE_SWEEP_CHANGE.search(clause) or _RE_SENSITIVITY.search(clause) or _RE_SWEEP_SWING.search(clause):
        return True
    d = C.deck_in(clause)
    return bool(d and C._RE_DECK.search(base_name or "") and not _same_deck(base_name, d.group(0)))


def _fix5_payback(flat, rows):
    if not rows:
        return rows
    r0 = rows[0]
    flat, st = _pb_statements(flat)
    good = [x for x in st if x[3] != "pre" and not _pb_sweep(flat, x[4], r0.get("scenario"))]
    if not good:
        return rows
    pick = next((x for x in good if x[3] == "after"), good[0])[2]
    cur = r0.get("payback_years")
    if cur is None:
        if not any(r.get("payback_years") == pick for r in rows[1:]):
            # the base case on its other basis (nominal / real) is the same scenario and has the same payback
            for r in rows:
                if r is r0 or (r.get("scenario") == r0.get("scenario") and r.get("payback_years") is None):
                    r["payback_years"] = pick
        return rows
    if cur != pick and not any(x[2] == cur for x in good) and any(x[2] == cur for x in st):
        r0["payback_years"] = pick      # the core's figure is a pre-tax or a sensitivity payback
    return rows


# IRRTAX: a figure filed under the wrong tax basis. An IRR stated without a tax word takes the basis of its own sentence
# ('Pre-tax NPV8% of $1,935.2 million ... and an IRR of 38.0% for the base case. After-tax NPV8% of $1,412.7 million and
# after-tax IRR of 33.4%' -- the core filed 38.0% as the after-tax IRR); a tax word written after the figures governs them
# ('NPV (7%) of C$440.1 M and IRR of 17.1% pre-tax and NPV (7%) of C$215.0 M and IRR of 12.7% after tax'); a bracketed
# figure on the other basis is the other basis ('pre-tax IRR of 34.1% (25.2% post-tax) and NPV8% of $230 million ($128
# million post-tax)').
_RE_TAXW = re.compile(r"(?i)\b(?:(?P<pre>pre|before)|(?P<aft>after|post))[\s-]{0,2}tax(?:es)?(?![a-z])")
_RE_IRR_STATED = re.compile(r"(?i)(?:(?<![\d.])(?P<b>\d{1,3}(?:\.\d+)?)\s*%\s*(?P<tb>(?:(?:pre|after|post)[\s-]{0,2}tax\s+)?)"
                            r"(?:IRR|internal\s+rate\s+of\s+return)\b"
                            r"|(?P<tl>(?:(?:pre|after|post)[\s-]{0,2}tax\s+)?)(?:IRR|internal\s+rate\s+of\s+return)\b"
                            r"(?:\s*\([^()]{0,25}\))?(?P<ti>\s*\((?:pre|after|post)[\s-]{0,2}tax\))?"
                            r"\s*(?:of\s+|:\s*|=\s*|is\s+|was\s+)?(?:approximately\s+|~\s*)?(?P<a>\d{1,3}(?:\.\d+)?)\s*%)"
                            r"(?P<tt>\s*(?:\(\s*)?(?:pre|after|post)[\s-]{0,2}tax(?![a-z]))?")
_OB_VAL = r"(?:(?:US|C|CA|A)?\$\s?[\d,.]+\s*(?:million|billion|bn|mm|M|B)?|\d{1,3}(?:\.\d+)?\s*%)"
_OB_TAX = r"(?:pre|after|post)\s?-?\s?tax"
_RE_OTHER_BASIS = re.compile(r"(?i)\s*\(\s*(?:(?P<v>" + _OB_VAL + r")\s*(?P<t>" + _OB_TAX + r")|(?P<t2>" + _OB_TAX + r")\s*:?\s*(?P<v2>"
                             + _OB_VAL + r"))\s*\)")


def _fig_any(v):
    """_fig_rx, and the figure written with trailing zeros ('C$215.0 M' for 215 million)."""
    base = _fig_rx(abs(v))
    alts = [base.pattern] if base is not None else []
    for div, unit in ((1e9, r"(?:billion|bn|B)\b"), (1e6, r"(?:million|mm|M)\b")):
        if abs(v) >= div:
            t = "%.10g" % (abs(v) / div)
            ip, dp = (t.split(".") + [""])[:2]
            alts.append(r"(?<![\d.,])" + re.escape(ip) + (r"\." + re.escape(dp) + r"0*" if dp else r"(?:\.0+)?") +
                        r"\s?" + unit)
            break
    return re.compile("|".join(alts)) if alts else None


def _basis_of(text):
    m = list(_RE_TAXW.finditer(text or ""))
    return None if not m else ("pre" if m[-1].group("pre") else "after")


def _irr_statements(flat):
    out = []
    for m in _RE_IRR_STATED.finditer(flat):
        v = float(m.group("b") or m.group("a"))
        lab = (m.group("tb") or "") + (m.group("tl") or "") + (m.group("ti") or "")
        tax = _basis_of(lab)
        if tax is None and m.group("tt"):
            tax = _basis_of(m.group("tt"))
        if tax is None:
            lead, own = _sentence_back(flat, m.start(), 250)
            tax = _basis_of(re.sub(r"\([^()]*\)", " ", own))
        out.append((v, tax, m.start(), m.end()))
    return out


def _fix5_tax(flat, rows):
    if not rows:
        return rows
    for r in rows:
        # a bracketed figure on the other basis right after one of the row's figures: the bracketed one is on the basis
        # it names, the figure before it on the other
        for fk, pct in (("npv_after_tax", False), ("npv_pre_tax", False), ("irr_after_tax_pct", True), ("irr_pre_tax_pct", True)):
            v = r.get(fk)
            if v is None:
                continue
            rx = re.compile(r"(?<![\d.])(?<!\d\s)" + re.escape("%g" % v) + r"\s*%") if pct else _fig_any(v)
            for m in (rx.finditer(flat) if rx else ()):
                b = _RE_OTHER_BASIS.match(flat, m.end())
                if not b:
                    continue
                t2 = _basis_of(b.group("t") or b.group("t2"))
                bv = b.group("v") or b.group("v2")
                if pct != ("%" in bv):
                    continue
                w = (float(re.sub(r"[^\d.]", "", bv.split("%")[0]).strip(".") or 0) if pct else C.money(bv)[0])
                if not w or w == v or (not pct and abs(w) < 1e6):
                    continue
                kind = "irr_%s_tax_pct" if pct else "npv_%s_tax"
                mine, other = kind % ("pre" if t2 == "after" else "after"), kind % t2
                if r.get(mine) not in (None, v) or r.get(other) not in (None, v, w):
                    break
                r[mine], r[other] = v, w
                break
    for r in rows:
        st = [x for x in _irr_statements(flat) if not _pb_sweep(flat, x[2], rows[0].get("scenario"))]
        ia, ip = r.get("irr_after_tax_pct"), r.get("irr_pre_tax_pct")
        after = [x[0] for x in st if x[1] == "after"] if r is rows[0] else []
        sa = [x[1] for x in st if x[0] == ia] if ia is not None else []
        sp = [x[1] for x in st if x[0] == ip] if ip is not None else []
        if sa and all(t == "pre" for t in sa):
            if ip is not None and ip != ia and sp and all(t == "after" for t in sp):
                r["irr_pre_tax_pct"], r["irr_after_tax_pct"] = ia, ip
            elif ip is None or ip == ia:
                r["irr_pre_tax_pct"] = ia
                r["irr_after_tax_pct"] = next((a for a in after if a != ia), None)
        elif ia is not None and ip == ia and "pre" in sa:
            r["irr_after_tax_pct"] = next((a for a in after if a != ia), ia)
    # a trailing tax word: the row's NPVs are filed the wrong way round
    def trail(v):
        rx = _fig_any(v) if v else None
        for m in (rx.finditer(flat) if rx else ()):
            nxt = _RE_NPV_WORD.search(flat, m.end(), m.end() + 160)
            seg = re.split(r"[;\n\u2022]|\.(?!\d)", flat[m.end():nxt.start() if nxt else m.end() + 100])[0]
            lead = flat[max(0, m.start() - 80):m.start()]
            lab = list(_RE_NPV_WORD.finditer(lead))
            # the figure's own NPV label, and a tax word written directly before it ('Post Tax NPV 8 of US$709m')
            own = lead[lab[-1].start():] if lab else lead[-40:]
            adj = re.search(r"(?i)(?:pre|after|post)[\s-]{0,2}tax(?:es)?[\s,]*$", lead[:lab[-1].start()]) if lab else None
            if adj is None and _basis_of(re.sub(r"\([^()]*\)", " ", own)) is None:
                t = _RE_TAXW.search(re.sub(r"\([^()]*\)", " ", seg))
                return None if t is None else ("pre" if t.group("pre") else "after")
        return None
    for r in rows:
        pre, post = r.get("npv_pre_tax"), r.get("npv_after_tax")
        if post is not None and post != pre and trail(post) == "pre" and (pre is None or trail(pre) == "after"):
            r["npv_pre_tax"], r["npv_after_tax"] = post, pre
    return [_fix_rates(r) for r in rows]


# CUR: what the release says it reports in, read across a line break ('All amounts \nare stated in U.S. dollars'), and
# in thousands of a currency ('are expressed in thousands of US dollars'); else the currency written in the NPV label's own
# unit ('NPV-5% (after tax, US$ millions) $434M', 'NPV 5% after taxes and mining duties (M CAD) 54.4').
_RE_CUR_SAID2 = re.compile(_RE_CUR_SAID.pattern.replace(r"(?P<cur>", r"(?:(?:thousands?|millions?)\s+of\s+)?(?P<cur>"),
                           _RE_CUR_SAID.flags)
_RE_NPV_UNIT = re.compile(r"(?i)(?:NPV|net\s+present\s+value)[^()\n$]{0,40}?(?:\(\s*\d{1,2}(?:\.\d+)?\s*%\s*\)[^()\n$]{0,30}?)?"
                          r"\((?:[^()\d]{0,24}?,\s*)?(?:(?P<a>US\$|C\$|CA\$|CDN\$|A\$|USD|CAD|AUD)\s*(?:M|MM|millions?|000'?s)?"
                          r"|(?:M|MM|millions?|\$\s?M)\s*(?P<b>USD|CAD|AUD))\s*\)")


def _fix5_currency(full):
    flat = " ".join((full or "").split())
    c = _said_currency_rx(_RE_CUR_SAID2, flat)
    if c:
        return c
    m = _RE_NPV_UNIT.search(flat)
    if m:
        k = re.sub(r"[\s$]", "", (m.group("a") or m.group("b"))).upper()
        return {"US": "USD", "USD": "USD", "C": "CAD", "CA": "CAD", "CDN": "CAD", "CAD": "CAD", "A": "AUD", "AUD": "AUD"}.get(k)
    return None


def _said_currency_rx(rx, text):
    m = rx.search(text or "")
    if not m:
        return None
    c = re.sub(r"[\s.$]", "", m.group("cur")).upper()
    return "CAD" if c.startswith(("CANADIAN", "CDN", "CAD", "C")) else "AUD" if c.startswith(("AUSTRALIAN", "A")) else "USD"


# PRECISE: a figure the release rounds in its headline or highlights ('After-Tax NPV (5%) of US$1.1 Billion', 'AFTER TAX IRR
# OF 35%') and states exactly in its own results table ('After-tax NPV5% ($M) $524 $1,060 $1,610 $2,159', 'After-Tax IRR %
# 34.8% 49.7%', 'After-tax IRR (%) 33.3') is the table's figure, when exactly one figure in that row rounds to it.
_RE_AT_LABEL = re.compile(r"(?i)\b(?:after|post)[\s-]{0,2}tax(?:es)?\s+(?P<k>NPV|IRR|internal\s+rate\s+of\s+return|net\s+present\s+value)(?![A-Za-z])"
                          r"|\b(?P<k2>NPV|IRR)\b[^\n\d]{0,6}?\d{0,2}%?\s*after\s+tax(?:es)?\b[^\n\d]{0,40}")
_RE_ROW_NUM = re.compile(r"(?<![\w.,])\$?\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(%?)")


def _sig(x):
    t = ("%.10g" % abs(x)).replace(".", "").lstrip("0").rstrip("0")
    return max(1, len(t))


def _fix5_precise(text, rows):
    cands = {"npv": [], "irr": []}
    for m in _RE_AT_LABEL.finditer(text or ""):
        kind = "irr" if re.match(r"(?i)IRR|internal", m.group("k") or m.group("k2")) else "npv"
        line = text[m.end():m.end() + 120].split("\n")[0]
        hdr = re.match(r"\s*(?:\d{1,2}(?:\.\d+)?\s*%\s*)?(?:\(\s*\d{1,2}\s*%\s*\)\s*)?(?:@\s*\d{1,2}%\s*)?(?P<u>\((?:US|C|CA)?\$\s?M+\)|"
                       r"(?:US|C|CA)?\$\s?(?:M+|millions?)\b|\((?:%)\)|%)?", line)
        unit = hdr.group("u") or ""
        if kind == "npv" and not re.search(r"(?i)M|million", unit):
            continue
        for c in _RE_ROW_NUM.finditer(line[hdr.end():]):
            w = float(c.group(1).replace(",", ""))
            cands[kind].append(w * 1e6 if kind == "npv" else w)
    for r in rows:
        for k, kind in (("npv_after_tax", "npv"), ("irr_after_tax_pct", "irr")):
            v = r.get(k)
            if not v or _sig(v) > 2:
                continue
            k_ = _sig(v)
            hit = {w for w in cands[kind] if _sig(w) > k_ and float("%.*g" % (k_, w)) == v}
            if len(hit) == 1:
                r[k] = hit.pop()
    return rows


# OWN: a release restating several studies, each in a sentence of its own ('The 2025 PEA for <one project> demonstrated an
# approximate 6-year underground mine life ... with initial capex of $36 million returning an after-tax NPV 5% of $227
# million'; 'The 2023 PEA for <another> demonstrated an 8.2-year open pit mine life ... initial capex of $28 million'):
# each row takes the mine life and initial capital its own sentence states, not the first one in the release.
_RE_OWN_LIFE = re.compile(r"(?i)(?<![\d.])(\d{1,2}(?:\.\d)?)[\s-]*years?[\s-]+(?:[a-z]+[\s-]+){0,2}?(?:mine|operating)[\s-]+life\b|"
                          r"\b(?:mine|operating)\s+life\s+of\s+(?:approximately\s+)?(\d{1,2}(?:\.\d)?)\s*years?\b")
_RE_OWN_CAPEX2 = re.compile(r"(?i)\binitial\s+(?:capital(?:\s+costs?)?|capex)\s+(?:of\s+|is\s+)?((?:US|C|CA|A)?\$\s?[\d,.]+\s*(?:million|billion|M\b|B\b))")


def _fix5_own(flat, rows):
    if len(rows) < 2:
        return rows
    spans = []
    for r in rows:
        v = r.get("npv_after_tax") or r.get("npv_pre_tax")
        rx = _fig_any(v) if v else None
        m = rx.search(flat) if rx else None
        if m is None:
            return rows
        lead, own = _sentence_back(flat, m.start(), 400)
        spans.append((m.start() - len(own), m.start(), own))
    if len({a for a, _b, _o in spans}) < len(spans):
        return rows                   # two rows in one sentence: a case list, not studies of their own
    for r, (_a, _b, own) in zip(rows, spans):
        lm = list(_RE_OWN_LIFE.finditer(own))
        if len(lm) == 1:
            r["mine_life_years"] = float(lm[0].group(1) or lm[0].group(2))
        cm = list(_RE_OWN_CAPEX2.finditer(own))
        if len(cm) == 1:
            c = C.money(cm[0].group(1))[0]
            if c:
                r["initial_capex"] = c
    return rows


def _price_unit(name):
    d = C._RE_DECK.search(name or "")
    u = re.search(r"(?i)(oz|ounce|lb|pound|t|tonne|mtu)\b", d.group(0)[d.group(0).index("/") if "/" in d.group(0) else 0:]) if d else None
    return {"ounce": "oz", "pound": "lb", "tonne": "t"}.get(u.group(1).lower(), u.group(1).lower()) if u else None


def _drop_rate_points(rows):
    """1.0.12: a row named only by a price, at another discount rate than the base case's and on the base case's own
    commodity, is a point of a sensitivity the release reports at that other rate ('NPV5% of $160mm at $1,650/oz Au;
    increasing to $216mm at $1,800/oz' beside a base case at $1,500/oz and 10%), not a case. A case the company names
    keeps its row whatever its rate, and so does a row at another rate on another commodity (a second project's study)."""
    if len(rows) < 2 or rows[0].get("discount_pct") is None or not _price_unit(rows[0].get("scenario")):
        return rows
    base = rows[0]
    return [r for r in rows if r is base or r.get("discount_pct") in (None, base["discount_pct"])
            or r.get("scenario") == base.get("scenario") or _price_unit(r.get("scenario")) != _price_unit(base.get("scenario"))
            or _RE_ROW_NAMED.search(_RE_BASE_CASE.sub(" ", r.get("scenario") or ""))]


def analyse(headline: str, body: str) -> dict:
    """Every scenario the release states, with the study's context and whose study it is."""
    if not _RE_ANY_ECON.search(headline or "") and not _RE_ANY_ECON.search(body or ""):
        return {"is_economic_study": False, "reason": "no_figures", "study_type": None,
                "context": None, "project": None, "owner_name": None, "scenarios": []}
    why = not_own_study(headline, body)
    if why:
        return {"is_economic_study": False, "reason": why, "study_type": None,
                "context": None, "project": None, "owner_name": None, "scenarios": []}
    head = headline or ""
    oth = _RE_OTHER_NEWS.search(body or "")
    if oth and oth.start() > 200:
        body = (body or "")[:oth.start()]      # 1.0.10: what follows is other companies' news
    body = _RE_URL.sub(" ", body or "")            # 1.0.11: a link's slug is not a statement
    body = _clean_body(body)                       # 1.0.12: words a PDF split, metres written 'm'
    text = C.economics_text(head, body)
    # a blank line, so the headline is never joined to the first line of the body: Freeman's
    # headline ends '...at US$4,350/oz Gold - PR Newswire Canada' and its body opens with the base case
    # at US$3,650, and read as one clause the base case took the headline's price
    full = head + "\n\n" + text
    res = {"is_economic_study": False, "reason": None, "study_type": None,
           "context": None, "project": None, "owner_name": None, "scenarios": []}

    study = C.study_type(head, text)
    context = _context(head, text, study)
    # a release announcing a new study may quote the one it replaces; those figures are not its own
    rows = C.scenarios(full, skip_prior=(context == "announced"))
    flat_ = C.unwrap(text)
    # 1.0.11: a rate read as a return, and an after-tax IRR copied from the pre-tax one, are not the release's figures
    rows = [_fix_copied_irr(flat_, _fix_rates(dict(r))) for r in rows]
    rows = [_fix_other_metric(flat_, r, rows) for r in rows]     # 1.0.12: EBITDA or capital read as the NPV
    rows = [r for r in rows
            if r["npv_after_tax"] is not None or r["npv_pre_tax"] is not None
            or r["irr_after_tax_pct"] is not None or r["irr_pre_tax_pct"] is not None]
    # 1.0.10: an NPV stated as part of a claim ('Forward royalty stream value to 2030 (NPV at 8%) ~US$15-25 million ...
    # TOTAL ESTIMATED CLAIM', Royalties Inc.) is a valuation for a court, not a study
    rows = [r for r in rows if not _claim_figure(flat_, r.get("npv_after_tax") or r.get("npv_pre_tax"))]
    rows = rows + _named_cases(flat_, rows, study)   # 1.0.12: a case named in words the core does not read
    issuer = _issuer_names(head, body)                # 1.0.12: another company's study quoted in passing
    rows = [r for r in rows if not _others_figure(flat_, r.get("npv_after_tax") or r.get("npv_pre_tax"), issuer)]
    if not rows:
        res["reason"] = "no_figures"
        return res

    project = PN.bare(PN.primary(head, text))
    owner = C.study_owner_name(head, text)
    # What the release SAYS it reports in beats the exchange rate it quotes, which in turn beats
    # what its currency marks happen to add up to -- Westhaven's recaps carry no mark but their
    # own except the US gold price they assume.
    fallback_cur = (C.stated_currency(full) or _said_currency(full) or _fix5_currency(full)
                    or C.exchange_base(full) or C.dominant_currency(full))
    shared = C.project_economics(full)
    # Justin, 2026-09-20: show both capital figures where a release states two. Desert Gold's
    # highlights say $15 million and the base row of its CAPEX sensitivity table says 20.9.
    shared["capex_sensitivity"] = C.capex_sensitivity_base(full, shared["initial_capex"])

    out = []
    for r in rows:
        row = dict(r)
        row["project"] = project
        row["study_type"] = row.pop("_kind", None) or study
        row["context"] = context
        row["currency"] = row["currency"] or fallback_cur
        for k, v in shared.items():
            if k == "capex_currency" or (k == "initial_capex" and row.get(k) is not None):
                continue                  # 1.0.12: a named case's own capital ('with initial capital costs of C$65 million')
            row[k] = v
        out.append(row)

    # A release that states the same scenario in two currencies has stated one scenario. STLLR
    # writes 'Base Case After-Tax NPV5% of C$1.36 billion (US$1.01 billion)' and headlines the
    # US figure; the page carries the currency the release reports in.
    if fallback_cur:
        keep = [r for r in out if (r.get("currency") or fallback_cur) == fallback_cur]
        if keep and len(keep) < len(out):
            names = {C._merge_key(r["scenario"])[:2] for r in keep}
            out = [r for r in out
                   if r in keep or C._merge_key(r["scenario"])[:2] not in names]

    # 1.0.3: a release reciting two studies -- Ivanhoe's Platreef update quotes the Phase 2 FS and the Phase 3 PEA;
    # Centerra's year-end results quote the Kemess PEA and the Mount Milligan PFS -- keeps the scenarios of the
    # study it is labelled with. A figure whose own sentence names another kind of study belongs to that study.
    if len(out) > 1 and study:
        flat = C.unwrap(text)
        kept = [r for r in out
                if C.figure_kind(flat, r.get("npv_after_tax") or r.get("npv_pre_tax")) in (None, study)]
        if kept:
            out = kept

    # 1.0.10: one scenario stated twice under two names ('$2,332/oz' in the highlights, '$2,333 per ounce' in the table,
    # Troilus): the same figures are the same scenario, and the first-named row takes the other's missing fields
    uniq = []
    for r in out:
        sig = tuple(r.get(k) for k in ("npv_pre_tax", "npv_after_tax", "irr_pre_tax_pct", "irr_after_tax_pct"))
        twin = next((u for u in uniq if u.get("basis") == r.get("basis") and sum(v is not None for v in sig) >= 1 and
                     all(a == b for a, b in zip(sig, (u.get(k) for k in ("npv_pre_tax", "npv_after_tax", "irr_pre_tax_pct", "irr_after_tax_pct"))))), None)
        if twin is not None and not _same_deck(twin.get("scenario"), r.get("scenario")):
            twin = None           # the same figures under two different prices: one name is wrong, and it is not ours to pick
        if twin is not None and (sig[0] is not None or sig[1] is not None):
            for k, v in r.items():
                if v is not None and twin.get(k) is None:
                    twin[k] = v
            continue
        uniq.append(r)
    out = uniq
    # 1.0.11: one scenario under one name is one row; a row named only by a price beside the base case is dropped
    # when the release marks it as a point on a sensitivity curve
    out = _drop_rate_points(out)          # 1.0.12: price points at a second discount rate
    out = _merge_same_name(out)
    out = _merge_same_price(out)          # 1.0.12: one price written twice is one scenario
    out = _drop_sweep_points(C.unwrap(full), out)
    flat_full = C.unwrap(full)
    out = _fix5_tax(flat_full, out)                # 1.0.13: figures filed under the wrong tax basis
    out = _fix5_precise(full, out)                 # 1.0.13: a rounded figure the results table states exactly
    out = _fix5_own(flat_full, out)                # 1.0.13: each restated study's own mine life and capital
    out = _fix5_payback(flat_full, out)            # 1.0.13: the study's payback

    res["is_economic_study"] = True
    res["reason"] = "scenarios"
    res["study_type"] = study
    res["context"] = context
    res["project"] = project
    res["owner_name"] = owner
    res["scenarios"] = out[:12]
    return res


# ------------------------------------------------------------------ facts store adapter
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["scenarios"]:
        return [F.Record(KIND, facts=[F.Fact("is_economic_study", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"])], confidence=0.0)]
    out = []
    for s in a["scenarios"]:
        fs = [F.Fact("is_economic_study", value_num=1.0)]
        if a["owner_name"]:
            fs.append(F.Fact("owner_name", value_text=a["owner_name"][:120]))
        for k in TXT_FIELDS:
            if s.get(k):
                fs.append(F.Fact(k, value_text=str(s[k])))
        for k in NUM_FIELDS:
            if s.get(k) is not None:
                fs.append(F.Fact(k, value_num=float(s[k])))
        out.append(F.Record(KIND, facts=fs, confidence=1.0))
    return out


def parse_records(rows_by_ordinal):
    """{ordinal: [(field, seq, value_num, value_text)]} -> the analyse()-shaped dict."""
    scen, is_es = [], False
    for ordinal in sorted(rows_by_ordinal):
        s = {k: None for k in TXT_FIELDS + NUM_FIELDS}
        for field_, seq, num, text in sorted(rows_by_ordinal[ordinal], key=lambda f: (f[0], f[1])):
            if field_ == "is_economic_study":
                is_es = is_es or num == 1.0
            elif field_ == "owner_name":
                s["owner_name"] = text
            elif field_ in NUM_FIELDS:
                s[field_] = num
            elif field_ in TXT_FIELDS:
                s[field_] = text
        if s["scenario"]:
            scen.append(s)
    return {"is_economic_study": is_es and bool(scen),
            "study_type": scen[0]["study_type"] if scen else None,
            "context": scen[0]["context"] if scen else None,
            "project": scen[0]["project"] if scen else None,
            "owner_name": scen[0].get("owner_name") if scen else None,
            "scenarios": scen}


def to_prediction(records):
    if not records:
        return None
    rows = {i: [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts]
            for i, rec in enumerate(records)}
    return prediction_from(parse_records(rows))


JUDGED = ("scenario", "study_type", "currency", "context", "basis", "discount_pct",
          "npv_pre_tax", "npv_after_tax", "irr_pre_tax_pct", "irr_after_tax_pct",
          "payback_years", "initial_capex", "capex_sensitivity", "mine_life_years")


def prediction_from(a):
    if not a.get("is_economic_study") or not a.get("scenarios"):
        return None
    return {"project": a.get("project"), "owner_name": a.get("owner_name"),
            "scenarios": [{k: s.get(k) for k in JUDGED} for s in a["scenarios"]]}


def _code_sha():
    # this reader's own two files, whole, and exactly the shared-helper code it runs (portal/fingerprint.py follows
    # every portal module this file imports; 1.0.6). The Resources reader is no longer used.
    return FP.code_sha(__file__, own=(C.__file__,))


SPEC = F.ExtractorSpec(NAME, VERSION, KIND, TAG, extract, _code_sha())


# ------------------------------------------------------------------ self-test
def self_test(verbose=False):
    """Cases the set forced. Every figure here is from a release Justin labelled on 2026-09-20;
    the full-body run on the box is what measures the reader, this is what stops a regression."""
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))
        elif verbose:
            print("  ok   %s" % name)

    # NILI.V 4629ef10f3a4 -- a four-cell flat table with the tax basis in a bare cell above it
    a = analyse("Surge Battery Metals Announces PEA for its Nevada North Lithium Project",
                "Surge Battery Metals Inc. (TSXV: NILI) announces the Preliminary Economic "
                "Assessment for its Nevada North Lithium Project. Project Economics | Pre-Tax | "
                "Net Present Value (NPV) | (8%) | $ M | 11,395 | Internal Rate of Return (IRR) | "
                "% | 25.5% | Post-Tax | Net Present Value (NPV) | 8%) | $ M | 9,214 | "
                "Internal Rate of Return (IRR) | % | 22.8%. The base case uses a lithium price "
                "of US$24,000/t LCE.")
    s = a["scenarios"]
    eq("NILI one row", len(s), 1)
    eq("NILI pre-tax NPV is not filed as after-tax",
       (s[0]["npv_pre_tax"], s[0]["npv_after_tax"]), (11395e6, 9214e6))
    eq("NILI IRRs", (s[0]["irr_pre_tax_pct"], s[0]["irr_after_tax_pct"]), (25.5, 22.8))
    eq("NILI rate from its own cell", s[0]["discount_pct"], 8.0)
    eq("NILI scenario carries its price deck", s[0]["scenario"], "base case US$24,000/t LCE")
    eq("NILI study type", a["study_type"], "PEA")
    eq("NILI project", a["project"], "Nevada North Lithium")

    # SLI.V f6a9a23a4d8f -- three-cell table, rate stated only in prose
    a = analyse("Standard Lithium Announces PEA for the Smackover Project",
                "The PEA uses a discount rate of 8%. NPV (Pre-Tax) | $ million | 5,924 | "
                "NPV (After-Tax) | $ million | 4,992 | IRR (Pre-Tax) | % | 25.7% | "
                "IRR (After-Tax) | % | 24.0%")
    s = a["scenarios"][0]
    eq("SLI tax label after the token", (s["npv_pre_tax"], s["npv_after_tax"]), (5924e6, 4992e6))
    eq("SLI rate from prose", s["discount_pct"], 8.0)

    # LMR.V 345847f40783 -- both bases in consecutive sentences; the nearest marker wins
    a = analyse("Lomiko Metals Announces PFS for the La Loutre Graphite Project",
                "Pre-tax NPV (8%) of CA$797.5 M and a pre-tax IRR of 30.3%. After-tax NPV (8%) "
                "of CA$617.4 M and an after-tax IRR of 24.7%.")
    s = a["scenarios"][0]
    eq("LMR both bases on one row",
       (s["npv_pre_tax"], s["npv_after_tax"], s["irr_pre_tax_pct"], s["irr_after_tax_pct"]),
       (797.5e6, 617.4e6, 30.3, 24.7))
    eq("LMR currency", s["currency"], "CAD")

    # DBG.V eb87d75595b9 -- three flowsheets tagged inline in one sentence
    a = analyse("Doubleview Gold Announces PEA for the Hat Project",
                "Using consensus prices the Hat deposit returns an After-Tax NPV(5%) of "
                "C$4.96 billion (A1), C$6.73 billion (A2), or C$7.27 billion (B), with an "
                "After-Tax IRR of 19% (A1), 23% (A2), or 19% (B).")
    eq("DBG three rows", [x["npv_after_tax"] for x in a["scenarios"]], [4.96e9, 6.73e9, 7.27e9])
    eq("DBG IRRs follow their tags", [x["irr_after_tax_pct"] for x in a["scenarios"]],
       [19.0, 23.0, 19.0])

    # DAU.V a32e12a20c53 -- two named cases above three sensitivity sweeps
    a = analyse("Desert Gold Announces PEA on the SMSZ Project",
                "At a base case gold price of US$2,500/oz the SMSZ project returns an after-tax "
                "NPV (10%) of US$24 million and an after-tax IRR of 34%. At US$3,000/oz gold the "
                "after-tax NPV (10%) is US$41 million and the after-tax IRR is 51%. "
                "Gold price sensitivity | -20% | NPV | US$9 million | -10% | NPV | "
                "US$16 million | +10% | NPV | US$32 million | +20% | NPV | US$40 million")
    eq("DAU sweeps are not scenarios", len(a["scenarios"]), 2)

    # detection: the vocabulary without the figures is not an economic study
    a = analyse("Century Lithium Receives Final Permit",
                "The PEA reports net present value, internal rate of return, capital costs and "
                "operating costs for the project.")
    eq("no figures, no study", a["is_economic_study"], False)
    eq("no figures, reason", a["reason"], "no_figures")

    # attribution: the reader records whose study the release says it is; the publisher decides.
    # PMC.CN 90d629ca3ed3, as Peloton actually wrote it -- no exchange symbol anywhere in it
    a = analyse("Surge Battery Metals Presents Their Preliminary Economic Assessment",
                "In June, 2025, Surge Battery Metals (Surge) released a Preliminary Economic Assessment "
                "(PEA) on their Nevada North Lithium Project, which is located immediately beside "
                "Peloton's North Elko Lithium Project. Key highlights from the Surge PEA include: "
                "After-tax NPV8%: US$9.21 Billion. After-tax IRR: 22.8% at US$24,000/t LCE.")
    eq("owner named in the headline", a["owner_name"], "Surge Battery Metals")
    eq("not Peloton's", C.same_company(a["owner_name"], "Peloton Minerals Corporation"), False)
    eq("is Surge's", C.same_company(a["owner_name"], "Surge Battery Metals Inc."), True)
    eq("the issuer's own headline", C.study_owner_name("Radisson Announces Its Positive PEA", ""), "Radisson")
    eq("a short name is the same company", C.same_company("Radisson", "Radisson Mining Resources Inc."), True)
    eq("a project name is not an owner", C.study_owner_name("West Red Lake Delivers Madsen PFS", ""), None)
    eq("no named owner", analyse("Standard Lithium Announces PEA for the Smackover Project",
                                 "NPV (After-Tax) | $ million | 4,992")["owner_name"], None)

    # background: a release restating a study it already published
    a = analyse("Frontier Lithium Initiates Update to the PAK Feasibility Study",
                "The Company is initiating an update. The 2025 FS, disclosed in a press release "
                "dated May 28, 2025, reported an after-tax NPV (8%) of C$932 million and an "
                "after-tax IRR of 17.9%.")
    eq("background is not announced", a["context"], "background")

    # from the corpus review on the live database, 2026-09-21: figures that are not the NPV
    a = analyse("Fuerte Announces a Positive Preliminary Economic Assessment for the Coffee Gold Project",
                "After-Tax NPV(5%) of US$2.3 Billion, IRR of 47.8%, and payback achieved in 1.7 years at "
                "analyst consensus gold prices. After-Tax NPV(5%) of US$4.0 Billion, IRR of 67.2% at spot.")
    eq("an IRR is not a net present value", sorted(x["npv_after_tax"] for x in a["scenarios"]), [2.3e9, 4.0e9])
    a = analyse("Westhaven Announces Brokered Private Placement",
                "the Shovelnose project, having a Cdn$454 million after- tax NPV6% and 43.2% IRR (base case "
                "parameters of US$2 ,400 per ounce gold, US$28 per ounce silver)")
    eq("the figure before a spaced tax label", [x["npv_after_tax"] for x in a["scenarios"]], [454e6])
    a = analyse("Cascadia Receives Permit",
                "A 2023 preliminary economic assessment demonstrated positive economic potential, with a $230.4 M\n"
                " post-tax NPV\n(5%)\n and 29%\npost-tax IRR at US$3.75\n/lb copper and US$1,800\n/oz gold.")
    eq("a metal price is not an NPV", [x["npv_after_tax"] for x in a["scenarios"]], [230.4e6])
    a = analyse("Arizona Metals Announces Results of Preliminary Economic Assessment",
                "Base Case After-Tax NPV 5% of US$-6 million and IRR of 4.9% at US$4.70/lb copper. Spot Case "
                "After-Tax NPV 5% of US$445 million and IRR of 14.9% at US$6.05/lb copper.")
    eq("a negative NPV keeps its sign", [x["npv_after_tax"] for x in a["scenarios"]], [-6e6, 445e6])
    a = analyse("Copper Fox Assembles Project Team",
                "a US$0.25/lb. increase in copper price increased the after-tax NPV by approximately US$90 million")
    eq("a change in NPV is not a scenario", a["scenarios"], [])
    a = analyse("RPX Gold Inc. Delivers Robust Preliminary Economic Assessment",
                "After-tax NPV5% C$523 million and after-tax IRR of 99.7% at a base case gold price of "
                "US$3,500/ounce and an after-tax NPV5% of C$935 million and IRR of 181% at an upside gold "
                "price of US$4,550/ounce.")
    eq("two priced scenarios in one sentence", [(x["npv_after_tax"], x["irr_after_tax_pct"]) for x in a["scenarios"]],
       [(523e6, 99.7), (935e6, 181.0)])
    # from the live page after the first publish (1.0.1)
    a = analyse("Omai Gold Announces Preliminary Economic Assessment for Its Omai Project",
                "$4.0 billion\n\nafter-tax net present value at a 5% discount rate at base case $3,600/oz gold, "
                "increasing to\n\n$5.5 billion\n\nat $4,200/oz gold")
    eq("a figure 'increasing to' belongs to the price after it",
       sorted((x["scenario"], x["npv_after_tax"]) for x in a["scenarios"]),
       [("$4,200/oz", 5.5e9), ("base case $3,600/oz", 4.0e9)])
    a = analyse("Freeman Gold Files Technical Report -- After-Tax NPV(5%) of Approximately US$1.03 Billion "
                "and ~45.4% IRR at US$4,350/oz Gold - PR Newswire Canada",
                "Feasibility Study base case confirms US$695.6 million after-tax NPV(5%), 34.4% IRR and "
                "2.5-year payback at US$3,650/oz gold, with a 15.2-year mine life")
    eq("the headline is not joined to the body", sorted(x["npv_after_tax"] for x in a["scenarios"]),
       [695.6e6, 1.03e9])
    a = analyse("Northcliff Announces Results of Feasibility Study Update",
                "Financial Results\nPre-Tax\nPost-Tax\nUndiscounted Cash Flow\n$ 34,527 M\n$ 19,896 M\n"
                "Net Present Value (8%)\n$ 12,290 M\n$ 6,915 M\nInternal Rate of Return (IRR)\n68.3 %\n49.8 %")
    eq("a pre-tax / post-tax table is one scenario",
       [(x["npv_pre_tax"], x["npv_after_tax"], x["irr_pre_tax_pct"], x["irr_after_tax_pct"]) for x in a["scenarios"]],
       [(12.29e9, 6.915e9, 68.3, 49.8)])

    # 1.0.2 -- the study a restatement comes from (Justin, 2026-09-21)
    T = C.study_type
    eq("a Pre-feasibility Study is not also a Feasibility Study (MNO.TO)",
       T("Meridian Announces Closing of C$50 Million LIFE Offering",
         'The Pre-feasibility Study technical report (the "PFS Technical Report") dated March 31, 2025, entitled: '
         '"Cabacal Gold-Copper Project NI 43-101 Technical Report and Pre-feasibility Study" outlines a base case '
         'after-tax NPV5 of USD 984 million and 61.2% IRR'), "PFS")
    eq("'Pre -Feasibility', spaced (ETL.V)",
       T("E3 Lithium Provides Notice of Annual General Meeting",
         "The Clearwater Pre - Feasibility Study outlined a 1.13 Mt LCE reserve with an after-tax NPV(8%) of "
         "USD 3.7 Billion with a 24.6% IRR"), "PFS")
    eq("the study the figures' own sentence names beats a headline about the next one (MNO.TO)",
       T("Meridian Appoints Ausenco Brazil as Lead Engineer for the Cabacal Definitive Feasibility Study",
         "Cabacal's Pre-Feasibility Study (effective date March 10, 2025) delivered strong economic results with a "
         "base case after-tax NPV5 of USD 984 million and 61.2% IRR"), "PFS")
    eq("work toward the next study after the figures is not their study (SURG.V)",
       T("Surge Copper's Berg Project Selected for Canada Investment Summit Dealbook",
         "The Company completed a Pre-Feasibility Study for the Project in June 2026 outlining an approximately "
         "28-year mine life and an after-tax NPV8% of C$4.6 billion. The Company is currently advancing "
         "feasibility-level technical work and a Feasibility Study is underway."), "PFS")
    eq("a figure broken over lines still anchors (NILI.V)",
       T("Surge Announces IR Agreements",
         "The recently completed PEA reported an after-tax NPV\n8\n% US $9.17 Billion and after-tax IRR of 22.8%. "
         "Surge has engaged Fluor to lead the Pre-Feasibility Study."), "PEA")
    eq("'Preliminary Economic Study' is a PEA (VZLA.TO)",
       T("Vizsla Silver Issues Annual Equity Grant",
         "The Company recently completed a Preliminary Economic Study for Panuco in July 2024 which highlights "
         "an after-tax NPV5% of US$1.1B, 86% IRR"), "PEA")
    eq("'The FS will build on the PFS' -- the figures are the PFS's (TAU.V)",
       T("Thesis Gold & Silver Commences 2026 Exploration and Project Advancement Programs",
         'The FS will build on the Prefeasibility Study ("PFS") announced in December 2025 that outlined an '
         "after-tax NPV5% of C$2.37 billion, an after-tax IRR of 54.4%"), "PFS")
    eq("'The FS' abbreviation (GPH.V)",
       T("Graphite One's Project Plan Posted on the FAST-41 Dashboard",
         "Resources increased to 322% of the PFS resource. The FS, effective March 25, 2025, projects a post-tax "
         "internal rate of return of 27%, using an 8% discount rate, with a net present value of $5.03 billion"),
       "FS")
    eq("a heading line belongs to the figures under it (AVL.TO)",
       T("Avalon Engages Consultant to Facilitate Lake Superior Lithium Feasibility Study",
         "said the consultant.\nLSLi PEA Project Highlights:\nAfter-tax Net Present Value of Cdn $4.1 billion "
         "at an 8% discount rate"), "PEA")

    # the facts-store round trip has to come back the same
    recs = extract("Standard Lithium Announces PEA for the Smackover Project",
                   "The PEA uses a discount rate of 8%. NPV (After-Tax) | $ million | 4,992")
    back = to_prediction(recs)
    eq("round trip keeps the figure", back["scenarios"][0]["npv_after_tax"], 4992e6)
    eq("round trip keeps the rate", back["scenarios"][0]["discount_pct"], 8.0)

    # 1.0.3 -- one release, two studies (Justin, 2026-09-21)
    a = analyse("Ivanhoe Mines announces update on Platreef, the world's largest precious metals mine under development",
                "In reference to the sensitivity tables in the 2025 IDP, and accounting for only the increase in "
                "platinum and palladium prices at current prices, the net present value (NPV8%) of the Phase 2 "
                "feasibility study at current spot prices is over 70% higher, at approximately $2.7 billion. In "
                "addition, the sensitivity tables in the Preliminary Economic Assessment (PEA) for the Phase 3 "
                "expansion indicate that the NPV8% increases by approximately 60%, to over $5.0 billion. This is "
                "based on platinum and palladium price assumptions of $1,550 and $1,700 per ounce, respectively.")
    eq("IVN one study per release", (a["study_type"], len({r["npv_after_tax"] for r in a["scenarios"]})), ("PEA", 1))
    eq("IVN keeps the PEA figure", [r["npv_after_tax"] for r in a["scenarios"]], [5.0e9])
    a = analyse("Centerra Gold Reports Fourth Quarter and Full Year 2025 Results",
                "In January 2026, Centerra published an updated mineral resource and the results of a PEA for the "
                "Kemess project in British Columbia, showing robust economics including an after-tax net present "
                "value (5%) (NPV5%) of $1.1 billion and an after-tax internal rate of return (IRR) of 16%, using "
                "long-term pricing of $3,000 per ounce of gold. At commodity prices of approximately $4,500 per "
                "ounce of gold, the after-tax NPV 5% increases to $2.8 billion and the IRR increases to 29%.\n\n"
                "The PFS reaffirms Mount Milligan's strong economics, with an after-tax NPV5% of approximately $1.5 "
                "billion at long-term gold and copper price assumptions of $2,600 per ounce and $4.30 per pound.")
    eq("CG drops the other study's figure", 1.5e9 in [r["npv_after_tax"] for r in a["scenarios"]], False)
    eq("CG keeps the Kemess PEA", (a["study_type"], 1.1e9 in [r["npv_after_tax"] for r in a["scenarios"]]), ("PEA", True))
    # ECON 1.0.8: capital and payback written in summary tables, and studies credited to someone else
    pe = C.project_economics
    eq("capex on the next line", pe("Initial capital cost: \n$128.6M\nAverage annual production: \n~65,400 oz")["initial_capex"], 128.6e6)
    eq("capex label broken across lines", pe("with initial \nCAPEX of $607.1 million\n\u2022 The project")["initial_capex"], 607.1e6)
    eq("start-up project capex", pe("Industry low start-up project \nCapital Expenditures (CapEx) of $155 million \nincluding")["initial_capex"], 155e6)
    eq("life-of-project total is not capex", pe("Stage 1 initial capital cost estimated at $1.1 billion. Total \ncapital cost of "
                                                "$3.3 billion over life of project.\nCapital Costs $3.3 B\n")["initial_capex"], 1.1e9)
    eq("sustaining over LOM leaves initial", pe("Total initial capital cost (\"capex\") of $58 M and sustaining capex of "
                                                "$77 M over the LOM")["initial_capex"], 58e6)
    eq("a table heading is not the label", pe("Total Capital Costs\n\nProcessing Plant $17.3 million.")["initial_capex"], None)
    def pay(body):
        sc = analyse("X Announces PEA", body)["scenarios"]
        return sc[0]["payback_years"] if sc else "no row"
    eq("payback on the next line", pay("After-tax NPV (5%) of US$215.8M.\nAfter-tax payback period:\n1.7 years (standalone)"), 1.7)
    eq("payback Year cell", pay("After-Tax NPV (8%) of US$130 million.\nAfter-Tax Simple Payback Year 4.7\nNotes"), 4.7)
    eq("payback in words", pay("After-tax NPV5% of US$633 million and an anticipated payback of nine months."), 0.75)
    eq("sub-two-year is not a figure", pay("After-tax NPV of US$1.71 billion, a sub-two-year payback."), None)
    eq("owner: paid piece", C.study_owner_name("A Positive PEA Just Landed", "Issued on behalf of Rua Gold Inc.\n\nWith gold"), "Rua Gold Inc.")
    eq("owner: runs on", C.study_owner_name("x", "Issued on behalf of Greenland Mines Ltd. Wheaton just closed"), "Greenland Mines Ltd.")
    eq("owner: commentary", C.study_owner_name("Analyst Note", "News Commentary\n\n\u2014 Rua Gold Inc. (TSX: RUA) (NZX: RGI) "
                                               "(\"RUA GOLD\" or the \"Company\") has released the results of a positive "
                                               "Preliminary Economic Assessment (\"PEA\")"), "Rua Gold Inc.")
    eq("owner: not a verb", C.study_owner_name("XXIX Metal Publishes Opemiska's Preliminary Economic Assessment Technical Report", ""), None)
    # ---- 1.0.10 (reader review 2026-09-29)
    a = analyse("Voyageur Submits Permit Application",
                "The PEA for the Frances Creek Project outlined a low-cost development. Base Case Economics (8% discount "
                "rate). Metric Pre-Tax After-Tax Net Present Value (NPV) $464 million $344 million Internal Rate of Return "
                "(IRR) 168% 137% Total Project Cash Flow (10 years cumulative) $839 million $626 million.")
    s = a["scenarios"]
    eq("1.0.10 flattened pre/after-tax columns", [(x["npv_pre_tax"], x["npv_after_tax"], x["irr_pre_tax_pct"], x["irr_after_tax_pct"]) for x in s],
       [(464e6, 344e6, 168.0, 137.0)])
    a = analyse("Kinross proceeding with value-enhancing Tasiast 24k project",
                "Based on the results of the completed Tasiast 24k feasibility study, the project has an after-tax NPV "
                "of Tasiast 24k and an IRR of 60%.")
    eq("1.0.10 'Tasiast 24k' is not money", [x["npv_after_tax"] for x in a["scenarios"]], [None] * len(a["scenarios"]))
    a = analyse("OceanaGold Reports Second Quarter 2020 Results",
                "The Company delivered the Waihi District PEA with after-tax IRR of 51%, net present value (\u201cNPV\u201d) of "
                "$665 mi llion and 2.2 million gold ounces produced over 16 years.")
    eq("1.0.10 split magnitude, ounces are not money", [x["npv_after_tax"] for x in a["scenarios"]], [665e6])
    a = analyse("Integra Announces Simplified Strategy",
                "The PFS demonstrates an after-tax NPV5% of US$314 million. Pre-production Capital K US$ 278,092 288,097 10,005 -3%")
    eq("1.0.10 a K US$ table header", [x["initial_capex"] for x in a["scenarios"]], [278092e3])
    a = analyse("A Positive Gold-Antimony PEA Just Landed",
                "Issued on behalf of Rua Gold Inc. With gold at record highs, the after-tax NPV5% of US$42M at base case.")
    eq("1.0.10 paid article", (a["is_economic_study"], a["reason"]), (False, "paid_article"))
    a = analyse("Trillion Announces Program Update",
                "The report, prepared in accordance with COGEH, identified contingent resources. 2C Contingent Resource of "
                "27.6 MMbbl, with an unrisked NPV-10 of US$733.5 million. Light oil confirmed with 38 metres of net pay.")
    eq("1.0.10 oil and gas", (a["is_economic_study"], a["reason"]), (False, "not_mining"))
    eq("1.0.10 a lithium brine in an oil field is mining", not_own_study("E3 Lithium Outlines Clearwater Project Pre-Feasibility Study",
       "Lithium brine from the Leduc oil field wells; crude oil and natural gas producers operate nearby. Mineral Reserves of "
       "1.1 Mt LCE under NI 43-101. The lithium hydroxide plant ... LCE ... lithium."), None)
    eq("1.0.10 a company's own 'In other news' is not cut", bool(_RE_OTHER_NEWS.search("In other news, GoldQuest")), False)
    a = analyse("Troilus Announces Feasibility Study Results",
                "ECONOMIC RESULTS Base Case (Au: $1,975/oz; Cu: $4.05/lb; Ag: $23/oz) After-tax NPV @ 5% discount rate "
                "$884 million (C$1,208 million) After-tax IRR 14%")
    eq("1.0.10 a by-product price is not the case's name", [x["scenario"] for x in a["scenarios"]].count("$23/oz"), 0)
    eq("1.0.10 scoping study", C.study_type("FPX Nickel Scoping Study for a Nickel Sulphate Refinery", "After-tax NPV of US$445 million"), "PEA")
    # ---- 1.0.11 (ACC150 quick fix, 2026-09-30)
    a = analyse("Barksdale Announces San Javier Preliminary Economic Assessment",
                "Highlights include:\nPre-tax NPV (7%) of $111.8 million, with an IRR of 26.3% and payback of 3.8 years;\n"
                "After-tax NPV (7%) of $61.5 million, with an IRR of 18.1% and payback of 5.3 years;\n"
                "At $4.50/lb copper, the after-tax NPV (7%) increases significantly to $103.3 million, with an IRR of 24.8%;\n"
                "The project has been evaluated using a copper price of US$4.00/lb.")
    eq("1.0.11 a price point beside the base case is a sweep", [x["npv_after_tax"] for x in a["scenarios"]], [61.5e6])
    a = analyse("Wallbridge Completes Updated PEA",
                "\u2022 After-tax NPV of $706 million at base case gold price of US$2,200/oz at a 5% discount rate.\n\n"
                "Sensitivities\nThe economic analysis is significantly influenced by gold prices. At a gold price of US$3,000/oz, "
                "the Project generates an after-tax NPV of $1,381.5 million with a payback period of 2.4 years.")
    eq("1.0.11 a price under a sensitivity heading is a sweep ('$1,381.5 million')", [x["npv_after_tax"] for x in a["scenarios"]], [706e6])
    a = analyse("First Mining Files Updated PEA",
                "PEA Highlights\n\u2022 $1.23 billion pre-tax NPV5% at US$1,300/oz gold ($1.75 billion at $1,500/oz gold)\n"
                "\u2022 $841 million after-tax NPV5% at US$1,300/oz gold ($1.22 billion at $1,500/oz gold)")
    eq("1.0.11 an aside at another price is a sweep", [(x["npv_pre_tax"], x["npv_after_tax"]) for x in a["scenarios"]], [(1.23e9, 841e6)])
    a = analyse("McEwen Files Grey Fox Prefeasibility Study",
                "\u2022 Base case at $3,000 per ounce gold: cash costs of $1,833 per ounce; post-tax NPV (5%) of $282 million, IRR of "
                "24.8% and payback of 4.6 years.\n\u2022 Enhanced case at $4,500 per ounce gold: cash costs of $2,042 per ounce; post-tax "
                "NPV (5%) of $841 million, IRR of 55% and payback of 2.3 years.")
    eq("1.0.11 a case the company names stays", [x["npv_after_tax"] for x in a["scenarios"]], [282e6, 841e6])
    a = analyse("GMV Minerals Files Updated Mexican Hat PEA",
                "\u2022 The PEA returns an after-tax NPV at a 5% discount rate of US$268.3 million using a US$2,500 per ounce gold price.\n"
                "\u2022 Based on price sensitivity analysis at approximately the current price of US$3,350 per ounce of gold, the "
                "project returns an after-tax NPV at a 5% discount rate of US$538.1 million.")
    eq("1.0.11 the current price is a case", len(a["scenarios"]), 2)
    eq("1.0.11 an IRR equal to the rate is the rate", _fix_rates({"discount_pct": 5.0, "irr_after_tax_pct": 5.0, "irr_pre_tax_pct": 44.0,
                                                                  "npv_after_tax": 30e6, "npv_pre_tax": 38e6})["irr_after_tax_pct"], None)
    eq("1.0.11 an IRR below the rate with a positive NPV", _fix_rates({"discount_pct": 8.0, "irr_after_tax_pct": 0.0, "irr_pre_tax_pct": None,
                                                                       "npv_after_tax": 1.5e9, "npv_pre_tax": None})["irr_after_tax_pct"], None)
    eq("1.0.11 a negative NPV below the rate is consistent", _fix_rates({"discount_pct": 5.0, "irr_after_tax_pct": 4.9, "irr_pre_tax_pct": None,
                                                                         "npv_after_tax": -6e6, "npv_pre_tax": None})["irr_after_tax_pct"], 4.9)
    a = analyse("Benchmark Announces Positive Preliminary Economic Assessment for the Lawyers Project",
                "PEA Highlights:\nPre-tax NPV 5% of C$ 921M, IRR 30.5%, and 2.1-year payback\n"
                "After-tax NPV 5% of C$ 577M, IRR 23.5%, and 2.7-year payback\n"
                "Project Economics | Pre-Tax: | NPV | 5% | C$ million | 921 | IRR | % | 30.5 |")
    s = a["scenarios"][0]
    eq("1.0.11 the after-tax IRR is the one stated with the after-tax NPV", (s["irr_pre_tax_pct"], s["irr_after_tax_pct"]), (30.5, 23.5))
    m = _merge_same_name([{"scenario": "base case US$4.70/lb", "basis": "real", "npv_after_tax": -6e6, "npv_pre_tax": None,
                           "irr_after_tax_pct": 4.9, "irr_pre_tax_pct": None, "payback_years": 7.5},
                          {"scenario": "base case US$4.70/lb", "basis": "real", "npv_after_tax": None, "npv_pre_tax": None,
                           "irr_after_tax_pct": 0.0, "irr_pre_tax_pct": None, "payback_years": 7.5}])
    eq("1.0.11 one scenario name is one row", [(x["npv_after_tax"], x["irr_after_tax_pct"]) for x in m], [(-6e6, 4.9)])
    a = analyse("Southern Silver Extends Closing of Non-Brokered Private Placement",
                "For more information on the current economic assessment of the CLM Project please refer to the following link:\n"
                "https://southernsilverexploration.com/news/2024/southern-silver-announces-updated-pea-on-cerro-las-\n"
                "minitas-us-501m-after-tax-npv5-21-irr-48-month-payback/\nThis press release shall not constitute an offer.")
    eq("1.0.11 a URL slug is not a statement", a["scenarios"], [])
    eq("1.0.11 a royalty holder recaps its operators' studies",
       not_own_study("Osisko Announces Preliminary Q4 2021 Deliveries and Portfolio Update",
                     "Montreal, January 10, 2022 - Osisko Gold Royalties Ltd (the \u201cCorporation\u201d or \u201cOsisko\u201d) (OR: TSX) is "
                     "pleased to provide an update. Osisko Mining Inc. released an updated PEA with an after-tax NPV of $1.5 billion."),
       "royalty_holder")
    eq("1.0.11 another company's release, relayed",
       not_own_study("Vulcan Minerals Inc. - Atlas Salt Delivers Positive Feasibility Study",
                     "St. John's - Vulcan Minerals Inc. (\u201cthe Company\u201d - \u201cVulcan\u201d TSX-V: VUL) is pleased to announce that "
                     "Atlas Salt Inc., an affiliated company, has released the results of a Feasibility Study with a pre-tax NPV8 of "
                     "$1.02 billion."), "relayed_release")
    eq("1.0.11 the issuer's own study is not relayed",
       not_own_study("Kootenay Silver Announces Positive PEA",
                     "Kootenay Silver Inc. (the \"Company\") is pleased to announce the results of a positive PEA with an after-tax "
                     "NPV5% of US$763 million."), None)
    a = analyse("Millennial Potash Completes Positive PEA with After-Tax NPV(10) of $1.07B for its Banio Potash Project",
                "The PEA is based on the Mineral Resource Estimate completed by ERCOSPLAN early in 2024 (see Press Release dated "
                "Jan. 16, 2024). The PEA outlines an after-tax NPV10 of US$1.07 billion and an after-tax IRR of 32.6%.")
    eq("1.0.11 a back-reference to the resource estimate is not a recap", a["context"], "announced")
    a = analyse("Canagold Resources Tenders Proposals for New Polaris Feasibility Study",
                "The 2019 PEA reported an after-tax NPV5% of C$469 million and an after-tax IRR of 56% at US$1,500 per ounce gold.")
    eq("1.0.11 a headline about the next kind of study", (a["study_type"], a["context"]), ("PEA", "background"))
    a = analyse("Rock Tech Lithium completes Bankable Project Study for its Guben Converter Project",
                "VANCOUVER - Rock Tech Lithium Inc. (the \"Company\") is pleased to announce the completion of a bankable project "
                "study (\"BPS\") for its converter. The BPS shows a pre-tax NPV8% of US$1,219 million.")
    eq("1.0.11 the lead announces the study", a["context"], "announced")
    a = analyse("Deep-South Commissions Update of the Haib Copper PEA to Reflect Higher Copper Prices",
                "The 2021 PEA reported an after-tax NPV of US$957 million and an after-tax IRR of 29.7% at $3.00/lb copper.")
    eq("1.0.11 commissioning the next update is not announcing", a["context"], "background")
    a = analyse("Wallbridge Mining Completes Updated Positive Preliminary Economic Assessment of Fenelon Gold Project",
                "All results herein are reported in Canadian dollars unless otherwise indicated.\n\u2022 After-tax Net Present Value "
                "(\"NPV\") of $706 million at base case gold price of US$2,200 at a 5% discount rate")
    eq("1.0.11 'All results herein are reported in Canadian dollars'", a["scenarios"][0]["currency"], "CAD")
    # 1.0.11 key gate (Justin's answer key, 2026-09-30)
    a = analyse("Desert Gold Delivers Positive PEA for SMSZ Project",
                "The SMSZ Project demonstrates strong leverage to gold price, as illustrated in the sensitivity analysis presented "
                "in Table 2. At the base case scenario of US$2,500 per ounce, the Project yields an after-tax NPV (10%) of US$24 "
                "million and an after-tax IRR of 34%. At a higher gold price of US$3,000 per ounce, the after-tax NPV increases to "
                "US$41 million with an IRR of 51%. These sensitivities are presented for illustrative purposes only.")
    eq("1.0.11 'a higher gold price of' names a case", [x["npv_after_tax"] for x in a["scenarios"]], [24e6, 41e6])
    eq("1.0.11 a price named only by its change stays a sweep", bool(_RE_PRICE_CASE.search("At $4.50/lb copper, the after-tax NPV (7%) increases to ")), False)
    a = analyse("Allied Critical Metals Further Highlights Rapid Payback and Capital Efficiency from Borralha PEA",
                "After-tax NPV(8%) of $473M and IRR of 48.8% at USD $1,000/mtu WO3.\n\nThe Company is providing the additional "
                "metrics below to facilitate investor understanding of project capital intensity, cash flow generation and payback "
                "presentation. For additional information, please see the news release dated March 2, 2026.")
    eq("1.0.11 a bare reference after a sentence about the economics is a recap", a["context"], "background")
    a = analyse("Tinka Reports Updated PEA for Ayawilca Project",
                "After-tax NPV8% of US$433M and IRR of 32% at $1.20/lb Zinc.\n\nExploration is focused at the adjacent copper-gold "
                "project, where we announced the discovery of high grade skarn zones. For details, please see the news release dated "
                "October 7, 2021.")
    eq("1.0.11 a bare reference after a sentence about something else is not", a["context"], "announced")
    # ---- 1.0.12 (FIX4, 2026-10-02)
    a = analyse("BacTech Announces updated Bankable Feasibility Study Results",
                "BacTech Environmental Corporation (the \"Company\") is pleased to announce updated results of its Bankable "
                "Feasibility Study.\nUpdated Key Economic Highlights:\n\u25cf Pre-tax NPV (Net Present Value with 5% di scount rate) "
                "of $60.7M (up 29.4% from $46.9M)\n\u25cf Pre-tax IRR (Internal Rate of Return) of 57.9% (up from 48%)\n"
                "\u25cf Assumed Purchase Prices of Concentrate - 65% of the contained gold value\n\u25cf Capital Cost of $17M")
    eq("1.0.12 a split 'di scount' and a '\u25cf' list are read", [(x["npv_pre_tax"], x["irr_pre_tax_pct"], x["discount_pct"])
                                                               for x in a["scenarios"]], [(60.7e6, 57.9, 5.0)])
    a = analyse("Panoro Delineating Expanded Gold Oxide Mineralization",
                "The anomalies can lead to increased project economic indicators of NPV and IRR. The Company is commencing a "
                "19,000 m drill program this month.")
    eq("1.0.12 '19,000 m drill program' is metres, not an NPV", a["scenarios"], [])
    a = analyse("Aclara Announces Updated PEA for its Flagship Carina Module",
                "Highlights\n\u2022 Robust economics\no After-tax Net Present Value (\"NPV\") of ~US$1.5 billion using an 8% discount "
                "rate pursuant to the base case price forecast\no 27% internal rate of return over the 22-year life of mine\n"
                "o After-tax NPV of ~US$2.2 billion using an 8% discount rate pursuant to the incentive price forecast by Argus\n")
    eq("1.0.12 a case named in words the core does not hold is a row",
       [(x["scenario"], x["npv_after_tax"]) for x in a["scenarios"]][1:], [("incentive price forecast", 2.2e9)])
    a = analyse("Moneta Announces Positive Results from Preliminary Economic Assessment",
                "After Tax NPV5% of C$236 million and IRR of 30% at US$1,500/oz gold\nHighly leveraged to the gold price with after "
                "tax NPV5% of C$423 million and 47% IRR at US$1,900 per ounce gold\nInitial capital of C$144 million\nAttractive "
                "alternative Toll Milling development option with after-tax NPV5% of C$197 million and IRR of 44%\n")
    eq("1.0.12 the next statement's case word does not name this figure",
       [x["scenario"] for x in a["scenarios"] if x["npv_after_tax"] == 423e6 and "option" in x["scenario"]], [])
    a = analyse("Hudbay De-risks Copper World Phase I with Enhanced Pre-Feasibility Study",
                "At a copper price of $3.75 per pound, the after-tax net present value (\"NPV\") of Phase I using an 8% discount "
                "rate is $1.1 billion and the internal rate of return (\"IRR\") is 19%. In the flotation only scenario, the project "
                "has an after-tax NPV (8%) of $863 million, an after-tax IRR of 18.7% and a payback period of 5.3 years at $3.75 "
                "per pound copper. At a copper price of $4.25 per pound, the flotation only NPV (8%) increases to $1.5 billion.")
    eq("1.0.12 'the flotation only scenario' is a case, its price change is not",
       [(x["npv_after_tax"], x["payback_years"]) for x in a["scenarios"]], [(1.1e9, None), (863e6, 5.3)])
    a = analyse("Denison Announces Results from Midwest ISR Preliminary Economic Assessment",
                "Base case post-tax Net Present Value (\"NPV\")(8%) of $965 million (100% basis) - with Denison's 25.17% interest "
                "in the project equating to a base-case after-tax NPV8% of $243 million.")
    eq("1.0.12 a holder's share of the NPV is not a case", [x["npv_after_tax"] for x in a["scenarios"]], [965e6])
    a = analyse("Lithium Americas Announces Positive Feasibility Study for Stage 1",
                "Average annual EBITDA of $233 million, after-tax NPV of $803 million (at a 10% discount rate) and after-tax IRR "
                "of 28.4% assuming a price of $12,000/t of battery-grade lithium carbonate sold")
    eq("1.0.12 EBITDA is not the NPV", [(x["npv_after_tax"], x["irr_after_tax_pct"]) for x in a["scenarios"]], [(803e6, 28.4)])
    eq("1.0.12 a figure labelled after it is still the NPV ('(C$315 million) NPV5%')",
       _fix_other_metric("average annual EBITDA of US$88 million / post-tax US$250 million (C$315 million) NPV5% - Synergies",
                         {"npv_after_tax": 315e6}, [])["npv_after_tax"], 315e6)
    a = analyse("Noram Announces New Resource Estimate for Zeus Lithium Deposit",
                "Vancouver - Noram Lithium Corp. (\"Noram\" or the \"Company\") announces a resource. The strip ratio is similar to "
                "the adjacent Cypress Development Corp.'s Clayton Valley project. Cypress projected a low mining cash cost, "
                "giving the company a US$1.03B NPV at an 8% discount rate.")
    eq("1.0.12 a neighbour's study is not the issuer's", a["scenarios"], [])
    a = analyse("Buffalo Potash Completes Initial Drill Hole",
                "Buffalo Potash Corp. (\"Buffalo\" or the \"Company\") reports drilling. In 2025 it released its PEA for the Disley "
                "Project, prepared by Micon International Co Limited. The PEA outlined a phased plan with an estimated after-tax "
                "net present value (NPV) of US$1.1 billion at 8% and an IRR of 30%.")
    eq("1.0.12 the firm that prepared a study does not own it", [x["npv_after_tax"] for x in a["scenarios"]], [1.1e9])
    m = _merge_same_price([{"scenario": "$1,200/oz", "basis": "real", "discount_pct": 5.0, "npv_after_tax": 130e6, "irr_after_tax_pct": 17.0},
                           {"scenario": "base case $1,200 per ounce", "basis": "real", "discount_pct": 5.0, "npv_after_tax": 21e6,
                            "irr_after_tax_pct": 17.0}])
    eq("1.0.12 one price written twice is one scenario", [x["npv_after_tax"] for x in m], [130e6])
    m = _merge_same_price([{"scenario": "US$70 per pound", "basis": "real", "npv_after_tax": 238e6, "irr_after_tax_pct": 33.0},
                           {"scenario": "base case US$70 per pound", "basis": "real", "npv_pre_tax": 238e6, "npv_after_tax": 197e6,
                            "irr_after_tax_pct": 33.0}])
    eq("1.0.12 the row that reads both tax bases is kept", [(x.get("npv_pre_tax"), x["npv_after_tax"], x.get("irr_after_tax_pct")) for x in m],
       [(238e6, 197e6, 33.0)])
    m = _merge_same_price([{"scenario": "$2,250 /ounce", "basis": "real", "npv_pre_tax": 546e6, "npv_after_tax": 474e6},
                           {"scenario": "base case $2,250 /ounce", "basis": "real", "npv_pre_tax": 365e6, "npv_after_tax": 322e6}])
    eq("1.0.12 two full sets of figures at one price stay two rows", len(m), 2)
    r = _drop_rate_points([{"scenario": "base case $1,500/oz Au", "discount_pct": 10.0, "npv_after_tax": 42e6},
                           {"scenario": "$1,650/oz Au", "discount_pct": 5.0, "npv_after_tax": 160e6},
                           {"scenario": "$4.00/lb", "discount_pct": 13.0, "npv_after_tax": 180e6},
                           {"scenario": "spot $1,800/oz Au", "discount_pct": 5.0, "npv_after_tax": 216e6}])
    eq("1.0.12 a price point at another rate is a sweep; another metal's or a named case is not",
       [x["npv_after_tax"] for x in r], [42e6, 180e6, 216e6])
    # ---- 1.0.13 (FIX5, 2026-10-04)
    def one(head, body, *keys):
        sc = analyse(head, body)["scenarios"]
        return [tuple(x.get(k) for k in keys) for x in sc]
    eq("1.0.13 a mine life in words", one("X Announces PEA", "After-tax NPV (5%) of US$99 million and IRR of 56%. Average "
       "production of 51,200 oz over an eight - year mine life.", "mine_life_years"), [(8.0,)])
    eq("1.0.13 'Life of mine is forecast at nine years'", one("X Files PEA", "After-tax NPV (8%) of C$342.9 million.\n"
       "Life of mine is forecast at nine years; project duration is 11 years", "mine_life_years"), [(9.0,)])
    eq("1.0.13 a hyphenated life-of-mine", one("X Drills", "After-tax NPV (5%) of US$329 million and IRR of 28.2%. Annual "
       "production of 75,900 oz for a total life-of-mine of 11.2 years.", "mine_life_years"), [(11.2,)])
    eq("1.0.13 'life-of-mine plan' is not a figure's label", _fix5_life("The life-of-mine plan comprises 17 years"),
       "The life-of-mine plan comprises 17 years")
    eq("1.0.13 an operating life", _fix5_life("six-year operating life"), "6-year mine life")
    eq("1.0.13 a U+2010 hyphen and a split decimal", _fix5_text("13\u2010year mine\u2010life; payback of 3. 6 years"),
       "13-year mine-life; payback of 3.6 years")
    eq("1.0.13 'Pre - Ta x' and 'I RR'", _fix5_text("Pre - Ta x NPV8 $2.3 billion Pre - Tax I RR 163%"),
       "Pre-Tax NPV8 $2.3 billion Pre-Tax IRR 163%")
    eq("1.0.13 'Payback' keeps its case", _fix5_text("Payback Period 2.58 Years; a 2.7 year pay -back period"),
       "Payback Period 2.58 Years; a 2.7 year payback period")
    eq("1.0.13 after-tax payback over pre-tax", one("X Announces PEA", "Pre-tax NPV5% of C$1.07 billion, after-tax NPV5% of "
       "C$588 million.\n\u2022 Pre-tax payback of 3.8 years; after-tax payback of 4.8 years", "payback_years"), [(4.8,)])
    eq("1.0.13 payback of initial capital, not the sensitivity", one("X Announces PFS", "After-tax NPV8% of $1,412.7 million "
       "and after-tax IRR of 33.4% for the base case at $3.00/lb copper. Estimated pre-tax and after-tax payback of initial "
       "capital within 2 years. At $2.00/lb copper, after-tax payback is 3 years.", "payback_years"), [(2.0,)])
    eq("1.0.13 a bracketed after-tax payback", one("X Engages", "a pre-tax NPV at a 5% discount rate of US$390.2 million "
       "(after-tax US$268.3 million) with a 1.53-year payback (1.82 year after-tax) using a US$2,500 per ounce gold price.",
       "npv_pre_tax", "npv_after_tax", "payback_years"), [(390.2e6, 268.3e6, 1.82)])
    eq("1.0.13 the unlabelled IRR takes its sentence's basis", one("X Announces PFS", "Pre-tax NPV8% of $1,935.2 million and an "
       "Internal Rate of Return of 38.0% for the base case. After-tax NPV8% of $1,412.7 million and after-tax IRR of 33.4% "
       "for the base case.", "irr_pre_tax_pct", "irr_after_tax_pct"), [(38.0, 33.4)])
    eq("1.0.13 a trailing tax word", one("X Announces PEA", "Attractive economics with NPV (7%) of C$440.1 M (US$339.8 M) and "
       "IRR of 17.1% pre-tax and NPV (7%) of C$215.0 M (US$166.0 M) and IRR of 12.7% after tax; and",
       "npv_pre_tax", "npv_after_tax", "irr_pre_tax_pct", "irr_after_tax_pct"), [(440.1e6, 215e6, 17.1, 12.7)])
    eq("1.0.13 a bracketed figure on the other basis", one("X Grants Options", "A 2018 PEA outlined a pre-tax IRR of 34.1% "
       "(25.2% post-tax) and NPV8% of $230 million ($128 million post-tax).",
       "npv_pre_tax", "npv_after_tax", "irr_pre_tax_pct", "irr_after_tax_pct"), [(230e6, 128e6, 34.1, 25.2)])
    eq("1.0.13 a split IRR figure is not moved", _fix5_tax("IRR of 3 1% (33% pre-tax)", [{"irr_pre_tax_pct": 1.0,
       "irr_after_tax_pct": None, "npv_pre_tax": None, "npv_after_tax": 709e6, "discount_pct": 8.0}])[0]["irr_after_tax_pct"], None)
    eq("1.0.13 a rounded figure stated exactly in the table", one("X Confirms Feasibility Study",
       "After-Tax NPV (5%) of US$1.1 Billion with an After-Tax IRR of 27.8% at $2,500/oz\n\nSensitivity Analysis\n"
       "Gold Price $2,100 $2,500 $2,900 $3,300\nAfter-tax NPV5% ($M)  $524 $1,060   $1,610 $2,159\n"
       "After-tax IRR (%)  18.1  27.8  36.6 44.7\n", "npv_after_tax"), [(1.06e9,)])
    eq("1.0.13 two table figures round to it: left alone", _fix5_precise("After-Tax NPV5 $ million 2,247  2,249\n",
       [{"npv_after_tax": 2.2e9, "irr_after_tax_pct": None}])[0]["npv_after_tax"], 2.2e9)
    eq("1.0.13 the currency said across a line break", one("X Announces PFS", "All amounts \nare stated in U.S. dollars unless "
       "otherwise stated. After-tax NPV8% of $1,412.7 million.", "currency"), [("USD",)])
    eq("1.0.13 the currency of the NPV label's unit", _fix5_currency("NPV 5% after taxes and mining duties (M CAD) 54.4"), "CAD")
    eq("1.0.13 'in thousands of US dollars'", _fix5_currency("All amounts are expressed in thousands of US dollars"), "USD")
    eq("1.0.13 'Cashflow' is another metric", one("X Files PEA - After-Tax NPV of CAD$342.9 million",
       "Pre-tax Cashflow = CAD$709.4 million, NPV = CAD$385.1 million, IRR = 46.5% p.a.", "npv_pre_tax"), [(385.1e6,)])
    eq("1.0.13 a split capital figure", _fix5_capex("estimated to be $6 92 million. Capital of $692 million"),
       "estimated to be $692 million. Capital of $692 million")
    eq("1.0.13 direct capital costs are a component", _fix5_capex("Total Direct Capital Costs C$M 634.3"), "Total Direct Costs C$M 634.3")
    eq("1.0.13 each restated study's own mine life and capital", one("X Announces Acquisition",
       "The 2025 PEA for the first project demonstrated an approximate 6-year underground mine life, producing 40 koz gold per "
       "year with initial capex of $36 million returning an after-tax NPV 5% of $227 million at $3,000/oz. The 2023 PEA for "
       "the second project demonstrated an 8.2-year open pit mine life, producing 60 koz gold per year with initial capex of "
       "$28 million returning an after-tax NPV 5% of $151 million at $1,600/oz.", "initial_capex", "mine_life_years"),
       [(36e6, 6.0), (28e6, 8.2)])
    # ---- 1.0.14 (FIX8, 2026-10-06): throughput, annual production and unit costs that cannot be right
    def pf(text, *keys):
        r = C.project_economics(text)
        return tuple(r[k] for k in keys)
    eq("FIX8 a year count is not production", pf("207 koz average annual gold production in the first 5 years at an AISC of "
       "US$1,098/oz", "annual_production", "production_unit"), (207e3, "oz"))
    eq("FIX8 a mine life is not production", pf("outlines 17.4 Moz AgEq annual production over an initial 9.4-year mine life",
       "annual_production", "production_unit"), (17.4e6, "oz"))
    eq("FIX8 money is not production", pf("a 17% increase in average annual gold production, approximately $0.8 billion in "
       "after-tax free cash flow", "annual_production"), (None,))
    eq("FIX8 MTU is a unit, not a magnitude", pf("average annual production of 598,000 MTU WO 3 and 4.2 M lbs Mo",
       "annual_production", "production_unit"), (598e3, "mtu"))
    eq("FIX8 metric tons", pf("annual production is expected to be 750 metric tons per annum of magnets",
       "annual_production", "production_unit"), (750.0, "t"))
    eq("FIX8 a table's footnote cell", pf("Average annual production of approximately 4.9 | [1] | million pounds U3O8",
       "annual_production", "production_unit"), (4.9e6, "lb"))
    eq("FIX8 metal words before the unit", pf("Average annual production of 37.0 million silver equivalent ounces",
       "annual_production", "production_unit"), (37e6, "oz"))
    eq("FIX8 a product is not throughput", pf("estimated production levels of 248tpa Dysprosium and 36tpa Terbium oxides",
       "throughput_tpd"), (None,))
    eq("FIX8 a mining rate is not throughput", pf("The peak mining rate is expected to be 81.0 Mtpa over a life of mine",
       "throughput_tpd"), (None,))
    eq("FIX8 processing rate", pf("Projected annual processing rate increased to a baseline of 7.5 Mtpa", "throughput_tpd"),
       (20547.9,))
    eq("FIX8 a footnote digit is not the cost", pf("Total Cash Cost1, $/oz 1,516 1,448 929", "opex", "opex_unit"),
       (1516.0, "oz"))
    eq("FIX8 a bracketed cost is negative", pf("Total Cash Costs of Silver (net of by-products) 4 $/oz (1.51)", "opex"),
       (-1.51,))
    eq("FIX8 negative cost keeps its sign", pf("Average cash cost (net of by-product credits) per pound of uranium of "
       "negative $121/lb U3O8", "opex", "opex_unit"), (-121.0, "lb U3O8"))
    eq("FIX8 the commodity after the unit", pf("Cash costs of C$17.48/lb Mo and AISC of C$19.79/lb Mo", "opex", "opex_unit"),
       (17.48, "lb Mo"))
    eq("FIX8 per tonne of lithium carbonate", pf("Operating Cost of US$4,719/tonne Lithium Carbonate", "opex", "opex_unit"),
       (4719.0, "t LCE"))
    eq("FIX8 plain release unchanged", pf("Average annual production of 150,000 ounces of gold over a 12-year mine life at a "
       "mill throughput of 5,000 tonnes per day, operating costs of US$45.20 per tonne milled and AISC of US$1,050/oz",
       "annual_production", "throughput_tpd", "opex", "opex_unit", "aisc"), (150e3, 5000.0, 45.2, "t", 1050.0))
    # ---- 1.0.14b (FIX8, 2026-10-06): real figures the first 1.0.14 candidate lost
    eq("FIX8b a figure glued to its unit", pf("with average annual production of 207koz, and peak production of 320koz",
       "annual_production", "production_unit"), (207e3, "oz"))
    eq("FIX8b tonnes glued", pf("Avg. LOM annual production of 217,700t of high-quality spodumene concentrate",
       "annual_production", "production_unit"), (217700.0, "t"))
    eq("FIX8b ozs", pf("Average annual gold production of 149,000 ozs over first 5 years", "annual_production",
       "production_unit"), (149e3, "oz"))
    eq("FIX8b more than", pf("an average annual production of more than 6,800,000 oz of Ag", "annual_production"), (6.8e6,))
    eq("FIX8b between ... and", pf("estimated annual gold production of between 400,000 and 435,000 ounces",
       "annual_production"), (417500.0,))
    eq("FIX8b production rate of", pf("average annual production rate of 225,000 tonnes of zinc", "annual_production",
       "production_unit"), (225e3, "t"))
    eq("FIX8b ounces per year", pf("generating an average of 95,600 ounces of gold per year over a 10-year mine life",
       "annual_production", "production_unit"), (95600.0, "oz"))
    eq("FIX8b ore per year is not production", pf("Open-pit mine with annual production rate of 2 million tonnes of ore per year",
       "annual_production"), (None,))
    eq("FIX8b a stream's ounces are not production", pf("the stream will deliver 5,000 ounces of gold per year to the holder",
       "annual_production"), (None,))
    eq("FIX8b $US and a footnote on the unit", pf("All-In Sustaining Cost (AISC) of $US892/oz gold", "aisc", "aisc_unit"),
       (892.0, "oz Au"))
    eq("FIX8b footnote digit after the unit", pf("All-in sustaining costs of $925/oz1 and NPV", "aisc"), (925.0,))
    eq("FIX8b per ton", pf("Estimated processing operating costs are US$27/ton.", "opex", "opex_unit"), (27.0, "t"))
    eq("FIX8b hyphenated tonne-per-day", pf("a plan to ramp up to a 750 tonne-per-day operation", "throughput_tpd"), (750.0,))
    eq("FIX8b the mill named after the rate", pf("a 1.8 Mtpa (\"million tonnes per year\") mill throughput", "throughput_tpd"),
       (4931.5,))
    # PROJ_NAMES_V1: the fingerprint takes the project-name helper code this reader runs, and nothing of Resources
    b = FP.borrowed_source(PN, "PN", __file__)
    eq("fingerprint: helper code used", ("def primary(" in b, "def clean(" in b), (True, True))
    eq("fingerprint: helper self-test not used", "def _selftest(" in b, False)
    eq("fingerprint: Resources not followed", any(m.endswith("resources") for m, _a in FP.portal_imports(__file__)), False)
    eq("fingerprint: stable", _code_sha(), SPEC.code_sha)
    print("economics %s: %s" % (VERSION, "ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if self_test(verbose=True) else 0)
