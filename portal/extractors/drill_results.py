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

Self-tests: python3 -m portal.extractors.drill_results
"""
from __future__ import annotations

import re

from portal import drill_extract as D
from portal import facts as F

NAME = "drill_results"
VERSION = "1.0.0"
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
    t = text or ""
    t = re.sub(r"(?<=[A-Za-z0-9])-[ \t]*\n[ \t]*(?=[A-Za-z0-9])", "-", t)      # "PLN25-\n205"
    t = re.sub(r"(?<=[A-Za-z]\d)- (?=\d)", "-", t)                              # "HS1- 06"
    t = re.sub(r"(?<=[A-Za-z]\d\d)- (?=\d)", "-", t)                            # "HS11- 06"
    t = re.sub(r"(?<![A-Za-z])([A-Z]{2,6}) -(?=\d{1,4}-\d)", r"\1-", t)       # "JES -21-43"
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
        if text[m.start():m.start() + 1] == "." and re.search(r"(?i)(?:\be\.g|\bi\.e|\bincl|\bapprox|\bvs|\best|\bNo)$", text[max(0, m.start() - 7):m.start()]):
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
    r"(?i)\b(?:grab|chips?|chip[\-\s]channel|channels?|channel\s+samples?|trench\w*|rock\s+samples?|outcrops?"
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
    r"|previous(?:ly)?[\s\-]+(?:report|announc|releas|disclos|drill|trench|sampl|publish|intersect|identif|defin|known|tested)\w*"
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
    r"|(?:original|initial|earlier)\s+(?:[\w\-]+\s+){0,3}(?:intercept|intersection)s?"
    r"|(?:acquired|compiled|legacy|archival)\s+(?:\w+\s+){0,2}(?:data|database|drill\w*)"
    r"|(?:previous|former|prior)\s+(?:operators?|owners?|explorers?|companies)"
    r"|(?:press|news)\s+releases?\s+(?:dated|of|on)\b|(?:asx\s+)?announcements?\s+(?:dated|of|on)\s+\d"
    r"|see\s+(?:the\s+)?(?:company'?s\s+|[A-Z][\w&]*'?s?\s+){0,2}(?:asx\s+)?(?:news|press)\s+rel"
    r"|based\s+on\s+(?:(?:19|20)\d\d\s+)?(?:historical\s+)?data|intercepts?\s+(?:of\s+)?up\s+to"
    r"|see\s+(?:the\s+)?(?:asx\s+)?announcement|\(\s*(?:see\s+)?(?:NR|PR)\s+(?:dated\s+)?(?:" + MONTHS + r")"
    r"|ref(?:\.|er\s+to|erence)?\s+(?:the\s+)?(?:company'?s\s+)?(?:press|news)\s+releases?"
    r"|assessment\s+(?:report|file)|prior\s+(?:drilling|programs?|holes?|campaigns?)"
    r"|non[\-\s]compliant|past[\-\s]producing\s+(?:\w+\s+)?(?:results|data)|reported\s+by\s+[A-Z]"
    r"|post[\-\s]quarter|during\s+the\s+(?:previous|last|prior)\s+quarter|quarterly\s+(?:activities\s+)?report"
    r"|activities\s+report"
    r"|(?:discovery|earlier|prior|phase\s+(?:i|1|one))\s+(?:rc\s+|diamond\s+|core\s+)?(?:drill\s*)?holes?\s+[A-Z0-9]"
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
    r"|\b(?P<y3>(?:19|20)\d\d)\s+(?:[\w\-]+\s+){0,3}?(?:drill\w*|trench\w*|sampl\w*|programs?|programmes?|campaigns?)\b"
    r"|\b(?:drill\w*|trench\w*|programs?|programmes?|campaigns?)\b[^.;\n]{0,60}?\b(?:in|during)\s+(?P<y4>(?:19|20)\d\d)\b")
_RE_RECAP_HEADLINE = re.compile(
    r"(?i)\b(?:achievements|year[\s\-]in[\s\-]review|year[\s\-]end\s+(?:review|update|summary|letter)"
    r"|highlights\s+of\s+(?:19|20)\d\d|(?:19|20)\d\d\s+(?:achievements|highlights|review|in\s+review|year\s+in\s+review)"
    r"|annual\s+review|letter\s+to\s+shareholders|quarterly\s+(?:activities\s+)?report|activities\s+report)\b")
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
_RE_REFERENCE = re.compile(r"(?i)^(?:see|\(|(?:press|news)\s+release|(?:asx\s+)?announcement|ref)")


def context_reason(ctx: str, release_date, program_years=(), pos=None, exempt_years=()) -> str | None:
    """Why the figures in this sentence are not new drill assays, or None. pos: where the figure sits in ctx."""
    if _RE_XRF.search(ctx):
        return "xrf"
    if _RE_VISUAL.search(ctx) and not _RE_ASSAY.search(ctx):
        return "visual"
    for m in _RE_HIST.finditer(ctx):
        before = ctx[max(0, m.start() - 90):m.start()]
        if _RE_SINCE.search(before):
            continue  # "completed since the last news release dated ..." introduces NEW results
        if (re.match(r"(?i)historic|prior\s+drill|previous\s+drill", m.group(0)) and _RE_RELATES.search(before)
                and (pos is None or pos < m.start() or not re.match(
                    r"(?i)^[^.;]{0,50}?(?:\bwhich\b|\bthat\b|\breturn\w*|\bgrad\w*|\bassay\w*|\(|:)", ctx[m.end():pos]))):
            continue  # new holes "confirming / beneath / filling gaps in the historic drilling"
        if (pos is not None and pos > m.end() and _RE_REFERENCE.match(m.group(0))
                and ctx.rfind("(", 0, m.start()) > ctx.rfind(")", 0, m.start())):
            continue  # "(see news release dated ...)" refers to what came before it, not to a later figure
        if pos is not None and pos < m.start() - 20 and m.group(0)[:8].lower() == "previous":
            continue  # "27 m @ 37 g/t (APC-162) ... up-dip of previously released hole X": the old hole comes after
        return "historical"
    if release_date:
        for m in _RE_YEAR_WORK.finditer(ctx):
            y = int(m.group("y") or m.group("y2") or m.group("y3") or m.group("y4"))
            if y in exempt_years:
                continue
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
_ID_CORE = r"(?:[A-Za-z]{1,8}\d{0,5}|\d{1,4}[A-Za-z]{1,6}\d{0,4}|\d{1,4})(?:[\-_](?:[A-Za-z]{0,10}\d{0,6}[A-Za-z]{0,3}))+"
_RE_HOLE_KW = re.compile(
    r"(?i:\b(?:drill[\s\-]?holes?|holes?|DDH|boreholes?|drill\s+core\s+holes?)\b)(?:\s*(?:#|No\.?|ID))?\s*[:#]?\s*"
    r"(?P<id>DDH-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*|" + _ID_CORE + r"|[A-Z]{1,6}\d{1,5}[A-Z]?)(?![A-Za-z0-9\-])")
_RE_HOLE_SHAPE = re.compile(
    r"(?<![A-Za-z0-9\-/.])(?P<id>(?:[A-Z]{1,8}\d{0,5}|\d{1,4}[A-Z]{1,6}\d{0,4})(?:-[A-Z]{0,10}\d{1,6}[A-Z]{0,3}){1,3}"
    r"|[A-Z]{1,6}\d{2,5}-\d{1,4}[A-Z]?)(?![A-Za-z0-9\-/])")
_NOT_HOLE = re.compile(
    r"(?i)^(?:NI-?43-101|43-101|COVID-19|[A-Z]{1,3}\d?O\d?(?:-\d+)?|Q[1-4]-\d+|H[12]-\d+|TSX-?V?|CSE|FSE|OTC\w*"
    r"|Form-\d+|\d{4}-\d{2,4}|[A-Z]{2}-\d{1,2}|Phase-\d+|Figure-\d+|Table-\d+|No-\d+|SEDAR-\d+|Rule-\d+)$")


def _hole_ok(h: str, keyword: bool) -> bool:
    if not h or not re.search(r"\d", h) or len(h) > 24:
        return False
    if _NOT_HOLE.match(h):
        return False
    if not keyword:
        # a shape-only id needs a letter and a hyphen-separated number: "PLN25-200", "EB-21-78"
        if not re.search(r"[A-Za-z]", h) or "-" not in h:
            return False
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
_ROW_INCL = re.compile(r"(?i)^\s*(?:incl(?:uding|\.)?|inc\.?|and|with|within)\b")


def _tnum(s):
    return float(s.replace(",", "."))


def find_tables(t: str, release_date, spans=None) -> list[dict]:
    """Intervals from 'Hole | From | To | Length | grades' tables in plain text."""
    out = []
    for hm in _TABLE_HEADER.finditer(t):
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
            if len(nums) >= 3 and (find_holes(line) or _ROW_INCL.match(line) or re.match(r"^\s*[\d.]", line)):
                first_row = cur
                break
            header_text += line
            cur += len(line)
            if len(header_text) > 900:
                break
        if first_row is None:
            continue
        cols = [(D._normalize_metal(re.sub(r"\s+", "", c.group("metal"))),
                 "g/t" if c.group("unit").lower() in ("gpt", "g/tonne") else c.group("unit").lower())
                for c in _TABLE_METAL.finditer(header_text[hm.start() - hstart:])]
        if not cols:
            continue
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
        pre_reason = context_reason(pre, release_date)
        if pre_reason is None and _RE_SURFACE.search(header_text + pre[-200:]) and not _RE_DRILL_WORD.search(header_text + pre[-200:]):
            pre_reason = "surface"
        hole = None
        pos = first_row
        rows = 0
        row_reason = None
        group, group_years, first_out = 0, {}, len(out)
        for line in t[first_row:first_row + 8000].split("\n"):
            lpos = pos
            pos += len(line) + 1
            if not line.strip():
                continue
            if rows and not _NUM.search(line) and len(line.strip()) <= 120:
                sub = context_reason(line, release_date)  # "Previously released on October 31, 2024" inside a table
                row_reason = sub if sub in ("historical", "previously_reported", "surface") else None
            holes = [h for h in find_holes(line) if h["pos"] < 12 or line[:h["pos"]].strip() == ""]
            if holes or (_RE_TABLE_HOLE_START.match(line) and not _ROW_INCL.match(line)):
                group += 1
            for ym in _RE_TABLE_DRILLED_YEAR.finditer(line):  # "Drilled 2022 (Rugby Resources)" in a comments column
                group_years.setdefault(group, []).append(int(ym.group(1)))
            nums_m = [n for n in _NUM.finditer(line)]
            if holes:
                hole = holes[0]["id"]
                nums_m = [n for n in nums_m if n.start() >= holes[0]["end"]]
            nums = [n.group(0) for n in nums_m]
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
                            "from_m": fr, "to_m": to, "hole": hole, "including": incl, "src": "table", "_group": group,
                            "reason": pre_reason or row_reason, "reason_src": "title" if pre_reason else None,
                            "rule": "table_title" if pre_reason else ("table_row" if row_reason else None)})
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
_PTOK = r"(?:[A-Z][A-Za-z0-9'’\-]*(?:/[A-Z][A-Za-z0-9'’\-]*)?)"
_COMMODITY = (r"gold|silver|copper|nickel|zinc|lead|lithium|uranium|antimony|polymetallic|palladium|platinum|pgm"
              r"|graphite|potash|tungsten|cobalt|vanadium|tin|molybdenum|rare[\s\-]earths?|base[\s\-]metals?"
              r"|critical[\s\-]minerals?|copper[\s\-]gold|gold[\s\-]silver|silver[\s\-]gold|gold[\s\-]copper")
_RE_PROJECT = re.compile(
    r"(?P<name>(?:" + _PTOK + r"[ \t]+|" + _PTOK + r"[ \t]*\n[ \t]*){0,3}" + _PTOK + r")"
    r"(?:[ \t]+(?i:" + _COMMODITY + r"))?[ \t\n]+"
    r"(?P<suffix>(?i:project|property|deposit|mine[ \t]+complex|mining[ \t]+complex|mine|complex|claims"
    r"|camp|district|zone|trend|target|prospect|showing|vein|discovery))\b")
_SUFFIX_RANK = {"project": 1, "property": 1, "deposit": 1, "mine complex": 1, "mining complex": 1, "mine": 1,
                "complex": 1, "claims": 1, "camp": 2, "district": 2, "zone": 3, "trend": 3, "target": 3,
                "prospect": 3, "showing": 3, "vein": 3, "discovery": 3}
_NAME_BREAK = D._PROJECT_STOP_NEW | {
    "provides", "announces", "reports", "releases", "commences", "completes", "receives", "expands", "extends",
    "confirms", "discovers", "returns", "hits", "encounters", "identifies", "samples", "updates", "continues",
    "begins", "starts", "launches", "intersects", "drills", "defines", "delivers", "outlines", "highlights",
    "in", "near", "and", "with", "for", "to", "by", "a", "an", "our", "company's", "company’s", "flagship",
    "wholly-owned", "100%-owned", "owned", "optioned", "adjacent", "along", "within", "across", "from", "on",
    "under", "below", "beneath", "its", "the", "this", "that", "these",
    "canada", "nevada", "quebec", "ontario", "yukon", "mexico", "peru", "chile", "b.c.", "bc", "usa",
}
_NAME_BARE = D._PROJECT_BARE_WORDS | {"mine", "project", "property", "deposit", "zone", "camp", "district"}


def _clean_name(raw: str):
    name = re.sub(r"\s+", " ", raw).strip(" ,;.")
    name = re.split(r"\S+['’]s\s+", name)[-1]
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
    name = " ".join(toks)
    low = [t.lower() for t in toks]
    if len(low) == 1 and low[0] in _NAME_BARE:
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


def _old_hole(hole, release_date):
    """Hole id names a year well before the release ("TM22-119" in a 2025 release)."""
    m = _RE_HOLE_YEAR.match(hole or "")
    if not m or not release_date:
        return False
    yy = release_date[0] % 100
    groups = [int(g) for g in re.findall(r"(?<![\d])(\d{2})(?![\d])", hole[m.end(1):])]
    if any(g in (yy, yy - 1) for g in groups):
        return False  # "J-10-21": hole 10 of 2021
    y = 2000 + int(m.group(1))
    return y < release_date[0] - 1 or (y < release_date[0] and (release_date[1] or 0) > 6)


_RE_WIDTH_NOTE = re.compile(r"(?i)\(\s*[\d.,]+\s*(?:m|metres?|meters?)\s*(?:etw|e\.t\.w\.?|tw|true\s+widths?|est\w*\.?\s+true\s+widths?)\s*\)")


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


def _attach_holes(t, spans, holes, intervals):
    """Hole for each text interval: 'in/from hole X' right after it, else the nearest id before it in
    the same unit, else a keyword id earlier in the same paragraph. Ids in historical units never count."""
    starts = sorted(i["pos"] for i in intervals)
    for iv in intervals:
        if iv.get("hole"):
            continue
        u = unit_at(spans, iv["pos"])
        us, ue = spans[u] if u >= 0 else (0, len(t))
        nxt = min((p for p in starts if p > iv["pos"]), default=len(t))
        after = [h for h in holes if iv["pos"] < h["pos"] < min(nxt, iv["pos"] + 220, ue)
                 and re.search(r"(?i)\b(?:in|from|of|for)\s+(?:the\s+)?(?:drill[\s\-]?)?(?:hole|DDH|borehole)s?\s*"
                               r"(?:#|No\.?)?\s*[:#]?\s*$", t[max(iv["pos"], h["pos"] - 40):h["pos"]])]
        if after:
            iv["hole"] = after[0]["id"]
            continue
        nxt_other = min((x["pos"] for x in intervals if x["pos"] > iv["pos"] and abs(x["length_m"] - iv["length_m"]) > 0.01), default=len(t))
        paren = [h for h in holes if iv["pos"] < h["pos"] < min(nxt_other, iv["pos"] + 120, ue)
                 and re.search(r"\(\s*$", t[max(iv["pos"], h["pos"] - 3):h["pos"]])
                 and not re.search(r"[.;]\s", t[iv["pos"]:h["pos"]])]
        if paren:
            iv["hole"] = paren[0]["id"]  # "327.0 g/t Au over 1.0 metre (TM25-176)"
            continue
        before = [h for h in holes if us <= h["pos"] < iv["pos"]]
        if before:
            iv["hole"] = before[-1]["id"]
            continue
        para_start = t.rfind("\n\n", 0, iv["pos"])
        back = [h for h in holes if h["kw"] and max(para_start, iv["pos"] - 700) <= h["pos"] < iv["pos"]]
        if back and not context_reason(t[back[-1]["pos"]:back[-1]["pos"] + 200], None):
            iv["hole"] = back[-1]["id"]


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


def _headline_family(th):
    best = None
    for fam, pat in _HEADLINE_METALS:
        m = re.search(r"(?i)\b(?:" + pat + r")\b", th)
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
    r"(?i)\b(?:of|between|near|beside|adjacent\s+to|away\s+from|(?:up|down)[\s\-]?dip\s+(?:of|from)|along\s+strike\s+(?:of|from)"
    r"|(?:north|south|east|west)\w*\s+of|twin(?:ning|s)?\s+of|offset\w*\s+(?:of|to)|previously\s+\w+|historic\w*"
    r"|(?:stepping|step[\s\-]?outs?|laterally|extending)\s+(?:\w+\s+)?from|\)\s*,\s*(?:and\s+)?)\s*"
    r"(?:the\s+)?(?:\w+\s+){0,2}?(?:(?:drill\s*)?holes?\s+)?(?-i:[A-Z][A-Z0-9]*(?:\s*-\s*[A-Z0-9]+)+)\s*\([^()]{0,30}$"
    r"|\bbetween\b[^.]{0,160}\band\s+(?:(?:drill\s*)?holes?\s+)?(?-i:[A-Z][A-Z0-9]*(?:\s*-\s*[A-Z0-9]+)+)\s*\([^()]{0,30}$"
    r"|\bpreviously\s+\w+\b[^.()]{0,90}\(\s*(?-i:[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\s*:[^()]{0,30}$")


_RE_SURFACE_NEAR = re.compile(r"(?i)\b(?:trench\w*|channels?|chip|grab|outcrop|soil|boulder|float)\b(?![\s\-]+(?:Vein|Zone|Creek|Lake|Hill))")
_RE_DRILL_NEAR = re.compile(r"(?i)\b(?:drill\w*|holes?|DDH|core|borehole)\b")
_RE_BACKREF = re.compile(r"(?i)^\W*(?:this|that|the\s+(?:same|above|previous))\s+(?:\w+\s+){0,2}(?:intersection|intercept|hole|interval|result)")
_RE_OLD_HOLE_REF = re.compile(
    r"(?i)\b(?:along\s+strike\s+(?:from|of)|away\s+from|near|(?:up|down)[\s\-]?dip\s+(?:of|from))\b[^.]{0,80}?"
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
# "(see NR March 31, 2026)" after a figure: it was released before
_RE_REF_AFTER = re.compile(r"(?i)\(\s*(?:see\s+|refer\s+to\s+)?(?:the\s+)?(?:company'?s\s+)?(?:NR|news\s+release|press\s+release)s?\b[^()]{0,40}?(?:19|20)\d\d\s*\)"
                           r"|\(\s*(?:see\s+)?(?:[A-Z][a-z]+\.?\s+\d{1,2},?\s+)?(?:19|20)\d\d\s+(?:NR|news\s+release|press\s+release)\s*\)")
_RE_EQ_PAREN = re.compile(r"(?i)(\d[\d.,]*\s*(?:g/t|%|ppm)\s*[A-Za-z0-9]{1,6}Eq\s*)\([^()]{3,80}\)(?=\s*(?:over|across|for)\b)")
_RE_REASSAY = re.compile(r"(?i)\bre\s?-?\s?assay\w*")
_RE_INVESTEE = re.compile(r"(?i)\binvestee\b|\bportfolio\s+compan|\b(?:applau\w+|congratulat\w+)\s+[A-Z]"
                          r"|\b(?:strategic\s+|equity\s+)?investment\s+in\s+(?-i:[A-Z])[\w&.\- ]{2,40}\(\s*(?:TSX|CSE|ASX|NYSE|OTC)")
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
    return bool(_RE_FIGURE_END.search(tail[max(0, m.start() - 40):m.start()]))


_RE_PLAN_CTX = re.compile(r"(?i)\b(?:is|are|will\s+be)\s+planned\b[^.]{0,160}\b(?:intersected|returned|encountered)\s+(?:in\s+)?[^.]{0,60}$"
                          r"|\bwill\s+(?:test|follow\s+up)\b[^.]{0,160}\b(?:intersected|returned|encountered)\s+(?:in\s+)?[^.]{0,60}$")
_RE_TRENCH_AFTER = re.compile(r"(?i)^(?:[^.;()]|\.(?=\d)){0,60}?\b(?:in|from)\s+(?:the\s+)?(?:trench\w*|channel\s+sampl\w*|channels?|grab\s+sampl\w*|outcrop)\b")
_RE_HIST_DRILL_HEADLINE = re.compile(r"(?i)\b(?:in|from)\s+(?:the\s+)?historic(?:al)?\s+(?:drill\w*|holes?|data|core|results|assays|intercepts)\b")
_RE_DRILL_VERB_HEADLINE = re.compile(r"(?i)\b(?:intersect(?:s|ing)?|intercept(?:s|ing)?|drills|drilling|hits|cuts|returns|returning|encounters?)\b")
_RE_SAMPLES_VERB = re.compile(r"^\W*(?:[A-Z][\w.&'\-]*\s+){1,4}?(?:Samples|Trenches|Channels|Channel\s+Samples)\s+(?:(?-i:[A-Z])\S*\s+){0,3}?(?:High[\s\-]Grade|Gold|Silver|Copper|Lithium|Uranium|up\s+to|\d)")
_RE_FOLLOW_UP_HEADLINE = re.compile(r"(?i)\b(?:to\s+)?follow[\s\-]?up\s+(?:on|to)\b[^|]{0,80}?\b(?:recent|previous(?:ly)?|prior|earlier|last\s+year'?s?)\b")
_RE_HOLE_YEAR = re.compile(r"^[A-Z]{1,6}-?(\d{2})[-_]\d")


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
    out = []
    for lit in lits:
        for m in re.finditer(r"(?<![\d.])" + re.escape(lit) + r"(?![\d])", t):
            out.append(m.start())
    return sorted(set(out))


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
    hl_ints = _one_length_per_grade(D.find_intercepts(hl), D._prep(hl))
    if not hl_ints and D._RE_PLAN_ONLY.search(hl) and not D._RE_RESULTS_STRONG.search(hl):
        result["reason"] = "plan"
        return result
    if not hl_ints and _RE_CAMPAIGN_HEADLINE.search(hl) and not _RE_RESULTS_WORDS.search(hl):
        result["reason"] = "plan"
        return result
    if not hl_ints and _headline_pending(hl):
        result["reason"] = "pending"
        return result

    if not hl_ints and _RE_NOT_RESULTS_HEADLINE.search(hl) and not _RE_RESULTS_WORDS.search(hl):
        result["reason"] = "not_results"
        return result
    if not hl_ints and _RE_EVENT_HEADLINE.search(hl):
        result["reason"] = "not_results"  # a webinar invitation or an investment update recaps results released elsewhere
        return result
    hl_drill = (bool(hl_ints) or bool(_RE_DRILL_WORD.search(th)) or bool(_RE_RESULTS_WORDS.search(th))
                or len(re.findall(r"[A-Za-z]+", hl)) < 5 or bool(re.search(r"(?i)news\s+release", hl)))
    lede_drill = bool(_RE_DRILL_WORD.search(t))

    release_reason = None
    th_np = _RE_PLAN_PHRASE.sub(" ", th)
    if _RE_XRF.search(th):
        release_reason = "xrf"
    elif not _RE_DRILL_WORD.search(th_np) and context_reason(re.sub(r"^\W*\w+", "", th_np, count=1), None) in ("surface", "historical"):
        release_reason = context_reason(re.sub(r"^\W*\w+", "", th_np, count=1), None)  # "Highlights Historical Soil Anomalies"
    elif not _RE_DRILL_WORD.search(th_np) and _RE_SAMPLES_VERB.search(th):
        release_reason = "surface"  # "Tocvan Samples High-Grade Gold and Silver 6-kilometers from Pilar"
    elif _RE_HIST_DRILL_HEADLINE.search(th) and not re.search(r"(?i)\btwin", th):
        release_reason = "historical"  # "... Results Including 3.51 g/t AuEq over 93 metres in Historic Drilling"
    elif not _RE_DRILL_WORD.search(th) and any(not re.search(r"(?i)drill", m.group(0)) for m in _RE_SURFACE_INTRO.finditer(t[:1800])):
        release_reason = "surface"
    elif _RE_PRIOR_OPERATOR_RELEASE.search(t[:2500]):
        release_reason = "historical_operator"
    elif _RE_FOLLOW_UP_HEADLINE.search(th) and _RE_PLAN_PHRASE.search(th) and not _RE_DRILL_VERB_HEADLINE.search(th):
        release_reason = "previously_reported"  # "Announces Drill Program to Follow up on Saddle Zone's Recent 5.94% CuEq over 11 m"
    elif _RE_INVESTEE.search(th) or _RE_INVESTEE.search(t[:1500]):
        release_reason = "investee"  # results of a company this one holds shares in
    elif _RE_RECAP_HEADLINE.search(th) or _RE_RECAP_BODY.search(t[:3000]):
        release_reason = "recap"
    program_years = {int(m.group(1)) for m in _RE_PROGRAM_YEAR.finditer(t)}
    hl_years = {int(y) for y in re.findall(r"\b((?:19|20)\d\d)\b", th)} if hl_drill else set()

    def reason_for(ctx, head="", pos=None):
        r = context_reason(ctx, rdate, program_years, pos, hl_years)
        if r is None and head:
            r = context_reason(head, rdate, program_years, None, hl_years)
        return r

    spans = units(t)
    copy = _headline_copy(t, hl)
    if copy:
        spans = _split_spans(spans, copy)
    holes = find_holes(t)
    text_ints = _one_length_per_grade(D.find_intercepts(ld), t)
    blanked = _RE_EQ_PAREN.sub(lambda m: m.group(1) + " " * (len(m.group(0)) - len(m.group(1))), t)
    blanked = _RE_WIDTH_NOTE.sub(lambda m: " " * len(m.group(0)), blanked)
    if blanked != t:
        noted = [m.span() for m in _RE_WIDTH_NOTE.finditer(t)]
        if noted:  # the length inside "(5.78m etw)" is a width, not the interval
            text_ints = [x for x in text_ints if not any(a <= x["pos"] + 200 and _width_from_note(t, x, a, b) for a, b in noted)]
        for iv in D.find_intercepts(blanked):  # "3.51 g/t AuEq (1.08 g/t Au & 0.69% Sb) over 93 metres"
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
            if lh and context_reason(lh, rdate, program_years) in ("surface", "historical", "xrf"):
                iv["reason"] = context_reason(lh, rdate, program_years)
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
        if iv["reason"] is None and _RE_UP_TO.search(t[max(0, iv["pos"] - 40):iv["pos"]]) and not any(_same(h, iv) for h in hl_ints):
            iv["reason"] = "not_interval"
            _rule(iv, "up_to")
        if iv["reason"] is None:
            seg = t[iv["pos"]:iv["pos"] + 300]
            end = re.search(r"\.(?:\s|$)", seg)
            if _RE_REF_AFTER.search(seg[:end.start() if end else 300]):
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
    for iv in text_ints:
        if iv["reason"] is None and _old_hole(iv.get("hole"), rdate):
            iv["reason"] = "historical"  # hole TM22-119 quoted in a 2025 release
            _rule(iv, "hole_year")
    # an id that only appears inside a historical sentence is somebody else's hole
    for iv in text_ints:
        if iv.get("hole") and iv["reason"] is None:
            hs = [h for h in holes if h["id"] == iv["hole"]]
            if hs and all(reason_for(*_unit_ctx(t, spans, h["pos"])[:2]) == "historical" for h in hs):
                iv["hole"] = None

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

    table_ints = find_tables(t, rdate, spans)
    for iv in table_ints:
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
                dup["hole"] = iv["hole"]
            continue
        merged.append(iv)

    # headline figures must agree with the body; a headline figure the body rejects is rejected,
    # and a headline that calls its own figures XRF or visual condemns the body copies too
    hl_reason = context_reason(th, rdate, program_years)
    body_ok = [x for x in merged if not x["reason"]]
    body_any = bool(merged)
    for iv in hl_ints:
        iv["src"] = "headline"
        htail = th[max(0, iv["pos"] - 90):iv["pos"]]
        iv["including"] = _is_sub(htail)
        match_ok = next((x for x in body_ok if _same(x, iv)), None) or next((x for x in body_ok if _rounded_same(iv, x)), None)
        match_bad = next((x for x in merged if x["reason"] and (_same(x, iv) or _rounded_same(iv, x))), None)
        named_hole = bool(match_bad and match_bad.get("hole") and re.search(r"(?i)\b(?:extends?|deepen\w*|re-?enter\w*)\b", th)
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
    pool = [x for x in ok if not x.get("including") or x["src_code"] == 0] or ok
    rank_list = [dict(x, src=x["src_code"], pos=(x.get("hl_pos", x["pos"]) if x["src_code"] == 0 else 100000 + x["pos"]))
                 for x in pool]
    if rank_list:
        D._stamp_tiers(rank_list)
        fam = _headline_family(th)
        if fam and not any(x["src"] == 0 for x in rank_list) and any(D._family(x["metal"]) == fam for x in rank_list):
            for x in rank_list:
                x["tier"] = 2 if D._family(x["metal"]) == fam else 0
        best_i = max(range(len(rank_list)), key=lambda i: D.score_intercept(rank_list[i]))
        top = pool[best_i]
        # one interval quoted in several metals ("529 m grading 0.41% Cu and 0.21 g/t Au"): show its equivalent grade if
        # given, else the metal the release lists first
        sibs = [x for x in pool if x["src"] == top["src"] and abs(x["length_m"] - top["length_m"]) < 0.011 and (x is top or x["metal"] != top["metal"])
                and (x.get("hole") or None) == (top.get("hole") or None) and abs(x["pos"] - top["pos"]) < 120
                and (x["src"] != "text" or not re.search(r"[.;]\s", t[min(x["pos"], top["pos"]):max(x["pos"], top["pos"])]))
                and bool(x.get("headline")) == bool(top.get("headline")) and bool(x.get("including")) == bool(top.get("including"))]
        hl_fams = {f for f, pat in _HEADLINE_METALS if re.search(r"(?i)\b(?:" + pat + r")\b", th)}
        one_fam = next(iter(hl_fams)) if len(hl_fams) == 1 else None
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
        if not top.get("hole"):
            twin = next((x for x in merged if x is not top and x.get("hole") and not x["reason"] and _same(x, top)), None)
            if twin:
                top["hole"] = twin["hole"]
    result["intervals"] = merged
    name, rank = find_project(th, t)
    result["project"], result["project_rank"] = name, rank
    return result


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
    import hashlib
    import os
    h = hashlib.sha1()
    for p in (__file__, D.__file__):
        with open(p, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest() + "-" + os.path.basename(D.__file__)


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
    if verbose:
        print("failures:", bad)
    return bad


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(1 if self_test(verbose=False) else 0)