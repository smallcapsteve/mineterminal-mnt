"""Property Options & Staking reader, facts-store version (OPT_V1, 2026-09-23).

The source of the Property Options & Staking page once it passes the accuracy gate. Written against the 50-item set
Justin confirmed on 2026-09-23 (46 items with rows, 56 rows; claude/MNT_OPT_SET_LABELS_CONFIRMED_2026-09-23.json) and
the label guide claude/MNT_OPT_LABEL_GUIDE_2026-09-23.md.

Justin's rules (2026-09-23):

  1. ONE ROW PER LAND DEAL the issuer reports: company, counterparty, property, deal type, stage, interest, and the
     terms (cash, shares, work, NSR, term, area) when stated. Types: option in, option out (earn-ins included),
     staking, claim purchase, property purchase, property sale.
  2. STAGES CHAIN across releases: proposed (LOI / MOU) -> signed -> payment -> completed (exercised, earned,
     closed), plus amended and terminated.
  3. IN SCOPE: options and earn-ins; staking and claim purchases; outright property purchases.
     OUT: stock / incentive options, company-level M&A, non-mining licences, other companies' deals, deals restated
     in passing (About sections, history).
  4. One agreement over several properties is one row; separate agreements are one row each (rule OS).

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per row (ordinal 0..n-1)
to_prediction(records) -> dict|None    what the accuracy judge compares

Self-tests: python3 -m portal.extractors.options

1.0.5 (2026-09-26): JURISDICTION is filled (the Permits reader's rule, PM._jurisdiction: "located in ..." first, else
the place named most often outside datelines and addresses; a deal among several reads only its own sentences). A NAME
CUT SHORT AT A LANDFORM gets its first word back: a qualifier stripped as a lead-in ("Mineral", "Table", "Key", "High",
"Rare Earth", a metal, a possessive) returns when a landform (Lake, Ridge, Mountain, Bay...) follows it, unless it ends
a company's name ("Toogood Gold Table..."); a capitalised word just outside the capture returns too ("Case Lake West",
"Monster Lake East"). A landform that starts a real name keeps it alone ("Lake Cargelligo", "River Valley").

1.0.6 (2026-09-26): no code change here. The Permits reader's jurisdiction rule this reader borrows became JUR_V2
(permits 1.0.3): securities legends, tickers, addresses, company and other names, and a project named after a country
are not places; the company's "About ..." paragraph is not read; each mention votes for its country, and the answer is
its most-named province or state. Ruby Creek (Stuhini) is British Columbia again, not USA; Baril Lake is Ontario.

1.0.7 (2026-09-30, blind samples in-tag and outside the tag): error kinds fixed.
  THE PROPERTY IS THE DEAL'S. A headline with several pieces of news is cut into clauses; a property named only in the
  clause of other news (a resource estimate, an update, a program, a financing) is not the deal's, in the headline or in
  the body, unless the deal adds ground to that project. The copy of the headline that opens most bodies is not read for
  names. A headline name must be a name: not one the body writes only in lower case ("Third Hard-Rock", "Identified
  High Sulphidation-Porphyry Prospects" are descriptions), not a count of properties ("Two New Toodoggone Projects":
  the body names them). Descriptive, corporate-finance and region words, deposit types, verbs and countries do not make
  a name ("Debt Settlement Property", "Timmins-Area Properties", "Carlin Trend Claims", "Zimbabwe Gold-Base Metal",
  "Optimizes Burnthut"); a company ("... Mineral Properties Canada Inc.") is not a property, nor is a neighbour's
  project ("Adjoining X Corp.'s Goliath Complex") when the release's main project stands in. A headline name with no
  Property word is read from "X Option Agreement" and "Interest in X". "Rayfield -Gjoll" (a PDF break) is one word.
  NOT GROUND, NO ROW. Deals in royalties, streams, offtakes, water rights and permits, power, data sets, drills and
  equipment, concentrate and production sales; an interest, stake or shares in a company, share purchase plans; "option"
  meaning a choice or a right that is not an option on ground (payment terms, mill or financing options, "exploring
  options", an option to buy production, a right of first refusal); agreements for services, advice or collaboration,
  an alliance, a mandate or intention to sell; a mapped (geological) footprint; exploitation or mining licence
  applications on ground already held. Company-level M&A: a merger ("to Merge With X Corp."), or a headline that buys a
  company the lead says is bought by amalgamation, arrangement or all its shares (its purchase sentences are not rows),
  or a lead that buys an interest in a company.
  BACKGROUND. A headline that names an option only as a partner's work ("Option Partner", "X's optioned Y property",
  "under option to", "following the announced sale"); a deal restated with a pointer to its earlier release; "since
  acquiring X in 2014", "in which the Company owns", "holds the option to".
  TYPE. "Acquires X" whose terms are an option ("can earn", "the Optionors", "the right to acquire ... over two years")
  is option_in; a partner that continues its earn-in is option_out at payment.
  ONE ROW PER DEAL. "Acquires & Stakes ..." gives a purchase row and a staking row; "has staked two prospects" named
  one by one in the body gives one row each.
  STAGE. A termination written as a condition ("If ... decides not to proceed", "will supersede and terminate") is not
  one; "has acquired the X claims" with nothing still open, "closed its ... agreement ... to acquire", "Completes Sale",
  "Sale Closed", "Acquires 100% Ownership", "Fulfills Option" are completed, and licences granted or registered complete
  a staking; "Extension of LOI", "Amendments", "renegotiates", an addendum are amended; "Issues Final Shares to Acquire"
  is a payment; a letter of intent mentioned as earlier paper ("previously paid on execution of the letter of intent")
  does not make the deal proposed; "on closing of the Acquisition" is a term, not completion.
  COUNTERPARTY. A parent named before "and its subsidiary, X" is the other side.

1.0.8 (2026-10-01, outside-tag samples conf3 / conf4): no row unless the release itself announces a land deal.
  COMPANY-LEVEL M&A. A headline that frames a merger, a business combination, an amalgamation, an arrangement, a
  takeover or "creating a ... company / producer" gives no row. Nor does a release whose lead deal acts on a company
  ("purchase its 100% ownership stake in X S/A, which owns the Y mine", "has acquired 100% of X Ltda.", "the purchase of
  X Metals Ltd.", "sale of its 25% interest in X Operations Inc.", "to divest its subsidiaries") when the release frames
  it as a company deal: the headline names no land object or option, the business is operating (a producing mine,
  "accretive", EBITDA), or the target's shareholders exchange their shares. A subsidiary sold or bought under a headline
  that names the property stays a land deal (the label guide's rule OA).
  NOT GROUND, NO ROW (more kinds). Stock options issued, awarded or cancelled; an over-allotment, underwriters' or
  agents' option; "many options on how to proceed"; a payment or option for a royalty, a royalty buy-back; mill
  assets, a processing plant, real estate; shares of another company bought or sold ("Sale of Firetail Shares"); an
  LOI, term sheet or agreement for equity, a loan, a facility or an investment; metal pre-paid or bought forward. When
  the headline's only deal is one of these, body sentences of the same kind restate it and are not read ("Closes Sale
  of Real Estate Asset": "closed the sale of its San Pedrito Property, a non-core asset"), unless the headline also
  names land other than where a royalty lies.
  BACKGROUND. "Post-acquisition" in a headline; the company's own licence application named as the place of other news.
  THE DEAL'S PROPERTY. "Sells its 50% share of X to Y" is a sale of X (the name ends before the buyer); an option to
  purchase an exploration permit is a deal on ground and the permit's quoted name is its property. A headline that
  runs on into the release ends at the dateline before the issuer's ticker.
  TYPE. Concessions and patents (patented claims) bought are claim purchases; "Sells K2 to Azimut", "LOI to Sell X"
  are sales.
  STAGE. A "binding agreement" is signed (a letter of intent stays proposed, binding or not); an extended closing or
  period to complete is amended; "has sold its X property" with nothing pending in that sentence is completed.

1.0.9 (2026-10-02, blind re-check ACC150b of the tagged page): wrong rows on the page.
  THE DEAL'S OWN GROUND. A name written after a relation is a neighbour's or the host project the new ground lies by:
  "contiguous to", "adjacent to and along strike of its", "on (the) extension of", "on trend with its", "between",
  "2 km northeast from X's previously staked"; in an upper-case headline too (the words before the name are read where
  the name itself starts). The ground's own name wins: "a property known as the X Property", "a former Y Exploration
  project referred to as the X Property", "94 mineral claims called the X Nord", "the X gold-silver property" (metals in
  lower case before the suffix), "Acquires 3 Additional Claims at X". A country is no name ("C\u00f4te d'Ivoire Projects"),
  nor is the paper ("Share Purchase Agreement"). The headline names the body's top project only with its first two
  words ("San Javier" does not name "San Antonio") and not after a relation.
  NOT THE RELEASE'S DEAL. A claim block named as the place of drilling ("Commences Drilling ... at B3 Claim Block"); a
  deal between two other companies (the headline's and the lead's subject are not the issuer); another company's deal
  written in the passive ("the X claims acquired by Y Development Corp."); "the X Project, now optioned to Y"; another
  company's staking ("contiguous to QIMC's recent claims staking") is not the issuer's; history in a release whose
  dateline no dash closes ("MONTREAL, July 05, 2022 (GLOBE
  NEWSWIRE)": the first date gives the year), unless the sentence agrees a change now.
  OPTION DIRECTION. Out: "the Company has granted the Optionor the option to acquire ... in its X project", "ABC will
  grant Kappa the sole exclusive option", "Y will be granted the right to acquire", "option to acquire the Company's
  55%-owned X", notice from the partner of its intention to relinquish or terminate its option, "to option the X Project
  to a private company", the partner "has fulfilled the ... requirements". In: "Options Additional Property Adjacent to
  X" ("to" after a relation names no optionee); "Receives Approval and Makes Initial Payments Under ... Option"; a
  buy-back option granted to the vendor.
  STAGE. "ABC acquired an initial 51% / an additional 24% interest" is completed; "terminate the purchase agreement and
  replace it with an option agreement" is not a termination; "has now acquired" while the acquisition "remains subject to
  customary conditions of closing" is signed; options relinquished in passing ("has relinquished its options to acquire
  the X and Y properties") are one terminated row each beside the release's main deal. A partner's "option to earn up
  to a 70% interest" in a district is a deal on ground.

1.0.10 (2026-10-04, FIX5 on blind sample ACC150c): counterparty, cash, shares.
  CASH: a cash total the release states in so many words ("cash payments over three years totalling US$1,350,000", "a
  series of cash payments tota ling US$1,200,000", "a total cash consideration of $250,001") wins over the first payment
  the older patterns pick; not a part ("additional", "further", "remaining", "balance") or a buy-back or royalty price.
  The scale is read with the figure ("$1.05 million", "C$1.05M"). (A first version summed payment schedules; on the
  held-back half its sums were too often wrong, and it was withdrawn.)
  SHARES: a stated total ("an aggregate of", "a maximum of", "consisting of ... 600,000 common shares", "1.3M
  shares over the initial 4 year earn in period"), the whole followed by its tranches, or the tranches summed. Never
  shares of a placement, units, warrants or options, a finder's or milestone shares, shares held, released from escrow
  or issued only if a condition is met. A number broken by a PDF line ("1,00 0,000") is one number.
  COUNTERPARTY. A name led by a number ("1234 Resources") or by a commodity word ("Nickel Beta Exploration", "Mining
  Gamma Pty Ltd") or written "X, LLC" is a name; a project named before "with / from X" makes no list ("the Alpha
  Copper Project, with SCM Beta Minerals Group"). With no party in the deal sentences: the one that keeps the
  royalty ("Beta Or Corp. retains a 2% NSR", "with Gamma Silver retaining a 3% NSR") or holds the optioned claims
  ("an option to acquire ... claims held by X"); not the seller of ground next door "recently optioned from X".
  TYPE. "Newly-staked claims", licences the government granted: staking. The other side earning ("for Beta to
  incur ... to exercise the first option to earn", "the earn-in to 90% by X"), never the company: option out.
  ONE ROW PER DEAL. New ground the company stakes itself beside the option or purchase it reports ("The Company also
  staked 87 claim units ... an additional 1880 hectares") is a staking row; claims bought outright for a price beside
  ground the company staked ("ABC has purchased the Alpha Claims for $300,000 cash") are a purchase row.
"""
from __future__ import annotations

import re

from portal import facts as F
from portal import fingerprint as FP
from portal import project_names as PN
from portal.extractors import permits as PM    # 1.0.5: jurisdiction, the Permits reader's rule
from portal.extractors import technical as T

NAME = "options"
VERSION = "1.0.10"  # 2026-10-01: no row for releases whose news is not a land deal (company-level M&A, non-land deals, background); stage and type cues; 2026-10-02: the deal's own ground (not a neighbour's or host project named after a relation, a place or a company), other companies' deals and background, option direction and stage cues; 2026-10-04 FIX5: cash only from an explicitly stated cash total; shares as the stated total or the schedule summed (never a tranche, milestone, financing or warrant), counterparty names as written and by role (keeps the royalty, holds the optioned claims), staking and option-out cues, own staking beside an option or a purchase beside staking as its own row; rev b: own staking only when the company is the subject and the ground is measured
KIND = "land_deal"
TAG = "Property Options & Staking"
TEXT_CAP = 40000

TXT_FIELDS = ("deal_type", "stage", "property", "counterparty", "currency", "date", "jurisdiction", "metal")
NUM_FIELDS = ("interest_pct", "cash", "shares", "work", "nsr", "term", "area")
DEAL_TYPES = ("option_in", "option_out", "staking", "claim_purchase", "property_purchase", "property_sale")
STAGES = ("proposed", "signed", "payment", "completed", "amended", "terminated")
STAGE_RANK = {"proposed": 1, "signed": 2, "payment": 3, "amended": 3, "completed": 4, "terminated": 5}

# ------------------------------------------------------------------ text
_FLS = re.compile(r"(?i)(?:^|\s)(?:cautionary\s+(?:note|statement|language)s?\b|forward[\s\-]+looking\s+(?:statements?|information)"
                  r"\s*(?:$|[A-Z:])|notice\s+regarding\s+forward|neither\s+(?:the\s+)?(?:tsx|canadian\s+securities|cse)\b|"
                  r"the\s+cse\s+(?:has\s+not|and\s+information)|no\s+stock\s+exchange|to\s+view\s+the\s+source)")
_ABOUT_CO = re.compile(r"(?:^|\s)About\s+(?:the\s+Company\b|Us\b|(?!the\s+(?:\w+\s+){0,4}?(?:Property|Project|Claims|Option|Agreement|"
                       r"Transaction|Acquisition|Deposit)\b)[A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5}\s*(?:[:.]|\(|\s(?=[A-Z][a-z]+\s)))")


_SQ_PAIR = re.compile(r"(?<![\w'])'([A-Z0-9][^'\n]{0,38}?)'(?![\w])")


def _unq(s):
    """OPT_V1f: "the 'Goose' Gold Project" -> "the  Goose  Gold Project" (same length, so positions hold). An apostrophe
    that follows a word ("Kinross' Great Bear") never opens a pair."""
    return _SQ_PAIR.sub(lambda m: " " + m.group(1) + " ", s)


def _prepare(headline, body):
    b = _unq(T._norm((body or "")[:TEXT_CAP]))
    b = re.sub(r"https?://\S+", " ", b)
    b = T._flat(b)
    b = re.sub(r"(?<=[A-Za-z]) -(?=[A-Z][a-z])", "-", b)     # 1.0.7: "Rayfield -Gjoll" (a PDF break) is "Rayfield-Gjoll"
    fls = _FLS.search(b, int(len(b) * 0.35))
    if fls:
        b = b[:fls.start()]
    about = None
    for m in _ABOUT_CO.finditer(b, 600):
        about = m.start()
        break
    h = T._flat(_unq(T._norm(headline or "")))
    h = re.sub(r"\s+(?:TSX\s+Venture\s+Exchange|TSX-?V|CSE|Frankfurt)\s*\(.*$", "", h)
    # 1.0.8: a headline that runs on into the release ("... in Mexico Vancouver, British Columbia - Starcore ... (TSX:SAM)
    # ... announces that it has closed ..."): the headline ends at the dateline before the issuer's ticker
    tk = re.search(r"\s\((?:TSX|TSXV|TSX-V|CSE|NYSE|NASDAQ|ASX|OTC\w*|NEO)\b", h)
    if tk and tk.start() > 40:
        h = h[:tk.start()]
        dm = re.search(r"\s(?:[A-Z][\w.\-]*\s+){0,2}[A-Z][\w.\-]*,\s+(?:[A-Z][\w.\-]*\s*){1,3}(?:,\s*[\w ,.]{3,30}?\d{4}\s*)?"
                       r"(?:[\-\u2013\u2014]{1,2}|\()\s", h[30:])
        if dm:
            h = h[:30 + dm.start()]
    return h, b, about


_LEGAL_END = re.compile(r"\b(?:Corp|Inc|Ltd|Co|Pty|S\.A|L\.L\.C)\.$")


def _sentences(b):
    out = []
    parts = []
    for s in T._sentences(b):
        # "Delta Metals Corp. ("Delta") whereby ..." is one sentence: T._sentences splits before a "(" after any "."
        if parts and s[:1] == "(" and _LEGAL_END.search(parts[-1]):
            parts[-1] += " " + s
        else:
            parts.append(s)
    for s in parts:
        # split long bullet-less sentences at ' \u2022 ' and at '; '
        out.extend(x for x in re.split(r"\s+[\u2022\u25aa\u25cfo]\s+(?=[A-Z$\d])", s) if len(x) > 8)
    return out


# ------------------------------------------------------------------ vocabulary
_STOCK_OPT = re.compile(r"(?i)\b(?:stock|share|incentive|employee)\s+options?\b|\boptions?\s+(?:to\s+purchase\s+up\s+to\s+[\d,]+\s+common|"
                        r"granted\s+to|(?:will\s+)?expire|are\s+exercisable)|\bgrant(?:ed|s|ing)?\s+(?:an\s+aggregate\s+of\s+)?[\d,]+\s+"
                        r"(?:incentive\s+)?options\b|\bgrant(?:s|ed)?\s+(?:of\s+)?(?:stock\s+|incentive\s+)?options\b(?!\s+to\s+acquire)|"
                        r"\bexercise\s+price\b|\bOption\s+Plan\b|\boptions?\s+to\s+(?:its\s+)?(?:directors|officers|consultants|management)|"
                        r"\bGrants\s+(?:Stock\s+)?Options\b|\bOption\s+Grants?\b|\bOptions?\s+Cancell?ation\b(?![^.]{0,40}propert)"
                        # 1.0.8: "... and Issues Options", "Cancellation of Options", "awarded 500,000 options"
                        r"|\b(?:issu(?:es|ed|ance\s+of)|award(?:s|ed)?|grant\s+of)\s+(?:an\s+aggregate\s+of\s+)?(?:[\d,]+\s+)?(?:incentive\s+|stock\s+)?"
                        r"options\b(?!\s+(?:to\s+acquire|on|over|for\s+the)\b)|\bcancell?ation\s+of\s+(?:[\w\-]+\s+){0,2}?options\b(?![^.]{0,40}propert)")
_OPT = re.compile(r"(?i)\boption(?:ed|s|ing)?\b|\bearn[- ]?in\b|\boptionor|\boptionee|\bearns?\s+(?:a\s+)?(?:further|additional|initial|"
                  r"second|first)\s+(?:\d{1,3}\s*%\s+)?interest\b")
_EARN_PCT = re.compile(r"(?i)\bearn(?:s|ed|ing)?\s+(?:up\s+to\s+)?(?:an?\s+|the\s+)?(?:initial\s+|additional\s+|undivided\s+|further\s+|full\s+)?"
                       r"(?:\d{1,3}(?:\.\d+)?\s*(?:%|-?per[\s-]?cent))")
_NP = r"(?:[^.;]|\.(?!\s)|(?<=\b[A-Z])\.|(?<=Corp)\.|(?<=Inc)\.|(?<=Ltd)\.)"     # not a sentence end: 'B.C.', 'Corp.'
_LAND = r"(?:propert(?:y|ies)|projects?|claims?|claim\s+block|licen[cs]es?|tenements?|land\s+(?:package|position)|concessions?|" \
        r"deposit|ground|mining\s+rights|mineral\s+rights|mines?(?!\s+(?:site\s+)?(?:operations|production|plan|life))|(?:exploration|uranium|mineral)\s+portfolio|mineral\s+and\s+surface\s+rights|" \
        r"lands|acres|(?:deeded\s+)?parcels?(?:\s+of\s+land)?|salars?)"
_PURCH = re.compile(r"(?i)\b(?:purchas(?:e|es|ed|ing)|acquir(?:e|es|ed|ing)|acquisition|buy|bought)\b" + _NP + r"{0,90}?\b" + _LAND + r"\b|"
                    r"\bProperty\s+Purchase\b|\b" + _LAND + r"\s+(?:purchase|acquisition)\b")
_STAKE = re.compile(r"(?i)\bstak(?:ed|ing|es)\b|\bexpansion\s+of\s+(?:the\s+|its\s+)?(?:Company['\u2019]s\s+)?(?:[\w-]+\s+){0,4}?"
                    r"(?:claim\s+block|land\s+(?:package|position)|claims?\s+(?:package|position))|\btenement\s+(?:filings?|applications?)|\bapplied\s+for\s+(?:\d+\s+)?(?:new\s+|additional\s+)?(?:mineral\s+|mining\s+|exploration\s+)?"
                    r"(?:claims|licen[cs]es|concessions|tenements|permits\s+covering)|\bapplications?\s+for\s+(?:\d+\s+)?(?:new\s+)?"
                    r"(?:mineral\s+|mining\s+|exploration\s+)?(?:claims|licen[cs]es|concessions|tenements)|\b(?:has\s+)?added\s+[\d,]+\s+"
                    r"(?:new\s+)?(?:mineral\s+|mining\s+)?claims|\b(?:were|was|been)\s+designated\b|\bmap[\s-]designat\w*|"
                    r"\bclaims\s+[\d,.]+\s+(?:hectares|ha)\s+of\s+new\s+(?:concessions|claims)|\b(?<!exploitation\s)(?<!mining\s)(?<!production\s)(?<!extraction\s)(?<!environmental\s)(?<!operating\s)(?:licen[cs]e|claim)\s+applications?\b|\bapplied\s+to\s+(?:increase|expand)\s+(?:its\s+)?(?:\w+\s+)?(?:land|claim)|\bprompted\s+mineral\s+licen[cs]e\s+application|"
                    r"\bincreased\s+(?:to\s+|the\s+)?size\s+of\s+(?:the\s+|its\s+)?(?:[\w\-]+\s+){0,3}?(?:propert|project|claim|land|package|holding|ground)|\bincreases?\s+(?:its\s+|the\s+)?(?:[\w\-]+\s+){0,3}?(?:project|property)\s+to\s+[\d,]+\s*"
                    r"(?:hectares|ha)\b|\b(?:expand|increas)(?:es|e|ed|s|ing)?\s+(?:its\s+|the\s+|our\s+)?(?:[\w\-]+\s+){0,2}?(?:land|claims?|mineral\s+claims?)\s+"
                    r"(?:position|package|holdings|base|area|footprint)\b|\b(?:expand|increas)\w*\s+(?:its\s+|the\s+|our\s+)?(?:mineral\s+)?claims?\s+(?:property\s+)?"
                    r"(?:position|to\s+[\d,]+\s+(?:hectares|ha))\b|\b(?:has\s+)?(?:added|adding|adds?)\s+(?:over\s+|more\s+than\s+|an?\s+"
                    r"(?:additional|further)\s+)?[\d,]+\s+(?:new\s+|additional\s+)?(?:mineral\s+|mining\s+)?claims|\bmade\s+(?:an?\s+)?"
                    r"applications?\s+to\s+acquire\b|\bapplications?\s+(?:have|has)\s+(?:now\s+)?been\s+(?:submitted|filed|made)\s+to\s+acquire\b|"
                    r"\bnewly\s+staked\b")
_SALE = re.compile(r"(?i)\b(?:sells?|sold|sale\s+of|divest\w*)\b[^.;]{0,80}\b(?:propert(?:y|ies)|projects?|claims|claim\s+blocks?|interest|mines?|licen[cs]es|tenements|"
                   r"(?<!oil\sand\sgas\s)(?<!equipment\s)assets|(?<=%\s)(?:share|stake)\s+(?:of|in))\b")     # 1.0.8: "sells its 50% share of X"
_THIRD = re.compile(r"(?i)\bthird[\s-]+part(?:y|ies)\b[^.]{0,80}\b(?:stak|filed|located)|\bhas\s+become\s+aware\b|\bwrongful\b|\btrespass\b")
_NONMINE = re.compile(r"(?i)\b(?:cannabis|marijuana|hemp|cultivation\s+licen|additive\s+manufacturing|technology\s+company|patent)\b")
_PROMO = re.compile(r"(?i)^\s*Market\s+One\b")
_BACKGROUND = re.compile(r"(?i)\b(?:also\s+(?:holds?|has|owns)|currently\s+(?:holds?|has)\s+(?:an?\s+)?option|holds?\s+(?:an?\s+|the\s+)?options?\s+"
                         r"(?:on|over|to)|has\s+(?:an?\s+)?options?\s+(?:on|over|to)|under\s+option\s+to|joins\s+our|"
                         r"(?:the|its|our)\s+(?:recently|previously|newly)\s+(?:acquired|optioned|staked)\s+\w+|portfolio\s+(?:that\s+)?includes|as\s+part\s+of\s+(?:their|its)\s+"
                         r"\w+\s+project|has\s+optioned\s+the\s+[A-Z]|holds\s+an\s+option\s+over|(?:its|our|[A-Z]\w+['\u2019]s)\s+optioned\s+\w+|"
                         r"\bin\s+which\s+the\s+Company\s+(?:owns|holds|has)\b|\bsince\s+acquiring\s+(?:the\s+)?[^.]{0,60}\bin\s+(?:19|20)\d\d\b|\bacquired\s+(?:the\s+)?[^.]{0,60}\bin\s+(?:January|February|March|April|May|June|July|August|September|October|"
                         r"November|December)\s+(?:19|20)\d\d\b|\bincluding\s+options?\s+to\s+(?:purchase|acquire)|\bbetween\s+(?:19|20)\d\d\s*(?:-|\u2013|and|to)\s*(?:19|20)\d\d\b|"
                         r"\b(?:now|currently)\s+(?:optioned|under\s+option)\b)")     # 1.0.9: "the X Project, now optioned to MATSA"
_THEIR_STAKING = re.compile(r"((?:[A-Z][\w&.\-]*\s+){0,4}(?!Company['\u2019]|Corporation['\u2019])[A-Z][\w&.\-]*)['\u2019]s\s+(?:\([^)]{0,30}\)\s+)?"
                            r"(?:[\w\-]+\s+){0,4}?(stak(?:ing|ed))\b")
# 1.0.9: another company's deal: "The San Antonio claims acquired by Osisko Development Corp. are contiguous with ..."
# 1.0.9: options dropped in passing ("has relinquished its options to acquire the Victoria and Tres Salares cobalt
# properties"): one row per property, kept apart from the release's main deal
_RELINQ = re.compile(r"(?i)\brelinquish\w*\s+(?:its|the|their|all)\s+(?:\w+\s+)?options?")
_DROP_OPT = re.compile(r"(?i)\bnot\s+to\s+proceed|\brelinquish\w*\s+(?:its|the|their|all)\s+(?:\w+\s+)?options?")
_OTHERS_DEAL = re.compile(r"\b(?:acquired|purchased|optioned|staked|bought|sold)\s+(?:recently\s+|earlier\s+)?by\s+((?!the\s+Company\b)(?:the\s+)?[A-Z][\w&.'\u2019\-]*"
                          r"(?:\s+[A-Z][\w&.'\u2019\-]*){0,3}\s+(?:Corp(?:oration)?|Inc|Ltd|Limited|LLC|Plc|S\.A|Mining|Mines|Resources|Metals|Minerals|"
                          r"Gold|Silver|Copper|Development|Exploration|Ventures)\b\.?)(?![^.]{0,80}\bpursuant\s+to\s+(?:an?|the)\s+option)")
# OPT_V1b (2026-09-23, corpus run c1): most false rows came from releases about something else (drill results,
# placements, MD&As, investor letters) that mention a deal in passing. Without a deal word in the headline, a body
# mention counts only in the first three sentences and only with a reporting verb.
_HL_DEAL = re.compile(r"(?i)\boption(?:s|ed|ing)?\b|\bearn[\s-]?in\b|\bearns?\b|\bstak(?:es|ed|ing)\b|\bacqui\w+|\bpurchas\w+|"
                      r"\bbuys?\b|\bsells?\b|\bsale\b|\bdivest\w*|\bLOI\b|\bletter\s+of\s+intent\b|\bterm\s+sheet\b|\bMOU\b|"
                      r"\b(?:expands?|increases?|adds?|grows?|doubles?|triples?|consolidates?|secures?)\b[^.]{0,60}\b(?:land|claims?|"
                      r"propert(?:y|ies)|ground|package|position|holdings|hectares|footprint)|\bnew\s+(?:claims|ground|licen[cs]es)\b|"
                      r"\bclaims?\s+(?:package|block|position|staking|acquisition)|\bland\s+(?:package|position)|\bvendors?\b")
_NEWS_VERB = re.compile(r"(?i)\b(?:has|have)\s+(?:now\s+|recently\s+|successfully\s+)?(?:entered|signed|executed|acquired|staked|"
                        r"completed|closed|exercised|terminated|amended|optioned|earned|agreed|made|issued|expanded|added)\b|"
                        r"\bentered\s+into\b|\b(?:announces?|announce)\s+(?:that\s+)?(?:the\s+)?(?:acquisition|signing|execution|"
                        r"completion|closing|staking|termination|amendment)\b")
_GENERIC_ACQ = re.compile(r"(?i)\b(?:focus(?:ed|es)?|engaged|speciali[sz]\w*|business|aims?|strategy|seeks?|objective|dedicated|"
                          r"committed|mandate|reviewing|evaluat\w+|pursue|pursuing|identify|identification)\b[^.]{0,60}\b(?:acqui|purchas)|"
                          r"\b(?:image|imagery|data|survey|geophysical|seismic|satellite|LiDAR|sample)\s+acquisition\b|"
                          r"\bacqui\w*\s+(?:(?!claims?\b|propert|projects?\b|mines?\b|deposit|land)[\w\-]+\s+){0,4}?(?:data|database|dataset|core|"
                          r"equipment|samples|survey\s+data|drill\s+rig|machine|mill|plant|fleet|trucks?|facility|concentrator|system)\b"
                          r"(?!\s+(?:Creek|Lake|River|Hill|Mountain|Property|Project|Claims?)\b)")
_SEE_EARLIER = re.compile(r"(?i)\(\s*see\s+(?:the\s+)?(?:company['\u2019]s\s+|our\s+|\w+\s+)?(?:press|news)\s+release|\(\s*see\s+[^)]{0,40}\b(?:release|news)\b")
_HISTORY = re.compile(r"^[\W_]*(?:Also,\s+)?(?:In|During|By)\s+(?:(?:early|late|mid)\s+)?(?:Q[1-4][\s\-]+)?(?:\w+\s+)?((?:19|20)\d\d)\b")

# 1.0.7: deals in things that are not ground. The phrase is blanked before the deal words are read, so a headline or
# sentence that also reports a land deal still does. Royalties, streams and offtakes, water rights, power, data sets,
# drills and equipment, concentrate and production sales; shares, equity stakes or an interest in a company; a right
# of first refusal; an LOI or agreement for services, advice or collaboration, or a strategic / generative alliance.
_NL_OBJ = r"(?:royalt(?:y|ies)|nsrs?|gors?|streams?|streaming|offtakes?|off-takes?|(?:ground)?water(?:\s+(?:rights?|permits?|licen[cs]es?))?|" \
          r"(?:historical\s+|historic\s+)?data(?:\s+sets?)?|" \
          r"database|dataset|core\s+(?:library|archive)|drills?|drill\s+rigs?|rigs|equipment|fleet|concentrates?|equity\s+stakes?|" \
          r"mill(?:ing)?\s+(?:assets|equipment|facilit(?:y|ies)|complex|buildings?)|(?:processing|mill)\s+plants?|processing\s+facilit(?:y|ies)|" \
          r"real\s+estate(?:\s+(?:assets?|parcels?|holdings?))?)"   # 1.0.8: mill assets, a processing plant, real estate
_NL_VERB = r"(?:(?:acqui\w+|purchas\w+|buys?|bought|sells?|sold|sale|divest\w*|dispos\w*|closes|closing|completes)\s+(?:of\s+)?(?:its\s+|an?\s+|the\s+)?)?"
_CO_NAME = r"(?!the\b)(?:(?-i:[A-Z0-9])[\w&.'\u2019\-]*\s+|(?:and|&|of|de|e|y|da|do|du|des|del)\s+){1,6}"   # 1.0.8: "Industria e Comercio"
class _Blank:
    """1.0.7: phrases to blank, each pattern tried only when one of its cue words is in the text (the backfill reads
    ~140k releases; one large alternation over every sentence was slow)."""

    def __init__(self, parts):
        self.parts = [(cues, re.compile("(?i)" + p)) for cues, p in parts]

    def sub(self, repl, s):
        low = s.lower()
        for cues, rx in self.parts:
            if any(c in low for c in cues):
                s = rx.sub(repl, s)
        return s


