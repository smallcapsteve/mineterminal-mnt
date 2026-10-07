"""Outside-tag admission rule for the options reader (Property Options & Staking). Round 6 (base: round 4, reader 1.0.7).

admit(headline, text, categories, out) -> (bool, short_reason)

The reader reads every release. On releases that do not carry the "Property Options & Staking" tag, it often picks up
land deals that are only background, or deals in assets that are not ground, or it gives a real deal the wrong
property. This rule admits a release only when the release is itself about a land deal and the rows name its ground.

Checked in this order (the first refusal wins):
  3. A purchase row that names no property is refused; a sale row with no property is refused when the lead reads as a
     company-level deal (shares of a subsidiary, arrangement, amalgamation).
  4. A row whose "property" is a description or a headline phrase, not a name, is refused ("Seven Namibian ...
     Licenses", "Investment Property", "Debt Settlement Property").
  5. (round 2) A row whose property the body never writes as a capitalised name is refused: the reader built it from
     headline words ("Third Hard-Rock", "Identified High Sulphidation-Porphyry Prospects").
  6. (round 2) In a headline with more than one piece of news (a deal plus results, a resource, an update, a
     financing ...), the row's property must be the deal's: a property named only in the other news, or not named in
     the headline at all, is refused. Not applied when the deal is ground added to a project.
  7. (round 4) Company-level M&A framed in the title: a business combination, merger, amalgamation, arrangement or
     reverse takeover, "creating a ... company / producer", or a title whose acquisition object is a company (the body
     writes it with a corporate suffix, never with a land word). Incoming rows only; a property sale is still read.
  6b. (round 4 refinement) "Update on <a deal>" titles count as other news: a row whose property the title does not
     name is refused.
  1. Admit when the headline announces a land deal (option / earn-in, acquisition or purchase, sale, staking, claims,
     LOI, definitive agreement, landholding expansion ...), after phrases that only look like deals are removed:
     stock options, financing options, option partners, share purchases, private placements, water rights, supply and
     service contracts, streams, royalties, data sets, equipment, strategic alliances, equity stakes, and a geological
     "footprint" (mapped rock or mineralisation, a strike length) as opposed to a land footprint. Round 4 adds: stock
     options issued, shares of another company bought or sold, a payment / option / buy-back whose object is a royalty,
     metal sold forward or pre-paid, and an LOI / term sheet / agreement for money (equity, loan, facility); and
     permitting news (permits, approvals, a record of decision) counts as other news for rule 6.
  2. Or admit when every row is staking and the body says the company staked new ground (not staking told as history,
     "During 2021 the company staked", nor third-party staking).

Round 6 (FIX5 item 6, 2026-10-04)
  Refused (new kinds, from dev9 outside-tag finds):
  R6-1 Product sold, not ground: "Sale of First Copper Cathode", concentrate, dore, bullion, first metal sales.
  R6-2 Records bought, not ground: drilling / trenching data, databases, drill core, reports, archives (words in
       between may now include "and" or dates, but no land word).
  R6-3 Plant or equipment bought or sold: a mill, plant, processing facility, smelter, camp, equipment.
  R6-4 Oil and gas rights or leases bought or sold (not mineral ground).
  R6-5 A geological footprint written "Expand(s) the Footprint of the X Discovery / Zone / System".
  R6-6 A commercial partnership: when the title is about offtake, supply (chain), collaboration, cooperation or a
       partnership, its LOI / term sheet / MOU / agreement is that partnership's paper, not a land deal.
  R6-7 An event notice about a deal (webinar, webcast, conference call, presentation) whose deal words come only
       after the event word: the terms were announced earlier.
  R6-8 Direction conflict (reader misread): a title that only sells ground with incoming rows (purchase, option in,
       staking), a title that only buys with outgoing rows, or an option / purchase on another company's ground
       ("Option on X's Project") with only outgoing rows. Not applied when the title also has option / JV / swap words.
  R6-9 The title names the deal's ground (mixed-case title, a name the body also writes, not a neighbour, place or
       stage word) and no row names it: the reader took a name from the description of the ground (reader misread).
  Admitted (capture, general land-deal wording): "<Property / Land> Expansion", "applied for ... concessions /
  licences / claims", approval or acceptance of an option, modified / amended terms of a named agreement (no
  financing, offtake or service words), a joint venture formed on ground, and a stake in named properties
  ("Increases Stake in X Properties from 40% to 80%", no longer read as an equity stake).

Standard library only, deterministic, no I/O.
"""
import re

_I = re.IGNORECASE

# Headlines that are not headlines: exchange disclaimers, distribution legends, wire boilerplate. For those the rule
# reads the first lines of the body instead (the real title usually follows the legend).
_JUNK_HEADLINE = re.compile(
    r"^\s*(neither\s+(the\s+)?tsx|not\s+for\s+(distribution|dissemination)|or\s+to\s+u\.?s\.?\s+news|for\s+immediate"
    r"|news\s+release\s*$|press\s+release\s*$)", _I)
_LEGEND = re.compile(
    r"neither\s+(the\s+)?tsx[^.]*?(release|news)\.?|not\s+for\s+(distribution|dissemination)[^.]*?(united\s+states|u\.s\.)\.?"
    r"|or\s+for\s+dissemination\s+in\s+the\s+united\s+states\.?", _I)

# Phrases that contain deal words but are not land deals. They are removed from the headline before the deal test,
# so a headline that also announces a real land deal is still admitted.
# Up to n words that are not land words (used between a deal verb and a non-land object).
_NONLAND_WORDS = (r"(?:(?!(?:propert|project|claim|concession|land|licen|tenement|mine\b|mines\b|ground|deposit|"
                  r"package|portfolio|block|option|interest)\w*)[^\s,;:|]+\s+)")

