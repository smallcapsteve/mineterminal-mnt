"""News release categorizer (v2 — #67 cleanup).

Assigns zero or more of 9 categories to a release based on regex signals.
v2 changes vs v1:
  * NEW category: Mergers & Acquisitions (was previously folded into Corporate Updates)
  * TIGHTENED Marketing: drop bare "corporate presentation"/"investor presentation"/
    "CEO interview" matches (cause of most false positives via sidebar/citation
    boilerplate); add explicit "investor awareness campaign" / "market awareness"
    patterns; restrict Marketing to LEAD (title + first 1500 chars of body) so
    related-posts widgets and citation footnotes can't trigger it.
  * IMPROVED Drill Results: add bare "drill program" (with begin/commence/resume
    verbs), "drill targets" / "high-priority drill targets", and
    "IP/geophysical/airborne survey results...drill" patterns.
  * Sidebar trimming: cut body at first " / • <Date> / " bullet sentinel or
    "Recent News" heading before pattern-matching, so sidebar/related-posts
    text can't influence categorization for any rule.

Categories (in output order):
  Financings, Drill Results, Resource Estimates, Economic Studies,
  Production Results, Financials, Mergers & Acquisitions,
  Marketing Announcement, Corporate Updates
"""
from __future__ import annotations
import re
from typing import Iterable

CATEGORIES: tuple[str, ...] = (
    "Financings",
    "Drill Results",
    "Resource Estimates",
    "Economic Studies",
    "Production Results",
    "Financials",
    "Mergers & Acquisitions",
    "Marketing Announcement",
    "Corporate Updates",
)

CODE_TO_CAT = {
    "fin": "Financings",
    "drl": "Drill Results",
    "res": "Resource Estimates",
    "eco": "Economic Studies",
    "prd": "Production Results",
    "fns": "Financials",
    "mna": "Mergers & Acquisitions",
    "mkt": "Marketing Announcement",
    "cor": "Corporate Updates",
}
CAT_TO_CODE = {v: k for k, v in CODE_TO_CAT.items()}

# ----- Sidebar / related-posts trim ----------------------------------------
# Many scraped bodies contain a tail block of OTHER recent releases ("sidebar
# leakage"). Pattern: " / • <Month> <day>, <year> / • <Category> / " bullets,
# or a "Recent News"/"Latest News" heading. Cut body at the first such marker.
_BODY_TAIL_BULLET = re.compile(
    r"\n*\s*/?\s*•\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{1,2},\s*\d{4}\s*/",
    re.I,
)
_BODY_TAIL_HEADING = re.compile(
    r"\n*\s*(?:Recent\s+(?:News|Posts|Articles|Releases)|Latest\s+News|"
    r"Other\s+News|More\s+News|Related\s+(?:Posts|News|Articles)|"
    r"News\s+Archive|You\s+May\s+Also\s+Like|Keep\s+Reading)\b",
    re.I,
)
# Prev/Next pagination chrome at the bottom of release pages — e.g.
#   • Prev - MAX POWER CLOSES $20.5 MILLION BROKERED OFFERING WITH ERIC SPROTT
#   • Next - MAX POWER ANNOUNCES AGSM RESULTS
# These often reference unrelated press releases by title, so anything
# after them can match financing / M&A / drill rules incorrectly.
_BODY_TAIL_PREVNEXT = re.compile(
    r"\n\s*•?\s*(?:Prev|Next|Previous)\s*[-–—]\s*[A-Z]",
)


def _trim_body(b: str) -> str:
    """Cut body at first sidebar-like marker. Best-effort — if no marker, return b."""
    cuts: list[int] = []
    m = _BODY_TAIL_BULLET.search(b)
    if m:
        cuts.append(m.start())
    m = _BODY_TAIL_HEADING.search(b)
    if m:
        cuts.append(m.start())
    m = _BODY_TAIL_PREVNEXT.search(b)
    if m:
        cuts.append(m.start())
    if not cuts:
        return b
    return b[: min(cuts)]


