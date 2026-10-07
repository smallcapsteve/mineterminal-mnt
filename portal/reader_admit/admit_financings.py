"""Outside-tag admission rule for the Mining News Terminal financings reader.

admit(headline, text, categories, out) -> (bool, short_reason)

Called only for releases that do NOT carry the "Financings" tag but where the financings reader found a deal.
Admits the release (so it gets the tag and its rows reach the page) only when the deal looks like the release's own
news: the issuer raising money now (announce / upsize / amend / close / terminate), not background such as a recap
of an earlier raise, a warrant or shares-for-debt action, periodic results, or another company's financing.
Standard library only; deterministic; no I/O.

Round 2 (after a blind check of 60 releases the round-1 rule admitted) adds: loans the company makes to someone else,
another company's raise reported by a shareholder, existing-debt housekeeping with no new money, grants and partner
earn-in funding, raises recapped in an update or year review, and a financing listed only as one item of a larger
transaction.  See NOTES_financings.md, "Round 2".
"""
import re

_WS = re.compile(r"\s+")
# A gap character inside one sentence: anything but a sentence end, except the dot inside a number ("$2.5 million").
_G = r"(?:[^.;|]|\.(?=\d))"

# ---------------------------------------------------------------------------------------------------------------
# Rule 1 - periodic results, MD&A, year-in-review and shareholder letters.  These recap raises already closed
# ("following the successful financing", "completed a C$175M placement in the quarter") and restate their terms.
_PERIODIC = re.compile(
    r"\b(?:q[1-4]|first|second|third|fourth|1st|2nd|3rd|4th)[ -]quarter\b" + _G + r"{0,60}\bresults\b"
    r"|\b(?:q[1-4]|h[12]|fy)\s*(?:20\d\d|fiscal)?" + _G + r"{0,30}\b(?:financial |operating )?results\b"
    r"|\b(?:annual|year[- ]end|full[- ]year|interim|quarterly|fiscal)\b" + _G + r"{0,40}\bresults\b"
    r"|\b(?:q[1-4]|full[- ]year|annual|quarterly)\b" + _G + r"{0,60}\b(?:revenue|receipts|production|guidance)\b"
    r"|\bfinancial results\b|\bresults for the (?:three|six|nine|twelve)\b|\byear in review\b|\boperational update\b"
    r"|\bmanagement'?s discussion and analysis\b|\bletter to shareholders\b|\bshareholder letter\b"
    # round 2: year reviews that do not say "year in review" ("a summary of key activities and achievements over the
    # past calendar year")
    r"|\b(?:activities|achievements|accomplishments|milestones|highlights)\b" + _G + r"{0,30}\b(?:over|during|of|for|in)"
    r" the (?:past|last|previous) (?:calendar |fiscal )?year\b")
_PERIODIC_TAGS = {"Financials", "Shareholder Letters & Outlook"}

# ---------------------------------------------------------------------------------------------------------------
# Rule 2 - the headline / first sentence is a capital action the guide says is not a raise.  The reader turns the
# placement that originally created the warrants, or the debt being settled or repaid, into a row.
_W = r"(?<!special )\bwarrants?\b"          # special warrants ARE a raise (special-warrant offerings)
_NON_RAISE = re.compile(
    # warrant term extensions, repricing, amendments, exercises, exercise-incentive programs, listing of warrants
    _W + _G + r"{0,60}\b(?:extend|extends|extended|extension|expiry|expiration|amend|amends|amended|amendments?"
    r"|reprice|reprices|repriced|repricing|exercised|listing|incentive|acceleration)\b"
    r"|\b(?:extend|extends|extension of|amend|amends|amendments? to|reprices?|repricing of|exercise of|listing of)\b"
    + _G + r"{0,60}" + _W +
    # proceeds from option / warrant exercises
    r"|\bfrom (?:the )?(?:exercise of )?(?:warrants?|options?|stock options)\b"
    # shares or units issued to settle debt or interest; debt-for-equity conversions
    r"|\bshares?[- ]for[- ]debt\b|\bdebt[- ]for[- ](?:equity|shares)\b|\bdebt settlement\b|\bdebt conversion\b"
    r"|\bsettle(?:ment of|s|d)?\b" + _G + r"{0,60}\b(?:debt|indebtedness|loan|accrued interest|interest due|interest payment)"
    r"|\bshares\b" + _G + r"{0,40}\b(?:in satisfaction of|as (?:an )?interest payment|in lieu of (?:cash )?interest)"
    # conversion, redemption or buy-back of the issuer's existing debentures / notes
    r"|\b(?:conversion of|redemption of|redeems?|repurchase|buy[- ]?back|tender offer|dutch auction)\b" + _G + r"{0,40}"
    r"\b(?:debentures?|notes|bonds)\b"
    # finder's fees paid on an earlier placement
    r"|\bannounces? finders?'?\s*fees?\b|\bfinders?'?\s*fees? (?:were |was |have been |has been )?paid\b"
    # repaying an existing loan
    r"|\b(?:repa(?:ys?|id|yment)|pays? back|paid back)\b" + _G + r"{0,60}\b(?:loans?|debt|facility|debentures?|notes?)\b"
    r"|\b(?:debt|loan) repayment\b"
    # compensation / option grants
    r"|\b(?:restructures|reduces) compensation\b|\bgrant of (?:stock )?options\b")

