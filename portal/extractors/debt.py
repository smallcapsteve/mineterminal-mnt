"""Debt & Credit Facilities reader, facts-store version (DEBT_V1, 2026-09-24).

The source of the Debt & Credit page once it passes the accuracy gate. Written against the 50-item set Justin
confirmed on 2026-09-24 (42 items with rows, 48 rows; claude/MNT_DEBT_SET_LABELS_CONFIRMED_2026-09-24.json) and the
label guide claude/MNT_DEBT_LABEL_GUIDE_2026-09-24.md.

Justin's rules (2026-09-24):

  1. ONE ROW PER DEBT INSTRUMENT a release reports: convertible debentures and notes, loans (term, bridge,
     related-party, government), credit facilities, notes and bonds, gold loans and metal prepayments. Streams and
     royalties are not debt (Royalties & Streams has them).
  2. THE ROW'S STAGE as of the release: proposed (announced offering, term sheet, commitment or interest letter),
     signed (binding agreement or pricing, not yet funded), closed (issued, funded, a tranche closed), drawn (a later
     drawdown), amended (extended, increased, repriced, restructured), converted, repaid (repaid, redeemed, bought
     back or settled, including a binding settlement not yet closed), terminated.
  3. SIDE: the issuer as borrower, or as lender / holder (rule DL as Justin decided: debt the company lends or buys is
     a row, side "lender").
  4. TERMS when stated: principal and currency, running total of tranches, interest rate (floating rates as text),
     maturity or term, lender, related party, security, conversion price (blank when a conversion unit holds several
     shares), warrants, the project it funds.
  5. NOT ROWS: debt restated as background or in an About section, balance-sheet lines in results, interest paid in
     shares, a scheduled conversion-price step-up, an advisor mandated to arrange debt, deferred purchase payments,
     another company's debt.

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per row (ordinal 0..n-1)
to_prediction(records) -> dict|None    what the accuracy judge compares

Self-tests: python3 -m portal.extractors.debt

1.0.2 (2026-09-25), from the first week on the page (Justin: "Fix these issues you found"):
  - a company that agreed to provide another company with a loan is the lender (Franco-Nevada / G Mining);
  - "(in U.S. dollars unless otherwise noted)" sets the release currency;
  - "previously issued" is not a closing; "has amended the terms of its ..." is an amendment;
  - a tender offer launched or extended is not yet a repayment (results and settlement are);
  - a new notes offering does not take the rate and maturity of the existing notes it refinances;
  - a redemption is sized by the notes redeemed, not the offering that paid for them;
  - a partial repayment is marked (purpose "Partial repayment") so the page does not end the debt there;
  - a covenant waiver or forbearance is not a row (label guide); a results release's unsized "repayment of
    debt" is not a row;
  - "non-convertible" is not convertible; a letter of interest or project letter received is proposed;
  - a non-convertible debenture from one named lender is a loan;
  - a stage date equal to the maturity, or far from the release date, is dropped;
  - "Executive Chairman <name>" in a greeting is not a related-party lender.

1.0.4 (2026-09-30), ACC150 quick fix (stage was the weakest key field, ~68%):
  - stage: a future, an option or a term is not an event ("will be issued", "is expected to close", "has the right
    to repay", "may convert", "proceeds will be used to repay"); a commitment letter, credit approval, term sheet,
    letter of interest or lender approval is proposed until a definitive agreement or funding; money received or
    advanced under an existing facility is drawn, a first draw closes it; "Receipt of" a loan closes it; shares for
    debt, retirements, debt reductions and notes bought back in tender offers are repaid (cancelled after a tender:
    repaid); a non-convertible debt "converted" into shares is repaid, a convertible the lead says was converted is
    converted; forgiveness is terminated; a deferral is an amendment; the noun after the headline's debt names the
    event ("Receives Debt Extension"); "Signs Definitive Agreements" is signed; an open offer to buy another
    issuer's debt is proposed; extending an offering's closing date is not an amendment;
  - interest (rule DI): settling or paying the interest owed (in shares or cash) is interest_paid, not repaid or
    closed; interest that was deferred, missed or not paid is no row; a headline that repays or converts the debt
    and pays interest on it gives both rows;
  - side (rule DL): the company is the lender when it lent, bought another's loan, makes a facility available or is
    repaid a loan it made ("Receipt of Loan Repayment", "loan purchase agreement", "in favour of", "Loan to X");
    "advanced to the Company" no longer makes it the lender;
  - instrument: "convertible securities / debt units" take the release's own word (debenture or note); a loan the
    lender may convert is a convertible loan (convertible_note); "the Convertible Loan ... the loan" is one row;
    a headline "Promissory Note" the body calls a convertible note, and a headline "Debt Facility" the lead calls a
    pre-payment facility, are those; a facility the headline refinances with a notes offering is not a second row;
  - amounts: an increase or upsizing gives the new size ("from US$14M to US$16M"); a first draw its amount; a unit's
    face value, one insider's share or another figure's per-share price do not size the debt; "U.S.$", "Cdn$",
    sterling and euro amounts are read; "$17,500,000 Million" is not multiplied again;
  - look-alikes with no row: equity draw-down "financing facilities" (units on each draw), shares for fees and
    payables with loans only lumped in, 'debt settlement' or 'convertible securities' only in boilerplate, an
    equity-only headline whose debt is background, a project named "Revolver", a year-in-review recap;
  - terms: the rate on overdue amounts, a standby fee or a spread over SOFR is not the rate; an amendment's new rate
    and latest maturity; "(un)secured" describing another instrument is ignored; a conversion price with a floor
    or a discount is a formula; the lender of the debt being repaid, or an offtake buyer, is not this debt's lender;
    an agency's initials carry its name ("U.S. Department of Energy (DOE)").
  - answer-key gate (same version): "contemplated" says nothing about the debt when it describes the takeover or
    transaction the loan supports; money the company "has provided" moved (closed); "concurrent with the closing of
    the" new facility is its closing whatever old facility precedes it; a credit facility retired with nothing said
    to be repaid is terminated; a tranche closed beside an upsize of the whole offering is the tranche (rule DP);
    "(un)secured" inside the instrument's own name ("convertible senior unsecured notes") describes it.
  - FIX3 (same version, 2026-10-01), from full-text releases the 1.0.4 file dropped although the live rows were right:
    a headline naming a lender's commitment or support letter, or "the Debt Owing" to insiders, makes the debt the
    news (not "debt only in passing"); "the secured <Name> facility" is a credit facility; deferring a debt or
    indebtedness is amended; "proceeds were utilized to repay debt as follows: - A - B" repays every listed item and
    each takes its own amount; "has agreed to borrow" under a headline loan is signed (and sizes it); satisfied
    conditions precedent are signed; "well advanced" and "a step toward a fully funded ..." are not fundings; a
    "prepayment and offtake agreement" is a prepayment; the equity draw-down look-alike needs the debt itself to be a
    facility without interest terms; shares to debenture holders "representing the $X in interest" are interest_paid
    on the named debenture (not shares for unnamed debt); a placement's amount or a bracketed currency equivalent
    does not size the debt.

1.0.5 (2026-10-04), FIX5 (Justin's item: lender, stage, maturity), each change measured alone on the ACC150c dev half:
  - lender: the name the sentence sets up as the lender: 'X (the "Lender")' (the release's defined term, wherever it
    is defined), 'from its largest shareholder, X', 'with its existing lenders, X', 'from two of its directors, X and
    Y', 'with Dr. X', 'debentures issued to X', 'X will lend / has advanced'; a title-case headline's capitals are not
    names; a full legal name the short form missed ('X Global Resources Fund IV LP', 'X Mining Company, Inc.',
    'X & Sons LLC', 'X (Hong Kong) Corporation Limited', '1234567 B.C. Ltd.');
  - maturity: '<date>, being the maturity date' / '<date> (the "Maturity Date")', 'the earlier of <event> and
    <date>', 'Notes due April, 2023', '<loan> ... is due on <date>', 'March 5 , 20 20', an extension 'from <date> to
    <date>' read past 'Inc.'; a warrant's exercise period is not the debt's term;
  - stage: 'Entry into' a facility is signed; 'The closing of the Loan is subject to ...' is not a closing; the month
    'May' is not a modal (an interest settlement dated in May is interest_paid); an offering re-priced or extended
    before closing stays proposed (rule DU); a headline that only announces a placement whose lead says it has closed
    is closed;
  - side (rule DL): the company 'has agreed to advance to X', 'advanced ... to X', 'has provided a ... financing ... to
    a private company', 'will hold a ... loan' is the lender; the borrower 'a private royalty company ("PrivCo")' or
    the 'X' of 'a loan ... with X' it holds.
"""
from __future__ import annotations

import re

from portal import facts as F
from portal import fingerprint as FP
from portal import project_names as PN
from portal.extractors import technical as T

NAME = "debt"
VERSION = "1.0.5"  # 2026-09-30: ACC150 quick fix: stage, company as lender, instrument words, amounts, look-alikes;
#                     2026-10-01: lender-letter, 'debt owing' and secured-facility headlines, repayment lists, borrow
#                     cues, equity look-alike and interest-share guards; full-text losses fixed;
#                     2026-10-04 FIX5: lender named by role or defined term and full legal names; maturity date
#                     wordings; warrant periods are not the term; stage wordings; the company as lender (rule DL)
#                     rev b: a legal ending alone ("Limited") is no lender name
KIND = "debt_instrument"
TAG = "Debt & Credit Facilities"
TEXT_CAP = 40000

TXT_FIELDS = ("instrument", "stage", "side", "currency", "rate_text", "maturity", "lender", "borrower",
              "conversion_text", "project", "purpose", "date")
NUM_FIELDS = ("principal", "principal_total", "rate_pct", "term_months", "related_party", "secured",
              "conversion_price", "warrants", "warrant_strike")
INSTRUMENTS = ("convertible_debenture", "convertible_note", "loan", "credit_facility", "notes", "gold_loan", "prepayment",
               "other")
STAGES = ("proposed", "signed", "closed", "drawn", "amended", "converted", "repaid", "terminated", "interest_paid")
STAGE_RANK = {"interest_paid": 0, "proposed": 1, "signed": 2, "closed": 3, "drawn": 4, "amended": 4, "converted": 5, "repaid": 5,
              "terminated": 5}

# ------------------------------------------------------------------ text
_FLS = re.compile(r"(?i)(?:^|\s)(?:cautionary\s+(?:note|statement|language)s?\b|forward[\s\-]+looking\s+(?:statements?|information)"
                  r"\s*(?:$|[A-Z:])|notice\s+regarding\s+forward|neither\s+(?:the\s+)?(?:tsx|canadian\s+securities|cse)\b|"
                  r"the\s+cse\s+(?:has\s+not|and\s+information)|no\s+stock\s+exchange|to\s+view\s+the\s+source|"
                  r"this\s+(?:news\s+)?release\s+does\s+not\s+constitute\s+an\s+offer)")
_ABOUT_CO = re.compile(r"(?:^|\s)About\s+(?:the\s+Company\b|Us\b|(?!the\s+(?:\w+\s+){0,4}?(?:Loan|Facility|Debentures?|Notes?|"
                       r"Offering|Agreement|Transaction|Financing)\b)[A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5}\s*(?:[:.]|\(|\s(?=[A-Z][a-z]+\s)))")


_UNITS_W = {w: n for n, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                           "fifteen sixteen seventeen eighteen nineteen".split())}
_TENS_W = {w: 10 * n for n, w in enumerate("x x twenty thirty forty fifty sixty seventy eighty ninety".split()) if n >= 2}
_CENTS = re.compile(r"(?i)(?<![\w$.])((?:(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[\s-](?:one|two|three|four|five|"
                    r"six|seven|eight|nine))?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
                    r"fifteen|sixteen|seventeen|eighteen|nineteen|[1-9]\d?))\s+cents\b")


def _cents(t):
    t = t.lower()
    if t.isdigit():
        return int(t)
    n = 0
    for w in re.split(r"[\s-]+", t):
        n += _TENS_W.get(w, _UNITS_W.get(w, 0))
    return n


def _prepare(headline, body):
    b = T._norm((body or "")[:TEXT_CAP])
    b = re.sub(r"https?://\S+", " ", b)
    b = T._flat(b)
    b = re.sub(r"(\$\s?\d{1,2}) (\d{1,2},\d{3})\b", r"\1\2", b)          # "$6 0,000" (a PDF gap inside a number)
    b = re.sub(r"(\$\s?\d{1,3},(\d{1,2})) ((\d{1,2}),\d{3})\b",
               lambda m: m.group(1) + m.group(3) if len(m.group(2)) + len(m.group(4)) == 3 else m.group(0), b)  # "$1,1 18,000"
    b = re.sub(r"(\$\s?\d+) \.(\d)", r"\1.\2", b)                       # "$3 .2895"
    b = re.sub(r"\bU\.\s?S\.\s?\$", "US$", b)                                 # 1.0.4: "U.S.$400 million"
    b = re.sub(r"\b(?:Cdn|CDN|Can|CAN)\s?\$", "C$", b)                         # 1.0.4: "Cdn$10,430,000"
    b = _CENTS.sub(lambda m: "$0.%02d" % _cents(m.group(1)), b)             # "a conversion price of eleven cents"
    b = re.sub(r"(?i)(\bdue\s+20) (\d\d)\b", r"\1\2", b)                  # "notes due 20 30"
    b = re.sub(r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\s*,\s*)"
               r"(20) (\d\d)\b", r"\1\2\3", b)                  # FIX5: "March 5 , 20 20" (a PDF gap in the year)
    b = re.sub(r"(?i)\b(one|two|three|four|five|six|seven|eight|nine|ten|twelve|eighteen|\d{1,2}) -(months?|years?)\b",
               r"\1-\2", b)                                                 # "six -month"
    fls = _FLS.search(b, int(len(b) * 0.30))
    if fls:
        b = b[:fls.start()]
    about = None
    for m in _ABOUT_CO.finditer(b, 600):
        about = m.start()
        break
    h = T._flat(T._norm(headline or ""))
    h = re.sub(r"^\s*TSX\s+Venture\s+Exchange\s*:\s*[A-Z]{2,5}\s*\.?\s*V\s+", "", h)
    return h, b, about


_LEGAL_END = re.compile(r"\b(?:Corp|Inc|Ltd|Co|Pty|S\.A|L\.L\.C|U\.S|No)\.$")


_SPLIT = re.compile(r"(?<![\s(][A-Z]\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\bSt\.)(?<!\bMt\.)(?<!\bNo\.)(?<!\bvs\.)"
                    r"(?<=[.;!?])\s+(?=[A-Z\u201c\"\u2022\u25aa(])|\s+[\u2022\u25aa\u25cf]\s+")


def _sentences(b):
    raw, parts = [], []
    for p in _SPLIT.split(b):
        p = p.strip()
        if not p:
            continue
        if raw and len(p) <= 12:
            raw[-1] += " " + p
        else:
            raw.append(p)
    for s in raw:
        if parts and (s[:1] == "(" and _LEGAL_END.search(parts[-1]) or re.match(r"^[a-z0-9$]", s) or
                      re.match(r"(?:Ltd|Inc|Corp|Limited|LLC)\b", s) and re.search(r"\b(?:B\.C|U\.S|Q\.C|N\.W\.T)\.$", parts[-1])):
            parts[-1] += " " + s
        else:
            parts.append(s)
    return parts


# ------------------------------------------------------------------ instruments
_CONV = r"(?<!non-)(?<!non- )(?<!non\s)(?:convertible|exchangeable)"
_I_CONVDEB = re.compile(r"(?i)\b" + _CONV + r"\s+(?:(?:senior|secured|unsecured|subordinated|promissory|non-interest[\s-]bearing|"
                        r"interest[\s-]bearing|gold-linked|redeemable|series\s+\w+|[\d.]+\s*%)\s+){0,3}debentures?\b|"
                        r"\bdebentures?\s+(?:that\s+are\s+|which\s+are\s+)?convertible\b|\bconvertible\s+debenture\s+units?\b|"
                        r"\b(?:Series\s+20\d\d\s+)?(?:replacement\s+)?(?:convertible\s+)?debentures?\s+(?=\([^)]{0,40}convertible)")
_I_CONVNOTE = re.compile(r"(?i)\b" + _CONV + r"\s+(?:(?:senior|secured|unsecured|subordinated|promissory|gold-linked|revolving|"
                         r"fixed[\s-]term|term|bridge|"
                         r"non-interest[\s-]bearing|interest[\s-]bearing|[\d.]+\s*%)\s+){0,3}(?:notes?|loans?|bonds?|"
                         r"credit\s+facilit(?:y|ies)|term\s+loans?|loan\s+facilit(?:y|ies)|promissory\s+notes?)\b")
_I_GOLD = re.compile(r"(?i)\b(?:gold|silver|metal|precious\s+metals?)\s+(?:loan|streaming\s+loan)s?\b(?:\s+facilit(?:y|ies))?|"
                     r"\bgold[\s-]linked\s+loan\b")
_I_PREPAY = re.compile(r"(?i)\b(?:(?:gold|silver|copper|concentrate|offtake|metal|zinc)\s+)?pre-?payment\s+(?:and\s+(?:[\w-]+\s+){0,2}?)?"
                       r"(?:facilit(?:y|ies)|agreements?|financing|arrangements?)\b|\bprepay(?:ment)?\s+facilit(?:y|ies)\b|\bpre-?paid\s+forward\b")
_I_CREDIT = re.compile(r"(?i)\b(?:revolving|standby|stand-by|senior\s+secured|secured|corporate|syndicated|bank|delayed[\s-]draw|"
                       r"(?:US|C|CA)?\$?[\d.,]+\s*(?:million|M|billion|B)?|term|senior|acquisition|construction|working\s+capital|"
                       r"reserve[\s-]based|non-revolving)?\s*(?:credit\s+facilit(?:y|ies)|credit\s+agreement|revolver|"
                       r"revolving\s+(?:loan|facility)|standby\s+(?:loan\s+)?facility|debt\s+facility|senior\s+debt\s+facility|"
                       r"(?:delayed[\s-]draw\s+(?:term\s+)?|revolving\s+|standby\s+|multi-draw\s+)loan\s+facilit(?:y|ies)|financing\s+facility|"
                       r"line\s+of\s+credit|credit\s+line)\b|"
                       r"\b(?:secured|unsecured)\s+(?:(?!(?:loan|credit|debt|term|bridge|financing|prepayment|standby|revolving|working)\b)"
                       r"(?-i:[A-Z][\w&.\-]*)\s+){0,2}?facilit(?:y|ies)\b")   # FIX3: 'the secured Samsung facility'
_I_NOTES = re.compile(r"(?i)\b(?:senior\s+(?:secured\s+|unsecured\s+)?(?:second[\s-]lien\s+|first[\s-]lien\s+)?notes?|"
                      r"(?:[\d.]+\s*%\s+)(?:senior\s+)?(?:secured\s+|unsecured\s+)?notes?\s+due|notes?\s+due\s+(?:19|20)\d\d|"
                      r"(?:secured\s+|unsecured\s+|non-convertible\s+|senior\s+secured\s+|senior\s+|redeemable\s+|series\s+\w+\s+)"
                      r"debentures?|debenture\s+(?:financing|offering|units?|private\s+placement)|bonds?\s+(?:issue|offering)|"
                      r"(?:corporate|project|green)\s+bonds?|\bbonds?\s+due)\b")
_I_LOAN = re.compile(r"(?i)\b(?:(?:secured|unsecured|term|bridge|bridging|shareholder|related[\s-]party|interest[\s-]free|"
                     r"non-interest[\s-]bearing|construction|project|acquisition|government|repayable|promissory|demand|"
                     r"working\s+capital|senior|senior\s+secured|first[\s-]lien)\s+)*(?:loans?(?:\s+facilit(?:y|ies))?|promissory\s+notes?)\b(?!\s+"
                     r"(?:technology|assets|company|applications?|origination|platform|portfolio|book|products?|officers?|servic\w*|market|"
                     r"business|brokers?|brokerage|underwriting|demand))")
_I_DEBT = re.compile(r"(?i)\b(?:debt\s+financing|senior\s+debt|secured\s+debt|project\s+debt|debenture|debentures)\b")

_INSTR_ORDER = (("gold_loan", _I_GOLD), ("prepayment", _I_PREPAY), ("convertible_debenture", _I_CONVDEB),
                ("convertible_note", _I_CONVNOTE), ("notes", _I_NOTES), ("credit_facility", _I_CREDIT), ("loan", _I_LOAN))


def _instruments_in(s):
    """[(start, end, instrument)] non-overlapping, most specific first."""
    taken, out = [], []
    for kind, rx in _INSTR_ORDER:
        for m in rx.finditer(s):
            a, b = m.start(), m.end()
            if any(a < y and x < b for x, y in taken):
                continue
            txt = m.group(0).lower()
            if kind == "loan" and re.search(r"(?i)\b(?:stock|share|warrant)\s+$", s[max(0, a - 7):a]):
                continue
            if kind == "loan" and txt == "loans" and (
                    re.search(r"(?-i:[A-Z][a-z]+)(?<!s)(?<!ed)\s+$", s[max(0, a - 25):a]) and m.group(0)[0] == "L" and
                    not re.search(r"(?i)\b(?:the|its|a|an|such|Term|Bridge|Shareholder|Secured|Unsecured|Government|Project|"
                                  r"Construction|Promissory|Demand|Related|Party|Additional|New|Existing)\s+$", s[max(0, a - 25):a])):
                continue                                  # a brand: 'Ruby Loans', 'Easy Loans'
            if kind == "loan" and txt == "loans" and re.search(r"(?i)\b(?:business|consumer|mortgage|personal|small|student|"
                                                             r"payday|auto|car|bank's|residential|commercial)\s+$", s[max(0, a - 15):a]):
                continue                                  # a lending business, not the company's debt
            if kind == "credit_facility" and txt.endswith("revolver") and (
                    m.group(0).endswith("Revolver") and not re.search(r"(?i)\b(?:the|its|a|new)\s+$", s[max(0, b - 20):b - 8]) or
                    re.match(r"\s+(?-i:[A-Z])|\s+(?:\w+\s+){0,2}(?:project|property|claims?|deposit|prospect|mine|rare|gold|silver|"
                             r"copper|lithium|zinc|nickel|uranium|graphite)\b", s[b:b + 40])):
                continue                                  # 1.0.4: a project or property named 'Revolver'
            if kind == "credit_facility" and re.search(r"(?i)^(?:[\d.,$\s]|us|c|ca)*(?:million|m|billion|b)?\s*$",
                                                        txt.split("credit")[0] if "credit" in txt else "x"):
                pass
            taken.append((a, b))
            out.append((a, b, kind))
    out.sort()
    return out


def _generic_debenture(s):
    """A bare 'debenture(s)' whose type the release sets elsewhere."""
    return [(m.start(), m.end()) for m in re.finditer(r"(?i)\bdebentures?\b", s)]


# ------------------------------------------------------------------ stages
_ST_TERM = re.compile(r"(?i)\bterminat(?:ed|es|ion\s+of)\b|\bcancel(?:l?ed|s)\b|\bdefault(?:ed)?\b|\baccelerat(?:ed|ion)\b|"
                      r"\bforgiv(?:e|en|es|eness)\b|\bwritten\s+off\b")
_ST_REPAID = re.compile(r"(?i)(?<!on\s)(?<!upon\s)(?<!until\s)(?<!before\s)(?<!prior\sto\s)(?<!for\s)(?<!of\s)"
                        r"\brepa(?:id|ys?|yment\s+of|yment\s+in\s+full|ying)\b|\brepayments?\b(?!\s+(?:terms?|schedule|dates?|period|tenor|profile|"
                        r"will|begins?|commenc|obligations|of\s+principal\s+will))|(?<!on\s)(?<!upon\s)(?<!to\s)\bredeem(?:ed|s)?\b|"
                        r"(?<!on\s)(?<!upon\s)(?<!of\s)(?<!at\s)\bredemption\b|"
                        r"\bpaid\s+(?:off|in\s+full|down)|\bpays?\s+(?:off|down)\b|\bbought\s+back|\bbuys?\s+back\b|\bbuy-?back\b(?!\s+(?:provision|right|option|clause))|"
                        r"\btender\s+offer\b|\bpurchased?\s+for\s+cash\b|\bsettle(?:d|s|ment)?\b(?![^.]{0,60}\binterest\b)|"
                        r"\bextinguish(?:ed|es)?\b|\bcancelling\s+the\s+[^.]{0,40}(?:loan|debenture|note|debt)|\bshares?\s+for\s+debt\b|"
                        r"\bfor\s+debt\s+(?:transaction|settlement)|\bdebt\s+(?:settlement|repayment)\b|\breducing\s+debt\b|"
                        r"\bretir(?:e|es|ed|ing)\b|\bretirement\s+of\s+(?:the\s+|its\s+|all\s+)?(?:[\w$.,%-]+\s+){0,4}?(?:debt|notes?|loans?|debentures?|"
                        r"facilit(?:y|ies))\b|\bshares?[\s-]+for[\s-]+(?:\w+\s+and\s+)?debt\b|\breduc(?:e|es|ed|tion)\s+(?:of\s+)?(?:its\s+|the\s+|in\s+)?"
                        r"(?:[\w$.,%-]+\s+){0,5}?(?:debt|debentures|notes|loans?)\b|\b(?:agree[sd]?\s+to\s+)?(?:re)?purchase[sd]?\s+(?:(?:US|C)?\$[\d.,]+\s*"
                        r"(?:million|billion)?\s+(?:of\s+)?)?(?:its\s+|the\s+)?(?:[\w-]+\s+){0,6}?notes\b[^.]{0,60}\b(?:tender|offers?|auction)")
                        # 1.0.4: retire, shares-for-debt, debt reduction, notes bought back through tender offers
_ST_CONV = re.compile(r"(?i)(?<!be\s)(?<!fully\s)(?<!if\s)\bconverted\b(?![^.]{0,30}\bprice\b)|(?<!upon\s)(?<!on\s)(?<!of\s)(?<!for\s)(?<!the\s)"
                      r"\bconversion\s+of\b(?![^.]{0,30}\bprice\b)|(?-i:\bConverts\b)|\bconverts\s+(?:US|C)?\$|"
                      r"\bnotice\s+(?:to\s+convert|of\s+conversion)\b|\belect(?:ed|ion)\s+to\s+convert\b|(?<!to\s)(?<!for\s)"
                      r"(?<!an\s)\bautomatic\s+conversion\b|\bfull\s+conversion\b|\bhas\s+converted\b|\bconverting\s+(?:US|C)?\$")
_ST_AMEND = re.compile(r"(?i)\bamend(?:ed|s|ing|ments?)\b|\bextend(?:ed|s|ing)?\b(?![^.]{0,25}\b(?:offer|offering|closing|deadline|placement)\b)|"
                       r"\bextension\b(?![^.]{0,25}\b(?:offering|closing|deadline|placement)\b)|"
                       r"\brestructur(?:e|ed|es|ing)\b|\bincreas(?:e|ed|es|ing)\s+(?:to\s+)?(?:the\s+|its\s+)?(?:[\w$.,]+\s+){0,4}?"
                       r"(?:loan|facility|debenture|credit)|\bupsiz(?:e|ed|es|ing)\s+(?:of\s+)?(?:the\s+|its\s+)?(?:existing\s+)?"
                       r"(?:[\w$.,]+\s+){0,3}?(?:credit|loan|facility|revolv)|\breplacement\s+(?:convertible\s+)?debentures?\b|"
                       r"\breprice[ds]?\b|\brepricing\b|\bvariation\b|\bassign(?:s|ed)\b|\bassignment\s+of\b|"
                       r"\bdeferral\b|\bdefer(?:s|red|ring)?\s+(?:the\s+|its\s+)?(?:\w+\s+)?(?:payment|repayment|maturity|interest)|"
                       r"\bdefer(?:s|red|ring)?\s+(?:the\s+|its\s+|all\s+)?(?:\w+\s+)?(?:debts?|indebtedness|loans?)\b")   # FIX3
_ST_DRAWN = re.compile(r"(?i)\bdr(?:ew|awn|aws?)\s+(?:down\s+)?(?:an?\s+)?(?:additional\s+|further\s+|the\s+)?"
                       r"(?:[\w$.,]+\s+){0,3}?(?:under|from|on)\b|\bdraw(?:-|\s)?down\b|\bdrawdown\b|\badvance\s+(?:of|under)\b|"
                       r"\b(?:receiv\w*|receipt\s+of|advance[sd]?)\s+(?:of\s+)?(?:an?\s+|the\s+)?(?:additional\s+|further\s+|second\s+|third\s+|"
                       r"final\s+)?(?:(?:US|C|CA)?\$\s?[\d.,]+\s*(?:million|M)?\s+)?(?:\w+\s+){0,2}?(?:under|on|pursuant\s+to)\s+(?:(?:the|its|a|an|"
                       r"previously|existing)\b|(?:[\w-]+\s+){0,2}(?:credit|loan|debt)\s+(?:facility|agreement))")   # 1.0.4: 'Receives US$5 Million Under Credit Facility'
