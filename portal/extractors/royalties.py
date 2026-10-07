"""Royalties & Streams reader, facts-store version (ROY_V1, 2026-09-21).

The source of the Royalties & Streams page once it passes the accuracy gate. Written against the
50-release set Justin confirmed on 2026-09-21 (22 releases with rows, 25 rows).

The row shape and the rules are Justin's (2026-09-21):

  1. ONE ROW PER ROYALTY OR STREAM INTEREST a release reports as news: type (NSR, GRR, NPI, stream, other),
     rate, metal, property, operator, buyer, seller, price and currency, action and status.
  2. THE EVENTS THAT ARE ROWS: an interest bought, sold or granted (stream and royalty financings included),
     a buyback or buy-down, an amendment. Royalty income, royalty payments and disputes are not rows.
  3. OUT OF SCOPE: oil and gas royalties, non-mining royalties (music), and a royalty mentioned in passing --
     an About section, the NSR a buyer grants the vendor in a property deal, a recap in quarterly results.
  4. PRECISION FIRST. The release has to be ABOUT the deal: the headline names it, or the headline names a
     financing / spin-out and the opening sentences say it is a stream or royalty.

Direction (who is buyer and who is seller) comes from the verb in the deal sentence:
  acquire / purchase / reacquire ... from X   -> the subject buys, X sells
  sale of / sell / grant ... to X             -> the subject sells, X buys
  "with X, pursuant to which X will acquire"  -> X buys
  a stream financing "with X"                 -> the royalty company buys, X sells
Action: amendment when the release amends or extends an agreement; buyback when the buyer operates the
property; new when the seller operates it (a grant or a stream financing); otherwise transfer.

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per row (ordinal 0..n-1)
to_prediction(records) -> dict|None    what the accuracy judge compares

1.0.1 (2026-09-27): onto the shared project-name helper portal/project_names.py, conservatively. 1.0.0's property
(_property on the deal sentence, the headline, the next sentences) stays first. The helper only
  - fills a blank on a one-row release: with a name the helper finds in the headline and the headline ties to the
    interest ("... Royalty on SolGold's Cascabel Project", "Fosterville Mine Royalty", "... Stream from Vale's
    Voisey's Bay Mine"), or else with a helper project the opening text ties to it ("... net smelter return royalty on
    the Pebble Project"); never on a portfolio release, never a party (buyer, seller, operator, issuer), a neighbour
    ("adjoining", "in exchange for"), a list, a mill, a nationality, a lone landform, a number or a description;
  - respells: "Clarence Strm" -> "Clarence Stream" (1.0.0 hides "Stream" in place names and never put it back),
    "Platreef's" -> "Platreef" (when the text writes the name before Project/Mine...), "Historic Haukiaho" ->
    "Haukiaho", "Montcalm Ni Cu Co" -> "Montcalm", a lone "Bay" -> the tied helper name ending in it ("Voisey's Bay");
  - replaces a name that is no property ("Company's", "Westhaven's", "Their Critical Rare Earth", "Orion Resource
    Partners") with a tied helper name, or leaves it blank.
  Names in this page's form: no trailing Project/Mine/Property..., metal words or element symbols. The fingerprint
  also covers the helper.

1.1.1 (2026-10-04, FIX5): six changes, each measured alone against 1.1.0 on the ACC150c dev half (notes in
NOTES_FIX5.md):
  - the other side of a property deal: 'to/from/with X' with one space (1.1.0 needed two), 'to' only in the opening
    text, a body name after 'from/with' only with its suffix or a defined name, a headline name cut before a verb;
  - who holds a vendor royalty: '... NSR to the vendors', 'will be granted to X', 'X was granted', 'grant X the
    right to receive', 'grant to X, a ...';
  - the vendor royalty's property: the name after the deal verb, never a demonstrative, descriptor or nationality;
  - held royalties: the headline read unmasked, '<Holder>'s <Name> Royalty Property', the Company's defined name,
    "the Company's 2% NSR", and the company whose property it is (operator);
  - the issuer keeps the royalty when it sells or options the property out and names no holder; the party that earns
    into the property is the counterparty;
  - rates in brackets ('one percent (1%)') and after the interest ('an NSR of 0.5%').

Self-tests: python3 -m portal.extractors.royalties
"""
from __future__ import annotations

import re
import unicodedata

from portal import facts as F
from portal import project_names as PN   # 1.0.1: the shared project-name helper
from portal import fingerprint as FP     # 1.0.2: fingerprints follow exactly the helper code this reader runs

NAME = "royalties"
VERSION = "1.1.1"  # 2026-09-28: vendor and held royalties, results closings, prices, metal (Justin's ROY11 answers);
#                   2026-10-04 FIX5: vendor-royalty parties and properties, held-royalty headlines and
#                   operators, bracketed and trailing rates
KIND = "royalty_row"
TAG = "Royalties & Streams"
TEXT_CAP = 40000

TXT_FIELDS = ("type", "metal", "property", "operator", "buyer", "seller", "currency", "action", "status",
              "price_note", "kind")
NUM_FIELDS = ("rate_pct", "price")

Q = "\"\u201c\u201d'\u2018\u2019"          # quote characters PDFs and wires use around defined terms
_SUFFIX = r"(?:Inc|Corp|Corporation|Ltd|Limited|Plc|plc|PLC|LLC|L\.L\.C|LP|L\.P|Co|Company|S\.A\.(?:\s+de\s+C\.V)?|SA|AG|AB|NL)"
_CAPW = r"(?:[A-Z][\w&'\u2019.\-]*|[A-Z]{2,}|of|de|del|and|&)"
_ORG = re.compile(r"\b((?:[A-Z][\w&'\u2019\-]*\.?\s+)(?:(?:" + _CAPW + r")\s+){0,5}?" + _SUFFIX + r")\.?(?=[\s,;:)(\u201d\"]|$)")
_METALS = ("gold", "silver", "copper", "platinum", "palladium", "nickel", "zinc", "lead", "cobalt", "tin", "tungsten",
           "graphite", "lithium", "uranium", "vanadium", "fluorspar", "iron ore", "molybdenum", "antimony", "rhodium",
           "tantalum", "manganese", "potash", "diamonds")

# ------------------------------------------------------------------ text preparation
_FLS = re.compile(r"(?i)\b(?:cautionary\s+(?:note|statement)s?\s+(?:regarding|on|concerning)|forward[\s\-]+looking\s+"
                  r"(?:statements?|information)\s*(?:and|&)?\s*(?:cautionary)?[^.]{0,40}?(?:\n|:|This\s+(?:news\s+)?release)"
                  r"|neither\s+(?:the\s+)?tsx|qualified\s+person)")


_NOT_PLACE = ("Silver", "Gold", "Copper", "Precious", "Metals", "Metal", "Mine", "Life", "Royalty", "Platinum", "Palladium",
              "Cobalt", "Nickel", "Zinc", "Graphite", "Uranium", "Lithium", "Tin", "Tungsten", "Definitive", "New", "Its",
              "The", "A", "Additional", "Second", "Third", "First", "Mineral", "Minerals", "Polymetallic", "Revenue")


def _places(t):
    """'Clarence Stream North Gold Project' is a place, not a stream."""
    return re.sub(r"\b([A-Z][a-z]+)\s+Stream\b(?!\s+(?:Agreement|Financing|Transaction|Interest|Deal))",
                  lambda m: m.group(0) if m.group(1) in _NOT_PLACE else m.group(1) + " Strm", t)


def _prepare(headline, body):
    b = (body or "")[:TEXT_CAP]
    m = _FLS.search(b, 400)
    if m:
        b = b[:m.start()]
    b = unicodedata.normalize("NFKC", b).replace(chr(160), " ")
    b = re.sub(r"\s+", " ", b)
    h = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", headline or ""))
    return _places(h.strip()), _places(b.strip())


def _title(h):
    """The headline without the lead some feeds append to it ('... Mine Franco-Nevada Corporation ("Franco-Nevada"
    or the "Company") is pleased to announce ...')."""
    t = h
    # the lead starts with the company's name, which it then defines: '... Mine Franco-Nevada Corporation
    # ("Franco-Nevada" or the "Company")' -- cut at the last place the defined name starts before that
    a = re.search(r"\(\s*[" + Q + r"]\s*([^" + Q + r"]{3,40}?)\s*[" + Q + r"]\s*(?:,|or)\s*(?:the\s+)?[" + Q + r"]\s*Company", h)
    if a and re.search(r"[a-z]", a.group(1)):
        w = re.escape(a.group(1).split()[0])
        starts = [m.start() for m in re.finditer(r"(?<![\w-])" + w, h[:a.start()])]
        if starts and starts[-1] > 10:
            t = h[:starts[-1]]
    if t == h:
        m = re.search(r"\s(?=(?:[A-Z][\w&'\u2019.\-]*\s+){0,5}" + _SUFFIX + r"\.?\s*[,(])", h[10:])
        t = h[:10 + m.start()] if m else h
    m = re.search(r"\s(?:is\s+pleased\s+to|announces?\s+that|\(\s*[" + Q + r"]|\((?:TSX|CSE|NYSE|NASDAQ))", t)
    return (t[:m.start()] if m else t).strip()


def _drop_title(b, title):
    """The headline is usually repeated at the top of the body, run into the dateline and the lead sentence."""
    if len(title) < 12:
        return b
    words = re.findall(r"\S+", title)
    rx = r"\s*".join(re.escape(w) for w in words)
    m = re.search(rx, b[:3000], flags=re.I)
    if not m:
        return b
    return b[:m.start()] + " . " + b[m.end():]


def _sentences(text):
    parts = re.split(r"(?<=[.;!?])\s+(?=[A-Z\u201c\"\u2022\u25aa])|\s+[\u2022\u25aa]\s+", text)
    out = []
    for p in parts:
        p = p.strip()
        # a run of capitals (a headline or banner repeated in the body) is not a sentence to read
        p = re.sub(r"^(?:[^a-z]{0,40}?\b)?(?:[A-Z0-9&%$.,'\u2019\-]+\s+){4,}(?=[A-Z][a-z])", "", p)
        p = re.sub(r"(?:\b[A-Z0-9&%$.,'\u2019\-]{2,}\s+){5,}", " ", p).strip()
        if p:
            out.append(p)
    return out


# ------------------------------------------------------------------ names
def _clean_org(s):
    s = re.sub(r"\s+", " ", s or "").strip(" ,;:.")
    s = re.sub(r"^(?:the|a|an|and|with|to|from|by|of)\s+", "", s, flags=re.I)
    s = re.sub(r"\s*,?\s*\b" + _SUFFIX + r"\.?$", "", s).strip(" ,")
    s = re.sub(r"['\u2019]s$", "", s)
    w = s.split()
    k = 0
    while k < len(w) and re.fullmatch(r"[A-Z0-9&\-]{2,}", w[k]):
        k += 1
    if k >= 2 and k < len(w):
        w = w[k:]
    # a dateline or banner in capitals after the name: 'Sprott Streaming KELLOGG'
    while len(w) > 1 and re.fullmatch(r"[A-Z]{4,},?", w[-1]) and any(re.search(r"[a-z]", x) for x in w[:-1]):
        w = w[:-1]
    s = " ".join(w)
    s = re.sub(r"['\u2019]$", "", s)
    s = re.sub(r"\s+(?:The|A|An)$", "", s)
    s = re.sub(r"^(?:Company|Corporation)\s+and\s+", "", s)
    return s or None


_BAD_PARTY = re.compile(r"(?i)^(?:newsfile|(?:canada|ontario|quebec|nevada|british\s+columbia|mexico|australia)\b(?!\s+[A-Z]\w+)|under|(?-i:or|Or|and|And)|"
                        r"the\s+company|shareholders?|management|board|tsx|cse|nyse|asx)\b|newsfile|information\s+circular|"
                        r"globe\s*newswire|pr\s*newswire|\b(?:mine|project|property|complex|deposit|claims)$|^.{0,2}$|"
                        r"\.\s+[A-Z]")


def _ok_party(n):
    return n if n and not _BAD_PARTY.search(n) else None


def _definitions(text):
    """Defined terms: 'Wheaton Precious Metals Corp. ("Wheaton")' -> {'wheaton': 'Wheaton Precious Metals'};
    'the Fruta del Norte ("FDN") gold mine' -> {'fdn': 'Fruta del Norte'}; the Company -> the issuer."""
    out, orgs = {}, set()
    for m in re.finditer(r"((?:(?:[A-Z][\w&'\u2019.\-]*|&|and)\s+){0,7}?(?:[A-Z][\w&'\u2019.\-]*|" + _SUFFIX + r"\.?))\s*,?\s*"
                         r"(?:\([^()]{0,80}\)\s*){0,4}\(\s*(?:collectively,?\s*)?(?:the\s+)?[" + Q + r"]\s*([^" + Q + r"]{1,40}?)\s*[" + Q + r"]",
                         text):
        name, alias = m.group(1).strip(), m.group(2).strip()
        name = re.sub(r"^(?:The|A|An|And|With|To|From|By|Of|On|In|At)\s+", "", name)
        if alias.lower() in ("company", "corporation", "transaction", "agreement", "royalty", "stream", "nsr",
                             "project", "property", "arrangement", "offering", "acquisition", "optionee"):
            if alias.lower() in ("optionee",):
                out["optionee"] = _clean_org(name)
            continue
        if alias in name and not name.startswith(alias) and re.search(r"[a-z]", alias):
            name = name[name.index(alias):]          # 'Ontario Franco-Nevada Corporation ("Franco-Nevada")'
        if len(alias) <= 40 and name and alias.lower() not in out:
            out[alias.lower()] = _clean_org(name)
            if re.search(r"\b" + _SUFFIX + r"\.?$", name.strip(" ,")) and \
                    (_clean_org(name) or "").lower() not in ("royalty", "royalties", "stream", "streaming", "and", "&"):
                orgs.add(_clean_org(name))
                orgs.add(alias)
    return out, orgs


def _issuer(headline, body):
    """The company that issued the release: the name defined as the 'Company', or the headline's opening words."""
    for m in re.finditer(r"\(\s*(?:[" + Q + r"]\s*[^" + Q + r"]{1,40}\s*[" + Q + r"]\s*(?:,|or)\s*)*(?:the\s+)?[" + Q + r"]\s*"
                         r"(?:Company|Corporation|Issuer)\s*[" + Q + r"]", body[:4000]):
        al = re.findall(r"[" + Q + r"]\s*([^" + Q + r"]{3,40}?)\s*[" + Q + r"]", m.group(0))
        al = [a for a in al if a.lower() not in ("company", "corporation", "issuer") and re.search(r"[a-z]", a)]
        pre = body[max(0, m.start() - 400):m.start()]
        pre = re.sub(r"\([^()]*\)\s*$", "", pre.rstrip())
        for _ in range(4):
            pre2 = re.sub(r"\([^()]*\)\s*$", "", pre.rstrip())
            if pre2 == pre:
                break
            pre = pre2
        orgs = list(_ORG.finditer(pre))
        if orgs:
            full = _clean_org(orgs[-1].group(1)) or ""
            if al and al[0] in full and not full.startswith(al[0]):
                return al[0]
            return full or None
        tail = re.findall(r"((?:[A-Z][\w&'\u2019.\-]*\s+){0,4}[A-Z][\w&'\u2019.\-]*)\s*$", pre)
        if tail:
            return _clean_org(tail[0])
    m = re.match(r"((?:[A-Z][\w&'\u2019.\-]*\s+){0,4}?)(?:Announces|Reports|Closes|Completes|Enters|Signs|Executes|"
                 r"Acquires|Purchases|Sells|Expands|Provides|to\s|Reaches|Receives|Grants)", headline)
    if m and m.group(1).strip():
        return _clean_org(m.group(1))
    return None


def _mask_orgs(text, names, table):
    """Company names that contain 'Royalty/Royalties/Streaming' would otherwise read as an interest. Each is
    swapped for a placeholder ('Zorgb') that _unmask() turns back into the name."""
    for n in sorted(names, key=len, reverse=True):
        if n and re.search(r"(?i)royalt|stream", n):
            tok = table.setdefault(n, "Zorg" + "abcdefghijklmnopqrstuvwxy"[len(table) % 25] + ("" if len(table) < 25 else "x"))
            text = re.sub(re.escape(n).replace(r"\ ", r"\s*"), tok, text, flags=re.I)
    return text


def _unmask(v, table):
    if not v:
        return v
    for n, tok in table.items():
        v = v.replace(tok, n)
    return v


def _royalty_orgs(text):
    out = set()
    for m in re.finditer(r"((?:[A-Z][\w&'\u2019.\-]*\s+){0,4}(?:Royalt(?:y|ies)|Streaming)(?:\s+(?:&|and)\s+Royalty)?)\s*"
                         r"(?:\s+" + _SUFFIX + r"\b|['\u2019]s\b)", text):
        out.add(m.group(1).strip())
    for m in re.finditer(r"\b([A-Z][\w\-]+(?:\s+[A-Z][\w\-]+){0,2}\s+Royalties)\b(?!\s+(?:on|in|over|to)\b)", text):
        if not re.match(r"(?i)(?:spin|out|net|gross|the|its|our|existing|additional|new|two|three|all)\b", m.group(1)):
            out.add(m.group(1))
    return out


# ------------------------------------------------------------------ scope
_INTEREST = re.compile(r"(?i)\broyalt(?:y|ies)\b|\bstream(?:s|ing)?\b|\bNSR\b|\bGRR\b|\bGOR\b|\bNPI\b|net\s+smelter|"
                       r"net\s+profits?\s+(?:interest|stream)")
_DEAL = re.compile(r"(?i)\b(?:acquir\w*|acquisition|purchas\w*|sale|sells?|sold|buy(?:s|ing)?(?:[\s\-]?(?:back|down))?|"
                   r"bought|repurchas\w*|reacquir\w*|grant(?:s|ed)?|spin\s*-?\s*out|financing|amend\w*|restructur\w*|"
                   r"expands?\s+(?:\w+\s+){0,2}agreement|extend\w*|closes|closing|completes|definitive|"
                   r"(?:stream|royalty|streaming)\s+agreement|enters?\s+into|signs?)\b")
_OUT_OF_SCOPE = re.compile(r"(?i)\b(?:oil\s+and\s+gas|oil\s*&\s*gas|petroleum|boe(?:/d)?|barrels?|ORRI|overriding\s+royalty\s+"
                           r"interest|permian|music|songs?|sound\s+recording|ringtone|pharma\w*|film|"
                           r"working\s+interest)\b")
_RESULTS = re.compile(r"(?i)\b(?:quarter|Q[1-4]|annual|year[\s\-]+end|financial|interim|fiscal)\b[^.]{0,60}\bresults\b|"
                      r"\bresults\s+for\s+the\b|\bletter\s+(?:from|to)\b|\bportfolio\s+update\b|\bupdate\s+on\s+(?:its|the)\b|"
                      r"^market\s+one\b|\bmarket\s+one:|\binclusion\s+in\b|\bpresenting\s+at\b|\bconference\b|\bwebinar\b|"
                      r"\blawsuit|\bcourt\b|\barbitration\b|\bdispute|\bmeeting\b|\bcircular\b|\bshareholders\s+approve|"
                      r"\bapprov(?:al|es|ed)\b|\bmail(?:s|ing)\b|\beffective\s+date\b|\bupdates?\b|\bprogress\b|"
                      r"\bsecuring\b|\bforward\s+pays?\b|\bprepay\w*|\broyalty\s+companies\b|\btalks\b|\bcontinues\s+to\b")
_H_FIN = re.compile(r"(?i)\b(?:financing|spin\s*-?\s*out|restructur\w*|transaction)\b")


_INT_W = r"(?:royalt(?:y|ies)|streams?|NSRs?|GRR|GOR|NPI|net\s+smelter|net\s+profits?)"
_DV_W = (r"(?:acquir\w*|acquisition|purchas\w*|sale|sells?|sold|buys?(?:[\s\-]?(?:backs?|downs?))?|buy[\s\-]?(?:back|down)s?|"
         r"bought|repurchas\w*|reacquir\w*|grant(?:s|ed|ing)|spin\s*-?\s*out|financing|amend\w*|restructur\w*|expand\w*|extension|"
         r"extend\w*|transaction|agreement|closes|closing|completes|completion|signs?|executes?|enters?)")
_HEAD_DEAL = re.compile(r"(?i)\b" + _DV_W + r"\b\W+(?:\S+\s+){0,9}?(?:\d[\d.,/]*\s?%\s+)?" + _INT_W + r"\b|\b" + _INT_W +
                        r"\b\W+(?:\S+\s+){0,6}?" + _DV_W + r"\b|[$]\s?\d[\d.,]*\s*(?:million|billion|M)?\s+(?:\w+\s+){0,2}?" +
                        _INT_W + r"\s+(?:with|from|financing|agreement|deal)\b|\bpartners?\b[^.]{0,60}?\bfor\s+(?:\w+\s+){0,3}?"
                        r"(?:and\s+)?royalt")
