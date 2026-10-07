"""Drill Results extractor, facts-store version (DRILL_V1). Phase 2b #1 of the revised plan.

Replaces portal/drill_extract.py (v2.4) as the source of /drills once it passes the
accuracy gate. It reuses that module's text clean-up, units, metal vocabulary, grade
grammar, plausibility caps and scoring, and changes what the analysis in
claude/MNT_DRILL_REBUILD_ANALYSIS_2026-09-16.md found wrong:

  1. every candidate interval is kept, then judged on its own, with a reason code
  2. headline figures pass the same checks (they must agree with the body)
  3. surface samples (grab, chip, channel, trench ...) are dropped, not just ranked lower
  4. handheld / portable XRF readings and visual estimates are dropped
  5. "historical" is judged on the interval's own sentence, with a wider vocabulary
     (previous operator, announcement dated, post-quarter, "In 2010 trenching" ...)
  6. hole ids: case-sensitive ids, ids starting with digits, broken hyphens repaired,
     and the hole is attached to EACH interval, never "first id in the text"
  7. results tables (Hole / From / To / Length / grades) are read
  8. project names are chosen by rank: Project/Property/Deposit/Mine/Complex first,
     Camp/District next, Zone/Trend/Target/Prospect only when nothing better exists

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    what the facts store keeps (one record per release)
to_prediction(records)  -> dict|None   what the accuracy check compares

1.0.6 (2026-09-27): onto the shared project-name helper portal/project_names.py, conservatively (like Exploration
1.2.2). The release's project is still 1.0.5's find_project (ranked: Project/Property/Mine first, then Camp/District,
then Zone/Target). The helper (PN.projects: its main project first) only
  - fills a blank: with a project the headline names, or else with the helper's main project when the opening
    800 characters name it, the text calls it a Project/Property/Mine..., and it is project-level (not a deposit --
    "Detour Lake Deposit" on an Emperor release, "Eskay Creek Deposit" on a Tower release are neighbours);
  - replaces a name that is no project: one the helper will not read as a name ("VMS", "Higher Grade", "Cu-Au",
    "Vanadium", "All") and that the text never writes before Project/Property/Mine... (so Clean Air's "Current" and
    Cambria's "Premier" stay), with a project-level name from the headline, the opening text or the helper's main pick.
  Names in this page's form: no trailing suffix, metal list or "and <metal>" tail, no "VMS"/"polymetallic"; a list
  ("Tom and Jason Deposits") is not taken. The fingerprint also covers the helper.

1.0.8 (2026-09-30): background no longer shown as the release's new drill result, and the headline hole fixed
(ACC150 "Drill headline hole" 82%). Measured on the ACC150 blind labels; see claude/ notes of the fix.
  - NEWS_V1 (release_news): the reader reads what the release says it announces -- the headline clause by clause and
    the company's own statement ("X is pleased to report ...") -- before any figure can stand. A plan, a program
    started / resumed / completed, pending assays, visual logs, probe / scintillometer / XRF readings, surface channel /
    chip / grab / trench / costean samples, historic data, an option / sale / agreement / financing / quarterly or
    annual report / PEA / survey / new target, paid commentary: is_result false with that reason (plan, pending,
    visual, instrument, surface, historical, previously_reported, not_results, investee, no_new_results), unless the
    lead plainly reports new assays. An update that says neither needs a lead sentence reporting a hole's graded
    interval that is not background (earlier dates, citations, old years or old hole ids, "to date", "anticipated").
  - background vocabulary: "as reported August 12, 2024", "(..., released July 23, 2024)", "previously returned",
    "earlier ... result", "earlier holes", "Hole X reported ...", "highlights ... to date are", "drilled by <Company>",
    "discovery hole ... which returned", "Other intercepts from this program" after a background sentence; the
    "see ... news release" citation now matches (it never matched "release"); a figure inside the citation's own
    brackets is the cited release's; "improved the grade to X" is the new figure; "Au Eq." no longer ends a sentence.
  - hole years: "DDH88-11" is a 1988 hole, "DDH04CB1" and "18-EP-025" carry years, and where the release's holes end in
    the year ("XY185-19"), "XY104-10" is an earlier program's hole.
  - HOLE_REPEAT_V1: the top interval takes the hole every other full quotation of it agrees on (highlights, the hole's
    paragraph, the table) when its own hole came from a loose rule, none, or the headline copy; a headline copy whose
    every repeat is background is background. Hole ids: "ABC18_046", "DD22-ABC-006", "Hole GR-28", "ABC7795: 15.2 m",
    "(AB21RC06)" after a figure, a list's heading id, a bracketed hole closing a list of figures, a table's one hole
    named above its header; table-credited holes count as firm.
  - PDF repairs: "115 . 38", "1.2 5 g/t", "si lver", "v isual", non-breaking hyphens and "AB26 - 10".
  - project names: accented letters kept ("Lac Tete" was "Lac T"); "Historical", "VMS", "SW", "Gold-Rich Major"
    are not names.

1.0.9 (2026-10-01): its own news only (NEWS_V2). Outside the tag, the wrong rows of 1.0.8 were whole releases with no new
assays of their own that quote intercepts released earlier, by another company or decades ago. The headline and the
company's statement now name more kinds of news that are not new assays, and the lead figures of an update that says
neither are checked harder:
  - drilling logistics (a rig added or operational, "three drills", core cut or logged, samples shipped or sent to the
    lab, preparations) is a plan; targets defined / refined / generated, an agreement signed, ground consolidated, an
    approval, permit or land lease, a clarifying disclosure are other news; historic resources / estimates are historical;
    "anticipates / awaits / expects ... assays" is pending; "surface work / exploration" is surface; a statement that
    reviews or summarises results, or sets goals, is a recap; an investor's equity-portfolio update is investee.
  - a sampling or historic headline with no drill word is not made a drill result by a statement of "results" that names
    no drilling.
  - the statement: "ispleased" (PDF joins) and "report that" count; with no "is pleased to", the text after the company's
    defined name is its statement; a vague first statement ("a major milestone") is explained by a second "is pleased to"
    within two sentences (not a quotation).
  - lead figures of an update: a hole a sentence cites as released before is background where it recurs; a sentence
    whose next one is its citation ("(see press release of June 19, 2024)"), "Link to ... News Release", "from <last
    year>", "Five drill holes ..." after a citation; ids that carry an earlier year with no separator ("OL21019" where
    the text pairs "OL20004" with 2020); with no dateline, the latest year the headline or statement names dates it.
  FIX3 (2026-10-01, same VERSION): full-text losses fixed. On the full text the box reads, 1.0.9 dropped tagged releases
  whose old row was real news. The kinds, each fixed in general terms (self-tests "109f"):
  - a citation inside the company's own claim ("announce drill results for one hole from the recently completed (See News
    Release: June 11) program", "assay results from the previously reported VG intersection") is about the program or an
    earlier visual report: it is cut from the statement; a statement that cites the results themselves still counts;
  - the statement: a second "is pleased to" with new results stands after a corporate first one; named holes before a
    project's study stage are not a corporate item; "summarized in Table One" is no look back; soil or geophysical
    anomalies that targeted the holes are no surface samples; an update on drilling "progress" / drilling "completed" is
    an update; drilling that "has confirmed / extended" is a drill claim; a hand-held spectrometer or cps is an instrument;
  - the headline: drill results first and a corporate item after ("Infill Drill Results and Feasibility Study Update",
    but not "MRE Update following Drill Results"); ", and further drill results" is a clause of its own; a visual
    sub-headline run on well after the assayed figure; a completed program's figures; "Drilling Discovers";
  - the lead: "preliminary / initial / final results include", "new highlights include", "the update includes drilling
    results", "assay highlights from hole", a "Table 1." assay caption (no sentence break after "Table 1."), "analyses have
    been received"; a run-together table is judged by its opening; "intersected by drilling", a length in other units in
    brackets, grams per tonne written out; a hole named in a sentence stays with the figures of the next two; "this year"
    is no back-reference and "no previous drilling" no background; "the most significant intercept" after a citation, and
    any claim whose holes all carry an earlier year, stay background;
  - figures: a background marker after the figure that belongs to another hole ("... down-dip of previously reported hole
    X (see ...)", "... below hole Y, ... (see press release ...)"), to a relation ("relative to historical drilling ...")
    or to a quotation no longer condemns the figure, but "(both previously released ...)" right after it does;
    "further to its news release" introduces new results; a headline copy is overruled only by its repeats' own
    sentences, not by a lead-in they inherit; "less than 2 ft of 0.02%" is a reporting cut-off; "the 2022 discovery" is
    an earlier year's work;
  - hole years: a grid or coordinate number ("AB36-262441") and two digits after the release year below 50 ("AB25-10" in
    2021) are no year.

Self-tests: python3 -m portal.extractors.drill_results
"""
from __future__ import annotations

import re

from portal import drill_extract as D
from portal import facts as F
from portal import project_names as PN   # 1.0.6: the shared project-name helper
from portal import fingerprint as FP     # 1.0.7: fingerprints follow exactly the helper code this reader runs

NAME = "drill_results"
VERSION = "1.0.10"  # 2026-10-01: no row when the headline or statement says the release is about something else (NEWS_V2); full-text losses fixed; 2026-10-04 FIX5: the shown hole is replaced only by the one hole every quotation of the figure sits with (row, list item, heading or "in hole X")
KIND = "drill_result"
TAG = "Drill Results"
MAX_INTERVALS = 150

MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december"
          "|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
_MONTH_NUM = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december"], 1)}


# ------------------------------------------------------------------ text repair for hole ids
def repair(text: str) -> str:
    """Join hole ids broken by PDF wrapping or stray spaces. Only letter/digit contexts."""
    t = (text or "").replace("\u2010", "-").replace("\u2011", "-")   # 1.0.8: (non-breaking) hyphen characters: "AB26\u201110"
    t = re.sub(r"(?<=[A-Za-z0-9])-[ \t]*\n[ \t]*(?=[A-Za-z0-9])", "-", t)      # "PLN25-\n205"
    t = re.sub(r"(?<=[A-Za-z]\d)- (?=\d)", "-", t)                              # "HS1- 06"
    # 1.0.8: PDF spacing inside figures: "115 . 38" (a table), "1.2 5 g/t Au, 0.3 3% Cu", "si lver"
    t = re.sub(r"(?<=\d) \. (?=\d)", ".", t)
    t = re.sub(r"(?<![\d.])(\d{1,3}\.\d) (\d{1,2})(?=\s?(?:%|g/t|gpt|ppm)(?![A-Za-z]))", r"\1\2", t)
    t = re.sub(r"(?i)\b(?:s ilver|si lver|sil ver|silv er|silve r|g old|go ld|gol d|c opper|co pper|cop per|copp er|coppe r"
               r"|n ickel|ni ckel|nic kel|nick el|nicke l|v isual|vi sual|vis ual|visu al|visua l)\b", lambda m: m.group(0).replace(" ", ""), t)
    t = re.sub(r"(?<=[A-Za-z]\d\d)- (?=\d)", "-", t)                            # "HS11- 06"
    t = re.sub(r"(?<![A-Za-z])([A-Z]{2,6}) -(?=\d{1,4}-\d)", r"\1-", t)       # "JES -21-43"
    # 1.0.2: "REG 23-21 yielded 38m" when the release also writes "REG-22-01": the same kind of id (RSMX.V)
    # 1.0.8: "hole AB26 - 10" when the release also writes "AB26-10"
    for a_, b_ in set(re.findall(r"(?<![A-Za-z0-9])([A-Z]{1,6}\d{1,4}) [-\u2013] (\d{1,4})(?![\d.,])", t)):
        if re.search(r"(?<![A-Za-z0-9])" + a_ + "-" + b_ + r"(?![\d])", t):
            t = re.sub(r"(?<![A-Za-z0-9])(" + a_ + r") [-\u2013] (" + b_ + r")(?![\d.,])", r"\1-\2", t)
    for pm in set(re.findall(r"(?<![A-Za-z])([A-Z]{2,6}) \d{2}-\d{1,4}\b", t)):
        if re.search(r"(?<![A-Za-z])" + pm + r"-\d{2}-\d", t):
            t = re.sub(r"(?<![A-Za-z])(" + pm + r") (\d{2}-\d{1,4})\b", r"\1-\2", t)
    # 1.0.2: "49.19 g Ag/t", "106.97g Ag eq/t" (Cartier, Eloro) are g/t grades the grammar did not read
    t = re.sub(r"(?<=\d)\s*g\s*(Ag|Au)\s*(eq\.?)?\s*/\s*t\b", lambda m: " g/t " + m.group(1) + ("Eq" if m.group(2) else ""), t)
    # 1.0.2: "25.00 metres grading 0.55 percent copper ("%") and 0.16 grams per tonne ("g/t") gold" (ALEX.V): units in words
    t = re.sub(r"[ \t]*\(\s*[\"\u201c\u201d]\s*(?:%|g/t|ppm|ppb|m)\s*[\"\u201c\u201d](?:[ \t]*(?:Au|Ag|Cu))?\s*\)", "", t)
    t = re.sub(r"(?<=\d)\s*(?:per\s*cent|percent)(?=\s+(?:copper|zinc|lead|nickel|cobalt|molybdenum|lithium|antimony|tungsten|tin|Cu|Zn|Pb|Ni|Li2O|U3O8)\b)", "%", t)
    t = re.sub(r"(?<=\d)\s*grams?\s+per\s+(?:metric\s+)?tonne\b", " g/t", t)
    t = re.sub(r"(?<=\dg/t)\s+of\s+(?=(?:gold|silver|platinum|palladium)\b)|(?<=\d\sg/t)\s+of\s+(?=(?:gold|silver|platinum|palladium)\b)", " ", t)  # "13.96 grams per tonne of gold" (MLM.CN)
    # 1.0.2: "45 ft. of 1.73g/t Au, 84.7g.t Ag" (MASS.V)
    t = re.sub(r"(?<=\d)(\s*)(ft|m)\.(?=\s+(?:of|at|@|grading)\b)", r"\1\2", t)
    t = re.sub(r"(?<=\d)(\s*)g\.t\b", r"\1g/t", t)
    return t


# ------------------------------------------------------------------ sentence units
_BOUNDARY = re.compile(
    r"[.!?](?=[\s\"\u201d)]*\s+[A-Z0-9\"\u201c(\u2022\u25cf\u25aa])"   # end of sentence
    r"|[\u2022\u25cf\u25aa\u25e6\x8a\x8c]"                                      # bullet glyph
    r"|:[ \t]*\n"                                                       # heading or lead-in line
    r"|\n[ \t]*\n[ \t]*(?=[\u2022\u25cf\u25aa\-*]\s)"                   # blank line then a list item
    r"|\n[ \t]*[-*][ \t]+"                                              # dash list item
    r"|\n[ \t]*o[ \t]+(?=[\d.])"                                        # "o 94.6m @ 1.6 g/t" list item
    r"|(?P<para>[ \t]*\n[ \t]*\n(?=[ \t]*(?:[A-Z][a-z]|[\u2022\u25cf\u25aa\"\u201c])))")   # paragraph break


_RE_MID_PHRASE = re.compile(r"(?i)(?:[(,&/\-]|\b(?:of|at|in|on|to|by|an?|or|and|the|for|from|with|grading|returned|include|including))\s*$")


def units(text: str) -> list[tuple[int, int]]:
    """(start, end) spans of sentence-like units. Newlines alone do not split: releases
    often wrap one sentence over many short lines."""
    out, start = [], 0
    for m in _BOUNDARY.finditer(text):
        if text[m.start():m.start() + 1] == "." and re.search(r"(?i)(?:\be\.g|\bi\.e|\bincl|\bapprox|\bvs|\best|\bNo|Eq)$", text[max(0, m.start() - 7):m.start()]):
            continue  # "(e.g. 3.085 g/t Au ...", "0.12 g/t Au incl. 12.8 m", "(est. true width)"
        if m.group("para") and _RE_MID_PHRASE.search(text[max(0, m.start() - 20):m.start()]):
            continue  # a sentence broken over paragraphs ("Post-quarter results of\n\n70.8m ...")
        end = m.end()
        if end > start:
            out.append((start, end))
        start = end
    if start < len(text):
        out.append((start, len(text)))
    return out


def unit_at(spans, pos):
    for i, (s, e) in enumerate(spans):
        if s <= pos < e:
            return i
    return len(spans) - 1 if spans else -1


# ------------------------------------------------------------------ context rules
_RE_XRF = re.compile(r"(?i)\b(?:p?XRF|pxrf|hand[\-\s]?held|portable\s+(?:x[\-\s]?ray|analy[sz]er)|niton|vanta)\b")
_RE_VISUAL = re.compile(
    r"(?i)\b(?:visual(?:ly)?\s+(?:estimat\w*|observ\w*|logg\w*|identif\w*)|estimated\s+(?:visual|sulph|sulf)\w*"
    r"|visual\s+(?:descriptions?|logs?)|(?:logged|estimated)\s+(?:as\s+)?\d[\d.]*\s*%\s*(?:visible|sulph|sulf))")
_RE_ASSAY = re.compile(r"(?i)\b(?:assay\w*|fire\s+assay|laboratory|lab\s+results?|analy[sz]ed|ICP)\b")
_RE_SURFACE = re.compile(
    r"(?i)\b(?:grab|chips?|chip[\-\s]channel|channels?|channel(?:l)?(?:ed|ing)|channel\s+samples?|trench\w*|costeans?|rock\s+samples?|outcrops?"
    r"|soils?|boulders?|float|dump\s+samples?|stockpile\w*|panel\s+samples?|surface\s+samples?|surface\s+sampling"
    r"|bulk\s+samples?|prospecting|till\s+samples?|stream\s+sediment\w*|(?:field|sampling|mapping)\s+program\w*"
    r"|samples?\s+(?:taken|collected)\s+(?:on|at|from)\s+(?:the\s+)?surface|(?-i:Samples)\s+(?:up\s+to\s+)?\d+)\b")
_RE_DRILL_WORD = re.compile(
    r"(?i)\b(?:drill\w*|holes?|DDH|core|RC|reverse\s+circulation|diamond|boreholes?|sonic(?=\s+(?:drill|hole|core|rig|program))|auger|percussion"
    r"|down[\-\s]?hole|intersect\w*)\b")
_RE_HIST = re.compile(
    r"(?i)\b(?:historic(?:al|ally)?\s+(?:[\w&/\-()]+\s+){0,4}(?:drill\w*|holes?|DDH|results?|intercepts?|intersections?"
    r"|highlights?|assays?|data|work|sampl\w*|trench\w*|values?|grades?|programs?|programmes?|campaigns?|core)"
    r"|(?:drill\w*|holes?|results?|intercepts?|intersections?|highlights?|assays?|trench\w*|sampl\w*)"
    r"\s+(?:\w+\s+){0,2}(?:are|were|is|was)\s+historic(?:al)?"
    r"|previous(?:ly)?[\s\-]+(?:report|announc|releas|disclos|drill|trench|sampl|publish|intersect|identif|defin|known|tested|hole|return)\w*"
    r"|(?:highest|best)[\-\s]+grade\s+(?:\w+\s+){0,2}(?:encountered|intersected|returned|drilled)\s+to\s+date\s+(?:at\s+(?:the\s+)?[\w\-]+(?:\s+[\w\-]+){0,2}\s+)?(?:is|was|remains|came)\b"
    r"|past\s+(?:drill\w*|exploration)\s+(?:success|results?|highlights?|programs?)"
    r"|\(\s*(?:" + MONTHS + r")\.?\s+\d{1,2},?\s+(?:19|20)\d\d\s+(?:news|press)\s+release"
    r"|(?:has|have|had)\s+(?:previously\s+)?reported\s+on\s+(?:numerous|several|multiple|many)"
    r"|(?:adjacent|next)\s+to\b[^.]{0,80}\b(?:which|that)\s+(?:has\s+|have\s+)?(?:reported|returned|intersected)"
    r"|re[\-\s]?sampl\w*\s+(?:of\s+)?(?:the\s+)?historic\w*"
    r"|(?:closest|nearest|nearby|neighbou?ring)\s+(?:\w+\s+){0,2}(?:drill\s*)?holes?|neighbou?ring\s+propert(?:y|ies)"
    r"|as\s+(?:previously\s+)?(?:announced|reported|released|disclosed)\s+(?:on|in)\b|recently\s+(?:announced|reported|released)"
    r"|(?:following|after)\s+(?:the\s+)?(?:\w+\s+){0,3}release\s+of"
    r"|(?:in|see)\s+(?:the\s+)?(?:" + MONTHS + r")\.?\s+\d{1,2},?\s+(?:19|20)\d\d,?\s+(?:news|press)\s+release"
    r"|discovery\s+(?:drill\s*)?hole\s*,?\s+(?:which|that)\s+(?:returned|intersected|graded)"
    r"|discovery\s+(?:drill\s*)?hole\b[^.;()]{0,60}?\b(?:which|that)\s+(?:previously\s+)?(?:returned|intersected|intercepted|graded)"  # 1.0.8
    r"|(?:intersections?|intercepts?|results?)\s+(?:[\w\-]+\s+){0,6}?(?:was|were)\s+(?:previously\s+)?reported\s+(?:in|from|by|on)\b"
    r"|(?:original|initial|earlier)\s+(?:[\w\-]+\s+){0,3}(?:intercept|intersection)s?"
    # 1.0.8: "the earlier spectacular result in hole AB033", "Results compare to earlier holes at the site", "Hole AB20-01
    # reported two principal gold zones", "The highlight of the 2018 drilling program to date is ...", "(see link to news release"
    r"|earlier\s+(?:[\w\-]+\s+){0,3}results?|(?:earlier|prior)\s+(?:drill\s*)?holes"
    # 1.0.8: another company's hole: "hole AB-0023, which was drilled by Other Gold Corporation"
    r"|(?:drilled|completed)\s+(?:in\s+(?:19|20)\d\d\s+)?by\s+(?:the\s+)?(?:[A-Z][\w&.\-]*\s+){1,4}(?:Corp\w*|Inc|Ltd|Limited|Resources|Mining|Mines|Minerals|Gold|Metals|Exploration|plc)\b"
    # 1.0.8: "... over 60.60 meters in AB24-03 as reported August 12, 2024", "(6.28 g/t Au over 54.9m, released July 23, 2024)"
    r"|as\s+(?:previously\s+)?(?:announced|reported|released|disclosed)\s+(?:on\s+)?(?:" + MONTHS + r")\.?\s+\d{1,2}"
    r"|\(\s*[^()]{0,80}?\b(?:released|reported|announced)\s+(?:on\s+)?(?:" + MONTHS + r")\.?\s+\d{1,2}"
    r"|(?:drill\s*)?hole\s+[A-Z0-9][\w\-]*\s+(?:previously\s+)?reported\s+(?!today|herein|in\s+this)"
    r"|(?:highlights?|best|highest|standout)\s+(?:[\w\-]+\s+){0,6}?to\s+date\s+(?:is|was|are|were|include[sd]?)"
    r"|see\s+(?:the\s+)?link\s+to\s+(?:the\s+)?(?:news|press)\s+release"
    r"|(?:acquired|compiled|legacy|archival)\s+(?:\w+\s+){0,2}(?:data|database|drill\w*)"
    r"|(?:previous|former|prior)\s+(?:operators?|owners?|explorers?|companies)"
    r"|(?:press|news)\s+releases?\s+(?:dated|of|on)\b|(?:asx\s+)?announcements?\s+(?:dated|of|on)\s+\d"
    r"|see\s+(?:the\s+)?(?:company['\u2019]?s\s+|[A-Z][\w&]*['\u2019]?s?\s+){0,2}(?:asx\s+)?(?:news|press)\s+rel\w*"  # 1.0.8: "rel" alone never matched "release"
    r"|based\s+on\s+(?:(?:19|20)\d\d\s+)?(?:historical\s+)?data"
    r"|previously,?\s+(?:the|this|that|our|its|we)\s"
    r"|see\s+(?:the\s+)?(?:asx\s+)?announcement|\(\s*(?:see\s+)?(?:NR|PR)\s+(?:dated\s+)?(?:" + MONTHS + r")"
    r"|ref(?:\.|er\s+to|erence)?\s+(?:the\s+)?(?:company['\u2019]?s\s+)?(?:press|news)\s+releases?"
    r"|assessment\s+(?:report|file)|prior\s+(?:drilling|programs?|holes?|campaigns?)"
    r"|non[\-\s]compliant|past[\-\s]producing\s+(?:\w+\s+)?(?:results|data)|reported\s+by\s+[A-Z]"
    r"|post[\-\s]quarter|during\s+the\s+(?:previous|last|prior)\s+quarter|quarterly\s+(?:activities\s+)?report"
    r"|activities\s+report"
    r"|(?:discovery|earlier|prior|phase\s+(?:i|1|one))\s+(?:rc\s+|diamond\s+|core\s+)?(?:drill\s*)?holes?\s+[A-Z0-9]"
    # 1.0.2: "follows up on some of the highest-grade silver intercepts reported in the Cobalt Camp in recent years" (NTH.V),
    # "among the highest grades obtained in Quebec" (SOI.V), "Confirming the 2021 Results of" (BYN.V), "Previous Samples Include"
    # (GR.V), "Catch Property, which hosts a ... discovery where inaugural drill results returned" (CAM.V)
    r"|follow(?:s|ed|ing)?\s+up\s+on\s+(?:[\w\-]+\s+){0,6}(?:intercepts?|results?|intersections?)\s+(?:[\w\-]+\s+){0,3}?reported"
    r"|among\s+the\s+highest[\-\s]grades?\s+(?:\w+\s+){0,3}?(?:obtained|reported|intersected|encountered|recorded)"
    r"|confirm\w*\s+(?:the\s+)?(?:19|20)\d\d\s+(?:drill(?:ing)?\s+)?results?"
    r"|previous\s+samples?\s+include"
    r"|where\s+(?:its\s+|the\s+)?(?:inaugural|initial|previous|past|earlier|first)\s+drill(?:ing)?\s+results?\s+returned"
    r"|(?:test|tested|testing|follow\s+up|followed\s+up|offset|twin|down[\s\-]dip\s+of|along\s+strike\s+(?:of|from))"
    r"\b[^.]{0,80}?\b(?:drill\s*)?holes?\s+[A-Z0-9][\w\-]*\s*,?\s*(?:which|that)\s+(?:returned|intersected|intercepted|graded)"
    r")\b|\(\s*(?:AR|SMAD|MDI|GM|MMI)\s+\d[\w\-]*\s*\)")
_RE_ANNOUNCED_DATE = re.compile(
    r"(?i)\b(?:announced|reported|released|disclosed)\b.{0,80}?\b(?:results?|intercepts?|assays?)\b"
    r"|\b(?:results?|intercepts?|assays?)\b.{0,60}?\b(?:announced|reported|released|disclosed)\b")
_RE_DATE = re.compile(
    r"(?i)\b(?:(?P<d1>\d{1,2})\s?(?:st|nd|rd|th)?\s+(?P<m1>" + MONTHS + r")\.?,?\s+(?P<y1>(?:19|20)\d\d)"
    r"|(?P<m2>" + MONTHS + r")\.?\s+(?P<d2>\d{1,2})\s?(?:st|nd|rd|th)?,?\s+(?P<y2>(?:19|20)\d\d))\b")
_RE_YEAR_WORK = re.compile(
    r"(?i)(?:^|[.;:]\s+|\n\s*|\b)(?:in|during)\s+(?P<y>(?:19|20)\d\d)[,\s]+(?:\w+\s+){0,4}?"
    r"(?:trench\w*|drill\w*|sampl\w*|program\w*|campaign\w*|work|exploration)"
    r"|\b(?:drilled|trenched|sampled|completed|conducted)\s+(?:in|during)\s+(?:(?:early|mid|late)[\s\-]+)?(?P<y2>(?:19|20)\d\d)"
    r"|\b(?P<y3>(?:19|20)\d\d)\s+(?:[\w\-]+\s+){0,3}?(?:drill\w*|trench\w*|sampl\w*|programs?|programmes?|campaigns?|discovery)\b"   # FIX3: "the 2022 discovery of"
    r"|\b(?:drill\w*|trench\w*|programs?|programmes?|campaigns?)\b[^.;\n]{0,60}?\b(?:in|during)\s+(?P<y4>(?:19|20)\d\d)\b")
_RE_RECAP_HEADLINE = re.compile(
    r"(?i)\b(?:achievements|year[\s\-]in[\s\-]review|year[\s\-]end\s+(?:review|update|summary|letter)"
    r"|highlights\s+of\s+(?:19|20)\d\d|(?:19|20)\d\d\s+(?:achievements|highlights|review|in\s+review|year\s+in\s+review)"
    r"|annual\s+review|letter\s+to\s+shareholders|quarterly\s+(?:activities\s+)?report|activities\s+report"
    r"|releases?\s+(?:an?\s+)?(?:[\w\-]+\s+){0,2}video|investmentpitch|webinar|podcast|recaps?)\b")  # 1.0.2: NLR.CN "Releases InvestmentPitch Video on ... Drill Results"
_RE_RECAP_BODY = re.compile(
    r"(?i)\b(?:quarterly\s+(?:activities\s+)?report|activities\s+report|report\s+on\s+its\s+activities"
    r"|for\s+the\s+(?:three|six|nine|twelve)\s+months\s+ended|(?:during|for)\s+the\s+(?:march|june|september|december)"
    r"\s+(?:20\d\d\s+)?quarter)\b")
_RE_PENDING_HEADLINE = re.compile(r"(?i)\b(?:results?\b[^.;:|]{0,30}?\b(?:are\s+)?pending|pending\s+(?:assay\s+)?results?|awaiting\s+(?:assay\s+)?results?)\b")


def _headline_pending(hl: str) -> bool:
    """Every clause of the headline that talks about results says they are still to come."""
    clauses = [c for c in re.split(r"[;:|.\u2013\u2014]|\s-\s", hl) if re.search(r"(?i)\b(?:results?|assays?)\b", c)]
    return bool(clauses) and all(_RE_PENDING_HEADLINE.search(c) for c in clauses)
_RE_PROGRAM_YEAR = re.compile(r"(?i)\b((?:19|20)\d\d)\s+(?:(?!to\b|for\b|will\b|and\b)[\w\-]+\s+){0,4}?(?:highlights?|results|intercepts|intersections)\b")
_RE_PRIOR_OPERATOR_RELEASE = re.compile(
    r"(?i)\b(?:these|the)\s+(?:results|assays|holes)\s+(?:are|were)\s+from\b.{0,160}?"
    r"\b(?:previous|former|prior)\s+(?:operator|owner)"
    r"|\b(?:holes?|drilling)\s+(?:completed|drilled)\s+(?:in\s+(?:19|20)\d\d\s+)?by\s+(?:a|the)\s+"
    r"(?:previous|former|prior)\s+(?:operator|owner)")


_RE_SINCE = re.compile(r"(?i)\bsince\s+(?:the\s+|our\s+|its\s+)?(?:last|previous|prior|most\s+recent)\b[^.]{0,40}$")
# a surface word that is part of a name: "Boulder Vein", "4-Trench Zone", "Channel Creek"
_RE_NAME_AFTER = re.compile(r"(?i)\s+(?:Vein|Veins|Zone|Zones|Creek|Lake|Hill|Mountain|Mine|Project|Property|Deposit|Target"
                            r"|Showing|Prospect|Extension|Trend|Road|River|Pit|Structure|Corridor|Area"
                            r"|silver|gold|resources|mining|metals|minerals|exploration|ventures|corp\w*|inc|ltd)\b")


def _month(s):
    s = (s or "").lower().rstrip(".")
    for full, n in _MONTH_NUM.items():
        if full.startswith(s[:3]):
            return n
    return None


def dateline(text: str):
    """(year, month, day) of the release, read from the first date near the top."""
    m = _RE_DATE.search((text or "")[:600])
    if not m:
        return None
    if m.group("y1"):
        return int(m.group("y1")), _month(m.group("m1")), int(m.group("d1"))
    return int(m.group("y2")), _month(m.group("m2")), int(m.group("d2"))


_RE_RELATES = re.compile(r"(?i)\b(?:confirm\w*|twin\w*|validat\w*|verif\w*|correspond\w*|consistent\s+with|identified\s+in"
                         r"|beneath|below|beyond|extend\w*|expand\w*|adjacent\s+to|near|between|infill\w*|fill\w*\s+gaps"
                         r"|follow\w*[\s\-]up|gaps\s+in|supported\s+by|designed\s+to|than|(?:north|south|east|west)\w*\s+of)\b[^.]{0,70}$")
_RE_REFERENCE = re.compile(r"(?i)^(?:see|please|\(|(?:press|news)\s+release|(?:asx\s+)?announcement|ref)")


# FIX3: after the figure, the sentence turns to another hole ("... 100 m below hole AB18-220D, the most southerly
# intersection to date (8.84 g/t ... (see press release ...)") or to a quotation: what follows is about that
_RE_OTHER_HOLE_REL = re.compile(
    r"(?i)\b(?:below|above|beneath|beside|adjacent\s+to|(?:up|down)[\s\-]?dip\s+(?:of|from)|along\s+strike\s+(?:of|from)"
    r"|(?:north|south|east|west)\w*\s+of|previously\s+\w+|prior|earlier|discovery|historic\w*)\s+(?:the\s+)?(?:[\w\-]+\s+){0,2}?"
    r"(?:drill\s*)?holes?\s+[A-Z0-9][\w\-]*\d")
_RE_RELATES_AFTER = re.compile(r"(?i)\b(?:(?:up|down)[\s\-]?dip|along\s+strike|relative\s+to|compared\s+(?:to|with)|step[\s\-]?out\w*\s+from)\b[^.]{0,70}$")
_RE_NEGATED = re.compile(r"(?i)\b(?:no|never|not|without)\s+(?:\w+\s+){0,2}$")


def _in_quote(gap):
    """The gap opens a quotation it does not close."""
    o, c = gap.rfind("\u201c"), gap.rfind("\u201d")
    return o > c or gap.count('"') % 2 == 1


def context_reason(ctx: str, release_date, program_years=(), pos=None, exempt_years=()) -> str | None:
    """Why the figures in this sentence are not new drill assays, or None. pos: where the figure sits in ctx."""
    if _RE_XRF.search(ctx):
        return "xrf"
    if _RE_VISUAL.search(ctx) and not _RE_ASSAY.search(ctx):
        return "visual"
    skip_until = comb_until = -1
    skipped = []
    after_other = False   # FIX3: a marker after the figure was found to be about something else; so is all that follows
    for m in _RE_HIST.finditer(ctx):
        before = ctx[max(0, m.start() - 90):m.start()]
        if pos is not None and pos < m.start() and m.start() < skip_until:
            continue  # the citation belongs to the sub-interval skipped just before it
        if (pos is not None and pos < m.start() and not after_other and not find_holes(ctx[pos:m.start()])
                and re.search(r"(?i)\(\s*(?:both|all|each|these|those|which\s+(?:were|was|are|have\s+been))\s*$", ctx[max(0, m.start() - 30):m.start()])):
            return "historical"   # FIX3: "... AB25-04 (28.97 g/t Au over 21.76 m) (both previously released; see ...)"
        if pos is not None and pos < m.start() and (after_other or _RE_OTHER_HOLE_REL.search(ctx[pos:m.start()])
                                                    or _in_quote(ctx[pos:m.start()]) or _RE_RELATES_AFTER.search(before)):
            after_other = True
            continue  # FIX3
        if re.match(r"(?i)previous|prior|historic", m.group(0)) and _RE_NEGATED.search(before[-30:]):
            continue  # FIX3: "the vein, which has had no previous drilling"
        if _RE_SINCE.search(before) or re.search(r"(?i)\bfurther\s+to\s+(?:its|our|the)\s+(?:[\w\-]+\s+){0,2}$", before):
            continue  # "completed since the last news release dated ..." / FIX3 "further to its news release of ..." introduce NEW results
        if (re.match(r"(?i)historic|prior\s+drill|previous\s+drill", m.group(0)) and _RE_RELATES.search(before)
                and (pos is None or pos < m.start() or not re.match(
                    r"(?i)^[^.;]{0,50}?(?:\bwhich\b|\bthat\b|\breturn\w*|\bgrad\w*|\bassay\w*|\(|:)", ctx[m.end():pos]))):
            after_other = after_other or (pos is not None and pos < m.start())   # FIX3
            continue  # new holes "confirming / beneath / filling gaps in the historic drilling"
        if (pos is not None and pos > m.end() and _RE_REFERENCE.match(m.group(0))
                and ctx.rfind("(", 0, m.start()) > ctx.rfind(")", 0, m.start())
                and ")" in ctx[m.end():pos]):   # 1.0.8: a figure inside the same brackets is the cited release's own
            continue  # "(see news release dated ...)" refers to what came before it, not to a later figure
        if (pos is not None and pos > m.end() and re.search(r"(?i)\b(?:improv|increas|extend|expand|upgrad|rais)\w*\s+(?:the\s+)?"
                                                             r"(?:[\w\-]+\s+){0,3}(?:to|at)\s+$", ctx[max(m.end(), pos - 80):pos])):
            continue  # 1.0.8: "extended the previously-reported intersection and improved the grade to 1,203 ppm over 580 feet"
        lead = ctx[max(0, m.start() - 45):m.start()]
        if (pos is not None and pos < m.start() and re.search(
                r"(?i)(?:includ\w*|incl\.?|within|encompass\w*|expand\w*|extend\w*|increas\w*|enlarg\w*|upgrad\w*|improv\w*)"
                r"\s+(?:\w+\s+){0,2}(?:the|a|an|its|our|of|on)?\s*$", lead)):
            skip_until = m.end() + 130
            skipped.append((m.start(), min(len(ctx), skip_until)))
            continue  # 1.0.1: "16.37 g/t over 16.0 m including the previously announced interval of 67.1 g/t over 3.0 m"
        if pos is not None and pos < m.start() - 20 and m.group(0)[:8].lower() == "previous":
            after_other = True   # FIX3: and the citation that closes that clause is about the old hole too
            continue  # "27 m @ 37 g/t (APC-162) ... up-dip of previously released hole X": the old hole comes after
        if (pos is not None and pos < m.start() and re.search(r"[.;]\s|\n\s*(?=(?:This|These|The|That)\b)", ctx[pos:m.start()]) and re.search(r"(?i)previous|announc|report|releas", m.group(0))
                and re.match(r"(?i)^\s*(?:(?:hole|drill\s*hole)\s+)?(?:[A-Z]{2,}[\w\-]*\d|\d[\d.,]*\s*(?:m\b|metres|meters|g/t|%))", ctx[m.end():m.end() + 40])):
            continue  # 1.0.2: "14.00 m grading 0.84% Cu ... . This intercept confirms ..., as previously reported in ANRD049 interval of 120 m" (ALEX.V)
        if pos is not None and m.start() < comb_until:
            continue
        if (pos is not None and pos > m.end() and re.search(r"(?i)report|releas|announc", m.group(0))
                and re.match(r"(?i)^[^.;]{0,40}?\b(?:mineral\s+resource\s+estimate|resource\s+estimate|MRE|technical\s+report|PEA|PFS|feasibility\s+study)\b", ctx[m.end():])):
            continue  # 1.0.2: "1.68 million ounces of Inferred resources, as reported in the 2021 mineral resource estimate" (BTR.V)
        if (pos is not None and pos > m.end() and re.search(r"(?i)combin\w*\s+with\s+(?:the\s+)?$", lead)
                and re.search(r"(?i)\b(?:these|the)\s+new\b", ctx[m.end():pos])):
            comb_until = m.end() + re.search(r"(?i)\b(?:these|the)\s+new\b", ctx[m.end():pos]).start()
            continue  # 1.0.2: "When combined with previously reported drill results ..., these new copper assays indicate ..." (BFG.CN)
        if (pos is not None and pos > m.end() and re.search(r"(?i)combin\w*\s+with\s+(?:the\s+)?$", lead)
                and re.search(r"(?i)\b(?:to\s+form|composite|for\s+a\s+total|combined)\b", ctx[m.end():pos])):
            continue  # "combining with previously released results to form a composite of 0.93% CuEq over 240 m"
        if (pos is not None and pos > m.end() and re.search(r"(?i)(?:increas\w*|expand\w*|extend\w*|improv\w*|upgrad\w*)\s+(?:the\s+)?(?:size|length|grade|width)?\s*(?:and\s+\w+\s+)?(?:of\s+)?(?:the\s+|a\s+)?$", lead)
                and re.search(r"(?i)\bnew\s+(?:results|assays|drilling|holes?)\b", ctx[m.end():pos])):
            continue  # "Significantly Increasing Size of Previously Announced Interval. New results ... 186 m of 2.13% CuEq"
        return "historical"
    for a, b in skipped:  # the dates of a skipped earlier sub-interval say nothing about the new parent
        ctx = ctx[:a] + " " * (b - a) + ctx[b:]
    if release_date:
        for m in _RE_YEAR_WORK.finditer(ctx):
            y = int(m.group("y") or m.group("y2") or m.group("y3") or m.group("y4"))
            if y in exempt_years:
                continue
            if re.search(r"(?i)\b(?:unreleased|unreported|unpublished|undisclosed|not\s+previously\s+(?:released|reported|disclosed|published))\s+(?:\w+\s+){0,2}$",
                         ctx[max(0, m.start() - 50):m.start()]):
                continue  # 1.0.2: "Reports Unreleased 2019 Drill Results" (USGD.CN): first disclosure of older work is new to the market
            if y < release_date[0] - 1 or (y < release_date[0] and release_date[1] and release_date[1] > 6):
                return "historical"
            if y < release_date[0] and release_date[0] in program_years:
                return "historical"
        if _RE_ANNOUNCED_DATE.search(ctx):
            for d in _RE_DATE.finditer(ctx):
                dd = (int(d.group("y1") or d.group("y2")), _month(d.group("m1") or d.group("m2")),
                      int(d.group("d1") or d.group("d2")))
                if dd < release_date:
                    return "previously_reported"
    if any(not _RE_NAME_AFTER.match(ctx, m.end()) for m in _RE_SURFACE.finditer(ctx)) and not _RE_DRILL_WORD.search(ctx):
        return "surface"
    return None