_NL_OBJ_CUES = ("royalt", "nsr", "gor", "stream", "offtake", "off-take", "water", "data", "core ", "drill", "rig", "equipment", "fleet",
                "concentrate", "equity stake", "mill", "processing", "real estate")
# an interest, a stake or shares in a company (not in a property): "Acquires 50% Interest in X Mines Inc.", "the
# closing of a 10% interest in a private company that owns the X Mine", "sell shares of X Ltd."; the deal verb goes with it
_CO_EQUITY = (r"\b" + _NL_VERB + r"(?:\d{1,3}(?:\.\d+)?\s*%\s+)?(?:indirect\s+)?(?:equity\s+)?(?:interest|stake|position|ownership)\s+in\s+"
              r"(?:an?\s+(?:private\s+)?company|" + _CO_NAME + r"(?:Inc|Corp|Corporation|Ltd|Limited|LLC|Plc|S\.A|Minerals|Mining|Resources|"
              r"Metals|Holdings|Ventures|S/A|SA|Ltda|S\.?R\.?L|SpA|SAS|GmbH|Pty|Oy|AB)\b\.?(?!\s*['\u2019]s)(?!\s+(?:Property|Project|Claims?|Mine|Deposit)\b))")
_NONLAND = _Blank([
    # a royalty, a stream, an offtake, water rights, a data set, drills or equipment bought or sold
    (_NL_OBJ_CUES,
     r"\b(?:acqui\w+|purchas\w+|buy[\s-]?backs?|buys?|bought|sells?|sold|sale|divest\w*|dispos\w*|monetiz\w+|monetis\w+)\s+(?:of\s+)?"
     r"(?:(?!propert|project|claim|concession|land|licen|tenement|mine\b|ground|and\b|with\b|to\b|from\b)[\w.%\u2019'\-]+\s+){0,7}?"
     + _NL_OBJ + r"\b(?!\s+(?:Creek|Lake|River|Hill|Mountain|Property|Project|Claims?)\b)"
     r"|\bpurchas\w+\s+and\s+\w+\s+(?:drills?|rigs?|equipment)\b"),
    # agreements, sales and purchases of things that are not ground: royalty, stream, offtake, water-rights, power and
    # data agreements, an LOI for a stream, concentrate and production sales
    (("royalt", "nsr", "stream", "offtake", "off-take", "water", "power", "concentrate", "data", "sale"),
     r"\b(?:royalt(?:y|ies)|nsr|streams?|streaming|offtakes?|off-takes?|water\s+rights?|power|concentrate|data|(?:silver|gold|metals?)\s+stream)"
     r"\s+(?:[\w\-]+\s+){0,2}?(?:purchase|sale|acquisition|agreement|term\s+sheet|transaction|portfolio|financing|investment|deal)s?\b"
     r"(?:\s+(?:and|&)\s+(?:sale|purchase))?(?:\s+agreements?)?"
     r"|\b(?:letter\s+of\s+intent|LOI|term\s+sheet|agreement)\s+(?:with\s+[^.;]{0,60}?\s+)?(?:for|on)\s+(?:an?\s+|the\s+)?(?:[\w\-]+\s+){0,3}?"
     r"(?:streams?|royalt(?:y|ies)|offtakes?)\b"
     r"|\b(?:first\s+)?(?:concentrate|production|ounces?|metal)\s+sales?\b|\bwater\s+rights?(?:\s+permits?)?\b|\bpower\s+purchase\b"
     # 1.0.8: a royalty bought back, a payment or an option whose object is a royalty ("Final Option Payment for Royalty Buy
     # Back"): the land is already the company's
     r"|\b(?:(?:final|first|second|third|last|annual)\s+)?(?:option\s+)?(?:payments?|options?)\s+(?:for|on|to\s+(?:buy|purchase|acquire|"
     r"repurchase))\s+(?:the\s+|an?\s+)?(?:[\w\-]+\s+){0,2}?(?:royalt(?:y|ies)|nsrs?|streams?)\b(?:\s+buy[\s-]?backs?)?"
     r"|\b(?:royalt(?:y|ies)|nsr)\s+(?:buy[\s-]?backs?|repurchases?)\b"),
    # "option" meaning a choice or a right that is not an option on ground: in the payment terms ("has the option to defer
    # 50% of the Deferred Consideration", "at the option of the holder"), mill or financing options, "exploring
    # options", an option to buy production, a right of first refusal (and the ground it covers)
    (("option", "refusal", "first offer", "rofr"),
     r"\bat\s+the\s+option\s+of\s+(?:the\s+)?(?:holder|lender|company|issuer|corporation|purchaser|investor)s?\b"
     r"|\b(?:at\s+(?:its|their|the\s+\w+['\u2019]s)\s+(?:sole\s+)?option|(?:has|have|with)\s+the\s+option\s+to\s+(?:defer|pay|satisfy|settle|"
     r"accelerate|elect|issue|extend|convert|make|reduce|buy\s+back|repurchase))\b"
     r"|\b(?:mill|processing|development|funding|financ\w+|plant|transport\w*|over[\s-]?allotment|underwriters?['\u2019]?|agents?['\u2019]?|"
     r"greenshoe)\s+options?\b|\b(?:two|three|several|various|other|many|a\s+lot\s+of)\s+options\b|\boptions?\s+(?:on|for|as\s+to)\s+how\b"
     r"(?!\s+(?:agreements?|to\s+acquire|on|over)\b)|\bBOOT\s+option\b"
     r"|\b(?:explor\w+|evaluat\w+|review\w*|consider\w*|assess\w*|pursu\w+)\s+(?:(?:the|all|various|several|other|strategic|potential|its|our|their)\s+)*"
     r"options\b"
     r"|\boption\s+to\s+(?:purchase|buy)\s+(?:\w+\s+){0,2}?(?:(?:silver|gold|metal|copper)\s+(?:produced|production|output|ounces)|"
     r"production|ounces|output|concentrates?)\b"
     r"|\b(?:acquisition\s+of\s+|acquires?\s+|grant\w*\s+|holds?\s+)?(?:an?\s+|the\s+)?(?:right\s+of\s+first\s+(?:refusal|offer)|"
     r"first\s+right\s+of\s+(?:refusal|offer)|ROFR)\b(?:\s+(?:over|on|to|for)\s+[^.;,]{0,60}?\b(?:claims|propert\w+|projects?|tenures?|licen\w+))?"),
    # equity: an interest, a stake or shares in a company, a share purchase plan or a buyback of shares
    (("interest in", "stake in", "position in", "ownership in", "shares", "share of", "securities of", "purchase plan", "issuer bid",
      "buyback", "buy-back", "stock"),
     _CO_EQUITY +
     r"|\b" + _NL_VERB + r"(?:(?:all\s+(?:of\s+)?)?the\s+)?(?:issued\s+and\s+outstanding\s+)?(?:common\s+)?(?:shares?|securities)\s+of\s+" + _CO_NAME +
     r"(?:Inc|Corp|Corporation|Ltd|Limited|LLC)\b\.?"
     r"|\b(?:share|stock)\s+purchase\s+plan\b|\bnormal\s+course\s+issuer\s+bid\b|\bbuy-?back\s+(?:of\s+)?(?:its\s+)?shares\b"
     # 1.0.8: shares held in another company sold or bought ("Sale of Firetail Shares", "sold 5,000,000 common shares of X")
     r"|\b(?:sale|sells?|sold|dispos\w+|divest\w*|acqui\w+|purchas\w+|buys?|bought)\s+(?:of\s+)?(?:(?:its|the|all|their)\s+)?"
     r"(?:[\d,.]+\s+(?:million\s+)?)?(?:(?-i:[A-Z])[\w&.'\u2019\-]*\s+){1,3}(?:common\s+)?(?:shares|stock)\b(?!\s+(?:purchase|exchange)\s+agreement)"
     r"|\b(?:sale|sells?|sold|dispos\w+|divest\w*)\s+(?:of\s+)?(?:(?:its|the|all|their)\s+)?(?:[\d,.]+\s+(?:million\s+)?)?(?:common\s+)?"
     r"(?:shares|stock|securities)\s+(?:of|in)\s+" + _CO_NAME),
    # agreements that transfer no ground: services, advice or collaboration; a strategic or generative alliance; a
    # mandate to look for a buyer or an intention to sell (no buyer, no agreement to sell)
    (("to act as", "to serve as", "advis", "toll", "processing", "service", "consulting", "epc", "construction", "supply", "collaboration",
      "cooperation", "co-operation", "alliance", "to sell", "to divest", "to dispose", "sales process", "sale process", "strategic review"),
     r"\b(?:letter\s+of\s+intent|LOI|MOU|memorandum\s+of\s+understanding|agreement)\b[^.;]{0,80}?\bto\s+(?:act|serve)\s+as\b"
     r"|\b(?:technical|engineering|strategic|financial)\s+advis\w+\b|\b(?:toll[\s-]?mill\w*|processing|services?|consulting|EPC|construction|"
     r"supply|collaboration|cooperation|co-operation)\s+(?:agreement|contract|LOI|letter\s+of\s+intent|MOU)\b"
     r"|\b(?:(?:letter\s+of\s+intent|LOI|MOU|agreement)\s+(?:for|on|to\s+form)\s+(?:an?\s+)?)?(?:strategic|generative|exploration)\s+alliance\b"
     r"|\b(?:intention|intends?|plans?|looking|seeking|decision|decided)\s+to\s+(?:sell|divest|dispose)\b|\bexplore\s+opportunities\s+to\s+"
     r"(?:sell|dispose|divest)\b|\bsales?\s+process\b|\bstrategic\s+review\b"),
    # 1.0.8: money, not ground: an LOI, term sheet or agreement for equity, a loan, a credit or pre-pay facility, an
    # investment, with no land or acquisition word in between; metal pre-paid or bought forward ("Pre-Pay Forward Purchase
    # Facility", "a forward purchase of 7,000 ounces of gold")
    (("equity", "financ", "loan", "credit", "facility", "funding", "investment", "capital", "pre-pay", "prepay", "pre- pay", "forward"),
     r"\b(?:letter\s+of\s+intent|LOI|term\s+sheet|MOU|memorandum\s+of\s+understanding|agreement)\s+(?:with\s+[^.;]{0,60}?\s+)?(?:for|to\s+"
     r"(?:provide|arrange|secure|raise))\s+(?:(?!\b(?:acqui\w+|purchas\w+|option\w*|propert\w+|projects?|claims?|lands?|sale|sells?|mines?|"
     r"interest|and)\b)[^.;,]){0,40}?\b(?:equity(?:\s+capital)?|financing|loan|credit|facility|funding|investment|capital|pre-?\s?pay\w*)\b"
     r"|\b(?:(?:gold|silver|metal)\s+)?(?:pre-?\s?pa(?:y|id)(?:ment)?\s+(?:forward\s+)?|forward\s+)(?:purchase|sale)s?"
     r"(?:\s+(?:facility|agreement))?(?:\s+of\s+(?:up\s+to\s+)?[\d,]+\s+(?:\w+\s+)?ounces(?:\s+of\s+\w+)?)?"
     r"|\b(?:gold\s+|silver\s+)?pre-?\s?pay(?:ment)?\s+facility\b"),
    # a geological footprint (mapped rock, mineralisation, an anomaly, a strike length), not ground
    (("footprint",),
     r"\b(?:expand\w*\s+(?:the\s+|its\s+)?)?(?:[\w\-]+ite|mineraliz\w+|mineralis\w+|alteration|anomal\w+|zones?|deposit|resource|"
     r"purity|grade|system|conductor|intrusi\w+)\W+(?:\w+\W+){0,2}?footprint\b"
     r"|\b(?:expand\w*\s+(?:the\s+|its\s+)?)?footprint\W+(?:\w+\W+){0,2}?[\d,.]+\s*(?:m|metres?|meters?|km|kilometres?|kilometers?)\b"
     r"|\bfootprint\b[^,;.]{0,40}\bstrike\b"),
])

# 1.0.7: the lead says what was bought is an interest in a company ("the closing of a 10% interest in a private
# company that owns 100% of the X Mine"): company-level, whatever the headline calls it (the equity kind above).
_CO_INTEREST = re.compile("(?i)" + _CO_EQUITY.replace(_NL_VERB, _NL_VERB[:-1], 1))      # here the deal verb must be there

# 1.0.7: the headline names an option only as someone else's work or as background: an "option partner" drilling or
# surveying, "X's optioned Y property", a project "under option to" a partner, a person's career "during the option of".
_HL_BACKGROUND = re.compile(
    r"(?i)\b(?:option|earn[\s-]?in|jv|joint\s+venture)\s+partner(?:s|['\u2019]s)?\b|\bpartner(?:s|['\u2019]s)?\b(?!\s+(?:on|in|to)\s+(?:the\s+)?"
    r"(?:acqui|purchas|option))|\boptioned\b(?!\s+(?:out|to)\b)|\b(?:under|held\s+under|during(?:\s+the)?)\s+(?:an?\s+)?option\b(?:\s+(?:to|of|from|with)\b)?"
    r"|\bunder\s+option\s+to\s+(?:[A-Z][\w&.'\u2019\-]*\s*){1,4}"
    r"|\b(?:following|after)\s+(?:the|its)\s+(?:previously\s+)?(?:announced|completed)\s+(?:sale|acquisition|option|purchase|disposition)\b"
    r"|\bpost[\s-]+(?:acquisition|closing|transaction)\b"      # 1.0.8: "Plans Drilling at X Post-Acquisition"
    # 1.0.8: an application the company already holds, named as the place of other news ("Review of Historic Data for
    # Their Orchy Licence Application")
    r"|\b(?:for|on|at|of|over)\s+(?:its|their|our|the\s+Company['\u2019]s)\s+(?:[\w\-]+\s+){0,3}?licen[cs]e\s+applications?\b")

# stage cues
_TERM = re.compile(r"(?i)\bterminat\w*|(?<!for\s)\bcancel+(?:ed|s|ation)\b|\bnot\s+to\s+proceed\b|\bdecided\s+not\s+to\b|\bdrop(?:s|ped)?\s+(?:the|its)\s+option|"
                   r"\brelinquish\w*|\babandon\w*|\bwithdr[ae]w\w*\s+from\s+the\s+option|\b(?:has\s+)?not\s+(?:to\s+)?exercis\w*\s+(?:its|the)\s+option|"
                   r"\belect\w*\s+not\s+to\s+(?:exercise|earn|proceed)")
_COMP = re.compile(r"(?i)\bacquired\s+an?\s+(?:initial|additional|further|undivided)\s+\d{1,3}\s*%|"    # 1.0.9: an earn-in step done
                   r"(?<!not\s)(?<!never\s)\bexercis(?:ed|es)\s+(?:the|its|an?)\b(?:\s+\w+){0,4}?\s*option\b|\bhas\s+(?:now\s+)?(?:successfully\s+)?earned\b|"
                   r"\bsuccessfully\s+earn|\bearns\s+(?:\d{1,3}\s*%|100)|\bearned\s+(?:an?\s+|its\s+)?(?:\d{1,3}\s*%|100)|"
                   r"\bcompleted\s+all\s+(?:the\s+)?requirements|\bcompletion\s+of\s+(?:the\s+)?final\s+(?:requirements|cash|payment|option)|"
                   r"\bnow\s+(?:holds|owns)\s+(?:a\s+)?\d{1,3}\s*%|\bnow\s+own\s+\d{1,3}\s*%|\bto\s+achieve\s+a\s+\d{1,3}\s*%\s+ownership|"
                   r"\bacquisition\s+(?:has\s+been\s+|was\s+)?(?:completed|closed)|\b(?:final|last)\s+(?:earn-in\s+)?option\s+payment\s+(?:to|for)\s+acquire|"
                   r"\bcomplet(?:ed|es)\s+(?:the\s+|its\s+)?(?:purchase|acquisition)\b(?:\s*\([^)]{0,40}\))?\s+of\b|\bCompletes\b[^.]{0,80}\bAcquisition\b|"
                   r"\bclos(?:ed|es)\s+(?:(?:on|its|the)\s+)+(?:previously\s+announced\s+)?(?:\w+\s+){0,8}?(?:acquisition|purchase)(?!\s+of\s+(?:an?|the)\s+option|\s+to\s+earn)|"
                   r"\bclos(?:ed|es)\s+(?:(?:on|its|the)\s+)+(?:previously\s+announced\s+)?(?:\w+\s+){0,6}?(?:sale|disposition|transaction)\b|"
                   r"\bClosing\s+of\s+(?:the\s+)?(?:\w+\s+){0,3}?(?:Sale|Acquisition|Purchase)\b|\bfinali[sz](?:es|ed)\s+(?:the\s+|its\s+)?acquisition|"
                   r"\b(?:third\s+and\s+)?final\s+(?:cash\s+|property\s+|option\s+)?payment\b[^.]{0,80}\bto\s+(?:acquire|exercise)|"
                   r"\bfully\s+satisfied\s+(?:its|all)\s+(?:\w+\s+)?(?:purchase|payment|option)\s+obligations|\bsecur(?:ing|es|ed)\s+100\s*%\s+ownership|"
                   r"\b(?:transaction|acquisition|purchase|sale)\s+(?:was|has\s+been)\s+(?:completed|closed)|\bhas\s+now\s+acquired\b|"
                   r"\bfull\s+earn[\s-]?in\s+status|\bExercises\b[^.]{0,40}\bOption\b|\bEarns\s+\d|\bCompletes\s+\d{2,3}%\s+Earn|"
                   r"\b(?:complet(?:ed|es)|ma(?:de|kes)|paid|pays)\s+(?:the\s+|its\s+|all\s+)?(?:final|last)\s+(?:\w+\s+){0,2}?payments?\b|"
                   r"\bclos(?:ed|es)\s+(?:the\s+|its\s+)?sale\s+of\b|\bfinali[sz](?:ed|es)\s+(?:the\s+|its\s+)?sale\b|"
                   r"\bcomplet(?:ed|es)\s+(?:the\s+|its\s+)?sale\s+of\b(?!\s+(?:\d|shares|securities|units|flow))|"
                   r"\b(?:pleased|delighted|excited)\s+to\s+(?:have\s+)?(?:close|closed|complete|completed)\s+the\s+(?:[\w\-]+\s+){0,3}?"
                   r"(?:amalgamation|acquisition|purchase|transaction)")
_AMEND = re.compile(r"(?i)\bamend(?:ed|s|ing|ments?)\b|\bextend(?:ed|s)?\s+(?:the\s+)?(?:Outside|term|option|deadline|date)|\bextension\s+(?:of|to)\s+(?:the\s+)?(?:\w+\s+){0,2}?(?:option|term|agreement|deadline|date|time|outside|period|expiry|LOI|letter\s+of\s+intent)\b|"
                    r"\bextend(?:s|ed|ing)\s+(?:the\s+|its\s+)?(?:[\w\-]+\s+){1,2}?(?:option(?:\s+agreement)?|LOI|letter\s+of\s+intent|deadline)\b|\bextending\s+the\s+(?:date|term|deadline|time)\b|"
                    r"\bland\s+position\s+covered\s+under\s+the\s+option|\brevised\s+terms\b|\bto\s+expedite\s+earn|\brenegotiat\w+|\baddend(?:um|a)\b|"
                    # 1.0.8: the deadline to close extended ("Extension of X Acquisition Closing", "agreed to extend the
                    # period to complete the acquisition")
                    r"\bextension\s+of\s+(?:the\s+)?(?:[\w\-]+\s+){0,3}?closing\b|\bextend\w*\s+(?:the\s+)?(?:period|time|closing\s+date|"
                    r"outside\s+date)\s+(?:to|for)\s+(?:complete|close|closing)\b")
_PAY = re.compile(r"(?i)\b(?:issu(?:ed|es|ance\s+of)|made|makes|received|receives|paid)\b[^.]{0,90}\b(?:shares|payment)\b[^.]{0,90}"
                  r"\b(?:pursuant\s+to|under|in\s+connection\s+with|per)\b[^.]{0,40}\b(?:option|agreement)|"
                  r"\b(?:first|second|secondary|third|fourth|annual)\s+(?:anniversary\s+)?(?:option\s+)?payment\b|\b(?:second|third|first|initial)\s+"
                  r"tranche\s+of\s+(?:common\s+)?shares|\bissu(?:ed|es)\s+(?:a\s+)?further\s+[\d,]+\s+(?:common\s+)?shares|"
                  r"\bIssues\s+Shares\s+in\s+Connection\s+with\b|\bMakes\s+(?:\w+\s+)?Option\s+Payment\b|\bIssuance\s+of\s+(?:a\s+)?"
                  r"(?:First|Second|Third)\s+Tranche|\b(?:pursuant\s+to|under)\s+the\s+option\b[^.]{0,40}\b(?:received|made|paid)\b[^.]{0,20}\bpayment|"
                  r"\bOption\s+Payment\s+Received\b")
_PAY_HL = re.compile(r"\b(?:Completes|Makes|Pays)\s+(?:(?:Initial|First|Second|Third|Annual|Final)\s+)?(?:Milestone\s+|Option\s+)?Payments?\b|"
                     r"\bEarns\s+Further\s+Interest\b|(?i:\bissues\s+(?:(?:first|second|third|final|annual)\s+)?(?:[\d,.]+\s+(?:million\s+)?)?"
                     r"(?:common\s+|consideration\s+)?shares\s+(?:to|for|under|pursuant))|(?i:\bcontinu(?:es|ing)\s+(?:to\s+|its\s+)?earn[\s-]?in\b)|(?i:\breceives?\b[^.]{0,60}\b(?:payments?|consideration|proceeds)\b)")          # headline only: in a body these are defined terms
_PROP = re.compile(r"(?i)\bletter\s+of\s+intent\b|\bLOI\b|\bmemorandum\s+of\s+understanding\b|\bMOU\b|\bterm\s+sheet\b|\bnon-binding\b|"
                   r"\bcontinued\s+to\s+pursue\s+the\s+acquisition\b|\bnegotiat\w+\s+(?:an?\s+)?increased\s+interest")
_SIGN = re.compile(r"(?i)\bentered\s+(?:in)?to\b|\bsign(?:ed|s)\b|\bexecut(?:ed|es)\b|\bdefinitive\b|\bagreement\s+dated\b|"
                   r"\bclos(?:ed|es)\b|\bapproval\b|\bhas\s+acquired\b|\bacquires\b|\bstaked\b|\bstakes\b|\bstaking\b|\bapplication\b|"
                   r"\bgranted\b|\boptions\b|\bagreed\s+to\s+(?:purchase|acquire)\b|\bincreased\b")

# ------------------------------------------------------------------ names
_LEGAL = r"(?:Corp(?:oration)?|Inc|Ltd|Limited|LLC|L\.L\.C|Pty(?:\s+Ltd)?|S\.A|SAS|GmbH|Ltda)"
_ORGW = r"(?:[A-Z][\w&'\u2019\-.]*|of|and|&|de|du|des)"
_ORG_TAIL = r"(?:" + _LEGAL + r"|Resources|Metals|Mining|Minerals|Mines|Gold(?:\s+Mines)?|Uranium|Exploration|Explorations|Ventures|Energy|" \
            r"Lithium|Royalties|Holdings|Capital(?:\s+Corporation|\s+Management(?:,?\s+LLC)?)?|Investment\s+Group|Silver|Copper|Nickel|Graphite)"
_ORG = re.compile(r"(\d{6,8}\s+(?:B\.?\s?C\.?|Ontario|Alberta|Canada|Qu\u00e9bec|Quebec)\s+(?:Ltd|Inc|Corp)\.?|"
                  r"(?:[A-Z][\w&'\u2019\-.]*)(?:\s+" + _ORGW + r"){0,5}?\s+" + _ORG_TAIL + r"\.?)")
_ORG_BAD = re.compile(r"(?i)^(?:the\s+)?(?:company|optionor|optionee|vendors?|purchaser|buyer|property|project|agreement|option|canadian\s+"
                      r"securities|tsx|cse|exchange|national\s+instrument|net\s+smelter|investor|mineral|qualified|board|"
                      r"common\s+shares?|shares?|each|pursuant|under|upon|if|following|in|on|and|to|with|from|by|at)\b")
_ALIAS = re.compile(r"[\u201c\"]\s*([A-Z][^\u201d\"]{1,40}?)\s*[\u201d\"]\s*(?:,\s*)?(?:or|and)\s+(?:the\s+|\u201cthe\s+)?[\u201c\"]?\s*(?:Company|Corporation|Issuer)\b")
_PROP_SUFFIX = r"(?:[Pp]roperty|[Pp]roperties|[Pp]roject|[Pp]rojects|Claims?|Claim\s+Block|Claims\s+Package|Tenements?|Licen[cs]es?|Deposit|Mines|Mine|PROPERTY|PROJECT)"
# 1.0.9: metals written in lower case between a name and a lower-case suffix ("the Clipper gold-silver property", "the
# Lucky copper-gold project") are not part of the name, and do not hide it
_LC_METAL = r"(?:gold|silver|copper|zinc|lead|nickel|cobalt|lithium|uranium|graphite|tungsten|antimony|molybdenum|vanadium|pgm|pge|" \
            r"polymetallic|base\s+metals?|precious\s+metals?|rare\s+earths?|ree)"
_PROP_RX = re.compile(r"((?:[A-Z\u00c0-\u00dd][\w'\u00c0-\u00ff\-/.]*)(?:\s+(?:[A-Z\u00c0-\u00dd0-9][\w'\u00c0-\u00ff\-/.]*|-|\u2013|de|del|la|du|y|and|&|of|\(\w+\)|S\.E\.)){0,5}?)"
                      r"(?:(?P<lcm>(?:\s+" + _LC_METAL + r"(?:[-\u2013/]" + _LC_METAL + r"){0,3}){1,2})(?=\s+(?:propert(?:y|ies)|projects?|claims)\b"
                      r"(?!\s+(?:area|areas|boundary|boundaries|portfolio|team|site|level)\b)))?\s+"
                      + _PROP_SUFFIX + r"\b(?!\s+(?i:workings|tailings|waste|dumps?)\b)")   # OPT_V1f: "Mine Workings"
_QUOTED = re.compile(r"(?:the\s+)?[\u201c\"]([A-Z][\w'\u00c0-\u00ff\-\s/]{1,40}?)[\u201d\"]")
_BAD_P = {"Ready", "Drill", "Drill-Ready", "Oz", "Ounce", "Ounces", "Koz", "Moz", "Historical", "Historic",      # OPT_V1f
          "Major",                                                                                 # OPT_V1f (round 4)
          "Option", "Options", "Agreement", "The", "This", "Its", "Company", "Company's", "Acquire", "Acquires", "Acquisition", "Earn",
          "Earn-In", "Signs", "Enters", "Announces", "Closes", "Executes", "Terminates", "Amends", "Exercises", "Completes", "Stakes",
          "New", "Additional", "Mineral", "Mining", "Exploration", "Gold", "Uranium", "Lithium", "Copper", "Silver", "Nickel", "Strategic",
          "Four", "Three", "Two", "Nine", "Eight", "Six", "Five", "Advanced", "Flagship", "Past", "Producing", "Contiguous", "Adjacent",
          "Unpatented", "Patented", "Single", "Cell", "Unit", "Units", "Rare", "Earth", "Element", "Critical", "Metals", "Mineral", "Quebec",
          "Qu\u00e9bec", "Ontario", "Nevada", "Saskatchewan", "British", "Columbia", "Manitoba", "Newfoundland", "Idaho", "Yukon", "Nunavut",
          "Arizona", "Wyoming", "Brazil", "Argentina", "Mexico", "Sweden", "Tanzania", "Europe", "Australia", "Western", "Northern",
          "Southern", "Eastern", "Central", "In", "On", "At", "For", "Of", "To", "A", "An", "And", "Interest", "Undivided", "Right",
          "Title", "Its", "Their", "Our", "High", "Grade", "High-Grade", "Large", "Prospective", "Highly", "Key", "Primary", "Main",
          "Portion", "All", "Both", "Each", "Other", "Existing", "Initial", "Final", "Proposed", "Definitive", "Binding", "Letter",
          "Intent", "LOI", "MOU", "Purchase", "Sale", "Property", "Project", "Claims", "Claim", "Staked", "Area", "Road", "Accessible",
          "Iron", "Zinc", "Antimony", "REE", "Gallium", "Tungsten", "Polymetallic", "Base", "Precious", "Battery", "Lode", "Cobalt",
          "Graphite", "Energy", "Resources", "Additional", "Acquired", "Acquiring", "Newly", "Optioned", "Transaction", "Update",
          "Expands", "Increases", "Increased", "Expanded", "Consolidates", "Mining", "Surrounding", "Nearby", "Existing", "Sherridon's",
          "Hectares", "Hectare", "Ha", "Km", "Acres", "Claim", "Package", "Block", "Its", "His", "Her", "Added", "More", "Stage",
          "Advanced-Stage", "Non-Core", "Figure", "Table", "Intellectual", "Large", "Recently", "Historic", "Current", "Final",
          "Prospective", "Staking", "Through", "Development", "Drill-Ready", "District-Scale", "Develop", "Targets", "Target",
          "Expanding", "Adding", "Increasing", "Enhancing", "Strengthening", "Consolidating", "Further", "Growing",
          # 1.0.7: headline descriptions, not names ("Third Hard-Rock", "Ground Covering Historic Vidette ...")
          "First", "Second", "Third", "Fourth", "Hard-Rock", "Ground", "Covering", "Identified", "Newly-Identified", "Vendor",
          "Vendors", "Disputed", "Investment", "District", "Camp", "Area", "High-Impact", "Large-Scale", "World-Class",
          "Road-Accessible", "Past-Producing", "Near-Surface", "Bulk-Tonnage"}
_COMMOD = {"palladium", "platinum", "group", "elements", "element", "pge", "pgm", "pges", "ree", "rare", "earth", "earths", "metals",
           "sulphidation", "sulfidation", "porphyry", "epithermal", "skarn", "vms", "iocg", "sedex", "intrusion-related",   # 1.0.7
           "gold", "silver", "copper", "zinc", "lead", "nickel", "cobalt", "lithium", "uranium", "vanadium", "molybdenum", "tungsten",
           "antimony", "graphite", "gallium", "germanium", "and", "base", "precious", "critical", "battery", "polymetallic"}


_PVERB = {"Secures", "Secured", "Grows", "Sign", "Enter", "Execute", "Complete", "Announce", "Acquiring",      # OPT_V1f
          "Optimizes", "Optimises", "Extend", "Extends", "Consolidate", "Buy", "Buys", "Expand", "Advances", "Advance",   # 1.0.7
          "Identifies", "Highlights", "Confirms", "Strengthens", "Expanding",
          "Options", "Option", "Acquires", "Acquire", "Signs", "Amends", "Enters", "Executes", "Exercises", "Announces", "Closes",
          "Terminates", "Completes", "Stakes", "Increases", "Expands", "Receives", "Issues", "Makes", "Earns", "Sells", "Consolidates",
          "Adds", "Grants", "Provides", "Reports", "Update", "Updates", "Restating", "Terms", "Owners", "Agreement", "Agreements",
          "OPTIONS", "ACQUIRES", "SIGNS", "AMENDS", "ENTERS", "EXERCISES", "ANNOUNCES", "TERMINATES", "COMPLETES", "STAKES",
          "INCREASES", "EXPANDS", "RECEIVES", "UNDER", "Under", "For", "FOR", "of", "OF", "Of", "at", "AT", "At", "in", "IN", "In", "on", "ON", "On",
          "to", "TO", "To", "from", "FROM", "From", "with", "WITH", "With", "Near", "near", "Along", "Around", "Adjacent", "by", "By"}
