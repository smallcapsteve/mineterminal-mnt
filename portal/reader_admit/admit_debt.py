"""Outside-tag admission rule for the Debt & Credit Facilities reader (debt).

admit(headline, text, categories, out) -> (bool, short_reason)

A release that lacks the "Debt & Credit Facilities" tag is admitted only when the debt the reader found is plainly the
release's own news:
  1. the headline names a debt instrument or debt event, or the headline is a financing / investment announcement
     whose opening paragraph names a debt instrument;
  2. the reader's rows agree with the wording of the release: the instrument the reader chose is named in the release,
     a headline repayment has a repaid/converted row, a lender row has lending wording, an interest_paid row is not a
     missed or deferred payment, and no instrument is read twice;
  3. none of the known look-alikes applies (equity draw-down "facilities", shares for trade payables with no loan,
     debt mandates and advisors, the company lending to or buying the debt of another company).
Standard library only; no names, tickers or ids; categories are not needed. About 0.5 ms per release.
"""
import re

_F = re.I

# --- 1a. Headline names a debt instrument or a debt event --------------------------------------------------------
# "Closes Debenture Financing", "Extends Convertible Debenture", "Senior Lender", "Bridge Loan", "Corporate Bond",
# "Debt Settlement", "Reduces Debt", "Interest Payment", "Conversion of ... Note", "Debt Extension Proposal".
HEAD_DEBT = re.compile(
    r"\b(debentures?|convertible|loans?|lenders?|bonds?|notes?\b(?!worthy)|credit (facility|agreement)|"
    r"debt|indebtedness|bridge financing|interest payments?|interest debt|prepayment|gold loan)\b", _F)

# --- 1b. Financing-type headline (the debt is in the opening paragraph instead of the headline) ------------------
# "Closes Private Placement", "Announces $15.3 Million Financing", "Strategic Investment", "Raises Funds",
# "Closes Final Tranche", "Financing Package", "Financing Offer".
HEAD_FIN = re.compile(
    r"\b(private placements?|financings?|investment|raises? (funds|\$)|tranche|offering|funding)\b", _F)
# Equity-only financing headlines: a debt instrument in their lead is a concurrent or earlier deal, not this news.
HEAD_EQUITY = re.compile(r"subscription receipts?|flow[- ]through|rights offering|bought deal|common shares|"
                         r"equity (offering|financing|facility)|warrant exercises?", _F)

# Debt instrument words for the opening paragraph (financing-type headlines only).
LEAD_DEBT = re.compile(
    r"\b(convertible (debentures?|notes?|loans?|promissory notes?|securities)|debentures?|bridge loans?|"
    r"term loans?|loan (facility|agreement|offers?)|credit facility|senior (secured )?notes|bonds|"
    r"promissory notes?|(debt|loan|project) (financing )?facility|debt financing)\b", _F)
LEAD_CHARS = 700   # about the opening paragraph: dateline + the sentence that says what was announced

# --- 2. The reader's instrument must be named in the release -----------------------------------------------------
INSTR_WORDS = {
    "convertible_debenture": r"debenture",
    "convertible_note": r"convertible\b.{0,30}\b(notes?|loans?|securities)\b",
    "loan": r"\bloan(s|ed)?\b|promissory|bridge|borrow|\blenders?\b|\badvances?\b|indebtedness",
    "credit_facility": r"facility",
    "notes": r"\bnotes\b|\bbonds?\b|debentures",
    "gold_loan": r"gold loan|loan",
    "prepayment": r"prepay|pre-pay|forward",
}

# --- 3. Look-alikes --------------------------------------------------------------------------------------------
# Equity draw-down / equity line "facilities" (units issued on each draw): not debt.
EQUITY_FACILITY = re.compile(r"equity (financing |draw-?down )?(financing )?facility|draw-?down equity|"
                             r"equity (private placement )?tranches|equity line", _F)
# Shares-for-debt releases: only a named loan/note/debenture is a row; trade payables, fees and salaries are not.
SETTLEMENT_HEAD = re.compile(r"shares? for debt|debt settlement|settle(ment of)? (outstanding )?debt|"
                             r"debt conversions?|in settlement of debt", _F)
LOAN_NAMED = re.compile(r"\bloans?\b|promissory|debentures?|convertible notes?|\blenders?\b|\bbonds?\b|"
                        r"credit facility|interest (owing|owed|payable|indebtedness|accrued)|accrued interest", _F)
# Interest that was NOT paid (deferred, in default, unable to pay) is not an interest_paid row.
INTEREST_UNPAID = re.compile(r"(not|unable to|did not|failed to|will not) (be )?(pay|paid|make)|deferr?al|"
                             r"\bin default\b|remains? (outstanding|unpaid)", _F)