# ------------------------------------------------------------------ hole ids
# 1.0.4: a wedge or daughter hole ends in letters AND digits -- CPG-112D2, OB-26-387W2, N109-7205A2
_ID_CORE = r"(?:[A-Za-z]{1,8}\d{0,5}|\d{1,4}[A-Za-z]{1,6}\d{0,4}|\d{1,4})(?:[\-_](?:[A-Za-z]{0,10}\d{0,6}[A-Za-z]{0,3}\d{0,3}))+"
_RE_HOLE_KW = re.compile(
    r"(?i:\b(?:drill[\s\-]?holes?|holes?|DDH|boreholes?|drill\s+core\s+holes?)\b)(?:\s*(?:#|No\.?|ID))?\s*[:#]?\s*"
    r"(?P<id>DDH-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*|" + _ID_CORE + r"|[A-Z]{1,6}\d{1,5}[A-Z]?|\d{1,4}[A-Z]{2,6}\d{2,6}[A-Z]?"   # 1.0.8: "hole 25GLR117"
    r"|\d{6,8})(?![A-Za-z0-9\-])")           # 1.0.4: "89.89 g/t Au over 3.0 metres in hole 6702608" (HMMC.TO).
# Six digits at least: "hole 100", "holes 043" and "hole 450m" are a count, a table cell and a depth.
# 1.0.8: an underscore joins the parts as a hyphen does ("ABC18_046"), and a letters-only part may sit between two
# numbered ones ("DD22-ABC-006")
_RE_HOLE_SHAPE = re.compile(
    r"(?<![A-Za-z0-9\-_/.])(?P<id>(?:[A-Z]{1,8}\d{0,5}|\d{1,4}[A-Z]{1,6}\d{0,4})(?:[\-_](?:[A-Z]{2,5}-)?[A-Z]{0,10}\d{1,6}[A-Z]{0,3}\d{0,3}){1,3}"
    r"|[A-Z]{1,6}\d{2,5}-\d{1,4}[A-Z]?\d{0,3})(?![A-Za-z0-9\-_/])")
# 1.0.8: an unhyphenated id that heads its figures ("ABC7795: 15.2 meters at 11.1 g/t", "26AB030: 2.0 metres at
# 44.65 g/t") or is bracketed right after one ("24m @ 0.29% Cu from 0m (AB21RC06)")
_RE_HOLE_HEADING = re.compile(r"(?<![A-Za-z0-9\-_/.])(?P<id>\d{0,2}[A-Z]{2,6}\d{3,6}[A-Z]?\d{0,2})\s*:\s*(?=\d)")
_RE_HOLE_PAREN = re.compile(r"(?i:\d\s*(?:m|metres?|meters?|ft|feet|g/t|gpt|%|ppm|ppb))(?:\s+[\w.]+){0,3}?\s*\(\s*"
                            r"(?P<id>[A-Z]{2,6}\d{2}[A-Z]{1,4}\d{2,4}[A-Z]?|[A-Z]{2,6}\d{3,6}[A-Z]?)\s*\)")
_NOT_HOLE = re.compile(
    r"(?i)^(?:NI-?43-101|43-101|COVID-19|[A-Z]{1,3}\d?O\d?(?:-\d+)?|Q[1-4]-\d+|H[12]-\d+|TSX-?V?|CSE|FSE|OTC\w*"
    r"|Form-\d+|\d{4}-\d{2,4}|Phase-\d+|Figure-\d+|Table-\d+|No-\d+|SEDAR-\d+|Rule-\d+"
    r"|(?:19|20)\d\d)$")


def _hole_ok(h: str, keyword: bool) -> bool:
    if not h or not re.search(r"\d", h) or len(h) > 24:
        return False
    if _NOT_HOLE.match(h):
        return False
    if not keyword:
        # a shape-only id needs a letter and a hyphen-separated number: "PLN25-200", "EB-21-78"
        if not re.search(r"[A-Za-z]", h) or ("-" not in h and "_" not in h):
            return False
        if re.fullmatch(r"(?i)[A-Z]{2}-\d{1,2}", h):
            return False  # "US-93", "PQ-12": a road or a core size; "Hole GR-28" (a keyword id) stays a hole (1.0.8)
    if re.fullmatch(r"\d{1,4}(?:-\d{1,4})+", h) and not keyword:
        return False
    return True


def find_holes(text: str) -> list[dict]:
    """Hole ids with positions. Keyword ids may be digits-only ("hole 43-317")."""
    out, seen = [], set()
    for m in _RE_HOLE_KW.finditer(text):
        h = m.group("id").rstrip("-_")
        if _hole_ok(h, True) and (m.start("id"), h) not in seen:
            seen.add((m.start("id"), h))
            out.append({"id": h, "pos": m.start("id"), "end": m.end("id"), "kw": True})
    kw_pos = {o["pos"] for o in out}
    for m in _RE_HOLE_SHAPE.finditer(text):
        h = m.group("id")
        if m.start("id") in kw_pos or any(o["pos"] <= m.start("id") < o["end"] for o in out):
            continue
        if _hole_ok(h, False):
            out.append({"id": h, "pos": m.start("id"), "end": m.end("id"), "kw": False})
    for rx in (_RE_HOLE_HEADING, _RE_HOLE_PAREN):   # 1.0.8
        for m in rx.finditer(text):
            s0 = m.start("id")
            if not any(o["pos"] <= s0 < o["end"] for o in out) and not _NOT_HOLE.match(m.group("id")):
                out.append({"id": m.group("id"), "pos": s0, "end": m.end("id"), "kw": False})
    # 1.0.4: an id this release has already confirmed counts wherever else it appears. "Best RC drill hole
    # intersections at the BK2 Target: BKR010 3m @ 9.21 g/t Au" -- BKR010 carries no hyphen, so the shape
    # pass will not take it on its own, though the same release names it as a hole further down.
    ids_seen = {o["id"] for o in out}
    # an id that is only the front of a longer one ("AL24" of "AL24-124") is a fragment, not a hole
    known = sorted([k for k in ids_seen
                    if not any(j != k and j.startswith(k) and j[len(k)] in "-_0123456789" for j in ids_seen)],
                   key=len, reverse=True)
    if known:
        out.sort(key=lambda o: o["pos"])
        held = [(o["pos"], o["end"]) for o in out]
        rex = re.compile(r"(?<![A-Za-z0-9\-/.])(?P<id>" + "|".join(re.escape(k) for k in known) +
                         r")(?![A-Za-z0-9\-/])")
        for m in rex.finditer(text):
            s0 = m.start("id")
            if any(a <= s0 < b for a, b in held):
                continue
            out.append({"id": m.group("id"), "pos": s0, "end": m.end("id"), "kw": False, "known": True})
    # 1.0.4: once a release has named two holes of the same unhyphenated shape -- ZND0030 and ZND0034 --
    # the rest of that series is a hole too, however it is written ("ZND0039 returned 623 ft grading 0.23%").
    fams = {}
    for k in ids_seen:
        if "-" in k or "_" in k or not re.fullmatch(r"[A-Za-z]{2,6}\d{2,6}[A-Za-z]{0,2}", k):
            continue
        fams.setdefault(re.sub(r"\d+", lambda d: r"\d{%d}" % len(d.group(0)), k), set()).add(k)
    fams = [f for f, v in fams.items() if len(v) >= 2]
    if fams:
        out.sort(key=lambda o: o["pos"])
        held = [(o["pos"], o["end"]) for o in out]
        rex = re.compile(r"(?<![A-Za-z0-9\-/.])(?P<id>" + "|".join(fams) + r")(?![A-Za-z0-9\-/])")
        for m in rex.finditer(text):
            s0 = m.start("id")
            if any(a <= s0 < b for a, b in held):
                continue
            out.append({"id": m.group("id"), "pos": s0, "end": m.end("id"), "kw": False, "known": True})
    out.sort(key=lambda o: o["pos"])
    return out


def norm_hole(h):
    return re.sub(r"[^A-Z0-9]", "", (h or "").upper())


# ------------------------------------------------------------------ tables
_TABLE_METAL = re.compile(
    r"(?P<metal>(?:\d?PGMs?|\d?PGEs?|3E)\s*\+\s*Au|(?:" + D._METAL_ALT_NEW + r")(?:\s*Eq\.?)?)(?![A-Za-z])"
    r"\s*[\n ]*\(?\s*(?P<unit>g/t|gpt|g/tonne|ppm|ppb|%|oz/t|opt)\s*\)?", re.I)
_TABLE_HEADER = re.compile(r"(?i)\bfrom\b[\s()m\n.]{0,12}\bto\b")
_NUM = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)?(?![\w.%/])")
_ROW_INCL = re.compile(r"(?i)^\s*(?:incl(?:uding|udes|\.)?|inc\.?|and|with|within|or(?=\s+\d))\b")
# 1.0.2: an unhyphenated id opening a table row ("MADN0010 151.61 226 74.39 ...", USGD.CN) that find_holes does not accept in prose
_RE_ROW_HOLE_PLAIN = re.compile(r"^\s*(?P<id>(?-i:[A-Z]{2,6}\d{3,}[A-Z]?))(?=[ \t]+(?:\([^()\n]{0,20}\)[ \t]+)?-?\d)")  # 1.0.8: "ABC127 (60, -58) 224.0 ..."


def _row_holes(line):
    holes = find_holes(line)
    if not holes:
        m = _RE_ROW_HOLE_PLAIN.match(line)
        if m and len(_NUM.findall(line[m.end():])) >= 3:
            holes = [{"id": m.group("id"), "pos": m.start("id"), "end": m.end("id"), "kw": False}]
    return holes


def _tnum(s):
    return float(s.replace(",", "."))


# 1.0.2 (TABLE_COLUMNS_V1): a results table is read column by column. The header after "From" is split into
# column kinds (from, to, length, true width, a metal grade, another number, text), and each row's cells are matched
# to them in order. A dash, "n/a", "pending", "<0.01" ... holds its column's place. 1.0.1 took the last N numbers of a
# row as the N grades, which read a length or a true width as a grade whenever a cell was empty or an extra number
# column followed (SGLD.V 17.19 g/t Au over 17.19 m, ZNG.V 35.2% Cu, NPR.V 140 g/t Au, MUX.TO 140.8 g/t Au).
_HDR_UNIT = r"(?:\s*\(\s*(?P<{0}>m|ft|feet|metres?|meters?|cl|tw)\s*\))*"
_HDR_TOKENS = [
    ("from", re.compile(r"(?i)\bfrom\b[\u00b9\u00b2\u00b3*\d]?(?:\s*\(\s*(?P<u>m|ft|feet|metres?|meters?)\s*\))?")),
    ("to", re.compile(r"(?i)\bto\b[\u00b9\u00b2\u00b3*\d]?(?:\s*\(\s*(?P<u>m|ft|feet|metres?|meters?)\s*\))?")),
    ("tw", re.compile(r"(?i)(?:\b(?:est(?:\.|imated)?|app(?:\.|arent)?|horizontal)\s+)?\b(?:true\s+(?:width|thickness)|etw|t\.?w\.?)"
                      r"(?![A-Za-z])[\w\u00b9\u00b2\u00b3*.]*(?:\s*\(\s*(?:tw|etw)\s*\))?(?:\s*\(\s*(?P<u>m|ft|feet|metres?|meters?)\s*\))?")),
    ("len", re.compile(r"(?i)\b(?:(?:core|drilled|downhole|down[\s-]hole|sample|mineralized|intersected)\s+)?"
                       r"(?:length|interval|intercept|width|thick(?:ness)?|int|intersection|cl)(?![A-Za-z])[\w\u00b9\u00b2\u00b3*.]*"
                       r"(?:\s*\(\s*(?:cl|core\s+length)\s*\))?(?:\s*\(\s*(?P<u>m|ft|feet|metres?|meters?)\s*\))?")),
    ("combo", None),        # "Zn+Pb (%)", "Pt+Pd+Au (g/t)": one column
    ("metal", None),        # _TABLE_METAL (metal + unit)
    ("bare_metal", None),   # a metal name without a unit ("Copper", "Au Eq**"): a number column
    ("num", re.compile(r"(?i)\b(?:g\s*[x\u00d7]\s*m|gxm|gram[\s-]*met(?:re|er)s?|m\s*[x\u00d7]\s*g/t|metal\s+factor|recovery|voids?|silica|sio2"
                       r"|vertical\s+depth|depth|elevation|elevati\s*on|elev|azimuth|azimut\s*h|az|dip|easting|northing|sample\s*(?:id|no\.?|#|number)?"
                       r"|rqd|cut[\s-]*off|cutoff|density|sg|ppm|samples?)\b[\w\u00b9\u00b2\u00b3*.]*(?:\s+(?:tw|cl|etw)\b)?(?:\s*\([^)\n]{0,8}\))?")),
    ("text", re.compile(r"(?i)\b(?:zones?|target(?:/zone)?|position(?:\s+in\s+deposit)?|comments?|rock\s+type|lithology|area|domain|vg|type|drilled\s+vein|vein"
                        r"|notes?|status|collar\s+location|description|host|core|oxides?|trench|showing|structure|remarks?|hole|significance|interpretation)\b[\w\u00b9\u00b2\u00b3*.]*")),
]
# 1.0.5: "Horizon" (Footwall / Hangingwall) is a text column (CADY.TO Table 1)
_HDR_TOKENS[-1] = ("text", re.compile(_HDR_TOKENS[-1][1].pattern.replace("|interpretation)", "|interpretation|horizons?)")))
_HDR_NOISE = re.compile(r"(?i)\b(?:grade|assays?|avg|average|results?|uncut|cut|capped|uncapped|weighted|diluted|undiluted)\b|\(\s*(?:metres?|meters?|feet)\s*\)|\(?\s*(?:m|ft|%|g/t|gpt|ppm|ppb|oz/t|opt|g/tonne)\s*\)?(?![A-Za-z])|[()\[\]*\u00b9\u00b2\u00b3\u2074\u2075#:/|\-\u2013,.;+^~\"'\u201c\u201d\u2019]+|\d{1,2}(?![\d.])")
_TABLE_METAL2 = re.compile(
    r"(?i)(?P<metal>(?:\d?PGMs?|\d?PGEs?|3E)\s*\+\s*Au|(?:" + D._METAL_ALT_NEW + r")(?![A-Za-z])(?:\s*Eq\.?)?)[\d\u00b9\u00b2\u00b3*]{0,3}"
    r"\s*[\n ]*\(?\s*(?P<unit>g/t|gpt|g/tonne|ppm|ppb|%|oz/ton|oz/t|opt)\s*\)?")
_TABLE_COMBO = re.compile(r"(?i)(?P<metals>(?:" + D._METAL_ALT_NEW + r")(?![A-Za-z])(?:\s*\+\s*(?:" + D._METAL_ALT_NEW + r")(?![A-Za-z]))+)"
                          r"\s*\(?\s*(?P<unit>g/t|gpt|g/tonne|ppm|ppb|%|oz/t|opt)\s*\)?")
_GRADE_UNIT = re.compile(r"(?i)^\(?\s*(%|g/t|gpt|g/tonne|ppm|ppb|oz/t|opt)\s*\)?$")
_PLACEHOLDER = re.compile(r"(?i)^(?:[-\u2013\u2014]+|n/?a|nsv|nss|ns|nsi|bdl|b\.d\.l\.?|<\s*d\.?l\.?|pending|tbd|nil|trace|tr|na|nr|n\.?s\.?|x|\*+|<[\d.,]+"
                          r"|unknown|undetermined|n\.?d\.?|ap)$")  # 1.0.2: "unknown" true width (NEXM.V), "Ap" assays pending
_CELL_NUM = re.compile(r"^[*~]?(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:[.,]\d+)?)\*{0,3}$")


def _cell_value(tok):
    """A table cell: float, None for a placeholder, or False for text."""
    if _PLACEHOLDER.match(tok):
        return None
    m = _CELL_NUM.match(tok)
    if not m:
        return False
    s_ = m.group(1)
    if re.match(r"^[1-9],[1-9]$", s_):
        return False  # 1.0.2: footnote marks "1,6" in a column of their own (CVV.V), not a decimal comma
    if re.match(r"^-?[1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?$", s_):  # 1.0.2: "0,106" is a decimal comma, never thousands (BGF.V)
        s_ = s_.replace(",", "")
    else:
        s_ = s_.replace(",", ".")
    try:
        return float(s_)
    except ValueError:
        return False


def _unit_m(u):
    return 0.3048 if (u or "").lower() in ("ft", "feet") else 1.0


def header_columns(seg: str):
    """Column kinds from the header text starting at "From": [(kind, metal, unit, len_unit)], or None when a label
    is not understood (then the 1.0.1 reading is used)."""
    m0 = re.search(r"(?i)\bfrom\b", seg)
    if not m0:
        return None
    s_ = seg[m0.start():]
    # qualifiers of the column before: "(cut to 90 g/t)", "(uncapped)", "(CL)", "(TW)"
    s_ = re.sub(r"(?i)\(\s*(?:cut|capped|uncut|uncapped|cl|tw|core\s+length|true\s+width|not\s+true)[^()]{0,30}\)", " ", s_)
    # 1.0.2: a label split over two header lines ("Est. True | ... | Width (m)", IPT.V): join it before reading
    mt = re.search(r"(?i)\b(?:est(?:\.|imated)?\s+)?true\b(?!\s+(?:width|thickness))", s_)
    if mt:
        mw = re.search(r"(?i)(?<!true\s)\b(width|thickness)\b", s_[mt.end():])
        if mw:
            w0 = mt.end() + mw.start()
            s_ = s_[:mt.end()] + " " + mw.group(1) + s_[mt.end():w0] + s_[w0 + len(mw.group(1)):]
    cols, i, residue, bare = [], 0, [], []
    while i < len(s_):
        if s_[i].isspace():
            i += 1
            continue
        hit = None
        for kind, rx in _HDR_TOKENS:
            if kind == "combo":
                mm = _TABLE_COMBO.match(s_, i)
                if mm:
                    unit = "g/t" if mm.group("unit").lower() in ("gpt", "g/tonne") else mm.group("unit").lower()
                    hit = (mm.end(), ("metal", "+".join(D._normalize_metal(x) for x in re.split(r"\s*\+\s*", mm.group("metals"))), unit, None))
            elif kind == "metal":
                mm = _TABLE_METAL2.match(s_, i)
                if mm and not (i > 0 and s_[i - 1].isalpha()):
                    unit = "g/t" if mm.group("unit").lower() in ("gpt", "g/tonne") else mm.group("unit").lower()
                    unit = "oz/t" if unit == "oz/ton" else unit
                    hit = (mm.end(), (kind, D._normalize_metal(re.sub(r"\s+", "", mm.group("metal"))), unit, None))
            elif kind == "bare_metal":
                mm = re.compile(r"(?i)(?:" + D._METAL_ALT_NEW + r")(?![A-Za-z])(?:\s*eq\.?)?[\d\u00b9\u00b2\u00b3*]*").match(s_, i)
                if mm and mm.group(0).lower() != "cut" and not (i > 0 and s_[i - 1].isalpha()) \
                        and not (mm.end() < len(s_) and s_[mm.end()].isalpha()):
                    raw = re.sub(r"[\s\u00b9\u00b2\u00b3*]+", "", mm.group(0)).rstrip(".")
                    if not re.fullmatch(r"(?i)(?:" + D._METAL_ALT_NEW + r")(?:eq\.?)?", raw):
                        raw = re.sub(r"\d+$", "", raw)  # a footnote number after the name ("Au2"); a formula ("U3O8", 1.0.2 CVV.V) is kept
                    hit = (mm.end(), ("bare_metal", D._normalize_metal(raw.replace(".", "")), None, None))
            else:
                mm = rx.match(s_, i)
                if mm and mm.end() > i:
                    u = mm.groupdict().get("u")
                    hit = (mm.end(), (kind, None, None, u))
            if hit:
                break
        if hit:
            i, col = hit
            if col[0] == "text" and cols and cols[-1][0] == "text":
                continue
            if col[0] == "metal" and cols and cols[-1][0] == "bare_metal" and cols[-1][1] == col[1]:
                cols[-1] = col  # "Gold (m) (m) (m) Au g/t": one column, named twice
                continue
            cols.append(col)
            continue
        nm = _HDR_NOISE.match(s_, i)
        if nm and nm.end() > i:
            unit_tok = _GRADE_UNIT.match(nm.group(0).strip())
            if unit_tok:
                bare.append(unit_tok.group(1).lower())
            i = nm.end()
            continue
        wm = re.match(r"\S+", s_[i:])
        residue.append(wm.group(0))
        i += wm.end()
    if residue:
        return None
    # "Copper Silver Copper Eq. ... m m m % gpt %": units on their own line, in column order
    bares = [k for k, c in enumerate(cols) if c[0] == "bare_metal"]
    if bares and not any(c[0] == "metal" for c in cols) and len(bare) >= len(bares):
        for k, u in zip(bares, bare[-len(bares):]):
            cols[k] = ("metal", cols[k][1], "g/t" if u in ("gpt", "g/tonne") else u, None)
    kinds = [c[0] for c in cols]
    if kinds[:1] != ["from"] or "to" not in kinds[:3] or not any(k == "metal" for k in kinds):
        return None
    return cols


def row_by_columns(cells, cols, prefix_nums=0):
    """Match one row's cells (floats, None placeholders) to the header columns. Returns (from_m, to_m, length_m,
    [(metal, unit, grade)]) or None when the row does not fit the header."""
    kinds = [c[0] for c in cols]
    # numeric kinds in order; a text column ends the part of the row that can be matched without counting
    firstt = kinds.index("text") if "text" in kinds else len(kinds)
    strict = [c for c in cols[:firstt]]
    after = [c for c in cols[firstt:] if c[0] != "text"]
    # number columns after the last grade (true width, recovery, voids) may be left empty in a row
    lastm = max((k for k, c in enumerate(strict) if c[0] == "metal"), default=-1)
    optional_tail = [c for c in strict[lastm + 1:]] if lastm >= 0 else []
    if optional_tail and all(c[0] in ("tw", "num", "len", "bare_metal") for c in optional_tail):
        need_n = lastm + 1
    else:
        need_n = len(strict)
    vals = [c for c in cells if c is not False]
    starts = [prefix_nums, 0] + list(range(len(vals)))
    tried = set()
    for st in starts:
        if st in tried or st < 0 or st + need_n > len(vals):
            continue
        tried.add(st)
        seg = vals[st:st + len(strict)]
        seg = seg + [None] * (len(strict) - len(seg))
        got = dict(zip(range(len(strict)), seg))
        d_ = {}
        ok = True
        for k, c in enumerate(strict):
            d_.setdefault(c[0], []).append((c, got[k]))
        fr_c, to_c = d_["from"][0], d_.get("to", [(None, None)])[0]
        fr, to = fr_c[1], to_c[1]
        if fr is None or to is None or to <= fr or fr < 0:
            continue  # 1.0.2: a negative "from" is a dip column (SIG.V "-65 193.0 263.7" read as 70.7% WO3)
        fu, tu = _unit_m(fr_c[0][3]), _unit_m(to_c[0][3])
        if d_.get("len") and all(v is None for c, v in d_["len"]):
            continue  # 1.0.2: the length cell is not there, so this alignment is a guess (CRTL.CN "Composite 15.3 1.76 - -")
        lens = [(c, v) for c, v in d_.get("len", []) if v is not None]
        if lens:
            lc, lv = lens[0]
            lu = _unit_m(lc[3]) if lc[3] else fu
            if abs((to - fr) * fu - lv * lu) > (max(0.15, 0.006 * lv * lu) if fu == lu else max(0.15, 0.03 * lv * lu) * 1.02):  # 1.0.2: tight, a grade read as "from" slips through 3% (CRTL.CN)
                # a second from/to pair in the other unit ("From (ft) To (ft) From (m) To (m)")
                if not (len(d_["from"]) > 1 and any(abs((d_["to"][1][1] - d_["from"][1][1]) * _unit_m(d_["from"][1][0][3]) - v * _unit_m(c[3] or d_["from"][1][0][3])) <= max(0.15, 0.03 * v)
                                                     for c, v in lens if len(d_.get("to", [])) > 1 and d_["to"][1][1] is not None and d_["from"][1][1] is not None)):
                    continue
        # metres: prefer a metre pair and a metre length
        pairs = list(zip(d_["from"], d_.get("to", [])))
        mpair = next(((a, b) for a, b in pairs if _unit_m(a[0][3]) == 1.0 and a[1] is not None and b[1] is not None), pairs[0])
        fr_m, to_m = mpair[0][1] * _unit_m(mpair[0][0][3]), mpair[1][1] * _unit_m(mpair[1][0][3])
        mlen = next((v * _unit_m(c[3] or mpair[0][0][3]) for c, v in lens if _unit_m(c[3] or mpair[0][0][3]) == 1.0), None)
        length = round(mlen if mlen is not None else to_m - fr_m, 3)
        grades = [(c[1], c[2], v) for c, v in zip(strict, seg) if c[0] == "metal"]
        rest = vals[st + len(strict):] if st + len(strict) <= len(vals) else []
        if after and len(rest) == len(after):
            grades += [(c[1], c[2], v) for c, v in zip(after, rest) if c[0] == "metal"]
        if ok and grades:
            tws = [v * _unit_m(c[3] or mpair[0][0][3]) for c, v in d_.get("tw", []) if v is not None]
            return round(fr_m, 3), round(to_m, 3), length, grades, (round(tws[0], 3) if tws else None)  # 1.0.5: true width
    return None



# 1.0.2 (TABLE_STREAM_V1): tables whose cells are not laid out one row per line: one cell per line with blank lines
# between (GRAY.CN J-9-21 52.09 g/t, IPT.V Z26-09 1,333 g/t Ag, ZNG.V), or the whole table flattened into one line
# (COS.V CS-21-73W3 13,620 g/t Ag). The cells are read as one stream; a hole id or a row label ("including", "And")
# starts a new row. Used only for a header that produced no row the line-by-line way.
_ROW_LABEL = re.compile(r"(?i)^(?:incl(?:uding|\.)?|inc\.?|and|a|nd|within|plus|or)$")


def _is_hole_token(tok):
    tok = tok.strip(",;:*")
    if not re.search(r"\d", tok) or not re.search(r"[A-Za-z]", tok):
        return False
    hs = find_holes(tok)
    return bool(hs and hs[0]["id"] == tok) or bool(re.match(r"^(?-i:[A-Z]{1,8})[\-_]?\d[\w\-]*$", tok) and "-" in tok)


def stream_table(t, hm, release_date, exempt_years=()):
    hline = t.rfind("\n", 0, hm.start()) + 1
    pre_line = t[hline:hm.start()]
    se = max([m.end() for m in re.finditer(r"[.;!?]\s|[:\u2013\u2014-]\s", pre_line)] + [0])
    seg_start = hline + se
    # the table's caption: up to three short lines right above the header; a line of prose ends it (1.0.2: GQC.V
    # "... the previously identified 7.5 km corridor." above "Table 1: Results from hole TIR-26-62")
    title, taken = pre_line[se:], (3 if se else 0)  # a table flattened into a prose line: its caption is on that line
    for ln in reversed(t[max(0, hline - 600):hline].split("\n")):
        ln = ln.strip()
        if not ln:
            continue
        if taken >= 3 or not (re.match(r"(?i)table\b", ln) or len(ln) <= 60) or (len(ln) > 60 and ln.endswith(".")):
            break
        title, taken = ln + " " + title, taken + 1
    toks = [(m.group(0), seg_start + m.start()) for m in re.finditer(r"\S+", t[seg_start:seg_start + 6000])]
    k0 = next((i for i, (tok, p) in enumerate(toks) if p >= hm.start()), None)
    if k0 is None:
        return []
    # header: labels from "From" until the first hole id, or the first number that starts a run of numbers
    head, i = [tok for tok, _ in toks[:k0] if not re.match(r"^\d$", tok)][-6:], k0
    foot = False
    while i < len(toks):
        tok = toks[i][0]
        nxt = toks[i + 1][0] if i + 1 < len(toks) else ""
        if _is_hole_token(tok):
            break
        v = _cell_value(tok)
        if isinstance(v, float):
            if re.match(r"^\d$", tok) and (_cell_value(nxt) is False and not _is_hole_token(nxt) or _is_hole_token(nxt)):
                i += 1
                foot = True
                continue  # a footnote mark in the header ("Width (m) 1 Au (g/t) 2")
            break
        head.append(tok)
        i += 1
        if len(head) > 60:
            return []
    kcols = header_columns(" ".join(head))
    if not kcols:
        return []
    out, hole, labels, vals, vpos, group, texts = [], None, [], [], None, 0, 0
    # 1.0.2: a text column between the numbers ("From | To | Type | Interval | AgEq ...", GRSL.V): the cells before it
    # wait for the rest of the row, and a row's cells end after the last numeric column
    kinds_ = [c[0] for c in kcols]
    n_before = kinds_.index("text") if "text" in kinds_ else None
    n_row = len([k for k in kinds_ if k != "text"]) if n_before is not None else None

    def flush(keep_rest=False):
        nonlocal labels, vals, vpos
        carry = []
        if n_row and len(vals) > n_row:
            vals, carry = vals[:n_row], (vals[n_row:] if keep_rest else [])
        if len(vals) >= 3:
            mapped = row_by_columns(vals, kcols, 0)
            if mapped:
                fr, to, length, grades, tw = mapped
                incl = bool(re.search(r"(?i)^(?:incl|inc\.?|and|within|plus|or)", "".join(labels))
                            or (n_before is not None and any(_ROW_LABEL.match(x) for x in labels[1:])))  # 1.0.5: "Footwall | Incl." (CADY.TO)
                seen = set()
                for metal, unit, g in grades:
                    if metal in seen or g is None or g <= 0 or not (0.1 <= length <= 2000) or not D._plausible(g, unit, metal, True):
                        continue
                    seen.add(metal)
                    out.append({"length_m": length, "grade": g, "unit": unit, "metal": metal, "pos": vpos, "from_m": fr, "to_m": to, "tw_m": tw,
                                "hole": hole, "hole_how": "table" if hole else None, "including": incl, "src": "table", "_group": group, "reason": None,
                                "reason_src": None, "rule": None})
        labels, vals, vpos = [], carry, (vpos if carry else None)

    prev_v = False
    while i < len(toks):
        tok, p = toks[i]
        i += 1
        v = _cell_value(tok)
        if foot and re.match(r"^\d$", tok) and not isinstance(prev_v, float):
            continue  # 1.0.2: a footnote mark after a text or pending cell ("Ap 4", "Lower Zone 3 1.95", NEXM.V)
        prev_v = v
        if _is_hole_token(tok):
            flush()
            hole, group, texts = tok.strip(",;:*"), group + 1, 0
            continue
        if v is False:
            if vals and not (n_before is not None and len(vals) <= n_before):
                flush(True)
            labels.append(tok)
            texts += 1
            if texts >= 6 or re.match(r"(?i)^(?:table|figure|notes?|source)\b", tok):
                break  # prose or the next caption: the table has ended
            continue
        texts = 0
        if vpos is None:
            vpos = p
        vals.append(v)
    flush()
    reason = context_reason(title, release_date, exempt_years=exempt_years)
    for x in out:
        if reason in ("historical", "previously_reported", "surface"):
            x["reason"], x["reason_src"], x["rule"] = reason, "title", "table_title"
        if release_date and not x["reason"] and _old_hole(x.get("hole"), release_date):
            x["reason"], x["rule"] = "historical", "table_hole_year"
    return out


_RE_TITLE_HOLE_RANGE = re.compile(r"(?i)\bholes?\s+[A-Z]{0,6}-?(?P<lo>\d{2,4})\s*(?:-|\u2013|to|through)\s*[A-Z]{0,6}-?(?P<hi>\d{2,4})\s+(?:were\s+|are\s+)?previously\s+(?:reported|released|announced|disclosed)")