_PLACES = {"nova scotia", "quebec", "qu\u00e9bec", "ontario", "british columbia", "bc", "nevada", "idaho", "saskatchewan", "manitoba", "yukon",
           "nunavut", "newfoundland", "labrador", "new brunswick", "arizona", "utah", "wyoming", "alaska", "montana", "argentina", "chile",
           "peru", "mexico", "brazil", "sweden", "finland", "norway", "tanzania", "australia", "western australia", "europe", "canada",
           "usa", "james bay", "athabasca", "athabasca basin", "abitibi", "timmins", "red lake", "ecuador", "colombia", "niger",
           "third", "second", "first", "fourth", "new", "lithium", "gold", "uranium", "copper", "exploration", "four", "three", "two",
           "mineral", "strategic", "additional",
           # 1.0.7: a country is not a property's name ("Zimbabwe Gold-Base Metal Prospect")
           "zimbabwe", "namibia", "botswana", "ghana", "mali", "burkina faso", "guinea", "kenya", "zambia", "congo", "drc",
           "morocco", "egypt", "ethiopia", "spain", "portugal", "serbia", "bosnia", "turkey", "turkiye", "greenland", "ireland",
           "scotland", "bolivia", "guatemala", "honduras", "nicaragua", "panama", "philippines", "indonesia", "mongolia",
           "kazakhstan", "paraguay", "uruguay", "guyana", "suriname", "south africa", "tanzania", "sweden", "norway",
           "base", "metal", "hard", "rock", "hard-rock", "base metal",
           # 1.0.9: more countries; "C\u00f4te d'Ivoire Projects" leaves "Ivoire" once the apostrophe cuts the name
           "ivoire", "cote d ivoire", "ivory coast", "senegal", "liberia", "sierra leone", "nigeria", "cameroon",
           "gabon", "madagascar", "mozambique", "angola", "uganda", "rwanda", "malawi", "eritrea", "sudan", "mauritania",
           "niger", "chad", "togo", "benin", "tunisia", "algeria", "saudi arabia", "oman", "armenia", "georgia", "kyrgyzstan",
           "uzbekistan", "tajikistan", "papua new guinea", "fiji", "new zealand", "united states", "united kingdom", "france",
           "germany", "italy", "austria", "slovakia", "czech republic", "poland", "romania", "bulgaria", "greece", "cyprus",
           "albania", "kosovo", "montenegro", "north macedonia", "croatia", "slovenia", "hungary", "ukraine", "dominican republic",
           "haiti", "jamaica", "cuba", "costa rica", "el salvador", "belize", "venezuela", "china", "japan", "korea", "vietnam",
           "laos", "cambodia", "thailand", "malaysia", "myanmar", "india", "pakistan", "afghanistan"}


_LANDFORM = {"Lake", "Lakes", "Mountain", "Hill", "Hills", "Creek", "River", "Bay", "Ridge", "Valley", "Point", "Island", "Pond",
             "Brook", "Peak", "Canyon", "Star", "King", "Queen", "Cross", "Dome", "Butte", "Flats", "Springs", "Basin"}


_NUMNAME = {"One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"}   # OPT_V1f


# 1.0.5: a landform needs its qualifier. The words this reader (or the helper) strips as lead-ins that also start place
# names before a landform: "Mineral Ridge", "Table Mountain", "Key Lake", "High Lake", "Iron Lake", "Silver Hill".
_GEO_W = set(PN._GEO) | {"Lakes", "Hills", "Brook", "Pond", "Island", "Peak"}
_GEO_QUAL = {"Mineral", "Table", "Key", "High", "Iron", "Silver", "Gold", "Golden", "Copper", "Nickel", "Cobalt", "Lithium",
             "Uranium", "Zinc", "Graphite", "Antimony", "Tungsten", "Big", "Red", "Black", "White"}
_GEO_STOP = {"the", "its", "our", "their", "his", "her", "this", "that", "a", "an", "and", "of", "for", "to", "in", "on",
             "at", "from", "with", "by", "or", "as", "into", "near", "new",
             "sell", "sells", "selling", "sold", "sale", "buy", "buys", "bought", "acquire", "acquires", "acquired", "option",
             "options", "optioned", "stake", "stakes", "staked", "purchase", "purchases", "purchased", "expand", "expands",
             "expanded", "increase", "increases", "return", "returns", "returned", "transfer", "transfers", "transferred",
             "divest", "divests", "divested", "drop", "drops", "dropped", "terminate", "terminates", "terminated",
             "called", "named", "known", "about", "around", "along", "across", "between", "west", "east", "north", "south"}


def _tt(w):
    return w.title() if w.isupper() and len(w) > 1 else w


def _geo_back(toks, j, loose=False):
    """1.0.5: the words to put back in front of toks[j], a landform: [] or ["Mineral"], ["Rare", "Earth"], ["Schott's"].
    loose: also any plain capitalised word (the capture stopped short of it: "Case Lake West", "Monster Lake East")."""
    if j <= 0 or j >= len(toks) or _tt(toks[j].strip("\"\u201c\u201d\u2018\u2019'(")) not in _GEO_W:
        return []
    t = toks[j - 1]
    if re.search(r"[,;:)\u201d\u2019\"]$", t) and not re.search(r"[A-Za-z]\u2019s$|[A-Za-z]'s$", t):
        return []                                  # a list, a clause or a quotation ends before the landform
    w = t.lstrip("\"\u201c\u2018'(").replace("\u2019", "'")
    if not re.fullmatch(r"[A-Z][A-Za-z'\-]*", w):
        return []
    wt = _tt(w)
    w2 = toks[j - 2].lstrip("\"\u201c\u2018'(").replace("\u2019", "'") if j >= 2 else ""
    tail = bool(re.fullmatch(r"[A-Z][\w'&.\-]*", w2)) and not re.search(r"[,;:]$", toks[j - 2]) and \
        _tt(w2) not in _BAD_P and _tt(w2) not in _PVERB and w2.lower() not in _GEO_STOP and not re.search(r"'s$", w2)
    if wt == "Earth" and _tt(w2) == "Rare":
        return [toks[j - 2].lstrip("\"\u201c\u2018'("), w]              # "Rare Earth Ridge"
    if w in PN._GEO_FIRST or wt in ("Mineral", "Table", "Key", "High"):
        return [w]                                              # "Mineral Ridge", "Voisey's Bay", "Key Lake South"
    if re.fullmatch(r"[A-Z][A-Za-z\-]+'s", w) and wt not in _BAD_P and w[:-2] not in ("Company", "Corporation", "Issuer") \
            and not w.isupper():
        return [w]                                              # "Schott's Lake"
    if wt in _GEO_QUAL and not tail:
        return [w]                                              # "Iron Lake"; not "Toogood Gold Table..."
    if loose and not w.isupper() and wt not in _BAD_P and wt not in _PVERB and w.lower() not in _GEO_STOP and \
            wt not in _GEO_W and not tail and len(w) > 2:
        return [w]                                              # "Case Lake West", "Monster Lake East"
    return []


def _geo_ext(p, text, pos=None):
    """1.0.5: a name starting with a landform, found at text[pos] (or searched for), gets the word in front of it back
    when that word is its qualifier (_geo_back, loose). Several names (" / ") are left alone."""
    if not p or " / " in p:
        return p
    nw = p.split()
    if _tt(nw[0]) not in _GEO_W:
        return p
    if pos is None:
        m = re.search(r"(?<![\w'\u2019])" + r"\s+".join(re.escape(w) for w in nw[:2]) + r"\b", text) or \
            re.search(r"(?i)(?<![\w'\u2019])" + r"\s+".join(re.escape(w) for w in nw[:2]) + r"\b", text)
        if not m:
            return p
        pos = m.start()
    toks = text[max(0, pos - 80):pos].split()
    add = _geo_back(toks + [nw[0]], len(toks), loose=True)
    if not add:
        return p
    if all(a.isupper() for a in add) and not nw[0].isupper():
        add = [_caps_title(a) for a in add]
    return " ".join(add + nw)


def _juris(h, sents, ms, n_deals):
    """1.0.5: where the property is -- the Permits reader's rule. One deal: the headline and the release; one deal among
    several: that deal's own sentences only, so a neighbour's province is not borrowed."""
    if n_deals > 1:
        return PM._jurisdiction("", PM._short([m["s"] for m in ms if not m["hl"]]))
    return PM._jurisdiction(h, PM._short([x for x, is_hl in sents if not is_hl]))


def _pretrim(name, keep_tail=False):
    """Cut this reader's lead-ins off a captured candidate ("Options", "Acquires", "Expanding Its", "Additional",
    "Contiguous"...). The shared helper then names what is left (_name)."""
    ws0 = name.replace("\u2019", "'").split()
    cut = 0
    for i, w in enumerate(ws0):
        if w.strip(",;:") in _PVERB or w.isupper() and len(w) > 1 and w.strip(",;:").title() in _PVERB or w.endswith((",", ";", ":")):
            cut = i + 1
    ws = ws0[cut:]
    if len(ws) >= 3 and ws[0].strip(",;:").title() == "Key":
        ws = ws[1:]            # OPT_V1f: "Secures Key South Preston Uranium Property"; "Key Lake" keeps its name
    ws_before = list(ws)
    while ws and (ws[0].strip(",;:") in _BAD_P or ws[0].strip(",;:").title() in _BAD_P or ws[0].lower() in ("and", "of", "&", "-", "\u2013", "the", "de", "y")
                  or re.search(r"'s$", ws[0]) or re.match(r"^\d", ws[0])):
        if len(ws) > 1 and ws[0].title() in _NUMNAME and ws[1].lower() in ("mile", "miles"):
            break              # OPT_V1f: "Nine Mile Brook", "Forty Mile" keep their number
        ws = ws[1:]
    j0 = len(ws0) - len(ws)
    if ws and j0 > 0:
        ws = _geo_back(ws0, j0) + ws         # 1.0.5: "Mineral Ridge", "Table Mountain", "Key Lake South"
    while ws and not keep_tail and (ws[-1] in _BAD_P or ws[-1].title() in _BAD_P or
                                    ws[-1].lower() in ("and", "of", "&", "-", "\u2013", "the", "de", "y")):
        ws = ws[:-1]
    if len(ws) == 1 and len(ws_before) > 1 and ws[0][:1].isupper() and ws[0].strip(",;:").title() not in _BAD_P \
            and ws[0].strip(",;:").replace("-", "").isalpha():
        # OPT_V1f: any one word, not only a landform: "Silver Park", "Rare One" (was: _LANDFORM only, "Silver Lake")
        i = len(ws_before) - 1 - ws_before[::-1].index(ws[0])
        if i > 0 and ws_before[i - 1].title() in ("Silver", "Gold", "Copper", "Iron", "Nickel", "Cobalt", "Lithium", "Uranium", "Zinc",
                                                  "Graphite", "Antimony", "Tungsten", "Rare", "Golden", "Red", "Black", "White", "Big"):
            ws = [ws_before[i - 1], ws[0]]      # OPT_V1b: "Silver Lake", "Cobalt Mountain" are names
    if not ws or all(re.sub(r"[()]", "", x).lower() in _COMMOD for w in ws for x in re.split(r"[/\-]", w) if x):
        return None             # OPT_V1d: "PALLADIUM/PLATINUM GROUP ELEMENTS (PGE) PROJECT" is a commodity, not a name
    s = " ".join(ws).strip(" ,;:.")
    if len(s) < 2 or not re.search(r"[A-Za-z]{2}", s) and not re.fullmatch(r"[A-Z]{1,2}\d{1,3}", s):
        return None            # OPT_V1f: "N2 Property" is a name
    return s


def _caps_title(s):
    return " ".join("-".join(x[:1].upper() + x[1:].lower() for x in w.split("-")) for w in s.split(" "))


def _name(raw, suffix=None):
    """OPT_V1e (PN_V1): a property candidate, pre-trimmed of this reader's lead-ins, named by portal/project_names.py.
    Returns "<name> <suffix>" (e.g. "Troilus North Property") or None."""
    if not raw:
        return None
    pre = _pretrim(raw)
    if not pre:
        return None
    if not PN.clean(pre, suffix) and PN.clean(_pretrim(raw, keep_tail=True) or "", suffix):
        pre = _pretrim(raw, keep_tail=True)
    raw_suffix = re.sub(r"\s+", " ", suffix.strip()) if suffix else ""
    if suffix:
        suffix = re.sub(r"\s+", " ", suffix.strip())
        if suffix.isupper() or suffix.islower():
            suffix = _caps_title(suffix)
    if pre.isupper() and len(pre) > 3:
        pre = _caps_title(pre)
    n = PN.clean(pre, suffix)
    if n and _tt(n.split()[0]) in _GEO_W:
        pt = pre.split()
        j = next((i for i, w in enumerate(pt) if w == n.split()[0]), 0)
        add = _geo_back(pt, j)
        if add:
            n = " ".join(add) + " " + n    # 1.0.5: the helper cuts "High", "Schott's" ("High Lake", "Schott's Lake")
    if not n and suffix in ("Property", "Project", "Claims") and len(pre.split()) == 1 and PN._REGION.match(pre) \
            and raw_suffix[:1].isupper():
        n = pre + " " + suffix     # OPT_V1f: "Molten Metals Options Texas Property" names the Texas Property
    if not n:
        return None
    for part in re.split(r"\s+(?:and|&)\s+", PN.bare(re.sub(r"\s+" + PN.SUFFIX + r"$", "", n))):
        if len([w for w in part.split() if not w.startswith("(") and T._fold(w).lower() not in _COMMOD and
                w.lower() not in ("of", "de", "del", "la", "y", "rare", "earth", "vms", "sedex", "porphyry", "skarn", "iocg")]) > 4:
            return None            # OPT_V1f: "NV Quito Gold Lander NV America Mine" is a list, not a name ("VMS" is a deposit type)
    if re.search(r"(?i)\b(?:financing|placement|offering|equity)\b", n):
        return None                # OPT_V1f: "Closing of Equity Financing & Mineral Claims Acquisitions"
    if re.search(r"(?i)\b(?:debt|settlement|investment|shares|warrants|loan|transaction|update)\b|\w-(?:area|region|district)\b|"
                 r"\b(?:trend|belt|goldbelt|district|region|camp)\s+(?:" + PN.SUFFIX + r")$", n):
        return None                # 1.0.7: "Debt Settlement Property", "Investment Property", "Timmins-Area Properties"
    k = PN.key(n)
    if k and all(len(w) <= 2 and w.isalpha() for w in k.split()):
        return None                # OPT_V1f: "N WT Lithium Properties"
    if not k or len(k) < 3 and not (len(k) == 2 and re.search(r"\d", k)) or T._fold(k) in _PLACES or all(w in _PLACES for w in k.split()) or all(w in _COMMOD for w in k.split()):
        return None
    if n.count("(") > n.count(")"):
        n = re.sub(r"\s\([^()\s]*(?=\s|$)", "", n)   # 1.0.5: "Jonathan's Pond (JP) Gold Project" had lost its ")"
    return n


_PLIST = re.compile(r"((?:[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+)?,\s+)+(?:[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+)?,?\s+)?and\s+(?:the\s+)?"
                    r"[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+)?)\s+(?:\w+\s+)?(?:[Pp]rojects|[Pp]roperties)\b")


# 1.0.9: a name written after a relation is a neighbour's or the host project the new ground lies by, not the deal's
# ("contiguous to X", "on extension of X", "along strike of its X", "on trend with its X", "2 km northeast from NAM's
# previously staked X", "positioned between X and Y"); upper-case headlines included.
_NEAR_ONLY = re.compile(r"(?i)\b(?:adjacent\s+to|near|nearby|contiguous\s+(?:to|with)|next\s+to|along\s+(?:strike|trend)\s+(?:from|of|with|to)|"
                        r"on\s+(?:the\s+)?(?:same\s+)?trend\s+(?:with|from|as)|(?:the\s+|an?\s+)?(?:\w+\s+)?extensions?\s+(?:of|to)|between|"
                        r"(?:south|north|east|west)\w*\s+(?:of|from)|close\s+to|proximity\s+to|neighbou?ring|bordering|adjoining)\s+(?:the\s+)?"
                        r"(?:[\w'\u2019.&\-]+\s+){0,4}$")      # 1.0.9: the same, without "expands" (staked ground is added to that project)
_NEAR_BEFORE = re.compile(r"(?i)\b(?:adjacent\s+to|near|nearby|contiguous\s+(?:to|with)|next\s+to|along\s+(?:strike|trend)\s+(?:from|of|with|to)|"
                          r"on\s+(?:the\s+)?(?:same\s+)?trend\s+(?:with|from|as)|(?:the\s+|an?\s+)?(?:\w+\s+)?extensions?\s+(?:of|to)|between|surround\w*|"
                          r"(?:south|north|east|west)\w*\s+(?:of|from)|close\s+to|proximity\s+to|neighbou?ring|bordering|adjoining|"
                          r"expand(?:s|ed|ing)?|increase\s+the\s+Company['\u2019]s|enhance\s+the)\s+(?:the\s+)?(?:[\w'\u2019.&\-]+\s+){0,4}$")


def _props_in(s, issuer_words=()):
    out = []
    for m in _PLIST.finditer(s):
        suf = "Project" if re.search(r"(?i)projects\b", m.group(0)[len(m.group(1)):]) else "Property"
        for part in re.split(r",\s+(?:and\s+)?|\s+and\s+(?:the\s+)?", m.group(1)):
            p = _name(re.sub(r"\s+(?:Lithium|Gold|Uranium|Copper|Silver|Nickel)$", "", part.strip()), suf)
            if p:
                out.append((m.start(1) + m.group(1).find(part), p))
    if out:
        out.sort()
        return out
    for m in _PROP_RX.finditer(s):
        if m.group(0).endswith("Mines") and (not re.search(r"(?i)\bthe\s+$", s[max(0, m.start() - 5):m.start()]) or
                                             re.match(r",?\s*(?:Ltd|Limited|Inc|Corp|Corporation|Co|Company|Exploration)\b", s[m.end():m.end() + 14])):
            continue                # OPT_V1f: "the Prospector & Freedom Uranium Mines"; "Denison Mines" is a company
        if re.match(r"\s*,?\s*(?:Canada\s+|USA\s+|U\.S\.\s+)?(?:Inc|Ltd|Limited|Corp|Corporation|LLC|S\.A|Pty)\b", s[m.end():m.end() + 20]):
            continue                # 1.0.7: "Freeport-McMoRan Mineral Properties Canada Inc." is a company
        raw, suf = m.group(1), m.group(0)[(m.end("lcm") if m.group("lcm") else m.end(1)) - m.start():]
        if " & " in raw:            # OPT_V1f: "&" joins two names ("Prospector & Freedom", "Coyote Basin & Red Wash"),
            l, r = raw.rsplit(" & ", 1)                          # never two metals ("SIGNIFICANT GOLD & SILVER PROPERTY")
            pw = re.search(r"(?:^|\s)([A-Z][\w'\-]*)\s+$", s[max(0, m.start() - 30):m.start()])
            if len(l.split()) == 1 and pw and pw.group(1) not in _BAD_P and pw.group(1).title() not in _BAD_P and \
                    pw.group(1) not in _PVERB and pw.group(1).title() not in _PVERB:
                l = pw.group(1) + " " + l                        # "the True Grit & Middle Ridge North Properties"
                raw = l + " & " + r
            if T._fold(l.split()[-1]).lower() in _COMMOD or T._fold(r.split()[0]).lower() in _COMMOD:
                raw = r
            elif not _name(raw, suf):
                both = [x for x in (_name(l, suf), _name(r, suf)) if x]
                if both:
                    out.append((m.start(), " / ".join(both)))
                continue
        p = _name(raw, suf)
        if not p:
            continue
        pos = s.find(p.split()[0], m.start())
        if pos < 0 or pos > m.end():
            # 1.0.9: an upper-case headline ("CONTIGUOUS TO NEW FOUND GOLD'S QUEENSWAY GOLD PROJECT") names it in capitals;
            # the words before the name itself are what tell a neighbour's project
            wm = re.search(r"(?i)(?<![\w])" + _flexrx(p.split()[0]), s[m.start():m.end()])
            pos = m.start() + wm.start() if wm else -1
        pos = m.start() if pos < 0 or pos > m.end() else pos     # OPT_V1d: "Claims Near Flagship Sheraton Property"
        p = _geo_ext(p, s, pos)             # 1.0.5: "Case Lake West", "Voisey's Bay South", "Monster Lake East"
        if _NEAR_BEFORE.search(s[max(0, pos - 70):pos]):
            continue
        if re.match(r"\s*,?\s*\(?\s*(?:(?:which\s+is\s+|now\s+)?(?:referred\s+to|known)\s+as|called|named)\s+(?:the\s+)?[\u201c\"]?[A-Z]", s[m.end():m.end() + 40]):
            continue                # 1.0.9: "a former Noranda Exploration project referred to as the Lucifer Property": the name follows
        if re.search(r"(?:\)|\b(?!Company|Corporation|Issuer)[A-Z][\w.&]*)(?:['\u2019]s|s['\u2019])\s+(?:\w+\s+){0,1}$", s[max(0, pos - 40):pos]) and \
                not (issuer_words and set(T._fold(re.search(r"(\S+?)(?:['\u2019]s|['\u2019])\s+(?:\w+\s+){0,1}$", s[max(0, pos - 40):pos]).group(1)).lower()
                                       .strip(").").split()) & {w.lower() for w in issuer_words}) and \
                not re.search(r"(?i)\b(?:acquir\w*|option\w*|purchas\w*|earn\w*|interest\s+in|from|sell\w*|sale)\b", s[max(0, pos - 90):pos]):
            continue                # OPT_V1d: "American Eagle Gold Corp.'s (TSXV: AE)'s NAK property" is someone else's
        if issuer_words and set(PN.key(p).split()) <= {T._fold(w) for w in issuer_words}:
            continue
        out.append((m.start(), p))
    for m in _QUOTED.finditer(s):
        q = m.group(1).strip()
        after = s[m.end():m.end() + 30]
        if re.match(r"\s*(?:project|property|claims?)\b", after, re.I) or re.search(r"(?i)\b(?:project|property|claims)$", q):
            sm = re.match(r"(?i)\s*(project|property|claims?)\b", after) or re.search(r"(?i)\b(project|property|claims)$", q)
            p = _name(re.sub(r"(?i)\s+(?:project|property|claims)$", "", q), sm.group(1) if sm else None)
            if p and PN.key(p) not in ("company", "agreement", "option"):
                out.append((m.start(), p))
        elif re.match(r"(?i)\s*(?:exploration\s+|research\s+|mining\s+)?(?:permits?|licen[cs]es?|concessions?|tenements?)\b", after):
            p = _name(q, "Property")     # 1.0.8: the PR 840 "Sienso" permit, the "Kappa" licence
            if p and PN.key(p) not in ("company", "agreement", "option"):
                out.append((m.start(), p))
    if not out:
        # 1.0.9: ground given a name with no Property word: "94 mineral claims called the RAM Nord, which is contiguous to"
        for m in re.finditer(r"(?i)\b(?:claims?|licen[cs]es|tenements|concessions|ground|land\s+package|block)\s+(?:\(\w+\)\s+)?"
                             r"(?:called|named|known\s+as|referred\s+to\s+as)\s+(?:the\s+)?[\u201c\"]?((?-i:[A-Z])[\w'\u2019\-]*(?:\s+(?-i:[A-Z])[\w'\u2019\-]*){0,3})", s):
            p = _name(m.group(1), "Property")
            if p and PN.key(p) not in ("company", "agreement", "option"):
                out.append((m.start(1), p))
    out.sort()
    return out


def _org_clean(o):
    o = re.sub(r"\s+", " ", o).strip(" ,.;:")
    o = re.sub(r"^(?:and|with|from|to|by|of|the|The)\s+", "", o)
    o = re.sub(r"^(?:[A-Z][a-z]+\s+){0,2}?(?:Subsidiary|Subsidiaries|Owned)\s+", "", o)
    return o


_ORG_X = re.compile(r"(?<![\w$.,])(\d{3,4}\s+(?:[A-Z][\w&'\u2019\-.]*\s+){0,2}?" + _ORG_TAIL + r"\.?)(?=[\s,(]|$)|"
                    r"\b((?:[A-Z][\w&'\u2019\-.]*)(?:\s+" + _ORGW + r"){0,4}?,\s+(?:LLC|L\.L\.C|Inc|Ltd|S\.A|Limited)\b\.?)")


def _orgs_in(s, self_rx):
    out = []
    ms = list(_ORG.finditer(s))
    # FIX5 CP: names led by a number ("1234 Resources") or written "X, LLC" ("Beta Nevada II, LLC")
    ms = sorted(ms + [x for x in _ORG_X.finditer(s) if not any(y.start() <= x.start() < y.end() for y in ms)], key=lambda x: x.start())
    for m in ms:
        o = _org_clean(m.group(1) or m.group(2))
        if not o or _ORG_BAD.match(o) or self_rx.search(o):
            continue
        if len(o.split()) == 1 or re.fullmatch(_ORG_TAIL + r"\.?", o.split(None, 1)[0]) and not (
                re.fullmatch(r"Gold|Silver|Copper|Nickel|Lithium|Uranium|Graphite|Energy|Mining|Minerals|Metals|Resources|Exploration",
                                             o.split()[0]) and
                len(o.split()) >= 3 and re.match(r"[A-Z]", o.split()[1]) and not re.fullmatch(_ORG_TAIL + r"\.?", o.split()[1])):
            continue
        if re.search(r"(?i)\b(?:TSX|Exchange|Securities|Instrument|Smelter|Returns|Royalty|Mining\s+Division|Mining\s+District|Gold\s+Belt|"
                     r"Gold\s+District|Gold\s+Project|Gold\s+Property|Trend|Camp|Greenstone|Basin|Region|Province|Township)\b", o):
            continue
        out.append((m.start(), o))
    return out


# ------------------------------------------------------------------ numbers
_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_MULT = {"million": 1e6, "m": 1e6, "mm": 1e6, "k": 1e3, "thousand": 1e3, "billion": 1e9}


def _amt(num, mult):
    v = float(num.replace(",", ""))
    return v * _MULT.get((mult or "").lower().strip(), 1)


_CUR_RX = r"(?:(C|CA|CDN|US|A|AU|AUD|CAD|USD)\s?)?\$\s?"
_PCT_INT = re.compile(r"(?i)(?:\b(?:up\s+to|an?|initial|additional|undivided|further|remaining|full|aggregate|total)\s+){0,3}"
                      r"(\d{1,3}(?:\.\d+)?)\s*(?:%|-?\s?per[\s-]?cent)\s*(?:\(\s*\d+\s*%\s*\)\s*)?(?:undivided\s+)?(?:legal\s+and\s+beneficial\s+)?"
                      r"(?:right,?\s+title\s+(?:and|&)\s+)?(?:beneficial\s+)?(?:ownership\s+)?(?:interest|ownership)\b")
_CASH = re.compile(r"(?i)(?:cash\s+payments?|cash\s+consideration|cash\s+paym\w+\s+totall?ing|pay(?:ing|ment\s+of)?\s+(?:a\s+total\s+of|an?\s+"
                   r"aggregate\s+(?:of\s+)?)|paying\s+the\s+optionor\s+a\s+total\s+cash\s+consideration\s+of|aggregate\s+cash\s+payments\s+of|"
                   r"cash\s+payments\s+totall?ing|for\s+a\s+cash\s+payment\s+totall?ing)\s*(?:of\s+|totall?ing\s+|in\s+the\s+amount\s+of\s+)?"
                   + _CUR_RX + _NUM + r"\s*(million|M|k)?\b")
_CASH2 = re.compile(r"(?i)" + _CUR_RX + _NUM + r"\s*(million|M|k)?\s+(?:in\s+)?(?:\(?CAD\)?\s+)?(?:cash|in\s+cash|cash\s+payments?)\b")
_WORK = re.compile(r"(?i)(?:" + _CUR_RX + _NUM + r"\s*(million|M|k)?\s+(?:in\s+)?(?:\w+\s+){0,2}?(?:exploration|work)\s+expenditures|"
                   r"(?:exploration|work)\s+expenditures\s+(?:of|totall?ing)\s+(?:at\s+least\s+)?" + _CUR_RX + _NUM + r"\s*(million|M|k)?|"
                   r"incur(?:ring)?\s+(?:an\s+aggregate\s+of\s+|a\s+total\s+of\s+|a\s+minimum\s+of\s+)?" + _CUR_RX + _NUM + r"\s*(million|M|k)?\s+"
                   r"(?:in\s+)?(?:\w+\s+){0,2}?expenditures)")
_NSR = re.compile(r"(?i)(\d(?:\.\d+)?)\s*%\s*(?:\(\s*[\w.]+\s*\)\s*)?(?:net\s+smelter|NSR)|\b(?:NSR|net\s+smelter\s+returns?)\s+"
                  r"(?:royalty\s+)?(?:of\s+)?(\d(?:\.\d+)?)\s*%")
_WORDN = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
          "eighteen": 18, "twenty-four": 24, "thirty": 30, "thirty-six": 36}
_TERMLEN = re.compile(r"(?i)\b(?:over|within)\s+(?:a|an)?\s*(?:period\s+of\s+)?(?:the\s+)?(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|"
                   r"twelve|eighteen|thirty|thirty-six|twenty-four)[\s-]*(?:\(\d+\)\s*)?(year|month)s?\b|\b(\d{1,2}|two|three|four|five|ten)"
                   r"[\s-]+years?\s+to\s+exercise|\bwould\s+have\s+(\w+)\s+years\s+to\s+exercise")
_AREA = re.compile(r"(?i)(?:~\s*)?" + _NUM + r"\s*(?:-\s*)?(hectares?|ha\b|km\s?2|km\u00b2|square\s+kilomet\w+)")
_DATED = re.compile(r"(?i)\bdated\s+(?:as\s+of\s+)?(?:" + T._DATE_RX + r")")
_ON_DATE = re.compile(r"(?i)\bon\s+(?:" + T._DATE_RX + r")\s*,?\s+(?:it\s+)?(?:entered|signed|executed)")


def _curr(tag):
    t = (tag or "").upper()
    if t in ("US", "USD"):
        return "USD"
    if t in ("A", "AU", "AUD"):
        return "AUD"
    return "CAD"


def _num_of(v):
    return float(v.replace(",", ""))


# ------------------------------------------------------------------ analyse
def _self_rx(h, b):
    names = set()
    iss = T._issuer(b)
    if iss:
        names.add(iss)
    for m in _ALIAS.finditer(b[:2500]):
        names.add(m.group(1))
    for m in re.finditer(r"[\u201c\"]\s*([A-Z][^\u201d\"]{1,40}?)\s*[\u201d\"]\s*,\s*(?:the\s+)?[\u201c\"]\s*(?:Company|Corporation)\b", b[:2500]):
        names.add(m.group(1))
    m = re.match(r"\s*((?:[A-Z][\w&'\u2019\-]*\.?\s+){1,4}?)(?:(?:Corp|Inc|Ltd|Limited|Corporation)\.?,?\s+)?(?:Announces|Enters|Signs|"
                 r"Executes|Options|Acquires|Completes|Closes|Stakes|Expands|Increases|Grants|Terminates|Amends|Exercises|Receives|"
                 r"Makes|Earns|Issues|Agrees|Sells|Finalizes|Secures|More\s+Than|Doubles|Triples|Adds|Consolidates|to\s)", h)
    if m and len(m.group(1).split()) <= 4:
        names.add(m.group(1).strip())      # OPT_V1c: "EEE Exploration Enters Into ..." names the issuer
    for m in re.finditer(r"[\u201c\"]\s*(?:the\s+)?Company\s*,?\s*[\u201d\"]\s*(?:,\s*)?(?:or|and)\s+(?:the\s+)?[\u201c\"]\s*([A-Z][^\u201d\"]{1,40}?)\s*[\u201d\"]", b[:2500]):
        names.add(m.group(1))
    hl_head = {w.lower() for w in re.findall(r"[A-Za-z][\w'\u2019]+", h)[:3]}
    for m in re.finditer(r"\(\s*[\u201c\"]\s*([A-Z][\w&.'\u2019\- ]{1,30}?)\s*[\u201d\"]\s*\)\s*\(\s*(?:TSX|CSE|NYSE|NASDAQ|ASX|OTC|FSE|NEO|Cboe)|"
                         r"\((?:TSX|CSE|NYSE|NASDAQ|ASX|OTC|FSE|NEO|Cboe)[^()]{0,40}\)\s*(?:\([^()]{0,40}\)\s*){0,3}\(\s*[\u201c\"]\s*"
                         r"([A-Z][\w&.'\u2019\- ]{1,30}?)\s*[\u201d\"]\s*\)", b[:800]):
        a = m.group(1) or m.group(2)
        if a.split()[0].lower() in hl_head and not re.match(r"(?i)(?:the\s+)?(?:company|corporation|issuer)$", a):
            names.add(a)       # OPT_V1b: '(\u201cBoreal\u201d) (CSE:BGLD)' names the issuer when the headline starts with it
    for n in list(names):
        fw = n.split()[0] if n.split() else ""
        if len(fw) >= 4 and fw.lower() not in ("gold", "silver", "copper", "lithium", "uranium", "canadian", "american", "north",
                                                "south", "western", "eastern", "northern", "southern", "great", "new", "first",
                                                "global", "golden", "royal", "united", "international", "pacific", "atlantic"):
            names.add(fw)
    words = set()
    for n in names:
        n = re.sub(r"\s+(?:Corp(?:oration)?|Inc|Ltd|Limited|Resources|Metals|Mining|Minerals|Gold|Uranium|Energy|Exploration|Ventures|"
                   r"Lithium)\.?$", "", n).strip()
        if n and len(n) > 2 and n.lower() not in ("gold", "resources", "metals", "mining", "minerals", "energy", "lithium",
                                                  "uranium", "silver", "copper", "exploration", "ventures", "capital", "the company"):
            words.add(n)
    alt = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    tk = re.search(r"\(\s*(?:TSX[-.\s]?V|TSXV|TSX|CSE|NEO|Cboe|ASX|NYSE|NASDAQ)\s*[:\-]\s*([A-Z]{3,5})\b", b[:1500])
    if tk and tk.group(1) not in ("GOLD", "CORP", "THE", "AND", "NEW", "ALL", "ONE", "USA"):
        alt = (alt + "|" if alt else "") + "(?-i:" + tk.group(1) + ")"     # OPT_V1d: "MCC has been granted" (TSXV: MCC) is the issuer
    rx = re.compile(r"(?i)\b(?:the\s+Company|Company['\u2019]s|the\s+Corporation|we|our|us" + ("|" + alt if alt else "") + r")\b")
    iw = set()
    for w in words:
        iw |= set(T._fold(w).split())
    return rx, iw


