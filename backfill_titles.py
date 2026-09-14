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

_DATEISH = (r"(?:\(?\s*(?:dated\s+)?[A-Za-z]{3,9}\.?\s+\d{1,2},?\s*20\d{2}\s*\)?)")

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
# is also what swept in "KELOWNA, BC", which the original excluded only by
# accident — it happened to be 11 characters. So a place is now excluded for
# being a place, which is the actual reason.

_DOC_DATELINE = re.compile(
    rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s*20\d{{2}}\b"
    rf"|\b\d{{1,2}}\s+(?:{_MONTHS})\.?,?\s*20\d{{2}}\b", re.I)

# The wire's stamp, always at the start of the dateline:
# "Vancouver, British Columbia--(Newsfile Corp. - September 11, 2026) -"
_DOC_WIRE = re.compile(
    r"--\s*\(|\(\s*Newsfile|\(\s*GLOBE\s*NEWSWIRE|\(\s*CNW|\(\s*ACCESS\s*Newswire"
    r"|\(\s*Business\s*Wire|\(\s*The\s*Newswire", re.I)

_DOC_LETTERHEAD = re.compile(
    r"[A-Z]\d[A-Z]\s?\d[A-Z]\d|\bsuite\b|\bstreet\b|\bavenue\b|\bboulevard\b"
    r"|\bfloor\b|\btel\b|\bphone\b|\bfax\b|\bemail\b|@|www\.|https?://|\bPO Box\b"
    r"|\b(?:ARBN|ACN|ABN)\b\s*:?\s*\d", re.I)

_DOC_LISTING = re.compile(
    r"^\s*(TSX[-.\s]?V?|CSE|CNSX|NEO|OTC\w*|FSE|Frankfurt|NYSE|NASDAQ|ASX|AIM)\s*[:\-]",
    re.I)

_DOC_LABEL = re.compile(
    r"^\s*[\W_]*(?:press|news|media)\s*release\b|^\s*for\s+immediate\s+release", re.I)

# The U.S. distribution disclaimer, including the second line of a wrapped one:
# "THIS NEWS RELEASE IS NOT FOR DISTRIBUTION TO U.S. NEWSWIRE SERVICES" /
# "OR FOR DISSEMINATION IN THE UNITED STATES"
_DOC_DISCLAIMER = re.compile(
    r"^\s*(?:this\s+(?:news|press)\s+release\s+is\s+not"
    r"|not\s+for\s+(?:distribution|dissemination|release)"
    r"|or\s+for\s+(?:distribution|dissemination)"
    r"|for\s+dissemination)", re.I)

# The same disclaimer where it ran onto the headline's own line.
_DOC_DISCLAIMER_RUN = re.compile(
    r"^.{0,150}?(?:u\.?s\.?\s+newswire\s+services?|newswire\s+services?"
    r"|(?:in|into|to)\s+the\s+united\s+states)\b[\s,.:;\-]*", re.I)

_DOC_BULLET = re.compile(r"^\s*[●•▪‣\-\*–]\s")

_DOC_FILENAME = re.compile(r"\.(?:docx?|pdf|html?|txt)\s*$", re.I)

# A line that is only a company name is letterhead. Deliberately NOT including
# resources / metals / mining / minerals: "Test Work Results from the Mineral
# Resources" is a headline continuation, and ending in an industry word does not
# make a line a company name.
_DOC_NAME_ONLY = re.compile(
    r"^[\w'&.,\- ]{3,45}\b(?:inc|ltd|corp|corporation|limited|plc|llc)\.?$", re.I)

# "KELOWNA, BC" · "Vancouver, British Columbia" — the dateline's place, which
# often sits on its own short line straight after the headline.
_DOC_PLACE = re.compile(
    r"^[A-Za-z][A-Za-z.\-' ]{1,26},\s*(?:[A-Z]{2}|British Columbia|Ontario|Alberta"
    r"|Quebec|Québec|Saskatchewan|Manitoba|Nova Scotia|New Brunswick"
    r"|Newfoundland(?: and Labrador)?|Yukon|Nunavut|Nevada|Arizona|Colorado|Utah"
    r"|Idaho|Montana|Texas|California|Washington|Canada|USA)\.?\s*$")

MAX_HEADLINE_CHARS = 220
MAX_SCAN_LINES = 24
MIN_HEADLINE_CHARS = 20
MAX_PLACE_LINE_CHARS = 34