def find_tables(t: str, release_date, spans=None, exempt_years=(), header_before=None) -> list[dict]:
    """Intervals from 'Hole | From | To | Length | grades' tables in plain text."""
    out = []
    for hm in _TABLE_HEADER.finditer(t):
        if header_before is not None and hm.start() >= header_before:
            break
        hstart = max(0, t.rfind("\n", 0, max(0, hm.start() - 120)) + 1)
        # header runs until the first line that starts with a hole id or a number row
        lines_start = hm.end()
        body_iter = list(re.finditer(r"[^\n]*\n?", t[lines_start:lines_start + 6000]))
        header_text = t[hstart:lines_start]
        first_row = None
        cur = lines_start
        for lm in body_iter:
            line = lm.group(0)
            if not line:
                break
            nums = _NUM.findall(line)
            if len(nums) >= 3 and (_row_holes(line) or _ROW_INCL.match(line) or re.match(r"^\s*[\d.]", line)):
                first_row = cur
                break
            header_text += line
            cur += len(line)
            if len(header_text) > 900:
                break
        if first_row is None:
            out.extend(stream_table(t, hm, release_date, exempt_years))
            continue
        cols = [(D._normalize_metal(re.sub(r"\s+", "", c.group("metal"))),
                 "g/t" if c.group("unit").lower() in ("gpt", "g/tonne") else c.group("unit").lower())
                for c in _TABLE_METAL.finditer(header_text[hm.start() - hstart:])
                if not (c.group("metal").lower() == "pt" and header_text[hm.start() - hstart:][max(0, c.start() - 1):c.start()].lower() == "g")]
        if not cols:
            out.extend(stream_table(t, hm, release_date, exempt_years))
            continue
        # 1.0.2 column model; a header whose labels are not all understood keeps the 1.0.1 reading
        hline0 = t.rfind("\n", 0, hm.start()) + 1
        hseg = header_text[max(0, hline0 - hstart):] if hline0 >= hstart else header_text[hm.start() - hstart:]
        if re.search(r"(?i)\bfrom\b", t[hline0:hm.start()]) is None:
            hseg = header_text[hm.start() - hstart:]
        hlines = hseg.split("\n")
        for k in range(len(hlines) - 1, 0, -1):
            if len(_NUM.findall(hlines[k])) >= 3 and not re.search(r"(?i)\bfrom\b", hlines[k]):
                hseg = "\n".join(hlines[k + 1:])  # a row swallowed into the header: a repeated header follows it
                break
        hl_ = hseg.split("\n")
        for k in range(1, len(hl_)):
            if find_holes(hl_[k]) and hl_[k].strip()[:1].isalnum() and not re.search(r"(?i)\bfrom\b", hl_[k]):
                hseg = "\n".join(hl_[:k])  # a hole id line ends the header ("LHCC-25-033" then "- - - NSV")
                break
        hseg = re.sub(r"(?:\n[ \t]*[A-Z]{2,6}[ \t]*)+\n?[ \t]*$", "\n", hseg)  # "SAL" of a hole id "SAL 01-25" split over two lines
        kcols = header_columns(hseg)
        prefix = 0
        if kcols:
            pre_hdr = header_text[:hm.start() - hstart][-200:].split("\n")[-3:]
            prefix = sum(1 for tm in re.finditer(r"(?i)\b(?:easting|northing|elevati\s*on|elevation|elev|azimut\s*h|azimuth|dip|depth|east|north|utm\s*[ex]|utm\s*[ny]|x|y|z)\b", " ".join(pre_hdr)))
        dual_units = bool(re.search(r"(?i)\(\s*(?:ft|feet)\s*\)", header_text) and re.search(r"(?i)\(\s*m\s*\)", header_text))
        has_len = bool(re.search(r"(?i)\b(?:length|interval|width|meters|metres|thickness|core|intercept|int)\b", header_text))
        # the table's own title: up to three lines right above the header line that are a "Table ..." caption
        # or short; a line of prose ends the title (prose above a table is about something else)
        hline = t.rfind("\n", 0, hm.start()) + 1
        pre, taken, cur_end = "", 0, hline
        while taken < 3 and cur_end > 0:
            ls = t.rfind("\n", 0, max(0, cur_end - 1)) + 1
            line = t[ls:cur_end].strip()
            cur_end = ls
            if not line:
                if ls == 0:
                    break
                continue
            if not (re.match(r"(?i)table\b", line) or len(line) <= 60):
                break
            pre = line + " " + pre
            taken += 1
        pre_reason = context_reason(pre, release_date, exempt_years=exempt_years)
        if pre_reason is None and _RE_SURFACE.search(header_text + pre[-200:]) and not _RE_DRILL_WORD.search(header_text + pre[-200:]):
            pre_reason = "surface"
        first_out = len(out)
        tried_columns = bool(kcols)
        # 1.0.8: a table of one hole's intervals names it above the header ("Drillhole ABCD0015 From (m) To (m) ...")
        cap = [h for h in find_holes(pre + " " + header_text) if h["kw"]]
        cap_hole = cap[0]["id"] if len({h["id"] for h in cap}) == 1 else None
        for kcols in ([kcols, None] if kcols else [None]):  # 1.0.2: a column model that reads no row falls back to 1.0.1 (NGEX.TO)
            hole = cap_hole
            pos = first_row
            rows = 0
            row_reason = None
            group, group_years = 0, {}
            for line in t[first_row:first_row + 8000].split("\n"):
                lpos = pos
                pos += len(line) + 1
                if not line.strip():
                    continue
                if rows and not _NUM.search(line) and len(line.strip()) <= 120:
                    sub = context_reason(line, release_date, exempt_years=exempt_years)  # "Previously released on October 31, 2024" inside a table
                    row_reason = sub if sub in ("historical", "previously_reported", "surface") else None
                holes = [h for h in _row_holes(line) if h["pos"] < 12 or line[:h["pos"]].strip() == ""]
                if holes or (_RE_TABLE_HOLE_START.match(line) and not _ROW_INCL.match(line)):
                    group += 1
                for ym in _RE_TABLE_DRILLED_YEAR.finditer(line):  # "Drilled 2022 (Rugby Resources)" in a comments column
                    group_years.setdefault(group, []).append(int(ym.group(1)))
                nums_m = [n for n in _NUM.finditer(line)]
                if holes:
                    hole = holes[0]["id"]
                    nums_m = [n for n in nums_m if n.start() >= holes[0]["end"]]
                nums = [n.group(0) for n in nums_m]
                if kcols:
                    rest_line = line[holes[0]["end"]:] if holes else line
                    rest_line = re.sub(r"(?i)\bnotes?\s*\d+\)?|\(\d\)", " ", rest_line)
                    rest_line = re.sub(r"<\s+(?=\d)", "<", rest_line)
                    cells = [_cell_value(tok) for tok in rest_line.split()]
                    incl_k = bool(_ROW_INCL.match(line)) or bool(re.search(r"(?i)\binc(?:l|luding)?\.?\b", line[:40]))
                    if sum(1 for c in cells if isinstance(c, float)) < 3:
                        if rows and not holes and len(nums) < 2 and len(line.strip()) > 40:
                            break  # prose after the table
                        continue
                    mapped = row_by_columns(cells, kcols, prefix)
                    if mapped is None:
                        continue
                    fr, to, length, kgrades, tw = mapped
                    if kcols[0][3] is None and re.search(r"\d['\u2019](?:\s|$)", line):
                        fr, to, length = round(fr * 0.3048, 3), round(to * 0.3048, 3), round(length * 0.3048, 3)  # 1.0.2: "BHE26-01_154-158'" rows in feet (BNKR.TO)
                    if not (0.1 <= length <= 2000) or to <= fr:
                        continue
                    rows += 1
                    seen_metals = set()
                    for metal, unit, g in kgrades:
                        if metal in seen_metals:
                            continue  # "Au g/t | Au g/t (cut)": the first is the uncut grade
                        seen_metals.add(metal)
                        if g is None or g <= 0 or not D._plausible(g, unit, metal, True):
                            continue
                        out.append({"length_m": length, "grade": g, "unit": unit, "metal": metal, "pos": lpos,
                                    "from_m": fr, "to_m": to, "tw_m": tw, "hole": hole, "hole_how": "table" if hole else None, "including": incl_k, "src": "table", "_group": group,
                                    "reason": pre_reason or row_reason, "reason_src": "title" if pre_reason else None,
                                    "rule": "table_title" if pre_reason else ("table_row" if row_reason else None)})
                    continue
                if kcols is None and tried_columns and len(re.findall(r"[A-Za-z]{3,}", line)) > 5:
                    continue  # 1.0.2: after the column model read nothing, a prose line is not a row (TGOL.V "Holes TM26-193 and 194 targeted ...")
                incl = bool(_ROW_INCL.match(line)) or bool(re.search(r"(?i)\binc(?:l|luding)?\.?\b", line[:40]))
                need = (3 if has_len else 2) + len(cols)
                if len(nums) < need:
                    if rows and not holes and len(nums) < 2 and len(line.strip()) > 40:
                        break  # prose after the table
                    continue
                try:
                    vals = [_tnum(x) for x in nums]
                except ValueError:
                    continue
                # From/To/Length are the first numbers that satisfy to - from ~= length; grades are the last len(cols)
                fr, to = vals[0], vals[1]
                trip = 0
                length = vals[2] if has_len else round(to - fr, 3)
                if has_len and abs((to - fr) - length) > max(0.15, 0.03 * max(length, 0.01)):
                    # a coordinate or azimuth column may come first: search for a consistent triple
                    ok = False
                    for i in range(0, len(vals) - 2 - len(cols) + 1):
                        a, b, c = vals[i], vals[i + 1], vals[i + 2]
                        if b > a and abs((b - a) - c) <= max(0.15, 0.03 * c):
                            fr, to, length, ok, trip = a, b, c, True, i
                            break
                    if not ok:
                        continue
                if len(nums) - (3 if has_len else 2) != len(cols) and len(vals) < len(cols):
                    continue
                rest = vals[trip + (3 if has_len else 2):]
                if not has_len and rest and abs(rest[0] - (to - fr)) <= max(0.15, 0.03 * max(to - fr, 0.01)):
                    rest = rest[1:]  # an unlabelled length column
                if len(rest) > len(cols) and not re.search(r"(?i)\btrue\b|\best\w*\.?\s+(?:true\s+)?width", header_text):
                    grades = rest[:len(cols)]
                else:
                    grades = vals[-len(cols):]
                if dual_units:
                    trips = [i for i in range(0, len(vals) - 2 - len(cols) + 1)
                             if vals[i + 1] > vals[i] and abs((vals[i + 1] - vals[i]) - vals[i + 2]) <= max(0.15, 0.03 * vals[i + 2])]
                    if len(trips) >= 2:
                        i = trips[-1] if trips[-1] >= trips[0] + 3 else trips[0]
                        fr, to, length = vals[i], vals[i + 1], vals[i + 2]
                        grades = vals[i + 3:i + 3 + len(cols)]
                if not (0.1 <= length <= 2000) or to <= fr:
                    continue
                rows += 1
                for (metal, unit), g in zip(cols, grades):
                    if g is None or g <= 0 or not D._plausible(g, unit, metal, True):
                        continue
                    out.append({"length_m": length, "grade": g, "unit": unit, "metal": metal, "pos": lpos,
                                "from_m": fr, "to_m": to, "hole": hole, "hole_how": "table" if hole else None, "including": incl, "src": "table", "_group": group,
                                "reason": pre_reason or row_reason, "reason_src": "title" if pre_reason else None,
                                "rule": "table_title" if pre_reason else ("table_row" if row_reason else None)})
            if rows:
                break
            del out[first_out:]
        if len(out) == first_out:
            out.extend(stream_table(t, hm, release_date, exempt_years))
        rng = _RE_TITLE_HOLE_RANGE.search(pre)
        if rng:  # 1.0.2: "Drill Holes SG016-SG029 (Holes SG016-SG022 Previously Reported)" (FAS.V): only that range is old
            lo, hi = int(rng.group("lo")), int(rng.group("hi"))
            for x in out[first_out:]:
                hm_ = re.search(r"(\d+)\D*$", x.get("hole") or "")
                if x.get("reason_src") == "title" and hm_ and not (lo <= int(hm_.group(1)) <= hi):
                    x["reason"], x["reason_src"], x["rule"] = None, None, None
        if release_date:
            for x in out[first_out:]:
                if not x["reason"] and _old_hole(x.get("hole"), release_date):
                    x["reason"], x["rule"] = "historical", "table_hole_year"  # AL19-020 in a 2025 table
                ys = group_years.get(x["_group"])
                if ys and max(ys) <= release_date[0] - 2 and not x["reason"]:
                    x["reason"], x["rule"] = "historical", "table_drilled_year"
    for x in out:
        x.pop("_group", None)
    return out


# ------------------------------------------------------------------ project names
_PTOK = r"(?:[A-Z][\w'\u2019\-]*(?:/[A-Z][\w'\u2019\-]*)?)"   # 1.0.8: accented letters belong to the name ("Lac T\u00eate", "Rivi\u00e8re")
_COMMODITY = (r"gold|silver|copper|nickel|zinc|lead|lithium|uranium|antimony|polymetallic|palladium|platinum|pgm"
              r"|graphite|potash|tungsten|cobalt|vanadium|tin|molybdenum|rare[\s\-]earths?|base[\s\-]metals?"
              r"|critical[\s\-]minerals?|copper[\s\-]gold|gold[\s\-]silver|silver[\s\-]gold|gold[\s\-]copper")
_RE_PROJECT = re.compile(
    r"(?P<name>(?:" + _PTOK + r"[ \t]+|" + _PTOK + r"[ \t]*\n[ \t]*){0,3}" + _PTOK + r")"
    r"(?:[ \t]+(?i:" + _COMMODITY + r"))?[ \t\n]+"
    r"(?P<suffix>(?i:project|property|deposit|mine[ \t]+complex|mining[ \t]+complex|mine|complex|claims"
    r"|camp|district|zone|trend|target|prospect|showing|vein|discovery))\b")
# 1.0.3: a deposit sits inside a property, so "Big Missouri deposit" loses to "Premier Gold Project"
_SUFFIX_RANK = {"project": 1, "property": 1, "mine complex": 1, "mining complex": 1, "mine": 1,
                "complex": 1, "claims": 1, "deposit": 2, "camp": 2, "district": 2, "zone": 3, "trend": 3,
                "target": 3, "prospect": 3, "showing": 3, "vein": 3, "discovery": 3}
_NAME_BREAK = D._PROJECT_STOP_NEW | {
    "provides", "announces", "reports", "releases", "commences", "completes", "receives", "expands", "extends",
    "confirms", "discovers", "returns", "hits", "encounters", "identifies", "samples", "updates", "continues",
    "begins", "starts", "launches", "intersects", "drills", "defines", "delivers", "outlines", "highlights",
    "in", "near", "and", "with", "for", "to", "by", "a", "an", "our", "company's", "company\u2019s", "flagship",
    "wholly-owned", "100%-owned", "owned", "optioned", "adjacent", "along", "within", "across", "from", "on",
    "under", "below", "beneath", "its", "the", "this", "that", "these",
    "canada", "nevada", "quebec", "ontario", "yukon", "mexico", "peru", "chile", "b.c.", "bc", "usa",
}
_NAME_BARE = D._PROJECT_BARE_WORDS | {"mine", "project", "property", "deposit", "zone", "camp", "district",
                                       # 1.0.8: a descriptor or a direction alone is not a name ("Historical Resource",
                                       # "VMS Deposit", "SW Zone")
                                       "historical", "historic", "vms", "sw", "se", "nw", "ne"}
_NAME_DESCRIPTOR = {"historical", "historic", "major", "gold-rich", "copper-rich", "silver-rich", "high-grade", "new"}


def _clean_name(raw: str):
    name = re.sub(r"\s+", " ", raw).strip(" ,;.")
    name = re.split(r"\S+['\u2019]s\s+", name)[-1]
    toks = name.split(" ")
    # keep the tokens after the last word that cannot be part of a name
    cut = 0
    for i, tok in enumerate(toks):
        if tok.lower().strip(".,;") in _NAME_BREAK:
            cut = i + 1
    toks = toks[cut:]
    if not toks:
        return None
    if all(t.isupper() or not t.isalpha() for t in toks) and any(len(t) > 3 and t.isalpha() for t in toks):
        toks = [t.title() if t.isalpha() else t for t in toks]
    # 1.0.2: descriptors are not part of a name ("Nisk Ni-Cu-Pd", "B26 Polymetallic", "Advanced N2 Gold")
    while len(toks) > 1 and (re.match(r"^(?:[A-Z][a-z]?(?:-[A-Z][a-z]?)+|polymetallic|poly-metallic|vms)$", toks[-1], re.I)
                             and not toks[-1].isupper() or re.match(r"^[A-Z][a-z]?(?:-[A-Z][a-z]?)+$", toks[-1])):
        toks = toks[:-1]
    while len(toks) > 1 and toks[0].lower() in ("advanced", "flagship", "high-grade", "tier-1", "tier-one", "world-class", "district-scale"):
        toks = toks[1:]
    if all(x.lower() in _NAME_DESCRIPTOR for x in toks):
        return None   # 1.0.8: "Gold-Rich Major (Copper Discovery)" describes, it does not name
    name = " ".join(toks)
    low = [t.lower() for t in toks]
    if len(low) == 1 and low[0] in _NAME_BARE:
        return None
    # 1.0.2: not names at all: a map datum ("WGS84"), a study level ("PFS-level"), "Tier-1", a metal ("Ni"), a hole id
    # ("MV21-006", "CD-852's")
    if (re.match(r"(?i)^(?:wgs|nad)\s*-?\d|^utm\b|^zone\s+\d", name)
            or re.search(r"(?i)-level$|^tier[\s-]?(?:1|one)$|^(?:pfs|pea|dfs|fs|mre|ni\s*43-101)$", name)
            or (len(toks) == 1 and re.match(r"^(?:[A-Z][a-z]?|PGMs?|PGEs?|REEs?|TREO)$", name) and name.lower() not in ("w", "b"))
            or re.search(r"['\u2019]s$", name)
            or re.match(r"^[A-Z]{1,6}-?\d{2}-\d{2,4}[A-Z]?$", name)):
        return None
    if not (1 <= len(toks) <= 5) or not (2 <= len(name) <= 60):
        return None
    return name


def find_project(headline: str, text: str):
    """(name, rank) chosen by suffix rank, then headline mention, then frequency, then position."""
    cands = []
    for src, s in (("h", headline or ""), ("b", text or "")):
        for m in _RE_PROJECT.finditer(s):
            name = _clean_name(m.group("name"))
            if not name:
                continue
            suf = re.sub(r"\s+", " ", m.group("suffix").lower())
            cands.append({"name": name, "rank": _SUFFIX_RANK.get(suf, 3), "src": src, "pos": m.start()})
    if not cands:
        return None, None
    hl = (headline or "").lower()
    whole = ((headline or "") + " " + (text or "")).lower()

    def key(c):
        low = c["name"].lower()
        return (c["rank"], 0 if low in hl else 1, -whole.count(low), 0 if c["src"] == "h" else 1, c["pos"])
    best = min(cands, key=key)
    return best["name"], best["rank"]


# ------------------------------------------------------------------ 1.0.6: the shared project-name helper
_PN_SUF = re.compile(r"(?i)\s+(?:projects?|property|properties|claims?|concessions?|permits?|licen[cs]es?|mine[ \t]+complex|"
                     r"mining[ \t]+complex|mines?|complex|deposits?|camp|district|prospects?|zones?|targets?|trend|showing|vein|"
                     r"discovery|underground|open[\s\-]*pit)$")
_PN_TAIL = re.compile(r"(?i)\s+(?:and|&)\s+(?:gold|silver|copper|zinc|nickel|polymetallic|base\s+metals?|critical\s+minerals?)\b.*$")
_PN_DESC = re.compile(r"(?i)^(?:polymetallic|poly-metallic|vms|(?:gold|silver|copper|zinc|lead|nickel|cobalt)"
                      r"(?:-(?:gold|silver|copper|zinc|lead|nickel|cobalt))+)$")
_PN_BAD_LEAD = {"extend", "extends", "extending", "work", "interval", "expanded", "current", "underground", "encouraging",
                "strong", "prospect", "deposit",
                # rev 2: a drilling method or a common noun is not a project ("Reverse Circulation Drill Samples",
                # "Maritime Concession Land")
                "reverse", "diamond", "core", "auger", "rc", "drill", "drilling", "sampling", "trenching", "maritime",
                "mining", "exploration", "regional", "land", "surface", "mineral", "main"}
_PN_REAL = r"(?:\s+[A-Z][\w'\u2019\-]*){0,2}\s+(?:projects?|property|properties|mine|mines|claims|concessions?|complex|deposits?|prospect)\b"
_PN_LEVEL1 = re.compile(r"(?i)\s(?:projects?|property|properties|claims?|concessions?|mines?|complex|permits?|licen[cs]es?)$")


def _pn_page(name):
    """A helper name in this page's form: 'Lac Dore Vanadium Property' -> 'Lac Dore Vanadium', 'Campo Morado
    polymetallic VMS Mine' -> 'Campo Morado', 'Ishkoday Gold and Polymetallic Project' -> 'Ishkoday Gold'; a list -> None."""
    s = (name or "").strip()
    for _ in range(3):
        s = _PN_SUF.sub("", s).strip()
    s = _PN_TAIL.sub("", s)
    if not s or re.search(r"(?i)\s(?:and|&)\s", s):
        return None
    s = " ".join(w for w in s.split() if not _PN_DESC.match(w))
    n = _clean_name(s) if s else None
    if not n or n.split()[0].lower() in _PN_BAD_LEAD:
        return None
    return n


def _pn_real(name, text):
    """The text writes the name before Project/Property/Mine/Claims/Deposit... ('Current Project', 'Premier Gold Project')."""
    return bool(name) and bool(re.search(re.escape(name) + _PN_REAL, text or "", re.I))


def _pn_words(name):
    return set(PN.key(name or "").split())


def _pn_not_a_name(own, text):
    """1.0.5's name is no project: the helper does not read it as a name and the text never calls it a project."""
    return PN.clean(own + " Project") is None and not _pn_real(own, text)


def _project_pn(th, t):
    """1.0.6: (name, rank) -- 1.0.5's find_project, filled or corrected by the shared helper (see the notes above)."""
    name, rank = find_project(th, t)   # 1.0.5's choice
    try:
        cands = PN.projects(th, t)
    except Exception:
        cands = []
    if not cands:
        return name, rank
    hw = _pn_words(th)
    head = [n for n in cands if _pn_words(n) and _pn_words(n) <= hw | {"project", "property"}]
    pick = head[0] if head else cands[0]
    new = _pn_page(pick)
    if not new:
        return name, rank
    early = bool(_pn_words(new)) and _pn_words(new) <= set(PN.key(" ".join((t or "")[:800].split())).split())
    level1 = bool(_PN_LEVEL1.search(pick))
    if not name:
        if head or (pick == cands[0] and early and level1 and _pn_real(new, t)):
            return new, 1 if level1 else 2
        return name, rank
    if PN.key(name) == PN.key(new) or _pn_words(name) == _pn_words(new):
        return name, rank
    if level1 and (head or early or pick == cands[0]) and _pn_not_a_name(name, t):
        return new, 1
    return name, rank


# ------------------------------------------------------------------ matching helpers
def _same(a, b):
    if D._family(a["metal"]) != D._family(b["metal"]) or a["metal"] != b["metal"]:
        return False
    ga = a["grade"] * D._TO_PPM.get(a["unit"], 1.0)
    gb = b["grade"] * D._TO_PPM.get(b["unit"], 1.0)
    if abs(ga - gb) > max(0.015 * max(ga, gb), 0.0051 * D._TO_PPM.get(b["unit"], 1.0)):
        return False
    return abs(a["length_m"] - b["length_m"]) <= max(0.03 * max(a["length_m"], b["length_m"]), 0.06)


def _one_length_per_grade(ivs, text):
    """The parser can pair one grade with two lengths ("0.8 m with 369.00 g/t Gold over 0.4 meters"): keep the length
    written nearest the grade, on either side ("76.10 m @ 3.26 g/t" or "3.26 g/t over 76.1 m")."""
    def dist(iv):
        lit = ("%.3f" % iv["length_m"]).rstrip("0").rstrip(".")
        if re.match(r"(?i)^[^;()]{0,30}?\b(?:over|across)\s+" + re.escape(lit) + r"(?:\.0+)?(?![\d])", text[iv["pos"]:iv["pos"] + 60]):
            return -1  # "369.00 g/t Gold over 0.4 meters"
        lo = max(0, iv["pos"] - 80)
        hits = [abs(m.start() + lo - iv["pos"]) for m in re.finditer(r"(?<![\d.])" + re.escape(lit) + r"(?:\.0+)?(?![\d])", text[lo:iv["pos"] + 80])]
        return min(hits) if hits else None
    out = []
    for iv in ivs:
        twins = [x for x in ivs if x is not iv and x["pos"] == iv["pos"] and x["grade"] == iv["grade"] and x["metal"] == iv["metal"]]
        if twins:
            d = dist(iv)
            others = [dist(x) for x in twins]
            if any(o is not None and (d is None or o < d) for o in others):
                continue
        out.append(iv)
    return out


def _hole_prefix(hole):
    """"SP" for "SP23-17": the letters a program's hole ids share, year and number aside."""
    m = re.match(r"^([A-Za-z]{1,6})", hole or "")
    return m.group(1).upper() if m else ""


def _old_hole(hole, release_date):
    """Hole id names a year well before the release ("TM22-119" in a 2025 release)."""
    m = _RE_HOLE_YEAR.match(hole or "") or re.match(r"^(\d{2})-[A-Z]{1,4}-\d", hole or "")   # 1.0.8: "18-EP-025"
    if not m or not release_date:
        return False
    yy = release_date[0] % 100
    groups = [int(g) for g in re.findall(r"(?<![\d])(\d{2})(?![\d])", hole[m.end(1):])]
    if any(g in (yy, yy - 1) for g in groups):
        return False  # "J-10-21": hole 10 of 2021
    if re.match(r"^[A-Z]\d{2}-\d{4,}-\d", hole):
        return False  # 1.0.2: "G11-3552-25" is Group Eleven's grid-numbered hole, not a 2011 hole
    if re.search(r"(?i)(?:W\d{1,2}|[\-_]?EXT?|X)$", hole):
        return False  # "CS-21-73W1", "TM21-107X": a wedge or extension drilled from an old hole is new drilling (1.0.1)
    if re.match(r"[\-_]\d{5,}$", hole[m.end(1):]):
        return False  # FIX3: "AB36-262441", "AB29-556043": a grid or coordinate number, not a year and a hole number
    y = 2000 + int(m.group(1))
    if y > release_date[0]:
        if int(m.group(1)) < 50:
            return False  # FIX3: "AB25-10" in a 2021 release is no 1925 hole; the digits are a level or a section
        y -= 100  # 1.0.8: "DDH88-11" in a 2026 release is a 1988 hole, not a 2088 one
    return y < release_date[0] - 1  # a hole named for last year is still this program's hole (1.0.1: "OB-24" in Sept 2025)


_RE_WIDTH_NOTE = re.compile(r"(?i)\(\s*[\d.,]+\s*(?:m|metres?|meters?)\s*,?\s*(?:etw|e\.t\.w\.?|tw|true\s+widths?|est\w*\.?\s+true\s+widths?)"
                            r"(?:\s*[\"\u201c\u201d]?\s*ETW\s*[\"\u201c\u201d]?)?\s*\)"
                            r"|(?<=metres|meters)\s+down[\-\s]?hole(?=\s*(?:\([^()]{0,60}\)\s*)?grading\b)|(?<=\dm)\s+down[\-\s]?hole(?=\s*(?:\([^()]{0,60}\)\s*)?grading\b)")


def _width_from_note(t, iv, a, b):
    lit = ("%.3f" % iv["length_m"]).rstrip("0").rstrip(".")
    return bool(re.search(r"(?<![\d.])" + re.escape(lit) + r"(?:\.0+)?(?![\d])", t[a:b])) and abs(a - iv["pos"]) < 120


def _rounded_same(h, b):
    """A headline that rounds the body's figure: "14 metres of 7 g/t" for "14.0 m grading 6.68 g/t"."""
    if h["metal"] != b["metal"] or h["unit"] != b["unit"]:
        return False

    def rounds_to(short, full):
        for nd in (0, 1):
            if abs(short - round(short, nd)) < 1e-9:
                return abs(round(full, nd) - short) < 1e-9 and abs(full - short) <= 0.1 * max(short, 1e-9)
        return False
    return rounds_to(h["grade"], b["grade"]) and rounds_to(h["length_m"], b["length_m"])


# 1.0.3: wording that credits an intercept to a hole, for a headline intercept that names none
_HL_HOLE_WINDOW = 1800          # how far past an intercept to look for the hole that is credited with it
_RE_HOLE_CREDIT_BEFORE = re.compile(
    r"(?i)(?:\b(?:in|from|for|at|with|and)\s+(?:the\s+)?)?\b(?:drill[\s\-]?)?(?:hole|ddh|borehole)s?\s*(?:#|no\.?|id)?\s*[:#]?\s*$")
_RE_HOLE_CREDIT_AFTER = re.compile(
    r"(?i)\s*[:,]?\s*(?:has\s+|was\s+)?(?:intersect\w*|intercept\w*|return\w*|encounter\w*|cut|cuts|hit|hits|report\w*|assay\w*|grad\w*|evaluat\w*|test\w*|drill\w*|confirm\w*|extend\w*)")


def _heads_list(t, h):
    """The id heads a list or a paragraph of results: 'CH19-240: 25.5 g/t', '\u2022 AB-12-25:', 'DD22-ABC-006 - 4.41 g/t'."""
    return bool(re.match(r"(?i)\s*(?:\([^()\n]{0,40}\)\s*)?(?:(?:has\s+|have\s+)?(?:intersected|intercepted|returned|assayed|cut|highlights?"
                         r"|results?|delivers|delivered)\s*)?(?::|[\-\u2013\u2014]\s)", t[h["end"]:h["end"] + 60]))


_RE_FIG_WORD = re.compile(r"(?i)^(?:and|at|of|over|grading|with|m|metres?|meters?|ft|feet|g/t|gpt|ppm|ppb|oz/t|opt|eq|gold|silver|copper"
                          r"|zinc|lead|nickel|cobalt|" + D._METAL_ALT_NEW + r")$")


def _fig_list_paren(t, pos, end):
    """Where the bracket opens in '... and 9.9 m at 3.58% Li2O (' -- figures and nothing else up to it -- or None."""
    w = t[pos:end]
    k = w.find("(")
    if k < 0 or re.search(r"[.;:]\s", w[:k]):
        return None
    words = re.findall(r"[A-Za-z][A-Za-z0-9/]*", w[:k])
    if not words or not all(_RE_FIG_WORD.match(x) for x in words):
        return None
    k2 = k + 1
    while k2 < len(w) and w[k2] == " ":
        k2 += 1
    return pos + k2


def _attach_holes(t, spans, holes, intervals, targets=None):
    """Hole for each text interval: 'in/from hole X' right after it, else the nearest id before it in
    the same unit, else a keyword id earlier in the same paragraph. Ids in historical units never count.
    targets (1.0.8): only these intervals are credited; the others only mark where the next figure starts."""
    for iv in (intervals if targets is None else targets):
        if iv.get("hole"):
            continue
        u = unit_at(spans, iv["pos"])
        us, ue = spans[u] if u >= 0 else (0, len(t))
        # 1.0.4: an "including ..." clause between a parent and the hole it is credited to must not cut the
        # search short: "4.75 g/t Au over 1.4 m. including 16.03 g/t Au over 0.4 m (VG), in hole BRDS-26-114"
        nxt = min((x["pos"] for x in intervals if x["pos"] > iv["pos"] and not x.get("including")),
                  default=len(t))
        after = [h for h in holes if iv["pos"] < h["pos"] < min(nxt, iv["pos"] + 220, ue)
                 and re.search(r"(?i)\b(?:in|from|of|for)\s+(?:the\s+)?(?:drill[\s\-]?)?(?:hole|DDH|borehole)s?\s*"
                               r"(?:#|No\.?)?\s*[:#]?\s*$", t[max(iv["pos"], h["pos"] - 40):h["pos"]])]
        if after:
            iv["hole"], iv["hole_how"] = after[0]["id"], "after"
            continue
        # 1.0.4: an "including ..." clause is part of this intercept, not the next one, so it must not end
        # the window either ("14.10 g/t gold over 1.59 m, including 47.87 g/t over 0.46 m (TR1-26-145)")
        nxt_other = min((x["pos"] for x in intervals if x["pos"] > iv["pos"] and not x.get("including")
                         and abs(x["length_m"] - iv["length_m"]) > 0.01), default=len(t))
        paren = [h for h in holes if iv["pos"] < h["pos"] < min(nxt_other, iv["pos"] + 160, ue)
                 and re.search(r"\(\s*$", t[max(iv["pos"], h["pos"] - 3):h["pos"]])
                 and not re.search(r"[.;]\s", t[iv["pos"]:h["pos"]])]
        if paren:
            iv["hole"], iv["hole_how"] = paren[0]["id"], "paren"  # "327.0 g/t Au over 1.0 metre (TM25-176)"
            continue
        # 1.0.8: a bracketed hole closing a list of figures is the hole of each ("56.6 m at 1.37% Li2O and 9.9 m at
        # 3.58% Li2O (AB23-231)")
        lp = _fig_list_paren(t, iv["pos"], min(len(t), iv["pos"] + 200, ue))
        if lp is not None:
            hp = [h for h in holes if lp <= h["pos"] <= lp + 2]
            if hp:
                iv["hole"], iv["hole_how"] = hp[0]["id"], "paren"
                continue
        # 1.0.4: the same credit without the word hole -- "(including 130m @ 0.5 g/t gold in MBA036)"
        named = [h for h in holes if iv["pos"] < h["pos"] < min(nxt_other, iv["pos"] + 160, ue)
                 and re.search(r"(?i)\b(?:in|from|of|for)\s+(?:the\s+)?$", t[max(iv["pos"], h["pos"] - 12):h["pos"]])
                 and not re.search(r"[.;]\s", t[iv["pos"]:h["pos"]])]
        if named:
            iv["hole"], iv["hole_how"] = named[0]["id"], "named"
            continue
        before = [h for h in holes if us <= h["pos"] < iv["pos"]]
        if before:
            iv["hole"], iv["hole_how"] = before[-1]["id"], "before"
            continue
        para_start = t.rfind("\n\n", 0, iv["pos"])
        back = [h for h in holes if (h["kw"] or h.get("known")) and max(para_start, iv["pos"] - 700) <= h["pos"] < iv["pos"]]
        # 1.0.8: an id that heads the list the figure belongs to ("\u2022 AB-12-25: o 21.5m at 1.32 g/t ... o 45m at 1.24
        # g/t") is its hole, not a keyword id further up ("holes AB-09-25 and AB-10-25 were reported June 4")
        head = [h for h in holes if max(para_start, iv["pos"] - 700) <= h["pos"] < iv["pos"] and _heads_list(t, h)
                and not any(h["pos"] < x["pos"] < iv["pos"] - 2 and norm_hole(x["hole"]) != norm_hole(h["id"])
                            for x in intervals if x.get("hole"))]
        if head and (not back or head[-1]["pos"] > back[-1]["pos"]) and not context_reason(t[head[-1]["pos"]:head[-1]["pos"] + 200], None):
            iv["hole"], iv["hole_how"] = head[-1]["id"], "heading"
            continue
        if back and not context_reason(t[back[-1]["pos"]:back[-1]["pos"] + 200], None):
            iv["hole"], iv["hole_how"] = back[-1]["id"], "para_kw"
            continue
        # 1.0.3: "drillhole BA-25-006 evaluated an IP anomaly. The hole intersected ... 6.27 g/t Au over 7.4 m" --
        # one hole named in a preceding sentence, and nothing else in between, is the hole.
        # 1.0.4: releases that head each hole's results with its id ("CDH-26-243 - Central D Vein area ...
        # 17 meters grading 178 gpt silver from 435.0 meters downhole") put several ids in the look-back, so
        # the 1.0.3 "exactly one" test declined every one of them. The nearest id before the intercept owns it.
        wide = [h for h in holes if iv["pos"] - 900 <= h["pos"] < iv["pos"]]
        if wide and not context_reason(t[wide[-1]["pos"]:wide[-1]["pos"] + 200], None):
            iv["hole"], iv["hole_how"] = wide[-1]["id"], "wide"


# 1.0.8 (HOLE_REPEAT_V1): the headline figure is usually quoted again further down -- in the highlights, in the
# hole's own paragraph, in the results table -- and there the release says which hole it came from. The reader used
# to credit a hole only where the figure first appeared, often the headline repeated at the top of the body, where the
# nearest id is some other hole (AB25-094 for AB25-100's "1.04 g/t over 19.8 m", a historic hole for the new hole's
# 200.7 m) or none at all. The top interval now takes the hole every other full quotation of it agrees on, when its
# own was found only by a loose rule, or not at all, or it sits in the headline copy.
_HOLE_HOW_FIRM = ("after", "paren", "named", "before", "heading", "table")


def _hole_from_repeats(t, spans, holes, top, text_ints, merged, copy):
    L = float(top["length_m"])
    got = []
    for p in _occurrences(t, top):
        if top["src"] != "headline" and abs(p - top["pos"]) < 5:
            continue
        us, ue = spans[unit_at(spans, p)]
        seg = t[max(us, p - 120):min(ue, p + 120)]
        if not any(_ft_close(_ft_m(D._num(m.group(1)), m.group(2)), L) for m in _RE_FT_LEN.finditer(seg)):
            continue  # the same grade, but not the same interval
        tmp = {"pos": p, "length_m": L, "grade": top["grade"], "metal": top["metal"], "including": False}
        # every figure written after this one ends its window, repeats included (the parser keeps one copy of each)
        own = _RE_N_GRADE.match(t, p)
        figs = [{"pos": m.start(), "length_m": -1.0} for m in _RE_N_GRADE.finditer(t, own.end() if own else p + 1, min(len(t), p + 400))]
        _attach_holes(t, spans, holes, [tmp] + figs, targets=[tmp])
        how = tmp.get("hole_how")
        if how == "para_kw":  # "Drillhole ABDH007 intersected: o 90.0m at 4.05% CuEq": the id right above, nothing between
            hp = max(h["pos"] for h in holes if h["id"] == tmp["hole"] and h["pos"] < p)
            if p - hp < 400 and not any(hp < h["pos"] < p for h in holes):
                how = "heading"
        if tmp.get("hole") and how in _HOLE_HOW_FIRM:
            got.append(tmp["hole"])
    got += [x["hole"] for x in merged if x is not top and x.get("src") == "table" and x.get("hole") and not x["reason"]
            and _same(x, top)]
    if len({norm_hole(h) for h in got}) != 1:
        return
    in_copy = top["src"] == "headline" or bool(copy and copy[0] <= top["pos"] < copy[1])
    new = max(got, key=len)
    cut = (bool(top.get("hole")) and len(norm_hole(top["hole"])) < len(norm_hole(new)) and norm_hole(new).startswith(norm_hole(top["hole"]))
           and bool(re.search(r"\d", norm_hole(new)[len(norm_hole(top["hole"])):])))
    if not top.get("hole") or top.get("hole_how") not in _HOLE_HOW_FIRM or in_copy or cut:  # cut: "CH19" of "CH19-240"
        top["hole"], top["hole_how"] = new, "repeat"


# FIX5 (HOLE_OWNER_V1): a hole that a quotation of the shown figure sits with, unambiguously. A hole named as the place
# another hole was drilled from or near ("40m east of AB-066-22", "100 m down-dip of previously released AB-0058") is a
# landmark and owns nothing.
_RE_REF_ID_BEFORE = re.compile(
    r"(?i)(?:\b(?:north|south|east|west)(?:east|west)?\s+of|\b(?:up|down)[\s\-]?dip\s+(?:of|from)|\balong\s+strike\s+(?:of|from)"
    r"|\b(?:above|below|beneath|underneath)|\bpreviously\s+(?:released|reported|announced|disclosed|drilled|completed)"
    r"|\bsame\s+(?:[\w\-]+\s+)?(?:setup|set[\s\-]up|pad|platform|collar|location)\s+as|\btwin(?:s|ned|ning)?(?:\s+of)?|\badjacent\s+to"
    r"|\boffset\w*\s+(?:of|to|from)|\bstep[\s\-]?out\s+(?:of|from)|\b(?:stepping|stepped)\s+(?:\w+\s+)?from)"
    r"\s+(?:(?:the|hole|holes|drill\s*holes?|drillholes?|DDH)\s+){0,2}$")
_RE_OWNER_BACKREF = re.compile(r"(?i)^(?:the|this|that)\s+(?:drill\s*)?hole\b|^it\b|^the\s+(?:interval|intercept|intersection)\b")
_RE_OWNER_AFTER = re.compile(r"(?i)(?:\(\s*|\b(?:in|from)\s+(?:the\s+)?(?:drill[\s\-]?)?(?:hole|DDH|borehole)\s*(?:#|no\.?)?\s*)$")


def _landmark(t, h):
    return bool(_RE_REF_ID_BEFORE.search(t[max(0, h["pos"] - 70):h["pos"]]))


def _owner_of(t, holes, top, p):
    """The hole the quotation of the top figure at p belongs to: named right after it ("8.8 m of 4.8% CuEq in hole X",
    "... from 170.10 metres (X)"), heading the line or list item it sits in ("X:\n\n26 m at 1.29% Li2O", "\u2022 X was drilled
    ... The hole returned ..."), or opening its one-line table row ("X North 124.21 127.00 2.79 37.33"). A set of holes
    (empty: no hole named; two: the quotation is ambiguous)."""
    L = float(top["length_m"])
    own = _RE_N_GRADE.match(t, p)
    ls, le = t.rfind("\n", 0, p) + 1, t.find("\n", p)
    le = len(t) if le < 0 else le
    if own is None:  # a bare table cell: the row must start with the hole and carry the length too
        h0 = [h for h in holes if ls <= h["pos"] < p and not t[ls:h["pos"]].strip()]
        lens = [x for x in re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])", t[h0[0]["end"]:p]) if abs(float(x) - L) <= 0.011] if h0 else []
        if h0 and lens and not any(h0[0]["end"] <= h["pos"] < le for h in holes if h is not h0[0]):
            return {norm_hole(h0[0]["id"]): h0[0]["id"]}
        return {}
    lo = max(0, p - 120)
    nx = _RE_N_GRADE.search(t, own.end(), min(len(t), p + 160))
    lens = list(_RE_FT_LEN.finditer(t, lo, p))[-1:] + list(_RE_FT_LEN.finditer(t, own.end(), nx.start() if nx else min(len(t), p + 160)))[:1]
    beside = any(_ft_close(_ft_m(D._num(m.group(1)), m.group(2)), L) for m in lens)   # the length written beside it
    item = re.search(r"\n[ \t]*(?:[\u2022\u25cf\u25aa\u25e6\u00bb*\-]|o[ \t])|\n[ \t]*\n|[.;]\s+(?=[A-Z])", t[own.end():own.end() + 300])
    item_end = own.end() + (item.start() if item else 300)
    if not beside and not any(_ft_close(_ft_m(D._num(m.group(1)), m.group(2)), L) for m in _RE_FT_LEN.finditer(t, own.end(), item_end)):
        return {}  # not the same interval
    # every hole bracketed or written "in hole X" later in the same list item or sentence names the figure ("8.8 m of
    # 4.8% CuEq in hole X", "0.1% Sn and 45 ppm Ta over 28.3 m, including 0.3% Sn ... over 3.0 m\n(X)")
    found = {}
    for h in holes:
        if own.end() <= h["pos"] < item_end and _RE_OWNER_AFTER.search(t[max(0, h["pos"] - 40):h["pos"]]) and not _landmark(t, h):
            found.setdefault(norm_hole(h["id"]), h["id"])
    if not beside:
        return found  # the length is further along the item: it can only make the figure ambiguous
    prev = [h for h in holes if p - 700 <= h["pos"] < p and not _landmark(t, h)]
    if prev:
        h = prev[-1]
        hs = t.rfind("\n", 0, h["pos"]) + 1
        rest = t[h["end"]:t.find("\n", h["end"]) if t.find("\n", h["end"]) >= 0 else len(t)]
        heads = (re.fullmatch(r"[\s\-*\u2022\u25cf\u25aa\u25e6\u00bbo]*(?i:(?:drill\s*)?hole\s*|DDH\s*)?", t[hs:h["pos"]])
                 or re.fullmatch(r"(?i)[^\n]{0,30}:\s*", rest))
        gap = t[h["end"]:p]
        ok = bool(heads) and not re.search(r"\n[ \t]*[\u2022\u25cf\u25aa\u25e6\u00bb*]", gap)
        if ok and re.search(r"\n[ \t]*\n", gap):
            ok = all(not ln.strip() or _RE_LIST_ITEM.search(ln) for ln in gap.split("\n")[1:])
        if ok:
            for m in re.finditer(r"[.;]\s+(?=[A-Z(])", gap):
                if not _RE_OWNER_BACKREF.search(gap[m.end():]):
                    ok = False
                    break
        if ok:
            found.setdefault(norm_hole(h["id"]), h["id"])
    return found


