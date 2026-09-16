"""News release categorizer (v7; v3 design notes below).

WHY v3
------
v2 decided five of the ten categories by searching for phrases anywhere in the
body. A phrase appearing somewhere is not the same as the release being ABOUT
that thing, and the corpus shows exactly what that costs:

  Mergers & Acquisitions   3,756 tagged, only 1,198 declared in the headline.
                           'to acquire' fires 1,091 times in bodies -- almost
                           all of it boilerplate describing a property the
                           company ALREADY holds an option on. 1,148 of the
                           body-only ones are really financings.
  Drill Results            4,644 tagged, 1,829 declared in the headline.
                           'drill program' fires 959 times. A drill program
                           ANNOUNCEMENT is not drill RESULTS.
  Corporate Updates        8,188 tagged, largely off 'provide an update' (400)
                           and 'appointment' (169) buried anywhere in the text.

Management Changes was already right, and shows the shape the rest should take:
it does not phrase-match at all. It asks management_extract to PARSE a change
(action + person + role + scope) out of the headline, and only fires if that
succeeds. Because the category and the page are the same code, they cannot
drift -- 865 = 865, the only category where chip and page agree exactly.

v3 applies that shape where it survives contact with the corpus:

  1. SCOPE. Nothing matches the full body any more. A category is decided from
     the SUBJECT window -- the headline plus the opening of the release, cut at
     the first boilerplate marker (forward-looking statements, "About X",
     exchange disclaimer, contact block). Boilerplate is where the false
     positives live.

  2. DECLARATION, NOT MENTION. Where a lede match is allowed at all, it must be
     DECLARATIVE -- an announcing verb next to the thing being announced -- not
     a bare noun. "announces the acquisition of" counts; "has an option to
     acquire" does not.

  3. PLANS ARE NOT RESULTS. A study that has been commissioned, engaged,
     commenced or merely intended has no results to report. 39 of the 162
     Economic Studies were plans. The same guard cleans Resource Estimates
     ("Commences Maiden MRE", "Engages Stantec for Maiden Resource Estimate",
     "Initiates Work Toward MRE").

  4. OTHER COMPANIES' NEWS IS NOT OURS. "Star Copper Congratulates Doubleview
     Gold's Mineral Resource Estimate" is not Star Copper's resource.

WHAT I DID *NOT* DO, AND WHY
----------------------------
The first draft of v3 delegated Drill Results to drill_extract and Resource
Estimates to resource_extract.is_real_mre, on the theory that the backfills
already select WHERE categories LIKE ?, so delegating would make chip == page
by construction. Measured against the corpus, both delegations are worse than
what they replace, because those extractors read the BODY:

  is_real_mre   would ADD 235 releases the chip does not have, and the sample
                is "Cascada Signs MOUs to Acquire Three Copper-Gold Porphyry
                Properties", "OTC Markets Group Welcomes Tartisan Nickel to
                OTCQX", "Cascada Silver Corp. To Become ATERRA Metals Inc" --
                acquisition releases that happen to quote a resource table.

  drill_extract would ADD 401, including "Emperor Metals Announces $6.5 Million
                Best Efforts Private Placement" and survey/technical-report
                filings -- numbers picked out of the body of a release that is
                about something else.

So both stay headline-driven, and drill_extract is used only as a RESCUE, gated
on the lede also declaring results. Delegation is right when the extractor is
the authority on the thing (management_extract parses the change itself); it is
wrong when the extractor is just another body scanner.

Bug fixed in passing: _FIN spelled it flow[- ]?through, so "Closes Flow Thru
Financing" was never tagged a financing at all. Second bug: _FINL's
'reports results' branch had every qualifier optional, so it matched "Reports
Results of Airborne ZTEM Survey", "Reports Results of 2025 AGM" and "Reports
Result of Vested Rights Hearing" as financial results.

Categories (in output order):
  Financings, Drill Results, Resource Estimates, Management Changes,
  Economic Studies, Production Results, Financials, Mergers & Acquisitions,
  Marketing Announcement, Corporate Updates
"""
from __future__ import annotations

import re
from typing import Iterable

# When nothing else matches, does the release fall into Corporate Updates?
# True  -> no release is left uncategorised; Corporate Updates is the "other"
#          bucket and grows.
# False -> tighter chips, but N releases carry no category at all and are
#          invisible on the front page (3,502 are in that state today).
FALLBACK_TO_CORPORATE = True

# How much of the body counts as "the subject of the release".
LEDE_CHARS = 900

CATEGORIES: tuple[str, ...] = (
    "Financings",
    "Debt & Credit Facilities",
    "Drill Results",
    "Resource Estimates",
    "Technical Reports (NI 43-101)",
    "Management Changes",
    "Economic Studies",
    "Production Results",
    "Financials",
    "Mergers & Acquisitions",
    "Royalties & Streams",
    "Property Options & Staking",
    "Exploration Programs",
    "Permits & Approvals",
    "Metallurgy & Processing",
    "Share Capital & Compensation",
    "Listings & Exchange",
    "Shareholder Meetings",
    "Corporate Actions",
    "Regulatory & Compliance",
    "Partnerships & JV",
    "Marketing Announcement",
    "Corporate Updates",
)

CODE_TO_CAT = {
    "fin": "Financings",
    "drl": "Drill Results",
    "res": "Resource Estimates",
    "mgt": "Management Changes",
    "eco": "Economic Studies",
    "prd": "Production Results",
    "fns": "Financials",
    "mna": "Mergers & Acquisitions",
    "exp": "Exploration Programs",
    "per": "Permits & Approvals",
    "met": "Metallurgy & Processing",
    "cap": "Share Capital & Compensation",
    "lst": "Listings & Exchange",
    "mtg": "Shareholder Meetings",
    "act": "Corporate Actions",
    "jv": "Partnerships & JV",
    "mkt": "Marketing Announcement",
    "cor": "Corporate Updates",
    "dbt": "Debt & Credit Facilities",
    "tec": "Technical Reports (NI 43-101)",
    "roy": "Royalties & Streams",
    "opt": "Property Options & Staking",
    "reg": "Regulatory & Compliance",
}
CAT_TO_CODE = {v: k for k, v in CODE_TO_CAT.items()}


# ===========================================================================
# Scope: sidebar trim (from v2) + boilerplate cut (new) + the subject window
# ===========================================================================

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
_BODY_TAIL_PREVNEXT = re.compile(
    r"\n\s*•?\s*(?:Prev|Next|Previous)\s*[-–—]\s*[A-Z]",
)

# Everything from here on is boilerplate: forward-looking statements, the
# exchange disclaimer, the "About <Company>" block, QP statements, the contact
# block. This is where 'to acquire', 'private placement' and 'drill program'
# live in releases that are about something else entirely.
_BOILERPLATE = re.compile(
    r"(?i)(?:"
    r"forward[-\s]looking\s+(?:statements?|information)|"
    r"cautionary\s+(?:note|statement|language)|"
    r"neither\s+(?:the\s+)?(?:canadian\s+securities\s+exchange|cse|tsx|"
    r"tsx\s+venture\s+exchange|investment\s+industry\s+regulatory)|"
    r"(?:the\s+)?(?:cse|tsx\s+venture\s+exchange|canadian\s+securities\s+exchange)"
    r"\s+(?:has\s+not|does\s+not|accepts?\s+no)|"
    r"\babout\s+[A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,4}\s*"
    r"(?:inc|corp|ltd|limited|corporation|resources|mining|metals|gold|"
    r"silver|copper|minerals|exploration)\b\.?\s*\n|"
    r"for\s+(?:further|more|additional)\s+information[,:\s]|"
    r"qualified\s+persons?\s+(?:statement|disclosure)|"
    r"(?:the\s+)?(?:technical|scientific)\s+(?:information|content|disclosure)"
    r"\s+(?:in|contained)|"
    r"not\s+for\s+(?:distribution|dissemination|release)|"
    r"\bsource\s*:\s|"
    r"contact\s+information|"
    r"for\s+investor\s+(?:relations|inquiries)|"
    r"on\s+behalf\s+of\s+the\s+board"
    r")"
)


def _trim_body(b: str) -> str:
    """Cut body at the first sidebar-like marker (v2 behaviour, unchanged)."""
    cuts: list[int] = []
    for rx in (_BODY_TAIL_BULLET, _BODY_TAIL_HEADING, _BODY_TAIL_PREVNEXT):
        m = rx.search(b)
        if m:
            cuts.append(m.start())
    if not cuts:
        return b
    return b[: min(cuts)]


def lede(b: str, n: int = LEDE_CHARS) -> str:
    """The opening of the release: sidebar-trimmed, cut at boilerplate, capped."""
    b = _trim_body(b or "")
    m = _BOILERPLATE.search(b)
    if m:
        b = b[: m.start()]
    return b[:n]


def subject(headline: str | None, body: str | None) -> str:
    """Headline + opening -- what the release is ABOUT."""
    return f"{(headline or '').strip()}\n\n{lede((body or '').strip())}"


# ===========================================================================
# Cross-cutting guards
# ===========================================================================

# Announcing verbs: the difference between announcing a thing and mentioning
# one. Used to gate every lede-scoped rule.
_ANN = (r"(?:announc\w+|report\w+|declar\w+|confirm\w+|complet\w+|clos\w+|"
        r"sign\w+|execut\w+|enter\w+\s+into|ha[sv]e?\s+(?:entered|signed|"
        r"completed|closed|acquired|agreed)|agree[sd]?\s+to|is\s+pleased\s+to\s+"
        r"announce|today\s+announced?|upsiz\w+|pric\w+|launch\w+|"
        r"receiv\w+|grant\w+|award\w+|intersect\w+|return\w+)")

# Somebody else's news. An absolute veto -- it is never overridden, because a
# congratulation always contains the other company's good result verbatim.
_THIRD_PARTY = re.compile(
    r"(?i)\b(?:congratulat\w+|comments?\s+on|reacts?\s+to|responds?\s+to|"
    r"weighs?\s+in\s+on)\b"
)

# A study/estimate that has been commissioned, started, or is merely intended
# has no results to report. Overridable by the _DELIVERED patterns below, so a
# headline that both files a report AND mentions an update still counts.
_STUDY_PLAN = re.compile(
    r"(?i)\b(?:"
    r"engage[sd]?|engaging|retain[sd]?|retaining|award(?:s|ed|ing)?|"
    r"contract(?:s|ed|ing)?|commission(?:s|ed|ing)?|select(?:s|ed)?|"
    r"appoint(?:s|ed|ment)?|hire[sd]?|"
    r"commenc\w+|initiat\w+|begins?|beginning|began|starts?|starting|"
    r"undertak\w+|advanc\w+|accelerat\w+|progress(?:es|ed|ing)?|"
    r"nearing\s+completion|on\s+track\s+(?:to|for)|"
    r"work(?:s|ing)?\s+(?:on|toward|towards)|"
    r"plans?\s+to|intends?\s+to|expects?\s+to|anticipat\w+|"
    r"will\s+(?:complete|deliver|commence|release|report)|"
    r"to\s+(?:complete|conduct|undertake|commence|prepare|deliver|file|"
    r"advance|accelerate|support|fund|release|report|showcase|present)|"
    r"in\s+support\s+of|as\s+part\s+of|to\s+support|supporting|"
    r"update\s+on|status\s+update|conference\s+call|"
    r"(?:PEA|PFS|DFS|feasibility\s+study|pre[-\s]?feasibility\s+study)\s+update|"
    r"target(?:s|ing)?\s+(?:a\s+|an\s+|the\s+)?(?:maiden\s+|initial\s+|updated\s+)?"
    r"(?:mineral\s+)?resource"
    r")\b"
)

# ...unless the same headline actually delivers the study.
_STUDY_DELIVERED = re.compile(
    r"(?i)(?:"
    r"positive\s+(?:PEA|PFS|DFS|pre[-\s]?feasibility|feasibility)|"
    r"results?\s+of\s+(?:the\s+|its\s+|an?\s+)?(?:updated\s+|independent\s+)?"
    r"(?:PEA|PFS|DFS|preliminary\s+economic|pre[-\s]?feasibility|feasibility)|"
    r"(?:PEA|PFS|DFS)\s+results?|"
    r"(?:after[-\s]tax|pre[-\s]tax)\s+(?:NPV|IRR)|(?:NPV|IRR)\s+of|"
    r"files?\s+.{0,40}?(?:technical\s+report|PEA|PFS|DFS|feasibility)|"
    r"(?:announces?|reports?|releases?|delivers?|completes?|publishes?)\s+"
    r"(?:its\s+|the\s+|an?\s+|positive\s+|robust\s+|updated\s+|initial\s+)*"
    r"(?:PEA|PFS|DFS|preliminary\s+economic\s+assessment|"
    r"pre[-\s]?feasibility\s+study|feasibility\s+study)"
    r")"
)

# ...and the same idea for a resource estimate.
_MRE_DELIVERED = re.compile(
    r"(?i)(?:"
    r"(?:announces?|reports?|releases?|delivers?|completes?|files?|publishes?|"
    r"updates?|increases?|expands?|grows?)\s+"
    r"(?:its\s+|the\s+|an?\s+|positive\s+|updated\s+|initial\s+|maiden\s+|"
    r"new\s+|expanded\s+|increased\s+|significantly\s+)*"
    r"(?:mineral\s+)?resource|"
    r"contained\s+(?:ounces|tonnes|pounds|metal)|"
    r"filing\s+of\s+.{0,50}?(?:technical\s+report|resource)|"
    r"NI\s?43[-\s]?101\s+technical\s+report"
    r")"
)

# A notice that results are coming is not the results.
_NOTICE = re.compile(
    r"(?i)(?:notice\s+of|to\s+(?:release|report|announce|host)\b|"
    r"will\s+(?:release|report|announce)\b|schedules?\s+(?:its\s+)?"
    r"(?:Q[1-4]|first|second|third|fourth|annual)|conference\s+call)"
)