# 1.0.9: "to" after a relation ("Options Additional Property Adjacent to Golden Culvert") names a neighbour, not the
# company the option is granted to
_REL_TO = r"(?<![Aa]djacent\s)(?<!ADJACENT\s)(?<![Cc]ontiguous\s)(?<!CONTIGUOUS\s)(?<![Nn]ext\s)(?<!NEXT\s)(?<![Cc]lose\s)(?<!CLOSE\s)(?<![Pp]roximity\s)"
_OUT_HL = re.compile(r"\b(?:[Oo]ptions?|OPTIONS?)\s+(?:[Ii]ts\s+|[Tt]he\s+|THE\s+|ITS\s+|an?\s+|\d{1,3}\s*%\s+(?:[Ii]nterest\s+)?(?:[Ii]n\s+)?)?(?![Tt][Oo]\s)"
                     r"[^.]{0,80}?(?<![Aa]djacent\s)(?<!ADJACENT\s)(?<![Cc]ontiguous\s)(?<!CONTIGUOUS\s)(?<![Nn]ext\s)(?<!NEXT\s)(?<![Cc]lose\s)(?<!CLOSE\s)(?<![Pp]roximity\s)\b(?:to|TO)\s+(?!acquire|earn|purchase|expedite|focus|Acquire|Earn|Purchase|Expedite|Focus|ACQUIRE|EARN)[A-Z]|"
                     r"\b[Tt]o\s+[Oo]ption\s+[^.]{0,80}\bto\s+[A-Z]|\bRECEIVES\b[^.]{0,40}\bOPTION\s+PAYMENT\s+FROM\b|(?i:\bpartner\b)|"
                     r"\bExercises\s+Initial\b[^.]{0,40}['\u2019]s\b|(?i:\bcontinu(?:es|ing)\s+(?:to\s+|its\s+)?earn[\s-]?in)|(?i:\breceives?\b(?:(?!\b(?:makes?|pays?|issues?|and)\b)[^.]){0,60}\b(?:payments?|consideration|shares)\b[^.]{0,60}"
                     r"\b(?:option|earn[\s-]?in)|\bgrants?\s+(?:an?\s+)?option\b)")


# 1.0.9: the other side holds the option on the issuer's ground: "the Company has granted the Optionor the option to
# acquire an 80% interest in its X project", "Minsur ... its option to acquire the Company's 55%-owned Lara Project",
# "received notice from KG Exploration ... that it intends to terminate the option", "to option the X Project to a
# private British Columbia company"
_OUT_BODY = re.compile(r"(?i)\b(?:the\s+Company|we)\s+(?:has\s+|have\s+|will\s+)?grant(?:ed|s)?\s+(?:to\s+)?(?:the\s+|an?\s+)?[^.]{0,60}?\b(?:option|right)\s+"
                       r"to\s+(?:acquire|earn|purchase)\b|\boption\s+to\s+(?:acquire|earn|purchase)\s+(?:all\s+of\s+|up\s+to\s+)?(?:an?\s+|the\s+)?"
                       r"(?:[\d.]+\s*%\s+(?:\w+\s+){0,2}interest\s+in\s+)?the\s+Company['\u2019]s\b|"
                       r"\b(?:received\s+(?:\w+\s+){0,2}notice\s+from|(?:been\s+)?notified\s+by)\b" + _NP + r"{0,160}?\b(?:its|their|it)\s+(?:intention\s+to\s+|"
                       r"intends\s+to\s+|has\s+(?:decided|elected)\s+to\s+|will\s+)?(?:terminat\w*|relinquish\w*|drop\w*|withdraw\w*|exercis\w*)\s+"
                       r"(?:its\s+|the\s+|their\s+)?option\b|"
                       r"\b(?:to\s+option|has\s+optioned|optioned)\s+(?:its|the)\s+[^.]{0,80}?\bto\s+(?:an?|one)\s+(?:private|arm['\u2019]s[\s-]+length|"
                       r"third[\s-]+party|(?:[A-Z][\w.\-]*\s+){1,3}(?:company|corporation))\b")


def _direction(s, is_hl, self_rx, hl):
    """option_in unless the text says the other side earns the interest."""
    if is_hl:
        if _OUT_HL.search(s) and not re.search(r"(?i)\bacquires?\s+option\s+to\b", s):
            return "option_out"
        return None
    other = r"(?!(?:the\s+)?Company\b)(?!we\b)[A-Z][\w&.'\u2019\-]*(?:\s+[A-Z][\w&.'\u2019\-]*){0,4}"
    if re.search(r"(?i)\b(?:grant(?:ed|ing|s)?|providing)\s+(?:to\s+)?(?:the\s+)?option\s+to\s+acquire\s+[^.]{0,60}\b(?:the\s+)?Company['\u2019]s\b", s) or \
            any(not self_rx.search(x.group(1)) and not re.match(r"(?i)(?:Upon|Pursuant|Under|Following|If|Once|After|Subject)\b", x.group(1))
                and not (re.search(r"(?:\band|&)\s+$", s[:x.start(1)]) and self_rx.search(s[max(0, x.start(1) - 50):x.start(1)]))  # "ABC and X can earn"
                for x in re.finditer(r"\b(" + other + r")\s+(?:\([^)]{0,60}\)\s+)?(?:will\s+obtain|has\s+the\s+right\s+to\s+acquire|"
                                     r"may\s+earn|can\s+earn|has\s+exercised|may\s+exercise|will\s+conduct|may\s+acquire|can\s+acquire|"
                                     r"has\s+(?:fulfilled|satisfied|met)\s+(?:the|its|all)\b|"     # 1.0.9: the partner meets its terms
                                     r"(?:has\s+been|was|is|will\s+be)\s+granted\s+(?:the|an)\s+(?:sole\s+)?(?:exclusive\s+)?(?:right|option)|acquired\s+(?:the|an)\s+(?:exclusive\s+)?"
                                     r"(?:right\s+and\s+option|option|right)\s+(?:\([^)]{0,40}\)\s+)?to\s+(?:purchase|acquire|earn)|"
                                     r"will\s+have\s+(?:the|an)\s+(?:exclusive\s+)?(?:right|option)\s+(?:and\s+(?:first\s+)?option\s+)?"
                                     r"(?:\([^)]{0,40}\)\s+)?to\s+(?:acquire|earn))\b", s)) or \
            any(not self_rx.search(x.group(1)) and not re.match(r"(?i)(?:the|an?|its)\b", x.group(1))
                for x in re.finditer(r"(?i:\b(?:has\s+|will\s+)?(?:grant(?:ed|s|ing)?|giv(?:ing|es|en))\s+(?:to\s+)?)(" + other + r")\s+(?:\([^)]{0,60}\)\s+)?"
                                     r"(?i:(?:the|an?)\s+(?:[\w-]+\s+){0,2}?(?:exclusive\s+)?(?:(?:right\s+and\s+)?option|right\s+to\s+"
                                     r"(?:acquire|earn|purchase)))", s)) or \
            any(self_rx.search(x.group(1)) for x in re.finditer(r"(?i)\bto\s+acquire\s+from\s+([^.,]{2,40})", s)) or \
            re.search(r"(?i)\b(?:earn-in|option)\s+partner\b|\breceived\s+(?:the\s+)?[^.]{0,40}payment\s+from\b", s) or \
            _OUT_BODY.search(s) and not re.search(r"(?i)\bbuy[\s-]?back\b|\bright\s+of\s+first\s+refusal\b|\broyalt", s) or \
            any(self_rx.search(x.group(1)) for x in re.finditer(r"(?i)\b(?:option|earn[\s-]?in)\b[^.]{0,60}?\b(?:to|in|on|over|into)\s+"
                                                                r"([\w&.'\-]+(?:\s+[\w&.'\-]+){0,2})['\u2019]s\s+(?!SEDAR|EDGAR|[Ww]ebsite)[A-Z]"
                                                                r"(?=[\w\s\-\u2013'\u2019]{0,40}\b(?:[Pp]ropert|[Pp]roject|[Cc]laims|[Dd]eposit|[Mm]ine|"
                                                                r"[Tt]enement|[Ll]icen))", s)) or \
            any(self_rx.search(x.group(1)) for x in re.finditer(r"([A-Z][\w&.'\u2019\-]*(?:\s+[A-Z][\w&.'\u2019\-]*){0,3})\s*\([^)]{0,80}?\b(?:the\s+)?[\u201c\"]\s*"
                                                                r"(?:Vendor|Optionor)\s*[\u201d\"]\s*\)", s)) or \
            re.search(r"\b(?:[Tt]o\s+option|[Oo]ptioned|[Oo]ptions)\s+(?:a\s+portion\s+of\s+)?(?:(?:its|the|an?)\s+)?[^.]{0,120}?_REL_\bto\s+"
                      r"(?!acquire|earn|purchase)[A-Z][\w]".replace("_REL_", _REL_TO), s):
        return "option_out"
    return None


_ANNOUNCE = re.compile(r"(?i)\b(?:is|are)\s+(?:pleased|excited|proud|delighted)\s+to\s+(?:announce|report|provide)?|"
                       r"\bannounces?\s+that\s+it\b|\bit\s+has\s+(?:now\s+)?(?:signed|entered|acquired|staked|executed|"
                       r"completed|closed|exercised|terminated|amended)\b")
_PASSIVE_STAKE = re.compile(r"(?i)\b(?:were|was|been)\s+(?:recently\s+|newly\s+)?staked\b(?![^.]{0,40}\b(?:19\d\d|200\d|201\d)\b)|"
                            r"\b(?:acquired\s+)?(?:via|by|through)\s+(?:map\s+|claim\s+|physical\s+|online\s+)?staking\b")


def _ctx_ok(s, self_rx, first_body):
    if self_rx.search(s) or _ANNOUNCE.search(s):
        return True
    return bool(re.match(r"(?i)\s*(?:pursuant\s+to|under\s+(?:the\s+)?(?:terms|agreement|option)|the\s+(?:option|agreement|transaction|"
                         r"acquisition|amendment|property|vendors?|optionors?)|in\s+(?:consideration|order)|upon|to\s+(?:exercise|earn|acquire|"
                         r"maintain)|as\s+consideration|subject\s+to|[A-Z][\w\-]+\s+(?:has|have)\s+exercised)", s)) or first_body


# 1.0.7: a headline with several pieces of news. It is cut into clauses; a property named only in a clause with news
# of another kind (a resource estimate, drill results, a project update, a program, a financing ...) is that news's
# project, not the deal's ("Files Resource Estimate for X Project, Completes Acquisition of Claims").
_HL_CLAUSE = re.compile(r"\s*(?:[,;:|]|\s[-\u2013\u2014]\s|\s+(?i:and|&|plus)\s+(?=(?i:announces?|completes?|closes?|provides?|grants?|files?|plans?|"
                        r"receives?|reports?|commences?|acquires?|acquisition|purchases?|sale|stakes?|staking|expands?|signs?|enters?|"
                        r"optimi[sz]es?|updates?|begins?|starts?|appoints?|intersects?|identifies?|drills?|confirms?|extends?|"
                        r"increases?|adds?|secures?|sells?|options?|executes?|amends?|terminates?|exercises?|mobilizes?|launches?|"
                        r"initiates?|further|details?|highlights?|issues?|arranges?|agm|annual|private|non-brokered|closing)\b))\s*")
_OTHER_NEWS = re.compile(
    r"(?i)\b(?:results?|assays?|intercepts?|intersects?|drill\w*|resources?|reserves?|estimate|ni\s*43-101|pea|pfs|feasibility|study|"
    r"update[sd]?|program(?:me)?s?|survey\w*|sampl\w+|mapping|mineraliz\w+|mineralis\w+|zones?|grades?|g/t|gpt|production|"
    r"financ\w+|placements?|offering|warrants|debt|q[1-4]|quarter\w*|optimi[sz]\w*|provides|reports|files|identifies|discovers|"
    r"commences|begins|starts|appoints|agm|meeting|highlights)\b")


def _other_news_spans(h):
    """1.0.7: the headline's clauses that report news of another kind and no deal: [(start, end)]."""
    spans, pos = [], 0
    for c in _HL_CLAUSE.split(h):
        st = h.find(c, pos) if c else -1
        if st < 0:
            continue
        pos = st + len(c)
        ce = _HL_BACKGROUND.sub(" ", _NONLAND.sub(" ", _STOCK_OPT.sub(" ", c)))
        if _OTHER_NEWS.search(c) and not _HL_DEAL.search(ce):
            spans.append((st, st + len(c)))
    return spans if len(spans) < len([c for c in _HL_CLAUSE.split(h) if c and c.strip()]) else []


def _flexrx(s):
    return r"[\W_]*".join(re.escape(c) for c in s if c.isalnum())


def _drop_head_copy(h, b):
    """1.0.7: the body without the copy of the headline most bodies open with (each clause of the headline, blanked
    where it first occurs in the lead; positions are kept). Letters and digits are compared, case and punctuation
    ignored."""
    keys = [k for k in ("".join(x for x in (c or "").lower() if x.isalnum()) for c in _HL_CLAUSE.split(h)) if len(k) >= 20]
    if not keys:
        return b
    idx = [i for i, x in enumerate(b[:3000]) if x.isalnum()]
    a = "".join(b[i] for i in idx).lower()
    if len(a) != len(idx):          # a letter whose lower case is longer: compare nothing rather than misplace
        return b
    out = list(b)
    for k in keys:
        j = a.find(k)
        if j < 0:
            continue
        for q in range(idx[j], idx[j + len(k) - 1] + 1):
            out[q] = " "
        a = a[:j] + "#" * len(k) + a[j + len(k):]
    return "".join(out)


def _at(s, p, q):
    """Where the name p (found by a capture starting at q) itself starts in s."""
    w = PN.bare(p).split()
    m = re.search(r"(?i)" + _flexrx(w[0]), s[q:]) if w else None
    return q + m.start() if m else q


def _named_in_body(p, b_nh):
    """1.0.7: a property name taken from the headline is one the body itself writes (capitalised, outside the copy of
    the headline). "Third Hard-Rock", "Identified High Sulphidation-Porphyry Prospects", "Dolomite Deposit" are
    headline words the body writes, if at all, in lower case: they describe ground, they do not name it."""
    ws = [w for w in re.findall(r"[\w'\u2019\-]+", PN.bare(p)) if PN.key(w) and T._fold(w).lower() not in _COMMOD and
          not all(x.lower() in _COMMOD for x in w.split("-")) and not (w.islower() and len(w) <= 3)]
    for w in ws:
        ms = [m.start() for m in re.finditer(r"(?i)(?<![\w])" + _flexrx(w) + r"(?![a-z])", b_nh)]
        if ms and not any(b_nh[q].isupper() or b_nh[q].isdigit() for q in ms):
            return False            # the body writes it only in lower case: a description
    return True


_CO_FORM = re.compile(r"(?i)\bamalgamat\w+|\bplan\s+of\s+arrangement\b|\bmerger\b|\bbusiness\s+combination\b|\breverse\s+take-?over\b|"
                      r"\b(?:all|100\s*%)\s+of\s+the\s+(?:issued\s+and\s+)?outstanding\s+(?:common\s+)?shares\s+of\b")


def _company_target(h, b):
    """1.0.7: the headline buys a company, not ground: its object ("Acquire Nuevo Silver", "Acquisition of Yellowhead
    Mining") is a company the body names with a legal ending (Inc., Corp., Ltd.), and the lead says the deal is an
    amalgamation, arrangement, merger or a purchase of all the company's shares. Company-level M&A is not a land deal
    even when it brings a property with it, so the release's purchase sentences are not rows (a sale or option it also
    reports still is)."""
    m = re.search(r"(?i)\b(?:acquires?|acquiring|acquisition\s+of|purchase\s+of|to\s+acquire)\s+(?:all\s+of\s+)?(?:the\s+)?"
                  r"((?-i:[A-Z])[\w&'\u2019\-]*(?:\s+(?-i:[A-Z])[\w&'\u2019\-]*){0,3})", h)
    if not m or not _CO_FORM.search(b[:2500]):
        return False
    name = re.sub(r"(?i)\s+(?:and|&)$", "", m.group(1).strip())
    if re.search(r"(?i)\b(?:propert(?:y|ies)|projects?|claims?|mines?|deposit|land\w*|tenements?|licen[cs]es?|concessions?|interest|"
                 r"option|portfolio|assets?)\b", name) or len(name) < 4:
        return False
    nm = r"\s+".join(re.escape(w) for w in name.split())
    return bool(re.search(r"(?i)\b" + nm + r"(?:\s+(?:Mining|Minerals|Metals|Resources|Gold|Silver|Copper|Exploration|Holdings))?,?\s+"
                          r"(?:Inc|Corp|Corporation|Ltd|Limited|LLC|S\.A|Plc)\b", b[:4000]))


# 1.0.8: COMPANY-LEVEL DEALS, read from the release's structure. The headline frames the news as a merger, a business
# combination, an amalgamation, an arrangement or a takeover, or as "creating a ... company / producer": M&A, no land
# deal row (the label guide: buying a company is not a row even when it brings properties with it).
_HL_MA = re.compile(r"(?i)\b(?:business\s+combination|merger|merge\s+with|amalgamat\w+|plan\s+of\s+arrangement|reverse\s+take-?over|"
                    r"take-?over\s+bid|creat(?:es?|ing)\s+(?:an?\s+|the\s+)?(?:[\w\-.$]+\s+){0,5}?(?:company|producer)|"
                    r"combin(?:e|es|ing)\s+to\s+(?:create|form))\b")
# what a deal verb in the lead acts on: the thing bought or sold
_DEAL_VERB = re.compile(r"(?i)\b(?:acqui(?:re[sd]?|ring|sition\s+of)|purchas(?:e[sd]?|ing)(?:\s+of)?|buy(?:s|ing)?|bought|sell(?:s|ing)?|sold|"
                        r"sale\s+of|divest(?:s|ed|ing|ment\s+of|iture\s+of)?|dispos(?:e|es|ed|ing|ition)\s+of)\s+")
_OBJ_FILL = re.compile(r"(?i)(?:of\s+|its\s+|the\s+|their\s+|all\s+|an?\s+|(?:issued\s+and\s+)?outstanding\s+|common\s+|(?:direct|indirect)\s+|"
                       r"(?:wholly|majority)[\s-]owned\s+|remaining\s+|(?:ownership|equity|controlling)\s+|interest\s+in\s+|stake\s+in\s+|"
                       r"shareholding\s+in\s+|(?:shares|securities)\s+(?:of|in)\s+|\d{1,3}(?:\.\d+)?\s*%\s+|(?-i:[A-Z])[\w&.\-]*['\u2019]s\s+)")
_CO_LEGAL = r"(?:Inc|Corp|Corporation|Ltd|Limited|LLC|L\.L\.C|Plc|S\.A|S/A|SA|Ltda|S\.?R\.?L|SpA|SAS|GmbH|Pty|Oy|AB|A\.S|de\s+C\.V)\b"
_CO_OBJ = re.compile(r"(?:(?-i:[A-Z0-9])[\w&.'\u2019\-]*,?\s+|(?:and|&|of|de|e|y|da|do|du|des|del)\s+){1,7}" + _CO_LEGAL +
                     r"|(?i:(?:[\w\-]+\s+){0,2}subsidiar(?:y|ies)\b)")
_LAND_OBJ = re.compile(r"(?i)\b(?:propert(?:y|ies)|projects?|claims?|mines?|deposits?|concessions?|licen[cs]es?|tenements?|permits?|"
                       r"land\s+(?:package|position)|ground|hectares|acres|patents)\b")
_OPERATING = re.compile(r"(?i)\bproducing\s+(?:\w+\s+){0,3}?(?:mine|asset|operation)s?\b|\boperating\s+(?:mine|business|company)\b|"
                        r"\b(?:immediately\s+)?accretive\b|\bEBITDA\b")
_SHARE_EXCH = re.compile(r"(?i)\beach\s+(?:[\w\-]+\s+){0,3}(?:common\s+)?share\b[^.]{0,80}?\b(?:received|receive|will\s+be\s+exchanged|"
                         r"entitled)\b|\bexchange\s+ratio\b|\bshareholders\s+of\s+(?-i:[A-Z])[\w&.\-]*(?:\s+(?-i:[A-Z])[\w&.\-]*){0,3}\s+"
                         r"(?:will\s+)?(?:receive|be\s+entitled)")


def _co_object(lead):
    """1.0.8: the lead's own deal acts on a company, not on ground: "purchase its 100% ownership stake in X S/A, which
    owns the Y mine", "has acquired 100% of X Participacoes Ltda.", "the purchase of X Metals Ltd.", "sale of its 25%
    interest in X Operations Inc.", "to divest X's wholly owned subsidiaries". The first deal verb whose object is a
    company or ground decides; a purchase agreement, price or consideration is not an object."""
    for m in _DEAL_VERB.finditer(lead):
        w = lead[m.end():m.end() + 220]
        if re.match(r"(?i)(?:and\s+sale\s+)?(?:agreement|price|consideration|option|program|plan|transaction|of\s+(?:up\s+to\s+)?[\d,]+\s+"
                    r"(?:common\s+)?(?:shares|units))\b", w):
            continue
        k = 0
        while True:
            f = _OBJ_FILL.match(w, k)
            if not f or f.end() == k:
                break
            k = f.end()
        rest = w[k:]
        c = _CO_OBJ.match(rest)
        land = _LAND_OBJ.search(rest[:(c.end() if c else 60)])
        if c and not land:
            return True
        if land or c:
            return False
    return False


_HL_SUBJ = re.compile(r"\s*((?:[A-Z][\w&'\u2019\-]*\.?\s+){1,4}?)(?:(?:Corp|Inc|Ltd|Limited|Corporation)\.?,?\s+)?(?:Enters|Signs|Executes|"
                      r"Options|Acquires|Completes|Closes|Stakes|Grants|Terminates|Amends|Exercises|Earns|Agrees|Sells)\b")
_CO_W = {"gold", "mines", "mining", "resources", "corp", "inc", "ltd", "limited", "silver", "metals", "minerals", "the", "company",
         "corporation", "exploration", "ventures", "copper", "lithium", "uranium", "energy", "and", "its"}