_LINK = re.compile(r"(?i)\b(?:streams?|royalt\w*|NSR|net\s+smelter|net\s+profits?)\b[^.]{0,80}?\b(?:financing|transaction|spin\s*-?\s*out)\b|"
                   r"\b(?:financing|transaction|spin\s*-?\s*out)\b[^.]{0,80}?\b(?:streams?|royalt\w*|NSR|net\s+smelter|net\s+profits?)\b")


# 'Sells Lauriston Project ... While Retaining 2% NSR', 'Acquisition of Agnico Eagle's 55% Interest ... Agnico to
# Retain a 2% NSR': the deal is a property, and the royalty the vendor keeps is a mention in passing (Justin,
# 2026-09-21). 'Acquires Half of the Manicouagan Project Royalty' is a royalty deal: the royalty is the object.
_PROPERTY_DEAL = re.compile(r"(?i)\b(?:sells?|sale\s+of|to\s+sell|acquir\w*|acquisition\s+of|purchase\s+of|ownership\s+of|agreement\s+for|"
                            r"interest\s+in|option\s+(?:on|to\s+acquire))\s+(?:(?!royalt|nsr|stream|grr|npi|net\s)\S+\s+){0,6}?"
                            r"(?:project|property|properties|claims|interest)\b(?!\s+(?:royalt|nsr|net\s+smelter|stream))")


_WIDE_DEAL = re.compile(r"(?i)\bacquisition\s+of\s+(?:an?\s+)?(?:additional\s+)?(?:\w+\s+){0,2}?(?:stream|royalty|NSR)\b|"
                        r"\bacquires?\s+(?:an?\s+)?(?:\d[\d.]*\s?%\s+)?(?:\w+\s+){0,2}?(?:stream|royalty|NSR)\b|"
                        r"[$]\s?\d[\d.,]*\s*(?:million|billion|M)?\s+(?:\w+\s+){0,3}?(?:stream|streaming|royalty)\s+"
                        r"(?:agreement|financing|transaction)\b")


def _in_scope(h, lead):
    """(ok, reason). The headline carries the deal (a royalty or stream is what is bought, sold, granted, bought back
    or amended), or names a financing/spin-out the opening sentences tie to a stream or royalty."""
    if _WIDE_DEAL.search(h) and not re.search(r"(?i)\b(?:Q[1-4]|quarter|annual|year[\s\-]+end|fiscal)\b[^.]{0,80}?"
                                             r"\b(?:results|revenues?|earnings)\b", h) and not _OUT_OF_SCOPE.search(h):
        return True, "headline"
    if _RESULTS.search(h):
        return False, "results, recap, meeting, update, promotion or dispute"
    if _OUT_OF_SCOPE.search(h) or _OUT_OF_SCOPE.search(lead[:900]):
        return False, "oil and gas or non-mining"
    pd, hd = _PROPERTY_DEAL.search(h), _HEAD_DEAL.search(h)
    if pd and (not hd or pd.start() <= hd.start()):
        return False, "a property deal; the royalty rides along"
    if _HEAD_DEAL.search(h):
        return True, "headline"
    if _H_FIN.search(h) and _INTEREST.search(lead[:1500]):
        return True, "headline financing"
    return False, "no royalty or stream deal in the headline"


# ------------------------------------------------------------------ interests
_PAREN = r"(?:\s*\(\s*[" + Q + r"]?[^()]{0,24}?[" + Q + r"]?\s*\))?"
_TYPE_RX = [
    ("NPI", r"net\s+profits?\s+(?:interest|stream|royalty)(?:\s+royalty)?" + _PAREN + r"|\bNPI\b"),
    ("other", r"gross\s+margin\s+royalty|production\s+royalty|net\s+tonnage\s+royalty"),
    ("GRR", r"(?:sliding[\s\-]+scale\s+)?gross\s+(?:revenue|overriding|metal|proceeds|smelter)(?:\s+returns?)?" + _PAREN +
            r"\s+royalt(?:y|ies)(?:\s+interests?)?" + _PAREN + r"|\bGRR\b|\bGOR\b|\bGMR\b"),
    ("NSR", r"net\s+smelter\s+returns?" + _PAREN + r"(?:\s+(?:royalt(?:y|ies)|interest)(?:\s+interest)?)?" + _PAREN +
            r"|net\s+smelter\s+royalt(?:y|ies)|\bNSRs?\b(?:\s+royalt(?:y|ies))?"),
    ("stream", r"(?:(?:life[\s\-]+of[\s\-]+mine|LOM|precious\s+metals?|" + "|".join(_METALS) +
               r")\s+)?(?:stream(?:ing)?\s+(?:agreement|financing|interest)|stream)\b"),
    ("royalty", r"\broyalt(?:y|ies)\b"),
]
# 1.1.1: 'a one percent (1%) net smelter royalty' -- the rate in brackets
_RATE_BEFORE = re.compile(r"(\d{1,2}(?:\.\d{1,3})?)\s?%\d?\)?\s+(?:\([^)]{0,20}\)\s*)?(?:[\w\-]+\s+){0,4}$")
_RATE_AFTER = re.compile(r"\s*(?:\([^()]{0,30}\)\s*)?(?:royalty\s+)?(?:\([^()]{0,30}\)\s*)?of\s+(\d{1,2}(?:\.\d{1,3})?)\s?%(?!\s+of\b)")
_METAL_RX = re.compile(r"(?i)\b(" + "|".join(_METALS) + r")\b")


def _interest_mentions(s):
    """[(start, type, rate, metal)] in one piece of text."""
    out, taken = [], []
    for typ, rx in _TYPE_RX:
        for m in re.finditer(rx, s, flags=re.I):
            if any(a <= m.start() < b for a, b in taken):
                continue
            around = s[max(0, m.start() - 25):m.end() + 25]
            if typ in ("stream", "royalty") and re.search(r"(?i)stream\w*\s+(?:company|and\s+royalty|&)|royalt(?:y|ies)\s+(?:and|&)\s+"
                                                          r"stream|royalty\s+company|royalty\s+holders?|Zorg", around):
                continue
            if typ == "royalty" and re.search(r"(?i)royalt(?:y|ies)\s+(?:agreement|purchase\s+agreement|payments?)", s[m.start():m.end() + 25]):
                taken.append((m.start(), m.end()))
                continue
            taken.append((m.start(), m.end()))
            pre = s[max(0, m.start() - 45):m.start()]
            rm = _RATE_BEFORE.search(pre)
            rate = float(rm.group(1)) if rm else None
            if rate is None:
                ra = _RATE_AFTER.match(s, m.end())          # 1.1.1: 'an NSR of 0.5%'
                rate = float(ra.group(1)) if ra else None
            metal = None
            mm = _METAL_RX.search(m.group(0)) or _METAL_RX.search(pre[-25:])
            if mm:
                metal = mm.group(1).lower()
            out.append((m.start(), typ, rate, metal))
    out.sort()
    return out


def _stream_rate(body):
    m = re.search(r"(?i)(\d{1,3}(?:\.\d{1,2})?)\s?%\s+of\s+(?:the\s+)?(?:payable\s+|refined\s+)?(" + "|".join(_METALS) +
                  r")\s+(?:produced|production|ounces)", body)
    return (float(m.group(1)), m.group(2).lower()) if m else (None, None)


# ------------------------------------------------------------------ property
_PROP_WORD = r"(?:Project|Mine|Property|Deposit|Concessions?|Claims?|Operations?|Complex|District|Mineral\s+District|Lease|Camp)"
_ADJ = r"(?:(?:flagship|producing|operating|past[\s\-]+producing|existing|fully\s+owned|100%\s+owned|wholly[\s\-]+owned|underlying|" \
       r"advanced|development[\s\-]+stage|cash[\s\-]+flowing)\s+)?"
_PROP = re.compile(
    r"\b(?:on|over|at|from|for|in|of|covering|comprising)\s+(?:all\s+\w+\s+produced\s+from\s+)?"
    r"(?:(?:the\s+)?(?:Company|Optionee|[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,4})['\u2019]s?\s+|the\s+|its\s+|their\s+)?" + _ADJ +
    r"((?:[A-Z][\w'\u2019\-]*|del|de|la|des|du)(?:\s+(?:[A-Z][\w'\u2019\-]*|del|de|la|des|du|\d)){0,4}?)"
    r"(?:\s*\([^)]{0,40}\))?\s+(?:(?:Gold|Silver|Copper|Tin|Tungsten|Nickel|Graphite|Lithium|Uranium|Zinc|"
    r"[A-Z][a-z]+\s*-\s*[A-Z][a-z]+|gold|silver|copper|gold\s*-\s*copper)\s+)?"
    r"(" + _PROP_WORD + r"|project|mine|property|deposit|concessions?|claims?|mineral\s+district|lease|operations?)\b")
_BAD_PROP = re.compile(r"(?i)^(?:the|company|its|a|an|all|this|such|our|certain|existing|additional|new|royalty|stream|nsr|"
                       r"optionee|each|mineral|tsx|cse|transaction|agreement|net|gross|two|three|other|several|these|"
                       r"those|any|both|which|and|or|canadian|quebec|ontario|nevada)$")


def _property(text, defs):
    for m in _PROP.finditer(text):
        name = m.group(1).strip()
        name = re.split(r"['\u2019]s\s+", name)[-1]
        name = re.sub(r"\s+(?:Zinc|Gold|Silver|Copper|Nickel)?['\u2019]s?$", "", name).strip()
        if _BAD_PROP.match(name.split()[0]) or _BAD_PROP.match(name) or re.search(r"Zorg", name):
            continue
        if re.match(r"(?i)(?:net|gross|royalt|stream|nsr|the)\b", name) or \
                re.search(r"\b(?:Mining|Resources|Metals|Minerals|Royalties|Exploration|Explorers)$", name):
            continue          # a company's name read as a property ('Bunker Hill Mining')
        d = defs.get(name.lower())
        if d and not re.search(r"(?i)\b" + _SUFFIX + r"\b", d) and len(d) > len(name) and \
                not re.search(r"\b(?:Mining|Resources|Metals|Minerals|Royalties|Exploration|Explorers|Gold|Silver)$", d):
            d = re.split(r"['\u2019]s\s+", d)[-1]
            d = re.sub(r"\s+(?:Gold|Silver|Copper)?\s*(?:Project|Mine|Property|Deposit)$", "", d)
            return d if name.lower() in d.lower() else name
        return name
    m = re.search(r"\b(?:stream|royalty|NSR)\s+on\s+([A-Z]{2,6})\b", text)
    if m and m.group(1).lower() in defs:
        return defs[m.group(1).lower()]
    return None


# ------------------------------------------------------------------ price
_MONEY = r"((?-i:US|U\.S\.|C|CA|CAD|CDN|A|AU|AUD)?\$|(?-i:USD|CAD|AUD)\s?)\s?(\d[\d,]*(?:\.\d+)?)\s*(million|billion|M|MM|B|k)?\b"


def _money(m, default_cur):
    cur_tok, num, mult = m.group(1).replace(" ", "").upper(), m.group(2), (m.group(3) or "")
    v = float(num.replace(",", ""))
    v *= {"million": 1e6, "m": 1e6, "mm": 1e6, "billion": 1e9, "b": 1e9, "k": 1e3}.get(mult.lower(), 1)
    cur = "USD" if cur_tok.startswith(("US", "U.S", "USD")) else "CAD" if cur_tok.startswith(("C", "CA", "CDN")) \
        else "AUD" if cur_tok.startswith(("A",)) else default_cur
    return v, cur


def _default_currency(body):
    if re.search(r"(?i)(?:in|all\s+dollar\s+(?:figures|amounts)\s+(?:are\s+)?in)\s+(?:U\.?S\.?|United\s+States)\s*(?:\$|dollars)|"
                 r"all\s+dollar\s+figures\s+in\s+US\$|unless\s+otherwise\s+(?:noted|stated|indicated)[^.]{0,20}US\$", body[:3000]):
        return "USD"
    return "CAD"


def _price(h, deal_text, body, cur0):
    m = re.search(r"(?i)total\s+(?:cash\s+)?(?:consideration|purchase\s+price)\s+(?:for\s+[^.$]{0,60}?)?(?:is|of|was)\s+"
                  r"(?:approximately\s+)?" + _MONEY, deal_text) or \
        re.search(r"(?i)\bfor\s+(?:an?\s+)?(?:aggregate|total|gross)?\s*(?:cash\s+)?(?:proceeds|consideration|purchase\s+price)?"
                  r"\s*(?:of\s+)?(?:approximately\s+)?" + _MONEY, deal_text) or \
        re.search(r"(?i)" + _MONEY + r"\s+(?:(?:gold|silver|precious\s+metals?|copper)\s+)?(?:stream|royalty)", deal_text) or \
        re.search(r"(?i)\bfor\s+" + _MONEY, h) or \
        re.search(r"(?i)total\s+(?:cash\s+)?(?:consideration|purchase\s+price)\s+(?:for\s+[^.$]{0,60}?)?(?:is|of|was)\s+"
                  r"(?:approximately\s+)?" + _MONEY, body[:6000]) or \
        re.search(r"(?i)consideration\s+(?:for\s+the\s+(?:purchase|acquisition)\s+)?(?:was|is|of)\s+" + _MONEY, body[:5000]) or \
        re.search(r"(?i)deemed\s+value\s+of\s+" + _MONEY, deal_text + " " + body[:3000])
    if m:
        return _money(m, cur0)
    return None, None


# ------------------------------------------------------------------ parties and direction
_BUY_V = r"acquir\w*|acquisition|purchas\w*|buy(?:s|ing)?|bought|reacquir\w*|repurchas\w*"
_SELL_V = r"sale|sells?|sold|grant(?:s|ed)?|spin\s*-?\s*out|allocated|transfer\w*"
_PARTY = r"((?:[A-Z][\w&'\u2019.\-]*\s+){0,5}[A-Z][\w&'\u2019.\-]*(?:\s*,?\s+" + _SUFFIX + r"\.?)?)"
_LEADIN = r"(?:a\s+wholly[\s\-]owned\s+subsidiary\s+of\s+|an\s+affiliate\s+of\s+|(?:the\s+)?funds\s+managed\s+by\s+|the\s+)?"


def _alias(name, defs, issuer):
    if not name:
        return None
    k = name.strip(" ,.").lower()
    if k in ("company", "the company", "corporation"):
        return issuer
    if k in defs and defs[k]:
        return defs[k]
    return _clean_org(name)


def _party_at(s, i, defs, issuer):
    """The party whose name starts at s[i:] -- and a second one joined by 'and' ('Franco-Nevada Corporation
    ("Franco-Nevada") and EMX Royalty Corporation') -- or None."""
    m = re.match(_LEADIN + _PARTY, s[i:])
    if not m:
        return None
    n = m.group(1)
    n = re.split(r"\s+(?:for|to|on|in|pursuant|under|over|covering|and\s+(?:its|the)|announce\w*|is|has|will|signs?|enters?)\b", n)[0]
    if re.match(r"(?i)(?:the|a|an|its|their|one|certain|shareholders|each|this|such|transaction|agreement|arrangement|"
                r"offering|acquisition|royalty|stream|project|closing|completion|approval)\b", n) or len(n) < 2:
        return None
    first = _alias(n, defs, issuer)
    rest = s[i + m.end():i + m.end() + 160]
    em = re.match(r"[^.,;]{0,30}?(?:\.\s*)?,?\s*an?\s*n?\s+(?:entity\s+(?:managed|controlled|advised)\s+by|wholly[\s\-]owned\s+"
                  r"subsidiary\s+of)\s+" + _PARTY, rest)
    if em:
        return _alias(em.group(1), defs, issuer)
    am = re.match(r"(?:\s*\([^()]{0,60}\))*\s+and\s+" + _PARTY, rest)
    if am and re.search(r"\b" + _SUFFIX + r"\.?$", am.group(1)):
        return first + "; " + _alias(am.group(1), defs, issuer)
    return first


def _named_after(prep, s, defs, issuer):
    for m in re.finditer(r"(?i)\b" + prep + r"\s+", s):
        p = _party_at(s, m.end(), defs, issuer)
        if p:
            return p
    return None


def _first(rx, s):
    m = re.search(r"(?i)\b(?:" + rx + r")\b", s)
    return m.start() if m else None


def _parties(D, defs, issuer, is_royalty_co, ctx=""):
    s = D
    if re.search(r"(?i)\bthe\s+Optionee\s+(?:has|will\s+have)\s+(?:the\s+)?option\s+to\s+acquire", ctx) and defs.get("optionee"):
        return defs.get("optionee"), issuer
    m = re.search(r"(?:pursuant\s+to\s+which|whereby|under\s+which)\s+(?:the\s+)?" + _PARTY +
                  r"\s+(?:will|would|has\s+agreed\s+to|agreed\s+to|shall)\s+(?:acquire|purchase|buy)", s)
    if m:
        buyer = _alias(m.group(1), defs, issuer)
        if buyer != issuer:
            return buyer, issuer
        # '... with Grupo Minero Bacis, pursuant to which the Company will acquire': the other party sells
        return issuer, (_named_after(r"from", s, defs, issuer) or _named_after(r"with", s, defs, issuer))
    if re.search(r"(?i)\bthe\s+Optionee\s+(?:has|will\s+have)\s+(?:the\s+)?option\s+to\s+acquire", s):
        return defs.get("optionee"), issuer
    gm = re.search(_PARTY + r"\s+granted\s+" + _LEADIN + _PARTY, s)
    if gm:
        return _alias(gm.group(2), defs, issuer), _alias(gm.group(1), defs, issuer)
    sv, bv = _first(_SELL_V, s), _first(_BUY_V, s)
    if sv is not None and (bv is None or sv < bv):
        return _named_after(r"to", s[sv:], defs, issuer), issuer
    if bv is not None:
        return issuer, (_named_after(r"from", s[bv:], defs, issuer) or _named_after(r"with", s, defs, issuer))
    other = _named_after(r"with", s, defs, issuer)
    return (issuer, other) if is_royalty_co else (other, issuer)


def _operator(D, body, defs, issuer, prop):
    s = D
    m = re.search(r"(?:operated|explored\s+under\s+option|owned\s+and\s+operated)\s+by\s+" + _PARTY, s)
    if m:
        return _alias(m.group(1), defs, issuer)
    m = re.search(r"\b(?:on|over|in|at)\s+(?:the\s+)?" + _PARTY + r"['\u2019]s?\s+" + _ADJ + r"[A-Z][^.]{0,60}?\b" + _PROP_WORD, s)
    if m:
        n = m.group(1)
        if n.lower() in ("company", "optionee"):
            return issuer if n.lower() == "company" else defs.get("optionee")
        if not re.match(r"(?i)(?:the|its)\b", n):
            return _alias(n, defs, issuer)
    if re.search(r"(?i)\b(?:on|over|in)\s+(?:the\s+)?(?:Company['\u2019]s|its)\s+" + _ADJ + r"[A-Z]", s):
        return issuer
    if prop:
        m = re.search(re.escape(prop) + r"[^.]{0,80}?\b(?:is\s+)?(?:owned\s+and\s+)?operated\s+(?:through\s+[^.]{0,60}?)?by\s+" +
                      _PARTY, body)
        if m:
            return _alias(m.group(1), defs, issuer)
    return None


_ROYCO = re.compile(r"(?i)\b(?:royalty\s+(?:and|&)\s+stream\w*|stream\w*\s+(?:and|&)\s+royalty|royalty)\s+company\b")


def _status(h, D):
    t = h + " " + D
    if re.search(r"(?i)\b(?:closes|closed|closing\s+of|completed|completes|completion\s+of|has\s+(?:now\s+)?(?:acquired|purchased|sold)|"
                 r"announced\s+today\s+the\s+sale|has\s+been\s+completed)\b", t):
        return "closed"
    if re.search(r"(?i)\b(?:agreement|agreed|definitive|term\s+sheet|will\s+acquire|to\s+acquire|intends|plans\s+to|entered\s+into|"
                 r"letter\s+agreement|binding)\b", t):
        return "agreed"
    return None