# ----- Financings -----------------------------------------------------------
_FIN = re.compile(
    r"\b("
    r"private\s+placement|"
    r"bought\s+deal|"
    r"(?:non[- ])?brokered\s+(?:private\s+)?(?:placement|offering|financing)|"
    r"closes?\s+(?:the\s+|a\s+|its\s+)?(?:non[- ])?(?:brokered\s+)?(?:private\s+)?(?:placement|offering|financing|subscription)|"
    r"announces?\s+(?:the\s+)?(?:closing\s+of\s+|extension\s+of\s+)?(?:a\s+|its\s+)?(?:non[- ])?(?:brokered\s+)?(?:private\s+)?(?:placement|offering|financing)|"
    r"upsize[sd]?\s+.{0,30}(?:financing|offering|placement)|"
    r"unit\s+offering|"
    r"flow[- ]?through\s+(?:common\s+)?(?:shares?|units?)|"
    r"subscription\s+receipts?|"
    r"(?:first|second|third|final|last)\s+tranche|"
    r"warrant\s+exercise\s+term|"
    r"extension\s+of\s+warrant|"
    r"up\s+to\s+C?\$[\d,.]+\s*(?:million|M\b)\s+(?:private\s+)?(?:placement|offering|financing)|"
    r"aggregate\s+gross\s+proceeds|"
    r"gross\s+proceeds\s+of\s+(?:approximately\s+)?C?\$[\d,.]+|"
    r"convertible\s+(?:loan|debenture|note|security)|"
    r"loan\s+financing|"
    r"acceleration\s+of\s+warrant|warrant\s+acceleration|"
    r"files?\s+(?:preliminary\s+)?non[- ]offering\s+prospectus|"
    r"short[- ]form\s+prospectus|"
    r"secured\s+(?:loan|debenture|note)\s+(?:facility|financing)|"
    r"credit\s+facility"
    r")\b",
    re.I,
)
_FIN_EXTRA = re.compile(
    r"(?:"
    r"\$\d[\d,.]*\s*(?:million|M\b|billion|B\b)?\s+(?:strategic\s+|equity\s+)?investment|"
    r"\$\d[\d,.]*\s*(?:million|M\b)?\s+(?:private\s+)?(?:placement|offering|financing)"
    r")",
    re.I,
)

# ----- Drill Results --------------------------------------------------------
# v2: added bare "drill program" (with begin/commence/resume verbs),
# "drill targets" / "high-priority drill targets",
# and IP/geophysical/airborne/magnetic survey results...(drill|targets).
_DRILL_HEAD = re.compile(
    r"\b("
    r"drill\s+results?|"
    r"drill\s+intercept|"
    r"drilling\s+results?|"
    r"drill\s+program(?:\s+(?:results?|update))?|"
    r"(?:commences?|commenced|begins?|began|resumes?|resumed|launch(?:es|ed)?|continues?|continued|completes?|completed|expands?|expanded|advances?|advanced)\s+(?:its\s+|the\s+|a\s+)?(?:phase\s+(?:[IV]+|\d+|one|two|three|four|five)\s+)?(?:drill(?:ing)?(?:\s+program)?|drill\s+targets?)|"
    r"(?:phase\s+(?:[IV]+|\d+|one|two|three|four|five)\s+)?drill\s+program\b|"
    r"(?:high[- ]?priority|priority|new|additional)\s+drill\s+targets?|"
    r"drill\s+targets?\s+(?:identified|confirmed|defined|established)|"
    r"identif(?:y|ies|ied)\s+(?:high[- ]?priority\s+|new\s+|additional\s+)?(?:drill\s+)?targets?|"
    r"survey\s+results?\s+confirm.{0,40}(?:targets?|drill|mineraliz)|"
    r"(?:IP|induced[- ]polarization|geophysical|airborne|magnetic|gravity|EM|electromagnetic|ZTEM|VTEM)\s+(?:survey\s+)?(?:results?|defines?|identifies?|confirms?)|"
    r"assay\s+results?|"
    r"(?:returns?|hits?|encounters?|intercepts?)\s+\d+(?:\.\d+)?\s*(?:m|metres?|meters?)|"
    r"\d+(?:\.\d+)?\s*(?:m|metres?|meters?)\s+(?:grading|@|of|averaging|at)\s*\d|"
    r"(?:high|bonanza)[- ]?grade\s+(?:assays?|intercepts?|intersect|results?)|"
    r"(?:best|significant)\s+(?:intersect|drill|assay|hole)|"
    r"intersects?\s+\d+(?:\.\d+)?\s*(?:m|metres?|meters?|g/t|%)|"
    r"hole\s+.{0,30}(?:returns?|intersects?|grades?)|"
    r"DDH[- ]?\w+.*?\s*(?:returns|intersects|grades)|"
    r"\d+(?:\.\d+)?\s*g\s*/\s*t(?:onne)?\s+(?:au|gold|silver|ag|cu|copper)|"
    r"discover(?:y|ies|ed|ing)\s+(?:of\s+)?(?:a\s+)?(?:new\s+)?(?:high[- ]grade|bonanza|ore\s+body|mineraliz)|"
    r"(?:grab|channel|surface|soil|chip|rock|trench)\s+sampl(?:e|es|ing)\s+(?:results?|returns?|confirms?|extend|intersect|grades?)|"
    r"sampling\s+(?:results?|returns?|confirms?|extends?|intersects?)|"
    r"mineralized\s+zones?\s+(?:at|with|grading|returning|extending)"
    r")\b",
    re.I,
)
_DRILL_BODY = re.compile(
    r"\b("
    r"assay\s+results?\s+(?:from|for|of)|"
    r"(?:drill\s+hole|drillhole|borehole)\s*[A-Z]*[- ]?\d+.*?(?:returned|intersected|graded)|"
    r"\d+(?:\.\d+)?\s*(?:m|metres?|meters?)\s+(?:grading|@|of|averaging|at)\s*\d+(?:\.\d+)?\s*(?:%|g/t|grams)|"
    r"(?:core|diamond|reverse\s+circulation|RC)\s+drilling\s+(?:results|intercepts|intersection)"
    r")\b",
    re.I,
)

