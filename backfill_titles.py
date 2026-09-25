#!/usr/bin/env python3
"""The exchange states the ticker. It does not state a headline.

Two jobs live here.

**1. Cleaning a feed title.** The CSE feed's `title` is whatever the issuer
typed into a form. Across all 3,856 of our 2026 titles, **464 (12.0%)** carry
boilerplate and **326 (8.5%)** say nothing once it is stripped. The first capped
backfill run published *"ESGold Corp. - Press Release (September 10, 2026)"* to
three public sites.

**2. Taking a headline out of a document.** TMX has no titles at all — `name` is
the literal string "News release" on 9,095 of 9,198 rows — so every TSX/TSXV
headline is read from the PDF. That makes `headline_from_body` the single most
load-bearing function in the TMX backfill.

**Erring towards the document is deliberate.** A wrong "this title is hollow"
costs a PDF parse that is happening anyway; a wrong "this title is fine" puts a
placeholder on three public sites.

These rules live apart from the runner so they can be corrected without touching
a 25 KB file, and because they are the part most likely to need correcting: they
are pattern-matching against free text a human typed.

    python3 backfill_titles.py          # run the self-test
"""
from __future__ import annotations

import re
import sys

_MONTHS = (r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
           r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|"
           r"Dec(?:ember)?")

_DATEISH = (r"(?:\(?\s*(?:dated\s+)?[A-Za-z]{3,9}\.?\s+\d{1,2}\s*,?\s*20\d{2}\s*\)?)")

_TITLE_PREFIX = re.compile(
    r"^\s*"
    r"(?:" + _DATEISH + r"\s*[-–—|:,]?\s*)?"
    r"(?:[\w'&.,()\- ]{2,40}?\s*[-–—|]\s*|[A-Za-z]{2,6}\s+)?"
    r"(?:news|new|press|media)\s*releases?"
    r"(?:\s*[-–—|:,]?\s*" + _DATEISH + r")?"
    r"\s*(?:re\b:?|[-–—|:,])?\s*", re.I)

_TITLE_HOLLOW = re.compile(
    r"^\s*(?:[\w'&.,()\- ]{0,40}?\s*[-–—|]\s*)?"
    r"(?:(?:news|new|press|media)\s*releases?|nr|pr)?\s*"
    r"(?:[-–—|(,]?\s*(?:dated\s+)?[A-Za-z]*\.?\s*\d{0,2},?\s*20\d{2}\s*\)?)?\s*$",
    re.I)

MIN_TITLE_CHARS = 28


def clean_title(raw: str) -> str:
    """Strip the boilerplate an issuer put in front of its own headline.

    Stripping to an empty string is a valid outcome, not a failed strip — that
    is exactly what `News Release` should become.
    """
    t = (raw or "").strip()
    for _ in range(3):
        stripped = _TITLE_PREFIX.sub("", t, count=1).strip(" -–—|:,")
        if stripped == t:
            break
        t = stripped
        if not t:
            break
    return t.strip()


def title_is_hollow(t: str) -> bool:
    """True when the title should not be trusted as a headline."""
    if not t:
        return True
    if _TITLE_HOLLOW.match(t):
        return True
    return len(t) < MIN_TITLE_CHARS


# --------------------------------------------------------------------------
# reading a headline out of the document
# --------------------------------------------------------------------------
#
# A release PDF is laid out the same way everywhere: letterhead, then the
# headline — usually wrapped over two or three lines — then the dateline, then
# the body. The mistake in the original extractor was using ONE "is this
# letterhead" test for two different questions: where does the headline start,
# and where does it end. A line under 12 characters is almost certainly
# letterhead *before* the headline and is almost certainly a continuation
# *inside* it.
#
# Allowing short continuations is what recovers "Financing" and "at Tynagh". It
# is also what swept in "KELOWNA, BC" and "Highlights", which the original
# excluded only by accident — both happened to be short. So a place is now
# excluded for being a place and a section header for being a section header,
# which are the actual reasons.

# A PDF text layer splits the digits of a date as readily as it puts a space
# before the comma: "May 27, 202 6", "February 1 7, 2026". Both shapes are
# datelines and both were invisible here until 2026-09-14.
_DAY = r"\d\s\d|\d{1,2}"
_YEAR = r"20\d\s\d|20\d{2}"

_DOC_DATELINE = re.compile(
    rf"\b(?:{_MONTHS})\.?\s+(?:{_DAY})(?:st|nd|rd|th)?\s*,?\s*(?:{_YEAR})\b"
    rf"|\b(?:{_DAY})\s+(?:{_MONTHS})\.?\s*,?\s*(?:{_YEAR})\b", re.I)

# A dateline introduces the release and sits at the front of its line:
# "Toronto, Ontario – September 10, 2026 – Wesdome". A headline that happens to
# mention a date mentions it late: "DLP Receives Drill Permits at Esperanza;
# First-Ever Drill Program to Commence September 18, 2026" — at character 78.
DATELINE_MAX_POS = 45

_DOC_WIRE = re.compile(
    r"--\s*\(|\(\s*Newsfile|\(\s*GLOBE\s*NEWSWIRE|\(\s*CNW|\(\s*ACCESS\s*Newswire"
    r"|\(\s*Business\s*Wire|\(\s*The\s*Newswire"
    r"|\(\s*ACCESSWIRE|\(\s*PRNewswire|\(\s*Marketwired", re.I)   # TITLES_SPACED_V1

# A street number and a street word, not a bare street word: the original
# matched "road" anywhere, which rejected Mineral Road Corp's own headline.
_DOC_ADDRESS = re.compile(
    r"\d[\d\-–]*\s+[\w.'\- ]{2,30}\b(?:road|rd\.?|street|st\.?|avenue|ave\.?"
    r"|boulevard|blvd\.?|drive|dr\.?|way|lane|highway|hwy)\b"
    r"|\bsuite\b|\bpo\s*box\b|\bwebsite\b\s*:", re.I)

_DOC_CONTACT = re.compile(
    r"[A-Z]\d[A-Z]\s?\d[A-Z]\d|\bfloor\b|\btel\b|\bphone\b|\bfax\b|\bemail\b"
    r"|@|www\.|https?://|\b(?:ARBN|ACN|ABN)\b\s*:?\s*\d"
    r"|^\s*(?:\+\d|\(\d{3}\)\s*\d{3}|\d{3}[\s.\-]\d{3}[\s.\-]\d{4})", re.I)