# A new-deal word in the headline field itself lets a mixed release through rule 2
# (e.g. "Warrants Exercised, Debentures Converted and $0.25 Units Offering Proceeding").
_HEADLINE_DEAL = re.compile(r"\b(?:private placement|placement|offering|financing)\b")

# ---------------------------------------------------------------------------------------------------------------
# Rule 3 - the ticker's company is the investor, not the one raising: early-warning reports, "invests ... into",
# subscribing to another company's placement, or "the Company announces that <other listed company> has entered
# into" a financing (a JV partner's or counterparty's deal).  Round 2 adds the company as LENDER to another company
# (the guide lists "the issuer LENDING to another company" as not a financing) and, in _OTHER_CO below, another
# company's own raise named with any corporate name, not only a listed one.
# "to <someone>" that is not the company itself and not a purpose ("to fund", "to repay").
_NOT_US =(r"(?!the company|the corporation|it\b|us\b|fund\b|finance\b|be\b|repay\b|purchase\b|acquire\b|support\b"
           r"|cover\b|settle\b)")
_INVESTOR = re.compile(
    r"\bacquiror\b|\bearly warning\b"
    r"|\bacquisition of (?:[\d,.]+ )?(?:common )?(?:shares|units|securities)\b" + _G + r"{0,40}\bof\b"
    r"|\binvests?\b" + _G + r"{0,60}\binto\b|\bsubscribing for\b"
    # a royalty / streaming company buying a stream or royalty (it is the funder, not the one raising)
    r"|\b(?:acquire|acquires|acquisition of|purchase|purchases)\b" + _G + r"{0,30}\b(?:stream|royalty)\b"
    r"|\binvestment portfolio\b"
    r"|\bannounces? that (?!the company|the corporation|it\b|its\b)[a-z][\w .&,-]{2,60}? (?:\([^)]{0,40}\) ?)?"
    r"\((?:tsx|tsxv|tsx-v|tsx -v|cse|nyse|nasdaq|asx|otc)[^)]*\)[^.]{0,40}\bhas\b"
    # round 2: the company is the LENDER to another company ("is pleased to announce it has entered into a definitive
    # agreement to provide a loan ... to <other company>", "provides update on loan to <other company>").  A loan TO the
    # company is kept (negative look-ahead), and so is a release where another party lends to the company.
    r"|\b(?:it|the company|the corporation|we)(?: has| have| will| is| are| has agreed to| agreed to| to)?" + _G + r"{0,60}?"
    r"\b(?:provide|provides|providing|make|makes|advance|advances|advanced|extend|extends|lend|lends|lent)\b(?: an?)?"
    + _G + r"{0,30}?\b(?:loans?|promissory notes?|bridge financing)\b" + _G + r"{0,60}?\bto " + _NOT_US + r"[a-z]"
    r"|\b(?:its|the company's|the corporation's|our) (?:\w+ ){0,2}loans? (?:\([^)]{0,40}\) )?to " + _NOT_US + r"[a-z]"
    r"|\bupdate on (?:the |its )?loan to " + _NOT_US + r"[a-z]")