_NOT_LAND = [
    # a geological footprint (mapped rock, mineralisation, an anomaly or a strike length), not a land footprint
    r"\b(\w+ite|mineral\w*|alteration|anomal\w+|zones?|deposit|resource|purity|grade|system|conductor|intrusi\w+)\W+(\w+\W+)"
    r"{0,2}?footprint\b|\bfootprint\W+(\w+\W+){0,2}?[\d,.]+\s*(m|metres?|meters?|km|kilometres?|kilometers?)\b(\W+\w+){0,2}"
    r"|\bfootprint\b[^,;]{0,40}\bstrike\b",
    # a deal whose object is a royalty, a stream, or a data set / database / core library (not ground)
    r"\b(acqui\w+|purchas\w+|buys?|sells?|sale|sold|divest\w*|dispos\w*)\b(\W+(?!propert|project|claim|concession|land|"
    r"licen|tenement|mine\b|ground|and\b|with\b)\w+){0,4}?\W+(royalt(y|ies)|streams?|(historical\s+|historic\s+)?data(\s+sets?)?"
    r"|database|dataset|core\s+(library|archive))\b",
    r"\b(stock|incentive|share)\s+options?\b",                       # equity compensation
    r"\bgrants?\s+(of\s+)?(\d[\d,.]*\s+)?(\w+\s+)?options?\b",           # "grants 500,000 options"
    r"\b\d[\d,.]*\s+options\b|\boptions\s+to\s+(directors|officers|employees|consultants)\b",
    r"\bfinancing\s+options?\b",                                     # "progressing financing options"
    r"\b(option\s+)?partner(s|'s|\u2019s)?\b",                            # a partner's drilling / survey on optioned ground
    r"\boptioned\b(?!\s+(out|to)\b)",                                # "X's optioned Y property" (describes, not reports)
    r"\b(under|held\s+under|during(\s+the)?|previously)\s+(an?\s+)?option\b[^.]{0,40}",  # option as background status
    r"\bshare\s+purchase\s+plan\b|\bnormal\s+course\s+issuer\s+bid\b|\bbuy-?back\b",   # buybacks
    r"\b(shares?|units?|warrants?|notes?|debentures?)\s+purchase\b|\bpurchas\w*\s+(of\s+)?(common\s+)?shares\b",
    r"\bprivate\s+placement\b|\b(bought|brokered)\s+deal\b",         # financings
    r"\bstatement\s+of\s+claim\b|\b(legal|insurance)\s+claims?\b|\bclaims?\s+against\b",  # lawsuits, not mining claims
    r"\b(acqui\w+|purchas\w+|buys?|leases?)\s+(of\s+)?(an?\s+|the\s+)?(\w+\s+){0,2}?(water\s+rights?|permits?)\b",
    # non-mineral rights, and supply or service contracts: water rights, power purchase, offtake, and an LOI or
    # agreement with an adviser, contractor, engineer or toll miller (round 2 added the service contracts)
    r"\bwater\s+rights?\b|\bpower\s+purchase\b|\bofftake\b"
    r"|\b(letter\s+of\s+intent|loi|mou|memorandum\s+of\s+understanding|agreement|term\s+sheet)\b[^,;]{0,60}?\bto\s+(act|serve)"
    r"\s+as\b|\b(technical|engineering|financial|strategic)\s+advis\w+\b|\b(toll[- ]?mill\w*|processing|services?|consulting"
    r"|epc|construction|supply)\s+(agreement|contract|loi|letter\s+of\s+intent|term\s+sheet)\b",
    r"\b(stream(ing|s)?|royalt(y|ies))\s+(\w+\s+){0,3}?(agreement|term\s+sheet|deal|financing|transaction|portfolio|"
    r"package|interests?|sale|purchase|acquisition)\b|\bstream(ing|s)?\b",
    r"\b(acquires?|acquisition\s+of|purchases?|purchase\s+of|sells?|sale\s+of)\s+(an?\s+)?(additional\s+)?"
    r"[\d.]+\s*%\s*(nsr|net\s+smelter|royalt(y|ies)|gor|gross)[^.]{0,40}",  # buying or selling a royalty, not ground
    r"\bpurchas\w*\s+(and\s+\w+\s+)?(drills?|rigs?|equipment|mill|plant|fleet)\b",   # equipment purchases
    r"\b(data|survey|seismic|geophysical|imagery|lidar)\s+acquisition\b",                # survey data acquisition
    r"\b(gold|silver|copper|metal|concentrate|ounces?|oz|record|quarterly|annual|production)\s+sales\b"
    r"|\b(ounces|oz|tonnes|concentrate)\b[^.]{0,20}\bsold\b",      # production sales
    r"\b((letter\s+of\s+intent|loi|agreements?)\s+(for|on)\s+)?(an?\s+)?(strategic\s+|generative\s+)?(exploration\s+)?"
    r"alliance(\s+agreements?)?\b",                                  # generative / strategic alliances (no named ground)
    r"\b(sells?|selling|sale\s+of)\s+(all\s+of\s+)?(the\s+)?(issued\s+and\s+outstanding\s+)?shares\b",  # equity sale
    r"\b((acquires?|acquisition\s+of|buys?|sells?|sale\s+of|takes?)\s+)?(an?\s+)?(equity|strategic|minority|[\d.]+\s*%)"
    r"\s+(equity\s+)?stake\b|\bstake\s+in\b(?!(\s+[^\s,;:]+){0,8}?\s+(propert|project|claim|mine|concession|licen|tenement|deposit))",
    # (round 6: a stake in named ground, "Increases Stake in X Properties from 40% to 80%", is an earn-in, kept)
    r"\b(share|stock)\s+consolidation\b|\bconsolidat\w*\s+(of\s+)?(its\s+|the\s+)?(common\s+)?shares\b",  # share consolidation
    # ---- round 4 ----
    # stock options issued or awarded ("Commences Drilling ... and Issues Options")
    r"\b(issu(e|es|ed|ing|ance\s+of)|award(s|ed|ing)?)\s+(\w+\s+){0,2}?options\b",
    # shares (or other securities) of another company bought or sold: "Sale of X Shares", "Sells its Y Stock".
    # The words in between may not be land words ("Acquires Z Property for Shares" stays a land deal).
    r"\b(sale|sells?|sold|selling|dispos\w+|divest\w*|purchas\w*|acqui\w+|buys?)\s+(of\s+)?((?!propert|project|claim|"
    r"concession|land|licen|tenement|mine\b|ground|for\b|with\b|and\b|in\b|to\b)\w+\s+){0,3}?(shares|stock|securities)\b",
    # a payment, option or agreement whose object is a royalty, or a royalty buy-back ("Final Option Payment for
    # Royalty Buy Back at X Property"): the ground is only where the royalty sits
    r"\b(option(\s+payments?)?|payments?|agreements?)\s+(for|on|to\s+(buy|acquire|purchase|repurchase)(\s+back)?)\s+"
    r"(the\s+|a\s+|an\s+)?(\w+\s+){0,3}?(royalt(y|ies)|nsr|streams?)\b(\s+(buy-?\s?back|re-?purchase))?"
    r"|\broyalt(y|ies)\s+(buy-?\s?back|re-?purchase)\b|\b(buy-?\s?back|re-?purchase)\s+(of\s+)?(\w+\s+){0,3}?royalt\w+",
    # an LOI, term sheet or agreement for money, not ground ("LOI with X for $5 Million in Equity Capital", "Term
    # Sheet for ... Pre-Pay ... Facility"); no acquisition or land word may come in between
    r"\b(letter\s+of\s+intent|loi|term\s+sheet|mou|memorandum\s+of\s+understanding|agreement)\b"
    r"(?:(?!\b(acqui|purchas|option|earn|propert|project|claim|land|licen|concession|tenement|stak|and\b|&)\w*)"
    r"([^,;&]|(?<=\d),(?=\d))){0,80}?"
    r"\b(equity|financing|loan|credit|facility|funding|investment|pre-?\s?pa(y|id)|prepa(y|id))\b",
    # metal sold forward or pre-paid ("Gold Pre-Pay Forward Purchase Facility"): a financing, not ground
    r"\b(pre-?\s?pa(y|id)|prepa(y|id)|forward)\s+(\w+\s+){0,2}?(purchase|sale)(\s+(facility|agreement|arrangement))?\b",
    # ---- round 6 ----
    # product sold: "Sale of First Copper Cathode", "Sells First Gold Dore", "First Concentrate Sale"
    r"\b(sale|sales|sells?|sold|selling)\s+(of\s+)?(its\s+|the\s+)?(first|initial|maiden)?\s*" + _NONLAND_WORDS + r"{0,3}?"
    r"(cathodes?|concentrates?|dor[e\u00e9]|bullion|bars?|ingots?|ounces|oz|pounds|lbs|tonnes|carbonate|hydroxide|"
    r"spodumene|cargo|shipments?|product)\b"
    r"|\b(first|initial|maiden)\s+(\w+\s+){0,2}?(cathode|concentrate|dor[e\u00e9]|bullion|metal|ore|product)\s+sales?\b",
    # records bought, not ground: "Acquires Late 1980s Drilling and Trenching Data for X Project"
    r"\b(acqui\w+|purchas\w+|buys?|bought|obtain\w*|secur\w+)\s+(of\s+)?" + _NONLAND_WORDS + r"{0,8}?"
    r"(data(\s+sets?)?|database|datasets?|drill\s+core|core|reports?|archives?|records|logs|information|samples)\b",
    # plant and equipment bought or sold, not ground: "Agreement to Sell the X Mill"
    r"\b(sale|sells?|sold|sell|selling|acqui\w+|purchas\w+|buys?|bought)\s+(of\s+)?" + _NONLAND_WORDS + r"{0,4}?"
    r"(mill|plant|processing\s+facility|facility|equipment|smelter|refinery|camp|buildings?|warehouse|vessel|barge)\b"
    r"(?!\s+(propert|project|claim|site|mine|tenement|concession|licen)\w*)",
    # oil and gas rights: not mineral ground ("To Sell its 18.75% Petroleum and Natural Gas Rights")
    r"\b(sale|sells?|sold|sell|selling|acqui\w+|purchas\w+|buys?|bought|dispos\w+)\s+(of\s+)?" + _NONLAND_WORDS +
    r"{0,5}?(petroleum|oil|natural\s+gas|gas)\b[^,;]*"
    r"|\b(petroleum|oil)(\s+(and|&)\s+(natural\s+)?gas)?\s+(rights|leases?|wells?|interests?|assets?)\b",
    # a geological footprint written "footprint of the X discovery / zone"
    r"\b(expand\w*\s+(the\s+)?)?footprint\s+of\s+([^\s,;:]+\s+){0,5}?(discover\w*|zones?|deposits?|mineraliz\w+|"
    r"mineralis\w+|system|veins?|trend|anomal\w+|targets?|resources?|orebody|intrusi\w+)\b",
]
_NOT_LAND_RE = [re.compile(p, _I) for p in _NOT_LAND]