# Letterhead only where it sits BEFORE the headline. Inside one, the same
# shape is a continuation: "GOLDENCARIBOO.com CSE Stock Symbol GCC" is a
# masthead; "CEO.ca Interview" is the tail of "... Strategic Growth in".
# That is the start/end distinction this module already turns on, and
# collapsing the two is what truncated the Super Copper headline.
_DOC_MASTHEAD = re.compile(r"^\s*[\w-]{3,}\.(?:com|ca|net|org|io|co)\b", re.I)

_DOC_LISTING = re.compile(
    r"^\s*[\(\[]?\s*(TSX[-.\s]?V?|CSE|CNSX|NEO|OTC\w*|FSE|Frankfurt|NYSE|NASDAQ|ASX|AIM)\s*[:\-]",
    re.I)

_DOC_LABEL = re.compile(
    r"^\s*[\W_]*(?:press|news|media)\s*release\b|^\s*for\s+immediate\s+release"
    r"|^\s*item\s+\d", re.I)

# Every alternative here was taken from a real document in the corpus, not
# imagined. The group used to be `not\s+(?:intended\s+for\s+)?(...)`, so the
# commonest form of all -- "NOT FOR DISTRIBUTION" -- never matched, because the
# optional part was "intended for" rather than "for".
#
# The last two alternatives are WRAPPED TAILS. A PDF breaks the disclaimer
# across lines, leaving "UNITED STATES" or "STATES OR FOR DISTRIBUTION TO U.S.
# NEWSWIRE SERVICES" standing alone, and each of those was being read as the
# start of a headline.
_DOC_DISCLAIMER = re.compile(
    r"^\s*(?:this\s+(?:news|press)\s+release\s+is\s+not"
    r"|not\s+(?:intended\s+)?(?:for\s+)?"
    r"(?:distribution|dissemination|release|publication)"
    r"|no\s+securities\s+regulatory\s+authority"
    r"|newswire\s+services?\b"
    r"|material\s+change\s+report\b"
    r"|(?:or\s+)?for\s+(?:distribution|dissemination|release|publication)\b"
    r"|for\s+dissemination"
    r"|(?:the\s+)?united\s+states\s*[.,]?\s*$"
    r"|the\s+united\s+states\s+(?!\w*\s+(?:corporation|corp|inc|antimony))"
    r"|states\s+or\s+for\s+(?:distribution|dissemination|release|publication)"
    r"|(?:in|into)\s+the\s+united\s+states\b[^a-z]*$)", re.I)

_DOC_DISCLAIMER_RUN = re.compile(
    r"^.{0,150}?(?:u\.?s\.?\s+newswire\s+services?|newswire\s+services?"
    r"|(?:in|into|to)\s+the\s+united\s+states|reviewed\s+this\s+document)\b[\s,.:;\-]*", re.I)

_DOC_BULLET = re.compile(r"^\s*[●•▪‣\-\*–]\s")

_DOC_FILENAME = re.compile(r"\.(?:docx?|pdf|html?|txt)\s*$", re.I)

# The section header a mining release puts directly under its headline.
_DOC_SECTION = re.compile(
    r"^\s*(?:key\s+)?(?:highlights?|summary|overview|about|背景)\s*:?\s*$", re.I)

# Deliberately NOT including resources / metals / mining / minerals: "Test Work
# Results from the Mineral Resources" is a headline continuation, and ending in
# an industry word does not make a line a company name.
_DOC_NAME_ONLY = re.compile(
    r"^[\w'&.,\- ]{3,45}\b(?:inc|ltd|corp|corporation|limited|plc|llc)\.?"
    r"(?:\s*\([^)]{0,40}\))?$", re.I)

# "KELOWNA, BC" · "Vancouver, British Columbia" — the dateline's place.
_DOC_PLACE = re.compile(
    r"^([A-Za-z][A-Za-z.\-' ]{1,26}),\s*(?:[A-Z]{2}|British Columbia|Ontario|Alberta"
    r"|Quebec|Québec|Saskatchewan|Manitoba|Nova Scotia|New Brunswick"
    r"|Newfoundland(?: and Labrador)?|Yukon|Nunavut|Nevada|Arizona|Colorado|Utah"
    r"|Idaho|Montana|Texas|California|Washington|Canada|USA)\.?\s*$")

# A dateline's place is a city. A wrapped headline can also end in a region -
# "Project, Nevada", "Gold Strike One Property, Yukon", "Holes at Lisbon
# Valley, Utah" - and treating those as the dateline truncated three of the
# first 53 TMX headlines mid-sentence. What separates them is the text before
# the comma: a city is one to three capitalised tokens, none of them a
# lowercase function word and none an orebody noun.
_NOT_A_CITY = {
    "project", "projects", "property", "properties", "hole", "holes", "mine",
    "mines", "claim", "claims", "target", "targets", "zone", "zones", "deposit",
    "deposits", "area", "areas", "district", "corridor", "corridors", "belt",
    "trend", "basin", "vein", "veins", "prospect", "prospects", "results", "program",
    "programs", "drilling", "phase", "stage", "block", "blocks", "lease",
}


def _is_dateline_place(s: str) -> bool:
    m = _DOC_PLACE.match(s)
    if not m:
        return False
    toks = m.group(1).split()
    if not 1 <= len(toks) <= 3:
        return False
    return all(t[:1].isupper() and t.lower().strip(".,'-") not in _NOT_A_CITY
               for t in toks)

MAX_PROSE_SHARE = 0.45


def reads_as_prose(s: str) -> bool:
    """True when this reads like a sentence out of the body, not a headline.

    Headlines are title-cased or upper-cased; body prose is not. Measured over
    the 47 candidate replacements in the 2026 repair pass, real headlines ran
    0-35% lowercase words and body sentences 54-80%, with nothing in between.
    """
    words = [w for w in (s or "").split() if any(c.isalpha() for c in w)]
    if len(words) < 6:
        return False
    lower = sum(1 for w in words if next(c for c in w if c.isalpha()).islower())
    return lower / len(words) > MAX_PROSE_SHARE


MAX_HEADLINE_CHARS = 220
MAX_SCAN_LINES = 24
MIN_HEADLINE_CHARS = 20
MAX_PLACE_LINE_CHARS = 34


def _has_dateline(s: str) -> bool:
    m = _DOC_DATELINE.search(s)
    return bool(m and m.start() <= DATELINE_MAX_POS)