_ST_CLOSED = re.compile(r"(?i)(?<!prior\sto\sthe\s)(?<!following\sthe\s)(?<!from\sthe\s)(?<!after\sthe\s)(?<!upon\s)(?<!on\s)"
                        r"(?<!at\s)(?<!of\s)(?<!until\s)(?<!before\s)(?<!toward\s)(?<!towards\s)(?<!to\s)(?<!for\s)\bclos(?:ed|es|ing)\b(?!\s+(?:price|date|conditions)\b)"
                        r"(?!\s+(?:date\s+of\s+the\s+(?:agreement|offering)\s+is\s+expected))|"
                        r"(?<!to\s)(?<!help\s)(?<!will\s)\bcompleted?\b|\bcompletes\b|\bcompletion\s+of\b|(?<!be\s)(?<!been\s)(?<!previously\s)\bissued\b(?!\s+(?:in\s+(?:ordinary\s+)?(?:multiples|denominations)|at\s+(?:a\s+)?"
                        r"(?:price|discount|par)|pursuant\s+to\s+(?:the\s+)?(?:terms|a|an)\b|under\s+(?:the\s+|a\s+)?(?:trust\s+)?indenture))|\bhas\s+issued\b|\bissues\b|\bfunded\b|"
                        r"\bfinancial\s+close\b|\breceive[ds]\b(?!\s+(?:\w+\s+){0,3}(?:approvals?|acceptance|consent|letter|indication|term\s+sheet|LOI)\b)|\bobtain(?:ed|s)\b(?!\s+(?:\w+\s+){0,2}(?:approval|acceptance|consent))|\bsecured\s+(?:a|an|the)\b|"
                        r"\bsecures\b|\badvanced\b(?=\s+(?:to|under|by|on|the|a|an|(?:US|C|CA)?\$|funds|in|as|pursuant)\b)|"
                        r"\b(?:has|have|had|was|were|been)\s+advanced\b|\breceipt\s+of\b(?!\s+(?:\w+\s+){0,3}(?:approvals?|acceptance|consent|"
                        r"letter|indication|term\s+sheet|LOI|notice|commitment|repayment))|"
                        r"\bprovided\b(?!\s+(?:that|for))|\bfully\s+(?:subscribed|funded)\b|"
                        r"\bsuccessfully\s+completes?\b|\bissuance\s+of\b|\bhas\s+raised\b|\braised\s+(?:gross\s+proceeds|CDN|C?\$|US\$)|\badvances\s+(?:a\s+|an\s+)?(?:(?:US|C)?\$[\d.,]+\s*(?:million\s+)?)?"
                        r"(?:secured\s+|bridge\s+|convertible\s+)?loan\b")
_ST_SIGNED = re.compile(r"(?i)\bentered\s+in(?:to)?\b|\benters\s+in(?:to)?\b|\bsign(?:ed|s|ing)\b(?!\s+of\s+a\s+(?:non-binding|term))|"
                        r"\bexecut(?:ed|es|ion\s+of)\b|\bpric(?:ed|ing|es)\b|\bdefinitive\b|\bbinding\s+(?:agreement|commitment|"
                        r"loan)|\bagreed\s+to\s+(?:lend|provide|advance|subscribe|issue)\b|\bagreed\s+to\s+(?:a|an|the)\s+(?:[\w-]+\s+){0,3}"
                        r"(?:loan|facility|financing|debentures?|notes?)\b|\bapprov(?:ed|es)\b(?=[^.]{0,30}\b(?:by\s+)?"
                        r"(?:the\s+)?(?:TSX|Exchange|CSE|shareholders)\b)|\barranged?\b|\barranges\b|"
                        r"\bestablish(?:ed|es)\b|\bagreement\s+with\b|\bagreement\s+dated\b|\breceive[ds]?\s+(?:\w+\s+){0,2}(?:approval|acceptance)\b|"
                        r"\bagreements?\s+for\s+(?:an?\s+|the\s+)?(?:(?:US|C|CA)?\$|new\b|revolving|senior|secured|term|credit|loan)|"
                        r"\bsatisf(?:ied|ies|action\s+of)\s+(?:\w+\s+){0,4}?conditions\s+precedent\b|"   # FIX3: an update on a facility's conditions
                        r"\bentry\s+into\b")                       # FIX5: 'Entry into a New Credit Facility'

_ST_PROP = re.compile(r"(?i)\bpropos(?:ed|es|al)\b|\bintend(?:s|ed)?\s+to\b|\bintention\s+to\b|\bterm\s+sheet\b|\bletters?\s+of\s+(?:intent|interest)\b|"
                      r"\bLOI\b|\bnon-binding\b|\bcommitment\s+letter\b|\bproject\s+letter\b|\bmandate\b|\bplans?\s+to\b|"
                      r"\blaunch(?:es|ed)?\b|\bannounces?\s+(?:a\s+|an\s+|its\s+)?(?:(?:proposed|non-brokered|brokered|"
                      r"private)\s+)*(?:offering|private\s+placement|financing)|\boffering\s+of\b|\bprivate\s+placement\s+of\b|"
                      r"\bseeks?\s+approval\b|\bfiles?\s+for\s+approval\b|\bproposes?\b|\bnegotiat(?:ed|es|ing)\b|"
                      r"\bis\s+(?:pleased\s+to\s+)?(?:announc\w+\s+)?(?:arranging|offering)\b|\bup\s+to\s+(?:C\$|US\$|\$)|"
                      r"\bagreed\s+(?:to\s+)?terms\b|\bexpected\s+to\s+close\b|\bagrees?\s+to\s+(?:acquire|purchase)\b|"
                      r"\barrang(?:es|ed|ing)\s+(?:a\s+|an\s+|its\s+)?(?:[\w$.,-]+\s+){0,4}?(?:offering|private\s+placement)\b|"
                      r"\bapprov(?:ed|es)\b(?![^.]{0,30}\b(?:by\s+)?(?:the\s+)?(?:TSX|Exchange|CSE|shareholders)\b)|"
                      r"\bcredit\s+approval\b")                # 1.0.4: a lender's approval is a commitment, not an agreement

_ANNOUNCE_OFFER = re.compile(r"(?i)\bannounces?\s+(?:a\s+|an\s+|its\s+)?(?:(?!(?:clos\w*|complet\w*|terminat\w*|repa\w*|amend\w*|"
                             r"extend\w*|draw\w*|converts?|converted|conversion|first|second|third|final|tranche)\b)[\w$.,-]+\s+){1,5}?"
                             r"(?:offering|private\s+placement|financing)\b")
_CLAUSE_BREAK = re.compile(r"(?i)\band\s+(?:also\s+)?(?:announc|secur|sign|enter|receiv|provid|complet|clos|obtain|launch|updat|"
                           r"cancel|terminat|appoint|report|grant|issu|acquir|arrang|execut|agree)\w*\b|;|"
                           r"\s[-\u2013|]\s")

_NOUN_OFFER = re.compile(r"(?i)(?:offering|private\s+placement)\s+of\b")

_STAGE_TESTS = (("terminated", _ST_TERM), ("repaid", _ST_REPAID), ("converted", _ST_CONV), ("amended", _ST_AMEND),
                ("drawn", _ST_DRAWN), ("closed", _ST_CLOSED), ("signed", _ST_SIGNED), ("proposed", _ST_PROP))

# not debt events
_INTEREST_SHARES = re.compile(r"(?i)\binterest\b[^.]{0,120}\b(?:in|by\s+(?:the\s+)?issu\w+\s+of|through\s+the\s+issuance\s+of|"
                              r"satisf\w+[^.]{0,40})\s+(?:common\s+)?shares\b|\b(?:interest\s+)?shares\b[^.]{0,60}\b(?:in\s+"
                              r"(?:payment|satisfaction|lieu)\s+of|to\s+pay|for)\s+(?:the\s+)?(?:accrued\s+)?interest\b|\binterest\s+"
                              r"payment\b|\binterest\s+conversion\b|\bpay\s+(?:debenture\s+)?interest\b|\binterest\s+shares\b")
_MANDATE = re.compile(r"(?i)\b(?:financial|debt)\s+advis[oe]r\b|\bappoint\w*\b[^.]{0,80}\badvis[oe]r\b|\bmandated?\s+lead\s+arranger")
_BACKGROUND = re.compile(r"(?i)\b(?:previously\s+(?:announced|disclosed|issued|entered)|as\s+(?:previously\s+)?(?:announced|disclosed)"
                         r"\s+on|originally\s+issued|(?:has|had)\s+(?:an?\s+)?outstanding|currently\s+outstanding|"
                         r"remain(?:s|ing)?\s+outstanding|was\s+(?:issued|entered\s+into|announced)\s+(?:on|in)\b|issued\s+on\s+"
                         r"(?:" + T._DATE_RX + r")|\bon\s+(?:" + T._DATE_RX + r"),?\s+(?:the\s+(?:Company|Corporation)|it)\s+announced\b)")
_RESULTS_HL = re.compile(r"(?i)\b(?:results|quarter(?:ly)?\s+(?:report|update)|Q[1-4]\b|financial\s+statements|annual\s+report|"
                         r"MD&A|year[\s-]end|year\s+in\s+review)\b")    # 1.0.4: a year-in-review recap is read like results
_HL_EVENT = re.compile(r"(?i)\b(?:announc\w*|clos\w*|complet\w*|secur\w*|enter\w*|sign\w*|execut\w*|arrang\w*|obtain\w*|"
                       r"receiv\w*|extend\w*|extension|amend\w*|repa\w*|redeem\w*|redemption|convert\w*|conversion|issu\w*|dr[ae]w\w*|"
                       r"pric\w*|launch\w*|upsiz\w*|increas\w*|establish\w*|finaliz\w*|settle\w*|restructur\w*|terminat\w*|"
                       r"propos\w*|agree\w*|approv\w*|buys?\s+back|pays?\s+(?:down|off)|reduc\w*|advanc\w*|provid\w*|acquir\w*|"
                       r"files?|seeks?|notice|replace\w*|offering|financing|placement|loans?|debentures?|notes?|facility)\b")
_OTHER_CO_LOAN = re.compile(r"(?i)\b(?:EXIM|Export[\s-]Import\s+Bank)\b[^.]{0,120}\b(?:loan|approv\w+)[^.]{0,80}\b(?:Perpetua|"
                            r"for\s+the\s+development\s+of\s+(?!the\s+Company))")
_PROMO = re.compile(r"(?i)^\s*(?:As\s+America|Market\s+One|Disseminated\s+on\s+behalf|This\s+article)|\bpaid\s+advertisement\b|"
                    r"\bsponsored\s+content\b|\busanewsgroup\b")

# ------------------------------------------------------------------ amounts
_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_MULT = {"million": 1e6, "m": 1e6, "mm": 1e6, "mln": 1e6, "k": 1e3, "thousand": 1e3, "billion": 1e9, "b": 1e9, "bn": 1e9}


def _curr(tag, ctx=""):
    t = (tag or "").upper().replace("$", "").strip()
    if t in ("US", "USD"):
        return "USD"
    if t in ("A", "AU", "AUD"):
        return "AUD"
    if t in ("C", "CA", "CAD", "CDN"):
        return "CAD"
    if t in ("GBP", "\u00a3"):
        return "GBP"
    if t in ("EUR", "\u20ac"):
        return "EUR"
    return None


def _money_all(s):
    """[(start, end, value, currency_or_None)]"""
    out = []
    for m in re.finditer(r"(?i)(?<![\w.$])(?-i:(US(?=\s?\$)|CA(?=\s?\$)|CAD|CDN|USD|AU(?=\s?\$)|AUD|A(?=\$)|C(?=\$)))?\s?\$\s?" + _NUM +
                         r"(?:\s*(million|billion|thousand|mln|bn|mm|m|k|b)\b)?|(?<![\w.])(?-i:(CAD|USD|AUD|US|C))\s?\$?\s?" + _NUM +
                         r"(?:\s*(million|billion|thousand|mln|bn|mm|m|k|b)\b)", s):
        if m.group(2):
            cur, num, mult = m.group(1), m.group(2), m.group(3)
        else:
            cur, num, mult = m.group(4), m.group(5), m.group(6)
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        if not (v >= 1e5 and (mult or "").lower() in ("million", "billion", "thousand", "mln", "bn", "mm")):
            v = round(v * _MULT.get((mult or "").lower(), 1), 2)   # 1.0.4: '$17,500,000 Million' is already whole
        tail = s[m.end():m.end() + 30].lower()
        if re.match(r"\s*(?:per|/|a)\s*(?:common\s+)?(?:share|unit|ounce|oz|tonne|lb|pound|debenture|warrant)\b", tail):
            continue
        if re.match(r"\s*(?:per\s+)?(?:share|unit)\b", tail):
            continue
        out.append((m.start(), m.end(), v, _curr(cur)))
    if "\u00a3" in s or "\u20ac" in s:                              # 1.0.4: sterling and euro amounts ('GBPGBP1,000,000', 'EUR680 million')
        for m in re.finditer(r"(?i)(?<![\w.])(?:(GBP|EUR)\s?)?([\u00a3\u20ac])\s?" + _NUM + r"(?:\s*(million|billion|thousand|m|bn|b)\b)?", s):
            v = float(m.group(3).replace(",", ""))
            if not (v >= 1e5 and (m.group(4) or "").lower() in ("million", "billion", "thousand", "bn")):
                v = round(v * _MULT.get((m.group(4) or "").lower(), 1), 2)
            if not re.match(r"(?i)\s*(?:per|/)\s*(?:common\s+)?(?:share|unit|ounce|oz|tonne)\b", s[m.end():m.end() + 30]):
                out.append((m.start(), m.end(), v, "GBP" if m.group(2) == "\u00a3" else "EUR"))
        out.sort()
    return out


def _body_currency(h, b):
    """The currency a release declares for itself: 'All amounts in US dollars', '(In United States dollars ...)'."""
    t = (h + " " + b[:1500])
    if re.search(r"(?i)\b(?:all\s+(?:dollar\s+)?(?:amounts|figures)\s+(?:are\s+)?(?:expressed\s+)?in\s+(?:US|U\.S\.|United\s+States)|"
                 r"in\s+United\s+States\s+dollars|amounts\s+in\s+US\$|all\s+amounts\s+in\s+US\$|unless\s+otherwise\s+(?:noted|"
                 r"indicated|stated)[^.]{0,20}US\$)", t):
        return "USD"
    if re.search(r"(?i)\b(?:all\s+)?(?:references\s+to\s+)?(?:dollar\s+)?(?:amounts|figures)\s+(?:contained\s+)?in\s+this\s+"
                 r"(?:press|news)\s+release\s+are\s+(?:expressed\s+|stated\s+)?in\s+(?:US|U\.S\.|United\s+States)\s+dollars", b):
        return "USD"
    if re.search(r"(?i)\(\s*(?:all\s+amounts\s+(?:are\s+)?(?:expressed\s+|stated\s+)?)?in\s+(?:U\.\s?S\.|US|United\s+States)\s+"
                 r"dollars?\b[^)]{0,40}(?:unless|except)|\bexpressed\s+in\s+(?:U\.\s?S\.|US|United\s+States)\s+dollars?\b"
                 r"[^.]{0,30}(?:unless|except)", t):
        return "USD"                                      # 1.0.2: "(in U.S. dollars unless otherwise noted)"
    return None


# ------------------------------------------------------------------ fields
_RATE = re.compile(r"(?i)(?:interest|coupon|bear\w*|accru\w*|rate\s+of|at\s+a\s+rate)[^.%]{0,60}?(\d{1,2}(?:\.\d{1,3})?)\s*(?:%|per\s*cent\b|percent\b)"
                   r"|(\d{1,2}(?:\.\d{1,3})?)\s*(?:%|per\s*cent\b|percent\b)\s*(?:subordinated\s+|redeemable\s+)?(?:per\s+annum|per\s+year|annual(?:ly)?|p\.a\.|interest|coupon|simple\s+interest|"
                   r"compounded|senior|convertible|secured|unsecured|second[\s-]lien|first[\s-]lien|notes?|debentures?|"
                   r"(?:unsecured\s+|secured\s+)?convertible)")
_FLOAT = re.compile(r"(?i)\b(?:(?:1|one|three|3)[\s-]month\s+)?(?:adjusted\s+|term\s+)?(?:SOFR|CORRA|CDOR|LIBOR|prime(?:\s+rate)?|"
                    r"base\s+rate|BA\s+rate|EURIBOR|Secured\s+Overnight\s+Financing\s+Rate|federal\s+funds(?:\s+effective)?\s+"
                    r"rate|reference\s+rate|term\s+benchmark(?:\s+basis)?|bankers'?\s+acceptance(?:\s+rate)?)\b[^.;]{0,20}?(?:\+|plus)\s*(?:a\s+margin\s+of\s+)?(\d(?:\.\d+)?)\s*%"
                    r"(?:\s*(?:to|-|\u2013)\s*(\d(?:\.\d+)?)\s*%)?")
_ZERO = re.compile(r"(?i)\b(?:non-interest[\s-]bearing|interest[\s-]free|zero[\s-]coupon|without\s+interest|bears?\s+no\s+interest|"
                   r"no\s+interest)\b")
_DUE = re.compile(r"(?i)\b(?:notes?|debentures?|bonds?)\s+due\s+((?:19|20)\d\d)\b|\bdue\s+(" + T._DATE_RX + r")")
_MATURE = re.compile(r"(?i)\b(?:matur(?:e|es|ing|ity(?:\s+date)?)|due\s+date|repayable|payable\s+in\s+full|due\s+and\s+payable|expire|"
                     r"must\s+repay[^.]{0,120}?\bby)\b[^.]{0,50}?"
                     r"(?:on|of|to|until|by|in|:)?\s*(?:the\s+)?(" + T._DATE_RX + r"|(?:January|February|March|April|May|June|July|"
                     r"August|September|October|November|December)\s+(?:19|20)\d\d|(?:19|20)\d\d\b)")
_WORDN = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "twelve": 12, "eighteen": 18, "twenty-four": 24, "thirty-six": 36, "sixty": 60}
_TERMRX = re.compile(r"(?i)\b(?:term\s+of(?:\s+up\s+to)?|for\s+a\s+(?:period|term)\s+of|(?:final\s+)?maturity\s*(?:of|:)|term\s*:|matur\w+\s+(?:in|on\s+the\s+date\s+(?:that\s+is|which\s+is)|"
                     r"after)|(?:mature|repayable|due|payable)\s+(?:on\s+the\s+date\s+that\s+is\s+)?|over|period\s+of|tenor\s+of|"
                     r"(?<!\d)-)?\s*\(?(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|twelve|eighteen|twenty-four|"
                     r"thirty-six|sixty)\)?\s*\(?\d*\)?\s*[\s-](months?|years?)\b(?:\s*\(\d+\))?(?:\s+(?:term|from|after|following|"
                     r"maturity|tenor))?")
_CONVP = re.compile(r"(?i)\b(?:conversion\s+(?:price|rate)\b[^.$]{0,200}?|deemed\s+price\s+per\s+(?:common\s+)?share\s+of\s+|convertible\s+(?:into\s+[^.]{0,80}?)?at\s+"
                    r"(?:a\s+(?:price|rate)\s+of\s+)?|convert(?:ible|ed|s|ing)?\s+(?:[^.]{0,90}?\s)?into\b[^.]{0,90}?at\s+(?:(?:a|the)\s+(?:conversion\s+)?"
                    r"(?:price|rate)\s+(?:per\s+(?:common\s+)?share\s+)?(?:(?:of|equal\s+to)\s+)?)?|at\s+a\s+"
                    r"conversion\s+price\s+of\s+|conversion\s+rate\s+of\s+|(?:deemed\s+)?(?:value|price)\s+of\s+(?=[^.]{0,12}\$[\d.]+\s+per\s+Unit)|convertible\s+(?:debentures?|notes?|loans?)\b[^.$]{0,100}?"
                    r"\bat\s+(?=(?:US|C|CA)?\$\s?\d+(?:\.\d+)?\s+per\s+(?:common\s+)?share))(?:(US|C|CA|CAD|CDN|USD)\s?)?\$\s?(\d+(?:\.\d+)?)")
_UNIT_MULTI = re.compile(r"(?i)\bunits?\b[^.]{0,220}?\b(?:consist\w*|compris\w*|each)\b[^.]{0,40}?\b(?:two|three|four|five|six|seven|"
                         r"eight|nine|ten|[2-9]|\d{2,})\b(?:\s*\(\d+\))?(?:\s+[\w.\-]+){0,4}?\s+shares")
_WARR_N = re.compile(r"(?i)(\d{1,3}(?:,\d{3})+|\d{4,})\s+(?:common\s+share\s+purchase\s+|share\s+purchase\s+|bonus\s+|"
                     r"non-transferable\s+|detachable\s+|debenture\s+)?warrants\b")
_WARR_P = re.compile(r"(?i)\bwarrants?\b[^.]{0,160}?\b(?:exercis\w+|exercise\s+price)[^.$]{0,60}?(?:(US|C|CA|CAD|USD)\s?)?\$\s?"
                     r"(\d+(?:\.\d+)?)")
_SECURED_NO = re.compile(r"(?i)\bunsecured\b")
_SECURED_YES = re.compile(r"(?i)\b(?:senior\s+secured|secured\s+(?:[\w-]+[\s-](?:year|month)\s+)?(?:by|against|convertible|debentures?|notes?|loans?|term|"
                          r"credit|bridge|promissory|debt|revolving|first[\s-]lien|second[\s-]lien)|(?:first|second)[\s-](?:ranking|lien)"
                          r"\s+(?:security|charge|secured)|general\s+security\s+agreement|security\s+(?:interest|over|on|agreement)|"
                          r"secured\s+against|pledge\s+of|guaranteed\s+and\s+secured|is\s+secured|will\s+be\s+secured|are\s+secured|"
                          r"collateralized|second[\s-]lien|first[\s-]lien|first\s+charge|security\s+(?:that\s+)?was\s+pledged|security\s+"
                          r"pledged|as\s+security\s+for|first[\s-]ranking\s+security|assets\s+secured\s+under|secured\s+by\s+a\s+charge)\b")
_RELATED = re.compile(r"(?i)\brelated[\s-]part(?:y|ies)\b|\binsiders?\b|\b(?:a|one|certain)\s+(?:director|officer)s?\b|"
                      r"\b(?:its|the\s+Company's)\s+(?:Chief\s+Executive\s+Officer|CEO|Chairman|Chair|President|largest\s+shareholder|"
                      r"major\s+shareholder|controlling\s+shareholder)\b|\bcontrol\s+person\b|\bnon-arm'?s[\s-]length\b|"
                      r"(?-i:\b(?:Chairman|CEO|President)\s+(?:(?:[A-Z][a-z]+\s+[A-Z][a-z]+)(?=[^.]{0,60}\b(?:lends?|loaned|advanced|"
                      r"provided|will\s+(?:lend|provide|advance)|has\s+agreed\s+to\s+(?:lend|provide|advance)|subscribed)\b)|Converts|"
                      r"Lends|Provides|Advances)\b)")

_ORG_W = r"(?:[A-Z][\w&'\-.]*|of|and|&|de|du|des|la|le|du|der|f\u00fcr|y)"
_ORG_TAIL = (r"(?:Corp(?:oration)?|Inc|Ltd|LTD|Limited|LLC|L\.L\.C|LP|L\.P|Pty(?:\s+Ltd)?|PTE(?:\s+LTD)?|Pte(?:\s+Ltd)?|S\.A|SAS|GmbH|AG|PLC|plc|"
             r"Plc|Ltda|N\.V|B\.V|AB|Services|"
             r"ULC|Trust|Bank|Banks|Capital|Fund|Funds|Partners|Group|Holdings|Management|Financial|Finance|Investments?|"
             r"Credit|Lending|Resources|Mining|Metals|Minerals|Royalt(?:y|ies)|Streaming|Nation|Canada|International)")
_ORG = re.compile(r"((?:[A-Z][\w&'\-.]*\s+){0,6}?" + _ORG_TAIL + r"\.?(?:\s+(?:Ltd|Inc|LLC|LP|AG|Corp|Limited)\.?)?(?:\s+(?:of|de)\s+"
                  r"(?:Canada|Montreal|Nova\s+Scotia|America|the\s+United\s+States))?)")
_KNOWN_LENDERS = re.compile(r"\b(?:EBRD|EDC|BDC|EXIM|Export\s+Development\s+Canada|Export[\s-]Import\s+Bank(?:\s+of\s+the\s+United\s+States)?|"
                            r"U\.S\.\s+Department\s+of\s+Energy|DOE|Glencore(?:\s+AG|\s+International\s+AG)?|Trafigura(?:\s+(?:PTE|Pte)\.?"
                            r"(?:\s+Ltd\.?)?|\s+Canada(?:\s+Limited)?)?|Sprott(?:\s+Resource\s+(?:Lending|Streaming\s+and\s+Royalty)"
                            r"(?:\s+Corp\.?)?)?|Nebari(?:\s+[A-Z][\w]+){0,6}|Auramet(?:\s+International,?\s+Inc\.?)?|Ocean\s+Partners"
                            r"(?:\s+UK\s+Ltd\.?)?|Monetary\s+Metals(?:\s+&\s+Co\.?)?|Beedie(?:\s+Capital|\s+Investment\s+Ltd\.?)?|"
                            r"Orion(?:\s+Resource\s+Partners)?|Macquarie(?:\s+Bank)?|BMO|Bank\s+of\s+Montreal|National\s+Bank\s+of\s+Canada|"
                            r"Scotiabank|Bank\s+of\s+Nova\s+Scotia|TD|Toronto-Dominion\s+Bank|RBC|Royal\s+Bank\s+of\s+Canada|CIBC|"
                            r"ING|Soci[e\u00e9]t[e\u00e9]\s+G[e\u00e9]n[e\u00e9]rale|Pan\s+American\s+Silver\s+Corp\.?|Crescat\s+Capital(?:\s+LLC)?|"
                            r"Delbrook\s+Capital(?:\s+Advisors)?|Samsung(?:\s+C&T)?|Taykwa\s+Tagamou\s+Nation)\b")
_ORG_BAD = re.compile(r"(?i)^(?:the\s+)?(?:company|corporation|issuer|lenders?|holders?|debentureholders?|purchasers?|subscribers?|"
                      r"agent|borrower|parties|board|exchange|tsx|tsx\s+venture|canadian\s+securities|cse|tsxv|investors?|"
                      r"insiders?|directors?|the\s+lender|offering|financing|loan|notes?|debentures?|facility|credit|"
                      r"private\s+placement|units?|shares?|warrants?|canada|mining|resources|metals|minerals|"
                      r"[A-Z]{1,3}|finder|gold|silver|copper)$")


def _org_clean(o, self_rx):
    o = re.sub(r"^(?:the|a|an|its|our|with|from|by)\s+", "", o.strip(" ,;:.()\"'"), flags=re.I).strip(" ,;:")
    o = re.sub(r"\s*\((?:the\s+)?[\"\u201c][^)]*\)$", "", o).strip()
    if not o or len(o) < 3 or _ORG_BAD.match(o) or (self_rx and self_rx.search(o)):
        return None
    if re.match(r"(?i)^(?:TSX|CSE|NYSE|NASDAQ|OTC|FSE|Frankfurt|Canadian|Canada|United|U\.S|US|Securities|Exchange|Company|"
                r"Corporation|Board|Management|Series|Tranche|Offering|Private|Convertible|Senior|Secured|Unsecured|Credit|"
                r"Loan|Term|Revolving|Bridge|Debenture|Note|Notes|Facility|Agreement|Amended|Gold|Silver|Copper)\b", o):
        return None
    return o



def _self_rx(h, b):
    """The issuer's own names, so they are never read as a lender or borrower."""
    names = []
    m = re.search(r"([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5})\s*(?:Inc|Corp|Ltd|Limited|Corporation)?\.?\s*\((?:the\s+)?"
                  r"[\"\u201c]?(?:Company|Corporation|Issuer)?", b[:1500])
    for mm in re.finditer(r"\(\s*(?:TSXV?|TSX-V|CSE|NYSE|NEO|CBOE|OTCQB|OTC)\s*[:\s]", b[:1500]):
        pre = b[max(0, mm.start() - 90):mm.start()]
        n = re.search(r"([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5})\s*$", pre.strip(" ,"))
        if n:
            names.append(n.group(1))
        break
    for mm in re.finditer(r"[\"\u201c]\s*([A-Z][\w&.'\- ]{1,40}?)\s*[\"\u201d]\s*(?:,\s*)?(?:or|and)\s+(?:the\s+)?[\"\u201c]?(?:Company|Corporation|Issuer)",
                          b[:3000]):
        names.append(mm.group(1))
    words = set()
    for n in names:
        for w in re.findall(r"[A-Z][a-z]{2,}|[A-Z]{2,}", n):
            if w.lower() not in ("inc", "corp", "ltd", "limited", "corporation", "the", "resources", "mining", "metals", "gold",
                                 "silver", "minerals", "copper", "energy", "exploration", "company", "royalties", "royalty",
                                 "capital", "group", "holdings", "international", "canada", "canadian"):
                words.add(re.escape(w))
    if not words:
        return None
    return re.compile(r"\b(?:" + "|".join(sorted(words)) + r")\b")