# Land-deal language in a headline.
_DEAL = re.compile(
    r"\boptions\b|\boption(s|ed)?\s+(out|to|and)\b"                     # "X Options Y Project", "to option"
    r"|\boption\s+(agreement|payment|deal|acquisition|over|on|interest|to\s+(acquire|purchase|buy|earn))\b"
    r"|\b(exercis\w*|terminat\w*|extend\w*|extension|fulfil\w*|amend\w*|acquires?|grant\w*|closes|completes|signs"
    r"|enters)\b[^.]{0,40}\boption\b"
    r"|\bearn[- ]?in\b|\bearns?\b[^.]{0,25}\d+\s*%"
    r"|\bacqui(re|res|red|ring|sition|sitions)\b|\bpurchas(e|es|ed|ing)\b|\bbuy(s|ing)?\b"
    r"|\b(sell|sells|selling|sale|sold|divest\w*|dispos\w*|vend|vends)\b"
    r"|\bstak(e|es|ed|ing)\b|\bclaims?\b|\blandholdings?\b|\bland\s+(package|position|holdings?)\b|\bfootprint\b"
    r"|\bletter\s+of\s+intent\b|\bLOI\b|\bterm\s+sheet\b"
    r"|\b(definitive|binding|purchase|option|earn-in|assignment)\s+agreement\b|\bassign(s|ment|ed)\b"
    r"|\bconsideration\s+shares\b|\b100\s*%\s+(interest|ownership)\b"
    # round 6: ground added ("X Property Expansion"), a land application ("Applied for Mineral Concessions"), an
    # approval or change of terms of an option or a named agreement, a joint venture formed on ground
    r"|\b(property|land|claims?|ground|tenure|landholdings?|land\s+package)\s+(expansion|addition|increase)\b"
    r"|\bappl(y|ies|ied|ying|ication|ications)\s+(for\s+)?(\w+\s+){0,3}?(concessions?|licen[cs]es?|claims?|tenements?)\b"
    r"|\b(approv\w*|acceptance)\b[^.]{0,40}\boption\b"
    r"|\b(modif\w+|amend\w+|revis\w+|restructur\w+|extend\w*)\s+(the\s+)?(terms\s+(of|to)\s+)?(the\s+|its\s+)?"
    r"((?!loan|credit|facility|financ|offtake|stream|royalt|warrant|debenture|notes?\b|services?|supply|employment|"
    r"consult|placement|offering|convertible|share)[\w'-]+\s+){1,4}?(option\s+|purchase\s+|earn-?in\s+)?agreements?\b"
    r"|\b(form\w*|establish\w*|creat\w*)\s+(of\s+)?(an?\s+|the\s+)?(\w+\s+){0,2}?joint\s+venture\b", _I)

