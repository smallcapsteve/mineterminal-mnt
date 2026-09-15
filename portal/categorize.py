"""News release categorizer (v3).

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
FALLBACK_TO_CORPORATE = False

# How much of the body counts as "the subject of the release".
LEDE_CHARS = 900

CATEGORIES: tuple[str, ...] = (
    "Financings",
    "Drill Results",
    "Resource Estimates",
    "Management Changes",
    "Economic Studies",
    "Production Results",
    "Financials",
    "Mergers & Acquisitions",
    "Exploration Programs",
    "Permits & Approvals",
    "Metallurgy & Processing",
    "Share Capital & Compensation",
    "Listings & Exchange",
    "Shareholder Meetings",
    "Corporate Actions",
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

def categorize(headline: str | None, body: str | None) -> list[str]:
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
    if _is_management_change(h):
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
    if (_MA_HEAD.search(h) or _MA_DECLARE.search(subj)) and not third_party:
        cats.append("Mergers & Acquisitions")

    # --- v4 categories: headline-scoped, additive -------------------------
    if _EXPLORATION.search(h):
        cats.append("Exploration Programs")
    if _PERMITS.search(h) and not third_party:
        cats.append("Permits & Approvals")
    if _METALLURGY.search(h):
        cats.append("Metallurgy & Processing")
    if _SHARE_CAPITAL.search(h):
        cats.append("Share Capital & Compensation")
    if _LISTINGS.search(h):
        cats.append("Listings & Exchange")
    if _MEETINGS.search(h):
        cats.append("Shareholder Meetings")
    if _CORP_ACTIONS.search(h):
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
