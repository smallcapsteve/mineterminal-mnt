"""Financings extractor, facts-store version (FIN_V1). Phase 2b #2 of the revised plan.

Replaces portal/financing_extract.py v3 + the pass-1 half of financing_backfill.py as the source of
/financings once it passes the accuracy gate. Grouping releases into deals is NOT done here (it needs
the whole corpus); portal/financing_publish.py does that from what this module stores.

Reuses the v3 role grammar and money reader (portal/extractors/fin_grammar.py) and changes what the
2026-09-17 baseline and the confirmed accuracy set found wrong:

  1. one decision "is this release the company's own financing?" with reasons (results, warrant
     exercises, shares for debt, option agreements, the company investing in or lending to someone
     else, congratulations ...) instead of a role of "mention" doing double duty
  2. deal type from the headline and the deal's own paragraph, not 3,000 characters of body that
     also describe other deals; "non-brokered" in any spelling is never BROKERED; agents,
     underwriters and "best efforts" make a deal brokered
  3. amounts are kept apart: size offered, size with the over-allotment option, this close, and the
     closed total; insider participation, finder's fees and earlier raises are not deal amounts
  4. every issue price of the deal (hard-dollar and flow-through), never a warrant's exercise price
     or a debenture's conversion price (kept separately)
  5. warrants: one-half / one-third / one whole, strike and term read from the unit's own sentence
     (numbers in words, "(2) years", "36 months following"), finder's and broker warrants ignored
  6. dates of the earlier releases this one refers to, for the publisher's grouping
  7. the text is normalised first (ligatures, "$0. 26", "C$ 0.35", curly quotes) and capped at
     8,000 characters, so the result does not depend on a release's legal boilerplate
  8. 1.0.4: the number of units (or shares) each amount bought, kept only when count x issue price equals
     that amount (within 1.5%), so no finder's, insider's or outstanding count is ever the deal's
  9. 1.0.5 (FIX5): amendments read from "revised terms" / "price change" wording, "Announces Updates on" is an
     update, money drawn under an existing facility is an update; a minimum offering's figure is not the size;
     "non flow-through" is the hard-dollar part; a sentence about an earlier release's close is not this close;
     "repricing from $X to $Y" keeps only $Y

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    what the facts store keeps (one record per release)
to_prediction(records)  -> dict|None   what the accuracy check compares (grouping comes from the publisher)

Self-tests: python3 -m portal.extractors.financings
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from portal import facts as F
from portal.extractors import fin_grammar as G

NAME = "financings"
VERSION = "1.0.6"  # 2026-10-06 FIX8 (d: narrower cues): unit prices are what a unit or share is sold for - not a warrant's exercise price written far from the word warrant, an acceleration trigger, a deemed or resale price; 2026-09-26: unit count (units_offered / units_this_close / units_closed_total); 2026-10-04 FIX5: stage
#                   (revised terms / price change = amendment, "Updates on" = update, a drawdown under a facility = update),
#                   amounts (the maximum of a minimum/maximum offering, "non flow-through" = hard-dollar part, an earlier
#                   release's close is not this close), a repricing's old price is not an issue price
KIND = "financing"
TAG = "Financings"
TEXT_CAP = 8000

ROLES = ("announcement", "upsize", "amendment", "tranche_close", "final_close", "terminated", "update")


# ------------------------------------------------------------------ text
_WS = re.compile(r"[ \t\u00a0\u2000-\u200b\u202f\u205f\u3000]+")


def clean(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("\u2010", "-").replace("\u2011", "-").replace("\u2012", "-").replace("\u2013", "-") \
        .replace("\u2014", "-").replace("\u2212", "-").replace("\u00ad", "")
    t = t.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    t = _WS.sub(" ", t)
    t = re.sub(r"\s*\n\s*", "\n", t)
    t = re.sub(r"(\$\s?\d+)\.\s(\d)", r"\1.\2", t)            # "$0. 26"
    t = re.sub(r"(\$)\s+(\d)", r"\1\2", t)                     # "C$ 0.35"
    t = re.sub(r"(?i)\bnon\s*-\s*\n?\s*brokered", "non-brokered", t)
    t = re.sub(r"(?i)\bflow\s*-?\s*\n?\s*through", "flow-through", t)
    t = re.sub(r"(?i)\bone\s*-\s*(half|third|quarter|fourth)\b", lambda m: "one-" + m.group(1).lower(), t)
    t = t.replace("\u019f", "ti").replace("\ua730", "ti")
    return t


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


_RE_FLS = re.compile(
    r"(?i)(?:forward[\-\s]looking\s+(?:statements?|information)\b"
    r"|cautionary\s+(?:note|statement)s?\b"
    r"|neither\s+(?:the\s+)?(?:tsx|canadian\s+securities\s+exchange|cse)\b"
    r"|this\s+news\s+release\s+(?:does\s+not\s+constitute|shall\s+not\s+constitute|contains\s+forward)"
    r"|\babout\s+(?:the\s+company|[A-Z][\w&.\-]+(?:\s+[A-Z][\w&.\-]+){0,4})\s*\n)")


def deal_window(body: str, cap: int = 5000) -> str:
    """The part of the release that is news: above the disclaimers / About heading, capped."""
    b = body[:TEXT_CAP]
    m = _RE_FLS.search(b, 200)
    if m and m.start() < 2600:
        # 1.0.3: an "About the Company" blurb in the middle of a release is not the end of the news --
        # if the offering's own terms carry on after it, read to the next disclaimer instead.
        tail = b[m.start():m.start() + 1800]
        if re.search(r"(?i)\beach\s+(?:whole\s+|full\s+)?warrant\b|\bexercise\s+price\b"
                     r"|\beach\s+(?:\S+\s+){0,3}unit\s+(?:will\s+)?(?:consist|comprise|be\s+comprised)"
                     r"|\bgross\s+proceeds\b|\bper\s+(?:FT\s+)?unit\b", tail):
            m2 = _RE_FLS.search(b, m.end())
            m = m2
    if m:
        b = b[:m.start()]
    return flat(b[:cap])


_RE_BOILER_HEAD = re.compile(
    r"(?i)^(?:news\s+release|press\s+release|for\s+immediate\s+release|symbol\b|tsx[v\-]|cse\b|"
    r"not\s+for\s+(?:distribution|dissemination)|responsible\s+mining|\d+(?:\.\d+)?\s*$)")


def main_headline(h: str) -> str:
    """A stored headline sometimes runs into the sub-headline or the first sentence ("... FINANCING The Company has
    also closed ..."). The role is read from the part before that when the part names a deal on its own."""
    if len(h) < 90:
        return h
    m = re.search(r"(?<=[a-z0-9A-Z)])\s+(?=(?:The\s+)?[Bb]ase\s+[Ss]helf|THIS\s+NEWS\s+RELEASE|NOT\s+FOR\s+DISTRIBUTION|(?:The|the)\s+(?:Company\b|[a-z])|[A-Z][a-z]+,\s+(?:[A-Z][a-z]+\s*)?(?:[A-Z][a-z]+)?\s*[-\u2013]|"
                  r"(?:Vancouver|Toronto|Calgary|Montreal|London|Edmonton|Kelowna|Halifax|Denver|Reno|Perth)\b)", h[40:])
    if m:
        cut = h[:40 + m.start()]
        if G._fin_noun(cut) or G._RE_MONEY_NOUN.search(cut):
            return cut
    return h


def effective_headline(headline: str, body: str) -> str:
    """The headline, or the first title-like line of the body when the stored headline is boilerplate."""
    h = flat(headline)
    informative = len(h) >= 25 and not _RE_BOILER_HEAD.search(h) and (
        len(h.split()) > 6 or re.search(r"(?i)\b(?:announces?|closes?|completes?|reports?|provides?|receives?|secures?|arranges?|"
                                         r"files?|increases?|upsizes?|amends?|terminates?|extends?)\b", h))
    if informative or G._fin_noun(h) or G._RE_MONEY_NOUN.search(h):
        return h
    raw = [x.strip() for x in (body or "")[:1500].split("\n")]
    lines = []
    for i, x in enumerate(raw):
        ln = x
        j = i + 1
        while ln and not re.search(r"[.!?:]\s*$", ln) and j < len(raw) and raw[j] and len(ln) < 200 and (ln.endswith("-") or raw[j][:1].isupper() is False or len(ln) > 40):
            ln = (ln + (" " if not ln.endswith("-") else "") + raw[j]).strip()
            j += 1
        lines.append(flat(ln))
    for ln in lines[:12]:
        if 20 <= len(ln) <= 220 and not _RE_BOILER_HEAD.search(ln) and (
                G._fin_noun(ln) or re.search(r"(?i)\b(?:announces?|closes?|completes?)\b", ln)):
            return ln
    fb = flat((body or "")[:1500])
    m = re.search(r"(?i)\b(?:announces?|is\s+pleased\s+to\s+announce|has\s+(?:closed|completed))\b[^.]{0,220}", fb)
    if m and G._fin_noun(m.group(0)):
        return m.group(0)
    return h


# ------------------------------------------------------------------ money
_CUR = G._CUR
_RE_MONEY = re.compile(_CUR + r"\s?(?=\d)")
_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "twelve": 12, "eighteen": 18, "twenty-four": 24, "twenty four": 24, "thirty-six": 36,
             "thirty six": 36, "forty-eight": 48, "sixty": 60, "thirty": 30, "twenty": 20, "fifteen": 15}


def monies(text: str):
    """[(value, currency_code, start, end)] for every "$" figure in text."""
    out = []
    for m in _RE_MONEY.finditer(text):
        v, end = G.read_amount(text, m.end())
        if v is None:
            continue
        out.append((v, G._cur_code(m.group("cur")), m.start(), end))
    return out


_RE_PER = re.compile(r"(?i)^\s*(?:\(\s*[^)]{0,60}\)\s*)?(?:per|/|for\s+each|each)\b")
_RE_NOT_DEAL_AMT_BEFORE = re.compile(
    r"(?i)(?:\b(?:insiders?|directors?|officers?|management|related\s+part(?:y|ies)|participat\w*|subscribed\s+by"
    r"|finders?'?|finder's|commissions?|fees?|cash\s+(?:position|balance|on\s+hand)|treasury|working\s+capital"
    r"|previously\s+(?:closed|completed|raised)|recently\s+(?:closed|completed)|last\s+year|since\s+inception"
    r"|to\s+date\s+(?:has|have)\s+raised|in\s+addition\s+to|market\s+capitali[sz]ation|valued\s+at|valuation"
    r"|exploration\s+(?:expenditures?|budget|program)|spend|expenditures?|payment\s+of|pa(?:y|ys|id|ying)|purchase\s+price|(?:equity|enterprise|total|transaction)\s+value|representing|non-dilutive|funding\s+transaction|grant|application\s+for|guarantee|EBITDA|profit|loss"
    r"|consideration|acquisition|interest|royalty|revenue|net\s+smelter|NPV|IRR|capex|capital\s+cost"
    r"|net\s+proceeds|proceeds\s+net\s+of|after\s+deducting"
    r"|debt\s+of|indebtedness|loan\s+of|owed|settle\w*)\b[^$]{0,60}$)")


def money_kind(text: str, v, start: int, end: int) -> str:
    """'price' | 'strike' | 'conversion' | 'other' | 'deal' for one figure, from its words around it."""
    after = text[end:end + 40]
    after_wide = text[end:end + 80]                       # 1.0.2: "$0.01 ($0.20 on a post-Consolidation basis) per Receipt"
    if re.match(r"(?i)\s*(?:was|is|were)\s+(?:part\s+of\s+)?(?:a\s+|the\s+)?(?:repayment|settlement|payment\s+to|owed)", after_wide):
        return "other"                                     # 1.0.3: "$30,000 was part of a repayment to a consultant"
    before = text[max(0, start - 140):start]
    near = before[-60:]
    if re.search(r"(?i)conver(?:sion|tible|t)\w*\s+(?:price\s+)?(?:of\s+|at\s+|equal\s+to\s+)?(?:approximately\s+)?$", near) \
            or re.search(r"(?i)\bconversion\s+price\b[^.$]{0,40}$", before):
        return "conversion"
    if re.search(r"(?i)(?:exercise\s+price\s+of|exercisable\s+(?:at\s+(?:a\s+price\s+of\s+)?|for[^.$]{0,40}?at\s+(?:a\s+price\s+of\s+)?)"
                 r"|warrant\s+(?:share\s+)?at\s+(?:a\s+price\s+of\s+)?)\s*(?:approximately\s+)?$", near):
        return "strike"
    if re.search(r"(?i)\bwarrants?\b[^.$]{0,160}"
                 r"(?:purchase|acquire|exercis\w*|entitl\w*)[^.$]{0,90}(?:at\s+(?:a\s+price\s+of\s+)?|price\s+of\s+)$", before) \
            and not re.match(r"(?i)\s*per\s+(?:FT\s+|flow-through\s+|NFT\s+|hard[\s\-]dollar\s+)?units?\b", after):
        return "strike"
    if re.search(r"(?i)\bprice\s+per\s+(?:\w+\s+){0,3}warrant\s+shares?\s+of\s+(?:approximately\s+)?$", near) \
            and v is not None and v < 1000:
        return "strike"                                   # 1.0.2: "at a price per Warrant Share of $0.85"
    if re.search(r"(?i)\bexercis\w*[^$]{0,60}$|\bexercise\s+price\b[^$]{0,80}$", before[-140:]) and v is not None and v < 1000 \
            and not re.match(r"(?i)\s*per\s+(?:FT\s+|flow-through\s+|NFT\s+|hard[\s\-]dollar\s+)?units?\b", after):
        return "strike"
    if _RE_PER.match(after) or _RE_PER.match(after_wide) or re.match(r"(?i)\s*(?:\(the\s+\"?(?:offering|issue|unit|subscription)\s+price)", after):
        return "price" if v is not None and v < 1000 else "other"
    if v is not None and v < 1000 and re.match(r"(?i)\s*(?:FT\s+|NFT\s+|HD\s+|hard[\s\-]dollar\s+|flow-through\s+)?(?:unit|share|receipt|debenture)s?\b", after) \
            and not re.search(r"(?i)\b(?:exercis\w*|conver\w*|strike)\b[^.$]{0,40}$", near):
        return "price"                                    # 1.0.2: "structured as a $0.05 Unit"
    if re.search(r"(?i)\bprice\s+per\s+(?:(?!warrant)\w+\s+){0,3}(?:share|unit|receipt|debenture)s?\s+of\s+(?:approximately\s+)?$", near) \
            and v is not None and v < 1000:
        return "price"                                    # 1.0.2: "at a price per FT Share of $0.40"
    if re.search(r"(?i)\bat\s+(?:a\s+(?:deemed\s+)?price\s+of\s+)?$", near) and v is not None and v < 1000 \
            and re.search(r"(?i)\b(?:units?|shares?|FT\s+shares?|common\s+shares?)\b[^.$]{0,60}$", before):
        return "price"
    if v is not None and v < 1000:
        return "other"
    if re.match(r"(?i)\s*(?:in\s+)?(?:cash\s+)?(?:finders?'?|finder's|commissions?|fees?|as\s+(?:a\s+)?finder)", after):
        return "other"
    if re.match(r"(?i)\s*(?:\(\s*[^)]{0,20}\)\s*)?(?:(?:equity|non-brokered|brokered|flow-through|strategic|LIFE|hard[\s\-]dollar|"
                r"unit|concurrent)\s+){0,3}(?:private\s+placement|offering|financing|bought\s+deal)", after):
        return "deal"
    if _RE_NOT_DEAL_AMT_BEFORE.search(before[-110:]):
        return "other"
    return "deal"


# ------------------------------------------------------------------ is it the company's own financing?
_RE_RESULTS = G.__dict__.get("_RESULTS_HEAD") or re.compile(
    r"(?i)\b(?:Q[1-4]|first|second|third|fourth|full|quarter(?:ly)?|annual|year[\s\-]end|semi[\s\-]annual|"
    r"half[\s\-]year|fiscal|interim|H[12])\b[^|]{0,40}?\b(?:results|financial\s+statements|financials|MD&A|"
    r"activities\s+report|operating\s+and\s+financial)\b|\bfinancial\s+results\b")
_RE_DEAL_WORDS = re.compile(
    r"(?i)\b(?:clos(?:es|ed|ing)\s+(?:of\s+)?(?:\S+\s+){0,6}?(?:private\s+placement|offering|financing|tranche)"
    r"|private\s+placements?|financings?|offerings?|bought\s+deal|flow[\s\-]through|LIFE|tranche|subscription\s+receipts?"
    r"|debentures?|loan|credit\s+facilit\w*|notes\s+offering|raises?|prospectus|strategic\s+investment|equity\s+investment)\b")
_RE_NOT_FIN_HEAD = re.compile(
    r"(?i)\b(?:warrants?\s+(?:exercise|extension|repric\w*|amendment|expiry|acceleration|incentive)"
    r"|(?:exercise|extension|repricing|acceleration|expiry)\s+of\s+(?:\w+\s+){0,3}warrants?"
    r"|extends?\s+(?:\w+\s+){0,3}warrants?|reprices?\s+(?:\w+\s+){0,3}warrants?|accelerat\w*\s+(?:\w+\s+){0,3}warrants?"
    r"|shares?\s+for\s+debt|debt\s+settlement|settles?\s+(?:\w+\s+){0,3}debt|interest\s+(?:payment|shares)"
    r"|normal\s+course\s+issuer\s+bid|NCIB|congratulat\w*|option\s+agreement|options?\s+grant|grants?\s+(?:of\s+)?"
    r"(?:stock\s+)?options|RSUs?\b|DSUs?\b|restricted\s+share\s+units|share\s+consolidation|name\s+change"
    r"|receives?\s+proceeds\s+from\s+(?:the\s+)?(?:exercise|warrant)|early\s+warning"
    r"|(?:extension|amendment|maturity|conversion|repayment|redemption)s?\s+(?:and\s+(?:extension|amendment)\s+)?of\s+(?:\w+\s+){0,3}(?:convertible\s+)?(?:debentures?|notes?|loans?)"
    r"|(?:extends?|amends?)\s+(?:\w+\s+){0,3}(?:convertible\s+)?(?:debentures?|notes|loan)\b(?!\s+(?:financing|offering))"
    r"|replacement\s+(?:convertible\s+)?debentures?|debentures?\s+conversion|conversion\s+of\s+(?:\w+\s+){0,3}debentures?"
    r"|proxy|dissident|vote\s+count|to\s+acquire\s+(?:an?\s+|additional\s+)?(?:\S+\s+){0,5}(?:stream|royalty|NSR)\b"
    r"|grant\s+funding|government\s+(?:grant|funding)|emissions\s+reduction\s+alberta|funding\s+from\s+(?:the\s+)?(?:government|province|ministry|NRCan|emissions))\b")