_RE_HOLE_SHORT = re.compile(r"(?i)\b(?:drill\s*)?hole\s+(?:#\s*|no\.?\s*)?(?P<n>\d{1,4})"
                            r"(?![\d.,\-/]|\s*(?:m\b|metres?|meters?|ft\b|feet|%|g/t|holes?\b|to\b|and\b|through\b))")


def _short_holes(t, holes):
    """"discovery hole 13 include:" -- one of the release's own ids (AB-19-13) written by its number alone; taken only
    when exactly one full id of the release ends in that number."""
    full = {h["id"] for h in holes if re.search(r"[A-Za-z]", h["id"]) and re.search(r"[\-_]\d{1,4}$", h["id"])}
    out = []
    for m in _RE_HOLE_SHORT.finditer(t):
        if any(h["pos"] <= m.start("n") < h["end"] for h in holes):
            continue
        cands = {k for k in full if int(re.search(r"(\d{1,4})$", k).group(1)) == int(m.group("n"))}
        if len(cands) == 1:
            out.append({"id": cands.pop(), "pos": m.start("n"), "end": m.end("n"), "kw": True})
    return out


def _owned_hole(t, holes, top):
    """The one hole every quotation of the top figure that names a hole agrees on, or None."""
    holes = sorted(holes + _short_holes(t, holes), key=lambda h: h["pos"])
    owners = {}
    for p in _occurrences(t, top):
        for k, v in _owner_of(t, holes, top, p).items():
            owners.setdefault(k, set()).add(v)
    if len(owners) != 1:
        return None
    return max(next(iter(owners.values())), key=len)


# ------------------------------------------------------------------ analysis
_RE_LIST_ITEM = re.compile(r"(?i)\d[\d.,]*\s*(?:m|metres?|meters?|ft|feet)\b|\d\s*(?:g/t|gpt|%|ppm|oz/t)")
_RE_DRILL_CONTEXT = re.compile(r"(?i)\b(?:drill\s*holes?|holes?\s+[A-Z0-9]|DDH|drilled|drilling|intersect\w*|core\s+(?:assays?|samples?))\b")
_STRONG_REASONS = ("xrf", "visual", "historical", "previously_reported", "surface")


_RE_SURFACE_INTRO = re.compile(
    r"(?i)\b(?:report|announc|present|provid)\w*\s+(?:\w+\s+){0,4}?(?:channel|trench\w*|grab|chip|soil|rock|surface|outcrop|bedrock)"
    r"\s+(?:sampl\w*\s+)?(?:results|assays?|program\w*)")
_RE_CAMPAIGN_HEADLINE = re.compile(r"(?i)\bdrill(?:ing)?\s+(?:campaign|program(?:me)?|season|rigs?)s?\b|\b(?:second|third|additional)\s+(?:drill\s+)?rig\b"
                                  r"|\b(?:resumes?|restarts?|recommences?)\s+(?:\w+\s+)?drilling\b"
                                  r"|\bdrill(?:ing)?\s+(?:(?!continu)\w+\s+){0,5}?to\s+(?:expand|test|extend|follow\s+up|target|evaluate|define|commence|begin|start)\b")
_RE_NOT_RESULTS_HEADLINE = re.compile(
    r"(?i)\b(?:private\s+placement|financing|offering|acquisition|acquires?|to\s+acquire|secures|option\s+agreement"
    r"|letter\s+of\s+intent|definitive\s+agreement|annual\s+general|shareholders?\s+meeting"
    r"|(?:ip|geophysical|magnetic|airborne|gravity|ground)\s+surveys?|technical\s+report"
    r"|financials|financial\s+(?:statements|results)|md&a|president'?s\s+message|webinar|conference)\b")
_RE_RESULTS_WORDS = re.compile(r"(?i)\b(?:results?|assays?|intersect\w*|intercept\w*|returns?|grading|drills\b|hits?|intervals?)\b")
_HEADLINE_METALS = [("Au", r"gold"), ("Ag", r"silver"), ("Cu", r"copper"), ("Zn", r"zinc"), ("Ni", r"nickel"),
                    ("Li", r"lithium"), ("U", r"uranium"), ("REE", r"rare\s+earths?|REE"), ("W", r"tungsten"),
                    ("Sb", r"antimony"), ("PGE", r"palladium|platinum|PGE|PGM")]
_PCT_CAP = {"Cu": 45.0, "CuEq": 60.0, "Ni": 40.0, "NiEq": 50.0, "Co": 25.0, "Li2O": 10.0, "Mo": 60.0, "Zn": 70.0, "Pb": 87.0,
            "Ta2O5": 10.0, "Nb2O5": 20.0, "TREO": 30.0, "REO": 30.0, "U3O8": 90.0, "Sb": 72.0, "WO3": 80.0}
# grade x length ceilings in g/t-metres: beyond these a table column or a number was misread
_GM_CAP = {"Au": 6000.0, "AuEq": 6000.0, "Ag": 250000.0, "AgEq": 250000.0}


# 1.0.2: "Silver Park", "Copper Mountain", "Gold Lake": a metal word that begins a place name says nothing about the release metal (NKG.V)
_PLACE_AFTER_METAL = (r"(?![\s\-]+(?:Park|Peak|Hill|Hills|Creek|Lake|Lakes|Mountain|Mountains|Ridge|River|Valley|Bay|Butte|Canyon|Flats?"
                      r"|Queen|King|Star|Cloud|Dome|Point|Springs?|Basin|Lode|Cliffs?|Crest|Range|Falls|Island|City|Bear|Hawk|Pond|Road|Trail|Pass|Bell|Cup)\b)")


def _headline_family(th):
    best = None
    for fam, pat in _HEADLINE_METALS:
        m = re.search(r"(?i)\b(?:" + pat + r")\b" + _PLACE_AFTER_METAL, th)
        if m and (best is None or m.start() < best[1]):
            best = (fam, m.start())
    return best and best[0]


_BULLET_CHARS = " -*o" + "".join(map(chr, (0x2022, 0x25CF, 0x25AA, 0x25E6, 0xBB, 0x8A, 0x8C)))


def _heading_ctx(t, spans, u):
    """Text a list item inherits: the lead-in line above the run of list items it belongs to."""
    k = u - 1
    steps = 0
    while k >= 0 and steps < 14:
        s, e = spans[k]
        txt = t[s:e].strip()
        if not txt.strip(_BULLET_CHARS):
            k -= 1
            continue
        if txt.endswith(":") or (steps and len(txt) <= 70 and not txt.endswith(".") and not _RE_LIST_ITEM.search(txt)):
            head = txt
            if len(txt) < 60 and k > 0:  # "Highlights include:" leans on the unit before it
                ps, pe = spans[k - 1]
                head = t[ps:pe].strip() + " " + head
            return head
        if not txt or (len(txt) < 260 and _RE_LIST_ITEM.search(txt)):
            k -= 1
            steps += 1
            continue
        return ""
    return ""


def _line_heading(t, pos):
    """The title line above a run of one-figure-per-line rows ("Colossa Mine Channel Samples")."""
    ls = t.rfind("\n", 0, pos) + 1
    for _ in range(15):
        if ls <= 0:
            return ""
        prev_s = t.rfind("\n", 0, ls - 1) + 1
        line = t[prev_s:ls].strip()
        ls = prev_s
        if not line:
            continue
        if _RE_LIST_ITEM.search(line) or (len(line) <= 25 and line.endswith(":")) or (len(line) <= 30 and re.search(r"\d|g/t|%|(?i:incl)", line)):
            continue
        return line if len(line) <= 80 and not line.endswith(".") else ""
    return ""


def _unit_ctx(t, spans, pos):
    u = unit_at(spans, pos)
    us, ue = spans[u]
    return t[us:ue], _heading_ctx(t, spans, u), pos - us


def _headline_copy(t, hl):
    """(start, end) of the headline repeated at the top of the body, or None."""
    words = re.findall(r"[A-Za-z0-9]+", hl or "")
    if len(words) < 5:
        return None
    first = re.compile(r"(?i)" + r"\W+".join(map(re.escape, words[:5])))
    last = re.compile(r"(?i)" + r"\W+".join(map(re.escape, words[-4:])))
    m = first.search(t[:2000])
    if not m:
        return None
    e = last.search(t, m.start(), m.start() + int(len(hl) * 1.6) + 40)
    return (m.start(), e.end()) if e else None


def _split_spans(spans, cuts):
    out = []
    for s, e in spans:
        pts = [s] + sorted(c for c in cuts if s < c < e) + [e]
        out += [(a, b) for a, b in zip(pts, pts[1:]) if b > a]
    return out


_RE_REF_HOLE = re.compile(
    r"(?i)\b(?:of|between|near(?![\s\-]+surface)|beside|adjacent\s+to|away\s+from|(?:up|down)[\s\-]?dip\s+(?:of|from)|along\s+strike\s+(?:of|from)"
    r"|(?:north|south|east|west)\w*\s+of|twin(?:ning|s)?\s+of|offset\w*\s+(?:of|to)|previously\s+\w+|historic\w*"
    r"|(?:stepping|step[\s\-]?outs?|laterally|extending)\s+(?:\w+\s+)?from|\)\s*,\s*(?:and\s+)?)\s*"
    r"(?:the\s+)?(?:\w+\s+){0,2}?(?:(?:drill\s*)?holes?\s+)?(?-i:[A-Z][A-Z0-9]*(?:\s*-\s*[A-Z0-9]+)+)\s*\([^()]{0,30}$"
    r"|\bbetween\b[^.]{0,160}\band\s+(?:(?:drill\s*)?holes?\s+)?(?-i:[A-Z][A-Z0-9]*(?:\s*-\s*[A-Z0-9]+)+)\s*\([^()]{0,30}$"
    r"|\bpreviously\s+\w+\b[^.()]{0,90}\(\s*(?-i:[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\s*:[^()]{0,30}$"
    # 1.0.1: "located 50m north of CC24_018, which intersected 88.25m of 0.60% CuEq"
    r"|\b(?:(?:north|south|east|west)\w*\s+of|(?:up|down)[\s\-]?dip\s+(?:of|from)|along\s+strike\s+(?:of|from)|below|above|beneath|adjacent\s+to|near(?![\s\-]+surface))\s+"
    r"(?:(?:drill\s*)?holes?\s+)?(?-i:[A-Z][A-Z0-9]*(?:[\-_][A-Z0-9]+)+)\s*,?\s*(?:which|that)\s+(?:previously\s+)?(?:intersected|returned|assayed|graded|intercepted)\s*,?\s*"
    r"(?:[\d.,]+[\s\-]*(?:m|metres?|meters?)\s*(?:of|@|at|grading)?\s*)?$")


_RE_SURFACE_NEAR = re.compile(r"(?i)\b(?:trench\w*|costeans?|channels?|channel(?:l)?(?:ed|ing)|chip|grab|outcrop|soil|boulder|float)\b(?![\s\-]+(?:Vein|Zone|Creek|Lake|Hill))")
_RE_DRILL_NEAR = re.compile(r"(?i)\b(?:drill\w*|holes?|DDH|core|borehole)\b")
_RE_BACKREF = re.compile(r"(?i)^\W*(?:this|that|the\s+(?:same|above|previous))\s+(?:\w+\s+){0,2}(?:intersection|intercept|hole|interval|result)"
                         # 1.0.8: "Other significant intercepts from this program included ..." after an earlier hole
                         r"|^\W*other\s+(?:[\w\-]+\s+){0,2}(?:intercepts|intersections|results|intervals|highlights)\s+(?:from|in|of)\s+(?:this|that|the\s+same)\b")
_RE_OLD_HOLE_REF = re.compile(
    r"(?i)\b(?:along\s+strike\s+(?:from|of)|away\s+from|near(?![\s\-]+surface)|(?:up|down)[\s\-]?dip\s+(?:of|from))\b[^.]{0,80}?"
    r"(?-i:[A-Z]{2,}[A-Z0-9]*-?\d[\w\-]*)\s*,?\s+which\s+(?:returned|intersected|graded)[^.]{0,40}$")
_RE_FOLLOW_UP_REF = re.compile(r"(?i)\bfollow\w*[\s\-]+up\s+on\b[^.]{0,120}\b(?:intercept|intersection|discovery|hole)s?\s+(?:of\s+)?$"
                               r"|\bfollow\w*[\s\-]+up\s+(?:on|to)\b[^.]{0,160}\b(?:hole|intercept|intersection|discovery)\b[^.]{0,40}?\b(?:that|which)\s+"
                               r"(?:assayed|returned|intersected|graded|yielded)\s+(?:[\d.,]+\s*(?:m|metres?|meters?)\s*(?:of|at|@|grading)?\s*)?$")
# "including 1.0 m at 22 g/t": the grade is where the figure starts, so allow a length between the word and it
_RE_INCL_TAIL = re.compile(r"(?i)\b(?:within\s*[:\-]?\s*|incl(?:uding|udes|\.)?\s*[:\-]?\s*(?:(?:a\s+)?(?:high[\s\-]grade\s+)?(?:interval\s+of\s+)?"
                           r"[\d.,]+\s*(?:m|metres?|meters?|ft|feet)\s*(?:at|@|of|grading|averaging|with)?\s*)?)$")
# "within 0.64 g/t Au over 55.4m": the figure after "within" is the parent of the one before it
_RE_WITHIN_TAIL = re.compile(r"(?i)\bwithin\s+(?:an?\s+)?(?:(?:broader|wider|larger|longer|thicker)\s+)?(?:(?:zone|interval|intercept|intersection|envelope|halo)\s+(?:of\s+)?)?"
                             r"(?:[\d.,]+\s*(?:m|metres?|meters?|ft|feet)\b\s*(?:-?\s*wide\s+)?(?:(?:zone|interval|envelope)\s+)?(?:at|@|of|grading|averaging)?\s*)?$")
# "Results Including 3.51 g/t AuEq over 93 metres": a list of results, not a sub-interval
_RE_LIST_INCL = re.compile(r"(?i)\b(?:results?|highlights?|intercepts?|intersections?|assays?|values|holes?|grades?|drilling)\s*,?\s+incl(?:uding|udes|\.)?\s*[:\-]?\s*$")
# "values up to 0.5 g/t Au within an 8 m-wide iron formation": the highest sample, not an interval
_RE_UP_TO = re.compile(r"(?i)\b(?:values?|grades?|samples?|concentrations?)\s+(?:of\s+|returning\s+|reaching\s+)?up\s+to\s*$")
# 1.0.1: "several intervals exceeding 50 m with grades above 10% P2O5", "in total ... 212 meters averaging above 0.1% Cu"
_THRESHOLD_WORD = r"(?:exceeding|above|greater\s+than|more\s+than|in\s+excess\s+of|>)\s*"
_RE_THRESHOLD_LEN = re.compile(r"(?i)" + _THRESHOLD_WORD + r"[\d.,]+\s*(?:m|metres?|meters?|ft|feet)\b")
_RE_THRESHOLD_GRADE = re.compile(r"(?i)" + _THRESHOLD_WORD + r"[\d.,]+\s*(?:%|g/t|gpt|ppm|grams)")
# "(see NR March 31, 2026)" after a figure: it was released before
_RE_REF_AFTER = re.compile(r"(?i)\(\s*(?:see\s+|refer\s+to\s+)?(?:the\s+)?(?:company'?s\s+)?(?:NR|news\s+release|press\s+release)s?\b[^()]{0,40}?(?:19|20)\d\d\s*\)"
                           r"|\(\s*(?:see\s+)?(?:[A-Z][a-z]+\.?\s+\d{1,2},?\s+)?(?:19|20)\d\d\s+(?:NR|news\s+release|press\s+release)\s*\)")
_RE_EQ_PAREN = re.compile(r"(?i)(\d[\d.,]*\s*(?:g/t|%|ppm)\s*[A-Za-z0-9]{1,6}Eq\s*)\([^()]{3,80}\)(?=\s*(?:over|across|for)\b)")
_RE_REASSAY = re.compile(r"(?i)\bre\s?-?\s?assay\w*")
_RE_INVESTEE = re.compile(r"(?i)\binvestee\b|\bportfolio\s+compan"
                          r"|\b(?:applau\w+|congratulat\w+)\s+(?!(?i:proposed|government|federal|provincial|premier|minister|announcement|decision|approval|the|its|all|his|her|their|team|everyone)\b)(?-i:[A-Z])"
                          r"|\b(?:strategic\s+|equity\s+)?investment\s+in\s+(?-i:[A-Z])[\w&.\- ]{2,40}\(\s*(?:TSX|CSE|ASX|NYSE|OTC)"
                          r"|\bsuccessful\s+investment\s+in\s+(?-i:[A-Z])[\w&.\-]{2,30}\s*:")  # 1.0.2: CDN.CN "REPORTS ON SUCCESSFUL INVESTMENT IN NORAM: NORAM ..."
# 1.0.1: a headline about another company's results ("highlights Results announced by Canada Nickel", "Discusses Allkem Ltd.'s")
_RE_INVESTEE_HEADLINE = re.compile(r"(?i)\b(?:results|success)\s+(?:announced|reported)\s+by\s+(?-i:[A-Z])"
                                   r"|\b(?:reports?\s+on|discuss\w*|comments?\s+on)\s+(?-i:[A-Z])[\w.&\-]*(?:\s+(?-i:[A-Z])[\w.&\-]*){0,3}['\u2019]s\b")
# the opening of a release that reports new assays (1.0.1): used only to overrule a plan / pending / corporate headline
_RE_NEW_RESULTS_LEDE = re.compile(
    r"(?i)\b(?:report|announc|provid|releas|present|deliver|shar)\w*\s+(?:\w+\s+){0,6}?(?:assay|drill(?:ing)?|analytical|laboratory|core)\s+results"
    r"|\b(?:report|announc|provid|releas|present)\w*\s+(?:the\s+)?(?:initial|first|final|further|additional|new|remaining|latest|complete)\s+(?:\w+\s+){0,3}?results"
    r"|\b(?:assay\s+)?results\s+(?:have\s+(?:now\s+)?been|were|are)\s+received|\breceived\s+(?:\w+\s+){0,3}(?:assay\s+)?results"
    r"|\bassays?\s+(?:results\s+)?(?:from|for)\s+(?:the\s+)?(?:first|initial|final|remaining|additional|next|last)?\s*(?:\w+\s+){0,2}(?:drill\s*)?holes"
    r"|\b(?:hole|DDH|drill\s+hole)\s+[A-Z][A-Za-z0-9]*[\-_]?[A-Za-z0-9\-]*\s+(?:returned|intersected|intercepted|assayed|cut|yielded)\b"
    # 1.0.2: "reports on the Company's second round of results for its inaugural diamond drill program" (FUTR.CN)
    r"|\b(?:report|announc|provid|releas)\w*\s+(?:on\s+)?(?:the\s+|its\s+)?(?:company['\u2019]s\s+)?(?:first|second|third|fourth|fifth|next|latest|final|new)\s+"
    r"(?:round|batch|set)\s+of\s+(?:assay\s+|drill(?:ing)?\s+)?results")
_RE_NEW_RESULTS_NOT_BEFORE = re.compile(r"(?i)(?:previous\w*|recent\w*|historic\w*|earlier|prior|past|\bto|\bwill|expect\w*|await\w*|summar\w*|consolidat\w*"
                                        r"|compil\w*|recap\w*|review\w*|once|when|until)\s+(?:\w+\s+){0,2}$")
_RE_NEW_RESULTS_NOT_IN = re.compile(r"(?i)summar|consolidat|compil|recap|historic|pending")
_RE_NEW_RESULTS_NOT_AFTER = re.compile(r"(?i)^\W{0,3}(?:for\s+(?:the\s+)?\w+\s+\w+\s+)?(?:were|was|have\s+been|had\s+been)\s+(?:previously\s+)?(?:announced|released|reported|disclosed|published)"
                                       r"|^[^.]{0,60}\b(?:are|remain|still)\s+pending")


def _new_results_lede(t: str) -> bool:
    """The opening says THIS release reports new assays (not that results were reported before, or are to come)."""
    for m in _RE_NEW_RESULTS_LEDE.finditer(t):
        before = t[max(0, m.start() - 60):m.start()]
        if _RE_NEW_RESULTS_NOT_BEFORE.search(before) and not re.search(
                r"(?i)(?:pleased|wish\w*|happy|excited|proud|delighted|like)\s+to\s+(?:\w+\s+)?$", before):
            continue
        if _RE_NEW_RESULTS_NOT_IN.search(m.group(0)) or _RE_NEW_RESULTS_NOT_AFTER.search(t[m.end():m.end() + 90]):
            continue
        return True
    return False
_RE_EVENT_HEADLINE = re.compile(r"(?i)\bwebinar\b|\binvites?\s+(?:\w+\s+){0,2}(?:investors|shareholders)\b|\blive\s+(?:investor\s+)?(?:presentation|event|stream)\b"
                                r"|\bfireside\s+chat\b|\bvirtual\s+(?:investor\s+)?(?:event|presentation)\b|\bupdates?\s+(?:on\s+)?(?:its\s+)?investment\s+in\b")
# plan wording in a headline ("Announces Drilling to Commence", "Commences Initial Diamond Drill Program"); the rest of the
# headline is what the release reports
_RE_PLAN_PHRASE = re.compile(
    r"(?i)\b(?:drill(?:ing)?\s+(?:targets?|to\s+(?:commence|begin|start|resume)|(?:program(?:me)?|campaign|season|rigs?)s?(?:\s+(?:to\s+)?(?:commenc\w*|underway|begins?|starts?|planned))?)"
    r"|(?:commenc\w+|begins?|starts?|mobiliz\w+|initiat\w+|launch\w*|plans?|prepares?\s+for|announces?)\s+(?:(?:initial|maiden|first|inaugural|phase\s+\w+|\d{4}|diamond|RC|core|a|an|the|its|\d[\d,]*\s*(?:m|metres?|meters?))\s+){0,4}"
    r"drill(?:ing)?(?:\s+(?:program(?:me)?|campaign))?)\b")
_RE_TABLE_DRILLED_YEAR = re.compile(r"(?i)\bdrilled\s+(?:in\s+)?(?:[A-Za-z\-]+\s+)?((?:19|20)\d\d)\b")
_RE_TABLE_HOLE_START = re.compile(r"^\s*(?-i:[A-Z]{1,6})[\-_]?\d[\w\-]*\b")
_RE_FIGURE_END = re.compile(r"(?i)(?:\d|g/t|gpt|%|ppm|ppb|oz/t|\bm|metres?|meters?|feet|ft|\)|\b[A-Z][a-z]?(?:Eq)?|\bU3O8|\bLi2O|\bWO3|\bdown\s?hole|\bdepth|\bcore\s+length|\btrue\s+width|\bsurface"
                            r"|\b(?:gold|silver|copper|zinc|lead|nickel|cobalt|uranium|lithium|antimony|tungsten|molybdenum|palladium|platinum)(?:\s+equivalent)?)\s*[,;:\-]?\s*$")


def _is_sub(tail):
    """'... over 16.55 m, including 5.65 m at 11.02 g/t' is a sub-interval; 'Intercepts at Auld Creek, Including 17m @ 9.8g/t' is a list."""
    m = _RE_INCL_TAIL.search(tail)
    if not m or re.match(r"(?i)within", m.group(0)):
        return False
    lead = re.sub(r"(?i)\b(?:that|which)\s+$", "", tail[max(0, m.start() - 46):m.start()])  # 1.0.2: "5.91 g/t Au that includes 0.80 m of 13.30 g/t"
    return bool(_RE_FIGURE_END.search(lead[-40:]))


_RE_PLAN_CTX = re.compile(r"(?i)\b(?:is|are|will\s+be)\s+planned\b[^.]{0,160}\b(?:intersected|returned|encountered)\s+(?:in\s+)?[^.]{0,60}$"
                          r"|\bwill\s+(?:test|follow\s+up)\b[^.]{0,160}\b(?:intersected|returned|encountered)\s+(?:in\s+)?[^.]{0,60}$")
_RE_TRENCH_AFTER = re.compile(r"(?i)^(?:[^.;()]|\.(?=\d)){0,60}?\b(?:in|from)\s+(?:the\s+)?(?:trench\w*|costeans?|channel\s+sampl\w*|channels?|grab\s+sampl\w*|outcrop)\b")
_RE_HIST_DRILL_HEADLINE = re.compile(r"(?i)\b(?:in|from)\s+(?:the\s+)?historic(?:al)?\s+(?:drill\w*|holes?|data|core|results|assays|intercepts)\b")
_RE_DRILL_VERB_HEADLINE = re.compile(r"(?i)\b(?:intersect(?:s|ing)?|intercept(?:s|ing)?|drills|drilling|hits|cuts|returns|returning|encounters?)\b")
_RE_SAMPLES_VERB = re.compile(r"^\W*(?:[A-Z][\w.&'\-]*\s+){1,4}?(?:Samples|Trenches|Channels|Channel\s+Samples)\s+(?:(?-i:[A-Z])\S*\s+){0,3}?(?:High[\s\-]Grade|Gold|Silver|Copper|Lithium|Uranium|up\s+to|\d)")
_RE_FOLLOW_UP_HEADLINE = re.compile(r"(?i)\b(?:to\s+)?follow[\s\-]?up\s+(?:on|to)\b[^|]{0,80}?\b(?:recent|previous(?:ly)?|prior|earlier|last\s+year'?s?)\b")
_RE_HOLE_YEAR = re.compile(r"^[A-Z]{1,6}-?(\d{2})(?:[-_]|[A-Z]{1,3}(?=\d))\d")  # 1.0.8: also "DDH04CB1"


def _local_reason(t, spans, iv, rdate, reason_for):
    """Reasons read from the few words right around one figure, or from the sentence before it."""
    before = t[max(0, iv["pos"] - 70):iv["pos"]]
    if _RE_SURFACE_NEAR.search(before) and not _RE_DRILL_NEAR.search(before):
        return "surface"  # "Trench TOST26-024 at Walaba intersected 7.0 m @ 4.57 g/t"
    if _RE_OLD_HOLE_REF.search(t[max(0, iv["pos"] - 200):iv["pos"]]) or _RE_FOLLOW_UP_REF.search(t[max(0, iv["pos"] - 200):iv["pos"]]):
        return "reference_hole"
    u = unit_at(spans, iv["pos"])
    if u > 0:
        us, ue = spans[u]
        ps, pe = spans[u - 1]
        cur, prev = t[us:ue], t[ps:pe]
        r_prev = reason_for(prev)
        if r_prev in ("historical", "previously_reported") and _RE_BACKREF.search(cur):
            return r_prev  # "... hole DM-22-273 (see press release January 16, 2023). This intersection ..."
        if (r_prev == "surface" and not _RE_DRILL_WORD.search(cur)
                and not re.search(r"(?i)\bsampl|trench|channel|chip|grab|assay", cur)):
            pass
    return None


def _rule(iv, name):
    """Remember which rule rejected an interval (first one wins)."""
    if iv.get("reason") and not iv.get("rule"):
        iv["rule"] = name


def _occurrences(t, iv):
    """Positions where the same grade figure appears again, e.g. the headline repeated at the top of the body."""
    g = iv["grade"]
    lits = {("%.3f" % g).rstrip("0").rstrip("."), ("%.2f" % g), ("%.1f" % g)}
    if g >= 1000:  # 1.0.8: "1,026 g/t Ag" is the same figure as 1026.0
        lits |= {("{:,.3f}".format(g)).rstrip("0").rstrip("."), "{:,.2f}".format(g), "{:,.1f}".format(g)}
    out = []
    for lit in lits:
        for m in re.finditer(r"(?<![\d.])" + re.escape(lit) + r"(?![\d])", t):
            out.append(m.start())
    return sorted(set(out))



# 1.0.2 (METAL_CONTEXT_V1). A grade written without a metal ("983 g/t over 3.4m at Galena") was gold unless a metal
# word stood just before it. In a silver release that made silver grades gold (USA.TO 983 g/t Au, BHS.V 1,104 g/t Au,
# AGAG.V 725 g/t Au). Now such a grade takes the release's own precious metal when its explicit grades are clearly
# silver. A percent grade is never inferred to be a precious metal (SIG.V "0.115%" of tungsten after "Gold Deposit";
# PNPN.V "2.34% CuEqRec" after "Ni-Cu-Pd"), a precious metal in percent is not a grade at all (AXO.V "gpt %" read as
# Pt), and "100% owned" is ownership (GOLD.TO "100% AuEq over 128 metres").
_RE_GOLD_WORD = re.compile(r"(?i)\bgold\b|\bAu(?:Eq)?\b")
_RE_OWNED_AFTER = re.compile(r"(?i)^\s*%?\s*[-\s]?(?:owned|interest|ownership|stake|held|controlled)\b")
_PRECIOUS = {"AU", "AG", "PT", "PD", "PGM", "PGE", "RH", "3E", "2PGM", "4E"}


def _precious(metal):
    return re.sub(r"(?i)eq$", "", (metal or "").split("+")[0]).upper() in _PRECIOUS


def dominant_precious(ints, text=""):
    """"Ag" when a release is clearly about silver: its explicit precious grades are silver, or it gives none and its
    prose says silver (lower case, so not a company name) and never gold. Else None."""
    ag = sum(1 for x in ints if x.get("metal_how") == "explicit" and D._family(x["metal"]) == D._family("Ag"))
    au = sum(1 for x in ints if x.get("metal_how") == "explicit" and D._family(x["metal"]) == D._family("Au"))
    if (ag >= 2 and ag >= 2 * au) or (ag >= 1 and au == 0):
        return "Ag"
    if ag == 0 and au == 0 and len(re.findall(r"\bsilver\b", text)) >= 2 and not re.search(r"\bgold\b", text):
        return "Ag"
    return None


def fix_metals(ints, text, dom):
    out = []
    for x in ints:
        g_at = x.get("pos") or 0
        if x.get("unit") == "%" and _precious(x.get("metal")):
            continue
        if x.get("unit") == "%" and abs((x.get("grade") or 0) - 100) < 1e-9:
            m = re.match(r"\s*100(?:\.0+)?", text[g_at:g_at + 12])
            if m and _RE_OWNED_AFTER.match(text[g_at + m.end():g_at + m.end() + 30]):
                continue
        if x.get("metal_how") == "inferred" and x.get("metal") == "Au" and dom == "Ag" \
                and x.get("unit") in ("g/t", "oz/t", "opt", "gms", "kg/t"):
            before = text[max(0, g_at - 160):g_at]
            cut = max([m.end() for m in re.finditer(r"[.;!?]\s|\n\s*\n", before)] + [0])
            if not _RE_GOLD_WORD.search(before[cut:]) and not _RE_GOLD_WORD.match(text[g_at:g_at + 40].split("over")[0][-12:] or ""):
                x = dict(x, metal="Ag", metal_how="release")
        out.append(x)
    return out


# ------------------------------------------------------------------ 1.0.8: what the release itself announces (NEWS_V1)
# A figure the reader accepts is shown as the release's new drill result. Outside its tag most such figures were
# background: an earlier or a past operator's hole, results restated from an earlier release or by a royalty holder,
# quoted in releases whose news is something else -- a plan, a program started, resumed or completed with assays
# pending, visual logs, probe / scintillometer / XRF readings, surface channel, chip, grab or trench samples, an option,
# a sale, a financing, a quarterly report. The reader now first reads what the release says it announces: the
# headline, clause by clause, and the company's own statement ("X is pleased to report ..."):
#   results  the headline states a drill result (a grade over a length, "drill / assay results", "intercepts") or the
#            statement reports results, assays or intersections: the figures are judged one by one, as before;
#   unclear  neither does ("Exploration Update", "Discovers New Zone"): a row only when a lead sentence that is not
#            background reports new assays or a hole's graded interval;
#   not      they announce something else, or call the news visual, instrument readings, surface samples, historic
#            data or pending assays: no row (is_result false with that reason), unless the lead plainly reports new
#            assays ("assays for the first ten holes have been received", "significant assays are tabulated below").
_N_VERBS = (r"announces|announce|reports|provides|commences|completes|terminates|grants|closes|identifies|discovers|expands|extends"
            r"|launches|begins|starts|prepares|plans|receives|signs|adds|appoints|confirms|continues|drills|intersects|intercepts"
            r"|hits|cuts|refines|outlines|increases|secures|files|updates|targets|defines|delivers|returns|encounters|resumes"
            r"|mobilizes|initiates|acquires|options|sells|stakes|consolidates|arranges|enters|highlights|advances|reaches")
_RE_N_SPLIT = re.compile(r"[;:|\u2022]|\s[-\u2013\u2014]+\s|,\s+(?=(?:and\s+)?(?:" + _N_VERBS + r")\b)"
                         r"|\s(?:and|&)\s+(?=(?:" + _N_VERBS + r")\b)"
                         # FIX3: "Completion of Drilling at X, and Further Drill Results": the results are a clause of their own
                         r"|,?\s(?:and|&)\s+(?=(?:further|additional|new|more|latest|first|initial|final|positive)\s+(?:[\w\-]+\s+){0,2}"
                         r"(?:results|assays|intercepts|intersections)\b)", re.I)
# FIX3: a drill-results phrase names new assays even beside a corporate item ("Reports Infill Drill Results and
# Feasibility Study Update")
_RE_N_DRILL_RESULTS = re.compile(r"(?i)\b(?:drill(?:ing|hole)?|assay|infill(?:\s+drill(?:ing)?)?|step[\s\-]?out\s+drill(?:ing)?)\s+results\b")
_RE_N_CORPORATE = re.compile(r"(?i)\b(?:preliminary\s+economic|PEA|feasibility|resource\s+estimate|MRE|financial|quarter\w*|annual|md&a"
                             r"|(?:year|quarter|period|months)\s+ended|outlook)\b")


def _n_results_beside_corporate(c):
    """FIX3: the clause reports drill results first and a corporate item after them ("Reports Infill Drill Results and
    Feasibility Study Update"); not drill results that led to the corporate item ("MRE Update following Drill Results")
    and not historic ones."""
    m = _RE_N_DRILL_RESULTS.search(c)
    return bool(m) and all(e.start() > m.end() and _RE_N_CORPORATE.fullmatch(e.group(0)) for e in _RE_N_ECON.finditer(c))
_RE_N_GRADE = re.compile(r"(?i)\d[\d,]*(?:\.\d+)?\s*(?:g/t|gpt|g/tonne|grams?\s+per\s+tonne|%|ppm|ppb|oz/t|opt|oz/ton)")
_RE_N_LEN = re.compile(r"(?i)\d[\d,]*(?:\.\d+)?[\s\-]*(?:m\b|metres?|meters?|ft\b|feet)")
_RE_N_DRILL = re.compile(r"(?i)\b(?:drill\w*|holes?|drillholes?|boreholes?|core|diamond|RC|reverse\s+circulation|DDH|intersect\w*"
                         r"|intercept\w*|hits?|cuts|returns?|returned|encounter\w*|assays?)\b")
_RE_N_DRILLW = re.compile(r"(?i)\b(?:drill\w*|holes?|drillholes?|boreholes?|core|diamond|RC|reverse\s+circulation|DDH|intersect\w*|intercept\w*)\b")
# the news is not an assay: visual logs, instrument readings
_RE_N_NOT_ASSAY = re.compile(r"(?i)\b(?:visual(?:ly)?|visible\s+(?:sulph|sulf|copper|mineral)\w*|scintillomet\w*|radioactiv\w*|radiometric"
                             r"|spectral|gamma|probe|(?:p|portable\s+|hand[\s\-]?held\s+)?x-?rf|equivalent\s+uranium|eU3O8|core\s+logs?"
                             r"|spectromet\w*|cps"   # FIX3: ">20,000 total cps on a hand-held spectrometer"
                             r"|logged|summary\s+logs?)\b")
_RE_N_SURFACE = re.compile(r"(?i)\b(?:grab|chips?|channels?|channel(?:l)?(?:ed|ing)|trench\w*|costeans?|soils?|rock\s+(?:samples?|sampling)|outcrops?|surface\s+sampl\w*"
                           r"|sampling|samples?|sampled|prospecting|mapping|till|boulders?|field\s+(?:work|campaign|program\w*|season)"
                           r"|cross[\s\-]?cut|underground\s+(?:drive|development|workings)"
                           r"|surface\s+(?:work|exploration|programs?|results|highlights))\b")   # 1.0.9: "results from surface work"
_RE_N_HIST = re.compile(r"(?i)\b(?:historic(?:al)?\s+(?:[\w\-]+\s+){0,2}(?:drill\w*|holes?|results?|data|assays?|intercepts?|intersections?"
                        r"|work|sampl\w*|core|values?|programs?|campaigns?|resources?|estimates?|reserves?)|previous\s+operators?|past\s+operators?|former\s+operators?"
                        r"|legacy|re-?interpret\w*|re-?logg\w*|compil\w*)\b")   # "under the historical open pit" is a place
_RE_N_PENDING = re.compile(r"(?i)\b(?:(?:assays?|results?|analys[ie]s)\s+(?:are\s+|remain\s+|still\s+)?(?:pending|awaited|outstanding)"
                           r"|pending\s+(?:assays?|results?)|awaiting\s+(?:assays?|results?)|(?:assays?|results?)\s+(?:are\s+)?expected"
                           r"|(?:anticipat(?:es?|ing)|awaits?|awaiting|expects?|expecting)\s+(?:the\s+)?(?:[\w\-]+\s+){0,3}(?:assays?|results?))\b")   # 1.0.9