# ----- Resource Estimates ---------------------------------------------------
_MRE = re.compile(
    r"\b("
    r"mineral\s+resource\s+estimate|"
    r"(?:updated|initial|maiden)\s+(?:mineral\s+)?resource(?:\s+estimate)?|"
    r"\bMRE\b|"
    r"(?:measured|indicated|inferred)\s+(?:and\s+(?:measured|indicated|inferred)\s+)?(?:mineral\s+)?resources?|"
    r"NI\s?43[- ]?101\s+(?:technical\s+report|resource\s+estimate|mineral\s+resource)|"
    r"contained\s+(?:ounces|tonnes|pounds|metal|gold|silver|copper)|"
    r"resource\s+(?:statement|calculation|update|report)|"
    r"(?:gold|silver|copper|nickel|zinc|lead)\s+equivalent\s+(?:ounces|resource)"
    r")\b",
    re.I,
)

# ----- Economic Studies (PEA, PFS, FS) --------------------------------------
_ECON = re.compile(
    r"\b("
    r"preliminary\s+economic\s+assessment|"
    r"pre[- ]?feasibility\s+study|"
    r"(?:bankable\s+)?feasibility\s+study|"
    r"definitive\s+feasibility\s+study|"
    r"\bPEA\b|\bPFS\b|\bDFS\b|"
    r"(?:after[- ]tax|pre[- ]tax)\s+(?:NPV|IRR)|"
    r"(?:NPV|IRR)\s+of\s+(?:approximately\s+)?(?:US\$|C\$|\$|CAD|USD)|"
    r"net\s+present\s+value\s+of\s+(?:approximately\s+)?(?:US\$|C\$|\$)|"
    r"internal\s+rate\s+of\s+return|"
    r"payback\s+period\s+of"
    r")\b",
    re.I,
)

# ----- Production Results ---------------------------------------------------
_PROD = re.compile(
    r"\b("
    r"(?:quarterly|annual|yearly|monthly|record|full[- ]year)\s+production\s+(?:results?|update|of|report|summary)|"
    r"production\s+results?|"
    r"production\s+update|"
    r"production\s+report|"
    r"produces?\s+(?:approximately\s+)?\d[\d,]*\s*(?:ounces|oz|tonnes|tons|pounds|lbs)|"
    r"produced\s+(?:approximately\s+)?\d[\d,]*\s*(?:ounces|oz|tonnes|tons|pounds|lbs)|"
    r"(?:annual|quarterly|monthly|record)\s+production\s+of\s+\d|"
    r"produc(?:tion|ed|ing)\s+of\s+\d[\d,.]*\s*(?:ounces|oz|tonnes|tons|pounds|lbs)|"
    r"(?:mill|plant)\s+(?:feed|throughput|recovery)\s+of|"
    r"tonnes?\s+(?:milled|mined|processed|treated|recovered)|"
    r"Q[1-4]\s+(?:\d{4}\s+)?(?:production|mining|milling)|"
    r"gold\s+pour(?:ed|ing)?|"
    r"commercial\s+production"
    r")\b",
    re.I,
)

