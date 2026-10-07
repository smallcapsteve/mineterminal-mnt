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
    "Mine Development & Operations",
    "Financials",
    "Mergers & Acquisitions",
    "Royalties & Streams",
    "Property Options & Staking",
    "Exploration Programs",
    "Sampling & Geoscience Results",
    "Permits & Approvals",
    "Metallurgy & Processing",
    "Share Capital & Compensation",
    "Listings & Exchange",
    "Shareholder Meetings",
    "Corporate Actions",
    "Regulatory & Compliance",
    "Legal & Disputes",
    "Partnerships & JV",
    "Shareholder Letters & Outlook",
    "Company Commentary",
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
    "dev": "Mine Development & Operations",
    "smp": "Sampling & Geoscience Results",
    "leg": "Legal & Disputes",
    "ltr": "Shareholder Letters & Outlook",
    "cmt": "Company Commentary",
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
# PERMIT_TAG_V1 (2026-09-22): Justin's tag fix, shipped with the /permits-approvals page. Exchange, shareholder,
# court and deal approvals are not permits (PER_V7_NOT vetoes them unless the headline also names a permit), and
# Notices of Intent / Notices of Work / named permits without a v7 verb come in (PER_V7D).
PER_V7_NOT = re.compile(
    r"(?i)\b(?:TSX(?:V|\s+Venture)?|CSE|NEO|Cboe|NYSE|NASDAQ|ASX|(?:stock\s+)?exchange|shareholders?|securityholders?|"
    r"court|final\s+order|interim\s+order|arrangement|amalgamation|merger|take-?over|acquisition|Investment\s+Canada|"
    r"Competition\s+(?:Act|Bureau)|antitrust|SAMR|listing|financing|private\s+placement|name\s+change|consolidation|"
    r"spin[\s-]?out|option\s+agreement|share\s+(?:purchase|exchange)|(?:qualifying\s+)?transaction|business\s+combination|"
    r"reverse\s+take-?over|conditional\s+approval|buy[\s-]?down|prospectus)\b")
PER_V7_PERMIT = re.compile(
    r"(?i)\b(?:permits?|licen[cs]es?|environmental|EIA|ESIA|EIS|plan\s+of\s+operations|notice\s+of\s+(?:work|intent)|"
    r"concessions?|mining\s+lease|drill(?:ing)?|water|land\s+access|record\s+of\s+decision|FAST-?41|impact\s+assessment)\b")
PER_V7D = re.compile(
    r"(?i)\bnotices?\s+of\s+intent\b(?!\s+to\s+(?:acquire|purchase|merge|enter|complete|sell|option|amalgamate|combine|"
    r"list|file|make))|\bnotice\s+of\s+work\b|\b(?:drill(?:ing)?|exploration|bulk[\s-]+sampl\w*|construction|operating)\s+"
    r"permits?\b|\bwork\s+authori[sz]ation\b")
# PERMIT_TAG_V1b (2026-09-22, Justin): buying, selling or optioning a licence is a deal, not a permit. A headline that
# acquires / sells / options / earns into licences, permits or concessions stays out of the tag unless it also reports
# a permit stage (received, granted, approved, submitted, renewed, a Notice of Intent, an environmental approval).
PER_V7_LICDEAL = re.compile(
    r"(?i)\b(?:acquir\w*|acquisition|purchas\w*|buys?|bought|sale\s+of|sells?|sold|divest\w*|option(?:s|ed)?\s+(?:to|on|agreement)|"
    r"earn(?:s|ed)?\s+(?:in(?:to)?\s+)?(?:an?\s+)?(?:\d+%|interest)|letter\s+of\s+intent|LOI|MOU|memorandum|term\s+sheet|"
    r"adds?\s+(?:\w+\s+){0,2}(?=(?:exploration|mining|mineral|prospecting)\s+licen))[^.]{0,70}?"
    r"\b(?:licen[cs]es?|permits?|concessions?|tenements?)\b|"
    r"\b(?:licen[cs]es?|permits?|concessions?)\s+(?:acquisition|sale|purchase)\b")
PER_V7_STAGE = re.compile(
    r"(?i)\b(?:rec(?:ei|ie)v\w*|granted|grant\s+of|approv\w*|issued|issuance|submit\w*|appl(?:y|ies|ied|ications?)|lodg\w*|"
    r"renew\w*|notices?\s+of\s+(?:intent|work)|plans?\s+of\s+operations|environmental|EIA|ESIA|drill(?:ing)?\s+permits?|FAST-?41)\b")
_PER_DEAL_APPROVAL = re.compile(r"(?i)\b(?:(?:rec(?:ei|ie)v\w*|obtain\w*|secur\w*|gains?|files?\s+for)\s+(?:its\s+|the\s+)?)?"
                                r"(?:TSX(?:V|\s+Venture)?|CSE|NEO|exchange|shareholders?|court|conditional|final|regulatory|"
                                r"antitrust)\s+(?:[\w\-]+\s+){0,2}?approvals?\b")


def _per_licence_deal(h):
    return bool(PER_V7_LICDEAL.search(h)) and not PER_V7_STAGE.search(_PER_DEAL_APPROVAL.sub(" ", h))


# Some stored headlines run on into the dateline and the issuer's tickers ("... Project Vancouver, BC -- Aben Gold Corp.
# (TSX-V: ABM)"); the vetoes read the headline proper only.
_PER_HEAD_END = re.compile(r"\((?:TSX|TSXV|TSX-V|TSX\.V|CSE|ASX|NYSE|NASDAQ|OTC\w*|NEO|Cboe|FSE)\b|\((?:VANCOUVER|TORONTO)\)|"
                           r"\b(?:VANCOUVER|TORONTO|CALGARY|MONTREAL|Vancouver|Toronto|Calgary|Montreal|Montréal|Halifax|"
                           r"Saskatoon|Perth|Reno|Denver|Cranbrook|Sudbury|Kelowna)\s*,\s")


def _per_head(h):
    m = _PER_HEAD_END.search(h or "")
    return h[:m.start()] if m and m.start() > 20 else h


def _per_not_permit(h):
    h = _per_head(h)
    return bool(PER_V7_NOT.search(h) and not PER_V7_PERMIT.search(h)) or _per_licence_deal(h)


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
    m = PER_V7.search(h) or PER_V7B.search(h) or PER_V7C.search(h) or PER_V7D.search(h)
    if m and not third and not _per_not_permit(h):
        add('Permits & Approvals', m.group(0))
    if 'Permits & Approvals' in cats and _per_not_permit(h):
        cats.remove('Permits & Approvals')   # PERMIT_TAG_V1: also when the v6 base rule added it
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


# OPT_TAG_V1 (2026-09-23): Justin's tag fix, shipped with the /property-options page. Adds headlines the v8 rule
# missed (about 660 in the stored corpus on 2026-09-23): "Options X Property" without "to", "Signs Option on",
# "Exercises ... Option", and buying claims / tenements / a property outright. Only adds; the v8 NOT rule still vetoes.
_OPTION_LAND_V9_CS = re.compile(
    r"\b(?:Options?|OPTIONS?|Optioned|OPTIONED)\s+(?:(?:[Ii]ts|ITS|[Tt]he|THE|[Aa]n?|AN?)\s+|\d{1,3}\s*%\s+(?:[Ii]nterest\s+)?"
    r"(?:[Ii]n\s+)?(?:[Tt]he\s+|[Ii]ts\s+)?)?(?:[A-Z0-9][\w'’.\-]*\s+){1,5}(?:[Pp]ropert(?:y|ies)|PROPERT(?:Y|IES)|"
    r"[Pp]rojects?|PROJECTS?|[Cc]laims?|CLAIMS?|[Tt]enements?|[Ll]icen[cs]es?|[Cc]oncessions?)\b")
_OPTION_LAND_V9 = re.compile(
    r"\b(?:signs?|signed|signing|enters?\s+into|entered\s+into|executes?|executed|grants?|granted)\s+(?:an?\s+|the\s+)?"
    r"(?:(?:definitive|binding|new|amended|property|earn-?in|purchase|mineral)\s+)*option\s+(?:on|for|over|to|with|"
    r"agreement)\b|"
    r"\bexercis(?:es|ed|ing|e\s+of)\s+(?:its\s+|the\s+|an?\s+|of\s+)?(?:[\w'’\-]+\s+){0,5}?option\b"
    r"(?!\s*(?:plan|grant|price|holders?)\b)|"
    r"\b(?:acquir(?:es|ed|ing|e)|acquisition\s+of|purchas(?:es|ed|ing|e)|buys?|bought)\s+"
    r"(?:(?:an?|the|its|\d{1,3}\s*%|100%|additional|new|strategic|contiguous|adjacent|key|two|three|four|five|several|"
    r"interest\s+in|of)\s+)*(?:[\w'’&.\-]+\s+){0,5}?(?:mineral\s+claims?|mining\s+claims?|claims?(?:\s+block)?|claim\s+blocks?|"
    r"tenements?|mineral\s+licen[cs]es?|exploration\s+licen[cs]es?|propert(?:y|ies)|projects?|land\s+package)\b",
    re.I)
_OPTION_LAND_V9_NOT = re.compile(
    r"\b(?:over[\s-]*allotment|greenshoe|agents?(?:['’]s?)?\s+option|underwriters?(?:['’]s?)?\s+option|royalt\w*|streams?\b|"
    r"offtake|NSR|shares\s+of|equity\s+interest\s+in|investment\s+in|drill\s+rig|equipment|mill\b|plant\b|cannabis|hemp|"
    r"oil\s+and\s+gas|petroleum|real\s+estate|data|technology\s+company|recycling|(?:recently|newly|previously)\s+acquired)",
    re.I)


def _is_option_land(h: str) -> bool:
    if not h:
        return False
    if _OPTION_LAND_NOT_V8.search(h):
        return False
    if _OPTION_LAND_V8.search(h):
        return True
    return bool(_OPTION_LAND_V9_CS.search(h) or _OPTION_LAND_V9.search(h)) and not _OPTION_LAND_V9_NOT.search(h)


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


# ===========================================================================
# v9 "rescue" rules (CU_RESCUE_V1, 2026-09-25). Justin: fix the releases that sit in
# Corporate Updates but should carry an existing tag. A random 300 of the 26,683
# Corporate-Updates-only releases read by hand: 35% belonged in an existing tag
# (Exploration Programs, Property Options & Staking, Management Changes and Drill
# Results most often). See claude/MNT_CORP_UPDATES_AUDIT_FINDINGS_2026-09-25.md.
#
# Headline-scoped like v8. RESCUE ONLY: these rules run only when everything
# before them left the release in Corporate Updates, so no release that already
# carries a real tag gains or loses anything. Adds existing tags only.
# Grade-less intersections go to Exploration Programs (Justin, 2026-09-15).
# ===========================================================================

R9_FUNDING = re.compile(r"(?i)\b(?:to\s+fund|to\s+finance|proceeds|private\s+placements?|financings?|offerings?|"
                        r"flow[-\s]?through|bought\s+deal|units?\s+at)\b")

R9_GRADE = re.compile(
    r"(?i)\b\d[\d.,]*\s*(?:g\s*/\s*t|gpt|g/tonne|grams?(?:\s+per\s+tonne|\s+gold|\s+/\s*t)?|%|ppm|oz\s*/\s*t|lbs?\s*/\s*t)"
    r"(?:\s*(?:" + _METAL + r"))?\b" + G(40) + r"\b(?:over|across|along|of|in)\s+\d[\d.,]*\s*(?:m\b|metres?|meters?|ft\b|feet)|"
    r"\b\d[\d.,]*\s*(?:m\b|metres?|meters?|ft\b|feet)\s+(?:of|at|grading|averaging|@)\s+\d[\d.,]*\s*(?:g\s*/\s*t|gpt|%|grams?|ppm|oz)|"
    r"\b(?:drill(?:s|ed|ing)?|intersects?|intercepts?)\s+\d[\d.,]*\s*(?:m\b|metres?|meters?)\s+(?:of|at|grading|averaging|@)\b|"
    r"\b(?:intercepts?|intersections?)\s+(?:of\s+)?(?:up\s+to\s+)?\d[\d.,]*\s*(?:%|g\s*/\s*t|gpt|ppm)")

R9_DRILL = re.compile(
    r"(?i)(?:"
    r"\b(?:results?|assays?)\s+(?:from|of|for|at)\s+(?:(?:the|its|first|initial|final|further|additional|remaining|new|latest|"
    r"phase|\d{4}(?:[-/]\d{2,4})?|winter|summer|fall|spring|maiden|inaugural|recent|ongoing|first-ever|step-out|infill|"
    r"diamond|RC|core|aircore|reverse\s+circulation|confirmation|follow-up|\d+(?:st|nd|rd|th)?|[IVX]+|one|two|three)\s+)*"
    r"(?:drill(?:ing|holes?)?|holes?|diamond\s+drilling|RC\s+drilling|core\s+drilling|drill\s+program|drilling\s+program)\b"
    r"(?!\s+(?:program\s+)?(?:plan|permit|contract|rig|targets?))|"
    r"\bdrill(?:ing)?\s+(?:hole\s+)?(?:assay\s+)?results\b(?!\s+(?:expected|pending|due))|"
    r"\bassays?\s+(?:results?\s+)?(?:from|for)\s+(?:holes?|drill)"
    r")")
R9_DRILL_NOT = re.compile(r"(?i)\b(?:historic(?:al)?\s+(?:drill|results|data)|pending|expected|awaits?|awaiting|to\s+release|"
                          r"will\s+release|schedule[ds]?)\b")

R9_EXPL = re.compile(
    r"(?i)(?:"
    r"\b(?:updates?|progress|reports?|news|details)\s+(?:on|of|regarding|for)\s+(?:(?:the|its|ongoing|current|continued|recent|"
    r"20\d\d|phase|summer|winter|fall|spring|first|second|next|[IVX]+|\d+)\s+)*(?:[\w'’\-]+\s+){0,3}?"
    r"(?:drill(?:ing)?|exploration|field\s*work|field\s+(?:program|season)|sampling|mapping|prospecting)\b(?!\s+results)|"
    r"\b(?:announces?|reports?|plans?|planned|begins?|beginning|starts?|commences?|continues?|resumes?|launch(?:es)?|"
    r"prepares?\s+for|preparing\s+for|kicks?\s+off|expands?|accelerates?|completes?)\s+"
    r"(?:(?:the|its|a|new|next|first|initial|further|additional|follow-up|maiden|inaugural|phase|[IVX]+|\d+|one|two|three|"
    r"\w+-hole|\w+-metre|\w+-meter|diamond|RC|core|winter|summer|fall|spring|20\d\d|second|seasonal|systematic|regional|"
    r"detailed|surface|ground|field)\s+)*"
    r"(?:drilling|drill\s+(?:program|campaign)|exploration\s+(?:program|work|campaign)|field\s*work|field\s+(?:program|season)|"
    r"sampling\s+program|mapping\s+program)\b|"
    r"\b(?:beginning|start|commencement|resumption|continuation|completion|next\s+phase|second\s+phase)\s+of\s+"
    r"(?:(?:the|its|a|new|phase|diamond|RC|core|\d[\d,]*\s*(?:m|metres?|meters?)|\w+)\s+){0,3}"
    r"(?:drilling|drill\s+program|exploration|field\s*work|sampling)\b|"
    r"\b(?:drilling|drill\s+program)\s+(?:advanc\w+|progress\w*|continues|underway|update|resumes|begins|"
    r"commences|at|on)\b|"
    r"\b(?:sets?|finali[sz]es?|selects?|prioriti[sz]es?|confirms?|announces?|refines?|ranks?)\b" + G(40) +
    r"\b(?:drill\s+targets?|target\s+areas?|drill[-\s]ready\s+targets?|exploration\s+targets?)\b|"
    r"\btargets?\s+(?:areas?\s+)?for\s+(?:drill(?:ing|\s+testing)?|follow-up)\b|\btargets?\s+advanced\b|"
    r"\b(?:advances?|advancing|refines?)\s+(?:[\w'’\-]+\s+){0,4}?(?:targets?|targeting)\b|"
    r"\bmobili[sz]\w*\s+(?:(?:the|its|a|field|exploration|drill|drilling|second)\s+)*(?:crews?|team|to\s+site|equipment|rigs?)\b|"
    r"\b(?:to|will)\s+(?:begin|commence|start|resume|conduct)\s+(?:(?:the|its|a|\w+)\s+){0,3}(?:drilling|exploration|"
    r"field\s*work|sampling)\b|\bto\s+sample\b|\breconnaissance\b|"
    r"\b(?:phase\s+(?:\d|I{1,3}V?|IV|one|two|three|four|five)|next\s+phase|second\s+phase)\s+(?:of\s+)?(?:exploration|"
    r"drilling|diamond\s+drilling|program|work)\b|"
    r"\b(?:intersects?|intersected|intercepts?|encounters?|encountered)\b|"
    r"\b(?:drilling|drill\s+program|drill\s+holes?)\s+(?:confirms?|extends?|expands?|hits?|delivers?|demonstrates?|"
    r"discovers?|returns?|traces?)\b|"
    r"\bcommences?\s+operations\s+on\s+(?:its\s+)?(?:[\w'’\-]+\s+){0,4}(?:project|property)\b|"
    r"\bcommencement\s+of\s+work\b|\bcommences?\s+work\b|\bcontinues?\s+work\s+(?:at|on)\b|\bdrill\s+tenders?\b|"
    r"\bdrills?\s+(?:large|wide|thick|broad|significant|multiple|extensive|long|deep|new)\b|"
    r"\bidentif\w+\s+(?:(?:a|new|additional|high[-\s]grade|gold|copper|silver|lithium|nickel|significant|multiple|two|three|several|further|another|\w+)\s+){0,3}(?:prospects?|potential|showings?|occurrences?)\b|"
    r"\breview\s+of\s+(?:the\s+)?historic\w*\b|\bhistoric(?:al)?\s+(?:drill\s+)?data\b|\bdata\s+(?:review|compilation)\b|"
    r"\badvances?\s+(?:[\w'’\-]+\s+){0,4}?(?:field\s*work|exploration|potential)\b|\b(?:rig\s+)?mobili[sz]ation\b|"
    r"\b(?:first|second|third|additional|new)\s+drill\s+rig\b|\bdrill\s+rigs?\s+(?:arriv\w+|on\s+site|turning)\b|"
    r"\bdrill\s+(?:contractor|phase)\b|\bdrilling\s+(?:ongoing|shows?|underway)\b|"
    r"\btargets?\s+(?:to\s+be\s+drilled|proposed|identified|defined|generated)\b|"
    r"\b(?:enhances?|bolsters?|generates?|develops?)\s+(?:(?:its|the|a)\s+)?(?:[\w\-]+\s+){0,3}?targets?\b|"
    r"\b(?:new|additional|priority|high[-\s]priority)\s+(?:[\w\-]+\s+){0,2}?targets?\b|"
    r"\bexploration\s+(?:work|strategy|activities|results?|season|update|plans?)\b|\bfocus\s+on\s+(?:[\w\-]+\s+){0,2}exploration\b|"
    r"\b(?:significant|extensive|new|additional|widespread|high[-\s]grade|massive|visible)\s+(?:[\w\-]+\s+){0,2}?mineraliz\w+|\bmineralis\w+|"
    r"\bresource\s+(?:expansion|growth)\s+potential\b|\b(?:plans?\s+to\s+)?commence\s+(?:exploration\s+)?operations\s+at\b|"
    r"\b(?:restart|resumption)\s+of\s+work\b"
    r")")
R9_EXPL_NOT = re.compile(r"(?i)\b(?:designed|planned|aim\w*|expected|intended)\s+to\s+(?:intersect|intercept)|"
                         r"\bmajor\s+drilling\b|\bdrilling\s+(?:company|services|contractor)\b|"
                         r"\bexploration\s+(?:inc|corp|ltd|limited|company)\b")

R9_OPT = re.compile(
    r"(?i)(?:"
    r"\bstakes?\s+(?!in\b|of\b|holders?\b|to\b)(?:(?:the|an?|additional|new|more|further|large|key|strategic|prospective|"
    r"extensive|significant|two|three|four|several)\b|\d)|"
    r"\bstaked\b|\bstaking\s+(?:of|at|in|on|program|campaign|additional|new|rush|claims?)\b|\bclaim\s+staking\b|"
    r"\b(?:adds?|added|acquires?|expands?|increases?|grows?|doubles?|triples?|consolidates?|secures?|enlarges?)\b" + G(40) +
    r"\b(?:land\s+(?:package|position|holdings?|base|footprint)|claim\s+blocks?|claims|ground|hectares|mineral\s+licen[cs]es?|"
    r"tenements?|concessions?|property\s+(?:package|position|portfolio)|(?:lithium|gold|copper|uranium|mineral|project|"
    r"exploration)\s+portfolio|additional\s+propert(?:y|ies)|land|structural\s+corridor|shear\s+zone)\b|"
    r"\b(?:extension|amendment|termination|renegotiation)\s+(?:of|to)\s+(?:the\s+|its\s+)?(?:[\w'’/\-]+\s+){0,4}?"
    r"(?:LOI|letter\s+of\s+intent|option(?:\s+agreement)?|property\s+(?:option\s+)?agreement|earn-?in(?:\s+agreement)?)\b|"
    r"\b(?:amends?|amended|amending|extends?|extended|terminates?|terminated|restructures?)\s+(?:the\s+|its\s+)?"
    r"(?:[\w'’/\-]+\s+){0,5}?(?:option|property|earn-?in|LOI|claims?)\s*(?:agreements?)?\b|"
    r"\bamends?\s+(?-i:(?:[A-Z][\w'’/\-]*\s+){1,5})(?:agreement|option)\b|"
    r"\breturns?\s+(?:of\s+)?(?:the\s+)?(?:[\w'’\-]+\s+){0,3}claims\b|\bdrops?\s+(?:the\s+)?(?:[\w'’\-]+\s+){0,3}"
    r"(?:claims|option)\b|\brelinquish\w*\b|"
    r"\bawarded\s+(?:the\s+|an?\s+)?(?:[\w'’,.\-]+\s+){0,6}?(?:project|property|licen[cs]es?|concessions?|tenements?|"
    r"exploration\s+(?:rights|licen\w+|permits?)|hectares|public\s+tender|tender|claims|blocks?)\b|"
    r"\bleases?\s+(?:its\s+|the\s+)?(?:[\w'’\-]+\s+){0,5}(?:concessions?|claims|property|properties)\b|"
    r"\b(?:option|earn-?in|property)\s+payments?\b|\bfinal\s+option\s+payment\b|"
    r"\bearn-?in\b(?!gs)|\bcarried\s+interest\b|\bproject\s+option\b|\bupdates?\s+on\s+" + G(40) + r"\boption\b|"
    r"\btermination\s+of\s+(?:the\s+)?(?:option|property|earn-?in)\s+agreement\b|"
    r"\bexpands?\s+(?:the\s+|its\s+)?(?:greater\s+)?(?-i:[A-Z][\w'’\-]*\s+){1,4}(?-i:[Pp]roperty|PROPERTY|[Pp]roject|PROJECT|[Cc]laims|CLAIMS)\b|"
    r"\b(?:NB)?LOI\b" + G(60) + r"\b(?:ha|hectares|land\s+package|claims|property|concessions?)\b|"
    r"\bletter\s+of\s+(?:intent|agreement)\b" + G(60) + r"\b(?:propert\w+|claims|land\s+package|hectares|concessions?|projects?)\b|"
    r"\boptions?\s+(?:the\s+)?(?:majority|\d{1,3}\s*%|its|an?\s+interest)\b" + G(60) + r"\b(?:package|propert\w+|projects?|claims)\b|"
    r"\b(?:purchase|assignment)\s+option\b|\bassignment\s+agreement\b|\bearn[-\s]+in\s+agreement\b|"
    r"\bleases?\s+(?:its\s+|the\s+)?(?:[\w'’\-]+\s+){0,4}mine\b|"
    r"\breduces?\s+(?:the\s+)?number\s+of\s+(?:[\w\-]+\s+)?(?:projects|properties|claims)\b|\bstrategic\s+foothold\b"
    r")")
R9_OPT_NOT = re.compile(r"(?i)\b(?:royalt\w*|streams?\b|over[\s-]*allotment|stock\s+options?|incentive|shares\s+of|"
                        r"equity\s+(?:interest|stake)|investment\s+in|stake\s+in|oil\s+and\s+gas|petroleum|cannabis|real\s+estate|"
                        r"crypto|token|validator|blockchain|mineraliz\w+|mineralis\w+|intercepts?|intersects?|drill\w*|resource|"
                        r"discovery|anomal\w+|conductors?|credit|loan|debenture|financing|offtake|employment|consulting|water\s+rights)\b|"
                        r"\bawarded\s+to\b")

R9_MGMT = re.compile(
    r"(?:"
    r"(?i:\b(?:board|management|executive|leadership|senior\s+management|officer|director)\s+(?:appointments?|changes?|"
    r"update|transition|restructur\w+|renewal)\b)|"
    r"(?i:\bchanges?\s+(?:to|in|of)\s+(?:the\s+|its\s+)?(?:board|management|executive|leadership|senior\s+management|"
    r"officers?|directors?)\b)|"
    r"(?i:\b(?:announces?|confirms?|makes?)\s+(?:(?:board|key|senior|new|several|two|three|director|directors?|executive|officer|"
    r"management)\s+)*appointments?\b)|"
    r"(?i:\bappoints?\s+(?:Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+|Dr\.?\s+)?)(?-i:[A-Z][a-z'’\-]+(?:\s+[A-Z]\.)?\s+[A-Z][A-Za-z'’\-]+)|"
    r"(?i:\b(?:hires?|hired|names?|named|welcomes?|adds?|elects?|elected|promotes?|promoted|selects?|selected)\b)" + G(60) +
    r"(?i:\b(?:as|to)\s+(?:its\s+|the\s+)?(?:new\s+|interim\s+|acting\s+)?(?:CEO|CFO|COO|CTO|President|Chair(?:man|person|woman)?|"
    r"Vice[-\s]President|VP|SVP|EVP|Chief\s+\w+\s+Officer|Corporate\s+Secretary|General\s+Manager|Exploration\s+Manager|"
    r"Directors?|Board)\b)|"
    r"(?i:\b(?:CEO|CFO|COO|President|Chair(?:man|person)?|Director|VP)\s+(?:resumes?|departs?|transition|to\s+step\s+down|"
    r"to\s+retire|leaves|assumes)\b)|"
    r"(?i:\b(?:strengthens?|bolsters?|expands?|builds?)\s+(?:out\s+)?(?:its\s+|the\s+)?(?:[\w,&'’\-]+\s+){0,5}team\b)|"
    r"(?i:\bannounces\s+)(?:Mr|Ms|Mrs|Dr)\.?\s+[A-Z]|"
    r"(?i:\b(?:resignation|retirement|departure)\s+of\s+(?:(?:its|the|a|an|two|three|new|independent|"
    r"non-executive|lead)\s+)*(?:CEO|CFO|COO|President|Chair\w*|Directors?|Board(?:\s+of\s+Directors)?|Officers?|VP|"
    r"Vice[-\s]President|founder|co-founder)\b)|"
    r"(?i:\baddition\s+of\s+(?:a\s+|two\s+|three\s+)?(?:new\s+)?(?:directors?|board\s+members?|independent\s+directors?)\b)|"
    r"(?i:\bnew\s+(?:CEO|CFO|COO|President|Chair\w*|Director|board\s+members?)\b)|"
    r"(?i:\bjoins?\s+(?:the\s+)?(?:board|management\s+team|leadership\s+team|executive\s+team)\b)|"
    r"(?i:\b(?:executive|management|leadership)\s+team\s+(?:update|changes?|expan\w+|additions?)\b)|"
    r"(?i:\bassumes?\s+(?:a\s+)?new\s+role\b)|(?i:\bupdate\s+to\s+(?:the\s+)?management\s+team\b)"
    r")")
R9_MGMT_NOT = re.compile(
    r"(?i)\b(?:auditors?|transfer\s+agent|market\s+mak\w+|investor\s+relations|IR\s+(?:firm|advisor|provider|consultant)|"
    r"marketing|communications|financial\s+advisors?|legal\s+counsel|contractors?|qualified\s+person|index|"
    r"executive\s+orders?|receivers?|trustees?|monitor|underwriters?|warrants?|options?|brokers?)\b|"
    r"\bappoints?\s+[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,4}\s+(?:Securities|Capital|Inc|Corp|Ltd|LLP|LLC|Group|Partners|"
    r"Consulting|Geoscience|Geosciences|Engineering|Associates|Services|Limited|Financial|Advisors|Agency|Media|Markets|"
    r"Geological|Mining|Drilling|Exploration)\b")

R9_MNA = re.compile(
    r"(?i)(?:"
    r"\b(?:completes?|completed|closes?|closed|closing\s+of|completion\s+of|finali[sz]es?|finali[sz]ation\s+of)\s+"
    r"(?:(?:the|its|previously|announced|proposed|successful|\w+)\s+){0,4}(?:acquisitions?|sale|disposition|disposal|divestiture|merger|"
    r"amalgamation|business\s+combination|arrangement|purchase|takeover)\b|"
    r"\b(?:terminat\w+|cancel\w*|abandon\w*|withdraw\w*)\s+(?:of\s+)?(?:(?:the|its|proposed|previously|announced)\s+){0,3}"
    r"(?:[\w'’\-]+\s+){0,3}?(?:acquisition|merger|arrangement|business\s+combination|takeover|transaction)\b|"
    r"\bcombine\b|\bcombination\s+(?:with|of)\b|\bmerger\s+of\s+equals\b|\bamalgamat\w+|"
    r"\bdue\s+diligence\b|"
    r"\b(?:to\s+create|creates?|forming|to\s+form)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:[\w\-]+\s+){0,5}(?:company|platform|producer|"
    r"developer|explorer|leader|champion)\b|"
    r"\bupdates?\s+(?:on\s+)?(?:the\s+)?(?:[\w'’\-]+\s+){0,3}?(?:acquisitions?|merger|transaction|arrangement)\b|"
    r"\btakeover\s+bid\b|\bunsolicited\s+(?:offer|proposal|bid)\b|\btender\s+offer\b|\bhostile\b|"
    r"\b(?:completes?|announces?)\s+(?:the\s+)?sale\s+of\b|\bdivestment\b|"
    r"\b(?:approval|approved)\s+(?:for|of)\s+(?:the\s+)?(?:proposed\s+)?transactions?\b|\bfiling\s+statement\b|\bstandstill\b|"
    r"\b(?:receives?|announces?)\s+approval\s+for\s+(?:the\s+)?transaction\b"
    r")")
R9_MNA_NOT = re.compile(r"(?i)\b(?:private\s+placement|placements?|financings?|offerings?|flow[-\s]?through|units?|debentures?|"
                        r"loans?|royalt\w*|streams?|shares?[-\s]for[-\s]debt|debt\s+settlement)\b|"
                        r"\bacqui\w+\s+(?:of\s+)?(?:[\w\-]+\s+){0,3}(?:data|equipment|drill\w*|core|samples|survey|rigs?)\b|"
                        r"\bsale\s+of\s+(?:[\w\-,]+\s+){0,4}(?:concentrate|ore|dor[eé]|ounces|oz|tonnes|t\b|fines|product|diamonds)")

R9_FIN = re.compile(
    r"(?i)(?:"
    r"\braises?\s+(?:gross\s+proceeds\s+of\s+)?(?:(?:C|CA|CAD|US|USD|A|AU|AUD)\s?)?[$£€]\s?\d|"
    r"\b(?:unit|units|equity|share|flow[-\s]?through|FT|hard[-\s]dollar|non[-\s]brokered|brokered)\s+financing\b|"
    r"\bfinancing\s+(?:update|closes?|closed|completed|tranche|increase[sd]?|upsized|amend\w*|terms)\b|"
    r"\bupdate\s+on\s+(?:the\s+|its\s+)?(?:[\w'’\-]+\s+){0,2}?(?:financing|private\s+placement|offering)\b|"
    r"\b(?:arranges?|announces?\s+and\s+arranges?)\s+(?:an?\s+)?(?:[$£€][\d.,]+\s+)?(?:[\w\-]+\s+){0,2}?(?:financing|placement)\b|"
    r"\bissue\s+of\s+" + G(40) + r"\b(?:CHESS\s+depository|placement)\b|"
    r"\bprivate\s+placement\b|\bequity\s+placement\b|"
    r"\b(?:increases?|increase\s+to|upsizes?|upsized|amends?|amended|amendment\s+to)\s+(?:the\s+|its\s+)?(?:previously\s+announced\s+)?(?:[\w\-]+\s+){0,2}?(?:offering|financing|placement)\b|"
    r"\b(?:arranges?|secures?|closes?|completes?)\s+(?:an?\s+)?(?:(?:US|C|CA|A|AU)?[$£€][\d.,]+\s*(?:million|m)?\s+)?(?:[\w\-]+\s+){0,2}?financing\b|"
    r"\b(?:security|share)\s+purchase\s+plan\b|\brights\s+(?:issue|offering)\b|\bentitlement\s+offer\b"
    r")")
R9_FIN_NOT = re.compile(r"(?i)\b(?:warrants?|options?|incentive\s+program|disposition|sale\s+of)\b")

R9_CAP = re.compile(
    r"(?i)(?:"
    r"\bwarrants?\s+(?:expir\w+|extension|extended|repric\w+|acceleration|accelerated|exercise[sd]?|incentive|amendment|"
    r"amended|conversion|terms|to\s+be\s+repriced)\b|\b(?:through|from|via)\s+(?:the\s+)?(?:exercise\s+of\s+)?(?:\w+\s+)?warrants?\b|"
    r"\bwarrants?\s+(?:and|&)\s+options?\b|\boptions?\s+(?:granted|grant|issued|awarded)\b|"
    r"\bgrants?\s+(?:of\s+)?(?:annual\s+)?(?:equity\s+incentives?|stock\s+options?|incentive\s+(?:stock\s+)?options?|options|RSUs?|"
    r"DSUs?|PSUs?|restricted\s+share\s+units?|deferred\s+share\s+units?|annual\s+incentives?)\b|"
    r"\bequity\s+(?:incentives?|issuances?)\b|\bshares?[-\s]for[-\s](?:debt|services)\b|\bdebt\s+settlements?\b|"
    r"\bsettlement\s+of\s+(?:debt|fees|directors?['’]?s?\s+fees|indebtedness|interest)\b|"
    r"\b(?:omnibus|equity\s+incentive|stock\s+option|share\s+unit|RSU|DSU)\s+plan\b|\bin\s+shares\b|\bshare\s+issuances?\b|"
    r"\bissues?\s+(?:[\w\-]+\s+){0,3}?shares\b|\bdebt\s+conversion\b|"
    r"\bgrants?\s+(?:[\w\-]+\s+){0,2}?incentive\s+awards?\b|\bgranting\s+of\s+(?:stock\s+)?options\b|\bgrant\s+of\s+(?:stock\s+)?options\b|"
    r"\bsettles?\s+(?:outstanding\s+)?(?:debt|indebtedness)\b|\bsalary\s+settlement\b|\bshare[-\s]based\s+(?:interest\s+)?payment\b|"
    r"\b(?:updated|update\s+to)\s+share\s+capital\b"
    r")")

R9_ACT = re.compile(
    r"(?i)(?:"
    r"\brollback\b|\b(?:share|stock)\s+consolidation\b|\bconsolidation\s+of\s+(?:its\s+)?(?:common\s+)?shares\b|"
    r"\bcompletion\s+of\s+(?:the\s+)?(?:share\s+)?consolidation\b(?!\s+of\b)|"
    r"\b(?:completes?|effects?|announces?|approves?)\s+(?:a\s+|its\s+|the\s+)?(?:\d+[:\-]\d+\s+|\d+\s+for\s+\d+\s+)?"
    r"(?:share\s+)?consolidation\b(?!\s+of\b)|\b\d+\s*(?:-|:|\s+for\s+)\s*\d+\s+(?:share\s+)?(?:consolidation|rollback|split)\b|"
    r"\b(?:forward|stock|share)\s+split\b|\bname\s+change\b|\bchange\s+of\s+(?:corporate\s+)?name\b|"
    r"\bchanges?\s+(?:its\s+)?(?:corporate\s+)?name\b|\bdividends?\b|\bspecial\s+distribution\b|\breturn\s+of\s+capital\b|"
    r"\bregistered\s+(?:office|address)\b|\bcorporate\s+domicile\b|\bprincipal\s+place\s+of\s+business\b|"
    r"\bnew\s+(?:ticker|trading)\s+symbol\b|\bsymbol\s+change\b|\bchanges?\s+(?:its\s+)?(?:ticker|trading\s+symbol)\b|"
    r"\bcreates?\s+(?:two\s+|a\s+)?(?:new\s+)?(?:100%\s+)?wholly[-\s]owned\s+subsidiar\w+\b|"
    r"\bincorporat\w+\s+(?:of\s+)?(?:a\s+)?(?:new\s+)?(?:wholly[-\s]owned\s+)?subsidiar\w+\b|\btransfer\s+agent\b|"
    r"\bchange\s+(?:of|in)\s+(?:financial\s+|fiscal\s+)?year[-\s]end\b|\bnormal\s+course\s+issuer\s+bid\b|\bNCIB\b|"
    r"\bshare\s+(?:buy-?backs?|repurchases?)\b"
    r")")

R9_LST = re.compile(
    r"(?i)(?:"
    r"\b(?:resumes?|resumption\s+of|to\s+resume)\s+(?:of\s+)?trading\b|\btrading\s+(?:resumes?|resumption)\b|"
    r"\bmoves?\s+to\s+(?:the\s+)?(?:TSX|TSXV|TSX[-\s]?V|TSX\s+Venture|CSE|NYSE|Nasdaq|ASX|AIM)\b|\bgraduat\w+\s+to\b|"
    r"\bup-?list\w*\b|\bdelist\w*\b|\b(?:commences?|begins?|start\s+of|starts?|commencement\s+of)\s+trading\b|"
    r"\b(?:listing|listed|lists)\s+(?:on|with)\s+(?:the\s+)?(?:OTCQB|OTCQX|OTC|Frankfurt|FSE|B[öo]e?rse|XETRA|NYSE|Nasdaq|ASX|AIM|"
    r"TSX|TSXV|CSE|Toronto\s+Stock\s+Exchange|TSX\s+Venture)\b|\bDTC\s+eligib\w*\b|\bFINRA\b|\bGerman\s+(?:symbols?|listing)\b|"
    r"\bdual[-\s]list\w*\b|\bconditional\s+listing\s+approval\b|\bfinal\s+listing\s+approval\b|"
    r"\b(?:qualif\w+|approved|approval)\s+(?:for|to)\s+(?:trade\s+on\s+)?(?:the\s+)?(?:OTCQB|OTCQX)\b|"
    r"\b(?:high|unusual)\s+(?:volume\s+of\s+)?(?:market\s+|trading\s+)?(?:activity|trading)\b|\bunusual\s+market\b"
    r")")

R9_FNS = re.compile(
    r"(?i)(?:"
    r"\b(?:files?|filed|filing\s+of|completes?|posts?|posted|announces?\s+filing\s+of)\s+(?:its\s+|the\s+)?(?:[\w'’\-]+\s+){0,5}?"
    r"(?:quarterly\s+(?:activit(?:y|ies)\s+)?report|annual\s+(?:filings?|reports?|financial\s+(?:disclosure|statements|results))|"
    r"interim\s+(?:filings?|financial\s+(?:statements|report))|year[-\s]end(?:\s+(?:filings?|financial\s+statements|results))?|"
    r"financial\s+statements|MD&A|audited\s+(?:annual\s+)?(?:financial\s+)?(?:statements|results))\b|"
    r"\binterim\s+filings\b|\bannual\s+filings\b|\bquarterly\s+activit(?:y|ies)\s+report\b|"
    r"\bfinancial\s+(?:and\s+operating\s+)?(?:highlights|position\s+update|update)\b|\bfree\s+cash\s+flow\b|"
    r"\b(?:strong|record|continued\s+strong|solid|improved)\s+financial\b|\bannual\s+reports?\s+posted\b|"
    r"\bto\s+(?:release|report|announce)\s+" + G(40) + r"\b(?:quarter|Q[1-4]|year[-\s]end|full[-\s]year|annual|interim)\b|"
    r"\bsales\s+of\s+(?:US|C|CA)?\s?\$|\brevenues?\s+(?:in\s+excess\s+of|of\s+(?:US|C|CA)?\s?\$)|\b(?:positive|record)\s+(?:adjusted\s+)?EBITDA\b|"
    r"\b(?:half[-\s]yearly|quarterly|interim)\s+report\b|\bquarter\s+report\b|\b20\d\d\s+financials\b"
    r")")
R9_FNS_NOT = re.compile(r"(?i)\b(?:delay\w*|late|MCTO|cease\s+trade|production|exploration|drill\w*|assay|meeting|AGM)\b")

R9_PRD = re.compile(
    r"(?i)(?:"
    r"\b(?:ounces|oz)\s+(?:of\s+(?:gold|silver)\s+)?produced\b|\bproduction\s+(?:increases?|increased|rises?|grows?|up\b|record|"
    r"update|summary|results|of\s+[\d,.]+)|\b(?:record|quarterly|monthly|annual|Q[1-4])\s+(?:\w+\s+)?production\b|"
    r"\b(?:commences?|begins?|starts?|restarts?|resumes?)\s+(?:(?:commercial|seasonal|full|test|pilot|small[-\s]scale|trial)\s+)*"
    r"production\b|\bcommercial\s+production\b|\bproduction\s+(?:and|&)\s+(?:guidance|sales|outlook)\b|"
    r"\b(?:production|throughput)\s+(?:outlook|estimate|guidance)\b|\brecord\s+throughput\b|\b(?:tonnes|ounces|oz|lbs|pounds)\s+produced\b|"
    r"\bproduc\w+\s+(?:a\s+)?(?:record\s+)?[\d,.]+\s*(?:oz|ounces|tonnes|t\b|lbs|pounds)|"
    r"\b(?:quarter|Q[1-4]|annual|year)\b" + G(30) + r"\b(?:operational|operating)\s+(?:results|update|highlights)\b"
    r")")

R9_PER = re.compile(
    r"(?i)(?:"
    r"\bpermitting\s+(?:update|progress|process|advances?|underway|milestone|application|activities|work|status|timeline|"
    r"schedule|continues)\b|\b(?:update|progress)\s+on\s+(?:the\s+|its\s+)?(?:[\w'’\-]+\s+){0,3}?permit\w*\b|"
    r"\bpermits?\s+(?:received|granted|approved|issued|renewed|for\s+drill\w*|applications?)\b|"
    r"\bapproval\s+of\s+(?:(?:the|required|all|key|its)\s+)*(?:permits?|licen[cs]es?)\b|"
    r"\b(?:drill(?:ing)?|exploration|mining|environmental|water|work|surface|construction)\s+permits?\b|"
    r"\benvironmental\s+(?:licen[cs]e|approval|impact|assessment|permit|certificate|authori[sz]ation|clearance)\b|"
    r"\bEIA\b|\bEIS\b|\brezoning\b|\bwater\s+rights\b|\bnotice\s+of\s+work\b|\bassessment\s+order\b|\bstop[-\s]work\s+order\b|"
    r"\bmining\s+(?:title|concession)\s+(?:granted|suspension|approval|renewal)\b|\bministerial\s+(?:decree|approval|order)\b|"
    r"\b(?:land\s+use|surface\s+access)\s+agreements?\b"
    r")")

R9_MET = re.compile(
    r"(?i)(?:"
    r"\bmetallurg\w+|\btest\s?work\b|\bbench[-\s]scale\b|\bpilot\s+(?:plant|scale|test\w*|program)\b|\bflotation\b|\bleach\w*\b|"
    r"\brecover(?:y|ies)\s+(?:test\w*|results?|rates?)\b|\b(?:gold|silver|copper|lithium|nickel|coarse\s+gold)\s+recover(?:y|ies)\b|"
    r"\bbulk\s+samples?\b|\bspheroni[sz]\w+\b|\bpurif\w+\b|\bbattery[-\s]grade\b|\b(?:anode|cathode)\s+(?:active\s+)?materials?\b|"
    r"\bcoatings?\b|\bprocessing\s+(?:of|technology|test\w*|route|flowsheet)\b|\bcustom\s+processing\b|\btoll\s+(?:milling|processing)\b|"
    r"\bconcentrate\s+(?:grade|quality|specification)\b|\bmineral\s+processing\b|\bore\s+sorting\b|\bmineralog\w+\b|"
    r"\bbeneficiation\b|\bflowsheet\b|\bextraction\s+(?:technology|process|test\w*)\b"
    r")")

R9_MKT = re.compile(
    r"(?i)(?:"
    r"\binvestor\s+relations\b|\bIR\s+(?:firm|consultant|services|agreement|program|campaign)\b|\bengagement\s+of\s+" + G(40) + r"\b(?:digest|media|marketing|communications|awareness)\b|"
    r"\b(?:engages?|retains?|hires?|appoints?)\b" + G(60) + r"\b(?:marketing|media|communications|digital|awareness|"
    r"investor\s+awareness|stock\s+digest)\b|"
    r"\b(?:increase|improve|enhance)s?\s+(?:its\s+)?(?:market\s+)?(?:visibility|awareness|shareholder\s+communications)\b|"
    r"\bconference\s+call\b|\bwebcast\b|\brecording\s+link\b|\binvestor\s+(?:day|call|update\s+call|presentation|webinar|"
    r"conference|site\s+visit|tour)\b|\bconference\s+attendance\b|\b(?:shareholder\s+)?update\s+call\b|\bvideo\b|\binterview\b|"
    r"\bconference\s+participation\b|\bto\s+showcase\b|\b(?:engages?|retains?)\s+(?:[A-Z][\w&.]*\s+){1,4}(?:Capital\s+Markets|Research)\b"
    r")")

R9_REG = re.compile(
    r"(?i)(?:"
    r"\bdelay\w*\s+(?:of|in)\s+(?:the\s+|its\s+)?(?:[\w\-]+\s+){0,2}?filings?\b|\blate\s+filing\b|\bMCTO\b|"
    r"\bmanagement\s+cease\s+trade\b|\bcease\s+trade\b|\bForm\s+15F\b|\bSEC\s+reporting\b|\bclarif\w+\b|"
    r"\bcorrect(?:ion|s|ed)?\s+(?:to|of|regarding)\s+(?:the\s+|its\s+|a\s+)?(?:\w+\s+){0,3}(?:news|press)\s+release\b|"
    r"\berratum\b|\bretract\w*\b|\bregulatory\s+(?:action|review|matters)\b|\bchange\s+of\s+auditors?\b|\bderegist\w+\b"
    r")")

R9_JV = re.compile(
    r"(?i)(?:"
    r"\b(?:establishes?|forms?|signs?|enters?\s+into|announces?)\s+(?:an?\s+|the\s+)?(?:[\w\-]+\s+){0,3}?(?:working\s+relationship|"
    r"joint\s+(?:technical\s+)?committee|technology\s+agreement|research\s+(?:agreement|collaboration|partnership)|"
    r"strategic\s+relationship)\b|\btechnology\s+agreement\b|\bMOU\b|\bmemorandum\s+of\s+understanding\b|\bjoint\s+venture\b|"
    r"\bstrategic\s+partner\w*\b|\bpartners?\s+with\b|\bteams?\s+up\s+with\b|\bjoint[-\s]venture\b|"
    r"\b(?:Indian\s+Band|First\s+Nations?|Nation)\b" + G(40) + r"\bagreement\b|\bbridging\s+agreement\b"
    r")")

R9_MTG = re.compile(r"(?i)\bmeeting\s+(?:matters|results)\b|\b(?:re-?)?election\s+of\s+(?:its\s+|the\s+)?(?:board|directors)\b|\bvoting\s+results\b|\bresults\s+of\s+(?:the\s+)?(?:annual|special)"
                    r"(?:\s+and\s+special)?\s+(?:general\s+)?meeting\b|\bAGM\s+results\b|\bshareholders?\s+approve\b")


R9_ROY = re.compile(r"(?i)\b(?:stream|royalty)\s+(?:repurchase|buy-?back)\b|\b(?:repurchase|buy-?back)\s+of\s+(?:the\s+)?(?:[\w\-]+\s+){0,3}(?:royalty|stream)\b")
R9_DBT = re.compile(r"(?i)\b(?:revolving\s+)?credit\s+facil\w+|\bfacilities\s+agreement\b|\bterm\s+loan\b|\bconvertible\s+(?:loan|note|debenture)s?\b")
R9_RES = re.compile(r"(?i)\b(?:announces?|reports?|delivers?|updates?|files?|releases?|publishes?)\s+(?:[\w'’\-,]+\s+){0,6}?"
                    r"(?:mineral\s+)?resource(?:\s+estimate|\s+update|\s+statement)?\b|\bresource\s+estimate\s+update\b|"
                    r"\b(?:maiden|initial|updated|first|inaugural)\s+(?:mineral\s+)?resource\b")
R9_RES_NOT = re.compile(r"(?i)\bresource\s+(?:stock|capital|sector|investors?|world|conference|digest|funds?|partners)\b|"
                        r"\bto\s+update\b|\bseeks?\b|\bsecures?\s+(?:\w+\s+)?technical\s+team\b|\binfill\s+drilling\b")
R9_LETTERHEAD = re.compile(r"(?i)for\s+further\s+information|(?:stock|trading|ticker)\s+symbols?\s*:|call-in|"
                           r"\b\d{1,2}:\d{2}\s*[ap]\.?m\.?\s+(?:ET|EST|EDT|PT|PST)|\bpage\s+\d+\s+of\b|shares\s+issued\s+and\s+outstanding")


def v9r_tags(headline: str | None) -> list[str]:
    """Existing tags a Corporate-Updates-only headline should have carried (CU_RESCUE_V1)."""
    h = norm_head(headline)
    if not h or _DISCLAIMER_HEADLINE_V8.search(h) or R9_LETTERHEAD.search(h):
        return []
    third = bool(_THIRD_PARTY.search(h))
    funding = bool(R9_FUNDING.search(h))
    out = []
    grade = bool(R9_GRADE.search(h))
    drill = ((grade and not re.search(r"(?i)\b(?:on\s+surface|surface|channel|trench\w*|grab|chip|soil)\b", h))
             or (R9_DRILL.search(h) and not R9_DRILL_NOT.search(h)))
    if drill and not third and not (_DRILL_HISTORICAL.search(h) and not _DRILL_NEW_WORK.search(h)):
        out.append("Drill Results")
    else:
        m = R9_EXPL.search(h)
        if (m and not R9_EXPL_NOT.search(h) and not funding and not third
                and not ("discover" in m.group(0).lower() and _DISCOVERY_NAME.search(h))):
            out.append("Exploration Programs")
    if (R9_RES.search(h) and not R9_RES_NOT.search(h) and not third
            and (_MRE_DELIVERED.search(h) or not _STUDY_PLAN.search(h))):
        out.append("Resource Estimates")
    if R9_OPT.search(h) and not R9_OPT_NOT.search(h) and not third:
        out.append("Property Options & Staking")
    if R9_MGMT.search(h) and not R9_MGMT_NOT.search(h) and not _MGMT_NOT.search(h):
        out.append("Management Changes")
    if R9_MNA.search(h) and not R9_MNA_NOT.search(h) and not third:
        out.append("Mergers & Acquisitions")
    if R9_FIN.search(h) and not R9_FIN_NOT.search(h):
        out.append("Financings")
    if R9_CAP.search(h):
        out.append("Share Capital & Compensation")
    if R9_ACT.search(h):
        out.append("Corporate Actions")
    if R9_LST.search(h):
        out.append("Listings & Exchange")
    if R9_FNS.search(h) and not R9_FNS_NOT.search(h) and not third:
        out.append("Financials")
    if (R9_PRD.search(h) and not _OIL_GAS.search(h) and not PROD_V7_NOT.search(h) and not third
            and not re.search(r"(?i)\bhistoric(?:al)?\s+production\b|\bexpected\s+to\b|\broyalt\w*|\breserves?\b|"
                              r"\btowards?\b|\bpath\s+to\b|\bplans?\b|\btarget\w*\b|\bexpects?\b", h)):
        out.append("Production Results")
    if R9_PER.search(h) and not third:
        out.append("Permits & Approvals")
    if R9_MET.search(h):
        out.append("Metallurgy & Processing")
    if R9_MKT.search(h) and not re.search(r"(?i)\bfinancial\s+advis", h) and "Financials" not in out:
        out.append("Marketing Announcement")
    if R9_REG.search(h):
        out.append("Regulatory & Compliance")
    if R9_JV.search(h):
        out.append("Partnerships & JV")
    if R9_MTG.search(h):
        out.append("Shareholder Meetings")
    if R9_ROY.search(h):
        out.append("Royalties & Streams")
    if R9_DBT.search(h):
        out.append("Debt & Credit Facilities")
    return [c for c in CATEGORIES if c in out]


def add_v9r_tags(cats: list[str], headline: str | None, recovered: str | None = None) -> list[str]:
    """CU_RESCUE_V1: only a release still in Corporate Updates alone is looked at again."""
    if list(cats) != ["Corporate Updates"]:
        return cats
    tags = v9r_tags(headline)
    if recovered:
        tags += [t for t in v9r_tags(recovered) if t not in tags]
    if not tags:
        return cats
    return [c for c in CATEGORIES if c in set(tags)]


# ===========================================================================
# v10 new tags (NEWTAGS_V1, 2026-09-26). Justin chose five of the eight tags suggested by the
# Corporate Updates audit (claude/MNT_CORP_UPDATES_AUDIT_FINDINGS_2026-09-25.md) and asked for the
# two small themes to go under Marketing Announcement:
#   Mine Development & Operations · Sampling & Geoscience Results · Legal & Disputes ·
#   Shareholder Letters & Outlook · Company Commentary;
#   results dates / conference-call notices and awards -> Marketing Announcement.
# Headline-scoped like v8. The five tags are ADDITIVE on every release (a release can be both
# Production Results and Mine Development); Corporate Updates is dropped when any tag fires.
# The Marketing fold-ins only rescue Corporate-Updates-only releases.
# ===========================================================================

V10_TAGS = ("Mine Development & Operations", "Sampling & Geoscience Results", "Legal & Disputes",
            "Shareholder Letters & Outlook", "Company Commentary")

R10_DEV = re.compile(
    r"(?i)(?:"
    # construction, commissioning, ramp-up, restart
    r"\b(?:construction|commissioning|commissioned|ramp[-\s]?up|ramping\s+up)\b|"
    r"\b(?:first|inaugural)\s+(?:gold|silver|dor[eé]|copper|concentrate|shipment|sale|production|ore|pour)\b|\bgold\s+pour\b|"
    r"\bpours?\s+(?:first|initial)\b|"
    r"\bmine\s+(?:development|restart|re-?start|build|construction|preparation|plan\s+update)\b|"
    r"\b(?:re-?starts?|restarting|restarted)\s+(?:of\s+)?(?:the\s+|its\s+)?(?:[\w\-]+\s+){0,3}?(?:mine|mill|plant|operations?|production|mining)\b|"
    r"\b(?:underground|lateral|decline|portal)\s+development\b|\bdewatering\b|\bportal\s+(?:construction|breakthrough|collared)\b|"
    r"\bmill\s+(?:refurbish\w*|restart|construction|upgrade|expansion)\b|\b(?:processing|heap\s+leach|CIL|CIP)\s+(?:plant|facility|pad)\b|"
    r"\b(?:all-season\s+|access\s+)road\b|\bpower\s+(?:line|supply\s+agreement)\b|\bgrid\s+connection\b|"
    r"\b(?:development|mining|construction|EPCM?|drill\s+and\s+blast)\s+contracts?\b|\bcontract\s+min(?:ing|er)\b|\bEPCM?\b|"
    r"\b(?:construction|production|development)\s+decision\b|\bfinal\s+investment\s+decision\b|\bFID\b|"
    r"\bon[-\s]track\s+for\s+(?:first\s+)?(?:production|commissioning|gold|pour)\b|\bcommercial\s+production\b|"
    # operations: updates, suspensions, incidents
    r"\b(?:operations?|operational|mine|site)\s+update\b|\boperational\s+outlook\b|\bcare\s+and\s+maintenance\b|"
    r"\b(?:suspend\w*|suspension|curtail\w*|shut\s?down|halts?|pauses?|temporar\w+\s+(?:stops?|closure))\s+"
    r"(?:of\s+)?(?:the\s+|its\s+|all\s+)?(?:[\w\-]+\s+){0,3}?(?:operations?|mining|production|milling|processing|mine|mill|plant|activities|work)\b|"
    r"\bforce\s+majeure\b|\bwildfires?\b|\bforest\s+fires?\b|\bflood\w*\b|\bblockades?\b|\bevacuat\w+\b|"
    r"\bfatal\w*\b|\b(?:safety\s+)?incident\b|\baccident\b|\bsafe\s+recovery\b|"
    r"\btrapped\b|\billegal\s+min\w+\b|\b(?:labou?r|workers?)\s+(?:dispute|strike|action|stoppage)\b|\bstrike\s+(?:action|at)\b|"
    r"\bresum\w+\s+(?:of\s+)?(?:full\s+|normal\s+)?(?:operations|mining|production|milling|processing)\b|"
    # offtake, sales, shipments
    r"\bofftake\b|\boff[-\s]take\b|\bconcentrate\s+(?:sales?|shipments?|purchase)\b|\b(?:ore|concentrate)\s+(?:purchase|processing|sales?)\s+agreement\b|"
    r"\btoll\s+(?:milling|processing|treatment)\b|\bshipments?\s+of\b|\bfirst\s+shipment\b|\bships?\s+(?:first\s+)?(?:concentrate|ore|dor[eé]|cargo)\b"
    r")")
R10_DEV_NOT = re.compile(
    r"(?i)\b(?:oil|natural\s+gas|petroleum|cannabis|hemp|crypto\w*|bitcoin|blockchain|real\s+estate|restaurant|software|"
    r"pharma\w*|biotech\w*)\b|"
    r"\b(?:trading|shares?|stock)\s+(?:halt|suspension)\b|\bsuspension\s+of\s+trading\b|\bhalt(?:s|ed)?\s+trading\b|"
    r"\b(?:drill\w*|exploration)\s+(?:program\s+)?(?:suspend\w*|suspension|restart\w*|resum\w+|paus\w+)\b|"
    r"\b(?:suspend\w*|suspension|restart\w*|resum\w+|paus\w+)\s+(?:of\s+)?(?:the\s+|its\s+|all\s+)?(?:[\w\-]+\s+){0,2}?(?:drill\w*|exploration)\b|"
    r"\bresource\s+model\b|\bwebinar\b|\bconference\b|\bcamp\s+construction\b|\bdrill(?:ing)?\s+operations\b|"
    r"\bhalt(?:s|ed|ing)?\s+(?:all\s+)?drill\w*\b|\bahead\s+of\s+(?:the\s+)?(?:\w+\s+)?drill\w*\b|"
    r"\bfiling\s+(?:deadlines?|requirements?)\b|\bcontinuous\s+disclosure\b|\bannual\s+(?:and\s+special\s+|general\s+)*meeting\b|\bAGM\b")
R10_COVID = re.compile(r"(?i)\b(?:COVID(?:-19)?|coronavirus|pandemic)\b")
R10_COVID_OPS = re.compile(r"(?i)\b(?:operations?|operating|mine|mines|mining|mill|site|production|cases?|workforce|employees|workers|"
                           r"suspend\w*|suspension|shut\w*|curtail\w*|resum\w+|restart\w*|protocols?|measures)\b")

R10_SMP = re.compile(
    r"(?i)(?:"
    r"\b(?:grab|chip|channel|rock|soil|till|stream[-\s]sediment|lake[-\s]sediment|surface|outcrop|boulder|trench|"
    r"reconnaissance|prospecting|float|bulk\s+leach|BLEG|lithium[-\s]brine|brine)\s+(?:and\s+\w+\s+)?(?:samples?|sampling|results|assays?|"
    r"values|grades?|geochemistry|program\s+results)\b|"
    r"\bsamples?\s+(?:returns?|returned|grading|assay\w*|up\s+to|yield\w*|of\s+up\s+to|results?|average\w*|confirm\w*|reveal\w*|"
    r"highlight\w*|include\w*|contain\w*|with)\b|\bsampling\s+(?:returns?|results?|confirms?|reveals?|identifies?|highlights?|"
    r"extends?|expands?|defines?|outlines?|delineates?|continues\s+to|yields?|program\s+results)\b|"
    r"\btrench(?:es|ing)?\s+(?:results?|returns?|exposes?|confirms?|reveals?|intersects?|cuts?|\d)|\btrenching\b" + G(40) +
    r"\b(?:g\s*/\s*t|gpt|%|ppm|results?|returns?|confirms?)\b|"
    r"\b(?:soil|till|geochemical|geophysical|IP|induced\s+polari[sz]ation|magnetic|magnetotelluric|gravity|radiometric|"
    r"airborne|ground|VTEM|ZTEM|EM|electromagnetic|MT|drone|LiDAR|hyperspectral|seismic)\s+(?:survey\s+)?(?:results?|"
    r"anomal(?:y|ies)|identifies|outlines|defines|delineates|reveals|confirms|highlights|detects|shows)\b|"
    r"\b(?:geophysic\w*|geochemi\w*|survey)\s+(?:results?|identif\w+|outlines?|defines?|delineates?|reveals?|confirms?|highlights?)\b|"
    r"\b(?:identif\w+|outlines?|defines?|delineates?|reveals?|discover\w*|detects?)\s+(?:[\w\-,]+\s+){0,5}?"
    r"(?:(?:soil|geochemical|geophysical|IP|chargeability|resistivity|magnetic|gravity|EM|conductive|radiometric|gold|copper|"
    r"lithium|uranium|nickel|silver|zinc|multi-element|coincident)\s+)?(?:anomal(?:y|ies)|conductors?|chargeability\s+highs?)\b|"
    r"\bconductors?\s+(?:identified|detected|outlined)\b|\bvisible\s+gold\b|\bhigh[-\s]grade\s+(?:surface|grab|rock|chip|channel|"
    r"float|boulder|outcrop)\b|\bmapping\s+(?:and\s+sampling\s+)?(?:results?|identif\w+|confirms?|reveals?|outlines?|defines?)\b|"
    r"\bnew\s+(?:gold|copper|lithium|silver|uranium|mineralized)?\s*(?:showing|occurrence|outcrop|zone)s?\s+(?:discovered|identified|found)\b|"
    r"\bsampl\w*\b" + G(60) + r"\b\d[\d.,]*\s*(?:g\s*/\s*t|gpt|g/tonne|%|ppm|oz\s*/\s*t)|"
    r"\bprospecting\s+(?:discovers|identifies|returns|results?|confirms)\b|\bsurface\s+(?:mineralization|showing|discovery|"
    r"exploration\s+results?|work\s+results?)\b"
    r")")
R10_SMP_NOT = re.compile(
    r"(?i)\bdrill\w*\b|\bholes?\b|\bintersect\w*\b|\bintercept\w*\b|\bcore\b|\b(?:metallurgical|bulk|environmental|water|"
    r"baseline|tailings)\s+samples?\b|\bsample\s+preparation\b|\bsamples?\s+(?:submitted|shipped|sent|awaiting|pending|collected)\b|"
    r"\b(?:plans?|planned|to\s+begin|begins|commences?|starts?|mobiliz\w+|underway|initiates?|launches?)\b" + G(40) +
    r"\b(?:sampling|survey|program|mapping|trenching)\b(?!" + G(40) + r"\b(?:results?|returns?|identif\w+|confirms?|reveals?)\b)|"
    r"\bpetroleum\b|\boil\b|\bcannabis\b|\bbulk\s+sampl\w*\b|\brigs?\b|\bships?\b|\bshipped\b|\bconcentrate\b|"
    r"\b(?:plans?|planned|expand\w*|begins?|commences?|starts?|initiates?|launches?)\s+(?:[\w\-]+\s+){0,3}?(?:soil|till|geochemi\w*|"
    r"geophysic\w*|survey|sampling|mapping|trenching|IP)\b(?!" + G(40) + r"\b(?:results?|returns?|identif\w+|confirms?|reveals?)\b)")

R10_LEG = re.compile(
    r"(?i)(?:"
    r"\blawsuits?\b|\blitigation\b|\bcourt\b|\barbitra\w+\b|\bICSID\b|\btribunal\b|\bjudg(?:e)?ments?\b|\binjunction\b|"
    r"\blegal\s+(?:action|actions|proceedings?|claims?|update|challenge|dispute|matters?|victory|win|case)\b|"
    r"\b(?:claim|action|suit|proceedings?|complaint)\s+against\b|\bstatement\s+of\s+claim\b|\bnotice\s+of\s+(?:dispute|intent\s+to\s+submit|arbitration|claim)\b|"
    r"\bappeal(?:s|ed|ing)?\b|\bdisputes?\b|\bdisputed\b|\bsues\b|\bsued\b|\bsuing\b|\bclass\s+action\b|\bexpropriat\w+\b|"
    r"\bnationali[sz]\w+\b|\bcreditor\s+(?:protection|proceedings)\b|\bbankruptcy\b|\binsolven\w+\b|\bCCAA\b|\breceivership\b|"
    r"\breceiver\s+(?:appointed|and\s+manager)\b|\bactivist\b|\bdissident\b|\bproxy\s+(?:fight|contest|battle)\b|\brequisition\w*\b|"
    r"\bverdict\b|\bruling\b|\bsettle\w*\s+(?:of\s+)?(?:the\s+|its\s+|all\s+)?(?:[\w\-]+\s+){0,3}?(?:litigation|lawsuit|dispute|claims?|"
    r"arbitration|legal\s+proceedings?|action)\b|\bdefamat\w+\b|\bfraud\b|\bbreach\s+of\s+contract\b|\bmoratorium\b"
    r")")
R10_LEG_NOT = re.compile(
    r"(?i)\bcourt\s+(?:approv\w+|order\s+approv\w+|hearing\s+(?:to\s+)?approv\w+)\b|\b(?:final|interim)\s+(?:court\s+)?order\b|"
    r"\bplan\s+of\s+arrangement\b|\bsupreme\s+court\s+of\s+british\s+columbia\s+approv\w+\b|\bapproval\s+of\s+the\s+court\b|"
    r"\bappeal(?:s|ing)?\s+to\s+(?:investors|shareholders)\b|\bdisputed\s+(?:ground|area)\b|\bwarrants?\b|\bnon[-\s]brokered\b|"
    r"\bprivate\s+placement\b|\bshares?\s+for\s+debt\b|\bdebt\s+settlement\b|\bruling\s+(?:party|class)\b|\bmineral\s+claims?\b|"
    r"\bstakes?\b|\bstaking\b|\b(?:approved|sanctioned)\s+by\s+(?:the\s+)?court\b|"
    r"\bCourt\s+(?:Copper|Gold|Silver|Zinc|Nickel|Lithium|Uranium|Project|Property|Prospect|Claims?|Deposit|Zone|Showing|Road|Drive)\b|"
    r"\b\d+\s+(?:[A-Z]\w+\s+){1,2}Court\b")

R10_LTR = re.compile(
    r"(?i)(?:"
    r"\bletter\s+(?:to|from)\s+(?:the\s+)?(?:shareholders|stakeholders|investors|CEO|chair\w*|president)\b|"
    r"\b(?:shareholder|stakeholder|investor)\s+letter\b|\b(?:CEO|chair\w*|president)(?:'s|’s)?\s+(?:letter|message|update\s+to\s+shareholders)\b|"
    r"\bmessage\s+(?:from|to)\s+(?:the\s+)?(?:president|CEO|chair\w*|shareholders)\b|\bupdate\s+to\s+shareholders\b|"
    r"\byear\s+in\s+review\b|\b(?:review|recap)\s+of\s+(?:20\d\d|the\s+year)\b|\byear[-\s]end\s+(?:review|recap|summary|letter)\b|"
    r"\b20\d\d\s+(?:year\s+)?(?:in\s+review|review|highlights|achievements|accomplishments|recap|milestones\s+achieved|summary)\b|"
    r"\b(?:outlook|objectives|priorities|milestones|catalysts|goals|strategy|strategic\s+priorities)\s+for\s+(?:20\d\d|the\s+(?:year|coming\s+year))\b|"
    r"\b20\d\d\s+(?:corporate\s+)?(?:outlook|objectives|priorities|milestones|catalysts|goals|strategy|strategic\s+plan)\b|"
    r"\b(?:corporate|strategic|business)\s+(?:strategy|plan|priorities|direction|vision)\b|\bstrategic\s+(?:update|overview)\b|"
    r"\bmid[-\s]year\s+(?:review|update|letter)\b|\blooks?\s+ahead\s+to\b|\bvision\s+for\b"
    r")")
R10_LTR_NOT = re.compile(
    r"(?i)\bstrategic\s+(?:review|alternatives|investment|investor|partner\w*|shareholder|stake|acquisition|alliance|financing)\b|"
    r"\bguidance\b|\bexploration\s+(?:program|plans?|budget)\b|\bdrill\w*\b|\bfinancial\s+statements\b|\bMD&A\b|"
    r"\bconference\s+call\b|\bwebcast\b|\b(?:financial|operating|production|quarter\w*)\s+(?:and\s+\w+\s+)?results\b|\bappoint\w*\b")

R10_CMT = re.compile(
    r"(?i)(?:"
    r"\bcomments?\s+(?:on|regarding|about)\b|\bcommentary\b|\b(?:responds|reacts?)\s+to\b|"
    r"\b(?:respond|response)\s+to\s+(?:the\s+)?(?:recent|media|market|short|report|article|allegations?|claims?|comments?|inquir\w+|"
    r"questions?|notice|letter|news|shareholder|statements?|press)\b|\bstatement\s+(?:on|regarding|about|in\s+response)\b|"
    r"\bcongratulates?\b|\bapplauds?\b|\bcommends?\b|\bwelcomes?\s+(?:the\s+)?(?:news|decision|announcement|ruling|approval|"
    r"government|federal|provincial|budget|policy|executive\s+order|designation|inclusion|report|results\s+of|release\s+of|"
    r"passage|launch|initiative|support|investment|recognition|progress)\b|\backnowledges?\s+(?:the\s+)?(?!receipt)\w+|"
    r"\bnotes\s+(?:the\s+)?(?:recent|media|market|report|announcement|decision|news|press)\b|\bsets\s+the\s+record\s+straight\b|"
    r"\baddresses\s+(?:recent|market|media|shareholder|investor)\b|\bupdate\s+on\s+(?:market|industry)\s+conditions\b|"
    r"\bhighlights\s+(?:[\w\-]+\s+){0,4}?(?:policy|environment|market|opportunit\w+|demand|tailwinds?|momentum|importance|role)\b|"
    r"\bweighs\s+in\b|\bspeaks\s+(?:out|on)\b|\bopen\s+letter\b"
    r")")
R10_CMT_NOT = re.compile(
    r"(?i)\bunusual\s+(?:market|trading)\b|\bmarket\s+activity\b|\bIIROC\b|\bCIRO\b|\bregulatory\s+(?:request|inquiry)\b|"
    r"\bno\s+material\s+(?:change|undisclosed)\b|\binformation\s+request\b|\bwelcomes?\s+(?:new\s+)?(?:[A-Z][a-z]+\s+){0,3}"
    r"(?:to\s+(?:the\s+)?(?:board|team)|as\s+)|\b(?:board|director|CEO|CFO|COO|VP|president|chair\w*)\b.{0,30}\bwelcom|"
    r"\bwelcomes?\b.{0,40}\b(?:board|director|CEO|CFO|COO|VP|president|chair\w*|advisor|team)\b|\backnowledges?\s+receipt\b|"
    r"\backnowledg\w+\s+(?:the\s+)?(?:TSX|CSE|exchange)\b")

# --- folded into Marketing Announcement (Corporate-Updates-only releases only) ---
R10_MKT_DATES = re.compile(
    r"(?i)(?:"
    r"^(?:[\w.&'’\-]+\s+){0,6}?(?:to|will)\s+(?:release|report|announce|publish)\b" + G(50) +
    r"\b(?:results|quarter|Q[1-4]|year[-\s]end|financial\s+statements|earnings)\b|"
    r"\b(?:to|will)\s+(?:host|hold)\b" + G(40) + r"\b(?:conference\s+call|webcast|earnings\s+call|investor\s+call|Q\s*&\s*A|AMA|"
    r"live\s+(?:stream|event|session))\b|"
    r"\bnotice\s+of\s+(?:the\s+)?(?:release|results|conference\s+call|webcast|earnings)\b|\bresults\s+(?:release\s+)?(?:date|timing)\b|"
    r"\b(?:release|reporting)\s+date\b|\bdate\s+(?:for|of)\s+(?:the\s+)?(?:release|announcement)\s+of\b|\bearnings\s+call\b"
    r")")
R10_MKT_AWARD = re.compile(
    r"(?i)(?:"
    r"\b(?:wins?|won|receives?|received|earns?|earned|presented\s+with|awarded)\s+(?:the\s+|a\s+|an\s+)?(?:[\w'’\-]+\s+){0,6}?"
    r"(?:award|prize|medal|trophy|recognition)s?\b|\baward(?:s)?\s+(?:for|at|in\s+recognition)\b|"
    r"\bTSX\s+Venture\s+50\b|\bTSXV?\s+50\b|\bOTCQX\s+Best\s+50\b|\bnamed\s+(?:to|in|among|one\s+of)\s+(?:the\s+)?(?:[\w'’\-&]+\s+){0,5}?"
    r"(?:list|ranking|50|100|top)\b|\brecogni[sz]ed\s+(?:as|by|for|among|with)\b|\bfinalist\b|\bhonou?red\b|\branked\s+(?:among|#?\d|in\s+the\s+top)\b"
    r")")
R10_MKT_AWARD_NOT = re.compile(
    r"(?i)\baward[-\s]winning\b|\bawarded\s+(?:[\w\-]+\s+){0,5}?(?:contract|concession|licen[cs]e|claims?|tender|project|permit|"
    r"property|tenements?|block|grant|funding|drilling|rights|option)\b|\bawards?\s+(?:contract|drilling|grant|options?|RSUs?|DSUs?|"
    r"stock|incentive)\b|\bstock\s+options?\b|\bincentive\b")


def v10_tags(headline: str | None) -> list[str]:
    """The five NEWTAGS_V1 tags this headline carries (additive on any release)."""
    h = norm_head(headline)
    if not h or _DISCLAIMER_HEADLINE_V8.search(h) or R9_LETTERHEAD.search(h):
        return []
    out = []
    if (R10_DEV.search(h) or (R10_COVID.search(h) and R10_COVID_OPS.search(h))) and not R10_DEV_NOT.search(h):
        out.append("Mine Development & Operations")
    if R10_SMP.search(h) and not R10_SMP_NOT.search(h):
        out.append("Sampling & Geoscience Results")
    if R10_LEG.search(h) and not R10_LEG_NOT.search(h):
        out.append("Legal & Disputes")
    if R10_LTR.search(h) and not R10_LTR_NOT.search(h):
        out.append("Shareholder Letters & Outlook")
    if R10_CMT.search(h) and not R10_CMT_NOT.search(h):
        out.append("Company Commentary")
    return out


def v10_marketing(headline: str | None) -> bool:
    """Results-date / conference-call notices and awards (folded into Marketing Announcement)."""
    h = norm_head(headline)
    if not h or _DISCLAIMER_HEADLINE_V8.search(h):
        return False
    return bool(R10_MKT_DATES.search(h) or (R10_MKT_AWARD.search(h) and not R10_MKT_AWARD_NOT.search(h)))


def add_v10_tags(cats: list[str], headline: str | None, recovered: str | None = None) -> list[str]:
    """NEWTAGS_V1: add the five new tags to any release; rescue Corporate-Updates-only releases into
    Marketing Announcement for results dates and awards. Corporate Updates goes when anything else fires."""
    cats = list(cats)
    tags = v10_tags(headline)
    if recovered:
        tags += [t for t in v10_tags(recovered) if t not in tags]
    if cats == ["Corporate Updates"] and (v10_marketing(headline) or (recovered and v10_marketing(recovered))):
        tags.append("Marketing Announcement")
    new = set(cats) | set(tags)
    if tags and "Corporate Updates" in new and len(new) > 1:
        new.discard("Corporate Updates")
    if new == set(cats):
        return cats
    return [c for c in CATEGORIES if c in new] + [c for c in cats if c not in CATEGORIES]


# ===========================================================================
# v11 tag fixes (TAGFIX_V1, 2026-09-27). From the tag-precision audit
# (claude/MNT_TAG_PRECISION_FINDINGS_2026-09-27.md) and Justin's four scope answers:
#   * option / earn-in / staking deals are Property Options only, not M&A;
#   * share buybacks (NCIB) are Share Capital, not Corporate Actions;
#   * management cease trade orders and late filings are Regulatory, not Listings;
#   * a company correcting its own release keeps its topic tag, not Regulatory.
# Plus the audit's clean headline fixes: early warning / semi-annual reporting /
# year-end / symbol changes out of Corporate Actions, index inclusions out of
# Listings, exchange approvals out of Permits, surface sampling out of Drill
# Results, royalty-company names out of Royalties, and a study named only as a
# place in a drill headline out of Economic Studies.
# Runs LAST in categorize(). Each fix only removes a tag when the same headline,
# with the matched phrase blanked out, no longer earns that tag on its own
# (_v11_refire), so a release with a second, real reason keeps the tag.
# ===========================================================================

_V11_OPT = re.compile(
    r"(?i)(?<!stock\s)(?<!share\s)(?<!incentive\s)(?<!RSU\s)\boption(?:s|ed|ing)?\b(?!\s+(?:grants?|plan|exercis\w*|to\s+(?:directors|officers|employees)))|"
    r"\bearn[-\s]?ins?\b|\bearn(?:s|ed|ing)?\s+(?:up\s+to|an?\s+(?:additional|initial|undivided|further)|a\s+\d|\d|100|its|the\s+right)\b|"
    r"\bstak(?:e|es|ed|ing)\b|\bclaims?\s+(?:block|package|staked|acquisition)\b|\badditional\s+claims\b|"
    r"\bexploration\s+(?:licen[cs]es?|permits?|reservations?)\b")
_V11_OUTRIGHT = re.compile(
    r"(?i)\btake[-\s]?overs?\b|\btakeover\s+bid\b|\bplan\s+of\s+arrangement\b|\barrangement\s+agreement\b|\bby\s+way\s+of\s+(?:a\s+)?(?:plan\s+of\s+)?arrangement\b|"
    r"\bamalgamat\w+\b|\bmergers?\b|\bmerg(?:e|es|ed|ing)\b|\bbusiness\s+combination\b|\breverse\s+take[-\s]?over\b|\bRTO\b|\bqualifying\s+transaction\b|"
    r"\btender\s+offer\b|\bsell(?:s|ing)?\b|\bsold\b|\bsale\s+of\b|\bdivest\w*\b|\b(?:all|100%)\s+of\s+(?:the\s+)?(?:issued\s+and\s+)?outstanding\b|\bshare\s+purchase\s+agreement\b|"
    r"\bacquisition\s+of\s+all\s+(?:of\s+)?(?:the\s+)?(?:issued\s+(?:and\s+outstanding\s+)?)?shares\b|\bto\s+acquire\s+(?:all\s+of\s+)?(?-i:[A-Z][\w'&.\-]*)(?:\s+(?-i:[A-Z][\w'&.\-]*)){0,4}\s+"
    r"(?:Inc|Corp|Corporation|Ltd|Limited|plc|S\.A|LLC)\b")

_V11_BUYBACK = re.compile(
    r"(?i)\bnormal\s+course\s+issuer\s+bids?\b|\bNCIBs?\b|\bsubstantial\s+issuer\s+bid\b|\bissuer\s+bid\b|"
    r"\b(?:share|stock)\s+(?:buy[-\s]?backs?|repurchases?)\b|\bbuy[-\s]?back\s+(?:program\w*|plan|of\s+(?:its\s+)?(?:common\s+)?shares)\b|"
    r"\brepurchase\s+(?:program\w*|plan|of\s+(?:its\s+)?(?:common\s+)?shares)\b|"
    r"\bautomatic\s+(?:share|securities)\s+purchase\s+plan\b")
_V11_SEMI = re.compile(r"(?i)\bsemi-?annual\s+(?:financial\s+)?reporting\b")
_V11_YEAREND = re.compile(r"(?i)\bchang\w*\s+(?:(?:in|of|to)\s+)?(?:its\s+|the\s+)?(?:financial\s+|fiscal\s+)?year[-\s]?ends?\b")
_V11_EWR = re.compile(r"(?i)\bearly\s+warning\s+(?:news\s+release|report|filing|disclosure|notice|press\s+release)s?\b|\b62-10[34]\b|^\W*early\s+warning\b")
_V11_SYMBOL = re.compile(
    r"(?i)\b(?:ticker\s+|trading\s+|stock\s+|OTC\w*\s+|U\.?S\.?\s+|FSE\s+)?symbol\s+change\b|\bchang\w*\s+(?:of\s+|in\s+|to\s+)?(?:its\s+|the\s+)?(?:ticker\s+|trading\s+|stock\s+)?symbol\b|"
    r"\bnew\s+(?:ticker\s+|trading\s+|stock\s+)?symbol\b")

_V11_LATE = re.compile(
    r"(?i)\bmanagement\s+cease\s+trade\s+orders?\b|\bMCTO\b|\bdefault\s+status\s+(?:report|update)\b|\bbi-?weekly\s+(?:default|MCTO|status)\b|"
    r"\blate\s+filing\b|\bdelay\w*\s+(?:in\s+)?(?:the\s+)?filing\b|\bfiling\s+delay\b|\bextended\s+filing\s+deadlines?\b|"
    r"\brel(?:y|ies|ying|iance)\s+(?:up)?on\b[^\n]{0,60}?\b(?:extension|relief|exemption|deadline)s?\b|\bfiling\s+(?:extension|relief)\b")
_V11_FNS_DONE = re.compile(
    r"(?i)\bresults\b|\bnet\s+(?:income|loss)\b|\bearnings\b|\brevenues?\b|\bfiles\b(?![^\n]{0,30}\b(?:late|delay\w*|application)\b)|\bfiled\b|"
    r"\bcomplet\w+\s+(?:the\s+|its\s+)?(?:annual\s+|interim\s+)?filings?\b")
_V11_FILING_OF = re.compile(r"(?i)\bfiling\s+of\s+(?:its\s+|the\s+)?(?:annual|interim|audited|year[-\s]end|quarterly|fiscal)")
_V11_LATE_BEFORE = re.compile(r"(?i)(?:late|delay\w*|delay\w*\s+in|extension\s+for|rel(?:y|ies|iance)\s+on)\s*(?:the\s+)?$")


def _v11_filed(h: str) -> bool:
    if _V11_FNS_DONE.search(h):
        return True
    return any(not _V11_LATE_BEFORE.search(h[max(0, m.start() - 30):m.start()]) for m in _V11_FILING_OF.finditer(h))


_V11_INDEX = re.compile(
    r"(?i)\b(?:added|addition|inclusion|included|includes?|join(?:s|ed)?|enters?)\b[^\n]{0,60}?\b(?:index|indices|ETFs?)\b|"
    r"\bindex\s+inclusion\b|\blisting\s+anniversary\b|\banniversary\s+of\s+(?:its\s+)?listing\b|\bcelebrates?\b[^\n]{0,40}\blisting\b")
_V11_MKTACT = re.compile(
    r"(?i)\bcomments?\s+on\s+(?:recent\s+)?(?:share|stock)\s+price\b|\b(?:share|stock)\s+price\s+(?:movement|decline|activity)\b|"
    r"\b(?:unaware|not\s+aware)\s+of\s+any\s+material\b|\bno\s+(?:undisclosed\s+)?material\s+change\b|\bunusual\s+(?:market|trading)\s+activity\b|"
    r"\bpromotional\s+activity\b|\bOTC\s+Markets?\s+(?:Group\s+)?(?:request|inquiry)\b|\btrading\s+activity\b[^\n]{0,40}\brequest\b")
_V11_DTC = re.compile(r"(?i)\bDTC\b|\bDepository\s+Trust\b")
_V11_EXCH_APPROVAL = re.compile(
    r"(?i)\b(?:approv\w+|accept\w*)\b[^\n]{0,50}?\b(?:warrants?|repric\w+|stock\s+options?|option\s+plan|DTC|normal\s+course\s+issuer\s+bid|NCIB|issuer\s+bid|"
    r"buy[-\s]?backs?|repurchase\w*|share\s+purchase\s+plan)\b|"
    r"\b(?:warrants?|repric\w+|DTC(?:\s+eligibility)?|normal\s+course\s+issuer\s+bid|NCIB)\b[^\n]{0,50}?\b(?:approv\w+|accept\w*)\b")

_V11_CORR = re.compile(
    r"(?i)\bcorrect(?:s|ed|ion|ions|ing)?\b|\bclarif(?:y|ies|ied|ication|ying)\b|\bretract(?:s|ed|ion)?\b|\brestat(?:es|ed|ement)\b|"
    r"\bsupersed\w+\b|\berratum\b|\bamend\w*\s+(?:to\s+)?(?:the\s+|its\s+|a\s+)?(?:prior\s+|previous\s+|earlier\s+)?(?:news|press)\s+release\b")
_V11_REGULATOR = re.compile(
    r"(?i)\bBCSC\b|\bOSC\b|\bASC\b|\bAMF\b|\bFCAA\b|\bsecurities\s+commission\b|\bCIRO\b|\bIIROC\b|\bregulat\w+\b|\bstaff\s+of\b|"
    r"\b(?:compliance|continuous\s+disclosure|disclosure)\s+review\b|\bcease\s+trade\b|\bMCTO\b|\bexchange\s+request\b|"
    r"\btechnical\s+(?:report\s+)?disclosure\b|\bhistorical\s+(?:resource\s+)?estimates?\b|\bresource\s+disclosure\b|\b43-?101\s+disclosure\b")

_V11_REGULATOR_BODY = re.compile(
    r"(?i)\bBCSC\b|British\s+Columbia\s+Securities|Ontario\s+Securities|Alberta\s+Securities|\bOSC\b|\bASC\b|\bAMF\b|Autorit\w+\s+des\s+march|"
    r"securities\s+commission|securities\s+regulator|\bCIRO\b|\bIIROC\b|Investment\s+(?:Industry|Regulatory)\s+Organization|\bregulator\w*\b|\bregulatory\s+review\b|"
    r"continuous\s+disclosure\s+review|\bat\s+the\s+request\s+of\b|\bas\s+a\s+result\s+of\s+(?:a|its|their)\s+review\b|\bstaff\s+of\s+the\b|"
    r"\bExchange\s+(?:has\s+)?(?:requested|review\w*)\b|\bnon-?compliant\b|\bnot\s+(?:in\s+)?complian\w+\b|\bNational\s+Instrument\s+43-?101\b|\bNI\s*43-?101\b")

_V11_SAMPLE = re.compile(
    r"(?i)\bsampl(?:e|es|ed|ing)\b|\btrench(?:es|ing|ed)?\b|\bchannel\s+(?:sampl\w*|cuts?|results?)\b|\bchip[-\s]channel\b|\bgrab\b|\b(?:rock\s+)?chips?\s+sampl\w*|"
    r"\bsoil\b|\btill\b|\bprospecting\s+(?:results?|program|samples?|returns?)\b|\bstripping\b")
_V11_DRILLISH = re.compile(
    r"(?i)\bdrill\w*\b|\bholes?\b|\bintercept\w*\b|\bcores?\b|\bDDH\b|\bRC\b|\bdiamond\s+drill\w*\b|\bboreholes?\b|\bwells?\b|"
    r"(?<!trench\s)(?<!trenches\s)(?<!channel\s)\bintersect\w*\b")

_V11_ROYCO = re.compile(
    r"\b(?:Orogen|Electric|Elemental(?:\s+Altus)?|Osisko\s+Gold|OR|Sandstorm\s+Gold|EMX|Ecora|Versamet|Vox|Empress|Sailfish|Trident|"
    r"Noranda|Music|Metalla|Maverix|Taurus|Labrador\s+Iron\s+Ore|Sprott\s+Streaming\s+(?:and|&))\s+Royalt(?:y|ies)"
    r"(?:\s+(?:&|and)\s+Streaming)?(?:\s+(?:Corp(?:oration)?|Inc|Ltd|Limited|PLC|Co|AG|Group)\b\.?)?|"
    r"\b(?-i:[A-Z][\w'&\-]*)(?:\s+(?-i:[A-Z][\w'&\-]*)){0,2}\s+Royalt(?:y|ies)(?:\s+(?:&|and)\s+Streaming)?\s+(?:Corp(?:oration)?|Inc|Ltd|Limited|PLC|AG)\b\.?|"
    r"\bRoyalties\s+Inc\b\.?|"
    r"(?:^|\band\s+)NSR(?=\s+(?:Announces?|Announce|Resources|Inc|Corp|Provides?|Reports?|Completes?)\b)")

_V11_ROY_DEAL = re.compile(
    r"(?i)\btransactions?\b|\bdeals?\b|\bpartnership\b|\bnet\s+profits?\s+interest\b|\bNPI\b|\bfinancing\b|\bfunding\b|\binvestments?\b|\bstreams?\b|\bpurchase\s+agreement\b|"
    r"\bsells?\s+(?:a\s+|an\s+|its\s+)?(?:(?!shares?\b)[\w\-]+\s+){0,3}?(?:royalt|NSR|stream)|\bgrants?\s+(?:a\s+|an\s+)?(?:[\w\-%.]+\s+){0,3}?(?:royalt|NSR)")

_V11_ROY_SUBJECT = re.compile(
    r"(?i)\b(?!NSR\b)(?:[\w'&\-]+\s+){0,2}Royalt(?:y|ies)(?:\s+(?:&|and)\s+Streaming)?(?:\s+(?:Corp(?:oration)?|Inc|Ltd|Limited|PLC|AG)\b\.?)?\s*"
    r"(?:\([^)]{0,40}\)\s*)?(?:Reports?|Announces?|Records?|Provides?|Receives?|Acquires?|Completes?|Closes?|Declares?|Files?|Publishes?|Issues?|"
    r"Enters?|Achieves?|Delivers?|Increases?|Adds?|Expands?|Signs?|Purchases?|Updates?|Continues?|Confirms?|Posts?|Generates?)\b")

_V11_ECO_DELIVERED = re.compile(
    r"(?i)\bNPV\w*\b|\bIRR\b|\bpayback\b|\b(?:after|pre)[-\s]tax\b|\bpositive\s+(?:results\s+(?:of|from)\s+)?(?:the\s+)?(?:PEA|PFS|FS|DFS|BFS|feasibility|pre-?feasibility|preliminary\s+economic|economic|scoping)\b|"
    r"\b(?:announc\w+|reports?|complet\w+|deliver\w+|releas\w+|files?|filed|results\s+of|outlines?|unveils?)\s+(?:the\s+|an?\s+|its\s+)?(?:updated\s+|positive\s+|robust\s+|independent\s+)?"
    r"(?:PEA|PFS|DFS|BFS|feasibility|pre-?feasibility|preliminary\s+economic|economic\s+(?:study|assessment)|scoping\s+study)\b")
_V11_DRILL_RESULT = re.compile(
    r"(?i)\bintercept\w*\b|\bintersect\w*\b|\bdrill(?:s|ed|ing)?\b[^\n]{0,60}?\b(?:g/t|%|ppm|metres?|m\b|results?)|\bholes?\b[^\n]{0,60}?\b(?:g/t|%|ppm|metres?|m\b)|"
    r"\b\d[\d.,]*\s*(?:g/t|gpt|%)\b[^\n]{0,20}?\bover\b")


def _v11_refire(h: str) -> list[str]:
    """What the headline alone earns (no body), through the same chain categorize() uses."""
    h = re.sub(r"\s+", " ", h).strip()
    if not h:
        return []
    cats, rec = categorize_v7(h, "")
    return add_v10_tags(add_v9r_tags(add_v8_tags(cats, h, rec), h, rec), h, rec)


def _v11_blank(rx, h: str) -> str:
    return rx.sub(" ", h)


def v11_fix(cats: list[str], headline: str | None, recovered: str | None = None, body: str | None = None) -> list[str]:
    """TAGFIX_V1: remove tags the audit found wrong (and add the tag that fits), headline-scoped."""
    h = norm_head(headline)
    if (not h or is_hollow(h)) and recovered:
        h = norm_head(recovered)
    if not h or _DISCLAIMER_HEADLINE_V8.search(h):
        return list(cats)
    new = list(cats)
    add, drop = set(), set()
    memo = {}

    def still(rx, tag):
        key = id(rx)
        if key not in memo:
            memo[key] = _v11_refire(_v11_blank(rx, h))
        return tag in memo[key]

    MNA, OPT, ACT, CAP, REG, LST, FNS, PER, MKT = ("Mergers & Acquisitions", "Property Options & Staking", "Corporate Actions",
                                                  "Share Capital & Compensation", "Regulatory & Compliance", "Listings & Exchange",
                                                  "Financials", "Permits & Approvals", "Marketing Announcement")
    DRL, SMP, ROY, ECO = "Drill Results", "Sampling & Geoscience Results", "Royalties & Streams", "Economic Studies"
    # 1. option / earn-in / staking deals: Property Options only
    if MNA in new and _V11_OPT.search(h) and not _V11_OUTRIGHT.search(h) and (OPT in new or _is_option_land(h)):
        drop.add(MNA); add.add(OPT)
    # 2. buybacks: Share Capital (and not an exchange "permit")
    if _V11_BUYBACK.search(h):
        add.add(CAP)
        if ACT in new and not still(_V11_BUYBACK, ACT): drop.add(ACT)
        if PER in new and not still(_V11_BUYBACK, PER): drop.add(PER)
    # 3. other Corporate Actions mistakes
    for rx, to in ((_V11_SEMI, REG), (_V11_YEAREND, FNS), (_V11_SYMBOL, LST)):
        if ACT in new and rx.search(h) and not still(rx, ACT):
            drop.add(ACT); add.add(to)
    if _V11_EWR.search(h) and not _V11_OUTRIGHT.search(h):
        add.add(REG)
        if ACT in new: drop.add(ACT)
        if MNA in new: drop.add(MNA)
    # 4. MCTO / late filing: Regulatory, not Listings (and not Financials unless something was filed)
    if _V11_LATE.search(h):
        add.add(REG)
        if LST in new and not still(_V11_LATE, LST): drop.add(LST)
        if FNS in new and not _v11_filed(h): drop.add(FNS)
    # 5. index inclusions / listing anniversaries -> Marketing; market-activity statements are not Listings
    if LST in new and _V11_INDEX.search(h) and not still(_V11_INDEX, LST):
        drop.add(LST); add.add(MKT)
    if LST in new and _V11_MKTACT.search(h) and not still(_V11_MKTACT, LST):
        drop.add(LST)
    # 6. exchange approvals and DTC eligibility are not permits
    if PER in new and _V11_DTC.search(h):
        add.add(LST)
        if not still(_V11_EXCH_APPROVAL, PER): drop.add(PER)
    if PER in new and _V11_EXCH_APPROVAL.search(h) and not still(_V11_EXCH_APPROVAL, PER):
        drop.add(PER)
    # 7. a company correcting its own release: no Regulatory unless a regulator is in the story
    #    (needs the opening text: most "clarifies disclosure" releases were asked for by a regulator)
    if (REG in new and REG not in add and body and body.strip() and _V11_CORR.search(h) and not _V11_REGULATOR.search(h)
            and not _V11_REGULATOR_BODY.search(body[:2500]) and not still(_V11_CORR, REG)):
        drop.add(REG)
    # 8. surface / trench / channel sampling is Sampling, not Drill Results
    if DRL in new and _V11_SAMPLE.search(h) and not _V11_DRILLISH.search(h):
        drop.add(DRL); add.add(SMP)
    # 9. royalty words that are only a company's name
    #    (only when the name was the reason: the full headline earns Royalties, the headline without the name does not,
    #    and it is not a deal with the royalty company)
    #    and not the royalty company's own release ("Vox Royalty Reports Record 2025 Results")
    if (ROY in new and _V11_ROYCO.search(h) and not _V11_ROY_DEAL.search(h) and not _V11_ROY_SUBJECT.search(h)
            and ROY in _v11_refire(h) and ROY not in _v11_refire(_V11_ROYCO.sub("The company", h))):
        drop.add(ROY)
    # 10. a study named as a place in a drill headline ("... Below the PEA Pit")
    if ECO in new and DRL in new and _V11_DRILL_RESULT.search(h) and not _V11_ECO_DELIVERED.search(h):
        drop.add(ECO)
    add -= drop
    res = (set(new) - drop) | add
    if not add and not drop:
        return list(cats)
    if len(res) > 1:
        res.discard("Corporate Updates")
    if not res:
        # nothing left: take what the headline earns without the phrase that was wrong
        for v in memo.values():
            res |= {c for c in v if c not in drop and c != "Corporate Updates"}
        if not res:
            res = {"Corporate Updates"}
    return [c for c in CATEGORIES if c in res] + [c for c in cats if c not in CATEGORIES and c in res]


# ===========================================================================
# v12 tag fixes (TAGFIX_V2, 2026-09-27). The rest of the suggestions made after the tag-precision audit,
# approved by Justin in order:
#   (2) a company's NAME is not news: tags that only a watchlist company name earns are dropped;
#   (3) company STAGE: Production Results only for producers/royalty companies (or a headline with production
#       figures), Mine Development & Operations only for developers/producers (or a mine/mill/plant headline);
#   (4) the OPENING SENTENCE: a release still left in Corporate Updates is re-read from the clause after
#       "is pleased to announce ...", through the same headline rules, and takes the tags that rules find
#       there (the tags whose headline rules held up on opening sentences);
#   (5) a CONFLICT TABLE: when two tags fire together, the weaker one goes unless the headline confirms it;
#   (6) PROOF and PLANS: Resource Estimates / Economic Studies / Metallurgy / Mine Development need the thing
#       itself, not a plan, a potential or a report about something else.
# Runs after v11_fix(). Like v11, a tag is only removed when the phrase that earned it is the problem.
# ===========================================================================
import os as _v12_os
import json as _v12_json

# --------------------------------------------------------------- (5) conflict table + (6) plans / proof
_V12_PROD_WORDS = re.compile(
    r"(?i)\bproduces\b|\bproduced\b|\bproduction\s+of\s+[\d,.]|\b(?:gold|silver|copper)\s+equivalent\s+ounces\b|\bAu\s*Eq\s+oz|\bAgEq\s+oz|\bGEOs?\b|"
    r"\b(?:record|quarterly|annual|monthly)\s+(?:gold\s+|silver\s+)?production\b|\b\d[\d,.]*\s*(?:k|thousand|M|million)?\s*(?:gold\s+|silver\s+)?(?:oz|ounces)\b(?![^\n]{0,30}\bresources?\b)")
_V12_MRE = re.compile(
    r"(?i)\b(?:mineral\s+)?resources?\s+estimates?\b|\bMREs?\b|\b(?:indicated|inferred|measured)\b|\bmineral\s+reserves?\b|\breserves?\s+(?:and\s+resources?|estimate|update)\b|"
    r"\bresources?\s+(?:update|increase|grows?|expan\w+\s+to|of\s+\d)|\b\d[\d.,]*\s*(?:M|million)\s*(?:oz|ounces|tonnes|t|lbs|pounds)\b[^\n]{0,40}\bresources?\b|\bmaiden\s+(?:mineral\s+)?resource\b|"
    r"\bupdated\s+(?:mineral\s+)?resource\b|\bupdat\w+\s+(?:mineral\s+)?resources?\b|\bresources?\s+(?:statement|model)\b|\bJORC\b|\bM\s*&\s*I\b|\b(?:doubl\w+|tripl\w+|increas\w+|expan\w+|grow\w*|upgrad\w+)\b[^\n]{0,30}\bresources?\b|\bcompliant\s+(?:mineral\s+)?resources?\b|\b43-?101\s+(?:mineral\s+)?resources?\b|"
    r"\b(?:expan\w+|increas\w+|maiden|updated|upgrad\w+|doubl\w+|new)\s+(?:mineral\s+)?reserves?\b|\bmaiden\s+[A-Z][\w\-]*(?:\s+[A-Z][\w\-]*){0,2}\s+resources?\b")
_V12_MRE_HARD = re.compile(r"(?i)\b(?:indicated|inferred|measured)\b|\bM\s*&\s*I\b|\b\d[\d.,]*\s*(?:M|million|billion|k|thousand)?\s*(?:oz|ounces|tonnes|lbs|pounds)\b|\bMREs?\b|\bJORC\b")
_V12_MRE_BODY = re.compile(r"(?i)\b(?:indicated|inferred|measured)\s+(?:and\s+\w+\s+)?(?:mineral\s+)?resources?\b|\bmineral\s+resource\s+estimate\b|\bresource\s+estimate\b|"
                           r"\bmineral\s+reserves?\b|\bmineral\s+resources?\b|\bMREs?\b")
_V12_NEGATED = re.compile(r"(?i)\b(?:no|not|nor|without|neither)\b[^.]{0,25}$")


def _v12_body_has_estimate(body):
    b = body[:2500]
    return any(not _V12_NEGATED.search(b[max(0, m.start() - 30):m.start()]) for m in _V12_MRE_BODY.finditer(b))
_V12_MRE_DELIVERED = re.compile(
    r"(?i)\b(?:announc\w+|reports?|reported|deliver\w+|complet\w+|releas\w+|publish\w+|unveil\w+|declares?|outlines?|files?|filed|increases?|expands?|doubles?|grows?|upgrades?|provides?)\b"
    r"[^\n]{0,60}?\b(?:mineral\s+)?(?:resources?|reserves?|MRE)\b|\b(?:indicated|inferred|measured)\s+(?:and\s+(?:indicated|inferred)\s+)?(?:mineral\s+)?resources?\s+of\b|"
    r"\b\d[\d.,]*\s*(?:M|million|billion|k|thousand)?\s*(?:oz|ounces|tonnes|t|lbs|pounds)\b|\b(?:indicated|inferred|measured)\b")
_V12_RES_PLAN = re.compile(
    r"(?i)\bresource\s+(?:potential|growth|expansion|conversion|upside|definition\s+drill\w*)\b|\bpotential\s+to\s+(?:upgrade|expand|grow|increase|add)\b|"
    r"\b(?:plans?|planned|expects?|expected|upcoming|towards?|in\s+preparation\s+for|to\s+support|will\s+support|to\s+(?:update|deliver|complete|publish|reinstate))\b[^\n]{0,50}\b(?:resource|reserve|MRE)s?\b|"
    r"\b(?:resource|reserve|MRE)s?\s+(?:estimates?\s+|updates?\s+)?(?:is\s+|are\s+|now\s+)?(?:expected|planned|scheduled|underway|in\s+progress|on\s+track)\b|\bresource\s+development\s+agreement\b")
_V12_TECH_REPORT = re.compile(r"(?i)\btechnical\s+reports?\b|\b43-?101\s+(?:technical\s+)?report\b")
# "files technical report to support the ... mineral resource estimate": the estimate exists; the report backs it
_V12_REPORT_SUPPORTS = re.compile(r"(?i)\b(?:to\s+support|supporting|in\s+support\s+of)\b[^\n]{0,60}\b(?:resources?|reserves?|MRE)\b")
_V12_STUDY = re.compile(r"(?i)\b(?:PEA|PFS|DFS|BFS|feasibility|pre-?feasibility|preliminary\s+economic|scoping\s+study|economic\s+(?:study|assessment))\b")
_V12_DRILLWORD = re.compile(r"(?i)\bdrill\w*\b|\bholes?\b|\bintercept\w*\b|\bintersect\w*\b|\bDDH\b|\bRC\b|\bcores?\b|\bboreholes?\b")

_V12_OFFTAKE = re.compile(
    r"(?i)\bofftakes?\b|\boff[-\s]takes?\b|\b(?:supply|sales?|purchase|distribution|toll\s+milling|toll\s+processing|marketing)\s+(?:agreement|contract|arrangement|deal|term\s+sheet|MOU)s?\b|"
    r"\b(?:concentrate|ore)\s+(?:purchase|sales?)\b|\btoll\s+mill\w*\b|\bsecure\s+(?:long[-\s]term\s+)?supply\b")
_V12_JVREAL = re.compile(
    r"(?i)\b(?:form|forms|formed|forming|enter\w*|sign\w*|creat\w*|establish\w*|terminat\w*|dissolv\w*|increas\w*|earn\w*|acquir\w*|consolidat\w*|amend\w*|formation|restructur\w*|"
    r"exercis\w*|elect\w*|transfer\w*|sell\w*|sale|buy\w*|dilut\w*|agreement|definitive|binding|term\s+sheet|letter\s+of\s+intent|LOI|MOU|memorandum)\b")
_V12_JV_CONTEXT = re.compile(r"(?i)\b(?:JV|joint[-\s]venture)\s+(?:partner|project|property|properties|projects|area|claims?|programs?|budget)\b|\b(?:JV|joint[-\s]venture)\s+partner'?s?\b|\bthe\s+[A-Z][\w\-]+\s+JV\b|\bJV\s*$|\bJV\)|\bJVs\b")
_V12_MEMBERSHIP = re.compile(r"(?i)\bjoins?\b[^\n]{0,60}\b(?:association|alliance|institute|consortium|council|chamber|network|federation|coalition|forum|society|group)\b|\baccepted\s+into\b[^\n]{0,40}\bconsortium\b|\bbecomes?\s+(?:a\s+)?member\b")

_V12_PLANT_OPS = re.compile(
    r"(?i)\b(?:commission\w*|construct\w*|heat[-\s]up|start[-\s]?up|throughput|expansion|refurbish\w*|restart\w*|re-?start\w*|build\w*|completes?\s+construction|arrival\s+of\s+equipment|"
    r"launch\w*|operations?|operating|shipments?|ships|toll\s+mill\w*|EPCM|selects?|hires?|payment|rezoning|site|fabricat\w*|order\w*|purchas\w*)\b")
_V12_PLANT_WORD = re.compile(r"(?i)\b(?:plant|mill|smelter|refinery|facility|facilities|circuit|concentrator|ore[-\s]sorter|crusher|processing\s+(?:plant|facility|centre|center|hub))s?\b|\bconcentrate\b")
_V12_METTEST = re.compile(
    r"(?i)\bmetallurg\w*\s+(?:test\w*|results?|stud\w+|program\w*|work|recover\w*|performance|characteri[sz]\w*|optimi[sz]\w*|breakthrough)\b|\brecover(?:y|ies)\s+(?:of|rates?|tests?|results?|up\s+to|above|over|exceed\w*|improv\w*)\b|"
    r"\b\d[\d.]*\s*%\s+(?:gold\s+|silver\s+|copper\s+|lithium\s+)?recover\w*\b|\btest\s?work\b|\bflowsheet\b|\bleach\s+(?:tests?|results?|columns?|testing)\b|\bcolumn\s+(?:tests?|leach)\b|\bbench[-\s]scale\b|"
    r"\bpilot\s+(?:plant\s+)?(?:tests?|testing|program|results?|campaign|run)\b|\bbeneficiation\b|\bflotation\s+(?:tests?|results?|testing)\b|\bmineralog\w+\b|\bprocess\s+(?:test|development|optimi[sz]ation)\b|"
    r"\b(?:pilot|demonstration|demo)\s+(?:plant|facility|scale)\b[^\n]{0,60}\b(?:operat\w+|results?|program\w*|campaign|runs?|commission\w*|restart\w*)\b|"
    r"\b(?:operat\w+|results?|program\w*|campaign|completion\s+of\s+commissioning|restart\w*|commission\w*)\b[^\n]{0,60}\b(?:pilot|demonstration|demo)\s+(?:plant|facility)\b|"
    r"\b(?:pilot|demonstration|demo)\s+(?:plant|facility)\b[^\n]{0,60}\b(?:commissioned|confirm\w*|successful\w*|produc\w+|installed\s+at\b[^\n]{0,30}\blab)|\btesting\s+lab\w*\b|\btest(?:ing|s)\b|\bgrind\w*\b|\bgravity\s+(?:recover\w*|separation|concentrat\w*)\b|\bextraction\s+(?:tests?|technology|results?|process)\b|\bupgrad\w+\b[^\n]{0,30}\b(?:concentrate|grade)\b|\bassay\w*\s+of\s+concentrate\b")
_V12_MET_NAME = re.compile(r"(?i)\bmetallurg\w*\s+(?:holes?|drill\w*)\b|\bmetallurg\w*\s+samples?\s+assays?\b|\bInstitute\s+of\s+Mining,?\s+Metallurgy\b|\bMetallurgists\b|\bCIM\b|\bMetallurgical\s+(?:Society|Institute|Association)\b")
_V12_BULK_PERMIT = re.compile(r"(?i)\bbulk\s+sampl\w*\b[^\n]{0,60}\b(?:permit\w*|application|approv\w*|licen[cs]\w*)\b|\b(?:permit\w*|application|approv\w*)\b[^\n]{0,60}\bbulk\s+sampl\w*\b")

_V12_MILESTONE = re.compile(
    r"(?i)\bfirst\s+(?:gold\s+|silver\s+|dor[eé]\s+)?pour\b|\b(?:initial|trial|inaugural)\s+(?:gold\s+)?pour\b|\bfirst\s+(?:gold|silver|ore|production)\b(?!\s+(?:sales?|shipment))|"
    r"\b(?:restart\w*|re-?start\w*|resum\w+|reopen\w*|recommenc\w*)\b|\bcommenc\w+\s+mining\b|\bahead\s+of\s+(?:first\s+)?production\b|\btowards?\s+production\b|\bpath\s+to\s+production\b")
_V12_PROD_FIGURES = re.compile(
    r"(?i)\b\d[\d,.]*\s*(?:k|thousand|M|million)?\s*(?:oz|ounces|tonnes|t|lbs|pounds|GEOs?|AuEq|AgEq|carats|wmt|dmt)\b|\bproduction\s+(?:results?|of|was|totall?ed|up|down|increase|guidance|report|update)\b|"
    r"\b(?:Q[1-4]|first|second|third|fourth|quarter\w*|annual|full[-\s]year|fiscal|monthly|record)\b[^\n]{0,40}\bproduc\w+\b|\bproduc\w+\b[^\n]{0,30}\b(?:Q[1-4]|quarter|year|month|record)\b|"
    r"(?<!financial\sand\s)\boperational\s+results\b|\bproduction\s+(?:summary|rate|levels?)\b|\btargeted\s+production\b|\bnameplate\b|\bthroughput\b|"
    r"\b(?:revenue|sales)\s+from\b|\$[\d,.]+\s*(?:k|M|million)?\s+(?:in\s+)?revenue\b|\bconcentrate\s+(?:sales?|orders?)\b|\border\s+of\s+[\w\s]{0,20}concentrate\b")
_V12_RESTART = re.compile(r"(?i)\b(?:restart\w*|re-?start\w*|resum\w+|reopen\w*|recommenc\w*)\b")
_V12_ROYALTY_PAYMENT = re.compile(r"(?i)\b(?:advance\s+)?royalty\s+payments?\b")
_V12_RESULTS_NOTICE = re.compile(r"(?i)\b(?:to|will)\s+(?:release|report|issue|announce|publish)\b[^\n]{0,60}\b(?:production|results)\b|\bproduction\s+results\s+(?:release\s+)?(?:date|timing)\b")

_V12_LTR_STRATEGY = re.compile(r"(?i)\b(?:corporate|strategic|business)\s+(?:strategy|plan|update|priorities|direction|vision)\b|\bstrategic\s+(?:update|overview|plan)\b|\bupdate\s+to\s+shareholders\b|\bvision\s+for\b")
_V12_LTR_REAL = re.compile(r"(?i)\bletter\b|\byear[-\s]in[-\s]review\b|\b(?:review|recap)\s+of\s+(?:20\d\d|the\s+year)\b|\b20\d\d\s+(?:year\s+)?(?:in\s+review|review|highlights|achievements|accomplishments|recap)\b|"
                           r"\b(?:outlook|objectives|priorities|milestones|catalysts|goals)\s+for\s+(?:20\d\d|the\s+(?:year|coming\s+year))\b|\bmessage\s+(?:from|to)\b|"
    r"\b20\d\d\s+(?:corporate\s+)?(?:outlook|objectives|priorities|goals|milestones)\b|\b(?:strategy|plan|objectives)\s+for\s+20\d\d\b|\bstrategic\s+direction\b|\byear[-\s]end\s+update\b|\bannual\s+report\b|\bupdate\s+on\s+20\d\d\s+activities\b")
_V12_OUTLOOK_ONLY = re.compile(r"(?i)\boutlook\b")

_V12_CMT_GEOLOGY = re.compile(r"(?i)\bcomments?\s+on\s+(?:the\s+)?(?:geology|drilling|drill\s+program|mineralization|results|assays?|exploration|progress|[\w\-]+\s+(?:drilling|project|campaign|program))\b")
_V12_CMT_WRONG = re.compile(r"(?i)\backnowledges?\s+(?:the\s+)?passing\b|\breceives?\s+(?:[\w\-]+\s+){0,2}comments\b|\brespond\w*\s+to\s+[^\n]{0,40}\bcall\s+for\b|\bcomments?\s+on\s+(?:its\s+)?prior\s+(?:technical\s+)?disclosure\b|"
                           r"\backnowledges?\s+(?:[\w\-]+\s+){0,3}(?:assistance|funding|grant|support)\s+from\b|\bin\s+response\s+to\s+(?:a\s+)?(?:shareholder\s+)?requisition\b")
_V12_CAP_REAL = re.compile(r"(?i)\bstock\s+options?\b|\bincentive\b|\bRSUs?\b|\bDSUs?\b|\bshares?\s+(?:issued|issuance|for|in\s+lieu)\b|\bissu\w+\s+(?:of\s+)?(?:\d[\d,]*\s+)?(?:common\s+)?shares\b|\bwarrants?\b|"
                          r"\bshare\s+capital\b|\bconsolidation\b|\bissues?\b[^\n]{0,40}\bshares\b|\bdebt\s+settlement\b|\bshares?\s+for\s+debt\b|\bunits?[-\s]for[-\s]|\bescrow\b|\bbuy[-\s]?back\b|\bNCIB\b|\bissuer\s+bid\b|\bcompensation\b|\bshare\s+purchase\s+plan\b|\block[-\s]?up\b|\bvoting\s+rights\b")
_V12_OPT_DEAL = re.compile(r"(?i)\boption\s+(?:agreement|to\s+purchase|payment|on|over)\b|\bproperty\s+option\b|\bearn[-\s]?in\b|\blease\s+and\s+option\b|\boption\s+payment\b")
_V12_RESULTS_CALL = re.compile(r"(?i)\b(?:webinar|conference\s+call|investor\s+call|earnings\s+call|call)\b[^\n]{0,60}\b(?:results|quarterly\s+report|half[-\s]year|annual\s+report)\b|"
                               r"\b(?:results|quarterly\s+report|half[-\s]year)\b[^\n]{0,60}\b(?:webinar|conference\s+call|investor\s+call|call)\b")
_V12_MKT_REAL = re.compile(r"(?i)\bpresent\w*\s+at\b|\bconference\s+(?:presentation|participation)\b|\binvestor\s+(?:conference|event|show|day)\b|\bmarketing\b|\bawareness\b|\binvestor\s+relations\b|\bIR\s+(?:firm|services|agreement)\b|\bnamed\s+to\b|\baward\b")
_V12_STATUS_LATE = re.compile(r"(?i)\b(?:status|filings?)\s+update\s+(?:on|regarding)?\s*(?:its\s+|the\s+)?(?:annual|interim|audited)\b|\bannual\s+filings\s+update\b")
_V12_PER_DEAL = re.compile(r"(?i)\b(?:competition|anti-?trust|FCC|Investment\s+Canada|foreign\s+investment|shareholder|court|TSX|TSXV|TSX\s+Venture|exchange|CSE|OTC\w*|Nasdaq|NYSE)\s+(?:final\s+)?(?:approvals?|clearance|acceptance)\b|"
                          r"\bapprov\w+\s+(?:to\s+(?:begin|commence|start)\s+trading|for\s+(?:listing|trading))\b|\b(?:final|conditional)\s+approval\s+to\s+proceed\s+with\b[^\n]{0,40}\b(?:acquisition|expansion\s+of\s+[\w\-]+\s+property)\b")
_V12_PER_REAL = re.compile(r"(?i)\b(?:drill\w*|exploration|mining|environmental|water|work|construction|operating|mine|land\s+use|surface)\s+(?:permits?|licen[cs]es?|authori[sz]ations?)\b|\bEIS\b|\bEIA\b|\bROD\b|\brecord\s+of\s+decision\b|\bpermit\w*\b")
_V12_WARRANT_TERMS = re.compile(r"(?i)\bwarrants?\b[^\n]{0,40}\b(?:extension|extend\w*|expiry|repric\w*|accelerat\w*|amend\w*|term)\b|\b(?:extend\w*|repric\w*|accelerat\w*|amend\w*)\b[^\n]{0,40}\bwarrants?\b")
_V12_FIN_REAL = re.compile(r"(?i)\bprivate\s+placement\b|\bfinancing\b|\boffering\b|\bunits\b|\bproceeds\b|\bflow[-\s]through\b|\bbought\s+deal\b|\bincentive\s+program\b|\bexercise\s+of\s+warrants\b")
_V12_MNA_WRONG = re.compile(r"(?i)\bvertical\s+amalgamation\b|\bwholly[-\s]owned\s+subsidiary\b[^\n]{0,20}\bamalgamat\w+|\bshare\s+options\b|\bdirector\s+dealings\b|\bwarrant\s+repricing\b|\bname\s+change\b")
_V12_MNA_REAL = re.compile(r"(?i)\btransaction\b|\bclosing\s+of\b|\bacqui\w+\b|\bpurchas\w+\b|\bmerg\w+\b|\btake[-\s]?over\b|\barrangement\b|\bsale\b|\bsells?\b|\bsold\b|\bdivest\w*\b|\bbusiness\s+combination\b|\btender\b|\bRTO\b")
_V12_JV_FORM = re.compile(r"(?i)\b(?:form|forms|formed|formation|establish\w*|creat\w*|complete\w*)\b[^\n]{0,40}\b(?:joint\s+venture|JV)\b|\bjoint\s+venture\s+(?:transaction|agreement|company|formation)\b")
_V12_STAKE_ONLY = re.compile(r"(?i)\bstak(?:e|es|ed|ing)\b|\badditional\s+claims\b|\bclaims?\s+(?:package|block)\b|\bland\s+(?:package|position)\b")


def _v12_conflicts(cats, h, body=None):
    """(5) + (6): headline-scoped conflict and proof rules. Returns (drop, add)."""
    s = set(cats)
    drop, add = set(), set()
    RES, PRD, TEC, ECO, DRL, EXP, DEV, JV, MET, PER, LTR, CMT, CAP, OPT, MKT, FNS, FIN, DBT, MNA, REG, LST, SMP = (
        "Resource Estimates", "Production Results", "Technical Reports (NI 43-101)", "Economic Studies", "Drill Results",
        "Exploration Programs", "Mine Development & Operations", "Partnerships & JV", "Metallurgy & Processing",
        "Permits & Approvals", "Shareholder Letters & Outlook", "Company Commentary", "Share Capital & Compensation",
        "Property Options & Staking", "Marketing Announcement", "Financials", "Financings", "Debt & Credit Facilities",
        "Mergers & Acquisitions", "Regulatory & Compliance", "Listings & Exchange", "Sampling & Geoscience Results")
    # Resource Estimates needs an estimate: not production, not a report without one, not potential or plans
    if RES in s:
        mre = _V12_MRE.search(h)
        if _V12_PROD_WORDS.search(h) and not mre:
            drop.add(RES); add.add(PRD)
        elif _V12_TECH_REPORT.search(h) and not mre:
            # a technical report may carry an estimate the headline does not name: the opening text decides
            if _V12_STUDY.search(h):
                drop.add(RES); add.add(ECO)
            elif body and body.strip() and not _v12_body_has_estimate(body):
                drop.add(RES)
        elif (_V12_RES_PLAN.search(h) and not _V12_MRE_HARD.search(h)
              and not _V12_MRE_DELIVERED.search(_V12_RES_PLAN.sub(" ", h))
              and not (_V12_TECH_REPORT.search(h) and _V12_REPORT_SUPPORTS.search(h))):
            drop.add(RES)
        elif DRL in s and not mre:
            drop.add(RES)
    # Drill Results on a resource/technical-report filing or a staking release with no drill word
    if DRL in s and not _V12_DRILLWORD.search(h):
        if (RES in s and _V12_TECH_REPORT.search(h)) or (OPT in s and _V12_STAKE_ONLY.search(h)):
            drop.add(DRL)
    # Offtake / supply contracts are Mine Development, not Partnerships; a JV named only as context is not JV news;
    # joining an association is not a partnership
    if JV in s:
        if _V12_OFFTAKE.search(h) and not re.search(r"(?i)\bjoint[-\s]ventures?\b|\bJV\b|\bpartnership\b|\bstrategic\s+(?:alliance|partner\w*)\b|\bequity\b|\binvestment\b", h):
            drop.add(JV); add.add(DEV)
        elif (s & {EXP, DRL, SMP}) and _V12_JV_CONTEXT.search(h) and not _V12_JVREAL.search(h):
            drop.add(JV)
        elif _V12_MEMBERSHIP.search(h):
            drop.add(JV)
    # Metallurgy needs test work: plant building/running is Mine Development; "metallurgical holes", society names
    # and bulk-sample permits are not metallurgy
    if MET in s and not _V12_METTEST.search(h):
        if _V12_PLANT_WORD.search(h) and _V12_PLANT_OPS.search(h):
            drop.add(MET); add.add(DEV)
        elif _V12_MET_NAME.search(h):
            drop.add(MET)
        elif _V12_BULK_PERMIT.search(h):
            drop.add(MET)
    # Production Results needs production: a milestone without figures is Mine Development; a royalty payment or
    # a results-date notice is not production
    if PRD in s:
        if DEV in s and _V12_MILESTONE.search(h) and not _V12_PROD_FIGURES.search(h) and not (
                _V12_RESTART.search(h) and re.search(r"(?i)\bproduction\b", h)):
            drop.add(PRD)
        elif _V12_ROYALTY_PAYMENT.search(h) and not _V12_PROD_FIGURES.search(h):
            drop.add(PRD)
        elif _V12_RESULTS_NOTICE.search(h) and not re.search(r"(?i)\b\d[\d,.]*\s*(?:oz|ounces|tonnes|lbs)\b", h):
            drop.add(PRD)
    # Letters & Outlook: "strategy" / "outlook" / "update to shareholders" inside deal, results or meeting news
    if LTR in s and not _V12_LTR_REAL.search(h):
        if (s & {FIN, MNA, "Shareholder Meetings", "Corporate Actions", DBT, FNS, "Royalties & Streams", EXP, DRL})\
                and (_V12_LTR_STRATEGY.search(h) or _V12_OUTLOOK_ONLY.search(h)):
            drop.add(LTR)
    # Company Commentary: "comments on" its own drilling, a death, regulators' review comments, a call for projects
    if CMT in s:
        if _V12_CMT_WRONG.search(h):
            drop.add(CMT)
            if re.search(r"(?i)\breview\s+comments\b", h): add.add(PER)
            if re.search(r"(?i)\bpassing\b", h): add.add("Management Changes")
        elif _V12_CMT_GEOLOGY.search(h):
            drop.add(CMT); add.add(EXP)
    # Share Capital on property-option amendments that mention no shares
    if CAP in s and OPT in s and _V12_OPT_DEAL.search(h) and not _V12_CAP_REAL.search(h):
        drop.add(CAP)
    # Marketing on a results call already tagged Financials
    if MKT in s and FNS in s and _V12_RESULTS_CALL.search(h) and not _V12_MKT_REAL.search(h):
        drop.add(MKT)
    # Financials: a filing-status update is not financial results
    if FNS in s and _V12_STATUS_LATE.search(h) and not re.search(r"(?i)\bresults\b|\bfiles\b|\bfiled\b", h):
        drop.add(FNS); add.add(REG)
    # Permits: deal, court, exchange and trading approvals are not permits
    if PER in s and _V12_PER_DEAL.search(h) and not _V12_PER_REAL.search(_V12_PER_DEAL.sub(" ", h)):
        drop.add(PER)
        if re.search(r"(?i)\btrading\b|\blisting\b", h): add.add(LST)
    # Financings: warrant term changes are share capital (loans stay: convertible debentures and loans are an open scope question)
    if FIN in s and _V12_WARRANT_TERMS.search(h) and not _V12_FIN_REAL.search(h):
        drop.add(FIN); add.add(CAP)
    # M&A: internal reorganisations, option exercises, name changes; a JV formation is JV news
    if MNA in s and _V12_MNA_WRONG.search(h) and not _V12_MNA_REAL.search(_V12_MNA_WRONG.sub(" ", h)):
        drop.add(MNA)
    if MNA in s and JV in s and _V12_JV_FORM.search(h) and not _V12_MNA_REAL.search(h):
        drop.add(MNA)
    return drop, add
_V12_STAGE_SNAPSHOT = (  # MTP stage_from_descriptions.json (MTP_STAGE_DESC_V1, revised 2026-09-24), stage letter only
    "AA:E AAG:D AAN:A AAUC:P AAZ:E ABA:A ABC:E ABGO:E ABI:D ABM:E ABR:E ABRA:D ABX:P ABZ:E "
    "ACDC:E ACDX:E ACM:A ACRE:E ACS:E ADDY:A ADE:E ADON:E ADP:E ADY:A ADZ:E AE:E AEC:D AEF:A "
    "AEM:P AEMC:A AERO:E AFF:E AFM:P AFX:E AG:P AGA:A AGAG:A AGC:A AGH:E AGI:P AGLD:P AGMR:D "
    "AGX:P AHM:E AHR:E AIR:A AIS:E ALAR:E ALDE:A ALEX:E ALGR:E ALK:P ALM:E ALMA:E ALS:R ALT:E "
    "ALTA:A ALTH:E ALTN:E ALX:E AMAP:P AMC:A AMCO:E AME:D AML:E AMM:A AMQ:A AMX:D ANDC:E ANK:E "
    "ANOR:E ANT:E ANTL:E AORO:E APGO:A API:E APM:P APMI:E APN:E APX:E APXC:E ARA:D AREE:U ARG:P "
    "ARGL:E ARIC:A ARIS:P ARK:E ARL:E ARMY:E ARO:R ARQ:E ARS:U ARTG:P ARU:E ASE:P ASHL:E ASL:E "
    "ASM:P ASTR:E ATC:E ATHA:E ATLA:E ATMY:E ATOM:E ATX:A ATY:P AUAU:A AUCU:E AUEN:E AUEX:E AUGC:E "
    "AUM:A AUMB:D AUMC:E AUME:A AUMN:U AUOZ:A AUQ:E AURA:E AURM:E AURO:A AURR:E AUX:E AUXX:A AVE:E "
    "AVG:E AVL:D AVR:E AVU:A AVX:D AWCM:E AWE:E AWM:E AWR:E AWX:E AXN:E AXO:D AYA:P AZCU:E "
    "AZEM:E AZM:A AZR:A AZS:E AZT:E B:E BAC:U BAD:E BAG:A BAR:E BARU:A BAT:E BATT:E BATX:E "
    "BAU:A BAY:D BBB:E BCU:E BEA:E BEAR:E BEAU:E BEEP:E BEM:E BEX:A BFG:E BFM:E BG:E BGAU:A "
    "BGD:E BGF:E BGLD:E BGX:U BHS:D BIG:E BIGT:E BIRD:E BKI:D BKM:A BLDS:E BLLG:P BLST:E BM:E "
    "BMM:E BMR:P BMT:A BMV:E BNKR:D BNZ:E BOCA:E BOGO:P BOL:E BOLT:E BONE:A BOOM:A BPAG:E BPR:E "
    "BRAU:A BRAZ:E BRC:D BRO:A BRON:E BRS:E BRU:E BRVO:A BRW:E BSK:A BST:E BSX:D BTO:P BTR:A "
    "BTT:E BTU:E BUFF:D BULL:E BURY:E BVA:A BWR:E BY:E BYN:A BYRG:E BZ:A C:E CACR:A CAD:A "
    "CADY:A CAM:A CAMB:D CAMP:E CAN:E CANU:E CANX:E CAPR:A CAPT:A CASA:E CASC:E CAT:E CATX:E CBA:A "
    "CBG:E CBI:E CBLT:E CBR:D CC:E CCCM:A CCD:E CCI:A CCM:D CCMC:E CCMI:A CCMM:E CCO:P CD:E "
    "CDA:E CDB:E CDE:P CDN:E CDPR:D CELL:E CENT:A CERT:P CFE:A CG:P CGD:E CGG:P CGM:E CGNT:A "
    "CIA:P CIO:E CKG:A CLCH:D CLCO:R CLIC:E CLUS:E CLV:E CLZ:E CMCG:E CMET:E CMIL:E CMP:E CN:E "
    "CNC:D CNL:A CNRI:A CNT:A COCO:E COMT:E CONE:E COPR:E COR:D COS:E COSA:E CPAU:D CPER:E CPI:E "
    "CPL:A CPS:D CQR:E CQX:A CRB:E CRC:E CRCL:E CRD:E CRE:D CRG:E CRI:E CRIV:E CRPC:E CRTL:E "
    "CRUZ:A CS:P CSG:E CSQ:E CSR:E CTG:E CTGO:P CTM:A CTN:E CTV:D CUAU:E CUCU:E CUEX:E CUPA:E "
    "CUPR:E CUU:D CVB:D CVV:E CVW:R CXC:E CYG:A CZZ:E DAN:D DAU:A DBG:A DC:U DCOP:E DCY:E "
    "DEC:E DEF:A DEFN:A DEMC:E DEX:E DFR:E DG:E DGC:E DIAM:A DLP:A DLTA:E DMCU:E DML:D DMX:A "
    "DNG:P DNO:E DOS:E DPM:P DRC:E DRY:E DSV:P DTWO:E DYG:A EAGL:E EAM:A EATH:E EAU:E ECOR:R "
    "ECR:A ECU:A EDCU:A EDDY:E EDG:E EDGM:E EDM:D EDR:P EDV:P EFF:E EFR:P EGM:A EGR:E ELD:P "
    "ELE:R ELEC:R ELEF:P ELEM:D ELO:A ELR:P ELYX:E EM:E EMET:E EML:A EMM:D EMN:D EMNT:E EMO:A "
    "EMPR:R EMPS:A EMR:E ENDR:E ENEV:E ENRG:E EOM:E EONE:E EOX:D EPG:E EPL:E EPR:E EQTY:A EQX:P "
    "ERD:P ERDA:R ERKA:E ERO:P ESAU:D ESK:E ESM:A ESPN:E ESXR:E ETF:E ETG:D ETL:A ETR:A EU:P "
    "EVER:E EVI:E EVNI:A EVR:R EWK:U EXCL:E EXG:E EXN:D FAIR:A FAN:E FAS:E FAT:E FCI:E FDR:E "
    "FDY:A FEO:A FEX:E FF:D FFF:A FFM:A FFOX:E FFU:E FG:E FIN:E FINX:E FISH:R FL:D FLCN:D "
    "FLM:E FM:P FMAN:D FMM:E FMN:E FMR:E FMS:D FNAU:E FNI:A FNV:R FNX:E FOG:E FOMO:E FOR:A "
    "FOXT:A FPC:A FPX:D FRDM:E FRED:A FRG:D FRI:A FROG:E FSY:D FT:D FTEL:E FTJ:E FTUR:E FTZ:E "
    "FURY:A FUSE:E FUTR:E FUU:E FVI:P FVL:A FWM:E FWZ:D FYL:E GAL:D GAMA:E GAU:P GBML:E GBU:U "
    "GC:E GCC:E GCN:E GCOM:E GCP:E GCR:E GCU:P GCUC:E GDN:E GDP:E GEL:E GEMC:E GEMG:E GEN:E "
    "GENM:D GERA:E GFG:E GFT:E GG:P GGA:P GGAU:E GGC:E GGD:P GGI:E GGL:E GGLD:E GGM:A GGO:A "
    "GGR:E GGX:E GHL:E GHRT:E GIG:E GIGA:A GLAD:E GLB:E GLD:E GLDC:A GLDN:E GLDR:E GLDS:E GLO:D "
    "GMC:E GMIN:P GMR:E GMV:E GMX:R GNG:E GOCO:E GOH:E GOLD:A GOR:E GORO:P GOT:E GPAC:E GPG:A "
    "GPH:D GPM:E GPO:A GPS:E GQC:D GR:A GRAY:E GRBM:A GRC:A GRD:A GRDM:E GRG:E GRHK:A GRI:E "
    "GRL:E GRSL:A GRUN:E GRUV:E GRZ:E GSKR:A GSP:D GSPR:E GSR:A GSRI:E GSS:E GST:E GSTM:E GSTR:E "
    "GSVR:P GT:A GTC:E GTCH:A GUN:A GURN:E GVR:E GWM:A GX:E GXLD:E GXP:E GZD:E HAMR:E HAN:E "
    "HANS:E HAR:E HARD:E HART:E HAWK:E HAY:E HBM:P HCH:A HERC:E HHE:E HHH:E HI:D HLND:E HLU:E "
    "HM:E HML:E HMMC:P HPM:E HRK:E HRNY:E HSLV:D HSTR:P HTRC:A HUNT:E HVG:E HWG:E HWY:E HZ:E "
    "IAU:D ICG:E ICM:A IDEX:E IE:A IFOS:P IGO:A III:P ILC:A ILI:A IMG:P IMM:E IMR:E IN:E "
    "INFI:E INFM:E INTG:E INTR:E INXS:E IPT:P IRI:E IRR:E IRV:E ISO:A ISP:E ITH:D ITR:P IVN:P "
    "IVS:E IZN:E IZZ:E JADE:E JAG:P JAY:A JDN:E JG:E JJJ:U JJJJ:E JTWO:E JUGR:E JZR:R K:P "
    "KALO:E KAPA:E KARU:E KBRA:E KBX:E KC:D KCC:E KCLI:E KCP:E KDK:A KENY:E KFR:E KG:A KGC:E "
    "KGS:E KIB:E KING:E KIP:E KIRO:E KLD:E KLDC:E KNG:E KNOX:E KNT:P KOG:E KORE:D KRI:E KRIT:E "
    "KRN:D KRY:A KS:E KTN:A KTO:E KTRI:E KUYA:P KVM:E LA:A LAB:E LAC:D LAF:E LAI:E LALI:E "
    "LAM:D LAR:P LBNK:D LCE:D LCR:E LEAP:E LECR:E LEGY:E LEM:D LEO:D LEXT:E LFLR:D LFNT:E LG:D "
    "LGC:E LGD:D LGHT:E LGO:P LI:A LIBR:E LIF:R LIFT:A LINE:E LIO:P LION:E LIT:A LITH:A LIVE:E "
    "LMCU:A LME:E LMG:D LMR:A LMS:E LOD:A LORD:E LOT:E LP:E LPK:U LRA:A LSTR:E LTH:D LTHM:E "
    "LTNG:E LTX:E LUC:P LUCA:P LUG:P LUN:P LUNR:R LUXR:E LVG:D LVX:E LWR:E LXE:E LXM:E LYNX:E "
    "M:E MACK:E MAI:P MANN:E MANU:E MARI:D MASS:E MAU:D MAV:E MAX:E MAXM:E MAXX:U MBL:E MCC:E "
    "MCI:D MCL:E MD:E MDI:U MDM:E MEC:E MEDA:E MEGA:E MEK:E MEO:E MERC:E MERG:E METL:E MEX:A "
    "MFG:D MGA:E MGG:D MGM:A MGMA:E MILE:E MILI:E MINE:E MINK:E MJS:P MKA:D MKO:P MKR:E MLKM:E "
    "MLM:A MLO:E MLP:D MM:E MMA:E MMET:E MMG:A MMX:E MMY:P MN:A MNG:E MNO:D MNRG:E MOC:E "
    "MOG:E MOGL:E MOLT:E MOLY:D MON:E MONI:E MOO:E MOON:D MOX:R MQM:E MRZ:E MRZL:A MSA:P MSC:E "
    "MSG:A MSM:E MSR:A MSV:A MT:E MTA:R MTH:E MTS:E MTT:E MTTA:A MTX:E MUN:E MUR:A MUX:P "
    "MY:E MYR:E NAM:A NAME:E NAP:E NAR:E NATN:E NATO:E NAU:A NBLC:E NBRK:E NBY:A NCAU:A NCF:D "
    "NCP:A NCX:A NDM:D NED:E NEO:U NEV:E NEWD:E NEXG:D NEXM:A NEXT:P NEXU:A NEXX:E NFG:P NG:D "
    "NGC:P NGEX:A NICE:E NICN:E NICO:A NICU:P NILI:A NIM:P NINE:E NIO:D NIOB:E NIX:A NKG:A NKL:P "
    "NL:E NLR:E NMB:A NMC:D NMI:D NNX:E NOAL:A NOB:E NOBL:E NOM:A NOP:E NOR:E NOU:D NOVA:D "
    "NPR:E NQC:E NRC:R NRDX:E NRED:E NRM:A NRN:E NSG:E NSJ:E NSU:E NT:E NTB:E NTH:A NTMC:E "
    "NTX:E NUAG:D NUCA:E NUG:E NUKE:A NVLH:A NVO:A NVPC:A NVR:E NVRO:U NVT:E NVX:E NWI:A NWST:A "
    "NXE:D NXS:E NXU.X:U OBUL:E OCG:A OCO:A OGC:P OGG:A OGN:R OGW:E OLV:E OM:E OMG:A OMGA:E "
    "OMI:E OMM:D ONAU:A ONYX:E OOR:E OPHR:E OPW:E OR:R ORCL:R ORE:P ORGN:E OROG:E ORS:E ORV:P "
    "OSM:E OTMC:E OWLI:E OWN:E OZ:E PA:E PAAS:P PAT:E PATH:A PAU:E PBM:E PCA:E PCU:A PDI:P "
    "PDN:P PDQ:E PE:E PEAK:E PEMC:E PER:P PERU:E PEX:A PGA:E PGC:E PGDC:D PGE:A PGLD:D PGOL:R "
    "PGP:E PGR:E PGX:E PGZ:A PHD:E PHNM:A PHOS:D PINN:D PJX:E PLLR:E PLTO:E PLY:E PMAX:E PMC:E "
    "PMET:D PMI:E PML:A PNGC:D PNPN:A PNRG:E PNTR:E PONY:E POWR:E PPM:E PPP:E PPTA:D PPX:D PRCG:E "
    "PRG:E PRIZ:E PRNC:E PRR:E PRS:E PRU:P PSE:P PSIL:E PSVA:E PTM:D PTU:E PTX:E PUMA:E PUR:A "
    "PURE:E PURO:A PURR:E PWM:A PWRO:E PX:A QB:E QBAT:E QGR:A QIM:E QIMC:E QMC:E QQQ:E QREE:E "
    "QRO:E QTWO:A QURI:U QZM:E RAGE:A RAIN:U RAK:E RAMP:E RBZ:E RCK:D RCT:E RDG:E RDS:A RDU:A "
    "REDC:E REE:E REG:A RES:E REVX:E REX:A RFLX:E RFR:A RGC:E RGLD:E RGN:E RGR:E RI:R RIO:P "
    "RISE:E RJX.A:E RK:A RKL:E RKR:E RLGC:E RLYG:E RM:A RMD:E RME:E RMES:E RMI:E RML:P RMO:E "
    "RNCH:E ROAD:E ROAR:E ROCB:E ROCK:A ROS:D ROX:E RPX:A RRI:E RRRL:E RSG:E RSM:A RSMX:A RTE:E "
    "RTG:A RTH:A RTM:E RUA:A RUC:E RUSH:A RUU:E RVG:D RXM:A RYO:D RYR:E S:P SAE:E SAF:E "
    "SAG:E SAGA:E SAGE:A SALT:D SAM:P SAND:E SANU:E SAO:A SASK:E SASQ:E SAU:D SBI:P SBMI:E SCD:A "
    "SCLT:E SCM:E SCMI:D SCOT:A SCU:E SCV:E SCY:D SCZ:P SEA:A SEAG.X:E SEAS:E SEND:E SEVA:A SF:E "
    "SFR:D SGC:E SGD:A SGLD:A SGML:P SGO:D SGQ:P SGRO:E SGU:A SGZ:E SHL:E SHOW:E SI:D SICO:P "
    "SIEN:E SIG:A SILV:E SK:U SKE:D SKEL:E SKP:E SKRR:E SKUL:E SKYG:E SL:E SLA:E SLG:E SLI:D "
    "SLO:E SLR:A SLS:A SLV:E SLVR:D SLZ:E SM:P SMD:R SME:A SMET:E SML:P SMN:A SMP:A SMR:E "
    "SMY:A SNAG:E SNG:E SOI:A SOMA:P SPA:D SPC:A SPD:E SPMC:A SPRK:E SPX:E SR:D SRAN:E SRC:P "
    "SRI:E SRL:D SRQ:E SRS:E SSE:E SSRM:P SSV:A STAR:E STCU:E STE:E STGO:P STGX:E STK:E STLR:D "
    "STMN:E STND:E STNG:E STRM:E STS:D STUD:E STUV:E STW:E SUI:E SUM:R SUR:A SURG:A SUU:E SVB:A "
    "SVE:A SVG:E SVM:P SVRS:D SWA:E SWLF:E SX:E SXGC:E SXL:E SXTY:D SYG:E SYH:E SYN:E TAI:E "
    "TAJ:E TALA:D TANA:E TARG:E TAU:D TAUR:E TBK:E TBLL:E TCCM:E TCEC:A TCO:E TDG:A TECK:P TECT:E "
    "TERA:E TES:E TEX:E TFPM:R TG:E TGC:E TGII:E TGLD:E TGOL:A TGX:E THM:A THX:P TI:P TICO:E "
    "TIG:A TIGR:A TIN:A TITI:D TK:A TKO:P TLG:D TLO:P TMAS:A TMET:E TMIN:E TMQ:D TN:A TNGD:A "
    "TNR:R TOC:E TOM:E TONE:E TORC:E TORQ:E TOTC:E TR:E TRAC:E TRAN:A TRBC:E TRCG:E TRG:E TRO:A "
    "TRR:E TRS:E TRU:E TRX:P TSD:E TSG:D TSK:P TSLV:E TT:E TTG:E TTS:A TUD:A TUF:D TUNG:D "
    "TUO:E TVI:U TWO:E TWR:E TXG:P UCM:E UCU:U UG:E UGD:D UPPR:E URC:R URE:P URZ:E USA:P "
    "USCM:E USCU:A USGD:E USHA:E USLI:E UTWO:E UUU:E UX:E V:A VAU:A VC.X:U VCG:D VCT:U VCU:A "
    "VCV:E VENT:E VERT:E VG:A VGC:A VGD:E VGZ:D VIO:E VIPR:A VIZ:E VKG:E VLC:A VLD:E VLI:E "
    "VLLC:E VLTA:E VLX:A VMET:R VML:A VMS:E VMXX:A VO:A VOLT:E VOXR:R VRB:E VRDN:E VROY:R VRR:E "
    "VRTX:E VTEN:E VTT:A VUL:E VZLA:D VZZ:E W:E WAM:A WAU:E WBGD:E WCU:E WDGY:U WDO:P WEC:P "
    "WEST:A WEX:A WG:E WGF:A WGLD:E WGM:E WGO:A WGX:P WHN:A WHY:A WINS:E WISE:E WLF:A WM:A "
    "WMC:E WMK:D WML:E WMS:E WPG:E WPM:R WRLG:P WRN:A WRR:E WSK:E WSR:E WUC:U WVM:D XGC:A "
    "XIM:E XPLR:E XRI:E XTG:A XTM:E XXIX:A YARR:E YGT:A YMC:E YRB:A ZAC:E ZAU:E ZBNI:E ZEUS:E "
    "ZFR:D ZIGY:E ZLTO:E ZNG:A ZNX:E ZON:E "
)
_V12_STAGE = dict(p.split(":", 1) for p in _V12_STAGE_SNAPSHOT.split())

# --------------------------------------------------------------- (2) company names
_V12_SUFFIX_RX = re.compile(r"(?i)^(?:\s*,?\s+(?:Corp(?:oration)?|Inc|Ltd|Limited|Co|Company|PLC|LLC|S\.A|AG|NL|Group|Holdings)\b)*\.?")
_V12_SUFFIX_END = re.compile(r"(?i)(?:\s*,?\s+(?:Corp(?:oration)?|Inc|Ltd|Limited|Co|Company|PLC|LLC|S\.A|AG|NL|Group|Holdings)\.?)+\s*$")
_V12_NAME_COMMON = set(
    "gold silver copper metals metal mining mines minerals mineral resources resource energy exploration lithium uranium nickel "
    "critical ventures one and american golden battery lake royalties royalty pacific north canadian first discovery global "
    "materials international new strategic precious company power mountain star group graphite northern western clean blue iron "
    "ridge sun capital canada nevada terra the of".split())
_V12_TOK = re.compile(r"[\w'&\-]+")
_V12_NAME_TAGS = ("Drill Results", "Sampling & Geoscience Results", "Resource Estimates", "Exploration Programs",
                  "Mergers & Acquisitions", "Metallurgy & Processing")
_V12_NAMES = None


def _v12_names():
    """Watchlist company names (tickers.json next to the app), indexed by first word. Empty if the file is missing."""
    global _V12_NAMES
    if _V12_NAMES is None:
        idx = {}
        try:
            p = _v12_os.path.join(_v12_os.path.dirname(_v12_os.path.dirname(_v12_os.path.abspath(__file__))), "tickers.json")
            for t in _v12_json.load(open(p, encoding="utf-8")):
                core = _V12_SUFFIX_END.sub("", (t.get("name") or "").strip()).strip(" ,.")
                words = [w.lower() for w in _V12_TOK.findall(core)]
                if not words or (len(words) == 1 and (len(words[0]) < 5 or words[0] in _V12_NAME_COMMON)):
                    continue
                if all(w in _V12_NAME_COMMON for w in words):
                    continue
                idx.setdefault(words[0], set()).add(tuple(words))
        except Exception:
            idx = {}
        _V12_NAMES = {k: sorted(v, key=len, reverse=True) for k, v in idx.items()}
    return _V12_NAMES


def _v12_mask_names(h: str):
    idx = _v12_names()
    if not idx:
        return h, False
    toks = list(_V12_TOK.finditer(h))
    out, i, last, hit = [], 0, 0, False
    while i < len(toks):
        cands = idx.get(toks[i].group(0).lower())
        done = False
        for c in cands or ():
            n = len(c)
            if i + n <= len(toks) and tuple(t.group(0).lower() for t in toks[i:i + n]) == c and \
                    all(re.fullmatch(r"\s+", h[toks[j].end():toks[j + 1].start()]) for j in range(i, i + n - 1)):
                end = toks[i + n - 1].end()
                m = _V12_SUFFIX_RX.match(h[end:])
                end += m.end() if m else 0
                if h[end:end + 2] in ("'s", "’s"):
                    end += 2
                out.append(h[last:toks[i].start()]); out.append("The company"); last = end
                while i < len(toks) and toks[i].start() < end:
                    i += 1
                done = hit = True
                break
        if not done:
            i += 1
    out.append(h[last:])
    return "".join(out), hit


def _v12_name_drops(cats, h):
    """(2) tags the headline earns only through a watchlist company's name ("Visible Gold Mines Appoints New CFO")."""
    s = set(cats) & set(_V12_NAME_TAGS)
    if not s:
        return set()
    masked, hit = _v12_mask_names(h)
    if not hit:
        return set()
    full, bare = set(_v11_refire(h)), set(_v11_refire(masked))
    return {t for t in s if t in full and t not in bare}


# --------------------------------------------------------------- (3) company stage
_V12_BODY_TICKER = re.compile(r"\((?:[^()]{0,40}?)(?:TSX[\s\-.]?V(?:enture)?(?:\s+Exchange)?|TSXV|TSX|CSE|NEO)\s*[:\-]\s*([A-Z][A-Z0-9]{0,5}(?:\.[A-Z])?)\b")
_V12_MINE_WORD = re.compile(
    r"(?i)\bmines?\b|\bmill(?:s|ing|ed)?\b|\bplant\b|\bprocessing\b|\bpit\b|\bunderground\b|\bdecline\b|\bportal\b|\bheap\s+leach\b|\bconcentrat\w+\b|\bpour\w*\b|"
    r"\bproduc\w+\b|\bcommission\w*\b|\bconstruction\b|\bofftake\b|\boff[-\s]take\b|\btoll\b|\bshipments?\b|\bsmelter\b|\brefinery\b|\btailings\b|\bramp[-\s]?up\b|"
    r"\bstockpile\w*\b|\bore\b|\bdor[eé]\b|\bfacility\b|\bquarry\b|\bplacer\b|\bbulk\s+sampl\w*\b|\brefiner\w*\b|\bfirst\s+gold\b|"
    r"\b(?:restart\w*|re-?start\w*|resum\w+|suspen\w+|halt\w*|curtail\w*)\s+(?:(?:its|the|all|of)\s+)?(?:\w+\s+){0,2}operations\b|"
    r"\bfatal\w*\b|\baccident\w*\b|\bincident\w*\b|\binjur\w*\b|\bevacuat\w*\b|\bblockade\w*\b|\bflood\w*\b")
_V12_EXPL_WORD = re.compile(r"(?i)\bexplor\w+\b|\bdrill\w*\b|\bgeophysic\w*\b|\bsampl\w+\b|\bsurvey\w*\b|\bfield\s+(?:program|work|season)\b|\bprospect\w*\b|\btargets?\b")


def _v12_stage(ticker, body):
    t = (ticker or "").strip().upper()
    if not t and body:
        m = _V12_BODY_TICKER.search(body[:1200])
        t = m.group(1) if m else ""
    for suf in (".TO", ".V", ".CN", ".NE", ".T"):
        if t.endswith(suf):
            t = t[: -len(suf)]
            break
    return _V12_STAGE.get(t) or _V12_STAGE.get(t.split(".")[0]) if t else None


def _v12_stage_drops(cats, h, stage):
    """(3) Production Results only from producers / royalty companies unless the headline gives production figures;
    Mine Development only from developers / producers unless the headline names a mine, mill, plant or production."""
    drop, add = set(), set()
    if stage not in ("E", "A"):
        return drop, add
    s = set(cats)
    if "Production Results" in s and not _V12_PROD_FIGURES.search(h) and not _V12_MILESTONE.search(h):
        drop.add("Production Results")
    if "Mine Development & Operations" in s and not _V12_MINE_WORD.search(h):
        drop.add("Mine Development & Operations")
        if _V12_EXPL_WORD.search(h):
            add.add("Exploration Programs")
    return drop, add


# --------------------------------------------------------------- (4) the opening sentence
_V12_CO_DEF = re.compile(r"""\((?:[^()]{0,120}?)?(?:the\s+)?[“"”']{1,2}\s*(?:Company|Corporation|Issuer|Corp|we)\s*[“"”']{1,2}[^()]{0,120}\)""", re.I)
_V12_PLEASED = re.compile(r"(?i)^\W*(?:is|are|was)?\s*(?:very\s+)?(?:pleased|delighted|excited|proud|happy|thrilled)\s+(?:to\s+)?"
                          r"(?:announce|report|provide|present|share|update|confirm|disclose|advise|inform|release)\w*\s*(?:(?:that|on|an|a|the|its|with|further|shareholders|you)\s+)*")
_V12_LEAD_VERB = re.compile(r"(?i)^\W*(?:today\s+|has\s+)?(?:announce[sd]?|report(?:s|ed)?|provide[sd]?|confirm(?:s|ed)?|advise[sd]?)\s+(?:today\s+)?(?:that\s+)?(?:(?:an|a|the|its)\s+)?")
_V12_TODAY = re.compile(r"(?i)\b(?:announced|reported)\s+today\s+(?:that\s+)?")
_V12_FURTHER = re.compile(r"(?i)^\W*further\s+to\s+(?:its|the|our)\s+(?:[\w\-]+\s+){0,4}?(?:news|press)\s+releases?\s+(?:dated|of|issued\s+on)?\s*[^,]{0,40},\s*(?:the\s+company\s+)?")
_V12_APPOSITIVE = re.compile(r"(?i)^\W*(?:an?|one\s+of|the\s+(?:leading|largest|premier))\s")
_V12_NEWS_START = re.compile(r"(?i)\b(?:is|are)\s+(?:very\s+)?(?:pleased|delighted|excited|proud|happy|thrilled)\b|\b(?:announces|reports|announced|reported|provides|confirms)\b")
# the tags whose headline rules held up when run on opening sentences (hand-read sample, 2026-09-27)
_V12_LEDE_TAGS = ("Exploration Programs", "Sampling & Geoscience Results", "Financials", "Mine Development & Operations",
                  "Property Options & Staking", "Share Capital & Compensation", "Legal & Disputes",
                  "Permits & Approvals", "Management Changes", "Shareholder Meetings", "Debt & Credit Facilities",
                  "Production Results", "Economic Studies", "Corporate Actions",
                  "Regulatory & Compliance", "Technical Reports (NI 43-101)", "Royalties & Streams", "Listings & Exchange")


def opening_clause(body):
    """The clause after "<Company> (the "Company") is pleased to announce that ..." up to the first sentence end."""
    if not body:
        return None
    t = re.sub(r"\s+", " ", lede(body, 1500))
    m = _V12_CO_DEF.search(t[:700])
    if m:
        rest = t[m.end():]
    else:
        m2 = re.search(r"(?i)\bis\s+(?:very\s+)?(?:pleased|delighted|excited|proud|happy)\s+to\b", t[:700]) or _V12_TODAY.search(t[:700])
        if not m2:
            return None
        rest = t[m2.start():]
    rest = re.sub(r"^[\s,;:\-]*(?:\([^)]{0,80}\)[\s,;:\-]*)+", "", rest)
    if _V12_APPOSITIVE.match(rest):
        m3 = _V12_NEWS_START.search(rest[:400])
        if not m3:
            return None
        rest = rest[m3.start():]
    rest = _V12_FURTHER.sub("", rest, count=1)
    rest = _V12_PLEASED.sub("", rest, count=1)
    if not re.match(r"(?i)\W*(?:is|are)\s", rest):
        rest = _V12_LEAD_VERB.sub("", rest, count=1)
    rest = _V12_TODAY.sub("", rest, count=1)
    rest = _V12_FURTHER.sub("", rest, count=1)
    s = re.split(r"(?<![A-Z][a-z])(?<!\b[A-Z])(?<!\d)\.(?=\s+[A-Z“\"(])", rest, maxsplit=1)[0]
    s = s[:260].strip(" ,;:-–—")
    return s if len(s.split()) >= 4 else None


def _v12_lede_tags(body, stage):
    """(4) tags for a Corporate-Updates-only release, read from its opening sentence."""
    c = opening_clause(body)
    if not c:
        return []
    tags = [t for t in _v11_refire(c) if t != "Corporate Updates"]
    if not tags:
        return []
    tags = [t for t in v11_fix(tags, c) if t != "Corporate Updates"]
    drop, add = _v12_conflicts(tags, c)
    tags = [t for t in (set(tags) - drop) | (add - drop)]
    drop2, _ = _v12_stage_drops(tags, c, stage)
    tags = [t for t in tags if t not in drop2 and t in _V12_LEDE_TAGS]
    if "Mine Development & Operations" in tags and "Metallurgy & Processing" in tags:
        tags.remove("Metallurgy & Processing")
    return tags


# --------------------------------------------------------------- wrapper
def v12_fix(cats: list[str], headline: str | None, recovered: str | None = None, body: str | None = None,
            ticker: str | None = None) -> list[str]:
    """TAGFIX_V2: conflict table + proof (5, 6), company names (2), company stage (3), opening sentence (4)."""
    h = norm_head(headline)
    if (not h or is_hollow(h)) and recovered:
        h = norm_head(recovered)
    if not h or _DISCLAIMER_HEADLINE_V8.search(h):
        return list(cats)
    stage = _v12_stage(ticker, body)
    drop, add = _v12_conflicts(cats, h, body)
    drop |= _v12_name_drops([c for c in cats if c not in drop], h)
    d3, a3 = _v12_stage_drops([c for c in (set(cats) | add) if c not in drop], h, stage)
    drop |= d3; add |= a3
    add -= drop
    res = (set(cats) - drop) | add
    if len(res) > 1:
        res.discard("Corporate Updates")
    if not res or res == {"Corporate Updates"}:
        res = set(_v12_lede_tags(body, stage)) or {"Corporate Updates"}
    if res == set(cats):
        return list(cats)
    return [c for c in CATEGORIES if c in res] + [c for c in cats if c not in CATEGORIES and c in res]


# ===========================================================================
# v13 per-issuer headline memory (TAGFIX_V3, 2026-09-27): suggestion (9).
# Many issuers reuse the same headline ("Orosur Mining Inc - Colombia update", "Provides Operational Update").
# When someone corrects the tags of one such release with portal/tag_memory.py, the correction is stored as
# (issuer symbol, headline template) -> tags in portal/tag_memory.json, and every later release from that
# issuer with the same template gets the corrected tags. Nothing is learned automatically.
# ===========================================================================
_V13_MONTHS = (r"january|february|march|april|may|june|july|august|september|october|november|december|"
               r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
_V13_MEMORY = None
_V13_MEMORY_MTIME = None


def headline_template(headline: str | None) -> str:
    """A release's headline with dates, periods and numbers blanked, lower-cased: what an issuer reuses."""
    h = norm_head(headline).lower()
    h = re.sub(r"\b(?:" + _V13_MONTHS + r")\b\.?", " <m> ", h)
    h = re.sub(r"\b(?:q[1-4]|h[12]|fy)\s*[-']?\s*\d{0,4}\b", " <p> ", h)
    h = re.sub(r"\b(?:first|second|third|fourth)\s+quarter\b", " <p> ", h)
    h = re.sub(r"\d[\d,.:/-]*", " <n> ", h)
    h = re.sub(r"[^\w<> ]+", " ", h)
    return re.sub(r"\s+", " ", h).strip()


def issuer_symbol(ticker: str | None, body: str | None = None) -> str | None:
    """Base exchange symbol ("OMI" for "OMI.V"), from the stored ticker or, failing that, the release text."""
    t = (ticker or "").strip().upper()
    if not t and body:
        m = _V12_BODY_TICKER.search(body[:1200])
        t = m.group(1) if m else ""
    for suf in (".TO", ".V", ".CN", ".NE", ".T"):
        if t.endswith(suf):
            t = t[: -len(suf)]
            break
    return t or None


def _v13_memory():
    """portal/tag_memory.json, re-read when it changes. {"SYMBOL\\ttemplate": [tags]}; empty if absent."""
    global _V13_MEMORY, _V13_MEMORY_MTIME
    p = _v12_os.path.join(_v12_os.path.dirname(_v12_os.path.abspath(__file__)), "tag_memory.json")
    try:
        mt = _v12_os.path.getmtime(p)
    except OSError:
        _V13_MEMORY, _V13_MEMORY_MTIME = {}, None
        return _V13_MEMORY
    if _V13_MEMORY is None or mt != _V13_MEMORY_MTIME:
        try:
            data = _v12_json.load(open(p, encoding="utf-8"))
            _V13_MEMORY = {e["symbol"].upper() + "\t" + e["template"]: [c for c in e["tags"] if c in CATEGORIES]
                           for e in data.get("entries", []) if e.get("symbol") and e.get("template") and e.get("tags")}
        except Exception:
            _V13_MEMORY = {}
        _V13_MEMORY_MTIME = mt
    return _V13_MEMORY


def v13_memory(cats: list[str], headline: str | None, body: str | None = None, ticker: str | None = None) -> list[str]:
    """(9) a remembered correction for this issuer's headline template replaces the computed tags."""
    mem = _v13_memory()
    if not mem:
        return list(cats)
    if is_hollow(norm_head(headline)):
        return list(cats)   # "News Release" / ticker-only headlines say nothing about the content
    sym = issuer_symbol(ticker, body)
    if not sym:
        return list(cats)
    tags = mem.get(sym + "\t" + headline_template(headline))
    if not tags:
        return list(cats)
    return [c for c in CATEGORIES if c in tags]


# ===========================================================================
# v14 Corporate Updates vocabulary (TAGFIX_V4, 2026-09-27). Justin: "go ahead and start this rule change/fix", then
# "provide a larger amount of headlines rule phrases the headline rules don't recognise yet and teach it".
# Phrases mined from the 13,151 approved Corporate-Updates-only headlines and checked by reading random matches.
# Runs only on a release still left in Corporate Updates alone: the headline first; when the headline gives nothing,
# the opening sentence, for the tags that read reliably there. Also fixes two opening-sentence mistakes (a
# sustainability report is not Financials; a late or postponed filing is Regulatory).
# ===========================================================================
_V14_SKIP = re.compile(
    r"(?i)\bneither (?:the )?TSX|\bstock symbol\b|\bfor further information\b|\bissued and outstanding\b|\bnon[-\s]GAAP\b|"
    r"\bthis news release\b|\bnot for (?:distribution|dissemination)\b|\bforward[-\s]looking\b|\ball (?:monetary )?amounts\b|"
    r"\bunaudited tabular\b|\bnotice to reader\b|\bname and address of company\b")
_V14_NONMINING = re.compile(
    r"(?i)\bcannabis\b|\bhemp\b|\bdispensar\w+\b|\bCBD\b|\bpsilocybin\b|\bpsychedelic\w*\b|\bclinics?\b|\btokens?\b|\btokeni[sz]\w+\b|"
    r"\bbitcoin\b|\bcrypto\w*\b|\bblockchain\b|\bantminer\w*\b|\b(?:oil|gas) (?:production|well|wells|field|and gas)\b|\bpermian\b|\bbarrels?\b|\bpatent application\b")
_V14_PLAN = re.compile(
    r"(?i)\b(?:engag\w+|retain\w*|commenc\w+|prepar\w+|select\w*|award\w*|mandate|hires?|start\w*|initiat\w+|to (?:update|deliver|complete|prepare|begin)|"
    r"work on|in advance of|ahead of|towards?|planned|plans?|will|expected|underway|progress)\b")

_V14_RULES = [
    # (code, headline regex, allowed on the opening sentence)
    ("prd", r"\b(?:production|operating|operational|cost) (?:and cost )?guidance\b|\bguidance for 20\d\d\b|\b20\d\d (?:production |operating )?guidance\b|"
            r"\b(?:beats|exceeds|meets|achieves|reaffirms|confirms)\b[^\n]{0,30}\bguidance\b|\bmonthly production\b|\bproduction (?:update|report|results|record)\b|"
            r"\brecord (?:quarterly |monthly |annual )?production\b|\bpreliminary (?:20\d\d |Q[1-4] )?(?:production|operating|operational) results\b|"
            r"\bproduction milestone\b|\b(?:millionth|billionth) (?:ounce|pound|tonne|carat)\b|"
            r"\b(?:reach|reaches|reached|surpass\w*|celebrat\w*)\b[^\n]{0,40}\b(?:million|billion|thousand|\d[\d,.]*)\s*(?:ounces|oz|pounds|lbs|tonnes|carats)\b[^\n]{0,30}\b(?:produc\w+|pour\w*)\b|"
            r"\b(?:gold|silver|copper|concentrate|ore) sales of\b|\b\d[\d,.]*\s*(?:ounces|oz) (?:of gold )?(?:sold|produced)\b", True),
    ("eco", r"\b(?:results? of|completes?|completed|completion of|positive|robust|delivers?|announces|reports?|files?) (?:the |an? |its )?(?:updated |internal |maiden |new )?(?:preliminary economic (?:assessment|analysis)|PEA|pre-?feasibility(?: study)?|PFS|feasibility study|DFS|BFS|scoping study|conceptual study)\b", False),
    ("res", r"\b(?:ore |mineral )?reserves? (?:growth|increase|statement|update)\b|\bmineral resources? and (?:ore |mineral )?reserves?\b|\bresources? and reserves?\b|"
            r"\bdefines? (?:a )?new resource\b|\bupdated? (?:mineral )?resources?\b(?! estimate)", True),
    ("fin", r"\bfinancing\b|\bprivate placement\b|\bpriv ate placement\b|\bp rivate placement\b|\bplacement\b|\bsubscription\b|\bstrategic investments?\b|\bequity investment\b|"
            r"\binvestment (?:by|from)\b|\bbought deal\b|\bflow[-\s]through\b|\bprospectus offering\b|\bat[-\s]the[-\s]market\b", False),
    ("dbt", r"\bnotes offering\b|\bsenior (?:secured )?notes\b|\bloan\b|\bcredit facility\b|\bdebentures?\b|\bletter of credit\b|\bpurchase order financing\b|\bprepayment facility\b", False),
    ("cap", r"\bwarrants?\b|\bstock options?\b|\b(?:consideration|bonus|fee|advisory|installment|milestone|payment) shares\b|\bissuance of\b[^\n]{0,40}\bshares\b|"
            r"\bshares for (?:debt|services)\b|\bdebt settlement\b|\bsettlement of (?:outstanding |approximately )?(?:[$\d,.]+ (?:of )?)?(?:outstanding )?debt\b|\bdebt conversions?\b|"
            r"\bshares (?:and warrants )?(?:of|in) its subsidiary\b|\bdistribut\w+ (?:of )?(?:\w+ )?shares\b", False),
    ("mna", r"\b(?:letter of intent|LOI)\b[^\n]{0,60}\b(?:acqui\w+|merge\w*|combin\w+|sale|sell|purchase|arrangement)\b|\b(?:acqui\w+|merge\w*|combin\w+|sale|sell|purchase)\b[^\n]{0,60}\b(?:letter of intent|LOI)\b|\bnon[-\s]binding term sheet\b|\bbinding term sheet\b|\bmerger\b|\bbusiness combination\b|\bplan of arrangement\b|\btake[-\s]?over\b|"
            r"\bspin[-\s]?out\b|\bspinco\b|\b(?:sale|divestiture|disposition) of (?:the |its |our |a |certain )?(?:[\w'’-]+ ){0,4}(?:project|property|properties|mine|deposit|interest|stake|subsidiary|assets?|business|operations?)\b|"
            r"\bacquisition of (?:[A-Z][\w&’'-]* ){1,4}(?:Corp\w*|Inc|Ltd|Limited|Mining|Mines|Resources|Gold|Metals|Minerals|Capital|Holdings|Ventures|Operations)\b|"
            r"\bcourt (?:order )?approval\b|\bconsolidates? \d+%", False),
    ("opt", r"\bstak(?:es|ed|ing) (?:claims|ground|new|additional|multiple|a|an|the|\d)\b|\bstaking\b|\b(?:mineral|lode|placer|mining|additional|new) claims\b|\bclaims? (?:package|block|acquisition)\b|"
            r"\bland (?:package|position|holdings?)\b|\b\d[\d,.]* (?:hectares?|ha|km2|square km|sq\.? km)\b|\bexpands? (?:its )?(?:land|property|claims)\b|\bdispositions\b|"
            r"\boption (?:agreement|payment)\b|\bproperty payment\b|\bearn[-\s]?in\b|\boptions? (?:highly |a |the )?(?:\w+ )?(?:concession|property|project)\b", False),
    ("per", r"\b(?:receives?|received|granted|grants|issues?|issued|approves?|approved|approval|obtains?|secures?|submits?|submitted|files?|filed|lodges?|applies|application|renew\w*|extension|extends?|reinstat\w*|awarded|draft)\b[^\n]{0,40}\b(?:permits?|licen[cs]es?|concessions?|tenements?|mining leases?|leases?|EIA|EIS|ESIA|environmental (?:assessment|approval|impact statement|clearance|certificate))\b|"
            r"\b(?:permits?|licen[cs]es?|concessions?|tenements?|mining leases?)\b[^\n]{0,25}\b(?:granted|approved|issued|received|renewed|extended|reinstated|ratif\w+|transfer\w*|good standing|application)\b|"
            r"\bpermitted for\b|\bpermitting (?:update|progress\w*|milestone|process|application)\b|\bwarden'?s? (?:court|hearing)\b|\bfast[-\s]track(?:ed)? approvals?\b|\bpublic (?:consultation|hearing)s?\b|"
            r"\b(?:EIA|EIS|ESIA|AMDAL|BAPE)\b|\bplan of operations\b|\bnotice of work\b|\brecord of decision\b|\bnuclear safety commission\b|\bSML\b", True),
    ("ltr", r"\bshareholder letter\b|\bletter to (?:shareholders|share[-\s]holders|investors)\b|\b(?:ceo|president)'?s? letter\b|\bmessage (?:from|to) (?:the )?(?:ceo|president|chairman|shareholders)\b|"
            r"\byear[-\s]end (?:update|review|letter|shareholder update)\b|\byear in review\b|\boutlook for 20\d\d\b|\b20\d\d (?:strategic )?outlook\b", False),
    ("lst", r"\b(?:secondary|dual|cross)[-\s]listing\b|\btransfer of listing\b|\blisting (?:of (?:its |the )?(?:common )?(?:shares|warrants) )?on (?:the )?[A-Z]|\blist(?:s|ed)? (?:its shares |common shares )?on (?:the )?[A-Z]|"
            r"\bapproval (?:for|to) (?:the )?list\w*\b|\bconditional approval\b[^\n]{0,30}\blist\w*\b|\bIPO\b[^\n]{0,20}\blisting\b|\b(?:now )?trades on\b|\b(?:begins|commences|to commence|to begin|starts) trading\b|"
            r"\bupgrades? (?:its |to )?(?:american )?(?:listing|OTCQX|OTCQB)\b|\bapproved for\b[^\n]{0,20}\b(?:OTC|listing)\b|\bDTC eligib\w+\b|\bdepository trust company\b|\bwithdrawal from (?:the )?OTC\w*\b|"
            r"\bwelcomes listing\b|\btrading symbol change\b|\bnew (?:trading )?symbol\b", False),
    ("mkt", r"\bconference\b|\bwebinar\b|\bwebcast\b|\btown ?hall\b|\bpodcast\b|\binterview\b|\bproject tour\b|\bto (?:address|present|moderate|speak|highlight)\b[^\n]{0,60}\b(?:conference|summit|forum|panel|roundup|event)\b|"
            r"\b(?:engages|retains|hires|adds)\b[^\n]{0,50}\b(?:investor relations|market(?:ing| maker|[-\s]making| support| awareness)|capital markets? advis\w+|(?:corporate|strategic|financial) advisory|IR (?:firm|services|resource)|promotional|awareness)\b|"
            r"\b(?:medal|prize)\b|\bhonou?red\b|\b(?:receives?|wins?|won) (?:the )?[\w\s“”\"'-]{0,40}\baward\b|\bawarded (?:the|with)\b[^\n]{0,40}\b(?:award|medal|prize|distinction)\b|\bawards? announcement\b|\bjoin (?:the )?russell\b|\bindex(?:es)? inclusion\b", False),
    ("cmt", r"\bcomments? (?:on|of|regarding)\b|\bresponds? to\b|\bresponse to (?!covid)\b|\bstatement (?:on|regarding|re)\b|\bapplauds?\b|\bcongratulates\b|\bcorrects? (?:false|misleading)\b|"
            r"\bmisleading\b|\bmisinformation\b|\bwelcomes (?:the |new |recent )?(?:government|announcement|decision|news|policy|federal|provincial|mining law|legislation|executive order)\b|"
            r"\bsupports? (?:the )?(?:government|federal|provincial|G7|policy|proposed|formation)\b|\bhighlights (?:\w+(?:'s|’s) )?(?:[\w\s]{0,30})(?:results|announcement|discovery)\b|\bexpresses\b", False),
    ("jv", r"\b(?:enters? into|signs?|forms?|formali[sz]es?|expands?|announces?|launch(?:es)?|establish(?:es)?|new)\b[^\n]{0,40}\b(?:partnership|joint venture|teaming agreement|strategic alliance|collaboration agreement|cooperation agreement|memorandum of understanding|MOU)\b|"
            r"\bjoint (?:exploration|development) (?:and development )?agreement\b|\bteam(?:s|ing)? up\b|\bpartners? with\b", False),
    ("exp", r"\bdrill(?:ing)? (?:program|campaign|plans?|contract|rig|underway|begins|commences|recommences|to begin|resumes|update|permits?)\b|\b(?:drilling|exploration) (?:re)?commences\b|"
            r"\bmobiliz\w+\b|\bexploration (?:program|plans?|update|activities|campaign|season|work|progress)\b|\bfield (?:program|work|season|crews?)\b|\b(?:identifies|defines|generates|outlines|stakes|expands) (?:new |multiple |additional )?(?:[\w-]+ ){0,3}targets?\b|"
            r"\bnew (?:[\w-]+ ){0,3}discovery\b|\bdiscovery (?:hole|zone|at)\b|\bhigh[-\s]grade (?:continuity|footprint|zone|potential|extension)\b|\bexpands? (?:the )?high[-\s]grade\b|\bgeophysic\w+\b|\b(?:airborne|drone|magnetic|gravity|EM|IP|LiDAR) survey\b|"
            r"\bmachine learning\b[^\n]{0,30}\btarget\w*\b|\btarget(?:ing)? (?:generation|development|refinement)\b", False),
    ("drl", r"\bdrill(?:ing)? results\b|\bassays?\b(?! lab)(?=[^\n]{0,80}\b(?:drill\w*|holes?|core|intersect\w*|metres|meters|m @|over \d))|\bintersect(?:s|ed|ing|ion|ions)\b|\bdrills?\b[^\n]{0,40}\b(?:holes?|metres|meters|m of)\b|\bholes?\b[^\n]{0,30}\b(?:g/t|%|metres|meters|intersect|return|hit)\b|"
            r"\b\d[\d.,]*\s*(?:g/t|gpt|%\s*(?:Cu|Zn|Ni|Li2O|U3O8|CuEq|ZnEq|Pb|Mo|TGC|Cg)|ppm|oz/t)\b[^\n]{0,40}\bover\s+\d[\d.,]*\s*(?:m|metres|meters|ft|feet)\b|\bscintillometer\b|\bcps\b|\bboreholes?\b", False),
    ("smp", r"\bsampl(?:es|ing) (?:results|returns?|yields?|confirms?|program|programs|survey)\b|\b(?:high[-\s]grade|grab|chip|channel|rock|soil|till|surface|outcrop|boulder) samples?\b|"
            r"\bsampl(?:es|ing|ed)\b[^\n]{0,40}\b(?:g/t|%|high[-\s]grade|gold|silver|copper)\b|\btrench(?:es|ing)?\b|\bsoil (?:geochem\w*|anomal\w*|chemistry|survey|gas)\b|\bgeochem\w+\b|\bmapping and sampling\b|\bsampling and mapping\b|"
            r"\bsurvey results\b|\borientation survey\b|\b(?:HSAMT|magnetotelluric)\b|\bprospecting results\b|\bboulders?\b[^\n]{0,30}\b(?:found|discovered|return|grade|samples?)\b", True),
    ("reg", r"\bearly warning\b|\bholding\(?s\)? in company\b|\bholdings in (?:[A-Z][\w.&-]* ){1,4}(?:Inc|Corp\w*|Ltd|Limited|Metals|Mining|Resources|Gold)\b|\bannounces? (?:changes to (?:his|her|its) )?holdings\b|\bdiscloses? (?:holdings?|investment|ownership|stake)\b|"
            r"\bshareholder holding in excess\b|\btakes? (?:an? )?[\d.]+% stake\b|\bcease trade\b|\bMCTO\b|\bsecurities commission\b|\bOSC\b|\bBCSC\b|\bCIRO\b|\bIIROC\b|\bASX compliance\b|"
            r"\blate filing\b|\b(?:delay\w*|postpone\w*) (?:in )?(?:the )?(?:filing|annual filings|financial statements)\b|\brequested filings\b|\bTR-1\b|\b62-103\b|\badjusts shareholding\b", True),
    ("leg", r"\bcourt\b(?! (?:order )?approval)|\blawsuit\b|\blitigation\b|\barbitration\b|\blegal (?:action|proceedings|counsel|challenge)\b|\bclaim against\b|\bjudicial review\b|\bICSID\b|\binjunction\b|"
            r"\bsettlement agreement\b|\bsubpoena\b|\bcriminal\b|\bfine\b", False),
    ("fns", r"\bfinancial (?:statements|results|report)\b|\bMD&A\b|\bearnings\b|\b(?:first|second|third|fourth)[-\s]quarter results\b|\bquarterly results\b|\bannual (?:filings?|results)\b|"
            r"\bfiscal (?:year|20\d\d) (?:end|results)\b|\byear[-\s]end change\b|\bchange (?:to|of|in) (?:its )?(?:financial |fiscal )year[-\s]end\b|\b(?:financial|fiscal) year[-\s]end\b", True),
    ("act", r"\bshare consolidation\b|"
            r"\bconsolidation (?:mandate|of (?:its |the )?(?:common )?shares)\b|\bname change\b|\bchange (?:of|its) name\b|\bdividend\b", False),
    ("met", r"\bmetallurg\w*\b(?![^\n]{0,20}\b(?:Society|Institute|Petroleum)\b)|\bhydrometallurg\w*\b|\brecover(?:y|ies) (?:of|rates?|up to|improv\w+|increas\w+|tests?|results|above|over|exceed\w*)\b|\b\d[\d.]*\s*% (?:\w+ )?recover\w*\b|\bimproved (?:\w+ )?recover\w*\b|\bflotation\b|\bleach(?:ing)? (?:test|tests|testing|results|column)\w*\b|\bflow ?sheet\b|\bbeneficiation\b|\bmineralog\w+\b|"
            r"\bQEMSCAN\b|\b(?:ore|material|mechanical|automated|sensor[-\s]based|XRT)[-\s]sort\w*\b|\bore[-\s]sorter\b|\bmagnetic separation\b|\bpre-?concentrat\w+\b|\btest ?work\b|\bbench[-\s]scale\b|"
            r"\bpilot (?:plant|production) (?:results|test\w*|campaign|program|run)\b|\bdemonstration plant\b|\bextraction\b[^\n]{0,30}\b(?:test|results|process|technology|rate)\w*\b|\b99\.\d+%[^\n]{0,30}\b(?:test\w*|sample|lab\w*|produc\w+|achiev\w+)\b|\bbattery[-\s]grade\b[^\n]{0,30}\b(?:test\w*|sample|produc\w+|achiev\w+)\b|\bspherical graphite\b|\bcharacteri[sz]ation (?:test\w*|study|analysis|work)\b", True),
    ("roy", r"\b(?:royalty|stream|NSR)\b[^\n]{0,20}\b(?:agreement|sale|purchase|acquisition|payment|financing|buy[-\s]?back|interest|closing|portfolio|holding update|update)\b|\bpayment to [\w\s]{0,20}royalt\w+\b|\bstream with\b|\broyalty[-\s]linked\b", False),
    ("mgt", r"\b(?:death|passing) of\b|\bleave of absence\b|\bresign\w*\b|\bsteps? down\b|\bretire\w*\b|\bappoint\w*\b(?![^\n]{0,30}\b(?:broker|auditors?|transfer agent|counsel|market maker|consultants?|contractor)\b)|\badditions? to (?:the|its) (?:board|team|management)\b|\bstrengthens (?:its )?(?:board|team|management|leadership)\b|"
            r"\bwelcomes\b[^\n]{0,40}\b(?:director|board|ceo|cfo|president|chair|vp|vice[- ]president|geologist|advisor)\b|\bexternal appointment\b|\bboard (?:changes?|renewal|reconstitution)\b|\bmanagement (?:changes?|reorgani[sz]ation|team)\b", False),
    ("dev", r"\b(?:start|starts|started|commence\w*|begin\w*|begins)\s+(?:of\s+)?(?:processing|trial mining|mining operations|test mining|ore processing|milling|mill processing|leaching|heap leach)\b|"
            r"\btrial mining\b|\btest mining\b|\bmine plan\b|\bmine life\b|\brestart\w*\b|\bconstruction (?:update|decision|progress|begins|commences|milestone|of)\b|\bcommissioning\b|\bramp[-\s]?up\b|"
            r"\b(?:plant|mill) (?:expansion|construction|commissioning|upgrade|refurbishment|restart)\b|\brefurbishment\b|\bcare and maintenance\b|\bsuspen(?:ds|sion of|ded) (?:operations|mining|production)\b|"
            r"\bmining contract(?:or)?\b|\bofftake\b|\bshaft sinking\b|\bunderground development\b|\bdecline development\b|\bfatal(?:ity|ities)?\b|\bcasualty\b|\bdeath of (?:an?|one) (?:employee|worker|contractor|miner)\b|"
            r"\b(?:workplace|underground|mine|mining|site|plant) (?:accident|incident)\b|\b(?:fire|flood(?:ing)?|rainfall|wildfire)\b[^\n]{0,30}\b(?:at|near|operation|mine|site)\b|\bexpansion (?:project|plan|phase)\b|\bprocessing (?:plant|facility)\b", False),
]
_V14_RX = [(c, re.compile("(?i)" + r), lede) for c, r, lede in _V14_RULES]
_V14_OPS = re.compile(r"(?i)\boperation(?:s|al)? update\b|\bprovides (?:an? )?operational\b|\bcorporate (?:and|&) operational update\b|\boperational (?:and corporate )?update\b")
_V14_ROLE = re.compile(r"(?i)\b(?:chair(?:man)?|director|ceo|cfo|president|managing director)\b")
_V14_SUST = re.compile(r"(?i)\b(?:sustainability|ESG|responsible mining|climate|TCFD|environmental,? social)\b[^\n]{0,20}\breport\b|\breport on (?:sustainability|ESG)\b")
_V14_LATE = re.compile(r"(?i)\blate filing\b|\b(?:delay\w*|postpon\w*)\b[^\n]{0,40}\b(?:filing|statements|annual filings)\b|\bfiling delay\b|\bcease trade\b|\bMCTO\b|\bblanket (?:relief|order)\b|\bfail\w* to file\b")
_V14_FILED = re.compile(r"(?i)\bfiles\b|\bfiled\b|\b(?:announces|completes) (?:the )?filings?\b|\bfilings? of\b[^\n]{0,60}\b(?:revocation|revoke)\b|"
                        r"\b(?:publication of|reports?|announces)\b[^\n]{0,40}\bunaudited\b[^\n]{0,40}\bresults\b|\binterim report\b|\band filing of\b|"
                        r"\breports?\b[^\n]{0,30}\b(?:financial|annual|quarter\w*|interim|20\d\d)\b[^\n]{0,20}\bresults\b")
_V14_FNS_REAL = re.compile(r"(?i)\bresults\b|\bconference call\b|\bfinancial statements\b|\bfiles?\b|\bfiled\b|\bearnings\b|\breports? (?:Q[1-4]|first|second|third|fourth|annual|interim)\b")


def _v14_tags(text, lede=False, stage=None):
    t = text or ""
    if not t.strip() or _V14_NONMINING.search(t):
        return []
    got = []
    for code, rx, on_lede in _V14_RX:
        if lede and not on_lede:
            continue
        if not rx.search(t):
            continue
        if code == "res" and _V14_PLAN.search(t):
            continue
        if code in ("prd", "fns") and re.search(r"(?i)\b(?:to|will) (?:release|report|announce|host|issue)\b|\bconference call\b", t):
            continue
        if code == "met" and re.search(r"(?i)\baward\b|\bpermit\b|\bsupply (?:contract|agreement)\b|\bpours?\b|\bexploring the use\b", t):
            continue
        if code in ("smp", "met") and re.search(r"(?i)\blaborator\w+\b|\blab\b|\bpermit\w*\b|\bgrants?\b|\bslippage\b|\bincident\b|\bengineer\b|\bappoint\w*\b", t):
            continue
        if code == "fin" and re.search(r"(?i)\b(?:retains|engages|appoints)\b[^\n]{0,60}\badvis\w+\b|\bplanned\b|\bmetal ?stream\b|\bstream financing\b|\bforward (?:gold )?(?:sale|purchase)\b", t):
            continue
        if code == "opt" and re.search(r"(?i)\bsale of\b|\bsells?\b|\b100% ownership\b|\brevert\w*\b", t):
            continue
        if code == "eco" and re.search(r"(?i)\b(?:engag\w+|commenc\w+|initiat\w+|begin\w*|start\w*|launch\w*|select\w*|award\w*|retain\w*|nearing|update|progress|status|underway|advanc\w+|plans?|to (?:begin|complete|deliver|prepare|conduct|lead|update)|work on|towards?|contract)\b", t):
            continue
        if code == "smp" and re.search(r"(?i)\bplans?\b|\bplanned\b|\bbulk sampl\w*\b|\bwill\b|\bexpanded\b", t):
            continue
        if code == "drl" and re.search(r"(?i)\bhistor\w+\b|\bdigiti[sz]\w+\b|\bcompilation\b", t):
            continue
        if code == "leg" and re.search(r"(?i)\b[A-Z][a-z]+ Court\b", t) and not re.search(r"(?i)\bcourt (?:decision|ruling|order|of appeal|case|hearing|proceedings|action|challenge)\b|\bsupreme court\b|\b(?:federal|superior|high|district) court\b", t):
            continue
        if code == "dev" and re.search(r"(?i)\binvestment\b", t):
            continue
        if code == "eco" and re.search(r"(?i)\b(?:grid|power|hydro\w*|transmission|rail|port|road|pipeline|energy) (?:\w+ )?feasibility\b|\bproposal\b|\bfunding\b|\binvited\b", t):
            continue
        if code == "met" and re.search(r"(?i)\bpurchas\w+\b[^\n]{0,30}\bmill\b|\blease\b|\bcompressive\b|\bgasification\b|\bbiomass\b|\bproject update\b", t):
            continue
        if code == "exp" and re.search(r"(?i)\bfinancing\b|\bplacement\b|\brehabilitation\b", t):
            continue
        if code == "per" and re.search(r"(?i)\bsupply\b|\bfleet\b|\bthanks\b|\bsampling\b", t):
            continue
        if code == "fin" and re.search(r"(?i)\bletter of credit\b|\bpost[-\s]financing\b", t):
            continue
        if code == "per" and re.search(r"(?i)\bacqui\w+\b|\bLOI\b|\bletter of intent\b|\bconsolidat\w+\b|\bgrant\b|\bfunding\b|\bfully[-\s]permitted\b|\bpermitting times\b|\bregist\w+ ownership\b", t):
            continue
        if code == "mgt" and len(_V14_ROLE.findall(t)) >= 3:
            continue                                     # a board list printed as a headline
        got.append(code)
    if "drl" in got and "smp" in got and not re.search(r"(?i)\bdrill|\bholes?\b|\bintersect|\bboreholes?\b|\bcore\b", t):
        got.remove("drl")
    if "mna" in got and "opt" in got and re.search(r"(?i)\bclaims?\b|\boption\b|\bearn[-\s]?in\b", t):
        got.remove("mna")
    return got


def v14_fix(cats: list[str], headline: str | None, recovered: str | None = None, body: str | None = None,
            ticker: str | None = None) -> list[str]:
    """TAGFIX_V4: headline and opening-sentence vocabulary for releases still in Corporate Updates only."""
    h = norm_head(headline)
    if (not h or is_hollow(h)) and recovered:
        h = norm_head(recovered)
    s = set(cats)
    # opening-sentence mistakes fixed on any release: a sustainability report is not Financials; a late filing is Regulatory
    if "Financials" in s and h:
        oc = opening_clause(body) if body else None
        if _V14_SUST.search(h) and not _V14_FNS_REAL.search(_V14_SUST.sub(" ", h)):
            s.discard("Financials")
        elif _V14_LATE.search(h) or (oc and _V14_LATE.search(oc) and not _V14_FNS_REAL.search(h)):
            s.add("Regulatory & Compliance")
            if not _V14_FILED.search(h):
                s.discard("Financials")
        if not s:
            s = {"Corporate Updates"}
    base = list(cats) if s == set(cats) else [c for c in CATEGORIES if c in s]
    if s != {"Corporate Updates"}:
        return base
    if not h or _DISCLAIMER_HEADLINE_V8.search(h):
        return base
    stage = _v12_stage(ticker, body)
    codes = [] if (is_hollow(h) or _V14_SKIP.search(h)) else _v14_tags(h, False, stage)
    if not codes and body:
        oc = opening_clause(body)
        if oc and not _V14_SKIP.search(oc):
            codes = _v14_tags(oc, True, stage)
    if not codes:
        return base
    new = {CODE_TO_CAT[c] for c in codes}
    return [c for c in CATEGORIES if c in new]


# ===========================================================================
# v15 per-tag false-positive removal (TAGFIX_V5 / FP1 Phase 1, 2026-09-27). Justin: "start the per-tag check for tags
# that don't belong on Mining News Terminal (Phase 1) ... Write removal rules that drop a tag only when nothing else in
# the release earns it." Patterns come from 250 graded random releases per tag (seed 20261002) and were checked on
# each tag's full population. Runs after TAGFIX_V4 on every release. A tag is dropped only when (a) a known false
# trigger is present and (b) nothing in the headline (or, where stated, the opening sentence) earns the tag. If a drop
# leaves the release with no tag, the V4 vocabulary picks the replacement from the headline, then the opening
# sentence; failing that, Corporate Updates.
# ===========================================================================

# ---- M&A ------------------------------------------------------------------------------------------------------------
_V15_MNA_CORP = re.compile(
    r"\bmerg\w+|\bamalgamat\w+|\bplan of arrangement\b|\bsuperior proposal\b|\brevised offer\b|\boffer (?:to acquire|for all)\b|\bcombine (?:with|to create)\b|\bto combine\b|\bcombination with\b|\barrangement agreement\b|\bbusiness combination\b|\btake[-\s]?over\b|"
    r"\btender offer\b|\bhostile\b|\bunsolicited\b|\breverse take[-\s]?over\b|\bRTO\b|\bqualifying transaction\b|\bspin[-\s]?(?:out|off)\b|"
    r"\bspinco\b|\bshare exchange\b|\b(?:all|100%) of the (?:issued and )?outstanding\b|\boutstanding (?:common )?shares\b|"
    r"\bacqui\w+ (?:of )?(?:all of )?(?-i:(?:[A-Z][\w&.’'-]*\s+){1,4}(?:Corp\w*|Inc\.?|Ltd\.?|Limited|LLC|S\.A\.|plc|PLC|AG|GmbH|Pty|Mines|Mining|Resources|Metals|Minerals|Capital|Holdings|Ventures|Exploration|Royalties|Energy|Gold|Silver|Copper|Lithium|Uranium|Nickel|MINES|MINING|RESOURCES|METALS|MINERALS|CAPITAL|HOLDINGS|VENTURES|EXPLORATION|ROYALTIES|ENERGY)\b(?!\s+(?:Project|Property|Properties|Mine|Deposit|Claims|Prospect|District|Belt|Camp|Assets|Portfolio|PROJECT|PROPERTY|PROPERTIES|MINE|DEPOSIT|CLAIMS)))\.?|"
    r"\b(?:sale|divestiture|disposition|divests?|sells?|sold) (?:of )?(?:its |the |a |our )?(?:\d+% )?(?:interest in |stake in )?"
    r"(?:[\w'’-]+ ){0,4}(?:subsidiary|business|division|shares of)\b", re.I)
_V15_MNA_CORE = re.compile(
    r"\bacqui\w+|\bmerg\w+|\bamalgamat\w+|\barrangement\b|\btake[-\s]?over\b|\bpurchas\w+|\bsale\b|\bsells?\b|\bsold\b|\bdivest\w+|"
    r"\bdispos\w+|\bbuy\w*|\bbought\b|\bconsolidat\w+|\bbusiness combination\b|\bspin[-\s]?(?:out|off)\b|\bspinco\b|\btender\b|"
    r"\bqualifying transaction\b|\bRTO\b|\bshare exchange\b|\btransfer of\b|\bstake in\b|\binterest in\b|\btransaction\b|"
    r"\bdefinitive agreement\b|\bletter of intent\b|\bLOI\b|\bownership\b|\bhostile\b|\binvestment in\b|\bdue diligence\b|\bterm sheet\b|\bbinding agreement\b|\bdeal\b|\bto create\b|\bcombin\w+|\bclosing\b|\baquisi\w+|\bstandstill\b|\bstakeholder\b|\bplatform\b|\bexclusivity\b", re.I)
_V15_OPTION = re.compile(r"\boption(?:s|ed|ing)?\b(?! (?:plan|grant|holders?|exercise|to purchase (?:common )?shares))|\bearn[-\s]?in\b|"
                         r"\bearn (?:an? |up to |a further |an additional )?(?:\d+%|interest)|\boptionor\b|\boptionee\b", re.I)
_V15_STOCK_OPT = re.compile(r"\b(?:stock|incentive|share|employee) options?\b|\bwarrants?,? (?:and|&) (?:stock )?options\b|\boptions? (?:and|&) warrants?\b|\bexercise of (?:\w+ ){0,2}options\b|\b(?:underwriter|agent|broker|finder)s?['’]?s?['’]? options?\b|\bover[-\s]{0,2}allotment options?\b|\bgreenshoe\b|\bfinancing options\b|\bwarrants?,? options\b|\boptions? (?:grant|to (?:directors|officers|employees))\w*", re.I)
_V15_STAKE = re.compile(r"\bstak(?:es|ed|ing)\b(?! (?:in|of|program|programs|rewards|pool|platform)\b)|\bby staking\b|\bthrough staking\b|\bland (?:package|position|holdings?|base)\b|"
                        r"\b(?:expands?|expanded|increases?|increased|grows?|triples?|doubles?|adds?|added|enlarges?)\b[^\n.]{0,40}"
                        r"\b(?:land|property|claims?|package|footprint|acreage|hectares|ground|tenure|size)\b|"
                        r"\b(?:new|additional|more) (?:mining |mineral |lode |placer )?claims\b|\bclaims? (?:block|package|acquisition)\b", re.I)
_V15_BOUGHT = re.compile(r"\bpurchase (?:and sale )?agreements?\b|\bpurchase price\b|\bfrom (?:an? )?(?:arm'?s[-\s]length |private )?vendors?\b|"
                         r"\bfrom (?:[A-Z][\w&.’'-]*\s+){1,4}(?:Corp\w*|Inc\.?|Ltd\.?|Limited|LLC|Resources|Mining|Metals|Gold|Minerals)\b|"
                         r"\bin consideration\b|\bcash (?:and|plus) (?:\d[\d,.]* )?(?:common )?shares\b|\boutright\b", re.I)
_V15_ROY = re.compile(r"\broyalt(?:y|ies)\b|\bNSR\b|\bNPI\b|\bGSR\b|\bstreams?\b|\bstreaming\b", re.I)
_V15_ROY_CO = re.compile(r"\b(?:[A-Z][\w-]*\s+){1,3}(?:Royalties|Royalty\s+(?:Corp\w*|Inc\.?|Ltd\.?|Limited|AG|plc)|Royalty\s+(?:&|and)\s+Streaming)\b"
                         r"|\bRoyalty (?:North|Corp\w*)\b")
_V15_EW = re.compile(r"\bearly warning\b|\b62-10[34]\b", re.I)


# ---- Metallurgy & Processing ----------------------------------------------------------------------------------------
_V15_MET_JOB = re.compile(r"\b(?:appoint\w*|hires?|names?|welcomes|joins?|adds?)\b[^\n]{0,80}\bmetallurg\w+|\bmetallurg\w+ (?:officer|manager|director|lead)\b|"
                          r"\b(?:vice[-\s]president|VP|chief|principal|senior)\b[^\n]{0,20}\bmetallurg\w+", re.I)

# ---- Mine Development & Operations ------------------------------------------------------------------------------------
_V15_DEV_NAME = re.compile(r"\bMine Development Associates\b|\bMDA\b|\bMineral Development Fund\b|\bMine Development Corp\w*\b|"
                           r"\b(?:Cantex|Kenville) Mine Development\b")

# ---- Drill Results ----------------------------------------------------------------------------------------------------
_V15_DRL_RESULT = re.compile(r"\bintersect\w*|\bintercept\w*|\bassays?\b|\bresults?\b|\bg/t\b|\bgpt\b|\bppm\b|\b%\s*(?:Cu|Zn|Ni|Li2O|U3O8|eU3O8|CuEq|Pb|Mo|TREO|Co|Sn|W|Au)\b|"
                             r"\bover \d|\bgrad\w+|\breturns?\b|\bhits?\b|\bcuts?\b|\bencounter\w*|\bconfirms?\b|\bextends?\b|\bexpands?\b|\bmineraliz\w+|\bmineralis\w+|"
                             r"\bdiscover\w*|\bhigh[-\s]grade\b|\bvisible gold\b|\bsulphides?\b|\bsulfides?\b|\bmetres of\b|\bmeters of\b|\bm of\b|"
                             r"\bextend\w*|\bintervals?\b|\bveins?\b|\bdrill(?:s|ed)? (?:an? )?\d[\d.,]*\s?(?:m|metres|meters|ft|feet)\b", re.I)
_V15_DRL_PLAN = re.compile(r"\b(?:begins?|start\w*|commenc\w+|resum\w+|initiat\w+|mobiliz\w+|launch\w*|plans?|planned|(?<!continues )to drill|will drill|approval to drill|"
                           r"permit\w* to drill|drill permit|underway|prepares?|preparing|upcoming|to begin|to commence|to start|contract\w*|rig)\b", re.I)
_V15_DRL_MET = re.compile(r"\brecover(?:y|ies)\b|\bmetallurg\w+|\bleach\w*|\bextraction\b|\bconcentrate\b|\bpilot plant\b|\bdense media\b|\bbulk sample\b", re.I)
_V15_DRL_HIST = re.compile(r"\bhistor\w+ (?:drill\w*|intercepts?|intersections?|results?|holes?)\b|\bpast drilling\b|\bprevious(?:ly reported)? (?:drill\w*|results?)\b|"
                           r"\bfinancial results\b|\bquarter(?:ly)? report\b|\bfiles? (?:first|second|third|fourth) quarter\b", re.I)

# ---- Resource Estimates -----------------------------------------------------------------------------------------------
_V15_RES_WORD = re.compile(r"\bresources?\b|\breserves?\b|\bMRE\b|\bMRMR\b|\bM&I\b|\binferred\b|\bindicated\b|\bmeasured\b|\bNI 43-101\b|\btechnical report\b|\bJORC\b", re.I)
_V15_RES_REPORT = re.compile(
    r"\b(?:announces|reports|delivers|releases|publishes|completes|completed|unveils|declares|posts|provides|issues|files|filed)\b[^\n]{0,50}\b(?:resource|reserve|MRE)\b(?! (?:update )?(?:timeline|drilling|target|potential|expansion drilling))|"
    r"\b(?:maiden|initial|inaugural|first|updated?|new|increased?|expanded|upgraded|revised|restated|robust|significant|large|larger|higher[-\s]grade|high[-\s]grade|open[-\s]pit|underground|global|combined|pit[-\s]constrained|in[-\s]pit)\s+"
    r"(?:(?:NI 43-101 |JORC |43-101 |compliant |mineral |gold |silver |copper |lithium |uranium |nickel |graphite |zinc |REE |rare earth |heap leach |\w+ )?){0,3}(?:mineral )?(?:resources?|reserves?|MRE)\b(?! (?:update )?(?:timeline|drilling|target|potential))|"
    r"\b(?:resource|reserve) (?:estimate|statement|update|increase|growth|expansion)\b(?! (?:timeline|drilling|by|in (?:Q\d|20\d\d)|expected|planned|work))|"
    r"\b\d[\d,.]*\s*(?:million |M |billion |B )?(?:oz|ounces|tonnes|t|Mt|lbs|pounds|carats|Moz|Koz|Mlbs|Blbs)\b[^\n]{0,60}\b(?:resource|reserve|M&I|indicated|inferred|measured)\b|"
    r"\b(?:resource|reserve|M&I|indicated|inferred|measured)\b[^\n]{0,60}\b\d[\d,.]*\s*(?:million |M |billion |B )?(?:oz|ounces|tonnes|t|Mt|lbs|pounds|carats|Moz|Koz|Mlbs|Blbs)\b|"
    r"\b(?:increases?|grows?|expands?|doubles?|triples?|boosts?|upgrades?|converts?)\b[^\n]{0,50}\b(?:resources?|reserves?|ounces)\b(?! (?:potential|target))|"
    r"\b(?:resources?|MRE|reserves?|MRMR)\b[^\n]{0,40}\b(?:confirms|shows|demonstrates|highlights|totals|contains|includes|grows|increases|update)\b|\bMRMR\b", re.I)
_V15_RES_PLAN = re.compile(
    r"\b(?:timeline|to (?:update|complete|deliver|prepare|publish|support|define|upgrade|expand|increase|grow|convert|begin|commence)|prepar\w+ (?:for|of)|towards?|"
    r"progress\w* (?:on|towards?|to)|work (?:on|towards?)|(?:MRE|resource)[-\s](?:definition |expansion |conversion |infill )?drilling|in preparation|planned|upcoming|expected|"
    r"(?:by|in) (?:Q[1-4]|early|mid|late|the (?:first|second|third|fourth) quarter|(?:january|february|march|april|may|june|july|august|september|october|november|december)|20\d\d)|"
    r"commenc\w+|initiat\w+|engag\w+|retain\w+|potential|beyond (?:the )?(?:current )?(?:mineral )?resource|outside (?:the )?(?:current )?(?:mineral )?resource|"
    r"below (?:the )?(?:current )?(?:mineral )?resource|target area|exploration target|nears? completion|moving into|adds? (?:a )?(?:second|third|fourth) (?:drill )?rig|"
    r"second (?:diamond )?drill|mobiliz\w+|drill rig)\b", re.I)
_V15_RES_DRILL = re.compile(r"\bintersect\w*|\bintercept\w*|\bdrill\w*|\bassay\w*|\bholes?\b|\bg/t\b|\bover \d", re.I)
_V15_RES_HIST = re.compile(r"\bhistor\w+ (?:\w+ ){0,3}(?:resources?|estimates?|reserves?)\b|\bexploration target\b", re.I)
_V15_RES_TECREP = re.compile(r"\b(?:files?|filed|filing of|completes?|publishes?|announces? (?:the )?filing of)\b[^\n]{0,40}\b(?:technical reports?|NI\s?43-101|43-101 reports?)\b", re.I)
_V15_RES_STUDY = re.compile(r"\bpreliminary economic assessment\b|\bPEA\b|\bpre-?feasibility\b|\bPFS\b|\bfeasibility study\b|\bFS\b|\bDFS\b|\bscoping study\b|"
                            r"\bintegrated development plan\b|\beconomic\b", re.I)
_V15_RES_IN_OC = re.compile(r"\b(?:mineral )?resource estimate\b|\bMRE\b|\bmineral resources?\b|\breserves?\b|\bM&I\b|\binferred\b|\bindicated\b", re.I)

# ---- Regulatory & Compliance ------------------------------------------------------------------------------------------
_V15_REG_REAL = re.compile(r"\bsecurities commission\b|\b(?:BCSC|OSC|ASC|AMF|FCAA|SEC|FINRA|IIROC|CIRO|ASIC|ASX)\b|\bregulat\w+\b|\bcontinuous disclosure\b|"
                           r"\bat the request of\b|\brequest(?:ed)? by\b|\bstaff of\b|\breview by\b|\bcease trade\b|\bMCTO\b|\bcompliance\b|\bexchange\b|\bTSXV?\b|\bCSE\b|"
                           r"\bearly warning\b|\bdelay\w* in (?:the )?filing\b|\bfiling delay\b|\blate filing\b|\bdisclosure (?:review|deficienc\w+|standards)\b|\bNI 43-101\b|\b43-101\b|\bnon-?compliant\b|\bpromotion\b|\bOTC Markets\b", re.I)

_V15_CODES = ("mna", "jv", "met", "dev", "drl", "res", "reg")
_V15_NONMINING = re.compile(r"\bETH\b|\bethereum\b|\bsolana\b|\bstaking (?:program|rewards|pool)\b|\bvalidator nodes?\b|\bdigital assets?\b|\btreasury strategy\b", re.I)
_V15_JVX = re.compile(r"\bjoint[-\s]?ventures?\b|\bJVs?\b", re.I)


_V15_OPT_HEADCTX = re.compile(r"\bacqui\w+|\bpurchas\w+|\binterest in\b|\bagreements?\b|\bLOI\b|\bletter of intent\b|\bterm sheet\b|\btransaction\b|\bdeal\b|"
                              r"\bvend\w+|\bexercis\w+|\bearn\w*|\bland\b|\bclaims?\b|\bpropert(?:y|ies)\b|\bconsolidat\w+|\bexpan\w+|\bamend\w*|\bpayments?\b|"
                              r"\bfootprint\b|\bhectares?\b|\btenements?\b|\bincreas\w+|\bdoubles?\b|\badds?\b|\bnew (?:[\w-]+ ){0,3}(?:project|prospect)s?\b", re.I)
_V15_FINHEAD = re.compile(r"\bprivate placement\b|\bbought deal\b|\bofferings?\b|\bfinancings?\b|\bLIFE\b|\bflow[-\s]through\b|\bgross proceeds\b|\bproceeds of\b", re.I)
_V15_FINOPT = re.compile(r"\b(?:underwriter|agent|broker|finder)s?['’]?s?['’]? options?\b|\bover[-\s]{0,2}allotment options?\b|\bgreenshoe\b", re.I)


def _v15_mna(h, oc, ho, lead=None):
    if _V15_EW.search(h):
        hx = re.sub(r"(?i)take[-\s]?over bids and issuer bids|take[-\s]?over bids", " ", h)
        if not re.search(r"(?i)\bmerg\w+|\barrangement\b|\b(?:offer|bid) (?:to acquire|for)\b|\btender\b", hx):
            return ("mna:early-warning", "reg")
    if _V15_MNA_CORP.search(h) or re.search(r"(?i)\bstrategic (?:review|alternatives)\b", h):
        return None
    hr = _V15_ROY_CO.sub(" ", h)
    asset_deal = re.search(r"(?i)\b(?:sale|sells?|sold|acqui\w+|purchas\w+)\b[^\n]{0,40}\b(?:project|property|properties|mine|deposit|claims|assets?)\b", hr) and not \
        re.search(r"(?i)\b(?:sale|sells?|sold|acqui\w+|purchas\w+|buy\w*)\b[^\n]{0,20}\b(?:royalt|NSR|NPI|GSR|stream)", hr)
    if _V15_ROY.search(hr) and not asset_deal and not (re.search(r"(?i)\binterest in\b", hr) and not re.search(r"(?i)\b(?:royalty|NSR|stream|GSR|NPI) interests?\b", hr)):
        rest = re.sub(r"(?i)\b(?:on|at|over|covering|in|for) (?:the |its |a |an )?(?:[\w'’.-]+ ){0,5}(?:project|property|properties|claims|mine|deposit|assets?)\b", " ", hr)
        if not re.search(r"(?i)\b(?:project|property|properties|claims|mine|deposit)\b", rest):
            return ("mna:royalty-deal", "roy")
    hopt = _V15_OPTION.search(_V15_STOCK_OPT.sub(" ", h))
    if not hopt and (_V15_FINOPT.search(h) or _V15_FINHEAD.search(h)) and not re.search(r"(?i)\bacqui\w+|\bmerg\w+|\bpurchas\w+|\bstak\w+|\bclaims\b", h) and \
            (_V15_FINOPT.search(h) or _V15_OPTION.search(_V15_STOCK_OPT.sub(" ", ho))):
        return ("mna:financing-only", "")
    if _V15_OPTION.search(_V15_STOCK_OPT.sub(" ", ho)) and not _V15_BOUGHT.search(ho) and not re.search(
            r"(?i)\b100% (?:acquisition|ownership|owned|interest|control)\b|\bacqui\w+ (?:of )?(?:a |the remaining )?100%|\bfull ownership\b", h) and not (
            re.search(r"(?i)\bsells?\b|\bsale of\b|\bsold\b", h) and not _V15_OPTION.search(h)):
        if not hopt and not _V15_OPT_HEADCTX.search(h):
            return ("mna:option-context", "")
        return ("mna:option-earn-in", "opt")
    if _V15_STAKE.search(h) and not _V15_BOUGHT.search(ho):
        if re.search(r"(?i)\bstak\w+\b", ho) or not re.search(r"(?i)\bacqui\w+\b|\bpurchas\w+\b", h):
            return ("mna:staking-land", "opt")
    if not _V15_MNA_CORE.search(h) and not (oc and _V15_MNA_CORE.search(oc)) and not (lead and _V15_MNA_CORE.search(lead)):
        return ("mna:no-deal-words", "")
    return None


_V15_JV_DEAL = re.compile(
    r"\bagreement\b|\btransaction\b|\bMO[Uu]\b|\bmemorandum\b|\bLOI\b|\bletter of intent\b|\bterm sheet\b|\bearn[-\s]?in\b|\binterests?\b|\bstake\b|"
    r"\bform(?:s|ed|ing|ation)?\b|\bsign\w*|\benter\w*|\bestablish\w*|\bcreat\w+|\bcomplet\w+ (?:of )?(?:the )?(?:[\w'’-]+ ){0,4}(?:JV|joint[-\s]?venture)|"
    r"\bconsolidat\w+|\bconver\w+|\bpayments?\b|\bdistribution\b|\bcontribut\w+|\bfund\w*|\bbudget\b|\bterminat\w+|\bdissol\w+|\brestructur\w+|"
    r"\brenew\w*|\bextend\w*|\bexpand\w* (?:its |the |our )?(?:[\w-]+ )?(?:partnership|alliance|collaboration|JV|joint venture)|\bincreas\w+ (?:its )?(?:[\w-]+ )?(?:collaboration|interest|stake|ownership)|"
    r"\bmerg\w+|\bacqui\w+|\bsells?\b|\bsale\b|\bpartners? with\b|\bpartnered\b|\bteam\w* up\b|\bjoin\w* forces\b|\b(?:alliance|collaboration|cooperation|co-operation|partnership|JV|joint venture) (?:with|between|agreement)\b|"
    r"\bstrategic\b|\bupdate on (?:the )?(?:[\w'’-]+ ){0,5}(?:JV|joint[-\s]?venture|partnership|alliance|MOU)\b|\bwebinar\b|\bjoint development\b|\bjointly\b|\bco-?develop\w*|"
    r"\bselected (?:by|to)\b|\bparticipat\w+|\bpartnership\b|\balliance\b|\bconsortium\b|\bcollaborat\w+|\bcooperation\b|\bnations?\b|\bfirst nations?\b|\bindigenous\b|"
    r"\bm[eé]tis\b|\binuit\b|\bcommunit\w+|\buniversit\w+|\binstitut\w+|\bgovernment\b|\breach\w* (?:an )?agreement\b|\bconclud\w+|\bto (?:JV|joint[-\s]?venture)\b|\bunwind\w*|\bbuys?[-\s]?outs?\b|\bnegotiat\w+|\bnew (?:[\w-]+ ){0,4}partner\b|\bannounc\w+ (?:a |the )?(?:new |proposed )?(?:JV|joint[-\s]?venture)\b", re.I)
_V15_JV_CTXMASK = re.compile(r"\bin (?:partnership|collaboration|cooperation|co-operation|conjunction) with\b|\b(?:JV|joint[-\s]?venture) partners?(?:['’]s)?\b|"
                             r"\bpartner compan\w+\b|\boperated by\b|\b(?:under|as part of) (?:its |the |a )?(?:strategic )?(?:alliance|partnership|joint venture|JV)(?: agreement)?(?: with)?\b", re.I)
_V15_JV_TOPIC = re.compile(
    r"\bdrill\w*|\bassays?\b|\bintersect\w*|\bintercept\w*|\bholes?\b|\bexplor\w+|\bprogram\w*|\bcampaign\b|\bsurvey\b|\bsampl\w+|\btrench\w*|\bdiscover\w*|"
    r"\bresults?\b|\bproduction\b|\bproduces?\b|\bresources?\b|\breserves?\b|\bmineraliz\w+|\bmineralis\w+|\bg/t\b|\btargets?\b|\bgeophysic\w+|\bdiamonds\b|"
    r"\bmanagement\b|\bappoint\w*|\blawsuit\b|\bplacement\b|\bfinancing\b|\bdeposit size\b|\buranium\b[^\n]{0,30}\b(?:zone|mineraliz\w+)\b", re.I)
_V15_JV_CSR = re.compile(r"\bmalaria\b|\bschools?\b(?! of mines)|\becoschools?\b|\bconservation\b|\bprotected\b|\bcharit\w+|\bdonat\w+|\bvaccin\w+|\baward\w*\b|"
                         r"\bconference\b|\bsummit\b|\bcapital event\b|\bpanelist\b|\bmember(?:ship)? of\b|\bfounding member\b|\bmarketing alliance\b|\bcongratulat\w+|"
                         r"\bapplauds?\b|\bhighlights\b|\bcomments? on\b|\bseeks?\b|\breviewing\b", re.I)
_V15_JV_SALE = re.compile(r"\b(?:MO[Uu]|memorandum of understanding|partnership|letter of intent|LOI)\b[^\n]{0,40}\b(?:for (?:the )?sale of|to supply|supply of|offtake|off-take|"
                          r"US\$\s?\d|to acquire (?:a )?building)\b|\b(?:sale of|to supply|offtake)\b[^\n]{0,40}\b(?:MO[Uu]|memorandum of understanding)\b", re.I)
_V15_JV_IR = re.compile(r"\bpartner\w*\b[^\n]{0,60}\b(?:VRify|investor relations|investor awareness|market(?:ing)? (?:strategy|awareness|efforts)|awareness|"
                        r"investment publishing|drill(?:ing)? contractor|geological services|ExploreTech|IR (?:firm|campaign|program|services))\b|"
                        r"\bVRify\b[^\n]{0,30}\bpartner\w*|\bpartnership to (?:elevate|boost|enhance) (?:marketing|investor)", re.I)


def _v15_jv(h, oc, ho):
    if _V15_JV_IR.search(h):
        return ("jv:vendor-ir", "mkt" if re.search(r"(?i)investor|market|awareness|publishing|IR\b", h) else "")
    if _V15_JV_CSR.search(h) and not re.search(r"(?i)\b(?:agreement|MO[Uu])\b[^\n]{0,40}\b(?:first nations?|indigenous|m[eé]tis|community)\b", h):
        return ("jv:csr-event-comment", "")
    if _V15_JV_SALE.search(h) and not _V15_JVX.search(h):
        return ("jv:sale-supply-mou", "")
    h2 = _V15_JV_CTXMASK.sub(" ", h)
    if _V15_JV_TOPIC.search(h2) and not _V15_JV_DEAL.search(h2):
        return ("jv:name-or-context", "")
    return None


_V15_MET_TESTISH = re.compile(
    r"\btest(?:s|ed|ing|work|works)?\b(?! labs?\b)(?<!acceptance testing)(?<!performance test)|\btrials?\b|"
    r"\b(?:test\w*|metallurg\w*|leach\w*|recovery|flotation|pilot|bench|sort\w*|column|bottle[-\s]roll|mineralog\w*|processing|spheroni[sz]\w+|purification) results\b|"
    r"\bresults (?:from|of) (?:the |its |an? )?(?:\w+ ){0,2}(?:test\w*|metallurg\w*|pilot|leach\w*|flotation|sort\w*|bench)|"
    r"\brecover(?:y|ies|s|ed|ing)?\b(?<!quarterly gold recovery)(?<!quarterly recovery)(?! underway)(?! (?:significant |first |more )?(?:coarse )?(?:gold|diamonds|carats) from bulk)|"
    r"\bleach\w*(?! (?:pads?|operations?|project|mine|gold (?:mineral )?resource|project feasibility))|\bmetallurg\w+ (?:work|program|results?|test\w*|study|studies|update)|"
    r"\bpositive metallurgy\b|\bproduc\w+ (?:\w+ ){0,3}(?:concentrates?|carbonate|hydroxide|sulphate|sulfate|oxide|anode material|cathode material|metal|graphite|samples?|dor[eé]|briquettes?|pellets?)\b|"
    r"\bcoin[-\s]cell\b|\bhalf[-\s]cell\b|\bpurity\b|\bflow ?sheet\b|\bflotation\b|\bvalidat\w+|\bcontinuous run\b|\breagent\w*|\bspheroni[sz]\w+|\bspheroidi[sz]\w+|"
    r"\bcharacteri[sz]\w+|\bmineralog\w+|\bore[-\s]sort\w*|\bsorting\b|\bbeneficiation\b|\bblister\b|\bpatent\w*|\bmethodology\b|\bprocess (?:development|design|route|optimi[sz]\w+)\b|"
    r"\bpilot[-\s]scale\b|\bbench[-\s]scale\b|\bqualif\w+|\bsamples? (?:shipped|sent)\b|\boutperforms?\b|\blicen[cs]\w+ (?:\w+ ){0,3}technology\b|"
    r"\bmetallurgical (?:bulk )?sampl\w+|\bmetallurgical lab\w*|\bscale[-\s]up\b|\bbioleach\w*|\bmetallurg\w+ (?:progress|evaluation|assessment|advances?|milestone)\b|"
    r"\bconcentrate (?:production|results|grad\w+)\b|\b(?:pilot|demonstration|demo)[-\s](?:scale |plant|facility)", re.I)
_V15_MET_OPS = re.compile(
    r"\bcommission\w*|\bconstruction\b|\bramp[-\s]?up\b|\bcommercial production\b|\bnameplate\b|\bthroughput\b|\bproduction (?:at|from|results|update)\b|\brecord\b[^\n]{0,30}\bproduction\b|"
    r"\bfull production\b|\bmineral processing (?:at|update|during)\b|\bupdate (?:on|for) (?:the )?[\w\s,'’-]{0,60}(?:processing plant|mill|smelter|refinery|concentrator)\b|"
    r"\bquarterly gold recovery\b|\brecovery underway\b|\bresults at \w+ with\b|\bpermitting process\b|\bships? (?:a )?\d|\bofftake\b|\bdemonstration plant update\b|"
    r"\bprocessing (?:of )?(?:ore|material|stockpiled)\b|\bprocess(?:es|ed)? (?:ore|\d)|\btoll (?:milling|processing)\b|\bgroundbreaking\b|\bground[-\s]breaking\b|\bequipment\b|"
    r"\bfactory acceptance\b|\bfatalit\w+|\boperations? update\b|\brestart\w*|\btailings (?:re-?)?processing\b|\bre-?processing\b|\boperating results\b|"
    r"\bmilling capacity\b|\bperformance test\b|\bcoating line\b|\brecycling line\b|\bnears? completion\b|\bprogress update\b|\bsite\b|\brelocat\w+|"
    r"\bheap leach (?:operations?|pads?|project)\b|\bmodifications\b|\bcircuit\b|\bmill\b|\bsmelter\b(?! tests?)|\bmanufacturing\b|\bsubsidiary\b|\bco-?develop\w*", re.I)
_V15_MET_DEVADD = re.compile(r"\bcommission\w*|\bconstruction\b|\bramp[-\s]?up\b|\bcommercial production\b|\bnameplate\b|\bthroughput\b|\btoll (?:milling|processing)\b|"
                             r"\bfatalit\w+|\brestart\w*|\bmilling capacity\b|\bprocessing (?:of )?ore\b|\bgroundbreaking\b|\brecord\b[^\n]{0,30}\bproduction\b", re.I)
_V15_MET_WORDONLY = re.compile(r"\bmetallurgical (?:silica|coal|grade|core|drill\w*|holes?|society|institute)\b|\bheap[-\s]leach\b|\bbulk[-\s]samples?\b|\bbulk sampling\b", re.I)
_V15_MET_DEAL = re.compile(r"\bcongratulat\w+|\bapplauds?\b|\b(?:acqui\w+|purchas\w+|to buy)\b[^\n]{0,60}\b(?:plant|mill|facility|refinery|smelter)\b|"
                           r"\b(?:permits?|licen[cs]e|approv\w+|water right)\b[^\n]{0,60}\b(?:plant|mill|facility|refinery|heap leach)\b|"
                           r"\b(?:letter of intent|LOI|MOU|joint venture|option agreement|framework agreement)\b[^\n]{0,80}\b(?:plant|mill|facility|refinery|smelter)\b|"
                           r"\b(?:plant|mill|facility|refinery|smelter)\b[^\n]{0,60}\b(?:letter of intent|LOI|MOU|joint venture|option agreement)\b", re.I)
_V15_MET_OTHER = re.compile(r"\bcongratulat\w+|\bapplauds?\b|\b(?:acqui\w+|purchas\w+|to buy)\b[^\n]{0,60}\b(?:plant|mill|facility|refinery|smelter|processing)\b|"
                            r"\b(?:permits?|licen[cs]e|approv\w+|water right)\b[^\n]{0,60}\b(?:plant|mill|facility|refinery|heap leach)\b|\b(?:financing|loan|letter of (?:interest|support))\b|"
                            r"\b(?:letter of intent|LOI|MOU|joint venture|option agreement|framework agreement)\b[^\n]{0,80}\b(?:plant|mill|facility|refinery|smelter)\b|"
                            r"\b(?:plant|mill|facility|refinery|smelter)\b[^\n]{0,60}\b(?:letter of intent|LOI|MOU|joint venture|option agreement)\b", re.I)


_V15_MET_STUDYKEEP = re.compile(r"\b(?:pilot|demonstration|demo)[-\s](?:scale |plant|facility)|\bstud(?:y|ies)\b[^\n]{0,60}\b(?:smelter|refinery|processing|plant)\b|"
                                r"\b(?:smelter|refinery|processing plant)\b[^\n]{0,60}\bstud(?:y|ies)\b", re.I)


def _v15_met(h, oc, ho):
    if _V15_MET_STUDYKEEP.search(h):
        return None
    if _V15_MET_DEAL.search(h) and not re.search(r"(?i)\bresults?\b|\brecover\w*|\btest\w* (?:show|confirm|deliver|achiev)\w*", h):
        return ("met:deal-permit-comment", "")
    if _V15_MET_TESTISH.search(h):
        return None
    if _V15_MET_JOB.search(h):
        return ("met:job-title", "mgt")
    if _V15_MET_OTHER.search(h):
        return ("met:deal-permit-comment", "")
    if _V15_MET_OPS.search(h):
        return ("met:plant-operations", "dev" if _V15_MET_DEVADD.search(h) else "")
    if _V15_MET_WORDONLY.search(h):
        return ("met:word-only", "")
    return None


_V15_DEV_SITEPREP = re.compile(
    r"\b(?:roads?|roadwork|drill (?:pads?|sites?|roads?)|pads?|camp|access|gravel work|trails?|airstrip|bridge)\b[^\n.;]{0,30}\bconstruction\b|"
    r"\bconstruction of (?:\w+ ){0,3}(?:drill|access|roads?|camp|pads?|trail)|\b(?:site access|road construction) contractor\b|\bdrill site preparations?\b|"
    r"\bsecures? [\w\s]{0,30}construction for\b", re.I)
_V15_DEV_COMMENT = re.compile(r"\bcongratulat\w+|\bapplauds?\b|\bpraises?\b|\bclarifies\b|\bcomments? on\b|\bschool\b|\bvaccinat\w+|"
                              r"\bpublic (?:school|hospital|health)\b|\bcommunity (?:centre|center|program)\b", re.I)
_V15_DEV_STRONG = re.compile(
    r"\bconstruction (?:decision|begins|began|commence\w*|start\w*|progress\w*|update|milestone|complete\w*|underway|continues|advanc\w+|activities|"
    r"is \d+% complete|on (?:track|schedule)|of (?:the )?(?:mine|mill|plant|processing|concentrator|open pit|underground|decline|shaft|heap leach|tailings|refinery|smelter))\b|"
    r"\b(?:starts?|begins?|commence\w*|completes?|advances?|initiat\w+) (?:mine |plant |mill |full[-\s]scale |main |early )?construction\b|"
    r"\bfirst (?:gold|silver|dor[eé]|pour|concentrate|ore|production|shipment|blast|cathode|anode|lithium|uranium|copper)\b|\bramp[-\s]?up\b|\bcommercial production\b|\bnameplate\b|"
    r"\bthroughput\b|\bmining operations\b|\bmine operations\b|\bofftake\b|\boff-take\b|\bfatal\w*\b|\bcasualty\b|\bwildfire\b|\bevacuation\b|\bfire\b|\bflood\w*\b|"
    r"\bsuspen\w+ (?:of )?(?:operations|mining|production|processing|activities)\b|\bcare and maintenance\b|\bgroundbreaking\b|\bground[-\s]breaking\b|\bbreaks? ground\b|"
    r"\bproduc\w+\b[^\n]{0,20}\b\d|\bproduction continuity\b|\boperat\w+ in line\b|\bcovid\w*\b|\bpandemic\b|\bunderground development\b|\bshaft sinking\b|"
    r"\bmine plan\b|\bstart of construction\b|\bconstruction permits?\b|\bpermits? (?:for|to (?:start|begin)) (?:[\w-]+ ){0,3}construction\b|\ballowing (?:the )?start of construction\b|"
    r"\b(?:approval|permit) (?:of|for) construction\b|\bpermits? for (?:the )?(?:[\w-]+ ){0,3}(?:mine|underground mine|plant) construction\b|\bfor (?:underground )?mine construction\b|\brestarts? mining\b|\bmining contract(?:or|s)?\b|\bcontract mining\b|\bapproves? (?:the )?construction\b|\bconstruction approv\w+|\blabou?r action\b|\bcontinu\w+ to operate\b|\bre-?enter\w*\b[^\n]{0,30}\bmine\b|"
    r"\bdecline\b|\bsupply (?:\w+ ){0,3}agreement\b|\bto supply\b|\bengineering,? procurement\b|\bEPCM?\b|\bprocurement\b|\blong[-\s]lead\b|\bquarr\w+\b|\bstrike\b|\bblockade\b|\bstockpil\w+|\bprocessing (?:of )?ore\b|\bmill (?:restart|expansion|upgrade|refurbishment)\b|"
    r"\b(?:restart\w*|re-?open\w*) (?:of )?(?:the )?(?:[\w'’-]+ ){0,3}(?:mine|mill|mining|plant|operations|production)\b|"
    r"\bcommissioning (?:of )?(?:the )?(?:[\w-]+ ){0,5}(?:plant|mill|concentrator|facility|circuit|module|line)\b|\bcommencement of (?:[\w-]+ ){0,2}construction\b|\bportal\b|\b(?:toll|custom) mill\w*|\bconstruction plans?\b|"
    r"\b(?:mine )?development (?:and [\w-]+ )?update\b", re.I)
_V15_DEV_WEAK = re.compile(
    r"\bcommission(?:s|ed|ing)? (?:a |an |the )?(?:[\w-]+ ){0,4}(?:study|studies|analysis|review|report|survey|assessment|PEA|audit|evaluation)\b|\bawards? (?:the )?(?:[\w'’ -]{0,40})study\b|"
    r"\b(?:MOU|memorandum|framework (?:cooperation )?agreement|cooperation agreement|development agreement|letter of intent|LOI|heads of agreement|partnership agreement|project alliance|term sheet)\b|"
    r"\b(?:permit\w*|approv\w+|decree|EIA|ESIA|EIS|rezoning|completeness review|application|environmental (?:work|assessment|impact))\b|"
    r"\bconstruction (?:financing|facility|loan|funding|capital)\b|\b(?:capex|guarantee|letter of (?:interest|support))\b|\bloan\b[^\n]{0,40}\bconstruction\b|"
    r"\bcommission(?:s|ed|ing)? (?:[\w-]+ ){0,4}(?:pilot plant|reactors?|lab\w*)\b|\bore[-\s]sorting\b|\btest work\b|\bin the lab\b|"
    r"\b(?:appoints?|leadership|project director)\b|\btest mining scenario\b|\bevaluat\w+|\breadiness\b|\btowards? (?:a )?(?:construction|production) decision\b|"
    r"\boptimi[sz]ation work\b|\boptions study\b|\bexpansion study\b|\bengineering contract\b|\bbridging engineering\b|\bmine development associates\b|\bMDA\b|"
    r"\b(?:adjoins|adjacent to|adjoining|next to|located near|near)\b[^\n]{0,60}\b(?:mine|construction)\b|\bin advance of\b|"
    r"\boperations? update\b|\boperational update\b|\brestarts? (?:\w+ )?operations\b|\bmineral development fund\b|"
    r"\bmine development corp\w*\b|\bconstruction and engineering\b|\bfeedstock\b|\bprice sensitivity\b", re.I)


def _v15_dev(h, oc, ho, stage):
    if _V15_DEV_SITEPREP.search(h) and re.search(r"(?i)\bdrill\w*|\bexplor\w+|\bcamp\b|\bpads?\b|\btrail\b", h) and \
            not re.search(r"(?i)\b(?:mine|mill|plant|processing|decline|shaft|pit) construction\b|\bconstruction of (?:the )?(?:mine|mill|plant)", h):
        return ("dev:site-prep", "exp" if re.search(r"(?i)\bdrill|\bexplor", h) else "")
    if _V15_DEV_COMMENT.search(h) and not _V15_DEV_STRONG.search(re.sub(r"(?i)\bcongratulat\w+[^\n]*", " ", h)):
        return ("dev:comment-csr", "")
    hm = _V15_DEV_NAME.sub(" ", h)
    if _V15_DEV_STRONG.search(hm):
        if re.search(r"(?i)\boperations? update\b|\boperational update\b|\brestarts? (?:\w+ )?operations\b|\bincident\b|\bcovid|\bpandemic", hm) and stage == "E" \
                and not re.search(r"(?i)\bfatal|\bmine\b|\bmill\b|\bplant\b", hm):
            return ("dev:explorer-operations", "")
        return None
    if stage == "E" and re.search(r"(?i)\blost[-\s]time\b|\bsafety milestone\b|\bincident\b", hm) and not re.search(r"(?i)\bfatal|\bmine\b|\bmill\b|\bplant\b", hm):
        return ("dev:explorer-operations", "")
    if hm != h and not _V15_DEV_WEAK.search(hm):
        return ("dev:name-only", "")
    if _V15_DEV_WEAK.search(hm):
        if re.search(r"(?i)\boperations? update\b|\boperational update\b", hm) and stage in ("P", "D", "R"):
            return None
        return ("dev:plans-permit-finance-name", "")
    return None


_V15_DRL_ANYDRILL = re.compile(
    r"\bdrill\w*|\bholes?\b|\bintersect\w*|\bintercept\w*|\bcores?\b|\bboreholes?\b|\bRC\b|\bDDH\b|\bdiamond\b|\bin[-\s]fill\b|\bstep[-\s]?outs?\b|\bdownhole\b|\bauger\w*|"
    r"\bsonic\b|\bpercussion\b|\bmetres? (?:of|grading|@)|\bm @|\bover (?:a )?\d[\d.,]*\s*(?:m|metres|meters|ft|feet)\b|\b[A-Z]{1,6}[-_]?\d{2}[-_]\d{1,4}\b|\b[A-Z]{2,6}(?:DD|RC)\d{2,}", re.I)
_V15_DRL_ANYSAMP = re.compile(r"\b(?:grab|rock|chip|channel|trench\w*|outcrop|soil|till|boulders?|float|prospecting|mapping|reconnaissance|panel|stream sediment)\b|\bsampl\w+", re.I)


def _v15_drl(h, oc, ho, lead=None):
    if _V15_DRL_HIST.search(h) and not re.search(r"(?i)\bdrilling (?:at|on|program)\b|\bdrills\b|\bdrilled\b|\bintersects?\b|\bhits\b|\bvalidat\w+|\btwin\w*|\bconfirm\w*|\bnew\b|\bextend\w*", h):
        return ("drl:historical-or-recap", "")
    if _V15_DRL_MET.search(h) and not re.search(r"(?i)\bintersect\w*|\bintercept\w*|\bdrill (?:holes?|results?)\b|\bholes?\b", h) and \
            not (re.search(r"(?i)\bdrill\w*", h) and _V15_DRL_RESULT.search(h)):
        return ("drl:metallurgy", "met")
    t = ho + " || " + (lead or "")
    if not _V15_DRL_ANYDRILL.search(t):
        if _V15_DRL_ANYSAMP.search(t):
            return ("drl:surface-sampling", "smp")
        return None
    if _V15_DRL_PLAN.search(h) and not _V15_DRL_RESULT.search(re.sub(r"(?i)\bdrill(?:ing)? (?:program|campaign)\b", " ", h)):
        return ("drl:program-no-results", "exp")
    return None


_V15_RES_STRONGPLAN = re.compile(
    r"\btimeline\b|\bprepar\w+ (?:for|of)\b|\bpreparation\b|\b(?:to|will) (?:update|upgrade|increase|complete|deliver|publish)\b|\btowards?\b|"
    r"\bprogress (?:on|towards?|to)\b|\bby (?:the )?(?:end of |mid-?|early |late )?(?:Q[1-4]|(?:january|february|march|april|may|june|july|august|september|october|november|december)|20\d\d)\b|"
    r"\bbeyond (?:the )?(?:current )?(?:mineral )?resource\b|\b(?:MRE|resource)[-\s](?:definition |expansion |conversion |infill )?drill\w*|\binitiat\w+|\bcommenc\w+ work\b|"
    r"\bpotential to (?:upgrade|expand|increase|grow)\b|\bupdates? on (?:the )?(?:[\w'’-]+ ){0,5}(?:resource|MRE)\b|\bresource target\b|"
    r"\badds? (?:a )?(?:second|third|fourth) (?:diamond )?drill\b|\bmobiliz\w+|\bupcoming\b|\bplanned\b|\bexpected\b", re.I)
_V15_RES_DIRECT = re.compile(
    r"\b(?:announces?|announced|reports?|delivers?|releases?|completes?|completed|unveils?|declares?|updates?(?! on)|publishes?|highlights|continues to (?:expand|grow))\b "
    r"(?:[\w'’&,.-]+ ){0,6}(?:mineral )?(?:resources?|reserves?|MRE|resource estimate|MRMR)\b(?! (?:update )?(?:timeline|drilling|target|potential|program))|"
    r"\b\d[\d,.]*\s*(?:million |M )?(?:[\w-]+ ){0,2}(?:indicated|inferred|measured)\b|\bincreases? (?:\w+ ){0,3}tonnage\b", re.I)
_V15_RES_NUM = re.compile(r"\b\d[\d,.]*\s*(?:million |M |billion |B )?(?:oz|ounces|tonnes|t|Mt|lbs|pounds|carats|Moz|Koz|Mlbs|Blbs)\b|\b\d[\d.]*\s*%", re.I)


def _v15_res(h, oc, ho):
    if not _V15_RES_WORD.search(h):
        if _V15_RES_TECREP.search(h) or (oc and _V15_RES_REPORT.search(oc)):
            return None
        return ("res:no-resource-words", "")
    if _V15_RES_HIST.search(h) and not _V15_RES_NUM.search(h) and not _V15_RES_DIRECT.search(h) and not re.search(r"(?i)\b(?:maiden|initial|updated?|new|current|NI 43-101 compliant)\b[^\n]{0,30}\b(?:resource|MRE)\b", _V15_RES_HIST.sub(" ", h)):
        return ("res:historical", "")
    if _V15_RES_STRONGPLAN.search(h) and not _V15_RES_NUM.search(h) and not _V15_RES_DIRECT.search(h) and not re.search(r"(?i)\b(?:files?|filed|filing)\b", h):
        return ("res:plans", "")
    if _V15_RES_TECREP.search(h) or re.search(r"(?i)\bNI\s?43-101\b|\btechnical report\b", h):
        if not re.search(r"(?i)\bresource|\breserve|\bMRE\b", h) and (_V15_RES_STUDY.search(h) or (oc and _V15_RES_STUDY.search(oc) and not _V15_RES_IN_OC.search(oc))):
            return ("res:study-report", "")
        return None
    if _V15_RES_REPORT.search(h) or _V15_RES_DIRECT.search(h):
        return None
    if _V15_RES_PLAN.search(h) or _V15_RES_DRILL.search(h):
        return ("res:plans-or-drilling", "")
    return None


_V15_REG_CORRONLY = re.compile(r"\bcorrect(?:s|ed|ion|ions|ive)?\b|\berratum\b|\bclarification of (?:terminology|news release|press release)\b|\bclarifies (?:the )?(?:structure|definition)\b", re.I)


def _v15_reg(h, oc, ho):
    if _V15_REG_REAL.search(h) or (oc and _V15_REG_REAL.search(oc)):
        return None
    if _V15_REG_CORRONLY.search(h) or (oc and re.search(r"(?i)^(?:corporate announcement|news release|press release)\W*$", h) and _V15_REG_CORRONLY.search(oc)):
        return ("reg:own-correction", "")
    return None


_V15_MET_DEVREFILL = re.compile(r"\bbulk[-\s]sampl\w*|\bheap[-\s]leach\w*|\btailings\b|\bplant\b|\bmill(?:ing)?\b|\bsmelt\w*|\brefiner\w*|\bprocessing\b|"
                                r"\bcommission\w*|\bproduction\b|\boperations?\b|\bconstruction\b|\bconcentrator\b|\bfacility\b", re.I)
_V15_KEEP_IF_EMPTY = ("mna", "jv", "dev", "res")
_V15_EMPTY_OK = ("dev:name-only",)   # the tag came only from a company name (Mine Development Associates etc.)


def _v15_apply(cats, h, oc, stage, why=None, lead=None):
    """Core of TAGFIX_V5 on an effective headline h, opening clause oc and company stage."""
    here = [c for c in _V15_CODES if CODE_TO_CAT[c] in cats]
    if not here or not h or is_hollow(h) or _DISCLAIMER_HEADLINE_V8.search(h):
        return cats
    ho = h + " || " + (oc or "")
    s = list(cats)
    dropped, adds, rules = [], set(), {}
    for code in here:
        if code == "mna":
            r = _v15_mna(h, oc, ho, lead)
        elif code == "jv":
            r = _v15_jv(h, oc, ho)
        elif code == "met":
            r = _v15_met(h, oc, ho)
        elif code == "dev":
            r = _v15_dev(h, oc, ho, stage)
        elif code == "drl":
            r = _v15_drl(h, oc, ho, lead)
        elif code == "res":
            r = _v15_res(h, oc, ho)
        else:
            r = _v15_reg(h, oc, ho)
        if r is None:
            continue
        dropped.append(code)
        rules[code] = r[0]
        s.remove(CODE_TO_CAT[code])
        if r[1]:
            adds.add(r[1])
        if why is not None:
            why.append(r[0])
    if not dropped:
        return cats
    nonmining = bool(_V14_NONMINING.search(h) or _V15_NONMINING.search(h))
    for a in ([] if nonmining else adds):
        if a not in dropped and CODE_TO_CAT[a] not in s:
            s.append(CODE_TO_CAT[a])
    if len(s) > 1 and "Corporate Updates" in s:
        s.remove("Corporate Updates")
    if not s:
        codes = [] if nonmining else [c for c in _v14_tags(h, False, stage) if c not in dropped]
        if not codes and oc and not nonmining:
            codes = [c for c in _v14_tags(oc, True, stage) if c not in dropped]
        if not codes and not nonmining and "dev" not in dropped and any(
                rules[c] in ("met:plant-operations", "met:word-only") for c in dropped) and _V15_MET_DEVREFILL.search(h):
            codes = ["dev"]   # bulk samples and plant operations with nothing else: Mine Development, not the Corporate Updates fallback
        if not codes and not nonmining and rules.get("mna") == "mna:option-context":
            codes = ["opt"]   # the opening sentence describes an option and nothing else is tagged: Property Options
        if not codes:
            # Keep-if-empty: for these tags the blind holdout showed drops that would leave only the
            # Corporate Updates fallback were right barely half the time, so the tag stays instead.
            keep = [c for c in dropped if c in _V15_KEEP_IF_EMPTY and rules[c] not in _V15_EMPTY_OK]
            if keep:
                if why is not None:
                    why.append("kept:" + "+".join(keep))
                s = [CODE_TO_CAT[c] for c in keep]
                return [c for c in CATEGORIES if c in set(s)]
        s = [CODE_TO_CAT[c] for c in codes] or ["Corporate Updates"]
        if why is not None:
            why.append("refill:" + ("+".join(codes) or "cor"))
    return [c for c in CATEGORIES if c in set(s)]


def v15_fix(cats: list[str], headline: str | None, recovered: str | None = None, body: str | None = None,
            ticker: str | None = None) -> list[str]:
    """TAGFIX_V5: drop Phase-1 tags (M&A, JV, Metallurgy, Mine Development, Drill Results, Resource Estimates, Regulatory)
    whose only support is a known false trigger. Returns cats unchanged when nothing applies."""
    if not any(CODE_TO_CAT[c] in cats for c in _V15_CODES):
        return cats
    h = norm_head(headline)
    if (not h or is_hollow(h)) and recovered:
        h = norm_head(recovered)
    oc = opening_clause(body) if body else None
    return _v15_apply(cats, h, oc, _v12_stage(ticker, body), None, re.sub(r"\s+", " ", body or "")[:300])


# ===========================================================================
# v16 per-tag false-positive removal (TAGFIX_V6 / FP2 Phase 2, 2026-09-28). Justin: "Let's start Phase 2 of the per-tag
# check ... Write removal rules that drop a tag only when nothing else in the release earns it. Add the correct tag where
# it's clear, and keep the tag rather than leave a release with only Corporate Updates." Patterns come from 250 graded
# random releases per tag (seed 20261010) and were checked on each tag's full population. Runs after TAGFIX_V5 on every
# release. Same shape as v15: a tag is dropped only when a known false trigger is present and nothing else in the headline
# (or, where stated, the opening sentence) earns it. If a drop leaves nothing, the V4 vocabulary refills from the headline,
# then the opening sentence; failing that the dropped tag stays (keep-if-empty).
# Rules marked SCOPE depend on an open scope question and are off until Justin answers.
# ===========================================================================

_V16_SCOPE = {"roy_retained_nsr": False, "roy_company_corporate": False, "ltr_results_outlook": False, "act_rights_plan": False}

_V16_RESULTS = re.compile(
    r"\b(?:first|second|third|fourth|Q[1-4]|quarter\w*|year[-\s]end|annual|fiscal|interim|half[-\s]year\w*|semi[-\s]annual|full[-\s]year|20\d\d|FY\d*)\b[^\n|]{0,60}\b(?:results|financials|highlights)\b|"
    r"\bfinancial statements\b|\bMD&A\b|\bfinancial results\b|\bannual report\b|\bquarterly (?:report|update)\b|\b(?:financial|operating|operational|production) (?:and \w+ )?results\b", re.I)

# ---- Shareholder Letters & Outlook -----------------------------------------------------------------------------------
_V16_LTR_KEEP = re.compile(
    r"\bletter\b(?! of (?:intent|credit|support|interest|understanding|agreement))|\bmessage (?:from|to)\b|\byear[-\s]in[-\s]review\b|\b(?:review|recap|summary) of (?:20\d\d|the year)\b|"
    r"\byear[-\s]end (?:review|recap|summary|update|letter)\b|\b20\d\d (?:year )?(?:in review|review|highlights|achievements|accomplishments|recap|milestones|summary)\b|"
    r"\b(?:outlook|objectives|priorities|milestones|catalysts|goals|strategy|plans?) for (?:20\d\d|the (?:year|coming year|year ahead))\b|\b20\d\d (?:corporate )?(?:outlook|objectives|priorities|goals|guidance)\b|"
    r"\blooks? ahead\b|\bmid[-\s]year (?:review|update|letter)\b|\bupdate to shareholders\b|\bshareholder update\b|\boutlook\b", re.I)
_V16_LTR_STRAT = re.compile(r"\bstrateg\w+|\bplan\b|\bvision\b|\breview\b|\bhighlights\b|\bdirection\b|\bupdate to shareholders\b", re.I)
_V16_LTR_EVENT = re.compile(r"\bwebinar\b|\bwebcast\b|\bpresentation\b|\bpresents? at\b|\bwebsite\b|\bconference\b|\bvideo\b|\bpodcast\b|\binterview\b", re.I)
_V16_LTR_OTHERNEWS = re.compile(
    r"\bspin[-\s]?out\b|\bIPO\b|\bacqui\w+|\bmerg\w+|\bpartner\w*|\bcommercializ\w+|\bcommends?\b|\bapplauds?\b|\bresponds?\b|"
    r"\bdrill\w*|\bintersect\w*|\bexploration\b|\bwork (?:plan|program)\b|\bloan\b|\bdeleverag\w+|\bdebt\b|\bfinancing\b|\bplacement\b|\bwebsite\b|\bmilestone\b|\bNOAA\b|\bpathways?\b", re.I)


def _v16_ltr(h, oc, ho, stage):
    if re.search(r"(?i)\bletter\b(?! of (?:intent|credit|support|interest))|\bmessage (?:from|to)\b|\byear[-\s]in[-\s]review\b", h):
        return None
    if _V16_LTR_EVENT.search(h) and not re.search(r"(?i)\bletter\b|\byear[-\s]in[-\s]review\b", h):
        return ("ltr:event-presentation", "mkt")
    outlook = re.search(r"(?i)\boutlook\b|\bguidance\b|\b(?:objectives|priorities|goals|catalysts) for\b|\blooks? ahead\b", h)
    if _V16_RESULTS.search(h) and not re.search(r"(?i)\b(?:review|recap|summar\w+|highlights and outlook|milestones|achievements|plans|objectives|goals|priorities|moving forward|year ahead|strategy)\b", h):
        if not outlook:
            return ("ltr:results-no-outlook", "fns" if re.search(r"(?i)\bfinancial|\bstatements\b|\bMD&A\b|\bannual report\b", h) else "")
        if _V16_SCOPE["ltr_results_outlook"] and re.search(r"(?i)\b(?:reports?|announces?|releases?|delivers?)\b[^\n]{0,80}\b(?:results|production|financials)\b|\bfinancials\b", h):
            return ("ltr:results-outlook", "")
        return None
    if _V16_LTR_KEEP.search(h):
        return None
    if _V16_LTR_STRAT.search(h) and _V16_LTR_OTHERNEWS.search(h):
        return ("ltr:strategy-word", "")
    if re.search(r"(?i)\bhighlights\b", h) and re.search(r"(?i)\bg/t\b|\b\d[\d.]*\s?m\b|\bintersect|\bdrill", h):
        return ("ltr:strategy-word", "")
    return None


# ---- Royalties & Streams ---------------------------------------------------------------------------------------------
_V16_ROY_NAMES = (r"Electric Royalties|Vox Royalty|Sailfish Royalty|Labrador Iron Ore Royalty|Orogen Royalties|Elemental (?:Altus )?Royalt(?:y|ies)|Osisko Gold Royalties|"
                  r"Empress Royalty|Versamet Royalties|OR Royalties|Vizsla Royalties|Gold Royalty(?= Corp|['’]s)|LunR Royalties|Evolve (?:Strategic Element )?Royalties|Summit Royalties|"
                  r"Nations Royalty|Tanzanian Royalty|CVW (?:Sustainable )?Royalties|Lithium Royalty(?= Corp)|EMX Royalty|Ely Gold Royalties|Music Royalties|Silver Crown Royalties|Uranium Royalty(?= Corp)|"
                  r"Moonlight Royalties|Altius Renewable Royalties|Nova Royalties|Star Royalties|Eagle Royalties|Metalla Royalty(?: (?:&|and) Streaming)?|Royalty North|Arc Mineral Royalties|"
                  r"Pizza Pizza Royalty|Maverix Metals|Prospect and Royalty Generator|Royalty Generator|Royalties Inc\.?")
_V16_ROY_NAME = re.compile(r"\b(?:" + _V16_ROY_NAMES + r")(?:\s+(?:Corp(?:oration)?|Inc|Ltd|Limited|plc|PLC|AG|Exploration))?\.?", re.I)
_V16_ROY_ISSUER = re.compile(r"\b(?:" + _V16_ROY_NAMES + r")(?:\s+(?:Corp(?:oration)?|Inc|Ltd|Limited|plc|PLC|AG|Exploration))?\.?,?\s+(?:board\s+)?(?:announces?|reports?|provides?|closes?|completes?|acquires?|enters?|signs?|declares?|files?|adds?|expands?|increases?|"
                             r"receives?|updates?|notes?|releases?|delivers?|agrees?|grants?|sells?|purchases?|publishes?|urges?|warns?|comments?|confirms?|continues?|launches?|changes?|reaches?|executes?|"
                             r"strengthens?|welcomes?|appoints?|issues?|reaffirms?|recommends?|rejects?|responds?|files|commences?|initiates?|establishes?|finalizes?|secures?|streams?|funds?|invests?)\b|"
                             r"^\W*(?:" + _V16_ROY_NAMES + r")\b", re.I)
_V16_ROY_WORD = re.compile(r"\broyalt(?:y|ies)\b|\bNSR\b|\bNPI\b|\bGSR\b|\bstreams?\b|\bstreaming\b|\bGEOs?\b|\bprecious metals? purchase\b|\bPMPA\b", re.I)
_V16_ROY_CORP = re.compile(r"\btake[-\s]?over\b|\bhostile\b|\bunsolicited\b|\btender\b|\bbid\b|\bIPO\b|\binitial public offering\b|\bname change\b|\bchanges? (?:its )?name\b|"
                           r"\bqualifying transaction\b|\bfiling statement\b|\breverse take[-\s]?over\b|\bregistration statement\b|\bboard\b|\bshareholders\b", re.I)
_V16_ROY_OWNNEWS = re.compile(r"\bresults\b|\bquarter\w*|\bQ[1-4]\b|\brevenue\b|\bGEOs?\b|\bportfolio\b|\bdividend\b|\bguidance\b|\bdeliver\w*|\brecord\b|\bacqui\w+|\bpurchas\w+|\bsells?\b|\bsale\b|\bsold\b|"
                              r"\bbuy[-\s]?back\b|\bcreates?\b|\bgrants?\b|\bcompletes?\b|\bcloses?\b|\bagreement\b|\binterest\b|\bupdate\b|\bproduction\b|\bprogress\b|\bhandbook\b|\basset\b", re.I)
_V16_ROY_FIN = re.compile(r"\bplacement\b|\bfinancing\b|\bofferings?\b|\bsale of (?:\$?[\d,.]+ (?:in )?)?common shares\b|\bshares\b|\bwarrants?\b|\binvestment\b|\bbought deal\b|\bunits\b|\bLIFE\b|\bgross proceeds\b|\bflow[-\s]through\b|\bnotice of meeting\b|\bstock options?\b", re.I)
_V16_ROY_RETAIN = re.compile(r"\b(?:plus|retain\w*|retention of|keep\w*|reserv\w+|with|and|including|subject to)\b[^\n]{0,30}\b\d(?:\.\d+)?\s?%\s*(?:NSR|net smelter|royalty|GSR|NPI)|"
                             r"\b(?:plus|retain\w*|keeps?|reserv\w+)\b[^\n]{0,20}\b(?:an? )?(?:NSR|royalty)\b|\bretain\w* (?:existing )?royalty\b", re.I)
_V16_PROPDEAL = re.compile(r"\bsells?\b|\bsale of\b|\bsold\b|\boptions?\b|\boption agreement\b|\bdivest\w*|\bLOI\b|\bletter of intent\b|\bdisposition\b|\bvends?\b|\bpurchase agreement\b|\bacqui\w+", re.I)


_V16_ROY_NOTROYCO = re.compile(r"\b(?:Tanzanian Royalty|Music Royalties|Royalties Inc|Pizza Pizza Royalty)\b", re.I)


def _v16_roy(h, oc, ho, stage):
    if not _V16_ROY_WORD.search(h):
        return None                                   # tagged from the opening text; nothing here to judge
    rest = _V16_ROY_NAME.sub(" ", h)
    if rest != h and not _V16_ROY_WORD.search(rest):
        if not _V16_ROY_ISSUER.search(h):
            if re.search(r"(?i)\bfinanc\w+|\bfund\w*|\binvest\w+|\bagreement\b|\bsells?\b|\bsale\b|\bsold\b|\bacqui\w+|\bpurchas\w+|\btransaction\b|\bdeal\b|\bchange of business\b|\bchanges? (?:its )?name\b|\bLOI\b|\bterm sheet\b|\bstream\w*|\bspin[-\s]?(?:out|off)\b|\bspinout\b|\bpartnership\b|\bcapital\b|\bpayments?\b|\bvote\b|\bproxy\b|\barrangement\b|\bcombination\b|\bbid\b|\btake[-\s]?over\b|\bshareholders?\b|\bIPO\b", rest):
                return None                           # a deal with the royalty company may itself be a royalty or stream
            return ("roy:company-name", "")           # the royalty company is only named (partner, holder, "About" line)
        own = re.search(r"(?i)\bat (?:the |its )?(?:[\w'’-]+ ){0,5}(?:project|mine|property|operation)s?\b|\broyalt\w+ (?:portfolio|interest|acquisition|financing|update)|\bstream\b|\bupdate\b|\bresults\b|\brevenue\b|\bGEOs?\b|\bdividend\b", rest)
        if _V16_ROY_NOTROYCO.search(h):
            if own:
                return None
            fin = re.search(r"(?i)\bplacement\b|\bfinancing\b|\bofferings?\b|\bsale of (?:[$\w,.]+ )*common shares\b|\bbought deal\b|\bunits\b|\bLIFE\b|\bflow[-\s]through\b|\bgross proceeds\b", h)
            return ("roy:company-name", "fin" if fin else "")   # not a royalty business, only the name says "Royalty"
        if _V16_SCOPE["roy_company_corporate"] and not own and (_V16_ROY_CORP.search(h) or _V16_ROY_FIN.search(h)) and not _V16_ROY_OWNNEWS.search(_V16_ROY_FIN.sub(" ", _V16_ROY_CORP.sub(" ", h))):
            return ("roy:royalty-company-corporate", "")
        return None
    if _V16_SCOPE["roy_retained_nsr"] and _V16_PROPDEAL.search(h) and _V16_ROY_RETAIN.search(h):
        h2 = _V16_ROY_RETAIN.sub(" ", h)
        if not _V16_ROY_WORD.search(_V16_ROY_NAME.sub(" ", h2)):
            return ("roy:retained-nsr", "")
    return None


# ---- Economic Studies ------------------------------------------------------------------------------------------------
_V16_STUDY = r"(?:PEA|PFS|FS|DFS|BFS|pre-?feasibility(?: study)?|feasibility(?: study)?|preliminary economic (?:assessment|evaluation|study)|scoping study|economic (?:study|assessment))"
_V16_ECO_DELIVER = re.compile(
    r"\b(?:announces?|reports?|delivers?|releases?|completes?|completed|files?|filed|filing|publishes?|unveils?|results? (?:of|from)|positive|robust|updated?|optimi[sz]ed|maiden|initial|new|revised|amended|"
    r"commenc\w+|initiat\w+|launch\w*|begins?|starts?|awards?|engages?|selects?|retains?|commissions?|appoints?|progress\w*|advanc\w+|on track|delay\w*|status)\b[^\n]{0,60}\b" + _V16_STUDY + r"|"
    r"\bNPV\b|\bIRR\b|\bafter[-\s]tax\b|\bpayback\b|\bcapex\b|\bcapital cost\b|\bAISC\b|\bmine life\b|\bLOM\b|\blife[-\s]of[-\s]mine\b|\b" + _V16_STUDY + r"\b[^\n]{0,40}\b(?:results|highlights|demonstrates|confirms|shows|outlines|update|underway|progress)", re.I)
_V16_ECO_CONTEXT = re.compile(
    r"\b(?:within|outside|below|beneath|beyond|near|adjacent to|inside|of) (?:and (?:outside|below) )?(?:the )?(?:current |planned |proposed )?" + _V16_STUDY + r" (?:open[-\s])?(?:pits?|shells?|mine plan|resource|area|design)\b|"
    r"\b" + _V16_STUDY + r"[-\s](?:pit|level|stage|grade)\b|\bduring (?:the )?" + _V16_STUDY + r" drilling\b|\b" + _V16_STUDY + r" drilling\b|"
    r"\bin (?:preparation|support) (?:of|for) (?:an? |the |its )?(?:upcoming |planned |future )?(?:\w+ ){0,2}" + _V16_STUDY + r"|\b(?:for|towards?|ahead of|to support|to feed into|in advance of) (?:an? |the |its )?(?:upcoming |planned |future |updated |new )?(?:mineral resource estimate and )?" + _V16_STUDY + r"\b|"
    r"\btimeline (?:for|to) (?:the )?(?:completion of )?(?:[\w/]+ )?" + _V16_STUDY + r"|\b" + _V16_STUDY + r" timeline\b|\bexpects? to (?:deliver|complete|release)\b[^\n]{0,30}\b" + _V16_STUDY + r"|"
    r"\bmoves? forward with (?:an? |the )?" + _V16_STUDY + r"|\bwith (?:robust |positive )?" + _V16_STUDY + r" economics\b|\bafter (?:positive |its )?" + _V16_STUDY + r"\b|\bfollowing (?:the |its )?(?:positive )?" + _V16_STUDY + r"\b|"
    r"\bto (?:help )?(?:fund|finance|advance|support)\b[^\n]{0,60}\b" + _V16_STUDY + r"|\bfunded for\b[^\n]{0,60}\b" + _V16_STUDY, re.I)
_V16_ECO_DRILL = re.compile(r"\bintersect\w*|\bintercept\w*|\bdrill\w*|\bhits?\b|\bg/t\b|\bover \d|\bmetres?\b|\bmeters?\b|\bdiscover\w*|\bmineraliz\w+|\bmineralis\w+|\bassays?\b|\bholes?\b", re.I)
_V16_ECO_FIN = re.compile(r"\bplacement\b|\bfinancing\b|\bofferings?\b|\bwarrant exercise\b|\bexercise of warrants\b|\bproceeds\b|\bflow[-\s]through\b|\bbought deal\b|\braises?\b|\bfunding\b", re.I)
_V16_ECO_MET = re.compile(r"\bmetallurg\w+|\brecover(?:y|ies)\b|\bore[-\s]sort\w*|\btest ?work\b|\btailings\b|\bflotation\b|\bleach\w*|\bconcentrate\b|\bprocess(?:ing)? (?:results|test\w*)\b", re.I)


def _v16_eco(h, oc, ho, stage):
    ctx = _V16_ECO_CONTEXT.search(h)
    if not ctx or re.search(r"(?i)\btechnical report\b|\b43-101\b|\bfil(?:es|ed|ing)\b|\bcorrection\b", h):
        return None
    hm = _V16_ECO_CONTEXT.sub(" ", h)
    if re.search(r"(?i)\b" + _V16_STUDY + r"\b", hm) and _V16_ECO_DELIVER.search(hm):
        return None                                   # a study is also delivered or advanced in its own right
    if re.search(r"(?i)\bNPV\b|\bIRR\b|\bpayback\b|\bafter[-\s]tax\b", h):
        return None
    if _V16_ECO_MET.search(h):
        return ("eco:testwork", "met")
    if _V16_ECO_FIN.search(h):
        return ("eco:funds-study", "fin")
    if _V16_ECO_DRILL.search(h):
        return ("eco:study-mentioned", "drl" if re.search(r"(?i)\bintersect|\bintercept|\bg/t\b|\bover \d|\bhits?\b|\bassays?\b|\bmineraliz|\bmineralis|\bdiscover|\bhigh[-\s]grade\b", h) else "exp")
    return ("eco:study-mentioned", "")


# ---- Production Results ----------------------------------------------------------------------------------------------
_V16_PRD_WORDS = re.compile(r"\bproduc\w+\b|\bounces\b|\boz\b|\btonnes\b|\bGEOs?\b|\bsales\b|\bsold\b|\brecord\b|\boutput\b|\bthroughput\b|\bguidance\b|\bpours?\b|\bshipments?\b|\brevenue\b", re.I)
_V16_PRD_FINOPS = re.compile(r"\bfinancial (?:and|&) operat\w+ (?:results|highlights|update)\b|\bfinancial results and operat\w+ (?:highlights|update)\b|\bfinancial and operat\w+ (?:highlights|update)\b", re.I)
_V16_PRD_MILESTONE = re.compile(
    r"\bcommenc\w+ (?:\w+ ){0,2}(?:mining|operations|milling|processing)\b|\bbegins? (?:\w+ ){0,2}(?:mining|processing|milling)\b|\bstarts? (?:\w+ ){0,2}mining\b|"
    r"\b(?:restart\w*|re-?start\w*|recommenc\w+|resum\w+|reopen\w*) (?:of )?(?:\w+ ){0,3}(?:operations|mining|milling|mine|mill|plant)\b|\bmovement control\b|\bcovid\w*\b", re.I)
_V16_PRD_PLAN = re.compile(r"\bon (?:track|schedule) (?:for|to)\b|\btowards?\b|\bpath to\b|\bplan\w* to\b|\bto (?:re-?)?(?:start|commence|recommence|resume|begin)\b|\bexpect\w*\b|\btarget\w*\b|\bpotential\b|"
                           r"\bpre-?production\b|\bprepar\w+\b|\bdecision\b|\bplanned\b|\bproposed\b|\bexpansion\b", re.I)
_V16_PRD_STUDY = re.compile(r"\b" + _V16_STUDY + r"\b|\beconomic (?:assessment|study|analysis)\b|\bmine plan\b|\bmining plan\b|\blife[-\s]of[-\s]mine\b", re.I)
_V16_PRD_REAL = re.compile(r"\bQ[1-4]\b|\bquarter\w*|\bH[12]\b|\bhalf\b|\bfull[-\s]year\b|\byear[-\s]end\b|\bannual\b|\bmonth\w*\b|\bfiscal\b|\bguidance\b|\bproduction (?:results|update|report|summary|and sales|figures)\b|"
                           r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b|\bresults\b|\bsales\b|\brecord (?:quarterly |annual |monthly )?production\b", re.I)


def _v16_prd(h, oc, ho, stage):
    figs = _V12_PROD_FIGURES.search(h)
    if stage == "D" and _V16_PRD_FINOPS.search(h) and not re.search(r"(?i)\bproduc\w+|\bounces\b|\boz\b|\bpour|\bsales\b|\brecord\b|\bshipment", h):
        return ("prd:developer-operating-results", "fns")
    if _V16_PRD_STUDY.search(h) and not _V16_PRD_REAL.search(h) and re.search(r"(?i)\b" + _V16_STUDY + r"\b|\beconomic (?:assessment|study)\b|\bmin(?:e|ing) plan\b", h):
        return ("prd:study-estimate", "eco" if re.search(r"(?i)\b" + _V16_STUDY + r"\b|\beconomic", h) else "")
    if figs or _V16_PRD_REAL.search(h):
        return None
    if _V16_PRD_MILESTONE.search(h) and not re.search(r"(?i)\b\d[\d,]*(?:st|nd|rd|th) (?:tonne|ounce|oz|pound|carat|bar)|\bmillionth\b|\bproduction milestone\b|\bsuspen\w+|\bcare and maintenance\b|\bcommercial production\b|\bpour\w*|\bcarats?\b|\bdiamonds?\b|\boperational update\b|\boperations update\b|\bproduction update\b|\bclarif\w+|\bexpand\w*", h):
        return ("prd:milestone-no-figures", "dev" if re.search(r"(?i)\bmine\b|\bmines\b|\bmill\w*|\bplant\b|\bmining\b|\bpit\b|\bunderground\b", h) else "")
    if _V16_PRD_PLAN.search(h) and re.search(r"(?i)\bproduction\b|\bmining\b|\boperations\b|\bmine\b", h):
        return ("prd:plans", "dev" if re.search(r"(?i)\bmine\b|\bmill\b|\bplant\b|\bconstruction\b|\brestart|\brecommenc", h) else "")
    return None


# ---- Company Commentary ----------------------------------------------------------------------------------------------
_V16_CMT_DOCS = re.compile(r"\b(?:registration|filing|position|cautionary|financial|management information|information|prospectus|offering) statements?\b|\bstatements? of claim\b|"
                           r"\bforward[-\s]looking (?:information|statements)\b|\bcontains forward[-\s]looking\b", re.I)
_V16_CMT_OWN = re.compile(
    r"\bhighlights\s+(?:[\w'’-]+\s+){0,4}?(?:exploration|project|results|potential|progress|milestones?|historic\w*|market timing|drill\w*|targets?|discovery|opportunit\w+|prospectivity|advantages?|value)\b|"
    r"\bcomments? on (?:the )?(?:presence|quebec|its|our|[\w'’-]+ (?:projects?|property|properties))\b|\bcomments on\b[^\n]{0,30}\b(?:hires|appoints|engages)\b|"
    r"\bresponds? to (?:the )?market with\b|\b(?:responds?|response) to stakeholders?\b|\bdeadline to comment\b|\b(?:public )?comment period\b|\bfeaturing commentary\b|\bmarket commentary from\b|"
    r"\bin response to (?:a )?review by\b|\bfiles? (?:a |its )?response to\b|\bcorrective disclosure\b|\bapplauds? (?:the )?inclusion\b|\bcongratulate (?:[\w.,&'’-]+ ){1,4}for\b(?=[^\n]*\b(?:grant|approval|loan))", re.I)
_V16_CMT_OUTSIDE = re.compile(r"\b(?:government|minister\w*|ministry|premier|president|federal|provincial|court|tribunal|regulator\w*|OTC Markets|IIROC|CIRO|media|article|report by|short seller|activist|dissident|"
                              r"shareholder (?:letter|proposal|requisition)|lawsuit|claim|allegations?|rumou?rs?|tariffs?|polic\w+|executive order|legislation|bill\b|announcement by|decision|ruling|election|price of|gold price|"
                              r"market volatility|unusual|market activity|trading activity|recent (?:news|events|developments|press)|market dynamics|gold market|metals? markets?|supply chains?|defen[cs]e|nearby|neighbou?ring|adjacent|vicinity|prices?|North America|demand|industry|sector)\b", re.I)


def _v16_cmt(h, oc, ho, stage):
    hm = _V16_CMT_DOCS.sub(" ", h)
    if hm != h and not R10_CMT.search(hm):
        return ("cmt:document-statement", "")
    if _V16_CMT_OWN.search(h) and not _V16_CMT_OUTSIDE.search(_V16_CMT_OWN.sub(" ", ho)):
        add = ""
        if re.search(r"(?i)\bcomment period\b|\bdeadline to comment\b", h): add = "per"
        elif re.search(r"(?i)\bcommentary from\b|\bfeaturing\b|\binclusion\b", h): add = "mkt"
        elif re.search(r"(?i)\breview by\b|\bcorrective disclosure\b", h): add = "reg"
        elif re.search(r"(?i)\bexploration\b|\bdrill\w*|\btargets?\b|\bprospectivity\b|\bhistoric", h): add = "exp"
        return ("cmt:own-news", add)
    return None


# ---- Corporate Actions -----------------------------------------------------------------------------------------------
_V16_ACT_REAL = re.compile(r"\bconsolidat\w+ of (?:its |the )?(?:common )?shares\b|\bshare consolidation\b|\bstock split\b|\bforward split\b|\bsplit\b|\bname change\b|\bchange (?:of|its) name\b|\bnew name\b|\brenam\w+|"
                           r"\bcontinuance\b|\bdividend\b|\bdistribution\b|\breturn of capital\b|\bchange of business\b|\bre-?domicil\w+|\bamalgamation\b|\breorgani[sz]ation\b|\bnew (?:trading )?symbol\b|\bshare structure\b|\bclass [AB]\b", re.I)


def _v16_act(h, oc, ho, stage):
    if re.search(r"(?i)\bconsolidat(?:es|ing|ion)\b[^\n]{0,40}\b(?:property|properties|package|claims?|land|district|ground|project|camp|portfolio|ownership|interest)\b|\b(?:property|land|claims?|district) consolidation\b", h) and \
            not re.search(r"(?i)\bshare consolidation\b|\bconsolidat\w+ of (?:its |the )?(?:issued |outstanding |common )*shares\b|\b\d+[-\s:]?(?:for|to)[-\s:]?\d+\b", h):
        return ("act:property-consolidation", "opt" if re.search(r"(?i)claims?|land|property|properties|package|ground", h) else "")
    if _V16_SCOPE["act_rights_plan"] and re.search(r"(?i)\bshareholder rights plan\b|\brights plan\b", h) and not _V16_ACT_REAL.search(re.sub(r"(?i)\brights plan\b", " ", h)):
        return ("act:rights-plan", "")
    return None


# ---- Listings & Exchange ---------------------------------------------------------------------------------------------
_V16_LST_REAL = re.compile(r"\blist(?:s|ed|ing|ings)?\b|\buplist\w*|\bdelist\w*|\bhalt\w*|\bresum\w+|\breinstat\w+|\bsymbol\b|\bticker\b|\bDTC\b|\bOTCQ[BX]\b|\bOTC\b|\bNYSE\b|\bNasdaq\b|\bFrankfurt\b|\bFSE\b|"
                           r"\bgraduat\w+|\bcommenc\w+ trading\b|\bbegins? trading\b|\bstarts? trading\b|\btrading (?:on|under|symbol)\b|\bcease trade order\b|\bCTO\b|\brevocation\b|\btransfer to\b|\bmoves? to\b|\bboard lot\b|\bTier [12]\b", re.I)
_V16_LST_NMC = re.compile(r"\bno material (?:undisclosed )?(?:change|information|news|developments?)\b|\bunaware of any\b|\bnot aware of any\b|\bunusual (?:market|trading)\b|\b(?:recent|market|trading) activity\b|"
                          r"\bat the request of (?:IIROC|CIRO|the (?:Investment Industry|Canadian Investment)|the (?:TSX|exchange))\b|\bmarket (?:rumou?rs?|speculation)\b", re.I)
_V16_LST_MCTO = re.compile(r"\bmanagement cease trade\b|\bMCTO\b|\b(?:notice of )?default (?:status )?(?:update|report|announcement|notice)\b|\bnotice of default\b|\bbi-?weekly (?:default )?(?:status )?(?:update|report)\b|"
                           r"\bdelay\w* (?:in )?(?:the )?(?:annual |interim |quarterly |Q[1-4] )?filing\w*|\bfiling delay\b|\blate filing\b|\bdelayed filing\b|\bstatus update\b", re.I)
_V16_LST_FULLCTO = re.compile(r"\bfailure[-\s]to[-\s]file\b|\bFFCTO\b|\b(?<!management )cease trade order\b(?![^\n]{0,20}\b(?:application|MCTO))|\brevoc\w+|\bresum\w+ trading\b|\breinstat\w+|\btrading (?:halt|suspension)\b|\bhalt\w*|\bdelist\w*|\bsuspen\w+", re.I)


def _v16_lst(h, oc, ho, stage):
    if _V16_LST_NMC.search(ho) and not _V16_LST_REAL.search(h) and not re.search(r"(?i)\bhalt\w*|\bresum", oc or ""):
        return ("lst:market-activity-statement", "reg" if re.search(r"(?i)\bclarif\w+|\bretract\w*|\bcorrect\w*", ho) else "cmt")
    if _V16_LST_MCTO.search(h) and not _V16_LST_FULLCTO.search(h) and not re.search(r"(?i)\bfailure[-\s]to[-\s]file|\bFFCTO\b|\bgeneral cease trade\b|\bcease trade order (?:was )?issued by\b", oc or ""):
        return ("lst:mcto-late-filing", "reg")
    return None


# ---- Property Options & Staking --------------------------------------------------------------------------------------
_V16_OPT_STOCK = re.compile(r"\b(?:stock|incentive|share|employee|director|officer)s?['’]? options?\b(?! agreement)|\bRSUs?\b|\bDSUs?\b|\bPSUs?\b|\bexercise of (?:stock |incentive |share )?options\b(?! (?:on|over|to acquire|for the))|"
                            r"\boptions (?:and RSUs|exercise|exercised|grants?|granted|cancell?ations?|to (?:directors|officers|employees|consultants))\b|\boption (?:grants?|granted|exercise price)\b|\bgrants? (?:of )?(?:\w+ )?options\b|"
                            r"\b(?:underwriter|agent|broker|finder)s?['’]?s?['’]? options?\b|\bover[-\s]{0,2}allotment options?\b|\bgreenshoe\b|\bwarrants?,? (?:and|&) options\b|\boptions? (?:and|&) warrants?\b|\boptions cancell?ations?\b", re.I)
_V16_OPT_REAL = re.compile(r"\boption\w*\b|\bearn[-\s]?in\b|\bearns?\b|\bstak\w+|\bclaims?\b|\bland (?:package|position|holdings?)\b|\bpropert(?:y|ies)\b|\btenements?\b|\blicen[cs]es?\b|\bconcessions?\b|\bhectares\b|\bacqui\w+|\bpurchas\w+|"
                           r"\bprojects?\b|\bexpan\w+|\bground\b|\bblocks?\b|\bprospects?\b|\bLOI\b|\bletter of intent\b|\bvend\w+", re.I)


def _v16_opt(h, oc, ho, stage):
    hm = _V16_OPT_STOCK.sub(" ", h)
    if hm != h and not _V16_OPT_REAL.search(hm):
        return ("opt:stock-options", "cap")
    if re.search(r"(?i)\broyalty buy[-\s]?back\b|\bbuy[-\s]?back (?:of )?(?:the |a |an )?(?:\d+(?:\.\d+)?% )?(?:NSR|royalty)\b", h) and not re.search(r"(?i)\boption agreement\b|\bearn[-\s]?in\b|\bstak\w+", h):
        return ("opt:royalty-buyback", "roy")
    if re.search(r"(?i)\b(?:mining )?fleet\b|\bequipment\b|\bEPC\b|\bEPCM\b|\bmill\b(?! (?:site|tailings|property|claims))", h) and not re.search(r"(?i)\boption\w*|\bearn[-\s]?in\b|\bstak\w+|\bclaims?\b|\bpropert(?:y|ies)\b|\bproject\b|\bmine\b|\bland\b|\bacres?\b|\bhectares?\b|\bposition\b", _V16_OPT_STOCK.sub(" ", re.sub(r"(?i)\bfor (?:the |its )?[\w\s'’-]{0,40}project\b", " ", h))):
        return ("opt:equipment-contract", "dev")
    return None


# ---- Sampling & Geoscience Results -----------------------------------------------------------------------------------
_V16_SMP_RESULT = re.compile(
    r"\bresults?\b|\bassays?\b(?! (?:pending|awaited))|\breturns?\b|\bgrad\w+|\bg/t\b|\bgpt\b|\bppm\b|\bppb\b|\boz/t\b|\b%|\bvalues?\b|\bup to\b|\bhighs?\b|\banomal\w+|\bdiscover\w*|\bconfirms?\b|\bidentif\w+|"
    r"\bdefines?\b|\breveals?\b|\bhighlights?\b|\bintersect\w*|\bmineraliz\w+|\bmineralis\w+|\boutlines?\b|\bdelineat\w+|\bextends?\b|\bexpands?\b|\bvisible gold\b|\bspodumene\b|\bconductors?\b|\btargets? (?:identified|defined|generated)\b|\bdefinition of\b|"
    r"\bsignificant\b|\bhigh[-\s]grade\b|\bstrong\b|\bencouraging\b|\bpositive\b|\bexceptional\b|\bimpressive\b|\bbonanza\b|\bnuggets?\b|\bsulphides?\b|\bsulfides?\b|\bshowings?\b|\bgrains?\b|\bgrams?\b|\bgram/tonne\b|\boz\b|\bvisible\b|\belevated\b|\bradioactiv\w+|\bcps\b|\bzones?\b|\bveins?\b|\btrends?\b|\bcorridor\b|\bsystems?\b", re.I)
_V16_SMP_PROGRAM = re.compile(
    r"\b(?:begins?|began|commenc\w+|starts?|started|initiat\w+|launch\w*|mobiliz\w+|plans?|planned|planning|prepar\w+|to (?:begin|commence|start|conduct|carry out)|underway|in progress|upcoming|scheduled|"
    r"collects?|collected|sends?|sent|submit\w*|ships?|shipped|awaits?|awaiting|pending|receives? (?:a )?permit|permit\w*|dewater\w*|expands? (?:its )?(?:\w+ )?program|"
    r"engag\w+|selects?|contract\w*|retain\w*)\b", re.I)
_V16_SMP_DRILL = re.compile(r"\bdrill\w*|\bdrill ?holes?\b|\bRC\b|\bDDH\b|\bdrill cores?\b|\bboreholes?\b|\bintersect\w*|\bintercept\w*", re.I)
_V16_SMP_SURF = re.compile(r"\bunderground\b|\bworkings\b|\bfaces?\b|\bmine\b|\bmines\b|\bshoots?\b|\bstopes?\b|\badits?\b|\bgrab\b|\brock\b|\bchip\b|\bchannel\b|\btrench\w*|\bsoil\b|\btill\b|\boutcrop\w*|\bsurface\b|\bboulders?\b|\bfloat\b|\bprospecting\b|\bmapping\b|\bgeophysic\w*|\bgeochem\w*|\bsurvey\b|\bstream sediment\b|\bbulk sample\b|\bpanel\b|\bstripping\b", re.I)
_V16_SMP_NAMES = re.compile(r"\bTrench Metals\b|\bALS (?:Geochemistry|Global|Canada|Minerals)\b|\bSGS\b|\bBureau Veritas\b|\bActlabs\b|\bMSALABS\b|\bGeochemistry (?:lab\w*|services)\b", re.I)


def _v16_smp(h, oc, ho, stage, lead=None):
    hn = _V16_SMP_NAMES.sub(" ", h)
    if hn != h and not re.search(r"(?i)\bsampl\w+|\bgeochem\w*|\bgeophysic\w*|\btrench\w*|\bassays?\b|\bsurvey\b", hn) and not _V16_SMP_RESULT.search(hn):
        return ("smp:name-match", "exp" if re.search(r"(?i)\bexplor\w+|\bprogram\b|\bproject\b|\breview\b", hn) else "")
    if _V16_SMP_DRILL.search(h) and not _V16_SMP_SURF.search(h) and re.search(r"(?i)\bsampl\w+", h) and _V16_SMP_RESULT.search(h):
        return ("smp:drill-results", "drl")
    tx = (oc or "") + " || " + (lead or "")
    oc_res = re.search(r"(?i)\bg/t\b|\bgpt\b|\bppm\b|\bppb\b|\b\d[\d.,]*\s?%|\boz/t\b|\bassays? (?:results|returned|received|up to)\b|\bresults\b|\breturned\b|\bgrading\b|\banomal\w+|\bhighlights?\b|\bup to\b|\bvalues\b|\bmineraliz\w+|\bmineralis\w+|\boutcrops?\b|\bdykes?\b|\bveins?\b|\bconductors?\b|\bdefin\w+ (?:of )?(?:\w+ )?targets?\b|\bidentif\w+|\bdiscover\w+|\bvisible\b|\bspodumene\b", tx)
    if _V16_SMP_PROGRAM.search(h) and not _V16_SMP_RESULT.search(h) and not oc_res and not re.search(r"(?i)\bsales?\b", h):
        return ("smp:no-results-yet", "exp")
    return None


# ---- Permits & Approvals ---------------------------------------------------------------------------------------------
_V16_PER_REAL = re.compile(r"\bpermit\w*|\blicen[cs]\w*|\bEIA\b|\bESIA\b|\bEIS\b|\benvironment\w*|\bwater\b|\bmining (?:lease|concession|title|right)s?\b|\bconcession\w*|\bgovernment\b|\bministry\b|\bminister\b|\bdepartment\b|"
                           r"\bBLM\b|\bUSFS\b|\bforest service\b|\bplan of operations\b|\bnotice of intent\b|\bNOI\b|\bexploration (?:license|licence|permit)\b|\bdrill(?:ing)? (?:approval|permit|program approval)\b|\bapproval to drill\b|\bfederal\b|\bprovincial\b|\bstate\b|\bcounty\b|\bmunicipal\w*|"
                           r"\bBAPE\b|\bFAST-41\b|\bclosure plan\b|\bwork permit\b|\bland use\b|\bzoning\b|\brezon\w+|\bregulator\w*\b(?! approval)|\bconsultation\b|\bcertificate of approval\b|\bdecree\b|\bauthori[sz]ation\b", re.I)
_V16_PER_EXCH = re.compile(r"\b(?:TSX[-\s]?V(?:enture)?(?: Exchange)?|TSX|CSE|NEO|Cboe|exchange|stock exchange)['’]?s? (?:final |conditional )?(?:approval|acceptance)\b|\bexchange approval\b|\b(?:approv\w+|accept\w+)\b[^\n]{0,30}\b(?:of|from|by) (?:the )?(?:TSX|CSE|exchange)\b|"
                           r"\b(?:conditional|final) (?:exchange )?(?:approval|acceptance)\b[^\n]{0,40}\b(?:for|of) (?:the )?(?:acquisition|sale|financing|placement|offering|option|transaction|amalgamation|arrangement|listing|shares|debt|loan|RTO|QT|qualifying)\b|"
                           r"\breceives? (?:conditional |final )?approval (?:for|of) (?:the )?(?:acquisition|sale|financing|placement|offering|option agreement|transaction|amalgamation|arrangement)\b|\bsubject to (?:regulatory|exchange|TSX|shareholder) approval\b|\bpermit the (?:directors|company|holders?)\b", re.I)
_V16_PER_GRANT = re.compile(r"\bgrants?\b(?! (?:of )?(?:\w+ )?(?:stock|incentive|share|options|RSUs?|DSUs?|PSUs?|equity|restricted|security|awards?|deferred|performance))|\btax (?:exemption|credit|incentive)s?\b|\bnon[-\s]repayable\b|\bOJEP\b|\bJEP\b|\bMEAP\b|\bTMEI\b|\bsubsidy\b|\bsubsidies\b|\bEcocert\b|\bcertification\b", re.I)
_V16_PER_STRONG = re.compile(r"\bpermit\w*|\blicen[cs]\w*|\bEIA\b|\bESIA\b|\bEIS\b|\benvironmental (?:approval|assessment|impact|licen\w+|permit|certificate|compliance|baseline|studies)\b|\bwater (?:licen\w+|permit|right|use)\b|\bmining (?:lease|concession|title)s?\b|\bconcession\w*|"
                             r"\bdrill(?:ing)? (?:approval|permit|program approval)\b|\bapproval (?:to|for) (?:drill|explor|the drill|its drill|construct|mine|operate|develop)\w*|\bBLM\b|\bUSFS\b|\bforest service\b|\bplan of operations\b|\bnotice of intent\b|\bwork plan\b|\bauthori[sz]ation\b|\bdecree\b|\bBAPE\b|\bFAST-41\b|\bclosure plan\b|\bzoning\b|\brezon\w+", re.I)
_V16_PER_ACCESS = re.compile(r"\b(?:land|surface|community|long[-\s]term) (?:access|use|rights) agreements?\b|\baccess agreements?\b|\bsurface rights agreements?\b", re.I)


def _v16_per(h, oc, ho, stage):
    hm = _V16_PER_EXCH.sub(" ", h)
    if hm != h and not _V16_PER_REAL.search(hm):
        return ("per:exchange-approval", "")
    if _V16_PER_GRANT.search(h) and not _V16_PER_STRONG.search(h):
        return ("per:grant-funding", "")
    if _V16_PER_ACCESS.search(h) and not _V16_PER_STRONG.search(h) and not re.search(r"(?i)\bapprov\w+|\bgovernment\b|\bministry\b", _V16_PER_ACCESS.sub(" ", h)):
        return ("per:access-agreement", "")
    return None


# ---- Financings ------------------------------------------------------------------------------------------------------
_V16_FIN_NEW = re.compile(r"\bplacements?\b|\bofferings?\b|\bbought deal\b|\bflow[-\s]?through\b|\bLIFE\b|\bprospectus\b|\bsubscri\w+|\bunits?\b|\bATM\b|\bat[-\s]the[-\s]market\b|\bstrategic investment\b|\bequity investment\b|"
                          r"\binvest\w+ (?:in|into) (?:the company|\w+)\b|\bfinancing\b(?! (?:update|activities))|\bfinancings\b|\bfinanc\w+ package\b|\braises?\b|\braised\b|\bgross proceeds\b|\bproceeds of\b|\bnew (?:loan|credit|facility)\b|\bdraw\w*\b|\btranche\b|"
                          r"\bupsiz\w+|\bincreas\w+|\badditional\b|\bpric\w+ of\b|\bstream\b|\bprepay\w*|\bgold loan\b|\bloan (?:agreement|facility)\b|\bcredit facility\b|\bconvertible (?:debenture|note|loan|bond)s? (?:financing|offering|placement|issuance)\b|\bissu\w+ (?:of )?(?:\$|US\$|C\$)", re.I)
_V16_FIN_WARRANT = re.compile(r"\b(?:exercise of|exercises?|exercised|early) (?:\w+ ){0,2}warrants?\b|\bwarrants? (?:exercise\w*|exercised|incentive|acceleration|accelerat\w+)\b|\bwarrant exercise\b|\bthrough (?:the )?(?:exercise of )?(?:\w+ )?warrants?\b", re.I)
_V16_FIN_DEBTONLY = re.compile(r"\bshares? for (?:debt|services)\b|\bshares?[-\s]for[-\s](?:debt|services)\b|\bsecurities for debt\b|\bdebt settlement\b|\bsettle\w* (?:of )?(?:\$[\d,.]+ (?:of |in )?)?(?:debt|indebtedness|liabilities|payables)\b", re.I)


def _v16_fin(h, oc, ho, stage):
    if _V16_FIN_WARRANT.search(h) and not _V16_FIN_NEW.search(_V16_FIN_WARRANT.sub(" ", h)):
        return ("fin:warrant-exercise", "cap")
    if _V16_FIN_DEBTONLY.search(h) and not re.search(r"(?i)\bdebentures?\b|\bconvertible\b|\bloans?\b|\bcredit\b|\bnotes?\b", h) and not _V16_FIN_NEW.search(_V16_FIN_DEBTONLY.sub(" ", h)):
        return ("fin:shares-for-debt", "cap")     # paying ordinary bills in shares is Share Capital; loans/debentures stay (scope: both)
    return None


_V16_CODES = ("ltr", "roy", "eco", "prd", "cmt", "act", "lst", "opt", "smp", "per", "fin")
_V16_FUNCS = {"ltr": _v16_ltr, "roy": _v16_roy, "eco": _v16_eco, "prd": _v16_prd, "cmt": _v16_cmt, "act": _v16_act, "lst": _v16_lst,
              "opt": _v16_opt, "smp": _v16_smp, "per": _v16_per, "fin": _v16_fin}


def _v16_apply(cats, h, oc, stage, why=None, lead=None):
    """Core of TAGFIX_V6 on an effective headline h, opening clause oc and company stage."""
    here = [c for c in _V16_CODES if CODE_TO_CAT[c] in cats]
    if not here or not h or is_hollow(h) or _DISCLAIMER_HEADLINE_V8.search(h):
        return cats
    ho = h + " || " + (oc or "")
    s = list(cats)
    dropped, adds, rules = [], set(), {}
    for code in here:
        r = _V16_FUNCS[code](h, oc, ho, stage, lead) if code == "smp" else _V16_FUNCS[code](h, oc, ho, stage)
        if r is None:
            continue
        dropped.append(code)
        rules[code] = r[0]
        s.remove(CODE_TO_CAT[code])
        if r[1]:
            adds.add(r[1])
        if why is not None:
            why.append(r[0])
    if not dropped:
        return cats
    nonmining = bool(_V14_NONMINING.search(h) or _V15_NONMINING.search(h))
    for a in ([] if nonmining else adds):
        if a not in dropped and CODE_TO_CAT[a] not in s:
            s.append(CODE_TO_CAT[a])
    if len(s) > 1 and "Corporate Updates" in s:
        s.remove("Corporate Updates")
    if not s:
        codes = [] if nonmining else [c for c in _v14_tags(h, False, stage) if c not in dropped]
        if not codes and oc and not nonmining:
            codes = [c for c in _v14_tags(oc, True, stage) if c not in dropped]
        if not codes:
            # Keep-if-empty (carried from FP1): never leave a release with only the Corporate Updates fallback.
            if why is not None:
                why.append("kept:" + "+".join(dropped))
            return cats
        s = [CODE_TO_CAT[c] for c in codes]
        if why is not None:
            why.append("refill:" + "+".join(codes))
    return [c for c in CATEGORIES if c in set(s)]


def v16_fix(cats: list[str], headline: str | None, recovered: str | None = None, body: str | None = None,
            ticker: str | None = None) -> list[str]:
    """TAGFIX_V6: drop Phase-2 tags whose only support is a known false trigger. Returns cats unchanged when nothing applies."""
    if not any(CODE_TO_CAT[c] in cats for c in _V16_CODES):
        return cats
    h = norm_head(headline)
    if (not h or is_hollow(h)) and recovered:
        h = norm_head(recovered)
    oc = opening_clause(body) if body else None
    return _v16_apply(cats, h, oc, _v12_stage(ticker, body), None, re.sub(r"\s+", " ", body or "")[:300])


# ===========================================================================
# v17 per-tag false-positive removal (TAGFIX_V7 / FP3, 2026-09-28). Justin, after TAGFIX_V6: build all three Phase 2b
# follow-ups ("Clarifies Technical Disclosure" Technical Reports -> Regulatory; monthly sales / production updates
# Financials -> Production; "moratorium" / "no appeal" wording Legal -> Permits) and switch on two V6 scope rules he
# answered "remove": a royalty company's own corporate news is not Royalties & Streams, and a results release that also
# gives an outlook is not Shareholder Letters & Outlook. Runs after TAGFIX_V6 on every release, same shape as v15/v16:
# a tag is dropped only when a known false trigger is present and nothing else in the headline earns it; the right tag
# is added where clear; if a drop leaves nothing the V4 vocabulary refills from the headline, then the opening
# sentence; failing that the dropped tag stays (keep-if-empty).
# ===========================================================================

# ---- Technical Reports: a company clarifying or retracting earlier disclosure (usually at a regulator's request) ----
_V17_TEC_CLAR = re.compile(
    r"\b(?:clarif\w+|retract\w*|corrective)\b[^\n|]{0,60}\b(?:disclosure|technical report|43-101|report)\b|"
    r"\b(?:disclosure|technical report|43-101 report|report)\b[^\n|]{0,20}\bclarification\b", re.I)
_V17_TEC_FILES = re.compile(
    r"\b(?:files?|filed|filing|re-?fil\w+|amends?|amended|restated|revised|updated|new|completes?|completed|publishes?|releases?|receives?|delivers?)\b"
    r"[^\n|]{0,40}\b(?:technical reports?|43-?\s?101 (?:technical )?reports?|NI 43-?\s?101 reports?)\b|\btechnical report status\b", re.I)


_V17_TEC_FILED = re.compile(
    r"\btechnical reports?\b[^.]{0,120}?\b(?:filed|dated|entitled|titled)\b|\b(?:filed|entitled|titled)\b[^.]{0,80}?\btechnical reports?\b|"
    r"\bclarif\w+ (?:the|its) (?:NI 43-?\s?101 )?technical reports?\b|"
    r"\btechnical reports? (?:on|for) the\b[^.]{0,120}?\b(?:effective date|filed|dated|not compliant|does not comply)\b", re.I)


def _v17_tec(h, oc, ho, stage, lead=None):
    if not _V17_TEC_CLAR.search(h) or _V17_TEC_FILES.search(h):
        return None
    if not re.search(r"(?i)\bdisclosures?\b", h) or re.search(r"(?i)\breports?\b", h):
        return None                                   # the headline is about a report itself: Technical Reports stays
    if lead and _V17_TEC_FILED.search(lead):
        return None                                   # it corrects a filed technical report: the topic tag stays (with Regulatory)
    return ("tec:disclosure-clarification", "reg")


# ---- Financials: monthly sales, production / operating updates and deliveries with no financial results -----------
_V17_MONTHS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_V17_FNS_OPS = re.compile(
    r"\bsales\b[^\n|]{0,60}\b(?:for|in) (?:the month of )?" + _V17_MONTHS + r"\b|\b" + _V17_MONTHS + r"(?: 20\d\d)? sales\b|\bmonthly sales\b|"
    r"\bproduction (?:and (?:cost|costs|sales|operating|operations|development) )?(?:update|results|report|figures|numbers|highlights|review)\b|"
    r"\b(?:preliminary|quarterly|monthly) (?:\w+ )?(?:operating|operational|production|sales) (?:results|update|highlights|figures)\b|"
    r"\b(?:operating|operational|operations|sales) (?:results|update|highlights)\b|\bGEO deliveries\b|\b(?:metals?|gold|silver|copper) sales (?:for|in|of)\b|"
    r"\bsold [\d,.]+ (?:[\w-]+ ){0,3}(?:ounces|oz|tonnes|pounds|lbs)\b|\brecord (?:quarterly |monthly )?(?:gold |silver )?(?:production|sales)\b|"
    r"\bgenerat\w+ (?:record )?revenue from (?:the |its )?(?:[\w'’-]+ ){0,4}(?:mine|operations?|plant|mill)\b", re.I)
_V17_FNS_REAL = re.compile(
    r"\bfinancial\w*\b|\bstatements?\b|\bMD&A\b|\bearnings\b|\bnet (?:income|loss|earnings)\b|\bincome\b|\bEBITDA\b|\bEPS\b|\bcash flows?\b|"
    r"\bcash margin\b|\bconference call\b|\bwebcast\b|\bearnings call\b|\bdividends?\b|\bprofit\w*\b|\binterim\b|\bfiscal\b|\bfilings?\b|\bfiled\b|"
    r"\b(?:results|release|reporting) date\b|\bbalance sheet\b|\baudit\w*\b|\byear[-\s]end\b|\bannual report\b", re.I)
_V17_FNS_OPSRES = re.compile(r"\b(?:production|operating|operational|operations|sales) (?:and (?:cost|costs|sales|operating|operations) )?results\b|\bresults (?:from|at) (?:the )?[\w' -]{0,30}\b(?:mine|operation)\b", re.I)


_V17_FNS_LEAD = re.compile(r"\bfinancial statements\b|\bMD&A\b|\bmanagement[’']?s discussion\b|\bnet (?:income|loss|earnings)\b|\bEBITDA\b|\bearnings per share\b|\bfinancial results\b", re.I)
_V17_FNS_MONEY = re.compile(
    r"(?:\bUS|\bC|\bA)?\$\s?[\d.,]+|\brevenues?\b|\bsales (?:of|results)\b|\bmonthly sales\b|\b(?:quarterly|annual|yearly) sales\b|"
    r"\bsales\b[^\n|]{0,40}\b(?:for|in) (?:the month of )?" + _V17_MONTHS + r"\b|\b" + _V17_MONTHS + r"(?: 20\d\d)? sales\b", re.I)


def _v17_fns(h, oc, ho, stage, lead=None):
    if not _V17_FNS_OPS.search(h) or _V17_FNS_REAL.search(h):
        return None
    if re.search(r"(?i)\bresults\b", _V17_FNS_OPSRES.sub(" ", h)):
        return None                                   # quarterly/annual results: Financials is right
    if lead and _V17_FNS_LEAD.search(lead):
        return None                                   # the text reports financial statements / results after all
    if _V17_FNS_MONEY.search(h):
        return ("fns:sales-add-prd", "prd", True)     # sales or revenue in money: keep Financials, add Production
    return ("fns:production-update", "prd")


# ---- Legal & Disputes: a government moratorium, or a permit that drew no appeal --------------------------------------
_V17_LEG_PERMIT = re.compile(
    r"\bmoratori(?:um|a)\b|\bno (?:\w+ )?appeals?\b|\bappeals? (?:period|window) (?:has |have )?(?:expired|lapsed|closed|ended|passed)\b|"
    r"\bwithout (?:any )?appeals?\b|\bnot (?:been )?appealed\b|\bfree (?:of|from) appeals?\b|\bnon[-\s]appealable\b", re.I)


def _v17_leg(h, oc, ho, stage):
    if not _V17_LEG_PERMIT.search(h) or not (R10_LEG.search(h) and not R10_LEG_NOT.search(h)):
        return None                                   # no moratorium/appeal wording, or Legal came from elsewhere
    m = _V17_LEG_PERMIT.sub(" ", h)
    if R10_LEG.search(m) and not R10_LEG_NOT.search(m):
        return None                                   # a court, lawsuit, appeal or dispute is also named
    if "leg" in _v14_tags(m, False, stage):
        return None
    permit = re.search(r"(?i)\b(?:lifting of|lifts|lifted|decision to lift)\b[^\n|]{0,30}\bmoratori|\bmoratori\w+ on (?:the )?(?:\w+ ){0,3}(?:licen[cs]es?|permits?|concessions?)\b|\bappeal", h)
    return ("leg:moratorium-no-appeal", "per" if permit else "")


# ---- Royalties & Streams: a royalty company's own corporate news (V6 rule roy:royalty-company-corporate, switched on) --
def _v17_roy(h, oc, ho, stage):
    if not _V16_ROY_WORD.search(h):
        return None
    rest = _V16_ROY_NAME.sub(" ", h)
    if rest == h or _V16_ROY_WORD.search(rest) or not _V16_ROY_ISSUER.search(h) or _V16_ROY_NOTROYCO.search(h):
        return None                                   # not a royalty company's own release (or V6 already judged it)
    own = re.search(r"(?i)\bat (?:the |its )?(?:[\w'’-]+ ){0,5}(?:project|mine|property|operation)s?\b|\broyalt\w+ (?:portfolio|interest|acquisition|financing|update)|\bstream\b|\bupdate\b|\bresults\b|\brevenue\b|\bGEOs?\b|\bdividend\b", rest)
    if not own and (_V16_ROY_CORP.search(h) or _V16_ROY_FIN.search(h)) and not _V16_ROY_OWNNEWS.search(_V16_ROY_FIN.sub(" ", _V16_ROY_CORP.sub(" ", h))):
        return ("roy:royalty-company-corporate", "")
    return None


# ---- Shareholder Letters & Outlook: a results release that also gives an outlook (V6 rule ltr:results-outlook, on) --
def _v17_ltr(h, oc, ho, stage):
    if re.search(r"(?i)\bletter\b(?! of (?:intent|credit|support|interest))|\bmessage (?:from|to)\b|\byear[-\s]in[-\s]review\b", h):
        return None
    if _V16_LTR_EVENT.search(h):
        return None
    outlook = re.search(r"(?i)\boutlook\b|\bguidance\b|\b(?:objectives|priorities|goals|catalysts) for\b|\blooks? ahead\b", h)
    if not outlook or not _V16_RESULTS.search(h) or re.search(r"(?i)\b(?:review|recap|summar\w+|highlights and outlook|milestones|achievements|plans|objectives|goals|priorities|moving forward|year ahead|strategy)\b", h):
        return None
    if re.search(r"(?i)\b(?:reports?|announces?|releases?|delivers?)\b[^\n]{0,80}\b(?:results|production|financials)\b|\bfinancials\b", h):
        return ("ltr:results-outlook", "fns" if re.search(r"(?i)\bfinancial|\bstatements\b|\bMD&A\b|\bannual report\b|\b(?:first|second|third|fourth|Q[1-4]|quarter\w*|year[-\s]end|annual|full[-\s]year|20\d\d) (?:\w+ )?results\b", h) else "")
    return None


_V17_FUNCS = {"tec": _v17_tec, "fns": _v17_fns, "leg": _v17_leg, "roy": _v17_roy, "ltr": _v17_ltr}
_V17_CODES = ("tec", "fns", "leg", "roy", "ltr")


def _v17_apply(cats, h, oc, stage, why=None, lead=None):
    """Core of TAGFIX_V7 on an effective headline h, opening clause oc and company stage."""
    here = [c for c in _V17_CODES if CODE_TO_CAT[c] in cats]
    if not here or not h or is_hollow(h) or _DISCLAIMER_HEADLINE_V8.search(h):
        return cats
    ho = h + " || " + (oc or "")
    s = list(cats)
    dropped, adds = [], set()
    for code in here:
        r = _V17_FUNCS[code](h, oc, ho, stage, lead) if code in ("tec", "fns") else _V17_FUNCS[code](h, oc, ho, stage)
        if r is None:
            continue
        if len(r) < 3 or not r[2]:                    # a third element True means: keep this tag, only add
            dropped.append(code)
            s.remove(CODE_TO_CAT[code])
        if r[1]:
            adds.add(r[1])
        if why is not None:
            why.append(r[0])
    if not dropped and not adds:
        return cats
    nonmining = bool(_V14_NONMINING.search(h) or _V15_NONMINING.search(h))
    for a in ([] if nonmining else adds):
        if a not in dropped and CODE_TO_CAT[a] not in s:
            s.append(CODE_TO_CAT[a])
    if len(s) > 1 and "Corporate Updates" in s:
        s.remove("Corporate Updates")
    if set(s) == set(cats):
        return cats                                   # nothing actually changed (e.g. an add the release already has)
    if not s:
        codes = [] if nonmining else [c for c in _v14_tags(h, False, stage) if c not in dropped]
        if not codes and oc and not nonmining:
            codes = [c for c in _v14_tags(oc, True, stage) if c not in dropped]
        if not codes:
            # Keep-if-empty (carried from FP1/FP2): never leave a release with only the Corporate Updates fallback.
            if why is not None:
                why.append("kept:" + "+".join(dropped))
            return cats
        s = [CODE_TO_CAT[c] for c in codes]
        if why is not None:
            why.append("refill:" + "+".join(codes))
    return [c for c in CATEGORIES if c in set(s)]


def v17_fix(cats: list[str], headline: str | None, recovered: str | None = None, body: str | None = None,
            ticker: str | None = None) -> list[str]:
    """TAGFIX_V7: drop tags whose only support is a known false trigger. Returns cats unchanged when nothing applies."""
    if not any(CODE_TO_CAT[c] in cats for c in _V17_CODES):
        return cats
    h = norm_head(headline)
    if (not h or is_hollow(h)) and recovered:
        h = norm_head(recovered)
    oc = opening_clause(body) if body else None
    return _v17_apply(cats, h, oc, _v12_stage(ticker, body), None, re.sub(r"\s+", " ", body or "").strip()[:1000])


# ---- TAGFIX_V8 (RULEFIX, 2026-09-28) ---------------------------------------------------------------------------
# Seven rules verified blind on fresh releases (claude/MNT_RULEFIX_FINDINGS_2026-09-28.md). Each rule is
# fn(headline, lede900, codes) -> (add, drop), run on the finished tag set (after V7), like the stored-tag test harness.

_v18B_I = re.I

_v18B__ANN = re.compile('(pleased to (?:announce|report|provide|present|share|disclose|inform|update)|\\bannounce[sd]?\\b|\\breports?\\b|\\btoday (?:announced|reported|reports)|\\bprovides?\\b an update)', _v18B_I)

_v18B__RECAP = re.compile('previously (?:announced|reported|disclosed)|further to (?:its|the|our)|news release (?:dated|of)|as (?:announced|reported) (?:on|in)|see (?:news|press) release', _v18B_I)

def _v18B__ann_window(lede, n=350):
    """Text of the opening announcement: from the first announce verb, n chars. '' if none in first 600 chars."""
    m = _v18B__ANN.search(lede[:600])
    if not m:
        return ''
    return lede[m.start():m.start() + n]

_v18B__NOT_NEWS = re.compile('\\b(webinar|replay|presentation|video|podcast|interview|conference|symposium)\\b', _v18B_I)

_v18B__D_LEDE = re.compile('\\b(?:drill(?:\\s?ing)?|core)\\s+results?\\b|\\bresults?\\s+(?:from|of|for)\\s+(?:the\\s+|its\\s+)?(?:[\\w-]+\\W+){0,5}(?:drill(?:\\s?ing)?(?![- ]?(?:ready|targets?))|drill\\s?holes?|holes?|boreholes?)\\b|\\bha(?:s|ve) (?:intersected|intercepted)\\b|\\bintersected\\b', _v18B_I)

_v18B__D_LEDE_BAD = re.compile('\\b(pending|awaited|await(?:ing)?|expected|will be|anticipat\\w*|historic(?:al)?|webinar|metallurg\\w*|recover(?:y|ies))\\b', _v18B_I)

_v18B__DEAL_H = re.compile('\\b(options?|optioned|acquir\\w*|acquisition|stakes?|staking|stream|royalt\\w*|purchase|sells?|sale|webinar|replay|presentation|video|podcast|interview)\\b', _v18B_I)

def _v18B_r_drl_drop_deal(h, lede, rules):
    if 'drl' not in rules or not rules & {'opt', 'mna', 'roy', 'mkt'}:
        return (set(), set())
    if not _v18B__DEAL_H.search(h) or re.search('\\b(drill\\w*|holes?|intersect\\w*|intercept\\w*)\\b', h, _v18B_I):
        return (set(), set())
    w = _v18B__ann_window(lede, 300)
    if w and _v18B__D_LEDE.search(w) and (not _v18B__RECAP.search(w)) and (not _v18B__D_LEDE_BAD.search(w)):
        return (set(), set())
    return (set(), {'drl'})

_v18B__EXPISH_H = re.compile('\\b(drill\\w*|holes?|intersect\\w*|intercept\\w*|assays?|sampl\\w*|trench\\w*|grab|soil|channel|explor\\w*|geophysic\\w*|survey|prospecting|mapping|discover\\w*|zones?|targets?|veins?)\\b', _v18B_I)

def _v18B_r_exp_from_results(h, lede, rules):
    if 'exp' in rules or not rules & {'drl', 'smp'}:
        return (set(), set())
    if _v18B_r_drl_drop_deal(h, lede, rules)[1] or _v18B__NOT_NEWS.search(h):
        return (set(), set())
    if rules & {'res', 'met', 'eco', 'tec', 'prd', 'dev', 'mna', 'opt', 'roy', 'fin', 'dbt'} and (not _v18B__EXPISH_H.search(h)):
        return (set(), set())
    return ({'exp'}, set())

_v18A_I = re.I

_v18A__ANN = re.compile('\\b(is|are)\\s+(very\\s+)?(pleased|excited|delighted|proud|happy)\\s+to\\b|\\bannounce[sd]?\\s+(that|today|the|its)\\b|\\b(today|has)\\s+(announced|reported)\\b|\\breports?\\s+that\\b|\\bis\\s+providing\\b|\\bwould\\s+like\\s+to\\b|\\bprovides?\\s+(the\\s+following|an\\s+update)\\b|\\bhas\\s+issued\\s+this\\b|\\bannounces:', _v18A_I)

def _v18A__win(lede, after=550):
    """Opening text up to ~550 chars past the company's own news statement (or ~850 chars if none found)."""
    m = _v18A__ANN.search(lede or '')
    end = m.end() + after if m else 850
    return (lede or '')[:end]

_v18A__C_EXP_H = re.compile('\\bexploration\\s+(program|begins|commences|starts|underway|update|activities|plans?|campaign|highlights)\\b|\\bdrill(ing)?\\b|\\bfield\\s+(program|season|work)\\b|\\bprospect(ing)?\\b|\\btargets?\\b|\\bsurveys?\\b|\\bmapping\\b|\\b(focus|focuses)\\s+on\\b[^.]{0,40}\\b(in\\s+20\\d\\d)\\b', _v18A_I)

_v18A__C_UPD_H = re.compile('\\b(update[sd]?|advances|progress|activit(y|ies)|summari[sz]es|overview)\\b', _v18A_I)

_v18A__C_SITE_H = re.compile('\\b(propert(y|ies)|projects?|prospects?|claims?|licen[cs]es?|concessions?|tenements?)\\b', _v18A_I)

_v18A__C_NOT_EXP_H = re.compile('\\bmine\\b|mining\\s+operations|production|construction|feasibility|\\bPEA\\b|financial|results\\s+of\\s+(the\\s+)?(annual|special)|meeting|royalt', _v18A_I)

_v18A__C_EXP_LEDE = re.compile('\\bexploration\\s+(program|programs|activities|work|highlights|plans?|update|campaign|season)\\b|\\bdrill(ing)?\\s+(program|campaign|targets?)\\b|\\bfield\\s+(program|work|season|crews?)\\b|\\b(soil|till|rock|grab|channel|geochemical|lake\\s+sediment)\\s+sampl|\\b(geophysical|magnetic|gravity|IP|airborne)\\s+surveys?\\b|\\bsurveys?\\s+(commenced|completed|began)\\b|\\bprospecting\\b|\\bmapping\\b', _v18A_I)

def _v18A_r_cor_exploration_update(h, lede, rules):
    """Release left as Corporate Updates only: exploration-program headline (drilling, targets, surveys, program start),
    or a property/project update whose opening statement describes exploration work -> Exploration Programs."""
    if rules != {'cor'}:
        return (set(), set())
    if _v18A__C_NOT_EXP_H.search(h) and (not _v18A__C_EXP_H.search(h)):
        return (set(), set())
    if _v18A__C_EXP_H.search(h):
        return ({'exp'}, set())
    if (_v18A__C_UPD_H.search(h) or _v18A__C_SITE_H.search(h)) and _v18A__C_EXP_LEDE.search(_v18A__win(lede, 500)):
        return ({'exp'}, set())
    return (set(), set())

_v18D_I = re.I

_v18D_STUDY = '(?:PEA|PFS|DFS|BFS|preliminary economic assessment|pre-?\\s?feasibility(?: study)?|prefeasibility(?: study)?|feasibility study|feasibility|scoping study)'

_v18D_RESULTS_HEAD = re.compile('\\b(?:Q[1-4]|first|second|third|fourth|1st|2nd|3rd|4th)\\b[^|]{0,25}\\b(?:quarter|results|report)\\b|\\bquarter(?:ly)? (?:results|report)\\b|\\b(?:year[-\\s]end|full[-\\s]year|annual|fiscal|20\\d\\d) (?:\\w+ )?(?:financial )?results\\b|\\bfinancial results\\b|\\bEBITDA\\b|\\bnet (?:income|earnings|profit)\\b', _v18D_I)

_v18D_PRD_SIG = re.compile('\\b(?:gold|silver|copper|zinc|nickel|uranium|iron ore|concentrate|AgEq|AuEq|GEO|equivalent|attributable|record|quarterly)\\b[^.]{0,30}\\bproduction\\b(?! (?:decision|start|restart|guidance for (?:the )?(?:first|initial)))|\\bproduc(?:ed|tion of)\\b[^.]{0,30}\\d|\\b(?:ounces|oz|tonnes|pounds|lbs|wmt)\\b[^.]{0,25}\\b(?:produced|sold)\\b|\\b(?:produced|sold)\\b[^.]{0,30}\\b(?:ounces|oz|tonnes|pounds|lbs|wmt)\\b|\\bAISC\\b|\\ball-in sustaining\\b|\\bcash costs?\\b|\\bthroughput\\b|\\b(?:tonnes|tons) (?:milled|processed|mined)\\b|\\bpayable (?:copper|gold|silver|nickel)\\b|\\bproduction guidance\\b|\\bGEOs?\\b|\\bdeliveries\\b', _v18D_I)

_v18D_PRD_SIG_FUT = re.compile('\\b(?:to be|will be|would be|expected to be|potential(?:ly)?|planned|targeted|projected|anticipated|forecast)\\b[^.]{0,12}$', _v18D_I)

def _v18D_r_prd_results_production_add(h, lede, rules):
    if 'prd' in rules:
        return (set(), set())
    if not ('fns' in rules or _v18D_RESULTS_HEAD.search(h)):
        return (set(), set())
    if re.search('\\b' + _v18D_STUDY + '\\b', h, _v18D_I):
        return (set(), set())
    text = h + ' . ' + (lede or '')[:700]
    for m in _v18D_PRD_SIG.finditer(text):
        if _v18D_PRD_SIG_FUT.search(text[max(0, m.start() - 40):m.start()]) or re.search('\\bto be produced\\b', m.group(0), _v18D_I):
            continue
        return ({'prd'}, set())
    return (set(), set())

_v18F_I = re.I

_v18F__ABBR = re.compile('\\b(Mr|Ms|Mrs|Dr|Prof|Inc|Corp|Ltd|Co|No|St|Jr|Sr|Ph\\.D|U\\.S|B\\.C|J\\.D|LL\\.M)\\.')

_v18F__SENT = re.compile('(?<=[.;!?])\\s+(?=[A-Z\\u201c\\"(])')

_v18F__RECAP = re.compile("\\bpreviously announced\\b|\\bfurther to\\b|\\bas announced\\b|\\bannounced (?:on|in) (?:\\w+ \\d|\\d)|\\bnews release(?:s)? (?:dated|of|issued on)\\b|\\bsee (?:the )?(?:company'?s? )?(?:news|press) release", _v18F_I)

def _v18F__open(lede, n=750, keep_recap=False):
    """Opening sentences of the lede (where the company states its news), recap sentences removed."""
    t = _v18F__ABBR.sub(lambda m: m.group(1).replace('.', ''), (lede or '')[:n])
    ss = _v18F__SENT.split(t)
    if not keep_recap:
        ss = [s for s in ss if not _v18F__RECAP.search(s)]
    return ss

_v18F__RX4 = re.compile('\\bfurther to\\b|\\b(?:news|press) release dated\\b', _v18F_I)

_v18F_H_RTO = re.compile('\\b(?:clos\\w+|complet\\w+|consummat\\w+)\\b.{0,50}\\b(?:reverse take-?over|RTO|business combination|qualifying transaction|merger|amalgamation)\\b', _v18F_I)

_v18F_L_RTO = re.compile('\\b(?:closing|completion|closed|completed)\\s+(?:of\\s+)?(?:its|the)\\s+(?:previously announced\\s+)?(?:business combination|reverse take-?over|RTO|qualifying transaction|amalgamation|merger)\\b', _v18F_I)

def _v18F_r_mgt_rto(h, lede, rules):
    if 'mgt' in rules:
        return (set(), set())
    ops = ' '.join((x for x in _v18F__open(lede, 600, keep_recap=True)[:3] if not _v18F__RX4.search(x)))
    if _v18F_H_RTO.search(h) or _v18F_L_RTO.search(ops):
        return ({'mgt'}, set())
    return (set(), set())

_v18D_TECHREP = '(?:technical reports?|NI[-\\s]?43[-\\s]?101|43[-\\s]?101|resource reports?|mineral resource estimate|resource estimate|MRE)'

_v18D_OPEN_CLAUSE = re.compile('\\b(?:is|are) (?:pleased|excited|proud|delighted) to (?:announce|report|provide|advise)\\b|\\bannounce[sd]?\\b|\\breports?\\b|\\btoday (?:announced|reported)\\b|\\badvises?\\b', _v18D_I)

def _v18D__opening(lede, n=320):
    """Text from the first announce-type verb for n chars (the sentence where the company states its news)."""
    m = _v18D_OPEN_CLAUSE.search(lede or '')
    if not m:
        return ''
    return lede[m.start():m.start() + n]

_v18D_RECAP = re.compile('previously (?:announced|disclosed|reported|released)|\\bfurther to\\b|\\b(?:news|press) release (?:dated|of|issued|titled)\\b|\\bannounced (?:on|in) \\w|\\boriginally (?:presented|announced|disclosed)\\b|\\bsupports? the (?:disclosure|results|previously)\\b|\\bas announced\\b|\\b(?:were|was) (?:first )?announced\\b|\\bin support of\\b', _v18D_I)

_v18D_TEC_FILE_HEAD = re.compile('\\b(?:files?|filed|filing|re-?files?)\\b[^|]{0,70}?\\b(?:' + _v18D_TECHREP[3:-1] + '|' + _v18D_STUDY[3:-1] + ')\\b', _v18D_I)

_v18D_TEC_FILE_LEDE = re.compile('\\b(?:has|have|we|it|today) (?:\\w+ )?(?:filed|completed and filed)\\b[^.]{0,90}?\\b(?:technical report|NI[-\\s]?43[-\\s]?101|National Instrument 43[-\\s]?101)\\b|\\bthe filing (?:on SEDAR\\+? )?of (?:an? |the |its )?[^.]{0,60}?\\b(?:technical report|NI[-\\s]?43[-\\s]?101|National Instrument 43[-\\s]?101)\\b', _v18D_I)

_v18D_TEC_NOT = re.compile('\\bfiling statement\\b|\\blisting statement\\b|\\bprospectus\\b|\\bfinancial statements\\b', _v18D_I)

def _v18D_r_tec_filing_add(h, lede, rules):
    if 'tec' in rules:
        return (set(), set())
    if _v18D_TEC_FILE_HEAD.search(h) and (not _v18D_TEC_NOT.search(h)):
        return ({'tec'}, set())
    op = _v18D__opening(lede, 260)
    if op and _v18D_TEC_FILE_LEDE.search(op) and (not _v18D_RECAP.search(op[:120])):
        return ({'tec'}, set())
    return (set(), set())

_v18F__RX5 = re.compile('\\bpromotional activity\\b', _v18F_I)

_v18F__RX6 = re.compile('\\bofftake\\b', _v18F_I)

_v18F__IRTERM = '(?:investor relations|investor awareness|media relations|public relations|shareholder communications?|market[- ]?(?:maker|making|awareness|advisory)|capital markets? (?:advis\\w+|services|strategy|advice)|digital (?:marketing|media)|marketing (?:services|campaign|program|agreement|firm)|market presence|IR (?:firm|services|consultant|program|agreement))'

_v18F_H_IR = re.compile('\\b(?:engag\\w*|retain\\w*|hires?|hired|signs?|contracts?|enter\\w*|partner\\w*|selects?)\\b.{0,80}\\b' + _v18F__IRTERM + '\\b|\\b(?:market advisory|investor relations|marketing|IR) (?:engagement|agreement|services|campaign|program)\\b|\\bfor investor relations\\b', _v18F_I)

_v18F_L_IR = re.compile('\\b(?:engaged|engagement (?:of|with)|retained|hired|entered into (?:an? )?(?:\\w+ )?(?:agreement|contract)|signed (?:an? )?(?:\\w+ )?(?:agreement|contract))\\b[^;]{0,250}?\\b' + _v18F__IRTERM + '\\b', _v18F_I)

_v18F__IR_OFFICER = re.compile('\\b(?:vice[- ]president|VP|director|manager|head|chief)\\b,?\\s+(?:of\\s+)?(?:investor relations|corporate communications|capital markets)\\b|\\badds investor relations resource\\b', _v18F_I)

_v18F_H_MKT_NONIR = re.compile('\\b(?:community|indigenous|first nations?|government|stakeholder|public affairs|local) (?:relations|engagement|affairs)\\b|\\b(?:mineral|minerals|product|graphite|concentrate|offtake|commodity|sales and|lithium|industrial minerals?) marketing\\b|\\bmarketing consult\\w+ firm\\b|\\brecogni[sz]ed by (?:the )?(?:government|federal|provincial|state|ministry|minister)\\b', _v18F_I)

_v18F__MKT_REAL = re.compile('\\b(?:investor|conference|summit|webinar|award|video|presentation|IR|market awareness|podcast|interview|forum|expo)\\b', _v18F_I)

def _v18F_r_mkt_ir(h, lede, rules):
    if 'mkt' in rules or _v18F__IR_OFFICER.search(h) or _v18F__RX5.search(h) or (_v18F_H_MKT_NONIR.search(h) and (not _v18F__MKT_REAL.search(h))) or _v18F__RX6.search(h):
        return (set(), set())
    if _v18F_H_IR.search(h):
        return ({'mkt'}, set())
    ops = ' '.join(_v18F__open(lede))
    if _v18F_L_IR.search(ops) and (not _v18F__IR_OFFICER.search(ops)):
        return ({'mkt'}, set())
    return (set(), set())

_v18E_I = re.I

_v18E__ANN = re.compile('(pleased to (?:announce|report|provide|present|share|inform|update|advise)|\\bannounce[sd]?\\b|\\breports?\\b|\\breported\\b|\\bwishes to announce\\b|\\bprovides?\\b)', _v18E_I)

def _v18E__ann_window(lede, n=380):
    """Opening announcement text: from the first announce verb (within the first 650 chars), n chars."""
    m = _v18E__ANN.search(lede[:650])
    if not m:
        return ''
    return lede[m.start():m.start() + n]

_v18E__DBT_HEAD = re.compile('\\b(credit (?:facilit\\w+|line|agreement)|loan(?:s| agreements?| facilit\\w+| notes?)?\\b|(?:project|senior|debt) financ\\w+ (?:debt|facilit\\w+|package)|debt (?:facilit\\w+|financing|restructur\\w*|refinanc\\w*|repayment)|prepay(?:ment)?\\b|prepay(?:ment)? (?:facilit\\w+|agreements?)|(?:gold|silver|senior|secured|unsecured|convertible|promissory|exchangeable)[- ](?:linked )?(?:notes?|debentures?|bonds?)|debentures?|notes offering|bond (?:issue|offering)|refinanc\\w+|repays?\\s+(?:\\S+\\s+){0,3}(?:debt|loan|facility|notes))\\b', _v18E_I)

_v18E__DBT_HEAD_BAD = re.compile('\\b(debt[- ]free|no debt|loan to|lend\\w* to|shares for debt|stream to refinance)\\b', _v18E_I)

_v18E__DBT_LEDE = re.compile('\\b((?:entered into|signed|executed|closed|secured|arranged|obtained|completed|drawn|drew)\\s+(?:\\S+\\s+){0,6}?(?:credit (?:agreement|facility|line)|loan (?:agreement|facility)|(?:prepayment|debt|term loan|revolving|bridge) facility)|senior secured (?:loan|notes|credit)|convertible (?:debenture|note)s? (?:financing|offering|agreement))', _v18E_I)

def _v18E_r_dbt_add(h, lede, rules):
    if 'dbt' in rules:
        return (set(), set())
    if _v18E__DBT_HEAD.search(h) and (not _v18E__DBT_HEAD_BAD.search(h)):
        return ({'dbt'}, set())
    w = _v18E__ann_window(lede, 320)
    if w and _v18E__DBT_LEDE.search(w) and (not re.search('\\b(lender|loan to|lends|advanced? to)\\b', w[:200], _v18E_I)):
        return ({'dbt'}, set())
    return (set(), set())

_V18_RULES = [
    ('exp_from_results', _v18B_r_exp_from_results),
    ('cor_exploration_update', _v18A_r_cor_exploration_update),
    ('prd_results_production_add', _v18D_r_prd_results_production_add),
    ('mgt_rto_close', _v18F_r_mgt_rto),
    ('tec_filing_add', _v18D_r_tec_filing_add),
    ('mkt_ir_engagement', _v18F_r_mkt_ir),
    ('dbt_add', _v18E_r_dbt_add),
]


def _v18_apply(codes, headline, lede_text, why=None):
    """codes: set of tag codes. Returns the new set (same rule-combination as the RULEFIX test harness)."""
    r = set(codes)
    A, Dr = set(), set()
    for name, fn in _V18_RULES:
        try:
            a, d = fn(headline or "", lede_text or "", set(r))
        except Exception:
            continue
        a = (set(a) & set(CODE_TO_CAT)) - r
        d = set(d) & r
        if (a or d) and why is not None:
            why.append(name)
        A |= a
        Dr |= d
    both = A & Dr
    A -= both
    Dr -= both
    s = (r | A) - Dr
    if (A - {"cor"}) and "cor" in s:
        s.discard("cor")
    if not s:
        s = {"cor"}
    return s


def v18_fix(cats, headline, body, why=None):
    """TAGFIX_V8: post-processing layer on the finished tag list (category names)."""
    codes = {CAT_TO_CODE.get(c, c) for c in cats}
    if not codes <= set(CODE_TO_CAT):
        return cats
    lede_text = re.sub(r"\s+", " ", lede(body or "", 900)).strip()
    new = _v18_apply(codes, headline, lede_text, why)
    if new == codes:
        return cats
    keep = [c for c in cats if CAT_TO_CODE.get(c, c) in new]
    added = [CODE_TO_CAT[c] for c in new if CODE_TO_CAT[c] not in keep]
    return [c for c in CATEGORIES if c in keep or c in added]


def categorize(headline: str | None, body: str | None, ticker: str | None = None) -> list[str]:
    """Return the categories this release belongs to, in CATEGORIES order
    (v8 = v7 + five tags; CU_RESCUE_V1 re-reads what is still Corporate Updates alone)."""
    cats, _recovered = categorize_v7(headline, body)
    return v13_memory(v18_fix(v17_fix(v16_fix(v15_fix(v14_fix(v12_fix(v11_fix(add_v10_tags(add_v9r_tags(add_v8_tags(cats, headline, _recovered), headline, _recovered),
                                                          headline, _recovered),
                                             headline, _recovered, body),
                                     headline, _recovered, body, ticker),
                             headline, _recovered, body, ticker),
                     headline, _recovered, body, ticker),
                    headline, _recovered, body, ticker),
                   headline, _recovered, body, ticker),
                      headline, body),
                      headline, body, ticker)   # NEWTAGS_V1, TAGFIX_V1, TAGFIX_V2, TAGFIX_V4, TAGFIX_V5, TAGFIX_V6, TAGFIX_V7, TAGFIX_V8, TAGFIX_V3


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
     ["Property Options & Staking"], ["Mergers & Acquisitions"]),   # TAGFIX_V5: land expansion is Property Options
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
     ["Partnerships & JV"], ["Mergers & Acquisitions"]),   # TAGFIX_V5: a JV deal is Partnerships & JV
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
     ["Exploration Programs"], []),   # TAGFIX_V8

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
     "and 1.97% Zinc in Outcrop", "", ["Sampling & Geoscience Results"], ["Drill Results"]),   # TAGFIX_V5: outcrop samples are Sampling
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
     ["Property Options & Staking"], ["Mergers & Acquisitions", "Drill Results"]),   # TAGFIX_V5: earn-in options are Property Options
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
     "", ["Exploration Programs"], []),   # TAGFIX_V8
]



SELF_TEST += [
    # --- v6b: a bulk sample is process work, not a soil survey -----------
    ("Honey Badger Silver Provides Bulk Sample Update at the PC Silver Mine",
     "", [], ["Exploration Programs", "Metallurgy & Processing"]),   # TAGFIX_V5: bulk samples are not Metallurgy
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
    ("Quimbaya Gold Expands Strategic Land Position at Tahami Project", "", ["Property Options & Staking"], ["Mergers & Acquisitions"]),   # TAGFIX_V5
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
    ('Clarification to Technical Disclosure', "", ['Regulatory & Compliance'], ['Debt & Credit Facilities', 'Royalties & Streams', 'Property Options & Staking', 'Technical Reports (NI 43-101)']),   # TAGFIX_V7: Justin 2026-09-28
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

SELF_TEST += [
    # --- CU_RESCUE_V1 (2026-09-25) ------------------------------------------
    ('FJORDLAND ANNOUNCES APPOINTMENTS', "", ['Management Changes'], ['Corporate Updates']),
    ('Largo Announces Change in Leadership', "", ['Management Changes'], ['Corporate Updates']),
    ('NexGen Appoints Bruce Sprague and Shawn Harriman', "", ['Management Changes'], ['Corporate Updates']),
    ('Jacquelin Gauthier hired as VP Exploration', "", ['Management Changes'], []),
    ('~ GSilver Selects Ramon Davila as President ~', "", ['Management Changes'], []),
    ('Belo Sun Mining Announces Changes to Executive Leadership', "", ['Management Changes'], []),
    ('Element 29 Announces Appointment of Stellium Service Ltd as Investor Relations Consultant', "", ['Marketing Announcement'], ['Management Changes']),
    ('Vatic Announces 10:1 Rollback', "", ['Corporate Actions'], ['Corporate Updates']),
    ('CHARBONE Announces Change of Corporate Name and Registered Address', "", ['Corporate Actions'], []),
    ('Iron Ore Company of Canada Dividend', "", ['Corporate Actions'], []),
    ('SIGNATURE RESOURCES STAKES ADDITIONAL 5 KM OF FAVOURABLE GOLD TREND AT LINGMAN LAKE', "", ['Property Options & Staking'], ['Corporate Updates']),
    ('Benton Stakes the New Great Copper-Gold Corridor, Adding Significantly to Its Land Position in Newfoundland', "", ['Property Options & Staking'], []),
    ('Emerita Awarded Public Tender for Key Zinc Project in the Riocin Mining Camp', "", ['Property Options & Staking'], []),
    ('Starcore Amends Toiyabe Property Agreement', "", ['Property Options & Staking'], []),
    ('Quebec Nickel Announces Return of Claims', "", ['Property Options & Staking'], []),
    ('Aztec Minerals Reports Final Gold and Multi-Element Results from 2021-2022 Drilling at the Cervantes Project', "", ['Drill Results'], []),
    ('Headwater Gold Announces Results from Initial Drilling at TJ Project, Nevada', "", ['Drill Results'], []),
    ('DORE COPPER INTERSECTS 3.98% COPPER OVER 2.35 METERS IN A NEW ZONE', "", ['Drill Results'], []),
    ('Gossan Drilling Intersects Footwall of VMS Systems Similar to Nearby VMS Deposits', "", ['Exploration Programs'], ['Drill Results']),
    ('Monterey announces Drilling at Alicia', "", ['Exploration Programs'], []),
    ('AURANIA PROVIDES UPDATE ON DRILLING AT TSENKEN AND TIRIA-SHIMPIA TARGETS', "", ['Exploration Programs'], []),
    ('Sama announces the beginning of drilling at the Yepleu property', "", ['Exploration Programs'], []),
    ('FALCON MOBILIZES CREWS AT SPRINGPOLE WEST, RED LAKE DISTRICT', "", ['Exploration Programs'], []),
    ('NEXUS GOLD SETS DRILL TARGETS AT MCKENZIE GOLD PROJECT, RED LAKE, ONTARIO', "", ['Exploration Programs'], []),
    ('Endeavour Silver Completes Sale of Bolanitos Mine', "", ['Mergers & Acquisitions'], []),
    ('Metal Energy Announces Closing of SourceRock Acquisition', "", ['Mergers & Acquisitions'], []),
    ('SIRIOS AND OVI COMBINE TO FORM AN OSISKO-BACKED GOLD COMPANY', "", ['Mergers & Acquisitions'], []),
    ('MKANGO RAISES £3.0M (C$5.6M) TO ADVANCE RARE EARTH MAGNET RECYCLING', "", ['Financings'], []),
    ('Rover Metals Announces and Arranges $0.08 Unit Financing', "", ['Financings'], []),
    ('RIO2 ANNOUNCES WARRANT EXPIRATION', "", ['Share Capital & Compensation'], []),
    ("Group Eleven Announces Settlement of Director's Fees", "", ['Share Capital & Compensation'], []),
    ('Kuya Silver Announces Grant of Equity Incentives', "", ['Share Capital & Compensation'], []),
    ('U3O8 Corp. To Resume Trading', "", ['Listings & Exchange'], []),
    ('FREEMAN GOLD MOVES TO TSX VENTURE EXCHANGE AND DELISTS FROM CSE', "", ['Listings & Exchange'], []),
    ('Austral Gold Announces Filing of Q2 2019 Quarterly Activity Report', "", ['Financials'], []),
    ('Equinox Gold Celebrates 5 Million Ounces of Gold Produced from Mesquite Mine', "", ['Production Results'], []),
    ('Red Moon Commences Seasonal Production at Gypsum Project', "", ['Production Results'], []),
    ('Wealth Minerals Provides Update on Kuska Permitting', "", ['Permits & Approvals'], []),
    ('King Announces Approval of Required Permits for Drilling on Silver Cord', "", ['Permits & Approvals'], []),
    ('Leading Edge Materials Reports Optimized Spheronising Test Results from Woxna Graphite Project', "", ['Metallurgy & Processing'], []),
    ('PUMA TO INCREASE VISIBILITY AND IMPROVE SHAREHOLDER COMMUNICATIONS', "", ['Marketing Announcement'], []),
    ('VATIC PROVIDES CLARIFICATION ON NEWS', "", ['Regulatory & Compliance'], []),
    ('FALCON GOLD CORP. ANNOUNCES DELAY OF FILINGS', "", ['Regulatory & Compliance'], []),
    ('OSISKO ANNOUNCES THE ELECTION OF ITS BOARD OF DIRECTORS', "", ['Shareholder Meetings'], ['Management Changes']),
    ('East Africa Metals Provides Corporate Update', "", ['Corporate Updates'], ['Management Changes']),
    ('REV PROVIDES CORPORATE UPDATE', "", ['Corporate Updates'], []),
    ('Element79 Gold Corp Provides Update on Nevada Portfolio', "", ['Corporate Updates'], []),
    ('Stock Symbol: AEM (NYSE and TSX) For further information: Investor Relations', "", ['Corporate Updates'], ['Marketing Announcement']),
    ('Libra Congratulates Athena Gold on New Discovery in Red Lake', "", ['Company Commentary'], ['Exploration Programs', 'Corporate Updates']),
    ('Why Are Gold Mining Penny Stocks a Good Investment? Top Reasons Explained', "", ['Corporate Updates'], []),
    ('Talon Metals Increases Stake in Tamarack Nickel Project Partner', "", [], ['Property Options & Staking']),
]

SELF_TEST += [
    # --- NEWTAGS_V1 (2026-09-26) ------------------------------------------------
    ('Artemis Gold Announces First Gold Pour at Blackwater Mine', "", ['Mine Development & Operations'], ['Corporate Updates']),
    ('K92 Mining Provides Update on Stage 3 Expansion Construction', "", ['Mine Development & Operations'], []),
    ('Calibre Suspends Operations at El Limon Following Blockade', "", ['Mine Development & Operations'], []),
    ('SSR Mining Provides an Update on Incident at Copler', "", ['Mine Development & Operations'], []),
    ('Fortuna Announces Fatality at the Lindero Mine', "", ['Mine Development & Operations'], []),
    ('Taseko Signs Offtake Agreement for Florence Copper', "", ['Mine Development & Operations'], []),
    ('Galiano Gold Achieves Commercial Production at Asanko', "", ['Mine Development & Operations'], []),
    ('Company Announces Halt in Trading Pending News', "", [], ['Mine Development & Operations', 'Sampling & Geoscience Results', 'Legal & Disputes', 'Shareholder Letters & Outlook', 'Company Commentary']),
    ('Bonterra Announces the Suspension of All Drilling Activities', "", [], ['Mine Development & Operations']),
    ('Canex Samples 19.4 g/t Gold Over 3 Metres at Gold Range', "", ['Sampling & Geoscience Results'], []),
    ('Mirasol Soil Sampling Identifies Large Gold Anomaly at Sobek', "", ['Sampling & Geoscience Results'], []),
    ('Rock Samples Return Up to 45 g/t Gold at Golden Triangle Property', "", ['Sampling & Geoscience Results'], []),
    ('IP Survey Outlines Strong Chargeability Anomaly at Main Zone', "", ['Sampling & Geoscience Results'], []),
    ('Company Commences Soil Sampling Program at Lucky Strike', "", [], ['Sampling & Geoscience Results']),
    ('Drilling Intersects 12 m of 3.1 g/t Gold; Surface Samples Also Strong', "", [], ['Sampling & Geoscience Results']),
    ('Metallurgical Samples Shipped for Testwork', "", [], ['Sampling & Geoscience Results']),
    ('Gabriel Resources Provides Update on ICSID Arbitration', "", ['Legal & Disputes'], []),
    ('Eco Oro Receives Favourable Tribunal Decision', "", ['Legal & Disputes'], []),
    ('Company Files Statement of Claim Against Former CEO', "", ['Legal & Disputes'], []),
    ('Company Receives Final Court Approval for Plan of Arrangement', "", [], ['Legal & Disputes']),
    ('Company Announces Shares for Debt Settlement', "", [], ['Legal & Disputes']),
    ('Company Stakes Additional Mineral Claims', "", [], ['Legal & Disputes']),
    ('A Letter to Shareholders from the CEO', "", ['Shareholder Letters & Outlook'], []),
    ('Osisko Development Provides 2026 Outlook and Strategic Priorities', "", ['Shareholder Letters & Outlook'], []),
    ('Company Reviews 2025 Highlights and Outlines Objectives for 2026', "", ['Shareholder Letters & Outlook'], []),
    ('Company Initiates Strategic Review Process', "", [], ['Shareholder Letters & Outlook']),
    ('Company Provides 2026 Production Guidance', "", [], ['Shareholder Letters & Outlook']),
    ('Company Comments on Recent Share Price Movement', "", ['Company Commentary'], []),
    ('Company Responds to Short Seller Report', "", ['Company Commentary'], []),
    ('Company Welcomes Government Decision on Critical Minerals List', "", ['Company Commentary'], []),
    ('Company Welcomes John Smith to the Board', "", [], ['Company Commentary']),
    ('Company Comments on Unusual Market Activity', "", [], ['Company Commentary']),
    ('Ero Copper to Release First Quarter 2026 Results', "", [], ['Corporate Updates']),
    ('Notice of Conference Call for Third Quarter Results', "", [], []),
    ('Company Named to 2025 TSX Venture 50', "", ['Marketing Announcement'], []),
    ('Company Wins PDAC Environmental Award', "", ['Marketing Announcement'], []),
    ('Company Awarded Exploration Licence in Finland', "", [], ['Marketing Announcement']),
    ('Company Provides Corporate Update', "", ['Corporate Updates'], ['Mine Development & Operations', 'Sampling & Geoscience Results', 'Legal & Disputes', 'Shareholder Letters & Outlook', 'Company Commentary', 'Marketing Announcement']),
    ('SAGA Metals Mobilizes Camp Construction Ahead of Drilling at Wolverine', "", [], ['Mine Development & Operations']),
    ('Taranis Temporarily Halts Drilling at Thor Due to Dangerous Wildfire Conditions', "", [], ['Mine Development & Operations']),
    ('Bam Bam Plans Expanded Soil Geochemistry Coverage at Majuba Hill', "", [], ['Sampling & Geoscience Results']),
    ('PPX Provides Q3 2018 Bulk Sampling Results for Mina Callanquitas', "", [], ['Sampling & Geoscience Results']),
    ('Additional Rig Mobilized, Target Significant Large-scale Magnetic Anomalies', "", [], ['Sampling & Geoscience Results']),
    ('Kapuskasing Gold Expands Kings Court Copper/Cobalt Project in Newfoundland', "", [], ['Legal & Disputes']),
    ('Thesis and Benchmark Merger Approved by Court', "", [], ['Legal & Disputes']),
    ('Skeena Announces Positive Judgment by the Supreme Court of Canada', "", ['Legal & Disputes'], []),
    ("GOLD MINERALIZED ZONES AT SIGNATURE'S LINGMAN LAKE PROPERTY RESPOND TO GEOPHYSICAL SURVEY", "", [], ['Company Commentary']),
    ('Heliostar Presents Fiscal 2025 Financial Results Full year 2025 Highlights', "", [], ['Shareholder Letters & Outlook']),
    ('Aya Gold & Silver Announces Commencement of Boumadine Feasibility Study and Accelerates Project Development to host call', "", [], ['Marketing Announcement']),
    ('Quebec Innovative Materials Corp. to Host Live X Spaces Q&A on Results', "", ['Marketing Announcement'], []),
    ('Rover Metals takes advantage of COVID 19 extended filing deadlines for its continuous disclosure requirements', "", [], ['Mine Development & Operations']),
    ('Giyani Announces Details for its Annual and Special Meeting of Shareholders and COVID-19 Restrictions', "", [], ['Mine Development & Operations']),
    ('Blue Moon Announces Follow on Investment of C$1.2M from Mining Contractor', "", [], ['Mine Development & Operations']),
    ('B2Gold Corp. Provides Update on COVID-19 Cases at the Fekola Mine, Mali', "", ['Mine Development & Operations'], []),
    ('Salazar Announces Award of Mining Contract for El Domo Copper-Gold Project', "", ['Mine Development & Operations'], []),
    ('Commerce Resources Ships 100 g Sample of Mixed REC Concentrate - 21.9% NdPr - to Major Global Processor', "", [], ['Sampling & Geoscience Results']),
]

SELF_TEST += [
    # --- TAGFIX_V1 (2026-09-27) -------------------------------------------------
    ("Northern Graphite Options Ni-Cu-Co Project in Voisey's Bay Region", "", ['Property Options & Staking'], ['Mergers & Acquisitions']),
    ('Canadian GoldCamps Announces Definitive Option Agreement with Stelmine for Courcy & Mercator Projects', "", ['Property Options & Staking'], ['Mergers & Acquisitions']),
    ('Freeport to Acquire Star Mountains Gold Project', "", ['Mergers & Acquisitions'], []),
    ('FPX Nickel Leverages Strong Balance Sheet and Intends to Launch Normal Course Issuer Bid', "", ['Share Capital & Compensation'], ['Corporate Actions']),
    ('Lundin Gold Announces TSX Approval for Renewal of its Normal Course Issuer Bid', "", ['Share Capital & Compensation'], ['Corporate Actions', 'Permits & Approvals']),
    ('Adamera Adopts Semi-Annual Financial Reporting', "", ['Regulatory & Compliance'], ['Corporate Actions']),
    ('Metals Creek Files Early Warning Report', "", ['Regulatory & Compliance'], ['Corporate Actions']),
    ('Cariboo Rose Provides Bi-Weekly MCTO Status Update', "", ['Regulatory & Compliance'], ['Listings & Exchange']),
    ('Peruvian Metals Announces Delay in Filing Annual Financial Statements', "", ['Regulatory & Compliance'], ['Listings & Exchange', 'Financials']),
    ('K92 MINING ANNOUNCES INCLUSION IN THE S&P/TSX COMPOSITE INDEX', "", ['Marketing Announcement'], ['Listings & Exchange']),
    ('Goldcliff Trench Samples 3.14 g/t Gold at Aurora', "", ['Sampling & Geoscience Results'], ['Drill Results']),
    ('Discovery Intercepts 337 g/t AgEq over 34 m and 606 g/t AgEq over 18 m Below the PEA Open Pit at Cordero', "", ['Drill Results'], ['Economic Studies']),
    ('Altius Resources Inc. Exercises Warrants of Orogen Royalties Inc.', "", [], ['Royalties & Streams']),
]

# Older cases whose expectation changed with Justin's scope answers (TAGFIX_V1, 2026-09-27)
_V11_REEXPECT = {'Pacific Ridge Options Yukon Gold Projects to Labrador Gold': (['Property Options & Staking'], ['Mergers & Acquisitions']), 'Alma Gold Announces Acquisition of Exploration Licences in Dialakoro Region': (['Property Options & Staking'], ['Mergers & Acquisitions']), 'Oakley Ventures Announces Exercise of Koster Dam Property Option': (['Property Options & Staking'], ['Mergers & Acquisitions']), 'Black Mammoth Metals Stakes 185 Claims at Quito NV': (['Property Options & Staking'], ['Mergers & Acquisitions']), 'Anteros Returns High-Grade Lead-Zinc-Silver in Surface Samples': (['Sampling & Geoscience Results'], ['Drill Results']), 'MANNING VENTURES SAMPLES UP TO 4.77% Cu AT THE COPPER HILL PROJECT': (['Sampling & Geoscience Results'], ['Drill Results']), 'Live Energy Minerals Corp. Reports Initial Samples Returning up to 1907 ppm Lithium at McDermitt': (['Sampling & Geoscience Results'], ['Drill Results']), 'Silver Tiger Announces Normal Course Issuer Bid': (['Share Capital & Compensation'], ['Corporate Actions']), 'WESDOME ANNOUNCES AUTOMATIC SHARE PURCHASE PLAN': (['Share Capital & Compensation'], ['Corporate Actions', 'Mergers & Acquisitions']), 'Waraba Gold Limited Unaware of Any Material Change': (['Regulatory & Compliance'], ['Listings & Exchange']), 'Argyle Responds to OTC Markets Request on Recent Promotional Activity': (['Regulatory & Compliance'], ['Listings & Exchange'])}
SELF_TEST = [(c[0], c[1]) + tuple(_V11_REEXPECT[c[0]]) if c[0] in _V11_REEXPECT else c for c in SELF_TEST]

SELF_TEST += [
    # --- TAGFIX_V2 (2026-09-27) -------------------------------------------------
    ('Santacruz Silver Produces 3.2 Million Silver Equivalent Ounces in 2021', '', ['Production Results'], ['Resource Estimates']),
    ('Global Energy Metals Announces Offtake Agreement for Werner Lake Cobalt Project', '', ['Mine Development & Operations'], ['Partnerships & JV']),
    ('Rock Tech Lithium joins the European Battery Alliance', '', [], ['Partnerships & JV']),
    ('Patriot Gold Announces First Pour From Its Arizona Moss Gold Mine', '', ['Mine Development & Operations'], ['Production Results']),
    ('Austral Gold Restarts Production at Casposo, Argentina', '', ['Production Results'], []),
    ('Carlin Provides Corporate Update', 'Carlin Gold Corporation (TSXV: CGD) (the “Company”) is pleased to announce that it has completed the previously announced consolidation of all of its issued and outstanding share capital. More text.', ['Corporate Actions'], ['Corporate Updates']),
]

# Older cases whose expectation changed with TAGFIX_V2 (2026-09-27)
_V12_REEXPECT = {'Canadian Copper Signs Offtake Agreement and Credit Facility with Ocean Partners': (['Mine Development & Operations', 'Debt & Credit Facilities'], ['Partnerships & JV'])}
SELF_TEST = [(c[0], c[1]) + tuple(_V12_REEXPECT[c[0]]) if c[0] in _V12_REEXPECT else c for c in SELF_TEST]

SELF_TEST += [
    # --- TAGFIX_V4 (2026-09-27) -------------------------------------------------
    ('Telson Announces Casualty at Tahuehueto', '', ['Mine Development & Operations'], ['Corporate Updates']),
    ('Nord Completed Conceptual Study to Guide Strategy and Targeting by Evaluating Open-Pit Concept at Castle East', '', ['Economic Studies'], ['Corporate Updates']),
    ('Holding(s) in Company', '', ['Regulatory & Compliance'], ['Corporate Updates']),
    ('K92 MINING RELEASES 2024 SUSTAINABILITY REPORT: DELIVERING SUSTAINABLE VALUE', '', ['Corporate Updates'], ['Financials']),
]

SELF_TEST += [
    # --- TAGFIX_V5 (2026-09-27) -------------------------------------------------
    ('Burin Gold appoints new Chief Financial Officer and announces change of auditor', '', ['Regulatory & Compliance'], []),
    ('Blue Sky Uranium Advances Ivana Project with Metallurgical Test Program and Feasibility Engineering Agreements', '', ['Metallurgy & Processing'], []),
    ('Avalon and Fort William First Nation Sign Letter of Intent to Collaborate on Development of Thunder Bay Lithium Refinery', '', [], ['Metallurgy & Processing']),
    ('Energy Materials for Tomorrow Falcon Files NI 43-101 Technical Report for Integrated Development Plan to Produce Anode Material', '', [], ['Resource Estimates']),
    ('Millennial Potash Drillhole Resampling Results for BA-003 Further Confirms Extensive Robust Potash Horizons Including 28.6m of 58.9% Carnallite', '', ['Drill Results'], []),
    ('MELIOR SECURES LOAN FACILITY FOR RESTART OF THE GOONDICUM MINE', '', ['Mine Development & Operations'], []),
    ('Metallurgical Innovation and Risk Mitigation Update Tiros Titanium and Rare Earths Project', '', ['Metallurgy & Processing'], []),
    ('AuMEGA Metals Commences Diamond Drilling at Cape Ray and Announces Partial Diamond Drill Results from Bunker Hill', '', ['Drill Results'], []),
    ('SOMA GOLD ANNOUNCES A POSITIVE PRELIMINARY ECONOMIC ASSESSMENT AND UPDATED MINERAL RESOURCE FOR ITS COLOMBIAN PROJECTS', '', ['Resource Estimates'], []),
    ('AFRICAN ENERGY METALS ANNOUNCES EXTENSION ON MALI ACQUISITION AGREEMENT, APPOINTMENT OF NEW AUDITOR AND LATE FILING OF FINANCIAL STATEMENTS', '', ['Regulatory & Compliance'], []),
    ('Clarification: Historical Mineral Resource Estimate at Roger Project', '', ['Resource Estimates'], []),
    ('Golden Independence Files NI 43-101 Technical Report on Sedar', '', ['Resource Estimates'], []),
    ('FPX Nickel Renews Global Generative Exploration Alliance with JOGMEC', '', ['Partnerships & JV'], []),
    ('Frontier Lithium Announces Excellent PFS- level Metallurgical Results Producing Spodumene Concentrate from the Spark Deposit', '', ['Metallurgy & Processing'], []),
    ('Xtra-Gold Announces Possible Delay in Filing Year-End Reporting Documents', '', ['Regulatory & Compliance'], []),
    ('Tahltan Land to be Protected in Partnership with Conservation Organizations, Skeena and the Province', '', ['Partnerships & JV'], []),
    ('Highest Uranium Extraction Combined with Lowest Acid Consumption Achieved In Leach Testing at Macusani', '', ['Metallurgy & Processing'], []),
    ('First Mining’s Joint Venture Partner Big Ridge Gold Completes Stage 1 Earn-In for the Hope Brook Gold Project, Ontario, Canada', '', ['Partnerships & JV'], []),
    ('Magnetic Separator and Dewatering Equipment Arrive at the El Peñón Processing Facility', '', [], ['Metallurgy & Processing']),
    ('SRG Graphite Files NI 43-101 Technical Report for Previously Announced Gogota Nickel- Cobalt-Scandium Deposit Maiden Mineral Resource Estimate', '', ['Resource Estimates'], []),
    ('Trident Resources Corp. Announces Updated Mineral Resource Estimates for Four La Ronge Gold Belt Deposits in Northern Saskatchewan, Canada', '', ['Resource Estimates'], []),
    ('Global Atomic Clarifies Niger’s Suspension of New Mining Permits', '', [], ['Mine Development & Operations']),
    ('International Prospect Ventures Signs Exploration Agreement with the Matachewan First Nation and Mattagami First Nation (Wabun Tribal Council)', '', ['Partnerships & JV'], []),
    ('DELTA AND YORKTON BEGIN DRAFTING DEFINITIVE AGREEMENT ON THE SALE OF THE BELLECHASSE-TIMMINS PROPERTY', '', ['Mergers & Acquisitions'], []),
    ('HUNT MINING CORP. ANNOUNCES PROPOSED REVERSE-TAKEOVER TRANSACTION WITH PATAGONIA GOLD PLC', '', ['Mergers & Acquisitions'], []),
    ('Metals Creek Acquires Property in The Shebandowan Greenstone Belt near Delta Resources.', '', ['Mergers & Acquisitions'], []),
    ('SCOTTIE RESOURCES INTERCEPTS 9.0 G/T GOLD OVER 7.39 METRES AND 14.5 G/T GOLD OVER 3.65 METRES AT SCOTTIE GOLD MINE PROJECT', '', ['Drill Results'], []),
    ('SSR MINING PROVIDES UPDATE ON ÇÖPLER INCIDENT', '', ['Mine Development & Operations'], []),
    ('Altair Resources to Rely on Temporary Relief Granted By Regulators in Filing Annual Financial Documents', '', ['Regulatory & Compliance'], []),
    ('Red Pine Discovers Significant Gold Mineralization in Faulted Extension of the Jubilee Shear on the Wawa Gold Project', '', ['Drill Results'], []),
    ('Trek Mining Announces Positive Feasibility Study for the Aurizona Gold Mine and Award of EPCM Contract to Ausenco', '', ['Mine Development & Operations'], []),
    ('TOTEC RESOURCES ANNOUNCES CLOSING OF QUALIFYING TRANSACTION AND ANTICIPATED TRADING DATE', '', ['Mergers & Acquisitions'], []),
    ('South Star Announces Re-Start of Santa Cruz Plant Ahead of Schedule', '', ['Mine Development & Operations'], []),
    ('Altair to Joint Venture Prince Mine and Proposed Share Consolidation', '', ['Partnerships & JV'], []),
    ('Black Iron Progresses Construction Financing and Receives Strong Support From Ukraine’s Prime Minister', '', [], ['Mine Development & Operations']),
    ('Peruvian Metals on Track for Full Production for 2026 at the Aguila Norte Processing Plant and Reports Positive Sample Results from the Tailings Area', '', [], ['Metallurgy & Processing']),
    ('Dynacor Enters into Non-Binding Letter of Intent Offer to Acquire Processing Plant and Assets in Ecuador', '', [], ['Metallurgy & Processing']),
    ('WINSHEAR COMMENCES CONSTRUCTION OF DRILL ROADS AND FIELD CAMP AHEAD OF ITS MAIDEN 1,600M DRILL PROGRAM AT THE GABAN GOLD PROJECT IN PERU', '', [], ['Mine Development & Operations']),
    ('Colibri Resource Corporation Advances Growth Strategy to Unlock Value at EP Gold Project and Pilar Joint Venture', '', ['Partnerships & JV'], []),
    ('Avrupa Minerals Updates Drilling Results at the Sesmarias VMS target, Alvalade JV, Portugal', '', [], ['Partnerships & JV']),
    ('Equitorial Exploration’s 50/50 Joint Venture Magnesium Project with Mag One Products Inc. Will Not Require Environmental Evaluation', '', ['Partnerships & JV'], []),
    ('Lumwana Seeks Long-Term Partnership With Zambian Government', '', ['Partnerships & JV'], []),
    ('Standard Lithium Signs LOI for Development of Continuously-Operating Demonstration Pilot Plant', '', ['Metallurgy & Processing'], []),
    ('Serengeti Settles Final Joint Venture Contract for Kwanika Project with Posco-Daewoo', '', [], ['Mergers & Acquisitions']),
    ('NOBLE PLAINS URANIUM CLOSES ON DUCK CREEK PROJECT IN THE HEART OF POWDER RIVER BASIN Exploration Target Range Supported by New NI 43-101 Technical Report', '', [], ['Resource Estimates']),
    ('ARIANNE PHOSPHATE SELLS ITS JAMES BAY AREA ROYALTY FOR $2,350,000 -transaction significantly increases financial position without any shareholder dilution', '', [], ['Mergers & Acquisitions']),
    ('Lake Victoria Gold Strengthens In-Country Leadership to Support Imwelo Construction Readiness', '', [], ['Mine Development & Operations']),
    ('PPX CLOSES FIRST TRANCHE OF CONSTRUCTION FACILITY', '', [], ['Mine Development & Operations']),
    ('Pacific Empire Assays to 2.95 g/t Gold & 0.65% Copper from Outcrop at Trident', '', [], ['Drill Results']),
    ('Blackrock Silver Announces Silver Cloud Results; Tonopah West Resource Update Timeline', '', ['Resource Estimates'], []),
    ('Conquest Announces Exercise of Royalty Option VerAI Drill Program to Commence on High Priority AI Targets', '', [], ['Mergers & Acquisitions']),
    ('MONUMENTAL ENERGY ENTERS INTO AN OPTION ACQUISITION AGREEMENT FOR THE TRANSFER OF THE SALAR DE TURI PROJECT', '', [], ['Mergers & Acquisitions']),
    ('CORRECTION OF NEWS RELEASE DATED FEBRUARY 22, 2024', '', [], ['Regulatory & Compliance']),
    ('Class 1 Nickel Commences work at Alexo-Dundonald to Upgrade and Increase Mineral Resources', '', ['Resource Estimates'], []),
    ('QC Copper Issues a correction to News Release', '', [], ['Regulatory & Compliance']),
    ('NINE MILE METALS MAINTAINS WEDGE PROJECT OPTION WITH SECOND ANNIVERSARY PAYMENTS', '', [], ['Mergers & Acquisitions']),
    ('Blackrock Silver Reports 90% to 98% Gold and 81% to 94% Silver Recoveries from Initial Metallurgical Testwork at Tonopah West', '', [], ['Drill Results']),
    ('Carlyle Recovers 80% Gold in Preliminary Newton Metallurgical Testing', '', [], ['Drill Results']),
    ('Telson Mining Corp Issues Correction to Press Release Announcing Renewable Power Purchase Agreement', '', [], ['Regulatory & Compliance']),
    ('FLOW METALS ANNOUNCES CORRECTION TO NEWS RELEASE', '', [], ['Regulatory & Compliance']),
    ('Telson Mining Corporation clarifies definition of Cash Flow in news release declaring Commercial Production at its Campo Morado Mine.', '', [], ['Regulatory & Compliance']),
    ('Magna Terra Discovers Massive Sulphide Mineralization in Boulders and Provides an Update on the Rocky Brook Project in the Bathurst Mining', '', [], ['Drill Results']),
]

SELF_TEST += [
    # --- TAGFIX_V6 (2026-09-28) -------------------------------------------------
    ('Madison Metals Announces Exercise of Warrants', '', ['Share Capital & Compensation'], ['Financings']),
    ('TerraX receives $1,910,759 from the exercise of warrants', '', ['Share Capital & Compensation'], ['Financings']),
    ('Redstar Gold Comments on Trading Activity at the Request of IIROC', '', ['Company Commentary'], ['Listings & Exchange']),
    ('AUXICO PROVIDES UPDATE ON MANAGEMENT CEASE TRADE', '', ['Regulatory & Compliance'], ['Listings & Exchange']),
    ('Notice of Default Update', '', ['Regulatory & Compliance'], ['Listings & Exchange']),
    ('ALMADEN DISCOVERS HIGH GRADE MINERALISATION IN A PREVIOUSLY UNDRILLED AREA INSIDE THE PFS PIT', '', ['Drill Results'], ['Economic Studies']),
    ('Northern Graphite Announces $2.2 Million Non-Brokered Private Placement Proceeds to help finance Baie-Comeau Battery Anode Material Plant Feasibility Study', '', ['Financings'], ['Economic Studies']),
    ('ALASKA SILVER ANNOUNCES PUBLIC FILING OF REGISTRATION STATEMENT ON FORM S-1 FOR PROPOSED U.S. INITIAL PUBLIC OFFERING', '', ['Financings'], ['Company Commentary']),
    ('Tanzanian Royalty Announces the Sale of Common Shares of $281,000', '', ['Financings'], ['Royalties & Streams']),
    ('Galway Metals Announces Option Payment for Royalty Buy Back at Its Clarence Stream Property', '', ['Royalties & Streams'], ['Property Options & Staking']),
    ('TRIGON COMMENCES MINING OPERATIONS AT KOMBAT MINE, NAMIBIA', '', ['Mine Development & Operations'], ['Production Results']),
    ('K92 Achieves Commercial Production at Kainantu Gold Mine', '', ['Production Results'], []),
    ('TOREX GOLD SUCCESSFULLY COMPLETES AMENDED DEBT FACILITY', '', ['Financings', 'Debt & Credit Facilities'], []),
    ('Class 1 Nickel Announces Option Cancellation', '', ['Property Options & Staking'], []),
    ('TINKA ANNOUNCES FILING OF NI 43-101 TECHNICAL REPORT FOR THE PEA ON THE AYAWILCA PROPERTY, PERU', '', ['Economic Studies'], []),
    ('Cameco reports Q1 results: 2024 outlook remains solid', '', ['Financials'], ['Shareholder Letters & Outlook']),   # TAGFIX_V7: Justin 2026-09-28
    ('CERRADO GOLD ANNOUNCES FAILURE TO FILE CEASE TRADE ORDER', '', ['Listings & Exchange'], []),
    ('LAHONTAN RECEIVES BLM APPROVAL FOR WEST SANTA FE DRILL PROGRAM, GRANTS OPTIONS', '', ['Permits & Approvals'], []),
    ('Hunt Mining Announces 7th Shipment from Martha Project', '', ['Production Results'], []),
    ('Canterra Minerals Completes Soil Sampling at Noel Paul Property, Newfoundland', '', ['Sampling & Geoscience Results'], []),
]

SELF_TEST += [
    # --- TAGFIX_V7 (2026-09-28) -------------------------------------------------
    ('Spanish Mountain Gold Clarifies Technical Disclosure', '', ['Regulatory & Compliance'], ['Technical Reports (NI 43-101)']),
    ('KALO GOLD CLARIFIES TECHNICAL DISCLOSURE AND FILES AMENDED TECHNICAL REPORT', '', ['Technical Reports (NI 43-101)', 'Regulatory & Compliance'], []),
    ('Neotech Metals Clarifies Technical Report Disclosure', '', ['Technical Reports (NI 43-101)'], []),
    ('DYNACOR REPORTS SALES OF US$26.9 MILLION FOR JANUARY 2024', '', ['Production Results', 'Financials'], []),
    ('IAMGOLD Reports Third Quarter 2023 Results', '', ['Financials'], []),
    ('IAMGOLD PROVIDES PRELIMINARY OPERATING RESULTS FOR THE THIRD QUARTER 2021', '', ['Production Results'], ['Financials']),
    ('THE PHILIPPINES ANNOUNCES THE LIFTING OF THE MORATORIUM ON EXPLORATION LICENSES', '', ['Permits & Approvals'], ['Legal & Disputes']),
    ('Excelsior Mining Receives No Appeal on Recently Granted State Operating Permit', '', ['Permits & Approvals'], ['Legal & Disputes']),
    ('Emerita Appeals Aznalcollar Exploitation Permit Grant', '', ['Legal & Disputes'], []),
    ('Hudbay Will Appeal Unprecedented Rosemont Court Decision', '', ['Legal & Disputes'], []),
    ('Elemental Royalties Announces Name Change to Elemental Altus Royalties Corp', '', ['Corporate Actions'], ['Royalties & Streams']),
    ("Elemental Royalties Board Continues to Recommend Rejection of Gold Royalty's Hostile Takeover Bid", '', ['Mergers & Acquisitions'], ['Royalties & Streams']),
    ('Voyageur Mineral Explorers Corp. and Evolve Strategic Element Royalties Ltd. Announce $20 Million Financing', '', ['Financings'], ['Royalties & Streams']),
    ('Vox Royalty Acquires Producing Wonmunna Royalty in Western Australia', '', ['Royalties & Streams'], []),
    ('China Gold International Reports Year-End 2018 Results and Provides 2019 Outlook', '', ['Financials'], ['Shareholder Letters & Outlook']),
    ('Nickel 28 Annual Shareholder Letter', '', ['Shareholder Letters & Outlook'], []),
]

SELF_TEST += [
    # --- TAGFIX_V8 (2026-09-28) -------------------------------------------------
    ('Acme Gold Intersects 12.5 g/t Au over 8.0 m at Red Hill', '', ['Drill Results', 'Exploration Programs'], []),
    ('Acme Gold Grab Samples Return up to 45.2 g/t Gold at Blue Lake Property', '', ['Sampling & Geoscience Results', 'Exploration Programs'], []),
    ('Acme Gold Webinar Replay: Drill Results from Red Hill', '', [], ['Exploration Programs']),
    ('Libra Congratulates Athena Gold on New Discovery in Red Lake', '', ['Company Commentary'], ['Exploration Programs']),
    ('Acme Mining Completes Reverse Takeover of Beta Minerals', '', ['Management Changes'], []),
    ('Acme Minerals Engages Investor Relations Firm Red Cloud Communications', '', ['Marketing Announcement'], []),
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