# Round 2: another company's own raise, reported by a company that holds its shares or is its partner
# ("is pleased to announce that <Other Co.> ("Other") has successfully completed an initial public offering").  Any
# company name (a corporate word before a defined-term parenthetical) marks the other company; the sentence must not
# bring in "the Company" or a subsidiary (so a lender that "has agreed to provide the Company" a loan, or "<X LLC>, a
# wholly-owned subsidiary of the Company, has closed" a stream, is not caught).
_OTHER_CO = re.compile(
    r"\bannounces?,? that (?![^.]{0,160}\b(?:subsidiary|affiliate|the company|the corporation)\b)"
    r"(?!the company|the corporation|it\b|its\b|we\b)"
    r"[a-z][\w .&,'-]{0,50}?\b(?:inc|corp|corporation|ltd|limited|llc|lp|plc|ag|sa|company|resources|mining|metals"
    r"|minerals|uranium|gold|silver|copper|group|holdings|capital|fund)\b\.? \([^)]{1,60}\)"
    r"[^.]{0,60}?\b(?:has|have)\b(?![^.]{0,200}\b(?:the company|the corporation)\b)")

# ---------------------------------------------------------------------------------------------------------------
# Round 2, rule 5 - housekeeping on debt the company already has, with no new money: a project loan's "financial
# completion" / completion test, a maturity or term extension, a covenant waiver.  Like a warrant extension (rule 2),
# the reader turns the existing loan's size into a row.  Skipped when the lead also brings new money (an increase, a
# new tranche or advance), which is a real amendment or upsize of the facility.
_DEBT_HOUSEKEEPING = re.compile(
    r"\bfinancial completion\b|\bcompletion test\b"
    r"|\b(?:extend|extends|extended|extending|extension of|extension to)\b (?:the )?(?:maturity|maturities|term)\b"
    r"|\bmaturity (?:date )?(?:extension|has been extended|was extended)\b"
    r"|\bcovenant (?:waiver|relief|holiday)\b|\bwaiver of (?:the |certain )?(?:financial )?covenants?\b")
_NEW_MONEY = re.compile(
    r"\b(?:additional|addition to|new|further|incremental|increas\w*|upsiz\w*)\b" + _G + r"{0,60}\b(?:advances?|loans?"
    r"|funds|funding|tranche|facility|financing|principal|amount|capital|commitments?|size|limit)\b"
    # a second, money-bearing deal alongside the extension ("Extension of <X> Loan and US$5,500,000 Financing")
    r"|\band (?:a |an )?(?:c\$|us\$|a\$|\$)[\d,.]+(?: million)? (?:financing|loan|placement|offering)\b")

# Round 2, rule 6 - money that is not a capital raise by the company: government grants and awards (program
# funding, contribution / "other transaction" agreements) and a partner's earn-in or joint-venture funding of
# project work.  The reader reads "secures US$31M funding" as a placement.  Applied only when the lead has no strong
# deal term (a grant alongside a real placement keeps the placement).
_NOT_CAPITAL = re.compile(
    r"\bgrant (?:funding|agreement|program|award)\b|\b(?:government|federal|provincial|state) (?:grant|funding|award)\b"
    r"|\bgrants? (?:of|totall?ing|worth) (?:up to )?(?:c\$|us\$|\$|€)|\bother transaction agreement\b"
    r"|\bcontribution agreement\b|\bawarded\b" + _G + r"{0,40}\b(?:grant|funding)\b"
    r"|\bearn[- ]in\b|\bearn (?:an? |up to (?:an? )?)?(?:\d+% )?(?:interest|stake)\b|\bsole[- ]fund\w*\b"
    r"|\b(?:joint venture|jv|option) partner\b" + _G + r"{0,60}\bfund\w*\b")

# Round 2, rule 7 - a raise recapped in an update: in a sentence found only by the weak words, a simple past
# completion with a date ("the Company completed a C$3.5 million financing in late July", "kicked off the year with
# the completion of a financing of $5.3M on January 4th") points back to an earlier release.  "Has closed" /
# "announces the closing" is present news and is not caught.
_MONTH = (r"(?:january|february|march|april|may|june|july|august|september|october|november|december"
          r"|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b")
_RECAP = re.compile(
    r"(?:(?<!has )(?<!have )(?<!had )(?<!was )(?<!been )\b(?:completed|closed|raised)\b|\bcompletion of\b)"
    r"(?=" + _G + r"{0,120}\b(?:(?:in|on|during|since|by) (?:late |early |mid[- ]|the end of )?" + _MONTH +
    r"|(?:in|during) (?:q[1-4]|the (?:first|second|third|fourth) quarter|20\d\d)\b"
    r"|\b(?:earlier|last) (?:this )?(?:year|month|quarter)\b|\bthis (?:past )?(?:year|quarter)\b))")