# Company staking its own ground, said in the body. Third-party staking near the company's ground is not a deal.
_STAKED = re.compile(r"\b(staked|staking)\b", _I)
# New ground in that sentence ("staking of two additional claims", "staked six new claims") ...
_NEW_GROUND = re.compile(r"\b(additional|new|newly|recent|recently|expand\w*|add(s|ed|ing)?|doubl\w+|tripl\w+|increas\w+)\b", _I)
# ... and not staking told as history ("During 2021 the company staked", "prospects staked since early 2023").
_OLD_STAKING = re.compile(r"\b(since|during)\s+(early\s+|late\s+|mid-?)?(19|20)\d\d\b|\b(previously|originally|last\s+year)\b", _I)


def _staking_sentences(text):
    """The sentence around each "staked" / "staking" (up to 200 characters before, 120 after)."""
    for m in _STAKED.finditer(text):
        s = text.rfind(".", max(0, m.start() - 200), m.start())
        e = text.find(".", m.end(), m.end() + 120)
        yield text[(s + 1 if s >= 0 else max(0, m.start() - 200)):(e if e >= 0 else m.end() + 120)]


_THIRD_PARTY_STAKING = re.compile(r"\b(third|3rd)[- ]party\b[^.]{0,40}\bstak", _I)

# A company-level transaction in the lead: the release sells or buys a company, not a named property.
_COMPANY_DEAL = re.compile(
    r"\bshare\s+purchase\s+agreements?\b|\b(all|100\s*%)\s+of\s+the\s+(issued\s+and\s+outstanding\s+)?shares\b"
    r"|\bplan\s+of\s+arrangement\b|\bamalgamation\b|\bsubsidiar(y|ies)\b", _I)


# ---- Rule 7 (round 4): company-level M&A. ------------------------------------------------------------------------
# Buying a company is not a land deal even when the company brings properties with it (label guide: company-level M&A
# is no row; a property bought through the company that holds it counts only when the release frames it as buying the
# property). A share purchase or share exchange agreement alone is NOT the cue: juniors buy most properties that way.
# The cue is the framing of the title:
#   a. the title announces a business combination, merger, amalgamation, plan of arrangement or reverse takeover, or
#      says the deal is "creating a ... company / producer";
#   b. the title's acquisition object is a company: the words after "acquisition of" / "acquires" are written in the
#      body with a corporate suffix ("Acquisition of X Minerals" -> "X Minerals Ltda.") and never with a land word.
# Only incoming rows (purchase, option in) are refused; a property sale in the same release is still read.
_CORP_SUFFIX = (r"(ltd|ltda|limited|inc|incorporated|corp|corporation|llc|plc|pty|gmbh|s\.?\s?a|s\.?\s?a\.?\s?s|s\.?\s?l"
                r"|s\.?\s?r\.?\s?l|participa\w+)\b")
_COMBINATION = re.compile(
    r"\bbusiness\s+combination\b|\bmerger\b|\bmerg(e|es|ing)\s+with\b|\bamalgamat\w+\b|\bplan\s+of\s+arrangement\b"
    r"|\breverse\s+take-?\s?over\b|\bcreat\w+\s+(an?\s+|the\s+)?([\w.-]+\s+){0,5}?(company|producer|platform)\b", _I)
_ACQ_OBJECT = re.compile(r"\b(?i:acquisition\s+of|acquires?|to\s+acquire|purchases?|purchase\s+of|buys?)\s+"
                         r"((?:[A-Z][\w\u00c0-\u024f'-]*(?:\s+|(?=[,;:.]|$))){1,3})")