# The company lends to, or buys the loans of, another company (rule DL). The reader stores these as borrower rows,
# so a release worded this way is left out; a lender row without such wording is a misread (the company borrowed).
_NOT_A_PARTY = (r"(?!(fund|finance|pay|support|advance|repay|be|cover|help|complete|purchase|acquire|settle|"
                r"provide|continue|develop|build|restart|retire|refinance|the company|\$|us\$|c\$|\d)\b)")
COMPANY_LENDS = re.compile(
    r"\b(provided|advanced|made|extended|granted|lent)( a| an)?( [\w$.,-]+){0,3} (bridge |secured |unsecured |term )?"
    r"(loans?|promissory note) to " + _NOT_A_PARTY +
    r"|loan purchase agreement|acquire .{0,80}loan facility|receipt of .{0,30}repayment|"
    r"receives? .{0,40}(loan|debt) repayment", _F)
HEAD_LOAN_TO = re.compile(r"\bloan to " + _NOT_A_PARTY, _F)
# A mandate or advisor to arrange debt, or the start of a debt process, is no row (rule DM).
HEAD_MANDATE = re.compile(r"\bmandate|\badvis(or|ory)\b|\barranger\b|initiat\w* .{0,40}(debt|financing)", _F)
# Headline announces a repayment / reduction: the reader must have a repaid, converted or terminated row, otherwise
# it read a side event (e.g. only the interest paid alongside the repayment).
HEAD_REPAY = re.compile(r"reduces? (its )?debt|debt reduction|\brepa(y|id|yment|ys)\b|debt[- ]free|"
                        r"eliminat\w* .{0,30}debt|pays? (off|down)|\bredeem|\bredemption", _F)


def _lead(headline, text, n=1500):
    """Opening of the release: the body up to n characters after the headline, or the first n characters."""
    t = re.sub(r"\s+", " ", text or "")
    h = re.sub(r"\s+", " ", headline or "")[:60]
    i = t.find(h) if h else -1
    start = i + len(h) if i >= 0 else 0
    return t[start:start + n] if i >= 0 else t[:n]


def admit(headline, text, categories, out):
    rows = (out or {}).get("rows") or []
    if not rows:
        return False, "no rows"
    h = re.sub(r"\s+", " ", headline or "")
    body = re.sub(r"\s+", " ", text or "")
    lead = _lead(h, body)

    # Look-alike: equity draw-down facility (Financings covers it).
    if EQUITY_FACILITY.search(h) or EQUITY_FACILITY.search(lead):
        return False, "equity facility"

    # Path into the page.
    if HEAD_DEBT.search(h):
        path = "headline"
    elif HEAD_FIN.search(h) and not HEAD_EQUITY.search(h) and LEAD_DEBT.search(lead[:LEAD_CHARS]):
        path = "fin+lead"
    else:
        return False, "debt not the headline news"

    # Shares for debt: needs a named loan, note or debenture (or interest on one) in the release.
    if SETTLEMENT_HEAD.search(h) and not LOAN_NAMED.search(body):
        return False, "payables settlement"

    # Mandates and advisors (rule DM).
    if HEAD_MANDATE.search(h):
        return False, "mandate/advisor"

    # The company as lender (rule DL): the reader's side must agree with the wording.
    lends = bool(COMPANY_LENDS.search(h) or COMPANY_LENDS.search(lead) or HEAD_LOAN_TO.search(h))
    sides = set((r.get("side") or "borrower") for r in rows)
    if lends and "borrower" in sides:
        return False, "company lends"
    if "lender" in sides and not lends:
        return False, "lender row, no lending"

    # Headline repayment the reader did not read as one.
    if HEAD_REPAY.search(h) and not any(r.get("stage") in ("repaid", "converted", "terminated") for r in rows):
        return False, "repayment not read"

    # One instrument read twice (same stage and same lender or amount under two instrument names).
    for a in range(len(rows)):
        for b in range(a + 1, len(rows)):
            ra, rb = rows[a], rows[b]
            if ra.get("stage") == rb.get("stage") and (
                    (ra.get("lender") and ra.get("lender") == rb.get("lender")) or
                    (ra.get("principal") and ra.get("principal") == rb.get("principal"))):
                return False, "duplicate rows"

    for r in rows:
        ins = r.get("instrument")
        pat = INSTR_WORDS.get(ins)
        if pat and not re.search(pat, body, _F):
            return False, "instrument not named: %s" % ins
        if r.get("stage") == "interest_paid" and INTEREST_UNPAID.search(lead):
            return False, "interest not paid"

    return True, path
