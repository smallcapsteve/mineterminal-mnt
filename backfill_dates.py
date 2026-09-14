#!/usr/bin/env python3
"""The exchange states the ticker. It does not state when the release was issued.

The CSE feed's `date` is **when the exchange received the document**, not when
the company issued it. For a prompt filer those are the same day. For a late or
batch filer they are not: Etruscus uploaded five releases on 2026-08-13 that had
been issued between February and November 2025.

That single fact caused the duplicates in the 2026 backfill. A release ingested
under its *upload* date sits weeks or months away from the wire's copy of the
same release, so `find_match`'s ±3 day window — and the portal's own
date-bounded fuzzy-duplicate guard — could not pair them, and the release was
published twice.

**Scored against ground truth.** For 260 releases a wire copy already existed,
and the wire's date is the real one:

    feed date       within 1 day of truth:   56/260  (22%),  median error 16 days
    extracted date  within 1 day of truth:  177/260  (68%),  median error  0 days

**The window was measured, not guessed.** Four windows against two strategies:

    window   plain          skipping "year ended"/"as at" context
      700    158 within 1d   156
     1000    167             164
     1400    168             165
     1800    170             167          <- plain 1800 wins outright

Filtering out dates that sit next to "year ended", "as at", "effective" and
similar *lost* accuracy at every window: those phrases appear in the boilerplate
around real datelines more often than they introduce a decoy.

**Issuers mistype the year.** Prismo's document reads "February 26th, 2025" for
a release the wire dates 2026-02-27; Peloton's reads "January 28, 2025" for
2026-01-28. Both are the familiar new-year slip. A date 330-400 days before
upload whose next-year equivalent lands within 21 days of the upload is treated
as a mistyped year and corrected.

The 21-day bound is the whole safety margin, and it is there for Etruscus: its
genuinely year-old filings sit 399 days before upload and would land 34 days
before it after "correction", so they are left alone. Widen that bound and real
history gets silently shifted forward a year.

Applied to the 1,675 backfilled rows: 1,563 dates from the dateline, 16 with a
mistyped year corrected, 96 with no readable date falling back to the upload
date. **465 dates moved.**

    python3 backfill_dates.py          # run the self-test
"""
from __future__ import annotations

import datetime as dt
import re
import sys

_MON = {m: i + 1 for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split())}

_MONTH = (r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
          r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|"
          r"Dec(?:ember)?")

# A PDF text layer splits the digits of a date as readily as it puts a space
# before the comma: "May 27, 202 6", "February 1 7, 2026". The split forms are
# listed first so a plain date still matches the plain branch, and the captured
# digits have their space removed before int().
_DAY = r"\d\s\d|\d{1,2}"
_YEAR = r"20\d\s\d|20\d{2}"


def _digits(s: str) -> int:
    return int(s.replace(" ", ""))


_PATTERNS = [
    # September 9, 2026 · Sept. 11, 2026 · February 26th, 2025
    re.compile(rf"\b({_MONTH})\.?\s+({_DAY})(?:st|nd|rd|th)?\s*,?\s*({_YEAR})\b", re.I),
    # 10 SEPTEMBER, 2026 · 9th June 2026
    re.compile(rf"\b({_DAY})(?:st|nd|rd|th)?\s+({_MONTH})\.?\s*,?\s*({_YEAR})\b", re.I),
    # 2026-09-09
    re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b"),
]

# A dateline that ran into the headline. `headline_from()` splits on lines, so
# when a PDF puts both on one extracted line the date comes along:
#   "OPTIONS GRANTED July 17th, 2026 – Muskoka - Ontario – Steadright..."
_DATELINE_HEAD = re.compile(
    rf"\s*[-–—(,]?\s*\b(?:{_MONTH})\.?\s+(?:{_DAY})(?:st|nd|rd|th)?\s*,?\s*(?:{_YEAR})\b",
    re.I)

WINDOW = 1800          # characters of the document to consider; measured, see above
MAX_BACKDATE_DAYS = 1100
YEAR_TYPO_MIN, YEAR_TYPO_MAX = 330, 400
YEAR_TYPO_TOLERANCE_DAYS = 21
MIN_HEADLINE_AFTER_TRIM = 12