_LAND_NAME = re.compile(r"\b(propert\w+|projects?|claims?|mine|mines|concessions?|licen[cs]es?|tenements?|blocks?|"
                        r"land|ground|deposits?|interest|option|portfolio|assets?|package)\b", _I)


_NOT_OBJECT = {"agreement", "agreements", "letter", "loi", "term", "definitive", "binding", "remaining", "additional",
               "new", "strategic", "majority", "minority", "controlling", "option", "options", "up", "all", "100%"}


def _company_object(title, text):
    for m in _ACQ_OBJECT.finditer(title):
        words = m.group(1).split()
        # "to Acquire X Gold's Y Property": X Gold is the vendor, not the object
        if re.match(r"[\w-]*['\u2019]s\b", title[m.end():]) or (words and words[0].lower() in _NOT_OBJECT):
            continue
        while words and (_LAND_NAME.match(words[-1]) or words[-1].lower() in ("the", "a", "an", "its", "in", "of")):
            words = words[:-1]
        if not words or any(_LAND_NAME.match(w) for w in words) or words[0].lower() in ("the", "a", "an", "its"):
            continue
        name = _flex(" ".join(words))
        if (re.search(name + r"[\W_]+([\w\u00c0-\u024f]+[\W_]+){0,2}?" + _CORP_SUFFIX, text, _I)
                and not re.search(name + r"\W+(\w+\W+){0,2}?" + _LAND_NAME.pattern, text, _I)):
            return " ".join(words)
    return None


# Words that describe ground rather than name it. A property made only of these (plus generic words such as
# Property / Gold / Claims) is a description the reader lifted from the headline.
_GENERIC = {"the", "a", "an", "of", "and", "de", "del", "la", "project", "projects", "property", "properties", "claims",
            "claim", "block", "blocks", "area", "mine", "mines", "deposit", "deposits", "gold", "silver", "copper",
            "lithium", "uranium", "nickel", "zinc", "lead", "cobalt", "tungsten", "antimony", "rare", "earth", "earths",
            "tenements", "tenement", "licence", "licences", "license", "licenses", "concession", "concessions",
            "package", "packages", "portfolio", "assets", "ground", "land", "mineral", "minerals", "metals", "critical",
            "polymetallic", "prospecting", "exploration", "mining", "porphyry", "vms", "pgm", "base"}
_DESCRIPTIVE = {"new", "additional", "strategic", "significant", "prospective", "key", "flagship", "major", "large",
                "high", "impact", "grade", "investment", "adjacent", "contiguous", "nearby", "surrounding", "expand",
                "expanded", "extend", "vendor", "vendors", "disputed", "optioned", "acquired", "target", "targets",
                "district", "scale", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "several",
                "multiple", "various", "certain", "undisclosed", "unnamed"}


# Corporate-finance words never belong to a property name: "Debt Settlement Property" is the reader running a
# financing clause of the headline into the deal.
_FINANCE_WORDS = {"debt", "settlement", "placement", "placements", "financing", "offering", "shares", "warrants",
                  "loan", "debenture", "debentures", "update"}


def _descriptive(prop):
    words = [w for w in re.findall(r"[a-z0-9]+", prop.lower()) if w not in _GENERIC]
    if any(w in _FINANCE_WORDS for w in words):
        return True
    if not words:
        return False
    # every remaining word is descriptive, a number, or a nationality / regional adjective ("Namibian", "Mexican")
    # (a lone "-ian" word such as "Caledonian" can be a real name, so at least one clearly descriptive word is needed)
    if not any(w in _DESCRIPTIVE or w.isdigit() for w in words):
        return False
    return all(w in _DESCRIPTIVE or w.isdigit() or re.fullmatch(r"[a-z]+(ian|ean|ese|ish)", w) for w in words)


# ---- Rule 5: the property must be a name the body uses. -----------------------------------------------------------
# The reader sometimes builds the property from headline words ("Third Hard-Rock", "Identified High Sulphidation-
# Porphyry Prospects", "Grid Metals Donner Lake"). A real property name is also written, capitalised, in the
# body (outside the copy of the headline that opens most bodies). Before the test, generic words (Property, Project,
# Claims ...), commodity and deposit-type words (Gold, Cu-Au, VMS, Porphyry ...) and a leading headline verb
# ("Extend", "Buy", "Out") are stripped, so "Buy Tonopah West" is tested as "Tonopah West".
_STRIP = re.compile(
    r"^(the|property|properties|project|projects|claims?|mine|mines|deposits?|concessions?|licen[cs]es?|tenements?|blocks?|"
    r"prospects?|area|package|prospecting|exploration|mining|mineral|minerals|district|camp|trend|complex|"
    r"gold|silver|copper|nickel|zinc|lead|cobalt|lithium|uranium|tin|tungsten|antimony|manganese|graphite|fluorspar|"
    r"titanium|vanadium|molybdenum|platinum|palladium|pgm|pge|ree|rare|earths?|base|metals?|battery|critical|polymetallic|"
    r"au|ag|cu|ni|zn|pb|co|li|mo|sb|w|vms|porphyry|epithermal|skarn|sedex|iocg|intrusion|"
    r"[a-z]+(-[a-z]+)+)$", _I)          # hyphenated commodity pairs: Gold-Silver, Cu-Au, Gold-Copper-Silver
_LEAD_VERB = re.compile(r"^(extend\w*|expand\w*|buy\w*|acquir\w*|option\w*|out|sell\w*|optimi[sz]\w*|identified|"
                        r"announces?|adds?|consolidat\w*|increas\w*|secures?)$", _I)