def _others_release(h, b):
    """1.0.9: a deal between two other companies ("Fortuna Silver Mines Enters into Option Agreement for Taviche Project",
    released by a company that keeps a carried interest: "Gold79 ... announces that Minaurum Gold Inc. ... have entered
    into an option agreement with Fortuna"). The headline's subject is not the issuer and neither is the lead's: no row
    (the label guide: deals between two other companies are not rows)."""
    hm = _HL_SUBJ.match(h)
    if not hm:
        return False
    iss = [T._issuer(b) or ""] + [m.group(1) for m in _ALIAS.finditer(b[:2500])]
    iw = {w.lower() for n in iss for w in re.findall(r"[A-Za-z0-9]{3,}", n)} - _CO_W
    if not iw or {w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", hm.group(1))} & iw:
        return False
    lead = re.search(r"(?i)\b(?:announces?|reports?|pleased\s+to\s+(?:announce|report))\s+that\s+((?-i:[A-Z])" + _NP + r"{0,200}?)\s+(?:has|have)\s+"
                     r"(?:entered|signed|executed|agreed|optioned|completed|closed)\b", b[:2000])
    if not lead or re.search(r"(?i)\b(?:it|the\s+company|we|our)\b", lead.group(1)):
        return False
    return not {w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", lead.group(1))} & iw


def analyse(headline, body):
    h, b, about = _prepare(headline, body)
    h = re.sub(r"(?i)\s*/?\s*\bNOT\s+FOR\s+(?:DISTRIBUTION|DISSEMINATION|RELEASE)\b.*$", "", h)   # OPT_V1e: wire boilerplate
    if _PROMO.search(h) or re.search(r"(?i)\bcongratulates\b", h):
        return {"rows": [], "reason": "promotional"}
    if re.search(r"(?i)\b(?:acqui\w+|purchase|merger|merge|amalgamation|takeover|arrangement)\b", h) and \
            re.search(r"\b[A-Z][\w&'\u2019\-]*(?:\s+[A-Z][\w&'\u2019\-]*){0,3}\s+(?i:resources|corp(?:oration)?\.?|inc\.?|ltd\.?|limited|mining|minerals|"
                      r"metals|exploration|ventures)(?:\s+(?i:corp|inc|ltd)\.?)?\s+(?i:acquisition|merger|amalgamation|transaction)\b|"
                      r"(?i:acqui\w+|purchase|merge\s+with)\s+(?:of\s+)?(?:all\s+(?:of\s+)?the\s+(?:shares|securities)\s+of\s+)?[A-Z][\w&'\u2019\-]*(?:\s+[A-Z][\w&'\u2019\-]*){0,3}\s+"
                      r"(?i:resources|corp(?:oration)?|inc|ltd|limited)\b", h) and \
            not re.search(r"(?i)\b(?:propert(?:y|ies)|projects?|claims?|mines?|deposit|land\w*|hectares|tenements?|licen[cs]es?|concessions?)\b", h):
        return {"rows": [], "reason": "company_acquisition"}     # OPT_V1e: buying a company is M&A, not a land deal
    if _others_release(h, b):
        return {"rows": [], "reason": "others_deal"}
    co_deal = _company_target(h, b)       # 1.0.7: the headline buys a company (amalgamation, arrangement, all its shares)
    lead = h + " " + b[:3000]
    if _NONMINE.search(lead) and not re.search(r"(?i)\b(?:mineral|mining|claims?|drill|ore|deposit)\b", lead):
        return {"rows": [], "reason": "not_mining"}
    if _NONMINE.search(h):
        return {"rows": [], "reason": "not_mining"}
    body_main = b[:about] if about else b
    self_rx, issuer_words = _self_rx(h, b)
    sents = [(h, True)] + [(x, False) for x in _sentences(body_main)]
    b_nh = _drop_head_copy(h, body_main)
    co_deal = co_deal or bool(_CO_INTEREST.search(b_nh[:1500]))
    # 1.0.8: company-level M&A. The headline frames a merger / combination / "creating a ... company"; or the lead's deal
    # acts on a company and the release frames it as a company deal: no land object in the headline, an operating
    # business bought (a producing mine, "immediately accretive"), or the target's shareholders exchanging their shares
    if _HL_MA.search(_HL_BACKGROUND.sub(" ", h)):
        return {"rows": [], "reason": "company_deal"}
    lead_nh = b_nh[:1500]
    if _co_object(lead_nh) and (not re.search(r"(?i)\boption\b|\bearn[\s-]?in\b", _STOCK_OPT.sub(" ", h)) and
                                not _LAND_OBJ.search(_NONLAND.sub(" ", h)) or _OPERATING.search(h + " " + b_nh[:3000]) or
                                _SHARE_EXCH.search(b_nh[:3000])):
        return {"rows": [], "reason": "company_deal"}
    dl = T._dateline(b) or ""
    if not dl:
        # 1.0.9: a dateline no bracket or dash closes ("MONTREAL, July 05, 2022 (GLOBE NEWSWIRE)", "December 20, 2021 NR 06"):
        # the first date at the top gives the release's year, so a deal "In June 2021 (see the press release)" is history
        dm = T._DATE.search(b[:400])
        dl = (T._iso(dm) or "") if dm and not re.search(r"(?i)\b(?:on|by|before|until|dated|since|from|effective)\s+$",
                                                        b[max(0, dm.start() - 12):dm.start()]) else ""
    dl_year = int(dl[:4]) if dl else None
    other_sp = _other_news_spans(h)
    # 1.0.7: the projects of the headline's other news (a resource estimate, an update ...) are not the deal's ground in
    # the body either, unless the deal adds ground to a project
    other_names = [p for a, z in other_sp for _q, p in _props_in(h[a:z], issuer_words)] if not any(
        re.search(r"(?i)\b(?:expan\w*|increas\w*|doubl\w*|tripl\w*|enlarg\w*|consolidat\w*|grows|adds|addition\w*)\b", c) and
        not re.search(r"\b[A-Z][\w'\u2019\-]+\s+(?i:" + PN.SUFFIX + r")\b", c) for c in _HL_CLAUSE.split(h)
        if c and not any(c in h[a:z] for a, z in other_sp)) else []
    # 1.0.7: the headline's property is the deal's: not one named only in another piece of news, and one the body names
    hl_props = [(q, p) for q, p in _props_in(h, issuer_words) if not any(a <= _at(h, p, q) < z for a, z in other_sp)
                and (len(b_nh) < 600 or _named_in_body(p, b_nh))]
    # 1.0.7: "Acquires Two New Toodoggone Projects": a count before a plural is a description of several properties;
    # their names are in the body
    hl_props = [(q, p) for q, p in hl_props if not re.search(
        r"(?i)\b(?:two|three|four|five|six|several|multiple|\d+)\s+(?:\w+\s+){0,2}$", h[max(0, _at(h, p, q) - 40):_at(h, p, q)])
        or not re.search(r"(?i)(?:projects|properties)$", p)]
    if not hl_props:
        # 1.0.7: "Renegotiates Rubi-Esperanza Cash and Option Agreement", "Extends Radio Option Agreement": the name
        # before the agreement, unless the body writes it as a company's name (the optionor's)
        am = re.search(r"(?i)\b(?:amends|amended|extends|extended|renegotiates|terminates|exercises|executes|signs|completes|closes|"
                       r"enters\s+into|update\s+on|to|on|of|its|the|for)\s+((?-i:[A-Z])[\w'\u2019\-]+(?:\s+(?:de|del|la|los|las|"
                       r"(?-i:[A-Z])[\w'\u2019\-]+)){0,3})\s+(?:(?:Cash|Property)\s+(?:and|&)\s+)?(?:Option|Earn-?In|Purchase)\s+Agreement\b", h)
        if am and re.fullmatch(r"(?i)(?:share|shares|stock|asset|assets|equity|securities|unit|units|definitive|binding|formal|"
                               r"amended|amending|revised|new|final)", am.group(1)):
            am = None               # 1.0.9: "Share Purchase Agreement", "Asset Purchase Agreement" name the paper, not the ground
        if am and not re.search(re.escape(am.group(1)) + r"\s+(?:[A-Z][\w&.'\u2019\-]*\s+){0,3}(?:Inc|Corp|Corporation|Ltd|Limited|LLC|Capital|"
                                r"Resources|Mining|Minerals|Metals|Ventures)\b", b[:6000]):
            p = _name(am.group(1), "Property")
            if p and (len(b_nh) < 600 or _named_in_body(p, b_nh)):
                hl_props = [(am.start(1), p)]
    if not hl_props:
        # 1.0.7: a name with no Property / Project word after it: "Sale of its 20% Interest in Hod Maden"
        im = re.search(r"(?i)\b(?:sale|sells?|acqui\w+|purchas\w+|divest\w*|disposition)\b[^.]{0,40}?\b(?:interests?\s+in|(?<=%\s)(?:share|stake)\s+"
                       r"(?:of|in))\s+(?:the\s+)?((?-i:[A-Z])[\w'\u2019\-]+(?:\s+(?-i:[A-Z])[\w'\u2019\-]+){0,2}?)(?:\s*$|(?=\s+(?:to|from|for|with)\s))", h)
        # 1.0.8: "... Sells its 50% share of Galore Creek to Newmont": the name ends before the buyer
        if im and not re.search(r"(?i)\b(?:inc|corp|corporation|ltd|limited|llc|resources|mining|minerals|metals|mines|holdings|"
                                r"ventures|exploration|gold|silver|copper)\.?$", im.group(1)):
            p = _name(im.group(1), "Project")
            if p:
                hl_props = [(im.start(1), p)]
    if not hl_props:
        # 1.0.9: ground bought or staked at a named place: "Acquires 3 Additional Claims at San Javier"
        cm = re.search(r"(?i)\b(?:\d+|additional|new|more|further|strategic|key|mineral|mining|two|three|four|five|six|several)\s+"
                       r"(?:(?:mineral|mining|exploration|new|additional)\s+)?(?:claims?|concessions?|licen[cs]es|tenements|ground|land)\s+(?:at|on)\s+(?:the\s+|its\s+)?"
                       r"((?-i:[A-Z])[\w'\u2019\-]+(?:\s+(?-i:[A-Z])[\w'\u2019\-]+){0,2}?)\s*(?:$|[,;:|]|(?=\s+(?:in|near|for|and)\s))", h)
        if cm and _HL_DEAL.search(h[:cm.start()]) and not re.match(r"\s*,\s*[A-Z][^,;]{0,40}?(?:,|\band\b|&)", h[cm.end(1):]):
            p = _name(cm.group(1), "Property")
            if p and (len(b_nh) < 600 or _named_in_body(p, b_nh)):
                hl_props = [(cm.start(1), p)]

    th = _THIRD.search(h)
    h_eff = re.sub(r"(?i)\b(?:recently|newly|previously)\s+acquired\b|\bOption\s+(?=(?:Property|Project|Claims|Drill|Program)\b)", " ",
                   _STOCK_OPT.sub(" ", h[:th.start()] if th else h))
    h_eff = _HL_BACKGROUND.sub(" ", _NONLAND.sub(" ", h_eff))     # 1.0.7: non-land assets; a partner's work, background
    if not re.search(r"(?i)\b" + _LAND + r"\b|\bland\b|\bground\b|\bhectares\b|\binterest\b|\b(?:belt|rights|salar|district|"
                     r"acreage|leases?|patents?)\b", h_eff):
        h_eff = re.sub(r"(?i)\bacqui\w+|\bpurchas\w+", " ", h_eff)     # OPT_V1c: "Image Acquisition", "Acquires Securities of"
    h_eff = _GENERIC_ACQ.sub(" ", h_eff)       # OPT_V1e: "Acquires Key Subsurface Data", "to Acquire ... Tunnel Boring Machine"
    # 1.0.9: a claim block or land package named as the place of other news ("Commences Drilling ... at B3 Claim Block",
    # "Intersects Sulphides with Drilling at B3 Claim Block") is not a deal
    h_eff = re.sub(r"(?i)\b(?:at|on|across|within|over|from)\s+(?:the\s+|its\s+|our\s+)?(?:[\w\-]+\s+){0,3}?(?:claims?\s+(?:blocks?|packages?)|"
                   r"land\s+(?:package|position))\b", " ", h_eff)
    hl_deal = bool(_HL_DEAL.search(h_eff))
    # 1.0.8: the headline's only deal is in something that is not ground ("Closes Sale of Real Estate Asset", "Acquires 1%
    # NSR"): body sentences of the same kind restate that deal ("has closed the sale of its San Pedrito Property, a
    # non-core asset"); a deal of another kind in the body still counts
    h_x = _GENERIC_ACQ.sub(" ", _HL_BACKGROUND.sub(" ", _STOCK_OPT.sub(" ", h)))
    nl_kinds = set()
    h_rest = _NONLAND.sub(" ", h_x)
    if _HL_DEAL.search(h_x) and not _HL_DEAL.search(h_rest) and not re.search(r"(?i)\binterests?\b", h_rest) and not any(
            not re.search(r"(?i)\b(?:on|at|over|covering|from|of|for)\s+(?:[\w'\u2019.\-]+\s+){0,4}$", h_rest[max(0, x.start() - 60):x.start()])
            for x in _LAND_OBJ.finditer(h_rest)):         # land in the headline other than where the royalty lies
        nl_kinds = {k for k, rx in (("property_sale", r"\b(?:sells?|sold|sale|divest\w*|dispos\w+)\b"), ("purchase", r"\b(?:acqui\w+|purchas\w+|buys?|bought)\b"),
                                    ("option", r"\boption")) if re.search("(?i)" + rx, h_x)}
    if re.fullmatch(r"(?i)\W*(?:(?:news|press)\s+release|news|release|update)?\W*", h or ""):
        hl_deal = bool(_HL_DEAL.search(_STOCK_OPT.sub(" ", b[:150])))      # no real headline: the title opens the body
    mentions = []
    for i, (s, is_hl) in enumerate(sents):
        th = _THIRD.search(s)
        if th and is_hl and th.start() > 20 and _HL_DEAL.search(s[:th.start()]):
            s = s[:th.start()]          # "ACQUIRES FINAL CLAIM BLOCK ... AS THIRD-PARTY STAKING ACTIVITY INTENSIFIES"
        elif th:
            continue
        stock = _STOCK_OPT.search(s)
        s_land = re.sub(r"(?i)\bintellectual\s+property\b", "IP", s)
        s_land = re.sub(r"(?i)(?:or\s+)?(?:the\s+)?[\u201c\"]\s*(?:Optionee|Optionor|Purchaser|Vendor)\s*[\u201d\"]", " ", s_land)   # OPT_V1d: issuer's label
        if is_hl:
            s_land = re.sub(r"(?i)\b(?:recently|newly|previously)\s+acquired\b|\bOption\s+(?=(?:Property|Project|Claims|Drill|Program)\b)",
                            " ", s_land)
            s_land = _HL_BACKGROUND.sub(" ", s_land)     # 1.0.7
        elif not hl_deal:
            s_land = _HL_BACKGROUND.sub(" ", s_land)     # 1.0.7: "... that option partner X has completed its program"
        s_land = _NONLAND.sub(" ", s_land)                # 1.0.7: a royalty, stream, water right, company shares ... is not ground
        if stock:
            # drop the stock-option clause; keep a property-option clause in the same sentence
            s_land = _STOCK_OPT.sub(" ", s_land)
            if not re.search(r"(?i)\boption\w*\b[^.]{0,80}\b" + _LAND, s_land) and not _STAKE.search(s_land) and not _PURCH.search(s_land):
                continue
        if not is_hl:
            if _BACKGROUND.search(s):
                continue
            od = _OTHERS_DEAL.search(s)
            if od and not self_rx.search(od.group(1)) and not re.match(r"(?:the\s+)?(?:Company|Corporation|Issuer|Optionee|Purchaser)\b", od.group(1)):
                continue            # 1.0.9: another company's deal, written in the passive
            hy = _HISTORY.match(s)
            if hy and dl_year and int(hy.group(1)) < dl_year - 1:
                continue
            if _SEE_EARLIER.search(s) and (not hl_deal and not re.search(r"(?i)\b(?:has|have)\s+(?:now\s+)?(?:entered|signed|executed|closed|"
                                                                          r"completed|acquired|staked|exercised|terminated|amended)\b", s)
                                           or dl_year and any(int(y) < dl_year for y in re.findall(r"\b((?:19|20)\d\d)\b", s))
                                           and not re.search(r"(?i)\b(?:have|has)\s+(?:now\s+)?agreed\s+to\s+(?:amend|extend|modify|terminate)", s)):
                continue            # 1.0.7: "In June 2021 (see the press release), Mosaic signed an option agreement ..."
            if not _ctx_ok(s, self_rx, i <= 2) and not _PASSIVE_STAKE.search(s):
                continue
        kind = None
        for om in _THEIR_STAKING.finditer(s_land):
            if not self_rx.search(om.group(1)):     # 1.0.9: another company's staking ("contiguous to QIMC's recent claims staking")
                s_land = s_land[:om.start(2)] + " " * len(om.group(2)) + s_land[om.end(2):]
        if re.search(r"(?i)\b(?:no|without|free\s+of)\b[^.]{0,50}\boption\s+payments?\b", s_land):
            s_land = re.sub(r"(?i)\boption\s+payments?\b", " ", s_land)
        if (_OPT.search(s_land) and re.search(r"(?i)\boption\w*\b" + _NP + r"{0,120}\b" + _LAND + r"|" + _LAND + _NP + r"{0,120}\boption\w*\b|"
                                              # 1.0.8: an exploration permit is ground ("an option to purchase agreement ... over the X permit")
                                              r"\boption\s+to\s+(?:purchase|acquire)\b" + _NP + r"{0,120}\bpermits?\b|"
                                              r"\bearn[- ]?in\b|\boptionor|\bthe\s+option\b|\boption\s+(?:payment|agreement)|\bearns?\s+(?:a\s+)?(?:further|additional|"
                                              r"initial|second|first)\s+", s_land)) \
                or _EARN_PCT.search(s_land):
            kind = "option"
        elif _STAKE.search(s_land):
            kind = "staking"
            if not re.search(r"(?i)\bstak|\bappl(?:y|ies|ied|ications?)\b|\bdesignat|\bfilings?\b|\badded\s+[\d,]+", s_land):
                kind = "expand"     # OPT_V1c: "Increases Land Holdings": staked or bought, the body says which
        elif _SALE.search(s_land) and self_rx.search(s_land) and not re.search(r"(?i)\bsale\s+of\s+(?:the\s+)?(?:securities|shares|units)", s_land):
            kind = "property_sale"
        elif _PURCH.search(s_land) and not re.search(r"(?i)\b(?:proceeds|use\s+of|intends\s+to\s+use|will\s+be\s+used)\b", s_land) \
                and not _GENERIC_ACQ.search(s_land) and not (re.search(
                    r"(?i)\b(?:issued\s+and\s+outstanding|all\s+of\s+the\s+(?:outstanding\s+)?(?:common\s+)?shares|share\s+capital|"
                    r"securities\s+of|business\s+unit)\b", s_land) and not re.search(r"(?i)\b" + _LAND + r"\b", h)):
            kind = "purchase"
        if not kind:
            continue
        if not is_hl and kind in nl_kinds:
            continue                # 1.0.8: the headline's non-land deal restated
        if co_deal and kind == "purchase":
            continue                # 1.0.7: the purchase is the company's; buying a company is M&A
        if not is_hl and kind in ("purchase", "staking") and not self_rx.search(s) and not re.match(r"(?i)\s*(?:the|pursuant|under)", s) \
                and not (kind == "staking" and _PASSIVE_STAKE.search(s)) and not _ANNOUNCE.search(s):
            continue
        if not is_hl and not hl_deal and not (i <= 3 and _NEWS_VERB.search(s)):
            continue                # OPT_V1b: a release whose headline is about something else reports a deal only in its lead
        # 1.0.7: a body sentence's names, not those of the copy of the headline it may open with (checked above)
        props = hl_props if is_hl else _props_in(_drop_head_copy(h, s) if i <= 3 else s, issuer_words)
        if kind not in ("staking", "expand"):          # staked ground is added to the project the other news is about
            props = [(q, p) for q, p in props if not any(PN.same(p, o) for o in other_names)]
        mentions.append({"i": i, "s": s, "hl": is_hl, "kind": kind, "props": [p for _, p in props]})
    if not mentions:
        return {"rows": [], "reason": "no_deal"}

    # group mentions into deals
    deals = []

    def new_deal(m):
        d = {"ms": [m], "props": list(m["props"][:3]), "kind": m["kind"]}
        deals.append(d)
        return d

    hl_m = [m for m in mentions if m["hl"]]
    first = hl_m[0] if hl_m else mentions[0]
    main = new_deal(first)
    if not main["props"] and hl_props:
        main["props"] = [hl_props[0][1]]
    plural = re.search(r"(?i)\b(?:two|three|four|five|\d)\s+(?:\(\d\)\s+)?(?:separate\s+)?(?:definitive\s+)?(?:property\s+)?(?:option|purchase)\s+"
                       r"agreements\b|\bOption\s+Agreements\b", h + " " + b[:1500])
    split_rx = re.compile(r"(?i)\b(?:to\s+exercise\s+its\s+option\s+to\s+acquire|will\s+(?:achieve|acquire)\b[^.]{0,60}\binterest|"
                          r"full\s+earn\s*-?\s*in|option\s+agreement\s+with)")
    by_cp = {}
    # 1.0.7: one row per deal, not one for several: a purchase and new staking announced together ("Acquires & Stakes
    # Properties ...") are two deals, purchase sentences and staking sentences each make their own row
    dual = bool(re.search(r"(?i)\b(?:acqui\w+|purchas\w+|buys?)\b", h_eff) and re.search(r"(?i)\bstak(?:es|ed|ing)\b", h_eff))
    by_kind = {main["kind"]: main} if main["kind"] in ("staking", "purchase") else {}
    for m in mentions:
        if m is first:
            continue
        if dual and not plural and m["kind"] in ("staking", "purchase"):
            tgt = by_kind.get(m["kind"])
            main["dual"] = True
            if tgt is None:
                by_kind[m["kind"]] = new_deal(dict(m, props=m["props"][:4]))
                by_kind[m["kind"]]["dual"] = True
            else:
                tgt["ms"].append(m)
                if not tgt["props"] and m["props"]:
                    tgt["props"] = m["props"][:4]
            continue
        if plural:
            w = re.search(r"(?i)\bterms\s+of\s+the\s+option\s+agreement\s+with\s+([A-Z0-9][\w\-]+)", m["s"])
            if w and not m["props"]:
                key = w.group(1)
                if key in by_cp:
                    by_cp[key]["ms"].append(m)
                else:
                    by_cp[key] = new_deal(dict(m, props=[]))
                    by_cp[key]["cp_short"] = key
                continue
            if split_rx.search(m["s"]) and len(m["props"]) >= 1:
                p0 = m["props"][0]
                tgt = next((d for d in deals if d is not main and any(PN.same(p0, q) for q in d["props"])), None)
                if tgt is not None:
                    tgt["ms"].append(m)
                else:
                    new_deal(dict(m, props=[p0]))
                continue
        if not main["props"] and m["props"] and not plural:
            main["props"] = m["props"][:4]
            main["ms"].append(m)
            continue
        own = [p for p in m["props"] if not any(PN.same(p, q) for d in deals for q in d["props"])]
        target = None
        for d in deals:
            if any(PN.same(p, q) for p in m["props"] for q in d["props"]):
                target = d
                break
        agreement_verb = re.search(r"(?i)\b(?:terminat\w*|not\s+to\s+proceed|relinquish\w*\s+(?:its|the|their|all)\s+(?:\w+\s+)?options?|"     # 1.0.9
                                   r"has\s+staked|staked|update\s+on\s+the|"
                                   r"continued\s+to\s+pursue)\b", m["s"]) or plural and re.search(
            r"(?i)\b(?:to\s+exercise\s+its\s+option\s+to\s+acquire|will\s+(?:achieve|acquire)\b[^.]{0,60}\binterest|full\s+earn[\s-]?in|"
            r"option\s+agreement\s+with|under\s+the\s+(?:revised\s+)?terms)", m["s"])
        if target is None and own and agreement_verb and not re.search(r"(?i)\b(?:each|collectively|together)\b", m["s"]) \
                and (len(own) == 1 or _DROP_OPT.search(m["s"])):
            # 1.0.9: "has relinquished its options to acquire the Victoria and Tres Salares cobalt properties": one row each
            if _DROP_OPT.search(m["s"]):
                own = [x for p in own for x in (
                    [q + " Property" for q in re.split(r"\s+(?:and|&)\s+", re.sub(r"\s+(?:Properties|Projects)$", "", p))]
                    if re.search(r"\s(?:and|&)\s.*\s(?:Properties|Projects)$", p) else [p])]
            if _DROP_OPT.search(m["s"]) and len(own) > 1:
                for p in own:
                    mm = dict(m, props=[p])
                    nd = new_deal(mm)
                    nd["term"] = True
                    nd["dropped"] = bool(_RELINQ.search(m["s"]))
                continue
            new_deal(m)
        elif target is not None:
            target["ms"].append(m)
        elif not m["props"] and _TERM.search(m["s"]) and any(d.get("term") for d in deals):
            for d in deals:         # 1.0.9: "By relinquishing the options to such properties ..." belongs to the dropped options
                if d.get("term"):
                    d["ms"].append(m)
        else:
            main["ms"].append(m)
            if not main["props"] and m["props"]:
                main["props"] = m["props"][:3]

    hl_props_names = [p for _q, p in hl_props]
    eff_staking = main["kind"] in ("staking", "expand") or main["kind"] == "purchase" and bool(_STAKED_BODY.search(body_main[:5000]))
    if len(deals) == 1 and main["kind"] in ("option", "purchase") and not eff_staking and not plural and not dual:
        # FIX5 R2: new ground the company stakes itself beside the option or purchase it reports ("The Company also staked
        # 87 claim units ... surrounding the X property") is its own deal: a staking row
        # rev b: only when the sentence's own subject is the company ("The Company also staked", "We have staked", its name),
        # it states how much ground (claims, cells, hectares, acres, square kilometres), and the ground is not shared,
        # counted "to date" or hypothetical
        st = [m for m in main["ms"] if not m["hl"] and m["kind"] == "staking" and _OWN_STAKE.search(m["s"]) and
              _own_stake_subject(m["s"], self_rx) and _STAKE_QTY.search(m["s"]) and
              not re.search(r"(?i)\boption|\bearn[\s-]?in\b|\bacqui\w+|\bpurchas\w+|\bvendors?\b|\bpreviously\b|\bsince\b|\b(?:19|20)\d\d\b|"
                            r"\bunder\s+(?:this|the|that)\s+(?:\w+\s+)?agreement|\bto\s+date\b|\bjoint\b|\bwould\b|\bon\s+behalf\s+of\b", m["s"])]
        if st:
            main["ms"] = [m for m in main["ms"] if m not in st]
            main["own_region"] = " ".join(x for x in _sentences(body_main[:12000]) if not any(x == m["s"] for m in st))
            deals.append({"ms": st, "props": [p for m in st for p in m["props"]][:1], "kind": "staking", "no_fill": True,
                          "own_region": " ".join(m["s"] for m in st),
                          # staked under an agreement or a joint venture: the company's share is not the default 100%
                          "shared": bool(re.search(r"(?i)\bunder\s+(?:this|the|that)\s+(?:\w+\s+)?agreement|\bjoint[\s-]+venture|\bon\s+behalf\s+of",
                                                   " ".join(m["s"] for m in st)))})
    if len(deals) == 1 and eff_staking and not plural and not dual:
        # FIX5 R2: and the reverse: claims the company bought outright beside the ground it staked ("ABC has purchased
        # the Alpha Claims for $300,000 cash and 200,000 shares") are their own deal: a purchase row
        pu = [m for m in main["ms"] if not m["hl"] and m["kind"] == "purchase" and m["props"] and
              re.search(r"(?i)\b(?:has|have)\s+(?:now\s+|also\s+)?(?:purchased|acquired|bought)\s+the\s+", m["s"]) and
              (self_rx.search(m["s"]) or re.match(r"\s*(?:The\s+Company|We)\b", m["s"])) and
              not re.search(r"(?i)\bpreviously\b|\bsince\b|\bstak", m["s"]) and
              re.search(r"(?i)\bfor\s+(?:(?:US|C|CA|CDN|A)\s?)?\$|\bconsideration\b|\bshares\b", m["s"]) and
              not any(PN.same(p, q) for p in m["props"] for q in main["props"] + hl_props_names)]
        if pu:
            main["ms"] = [m for m in main["ms"] if m not in pu]
            # the staking row's terms leave out every priced purchase ("has previously purchased the X claim for $20,000")
            bought = [m["s"] for m in main["ms"] if m["kind"] == "purchase" and re.search(r"\bfor\s+(?:(?:US|C|CA|CDN|A)\s?)?\$", m["s"])]
            main["own_region"] = " ".join(x for x in _sentences(body_main[:12000]) if not any(x == m["s"] for m in pu) and x not in bought)
            deals.append({"ms": pu, "props": pu[0]["props"][:1], "kind": "purchase", "own_region": " ".join(m["s"] for m in pu),
                          "bought": True})
    n_live = len([d for d in deals if not d.get("dropped")])    # 1.0.9: options relinquished in passing are their own rows
    if plural and n_live > 2 or plural and n_live > 1 and (not main["props"] or len(main["props"]) > 1 or
                                                           all(x["hl"] for x in main["ms"]) or by_cp):
        for d in deals[1:]:
            if d.get("dropped"):
                continue
            d["ms"] = [x for x in main["ms"] if x["hl"]][:1] + d["ms"]
            if not d["props"] and main["props"]:
                d["props"] = main["props"][:1]
        deals.remove(main)
        main = deals[0]
    # 1.0.7: one row per deal (as above): "has staked two high-grade prospects in Nevada." with each named in its own
    # section after ("Sniper Property ...", "Irwin Property ..."): the named properties, one row each, not one row
    for d in deals:
        if d["props"] or not (d["kind"] == "staking" or d is main and _hl_type(h) == "staking"):
            continue
        for m in d["ms"]:
            cm = None if m["hl"] else re.search(r"(?i)\bstak(?:ed|ing)\s+(?:an?\s+)?(two|three|four|five|2|3|4|5)\s+(?:new\s+)?(?:[\w\-]+\s+){0,4}?"
                                                 r"(?:propert(?:y|ies)|prospects|projects|claim\s+blocks|blocks)\b", m["s"])
            if not cm:
                continue
            n = {"two": 2, "three": 3, "four": 4, "five": 5}.get(cm.group(1).lower()) or int(cm.group(1))
            at = body_main.find(m["s"][-60:])
            names = []
            for x in _sentences(body_main[at:at + 6000] if at >= 0 else ""):
                for _q, p in _props_in(x, issuer_words):
                    if not any(PN.same(p, q) for q in names):
                        names.append(p)
            if len(names) >= n:
                d["props"] = names[:n]
            break
    # staking of several named properties in one sentence: one row each
    for d in list(deals):
        if d["kind"] == "staking" or (d is main and _hl_type(h) == "staking") or \
                d["kind"] == "expand" and not any(m["kind"] in ("purchase", "option") for m in d["ms"]):
            uniq = []
            for p in d["props"]:
                if not any(PN.same(p, q) for q in uniq):
                    uniq.append(p)
            if len(uniq) > 1:
                i = deals.index(d)
                deals[i:i + 1] = [dict(d, props=[p], one=True) for p in uniq]
                if d is main:
                    main = deals[i]
    rows = []
    hl_type = _hl_type(h)
    for d in deals:
        d["dl_year"] = dl_year
        d["other_names"] = other_names
        r = _row(d, sents, h, b, body_main, self_rx, issuer_words, hl_type if d is main and not d.get("dual") else None, d is main,
                 len(deals))
        if r:
            rows.append(r)
    # the same property twice (one agreement restated): keep the first
    out = []
    for r in rows:
        if any(r["property"] and o["property"] and PN.same(r["property"], o["property"]) and o["deal_type"] == r["deal_type"]
               for o in out):
            continue
        out.append(r)
    return {"rows": out, "reason": None if out else "no_deal"}


def _hl_type(h):
    if _STOCK_OPT.search(h):
        h = _STOCK_OPT.sub(" ", h)
    h = _HL_BACKGROUND.sub(" ", _NONLAND.sub(" ", h))       # 1.0.7
    th = _THIRD.search(h)
    if th and th.start() > 20:
        h = h[:th.start()]
    if re.search(r"(?i)\boption|\bearn[- ]?in\b|\bearns\s+\d", h):
        return "option"
    if re.search(r"(?i)\b(?:sells?|sale\s+of|divest\w*|disposition\s+of|to\s+sell)\b[^.]{0,80}\b(?:propert(?:y|ies)|projects?|claims|"
                 r"interests?|licen[cs]es|claim\s+blocks?|mines?|assets|(?<=%\s)(?:share|stake)\s+(?:of|in))\b|\bproperty\s+sale\b", h):
        return "property_sale"
    if re.search(r"\b(?i:sells?|to\s+sell)\s+(?:(?i:its|the)\s+)?(?:\d{1,3}\s*%\s+(?:(?i:interest)\s+(?i:in)\s+)?(?:(?i:the)\s+)?)?"
                 r"[A-Z][\w\-]*(?:\s+[A-Z][\w\-]*){0,3}(?:\s+(?i:to)\s+[A-Z]|\s*$)", h):
        return "property_sale"      # 1.0.8: "Dios sells K2 to Azimut", "Extends LOI to Sell Northshore Gold": a named asset sold
    if re.search(r"(?i)\bstak(?:es|ed|ing)\b", h) and not re.search(r"(?i)\b(?:acquir\w*|purchas\w*)\b", h):
        return "staking"
    if re.search(r"(?i)\b(?:acquir\w*|purchase|acquisition)\b[^.]{0,60}\b(?:claims?|licen[cs]es?|tenements?|concessions|patents)\b", h):
        return "claim_purchase"     # 1.0.8: mining concessions and patents (patented claims) are claims
    if re.search(r"(?i)\b(?:acquir\w*|purchase|acquisition)\b[^.]{0,80}\b(?:propert(?:y|ies)|project)\b", h):
        return "property_purchase"
    if re.search(r"(?i)\bstak(?:es|ed|ing)\b", h):
        return "staking"
    return None                     # OPT_V1b: "Expands Land Package" says nothing of how; the body decides


# 1.0.7: the terms of the release's own deal read as an option, whatever the headline calls it ("Acquires X Property":
# "the Company can earn a 100% interest ... within two years", "the Optionors", "the right to acquire ... over a
# two-year period", "approval of the option agreement"). Not an earlier or underlying option.
_OPT_TERMS = re.compile(r"(?i)\b(?:can|may)\s+earn\b|\bto\s+earn\s+(?:an?\s+|up\s+to\s+(?:an?\s+)?)?\d|\boption\s+agreement\b|\boptionors?\b|"
                        r"\bearn[\s-]?in\b|\b(?:right|terms?)\s+to\s+acquire\b[^.]{0,300}\bover\s+(?:a|the\s+next)?\s*(?:[\w()]+[\s-]+){0,2}(?:years?|months?)\b|"
                        r"\bexercise\s+(?:of\s+)?the\s+option\b|\boption\s+to\s+(?:acquire|purchase|earn)\b")
_OLD_DEAL = re.compile(r"(?i)\b(?:original|previous|previously|existing|prior|underlying|former|earlier)\b")


def _opt_terms(ms, dl_year, props=()):
    for m in ms:
        if m["hl"] or not _OPT_TERMS.search(m["s"]) or _OLD_DEAL.search(m["s"]) or _STOCK_OPT.search(m["s"]) or _TERM.search(m["s"]):
            continue
        if m["props"] and props and not any(PN.same(p, q) for p in m["props"] for q in props):
            continue                # another property's option
        if dl_year and any(int(y) < dl_year for y in re.findall(r"\b((?:19|20)\d\d)\b", m["s"])):
            continue
        return True
    return False


def _row(d, sents, h, b, body_main, self_rx, issuer_words, hl_type, is_main, n_deals):
    ms = d["ms"]
    if is_main and not re.search(r"(?i)\boption|\bearn[\s-]?in\b|\bearns?\b", h):
        lead = [m for m in ms if not m["hl"]][:1]
        if lead and (lead[0]["kind"] in ("purchase", "staking", "expand") and lead[0]["i"] <= 3 or
                     lead[0]["kind"] in ("staking", "expand") and lead[0]["i"] <= 6):
            ms = [m for m in ms if m["kind"] != "option" or m["i"] <= 3] or ms   # OPT_V1d: a purchase lead; a later option is background
    text = " ".join(m["s"] for m in ms)
    kinds = [m["kind"] for m in ms]
    if "expand" in kinds:
        other = [k for k in kinds if k != "expand"]
        kinds = [(other[0] if other else "staking") if k == "expand" else k for k in kinds]
    # deal type
    strong_opt = re.search(r"(?i)\boption\s+to\s+(?:acquire|earn|purchase)|\bearn[- ]?in\b|\bto\s+earn\b|\bmay\s+earn\b|"
                           r"\bentered\s+into\s+(?:an?\s+)?(?:\w+\s+)?option\s+agreement|\bgranted\s+(?:the|an)\s+option|\boption\s+agreement\s+"
                           r"(?:to|whereby|pursuant|with)\b|\bexercis\w+\s+(?:the|its)\s+option|\bhas\s+optioned\b|"
                           r"\b(?:executed|signed|entered\s+into)\s+(?:an?|the)\s+(?:\w+\s+){0,2}option\b",
                           " ".join(m["s"] for m in ms if (m["hl"] or m["i"] <= 3 or hl_type not in ("claim_purchase", "property_purchase",
                                                                                                       "property_sale"))
                                    and not re.search(r"(?i)\bpreviously\s+(?:entered|announced|optioned|acquired)", m["s"])))
    if hl_type in ("claim_purchase", "property_purchase") and is_main and not strong_opt and \
            _opt_terms(d["ms"], d.get("dl_year"), d["props"]):
        strong_opt = True           # 1.0.7: "Acquires X Property" whose terms are an option ("can earn", "the Optionors")
        kinds = kinds + ["option"]
    if hl_type in ("claim_purchase", "property_purchase", "property_sale") and is_main and not strong_opt and \
            not re.search(r"(?i)\boption", h):
        kinds = [k for k in kinds if k != "option"] or kinds    # OPT_V1b: a purchase headline; an option deeper down is background
    if "option" in kinds and (hl_type in (None, "option") or not is_main or strong_opt):
        typ = "option"
    elif is_main and hl_type:
        typ = hl_type
    else:
        typ = kinds[0]
    text_nip = re.sub(r"(?i)\bintellectual\s+property\b", "IP", text)
    if typ == "option" and not re.search(r"(?i)\b" + _LAND + r"\b|\boption\s+to\s+(?:purchase|acquire)\b[^.]{0,120}\bpermits?\b", text_nip) and (not re.search(
            r"(?i)\boption\s+(?:agreement|payment)|\boptionor|\bearn[\s-]?in\s+(?:agreement|term\s+sheet|right)|"
            r"\boption\s+to\s+earn\s+(?:up\s+to\s+)?(?:an?\s+)?\d{1,3}\s*%\s+interest", text) or re.search(     # 1.0.9: earning an interest is ground
            r"(?i)\boption\s+to\s+acquire\b[^.]{0,120}\b(?:shares|share\s+capital|ownership\s+of)\b", text)):
        return None                 # an option over a company's shares (Temas / ORF Technologies) is not a land deal
    if typ in ("claim_purchase", "property_purchase", "purchase") and not d.get("bought") and _STAKED_BODY.search(body_main[:5000]) or \
            typ in ("claim_purchase", "property_purchase", "purchase") and re.search(
            r"(?i)\bnewly[\s-]+staked\b|\bgovernment\b[^.]{0,40}\b(?:has|have)\s+granted\b[^.]{0,40}\b(?:licen[cs]es|permits|concessions)\b",
            body_main[:5000]):
        typ = "staking"
    if typ == "purchase":
        pm = next((m for m in ms if m["kind"] == "purchase"), ms[0])
        pm = next((m for m in ms if _PURCH.search(m["s"]) and m["kind"] in ("purchase", "expand")), pm)
        pmm = _PURCH.search(pm["s"])
        lw = ""
        if pmm and not re.match(r"\s*(?:Pty|Ltd|Inc|Corp|LLC|Limited)\b", pm["s"][pmm.end():]):
            g = pmm.group(0)
            if re.match(r"(?i)(?:purchas|acquir|buy|bought)", g):
                lw = re.search(r"(?i)(\w+(?:\s+\w+)?)\W*$", g).group(1).lower()
            else:
                lw = g.split()[0].lower()
            if re.search(r"(?i)\b(?:claims?|licen[cs]es?|tenements?)\s+(?:\w+\s+){0,1}$", pm["s"][max(0, pmm.start() - 40):pmm.start()]):
                lw = "claims"               # "the mineral claims acquired under the Secret Pass Gold Project"
        if re.search(r"claims?$|claim\s+block$|licen[cs]es?$|tenements?$", lw):
            typ = "claim_purchase"          # OPT_V1d: the thing bought decides ("expanded its property by acquiring the X claims")
        elif re.search(r"propert(?:y|ies)$|projects?$|deposit$|mines?$|lands$|parcels?$|land$|salars?$|concessions?$", lw):
            typ = "property_purchase"
        else:
            typ = "claim_purchase" if re.search(r"(?i)\b(?:claims?|licen[cs]es?|tenements?|exploration\s+permits)\b", pm["s"]) and not \
                re.search(r"(?i)\b(?:propert(?:y|ies)|project)\b", pm["s"][:200]) else "property_purchase"
    if typ == "option":
        direction = None
        for m in ms:
            dd = _direction(m["s"], m["hl"], self_rx, h)
            if dd == "option_out":
                direction = dd
                break
            if re.search(r"(?i)\b(?:the\s+Company|we)\s+(?:has\s+been\s+|was\s+)?(?:granted|may\s+(?:acquire|earn)|has\s+the\s+(?:right|option)|"
                         r"can\s+earn|will\s+(?:acquire|earn|achieve))|\bgrant(?:ed|s)\s+(?:to\s+)?(?:the\s+Company|us)\s+(?:the|an)\s+"
                         r"(?:exclusive\s+)?(?:right|option)|\b(?:the\s+Company|it)\s+has\s+(?:also\s+)?secured\s+(?:an?\s+)?(?:separate\s+)?"
                         r"option\s+to\s+acquire", m["s"]):
                break
        typ = direction or "option_in"
    # stage
    stage = _stage(ms, typ, d.get("term"), h)
    # property
    props = d["props"]
    prop = None
    if d.get("one"):
        props = props[:1]
    if props:
        if len(props) > 1 and n_deals == 1 and re.search(r"(?i)\b(?:two|three|four|\d)\s+(?:advanced\s+)?(?:\w+\s+){0,3}(?:projects|properties)\b|"
                                                         r"\bcomprising\s+the\b", text):
            uniq = []
            for p in props:
                if not any(PN.same(p, q) for q in uniq):
                    uniq.append(p)
            prop = " / ".join(uniq[:4])
        else:
            prop = props[0]
    if not prop:
        for m in ms:
            pp = m["props"] if not m["hl"] else []      # 1.0.7: the names already checked (headline copy, other news)
            if pp:
                prop = pp[0]
                break
    if not prop and is_main and not d.get("no_fill"):
        # OPT_V1e (PN_V1): the deal sentences name none; the release's main project. OPT_V1f: then any other project the
        # release names, when the headline names it ("Closes Magistral Acquisition": the body's top project is Jabali)
        tried = []
        for pr in [PN.primary(h, body_main)] + PN.projects(h, body_main):
            if not pr or any(PN.same(pr, t) for t in tried):
                continue
            tried.append(pr)
            sm = re.match(r"(.+?)\s+(" + PN.SUFFIX + r")$", pr or "")
            pr = _name(sm.group(1), sm.group(2)) if sm else _name(pr) if pr else None     # this reader's lead-ins and places too
            pr = _geo_ext(pr, h + " || " + body_main)       # 1.0.5: "High Lake and West Hawk Lake Properties"
            kw = PN.key(pr).split() if pr else []
            if len(kw) == 1 and kw[0] in PN._PART_WORDS:
                continue           # OPT_V1f: "Lake Property" from "McFarlane Lake Mining" is no name
            if pr and typ != "staking" and any(PN.same(pr, o) for o in d.get("other_names") or ()):
                continue           # 1.0.7: the project of the headline's other news
            iw = {T._fold(w).lower() for w in issuer_words} if issuer_words else set()
            if kw and kw[0] in iw and (len(kw) > 1 and kw[1] in iw or
                                       PN._REGION.match(" ".join(w.title() for w in kw[1:])) or len(kw) == 1):
                continue           # OPT_V1f: "Hertz Energy Namibia", "Nexus South Dakota" start with the company's name
            hm = re.search(r"(?i)\b" + re.escape(kw[0]) + r"\b", T._fold(h)) if kw else None
            nx = re.match(r"[\s\-]+([A-Z][\w'\u2019]*)", T._fold(h)[hm.end():]) if hm and len(kw) > 1 else None
            if nx and nx.group(1).lower() != kw[1] and nx.group(1).lower() not in _COMMOD and nx.group(1).lower() not in kw and \
                    not re.fullmatch(PN.SUFFIX + r"|(?i:property|project|claims?|mine|deposit|prospect|gold|silver|copper|lithium|uranium)", nx.group(1)):
                hm = None          # 1.0.9: the headline names another one ("San Javier" does not name "San Antonio")
            if pr and hm and not (issuer_words and set(kw) <= {T._fold(w) for w in issuer_words}) and \
                    not re.search(r"(?i)\b(?:adjacent\s+to|near|next\s+to|neighbou?ring|bordering|adjoining)\s+(?:the\s+)?(?:[\w\-.]+\s+){0,5}$|"
                                  r"(?:Corp|Inc|Ltd|Limited|Mining|Resources|Gold|Metals)\.?['\u2019]s\s+(?:[\w\-]+\s+){0,1}$",
                                  T._fold(h)[:hm.start()]) and not _NEAR_ONLY.search(T._fold(h)[:hm.start()]) and \
                    not re.match(r"(?i)(?:\s+(?!(?:project|property|claims|mine)\b)\w+){0,3}?\s+(?:belts?|districts?|regions?|areas?|camps?|trend|basin|valley\s+region)\b",
                                 T._fold(h)[hm.start() + len(" ".join(kw)):]):
                prop = pr      # only when the headline names it: the body's most-mentioned project can be a neighbour
                break
            if len(tried) >= 6:
                break
    if prop:
        prop = " / ".join(PN.bare(x) for x in prop.split(" / "))     # the column is headed Property
    # counterparty
    cp = _counterparty(ms, typ, self_rx, b)
    if cp is None and typ != "staking" and not d.get("cp_short"):
        cp = _cp_fallback(body_main, self_rx, typ)
    if d.get("cp_short"):
        full = re.search(r"\b(" + re.escape(d["cp_short"]) + r"[\w\s.&]{0,40}?(?:Corporation|Corp|Inc|Ltd|Limited)\.?)", b)
        cp = re.sub(r"(?i)[,\s]+(?:Inc|Ltd|Corp|Corporation|Limited|LLC)\.?$", "", full.group(1)) if full else d["cp_short"]
    if typ == "option_in" and cp:
        typ = _earner_out(cp, body_main, self_rx) or typ
    # interest
    pct = _interest(ms, stage, typ)
    if d.get("shared") and not any(_PCT_INT.search(m["s"]) for m in ms):
        pct = None
    # terms
    region = d["own_region"] if d.get("own_region") else text if n_deals > 1 else body_main[:12000]
    terms = _terms(region, typ)
    date = None
    for m in ms:
        dm = _DATED.search(m["s"]) or _ON_DATE.search(m["s"])
        if dm and not re.search(r"(?i)news\s+release\s+dated|press\s+release\s+dated", m["s"][max(0, dm.start() - 30):dm.end()]):
            date = T._iso(dm)
            break
    if typ == "staking" and stage not in ("terminated",):
        stage = "completed" if _STAKE_DONE.search(h + " " + text) or re.search(
            r"(?i)\bgovernment\b[^.]{0,40}\b(?:has|have)\s+granted\b[^.]{0,40}\b(?:licen[cs]es|permits|concessions)\b", body_main[:5000]) \
            else "signed"     # 1.0.7: licences granted = registered
    return dict({"deal_type": typ, "stage": stage, "property": prop, "counterparty": None if typ == "staking" else cp,
                 "interest_pct": pct, "date": date, "metal": T._metal(h + " " + b[:2500]),
                 "jurisdiction": _juris(h, sents, ms, n_deals)}, **terms)


def _earner_out(cp, b, self_rx):
    """FIX5 D2: the other side is the one earning ("for Beta to incur ... to exercise the first option to earn a 51%
    interest", "Upon completion of the earn-in to 90% by Beta", "Beta may earn"), and the company is never said to
    earn: the company granted the option (option_out)."""
    w = re.escape(cp.split()[0])
    them = re.search(r"\b" + w + r"\b[\w\s.&'\u2019\-]{0,30}?\s+(?:will|may|can|shall|could)\s+(?:\w+\s+){0,2}?earn\b|\bfor\s+" + w +
                     r"\b[\w\s.&'\u2019\-]{0,30}?\s+to\s+(?:incur|earn|exercise|fund|spend)\b|\bearn[\s-]?in\s+(?:to\s+)?(?:\w+\s+){0,3}?by\s+" + w + r"\b|"
                     r"\b" + w + r"\b[\w\s.&'\u2019\-]{0,30}?\s+(?:has\s+the\s+right|is\s+entitled|has\s+the\s+option)\s+to\s+(?:\w+\s+){0,2}?(?:earn|acquire)\b", b)
    if not them:
        return None
    us = re.search(r"(?i)\b(?:the\s+Company|we)\s+(?:will|may|can|shall|could)\s+(?:\w+\s+){0,2}?earn\b|\b(?:the\s+Company|we)\s+(?:has|have)\s+the\s+"
                   r"(?:right|option)\s+to\s+(?:\w+\s+){0,2}?(?:earn|acquire)\b|\bfor\s+the\s+Company\s+to\s+(?:earn|exercise|incur)", b)
    if us:
        return None
    for m in self_rx.finditer(b):
        if re.match(r"[\w\s.&'\u2019\-]{0,30}?\s+(?:will|may|can|shall)\s+(?:\w+\s+){0,2}?earn\b", b[m.end():m.end() + 60]):
            return None
    return "option_out"


_STAKED_BODY = re.compile(r"(?i)\b(?:was|were)\s+(?:recently\s+)?staked(?![^.]{0,40}\b(?:19\d\d|200\d|201\d)\b)|\bstaked\s+on-?line|\bhas\s+staked|"
                          r"\b(?:through|via|by)\s+(?:directly\s+)?staked\b|\bdirectly\s+staked\b|\b(?:by|through|via)\s+(?:physical\s+|online\s+|"
                          r"claim\s+|map\s+)?staking\b|\bmap[\s-]designat\w+|\bwere\s+designated")
_OWN_STAKE = re.compile(r"(?i)\b(?:has|have|also|recently|additionally|further|then)\s+(?:also\s+|recently\s+|additionally\s+)?staked\b|"
                        r"^\W*(?:The\s+Company|We)\s+(?:also\s+)?staked\b")


_STAKE_QTY = re.compile(r"(?i)\b\d[\d,.]*\s*(?:(?:new|additional|mineral|mining|federal|unpatented|lode|placer|contiguous)\s+)*"
                        r"(?:claims?\b|claim\s+units|cells\b|hectares|ha\b|acres|km2|km\u00b2|square\s+(?:kilometres|kilometers|km|miles))")


def _own_stake_subject(s, self_rx):
    """rev b: the staking sentence's own subject is the company: "The Company", "we" or its name, after an optional lead
    ("In addition,", "Additionally,", "In addition to the core project area,"), with "staked" in the same clause."""
    lead = re.sub(r"(?i)^\W*(?:(?:in\s+addition(?:\s+to\s+[^,.;]{1,80})?|additionally|further(?:more)?|also)\s*,?\s*)", "", s)
    m = re.match(r"(?i)(?:the\s+company|we)\b", lead) or self_rx.match(lead)
    return bool(m) and bool(re.match(r"[^.;:]{0,40}?\bstaked\b", lead[m.end():]))


_IF_BEFORE = re.compile(r"\b(?:[Ii]f|[Ss]hould|[Uu]nless|[Ww]hether|in\s+the\s+event|may|would|could|shall|will|right\s+to|supersede)\b[^;:]*$")


def _term_said(group):
    """1.0.7: a termination the release reports, not one written as a condition ("If Clarity ... decides not to proceed
    with the further 51%", "If Precore has waived or abandoned its right ...")."""
    for x in group:
        for m in list(_TERM.finditer(x)) + list(re.finditer(r"(?i)\bnot\s+to\s+proceed", x)):
            if re.match(r"(?i)\w*\s[^.]{0,160}?\breplac\w*\s+(?:it|them|(?:the|that|this)\s+(?:\w+\s+){0,2}?agreement)\s+(?:with|by)\b", x[m.start():]):
                continue            # 1.0.9: "agreed to terminate the purchase agreement ... and replace it with an option agreement"
            if not _IF_BEFORE.search(x[max(0, m.start() - 120):m.start()]):
                return True
    return False


# 1.0.7: a purchase the release reports as done: "has acquired the X claims", "closed its ... agreement ... to acquire",
# with no condition still open ("subject to", "will issue", "closing is expected", "upon approval").
_ACQUIRED = re.compile(r"(?i)\b(?:has|have)\s+(?:now\s+|successfully\s+|recently\s+)?(?:acquired|purchased)\b|"
                       r"\bclosed\s+(?:its|the)\s+(?:previously\s+announced\s+)?[^.]{0,160}?\bagreement\b[^.]{0,160}?\bto\s+acquire\b|"
                       r"\b(?:transfer(?:red)?|registered)\s+(?:to|in\s+the\s+name\s+of)\s+(?:the\s+Company|us)\b")
_PENDING = re.compile(r"(?i)\bsubject\s+to\b|\b(?:will|shall)\s+(?:be\s+)?(?:acquire|complete|close|issue|pay|receive|grant)|\bexpected\s+to\s+"
                      r"(?:close|complete)|\bupon\s+(?:the\s+)?(?:closing|completion|approval|receipt|acceptance)|\bconditional\b|\bpending\b|"
                      r"\bagreed\s+to\s+(?:acquire|purchase)|\bagreement\s+to\s+(?:acquire|purchase)\b(?![^.]{0,60}\bclosed)|\bto\s+be\s+"
                      r"(?:issued|paid|completed|closed)|\bclosing\s+(?:date|is|of\s+the)|\bremains?\s+subject|\bdue\s+diligence\b|"
                      r"\bon\s+or\s+before\b|\banniversary\b|\bletter\s+of\s+intent\b|\bLOI\b|\bterm\s+sheet\b|"
                      r"\bover\s+(?:a|the\s+next)\s+(?:[\w()]+[\s-]+){0,2}(?:years?|months?)\b|\bcan\s+earn\b")


# 1.0.7: a headline that reports the deal as closed ("Completes Sale to X", "Closes Disposition with X", "Opawica Sale
# Closed", "Closes Strategic Land Acquisition"), or the ownership as whole ("Acquires 100% Ownership in X").
_HL_DONE = re.compile(r"(?i)\b(?:completes?|completed|closes|closed|closing\s+of|completion\s+of|finali[sz]es)\b[^.]{0,60}?\b(?:sale|divestiture|"
                      r"disposition|acquisition|purchase)\b|\b(?:sale|acquisition|purchase|disposition|divestiture)\s+(?:is\s+|has\s+been\s+)?"
                      r"(?:closed|completed)\b")
_HL_OWNED = re.compile(r"(?i)\b(?:acquires|consolidates|secures|achieves|attains)\s+(?:a\s+)?100\s*%\s+ownership\b|"
                       r"\bfulfil\w*\s+(?:the\s+|its\s+)?(?:\w+\s+)?option\b")
_STAKE_DONE = re.compile(r"(?i)\b(?:licen[cs]es?|claims?|applications?|tenements?|concessions?)\b[^.]{0,80}?\b(?:has|have|were|was|been)\s+"
                         r"(?:now\s+|officially\s+)?(?:granted|issued|approved|registered)\b|\b(?:receives?|received)\s+(?:the\s+)?"
                         r"(?:approval|grant)\s+of\b[^.]{0,60}\b(?:licen[cs]es?|applications?|claims|tenements?)\b")


# 1.0.9: "has now acquired ..." while "the acquisition ... remains subject to customary conditions of closing": signed
_OPEN_CLOSE = re.compile(r"(?i)\bremains?\s+subject\s+to\b|\bsubject\s+to\s+(?:the\s+)?(?:customary\s+)?(?:conditions\s+(?:of|to|for)\s+)?closing\b")


# 1.0.8: a "binding agreement" is signed, even when its paper is a term sheet or MOU (the label guide: signed = a
# definitive or binding agreement); a letter of intent stays proposed, binding or not
_BINDING = re.compile(r"(?i)(?<!non-)(?<!non\s)\bbinding\s+(?:definitive\s+)?agreements?\b")


def _stage(ms, typ, term_flag, h=""):
    if term_flag:
        return "terminated"
    hl = [m["s"] for m in ms if m["hl"]]
    # OPT_V1e: "Signs Titanium LOI": a headline that names only the paper still says the deal is proposed
    h_prop = not hl and bool(_PROP.search(h or "")) and not re.search(r"(?i)\bdefinitive\b", h or "") and not _BINDING.search(h or "")
    h_amend = not hl and bool(re.search(r"(?i)\b(?:extension|amendment)s?\s+(?:of|to)\s+(?:the\s+)?(?:\w+\s+){0,3}?(?:LOI|letter\s+of\s+intent|"
                                        r"option|agreement)|\bamends\b", h or ""))     # 1.0.7: "Announces Extension of LOI"
    bodies = [m["s"] for m in ms if not m["hl"]]
    for group in (hl, bodies):
        t = " ".join(group)
        if not t:
            continue
        if _TERM.search(t) and not re.search(r"(?i)\b(?:may\s+be\s+terminated|will\s+(?:automatically\s+)?terminate|terminate\s+at\s+the|"
                                             r"failure\s+to|may\s+terminate|result\s+in\s+the\s+termination|option\s+may\s+be\s+terminated)",
                                             t) and _term_said(group) or re.search(r"(?i)\bnot\s+to\s+proceed", t) and _term_said(group):
            return "terminated"
        if group is hl and re.search(r"(?i)\bclos(?:es|ed|ing\s+of)\s+(?:the\s+|an?\s+|its\s+)?(?:definitive\s+)?(?:\w+\s+){0,2}?option\s+agreement", t):
            return "signed"         # OPT_V1d: "Closes Option Agreement": the option starts, nothing is earned yet
        if any(not re.search(r"(?i)\b(?:if|once|when|upon|on|at|should|until|event|order\s+to|may|will|would|subject\s+to|having|date|"
                             r"time|before|prior\s+to|after|following)\b[^.;:]{0,30}$",
                             t[max(0, m.start() - 40):m.start()])
               and not (typ in ("option_in", "option_out") and re.match(r"(?i)clos", m.group(0)))    # OPT_V1e
               and not (re.match(r"(?i)has\s+now\s+acquired", m.group(0)) and _OPEN_CLOSE.search(t))   # 1.0.9
               for m in _COMP.finditer(t)):
            return "completed"      # OPT_V1b: "If the Company exercises the Option" is a term, not an event
        if (typ in ("claim_purchase", "property_purchase", "property_sale") and _HL_DONE.search(h or "") or _HL_OWNED.search(h or "")) \
                and not re.search(r"(?i)\b(?:option|earn[\s-]?in)\b[^.]{0,30}(?:agreement|acquisition)", h or ""):
            return "completed"      # 1.0.7: "Completes Sale to Gold Hunter", "Acquires 100% Ownership in X"
        if group is bodies and typ in ("claim_purchase", "property_purchase") and any(
                re.search(r"(?i)\bclosed\s+(?:its|the)\s+(?:previously\s+announced\s+)?[^.]{0,160}?\bagreement\b[^.]{0,160}?\bto\s+acquire\b", x)
                and not re.search(r"(?i)\bsubject\s+to\b", x) for x in group[:3]):
            return "completed"      # 1.0.7: "has closed its previously announced ... agreement ... to acquire"
        if group is bodies and typ in ("claim_purchase", "property_purchase") and \
                any(_ACQUIRED.search(x) for x in group[:3]) and not any(_PENDING.search(x) for x in group):
            return "completed"      # 1.0.7: "has acquired the Wilson Claims ... for $1,000 and 10,000 shares"
        if group is bodies and typ == "property_sale" and any(
                re.search(r"(?i)\b(?:has|have)\s+(?:now\s+)?(?:sold|divested)\b|^[^,;]{0,80}?\bsold\s+(?:its|a|the|all|100)\b", x) and
                not _PENDING.search(x) for x in group[:3]):
            return "completed"      # 1.0.8: "announces that it has sold a 100% interest in its X Property to Y for $100,000"
        ta = " ".join(x for x in group if not re.search(r"(?i)\bassign(?:ed|s|ment)\b|\bunderlying\b", x))
        ta = re.sub(r"(?i)\bas\s+amended\b|\bamended\s+(?:and\s+restated\s+)?(?:offering|prospectus|financial|MD&A|filing|"
                    r"document|circular|notice|technical)\b|\bassignment\s+and\s+amendment\b", " ", ta)
        if _AMEND.search(ta) or re.search(r"(?i)\bamendment\b", ta) or h_amend and group is not hl:
            return "amended"
        if _PAY.search(t) or group is hl and _PAY_HL.search(t):
            return "payment"
        if _PROP.search(t) and not re.search(r"(?i)\b(?:pursuant\s+to|under)\s+(?:a|the)\s+letter\s+of\s+intent\s+dated|"
                                             r"\b(?:execution|signing)\s+of\s+the\s+letter\s+of\s+intent|\bprevious(?:ly)?\b[^.]{0,80}\bletter\s+of\s+intent|"
                                             r"\b(?:replac|supersed)\w+\s+the\s+(?:letter\s+of\s+intent|LOI|term\s+sheet)|"
                                             r"previously\s+announced\s+under\s+a\s+memorandum", t) and not re.search(
                r"(?i)\b(?:entered\s+into|signed|executed|executes|enters\s+into)\s+(?:a\s+|the\s+|two\s+)?definitive|definitive\s+"
                r"(?:\w+\s+){0,2}agreements?\s+dated", t) and not ((_BINDING.search(t) or _BINDING.search(h or "")) and
                                    not re.search(r"(?i)\bnon-?\s?binding\b", t)):
            return "proposed"
        if re.search(r"(?i)\bincrease\s+in\s+land\s+package\s+under\b", t):
            return "amended"
        if h_prop and group is not hl:
            return "proposed"
        if _SIGN.search(t) and group is not hl:
            return "signed"
        if group is hl and re.search(r"\b(?:Options|OPTIONS|Signs|SIGNS|Enters|ENTERS|Executes|EXECUTES)\b", t):
            return "signed"         # OPT_V1b: "Voyageur ... Options Mink Narrows Project": a termination deeper down is another deal
    return "signed"


def _counterparty(ms, typ, self_rx, b):
    cands = []
    for m in ms:
        s = m["s"]
        orgs = _orgs_in(s, self_rx)
        for k, (pos, o) in enumerate(orgs):
            end = pos + len(o)
            if o.split()[0] in _PVERB or re.match(r"\s*(?:[Pp]ropert|[Pp]roject|Claims|Deposit|Mine\b|PROPERT|PROJECT)", s[end:end + 12]):
                continue
            if re.match(r"['\u2019]s\s+(?:wholly[\s-]owned\s+)?subsidiar", s[end:end + 30]):
                continue                    # "F3 Uranium Corp's wholly-owned subsidiary, F4 Uranium Corp." -> F4
            if re.search(r"(?i)\b(?:its|our|the\s+Company['\u2019]s)\s+(?:indirect\s+|direct\s+)?(?:wholly\s*[\s-]\s*owned\s+)?(?:\w+\s+)?subsidiary,?\s*(?:\(\s*)?$",
                         s[max(0, pos - 60):pos]) or re.search(r"(?i)^[^.]{0,80}\b(?:in\s+consideration\s+for\s+services|finder|"
                                                              r"introducing\s+the\s+Company)", s[end:end + 120]):
                continue                    # OPT_V1b: the issuer's own subsidiary, or a finder, is not the other side
            before = s[max(0, pos - 70):pos]
            after = s[end:end + 70]
            score = 0
            if re.search(r"(?i)\b(?:with|from)\s+(?:(?:its|the)\s+)?(?:[\w'\u2019\-]+\s+){0,5}?$", before) and not any(
                    p2 < pos and p2 > pos - 70 for p2, o2 in orgs[:k]
                    if not re.match(r"\s*(?:[Pp]ropert|[Pp]roject|PROPERT|PROJECT|Claims|Deposit|Mine\b)", s[p2 + len(o2):p2 + len(o2) + 12])) or re.search(r"(?i)subsidiary,?\s+$", before) and \
                    not re.search(r"(?i)\band\s+its\s+(?:[\w\-]+\s+){0,3}subsidiary,?\s+$", before) and not \
                    re.search(r"(?i)\b(?:shares|securities)\b[^.]{0,80}\bof\s+[\w'\u2019\-]+(?:\s+[\w'\u2019\-]+)?['\u2019]s\s+wholly[\s-]owned\s+"
                              r"subsidiary,?\s+$", s[max(0, pos - 160):pos]):
                score += 3          # "shares ... of Cachee's wholly-owned subsidiary, Launay Gold Corp." -> Launay is the target
            if typ in ("option_out", "property_sale") and re.search(r"(?i)\bto\s+$", before):
                score += 3
            if re.search(r"(?i)^\W{0,4}\(?\s*(?:the\s+)?[\u201c\"]?\s*(?:Optionors?|Optionee|Vendors?|Purchaser|Buyer|Target|Assignor)\b", after) \
                    and not (re.search(r"(?:,|\band)\s*$", before) and any(pos - 90 < p2 < pos for p2, _ in orgs[:k])):
                score += 4          # "with A Ltd., B Inc. and C Inc. (the "Optionors")": the label is the list's, A leads
            if typ == "option_out" and re.search(r"(?i)^[^.]{0,60}\b(?:will\s+obtain|has\s+exercised|may\s+earn|can\s+earn|has\s+the\s+right)",
                                                 after):
                score += 3
            if re.search(r"(?i)\b(?:partner|optionee)\b", before[-40:]):
                score += 2
            if re.search(r"(?i)\b(?:historical|drilled|discovered|explored|previous|owned\s+by|adjacent|near|contiguous|operated\s+by|"
                         r"including|such\s+as|by)\s+(?:\w+\s+){0,2}$", before):
                score -= 4
            if score >= 3:
                cands.append((score, -m["i"], o))
    if not cands:
        return None
    cands.sort(reverse=True)
    o = cands[0][2]
    o = re.sub(r"(?i)[,\s]+(?:Inc|Ltd|Corp|Corporation|Limited|LLC)\.?$", "", o).strip()
    return o or None


_ROLE_AFTER = re.compile(r"(?i)^\W{0,4}\(?\s*(?:the\s+)?[\u201c\"]?\s*(?:Optionors?|Optionee|Vendors?|Target)\b")
_ROLE_BEFORE = re.compile(r"(?i)(?:\boptioned\s+from|\bearn-in\s+partner\b[^.]{0,80}?,|\boption\s+payment\s+from|"
                          r"\bowing\s+to|\boptionor,?)\s+$")


_RETAINS = re.compile(r"\b((?:(?:[A-Z][\w&'\u2019\-]*|(?:Corp|Inc|Ltd|Co|[A-Z])\.)\s+){0,3}[A-Z][\w&'\u2019\-]*\.?)\s+(?:will\s+|shall\s+)?retain(?:s|ing)?\s+(?:a|an)\s+"
                      r"(?:[\w\-]+\s+){0,2}?\d{1,2}(?:\.\d+)?\s*%\s*(?:\(\s*[\w.%]+\s*\)\s*)?(?i:NSR|net\s+smelter|royalty|gross\s+(?:overriding|metal))")
_HELD_BY = re.compile(r"(?i)\b(?:option\s+to\s+(?:acquire|earn|purchase)|acquir\w+|purchas\w+)\b[^.;]{0,100}?\b(?:held|owned)\s+by\s+$")


def _cp_fallback(b_main, self_rx, typ):
    """OPT_V1 (2026-09-23): no counterparty in the deal sentences. Take one from the body only when the release gives
    it a role: 'X Ltd. (the "Optionor")', 'optioned from X', 'option payment from X', 'earn-in partner ..., X'."""
    if typ in ("option_in", "claim_purchase", "property_purchase"):
        for m in _RETAINS.finditer(b_main[:8000]):
            o = _org_clean(m.group(1))
            o = re.sub(r"^(?:With|And|The|Where|Whereby|Which|While|Under|Pursuant|Each|Both|Such)\s+", "", o)
            o = re.sub(r"(?i)[,\s]+(?:Inc|Ltd|Corp|Corporation|Limited|LLC)\.?$", "", o).strip()
            if o and not self_rx.search(o) and not _ORG_BAD.match(o) and not re.search(
                    r"(?i)\b(?:vendors?|optionors?|owners?|holders?|prospectors?|company|corporation|issuer|seller|parties|party|"
                    r"they|he|she|it|who|which|this|that)\b", o) and len(o) > 2:
                return o            # FIX5 CP5: the vendor keeps the royalty ("Beta Or Corp. retains a 2% NSR")
        for s in _sentences(b_main[:6000]):
            for pos, o in _orgs_in(s, self_rx):
                if _HELD_BY.search(s[max(0, pos - 140):pos]):
                    return re.sub(r"(?i)[,\s]+(?:Inc|Ltd|Corp|Corporation|Limited|LLC)\.?$", "", o).strip() or None
    for s in _sentences(b_main[:6000]):
        orgs = _orgs_in(s, self_rx)
        for k, (pos, o) in enumerate(orgs):
            end = pos + len(o)
            before = s[max(0, pos - 90):pos]
            listed = re.search(r"(?:,|\band)\s*$", before) and any(pos - 90 < p2 < pos for p2, _ in orgs[:k])
            if listed:
                continue
            tail = s[end:end + 160]
            follow = re.match(r"(?:\s*(?:,|and)\s*\d{6,8}\s+\w+(?:\s+\w+)?\s+(?:Ltd|Inc|Corp)\.?|\s*(?:,|and)\s+[A-Z][\w.&'\u2019\- ]{2,40}?"
                              r"(?:Ltd|Inc|Corp|Corporation|Limited)\.?)+", tail)
            after = tail[follow.end():] if follow else tail
            if re.search(r"(?i)\b(?:recently|previously|already)\s+optioned\s+from\s+$|\b(?:contiguous|adjacent|adjoining|"
                                         r"next\s+to|near)\b[^.]{0,80}$", before):
                continue            # the ground next door, optioned earlier from X: not this deal's party
            if _ROLE_AFTER.search(after) or _ROLE_BEFORE.search(before):
                return re.sub(r"(?i)[,\s]+(?:Inc|Ltd|Corp|Corporation|Limited|LLC)\.?$", "", o).strip() or None
    return None


def _interest(ms, stage, typ):
    vals = []
    comp = []
    for m in ms:
        for x in _PCT_INT.finditer(m["s"]):
            v = float(x.group(1))
            if 0 < v <= 100:
                vals.append(v)
                if _COMP.search(m["s"]):
                    comp.append(v)
        for x in re.finditer(r"(?i)\b(?:acquire|earn|own|purchase)\s+(?:a\s+|an\s+)?(\d{1,3})\s*%\s+of\b", m["s"]):
            vals.append(float(x.group(1)))
    if stage == "completed" and comp:
        return comp[0]
    for m in ms:
        vs = [float(x.group(1)) for x in _PCT_INT.finditer(m["s"]) if 0 < float(x.group(1)) <= 100]
        if vs:
            up = [float(x.group(1)) for x in re.finditer(r"(?i)\bup\s+to\s+(?:an?\s+)?(?:\w+\s+)?(\d{1,3})\s*%", m["s"])]
            return up[0] if up else vs[0]
    if vals:
        return max(vals)
    if typ in ("staking",) or (typ in ("claim_purchase", "property_purchase") and stage in ("signed", "completed")):
        return 100.0
    return None


_CASH_TOTAL = re.compile(r"(?i)(?:total\s+consideration\s+of|cash\s+payments?\s+(?:totall?ing|in\s+the\s+aggregate\s+of|aggregating)|"
                         r"aggregate\s+cash\s+(?:payments?|consideration)\s+of|pay(?:ing)?\s+(?:the\s+\w+\s+)?(?:a\s+total|an\s+aggregate)\s+"
                         r"(?:cash\s+consideration\s+)?of|a\s+cash\s+payment\s+totall?ing|total\s+cash\s+consideration\s+of)\s*"
                         + _CUR_RX + _NUM + r"\s*(million|M|k)?\b")
_NEG_CTX = re.compile(r"(?i)\b(?:milestone|bonus|buy[\s-]?back|repurchase|purchase\s+(?:\d(?:\.\d+)?%|one|half)|reduce\s+the\s+royalty|"
                      r"private\s+placement|offering|financing|flow[\s-]through|units?\b|warrants?|proceeds|outstanding|consolidat|"
                      r"historical|incurred\s+\$[\d.,]+\s+million\s+in\s+exploration\s+expenditures\s+during|marketing|budget|debt|"
                      r"market\s+capitali[sz]ation|finder)")


def _best(rx, t, pos_rx=r"(?i)\b(?:total|aggregate|in\s+total|totall?ing)\b", neg=_NEG_CTX, before=60, after=40):
    best = None
    for m in rx.finditer(t):
        ctx_b = t[max(0, m.start() - before):m.start()]
        ctx_a = t[m.end():m.end() + after]
        sc = 0
        if re.search(pos_rx, ctx_b + " " + m.group(0)):
            sc += 2
        if neg.search(ctx_b[-45:] + " " + m.group(0) + " " + ctx_a):
            sc -= 4
        if best is None or sc > best[0]:
            best = (sc, m)
    return best[1] if best and best[0] > -2 else None


# FIX5 S1: clause words that mark shares (or money) as a fee, a loan or a financing, not deal consideration
_PAY_NEG_CL = re.compile(r"(?i)\bservices?\b|\bfinders?\b|\bfees?\b|\bconsult\w*|\bloan|\bowed|\bdebt|\bplacement|\bproceeds|\bfinancing")


_PART = re.compile(r"(?i)\b(?:initial|first|second|third|fourth|fifth|additional|further|remaining|balance|subsequent|next)\b|"
                   r"\b(?:later|earlier)\s+of\b|\bat\s+(?:the\s+)?(?:closing|signing|execution)\b|"
                   r"\bupon\s+(?:the\s+)?(?:execution|signing|closing|approval|receipt)|\bon\s+(?:the\s+)?(?:execution|signing|closing)|"
                   r"\banniversary|\bwithin\s+\w+|\bon\s+or\s+before|\bby\s+(?:the\s+)?(?:end|December|January|February|March|April|May|June|"
                   r"July|August|September|October|November|\d)|\bmonths?\s+(?:after|following|from)|\b(?:has|have)\s+already\s+paid|\balready\s+(?:been\s+)?paid")


_TRANCHE = re.compile(r"(?i)\b(?:initial|first|second|third|fourth|fifth|additional|further|remaining|balance|subsequent|next)\b|"
                      r"\bupon\s+(?:the\s+)?(?:execution|signing|closing|approval|receipt)|\bon\s+(?:the\s+)?(?:execution|signing|closing)|"
                      r"\banniversary|\bmonths?\s+(?:after|following|from)")




# FIX5 S1: the shares to be issued, as a total the release states ("an aggregate of 4,000,000 shares") or the issues of
# a schedule summed; never shares of a placement, warrants or options, a finder's shares or a milestone bonus.
_SHARE_N = re.compile(r"(?i)\b(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(million|(?-i:M))?\s+(?:of\s+(?:its|the\s+Company['\u2019]s)\s+)?"
                      r"(?:(?-i:[A-Z])[\w\-]*\s+){0,2}?(?:fully\s+paid\s+)?(?:common\s+|ordinary\s+|consideration\s+|class\s+a\s+)?s\s?hares\b")
_SH_CUE = re.compile(r"(?i)\b(?:issu\w*|deliver\w*|allot\w*)\b(?:(?!\d{3})[^.;:])*$|\b(?:cash|\$\s?[\d,.]+\s*(?:million|M)?)\s*(?:cash\s+)?(?:payments?\s+)?(?:and|plus|,)\s+$|"
                     r"\bshares\b[^.;]{0,60}\b(?:and|plus)\s+(?:an?\s+)?(?:additional|further)?\s*$")
_SH_NEG = re.compile(r"(?i)\bplacement|\bunits?\b|\bwarrants?|\bstock\s+options?|\bincentive|\boutstanding|\bfinder|\bconsolidat|\bflow[\s-]?through|"
                     r"\bbonus|\bmilestone|\bresource\b|\bfeasibility|\bcommercial\s+production|\bdiscovery|\bsubscri|\bheld\s+by|\bholds?\b|"
                     r"\bowns?\b|\b(?:acquire|purchase|bought|sell|sold)\b|\bprivate|\bdebt|\bsettle|\bexchange\s+for\s+each|\bper\s+share|"
                     r"\bservices?\b|\bfees?\b|\bconsult")
_SH_TOTAL = re.compile(r"(?i)\b(?:aggregate|total|totall?ing|cumulative)\b(?:(?!\bshares\b)(?:[^.;]|\.(?=\d)))*$")


def _digits(t):
    """FIX5: numbers broken by a PDF line ('1,00 0,000', '15 0,000', '$ 10 ,000') are one number again."""
    t = re.sub(r"\b(\d{1,3}),(\d{2}) (\d),(\d{3})\b", r"\1,\2\3,\4", t)
    t = re.sub(r"\b(\d{1,3}),(\d) (\d{2}),(\d{3})\b", r"\1,\2\3,\4", t)
    t = re.sub(r"\b(\d{1,2}) (\d),(\d{3})\b(?=\s+(?:\w+\s+){0,2}shares)", r"\1\2,\3", t)
    return re.sub(r"(\$\s?\d{1,3}) ,(\d{3})\b", r"\1,\2", t)


def _sh_clause(t, i, n=90):
    b4 = re.sub(r"\([^()]*\)", " ", t[max(0, i - n - 40):i])
    b4 = re.split(r"[;:]\s|\.\s|\s[-\u2022]\s|\s\(?(?:[ivx]{1,4}|[a-h1-9])\)\s", b4)[-1][-n:]
    seg = t[max(0, i - 250):i]
    k = seg.rfind(":")
    if k >= 0 and re.search(r"[\u2022\u25aa\u25cf]|\s[-*]\s|\(\w{1,3}\)", seg[k + 1:]) and not re.search(r"\.\s", seg[k + 1:]):
        b4 = seg[:k][-80:] + " : " + b4     # an item of a list: the list's head ("aggregate consideration consisting of:")
    return b4


_SH_NEG_AF = re.compile(r"(?i)^[^.;]{0,50}?(?:\breleased?\b|\bescrow|\bresale|\bwarrants?\b|\bunits?\b|\bplacement|\bfinder|\boutstanding|\bbonus|\bmilestone|\bresource\b|"
                        r"\bfeasibility|\bcommercial\s+production|\bheld\s+by|\bflow[\s-]?through)")


_SH_COND = re.compile(r"(?i)\badjust\w*|\bprovided\s+that|\bin\s+the\s+event|\bif\b|\bshould\b|\breleased?\b|\bescrow|\bresale|\bhold\s+period|"
                      r"\block[\s-]?up")
_SH_MILE = re.compile(r"\bresources?\b|\bounces\b|\b[Ff]easibility|\bcommercial\s+production|\bdiscovery|\b[Mm]ilestone|\bbonus|\bPEA\b|"
                      r"\bpreliminary\s+economic|\bproduction\s+decision")


_SH_OVER = re.compile(r"(?i)\s*(?:(?:of|in)\s+(?:the\s+)?(?:capital\s+of\s+)?[\w\-]+\s+)?(?:to\s+(?:the\s+)?[\w\-]+\s+)?over\s+(?:a\s+period\s+of\s+|"
                      r"the\s+(?:next\s+|initial\s+|first\s+)?|an?\s+)?(?:\w+|\d+)[\s-]*(?:\(\d+\)\s*)?(?:years?|months?)\b")


def _share_sum(t):
    """FIX5 S1: (count, kind) of the shares the deal issues: a stated total, else the whole followed by its tranches,
    else the issues of a schedule summed; (0, 'part') when only a part is stated; None when none or when several
    separate issues cannot be told apart."""
    vals = []
    for m in _SHARE_N.finditer(t):
        b4 = _sh_clause(t, m.start())
        af = re.split(r"[;.]\s", re.sub(r"\([^()]*\)", " ", t[m.end():m.end() + 90]))[0]
        if not (_SH_CUE.search(b4) or re.search(r"(?i)\b(?:consideration|consisting\s+of|maximum\s+of)\b", b4) or
                re.match(r"(?i)\s*(?:to|in\s+favou?r\s+of)\s+(?:the\s+)?(?:optionors?|vendors?|owners?|holders?|(?-i:[A-Z]))|"
                         r"\s*(?:of\s+(?:the\s+Company|(?-i:[A-Z])\w*)\s+)?(?:will|shall|are\s+to|to)\s+be\s+issued", af)):
            continue
        b4n = re.split(r",\s|\sand\s", b4)[-1]
        if _SH_NEG.search(b4n[-50:]) or _SH_NEG_AF.search(af) or _PAY_NEG_CL.search(b4) or _SH_COND.search(b4n) or _SH_MILE.search(b4):
            continue
        v = _amt(m.group(1), m.group(2))
        if v < 1000:
            continue
        tot = bool(_SH_TOTAL.search(b4) or re.search(r"(?i)\bmaximum\s+of\s+$", b4) or _SH_OVER.match(af))
        ctx = b4n[-45:] + ("" if tot else " " + af[:50])
        vals.append((v, bool(_PART.search(ctx)), tot, bool(_TRANCHE.search(ctx))))
    if not vals:
        return None
    tots = [v for v, p, tt, _k in vals if tt and not p]
    if tots:
        return tots[0], "total"
    if any(tt and p for v, p, tt, _k in vals):
        return 0, "part"
    if len(vals) > 1 and abs(vals[0][0] - sum(x[0] for x in vals[1:])) <= 0.02 * vals[0][0] and not vals[0][1]:
        return vals[0][0], "total"  # the whole, then its tranches
    tr = [x[0] for x in vals if x[1]]
    last_tr = max((i for i, x in enumerate(vals) if x[1]), default=-1)
    whole = []
    for i, x in enumerate(vals):
        if not x[1] and x[0] not in whole and not (i > last_tr and x[0] in tr):    # a tranche restated after the schedule
            whole.append(x[0])
    if len(whole) > 1:
        return None                 # several separate issues: which is the deal's cannot be told
    if whole and tr:
        w, st = whole[0], sum(tr)
        return (w if w >= st * 0.98 or abs(w - sum(set(tr))) <= 0.02 * w else w + st), "sum"
    if whole:
        return whole[0], "one"
    if len(tr) > 1:
        return sum(tr), "sum"
    if len(vals) == 1 and not vals[0][3]:
        return vals[0][0], "one"
    return None


_SCALE = r"(?:\s*-?\s*(?i:(million|mm|m|thousand|k|billion))\b)?"
# FIX5 r2 N1: only a cash total the release states in so many words
_CASH_STATED = re.compile(
    r"(?i)\b(?:(?:aggregate|total)\s+(?:of\s+)?(?:\w+\s+){0,2}?cash\s+(?:payments?|consideration)\s+(?:of|totall?ing|amounting\s+to)\s+(?:up\s+to\s+)?|"
    r"cash\s+payments?\s+(?:(?!\$)[^.;:\d$]){0,40}?\b(?:tota\s?ll?ing|aggregating|in\s+the\s+aggregate\s+of|of\s+an\s+aggregate\s+of|of\s+a\s+total\s+of)\s+(?:up\s+to\s+)?|"
    r"(?:a\s+total|an\s+aggregate)\s+of\s+(?=(?:(?:C|CA|CDN|US|A|AU|AUD|CAD|USD)\s?)?\$\s?[\d,.]+" + r"(?:\s*-?\s*(?:million|m)\b)?\s+(?:in\s+)?cash\b))"
    + _CUR_RX + _NUM + _SCALE)


def _cash_stated(t):
    """FIX5 r2 N1: (amount, currency) of an explicitly stated aggregate / total of cash payments, or None. Not a part
    ("additional", "further", "remaining", "balance" before it in the sentence) and not a buy-back or royalty price."""
    for m in _CASH_STATED.finditer(t):
        sent = re.split(r"\.\s", t[max(0, m.start() - 150):m.start()])[-1]
        if re.search(r"(?i)\b(?:additional|further|remaining|balance|subsequent)\b", sent) or \
                re.search(r"(?i)\bbuy[\s-]?(?:back|down)|\brepurchas|\broyalt|\bNSR\b|\bmilestone|\bbonus", sent[-80:]):
            continue
        v = _amt(m.group(2), m.group(3))
        if 100 <= v <= 5e9:
            return v, _curr(m.group(1))
    return None


def _terms(t, typ):
    out = {"cash": None, "currency": None, "shares": None, "work": None, "nsr": None, "term": None, "area": None}
    m = _best(_CASH_TOTAL, t) or _best(_CASH, t) or _best(_CASH2, t)
    if m:
        g = [x for x in m.groups()]
        out["cash"] = _amt(g[1], g[2])
        out["currency"] = _curr(g[0])
        if out["cash"] > 5e9:       # "US$13,165,677 million": a typo, not a price
            out["cash"] = out["currency"] = None
    st = _cash_stated(t)            # FIX5 r2: a cash total the release states in so many words wins
    if st:
        out["cash"], out["currency"] = st
    ss = _share_sum(_digits(t))     # FIX5 S1: the shares' stated total, or the issues summed
    if ss and ss[1] != "part" and ss[0] <= 5e9:
        out["shares"] = ss[0]
    m = _best(_WORK, t)
    if m:
        g = [x for x in m.groups() if x is not None]
        nums = [x for x in g if re.match(r"^[\d,.]+$", x)]
        mult = next((x for x in g if x.lower() in ("million", "m", "k")), None)
        if nums:
            out["work"] = _amt(nums[0], mult)
    m = _best(_NSR, t, pos_rx=r"(?i)\b(?:grant|retain|subject\s+to)", neg=re.compile(r"(?i)\bconvert|dilut|buy[\s-]?back\s+(?:of\s+)?\d"))
    if m:
        out["nsr"] = float(m.group(1) or m.group(2))
    m = _TERMLEN.search(t)
    if m:
        n, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3) or m.group(4), "year")
        n = _WORDN.get(n.lower(), None) if not n.isdigit() else int(n)
        if n:
            out["term"] = round(n / 12.0, 2) if unit.lower().startswith("month") else float(n)
    pos_area = r"(?i)\b(?:stak\w*|new\s+claims|additional|adds?|covering|comprised\s+of|consists?\s+of|comprising|encompassing|of\s+mineral\s+claims)\b"
    neg_area = re.compile(r"(?i)\bnow\s+(?:comprises|covers|totals)|mining\s+district|\bdistrict\b|total\s+(?:project\s+)?tenure|"
                          r"increasing\s+the\s+total|portfolio|footprint|from\s+the\s+original|to\s+now\s+more\s+than")
    m = _best(_AREA, t, pos_rx=pos_area, neg=neg_area, before=80, after=30)
    if m:
        v = _num_of(m.group(1))
        out["area"] = round(v * 100 if re.match(r"(?i)km|square", m.group(2)) else v)
    return out