# ---------------------------------------------------------------------------------------------------------------
# Rule 4 - clauses that point back to a raise that is over, or not yet real, are removed before looking for a live
# deal ("following the successful $3.5M capital raising", "contingent upon the closing of its financing announced
# on ...", "complementary to its recent private placement", "which closed on May 16", "pending financing").
_PAST_REF = re.compile(
    r"\bfollowing (?:the |its |a |their )?(?:successful |recent |recently completed |oversubscribed )?"
    + _G + r"{0,50}?\b(?:financing|raise|raising|placement|offering)s?\b"
    r"|\b(?:its |the |a )?recent(?:ly (?:completed|closed))?\b" + _G + r"{0,60}?\b(?:placement|financing|offering|raise)\b"
    r"|\bpreviously (?:completed|closed)\b" + _G + r"{0,60}?\b(?:placement|financing|offering)\b"
    r"|\bcontingent (?:up)?on (?:the )?(?:closing|completion) of\b" + _G + r"{0,80}"
    r"|\bwhich closed on\b|\bpending financing\b|\bfinancing options\b")

# Live raise language, in two strengths.
# Strong: words that only occur for a securities / debt raise - placements, flow-through, LIFE, prospectus / bought /
# marketed offerings, special warrants, ATM programs, gross proceeds, tranches, unit pricing, loan agreements,
# credit / term / standby / equipment / prepay facilities, convertible debentures, metal streams sold for cash.
_DEAL = re.compile(
    r"\bprivate placements?\b|\bflow[- ]?through\b|\bbought deal\b|\blisted issuer financing exemption\b"
    r"|\b(?:public|prospectus|marketed|unit|units|equity|brokered|underwritten|best efforts|share|shares|life"
    r"|bond|notes?|debenture) offering\b|\boffering of\b|\bspecial warrants?\b|\bat[- ]the[- ]market\b"
    r"|\bequity distribution agreement\b|\bgross proceeds\b|\b(?:first|second|third|final|initial) tranche\b"
    r"|\bper unit\b|\bunits? at (?:a price of )?(?:c\$|us\$|\$)|\bloan agreements?\b|\bline of credit\b"
    r"|\b(?:credit|loan|debt|term|revolving|standby|equipment|financing|bridge|lease|prepa\w+|drawdown|offtake"
    r"|secured|unsecured|working capital)\s+(?:loan\s+)?facilit(?:y|ies)\b|\bfacilit(?:y|ies)\s+agreements?\b"
    r"|\bconvertible (?:debentures?|notes?)\b|\b(?:gold|silver|metals?|copper|precious metals) stream\b"
    r"|\bstream(?:ing)? (?:agreement|financing|transaction)\b"
    r"|\b(?:financing|placement|offering) of (?:up to )?(?:[\d,.]+ )?(?:units|common shares|flow-through shares)\b"
    r"|\bunits? (?:is |are |will be )?priced at\b")
# Weak: words also used for other things (a "raise" in a mine, a reclamation "bond", "financing" plans, a lender's
# "loan" to someone else).  They count only in a sentence that also states a sum of money and a deal action.
_WEAK = re.compile(r"\bfinancings?\b|\braise[sd]?\b|\braising\b|\bloans?\b|\bbonds?\b|\bnotes\b"
                   r"|\bdebentures?\b|\bprepa(?:id|yment)\b|\bfunding\b")
_MONEY = re.compile(r"(?:[$£€]|\b(?:c|us|a|cdn|cad|usd|aud|rmb|gbp|eur)\s?\$?)\s?\d"
                    r"|\b\d[\d,.]*\s?(?:million|billion|mm|m)\b")
_ACTION = re.compile(
    r"\b(?:announc\w*|arrang\w*|clos(?:e|es|ed|ing)|complet\w*|enter(?:s|ed)? into|secur(?:e|es|ed)|obtain\w*|sign\w*"
    r"|agree\w*|borrow\w*|advanc\w*|draw\w*|commit\w*|receiv\w*|intend\w*|propos\w*|launch\w*|plac(?:e|es|ed|ing)"
    r"|rais(?:e|es|ed|ing)|finaliz\w*|execut\w*|increas\w*|amend\w*|revis\w*|extend\w*|terminat\w*|new|additional"
    r"|up to|provid\w*)\b")