# ----- Financials -----------------------------------------------------------
_FINL = re.compile(
    r"\b("
    r"financial\s+results?|"
    r"financial\s+statements?|"
    r"(?:Q[1-4]|first|second|third|fourth)\s+quarter\s+(?:\d{4}\s+)?(?:financial\s+)?results?|"
    r"(?:annual|year[- ]end|interim|half[- ]year)\s+(?:financial\s+)?(?:results?|report|statements?)|"
    r"reports?\s+(?:Q[1-4]\s+)?(?:\d{4}\s+)?(?:financial\s+)?results?|"
    r"\bMD&A\b|"
    r"management'?s\s+discussion\s+(?:and\s+analysis)?|"
    r"revenue\s+of\s+(?:approximately\s+)?(?:\$|USD|CAD|US\$|C\$)|"
    r"EBITDA\s+of\s+(?:approximately\s+)?(?:\$|USD|CAD)|"
    r"net\s+(?:income|loss|earnings)\s+(?:of|for)|"
    r"earnings\s+per\s+share|"
    r"\bEPS\b|"
    r"fiscal\s+(?:year|Q[1-4])\s+\d{4}"
    r")\b",
    re.I,
)

# ----- Mergers & Acquisitions (NEW) ----------------------------------------
# Patterns previously embedded in _CORP, now split out as a first-class category.
_MA = re.compile(
    r"\b("
    r"(?:option|agreement)\s+to\s+(?:earn|acquire|purchase|option)|"
    r"(?:earn[- ]in|earn[- ]in\s+agreement)|"
    r"acquires?\s+option\s+to\s+acquire|"
    r"(?:announces?|signs?|enters?\s+into|entered\s+into|executes?|executed)\s+(?:an?\s+)?(?:definitive\s+|binding\s+)?(?:agreement\s+to\s+(?:acquire|purchase|option)|option\s+(?:agreement|to\s+acquire)|share\s+(?:purchase|exchange)\s+agreement)|"
    r"definitive\s+(?:purchase|acquisition|earn[- ]in|option|share\s+exchange)\s+agreement|"
    r"plan\s+of\s+arrangement|"
    r"reverse\s+takeover|\bRTO\b|"
    r"reverse\s+merger|"
    r"share\s+(?:exchange|swap)\s+agreement|"
    r"share\s+exchange|share\s+swap|"
    r"business\s+combination|"
    r"\bamalgamation\b|"
    r"acquisition\s+of\s+(?:a\s+|an\s+|the\s+)?(?:property|project|claims?|lease|mineral|royalty|license|company|entity|interest|additional|\d+%)|"
    r"acquires?\s+(?:additional\s+|new\s+|the\s+|a\s+|an\s+|\d+%\s+)?(?:property|project|claims?|lease|mineral|royalty|licen[cs]es?|interest\s+in|company)|"
    r"options?\s+(?:the\s+)?[A-Z][A-Za-z\s]{2,40}\s+(?:projects?|property|properties|claims?|licen[cs]es?)|"
    r"(?:announces?|signs?)\s+(?:a\s+|an\s+)?(?:agreement\s+to\s+)?option\s+(?:the\s+|a\s+|an\s+)?[A-Z][A-Za-z\s]{2,40}|"
    r"agreement\s+to\s+option\s+[A-Z\d]|"
    r"letter\s+of\s+intent\s+(?:to\s+)?(?:acquire|purchase|option|earn|amalgamate|merge)|"
    r"(?:completes?|completed|closes?|closed)\s+(?:acquisition|merger|amalgamation|plan\s+of\s+arrangement|business\s+combination|reverse\s+takeover|share\s+exchange)|"
    r"assignment\s+agreement.{0,40}acquire|"
    r"assignment\s+(?:and\s+assumption\s+)?agreement\s+(?:to\s+)?(?:acquire|purchase)|"
    r"acquisition\s+(?:of|target)|"
    r"(?:going[- ]public|qualifying)\s+transaction|"
    r"acquires?\s+(?:\S+\s+){0,6}(?:project|properties|property|claims?|deposit|mine|prospect|lease|royalty|licen[cs]es?|stake|interest)\b|"
    r"\b(?:to|intends?\s+to|will|plans?\s+to|expects?\s+to)\s+acquire\b|"
    r"\bto\s+(?:purchase|option)\s+(?:\d+%|the|a|an|all)|"
    r"\b(?:MOU|LOI)\s+(?:to\s+)?(?:acquire|purchase|option|earn|amalgamate|merge)\b|"
    r"\b(?:exclusive\s+)?(?:MOU|LOI|memorandum\s+of\s+understanding)\s+(?:with|to|on)\s+(?:.{0,40})(?:acquire|purchase|option|earn|amalgamate)|"
    r"\bstak(?:e|es|ed|ing)\s+(?:additional\s+|new\s+)?(?:mineral\s+)?claims?\b|"
    r"\b(?:land|property|claim|mineral)\s+package\s+(?:acquisition|expansion)|"
    r"\bexpands?\s+(?:land|property|claim|mineral)\s+(?:position|package)|"
    r"\b(?:asset|property|share|claim)\s+purchase\s+agreement|"
    r"\bconsolidates?\s+(?:land|claims?|district|holdings|position|its\s+land|its\s+claims)|"
    r"\bspin[- ](?:out|off)\b|"
    r"\bqualifying\s+transaction\b"
    r")\b",
    re.I,
)