# ===========================================================================
# Financings
# ===========================================================================
_FIN = re.compile(
    r"\b("
    r"private\s+placement|"
    r"bought\s+deal|"
    r"(?:non[-\s])?brokered\s+(?:private\s+)?(?:placement|offering|financing)|"
    r"(?:closes?|closed|completes?|completed)\s+(?:the\s+|a\s+|its\s+|first\s+|"
    r"final\s+|second\s+)?(?:non[-\s])?(?:brokered\s+)?(?:private\s+)?"
    r"(?:placement|offering|financing|subscription)|"
    r"(?:announces?|completes?|closes?)\s+(?:the\s+)?"
    r"(?:closing|completion|extension|pricing|upsizing|amendment)\s+of\s+"
    r"(?:[\w$,.’\-]+\s+){0,5}?"
    r"(?:placement|offering|financing|debenture|subscription|tranche)|"
    r"announces?\s+(?:the\s+)?(?:a\s+|its\s+)?"
    r"(?:non[-\s])?(?:brokered\s+)?(?:private\s+)?(?:placement|offering|financing)|"
    r"funding\s+agreement|royalty\s+financing|streaming\s+agreement|"
    r"rights\s+offering|over[-\s]?allotment|"
    r"upsize[sd]?\s+.{0,30}(?:financing|offering|placement)|"
    r"unit\s+offering|"
    # v3 fix: the corpus spells it 'Flow Thru' as often as 'flow-through', and
    # v2's pattern required 'through', so "Closes Flow Thru Financing" was not
    # tagged a financing at all.
    r"flow[-\s]?thr(?:ough|u)(?:\s+(?:common\s+)?(?:shares?|units?|financing|"
    r"placement|offering|subscription))?|"
    r"\bLIFE\s+(?:offering|financing|placement)|"
    r"listed\s+issuer\s+financing\s+exemption|"
    r"subscription\s+receipts?|"
    r"(?:first|second|third|final|last)\s+tranche|"
    r"warrant\s+exercise\s+term|"
    r"extension\s+of\s+warrant|"
    r"up\s+to\s+C?\$[\d,.]+\s*(?:million|M\b)\s+(?:private\s+)?"
    r"(?:placement|offering|financing)|"
    r"aggregate\s+gross\s+proceeds|"
    r"gross\s+proceeds\s+of\s+(?:approximately\s+)?C?\$[\d,.]+|"
    r"convertible\s+(?:loan|debenture|note|security)|"
    r"loan\s+financing|"
    r"acceleration\s+of\s+warrant|warrant\s+acceleration|"
    r"files?\s+(?:preliminary\s+)?non[-\s]offering\s+prospectus|"
    r"short[-\s]form\s+prospectus|"
    r"(?:base\s+)?shelf\s+prospectus|final\s+prospectus|"
    r"term\s+loan|warrant\s+exercise|"
    r"exercis\w+\s+(?:[\w$,.’\-]+\s+){0,4}?warrants?|"
    r"(?:marketed\s+)?equity\s+offering|marketed\s+offering|"
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
# In the lede, an instrument noun alone is not enough -- it is how a drill
# release picks up "the Company closed a private placement in June". Require an
# announcing verb within a short distance of the instrument.
_FIN_DECLARE = re.compile(
    rf"(?i)\b{_ANN}\b[^.\n]{{0,80}}?\b(?:"
    r"private\s+placement|bought\s+deal|(?:non[-\s])?brokered\s+(?:private\s+)?"
    r"(?:placement|offering|financing)|flow[-\s]?thr(?:ough|u)|unit\s+offering|"
    r"subscription\s+receipts?|convertible\s+(?:debenture|note|loan)|"
    r"LIFE\s+offering|gross\s+proceeds"
    r")\b"
)

# ===========================================================================
# Drill Results -- the headline must report RESULTS. Programs, targets,
# surveys and mobilisations are exploration activity -> Corporate Updates.
# ===========================================================================
_DRILL_RESULT_HEAD = re.compile(
    r"\b("
    r"drill(?:ing)?\s+results?|"
    r"drill(?:ing)?\s+intercepts?|"
    r"assay\s+results?|"
    r"(?:returns?|hits?|encounters?|intersects?|intercepts?|cuts?)\s+"
    r"\d+(?:\.\d+)?\s*(?:m|metres?|meters?|ft|feet)|"
    r"\d+(?:\.\d+)?\s*(?:m|metres?|meters?)\s+(?:grading|@|of|averaging|at)\s*\d|"
    r"intersects?\s+\d+(?:\.\d+)?\s*(?:m|metres?|meters?|g/t|%)|"
    r"\d+(?:\.\d+)?\s*g\s*/\s*t(?:onne)?\s+(?:au|gold|silver|ag|cu|copper)|"
    r"(?:high|bonanza)[-\s]?grade\s+(?:\w+\s+){0,2}"
    r"(?:assays?|intercepts?|intersections?|results?|mineraliz\w+)|"
    r"results?\s+from\s+(?:the\s+)?(?:first\s+|final\s+|initial\s+)?"
    r"(?:\w+\s+){0,2}holes?\b|"
    r"(?:best|significant)\s+(?:intersect\w*|drill\s+results?|assays?|hole)|"
    r"hole\s+\S{0,14}\s*(?:returns?|intersects?|grades?)|"
    r"(?:grab|channel|surface|soil|chip|rock|trench)\s+sampl(?:e|es|ing)\s+"
    r"(?:results?|returns?)|"
    # v4 recall, from the residual of the new-tag measurement
    r"\bsamples?\s+up\s+to\s+[\d.,]+\s*(?:%|g\s*/\s*t|ppm|ppb|opt)|"
    r"\b(?:provides?|reports?|announces?|delivers?)\s+(?:[\w\-]+\s+){0,3}?"
    r"results?\s+(?:for|from)\s+(?:the\s+)?(?:[\w\-]+\s+){0,3}?drill|"
    r"\breports?\s+assays?\b|\bassays?\s+from\s+(?:hole|drill|the)\b|"
    r"\bintercepts?\s+includ\w+|"
    r"\bvisible\s+gold\b|"
    r"\bextends?\s+(?:the\s+)?[\w\-]+\s+zone\s+by\s+\d|"
    r"\b\d[\d.,]*\s*%\s*(?:cu|zn|pb|ni|sb|li2o|reo|treo|fe2o3|u3o8)\b|"
    # v5: a grade with a unit AND a metal, spelled out or abbreviated. The "%"
    # branch refuses of/interest/ownership/in-the, because "acquires 100% of the
    # Gold Project" is an ownership stake, not an assay.
    r"(?:(?:100(?:\.\d+)?|\d{1,2}(?:\.\d+)?)\s*"
    r"%(?!\s*(?:of\b|interest|own\w*|option|stake|holding|in\s+the))"
    r"|\d[\d.,]*\s*(?:g\s*/\s*t|gpt|ppm|ppb|oz\s*/\s*t|opt))\s*"
    r"(?:[\w\-]+\s+){0,2}?"
    r"(?:au|ag|cu|pb|zn|ni|co|sb|mo|sn|u3o8|li2o|reo|treo|pgm|nb2o5|ga2o3|"
    r"gold|silver|copper|lead|zinc|nickel|cobalt|antimony|molybdenum|tin|"
    r"tungsten|uranium|lithium|graphite|hydrogen|potash|platinum|palladium|"
    r"rare\s+earth)\b(?!\s+recover)|"
    # v5: extending a zone or mineralisation is a result
    r"\b(?:extends?|expands?|grows?)\s+(?:[\w\-]+\s+){0,3}?"
    r"(?:mineraliz\w+|strike\s+length|high[-\s]?grade\s+zone|zones?)\b|"
    # v3e: a result reported without a number in the headline
    r"\bdrills\s+(?:[\w.,%’\-]+\s+){0,4}?(?:\d[\d.,]*\s*"
    r"(?:m\b|metres?|meters?|g\s*/\s*t|%)|mineraliz\w+|sulphides?|sulfides?|"
    r"veins?|zones?)|"
    r"discover\w+\s+(?:[\w’\-]+\s+){0,3}?(?:high[-\s]?grade|mineraliz\w+|"
    r"extension|zones?|occurrences?|sulphides?|sulfides?)|"
    r"returns?\s+(?:[\w’\-]+\s+){0,3}?(?:high[-\s]?grade|mineraliz\w+)|"
    r"drill(?:ing)?\s+(?:[\w’\-]+\s+){0,3}?returns?|"
    r"(?:expose[sd]?|exposing|intersect\w+)\s+(?:[\w’\-]+\s+){0,3}?"
    r"(?:mineraliz\w+|sulphides?|sulfides?|high[-\s]?grade)"
    r")\b",
    re.I,
)
# drill_extract is allowed to RESCUE a release whose headline is vague, but
# only when the lede also declares results. On its own it adds 401 false
# positives (financings, surveys, technical-report filings).
# Historical results are not new results -- but most headlines containing
# "historic" ARE new work on historic ground, so the veto only fires when there
# is no new-work language at all. Measured: 51 of 1,474 mention "historic";
# only a handful are pure historical reporting.
_DRILL_HISTORICAL = re.compile(
    r"(?i)\bhistoric(?:al)?\s+(?:[\w\-]+\s+){0,2}?"
    r"(?:results?|intersections?|intercepts?|assays?|grades?|drill\w*|data)\b"
)
_DRILL_NEW_WORK = re.compile(
    r"(?i)\b(?:confirms?|confirmed|validat\w+|verif\w+|twin\w+|re-?assay\w*|"
    r"new\s+(?:drill|assay|result|discover)|intersects?|intersected|drills\b|"
    r"maiden|infill\s+(?:drill|sampl)|extends?|continues?\s+to)\b"
)


_DRILL_LEDE = re.compile(
    rf"(?i)\b{_ANN}\b[^.\n]{{0,90}}?\b(?:"
    r"drill(?:ing)?\s+results?|assay\s+results?|intercept\w*|"
    r"intersect\w*|drill\s*hole|channel\s+sampl\w+"
    r")\b"
)

# ===========================================================================
# Resource Estimates (headline; guarded by plan + third-party)
# ===========================================================================
_MRE = re.compile(
    r"\b("
    r"mineral\s+resource\s+estimate|"
    r"(?:updated|initial|maiden)\s+(?:mineral\s+)?resource(?:\s+estimate)?|"
    r"\bMRE\b|"
    r"(?:updates?|increases?|expands?|grows?)\s+(?:its\s+)?(?:significantly\s+)?"
    r"(?:mineral\s+)?resources?|"
    r"(?:measured|indicated|inferred)\s+(?:and\s+(?:measured|indicated|inferred)\s+)?"
    r"(?:mineral\s+)?resources?|"
    r"NI\s?43[-\s]?101\s+(?:technical\s+report|resource\s+estimate|mineral\s+resource)|"
    r"contained\s+(?:ounces|tonnes|pounds|metal|gold|silver|copper)|"
    r"resource\s+(?:statement|calculation|update|report)|"
    r"(?:gold|silver|copper|nickel|zinc|lead)\s+equivalent\s+(?:ounces|resource)"
    r")\b",
    re.I,
)

# ===========================================================================
# Economic Studies
# ===========================================================================
_ECON = re.compile(
    r"\b("
    r"preliminary\s+economic\s+assessment|"
    r"pre[-\s]?feasibility\s+study|"
    r"(?:bankable\s+)?feasibility\s+study|"
    r"definitive\s+feasibility\s+study|"
    r"\bPEA\b|\bPFS\b|\bDFS\b|"
    r"(?:after[-\s]tax|pre[-\s]tax)\s+(?:NPV|IRR)|"
    r"(?:NPV|IRR)\s+of\s+(?:approximately\s+)?(?:US\$|C\$|\$|CAD|USD)|"
    r"net\s+present\s+value\s+of\s+(?:approximately\s+)?(?:US\$|C\$|\$)|"
    r"internal\s+rate\s+of\s+return|"
    r"payback\s+period\s+of"
    r")\b",
    re.I,
)

# ===========================================================================
# Production Results
# ===========================================================================
_PROD = re.compile(
    r"\b("
    r"(?:quarterly|annual|yearly|monthly|record|full[-\s]year)\s+production\s+"
    r"(?:results?|update|of|report|summary)|"
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
# This is a precious-metals terminal. Two Permian Basin oil updates were tagged
# Production Results.
_OIL_GAS = re.compile(
    r"(?i)\b(?:permian|bakken|eagle\s+ford|montney|duvernay|haynesville|"
    r"marcellus|wellbore|boe\s*/\s*d|bbls?|barrels?|natural\s+gas|"
    r"oil\s+(?:and|&)\s+gas|petroleum|frac(?:king|ture\s+stimulat)|"
    r"working\s+interest\s+well|gas\s+well|oil\s+well)\b"
)
# Reaching towards production, or contracting for the technology to produce,
# is not production. "Enter MOU for Purchase of LFP Commercial Production
# Technology" and "Advances Boardwalk Toward Commercial Production" were both
# tagged Production Results.
_PROD_NOT = re.compile(
    r"(?i)(?:\b(?:MOU|memorandum\s+of\s+understanding|letter\s+of\s+intent)\b|"
    r"progressing\s+towards?|toward[s]?\s+(?:commercial\s+)?production|"
    r"on\s+track\s+to\s+(?:produce|pour|commence|begin|start|enter|"
    r"achieve\s+commercial)|expects?\s+to\s+(?:produce|pour)|"
    r"plans?\s+to\s+(?:produce|pour)|production\s+technology)"
)

# ===========================================================================
# Financials
# ===========================================================================
# v2's 'reports results' branch had every qualifier optional, so bare "Reports
# Results" matched -- and the corpus is full of "Reports Results of Airborne
# ZTEM Survey", "Reports Results of 2025 AGM", "Reports Result of Vested Rights
# Hearing", "Reports Results from 528 kg Sorting Test". A period qualifier or
# the word 'financial' is now required.
_FINL = re.compile(
    r"\b("
    r"(?:financial|operating\s+and\s+financial)\s+results?|"
    r"financial\s+statements?|"
    r"(?:Q[1-4]|first|second|third|fourth)\s+quarter\s+(?:\d{4}\s+)?"
    r"(?:financial\s+)?results?|"
    r"(?:annual|year[-\s]end|interim|half[-\s]year|full[-\s]year)\s+"
    r"(?:financial\s+)?(?:results?|report|statements?)|"
    r"reports?\s+(?:its\s+)?(?:(?:first|second|third|fourth)\s+quarter|"
    r"Q[1-4]|full[-\s]year|annual|year[-\s]end|interim|half[-\s]year|"
    r"fiscal(?:\s+\d{4})?|\d{4})\s+(?:\d{4}\s+)?(?:financial\s+)?results?|"
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

# ===========================================================================
# Mergers & Acquisitions
# ===========================================================================
_MA_HEAD = re.compile(
    r"\b("
    r"(?:option|agreement)\s+to\s+(?:earn|acquire|purchase|option)|"
    r"earn[-\s]in(?:\s+agreement)?|"
    r"(?:announces?|signs?|enters?\s+into|entered\s+into|executes?|executed)\s+"
    r"(?:an?\s+)?(?:definitive\s+|binding\s+)?(?:agreement\s+to\s+"
    r"(?:acquire|purchase|option)|option\s+(?:agreement|to\s+acquire)|"
    r"share\s+(?:purchase|exchange)\s+agreement)|"
    r"definitive\s+(?:purchase|acquisition|earn[-\s]in|option|share\s+exchange)"
    r"\s+agreement|"
    r"plan\s+of\s+arrangement|"
    r"reverse\s+takeover|\bRTO\b|reverse\s+merger|"
    r"share\s+(?:exchange|swap)(?:\s+agreement)?|"
    r"business\s+combination|"
    r"\bamalgamat\w+|\bmerger\b|\bmerges?\s+with\b|"
    # the gap must be able to cross "100%" and "US$2.5M" -- it could not, so
    # "Acquisition of 100% Interest in ..." never matched
    r"acquisition\s+of\s+(?:[\w.,'’\-%$&/]+\s+){0,6}?(?:propert(?:y|ies)|"
    r"projects?|claims?|leases?|mineral|royalt(?:y|ies)|licen[cs]es?|compan(?:y|ies)|"
    r"entity|interest|additional|assets?|deposits?|mines?|corp\b|corporation|"
    r"\binc\b|\bltd\b|limited|\d+%)|"
    r"acquires?\s+(?:[\w.,'’\-%$&/]+\s+){0,6}?(?:propert(?:y|ies)|projects?|"
    r"claims?|leases?|mineral|royalt(?:y|ies)|licen[cs]es?|interest(?:\s+in)?|"
    r"compan(?:y|ies)|corp\b|corporation|\binc\b|\bltd\b|limited|deposits?|"
    r"mines?|stake)|"
    # takeover mechanics, and arrangements without the words "plan of"
    r"\b(?:take[-\s]?over\s+bid|unsolicited\s+(?:offer|bid|take[-\s]?over)|"
    r"hostile\s+(?:bid|offer)|tender\s+offer|superior\s+proposal|"
    r"combination\s+transaction)\b|"
    r"\b(?:completes?|completed|terminates?|confirms?)\s+(?:the\s+)?arrangement\b|"
    r"\bstakes?\s+(?:the\s+)?[A-Z][\w\-]*(?:\s+[A-Z][\w\-]*){0,3}\s+"
    r"(?:mine|claims?|propert(?:y|ies))\b|"
    r"letter\s+of\s+intent\s+(?:to\s+)?(?:acquire|purchase|option|earn|"
    r"amalgamate|merge)|"
    r"(?:completes?|completed|closes?|closed)\s+(?:the\s+)?(?:acquisition|merger|"
    r"amalgamation|plan\s+of\s+arrangement|business\s+combination|"
    r"reverse\s+takeover|share\s+exchange)|"
    r"(?:going[-\s]public|qualifying)\s+transaction|"
    r"\b(?:to|intends?\s+to|will|plans?\s+to|agrees?\s+to)\s+acquire\b|"
    r"\bto\s+(?:purchase|option)\s+(?:\d+%|the|a|an|all)|"
    r"\b(?:MOU|LOI)s?\s+(?:to\s+)?(?:acquire|purchase|option|earn|amalgamate|merge)\b|"
    r"\bstak(?:e|es|ed|ing)\s+(?:additional\s+|new\s+)?(?:mineral\s+)?claims?\b|"
    r"\b(?:land|property|claim|mineral)\s+package\s+(?:acquisition|expansion)|"
    r"\b(?:expands?|increases?|grows?|consolidat\w+)\s+"
    r"(?:its\s+)?(?:land|property|claim|mineral)\s+(?:position|package|holdings)|"
    r"\benters?\s+(?:into\s+)?(?:an?\s+)?definitive\s+agreement|"
    r"\b(?:asset|property|share|claim)?\s*purchase\s+agreement|"
    r"\bjoint\s+ventures?\b|"
    r"\bexercis\w+\s+(?![^.\n]{0,40}over[-\s]?allot)"
    r"(?:[\w.,'’\-%$&/]+\s+){0,5}?options?\b|"
    r"\bproperty\s+transaction\b|"
    r"\bsale\s+of\s+(?:[\w.,'’\-%$&/]+\s+){0,5}?"
    r"(?:projects?|propert(?:y|ies)|claims?|interest|assets?|subsidiary)|"
    r"\bconsolidates?\s+(?:land|claims?|district|holdings|position)|"
    r"\boptions?\s+(?:the\s+|its\s+|a\s+)?[A-Z][A-Za-z\s\-]{2,40}\s*"
    r"(?:projects?|propert(?:y|ies)|claims?|licen[cs]es?|deposits?)\b|"
    r"\boptions?\s+(?:the\s+|its\s+)?[A-Z][A-Za-z\s\-]{2,40}\s+to\s+[A-Z]|"
    r"\bspin[-\s](?:out|off)\b|"
    r"\bdivests?\b|\bdivestiture\b|"
    r"\bsells?\s+(?:its\s+)?(?:interest|stake|property)"
    r")\b",
    re.I,
)
# LEDE tier: a transaction must be DECLARED, not described. This is what kills
# the 1,091 'to acquire' body hits -- an option the company already holds is
# never introduced by "announces" or "has entered into".
_MA_DECLARE = re.compile(
    rf"(?i)\b{_ANN}\b[^.\n]{{0,45}}?\b(?:the|a|an|its|their|this)\s+"
    r"(?:\w+\s+){0,2}?(?:"
    r"acquisition|amalgamation|merger|plan\s+of\s+arrangement|"
    r"business\s+combination|reverse\s+takeover|share\s+exchange|"
    r"earn[-\s]in\s+agreement|option\s+agreement|"
    r"(?:definitive|binding)\s+agreement|"
    r"(?:asset|property|share|claim)\s+purchase\s+agreement|"
    r"letter\s+of\s+intent|qualifying\s+transaction"
    r")\b"
)

# ===========================================================================
# Marketing Announcement (subject scope, not full text)
# ===========================================================================
_MKT = re.compile(
    r"\b("
    r"engagement\s+of\s+(?:marketing|investor\s+relations|IR|communications|media)\s+"
    r"(?:firm|services|agency|consultant|advisor)|"
    r"retains?\s+.{0,60}\s+(?:as\s+)?(?:marketing|investor\s+relations|IR|"
    r"communications|capital\s+markets\s+advisor)|"
    r"(?:digital\s+)?(?:marketing|investor\s+relations)\s+(?:services?\s+)?"
    r"(?:agreement|contract|engagement)|"
    r"marketing\s+services\s+agreement|"
    r"appoints?\s+.{0,40}(?:marketing|IR|investor\s+relations|communications)\s+"
    r"(?:firm|advisor|consultant|agency)|"
    r"(?:announces?|launches?|commences?|expands?|initiates?|enters\s+into)\s+"
    r".{0,40}(?:investor\s+awareness|market\s+awareness|awareness\s+campaign|"
    r"marketing\s+campaign|advertising\s+campaign|digital\s+marketing\s+campaign)|"
    r"investor\s+awareness\s+(?:campaign|program|initiative|services)|"
    r"market\s+awareness\s+(?:campaign|program|initiative)|"
    r"sponsorship\s+agreement|"
    # An IR/marketing firm is identified by its own name, not by a trailing
    # purpose clause: "Engages Investing News Network", "Retains Red Cloud".
    r"(?:engages?|engaged|retains?|retained)\s+(?:[\w.&'\-]+\s+){0,5}?"
    r"(?:News|Media|Marketing|Communications|Relations|Wire|Digital|Agency|"
    r"Advertising|Investor|Investing|Awareness)\b|"
    r"(?:engages?|engaged|engaging|retains?|retained)\s+[A-Z][A-Za-z\s.&,]{2,60}\s+"
    r"(?:to\s+provide|for|as)\s+(?:investor\s+relations|IR|marketing|advertising|"
    r"digital\s+marketing|media\s+relations|communications|public\s+relations|"
    r"capital\s+markets)|"
    r"capital\s+markets\s+(?:advisory|advisor)\s+(?:agreement|engagement)"
    r")\b",
    re.I,
)
# v2 matched these against the FULL body, so a booth number or a conference
# name in a footer made a drill release a marketing announcement.
# Headline-only. A conference name, a booth number or a webinar link in the
# BODY is a footer on a release about something else -- that is how a drill
# release became a marketing announcement.
_MKT_HEAD_ONLY = re.compile(
    r"(?i)(?:"
    r"\b(?:booth\s+#?\s?\d+|trade\s+show)\b|"
    r"\b(?:to\s+participate|will\s+participate|participates?|to\s+attend|"
    r"attending|to\s+present|presenting|will\s+present|to\s+showcase|"
    r"presents?|presented)\s+(?:at|in)\b"
    r"(?![^.\n]{0,50}(?:private\s+placement|offering|financing|"
    r"bought\s+deal|tranche))|"
    r"\b(?:at|attend\w*|participat\w*|present\w*|host\w*|showcas\w*|"
    r"exhibit\w*|speak\w*|invited)\b[^.\n]{0,45}?"
    r"\b(?:conference(?!\s+call)|summit|symposium|expo|webinar|webcast|"
    r"virtual\s+event|investor\s+day)\b|"
    r"\b(?:hosting|hosts|hosted)\s+(?:a\s+|an\s+)?(?:webinar|webcast)\b"
    r")"
)

# ===========================================================================
# Corporate Updates -- explicit declarations; the fallback is separate
# ===========================================================================
_CORP = re.compile(
    r"\b("
    r"director\s+changes?|board\s+changes?|management\s+changes?|"
    r"grants?\s+(?:stock\s+options?|RSUs?|DSUs?|restricted\s+(?:share|stock)\s+units?)|"
    r"(?:stock\s+options?|RSUs?|DSUs?)\s+(?:granted|issued|grant|awarded)|"
    r"option\s+grants?|grant\s+of\s+(?:stock\s+)?options|"
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
    r"welcomes?\s+[A-Z][A-Za-z.&\s]{2,40}\s+to\s+(?:OTCQX|OTCQB|the\s+OTCQX)|"
    r"corporate\s+update|company\s+update|operational\s+update|"
    r"(?:provides?|reports?|issues?|announces?)\s+(?:an?\s+)?"
    r"(?:[\w’\-]+\s+){0,3}?update\b|"
    r"option\s+extension|"
    # exploration activity: programs, mobilisation, surveys, targets. v2 tagged
    # all of this Drill Results.
    r"(?:commences?|commenced|begins?|began|resumes?|resumed|launch(?:es|ed)?|"
    r"mobiliz\w+|completes?|completed|expands?|expanded|advances?|advanced|"
    r"initiates?|initiated|conducts?|conducted|performs?|performed|"
    r"undertakes?|undertook)\s+(?:[\w.,'’\-]+\s+){0,8}?"
    r"(?:drill(?:ing)?(?:\s+program)?|exploration|surveys?|mapping|sampling|"
    r"fieldwork|campaigns?|stud(?:y|ies)|resource\s+estimate|"
    r"technical\s+report|mineraliz\w+|trenching|permitting)|"
    r"(?:phase\s+(?:[IVX]+|\d+|one|two|three|four|five)\s+)?drill(?:ing)?\s+program|"
    r"(?:high[-\s]?priority|priority|new|additional)\s+drill\s+targets?|"
    r"drill\s+targets?\s+(?:identified|confirmed|defined|established)|"
    r"identif(?:y|ies|ied)\s+(?:high[-\s]?priority\s+|new\s+|additional\s+)?"
    r"(?:drill\s+)?targets?|"
    r"(?:IP|induced[-\s]polarization|geophysical|airborne|magnetic|gravity|EM|"
    r"electromagnetic|ZTEM|VTEM)\s+(?:survey\s+)?"
    r"(?:results?|defines?|identifies?|confirms?)|"
    r"filing\s+of\s+(?:court|litigation|claim|statement|suit)|"
    r"court\s+action|legal\s+proceedings?|"
    r"(?:filing|files)\s+(?:a\s+)?(?:lawsuit|complaint|claim)|"
    r"technology\s+(?:development\s+)?agreement|"
    r"(?:signs|enters\s+into)\s+.{0,40}(?:partnership|collaboration|cooperation)|"
    r"memorandum\s+of\s+understanding|\bMOU\b|"
    r"termination\s+of\s+.{0,40}(?:option|agreement|consulting|contract)|"
    r"consulting\s+agreement|"
    r"share\s+issuances?|"
    r"receipt\s+of\s+(?:interim\s+order|final\s+order|court\s+order)|"
    r"interim\s+order\s+for|"
    r"establish(?:es|ed|ing)\s+(?:new\s+|[A-Z][A-Za-z]+\s+)*"
    r"(?:headquarters|office|subsidiary|operations|presence|hub)|"
    r"files?\s+.{0,40}(?:prospectus|circular|proxy|MD&A|interim|annual\s+report)|"
    r"issues?\s+shares?\s+(?:pursuant|as\s+consideration|in\s+settlement)|"
    # --- v3d: routine corporate news the 6,543 uncategorised were full of
    r"debt\s+settlement|shares?\s+for\s+(?:services|debt)|"
    r"issues?\s+(?:[\w’\-]+\s+){0,3}?shares?\b|share\s+issuance|"
    r"\b(?:stock\s+options?|incentive\s+(?:stock\s+)?options?|RSUs?|DSUs?)\b|"
    r"(?:extension|amendment|repricing|cancellation|exercise)\s+of\s+"
    r"(?:the\s+|its\s+|certain\s+|incentive\s+)?(?:warrants?|options?)|"
    r"market\s+maker(?:\s+services)?|"
    r"leadership\s+(?:changes?|transition|appointment)|"
    r"(?:senior\s+)?management\s+transition|"
    r"\b(?:clarif\w+|corrects?|correction|retraction|restates?)\b|"
    r"incorporat\w+\s+(?:[\w\-]+\s+){0,3}?(?:subsidiary|sub\b|company)|"
    r"(?:receives?|granted|awarded)\s+(?:an?\s+)?(?:[\w\-]+\s+){0,3}?"
    r"(?:permit|licence|license|approval|order|grant\b)|"
    r"trade\s+resumption|cease\s+trade|halt(?:ed)?\s+trading|"
    r"(?:appoints?|engages?)\s+(?:[\w\-]+\s+){0,3}?"
    r"(?:auditor|transfer\s+agent|advisor|consultant)"
    r")\b",
    re.I,
)




# ===========================================================================
# v4 categories, carved out of the Corporate Updates bucket. Every one is
# HEADLINE-scoped for the reason v3 established: a phrase in the body is not
# what the release is about.
# ===========================================================================

_V4_GAP = r"(?:[\w.,'’\-%$&/]+\s+){0,6}?"

# Exploration Programs. The verb list is SPLIT: `advance`/`expand` also live
# inside company names -- "Advanced Gold Exploration" is a company, and with a
# broad noun list its own name parsed as "<verb> <stuff> <exploration>", 13
# times. Those two verbs may only reach an explicit "<x> program".
_EXPLORATION = re.compile(
    r"(?i)(?:"
    r"\b(?:commences?|commenced|begins?|began|starts?|started|resumes?|resumed|"
    r"launch(?:es|ed)?|mobiliz\w+|initiates?|initiated|completes?|completed|"
    r"conducts?|conducted|undertakes?|kicks?\s+off|prepares?\s+for)\s+" + _V4_GAP +
    r"(?:drill(?:ing)?\s+programs?|exploration\s+programs?|field\s+programs?|"
    r"work\s+programs?|drill\s+campaigns?|drilling\b|exploration\b|fieldwork|"
    r"trenching|geological\s+mapping|sampling\s+programs?)|"
    r"\b(?:advances?|advanced|expands?|expanded)\s+" + _V4_GAP +
    r"(?:drill(?:ing)?\s+programs?|exploration\s+programs?|field\s+programs?|"
    r"work\s+programs?|drill\s+campaigns?)|"
    # v5: defining targets from geochem/geophysics. Measured at 8% drill data,
    # so this is exploration work product, not a drill result.
    r"\b(?:identifies?|identified|outlines?|outlined|defines?|defined|"
    r"delineates?|delineated)\s+" + _V4_GAP +
    r"(?:drill\s+targets?|drill\s+plans?|targets?|anomal\w+|"
    r"geochemical\s+zone|corridor)\b|"
    r"\b(?:phase\s+(?:[IVX]+|\d+|one|two|three|four|five)|\d[\d,]*\s*"
    r"(?:m\b|metre|meter)\w*)\s+" + _V4_GAP + r"(?:drill(?:ing)?\s+program|"
    r"exploration\s+program)|"
    r"\b(?:drill(?:ing)?|exploration|field|work)\s+program\s+"
    r"(?:underway|commenc\w+|begins?|update|planned|expanded)|"
    r"\b(?:IP|induced[-\s]polarization|geophysical|airborne|magnetic|gravity|"
    r"electromagnetic|ZTEM|VTEM|magnetotelluric|seismic|LiDAR|radiometric|"
    r"DCIP|soil\s+geochem\w*)\s+(?:survey|program|data)|"
    r"\bsurvey\s+(?:commenc\w+|underway|completed|results?)"
    r")"
)

_PERMITS = re.compile(
    r"(?i)(?:"
    r"\b(?:receives?|received|is\s+granted|grants?|granted|obtains?|obtained|"
    r"secures?|secured|awarded|submits?|submitted|applies\s+for|applied\s+for|"
    r"files?\s+for|approved\s+for|renew(?:s|ed)?)\s+" + _V4_GAP +
    r"(?:permits?|licen[cs]es?|approvals?|authorization|certificate)|"
    r"\b(?:drill(?:ing)?|exploration|mining|environmental|water|operating|"
    r"blasting|land[-\s]use)\s+permits?\b|"
    r"\bpermit\s+(?:application|approval|granted|received|amendment|renewal|receipt)|"
    r"\benvironmental\s+(?:assessment|approval|permit|authorization)|"
    r"\bnotice\s+of\s+work\b|"
    r"\b(?:regulatory|government|ministerial)\s+approval"
    r")"
)

_METALLURGY = re.compile(
    r"(?i)(?:"
    r"\bmetallurg\w+|\bmet\s+(?:test|work)\w*\b|"
    r"\bflotation\b|\bleach(?:ing)?\s+test\w*\b|\bheap\s+leach\b|"
    r"\bbulk\s+sample\b|\bpilot\s+plant\b|\bprocess(?:ing)?\s+plant\b|"
    r"\bmill\s+(?:restart|commission\w*|expansion|throughput)\b|"
    r"\brecover(?:y|ies)\s+(?:test|rate|result)s?\b|"
    r"\b\d[\d.,]*\s*%\s*(?:[\w\-]+\s+){0,3}?recover(?:y|ies)\b|"
    r"\brecovers?\s+\d[\d.,]*\s*%|"
    r"\bconcentrate\s+(?:grade|production|shipment)\b|"
    r"\bgravity\s+circuit\b|\bcomminution\b|\bassay\s+lab\b"
    r")"
)

# Share Capital & Compensation. Warrants need an ACTION word: the bare noun is
# in nearly every financing headline.
_SHARE_CAPITAL = re.compile(
    r"(?i)(?:"
    r"\b(?:stock\s+options?|incentive\s+(?:stock\s+)?options?|RSUs?|DSUs?|"
    r"restricted\s+(?:share|stock)\s+units?|deferred\s+share\s+units?|"
    r"performance\s+share\s+units?)\b|"
    r"\b(?:grants?|granted|awards?|awarded|issuance\s+of|repric\w+|"
    r"cancellation\s+of|amendment\s+to)\s+" + _V4_GAP + r"options?\b|"
    r"\b(?:extension|amendment|repricing|acceleration|exercise|expiry|"
    r"early\s+exercise)\s+of\s+" + _V4_GAP + r"warrants?\b|"
    r"\bwarrant\s+(?:extension|repricing|exercise|acceleration|expiry|amendment)|"
    r"\b(?:extends?|extended|reprices?|amends?)\s+(?:[\w\-]+\s+){0,2}?warrants?\b|"
    r"\b(?:investors?|holders?)\s+exercise\s+" + _V4_GAP + r"warrants?|"
    r"\bdebt\s+settlement|\bshares?\s+for\s+(?:debt|services)|"
    r"\bsettlement\s+of\s+(?:outstanding\s+)?(?:debt|indebtedness|payables)|"
    r"\brepurchase\s+and\s+cancellation\s+of\s+" + _V4_GAP + r"shares?\b|"
    r"\bissues?\s+" + _V4_GAP +
    r"shares?\s+(?:to|for|in\s+settlement|pursuant|as\s+consideration)"
    r")"
)

_LISTINGS = re.compile(
    r"(?i)(?:"
    r"\b(?:lists?|listing|listed|uplist\w+|commence[sd]?\s+trading|"
    r"begins?\s+trading|approved\s+for\s+(?:listing|trading)|graduat\w+\s+to|"
    r"admitted\s+to\s+trading)\b[^.\n]{0,40}"
    r"\b(?:OTCQB|OTCQX|OTC\s+Markets|Frankfurt|FSE|NASDAQ|NYSE|TSX|TSXV|CSE|"
    r"LSE|AQSE|Canadian\s+Securities\s+Exchange|Venture\s+Exchange)\b|"
    r"\b(?:OTCQB|OTCQX|Frankfurt|NASDAQ|NYSE|TSXV?|CSE)\b[^.\n]{0,40}"
    r"\b(?:listing|uplisting|dual\s+list\w+|de[-\s]?listing)\b|"
    r"\bDTC\s+eligib\w+|\bCUSIP\b|"
    r"\b(?:inclusion\s+(?:in|into)\s+the\s+[A-Z]{2,6}\b|index\s+inclusion|"
    r"added\s+to\s+the\s+[\w\s]{0,20}index)\b|"
    r"\b(?:cease\s+trade|trading\s+halt|halt(?:ed)?\s+trading|"
    r"trade\s+resumption|resumption\s+of\s+trading|reinstatement\s+of\s+trading)"
    r")"
)

_MEETINGS = re.compile(
    r"(?i)(?:"
    r"\bannual\s+(?:and\s+special\s+)?(?:general\s+)?meeting\b|"
    r"\bannual\s+general\s+and\s+special\s+meeting\b|"
    r"\bAGM\b|\bAGSM\b|"
    r"\bspecial\s+meeting\s+of\s+(?:the\s+)?(?:shareholders|securityholders|"
    r"security\s*holders)\b|"
    r"\bshareholder\s+meeting\b|\bmeeting\s+of\s+shareholders\b|"
    r"\bresults?\s+of\s+(?:the\s+)?(?:annual|special)\b|"
    r"\b(?:proxy|information)\s+circular\b|\bvoting\s+results?\b"
    r")"
)

_CORP_ACTIONS = re.compile(
    r"(?i)(?:"
    r"\bname\s+change\b|\bchanges?\s+(?:its\s+)?(?:corporate\s+)?name\b|"
    r"\bchange\s+its\s+name\b|\bchanges?\s+name\s+to\b|"
    r"\bsymbol\s+change\b|\bticker\s+(?:symbol\s+)?change\b|\bnew\s+ticker\b|"
    r"\bshare\s+consolidation\b|\bconsolidat\w+\s+of\s+(?:its\s+)?"
    r"(?:common\s+)?shares\b|"
    r"\breverse\s+split\b|\bforward\s+split\b|\bstock\s+split\b|\brebrand\w+"
    r")"
)

_PARTNERSHIPS = re.compile(
    r"(?i)(?:"
    r"\bjoint\s+ventures?\b|\bJV\s+(?:agreement|partner)\b|"
    r"\bstrategic\s+(?:partnership|alliance|collaboration)\b|"
    r"\bpartnership\s+(?:with|agreement)\b|"
    r"\bcollaboration\s+agreement\b|\bcooperation\s+agreement\b|"
    r"\boff[-\s]?take\s+agreement\b|\btoll\s+mill\w+\b|"
    r"\bmemorandum\s+of\s+understanding\b|\bMOU\b|"
    r"\bteams?\s+up\s+with\b|\bpartners\s+with\b"
    r")"
)


# ===========================================================================
# v6 recall pass (2026-09-15). Parallel constants, OR-ed in at the call site,
# so no existing pattern is edited. Every one of these was derived from a
# measured bucket in the Corporate-Updates-only corpus, not from imagination.
# ===========================================================================

# The gap class needs the LEFT curly quote too. U+2018 opens "Acquires the
# 'South-Advocate Hydrogen Project'" and the class only had U+2019.
_V6_GAP = r"(?:[\w.,'’‘\"“”\-%$&/]+\s+){0,6}?"

# --- Management Changes without a parseable person ------------------------
# management_extract answers "who moved into what role". When the headline
# names nobody it returns nothing, and 194 releases fell through.
_MGMT_ROLE = (r"(?:CEO|CFO|COO|CTO|President|Chair(?:man|person|woman)?|"
              r"Directors?|Board|Officers?|VP|Vice[-\s]President|"
              r"General\s+Counsel|Treasurer|Secretary|Managers?|Advisors?|"
              r"Advisory\s+(?:Board|Council)|Geologist|Executive)")

_MGMT_HEAD = re.compile(
    r"(?i)(?:"
    r"\b(?:appoints?|appointed|appointments?\s+of|names?)\s+" + _V6_GAP +
    _MGMT_ROLE + r"\b|"
    r"\bappoints?\s+(?:new\s+)?(?:[\w.\-]+\s+){1,3}(?:as|to)\b|"
    r"\b(?:resignations?|resigns?|resigned|steps?\s+down|stepping\s+down|"
    r"departure\s+of|retires?\s+as|retirement\s+of)\b|"
    r"\bleadership\s+(?:changes?|transition|appointments?)\b|"
    r"\b(?:senior\s+)?management\s+(?:changes?|transition)\b|"
    r"\bboard\s+(?:changes?|appointments?|refresh\w*|renewal)\b|"
    r"\bchange\s+of\s+(?:officer|director|management)\b|"
    r"\b(?:strengthens?|bolsters?|expands?|adds?\s+to)\s+" + _V6_GAP +
    r"(?:board\b|management\s+team|leadership\s+team|"
    r"advisory\s+(?:board|council))|"
    r"\b(?:joins?|joining)\s+(?:the\s+)?(?:board|advisory\s+board|"
    r"management\s+team)\b"
    r")"
)
# Hiring a service provider is not a management change. Without this,
# "Appoints New Auditor" and "Appoints Red Cloud as IR Advisor" both land in
# Management Changes.
_MGMT_NOT = re.compile(
    r"(?i)\b(?:auditors?|transfer\s+agent|market\s+makers?|"
    r"investor\s+relations|IR\s+(?:firm|advisor|provider)|"
    r"marketing\s+(?:firm|agency|services)|"
    r"communications\s+(?:firm|agency)|"
    r"(?:legal|financial)\s+advisors?\s+(?:firm|to\s+the))\b"
)

# --- Corporate Actions: dividends, buybacks, consolidations ---------------
_CORP_ACTIONS_V6 = re.compile(
    r"(?i)(?:"
    r"\b(?:declares?|declaration\s+of|announces?|initiates?|increases?|"
    r"reinstates?|suspends?)\s+" + _V6_GAP + r"dividends?\b|"
    r"\b(?:quarterly|semi-?annual|annual|special|inaugural|regular|monthly)\s+"
    r"(?:cash\s+)?dividends?\b|"
    r"\bdividend\s+(?:policy|declaration|payment|record\s+date|of\s+)|"
    r"\bnormal\s+course\s+issuer\s+bid\b|\bNCIB\b|"
    r"\bsubstantial\s+issuer\s+bid\b|"
    r"\bshare\s+(?:buy-?back|repurchase)\s+program\b|"
    r"\bproposed\s+consolidation\b|"
    r"\bannounces?\s+(?:a\s+)?(?:proposed\s+)?(?:share\s+)?consolidation\b|"
    r"\bconsolidation\s+of\s+" + _V6_GAP + r"shares?\b|"
    r"\bearly\s+warning\s+report\b|"
    r"\b(?:adopts?|adoption\s+of)\s+" + _V6_GAP +
    r"(?:semi-?annual|quarterly)\s+(?:financial\s+)?reporting\b|"
    r"\breporting\s+exemption\b"
    r")"
)

# --- Share Capital: the reverse noun order ---------------------------------
_SHARE_CAPITAL_V6 = re.compile(
    r"(?i)(?:"
    r"\boptions?\s+grants?\b|\boption\s+grants?\b|"
    r"\bgrant\s+of\s+(?:stock\s+|incentive\s+)?options?\b|"
    r"\b(?:equity\s+)?incentive\s+plan\b|"
    r"\bshare\s+issuances?\b|"
    r"\brestricted\s+share\s+unit\s+grants?\b"
    r")"
)

# --- Listings: the venue is there, the verb is a noun ----------------------
_LISTINGS_V6 = re.compile(
    r"(?i)(?:"
    r"\bcommencement\s+of\s+" + _V6_GAP + r"trading\b|"
    r"\b(?:OTCQB|OTCQX|OTC\s+Markets)\b[^.\n]{0,30}\btrading\b|"
    r"\btrading\b[^.\n]{0,30}\b(?:OTCQB|OTCQX)\b|"
    r"\bwelcomes?\b[^\n]{0,60}?\bto\s+(?:the\s+)?(?:OTCQX|OTCQB)\b|"
    r"\b(?:begins?|commences?|commenced)\s+trading\s+(?:on|under|as)\b|"
    r"\bgraduat\w+\s+to\s+(?:the\s+)?(?:TSX|TSXV|CSE|NYSE|NASDAQ|"
    r"Toronto\s+Stock\s+Exchange)\b|"
    r"\buplist\w+\b"
    r")"
)

# --- M&A: the word-boundary defect and the curly quote --------------------
_MA_V6 = re.compile(
    r"(?i)\b(?:acquires?|acquisition\s+of|to\s+acquire)\s+" + _V6_GAP +
    r"(?:minerals?|prospects?|concessions?|tenements?|projects?|propert\w+|"
    r"claims?|leases?|licen[cs]es?|royalt\w+|interests?|assets?|deposits?|"
    r"mines?|stakes?|land\s+package|compan(?:y|ies)|corp\w*|\binc\b|\bltd\b|"
    r"limited|resources?|metals?|holdings?)"
)

# --- Exploration: surveys that do not say "survey" next, and progress -----
# Justin's call, 2026-09-15: a drilling progress report with no assays is part
# of the PROGRAM, not a result. Drill Results keeps meaning "there are numbers
# in this release".
_EXPLORATION_V6 = re.compile(
    r"(?i)(?:"
    r"\bgeophysic\w+|"
    r"\b(?:MT|IP|DCIP|3DIP|ZTEM|VTEM|EM|CSAMT)\s+surveys?\b|"
    r"\b(?:magnetotelluric|radiometric|aeromagnetic|induced[-\s]polarization)\b|"
    r"\b(?:soil|rock|channel|surface|grab|till|stream\s+sediment)\s+"
    r"sampl\w+|"
    r"\bsampling\s+(?:program|campaign|underway|commenc\w+)\b|"
    r"\b(?:commences?|commenced|begins?|initiates?|completes?|completed)\s+" +
    _V6_GAP + r"sampling\b|"
    r"\b(?:drilling|exploration|fieldwork|field\s+work|work\s+program)\s+"
    r"(?:progress\s+)?updates?\b|"
    r"\bdrilling\s+progress\b|"
    r"\bauger\s+drilling\b|\btrench(?:es|ing)\b|"
    r"\bfield\s+(?:work|program|reconnaissance)\b|"
    r"\bdownhole\s+survey\b|\bopticals?\s+televiewer\b"
    r")"
)


# ===========================================================================
# Delegation. management_extract is the authority on what a management change
# IS, so the category asks it. Imported lazily and guarded: if it is ever
# missing, categorisation degrades rather than raising on every ingest.
# ===========================================================================

_EXTRACTORS: dict[str, object] = {}


def _get(name: str, attr: str):
    """Resolve an extractor under whichever name is importable here.

    management_extract lives at /opt/mnt/app/ and imports bare; drill_extract
    and resource_extract live in /opt/mnt/app/portal/ and import as portal.*.
    The running app only has /opt/mnt/app on sys.path, so a bare-only lookup
    silently disables the drill rescue in production while working on the
    bench. Try both.
    """
    key = f"{name}.{attr}"
    if key not in _EXTRACTORS:
        fn = False
        for modname in (name, f"portal.{name}"):
            try:
                mod = __import__(modname, fromlist=[attr])
                fn = getattr(mod, attr)
                break
            except Exception:
                continue
        _EXTRACTORS[key] = fn
    return _EXTRACTORS[key]


def _is_management_change(headline: str | None) -> bool:
    fn = _get("management_extract", "extract")
    if not fn:
        return False
    try:
        return bool(fn(headline or "").get("changes"))
    except Exception:
        return False


def _has_intercepts(headline: str | None, body: str | None) -> bool:
    fn = _get("drill_extract", "extract")
    if not fn:
        return False
    try:
        return bool(fn(headline or "", body or "").get("intercepts"))
    except Exception:
        return False


# ===========================================================================
# The categoriser
# ===========================================================================

def _categorize_v6(headline: str | None, body: str | None) -> list[str]:
    """Return the categories this release belongs to, in CATEGORIES order.

    Nothing is matched against the full body. Every rule sees either the
    headline alone or the subject window (headline + lede cut at boilerplate).
    """
    h = (headline or "").strip()
    b = (body or "").strip()
    subj = subject(h, b)
    third_party = bool(_THIRD_PARTY.search(h))

    cats: list[str] = []

    # --- Financings: headline says so, or the lede DECLARES one ------------
    if _FIN.search(h) or _FIN_EXTRA.search(h) or _FIN_DECLARE.search(subj):
        cats.append("Financings")

    # --- Drill Results: headline reports results, or intercepts + a lede
    #     that declares them --------------------------------------------
    if (_DRILL_RESULT_HEAD.search(h) or (
            _DRILL_LEDE.search(subj) and _has_intercepts(h, b))
            ) and not (_DRILL_HISTORICAL.search(h)
                       and not _DRILL_NEW_WORK.search(h)):
        cats.append("Drill Results")

    # --- Resource Estimates: an estimate delivered, not commissioned -------
    if (_MRE.search(h) and not third_party
            and (_MRE_DELIVERED.search(h) or not _STUDY_PLAN.search(h))):
        cats.append("Resource Estimates")

    # --- Management Changes: unchanged, already delegated ------------------
    if _is_management_change(h) or (_MGMT_HEAD.search(h)
                                    and not _MGMT_NOT.search(h)):
        cats.append("Management Changes")

    # --- Economic Studies: a delivered study, not a commissioned one -------
    if (_ECON.search(h) and not third_party
            and (_STUDY_DELIVERED.search(h) or not _STUDY_PLAN.search(h))):
        cats.append("Economic Studies")

    # --- Production Results: mining production, not oil & gas, not a plan --
    # Both vetoes read the HEADLINE, not the subject window. Scoped to the
    # body they killed four real quarterly production reports, because a gold
    # miner's body says "barrels" and Wesdome's headline says "on track".
    if (_PROD.search(h) and not third_party
            and not _OIL_GAS.search(h) and not _PROD_NOT.search(h)):
        cats.append("Production Results")

    # --- Financials: headline only, and not a notice that results are due --
    if _FINL.search(h) and not _NOTICE.search(h) and not third_party:
        cats.append("Financials")

    # --- M&A: headline says so, or the lede DECLARES a transaction --------
    if (_MA_HEAD.search(h) or _MA_V6.search(h)
            or _MA_DECLARE.search(subj)) and not third_party:
        cats.append("Mergers & Acquisitions")

    # --- v4 categories: headline-scoped, additive -------------------------
    if _EXPLORATION.search(h) or _EXPLORATION_V6.search(h):
        cats.append("Exploration Programs")
    if _PERMITS.search(h) and not third_party:
        cats.append("Permits & Approvals")
    if _METALLURGY.search(h):
        cats.append("Metallurgy & Processing")
    if _SHARE_CAPITAL.search(h) or _SHARE_CAPITAL_V6.search(h):
        cats.append("Share Capital & Compensation")
    if _LISTINGS.search(h) or _LISTINGS_V6.search(h):
        cats.append("Listings & Exchange")
    if _MEETINGS.search(h):
        cats.append("Shareholder Meetings")
    if _CORP_ACTIONS.search(h) or _CORP_ACTIONS_V6.search(h):
        cats.append("Corporate Actions")
    if _PARTNERSHIPS.search(h):
        cats.append("Partnerships & JV")

    # --- Marketing: subject scope; booths and trade shows headline only ---
    if _MKT.search(subj) or _MKT_HEAD_ONLY.search(h):
        cats.append("Marketing Announcement")

    # --- Corporate Updates: explicit declaration --------------------------
    if _CORP.search(subj):
        cats.append("Corporate Updates")

    # --- Corporate Updates is the bucket of last resort --------------------
    # If anything more specific matched, drop it. It means "nothing else fits";
    # carrying it alongside a real category made the chip a duplicate of the
    # whole feed instead of a filter.
    if len(cats) > 1 and "Corporate Updates" in cats:
        cats = [c for c in cats if c != "Corporate Updates"]

    # --- ...or the bucket for everything that matched nothing -------------
    if FALLBACK_TO_CORPORATE and not cats:
        cats.append("Corporate Updates")

    return cats


# ===========================================================================
# v7 -- pipeline review, 2026-09-15. Justin: "look at Corporate Updates, the
# catch-all, for anything that should have landed in a real tag".
#
# 14,687 of 43,505 approved releases (34%) carried Corporate Updates alone.
# Three reading rounds (a 450-release random sample, then 450 and 380 more of
# what was still left) found misses in all 17 real categories. The rules
# below are ADDITIVE: v6 runs unchanged as _categorize_v6(), and v7 only adds
# categories, then re-applies "Corporate Updates is the bucket of last resort".
# Measured on the whole corpus in both directions before shipping -- see
# claude/MNT_PIPELINE_REVIEW_2026-09-15.md in the project.
#
# A HOLLOW headline ("News release", a disclaimer line, a trading-symbol line)
# is categorised twice -- once as stored, once with the real title recovered
# from the first lines of the document -- and the union is kept, so recovery
# can add a category but never take one away. The stored headline is not
# touched.
#
# Every gap between two anchors is a character gap over [^\n]: inside a
# headline there is no sentence to run past, and a gap must be able to cross a
# period ("H.C. Wainwright"), a percent sign, a curly quote and a ">".
# ===========================================================================

G = lambda n: r"[^\n]{0," + str(n) + r"}?"

# ---------------------------------------------------------------- helpers
_PERIOD = (r"(?:(?:Q|q)\s?[1-4]|[1-4]Q|(?:first|second|third|fourth)\s+(?:fiscal\s+)?quarter|"
           r"(?:full|half|fiscal)[-\s]year|year[-\s]end(?:ed)?|annual|interim|"
           r"(?:first|second)\s+half|H[12]|(?:three|six|nine|twelve)\s+months|fiscal\s+(?:20)?\d\d|FY\s?(?:20)?\d\d)")
_NOT_FIN_RESULTS_UNUSED = r"(?:exploration|drill\w*|assay|sampling|metallurg\w*|test\w*|survey|program\w*|geophysic\w*|soil|trench\w*|study|PEA|PFS|feasibility|resource)"

# ---------------------------------------------------------------- Financials
FINL_V7 = re.compile(
    r"(?i)(?:"
    r"\b(?:financial|operating|operational)\s+(?:and|&)\s+(?:financial|operating|operational)\s+results?\b|"
    r"\b" + _PERIOD + r"\b(?:[\s,\-]+(?:and|&|of|for|the|ended|ending|to|(?:20)?\d\d|FY\s?(?:20)?\d\d|fiscal|full[-\s]year|year[-\s]end|"
    r"quarter|months|june|march|september|december|\d{1,2},?|unaudited|audited|preliminary|interim|record|solid|strong|robust|positive|"
    r"consolidated|financial|annual)){0,7}[\s,\-]+(?:financial\s+)?(?:(?:and|&)\s+(?:operating|operational)\s+)?(?:results?|earnings|financials)\b|"
    r"\b(?:results?|earnings)\s+(?:for\s+(?:the\s+)?)?" + _PERIOD + r"\b|"
    r"\bearnings\s+(?:results?|release|call|conference\s+call)\b|"
    r"\b(?:notice\s+of|to\s+(?:release|report|announce|issue|host)|will\s+(?:release|report|announce)|"
    r"schedules?|release\s+date|call\s+details|details\s+of)\b" + G(40) + r"\b(?:" + _PERIOD + r"|financial|earnings)\b" + G(40) + r"\b(?:results?|earnings|financials|call)\b|"
    r"\b" + _PERIOD + r"\b" + G(40) + r"\bconference\s+call\b|"
    r"\bconference\s+call\s+(?:and\s+webcast\s+)?details\b|"
    r"\b(?:record|quarterly|annual)\s+(?:\w+\s+)?(?:revenues?|net\s+income|net\s+profit|free\s+cash\s+flow|EBITDA)\b|"
    r"\b(?:revenues?|net\s+profit|net\s+income)\s+(?:of|up|increase\w*|grow\w*|rises?)\b|"
    r"\breports?\s+(?:record\s+)?sales\s+of\s+(?:US|C|CA)?\$|"
    r"\b(?:files?|filed|filing\s+of)\b" + G(40) + r"\b(?:annual\s+information\s+form|AIF|40-F|20-F|10-K|"
    r"(?:audited\s+|annual\s+|interim\s+)?financial\s+statements|annual\s+report|MD&A)\b|"
    r"\b(?:40-F|20-F)\b" + G(30) + r"\bfiled\b"
    r")"
)

FINL_V7_NOT = re.compile(r"(?i)\b(?:meeting|AGM|voting|vote|shareholders?|production\s+results?|exploration\s+results?|assay|drill\w*)\b")

# ---------------------------------------------------------------- Production
PROD_V7 = re.compile(
    r"(?i)(?:"
    r"\b" + _PERIOD + r"\b" + G(40) + r"\b(?:operating|operational|production)\s+(?:results?|update|highlights)\b|"
    r"\b" + _PERIOD + r"\b" + G(30) + r"\b(?<!financial\sand\s)(?<!financial\s&\s)(?:operating|operational)\s+results?\b|"
    r"\bproduc(?:es|ed|tion\s+of|ing)\b" + G(30) + r"\b(?:ounces|oz|GEOs?|AgEq|AuEq|CuEq|tonnes|pounds|lbs|carats|dmt|wmt)\b|"
    r"\bproduction\s+guidance\b|\b(?:record|quarterly|annual|full[-\s]year)\s+(?:gold\s+|silver\s+|copper\s+|uranium\s+|attributable\s+)?production\b|"
    r"\b(?:first|initial)\s+(?:gold\s+pour|gold\s+(?:bar|dor[eé])|dor[eé]|concentrate|cathode|anode|shipment|production)\b" + G(30) + r"\b(?:produced|poured|shipped|achieved|at|from)\b|"
    r"\b(?:delivers?|achieves?|pours?|produces?|celebrates?)\s+(?:its\s+)?first\s+gold\b|"
    r"\bfirst\s+(?:gold\s+)?pour\b|"
    r"(?<!P\.)(?-i:\bGEOs?\b)|\bgold\s+equivalent\s+ounces\b|"
    r"\brecover(?:y|s|ed)\s+(?:of\s+)?" + G(30) + r"\bcarat\b"
    r")"
)

PROD_V7_NOT = re.compile(r"(?i)\b(?:notice\s+of|to\s+(?:release|report|announce|host)|will\s+(?:release|report)|conference\s+call|webcast|call\s+details)\b")

# ---------------------------------------------------------------- Resources
MRE_V7 = re.compile(
    r"(?i)(?:"
    r"\bmineral\s+reserves?\b|\breserves?\s+(?:and|&)\s+(?:mineral\s+)?resources?\b|"
    r"\bresources?\s+(?:and|&)\s+reserves?\b|\bMRMR\b|"
    r"\bM\s?&\s?I\b" + G(40) + r"\b(?:resources?|ounces|oz|tonnes|lbs|pounds)\b|"
    r"\b(?:doubl|tripl|increas|grow|expand|upgrad)\w*\b" + G(40) +
    r"\b(?:measured|indicated|inferred|mineral\s+resource)\b|"
    r"\b(?:files?|filed|filing\s+of|completes?|completion\s+of|releases?|publishes?)\b" + G(40) +
    r"\btechnical\s+reports?\b"
    r")"
)

# ---------------------------------------------------------------- Econ
ECON_V7 = re.compile(
    r"(?i)(?:"
    r"\bpreliminary\s+economic\b|\bscoping\s+study\b|\bproject\s+economics\b|"
    r"\blife[-\s]of[-\s]mine\s+plan\b|\bLOM\s+plan\b|"
    r"\b(?:NPV|IRR)\b"
    r")"
)

# ---------------------------------------------------------------- Drill Results
_METAL = (r"(?:au|ag|cu|pb|zn|ni|co|sb|mo|sn|w|u3o8|li2o|reo|treo|pgm|pge|p2o5|v2o5|wo3|"
          r"gold|silver|copper|lead|zinc|nickel|cobalt|antimony|molybdenum|tin|tungsten|li20|"
          r"gallium|germanium|rubidium|cesium|caesium|scandium|niobium|tantalum|indium|tellurium|bismuth|rhodium|iridium|"
          r"uranium|lithium|graphite|platinum|palladium|rare\s+earths?|phosphate|vanadium|"
          r"AuEq|AgEq|CuEq|NiEq|ZnEq|gold\s+equivalent|copper\s+equivalent|silver\s+equivalent)")
DRILL_V7 = re.compile(
    r"(?i)(?:"
    r"\b\d[\d.,]*\s*(?:grams?\s+per\s+tonne|grams?\s*/\s*tonne|g\s*/\s*tonne|oz\s*/\s*ton|ounces?\s+per\s+ton)\s+" + G(15) + _METAL + r"\b|"
    r"\b(?:intersects?|intercepts?|drills|drilled|returns?|cuts?|hits?|encounters?)\b" + G(50) +
    r"\b\d[\d.,]*\s*(?:m|metres?|meters?|ft|feet)\b" + G(40) + r"\b(?:of|at|grading|averaging|@)\b" + G(10) + r"\d|"
    r"\bdrill[-\s]?holes?\s+(?:assay\s+)?results?\b|\bassays?\s+(?:returned|received|confirm\w*)\b|"
    r"\b\d[\d.,]*\s*%\s*" + _METAL + r"\b\s+(?:over|across)\s+\d[\d.,]*\s*(?:m\b|metres?|meters?|ft\b|feet)"
    r")"
)
# grade-less intersections and progress: Exploration Programs per Justin 2026-09-15

# ---------------------------------------------------------------- Exploration
_PROG = r"(?:programs?|programmes?|plans?(?!\s+of\s+operations)|campaigns?|budgets?|season|strategy|activities)"
EXPLORATION_V7 = re.compile(
    r"(?i)(?:"
    r"\b(?:drill(?:ing)?|exploration|field|work|diamond\s+drill(?:ing)?|core\s+drill(?:ing)?|RC\s+drill(?:ing)?|"
    r"geophysical|geochemical|sampling|prospecting|mapping|summer|winter|fall|spring|maiden\s+drill|inaugural\s+drill|"
    r"follow[-\s]up|step[-\s]out|infill|phase\s+(?:[IVX]+|\d|one|two|three))\s+" + _PROG + r"\b|"
    r"\b(?:drilling|drill\s+rigs?|second\s+drill|drill\s+crews?|diamond\s+drill\w*|core\s+drilling|RC\s+drilling|fieldwork|field\s+work|field\s+crews?|field\s+activities)\b"
    + G(40) + r"\b(?:underway|commenc\w+|begins?|began|resum\w+|starts?|started|mobiliz\w+|mobilis\w+|arriv\w+|conclud\w+|"
    r"completed?|ramps?\s+up|progress\w*|continues?|expan\w+|planned|nearing)\b|"
    r"\b(?:mobiliz\w+|mobilis\w+|commence\w*|commencement\s+of|begins?|resum\w+|resumption\s+of|starts?|launch\w*|initiat\w+|"
    r"secures?\s+(?:a\s+)?contractor|engages?|contracts?|completes?|completion\s+of|conclud\w+|expands?|accelerat\w+)\b" + G(50) +
    r"\b(?:drilling|drill\s+rigs?|drill\s+crews?|drill\s+contractor|drill\s+hole|fieldwork|field\s+(?:work|crews?|season|activities|campaign)|"
    r"prospecting|exploration\s+activities|sampling|mapping)\b|"
    r"\b(?:mag|magnetic|aeromagnetic|drone|UAV|TDEM|AMT|MobileMT|gravity|seismic|hyperspectral|LiDAR|ambient\s+noise|tomography|"
    r"borehole\s+EM|BHEM|ground\s+EM|HLEM|VLF|FLEM|TEM|radon|biogeochemical|till)\s+surveys?\b|"
    r"\bsurveys?\b" + G(40) + r"\b(?:completed?|results?|commenc\w+|underway|identif\w+|discovers?|defines?|outlines?|reveals?)\b|"
    r"\b(?:completes?|commences?|launches?|begins?|conducts?|initiates?)\b" + G(50) + r"\bsurveys?\b|"
    r"\b(?:identif\w+|defines?|defined|delineat\w+|outlines?|finds?|discovers?|models?|generates?|refines?|develops?|highlights?|reports?)\b"
    + G(60) + r"\b(?:anomal(?:y|ies)|conductors?|conductive|chargeability|drill\s+targets?|exploration\s+targets?|new\s+targets?|"
    r"targets?\s+(?:at|on|for)|pegmatites?|gossans?|mineralized\s+boulders?|soil\s+anomal\w+|trends?\s+(?:at|on))\b|"
    r"\bexploration\s+(?:update|results?|strategy|budget|activities|season)\b|"
    r"\b(?:program|campaign)\s+(?:and|&)\s+budget\b|\b(?:increased|approved|expanded)\s+(?:exploration\s+)?budget\b|"
    r"\b(?:structural|geological)\s+(?:mapping|model\w*|interpretation|study)\b|\b3D\s+(?:geological\s+)?model\w*\b|"
    r"\bgrade[-\s]block\s+model\w*\b|\bre-?logging\b|\bcore\s+(?:logging|re-?sampling)\b|\bassays?\s+pending\b|"
    r"\b(?:submits?|shipped|ships)\b" + G(40) + r"\b(?:core|samples)\b" + G(30) + r"\b(?:assay|lab\w*)\b|"
    r"\b(?:intersects?|intercepts?|encounters?)\b" + G(50) + r"\b(?:mineraliz\w+|mineralis\w+|sulphides?|sulfides?|veins?|pegmatites?|"
    r"zones?|system|structures?|formation)\b"
    r")"
)

# ---------------------------------------------------------------- M&A
MA_V7 = re.compile(
    r"(?i)(?:"
    r"\b(?:expands?|expanded|expansion\s+of|increases?|grows?|doubles?|doubling|triples?|quadruples?|enlarges?|adds?|added|"
    r"consolidates?)\b" + G(40) +
    r"\b(?:land\s+(?:package|position|holdings?|base)|claims?|claim\s+(?:block|package)|mineral\s+tenures?|tenures?|concessions?|"
    r"land\s+footprint|acreage|hectares|mineral\s+rights|size\s+of\s+(?:the\s+|its\s+)?" + G(30) + r"(?:propert\w+|projects?))\b|"
    r"\b(?:completes?|completion\s+of)\s+(?:claim\s+)?staking\b|\bannounces?\s+staking\b|\bstaking\s+(?:of|at|in)\b|"
    r"\b(?:completes?|completion\s+of|closes?|closing\s+of|announces?|enters?\s+into|signs?|executes?)\b" + G(30) +
    r"\b(?<!debt\s)(?<!loan\s)(?:proposed\s+)?(?:transaction|definitive\s+agreement|binding\s+agreement|securities\s+exchange\s+agreement|"
    r"share\s+purchase(?!\s+(?:warrants?|plan))|asset\s+purchase|purchase\s+and\s+sale|sale\s+agreement(?!\s+for\s+(?:concentrate|product|material))|arrangement\s+agreement)\b|"
    r"\bproposed\s+transaction\b|"
    r"\b(?:sells?|sold|disposes?|disposition\s+of|divests?|to\s+sell|agreement\s+to\s+sell)\b" + G(60) +
    r"\b(?:claims?|propert\w+|projects?|interest|stake|royalt\w+|assets?|subsidiary|mines?|shares\s+of|portfolio)\b|"
    r"\boption\s+agreement\b|"
    r"\boptions?\b" + G(50) + r"\b(?:mines?|projects?|propert\w+|claims?)\b(?![^\n]{0,3}\bgrant)|"
    r"\broyalty\s+(?:purchase|sale|buy[-\s]?back|acquisition)\b|\b(?:buys?\s+back|repurchases?)\b" + G(20) + r"\broyalty\b|"
    r"\bacqui(?:res?|sition\s+of)\b(?!\s+(?:of\s+)?(?:new\s+|additional\s+|historical\s+|extensive\s+)*(?:data|dataset|drill\b|rigs?|equipment|core|software|LiDAR))"
    + G(90) + r"\b(?:propert\w+|projects?|claims?|mines?|deposits?|concessions?|licen[cs]es?|interest|stake|ownership)\b|"
    r"\b(?:approves?|approval\s+of|approved)\b" + G(30) + r"\barrangement\b|\barrangement\s+(?:agreement|with|resolution)\b|"
    r"\bspin[-\s]?(?:out|off)\b|\bspinout\b|"
    r"\b(?:secures?|obtains?)\s+(?:exclusive\s+)?(?:mineral|mining|exploration)\s+rights\b|"
    r"\bcombine\b" + G(30) + r"\b(?:to\s+create|forces)\b"
    r")"
)

MA_V7_NOT = re.compile(r"(?i)\bshares?\s+for\s+debt\b|\bdebt\s+settlement\b|\bloan\s+transaction\b|\bfinancing\s+transaction\b")

# ---------------------------------------------------------------- Management
_ROLE7 = (r"(?:CEO|CFO|COO|CTO|CSO|CIO|President|Chair(?:man|person|woman)?|Directors?|Board|Officers?|VP|SVP|EVP|"
          r"Vice[-\s]President|Chief\s+[A-Z]\w+(?:\s+[A-Z]\w+)?\s+Officer|General\s+Counsel|Treasurer|"
          r"Corporate\s+Secretary|Country\s+Manager|General\s+Manager|Mine\s+Manager|Exploration\s+Manager|"
          r"Advisors?|Advisers?|Advisory\s+(?:Board|Council|Committee)|Executive\s+(?:Chair\w*|Director|Officer|Vice[-\s]President|Team|Appointments?)|Senior\s+Executives?|Geologist)")
MGMT_V7 = re.compile(
    r"(?:"
    r"(?i:\bpassing\s+of\b|\bpassed\s+away\b|\bin\s+memoriam\b|\bmourns?\b|\btribute\s+to\b" + G(20) + r"\blate\b)|"
    r"(?i:\b(?:strengthens?|bolsters?|expands?|adds?\s+to|builds?\s+out|enhances?|streamlines?|restructures?|reorganiz\w+)\b)" + G(30) +
    r"(?i:\b(?:team|board|leadership|management|executive\s+team|technical\s+team|advisory\s+(?:board|team|group|council)))\b|"
    r"(?i:\b(?:announces?|welcomes?|names?|introduces?|confirms?|engages?|hires?)\s+(?:the\s+)?(?:new\s+|interim\s+|acting\s+|key\s+)?)"
    r"(?:(?:[A-Z][\w.'\-]+\s+){1,4}(?i:as\s+(?:the\s+)?(?:new\s+|interim\s+)?))?" + r"(?i:" + _ROLE7 + r")\b|"
    r"(?i:\b(?:change|changes)\s+(?:of|in|to)\s+(?:the\s+)?(?:its\s+)?)(?i:" + _ROLE7 + r")\b|"
    r"(?i:\b(?:CEO|CFO|COO|President|Chair\w*|Board|Officer|Director|Executive|Management|Leadership)\s+"
    r"(?:update|transition|succession|changes?|appointments?|additions?)\b)|"
    r"(?i:\bappoint\w*\b)" + G(80) + r"(?i:\b(?:as|to)\s+(?:the\s+|a\s+|an\s+|its\s+|interim\s+|new\s+|independent\s+|non-executive\s+)*)(?i:" + _ROLE7 + r")\b|"
    r"(?i:\badditions?\b)" + G(60) + r"(?i:\bto\s+(?:its\s+|the\s+)?(?:\w+\s+)?(?:management|board|advisory|leadership|technical|executive|senior)\b)|"
    r"(?i:\b(?:management|board|advisory|leadership|team)\s+additions?\b)|"
    r"(?i:\bagrees?\s+to\s+(?:act|serve|join)\s+as\b)|"
    r"(?i:\b(?:appointed|resigns?|resigned|steps?\s+down|retires?)\b)"
    r")"
)
MGMT_V7_NOT = re.compile(
    r"(?i)\b(?:auditors?|transfer\s+agent|market\s+mak\w+|investor\s+relations|IR\s+(?:firm|advisor|provider)|"
    r"marketing|communications\s+(?:firm|agency)|financial\s+advisors?|legal\s+counsel|drill(?:ing)?\s+contractor|"
    r"contractor|consultants?\s+(?:firm|group)|qualified\s+person|index|executive\s+orders?|receivers?|trustees?|monitor|underwriters?)\b|"
    r"\bjoins\s+the\b" + G(40) + r"\badvisory\s+committee\b|\bsocial\s+monitoring\b"
)

# ---------------------------------------------------------------- Financings
FIN_V7 = re.compile(
    r"(?i)(?:"
    r"\b(?:clos\w+|complet\w+)\b" + G(50) + r"\b(?:financings?|placements?|offerings?|tranches?|debentures?|raises?|financing\s+round)\b|"
    r"\b(?:oversubscribed|fully\s+subscribed|upsized)\b" + G(30) + r"\b(?:financings?|placements?|offerings?|round)\b|"
    r"\b(?:total|gross|aggregate)\s+proceeds\b|\bproceeds\s+of\s+(?:approximately\s+)?(?:US|C|CA|A)?\$|"
    r"(?:US|C|CA|A)?\$\s?[\d,.]+\s*(?:million|M|k|thousand)?\s+" + G(15) + r"\btranches?\b|"
    r"\b(?:debt\s+financing|project\s+financ\w+|credit\s+(?:agreement|facility)|term\s+loan|bridge\s+loan|loan\s+(?:facility|agreement)|"
    r"gold\s+prepay\w*|prepay(?:ment)?\s+(?:facility|arrangements?|agreement)|(?:gold|silver|copper|precious\s+metals?)\s+stream|"
    r"stream(?:ing)?\s+(?:transaction|financing|deal)|multi-facility|debt\s+facility|financing\s+package|green\s+bonds?|"
    r"convertible\s+(?:notes?|debentures?|loans?|facility)|royalty\s+financing|equity\s+financing|financing\s+round)\b|"
    r"\b(?:announces?|secures?|arranges?|obtains?|receives?)\s+" + G(20) + r"\bloans?\b|"
    r"\bstrategic\s+(?:equity\s+)?investment\b|\b(?:announces?|makes?|completes?|closes?)\s+(?:an?\s+)?(?:additional\s+)?(?:equity\s+)?investment\s+(?:in|into)\s+[A-Z]|\binvestment\s+(?:by|from)\s+[A-Z]|"
    r"\b(?:ATM|at[-\s]the[-\s]market)\s+(?:program|equity|offering|sales|facility)\b|"
    r"\btop[-\s]up\s+rights?\b|\bparticipation\s+rights?\b|"
    r"\b(?:financing|placement|offering)\s+(?:is\s+)?(?:fully\s+subscribed|oversubscribed|upsized|increased|extended|amended|terminated|priced)\b"
    r")"
)

FIN_V7_NOT = re.compile(r"(?i)\b(?:disposition|dispos\w+|sale\s+of|sells?|sold)\b" + G(60) + r"\bproceeds\b")

# ---------------------------------------------------------------- Share Capital
CAP_V7 = re.compile(
    r"(?i)(?:"
    r"\b(?:share[-\s]based|equity|long[-\s]term\s+incentive|LTI)\s+(?:compensation\s+|incentive\s+)?(?:grants?|awards?)\b|"
    r"\bgrants?\s+of\s+(?:long[-\s]term\s+)?(?:incentive|equity)\s+(?:awards?|compensation)\b|"
    r"\b(?:amend\w*|extend\w*|extension\w*|repric\w*|expir\w+|exercis\w+|accelerat\w+|expedit\w+)\b" + G(50) + r"\bwarrants?\b|"
    r"\bwarrants?\b" + G(30) + r"\b(?:exercised|exercises?|extension|amendment|repricing|expiry|term)\b|"
    r"\bsets?\s+options\b|\bissu\w+\s+of\s+(?:common\s+|bonus\s+)?shares\b|\b(?:securities|shares)\s+for\s+services\b|"
    r"\bappendix\s+(?:2A|3B|3G|3H|3Y)\b|\bproposed\s+issue\s+of\s+securities\b|\bcessation\s+of\s+securities\b|"
    r"\bescrow\s+release\b|\bbonus\s+shares\b"
    r")"
)

# ---------------------------------------------------------------- Listings
LIST_V7 = re.compile(
    r"(?i)(?:"
    r"\btrade\s+halt\b|\btrading\s+halt\w*\b|\bhalts?\s+trading\b|\bhalted\b|\bIIROC\b|\bCIRO\b|"
    r"\b(?:upgrades?|upgraded|moves?\s+to|graduat\w+|approv\w+)\b" + G(40) + r"\b(?:OTCQX|OTCQB|Best\s+Market|Venture\s+Market)\b|"
    r"\bapproval\s+to\s+trade\b|\b(?:to|will)\s+(?:begin\s+|commence\s+|start\s+)?trade\s+on\b|\bbegins?\s+(?:active\s+)?trading\b|"
    r"\blisting\s+(?:process|application)\b|"
    r"\bunaware\s+of\s+any\s+(?:material\s+)?(?:change|undisclosed|corporate\s+developments?)\b|"
    r"\b(?:MCTO|management\s+cease\s+trade|default\s+status\s+report|cease\s+trade\s+order)\b|"
    r"\b(?:addition|added|inclusion|included|joins?)\b" + G(50) + r"\bindex\b"
    r")"
)

# ---------------------------------------------------------------- Meetings
MTG_V7 = re.compile(
    r"(?i)(?:"
    r"\bshareholders'?\s+(?:meeting|approv\w+|vote[sd]?)\b|\bsecurity\s*holders?\s+approv\w+\b|"
    r"\bmeeting\s+materials\b|\bproxy\s+advisory\b|\bvote\s+(?:for|in\s+favou?r)\b|\bgeneral\s+meeting\b|"
    r"\b(?:annual|special)\s+(?:and\s+special\s+)?meeting\b"
    r")"
)

# ---------------------------------------------------------------- Corporate Actions
ACT_V7 = re.compile(
    r"(?i)(?:"
    r"\bto\s+become\s+(?-i:[A-Z][\w&'.\-]*)(?:\s+(?-i:[A-Z][\w&'.\-]*)){0,5}\s+(?:inc|corp|corporation|ltd|limited)\b\.?|\bnew\s+name\b|"
    r"\bchanges?\s+(?:its\s+)?(?:financial\s+|fiscal\s+)?year[-\s]end\b|"
    r"\b(?:intention\s+to|intends\s+to|proposes?\s+to)\s+(?:complete|effect|implement)\s+(?:a\s+)?(?:share\s+)?consolidation\b|"
    r"\bconsolidation\s+(?:ratio|effective|of\s+common)\b|\bpost[-\s]consolidation\b|"
    r"\bcontinuance\b|\bredomicil\w*|\bdomesticat\w+\b"
    r")"
)

# ---------------------------------------------------------------- Partnerships
JV_V7 = re.compile(
    r"(?i)(?:"
    r"\bJV\b|"
    r"\b(?:signs?|signed|enters?\s+into|executes?|announces?|establish\w*|reach\w*|forms?|renews?|extends?)\b" + G(50) +
    r"\b(?:collaboration|cooperation|partnership|alliance|agreement\s+in\s+principle|milestone\s+agreement|community\s+agreement|"
    r"benefits?\s+agreement|exploration\s+agreement|accommodation\s+agreement|relationship\s+agreement|investor\s+rights\s+agreement|"
    r"framework\s+agreement|collaboration\s+framework|strategic\s+agreement)\b|"
    r"\b(?:First\s+Nations?|Indigenous|M[ée]tis|Inuit)\b" + G(60) + r"\b(?:agreement|partnership|MOU|LOI)\b|"
    r"\bconsortium\b|\boff[-\s]?take\b|\bsupply\s+agreement\b"
    r")"
)

# ---------------------------------------------------------------- Permits
PER_V7 = re.compile(
    r"(?i)(?:"
    r"\b(?:receives?|received|granted|obtains?|obtained|secures?|secured|awarded|submits?|submitted|files?\s+for)\b"
    + G(90) + r"\b(?:permits?|licen[cs]es?|authorization|authorisation|(?<!shareholder\s)(?<!securityholder\s)(?<!stockholder\s)approvals?)\b|"
    r"\bplan\s+of\s+operations\b|\brecord\s+of\s+decision\b|\bterms\s+of\s+reference\b|\b(?:EIS|ESIA)\b|"
    r"\bimpact\s+assessment\b|\bmining\s+lease\s+(?:application|granted|approv\w+|renew\w+)|\bgrant\w*\s+(?:of\s+)?(?:a\s+|the\s+)?mining\s+lease\b|\bexploitation\s+(?:licen[cs]e|concession)\b|"
    r"\bwater\s+(?:licen[cs]e|use\s+permit)\b|\bvested\s+rights?\b|\bpriority\s+project\b|\bnational\s+interest\s+designation\b|"
    r"\bFAST-?41\b|\bgreen\s+light\b|\b(?:receives?|gets?|given|secures?)\s+(?:the\s+)?(?:regulatory\s+)?greenlight\b|"
    r"\b(?:initiates?|advances?|submits?|completes?|commences?|begins?)\b" + G(40) + r"\bpermitting\b|\bpermitting\s+(?:process|timeline|schedule|milestone)\b|"
    r"\b(?:exploration|mineral|mining)\s+licen[cs]es?\s+(?:granted|approved|issued|renewed)\b"
    r")"
)

# ---------------------------------------------------------------- Metallurgy
MET_V7 = re.compile(
    r"(?i)(?:"
    r"\bpatent\w*\b" + G(50) + r"\b(?:recovery|process\w*|extraction|leach\w*|refin\w+|separation)\b|"
    r"\b(?:recovery|processing|extraction|refining|separation)\s+(?:technology|process|patent|facility)\b|"
    r"\bmagnetic\s+concentrate\b|\b(?:test\s?work|bench[-\s]scale|pilot[-\s]scale|scale[-\s]up|flowsheet|mineralog\w+|beneficiation|"
    r"ore\s+sorting|sorting\s+test|hydrometallurg\w+|pyrometallurg\w+|(?<!net\s)smelter|refinery)\b"
    r")"
)

# ---------------------------------------------------------------- Marketing
MKT_V7 = re.compile(
    r"(?i)(?:"
    r"\b(?:attend\w*|present\w*|participat\w*|exhibit\w*|sponsor\w*|speak\w*|host\w*|showcas\w*|invited|featured|feature)\b" + G(90) +
    r"\b(?:conferences?(?!\s+call)|conventions?|summits?|symposi\w+|expos?|webinars?|PDAC|roadshows?|investor\s+(?:forum|day|events?)|"
    r"metals\s+investor\s+forum|mining\s+showcase|podcast|investment\s+(?:conference|forum|summit))\b|"
    r"\b(?:PDAC)\b" + G(20) + r"\b(?:convention|booth|20\d\d)\b|"
    r"\b(?:investor|corporate|company)\s+presentation\b|\blive\s+presentation\b|\bwebinar\b|\bpodcast\b|\binterview\b|"
    r"\bInside\s+the\s+Boardroom\b|\bBTV\b|\bnew\s+canadian\s+stocks\b|\bAGORACOM\b|\broadshow\b|"
    r"\bmarket[-\s]?mak\w+\b|\bliquidity\s+provider\w*\b|\bautomated\s+market\b|"
    r"\b(?:marketing|awareness|advertising|communications|investor\s+relations|digital\s+media|media|IR)\s+"
    r"(?:programs?|campaigns?|agreements?|services|consulting|firm|contracts?|engagements?|extension)\b|"
    r"\b(?:engages?|retains?|hires?)\b" + G(50) + r"\b(?:research|analyst\s+coverage|equity\s+research)\b|"
    r"\binitiat\w+\s+(?:of\s+)?(?:analyst\s+|research\s+)?coverage\b"
    r")"
)
MKT_V7_NOT = re.compile(r"(?i)\b(?:results?|earnings)\b" + G(60) + r"\b(?:conference\s+call|webcast)\b|\b(?:conference\s+call|webcast)\b" + G(60) + r"\b(?:results?|earnings|Q[1-4])\b")


# =====================================================================
# Round 2 -- from reading 450 releases still left in Corporate Updates
# after round 1. OR-ed with the round-1 constant of the same category.
# =====================================================================
FIN_V7B = re.compile(
    r"(?i)(?:"
    r"\b(?:non[-\s])?(?:brokered\s+)?private\s+placements\b|\bcapital\s+raise\b|\bbridge\s+financing\b|\bfinancing\s+offer\b|"
    r"\bbest[-\s]efforts\s+(?:private\s+)?(?:offering|placement)\b|\b(?:bought\s+deal\s+)?public\s+offering\b|"
    r"\bsecondary\s+offering\b|\b(?:convertible\s+)?senior\s+(?:secured\s+)?notes\b|\bdebt\s+agreement\b|"
    r"\b(?:equity|standby|share\s+subscription|convertible\s+securities)\s+(?:facility|agreement)\b|"
    r"\bdraws?\s+(?:down\s+)?(?:from|on|under|of)\b|\bdrawdowns?\b|\bplacement\s+priv[ée]\b|\bfinancements?\b|"
    r"\bupfront\s+capital\s+funding\b|\bletter\s+of\s+interest\b" + G(40) + r"\b(?:bank|EXIM|export|financ\w+)\b|"
    r"\b(?:base\s+)?shelf\s+prospectus\b|\bprospectus\s+supplement\b"
    r")"
)
DRILL_V7B = re.compile(
    r"(?i)(?:"
    r"\b\d[\d.,]*\s*(?:m|metres?|meters?)\s+(?:of|at|grading)\s+\d[\d.,]*\s*(?:g\s*/\s*t|gpt|%|ppm)\s*" + _METAL + r"\b|"
    r"\b\d[\d.,]*\s*(?:grams?\s+per\s+tonne|g\s*/\s*t|gpt)\b\s+(?:\w+\s+){0,2}?(?:over|across)\s+\d[\d.,]*\s*(?:m\b|metres?|meters?|ft\b|feet)|"
    r"\b\d[\d.,]*\s*(?:g\s*/\s*t|gpt|%|ppm)\s*(?:Pd\s*\+\s*Pt(?:\s*\+\s*Au)?|Pt\s*\+\s*Pd(?:\s*\+\s*Au)?|3E|2PGE|Cg|TGC|Cs2O|Rb2O|BeO)\b"
    r")"
)
EXPLORATION_V7B = re.compile(
    r"(?i)(?:"
    r"\b(?:(?:to|will)\s+(?:drill|test)|plans?\s+to\s+drill|gears?\s+up\s+for\s+drilling|in\s+advance\s+of\s+drilling|"
    r"drill[-\s]ready|test\s+(?:gold\s+)?(?:exploration\s+)?targets)\b|"
    r"\b(?:mobiliz\w+|mobilis\w+|adds?|doubles?)\s+(?:a\s+|the\s+|its\s+)?(?:second\s+|third\s+|additional\s+|diamond\s+|core\s+|RC\s+)?drill(?:s|\s+rigs?)?\b|"
    r"\b(?:announces?|plans?|launch\w*|initiat\w+|advanc\w+|outlines?|begins?|commenc\w+|continues?|approves?|designs?)\b" +
    r"(?:(?!\b(?:marketing|awareness|incentive|outreach|advertising|investor|tokeni[sz]ation|partnership|buy-?back|rights|environmental|baseline|"
    r"recovery|ESG|sustainability|community|social|training|stock|equity|ATM|loyalty|warrant|option|share|research|digital|media|IR|"
    r"placement|financing|offering|fund\w*|proceeds|test\w*|metallurg\w*|pilot|certification|compliance|reporting|safety)\b)[^\n]){0,60}?"
    r"\b(?:program|programme)\b(?!\s+(?:of\s+)?(?:with|for)\s+(?:shareholders|investors))|"
    r"\bcontinues?\s+(?:to\s+)?(?:drill|explor\w+|exploration)\b|\bcontinu\w+\s+exploration\b|"
    r"\b(?:new\s+|makes?\s+(?:a\s+)?(?:new\s+)?)(?:gold\s+|copper\s+|silver\s+|lithium\s+|uranium\s+|rare\s+earth\s+)?discover(?:y|ies)\b|"
    r"\bdiscover(?:s|ed|ies\s+of)\b(?!\s+day)|\bdiscovery\s+(?:of|at|on|work|zone)\b|"
    r"\b(?:soil|rock|till|lake\s+sediment|stream\s+sediment|biogeochem\w*|geochem\w*|geomicrobial)\s+(?:\w+\s+)?(?:results?|survey|data|anomal\w+)\b|"
    r"\b(?:preliminary\s+)?geochemical\s+(?:results?|analysis|data)\b|\b(?:IP|VTEM|MT|DCIP|magnetic|gravity)\s+(?:and\s+\w+\s+)?(?:results?|modell?ing|inversions?|target\s+zone)\b|"
    r"\b(?:magnetometer|satellite|WorldView|ASTER|hyperspectral|LiDAR|AI[-\s]assisted|machine\s+learning)\s+(?:\w+\s+){0,2}(?:survey|study|analysis|imagery|image|targeting|acquisition)\b|"
    r"\b(?:data\s+compilation|compilation\s+and\s+data\s+review|data\s+review|targeting\s+and\s+model\w+|deposit\s+models?|geologic(?:al)?\s+interpretation|"
    r"structural\s+geology|zonation|site\s+visit|field\s+investigations?|metallic\s+screen|re-?assay\s+program)\b|"
    r"\b(?:new|additional|multiple|priority|\d+)\s+(?:\w+\s+){0,2}targets?\s+(?:identified|defined|delineated|generated|at|on)\b|"
    r"\b(?:identif\w+|defines?|delineat\w+|confirms?|establish\w+|extends?|expands?|reports?|finds?|encounters?|hits?|samples?|unlocks?)\b" + G(60) +
    r"\b(?:mineraliz\w+|mineralis\w+|pegmatites?|porphyry|intrusion|veins?|(?-i:horizons|Horizons\b(?!\s+[A-Z]))|structures?|alteration|anomalous|showings?|occurrences?|"
    r"indicators?|trend|target\s+zone|strike\s+length|enrichment)\b|"
    r"\bstep[-\s]?out\b|\b(?:completes?|drills?)\s+(?:\w+\s+){0,3}(?:holes?|drill\s+holes?)\b|\bdrill\s+holes?\s+(?:indicate|confirm|intersect)\w*\b|"
    r"\b(?:engages?|retains?|hires?)\b" + G(40) + r"\b(?:geological|exploration|geophysical|geoscience)\s+(?:consult\w+|services|contractor)\b"
    r")"
)
_DISCOVERY_NAME = re.compile(r"(?-i:\bDiscovery\s+(?:Lithium|Silver|Minerals|Metals|Harbour|Gold|Day|Resources|Mines|Ventures))|\b(?:Exploits|Newfoundland|Advanced)\s+Discovery\b")
PROD_V7B = re.compile(
    r"(?i)(?:"
    r"\bproduction\b" + G(40) + r"\b\d[\d,.]*\s*(?:million\s+|thousand\s+)?(?:ounces|oz|koz|Moz|tonnes|t\b|pounds|lbs|carats|GEOs?)\b|"
    r"\breports?\s+production\b|\b(?:record|strong|solid)\s+(?:\w+\s+){0,2}production\b|\b(?:monthly|quarterly)\s+production\b|"
    r"\bproduction\s+and\s+sales\b|\boperating\s+(?:performance|progress)\b|\bramps?\s+up\s+production\b|"
    r"\b(?:shipment|exports?)\s+(?:of\s+)?(?:\w+\s+){0,3}concentrates?\b|\b(?:second|third|first|\d+(?:st|nd|rd|th))\s+shipment\b|"
    r"\bexports?\s+\d[\d,.]*\s*tonnes\b|\bbegins?\s+(?:placer\s+)?(?:gold\s+)?(?:recovery|sales|processing)\b|"
    r"\boperations\s+update\s+for\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\b|"
    r"\bgenerates?\b" + G(30) + r"\brevenue\s+from\b"
    r")"
)
PROD_V7_OIL = re.compile(r"(?i)\boil\s+production\b|\boil\b|\bgas\s+well\b|\bspud\w*\b|\bwells?\b|\bDuvernay\b|\bboe\b")
FINL_V7B = re.compile(
    r"(?i)(?:"
    r"\breports?\s+results\s+for\s+the\s+(?:year|quarter)\b|\bquarterly\s+(?:financial\s+)?results\b|\bnet\s+earnings\b|\boperating\s+cash\s+flow\b|"
    r"\brecord\s+financial\s+performance\b|\battributable\s+revenue\b|\brevenue\s+guidance\b|"
    r"\bquarterly\s+(?:activities\s+)?report\b|\bquarterly\s+report\s+of\s+activities\b|\bForm\s+10-Q\b"
    r")"
)
MGMT_V7B = re.compile(
    r"(?:"
    r"(?i:\bstrengthening\s+(?:its\s+)?(?:management|leadership|board|executive|technical)\b)|"
    r"(?i:\bappointment\s+of\b)" + G(60) + r"(?i:\bas\s+(?:the\s+)?(?:company|corporation)['’]s\s+)(?i:" + _ROLE7 + r")\b|"
    r"(?i:\bjoins?\s+)(?:[A-Z][\w'’\-]*\s+){0,3}(?i:(?:board|advisory\s+board|management\s+team|leadership\s+team)\b)|"
    r"(?i:\bannounces?\s+)(?:[A-Z][\w.'’\-]*\s+){1,3}(?:and|&)\s+(?:[A-Z][\w.'’\-]*\s+){1,3}(?i:as\s+(?:\w+\s+)?)(?i:" + _ROLE7 + r")|"
    r"(?i:\baddition\s+of\b)" + G(60) + r"(?i:\bas\s+(?:the\s+|its\s+|a\s+|an\s+)?(?:[\w\-]+\s+){0,3}?(?:" + _ROLE7 + r"|manager))\b|"
    r"(?i:\b(?:changes?\s+in\s+management|organizational\s+changes|CFO\s+commences\s+role)\b)|"
    r"(?i:\b(?:CEO|CFO|COO|President)\s+(?:commences|assumes|begins)\s+(?:role|position|duties)\b)"
    r")"
)
MA_V7B = re.compile(
    r"(?i)(?:"
    r"\b(?:completes?\s+)?purchase\s+of\s+\d[\d,.]*\s*(?:square\s+kilomet\w+|km2|hectares|ha\b|acres)\b|"
    r"\b(?:acquires?|stakes?|adds?)\s+(?:an?\s+)?(?:additional\s+)?\d[\d,.]*\s*(?:additional\s+)?(?:mineral\s+|lode\s+|placer\s+|new\s+)?"
    r"(?:acres|hectares|ha\b|claims?|square\s+kilomet\w+|km2|licen[cs]es)\b|"
    r"\bstakes?\s+(?:a\s+)?new\b" + G(40) + r"\b(?:project|property|claims?)\b|\bfiling\s+of\s+\d+\s+(?:mineral\s+|lode\s+)?claims\b|"
    r"\bclaims?\s+purchase\b|\b(?:property|project|asset|claims?)\s+(?:acquisition|sale)\b|"
    r"\bincreases?\s+(?:its\s+)?ownership\b|\bconsolidation\s+of\s+ownership\b|\bnow\s+owns\s+100\s*%|"
    r"\bacquiring\s+(?:prospective\s+|additional\s+|new\s+)?(?:\w+\s+)?(?:projects?|propert\w+|claims)\b|"
    r"\bacquires\s+(?:a\s+)?(?:cluster|portfolio|package)\s+of\b|\bexpands?\s+(?:its\s+)?(?:\w+\s+){0,2}(?:portfolio|land\s+base)\b|"
    r"\baddition\s+to\s+the\b" + G(40) + r"\bpropert(?:y|ies)\b|\binks?\s+(?:a\s+)?definitive\b|\bspinning\s+out\b|"
    r"\b(?:royalty|stream)\s+portfolio\b|\bexclusive\s+right\s+to\s+(?:expand|acquire)\b|\blease\s+termination\b|"
    r"\bdue\s+diligence\s+agreement\b|\bexclusivity\s+agreement\b|\bnot\s+proceeding\s+with\b|\btransaction\s+update\b|"
    r"\bamends?\s+agreement\s+for\s+100\s*%"
    r")"
)
MKT_V7B = re.compile(
    r"(?i)(?:"
    r"\b(?:mining\s+)?investment\s+event\b|\b121\s+mining\b|\binvitation\s+to\b" + G(30) + r"\b(?:investment|mining|conference|summit|forum)\b|"
    r"\bconference\s+schedule\b|\bRenmark\b|\bCorpComm\b|\binvestor\s+relations\s+(?:and\s+[\w\s]{0,30})?(?:agreements?|services)\b|"
    r"\bconsulting\s+services\s+agreement\s+with\b" + G(30) + r"\b(?:media|marketing|communications)\b|"
    r"(?<!\[)\bvideo\b(?!\s+enhanced)|\bCEO\s+Clips\b|\bfact\s+sheet\b|\bupdated\s+presentation\b|\bfeatured\s+in\b|\bring\s+(?:the\s+)?(?:\w+\s+)?(?:closing|opening)\s+bell\b|"
    r"\bnew\s+(?:corporate\s+)?website\b|\bcapital\s+markets\s+day\b"
    r")"
)
LIST_V7B = re.compile(
    r"(?i)(?:"
    r"\bCSE\s+Bulletin\b|\bnew\s+(?:U\.?S\.?\s+)?(?:stock\s+|trading\s+)?symbol\b|\bexchange\s+listings?\b|\bcommence\s+[àa]\s+n[ée]gocier\b|"
    r"\badmission\s+of\s+shares\b|\bat\s+(?:the\s+)?request\s+of\s+(?:OTC\s+Markets|CIRO|IIROC|the\s+(?:TSX|CSE))\b|\btrading\s+suspension\b|\bsuspension\s+of\s+trading\b"
    r")"
)
ACT_V7B = re.compile(
    r"(?i)(?:"
    r"\bshareholder\s+rights\s+plan\b|\bchange\s+of\s+name\b|\beffective\s+date\s+(?:for|of)\s+(?:the\s+)?(?:share\s+)?consolidation\b|"
    r"\bcorporate\s+reorganization\b|\breturn\s+of\s+capital\b|\bautomatic\s+share\s+purchase\s+plan\b|\bshare\s+(?:repurchase|buy-?back)\b|\brachat\s+d.actions\b|\bfundamental\s+change\s+of\s+business\b|"
    r"\bchange\s+of\s+business\b"
    r")"
)
MTG_V7B = re.compile(r"(?i)\belection\s+of\s+directors\b|\bshareholder\s+requisition\b|\brequisition(?:ed)?\s+meeting\b")
PER_V7B = re.compile(r"(?i)\brenewal\s+of\b" + G(30) + r"\blicen[cs]e\b|\benvironmental\s+baseline\b|\bsurface\s+(?:rights\s+)?(?:access\s+)?agreements?\b")
JV_V7B = re.compile(
    r"(?i)(?:"
    r"\b(?:adds?|add)\b" + G(40) + r"\bto\s+(?:the\s+)?exploration\s+agreement\b|\bshare[-\s]based\s+partnership\b|\bprocessing\s+agreements?\b|"
    r"\bmining\s+services?\s+agreements?\b|\bprotocole\s+d.entente\b|\bresearch\s+(?:program|collaboration|partnership)\b|"
    r"\bjoins?\b" + G(40) + r"\b(?:association|institute|alliance)\b|\breceives?\s+(?:an?\s+)?(?:purchase\s+)?order\s+from\b"
    r")"
)
MRE_V7B = re.compile(
    r"(?i)(?:"
    r"\b(?:grows?|increases?|expands?|upgrades?|doubles?|boosts?)\b" + G(40) + r"\bresources?\b(?!\s+(?:corp|inc|ltd|limited|sector|industry|nationalism))|"
    r"\bNI[-\s]?43[-\s‐]?101(?:\s+(?:technical\s+)?report)?\b" + G(20) + r"\b(?:files?|filed|filing|receives?|on\b)|"
    r"\b(?:files?|filed|filing\s+of|receives?)\b" + G(30) + r"\bNI[-\s]?43[-\s‐]?101\b"
    r")"
)
MET_V7B = re.compile(
    r"(?i)(?:"
    r"\bbio-?leach\w*\b|\b(?:tailings|residue)\s+(?:re-?processing|recovery|reprocessing)\b|\b(?:scandium|lithium|metal|gold|cobalt|nickel|rare\s+earth)\s+recovery\b|"
    r"\b(?:hydroxide|carbonate|sulphate|sulfate)\s+test\w*\b|\bPhotonAssay\b|"
    r"\b(?:demonstration|pilot|processing|flotation|leach|concentrator)\s+(?:plant|facility|circuit)\b|"
    r"\bplant\s+(?:refurbishment|relocation|construction|commissioning|restart)\b|\bcommissioning\s+(?:of\s+)?(?:the\s+|its\s+)?(?:[\w\-]+\s+){0,3}(?:plant|mill|facility|circuit|line|concentrator|refinery|smelter|kiln)s?\b|\b(?:plant|mill|facility|circuit|line|concentrator|refinery|smelter)\s+commissioning\b|\bprocessing\s+equipment\b|"
    r"\bconcentrate\s+potential\b"
    r")"
)

MRE_V7_NOT = re.compile(r"(?i)\bpotential\s+to\b|\befforts?\s+to\b|\bto\s+(?:upgrade|expand|grow|increase|update)\b|\bresource[-\s]conversion\b|\bexploration\s+recommendations\b")


# =====================================================================
# Round 3 -- 380 more releases still left in Corporate Updates after round 2.
# =====================================================================
FIN_V7C = re.compile(
    r"(?i)(?:"
    r"\bterm\s+sheet\b" + G(40) + r"\b(?:facility|financing|loan)\b|\bconstruction\s+loan\b|\bdebt\s+facilit(?:y|ies)\b|"
    r"\bfacility\s+upsizing\b|\bupsiz\w+\b" + G(20) + r"\bfacility\b|\b(?:increases?|extends?|arranges?)\s+(?:its\s+)?financing\b|"
    r"\braises?\s+funds\b|\bconcurrent\s+financings?\b|\bproceeds\s+of\b" + G(30) + r"\bfrom\s+(?:the\s+)?(?:warrant\s+|option\s+)?exercises?\b|"
    r"\bnon-dilutive\s+(?:cash|funding|financing)\b|\bequity\s+swap\b|\bmanagement\s+investment\b|"
    r"\brepayment\s+of\b" + G(30) + r"\b(?:debt|debentures?|loans?|notes?)\b"
    r")"
)
EXPLORATION_V7C = re.compile(
    r"(?i)(?:"
    r"\b(?:secures?|signs?|awards?|selects?|engages?)\s+(?:a\s+)?drill(?:ing)?\s+contract(?:or)?\b|\bdrilling\s+contract\b|"
    r"\bfirst\s+hole\s+completed\b|\bresults?\s+from\s+(?:the\s+)?(?:\d{4}\s+)?(?:phase\s+\w+\s+)?drilling\b|"
    r"\bdrills\s+(?:initial|multiple|stacked)\b|\brestarts?\s+drilling\b|\b(?:drilling|exploration)\s+(?:and\s+\w+\s+)?planning\b|"
    r"\bplanning\s+\d{4}\s+drilling\b|\bcontinues?\s+to\s+discover\b|\bnew\s+targets?\b|\btargets?\s+identified\b|"
    r"\bexploration\s+(?:goals|division|timeline|success|advances|targets?)\b|\bprospecting\s+update\b|"
    r"\b(?:AEM|heli-?borne|airborne)\b" + G(20) + r"\bsurvey\b|\bmagneto-?telluric\b|\bgeology\s+map\b|\bhistoric\s+workings\b|"
    r"\bdrill\s+targeting\b|\bpumping\s+test\b|\btest\s+well\b|\bdoubles?\s+exploration\s+target\b|"
    r"\bmore\s+than\s+doubles\b" + G(30) + r"\b(?:zone|length|strike)\b|\b\d[\d.,]*\s*(?:m|metres?|meters?)\s+intersection\b|"
    r"\bdeep-?test\b|\bengages?\b" + G(40) + r"\bfor\s+(?:\d{4}\s+)?exploration\b|\bsurface\s+(?:gold|silver|copper)(?:-\w+)?\s+results\b|"
    r"\bhigh\s+(?:lithium|gold|copper|uranium)\s+values\b|\bhydrogen[-\s]associated\b|\bhydrogen\s+(?:zone|discovery|data)\b|"
    r"\bstrike\s+length\b|\bdefines?\b" + G(40) + r"\bzone\s+over\b"
    r")"
)
PROD_V7C = re.compile(
    r"(?i)(?:"
    r"\bproduced\s+\d|\b(?:resumes?|restarts?|recommences?)\s+(?:\w+\s+)?(?:production|mining|operations)\b|\bproduction\s+restart\b|"
    r"\bmining\s+restart\b|\bcommences?\s+mining\b|\b(?:underground|open[-\s]pit|test|trial|placer)\s+mining\s+commences\b|\bcommenced\s+production\b|"
    r"\b(?:record\s+)?sales\s+in\s+(?:the\s+)?(?:first|second|third|fourth)\s+quarter\b|\bmine\s+operating\s+income\b|\bmined\s+\d|"
    r"\bquarter\s+of\s+production\b|\broyalty\s+payments?\b|\bsuspends?\s+operations\b|\boperational\s+continuity\b|"
    r"\boperations\s+continue\b|\bproduction\s+rate\b"
    r")"
)
MRE_V7C = re.compile(r"(?i)\bupdates?\s+(?:in-pit\s+)?resource\b|\bresource\s+summary\b|\bS-K\s+1300\b")
MA_V7C = re.compile(
    r"(?i)(?:"
    r"\banniversary\s+payments?\b|\boption\s+payments?\b|\bscheduled\s+payment\s+for\b|\bearns?\s+(?:a\s+)?(?:further\s+|additional\s+|\d+\s*%\s+)?interest\b|"
    r"\bdiscontinues?\b" + G(30) + r"\boptions?\b|\breacquires?\b|\btakes?\s+(?:direct\s+)?control\s+of\b|\bdeal\s+closing\b|"
    r"\bpurchases?\s+(?:an?\s+|the\s+)?NSR\b|\bimplementation\s+agreement\b|\btermination\s+of\b" + G(20) + r"\bsale\b|\bsale\s+process\b|"
    r"\blargest\s+(?:contiguous\s+)?land\s+package\b|\bincreases?\s+(?:its\s+)?footprint\b|\bconsolidates?\b" + G(30) + r"\bpropert(?:y|ies)\b|"
    r"\bexpands?\s+(?:its\s+)?holdings\b|\bintroduces?\b" + G(30) + r"\bowned\b" + G(30) + r"\bproject\b|\bstaking\b|"
    r"\bstrategic\s+review\b|\bfor\s+acquisition\b|\bincreased\s+ownership\s+in\b"
    r")"
)
MGMT_V7C = re.compile(
    r"(?:"
    r"(?i:\bpasses\s+away\b|\bterminates?\b" + G(30) + r"\bas\s+(?:CEO|CFO|President)\b|\bappoints?\s+(?:VP|SVP|EVP)\b|"
    r"\badvisory\s+(?:board|committee|commit\w*)\b|\bappoint\w*\s+(?:dr|mr|ms|mrs)\.?\s|\bappointemnets?\b|"
    r"\bupdate\s+on\s+(?:its\s+)?board\s+of\s+directors\b|\bsenior\s+leaders\b|\bto\s+(?:its|the)\s+board\b|"
    r"\bwelcomes?\b" + G(70) + r"\bas\s+(?:senior\s+)?(?:vice\s+president|VP|CFO|CEO|director|advisor|chair\w*)\b|"
    r"\battracts?\b" + G(40) + r"\bto\s+the\s+board\b)"
    r")"
)
LIST_V7C = re.compile(
    r"(?i)(?:"
    r"\bOTCQB\s+quotation\b|\bstarts?\s+trading\s+on\b|\blisting\s+of\s+warrants\b|\bminimum\s+bid\s+price\b|\bextend\s+filing\s+deadline\b|"
    r"\bdelay\s+in\s+(?:\w+\s+)?filing\b|\bannual\s+filings\s+status\b|\bdefault\s+update\b|\b(?:responds?|comments?)\b" + G(40) + r"\bpromotion(?:al)?\s+activit\w+\b|"
    r"\bOTC\s+Markets\s+request\b|\bshare\s+price\s+movement\b|\bresponds\s+to\s+market\s+activity\b|\btrading\s+of\s+its\s+common\s+shares\b|"
    r"\bupdated\s+trading\s+symbols?\b|\bOSC\s+staff\s+review\b|\bpossible\s+delay\s+in\s+filing\b"
    r")"
)
MTG_V7C = re.compile(r"(?i)\badvance\s+notice\s+(?:by-?law|policy)\b|\bISS\s+presentation\b|\bvote\s+(?:green|blue|gold|white)\b|\bdissident\b|\bproxy\s+contest\b")
ACT_V7C = re.compile(r"(?i)\bsemi-?annual\s+reporting\b|\bto\s+consolidate\s+(?:its\s+)?(?:common\s+)?shares\b|\bevolves?\s+(?:in)?to\s+[A-Z]|\bcash\s+dividend\b|\bdividend\s+for\s+the\b")
CAP_V7C = re.compile(r"(?i)\bissues?\s+\d[\d,]*\s+(?:common\s+)?shares\b|\bto\s+issue\s+shares\b|\bshare\s+capital\s+and\s+voting\s+rights\b|\brestricted\s+share\s+rights\b|\b(?:security|share)[-\s]based\s+compensation\s+plan\b|\bwarrants\s+extended\b|\block-?up\s+of\b" + G(40) + r"\bwarrants\b|\bblock\s+listing\b")
PER_V7C = re.compile(
    r"(?i)(?:"
    r"\bpermits?\s+(?:renewed|obtained|received|granted|update)\b|\bpermit\s+renewal\b|\blicen[cs]e\s+renewal\b|\bland\s+access\s+agreements?\b|"
    r"\bsecures?\s+land\s+access\b|\bmining\s+agreement\b|\bproject\s+description\b|\benvironmental\s+(?:impact\s+)?declaration\b|"
    r"\brecovery\s+of\s+minerals\s+permit\b|\bone\s+project,?\s+one\s+process\b|\bpermitting\s+support\b|\bstate\s+lease\s+lands\b|"
    r"\bapproval\s+of\s+application\b|\badvancing\s+permitting\b|\bmining\s+lease\b(?=" + G(30) + r"\b(?:grant|new|approv|renew))|\bgrant\s+of\s+new\s+mining\s+lease\b"
    r")"
)
MET_V7C = re.compile(r"(?i)\bore[-\s]sorting\b|\bmetallurg\w*\s+labs?\b|\b5N\s+purity\b|\bbattery[-\s]grade\b|\bproduction\s+run\b|\bcarbonation\s+technology\b|\bprocessing\s+methodology\b|\bnickel\s+sulphate\b")
MKT_V7C = re.compile(
    r"(?i)(?:"
    r"\bmarketing\s+consultant\b|\bEquity\s+Guru\b|\binvestors?\s+update\s+call\b|\bdocumentary\b|\bwebsite\b|\bcorporate\s+communications\b|"
    r"\bsocial\s+media\b|\bTorrey\s+Hills\b|\bMining\s+Networks\b|\binvestor\s+relations\s+team\b|\bVP\s+of\s+investor\s+relations\b|"
    r"\bresearch\s+coverage\b|\breports\s+on\b" + G(30) + r"\bconference\b|\bluncheon\s+presentation\b"
    r")"
)
JV_V7C = re.compile(r"(?i)\bjoint\s+development\s+agreement\b|\bjoin\s+forces\b|\bfounding\s+member\b|\bproject\s+partner\b|\bevaluation\s+framework\b|\bcollaboration\b")


_SUB = str.maketrans({**{c: str(i) for i, c in enumerate('₀₁₂₃₄₅₆₇₈₉')}, '\u2010': '-', '\u2011': '-'})
def norm_head(h):
    h = (h or '').translate(_SUB)
    if ' ' not in h.strip() and re.search(r'[-_]', h):
        h = re.sub(r'[-_]+', ' ', h)
    return re.sub(r'\s+', ' ', h).strip()

_HOLLOW = re.compile(
    r"(?i)^\W*(?:"
    r"(?:news|press|media)\s*(?:release|advisory)?(?:\s*(?:no\.?|#)?\s*[\d\-/]+)?|nr\s*[\d\-]*|release|news|"
    r"for\s+immediate\s+release|"
    r"(?:trading\s+symbols?|symbol)\s*:.*|"
    r"(?:not\s+for\s+(?:distribution|dissemination|release)|or\s+for\s+dissemination|neither\s+(?:the\s+)?tsx|"
    r"this\s+news\s+release|failure\s+to\s+comply|of\s+america\s+or|or\s+through\s+u\.?s\.?).*|"
    r"(?:tsx|tsxv|tsx-v|cse|otcqb|otcqx|fse|frankfurt)[\s:\-\.A-Z]*"
    r")\W*$"
)
_VERBISH = re.compile(r"(?i)\b(?:announc\w+|reports?|closes?|complet\w+|intersect\w*|drills?|appoint\w*|provides?|receives?|signs?|enters?|acquir\w+|"
                      r"commenc\w+|launch\w+|files?|grants?|updates?|confirms?|expands?|identif\w+|begins?|secures?|extends?|results?|"
                      r"private\s+placement|financing|agreement|program|option|update)\b")
_BAD_LINE = re.compile(r"(?i)(?:^\W*(?:news\s*release|press\s*release)\W*$|not\s+for\s+(?:distribution|dissemination)|dissemination\s+in\s+the|"
                       r"united\s+states|suite\s+\d|\bstreet\b|\bavenue\b|www\.|@|tel\b|phone|fax|page\s+\d|^\W*\d{1,2}[,/ ]|"
                       r"^(?:january|february|march|april|may|june|july|august|september|october|november|december)\b|"
                       r"trading\s+symbol|tsx\s*venture\s*exchange\s*:|^\W*(?:tsx|cse|otc)\w*\s*[:\-])")
_PROSE = re.compile(r"(?i)\bpleased\s+to\b|\bannounced\s+today\b|[\u201c\x22]\s*(?:company|corporation)|\(the\s|\bis\s+(?:a|an)\s|\bwe\s|\bour\s")
def recover_headline(body):
    lines = [l.strip() for l in (body or '')[:1500].split('\n')]
    lines = [l for l in lines if l]
    for i, l in enumerate(lines[:14]):
        if len(l) < 20 or len(l) > 220 or _BAD_LINE.search(l): continue
        if len(l.split()) < 4 or not _VERBISH.search(l): continue
        if _PROSE.search(l) or re.match(r"[a-z(\u201c\x22]", l) or re.search(r"(?i)\bthe\s+company\b", l): continue
        # a wrapped title continues on the next line when this one has no terminal punctuation
        if i + 1 < len(lines) and not re.search(r"[.!?:]$", l) and len(l) < 120:
            nxt = lines[i+1]
            if 3 <= len(nxt.split()) <= 14 and not _BAD_LINE.search(nxt) and not re.search(r"(?i)\b(?:is\s+pleased|announced\s+today|\(the|“)", nxt):
                l = l + ' ' + nxt
        return l
    return None

def is_hollow(h):
    h = (h or '').strip()
    return (not h) or (bool(_HOLLOW.match(h)) and not _VERBISH.search(h))

def _DISC_NAME_HIT(h, m):
    return 'discover' in m.group(0).lower() and any(d.start() <= m.start() + 40 and d.end() >= m.start() for d in _DISCOVERY_NAME.finditer(h))

_PURPOSE = re.compile(r"(?i)(?:ahead\s+of|to\s+fund|to\s+support|to\s+finance|in\s+preparation\s+for|proceeds|in\s+support\s+of|to\s+advance|for\s+(?:the|its|a|an|upcoming))\s+(?:[\w\-]+\s+){0,3}$")
_TR_EVIDENCE = re.compile(r"(?i)\b(?:resources?|MRE|reserves?)\b")
_TR_LEDE = re.compile(r"(?i)\b(?:mineral\s+resource|resource\s+estimate|MRE)\b")
ECON_DELIVERED_V7 = re.compile(r"(?i)\bpositive\s+preliminary\s+economic|\bscoping\s+study\s+(?:results|outlines|demonstrates|confirms|shows)|\bresults\s+of\s+(?:the\s+|its\s+)?scoping")

def categorize_v7(headline, body, trace=None):
    h0 = norm_head(headline)
    if is_hollow(h0):
        rec = recover_headline(body)
        if rec:
            a, _ = _categorize_v7(h0, body, trace)
            bb, _ = _categorize_v7(norm_head(rec), body, trace)
            u = [c for c in a if c != 'Corporate Updates'] + [c for c in bb if c != 'Corporate Updates' and c not in a]
            if not u: u = ['Corporate Updates'] if FALLBACK_TO_CORPORATE else []
            order = {c: i for i, c in enumerate(CATEGORIES)}
            return sorted(u, key=lambda c: order.get(c, 99)), rec
    return _categorize_v7(h0, body, trace)

def _categorize_v7(h, body, trace=None):
    recovered = None
    b = (body or '').strip()
    base = _categorize_v6(h, b)
    cats = [c for c in base if c != 'Corporate Updates']
    third = bool(_THIRD_PARTY.search(h))
    def add(cat, why):
        if cat not in cats:
            cats.append(cat)
            if trace is not None: trace.append((cat, why))
    m = FINL_V7.search(h) or FINL_V7B.search(h)
    if m and 'Economic Studies' not in cats and not FINL_V7_NOT.search(h) and not third: add('Financials', m.group(0))
    m = PROD_V7.search(h) or PROD_V7B.search(h) or PROD_V7C.search(h)
    if m and 'Economic Studies' not in cats and not PROD_V7_NOT.search(h) and not PROD_V7_OIL.search(h) and not third and not _OIL_GAS.search(h) and not _PROD_NOT.search(h): add('Production Results', m.group(0))
    m = MRE_V7.search(h) or MRE_V7B.search(h) or MRE_V7C.search(h)
    if m and not third and (_MRE_DELIVERED.search(h) or not _STUDY_PLAN.search(h)):
        g = m.group(0).lower()
        if MRE_V7_NOT.search(h):
            pass
        elif not re.search(r"technical\s+report|43[-\s]?101", g) or _TR_EVIDENCE.search(h) or _TR_LEDE.search(lede(b)):
            add('Resource Estimates', m.group(0))
    m = ECON_V7.search(h)
    if m and not third and (_STUDY_DELIVERED.search(h) or ECON_DELIVERED_V7.search(h) or not _STUDY_PLAN.search(h)): add('Economic Studies', m.group(0))
    m = DRILL_V7.search(h) or DRILL_V7B.search(h)
    if m and not (_DRILL_HISTORICAL.search(h) and not _DRILL_NEW_WORK.search(h)) and 'Resource Estimates' not in cats: add('Drill Results', m.group(0))
    if not ({'Drill Results', 'Resource Estimates', 'Economic Studies', 'Production Results'} & set(cats)) and not third:
        import itertools
        for m in itertools.chain(EXPLORATION_V7.finditer(h), EXPLORATION_V7B.finditer(h), EXPLORATION_V7C.finditer(h)):
            if _DISC_NAME_HIT(h, m): continue
            if re.search(r"(?i)\b(?:to\s+fund|to\s+finance|proceeds|placement|financing|offering)\b", m.group(0)): continue
            if re.search(r"(?i)\b(?:financing|placement|offering|to\s+fund|proceeds)\b", h[max(0, m.start()-40):m.start()]): continue
            if not _PURPOSE.search(h[max(0, m.start()-45):m.start()]):
                add('Exploration Programs', m.group(0)); break
    m = MA_V7.search(h) or MA_V7B.search(h) or MA_V7C.search(h)
    if m and not MA_V7_NOT.search(h) and not third: add('Mergers & Acquisitions', m.group(0))
    m = MGMT_V7.search(h) or MGMT_V7B.search(h) or MGMT_V7C.search(h)
    if m and not MGMT_V7_NOT.search(h) and not _MGMT_NOT.search(h): add('Management Changes', m.group(0))
    m = FIN_V7.search(h) or FIN_V7B.search(h) or FIN_V7C.search(h)
    if m and not FIN_V7_NOT.search(h): add('Financings', m.group(0))
    for rxs, cat in (((CAP_V7, CAP_V7C), 'Share Capital & Compensation'), ((LIST_V7, LIST_V7B, LIST_V7C), 'Listings & Exchange'),
                    ((MTG_V7, MTG_V7B, MTG_V7C), 'Shareholder Meetings'), ((ACT_V7, ACT_V7B, ACT_V7C), 'Corporate Actions'), ((JV_V7, JV_V7B, JV_V7C), 'Partnerships & JV'),
                    ((MET_V7, MET_V7B, MET_V7C), 'Metallurgy & Processing')):
        m = next((x for x in (rx.search(h) for rx in rxs) if x), None)
        if m: add(cat, m.group(0))
    m = PER_V7.search(h) or PER_V7B.search(h) or PER_V7C.search(h)
    if m and not third: add('Permits & Approvals', m.group(0))
    m = MKT_V7.search(h) or MKT_V7B.search(h) or MKT_V7C.search(h)
    if m and not MKT_V7_NOT.search(h): add('Marketing Announcement', m.group(0))
    if not cats:
        cats = ['Corporate Updates'] if FALLBACK_TO_CORPORATE else []
    order = {c: i for i, c in enumerate(CATEGORIES)}
    return sorted(cats, key=lambda c: order.get(c, 99)), recovered


# ===========================================================================
# v8 tags (2026-09-16): five tags carved out of Corporate Updates.
# Headline-scoped, additive. Measured on the CU-only corpus first:
#   Royalties & Streams ~142 · Property Options & Staking ~276 ·
#   Regulatory & Compliance ~208 · Technical Reports (NI 43-101) ~189 ·
#   Debt & Credit Facilities ~183
# Standing lesson applied: gaps inside a headline use [^\n], so they can
# cross a period, a percent sign and a curly quote.
# ===========================================================================

# --- Royalties & Streams ---------------------------------------------------
_ROYALTY_V8 = re.compile(
    r"\broyalt(?:y|ies)\b|\bNSRs?\b|\bnet\s+smelter\s+returns?\b|"
    r"\bgross\s+(?:revenue|overriding)\s+royalt|"
    r"\bstream(?:ing)?\s+(?:agreements?|deals?|transactions?|financing|"
    r"interests?|portfolio|facility|arrangements?|contracts?)\b|"
    r"\b(?:gold|silver|precious\s+metals?|copper|metals?|cobalt|nickel|"
    r"platinum|palladium)\s+streams?\b|"
    r"\bprecious\s+metals?\s+purchase\s+agreements?\b|\bPMPA\b",
    re.I,
)
# A royalty company named at the start of its own headline ("Noranda
# Royalties Engages...", "Royalties Inc. Reports Yearend Results") is a name,
# not a royalty. Stripped before matching; the name may not contain a verb,
# so "ATEX Reduces NSR Royalty" keeps its match.
_ROYALTY_VERBS_V8 = (
    r"announces?|provides?|reports?|completes?|closes?|acquires?|receives?|"
    r"enters?|signs?|sells?|adds?|expands?|highlights?|notes?|debuts?|"
    r"engages?|appoints?|files?|grants?|declares?|reduces?|purchases?|"
    r"agrees?|increases?|updates?|comments?|confirms?|welcomes?|launches?|"
    r"executes?|amends?|terminates?|creates?|buys?|secures?|exercises?|"
    r"converts?|restructures?|to|of|on|for|with|from|and|the|a|an"
)
_ROYALTY_NAME_V8 = re.compile(
    r"^\s*Royalt(?:y|ies)\s+(?:Corp(?:oration)?|Inc|Ltd|Limited)\b\.?|"
    r"^\s*(?:[^\s:]+:\s+)?"                       # "Market One: " prefix
    r"(?:(?!(?:" + _ROYALTY_VERBS_V8 + r")\b)[\w'’.&$()/,-]+\s+){1,4}?"
    r"(?:Gold\s+|Precious\s+Metals\s+)?Royalt(?:y|ies)\b"
    r"(?:\s+(?:&|and)\s+Streaming)?"
    r"(?:\s+(?:Corp(?:oration)?|Inc|Ltd|Limited|Co)\b\.?)?",
    re.I,
)
_ROYALTY_NOT_V8 = re.compile(
    r"\broyalty\s+(?:rates?|regime|tax(?:es)?|framework|bill|law|review)\b|"
    r"\bmining\s+royalt(?:y|ies)\s+(?:bill|law|act|regime)\b",
    re.I,
)


def _is_royalty(h: str) -> bool:
    if not h:
        return False
    stripped = _ROYALTY_NAME_V8.sub(" ", h, count=1)
    return bool(_ROYALTY_V8.search(stripped)) and not _ROYALTY_NOT_V8.search(h)


# --- Property Options & Staking -------------------------------------------
_OPTION_LAND_V8 = re.compile(
    r"\boption(?:s|ed)?\s+(?:and\s+[\w-]+\s+)?agreements?\b|"
    r"\bproperty\s+options?\b|"
    r"\boption\s+(?:to\s+(?:acquire|earn|purchase)\b|payments?\b|"
    r"terminations?\b|cancell?ations?\b|amendments?\b|extensions?\b)|"
    r"\boptions?\s+(?:its\s+|the\s+|an?\s+|\d+\s*%\s+)?[^\n]{0,60}?"
    r"\b(?:property|project|claims?|interest)\s[^\n]{0,40}?\bto\b|"
    r"\b(?:terminat\w*|cancel\w*|drops?|dropped|amend\w*|extend\w*)\s+"
    r"(?:of\s+)?(?:the\s+|its\s+|an?\s+)?(?:[\w'’-]+\s+){0,4}?option\b"
    r"(?!\s*(?:plan|grant|price|holders?)\b)|"
    r"\bearn(?:s|ed|ing)?[- ]in\b|"
    r"\bearn(?:s|ed)?\s+(?:an?\s+)?(?:additional\s+|further\s+|initial\s+|"
    r"first\s+|second\s+|full\s+)?(?:\d+(?:\.\d+)?\s*%\s+)?interest\b|"
    r"\bearns?\s+(?:a\s+)?(?:\d+(?:\.\d+)?\s*%)|"
    r"\bstak(?:ed|ing)\b|\bstakes\s+(?!in\b)(?:\w+\s+){0,3}?"
    r"(?:ground|claims?|land|property|projects?|hectares|licen[cs]es?|"
    r"tenements?|area|block)\b|"
    r"\bclaims?\s+(?:staking|acquisitions?|packages?|blocks?)\b|"
    r"\b(?:expands?|expanded|expanding|increases?|increased|consolidates?|"
    r"consolidated|doubles?|doubled|triples?|tripled|grows?|enlarges?|"
    r"adds?\s+to)\b[^\n]{0,50}?\b(?:land\s+(?:packages?|positions?|holdings?|"
    r"base|tenure)|claims?\s+(?:area|positions?|holdings?|packages?|blocks?)|"
    r"mineral\s+claims?|property\s+(?:size|area|footprint)|mineral\s+tenure)\b",
    re.I,
)
_OPTION_LAND_NOT_V8 = re.compile(
    r"\b(?:stock|share|incentive|employee)\s+options?\b|"
    r"\b(?:equity|strategic|ownership|minority|majority|controlling)\s+stakes?\b|"
    r"\b(?:crypto\w*|ETH|ethereum|solana|token|validator|proof[- ]of)\b",
    re.I,
)


def _is_option_land(h: str) -> bool:
    return bool(h) and bool(_OPTION_LAND_V8.search(h)) and not _OPTION_LAND_NOT_V8.search(h)


# --- Regulatory & Compliance ----------------------------------------------
_REGULATORY_V8 = re.compile(
    r"\bMCTO\b|\bcease\s+trade\s+orders?\b|"
    r"\bchange\s+(?:of|in)\s+(?:the\s+)?auditors?\b|"
    r"\bauditors?\s+(?:change|resignation|appointment|transition)\b|"
    r"\bas\s+(?:the\s+)?(?:company'?s\s+|new\s+|successor\s+)?auditors?\b|"
    r"\b(?:appointment|resignation)\s+of\s+(?:the\s+)?(?:new\s+)?auditors?\b|"
    r"\blate\s+filing\b|\bdelay\w*\s+(?:in\s+)?(?:the\s+)?filing\b|"
    r"\bfiling\s+delay\b|\bdefault\s+(?:status|announcement|report)\b|"
    r"\bbi-?weekly\s+(?:default\s+|MCTO\s+)?status\b|"
    r"\bfiling\s+relief\b|\bblanket\s+relief\b|"
    r"\bCSE\s+bulletin\b|\bForm\s+7\b|\bmonthly\s+progress\s+report\b|"
    r"\b(?:no|unaware\s+of\s+any|not\s+aware\s+of\s+any)\s+(?:undisclosed\s+)?"
    r"material\s+(?:change|developments?)\b|"
    r"\b(?:respond\w*|repl(?:y|ies))\s+to\s+(?:an?\s+|the\s+)?(?:OTC|IIROC|CIRO|"
    r"regulator|BCSC|OSC|recent\s+(?:promotional|market|trading|stock))|"
    r"\bOTC\s+Markets?\s+(?:Group\s+)?(?:request|inquiry|inquiries)\b|"
    r"\bpromotional\s+activit(?:y|ies)\b|\bunusual\s+(?:market|trading)\s+activity\b|"
    r"\bunsanctioned\s+(?:third[- ]party\s+)?promotion|"
    r"\bclarif(?:y|ies|ied|ication|ying)\b[^\n]{0,60}?\b(?:disclosure|"
    r"news\s+release|press\s+release|announcement)\b|"
    r"\b(?:correction|corrects|retraction|retracts)\b[^\n]{0,40}?"
    r"\b(?:news\s+release|press\s+release|disclosure)\b|"
    r"\b(?:Nasdaq|NYSE(?:\s+American)?)\b[^\n]{0,40}?\b(?:notification|notice|"
    r"deficiency|non-?compliance)\b|\bminimum\s+bid\s+price\b|"
    r"\bregains?\s+compliance\b|\bcontinued\s+listing\s+(?:standards?|requirements?)\b|"
    r"\brevocation\s+of\s+(?:the\s+)?(?:MCTO|management\s+cease|cease\s+trade)|"
    r"\bsecurities\s+commission\b[^\n]{0,40}?\b(?:order|settlement|hearing|"
    r"allegations?|decision)\b",
    re.I,
)


def _is_regulatory(h: str) -> bool:
    return bool(h) and bool(_REGULATORY_V8.search(h))


# --- Technical Reports (NI 43-101) ----------------------------------------
_TECH_REPORT_V8 = re.compile(
    r"\btechnical\s+reports?\b|"
    r"\b(?:NI|N\.I\.)\s*-?\s*43\s*-?\s*101\s+(?:technical\s+)?reports?\b|"
    r"\b43\s*-?\s*101\s+reports?\b|"
    r"\bS-?K\s*1300\s+(?:technical\s+report\s+summary|report)\b|"
    r"\bconsent\s+of\s+(?:the\s+)?qualified\s+persons?\b|"
    r"\btechnical\s+(?:report\s+)?disclosure\b",
    re.I,
)
# Commissioning a report is a plan, the same rule Resource Estimates follows.
_TECH_REPORT_PLAN_V8 = re.compile(
    r"\b(?:engag\w*|commission\w*|retain\w*|initiat\w*|commenc\w*|begins?|"
    r"start\w*|select\w*|hires?|contracts?|mandates?)\b[^\n]{0,80}?"
    r"\b(?:technical|43\s*-?\s*101)\s+(?:technical\s+)?report|"
    r"\b(?:to\s+prepare|preparation\s+of|towards?|in\s+support\s+of|"
    r"planned|upcoming|forthcoming)\b[^\n]{0,40}?\b(?:NI\s*43-?101|technical)"
    r"\s+(?:technical\s+)?(?:report|disclosure)",
    re.I,
)
_TECH_REPORT_DONE_V8 = re.compile(
    r"\b(?:files?|filed|filing|refil\w*|publish\w*|releases?|delivers?|"
    r"completes?|completion|receives?|amended|updated|voluntary|posts?)\b"
    r"[^\n]{0,60}?\btechnical\s+report|"
    r"\btechnical\s+report\b[^\n]{0,20}?\b(?:filed|completed|received)\b",
    re.I,
)


def _is_tech_report(h: str) -> bool:
    if not h or not _TECH_REPORT_V8.search(h):
        return False
    return bool(_TECH_REPORT_DONE_V8.search(h)) or not _TECH_REPORT_PLAN_V8.search(h)


# --- Debt & Credit Facilities ---------------------------------------------
_DEBT_V8 = re.compile(
    r"\bloans?\b|"
    r"\b(?:credit|debt|loan|revolving(?:\s+credit)?|prepayment|standby|"
    r"equipment\s+financing|term\s+debt|bridge|working\s+capital)\s+"
    r"facilit(?:y|ies)\b|"
    r"\bdebentures?\b|"
    r"\bconvertible\s+(?:senior\s+)?(?:notes?|bonds?)\b|"
    r"\b(?:senior|secured|unsecured|subordinated|promissory|exchangeable)\s+"
    r"(?:secured\s+|unsecured\s+|convertible\s+)?notes?\b|"
    r"\bbonds?\s+(?:offering|issue|issuance)\b|\bgreen\s+bonds?\b|"
    r"\bgold\s+prepay\w*\b|\bprepayment\s+(?:agreement|financing)\b|"
    r"\bproject\s+(?:debt|finance\s+facility)\b|"
    r"\bdebt\s+(?:financing|facilit(?:y|ies)|restructur\w*|refinanc\w*|"
    r"repayment|package|funding|instruments?)\b|"
    r"\brefinanc\w*\b|"
    r"\brepa(?:y|ys|id|ying|yment)\b[^\n]{0,40}?\b(?:loans?|debt|debentures?|"
    r"notes?|facilit(?:y|ies)|credit|lenders?)\b|"
    r"\bextend\w*\s+(?:the\s+)?maturit(?:y|ies)\b|\bmaturity\s+(?:date\s+)?extensions?\b",
    re.I,
)
_DEBT_NOT_V8 = re.compile(
    r"\bdebt\s+settlements?\b|\bshares?\s+for\s+debt\b|"
    r"\bsettle\w*\s+(?:of\s+)?(?:outstanding\s+)?(?:debt|indebtedness)\b|"
    r"\bin\s+settlement\s+of\b",
    re.I,
)


def _is_debt(h: str) -> bool:
    return bool(h) and bool(_DEBT_V8.search(h)) and not _DEBT_NOT_V8.search(h)


V8_TAGS = (
    ("Debt & Credit Facilities", _is_debt),
    ("Technical Reports (NI 43-101)", _is_tech_report),
    ("Royalties & Streams", _is_royalty),
    ("Property Options & Staking", _is_option_land),
    ("Regulatory & Compliance", _is_regulatory),
)


# A headline that is really the exchange disclaimer ("Neither TSX Venture
# Exchange nor its Regulation Services Provider...") carries the issuer's
# name but not the subject, so "Orogen Royalties" in it is not a royalty.
_DISCLAIMER_HEADLINE_V8 = re.compile(
    r"^\s*neither\s+(?:the\s+)?(?:TSX|CSE|Canadian\s+Securities|"
    r"Investment\s+Industry)", re.I)


def v8_tags(headline: str | None) -> list[str]:
    h = (headline or "").strip()
    if _DISCLAIMER_HEADLINE_V8.search(h):
        return []
    return [name for name, fn in V8_TAGS if fn(h)]


def add_v8_tags(cats: list[str], headline: str | None, recovered: str | None = None) -> list[str]:
    """v8: add the five tags from the headline (and a recovered title), then
    re-apply 'Corporate Updates is the bucket of last resort'."""
    tags = v8_tags(norm_head(headline))
    if recovered:
        tags += [t for t in v8_tags(norm_head(recovered)) if t not in tags]
    if not tags:
        return cats
    merged = set(cats) | set(tags)
    merged.discard("Corporate Updates")
    return [c for c in CATEGORIES if c in merged]


def categorize(headline: str | None, body: str | None) -> list[str]:
    """Return the categories this release belongs to, in CATEGORIES order (v8 = v7 + five tags)."""
    cats, _recovered = categorize_v7(headline, body)
    return add_v8_tags(cats, headline, _recovered)


def format_categories(cats: Iterable[str]) -> str:
    """Serialize categories to a pipe-delimited DB string."""
    return "|".join(c for c in cats if c)


def parse_categories(s: str | None) -> list[str]:
    """Parse a pipe-delimited DB string back to a list of category names."""
    if not s:
        return []
    return [x for x in s.split("|") if x]


# ===========================================================================
# Self-test. Almost every case is a REAL headline from the corpus that v2 got
# wrong, or one it got right that must not regress.
# ===========================================================================

# (headline, body, must_include, must_exclude)
SELF_TEST: list[tuple[str, str, list[str], list[str]]] = [
    # --- the flow-thru spelling bug ------------------------------------
    ("Antimony Resources Corp. Closes Flow Thru Financing", "",
     ["Financings"], []),
    ("Antimony Resources Corp. (ATMY) (K8J0) Closes Flow Thru Financing", "",
     ["Financings"], []),

    # --- M&A must stop eating financings and option grants --------------
    ("American Copper Development Corporation Grants Stock Options",
     "The Company has granted stock options. American Copper holds an option "
     "to acquire a 100% interest in the Lordsburg property.",
     ["Share Capital & Compensation"], ["Mergers & Acquisitions", "Financings"]),
    ("Alma Gold Closes Private Placement",
     "Alma Gold Corp. announces it has closed its private placement. The "
     "Company retains an option to acquire the remaining 20% interest.",
     ["Financings"], ["Mergers & Acquisitions"]),
    ("Advanced Gold Upsizes Private Placement",
     "Advanced Gold has upsized its non-brokered private placement.",
     ["Financings"], ["Mergers & Acquisitions"]),
    ("Advanced Gold Exploration Retains Market Maker Services",
     "The Company has retained market maker services. It may acquire "
     "additional claims in due course.",
     [], ["Mergers & Acquisitions"]),
    ("ATERRA Metals Announces $3 Million Private Placement", "",
     ["Financings"], ["Mergers & Acquisitions"]),
    # ...but a real acquisition is still M&A, from the headline or the lede
    ("Discovery Energy Metals to Acquire 100% of Crystal Lake Copper Property",
     "", ["Mergers & Acquisitions"], []),
    ("Northern Star Announces Corporate Milestone",
     "Northern Star Resources announces it has entered into a definitive "
     "agreement to acquire all of the issued shares of Southern Cross Ltd.",
     ["Mergers & Acquisitions"], []),

    # --- drill programs are not drill results ---------------------------
    ("Cascada Mobilizes for Phase II Angie Diamond Drill Program", "",
     ["Exploration Programs"], ["Drill Results", "Financings"]),
    ("American Copper Initiates a 5,000m Drill Program at its Flagship Lordsburg Project",
     "", ["Exploration Programs"], ["Drill Results", "Marketing Announcement"]),
    ("Anteros Metals Commences Drilling at Seagull Critical Minerals Project", "",
     ["Exploration Programs"], ["Drill Results"]),
    ("Appia Completes SPARTAN MT Survey at its Otherside Uranium Property", "",
     ["Corporate Updates"], ["Drill Results"]),
    ("Emperor Metals Mobilizes Drill Rig to Advance Duquesne West Exploration",
     "", ["Exploration Programs"], ["Drill Results"]),
    # ...but real results are
    ("Acme Gold Intersects 12.5 m grading 4.30 g/t Au at the Bell Zone", "",
     ["Drill Results"], []),
    ("Bravo Minerals Reports Drill Results from the Luanga Project", "",
     ["Drill Results"], []),
    ("Charlie Resources Announces Assay Results from Hole CR-26-014", "",
     ["Drill Results"], []),
    ("Carlyle Drills 0.75 g/t Au Over 39m at Newton Gold & Silver Project", "",
     ["Drill Results"], []),

    # --- economic studies: plans are not studies ------------------------
    ("ESGOLD Engages BBA Engineering to Conduct a Preliminary Economic Assessment at Montauban",
     "", [], ["Economic Studies"]),
    ("Fox River Commences Preliminary Economic Assessment on Martison Phosphate Project",
     "", [], ["Economic Studies"]),
    ("ESGold Nearing Completion of the Montauban Preliminary Economic Assessment",
     "", [], ["Economic Studies"]),
    ("Lion Copper and Gold Provides a Pre-Feasibility Study Update", "",
     [], ["Economic Studies"]),
    ("Surge Battery Metals Announces 2026 Drill Program to Accelerate Nevada North Bankable Feasibility Study",
     "", [], ["Economic Studies"]),
    ("POWR Lithium Congratulates American Lithium's Increased Resource Estimate and Positive PEA",
     "", [], ["Economic Studies", "Resource Estimates"]),
    # ...but a delivered study is
    ("Fox River Announces Positive PEA for Martison Phosphate Project with After-tax NPV8% of USD$2.5B",
     "", ["Economic Studies"], []),
    ("Torex Gold Releases Results of Los Reyes Preliminary Economic Assessment",
     "", ["Economic Studies"], []),
    ("Getchell Gold Corp. Files Robust Preliminary Economic Assessment Fondaway Canyon Gold Project",
     "", ["Economic Studies"], []),
    ("AbraSilver Files Definitive Feasibility Study Technical Report & Provides Heap Leach PEA Update",
     "", ["Economic Studies"], []),

    # --- resource estimates: same guard ---------------------------------
    ("Emperor Commences Maiden Mineral Resource Estimate for Duquesne West Gold Project",
     "", [], ["Resource Estimates"]),
    ("Cruz Battery Metals Engages Stantec for Maiden Resource Estimate and Technical Report",
     "", [], ["Resource Estimates"]),
    ("Pan American Energy Initiates Work Toward Mineral Resource Estimate for the Big Mack Project",
     "", [], ["Resource Estimates"]),
    ("Star Copper Congratulates Doubleview Gold's Mineral Resource Estimate",
     "", [], ["Resource Estimates"]),
    ("Star Copper Fully Funded 15,000 Metre Drill Program Targets Maiden Resource in 2026",
     "", [], ["Resource Estimates"]),
    ("Class 1 Nickel Files Updated NI 43-101 Mineral Resource Estimate for Dundonald North",
     "", ["Resource Estimates"], []),
    ("Canadian Copper Significantly Grows Mineral Resources at Chester Project",
     "", ["Resource Estimates"], []),

    # --- production results: not oil, not an MOU, not a plan ------------
    ("Wedgemount Announces Further Gains in Permian Basin Oil Production Update",
     "", [], ["Production Results"]),
    ("First Phosphate and Ultion Technologies Enter MOU for Purchase of LFP / LFMP Commercial Production Technology",
     "", [], ["Production Results"]),
    ("LaFleur Minerals Progressing Towards Gold Pour at Beacon Gold Mill", "",
     [], ["Production Results"]),
    ("LithiumBank Advances Boardwalk Toward Commercial Production with SLB", "",
     [], ["Production Results"]),
    ("Torex Gold Reports Q1 2026 Production Results", "",
     ["Production Results"], []),
    ("BLUE LAGOON ATTAINS COMMERCIAL PRODUCTION", "",
     ["Production Results"], []),

    # --- financials: 'reports results' needs a period qualifier ---------
    ("Global Uranium Corp. Reports Results of Airborne ZTEM Survey at Astro Project",
     "", [], ["Financials"]),
    ("International Lithium Corp. Reports Results of 2025 Annual General Meeting",
     "", [], ["Financials"]),
    ("Rise Gold Reports Result of Vested Rights Hearing", "", [], ["Financials"]),
    ("Sasquatch Resources Reports Results from 528 kg Sorting Test of Waste-Rock at Mount Sicker",
     "", [], ["Financials"]),
    ("Americas Gold and Silver Provides Notice of First Quarter 2026 Results and Conference Call",
     "", [], ["Financials"]),
    ("Lithium Argentina to Release First Quarter 2026 Results on May 12, 2026",
     "", [], ["Financials"]),
    ("Pasinex Announces Q4 2025 Financial Results", "", ["Financials"], []),
    ("First Quantum Minerals Reports First Quarter 2026 Results", "",
     ["Financials"], []),
    ("SOMA GOLD REPORTS 2025 YEAR-END FINANCIAL RESULTS", "",
     ["Financials"], []),

    # --- marketing: conference attendance yes, footers no ---------------
    ("Athena Gold To Participate At PDAC 2026", "",
     ["Marketing Announcement"], []),
    ("Lima Resources Reports Drill Results from the Quartz Zone",
     "Lima intersected 8.0 metres grading 3.10 g/t gold. Visit us at booth "
     "#212 at the upcoming conference in Vancouver.",
     ["Drill Results"], ["Marketing Announcement"]),
    ("Alma Gold Engages Investing News Network", "",
     ["Marketing Announcement"], []),

    # --- management changes still delegate ------------------------------
    ("Anteros Metals Announces Appointment of Abraham Drost as Executive Chairman",
     "", ["Management Changes"], ["Drill Results", "Mergers & Acquisitions"]),
    ("Ameriwest Lithium Announces Appointments of Chief Financial Officer", "",
     ["Management Changes"], ["Financings"]),

    # --- boilerplate must not categorise --------------------------------
    ("Mike Minerals Announces Share Consolidation",
     "Mike Minerals announces a share consolidation. FORWARD-LOOKING "
     "STATEMENTS: this release contains statements about the Company's "
     "intention to acquire additional claims, complete a private placement, "
     "and commence a drill program at the Foo project.",
     ["Corporate Actions"],
     ["Mergers & Acquisitions", "Financings", "Drill Results"]),
    ("Athena Gold Announces Share Consolidation", "",
     ["Corporate Actions"], ["Mergers & Acquisitions", "Drill Results"]),
    ("Cascada Announces Grant of Options", "",
     ["Share Capital & Compensation"], ["Mergers & Acquisitions", "Drill Results"]),

    # ===== v3b: the regressions the corpus diff found =====
    # 1. a veto must be scoped like the claim it vetoes
    ("Torex Gold Reports Q1 2026 Production Results",
     "Torex produced 224,000 ounces of gold. Costs are reported per barrel "
     "equivalent for comparison and the mill is on track to expand.",
     ["Production Results"], []),
    ("WESDOME ANNOUNCES SECOND QUARTER 2026 PRODUCTION RESULTS; ON TRACK TO "
     "ACHIEVE FULL-YEAR CONSOLIDATED GUIDANCE", "",
     ["Production Results"], []),
    # ...the genuine oil and MOU cases still stay out
    ("Wedgemount Announces Permian Basin Oil Production Update", "",
     [], ["Production Results"]),
    ("First Phosphate and Ultion Technologies Enter MOU for Purchase of LFP "
     "Commercial Production Technology", "", [], ["Production Results"]),

    # 2 + 3. optioning a property out is M&A; joining a board is not
    ("Pacific Ridge Options Yukon Gold Projects to Labrador Gold", "",
     ["Mergers & Acquisitions"], []),
    ("Philip Birch Joins the Oregen Strategic Advisory Board",
     "Oregen Energy Corp. announces the appointment of Philip Birch to its "
     "strategic advisory board, and provides an update on the option "
     "agreement covering its Namibian licences.",
     ["Management Changes"], ["Mergers & Acquisitions"]),

    # 4. a company called Sun Summit is not a conference
    ("Sun Summit Minerals Commences Fieldwork at the Orbit Copper-Gold "
     "Project, Toodoggone Mining District", "",
     ["Exploration Programs"], ["Marketing Announcement"]),
    ("Norsemont Mining to Host Webinar", "",
     ["Marketing Announcement"], []),
    ("Avalon Advanced Materials to Participate in Sidoti's Micro-Cap Virtual "
     "Investor Conference", "", ["Marketing Announcement"], []),
    ("York Harbour Metals Engages Firm for Investor Relations Services in "
     "North America", "", ["Marketing Announcement"], []),

    # 5. 'Reports First Results' is not a quarterly
    ("Cambria Gold Reports First Results from Premier Underground Infill "
     "Drilling: Including 19.82 g/t Au over 3.1 m", "",
     ["Drill Results"], ["Financials"]),

    # 6. misses in the other direction
    ("foremost clean energy reports high grade gold results from first two "
     "holes of 2025 jean lake drill program", "", ["Drill Results"], []),
    ("RIVERSIDE RESOURCES COMPLETES FIRST FINANCING FOR RAVENA RESOURCES CORP.",
     "", ["Financings"], []),
    ("Emperor Metals Announces Filing of Technical Report in Support of Maiden "
     "Mineral Resource Estimate", "", ["Resource Estimates"], []),

    # ===== v3d: routine news that fell through to no category at all =====
    ("Alma Gold Closes Debt Settlement", "", ["Share Capital & Compensation"], []),
    ("Affinity Metals Corp. Announces Cancellation of Incentive Stock Options",
     "", ["Share Capital & Compensation"], []),
    ("Affinity Metals Corp. Announces Proposed Extension of Warrants", "",
     ["Share Capital & Compensation"], []),
    ("Appia Completes SPARTAN MT Survey at its Otherside Uranium Property", "",
     ["Corporate Updates"], ["Drill Results"]),
    ("American Copper Development Corporation Completes 134 line-km Titan 160 "
     "DCIP and MT Survey", "", ["Corporate Updates"], ["Drill Results"]),
    ("Anteros Metals Reports Drilling Update at Seagull Critical Minerals "
     "Project, Ontario", "", ["Corporate Updates"], ["Drill Results"]),
    ("Advanced Gold Exploration Retains Market Maker Services", "",
     ["Corporate Updates"], ["Mergers & Acquisitions"]),
    ("Cascada Announces Senior Leadership Changes", "",
     ["Corporate Updates"], []),
    ("Advanced Gold Incorporates US Sub to Hold Silver Belle", "",
     ["Corporate Updates"], []),
    ("Emperor Commences Maiden Mineral Resource Estimate for Duquesne West "
     "Gold Project", "", ["Corporate Updates"], ["Resource Estimates"]),
    ("Affinity Metals Completes Shares for Services Agreement", "",
     ["Share Capital & Compensation"], []),
    ("IIROC Trade Resumption - BLLG", "", ["Listings & Exchange"], []),

    # ===== v3d: the specific misses the diff showed =====
    ("Inflection Resources Drilling Intercepts New Zone of Alteration", "",
     ["Drill Results"], []),
    ("Patriot Gold's Bruner Project Acquires 20 Acre Patented Mining Claim",
     "", ["Mergers & Acquisitions"], []),
    ("SCOTCH CREEK INCREASES LAND PACKAGE TO OVER 10,000 ACRES", "",
     ["Mergers & Acquisitions"], []),
    ("Anteros Metals Enters Definitive Agreement", "",
     ["Mergers & Acquisitions"], []),
    ("Kuya Silver Announces Term Loan and Provides Corporate Update", "",
     ["Financings"], []),
    ("Apex Announces Filing of Final Base Shelf Prospectus", "",
     ["Financings"], []),
    ("Wedgemount Announces Warrant Exercise and Increased Cash Balance", "",
     ["Financings"], []),

    # ===== v3e: the fixed-gap defect, hunted everywhere it survives =====
    ("K2 Gold Drills Extensive Disseminated Mineralization and Gold-Silver "
     "Epithermal Quartz Veins", "", ["Drill Results"], []),
    ("York Harbour Metals Drills Massive Sulphides North and South of the "
     "Main Mine Zone", "", ["Drill Results"], []),
    ("Anteros Discovers High-Grade Copper-Gold-Silver in Untested Target Area",
     "", ["Drill Results"], []),
    ("Anteros Returns High-Grade Lead-Zinc-Silver in Surface Samples", "",
     ["Drill Results"], []),
    ("Inflection Resources Initial Drilling Returns Highly Encouraging Results",
     "", ["Drill Results"], []),
    ("Stinger Resources Announces Acquisition of Golden Triangle Mineral Claims",
     "", ["Mergers & Acquisitions"], []),
    ("Alma Gold Announces Acquisition of Exploration Licences in Dialakoro "
     "Region", "", ["Mergers & Acquisitions"], []),
    ("Cosa Resources Issues Deferred Payment Shares to Denison Mines", "",
     ["Share Capital & Compensation"], []),

    # ===== v3e: transaction types with no rule at all =====
    ("AUXICO ANNOUNCES JOINT VENTURE FOR A RARE EARTH PROPERTY", "",
     ["Mergers & Acquisitions"], []),
    ("Oakley Ventures Announces Exercise of Koster Dam Property Option", "",
     ["Mergers & Acquisitions"], []),
    ("Sorrento Resources Ltd. Announces Purchase Agreement for Lord Baron "
     "Project", "", ["Mergers & Acquisitions"], []),
    ("Canadian Copper Completes Sale of Turgeon Project", "",
     ["Mergers & Acquisitions"], []),
    ("South Pacific Metals Announces Marketed Equity Offering Up to C$15 "
     "Million", "", ["Financings"], []),
    ("Maxus Mining Investors Exercise $1,105,952 CDN in Warrants", "",
     ["Financings"], []),

    # ===== v3e: and the false positive it created =====
    ("Directors of Canadian Gold Resources to Participate in Non-Brokered "
     "Private Placement", "",
     ["Financings"], ["Marketing Announcement"]),
    # ...while a real conference appearance still counts
    ("Athena Gold To Participate At PDAC 2026", "",
     ["Marketing Announcement"], []),

    # ===== v3f: the regressions v3e introduced =====
    ("Abitibi Metals Launches Large-Scale Phase 4 Drill Program Targeting Up "
     "to 40,000 Metres", "", ["Exploration Programs"], ["Drill Results"]),
    ("Newfoundland Discovery Commences Winter Drilling of up to 10,000 metres "
     "at the Chubb Lithium Project", "",
     ["Exploration Programs"], ["Drill Results"]),
    # ...the verb form still reports a result
    ("Apex Drills 4.02% REO over 23.7 m at the Cap Project", "",
     ["Drill Results"], []),
    ("AMAPA MINERALS ANNOUNCES PARTIAL EXERCISE OF OVER-ALLOTMENT OPTION", "",
     ["Financings"], ["Mergers & Acquisitions"]),
    ("Bonterra Announces Closing of Guaranteed Rights Offering", "",
     ["Financings"], []),
    ("Getchell Gold Corp. Announces Closing of Debenture Financing", "",
     ["Financings"], []),
    ("ACME Lithium Announces US$3 Million Funding Agreement with Lithium "
     "Royalty Corporation", "", ["Financings"], []),
    # ...and a genuine option exercise is still M&A
    ("Oakley Ventures Announces Exercise of Koster Dam Property Option", "",
     ["Mergers & Acquisitions"], []),
    # ===== v4: the eight new categories =====
    ("Anteros Metals Commences Drilling at Seagull Critical Minerals Project",
     "", ["Exploration Programs"], ["Drill Results"]),
    ("Cascada Mobilizes for Phase II Angie Diamond Drill Program", "",
     ["Exploration Programs"], ["Drill Results"]),
    ("Myriad Uranium Completes Large-Scale Radiometric and Magnetic "
     "Geophysical Survey", "", ["Exploration Programs"], []),
    # ...but a company whose NAME contains a verb is not a program
    ("Advanced Gold Exploration Retains Market Maker Services", "",
     [], ["Exploration Programs"]),
    ("Advanced Gold Copper, Gold, Silver VMS Drilling, Buck Lake, Ontario", "",
     [], ["Exploration Programs"]),

    ("Green River Gold Corp. Receives Drill Permit for 6000 Meters of Drilling",
     "", ["Permits & Approvals"], []),
    ("GLENSTAR MINERALS SUBMITS PERMIT APPLICATION FOR EXTENSIVE DRILL PROGRAM",
     "", ["Permits & Approvals"], []),

    ("Carlyle Recovers 80% Gold in Preliminary Newton Metallurgical Testing",
     "", ["Metallurgy & Processing"], []),
    ("Lithium Pilot Plant Commissioning Update and Processing Progress", "",
     ["Metallurgy & Processing"], []),

    ("American Copper Development Corporation Grants Stock Options", "",
     ["Share Capital & Compensation"], []),
    ("Alma Gold Closes Debt Settlement", "",
     ["Share Capital & Compensation"], []),
    ("Peloton Extends Warrants", "", ["Share Capital & Compensation"], []),
    ("Gold Strike Awards Options", "", ["Share Capital & Compensation"], []),
    # a financing that merely mentions warrants is NOT a share-capital event
    ("Alma Gold Announces Private Placement of Units Each Comprising One Share "
     "and One Warrant", "", ["Financings"], ["Share Capital & Compensation"]),

    ("Inflection Resources Commences Trading on the OTCQB", "",
     ["Listings & Exchange"], []),
    ("American Copper Receives DTC Eligibility for U.S Trading", "",
     ["Listings & Exchange"], []),
    ("SNOWLINE GOLD ANNOUNCES INCLUSION INTO THE GDXJ", "",
     ["Listings & Exchange"], []),

    ("Alma Gold Inc. Announces Results of Annual General and Special Meeting",
     "", ["Shareholder Meetings"], []),
    ("MAX POWER ANNOUNCES AGSM RESULTS AND APPOINTMENT OF NEW DIRECTOR", "",
     ["Shareholder Meetings", "Management Changes"], []),

    ("Athena Gold Announces Share Consolidation", "",
     ["Corporate Actions"], []),
    ("Exploits Changes Name to Epic Gold Corp.", "",
     ["Corporate Actions"], []),

    ("Cruz Battery Metals Enters into Joint Venture Agreement for Deep Basin "
     "Lithium Brine Exploration", "", ["Partnerships & JV"], []),
    ("Canadian Copper Signs Offtake Agreement and Credit Facility with Ocean "
     "Partners", "", ["Partnerships & JV"], []),

    # ===== v4: recall gaps the residual exposed in EXISTING categories =====
    ("Advanced Gold Acquires 100% Interest in Silver Belle Nevada CRD Claims",
     "", ["Mergers & Acquisitions"], []),
    ("CARLYLE ACQUIRES OWL LAKE RESOURCES CORP. BECOMING ONE OF THE LARGEST "
     "CONTIGUOUS LANDHOLDERS", "", ["Mergers & Acquisitions"], []),
    ("Fox River Completes Arrangement with Avenir Minerals Limited", "",
     ["Mergers & Acquisitions"], []),
    ("Pacific Booker Minerals Inc. Confirms Termination of Unsolicited "
     "Take-Over Bid", "", ["Mergers & Acquisitions"], []),
    ("MANNING VENTURES SAMPLES UP TO 4.77% Cu AT THE COPPER HILL PROJECT", "",
     ["Drill Results"], []),
    ("Beyond Minerals Provides Results for the Drill Program at the "
     "Fabie-eastchester Project", "", ["Drill Results"], []),
    ("Exploits: Visible Gold at Saddle Zone Extends Strike and Lateral "
     "Continuity", "", ["Drill Results"], []),
    ("SAGA Metals Reports Assays from R-0055 to R-0057", "",
     ["Drill Results"], []),
    # ===== v5: grades in the headline are results =====
    ("Live Energy Minerals Corp. Reports Initial Samples Returning up to 1907 "
     "ppm Lithium at McDermitt", "", ["Drill Results"], []),
    ("Vital Battery Metals Field Program Returns 9.5 ppm Gold, 4.84% Copper "
     "and 1.97% Zinc in Outcrop", "", ["Drill Results"], []),
    ("Green River Gold Corp. Achieves XRF Results Averaging 0.197% Nickel "
     "Beginning at Surface", "", ["Drill Results"], []),
    ("POWR Lithium Discovers up to 1,735 ppm Lithium in Maiden Drilling "
     "Campaign", "", ["Drill Results"], []),
    ("Spark's Maiden Drilling Delivers 78-Meters Rare Earth Intercept Grading "
     "2,430 ppm TREO", "", ["Drill Results"], []),
    ("Gander Gold Expands Golden Horseshoe Zone at Mount Peyton Project", "",
     ["Drill Results"], []),

    # ===== v5d: a percentage that is not a grade at all =====
    ("Lion Situated To Take Advantage Of The EV Boom Creating a 500% Increase "
     "In Graphite Demand", "", [], ["Drill Results"]),
    ("ESGold Reports over 90.9% Gold Recovery Using Dundee Sustainable "
     "Technologies Non-Cyanide Process", "",
     ["Metallurgy & Processing"], ["Drill Results"]),
    # ...while real grades still read
    ("Magna Mining Intersects 29.7% Copper Equivalent over 3.4 metres", "",
     ["Drill Results"], []),
    ("Rio Grande Resources Reports Gold up to 41.2 g/t and Silver up to 1,435 "
     "g/t at Its Winston Project", "", ["Drill Results"], []),

    # ===== v5: a percentage of a company is not a grade =====
    ("Red Canyon Outlines Drill Plans for Its 100% Owned Osiris Copper-Gold "
     "Project", "", ["Exploration Programs"], ["Drill Results"]),
    ("Headwater Gold Commences Drilling Its 100% Owned Mahogany Gold Project",
     "", ["Exploration Programs"], ["Drill Results"]),
    ("Golden Arrow Resources Announces US$25 Million Sale of 75% Owned Copper "
     "Assets at San Pietro", "", ["Mergers & Acquisitions"], ["Drill Results"]),
    ("Myriad Exercises Initial 50% Option on Copper Mountain", "",
     ["Mergers & Acquisitions"], ["Drill Results"]),
    ("Golden Spike Acquires 100% of Golden Horizon Exploration Corp.", "",
     ["Mergers & Acquisitions"], ["Drill Results"]),
    ("Pegmatite One Confirms 100% Interest in Golden Scheelite Tungsten "
     "Project, Humboldt County, Nevada", "", [], ["Drill Results"]),
    ("Myriad Uranium to Sell Red Basin Uranium Project for US$2.5 Million, "
     "Retain 10% Free Carried Interest", "", [], ["Drill Results"]),

    # ===== v5: historical numbers are not new results... =====
    ("Molten Metals Corp. Announces Results of West Gore Digitization, "
     "Including Historical Intersections", "", [], ["Drill Results"]),
    ("Maxus Mining Expands Hurley West Antimony Project to Cover Historic "
     "Stibnite Prospect with Historical Results up to 16.9% Sb", "",
     [], ["Drill Results"]),
    # ...but new work ON historic ground is
    ("Myriad Uranium's Drilling at Copper Mountain Continues to Validate "
     "Historic Drill Results", "", ["Drill Results"], []),
    ("Nova Pacific Drilling Confirms Significance of High-Grade Historical "
     "Trench Results", "", ["Drill Results"], []),
    ("Big Gold Announces Results from Infill Sampling of Historic Core, "
     "including 1.46 metres of 1.2 g/t gold", "", ["Drill Results"], []),

    # ===== v5: target definition is exploration, not results =====
    ("Gander Gold Identifies Multiple Gold Targets Across 25-Km-Long Trend at "
     "Gander North", "", ["Exploration Programs"], []),
    ("Goldrea's 3DIP Survey Identifies Second Porphyry Copper Target at "
     "Cannonball Property", "", ["Exploration Programs"], []),
    ("MANNING VENTURES OUTLINES 800-METER COPPER GEOCHEMICAL ZONE AT THE "
     "COPPER HILL PROJECT", "", ["Exploration Programs"], []),

    # ===== v5: "Discovery" in a company name is still not a discovery =====
    ("Exploits Discovery Announces Leadership Transition", "",
     [], ["Drill Results"]),
    ("Newfoundland Discovery Announces Change of Officer", "",
     [], ["Drill Results"]),
    ("Discovery Lithium Inc. Announces Name Change", "",
     ["Corporate Actions"], ["Drill Results"]),
]


# --- v6: expectations changed by decisions taken 2026-09-15 ---------------
# A survey and a drilling progress report are exploration work, not "nothing
# else fits". A leadership change with no named person is still a management
# change. These four were written when those cases had nowhere to go.
_V6_OVERRIDES = {
    "Appia Completes SPARTAN MT Survey at its Otherside Uranium Property":
        (["Exploration Programs"], ["Drill Results"]),
    "American Copper Development Corporation Completes 134 line-km Titan 160 "
    "DCIP and MT Survey":
        (["Exploration Programs"], ["Drill Results"]),
    "Anteros Metals Reports Drilling Update at Seagull Critical Minerals "
    "Project, Ontario":
        (["Exploration Programs"], ["Drill Results"]),
    "Cascada Announces Senior Leadership Changes":
        (["Management Changes"], []),
}
SELF_TEST = [
    ((h, b) + _V6_OVERRIDES[h]) if h in _V6_OVERRIDES else (h, b, mi, me)
    for (h, b, mi, me) in SELF_TEST
]

SELF_TEST += [
    # --- Corporate Actions had no dividend rule at all -------------------
    ("Centerra Gold Announces Quarterly Dividend of C$0.07 per Common Share",
     "", ["Corporate Actions"], []),
    ("Lundin Mining Announces Declaration of Regular Dividend", "",
     ["Corporate Actions"], []),
    ("LUNDIN GOLD DECLARES QUARTERLY DIVIDENDS OF US$1.08 PER SHARE", "",
     ["Corporate Actions"], []),
    ("Advanced Gold Announces Proposed Consolidation", "",
     ["Corporate Actions"], []),
    ("Silver Tiger Announces Normal Course Issuer Bid", "",
     ["Corporate Actions"], []),

    # --- Share Capital: "Option Grants" is the common noun order ---------
    ("Auric Minerals Corp. Announces Option Grants", "",
     ["Share Capital & Compensation"], []),
    ("Class 1 Nickel Announces Option Grant", "",
     ["Share Capital & Compensation"], []),
    ("Refined Energy Corp. Announces Option Grant to Advisory Board Members",
     "", ["Share Capital & Compensation"], []),

    # --- Listings: venue present, verb is a noun -------------------------
    ("KO Gold Announces Commencement of OTCQB Trading", "",
     ["Listings & Exchange"], []),
    ("OTC Markets Group Welcomes Tartisan Nickel Corp. to OTCQX", "",
     ["Listings & Exchange"], []),
    ("North Atlantic Titanium Corp commences trading under its new Canadian "
     "Stock Exchange ticker", "", ["Listings & Exchange"], []),

    # --- Management Changes with nobody named ----------------------------
    ("American Copper Development Corp. Announces Leadership Transition and "
     "Strategic Refocus", "", ["Management Changes"], []),
    ("Exploits Discovery Announces Leadership Transition", "",
     ["Management Changes"], ["Drill Results"]),
    ("Bayridge Forms Advisory Council and Appoints Timothy Henneberry as "
     "Inaugural Member", "", ["Management Changes"], []),
    ("Frontier Lithium Bolsters Executive Advisory Council to Drive Execution "
     "Readiness", "", ["Management Changes"], []),
    ("Goldsky appoints Carl Danielsson as Manager of Communications and "
     "Public Affairs", "", ["Management Changes"], []),
    # ...but hiring a service provider is not one
    ("Peloton Minerals Appoints New Auditor", "", [], ["Management Changes"]),
    ("Alma Gold Engages Investing News Network", "",
     ["Marketing Announcement"], ["Management Changes"]),
    ("Advanced Gold Exploration Retains Market Maker Services", "",
     [], ["Management Changes", "Exploration Programs"]),

    # --- M&A: the word boundary after "mineral", and the left curly quote -
    ("United Lithium Acquires Swedish Minerals AB Expanding Its Nordic "
     "Critical Minerals Platform", "", ["Mergers & Acquisitions"], []),
    ("Cruz Battery Metals Acquires the ‘South-Advocate Hydrogen "
     "Project’ in Nova Scotia", "", ["Mergers & Acquisitions"], []),
    ("Green River Gold Corp. Acquires Lithium Prospect in Central British "
     "Columbia", "", ["Mergers & Acquisitions"], []),

    # --- Exploration: surveys, sampling, progress ------------------------
    ("Bayridge Resources Commences Advanced Geophysical Re-interpretation at "
     "the Baker Lake Project", "", ["Exploration Programs"], []),
    ("Anteros Metals Provides Phase 1 Drilling Update at Seagull Critical "
     "Minerals Project", "", ["Exploration Programs"], ["Drill Results"]),
    ("Inflection Resources Provides Drilling Update From Northern New South "
     "Wales", "", ["Exploration Programs"], ["Drill Results"]),
    ("Athena Gold Provides Exploration Update From Nevada and Ontario", "",
     ["Exploration Programs"], []),
    ("QIMC Commences Hydrogen-Helium Soil Gas Sampling at Ville Marie", "",
     ["Exploration Programs"], []),
    ("Exploits Commences Optical Televiewer Downhole Survey at Bullseye "
     "Property", "", ["Exploration Programs"], []),
    # ...and a company name containing a verb is still not a program
    ("Advanced Gold Copper, Gold, Silver VMS Drilling, Buck Lake, Ontario",
     "", [], ["Exploration Programs"]),
]



SELF_TEST += [
    # --- v6b: a bulk sample is process work, not a soil survey -----------
    ("Honey Badger Silver Provides Bulk Sample Update at the PC Silver Mine",
     "", ["Metallurgy & Processing"], ["Exploration Programs"]),
    # --- v6b: an acquisition that already happened is not this release ---
    # "Announces <x> Program" is a known recall gap, deliberately left for the
    # next measured pass. What matters here is that a past acquisition
    # mentioned in passing does not make this release M&A.
    ("Big Gold Announces Spring Exploration Program for Newly Acquired Tabor "
     "Project in Shebandowan", "", [], ["Mergers & Acquisitions"]),
    ("FATHOM ANNOUNCES COMPLETION OF SURFACE PROGRAM AT THE RECENTLY ACQUIRED "
     "TREMBLAY-OLSON AREA CLAIMS", "", [], ["Mergers & Acquisitions"]),
    # ...while the present tense is still a transaction
    ("Mosaic Minerals Acquires 6,600 Hectares With Critical Minerals "
     "Potential in Nunavik", "", ["Mergers & Acquisitions"], []),
]


# --- v7: expectations changed by decisions -----------------------------------
# Justin, 2026-09-15: genuine earnings calls go to Financials, so a notice of
# quarterly results is Financials too. Market-maker engagements are paid
# capital-markets services and now sit with Marketing Announcement (flagged
# for Justin's review in the v7 write-up).
_V7_OVERRIDES = {
    "Americas Gold and Silver Provides Notice of First Quarter 2026 Results and Conference Call":
        (["Financials"], ["Production Results"]),
    "Lithium Argentina to Release First Quarter 2026 Results on May 12, 2026":
        (["Financials"], []),
    "Advanced Gold Exploration Retains Market Maker Services":
        (["Marketing Announcement"], ["Management Changes", "Exploration Programs", "Mergers & Acquisitions"]),
}
SELF_TEST = [
    ((h, b) + _V7_OVERRIDES[h]) if h in _V7_OVERRIDES else (h, b, mi, me)
    for (h, b, mi, me) in SELF_TEST
]

SELF_TEST += [
    # --- v7 recall: every one of these sat in Corporate Updates alone -------
    ("Eldorado Gold Reports Solid First Quarter 2025 Financial and Operational Results; Skouries Progressing to Plan",
     "", ["Financials"], ["Corporate Updates"]),
    ("Denison Reports Financial and Operational Results for Q2 2026", "", ["Financials"], []),
    ("LUCARA ANNOUNCES Q1 2025 RESULTS", "", ["Financials"], []),
    ("GALIANO GOLD PROVIDES NOTICE OF THIRD QUARTER 2025 RESULTS", "", ["Financials"], []),
    ("Jaguar Mining Inc. Reports First Quarter 2026 Operating Results", "", ["Production Results"], []),
    ("First Majestic Produces 7.9 Million AgEq Ounces in Q2 2025", "", ["Production Results"], []),
    ("B2Gold Announces Total Consolidated Gold Production for 2024 of 804,778 oz", "", ["Production Results"], []),
    ("NEVADA KING ANNOUNCES MORE THAN DOUBLING OF M&I RESOURCE AT ATLANTA TO 1,019,600 GOLD OUNCES", "",
     ["Resource Estimates"], []),
    ("Torex Gold Reports Year-End 2024 Reserves & Resources", "", ["Resource Estimates"], []),
    ("McFarlane Intersects 148.37 Grams per Tonne Gold Over 1.3 Metres", "", ["Drill Results"], []),
    ("First Drill Hole at St Anthony Gold Mine Reports Near Surface 11.9 grams per tonne over 8.4 metres", "",
     ["Drill Results"], []),
    ("HARFANG ANNOUNCES WINTER DIAMOND DRILL PROGRAM AT SKY LAKE, ONTARIO", "", ["Exploration Programs"], []),
    ("Greenridge Exploration Announces 2024 Work Program for its Weyman Copper Project", "",
     ["Exploration Programs"], []),
    ("VICTORY COMPLETES MAG SURVEY OF ITS TAHLO LAKE PROPERTY", "", ["Exploration Programs"], []),
    ("First Andes Delineates >1.2-km-Long Gold-in-Soil Anomaly, Santas Gloria Project, Peru", "",
     ["Exploration Programs"], []),
    ("Black Mammoth Metals Stakes 185 Claims at Quito NV", "", ["Mergers & Acquisitions"], []),
    ("Quimbaya Gold Expands Strategic Land Position at Tahami Project", "", ["Mergers & Acquisitions"], []),
    ("Nuclear Fuels Shareholders Approve Arrangement with Premier American Uranium", "",
     ["Mergers & Acquisitions", "Shareholder Meetings"], []),
    ("Canadian Critical Minerals Announces the Passing of Founder David W. Johnston", "",
     ["Management Changes"], []),
    ("Hertz Energy Announces Change of Chief Financial Officer", "", ["Management Changes"], []),
    ("Blackrock Silver Announces the Appointment of Bernard Poznanski and Susan Mathieu to the Board of Directors", "",
     ["Management Changes"], []),
    ("APPIA ANNOUNCES $478,640 FINAL CLOSING AND TOTAL PROCEEDS OF $1,299,165", "", ["Financings"], []),
    ("Cullinan Metals Announces Private Placements", "", ["Financings"], []),
    ("OUTCROP SILVER ANNOUNCES $20 MILLION PUBLIC OFFERING", "", ["Financings"], []),
    ("Bunker Hill Announces Equity Compensation Grants", "", ["Share Capital & Compensation"], []),
    ("Max Resource Extends Expiry Date and Amends Price on Share Purchase Warrants", "",
     ["Share Capital & Compensation"], ["Mergers & Acquisitions"]),
    ("IIROC Trade Halt - Alba Minerals Ltd.", "", ["Listings & Exchange"], []),
    ("Waraba Gold Limited Unaware of Any Material Change", "", ["Listings & Exchange"], []),
    ("Happy Creek Announces Arrangements To Address Mailing of Shareholders Meeting Materials", "",
     ["Shareholder Meetings"], []),
    ("POWER NICKEL ANNOUNCES CHANGE OF NAME TO POWER METALLIC MINES INC.", "", ["Corporate Actions"], []),
    ("RAIN ENTERS INTO ARGENTINIAN LITHIUM JV OVER 150,000 HECTARES", "", ["Partnerships & JV"], []),
    ("Surge Receives Positive Record of Decision on its Exploration Plan of Operations Permit at the Nevada North Lithium Project",
     "", ["Permits & Approvals"], []),
    ("Chesapeake Gold Receives a U.S. Patent for Enhanced Metal Recovery from Sulphide Ores", "",
     ["Metallurgy & Processing"], []),
    ("Foremost Lithium to Attend H.C. Wainwright 26th Annual Global Investment Conference", "",
     ["Marketing Announcement"], []),
    ("Hybrid Power Solutions Inc. to Exhibit at Public Works and Defence Industry Conferences", "",
     ["Marketing Announcement"], []),
    # a hollow stored headline is read through the document's own title
    ("News release", "250 Southridge NW, Suite 300\nEdmonton, AB\nSankamap Announces $5.0M Private Placement\n"
     "Edmonton, Alberta - March 3, 2026 - Sankamap Metals Inc. proposes to complete a non-brokered private placement",
     ["Financings"], ["Corporate Updates"]),

    # --- v7 precision: each of these was a false positive while building ---
    ("GreenLight Metals Engages ICP Securities for Automated Market Making Services", "", [], ["Permits & Approvals"]),
    ("Nevada Organic Phosphate Appoints Garry Smith, P.Geo. Director", "", [], ["Production Results"]),
    ("Pan American Energy Announces The Commencement of Metallurgical Testing On Core Samples From The Horizon Lithium Project",
     "", [], ["Exploration Programs"]),
    ("Exploits Discovery Announces Leadership Transition", "", [], ["Exploration Programs"]),
    ("OceanaGold Provides Notice of Third Quarter 2025 Results and Conference Call", "", ["Financials"], ["Production Results"]),
    ("Blackrock Silver Announces Updated Preliminary Economic Assessment for Its Tonopah West Project; Production of 7.1 million ounces",
     "", ["Economic Studies"], ["Production Results"]),
    ("MAJESTIC GOLD CORP. REPORTS SUSPENSION OF DGZ MINE", "", [], ["Listings & Exchange"]),
    ("Japan Gold Announces Extension to Investment Agreement with OR Royalties for the Option to Purchase an Additional Net Smelter Return Royalty",
     "", [], ["Metallurgy & Processing"]),
    ("CCC Announces Proposed $25 Million Financing for Winter Drilling Program at Black Horse and Continuing Support for Commissioning of Muketi Airstrip",
     "", ["Financings"], ["Exploration Programs", "Metallurgy & Processing"]),
    ("Golden Rapture Mining Announces Expiry of 7,457,068 Share Purchase Warrants", "", [], ["Mergers & Acquisitions"]),
    ("Global Uranium Corp. Announces Marketing Program", "", ["Marketing Announcement"], ["Exploration Programs"]),
    ("Adelayde Announces Private Placement to Fund Gold Drill Program in Esmeralda County, Nevada", "",
     ["Financings"], ["Exploration Programs"]),
    ("Forge Resources Corp. Announces Executive Site Visit to La Estrella Coal Project", "", [], ["Management Changes"]),
    ("FREEMAN WELCOMES EXECUTIVE ORDER EMPOWERING DOMESTIC MINERAL PRODUCTION", "", [], ["Management Changes"]),
    ("Ivanhoe's mining crews have entered the orebody on the way to become the world's leading polymetallic producer", "",
     [], ["Corporate Actions"]),
    ("AC/DC Battery Metals Provides Annual General Meeting Results", "", ["Shareholder Meetings"], ["Financials"]),
    ("Trinity One Metals Identifies Historic High Grade Silver Intercepts at Silver-1 Including 2.60 m at 1,240 g/t Silver",
     "", [], ["Drill Results"]),
    ("ALBA REPORTS ON SUCCESSFUL INVESTMENT IN NORAM: NORAM EXTENDS ZEUS LITHIUM DEPOSIT", "", [], ["Financings"]),
    ("Northstar Expands Bryce Gold Property Acquires Historic Britcanna Mining Lease", "", [], ["Permits & Approvals"]),
    ("WESDOME ANNOUNCES AUTOMATIC SHARE PURCHASE PLAN", "", ["Corporate Actions"], ["Mergers & Acquisitions"]),
    # round 3: a company name that ends in "Mining" is not a mine starting up
    ("Collective Mining Commences Drilling at the San Antonio Project", "", ["Exploration Programs"], ["Production Results"]),
    ("GR Silver Mining Commences Trading on OTCQX", "", [], ["Production Results"]),
    ("Sierra Madre Commences Mining at Coloso, Expanding Mining Operations", "", ["Production Results"], []),
    ("Argyle Responds to OTC Markets Request on Recent Promotional Activity", "", ["Listings & Exchange"], []),
    ("Austral Gold Restarts Production at Casposo, Argentina", "", ["Production Results"], []),
    ("Lithium Argentina Announces $220 Million of New Debt Facilities Closed at Cauchari-Olaroz", "", ["Financings"], []),
    ("QUANTUM CRITICAL METALS REPORTS 150 METERS OF 38GPT GALLIUM, 694GPT RUBIDIUM", "", ["Drill Results"], []),
]

SELF_TEST += [
    # --- v8: five new tags (2026-09-16) ---------------------------------
    ('ATEX Reduces NSR Royalty on the Valeriano Project', "", ['Royalties & Streams'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Noranda Royalties Completes Compilation of Data ON Arctic Fox Lithium Corp.’S Kana Lake Lithium Property', "", [], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Royalties Inc. Reports Yearend Results for 2025', "", [], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Market One: Summit Royalties Expands Its Gold Royalty and Streaming Portfolio', "", ['Royalties & Streams'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Japan Gold Announces Sale of Royalty to Osisko Gold Royalties', "", ['Royalties & Streams'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('TNR Gold NSR Royalty Update - McEwen Provides Update on NSR Royalty on Los Azules Copper', "", ['Royalties & Streams'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Saskatchewan Government Sets Lithium Production Royalty Rate at 3%', "", [], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Delta Resources Options DELTA-2 Project in Québec to Troilus Mining Corp. - $8.25M and 1% NSR to Be Paid over 3 Years', "", ['Royalties & Streams', 'Property Options & Staking'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Regulatory & Compliance']),
    ('F4 Uranium Confirms Termination of Hearty Bay Option Agreement by Traction Uranium', "", ['Property Options & Staking'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Regulatory & Compliance']),
    ('Canada One Stakes New Ground at Copper Dome Project,', "", ['Property Options & Staking'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Regulatory & Compliance']),
    ('Getchell Gold Corp. Increases Fondaway Canyon Project Claim Area by 50%', "", ['Property Options & Staking'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Regulatory & Compliance']),
    ('Class 1 Nickel Announces Option Cancellation', "", ['Property Options & Staking'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Regulatory & Compliance']),
    ('American Copper Development Corporation Grants Stock Options', "", [], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Company Acquires Strategic Stake in Peer', "", [], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Spearmint Expands ETH Staking Program', "", [], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Sankamap Announces Revocation of MCTO', "", ['Regulatory & Compliance'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking']),
    ('Homeland Announces Change in Auditor', "", ['Regulatory & Compliance'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking']),
    ('Crest Announces Appointment of Mnp Llp, Chartered Accountants, as Auditor', "", ['Regulatory & Compliance'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking']),
    ('Gemdale Gold Unaware of Any Material Change', "", ['Regulatory & Compliance'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking']),
    ('Benjamin Hill Responds to OTC Markets Request Regarding Recent Unsanctioned Third-Party Promotional Activity', "", ['Regulatory & Compliance'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking']),
    ('Goliath Clarifies News Release Issued This Morning', "", ['Regulatory & Compliance'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking']),
    ('Largo Announces Receipt of Nasdaq Notification Regarding Minimum Bid Price Deficiency', "", ['Regulatory & Compliance'], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking']),
    ('XYZ Appoints Jane Doe as CTO', "", [], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Mithril Silver & Gold Announces Filing Of Technical Report', "", ['Technical Reports (NI 43-101)'], ['Debt & Credit Facilities', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Spearmint Engages Stantec for Resource Estimate and Technical Report on the Clayton Valley Lithium Clay Discovery', "", [], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Consent of qualified person (NI 43-101)', "", ['Technical Reports (NI 43-101)'], ['Debt & Credit Facilities', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Clarification to Technical Disclosure', "", ['Technical Reports (NI 43-101)', 'Regulatory & Compliance'], ['Debt & Credit Facilities', 'Royalties & Streams', 'Property Options & Staking']),
    ('Acme Announces Maiden NI 43-101 Mineral Resource Estimate', "", [], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Abcourt Closes US$8M Loan Facility to Start Sleeping Giant MINE', "", ['Debt & Credit Facilities'], ['Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Euromax Enters into Agreements to Extend Maturity Dates of Previously Issued Convertible Debentures', "", ['Debt & Credit Facilities'], ['Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Ivanhoe Mines prices an offering of US$750,000,000 Senior Notes due 2030', "", ['Debt & Credit Facilities'], ['Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Silver Pony Announces Communications Engagement and Debt Settlement', "", [], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Guanajuato Silver Takes Advantage of Favourable Pricing to Further Accelerate Gold Loan Repayment', "", ['Debt & Credit Facilities'], ['Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Lincoln Gold Receives Demand for Loan Repayment', "", ['Debt & Credit Facilities'], ['Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Battery X Metals Advances 2025 Critical Metals Exploration Strategy, Initiates NI 43-101 Report for Y Lithium Project', "", [], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Neither TSX Venture Exchange nor its Regulation Services Provider (as that term is defined in the policies of the TSX Venture Exchange) accepts responsibility Orogen Royalties Inc.', "", [], ['Debt & Credit Facilities', 'Technical Reports (NI 43-101)', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
    ('Surge Copper Files NI 43-101 Technical Report for the Berg PFS', "", ['Technical Reports (NI 43-101)'], ['Debt & Credit Facilities', 'Royalties & Streams', 'Property Options & Staking', 'Regulatory & Compliance']),
]


def self_test(verbose: bool = True) -> int:
    bad = 0
    # Wiring first. A category that delegates to an extractor it cannot import
    # fails open -- it just stops firing, with nothing in the logs. This is the
    # only check here that tests the environment rather than the rules.
    for _mod, _attr in (("management_extract", "extract"),
                        ("drill_extract", "extract")):
        _ok = bool(_get(_mod, _attr))
        bad += not _ok
        if verbose or not _ok:
            print(f"  {'ok  ' if _ok else 'FAIL'}  wiring: {_mod}.{_attr} resolved")
    for hl, bd, must, mustnt in SELF_TEST:
        got = categorize(hl, bd)
        miss = [c for c in must if c not in got]
        extra = [c for c in mustnt if c in got]
        ok = not miss and not extra
        bad += not ok
        if verbose or not ok:
            flag = "ok  " if ok else "FAIL"
            print(f"  {flag}  {hl[:70]}")
            if not ok:
                print(f"          got      : {got}")
                if miss:
                    print(f"          missing  : {miss}")
                if extra:
                    print(f"          unwanted : {extra}")
    total = len(SELF_TEST) + 2   # + the two wiring checks
    print(f"\n  {total - bad}/{total} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    import sys
    sys.exit(self_test())