# the company putting money into someone else
_RE_PROVIDER_HEAD = re.compile(
    r"(?i)\b(?:invests?\s+(?:\w+\s+){0,3}in\b|investment\s+in\s+(?!(?:the\s+)?company\b)[A-Z]|strategic\s+investment\s+in\b"
    r"|(?:financing|funding|loan)\s+(?:package|agreement|facility)\s+(?:with|to|for)\b"
    r"|provides?\s+(?:\w+\s+){0,3}(?:financing|loan|funding)\s+to|acquires?\s+(?:\w+\s+){0,4}shares?\s+of"
    r"|participates?\s+in\s+(?:\w+\s+){0,4}(?:private\s+placement|financing|offering)|subscribes?\s+(?:for|to)\b"
    r"|acquisition\s+of\s+(?:\w+\s+){0,3}(?:subscription\s+receipts|shares|units|securities)\s+of\b)")
_RE_RECEIVER_HEAD = re.compile(r"(?i)\b(?:from|by|led\s+by|secures?|receives?|closes?|completes?|arranges?|announces?\s+\$)\b")
_RE_PROVIDER_BODY = re.compile(
    r"(?i)\b(?:has\s+acquired|will\s+provide|has\s+agreed\s+to\s+provide|to\s+provide\s+(?:up\s+to\s+)?(?:US|A|C)?\$|will\s+invest|has\s+invested"
    r"|has\s+agreed\s+to\s+(?:invest|subscribe|lend|advance)|will\s+subscribe\s+for|lend\s+to|advance\s+to|to\s+fund\s+(?:its\s+)?(?:partner|investee))\b")
_RE_ACQ_HEAD = re.compile(
    r"(?i)\b(?:acquisition|acquires?|earn[\s\-]?in|option\s+to\s+acquire|arrangement|merger|amalgamation|drill\w*|assays?"
    r"|intercepts?|results?|exploration|geophysic\w*|sampling|resource\s+estimate|PEA|feasibility|permit\w*|AGM"
    r"|annual\s+general\s+meeting|listing|trading|appoint\w*|update)\b")


_RE_HEAD_FIN_EXTRA = re.compile(
    r"(?i)\b(?:(?:final|preliminary|amended)\s+(?:base\s+shelf\s+)?(?:short[\s\-]form\s+)?prospectus|prospectus\s+supplement|financial\s+support\s+from|(?:term\s+)?loan\s+commitment|financing\s+commitment|funding\s+commitment"
    r"|commitment\s+letter\s+for|equity\s+commitment|investment\s+(?:agreement\s+)?(?:from|by|with)\s+[A-Z]|lead\s+order|strategic\s+investment(?!\s+in\b))\b")


def financing_decision(h: str, window: str, role: str):
    """(is_financing, reason). h: effective headline; window: deal window (flat)."""
    lede = window[:1500]
    head_deal = bool(G._fin_noun(h) or G._RE_MONEY_NOUN.search(h) or G._RE_DEAL_EXTRA.search(h) or _RE_HEAD_FIN_EXTRA.search(h))
    if _RE_RESULTS.search(h) and not _RE_DEAL_WORDS.search(h):
        return False, "results"
    if re.search(r"(?i)\bnon[\s\-]offering\s+prospectus\b", h + " " + lede[:900]) and not re.search(
            r"(?i)\b(?:concurrent|private\s+placement|bought\s+deal|offering\s+of\s+(?:units|shares))\b", h):
        return False, "non_offering_prospectus"    # 1.0.3: capacity to list, no securities sold
    if re.search(r"(?i)\b(?:exercise\s+of\s+(?:the\s+|its\s+)?(?:\w+\s+){0,2}(?:over[\s\-]allotment|underwriters?'?|agents?'?|greenshoe|option)"
                 r"|(?:over[\s\-]allotment|underwriters?'?|agents?'?)\s+option)\b", h) and re.search(r"(?i)\bproceeds|offering|placement|US?\$|C\$|\$", h + " " + lede[:600]):
        return True, "option_exercise"
    if _RE_NOT_FIN_HEAD.search(h) and not re.search(
            r"(?i)\b(?:private\s+placements?|offering|bought\s+deal|flow[\s\-]through\s+(?:financing|placement|offering)"
            r"|LIFE\s+(?:offering|financing)|(?:debenture|unit|equity|convertible|flow-through)\s+financing|announces\s+(?:\w+\s+){0,3}financing|PP)\b|\$[\d.,]+\s*(?:million|m)?\s+financing\b", h):
        return False, "not_a_raise"
    ph = _RE_PROVIDER_HEAD.search(h)
    pb = _RE_PROVIDER_BODY.search(lede[:1200])
    if pb and re.search(r"(?i)\b(?:to|in|into)\s+(?:the\s+)?company\b|\bthe\s+company\s+will\s+receive", lede[pb.start():pb.end() + 140]):
        pb = None                                             # someone providing money TO the company
    if ph and pb and not re.search(r"(?i)\b(?:from|by|led\s+by|into\s+(?:the\s+)?company)\b", h) \
            and not re.search(r"(?i)\b(?:private\s+placement|bought\s+deal|flow-through|LIFE\s+offering|offering\s+of\s+(?:units|shares))\b", h):
        return False, "invests_in_other"
    if head_deal:
        if G._RE_NOT_ANNOUNCE.search(h) and not re.search(
                r"(?i)\b(?:clos\w*|complet\w*|upsiz\w*|increas\w*|amend\w*|terminat\w*|tranche|announces?\s+(?:a\s+)?(?:\$|non|brokered|private|flow|LIFE|bought))\b", h):
            # "Provides Update on Proposed Private Placement": still the deal, an update
            return True, "update_head"
        return True, "headline"
    if _RE_ACQ_HEAD.search(h) and not re.search(
            r"(?i)\b(?:concurrent|private\s+placement|financing|offering)\b", lede[:600]):
        return False, "other_topic"
    # headline says nothing about money: the lede must announce or close the company's own deal
    if re.search(r"(?i)\b(?:announces?|pleased\s+to\s+announce|has\s+(?:closed|completed)|intends\s+to\s+complete|"
                 r"has\s+arranged|proposes)\b[^.]{0,160}\b(?:private\s+placements?|offering|financing|flow-through|"
                 r"bought\s+deal|convertible\s+debentures?|credit\s+facility|loan)\b", lede[:900]) \
            and (monies(lede[:1500])):
        return True, "lede"
    return False, "no_deal"


# ------------------------------------------------------------------ role
_RE_UPDATE_HEAD = re.compile(
    r"(?i)\b(?:fully\s+subscribed|over[\s\-]?subscribed\b(?![^|]*\bclos)|conditional\s+(?:acceptance|approval)"
    r"|receives?\s+(?:tsx\w*\s+|cse\s+|exchange\s+)?(?:conditional\s+)?(?:acceptance|approval)"
    r"|(?:final|amended)\s+(?:base\s+shelf\s+)?(?:short[\s\-]form\s+)?prospectus|prospectus\s+supplement"
    r"|files?\s+(?:a\s+|its\s+)?(?:final|amended)|updates?\s+(?:on|to|regarding)|provides?\s+(?:an\s+)?update"
    r"|extends?\s+(?:the\s+)?(?:closing|deadline|price\s+protection)|extension\s+of\s+(?:\w+\s+){0,5}(?:closing|placement|offering|financing)"
    r"|clos(?:ing|e)\s+dates?\s+extend\w*|to\s+close\b|will\s+close|expected\s+to\s+close|closing\s+(?:date|scheduled)"
    r"|pricing\s+of|prices\s+(?:its\s+)?(?:previously|offering|bought))")


_RE_LEDE_CLOSED = re.compile(
    r"(?i)\b(?:has|have)\s+(?:now\s+)?(?:successfully\s+)?(?:closed|completed|issued)\b|\bannounces?\s+(?:the\s+)?(?:successful\s+)?"
    r"(?:closing|completion|close)\s+of\b|\bpleased\s+to\s+announce\s+(?:the\s+)?(?:successful\s+)?(?:closing|completion)\b"
    r"|\bcloses\s+\$|\bclosed\s+(?:a|its|the)\s+(?:\S+\s+){0,4}(?:private\s+placement|offering|financing|tranche)")
_RE_LEDE_ANNOUNCE = re.compile(
    r"(?i)\b(?:intends?\s+to\s+(?:complete|close|undertake|conduct|raise|proceed)|proposes?\s+to|will\s+proceed\s+(?:to|with)"
    r"|is\s+pleased\s+to\s+announce\s+(?:that\s+it\s+(?:has\s+(?:arranged|entered|agreed)|intends|proposes|will)|(?:a|an|its)\s+(?:proposed\s+)?(?:\S+\s+){0,4}"
    r"(?:private\s+placement|offering|financing|bought\s+deal))|has\s+(?:arranged|launched)|(?:has\s+)?entered\s+into\s+an?\s+(?:agreement|engagement\s+letter)"
    r"\s+with\s+[^.]{0,80}\b(?:underwriters?|agents?|lead|bookrunner)|announces?\s+(?:a|an|its)\s+(?:proposed\s+)?(?:\S+\s+){0,3}(?:private\s+placement|offering|financing)"
    r"|(?:plans|proceeding)\s+(?:to|with)\s+(?:a|an)\s+(?:\S+\s+){0,3}(?:private\s+placement|financing))")


def _lede_role(window):
    """Role from the deal's first sentences, for headlines the grammar cannot read."""
    L = window[:1200]
    mc, ma = _RE_LEDE_CLOSED.search(L), _RE_LEDE_ANNOUNCE.search(L)
    if not mc and not ma:
        for sm in re.finditer(r"[^.]*\b(?:private\s+placement|offering|financing)\b[^.]*\.", window[:3000]):
            sent = sm.group(0)
            if _RE_LEDE_ANNOUNCE.search(sent):
                return "announcement"
            if _RE_LEDE_CLOSED.search(sent) and G._close_is_financing(sent):
                return "final_close"
    if mc and not re.search(r"(?i)\b(?:will|expects?\s+to|anticipat\w*|intends?\s+to|subject\s+to)\b", L[max(0, mc.start() - 40):mc.start()]) \
            and (not ma or mc.start() < ma.start()) and G._close_is_financing(L[max(0, mc.start() - 60):mc.end() + 200]):
        tr = re.search(r"(?i)\b(?:first|second|third|fourth|initial|1st|2nd|3rd)\s+(?:and\s+final\s+)?tranche|\btranche\b", L[mc.start():mc.end() + 150])
        if tr and not re.search(r"(?i)\bfinal\b", tr.group(0)):
            return "tranche_close"
        return "final_close"
    if ma:
        return "announcement"
    return None


def classify(h: str, window: str):
    """(role, tranche_label) with FIN_V1's changes on top of the v3 grammar."""
    role, tranche = G.classify_role(h, window[:4000])
    if role == "mention":
        role = "update"
        um = _RE_UPDATE_HEAD.search(h)
        strong_update = bool(um) and not re.search(r"(?i)\bannounces?\b[^|]{0,40}\b(?:fully|over)[\s\-]?subscribed", h) and not (
            re.match(r"(?i)update\s+on|provides?\s+(?:an\s+)?update", um.group(0)) and not re.search(
                r"(?i)\bupdat\w*\s+(?:on|to|regarding)\s+(?:its\s+|the\s+)?(?:\w+\s+){0,3}(?:private\s+placement|offering|financing|closing|tranche)", h))
        if not strong_update:
            lr = _lede_role(window)
            if lr:
                role = lr
    if role == "update" and re.search(r"(?i)\b(?:approv\w*|acceptance|permission)\s+to\s+close\b", h) and re.search(r"(?i)\bhas\s+(?:now\s+)?(?:issued|closed|completed)\b", window[:900]):
        role = "final_close"
    if role == "announcement" and "$" not in h and not re.search(r"(?i)\b(?:propos\w*|intend\w*|intention|plans?|launch\w*|million|up\s+to|upsiz\w*|increas\w*)\b", h):
        lr = _lede_role(window[:700])
        mc = _RE_LEDE_CLOSED.search(window[:700])
        if lr in ("final_close", "tranche_close") and mc and not re.search(r"(?i)\balso\b|\bprevious\s+(?:offering|placement|financing)", window[max(0, mc.start() - 30):mc.end() + 60]):
            role = lr
    if role == "final_close" and re.search(r"(?i)\bcloses\s+(?:an?\s+)?initial\b|\binitial\s+(?:US|C|CA)?\$", h):
        role = "tranche_close"
    if role in ("announcement", "update") and re.search(r"(?i)\b(?:private\s+placement|offering|financing)\s+(?:increase|upsize)d?\s+to\b|\bincreas\w*\s+(?:to|size\s+to)\s+(?:US|C|CA)?\$", h):
        role = "upsize"
    if role in ("announcement", "update") and re.search(r"(?i)\b(?:price\s+adjustment|re-?pric(?:es|ing|ed)|repris(?:es|ing)|revised\s+pricing|amended\s+terms)\b", h):
        role = "amendment"
    if role == "update" and re.search(r"(?i)\b(?:reduc(?:es|ed|tion)|decreas(?:es|ed)|downsiz\w*)\s+(?:\w+\s+){0,6}(?:size|private\s+placement|offering|financing)\b|\bsize\s+of\s+(?:\w+\s+){0,5}(?:reduced|decreased)", h + " " + window[:800]):
        role = "amendment"
    if role == "final_close" and re.search(
            r"(?i)\b(?:first|initial)\s+(?:closing|close)\b|\bintends?\s+to\s+(?:proceed\s+with|close|complete)\s+(?:a\s+|the\s+)?(?:second|subsequent|additional|further)\s+(?:and\s+final\s+)?tranche",
            h + " " + window[:1500]) and not re.search(
            r"(?i)\bfinal\s+(?:tranche|clos(?:e|ing))\b|\band\s+final\s+tranche\b|\bcompleted\s+its\s+final\b", h + " " + window[:1500]):
        role = "tranche_close"
    if role == "update" and re.search(r"(?i)\b(?:receives?|secures?|obtains?)\s+(?:\w+\s+){0,3}(?:financial\s+support|commitments?|investment|financing|funding|loan)\b", h) \
            and not re.search(r"(?i)\bupdat\w*", h):
        role = "announcement"
    if re.search(r"(?i)\b(?:full\s+)?exercise\s+of\s+(?:the\s+|its\s+)?(?:\w+\s+){0,2}(?:over[\s\-]allotment|underwriters?'?|agents?'?|greenshoe)?\s*option\b", h) \
            and re.search(r"(?i)\bproceeds|clos", h + " " + window[:600]) and role not in ("final_close", "tranche_close"):
        role = "tranche_close"
    if role in ("announcement", "amendment", "upsize") and re.search(
            r"(?i)\b(?:files?|filing\s+of)\s+(?:\w+\s+){0,3}(?:prospectus\s+supplement|final\s+(?:short[\s\-]form\s+)?prospectus)", h):
        return "update", tranche
    if role in ("announcement", "amendment") and _RE_UPDATE_HEAD.search(h) and not re.search(
            r"(?i)\b(?:announces?\s+(?:a\s+)?(?:\$|up\s+to|non[\s\-]brokered|brokered|private|flow|LIFE|bought|proposed|fully\s+subscribed|over[\s\-]?subscribed|(?:US|C|CA)\$)"
            r"|amends?\s+(?:the\s+)?(?:terms|pric\w*|private|offering|financing)|upsiz\w*|increas\w*)\b", h):
        if not re.search(r"(?i)\bpreliminary\s+(?:short[\s\-]form\s+|base\s+shelf\s+)?prospectus\b", h):
            role = "update"
    if role == "announcement" and re.search(
            r"(?i)\bfurther\s+to\s+(?:its|the\s+company's|our)\s+(?:news|press)\s+releases?\b|\bpreviously\s+announced\b",
            window[:500]) and not re.search(r"(?i)\b(?:announces?|arranges?|proposes?|launch\w*)\b[^|]{0,60}"
                                            r"\b(?:new|second|additional)\b", h) and _RE_UPDATE_HEAD.search(h + " " + window[:300]):
        role = "update"
    # 1.0.2 role wording
    if re.search(r"(?i)\b(?:cancell?\w*|withdraw\w*|rescind\w*|terminat\w*)\b", h) and G._fin_noun(h):
        role = "terminated"
    elif re.search(r"(?i)\bwill\s+not\s+(?:be\s+)?proceed\w*\s+with\b[^.]{0,80}(?:private\s+placement|offering|financing)",
                   window[:900]) and role in ("update", "mention"):   # a release that also announces its own raise is that announcement
        role = "terminated"
    if role in ("tranche_close", "update") and re.search(
            r"(?i)\b(?:final|last)\s+clos(?:e|ing)\b(?!\s+(?:amounts?|figures?|numbers?|conditions?|costs?|dates?|prices?|process))"
            r"|\bcompleted\s+its\s+final\b", h + " " + window[:900]) \
            and not re.search(r"(?i)\b(?:first|initial|second|third)\s+(?:and\s+final\s+)?tranche\s+(?:of\s+)?(?:the\s+)?(?:offering|placement)\s+(?:is|are)\s+expected", window[:900]) \
            and not re.search(r"(?i)\bexpects?\s+to\s+(?:complete|close)\s+(?:an?\s+)?(?:additional|further|second|another|final)\b", window[:1500]):
        role = "final_close"
    if role == "final_close" and re.search(
            r"(?i)\bclosed\s+(?:an?|another)\s+(?:additional|further|subsequent)\s+tranche\b|\ban?\s+additional\s+tranche\s+of\b", window[:900]) \
            and not re.search(r"(?i)\bfinal\s+tranche\b|\band\s+final\b", h + " " + window[:600]):
        role = "tranche_close"
    if role in ("announcement", "update") and re.search(
            r"(?i)\bincreas(?:e|es|ed|ing)\b[^|]{0,40}\b(?:private\s+placement|offering|financing|raise)\b"
            r"|\b(?:private\s+placement|offering|financing)\b[^|]{0,30}\bincreas(?:e|ed|ing)\b", h):
        role = "upsize"
    # 1.0.3: a release that closes a tranche AND upsizes the offering is a tranche close --
    # the money that moved is the tranche; the new size is the offering's, not what was raised.
    if role == "upsize":
        mt = _RE_CLOSE_TRANCHE.search(h)
        if mt:
            role = "tranche_close"
            tranche = (mt.group(1) or "").lower() or tranche
            if tranche == "initial":
                tranche = "first"
    # 1.0.3: "Closes Private Placement" while the body still expects a further tranche
    if role == "final_close" and _RE_MORE_TRANCHES.search(window[:2000]) and not re.search(
            r"(?i)\bfinal\s+(?:tranche|clos(?:e|ing))\b|\band\s+final\s+tranche\b", h):
        role = "tranche_close"
    # 1.0.3: "Announces Correction to Warrant Terms of ..." changes terms, it does not raise or upsize
    if re.search(r"(?i)\b(?:announces?\s+)?correction\s+to\b|\bcorrects?\s+(?:the\s+)?(?:warrant\s+)?terms\b", h) \
            and role in ("upsize", "announcement", "update"):
        role = "amendment"
    # 1.0.3: repricing STOCK OPTIONS is not an amendment of the financing announced in the same release
    if role == "amendment" and re.search(r"(?i)\bre-?pric\w*\s+(?:of\s+)?(?:its\s+|the\s+)?(?:outstanding\s+)?(?:stock\s+)?options?\b", h) \
            and not re.search(r"(?i)\bre-?pric\w*\s+(?:of\s+)?(?:its\s+|the\s+)?(?:\w+\s+){0,3}(?:private\s+placement|offering|financing)", h):
        role = "announcement" if re.search(r"(?i)\bannounces?\b", h) else "update"
    # 1.0.3: the first disclosure of an offering's price is that offering's announcement
    if role == "update" and re.search(r"(?i)\bpricing\s+of\b|\bprices\s+(?:its\s+)?(?:\w+\s+){0,3}(?:offering|placement)", h) \
            and not re.search(r"(?i)\bpreviously\s+announced\b|\bfurther\s+to\b", window[:600]):
        role = "announcement"
    # 1.0.3: "Announces Additional Investment from <investor>" announces a new subscription
    if role == "update" and G._RE_DEAL_EXTRA.search(h) and re.search(r"(?i)\bannounces?\b", h) \
            and not G._RE_NOT_ANNOUNCE.search(h) and not _RE_UPDATE_HEAD.search(h):
        role = "announcement"
    # 1.0.5: "Announces Revised Terms of ...", "Price Change for its Proposed Private Placement", "has revised the terms of its"
    if role in ("announcement", "update") and (_RE_AMEND_HEAD.search(h) or _RE_AMEND_LEDE.search(window[:700])):
        role = "amendment"
    return role, tranche