# ----- Marketing Announcement (TIGHTENED) ----------------------------------
# Removed (too noisy in citation/sidebar boilerplate):
#   "investor presentation", "corporate presentation",
#   "(CEO|CFO|management) interview", "podcast interview",
#   "(webinar|webcast) (presentation|replay)" (kept only when tied to hosting)
# Added:
#   "investor awareness campaign / program / initiative"
#   "market awareness campaign"
#   "(announces|launches|expands) ... (awareness|marketing|advertising) campaign"
#   "(digital )?marketing services agreement" (already partly covered, made explicit)
_MKT = re.compile(
    r"\b("
    r"engagement\s+of\s+(?:marketing|investor\s+relations|IR|communications|media)\s+(?:firm|services|agency|consultant|advisor)|"
    r"retains?\s+.{0,60}\s+(?:as\s+)?(?:marketing|investor\s+relations|IR|communications|capital\s+markets\s+advisor)|"
    r"(?:digital\s+)?(?:marketing|investor\s+relations)\s+(?:services?\s+)?(?:agreement|contract|engagement)|"
    r"marketing\s+services\s+agreement|"
    r"appoints?\s+.{0,40}(?:marketing|IR|investor\s+relations|communications)\s+(?:firm|advisor|consultant|agency)|"
    r"(?:announces?|launches?|commences?|expands?|initiates?|enters\s+into)\s+.{0,40}(?:investor\s+awareness|market\s+awareness|awareness\s+campaign|marketing\s+campaign|advertising\s+campaign|digital\s+marketing\s+campaign)|"
    r"investor\s+awareness\s+(?:campaign|program|initiative|services)|"
    r"market\s+awareness\s+(?:campaign|program|initiative)|"
    r"(?:upcoming|attending|to\s+attend|presenting\s+at|will\s+present|to\s+present\s+at|presents?\s+(?:at\s+)?|presented\s+(?:at\s+)?)\s*.{0,60}(?:conference|summit|symposium|expo|trade\s+show|webinar(?:\s+series)?|webcast|virtual\s+event|virtual\s+(?:webinar\s+)?series)|"
    r"conference\s+(?:presentation|attendance)|"
    r"trade\s+show|"
    r"(?:hosting|hosted|hosts)\s+(?:a\s+|an\s+)?(?:webinar|webcast|investor\s+(?:webinar|webcast))|"
    r"booth\s+#?\s?\d+|"
    r"sponsorship\s+agreement|"
    r"(?:engages?|engaged|engaging|retains?|retained)\s+[A-Z][A-Za-z\s.&,]{2,60}\s+(?:to\s+provide|for|as)\s+(?:investor\s+relations|IR|marketing|advertising|digital\s+marketing|media\s+relations|communications|public\s+relations|capital\s+markets)|"
    r"capital\s+markets\s+(?:advisory|advisor)\s+(?:agreement|engagement)"
    r")\b",
    re.I,
)