def _date_of(s):
    m = T._DATE.search(s)
    return T._iso(m) if m else None


_MON_YEAR = (r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s*,?\s+(?:19|20)\d\d")
# FIX5: 'until August 16, 2028, being the maturity date', 'on June 30, 2026 (the "Maturity Date")', 'mature on the
# earlier of <an event> and March 4, 2019', 'Senior Notes due April, 2023', an extension 'from <date> to <date>' past 'Inc.'
_MAT_AFTER = re.compile(r"(?i)(" + T._DATE_RX + r")\s*,?\s*(?:being\s+the|\(\s*the\s*[\"\u201c]\s*)\s*maturity\s+date\b")
_MAT_EARLIER = re.compile(r"(?i)\b(?:matur(?:e|es|ing|ity(?:\s+date)?)|due|repayable)\b[^.]{0,30}?\bthe\s+earlier\s+of\b[^.]{0,140}?"
                          r"\band\s+(?:the\s+)?(" + T._DATE_RX + r")")
_DUE_ON = re.compile(r"(?i)\b(?:loans?|debentures?|notes?|facility|principal)\b[^.]{0,180}?(?<!interest\s)\b(?:is|are|will\s+be|shall\s+be|"
                     r"becomes?)\s+due\s+(?:and\s+payable\s+)?(?:on|by)\s+(?:or\s+before\s+)?(" + T._DATE_RX + r")")
_DUE_MON = re.compile(r"(?i)\b(?:notes?|debentures?|bonds?)\s+due\s+(" + _MON_YEAR + r")")
_EXTEND_TO = re.compile(r"(?i)\bextend\w*\b(?:[^.]|\.(?=\s*[(\u201c\"a-z,])){0,220}?\b(?:to|until)\s+(" + T._DATE_RX + r"|"
                         + _MON_YEAR + r"|(?:19|20)\d\d\b)")


def _maturity(sents, stage, skip=None):
    for s in sents:                                       # FIX5: the wordings above, before the generic ones
        s2 = s.replace(skip, " ") if skip else s
        for rx in (_MAT_AFTER, _MAT_EARLIER):
            m = rx.search(s2)
            if m and not (stage == "amended" and _EXTEND_TO.search(s2)):
                d = _to_date(m.group(1))
                if d:
                    return d
        m = (_DUE_MON.search(s2) if stage != "amended" else None) or _DUE_ON.search(s2)
        if m and not (stage == "amended" and _EXTEND_TO.search(s2)):
            d = _to_date(m.group(1))
            if d:
                return d
    if stage == "amended":
        ext = [d for s in sents for m in _EXTEND_TO.finditer(s.replace(skip, " ") if skip else s) for d in [_to_date(m.group(1))] if d]
        if ext:
            return max(ext)                               # 1.0.4: an extension's new date is the latest one it names
    for s in sents:
        if skip:
            s = s.replace(skip, " ")
        m = _DUE.search(s)
        if m:
            if m.group(1):
                return m.group(1)
            d = _to_date(m.group(2))
            if d:
                return d
        m = _MATURE.search(s)
        if m:
            d = _to_date(m.group(1))
            if d:
                return d
    return None


_MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
           "september": 9, "october": 10, "november": 11, "december": 12}


def _to_date(t):
    if not t:
        return None
    m = T._DATE.search(t)
    if m:
        return T._iso(m)
    m = re.match(r"(?i)(January|February|March|April|May|June|July|August|September|October|November|December)\s*,?\s+((?:19|20)\d\d)", t)
    if m:
        return "%s-%02d" % (m.group(2), _MONTHS[m.group(1).lower()])
    m = re.match(r"((?:19|20)\d\d)$", t.strip())
    if m:
        return m.group(1)
    return None


def _term_months(sents):
    t = _term_explicit(sents)
    if t:
        return t
    for s in sents:
        m = re.search(r"(?i)\b(?:the\s+)?(1st|first|2nd|second|3rd|third|4th|fourth|5th|fifth)\s+anniversary\s+of\s+the\s+(?:date\s+of\s+)?"
                      r"(?:issu|clos)", s)
        if m and re.search(r"(?i)matur", s):
            return {"1": 12, "f": 12, "2": 24, "s": 24, "3": 36, "t": 36, "4": 48, "5": 60}.get(m.group(1)[0].lower(),
                   {"fourth": 48, "fifth": 60}.get(m.group(1).lower()))
    return None


def _term_explicit(sents):
    for s in sents:
        for m in _TERMRX.finditer(s):
            n = m.group(1).lower()
            n = _WORDN.get(n, None) if not n.isdigit() else int(n)
            if not n:
                continue
            ctx = s[max(0, m.start() - 60):m.end() + 40].lower()
            # 'a secured two-year convertible debenture', 'a six-month loan': the term names the instrument
            adj = "-" in m.group(0) and re.match(r"(?i)\s*(?:(?:senior|secured|unsecured|convertible|non-convertible|bridge|term|"
                                                 r"promissory|subordinated|interest[\s-]bearing)\s+){0,3}(?:debentures?|notes?|"
                                                 r"loans?|credit\s+facilit|facilit|bonds?)\b", s[m.end():m.end() + 70])
            if not adj and not re.search(r"matur|term|repa(?:y|id)|due|tenor|from\s+(?:the\s+)?(?:date|closing|issu)|following|"
                                         r"after|months?[\s-]+period", ctx):
                continue
            if re.search(r"(?i)^\s*(?:term\s+)?(?:SOFR|CDOR|LIBOR|CORRA|BA\b|bankers|Secured\s+Overnight)", s[m.end():m.end() + 25]) or \
                    re.search(r"(?i)\b(?:term\s+)?(?:SOFR|CDOR|LIBOR|CORRA)\b", m.group(0)):
                continue                                  # 'three-month term SOFR' is a rate, not a term
            own = m.group(0).lower()
            if not adj and not re.search(r"term|period|matur|over|tenor|mature|repayable|due|payable|from|after|following|:", own + s[m.end():m.end() + 30].lower()[:30]):
                continue
            if re.search(r"(?i)every\s+(?:\w+\s+)?\(?\d*\)?\s*$|commencing\s+on\s+the\s+date\s+that\s+is\s*$|first\s*$|grace", s[max(0, m.start() - 40):m.start()]):
                continue
            if re.search(r"(?i)\bwarrants?\b[^.]*?\b(?:exercis\w+|entitle\w*)\b", s[:m.start()]) and \
                    not re.search(r"(?i)matur|debenture|\bnotes?\b|\bloan|facility", s[:m.start()]):
                continue                                  # FIX5: 'Each Warrant is exercisable ... for 24 months'
            if re.search(r"warrant|exercis|hold\s+period|(?:months?|years?)\s+and\s+one\s+day|notice|option\s+to\s+acquire|within\s+"
                         r"(?:\w+\s+)?\(?\d*\)?\s*months?\s+from\s+closing|grace|interest[\s-]only|availability", s[max(0, m.start() - 70):m.end() + 10].lower()):
                continue
            months = n * 12 if m.group(2).lower().startswith("year") else n
            if 1 <= months <= 240:
                return months
    return None


def _fixed_rate(s):
    for m in _RATE.finditer(s):
        v = float(m.group(1) or m.group(2))
        ctx = s[max(0, m.start() - 40):m.end() + 40].lower()
        if re.search(r"(?i)\b(?:SOFR|CORRA|CDOR|LIBOR|EURIBOR|prime\s+rate|base\s+rate|reference\s+rate|Secured\s+Overnight)\b[^.]{0,80}"
                     r"\b(?:plus|spread|margin)\b", s[max(0, m.start() - 160):m.end()]):
            continue                                      # 1.0.4: a spread or margin over a floating rate
        if re.search(r"(?i)\b(?:standby|commitment|undrawn|arrangement|structuring)\s+fees?\b[^.]{0,160}$", s[max(0, m.start() - 170):m.start()]):
            continue                                      # 1.0.4: a fee on the undrawn amount, not the interest rate
        if re.search(r"(?i)\b(?:unpaid|overdue|past\s+due|after\s+the\s+maturity|on\s+or\s+after\s+the\s+maturity|event\s+of\s+default|"
                     r"default\s+rate|late\s+payment)\b[^.]{0,120}$", s[max(0, m.start() - 160):m.start()]):
            continue                                      # 1.0.4: the rate on overdue amounts, not the debt's rate
        if re.search(r"discount|premium|interest\s+in\s+|%\s+(?:interest\s+)?in\s+|royalty|nsr|stake|ownership|"
                     r"increased\s+from|%\s+to\s+\d|effective\s+interest|fee\b|standby|"
                     r"of\s+the\s+(?:issued|outstanding)|shareholder|equity|stream", ctx) and not re.search(
                         r"per\s+annum|annual|interest\s+(?:at|rate)", ctx):
            continue
        if re.match(r"\s*%?\s*(?:per|a|each)\s+month\b", s[m.end() - 1 if s[m.end() - 1] == "%" else m.end():][:20]) or \
                re.match(r"\s*per\s+month\b", s[m.end():m.end() + 15]):
            return round(v * 12, 4), re.sub(r"\s+", " ", s[m.start():m.end() + 10]).strip()[:60]
        if 0 < v <= 30:
            return v, None
    return None


def _rate(sents, st=None):
    """The first sentence (in the instrument's own order) that states a rate decides it."""
    if st == "amended":
        for s in sents:                                   # 1.0.4: an amendment's new rate ('rate raised to 7.5%')
            m = re.search(r"(?i)\b(?:increas\w*|decreas\w*|reduc\w*|rais\w*|amend\w*|chang\w*|lower\w*|adjust\w*)\s+(?:the\s+)?(?:annual\s+)?"
                          r"(?:interest\s+)?rate\b[^.%]{0,60}?\bto\s+(\d{1,2}(?:\.\d{1,3})?)\s*%|\b(?:interest\s+)?rate\b[^.%]{0,60}?"
                          r"\bfrom\s+\d{1,2}(?:\.\d{1,3})?\s*%\s+to\s+(\d{1,2}(?:\.\d{1,3})?)\s*%", s)
            if m:
                return float(m.group(1) or m.group(2)), None
    for s in sents:
        if _ZERO.search(s):
            return 0.0, None
        m = _FLOAT.search(s)
        if m:
            txt = s[m.start():m.end()]
            return None, re.sub(r"\s+", " ", txt)[:120]
        m = re.search(r"(?i)\b(SOFR|CORRA|CDOR|LIBOR|prime)\b[^.]{0,220}?\band\s+\(ii\)\s+(\d{1,2}(?:\.\d+)?)\s*%", s)
        if m and re.search(r"(?i)\bsum\s+of\b", s[max(0, m.start() - 120):m.start()]):
            return None, "%s + %s%%" % (m.group(1).upper() if m.group(1).lower() != "prime" else "prime", m.group(2))
        f = _fixed_rate(s)
        if f:
            return f
    return None, None


def _conversion(sents, instrument, currency=None):
    if instrument not in ("convertible_debenture", "convertible_note"):
        return None, None
    for s in sents:
        m = _CONVP.search(s)
        if m and re.search(r"(?i)\b(?:floating|discount|minimum|floor|VWAP|volume[\s-]weighted|market\s+price|greater\s+of|lesser\s+of)\b",
                           s[m.start():m.end()]):
            m = None                                      # 1.0.4: a formula with a floor, not a fixed conversion price
        if m:
            v = float(m.group(2))
            par = re.match(r"\s*\(\s*(US|C|CA)\s?\$\s?(\d+(?:\.\d+)?)\s*\)", s[m.end():m.end() + 20])
            if par and currency and _curr(par.group(1)) == currency and _curr(m.group(1)) != currency:
                v = float(par.group(2))
            unit_ctx = s[m.start():min(len(s), m.end() + 200)]
            if re.search(r"(?i)\bper\s+unit\b|\bunits?\b", s[max(0, m.start() - 60):m.end() + 30]) and _UNIT_MULTI.search(
                    " ".join(sents)):
                return None, re.sub(r"\s+", " ", unit_ctx)[:160]
            if 0 < v < 1000:
                return v, None
    for s in sents:
        m = re.search(r"(?i)\b(?:VWAP|volume[\s-]weighted|market\s+price|discount\s+(?:to|of)|equal\s+to\s+the\s+greater)\b", s)
        if m and re.search(r"(?i)convert", s):
            return None, re.sub(r"\s+", " ", s[max(0, m.start() - 80):m.end() + 80])[:160]
    return None, None


def _warrants(sents):
    n, p = None, None
    for s in sents:
        if n is None:
            m = _WARR_N.search(s)
            if m and not re.search(r"(?i)\bbroker|finder|agent|compensation", s[max(0, m.start() - 60):m.end() + 20]):
                n = float(m.group(1).replace(",", ""))
        if p is None:
            m = _WARR_P.search(s)
            if m and not re.search(r"(?i)\bbroker|finder|agent|compensation", s[max(0, m.start() - 80):m.start() + 20]):
                p = float(m.group(2))
    return n, p


def _other_instrument(s, k):
    """1.0.4: '(un)secured' that describes another instrument in the sentence ('the unsecured promissory note' beside
    the convertible loan) says nothing about this one: blank those words out."""
    if not k:
        return s
    own = [(x, y) for x, y, kk in _instruments_in(s) if kk == k]
    for m in re.finditer(r"(?i)\b(?:un)?secured\b", s):
        if any(x <= m.start() < y for x, y in own):
            continue                                      # inside this instrument's own name: 'convertible senior unsecured notes'
        spans = [x for x in _instruments_in(s[m.start():m.start() + 80]) if x[0] <= 30]
        if spans and spans[0][2] != k and not (k == "convertible_debenture" and spans[0][2] == "notes"):
            s = s[:m.start()] + " " * (m.end() - m.start()) + s[m.end():]
    return s


def _secured(sents, k=None):
    yes = no = False
    sents = [_other_instrument(s, k) for s in sents]
    for s in sents[:3]:
        t = re.sub(r"(?i)subordinat\w*\s+(?:in\s+right\s+of\s+payment[^.]{0,60}?\s+)?to\s+[^.]{0,80}", " ", s)
        if re.search(r"(?i)\bunsecured\s+(?:redeemable\s+)?(?:convertible|senior|subordinated|promissory|loans?|notes?|debentures?|bridge|term|"
                     r"obligations)", t):
            return 0.0
    for s in sents:
        s = re.sub(r"(?i)subordinat\w*\s+(?:in\s+right\s+of\s+payment[^.]{0,60}?\s+)?to\s+[^.]{0,80}", " ", s)
        if _SECURED_NO.search(s):
            no = True
        t = _SECURED_NO.sub(" ", s)
        if _SECURED_YES.search(t):
            yes = True
    if no and not yes:
        return 0.0
    if yes and not no:
        return 1.0
    return None


# ------------------------------------------------------------------ the analysis
_MODAL_PRE = re.compile(r"(?i)\b(?:to|will|shall|would|may|might|can|could|must|should|cannot|expects?\s+to|intends?\s+to|"
                        r"plans?\s+to|anticipates?\s+to)\s+(?:not\s+)?(?:be\s+|have\s+been\s+)?(?:(?:fully|first|also|then|only|"
                        r"subsequently|immediately|further|partially|partly|initially|automatically)\s+)?$")
_AGREED_PRE = re.compile(r"(?i)\b(?:agreed|agrees|agree|agreement|elected|elects|election|decided|resolved|determined|approved|"
                         r"proceeded|continue[ds]?)\s+(?:\w+\s+){0,2}?to\s+(?:be\s+)?$")
_OPTION_PRE = re.compile(r"(?i)(?:\b(?:right|option|entitled|ability|may|can|could|might|permitted|allowed|elect|able|discretion)\s+"
                         r"(?:\w+\s+){0,4}?(?:to\s+)?(?:be\s+)?|\bin\s+order\s+to\s+|\bprior\s+to\s+(?:the\s+)?|\bupon\s+|"
                         r"\bprovides?\s+for\s+(?:an?\s+|the\s+)?|"
                         r"\bvoluntary\s+)$")
_PAST_USE = re.compile(r"(?i)(?:\b(?:was|were|been|being|is|are|has|have|had)\s+(?:\w+\s+)?(?:used|utili[sz]ed|applied)|(?<!will\s)"
                       r"(?<!to\s)(?<!be\s)(?<!would\s)(?<!shall\s)(?<!and\s)\b(?:used|utili[sz]ed))\b[^.;]{0,130}\bto\s+(?:fully\s+)?$")
                       # FIX3: 'proceeds ... were utilized to repay debt as follows'
_FUTURE_USE = re.compile(r"(?i)\b(?:will|shall|would|intends?|intended|plans?|planned|expects?|expected|anticipat\w*|to\s+be|are\s+to|"
                         r"is\s+to)\b[^.;]{0,60}\b(?:use[ds]?|appl(?:y|ied)|proceeds|allocated)\b[^.;]{0,60}\bto\s+(?:be\s+)?(?:\w+\s+)?$|"
                         r"\buse\s+of\s+(?:the\s+)?(?:net\s+)?proceeds\b[^.;]{0,80}$")


def _not_happening(st, m, s):
    """1.0.4: a stage cue that states a future, an option or a term, not an event: 'will be issued', 'is expected to
    close', 'has the right to repay', 'may be converted', 'proceeds will be used to repay'. An agreed act ('has agreed
    to extend', 'elected to convert') and a settlement ('proposes to settle debt for shares') still count."""
    if st == "proposed":
        return False
    pre = s[max(0, m.start() - 60):m.start()]
    word = m.group(0).lower()
    if _AGREED_PRE.search(pre):
        return False
    if st == "repaid":
        if re.match(r"settl|shares?[\s-]+for|for\s+debt|debt\s+settle|extinguish|tender", word):
            return False
        if re.match(r"(?i)\s*(?:options?|rights?|premium|fees?|penalt\w+|features?|provisions?|clauses?|terms?|schedule)\b",
                    s[m.end():m.end() + 20]):
            return True                                   # 'an early repayment option', 'redemption premium'
        wide = s[max(0, m.start() - 160):m.start()]
        if _PAST_USE.search(wide) and not _FUTURE_USE.search(wide):
            return False                                  # 'is being used to repay', 'used part of the proceeds to repay'
        return bool(_MODAL_PRE.search(pre) or _OPTION_PRE.search(pre) or _FUTURE_USE.search(wide))
    if st in ("amended",):
        return bool(re.search(r"(?i)\b(?:right|option|entitled|may|can|could|might|permitted|allowed)\s+(?:\w+\s+){0,3}?(?:to\s+)?"
                              r"(?:be\s+)?$", pre))
    if st in ("closed", "drawn", "converted", "terminated", "signed"):
        if _MODAL_PRE.search(pre):
            return True
        if st in ("converted", "drawn", "terminated") and re.search(
                r"(?i)\b(?:right|option|entitled|may|can|could|might|permitted|allowed|elect|able)\s+(?:\w+\s+){0,3}?(?:to\s+)?"
                r"(?:be\s+)?$|\bprovides?\s+for\s+(?:an?\s+|the\s+)?$", pre):
            return True
    return False


def _stage_hits(s, around=None, window=None):
    """[(stage, distance, pos)] of every stage cue in s; with 'window', only cues within that many characters of
    'around'."""
    hits, nouns = [], []
    for st, rx in _STAGE_TESTS:
        for m in rx.finditer(s):
            if _not_happening(st, m, s):
                continue                                  # 1.0.4: 'will be issued', 'the right to repay', 'may convert'
            d = abs(m.start() - around) if around is not None else m.start()
            btw = s[min(m.start(), around):max(m.end(), around)] if around is not None else ""
            lst = re.search(r":\s*[-\u2013\u2022]\s", btw) if around is not None and m.start() < around else None
            if lst:                                       # FIX3: 'repaid debt as follows: - A of $X - B of $Y': each
                d = abs(m.start() - (min(m.start(), around) + lst.start()))   # list item takes the verb before the colon
                btw = re.sub(r"\s[-\u2013\u2022]\s", " ", btw)
            if window is not None and d > window:
                continue
            if around is not None and m.start() > around:
                d += 15                                   # a headline's verb comes before what it acts on
            if st == "proposed" and re.match(r"(?i)up\s+to\b", m.group(0)):
                d += 150                                  # 1.0.4: 'up to US$' sizes a facility or accordion; weak
            if around is not None and _CLAUSE_BREAK.search(btw):
                continue                                  # a headline's other clause: 'Closes X and Announces Y'
            hits.append((st, d, m.start()))
            if st == "proposed" and _NOUN_OFFER.match(m.group(0)):
                nouns.append(m.start())
    # 'Completes $7.5M Private Placement of ...', 'Pricing of Upsized Offering of ...': the offering is what the
    # verb acts on, not a proposal of its own
    if nouns:
        acts = [p for st, d, p in hits if st in ("closed", "signed")]
        drop = {q for q in nouns if any(p < q and not _CLAUSE_BREAK.search(s[p:q]) for p in acts)}
        hits = [x for x in hits if not (x[0] == "proposed" and x[2] in drop)]
    return hits


_ORDER = ["terminated", "converted", "repaid", "amended", "drawn", "closed", "signed", "proposed"]


def _pick_stage(hits, nearest=False):
    if not hits:
        return None
    by = {}
    for st, d, p in hits:
        by[st] = min(d, by.get(st, 10 ** 6))
    present = [st for st in _ORDER if st in by]
    if nearest:
        # a headline says one thing about each instrument: the cue nearest it, the stronger one on a near tie
        best = min(by.values())
        close = [st for st in present if by[st] <= best + 6]
        if "proposed" in close and len(close) > 1 and set(close) <= {"proposed", "signed", "closed"}:
            if "closed" in close and by["closed"] <= by["proposed"]:
                return "closed"
            return "signed" if "signed" in close and by["signed"] < by["proposed"] else "proposed"
        return close[0]
    if "proposed" in present and len(present) > 1 and set(present) <= {"proposed", "signed", "closed"}:
        if "closed" in present and by["closed"] <= by["proposed"] + 60:
            return "closed"
        if "signed" in present and by["signed"] < by["proposed"]:
            return "signed"
        return "proposed"
    return present[0]


_GENERIC_HL = re.compile(r"(?i)^\s*(?:news\s+release|press\s+release|news|release|media\s+release|nr)?\s*[-:.]?\s*$")
_WEAK_CLOSE = re.compile(r"(?i)\bsecures\b|\bsecured\s+(?:a|an|the|its|(?:US|C|CA)?\$|funding|financing|additional|new|up\s+to|"
                         r"commitments?)\b|\bobtain(?:s|ed)\b|\barrang(?:es|ed)\b|\bestablish(?:es|ed)\b")   # 1.0.4: not the adjective
_REAL_CLOSE = re.compile(r"(?i)\bdrew\b|\bhas\s+(?:been\s+)?drawn\b|\bdrawn\s+down\b|(?<!from\sthe\s)(?<!after\sthe\s)(?<!following\sthe\s)"
                         r"\b(?:initial|first)\s+(?:draw|drawdown|advance)\b(?![^.]{0,60}\b(?:is\s+to\s+be|will\s+be|shall\s+be|expected|"
                         r"to\s+be\s+made))|"
                         r"\bdrawdowns?\s+(?:of|from|under)\b|\bdraw\s+down\s+(?:of|under|from)\b|(?<!be\s)\bfunded\b|(?<!be\s)(?<!well\s)\badvanced\b(?=\s+(?:to|under|by|on|the|a|an|(?:US|C|CA)?\$|in|as|funds)\b)|"
                         r"\b(?:has|have|had|was|were|been)\s+advanced\b(?!\s+(?:stage|exploration|development|discussions?|"
                         r"negotiations?|towards?))|\badvances\s+previously\s+made\b|"
                         r"\b(?:has|have|had)\s+provided\s+(?:US|C|CA|Cdn)?\$\s?[\d.,]+\d|"
                         r"\bconcurrent\s+with\s+the\s+closing\s+of\s+the\b|\breceived\s+(?:the\s+)?(?:\w+\s+)?"
                         r"(?:funds|proceeds|first)|\bclos(?:ed|ing)\s+of\s+the\s+(?:loan|facility|financing)|\bhas\s+closed\b|"
                         r"\bfinancial\s+close\b|\bproceeds\s+of\s+the\s+(?:loan|facility)\s+(?:were|have\s+been)\b")
# FIX3: 'advanced' as progress ('which is well advanced and', 'has advanced development') is not money advanced
_GENERIC_DEB = re.compile(r"(?i)\bdebentures?\b(?!holder)|\bdebentureholders?\b")
_GENERIC_DEBT = re.compile(r"(?i)\b(?:senior\s+(?:secured\s+)?debt|secured\s+debt|debt\s+(?:financing|facility|settlement|"
                           r"restructuring|repayment)|(?:repayment|restructur\w*|settle\w*)\s+(?:of\s+)?(?:the\s+|its\s+|certain\s+)?"
                           r"(?:outstanding\s+)?debt|debt\s+owe[ds]|debts?\s+owing|indebtedness\s+ow(?:ed|ing)|project\s+debt|"
                           # 1.0.4: 'Shares for Debt', 'Debt Conversion', 'Reduces Debt', 'Interest Debt', 'Debt Extension'
                           r"shares?[\s-]+for[\s-]+(?:\w+\s+and\s+)?debt|debt[\s-]+for[\s-]+shares|debt\s+(?:conversions?|reduction|extension|"
                           r"settlements?)|conversion\s+of\s+(?:\w+\s+)?debt|interest\s+(?:debt|indebtedness)|(?:reduces?|reducing|"
                           r"eliminat\w+|extinguish\w*|retir\w+)\s+(?:\w+\s+){0,3}?debt|debt[\s-]free|debt\s+reorgani[sz]ation|"
                           r"reorgani[sz]ation\s+of\s+(?:\w+\s+){0,2}debt)\b")
_GENERIC_CONV = re.compile(r"(?i)(?<!non-)(?<!non\s)\bconvertible\s+(?:debt(?:\s+(?:financing|units?|private\s+placement))?|"
                           r"securities|financing|units?)\b")                  # 1.0.4: resolved to the release's own word
_HL_NOTE = re.compile(r"(?:\$\s?[\d.,]+\s*(?:[Mm]illion|MILLION|M)?\s+|\b(?:[Oo]f|OF|[Tt]he|THE)\s+)(?:Notes?|NOTES?)\b(?!\s*:)")
_TRANCHE = re.compile(r"(?i)\btranches?\b")
_CANCEL_FOR_SHARES = re.compile(r"(?i)\bcancel\w*\s+(?:the\s+)?(?:US\$|C\$|\$)?[\d.,]*\s*(?:million\s+)?(?:face\s+value\s+of\s+)?"
                                r"(?:the\s+)?(?:senior\s+)?(?:secured\s+)?(?:loan|debt|debentures?|notes?)|\bin\s+exchange\s+for\b"
                                r"[^.]{0,80}\bshares\b|\bsatisf\w+\s+(?:in\s+full\s+)?(?:through|by)\s+(?:the\s+)?(?:\w+\s+){0,2}issu\w+\s+(?:of\s+)?"
                                r"[^;]{0,50}?shares")
_INTEREST_ONLY_HL = re.compile(r"(?i)\binterest\s+(?:conversion|payment)\s+(?:election|deadline|obligation)|\bdeadline\b[^.]{0,80}"
                               r"\binterest|\binterest\s+(?:payment|conversion)\b|\bpay(?:s|ment\s+of)?\s+(?:debenture\s+)?interest\b|"
                               r"\binterest\s+(?:shares|payable)\b|\bshares\s+(?:issued\s+)?for\s+interest\b")