_RE_N_OTHER = re.compile(
    r"(?i)\b(?:option(?:s|ed)?\s+(?:agreements?|payments?)|options\s+(?:\w+\s+){0,4}(?:to|with)\b|heads\s+of\s+agreement|letter\s+of\s+intent"
    r"|definitive\s+agreement|acqui(?:re|res|red|sition)|to\s+sell|sale\s+of|sells|staked|stakes|staking|consolidates\s+claims"
    r"|private\s+placement|financing|flow[\s\-]through|warrants?|repa(?:y|ys|id)|loans?|debentures?|financial\s+(?:results|statements)"
    r"|quarterly|quarter\s+(?:update|report|results)|q[1-4][\s\-]20\d\d|annual\s+(?:results|report|general)|md&a|outlook"
    r"|preliminary\s+economic|PEA|feasibility|resource\s+estimate|MRE|technical\s+report|management|appoint\w*|CEO|board|grant"
    r"|webinar|conference|geophysic\w*|surveys?|VTEM|electro-?magnetic|magnetic|lidar|conceptual|exploration\s+targets?|targeting"
    r"|reviews?|summar(?:y|ies|izes?|ises?)|recaps?|royalt(?:y|ies)"
    r"|identif\w*\s+(?:[\w\-]+\s+){0,5}targets?|targets?\b[^.]{0,60}\bidentified"   # 1.0.8: a new target, not a result
    # 1.0.9: targets defined / refined / generated, an agreement signed, ground consolidated, an approval or a permit,
    # a clarifying disclosure, a look back with goals
    r"|(?:defin|refin|generat|uncover|outlin|priori[tz]|delineat)\w*\s+(?:[\w\-]+\s+){0,5}targets?"
    r"|targets?\b[^.]{0,60}\b(?:defined|refined|generated|prioriti[sz]ed)"
    r"|sign(?:s|ed|ing)?\s+(?:[\w\-]+\s+){0,3}agreements?"
    r"|(?:consolidat(?:e|es|ing|ion\s+of)|consolidated\s+(?:its|the|their|our))\s+(?:[\w\-]+\s+){0,2}(?:ground|land|claims?|propert\w*|concessions?|tenure)"
    r"|land\s+lease|lease\s+status|(?:receives?|received|granted|obtains?|obtained)\s+(?:[\w\-]+\s+){0,3}(?:approvals?|permits?)"
    r"|clarif\w*\s+(?:[\w\-]+\s+){0,3}disclosures?|sets?\s+the\s+stage|goals?\s+for|year[\s\-]+in[\s\-]+review"
    # 1.0.8: land, options and agreements, geophysical anomalies, models
    r"|acres|hectares|land\s+(?:position|package|holdings?)|claims?\s+(?:block|package|group)|option(?:s|ed)\s+(?:out\s+)?(?:the\s+)?"
    r"(?:[\w\-]+\s+){0,6}(?:project|property|claims?)|(?:exploration|letter|binding|option|purchase|earn-in|definitive|access"
    r"|joint\s+venture|sale)\s+agreement|induced\s+polari[sz]ation|IP\s+(?:anomal\w*|chargeab\w*)|(?:exploration|geologic(?:al)?)\s+model)\b")
_RE_N_ECON = re.compile(r"(?i)\b(?:preliminary\s+economic|PEA|feasibility|resource\s+estimate|MRE|financial|quarter\w*|annual|md&a"
                        r"|(?:year|quarter|period|months)\s+ended"
                        r"|outlook|geophysic\w*|surveys?|compil\w*|historic\w*|previous\s+operators?)\b")
_RE_N_PROGRAM = re.compile(
    r"(?i)\b(?:complet(?:e|es|ed|ion)(?!\s+(?:[\w\-]+\s+)?(?:drill\s*)?holes?\b)|commenc\w*|start\w*|began|begun|begin\w*|resum\w*|recommenc\w*|launch\w*|mobiliz\w*|preparing"
    r"|prepares|plans?|planned|planning|upcoming|underway|under\s+way|initiat\w*|proposes?|proposed|will\s+(?:undertake|drill|commence"
    r"|begin|start|test)|to\s+(?:drill|commence|begin|start|test)|increase\s+of|expands?\s+(?:the\s+)?(?:\w+\s+)?program|progress)\b")
_RE_N_RESULTS = re.compile(
    r"(?i)\b(?:(?:drill(?:ing|hole|\s+hole)?|assay|analytical|core|lab(?:oratory)?)\s+results?|assays|assay\s+results|results\s+(?:from|of|for)\s+"
    r"(?:\w+\s+){0,4}(?:holes?|drill\w*|program(?:me)?s?|campaign)|(?:first|initial|final|additional|further|new|latest|more|positive"
    r"|encouraging|high[\s\-]grade|significant|strong|best|excellent|exceptional|remaining|maiden|second|third|fourth|fifth)\s+"
    r"(?:[\w\-]+\s+){0,2}(?<!hole\s)(?<!holes\s)(?:drill\w*\s+)?(?:results|intercepts|intersections|assays))\b")  # "hole intercepts" is a verb
_RE_N_HL_VERB = re.compile(r"(?i)\b(?:intersect\w*|intercept\w*|drills|drilled|hits?|cuts|returns?|returned|encounters?|assays?)\b")
# 1.0.9 (NEWS_V2): what a headline or statement is about when it is not new assays
# drill rigs: "a second diamond drill rig", "increases to three drills" ("drills" is a noun here, not the verb)
_RE_N_RIGS = re.compile(r"(?i)\b(?:(?:a|one|two|three|four|five|six|\d{1,2}|second|third|fourth|fifth|additional|another|extra|new|more)\s+"
                        r"(?:(?:diamond|core|RC|reverse\s+circulation|drill)\s+){0,2}(?:rigs?|drills)\b"
                        r"|(?:second|third|fourth|fifth|additional|another|extra)\s+(?:(?:diamond|core|RC)\s+)?drill\b"
                        r"(?![\s\-]+(?:holes?|program\w*|results?|intercepts?|campaign|phase|targets?|core|assays?|season)\b))")
# drilling logistics: rigs, core cut or logged, samples shipped or sent to the lab, preparations
_RE_N_LOGISTICS = re.compile(
    r"(?i)\b(?:(?:drill\s+)?rigs?\b|samples?\s+(?:[\w\-]+\s+){0,8}?(?:(?:were|have\s+been|has\s+been|are\s+being|being|are|was)\s+)?"
    r"(?:shipped|sent|delivered|submitted|dispatched)\b|(?:shipped|sent|delivered|submitted)\s+(?:[\w\-]+\s+){0,3}?(?:to|for)\s+(?:the\s+)?"
    r"(?:lab\w*|analys[ie]s|assay\w*)|core\s+(?:cutting|logging|splitting|processing)|preparations?\b)")
# an investor's update on its portfolio of equities: the results it quotes are its investees'
_RE_N_PORTFOLIO = re.compile(r"(?i)\bequit(?:y|ies)\s+(?:portfolio|holdings?|investments?)|\bjunior\s+equities\b"
                             r"|\bportfolio\s+of\s+(?:[\w\-]+\s+){0,2}(?:equities|shares|investments)\b")
# a look back: the statement reviews or summarises results already out ("review its successful 2025 results and goals")
# FIX3: "summarized in Table One" lays the new results out; it is no look back
_RE_N_LOOKBACK = re.compile(r"(?i)\b(?:summar\w*\b(?!\s+(?:in|below|herein|as\s+follows)\b)|recap\w*|look\w*\s+back|goals?\s+for|sets?\s+the\s+stage|year[\s\-]+in[\s\-]+review"
                            r"|review(?:s|ing)?\s+(?:of\s+)?(?:its|the|our|their|all|last)\b|(?:a|the)\s+review\s+of)")
# a sentence that marks its figures as released before (its holes are background wherever they recur)
_RE_N_EARLIER_WORD = re.compile(r"(?i)\b(?:previous(?:ly)?|prior|earlier|historic(?:al)?|announced|reported|released|disclosed|last\s+year)\b")
# the company's own statement of its news, in the present tense
_RE_N_STMT = re.compile(r"(?i)\b(?:is|are)\s*(?:very\s+)?(?:pleased|excited|delighted|happy|proud|thrilled)\s+to\b"   # 1.0.9: "ispleased"
                        r"|\b(?:report|announce)\s+that\b"   # 1.0.9: two companies "report that ..."
                        r"|\bwish(?:es)?\s+to\s+(?:announce|report|provide|update)\b"
                        r"|\b(?:announces|reports|provides|releases|presents|(?:announced|reported|provided)\s+today"
                        r"|today\s+(?:announced|reported|provided|released))\b")
_RE_N_ABBR = re.compile(r"(?i)\b(?:inc|ltd|corp|co|no|nos|approx|st|mt|dr|mr|ms|jr|sr|u\.s|e\.g|i\.e|vs|est|incl|ft|pty|s\.a)\.$")
_RE_N_ST_RESULTS = re.compile(r"(?i)\b(?:results?|assays?|assayed|analytical|analyses|intersections?|intercepts?|mineralized\s+intervals?"
                              r"|returned|grading|grades|values)\b")
_RE_N_ST_WEAK = re.compile(r"(?i)\b(?:intersect(?:s|ed|ing)?|encounter\w*|discover\w*)\b"
                           # FIX3: the drilling itself "has confirmed / extended" the zone
                           r"|\b(?:drill\w*|holes?)\s+(?:[\w\-]+\s+){0,4}?(?:has|have)\s+(?:now\s+|successfully\s+)?(?:confirmed|extended|expanded)\b")
_RE_N_CITE = re.compile(r"(?i)\b(?:see\s+(?:the\s+)?(?:\w+\s+){0,2}(?:news|press)\s+releases?|(?:news|press)\s+releases?\s+dated|dated\s+\w+\.?\s+\d"
                        r"|link\s+to\s+(?:[\w\-]+\s+){0,3}(?:news|press)\s+releases?"   # 1.0.9
                        r"|previously\s+(?:reported|announced|released)|as\s+(?:previously\s+)?(?:reported|announced)\s+(?:on|in)\b)")
_RE_N_NEWMARK = re.compile(r"(?i)\b(?:new|first|initial|final|latest|additional|further|remaining|recent(?:ly)?|today|herein|received"
                           r"|second|third|fourth|fifth|next|batch|round)\b")
# a lead sentence that plainly reports the release's own new assays
_RE_N_NEW_ASSAYS = re.compile(
    r"(?i)\b(?:assays?|assay\s+results|analytical\s+results|results|analyses)\b(?:\s+[\w\-]+){0,8}?\s+(?:have|has)\s+(?:now\s+)?(?:been\s+)?(?:received|returned)"
    r"|\breceived\s+(?:[\w\-]+\s+){0,3}(?:assays?|assay\s+results|analytical\s+results|results)\s+(?:for|from|of)\b"
    r"|\b(?:assays?|assay\s+results|results)\s+(?:(?:were|are|have\s+been|now)\s+)?received\s+(?:for|from)\b"
    r"|\b(?:significant\s+|selected\s+|highlight\s+)?(?:assays?|assay\s+results|drill(?:ing)?\s+results|results|intersections|intercepts)\W{0,3}"
    r"(?:\s+[\w\-]+){0,4}?\s+(?:are|is)\s+(?:highlighted|tabulated|summari[sz]ed|detailed|presented|shown|listed|as\s+follows|given)\b"
    r"|\bresults\s+(?:of|from)\s+(?:the\s+)?(?:[\w\-]+\s+){0,5}(?:drilling|holes|drill\s+program(?:me)?)\s+(?:[\w\-]+\s+){0,4}?(?:are|is)\s+"
    r"(?:as\s+follows|tabulated|shown|presented|summari[sz]ed|detailed|listed)"
    r"|\bassays?\s+(?:results\s+)?(?:for|from)\s+(?:the\s+)?(?:[\w\-]+\s+){0,2}(?:additional|new|further|first|next|remaining|latest|\d+|two|three"
    r"|four|five|six|seven|eight|nine|ten)\s+(?:[\w\-]+\s+){0,2}(?:drill\s*)?holes"
    r"|\b(?:pleased|excited|delighted|happy|proud)\s+(?:to\s+(?:report|announce|present|provide|release|share)\s+(?:on\s+)?|with\s+)(?:[\w\-]+\s+){0,6}?"
    r"(?:assays?|results|intersections|intercepts)\b"
    r"|\b(?:this|the)\s+(?:news\s+)?release\s+(?:includes|reports|presents|contains|provides)\s+(?:[\w\-]+\s+){0,4}(?:results|assays)\b"
    r"|\b(?:latest|new|recent|additional|further)\s+(?:[\w\-]+\s+){0,2}results\s+(?:have|has|are|were|include|show|confirm|continue\w*|returned|from)\b"
    r"|\b(?:drilling|program(?:me)?|holes?)\s+(?:has|have)\s+returned\s+(?:[\w\-]+\s+){0,4}(?:intersections|intercepts|results|assays|grades)"
    # FIX3: "Preliminary results include 8 m @ 4.6 g/t", "preliminary results already successfully returning high grade
    # intercepts", "Significant mineralized intercepts include:", "New highlights include:", "The update includes drilling
    # results", "Assay highlights from hole AB-01:", "Table 1. Drill hole assay data from the Alpha drilling"
    r"|\b(?:preliminary|initial|first|final)\s+(?:[\w\-]+\s+){0,2}results\s+(?:include|show|confirm|have|has|are|were"
    r"|(?:already\s+|successfully\s+){0,2}(?:returning|returned))\b"
    r"|\b(?:significant|selected|key|notable|new|highlighted)\s+(?:[\w\-]+\s+){0,2}(?:intercepts|intersections|assays|highlights)"
    r"\W{0,3}(?:\(\d\)\s*)?(?:include|includes|included)\b"
    r"|\b(?:this|the)\s+(?:news\s+release|release|update)\s+(?:includes|reports|presents|contains)\s+(?:[\w\-]+\s+){0,4}(?:results|assays)\b"
    r"|\bassay\s+highlights\s+(?:from|for|of)\s+(?:drill\s*)?holes?\b"
    r"|\btable\s+\d+\s*[.:\-]\s*(?:[\w\-]+\s+){0,2}(?:drill\s*hole\s+)?assay\s+(?:data|results)\b")
# background in a lead sentence: somebody else's, older, restated, pending or planned work
_RE_N_BG = re.compile(
    r"(?i)\b(?:historic(?:al)?\s+(?:[\w\-]+\s+){0,2}(?:drill\w*|holes?|results?|intercepts?|intersections?|assays?|data|work|sampl\w*|values?"
    r"|grades?|programs?|campaigns?|core|trench\w*)|previous(?:ly)?|past\s+(?:operators?|drilling|work|owners?)|former\s+(?:operators?|owners?)|see\s+(?:\w+\s+){0,2}(?:news|press)"
    r"|news\s+release\s+dated|to\s+date|pending|awaits?|awaiting|expected|anticipated|will|plans?|planned|last\s+year'?s?"
    r"|(?:prior|earlier)\s+(?:drill\w*|results?|releases?|programs?|work|operators?|holes?)|channel|chip|grab|trench\w*|soil|surface\s+sampl\w*"
    r"|re-?sampl\w*|re-?assay\w*|re-?logg\w*|compilation|conceptual|visual\w*|announced\s+on|reported\s+on\s+\w+\s+\d|anticipat\w*"
    r"|(?:company|it|they|we)\s+(?:announced|reported|released)|(?:19|20)\d\d\s+(?:news|press)\s+release|preliminary\s+economic|PEA"
    r"|financial|quarter\w*|geophysic\w*|survey"
    r"|(?:in|over|during)\s+the\s+(?:last|past|previous)\s+(?:\d+|\w+)\s+(?:months?|years?|quarters?)"
    r"|(?:highest|best|widest|thickest)[\s\-]+(?:grade\s+)?(?:intercepts?|intersections?|results?)\s+(?:in|of|to)\b)\b")
# a hole with a graded interval, in a lead sentence (used only when neither the headline nor the statement says)
_RE_N_HIT = re.compile(r"(?i)\b(?:drill\s*holes?|holes?|DDH|drillholes?|boreholes?|drilling|intersection|intercept)\b.{0,160}?\b(?:intersect\w*|intercept\w*|return\w*|cut|cuts"
                       r"|assay\w*|grad\w*|record\w*|yield\w*|averag\w*|contain\w*)\b"
                       # FIX3: the other order, "... was intersected by drilling"
                       r"|\b(?:intersect\w*|intercept\w*)\s+(?:by|in|with)\s+(?:the\s+)?(?:[\w\-]+\s+){0,2}(?:drill\w*|holes?|boreholes?)\b")


# FIX3: the length in other units may sit between the length and its grade ("7.47 metres (24.5 feet) at 25.55% zinc"), and the grade
# may be written out ("25.07 grams per tonne (g/t) over 2.1 metres")
_RE_N_FIG = re.compile(r"(?i)\d[\d,]*(?:\.\d+)?[\s\-]*(?:m\b|metres?|meters?|ft\b|feet)\s*(?:\(\s*[\d.,]+\s*(?:m|metres?|meters?|ft|feet)\s*\)\s*)?(?:@|at|of|grading|averaging|assaying)\s*\d[\d,]*(?:\.\d+)?\s*"
                       r"(?:g/t|gpt|%|ppm|ppb|oz/t|grams)|\d[\d,]*(?:\.\d+)?\s*(?:g/t|gpt|%|ppm|ppb|oz/t|grams?\s+per\s+tonne)[^.;]{0,50}?\b(?:over|across)\s+\d")
_RE_N_HOLE_ID = re.compile(r"\b(?:[Hh]ole|DDH|[Dd]rill\s*hole|[Dd]rillhole)\s+[A-Z0-9][\w\-]*\d|\((?:hole\s+)?[A-Z]{1,8}[\-_]?\d[\w\-]*\)"
                           r"|\b[A-Z]{1,8}\d{0,4}[\-_]\d{2,}[\w\-]*\s*[:\-\u2013]")
_RE_N_DATE = re.compile(r"(?i)\b(?:(?P<d1>\d{1,2})\s?(?:st|nd|rd|th)?\s+(?P<m1>" + MONTHS + r")\.?,?\s+(?P<y1>(?:19|20)\d\d)"
                        r"|(?P<m2>" + MONTHS + r")\.?\s+(?P<d2>\d{1,2})\s?(?:st|nd|rd|th)?,?\s+(?P<y2>(?:19|20)\d\d))\b")


def _n_earlier_date(s, rdate):
    """The sentence dates something before the release ('(August 8, 2018 News Release)', 'On September 8, 2025, ...')."""
    for d in _RE_N_DATE.finditer(s):
        dd = (int(d.group("y1") or d.group("y2")), _month(d.group("m1") or d.group("m2")), int(d.group("d1") or d.group("d2")))
        if rdate and dd < tuple(rdate):
            return True
    return False


_RE_N_CONTINUES = re.compile(r"(?i)^\W*(?:other|also|in\s+addition|additionally|it|they|(?:this|these|that|those|the\s+same|the)\s+(?!year\b)(?:[\w\-]+\s+)?"
                             r"(?:holes?|intercepts?|intersections?|results?|intervals?|drilling|assays?)"
                             r"|(?:all|both|each|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\s+(?:of\s+the\s+)?(?:[\w\-]+\s+)?"
                             r"(?:drill\s*)?holes"   # 1.0.9: "Five drill holes tested ..." after a cited sentence
                             # FIX3: "The most significant intercept from Hole 001-97 returned ..." after a cited sentence
                             r"|(?:the\s+)?(?:most\s+significant|best|highest[\s\-]grade|strongest)\s+(?:[\w\-]+\s+)?(?:intercepts?|intersections?|results?|holes?))\b")


def _n_sentences(s):
    out, start = [], 0
    for m in re.finditer(r"(?<=[.;!?])\s+(?=[A-Z0-9\"\u201c(\u2022])|\s[\u2022\u25cf\u25aa\u25e6\uf0b7\uf0a7]\s|\s+o\s+(?=\d)", s):
        if _RE_N_ABBR.search(s[max(0, m.start() - 6):m.start()]) or re.search(r"(?i)\b(?:table|figure|fig)\s+\d{1,2}\.$", s[max(0, m.start() - 10):m.start()]):   # FIX3: "Table 1. Drill hole assay data"
            continue
        out.append(s[start:m.start()])
        start = m.end()
    out.append(s[start:])
    return [x for x in out if x.strip()]


def _n_body(hl, t):
    """The body with a copy of the headline near its top removed (a copy further down is not the headline)."""
    body = " ".join((t or "")[:6000].split())
    words = re.findall(r"\w+", hl or "")
    if len(words) >= 4:
        m1 = re.search(r"(?i)" + r"\W+".join(map(re.escape, words[:4])), body[:400])
        if m1:
            m2 = re.search(r"(?i)" + r"\W+".join(map(re.escape, words[-4:])), body[m1.start():m1.start() + len(hl) + 200])
            if m2:
                return body[m1.start() + m2.end():]
    return body


def _n_statement(body, nth=0):
    """The company's own statement of its news: from its 'is pleased to report / announces / provides' on, cut before
    the project's description ('located ...'). nth=1 (1.0.9): a second statement within two sentences of the first
    ("... a major milestone. The Company is pleased to announce that it has completed the final option payments")."""
    first = None
    for i, s in enumerate(_n_sentences(body[:3500])):
        m = _RE_N_STMT.search(s)
        if m and first is not None and i - first > 2:
            return ""
        if m and first is None and nth:
            first = i
            continue
        if m and first is not None:
            m = re.search(r"(?i)\b(?:is|are)\s*(?:also\s+)?(?:very\s+)?(?:pleased|excited|delighted|happy|proud|thrilled)\s+to\b", s)
            if not m or re.search("[\"\u201c\u2018]", s[:m.start()]):
                continue   # the second statement is the company's own, not a quotation or a "press releases dated" citation
        if m:
            return _n_cut(s[m.start():])
    if not nth and first is None:
        # 1.0.9: no "is pleased to" -- the company's defined name is followed by its news ("(the "Company" or "X")
        # plans to commence ...", "..., has completed the first 6 holes ...")
        for s in _n_sentences(body[:1500])[:3]:
            m = _RE_N_DEFINED.search(s)
            if m:
                return _n_cut(s[m.end():])
    return ""


_RE_N_DEFINED = re.compile("\\((?:the\\s+)?[\"\u201c\u2018\\s]*(?:Company|Corporation|Issuer)\\b[^()]{0,80}\\)(?:\\s*\\([^()]{0,80}\\))*\\s*,?\\s*(?=[a-z])")


def _n_cut(st):
    # cut before the project's description and before a clause about an earlier hole ("... above the
    # discovery hole (AB-18-031) that intersected 4.1 m grading 38.2% ZnEq")
    cut = re.search(r"(?i)[,(]?\s+\b(?:located|situated)\b|,\s+which\s+(?:is|was|lies)\b"
                    r"|\b(?:that|which)\s+(?:previously\s+|had\s+)?(?:intersected|returned|graded|assayed|yielded)\b"
                    r"|,\s+where\b", st)   # "... drilling has started at Alpha, where hole AB-25-05 returned ..."
    return st[:cut.start()] if cut else st[:350]


def _n_old_year(s, year):
    return bool(year) and any(int(y) <= year - 2 for y in re.findall(r"(?<![\d\-/])((?:19|20)\d\d)(?![\d\-/])", s))


def _n_headline(hl, year):
    """'results', 'weak' (a drill verb without a grade or a results phrase), 'not' (other news, or news that is not an
    assay), or None. The reason word comes with 'not'."""
    clauses = [c for c in _RE_N_SPLIT.split(hl or "") if c and c.strip()]
    kinds = []
    prev_c = ""
    for c in clauses:
        fig = _RE_N_GRADE.search(c) and (_RE_N_LEN.search(c) or re.search(r"(?i)\bassays?\b", c))
        na = _RE_N_NOT_ASSAY.search(c)
        if na and fig and na.start() > max(m.end() for m in list(_RE_N_GRADE.finditer(c)) + list(_RE_N_LEN.finditer(c))) + 30:
            na = None   # FIX3: "Intersects 30.7m of 1.05% Cu ... at the Alpha Deposit Significant visual sulfides encountered in
            #             all four holes": a sub-headline run on after the assayed figure
        if na:
            kinds.append(("not", "visual" if re.search(r"(?i)visu|logg|logs?\b|preliminary", c) else "instrument"))
        elif _RE_N_SURFACE.search(c) and not _RE_N_DRILL.search(c):
            kinds.append(("not", "surface"))
        elif _RE_N_HIST.search(c) and not re.search(r"(?i)\b(?:new|twin\w*|confirm\w*|beneath|below|extend\w*)\b", c):
            kinds.append(("not", "historical"))
        elif _n_old_year(c, year):
            kinds.append(("not", "historical"))
        elif _RE_N_PENDING.search(c):
            kinds.append(("not", "pending"))
        elif fig and not _RE_N_ECON.search(c):
            if (kinds and kinds[-1][0] == "not" and not _RE_N_DRILL.search(c)
                    and not (kinds[-1][1] == "plan" and re.search(r"(?i)\b(?:complet|conclu|finish)\w*", prev_c))):   # FIX3
                kinds.append(kinds[-1])   # "Reports Historic Drill Results; Includes 4.66 m of 3.07% Copper"
                # (but "Completes 2021 Drilling at X; LBP380: 1.52 g/t Au over 30.5 m" gives the program's results)
            else:
                kinds.append(("results", None))
        elif _RE_N_RESULTS.search(c) and not _RE_N_PROGRAM.search(c) and (not _RE_N_ECON.search(c) or _n_results_beside_corporate(c)):
            kinds.append(("results", None))
        elif ((_RE_N_HL_VERB.search(_RE_N_RIGS.sub(" ", c))   # 1.0.9: "three drills"
               or re.search(r"(?i)\bdrill\w*\s+(?:[\w\-]+\s+){0,2}discovers?\b", c))   # FIX3: "Phase II Drilling Discovers New Zone"
              and not _RE_N_PROGRAM.search(c)):
            kinds.append(("weak", None))
        elif _RE_N_OTHER.search(c) or _RE_N_PROGRAM.search(c) or _RE_N_LOGISTICS.search(c) or _RE_N_RIGS.search(c):
            kinds.append(("not", "plan" if (_RE_N_PROGRAM.search(c) or _RE_N_LOGISTICS.search(c) or _RE_N_RIGS.search(c))
                          else "not_results"))
        else:
            kinds.append((None, None))
        prev_c = c
    figs = any(_RE_N_GRADE.search(c) and _RE_N_LEN.search(c) for c in clauses)
    if not figs and not any(k == "results" for k, _ in kinds):
        # "... hole intercepts polymetallic mineralization - assays pending": the claim is a visual one (but "Full Assay
        # Results from TADD-278; Second Hole Results Pending" reports the first hole)
        for k, why in kinds:
            if k == "not" and why in ("pending", "visual", "instrument"):
                return "not", why
    if any(k == "results" for k, _ in kinds):
        # a surface-sample headline gives its figure without a drill word ("Samples 26.67 g/t Gold over 2 Metres")
        if not any(_RE_N_DRILL.search(c) for c in clauses) and any(w == "surface" for _, w in kinds):
            return "not", "surface"
        return "results", None
    for want in ("weak", "not"):
        for k, why in kinds:
            if k == want:
                return k, why
    return None, None


# FIX3: a claim of the company's own results ahead of a citation in its statement ("announce diamond drill results for one
# hole from the recently completed (See News Release: June 11, 2026) program", "assay results from the previously
# reported VG intersection"): the citation is about the program or an earlier, visual report, not these results
_RE_N_ST_CLAIM = re.compile(r"(?i)\b(?:results?|assays?|assayed|analytical|analyses|intersections?|intercepts?|grades)\b"
                            r"|\b(?:intersect(?:s|ed)?|encountered)\b")
# a citation of the results themselves: "results previously announced", "results that were reported"
_RE_N_CITED_CLAIM = re.compile(r"(?i)\b(?:results?|assays?|intercepts?|intersections?)\s*,?\s*(?:(?:that|which)\s+(?:were|was|have\s+been)\s+)?$")
# FIX3: soil or geophysical anomalies that targeted the drilling are no surface samples
_RE_N_ANOMALY = re.compile(r"(?i)\b(?:soils?|till|geochemi\w*|geophysic\w*|surface)\s+(?:(?:and|or|&)\s+[\w\-]+\s+)?(?:anomal\w*|targets?)\b")
# FIX3: an update on drilling "progress" or on drilling "completed" is an update, not a plan
_RE_N_UPDATE_DRILL = re.compile(r"(?i)\bupdate\s+(?:on|from|of|regarding)\s+(?:[\w\-]+\s+){0,6}?(?:drill\w*|exploration)\b")


def _n_strip_cite(st):
    """The statement without the citations that follow the company's own claim of results (FIX3): a bracketed citation
    goes whole, any other to the end of its clause."""
    if re.search(r"(?i)\b(?:new|today|herein|latest|additional)\b", st) or not _RE_N_DRILL.search(st):
        return st
    for _ in range(4):
        m = _RE_N_CITE.search(st)
        if not m:
            break
        pre = st[:m.start()]
        if not (_RE_N_ST_CLAIM.search(pre) or _RE_N_ST_WEAK.search(pre)) or _RE_N_CITED_CLAIM.search(pre):
            break
        o, c = pre.rfind("("), pre.rfind(")")
        if o > c and ")" in st[m.end():]:
            st = st[:o] + " " + st[st.index(")", m.end()) + 1:]
        else:
            e = re.search(r"[,;.]\s|$", st[m.end():])
            st = pre + " " + st[m.end() + e.start():]
    return st


def _n_statement_kind(st):
    if not st:
        return None, None
    st = _n_strip_cite(st)   # FIX3
    if _RE_N_CITE.search(st) and not re.search(r"(?i)\b(?:new|today|herein|latest|additional)\b", st):
        return "not", "previously_reported"
    st = _RE_N_ANOMALY.sub(" ", st)   # FIX3
    na = _RE_N_NOT_ASSAY.search(st)
    if na and _RE_N_ST_RESULTS.search(st[:na.start()]) and _RE_N_DRILLW.search(st[:na.start()]):
        na = None   # "initial results from ... four drill holes ... and the mobilization of a mobile XRF scanner"
    if na and not re.search(r"(?i)\b(?:assays?|analytical|laborator\w*)\b", st):
        return "not", "visual" if re.search(r"(?i)visu|logg|logs?\b|preliminary", st) else "instrument"
    if _RE_N_SURFACE.search(st) and not _RE_N_DRILLW.search(st):
        return "not", "surface"
    if re.search(r"\b(?i:that)\s+[A-Z](?:[^.]|\.(?=[,)\s]*[(,\u201c\"a-z])){0,140}?\b(?i:announced|released)\b(?!\s+today)", st):
        return "not", "previously_reported"  # "... is pleased to announce that <partner>, the optionor, announced results of ..."
    if re.search(r"(?i)\b(?:has\s+|have\s+)?released\s+(?:[\w\-]+\s+){0,3}(?:drill\s*holes|drillholes|holes)\b", st):
        return "results", None  # "announces <subsidiary> has released three drillholes ..."
    if _RE_N_PORTFOLIO.search(st):
        return "not", "investee"   # 1.0.9: an investor's portfolio update quotes its investees' results
    if _RE_N_ST_RESULTS.search(st):
        if _RE_N_HIST.search(st) and not re.search(r"(?i)\b(?:new|today|herein|latest|additional|first)\b", st):
            return "not", "historical"
        econ = _RE_N_ECON.search(st)
        named = find_holes(st)   # FIX3: "assay results from drill holes FCG25-31 and FCG25-32 ... preliminary economic stage"
        if econ and not (_RE_N_DRILLW.search(st) and _RE_N_NEWMARK.search(st)) and not (named and named[0]["pos"] < econ.start()):
            return "not", "not_results"
        if _RE_N_LOOKBACK.search(st) and not re.search(r"(?i)\b(?:final|new|initial|first|latest|additional|analytical)\b", st):
            return "not", "recap"   # 1.0.9: also "review its ... results", "goals for", "sets the stage"
        return "results", None
    if re.search(r"(?i)\breport\w*\s+on\s+(?:[\w\-]+\s+){0,6}(?:drill\w*|intersections?|holes?)\b", st):
        return "results", None
    if _RE_N_ST_WEAK.search(st) and _RE_N_DRILL.search(st):
        return "weak", None
    if _RE_N_PROGRAM.search(st) or _RE_N_LOGISTICS.search(st) or _RE_N_RIGS.search(st):   # 1.0.9: rigs, samples shipped
        if (_RE_N_UPDATE_DRILL.search(st) and not _RE_N_LOGISTICS.search(st) and not _RE_N_RIGS.search(st)
                and all(re.match(r"(?i)progress|completed$", m.group(0)) for m in _RE_N_PROGRAM.finditer(st))):
            return None, None   # FIX3: "an update on the recent exploration drilling progress", "... drilling activities completed"
        return "not", "plan"
    if _RE_N_OTHER.search(st):
        return "not", "not_results"
    return None, None


def _n_lead_reports(body, rdate, loose):
    """A lead sentence, not background, that reports new assays (loose: or a hole's graded interval)."""
    year = rdate[0] if rdate else None
    prev_bg, lead_in = False, ""
    sents = _n_sentences(body[:3500])
    bg_holes = set()   # 1.0.9: holes a sentence cites as released before
    # 1.0.9: ids that carry the year with no separator ("OL20004" in "drilling in 2020 ... DDH OL20004"): a sentence that
    # pairs such an id with its year teaches the form; "OL21019" in a 2025 release is then an earlier program's hole
    cy = {m.group(1) for s in sents for y in re.findall(r"(?<![\d\-/])(?:19|20)(\d\d)(?![\d\-/])", s)
          for m in re.finditer(r"\b([A-Z]{1,4})" + y + r"\d{3}\b", s)}

    def _old_id(h):
        m = re.fullmatch(r"([A-Z]{1,4})(\d{2})\d{3}", h)
        return _old_hole(h, rdate) or bool(m and year and m.group(1) in cy and 2000 + int(m.group(2)) < year - 1)
    carry, carry_i = [], -9   # FIX3: the hole a lead sentence names stays with the figures of the next two
    for i, s in enumerate(sents):
        nxt = sents[i + 1] if i + 1 < len(sents) else ""
        sh = {norm_hole(h["id"]) for h in find_holes(s)}

        def _bg(x):
            x = re.sub(r"(?i)\b(?:no|never|not|without)\s+(?:\w+\s+){0,2}(?:previous(?:ly)?|prior|historic\w*)\s+\w+", " ", x)   # FIX3: "no previous drilling"
            earlier_ = bool(_n_old_year(x, year) or _RE_N_CITE.search(x) or _n_earlier_date(x, rdate))
            return earlier_, bool(
                _RE_N_BG.search(x) or earlier_ or (prev_bg and _RE_N_CONTINUES.search(x))
                or (sh and sh <= bg_holes)   # 1.0.9: "Discovery hole AB21069 intersected ..." after "(as reported January 20)"
                # 1.0.9: the next sentence is the citation of this one ("... over 54.6 m. (see press release of June 19)")
                or bool(re.match(r"(?i)\W{0,3}\(?\s*(?:see|refer|link|as\s+(?:previously\s+)?(?:reported|announced))\b", nxt)
                        and (_RE_N_CITE.search(nxt) or _n_earlier_date(nxt, rdate))))
        earlier, bg = _bg(s)
        # FIX3: a table run together into one long "sentence" ("Significant assays are tabulated below: Hole | From | ...")
        # is judged by its opening; a footnote far down it ("... is expected to be +95%") says nothing about the claim
        if (bg and len(s) > 500 and _RE_N_NEW_ASSAYS.search(s[:500]) and not _bg(s[:500])[1]
                and not (sh and all(_old_id(h["id"]) for h in find_holes(s[:500])))):
            return True
        if bg and sh and (earlier or _RE_N_EARLIER_WORD.search(s)):
            bg_holes |= sh
        prev_bg = bg
        if bg:
            continue
        if _RE_N_NEW_ASSAYS.search(s) and not (sh and all(_old_id(h["id"]) for h in find_holes(s))):   # FIX3: "AB22008: 6.75 m" in 2025
            return True
        if sh and _RE_N_HIT.search(s):
            carry, carry_i = [h["id"] for h in find_holes(s)], i
        ids = [h["id"] for h in find_holes(s)] if loose else []
        ids += [m.group(0) for m in re.finditer(r"\b([A-Z]{1,4})\d{5}\b", s) if loose and m.group(1) in cy and m.group(0) not in ids]
        if (loose and _RE_N_GRADE.search(s) and _RE_N_LEN.search(s)
                and not (year and re.search(r"(?i)\b(?:in|during|from)\s+(?:early\s+|late\s+|mid-?)?%d\b" % (year - 1), s))   # 1.0.9: "from"
                and not (ids and all(_old_id(h) for h in ids))      # "AB21026 returned 29.44m @ 1.30 g/t" in 2025
                and (_RE_N_HIT.search(s) or (_RE_N_FIG.search(s) and (_RE_N_HOLE_ID.search(s) or find_holes(s)
                                                                       or (lead_in and find_holes(lead_in))
                                                                       or (carry and i - carry_i <= 2
                                                                           and not all(_old_id(h) for h in carry)))))):
            return True
        lead_in = s if (len(s) < 120 and re.search(r":\s*$", s)) else ""   # "Drillhole BHE26-01 returns:" heads the next items
    return False


_RE_N_COMMENTARY = re.compile(r"(?i)\b(?:news\s+commentary|paid\s+(?:for|advertis\w*|commentary|promotion)|sponsored\s+content"
                              r"|disseminated\s+on\s+behalf|compensated\s+(?:by|for))\b")


def release_news(hl, t, rdate, hl_figure=False):
    """(kind, reason): kind 'results', 'unclear' or 'not' -- what the release itself announces (see NEWS_V1 above).
    hl_figure: the reader accepted a figure from the headline itself."""
    body = _n_body(hl, t)
    if not rdate:
        # 1.0.9: no dateline: the latest year the headline or the statement names stands in (as of its first day)
        yrs = [int(y) for y in re.findall(r"(?<![\d\-/])((?:19|20)\d\d)(?![\d\-/])", (hl or "") + " " + _n_statement(body))]
        rdate = (max(yrs), 1, 1) if yrs else None
    year = rdate[0] if rdate else None
    if _RE_N_COMMENTARY.search(t[:3000]):
        return "not", "investee"   # a paid piece restating another company's release
    hk, hwhy = _n_headline(hl, year)
    if hl_figure and hk in (None, "weak"):
        hk = "results"   # "X Drills 5.3 Grams Au over 3.8 Meters": the grammar read a figure the clause test did not
    st = _n_statement(body)
    sk, swhy = _n_statement_kind(st)
    if sk is None and st:
        st2 = _n_statement(body, 1)   # 1.0.9: a vague first statement ("a major milestone") is explained by the next one
        if st2:
            st, (sk, swhy) = st2, _n_statement_kind(st2)
    elif sk == "not" and swhy in ("plan", "not_results"):
        # FIX3: "... supports an increase to the exploration target. Additionally, the Company is pleased to release
        # updated exploration results": a second statement of the company's own new results stands
        st2 = _n_statement(body, 1)
        if st2 and _n_statement_kind(st2)[0] == "results":
            st, (sk, swhy) = st2, ("results", None)
    if sk == "not" and swhy in ("visual", "instrument") and hk != "results":
        return "not", swhy
    if hk == "not" and hwhy in ("visual", "instrument", "pending") and sk != "results":
        return "not", hwhy
    if sk == "not" and swhy in ("historical", "previously_reported", "surface") and not _RE_N_DRILLW.search(hl or ""):
        return "not", swhy   # "Reports 108.36 g/t Gold over 7 Metres ..." / "pleased to provide ... historical results"
    if (hk == "not" and hwhy in ("surface", "historical") and sk == "results" and not _RE_N_DRILLW.search(st)
            and not _RE_N_DRILL.search(hl or "")):
        return "not", hwhy   # 1.0.9: "Reports Underground Sampling Results ..." + "pleased to announce results from its program"
    if hk == "results" or sk == "results":
        return "results", None
    if hk == "not" or sk == "not":
        why = (hwhy if hk == "not" else swhy) or "not_results"
        if why not in ("plan", "not_results"):
            return "not", why        # the news is named as something that is not a new assay
        if hk == "not" and hwhy == "not_results" and sk in ("not", None):
            return "not", why        # an option, a sale, a financing, a management change, a PEA, a quarterly report ...
        if hk == "weak" or sk == "weak":  # "... and Continues to Intersect Significant Gold in Drilling"
            return ("results", None) if _n_lead_reports(body, rdate, True) else ("not", why)
        return ("results", None) if _n_lead_reports(body, rdate, False) else ("not", why)
    if not _n_statement(body) and hk != "not" and len(body) < 700:
        return "results", None   # a fragment with no statement of its own to go by: the figures are judged as before
    return ("results", None) if _n_lead_reports(body, rdate, True) else ("unclear", "no_new_results")