# --------------------------------------------------------------------------
# TITLES_SPACED_V1 (2026-09-25)
#
# 7,042 approved TSX/TSXV releases were on MNT headlined "News release" (or with
# a letter-spaced masthead glued to the front). Measured on all of them:
#   * 3,514: the first block the walk found was letterhead it did not know -
#     "Vancouver, British Columbia", "TSX.V Trading Symbol: DEC", "Corporate
#     Office", "INVESTOR ANNOUNCEMENT and" - or a REAL headline under 28
#     characters ("Wealth Grants Stock Options"), and the caller's 28-character
#     rule for feed titles threw it away;
#   * 2,959: the first block was a short letterhead line ("Symbol: TSX-V:
#     ATOM", "OTC Pink: TRXXF", "Head Office:", "Littleton, CO 80127");
#   * a letter-spaced masthead ("N E W S R E L E A S E", Franco-Nevada since
#     2025) read as the headline's first line.
# In every case the headline was a few lines further down, and nothing looked.
# So: clean each line first, know more letterhead, and when the first block is
# not a headline, keep walking instead of giving up.
# --------------------------------------------------------------------------
_SPACED_RUN = re.compile(r"^(?:[A-Za-z&.,'\-]\s+){3,}[A-Za-z&.,'\-](?=\s|$)")
_PRIVATE_USE = re.compile("[-]")


def strip_spaced_masthead(s: str) -> str:
    """The line without a leading letter-spaced run ('' when that is all it is)."""
    m = _SPACED_RUN.match(s or "")
    if not m or sum(c.isalpha() for c in m.group(0)) < 4:
        return s
    return s[m.end():].strip()


def _prep_line(l: str) -> str:
    l = _PRIVATE_USE.sub("", (l or "").replace(" ", " ")).strip()
    l = strip_spaced_masthead(l)
    toks = l.split()
    if len(toks) >= 4 and sum(len(t) == 1 for t in toks) >= len(toks) * 0.5:
        return ""                       # "C O PPER C O R P", "W W W. R T M C O R P. C O M"
    return l


_EXCH = (r"\b(?:TSX[-.\s]?V(?:enture)?|TSX|CSE|CNSX|NEX|OTC(?:QB|QX)?|OTC\s+Pink|NYSE(?:\s+American)?"
         r"|NASDAQ|FSE|FRA|Frankfurt|ASX|AIM|SSE|LSE|JSE)\b")
_DOC_EXCH = re.compile(_EXCH, re.I)
_DOC_VERB = re.compile(
    r"(?i)\b(?:announc\w*|reports?|reported|clos\w+|complet\w+|intersect\w*|drill\w*|appoint\w*|provid\w+"
    r"|receiv\w+|signs?|signed|enter\w*|acqui\w+|commenc\w+|launch\w*|files?|filed|grant\w*|updates?|confirm\w*"
    r"|expand\w*|identif\w+|begin\w*|begun|secur\w+|extend\w*|extension|results?|increas\w*|upsiz\w*|lists?"
    r"|listing|trad\w+|declar\w+|elect\w*|approv\w+|terminat\w+|amend\w*|agree\w*|discover\w*|options?"
    r"|placement|financing|offering|dividend|acquisition|merger|arrangement|webinar|presentation|conference"
    r"|guidance|production|resources?|estimate|study|program|update)\b")
_DOC_START_JUNK = re.compile(
    r"^[\w .&'\-]{0,45}?\b(?:trading\s+)?symbols?\s*:"             # "TSX.V Trading Symbol: DEC"
    r"|^\s*(?:head|corporate|executive|registered|main|principal)\s+offices?\b"
    r"|^\s*release\s*:|^\s*(?:investor|asx|market|company)\s+(?:announcement|update)\s*(?:and)?\s*$"
    r"|(?:news|press|media)\s+releases?\s*[-–—:]?\s*$"            # "ODV NYSE TSXV News Release"
    r"|^\s*nr\s*[\d\-/]+\s*$|^\s*\d+\s*\|"                          # "NR 23-33", "1 | Alamos Gold Inc"
    r"|\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b"                             # "Littleton, CO 80127"
    r"|\\[\w .$-]+\\"                                              # a Windows path
    r"|^\s*\(?\s*(?:all\s+(?:amounts|figures|dollar)|expressed\s+in|in\s+u\.?s\.?\s+dollars|unless\s+otherwise)"
    r"|^[A-Z][A-Za-z.\-' ]{1,26},\s*(?:B\.\s?C\.?|Canada|U\.S\.A\.?)\s*$"
    r"|\bsymbols?\s*\("                                               # "Trading Symbol (TSX-V: ANZ)"
    r"|\boffices?\s*:?\s*$"                                          # "Principal & Registered Office:"
    r"|\(\s*(?:the\s+)?[\"\N{LEFT DOUBLE QUOTATION MARK}][^\"\N{RIGHT DOUBLE QUOTATION MARK}]{1,40}[\"\N{RIGHT DOUBLE QUOTATION MARK}]"                  # defined terms: (the "Company")
    r"|^\d{2,5}[\s,]+(?:rue|boul\w*|av\.?|avenue|chemin|de\s+la|du|des)\b", re.I)
_DISCLAIMER_WORDS = re.compile(r"(?i)\b(?:dissemination|distribution|news\s*wires?|newswires?)\b")
_PLACE_ONLY = re.compile(r"^[A-Z][\w.\-']*(?:\s+[A-Z][\w.\-']*)*(?:\s*,\s*[A-Z][\w.\-']*(?:\s+[A-Z][\w.\-']*)*){1,3}\s*,?\s*$")


def _start_junk(s: str) -> bool:
    """Letterhead that only ever appears ABOVE a headline."""
    if _DOC_START_JUNK.search(s):
        return True
    if len(s) <= 70 and _DOC_EXCH.search(s) and not _DOC_VERB.search(s):
        return True                     # "OTC Pink: TRXXF", "TSX Venture:  RCT"
    if len(s) <= 45 and _PLACE_ONLY.match(s) and not _DOC_VERB.search(s):
        return True                     # "Toronto, Ontario, Canada,"
    return len(s) <= MAX_PLACE_LINE_CHARS and _is_dateline_place(s)


def doc_headline_is_hollow(h: str) -> bool:
    """For a headline READ FROM THE DOCUMENT. `title_is_hollow` is tuned for
    feed titles, where a 23-character "Gold Rock Assay Results" is worth
    replacing by the document's; for the document itself a short headline is
    still the headline."""
    h = (h or "").strip()
    if not h or _TITLE_HOLLOW.match(h):
        return True
    if len(h) >= MIN_HEADLINE_CHARS:
        return False
    return not (len(h) >= 12 and len(h.split()) >= 2 and _DOC_VERB.search(h))