def trim_at_dateline(headline: str) -> str:
    """Cut a headline at the point its document's dateline begins.

    Two guards, both paid for:

    Enough headline must survive - a release whose headline legitimately opens
    with a date would otherwise be erased. 16 of ~130 document-derived
    headlines during the 2026 repair pass.

    And the date must actually introduce something. A dateline is followed by
    the company issuing the release: "... - September 11, 2026 - Inomin Mines
    Inc. ...". A headline that merely ENDS in a date is a headline: "Vertex
    Announces Adjournment of AGM to February 13, 2026". Cutting at the date
    there removed the only thing the headline said. Four of 1,728 stored rows.
    """
    h = (headline or "").strip()
    m = _DATELINE_HEAD.search(h)
    if not m:
        return h
    rest = h[m.end():]
    if len(rest.strip(" )]-–—|:,.")) < 3 and not rest.lstrip().startswith(")"):
        return h
    t = h[:m.start()].strip(" -–—|:,(")
    return t if len(t) >= MIN_HEADLINE_AFTER_TRIM else h


def _candidates(text: str) -> list[tuple[int, dt.date]]:
    """Every parseable date in the text, in the order it appears."""
    out = []
    for i, pat in enumerate(_PATTERNS):
        for m in pat.finditer(text):
            try:
                if i == 0:
                    mo, d, y = _MON[m.group(1)[:3].lower()], _digits(m.group(2)), _digits(m.group(3))
                elif i == 1:
                    d, mo, y = _digits(m.group(1)), _MON[m.group(2)[:3].lower()], _digits(m.group(3))
                else:
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                out.append((m.start(), dt.date(y, mo, d)))
            except (KeyError, ValueError):
                continue          # "February 30" and similar
    return sorted(out)


def _plus_one_year(d: dt.date) -> dt.date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:            # 29 February
        return d.replace(year=d.year + 1, day=28)


def release_date(body: str, upload: dt.date) -> tuple[dt.date, str]:
    """(date, provenance) — the date the company issued this release.

    `upload` is the exchange's own date, which bounds the answer: a release
    cannot have been issued after the exchange received it. That bound is what
    makes taking the *first* plausible date safe, and it is why this needs the
    feed date rather than replacing it outright.

    provenance is 'dateline', 'dateline_year_fixed', or 'upload' when the
    document yields nothing — about 6% of releases, which are image-only scans
    or documents whose text layer has no date.
    """
    if body:
        floor = upload - dt.timedelta(days=MAX_BACKDATE_DAYS)
        ceiling = upload + dt.timedelta(days=1)
        for _pos, d in _candidates(body[:WINDOW]):
            if not (floor <= d <= ceiling):
                continue
            back = (upload - d).days
            if YEAR_TYPO_MIN <= back <= YEAR_TYPO_MAX:
                fixed = _plus_one_year(d)
                if fixed <= ceiling and (upload - fixed).days <= YEAR_TYPO_TOLERANCE_DAYS:
                    return fixed, "dateline_year_fixed"
            return d, "dateline"
    return upload, "upload"