def _real_close(txt):
    """A funding that happened: not 'three years from the initial drawdown', not 'is to be made on closing'."""
    for m in _REAL_CLOSE.finditer(txt):
        if re.search(r"(?i)\b(?:from|after|following|upon|until|before|of)\s+(?:the\s+)?(?:date\s+of\s+(?:the\s+)?)?(?:\w+\s+)?$",
                     txt[max(0, m.start() - 30):m.start()]):
            continue
        if re.search(r"(?i)^[^.]{0,60}\b(?:is\s+to\s+be|will\s+be|shall\s+be|expected|to\s+be\s+made|anticipated|will\s+occur|"
                     r"to\s+occur|is\s+scheduled|will)\b", txt[m.end():m.end() + 70]):
            continue
        if re.search(r"(?i)^[^.]{0,40}?\b(?:is|are|remains?)\s+(?:still\s+)?(?:subject\s+to|conditional\s+(?:on|upon))\b",
                                       txt[m.end():m.end() + 60]):
            continue                                      # FIX5: 'The closing of the Loan is subject to ... conditions'
        if re.search(r"(?i)\b(?:expects?|expected|anticipat\w+|intends?|will|shall|plans?|scheduled|subject\s+to|conditional\s+on)\b"
                     r"[^.;]{0,90}$", txt[max(0, m.start() - 100):m.start()]):
            continue                                      # 1.0.4: 'expects that closing and the first drawdown will occur'
        if re.search(r"(?i)\b(?:toward|towards|to\s+reach|reaching|to\s+achieve|achieving|path\s+to)\b[^.;]{0,90}$",
                     txt[max(0, m.start() - 100):m.start()]):
            continue                                      # FIX3: 'a step toward a fully funded ...', 'to reach financial close'
        if not re.match(r"(?i)concurrent", m.group(0)) and \
                re.search(r"(?i)\b(?:existing|previous(?:ly)?|prior(?!\s+to)|earlier|original(?:ly)?|in\s+addition\s+to)\b(?:[^.;]|\.(?=\d)){0,120}$",
                          txt[max(0, m.start() - 130):m.start()]):
            continue                                      # 1.0.4: an earlier facility's funding (not 'concurrent with the
                                                          # closing of the' new one, whatever old facility precedes it)
        return True
    return False


def _kind_mentions(h, sents, upto):
    """{kind: [(sentence index or -1 for the headline, position)]}, with generic words ('debentures', 'debt') set
    aside as '?deb' and '?debt' for the release to resolve."""
    per = {}

    def add(i, t):
        spans = _instruments_in(t)
        for a, e, k in spans:
            per.setdefault(k, []).append((i, a))
        for m in _GENERIC_DEB.finditer(t):
            if not any(a <= m.start() < e for a, e, _k in spans):
                per.setdefault("?deb", []).append((i, m.start()))
        for m in _GENERIC_DEBT.finditer(t):
            if not any(a <= m.start() < e for a, e, _k in spans):
                per.setdefault("?debt", []).append((i, m.start()))
        for m in _GENERIC_CONV.finditer(t):
            if not any(a <= m.start() < e for a, e, _k in spans):
                per.setdefault("?conv", []).append((i, m.start()))
        if i == -1:
            for m in _HL_NOTE.finditer(t):             # 1.0.4: a headline 'Note' the body names ('Conversion of $9M Note')
                if not any(a <= m.start() < e for a, e, _k in spans):
                    per.setdefault("?debt", []).append((i, m.start()))
    add(-1, h)
    for i, t in enumerate(sents[:upto]):
        add(i, t)
    return per


def _resolve(per, sents, h):
    specific = [k for k in INSTRUMENTS if k in per]
    first = sorted(((min(i if i >= 0 else -1 for i, a in per[k]), k) for k in specific), key=lambda x: (x[0], INSTRUMENTS.index(x[1])))
    if "?deb" in per:
        conv = any(re.search(r"(?i)\bconvertib|convert(?:ed)?\s+(?:into|the)", (h if i == -1 else sents[i]))
                   for i, a in per["?deb"]) or "convertible_debenture" in per
        nonconv = any(re.search(r"(?i)\bnon-convertible", (h if i == -1 else sents[i])) for i, a in per["?deb"]) or \
            re.search(r"(?i)\bnon-convertible\s+debentures?", " ".join(sents[:12]))
        tgt = "notes" if nonconv and not "convertible_debenture" in per else ("convertible_debenture" if conv else "notes")
        if nonconv:
            per.pop("convertible_debenture", None)
        per.setdefault(tgt, []).extend(per.pop("?deb"))
    if "?conv" in per:
        # 1.0.4: 'Convertible Debt Units', 'Convertible Securities': the release's own word for the instrument
        if "convertible_debenture" in per:
            tgt = "convertible_debenture"
        elif "convertible_note" in per:
            tgt = "convertible_note"
        else:
            tgt = "convertible_debenture" if re.search(r"(?i)\bdebentures?\b", h + " " + " ".join(sents[:12])) else \
                "convertible_note"
        per.setdefault(tgt, []).extend(per.pop("?conv"))
    generic_debt = per.pop("?debt", None)             # 1.0.4: resolved last, onto the instrument as finally named
    # 'the Debenture Offering' of a convertible debenture is that debenture, not a second (non-convertible) one
    if "notes" in per and "convertible_debenture" in per and not re.search(r"(?i)\bnon-convertible", h + " " + " ".join(sents[:12])):
        txt = lambda i, a: (h if i == -1 else sents[i])[a:a + 45]
        debish = [(i, a) for i, a in per["notes"] if re.search(r"(?i)debenture", txt(i, a)) and
                  not re.search(r"(?i)\bnotes?\b|\bbonds?\b|\bsenior\b", txt(i, a))]
        if debish:
            per["convertible_debenture"] += debish
            per["notes"] = [x for x in per["notes"] if x not in debish]
            if not per["notes"]:
                per.pop("notes")
    # one instrument called two things: keep the name it is given first -- except a headline 'Notes' the lead only
    # ever calls debentures (the release's own word for it)
    if "convertible_note" in per and "convertible_debenture" in per and \
            all(i == -1 for i, a in per["convertible_note"]) and any(0 <= i <= 1 for i, a in per["convertible_debenture"]):
        per["convertible_debenture"] += per.pop("convertible_note")
    if "convertible_note" in per and "convertible_debenture" in per:
        fn = min((i, a) for i, a in per["convertible_note"])
        fd = min((i, a) for i, a in per["convertible_debenture"])
        keep, drop = ("convertible_note", "convertible_debenture") if fn < fd else ("convertible_debenture", "convertible_note")
        per[keep] += per.pop(drop)
    for spec in ("gold_loan", "prepayment", "credit_facility", "convertible_note", "convertible_debenture", "notes"):
        if "loan" in per and spec in per and not any(i == -1 for i, a in per["loan"]):
            txt = lambda i, a: (h if i == -1 else sents[i])
            # 1.0.4: 'the Convertible Loan ... the outstanding loan' is one instrument, unless the release names a
            # loan of another kind
            conv_loan = spec == "convertible_note" and any(re.match(r"(?i)\S+\s+(?:[\w-]+\s+){0,3}?loans?\b", txt(i, a)[a:a + 60])
                                                           for i, a in per[spec]) and \
                not any(re.search(r"(?i)\b(?:bridge|term|shareholder|related[\s-]party|government|promissory|separate|"
                                  r"short[\s-]term)\s+(?:\w+\s+)?$", txt(i, a)[max(0, a - 30):a]) or
                        re.match(r"(?i)promissory", txt(i, a)[a:a + 12]) for i, a in per["loan"])
            if spec in ("convertible_note", "convertible_debenture", "notes") and not conv_loan and not all(
                    re.search(r"(?i)convertib|debenture|note", txt(i, a)) for i, a in per["loan"]):
                continue
            per[spec] += per.pop("loan")
    # a headline 'Loan Facility' the body calls 'the Financing Facility' or 'Credit Facility' stays one loan
    if "loan" in per and "credit_facility" in per and any(i == -1 for i, a in per["loan"]) and \
            not any(i == -1 for i, a in per["credit_facility"]) and re.search(r"(?i)\bloan\s+facilit", h) and \
            not any(i > 1 for i, a in per["loan"]):
        per["loan"] += per.pop("credit_facility")
    # a headline 'loan' that the body calls a convertible note, a prepayment or a gold loan is that
    if "loan" in per and any(i == -1 for i, a in per["loan"]):
        hn = re.search(r"(?i)promissory\s+note|loan", h[min(a for i, a in per["loan"] if i == -1):])
        hn = hn.group(0).lower().split()[-1] if hn else "loan"
        body_spec = [k for k in ("convertible_note", "gold_loan", "prepayment") if k in per and not any(
            i == -1 for i, a in per[k]) and any(0 <= i <= 3 or 0 <= i <= 12 and hn in sents[i][a:a + 50].lower()
                                                for i, a in per[k])]  # 1.0.4: 'Issues Promissory Note' = the body's convertible note
        if len(body_spec) == 1 and not re.search(r"(?i)\bloans\b|\band\s+(?!(?:converts?|repays?|extends?|amends?|closes?|settles?|"
                                                 r"announces?|enters?|secures?|increases?)\b)[^.]{0,30}\bloan", h):
            per[body_spec[0]] += per.pop("loan")
        elif body_spec == ["convertible_note"] and re.search(r"(?i)\bconversion\s+(?:feature|right|option)|\bconvertible\b", h):
            per["convertible_note"] += per.pop("loan")    # 'Amends Loan Facility with a Conversion Feature'
    # 1.0.4: a headline 'Debt Facility' the lead names as a pre-payment facility or gold loan is that instrument
    if "credit_facility" in per and all(i == -1 or i >= 2 for i, a in per["credit_facility"]) and \
            any(i == -1 and re.match(r"(?i)(?:debt|financing|funding)\s+facilit", h[a:a + 30]) for i, a in per["credit_facility"]):
        lead_kind = [k for k in ("prepayment", "gold_loan") if k in per and any(0 <= i <= 1 for i, a in per[k])]
        if len(lead_kind) == 1:
            per[lead_kind[0]] += per.pop("credit_facility")
    if generic_debt:
        now = sorted(((min(i for i, a in per[k]), INSTRUMENTS.index(k), k) for k in per if k in INSTRUMENTS))
        per.setdefault(now[0][2] if now else "loan", []).extend(generic_debt)
    return per


def _is_background(s):
    return bool(_BACKGROUND.search(s)) and not re.search(r"(?i)\b(?:today|now|has\s+(?:closed|completed|repaid|entered|"
                                                         r"received|issued|priced)|is\s+pleased)\b", s)


def analyse(headline, body):
    h, b, about = _prepare(headline, body)
    res = {"rows": [], "reason": None}
    main = b[:about] if about else b
    sents = _sentences(main)
    if _GENERIC_HL.match(h) and sents:
        h = sents[0][:300]
    if _PROMO.search(h) or _PROMO.search(b[:400]):
        res["reason"] = "promotional article"
        return res
    self_rx = _self_rx(h, b)
    lead = " ".join(sents[:4])
    results = bool(_RESULTS_HL.search(h))
    per = _kind_mentions(h, sents, 7 if results else 40)
    if not per:
        res["reason"] = "no debt instrument"
        return res
    hl_debt = any(i == -1 for v in per.values() for i, a in v)
    if not hl_debt and not re.search(r"(?i)\b(?:loans?|debentures?|credit|debt|notes?|facility|convertible|prepay\w*|bonds?)\b", h):
        if not any(0 <= i <= 2 for v in per.values() for i, a in v):
            res["reason"] = "debt not the news"
            return res
    if _MANDATE.search(h) and not re.search(r"(?i)\b(?:clos|sign|enter|secur)\w*\b[^.]{0,40}\b(?:loan|facility)", h):
        res["reason"] = "advisor mandate"
        return res
    if _OTHER_CO_LOAN.search(h + " " + lead) and not re.search(r"(?i)\bthe\s+Company\s+(?:has\s+)?(?:received|secured|entered)", lead):
        res["reason"] = "another company's loan"
        return res
    if re.search(r"(?i)\bdeadline\b[^.]{0,120}\binterest|\binterest\s+(?:conversion|payment)\s+election", h):
        res["reason"] = "interest paid in shares"
        return res
    if _INTEREST_ONLY_HL.search(h) and _INTEREST_UNPAID.search(h + " " + lead):
        res["reason"] = "interest not paid"               # 1.0.4: deferred, missed or in default: nothing was paid
        return res
    if _INTEREST_ONLY_HL.search(h) and not re.search(
            r"(?i)\b(?:clos\w*|issu\w*\s+(?:of\s+)?(?:US|C)?\$|repa\w*\s+(?:of\s+)?(?:the\s+)?(?:US|C)?\$|convert\w*\s+(?:of\s+)?"
            r"(?:US|C)?\$|extend\w*|amend\w*|tranche|financing|offering|placement|reduc\w*|redeem\w*|redemption|retir\w*|"
            r"conversion\s+of|repa(?:y|id|ys|yment)\s+of)", _INTEREST_ONLY_HL.sub(" ", h)):
        # rule DI (changed by Justin 2026-09-24): an interest payment is a row of its own, stage interest_paid
        res["rows"] = [_interest_row(h, sents, per, self_rx, _body_currency(h, b))]
        res["reason"] = "interest paid"
        return res
    holder_only = [a for i, a in per.get("?deb", []) if i == -1 and re.match(r"(?i)debenture-?holders?", h[a:a + 20])]
    if holder_only and not any(i == -1 for k, v in per.items() if k != "?deb" for i, a in v):
        ev = [st for a in holder_only for st, d, p in _stage_hits(h, around=a, window=60)
              if st in ("amended", "converted", "repaid", "terminated")]
        if not ev:
            res["reason"] = "debt not the news"
            return res
    if "?debt" in per and not any(not k.startswith("?") or k in ("?deb", "?conv") for k in per) and re.search(
            r"(?i)\bsettle\w*\s+(?:\w+\s+){0,3}(?:debt|indebtedness)\b[^.]{0,160}\bshares\b|\bshares?\s+for\s+debt\b|"
            r"\bdebt\s+settlement\b|\bsettlement\s+of\s+(?:\w+\s+){0,2}debt\b|\bdebt\s+settlements\b|\bshares?[\s-]+for[\s-]+debt\b|"
            r"\bdebt[\s-]+for[\s-]+shares\b", h + " " + lead):
        res["reason"] = "shares for unnamed debt (rule DS)"
        return res
    if _WAIVER_HL.search(h) and not re.search(
            r"(?i)\b(?:amend\w*|extension\s+of\s+(?:the\s+)?maturity|repa\w+|clos\w+|complet\w+|convert(?:s|ed|ing)?\b|"
            r"conversion|settle\w*|draw\w*|new|additional)\b",
            _WAIVER_HL.sub(" ", h)):
        res["reason"] = "covenant waiver or forbearance"          # 1.0.2: not a row (label guide, item 48)
        return res
    def _in_headline(i, a):
        if i == -1:
            return True                                   # (or the body's full copy of a cut-off headline)
        p0 = sents[i].find(h[:40]) if 0 <= i <= 2 and len(h) >= 40 else -1
        return p0 >= 0 and p0 <= a <= p0 + len(h) + 40
    lender_hl = re.search(r"(?i)\bletters?\s+of\s+interest\b|\bLOI\b[^.]{0,40}\b(?:EXIM|Export|EDC|UKEF|KfW|bank|lenders?)\b|"
                          r"\bterm\s+sheet\b|\b(?:debt|project|loan|credit)\s+(?:financing|facility|package)\b|\bexport\s+credit\b|"
                          r"\bEXIM\b|\bExport[\s-]Import\b|\bExport\s+Development\b|"
                          # FIX3: 'Debt Commitment Letter', 'Support Letter ... From Leading Financial Institution'
                          r"\b(?:commitment|support)\s+letters?\b|\bletters?\s+of\s+support\b|\bfinancial\s+institution\b", h)
    weak_conv = all(re.match(r"(?i)convertible\s+securities", (h if i == -1 else sents[i])[a:a + 30]) for i, a in per.get("?conv", []))
    if all(k == "?debt" or k == "?conv" and weak_conv for k in per) and \
            not any(_in_headline(i, a) or lender_hl and 0 <= i <= 6 for v in per.values() for i, a in v):
        res["reason"] = "debt only in passing"          # 1.0.4: only 'debt settlement' or 'convertible securities' in boilerplate
        return res
    per = _resolve(per, sents, h)
    per = {k: v for k, v in per.items() if not k.startswith("?")}
    own_loans = [(i, a) for i, a in per.get("loan", []) if _I_LOAN.match(h if i == -1 else sents[i], a)]
    if own_loans and _SETTLE_HL.search(h) and all(_lumped_loan(h if i == -1 else sents[i], a) for i, a in own_loans):
        per.pop("loan")                                   # 1.0.4 (rule DS): 'management fees and loans' settled in shares
        if not per:
            res["reason"] = "shares for fees and payables (rule DS)"
            return res
    if not per:
        res["reason"] = "no debt instrument"
        return res
    kinds = [k for k in INSTRUMENTS if k in per and any(i == -1 for i, a in per[k])]
    if len(kinds) > 1:
        # 1.0.4: 'Notes Offering to Refinance the Project Facility': the facility is the use of proceeds, not a row
        used = [k for k in kinds if all(_USE_OF_PROCEEDS.search(h[max(0, a - 90):a].rstrip() + " ") for i, a in per[k] if i == -1)]
        if used and len(used) < len(kinds):
            kinds = [k for k in kinds if k not in used]
    if not kinds:
        kinds = [k for k in INSTRUMENTS if k in per and any(0 <= i <= 2 and not _is_background(sents[i]) for i, a in per[k])]
    if not kinds:
        k0 = min(per, key=lambda k: min(i for i, a in per[k]))
        if min(i for i, a in per[k0]) > 6 or results or _EQUITY_HL.search(h):
            res["reason"] = "debt only in passing"
            return res
        kinds = [k0]
    cur_default = _body_currency(h, b)
    rows = []
    for k in kinds:
        own = " ".join(sents[i] for i in sorted({i for i, a in per[k] if 0 <= i <= 24})[:4])
        # FIX3: only a facility can be an equity draw-down look-alike (not 'promissory notes' beside one), and a
        # facility whose own terms carry interest ('The Facility will bear interest at 10%') is a loan
        fac_word = any(re.search(r"(?i)facilit|\blines?\b|revolv", (h if i == -1 else sents[i])[a:a + 45]) for i, a in per[k])
        if k in ("credit_facility", "loan") and fac_word and _EQUITY_FAC.search(h + " " + own + " " + " ".join(sents[:4])) and \
                not re.search(r"(?i)\binterest\b|\bper\s+annum\b|\brepay", own + " " + " ".join(_context(k, per[k], h, sents)[:6])):
            res["reason"] = "equity draw-down facility"   # 1.0.4: units issued on each draw are equity, not debt
            continue
        st = _stage_for(k, per[k], h, sents)
        if st is None:
            continue
        if st == "interest-only":
            rows.append(_interest_row(h, sents, {k: per[k]}, self_rx, cur_default))
            continue
        side = _side(h, sents, per[k], self_rx)
        k2 = k
        if k == "loan" and _CONV_FEATURE.search(" ".join(_context(k, per[k], h, sents)[:10])):
            k2 = "convertible_note"                       # 1.0.4: a loan the lender may convert is a convertible loan
        rows.append(_fill_row(k2, st, side, h, sents, per[k], self_rx, cur_default))
    rows += _extra_rows(h, sents, per, rows, self_rx, cur_default)
    if re.search(r"(?i)\btender\s+offer", h) and not _TENDER_DONE.search(h) and \
            not _TENDER_DONE_BODY.search(" ".join(sents[:8])):
        rows = [r for r in rows if r["stage"] != "repaid"]    # 1.0.2: launched or extended, nothing bought yet
        if not rows:
            res["reason"] = "tender offer not yet settled"
    if results:
        rows = [r for r in rows if not (r["stage"] == "repaid" and not r.get("principal") and not r.get("lender"))]
    for r in rows:
        if r["side"] == "lender" and r["stage"] == "repaid" and re.search(r"(?i)\b(?:offer|bid)\b", h) and \
                not _TENDER_DONE.search(h):
            r["stage"] = "proposed"                       # 1.0.4: an open offer to buy another issuer's debt
    # 1.0.4 (rule DI): a headline that reports both an event on the debt and an interest payment on it gives both rows
    if rows and (_INT_SETTLE_HL.search(h) or _INTEREST_ONLY_HL.search(h)) and not _INTEREST_UNPAID.search(h) and \
            not any(r["stage"] == "interest_paid" for r in rows) and rows[0]["side"] == "borrower" and \
            rows[0]["stage"] in ("repaid", "converted", "amended"):
        ir = _interest_row(h, sents, {rows[0]["instrument"]: []}, self_rx, cur_default)
        ir["instrument"] = rows[0]["instrument"]
        ir["lender"] = rows[0].get("lender") or ir["lender"]
        rows.append(ir)
    # one instrument read twice under two names: the same side, stage and amount is one row
    kept = []
    for r in rows:
        if r["principal"] and any(q["side"] == r["side"] and q["stage"] == r["stage"] and q["principal"] and
                                  abs(q["principal"] - r["principal"]) <= 0.005 * r["principal"] for q in kept):
            continue
        kept.append(r)
    rows = kept
    if rows and all(r["side"] == "borrower" for r in rows):
        m = re.search(r"(?i)\bused\s+for\s+a\s+bridge\s+loan\s+to\s+([A-Z][\w&.,\s]{2,60}?)(?:\s+and\b|[.,;])", main)
        if m:
            bor = _org_clean(m.group(1), self_rx)
            rows.append(dict(_empty(), instrument="loan", stage="proposed", side="lender", borrower=bor,
                             currency=rows[0].get("currency"), related_party=0.0,
                             purpose="bridge loan from the proceeds"))
    res["rows"] = rows
    if not rows and not res["reason"]:
        res["reason"] = "no stage"
    return res


_INTEREST_UNPAID = re.compile(r"(?i)\b(?:not|unable\s+to|did\s+not|failed\s+to|will\s+not|cannot)\s+(?:be\s+)?(?:make|made|pay|paid)\b|"
                              r"\bdefer(?:s|red|ral|ring)?\b|\bnon-?payment\b|\bmissed\b|\bin\s+default\b|\bremains?\s+unpaid\b")
_EQUITY_FAC = re.compile(r"(?i)\bequity\s+(?:financing\s+|draw-?down\s+|investment\s+|line\s+)?(?:facility|line)\b|\bdraw-?down\s+equity\b|"
                         r"\bequity\s+(?:private\s+placement\s+)?tranches\b|\bdraw\s*-?\s*down\b[^.]{0,80}\b(?:equity|units|common\s+shares)\b|"
                         r"\b(?:units|shares)\b[^.]{0,60}\b(?:each|every|upon\s+(?:each|a))\s+(?:draw|drawdown|draw-down|tranche)\b")
_EQUITY_HL = re.compile(r"(?i)\bsubscription\s+receipts?\b|\bflow[\s-]through\b|\bbought\s+deal\b|\brights\s+offering\b|\bshare\s+capital\b|"
                        r"\bvoting\s+rights\b")
_WAIVER_HL = re.compile(r"(?i)(?:\b(?:signs?|signed|extends?|extended|grants?|granted|obtains?|obtained|receives?|received|"
                        r"announces?|enters?\s+into)\s+(?:an?\s+|the\s+)?(?:[\w-]+\s+){0,2}?)?(?:\bforbear\w*|\bforebear\w*|"
                        r"\bwaiv\w*\b[^.]{0,40}?\bcovenants?\b|\bcovenants?\b[^.]{0,40}?\bwaiv\w*|\bwaiver\s+agreement\b)(?:\s+agreement)?")
_TENDER_DONE = re.compile(r"(?i)\bresults?\b|\bcomplet\w*|\bsettle(?:d|s)\b|\bsettlement\b(?!\s+date)|\bexpir\w+\s+and\b|"
                          r"\bfinal\b|\bpurchased\b|\baccept\w*\b|\bcancell?(?:ation|ed)\b|\bdischarge\w*|\bfollowing\s+(?:the\s+)?tender")
_TENDER_DONE_BODY = re.compile(r"(?i)\b(?:has|have)\s+(?:been\s+)?(?:accepted\s+for\s+purchase|purchased)\b|\bwere\s+"
                               r"(?:validly\s+tendered\s+and\s+)?accepted\b|\belected\s+to\s+(?:exercise\s+its\s+right\s+to\s+)?"
                               r"make\s+payment\b|\bhas\s+completed\s+(?:the|its)\s+(?:previously\s+announced\s+)?(?:cash\s+)?tender")


_COMMIT = re.compile(r"(?i)\bcommitment\s+letters?\b|\b(?:internal\s+|final\s+)?credit\s+(?:committee\s+)?approvals?\b|\bterm[\s-]?sheets?\b|"
                     r"\bletters?\s+of\s+(?:intent|interest|support)\b|\bproject\s+letter\b|\b(?:engagement|mandate)\s+letters?\b|"
                     r"\bconditional\s+commitment\b|\b(?:debt|loan|financing)\s+commitments?\b|\bindicative\b|"
                     r"\bcontemplated\b(?!\s+(?:\w+\s+)?(?:transactions?|acquisitions?|mergers?|business\s+combinations?|"
                     r"arrangements?|amalgamations?|take-?overs?|purchases?|sales?|dispositions?|reverse\s+takeovers?))|"
                     r"\bnon-binding\b|\bunderwritten\s+commitment|\bfully\s+(?:committed|underwritten)\b|"
                     r"\bsubject\s+to\s+(?:the\s+)?(?:negotiation|execution|completion|finali[sz]ation|settlement)\s+of\s+"
                     r"(?:the\s+|a\s+)?(?:definitive|final|long[\s-]form)|\bsubject\s+to\s+(?:the\s+)?(?:definitive|final|closing|"
                     r"long[\s-]form|loan)\s+(?:loan\s+)?(?:documentation|documents|agreements?)\b|\bsubject\s+to\s+[^.]{0,60}\b(?:definitive|"
                     r"long[\s-]form)\s+(?:loan\s+|credit\s+)?(?:documentation|documents|agreements?)\b|\bupon\s+(?:the\s+)?(?:execution|"
                     r"completion)\s+of\s+(?:the\s+)?definitive|\bboard\s+(?:of\s+directors\s+)?(?:has\s+)?approv\w+\b[^.]{0,80}\b"
                     r"(?:loan|facility|financing)|\b(?:received|receives|obtained)\s+(?:\w+\s+){0,2}approvals?\s+from\s+"
                     r"(?!the\s+(?:TSX|Exchange|CSE|shareholders)|(?:TSX|CSE)\b)")
_DEFINITIVE = re.compile(r"(?i)\b(?:entered\s+into|enters\s+into|executed|signed|signs|executes|entering\s+into|execution\s+of)\s+"
                         r"(?:a\s+|an\s+|the\s+|two\s+|its\s+)?(?:binding\s+)?(?:[\w-]+\s+){0,3}?(?:definitive|credit|loan|facility|"
                         r"debenture|note\s+purchase|subscription|amending|financing)\s+agreements?\b|\bdefinitive\s+(?:loan\s+|"
                         r"credit\s+|financing\s+)?agreements?\s+(?:were|was|have\s+been|has\s+been)\s+(?:signed|executed|entered)")
_INT_SETTLE_HL = re.compile(r"(?i)\binterest\s+(?:debt|indebtedness|owing|owed|obligations?|payment\s+obligations?)\b|"
                            r"\b(?:settle\w*|settlement|satisf\w*)\s+(?:of\s+)?(?:\w+\s+){0,3}?interest\b|\bshares?\s+(?:issued\s+)?"
                            r"(?:for|as)\s+(?:\w+\s+){0,2}interest\b|\binterest\s+(?:debt\s+)?settlement\b")
_SETTLE_ACT = re.compile(r"(?i)\bsettle\w*|\bsatisf\w*|\bshares?[\s-]+for[\s-]+debt|\bin\s+(?:payment|lieu)\s+of|\bpay\w*\b[^.]{0,120}"
                         r"\b(?:shares|units)\b|\bissu\w+\s+[^.]{0,120}\b(?:shares|units)\b|\bpaying\s+off\b")
_INT_SETTLED = re.compile(r"(?i)\b(?:settle\w*|settlement\s+of|satisf\w*|pay\w*|paid|repay\w*|in\s+(?:lieu|respect|payment)\s+of)\s+"
                          r"(?:(?:all|the|of|its|a|portion|part|certain|outstanding|accrued|unpaid|and|fees|owing|total|aggregate|"
                          r"approximately|remaining|annual|quarterly|semi-annual|(?:US|C|CA)?\$[\d,.]+|[\d,.]+)\s+){0,6}interest\b|"
                          r"\binterest\s+(?:indebtedness|debt|owing|owed|payable|obligations?|payment\s+obligations?)\b|\bdebt\s+being\s+"
                          r"settled\s+is\s+[^.]{0,40}\binterest\b|\bshares?\s+(?:issued\s+)?(?:for|as)\s+(?:\w+\s+){0,2}interest\b|"
                          r"\brepresenting\s+(?:a\s+portion\s+of\s+)?(?:the\s+)?(?:fees\s+and\s+)?interest\b|"
                          r"\brepresenting\s+(?:the\s+)?(?:US|C|CA)?\$\s?[\d.,]*\d\s+(?:in|of)\s+(?:accrued\s+)?interest\b")
                          # FIX3: 'shares ... to debenture holders, representing the $7,500 in interest due' 
_PRINC_SETTLED = re.compile(r"(?i)\bprincipal\b[^.]{0,60}\b(?:settle[ds]?|repaid|converted|retired|extinguished)\b|\b(?:settle[ds]?|settling|"
                            r"repa(?:y|id|ys|ying)|convert(?:ed|s|ing)?|retir(?:e|ed|es|ing))\s+(?:(?!interest\b)[\w$.,]+\s+){0,4}"
                            r"(?:principal|loans?|notes?|debentures?|advances?|"
                            r"indebtedness)\b|\b(?:debentures?|notes?|loans?)\s+(?:\w+\s+){0,3}(?:were|was|have\s+been|has\s+been)\s+"
                            r"(?:\w+\s+)?(?:converted|repaid|settled)\b")