def _good_block(out: str) -> bool:
    # Not judged on prose: sentence-case headlines are common ("Zijin Mining
    # exercises its anti-dilution rights ..."), and rejecting them sent the
    # walk down into the body.
    if not out or _TITLE_HOLLOW.match(out):
        return False
    if len(out) >= MIN_HEADLINE_CHARS and len(out.split()) >= 3:
        return True
    return len(out) >= 12 and len(out.split()) >= 2 and bool(_DOC_VERB.search(out))


def _is_letterhead(s: str) -> bool:
    """Things that are never part of a headline, wherever they appear."""
    return bool(_DOC_ADDRESS.search(s) or _DOC_CONTACT.search(s)
                or _has_dateline(s) or _DOC_LISTING.match(s)
                or _DOC_LABEL.match(s) or _DOC_DISCLAIMER.match(s)
                or _DOC_BULLET.match(s) or _DOC_FILENAME.search(s)
                or _DOC_WIRE.search(s))


def _starts_headline(s: str) -> bool:
    """False while we are still walking through letterhead."""
    if len(s) < 12 or _is_letterhead(s) or _DOC_NAME_ONLY.match(s):
        return False
    if _start_junk(s):                  # TITLES_SPACED_V1
        return False
    if _DOC_MASTHEAD.match(s):
        return False
    # A headline does not begin in the middle of a sentence. Judged on the
    # whole first word, so "iMetal Resources ..." keeps its capital and
    # "contrary is an offence ..." does not.
    first = (s.split()[0] if s.split() else "").strip(".,;:!?)(\"'\u201c\u201d\u2018\u2019")
    if first.isalpha() and first.islower():
        return False
    if _DOC_SECTION.match(s) or s.count("|") >= 2:
        return False
    letters = sum(c.isalpha() for c in s)
    return letters >= len(s) * 0.4


def _ends_headline(s: str) -> bool:
    """True for the first line that is no longer part of the headline.

    Notably absent: any test on length, and any company-name test. Both belong
    to finding the start, and applying them here truncated real headlines.
    """
    if _is_letterhead(s) or _DOC_SECTION.match(s):
        return True
    return len(s) <= MAX_PLACE_LINE_CHARS and _is_dateline_place(s)


def _clean_block(block: list[str]) -> str:
    out = re.sub(r"\s+", " ", " ".join(block)).strip()
    cut = _DOC_DISCLAIMER_RUN.sub("", out).strip()
    # A headline may END in "in the United States" ("Surge Upgrades and Begins
    # Trading on the OTCQX in the United States"); cutting to the disclaimer
    # there erased all of it. But a block that is only disclaimer ("OR FOR
    # DISSEMINATION IN THE", "DISSEMINATION IN THE UNITED STATES") is nothing.
    if len(cut) < 12:
        return "" if _DISCLAIMER_WORDS.search(out) else out
    if len(cut) < 60 and _DISCLAIMER_WORDS.search(cut):
        return ""
    return cut


def _block_from(lines: list[str], start: int) -> tuple[str, int]:
    """(headline text, index of the line after it) for a block starting at `start`.

    When the headline sits BELOW the dateline (Franco-Nevada: label,
    "Toronto, July 20, 2026", headline, body) nothing letterhead-like follows
    it - the body does. There, and only there, the first line that reads as
    prose ends the headline. Above the dateline the old rule stands, so a
    sentence-case headline wrapped over two lines is never cut."""
    after_dateline = any(_has_dateline(l) for l in lines[:start])
    block, chars = [], 0
    for i in range(start, len(lines)):
        l = lines[i]
        if block and (_ends_headline(l) or (after_dateline and reads_as_prose(l))):
            return _clean_block(block), i
        block.append(l)
        chars += len(l) + 1
        if chars >= MAX_HEADLINE_CHARS:
            return _clean_block(block), i + 1
    return _clean_block(block), len(lines)


def headline_from_body(body: str, fallback: str = "") -> str:
    """The headline of a news-release PDF, including its wrapped continuation."""
    if not body:
        return fallback
    lines = [_prep_line(l) for l in body.split("\n")]          # TITLES_SPACED_V1
    lines = [l for l in lines if l][:MAX_SCAN_LINES]

    first, i = None, 0
    while i < len(lines):
        start = next((j for j in range(i, len(lines)) if _starts_headline(lines[j])), None)
        if start is None:
            break
        out, nxt = _block_from(lines, start)
        if first is None:
            first = out
        if _good_block(out):
            break
        out = None
        i = max(nxt, start + 1)
    else:
        out = None
    if first is None:
        return fallback
    if out is None:
        out = first                     # nothing better below it: the old answer
    if len(out) < MIN_HEADLINE_CHARS and not _good_block(out):
        return fallback or out
    # Prose loses to anything else there is. With no fallback - TMX, where
    # the document is all there is - it is still better than nothing, and
    # the caller can apply its own judgement with reads_as_prose().
    if fallback and reads_as_prose(out):
        return fallback
    return out[:300]


SELF_TEST = [
    ("ESGold Corp. - Press Release (September 10, 2026)", "", True),
    ("ESGold Corp - Press Release (September 1, 2026)", "", True),
    ("News Release", "", True),
    ("Press Release", "", True),
    ("AREE | Press Release", "", True),
    ("Press Release - August 19, 2026", "", True),
    ("NLR News Release (August 31, 2026)", "", True),
    ("MHL Press Release May 19, 2026", "", True),
    ("HML PR August 26, 2026", "HML PR August 26, 2026", True),
    ("News Release - Krait Commences Trading on Frankfurt Stock Exchange",
     "Krait Commences Trading on Frankfurt Stock Exchange", False),
    ("News Release dated September 4, 2026 - Announcing Definitive Agreement Signing",
     "Announcing Definitive Agreement Signing", False),
    ("News release re Williams 2026 Exploration Update",
     "Williams 2026 Exploration Update", False),
    ("News Release - 1st Tranche of FT Financing Closes, Increases Offering",
     "1st Tranche of FT Financing Closes, Increases Offering", False),
    ("June 30, 2026 News Release - Super Copper Mobilizes for Maiden Drill Program",
     "Super Copper Mobilizes for Maiden Drill Program", False),
    ("July 21, 2026 HML News Release - Year Round Update and Drilling",
     "Year Round Update and Drilling", False),
    ("New Release - Commences IP Survey at Three Guardsman",
     "Commences IP Survey at Three Guardsman", False),
    ("New Release dated May 29, 2026 - Announcing US Listing Application",
     "Announcing US Listing Application", False),
    ("Drilling Results", "Drilling Results", True),
    ("Property update", "Property update", True),
    ("Financing", "Financing", True),
    ("OPTIONS GRANTED", "OPTIONS GRANTED", True),
    ("Results of 2026 AGM", "Results of 2026 AGM", True),
    ("Stock Options Granted", "Stock Options Granted", True),
    ("Gold Rock Assay Results", "Gold Rock Assay Results", True),
    ("Beaumont PP Closing", "Beaumont PP Closing", True),
    ("Private Placement - Tranche 2 Closes", "Private Placement - Tranche 2 Closes", False),
    ("TOCVAN PROVIDES 2025 YEAR IN REVIEW", "TOCVAN PROVIDES 2025 YEAR IN REVIEW", False),
    ("TARGA CLOSES FINAL TRANCHE OF NON-BROKERED PRIVATE PLACEMENT",
     "TARGA CLOSES FINAL TRANCHE OF NON-BROKERED PRIVATE PLACEMENT", False),
    ("Riverside Resources Expands British Columbia Mineral Tenures",
     "Riverside Resources Expands British Columbia Mineral Tenures", False),
    ("Company Issues Press Release Correction Regarding Assay Widths",
     "Company Issues Press Release Correction Regarding Assay Widths", False),
    ("News Release - August Drilling Update at the Example Project",
     "August Drilling Update at the Example Project", False),
]