def analyse(headline: str, body: str) -> dict:
    hl = repair(headline or "")
    raw_body = repair(body or "")
    rdate = dateline(raw_body)
    ld = D.lede(raw_body)
    th = D._prep(hl)
    t = D._prep(ld)
    result = {"is_result": False, "reason": None, "intervals": [], "top": None, "project": None,
              "project_rank": None, "release_date": rdate}

    # a release that announces a plan, or says results are still pending, and carries no number of its own
    _body_all = D.find_intercepts(ld)
    _dom = dominant_precious(D.find_intercepts(hl) + _body_all, t)
    hl_ints = _one_length_per_grade(fix_metals(D.find_intercepts(hl), D._prep(hl), _dom), D._prep(hl))
    # 1.0.1: a plan / pending / corporate headline no longer ends the analysis on its own. The body is read, and the
    # release keeps a row only if its own opening says it reports new results ("Completes Drill Program" releases that
    # announce final assays, "Assay Results Still Pending" releases that report the first holes, financing + results).
    hl_kind = None
    if not hl_ints and D._RE_PLAN_ONLY.search(hl) and not D._RE_RESULTS_STRONG.search(hl):
        hl_kind = "plan"
    elif not hl_ints and _RE_CAMPAIGN_HEADLINE.search(hl) and not _RE_RESULTS_WORDS.search(hl):
        hl_kind = "plan"
    elif not hl_ints and _headline_pending(hl):
        hl_kind = "pending"
    elif not hl_ints and _RE_NOT_RESULTS_HEADLINE.search(hl) and not _RE_RESULTS_WORDS.search(hl):
        hl_kind = "not_results"
    if re.search(r"(?i)\bitems\s+per\s+page\b|\bnews\s+listings\s+will\s+update\b|\bmaking\s+a\s+selection\s+with\s+these\s+dropdown", ld[:3000]):
        result["reason"] = "not_results"  # 1.0.2: a newswire category page ("Mining & Metals") captured instead of a release (AUAU.V)
        return result
    if not hl_ints and _RE_EVENT_HEADLINE.search(hl):
        result["reason"] = "not_results"  # a webinar invitation or an investment update recaps results released elsewhere
        return result
    if hl_kind and not _new_results_lede(D._prep(D.lede(raw_body))[:2500]):
        result["reason"] = hl_kind
        return result
    hl_drill = (bool(hl_ints) or bool(_RE_DRILL_WORD.search(th)) or bool(_RE_RESULTS_WORDS.search(th))
                or len(re.findall(r"[A-Za-z]+", hl)) < 5 or bool(re.search(r"(?i)news\s+release", hl)))
    lede_drill = bool(_RE_DRILL_WORD.search(t))

    release_reason = None
    # 1.0.2: "First Results from Underground Drilling Program" reports the program's results; it is not a plan (PINN.V)
    th_np = _RE_PLAN_PHRASE.sub(lambda m: m.group(0) if re.search(r"(?i)\b(?:results?|assays?|intercepts?|holes?)\s+(?:from|of)\s+(?:the\s+|its\s+|our\s+)?(?:[\w\-]+\s+){0,3}$",
                                                               th[max(0, m.start() - 60):m.start()]) else " ", th)
    # 1.0.1: "Significantly Increasing Size of Previously Announced Interval" is about the new result
    th_np = re.sub(r"(?i)\b(?:increas|expand|extend|improv|upgrad|enlarg)\w*\s+(?:the\s+)?(?:size|length|grade|width)?\s*(?:and\s+\w+\s+)?(?:of\s+)?(?:the\s+|a\s+)?"
                   r"previously\s+(?:announced|reported|released)", " ", th_np)
    if _RE_XRF.search(th):
        release_reason = "xrf"
    elif not _RE_DRILL_WORD.search(th_np) and context_reason(re.sub(r"^\W*\w+", "", th_np, count=1), None) in ("surface", "historical"):
        release_reason = context_reason(re.sub(r"^\W*\w+", "", th_np, count=1), None)  # "Highlights Historical Soil Anomalies"
    elif not _RE_DRILL_WORD.search(th_np) and _RE_SAMPLES_VERB.search(th):
        release_reason = "surface"  # "Tocvan Samples High-Grade Gold and Silver 6-kilometers from Pilar"
    elif _RE_HIST_DRILL_HEADLINE.search(th) and not re.search(r"(?i)\btwin", th):
        release_reason = "historical"  # "... Results Including 3.51 g/t AuEq over 93 metres in Historic Drilling"
    elif not _RE_DRILL_WORD.search(th) and any(not re.search(r"(?i)drill|near[\s\-]+surface", m.group(0)) for m in _RE_SURFACE_INTRO.finditer(t[:1800])):
        release_reason = "surface"
    elif any(not re.search(r"(?i)\b(?:between|near|beside|adjacent\s+to|around|among|from|of|below|beneath|under|twin\w*|follow\w*\s+up\s+on)\s+(?:\w+\s+){0,2}$",
                           t[max(0, m.start() - 40):m.start()])
             for m in _RE_PRIOR_OPERATOR_RELEASE.finditer(t[:2500])):  # 1.0.1: "tested the vein between drill holes completed by the previous operator"
        release_reason = "historical_operator"
    elif _RE_FOLLOW_UP_HEADLINE.search(th) and _RE_PLAN_PHRASE.search(th) and not _RE_DRILL_VERB_HEADLINE.search(th):
        release_reason = "previously_reported"  # "Announces Drill Program to Follow up on Saddle Zone's Recent 5.94% CuEq over 11 m"
    elif _RE_INVESTEE.search(th) or _RE_INVESTEE_HEADLINE.search(th) or _RE_INVESTEE.search(t[:1500]):
        release_reason = "investee"  # results of a company this one holds shares in
    elif _RE_RECAP_HEADLINE.search(th) or _RE_RECAP_BODY.search(t[:3000]):
        release_reason = "recap"
    program_years = {int(m.group(1)) for m in _RE_PROGRAM_YEAR.finditer(t)}
    hl_years = {int(y) for y in re.findall(r"\b((?:19|20)\d\d)\b", th)} if hl_drill else set()

    def reason_for(ctx, head="", pos=None):
        r = context_reason(ctx, rdate, program_years, pos, hl_years)
        if r is None and head:
            r = context_reason(head, rdate, program_years, len(head), hl_years)  # 1.0.2: the list items follow their lead-in
        return r

    spans = units(t)
    copy = _headline_copy(t, hl)
    if copy:
        spans = _split_spans(spans, copy)
    holes = find_holes(t)
    text_ints = _one_length_per_grade(fix_metals(_body_all, t, _dom), t)
    blanked = _RE_EQ_PAREN.sub(lambda m: m.group(1) + " " * (len(m.group(0)) - len(m.group(1))), t)
    blanked = _RE_WIDTH_NOTE.sub(lambda m: " " * len(m.group(0)), blanked)
    if blanked != t:
        noted = [m.span() for m in _RE_WIDTH_NOTE.finditer(t)]
        if noted:  # the length inside "(5.78m etw)" is a width, not the interval
            text_ints = [x for x in text_ints if not any(a <= x["pos"] + 200 and _width_from_note(t, x, a, b) for a, b in noted)]
        for iv in fix_metals(D.find_intercepts(blanked), blanked, _dom):  # "3.51 g/t AuEq (1.08 g/t Au & 0.69% Sb) over 93 metres"
            if not any(_same(x, iv) and abs(x["pos"] - iv["pos"]) < 5 for x in text_ints):
                text_ints.append(iv)
        text_ints.sort(key=lambda x: x["pos"])
    for iv in text_ints:
        iv["src"] = "text"
        tail = t[max(0, iv["pos"] - 90):iv["pos"]]
        iv["including"] = _is_sub(tail) and not _RE_WITHIN_TAIL.search(tail)
        if _RE_WITHIN_TAIL.search(tail):
            prev = [x for x in text_ints if x["pos"] < iv["pos"] and iv["pos"] - x["pos"] < 200]
            if prev:
                ln = max(prev, key=lambda x: x["pos"])["length_m"]
                for x in prev:
                    if abs(x["length_m"] - ln) < 0.01 and x["length_m"] < iv["length_m"]:
                        x["including"] = True  # "4.60 g/t Au over 5.9m within 0.64 g/t Au over 55.4m"
        ctx, head, pin = _unit_ctx(t, spans, iv["pos"])
        iv["reason"] = release_reason or reason_for(ctx, head, pin)
        _rule(iv, "context")
        if iv["reason"] is None:
            lh = _line_heading(t, iv["pos"])
            if lh and context_reason(lh, rdate, program_years, exempt_years=hl_years) in ("surface", "historical", "xrf"):
                iv["reason"] = context_reason(lh, rdate, program_years, exempt_years=hl_years)
                _rule(iv, "line_heading")
        if iv["reason"] is None:
            iv["reason"] = _local_reason(t, spans, iv, rdate, reason_for)
            _rule(iv, "local")
        if iv["reason"] is None and re.search(r"(?i)^[^.;]{0,40}?\bover\s+[\d.,]+\s*(?:m|metres?|meters?|km)\s+(?:of\s+)?strike", t[iv["pos"]:iv["pos"] + 80]):
            iv["reason"] = "strike_length"
            _rule(iv, "strike")
        if iv["reason"] is None and _RE_PLAN_CTX.search(t[max(0, iv["pos"] - 250):iv["pos"]]):
            iv["reason"] = "reference_hole"  # "drilling is planned ... to test the BIF intersected in RC hole KR-26-021 (9 m @ 4.04 g/t"
            _rule(iv, "plan_ctx")
        if iv["reason"] is None and _RE_REF_HOLE.search(t[max(0, iv["pos"] - 200):iv["pos"]]):
            iv["reason"] = "reference_hole"  # "... 50 m downdip of hole AB-12 (1.2 g/t over 3 m)"
            _rule(iv, "ref_hole")
        near_t = t[max(0, iv["pos"] - 200):iv["pos"] + 150]  # the interval's own sentence
        cut = [m.end() for m in re.finditer(r"[.;]\s", near_t[:min(200, iv["pos"])])]
        near_t = near_t[cut[-1] if cut else 0:]
        end = re.search(r"[.;]\s", near_t[min(200, iv["pos"]) - (cut[-1] if cut else 0):])
        if end:
            near_t = near_t[:min(200, iv["pos"]) - (cut[-1] if cut else 0) + end.start()]
        if (iv["reason"] is None and not any(_same(h, iv) for h in hl_ints) and (
                (_RE_THRESHOLD_LEN.search(near_t) and _RE_THRESHOLD_GRADE.search(near_t))
                or (_RE_THRESHOLD_GRADE.search(near_t) and re.search(r"(?i)\b(?:in\s+total|cumulative|aggregate|combined\s+(?:length|thickness))\b", near_t)))):
            iv["reason"] = "not_interval"
            _rule(iv, "threshold")
        if iv["reason"] is None and _RE_UP_TO.search(t[max(0, iv["pos"] - 40):iv["pos"]]) and not any(_same(h, iv) for h in hl_ints):
            iv["reason"] = "not_interval"
            _rule(iv, "up_to")
        if (iv["reason"] is None and re.search(r"(?i)\b(?:less|fewer)\s+than\s+(?:[\d.,]+\s*(?:m|metres?|meters?|ft|feet)\s*(?:of|at|@|grading)?\s*)?$", t[max(0, iv["pos"] - 50):iv["pos"]])
                and not any(_same(h, iv) for h in hl_ints)):
            iv["reason"] = "not_interval"   # FIX3: "Holes with less than 2 ft of 0.02% U3O8 are not reported": a reporting cut-off
            _rule(iv, "less_than")
        if iv["reason"] is None:
            seg = t[iv["pos"]:iv["pos"] + 300]
            end = re.search(r"\.(?:\s|$)", seg)
            sent = seg[:end.start() if end else 300]
            inc = re.search(r"(?i)includ\w*\s+(?:the\s+)?previously\s+(?:announced|reported|released)", sent)
            ref = _RE_REF_AFTER.search(sent)
            if ref and inc and inc.start() < ref.start():
                ref = None  # 1.0.1: "... over 16.0 m including the previously announced interval of 67.1 g/t (see Press Release ...)"
            if ref and _RE_OTHER_HOLE_REL.search(sent[:ref.start()]):
                ref = None  # FIX3: "... in hole AB-26-038, 100m down-dip of previously reported hole AB-26-027 (see ... press release)"
            if ref:
                iv["reason"] = "previously_reported"
                _rule(iv, "ref_after")
        if iv["reason"] is None and _RE_TRENCH_AFTER.search(t[iv["pos"]:iv["pos"] + 120]):
            iv["reason"] = "surface"  # "6.24 g/t Au with 1715 g/t Ag over 0.36 m in trenching"
            _rule(iv, "trench_after")
        if iv["reason"] is None and _RE_REASSAY.search(ctx):
            iv["reason"] = "previously_reported"  # a re-assay of a hole released before
            _rule(iv, "reassay")
        if iv["reason"] is None and not hl_drill and not lede_drill:
            iv["reason"] = "no_drill_context"
            _rule(iv, "no_drill")
        iv["_drill_ctx"] = bool(_RE_DRILL_CONTEXT.search(ctx))
    # "hole KW-25-003 that assayed 301.67 g/t over 3.90 m including 1,930 g/t over 0.60 m": a sub-interval shares its parent's fate
    for k, iv in enumerate(text_ints):
        if iv.get("including") and iv["reason"] is None and k > 0:
            par = text_ints[k - 1]
            if par["reason"] and iv["pos"] - par["pos"] < 150 and not re.search(r"[.;]\s", t[par["pos"]:iv["pos"]]):
                iv["reason"] = par["reason"]
                _rule(iv, "incl_parent")
    _attach_holes(t, spans, holes, text_ints)
    _text_depths(t, text_ints)                                # 1.0.5
    # 1.0.2: one quoted interval in several metals shares its hole ("61 metres @ 0.47 g/t Au & 0.78 g/t Ag" in MV21-010):
    # the gold took the hole and was judged by its year, the silver had none and stood as a new result (NOM.CN)
    for iv in text_ints:
        if iv.get("hole"):
            continue
        def _quoted_with(x):
            if abs(x["pos"] - iv["pos"]) < 120 and not re.search(r"[.;]\s|\n\s*\n", t[min(x["pos"], iv["pos"]):max(x["pos"], iv["pos"])]):
                return True
            # the sibling was de-duplicated against an earlier mention: its grade is written just before this one
            win = t[max(0, iv["pos"] - 60):iv["pos"]]
            ms = list(re.finditer(r"(?<![\d.])" + re.escape("%g" % x["grade"]) + r"0*(?![\d])", win))
            return bool(ms) and not re.search(r"[.;]\s|\n", win[ms[-1].end():])
        sib = next((x for x in text_ints if x is not iv and x.get("hole") and abs(x["length_m"] - iv["length_m"]) < 0.011
                    and _quoted_with(x)), None)
        if sib is None:  # "..., including 15 metres grading ...": the parent's hole
            sib = next((x for x in sorted(text_ints, key=lambda y: -y["pos"]) if x is not iv and x.get("hole") and x["pos"] < iv["pos"]
                        and iv["pos"] - x["pos"] < 150 and x["length_m"] > iv["length_m"]
                        and re.search(r"(?i)\bincl(?:uding|\.)?\b", t[x["pos"]:iv["pos"]])
                        and not re.search(r"[.;]\s|\n\s*\n", t[x["pos"]:iv["pos"]])), None)
        if sib:
            iv["hole"], iv["hole_how"] = sib["hole"], "sibling"
    for iv in text_ints:
        if (iv["reason"] is None and _old_hole(iv.get("hole"), rdate)
                and not re.search(re.escape(iv["hole"]) + r"\s?W\d", t)):  # 1.0.1: wedge "CS-21-73W1" is new drilling
            iv["reason"] = "historical"  # hole TM22-119 quoted in a 2025 release
            _rule(iv, "hole_year")
    # 1.0.8: a release whose holes carry the year at the end ("XY185-19", "XY187-19" in 2019): an id of the same form
    # ending in an older year ("XY104-10") is an earlier program's hole
    if rdate:
        yy, suf = rdate[0] % 100, {}
        for h in holes:
            m_ = re.fullmatch(r"([A-Z]{1,6})\d{3}-(\d{2})", h["id"])
            if m_ and int(m_.group(2)) in (yy, (yy - 1) % 100):
                suf.setdefault(m_.group(1), set()).add(h["id"])
        for iv in text_ints:
            m_ = re.fullmatch(r"([A-Z]{1,6})\d{3}-(\d{2})", iv.get("hole") or "")
            if iv["reason"] is None and m_ and len(suf.get(m_.group(1), ())) >= 2 and 2 <= (yy - int(m_.group(2))) % 100 <= 40:
                iv["reason"] = "historical"
                _rule(iv, "hole_year_suffix")
    # an id that only appears inside a historical sentence is somebody else's hole
    cur_prefixes = {_hole_prefix(h["id"]) for h in holes
                    if rdate and _RE_HOLE_YEAR.match(h["id"]) and 2000 + int(_RE_HOLE_YEAR.match(h["id"]).group(1)) == rdate[0]}
    for iv in text_ints:
        if iv.get("hole") and iv["reason"] is None:
            hs = [h for h in holes if h["id"] == iv["hole"]]
            hist = [reason_for(*_unit_ctx(t, spans, h["pos"])[:2]) == "historical" for h in hs]
            if (hs and any(hist) and iv["hole"] not in _unit_ctx(t, spans, iv["pos"])[0]
                    and _old_hole(iv["hole"], (rdate[0] + 1, 1, 1) if rdate else None)
                    and _hole_prefix(iv["hole"]) in cur_prefixes):
                iv["reason"] = "historical"  # "hole SP22-13 ... highest grade to date. These intervals are part of a broader zone" (1.0.1)
                _rule(iv, "hole_hist_sentence")
            elif hs and all(hist):
                iv["hole"] = None

    # 1.0.1: the same figure elsewhere called "previously reported hole X returned ..." is not new where it is repeated
    for iv in text_ints:
        if iv["reason"] is not None or any(_same(h, iv) for h in hl_ints):
            continue
        lit_len = ("%.2f" % iv["length_m"]).rstrip("0").rstrip(".")
        for p in _occurrences(t, iv):
            if abs(p - iv["pos"]) < 5:
                continue
            near = t[max(0, p - 140):p + 60]
            if not re.search(r"(?<![\d.])" + re.escape(lit_len) + r"(?![\d])", near):
                continue
            pre = t[max(0, p - 140):p]
            if re.search(r"[.;]\s", pre):
                pre = pre[re.search(r"^.*[.;]\s", pre, re.S).end():]  # same sentence only
            if re.search(r"(?i)\bpreviously\s+(?:reported|announced|released|disclosed|published)\s+(?:drill\s+)?(?:holes?|intercepts?|intervals?|intersections?|results?)\b", pre):
                iv["reason"] = "previously_reported"
                _rule(iv, "occurrence_prev")
                break

    # 1.0.8: the headline repeated at the top of the body gives a figure no context of its own; where the body quotes the
    # same interval again, it says what it is ("Selected historical high-grade drilling intersected 108.36 g/t gold ...
    # over 7 metres (DDH81AS43)"). When every such quotation is background, so is the headline copy.
    for iv in text_ints:
        if iv["reason"] is not None or not (copy and copy[0] <= iv["pos"] < copy[1]):
            continue
        whys = []
        for p in _occurrences(t, iv):
            if copy[0] <= p < copy[1]:
                continue
            us, ue = spans[unit_at(spans, p)]
            if not any(_ft_close(_ft_m(D._num(m.group(1)), m.group(2)), float(iv["length_m"])) for m in _RE_FT_LEN.finditer(t[max(us, p - 120):min(ue, p + 120)])):
                continue
            ctx_, head_, pin_ = _unit_ctx(t, spans, p)
            # FIX3: the repeat's own sentence decides; a lead-in it inherits ("Historical underground grades were 8 to 10
            # g/t ... Highlights:") is not enough to overrule the headline
            whys.append(reason_for(ctx_, "", pin_) or _local_reason(t, spans, dict(iv, pos=p), rdate, reason_for))
        if whys and all(w in ("historical", "previously_reported", "reference_hole") for w in whys):
            iv["reason"] = whys[0]
            _rule(iv, "repeat_context")

    # the same figure elsewhere in the body: a rock-chip or XRF mention of it condemns a bare repeat
    for iv in text_ints:
        if iv["reason"] is not None or iv["_drill_ctx"]:
            continue
        if any(x is not iv and _same(x, iv) and x["_drill_ctx"] and x["reason"] is None for x in text_ints):
            continue  # the body reports the same figure as a drill result
        if _RE_DRILL_WORD.search(th_np) and any(_same(h, iv) for h in hl_ints):
            continue  # "ESCONDIDA VEIN RETURNS FIRST DRILL INTERCEPT OF 4.25 g/t Au": the headline itself says drilling
        found = None
        drill_seen = False
        for p in _occurrences(t, iv):
            if abs(p - iv["pos"]) < 5:
                continue
            ctx, head, _pin = _unit_ctx(t, spans, p)
            if _TABLE_HEADER.search(ctx):
                continue  # a table header ("samples not analyzed by XRF") says nothing about the prose figure
            if not re.search(r"(?<![\d.])" + re.escape(("%.2f" % iv["length_m"]).rstrip("0").rstrip(".")) + r"(?![\d])", ctx):
                continue
            if _RE_DRILL_CONTEXT.search(ctx):
                drill_seen = True
            r = reason_for(ctx, head)
            if r in ("surface", "xrf", "visual"):
                found = found or r
        if found and not drill_seen:
            iv["reason"] = found
            _rule(iv, "occurrence")

    # 1.0.2: a results table that starts near the end of the lede is read to its end (PMI.V: the lede cut the table after
    # its first row, so the 4.13% Ni row was never seen). Only tables whose header is inside the lede count.
    tab_t = t
    if len(ld) >= D.LEDE_CHARS and _TABLE_HEADER.search(t, max(0, len(t) - 2500)):
        full = D._prep(D.lede(raw_body, D.LEDE_CHARS + 4000))
        if len(full) > len(t) and full.startswith(t):
            tab_t = full
    table_ints = find_tables(tab_t, rdate, spans, hl_years, header_before=len(t))
    for iv in table_ints:
        iv["pos"] = min(iv["pos"], len(t) - 1)
    for iv in table_ints:
        if release_reason == "surface" and iv.get("hole") and _RE_DRILL_WORD.search(_unit_ctx(t, spans, iv["pos"])[0][:400]):
            continue  # 1.0.1: a drill-hole table in a release that also reports soil or channel samples
        if release_reason:
            iv["reason"] = release_reason
            _rule(iv, "release")

    # table rows and prose repeat each other: keep one, preferring the table's hole and depths
    merged = list(table_ints)
    for iv in text_ints:
        dup = next((x for x in merged if _same(x, iv)), None)
        if dup:
            if dup["src"] == "table" and iv["reason"] and not dup["reason"]:
                dup["reason"] = iv["reason"]
                _rule(dup, "dup_copy")
            elif dup["src"] == "text" and dup["reason"] and not iv["reason"]:
                dup["reason"], dup["rule"] = None, None  # one clean mention of the same figure is enough
            if dup.get("including") and not iv.get("including"):
                dup["including"] = False
            if dup["reason"] and dup.get("reason_src") == "title" and not iv["reason"] and iv.get("_drill_ctx"):
                dup["reason"] = None  # the prose reports this row as a new drill result
            if not dup.get("hole") and iv.get("hole"):
                dup["hole"], dup["hole_how"] = iv["hole"], iv.get("hole_how")
            if dup.get("from_m") is None and iv.get("from_m") is not None:
                dup["from_m"], dup["to_m"], dup["depth_src"] = iv["from_m"], iv["to_m"], "text"  # 1.0.5
            continue
        merged.append(iv)

    # 1.0.5: a results table printed after the lead text (CADY.TO "Table 1. Selected Significant Results" at 9,600
    # characters) is not read for new intervals, but it lends its From-To to the intervals the prose already gave:
    # the same hole, metal and grade, and the same length, or the table's downhole length where the prose quotes
    # the true width. Only an unambiguous match is taken.
    if len(ld) >= D.LEDE_CHARS and any(x.get("from_m") is None for x in merged):
        far = D._prep(D.lede(raw_body, D.LEDE_CHARS + 16000))
        if len(far) > len(tab_t) and far.startswith(tab_t[:len(t)]):
            far_rows = [x for x in find_tables(far, rdate, None, hl_years) if x["pos"] >= len(tab_t) - 200]
            etw_doc = bool(_RE_FT_ETW.search(far))
            for iv in merged:
                if iv.get("from_m") is not None:
                    continue
                cands = []
                for r in far_rows:
                    if r["metal"] != iv["metal"] or r.get("from_m") is None:
                        continue
                    if iv.get("hole") and r.get("hole") and norm_hole(iv["hole"]) != norm_hole(r["hole"]):
                        continue
                    gi, gr = iv["grade"] * D._TO_PPM.get(iv["unit"], 1.0), r["grade"] * D._TO_PPM.get(r["unit"], 1.0)
                    if abs(gi - gr) > max(0.005 * max(gi, gr), 0.0051 * D._TO_PPM.get(r["unit"], 1.0)):
                        continue
                    same_len = abs(iv["length_m"] - r["length_m"]) <= max(0.02 * r["length_m"], 0.051)
                    same_tw = r.get("tw_m") is not None and abs(iv["length_m"] - r["tw_m"]) <= max(0.02 * r["tw_m"], 0.051)
                    if same_len or same_tw or (etw_doc and r.get("tw_m") is None and iv.get("hole") and r.get("hole")
                                               and r["length_m"] > iv["length_m"]):
                        cands.append(r)
                if len({(c["from_m"], c["to_m"]) for c in cands}) == 1:
                    iv["from_m"], iv["to_m"], iv["depth_src"] = cands[0]["from_m"], cands[0]["to_m"], "far_table"
                    if not iv.get("hole") and len({c.get("hole") for c in cands}) == 1 and cands[0].get("hole"):
                        iv["hole"], iv["hole_how"] = cands[0]["hole"], "table"  # the table names the hole the prose left out
                    continue
                # the table names another hole for exactly this grade and length ("2.44 g/t Au over 7.5 m ETW, and 3.21 g/t
                # Au over 3.4 m (ETW) in hole KAD26-473" was credited to the hole named before it): the table is right
                exact = [r for r in far_rows if r["metal"] == iv["metal"] and r.get("from_m") is not None and r.get("hole")
                         and abs(r["grade"] - iv["grade"]) <= 1e-9
                         and (abs(iv["length_m"] - r["length_m"]) <= 0.011
                              or (r.get("tw_m") is not None and abs(iv["length_m"] - r["tw_m"]) <= 0.011))]
                if len(exact) == 1 and not iv.get("including"):
                    r = exact[0]
                    iv["from_m"], iv["to_m"], iv["depth_src"] = r["from_m"], r["to_m"], "far_table"
                    if not iv.get("hole") or norm_hole(iv["hole"]) != norm_hole(r["hole"]):
                        iv["hole"], iv["hole_how"] = r["hole"], "table"

    # headline figures must agree with the body; a headline figure the body rejects is rejected,
    # and a headline that calls its own figures XRF or visual condemns the body copies too
    hl_reason = context_reason(th, rdate, program_years, exempt_years=hl_years)
    body_ok = [x for x in merged if not x["reason"]]
    body_any = bool(merged)
    for iv in hl_ints:
        iv["src"] = "headline"
        htail = th[max(0, iv["pos"] - 90):iv["pos"]]
        iv["including"] = _is_sub(htail)
        match_ok = next((x for x in body_ok if _same(x, iv)), None) or next((x for x in body_ok if _rounded_same(iv, x)), None)
        match_bad = next((x for x in merged if x["reason"] and (_same(x, iv) or _rounded_same(iv, x))), None)
        named_hole = bool(match_bad and match_bad.get("hole") and re.search(r"(?i)\b(?:extends?|extension|extended|deepen\w*|re-?enter\w*)\b", th)
                          and norm_hole(match_bad["hole"]) in {norm_hole(h["id"]) for h in find_holes(th)})
        if (not match_ok and match_bad and not release_reason and match_bad["reason"] in ("historical", "previously_reported") and (
                named_hole or (hl_reason is None and _RE_DRILL_VERB_HEADLINE.search(th)
                               and match_bad.get("rule") in ("context", "dup_copy", "line_heading")))):
            match_bad["reason"], match_bad["rule"] = None, None  # "Argenta Intersects 1,385 g/t Ag over 4.0m": the company's own new hole
            match_ok, match_bad = match_bad, None
            body_ok.append(match_ok)
        if match_ok:
            if hl_reason in ("xrf", "visual"):
                for x in merged:
                    if _same(x, iv):
                        x["reason"] = hl_reason
                        _rule(x, "headline_xrf")
            else:
                match_ok["headline"] = True
                match_ok["hl_pos"] = min(match_ok.get("hl_pos", iv["pos"]), iv["pos"])
            continue
        if match_bad:
            iv["reason"] = match_bad["reason"]
            _rule(iv, "headline_match_bad")
        else:
            iv["reason"] = release_reason or hl_reason
            _rule(iv, "headline_ctx")
        if iv["reason"] is None and not body_ok and body_any:
            iv["reason"] = "headline_unconfirmed"
            _rule(iv, "headline_unconfirmed")
        merged.append(iv)

    if len(merged) > MAX_INTERVALS:
        # long tables must not push the prose and headline figures out
        keep_tab = MAX_INTERVALS - sum(1 for x in merged if x["src"] != "table")
        seen_tab = 0
        trimmed = []
        for x in merged:
            if x["src"] == "table":
                seen_tab += 1
                if seen_tab > max(keep_tab, 0) and not x.get("headline"):
                    continue
            trimmed.append(x)
        merged = trimmed
    for x in merged:
        x.pop("_drill_ctx", None)
        cap = _PCT_CAP.get(x["metal"])
        gm = _GM_CAP.get(x["metal"])
        if not x["reason"] and gm and x["unit"] == "g/t" and x["grade"] * x["length_m"] > gm and not x.get("headline"):
            x["reason"] = "implausible"
            _rule(x, "gm_cap")
        if not x["reason"] and ((x["unit"] == "%" and cap and x["grade"] > cap) or (x["unit"] == "ppb" and x["grade"] < 1)):
            x["reason"] = "implausible"
            _rule(x, "pct_cap")
    ok = [x for x in merged if not x["reason"]]
    for x in ok:
        x["src_code"] = 0 if (x["src"] == "headline" or x.get("headline")) else 1
    # a sub-interval ("including 1.0 m at 46 g/t") is shown under its parent, never instead of it
    # 1.0.3: the same interval quoted again, in a headline or a highlight, is still a sub-interval
    for x in ok:
        if not x.get("including") and any(y is not x and y.get("including") and _same(y, x) for y in merged):
            x["including"] = True
            _rule(x, "sub_by_value")
    # 1.0.3: "including: 9.3 g/t over 3.5 m; 14.9 g/t over 5.9 m" -- every item of an "including" list is
    # inside the parent, not just the first one the grammar caught.
    subs = sorted([x for x in merged if x.get("including") and x.get("src") == "text"], key=lambda x: x["pos"])
    for x in ok:
        if x.get("including") or x.get("src") != "text":
            continue
        prev = [y for y in subs if y["pos"] < x["pos"]]
        if not prev:
            continue
        a = prev[-1]
        gap = t[a["pos"]:x["pos"]]
        if len(gap) > 320 or re.search(r"[.!?]\s+[A-Z]", gap):
            continue
        if (a.get("hole") or None) != (x.get("hole") or None):
            continue
        if any(a["pos"] < h["pos"] < x["pos"] for h in holes):
            continue
        # the list has to sit inside a parent, and every item of it is shorter than that parent
        par = [y for y in merged if not y.get("including") and y["pos"] < a["pos"]
               and y.get("src") == "text" and (y.get("hole") or None) == (a.get("hole") or None)]
        if not par or x["length_m"] >= 0.9 * max(y["length_m"] for y in par[-2:]):
            continue
        x["including"] = True
        _rule(x, "sub_in_list")
    pool = [x for x in ok if not x.get("including") or x["src_code"] == 0] or ok
    rank_list = [dict(x, src=x["src_code"], pos=(x.get("hl_pos", x["pos"]) if x["src_code"] == 0 else 100000 + x["pos"]))
                 for x in pool]
    if rank_list:
        D._stamp_tiers(rank_list)
        fam = _headline_family(th)
        if fam and not any(x["src"] == 0 for x in rank_list) and any(D._family(x["metal"]) == fam for x in rank_list):
            for x in rank_list:
                x["tier"] = 2 if D._family(x["metal"]) == fam else 0
        order = sorted(range(len(rank_list)), key=lambda i: D.score_intercept(rank_list[i]), reverse=True)
        # 1.0.3: a sub-interval never wins over a parent that is present, even when the headline quotes it
        best_i = next((i for i in order if not pool[i].get("including")), order[0])
        top = pool[best_i]
        # one interval quoted in several metals ("529 m grading 0.41% Cu and 0.21 g/t Au"): show its equivalent grade if
        # given, else the metal the release lists first
        sibs = [x for x in pool if x["src"] == top["src"] and abs(x["length_m"] - top["length_m"]) < 0.011 and (x is top or x["metal"] != top["metal"])
                and (x.get("hole") or None) == (top.get("hole") or None) and abs(x["pos"] - top["pos"]) < 120
                and (x["src"] != "text" or not re.search(r"[.;]\s", t[min(x["pos"], top["pos"]):max(x["pos"], top["pos"])]))
                and bool(x.get("headline")) == bool(top.get("headline")) and bool(x.get("including")) == bool(top.get("including"))]
        hl_hits = [(m.start(), f) for f, pat in _HEADLINE_METALS
                   for m in [re.search(r"(?i)\b(?:" + pat + r")\b" + _PLACE_AFTER_METAL, th)] if m]
        hl_fams = {f for _p, f in hl_hits}
        # 1.0.3: "Gold and Silver Results" ranks on gold -- the metal the headline names first
        one_fam = (next(iter(hl_fams)) if len(hl_fams) == 1
                   else (min(hl_hits)[1] if hl_hits else None))
        if len(sibs) > 1:
            top = min(sibs, key=lambda x: (0 if one_fam and D._family(x["metal"]) == one_fam else 1,
                                           0 if x["metal"].endswith("Eq") else 1,
                                           x.get("hl_pos", x["pos"]) if x.get("headline") else x["pos"], merged.index(x)))
        result["top"] = merged.index(top)
        result["is_result"] = True
    else:
        reasons = [x["reason"] for x in merged if x["reason"]]
        result["reason"] = max(set(reasons), key=reasons.count) if reasons else "no_intervals"
    if result["top"] is not None:
        top = merged[result["top"]]
        _hole_from_repeats(t, spans, holes, top, text_ints, merged, copy)   # 1.0.8
        if not top.get("hole"):
            twin = next((x for x in merged if x is not top and x.get("hole") and not x["reason"] and _same(x, top)), None)
            if twin is None:
                # 1.0.3: the same interval reported once per metal carries the hole on its other metals
                twin = next((x for x in merged if x is not top and x.get("hole") and not x["reason"]
                             and abs(x["length_m"] - top["length_m"]) <= max(0.03 * max(x["length_m"], top["length_m"]), 0.06)), None)
            if twin is None:
                # 1.0.4: a hole named before the intercept beats one named after it. Without this the
                # forward scan jumps over the heading that owns the figure ("Hole ND26-006 - Hachey Zone
                # ... 5.5 m @ 469.8 g/t AgEq ... Hole BC26-001B - Pine Tree W") and credits the next hole.
                prev = [h for h in holes if top["pos"] - _HL_HOLE_WINDOW <= h["pos"] < top["pos"]]
                if prev and not context_reason(t[prev[-1]["pos"]:prev[-1]["pos"] + 200], rdate):
                    top["hole"] = prev[-1]["id"]
            if twin is None and not top.get("hole"):
                # 1.0.3: a headline intercept names no hole of its own; the hole the body names first,
                # right after it ("... 90.92 g/t Ag over 309.0 m ... from hole DSB-75"), is its hole.
                # 1.0.4: the same is true of a lead-paragraph or highlights restatement, which is text and
                # not headline, and is what wins on most releases whose hole column comes out blank.
                for nh in [h for h in holes if top["pos"] < h["pos"] <= top["pos"] + _HL_HOLE_WINDOW]:
                    if context_reason(t[nh["pos"]:nh["pos"] + 200], rdate):
                        continue
                    if not (_RE_HOLE_CREDIT_BEFORE.search(t[max(0, nh["pos"] - 60):nh["pos"]])
                            or _RE_HOLE_CREDIT_AFTER.match(t[nh["end"]:nh["end"] + 70])):
                        continue
                    top["hole"] = nh["id"]
                    break
            if twin:
                top["hole"] = twin["hole"]
        # FIX5: the shown hole gives way only to the one hole that every quotation of the figure is written with
        if top.get("hole"):
            owned = _owned_hole(t, holes, top)
            a_, b_ = norm_hole(owned or ""), norm_hole(top["hole"])
            if owned and a_ not in b_ and b_ not in a_:   # "25-060" is "DDH-25-060"; "AB17" is a piece of "AB17 -11"
                top["hole"], top["hole_how"] = owned, "owner"
        if top.get("from_m") is None:
            twin = next((x for x in merged if x is not top and x.get("from_m") is not None and not x["reason"] and _same(x, top)), None)
            if twin:
                top["from_m"], top["to_m"] = twin["from_m"], twin["to_m"]  # 1.0.5
    # 1.0.8: the release must itself announce new drill results (NEWS_V1); otherwise its figures are background
    if result["is_result"]:
        kind, why = release_news(hl, t, rdate, any(x.get("src") == "headline" and not x["reason"] or x.get("headline") and not x["reason"]
                                                   for x in merged))
        if kind != "results":
            for x in merged:
                if not x["reason"]:
                    x["reason"], x["rule"] = why, "release_news"
            result["is_result"], result["top"], result["reason"] = False, None, why
    result["intervals"] = merged
    name, rank = _project_pn(th, t)   # 1.0.6
    result["project"], result["project_rank"] = name, rank
    return result


# ------------------------------------------------------------------ 1.0.5: downhole depths quoted in prose
_FT_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_FT_UNIT = r"(m|metres?|meters?|ft|feet)\b"
_FT_DASH = "(?:to|-|" + chr(0x2013) + "|" + chr(0x2014) + ")"
_RE_FT_LEN = re.compile(r"(?i)(?<![\w.,])" + _FT_NUM + r"\s*" + _FT_UNIT)
_RE_FT_FROM = re.compile(r"(?i)\b(?:from|starting\s+at|beginning\s+at)\s+(?:a\s+)?(?:down[\s\-]?hole\s+)?(?:depth\s+of\s+)?(?:approximately\s+|about\s+|~\s*)?"
                         + _FT_NUM + r"\s*(?:" + _FT_UNIT + r")?"
                         r"(?:\s*" + _FT_DASH + r"\s*" + _FT_NUM + r"\s*(?:" + _FT_UNIT + r")?)?")
_RE_FT_PAREN = re.compile(r"(?i)^\s*\(\s*(?:from\s+)?" + _FT_NUM + r"\s*(?:" + _FT_UNIT + r")?\s*" + _FT_DASH + r"\s*"
                          + _FT_NUM + r"\s*(?:" + _FT_UNIT + r")?\s*(?:down[\s\-]?hole\s*)?\)")