# 1.0.5: the release changes the terms or the price of an offering it announced before
_RE_AMEND_HEAD = re.compile(
    r"(?i)\b(?:revis(?:ed|es|ion\s+(?:of|to))\s+(?:the\s+)?(?:\w+\s+){0,2}terms|price\s+(?:change|amendment|revision)"
    r"|chang(?:e|es)\s+(?:to|in)\s+(?:the\s+)?(?:\w+\s+){0,2}(?:terms|pric(?:e|ing))\s+(?:of|for)"
    r"|amend(?:s|ed|ment\s+(?:of|to))\s+(?:the\s+)?(?:\w+\s+){0,2}terms\s+(?:of|for)"
    r"|modif(?:ies|ied|ication\s+(?:of|to))\s+(?:the\s+)?(?:\w+\s+){0,2}terms)\b")
_RE_AMEND_LEDE = re.compile(
    r"(?i)\b(?:(?:has|have)\s+(?:revised|amended|modified|changed)\s+the\s+terms\s+of|update\s+on\s+the\s+terms\s+of"
    r"|is\s+repricing|has\s+repriced)\s+(?:its|the)\s+(?:previously\s+announced\s+)?(?:[\w\-]+\s+){0,3}"
    r"(?:private\s+placement|offering|financing)")
# 1.0.5: money drawn under a loan or credit facility that already exists is an update of that deal, not its close
_RE_DRAWDOWN = re.compile(
    r"(?i)\b(?:drawn\s+down|drew\s+down|draws?\s+down|drawdown\s+of|draw\s+of|received\s+(?:an?\s+|the\s+)?(?:\w+\s+){0,3}(?:advance|drawdown))\b"
    r"[^.]{0,160}\bunder\b[^.]{0,60}\b(?:facility|loan|credit|agreement)\b")


# 1.0.3: a close verb applied to a tranche, in a headline the grammar read as an upsize
_RE_CLOSE_TRANCHE = re.compile(
    r"(?i)\b(?:clos(?:es|ed|ing)|completes?|completed|completion)\b(?:\s+(?:of|the|its|a|an))?"
    r"(?:\s+(?!and\b)[\w$,.\-]+){0,6}?\s+(first|second|third|fourth|fifth|initial|final)?\s*tranche\b")
# 1.0.3: the body says another tranche is still to come
_RE_MORE_TRANCHES = re.compile(
    r"(?i)\b(?:expects?|anticipat\w*|intends?|plans?|hopes?)\s+to\s+(?:be\s+able\s+to\s+)?(?:clos\w*|complet\w*|announce)\b"
    r"[^.]{0,90}?\b(?:second|third|fourth|subsequent|additional|further|final)\b[^.]{0,30}?\btranche"
    r"|\b(?:second|third|subsequent|additional|further)\s+(?:and\s+final\s+)?tranche\b[^.]{0,80}?"
    r"\b(?:expected|anticipated|to\s+close|in\s+the\s+near\s+term|to\s+follow|shortly)\b")

# ------------------------------------------------------------------ type
_RE_T_FT = re.compile(r"(?i)\bflow-through\b|\bFT\s+(?:shares?|units?)\b|\bcharity\s+flow")
_RE_T_LIFE = re.compile(r"(?:\bLIFE\b(?!\s+of\s+mine)|(?i:listed\s+issuer\s+financing))")
_RE_T_CD = re.compile(r"(?i)(?<!non-)\bconvertible\s+(?:senior\s+)?(?:secured\s+|unsecured\s+)?(?:debentures?|notes?|loans?|promissory\s+notes?|bonds?)\b|\bdebenture\s+(?:financing|offering|units?)\b")
_RE_T_DEBT = re.compile(
    r"(?i)\b(?:senior\s+(?:secured\s+|unsecured\s+)?notes|notes?\s+offering|credit\s+(?:facility|agreement)|loan(?:\s+facility|\s+agreement)?"
    r"|debt\s+(?:financing|facility)|term\s+(?:loan|facility)|revolving\s+(?:credit\s+)?facility|bonds?\b|project\s+(?:debt|finance\s+facility)"
    r"|(?:gold\s+)?pre[\s\-]?pay(?:ment)?\s+(?:facility|agreement|financing)|bridge\s+(?:loan|facility)|non-convertible\s+debentures?|corporate\s+note\s+units?"
    r"|standby\s+facility|(?:secured|senior|promissory)\s+notes?)\b")
_RE_T_IPO = re.compile(r"(?i)\binitial\s+public\s+offering\b|\bIPO\b")
_RE_T_ATM = re.compile(r"(?i)\bat[\s\-]the[\s\-]market\b|\bATM\s+(?:equity\s+)?(?:program|offering)|\bequity\s+distribution\s+agreement")
_RE_T_STREAM = re.compile(r"(?i)\b(?:stream(?:ing)?\s+(?:agreement|financing|transaction|deal)|(?:gold|silver|copper|precious\s+metals?)\s+stream|royalty\s+financing|sale\s+of\s+(?:a\s+)?(?:\S+\s+)?royalty)\b")
_RE_T_PP_UNITS = re.compile(r"(?i)\b(?:non-flow-through|hard[\s\-]dollar|NFT)\s+(?:units?|shares?)\b|\bunits?\b(?![\s\-]+(?:of\s+)?flow)|\bcommon\s+shares\b")
_RE_O_BOUGHT = re.compile(r"(?i)\bbought[\s\-]deal\b")
_RE_O_NON = re.compile(r"(?i)\bnon-brokered\b|\bnon\s+brokered\b|\bnonbrokered\b")
_RE_O_BROKER = re.compile(
    r"(?i)(?<!non-)(?<!non )\bbrokered\b|\b(?:as\s+)?(?:lead\s+|sole\s+)?(?:agents?|underwriters?|bookrunners?)\b(?!'?s?\s+(?:option|fee|warrant|commission))"
    r"|\bbest[\s\-]efforts\b|\bmarketed\s+(?:private\s+placement|offering|public\s+offering)\b|\bagency\s+agreement\b|\bunderwriting\s+agreement\b")


def _terms_sentences(window, rx, limit=3000):
    """True when rx appears in a sentence that states the offering's terms (a price, proceeds or units offered)."""
    for m in rx.finditer(window[:limit]):
        sent = _sentence(window, m.start(), m.end())
        if re.search(r"(?i)\bprevious(?:ly)?\s+(?:closed|completed)|\blast\s+year\b|\bprior\s+(?:financing|placement)", sent):
            continue
        if re.search(r"(?i)\$\s?\d|\bgross\s+proceeds\b|\bper\s+(?:FT\s+)?(?:unit|share)\b|\b(?:up\s+to\s+)?[\d,]{5,}\s+(?:\w+\s+){0,3}(?:units?|shares?)\b", sent):
            return True
    return False


def deal_types(h: str, window: str, h_main: str = None):
    """(sorted type tokens, offering or None). Headline first, then the deal's own terms."""
    w = window[:1800]
    both = h + " \n " + w[:700]
    types = set()
    if _RE_T_FT.search(both) or _terms_sentences(window, _RE_T_FT):
        types.add("FT")
    if _RE_T_LIFE.search(h) or _RE_T_LIFE.search(w) or re.search(r"(?i)listed\s+issuer\s+financing\s+exemption|\bLIFE\s+(?:offering|exemption)", window[:4500]):
        types.add("LIFE")
    cd_h = _RE_T_CD.search(h)
    if cd_h or (_RE_T_CD.search(w[:700]) and not (_RE_T_FT.search(h) or _RE_T_LIFE.search(h))):
        types.add("CD")
    debt_h = _RE_T_DEBT.search(h)
    if debt_h and "CD" not in types:
        types.add("DEBT")
    elif not G._fin_noun(h) and _RE_T_DEBT.search(w[:400]) and "CD" not in types and not re.search(
            r"(?i)private\s+placement|flow-through|offering\s+of\s+(?:units|shares)", w[:400]):
        types.add("DEBT")
    if _RE_T_IPO.search(h):
        types.add("IPO")
    if _RE_T_ATM.search(h) or (_RE_T_ATM.search(w[:500]) and not G._fin_noun(h)):
        types.add("ATM")
    if _RE_T_STREAM.search(h):
        types.add("STREAM")
    if not types or ("FT" in types and re.search(
            r"(?i)\b(?:non-flow-through|hard[\s\-]dollar|NFT)\s+(?:units?|shares?|common\s+shares?)\b|\(non-flow-through\)\s+units?", both[:2200])):
        types.add("PP")
    if types == {"DEBT", "PP"} and not re.search(r"(?i)\b(?:equity\s+)?private\s+placement|subscription\s+receipts|equity\s+(?:investment|financing)", both[:1600]):
        types = {"DEBT"}
    if "DEBT" in types and "PP" not in types and re.search(r"(?i)\bequity\s+private\s+placement|\bprivate\s+placement\s+of\s+(?:common\s+shares|subscription\s+receipts)", w[:1500]):
        types.add("PP")
    offering = None
    for text in (h_main or h, w[:1200], w):
        mb, mn, mk = _RE_O_BOUGHT.search(text), _RE_O_NON.search(text), _RE_O_BROKER.search(text)
        if mb:
            offering = "BOUGHT_DEAL"
            break
        if mn and (not mk or mn.start() <= mk.start()):
            offering = "NON_BROKERED"
            break
        if mk and not mn:
            offering = "BROKERED"
            break
        if mk and mn:
            offering = "NON_BROKERED" if mn.start() < mk.start() else "BROKERED"
            break
    if types & {"DEBT", "STREAM", "ATM"} and offering == "BROKERED" and not re.search(r"(?i)\bbrokered\b|\bbought\b", both):
        offering = None
    return sorted(types), offering


# ------------------------------------------------------------------ amounts
# 1.0.3: the new size of an upsized offering, stated only in the body
_RE_UPSIZED_TO = re.compile(
    r"(?i)\b(?:(?:will\s+)?now\s+rais(?:e|es|ing)|rais(?:e|es|ing)\s+(?:a\s+total\s+of\s+)?up\s+to"
    r"|(?:increas(?:e|es|ed|ing)|upsiz(?:e|es|ed|ing)|expand(?:s|ed)?)\s+(?:(?!from\b)[\w\-]+\s+){0,12}?(?:to|up\s+to)"
    r"|(?:new|revised|amended|increased|upsized)\s+(?:maximum\s+)?(?:aggregate\s+)?(?:gross\s+)?(?:offering\s+size|proceeds|size)\s+(?:of|to)"
    r"|maximum\s+(?:aggregate\s+)?gross\s+proceeds\s+of)\s+"
    r"(?:approximately\s+|up\s+to\s+|a\s+maximum\s+of\s+|gross\s+proceeds\s+of\s+)*"
    + G._CUR + r"\s?(?=\d)")

_CUR_NG = G._CUR.replace("?P<cur>", "?:")                     # the same currency alternation, without the group name
_RE_FROM_TO = re.compile(
    r"(?i)\b(?:upsiz(?:e|es|ed|ing)|increas(?:e|es|ed|ing)|expand(?:s|ed)?|rais(?:e|es|ed|ing))\b[^.]{0,120}?"
    r"\bfrom\b\s*" + _CUR_NG + r"\s?[\d,.]+\s*(?:million|m\b|bn\b|billion)?\s*\bto\b\s*" + _CUR_NG + r"\s?(?=\d)")

_RE_UPTO = re.compile(r"(?i)\b(?:up\s+to|maximum\s+of|a\s+maximum|not\s+to\s+exceed|of\s+up\s+to)\s+(?:an?\s+aggregate\s+of\s+|approximately\s+|gross\s+proceeds\s+of\s+)?$")
_RE_ADDITIONAL = re.compile(r"(?i)\b(?:additional|further|over[\s\-]allotment|agents?'?\s*'?s?\s+option|underwriters?'?\s*'?s?\s+option|greenshoe)\b[^.$]{0,60}$")
# 1.0.3: the markers of an offering filed with the SEC, where a bare "$" is US dollars
_RE_SEC_FILING = re.compile(
    r"(?i)\bfiled\s+pursuant\s+to\s+rule\s+42[45]|\bregistration\s+statement\s+no\.|\brule\s+144a\b"
    r"|\bprospectus\s+supplement\b[^.]{0,140}\bsecurities\s+act\s+of\s+1933|\bform\s+(?:s-3|f-10|40-f)\b")

_RE_FT_WORD = re.compile(r"(?i)\bflow-through|\bFT\s+(?:units?|shares?)|\bcharity\s+(?:FT|flow)|\bCFT\b")
_RE_NFT_WORD = re.compile(r"(?i)non-flow-through|\bnon\s+flow-through|\bnon-FT\b|\bNFT\b|hard[\s\-]dollar|\bHD\s+units?|working\s+capital\s+units?|\bWC\s+units?")


def _part(before):
    """'FT' / 'NFT' when the nearest unit type named before a figure is one of the two, else None."""
    ft = [m.end() for m in _RE_FT_WORD.finditer(before)]
    nft = [m.end() for m in _RE_NFT_WORD.finditer(before)]
    if not ft and not nft:
        return None
    if nft and (not ft or nft[-1] >= ft[-1] - 4):
        return "NFT"
    return "FT"


_RE_TOTAL_BEFORE = re.compile(
    r"(?i)\b(?:aggregate|total|combined|cumulative)\s+(?:gross\s+)?proceeds\b[^.$]{0,90}$|\btotal\s+(?:\w+\s+){0,2}raised\s+(?:aggregate\s+)?(?:gross\s+)?proceeds\s+of\s+$|\bbringing\s+(?:the\s+)?(?:total|aggregate)\b[^.$]{0,60}$"
    r"|\bto\s+date\b[^.$]{0,40}$|\bin\s+(?:the\s+)?aggregate\s+(?:of\s+)?$|\bfor\s+(?:a\s+)?total\s+of\s+$|\bfor\s+aggregate\s+(?:gross\s+)?proceeds\s+of\s+$"
    r"|\baggregate\s+total\s+of\s+$|\b(?:raised|raising|brings?|bringing)\s+(?:an?\s+|the\s+)?(?:aggregate\s+)?total\s+(?:of\s+)?$"
    r"|\btotal\s+(?:gross\s+)?proceeds\s+raised\s+from\s+(?:both|all)\b[^.$]{0,140}$")
