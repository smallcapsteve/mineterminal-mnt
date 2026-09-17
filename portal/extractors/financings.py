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

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    what the facts store keeps (one record per release)
to_prediction(records)  -> dict|None   what the accuracy check compares (grouping comes from the publisher)

Self-tests: python3 -m portal.extractors.financings
"""
from __future__ import annotations

import re
import unicodedata

from portal import facts as F
from portal.extractors import fin_grammar as G

NAME = "financings"
VERSION = "1.0.0"
KIND = "financing"
TAG = "Financings"
TEXT_CAP = 8000

ROLES = ("announcement", "upsize", "amendment", "tranche_close", "final_close", "terminated", "update")


# ------------------------------------------------------------------ text
_WS = re.compile(r"[ \t  -​  　]+")


def clean(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("‐", "-").replace("‑", "-").replace("‒", "-").replace("–", "-") \
        .replace("—", "-").replace("−", "-").replace("­", "")
    t = t.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
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


_RE_PER = re.compile(r"(?i)^\s*(?:\(\s*[^)]{0,30}\)\s*)?(?:per|/|for\s+each|each)\b")
_RE_NOT_DEAL_AMT_BEFORE = re.compile(
    r"(?i)(?:\b(?:insiders?|directors?|officers?|management|related\s+part(?:y|ies)|participat\w*|subscribed\s+by"
    r"|finders?'?|finder's|commissions?|fees?|cash\s+(?:position|balance|on\s+hand)|treasury|working\s+capital"
    r"|previously\s+(?:closed|completed|raised)|recently\s+(?:closed|completed)|last\s+year|since\s+inception"
    r"|to\s+date\s+(?:has|have)\s+raised|in\s+addition\s+to|market\s+capitali[sz]ation|valued\s+at|valuation"
    r"|exploration\s+(?:expenditures?|budget|program)|spend|expenditures?|payment\s+of|pa(?:y|ys|id|ying)|purchase\s+price|(?:equity|enterprise|total|transaction)\s+value|representing|non-dilutive|funding\s+transaction|grant|application\s+for|guarantee|EBITDA|profit|loss"
    r"|consideration|acquisition|interest|royalty|revenue|net\s+smelter|NPV|IRR|capex|capital\s+cost"
    r"|debt\s+of|indebtedness|loan\s+of|owed|settle\w*)\b[^$]{0,60}$)")


def money_kind(text: str, v, start: int, end: int) -> str:
    """'price' | 'strike' | 'conversion' | 'other' | 'deal' for one figure, from its words around it."""
    after = text[end:end + 40]
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
    if re.search(r"(?i)\bexercis\w*[^$]{0,60}$|\bexercise\s+price\b[^$]{0,80}$", before[-140:]) and v is not None and v < 1000 \
            and not re.match(r"(?i)\s*per\s+(?:FT\s+|flow-through\s+|NFT\s+|hard[\s\-]dollar\s+)?units?\b", after):
        return "strike"
    if _RE_PER.match(after) or re.match(r"(?i)\s*(?:\(the\s+\"?(?:offering|issue|unit|subscription)\s+price)", after):
        return "price" if v is not None and v < 1000 else "other"
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
    r"|files?\s+(?:a\s+|its\s+)?(?:final|amended)|update\s+(?:on|to|regarding)|provides?\s+(?:an\s+)?update"
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
            h + " " + window[:1500]):
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
    return role, tranche


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
_RE_UPTO = re.compile(r"(?i)\b(?:up\s+to|maximum\s+of|a\s+maximum|not\s+to\s+exceed|of\s+up\s+to)\s+(?:an?\s+aggregate\s+of\s+|approximately\s+|gross\s+proceeds\s+of\s+)?$")
_RE_ADDITIONAL = re.compile(r"(?i)\b(?:additional|further|over[\s\-]allotment|agents?'?\s*'?s?\s+option|underwriters?'?\s*'?s?\s+option|greenshoe)\b[^.$]{0,60}$")
_RE_FT_WORD = re.compile(r"(?i)\bflow-through|\bFT\s+(?:units?|shares?)|\bcharity\s+(?:FT|flow)|\bCFT\b")
_RE_NFT_WORD = re.compile(r"(?i)non-flow-through|\bNFT\b|hard[\s\-]dollar|\bHD\s+units?|working\s+capital\s+units?|\bWC\s+units?")


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
    r"|\bto\s+date\b[^.$]{0,40}$|\bin\s+(?:the\s+)?aggregate\s+(?:of\s+)?$|\bfor\s+(?:a\s+)?total\s+of\s+$|\bfor\s+aggregate\s+(?:gross\s+)?proceeds\s+of\s+$")
_RE_TOTAL_AFTER = re.compile(r"(?i)^\s*(?:\S+\s+){0,3}(?:in\s+(?:the\s+)?aggregate|to\s+date|in\s+total)\b")
_RE_CLOSE_CTX = re.compile(r"(?i)\b(?:closed|completed|closing|issued|has\s+issued|completion|raised|sold)\b")
_RE_FUTURE_CTX = re.compile(r"(?i)\b(?:will|intends?|expects?|anticipated|proposed|up\s+to|may|subject\s+to|to\s+be)\b")


def _sentence(text, start, end):
    a = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start))
    b = text.find(". ", end)
    return text[a + 1 if a >= 0 else 0: b if b >= 0 else len(text)]


def amounts(h: str, window: str, role: str):
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
                   "pre_tranche": bool(re.match(r"(?i)\s*(?:(?:first|second|third|fourth|final|initial|1st|2nd|3rd)\s+)?tranche\b", h[e:e + 25]))})
    body = []
    w = window[:4000]
    for v, cur, s, e in monies(w):
        if not G.plausible_gross(v):
            continue
        k = money_kind(w, v, s, e)
        if k != "deal":
            continue
        before = w[max(0, s - 160):s]
        sent = _sentence(w, s, e)
        body.append({"v": v, "cur": cur, "s": s, "upto": bool(_RE_UPTO.search(before[-45:])),
                     "minimum": bool(re.search(r"(?i)\bminimum\b[^$]{0,40}$", before[-60:])),
                     "part": _part(before[-170:]), "combo": bool(re.search(r"(?i)non-dilutive|combined\s+with|together\s+with\s+(?:the\s+)?(?:\w+\s+)?(?:funding|grant|loan|facility)|when\s+combined", sent)),
                     "add": bool(_RE_ADDITIONAL.search(before[-70:])),
                     "total": bool(_RE_TOTAL_BEFORE.search(before[-130:]) or _RE_TOTAL_AFTER.match(w[e:e + 40])),
                     "gross": bool(re.search(r"(?i)\bproceeds\s+(?:to\s+the\s+company\s+)?(?:of\s+)?(?:up\s+to\s+|approximately\s+|a\s+(?:minimum|maximum)\s+of\s+|not\s+less\s+than\s+)?$", before[-60:])),
                     "closed": bool(_RE_CLOSE_CTX.search(sent)), "future": bool(_RE_FUTURE_CTX.search(before[-100:])),
                     "sent": sent})
    curs = [x["cur"] for x in hd + body if x["cur"]]
    out["currency"] = curs[0] if curs else "CAD"

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
            out["offered"] = c["v"] if c else None
        else:
            c = (pick(hd, upto=True) or (hd[0] if hd else None))
            nb = [b for b in body if not b["add"] and not b["minimum"]]
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
        bclose = [b for b in body if not b["add"] and not b["upto"] and b["closed"] and not b["total"] and not b["minimum"] and b["s"] < 2500]
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
                       and (not b["upto"] or b["closed"]) and b["s"] < 2000), None)
            if fb:
                out["this_close"] = fb["v"]
        if btot:
            t = max(btot, key=lambda b: b["v"])
            if out["this_close"] is None or t["v"] >= out["this_close"] - 1:
                out["closed_total"] = t["v"]
            smaller = [b for b in btot if b["v"] < t["v"] - 1 and b["s"] < t["s"]]
            if smaller and (out["this_close"] is None or (comp and out["this_close"] < smaller[0]["v"])):
                out["this_close"] = smaller[0]["v"]
            if out["this_close"] is None and len(btot) == 1 and not tranche_head:
                out["this_close"] = t["v"]
        if out["closed_total"] is None and out["this_close"] is not None:
            first = re.search(r"(?i)\b(?:first|initial|1st)\s+tranche|tranche\s+(?:1|one|i)\b", h + " " + w[:600])
            later = re.search(r"(?i)\b(?:second|third|fourth|fifth|2nd|3rd|4th|5th|subsequent|additional|further)\s+(?:and\s+final\s+)?tranche"
                              r"|tranche\s+(?:2|3|4|two|three|four|ii|iii|iv)\b", h + " " + w[:600])
            if (role == "final_close" and not later and not tranche_head) or (first and not later):
                out["closed_total"] = out["this_close"]
        # the deal's size, when the close release restates it
        up = pick(hd, of=True) or pick(hd, upto=True)
        bu = pick([b for b in body if not b["add"]], upto=True)
        ref = out["closed_total"] or out["this_close"]
        plaus = lambda v: ref is None or (ref * 0.3 <= v <= ref * 4)
        if up and up["v"] != out["this_close"] and plaus(up["v"]):
            out["offered"] = up["v"]
        elif bu and bu["v"] != out["this_close"] and plaus(bu["v"]) and bu["s"] < 2500:
            out["offered"] = bu["v"]
    return out


# ------------------------------------------------------------------ prices and warrants
_RE_EXCLUDE_WARRANT = re.compile(r"(?i)\b(?:finders?'?|finder's|broker(?:'s)?|brokers'|agents?'|agent's|compensation|advisory|bonus)\s+(?:\w+\s+){0,2}warrants?\b")


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
            if all(abs(v - g) > 1e-9 for g in got):
                got.append(v)
        if len(got) >= 3:
            break
    return got, conv


_RE_W_FRACTION = re.compile(
    r"(?i)\b(?P<frac>one[\s\-]half|1/2|½|one[\s\-]third|1/3|one[\s\-]quarter|one[\s\-]fourth|three[\s\-]quarters?"
    r"|one\s*\(1\)|one|a|1|two|2)\s*(?:\(\s*(?:1/2|½|0\.5|1/3|1)\s*\)\s*)?(?:of\s+one\s+(?:\(1\)\s+)?)?"
    r"(?:(?:whole|transferable|non-transferable|common|share|stock|purchase|non-flow-through|NFT|FT|subscription)\s+){0,4}warrants?\b")
_FRAC = {"one-half": 0.5, "one half": 0.5, "1/2": 0.5, "½": 0.5, "one-third": 1 / 3, "one third": 1 / 3, "1/3": 1 / 3,
         "one-quarter": 0.25, "one quarter": 0.25, "one-fourth": 0.25, "one fourth": 0.25, "three-quarters": 0.75,
         "three-quarter": 0.75, "three quarters": 0.75, "one (1)": 1.0, "one": 1.0, "a": 1.0, "1": 1.0, "two": 2.0, "2": 2.0}
_RE_W_TERM = re.compile(
    r"(?i)\b(?:(?:for\s+a\s+(?:period|term)\s+of|for|within|until\s+the\s+date\s+that\s+is|ending\s+on\s+the\s+date\s+which\s+is"
    r"|(?:before|until|ending\s+on|on)\s+the\s+date\s+(?:that|which)\s+is|expir\w*\s+(?:on\s+the\s+date\s+that\s+is\s+)?|term\s+of|period\s+of|up\s+to)\s+)"
    r"(?P<n>\d{1,2}|one|two|three|four|five|six|twelve|eighteen|twenty[\s\-]four|thirty[\s\-]six|forty[\s\-]eight|sixty)"
    r"\s*(?:\(\s*\d{1,2}\s*\)\s*)?(?P<u>months?|years?)\b"
    r"|\b(?P<n2>\d{1,2}|two|three|five)[\s\-](?P<u2>month|year)\s+(?:term|period|warrants?|expiry)")


def _term_months(m):
    n = m.group("n") or m.group("n2")
    u = (m.group("u") or m.group("u2") or "").lower()
    n = n.lower().replace(" ", "-")
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
    r"(?i)\b(one-half|one\s+half|1/2|½|one-third|one\s+third|1/3|one-quarter|one-fourth|three-quarters?|one|a|an|1|two|2)\b"
    r"(?:\s*\(\s*(?:1/2|½|0\.5|1/3|1|2)\s*\))?(?:\s+of\s+(?:one|a)(?:\s*\(1\))?)?"
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
        if per is None and frac in ("an",):
            per = 1.0
        return _Frac(per, wm.start() - len(pre) + fm.start() + max(0, 0), wm.end())
    return None


_RE_W_TERM_STOP = re.compile(r"(?i)\bhold\s+period|four\s+months\s+and\s+(?:a|one)\s+day|accelerat\w*|insiders?\b|proceeds\b|finders?\b|related\s+party")


def _warrant_term(seg):
    """The longest term stated in the warrant's own description (stepped prices: '18 months ... or 36 months')."""
    stop = _RE_W_TERM_STOP.search(seg)
    part = seg[:stop.start()] if stop else seg[:500]
    terms = [x for x in (_term_months(t) for t in _RE_W_TERM.finditer(part)) if x]
    return max(terms) if terms else None