_RE_FT_STOP = re.compile(r"(?i)" + chr(0x2022) + r"|\n\s*\n\s*(?=(?:Hole|Drill\s*hole|DDH)\b|[A-Z]{1,6}[\w\-]*\d{2,}[\w\-]*\s*[:\-" + chr(0x2013) + r"])|;|\.\s+(?=[A-Z(])|\bincl(?:uding|udes|\.)|\bwithin\b|\bwhich\b|\bwhile\b|\bwhereas\b"
                         r"|\b(?:previously|historic\w*)\b")
_RE_FT_SURFACE = re.compile(r"(?i)\b(?:from|starting\s+at)\s+(?:the\s+)?surface\b(?!\s+(?:to|down|sampl|trench|channel|grab|expression|outcrop))")
_RE_FT_ETW = re.compile(r"(?i)\btrue\s+(?:width|thickness)|\bE?TW\b|\be\.t\.w\b")


def _ft_m(v, u):
    return v * 0.3048 if (u or "m").lower().startswith(("f",)) else v


def _ft_close(a, b):
    return abs(a - b) <= max(0.051, 0.015 * max(a, b))


def _depth_at(t, p, L):
    """The (from, to) the prose gives for an interval of length L whose grade starts at p, or None."""
    w = t[p:p + 220]
    lead = t[max(0, p - 60):p]
    op = lead.rfind("(")
    if op != -1 and ")" not in lead[op:]:
        close = w.find(")")
        if close != -1:
            w = w[:close]                              # "(including 62.39 g/t Au over 0.9 m) (TGC-0447, from 92 m)": the
                                                       # depth after the brackets is the parent's, not this one's
    # "56.59 g/t Au over 1.3 m (including 62.39 g/t Au over 0.9 m) (TGC-0447, from 92 m depth)": the bracketed
    # sub-interval does not end the parent's clause
    w = re.sub(r"(?i)\(\s*incl[^()]{0,120}\)", lambda m_: " " * len(m_.group(0)), w)
    stop = _RE_FT_STOP.search(w)
    if stop:
        w = w[:stop.start()]

    def others(seg):
        return [x for x in _RE_FT_LEN.finditer(seg) if not _ft_close(_ft_m(D._num(x.group(1)), x.group(2)), L)]
    sm = _RE_FT_SURFACE.search(w)
    if sm and not others(w[:sm.start()]):
        return 0.0, round(L, 3)                        # "84.55 metres @ 2.04 g/t AuEq from surface"
    got = None
    m = _RE_FT_FROM.search(w)
    if m and not others(w[:m.start()]):
        got = m
    if got is None:
        # the depths in brackets right after the length, before the grade
        back = t[max(0, p - 140):p]
        for x in _RE_FT_LEN.finditer(back):
            if not _ft_close(_ft_m(D._num(x.group(1)), x.group(2)), L):
                continue
            pm = _RE_FT_PAREN.match(back, x.end())
            if pm and not _RE_FT_STOP.search(back[pm.end():]) and not others(back[pm.end():]):
                got = pm
    if got is None:
        return None
    g = got.groups()
    try:
        a = D._num(g[0])
        b = D._num(g[2]) if g[2] else None
    except (ValueError, TypeError):
        return None
    ua = g[1] or (g[3] if b is not None else None)
    ub = g[3] or g[1]
    if ua is None:
        return None                                    # "from 12 samples", "from 2024": no depth without a unit
    a = _ft_m(a, ua)
    etw = bool(_RE_FT_ETW.search(t[max(0, p - 60):p + 160]))
    if b is not None:
        b = _ft_m(b, ub)
        if not (b > a and (_ft_close(b - a, L) or (etw and b - a > L))):
            return None
    else:
        if etw:
            return None
        b = a + L
    if a > 5000:
        return None
    return round(a, 3), round(b, 3)


_RE_FT_GRADE_UNIT = re.compile(r"(?i)^\s*(?:%|g/t|gpt|g/tonne|ppm|ppb|oz/t|opt)")


def _text_depths(t, ints):
    """1.0.5: "3.4 g/t Au over 44.75 metres from 256.23 metres", "0.1% U3O8 over 1.0 metres from 183.0 to 184.0m",
    "400m @ 0.46% Cu ... from 32m", "6.2 metres (from 144.0 to 150.2 metres) of ... 0.10% U3O8": the downhole
    depths prose gives for an interval. A stated to-depth must agree with the length (or, when the length is a
    true width, be longer than it); a from-depth alone gives the to-depth as from + length, except for a true
    width. Nothing is taken across another interval's length, a sentence end, a bullet or an "including". The
    same figure quoted again (a lead paragraph and then the hole's own paragraph) lends its depths to the first."""
    for iv in ints:
        if iv.get("from_m") is not None or not iv.get("length_m"):
            continue
        L = float(iv["length_m"])
        got = _depth_at(t, iv["pos"], L)
        if got is None:
            for q in _occurrences(t, iv):
                if abs(q - iv["pos"]) < 5:
                    continue
                num = re.match(r"[\d.,]+", t[q:])
                if not num or not _RE_FT_GRADE_UNIT.match(t[q + num.end():q + num.end() + 10]):
                    continue
                try:
                    if abs(D._num(num.group(0).rstrip(".,")) - float(iv["grade"])) > 1e-9:
                        continue                       # the same figure, not a rounding of it
                except (ValueError, TypeError):
                    continue
                near = t[max(0, q - 90):q + 90]
                if not any(_ft_close(_ft_m(D._num(x.group(1)), x.group(2)), L) for x in _RE_FT_LEN.finditer(near)):
                    continue
                got = _depth_at(t, q, L)
                if got:
                    break
        if got:
            iv["from_m"], iv["to_m"] = got
            iv["depth_src"] = "text"

# ------------------------------------------------------------------ facts store adapter
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    ivs = a["intervals"]
    if not ivs and not a["is_result"]:
        return []
    facts = [F.Fact("is_result", value_num=1.0 if a["is_result"] else 0.0)]
    if a["reason"]:
        facts.append(F.Fact("release_reason", value_text=a["reason"]))
    if a["project"]:
        facts.append(F.Fact("project", value_text=a["project"]))
        facts.append(F.Fact("project_rank", value_num=float(a["project_rank"])))
    n_ok = 0
    for seq, iv in enumerate(ivs):
        ok = not iv["reason"]
        n_ok += 1 if ok else 0
        facts.append(F.Fact("iv_grade", value_num=float(iv["grade"]), unit=iv["unit"], metal=iv["metal"], seq=seq))
        facts.append(F.Fact("iv_length_m", value_num=float(round(iv["length_m"], 4)), unit="m", seq=seq))
        facts.append(F.Fact("iv_src", value_text=iv["src"], seq=seq))
        facts.append(F.Fact("iv_ok", value_num=1.0 if ok else 0.0, seq=seq))
        if iv.get("including"):
            facts.append(F.Fact("iv_including", value_num=1.0, seq=seq))
        if iv.get("hole"):
            facts.append(F.Fact("iv_hole", value_text=iv["hole"], seq=seq))
        if iv.get("from_m") is not None:
            facts.append(F.Fact("iv_from_m", value_num=float(iv["from_m"]), unit="m", seq=seq))
            facts.append(F.Fact("iv_to_m", value_num=float(iv["to_m"]), unit="m", seq=seq))
        if iv["reason"]:
            facts.append(F.Fact("iv_reason", value_text=iv["reason"], seq=seq))
            if iv.get("rule"):
                facts.append(F.Fact("iv_rule", value_text=iv["rule"], seq=seq))
    facts.append(F.Fact("n_intervals", value_num=float(n_ok)))
    if a["top"] is not None:
        top = ivs[a["top"]]
        facts += [F.Fact("best_grade", value_num=float(top["grade"]), unit=top["unit"], metal=top["metal"]),
                  F.Fact("best_metal", value_text=top["metal"]),
                  F.Fact("best_unit", value_text=top["unit"]),
                  F.Fact("best_length_m", value_num=float(round(top["length_m"], 4)), unit="m"),
                  F.Fact("best_seq", value_num=float(a["top"]))]
        if top.get("hole"):
            facts.append(F.Fact("best_hole", value_text=top["hole"]))
    return [F.Record(KIND, facts=facts, confidence=1.0 if a["is_result"] else 0.0)]


def to_prediction(records):
    """The accuracy check's view of one release: None when there is no drill result."""
    if not records:
        return None
    f = {x.field: x for x in records[0].facts if x.seq == 0}
    if not f.get("is_result") or f["is_result"].value_num != 1.0 or "best_grade" not in f:
        return None
    return {"project": f["project"].value_text if "project" in f else None,
            "hole": f["best_hole"].value_text if "best_hole" in f else None,
            "grade": f["best_grade"].value_num, "unit": f["best_unit"].value_text,
            "metal": f["best_metal"].value_text, "length_m": f["best_length_m"].value_num}


def _code_sha():
    # 1.0.7: this file and drill_extract.py whole, plus exactly the helper code this reader runs
    # (portal/fingerprint.py): a helper change to that code still bumps the version; an addition it does not call
    # does not. Same "-drill_extract.py" suffix as before.
    return FP.code_sha(__file__, own=(D.__file__,))


SPEC = F.ExtractorSpec(NAME, VERSION, KIND, TAG, extract, _code_sha())


# ------------------------------------------------------------------ self-test
# The v2.x corpora from portal/drill_extract.py are reused as-is (they are real corpus text), plus cases for
# the rules this version adds. Each new case names the rule it guards.
CASES_V1 = [
    # (rule, headline, body, expect) where expect is (length_m, grade, metal) that must be an accepted interval,
    # or ("reject", length_m, grade) that must not be accepted, or ("reason", why) for a release with no result
    ("xrf_headline", "Green River Gold Corp. Intercepts Its Highest XRF Nickel Results to Date, Including 0.355% "
     "Nickel over 7 Meters", "Highlights from Zone 2 thus far include 0.355% nickel over 7 meters in hole WK-22-02.",
     ("reject", 7.0, 0.355)),
    ("surface_repeat", "Eagle Plains Reports up to 29.9 g/t Au over 1.8m at the Bulldog Project",
     "Eagle Plains Reports up to 29.9 g/t Au over 1.8m at the Bulldog Project\nCranbrook, B.C., December 01 st, "
     "2025: Eagle Plains is pleased to announce results.\n\nHighlights\n\n\N{BULLET} 29.9 g/t Au, 22.6 g/t Ag and 0.2% "
     "Cu over 1.8m (rock chip)\n\N{BULLET} Grab sample returned 122 g/t Ag", ("reject", 1.8, 29.9)),
    ("year_after_work", "Company Acquires Property",
     "Toronto, Ontario, March 3, 2025: Highlights from a seven hole, 234 meter drill program by Enterayon Inc. in "
     "2006 include DDH DD-06, which returned 4.2m at 5.6 g/t Au (AR 28764).", ("reject", 4.2, 5.6)),
    ("pending_clause", "Corporate Update. Drill Results at Pilar Pending",
     "Historic highlights include: \no 16.5m @ 53.5g/t Au", ("reason", "pending")),
    ("pending_clause_partial", "ORVANA PROVIDES DRILLING UPDATE: FULL ASSAY RESULTS FROM TADD-278; SECOND HOLE "
     "RESULTS PENDING", "Hole TADD-278 intersected 12.5 m at 3.2 g/t Au from 100 m.", (12.5, 3.2, "Au")),
    ("heading_list", "Tocvan Drills 35.1 meters of 0.72 g/t AuEq at Pilar",
     "Hermosillo, June 15, 2021. Tocvan drilled 35.1 meters of 0.72 g/t AuEq in hole JES-21-43.\n"
     "\N{BULLET} 17,700m of Historic Core & RC drilling. Highlights include: \no 61.0m @ 0.8 g/t Au \n"
     "o 16.5m @ 53.5g/t Au and 53 g/t Ag \n", ("reject", 16.5, 53.5)),
    ("sentence_over_paragraphs", "Outstanding drilling results from high-grade core",
     "April 20, 2026\n\nHIGHLIGHTS\n\nPost-quarter results of\n\n70.8m @ 4.0% CuEq\n\nand\n\n53.3m @ 4.1% CuEq\n\n"
     "from hole MUG25-096 and MUG25-209 respectively (see ASX announcement dated 8 April 2026)\n\nThe MRE stands",
     ("reject", 70.8, 4.0)),
    ("paragraph_split", "CLARITY GOLD REPORTS HIGH GRADE GOLD INTERCEPTS INCLUDING 2.10 m of 18.64 gpt Au",
     "Vancouver, BC \N{EN DASH} June 16, 2021, Clarity Gold is pleased to announce results.\n \nSelected Intercepts \n"
     "Hole DES21-156: 3.68 g/t Au over 5.25 m, 18.64 g/t Au over 2.10 m \n \nMaps showing hole locations are "
     "available.\n \nThe holes were designed to confirm mineralization identified in historic drilling.",
     (2.10, 18.64, "Au")),
    ("recap", "FREEMAN GOLD CORP. DELIVERS MAJOR 2025 ACHIEVEMENTS; High-grade drill results",
     "The program delivered encouraging results, including high-grade intercepts such as 8.0 metres grading "
     "3.1 g/t gold.", ("reject", 8.0, 3.1)),
]


CASES_V1 += [
    ("webinar_invite", "Regency Silver Corp. Invites Investors to Live Webinar to Review 2025/2026 Drill Results",
     "June 19, 2026 - REG-26-29: 266.04 g/t Ag over 7.55m in drilling.", ("reason", "not_results")),
    ("investee", "Leocor Gold Applaudes Intrepid Metals Recent Drill Results At Corral",
     "July 11, 2024 - Leocor is pleased to update shareholders on news from Intrepid Metals (TSX.V: INTR). Intrepid reported "
     "112.95 meters of 1.50% Copper in Hole CC24_023.", ("reason", "investee")),
    ("plan_phrase_stripped", "Prismo Metals Announces Drilling to Commence at Los Pavitos Reports Additional Assay Results from Trenching",
     "Dec 9, 2025 - The best assays are 20.4 g/t Au over 2 meters at Las Auras.", ("reason", "surface")),
    ("values_up_to", "Delta Reports Drill Results", "February 27, 2026 - Drilling intersected anomalous gold including values up to "
     "0.5 g/t Au within an 8 m-wide sulphide-bearing iron formation.", ("reject", 8.0, 0.5)),
    ("ref_after", "F3 Intersects Uranium in Step-Out Holes", "April 22, 2026 - Hole PLN26-230 returned 2.0 m of 0.51% U3O8. It lies "
     "275m along strike from PLN25-219A which returned 13.0m of 0.28% U3O8 (see NR March 31, 2026).", ("reject", 13.0, 0.28)),
    ("follow_up_ref", "Dryden Gold Reports High-Grade Drill Results", "July 24, 2025 - The company has drilled four holes to follow "
     "up on the initial discovery in hole KW-25-003 that assayed 301.67 g/t over 3.90 meters including 1,930 g/t over 0.60 meters. "
     "Hole KW-25-061 intersected 12.5 g/t Au over 2.0 metres.", ("reject", 0.6, 1930.0)),
    ("headline_rounded", "Luca Mining Intersects 14 metres of 7 g/t Gold", "Sept 8, 2025 - Highlights include: 14.0 m grading 6.68 g/t "
     "gold and 6.0 m grading 9.0 g/t gold in drill hole DDH25-230.", (14.0, 6.68, "Au")),
    ("within_parent", "Banyan Gold Extends Powerline", "Dec 9, 2025 - Drill highlights: AX-25-724 - 4.60 g/t Au over 5.9m within "
     "0.64 g/t Au over 55.4m.", (55.4, 0.64, "Au")),
]


CASES_V1 += [
    ("abbrev_eg", "Provenance Gold Reports Summary of Results from Its Maiden RC Drill Program", "December 14, 2023 - Hole ED-01 "
     "intersected breccia. Previously reported intervals (e.g. 3.085 g/t Au over 114.30m including 39.875 g/t gold over 3.048 m) are "
     "not included. Hole ED-10 intersected 0.33 g/t Au over 140 m.", ("reject", 114.3, 3.085)),
    ("plan_drilling_to", "CANADIAN PALLADIUM DIAMOND DRILLING AT EAST BULL PROPERTY TO EXPAND MINERALIZATION", "June 7, 2021 - update.",
     ("reason", "plan")),
    ("historical_soil_headline", "Torr Metals Highlights Historical Soil Anomalies Linked to Sonic Porphyry Target",
     "Sept 3, 2025 - up to 700 ppb Au in soil and 2.24 g/t Au over 4.4 meters (m).", ("reason", "surface")),
    ("trench_after", "Company Reports Drill Results at Sonic", "Sept 3, 2025 - Hole SN-25-01 intersected 1.2 g/t Au over 30 m. "
     "Also, 6.24 g/t Au with 1715 g/t Ag over 0.36 m in trenching.", ("reject", 0.36, 1715.0)),
    ("list_including", "RUA GOLD Reports High-Grade Intercepts at", "RUA GOLD Reports High-Grade Intercepts at Auld Creek, Including "
     "17m @ 9.8g/t AuEq and 8m @ 8.9g/t AuEq. Sept 8, 2025 - Drilling at Auld Creek intersected high grades.", (17.0, 9.8, "AuEq")),
]


CASES_V1 += [
    ("length_before_grade", "Collective Mining Expands Apollo System", "December 3, 2025 - Hole APC140-D2 cut 76.10 meters @ 3.26 g/t "
     "gold including 16.40 meters @ 8.44 g/t gold. Hole APC141 cut 55.10 meters @ 3.06 g/t gold.", (76.1, 3.26, "Au")),
    ("width_note", "Kootenay Reports Results from Nine Holes", "January 8, 2026 - Hole CDH-25-201 intersected 16.5 meters "
     "(5.78m etw) of 691 gpt Ag.", (16.5, 691.0, "Ag")),
    ("feet_and_metres_table", "Arizona Gold & Silver Announces High Gold Grades in Core Drill Hole PC25-136", "April 7, 2025 - Hole "
     "PC24-136 assays are as follows:\nFrom (ft) To(ft) Thick.(ft) From(m) To(m) Thick.(m) Au (gpt) Ag (gpt)\n"
     "561.5 577.5 16 171.2 176.1 4.9 9.2 9.2\n", (4.9, 9.2, "Au")),
]


CASES_V1 += [
    ("headline_says_drill", "ESCONDIDA VEIN RETURNS FIRST DRILL INTERCEPT OF 4.25 g/t Au OVER 1.85 m",
     "ESCONDIDA VEIN RETURNS FIRST DRILL INTERCEPT OF 4.25 g/t Au OVER 1.85 m VANCOUVER, BC, Aug. 18, 2026 - Soma reports. "
     "EZDDH-26-001: 4.25 g/t Au over 1.85 m\nUnderground channel samples from the Escondida Mine include:\nCHU600005: 15.40 g/t Au "
     "over 1.0 m.", (1.85, 4.25, "Au")),
    ("plan_follow_up_headline", "XXIX Announces 20 Hole Drill Program to Follow up on Saddle Zone's Recent 5.94% Copper Equivalent "
     "over 11-metre Intersection", "Feb 10, 2025 - The program will follow up on hole SZ-24-03 which returned 5.94% CuEq over 11 m.",
     ("reject", 11.0, 5.94)),
]


# 1.0.1: releases 1.0.0 wrongly dropped at the /drills switch (claude/MNT_DRILL_V101_2026-09-17.md)
CASES_V1 += [
    ("plan_headline_new_results", "Opus One Gold Completes 2026 Drill Program at Noyell",
     "Toronto, Ontario, September 16, 2026 - Opus One Gold Corp. is pleased to announce the final assay results from its 2026 "
     "drilling program. Hole NO-26-18 returned 2.34 g/t Au over 9.34 metres.", (9.34, 2.34, "Au")),
    ("plan_headline_past_results", "Canadian Palladium Diamond Drilling at East Bull Property to Expand Mineralization",
     "Vancouver, June 7, 2021 - The company is pleased to provide an update on diamond drilling. The drilling will deepen hole "
     "EB-21-52, found to contain 2.38 g/t Pd over 6 metres at the bottom of the hole (see May 5, 2021 press release).",
     ("reject", 6.0, 2.38)),
    ("pending_headline_new_results", "Corporate Update: Assay Results Still Pending at Pilar",
     "March 2, 2026 - The company is pleased to announce assay results from the first two holes. Hole PL-26-01 returned "
     "54.55 m of 7.04 g/t Au.", (54.55, 7.04, "Au")),
    ("including_prev_announced", "Graycliff Expands High-Grade Interval in Hole 9 to 13.32 g/t Gold Over 16.0 Metres",
     "September 23, 2021 - Drill Hole J-9-21 intersected a mineralized interval of 13.32 g/t gold over 16.0 metres, including "
     "the previously announced interval of 52.0 g/t Au over 4.0 m see Press Release dated June 15, 2021), as detailed below.",
     (16.0, 13.32, "Au")),
    ("downhole_etw", "Outcrop Silver Intersects Additional High-Grade Mineralization",
     "Jan. 20, 2026 - Highlights DH549 returned 3.28 metres downhole (2.45 metres, Estimated True Width \"ETW\") grading "
     "214 g/t Ag and 0.64 g/t Au in drilling.", (3.28, 214.0, "Ag")),
    ("wedge_hole", "Cosa Reports 2,848 g/t Silver over 6.65 m in Wedge Hole",
     "June 2, 2026 - Picture of new intersection interval from hole CS-21-73W1 drilled this spring grading 2,848 g/t silver "
     "over 6.65m.", (6.65, 2848.0, "Ag")),
    ("prior_year_hole", "Radisson Continues to Expand Gold Mineralization with Latest Drill Results",
     "September 8, 2025 - Highlights include: OB-24-363 intersected 8.41 g/t gold over 2.2 metres in drilling at O'Brien.",
     (2.2, 8.41, "Au")),
    ("congratulate_team", "Americas Gold and Silver Announces High-Grade Infill Drill Results at Cosala",
     "May 5, 2025 - \"I'd like to congratulate the Cosala team,\" said the CEO. Hole CS-25-11 intersected 599.8 g/t Ag over 14.0 m.",
     (14.0, 599.8, "Ag")),
    ("previously_the", "Goliath Expands Bonanza Zone By 750 Meters",
     "July 15, 2026 - Previously the Golden Gate Zone contained 18 lodes with intercepts up to 34.52 g/t AuEq over 39.00 meters "
     "(drill hole GD-24-260). Assays are pending.", ("reject", 39.0, 34.52)),
    ("repeat_prev_reported", "Opus One Reports Final Results",
     "September 16, 2026 - The zone 1 shoot, outlined by Hole NO-26-21a (4.92 g/t gold over 11.37 metres), will be a focus of "
     "drilling. Previously reported hole NO-26-21a returned 4.92 g/t Au over 11.37 metres (June 17, 2026 press release). "
     "Hole NO-26-18 returned 2.34 g/t Au over 9.34 metres.", ("reject", 11.37, 4.92)),
    ("downhole_range", "Aston Bay Intersects Copper Outside Proposed Pit Designs",
     "October 20, 2025 - Drill hole PFS-002: 12.1 metres @ 5.6% copper from 70m. The drill hole intersected semi-massive "
     "chalcocite between 70-82.1m downhole at an average grade of 5.6% Cu.", ("reject", 82.1, 5.6)),
    ("threshold", "First Phosphate Provides Analytical Results for Infill Drill Program",
     "April 27, 2026 - In the Mountain Zone, several intervals exceeding 50 m with grades above 10% P2O5 were intersected.",
     ("reject", 50.0, 10.0)),
    ("reference_which", "Intrepid Metals Expands Ringo Footprint with Latest Drill Results",
     "September 9, 2025 - The latest drill hole, CC25_037 intersected 140.80m of 0.36% CuEq and is located roughly 90m "
     "northwest of CC24-019, which intersected 175.00m of 0.45% CuEq.", ("reject", 175.0, 0.45)),
]


# 1.0.2, second pass: releases read on 2026-09-17
CASES_V1 += [
    ("unreleased_year", "Company Reports Unreleased 2019 Drill Results from the Madison Project", "July 28, 2020 - Results from the "
     "2019 drilling program: hole MADN0010 cut 1.16 g/t Au over 74m.", (74.0, 1.16, "Au")),
    ("near_surface_not_ref", "Company Expands Discovery", "January 20, 2026 - This includes a broad interval of near surface\n"
     "gold mineralization in hole DSH-004 which returned 1.10 g/t gold over 15.50 metres.", (15.5, 1.10, "Au")),
    ("words_units", "Company Expands Porphyry", "April 9, 2026 - Core drilling results from ANRD041: 25.00 metres grading 0.55 percent "
     "copper (\"%\") and 0.16 grams per tonne (\"g/t\") gold.", (25.0, 0.55, "Cu")),
    ("feet_dot", "Company Confirms Mineralization Beneath Mine", "July 15, 2026 - Drill results include 45 ft. of 1.73g/t Au and "
     "34.7g.t Ag in drill hole BM26-01.", (13.716, 34.7, "Ag")),
    ("plain_hole_table", "Company Reports Drill Results", "July 28, 2020 - Table 1: Significant Drill Results\nHOLE ID\nFROM\n(m)\nTO\n(m)\n"
     "Interval\n(m)\nAg\n(g/t)\nAu\n(g/t)\nMADN0010 151.61 226 74.39 2.12 1.16\nMADN0011 182.00 184.54 2.54 44.5 1.42\n", (74.39, 1.16, "Au")),
    ("split_true_width", "Company Intersects Silver", "June 15, 2026 - TABLE 1: DRILL RESULTS\n\nHole No.\n\nFrom\n\nTo\n\nInterval\n\n"
     "Est. True\n\nGold\n\nSilver\n\n(metres)\n\n(metres)\n\n(metres)\n\nWidth (m)\n\n(g/t)\n\n(g/t)\n\nZ26-09\n\n158.10\n\n162.05\n\n"
     "3.95\n\n3.45\n\n2.95\n\n938.65\n", (3.95, 938.65, "Ag")),
    ("combined_with_new", "Company Drilling Expands Oxide Zones", "October 5, 2020 - When combined with previously reported drill "
     "results and the historic drilling, these new assays indicate a new zone. Results include:\n- Hole MHB-3: 47.2 m of 0.68% Cu", (47.2, 0.68, "Cu")),
    ("later_citation", "Company Expands Porphyry", "April 9, 2026 - Including 14.00 metres grading 0.84% copper\nThis intercept confirms "
     "the extension, as previously reported in ANRD049 interval of 120 metres grading 0.30% copper.", (14.0, 0.84, "Cu")),
    ("round_of_results", "COMPANY REPORTS HIGH-GRADE GOLD IN LATEST SIX DRILL HOLES & ANNOUNCES NON-BROKERED FINANCING",
     "February 23, 2022 - The Company reports on the Company's second round of results for its inaugural diamond drill program. "
     "Drill hole HR22-06 returned 3.52 m of 5.91 g/t Au.", (3.52, 5.91, "Au")),
    ("results_from_program", "Company Provides First Results from Underground Drilling Program; Samples up to 59.2 g/t Au",
     "August 18, 2026 - A horizontal hole extended the strike length including a 13.18 metre core length assaying 9.69 g/t Au.", (13.18, 9.69, "Au")),
]


# 1.0.2, corpus review (4,022 tagged releases, 2026-09-17)
CASES_V1 += [
    ("formula_footnote_stream", "Company Announces Assay Results from Winter Drill Program", "August 17, 2026 - Table 1: Intersections\n\nDDH\n\n"
     "From\n\n(m)\n\nTo\n\n(m)\n\nLength\n\n(m)\n\n9\n\nAverage Grade\n\n(% U3O8\n\n)\n\nWMA101-02\n\n3,6\n\n812.1\n\n817.5\n\n5.4\n\n1.48\n\n"
     "WMA101-03\n\n3,6\n\n822.5\n\n824.0\n\n1.5\n\n0.13\n", (5.4, 1.48, "U3O8")),
    ("negative_from_is_dip", "Company Reports Tungsten Drilling", "April 15, 2026 - Table 1\n\nHole ID\n\nZone\n\nLength (m)\n\nAzimuth\n\nDip\n\n"
     "From (m)\n\nTo (m)\n\nLength (m)\n\nWO3 (%)\n\nDDRCRG-25-025\n\nRhosgobel\n\n417.6\n\n205\n\n-65\n\n193.0\n\n263.7\n\n70.7\n\n0.149\n",
     ("reject", 263.7, 70.7)),
    ("feet_marked_rows", "Company Drilling Intersects Silver", "May 4, 2026 - Table 1: Significant intervals from drillhole BHE26-01\n"
     "Sample ID From To Zinc % Lead % Silver oz/t\nBHE26-01_176-176.8' 176 176.8 0.05 29.30 11.90\n"
     "BHE26-01_176.8-180' 176.8 180 0.03 0.69 0.52\n", (0.244, 11.9, "Ag")),
    ("recaps_headline", "Company Recaps 2019 and 2020 Drill Results from the Madison Project", "July 20, 2021 - Hole MADN0010 cut "
     "1.16 g/t Au over 74m.", ("reason", "recap")),
    ("listing_page", "Mining & Metals", "October 14, 2017 - Items per page: 25 per page. Eminent Hits 57.9 m @ 0.3 g/t Au of Oxide Gold",
     ("reason", "not_results")),
    ("gt_of_gold", "Company Finds More Gold", "April 9, 2024 - This year drilling in hole MLHL-24-53 intersected 4.04 grams per tonne of "
     "gold over 2.25 meters.", (2.25, 4.04, "Au")),
    ("decimal_comma_zero", "Company Drills Gold", "March 3, 2026 - Table 1: 2025 Drill Results\nArea Hole No From (m) To(m) Interval(m)  Au (g/t) Note\n"
     "Grondin GR-25-02 20 24 4 2\nGrondin GR-25-03 55 55,5 0,5 0,106\n", ("reject", 0.5, 106.0)),
    ("unknown_width_footnotes", "Company Drills Sulphide Mineralization", "January 20, 2026 - Table 1: 2025 Surface Drilling Results\nHole-ID\nFrom\n(m)\n"
     "To\n(m)\nLength\n(m)\nEst. True\nThickness\n1\nCu\n(%)\nNi\n(%)\n2\nZone\nCuEq\n(%)\n3\nSMD-25-201\n1829.15\n1831.75\n2.60\n2.37\n0.53\n"
     "0.69\nLower Zone\n3\n1.95\nSMD-25-202\n1753.95\n1754.65\n0.70\nunknown\n0.81\n2.39\nMain Zone\n5.73\n", (0.7, 5.73, "CuEq")),
    ("title_hole_range", "Company Reports Final Drilling Assays", "September 16, 2025 - Table 1: Assay Results for Drill Holes SG016-SG029 "
     "(Holes SG016-SG022 Previously Reported)\nHole ID From (m) To (m) Length (m) Ag (g/t) AgEq (g/t)\nSG016 10.0 12.0 2.0 50.0 60.0\n"
     "SG027 89.0 93.8 4.8 152.9 167.1\n", (4.8, 167.1, "AgEq")),
]