# ----- Corporate Updates (TRIMMED — M&A patterns moved to _MA) -------------
_CORP = re.compile(
    r"\b("
    r"appoint(?:s|ed|ment|ing)\b|"
    r"(?:new\s+)?(?:CEO|CFO|COO|president|director|chair(?:man|person)?|vice[- ]president|\bVP\b)\s+appoint|"
    r"director\s+changes?|board\s+changes?|management\s+changes?|"
    r"resigns?\s+(?:as|from)|\bresignation\b|"
    r"grants?\s+(?:stock\s+options?|RSUs?|DSUs?|restricted\s+(?:share|stock)\s+units?)|"
    r"(?:stock\s+options?|RSUs?|DSUs?)\s+(?:granted|issued|grant|awarded)|"
    r"option\s+grants?|"
    r"grant\s+of\s+(?:stock\s+)?options|"
    r"name\s+change|symbol\s+change|ticker\s+change|"
    r"share\s+consolidation|reverse\s+split|forward\s+split|"
    r"annual\s+(?:and\s+)?general\s+meeting|\bAGM\b|"
    r"special\s+meeting\s+of\s+(?:shareholders|security\s*holders)|"
    r"shareholder\s+meeting|"
    r"normal\s+course\s+issuer\s+bid|\bNCIB\b|"
    r"(?:engages|appoints)\s+new\s+(?:auditor|transfer\s+agent)|"
    r"commence[sd]?\s+trading|"
    r"(?:OTCQB|OTCQX|TSXV|CSE|Frankfurt|FSE|NYSE|NASDAQ)\s+(?:listing|listed|uplisting)|"
    r"renews?\s+(?:its\s+)?(?:OTCQB|OTCQX)\s+listing|"
    r"(?:dual\s+)?listing\s+on\s+(?:the\s+)?(?:OTCQB|OTCQX|Frankfurt|TSXV|CSE|NYSE|NASDAQ)|"
    r"lists?\s+on\s+(?:the\s+)?(?:OTCQB|OTCQX|Frankfurt|TSXV|CSE|NYSE|NASDAQ)|"
    r"corporate\s+update|company\s+update|operational\s+update|"
    r"provides?\s+(?:an?\s+)?update|"
    r"provides?\s+(?:an?\s+)?operations?\s+update|"
    r"provides?\s+(?:additional\s+|further\s+)?(?:details?|information)|"
    r"option\s+extension|"
    r"(?:strategic\s+)?investment\s+of\s+(?:approximately\s+)?(?:\$|C\$|US\$)|"
    r"(?:US)?\$\d[\d,.]*\s*(?:million|M\b|billion|B\b)?\s+(?:strategic\s+)?(?:equity\s+)?investment|"
    r"(?:completes|completed|completing)\s+.{0,40}(?:exploration|drilling|survey|program|campaign)|"
    r"(?:commences|commenced|commencing|mobilizes|mobilized|mobilizing|initiates|initiated)\s+(?:for\s+)?(?:.{0,40})?(?:exploration|survey|campaign|mapping|sampling)|"
    r"(?:conducts|conducting|conducted)\s+.{0,40}(?:survey|geophysics|geochemistry|mapping|sampling)|"
    r"engages?\s+.{0,60}\s+(?:for|to)\s+(?:drilling|exploration|services|consulting|advisory)|"
    r"engages?\s+[A-Z][A-Za-z ]{2,40}(?:\s+Drilling|\s+Services|\s+Consulting)|"
    r"(?:expands?|expanded|expanding)\s+.{0,40}(?:land\s+package|claim|property|project)|"
    r"filing\s+of\s+(?:court|litigation|claim|statement|suit)|"
    r"court\s+action|"
    r"legal\s+proceedings?|"
    r"(?:filing|files)\s+(?:a\s+)?(?:lawsuit|complaint|claim)|"
    r"technology\s+(?:development\s+)?agreement|"
    r"(?:signs|enters\s+into)\s+.{0,40}(?:partnership|collaboration|cooperation)|"
    r"memorandum\s+of\s+understanding|\bMOU\b|"
    r"termination\s+of\s+.{0,40}(?:option|agreement|consulting|contract)|"
    r"consulting\s+agreement|"
    r"share\s+issuances?|"
    r"welcomes?\s+[A-Z][A-Za-z\s.]{2,40}\s+(?:as\s+)?(?:an?\s+)?(?:advisor|consultant|director|board\s+member|chair)|"
    r"appointment\s+of\s+(?:VP|vice[- ]president|director|advisor|consultant|CFO|CEO|COO)|"
    r"receipt\s+of\s+(?:interim\s+order|final\s+order|court\s+order)|"
    r"interim\s+order\s+for|"
    r"spin[- ]off|"
    r"establish(?:es|ed|ing)\s+(?:new\s+|[A-Z][A-Za-z]+\s+)*(?:headquarters|office|subsidiary|operations|presence|hub)|"
    r"(?:to\s+commence|commence[sd]?)\s+(?:fieldwork|exploration|mapping|sampling)|"
    r"files?\s+.{0,40}(?:prospectus|circular|proxy|MD&A|interim|annual\s+report)|"
    r"commission(?:s|ed|ing)\s+[A-Z][A-Za-z\s]{2,40}|"
    r"issues?\s+shares?\s+(?:pursuant|as\s+consideration|in\s+settlement)"
    r")\b",
    re.I,
)
_CORP_EXTRA = re.compile(
    r"(?:"
    r"\$\d[\d,.]*\s*(?:million|M\b|billion|B\b)?\s+(?:strategic\s+)?(?:equity\s+)?investment|"
    r"C\$\d[\d,.]*\s*(?:million|M\b)?\s+(?:strategic\s+)?(?:equity\s+)?investment|"
    r"US\$\d[\d,.]*\s*(?:million|M\b)?\s+(?:strategic\s+)?(?:equity\s+)?investment"
    r")",
    re.I,
)