_SENT = re.compile(r"(?<!\d)\.(?!\d)|;|\|")


def _live_raise(window, lead, top):
    """-> "strong", "weak" or None.  Strong deal words in the search window; or a weak one in a lead sentence with a
    sum of money and an action, that is not a dated past completion (rule 7) and not in a release about grants or
    partner earn-in funding (rule 6)."""
    if _DEAL.search(window):
        return "strong"
    if _NOT_CAPITAL.search(top):
        return None
    for s in _SENT.split(lead):
        if _WEAK.search(s) and _MONEY.search(s) and _ACTION.search(s) and not _RECAP.search(s):
            return "weak"
    return None


# Rule 0 exception - a row with no amount and no price is admitted only when the headline itself announces a deal
# event ("Arranges Additional Short-Term Financing", "Announces RMB 235 Million Secured Loan").
_HEADLINE_EVENT = re.compile(
    # round 2: no comma between the verb and the deal word ("Announces RTO, Change of Business and Financing" names a
    # financing only as one item of a larger transaction; its terms are not set)
    r"\b(?:announces?|arranges?|closes|completes|secures?|enters? into|obtains?|extends?)\b"
    r"(?:[^.;|,]|(?<=\d)[.,](?=\d)){0,60}?"
    r"\b(?:loan|financing|private placement|placement|offering|tranche|debentures?|credit facility|facility"
    r"|facilities)\b")


def _norm(s):
    return _WS.sub(" ", (s or "").replace("’", "'").replace("‘", "'")).lower()


def _has_number(out):
    """True when the reader's row carries at least one amount or an issue price."""
    rows = out if isinstance(out, list) else [out]
    for r in rows:
        if isinstance(r, dict) and (r.get("amounts") or r.get("unit_price")):
            return True
    return False


def admit(headline, text, categories, out):
    head = _norm(headline)
    body = _norm((text or "")[:9000])    # at most the first 8,000 characters are ever searched
    top = head + " | " + body[:700]      # real headline and first sentence (the headline field is often letterhead)
    lead = head + " | " + body[:1500]    # headline plus the lead paragraphs

    # Rule 0: the reader found a deal but no amount and no price.  Outside the tag this is nearly always a passing
    # mention ("will seek financing", a warrant clause, a VP 'responsible for financing'); the guide wants at least an
    # amount or a price for a raise in a release whose main news is something else.  Kept only when the headline
    # itself announces a deal.
    if not _has_number(out) and not _HEADLINE_EVENT.search(head):
        return False, "no amount or price in reader row"

    # Rule 1: results / MD&A / year-in-review / shareholder letters restate past raises.
    if _PERIODIC.search(top) or (set(categories or []) & _PERIODIC_TAGS):
        return False, "periodic results or review"

    # Rule 2: warrant actions, shares for debt, finder's fees, loan repayments, compensation.
    if _NON_RAISE.search(top) and not _HEADLINE_DEAL.search(head):
        return False, "non-raise capital action"

    # Rule 3: the company is the investor / acquiror, or reports another company's deal.
    # Rule 3 (round 2 additions): the company lends to someone else (in _INVESTOR), or reports another company's own
    # raise ("announces that <Other Co.> ("Other") has completed an IPO").
    if _INVESTOR.search(top) or _OTHER_CO.search(top):
        return False, "issuer is the investor"

    # Rule 5 (round 2): housekeeping on existing debt with no new money (completion test, maturity extension, waiver).
    if _DEBT_HOUSEKEEPING.search(top) and not _NEW_MONEY.search(top):
        return False, "existing debt, no new money"

    # Rule 4: after dropping clauses that point back to an earlier raise, the lead must still describe a raise.
    # When the headline field itself names a financing ("... Start of Drilling and New Financing"), the deal may sit
    # below a long first section, so the first 8,000 characters are searched for it.  Rules 6 and 7 (round 2) apply
    # inside: a lead found only by weak words must not be grant / earn-in money or a dated recap of a past raise.
    window = head + " | " + body[:8000] if _HEADLINE_DEAL.search(head) else lead
    if not _live_raise(_PAST_REF.sub(" ", window), _PAST_REF.sub(" ", lead), top):
        return False, "no live raise in lead"

    return True, "raise in lead"