def self_test(verbose: bool = True) -> int:
    bad = 0

    def accepted(hl, body):
        a = analyse(hl, body)
        return a, [x for x in a["intervals"] if not x["reason"]]

    def show(ok, label):
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  {label}")

    for hl, L, G, M in D.FIND_TEST:
        _, its = accepted(hl, "")
        ok = any(abs(i["length_m"] - L) < 0.05 and abs(i["grade"] - G) < 0.005 and i["metal"].lower() == M.lower()
                 for i in its)
        bad += not ok
        show(ok, f"find {hl[:60]}")
    for change, hl, body, L, G, M in D.FIND_TEST_V24:
        _, its = accepted(hl, body)
        ok = any(abs(i["length_m"] - L) < 0.05 and abs(i["grade"] - G) < 0.005 and i["metal"].lower() == M.lower()
                 for i in its)
        bad += not ok
        show(ok, f"find[{change}] {hl[:50]}")
    for hl, body in D.REJECT_TEST:
        _, its = accepted(hl, body)
        ok = not its
        bad += not ok
        show(ok, f"reject {hl[:56]}")
    for change, hl, body, forbid in D.REJECT_TEST_V24:
        _, its = accepted(hl, body)
        ok = (not its) if forbid is None else not any(
            abs(i["length_m"] - forbid[0]) < 0.05 and abs(i["grade"] - forbid[1]) < 0.005 for i in its)
        bad += not ok
        show(ok, f"reject[{change}] {hl[:50]}")
    for rule, hl, body, want in CASES_V1:
        a, its = accepted(hl, body)
        if want[0] == "reject":
            ok = not any(abs(i["length_m"] - want[1]) < 0.05 and abs(i["grade"] - want[2]) < 0.005 for i in its)
        elif want[0] == "reason":
            ok = not its and a["reason"] == want[1]
        else:
            ok = any(abs(i["length_m"] - want[0]) < 0.05 and abs(i["grade"] - want[1]) < 0.005
                     and i["metal"] == want[2] for i in its)
        bad += not ok
        show(ok, f"v1[{rule}] {hl[:50]}")

    # ---------------------------------------------------------------- 1.0.3
    def topof(hl, body):
        a = analyse(hl, body)
        ivs = a.get("intervals") or []
        t = a.get("top")
        return a, (ivs[t] if isinstance(t, int) and 0 <= t < len(ivs) else None)

    a, top = topof("Eloro Reports 90.92 g/t Ag over 309.0 m at Iska Iska",
                   "The high grade intersection above from hole DSB-75 includes 962.23 g/t Ag over 9.75m within a "
                   "wider zone of 34.50m grading 440.09 g/t Ag at the Iska Iska Project.")
    ok = top is not None and top.get("hole") == "DSB-75"
    bad += not ok
    show(ok, "103 headline intercept takes the hole the body credits")

    a, top = topof("Revival Gold Reports 14.9 g/T Gold over 5.9 Metres at Mercur",
                   "Highlights Hole BT26-254D intercepted: 2.37 g/T gold over 147.2 meters drilled width at 808 meters "
                   "downhole including: 9.3 g/T gold over 3.5 meters drilled width at 818 meters downhole; 14.9 g/T gold "
                   "over 5.9 meters drilled width at 831 meters downhole. The Mercur Project is in Utah.")
    ok = top is not None and abs(top["length_m"] - 147.2) < 0.05
    bad += not ok
    show(ok, "103 every item of an including list is a sub-interval")

    a, top = topof("Nord Drills 1.0 m of 29.2% Cu",
                   "Hole FNX6083-W1 returned 12.8% Cu over 2.6 metres, including 29.2% Cu over 1.0 metre, at the "
                   "Levack Mine Property.")
    ok = top is not None and abs(top["length_m"] - 2.6) < 0.05
    bad += not ok
    show(ok, "103 a headline sub-interval loses to its parent")

    a, top = topof("AbraSilver Reports Gold and Silver Results from Diablillos",
                   "Hole DDH-26-047 intersected 1.50 g/t Au and 4.60 g/t Ag over 14.0 metres at the Diablillos Project.")
    ok = top is not None and top["metal"] == "Au"
    bad += not ok
    show(ok, "103 the metal the headline names first is the one ranked")

    a, _ = topof("Cambria Reports Results From 2025 Drilling",
                 "Hole P25-2659a returned 20.75 g/t Au over 15.9 m on the Big Missouri deposit, part of the "
                 "Premier Gold Project.")
    ok = a.get("project") == "Premier Gold"
    bad += not ok
    show(ok, "103 a property outranks a deposit inside it (got %r)" % (a.get("project"),))

    # ---------------------------------------------------------------- 1.0.4
    a, top = topof("Cowley Park Drilling Extends Copper Mineralization",
                   "Key results from the west side of the Northern Limb include: CPG-112D2 returned 130m @ 0.78% Cu "
                   "from 2m, including: 92m @ 1.03% Cu from 2m. CPG-118 returned 40m @ 0.30% Cu from 10m at the "
                   "Cowley Park Project.")
    ok = top is not None and top.get("hole") == "CPG-112D2"
    bad += not ok
    show(ok, "104 a wedge hole keeps its suffix (got %r)" % (None if top is None else top.get("hole"),))

    a, top = topof("Ongwe Minerals Intersects High Grade Gold at Belmont Prospect",
                   "Best RC drill hole intersections at the BK2 Target: BKR010 3m @ 9.21 g/t Au from 17m, and 5m @ "
                   "0.90 g/t Au from 39m. The Company confirms that hole BKR010 was drilled at the Khorixas Project.")
    ok = top is not None and top.get("hole") == "BKR010"
    bad += not ok
    show(ok, "104 an id the release confirms elsewhere counts where it has no hyphen (got %r)"
         % (None if top is None else top.get("hole"),))

    a, top = topof("Hemlo Mining Intersects 89.9 g/t Au over 3.0 Metres at South-Rim",
                   "Highlights: New South-Rim results include 89.89 g/t Au over 3.0 metres in hole 6702608 and "
                   "14.81 g/t Au over 10.0 metres in hole 6702632 at the South-Rim Project.")
    ok = top is not None and top.get("hole") == "6702608"
    bad += not ok
    show(ok, "104 a hole numbered only in digits (got %r)" % (None if top is None else top.get("hole"),))

    a, top = topof("Bonterra Intersects High-Grade Visible Gold at O'Brien East Deep",
                   "O'Brien East Deep Target - 4.75 g/t Au over 1.4 m. including 16.03 g/t Au over 0.4 m (visible "
                   "gold or VG), in hole BRDS-26-114, and 0.71 g/t Au over 2.2 m, in hole BRDS-26-124A at the "
                   "Desmaraisville South Project.")
    ok = top is not None and top.get("hole") == "BRDS-26-114"
    bad += not ok
    show(ok, "104 an including clause does not hide the hole the parent is credited to (got %r)"
         % (None if top is None else top.get("hole"),))

    a, top = topof("Silver Acadia Reports Final Phase 1 Drill Results at Nicholas-Denys",
                   "Highlight assay results: Hole ND26-004 - Hachey Zone 1.1 m @ 467 g/t Ag. Hole ND26-006 - Hachey "
                   "Zone 8.6 m @ 91.5 g/t Ag 5.5 m @ 374 g/t Ag including 1.8 m @ 878.8 g/t Ag at the Nicholas-Denys "
                   "Project.")
    ok = top is not None and top.get("hole") == "ND26-006"
    bad += not ok
    show(ok, "104 the nearest hole heading before an intercept owns it (got %r)"
         % (None if top is None else top.get("hole"),))

    a, top = topof("Altamira Extends Gold Mineralization West at Maria Bonita",
                   "Drill holes MBA036 through MBA039 have each intersected wide zones of gold mineralization "
                   "outside the current mineral resource boundary (including 130m @ 0.5 g/t gold in MBA036), "
                   "progressively extending the system to the west at the Maria Bonita Project.")
    ok = top is not None and top.get("hole") == "MBA036"
    bad += not ok
    show(ok, "104 a hole credited without the word hole (got %r)" % (None if top is None else top.get("hole"),))

    a = analyse("Investigator Returns 14.10 g/t Gold over 1.59 m at Trench 1",
                "Drill hole TR1-26-144 was completed west of the bulk sample site. Grade-control drilling "
                "returned highlight intersections of: 14.10 g/t gold over 1.59 m, including 47.87 g/t gold over "
                "0.46 m (TR1-26-145); 7.58 g/t gold over 2.35 m, including 34.28 g/t gold over 0.40 m "
                "(TR1-26-140) at the Trench 1 Project.")
    iv0 = (a.get("intervals") or [None])[0]
    ok = iv0 is not None and iv0.get("hole") == "TR1-26-145" and abs(iv0["length_m"] - 1.59) < 0.01
    bad += not ok
    show(ok, "104 a bracketed hole after an including clause still credits the parent (got %r)"
         % (None if iv0 is None else iv0.get("hole"),))

    # ---------------------------------------------------------------- 1.0.5: From-To from prose and far tables
    def depths(hl, body, L, G):
        a = analyse(hl, body)
        iv = next((x for x in a.get("intervals") or [] if abs(x["length_m"] - L) < 0.05 and abs(x["grade"] - G) < 0.005), None)
        return None if iv is None else (iv.get("from_m"), iv.get("to_m"))

    for label, hl, body, L, G, want in [
        ("from only", "Alotta Drills 3.4 g/t Gold over 44.75 Metres",
         "Drill hole ALT-25-012 intersected 3.4 g/t gold over 44.75 metres from 256.23 metres at the Payoff Zone.",
         44.75, 3.4, (256.23, 300.98)),
        ("from and to", "Tuning Fork Drill Results",
         "Drill hole TF-25-16 returned 0.87% U3O8 over 1.0 metres from 183.0 to 184.0m at the Tuning Fork target.",
         1.0, 0.87, (183.0, 184.0)),
        ("to must agree with the length", "Tuning Fork Drill Results",
         "Drill hole TF-25-16 returned 0.87% U3O8 over 1.0 metres from 183.0 to 189.0m at the Tuning Fork target.",
         1.0, 0.87, (None, None)),
        ("starting at a depth", "Elida Drill Results",
         "Hole ELID037 intersected 401.0 m grading 0.71% CuEq, starting at a depth of 401.0 m, at the Elida Project.",
         401.0, 0.71, (401.0, 802.0)),
        ("from surface", "Apollo Drill Results",
         "Hole APC-147 drilled to the northwest returned 84.55 metres @ 2.04 g/t gold equivalent from surface at Apollo.",
         84.55, 2.04, (0.0, 84.55)),
        ("not across another interval", "Drill Results",
         "Hole TF-25-16 returned 0.22% U3O8 over 0.9 metres. Assay results indicate 6.2 metres (from 144.0 to 150.2 metres) "
         "of total mineralization at the Tuning Fork target.",
         0.9, 0.22, (None, None)),
        ("bracketed sub-interval: the depth is the parent's", "Drill Results",
         "Drill hole TGC-0447 returned 56.59 g/t Au over 1.3 m (including 62.39 g/t Au over 0.9 m) (TGC-0447, from 92 m depth) "
         "at the Tonopah project.",
         1.3, 56.59, (92.0, 93.3)),
        ("no depth without a unit", "Drill Results",
         "Hole AB-26-01 returned 2.5 g/t Au over 12.0 m from 12 samples at the Main Zone.",
         12.0, 2.5, (None, None)),
    ]:
        got = depths(hl, body, L, G)
        ok = got == want
        bad += not ok
        show(ok, "105 %s (got %r)" % (label, got))
    cols = header_columns("From (m) To (m) Downhole Interval (m) ETW (m) Au (g/t) Horizon")
    ok = bool(cols) and [c[0] for c in cols] == ["from", "to", "len", "tw", "metal", "text"]
    bad += not ok
    show(ok, "105 a Horizon column is text (got %r)" % (cols,))
    # 1.0.6: the shared helper
    got = [_pn_page(n) for n in ("Lac Dor\u00e9 Vanadium Property", "Campo Morado polymetallic VMS Mine",
                                 "Ishk\u014dday Gold and Polymetallic Project", "Tom and Jason Deposits", "Eagle River Underground Mine")]
    ok = got == ["Lac Dor\u00e9 Vanadium", "Campo Morado", "Ishk\u014dday Gold", None, "Eagle River"]
    bad += not ok
    show(ok, "106 helper names in this page's form (got %r)" % (got,))
    got = [_pn_not_a_name("VMS", "Drilling at the Caba\u00e7al Mine."), _pn_not_a_name("Current", "the Current Project, Ontario"),
           _pn_not_a_name("Premier", "Cambria's Premier Gold Project in BC")]
    ok = got == [True, False, False]
    bad += not ok
    show(ok, "107 a name that is no project, and real names the helper would not read (got %r)" % (got,))
    ok = "FP" in _code_sha.__code__.co_names and FP.borrowed_source(PN, "PN", __file__).split("\n")[0] != "uses "
    bad += not ok
    show(ok, "108 the fingerprint covers the helper")

    # ---------------------------------------------------------------- 1.0.8: what the release announces (NEWS_V1)
    def news(hl, body):
        a = analyse(hl, body)
        return a["is_result"], a["reason"]
    for label, hl, body, want in [
        ("a program start quoting a hole is no result", "Company Starts Drilling at Alpha",
         "March 3, 2026 - Company Corp. is pleased to announce that drilling has started at its Alpha Project, where hole "
         "AB-25-05 returned 12.0 m of 3.1 g/t Au.", (False, "plan")),
        ("assays pending: the headline's hit is visual", "Company Intersects Massive Sulphides in First Hole - Assays Pending",
         "March 3, 2026 - Company Corp. is pleased to announce that hole AB-26-01 intersected 12.0 m of massive sulphides. "
         "Hole AB-25-05 returned 3.1 g/t Au over 12.0 m.", (False, "pending")),
        ("scintillometer readings are no assays", "Company Drills Radioactive Zones at Beta",
         "March 3, 2026 - Company Corp. is pleased to report hand-held scintillometer readings from its first holes at Beta. "
         "Hole BE-25-02 returned 0.8 m of 1.1% U3O8.", (False, "instrument")),
        ("an option agreement quoting an old hole", "Company Options the Delta Property to Partner Corp.",
         "March 3, 2026 - Company Corp. announces that it has entered into an option agreement with Partner Corp. on the "
         "Delta Property. Hole DL-25-01 returned 5.0 m of 2.0 g/t Au.", (False, "not_results")),
        ("paid commentary restates another company's release", "Every Drillhole Hits at Omega",
         "NEW YORK, March 3, 2026 -- USA News Group News Commentary -- Omega Corp. has reported that hole OM-26-01 "
         "returned 14.9 m of 0.32% Sb.", (False, "investee")),
        ("an update with no statement of results and no lead result", "Company Provides Exploration Update",
         "March 3, 2026 - Company Corp. is pleased to provide an update on exploration at its Zeta project. Mapping "
         "continues. The Zeta zone hosts drill intercepts such as 2.1 g/t Au over 9.0 m.", (False, "no_new_results")),
        ("a completed program whose lead reports assays received", "Company Completes Phase 1 Drilling at Eta",
         "March 3, 2026 - Company Corp. is pleased to announce it has completed Phase 1 drilling at Eta. Assays have been "
         "received for the first three holes. Hole ET-26-01 returned 6.0 m of 5.5 g/t Au.", (True, None)),
        ("results statement keeps the row", "Company Reports Drill Results from Epsilon",
         "March 3, 2026 - Company Corp. is pleased to report assay results from three holes. Hole EP-26-01 returned 8.0 m "
         "of 4.2 g/t Au.", (True, None)),
        ("the statement calls the results historical", "Company Reports 108.4 g/t Gold over 7 Metres at Theta",
         "March 3, 2026 - Company Corp. is pleased to provide drilling plans and historical results at Theta. Selected "
         "historical drilling intersected 108.4 g/t gold over 7 metres (DDH81-43).", (False, "historical")),
    ]:
        got = news(hl, body)
        ok = got == want
        bad += not ok
        show(ok, "108n %s (got %r)" % (label, got))

    # ---------------------------------------------------------------- 1.0.9: what the release is about (NEWS_V2)
    def news2(hl, body):
        h, raw = repair(hl), repair(body)
        kind, why = release_news(h, D._prep(D.lede(raw)), dateline(raw))
        a = analyse(hl, body)
        return (kind == "results" and a["is_result"], None if kind == "results" else why)
    for label, hl, body, want in [
        ("a second rig at work, last year's intercepts quoted", 'Company Adds Second Drill; Provides Drilling Update',
         'June 10, 2026 - Company Corp. is pleased to announce that a second diamond drill rig is now '
         'operational at its Alpha project. Intercepts from 2025 include 900 m of 0.50% CuEq from '
         'surface in hole AL25-12.', (False, 'plan')),
        ("'three drills' is a noun, not the verb", 'Company Increases to Three Drills at Beta',
         'June 23, 2026 - Company Corp. is pleased to announce the addition of one diamond drill rig at '
         'Beta. Deeper holes including BE-25-92 (66.71 g/t Au over 4.70 m) highlight the potential at '
         'depth.', (False, 'plan')),
        ('samples sent to the lab', 'Company Samples from the First 6 Holes at Sigma were Sent to the Lab',
         'April 25, 2026 - Company Corp. (the \u201cCompany\u201d) has completed the first 6 holes at Sigma, where '
         'hole SI-25-012 intersected 5.37 g/t Au over 19.8 metres.', (False, 'plan')),
        ('targets defined after re-logging', 'Company Defines Exploration Targets at Delta',
         'September 17, 2026 - Company Corp. is pleased to announce that it has refined several drill '
         'targets at Delta. The deepest hole (DE-210) assayed 21.2 m of 8.16 g/t Au.', (False, 'not_results')),
        ('a look back with goals', 'Company Provides Year-End Update',
         'December 17, 2026 - Company Corp. is pleased to review its successful 2026 exploration results '
         'and share its goals for 2027. In May the Company intersected 301.67 g/t gold over 3.90 metres.', (False, 'recap')),
        ("an investor's equity portfolio update", 'Company Provides Second Quarter Project Generation Update',
         'July 10, 2026 - Company Corp. is pleased to update its project generation activities and its '
         'junior equities portfolio. Investee Corp. continues to release drill results; recent '
         'highlights include 79 metres at 238 g/t from hole DDH 26-029.', (False, 'investee')),
        ('agreements signed and ground consolidated', 'Company Signs Two Agreements and Consolidates Ground at Epsilon',
         'January 31, 2026 - Company Corp. is pleased to announce agreements on the Epsilon project. A '
         'drill-hole intersection averaged 1.41 g/t Au across 30.0 metres in hole EP-95-08.', (False, 'not_results')),
        ('an approval for a land lease', 'Company Receives Approval for Conversion of Zeta Claims to Land Lease Status',
         'December 21, 2026 - Company Corp. provides a corporate and project update on Zeta. Drilling '
         'highlights include: ZE-25-080 intersected 8.25 g/t Au over 9.0 m.', (False, 'not_results')),
        ('historic resources, clarifying disclosure', 'Historic Resources at Eta, additional and clarifying disclosure',
         'November 6, 2026 - Company Corp. clarifies its disclosure of the historical resource estimate '
         'at Eta. The cut-off was 1.5 m of 1% combined Cu + Ni.', (False, 'historical')),
        ('a company anticipating its remaining assays', 'Company Anticipates Remaining 2026 Drill Assays; Provides Summary of Program',
         'December 20, 2026 - Company Corp. is pleased to provide a summary of its 2026 exploration. '
         'Phase I results were announced earlier this year, such as 12.45 g/t Au over 5.15 m.', (False, 'pending')),
        ('results of surface work', 'Company Announces More 2026 Surface Exploration Highlights',
         'December 11, 2026 - Company Corp. is pleased to announce further results from surface work '
         'completed during 2026. All drill holes yielded gold values, including 5.32 g/t gold over 2.75 '
         'm.', (False, 'surface')),
        ('a sampling headline is not made drilling by a results statement', 'Company Reports Underground Sampling Results 79.45 oz/t Au over 5.5 ft.',
         'July 7, 2026 - Company Corp. is pleased to announce results from its ongoing underground '
         'exploration program at Theta. 79.45 oz/t Au over 5.5 ft.', (False, 'surface')),
        ('a vague statement is explained by the next one', 'Company Announces Milestone Event on its Properties',
         'February 17, 2026 - Company Corp. is pleased to report a major milestone for its property '
         'portfolio. The Company is pleased to announce that it has made the final option payments on '
         'its Iota property. Highlights of our drilling have so far returned 114.96 g/t Au over 2.55 '
         'meters in hole 12.', (False, 'not_results')),
        ("no 'is pleased to': the defined name is followed by the news", 'Company Provides Update on Kappa',
         'November 8, 2026 - Company Corp. (TSX-V: ABC) (the \u201cCompany\u201d or \u201cAbc\u201d) plans to commence the '
         'initial drill program at Kappa. Historical drilling used RC rigs. The initial targets include: '
         '1. Area of KA-RC-0002 which intersected 72 meters grading 1.21% copper.', (False, 'plan')),
        ('a hole cited as reported before is background where it recurs', 'Company Intersects Pegmatite in 9 Holes',
         'January 26, 2026 - Company Corp. ispleased to provide an update on Lambda. Assays are '
         'available from the discovery hole LA25069 (as reported January 20, 2026). Discovery hole '
         'LA25069 intersected 47.75m of 1.34% Li2O.', (False, 'no_new_results')),
        ('a figure whose citation follows it', 'Company Provides Update on Mu',
         'October 10, 2026 - Company Corp. is pleased to provide an update on Mu. The spring drilling '
         'program yielded 1.62% Li2O over 158.0 m in hole MU-26-01. (see press release of June 19, 2026).', (False, 'no_new_results')),
        ('holes whose id carries an earlier year with no separator', 'Company Provides an Update on Nu',
         'April 28, 2026 - Company Corp. is pleased to provide an update on Nu. Inaugural drilling in '
         '2022 returned 39.80m @ 1.09 g/t Au from DDH NU22004. Zone drilling results included NU23026 '
         'which returned 29.44m @ 1.30 g/t Au.', (False, 'no_new_results')),
        ('no dateline: the year the statement names dates the release', 'Company Moves Drill to Xi',
         'Company Corp. is pleased to provide an update on its 2026 diamond drill program activity at '
         'Xi. The Company drilled 3 holes in 2017. Highlights included 1.33% Li2O over 5.3m in hole '
         'X-17-01.', (False, 'no_new_results')),
        ('an update whose lead reports a fresh hole keeps its row', 'Company Provides Exploration Update at Omicron',
         'April 28, 2026 - Company Corp. is pleased to provide an exploration update for Omicron. Hole '
         'OM26-001 was the first hole drilled and returned 9.1 meters grading 0.51 g/t gold.', (True, None)),
        ("a quoted second statement is not the company's", 'New Gold Discovery at Pi',
         'October 19, 2026 - Company Corp. announces a new discovery of gold mineralization at Pi. '
         'Highlights include: 1.17 g/t gold over 45.7 meters (hole PI-26-005). The VP stated: \u201cWe are '
         'pleased to report this discovery on one of the 32 targets so far identified.\u201d', (True, None)),
        ("a property named 'Consolidated' is no consolidation", 'Company Confirms New VMS System at Rho',
         'January 18, 2026 - Company Corp. is pleased to announce it has confirmed a VMS system on its '
         'Consolidated Rho Property. Preliminary results from the first drill holes include 2.47 g/t Au '
         'over 11.34m in hole RH25-10.', (True, None)),
    ]:
        got = news2(hl, body)
        ok = got == want
        bad += not ok
        show(ok, "109n %s (got %r)" % (label, got))

    # ---------------------------------------------------------------- 1.0.9 FIX3: full-text losses (real news kept)
    news_cases = [
        ("a citation after the company's own claim is about the program",
         "Company Returns 40.61 g/t Gold over 2.6 Metres at Alpha",
         "June 25, 2026 - Company Corp. is pleased to announce diamond drill results for one hole from the recently completed "
         "(See News Release: June 11, 2026) three hole program at the Alpha Project. Hole AL-26-75 returned 40.61 g/t Au over 2.6 m.",
         (True, None)),
        ("a statement that cites the program, not results, stays background",
         "Company Provides Progress Update at Beta",
         "June 25, 2026 - Company Corp. is pleased to announce progress for the previously announced 2026 campaign at Beta. "
         "Earlier work returned 3.1 g/t Au over 2.0 m.",
         (False, "previously_reported")),
        ("a second statement of new results after a corporate one",
         "Company Increases Exploration Target at Lambda",
         "September 24, 2026 - Company Corp. is pleased to announce that drilling supports an increase to the exploration target at "
         "Lambda. Additionally, the Company is pleased to release updated exploration results highlighting high-grade gold "
         "intersections. Recent drilling returned 38.4 metres @ 8.1 g/t gold in hole LA-26-14.",
         (True, None)),
        ("named holes ahead of a project's study stage",
         "Company Extends Zone 80 m Down-Dip at Delta",
         "October 20, 2026 - Company Corp. is pleased to present assay results from drill holes DE26-31 and DE26-32 at its "
         "preliminary economic stage Delta project. DE26-32 intersected 1.1 g/t Au over 90.7 m.",
         (True, None)),
        ("drill results first, a feasibility update after",
         "Company Reports Infill Drill Results and Feasibility Study Update",
         "June 22, 2026 - Company Corp. provides an update on the feasibility study at Epsilon. Hole EP-066 returned 105.0 m "
         "grading 1.10 g/t gold.",
         (True, None)),
        ("a resource update that follows drill results is not a results release",
         "Company Undertakes a Mineral Resource Estimate Update following Positive Drill Results",
         "August 13, 2026 - Company Corp. is delighted to announce the commencement of a mineral resource update at Zeta. Key "
         "results to date (NR dated July 22, 2026) include ZE24-114 with 1.67% Li2O over 105.6 metres.",
         (False, "not_results")),
        ("completion of drilling, and further drill results",
         "Company Announces the Completion of Drilling at Eta, and Further Drill Results",
         "December 13, 2026 - Company Corp. is pleased to update investors on the completion of the Phase 2 drilling programme at "
         "Eta. Three holes were drilled at the CBZ and returned 0.54 g/t Au over 47.8 m (ET-093).",
         (True, None)),
        ("a visual sub-headline run on after the assayed figure",
         "Company Intersects 30.7m of 1.05% Cu and 1.34 g/t Au at the Theta VMS Deposit in the northern district Significant visual sulfides "
         "encountered in all four holes drilled",
         "April 27, 2026 - Company Corp. is pleased to provide an update on the drilling program at Theta. Assay results from the "
         "first hole (TH26-007) have been received.",
         (True, None)),
        ("a completed program whose headline gives its holes' figures",
         "Company Completes 2026 Drilling at Iota IO380: 1.52 g/t Au over 30.5 m and 2.44 g/t Au over 21.3 m",
         "December 6, 2026 - Company Corp. is pleased to announce that the 2026 drilling campaign at Iota was completed. Hole "
         "IO380 returned 1.52 g/t Au over 30.5 m.",
         (True, None)),
        ("'Drilling Discovers' is a drill claim",
         "Company Phase II Drilling Discovers New High-Grade Zone at Kappa",
         "May 17, 2026 - Company Corp. is pleased to report a new high-grade zone from the Phase II program completed in Q1 at "
         "Kappa. Hole KA-DDH-005 intersected 10.80m at 625 g/t Ag.",
         (True, None)),
        ("'summarized in Table One' lays out new results",
         "Company Reports Gold Intersections in Holes LA-15 and LA-16",
         "March 19, 2026 - Company Corp. is pleased to report the Company has received the preliminary gold analyses for drill "
         "holes LA-15 and LA-16, summarized in Table One. Hole LA-16 returned 1.35 g/t Au over 4.1 m.",
         (True, None)),
        ("soil anomalies that targeted the drilling are no surface samples",
         "Company Announces High Grade Results at Mu Target",
         "May 12, 2026 - Company Corp. is pleased to announce additional results from Mu, which tested targets based on soil and "
         "geophysical anomalies. Hole MU-616 intersected 9.0 metres grading 16.90 g/t Au.",
         (True, None)),
        ("an update on drilling progress is an update, not a plan",
         "Company Finds More Gold at Nu",
         "April 9, 2026 - Company Corp. is pleased to provide an update on the recent exploration drilling progress at Nu. This "
         "year drilling in hole NU-26-50 intersected 13.96 grams per tonne of gold over 1.17 meters.",
         (True, None)),
        ("drilling that 'has confirmed and extended' is a drill claim",
         "Company Confirms Mineralization in Underground Drilling at Xi",
         "September 9, 2026 - Company Corp. is pleased to announce that ongoing underground drilling has confirmed and extended "
         "the previously announced mineralization at Xi. Follow-up drilling has now intersected 6.19 g/t Au over 10.89 metres in "
         "hole XI26068.",
         (True, None)),
        ("'Preliminary results include' reports new assays",
         "Near-Mine Mineralization Confirmed at Omicron",
         "October 21, 2026 - Company Corp. is pleased to provide an update on recent drilling at Omicron. Preliminary results "
         "include 8 m @ 4.6 g/t Au from 26 m and 10 m @ 3.0 g/t Au from 32 m.",
         (True, None)),
        ("a table caption of assay data",
         "Company Completes Drilling at Pi",
         "October 11, 2026 - Company Corp. is pleased to announce completion of the program at Pi. Table 1. Drill hole assay data from the Pi drilling. PI26-01 from 203 to 214.5 m: "
         "11.5 m of 0.22% Cu.",
         (True, None)),
        ("a run-on table is judged by its opening",
         "Company Encounters Multiple Gold Veins at Rho",
         "September 10, 2026 - Company Corp. is pleased to announce that hole RH26-001 has encountered multiple mineralized vein "
         "zones. Significant assays are tabulated below: RH26-001 from 444.0 to 449.0 m returned 5.00 m of 2.90 g/t Au, "
         + "| 1.0 | 1.2 | 0.55 " * 40 + "recovery of both metals is expected to be +95% as smelter flux and the hole is open.",
         (True, None)),
        ("'intersected by drilling', grams per tonne written out",
         "Drilling Confirms High Grade Gold Mineralization at Sigma",
         "January 20, 2026 - Company Corp. is pleased to announce that vein hosted gold mineralization, with a weighted average "
         "of up to 25.07 grams per tonne (g/t) over 2.1 metres true width, was intersected by drilling on the Sigma Zone.",
         (True, None)),
        ("a hole named in one sentence owns the figures of the next",
         "Company Drilling Intersects Significant Zinc Mineralization",
         "January 24, 2026 - Company Corp. is pleased to announce that its partner has intersected high grade mineralization in "
         "their first drill hole at Tau. Hole TA26-79 intersected a significant zone of zinc mineralisation. True width is "
         "approximately 55%. \u2022 7.47 metres (24.5 feet) at 25.55% zinc and 0.87% copper from 412.81 metres.",
         (True, None)),
        ("'the most significant intercept' after a citation is background",
         "Company Exhibits at a Convention",
         "February 24, 2026 - Company Corp. is pleased to announce that it will exhibit at a convention. Initial drilling by a "
         "major in 1997 included 12 shallow holes. (Refer to the Company's news release of March 4, 2024). The most significant "
         "intercept from Hole 001-97 returned 131 metres grading 2.55 g/t gold from surface.",
         (False, "no_new_results")),
        ("'no previous drilling' is no background",
         "Company Discovers New High Grade Zone at Upsilon",
         "September 19, 2026 - Company Corp. is pleased to announce the discovery of a new high grade zinc zone in an area that "
         "had no previous drilling. The discovery hole UP092 intersected 6.2 metres of 12.99% zinc.",
         (True, None)),
        ("a hand-held spectrometer reading is an instrument",
         "Company Intersects Strong Uranium Mineralization at Phi",
         "January 28, 2026 - Company Corp. is pleased to announce that it has intersected intervals of strong (>20,000 total cps "
         "on a hand-held spectrometer) uranium mineralization at Phi. Hole PH26-01 intersected 2.05% U3O8 over 0.8 metres.",
         (False, "instrument")),
        ("significant intersections of holes from an earlier year",
         "Company Provides an Update on Chi",
         "April 28, 2026 - Company Corp. is pleased to provide an update on Chi. Inaugural drilling in 2022 returned 39.80m @ "
         "1.09 g/t Au from DDH CH22004. Significant intersections include: CH23008: 6.75 m @ 0.95 g/t.",
         (False, "no_new_results")),
    ]
    top_cases = [
        ("a citation after the figure that closes a clause about another hole",
         "Company Drills 1.30 g/t AuEq over 59m at Psi",
         "May 9, 2026 - Company Corp. reports assay results from Psi. 1.30 g/t AuEq over 59m in hole PS-26-038, confirming "
         "continuity 100m down-dip of previously reported hole PS-26-027 (see March 23, 2026 press release) which intersected "
         "2.72 g/t AuEq over 50m.", (59.0, 1.30, "AuEq")),
        ("the citation of another hole named below the figure",
         "Company Intersects 6.2 g/t Gold over 14.2 Meters within 3.6 g/t Gold over 51.5 Meters at Omega",
         "September 12, 2026 - Company Corp. is pleased to announce initial results from its 2026 drilling program at Omega. "
         "OM26-241D intersected 6.2 g/t gold over 14.2 meters within 3.6 g/t gold over 51.5 meters approximately 100 meters "
         "below hole OM18-220D, the most southerly intersection to-date (8.84 g/t gold over 3.0 meters (see press release dated "
         "December 4th, 2018).", (51.5, 3.6, "Au")),
        ("a quotation that mentions historic results",
         "Company Intersects 1.11 g/t Gold over 6.1 Metres at Alpha",
         "January 21, 2026 - Company Corp. is pleased to announce initial drill results from Alpha. Results include: 0.45 g/t "
         "gold over 33.5 metres including 1.11 g/t gold over 6.1 metres \"The initial assay results fall in range with "
         "expectations and historic results,\" commented the President.", (33.5, 0.45, "Au")),
        ("'(both previously released)' cites the figure before it",
         "Company Extends Mineralization at Beta",
         "November 11, 2026 - Company Corp. today reported new results from drilling at Beta. New highlights include 12.03 g/t "
         "Au over 8.26 m (BE-602-23). These holes extend mineralization from drillhole BE25-04 (28.97 g/t Au over 21.76 m) "
         "(both previously released; see press release dated June 15, 2026).", (8.26, 12.03, "Au")),
        ("'further to its news release' introduces new results",
         "Company's Partner Drills 43.66 metres of 1.76 g/t Gold at Gamma",
         "January 19, 2026 - Company Corp. is pleased to announce that, further to its news release of November 2, 2025, it has "
         "received assays for two additional drill holes at Gamma: Drill hole 17 contained 43.66 metres of 1.76 g/t gold.",
         (43.66, 1.76, "Au")),
        ("a lead-in the repeat inherits does not overrule the headline",
         "Company Intersects 11.45 g/t Gold Over 33 Meters at Delta",
         "Company Intersects 11.45 g/t Gold Over 33 Meters at Delta\nJanuary 9, 2026 - Company Corp. is pleased to provide assay "
         "results from the last hole of its drill program at Delta.\nHistorical underground grades were 8 to 10 g/t gold from two "
         "shafts.\nHighlights:\n11.45 g/t in drill hole DE-26-A from 0 to 33 m core length.", (33.0, 11.45, "Au")),
        ("a reporting cut-off is no interval",
         "Company Extends Uranium Mineralization at Epsilon",
         "June 1, 2026 - Company Corp. today shared results from initial exploration drilling at Epsilon. The final results are "
         "reported for the initial 17 holes. Holes with less than 2 ft of 0.02% U3O8 are not reported in the table.", None),
        ("an earlier year's discovery is background",
         "Company Extends Mineralization at Zeta",
         "December 7, 2026 - Company Corp. is pleased to provide an update on its exploration at Zeta. Building upon the 2025 "
         "discovery of 119.20 metres of 0.97 g/t Au, six 2026 drillholes confirmed multiple zones. Hole ZE26003 intercepted "
         "10.00 m of 3.01 g/t Au.", (10.0, 3.01, "Au")),
        ("a grid-numbered hole is no old hole",
         "Company Reports on Drill Results",
         "October 17, 2026 - Company Corp. reports today on assay results for 162 new boreholes. Hole AB36-262441: 55.50 m at "
         "8.92% Cg.", (55.5, 8.92, "Cg")),
    ]
    hole_cases = [("AB25-08", (2021, 11, 11), False), ("AB29-556043", (2019, 2, 14), False), ("DDH88-11", (2026, 1, 19), True)]

    ctx_cases = [
        ("a citation closing a clause about another hole", (2026, 5, 9),
         "1.30 g/t AuEq over 59m in hole PS-26-038, confirming continuity 100m down-dip of previously reported hole PS-26-027 "
         "(see March 23, 2026 press release) which intersected 2.72 g/t AuEq over 50m.", "1.30", None),
        ("the citation of a hole named below the figure", (2026, 9, 12),
         "OM26-241D intersected 3.6 g/t gold over 51.5 meters approximately 100 meters below hole OM18-220D, the most southerly "
         "intersection to-date (8.84 g/t gold over 3.0 meters (see press release dated December 4th, 2018);", "3.6", None),
        ("historic results in a quotation", (2026, 1, 21),
         "0.45 g/t gold over 33.5 metres including 1.11 g/t gold over 6.1 metres \"The initial assay results fall in range with "
         "expectations and historic results,\" commented the President.", "0.45", None),
        ("a figure related to historical drilling, and that drilling's citation", (2026, 9, 28),
         "AB-02 returned 660m of 0.97% CuEq, confirming the significant extension of mineralization relative to historical "
         "drilling first reported in AB-01 (see August 10, 2025 Press Release)", "660m", None),
        ("'(both previously released)' cites the figure before it", (2026, 11, 11),
         "These holes extend mineralization from drillhole BE25-04 (28.97 g/t Au over 21.76 m) (both previously released; see "
         "press release dated June 15, 2026).", "28.97", "historical"),
        ("'further to its news release' introduces new results", (2026, 1, 19),
         "The Company is pleased to announce that, further to its news release of November 2, 2025, it has received assays for "
         "two additional drill holes: hole 17 contained 43.66 metres of 1.76 g/t gold.", "43.66", None),
        ("'no previous drilling' is no background", (2026, 11, 23),
         "Assay results from the eastern part of the vein, which has had no previous drilling, include: 2.17 m @ 823 g/t Ag.",
         "2.17", None),
    ]
    for label, hl, body, want in news_cases:
        got = news2(hl, body)
        ok = got == want
        bad += not ok
        show(ok, "109f %s (got %r)" % (label, got))
    for label, hl, body, want in top_cases:
        a, top = topof(hl, body)
        got = None if top is None else (top["length_m"], top["grade"], top["metal"])
        ok = (got is None) if want is None else (got is not None and abs(got[0] - want[0]) < 0.05
                                                 and abs(got[1] - want[1]) < 0.005 and got[2] == want[2])
        bad += not ok
        show(ok, "109f %s (got %r)" % (label, got))
    for h, rd, want in hole_cases:
        ok = _old_hole(h, rd) == want
        bad += not ok
        show(ok, "109f hole %s old=%s" % (h, want))
    for label, rd, ctx, at, want in ctx_cases:
        got = context_reason(ctx, rd, (), ctx.index(at))
        ok = got == want
        bad += not ok
        show(ok, "109f %s (got %r)" % (label, got))

    # ---------------------------------------------------------------- 1.0.8: background figures, hole ids
    for rule, hl, body, want in [
        ("citation_as_reported", "Company Drills at Gamma", "November 1, 2024 - Company Corp. is pleased to announce drill "
         "results. This zone is similar to an interval grading 1.17% copper over 60.60 metres in AB24-03 as reported "
         "August 12, 2024. Hole AB24-08 returned 2.0 m of 0.9% Cu.", ("reject", 60.6, 1.17)),
        ("see_news_release_then_other", "Company Reports Results", "March 18, 2020 - Company Corp. announced today results of its "
         "first hole. Last year, DDH ABGW-19-04 intersected 6.65m of 1.07g/t gold (see press release May 16th, 2019). Other "
         "significant intercepts from this program included 2.95 g/t gold over 2.5 meters.", ("reject", 2.5, 2.95)),
        ("eq_abbreviation_no_split", "Company Reports Results", "March 3, 2023 - Company Corp. is pleased to report results. The "
         "target produced significant drill results, including 8.00 m @ 6.00 g/t Au Eq. (see news release dated January 31st, "
         "2023). Hole AB-23-01 returned 4.0 m of 1.66 g/t Au.", ("reject", 8.0, 6.0)),
        ("hole_last_century", "Company Reports Results at Kappa", "January 19, 2026 - Company Corp. is pleased to report results "
         "from three holes. Hole DDH88-11 returned 86.4 g/t Au over 2.0 m.", ("reject", 2.0, 86.4)),
        ("hole_year_suffix", "Company Reports New Drill Results", "April 29, 2019 - Company Corp. is pleased to report new drill "
         "results. Hole XY185-19 returned 40.9 m of 0.8 g/t Au. Hole XY187-19 returned 0.7 m of 12.7 g/t Au. Drilling from "
         "2006 through 2012 found gold at MG; hole XY104-10 cut 0.5 m @ 264.9 g/t gold.", ("reject", 0.5, 264.9)),
        ("other_company_hole", "Company Discovers Extension", "May 24, 2017 - Company Corp. is pleased to announce its first hole "
         "has intersected high grade gold. The deepest hole on the deposit, AB-0023, was drilled by Other Gold Corporation. "
         "This hole recorded an intersection of 30.6 metres @ 2.0 g/t Au. Hole AB-0009 returned 5.4 m @ 11.68 g/t Au.",
         ("reject", 30.6, 2.0)),
        ("pdf_split_decimal", "Company Extends Lambda", "January 13, 2026 - Company Corp. is pleased to report results. "
         "Drill hole AB25-013 intersected 1.2 5 g/t Au, 2.2 g/t Ag, 0.3 3% Cu over 128.7 metres.", (128.7, 0.33, "Cu")),
        ("costean_is_surface", "Company Reports First Results", "July 1, 2017 - Company Corp. is pleased to announce first Au "
         "results. Hole AB-17-01 returned 2.0 m of 1.5 g/t Au. Notable results include 17.66 gpt Au over 1.0 m from costean "
         "ABC17-177.", ("reject", 1.0, 17.66)),
    ]:
        a, its = accepted(hl, body)
        if want[0] == "reject":
            ok = not any(abs(i["length_m"] - want[1]) < 0.05 and abs(i["grade"] - want[2]) < 0.005 for i in its)
        else:
            ok = any(abs(i["length_m"] - want[0]) < 0.05 and abs(i["grade"] - want[1]) < 0.005 and i["metal"] == want[2] for i in its)
        bad += not ok
        show(ok, f"108[{rule}] {hl[:50]}")

    for label, hl, body, want in [
        ("the headline figure takes the hole its repeat names", "Company Intersects 1.04 g/t Gold over 19.8 m and 0.85 g/t "
         "Gold over 21.3 m at Mu", "Company Intersects 1.04 g/t Gold over 19.8 m and 0.85 g/t Gold over 21.3 m at Mu "
         "Toronto, October 6, 2025 - Company Corp. is pleased to report results: o AB25-094 intersected 0.85 g/t gold over 21.3 "
         "meters o AB25-100 intersected 1.04 g/t gold over 19.8 meters at the Mu Project.", "AB25-100"),
        ("an id heading a list owns its figures", "Company Reports Assay Results", "June 29, 2026 - Company Corp. is pleased to "
         "report assay results. Holes AB-09-25 and AB-10-25 were reported in June. New results: \u2022 AB-12-25: o 21.5m at "
         "1.32g/t Au from 68.5m o 45m at 1.24g/t Au from 113.5m at the Nu Project.", "AB-12-25"),
        ("a bracketed hole closes a list of figures", "Company Drills Step-Out Holes", "December 17, 2023 - Company Corp. is "
         "pleased to report results: o 56.6 m at 1.37% Li2O and 9.9 m at 3.58% Li2O (AB23-231) at the Xi Property.", "AB23-231"),
        ("a two-letter keyword id is a hole", "Company Reports Results from Omicron", "January 10, 2023 - Company Corp. is pleased to "
         "report results. Hole GR-28 intersected 97.85 metres grading 0.30% nickel at the Omicron prospect.", "GR-28"),
        ("an underscore id", "Company Intersects 1.41 g/t AuEq over 144.78 m", "September 18, 2018 - Company Corp. is pleased to "
         "report results: ABC18_046 : 1.41 g/t AuEq over 144.78 m at the Pi Project.", "ABC18_046"),
        ("a table names its one hole above the header", "Company Reports Results", "April 27, 2023 - Company Corp. is pleased to "
         "report results.\nDrillhole ABCD0015\nFrom (m) To (m) Width (m) Ni% Cu%\n33.02 43.39 10.37 0.45 0.18\n", "ABCD0015"),
    ]:
        a, top = topof(hl, body)
        ok = top is not None and top.get("hole") == want
        bad += not ok
        show(ok, "108h %s (got %r)" % (label, None if top is None else top.get("hole")))
    # ---------------------------------------------------------------- FIX5 (HOLE_OWNER_V1)
    for label, hl, body, want in [
        ("a landmark hole gives way to the hole the figure is written with", "Company Intersects 326.6 m of 1.92% Li2O",
         "October 11, 2022 - Company Corp. is pleased to report results from the Rho Project.\nDrill hole AB-067-22, "
         "collared 40m east of AB-066-22, intersected 326.6 m averaging 1.92% Li2O.", "AB-067-22"),
        ("the id opening the list item owns its figures", "Company Reports 7.49 g/t Gold over 9.0 Metres",
         "November 29, 2021 - Company Corp. is pleased to report results from the Sigma Project.\n"
         "\u2022 AB21-003 returned 6.08 g/t gold over 10.9 m.\n"
         "\u2022 AB21-004 was drilled from the same setup as AB21-003 at a steeper dip. The hole returned 4.44 g/t gold over "
         "19.0 m with a high-grade interval of 7.49 g/t gold over 9.0 m.", "AB21-004"),
        ("a hole written by its number alone heads the list", "Company Intersects 44.3 Metres of 1.14% CuEq",
         "December 2, 2019 - Company Corp. announces drill core assay results from the Tau target.\n"
         "\u25aa Highlight assays from discovery hole 13 include:\no 44.3m of 1.14% CuEq, including 30 m of 1.46% CuEq\n"
         "\u25aa Drill holes 19-22 in the zone are complete and being processed for assay\n"
         "Hole AB-19-13 was drilled to 400 m.", "AB-19-13"),
        ("two quotations naming different holes change nothing", "Company Drilling Hits 8.8 m of 4.8% CuEq",
         "April 5, 2023 - Company Corp. is pleased to announce results from the Tau Project. Hole AB-22-95 intersected "
         "2.7 m grading 0.5% CuEq at a new target. Drilling intersected 8.8 m of 4.8% CuEq in hole AB-23-97.\n"
         "Hole AB-22-97\n8.8 m @ 4.8% CuEq", None),
    ]:
        a, top = topof(hl, body)
        if want is None:
            ok = top is not None and top.get("hole_how") != "owner"
        else:
            ok = top is not None and top.get("hole") == want
        bad += not ok
        show(ok, "FIX5 %s (got %r)" % (label, None if top is None else top.get("hole")))
    got = [_clean_name(n) for n in ("Historical", "VMS", "Gold-Rich Major", "Lac T\u00eate")]
    ok = got == [None, None, None, "Lac T\u00eate"]
    bad += not ok
    show(ok, "108 descriptors are not names, accented names are kept (got %r)" % (got,))
    if verbose:
        print("failures:", bad)
    return bad


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(1 if self_test(verbose=False) else 0)