def warrants(window: str):
    """[{per_unit, strike, term_months}] one per unit type, in text order."""
    w = window[:4500]
    out = []
    for m in re.finditer(r"(?i)\beach\s+(?:\S+\s+){0,4}?(?:units?|FT\s+units?|flow-through\s+units?)\b[^.]{0,40}?\b(?:consist\w*|compris\w*|is\s+comprised|will\s+be\s+comprised|shall\s+consist)\b"
                         r"|\bunits?\b[^.]{0,30}\b(?:each\s+)?(?:consisting|comprised|composed)\s+of\b", w):
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
            k = money_kind(seg, v, s, e)
            if k == "strike" or (k in ("price", "other") and re.search(r"(?i)\b(?:exercis\w*|purchase|acquire)\b[^.$]{0,120}$", seg[max(0, s - 160):s])
                                 and re.search(r"(?i)warrant", seg[max(0, s - 260):s])):
                if 0.001 <= v < 1000:
                    strike = v
                    break
        tm = _warrant_term(seg[fm.start():])
        key = (per, strike, tm)
        if strike is None and tm is None and per is None:
            continue
        if any((o["per_unit"], o["strike"], o["term_months"]) == key for o in out):
            continue
        out.append({"per_unit": per, "strike": strike, "term_months": tm})
        if len(out) >= 3:
            break
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
    return out