# ------------------------------------------------------------------ records
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["rows"]:
        return [F.Record(KIND, facts=[F.Fact("is_deal", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"] or "none")], confidence=0.0)]
    out = []
    for r in a["rows"]:
        fs = [F.Fact("is_deal", value_num=1.0)]
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
            if field_ == "is_deal":
                yes = num == 1.0
            elif field_ in TXT_FIELDS:
                r[field_] = text
            elif field_ in NUM_FIELDS:
                r[field_] = num
        if yes and r["deal_type"]:
            rows.append(r)
    return {"is_deal": bool(rows), "rows": rows}


JUDGED = ("deal_type", "stage", "property", "counterparty", "interest_pct", "cash", "shares", "work", "nsr", "term", "area")


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

    fill = " The property is road accessible and hosts several gold showings along a regional structure." * 3
    lead = "Vancouver, British Columbia, March 2, 2026 -- ABC Gold Corp. (TSXV: ABC) (\"ABC\" or the \"Company\") "

    def rows(h, b, keys=("deal_type", "stage", "property", "counterparty", "interest_pct")):
        return [tuple(r[k] for k in keys) for r in analyse(h, lead + b + fill)["rows"]]

    eq("option in, with terms",
       rows("ABC Gold Signs Option to Acquire Alpha Property",
            "is pleased to announce that it has entered into an option agreement with Beta Minerals Inc. (\"Beta\") pursuant "
            "to which the Company may acquire a 100% interest in the Alpha Property in Ontario by making cash payments "
            "totalling $250,000, issuing 2,000,000 common shares and incurring $1,500,000 in exploration expenditures over "
            "four years. Beta will retain a 2% NSR royalty.",
            ("deal_type", "stage", "property", "counterparty", "interest_pct", "cash", "shares", "work", "nsr", "term")),
       [("option_in", "signed", "Alpha Property", "Beta Minerals", 100.0, 250000.0, 2000000.0, 1500000.0, 2.0, 4.0)])
    eq("option out, 'Corp. (\"Delta\")' does not end the sentence",
       rows("ABC Gold Options Kappa Property to Delta Metals",
            "has entered into an option agreement with Delta Metals Corp. (\"Delta\") whereby Delta may earn up to a 70% "
            "interest in the Kappa Property by incurring $3,000,000 in exploration expenditures over five years."),
       [("option_out", "signed", "Kappa Property", "Delta Metals", 70.0)])
    eq("staking, with area",
       rows("ABC Gold Stakes New Claims at Gamma Lake",
            "has staked 45 mineral claims covering 2,300 hectares at its Gamma Lake Property in Quebec.",
            ("deal_type", "stage", "property", "counterparty", "area")),
       [("staking", "signed", "Gamma Lake Property", None, 2300)])
    eq("option exercised",
       rows("ABC Gold Exercises Option on Alpha Property",
            "announces that it has exercised its option and now holds a 100% interest in the Alpha Property, having "
            "completed all cash payments and share issuances under the option agreement with Beta Minerals Inc."),
       [("option_in", "completed", "Alpha Property", "Beta Minerals", 100.0)])
    eq("option terminated",
       rows("ABC Gold Terminates Option on Omega Property",
            "has terminated its option agreement with Zeta Resources Ltd. on the Omega Property and returned the property "
            "to Zeta."),
       [("option_in", "terminated", "Omega Property", "Zeta Resources", None)])
    eq("LOI is proposed",
       rows("ABC Gold Signs LOI to Acquire Sigma Property",
            "has signed a non-binding letter of intent with Theta Mining Ltd. to acquire a 100% interest in the Sigma "
            "Property for $500,000 in cash."),
       [("property_purchase", "proposed", "Sigma Property", "Theta Mining", 100.0)])
    eq("option amended",
       rows("ABC Gold Amends Option Agreement for Alpha Property",
            "has amended its option agreement with Beta Minerals Inc. on the Alpha Property to extend the deadline for the "
            "final cash payment by twelve months."),
       [("option_in", "amended", "Alpha Property", "Beta Minerals", None)])
    eq("claim purchase completed",
       rows("ABC Gold Completes Acquisition of Tau Claims",
            "has completed the purchase of the Tau Claims from an arm's length vendor for $25,000 cash and 250,000 common "
            "shares.", ("deal_type", "stage", "property", "counterparty", "interest_pct", "cash", "shares")),
       [("claim_purchase", "completed", "Tau Claims", None, 100.0, 25000.0, 250000.0)])
    eq("property sale, buyer after 'to'",
       rows("ABC Gold Sells Rho Property to Pi Metals",
            "has sold its Rho Property to Pi Metals Inc. for $1,000,000 in cash."),
       [("property_sale", "completed", "Rho Property", "Pi Metals", None)])     # 1.0.8: "has sold" is a completed sale
    eq("stock options are not a deal",
       rows("ABC Gold Grants Stock Options",
            "has granted incentive stock options to purchase up to 500,000 common shares to directors and officers at an "
            "exercise price of $0.20."), [])
    eq("placement is not a deal", rows("ABC Gold Closes Private Placement", "has closed a private placement of 5,000,000 "
                                                                            "units."), [])
    recs = extract("ABC Gold Exercises Option on Alpha Property",
                   lead + "has exercised its option and now holds a 100% interest in the Alpha Property under the option "
                          "agreement with Beta Minerals Inc." + fill)
    p = to_prediction(recs)
    eq("round trip", [(x["deal_type"], x["stage"], x["property"], x["interest_pct"]) for x in p["rows"]],
       [("option_in", "completed", "Alpha Property", 100.0)])
    eq("no-deal record", to_prediction(extract("ABC Gold Closes Private Placement",
                                               lead + "has closed a private placement." + fill)), None)
    # OPT_V1b (2026-09-23): found by hand-grading 95 releases of corpus run c1
    eq("granted the other side the option -> option out",
       rows("ABC Gold Announces Closing of Option Agreement with Zeta Silver for Non-Core Properties",
            "is pleased to announce it has completed the previously announced option agreement with Zeta Silver Corp. As "
            "announced, the Company has granted Zeta the option to acquire a 100% interest in its Omega Property.")[0][:2],
       ("option_out", "signed"))
    eq("a release about something else does not report a deal in passing",
       rows("ABC Gold Intersects 12 m of 5 g/t Au at Alpha", "reports drill results. The Company is focused on the acquisition "
            "and exploration of gold properties. In 2021 it acquired the Beta Property from Delta Resources Ltd."), [])
    eq("'If the Company exercises the Option' is a term, not an event",
       rows("ABC Gold Executes Option Agreement to Acquire Alpha Property",
            "has entered into an option agreement with Beta Minerals Inc. to acquire a 100% interest in the Alpha Property. "
            "If the Company exercises the Option, it will grant Beta a 2% NSR royalty.")[0][:2], ("option_in", "signed"))
    eq("claims acquired by staking are staking",
       rows("ABC Gold Acquires Additional Mineral Claims at Alpha Project",
            "recently acquired through staking an additional 35 square kilometres at the Alpha Project.")[0][:2],
       ("staking", "signed"))
    eq("an option over a company's shares is not a land deal",
       rows("ABC Gold Enters Into Option Agreement", "has entered into an option agreement pursuant to which the shareholders of "
            "XYZ Technologies Inc. grant the Company an option to acquire the remaining 50% of the outstanding shares of XYZ and "
            "its Intellectual Property."), [])
    eq("'Silver Lake' keeps its first word", _name("Silver Lake", "Property"), "Silver Lake Property")
    eq("'Rare One' keeps its first word (OPT_V1f)", _name("Rare One", "Project"), "Rare One Project")
    eq("'Silver Park' keeps its first word (OPT_V1f)", _name("Silver Park", "Claims"), "Silver Park Claims")
    eq("'Key' is an adjective before a longer name (OPT_V1f)", _name("SECURES KEY SOUTH PRESTON URANIUM", "PROPERTY"),
       "South Preston Property")
    eq("'Key' before a short name is an adjective too (OPT_V1f)", _name("Acquires Key Swanson", "Claim"), "Swanson Claim")
    eq("region-only name with a capitalised suffix (OPT_V1f)", (_name("Options Texas", "Property"), _name("its Texas", "property")),
       ("Texas Property", None))
    eq("a list is not a name (OPT_V1f)", _name("NV Quito Gold Lander NV America", "Mine"), None)
    eq("two names joined are two names, not a list (OPT_V1f)", _name("Green Vein Mesa and Wheal Anne", "Claims"),
       "Green Vein Mesa and Wheal Anne Claims")
    eq("drill-ready, ounces, financing (OPT_V1f)", (_name("Drill Ready Solar Lithium", "Project"),
       _name("Historical 877,000 Oz Gold N2", "Property"), _name("Closing of Equity Financing", "Claims")),
       ("Solar Project", "N2 Property", None))
    eq("'Major Drill Ready' is not a name; a deposit type is not a word of the name (OPT_V1f)",
       (_name("Major Drill Ready Nevada Lithium", "Project"), _name("Canoe Landing Lake East VMS", "Projects")),
       (None, "Canoe Landing Lake East VMS Projects"))
    eq("'Nine Mile' keeps its number (OPT_V1f)", _name("Nine Mile Brook", "Project"), "Nine Mile Brook Project")
    eq("'&' names reach back one word (OPT_V1f)", [p for _q, p in _props_in("100% Interest in the True Grit & Middle Ridge North Gold "
       "Properties")], ["True Grit & Middle Ridge North Properties"])
    eq("letters only (OPT_V1f)", _name("N WT LITHIUM", "PROPERTIES"), None)
    eq("quoted name (OPT_V1f)", _unq("the 'Goose' Gold Project; Kinross' Great Bear"), "the  Goose  Gold Project; Kinross' Great Bear")
    eq("'&' joins two names, not two metals (OPT_V1f)", ([p for _q, p in _props_in("Homeland Grows Coyote Basin & Red Wash Properties")],
       [p for _q, p in _props_in("TO ACQUIRE SIGNFICANT GOLD & SILVER PROPERTY")]),
       (["Coyote Basin & Red Wash Properties"], []))
    eq("'the X Mines', not a company (OPT_V1f)", [p for _q, p in _props_in("earn 100% in the Prospector & Freedom Uranium Mines in "
       "Utah with Denison Mines Corp.")], ["Prospector & Freedom Mines"])
    # OPT_V1c (2026-09-23): found by hand-grading the fresh sample of corpus run c2
    eq("'Two B.C. Properties' is one sentence",
       rows("ABC Gold Announces Definitive Agreement on Option to Acquire Two B.C. Properties",
            "is pleased to announce it has signed a definitive agreement for the option.")[0][:2], ("option_in", "signed"))
    eq("granted X a three-year option -> option out",
       rows("ABC Gold Receives First Payment of Option Agreement",
            "is pleased to announce that it has received the first payment under the option agreement with Kappa Metals Corp. "
            "Pursuant to the Agreement, ABC granted Kappa a three-year option to acquire a 100% interest in the Omega Project.")[0][:2],
       ("option_out", "payment"))
    eq("passive staking in an 'expands land position' release",
       rows("ABC Gold Expands Land Position at Alpha by 26%", "reports new targets at Alpha. New Targets and Claims: ninety-five "
            "claims covering 1,985 hectares were recently staked.")[0][:2], ("staking", "signed"))
    eq("'increases land holdings' by a purchase is a purchase",
       rows("ABC Gold Increases Land Holdings in Brazil by 700%", "has entered into a mineral claims purchase agreement with "
            "Talisman Ltd. to acquire 12 exploration permits.")[0][:1], ("claim_purchase",))
    eq("a sale headline is a sale", rows("ABC Gold Announces Sale of Non-Core Omega Property",
                                          "is pleased to announce the sale of its 51% interest in the Omega Property to Zeta "
                                          "Phosphate Ltd. Zeta will have the option to pay in shares.")[0][:1], ("property_sale",))
    eq("buying a company's shares is not a land deal",
       rows("ABC Gold Acquires Securities of XYZ Technologies Inc.", "has acquired 1,500,000 common shares of XYZ Technologies "
            "Inc. The Company is focused on the acquisition of gold properties."), [])
    # OPT_V1d (corpus run c3)
    eq("'Closes Option Agreement' starts the option",
       rows("ABC Gold Closes Option Agreement on Zeta Property", "is pleased to announce that it has closed the option agreement "
            "with Iota Resources Ltd. under which the Company may acquire a 100% interest in the Zeta Property.")[0][:2],
       ("option_in", "signed"))
    eq("'Closes Sale of' is a completed sale",
       rows("ABC Gold Closes Sale of Omega Project", "is pleased to announce that it has closed the sale of its Omega Project to "
            "Sigma Metals Inc. for $500,000 in cash.")[0][:2], ("property_sale", "completed"))
    eq("a final payment for an acquisition completes it",
       rows("ABC Gold Makes Final Payment for Acquisition of Rho Project", "reports that it has paid the final $100,000 to Upsilon "
            "Mining LLC under the purchase agreement for the Rho Project.")[0][:2], ("property_purchase", "completed"))
    eq("the thing bought decides claim vs property",
       rows("ABC Gold Expands Tau Property", "is pleased to announce it has expanded its Tau property by acquiring the Tau East "
            "claims from a private vendor for $5,000.")[0][:1], ("claim_purchase",))
    eq("'giving X the right to acquire' is option out",
       rows("ABC Gold Enters Earn-in Agreement on Psi Property", "has entered into an earn-in agreement with Omega Metals Corp. "
            "(\"Omega\") giving Omega the right to acquire up to a 75% interest in the Psi Property.")[0][:2], ("option_out", "signed"))
    eq("congratulating another company is not a deal",
       rows("ABC Gold Congratulates Chi Metals on Option of Phi Property", "congratulates Chi Metals Inc. on its agreement to "
            "option the Phi Property, in which ABC holds shares."), [])
    eq("acquiring data is not a land deal",
       rows("ABC Gold Acquires Data and Updates Model for Mu Copper Project", "has acquired historical drill data for the Mu "
            "Copper Project and updated its geological model."), [])
    eq("an application to acquire mineral rights is staking",
       rows("ABC Gold Increases Land Position in Brazil", "is pleased to announce that it has made application to acquire the "
            "mineral rights for an additional 7,865 hectares in Piaui, Brazil.")[0][:1], ("staking",))
    eq("'the Company's SEDAR profile' is not a direction cue",
       rows("ABC Gold Signs Option Agreement on Nubia Property", "has entered into an option agreement with Xi Resources Inc. to "
            "acquire up to 90% of the Nubia Property. A copy of the Option Agreement is available on the Company's SEDAR "
            "profile.")[0][:1], ("option_in",))
    ld2 = "Montreal, April 1, 2026 - Kappa Strategic Minerals Corporation (TSXV: KSM) (\"Kappa Strategic\" or the \"Corporation\") "
    eq("the issuer's ticker names the issuer",
       [r["deal_type"] for r in analyse("Kappa Strategic Minerals Announces Option Agreement in Morocco", ld2 + "is pleased to "
                                        "announce that it has entered into an option agreement with Nu Groupe Inc., pursuant to "
                                        "which KSM has been granted an exclusive option to acquire up to an 80% interest in the "
                                        "Lambda Mine." + fill)["rows"]], ["option_in"])
    # 1.0.5: jurisdiction (the Permits reader's rule) and names cut short at a landform
    eq("jurisdiction: located in",
       [r["jurisdiction"] for r in analyse("ABC Gold Signs Option to Acquire Alpha Property", lead + "is pleased to announce "
                                           "that it has entered into an option agreement to acquire a 100% interest in the "
                                           "Alpha Property located in the Red Lake district of Ontario." + fill)["rows"]],
       ["Ontario, Canada"])
    eq("jurisdiction: the dateline does not count",
       [r["jurisdiction"] for r in analyse("ABC Gold Stakes Beta Claims", lead + "has staked 20 claims forming the Beta "
                                           "Property." + fill)["rows"]], [None])
    eq("jurisdiction: one deal among several reads its own sentences",
       sorted((r["property"], r["jurisdiction"]) for r in analyse(
           "ABC Gold Signs Two Option Agreements", lead + "is pleased to announce that it has entered into an option "
           "agreement with Delta Metals Corp. (\"Delta\") whereby the Company may acquire a 100% interest in the Kappa "
           "Property located in Nevada by paying $100,000. The Company has also entered into a separate option agreement "
           "with Omega Minerals Inc. (\"Omega\") whereby the Company may acquire a 100% interest in the Lambda Property "
           "located in Quebec by paying $50,000." + fill)["rows"]),
       [("Kappa Property", "Nevada, USA"), ("Lambda Property", "Quebec, Canada")])
    eq("a stripped qualifier comes back before a landform",
       [O for _p, O in _props_in("Titan Mining Announces Option to Earn up to 100% in the Mineral Ridge Gold Project")] +
       [O for _p, O in _props_in("Orogen Royalties Signs LOI to Option Table Mountain Gold Project to Toogood Gold")] +
       [O for _p, O in _props_in("Canamera Options Rare Earth Ridge REE-Niobium Project")] +
       [O for _p, O in _props_in("AMV CAPITAL CORPORATION SIGNS DEFINITIVE AGREEMENT TO ACQUIRE KEY LAKE SOUTH URANIUM PROJECT")],
       ["Mineral Ridge Project", "Table Mountain Project", "Rare Earth Ridge REE-Niobium Project",
        "Key Lake South Project"])
    eq("a possessive and a word outside the capture come back",
       [O for _p, O in _props_in("Vulcan Minerals Inc. \u2013 Options Voisey\u2019s Bay South Claims to Fjordland Exploration Inc.")] +
       [O for _p, O in _props_in("Eagle Plains Executes Option Agreement with Canter on Schott\u2019s Lake Copper Project")] +
       [O for _p, O in _props_in("Sienna Acquires the \"Case Lake West Cesium and Spodumene Pegmatite Project\" in Ontario")],
       ["Voisey's Bay South Claims", "Schott's Lake Copper Project",
        "Case Lake West Cesium and Spodumene Pegmatite Project"])
    eq("a landform that starts a real name stays alone",
       [O for _p, O in _props_in("to acquire 100% of the Lake Cargelligo Gold Project")] +
       [O for _p, O in _props_in("our 100% owned River Valley Project, located in the Sudbury district")] +
       [O for _p, O in _props_in("IsoEnergy Acquires Mountain Lake Uranium Deposit")],
       ["Lake Cargelligo Project", "River Valley Project", "Mountain Lake Deposit"])
    eq("a verb is not a qualifier; a bracket that lost its end goes",
       ([O for _p, O in _props_in("Noble Agrees to Sell Island Pond Claims to Benton Resources Inc.")],
        _name("Jonathan's Pond (JP", "Project")), (["Island Pond Claims"], "Jonathan's Pond Project"))
    eq("a company's name is not a qualifier",
       (_geo_back("Toogood Gold Lake".split(), 2), _geo_back("of Iron Lake".split(), 2),
        _geo_back("Hazeur, Lake".split(), 1, loose=True), _geo_back("of Monster Lake".split(), 2, loose=True)),
       ([], ["Iron"], [], ["Monster"]))
    # 1.0.7 (2026-09-30): the error kinds of the outside-tag and in-tag samples
    eq("not ground: a royalty sale, water rights, a stream, a stake in a company",
       (rows("ABC Gold Closes Sale of Zeta Royalty", "has closed the sale of its 2% NSR royalty on the Zeta Project to Omega Royalties "
             "Inc. for $1,000,000."),
        rows("ABC Gold Enters Into Water Rights Purchase and Sale Agreement in Alpha Valley", "has entered into a water rights purchase "
             "and sale agreement to buy a groundwater permit for its Alpha Project for $2,000,000."),
        rows("ABC Gold Signs Binding LOI with Kappa Mining for a Silver Stream", "has signed a binding letter of intent with Kappa Mining "
             "Corp. in respect of acquiring a silver stream for US$6 million and an option to purchase subsequent silver produced from "
             "the Kappa mine."),
        rows("ABC Gold Acquires 40% Interest in Kappa Mines Inc.", "has acquired a 40% interest in Kappa Mines Inc., a private company "
             "that holds the Lambda Project, for 2,000,000 shares.")), ([], [], [], []))
    eq("company-level deals: a merger, an amalgamation that brings a mine",
       (rows("ABC Gold Enters Binding Letter of Intent to Merge With Delta Metals Corp.", "has entered into a binding letter of intent for "
             "a merger under which ABC would acquire all of the issued and outstanding shares of Delta Metals Corp. pursuant to a plan "
             "of arrangement. ABC has earned a 75% interest in the Omega Property under an option agreement with Delta."),
        rows("ABC Gold Announces Agreement to Acquire Nuovo Silver and the Kappa Mine", "has entered into a binding letter providing for "
             "the acquisition of Nuovo Silver Inc. by way of a three-cornered amalgamation. Nuovo Silver recently agreed to acquire "
             "100% of the producing Kappa Mine.")), ([], []))
    eq("no land deal: a partner's work, a right of first refusal, an intention to sell, a licence application on held "
       "ground, a mapped footprint",
       (rows("ABC Gold Option Partner Drills 20 Metres of 3 g/t Gold at Alpha", "reports that its option partner Delta Metals Corp. "
             "has completed a drill program on the Alpha Property."),
        rows("ABC Gold Announces Acquisition of a Right of First Refusal Over B.C. Claims", "has acquired a right of first refusal "
             "over mineral claims held by a consultant."),
        rows("ABC Gold Announces its Intention to Sell its Omega Property Interest", "has entered into an agreement allowing Kappa "
             "Metals Corp. to explore opportunities to dispose of its interest in the Omega Project."),
        rows("ABC Gold Files Exploitation Licence Application for the Alpha Project", "has filed an exploitation licence application "
             "for its wholly owned Alpha Project."),
        rows("ABC Gold Expands the Footprint to 650 Metres Strike at Alpha", "reports new mapping results that expand the "
             "mineralized footprint at the Alpha Project.")), ([], [], [], [], []))
    eq("background: an earlier deal restated with its release; an acquisition dated years back",
       (rows("ABC Gold Starts 2026 Exploration Program at Alpha Project", "has started its exploration program. The Company entered "
             "into an option agreement for the Alpha Project, whereby it can acquire a 70% interest (see News Release dated June 11, "
             "2025)."),
        rows("ABC Gold and Kappa Nation Announce Letter of Intent", "is pleased to announce a letter of intent with the Kappa Nation. "
             "Since acquiring the Alpha project in 2014, we have prioritized our relationship with the Kappa Nation.")), ([], []))
    eq("'option' as a payment choice",
       rows("ABC Gold Announces Closing of Rho Sale to Pi Metals", "announces that it has closed the previously announced sale of "
            "the Rho Project to Pi Metals Inc. Pi has the option to defer 50% of the deferred consideration."),
       [("property_sale", "completed", "Rho", "Pi Metals", None)])
    eq("the property is the deal's, not the other news's",
       rows("ABC Gold Files Resource Estimate for Alpha Project, Completes Acquisition of Beta Claims", "has filed a technical report "
            "on the resource estimate for its Alpha Project. The Company has acquired the Beta Claims from Kappa Resources Ltd. for "
            "100,000 shares."), [("claim_purchase", "completed", "Beta Claims", "Kappa Resources", 100.0)])
    eq("headline words are not a name; a count of properties is named in the body",
       (rows("ABC Gold Stakes Third Hard-Rock Lithium Project in Wyoming: the Freedom Project", "has staked 40 lode claims forming its "
             "third hard-rock lithium project, the Freedom Project, in Wyoming."),
        rows("ABC Gold Acquires Two New Toodoggone Projects", "has entered into a property sale agreement with Kappa Resources Ltd. "
             "whereby ABC will purchase a 100% interest in the Saunders (\"Saunders\") and Nub (\"Nub\") projects. The acquisition of "
             "the Saunders and Nub projects strengthens our position in the Toodoggone District.")),
       ([("staking", "signed", "Freedom", None, 100.0)], [("property_purchase", "signed", "Saunders and Nub", "Kappa Resources", 100.0)]))
    eq("a name with no Property word: 'X Option Agreement', 'Interest in X'",
       (rows("ABC Gold Renegotiates Rubi-Esperanza Cash and Option Agreement", "has signed a second addendum to the option agreement "
             "for the Rubi-Esperanza property to defer the final payment by twelve months."),
        rows("ABC Gold Announces the Sale of its 20% Interest in Hod Maden", "has entered into a definitive agreement with Lidya Mines "
             "to sell its 20% interest in the Hod Maden project."),
        rows("ABC Gold Provides Supplemental Disclosure Related to BullRun Option Agreement", "has entered into an option agreement "
             "with BullRun Capital Inc. to acquire a 100% interest in the Monarch Property.")),
       ([("option_in", "amended", "Rubi-Esperanza Property", None, None)], [("property_sale", "signed", "Hod Maden", "Lidya Mines", 20.0)],
        [("option_in", "signed", "Monarch Property", "BullRun Capital", 100.0)]))
    eq("stage: a termination written as a condition; 'has acquired'; 'Completes Sale'; 'Extension of LOI'; licences granted",
       (rows("ABC Gold Signs Option to Acquire Alpha Property", "has entered into an option agreement with Beta Minerals Inc. whereby "
             "the Company may earn a 49% interest in the Alpha Property. If the Company decides not to proceed with the acquisition of "
             "the further 51%, Beta may buy back the interest.")[0][1],
        rows("ABC Gold Acquires Wilson Claims", "is pleased to announce that it has acquired the Wilson Claims through a purchase and "
             "sale agreement with a private vendor for $1,000 and 10,000 common shares.")[0][:2],
        rows("ABC Gold Completes Sale to Pi Metals", "has sold its Rho Property to Pi Metals Inc. for $60,000 and 1,000,000 Pi "
             "shares.")[0][:2],
        rows("ABC Gold Announces Extension of LOI", "announces that, further to its news release, the binding letter of intent with "
             "Beta Minerals Inc. under which the Company granted Beta the option to acquire an 80% interest in its Alpha Project has "
             "been extended to March 31.")[0][:2],
        rows("ABC Gold Receives Approval of Nianfors Mineral License Applications", "announces that its mineral licence applications "
             "Nianfors nr 1 and 2 have been granted to its subsidiary by the Mining Inspectorate.")[0][:2]),
       ("signed", ("claim_purchase", "completed"), ("property_sale", "completed"), ("option_out", "amended"), ("staking", "completed")))
    eq("deal type: 'Acquires' on option terms; a partner continuing its earn-in",
       (rows("ABC Gold Acquires Gold Project in Central Quebec", "has entered into an agreement with an arm's length vendor to acquire "
             "a 100% interest in the Bonneville Gold Project. Under the terms of the agreement, the Company can earn a 100% interest in "
             "the project by paying a total of $260,000 within two years.")[0][:3],
        rows("Kappa Metals Continues Earn-In at ABC's Alpha Project", "is pleased to announce that Kappa Metals Corp. (\"Kappa\") has "
             "committed to continuing through 2026 its earn-in to ABC's Alpha Project.")[0][:3]),
       (("option_in", "signed", "Bonneville"), ("option_out", "payment", "Alpha")))
    eq("one row per deal: a purchase and staking announced together; blocks staked and named one by one",
       (rows("ABC Gold Acquires and Stakes Claims Around its Alpha Discovery", "has agreed to acquire the Beta Property from Kappa "
             "Resources Ltd. for $35,000. The Company has also staked 299 claims adjacent to the Alpha property.", ("deal_type", "property")),
        rows("ABC Gold Stakes Two New Gold Projects", "announces that it has staked two high-grade precious metal prospects in Nevada. "
             "Sniper Property The Sniper Property covers old workings on Gold Mountain. Irwin Property The Irwin Property covers a "
             "quartz vein system.", ("deal_type", "property"))),
       ([("staking", None), ("property_purchase", "Beta Property")], [("staking", "Sniper Property"), ("staking", "Irwin Property")]))
    eq("counterparty: a parent before its subsidiary",
       rows("ABC Gold Acquires Carlin Trend Claims", "has entered into a definitive claims acquisition agreement with Fremont Gold Ltd. "
            "and its Nevada-based subsidiary, Intermont Exploration Corp. to acquire a 100% interest in the Coyote and Rossi Claim "
            "Blocks.", ("property", "counterparty")), [("Coyote and Rossi Claim", "Fremont Gold")])
    eq("names: a company, a description, a country, a PDF break",
       ([p for _q, p in _props_in("an earn-in agreement with Freeport-McMoRan Mineral Properties Canada Inc. on the Joy project")],
        (_name("Debt Settlement", "Property"), _name("Timmins-Area", "Properties"), _name("Zimbabwe Gold-Base Metal", "Project"),
         _name("Third Hard-Rock", "Project")), _prepare("x", lead + "the Rayfield -Gjoll Project")[1][-26:]),
       (["Joy Project"], (None, None, None, None), "the Rayfield-Gjoll Project"))
    eq("the copy of the headline in the body is blanked, positions kept",
       _drop_head_copy("ABC Gold Acquires Beta Claims", "ABC GOLD ACQUIRES BETA CLAIMS Vancouver - ABC has acquired the Beta Claims."),
       " " * 30 + "Vancouver - ABC has acquired the Beta Claims.")
    # 1.0.8 (2026-10-01): the reader's own news only (outside-tag samples conf3 / conf4)
    eq("not ground: an over-allotment option, options issued, a royalty buy-back payment, mill assets, another company's shares",
       (rows("ABC Gold Closes $33 Million Bought Deal Including the Full Exercise of the Over-Allotment Option", "announces that it has "
             "closed its bought deal public offering, including the full exercise of the over-allotment option granted to the underwriters."),
        rows("ABC Gold Commences Drilling at Alpha Property and Issues Options", "has commenced drilling at the Alpha property. The "
             "Company has issued 500,000 incentive stock options to its directors."),
        rows("ABC Gold Announces Final Option Payment for Royalty Buy Back at Its Alpha Property", "intends to settle the final payment "
             "to buy back the 2% NSR royalty on the Alpha Property."),
        rows("ABC Gold Announces Strategic Divestiture of Beta Mill Assets", "has signed an agreement to sell the Beta mill equipment "
             "to Kappa Metals Inc. for $2,000,000."),
        rows("ABC Gold Announces Sale of Kappa Shares for $1.7 Million", "has sold 10,000,000 common shares of Kappa Metals Ltd. Under "
             "the terms of the option agreement with Kappa, ABC may receive further shares if Kappa completes the earn-in to acquire an "
             "80% interest in the Alpha project.")), ([], [], [], [], []))
    eq("not ground: an LOI for equity capital, a gold pre-pay forward purchase",
       (rows("ABC Gold Enters Into Letter of Intent with Kappa Capital for $5 Million in Equity Capital", "has entered into a letter of "
             "intent with Kappa Capital for an equity facility. This gives us confidence in our pending Alpha property acquisition."),
        rows("ABC Gold Signs Term Sheet for Up to 7,000 Ounces Gold Pre-Pay Forward Purchase Facility", "has signed a term sheet for a "
             "pre-pay facility. The facility includes a forward purchase of 7,000 ounces of gold to support development of the Alpha "
             "Mine.")), ([], []))
    eq("company-level M&A in the headline: a business combination, 'creating a ... company'",
       (rows("ABC Gold Enters into Letter of Intent for Proposed Business Combination with Kappa", "has entered into a letter of intent "
             "with Kappa Metals Corp. We have many options on how to proceed on each project, including optioning certain assets."),
        rows("ABC Gold to Acquire Kappa's Alpha Mine and Beta Mill, Creating a Multi-Asset Copper Company", "has signed a share purchase "
             "agreement with Kappa Mining Corporation. ABC will acquire 100% of the Alpha Mine and Beta Mill operations.")), ([], []))
    eq("company-level: the lead buys a company (an operating mine's owner, a company with no land in the headline, a share exchange)",
       (rows("ABC Gold to Acquire Alpha Copper Mine in Brazil", "has entered into a definitive purchase agreement with Kappa Gold Inc. "
             "to purchase its 100% ownership stake in Mineracao Alpha Industria e Comercio S/A, which owns the producing Alpha "
             "copper-gold mine. The acquisition is immediately accretive."),
        rows("ABC Gold Announces Strategic Acquisition of Kappa Minerals, Expanding Footprint in the Lithium District", "reports that "
             "it has acquired 100% of Kappa Minerals Participacoes Ltda., a Brazilian company which owns a 40% interest in the Alpha "
             "Project."),
        rows("ABC Gold Closes Acquisition of Kappa Metals and its Alpha Project", "is pleased to announce completion of the purchase of "
             "Kappa Metals Ltd. pursuant to which the Company has acquired all of the issued and outstanding common shares of Kappa. "
             "Each Kappa share received 2.8 ABC shares. All six properties were staked by Kappa."),
        rows("ABC Gold Seeks Shareholder Approval for the Sale of its 25% Ownership Interest in Kappa Operations", "announces a "
             "meeting in connection with the previously announced sale of its 25% interest in Kappa Operations Inc. to its joint venture "
             "partner Omega Mining Inc.")), ([], [], [], []))
    eq("a subsidiary that holds a named project, sold under a headline that names the project, is a property sale",
       rows("ABC Gold to Sell Alpha Gold Project in Mali to Kappa Gold", "has executed a sale and purchase agreement with Kappa Gold "
            "Corporation for the sale of the Company's 100% owned subsidiary Alpha Mali Inc. which owns the Alpha licences.")[0][:1],
       ("property_sale",))
    eq("background: a program 'post-acquisition'; the company's own licence application named as the place of other news",
       (rows("ABC Gold Plans 9,000m of Drilling at the Alpha Project Post-Acquisition", "is pleased to announce that it expects to "
             "complete the previously announced acquisition of the Alpha Project from Kappa Metals Corp. in May."),
        rows("ABC Gold Announces Review of Historic Data for Their Beta Licence Application, Alpha Gold Project", "reports a review "
             "of historic gold and silver data.")), ([], []))
    eq("a headline with several pieces of news: the sale's own property, permits are other news",
       rows("ABC Gold Reports Third Quarter Results: Alpha Gold Receives Record of Decision & Key Permits & ABC Gold Sells its 50% "
            "share of Beta Creek to Kappa", "released its third quarter results. Alpha Gold received a Record of Decision and key "
            "permits for the Alpha Project.", ("deal_type", "property")), [("property_sale", "Beta Creek")])
    eq("an option over an exploration permit; the permit's quoted name",
       rows("ABC Gold Expands its Exploration Footprint in the Alpha District", "has expanded its footprint in the Alpha district. "
            "The expansion is executed through an option to purchase agreement with Kappa Gold Limited over the PR 840 \"Sienso\" "
            "permit.", ("deal_type", "property", "counterparty")), [("option_in", "Sienso Property", "Kappa Gold")])
    eq("a headline that runs into the body ends at the dateline; the body restates the headline's non-land deal",
       rows("ABC Gold Closes C$13.5 Million Sale of Real Estate Asset in Mexico Vancouver, British Columbia - ABC Gold Mines Ltd. "
            "(TSX:ABC) announces that it has closed the sale of its Alpha Property, a non-core asset", "has closed the sale of its "
            "Alpha Property, a non-core real estate asset, for C$13.5 million."), [])
    eq("a royalty or stream bought on a project is not ground; royalty-free ground is",
       (rows("ABC Gold Acquires Existing NSR Royalty on Its Alpha Project", "has acquired the 2% NSR royalty on its Alpha Project "
             "from Kappa Gold Corp. for $500,000."),
        rows("ABC Gold Closes Purchase for Royalty-free 100% Interest in Past-Producing Alpha Mine", "has closed the purchase of a "
             "100% interest in the Alpha Mine from Kappa Mining LLC.")[0][:1]), ([], ("property_purchase",)))
    eq("deal type: concessions and patents bought are claims; a named asset sold is a sale",
       (rows("ABC Gold Acquires La Alpha Gold-Silver Concessions in Sonora", "has acquired the La Alpha concessions from Kappa Silver "
             "Corp.")[0][:1],
        rows("ABC Gold Acquires Ownership of the Alpha Patents", "has entered into an agreement to acquire the Alpha patents, three "
             "patented mining claims, from Kappa Ontario Inc.")[0][:1],
        rows("ABC sells K2 to Kappa", "has entered into an agreement with Kappa Exploration Inc. pursuant to which Kappa will acquire "
             "the K2 property.")[0][:1]), (("claim_purchase",), ("claim_purchase",), ("property_sale",)))
    eq("stage: a binding agreement is signed; an extended closing is amended; 'has sold' is completed",
       (rows("ABC Gold Announces Binding Agreement to Sell its Interest in the Alpha Mine", "has entered into a binding memorandum of "
             "understanding to sell its 80% interest in the Alpha mine to Kappa Holding A.S.")[0][1],
        rows("ABC Gold Announces Extension of Alpha Acquisition Closing", "and Kappa Mining Company have agreed to extend the period "
             "to complete the acquisition of the Alpha project to June 30.")[0][1],
        rows("ABC Gold Sells Alpha Property", "announces that it has sold a 100% interest in its Alpha Property to Kappa Metals Ltd. "
             "for $100,000.")[0][1],
        rows("ABC Gold Signs Binding Letter of Intent to Sell Alpha Property", "has signed a binding letter of intent to sell the "
             "Alpha Property to Kappa Metals Ltd.")[0][1]), ("signed", "amended", "completed", "proposed"))
    # 1.0.9 (FIX4): the deal's own ground, not a neighbour's or the host project named after a relation
    eq("1.0.9 upper-case headline: a neighbour's project after 'contiguous to'; the body's 'known as' name",
       rows("ABC GOLD ACQUIRES SECOND GOLD PROPERTY CONTIGUOUS TO KAPPA GOLD'S OMEGA GOLD PROJECT", "is pleased to announce the "
            "acquisition of a second gold property known as the \"Alpha Property\", contiguous to the Omega Gold Project, owned by "
            "Kappa Gold Corp.", ("deal_type", "property")), [("property_purchase", "Alpha Property")])
    eq("1.0.9 relations: 'adjacent to and along strike of its', 'on trend with its'; lower-case metals before the suffix",
       (rows("ABC Gold Options Additional Property Adjacent to Omega, Yukon", "has concluded an option agreement to acquire 78 "
             "claims adjacent to and along strike of its Omega and Sigma projects. The Company is pleased to have concluded an option "
             "agreement on the Alpha Property.", ("deal_type", "property")),
        rows("ABC Gold Stakes New Property to Expand its Omega Property", "is pleased to announce its acquisition through staking "
             "of the Alpha gold-silver property, on trend with its Omega and Sigma properties.", ("deal_type", "property"))),
       ([("option_in", "Alpha Property")], [("staking", "Alpha Property")]))
    eq("1.0.9 names: 'referred to as the X'; 'claims called the X'; a country is no name; 'Share Purchase Agreement' names paper",
       (rows("ABC Gold Announces Option Agreement and Private Placement", "has entered into an option agreement to acquire a 100% "
             "interest in a former Kappa Exploration project referred to as the Alpha Property.", ("property",)),
        rows("ABC Gold Signs LOI for Purchase of 94 Claims Contiguous to the Omega Project", "has signed a letter of intent for the "
             "purchase of 94 mineral claims called the Alpha Nord, which is contiguous to the Omega Project.", ("property",)),
        rows("ABC Gold Enters into Share Purchase Agreement to Acquire C\u00f4te d'Ivoire Projects", "has entered into a share purchase "
             "agreement to acquire the Alpha Project of 14 km2.", ("property",))),
       ([("Alpha Property",)], [("Alpha Nord Property",)], [("Alpha",)]))
    eq("1.0.9 headline 'Claims at X' names the ground; a list of places does not",
       (rows("ABC Gold Acquires 3 Additional Claims at Alpha", "has acquired three additional claims at its Alpha project.",
             ("property",)),
        [r[0] for r in rows("ABC Gold Stakes 185 Claims at Alpha NV, Beta, ID and Gamma AZ", "has staked 185 claims at its Alpha "
                            "Property, Beta Property and Gamma Property.", ("property",))]),
       ([("Alpha Property",)], ["Alpha Property", "Beta Property", "Gamma Property"]))
    # 1.0.9: option direction
    eq("1.0.9 direction: the Company grants the option; a partner's notice to drop it; the issuer's own payments",
       (rows("ABC Gold Announces Amendment to Option Agreement with Kappa Metals for Alpha Project", "has signed an amendment to its "
             "option agreement with Kappa Metals Corp. (\"Kappa\"), pursuant to which ABC will grant Kappa the sole exclusive option to "
             "acquire a 100% interest in the Alpha Project.", ("deal_type",)),
        rows("ABC Gold Announces Extension of LOI", "announces that the Company has granted the Optionor the option to acquire an 80% "
             "interest in its Alpha project, and the parties have agreed to extend the LOI.", ("deal_type",)),
        rows("ABC Gold Announces Kappa's Termination of its Option to Acquire the Alpha Project", "announces that it has been notified "
             "by Kappa S.A. of its intention to relinquish its option to acquire the Company's 55%-owned Alpha Project.",
             ("deal_type", "stage")),
        rows("ABC Gold Receives Regulatory Approval and Makes Initial Payments Under Alpha Project Option Agreement", "announces that "
             "it has made the initial payments under the Alpha Project option agreement; the Company could earn a 60% interest in "
             "the Project.", ("deal_type",)),
        rows("ABC Gold Enters Option Agreement for Alpha Property", "has entered into an option agreement with Kappa Resources Inc. "
             "pursuant to which the Company may earn a 100% interest in the Alpha Property. The Company will grant Kappa an option to "
             "purchase the mining rights to other minerals on the Property (the \"Buy-Back Option\").", ("deal_type",))),
       ([("option_out",)], [("option_out",)], [("option_out", "terminated")], [("option_in",)], [("option_in",)]))
    # 1.0.9: not the release's own deal
    eq("1.0.9 no deal: a claim block named as the place of drilling; two other companies' option; their staking, our purchase",
       (rows("ABC GOLD COMMENCES DRILLING OF COPPER TARGETS AT B3 CLAIM BLOCK IN QUEBEC", "has commenced drilling at the B3 claim "
             "block. The 24,322 hectare B3 claim block was staked due to the Company's sampling."),
        analyse("Kappa Silver Mines Enters into Option Agreement for Omega Project, Mexico", "Ottawa, Ontario, January 8, 2021 - ABC "
                "Gold Mines Ltd. (TSXV: ABC) (\"ABC\" or the \"Company\") announces that Sigma Gold Inc. and its subsidiary (\"SGI\") "
                "have entered into an option agreement with Kappa Silver Mines Inc., pursuant to which Kappa can earn up to an 80% "
                "interest in the Omega project. ABC retains a 20% free-carried interest in the Omega project." + fill)["rows"],
        rows("ABC Gold Expands Land Position in Alpha District, Quebec", "is pleased to announce it has acquired a 100% interest in "
             "four additional mineral claims directly contiguous to Kappa Materials Corp.'s (\"KMC\") recent expansion claims staking. "
             "The Company's acquisition of the claims remains subject to customary conditions of closing.", ("deal_type", "stage"))),
       ([], [], [("claim_purchase", "signed")]))
    eq("1.0.9 background: another company's deal in the passive; 'now optioned to'; history behind a pointer to an earlier release",
       (rows("ABC Gold Acquires 3 Additional Claims at Alpha", "has acquired three additional claims at its Alpha project. The Omega "
             "claims acquired by Kappa Development Corp. are contiguous with the Company's claims to the north.", ("property",)),
        rows("ABC Gold Signs Agreement to Acquire Four Properties in Finland", "has signed a binding letter agreement to earn 100% of "
             "four exploration reservations from Kappa B.V. The Company holds one licence in Portugal, the Omega VMS Project, now "
             "optioned to Sigma in an earn-in joint venture agreement.", ("deal_type", "property")),
        analyse("ABC Gold Acquires 100% Interest in the Alpha and Beta Projects", "MONTREAL, July 05, 2022 (GLOBE NEWSWIRE) -- ABC Gold "
                "Corporation (\"ABC\" or \"The Company\") announces that it has signed an agreement to acquire 100% of the interest in "
                "the Alpha project and Beta project from Kappa Mining Corporation. Original Option Agreements In June 2021 (see the "
                "press release), ABC signed an option agreement with Kappa Mining Corporation to acquire up to 50% interest in the "
                "Beta project." + fill)["rows"].__len__()),
       ([("Alpha Property",)], [("option_in", None)], 1))
    # 1.0.9: stage
    eq("1.0.9 stage: an earn-in step done; a replaced agreement is not terminated; options relinquished in passing are their own rows",
       (rows("ABC Gold Acquires 75% of the Alpha Gold Project", "is pleased to announce the completion of the Alpha option. Pursuant to "
             "the Alpha option agreement with Kappa Resources Ltd., ABC acquired an initial 51% interest in the Alpha Project. ABC "
             "acquired an additional 24% (75% total) interest in the Alpha Project.", ("stage",)),
        rows("ABC and Kappa Replace Purchase and Sale with Option to Acquire the Alpha Property", "is pleased to announce that Kappa "
             "Exploration Inc. and the Company have agreed to terminate the purchase agreement signed on July 2, 2019 and replace it "
             "with an option agreement pursuant to which Kappa will grant ABC the option to acquire a 100% interest in the Alpha "
             "property.", ("stage",)),
        rows("ABC Gold Announces Signing of Definitive Option Agreements to Acquire Alpha North Project", "has signed definitive option "
             "agreements to acquire a 70% interest in the Alpha North Project. The Company also announces that it has relinquished its "
             "options to acquire the Beta and Gamma cobalt properties. By relinquishing the options to such properties, the Company "
             "will not be subject to any further obligations.", ("stage", "property"))),
       ([("completed",)], [("signed",)], [("signed", "Alpha North"), ("terminated", "Beta Property"), ("terminated", "Gamma Property")]))
    eq("1.0.9 a partner earning a % interest in a district is a deal on ground",
       rows("KAPPA CONTINUES EARN-IN AT ABC'S ALPHA COPPER-GOLD DISTRICT", "is pleased to announce that Kappa Mineral Canada Ltd. "
            "(\"Kappa\") has committed to continuing through 2025 its earn-in to ABC's Alpha District. Under the terms of the Agreement, "
            "Kappa has a two-staged option to earn up to a 70% interest in the Alpha District by funding $90 million of expenditures.",
            ("deal_type",)), [("option_out",)])
    # FIX5 (1.0.10)
    t5 = ("deal_type", "stage", "property", "counterparty", "cash", "shares")
    eq("1.0.10 C1 a total the release states, words in between",
       rows("ABC Gold Signs Option to Acquire Alpha Gold Project", "has entered into an option agreement with Beta Minerals Inc. to "
            "acquire a 100% interest in the Alpha Gold Project. ABC is required to make cash payments over three years totalling "
            "US$1,350,000 and work commitments totalling US$1,000,000 over two years. The payment schedule is as follows: US$100,000 "
            "upon signing, US$200,000 on the first anniversary.", ("cash",)), [(1350000.0,)])
    eq("1.0.10 r2 a stated total cash consideration wins over its first payment; the scale is read",
       [rows("ABC Gold Signs Option on Alpha Property", "has entered into an option agreement with Beta Minerals Inc. to acquire " +
             ("a 100%% interest in the Alpha Property by paying the Optionor a total cash consideration of %s as follows: $50,000 "
             "on signing and the balance on the first anniversary." % x), ("cash",)) for x in ("$1.05 million", "C$1.05M",
                                                                                               "$1,050,000")],
       [[(1050000.0,)], [(1050000.0,)], [(1050000.0,)]])
    eq("1.0.10 S1 the share issues of a schedule summed (a lone cash payment named with a step of the schedule is not a total)",
       rows("ABC Gold Acquires Alpha Claims", "has signed a letter of intent to acquire the Alpha Claims by paying the vendors $5,000 "
            "and issuing 750,000 shares on signing and an additional 650,000 shares on the first anniversary of the agreement.",
            ("cash", "shares")), [(None, 1400000.0)])
    eq("1.0.10 S1 the whole, then its tranches, is the whole",
       rows("ABC Gold Signs Option on Alpha Project", "has entered into an option agreement with Beta Minerals Inc. to acquire a 100% "
            "interest in the Alpha Project by issuing 1,500,000 common shares of ABC to Beta. Option payment summary: 750,000 ABC "
            "Shares to Beta following Exchange approval; 750,000 ABC Shares to Beta on the first anniversary.", ("shares",)),
       [(1500000.0,)])
    eq("1.0.10 S1 shares of a placement, warrants and a finder's shares are not the deal's",
       rows("ABC Gold Acquires Alpha Property", "has acquired the Alpha Property from Beta Minerals Inc. for $50,000 cash and the issuance "
            "of 1,000,000 common shares. The Company also announces a private placement of 5,000,000 units and will issue 100,000 "
            "shares to a finder.", ("cash", "shares")), [(50000.0, 1000000.0)])
    eq("1.0.10 CP the other side's name as written: led by a number, a commodity word, or 'X, LLC'",
       [rows("ABC Gold Enters into Option Agreement with 1234 Resources to Sell a 100% Interest in the Alpha Project", "has entered "
             "into an option agreement to sell a 100% interest in the Alpha Project to 1234 Resources (TSXV: XYZ), in exchange for "
             "cash payments.", ("counterparty",)),
        rows("ABC Gold Signs Option on Alpha Project", "has entered into an option agreement to acquire up to a 100% interest in the "
             "Alpha Project from Nickel Beta Exploration Corp. (\"NBE\").", ("counterparty",)),
        rows("ABC Gold Signs Option on Alpha Project", "has entered into an option agreement with Alpha Nevada II, LLC (\"Alpha\"), "
             "to acquire a 100% interest in the Alpha project.", ("counterparty",))],
       [[("1234 Resources",)], [("Nickel Beta Exploration",)], [("Alpha Nevada II",)]])
    eq("1.0.10 CP a project name before 'with X' does not make a list",
       rows("ABC Gold to Acquire up to 80% of Alpha Copper Project", "has entered into a letter of intent for an option to acquire up "
            "to an 80% interest in the Alpha Copper Project, with XYZ Beta Minerals Group, a privately held mining company.",
            ("counterparty",)), [("XYZ Beta Minerals",)])
    eq("1.0.10 CP the vendor keeps the royalty; ground optioned earlier next door names no party",
       [rows("ABC Gold Acquires Additional Claims at Alpha Project", "has acquired 6 additional claims at the Alpha Project. The "
             "claims were acquired under the existing option agreement and no additional cash or shares were issued. Beta Or Corp. "
             "retains a 2% Net Smelter Return Royalty on the added claims.", ("counterparty",)),
        rows("ABC Gold Acquires Key Claims", "has signed a letter of intent to acquire a 100% interest in a 10 claim block (the Gamma "
             "claims)." + fill + " The claims are contiguous with ABC's Delta claims recently optioned from Epsilon Resources Inc.",
             ("counterparty",))],
       [[("Beta Or",)], [(None,)]])
    eq("1.0.10 D newly staked ground is staking; the other side earning is an option out",
       [rows("ABC Gold Acquires the Alpha Property", "is pleased to announce the acquisition of the Alpha property. The newly-staked "
             "claims are located 500 metres north of a past-producing mine.", ("deal_type",)),
        rows("ABC Gold Amends Agreement with Beta Mining on Alpha Project", "announces that it has agreed to amend certain terms in "
             "the Option Agreement with Beta Mining Corp. The deadline for Beta to incur the final $1,000,000 in exploration "
             "expenditures, required to exercise the first option to earn a 51% interest in the Alpha project, has been extended.",
             ("deal_type",))],
       [[("staking",)], [("option_out",)]])
    eq("1.0.10 R2 new ground the company stakes beside its option is its own row",
       rows("ABC Gold Options Alpha Property", "is pleased to announce it has optioned the Alpha property. The Company acquired the "
            "843 hectare Alpha property through a prospector option agreement covering 3 mineral claims. The Company also staked "
            "87 claim units to cover an additional 1880 hectares surrounding the Alpha property.", ("deal_type", "area")),
       [("option_in", 843.0), ("staking", 1880.0)])
    eq("1.0.10 rev b no own-staking row for another company's, shared, unmeasured or hypothetical staking",
       [len(rows("ABC Gold Options Alpha Property", "is pleased to announce it has optioned the Alpha property. " + x,
                 ("deal_type",))) for x in
        ("Beta Mining has also staked an additional 862 square kilometres of new claims adjoining the property.",
         "The Company has staked 906 claims under this agreement.",
         "The Company has also staked additional claims in the region.",
         "This is ground we would have staked if it were open.")],
       [1, 1, 1, 1])
    # FP_NARROW: the fingerprint takes the Technical code this reader runs, and none of the rest
    b = FP.borrowed_source(T, "T", __file__)
    eq("fingerprint: Technical code used", ("def _sentences(" in b, "_DATE_RX = " in b), (True, True))
    eq("fingerprint: Technical code not used", ("def extract(" in b, "SPEC = " in b), (False, False))
    pb = FP.borrowed_source(PN, "PN", __file__)
    eq("fingerprint: project-name helper followed", ("def clean(" in pb, "def primary(" in pb, "def _selftest(" in pb),
       (True, True, False))
    eq("fingerprint: uses the helper", FP.uses(__file__, "portal.project_names"), True)
    mb = FP.borrowed_source(PM, "PM", __file__)
    eq("fingerprint: the Permits jurisdiction rule followed, nothing else", ("def _jurisdiction(" in mb, "def _short(" in mb,
                                                                          "def extract(" in mb), (True, True, False))
    eq("fingerprint: stable", FP.code_sha(__file__), SPEC.code_sha)
    print("options: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test("-v" in sys.argv) else 0)