def _norm_key(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# ------------------------------------------------------------------ 1.0.1: the shared project-name helper
_PN_SUF = re.compile(r"(?i)\s+(?:projects?|property|properties|mines?|deposits?|claims?|concessions?|operations?|complex|"
                     r"(?:mineral\s+)?district|leases?|camp|prospects?)$")
_PN_MET = (r"(?:gold|silver|copper|tin|tungsten|nickel|graphite|lithium|uranium|zinc|tantalum|cobalt|pgms?|pge|"
           r"iron\s+ore|oxide|polymetallic)")
_PN_MET_TAIL = re.compile(r"(?i)(?:\s+" + _PN_MET + r"(?:\s*-\s*" + _PN_MET + r")*)+$")
_PN_SYM_TAIL = re.compile(r"(?:\s+(?:Ni|Cu|Co|Au|Ag|Zn|Pb|PGE|PGM))+$")
_PN_DROP_LEAD = re.compile(r"(?i)^(?:(?:historic|historical|permitted|producing|past[\s\-]+producing|flagship|newly|"
                           r"acquired|remaining|the|its)\s+)+")
_PN_BAD_LEAD = {"include", "includes", "including", "fund", "funding", "selling", "sell", "spin-out", "spin", "owners",
                "both", "two", "three", "four", "five", "six", "their", "our", "company", "company\u2019s", "company's",
                "prospective", "future", "relinquished", "certain", "several", "all", "each", "part", "royalty", "stream",
                "nsr", "net", "gross", "canadian", "quebec", "ontario", "nevada", "mexican", "australian", "bolivian"}
_PN_LONE = {"bay", "lake", "lakes", "creek", "river", "valley", "hill", "hills", "mountain", "ridge", "park", "island",
            "peak", "canyon", "gulch", "brook", "pond", "mill", "north", "south", "east", "west", "main", "diamond"}
_PN_ORG_END = re.compile(r"(?i)\b(?:partners|finance|capital|resources|resource|mining|metals|minerals|royalties|royalty|"
                         r"streaming|exploration|holdings?|group|corp|corporation|inc|ltd|limited|plc|llc)\.?$")
_PN_INT = r"(?:royalt\w*|streams?|nsrs?|npi|grr|net\s+smelter|net\s+profits?|financing)"
_PN_PORTFOLIO = re.compile(r"(?i)portfolio|royalty\s+(?:interests|assets)|\bassets\b|\broyalties\s+(?:on|in|to|from|and|of)\b|"
                           r"\broyalties\s*$|\bstreams\s+(?:on|from)\b")
_PN_NEIGH = re.compile(r"(?i)adjoin\w*|adjacent|neighbou?r\w*|contiguous|along\s+strike|in\s+exchange\s+for")


def _pn_rx(name):
    return r"(?<![\w\u2019'])" + r"\s+".join(re.escape(w) for w in name.split()) + r"(?![\w\u2019'])"


def _pn_names(found):
    out = []
    for v in found or []:
        s = v if isinstance(v, str) else next((y for y in v if isinstance(y, str)), None)
        if s:
            out.append(s)
    return out


def _pn_page(raw):
    """A helper name in this page's form: suffix, metal words and element symbols off ('Norway Based Rana
    Nickel-Copper-Cobalt' -> 'Rana'); lists, descriptions, numbers, mills and lone landforms refused (None)."""
    s = " ".join((raw or "").split())
    s = re.sub(r"(?i)^.*?\bbased\s+", "", s)
    for _ in range(3):
        s = _PN_SUF.sub("", s).strip()
        s = _PN_MET_TAIL.sub("", s).strip()
        s = _PN_SYM_TAIL.sub("", s).strip()
    s = _PN_DROP_LEAD.sub("", s).strip()
    if not s or len(s) < 2 or re.search(r"(?i)\s(?:and|&|or)\s|,", s) or \
            re.fullmatch(r"(?i)" + _PN_MET + r"(?:\s*-\s*" + _PN_MET + r")*", s):
        return None
    ws = s.split()
    if ws[0].lower() in _PN_BAD_LEAD or re.match(r"\d", s) or \
            re.search(r"(?i)\b(?:million|billion|ounces?|oz|moz|tonnes?|based|mill)\b", s):
        return None
    if len(ws) == 1 and (ws[0].lower() in _PN_LONE or ws[0].islower() or _BAD_PROP.match(ws[0]) or
                         re.search(r"(?i)(?:ian|ean|ese)$", ws[0])):
        return None
    if _PN_ORG_END.search(s) or PN.clean(s + " Project") is None:
        return None
    return s


def _pn_parties(rows, issuer):
    ws = set(PN.key(issuer or "").split())
    for r in rows:
        for k in ("buyer", "seller", "operator"):
            for part in re.split(r";\s*", r.get(k) or ""):
                ws |= set(PN.key(part).split())
    return ws


def _pn_is_party(name, parties):
    return bool(set(PN.key(name).split()) & parties)


def _pn_tied_head(name, t):
    """The headline ties the name to the interest: '... Royalty on SolGold's Cascabel', '... Stream from Vale's
    Voisey's Bay', 'Fosterville Mine Royalty'; not a neighbour or an exchange ('... in exchange for Tug Project')."""
    for m in re.finditer(_pn_rx(name), t, re.I):
        pre = t[:m.start()]
        if _PN_NEIGH.search(pre[-40:]):
            continue
        interest_before = re.search(r"(?i)\b" + _PN_INT, pre)
        if interest_before and re.search(r"(?i)\b(?:on|over|at|in|covering|respect\s+(?:to|of))\s+(?:(?:the|its|a|an)\s+)?"
                                         r"(?:[\w.\u2019'\-]+\s+){0,3}$", pre):
            return True
        if interest_before and re.search(r"(?i)\bfrom\s+(?:[\w.\u2019'\-]+\s+){0,2}[\w.\-]+(?:['\u2019]s?|s['\u2019])\s+$", pre):
            return True
        if re.match(r"(?i)(?:\s+[\w.\u2019'\-]+){0,3}?\s+(?:royalt\w*|streams?|nsr|npi|grr)\b", t[m.end():]):
            return True
    return False


def _pn_tied_body(name, b):
    """The opening text ties the name to the interest in one sentence: '... net smelter return royalty on the
    Pebble Project', '... silver stream in respect to the Horne 5 Project'. Not the About section or a company
    description ('Sailfish is a ... royalty and streaming company ... portfolio ... San Albino'), and not one of several
    properties ('the Mactung and Cantung royalty', 'the Sleeping Giant and Dormex properties')."""
    about = re.search(r"\bAbout\s+(?:the\s+)?[A-Z][\w\-\u2019']+", b)
    if about and about.start() > 200:
        b = b[:about.start()]
    n = _pn_rx(name)
    if re.search(n + r"\s+(?:[A-Za-z]+)?\s*,?\s*and\s+(?:the\s+)?[A-Z][a-z]", b[:3000]) or \
            re.search(r"[A-Z][\w\-\u2019']+\s+and\s+(?:the\s+)?" + n, b[:3000]):
        return False     # the release pairs it with another property: one row cannot name both
    for m in re.finditer(n, b[:3000], re.I):
        pre = re.split(r"[.;]\s", b[max(0, m.start() - 220):m.start()])[-1]
        post = b[m.end():m.end() + 60]
        if _PN_NEIGH.search(pre[-60:]) or \
                re.search(r"(?i)portfolio|\bis\s+an?\s+[^.]{0,60}?\b(?:royalty|streaming)\b[^.]{0,30}?\bcompany", pre):
            continue
        if re.match(r"\s+(?:[A-Za-z]+)?\s*,?\s*and\s+(?:the\s+)?[A-Z][a-z]", post) or \
                re.search(r"[A-Z][\w\-\u2019']+\s+and\s+(?:the\s+)?$", pre):
            continue
        if re.search(r"(?i)\b" + _PN_INT + r"\b[^.]{0,100}?\b(?:on|over|at|covering|respect\s+(?:to|of))\s+"
                     r"(?:(?:the|its|a|an)\s+)?(?:[\w.\u2019'\-]+\s+){0,3}$", pre):
            return True
    return False


def _pn_fix_own(own, text, pick):
    """1.0.0's name respelled or, when it is no property, replaced by pick() (a tied helper name) or left blank."""
    m = re.match(r"^(.*?)['\u2019]s$", own)
    if m:   # 'Platreef's', "Scottie's" -> the name when the text writes it before Project/Mine...; 'Company's' is none
        stem = m.group(1).strip()
        if stem and stem.lower() not in ("company", "corporation") and \
                re.search(_pn_rx(stem) + r"(?:\s+[A-Z][\w\-]*){0,2}\s+(?:Project|Mine|Property|Deposit|Claims)", text):
            return stem
        return pick()
    ws = own.split()
    if ws[0].lower() in ("their", "its", "our", "the", "company", "relinquished", "include", "includes", "including") or \
            own[:1].islower() or _PN_ORG_END.search(own):
        return pick()
    if len(ws) == 1 and ws[0].lower() in _PN_LONE:
        c = pick()
        return c if c and c.split()[-1].lower() == ws[0].lower() else own
    if ws[0].lower() in ("historic", "historical") and len(ws) > 1:
        rest = " ".join(ws[1:])
        if rest.lower() not in ("placer", "lode", "vein", "zone", "target", "mine", "workings") and \
                PN.clean(rest + " Project") and re.search(_pn_rx(rest) + r"\s+(?:\w+\s+)?(?:Project|Deposit|Property|Mine)", text, re.I):
            return rest
        return own
    s = _PN_SYM_TAIL.sub("", own).strip()
    return s or own


def _property_pn(rows, headline, body, issuer):
    """1.0.1: 1.0.0's property first; the shared helper fills a blank, respells, or replaces a name that is no property
    (see the notes at the top)."""
    if not rows:
        return rows
    t = " ".join((headline or "").split())
    b = " ".join((body or "")[:8000].split())
    try:
        head = [p for p in (_pn_page(n) for n in _pn_names(PN.find(t, issuer))) if p]
        opening = [p for p in (_pn_page(n) for n in _pn_names(PN.projects(t, b[:6000], issuer))) if p]
    except Exception:
        return rows
    parties = _pn_parties(rows, issuer)
    portfolio = bool(_PN_PORTFOLIO.search(t))
    single = len(rows) == 1

    def pick():
        if portfolio or not single:
            return None
        for n in head:
            if not _pn_is_party(n, parties) and _pn_tied_head(n, t):
                return n
        for n in opening:
            if not _pn_is_party(n, parties) and _pn_tied_body(n, b):
                return n
        return None

    text = t + " " + b
    out = []
    for r in rows:
        own = r.get("property")
        if own and "Strm" in own:
            cand = re.sub(r"\bStrm\b", "Stream", own)
            new = cand if re.search(_pn_rx(cand), text, re.I) else own
        elif not own:
            new = pick()
        else:
            new = _pn_fix_own(own, text, pick)
        if new and new != own and any(new == x.get("property") for x in rows if x is not r):
            new = own          # never fold one row into another's property
        out.append(dict(r, property=new) if new != own else r)
    return out


# ------------------------------------------------------------------ 1.0.3: several properties per release (helper 1.0.5)
_PM_MAX_ROWS = 4          # a release tying 2 to 4 properties to the interest gets one row each; more is a portfolio
_PM_LIST_CHARS = 150      # the property fact keeps 160 characters
# rev 6: words that make a name a reference point, not the royalty ('... surrounding the main Horne 5 properties', 'in
# proximity to the Horne 5 Gold Project', '11km to the northwest of Falco's Horne 5')
_PM_NEAR = re.compile(r"(?i)surround\w*|\bnear(?:by)?\b|proxim\w*|in\s+the\s+vicinity|\baround\b|"
                      r"\b\d+(?:\.\d+)?\s?(?:km|kilomet\w+|miles?)\b")
_PM_COMPANY_DESC = re.compile(r"(?i)\bis\s+an?\s+[^.]{0,60}?\b(?:royalty|streaming)\b[^.]{0,30}?\bcompany")


def _pm_tied(name, t, news):
    """The release ties the name to the interest: the headline does (as 1.0.1), or one sentence of the news (the
    helper's subject_text: no About section, no forward-looking notes) names both the interest and the name -- not as a
    neighbour and not in a company description."""
    if _pn_tied_head(name, t):
        return True
    n = _pn_rx(name)
    if any(_PM_NEAR.search(news[max(0, m.start() - 60):m.start()]) for m in re.finditer(n, news[:6000], re.I)):
        return False          # rev 6: the release uses it as a reference point somewhere
    for s in re.split(r"(?<=[.;!?])\s+", news[:6000]):
        m = re.search(n, s, re.I)
        if not m or _PN_NEIGH.search(s[:m.start()][-60:]) or _PM_NEAR.search(s[:m.start()][-60:]) or \
                _PM_COMPANY_DESC.search(s):
            continue
        if re.search(r"(?i)\b" + _PN_INT + r"\b", s):
            return True
    return False


def _pm_tied_strict(name, t, news):
    """For a row of its own, the release has to put the property under the interest: the headline does (as 1.0.1), or
    a news sentence says '... royalty/stream/NSR ... on/over/covering/at/from [up to six words] <name>' ('royalties on
    both Kirkland West and Omega', 'a 1.8% GRR on the Dalgaranga Project'). A name the sentence only mentions (a mill,
    the company's other mine) does not get a row."""
    if _pn_tied_head(name, t):
        return True
    n = _pn_rx(name)
    for s in re.split(r"(?<=[.;!?])\s+", news[:6000]):
        if _PM_COMPANY_DESC.search(s):
            continue
        for m in re.finditer(n, s, re.I):
            pre = s[:m.start()]
            if _PN_NEIGH.search(pre[-60:]) or _PM_NEAR.search(pre[-60:]):
                continue
            if re.search(r"(?i)\b" + _PN_INT + r"\b[^.]{0,100}?\b(?:on|over|covering|at|from|respect\s+(?:to|of))\s+"
                         r"(?:(?:the|its|a|an|both)\s+)?(?:[\w.\u2019'\-]+\s+){0,6}$", pre):
                return True
    return False


_PM_SUB = re.compile(r"(?i)\b(?:deposits?|zones?|prospects?|targets?|showings?|pits?|veins?|claims?)$")


def _pm_names(projects, parties):
    raws = [r for r in (projects or []) if r]
    if any(not _PM_SUB.search(r) for r in raws):
        raws = [r for r in raws if not _PM_SUB.search(r)]    # a deposit inside a named project is not its own row
    out = []
    for raw in raws:
        p = _pn_page(raw)
        if p and not _pn_is_party(p, parties) and not any(PN.same(p, x) for x in out) and not _pm_junk(p):
            out.append(p)
    # rev 4: an abbreviation of another listed name ('ATO' for Altan Tsagaan Ovoo) is not a second property; rev 5: nor
    # is a bare two- or three-letter abbreviation ('SP', 'SG' for Metalla's Pelangio Poirier royalty)
    return [p for p in out if not re.fullmatch(r"[A-Z]{1,3}", p) and not (re.fullmatch(r"[A-Z]{2,5}", p) and any(
        "".join(w[0] for w in x.split() if w[:1].isupper()) == p for x in out if x != p))]


# rev 4: words that make a listed name generic ('Operator Operator Stock Exchange Listing', 'Exciting Development')
_PM_JUNK = {"operator", "stock", "exchange", "listing", "exciting", "development", "strategic", "transformational",
            "growth", "asset", "assets", "royalty", "royalties", "stream", "streams", "portfolio", "company",
            "corporate", "new", "existing", "additional", "project", "projects", "property", "properties"}


def _pm_junk(name):
    ws = re.findall(r"[A-Za-z]+", name or "")
    return not ws or all(w.lower() in _PM_JUNK for w in ws)


# rev 4: a name the release writes as a company ('Cameco Corporation', 'Orion Mine Finance') is not a property
_PM_CORP = (r"\s+(?:Corporation|Corp\b|Inc\b|Incorporated|Ltd\b|Limited|plc\b|LLC\b|L\.?P\b|Group\b|Fund\b|"
            r"Mine\s+Finance|Holdings|Capital\b|Resource\s+Partners|Partners\b|Resources\s+(?:Inc|Corp|Ltd|LLC)\b)")


def _pm_company(name, b):
    return re.search(_pn_rx(name) + _PM_CORP, b) is not None


def _pm_nested(x, y, text):
    """rev 4: the release puts one name inside the other ('the Eagle Gold Project on the Dublin Gulch property',
    'the Trixie mine at its Tintic Project'): one property, not two rows."""
    tail = r"\s+(?:(?:the|its|a)\s+)?(?:[\w\u2019'\-]+\s+){0,2}?"
    for a, c in ((x, y), (y, x)):
        # strong words within five words ('... property (the "Property") which hosts the Eagle ...'); 'in/at/on/of'
        # only straight after the name ('Trixie Mine in Utah's historic Tintic'), not 'El Realito Property and Adds
        # Royalty on ... Orion'
        if re.search(_pn_rx(a) + r"(?:\s+[^\s.;]+){0,5}?\s+(?:within|part\s+of|located\s+(?:on|at|in|within)|hosts?|"
                     r"hosting|compris\w*|contain\w*)" + tail + _pn_rx(c), text, re.I) or \
                re.search(_pn_rx(a) + r"(?:\s+[^\s.;,]+)?\s+(?:in|at|on|of)" + tail + _pn_rx(c), text, re.I):
            return True
    return False


# rev 4: a one-name 'Portfolio: X' only when the headline sells or buys a portfolio / package of royalties or streams
_PM_PF_HEAD = re.compile(r"(?i)(?:royalt\w*|stream\w*|NSRs?)\s+(?:portfolio|package)|portfolio\s+of\s+(?:[\w\-]+\s+){0,4}?"
                         r"(?:royalt|stream|NSR)|\bpackage\b")


def _pm_rate(name, b):
    """A rate the release states for this property ('a 1.5% NSR on the Saxby Project'), else None."""
    m = re.search(r"(\d{1,2}(?:\.\d{1,3})?)\s?%\s+(?:[\w\-]+\s+){0,4}?(?:NSR|net\s+smelter|royalt\w*|GRR|gross|stream|NPI)"
                  r"[^.]{0,60}?\b(?:on|over|covering|at|in\s+respect\s+(?:to|of))\s+(?:the\s+)?" + _ADJ + _pn_rx(name), b, re.I)
    if not m:
        return None
    v = float(m.group(1))
    return v if 0 < v <= 100 else None


def _pm_listing(names):
    """'Portfolio: Eskay Creek, Pinson, Hasbrouck +19' within the property fact's length."""
    s, used = "Portfolio: ", 0
    for i, n in enumerate(names):
        more = len(names) - i - 1
        piece = ("" if i == 0 else ", ") + n
        tail = " +%d" % more if more else ""
        if len(s) + len(piece) + len(tail) > _PM_LIST_CHARS and i > 0:
            return s + " +%d" % (len(names) - i)
        s += piece
        used += 1
    return s


def _property_multi(rows, headline, body, issuer):
    """1.0.3: a release about several properties (PN.release_projects, helper 1.0.5), when the reader wrote one row.
      - 2 to 4 properties the release puts under the interest (_pm_tied_strict) -> one row per property. The row the
        reader wrote is kept as it is when it names one of them; each other property gets a row with the deal's type,
        metal, parties, action and status, the rate stated for that property (or the deal's rate when the release
        states one rate for all), and no price -- the price is the whole deal's, as 1.0.0 does for its two-property rows.
      - a portfolio (the helper's scope, or 1.0.1's portfolio wording with 3+ tied properties, or more than 4 tied)
        -> the one row, its property listing the tied properties: 'Portfolio: Eskay Creek, Pinson +20' (Justin
        2026-09-27: 'One row listing the properties').
    Nothing changes when the reader's own property is not among the tied ones, or when it wrote several rows."""
    if len(rows) != 1:
        return rows
    t = " ".join((headline or "").split())
    b = " ".join((body or "")[:8000].split())
    try:
        rp = PN.release_projects(t, body or "", issuer)
        news = " ".join(PN.subject_text(body or "").split())
    except Exception:
        return rows
    if rp.get("scope") not in ("several", "portfolio") and not _PN_PORTFOLIO.search(t):
        return rows
    base = rows[0]
    own = base.get("property")
    parties = _pn_parties(rows, issuer)
    names = _pm_names(rp.get("projects"), parties)
    tied = [n for n in names if _pm_tied(n, t, news)]
    if own:
        hit = [n for n in tied if PN.same(n, own)]
        if not hit:
            return rows
        tied = [own] + [n for n in tied if n not in hit]     # the reader's spelling first
    tied = [n for n in tied if (own and n == own) or not _pm_company(n, b)]      # rev 4
    portfolio = rp.get("scope") == "portfolio" or (_PN_PORTFOLIO.search(t) and len(tied) >= 3) or len(tied) > _PM_MAX_ROWS
    if portfolio:
        # rev 4: a one-name listing only when the headline sells or buys a royalty portfolio or package
        need = 2 if own or not _PM_PF_HEAD.search(t) else 1
        return [dict(base, property=_pm_listing(tied))] if len(tied) >= need else rows
    if rp.get("scope") != "several":
        return rows
    tied = [n for n in tied if (own and n == own) or _pm_tied_strict(n, t, news)]
    if len(tied) < 2:
        return rows
    try:
        parts = PN.split_by_project(news, tied, issuer)
    except Exception:
        parts = {}
    out = []
    for n in tied:
        stated = _pm_rate(n, b)
        if own and n == own:
            out.append(base)          # the reader's own row is kept as it is
            continue
        if any(_pm_nested(n, x.get("property") or "", t + ". " + news) for x in out if x.get("property")):
            continue          # rev 4: a property inside another one already listed
        # the property's own interest: the typed mention in the sentences about it ('a 1.8% GRR on Dalgaranga' in a
        # release led by a stream), else the deal's
        typed = [x for x in _interest_mentions(parts.get(n) or "") if x[1] != "royalty"]
        typ = typed[0][1] if typed else base.get("type")
        rate = stated if stated is not None else (typed[0][2] if typed and typed[0][2] is not None else
                                                   _pm_shared_rate(n, base.get("rate_pct"), b))
        if rate is not None and rate <= 0:
            rate = None       # rev 4: a 0% is no rate (Cerrado's Lagoa Salgada)
        if rate is None and not (_pn_tied_head(n, t) or re.search(_pn_rx(n), t, re.I)):
            continue          # rev 3: no headline and no rate for it -- a mention (money owed on another royalty), not a row
        metal = (typed[0][3] if typed and typed[0][3] else None) if typ != base.get("type") else base.get("metal")
        out.append(dict(base, property=n, type=typ, rate_pct=rate, metal=metal, price=None, currency=None))
    return out if len(out) >= 2 else rows


def _pm_shared_rate(name, rate, b):
    """The deal's rate for another property only when one sentence states that rate with this property too ('1.5%
    royalties on both Kirkland West and Omega', '1.75% NSR on the Crepori and Apiacas Gold Projects')."""
    if rate is None:
        return None
    r = ("%.3f" % rate).rstrip("0").rstrip(".")
    for s in re.split(r"(?<=[.;!?])\s+", b[:6000]):
        if re.search(r"(?<![\d.])" + re.escape(r) + r"\s?%", s) and re.search(_pn_rx(name), s, re.I):
            return rate
    return None


# ------------------------------------------------------------------ 1.1 (2026-09-28): wider rows (Justin's ROY11 answers)
# Justin, 2026-09-28, on the fresh 50-release set: every royalty kept by or granted to a property's seller or optionor is
# a row ("vendor royalty"; reverses the 09-21 rule Q1); a release that restates a royalty the company already holds gets
# a 'held' row when its headline is about that royalty (Q12 A: not portfolio updates, CEO letters or results tables); a
# closing or change reported inside a results release gets its own row (Q5); a settlement that changes how a royalty is
# calculated is an amendment (Q8); a royalty that replaces another is its own row (Q9); a second royalty bought back in
# the same release is its own row (Q10). Oil and gas stays out.
_V_KIND = "kind"          # fact: deal (default, not written) | vendor | held
_V_NEWS_CHARS = 7000
_V_ROLE = re.compile(r"(?i)\b(?:vendors?|optionors?|sellers?|grantors?|transferors?|owners?|landowners?|prospectors?)\b")
_V_NOT_NEW = re.compile(r"(?i)\b(?:existing|underlying|currently|already|previously|prior|historic\w*|third[\s\-]+part\w+|"
                        r"free\s+of|no\s+(?:NSR|royalt)|not\s+subject|eliminat\w*|terminat\w*|extinguish\w*|cancel\w*|"
                        r"ceas\w*|remov\w*|purchas\w*\s+(?:the\s+)?(?:remaining\s+)?(?:\d[\d.]*\s?%\s+)?(?:of\s+the\s+)?(?:NSR|royalt))")
# the release announces a property deal: an option, sale, purchase, earn-in or transfer of a property (not a payment,
# an update or results)
_V_HEAD = re.compile(r"(?i)\b(?:options?|optioned|optioning|earn[\s\-]?in|acquir\w*|acquisition|purchas\w*|sells?|sale|sold|"
                     r"divest\w*|dispos\w*|transfer\w*|vend\w*|agreement|agrees?|consolidat\w*|expands?|adds?|signs?|"
                     r"enters?|executes?|closes|completes|completion|monetiz\w*|spin[\s\-]?out|generates?|retain\w*)\b")
_V_HEAD_OBJ = re.compile(r"(?i)\b(?:propert(?:y|ies)|projects?|claims?|mines?|deposits?|concessions?|licen[cs]es?|"
                         r"tenements?|assets?|land\s+package|interest|lands|business\s+unit|district|portfolio|hectares)\b")
_V_NOT_HEAD = re.compile(r"(?i)\b(?:payment|receives?\s+\w*\s*(?:option|cash|share|final|first|second)|results|"
                         r"quarter|annual|drill\w*|assays?|intercepts?|samples?|sampling|update|letter|webinar|"
                         r"private\s+placement|financing\s+closes|amends?\s+option|extension|exercises?)\b")
_V_GRANT = re.compile(
    r"(?i)(?P<retain>\bretain\w*\b|\breserv\w*\b|\bkeep\w*\b)|"
    r"(?P<grant>\bgrant(?:s|ed|ing)?\b(?!\s+of\s+(?:options|RSU|stock|DSU))|\bissu\w+\b|\bcommit\w*\s+to\s+pay\w*|\bto\s+pay\w*|"
    r"\bpaying\b|\bwill\s+be\s+granted\b|\bbe\s+subject\s+to\b|\bsubject\s+to\b|\bplus\b|\bin\s+favou?r\s+of\b|"
    r"\bpayable\s+to\b|\bheld\s+by\s+the\s+(?:vendor|optionor)s?\b)")


def _v_news(body, limit=None):
    """The release's own news (PN.subject_text); with a limit, the whole body up to it -- a holdings statement in the
    About section is still what the company holds."""
    try:
        news = PN.subject_text(body or "") if not limit else body or ""
    except Exception:
        news = body or ""
    news = " ".join(news.split())[:limit or _V_NEWS_CHARS]
    news = re.sub(r"\bN\s(?=SR\b)", "N", news)                                       # 'N SR' split by the PDF
    news = re.sub(r"\bOption\s+ors\b", "Optionors", news)                          # a PDF split word
    return re.sub(r"(?i)(\d(?:\.\d+)?)\s*-?\s*per[\s\-]?cent\b", r"\1%", news)     # '1 -per-cent NSR'


_V_PARTY = r"((?:[A-Z][\w&'\u2019.\-]*\s+){0,4}?[A-Z][\w&'\u2019.\-]*)"
_V_ROLEW = r"(?:Vendors?|Optionors?|Sellers?|Owners?|Landowners?|vendors?|optionors?|sellers?|owners?|landowners?)"


def _v_role_names(news, word):
    """'with Gravel Ridge Resources Ltd., 1544230 Ontario Inc. and 2873454 Ontario Inc. (the "Optionors")'."""
    m = re.search(r"(?:with|from|to)\s+([^()]{5,220}?)\s*\(\s*(?:collectively,?\s*)?(?:the\s+)?[" + Q + r"]\s*" +
                  word + r"s?\s*[" + Q + r"]", news, re.I)
    if not m:
        return None
    parts = [_clean_org(x) for x in re.split(r",\s*(?:and\s+)?|\s+and\s+", m.group(1))]
    parts = [x for x in parts if x and len(x) > 2 and re.match(r"[A-Z0-9]", x)]
    return "; ".join(parts[:4]) or None


def _v_resolve(who, defs, issuer, news):
    who = re.sub(r"^(?:the|The)\s+", "", who.strip())
    if re.fullmatch(r"(?i)company|corporation", who):
        return issuer
    if re.fullmatch(_V_ROLEW, who):
        role = who.rstrip("s").lower()
        return _v_role_names(news, role) or defs.get(who.lower()) or "the " + who.lower()
    return _alias(who, defs, issuer)


def _v_holder(s, pos, defs, issuer, news, head):
    """Who gets or keeps the royalty mentioned at s[pos]."""
    pre, post = s[:pos], s[pos:]
    cands = []
    for m in re.finditer(r"(?:^|(?<=[\s(,;:\u2022]))(?:the\s+)?(" + _V_ROLEW + r"|Company|" + _V_PARTY[1:-1] + r")\s+(?:(?:will|shall|would|is\s+to|"
                         r"continues?\s+to|also|has|have|had)\s+){0,2}(?:retain\w*|reserv\w*|keep\w*|(?:be|was|were|been)\s+granted|"
                         r"receiv\w*\s+(?:a|an)\s+\d)", pre):
        cands.append(m.group(1))
    if cands:
        return _v_resolve(cands[-1], defs, issuer, news)
    # 1.1.1: 'grant a 2.5% NSR to the vendors', 'a 0.5% NSR royalty will be granted to Alpha', 'royalty (the "NSR
    # Royalty") to Alpha', 'grant Alpha the right to receive an NSR'
    end = _mention_end(s, pos)
    m = re.match(r"(?:\s*\([^()]{0,40}\))?(?:\s+royalt(?:y|ies))?(?:\s*\([^()]{0,40}\))?\s+(?:(?:will|shall|would)\s+be\s+"
                 r"(?:granted|payable)\s+|(?:granted|payable)\s+)?to\s+(?:the\s+)?(" + _V_ROLEW + r"|" + _V_PARTY[1:-1] + r")\b", s[end:end + 160])
    if m and not re.match(r"(?i)company|corporation|purchase|acquire|buy|be\b", m.group(1)):
        return _v_resolve(m.group(1), defs, issuer, news)
    m = re.search(r"\bgrant\w*\s+(?:to\s+)?(?:the\s+)?(" + _V_ROLEW + r"|" + _V_PARTY[1:-1] + r")\s+the\s+right\s+to\s+receive\s+"
                  r"(?:an?\s+)?$", pre[-200:])
    if m:
        return _v_resolve(m.group(1), defs, issuer, news)
    # 1.1.1: 'grant to Alpha, a one percent (1.0%) ...': a comma after the name
    for m in re.finditer(r"\b(?:grant\w*|issu\w+|pay\w*)\s+(?:to\s+)?(?:the\s+)?(" + _V_ROLEW + r"|" + _V_PARTY[1:-1] +
                         r"),?\s+(?:(?:an?\s+)?(?:aggregate\s+)?(?:of\s+)?(?:a|an)\s+|a\s+|an\s+|of\s+a\s+|\d)", pre[-200:] + " " + post[:20]):
        cands.append(m.group(1))
    if cands:
        return _v_resolve(cands[-1], defs, issuer, news)
    m = re.search(r"\b(?:in\s+favou?r\s+of|payable\s+to|held\s+by)\s+(?:the\s+)?(" + _V_ROLEW + r"|" + _V_PARTY[1:-1] + r")", post[:160])
    if m:
        return _v_resolve(m.group(1), defs, issuer, news)
    if re.search(r"(?i)\bretain\w*\b[^.]{0,30}$|\bplus\s+(?:a\s+)?(?:\d[\d.]*\s?%\s+)?(?:NSR|royalt)", head) and \
            re.search(r"(?i)\b(?:sells?|sale|sold|divest\w*|dispos\w*)\b", head):
        return issuer
    return None


def _v_issuer_side(h, news):
    """Which side of the property deal the issuer is on: 'buyer' (it acquires or options in the property), 'seller' (it
    sells or options it out), or None when the release does not say plainly."""
    lead = news[:1500]
    buy = re.search(r"(?i)\b(?:acquires?|acquisition\s+of|to\s+acquire|purchases?|purchase\s+of|consolidat\w*\s+into)\b", h) or \
        re.search(r"(?i)\b(?:the\s+Company|it)\s+(?:has\s+|will\s+|may\s+)?(?:\w+\s+){0,4}?(?:acquire[ds]?|purchased?|earn)\b[^.]{0,160}?\bfrom\s+[A-Z]", lead)
    sell = re.search(r"(?i)\b(?:sells?|sale\s+of|divest\w*|dispos\w*|options?\s+(?:\S+\s+){1,6}?to\s+[A-Z]|optioned\s+to|earn[\s\-]?in\s+agreement\s+on\s+its)\b", h) or \
        re.search(r"(?i)\b(?:sell|sold|option(?:ed)?)\s+(?:its|our|the|all|a)\s+[^.]{0,120}?\bto\s+[A-Z]", lead)
    if buy and not sell:
        return "buyer"
    if sell and not buy:
        return "seller"
    return None


def _mention_end(s, pos):
    """Where the interest mentioned at s[pos] ends ('net smelter returns royalty')."""
    for _typ, rx in _TYPE_RX:
        m = re.match(rx, s[pos:], flags=re.I)
        if m:
            return pos + m.end()
    return pos


def _v_counterparty(h, news, defs, issuer):
    """The other side of the property deal: 'to Genesis', 'Optionee', 'with Beta Minerals', 'from Glencore'.
    1.1.1: the party that earns into or acquires the property ('Alpha Ventures Corp. of Calgary will have the right to
    earn 80%', '... by which ABC can acquire up to a 90% interest'); 'to'/'from'/'with' followed by one space (1.1.0
    asked for two); 'to' only in the opening text; a name after 'from'/'with' in the body is a company only with its
    suffix or a defined name ('from the Trans Canada Highway' is not); a headline name ends before a verb ('to Beta
    Mining Generates New Royalty')."""
    if defs.get("optionee"):
        return defs["optionee"]
    for m in re.finditer(r"(?:^|(?<=[\s(,;:]))" + _PARTY + r"(?:\s+of\s+[A-Z][\w\s]{0,30}?)?\s*(?:\([^()]{0,60}\)\s*)*,?\s+"
                         r"(?:will|shall|may|can|could|has|have)\s+(?:have\s+|has\s+|be\s+granted\s+)?(?:the\s+)?(?:(?:right|option)\s+to\s+)?"
                         r"(?:earn|acquire)\s+(?:up\s+to\s+|an?\s+|the\s+|its\s+)?(?:initial\s+|undivided\s+)?(?:\d[\d.]*\s?%|100|all|a\s+100)",
                         news[:2500]):
        n = re.split(r"(?<=[a-z])\.\s+(?=[A-Z])", m.group(1))[-1]
        p = _alias(n, defs, issuer)
        if p and not _same_party(p, issuer or "") and not re.match(r"(?i)(?:the|it|we|company|optionee|purchaser|"
                                                                      r"buyer|vendors?|optionors?|each|this|which|who)\b", n):
            p = _v_ok(p)
            if p:
                return p
    for rx, texts in ((r"(?:sell|sells|selling|sale\s+of|sold|transfer\w*|divest\w*|dispos\w*|options?|optioned)\b[^.]{0,140}?\bto",
                       (h, news[:1500])),
                      (r"\bfrom", (h, news[:1500])), (r"\bwith", (news[:1500],))):
        for t in texts:
            p = _named_after(rx, t, defs, issuer)
            if p and t is h:
                p = re.split(r"\s+(?:Generates?|Acquires?|Sells?|Retains?|Completes?|Closes?|Expands?|Adds?|Receives?|"
                             r"Reports?|Provides?|Announces?|Signs?|Enters?|Grants?)\b", p)[0]
            if p and p != issuer and not re.match(r"(?i)(?:vendors?|optionors?|arm|each|certain|third)\b", p) and \
                    not re.search(r"(?i)\b(?:project|property|claims|shares|interest)\b", p):
                if t is not h and not rx.endswith(r"\bto") and not (
                        p in defs.values() or re.search(re.escape(p) + r"\s*,?\s+" + _SUFFIX + r"\b", t)):
                    continue
                return p
    return None


_V_PROP_H = re.compile(r"\b(?:the\s+)?((?:[A-Z][\w'\u2019\-]*|de|del|la)(?:\s+(?:[A-Z][\w'\u2019\-]*|de|del|la)){0,3}?)\s+"
                       r"(?:(?:Gold|Copper|Silver|Lithium|Uranium|Nickel|Zinc|Graphite|Base\s+Metal|Precious\s+Metal|Gold-Copper|"
                       r"Copper-Gold|Polymetallic|Pegmatite|Group\s+of\s+Lithium)\s+)?(?i:Projects?|Propert(?:y|ies)|Claims|Mine|Deposit|"
                       r"Group|Concessions?|Licen[cs]es?|Tenements?)\b")
_V_PROP_BAD = re.compile(r"(?i)^(?:gold|silver|copper|lithium|uranium|nickel|zinc|base|precious|its|the|a|an|new|two|three|"
                         r"four|five|six|several|remaining|option|acquisition|agreement|sale|sells?|options?|announces|"
                         r"completes|signs|enters|lithium\s+exploration|ontario|quebec|nevada|idaho|arizona|british|"
                         r"canadian|mexican|exploration|mineral|mining|second|first|third|additional|highly|prospective|large|district|"
                         r"undrilled|flagship|acquire|to|advanced|past|historic|strategic|non[\s\-]core|core|remaining|"
                         r"property|project|claims)\b")


_V_PROP_JUNK = re.compile(r"(?i)^(?:these|this|those|such|said|each|both|element|elements|consolidate|unpatented|patented|"
                          r"mining|propert(?:y|ies)['\u2019]?|projects?|claims|compelling|extensive|promising|prolific|significant|"
                          r"exciting)(?:\s|$)")
_P_DESC = set(_METALS) | {"porphyry", "exploration", "vms", "ree", "rare", "earth", "earths", "pgm", "pge", "pges", "gold-bearing",
                          "mineralized", "base", "precious", "metal", "metals", "critical", "mineral", "minerals", "polymetallic",
                          "pegmatite", "sedex", "skarn", "epithermal", "iocg", "magmatic", "sulphide", "sulfide", "co", "cu", "au",
                          "ag", "ni", "zn", "pb", "u", "li", "rees", "moly", "tungsten", "cobalt", "high-grade", "district-scale",
                          "hematite", "iron", "ore", "carbonatite", "au-ag", "ag-au", "cu-au", "au-cu", "vein", "intrusion",
                          "greenstone", "underexplored", "prospective", "hosted", "orogenic"}


def _pclean(name):
    """'Perk-Rocky Copper-Gold Porphyry' -> 'Perk-Rocky'; 'EASTMAIN-LERAN' -> 'Eastmain-Leran'; '2,300-Hectare Waterslide
    Uranium-REE' -> 'Waterslide'; a phrase with a verb or a capitalised preposition in it is no name."""
    w = [x if not x.isupper() or len(x) <= 3 else "-".join(p[:1] + p[1:].lower() for p in x.split("-")) for x in name.split()]
    while w and all(p.lower() in _P_DESC for p in re.split(r"[\-/]", w[-1]) if p):
        w.pop()
    while w and re.match(r"(?i)^(?:[\d,.\-]*hectares?|[\d,.\-]*acres?|km2|km\u00b2|ownership|of|the|royalt\w*|interest|stake|"
                         r"\d[\d,.]*%?|district-scale|high-grade|multiple|newly|acquired|new|two|three|four|several|in|at|on)$", w[0]):
        w.pop(0)
    if "Near" in w:
        w = w[:w.index("Near")]
    out = " ".join(w)
    if re.fullmatch(r"[A-Z]{2,4}|(?i:eight|seven|six|key|package|completion|core|main|north|south|east|west|several|vendors?|"
                    r"optionors?|saskatchewan|manitoba|alberta|yukon|newfoundland|labrador|nunavut|ontario|quebec|nevada|"
                    r"idaho|arizona|utah|montana|alaska|british\s+columbia|mexico|peru|chile|argentina|brazil)", out):
        return None
    if re.search(r"\b(?:FOR|TO|OF|For|To|Rights?|Options?|Acquires?|Announces?|Sells?|Closes?|Completes?)\b", out):
        return None
    return out or None


def _v_property(h, s, news, defs, issuer):
    """1.1.1: the name after the deal verb ('Alpha Options Bravo Gold Project' -> 'Bravo'); never a demonstrative, a
    descriptor or a nationality ('These claims', 'Platinum Group Element Properties', 'Unpatented Mining Claims', 'Ruritanian
    Gold Property'); not a 'Project Portfolio'; a line-broken 'High- Grade' joined; a name a metal word starts ('Gold
    Point') kept."""
    pty = set(PN.key(issuer or "").split())
    for t in (h, s, news[:2500]):
        t = re.sub(r"\b([A-Z][a-z]+)-\s+([A-Z][a-z]+)\b", r"\1-\2", t)
        for m in _V_PROP_H.finditer(t):
            name = re.split(r"['\u2019]s\s+", m.group(1))[-1].strip()
            if re.match(r"\s+Portfolio\b", t[m.end():]):
                continue
            name = re.split(r"\b(?:Options?|Acquires?|Sells?|Sale\s+of|Buys|Purchases?|Acquisition\s+of|Adds|Expands|"
                            r"Announces|Signs|Completes|Closes|Enters|Consolidates?)\s+", name)[-1]
            name = re.sub(r"^(?:(?:Options?|Acquires?|Sells?|Sale\s+of|Buys|Purchases?|Acquisition\s+of|of|the|to|To\s+Acquire)\s+)+", "", name, flags=re.I)
            name = _pclean(name)
            if name and re.fullmatch(r"(?:Gold|Silver|Copper)\s+[A-Z][a-z]+", name) and \
                    not _V_PROP_BAD.match(name.split()[1]) and name.split()[1].lower() not in _P_DESC and \
                    not _V_PROP_JUNK.match(name.split()[1]) and not _pn_is_party(name, pty):
                return name
            if not name or _V_PROP_BAD.match(name) or _pn_is_party(name, pty) or len(name) < 3:
                continue
            if _V_PROP_JUNK.match(name) or re.fullmatch(r"[A-Z][a-z]+(?:ean|ian|ese)", name):
                continue
            return name
    try:
        p = PN.primary(h, news, issuer)
        p = _pn_page(p) if p else None
    except Exception:
        p = None
    return p if p and len(p) >= 4 and not re.fullmatch(r"[A-Z]{2,5}", p) and not _V_PROP_BAD.match(p) else None


def _v_ok(n):
    """A party name, not a clause ('2023; Metal Energy entered into ...') or a bare word ('Exploration', 'Resources Inc.')."""
    n = _ok_party(n)
    if not n:
        return None
    if ";" in n and re.search(r"\b[a-z]{3,}\b", n.split(";")[-1]) and not re.match(r"(?i)the\s+", n):
        return None
    if re.match(r"\d", n) and not re.match(r"\d{5,}\s+(?:Ontario|B\.?C\.?|Canada|Alberta|Quebec)", n):
        return None
    if re.fullmatch(r"(?i)partners?|prospectors?|i\s+nc|owners?|optionee|purchaser|buyer|investor", n):
        return None
    n = re.sub(r"\s+(?:INC|CORP|LTD|Inc|Corp|Ltd)\.?$", "", n)
    if n.isupper() and len(n) > 6:
        n = " ".join(w if len(w) <= 3 and w not in ("CORP", "LTD") else w.title() for w in n.split())
        n = _clean_org(n)
    if len(n.split()) > 7 or re.fullmatch(r"(?i)(?:exploration|resources?|mining|minerals|metals|gold|royalt\w*)(?:\s+" +
                                          _SUFFIX + r"\.?)?", n):
        return None
    return n


def _vendor_rows(h, body, defs, issuer, table):
    """Vendor royalties in a release that announces a property deal (Justin 2026-09-28: every vendor royalty is a row).
    One row per royalty the deal creates or keeps for the seller/optionor: type, rate and metal from the mention; buyer
    = the seller/optionor who holds it; seller field and operator = the party taking the property; no price (the price
    is the property's); buy-back terms go in price_note."""
    if not _V_HEAD.search(h) or not _V_HEAD_OBJ.search(h) or _V_NOT_HEAD.search(h) or _OUT_OF_SCOPE.search(h):
        return []
    news = _mask_orgs(_places(_v_news(body)), set(table), table)
    rows = []
    sents = _sentences(news)
    terms = [x for x in sents if _INTEREST.search(x) and re.search(r"(?i)\b(?:buy[\s\-]?back|repurchas\w*|buy[\s\-]?down|"
                                                                  r"purchase)\b[^.]{0,80}?(?:\d[\d.]*\s?%|half|one[\s\-]half)", x)]
    for s in sents:
        if not _INTEREST.search(s) or re.match(r"(?i)about\s", s) or _PM_COMPANY_DESC.search(s):
            continue
        if not _V_GRANT.search(s) or re.search(r"(?i)\bdilut\w*|\bfall\w*\s+below|\breduced?\s+to\s+(?:less|below)", s):
            continue
        first_sent = rows[0]["_s"] if rows else None
        for (pos, typ, rate, metal) in _interest_mentions(s):
            if typ == "royalty" and rate is None and not re.search(r"(?i)net\s+smelter|NSR|gross|production\s+royalty|"
                                                                  r"royalty\s+of\s+\d", s[max(0, pos - 40):pos + 60]):
                continue
            window = s[max(0, pos - 160):pos + 80]
            if _V_NOT_NEW.search(s[max(0, pos - 90):pos + 40]) or \
                    re.search(r"(?i)(?:buy[\s\-]?back|repurchas\w*|buy[\s\-]?down|purchase|acquire)\s+(?:\S+\s+){0,5}?$", s[max(0, pos - 60):pos]):
                continue          # a buy-back term, or an existing royalty
            if not (_V_GRANT.search(s[max(0, pos - 160):pos + 60]) and
                    (_V_ROLE.search(window) or re.search(r"(?i)\bretain\w*|\bwill\s+be\s+granted|\bgrant\w*\s+(?:to\s+)?"
                                                         r"[A-Z]|\bin\s+favou?r\s+of\s+[A-Z]", window))):
                continue
            if re.search(r"(?i)\bretain\w*\s+(?:a|an|its)?\s*(?:\d[\d.]*\s?%\s+)?(?:interest|right|option|offtake|back[\s\-]in)", window):
                continue
            if typ == "royalty":
                typ = "NSR" if re.search(r"(?i)net\s+smelter|\bNSR", s[pos:pos + 80]) else "other"
            if rate is not None and (rate <= 0 or rate > 15):
                rate = None
            if any(r["type"] == typ and (r["rate_pct"] == rate or rate is None or r["rate_pct"] is None) for r in rows):
                continue
            if rows and s != first_sent:
                continue          # a later sentence restating the royalty or giving its buy-back terms
            holder = _v_holder(s, pos, defs, issuer, news, h)
            other = _v_counterparty(h, news, defs, issuer)
            if holder is None and not re.search(r"(?i)\bsale\s+of\s+(?:a|the|its)\s+(?:\S+\s+){0,3}?royalt", news[:2000]):
                # 1.1.1: nobody named for the royalty -- the side of the property deal says who keeps it: the issuer
                # when it sells or options the property out, the named vendor when it acquires the property
                side = _v_issuer_side(h, news)
                holder = issuer if side == "seller" else other if side == "buyer" else None
            grantor = other if holder and _same_party(holder, issuer) else issuer
            if holder and grantor and _same_party(holder, grantor):
                grantor = None
            prop = _v_property(h, s, news, defs, issuer)
            if not prop and re.search(r"(?i)\b(?:on|over|covering)\s+(?:any|all)\s+(?:new|future)\s+(?:projects|properties|claims)", s):
                prop = "Portfolio: new projects" + (" of " + grantor if grantor else "")     # 'on any new projects organically generated'
            if metal is None:
                mm = re.search(r"(?i)\b(" + "|".join(_METALS) + r")\s+royalt", s[max(0, pos - 30):pos + 30])
                metal = mm.group(1).lower() if mm else None
            note = "vendor royalty: kept by or granted to the seller/optionor in the property deal"
            t = next((x for x in terms if x != s), None) or next((x for x in terms), None)
            if t:
                note += "; " + re.sub(r"\s+", " ", t)[:100]
            rows.append(dict(type=typ, rate_pct=rate, metal=metal, property=_unmask(prop, table),
                             operator=_v_ok(_unmask(grantor, table)), buyer=_v_ok(_unmask(holder, table)),
                             seller=_v_ok(_unmask(grantor, table)), price=None, currency=None, action="new",
                             status=_status(h, s), price_note=note, kind="vendor", _s=s))
    for r in rows:
        r.pop("_s", None)
    return rows[:4]


def _same_party(a, b):
    return bool(a and b and (a == b or a.split()[0].lower() == b.split()[0].lower()))


def _prop_lc(s):
    """'the entire Los Azules copper project': a capitalised name before a lower-case '<metal> project'."""
    m = re.search(r"\b(?:the\s+(?:entire\s+)?)?((?:[A-Z][\w'\u2019\-]*)(?:\s+[A-Z][\w'\u2019\-]*){0,2})\s+(?:(?:" + "|".join(_METALS) +
                  r")(?:[\-\s](?:" + "|".join(_METALS) + r"))*\s+)?(?:project|mine|property|deposit)\b", s)
    return _pclean(m.group(1)) if m and not _V_PROP_BAD.match(m.group(1)) else None


# -- held: a release about a royalty the company already holds (Q12 A)
_HELD_HEAD = re.compile(r"(?i)(?:\b(?:royalt\w*|NSR|stream|GRR|NPI)\b[^.]{0,60}?\b(?:update\w*|notes?|lawsuit|court|appeal|"
                        r"judg\w*|first\s+gold\s+pour|pour|reserves?|resources?|production|growth|progress|advanc\w*)\b|"
                        r"\b(?:update\w*|notes?|lawsuit|court|appeal)\b[^.]{0,60}?\b(?:royalt\w*|NSR|stream|GRR)\b|"
                        r"\blawsuit\b)")
_HELD_NOT = re.compile(r"(?i)\bportfolio\b|\bletter\b|\bdividend|\bpayment|\brevenue|\bfinancing|\bsells?\b|\bsale\b|"
                       r"\bacquires?\b(?!\s+[^.]{0,40}acquisition)|\bbuy|\bgrant|\bamend")
# a deal headline is the deal reader's, never a held row ('Closing of Silver Royalty Option', 'purchases outstanding 2%
# NSR', 'Completes Acquisition of Royalty', 'Partial Disposal', 'CSA Stream Transaction', 'Updates Silver Stream Agreement')
_HELD_DEAL = re.compile(r"(?i)\bclosing\s+of\b|\bcomplet\w*\s+(?:the\s+)?(?:acquisition|sale|purchase|disposal)|\bpurchas\w*|"
                        r"\bdisposal\b|\boption\b|\btransaction\b|\b(?:stream|royalty)\s+agreement\b")
_HELD_VERB = re.compile(r"(?i)\b(?:holds?|owns?|has|retains?|maintains?|entitlement\s+to|ownership\s+of|claim\s+to|interest\s+in)\b")


_HELD_PROP = re.compile(r"(?:([A-Z][\w\-]+)['\u2019]s\s+(?:[A-Z][\w'\u2019\-]*\s+){1,3}|\b([A-Z][\w\-]+)\s+(?:Gold\s+|Silver\s+|Copper\s+)?)"
                        r"Royalty\s+(?:Property|Claims)\b")


def _held_rows(h, body, defs, issuer, table):
    """'TNR Gold NSR Royalty Update - Los Azules ...', 'Royalty Update: First Gold Pour at Moss Mine', '... Lawsuit for 2%
    NSR on Cozamin Mine', 'Notes Continued Growth at Royalty Assets with ... Laverton ...': a 'held' row for each
    royalty the news says the company holds (at most three; more is a portfolio update). When the headline names
    properties, only those."""
    hu = _unmask(h, table)          # 1.1.1: a masked company name ('... and Alpha Royalties') hides the headline's word
    if not (_HELD_HEAD.search(hu) or _HELD_PROP.search(hu)) or \
            _HELD_NOT.search(re.sub(r"(?i)\b\w+\s+acquisition\b", "", hu)):
        return []
    if _OUT_OF_SCOPE.search(h) or _HELD_DEAL.search(h):
        return []
    news = _mask_orgs(_places(_v_news(body, 16000)), set(table), table)
    me = [w for w in re.findall(r"[A-Z][\w\-]+", issuer or "")[:2]]
    # 1.1.1: the name the release defines for the Company ('("Alpha" or the "Company")') when the issuer's name came
    # out garbled
    al = re.search(r"\(\s*[" + Q + r"]\s*([A-Z][^" + Q + r"]{1,30}?)\s*[" + Q + r"]\s*(?:,|or)\s*(?:the\s+)?[" + Q + r"]\s*Company\s*[" + Q + r"]",
                   body[:4000] if body else "")
    if al and al.group(1).split()[0] not in me:
        me = [al.group(1).split()[0]] + me
        issuer = al.group(1) if not issuer or al.group(1).split()[0] not in issuer else issuer
    subj = r"(?:the\s+Company|Company|It|We|" + "|".join(re.escape(w) for w in me) + r")" if me else r"(?:the\s+Company|Company)"
    rows, seen, last_prop = [], set(), None
    for s in _sentences(news):
        p0 = _property(s, defs)
        if p0:
            last_prop = p0
        if not _INTEREST.search(s) or not (_HELD_VERB.search(s) or re.search(r"['\u2019]s\s+(?:[\w%.\-]+\s+){0,3}?" + _INT_W, s)) \
                or re.match(r"(?i)about\s", s):
            continue
        if not (re.search(subj + r"[^.]{0,40}?" + _HELD_VERB.pattern.replace("(?i)", ""), s, re.I) or
                re.search(r"(?i)(?:entitlement|ownership|claim)\s+(?:of|to)\s+(?:a|an|the)\s+\d", s) or
                re.search(subj + r"['\u2019]s\s+(?:[\w%.\-]+\s+){0,3}?" + _INT_W + r"\b", s, re.I)):      # 1.1.1: "the Company's 2% NSR"
            continue
        ments = _interest_mentions(s)
        for (pos, typ, rate, metal) in ments:
            if typ == "royalty" and rate is None and not re.search(r"(?i)per\s+ounce|production\s+royalty", s):
                continue
            if typ == "royalty" and any(t != "royalty" and r2 == rate for (_, t, r2, _) in ments):
                continue        # 'a 0.36% royalty on the net smelter return ("NSR") royalty' is an NSR
            if typ == "royalty":
                typ = "other"
            prop = _property(s[pos:], defs) or _property(s, defs) or _prop_lc(s[pos:]) or last_prop
            if not prop:
                continue
            k = _norm_key(prop)
            if k in seen:
                continue
            seen.add(k)
            sub = re.search(r"\bsubsidiary,?\s+((?:[A-Z][\w&'\u2019.\-]*)(?:\s+(?:[A-Z][\w&'\u2019.\-]*|de|del|la|y)){0,5})", s)
            holder = _ok_party(issuer)
            if holder and sub and not _same_party(_clean_org(sub.group(1)), holder):
                holder = "%s (%s)" % (holder, _clean_org(sub.group(1)))           # "'s 88% subsidiary Minera Portree de Zacatecas"
            rows.append(dict(type=typ, rate_pct=rate if rate is None or 0 < rate <= (100 if typ in ("stream", "NPI") else 15) else None,
                             metal=metal, property=_unmask(prop, table), operator=_ok_party(_unmask(_operator(s, news, defs, issuer, prop), table)),
                             buyer=holder, seller=None, price=None, currency=None, action="held", status=None,
                             price_note="a royalty the company already holds", kind="held"))
    # a royalty company's section headers: 'Laverton (2% Gross Revenue Royalty)', 'Hercules (A$10/oz Royalty plus ...)'
    for m in re.finditer(r"\b([A-Z][\w'\u2019\-]+(?:\s+[A-Z][\w'\u2019\-]+){0,2})\s+\(\s*(?:(\d[\d.]*)\s?%\s+)?(?:[A-Z]{0,2}\$\s?\d[\d.]*\s*/\s*oz\s+)?"
                         r"(Gross\s+Revenue\s+Royalty|Net\s+Smelter\s+Returns?\s+Royalty|NSR|GRR|Royalty|Stream)\b", body or ""):
        name = m.group(1)
        if not re.search(_pn_rx(name), h, re.I) or _norm_key(name) in seen:
            continue
        seen.add(_norm_key(name))
        t = m.group(3).lower()
        typ = "GRR" if t.startswith("gross") or t == "grr" else "NSR" if t.startswith("net") or t == "nsr" else \
            "stream" if t == "stream" else "other"
        rate = float(m.group(2)) if m.group(2) else None
        rows.append(dict(type=typ, rate_pct=rate if rate is None or 0 < rate <= 15 or typ == "stream" else None, metal=None,
                         property=name, operator=None, buyer=_ok_party(issuer), seller=None, price=None, currency=None,
                         action="held", status=None, price_note="a royalty the company already holds", kind="held"))
    if not rows:
        m = re.search(r"(?i)royalty\s+update\W+[^.]{0,80}?\b(?:at|on)\s+(?:the\s+)?([A-Z][\w'\u2019\-]*(?:\s+[A-Z][\w'\u2019\-]*){0,3})\s+"
                      r"(Mine|Project|Property)\b", h)
        if m:
            metal = "gold" if re.search(r"(?i)\bgold\b", h) else None
            rows.append(dict(type="other", rate_pct=None, metal=metal, property=m.group(1), operator=None,
                             buyer=_ok_party(issuer), seller=None, price=None, currency=None, action="held",
                             status=None, price_note="a royalty the company already holds", kind="held"))
    # 1.1.1: 'Bravo Royalty Property' is the Bravo property; the holder's own name is no property ('Alpha Gold Royalty
    # Property'); the holder does not operate it
    hw = set(PN.key(issuer or "").split())
    for r in rows:
        r["property"] = re.sub(r"\s+Royalty$", "", r["property"])
        if r.get("operator") and _same_party(r["operator"], r.get("buyer")):
            r["operator"] = None
    rows = [r for r in rows if not (set(PN.key(r["property"]).split()) & hw)]
    # Q12 A: only a royalty the headline names; a portfolio or asset update ('Royalty Assets', 'Royalties Update')
    # names none and gets no row
    named = [r for r in rows if re.search(_pn_rx(r["property"].split(" (")[0]), h, re.I)]
    # a lawsuit over one royalty ('Update on Capstone Lawsuit') names the party, not the property
    if not named:
        # 'Updates on Copper & Lithium Royalties': the royalties on the metals the headline names
        mh = re.search(r"(?i)\b((?:" + "|".join(_METALS) + r")(?:\s*(?:,|&|and)\s*(?:" + "|".join(_METALS) + r"))*)\s+(?:royalt|NSR|stream)", h)
        if mh:
            want = {x.lower() for x in re.findall(r"(?i)" + "|".join(_METALS), mh.group(1))}
            named = [r for r in _metal_fill(rows, h, body) if r.get("metal") and set(r["metal"].split(", ")) & want]
    rows = named or (rows if len(rows) == 1 and re.search(r"(?i)\blawsuit|\bcourt\b|\bappeal|\bjudg", h) else [])
    for r in rows:      # the headline's own word for the metal ('Ganfeng's Mariana Lithium')
        m = re.search(_pn_rx(r["property"].split(" (")[0]) + r"\s+(" + "|".join(_METALS) + r")\b", h, re.I)
        if m:
            r["metal"] = m.group(1).lower()
    for r in rows:      # 1.1.1: the company whose property it is
        if not r.get("operator"):
            r["operator"] = _held_operator(r["property"], r.get("buyer"), h, body, table)
    return rows if len(rows) <= 3 else []


_HO_ORG = r"((?:[A-Z][\w&'\u2019.\-]*\s+){0,3}?[A-Z][\w&'\u2019.\-]*?)"


def _held_operator(prop, holder, h, body, table):
    """1.1.1: the company whose property carries a royalty the issuer holds: "Alpha Mining's Bravo project", "the Bravo
    concession within Alpha Silver Corp.'s Charlie mine", "Alpha Resources Inc. ... has published a ... Report as
    regards the Bravo Property", "Alpha Mining Corp. publicly announced drill results ... of its wholly-owned Bravo
    property"."""
    if not prop:
        return None
    t = _unmask(" ".join((h or "").split()), table) + " . " + " ".join((body or "")[:4000].split())
    p = _pn_rx(prop.split(" (")[0])
    cands = []
    for m in re.finditer(_HO_ORG + r"(?:\s*,?\s+" + _SUFFIX + r")?\.?['\u2019]s?\s+(?:\([^()]{0,40}\)\s*)*(?:[\w\-%]+\s+){0,3}?" + p, t):
        cands.append(m.group(1))
    for m in re.finditer(p + r"[^.]{0,80}?\b(?:part\s+of|within)\s+" + _HO_ORG + r"(?:\s*,?\s+" + _SUFFIX + r")?\.?['\u2019]s?\s", t):
        cands.append(m.group(1))
    for m in re.finditer(_HO_ORG + r"(?:\s*,?\s+" + _SUFFIX + r")?\.?\s*(?:\([^()]{0,60}\)\s*)*(?:has\s+|have\s+)?(?:publicly\s+|today\s+)?"
                         r"(?:announced|reported|published|provided|released|approved)\b[^.]{0,160}?" + p, t):
        cands.append(m.group(1))
    for c in cands:
        c = _clean_org(re.sub(r"^(?:on|at|in|of|the|and|that|within)\s+", "", c, flags=re.I))
        if not c or (holder and _same_party(c, holder)) or re.match(r"(?i)(?:the|its|our|their|this|company)\b", c) \
                or PN.same(c, prop) or not _ok_party(c) or len(c.split()) > 4:
            continue
        return c
    return None


# -- results releases: closings and changes reported inside them (Q5)
_R_CLOSE = re.compile(r"(?i)\b(?:closed|completed|closing\s+of|completion\s+of)\b")
_R_CHANGE = re.compile(r"(?i)\b(?:binding\s+agreement|agreed\s+to\s+(?:extend|amend)|to\s+extend|to\s+restructure|restructur\w+|"
                       r"amend\w*)\b")


def _results_rows(h, body, defs, issuer, table, issuer_royco):
    news = _mask_orgs(_places(_v_news(body)), set(table), table)
    rows, seen = [], set()
    for s in _sentences(news):
        if not _INTEREST.search(s) or re.match(r"(?i)about\s", s):
            continue
        closing, change = _R_CLOSE.search(s), _R_CHANGE.search(s)
        if not (closing or change):
            continue
        clauses = re.split(r";\s+|,\s+and\s+(?=entered|closed|completed)|:\s+(?=[A-Z])", s)
        close_ctx = False
        for c in clauses:
            close_ctx = close_ctx or bool(_R_CLOSE.search(c))
            chg = _R_CHANGE.search(c)
            if not _INTEREST.search(c) or re.search(r"(?i)revenue|dividend|share\s+repurchase|normal\s+course|\boil\b|\bgas\b|"
                                                    r"thermal|renewable|\benergy\b|\bwind\b|\bsolar\b", c):
                continue
            if not (close_ctx or chg):
                continue
            ments = [x for x in _interest_mentions(c) if x[1] != "royalty"] or _interest_mentions(c)
            if not ments:
                continue
            _p, typ, rate, metal = ments[0]
            typ = "other" if typ == "royalty" else typ
            prop = None
            pf = re.search(r"(?i)portfolio\s+of\s+(?:\w+\s+){0,2}royalties[^.]{0,120}?\banchored\s+by\s+[^.]{0,80}?\bon\s+"
                           r"(?:[^.]{0,60}?['\u2019]s\s+)?(?:producing\s+)?([A-Z][\w'\u2019\-]*(?:\s+[A-Z][\w'\u2019\-]*){0,2})", c)
            if pf:
                prop = "Portfolio: " + pf.group(1)
            if not prop:
                m = re.search(r"(?i)\b(?:covering|cover|on)\s+(?:the\s+)?(?:[^.]{0,40}?['\u2019]s\s+)?((?-i:[A-Z])[\w'\u2019\-]*(?:\s+(?-i:[A-Z])[\w'\u2019\-]*){0,2})\s+"
                              r"(?:Gold\s+|Copper\s+|Silver\s+)?(?:project|Project|Mine|mine|Property|property)", c)
                prop = m.group(1) if m else None
            if not prop:
                m = re.search(r"(?:million|\d)\s+((?:[A-Z][\w'\u2019\-]*\s+){1,3})(?:precious\s+metals?\s+|gold\s+|silver\s+)?stream", c)
                prop = m.group(1).strip() if m else None
            prop = _pclean(prop) if prop and not prop.startswith("Portfolio") else prop
            if not prop or _V_PROP_BAD.match(prop):
                continue
            k = (typ, _norm_key(prop).split(" ")[0])
            if k in seen:
                continue
            seen.add(k)
            amts = list(re.finditer(r"\(\s*" + _MONEY + r"\s*\)", c)) or \
                list(re.finditer(r"(?i)(?:for|of|payment\s+of|consideration\s+of)\s+(?:cash\s+)?" + _MONEY, c)) or \
                list(re.finditer(r"(?i)" + _MONEY + r"\s+(?:\w+\s+){0,4}?(?:stream|royalt)", c))
            price, cur = (_money(amts[0], _default_currency(body or "")) if amts else (None, None))
            if chg and not _R_CLOSE.search(c):
                action, status = "amendment", "agreed"
                other = _named_after(r"with", c, defs, issuer)
                buyer, seller = (issuer, other) if issuer_royco else (other, issuer)
            else:
                status = "closed"
                frm = _named_after(r"from", c, defs, issuer)
                wth = _named_after(r"with", c, defs, issuer)
                if typ == "stream" and wth:
                    action, buyer, seller = "new", issuer, wth
                elif re.search(r"(?i)\bholder\s+of\b", c):
                    m = re.match(r"\s*((?:[A-Z][\w&'\u2019.\-]*\s+){0,4}[A-Z][\w&'\u2019.\-]*)", c)
                    action, buyer, seller = "transfer", issuer, (_clean_org(m.group(1)) + " shareholders") if m else None
                elif issuer_royco:
                    action, buyer, seller = "transfer", issuer, frm
                else:
                    action, buyer, seller = "transfer", frm, issuer
            op = _operator(c, news, defs, issuer, prop)
            if not op and typ == "stream" and seller:
                op = seller
            rows.append(dict(type=typ, rate_pct=rate if prop and not prop.startswith("Portfolio") else None, metal=metal,
                             property=_unmask(prop, table), operator=_ok_party(_unmask(op, table)),
                             buyer=_ok_party(_unmask(buyer, table)), seller=_ok_party(_unmask(seller, table)),
                             price=price if price and price >= 1000 else None,
                             currency=cur if price and price >= 1000 else None, action=action, status=status,
                             price_note="reported in a results release", kind="deal"))
    return rows[:6]


# -- a settlement that changes how a royalty is calculated (Q8)
def _settlement_rows(h, body, defs, issuer, table):
    if not re.search(r"(?i)\bsettle\w*\b", h) or not _INTEREST.search(h):
        return []
    news = _mask_orgs(_places(_v_news(body)), set(table), table)
    if not re.search(r"(?i)\bnew\s+(?:method|formula|basis)\b|\bamend\w*\b|\bcalculat\w+\b", news[:3000]):
        return []
    typed = [x for s in _sentences(news[:4000]) for x in _interest_mentions(s) if x[1] != "royalty" and x[2] is not None]
    if not typed:
        return []
    _p, typ, rate, metal = typed[0]
    m = re.search(r"\bon\s+(?:the\s+)?([A-Z][\w\-]*(?:['\u2019]s)?(?:\s+[A-Z][\w'\u2019\-]*){0,2}?)\s+(?:NSR|GRR|Royalt|royalt|Stream|stream)", h)
    prop = (m.group(1) if m else None) or _property(h, defs) or _property(news[:2000], defs)
    other = _named_after(r"with", h, defs, issuer) or _named_after(r"with", news[:1500], defs, issuer)
    if other and prop and _norm_key(other) == _norm_key(prop):
        other = None
    return [dict(type=typ, rate_pct=rate, metal=metal, property=_unmask(prop, table), operator=_ok_party(other),
                 buyer=_ok_party(issuer), seller=_ok_party(other), price=None, currency=None, action="amendment",
                 status="agreed", price_note="settlement: the royalty's calculation changes", kind="deal")]


# -- a second royalty in a deal release: a replacement (Q9) or another holder's royalty bought back (Q10)
def _extra_rows(rows, h, body, defs, issuer, table):
    if len(rows) != 1:
        return rows
    base = rows[0]
    news = _mask_orgs(_places(_v_news(body)), set(table), table)
    out = list(rows)
    m = re.search(r"(?i)\b(?:newly[\s\-]granted|replac\w+\s+(?:it\s+)?(?:with|by)|leaving\s+in\s+place)\s+(?:a|an)?\s*"
                  r"(\d{1,2}(?:\.\d{1,3})?)\s?%\s+(?:net\s+smelter\s+)?(royalt\w*|NSR)", news)
    if m and base.get("action") == "buyback":
        out.append(dict(base, rate_pct=float(m.group(1)), buyer=None, seller=base.get("buyer"), action="amendment",
                        price=None, currency=None, price_note="the royalty that replaces the one bought back"))
        return out
    if base.get("action") == "new" and base.get("seller") and base.get("seller") == issuer:
        for s in _sentences(news):
            mm = re.search(r"(?i)\b(?:buy\s+back|buy[\s\-]?back|repurchase|option\s+to\s+(?:purchase|acquire|buy)|to\s+acquire)\s+"
                           r"(?:the\s+|an?\s+|its\s+)?(?:existing\s+)?(?:(\d{1,2}(?:\.\d{1,3})?)\s?%\s+)?(?:\w+\s+){0,3}?"
                           r"(NSR|net\s+smelter\s+returns?\s+royalty|royalt(?:y|ies))\b[^.]{0,80}?(?:\bheld\s+by|\bfrom|\bowned\s+by)\s+"
                           r"((?:[A-Z][\w&'\u2019.\-]*\s*){1,4})", s)
            if mm:
                rate = float(mm.group(1)) if mm.group(1) else None
                if rate is not None and abs(rate - (base.get("rate_pct") or -1)) < 1e-9 and not re.search(r"(?i)existing", s):
                    continue
                out.append(dict(base, rate_pct=rate, buyer=issuer, seller=_ok_party(_alias(mm.group(3).strip(), defs, issuer)),
                                action="buyback", price=None, currency=None, status=base.get("status"),
                                price_note="another holder's royalty bought back in the same deal"))
                break
    return out


# -- metal from the property's own description ('the Cariboo Gold Project', 'Kenbridge Nickel Project')
def _metal_fill(rows, h, body):
    t = (h or "") + " " + " ".join((body or "")[:6000].split())
    mh = re.search(r"(?i)\b(" + "|".join(_METALS) + r")\s+(?:stream|royalt\w*|NSR)\b", h or "")
    for r in rows:
        if r.get("metal"):
            continue
        if mh and len(rows) == 1:      # 'Additional Gibraltar Silver Stream Interest'
            r["metal"] = mh.group(1).lower()
            continue
        if not r.get("property") or r.get("property", "").startswith("Portfolio"):
            continue
        p = _pn_rx(r["property"].split(" (")[0])
        m = re.search(p + r"\s+(?:[A-Z][\w\-]+\s+)?((?:" + "|".join(_METALS) + r")(?:\s*(?:-|and|&|/)\s*(?:" + "|".join(_METALS) +
                      r"))?)\s+(?:project|mine|property|deposit|operations?)\b", t, re.I)
        if m:
            ms = [x.lower() for x in re.findall(r"(?i)" + "|".join(_METALS), m.group(1))]
            r["metal"] = ", ".join(dict.fromkeys(ms))
    return rows


def _money_more(text, cur0):
    """1.1 prices the reader missed: 'US$24 million for a 2.9% NSR', 'total price of US$14 million', 'gross proceeds of
    C$5,000,000', 'USD $4.85 million', '$500,000 USD'."""
    pats = (r"(?i)" + _MONEY + r"\s+(?:in\s+cash\s+)?for\s+(?:a|an|the)\s+(?:\d[\d.]*\s?%\s+)?(?:\w+\s+){0,3}?(?:NSR|royalt|stream|GRR|net\s+smelter)",
            r"(?i)\b(?:total|aggregate)\s+(?:cash\s+)?(?:purchase\s+)?price\s+of\s+(?:approximately\s+)?" + _MONEY,
            r"(?i)\b(?:gross\s+proceeds|upfront\s+cash\s+(?:consideration|payment|deposit)|cash\s+consideration|total\s+consideration)\s+"
            r"(?:of\s+)?(?:approximately\s+)?" + _MONEY,
            r"(?i)\bfor\s+the\s+(?:aggregate|total)\s+(?:cash\s+)?(?:purchase\s+price|consideration)\s+of\s+" + _MONEY)
    for p in pats:
        m = re.search(p, text)
        if m:
            v, c = _money(m, cur0)
            if v >= 1000:
                return v, c
    m = re.search(r"(?i)\bUSD\s*\$\s?(\d[\d,]*(?:\.\d+)?)\s*(million|billion|M)?\b", text)
    if m:
        v = float(m.group(1).replace(",", "")) * {"million": 1e6, "m": 1e6, "billion": 1e9}.get((m.group(2) or "").lower(), 1)
        if v >= 1000:
            return v, "USD"
    return None, None


def _currency_suffix(text, price):
    """'$500,000 USD': a currency written after the figure."""
    if price is None:
        return None
    m = re.search(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(million|M)?\s+(USD|CAD|AUD|US\s+dollars)\b", text)
    if m:
        v = float(m.group(1).replace(",", "")) * (1e6 if m.group(2) else 1)
        if abs(v - price) <= 0.01 * price:
            return {"USD": "USD", "CAD": "CAD", "AUD": "AUD"}.get(m.group(3), "USD")
    return None


# ------------------------------------------------------------------ the reader
def _context(headline, body):
    """What every 1.1 path needs from a release: the prepared headline and body, defined terms, the issuer, and the
    masking table for company names that contain Royalty/Streaming."""
    h, b = _prepare(headline, body)
    title = _title(h)
    b = _drop_title(b, title)
    defs, def_orgs = _definitions(b[:12000])
    issuer = _issuer(title, b)
    roy_orgs = _royalty_orgs(h + " " + b[:12000]) | {n for n in def_orgs if n and re.search(r"(?i)royalt|stream", n)}
    # a bare name, or metals + Royalties ('Lithium Royalties'), is a company only with its suffix ('Gold Royalty Corp.')
    roy_orgs = {n for n in roy_orgs if (len(n.split()) > 1 and not re.fullmatch(
                    r"(?i)(?:(?:" + "|".join(_METALS) + r"|precious\s+metals?|base\s+metals?)\s*(?:&|and|,)?\s*)+(?:royalt\w*|streams?)", n))
                or re.search(r"(?i)royalt|stream", n) is None or
                re.search(r"(?i)" + re.escape(n) + r"\s+(?:" + _SUFFIX + r")\b", h + " " + b[:3000])}
    table = {}
    tm = _mask_orgs(title, roy_orgs, table)
    royco = bool(issuer and (re.search(r"(?i)royalt|stream", issuer) or re.search(
        r"(?i)\babout\s+" + re.escape(issuer.split()[0]) + r"\b[^.]{0,200}?" + _ROYCO.pattern.replace("(?i)", ""), b)))
    return dict(h=h, b=b, title=title, tm=tm, defs=defs, issuer=issuer, table=table, royco=royco)


_V_BODY = re.compile(r"(?i)net\s+smelter|\bNSR\b|\broyalt|\bGRR\b|\bstream")


_R_HEAD = re.compile(r"(?i)\b(?:Q[1-4]|quarter|year[\s\-]+end|annual|fiscal|first\s+half|half[\s\-]+year|full[\s\-]+year)\b[^.]{0,80}?"
                     r"\b(?:results|reports?|revenues?|earnings|financial|highlights|update)\b|\b(?:reports?|results)\b[^.]{0,80}?"
                     r"\b(?:Q[1-4]|quarter|year[\s\-]+end|annual|fiscal)\b")
_HELD_FIRST = re.compile(r"(?i)\b(?:notes|royalty\s+update|NSR\s+royalty\s+update|updates\s+on\b[^.]{0,40}royalt)")


def analyse(headline, body):
    """1.1: the 1.0.3 deal reader first (_analyse_deal), then Justin's 2026-09-28 rows -- vendor royalties, held
    royalties, closings and changes inside results releases, settlements, and a second royalty in a deal release."""
    hd = " ".join((headline or "").split())
    a = _analyse_deal(headline, body)
    rows = [dict(r) for r in a["rows"]]
    head_body = _V_BODY.search((body or "")[:_V_NEWS_CHARS])
    held_first = bool(_HELD_HEAD.search(hd) and _HELD_FIRST.search(hd))
    want_vendor = bool(not rows and _V_HEAD.search(hd) and _V_HEAD_OBJ.search(hd) and not _V_NOT_HEAD.search(hd) and head_body)
    want_held = bool((not rows or held_first) and (_HELD_HEAD.search(hd) or _HELD_PROP.search(hd)))
    want_settle = bool(not rows and re.search(r"(?i)\bsettle", hd) and _INTEREST.search(hd))
    want_results = bool(not rows and head_body and (_R_HEAD.search(hd) or
                                                    re.search(r"(?i)binding\s+agreement[^.]{0,80}?(?:stream|royalt)", hd)))
    if not (rows or want_vendor or want_held or want_settle or want_results):
        return a
    c = _context(headline, body)
    ttl, defs, issuer, table = c["tm"], c["defs"], c["issuer"], c["table"]
    issuer = _issuer11(issuer, hd, c["b"])
    reason = a["reason"]
    ttl = _uncaps(ttl)
    if want_held:
        hp = _HELD_PROP.search(hd)      # 1.1.1: "on Alpha's Bravo Royalty Property": Alpha holds it
        held = _held_rows(ttl, body, defs, (hp.group(1) or hp.group(2)) if hp and not _HELD_HEAD.search(hd) else issuer, table)
        if held:
            return {"rows": _metal_fill(held, headline, body), "reason": "held royalty", "issuer": issuer}
    if rows:
        rows = _extra_rows(rows, ttl, body, defs, issuer, table)
        rows = [_deal_fix(r, c, issuer, hd, body) for r in rows]
    else:
        if want_settle:
            rows = _settlement_rows(ttl, body, defs, issuer, table)
            reason = "settlement" if rows else reason
        if not rows and want_results:
            rows = _results_rows(ttl, body, defs, issuer, table, c["royco"])
            reason = "reported in a results release" if rows else reason
        if not rows and want_vendor:
            rows = _vendor_rows(ttl, body, defs, issuer, table)
            reason = "vendor royalty" if rows else reason
    rows = _metal_fill(rows, headline, body)
    rows = [_current_names(r, body) for r in rows]
    for r in rows:
        if r.get("property") and re.search(r"Zorg", r["property"]):
            r["property"] = _unmask(r["property"], table)
    return {"rows": rows, "reason": reason, "issuer": a.get("issuer") or issuer}


def _issuer11(issuer, hd, b):
    """The 1.0.3 issuer, or for the 1.1 paths the company a headline in capitals or a dateline names ('ALTIUS REPORTS
    ...', 'Altius Minerals Corporation ("Altius") today announces')."""
    if issuer and re.fullmatch(r"(?i)royalties|royalty|streaming|mining|minerals|resources|gold|metals", issuer):
        m = re.search(re.escape(issuer) + r"\s+(?:" + _SUFFIX + r")\.?", b[:1500])
        if m:
            return m.group(0)
        issuer = None
    if issuer and not re.match(r"(?i)newsfile|globe|pr\s+newswire|accesswire", issuer):
        return issuer
    m = re.search(r"((?:(?:[A-Z][\w&'\u2019.\-]*|&)\s+){0,4}[A-Z][\w&'\u2019.\-]*\s*,?\s+" + _SUFFIX + r")\.?\s*\(\s*(?:[" + Q +
                  r"]|(?:TSX|TSXV|TSX-V|TSX\s+Venture|CSE|NYSE|NASDAQ|ASX|LSE|AIM|OTC\w*)\b)", b[:1500])
    if m:
        return _org11(m.group(1))
    m = re.match(r"((?:[A-Z][\w&'\u2019.\-]*\s+){0,3}?)(?:REPORTS|ANNOUNCES|COMPLETES|CLOSES|ACQUIRES|Reports|Announces|Notes|"
                 r"Updates|Royalty\s+Update|NSR)\b", hd)
    if m and m.group(1).strip():
        return _clean_org(m.group(1).title() if m.group(1).isupper() else m.group(1))
    return issuer


_SMALL = {"on", "with", "of", "the", "and", "to", "for", "in", "at", "a", "an", "from", "by", "over", "its", "into"}


def _uncaps(h):
    """'ALTIUS REPORTS SETTLEMENT WITH VALE ON VOISEY'S BAY ROYALTY DISPUTE' -> 'Altius Reports Settlement with Vale on
    Voisey's Bay Royalty Dispute'; the interest words (NSR, GRR, NPI) and tickers stay in capitals. Mixed case is
    left alone."""
    letters = [ch for ch in h if ch.isalpha()]
    if not letters or sum(ch.isupper() for ch in letters) < 0.8 * len(letters):
        return h
    def one(m):
        w = m.group(0)
        if w in ("NSR", "GRR", "NPI", "NSRs", "TSX", "TSXV", "CSE", "NYSE", "US", "CEO", "PEA", "DFS", "PFS") or re.match(r"Zorg", w):
            return w
        if w.lower() in _SMALL and m.start() > 0:
            return w.lower()
        return "-".join(p[:1].upper() + p[1:].lower() for p in w.split("-"))
    out = re.sub(r"[^\W\d_](?:[^\W\d_]|-)*(?:['\u2019][^\W\d_]+)?", one, h)
    return re.sub(r"(['\u2019])S\b", r"\1s", out)


def _current_names(r, body):
    """A party the release names by its old name: 'Elemental Royalty Corporation (previously operating as EMX Royalty
    Corporation ("Elemental"))' -> Elemental Royalty, not EMX Royalty."""
    for f in ("buyer", "seller", "operator"):
        v = r.get(f)
        if not v or ";" in v:
            continue
        m = re.search(r"((?:[A-Z][\w&'\u2019.\-]*\s+){0,4}?[A-Z][\w&'\u2019.\-]*(?:\s+" + _SUFFIX + r")?)\.?\s*\(\s*(?:previously\s+operating\s+as|"
                      r"formerly(?:\s+known\s+as)?|previously\s+known\s+as)\s+" + re.escape(v.split(" (")[0]), body or "")
        if m:
            r = dict(r)
            r[f] = _clean_org(m.group(1))
    return r


def _org11(s):
    """A dateline name: what follows a place ('Longueuil, Quebec. Highland Copper Company Inc.'), and the full name
    when the bare name is one generic word ('Royalties Inc.')."""
    s = re.split(r"\.\s+(?=[A-Z])", " ".join(s.split()))[-1]
    c = _clean_org(s)
    if re.fullmatch(r"(?i)royalties|royalty|streaming|mining|minerals|resources|gold|metals", c or ""):
        return s.rstrip(" ,")
    return c


_ROYNAME = (r"(?i)royalt|streaming|\bwheaton\b|\bfranco|\bosisko\s+gold|\bsandstorm|\btriple\s+flag|\bmetalla|\bmaverix|"
            r"\bsprott\s+(?:resource\s+)?(?:streaming|lending|private)|\bappian\b|\borion\s+(?:mine|resource)|\bnebari\b|"
            r"\belemental\b|\bvox\b|\becora\b|\baltius\b|\bemx\b|\bempress\b|\bsailfish\b|\bversamet\b|\bdeterra\b|"
            r"\bresource\s+capital\s+fund|\bla\s+mancha\b|\bocean\s+partners\b|\btaurus\b|\blunr\b")


def _own_property(r, issuer, hd, b):
    """The buyer buys a royalty on its own property: it exercises a right to, the headline says buy back / buy down /
    buy out, or the release calls the row's property its own ('its Ladner Gold Project', "Chakana's Soledad")."""
    if re.search(r"(?i)\bbuy(?:s|ing)?[\s\-]?(?:back|down|out)\b|\bbuy[\s\-]?(?:back|down|out)\b", hd):
        return True
    t = hd + " " + b[:3000]
    me = re.escape(issuer.split()[0]) if issuer else "(?!)"
    if re.search(r"(?i)\b(?:the\s+Company|" + me + r")\b[^.]{0,60}?\bexercis\w*\s+(?:its\s+)?(?:right|option)\s+to\s+"
                 r"(?:acquire|purchase|buy)", t):
        return True
    if not r.get("property") or re.search(r"(?i)\breceiv\w*|\bretain\w*|\bpayment\b", hd) or \
            re.search(r"(?i)\bfor\s+the\s+sale\s+of\b|\breceived\s+(?:gross\s+)?proceeds\b", b[:2000]):
        return False
    p = _pn_rx(r["property"].split(" (")[0])
    m = re.search(r"\b([A-Z][\w\-]*)(?:\s+[A-Z][\w\-]*){0,2}['\u2019]s\s+(?:\w+\s+){0,3}?" + p, hd, re.I)
    if m and not re.match(me, m.group(1), re.I):
        return False            # "on Monarch Mining's Beaufor Mine": another company's property
    w = r"(?:(?!royalt|interest|stream|nsr|gross|net\b)(?:\w|[\-/])+\s+)"      # 'its existing royalty on X' is not X
    return bool(re.search(r"(?i)\b(?:its|the\s+Company['\u2019]s|our|" + me + r"['\u2019]s)\s+" + w + r"{0,4}?" + p, t) or
                re.search(r"(?i)" + p + r"[^.]{0,80}?\b(?:owned|held)\s+(?:\w+\s+){0,2}by\s+(?:the\s+Company|" + me + r")", t))


def _deal_fix(r, c, issuer, hd, body):
    """1.1 fixes on a 1.0.3 deal row: the action when the property's owner is a party, a price the deal names in
    another shape, a currency written after the figure, a per-share figure that is no price."""
    r = dict(r)
    b = c["b"]
    if r.get("price") is not None and r["price"] < 1000:
        r["price"], r["currency"] = None, None
    if r.get("price") is None:
        text = " ".join(s for s in _sentences(b[:6000]) if _INTEREST.search(s))
        v, cur = _money_more(text, _default_currency(b))
        if v:
            r["price"], r["currency"] = v, cur
    cur2 = _currency_suffix(b[:6000], r.get("price"))
    if cur2:
        r["currency"] = cur2
    if re.search(r"(?i)\b(?:royalty|stream)\s+financing\b", hd) and r.get("seller") == issuer and r.get("action") == "transfer":
        r["action"] = "new"
    royco = c["royco"] or bool(re.search(r"(?i)\b(?:royalty|streaming|stream)(?:\s+and\s+(?:royalty|streaming|stream))?\s+"
                                         r"(?:company|corporation|business)\b|\bprecious\s+metals?\s+streaming\b", b[:4000]) or
                               (issuer and re.search(re.escape(issuer) + r"\s+(?:Royalt|Streaming)", b[:4000])))
    if r.get("action") == "transfer" and r.get("buyer") and r.get("buyer") == issuer and not royco and \
            not re.search(r"(?i)\bgross\s+proceeds|\bfinancing\b|\bsale\b|\bsells?\b|\bgrants?\b", hd) and _own_property(r, issuer, hd, b):
        r["action"] = "buyback"
    if r.get("action") == "transfer" and r.get("seller") and r.get("property") and \
            not re.search(r"(?i)\b(?:acquir\w*|purchas\w*|buy\w*)\s+(?:an?\s+|the\s+|its\s+)?existing\b", hd + " " + b[:1500]):
        own = r["seller"].split()[0]
        if re.search(re.escape(own) + r"[\w\s.,]{0,40}?['\u2019]s\s+(?:\w+\s+){0,3}" + _pn_rx(r["property"].split(" (")[0]), hd + " " + b[:3000], re.I) or \
                re.search(re.escape(own) + r"[^.]{0,120}?\b(?:wholly[\s\-]owned|100%[\s\-]owned)\s+(?:\w+\s+){0,3}?" +
                          _pn_rx(r["property"].split(" (")[0]), b[:3000], re.I):
            r["action"] = "new"
            r["operator"] = r.get("operator") or r["seller"]
    # the royalty or stream company is the one that buys: 'Rio2 ... Gold Stream with Wheaton', 'Franco-Nevada ... Stream
    # with Sibanye-Stillwater'
    for f in ("buyer", "seller", "operator"):
        if r.get(f):
            r[f] = re.sub(r"(?<=[a-z])(?:TM|\u2122|\u00ae)$", "", r[f])
    if r.get("action") == "new" and r.get("seller") and r.get("buyer") and re.search(_ROYNAME, r["seller"]) and \
            not re.search(_ROYNAME, r["buyer"]) and \
            not re.search(r"(?i)\bsells?\b|\bsale\b|\bsold\b|\bterminat\w*|\bdispos\w*|\bmonetiz\w*", hd):
        other = _named_after(r"with", hd, c["defs"], r["seller"])
        r["buyer"], r["seller"] = r["seller"], (other if other and other != r["seller"] else r.get("buyer"))
    # what the headline itself states: 'Announces $20 Million Royalty with Wheaton ... on Mt Todd'
    if r.get("price") is None:
        m = re.search(r"(?i)" + _MONEY + r"\s+(?:\w+\s+){0,2}?" + _INT_W + r"\b", hd)
        if m:
            v, cur = _money(m, _default_currency(b))
            if v >= 1000:
                r["price"], r["currency"] = v, cur
    if not r.get("property"):
        m = re.search(r"(?i)" + _INT_W + r"\b.{0,100}?\b(?-i:on)\s+(?:the\s+|its\s+)?([A-Z][\w'\u2019\-]*(?:\s+[A-Z][\w'\u2019\-]*){0,2})\s*$", hd)
        if m and not _BAD_PARTY.search(m.group(1)) and not re.match(
                r"(?i)(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|may|june|july|"
                r"august|september|october|november|december|behalf|closing|completion|signing)\b", m.group(1)):
            r["property"] = m.group(1)
    if r.get("type") == "other" and r.get("rate_pct") is None:
        m = re.search(r"(?i)\broyalty\s+(?:in\s+the\s+amount\s+of|at\s+a\s+rate\s+of|equal\s+to)\s+(\d{1,2}(?:\.\d{1,3})?)\s?%\s+of\s+"
                      r"(?:the\s+)?(gross\s+revenue|net\s+smelter)", b[:4000])
        if m:
            r["type"], r["rate_pct"] = ("GRR" if m.group(2).lower().startswith("gross") else "NSR"), float(m.group(1))
    if r.get("type") == "other" and r.get("rate_pct") is None:
        for s in _sentences(b[:4000]):
            ms = [x for x in _interest_mentions(s) if x[1] != "royalty" and x[2] is not None]
            if ms:
                r["type"], r["rate_pct"] = ms[0][1], ms[0][2]
                break
    return r


def _analyse_deal(headline, body):
    if not (_INTEREST.search(headline or "") or _H_FIN.search(headline or "")):
        return {"rows": [], "reason": "no royalty or stream deal in the headline"}     # the fast path: most releases
    h, b = _prepare(headline, body)
    title = _title(h)
    b = _drop_title(b, title)
    defs, def_orgs = _definitions(b[:12000])
    issuer = _issuer(title, b)
    roy_orgs = _royalty_orgs(h + " " + b[:12000]) | {n for n in def_orgs if n and re.search(r"(?i)royalt|stream", n)}
    roy_orgs = {n for n in roy_orgs if len(n.split()) > 1 or re.search(r"(?i)royalt|stream", n) is None or
                re.search(r"(?i)" + re.escape(n) + r"\s+(?:" + _SUFFIX + r")\b", h + " " + b[:3000])}
    table = {}
    tm, bm = _mask_orgs(title, roy_orgs, table), _mask_orgs(b, roy_orgs, table)
    ok, reason = _in_scope(tm, bm[:1500])
    if not ok:
        return {"rows": [], "reason": reason}
    sents = _sentences(bm[:8000])
    D = None
    if reason == "headline financing":
        # the release is a financing, a spin-out or a transaction: one of its opening sentences has to say it is
        # a stream or royalty (Franco-Nevada's '$100 million gold stream financing transaction with Orezone')
        for s in sents[:3]:
            if _LINK.search(s) and not re.search(r"(?i)\bretain\w*\b", s):
                D = s
                break
        if D is None:
            return {"rows": [], "reason": "financing or transaction without a stream or royalty"}
    else:
        for s in sents:
            if _INTEREST.search(s) and _DEAL.search(s) and not re.match(r"(?i)about\s", s) and \
                    not re.search(r"Zorg\w*\s+(?:is|was)\s+an?\s", s):
                D = s
                break
    if D is None:
        return {"rows": [], "reason": "no deal sentence"}
    di = sents.index(D)
    ctx = " ".join(sents[di:di + 3])
    if _OUT_OF_SCOPE.search(D):
        return {"rows": [], "reason": "oil and gas or non-mining"}
    U = lambda v: _ok_party(_unmask(v, table))     # noqa: E731
    issuer_royco = bool(issuer and (re.search(r"(?i)royalt|stream", issuer) or re.search(
        r"(?i)\babout\s+" + re.escape(issuer.split()[0]) + r"\b[^.]{0,200}?" + _ROYCO.pattern.replace("(?i)", ""), b)))
    # the interest: the most specific typed mention in the deal sentence, the headline, then the next sentences
    ments = _interest_mentions(D) + _interest_mentions(tm) + _interest_mentions(ctx)
    typed = [x for x in ments if x[1] != "royalty"]
    if not typed:
        typed = [x for x in _interest_mentions(bm[:4000]) if x[1] in ("NSR", "GRR", "NPI")][:1]
    if typed:
        typ = typed[0][1]
    elif ments:
        typ = "other"
    else:
        return {"rows": [], "reason": "no interest named"}
    rate = next((x[2] for x in typed if x[2] is not None and x[1] == typ), None)
    if rate is None:
        rate = next((x[2] for x in ments if x[2] is not None and x[1] == "royalty"), None)
    metal = next((x[3] for x in ments if x[3] and x[1] == typ), None)
    if typ == "stream" and rate is None:
        r2, m2 = _stream_rate(b)
        rate, metal = r2, metal or m2
    # a royalty over 15% is a share of one ('50% of the NSR'), not a rate; a stream or NPI can reach 100%
    if rate is not None and (rate <= 0 or rate > (100 if typ in ("stream", "NPI") else 15)):
        rate = None
    if metal is None:
        mm = re.search(r"(?i)\bon\s+(" + "|".join(_METALS) + r")(?:\s+and\s+(" + "|".join(_METALS) + r"))?\s+production", ctx)
        if mm:
            metal = mm.group(1).lower() + (", " + mm.group(2).lower() if mm.group(2) else "")
        elif re.search(r"(?i)covering\s+all\s+minerals", ctx):
            metal = "all minerals"
    prop = _property(D, defs) or _property(tm, defs) or _property(ctx, defs)
    buyer, seller = _parties(D, defs, issuer, issuer_royco, ctx)
    buyer, seller = _ok_party(buyer), _ok_party(seller)
    operator = _ok_party(_operator(D, b, defs, issuer, prop) or _operator(ctx, b, defs, issuer, prop))
    hd = tm + " " + D
    buy_back = re.search(r"(?i)\b(?:repurchas\w*|reacquir\w*|buys?[\s\-]?backs?|buying\s+back|buy[\s\-]?downs?)\b(?!\s+(?:of\s+)?(?:its\s+)?"
                         r"(?:common\s+)?shares?)|\bunderlying\s+(?:\w+\s+){0,4}(?:royalt|NSR|net\s+smelter)", hd)
    if buy_back and re.search(r"(?i)\bshare\s+(?:re)?purchase|\bshare\s+buy", hd) and not re.search(
            r"(?i)(?:repurchas\w*|buys?[\s\-]?back|buy[\s\-]?down)\w*\s+(?:\S+\s+){0,5}?(?:royalt|NSR|net\s+smelter|stream)", hd):
        buy_back = None
    sell_title = re.search(r"(?i)\b(?:sale|sells?|sold|purchas\w*|acquir\w*|acquisition|buy|buys|bought)\b", tm)
    if (re.search(r"(?i)\b(?:amend\w*|restructur\w*|extension|extend\w*|expands?\s+(?:\w+\s+){0,2}agreement)\b", tm) or
            (re.search(r"(?i)\bamend\w*[^.]{0,80}\b(?:royalt\w*|stream\w*|NSR)\b", D) and not sell_title)) and \
            not re.search(r"(?i)\bsale\s+of\s+(?:an?\s+)?option|\boption\s+to\s+(?:buy|acquire)", hd) and not buy_back:
        action = "amendment"
        if not buyer or buyer == issuer:
            buyer = _ok_party(_named_after(r"with", hd, defs, issuer)) or buyer
        if buyer == issuer:
            buyer = None
        seller = issuer
        operator = operator or issuer
    elif buy_back or (buyer and operator and buyer == operator) or \
            (buyer == issuer and re.search(r"(?i)\b(?:on|over)\s+(?:its|the\s+Company['\u2019]s)\s+", hd)) or \
            re.search(r"(?i)\boption\s+to\s+(?:buy|acquire)[^.]{0,60}\bheld\s+by\s+the\s+Company", D):
        action = "buyback"
        # 'Abcourt Exercises Option to Buy-Back 0.5% NSR': the company whose headline it is buys it back
        if buy_back and seller == issuer and buyer != issuer and \
                re.search(r"(?i)\b(?:repurchas\w*|reacquir\w*|buys?[\s\-]?backs?|buy[\s\-]?back)\b", tm) and \
                not re.search(r"(?i)\bsale\s+of\s+(?:an?\s+)?option|\bsells?\s+(?:an?\s+)?option", tm):
            buyer, seller = issuer, buyer
        operator = operator or buyer
        buyer = buyer or operator
    elif seller and ((issuer_royco and seller == issuer) or re.search(r"(?i)royalt|stream", seller) or
                     re.search(r"(?i)\b(?:its|an\s+existing)\s+(?:\S+\s+){0,3}?(?:\d[\d.]*\s?%\s+)?(?:NSR|net\s+smelter|"
                               r"royalt\w*|stream|gross)", tm + " " + D) or
                     re.search(r"(?i)\b(?:held\s+by|currently\s+being|under\s+option)\b", D) or
                     re.search(r"(?i)\bnon[\s\-]core\s+(?:\S+\s+){0,2}?(?:royalt|NSR|stream)", tm)):
        action = "transfer"
    elif (seller and operator and seller == operator) or \
            re.search(r"(?i)\b(?:grant\w*|creat\w*|spin\s*-?\s*out|(?:stream|royalty)\s+financing|financing\s+transaction)\b", D) or \
            (typ in ("stream", "NPI") and not re.search(r"(?i)\bexisting\b", D)) or seller == issuer:
        action = "new"
        operator = operator or seller
        seller = seller or operator
    else:
        action = "transfer"
    def _same(a, c):
        return bool(a and c and (a == c or a.split()[0].lower() == c.split()[0].lower()))
    if _same(buyer, seller):
        # the same company on both sides: keep it where the release puts its own name -- a royalty company buys
        if issuer_royco or action in ("transfer", "buyback"):
            seller = None
        else:
            buyer = None
    # a property is not a party ('Eskay Creek' read as the seller of the Eskay Creek stream)
    pl = (prop or "").lower()
    buyer, seller, operator = [None if (v and v.lower() == pl) else v for v in (buyer, seller, operator)]
    price, cur = _price(tm, D + " " + " ".join(sents[di + 1:di + 3]), b, _default_currency(b))
    status = _status(tm, D)
    base = dict(type=typ, rate_pct=rate, metal=metal, property=_unmask(prop, table), operator=U(operator), buyer=U(buyer),
                seller=U(seller), price=price, currency=cur if price is not None else None, action=action,
                status=status, price_note=None)
    rows = [base]
    # two properties in one deal sentence ('royalties on the Lunahuasi and Los Helados Projects')
    two = re.search(r"\bon\s+the\s+([A-Z][\w'\u2019\-]*(?:\s+[A-Z][\w'\u2019\-]*){0,3})\s+and\s+([A-Z][\w'\u2019\-]*(?:\s+[A-Z][\w'\u2019\-]*){0,3})\s+"
                    r"(?:Projects|Mines|Properties)\b", D)
    if two:
        rows = []
        for p in (two.group(1), two.group(2)):
            rm = re.search(r"(\d{1,2}(?:\.\d{1,3})?)\s?%\s+(?:NSR|net\s+smelter)[^.]{0,40}?\bon\s+(?:the\s+)?" + _ADJ + re.escape(p), b)
            rows.append(dict(base, property=p, rate_pct=float(rm.group(1)) if rm else None, price=None, currency=None))
    for r in rows:
        for k in ("buyer", "seller", "operator"):
            if r[k] and re.search(r"Zorg", r[k]):
                r[k] = None
    rows = _property_pn(rows, headline, body, issuer)   # 1.0.1
    rows = _property_multi(rows, headline, body, issuer)   # 1.0.3
    return {"rows": rows, "reason": reason, "issuer": issuer}


# ------------------------------------------------------------------ facts store
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["rows"]:
        return [F.Record(KIND, facts=[F.Fact("is_royalty", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"])], confidence=0.0)]
    out = []
    for r in a["rows"]:
        fs = [F.Fact("is_royalty", value_num=1.0)]
        for k in TXT_FIELDS:
            if r.get(k):
                fs.append(F.Fact(k, value_text=str(r[k])[:160]))
        for k in NUM_FIELDS:
            if r.get(k) is not None:
                fs.append(F.Fact(k, value_num=float(r[k])))
        out.append(F.Record(KIND, facts=fs, confidence=1.0))
    return out


def parse_records(rows_by_ordinal):
    """{ordinal: [(field, seq, value_num, value_text)]} -> the analyse()-shaped dict."""
    rows = []
    for ordinal in sorted(rows_by_ordinal):
        r = {k: None for k in TXT_FIELDS + NUM_FIELDS}
        yes = False
        for field_, seq, num, text in rows_by_ordinal[ordinal]:
            if field_ == "is_royalty":
                yes = num == 1.0
            elif field_ in NUM_FIELDS:
                r[field_] = num
            elif field_ in TXT_FIELDS:
                r[field_] = text
        if yes and r["type"]:
            rows.append(r)
    return {"is_royalty": bool(rows), "rows": rows}


JUDGED = TXT_FIELDS + NUM_FIELDS


def to_prediction(records):
    if not records:
        return None
    rows = {i: [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts] for i, rec in enumerate(records)}
    p = parse_records(rows)
    if not p["rows"]:
        return None
    return {"rows": [{k: r.get(k) for k in JUDGED} for r in p["rows"]]}


def _code_sha():
    # 1.0.2: this file whole, plus exactly the helper code this reader runs (portal/fingerprint.py): a helper
    # change to that code still bumps the version; an addition it does not call does not
    return FP.code_sha(__file__)


SPEC = F.ExtractorSpec(NAME, VERSION, KIND, TAG, extract, _code_sha())


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

    def one(h, b=""):
        r = analyse(h, b)["rows"]
        return r[0] if r else None

    # SPA.V b9406ab2e61b -- a developer sells a new NSR on its own project: 'new', the buyer from 'pursuant to which'
    r = one("Spanish Mountain Gold Announces Sale of a 1.5% Royalty to Wheaton Precious Metals for US$55 Million",
            "Spanish Mountain Gold Ltd. (the \u201cCompany\u201d or \u201cSpanish Mountain Gold\u201d) (TSX-V: SPA) is pleased to "
            "announce that it has entered into a royalty agreement (the \u201cRoyalty Agreement\u201d) with Wheaton Precious "
            "Metals Corp. (\u201cWheaton\u201d), pursuant to which Wheaton will acquire a 1.5% net smelter returns royalty "
            "(\u201cNSR\u201d) on gold and silver production from the Spanish Mountain Gold Project (the \u201cProject\u201d) for "
            "aggregate cash proceeds of US$55 million, to be paid in three installments.")
    eq("SPA", (r["type"], r["rate_pct"], r["buyer"], r["seller"], r["action"], r["price"], r["currency"]),
       ("NSR", 1.5, "Wheaton Precious Metals", "Spanish Mountain Gold", "new", 55e6, "USD"))
    # GGO.V aa4e94b6f360 -- a buyback: the operator reacquires its royalty from Newmont
    r = one("Galleon Gold Enters into Agreement to Repurchase Royalty on the West Cache Project",
            "Galleon Gold Corp. (TSXV: GGO) (the \" Company \" or \" Galleon Gold \") is pleased to announce it has entered "
            "into an agreement (the \" Agreement \") with a wholly-owned subsidiary of Newmont Corporation (\" Newmont \"), "
            "to reacquire a 3% net smelter return royalty (the \" Royalty \") on the Company's West Cache Gold Project "
            "located in Timmins, Ontario.")
    eq("GGO", (r["type"], r["rate_pct"], r["property"], r["buyer"], r["seller"], r["action"]),
       ("NSR", 3.0, "West Cache", "Galleon Gold", "Newmont", "buyback"))
    # FNV.TO 3071f862b32f -- an existing royalty bought from Altius: 'transfer', operator from the possessive
    r = one("Franco-Nevada Announces Acquisition of 1.0% NSR on AngloGold\u2019s Arthur Gold Project in Nevada",
            "Franco-Nevada Corporation (\u201cFranco-Nevada\u201d or the \u201cCompany\u201d) (TSX & NYSE:FNV) is pleased to "
            "announce that its wholly-owned subsidiary has acquired an existing 1.0% net smelter return royalty (the "
            "\u201cRoyalty\u201d) on AngloGold Ashanti plc\u2019s (\u201cAngloGold\u201d) Arthur Gold Project from Altius Minerals "
            "Corporation (\u201cAltius\u201d) for $250 million in cash.")
    eq("FNV Arthur", (r["type"], r["rate_pct"], r["buyer"], r["seller"], r["action"], r["status"]),
       ("NSR", 1.0, "Franco-Nevada", "Altius Minerals", "transfer", "closed"))
    # a royalty company's name is not a royalty (VMET.TO 15833a041d39)
    eq("royalty company's financing", one("Versamet Royalties Closes C$142 Million Bought Deal Financing",
                                          "Versamet Royalties Corporation (\u201cVersamet\u201d or the \u201cCompany\u201d) is pleased to "
                                          "announce that it has closed its previously announced bought deal public offering."), None)
    # royalty income, a lawsuit, oil and gas, music: not rows
    eq("royalty payment", one("NEWPORT RECEIVES AUD$385,012 QUARTERLY ROYALTY PAYMENT"), None)
    eq("results", one("Royalties Inc. Reports Q3 Results and Success on Capstone Copper Lawsuit for 2% NSR on Cozamin Mine"), None)
    eq("oil and gas", one("Wedgemount Resources Sells Royalty on Permian Basin Assets",
                          "Wedgemount announces an agreement to sell up to a five percent Overriding Royalty Interest in its "
                          "west central Texas oil and gas assets."), None)
    # 1.1 (Justin 2026-09-28): every vendor royalty is a row -- held by the vendor, granted by the buyer of the property
    r = one("XCITE RESOURCES INC CLOSES ACQUISITION OF TURGEON LAKE PROPERTY",
            "Under the Agreement Xcite granted Bullion a 2% net smelter returns royalty on the Property.")
    eq("vendor NSR", (r or {}).get("kind") and (r["type"], r["rate_pct"], r["buyer"], r["seller"], r["action"], r["kind"]),
       ("NSR", 2.0, "Bullion", "Xcite Resources", "new", "vendor"))
    # the facts-store round trip
    back = to_prediction(extract("Hemlo Explorers Announces Sale of Hawkins Gold Royalty",
                                 "Hemlo Explorers Inc. (the \u201cCompany\u201d) (TSXV: HMLO) announced today the sale of its 0.5% net "
                                 "smelter return (\u201cNSR\u201d) royalty on the Hawkins Gold Project, currently being explored under "
                                 "option by E2Gold Inc., to Vox Royalty Corp. (NASDAQ: VOXR, TSX: VOXR) for gross cash proceeds of "
                                 "C$100,000."))
    eq("round trip", [(x["type"], x["rate_pct"], x["property"], x["operator"], x["buyer"], x["seller"], x["action"], x["price"])
                      for x in back["rows"]],
       [("NSR", 0.5, "Hawkins", "E2Gold", "Vox Royalty", "Hemlo Explorers", "transfer", 100000.0)])
    # 1.0.1: the shared helper
    got = [_pn_page(n) for n in ("Norway Based Rana Nickel-Copper-Cobalt", "Tin-Tantalum Mine",
                                 "Kirkland West and Omega Projects", "Sibanye Stillwater 18 Million Ounce Limpopo PGM Project",
                                 "Two Jamaican Properties", "Kanowna Belle Mill", "Cascabel Copper-Gold Project")]
    eq("101 helper names in this page's form", got, ["Rana", None, None, None, None, None, "Cascabel"])
    got = [_pn_tied_head("Tug", "WEST KIRKLAND MINING BUYS 1.1% NSR ROYALTY AT HASBROUCK IN EXCHANGE FOR TUG PROJECT INTERESTS"),
           _pn_tied_head("Birch Lake", "BIRCH LAKE PROPERTY RETURNED TO PELANGIO AND PELANGIO ACQUIRES NET SMELTER ROYALTY ON "
                                       "ADJOINING PROPERTY"),
           _pn_tied_head("Cascabel", "OSISKO TO ACQUIRE ROYALTY ON SOLGOLD\u2019S CASCABEL PROJECT"),
           _pn_tied_head("Fosterville", "Metalla Completes Fosterville Mine Royalty Acquisition"),
           _pn_tied_head("Voisey\u2019s Bay", "WHEATON PRECIOUS METALS ACQUIRES COBALT STREAM FROM VALE\u2019S VOISEY\u2019S BAY MINE")]
    eq("102 the headline ties the name to the interest", got, [False, False, True, True, True])
    eq("103 the opening text ties it", [_pn_tied_body("Pebble", "Northern Dynasty announces that it has entered into an "
                                                      "amended royalty agreement on the Pebble Project in Alaska."),
                                       _pn_tied_body("Birch Lake", "Pelangio acquires a net smelter royalty on the property "
                                                     "adjoining the Birch Lake Property."),
                                       _pn_tied_body("Mactung", "Elemental Altus completed the Mactung and Cantung royalty "
                                                     "acquisition. It holds a 1.0% royalty on the Mactung project."),
                                       _pn_tied_body("San Albino", "Sailfish is a precious metals royalty and streaming company. "
                                                     "Within Sailfish's portfolio are three main assets: a gold stream on "
                                                     "the San Albino gold mine.")], [True, False, False, False])
    eq("104 respelled or replaced", [_pn_fix_own("Platreef\u2019s", "Platreef\u2019s stream on the Platreef Project", lambda: None),
                                      _pn_fix_own("Company\u2019s", "the Company\u2019s properties", lambda: None),
                                      _pn_fix_own("Montcalm Ni Cu Co", "Montcalm Ni Cu Co Project", lambda: None),
                                      _pn_fix_own("Historic Haukiaho", "the Historic Haukiaho Deposit", lambda: None),
                                      _pn_fix_own("Bay", "Voisey\u2019s Bay Mine", lambda: "Voisey\u2019s Bay")],
       ["Platreef", None, "Montcalm", "Haukiaho", "Voisey\u2019s Bay"])
    r = one("Metalla Acquires Royalty on the Clarence Stream Project",
            "Metalla Royalty & Streaming Ltd. (the \u201cCompany\u201d) announces that it has acquired a 1.0% net smelter return "
            "royalty on the Clarence Stream Project from Galway Metals Inc. for C$1 million.")
    eq("105 a place named Stream keeps its name", (r or {}).get("property"), "Clarence Stream")
    eq("106 the fingerprint covers the helper", "FP" in _code_sha.__code__.co_names and FP.borrowed_source(PN, "PN", __file__).split("\n")[0] != "uses ", True)
    # 1.0.3: several properties per release (helper 1.0.5)
    rr = analyse("Vox Royalty Enters into Binding Agreements to Acquire the Saxby Gold Royalty and the Uley Graphite Royalty",
                 "Vox Royalty Corp. (\"Vox\") is pleased to announce that it has entered into binding agreements to "
                 "acquire a 1.0% net smelter return royalty on the Saxby Gold Project and a 1.5% gross revenue royalty on "
                 "the Uley Graphite Project from a private vendor for A$1,000,000.")["rows"]
    eq("107 two tied properties -> a row each", [(x["property"], x["rate_pct"], x["price"]) for x in rr],
       [("Saxby", 1.0, 1000000.0), ("Uley", 1.5, None)])
    rr = analyse("Barrick Agrees to Sell Royalty Portfolio to Maverix Metals",
                 "Barrick Gold Corporation announced today that it has agreed to sell a portfolio of 22 royalties to "
                 "Maverix Metals Inc. The portfolio includes a 1% net smelter return royalty on the Eskay Creek Project, "
                 "a royalty on the Pinson Mine and a royalty on the Hasbrouck Project.")["rows"]
    eq("108 a portfolio -> one row listing the properties", [x["property"] for x in rr],
       ["Portfolio: Eskay Creek, Pinson, Hasbrouck"])
    r = one("Metalla Acquires Royalty on the Clarence Stream Project",
            "Metalla Royalty & Streaming Ltd. announces that it has acquired a 1.0% net smelter return royalty on the "
            "Clarence Stream Project and holds a royalty on the Fifteen Mile Stream Project.")
    eq("109 a named property is never split", (r or {}).get("property"), "Clarence Stream")
    eq("110 listing length", len(_pm_listing(["Alpha Beta Gamma %d" % i for i in range(30)])) <= 160, True)
    rr = analyse("Northgate Graphite Restructures Stream with Sprout Streaming",
                 "Northgate Graphite Corporation (TSXV: NGX) announces an amendment to the streaming agreement in "
                 "respect of the Company's Alpha project to remove the production cap, such that the streaming agreement "
                 "will now cover all future production from the Alpha project. The Company will pay in full all amounts "
                 "owing on the Sprout Streaming royalty in respect of the Company's Beta mine in the amount of US$4.4 "
                 "million. The Company is also advancing the restart of the Beta mine and the Alpha project.")["rows"]
    eq("111 a property mentioned without a rate or the headline is not a row", len(rr) <= 1, True)
    eq("112 generic listed names are not properties", [_pm_junk(x) for x in ("Operator Operator Stock Exchange Listing",
       "Exciting Development", "Development", "Eskay Creek")], [True, True, True, False])
    eq("113 a company is not a property", (_pm_company("Cameco", "a stream held by Cameco Corporation on the mine"),
       _pm_company("Orion", "acquired from Orion Mine Finance"), _pm_company("Omega", "royalties on Omega")),
       (True, True, False))
    eq("114 a property inside another is one property", (_pm_nested("Eagle", "Dublin Gulch",
       "the Eagle Gold Mine located on the Dublin Gulch property"), _pm_nested("Kirkland West", "Omega",
       "1.5% royalties on both Kirkland West and Omega")), (True, False))
    eq("114b hosts / comprising / in, not 'and ... on'", (_pm_nested("Eagle", "Dublin Gulch", "a 5% NSR royalty on the Dublin Gulch property "
       "(the \u201cProperty\u201d) which hosts the Eagle Gold project"), _pm_nested("Silverstone", "Panuco-Copala",
       "on certain concessions (the \" Silverstone Concessions \") comprising the Panuco-Copala Silver-Gold Project"),
       _pm_nested("Trixie", "Tintic", "A METALS STREAM ON THE HIGH-GRADE TRIXIE MINE IN UTAH\u2019S HISTORIC TINTIC MINING "
       "DISTRICT"), _pm_nested("El Realito", "Orion", "Metalla Completes Acquisition of Royalty on Agnico Eagle's El Realito "
       "Property and Adds Royalty on Minera Frisco's Orion Project From Alamos Gold")), (True, True, True, False))
    eq("116 one-name portfolio only on a portfolio headline", (bool(_PM_PF_HEAD.search("Altius Retains 0.5% NSR interest "
       "as Long-Term Portfolio Component")), bool(_PM_PF_HEAD.search("Barrick Agrees to Sell Royalty Portfolio")),
       bool(_PM_PF_HEAD.search("FALCO AGREES TO SELL A PORTFOLIO OF NET SMELTER RETURN ROYALTIES"))), (False, True, True))
    eq("115 an abbreviation is not a second property", _pm_names(["Altan Tsagaan Ovoo Project", "ATO Project"], set()),
       ["Altan Tsagaan Ovoo"])
    eq("117 a neighbour of the royalty is not listed", _pm_tied("Horne 5", "Falco Agrees to Sell a Portfolio of Royalties",
       "The Royalties relate to properties known as Flavrian and Central Camp which are exploration properties "
       "surrounding the main Horne 5 properties."), False)
    eq("117b a reference point anywhere is not listed", _pm_tied("Horne 5", "Vox to Acquire Canadian Royalty Portfolio",
       "royalty rights in proximity to the Horne 5 Gold Project. Falco plans to use these royalty-linked concessions as a "
       "tailings site for the Horne 5 Project."), False)
    eq("118 bare abbreviations are not listed", _pm_names(["SP Property", "Beaudoin Property", "SG Property"], set()),
       ["Beaudoin"])
    # ---- 1.1
    rr = analyse("TNR Gold Updates on Copper & Lithium Royalties and Shotgun Gold Project",
                 "TNR Gold Corp. (TSX-V: TNR) reports on its holdings. Los Azules Copper Project NSR Royalty Holding. The "
                 "Company holds a 0.36% royalty on the net smelter return (\u201cNSR\u201d) royalty of the entire Los "
                 "Azules copper project in Argentina. TNR retains a 1.8% NSR "
                 "royalty on the Mariana Lithium Project in Argentina.")["rows"]
    eq("119 held rows on a '<metal> Royalties' headline", [(x["type"], x["rate_pct"], x["property"], x["metal"], x["action"])
                                                           for x in rr],
       [("NSR", 0.36, "Los Azules", "copper", "held"), ("NSR", 1.8, "Mariana", "lithium", "held")])
    rr = analyse("Vox Royalty Provides Development Updates on Gold Royalty Assets",
                 "Vox Royalty Corp. holds a 1% NSR royalty on the Kal East project and a 2.5% NSR royalty on the Otto Bore project.")
    eq("120 a portfolio update names no royalty: no held row", rr["rows"], [])
    r = one("Highland Copper Announces Closing of Silver Royalty Option and Update on White Pine Acquisition",
            "Highland Copper Company Inc. holds the Copperwood project and has an NSR royalty on it.")
    eq("121 a deal headline is never a held row", (r or {}).get("action") != "held", True)
    r = one("ALTIUS REPORTS SETTLEMENT WITH VALE ON VOISEY\u2019S BAY ROYALTY DISPUTE",
            "Altius Minerals Corporation (TSX: ALS) reports that it has reached a settlement with Vale. Under the "
            "settlement the 3% net smelter return royalty will be calculated under a new method.")
    eq("122 a settlement that changes the calculation", (r or {}).get("action") and (r["type"], r["rate_pct"], r["property"],
       r["buyer"], r["seller"], r["action"]), ("NSR", 3.0, "Voisey\u2019s Bay", "Altius Minerals", "Vale", "amendment"))
    r = one("Vista Gold Corp. Announces $20 Million Royalty with Wheaton Precious Metals Corp. on Mt Todd",
            "Vista Gold Corp. (NYSE American: VGZ) announces a royalty agreement with Wheaton Precious Metals Corp. "
            "(\u201cWheaton\u201d). Vista Australia granted Wheaton a royalty in the amount of 1% of gross revenue from "
            "the Project.")
    eq("123 headline price and property, the rate from 'in the amount of'", (r or {}).get("type") and (r["type"], r["rate_pct"],
       r["property"], r["price"], r["buyer"], r["action"]), ("GRR", 1.0, "Mt Todd", 20e6, "Wheaton Precious Metals", "new"))
    eq("124 all-caps headlines read in title case", _uncaps("FOCUS GRAPHITE SELLS ITS INTEREST IN THE EASTMAIN-L\u00c9RAN PROJECT"),
       "Focus Graphite Sells its Interest in the Eastmain-L\u00e9ran Project")
    eq("125 descriptors are not part of the name", [_pclean(x) for x in ("Perk-Rocky Copper-Gold Porphyry", "Knife Lake VMS",
       "2,300-Hectare Waterslide Uranium-REE", "FOR Rights TO Gold-Bearing", "BLM")],
       ["Perk-Rocky", "Knife Lake", "Waterslide", None, None])
    eq("126 'OR Royalties' is a party", _ok_party("OR Royalties"), "OR Royalties")
    eq("127 a clause is no party", (_v_ok("2023; Metal Energy entered into a Purchase Agreement with an arms length vendor"),
       _v_ok("Exploration"), _v_ok("1544230 Ontario")), (None, None, "1544230 Ontario"))
    r = one("Triple Flag Acquires 2.75% NSR Royalty on Monarch Mining\u2019s Beaufor Mine in Quebec",
            "Triple Flag Precious Metals Corp. announces that it has acquired a 2.75% NSR royalty on the Beaufor Mine from "
            "a private holder for US$5 million. Monarch continues to prepare its past-producing Beaufor Mine for restart.")
    eq("128 a royalty on another company's mine is no buyback", (r or {}).get("action"), "transfer")
    # ---- 1.1.1 (FIX5)
    def rows(h, b):
        return [(x["type"], x["rate_pct"], x["property"], x["operator"], x["buyer"], x["seller"], x["action"])
                for x in analyse(h, b)["rows"]]
    eq("129 the issuer options the property out 'to X' and keeps the royalty",
       rows("Alpha Resources Options Bravo Property to Charlie Metals",
            "Alpha Resources Corp. (the \"Company\") is pleased to announce that it has entered into an option agreement "
            "with Charlie Metals Inc. (\"Charlie\"). Charlie can acquire a 100% interest in the Bravo Property. Upon "
            "exercise of the option, Alpha will retain a 2% net smelter returns royalty on the Property."),
       [("NSR", 2.0, "Bravo", "Charlie Metals", "Alpha", "Charlie Metals", "new")])
    eq("130 a name after 'from' without a suffix is no company", _v_counterparty(
        "Delta Acquires Echo Property", "The Company acquired the Echo Property from the Trans Canada Highway area "
        "vendors.", {}, "Delta Gold"), None)
    eq("131 the holder after the royalty: 'NSR to the vendors', 'will be granted to X'", [rows(h, b)[0][4] for h, b in (
        ("Delta Gold Acquires Echo Property", "Delta Gold Corp. (the \"Company\") announces that it has acquired the "
         "Echo Property. To acquire the property the Company will issue 1,000,000 shares, pay $20,000 and grant a 2.5% "
         "NSR to the vendors, of which 1% can be purchased for $1,000,000."),
        ("Delta Gold Signs Agreement to Acquire Option on Echo Gold Project", "Delta Gold Corp. (the \"Company\") "
         "announces a definitive agreement to acquire an option on the Echo Gold Project. NSR Royalty: If Delta acquires "
         "100% ownership of the Project, a 0.5% NSR royalty will be granted to Foxtrot."))], ["the vendors", "Foxtrot"])
    eq("132 the property after the deal verb; a nationality or a demonstrative is none",
       (_v_property("Alpha Options Bravo Gold Project", "", "", {}, "Alpha Resources"),
        _v_property("Alpha Acquires Ruritanian Gold Property", "These claims are subject to a royalty.", "", {},
                    "Alpha Resources")), ("Bravo", None))
    eq("133 a held royalty on '<Holder>\u2019s <Name> Royalty Property', with the property's company",
       rows("Echo Continues Drilling on Alpha\u2019s Bravo Royalty Property",
            "Echo Continues Drilling on Alpha\u2019s Bravo Royalty Property. Alpha Mining Enterprises Inc. is pleased to "
            "inform shareholders that Echo Resources Inc. has published a new resource report as regards the Bravo "
            "Property. Alpha retains a 3% Gross Metal Royalty on all mineral production from the property."),
       [("GRR", 3.0, "Bravo", "Echo Resources", "Alpha", None, "held")])
    eq("136 the party that earns in is the other side",
       rows("Alpha Resources Announces Earn-In Agreement on its Bravo Project", "Alpha Resources Corp. (the "
            "\"Company\") announces an agreement on its Bravo Project. Charlie Metals Ltd. will have the right to earn up "
            "to 80% of the Bravo Project by spending $1.9M. Alpha will retain a 2% net smelter returns royalty."),
       [("NSR", 2.0, "Bravo", "Charlie Metals", "Alpha", "Charlie Metals", "new")])
    eq("137 the seller keeps the royalty the buyer grants when nobody else is named",
       rows("Alpha Resources Sells Bravo Property to Charlie Metals", "Alpha Resources Corp. (the \"Company\") "
            "announces the sale of its Bravo Property to Charlie Metals Inc. In addition, Charlie Metals has granted a 1% "
            "net smelter returns royalty on any of the claims that do not carry another royalty."),
       [("NSR", 1.0, "Bravo", "Charlie Metals", "Alpha Resources", "Charlie Metals", "new")])
    eq("138 rates in brackets and after the interest", [x[1] for h, b in (
        ("Delta Gold Acquires Echo Property", "Delta Gold Corp. (the \"Company\") announces it has acquired the Echo "
         "Property. The vendor shall retain a one percent (1%) net smelter royalty on all ore mined."),
        ("Delta Gold Acquires Echo Project Portfolio From Foxtrot Resources", "Delta Gold Corp. (the \"Company\") "
         "announces it will purchase the Projects. Delta will grant Foxtrot the right to receive an NSR of 0.5% on the "
         "current tenure of the Echo, Golf, and Hotel Projects.")) for x in rows(h, b)], [1.0, 0.5])
    print("royalties %s: %s" % (VERSION, "ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if self_test(verbose=True) else 0)