# ------------------------------------------------------------------ references to earlier releases
_MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december"
           "|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
_MONTH_NUM = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_RE_REF = re.compile(
    r"(?i)\b(?:further\s+to|as\s+(?:previously\s+)?(?:announced|disclosed)\s+(?:in|on)|(?:news|press)\s+releases?\s+(?:dated|of|on|issued\s+on)"
    r"|announced\s+on|previously\s+announced\s+(?:on|in)|see\s+(?:the\s+)?(?:company's\s+)?(?:news|press)\s+release)"
    r"[^.]{0,80}?\b(" + _MONTHS + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d|19\d\d)")


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
           "warrants": [], "refs": []}
    if not ok:
        return res
    res["types"], res["offering"] = deal_types(h, w, h_main)
    am = amounts(h, w, role)
    res.update(currency=am["currency"], offered=am["offered"], offered_alt=am["offered_alt"],
               this_close=am["this_close"], closed_total=am["closed_total"])
    res["prices"], res["conversion"] = prices(w)
    if "CD" in res["types"] and not res["conversion"] and res["prices"] and not re.search(r"(?i)\bunits?\b", w[:1500]):
        res["prices"] = []
    res["warrants"] = warrants(w)
    res["refs"] = ref_dates(w)
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
        for fld in ("offered", "this_close", "closed_total"):
            if a[fld] is not None:
                fs.append(F.Fact("amount_" + fld, value_num=float(a[fld]), unit=a["currency"] or "CAD"))
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
    return [F.Record(KIND, facts=fs, confidence=1.0 if a["is_financing"] else 0.0)]