def _cores(prop):
    """The name parts of a property: split on / , ; and &, generic and commodity words stripped."""
    out = []
    for part in re.split(r"\s*(?:/|,|;|&|\band\b)\s*", prop, flags=re.I):
        w = part.split()
        while w and _LEAD_VERB.match(w[0]):
            w = w[1:]
        while w and _STRIP.match(w[-1]):
            w = w[:-1]
        while w and re.fullmatch(r"the|property|project|claims?", w[0], _I):
            w = w[1:]
        if w:
            out.append(" ".join(w))
    return out


def _flex(s):
    """A pattern for s that ignores spacing and punctuation (bodies from PDFs break words: "Arg entina")."""
    return r"[\W_]*".join(re.escape(c) for c in s if c.isalnum())


def _headline_spans(text, headline):
    """Where the body repeats the headline (most bodies open with it)."""
    if sum(c.isalnum() for c in headline) <= 20:
        return []
    return [m.span() for m in re.finditer(_flex(headline), text, _I)]


def _named_in_body(core, text, heads):
    if not any(c.isalnum() for c in core):
        return True
    for m in re.finditer(_flex(core), text, _I):
        if any(a <= m.start() < b for a, b in heads):
            continue
        if text[m.start()].isupper() or text[m.start()].isdigit():
            return True
    return False


# ---- Rule 6: in a headline with more than one piece of news, the row's ground must be the deal's ground. ----------
# "Files Resource Estimate for X Project, Completes Acquisition of Claims", "Update on X Project and Detail on Y
# Property Purchase", "Completes Exploration Program and Acquisition of Concessions": the reader often gives the deal
# the property of the other news. The headline is cut into clauses; a clause with deal language is a deal clause, a
# clause with news of another kind (results, drilling, resource, update, financing, study ...) is an other-news clause.
#   a. A row whose property is named in an other-news clause is refused.
#   b. When the headline has an other-news clause, a row whose property is not named in the headline at all is refused
#      (the deal clause names no ground, or names other ground, so the row cannot be tied to the deal).
# Not applied when the deal is ground added to a project ("Increases Holdings and Plans Drill Program at X Project",
# "Expands Footprint ... & Provides Update"): there the project named in the other clause is the deal's ground.
_GROWS = re.compile(r"\b(expan\w*|increas\w*|doubl\w*|tripl\w*|enlarg\w*|consolidat\w*|grows|adds|addition\w*)\b", _I)
_CLAUSE_SPLIT = re.compile(r"\s*(?:,|;|:|\||\s[-\u2013\u2014]\s|\band\b|&|\bplus\b)\s*", _I)
_OTHER_NEWS = re.compile(
    r"\b(results?|assays?|intercepts?|intersects?|drill\w*|resources?|reserves?|estimate|ni\s*43-101|pea|pfs|"
    r"feasibility|study|update[sd]?|program(me)?s?|survey\w*|sampl\w+|mapping|mineraliz\w+|mineralis\w+|"
    r"zones?|grades?|g/t|gpt|production|financ\w+|placements?|offering|warrants|debt|q[1-4]|quarter\w*|"
    r"optimi[sz]\w*|provides|reports|files|identifies|discovers|commences|begins|starts|appoints|"
    r"permits?|permitting|approvals?|record\s+of\s+decision)\b", _I)    # round 4: permitting news


def _in(core, clause):
    return any(c.isalnum() for c in core) and re.search(_flex(core), clause, _I) is not None


def _title(headline, text):
    """The headline, or the first lines of the body when the headline is a legend."""
    h = headline or ""
    if _JUNK_HEADLINE.search(h) or len(re.findall(r"[A-Za-z]{3,}", h)) < 3:
        lead = _LEGEND.sub(" ", (text or "")[:700])
        return lead[:350]
    return h


# Ground added to a property: "Expands X Property", "Doubles its Landholdings", "Consolidation of the Y District".
# The land word must come within a few words of the verb, with no resource / drilling / share word in between
# ("Increases Mineral Resource at X Project" and "Share Consolidation" are not land deals).
_EXPAND = re.compile(r"\b(expand\w*|increas\w*|doubles|triples|enlarg\w*|consolidat\w*|grows|adds)\b((?:\W+\w+){0,7})", _I)
_LAND_WORD = re.compile(r"^(property|properties|project|land\w*|ground|claims?|holdings?|district|footprint|tenure|"
                        r"hectares|acres|km|kilometres?|kilometers?|concessions?|tenements?|licen[cs]es?)$", _I)
_NOT_LAND_WORD = re.compile(r"^(resources?|reserves?|drill\w*|program\w*|zones?|strike|mineraliz\w*|mineralis\w*|"
                            r"exploration|plant|mill|capacity|production|targets?|system|shares?|common|budget|"
                            r"financing|offering|placement|size|stake|ownership|interest)$", _I)


def _expansion(h):
    for m in _EXPAND.finditer(h):
        for w in re.findall(r"[\w-]+", m.group(2)):
            if _NOT_LAND_WORD.match(w) or w.lower() in ("at", "to"):   # "Expands X at Y Project": X is what grew
                break
            if _LAND_WORD.match(w):
                return m.group(0)
    return None


# Round 6: a title about a commercial partnership (offtake, supply chain, collaboration, cooperation) uses LOI / term
# sheet / MOU / agreement for that partnership, not for ground ("Sign LOI and Offtake Term Sheet to Strengthen ...
# Supply Chain").
_COMMERCIAL = re.compile(r"\bofftake\b|\bsupply(\s+chain)?\b|\bcollaborat\w+|\bco-?operation\b|\bpartnership\b"
                         r"|\b(joint\s+)?(development|marketing|research|technology)\s+agreement\b", _I)
