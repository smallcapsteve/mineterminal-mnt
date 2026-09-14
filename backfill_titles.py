#!/usr/bin/env python3
"""The exchange states the ticker. It does not state a headline.

The CSE feed is authoritative about *which company* a release belongs to —
that is the whole reason the exchange path exists. Its `title`, though, is
whatever the issuer typed into a form, and measured across all 3,856 of our
2026 titles:

  * **464 (12.0%)** carry boilerplate: `News Release - `, `Press Release (date)`,
    or are placeholders outright — `News Release`, `Press Release`,
    `HML PR August 26, 2026`, `ESGold Corp. - Press Release (September 10, 2026)`.
  * **326 (8.5%)** say nothing at all once that is stripped.

The first capped backfill run published *"ESGold Corp. - Press Release
(September 10, 2026)"* to three public sites. That is the problem this module
exists to stop.

Two rules, in order:

  1. **Strip the boilerplate.** Most are good headlines wearing a prefix:
     `News Release - Krait Commences Trading on Frankfurt Stock Exchange` is
     fine once four words come off the front.
  2. **If nothing survives, say so** — and let the caller take the headline out
     of the PDF instead, which it is fetching anyway.

**Erring towards "hollow" is deliberate.** Run against all 3,856 titles, 41 are
called hollow despite a raw length over 45 characters, because what survives the
strip is a bare noun phrase — `Final Base Shelf Prospectus`, `Change in
Directors`, `Niobium Mineralization`. Those could be kept. They are not, because
the two errors are not symmetric: a wrong *hollow* costs a PDF parse that is
happening anyway and usually produces a better headline, while a wrong *not
hollow* puts a placeholder on three public sites. `headline_for()` in the runner
falls back to the cleaned title anyway if the document yields nothing.

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

# Optionally a company name and a dash, then the words themselves, then
# optionally a date, then optionally a separator. Everything after the words is
# optional because the boilerplate is often the entire title — the first
# version required a trailing separator and so left "News Release" untouched.
#
# The date may be introduced by its own separator ("Press Release - August 19,
# 2026"), so one is allowed in front of it; without that the date survived the
# strip and became the cleaned title.
#
# Note the leading company-name branch requires a dash or pipe after it. That is
# what stops "Company Issues Press Release Correction Regarding Assay Widths"
# from being eaten: the phrase is mid-sentence in a real headline, and only
# boilerplate that is *set off* by punctuation is boilerplate.
_TITLE_PREFIX = re.compile(
    r"^\s*(?:[\w'&.,()\- ]{2,40}?\s*[-–—|]\s*)?"
    r"(?:news|press|media)\s*releases?"
    r"(?:\s*[-–—|:,]?\s*" + _DATEISH + r")?"
    r"\s*(?:re\b:?|[-–—|:,])?\s*", re.I)

# What remains once the words and a date are accounted for: nothing.
_TITLE_HOLLOW = re.compile(
    r"^\s*(?:[\w'&.,()\- ]{0,40}?\s*[-–—|]\s*)?"
    r"(?:(?:news|press|media)\s*releases?|nr|pr)?\s*"
    r"(?:[-–—|(,]?\s*(?:dated\s+)?[A-Za-z]*\.?\s*\d{0,2},?\s*20\d{2}\s*\)?)?\s*$",
    re.I)

# A headline says what happened. This is the vocabulary of a mining release
# doing that; a short title with none of it is a label, not a headline.
_HAS_VERB = re.compile(
    r"\b(announc\w*|report\w*|clos\w*|complet\w*|commenc\w*|acquir\w*|intersect\w*"
    r"|grant\w*|receiv\w*|provid\w*|files?\b|filed\b|enter\w*|expand\w*|signs?\b"
    r"|signed\b|updat\w*|results?\b|assay\w*|drill\w*|appoint\w*|resign\w*"
    r"|extend\w*|raises?\b|raised\b|start\w*|begin\w*|discover\w*|confirm\w*"
    r"|increas\w*|launch\w*|secur\w*|option\w*|amend\w*|lists?\b|listed\b"
    r"|trad\w*|present\w*|approv\w*|terminat\w*|settl\w*|issu\w*|stak\w*"
    r"|sampl\w*|survey\w*|agreement\w*|placement\w*|financ\w*)", re.I)

# "HML PR August 26, 2026" is 22 characters and survives the hollow regex
# because nothing sets the boilerplate off with punctuation. The length rule is
# what catches it, so this threshold is load-bearing — lowering it to keep
# "Change in Directors" would let that one through.
MIN_TITLE_CHARS = 28


def clean_title(raw: str) -> str:
    """Strip the boilerplate an issuer put in front of its own headline.

    Stripping to an empty string is a valid outcome, not a failed strip — that
    is exactly what `News Release` should become. The first version treated it
    as failure and handed the original straight back, which is why two of the
    three self-test failures looked like regex bugs and were not.
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
    """True when the cleaned title would tell a reader nothing."""
    if not t:
        return True
    if _TITLE_HOLLOW.match(t):
        return True
    return len(t) < MIN_TITLE_CHARS and not _HAS_VERB.search(t)


SELF_TEST = [
    # (raw title, expected cleaned, expected hollow?) — every one of these is a
    # real 2026 title from the CSE feed, except the last two, which are the
    # shapes of headline the stripper must not touch.
    ("ESGold Corp. - Press Release (September 10, 2026)", "", True),
    ("ESGold Corp - Press Release (September 1, 2026)", "", True),
    ("News Release", "", True),
    ("Press Release", "", True),
    ("AREE | Press Release", "", True),
    ("HML PR August 26, 2026", "HML PR August 26, 2026", True),
    ("Press Release - August 19, 2026", "", True),
    ("News Release - Krait Commences Trading on Frankfurt Stock Exchange",
     "Krait Commences Trading on Frankfurt Stock Exchange", False),
    ("News Release dated September 4, 2026 - Announcing Definitive Agreement Signing",
     "Announcing Definitive Agreement Signing", False),
    ("News release re Williams 2026 Exploration Update",
     "Williams 2026 Exploration Update", False),
    ("News Release - 1st Tranche of FT Financing Closes, Increases Offering",
     "1st Tranche of FT Financing Closes, Increases Offering", False),
    ("Stock Options Granted", "Stock Options Granted", False),
    ("Gold Rock Assay Results", "Gold Rock Assay Results", False),
    ("Private Placement - Tranche 2 Closes", "Private Placement - Tranche 2 Closes", False),
    ("Beaumont PP Closing", "Beaumont PP Closing", False),
    ("TARGA CLOSES FINAL TRANCHE OF NON-BROKERED PRIVATE PLACEMENT",
     "TARGA CLOSES FINAL TRANCHE OF NON-BROKERED PRIVATE PLACEMENT", False),
    ("Riverside Resources Expands British Columbia Mineral Tenures",
     "Riverside Resources Expands British Columbia Mineral Tenures", False),
    # Mid-sentence, not boilerplate: must survive untouched. An earlier version
    # of this case asserted the opposite and was itself the bug.
    ("Company Issues Press Release Correction Regarding Assay Widths",
     "Company Issues Press Release Correction Regarding Assay Widths", False),
    # A month name with no day and no year is not a date: this is a headline.
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
                  f"hollow={hollow}"
                  f"{'' if ok else f'   WANTED {want_clean!r} hollow={want_hollow}'}")
    if verbose:
        print(f"\n{len(SELF_TEST) - bad}/{len(SELF_TEST)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(self_test())