def parse_facts(rows):
    """rows: (field, seq, value_num, value_text) -> the analyse()-shaped dict the publisher uses."""
    a = {"is_financing": False, "reason": None, "role": None, "tranche": None, "types": [], "offering": None,
         "currency": "CAD", "offered": None, "offered_alt": [], "this_close": None, "closed_total": None,
         "prices": [], "conversion": None, "warrants": [], "refs": []}
    ws = {}
    alts, prs, refs = {}, {}, {}
    for field, seq, num, text in rows:
        seq = int(seq or 0)
        if field == "is_financing":
            a["is_financing"] = num == 1.0
        elif field in ("reason", "role", "tranche", "offering", "currency"):
            a[field] = text
        elif field == "types":
            a["types"] = (text or "").split("+") if text else []
        elif field.startswith("amount_") and field != "amount_offered_alt":
            a[field[7:]] = num
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
    a["offered_alt"] = [alts[k] for k in sorted(alts)]
    a["prices"] = [prs[k] for k in sorted(prs)]
    a["warrants"] = [ws[k] for k in sorted(ws)]
    a["refs"] = [refs[k] for k in sorted(refs)]
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

    eq("clean ligature", clean("ﬂow-through $0. 26 C$ 0.35"), "flow-through $0.26 C$0.35")
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
    print(f"financings self-test: {'ok' if not bad else str(bad) + ' failures'}")
    return bad


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(1 if self_test() else 0)