_PAPER = re.compile(r"\b(letter\s+of\s+intent|loi|mou|memorandum\s+of\s+understanding|term\s+sheets?|"
                    r"(definitive|binding)\s+agreements?|agreements?)\b", _I)


def _deal_words(h):
    commercial = _COMMERCIAL.search(h)
    for rx in _NOT_LAND_RE:
        h = rx.sub(" ", h)
    if commercial:
        h = _PAPER.sub(" ", h)
    m = _DEAL.search(h)
    return m.group(0) if m else _expansion(h)


# ---- Round 6 (FIX5 item 6) ------------------------------------------------------------------------------------------
# R6a. An event notice about a deal (webinar, conference call, presentation): the deal was announced earlier and the
#      notice adds no terms. Refused when the deal words come only after the event word.
_EVENT = re.compile(r"\b(webinars?|webcasts?|conference\s+calls?|live\s*streams?|(investor|virtual|corporate)\s+presentations?"
                    r"|town\s+halls?|fireside\s+chats?|ama\b|ask\s+me\s+anything|to\s+present\s+at|investor\s+day)\b", _I)
# R6b. The rows go the other way from the title: a title that only sells ground ("Completes Sale of X") with rows that
#      buy, option in or stake, or a title that only buys with rows that sell. The reader read another deal (or the
#      buyer's side).
_SALE_SIDE = re.compile(r"\b(sell|sells|selling|sale|sold|divest\w*|dispos\w*|vends?)\b", _I)
_BUY_SIDE = re.compile(r"\b(acqui\w+|purchas\w+|buys?|buying|bought|earn[- ]?in|earns?|stak(e|es|ed|ing))\b", _I)
_ANY_OPTION = re.compile(r"\boption\w*\b|\bjoint\s+venture\b|\bjv\b|\bswap\b|\bexchange\b", _I)
# An option or purchase on another company's ground ("Completes the Option on X's Gold Project") is incoming.
_OTHERS_GROUND = re.compile(r"\b(?i:option\w*|earn[- ]?in|acqui\w+|purchas\w+|interest)\b[^,;:|]{0,25}?\b(?i:on|in|of|from|over)"
                            r"\s+(?:[A-Z][\w.&-]*\s+){0,3}?[A-Z][\w.&-]*['\u2019]s\s+([^\s,;:|]+\s+){0,4}?"
                            r"(?i:propert\w*|projects?|claims?|mine|concessions?|licen[cs]es?|tenements?|ground)\b")
_INCOMING = ("property_purchase", "claim_purchase", "option_in", "staking")
_OUTGOING = ("property_sale", "option_out")
# R6c. The title names the deal's ground ("X Project Acquisition", "Options the Y Property") and the row names other
#      ground: the reader took a name from the description of the ground or its neighbours.
_TITLE_GROUND = re.compile(r"((?:[A-Z][\w\u00c0-\u024f'\u2019.-]*\s+){1,4})(Projects?|Property|Properties|Claims?|Mine|"
                           r"Concessions?|Licen[cs]es?|Tenements?|Blocks?|Prospects?)\b")


# Jurisdictions describe where ground is, they do not name it ("Sell Saskatchewan Mineral Claims").
_PLACE = {"canada", "canadian", "british", "columbia", "bc", "alberta", "saskatchewan", "manitoba", "ontario", "quebec",
          "qu\u00e9bec", "new", "brunswick", "nova", "scotia", "newfoundland", "labrador", "yukon", "nunavut", "northwest",
          "territories", "nwt", "nevada", "arizona", "idaho", "montana", "utah", "alaska", "wyoming", "colorado", "oregon",
          "california", "washington", "mexico", "mexican", "usa", "us", "u", "s", "united", "states", "america",
          "american", "peru", "peruvian", "chile", "chilean", "argentina", "argentine", "argentinian", "brazil",
          "brazilian", "ecuador", "colombia", "colombian", "bolivia", "guyana", "australia", "australian", "western",
          "northern", "southern", "eastern", "north", "south", "east", "west", "queensland", "nsw", "victoria", "finland",
          "finnish", "sweden", "swedish", "norway", "norwegian", "ireland", "irish", "spain", "spanish", "portugal",
          "ghana", "mali", "namibia", "tanzania", "kenya", "africa", "african", "province", "provincial", "state",
          "county", "region", "regional", "territory"}


# Stage and kind of ground, not a name ("Producing Mines and Development Projects").
_STAGE_WORDS = {"producing", "production", "development", "advanced", "past", "historic", "historical", "former",
                "brownfield", "greenfield", "early", "stage", "satellite", "near", "exploration", "royalty", "mining",
                "mineral", "gold", "silver", "copper", "lithium", "uranium", "nickel", "graphite", "silica", "quartz",
                "portfolio", "of", "and", "in", "its", "their"}


def _cleaned(title):
    for rx in _NOT_LAND_RE:
        title = rx.sub(" ", title)
    return title


_CUT_WORD = re.compile(r"(the|its|a|an|and|of|on|for|to|at|in|with|from|by|into|over|completes?|closes?|signs?|"
                       r"enters?|executes?|announces?|terminates?|exercises?|agreement|option|options|acquisition|sale|"
                       r"purchase|stakes?|staking|acquires?|purchases?|sells?|buys?|reports?|provides?|update|"
                       r"corp\.?|inc\.?|ltd\.?|limited)$", _I)
_NEIGHBOUR = re.compile(r"\b(contiguous|adjacent|adjoining|next|near|nearby|close|surrounding|bordering|neighbou?r\w*|"
                        r"along\s+strike|east|west|north|south)\s+(to\s+|of\s+)?(the\s+|its\s+)?$", _I)