def categorize(headline: str | None, body: str | None) -> list[str]:
    """Return the list of matching categories for this release.

    Output is in CATEGORIES order; empty list means no category matched.
    """
    h = (headline or "").strip()
    b_full = (body or "").strip()
    b = _trim_body(b_full)  # cut sidebar/related-posts tail

    lead = f"{h}\n\n{b[:1500]}"
    text = f"{h}\n\n{b}"  # full text (already sidebar-trimmed)

    cats: list[str] = []

    # Financings: full (trimmed) text
    if _FIN.search(text) or _FIN_EXTRA.search(text):
        cats.append("Financings")
    # Drill Results: lead (headline + first 1500 chars)
    if _DRILL_HEAD.search(lead) or _DRILL_BODY.search(lead):
        cats.append("Drill Results")
    # Resource Estimates: HEADLINE ONLY
    if _MRE.search(h):
        cats.append("Resource Estimates")
    # Economic Studies: HEADLINE ONLY
    if _ECON.search(h):
        cats.append("Economic Studies")
    # Production Results: HEADLINE ONLY
    if _PROD.search(h):
        cats.append("Production Results")
    # Financials: HEADLINE ONLY
    if _FINL.search(h):
        cats.append("Financials")
    # Mergers & Acquisitions: lead (covers headline + intro paragraph)
    if _MA.search(lead):
        cats.append("Mergers & Acquisitions")
    # Marketing Announcement: full (trimmed) text. The body trim now removes
    # sidebar/related-posts/Prev-Next chrome, so full-text matching is safe.
    if _MKT.search(text):
        cats.append("Marketing Announcement")
    # Corporate Updates: full (trimmed) text
    if _CORP.search(text) or _CORP_EXTRA.search(text):
        cats.append("Corporate Updates")
    return cats


def format_categories(cats: Iterable[str]) -> str:
    """Serialize categories to a pipe-delimited DB string."""
    return "|".join(c for c in cats if c)


def parse_categories(s: str | None) -> list[str]:
    """Parse a pipe-delimited DB string back to a list of category names."""
    if not s:
        return []
    return [x for x in s.split("|") if x]