_TERMS_ONLY = re.compile(r"(?i)\b(?:may(?!\s+\d)|shall|can|could|if|any|option|discretion|election|payable|coupon|bears?|bearing|per\s+annum|"
                         r"in\s+the\s+event)\b")


_SETTLE_HL = re.compile(r"(?i)\bshares?[\s-]+for[\s-]+debt\b|\bdebt[\s-]+for[\s-]+shares\b|\bdebt\s+settlements?\b|\bsettle\w*\s+(?:of\s+)?"
                        r"(?:\w+\s+){0,2}(?:debt|indebtedness)\b|\bin\s+settlement\s+of\s+debt\b")


def _lumped_loan(s, a):
    """1.0.4 (rule DS): a 'loan' named only inside a list of fees, advances or payables settled together ('management
    fees and loans', 'loans, advances or payments'), with no amount of its own."""
    pre, post = s[max(0, a - 60):a], s[a:a + 60]
    fee = r"(?:fees?|salar\w*|services?|payables?|expenses|wages|remuneration|compensation|payments?|advances|liabilities)"
    lumped = re.search(r"(?i)\b" + fee + r"\b\s*(?:,|and|or|&)\s+(?:[\w-]+\s+){0,2}$", pre) or \
        re.match(r"(?i)loans?\s*(?:,|and|or|&)\s+(?:[\w-]+\s+){0,2}" + fee + r"\b", post)
    sized = re.search(r"(?i)(?:US|C|CA)?\$\s?[\d,.]+\d\s*(?:million\s+)?(?:\w+\s+){0,3}$", pre[-40:]) or \
        re.match(r"(?i)loans?\s+(?:\w+\s+){0,4}(?:of|totall?ing|in\s+the\s+amount\s+of)\s+(?:US|C|CA)?\$", post)
    owed_on = re.search(r"(?i)\binterest\s+(?:\w+\s+){0,3}$", pre)          # 'interest on the Loan and the ...'
    return bool(lumped and not sized and not owed_on)


_USE_OF_PROCEEDS = re.compile(r"(?i)\b(?:to|will)\s+(?:re(?:finance|pay)|redeem|retire|replace|prepay)\s+(?:the\s+|its\s+|an?\s+|existing\s+|"
                              r"outstanding\s+|certain\s+)*(?:[\w$.,%'\u2019-]+\s+){0,5}$|\brefinancing\s+of\s+(?:the\s+|its\s+)?(?:[\w$.,%'\u2019-]+\s+){0,5}$")


def _interest_settlement(h, sents):
    """1.0.4: the release settles the interest owed on a debt (in shares or cash), not the debt itself (rule DI):
    'Settlement of Interest Debt', 'to settle interest indebtedness of $50,400 owing on its convertible debentures',
    'The debt being settled is pursuant to interest owed on convertible notes'."""
    acts = [s for s in sents[:8] if _SETTLE_ACT.search(s) and not _is_background(s) and not _TERMS_ONLY.search(s)][:4]
    if any(_PRINC_SETTLED.search(s) for s in acts):
        return False
    if _INT_SETTLE_HL.search(h):
        # unless the headline also reports an event on the debt itself ('Reduces Debt and Issues Shares as Interest')
        return not re.search(r"(?i)\b(?:reduc\w*|repa(?:y|id|ys|yment)|redeem\w*|redemption|convert\w*|conversion|extend\w*|"
                             r"extension|amend\w*|retir\w*|eliminat\w*|clos(?:es|ed|ing))\b", _INT_SETTLE_HL.sub(" ", h))
    return any(_INT_SETTLED.search(s) for s in acts)


_CONV_FEATURE = re.compile(r"(?i)\b(?:right|option|entitled|elect(?:ion)?|may)\s+(?:\w+\s+){0,3}?to\s+convert\s+(?:all\s+or\s+(?:any\s+)?"
                           r"(?:a\s+)?part\s+of\s+|any\s+portion\s+of\s+|some\s+or\s+all\s+of\s+)?(?:the\s+)?(?:outstanding\s+)?(?:principal|"
                           r"loan|amount|advances?)\b|\b(?:loan|principal|advances?)\s+(?:\w+\s+){0,4}(?:is|are|will\s+be|shall\s+be)\s+"
                           r"convertible\b|\bconversion\s+(?:feature|right)s?\b|\(\s*the\s+[\"\u201c]\s*Conversion\s+Price\s*[\"\u201d]")


def _stage_for(k, idx, h, sents):
    hl = [(i, a) for i, a in idx if i == -1]
    named = {a for a, e, kk in _instruments_in(h)}
    if any(a in named for i, a in hl):
        hl = [(i, a) for i, a in hl if a in named]       # 1.0.4: the headline's own name for it, not a generic 'Debt'
    st = None
    if hl:
        hits = []
        for i, a in hl:
            hits += _stage_hits(h, around=a, window=70)
        st = _pick_stage(hits, nearest=True)
        a0 = min(a for i, a in hl)
        m = re.match(r"(?i)(?:(?!(?:and|or)\b)[\w$.,%'\u2019-]+\s+){1,3}?(extension|amendment|repayment|conversion|settlement|redemption|"
                     r"restructuring|drawdown|draw-down|termination|increase|upsize|forgiveness)s?\b", h[a0:a0 + 60])
        if m:                                             # 1.0.4: 'Receives Debt Extension': the noun names the event
            st = _pick_stage(_stage_hits(m.group(1))) or st
        if st == "drawn" and re.search(r"(?i)\bclos(?:es|ed|ing)\b", h[:min(a for i, a in hl)]):
            st = "closed"                                 # 'Closing of the Gold Loan and Draw Down': funded at closing
        if st == "drawn" and re.search(r"(?i)\b(?:initial|first)\s+(?:draw\w*|advance|utili[sz]ation|funding)", h):
            st = "closed"                                 # 1.0.4: the first funding of a facility is its closing
        if st and any(_TRANCHE.search(h[max(0, a - 80):a + 60]) and not re.search(r"(?i)\band\s+(?:also\s+)?announc|;|\band\s+(?:the\s+)?"
                                                                                      r"(?:launch|propos)", h[max(0, a - 80):a]) for i, a in hl) and st in ("proposed", "signed") and not re.search(r"(?i)\bpropos|\bannounces?\s+"
                                                                                       r"(?:private|offering|non-brokered)", h):
            st = "closed"
    body_lead = [(i, a) for i, a in idx if 0 <= i <= 6 and not _is_background(sents[i])]
    gen = _GENERIC_WORD.get(k)
    if gen is not None and hl:
        # 'has entered into a loan agreement with Petra': the body's own word for the headline's instrument
        for i in range(min(3, len(sents))):
            if not _is_background(sents[i]):
                body_lead += [(i, m.start()) for m in gen.finditer(sents[i]) if (i, m.start()) not in body_lead]
    if st is None:
        for i in sorted({i for i, a in body_lead}):
            hits = []
            for i2, a in body_lead:
                if i2 == i:
                    hits += _stage_hits(sents[i], around=a, window=220)
            st = _pick_stage(hits)
            if st:
                break
        if st is None and re.search(r"(?i)\b(?:clos|complet)\w*\b", h) and re.search(r"(?i)financing|placement|offering", h):
            st = "closed"
    if st is None and body_lead == [] or st is None:
        hits = []
        for i, a in idx:
            if 0 <= i <= 6 and _is_background(sents[i]):
                hits += _stage_hits(sents[i], around=a, window=160)
        st = _pick_stage(hits)
    if st is None and hl:
        # FIX3: 'Announces Shareholder Loan', then 'it has agreed to borrow up to $200,000 from three directors'
        for s in [x for x in sents[:3] if not _is_background(x)]:
            mb = _BORROW.search(s)
            if mb:
                st = "closed" if mb.group(1) else "signed"
                break
    if st is None and hl and (_ANNOUNCE_OFFER.search(h) or re.search(r"(?i)\bannounc\w*\b", h) and any(
            re.match(r"(?i)[\w\s-]{0,30}?\b(?:financing|offering|private\s+placement)\b", h[a:a + 60]) for i, a in hl)):
        st = "proposed"                                   # 'Announces $1,000,000 Convertible Note Offering'
    if st is None and _TRANCHE.search(h):
        st = "closed"
    if st is None and hl and any(re.search(r"(?i)\bannounc\w*\s+(?:an?\s+|its\s+|new\s+)?(?:(?:US|C|CA|GBP|EUR)?\s?[$\u00a3\u20ac]\s?[\d.,]+\s*"
                                           r"(?:million|billion|m)?\s+)(?:[\w-]+\s+){0,3}$", h[:a]) for i, a in hl):
        st = "proposed"                                   # 1.0.4: 'Announces GBP1 Million Convertible Debenture', nothing more
    if not hl and st in (None, "proposed") and re.search(r"(?i)\b(?:signs?|signed|executes?|executed|enters?\s+into)\s+(?:\w+\s+){0,2}"
                                                           r"definitive\s+(?:\w+\s+)?agreements?\b", h):
        st = "signed"                                     # 1.0.4: the headline's own report of a definitive agreement
    if st is None:
        return None
    lead_txt = " ".join(sents[i] for i, a in body_lead[:4]) + " " + " ".join(sents[:3])
    if st in ("closed", "signed") and _WEAK_CLOSE.search(h) and k in ("credit_facility", "prepayment", "gold_loan", "loan",
                                                                    "convertible_note") and \
            not _real_close(h + " " + lead_txt):
        st = "signed"
    if st == "signed" and k in ("loan", "credit_facility", "gold_loan", "prepayment", "convertible_note") and \
            _real_close(" ".join(sents[:10])) and not re.search(r"(?i)\bexpected\s+to\s+close|\bterm\s+sheet|\bsubject\s+to\s+"
                                                                     r"(?:the\s+)?(?:execution|definitive)", " ".join(sents[:6])):
        st = "closed"
    if st in ("proposed", "signed", "closed") and re.search(
            r"(?i)\bhas\s+amended\s+(?:and\s+restated\s+)?(?:the\s+terms\s+of\s+)?(?:its|the)\b|\bamendments?\s+to\s+"
            r"(?:its|the)\s+existing\b|\bexisting\s+(?:credit\s+)?facilit(?:y|ies)\s+(?:were\s+|was\s+|have\s+been\s+)?revised\b",
            h + " " + " ".join(sents[:2])):
        st = "amended"                                    # 1.0.2: Torex's sustainability-linked amendment
    own_txt = lead_txt + " " + " ".join(sents[i] for i, a in idx if 0 <= i < 40)
    if st == "closed" and k in ("loan", "credit_facility", "convertible_note") and re.search(
            r"(?i)\bconditional(?:ly)?\s+(?:acceptance|approv\w*|accepted)\b", own_txt) and not re.search(
            r"(?i)\b(?:has|have|was|were)\s+(?:been\s+)?(?:advanced|funded|drawn|disbursed)\b|\breceived\s+(?:the\s+)?"
            r"(?:funds|proceeds|advance)\b", own_txt):
        st = "signed"                                     # 1.0.2: exchange acceptance pending, nothing advanced
    if st == "amended" and _CANCEL_FOR_SHARES.search(lead_txt + " " + " ".join(sents)) and re.search(
            r"(?i)restructur|settle|cancel", h + " " + lead_txt):
        st = "repaid"
    if st == "repaid" and re.search(r"(?i)\bconver(?:sion|ted|ts)\b", h):
        st = "converted"
    # FIX5 (rule DU): an offering re-priced, extended or upsized before it closes keeps its stage; a headline
    # that only 'announces' a placement whose lead says it has closed reports the closing
    if st == "amended" and re.search(r"(?i)\b(?:amend\w*|extension|extend\w*|re-?pric\w*)\b[^.]{0,80}?\b(?:offering|private\s+"
                                     r"placement)\b", h + " " + " ".join(sents[:2])) and \
            re.search(r"(?i)\bpreviously\s+announced\b[^.]{0,80}\b(?:offering|private\s+placement)\b", h + " " + " ".join(sents[:2])) and \
            not re.search(r"(?i)\b(?:has|have)\s+(?:now\s+)?(?:closed|completed)\b|\btranche\b", h + " " + " ".join(sents[:3])):
        st = "proposed"
    if st == "proposed" and hl and not re.search(r"(?i)\bpropos\w*|\bintend|\blaunch\w*|\bterm\s+sheet|\bnon-binding|\bletter", h):
        lead3 = [x for x in sents[:4] if not _is_background(x)][:3]
        if any(re.search(r"(?i)(?<!will\s)(?<!to\s)\b(?:has|have)\s+(?:now\s+)?(?:closed|completed)\s+(?:the|its|a)\s+(?:[\w-]+\s+){0,4}?"
                         r"(?:private\s+placement|offering|financing|debentures?|notes?)\b", x) for x in lead3):
            st = "closed"
    # 1.0.4: a commitment letter, credit approval, term sheet or letter of interest is proposed until a definitive
    # agreement is signed or money moves (label guide: proposed)
    hl_done = re.search(r"(?i)\b(?:clos(?:es|ed|ing)|complet(?:es|ed|ion)|funded|draw\w*)\b", h)
    commit_txt = h + " " + lead_txt + " " + " ".join(sents[i] for i in sorted({i for i, a in idx if 0 <= i <= 24})[:4])
    if st in ("signed", "closed") and not hl_done and _COMMIT.search(commit_txt) and not _DEFINITIVE.search(commit_txt) and \
            not _real_close(commit_txt):
        st = "proposed"
    # 1.0.4: converting a debt that is not convertible (a loan settled in shares) is a repayment; a convertible the lead
    # says was converted is converted
    conv_kind = k in ("convertible_debenture", "convertible_note")
    if st == "converted" and not conv_kind:
        st = "repaid"
    if st == "repaid" and conv_kind and body_lead:
        i0 = min(i for i, a in body_lead)
        near = [x for a in [a for i, a in body_lead if i == i0] for x in _stage_hits(sents[i0], around=a, window=160)
                if x[0] in ("converted", "repaid")]
        if near and min(near, key=lambda x: x[1])[0] == "converted":
            st = "converted"                              # 1.0.4: 'has converted a $394,883 convertible debenture'
    if st == "terminated" and re.search(r"(?i)\btender\s+offers?|\bredeem\w*|\bredemption|\brepurchas\w*|\bpurchased\b|\bbuy-?back|"
                                        r"\bnormal\s+course\s+issuer\s+bid", h + " " + lead_txt):
        st = "repaid"                                     # 1.0.4: notes cancelled after they were bought back
    st = _facility_ending(k, st, h + " " + lead_txt)      # a credit facility retired, nothing repaid: terminated
    if st == "repaid" and any(re.search(r"(?i)\bissu\w+\s+(?:\w+\s+){0,8}?(?:debentures?|notes?)\b[^.]{0,120}\b(?:in\s+(?:settlement|"
                                        r"satisfaction)\s+of|to\s+settle)\b", sents[i]) for i, a in body_lead[:3]):
        st = "closed"                                     # 1.0.4: the debenture is issued to settle other debt
    # 1.0.4: what is settled is the interest owed on the debt, not the debt (rule DI)
    if st in ("repaid", "closed", "signed", "proposed") and (not hl or st == "repaid" or _INT_SETTLE_HL.search(h)) and \
            _interest_settlement(h, sents):
        return "interest-only"
    if st == "repaid":
        # the only thing repaid is interest (rule DI)
        rep = [s for s in sents[:6] if _ST_REPAID.search(s)]
        said_interest = any(re.search(r"(?i)\bportion\s+of\s+the\s+accrued|\baccrued\s+(?:\w+\s+){0,3}interest\s+owing|"
                                      r"repay\s+[^.]{0,80}\binterest\b", s) for s in rep)
        said_principal = any(re.search(r"(?i)repa\w*\s+(?:\w+\s+){0,6}principal|principal\s+(?:amount\s+)?(?:was|has\s+been|is|"
                                       r"will\s+be)\s+repaid|\bin\s+full\b|\boutstanding\s+(?:balance|principal)\b|\bface\s+value",
                                       s) for s in rep)
        if said_interest and not said_principal:
            return "interest-only"
    return st


_BORROW = re.compile(r"(?i)\b(?:(?:has|have)\s+(borrowed)\b|(?:has\s+|have\s+)?agreed\s+to\s+borrow\b)")


_LENDER_SIDE = re.compile(r"(?i)\b(?:has\s+)?(?:provided|advanced|lent|loaned|will\s+(?:provide|advance|lend))\s+(?:a\s+|an\s+)?"
                          r"(?:(?:US|C|CA)?\$[\d.,]+\s*(?:million|M)?\s+)?(?:to\s+(?:a|an)\s+(?:subsidiary|target|private|"
                          r"company)\b|to\s+the\s+target\b)|\bhas\s+provided\s+(?:US|C)?\$[\d.,]+\s*(?:million\s+)?to\s+(?!the\s+(?:Company|Corporation)\b)|"
                          r"\bacquir\w+\s+[^.]{0,60}\bdebentures?\s+(?:of|issued\s+by)\b|\bacquir\w+\s+(?:additional\s+)?"
                          r"[^.]{0,40}\bdebenture\s+units\s+of\s+(?!the\s+Company\b)|\bDebentures\b[^.]{0,40}\bfrom\s+"
                          r"clients\b|\bconvertible\s+promissory\s+note\s+issued\s+by\s+the\s+Target|\bpursuant\s+to\s+an?\s+"
                          r"(?:unsecured\s+|secured\s+)?convertible\s+promissory\s+note\s+issued\s+by\b|\bintends\s+to\s+acquire"
                          r"\s+these\s+units\b|\bacquire\s+[^.]{0,30}\bdebentures\s+for\s+shares\b|\b(?:is|as|becomes?|become)\s+(?:the\s+)?(?:sole\s+)?holder\s+of\s+[^.]{0,40}"
                          r"\bdebentures\b|\bADVANCES\s+LOAN\b|\bAdvances\s+Loan\b")


_PROVIDE_WITH = re.compile(r"\b(?:has\s+|have\s+)?agreed\s+to\s+provide\s+([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5})"
                          r"[^.]{0,60}?\s+with\s+(?:a|an|up\s+to)?\s*(?:(?:US|C|CA)?\$\s?[\d.,]+\s*(?:million|billion|M)?\s+)"
                          r"(?:[\w-]+\s+){0,4}?(?:loan|credit\s+facility|facility|debentures?|notes?|bridge)")


def _self_subject(subj, self_rx):
    """The company itself is the subject just before the verb: 'Franco-Nevada, through one of its wholly-owned
    subsidiaries, has agreed ...'; not 'a director of the Company has agreed ...'."""
    subj = re.split(r"[.;]\s", subj)[-1]
    ends = [m.end() for m in re.finditer(r"(?i)\bthe\s+(?:Company|Corporation)\b|\bwe\b|\bit\b", subj)]
    if self_rx:
        ends += [m.end() for m in self_rx.finditer(subj)]
    return any(re.match(r"(?:\s+[A-Z][\w&.\-]*){0,4}\s*(?:\([^)]{0,60}\)\s*)?(?:,[^.]{0,120}?,)?\s*$", subj[e:]) for e in ends)


_NOT_A_PARTY = (r"(?!(?:the\s+)?(?:company|corporation|issuer|fund|finance|pay|support|advance|repay|be|cover|help|complete|"
                r"purchase|acquire|settle|provide|continue|develop|build|restart|retire|refinance|meet|allow|enable|bridge|close|"
                r"expand|accelerate|commence|begin|start|us|it|its|date|maturity|\$|us\$|c\$|\d)\b)")
# 1.0.4 (rule DL): the company lends, buys another's debt, or is repaid a loan it made
_LENDS = re.compile(r"(?i)\breceipt\s+of\s+(?:\w+\s+){0,2}(?:loan|debt)\s+repayments?\b|\breceive[sd]?\s+(?:[\w$.,]+\s+){0,4}(?:from|in)\s+"
                    r"(?:\w+\s+){0,2}(?:loan|debt)\s+repayments?\b|\bloan\s+purchase\s+agreement\b|\bmakes?\s+available\s+to\s+"
                    r"(?!the\s+Company)(?-i:[A-Z])|\bin\s+favou?r\s+of\s+(?!the\s+(?:Company|Corporation|Lenders?))(?-i:[A-Z])[\w&.'-]+"
                    r"(?=[^.]{0,40}$)|\bgranted\s+by\s+the\s+(?:Company|Corporation)\s+to\b|\bacquire\s+(?:[\w'\u2019]+\s+){0,6}?(?:interests?\s+"
                    r"in\s+)?(?:(?:secured|senior|outstanding)\s+)*(?:loans?|loan\s+(?:obligations|facility)|indebtedness)\s+(?:owed|owing|"
                    r"of|obligations)\b|\b(?:acquire|purchase)\s+(?:all\s+(?:of\s+)?)?(?:the\s+)?interests?\s+(?:owned|held)\s+by\s+(?:a\s+)?"
                    r"(?:group\s+of\s+)?creditors\b")
_LENT_TO = re.compile(r"(?i)\b(?:provided|made|extended|granted|advanced|lent|loaned|completed)\s+(?:a|an)\s+(?:[^\s.]+\s+){0,12}?"
                      r"(?:loan|credit\s+facility|facility|promissory\s+note)\b[^.]{0,120}?\bto\s+" + _NOT_A_PARTY +
                      r"(?:an?\s+(?:arm'?s[\s-]length\s+)?private|(?-i:[A-Z]))")
_HEAD_LOAN_TO = re.compile(r"(?i)\b(?:loan|credit\s+facility|bridge\s+financing)\s+to\s+" + _NOT_A_PARTY + r"(?:private\s+company|"
                           r"(?-i:[A-Z])[\w&.'-]*)")


# FIX5 (rule DL): the company itself advances, provides or holds the debt: 'the Company has agreed to advance to X up
# to $950,000', 'the Company advanced $130,000 under the Credit Facility to X', 'it has provided a short-term financing
# of US$7.2 million ... to a private royalty company', 'the Company will hold a $1,725,000 secured demand loan ... with X'
_SELF_LENDS = re.compile(r"\b(?:the\s+(?:Company|Corporation)|[Ii]t|[Ww]e)\s+(?:has\s+|have\s+|had\s+)?(?:(?:also\s+)?agreed\s+to\s+|will\s+)?"
                         r"(?:advanced?|lend|lent|loaned|provided|provide)\s+(?:(?!to\b)[^.;]|\.(?=\d)){0,160}?\bto\s+"
                         r"(?!(?:the\s+)?(?:Company|Corporation|us|it|its|fund|support|complete|meet|be|help|enable|allow|finance|pay|"
                         r"repay|acquire|cover)\b)(?:an?\s+(?:arm'?s[\s-]length\s+)?private|[A-Z])")
_SELF_HOLDS = re.compile(r"\b(?:the\s+(?:Company|Corporation)|[Ii]t|[Ww]e)\s+(?:will\s+|now\s+|shall\s+)?holds?\s+(?:an?\s+|the\s+)?"
                         r"(?:(?:US|C|CA)?\$[\d.,]+\s*(?:million\s+)?)?(?:[\w-]+\s+){0,3}(?:loan|debentures?|notes?|credit\s+facility)\b")


def _side(h, sents, idx, self_rx):
    body = " ".join(sents[i] for i, a in idx if 0 <= i <= 4)
    # 1.0.4: the sentences that name the instrument, wherever the release first names it
    own = sorted({i for i, a in idx if 0 <= i <= 24})[:4]
    body_own = " ".join(sents[i] for i in own)
    txt = h + " " + body
    for m in list(_SELF_LENDS.finditer(body_own)) + list(_SELF_HOLDS.finditer(body_own)):
        if re.search(r"(?i)\b(?:loans?|credit|facilit|debentures?|notes?|financing|advances?|funding)\b", m.group(0) +
                     body_own[m.end():m.end() + 80]) and not re.search(r"(?i)\bsubsidiar|\bwholly[\s-]owned", m.group(0)):
            return "lender"
    if _LENDS.search(h + " " + body_own):
        return "lender"
    m = _HEAD_LOAN_TO.search(h)
    if m and not (self_rx and self_rx.search(h[m.end() - 1 - len(m.group(0).split()[-1]):m.end() + 40])):
        return "lender"
    for m in _LENT_TO.finditer(body_own):
        subj = body_own[max(0, m.start() - 160):m.start()]
        tail = body_own[m.end() - 1:m.end() + 60]
        if self_rx and self_rx.match(tail):
            continue
        if _self_subject(subj, self_rx) or re.search(r"(?i)\b(?:it|we)\s+(?:has|have)\s*$", subj):
            return "lender"
    # 1.0.2: "Franco-Nevada ... has agreed to provide G Mining Ventures Corp. with a $75 million secured term loan"
    for m in _PROVIDE_WITH.finditer(body):
        who, subj = m.group(1), body[max(0, m.start() - 160):m.start()]
        if self_rx and self_rx.search(who) or re.match(r"(?i)(?:the\s+)?(?:Company|Corporation|Issuer|us|it)\b", who):
            continue
        if _self_subject(subj, self_rx):
            return "lender"
    for m in _LENDER_SIDE.finditer(txt):
        tail = txt[m.end():m.end() + 60]
        if self_rx and re.search(r"(?i)\bunits\s+of\s*$", m.group(0)) and self_rx.match(tail):
            continue
        return "lender"
    # a bid for another issuer's debentures: 'Superior Offer for Stone Investment Group Limited Debentures'
    for m in re.finditer(r"(?i)\b(?:offer|bid)\s+(?:to\s+(?:purchase|acquire)\s+|for\s+)(?:all\s+(?:of\s+)?)?(?:the\s+)?"
                         r"(?:outstanding\s+)?((?:[A-Z][\w&.'-]*\s+){1,6})debentures\b", txt):
        who = m.group(1)
        if re.search(r"(?i)\b(?:Limited|Ltd|Inc|Corp|Group|Corporation)\b", who) and not (self_rx and self_rx.search(who)):
            return "lender"
    # 'a loan to Target Corp.' in the body (a headline's capitals prove nothing)
    m = re.search(r"\b[Ll]oan\s+to\s+([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,4})", body)
    if m and not re.match(r"(?i)(?:the\s+)?(?:Company|Corporation|Issuer|it|us|help|fund|finance|complete|support|enable|"
                          r"advance|pay|repay|acquire|cover|meet|provide|allow|build|develop|purchase|refinance|fully|"
                          r"congressional|value|cost|date|closing|maturity|equity|shares?|common|units?|January|February|March|April|May|June|"
                          r"July|August|September|October|November|December|\d)\b",
                          m.group(1)) and not (self_rx and self_rx.search(m.group(1))):
        if re.search(r"(?i)\b(?:subsidiary|wholly[\s-]owned)", txt[max(0, m.start() - 60):m.end() + 60]):
            return "borrower"
        return "lender"
    return "borrower"


def _empty():
    return {k: None for k in TXT_FIELDS + NUM_FIELDS}


_GENERIC_WORD = {
    "convertible_debenture": re.compile(r"(?i)\bdebentures?\b"),
    "convertible_note": re.compile(r"(?i)\b(?:convertible\s+)?(?:notes?|loans?)\b"),
    "loan": re.compile(r"(?i)\b(?:the|such|each|this)\s+(?:\w+\s+)?(?:loans?|promissory\s+notes?)\b|\bLoans?\b|\bthe\s+Debt\b|"
                       r"(?-i:\bFinancing\s+Facility\b|\bthe\s+Facility\b|\bLoan\s+Facility\b)|"
                       r"\bthe\s+(?:Senior\s+)?(?:Debt\s+)?Financing\b|\bDebt\s+Agreement\b"),
    "credit_facility": re.compile(r"(?i)\b(?:the|this|such|new)\s+(?:\w+\s+){0,2}?(?:facility|facilities|revolver)\b|\bFacility\b"),
    "notes": re.compile(r"(?i)\b(?:the|such)\s+(?:\w+\s+){0,2}?(?:notes|debentures?|bonds)\b|\b(?:Notes|Debentures?|Bonds)\b"),
    "gold_loan": re.compile(r"(?i)\b(?:the|this)\s+(?:\w+\s+){0,2}?(?:loan|facility)\b"),
    "prepayment": re.compile(r"(?i)\b(?:the|this)\s+(?:\w+\s+){0,2}?(?:prepayment|facility)\b"),
}
_TERMS_WORD = re.compile(r"(?i)\binterest\b|\bmatur|\bsecur|\bconver|\bterm\b|\brate\b|\bwarrants?\b|\bprincipal\b|\bdue\b|"
                         r"\brepay")
_LABEL_LINE = re.compile(r"^[A-Z][\w\s/()&-]{1,34}:\s")