def _is_letterhead(s: str) -> bool:
    """Things that are never part of a headline, wherever they appear."""
    return bool(_DOC_LETTERHEAD.search(s) or _DOC_DATELINE.search(s)
                or _DOC_LISTING.match(s) or _DOC_LABEL.match(s)
                or _DOC_DISCLAIMER.match(s) or _DOC_BULLET.match(s)
                or _DOC_FILENAME.search(s) or _DOC_WIRE.search(s))


def _starts_headline(s: str) -> bool:
    """False while we are still walking through letterhead."""
    if len(s) < 12 or _is_letterhead(s) or _DOC_NAME_ONLY.match(s):
        return False
    if s.count("|") >= 2:
        return False
    letters = sum(c.isalpha() for c in s)
    return letters >= len(s) * 0.4


def _ends_headline(s: str) -> bool:
    """True for the first line that is no longer part of the headline.

    Notably absent: any test on length, and any company-name test. Both belong
    to finding the start, and applying them here truncated real headlines.
    """
    if _is_letterhead(s):
        return True
    return bool(len(s) <= MAX_PLACE_LINE_CHARS and _DOC_PLACE.match(s))


def headline_from_body(body: str, fallback: str = "") -> str:
    """The headline of a news-release PDF, including its wrapped continuation."""
    if not body:
        return fallback
    lines = [l.strip() for l in body.split("\n")]
    lines = [l for l in lines if l][:MAX_SCAN_LINES]

    start = next((i for i, l in enumerate(lines) if _starts_headline(l)), None)
    if start is None:
        return fallback

    block, chars = [], 0
    for l in lines[start:]:
        if block and _ends_headline(l):
            break
        block.append(l)
        chars += len(l) + 1
        if chars >= MAX_HEADLINE_CHARS:
            break
    out = re.sub(r"\s+", " ", " ".join(block)).strip()
    out = _DOC_DISCLAIMER_RUN.sub("", out).strip()
    if len(out) < MIN_HEADLINE_CHARS:
        return fallback or out
    return out[:300]


SELF_TEST = [
    # (raw title, expected cleaned, expected distrusted?)
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

# Real TMX and CSE documents, trimmed to the lines that matter. The first four
# were broken by the original extractor; the last five were broken by the
# rewrite that fixed those four.
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

    # a filename, not a headline
    ("2026-09-10 AGM Results - Draft.docx\nInomin Announces AGM Results\n"
     "Vancouver, British Columbia--(Newsfile Corp. - September 11, 2026) - Inomin Mines\n",
     "Inomin Announces AGM Results"),

    # the disclaimer, and its wrapped second line
    ("THIS NEWS RELEASE IS NOT FOR DISTRIBUTION TO U.S. NEWSWIRE SERVICES\n"
     "OR FOR DISSEMINATION IN THE UNITED STATES\n"
     "LAKE WINN ANNOUNCES PRIVATE PLACEMENT\n"
     "Vancouver, British Columbia – September 10, 2026 – Lake Winn Resources\n",
     "LAKE WINN ANNOUNCES PRIVATE PLACEMENT"),

    # a bullet is body, never a headline
    ("• All required permits received – DLP has received the necessary permits\n"
     "DLP Receives Drill Permits at Esperanza\n"
     "Vancouver, British Columbia – September 9, 2026 – DLP Resources\n",
     "DLP Receives Drill Permits at Esperanza"),

    # the dateline's place on its own short line
    ("CANTEX CLOSED SECOND TRANCHE OF PRIVATE PLACEMENT\nKELOWNA, BC\n"
     "September 11, 2026 - Cantex Mine Development Corp.\n",
     "CANTEX CLOSED SECOND TRANCHE OF PRIVATE PLACEMENT"),

    # letterhead first, then the headline — the shape the original handled well
    ("Wesdome Gold Mines Ltd\n8 King Street East, Suite 811\nToronto, ON M5C 1B5\n"
     "NEWS RELEASE\nWESDOME INTERSECTS 7.8 G/T GOLD OVER 57.2 METRES AT KIENA DEEP\n"
     "Toronto, Ontario – September 10, 2026 – Wesdome Gold Mines Ltd.\n",
     "WESDOME INTERSECTS 7.8 G/T GOLD OVER 57.2 METRES AT KIENA DEEP"),
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
    total = len(SELF_TEST) + len(DOC_TEST)
    if verbose:
        print(f"\n{total - bad}/{total} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(self_test())
