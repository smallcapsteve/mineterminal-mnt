"""Outside-tag admission rule for the economics reader (Economic Studies), 2026-09-30.

Called for a release that does NOT carry the Economic Studies tag but where the reader found rows.
Returns (admit, short_reason). Standard library only, deterministic, no I/O.

Why these rules: on the 100 labelled outside-tag releases, almost every wrong find is one of
  * figures that are not in the text at all: the reader fills in a project's well-known NPV/IRR from
    an About paragraph that is not in the body it was given, or from a URL slug
    ("...-us-501m-after-tax-npv5-21-irr-48-month-payback/"), on financings, option grants, AGM
    notices, drill results, conference notices (about 45 of the 51 wrong finds);
  * figures that are real but belong to no named study (a reserve update, a generic "technical
    report", deal terms, a new officer's career bio) -- the label guide files these as no row;
  * a royalty/streaming company recapping an operator's study (whose study is it?).
Own-project recaps that ARE stated in the text are labelled as (background) rows, so they are
admitted: the reader's `context` already marks them background and the page shows them as such.
"""
import re

# --- text clean-up -----------------------------------------------------------------------------
# URLs and hyphenated slugs. Kind of release: any release linking to an earlier study release,
# whose URL slug spells the old figures ("us-501m-after-tax-npv5-21-irr"). A slug is not a statement.
_URL = re.compile(r'(?:https?://|www\.)\S+|\S*[a-z0-9](?:-[a-z0-9]+){4,}\S*', re.I)

_NUM = r'(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)'
# money with a unit: "$454 million", "C$1.4B", "US$ 2.0 billion". A bare "m"/"b" counts only after a
# currency sign, because drill and exploration releases are full of metres ("122m").
_MONEY_UNIT = re.compile(r'(?:([$€£])\s*)?' + _NUM + r'\s*(billion|bn\b|b\b|million|mm\b|m\b|mln\b)', re.I)
_MULT = {'billion': 1e9, 'bn': 1e9, 'b': 1e9, 'million': 1e6, 'mm': 1e6, 'mln': 1e6, 'm': 1e6}
_BARE = re.compile(r'(?<![\w.,])' + _NUM + r'(?![\d])')
_NPV_WORD = re.compile(r'NPV|net present value', re.I)
_IRR_WORD = re.compile(r'IRR|internal rate of return', re.I)

# the release's own company, as defined in its lead: '... Royalties Ltd (the "Corporation" ...'
_SELF_DEF = re.compile(r'\((?:the\s+)?["“”]?(?:Company|Corporation|Issuer)["“”]?', re.I)
_ROYALTY_NAME = re.compile(r'royalt|stream', re.I)
_BASE = re.compile(r'\bbase\b', re.I)


def _f(s):
    return float(s.replace(',', ''))


def _close(a, b, tol=0.02):  # the checker's own 2% money tolerance
    return abs(a - b) <= tol * max(abs(a), abs(b))


def _money_values(t):
    vals = []
    for m in _MONEY_UNIT.finditer(t):
        u = m.group(3).lower()
        if u in ('m', 'b') and not m.group(1):
            continue
        vals.append(_f(m.group(2)) * _MULT[u])
    return vals


def _near(t, word_re, win):
    for m in word_re.finditer(t):
        yield t[max(0, m.start() - win): m.end() + win]


def _money_grounded(v, t, allvals):
    if any(_close(v, x) for x in allvals):
        return True
    # study tables print bare figures under an "NPV (US$M)" heading
    for w in _near(t, _NPV_WORD, 250):
        for m in _BARE.finditer(w):
            x = _f(m.group(1))
            if x and (_close(v, x * 1e6) or _close(v, x * 1e9)):
                return True
    return False


def _irr_grounded(v, t):
    for w in _near(t, _IRR_WORD, 200):
        for m in _BARE.finditer(w):
            if abs(_f(m.group(1)) - v) <= 0.051:
                return True
    return False


def _row_grounded(r, t, allvals):
    """A row is grounded when its NPV (pre- or after-tax) or its IRR is actually written in the text."""
    for k in ('npv_after_tax', 'npv_pre_tax'):
        if r.get(k) and _money_grounded(r[k], t, allvals):
            return True
    for k in ('irr_after_tax_pct', 'irr_pre_tax_pct'):
        if r.get(k) is not None and _irr_grounded(r[k], t):
            return True
    return False


def _royalty_issuer(t):
    """The lead defines the issuer as a royalty/streaming company."""
    m = _SELF_DEF.search(t[:1500])
    return bool(m and _ROYALTY_NAME.search(t[max(0, m.start() - 90):m.start()]))


def admit(headline, text, categories, out):
    rows = (out or {}).get('rows') or []
    if not rows:
        return False, 'no rows'
    t = _URL.sub(' ', text or '')

    # Rule 1 -- every row's figures must be in the text. For: financings, option grants, AGM and
    # conference notices, drill results and appointments where the reader supplies a project's NPV/IRR
    # that the body never states (About paragraph not in the body, URL slug, memory of the project).
    allvals = _money_values(t)
    if not all(_row_grounded(r, t, allvals) for r in rows):
        return False, 'figures not in text'

    # Rule 2 -- every row must belong to a named study (PEA / PFS / FS). For: quarterly results
    # quoting a reserve update, half-year reports citing a generic technical report, deal terms,
    # an officer's bio mentioning another company's project. The reader leaves study_type empty
    # exactly when the text names no study, and the label guide files those as no row.
    if not all(r.get('study_type') for r in rows):
        return False, 'no named study'

    # Rule 3 -- whose study is it? For: royalty and streaming companies' portfolio updates, which
    # recap operators' studies on assets they only hold a royalty or stream on.
    if _royalty_issuer(t):
        return False, 'royalty issuer quoting operator study'

    # Rule 4 -- one base case per release. For: study recaps and study announcements where the
    # reader splits one scenario into two rows both called "base" (a sensitivity line or the other
    # tax basis turned into its own row). Two base rows on the same real/nominal basis means the row
    # list is wrong, so the release is not admitted rather than showing a duplicate.
    bases = [r.get('basis') for r in rows if _BASE.search(r.get('scenario') or '')]
    if len(bases) != len(set(bases)):
        return False, 'duplicate base-case rows'

    return True, 'grounded study figures'