def _context(k, idx, h, sents):
    """The sentences that describe this instrument: those naming it, those using its defined term, the terms that
    follow them (next three sentences, and 'Label: value' lines)."""
    base = sorted({i for i, a in idx if i >= 0})
    gen = _GENERIC_WORD.get(k)
    if gen is not None:
        base = sorted(set(base) | {i for i in range(min(len(sents), 40)) if gen.search(sents[i])})
    got = set(base)
    for i in base[:12]:
        for j in range(i + 1, min(len(sents), i + 4)):
            if _TERMS_WORD.search(sents[j]):
                got.add(j)
        j = i + 1
        while j < len(sents) and j < i + 12 and _LABEL_LINE.match(sents[j]):
            got.add(j)
            j += 1
    near = [sents[i] for i in sorted(got)[:30]]
    return ([h] if any(i == -1 for i, a in idx) else []) + near


_PRINCIPAL_RX = re.compile(r"(?i)(?:aggregate\s+)?principal\s+(?:amount\s+)?(?:of\s+)?(?:up\s+to\s+)?(?:the\s+\w+\s+)?"
                           r"((?:US|C|CA|CAD|CDN|USD)?\s?\$\s?[\d.,]+(?:\s*(?:million|billion))?)|((?:US|C|CA|CAD|CDN|USD)?\s?\$\s?"
                           r"[\d.,]+(?:\s*(?:million|billion))?)\s+(?:in\s+)?(?:outstanding\s+)?(?:aggregate\s+)?principal\s+amount|((?:US|C|CA|CAD|CDN|USD)?"
                           r"\$?\s?[\d.,]+(?:\s*(?:million|billion))?)\s*\(\s*the\s+[\"\u201c]\s*Principal\s+Amount")
_NOT_PRINCIPAL = re.compile(r"(?i)mark-to-market|market\s+value|valued\s+at|value\s+of\s+approximately|capex|capital\s+cost|npv|"
                            r"revenue|market\s+cap|purchase\s+price\s+(?:of|for)\s+the\s+(?:property|company|site|refinery)|"
                            r"per\s+(?:share|unit|ounce)|exercise\s+price|royalt|stream\s+(?:deposit|payment)|equity\s+financing|"
                            r"private\s+placement\s+of\s+(?:units|shares|common)|flow[\s-]through|accordion|\bto\s+cost\b|\bwill\s+cost\b|"
                            r"\bcost\s+of\b|\bcosts?\s+(?:estimated|estimate)")


def _money_to_value(txt):
    ms = _money_all(txt)
    return (ms[0][2], ms[0][3]) if ms else (None, None)


_FACE = re.compile(r"(?i)((?:US|C|CA|CAD|USD)?\$\s?[\d.,]+(?:\s*(?:million|billion))?)\s+face\s+value|\bface\s+value\s+of\s+"
                   r"((?:US|C|CA|CAD|USD)?\$\s?[\d.,]+(?:\s*(?:million|billion))?)")
_PER_UNIT = re.compile(r"(?i)\b(?:a|each|every|per|one)\s*$|\bper\s+(?:unit|debenture|note)\b|\bfor\s+each\b|"
                       r"\beach\s+(?:unit|debenture|note)\b")
_EACH_PRE = re.compile(r"(?i)\beach\b[^.$]{0,50}$|\bper\s+(?:debenture|note|unit)\b[^.$]{0,20}$")


def _pick_money(s, x, y):
    return not _EACH_PRE.search(s[max(0, x - 60):x])


_MONEY_TXT = r"((?:US|C|CA|CAD|USD|CDN)?\s?\$\s?[\d.,]*\d(?:\s*(?:million|billion|M)\b)?)"
_NEW_SIZE = re.compile(r"(?i)\b(?:increas\w*|upsiz\w*|expan\w*|amend\w*|rais\w*)\b[^.]{0,160}?\bfrom\s+(?:up\s+to\s+)?" + _MONEY_TXT +
                       r"\s+to\s+(?:up\s+to\s+)?(?:a\s+(?:total|maximum)\s+of\s+)?" + _MONEY_TXT + r"|\b(?:increas\w*|upsiz\w*|"
                       r"expan\w*)(?!\s+of\b)\s+(?:the\s+|its\s+)?(?:[\w-]+\s+){0,5}?(?:by\s+[^.]{0,40}?\s+)?to\s+(?:a\s+(?:total|maximum)\s+"
                       r"(?:of\s+)?|up\s+to\s+|an\s+aggregate\s+(?:of\s+)?)?" + _MONEY_TXT + r"|\bbring(?:s|ing)?\s+the\s+(?:total\s+|"
                       r"aggregate\s+|outstanding\s+)*(?:principal\s+)?(?:amount\s+)?(?:\w+\s+){0,3}?to\s+" + _MONEY_TXT)


def _principal(k, st, h, sents, idx, ctx, cur_default):
    body_ctx = [c for c in ctx if c is not h]
    # 0. a face value
    for s2 in body_ctx:
        m = _FACE.search(s2)
        if m and not re.search(r"(?i)^\s*(?:of|per)\s+(?:each|every|a|one)\b", s2[m.end():m.end() + 20]) and \
                not _EACH_PRE.search(s2[max(0, m.start() - 60):m.start()]):
            v, c = _money_to_value(m.group(1) or m.group(2))
            if v and v > 1000:
                return v, c
    # 0b. a repayment the headline sizes
    if st == "repaid":
        for i, a in idx:
            if i == -1:
                ms = [(abs(x - a), v, c) for x, y, v, c in _money_all(h) if v >= 1000 and abs(x - a) <= 45]
                if ms:
                    return min(ms)[1:]
    # 0b2. 1.0.4: an increase or amendment sizes the debt as it now stands ('from US$14,000,000 to US$16,000,000')
    # a tranche closed is that tranche, even beside an upsize of the whole offering (rule DP)
    tranche_close = st == "closed" and bool(_TRANCHE.search(h))
    if st == "amended" or st in ("proposed", "signed", "closed") and not tranche_close and re.search(
            r"(?i)\b(?:increas\w*|upsiz\w*)\b[^.]{0,40}\b(?:loans?|financing|facility|debentures?|notes?|offering|placement)\b", h):
        for s in [h] + body_ctx[:8]:
            for m in _NEW_SIZE.finditer(s):
                if re.search(r"(?i)\b(?:was|were|had\s+been|previously|subsequently|originally)\b[^.]{0,40}$", s[:m.start() + 12]) or \
                        re.match(r"(?i)\s*(?:per|a|each)\s+(?:month|year|quarter|annum)", s[m.end():m.end() + 15]) or \
                        not re.search(r"(?i)\b(?:loans?|facilit\w*|debentures?|notes?|financing|credit|principal|offering|placement|"
                                      r"prepayment|advances?)\b", s[max(0, m.start() - 160):m.end()]):
                    continue                              # an earlier increase; a payment rate; not the debt's size
                v, c = _money_to_value(m.group(m.lastindex))
                if v and v >= 1000:
                    return v, c
    # 0b3. 1.0.4: an upsized offering is its final size, the headline's figure beside the instrument (rule DU)
    if st in ("proposed", "signed", "closed") and not tranche_close and re.search(r"(?i)\bupsiz\w*", h):
        for i, a in idx:
            if i == -1:
                ms = [(a - y, v, c) for x, y, v, c in _money_all(h) if v >= 1000 and 0 <= a - y <= 40]
                if ms:
                    return min(ms)[1:]
    # 0c. a drawdown: the amount drawn, not the facility size (also a first draw, which is the facility's closing)
    if st == "drawn" or st == "closed" and re.search(r"(?i)\b(?:initial|first)\s+(?:draw\w*|advance|utili[sz]ation)", h):
        for s in [h] + sents[:5]:
            for x, y, v, c in _money_all(s):
                if v > 1000 and re.search(r"(?i)\b(?:draw\s*-?\s*down|drawdowns?|drew(?:\s+down)?|drawn(?:\s+down)?|advances?|draws?)"
                                          r"\s+(?:of\s+|down\s+)?(?:an\s+additional\s+|a\s+further\s+|approximately\s+)?$", s[max(0, x - 50):x]):
                    return v, c
    # 1. a tranche closed: the money in the sentence that closes it (the one naming this tranche first)
    if st == "closed" and _TRANCHE.search(h + " " + " ".join(ctx[:3])):
        lead = [s for s in sents[:3] if s not in body_ctx]
        cands = []
        for n, s in enumerate(body_ctx[:6] + lead):
            if _TRANCHE.search(s) and re.search(r"(?i)\bclosed\b|\bclosing\s+of\s+the\b|\btranche\s+closing\b|\bcomprised|"
                                                r"\bconsisted|\bissued|\bcomplet(?:ed|ion)|\bsold\b", s):
                for x, y, v, c in _money_all(s):
                    ctxm = re.sub(r"(?i)\bper\s+(?:unit|debenture)\b", " ", s[max(0, x - 60):y + 25])
                    if v <= 1000 or _NOT_PRINCIPAL.search(ctxm) or re.search(r"(?i)\bequity\b|\bshares\b", s[max(0, x - 80):x]):
                        continue
                    if re.search(r"(?i)\bunits\b", s[max(0, x - 60):x]) and not re.search(r"(?i)debenture|note",
                                                                                        s[max(0, x - 60):x]):
                        continue                          # the equity units sold beside the debentures
                    own = 0 if re.search(r"(?i)\b(?:this|the\s+(?:first|second|third|fourth|final))\s+(?:and\s+final\s+)?tranche\b"
                                         r"[^.]{0,230}$|\bincremental\b[^.]{0,40}$", s[:x]) else 1
                    if re.search(r"(?i)\bup\s+to|upsiz|increas\w*\s+to|to\s+date|pursuant\s+to\s+the\s+offering",
                                 s[max(0, x - 40):x] + " " + s[:30]):
                        continue
                    if own and re.search(r"(?i)aggregate|total", s[max(0, x - 40):x]):
                        continue
                    tr = [m2.end() for m2 in _TRANCHE.finditer(s[:x])]
                    gap = (x - tr[-1]) if tr else 10 ** 4
                    if re.search(r"(?i)\bincremental\b[^.]{0,40}$", s[:x]):
                        gap = 0
                    cands.append((own, gap, n, v, c))
        if not any(c[0] == 0 for c in cands):
            # 'has closed the second and final tranche ...' then 'The Company has issued 20 debentures for gross
            # proceeds of $1,000,000.'
            for j, s in enumerate(sents[:6]):
                if not (_TRANCHE.search(s) and re.search(r"(?i)\bclosed\b|\bcomplet(?:ed|ion)\b", s)) or \
                        any(v > 1000 and x > _TRANCHE.search(s).start() for x, y, v, c in _money_all(s)) or j + 1 >= len(sents):
                    continue
                s2 = sents[j + 1]
                if not re.search(r"(?i)debenture|\bnotes?\b|\bloan", s2) or (re.search(r"(?i)\bunits?\b", s2) and
                                                                            not re.search(r"(?i)debenture\s+units?", s2)):
                    break                                 # the equity units closed beside the debt
                for x, y, v, c in _money_all(s2):
                    if v > 1000 and re.search(r"(?i)(?:gross\s+)?proceeds\s+of\s*$|\bissued\b[^.$]{0,80}$", s2[max(0, x - 90):x]) \
                            and not re.search(r"(?i)\b(?:total|aggregate|to\s+date)\b", s2[max(0, x - 60):x]):
                        cands.append((0, 0, j + 1, v, c))
                        break
                break
        if cands:
            own, gap, n, v, c = min(cands)
            return v, c
    # 2. a stated principal amount
    for s in ctx:
        if _is_background(s) and st not in ("amended", "converted", "repaid"):
            continue
        m = _PRINCIPAL_RX.search(s)
        if m and _PER_UNIT.search(s[max(0, m.start() - 14):m.start()] + " " + s[m.start():m.end() + 60].split(",")[0]):
            m = None                                          # 'each Unit is a $1,000 principal amount of ...'
        if m and re.search(r"(?i)\b(?:insiders?|director|officer|control\s+person|subscriber|CEO|Chief\s+Executive|President|"
                           r"Chair(?:man)?)\b[^.]{0,100}$", s[:m.start()]):
            m = None
        if m and re.search(r"(?i)\beach\s+(?:\w+\s+){0,2}?(?:units?|debentures?|notes?)\b", s[:m.start()]):
            m = None                                          # 1.0.4: 'Each Debenture Unit shall consist of ... $10,000' 
        if m and st == "repaid" and re.search(r"(?i)\bproceeds\s+(?:from|of)\b[^.]{0,80}\b(?:offering|issu\w+)\s+of\s*$",
                                              s[:m.start()]):
            m = None                                          # 1.0.2: the new notes that paid for the redemption                                          # one insider's share: 'to one insider ... principal amount of'
        if m:
            v, c = _money_to_value(next(g for g in m.groups() if g))
            if v and v > 1000:
                return v, c
    # 3. money in the headline nearest the instrument, then in the sentences naming it
    best = None
    hl_spans = [(x, k2) for x, y, k2 in _instruments_in(h)]
    for i, a in idx:
        s = h if i == -1 else sents[i]
        if i >= 0 and _is_background(s) and st not in ("repaid", "converted", "amended"):
            continue
        for x, y, v, c in _money_all(s):
            if v <= 1000 or not _pick_money(s, x, y):
                continue
            around = s[max(0, x - 60):y + 60]
            around = around[:x - max(0, x - 60)] + re.sub(r"(?i)(?:US|C|CA)?\$\s?[\d.,]+\s+per\s+(?:common\s+)?(?:share|unit|ounce)", " ",
                                                            around[x - max(0, x - 60):])    # 1.0.4: another figure's price
            if _NOT_PRINCIPAL.search(around) and not re.search(r"(?i)loan|debenture|note|facility|credit|principal|prepay",
                                                               s[max(0, x - 30):y + 30]):
                continue
            if re.search(r"(?i)\binterest\b", s[y:y + 25]) and not re.search(r"(?i)principal", s[max(0, x - 40):y + 40]):
                continue
            if re.search(r"(?i)(?:US|C|CA|CAD|USD)?\$\s?[\d.,]*\d\s*(?:million|billion|M)?\s*\(\s*(?:approximately|approx\.?|about|"
                         r"or|equivalent\s+to|being|~)?\s*$", s[max(0, x - 50):x]):
                continue                                  # FIX3: 'US$115 million (approximately C$150 million)': the equivalent
            if re.match(r"(?i)\s*(?:(?:non-)?brokered\s+|equity\s+|unit\s+)?(?:private\s+placement|offering|"
                                    r"placement|financing|units?|flow[\s-]through)\b", s[y:y + 40]) and \
                    not re.match(r"(?i)\s*(?:\w+\s+){0,3}?(?:loans?|debentures?|notes?|facility|credit|bonds?)\b", s[y:y + 40]):
                continue                                  # FIX3: the amount sizes the private placement beside the debt
            if i == -1 and hl_spans and min(hl_spans, key=lambda t: abs(t[0] - x))[1] != k and \
                    abs(min(hl_spans, key=lambda t: abs(t[0] - x))[0] - x) < abs(x - a):
                continue                                  # the headline sizes another instrument
            d = abs(x - a) + (0 if i == -1 else 1000 * (1 + i))
            if i >= 0 and re.search(r":\s*[-\u2013\u2022]\s", s):
                if re.search(r"\s[-\u2013\u2022]\s", s[min(y, a):max(x, a)]):
                    continue                              # FIX3: another list item's amount ('- A of $X - B of $Y')
                d = 1000 * (1 + i) + a + 0.001 * abs(x - a)   # FIX3: in a list, the first item of this kind
            if best is None or d < best[0]:
                best = (d, v, c)
    if best:
        v, c = best[1], best[2]
        # 'up to US$75 million' in the headline is the accordion when the body commits a smaller amount first
        for s in body_ctx:
            ms = _money_all(s)
            for n2, (x, y, v2, c2) in enumerate(ms):
                if abs(v2 - v) <= 0.005 * v and n2 > 0 and re.search(r"(?i)(?:increase|expand|upsize)\w*\s+(?:up\s+)?to\s*$|"
                                                                     r"accordion[^.$]{0,30}$", s[max(0, x - 40):x]):
                    if ms[0][2] < v and ms[0][2] >= 1000:
                        return ms[0][2], ms[0][3] or c
        return v, c
    # 4. nothing near the instrument: a background sentence may still size it (an update on an announced facility)
    for s in body_ctx[:8]:
        for x, y, v, c in _money_all(s):
            if v > 1000 and _pick_money(s, x, y) and not _NOT_PRINCIPAL.search(s[max(0, x - 60):y + 60]) and \
                    re.search(r"(?i)loan|debenture|note|facility|credit|principal|prepay", s[max(0, x - 80):y + 80]):
                return v, c
    # 5. FIX3: the lead says what the company borrows ('has agreed to borrow up to $200,000 from three directors')
    for s in sents[:3]:
        m = re.search(r"(?i)\bborrow(?:ed|s|ing)?\s+(?:up\s+to\s+|an?\s+(?:aggregate|total)\s+(?:of\s+)?|approximately\s+)?" + _MONEY_TXT, s)
        if m:
            v, c = _money_to_value(m.group(1))
            if v and v > 1000:
                return v, c
    return None, None


def _currency_for(v, c, h, ctx, cur_default):
    if c:
        return c
    if re.search(r"\b(?:U\.S\.\s+)?(?:DOE|Department\s+of\s+Energy|EXIM|Export-Import\s+Bank\s+of\s+the\s+United\s+States|"
                 r"U\.S\.\s+International\s+Development\s+Finance|DFC)\b", h + " " + " ".join(ctx[:4])):
        return "USD"
    for s in ctx:
        for x, y, v2, c2 in _money_all(s):
            if c2 and v and abs(v2 - v) <= 0.01 * v:
                return c2
    return cur_default or "CAD"


_PERSON_LENDER = re.compile(r"(?:\bfrom|\bby|\bwith)\s+(?:a\s+|its\s+|the\s+Company's\s+)?(?:director|officer|CEO|Chief\s+Executive\s+"
                            r"Officer|Chairman|Chair|President|insider|shareholder|largest\s+shareholder),?\s*(?:Mr\.|Ms\.|Dr\.)?\s*"
                            r"([A-Z][a-z]+(?:\s+[A-Z]\.)?\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?)\b|\b([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:intends\s+"
                            r"to\s+|has\s+agreed\s+to\s+|will\s+)?(?:acquire|subscribe[d]?|purchase[d]?)\s+(?:for\s+)?(?:the\s+)?"
                            r"(?:Notes|Debentures|Loan)\b|\b(?:Chairman|CEO|President|Director|Chief\s+Executive\s+Officer)\s+"
                            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:has\s+)?(?:initiated|elected|agreed|advanced|lent|provided)\b[^.]{0,80}?"
                            r"\b(?:his|her|a)\s+(?:\w+\s+){0,2}loan\b|\b(?:Debenture|Note|Loan)\s*holder,?\s+(?:Mr\.|Ms\.|Dr\.)\s*"
                            r"([A-Z][a-z]+\s+[A-Z][a-z]+)\b")
_NOT_PERSON = re.compile(r"(?i)^(?:The|This|Such|Each|Any|All|Our|Its|Their|Canada|Ontario|British|North|South|New|United|"
                         r"Chief|Board|Company|Corporation|Nevada|Quebec|Toronto|Vancouver|Private|Capital|Gold|Silver|Copper)\b")
_AGENT_AFTER = re.compile(r"(?i)^[^.]{0,40}?(?:\bas|,)\s+(?:the\s+|its\s+)?(?:[\w-]+\s+){0,3}(?:tender|information|depositary|dealer|trustee|"
                          r"agent|underwriter|bookrunner|financial\s+advis[oe]r|legal\s+counsel|lead\s+arranger|initial\s+"
                          r"purchaser|placement\s+agent|manager)s?\b")


_LENDER_FULL = {"DOE": "U.S. Department of Energy (DOE)", "EDC": "Export Development Canada (EDC)",
                "EXIM": "Export-Import Bank of the United States (EXIM)", "BDC": "Business Development Bank of Canada (BDC)",
                "EBRD": "European Bank for Reconstruction and Development (EBRD)", "BMO": "Bank of Montreal (BMO)",
                "RBC": "Royal Bank of Canada (RBC)", "TD": "Toronto-Dominion Bank (TD)",
                "CIBC": "Canadian Imperial Bank of Commerce (CIBC)"}


# FIX5: the lender named by its role in the sentence (a name, an optional title, legal-form endings)
_NM = (r"((?:(?:Mr|Ms|Mrs|Dr)\.\s*|\d{5,9}\s+)?[A-Z][\w'&.\-]*(?:(?:\s+(?:&|and|of|de|du)\s+|\s+&?\s*)"
       r"(?:[A-Z0-9][\w'&.\-]*|\([A-Z][\w.\s]{0,18}\)|[\"\u201c][A-Z][a-z]+[\"\u201d])){0,10})")
_LEGAL_TAIL = re.compile(r"(?:\b(?:Corp(?:oration)?|Inc|Ltd|LTD|Limited|LLC|L\.L\.C|LP|L\.P|Pty|PTE|Pte|S\.A|SAS|GmbH|AG|"
                         r"PLC|plc|Plc|Ltda|N\.V|B\.V|ULC|KG|DMCC|Company|Trust|Fund|Bank)\.?)$")
_DEF_LENDER = re.compile(r"\s*\(\s*(?:the\s+|collectively,?\s+(?:the\s+)?|each\s+a\s+|together,?\s+(?:the\s+)?)?[\"\u201c]\s*"
                         r"L\s?e\s?n\s?d\s?e\s?r\s?s?\s*[\"\u201d]\s*\)")
_ROLE = (r"(?:(?:one|two|three|four|certain|some|each)\s+of\s+)?(?:the\s+|its\s+|our\s+|a\s+|an\s+)?"
         r"(?:(?:existing|current|major|largest|significant|principal|strategic|controlling|founding|long-?time|arm'?s[\s-]+length)\s+)*"
         r"(?:lenders?|shareholders?|directors?|officers?|insiders?|investors?|noteholders?|debentureholders?|"
         r"(?:Executive\s+)?Chair(?:man)?(?:\s+and\s+(?:CEO|Chief\s+Executive\s+Officer))?|CEO|President|Chief\s+Executive\s+Officer)"
         r"(?:\s+of\s+the\s+(?:Company|Corporation))?\s*,?\s+")
_ROLE_CUE = re.compile(r"(?i:\b(?:from|with|by|owed\s+to|owing\s+to|due\s+to)\s+)(?:(?i:" + _ROLE + r")|(?=(?:Mr|Ms|Mrs|Dr)\.))" + _NM)
_ISSUED_TO = re.compile(r"(?i:\b(?:issu(?:ance|ed|e|ing)|sale|sold|placement|placed)\b(?:(?!\bto\b)[^.]){0,160}?\b(?:debentures?|"
                        r"notes?|units?|loans?)\b(?:\s*\([^)]{0,40}\))?\s+to\s+(?:" + _ROLE + r")?)" + _NM)
_CUE_LENDS = re.compile(_NM + r"\s+(?:will\s+lend|(?:has\s+|have\s+)?agreed\s+to\s+lend|has\s+(?:advanced|lent|loaned)|have\s+(?:advanced|"
                    r"lent|loaned)|lent|loaned)\b")
_DEBT_WORD_BEFORE = re.compile(r"(?i)\b(?:loans?|debentures?|notes?|facilit(?:y|ies)|credit|financing|debt|prepayment|agreements?|"
                               r"advances?|borrow\w*|lend\w*|indebtedness|interest(?:\s+payment)?|placement|Debt)\b(?:[^.]|\.(?=\S)){0,90}$")
_NOT_NAME = re.compile(r"(?i)^(?:the|this|that|such|each|any|all|our|its|their|company|corporation|issuer|lenders?|holders?|board|"
                       r"tsx|tsxv|cse|nyse|exchange|canadian|united|january|february|march|april|may|june|july|august|"
                       r"september|october|november|december|private|convertible|senior|secured|unsecured|series|tranche|"
                       r"offering|agreement|loan|note|notes|debenture|debentures|facility|credit|mi|multilateral|"
                       r"subscribers?|purchasers?|investors?|insiders?|directors?|officers?|mr|ms|dr|it|he|she|they|we|which|management)\b")


def _cue_clean(raw, self_rx, subject=False):
    o = re.sub(r"^(?:(?:Mr|Ms|Mrs|Dr)\.\s*)", "", raw.strip())
    o = re.sub(r"\s+[\"\u201c][A-Z][a-z]+[\"\u201d]", "", o)                 # 'First "Nick" Last'
    o = re.sub(r"(?:\s+(?:&|and|of|de|du))+$", "", o).strip(" ,;:")
    if not re.search(r"\b(?:Inc|Ltd|Corp|Co|S\.A|L\.P|N\.V|B\.V|Jr|Sr|[A-Z])\.$", o):
        o = o.rstrip(".")
    if not o or _NOT_NAME.match(o) or (self_rx and self_rx.search(o)):
        return None
    if re.fullmatch(r"(?i)(?:(?:limited|ltd|inc|incorporated|corp|corporation|co|company|llc|lp|l\.p|plc|gmbh|s\.a|sarl|"
                    r"pty|ag|ab|as|bv|nv|ltda|sas|srl)\.?[\s,]*)+", o):
        return None                                       # FIX5 rev b: a legal ending alone ("Limited") is no name
    if re.fullmatch(r"[A-Z]{2,5}", o):
        return o if subject and len(o) >= 3 else None
    if " " not in o and not _LEGAL_TAIL.search(o) and not subject:
        return None
    return o


def _title_case(s):
    w = re.findall(r"\b[A-Za-z][a-z]{2,}\b|\b[A-Z]{2,}\b", s)
    return len(w) >= 4 and sum(1 for x in w if x[0].isupper()) >= 0.7 * len(w)


def _cue_lender(sents, self_rx, stage, allsents=None):
    """FIX5: a name set up as the lender by the sentence itself: 'X (the "Lender")', 'from its largest
    shareholder, X', 'with Dr. X', 'debentures issued to X', 'X will lend / has advanced'."""
    pool = list(sents)
    if allsents and any(re.search(r"\b(?:the|The)\s+Lenders?\b", s) for s in sents):
        pool += [s for s in allsents if s not in sents]   # the row's sentences use the release's defined term
    for s in pool:
        for m in re.finditer(_NM + _DEF_LENDER.pattern, s):
            o = _cue_clean(m.group(1), self_rx)
            if o:
                return o
        m = re.search(r"\b(?:an?\s+)?(?:affiliate|company|entity)\s*" + _DEF_LENDER.pattern + r"\s*(?:of|controlled\s+by)\s+" + _NM, s)
        if m:
            o = _cue_clean(m.group(1), self_rx)
            if o:
                return o
    for s in sents:
        if _title_case(s):
            continue                                      # a headline in title case: its capitals are not names
        for rx in (_ROLE_CUE, _ISSUED_TO):
            for m in rx.finditer(s):
                if rx is _ROLE_CUE and not _DEBT_WORD_BEFORE.search(s[max(0, m.start() - 120):m.start()]):
                    continue
                if _other_party(s, m.start(), stage) or _AGENT_AFTER.match(s[m.end():]):
                    continue
                o = _cue_clean(m.group(1), self_rx)
                if o:
                    return o
        for m in _CUE_LENDS.finditer(s):
            o = _cue_clean(m.group(1), self_rx, subject=True)
            if o:
                return o
    return None


def _other_party(s, pos, stage):
    """1.0.4: a name that follows 'to repay ...' or an offtake is the lender of the debt being repaid or the offtake
    buyer, not this instrument's lender (unless this row is the repayment)."""
    return stage not in ("repaid", "terminated", "converted") and bool(re.search(
        r"(?i)\b(?:offtake|off-take|concentrate\s+(?:purchase|sales?)|to\s+(?:re)?pay|to\s+refinance|repayment\s+of)\b[^.]{0,150}$",
        s[max(0, pos - 170):pos]))