# Real TMX and CSE documents, trimmed to the lines that matter. Each one broke
# some version of this extractor.
DOC_TEST = [
    ("Scottie Announces $27 Million Non-Brokered\nFinancing\n"
     "Vancouver, British Columbia--(Newsfile Corp. - September 11, 2026) - Scottie Resources\n",
     "Scottie Announces $27 Million Non-Brokered Financing"),

    ("Northmin Announces Positive Metallurgical\nTest Work Results from the Mineral Resources\n"
     "at Tynagh\nToronto, Ontario--(Newsfile Corp. - September 14, 2026) - Northmin Corporation\n",
     "Northmin Announces Positive Metallurgical Test Work Results from the Mineral "
     "Resources at Tynagh"),

    ("Li-FT Power Ltd. ARBN: 696 815 595\n"
     "Suite 1218-1030 West Georgia Street, Vancouver, BC, Canada, V6E 2Y3\n"
     "www.li-ft.com / TSX-V: LIFT / ASX: LFT / OTCQX: LIFFF / FRA: WS0\n"
     "LI-FT POWER PROJECTS FEATURED IN CANADA INVESTMENT\nSUMMIT PROSPECTUS\n"
     "September 14, 2026 – Vancouver, B.C., Li-FT Power Ltd.\n",
     "LI-FT POWER PROJECTS FEATURED IN CANADA INVESTMENT SUMMIT PROSPECTUS"),

    ("Prospector Completes Return of Capital\n"
     "Vancouver, British Columbia--(Newsfile Corp. - September 11, 2026) -\n",
     "Prospector Completes Return of Capital"),

    ("2026-09-10 AGM Results - Draft.docx\nInomin Announces AGM Results\n"
     "Vancouver, British Columbia--(Newsfile Corp. - September 11, 2026) - Inomin Mines\n",
     "Inomin Announces AGM Results"),

    ("THIS NEWS RELEASE IS NOT FOR DISTRIBUTION TO U.S. NEWSWIRE SERVICES\n"
     "OR FOR DISSEMINATION IN THE UNITED STATES\n"
     "LAKE WINN ANNOUNCES PRIVATE PLACEMENT\n"
     "Vancouver, British Columbia – September 10, 2026 – Lake Winn Resources\n",
     "LAKE WINN ANNOUNCES PRIVATE PLACEMENT"),

    ("• All required permits received – DLP has received the necessary permits\n"
     "DLP Receives Drill Permits at Esperanza\n"
     "Vancouver, British Columbia – September 9, 2026 – DLP Resources\n",
     "DLP Receives Drill Permits at Esperanza"),

    # the headline itself names a date, late in a long line, and a section
    # header follows it
    ("DLP Receives Drill Permits at Esperanza; First-Ever Drill Program to Commence "
     "September 18, 2026\nHighlights\n"
     "• All required permits received – DLP has received the necessary permits\n",
     "DLP Receives Drill Permits at Esperanza; First-Ever Drill Program to Commence "
     "September 18, 2026"),

    ("CANTEX CLOSED SECOND TRANCHE OF PRIVATE PLACEMENT\nKELOWNA, BC\n"
     "September 11, 2026 - Cantex Mine Development Corp.\n",
     "CANTEX CLOSED SECOND TRANCHE OF PRIVATE PLACEMENT"),

    ("12 Mitchell Road\nFlin Flon, Manitoba R8A 1N1\nTel: 204-687-3500\n"
     "Email: BorealGoldInc@gmail.com\nWebsite: BorealGold.ca\nBGLD (CSE)\n"
     "Boreal Gold Closes the Second Tranche Private Placement for $594,999.80\n"
     "Flin Flon, Manitoba, September 9, 2026 –Boreal Gold Inc (CSE:BGLD)\n",
     "Boreal Gold Closes the Second Tranche Private Placement for $594,999.80"),

    ("Wesdome Gold Mines Ltd\n8 King Street East, Suite 811\nToronto, ON M5C 1B5\n"
     "NEWS RELEASE\nWESDOME INTERSECTS 7.8 G/T GOLD OVER 57.2 METRES AT KIENA DEEP\n"
     "Toronto, Ontario – September 10, 2026 – Wesdome Gold Mines Ltd.\n",
     "WESDOME INTERSECTS 7.8 G/T GOLD OVER 57.2 METRES AT KIENA DEEP"),

    # A wrapped headline whose second line ends in a region is not the
    # dateline. All three of these truncated real TMX headlines mid-sentence.
    ("Toogood Gold Defines Two Priority Drill Target Corridors at the Table Mountain\n"
     "Project, Nevada\n"
     "Vancouver, British Columbia – September 10, 2026 – Toogood Gold Corp.\n",
     "Toogood Gold Defines Two Priority Drill Target Corridors at the Table Mountain "
     "Project, Nevada"),

    ("Gold Strike Announces Magnetic Survey Results Identifying Exploration Targets at\n"
     "Gold Strike One Property, Yukon\n"
     "Vancouver, BC – September 10, 2026 – Gold Strike Resources Ltd.\n",
     "Gold Strike Announces Magnetic Survey Results Identifying Exploration Targets "
     "at Gold Strike One Property, Yukon"),

    ("Manhattan Uranium Identifies 3.70% eU3O8 Over 5.2 ft in Compilation of 499 Historical Drill\n"
     "Holes at Lisbon Valley, Utah\n"
     "Vancouver, British Columbia – September 10, 2026 – Manhattan Uranium Corp.\n",
     "Manhattan Uranium Identifies 3.70% eU3O8 Over 5.2 ft in Compilation of 499 "
     "Historical Drill Holes at Lisbon Valley, Utah"),

    # "September 14 , 2026" - a space before the comma. The dateline was not
    # recognised, so it ran into the headline.
    ("NexGold’s Goldboro Project Selected for Inclusion in the Canada Investment Summit\n"
     "Prospectus\n"
     "TORONTO, September 14 , 2026 – NexGold Mining Corp. (TSXV: NEXG ; OTCQX: NXGCF)\n",
     "NexGold’s Goldboro Project Selected for Inclusion in the Canada Investment "
     "Summit Prospectus"),

    ("Inomin Announces AGM Results\n"
     "Vancouver, British Columbia – September 11 , 2026 – Inomin Mines Inc. (TSXV: MINE)\n",
     "Inomin Announces AGM Results"),

    # Boilerplate the extractor used to mistake for a headline. Each of
    # these replaced a real feed title during the 2026 repair dry run.
    ("No securities regulatory authority or regulator has assessed the merits of\n"
     "these securities or reviewed this document.\n"
     "Ashley Gold Corp. Announces Amended and Restated Offering Document\n",
     "Ashley Gold Corp. Announces Amended and Restated Offering Document"),

    ("NOT INTENDED FOR DISTRIBUTION TO UNITED STATES NEWS WIRE SERVICES OR\n"
     "FOR DISSEMINATION IN THE UNITED STATES\n"
     "Hemlo Explorers Announces Closing of Private Placement\n",
     "Hemlo Explorers Announces Closing of Private Placement"),

    ("(OTCQB: PMOMF) is pleased to invite investors to attend the webinar\n"
     "Prismo Metals to Host Webinar on Recent Drill Results\n",
     "Prismo Metals to Host Webinar on Recent Drill Results"),

    ("GOLDENCARIBOO.com CSE Stock Symbol GCC\n"
     "Golden Cariboo Closes $700,000 Non-Brokered Private Placement\n",
     "Golden Cariboo Closes $700,000 Non-Brokered Private Placement"),

    # A headline may name a website without being letterhead.
    ("Super Copper Founder Discusses High-Grade Results and Strategic Growth in\n"
     "CEO.ca Interview\n"
     "Vancouver, British Columbia \u2013 January 21, 2026 \u2013 Super Copper Corp.\n",
     "Super Copper Founder Discusses High-Grade Results and Strategic Growth in "
     "CEO.ca Interview"),

    # ... but a stock-symbol line and a phone-number line are letterhead
    ("GOLDENCARIBOO.com CSE Stock Symbol GCC\n"
     "Golden Cariboo Closes $700,000 Non-Brokered Private Placement\n",
     "Golden Cariboo Closes $700,000 Non-Brokered Private Placement"),

    ("+1 587 777 9072| ashleygoldcorp.com\n"
     "Ashley Gold Corp. Announces Strategic Acquisition of the Hyndman Flank Project\n",
     "Ashley Gold Corp. Announces Strategic Acquisition of the Hyndman Flank Project"),

    # a headline does not start in the middle of a sentence
    ("contrary is an offence. This Offering may not be suitable for you and you\n"
     "should only invest in it if you are willing to risk the loss.\n"
     "Ashley Gold Corp. Announces Amended and Restated Offering Document\n",
     "Ashley Gold Corp. Announces Amended and Restated Offering Document"),

    # a material change report is not a news release
    ("Material Change Report\n"
     "Item 1. Name and Address of Company\n"
     "Nevada Organic Phosphate Inc. Reports Drill Results at Pine Valley\n",
     "Nevada Organic Phosphate Inc. Reports Drill Results at Pine Valley"),

    # "stock symbol" in a headline is a headline; a line that OPENS with a
    # domain is letterhead.
    ("Hi-VIEW RESOURCES INC. ANNOUNCES CHANGE OF STOCK SYMBOL TO GXLD\n"
     "Vancouver, British Columbia \u2013 January 7, 2026 \u2013 Hi-View Resources Inc.\n",
     "Hi-VIEW RESOURCES INC. ANNOUNCES CHANGE OF STOCK SYMBOL TO GXLD"),

    # an ISO date is a run of digits and dashes, but it is not a phone number
    ("2026-03-05 NEWS\n"
     "Adelphi Metals Amends Previously Announced Private Placement\n",
     "Adelphi Metals Amends Previously Announced Private Placement"),

    # the first word carries a full stop, and is still the middle of a sentence
    ("investment. In making this investment decision, you should seek advice\n"
     "from a registered dealer before proceeding any further with this.\n"
     "Ashley Gold Corp. Announces Amended and Restated Offering Document\n",
     "Ashley Gold Corp. Announces Amended and Restated Offering Document"),

    # a bare company name, with or without its defined term, is not a headline
    ("Material Change Report\n"
     "Item 2. Date of Material Change\n"
     "Nevada Organic Phosphate Inc. (the \u201cCompany\u201d)\n"
     "Nevada Organic Phosphate Reports Drill Results at Pine Valley\n",
     "Nevada Organic Phosphate Reports Drill Results at Pine Valley"),

    # The text layer split the digits of the year, so the dateline was
    # invisible and ran into the headline. Seen live in the TMX backfill.
    ("Metalero Announces $3.0M Private Placement\n"
     "Edmonton, AB, May 27, 202 6 \u2013 Metalero Mining Corp. (TSXV: MLO)\n",
     "Metalero Announces $3.0M Private Placement"),

    ("One Step Closer to Cash Flow: Average grades of 3.72g/t Au from 1930s Rockpiles\n"
     "VANCOUVER, BC, February 1 7, 2026 \u2013 Heritage Mining Ltd. (CSE: HML)\n",
     "One Step Closer to Cash Flow: Average grades of 3.72g/t Au from 1930s Rockpiles"),

    # TITLES_SPACED_V1 - all from the 7,042 releases that were on MNT as
    # "News release". A letter-spaced masthead is letterhead (Franco-Nevada).
    ("N E W S R E L E A S E\nNEWS RELEASE\nToronto, July 20, 2026\n"
     "Franco-Nevada to Release Second Quarter 2026 Results\n"
     "Franco-Nevada Corporation announced today that it will report second quarter\n",
     "Franco-Nevada to Release Second Quarter 2026 Results"),
    ("N E W S R E L E A S E\nNEWS RELEASE\nToronto, March 10, 2026\n"
     "(in U.S. dollars unless otherwise noted)\nFranco-Nevada Reports Record 2025 Results\n"
     "Strong Finish to the Year\n2025 was a record-breaking year for Franco-Nevada driven by higher\n",
     "Franco-Nevada Reports Record 2025 Results Strong Finish to the Year"),
    ("P R E S S R E L E A S E CASH DIVIDEND FOR THE SECOND QUARTER\n"
     "Toronto, Ontario, May 12, 2026 - Labrador Iron Ore Royalty Corporation\n",
     "CASH DIVIDEND FOR THE SECOND QUARTER"),
    ("S U R G E\nC O PPER  C O R P\n"
     "PO Box 10351 888 - 700 West Georgia Street Vancouver, BC  V7Y 1G5  P: 604-718-5454\n"
     "SURGE COPPER AMENDS THE TERMS OF ITS RECENTLY ANNOUNCED FINANCING, WHILE\n"
     "OOTSA DRILL PREPARATIONS ARE UNDERWAY\n"
     "NOT FOR DISTRIBUTION TO U.S. NEWSWIRE SERVICES OR FOR DISSEMINATION\n",
     "SURGE COPPER AMENDS THE TERMS OF ITS RECENTLY ANNOUNCED FINANCING, WHILE OOTSA DRILL PREPARATIONS ARE UNDERWAY"),
    # letterhead the walk did not know, above the headline
    ("SABLE RESOURCES LTD.\n900 – 999 West Hastings Street\nVancouver, British Columbia\n"
     "V6C 2W2 Canada\nTSXV | SAE       OTCQB | SBLRF\nSable Expands Cu-Au Footprint and Identifies\n"
     "New Copper and Gold Targets Ahead of Maiden Drill Program\nat the Zorro Project, San Juan, Argentina\n",
     "Sable Expands Cu-Au Footprint and Identifies New Copper and Gold Targets Ahead of Maiden "
     "Drill Program at the Zorro Project, San Juan, Argentina"),
    ("1\nFor Immediate Release\nPRESS RELEASE\nApril 9, 2026\nSymbol: TSX-V:  ATOM\nFSE: DO8\n"
     "OTCQB: ATMMF\nAtomic Minerals Highlights Strategic Role Amid Possible Iran\n",
     "Atomic Minerals Highlights Strategic Role Amid Possible Iran"),
    ("TSX Venture:  RCT\nFrankfurt:  R5I\nSuite 1305-1090 W. Georgia St., Vancouver, BC, V6E 3V7\n"
     "News Release\nROCHESTER PROVIDES UPDATE ON DEBT SETTLEMENT\n"
     "Vancouver, British Columbia – December 11th 2020: - Rochester Resources Ltd. (the “Company”)\n",
     "ROCHESTER PROVIDES UPDATE ON DEBT SETTLEMENT"),
    ("10758 W. Centennial Rd.\nLittleton, CO 80127\nPhone: 720.981.4588\nwww.ur-energy.com\nNews Release\n"
     "Join Ur-Energy’s CEO John Cash for a Live Webinar June 20, 2023 hosted by Red Cloud\n"
     "Littleton, C olorado (ACCESSWIRE – June 14, 2 023) Ur-Energy Inc. (NYSE American:URG)\n",
     "Join Ur-Energy’s CEO John Cash for a Live Webinar June 20, 2023 hosted by Red Cloud"),
    ("Corporate Office\n1055 Dunsmuir Street\nSuite 2800, Bentall IV\nVancouver, BC V7X 1L2\n"
     "Phone: +1 604 689 7842\nlundinmining.com\nNEWS RELEASE\n"
     "Lundin Mining Announces Updated Share Capital and Provides Update on Share\n",
     "Lundin Mining Announces Updated Share Capital and Provides Update on Share"),
    ("- 1 -\nNEWS RELEASE\nNovember 25th, 2020\nTrading Symbols:\nTSX: AMM; NYSE American: AAU\n"
     "www.almadenminerals.com\nAlmaden Announces Pathfinder Elements Validate SE Alteration Zone Potential\n"
     "for Epithermal Veining\n",
     "Almaden Announces Pathfinder Elements Validate SE Alteration Zone Potential for Epithermal Veining"),
    ("Galway Metals Inc.\n82 Richmond Street East, Toronto, Ontario, M5C 1P1\nTSXV – GWM\nOTCQB – GAYMF\n1\n"
     "NEWS RELEASE\nGalway Metals Confirms Improved Au and Sb Recovery with Process\nOptimization\n",
     "Galway Metals Confirms Improved Au and Sb Recovery with Process Optimization"),
    ("Media Release\nRelease: Immediate\nNOT FOR DISSEMINATION IN THE UNITED STATES OR THROUGH U.S. NEWSWIRES\n"
     "GFG Provides Update on Private Placement of Flow Through\nFinancing\n"
     "December 14, 2018, Saskatoon, Saskatchewan, Canada: GFG Resources Inc. (TSX-V: GFG)\n",
     "GFG Provides Update on Private Placement of Flow Through Financing"),
    ("CONTACT:  NIC EARNER, MANAGING DIRECTOR & CEO, ALKANE RESOURCES LTD, TEL +61 8 9227 5677\n"
     "ABN: 35 000 689 216  |  Telephone: +61 8 9227 5677  |  alkres.com  |  mail@alkres.com\n"
     "INVESTOR ANNOUNCEMENT and\nMEDIA RELEASE\n5 May 2025\nAlkane Resources Provides Notice of Release of\n"
     "Quarterly Results\n",
     "Alkane Resources Provides Notice of Release of Quarterly Results"),
    ("ODV NYSE TSXV News Release\nwww.osiskodev.com  Page 1 of 4\n"
     "OSISKO DEVELOPMENT SECURES US$450 MILLION FINANCING FACILITY TO\nDEVELOP THE CARIBOO GOLD PROJECT\n"
     "Montreal, Québec, July 21, 2025 – Osisko Development Corp. (NYSE: ODV, TSXV: ODV) (\"Osisko\n",
     "OSISKO DEVELOPMENT SECURES US$450 MILLION FINANCING FACILITY TO DEVELOP THE CARIBOO GOLD PROJECT"),
    ("T R A D I N G   S Y M B O L:   T S X: A G I    N Y S E: A G I\n1 | Alamos Gold Inc\nAlamos Gold Inc.\n"
     "Brookfield Place, 181 Bay Street, Suite 3910, P .O. Box #823\n"
     "All amounts are in United States dollars, unless otherwise stated.\n"
     "Alamos Gold Reports Fourth Quarter and Year-End 2017 Results\n",
     "Alamos Gold Reports Fourth Quarter and Year-End 2017 Results"),
    ("Decade Resources Ltd.\n426 King Street\nStewart, BC\nV0T 1W0\nTSX.V Trading Symbol: DEC\nNEWS RELEASE\n"
     "August 10, 2023\nDECADE ANNOUNCES NON-BROKERED PRIVATE PLACEMENT BACKED BY\nCRESCAT CAPITAL\n",
     "DECADE ANNOUNCES NON-BROKERED PRIVATE PLACEMENT BACKED BY CRESCAT CAPITAL"),
    # a real headline shorter than a feed title may be
    ("#2710 – 200 Granville Street, Vancouver, BC Canada V6C 1S4\n"
     "Tel 604.331.0096  Fax 604.408.7499 www.wealthminerals.com\nNR22-02 March 18, 2022\n"
     "Wealth Grants Stock Options\nFOR IMMEDIATE RELEASE....Vancouver, British Columbia: Wealth Minerals Ltd. (the\n",
     "Wealth Grants Stock Options"),
    ("TSX.V :  GGX\nFRA :  3SR2\nOTCQB :  GGXXF\nJune 5, 2018\nCorporate Update\n"
     "Vancouver, British Columbia – June 5 , 2018 – GGX Gold Corp. (TSX.V: GGX)\n",
     "Corporate Update"),
    # a headline that ends in "in the United States" is not a disclaimer
    ("Surge Upgrades and Begins Trading on the\nOTCQX in the United States\n"
     "West Vancouver, British Columbia--(Newsfile Corp. - September 28, 2023) -\n",
     "Surge Upgrades and Begins Trading on the OTCQX in the United States"),

    # a sentence-case headline is still the headline, not a reason to walk on
    ("Zijin Mining exercises its anti-dilution rights, generating additional proceeds for Ivanhoe Mines of C$67 million\n"
     "BEIJING, CHINA \N{EN DASH} May 15, 2019 \N{EN DASH} Robert Friedland, Co-Chairman of Ivanhoe Mines, announced today\n",
     "Zijin Mining exercises its anti-dilution rights, generating additional proceeds for Ivanhoe Mines of C$67 million"),
    # disclaimer tails, places, defined terms and symbol lines are not headlines
    ("NOT FOR DISTRIBUTION TO U.S. NEWSWIRE SERVICES\nOR FOR DISSEMINATION IN THE\nUNITED STATES\n"
     "Toronto, Ontario, Canada,\nTrading Symbol (TSX-V: ANZ)\n"
     "Alianza Minerals Closes Private Placement\n",
     "Alianza Minerals Closes Private Placement"),
    ("Moneta Porcupine Mines Inc. (TSX:ME)\n(XETRA:MOP) (\"Moneta\" or the \"Company\")\n"
     "Moneta Announces Drill Results at Golden Highway\n",
     "Moneta Announces Drill Results at Golden Highway"),

    # a company whose name contains a street word must keep its headline
    ("MINERAL ROAD COMMISSIONS STRATEGIC REVIEW OF SIGNIFICANT\n"
     "BERGSLAGEN TUNGSTEN PROJECT IN SWEDEN\n"
     "Vancouver, British Columbia – August 4, 2026 – Mineral Road Corp.\n",
     "MINERAL ROAD COMMISSIONS STRATEGIC REVIEW OF SIGNIFICANT BERGSLAGEN TUNGSTEN "
     "PROJECT IN SWEDEN"),
]