def _title_grounds(title, text, heads):
    """Names of ground the title gives (mixed-case titles only) that the body also writes as a name. Words before the
    last verb or connector are cut ("X Corp Acquires Y Project" -> "Y"); ground named as a neighbour ("Claims
    Contiguous to the Z Property") is not the deal's ground."""
    letters = [c for c in title if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) > 0.6 * len(letters):
        return []
    names = []
    for m in _TITLE_GROUND.finditer(title):
        if _NEIGHBOUR.search(title[max(0, m.start() - 30):m.start()]):
            continue
        words = m.group(1).split()
        cut = [k for k, w in enumerate(words) if _CUT_WORD.match(w) or _LEAD_VERB.match(w)]
        if cut:
            words = words[cut[-1] + 1:]
        while words and _STRIP.match(words[-1]):
            words = words[:-1]
        name = " ".join(words)
        if not name or re.search(r"['\u2019]s$", name):
            continue
        rest = [w for w in re.findall(r"[a-z0-9\u00c0-\u024f]+", name.lower())
                if w not in _GENERIC and w not in _DESCRIPTIVE and w not in _PLACE and w not in _STAGE_WORDS]
        if rest and len(text) >= 600 and all(_named_in_body(k, text, heads) for k in _cores(name)):
            names.append(name)
    return names


def admit(headline, text, categories, out):
    rows = [r for r in ((out or {}).get("rows") or []) if r and r.get("deal_type")]
    if not rows:
        return False, "no rows"
    text = text or ""

    # Rule 3: rows without a property. Only property sales are reliable there, and never a company-level deal.
    noprop = [r for r in rows if not (r.get("property") or "").strip()]
    if any(r["deal_type"] in ("property_purchase", "claim_purchase") for r in noprop):
        return False, "purchase with unnamed property"
    if any(r["deal_type"] == "property_sale" for r in noprop) and _COMPANY_DEAL.search(text[:2500]):
        return False, "unnamed property, company-level deal"

    # Rule 4: a property that is a description, not a name ("Seven Namibian Uranium Prospecting Licenses",
    # "Investment Property", "Expand Claim"). The reader took a phrase from the headline; the row is not the deal.
    for r in rows:
        if r.get("property") and _descriptive(r["property"]):
            return False, "property is a description"

    title = _title(headline, text)

    # Rule 7: the title frames a company bought, merged or combined; its properties are not the release's land deal.
    if all(r["deal_type"] in ("property_purchase", "claim_purchase", "option_in") for r in rows):
        if _COMBINATION.search(title):
            return False, "company-level: combination"
        if _company_object(title, text[:3000]):
            return False, "company-level: a company bought"

    # Rule 5: every property is a name the body itself uses (skipped when the stored body is a stub).
    if len(text) >= 600:
        heads = _headline_spans(text, headline or "")
        for r in rows:
            for core in _cores(r.get("property") or ""):
                if not _named_in_body(core, text, heads):
                    return False, "property not named in body"

    # Rule 6: a multi-news headline; the row's ground must be the deal's ground.
    clauses = [c for c in _CLAUSE_SPLIT.split(title) if c and c.strip()]
    deal_cl = [c for c in clauses if _deal_words(c)]
    other_cl = [c for c in clauses if not _deal_words(c) and _OTHER_NEWS.search(c)]
    if deal_cl and other_cl and not any(_GROWS.search(c) for c in deal_cl):
        for r in rows:
            cores = _cores(r.get("property") or "")
            if not cores:
                continue
            if any(_in(k, c) for k in cores for c in other_cl) and not any(_in(k, c) for k in cores for c in deal_cl):
                return False, "property belongs to other news"
            if not any(_in(k, title) for k in cores):
                return False, "multi-news headline, ground not named"

    # Rule 6b, round 4 refinement: an update on a deal ("Provides Update on Proposed Acquisition of ... Land Package")
    # counts as other news even though the update and the deal share one clause. The terms were in an earlier release
    # and the body mostly describes the ground and its neighbours, so a row whose property the title does not name is
    # the reader picking a name from that description.
    upd = re.search(r"\bupdates?\s+(on|regarding|about|to)\b([^,;:|&]*)", title, _I)
    if upd and _deal_words(upd.group(2)):
        for r in rows:
            cores = _cores(r.get("property") or "")
            if cores and not any(_in(k, title) for k in cores):
                return False, "deal update, ground not named"

    # Round 6 checks (R6a-c).
    ev = _EVENT.search(title)
    if ev and not _deal_words(title[:ev.start()]):
        return False, "event notice about a deal"
    clean = _cleaned(title)
    sale, buy = _SALE_SIDE.search(clean), _BUY_SIDE.search(clean)
    if not _ANY_OPTION.search(clean):
        if sale and not buy and any(r["deal_type"] in _INCOMING for r in rows):
            return False, "title sells, row buys"
        if buy and not sale and any(r["deal_type"] in _OUTGOING for r in rows):
            return False, "title buys, row sells"
    if (_OTHERS_GROUND.search(title) and not _SALE_SIDE.search(clean)
            and all(r["deal_type"] in _OUTGOING for r in rows)):
        return False, "title takes another's ground, row gives"
    named = [r for r in rows if _cores(r.get("property") or "")]
    if named and _title_grounds(title, text, _headline_spans(text, headline or "")):
        if not any(_in(k, title) for r in named for k in _cores(r["property"])):
            return False, "title names other ground"

    # Rule 1: the headline announces a land deal.
    m = _deal_words(title)
    if m:
        return True, "headline deal: " + m[:25].lower()

    # Rule 2: staking announced inside an exploration / sampling release.
    if (all(r["deal_type"] == "staking" for r in rows) and not _THIRD_PARTY_STAKING.search(text)
            and any(_NEW_GROUND.search(s) and not _OLD_STAKING.search(s) for s in _staking_sentences(text))):
        return True, "staking in body"

    return False, "no deal in headline"