SELF_TEST = [
    # (body, upload, expected date, expected provenance) — all real documents.
    ("TERRA BALCANICA INTERCEPTS 607 G/T AG EQ. OVER 3.0 M\n\n"
     "Vancouver, British Columbia – March 17th, 2026 – Terra Balcanica Resources Corp.",
     "2026-04-07", "2026-03-17", "dateline"),

    # Prismo's document says 2025; the release is 2026. Corrected.
    ("Prismo Metals to Advance Hot Breccia Toward Drilling\n"
     "Vancouver, British Columbia, February 26th, 2025 – Prismo Metals Inc.",
     "2026-03-06", "2026-02-26", "dateline_year_fixed"),

    # Peloton, same slip, one day before upload.
    ("PELOTON MINERALS CORPORATION\n NEWS RELEASE\n January 28, 2025   CSE SYMBOL: PMC",
     "2026-01-29", "2026-01-28", "dateline_year_fixed"),

    # Etruscus genuinely filed a year late: 399 days back, 34 days after any
    # "correction", so it must be left exactly where it is.
    ("ETRUSCUS LAUNCHES INAUGURAL DRILL PROGRAM AT ZAPPA PORPHYRY TARGET\n"
     "Vancouver, B.C. – July 10, 2025 – Etruscus Resources Corp.",
     "2026-08-13", "2025-07-10", "dateline"),

    # prompt filer, same day
    ("Vancouver, BC – September 9, 2026 – Example Gold Corp. today reported",
     "2026-09-09", "2026-09-09", "dateline"),

    # a date after the upload is impossible and must be skipped
    ("Closing is expected on or about December 31, 2027.\n"
     "Toronto, Ontario – August 4, 2026 – Example Corp.",
     "2026-08-04", "2026-08-04", "dateline"),

    # ISO form
    ("Press release 2026-02-11 - Example Mining announces", "2026-02-12",
     "2026-02-11", "dateline"),

    # A space before the comma is a PDF text-layer artefact, not a typo.
    # Until 2026-09-14 this shape matched nothing at all, so the release
    # fell back to its upload date and kept the dateline in its headline.
    ("NexGold’s Goldboro Project Selected for Inclusion in the Canada Investment\n"
     "TORONTO, September 14 , 2026 – NexGold Mining Corp. (TSXV: NEXG)",
     "2026-09-14", "2026-09-14", "dateline"),

    # The text layer split the digits of the year. Seen live in the TMX
    # backfill: "Edmonton, AB, May 27, 202 6 - Metalero Mining Corp."
    ("Metalero Announces $3.0M Private Placement\n"
     "Edmonton, AB, May 27, 202 6 – Metalero Mining Corp. (TSXV: MLO)",
     "2026-05-27", "2026-05-27", "dateline"),

    # and of the day
    ("One Step Closer to Cash Flow\n"
     "VANCOUVER, BC, February 1 7, 2026 – Heritage Mining Ltd. (CSE: HML)",
     "2026-02-17", "2026-02-17", "dateline"),

    # nothing readable: fall back to the exchange's date
    ("", "2026-05-05", "2026-05-05", "upload"),
    ("Scanned image, no text layer worth reading.", "2026-05-05", "2026-05-05", "upload"),
]

TRIM_TEST = [
    ("OPTIONS GRANTED July 17th, 2026 – Muskoka - Ontario – Steadright Critical",
     "OPTIONS GRANTED"),
    ("OPTIONS GRANTED July 17 , 2026 – Muskoka - Ontario", "OPTIONS GRANTED"),
    ("Westward Gold Drills 12.0 Metres of 8.06 g Au/t within 27.0 Metres",
     "Westward Gold Drills 12.0 Metres of 8.06 g Au/t within 27.0 Metres"),
    ("Irving Resources Announces Results of AGM",
     "Irving Resources Announces Results of AGM"),
    # a month with no day and year is not a dateline
    ("August Drilling Update at the Example Project",
     "August Drilling Update at the Example Project"),
    # too little would survive, so leave it whole
    ("July 17, 2026 - Muskoka", "July 17, 2026 - Muskoka"),
    # a headline that ENDS in a date is a headline, not a dateline
    ("Vertex Announces Adjournment of AGM to February 13, 2026",
     "Vertex Announces Adjournment of AGM to February 13, 2026"),
    ("FUTURA APPOINTS NEW CHIEF FINANCIAL OFFICER EFFECTIVE MARCH 17, 2026",
     "FUTURA APPOINTS NEW CHIEF FINANCIAL OFFICER EFFECTIVE MARCH 17, 2026"),
    # ... but a date parenthesised at the end is filing furniture
    ("Metals Corp Announces Closing of Private Placement (February 4 2026)",
     "Metals Corp Announces Closing of Private Placement"),
    # a split year is still a dateline
    ("Metalero Announces $3.0M Private Placement Edmonton, AB, May 27, 202 6 – "
     "Metalero Mining Corp. (TSXV: MLO)",
     "Metalero Announces $3.0M Private Placement Edmonton, AB"),
]


def self_test(verbose: bool = True) -> int:
    bad = 0
    for body, up, want_d, want_p in SELF_TEST:
        upload = dt.date.fromisoformat(up)
        got_d, got_p = release_date(body, upload)
        ok = (got_d.isoformat() == want_d) and (got_p == want_p)
        if not ok:
            bad += 1
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  upload={up}  -> {got_d} ({got_p})"
                  f"{'' if ok else f'   WANTED {want_d} ({want_p})'}")
    for raw, want in TRIM_TEST:
        got = trim_at_dateline(raw)
        ok = got == want
        if not ok:
            bad += 1
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  trim {raw[:46]!r} -> {got[:46]!r}"
                  f"{'' if ok else f'   WANTED {want!r}'}")
    total = len(SELF_TEST) + len(TRIM_TEST)
    if verbose:
        print(f"\n{total - bad}/{total} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(self_test())