_RE_TOTAL_AFTER = re.compile(r"(?i)^\s*(?:\S+\s+){0,3}(?:in\s+(?:the\s+)?aggregate|to\s+date|in\s+total)\b")
_RE_CLOSE_CTX = re.compile(r"(?i)\b(?:closed|completed|closing|issued|has\s+issued|completion|raised|sold)\b")
_RE_FUTURE_CTX = re.compile(r"(?i)\b(?:will|intends?|expects?|anticipated|proposed|up\s+to|may|subject\s+to|to\s+be)\b")


def _sentence(text, start, end):
    a = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start))
    b = text.find(". ", end)
    return text[a + 1 if a >= 0 else 0: b if b >= 0 else len(text)]


_RE_COMBINED_TRANCHES = re.compile(
    r"(?i)\b(?:(?:when\s+)?combined|together)\s+with\s+(?:the\s+)?(?:proceeds\s+(?:of|from)\s+(?:the\s+)?)?"
    r"(?:(?:first|second|third|initial|previous|prior|earlier|other)\s+(?:and\s+(?:the\s+)?\w+\s+)?tranches?|tranches?\s+(?:1|one|i)\b)"
    r"|^\W*in\s+total\b")
_RE_TRANCHE_SCOPED = re.compile(r"(?i)^\W*(?:under|in|for|pursuant\s+to|with)\s+(?:the\s+|this\s+|such\s+)?(?:(?:first|second|third|fourth|fifth|final|initial)\s+)?tranche\b")


def _sentence_start(text, pos):
    a = max(text.rfind(". ", 0, pos), text.rfind("\n", 0, pos))
    return a + 1 if a >= 0 else 0


def _headline_copy(h, w):
    """(start, end) of a copy of the headline at the top of the body, or None."""
    words = re.findall(r"\w+", h)[:8]
    if len(words) < 4:
        return None
    m = re.search(r"\W+".join(map(re.escape, words)), w[:1200], re.I)
    if not m:
        return None
    return m.start(), m.start() + len(h) + 25


def amounts(h: str, window: str, role: str, head_copy: bool = True):
    """{currency, offered, offered_alt[], this_close, closed_total} as numbers or None."""
    out = {"currency": None, "offered": None, "offered_alt": [], "this_close": None, "closed_total": None}
    closing = role in ("tranche_close", "final_close")
    # headline figures
    hd = []
    for v, cur, s, e in monies(h):
        if not G.plausible_gross(v) or money_kind(h, v, s, e) != "deal":
            continue
        pre = h[max(0, s - 40):s]
        hd.append({"v": v, "cur": cur, "to": bool(re.search(r"(?i)\bto\s+(?:up\s+to\s+|an?\s+aggregate\s+of\s+|approximately\s+)?$", pre)),
                   "of": bool(re.search(r"(?i)\b(?:of|for)\s+(?:its\s+|the\s+|an?\s+)?(?:up\s+to\s+|approximately\s+)?$", pre)),
                   "closeverb": bool(re.search(r"(?i)\b(?:clos\w*|complet\w*|rais\w*)\s+(?:of\s+)?(?:an?\s+)?(?:\w+\s+){0,2}$", pre)),
                   "upto": bool(re.search(r"(?i)up\s+to\s+$", pre)),
                   "from": bool(re.search(r"(?i)\bfrom\s+(?:an?\s+)?$", pre)),
                   "pre_tranche": bool(re.match(r"(?i)\s*(?:(?:first|second|third|fourth|final|initial|1st|2nd|3rd)\s+(?:and\s+final\s+)?)?tranche\b", h[e:e + 35])),
                   "proceeds": bool(re.search(r"(?i)(?:\bproceeds|\bfinancing|\braise|\bfor|\btotal)\s+(?:of\s+)?(?:approximately\s+|approx\.?\s+|about\s+|over\s+)?$", pre)),
                   "totalword": bool(re.search(r"(?i)\b(?:total|aggregate|cumulative|combined)\b[^$]{0,30}$", pre)),
                   "tranche_of": bool(re.search(r"(?i)\btranche\s+of\s+(?:approximately\s+)?$", pre)
                                      and re.match(r"(?i)\s*(?:million\s+|m\s+)?(?:for|and|,|raising|bringing)\b", h[e:e + 20]))})
    body = []
    w = window[:4000]
    copy = _headline_copy(h, w) if head_copy and hd else None
    hvals = [x["v"] for x in hd]
    for v, cur, s, e in monies(w):
        if not G.plausible_gross(v):
            continue
        k = money_kind(w, v, s, e)
        if k != "deal":
            continue
        if copy and copy[0] <= s <= copy[1] and any(abs(v - x) <= 0.001 * x for x in hvals):
            continue                                          # 1.0.1: the headline repeated at the top of the body
        if re.search(r"\d\s*(?:million|billion|m|bn)?\s*(?:[A-Z]{3}\s*)?\(\s*(?:approximately\s+|approx\.?\s+|about\s+|or\s+|equivalent\s+to\s+)?[A-Z]{0,3}\$?$", w[max(0, s - 40):s]):
            continue                                          # 1.0.1: "US$3,000,000 (CA$4,200,000)" - a bracketed conversion
        before = w[max(0, s - 160):s]
        sent = _sentence(w, s, e)
        pre_sent = w[max(_sentence_start(w, s), s - 300):s]
        scoped = bool(_RE_TRANCHE_SCOPED.search(pre_sent))
        # "it closed the second tranche ... for aggregate gross proceeds of $X": the tranche's own proceeds
        tranche_sent = bool(re.search(r"(?i)\b(?:c\s?los\w*|com\s?plet\w*)\s+(?:of\s+)?(?:the\s+|its\s+|a\s+)?(?:\w+\s+){0,3}tranche\b", pre_sent)
                            and not re.search(r"(?i)together|combined|to\s+date|in\s+total|bringing|cumulative|all\s+tranches|both\s+tranches|raised\s+(?:an?\s+)?(?:aggregate\s+)?total"
                                              r"|(?:previously|earlier|prior)\s+(?:announced\s+)?(?:the\s+)?(?:c\s?los|complet)\w*|had\s+(?:been\s+)?closed|was\s+closed"
                                              r"|fully\s+subscribed|total\s+(?:gross\s+)?(?:proceeds|financing)|\bnow\s+(?:raised|closed|completed)", pre_sent))
        scoped = scoped or tranche_sent
        size_ref = bool(re.search(r"(?i)\b(?:tranche|portion)\s+of\s+(?:the|its|a|an)\s+(?:previously\s+announced\s+|upsized\s+|oversubscribed\s+|over-subscribed\s+)?$", before[-70:])
                        and re.match(r"(?i)\s*(?:million\s+|m\s+)?(?:[\w\-]+\s+){0,4}?(?:financing|offering|private\s+placement|placement)\b", w[e:e + 70]))
        # 1.0.5: "(i) a minimum of ... for gross proceeds of $X; and (ii) a maximum of ...": $X is not the size
        clause = re.split(r";|\(i{1,3}\)|\(\w\)\s", pre_sent)[-1]
        minc = bool(re.search(r"(?i)\bminimum\b", clause) and not re.search(r"(?i)\bmaximum\b", clause)
                    or re.match(r"(?i)[^.;$]{0,30}\bin\s+the\s+case\s+of\s+(?:the\s+|a\s+)?minimum", w[e:e + 70])) \
            and bool(re.search(r"(?i)\bmaximum\b", w[max(0, s - 400):e + 400]))
        # 1.0.5: "On <date>, the Company announced it had closed its first tranche ... $X": an earlier release's close
        hist = bool(re.search(r"(?i)\b(?:had\s+(?:\w+\s+)?(?:closed|completed)|previously\s+(?:closed|completed))\b", sent)) and not re.search(
            r"(?i)\b(?:has|have)\s+(?:now\s+|also\s+|successfully\s+)?(?:\w+\s+)?(?:closed|completed)\b|\bis\s+pleased|\bannounces?\s+(?:the\s+)?(?:closing|completion)", sent)
        insider = bool(re.search(r"(?i)\binsiders?\b|\bdirectors?\b|\bofficers?\b|related\s+part|\bparticipat\w+|\bpurchas(?:ed|ing)\s+(?:an?\s+aggregate\s+of\s+)?[\d,]+", sent))
        body.append({"v": v, "cur": cur, "s": s, "size_ref": size_ref, "scoped": scoped, "insider": insider, "minc": minc, "hist": hist, "upto": bool(_RE_UPTO.search(before[-45:]) or re.search(
                         r"(?i)\bup\s+to\s+[\d,.]+\s+(?:million\s+)?(?:[\w\-\"'\u201c\u201d]+\s+){0,4}(?:for|with|representing)\s+(?:aggregate\s+|total\s+)?(?:gross\s+)?proceeds\s+of\s+(?:up\s+to\s+)?$", before[-120:])),
                     "minimum": bool(re.search(r"(?i)\bminimum\b[^$]{0,40}$", before[-60:])),
                     "part": _part(before[-170:]), "combo": bool(re.search(r"(?i)non-dilutive|(?:when\s+)?combined\s+with(?!\s+(?:the\s+)?(?:proceeds\s+(?:of|from)\s+(?:the\s+)?)?(?:first|second|third|initial|previous|prior|earlier|other)\s+(?:and\s+\w+\s+)?tranches?|\s+tranches?\b)|together\s+with\s+(?:the\s+)?(?:\w+\s+)?(?:funding|grant|loan|facility)", sent)),
                     "add": bool(_RE_ADDITIONAL.search(before[-70:])),
                     "total": (not scoped) and bool(_RE_TOTAL_BEFORE.search(before[-130:]) or _RE_TOTAL_AFTER.match(w[e:e + 40])
                                                    or _RE_COMBINED_TRANCHES.search(pre_sent)),
                     "gross": bool(re.search(r"(?i)(?:\bproceeds|subscription\s+price|subscription\s+proceeds)\s+(?:to\s+the\s+company\s+)?(?:of\s+)?(?:up\s+to\s+|approximately\s+|a\s+(?:minimum|maximum)\s+of\s+|not\s+less\s+than\s+)?$", before[-60:])),
                     "closed": (scoped and not _RE_UPTO.search(before[-45:]) and "up to" not in before[-45:].lower()) or bool(_RE_CLOSE_CTX.search(sent)),
                     "future": bool(_RE_FUTURE_CTX.search(before[-100:])),
                     "announced": size_ref or bool(re.search(r"(?i)\b(?:previously\s+)?announced\s+(?:an?\s+|its\s+|the\s+)?(?:up\s+to\s+)?$", before[-45:])),
                     "sent": sent})
    curs = [x["cur"] for x in hd + body if x["cur"]]
    if curs:
        out["currency"] = curs[0]
    elif _RE_SEC_FILING.search(window[:2500]):
        out["currency"] = "USD"                               # 1.0.3: a US registered offering is not in Canadian dollars
    else:
        out["currency"] = "CAD"

    def pick(cands, **want):
        for c in cands:
            if all(c[k] == val for k, val in want.items()):
                return c
        return None

    if not closing:
        if role == "upsize":
            hd_nf = [x for x in hd if not x["from"]]
            c = pick(hd_nf, to=True) or (hd_nf[-1] if hd_nf else None)
            if c is None:
                m = G._RE_UPSIZE_INCREASED_FROM_TO.search(w)
                if m:
                    v, _ = G.read_amount(w, m.start(1))
                    if G.plausible_gross(v):
                        c = {"v": v}
            if c is None:
                c = pick([b for b in body if not b["add"]], upto=True) or pick([b for b in body if not b["add"]], gross=True)
            if c is None:                                     # 1.0.3: "will now raise $600,000", "increased to $5,750,000"
                m2 = _RE_FROM_TO.search(w) or _RE_UPSIZED_TO.search(w)
                if m2:
                    v2, _ = G.read_amount(w, m2.end())
                    if G.plausible_gross(v2):
                        c = {"v": v2}
            out["offered"] = c["v"] if c else None
        else:
            c = (pick(hd, upto=True) or (hd[0] if hd else None))
            nb = [b for b in body if not b["add"] and not b["minimum"] and not b["minc"]]
            bc = pick(nb, gross=True, upto=True) or pick(nb, gross=True) or pick(nb, upto=True) \
                or (next((b for b in nb if not b["total"]), None))
            # a two-part placement: "up to $750,000" of hard-dollar units and "up to $500,000" of flow-through units
            parts = {}
            for b in nb[:6]:
                if b["upto"] and b["part"] and b["part"] not in parts:
                    parts[b["part"]] = b["v"]
            total_stated = any(b["upto"] and not b["part"] for b in nb[:6])
            if c is not None:
                near = next((b for b in nb if abs(b["v"] - c["v"]) <= 0.05 * c["v"] and b["v"] != c["v"]), None)
                out["offered"] = near["v"] if near else c["v"]
            elif len(parts) == 2 and not total_stated:
                out["offered"] = round(sum(parts.values()), 2)
                out["offered_alt"] = sorted(parts.values(), reverse=True)
            elif bc is not None:
                out["offered"] = bc["v"]
        # size with an option exercised: "up to an additional $X"
        add = next((b for b in body if b["add"]), None)
        if out["offered"] and add and not out["offered_alt"]:
            if add["v"] < out["offered"]:
                out["offered_alt"].append(round(out["offered"] + add["v"], 2))
            elif add["v"] > out["offered"]:
                out["offered_alt"].append(add["v"])
    else:
        # this close: a headline figure right after the close verb, or the first past-tense gross proceeds
        hc = pick(hd, closeverb=True)
        tranche_head = bool(re.search(r"(?i)\btranche\b", h))
        comp = bool(_RE_FT_WORD.search(w[:2500]) and _RE_NFT_WORD.search(w[:2500]))
        bclose = [b for b in body if not b["add"] and not b["upto"] and b["closed"] and not b["total"] and not b["minimum"] and b["s"] < 2500
                  and not b["announced"] and not b["hist"]]
        btot = [b for b in body if b["total"] and not b["upto"] and not b["add"] and not b["combo"] and b["s"] < 3000]
        whole = [b for b in bclose if not (comp and b["part"])]
        parts = [b for b in bclose if comp and b["part"]]
        if hc and (not (tranche_head and hc["of"]) or hc.get("pre_tranche")):
            near = next((b for b in body if abs(b["v"] - hc["v"]) <= 0.05 * hc["v"] and not b["add"] and not b["upto"]), None)
            out["this_close"] = near["v"] if near else hc["v"]
        elif whole:
            out["this_close"] = whole[0]["v"]
        elif parts:
            ft = next((b["v"] for b in parts if b["part"] == "FT"), None)
            nft = next((b["v"] for b in parts if b["part"] == "NFT"), None)
            if ft and nft:
                out["this_close"] = round(ft + nft, 2)
            elif len(btot) >= 2:
                pass
            else:
                out["this_close"] = parts[0]["v"]
        elif hd and not tranche_head and not hd[0]["upto"]:
            out["this_close"] = hd[0]["v"]
        else:
            fb = next((b for b in body if b["gross"] and not b["add"] and not b["total"] and not b["minimum"]
                       and (not b["upto"] or (b["closed"] and not b["scoped"])) and b["s"] < 2000 and not b["announced"]
                       and not (b["insider"] and not b["closed"])), None)
            if fb:
                out["this_close"] = fb["v"]
        # 1.0.1: "Closing ... for Gross Proceeds of $2.18M" = brokered $1,703,695 + concurrent $480,000 in the body
        hp0 = next((x for x in hd if x["proceeds"] and not x["upto"] and not x["from"]), None)
        if hp0 is not None and not hp0["totalword"] and len(bclose) >= 2 and not any(b["scoped"] for b in bclose[:4]):
            vals = []
            for b in bclose[:4]:
                if all(abs(b["v"] - x) > 0.001 * x for x in vals):
                    vals.append(b["v"])
            for n in (2, 3):
                if len(vals) >= n and abs(sum(vals[:n]) - hp0["v"]) <= 0.01 * hp0["v"] and not any(
                        abs(x - hp0["v"]) <= 0.01 * hp0["v"] for x in vals):
                    out["this_close"] = round(sum(vals[:n]), 2)
                    break
        if btot:
            t = max(btot, key=lambda b: b["v"])
            if out["this_close"] is None or t["v"] >= out["this_close"] - 1:
                out["closed_total"] = t["v"]
            smaller = [b for b in btot if b["v"] < t["v"] - 1 and b["s"] < t["s"]]
            if smaller and (out["this_close"] is None or (comp and out["this_close"] < smaller[0]["v"])):
                out["this_close"] = smaller[0]["v"]
            if out["this_close"] is None and len(btot) == 1 and not tranche_head:
                out["this_close"] = t["v"]
            elif out["this_close"] is None and role == "final_close" and not re.search(r"(?i)\btranche", h + " " + w[:2500]):
                out["this_close"] = min(btot, key=lambda b: b["s"])["v"]   # 1.0.1: a single close stated only as an aggregate
        # 1.0.1: a close headline that states the proceeds ("Closes Third and Final Tranche ... for Gross Proceeds of
        # C$10.1 M", "... for Total Financing of $1.2 Million") when the body gives no closed figure of its own
        hp = next((x for x in hd if x["proceeds"] and not x["upto"] and not x["pre_tranche"] and not x["from"]), None)
        # "Closes Final Tranche of $1,011,135 for Aggregate Gross Proceeds of $2,313,136": the first figure is the tranche
        ht = next((x for x in hd if x["tranche_of"]), None)
        if ht is not None and hp is not None and hp is not ht and hp["v"] > ht["v"] * 1.01:
            if out["this_close"] is None or abs(out["this_close"] - hp["v"]) <= 0.01 * hp["v"]:
                out["this_close"] = ht["v"]
        if hp is not None and out["closed_total"] is None:
            final_head = bool(re.search(r"(?i)\bfinal\s+(?:tranche|closing)|\band\s+final\b", h)) or (
                role == "final_close" and bool(re.search(r"(?i)\bfinal\s+tranche\b", w[:900])))
            if hp["totalword"] or final_head:
                if out["this_close"] is None or hp["v"] > out["this_close"] * 1.01:
                    out["closed_total"] = hp["v"]
                elif hp["totalword"] and abs(hp["v"] - out["this_close"]) <= 0.01 * hp["v"]:
                    out["closed_total"] = out["this_close"]
            elif out["this_close"] is None and tranche_head:
                out["this_close"] = hp["v"]
        if out["this_close"] is None and out["closed_total"] is not None and re.search(
                r"(?i)\b(?:first|initial|1st)\s+tranche|tranche\s+(?:1|one|i)\b", h + " " + w[:600]) and not re.search(
                r"(?i)\b(?:second|third|fourth|final|2nd|3rd|subsequent)\s+tranche", h + " " + w[:600]):
            out["this_close"] = out["closed_total"]               # 1.0.1: a first tranche's aggregate is this close
        if out["closed_total"] is None and out["this_close"] is not None:
            first = re.search(r"(?i)\b(?:first|initial|1st)\s+tranche|tranche\s+(?:1|one|i)\b", h + " " + w[:600])
            later = re.search(r"(?i)\b(?:second|third|fourth|fifth|2nd|3rd|4th|5th|subsequent|additional|further)\s+(?:and\s+final\s+)?tranche"
                              r"|tranche\s+(?:2|3|4|two|three|four|ii|iii|iv)\b", h + " " + w[:600])
            if later and first and re.search(r"(?i)\b(?:intends?|expects?|anticipates?|plans?)\s+to\s+close\s+(?:the\s+|a\s+)?$",
                                             (h + " " + w[:600])[max(0, later.start() - 40):later.start()]):
                later = None                                  # 1.0.1: "The Company intends to close the second and final tranche"
            if later and first and re.match(r"(?i)[^.]{0,60}?\b(?:is|are)\s+(?:expected|anticipated|scheduled)|[^.]{0,25}?\b(?:to\s+follow|will\s+(?:close|be\s+completed))",
                                            (h + " " + w[:600])[later.end():]):
                later = None                                  # 1.0.1: "a second and final tranche is expected to close"
            if (role == "final_close" and not later and not tranche_head) or (first and not later):
                out["closed_total"] = out["this_close"]
        # the deal's size, when the close release restates it
        up = pick(hd, of=True) or pick(hd, upto=True)
        bu = pick([b for b in body if not b["add"]], upto=True)
        ref = out["closed_total"] or out["this_close"]
        plaus = lambda v: ref is None or (ref * 0.3 <= v <= ref * 4)
        near_closed = lambda v: any(x and abs(v - x) <= 0.01 * x for x in (out["this_close"], out["closed_total"]))
        if up and up.get("proceeds") and not up.get("tranche_of"):
            up = None                                         # 1.0.1: "... for Gross Proceeds of $X" in a close headline is money closed
        if up and not near_closed(up["v"]) and plaus(up["v"]):
            out["offered"] = up["v"]
        elif bu and bu["v"] != out["this_close"] and plaus(bu["v"]) and bu["s"] < 2500:
            out["offered"] = bu["v"]
        else:
            ba = next((b for b in body if b["announced"] and not b["add"] and b["s"] < 1500), None)
            if ba and not near_closed(ba["v"]) and plaus(ba["v"]) and (out["this_close"] is None or ba["v"] > out["this_close"]):
                out["offered"] = ba["v"]                      # 1.0.1: "its previously announced $3,000,000 private placement"
    return out