PROSE_TEST = [
    # real headlines taken from the 2026 repair pass
    ("Heritage Doubles Down at Melba: Expands Land Package ahead of Pending Drill "
     "Results", False),
    ("ESGold Files Amended LIFE Offering Document to include Quebec as an Offering "
     "Jurisdiction for Previously Announced Brokered LIFE Offering", False),
    ("Boreal Gold Reports 15.54 g/t Gold over 2.41m in Drill Hole GR-26-149 "
     "Including 81.5 g/t Gold over 0.41m in the High-Grade Gold Rock Vein", False),
    ("Military Metals Reports Maiden Inferred Resource Estimate Containing 67,000 "
     "Tonnes of Antimony and 222,000 Ounces of Gold at Flagship Trojarova", False),
    ("One Step Closer to Cash Flow: Average grades of 3.72g/t Au and 0.96g/t Au "
     "from 1930s Rockpiles at Drayton - Black Lake", False),
    ("Forty Pillars Announces Program Results on the Silver Dollar Project", False),
    # and the three body sentences it offered in their place
    ("This Offering Document constitutes an offering of these securities only in "
     "those jurisdictions where they may be lawfully offered for sale", True),
    ("CEO Alain Lambert and Chief Exploration Officer Dr. Craig Gibson will discuss "
     "the upcoming drill program at its Silver King project near Superior", True),
    ("The Company announced that, further to its news releases dated", True),
    # too short to judge
    ("Options Granted", False),
]


def self_test(verbose: bool = True) -> int:
    """Returns 0 when every case passes. Cheap, and the only thing standing
    between a bad regex and thousands of headlines on three public sites."""
    bad = 0
    for raw, want_clean, want_hollow in SELF_TEST:
        got = clean_title(raw)
        hollow = title_is_hollow(got)
        ok = (got == want_clean) and (hollow == want_hollow)
        if not ok:
            bad += 1
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  {raw[:52]:<52} -> {got[:40]!r:<42} "
                  f"distrust={hollow}"
                  f"{'' if ok else f'   WANTED {want_clean!r} distrust={want_hollow}'}")
    for body, want in DOC_TEST:
        got = headline_from_body(body)
        ok = got == want
        if not ok:
            bad += 1
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  doc -> {got[:70]!r}"
                  f"{'' if ok else f'{chr(10)}        WANTED {want[:70]!r}'}")
    for raw, want in PROSE_TEST:
        got = reads_as_prose(raw)
        ok = got == want
        if not ok:
            bad += 1
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  prose={str(got):<5} {raw[:58]!r}")
    total = len(SELF_TEST) + len(DOC_TEST) + len(PROSE_TEST)
    if verbose:
        print(f"\n{total - bad}/{total} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(self_test())