def _lender(sents, self_rx, side, stage=None, allsents=None):
    o = _cue_lender(sents, self_rx, stage, allsents)
    if o:
        return o
    for s in sents:
        for m in _KNOWN_LENDERS.finditer(s):
            name = m.group(0)
            if self_rx and self_rx.search(name):
                continue
            pre = s[max(0, m.start() - 45):m.start()]
            post = s[m.end():m.end() + 45]
            if _AGENT_AFTER.match(post):
                continue
            if _other_party(s, m.start(), stage):
                continue                                  # 1.0.4: the offtake buyer, or the lender of the debt being repaid
            if not re.search(
                    r"(?-i:loan|facilit|credit|debenture|note|lend|financing|debt|borrow|advance|prepay|Loan|Facility|Debenture|Note|"
                    r"Credit|Debt|Lender|Prepayment)", s[max(0, m.start() - 220):m.end() + 120]):
                continue                                  # 1.0.4: a known lender named for something else (a share deal)
            if re.search(r"(?i)\b(?:from|with|by|to|lender|holder|provided\s+by|owed\s+to|owing\s+to|subscribed\s+by|"
                         r"funds\s+managed\s+by|of)\s*(?:the\s+)?(?:[\w&.,'-]+\s+){0,3}$", pre) or \
                    re.match(r"\s*(?:\([^)]{0,40}\)\s*)?(?:(?:Senior\s+)?(?:Secured\s+)?(?:Convertible\s+)?(?:Term\s+)?"
                             r"(?:Loan|Debenture|Facility|Credit|Debt|Prepayment|Note)s?\b|(?:has|have|will|agreed|is\s+providing|"
                             r"committed))", post, re.I):
                # 1.0.4: 'Nebari Loan' is the lender Nebari; an agency's initials carry its full name
                name = re.sub(r"(?:\s+(?:Loans?|Facilit(?:y|ies)|Debentures?|Notes?|Credit|Agreement|Term|Bridge|Convertible|"
                              r"Senior|Secured|Debt))+$", "", name)
                return _LENDER_FULL.get(name, name)
    for s in sents:
        m = re.search(r"(?i)\blenders?,?\s+being\s+", s)
        if m:
            om = _ORG.match(s[m.end():m.end() + 90])
            if om:
                o = _org_clean(om.group(1), self_rx)
                if o:
                    return o
        m = re.search(r"has\s+agreed\s+to\s+(?:loan|lend|advance)\s+(?:to\s+)?the\s+(?:Company|Corporation)\b", s) or re.search(
                      r"(?:will\s+provide|is\s+providing|has\s+agreed\s+to\s+(?:provide|lend|advance)|"
                      r"agreed\s+to\s+(?:provide|lend|advance)|will\s+lend|will\s+advance)\s+(?:the\s+Company\s+|[\w\s]{0,20})?"
                      r"(?:an?\s+|the\s+)?(?:(?:US|C|CA)?\$[\d.,]+\s*(?:million\s+)?)?(?:\w+\s+){0,2}(?:loan|facility|financing)", s)
        if m:
            toks = re.findall(r"\S+", s[max(0, m.start() - 80):m.start()])
            name = []
            for t in reversed(toks):
                if re.match(r"^[A-Z][\w&'\-.]*$", t) and not re.search(r"[,;:)\u201d\"]$", t) and len(name) < 4:
                    name.insert(0, t)
                elif name and re.match(r"^(?:LLC|Inc|Ltd|LP|Corp|Limited|AG)\.?$", name[0]) and re.match(r"^[A-Z][\w&'\-.]*,$", t) \
                        and len(name) < 4:
                    name.insert(0, t)                     # 'Trexs Investments, LLC'
                else:
                    break
            o = _org_clean(" ".join(name), self_rx) if name else None
            if o and not re.match(r"(?i)(?:The|This|It|Such|Each|Company|Corporation)\b", o):
                return o
    for s in sents:
        for m in re.finditer(r"(?i)\b(?:from|with|provided\s+by|made\s+by|arranged\s+by|led\s+by|subscribed\s+for\s+by|"
                             r"owed\s+to|owing\s+to)\s+(?:the\s+|its\s+)?", s):
            pre = s[max(0, m.start() - 70):m.start()]
            if not re.search(r"(?i)\b(?:loans?|debentures?|notes?|facilit(?:y|ies)|credit(?:\s+agreement)?|financing|debt|prepayment|"
                             r"agreements?|advances?|borrow\w*|lend\w*|indebtedness)\b[^.]{0,50}$", pre) or \
                    re.search(r"(?i)\b(?:purchase|acquisition|acquire|buy|obtain(?:ed)?|available|directed|requests?|copies)\b[^.]{0,40}$", pre):
                continue
            tail = s[m.end():m.end() + 90]
            if side == "borrower" and re.match(r"(?i)(?:an?\s+)?(?:arm'?s|arms|third|unrelated|certain|private|institutional|"
                                                 r"accredited|strategic|existing|new|several|a\s+group|director|officer)", tail):
                continue
            nm = re.match(r"(\d{6,8}\s+(?:B\.?\s?C\.?|Ontario|Alberta|Canada|Qu[e\u00e9]bec)\s+(?:Ltd|Inc|Corp)\.?)", tail)
            if nm:
                return nm.group(1)
            om = _ORG.match(tail)
            if om and not _AGENT_AFTER.match(tail[om.end():]) and not _other_party(s, m.end(), stage):
                o = _org_clean(om.group(1), self_rx)
                if o and (not re.search(r"(?i)\b(?:Resources|Mining|Metals|Minerals)\b$", o) or
                          re.search(r"(?i)\b(?:Corp|Inc|Ltd|Limited|AG|LLC|LP)\.?$", o)):
                    return o
            # FIX5: a full legal name the short form misses ('X Global Resources Fund IV LP', 'X Mining Company,
            # Inc.', 'X & Sons LLC', 'X (Hong Kong) Corporation Limited')
            nm = re.match(_NM + r"(?:,\s*(?:Inc|LLC|Ltd|L\.P|LP)\.?)?", tail)
            if nm and not _AGENT_AFTER.match(tail[nm.end():]) and not _other_party(s, m.end(), stage):
                o = _cue_clean(nm.group(0), self_rx)
                lt = list(re.finditer(_LEGAL_TAIL.pattern[:-1] + r"(?=\s|$)", o or ""))
                if lt:
                    return o[:lt[-1].end()]
    for s in sents:
        m = _PERSON_LENDER.search(s)
        if m:
            nm = m.group(1) or m.group(2) or m.group(3) or m.group(4)
            if nm and not _NOT_PERSON.match(nm) and not (self_rx and self_rx.search(nm)):
                return nm
    for s in sents:
        m = re.search(r"(\d{6,8}\s+(?:B\.?\s?C\.?|Ontario|Alberta|Canada|Qu[e\u00e9]bec)\s+(?:Ltd|Inc|Corp)\.?)", s)
        if m and re.search(r"(?i)\blend|\bloan|\bholder", s):
            return m.group(1)
    return None


def _borrower(sents, self_rx):
    for s in sents:
        # FIX5 (rule DL): 'credit facility (the "Facility") to a private royalty company ("PrivCo")' gives that
        # description and its defined name; 'a $1,725,000 secured demand loan ... with X' that the company holds
        m = re.search(r"(?i)\b(?:loan|facility|financing|note)\b[^.]{0,120}?\bto\s+an?\s+((?:arm'?s[\s-]length\s+)?private\s+"
                      r"(?:[\w-]+\s+){0,3}?(?:company|corporation|entity))\s*\(\s*[\"\u201c]([^\"\u201d]{2,30})[\"\u201d]", s)
        if m:
            return "%s (%s)" % (m.group(1), m.group(2))
        m = re.search(r"(?i:\b(?:loan|credit\s+facility)\b[^.]{0,100}?\bwith\s+)([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,4})", s)
        if m and re.search(r"(?i)\b(?:hold|holds|held|lend|lent|advanced?)\b", s):
            o = _org_clean(m.group(1), self_rx)
            if o:
                return o
    for s in sents:
        # 1.0.4: 'makes available to SRG', 'in favour of Kuya', 'a bridge loan (the "Loan") to Anfield'
        m = re.search(r"\bmakes?\s+available\s+to\s+([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,4})|\bin\s+favou?r\s+of\s+([A-Z][\w&.'\-]*"
                      r"(?:\s+[A-Z][\w&.'\-]*){0,4})|\b(?:loan|facility|note)\b[^.]{0,80}?\bto\s+((?!The\b|the\b)[A-Z][\w&.'\-]*"
                      r"(?:\s+[A-Z][\w&.'\-]*){0,4}(?:,\s*(?:LLC|Inc|Ltd)\.?)?)", s)
        if m:
            o = _org_clean(next(g for g in m.groups() if g), self_rx)
            if o and not re.match(r"(?i)(?:Fund|Finance|Pay|Repay|Support|Complete|Purchase|Acquire|Settle|Provide|Close|Be)\b", o):
                return o
        m = re.search(r"(?i)\bdebenture\s+units\s+of\s+([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5}\s+(?:Limited|Ltd|Inc|Corp)\.?)"
                      r"|\bdebentures?\s+(?:of|issued\s+by)\s+([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5})|\bloan\s+to\s+"
                      r"([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,4}(?:,\s*(?:LLC|Inc|Ltd)\.?)?)", s)
        if m:
            o = _org_clean(next(g for g in m.groups() if g), self_rx)
            if o:
                return o
    return None


def _fill_row(k, st, side, h, sents, idx, self_rx, cur_default):
    r = _empty()
    r.update(instrument=k, stage=st, side=side)
    ctx = _context(k, idx, h, sents)
    v, c = _principal(k, st, h, sents, idx, ctx, cur_default)
    if v is not None:
        r["principal"] = v
        r["currency"] = _currency_for(v, c, h, ctx, cur_default)
    for s in ctx:
        m = re.search(r"(?i)(?:aggregate|total)\s+(?:gross\s+)?(?:proceeds|funds|principal(?:\s+amount)?)\s+(?:of\s+)?"
                      r"(?:raised\s+)?(?:to\s+date\s+)?(?:of\s+)?(?:(US|C|CA)\s?)?\$\s?" + _NUM + r"(?:\s*(million))?[^.]{0,80}?"
                      r"(?:across|under|in)\s+(?:all|both|the\s+(?:first|two|three|debenture|offering|financing))", s) or \
            re.search(r"(?i)(?:bringing|brings)\s+the\s+(?:aggregate|total)[^.$]{0,60}?(?:(US|C|CA)\s?)?\$\s?" + _NUM +
                      r"(?:\s*(million))?", s)
        if m and st == "closed" and _TRANCHE.search(h + " " + s):
            tv = float(m.group(2).replace(",", "")) * (1e6 if m.group(3) else 1)
            if r["principal"] is None or tv > r["principal"]:
                r["principal_total"] = tv
            break
    tctx = ctx
    if st in ("proposed", "signed", "closed", "drawn"):
        # 1.0.2: "to fund the concurrent tender offer for its existing 6.875% senior notes due 2027" sizes nothing
        tctx = [s for s in ctx if not _OLD_SERIES.search(s)]
    r["rate_pct"], r["rate_text"] = _rate(tctx, st)
    dl = T._dateline(" ".join(sents[:2]))
    r["maturity"] = _maturity(tctx, st)
    if dl and r["maturity"] and r["maturity"] == dl:
        m0 = T._DATE.search(" ".join(sents[:2]))
        r["maturity"] = _maturity(tctx, st, skip=m0.group(0) if m0 else None)
    if r["maturity"] is None:
        r["term_months"] = _term_months(tctx)
    if side == "borrower":
        r["lender"] = _lender(ctx, self_rx, side, st, sents)
    else:
        r["borrower"] = _borrower(ctx, self_rx) or _lender(ctx, self_rx, side)
        for s in [h] + sents[:8]:
            pw = _PROVIDE_WITH.search(s)
            if pw:                                        # 1.0.2: "agreed to provide G Mining Ventures Corp. with"
                r["borrower"] = _org_clean(pw.group(1), self_rx) or pw.group(1).strip()
                break
    r["related_party"] = 1.0 if any(_RELATED.search(s) for s in ctx) else 0.0
    r["secured"] = _secured(ctx, k)
    r["conversion_price"], r["conversion_text"] = _conversion(ctx, k, r.get("currency"))
    if k in ("convertible_debenture", "convertible_note", "notes", "loan", "credit_facility"):
        r["warrants"], r["warrant_strike"] = _warrants(ctx)
    proj = None
    for s in ctx[:6]:
        f = PN.find(s)
        if f:
            proj = f[0][1]
            break
    if proj:
        proj = re.sub(r"(?i)^(?:to\s+)?(?:start|restart|fund|fully\s+fund|advance|develop|build|complete|support|finance)\s+", "", proj)
    r["project"] = PN.bare(proj) if proj else None
    for s in ctx[:6]:
        d = re.search(r"(?i)\b(?:on|dated(?:\s+as\s+of)?|effective)\s+(" + T._DATE_RX + r")", s)
        if d:
            dd = _to_date(d.group(1))
            if dd:
                r["date"] = dd
                break
    if r["date"] and (r["maturity"] and r["date"][:10] == str(r["maturity"])[:10] or
                      dl and _far(r["date"], dl)):
        r["date"] = None                                  # 1.0.2: the maturity, or an old agreement's date
    if st == "repaid" and _PARTIAL.search(h + " " + " ".join(sents[:4]) + " " + " ".join(ctx[:4])) and \
            not re.search(r"(?i)\bany\s+and\s+all\b", h + " " + " ".join(sents[:3])):
        r["purpose"] = "Partial repayment"
    if k == "notes" and side == "borrower" and r.get("lender") and re.search(r"(?i)\bdebentures?\b", " ".join(ctx[:4])) and \
            not re.search(r"(?i)\b(?:senior\s+(?:secured\s+|unsecured\s+)?notes|bonds?)\b", " ".join(ctx[:4])):
        r["instrument"] = "loan"                          # 1.0.2: Glencore's senior secured debenture to Abcourt
    return r


_OLD_SERIES = re.compile(r"(?i)\b(?:existing|outstanding)\s+(?:[\d.]+\s?%\s+)?(?:senior\s+)?(?:secured\s+|unsecured\s+)?"
                         r"(?:second[\s-]lien\s+|first[\s-]lien\s+)?(?:notes|debentures|bonds)\b|\b(?:redeem|redemption\s+of|"
                         r"tender\s+offers?\s+for|repurchase|refinanc\w*)\s+(?:all\s+of\s+|in\s+full\s+)?(?:its|the)\s+"
                         r"(?:existing\s+|outstanding\s+)?(?:US\$[\d.,]+\s*(?:million|billion)?\s+(?:aggregate\s+principal\s+"
                         r"amount\s+(?:outstanding\s+)?of\s+)?)?[\d.]+\s?%")
_PARTIAL = re.compile(r"(?i)\bpartial(?:ly)?\s+(?:re)?pa(?:id|y\w*)\b|\bpartial\s+(?:redemption|settlement|repurchase|"
                      r"prepayment|buy-?back)\b|\brepa\w+\s+(?:a\s+)?portion\s+of\b|\bmaximum\s+(?:aggregate\s+principal\s+"
                      r"amount|tender\s+amount)\b|\bfor\s+a\s+portion\s+of\s+its\b")


def _far(d, dl, days=400):
    from datetime import date as _d
    try:
        a, b = _d.fromisoformat(str(d)[:10]), _d.fromisoformat(str(dl)[:10])
    except ValueError:
        return False
    return (a - b).days > 45 or (b - a).days > days


_DONE = re.compile(r"(?i)\b(?:was|were|has\s+been|have\s+been|had\s+been|is\s+now)\s+(?:\w+\s+){0,2}(?:repaid|retired|redeemed|"
                   r"terminated|cancell?ed|settled|extinguished|discharged)\b|\bextinguished\b|\b(?:repaid|retired|redeemed)\s+(?:in\s+full|"
                   r"the|its|all|a|an)\b|\bused\s+[^.]{0,100}\bto\s+(?:fully\s+)?(?:repay|retire|redeem)\b|\bpartial\s+"
                   r"(?:conversion\s+and\s+)?repayment\b")
_MAYBE = re.compile(r"(?i)\bmay\s+be\s+(?:repaid|redeemed|prepaid)|\bat\s+the\s+option\s+of\b|\bprior\s+to\s+maturity\b|"
                    r"\brequired\s+to\s+repay\b|\bsubject\s+to\s+the\s+satisfaction\b|\bconditions?\b")


_PAID_WORDS = re.compile(r"(?i)\brepa(?:id|y|ys|ying|yments?)\b|\bredeem\w*|\bredemption\b|\bpaid\b|\bpay(?:s|ing)?\s+(?:off|down)\b|"
                         r"\bsettle\w*|\bextinguish\w*|\bbought\s+back\b|\brepurchas\w*|\bshares?[\s-]+for[\s-]+debt\b|\bconver\w+")


def _facility_ending(k, st, txt):
    """A credit facility retired or closed with nothing said to be repaid is terminated, not repaid (label guide:
    terminated = cancelled or lapsed; repaid needs money or shares paid)."""
    if k == "credit_facility" and st == "repaid" and re.search(r"(?i)\bretir\w+", txt) and not _PAID_WORDS.search(txt):
        return "terminated"
    return st


def _extra_rows(h, sents, per, rows, self_rx, cur_default):
    """Another instrument the lead reports with its own event: an old facility repaid or retired beside a new one,
    or a second loan from another lender."""
    out = []
    if not rows:
        return out
    have = {(r["instrument"], r["principal"]) for r in rows}
    principals = {r["principal"] for r in rows if r["principal"]}
    lenders = {(r.get("lender") or "").lower() for r in rows}
    seen = set()
    for k in ("loan", "credit_facility", "notes", "convertible_debenture", "convertible_note"):
        for i, a in per.get(k, []):
            if not (0 <= i <= 10) or i in seen:
                continue
            s = sents[i]
            if _is_background(s):
                continue
            st = _pick_stage(_stage_hits(s, around=a, window=90), nearest=True)
            if st not in ("repaid", "terminated"):
                continue
            if any(r["instrument"] == k and (r["stage"] == st or r["stage"] in ("repaid", "terminated", "converted")) for r in rows):
                continue                                  # 1.0.4: one ending per instrument ('redeemed ... and cancelled')
            if not _DONE.search(s) or _MAYBE.search(s):
                continue                                  # redemption terms, a fee owed at maturity: nothing happened
            vals = [v for x, y, v, c in _money_all(s) if v >= 1000 and not _NOT_PRINCIPAL.search(s[max(0, x - 40):y + 40])
                    and not re.search(r"(?i)\binterest\b|\bfees?\b", s[max(0, x - 50):x] + s[y:y + 12])]
            if not vals or any(abs(vals[0] - p) <= 0.02 * p for p in principals):
                continue
            own = [kk for x, y, kk in _instruments_in(s) if x <= a < y + 5 or abs(x - a) < 3]
            st = _facility_ending(own[0] if own else k, st, s)
            r = _empty()
            r.update(instrument=own[0] if own else k, stage=st, side="borrower", principal=vals[0],
                     currency=_currency_for(vals[0], _money_all(s)[0][3], h, [s], cur_default))
            r["lender"] = _lender([s], self_rx, "borrower", st)
            r["related_party"] = 1.0 if _RELATED.search(s) else 0.0
            r["secured"] = _secured([s])
            out.append(r)
            principals.add(vals[0])
            seen.add(i)
    # two loans from two named lenders ("Loan #1 ... Loan #2")
    if any(r["instrument"] == "loan" for r in rows):
        ents = []
        for i, s in enumerate(sents[:14]):
            m = re.search(r"(?i)\bentered\s+into\s+an?\s+(?:\w+\s+)?loan\s+agreement\s+with\s+", s)
            if m:
                om = _ORG.match(s[m.end():m.end() + 90])
                if om:
                    o = _org_clean(om.group(1), self_rx)
                    if o:
                        ents.append((i, o))
        if len({o.lower() for i, o in ents}) >= 2:
            first = next(r for r in rows if r["instrument"] == "loan")
            for n, (i, o) in enumerate(ents):
                seg = sents[i:(ents[n + 1][0] if n + 1 < len(ents) else min(len(sents), i + 8))]
                vals = [v for s in seg for x, y, v, c in _money_all(s) if v >= 1000]
                if n == 0:
                    first["lender"] = o
                    if vals:
                        first["principal"] = vals[0]
                    first["maturity"] = _maturity(seg, first["stage"])
                    first["term_months"] = None if first["maturity"] else _term_months(seg)
                    first["rate_pct"], first["rate_text"] = _rate(seg)
                    first["secured"] = _secured(seg)
                    continue
                if o.lower() in lenders:
                    continue
                r = _empty()
                r.update(instrument="loan", stage=first["stage"], side="borrower", lender=o,
                         principal=vals[0] if vals else None, currency=first["currency"])
                r["rate_pct"], r["rate_text"] = _rate(seg)
                r["maturity"] = _maturity(seg, r["stage"])
                r["term_months"] = None if r["maturity"] else _term_months(seg)
                r["secured"] = _secured(seg)
                r["related_party"] = 1.0 if any(_RELATED.search(s) for s in seg) else 0.0
                out.append(r)
    return out


_INT_AMT_AFTER = re.compile(r"(?i)^\s*(?:in|of)\s+(?:\w+\s+){0,2}interest\b")
_INT_SHARES = re.compile(r"(?i)(\d{1,3}(?:,\d{3})+|\d{4,})\s+(?:common\s+shares|shares|Common\s+Shares)\b")


def _interest_row(h, sents, per, self_rx, cur_default):
    """Interest paid (in shares or cash) on a debt already outstanding: a row with stage interest_paid, the interest
    paid as its amount and the shares issued for it in conversion_text (rule DI, changed 2026-09-24)."""
    kinds = [k for k in INSTRUMENTS if k in per]
    txt = h + " " + " ".join(sents[:4])
    if "convertible_debenture" in kinds or (not kinds and re.search(r"(?i)debenture", txt)):
        k = "convertible_debenture" if re.search(r"(?i)convertible", txt) or "convertible_debenture" in kinds else "notes"
    else:
        k = kinds[0] if kinds else ("notes" if re.search(r"(?i)\bnotes?\b", txt) else "loan")
    r = _empty()
    r.update(instrument=k, stage="interest_paid", side="borrower")
    amts, used, cur = [], [], None
    for s in sents[:14]:
        for x, y, v, c in _money_all(s):
            if v < 100 or re.search(r"(?i)\bon\s+(?:the\s+)?$", s[max(0, x - 8):x]) or re.match(
                    r"(?i)\s*(?:(?:senior|secured|unsecured|subordinated|convertible|of)\s+)*(?:debentures?|notes?|loans?|credit|"
                    r"facilit)", s[y:y + 50]):
                continue                                  # 'US$25 Million Convertible Debenture': the debt, not the interest
            if _INT_AMT_AFTER.match(s[y:y + 30]) or (re.search(r"(?i)\b(?:pay\w*|repay\w*|satisf\w*|settle\w*)\b[^.$]{0,40}$",
                                                               s[max(0, x - 50):x])
                                                     and re.search(r"(?i)\binterest\b", s[max(0, x - 40):x] + s[y:y + 120])) or (
                    re.search(r"(?i)\binterest\b(?:(?!principal|debenture|note|loan|value)[^.$]){0,80}$", s[max(0, x - 90):x]) and
                    re.match(r"(?i)[^.]{0,60}?\b(?:exchanged|settled|paid|satisfied|converted|through|by\s+(?:the\s+)?issu\w+|"
                             r"in\s+(?:common\s+)?shares|for\s+[\d,]+\s+(?:common\s+)?(?:shares|units))", s[y:y + 70])):
                # 1.0.4: 'interest due of $30,000 was exchanged for 600,000 common shares' 
                if not any(abs(v - a) <= 0.005 * v for a in amts):
                    amts.append(v)
                    used.append(s)
                    cur = cur or c
                break
    if amts:
        r["principal"] = round(sum(amts), 2)
        r["currency"] = _currency_for(r["principal"], cur, h, used, cur_default)
    shares, price = [], None
    for s in (used + [t for t in sents[:8] if t not in used]):
        if shares and s not in used:
            break
        m = _INT_SHARES.search(s)
        if m:
            shares.append(int(m.group(1).replace(",", "")))
        pm = re.search(r"(?i)\b(?:at\s+a\s+|at\s+the\s+)?(?:deemed\s+)?(?:offering\s+)?price\s+of\s+((?:US|C|CA)?\$\s?\d+(?:\.\d+)?)\s+per", s)
        if pm and price is None:
            price = pm.group(1).replace(" ", "")
    if shares:
        r["conversion_text"] = "interest paid in {:,} common shares".format(sum(shares)) + (" at " + price if price else "")
    lead = sents[:6]
    r["lender"] = _lender(lead, self_rx, "borrower", "interest_paid")
    r["related_party"] = 1.0 if any(_RELATED.search(s) for s in sents[:14]) else 0.0
    return r