# ------------------------------------------------------------------ separately closed financings (1.0.1)
_RE_PART_ANCH = re.compile(
    r"(?i)\b(?:(?:has|have)\s+(?:now\s+|also\s+|successfully\s+|concurrently\s+)*(?:closed|completed)"
    r"|(?<!previously\s)(?<!had\s)(?:also\s+)?closed\s+(?:its|the|a|an)\b|(?<!previously\s)completed\s+(?:its|the|a|an)\b"
    r"|announces?\s+(?:the\s+)?(?:closing|completion)\s+of\s+(?:its|the|a|an)\b)")
_RE_PART_TYPEWORD = re.compile(
    r"(?i)private\s+placement|\boffering\b|debentures?\b|\bnotes?\b|flow-through|\bLIFE\b|\bfacility\b|\bloan\b|\bstream\b"
    r"|\broyalty\b|bought\s+deal|subscription\s+receipts|strategic\s+investment")
_RE_PART_HISTORY = re.compile(r"(?i)\b(?:previously|had|was|were|earlier|on\s+\w+\s+\d{1,2},?\s+\d{4},?\s+the\s+company)\s+$")


def _part_amount(seg):
    """(score, value, currency) of the segment's deal figure: gross proceeds / principal amount first."""
    best = None
    for v, cur, s, e in monies(seg):
        if not G.plausible_gross(v) or money_kind(seg, v, s, e) != "deal":
            continue
        pre = seg[max(0, s - 60):s]
        score = 0
        if re.search(r"(?i)(?:gross\s+proceeds|principal\s+amount|proceeds)\s+(?:of\s+)?(?:approximately\s+|approx\.\s+|about\s+)?$", pre) \
                or re.search(r"(?i)^\s*(?:million|m)?\s*(?:\([^)]{0,60}\)\s*)?(?:aggregate\s+)?principal\s+amount", seg[e:e + 90]):
            score = 2
        if re.search(r"(?i)\b(?:up\s+to|additional|option|total|combined|together)\b[^$]{0,30}$", pre):
            score -= 3
        if re.search(r"\(\s*(?:approximately\s+|approx\.?\s+|about\s+|or\s+)?$", pre):
            score -= 1                                       # "USD$25 million (approximately C$34,130,000)"
        if best is None or score > best[0]:
            best = (score, v, cur)
    return best if best is None or best[0] >= 2 else (best[0], best[1], best[2])


def close_parts(window: str):
    """Separately closed financings named in one close release, in text order: [{types, offering, currency, amount,
    price}]. Empty unless at least two parts with different amounts are found. The publisher splits a release only
    when two different existing deals match two parts; otherwise this is informational."""
    w = window[:3000]
    ms = list(_RE_PART_ANCH.finditer(w))
    parts = []
    for i, m in enumerate(ms):
        if _RE_PART_HISTORY.search(w[max(0, m.start() - 40):m.start()]):
            continue
        end = min(ms[i + 1].start() if i + 1 < len(ms) else len(w), m.start() + 900)
        seg = w[m.start():end]
        if not _RE_PART_TYPEWORD.search(seg[:400]):
            continue
        amt = _part_amount(seg)
        if amt is None or amt[0] < 2:
            continue
        t, off = deal_types(seg[:300], seg, seg[:300])
        pr, conv = prices(seg)
        if "CD" in t:
            pr = [conv] if conv else []
        parts.append({"types": t, "offering": off, "currency": amt[2] or None, "amount": amt[1],
                      "price": pr[0] if pr else None})
    # drop repeats and a combined figure (one part equal to the sum of the others)
    uniq = []
    for p in parts:
        if all(abs(p["amount"] - q["amount"]) > 0.01 * q["amount"] for q in uniq):
            uniq.append(p)
    if len(uniq) >= 3:
        tot = max(uniq, key=lambda p: p["amount"])
        rest = sum(p["amount"] for p in uniq if p is not tot)
        if abs(tot["amount"] - rest) <= 0.03 * tot["amount"]:
            uniq = [p for p in uniq if p is not tot]
    return uniq[:3] if len(uniq) >= 2 else []


# ------------------------------------------------------------------ prices and warrants
_RE_EXCLUDE_WARRANT = re.compile(r"(?i)\b(?:finders?'?|finder's|broker(?:'s)?|brokers'|agents?'|agent's|compensation|advisory|bonus)\s+(?:\w+\s+){0,2}warrants?\b")
# 1.0.3: "$0.42 per HD Unit" / "$1.20 per FT Unit" price the unit, never the warrant it carries
_RE_PER_UNIT_AFTER = re.compile(r"(?i)\s*per\s+(?:(?!warrant)[\w\-]+\s+){0,3}(?:unit|receipt|debenture)s?\b(?!\s+warrant)")


def prices(window: str):
    """(issue prices [..3], conversion price or None)."""
    w = window[:4000]
    got, conv = [], None
    for v, cur, s, e in monies(w):
        if v is None or v <= 0 or v >= 1000:
            continue
        k = money_kind(w, v, s, e)
        if k == "conversion" and conv is None and 0.001 <= v < 1000:
            conv = v
        elif k == "price":
            sent = _sentence(w, s, e)
            if re.search(r"(?i)\b(?:exercis\w*|conver\w*|deemed\s+price|per\s+ounce|/oz|per\s+tonne|per\s+pound|/lb|option)\b", w[max(0, s - 50):e + 45]):
                continue
            if _RE_EXCLUDE_WARRANT.search(sent) and not re.search(r"(?i)\bper\s+(?:FT\s+)?(?:unit|share)\b", w[e:e + 30]):
                continue
            if re.search(r"(?i)\b(?:closing|trading|market)\s+price\b|\bvwap\b|\blast\s+closing\b", w[max(0, s - 60):s]):
                continue
            # 1.0.6 (FIX8, 2026-10-06): prices in the sentence that are not what a unit or share is sold for. A warrant's
            # acceleration trigger ('if the closing price ... is at least $0.45 per share for 10 consecutive trading days'),
            # a warrant's exercise price written far from the word warrant ('Each Warrant will entitle the holder to purchase
            # one Share at a price of $0.40'), a deemed or resale price, shares sold by someone else. These were listed as
            # second and third unit prices.
            sent_before = sent[:max(0, s - _sentence_start(w, s))] if sent else ""
            # 1.0.6b: the cue looks back only to the sentence's own start, which may end in a closing quote or bracket
            # ('... in 2018." The Private Placement consisted of ... at $0.275 per Unit'), and its cues are specific: one
            # or more agents, accelerating the development and 'may not exceed' are not acceleration triggers.
            _sb = re.split(r"[.!?][\"\u201d\u2019')\]]*\s+(?=[\"\u201c\u2018(]*[A-Z0-9])", sent_before[-400:])[-1]
            if re.search(r"(?i)\b(?:subject\s+to\s+(?:an?\s+|the\s+)?(?:early\s+)?acceleration|acceleration\s+(?:clause|provision|right|option|"
                         r"period|event|feature|notice|of\s+the\s+expiry)|accelerat\w*\s+(?:the\s+)?(?:expir\w*|term|exercise)|right\s+to\s+accelerate|"
                         r"consecutive\s+trading\s+days|equals?\s+or\s+exceeds?|at\s+or\s+above|(?<!not\s)(?<!to\s)exceeds?|is\s+at\s+least)\b",
                         _sb[-220:]) and not _RE_PER_UNIT_AFTER.match(w[e:e + 40]):
                continue                                   # 1.0.6d: '$0.40 per Unit' is the offering's price; triggers are per share
            # 1.0.6d: 'greater/more than' is a trigger only right before the price ('is greater than $0.34'), not
            # 'will consist of more than 3,333,333 shares at a purchase price of $0.30'
            if re.search(r"(?i)(?<!not\s)(?<!no\s)\b(?:greater|higher|more)\s+than(?:\s+or\s+equal\s+to)?(?:\s+a\s+price\s+of)?[\s(]*(?:(?:C|CDN|CA|US)\s?)?$",
                         _sb[-60:]) and not _RE_PER_UNIT_AFTER.match(w[e:e + 40]):
                continue
            # 1.0.6c: a market-price basis ('the 10-day volume weighted average price', 'the closing price') marks a trigger
            # unless the sentence prices the offering itself on it ('issued at a price equal to the 10-day VWAP ... being $2.05').
            if re.search(r"(?i)\b(?:volume[\s-]+weighted|trades?\s+(?:at|above)|(?:closing|trading)\s+price)\b", _sb[-220:]) and not \
                    re.search(r"(?i)\b(?:offering|issue|subscription)\s+price\b|\bissued\s+at\s+a\s+price\b|\bpriced\s+at\b", _sb) \
                    and not _RE_PER_UNIT_AFTER.match(w[e:e + 40]):
                continue
            if re.search(r"(?i)\bwarrants?\b[^.]{0,260}?\b(?:entitl\w*|exercis\w*|purchase|acquire)\b[^.]{0,140}$", sent_before) \
                    and not _RE_PER_UNIT_AFTER.match(w[e:e + 40]) \
                    and not re.match(r"(?i)\s*per\s+(?:\w+\s+){0,2}share\s+and\s+(?:\w+\s+){0,2}warrants?\b", w[e:e + 70]):
                continue                                   # 1.0.6c: '$0.32 per Common Share and associated Warrant' is the price
            if re.search(r"(?i)\bdeemed\s+(?:issue\s+|issuance\s+)?price\b|\bsold\s+(?:such|the|its|these|those)\s+shares\b|"
                         r"\binterest\s+shares\b|\bstandby\b|\bbonus\s+warrants?\b", sent_before[-220:]):
                continue
            if re.match(r"(?i)\s*per\s+(?:\w+\s+){0,2}warrant\s+shares?\b", w[e:e + 40]):
                continue                                   # 1.0.3: "per Warrant Share" prices the warrant, not the unit
            if re.search(r"(?i)\bfrom\s+$", w[max(0, s - 8):s]) and re.match(
                    r"(?i)\s*(?:per\s+(?:[\w\-]+\s+){0,2}?(?:unit|share|receipt)s?\s+)?to\s+(?:(?:C|CDN|CA|US)\s?)?\$\s?\d", w[e:e + 50]):
                continue                                   # 1.0.5: "repricing from $0.05 per Unit to $0.035 per Unit"
            if all(abs(v - g) > 1e-9 for g in got):
                got.append(v)
        if len(got) >= 3:
            break
    return got, conv


_RE_W_FRACTION = re.compile(
    r"(?i)\b(?P<frac>one[\s\-]half|1/2|\u00bd|one[\s\-]third|1/3|one[\s\-]quarter|one[\s\-]fourth|three[\s\-]quarters?"
    r"|one\s*\(1\)|one|a|1|two|2)\s*(?:\(\s*(?:1/2|\u00bd|0\.5|1/4|1/3|2/3|3/4|1|2)\s*\)\s*)?(?:of\s+one\s+(?:\(1\)\s+)?)?"
    r"(?:(?:whole|transferable|non-transferable|common|share|stock|purchase|non-flow-through|NFT|FT|subscription)\s+){0,4}warrants?\b")
_FRAC = {"one-half": 0.5, "one half": 0.5, "a-half": 0.5, "a half": 0.5, "half": 0.5, "1/2": 0.5, "\u00bd": 0.5, "one-third": 1 / 3, "one third": 1 / 3, "1/3": 1 / 3,
         "one-quarter": 0.25, "one quarter": 0.25, "one-fourth": 0.25, "one fourth": 0.25, "three-quarters": 0.75,
         "three-quarter": 0.75, "three quarters": 0.75, "one (1)": 1.0, "one": 1.0, "a": 1.0, "1": 1.0, "two": 2.0, "2": 2.0}
_RE_W_TERM = re.compile(
    # 1.0.3: "on or before that date which is 24 months", "valid for 18 months", "a term of 36-months"
    r"(?i)\b(?:(?:for\s+a\s+(?:period|term)\s+of|for|within|valid\s+for|exercisable\s+for|until\s+the\s+date\s+that\s+is|ending\s+on\s+the\s+date\s+which\s+is"
    r"|(?:on\s+or\s+)?(?:before|until|ending\s+on|on)\s+(?:the|that)\s+date\s+(?:that|which)\s+is|expir\w*\s+(?:on\s+the\s+date\s+that\s+is\s+)?"
    r"|(?:shall\s+|will\s+)?have\s+a\s+term\s+of|term\s+of|period\s+of|up\s+to)\s+)"
    r"(?P<n>\d{1,2}|one|two|three|four|five|six|twelve|eighteen|twenty\s*[\s\-]\s*four|thirty\s*[\s\-]\s*six|forty\s*[\s\-]\s*eight|sixty)"
    r"\s*(?:\(\s*[\w\s\-]{1,24}\s*\)\s*)?[\s\-]*(?P<u>months?|years?)\b"
    # 1.0.3: "one two-year share purchase warrant", "a 2 year half warrant at $0.15"
    r"|\b(?P<n2>\d{1,2}|one|two|three|four|five|six|twelve|eighteen)[\s\-](?P<u2>month|year)s?\s+(?:(?!and\b)[\w\-]+\s+){0,3}(?:term|period|warrants?|expiry)"
    r"|\(\s*(?P<n3>\d{1,2})\s*\)\s*(?P<u3>months?|years?)\b")

# 1.0.3: a stepped warrant described by the years it runs -- "during the first year ... thereafter"
_RE_W_ORDINAL_YEAR = re.compile(r"(?i)\b(first|second|third|fourth|fifth)\s+year\b")
_RE_W_ANNIVERSARY = re.compile(r"(?i)\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|1st|2nd|3rd|4th|5th)\s+anniversary\b")
_ORD_YEAR = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
             "eighth": 8, "ninth": 9, "tenth": 10, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5}


def _term_months(m):
    n = m.group("n") or m.group("n2") or m.groupdict().get("n3")
    u = (m.group("u") or m.group("u2") or m.groupdict().get("u3") or "").lower()
    n = re.sub(r"\s*-\s*", "-", n.lower().strip()).replace(" ", "-")
    v = int(n) if n.isdigit() else _WORD_NUM.get(n) or _WORD_NUM.get(n.replace("-", " "))
    if not v:
        return None
    months = v * 12 if u.startswith("year") else v
    return months if 1 <= months <= 120 else None


