#!/usr/bin/env python3
"""The exchange states the ticker. It does not state a headline.

The CSE feed is authoritative about *which company* a release belongs to —
that is the whole reason the exchange path exists. Its `title`, though, is
whatever the issuer typed into a form.

Measured across all 3,856 of our 2026 titles: **464 (12.0%)** carry boilerplate
and **326 (8.5%)** say nothing once it is stripped. Then the first full run of
1,995 was audited afterwards, and **103 of the 1,675 published headlines (6.1%)**
were still weak. Both rounds of evidence are baked into the cases below.

Two rules, in order:

  1. **Strip the boilerplate.** Most are good headlines wearing a prefix:
     `News Release - Krait Commences Trading on Frankfurt Stock Exchange` is
     fine once four words come off the front.
  2. **If what remains is thin, distrust it** — and let the caller take the
     headline out of the PDF instead, which it is fetching anyway.

**What the audit changed.** The first version kept any title containing an
action word, however short. That left `Drilling Results`, `Property update`,
`Financing` and `OPTIONS GRANTED` on the sites while the documents behind them
said `Westward Gold Drills 12.0 Metres of 8.06 g Au/t within 27.0 Metres`,
`Emperor Continues to Define Shallow High-Grade Gold Mineralization` and
`Irving Resources Announces Results of AGM`. For a precious-metals audience the
grade and the interval *are* the headline, so the verb escape hatch is gone and
a short title is always distrusted.

**Erring towards the document is safe by construction.** `headline_for()` in the
runner falls back to the cleaned title whenever the document yields nothing, so
distrusting a title can never lose a release — it can only cost a PDF parse that
is happening anyway. The two errors are not symmetric: the other direction puts
`ESGold Corp. - Press Release (September 10, 2026)` on three public sites, which
is what the first capped run actually did.

These rules live apart from the runner so they can be corrected without touching
a 23 KB file, and because they are the part most likely to need correcting: they
are pattern-matching against free text a human typed into a form.

    python3 backfill_titles.py          # run the self-test
"""
from __future__ import annotations

import re
import sys

# "September 10, 2026", "dated Sept 4, 2026", "(September 1, 2026)". A day
# number AND a year are both required, which is what keeps "August Drilling
# Update" — a real headline — out of the date branch.
_DATEISH = (r"(?:\(?\s*(?:dated\s+)?[A-Za-z]{3,9}\.?\s+\d{1,2},?\s*20\d{2}\s*\)?)")

# The boilerplate, in the shapes issuers actually type. Every optional part here
# was added because a real 2026 title needed it:
#
#   "June 30, 2026 News Release - Super Copper Mobilizes…"  date first
#   "July 21, 2026 HML News Release - Year Round Update"    date AND initials
#   "NLR News Release (August 31, 2026)"                    initials, no dash
#   "MHL Press Release May 19, 2026"                        trailing date
#   "New Release - Commences IP Survey at Three Guardsman"  the issuer's typo
#
# The company branch accepts either a name set off by a dash, or a short
# unpunctuated token like "NLR". It deliberately does NOT accept a long
# unpunctuated run, which is what keeps "Company Issues Press Release Correction
# Regarding Assay Widths" — a real headline — intact.
_TITLE_PREFIX = re.compile(
    r"^\s*"
    r"(?:" + _DATEISH + r"\s*[-–—|:,]?\s*)?"
    r"(?:[\w'&.,()\- ]{2,40}?\s*[-–—|]\s*|[A-Za-z]{2,6}\s+)?"
    r"(?:news|new|press|media)\s*releases?"
    r"(?:\s*[-–—|:,]?\s*" + _DATEISH + r")?"
    r"\s*(?:re\b:?|[-–—|:,])?\s*", re.I)

# What remains once the words and a date are accounted for: nothing.
_TITLE_HOLLOW = re.compile(
    r"^\s*(?:[\w'&.,()\- ]{0,40}?\s*[-–—|]\s*)?"
    r"(?:(?:news|new|press|media)\s*releases?|nr|pr)?\s*"
    r"(?:[-–—|(,]?\s*(?:dated\s+)?[A-Za-z]*\.?\s*\d{0,2},?\s*20\d{2}\s*\)?)?\s*$",
    re.I)