# ------------------------------------------------------------------ records
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["rows"]:
        return [F.Record(KIND, facts=[F.Fact("is_debt", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"] or "none")], confidence=0.0)]
    out = []
    for r in a["rows"]:
        fs = [F.Fact("is_debt", value_num=1.0)]
        for k in TXT_FIELDS:
            v = r.get(k)
            if v not in (None, ""):
                fs.append(F.Fact(k, value_text=str(v)[:300]))
        for k in NUM_FIELDS:
            v = r.get(k)
            if v is not None:
                fs.append(F.Fact(k, value_num=float(v)))
        out.append(F.Record(KIND, facts=fs, confidence=1.0))
    return out


def parse_records(rows_by_ordinal):
    """{ordinal: [(field, seq, value_num, value_text)]} -> the analyse()-shaped dict."""
    rows = []
    for ordinal in sorted(rows_by_ordinal):
        r = {k: None for k in TXT_FIELDS + NUM_FIELDS}
        yes = False
        for field_, seq, num, text in rows_by_ordinal[ordinal]:
            if field_ == "is_debt":
                yes = num == 1.0
            elif field_ in TXT_FIELDS:
                r[field_] = text
            elif field_ in NUM_FIELDS:
                r[field_] = num
        if yes and r["instrument"]:
            for b in ("related_party", "secured"):
                if r[b] is not None:
                    r[b] = bool(r[b])
            rows.append(r)
    return {"is_debt": bool(rows), "rows": rows}


JUDGED = ("instrument", "stage", "side", "principal", "currency", "principal_total", "rate_pct", "rate_text", "maturity",
          "term_months", "lender", "borrower", "related_party", "secured", "conversion_price", "warrants", "warrant_strike")


def to_prediction(records):
    if not records:
        return None
    rows = {i: [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts] for i, rec in enumerate(records)}
    p = parse_records(rows)
    if not p["rows"]:
        return None
    return {"rows": [{k: r.get(k) for k in JUDGED} for r in p["rows"]]}


# The fingerprint (FP_AUTO_V1): this file whole, plus exactly the code it reaches in the Technical reader (T.) and the
# shared project-name helper (PN.); see portal/fingerprint.py.
SPEC = F.ExtractorSpec(NAME, VERSION, KIND, TAG, extract, FP.code_sha(__file__))


# ------------------------------------------------------------------ self-test
def self_test(verbose=False):
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))
        elif verbose:
            print("  ok   %s" % name)

    fill = " The Company is advancing its gold projects in Ontario and continues to review opportunities." * 3
    lead = "Vancouver, British Columbia, March 2, 2026 -- ABC Gold Corp. (TSXV: ABC) (\"ABC\" or the \"Company\") "

    def rows(h, b, keys=("instrument", "stage", "side", "principal")):
        return [tuple(r[k] for k in keys) for r in analyse(h, lead + b + fill)["rows"]]

    eq("convertible debenture offering",
       rows("ABC Gold Announces $1,000,000 Convertible Debenture Offering",
            "is pleased to announce a non-brokered private placement of unsecured convertible debentures for gross proceeds of "
            "up to $1,000,000. The debentures bear interest at 10% per annum, mature 24 months from issuance and are "
            "convertible into common shares at a conversion price of $0.15 per share.",
            ("instrument", "stage", "principal", "rate_pct", "term_months", "secured", "conversion_price")),
       [("convertible_debenture", "proposed", 1000000.0, 10.0, 24, 0.0, 0.15)])
    eq("loan closed from a named lender",
       rows("ABC Gold Closes US$5 Million Secured Term Loan with Delta Capital LLC",
            "has closed a US$5 million secured term loan with Delta Capital LLC. The loan bears interest at 12% per annum "
            "and matures on December 31, 2027.",
            ("instrument", "stage", "principal", "currency", "lender", "secured", "maturity")),
       [("loan", "closed", 5000000.0, "USD", "Delta Capital LLC", 1.0, "2027-12-31")])
    eq("credit facility repaid",
       rows("ABC Gold Announces Repayment of C$5 Million Credit Facility",
            "has repaid in full its C$5 million credit facility."), [("credit_facility", "repaid", "borrower", 5000000.0)])
    eq("interest paid in shares is an interest_paid row (rule DI, changed 2026-09-24)",
       rows("ABC Gold Issues Shares to Pay Debenture Interest",
            "The Company has elected to pay $52,500 in interest accrued on its convertible debentures by issuing "
            "250,000 common shares."), [("convertible_debenture", "interest_paid", "borrower", 52500.0)])
    eq("pdf gaps: '$3 .2895', '$1,1 18,000', 'due 20 30', 'six -month', 'eleven cents'",
       [_prepare("", "$3 .2895 $1,1 18,000 notes due 20 30 a six -month loan at eleven cents")[1]],
       ["$3.2895 $1,118,000 notes due 2030 a six-month loan at $0.11"])
    eq("'Completes $7.5M Private Placement of ...' is closed",
       rows("XYZ Gold Completes $7.5M Oversubscribed Private Placement of Convertible Debentures",
            "XYZ Gold has closed its private placement of convertible debentures for gross proceeds of $7,500,000."),
       [("convertible_debenture", "closed", "borrower", 7500000.0)])
    eq("an advisor mandate is not a row",
       rows("ABC Gold Appoints Financial Advisor for Project Debt Financing",
            "has appointed XYZ Bank as financial advisor to arrange project debt financing for the Alpha Project."), [])
    eq("senior notes offering priced",
       rows("ABC Gold Announces Pricing of US$500 Million Senior Notes Due 2032",
            "has priced its offering of US$500 million aggregate principal amount of 7.25% senior notes due 2032.",
            ("instrument", "stage", "principal", "rate_pct", "maturity")),
       [("notes", "signed", 500000000.0, 7.25, "2032")])
    eq("maturity extended",
       rows("ABC Gold Extends Convertible Debentures",
            "has agreed with the holders of its 8% convertible debentures to extend the maturity date to June 30, 2028.",
            ("instrument", "stage", "maturity")),
       [("convertible_debenture", "amended", "2028-06-30")])
    eq("company as lender",
       rows("ABC Gold Advances Loan to Target",
            "has provided a US$250,000 loan to a private company in connection with a proposed transaction.",
            ("instrument", "stage", "side")),
       [("loan", "closed", "lender")])
    eq("a placement is not debt", rows("ABC Gold Closes Private Placement", "has closed a private placement of units."), [])
    recs = extract("ABC Gold Closes US$5 Million Secured Term Loan",
                   lead + "has closed a US$5 million secured term loan. The loan bears interest at 12% per annum." + fill)
    p = to_prediction(recs)
    eq("round trip", [(x["instrument"], x["stage"], x["principal"], x["secured"]) for x in p["rows"]],
       [("loan", "closed", 5000000.0, True)])
    eq("no-debt record", to_prediction(extract("ABC Gold Closes Private Placement",
                                               lead + "has closed a private placement." + fill)), None)
    # 1.0.2 (2026-09-25)
    eq("agreed to provide another company with a loan: lender, US$ from the release note",
       rows("ABC Gold Announces $352.5 Million Financing Package with Delta Mining on the Alpha Project",
            "(in U.S. dollars unless otherwise noted) is pleased to announce a stream. Additionally, ABC Gold, through one "
            "of its wholly-owned subsidiaries, has agreed to provide Delta Mining Corp. (\"Delta\") with a $75 million "
            "secured term loan (the \"Term Loan\").", ("instrument", "side", "principal", "currency")),
       [("loan", "lender", 75000000.0, "USD")])
    eq("a tender offer extended is not yet a repayment",
       rows("ABC Gold Announces Extension of the Expiration Date of Cash Tender Offer to Purchase Any and All of Its "
            "Outstanding 6.875% Senior Notes Due 2027",
            "announces that it has extended the expiration date of its previously announced cash tender offer for its "
            "6.875% senior notes due 2027."), [])
    eq("a new offering does not take the terms of the notes it refinances",
       rows("ABC Gold Announces $750 Million Senior Notes Offering",
            "announces that it is launching an offering of $750 million aggregate principal amount of senior notes due "
            "2034. The Company intends to apply the gross proceeds to fund the concurrent tender offer for its existing "
            "6.875% senior notes due 2027.", ("instrument", "stage", "principal", "rate_pct", "maturity")),
       [("notes", "proposed", 750000000.0, None, "2034")])
    eq("a redemption is the notes redeemed, not the offering that paid for it",
       rows("ABC Gold Announces Redemption of 2027 Notes",
            "announces that it has completed the previously announced redemption of all of its outstanding 6.875% "
            "senior notes due 2027 (the \"2027 Notes\") in an aggregate of $41,878,000 outstanding principal amount. "
            "The Company redeemed the 2027 Notes using the proceeds from its previously announced offering of $1,000 "
            "million aggregate principal amount of 7.250% senior notes due 2034.", ("instrument", "stage", "principal")),
       [("notes", "repaid", 41878000.0)])
    eq("a partial repayment is marked",
       [r["purpose"] for r in analyse("ABC Gold Announces Partial Repayment of Debt Owed to EBRD",
                                      lead + "has entered into a debt settlement agreement with EBRD to repay C$1,149,270 "
                                             "owed under its convertible loan." + fill)["rows"]], ["Partial repayment"])
    eq("a covenant waiver is not a row",
       rows("ABC Gold and Lenders Sign Waiver on Liquidity Covenant",
            "and its lenders have signed a waiver of the liquidity covenant under its US$25 million credit facility."), [])
    eq("non-convertible is not convertible; previously issued is not a closing",
       rows("ABC Gold Announces Intention to Extend Maturity Dates of Previously Issued Convertible Debentures",
            "announces that it intends to extend the maturity date of its convertible debentures to February 28, 2027.",
            ("instrument", "stage")) + rows("ABC Gold Provides Financing Update",
            "announces that it has agreed to issue a non-interest bearing, unsecured, non- convertible promissory note "
            "in the principal amount of US$804,000.", ("instrument",)),
       [("convertible_debenture", "amended"), ("loan",)])
    eq("the maturity is not the stage date",
       [r["date"] for r in analyse("ABC Royalties Establishes Credit Facility of up to $150 Million",
                                   lead + "has entered into an agreement with Delta Bank for a revolving credit facility "
                                          "of $150 million. The RCF has a term of three years, maturing on August 14, "
                                          "2029." + fill)["rows"]], [None])
    eq("a chairman named in a greeting is not a related party",
       [r["related_party"] for r in analyse("ABC Gold Closes US$5 Million Secured Term Loan",
                                            lead + "Executive Chairman Robert Smith and President Jane Doe are pleased to "
                                                   "announce that the Company has closed a US$5 million secured term loan "
                                                   "with Delta Capital LLC." + fill)["rows"]], [0.0])
    eq("the company lending names the borrower; a director of the company lending is not the company",
       [(r["side"], r["borrower"]) for r in analyse("ABC Gold Announces Financing Package with Delta Mining",
            lead + "is pleased to announce a stream. Additionally, ABC Gold, through one of its wholly-owned subsidiaries, "
                   "has agreed to provide Delta Mining Corp. (\"Delta\") with a $75 million secured term loan." + fill)["rows"]] +
       [r["side"] for r in analyse("ABC Gold Announces Loan Agreements",
            lead + "announces that John Smith, a director of the Company, has agreed to provide ABC Gold with a $1,000,000 "
                   "unsecured loan." + fill)["rows"]],
       [("lender", "Delta Mining Corp"), "borrower"])
    eq("a forbearance agreement on debentures is not a row; waiving a tender condition is not a covenant waiver",
       (rows("Convertible debentures Forebearance agreement",
             "announces that a Forbearance Agreement dated December 21st, 2020 has been executed by the Company and the "
             "majority holders of its convertible debentures."),
        analyse("ABC Gold Increases Offer for Delta Group Limited Debentures. Waives Minimum Tender Condition",
                lead + "has increased its offer to acquire all of the outstanding debentures of Delta Group Limited." +
                fill)["reason"] != "covenant waiver or forbearance"), ([], True))
    eq("conditional acceptance of a term loan, nothing advanced: signed",
       rows("ABC Gold Announces Closing of Private Placement of Units and Update on Term Loan Facility",
            "has completed its previously announced private placement of units. Update on Term Loan Facility: the "
            "Company has received conditional acceptance of the TSX Venture Exchange for its $775,000 term loan "
            "facility bearing interest at 8% per annum.", ("instrument", "stage")),
       [("loan", "signed")])
    # 1.0.4 (2026-09-30, ACC150 quick fix)
    eq("a right to repay is a term, not a repayment; 'convertible securities' are the release's convertible loans",
       rows("ABC Gold Announces Private Placement of Convertible Securities",
            "announces a non-brokered private placement of convertible securities of up to $250,000. The securities will "
            "be issued pursuant to a convertible loan bearing interest at 15% per annum. The Company has the right to repay "
            "the convertible loan at any time after three months.", ("instrument", "stage")),
       [("convertible_note", "proposed")])
    eq("interest settled in shares is interest_paid, not a repayment or a closing (rule DI)",
       rows("ABC Gold Announces Settlement of Interest Debt",
            "has issued 1,008,000 common shares to settle interest indebtedness of $50,400 owing on its outstanding "
            "convertible debentures.", ("instrument", "stage", "principal")) +
       rows("ABC Gold Announces Debt Settlement",
            "today announces that it intends to pay all of the interest owing on its secured convertible debentures by the "
            "issuance of common shares. Accordingly, the Company intends to issue 5,785,732 shares at a price of $0.12 per "
            "share in settlement of interest owing of $694,288.20.", ("instrument", "stage", "principal")),
       [("convertible_debenture", "interest_paid", 50400.0), ("convertible_debenture", "interest_paid", 694288.2)])
    eq("shares for debt retiring a named note is a repayment; fees and loans lumped together are no row (rule DS)",
       rows("ABC Gold Announces Private Placement and Shares for Debt",
            "announces a non-brokered private placement of units. In addition, the Company proposes to issue 1,524,800 "
            "common shares at a price of $0.10 per share to retire promissory notes with an aggregate value of $152,480.",
            ("instrument", "stage", "principal")) +
       rows("ABC Gold Announces Debt Settlement",
            "has agreed to settle $491,057.90 of debt through the issuance of 9,821,158 common shares. Of this amount, "
            "$205,000 relates to the provision of management fees and loans to the Company's Chief Financial Officer."),
       [("loan", "repaid", 152480.0)])
    eq("a commitment letter is proposed; a receipt under a facility is a drawdown; a first draw closes the facility",
       rows("ABC Gold Secures US$200 Million Senior Credit Facility",
            "has received a commitment letter from Delta Bank for a US$200 million senior secured credit facility. Closing "
            "is subject to definitive documentation.", ("instrument", "stage", "principal")) +
       rows("ABC Gold Receives US$5 Million Under Credit Facility",
            "has received the second advance of US$5 million under its US$15 million credit agreement with Delta Capital.",
            ("instrument", "stage", "principal")) +
       rows("ABC Gold Announces Initial Draw of $70 Million Under Senior Secured Credit Facility",
            "has completed the initial draw of $70 million under its $115 million senior secured credit facility.",
            ("instrument", "stage", "principal")),
       [("credit_facility", "proposed", 200000000.0), ("credit_facility", "drawn", 5000000.0),
        ("credit_facility", "closed", 70000000.0)])
    eq("the company as lender: a loan it made repaid to it, a facility it makes available",
       rows("ABC Gold Announces Receipt of Loan Repayment",
            "announces that Delta Mining Corp. has repaid in full the $1,000,000 secured loan made by the Company."),
       [("loan", "repaid", "lender", 1000000.0)])
    eq("an equity draw-down 'financing facility' is not debt",
       rows("ABC Gold Arranges $8.0M Financing Facility with Delta Partners",
            "has entered into a financing facility for up to $8.0 million with Delta Partners. The Company can draw down "
            "equity private placement tranches of up to $250,000, each tranche composed of units."), [])
    eq("'Convertible Debt Units' the body calls debentures; a loan the lender may convert is a convertible loan",
       rows("ABC Gold Announces Private Placement of Convertible Debt Units",
            "announces a private placement of up to 750 units, each consisting of a $1,000 debenture and 6,896 warrants. "
            "The debentures bear interest at 10% per annum and are convertible at $0.145.", ("instrument", "stage")) +
       rows("ABC Gold Closes Loan Amendment",
            "announces that the amendment to its loan agreement with Delta Fund has become effective, increasing the "
            "unsecured loan from US$14,000,000 to US$16,000,000. Delta has the right to convert all or part of the "
            "principal amount of the loan into common shares at a conversion price of $0.156 per share.",
            ("instrument", "stage", "principal", "conversion_price")),
       [("convertible_debenture", "proposed"), ("convertible_note", "amended", 16000000.0, 0.156)])
    eq("one convertible loan, however often the release calls it 'the loan'",
       rows("ABC Gold Amends Convertible Loan with Delta",
            "has amended its Convertible Loan Agreement with Delta Fund. The outstanding loan and accrued interest will "
            "convert into a royalty upon a fundraising condition.", ("instrument", "stage")),
       [("convertible_note", "amended")])
    eq("interest that was not paid is no row; a repayment and an interest payment in one headline are two rows",
       (rows("Update on interest payment obligations to Delta",
             "announces that the interest payment due on its convertible debenture has not been paid and is in default."),
        rows("ABC Gold Reduces Debt and Issues Shares as Interest Payment",
             "has repaid $1,000,000 of principal on its credit facility with Delta Financing Corp. The Company also issued "
             "3,899,424 shares in payment of annual interest of $1,991,436.", ("instrument", "stage", "principal"))),
       ([], [("credit_facility", "repaid", 1000000.0), ("credit_facility", "interest_paid", 1991436.0)]))
    eq("an amendment's new size and rate; an offering's use of proceeds is not a second row",
       rows("ABC Gold Announces Increase to Loan Facility",
            "announces that the maximum amount of the Delta Loan is increased from US$15 million to US$20 million, and "
            "the interest rate increased to 7.5% per annum.", ("stage", "principal", "rate_pct")) +
       rows("ABC Gold Announces Pricing of US$600 Million Senior Notes Offering to Refinance Project Credit Facility",
            "has priced its offering of US$600 million aggregate principal amount of 9.25% senior secured notes due 2031.",
            ("instrument", "stage", "principal")),
       [("amended", 20000000.0, 7.5), ("notes", "signed", 600000000.0)])
    eq("the lender of the debt being repaid is not this debt's lender; an agency's initials carry its name",
       [(r["instrument"], r["lender"]) for r in analyse(
           "ABC Gold Completes US$350 Million Offering of Convertible Senior Notes",
           lead + "announced today the closing of its offering of US$350 million of 0.25% convertible senior notes due 2031. "
                  "The Company intends to use the net proceeds to repay its senior secured debt facility with ING Capital "
                  "LLC." + fill)["rows"]] +
       [r["lender"] for r in analyse("ABC Gold Closes US$2.26 Billion DOE Loan",
                                     lead + "has closed its US$2.26 billion loan from the DOE Loan Programs Office." + fill)["rows"]],
       [("convertible_note", None), "U.S. Department of Energy (DOE)"])
    eq("a project named 'Revolver' is not a credit facility; sterling amounts; a conversion formula with a floor",
       (rows("ABC Gold Completes Phase I Exploration Program on Revolver Rare Earth Elements Project",
             "has completed the first phase of exploration on the Revolver rare earth elements project."),
        rows("ABC Gold Announces GBP\u00a31 Million Convertible Debenture",
             "announces a Convertible Debenture for GBP\u00a31,000,000 /CAD$1,731,190. The conversion price is floating, at a "
             "discount of 25% to the closing price, with a minimum price of CAD$0.05.",
             ("instrument", "principal", "currency", "conversion_price"))),
       ([], [("convertible_debenture", 1000000.0, "GBP", None)]))
    eq("money lent to support a contemplated takeover is closed; 'concurrent with the closing of' a new facility beside "
       "an existing one is closed; an old facility retired with nothing repaid is terminated",
       rows("ABC Gold Advances Loan",
            "has provided US$250,000 to a private company in order to support a contemplated transaction pursuant to a "
            "convertible promissory note issued by the target. The note matures on December 3, 2027.",
            ("instrument", "stage", "side")) +
       rows("ABC Gold Signs New US$40 Million Credit Facility",
            "has entered into a new revolving credit facility with Delta Bank of Canada. Closure of Existing Credit "
            "Facilities \nConcurrent with the closing of the Delta revolving credit facility, the Company has closed its "
            "existing US$25 million credit facility with Epsilon Bank, which has been retired in conjunction with the "
            "establishment of the Delta revolving credit facility.", ("instrument", "stage", "principal")),
       [("convertible_note", "closed", "lender"), ("credit_facility", "closed", 40000000.0),
        ("credit_facility", "terminated", 25000000.0)])
    eq("a tranche closed beside an intended upsize is the tranche (rule DP); 'convertible senior unsecured notes' are unsecured",
       rows("ABC Gold Closes Second Tranche and Upsizes Convertible Debenture Financing to $5 Million",
            "has closed the second tranche of its private placement of unsecured convertible debentures for gross proceeds "
            "of $300,000. The Company intends to increase the size of the private placement to up to $5,000,000.",
            ("stage", "principal")) +
       rows("ABC Gold Announces Pricing of Offering of Convertible Senior Notes",
            "has priced its offering of convertible senior unsecured notes due 2030 in an aggregate principal amount of "
            "US$400 million. In order to reduce interest expense, the Company will apply the net proceeds to its revolving "
            "credit facility.", ("instrument", "stage", "secured")),
       [("closed", 300000.0), ("convertible_note", "signed", False)])
    # FIX3 (2026-10-01): releases the full text showed were lost
    eq("a lender's commitment or support letter headline names the debt (proposed); a step toward a fully funded "
       "decision is not a funding; an equivalent in brackets does not size it",
       rows("ABC Gold Receives US$500 Million Credit-Approved Debt Commitment Letter for the Alpha Project",
            "is pleased to announce that it has received a credit-approved commitment letter from Delta Bank to underwrite "
            "a total of US$500 million in debt financing for its Alpha Project. The approvals mark an important step "
            "toward a fully funded construction decision.") +
       rows("ABC Gold Announces Receipt of Support Letter for up to US$100 Million from Leading Financial Institution",
            "announced receipt of a support letter from a leading Canadian financial institution stating its interest in "
            "providing long term debt financing of up to US$100 million (approximately C$140 million) of project debt."),
       [("loan", "proposed", "borrower", 500000000.0), ("loan", "proposed", "borrower", 100000000.0)])
    eq("a deferral of the debt owing to insiders is an amendment",
       rows("ABC Gold Enters into Agreement to Defer the Debt Owing to Its Chairman",
            "announces that it has entered into an agreement with its Chairman with respect to all of the indebtedness "
            "owing by the Company to him. Pursuant to the Agreement, $215,242 owing to the Chairman will be deferred "
            "until the share price is at least $2.00.", ("instrument", "stage", "side")),
       [("loan", "amended", "borrower")])
    eq("proceeds 'were utilized to repay debt as follows:' a list: each item repaid, sized by its own amount",
       rows("ABC Gold Repays Debt",
            "confirms that it has received sale proceeds of approximately US$700 million. Proceeds from the sale were "
            "utilized to repay debt as follows: - Senior secured revolving credit facility of $200 million - Unsecured "
            "convertible debentures of $115 million - Senior unsecured notes of US$325 million"),
       [("convertible_debenture", "repaid", "borrower", 115000000.0), ("credit_facility", "repaid", "borrower", 200000000.0),
        ("notes", "repaid", "borrower", 325000000.0)])
    eq("a named secured facility repaid; 'agreed to borrow' under a headline loan is signed and sized",
       rows("ABC GOLD COMPLETES REPAYMENT OF THE SECURED DELTA FACILITY",
            "is pleased to announce that as a result of it repaying in full the secured facility provided by Delta "
            "Trading Limited, the associated security on its Alpha property has been discharged.",
            ("instrument", "stage", "lender")) +
       rows("ABC ANNOUNCES SHAREHOLDER LOAN",
            "announces that subject to TSX Venture Exchange approval, it has agreed to borrow up to $200,000 from three "
            "directors. The Principal will bear interest at 12.5% per annum. ABC may repay all or part of the loan at "
            "any time.", ("instrument", "stage", "principal")),
       [("credit_facility", "repaid", "Delta Trading Limited"), ("loan", "signed", 200000.0)])
    eq("conditions precedent satisfied, a deal 'well advanced': signed, not funded; a prepayment and offtake agreement",
       rows("ABC Gold Announces Satisfaction of Conditions Precedent of Loan Facility",
            "announces that it has satisfied the majority of the conditions precedent required under its previously "
            "announced US$5,000,000 secured loan facility with Delta Fund. The remaining condition is an offtake agreement, "
            "which is well advanced and should be completed by the end of September.") +
       rows("ABC Secures Prepayment and Concentrate Offtake Agreement with Delta Partners",
            "is pleased to report a new prepayment and concentrate purchase agreement has been arranged with Delta "
            "Partners. The agreement provides the Company an opportunity to draw down on a US$80,000 prepayment facility "
            "when needed."),
       [("loan", "signed", "borrower", 5000000.0), ("prepayment", "signed", "borrower", 80000.0)])
    eq("not equity look-alikes: promissory notes beside draw-down equity facilities; a bridge loan facility bearing "
       "interest with bonus warrants on each drawdown; the placement's amount does not size the notes",
       rows("ABC Announces Closing of $925,000 Private Placement & Agreement to Settle Outstanding Promissory Notes",
            "announces that it has completed a private placement of 500,000 shares. In addition, ABC has access to "
            "$33,000,000 in draw down equity facilities. ABC has agreed with the holders of the $5.5 million promissory "
            "notes issued in connection with an acquisition to settle the full amount in exchange for 4,104,474 common "
            "shares.") +
       rows("ABC announces bridge loan",
            "announces that it has entered into a bridge loan facility (the \"Facility\") with Delta, a significant "
            "shareholder. Pursuant to the Facility, ABC may borrow up to C$300,000. The Facility will bear interest at "
            "a rate of 10% per annum. Delta will be issued bonus warrants upon each drawdown on the Facility entitling it "
            "to acquire common shares. An initial drawdown under the Facility of C$82,000 has been completed."),
       [("loan", "repaid", "borrower", 5500000.0), ("loan", "closed", "borrower", 300000.0)])
    eq("'shares for debt' issued to debenture holders for the interest due is interest_paid on the debenture",
       rows("ABC COMPLETES A SHARES FOR DEBT",
            "announces the closing of a share for debt pursuant to which ABC issued 150,000 common shares at a deemed "
            "price of $0.05 per share to debenture holders, representing the $7,500 in interest due as of March 22, 2017, "
            "on its $150,000 convertible debenture. The debenture bears interest at 10% per annum."),
       [("convertible_debenture", "interest_paid", "borrower", 7500.0)])
    # FIX5 (2026-10-04)
    eq("f5 lender: a defined 'Lender', a role before the name, a title, debentures issued to a name, a name that lends",
       [r["lender"] for h, b in (
           ("ABC Gold Secures Bridge Loan",
            "has entered into a loan agreement with Delta Holdings (Bermuda) Corporation Limited (the \u201cLender\u201d) "
            "for a bridge loan of up to $500,000. The Bridge Loan is unsecured."),
           ("ABC Gold Arranges Shareholder Loan",
            "has entered into a Shareholder Loan Agreement for $750,000 from the largest shareholder of the Company, "
            "Delta Grabhold GmbH & Co KG (\"Delta\")."),
           ("ABC GOLD SIGNS LOAN AGREEMENT WITH ITS CHAIRMAN AND CEO",
            "has entered into a loan agreement with Dr. Jane Roe, the Company's Chairman and CEO, providing for a "
            "loan of up to US$3,000,000 (the \"Loan\"). The Loan is unsecured."),
           ("ABC Gold Announces Closing of Financing",
            "has closed a financing of US$4 million raised through the issuance of an unsecured convertible debenture "
            "(the \u201cDebenture\u201d) to Delta Road Capital Investment Ltd. (TSX:DRC)."),
           ("ABC Gold Announces Convertible Loan Agreement",
            "has entered into a convertible loan agreement (the \u201cLoan Agreement\u201d), pursuant to which DRC will "
            "lend ABC US$12,000,000 (the \u201cLoan\u201d).")) for r in analyse(h, lead + b + fill)["rows"]],
       ["Delta Holdings (Bermuda) Corporation Limited", "Delta Grabhold GmbH & Co KG", "Jane Roe",
        "Delta Road Capital Investment Ltd.", "DRC"])
    eq("f5 lender: a full legal name past a weak ending (both named lenders kept) ('X Mining Company, Inc.', 'X Global Resources Fund IV LP')",
       [r["lender"] for h, b in (
           ("ABC Gold Signs Five-Year Loan Agreement",
            "has entered into a 5-year, unsecured loan for US$500,000 with Delta Mining Company, Inc. (\u201cDelta\u201d)."),
           ("ABC Extends Its Loan Facilities",
            "today announced it has extended each of the existing loan facilities aggregating US$12 million from Delta "
            "Global Resources Fund IV LP and The Delta Group Limited (collectively, \"Delta\") to September 30, 2028.")) for
        r in analyse(h, lead + b + fill)["rows"]],
       ["Delta Mining Company, Inc.", "Delta Global Resources Fund IV LP and The Delta Group Limited"])
    eq("f5 maturity: 'being the maturity date', 'the earlier of ... and <date>', 'Notes due April, 2027', a PDF gap in "
       "the year, an extension past 'Inc.', a loan that 'is due on <date>'",
       [r["maturity"] for h, b in (
           ("ABC Closes First Tranche Under Credit Facility",
            "has closed the first tranche of US$6 million under its credit facility with Delta Fund. The bonus warrants "
            "are exercisable until August 16, 2028, being the maturity date of the Loan Agreement."),
           ("ABC Secures Bridge Loan",
            "has entered into a loan agreement for a C$1 million bridge loan. The Bridge Loan is unsecured and will "
            "mature on the earlier of the completion of the Rights Offering and March 4, 2029."),
           ("ABC Announces Partial Redemption of Notes",
            "has issued a notice of partial redemption for $600 million of its outstanding 7.250% Senior Notes due "
            "April, 2027."),
           ("ABC Announces New Loan",
            "has closed a new loan of US$600,000. The New Loan bears interest at 8% per annum. The New Loan matures on "
            "March 5 , 20 28."),
           ("ABC Extends Loan",
            "has extended the repayment date of the US$12 million loan facility with Delta International, Inc. "
            "(\u201cDelta\u201d) from January 18, 2028, to February 16, 2028."),
           ("ABC Announces Loan",
            "has closed a $1,725,000 secured loan with Delta that accrues interest at 8% per annum and is due on "
            "October 27, 2029.")) for r in analyse(h, lead + b + fill)["rows"]],
       ["2028-08-16", "2029-03-04", "2027-04", "2028-03-05", "2028-02-16", "2029-10-27"])
    eq("f5 term: a warrant's exercise period is not the debt's term",
       rows("ABC Closes Convertible Note Units",
            "has closed its private placement of $850,000 of convertible note units. Each Warrant is exercisable into "
            "one Common Share for a period of 24 months from the date of issuance. The Notes have a maturity date "
            "(the \u201cMaturity Date\u201d) of 36 months from the date of issuance.", ("stage", "term_months")),
       [("closed", 36)])
    eq("f5 stage: 'Entry into' a facility is signed; a closing 'subject to' conditions is not a closing; a 'May' date "
       "is not a modal; an offering re-priced before closing stays proposed; 'announces placement' that has closed",
       [r["stage"] for h, b in (
           ("ABC Announces Share Financing and Entry into a New Credit Facility",
            "announces a bought deal financing of common shares. The Company has also agreed terms on a new credit "
            "facility of US$20 million."),
           ("ABC Announces Convertible Loan Agreement",
            "has entered into a convertible loan agreement with Delta Fund LP pursuant to which Delta will lend the "
            "Company US$12,000,000 (the \u201cLoan\u201d). The closing of the Loan is subject to certain customary "
            "closing conditions."),
           ("ABC CLOSES ITS DEBT SETTLEMENT",
            "announces that, further to its News Release of May 18, 2026, it has received approval for the issuance of "
            "270,587 common shares in settlement of $23,000 interest owing on convertible debentures."),
           ("ABC Amends and Extends Its Previously Announced Convertible Debenture Offering",
            "has amended the pricing and extended the closing for its previously announced private placement of "
            "secured convertible debentures."),
           ("ABC Announces Convertible Debenture Unit Private Placement",
            "announces that it has closed the private placement of unsecured convertible debenture units for aggregate "
            "proceeds of $275,000.")) for r in analyse(h, lead + b + fill)["rows"]],
       ["signed", "signed", "interest_paid", "proposed", "closed"])
    eq("f5 side (rule DL): the company advances to, provides to or holds the debt of another",
       [(r["side"], r["borrower"]) for h, b in (
           ("ABC Announces Credit Facility with Delta Ltda.",
            "announces that it has entered into a credit facility agreement, pursuant to which the Company has agreed "
            "to advance to Delta up to an aggregate of $950,000 (the \u201cLoan\u201d). The Loan bears interest at 8%."),
           ("ABC Announces Short-term Investment",
            "is pleased to announce that it has provided a short-term financing of US$7.2 million, as part of a US$17.5 "
            "million senior secured credit facility (the \u201cFacility\u201d) to a private royalty company "
            "(\u201cPrivCo\u201d)."),
           ("ABC Gives an Update on Its Loan Holdings",
            "announces that, upon completion of the assignment, the Company will hold a $1,725,000 secured demand loan "
            "with Delta that accrues interest at 8% per annum.")) for r in analyse(h, lead + b + fill)["rows"]],
       [("lender", "Delta"), ("lender", "private royalty company (PrivCo)"), ("lender", "Delta")])
    print("debt: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test(verbose="-v" in sys.argv) else 0)