class _Frac:
    def __init__(self, per, start, end):
        self.per, self._s, self._e = per, start, end

    def start(self):
        return self._s

    def end(self):
        return self._e


_RE_W_WORD = re.compile(r"(?i)\bwarrants?\b")
_RE_W_FRAC_BEFORE = re.compile(
    r"(?i)\b(one-half|one\s+half|a\s+half|half|1/2|\u00bd|one-third|one\s+third|1/3|one-quarter|one\s+quarter|one-fourth|three-quarters?"
    r"|\d{1,3}(?:,\d{3})+|one|a|an|1|two|2)\b"
    r"(?:\s*\(\s*(?:1/2|\u00bd|0\.5|1/4|1/3|2/3|3/4|1|2)\s*\))?(?:\s+of\s+(?:one|a)(?:\s*\(\s*(?:1/2|\u00bd|0\.5|1/4|1/3|2/3|3/4|1)\s*\))?)?"
    r"((?:\s+(?!and\b|or\b|share\b(?!\s+purchase)|shares\b|unit|flow)[\w\-]+){0,6})\s+$")


def _unit_warrant(seg):
    """The warrant the unit carries: fraction and position, or None (finder's / broker warrants are skipped)."""
    for wm in _RE_W_WORD.finditer(seg):
        pre = seg[max(0, wm.start() - 90):wm.start()]
        if _RE_EXCLUDE_WARRANT.search(seg[max(0, wm.start() - 40):wm.end()]):
            continue
        fm = _RE_W_FRAC_BEFORE.search(pre)
        if not fm:
            continue
        frac = fm.group(1).lower().replace(" ", "-") if fm.group(1).lower() not in ("a", "an") else "a"
        per = _FRAC.get(frac, _FRAC.get(frac.replace("-", " ")))
        if per is None and re.match(r"^\d{1,3}(?:,\d{3})+$", frac):
            if not re.match(r"(?i)\s*each\b", seg):      # "2,415,000 Units, comprised of ... and 1,207,500 Warrants" is a total
                continue
            per = float(frac.replace(",", ""))            # 1.0.2: "each Unit ... and 3,334 warrants"
        if per is None and frac in ("an",):
            per = 1.0
        return _Frac(per, wm.start() - len(pre) + fm.start() + max(0, 0), wm.end())
    return None


_W_MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december"
             "|jan\\.?|feb\\.?|mar\\.?|apr\\.?|jun\\.?|jul\\.?|aug\\.?|sept?\\.?|oct\\.?|nov\\.?|dec\\.?")
_W_MONTH_NUM = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_RE_DATE_TEXT = re.compile(r"(?i)\b(" + _W_MONTHS + r")\s+(\d{1,2})\s*(?:st|nd|rd|th)?\s*,?\s+(20\d{2})\b")
_RE_W_EXPIRY = re.compile(r"(?i)\b(?:until|on\s+or\s+before|expir\w+\s+(?:on\s+|at\s+)?|through|to)\s+(?:5:00\s*[ap]\.?m\.?[^,]{0,25},?\s*)?"
                          r"\b(" + _W_MONTHS + r")\s+(\d{1,2})\s*(?:st|nd|rd|th)?\s*,?\s+(20\d{2})\b")
_TERM_SNAP = (6, 12, 18, 24, 30, 36, 48, 60)


def _release_date(window: str):
    """The release's own date, from its dateline, for warrant terms written as an expiry date."""
    m = _RE_DATE_TEXT.search(window[:1600])
    if not m:
        return None
    try:
        return date(int(m.group(3)), _W_MONTH_NUM[m.group(1).lower()[:3]], int(m.group(2)))
    except (KeyError, ValueError):
        return None


def _term_from_expiry(seg: str, issued):
    """term_months from '... until May 14, 2028' when the release dates itself."""
    if issued is None:
        return None
    m = _RE_W_EXPIRY.search(seg)
    if not m:
        return None
    try:
        exp = date(int(m.group(3)), _W_MONTH_NUM[m.group(1).lower()[:3]], int(m.group(2)))
    except (KeyError, ValueError):
        return None
    months = round((exp - issued).days / 30.44)
    floor = 6
    # 1.0.3: a short-dated warrant states its own exercise price; a 4-month hold period does not
    if 3 <= months < 6 and re.search(r"(?i)\bexercisable\b|\bexercise\s+price\b|\bat\s+a\s+price\s+of\b", seg) \
            and not re.search(r"(?i)\bhold\s+period|\bresale\b|\bstatutory\b|\brestricted\s+period", seg):
        floor = 3
    if not floor <= months <= 120:
        return None                                       # 4 months is the resale hold period, not a warrant term
    if months < 6:
        return months                                      # 1.0.3: a short-dated warrant is not snapped up to 6
    near = min(_TERM_SNAP, key=lambda x: abs(x - months))
    return near if abs(near - months) <= 2 else months


_RE_W_TERM_STOP = re.compile(r"(?i)[\w\-]+\s*(?:\(\d+\)\s*)?months?(?:\s+and\s+[\w\(\)]+\s*(?:\(\d+\)\s*)?days?)?"
                             r"\s+(?:hold|statutory)\b"                                     # 1.0.2: "a four (4) month [and one (1) day] hold period"
                             r"|\bhold\s+period|four\s+months\s+and\s+(?:a|one)\s+day|accelerat\w*|insiders?\b|proceeds\b|finders?\b|related\s+party")


def _warrant_term(seg):
    """The longest term stated in the warrant's own description (stepped prices: '18 months ... or 36 months')."""
    stop = _RE_W_TERM_STOP.search(seg)
    part = seg[:stop.start()] if stop else seg[:500]
    terms = [x for x in (_term_months(t) for t in _RE_W_TERM.finditer(part)) if x]
    if not terms:                                          # 1.0.3: "if exercised during the first year ... the second year"
        yrs = [_ORD_YEAR[m.group(1).lower()] for m in _RE_W_ORDINAL_YEAR.finditer(part)]
        if yrs and re.search(r"(?i)\bexercis\w*|\bwarrant", part):
            terms = [max(yrs) * 12]
    if not terms:                                          # 1.0.3: "will expire on the fifth anniversary of issuance"
        am = _RE_W_ANNIVERSARY.search(part)
        if am and re.search(r"(?i)\bexpir\w*|\bexercis\w*", part):
            terms = [_ORD_YEAR[am.group(1).lower()] * 12]
    return max(terms) if terms else None


_RE_W_DESC = re.compile(
    r"(?i)(?:each\s+|every\s+)?(?:whole\s+|full\s+|one\s+)?warrants?\b(?:[^.]|\.(?=\d)){0,200}?"
    r"\b(?:entitl\w+|exercisable|grants?\s+the\s+holder|permits?\s+the\s+holder|to\s+purchase|to\s+acquire|valid\s+for|expire"
    r"|(?:shall|will)\s+have\s+a\s+term)\b"
    r"(?:[^.]|\.(?=\d)){0,320}")
_RE_W_AT_PRICE = re.compile(r"(?i)\b(?:at|for|of)\s+(?:an?\s+)?(?:exercise\s+|purchase\s+)?(?:price\s+(?:of|per\s+\w+\s+of)\s+)?$")
_RE_W_OFFER_PRICE = re.compile(r"(?i)\b(?:public\s+)?offering\s+price\b[^.$]{0,30}$")
# "a 2 year half warrant at $0.15": the term sits in front of the word, the strike behind it
_RE_W_INLINE = re.compile(
    r"(?i)\b(?P<n>\d{1,2}|one|two|three|four|five)[\s\-](?P<u>year|month)s?\s+(?:(?!and\b)[\w\-]+\s+){0,2}warrants?\s+at\s+")


def _standalone_warrants(w, issued):
    """1.0.3: the warrant described on its own, where no unit sentence anchors it
    (subscription receipts converting, a bullet list of tranche terms, an ADS offering)."""
    out = []
    for m in _RE_W_INLINE.finditer(w):
        strike = None
        for v, cur, s2, e2 in monies(w[m.end() - 4:m.end() + 40]):
            if 0.001 <= v < 1000:
                strike = v
                break
        tm = None
        n = m.group("n").lower()
        v = int(n) if n.isdigit() else _WORD_NUM.get(n)
        if v:
            tm = v * 12 if m.group("u").lower().startswith("year") else v
        if strike is not None or tm is not None:
            out.append({"per_unit": None, "strike": strike, "term_months": tm})
        if out:
            return out[:1]
    for m in _RE_W_DESC.finditer(w):
        sent = m.group(0)
        lead = w[max(0, m.start() - 45):m.start()] + sent      # "... issued to the Agents compensation | Warrants ..."
        if _RE_EXCLUDE_WARRANT.search(lead) or re.search(r"(?i)\bconvers\w*|\bconvertible\b|\bhold\s+period|\bresale\b", sent):
            continue
        strike = None
        for v, cur, s2, e2 in monies(sent):
            if not 0.001 <= v < 1000:
                continue
            if _RE_PER_UNIT_AFTER.match(sent[e2:e2 + 45]):
                continue
            if _RE_W_OFFER_PRICE.search(sent[max(0, s2 - 60):s2]):
                continue                                       # 1.0.3: the offering price of the unit, not the warrant
            k = money_kind(sent, v, s2, e2)
            if k == "strike" or (k in ("price", "other") and _RE_W_AT_PRICE.search(sent[max(0, s2 - 34):s2])):
                strike = v
                break
        tm = _warrant_term(sent) or _term_from_expiry(sent, issued)
        if strike is None and tm is None:
            continue
        pre = w[max(0, m.start() - 220):m.start() + 40]
        fm = _unit_warrant(pre)
        out.append({"per_unit": fm.per if fm else None, "strike": strike, "term_months": tm})
        if len(out) >= 3:
            break
    full = [o for o in out if o["strike"] is not None and o["term_months"] is not None]
    return (full or out)[:2]


def warrants(window: str):
    """[{per_unit, strike, term_months}] one per unit type, in text order."""
    w = window[:4500]
    issued = _release_date(window)
    out = []
    for m in re.finditer(r"(?i)\beach\s+(?:\S+\s+){0,4}?(?:units?|FT\s+units?|flow-through\s+units?|[A-Z]{2,4}Us?)\b[^.]{0,40}?\b(?:consist\w*|compris\w*|is\s+comprised|will\s+be\s+comprised|shall\s+consist)\b"
                         r"|\b(?:units?|[A-Z]{2,4}Us?)\b[^.]{0,30}\b(?:each\s+)?(?:consisting|comprised|composed)\s+of\b"
                         r"|\b(?:units?|[A-Z]{2,4}Us?)\b[^.]{0,30}\b(?:will\s+|shall\s+)?consists?\s+of\b", w):
        seg_end = min(len(w), m.end() + 700)
        seg = w[m.start():seg_end]
        fm = _unit_warrant(seg[:320])
        if not fm:
            continue
        per = fm.per
        strike = None
        for v, cur, s, e in monies(seg):
            if s < fm.start():
                continue
            if _RE_PER_UNIT_AFTER.match(seg[e:e + 45]):    # 1.0.3: "$0.42 per HD Unit" is the unit price, not the strike
                continue
            k = money_kind(seg, v, s, e)
            if k == "strike" or (k in ("price", "other") and re.search(r"(?i)\b(?:exercis\w*|purchase|acquire)\b[^.$]{0,120}$", seg[max(0, s - 160):s])
                                 and re.search(r"(?i)warrant", seg[max(0, s - 260):s])):
                if 0.001 <= v < 1000:
                    strike = v
                    break
        tm = _warrant_term(seg[fm.start():]) or _term_from_expiry(seg[fm.start():fm.start() + 700], issued)
        if strike is None or tm is None:                  # 1.0.2: "... and 3,334 warrants" described further down
            wide = w[m.start():]
            for wm2 in re.finditer(r"(?i)\bwarrants?\b(?:[^.]|\.(?=\d)){0,200}?(?:exercisable|entitl\w+|permit\w+|purchase)\b"
                                   r"(?:[^.]|\.(?=\d)){0,240}", wide):
                sent = wm2.group(0)
                if _RE_EXCLUDE_WARRANT.search(sent) or re.search(r"(?i)\bconvers\w*|\bconvertible\b", sent):
                    continue
                if strike is None:
                    for v, cur, s2, e2 in monies(sent):
                        if _RE_PER_UNIT_AFTER.match(sent[e2:e2 + 45]):
                            continue
                        if 0.001 <= v < 1000 and money_kind(sent, v, s2, e2) in ("strike", "price", "other") \
                                and re.search(r"(?i)(?:at|for|of)\s+(?:a\s+price\s+of\s+)?$", sent[max(0, s2 - 30):s2]):
                            strike = v
                            break
                if tm is None and not re.search(r"(?i)\bhold\s+period|\bresale\b|\brestricted\s+period", sent):
                    t2 = _warrant_term(sent) or _term_from_expiry(sent, issued)
                    if t2 is not None and 6 <= t2 <= 120:   # 4 months is a hold period, not a warrant term
                        tm = t2
                if strike is not None and tm is not None:
                    break
        key = (per, strike, tm)
        if strike is None and tm is None and per is None:
            continue
        if any((o["per_unit"], o["strike"], o["term_months"]) == key for o in out):
            continue
        same = next((o for o in out if o["per_unit"] == per
                     and (o["strike"] is None or strike is None or o["strike"] == strike)
                     and (o["term_months"] is None or tm is None or o["term_months"] == tm)), None)
        if same is not None:                              # 1.0.2: one unit type described over two sentences
            if same["strike"] is None:
                same["strike"] = strike
            if same["term_months"] is None:
                same["term_months"] = tm
            continue
        out.append({"per_unit": per, "strike": strike, "term_months": tm})
        if len(out) >= 3:
            break
    if out and any(o["strike"] is None or o["term_months"] is None for o in out):
        extra = _standalone_warrants(w, issued)                # 1.0.3: the terms stated away from the unit sentence
        if extra:
            e0 = extra[0]
            for o in out:
                if o["term_months"] is None and e0["term_months"] is not None:
                    o["term_months"] = e0["term_months"]
                if o["strike"] is None and e0["strike"] is not None and len(out) == 1:
                    o["strike"] = e0["strike"]
    if not out:
        # "... and one-half of one common share purchase warrant" without an "each unit" sentence
        for fm in _RE_W_FRACTION.finditer(w):
            if fm.group("frac").lower() in ("a", "1", "two", "2"):
                continue
            ctx = w[max(0, fm.start() - 200):fm.end() + 400]
            if _RE_EXCLUDE_WARRANT.search(w[max(0, fm.start() - 40):fm.end()]) or not re.search(r"(?i)\bunits?\b", w[max(0, fm.start() - 200):fm.start()]):
                continue
            frac = fm.group("frac").lower()
            per = _FRAC.get(frac, _FRAC.get(frac.replace("-", " ")))
            strike = None
            seg = w[fm.start():fm.end() + 400]
            for v, cur, s, e in monies(seg):
                if money_kind(seg, v, s, e) == "strike" and 0.001 <= v < 1000:
                    strike = v
                    break
            tm = next((x for x in (_term_months(t) for t in _RE_W_TERM.finditer(seg)) if x), None)
            if strike or tm:
                out.append({"per_unit": per, "strike": strike, "term_months": tm})
            break
    if not out:
        out = _standalone_warrants(w, issued)                  # 1.0.3: no unit sentence anchors the warrant
    return out


# ------------------------------------------------------------------ references to earlier releases
_MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december"
           "|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
_MONTH_NUM = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_RE_REF = re.compile(
    r"(?i)\b(?:further\s+to|as\s+(?:previously\s+)?(?:announced|disclosed)\s+(?:in|on)|(?:news|press)\s+releases?\s+(?:dated|of|on|issued\s+on)"
    r"|announced\s+on|previously\s+announced\s+(?:on|in)|see\s+(?:the\s+)?(?:company's\s+)?(?:news|press)\s+release)"
    r"[^.]{0,80}?\b(" + _MONTHS + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d|19\d\d)")


# ------------------------------------------------------------------ unit count (1.0.4)
# A count is kept only when count x issue price equals a deal amount this reader already found (within 1.5%), so a
# finder's, insider's or outstanding-share count can never be stored as the deal's. Two counts at two prices in one
# sentence ("5,000,000 HD Units at $0.10 and 3,000,000 FT Units at $0.12") are one deal when their sum matches.
_UNIT_KIND = (r"(?:(?:hard[\s\-]dollar|HD|non[\s\-]flow[\s\-]through|NFT|(?:charity|premium|national|traditional|critical\s+minerals?)"
              r"\s+flow[\s\-]through|flow[\s\-]through|FT|LIFE|common|special|new|additional|ordinary)\s+){0,3}")
_RE_UNITS = re.compile(r"(?i)(?<![\w$.,])(?P<n>\d{1,3}(?:,\d{3})+(?![\d,])|\d{4,10}(?![\d,])|\d{1,4}(?:\.\d+)?\s*million)\s+"
                       r"(?:\(\s*[^)]{0,40}\)\s+)?" + _UNIT_KIND +
                       r"(?:units?|shares|common\s+shares|subscription\s+receipts?|ordinary\s+shares)\b")
_RE_UNITS_NOT = re.compile(r"(?i)\b(?:finder|broker|agents?'?\s*(?:warrants?|units?|options?|fees?)|compensation|commission|insiders?|"
                           r"directors?|officers?|related\s+part\w*|management|exercis\w*|outstanding|conver\w*|consolidat\w*|"
                           r"settle\w*|in\s+lieu|debt|stock\s+options?|RSUs?|DSUs?|bonus|vendors?|escrow\w*|held\s+by|holds?|owns?|"
                           r"underlying|warrant\s+shares|diluted|shareholders?|previously|deemed|acquisition\s+of|"
                           r"purchased\s+by|subscribed\s+(?:for\s+)?by|participat\w*)\b")