# Below this, a title is a label rather than a headline and the document wins.
# "Results of 2026 AGM" (19) and "Drilling Results" (16) both sit under it; the
# documents behind them give the company name and the numbers.
MIN_TITLE_CHARS = 28


def clean_title(raw: str) -> str:
    """Strip the boilerplate an issuer put in front of its own headline.

    Stripping to an empty string is a valid outcome, not a failed strip — that
    is exactly what `News Release` should become. The first version treated it
    as failure and handed the original straight back, which is why two of the
    three original self-test failures looked like regex bugs and were not.
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
    """True when the title should not be trusted as a headline.

    Named for its original meaning — "says nothing at all" — but widened by the
    audit to include any title too short to carry a company name and a fact.
    There is no verb escape hatch: `Drilling Results` contains an action word
    and is still worse than what its own document says.
    """
    if not t:
        return True
    if _TITLE_HOLLOW.match(t):
        return True
    return len(t) < MIN_TITLE_CHARS


SELF_TEST = [
    # (raw title, expected cleaned, expected distrusted?)
    # Every case is a real 2026 CSE title except the two marked as guards.

    # -- nothing but boilerplate --------------------------------------------
    ("ESGold Corp. - Press Release (September 10, 2026)", "", True),
    ("ESGold Corp - Press Release (September 1, 2026)", "", True),
    ("News Release", "", True),
    ("Press Release", "", True),
    ("AREE | Press Release", "", True),
    ("Press Release - August 19, 2026", "", True),
    ("NLR News Release (August 31, 2026)", "", True),
    ("MHL Press Release May 19, 2026", "", True),
    ("HML PR August 26, 2026", "HML PR August 26, 2026", True),

    # -- boilerplate wrapped round a real headline ---------------------------
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

    # -- too short to be a headline: the document wins -----------------------
    ("Drilling Results", "Drilling Results", True),
    ("Property update", "Property update", True),
    ("Financing", "Financing", True),
    ("OPTIONS GRANTED", "OPTIONS GRANTED", True),
    ("Results of 2026 AGM", "Results of 2026 AGM", True),
    ("Stock Options Granted", "Stock Options Granted", True),
    ("Gold Rock Assay Results", "Gold Rock Assay Results", True),
    ("Beaumont PP Closing", "Beaumont PP Closing", True),

    # -- long enough to stand on their own -----------------------------------
    ("Private Placement - Tranche 2 Closes", "Private Placement - Tranche 2 Closes", False),
    ("TOCVAN PROVIDES 2025 YEAR IN REVIEW", "TOCVAN PROVIDES 2025 YEAR IN REVIEW", False),
    ("TARGA CLOSES FINAL TRANCHE OF NON-BROKERED PRIVATE PLACEMENT",
     "TARGA CLOSES FINAL TRANCHE OF NON-BROKERED PRIVATE PLACEMENT", False),
    ("Riverside Resources Expands British Columbia Mineral Tenures",
     "Riverside Resources Expands British Columbia Mineral Tenures", False),

    # -- guards: these must survive untouched --------------------------------
    # "press release" mid-sentence in a real headline. An earlier version of
    # this case asserted the opposite and was itself the bug.
    ("Company Issues Press Release Correction Regarding Assay Widths",
     "Company Issues Press Release Correction Regarding Assay Widths", False),
    # a month name with no day and no year is not a date
    ("News Release - August Drilling Update at the Example Project",
     "August Drilling Update at the Example Project", False),
]


def self_test(verbose: bool = True) -> int:
    """Returns 0 when every case passes. Cheap, and the only thing standing
    between a bad regex and two thousand headlines on three public sites."""
    bad = 0
    for raw, want_clean, want_hollow in SELF_TEST:
        got = clean_title(raw)
        hollow = title_is_hollow(got)
        ok = (got == want_clean) and (hollow == want_hollow)
        if not ok:
            bad += 1
        if verbose or not ok:
            print(f"  {'ok  ' if ok else 'FAIL'}  {raw[:56]:<56} -> {got[:42]!r:<44} "
                  f"distrust={hollow}"
                  f"{'' if ok else f'   WANTED {want_clean!r} distrust={want_hollow}'}")
    if verbose:
        print(f"\n{len(SELF_TEST) - bad}/{len(SELF_TEST)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(self_test())
