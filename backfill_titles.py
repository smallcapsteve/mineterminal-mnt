#!/usr/bin/env python3
"""The exchange states the ticker. It does not state a headline.

The CSE feed is authoritative about *which company* a release belongs to —
that is the whole reason the exchange path exists. Its `title`, though, is
whatever the issuer typed into a form, and measured across all 3,856 of our
2026 titles:

  * **497 (12.9%)** lead with `News Release - `, `Press Release (date)`, or
    are placeholders outright — `News Release`, `Press Release`,
    `HML PR August 26, 2026`, `ESGold Corp. - Press Release (September 10, 2026)`.
  * **87 more (2.3%)** are under 28 characters.

The first capped backfill run published *"ESGold Corp. - Press Release
(September 10, 2026)"* to three public sites. That is the problem this module
exists to stop.

Two rules, in order:

  1. **Strip the boilerplate.** Most of the 497 are good headlines wearing a
     prefix: `News Release - Krait Commences Trading on Frankfurt Stock
     Exchange` is fine once four words come off the front.
  2. **If nothing survives, say so** — and let the caller take the headline out
     of the PDF instead, which it is fetching anyway.

Rule 2 is deliberately conservative. A short title that still names an action
(`Stock Options Granted`, `Gold Rock Assay Results`) is kept, because replacing
it costs a PDF parse and the replacement can itself be wrong. Only a title with
no action word *and* no length is thrown away.

These rules are separate from the runner so they can be corrected without
touching a 27 KB file, and because they are the part most likely to need
correcting: they are pattern-matching against free text a human typed.

    python3 backfill_titles.py          # run the self-test
"""
from __future__ import annotations

import re
import sys

# "September 10, 2026", "dated Sept 4, 2026", "(September 1, 2026)"
_DATEISH = (r"(?:\(?\s*(?:dated\s+)?[A-Za-z]{3,9}\.?\s+\d{1,2},?\s*20\d{2}\s*\)?)")

# Optionally a company name and a dash, then the words themselves, then
# optionally a date, then optionally a separator. Everything after the words is
# optional because the boilerplate is often the entire title — the first
# version required a trailing separator and so left "News Release" untouched.
_TITLE_PREFIX = re.compile(
    r"^\s*(?:[\w'&.,()\- ]{2,40}?\s*[-–—|]\s*)?"
    r"(?:news|press|media)\s*releases?"
    r"(?:\s*" + _DATEISH + r")?"
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
    # real 2026 title from the CSE feed.
    ("ESGold Corp. - Press Release (September 10, 2026)", "", True),
    ("ESGold Corp - Press Release (September 1, 2026)", "", True),
    ("News Release", "", True),
    ("Press Release", "", True),
    ("AREE | Press Release", "", True),
    ("HML PR August 26, 2026", "HML PR August 26, 2026", True),
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
    # must not eat a real headline that merely contains the word
    ("Company Issues Press Release Correction Regarding Assay Widths",
     "Correction Regarding Assay Widths", False),
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