_RE_UNIT_AT = re.compile(r"(?i)^[^.;]{0,90}?\bat\s+(?:a\s+)?(?:(?:issue|offering|subscription|purchase)\s+)?(?:price\s+of\s+)?"
                         r"(?:(?:C|CDN|CA|US|A|AU)\s?)?\$\s?(\d+(?:\.\d+)?)(?!\d)")


def _count_of(s):
    s = s.replace(",", "").strip()
    m = re.match(r"(?i)(\d+(?:\.\d+)?)\s*million$", s)
    return int(round(float(m.group(1)) * 1e6)) if m else int(s)


def unit_counts(window: str, res: dict):
    """{"offered", "this_close", "closed_total"} -> the number of units (or shares) that amount bought, or None."""
    w = window[:4000]
    cands = []
    for m in _RE_UNITS.finditer(w):
        try:
            n = _count_of(m.group("n"))
        except ValueError:
            continue
        if n < 1000 or n > 5_000_000_000:
            continue
        st = max(w.rfind(". ", 0, m.start()) + 2, m.start() - 60, 0)
        en = w.find(". ", m.end())
        en = min(en if en >= 0 else len(w), m.end() + 40)
        if _RE_UNITS_NOT.search(w[st:en]):
            continue
        pm = _RE_UNIT_AT.match(w[m.end():m.end() + 160])
        cands.append((n, float(pm.group(1)) if pm else None, m.start()))
    out = {"offered": None, "this_close": None, "closed_total": None}
    if not cands:
        return out
    px_all = [p for p in (res.get("prices") or []) if p]
    ok = lambda amt, v: abs(v - amt) <= 0.015 * amt

    def match(amt):
        for n, p, _pos in cands:
            for q in ([p] if p else px_all):
                if ok(amt, n * q):
                    return n
        for i, (n1, p1, s1) in enumerate(cands):
            for n2, p2, s2 in cands[i + 1:]:
                if p1 and p2 and p1 != p2 and abs(s2 - s1) < 400 and ok(amt, n1 * p1 + n2 * p2):
                    return n1 + n2
        return None
    for k in out:
        if res.get(k):
            out[k] = match(res[k])
    return out


def ref_dates(window: str):
    out = []
    for m in _RE_REF.finditer(window[:3000]):
        mon = _MONTH_NUM.get(m.group(1).lower()[:3])
        d = int(m.group(2))
        if mon and 1 <= d <= 31:
            s = f"{m.group(3)}-{mon:02d}-{d:02d}"
            if s not in out:
                out.append(s)
    return out[:5]


# ------------------------------------------------------------------ the analysis
# 1.0.2: Quebec issuers file the same release in French and English; the French copy parses to almost nothing,
# so it is marked here and the publisher treats it as a copy of its English twin instead of a deal update.
_RE_FR = re.compile(r"(?i)pour\s+diffusion\s+imm|produit\s+brut|placement\s+priv|ne\s+pas\s+distribuer\s+aux\s+services"
                    r"|\bsoci\u00e9t\u00e9\b|\bactions\s+ordinaires\b|\bd\u00e9b\u00e9nture|\bunit\u00e9s\b")


def language(body: str) -> str:
    return "fr" if len(_RE_FR.findall((body or "")[:3000])) >= 2 else "en"


def analyse(headline: str, body: str) -> dict:
    b = clean((body or "")[:TEXT_CAP])
    h = clean(effective_headline(headline or "", body or ""))
    h = flat(h)
    w = deal_window(b)
    h_main = main_headline(h)
    role, tranche = classify(h_main, w)
    ok, reason = financing_decision(h_main, w, role)
    res = {"is_financing": ok, "reason": reason, "headline_used": h, "role": role if ok else None,
           "tranche": tranche if ok else None, "types": [], "offering": None, "currency": None, "offered": None,
           "offered_alt": [], "this_close": None, "closed_total": None, "prices": [], "conversion": None,
           "warrants": [], "refs": [], "parts": [], "lang": language(body),
           "units_offered": None, "units_this_close": None, "units_closed_total": None}
    if not ok:
        return res
    res["types"], res["offering"] = deal_types(h, w, h_main)
    if role in ("tranche_close", "final_close") and "DEBT" in res["types"] and _RE_DRAWDOWN.search(h + " \n " + w[:900]):
        role = res["role"] = "update"           # 1.0.5: a drawdown under an existing facility
    am = amounts(h, w, role, head_copy=(flat(clean(headline or "")) == h))
    res.update(currency=am["currency"], offered=am["offered"], offered_alt=am["offered_alt"],
               this_close=am["this_close"], closed_total=am["closed_total"])
    res["prices"], res["conversion"] = prices(w)
    if "CD" in res["types"] and not res["conversion"] and res["prices"] and not re.search(r"(?i)\bunits?\b", w[:1500]):
        res["prices"] = []
    res["warrants"] = warrants(w)
    res["refs"] = ref_dates(w)
    u = unit_counts(w, res)                    # 1.0.4
    res["units_offered"], res["units_this_close"], res["units_closed_total"] = u["offered"], u["this_close"], u["closed_total"]
    if role in ("tranche_close", "final_close"):
        res["parts"] = close_parts(w)
    return res


# ------------------------------------------------------------------ facts store adapter
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    fs = [F.Fact("is_financing", value_num=1.0 if a["is_financing"] else 0.0),
          F.Fact("reason", value_text=a["reason"])]
    if a["is_financing"]:
        fs.append(F.Fact("role", value_text=a["role"]))
        if a["tranche"]:
            fs.append(F.Fact("tranche", value_text=a["tranche"]))
        if a["types"]:
            fs.append(F.Fact("types", value_text="+".join(a["types"])))
        if a["offering"]:
            fs.append(F.Fact("offering", value_text=a["offering"]))
        fs.append(F.Fact("currency", value_text=a["currency"] or "CAD"))
        if a.get("lang") and a["lang"] != "en":
            fs.append(F.Fact("lang", value_text=a["lang"]))
        for fld in ("offered", "this_close", "closed_total"):
            if a[fld] is not None:
                fs.append(F.Fact("amount_" + fld, value_num=float(a[fld]), unit=a["currency"] or "CAD"))
        for fld in ("offered", "this_close", "closed_total"):
            if a.get("units_" + fld):
                fs.append(F.Fact("units_" + fld, value_num=float(a["units_" + fld])))     # 1.0.4
        for i, v in enumerate(a["offered_alt"]):
            fs.append(F.Fact("amount_offered_alt", value_num=float(v), unit=a["currency"] or "CAD", seq=i))
        for i, v in enumerate(a["prices"]):
            fs.append(F.Fact("unit_price", value_num=float(v), seq=i))
        if a["conversion"] is not None:
            fs.append(F.Fact("conversion_price", value_num=float(a["conversion"])))
        for i, wt in enumerate(a["warrants"]):
            if wt["per_unit"] is not None:
                fs.append(F.Fact("warrant_per_unit", value_num=float(wt["per_unit"]), seq=i))
            if wt["strike"] is not None:
                fs.append(F.Fact("warrant_strike", value_num=float(wt["strike"]), seq=i))
            if wt["term_months"] is not None:
                fs.append(F.Fact("warrant_term_months", value_num=float(wt["term_months"]), seq=i))
        for i, d in enumerate(a["refs"]):
            fs.append(F.Fact("ref_date", value_text=d, seq=i))
        for i, pt in enumerate(a["parts"]):
            fs.append(F.Fact("part_amount", value_num=float(pt["amount"]), unit=pt["currency"] or a["currency"] or "CAD", seq=i))
            if pt["types"]:
                fs.append(F.Fact("part_types", value_text="+".join(pt["types"]), seq=i))
            if pt["offering"]:
                fs.append(F.Fact("part_offering", value_text=pt["offering"], seq=i))
            if pt["currency"]:
                fs.append(F.Fact("part_currency", value_text=pt["currency"], seq=i))
            if pt["price"] is not None:
                fs.append(F.Fact("part_price", value_num=float(pt["price"]), seq=i))
    return [F.Record(KIND, facts=fs, confidence=1.0 if a["is_financing"] else 0.0)]


def parse_facts(rows):
    """rows: (field, seq, value_num, value_text) -> the analyse()-shaped dict the publisher uses."""
    a = {"is_financing": False, "reason": None, "role": None, "tranche": None, "types": [], "offering": None,
         "currency": "CAD", "offered": None, "offered_alt": [], "this_close": None, "closed_total": None,
         "prices": [], "conversion": None, "warrants": [], "refs": [], "parts": [], "lang": "en",
         "units_offered": None, "units_this_close": None, "units_closed_total": None}
    ws = {}
    pts = {}
    alts, prs, refs = {}, {}, {}
    for field, seq, num, text in rows:
        seq = int(seq or 0)
        if field == "is_financing":
            a["is_financing"] = num == 1.0
        elif field in ("reason", "role", "tranche", "offering", "currency", "lang"):
            a[field] = text
        elif field == "types":
            a["types"] = (text or "").split("+") if text else []
        elif field.startswith("amount_") and field != "amount_offered_alt":
            a[field[7:]] = num
        elif field.startswith("units_"):
            a[field] = int(num) if num is not None else None     # 1.0.4
        elif field == "amount_offered_alt":
            alts[seq] = num
        elif field == "unit_price":
            prs[seq] = num
        elif field == "conversion_price":
            a["conversion"] = num
        elif field.startswith("warrant_"):
            ws.setdefault(seq, {"per_unit": None, "strike": None, "term_months": None})[field[8:]] = num
        elif field == "ref_date":
            refs[seq] = text
        elif field.startswith("part_"):
            pt = pts.setdefault(seq, {"types": [], "offering": None, "currency": None, "amount": None, "price": None})
            key = field[5:]
            if key == "types":
                pt["types"] = (text or "").split("+") if text else []
            elif key in ("offering", "currency"):
                pt[key] = text
            else:
                pt[key] = num
    a["offered_alt"] = [alts[k] for k in sorted(alts)]
    a["prices"] = [prs[k] for k in sorted(prs)]
    a["warrants"] = [ws[k] for k in sorted(ws)]
    a["refs"] = [refs[k] for k in sorted(refs)]
    a["parts"] = [pts[k] for k in sorted(pts)]
    if a["warrants"]:
        for w_ in a["warrants"]:
            if w_["term_months"] is not None:
                w_["term_months"] = int(w_["term_months"])
    return a


def to_prediction(records):
    """The per-release view the accuracy judge scores (members are filled in by the publisher)."""
    if not records:
        return None
    rows = [(f.field, f.seq, f.value_num, f.value_text) for f in records[0].facts]
    return prediction_from(parse_facts(rows))


def prediction_from(a):
    if not a["is_financing"]:
        return None
    w = a["warrants"][0] if a["warrants"] else None
    return {"role": a["role"], "kind": list(a["types"]) + ([a["offering"]] if a["offering"] else []),
            "amounts": [x for x in (a["offered"], a["this_close"], a["closed_total"]) if x],
            "unit_price": a["prices"][0] if a["prices"] else (a["conversion"] if a["conversion"] else None),
            "warrant": dict(w) if w else None, "members": []}


def _code_sha():
    import hashlib
    import os
    h = hashlib.sha1()
    for p in (__file__, G.__file__):
        with open(p, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest() + "-" + os.path.basename(G.__file__)


SPEC = F.ExtractorSpec(NAME, VERSION, KIND, TAG, extract, _code_sha())


# ------------------------------------------------------------------ self-test
def self_test(verbose=False):
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print(f"  FAIL {name}: got {got!r}, want {want!r}")
        elif verbose:
            print(f"  ok   {name}")

    # 1.0.4: unit count, kept only when count x price equals a deal amount
    a = analyse("DLP Resources Announces Brokered LIFE Offering for Gross Proceeds of up to C$5 Million",
                "DLP Resources Inc. is pleased to announce a private placement for gross proceeds of up to C$5,000,000 from the sale "
                "of up to 20,000,000 units of the Company at a price of C$0.25 per Unit. Each Unit will consist of one common share "
                "and one common share purchase warrant.")
    eq("units offered", (a["units_offered"], a["units_this_close"]), (20000000, None))
    a = analyse("ABC Gold Closes Private Placement",
                "ABC Gold Corp. is pleased to announce that it has closed its non-brokered private placement, issuing 5,000,000 "
                "hard dollar units at $0.10 per unit and 3,000,000 flow-through units at $0.12 per FT unit for aggregate gross "
                "proceeds of $860,000. Insiders purchased 1,000,000 units. In connection with the closing the Company paid "
                "finder's fees and issued 240,000 finder's warrants.")
    eq("units closed: two kinds at two prices", (a["this_close"] or a["closed_total"], a["units_this_close"] or a["units_closed_total"]),
       (860000.0, 8000000))
    a = analyse("ABC Gold Announces Private Placement",
                "ABC Gold Corp. announces a non-brokered private placement of up to $500,000. The Company currently has "
                "45,000,000 common shares outstanding. The units will be priced at $0.05 per unit.")
    eq("an outstanding share count is not the deal's", a["units_offered"], None)
    got = parse_facts([(f.field, f.seq, f.value_num, f.value_text) for f in extract(
        "DLP Resources Announces Brokered LIFE Offering",
        "DLP Resources Inc. announces a private placement for gross proceeds of up to C$5,000,000 from the sale of up to "
        "20,000,000 units at a price of C$0.25 per Unit.")[0].facts])
    eq("units round-trip the facts store", got["units_offered"], 20000000)
    eq("clean ligature", clean("\ufb02ow-through $0. 26 C$ 0.35"), "flow-through $0.26 C$0.35")
    a = analyse("DLP Resources Announces Brokered LIFE Offering for Gross Proceeds of up to C$5 Million",
                "Cranbrook, British Columbia, May 7, 2026 - DLP Resources Inc. is pleased to announce that it has entered into an "
                "agreement with Red Cloud Securities Inc. to act as sole agent and bookrunner in connection with a \"best efforts\" "
                "private placement for gross proceeds of up to C$5,000,000 from the sale of up to 20,000,000 units of the Company at a "
                "price of C$0.25 per Unit. Each Unit will consist of one common share of the Company and one common share purchase "
                "warrant. Each Warrant will entitle the holder thereof to purchase one Common Share at a price of C$ 0.35 at any time "
                "during the period beginning on the date that is 61 days following the Closing Date and ending on the date which is "
                "36 months following the Closing Date. The Company also grants Red Cloud an option to sell up to an additional "
                "4,000,000 Units at the Offering Price for up to an additional C$1,000,000 in gross proceeds.")
    eq("dlp financing", (a["is_financing"], a["role"]), (True, "announcement"))
    eq("dlp type", (a["types"], a["offering"]), (["LIFE"], "BROKERED"))
    eq("dlp amounts", (a["currency"], a["offered"], a["offered_alt"]), ("CAD", 5000000.0, [6000000.0]))
    eq("dlp price", a["prices"], [0.25])
    eq("dlp warrant", a["warrants"], [{"per_unit": 1.0, "strike": 0.35, "term_months": 36}])
    a = analyse("Canamera Energy Metals Announces Non-Brokered Private Placement",
                "Canamera Energy Metals Corp. intends to complete a non-brokered private placement for gross proceeds of up to "
                "$3-million, consisting of two parts: Up to 1,785,714 flow-through units (\"FT Units\") at a price of $0.56 per FT Unit, "
                "with each FT unit consisting of one flow-through common share and one-half of one warrant, and with each whole FT "
                "Warrant exercisable at $0.65 to acquire one common share for 36 months. Up to 4,444,445 (non-flow-through) units at a "
                "price of $0.45 per Unit, with each Unit consisting of one (non-flow-through) common share and one-half of one warrant, "
                "with each whole warrant exercisable at $0.56 to acquire one share for 36 months.")
    eq("canamera types", (a["types"], a["offering"]), (["FT", "PP"], "NON_BROKERED"))
    eq("canamera offered", a["offered"], 3000000.0)
    eq("canamera prices", a["prices"], [0.56, 0.45])
    eq("canamera warrants", [(x["per_unit"], x["strike"], x["term_months"]) for x in a["warrants"]], [(0.5, 0.65, 36), (0.5, 0.56, 36)])
    a = analyse("Rise Gold Closes US$7,000,000 Financing",
                "Rise Gold Corp. is pleased to announce that it has closed its non-brokered private placement of 28,000,000 units at "
                "a price of US$0.25 per unit for gross proceeds of US$7,000,000. Directors and officers of the Company purchased "
                "1,080,000 units for gross proceeds of US$270,000.")
    eq("rise close", (a["role"], a["currency"], a["this_close"], a["closed_total"]), ("final_close", "USD", 7000000.0, 7000000.0))
    a = analyse("Sendero Resources Announces Closing of Second Tranche of Private Placement",
                "Sendero has closed the second tranche of its private placement for gross proceeds of $450,000. Together with the first "
                "tranche, the Company has raised aggregate gross proceeds of $1,250,000 under the offering of up to $2,000,000.")
    eq("tranche amounts", (a["role"], a["this_close"], a["closed_total"], a["offered"]), ("tranche_close", 450000.0, 1250000.0, 2000000.0))
    eq("warrant exercise is not a raise", analyse("Casa Minerals Receives Proceeds of $432,777 from Warrant Exercises", "")["is_financing"], False)
    eq("results not a raise", analyse("Artemis Gold Reports Q2 2025 Results", "")["is_financing"], False)
    eq("investor side", analyse("Franco-Nevada Announces A$200 Million Follow-on Financing Package with Minerals 260 for the Bullabulling Gold Project",
                                "Franco-Nevada Corporation is pleased to announce that it will provide a A$200 million financing package to Minerals 260 Limited.")["is_financing"], False)
    eq("strategic investment from", analyse("Kingfisher Announces Strategic Investment from Barrick", "Kingfisher Metals Corp. is pleased to announce a strategic investment by Barrick of $20,885,761 at $1.35 per share.")["is_financing"], True)
    a = analyse("Metalero Mining Closes Oversubscribed Private Placement", "Metalero Mining Corp. is pleased to announce that it has closed its non - brokered private placement.")
    eq("non - brokered", a["offering"], "NON_BROKERED")
    eq("term words", _term_months(_RE_W_TERM.search("exercisable for a period of two (2) years")), 24)
    eq("refs", ref_dates("Further to its news release dated August 1, 2025, it has closed"), ["2025-08-01"])
    eq("fully subscribed is an update", analyse("Xali Gold Private Placement Fully Subscribed", "Xali Gold Corp. announces its private placement of $1,000,000 is fully subscribed.")["role"], "update")
    recs = extract("Rise Gold Closes US$7,000,000 Financing", "Rise Gold Corp. has closed its private placement of units at US$0.25 per unit for gross proceeds of US$7,000,000.")
    p = to_prediction(recs)
    eq("prediction", (p["role"], p["amounts"], p["unit_price"]), ("final_close", [7000000.0, 7000000.0], 0.25))
    # 1.0.1
    a = analyse("Gold Terra Closes Third and Final Tranche of Its LIFE Offering for Gross Proceeds of Approximately C$10.1 M",
                "This release is published on Accesswire. Click 'Original source' to read the full release.")
    eq("101 headline-only final total", (a["role"], a["offered"], a["this_close"], a["closed_total"]), ("final_close", None, None, 10100000.0))
    a = analyse("Nevada Organic Phosphate Increases Unit Offering and Closes Final Tranche of $1,011,135 for Aggregate Gross Proceeds of $2,313,136", "")
    eq("101 tranche of X for aggregate Y", (a["this_close"], a["closed_total"], a["offered"]), (1011135.0, 2313136.0, None))
    h = "GoldQuest Closes Third and Final Tranche of Private Placement for Gross Proceeds of Approximately C$3.3 Million"
    a = analyse(h, h + " Vancouver, January 13, 2026 - GoldQuest Mining Corp. is pleased to announce the closing of the third and final "
                "tranche of its previously announced non-brokered private placement. Under the Third Tranche, the Company issued "
                "2,744,542 Units at a price of C$1.21 per Unit, for total gross proceeds of approximately C$3.3 million. Combined with "
                "the First Tranche and Second Tranche, the Company has issued a total of 34,710,743 Units under the Private Placement, "
                "for gross proceeds of approximately C$42 million.")
    eq("101 headline copy, scoped tranche, combined total", (a["this_close"], a["closed_total"]), (3300000.0, 42000000.0))
    a = analyse("South Star Closes Final Tranche", "South Star Battery Metals Corp. has completed the closing of the third and final tranche "
                "of its non-brokered private placement for gross proceeds to the Company of US$879,449.45 (CA$1,231,229.06). When combined "
                "with Tranche 1 and Tranche 2, the gross proceeds of the Private Placement to the Company total US$3,000,000 (CA$4,200,000).")
    eq("101 bracketed conversion", (a["currency"], a["this_close"], a["closed_total"]), ("USD", 879449.45, 3000000.0))
    a = analyse("Foremost Lithium Announces Closing of the Second Tranche of its Flow-Through Private Placement",
                "Foremost announces that on April 29, 2024, it closed the second tranche of its non-brokered private placement for aggregate "
                "gross proceeds of $1,455,129.48. Foremost issued 247,471 flow-through units at a price of $5.88 per FT Unit.")
    eq("101 tranche sentence aggregate is this close", (a["this_close"], a["closed_total"]), (1455129.48, None))
    a = analyse("ATHA Energy Closes $63 Million In Financings",
                "ATHA Energy Corp. is pleased to announce that it has closed approximately C$63 million in new financing: further to its press "
                "releases dated January 13 and January 22, 2026, the Company has closed its private placement of USD$25 million (approximately "
                "C$34,130,000 million) principal amount of unsecured convertible debentures with Queen's Road Capital; and further to its press "
                "release dated January 15, 2026, the Company has closed its best efforts brokered private placement of charity flow-through "
                "common shares through the issuance of 28,186,500 FT Shares at a price per FT Share of C$1.02 for aggregate gross proceeds of "
                "C$28,750,230 (the LIFE Offering).")
    eq("101 close parts", [(x["types"], x["currency"], x["amount"]) for x in a["parts"]],
       [(["CD"], "USD", 25000000.0), (["FT", "LIFE"], "CAD", 28750230.0)])
    a = analyse("Gold X2 Announces Closing of First Tranche of Private Placement for Gross Proceeds of Approximately $43,160,000",
                "Gold X2 has closed the first tranche of its non-brokered private placement. The Company issued 23,800,000 units at a price of "
                "$0.95 per Unit for gross proceeds of $22,610,000 and 16,666,666 charity flow-through shares at a price of $1.233 per Charity FT "
                "Share for gross proceeds of $20,549,999.18. The Company intends to close the second and final tranche of the Private Placement "
                "on or about March 27, 2026.")
    eq("101 headline = sum of body closes, first tranche", (a["this_close"], a["closed_total"]), (43159999.18, 43159999.18))

    # ---------------------------------------------------------------- 1.0.3
    a = analyse("Showcase Announces $450,000 Private Placement Offering",
                "Showcase Minerals Inc. (CSE: SHOW) is pleased to announce a private placement offering of up to 1,500,000 units at "
                "$0.30 per unit. Each unit will consist of one common share and one two-year share purchase warrant entitling the "
                "holder to acquire an additional common share for $0.40/share.")
    eq("103 term in words before the noun", a["warrants"], [{"per_unit": 1.0, "strike": 0.4, "term_months": 24}])
    a = analyse("Goldgroup Announces Upsizing of Private Placement",
                "Each Unit will consist of one common share (a \"Common Share\") and one-half common share purchase warrant, with each "
                "full warrant (a \"Warrant\") being exercisable to purchase one Common Share at a price of $0.45 for 24 (twenty-four) "
                "months from the date of issuance.")
    eq("103 bracketed word number", a["warrants"][0]["term_months"], 24)
    a = analyse("Kodiak Announces $5 Million Non-Brokered Private Placement",
                "Common share units (the \"HD Units\"), each of which HD Unit will consist of one non-flow-through Common Share and "
                "one-half of one non-transferable common share purchase warrant (each whole warrant, a \"Warrant\"), at a price of "
                "$0.42 per HD Unit. Each Warrant will be exercisable at a price of $0.75 for a period of 24 months.")
    eq("103 unit price is not the strike", a["warrants"][0]["strike"], 0.75)
    a = analyse("Nortec Completes $605,000 Non-Brokered Private Placement",
                "Each Unit consists of one common share and one common share purchase warrant. Warrant Terms Each whole Warrant shall "
                "have a term of 36-months, subject to acceleration; During the first 18-months after closing, the exercise price of "
                "each Warrant shall be C$0.065 and thereafter C$0.11 per common share.")
    eq("103 term stated away from the unit sentence", a["warrants"][0]["term_months"], 36)
    a = analyse("Ashley Gold Corp. Closes First Tranche of Private Placement",
                "The closing of the first tranche consists of the following: - 1,578,922 units of FT at $0.095 with a 2 year half "
                "warrant at $0.15 for gross proceeds of $149,795.09.")
    eq("103 inline term and strike", (a["warrants"][0]["strike"], a["warrants"][0]["term_months"]), (0.15, 24))
    a = analyse("Muzhu announces Closing of First Tranche of Financing and Upsize of Private Placement",
                "Muzhu Mining Corp. announces that it has closed the first tranche of its non-brokered private placement for gross "
                "proceeds of $250,000, and has increased the size of the offering to $1,000,000.")
    eq("103 a tranche close that also upsizes", (a["role"], a["tranche"], a["this_close"]), ("tranche_close", "first", 250000.0))
    a = analyse("Newpath Resources Closes Second and Final Tranche of Private Placement Financing",
                "The Company closed the second tranche by issuing 1,928,571 units at a price of $0.07 per Unit. The total gross "
                "proceeds raised from the Second Tranche is $135,000 and a total net proceeds of $105,000, as $30,000 was part of a "
                "repayment to a consultant of the Company. The total gross proceeds raised from both the first and Second Tranche of "
                "the previously announced private placement is $611,850.")
    eq("103 net proceeds are not the deal", (a["this_close"], a["closed_total"]), (135000.0, 611850.0))
    a = analyse("Irving Resources Reports Upsized Private Placement",
                "Further to its news release of January 22, 2026, Irving Resources Inc. has upsized its non-brokered private "
                "placement, from $2,000,000 to $4,000,000. The gross proceeds will be raised by the issuance of units at a price of "
                "$0.25 per Unit.")
    eq("103 upsized from X to Y", (a["role"], a["offered"]), ("upsize", 4000000.0))
    a = analyse("American Tungsten Announces Correction to Warrant Terms of Upsized Bought Deal",
                "American Tungsten Corp. announces a correction to the warrant terms of its previously announced upsized bought deal "
                "private placement for gross proceeds of C$34,784,400.")
    eq("103 a correction amends, it does not upsize", a["role"], "amendment")
    a = analyse("Lithium Americas Files Prospectus Supplement",
                "Filed Pursuant to Rule 424(b)(3) Registration Statement No. 333-287327. The Company may offer and sell common shares "
                "having an aggregate offering price of up to $250,000,000 from time to time through its at-the-market equity program.")
    eq("103 an SEC-filed offering is in US dollars", a["currency"], "USD")

    # ---------------------------------------------------------------- 1.0.5 (FIX5)
    a = analyse("Northbay Metals Announces Revised Terms of Private Placement",
                "Northbay Metals Inc. announces that, further to its news release on June 1, 2026, it has revised the terms of its "
                "non-brokered private placement. The Company will now issue up to 8,000,000 units at a price of $0.25 per unit for "
                "gross proceeds of up to $2,000,000.")
    eq("105 revised terms is an amendment", a["role"], "amendment")
    a = analyse("Northbay Metals Announces Price Change for its Proposed Private Placement",
                "Northbay Metals Inc. announces it is repricing its private placement offering announced on May 4, 2026 from $0.05 "
                "per Unit to $0.035 per Unit for gross proceeds of up to $500,000.")
    eq("105 price change is an amendment; the old price is not an issue price", (a["role"], a["prices"]), ("amendment", [0.035]))
    a = analyse("Northbay Metals Announces Update on Private Placement",
                "Northbay Metals Inc. is pleased to provide an update on the terms of its previously announced non-brokered private "
                "placement. The units will now be offered at a price of $0.14 per unit.")
    eq("105 an update on the terms is an amendment", a["role"], "amendment")
    a = analyse("NORTHBAY ANNOUNCES UPDATES ON ITS NON-BROKERED PRIVATE PLACEMENT",
                "Northbay Metals Inc. announces that further to its news release of June 24, 2026, wherein it had announced a "
                "non-brokered private placement of up to 30,000,000 units at a price of $0.05 per unit to raise gross proceeds of up "
                "to $1,500,000, the Company is continuing to collect subscriptions.")
    eq("105 updates on is an update", a["role"], "update")
    a = analyse("Northbay Closes on First Tranche of US$6 Million under Credit Facility",
                "Northbay Metals Inc. announces that, further to its news release dated August 14, 2026, it has drawn down and "
                "received US$6 million in funding under the first tranche of its credit agreement dated August 14, 2026.")
    eq("105 a drawdown under an existing facility is an update", (a["role"], a["types"]), ("update", ["DEBT"]))
    a = analyse("Northbay Metals Announces Non-Brokered Private Placement",
                "Northbay Metals Inc. announces a non-brokered private placement for the sale of: (i) a minimum of 13,333,334 units "
                "at a price of $0.15 per Unit for aggregate gross proceeds of $2,000,000; and (ii) a maximum of 23,333,334 Units at "
                "the Offering Price for aggregate gross proceeds of $3,500,000.")
    eq("105 a minimum and a maximum: the size is the maximum", a["offered"], 3500000.0)
    a = analyse("Northbay Announces Proposed Non-Brokered Private Placement",
                "Northbay Metals Inc. is proposing to complete a flow-through and non flow-through private placement. Under the "
                "flow-through portion, the Corporation intends to raise up to approximately $1,200,000 in gross proceeds by issuing "
                "flow-through units. Under the non flow-through portion, the Corporation intends to raise up to approximately "
                "$500,000 in gross proceeds by issuing non flow-through units. The Corporation has accepted subscriptions in "
                "aggregate gross proceeds of approximately $371,000.")
    eq("105 non flow-through spelled with a space is the hard-dollar part", (a["offered"], a["offered_alt"]), (1700000.0, [1200000.0, 500000.0]))
    a = analyse("Northbay Closes Financing",
                "Northbay Metals Inc. announces that the Company has closed the final tranche of the private placement. On December "
                "28, 2025, the Company announced it had closed its first tranche of a non-brokered flow-through private placement of "
                "8,166,667 flow-through units to raise gross proceeds of $735,000. A second tranche of 1,770,000 non flow-through "
                "units at a price of $0.05 per unit has also closed, raising gross proceeds of $88,500.")
    eq("105 an earlier release's close is not this close", (a["role"], a["this_close"]), ("final_close", 88500.0))
    # ---- 1.0.6 (FIX8, 2026-10-06): prices that are not unit prices
    eq("1.0.6 a warrant's price written far from the word warrant is not a unit price", prices(
        "up to 5,714,285 Units at a price of $0.35 per Unit for gross proceeds of up to $2,000,000. Each Unit consists of one "
        "common share and one common share purchase warrant (a Warrant). Each Warrant will entitle the holder to purchase one "
        "Share at a price of $0.40 for a period of 24 months from the closing date.")[0], [0.35])
    eq("1.0.6 an acceleration trigger is not a unit price", prices(
        "5,000,000 units at a purchase price of $0.20 per Unit for gross proceeds of $1,000,000. If, after the expiry date, the "
        "closing price of the Company's shares on the TSX Venture Exchange trades at or above a price of $0.45 per share for "
        "10 consecutive trading days, the Company may accelerate the expiry.")[0], [0.2])
    eq("1.0.6 a deemed price is not a unit price", prices(
        "up to 5,128,205 units at a price of $0.195 per Unit for gross proceeds of up to $1,000,000. The number of common "
        "shares to be issued, 1,851,248, and the deemed issue price of $0.25 per common share remain unchanged.")[0], [0.195])
    eq("1.0.6b one or more agents is not an acceleration trigger", prices(
        "an agreement with an agent on behalf of a syndicate of one or more additional agents in connection with a best efforts "
        "private placement of up to 33,333,334 units at a price of C$0.15 per Unit for gross proceeds of up to C$5 million.")[0], [0.15])
    eq("1.0.6b accelerating the development in the sentence before is not a trigger", prices(
        "We look forward to accelerating the development of the Company\u2019s properties during 2018.\u201d The Private Placement "
        "consisted of 7,207,890 units issued at $0.275 per Unit with each Unit consisting of one common share.")[0], [0.275])
    eq("1.0.6b may not exceed is not a trigger", prices(
        "The offering may not exceed 10,000,000 units at a price of $0.12 per unit.")[0], [0.12])
    eq("1.0.6b subject to acceleration still drops the trigger price", prices(
        "8,000,000 units at a price of $0.40 per unit for gross proceeds of $3,200,000. Each warrant is exercisable at $0.50 for 12 months, subject to acceleration, in the event "
        "that the shares close trading at $0.65 for ten consecutive days.")[0], [0.4])
    eq("1.0.6c a minimum offering size is not a trigger", prices(
        "The Offering will consist of the issuance of no less than 4,000,000 common shares and up to 10,000,000 common shares at "
        "price of $0.025 per common share.")[0], [0.025])
    eq("1.0.6c an offering priced on the VWAP keeps its price", prices(
        "The Shares were issued at a price equal to the 10-day volume weighted average trading price of the Shares on the Canadian "
        "Securities Exchange at the date of signing of the subscription agreement, being $2.05 per Share (the Offering Price).")[0], [2.05])
    eq("1.0.6c per share and associated warrant is the price", prices(
        "Pursuant to the Private Placement, the Company issued 15,625,000 Common Shares and Warrants to purchase up to 15,625,000 "
        "Common Shares at a purchase price of Cdn$0.32 per Common Share and associated Warrant.")[0], [0.32])
    eq("1.0.6c a closing-price trigger still drops", prices(
        "provided that, in the event the Shares trade at a closing price on the Exchange of greater than $0.15 per Share for a "
        "period of 10 consecutive trading days at any time, the Company may accelerate the expiry.")[0], [])
    eq("1.0.6d more than N shares is not a trigger", prices(
        "As a result of being oversubscribed, the Private Placement will now consist of more than 3,333,333 common shares of the "
        "Company (Shares) at a purchase price of $0.30 per Share.")[0], [0.3])
    eq("1.0.6d a per-unit price in a sentence about the acceleration right is the offering price", prices(
        "announces a revision to the warrant Acceleration Right in respect of its previously announced private placement financing of "
        "up to 13,250,000 units at a price of C$0.40 per Unit (the Offering Price), for aggregate gross proceeds of up to C$5.3 million.")[0], [0.4])
    eq("1.0.6d is greater than right before the price is a trigger", prices(
        "Opawica may accelerate the expiry date of the Warrants if the daily trading price of the Common Shares on the TSX Venture "
        "Exchange is greater than $0.34 per Common Share for the preceding 10 consecutive trading days.")[0], [])
    eq("1.0.6 flow-through and hard-dollar prices both stay", prices(
        "up to 6,000,000 Flow-Through units at a price of $0.25 per unit and up to 5,000,000 Non-Flow-Through units at a "
        "price of $0.20 per unit, for aggregate gross proceeds of up to $2,500,000.")[0], [0.25, 0.2])
    print(f"financings self-test: {'ok' if not bad else str(bad) + ' failures'}")
    return bad


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(1 if self_test() else 0)
