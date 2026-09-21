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

Self-tests: python3 -m portal.extractors.royalties
"""
from __future__ import annotations

import re
import unicodedata

from portal import facts as F

NAME = "royalties"
VERSION = "1.0.0"
KIND = "royalty_row"
TAG = "Royalties & Streams"
TEXT_CAP = 40000

TXT_FIELDS = ("type", "metal", "property", "operator", "buyer", "seller", "currency", "action", "status",
              "price_note")
NUM_FIELDS = ("rate_pct", "price")

Q = "\"“”'‘’"          # quote characters PDFs and wires use around defined terms
_SUFFIX = r"(?:Inc|Corp|Corporation|Ltd|Limited|Plc|plc|PLC|LLC|L\.L\.C|LP|L\.P|Co|Company|S\.A\.(?:\s+de\s+C\.V)?|SA|AG|AB|NL)"
_CAPW = r"(?:[A-Z][\w&'’.\-]*|[A-Z]{2,}|of|de|del|and|&)"
_ORG = re.compile(r"\b((?:[A-Z][\w&'’\-]*\.?\s+)(?:(?:" + _CAPW + r")\s+){0,5}?" + _SUFFIX + r")\.?(?=[\s,;:)(”\"]|$)")
_METALS = ("gold", "silver", "copper", "platinum", "palladium", "nickel", "zinc", "lead", "cobalt", "tin", "tungsten",
           "graphite", "lithium", "uranium", "vanadium", "fluorspar", "iron ore", "molybdenum", "antimony", "rhodium",
           "tantalum", "manganese", "potash", "diamonds")

# ------------------------------------------------------------------ text preparation
_FLS = re.compile(r"(?i)\b(?:cautionary\s+(?:note|statement)s?\s+(?:regarding|on|concerning)|forward[\s\-]+looking\s+"
                  r"(?:statements?|information)\s*(?:and|&)?\s*(?:cautionary)?[^.]{0,40}?(?:\n|:|This\s+(?:news\s+)?release)"
                  r"|neither\s+(?:the\s+)?tsx|qualified\s+person)")


def _prepare(headline, body):
    b = (body or "")[:TEXT_CAP]
    m = _FLS.search(b, 400)
    if m:
        b = b[:m.start()]
    b = unicodedata.normalize("NFKC", b).replace(chr(160), " ")
    b = re.sub(r"\s+", " ", b)
    h = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", headline or ""))
    return h.strip(), b.strip()


def _title(h):
    """The headline without the lead some feeds append to it ('... Mine Franco-Nevada Corporation (“Franco-Nevada”
    or the “Company”) is pleased to announce ...')."""
    m = re.search(r"\s(?=(?:[A-Z][\w&'’.\-]*\s+){0,5}" + _SUFFIX + r"\.?\s*[,(])", h[10:])
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
    parts = re.split(r"(?<=[.;!?])\s+(?=[A-Z“\"•▪])|\s+[•▪]\s+", text)
    out = []
    for p in parts:
        p = p.strip()
        # a run of capitals (a headline or banner repeated in the body) is not a sentence to read
        p = re.sub(r"^(?:[^a-z]{0,40}?\b)?(?:[A-Z0-9&%$.,'’\-]+\s+){4,}(?=[A-Z][a-z])", "", p)
        p = re.sub(r"(?:\b[A-Z0-9&%$.,'’\-]{2,}\s+){5,}", " ", p).strip()
        if p:
            out.append(p)
    return out


# ------------------------------------------------------------------ names
def _clean_org(s):
    s = re.sub(r"\s+", " ", s or "").strip(" ,;:.")
    s = re.sub(r"^(?:the|a|an|and|with|to|from|by|of)\s+", "", s, flags=re.I)
    s = re.sub(r"\s*,?\s*\b" + _SUFFIX + r"\.?$", "", s).strip(" ,")
    s = re.sub(r"['’]s$", "", s)
    w = s.split()
    k = 0
    while k < len(w) and re.fullmatch(r"[A-Z0-9&\-]{2,}", w[k]):
        k += 1
    if k >= 2 and k < len(w):
        s = " ".join(w[k:])
    return s or None


def _definitions(text):
    """Defined terms: 'Wheaton Precious Metals Corp. (“Wheaton”)' -> {'wheaton': 'Wheaton Precious Metals'};
    'the Fruta del Norte (“FDN”) gold mine' -> {'fdn': 'Fruta del Norte'}; the Company -> the issuer."""
    out, orgs = {}, set()
    for m in re.finditer(r"((?:(?:[A-Z][\w&'’.\-]*|&|and)\s+){0,7}?(?:[A-Z][\w&'’.\-]*|" + _SUFFIX + r"\.?))\s*,?\s*"
                         r"(?:\([^()]{0,80}\)\s*){0,4}\(\s*(?:collectively,?\s*)?(?:the\s+)?[" + Q + r"]\s*([^" + Q + r"]{1,40}?)\s*[" + Q + r"]",
                         text):
        name, alias = m.group(1).strip(), m.group(2).strip()
        name = re.sub(r"^(?:The|A|An|And|With|To|From|By|Of|On|In|At)\s+", "", name)
        if alias.lower() in ("company", "corporation", "transaction", "agreement", "royalty", "stream", "nsr",
                             "project", "property", "arrangement", "offering", "acquisition", "optionee"):
            if alias.lower() in ("optionee",):
                out["optionee"] = _clean_org(name)
            continue
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
        pre = body[max(0, m.start() - 400):m.start()]
        pre = re.sub(r"\([^()]*\)\s*$", "", pre.rstrip())
        for _ in range(4):
            pre2 = re.sub(r"\([^()]*\)\s*$", "", pre.rstrip())
            if pre2 == pre:
                break
            pre = pre2
        orgs = list(_ORG.finditer(pre))
        if orgs:
            return _clean_org(orgs[-1].group(1))
        tail = re.findall(r"((?:[A-Z][\w&'’.\-]*\s+){0,4}[A-Z][\w&'’.\-]*)\s*$", pre)
        if tail:
            return _clean_org(tail[0])
    m = re.match(r"((?:[A-Z][\w&'’.\-]*\s+){0,4}?)(?:Announces|Reports|Closes|Completes|Enters|Signs|Executes|"
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
    for m in re.finditer(r"((?:[A-Z][\w&'’.\-]*\s+){0,4}(?:Royalt(?:y|ies)|Streaming)(?:\s+(?:&|and)\s+Royalty)?)\s*"
                         r"(?:\s+" + _SUFFIX + r"\b|['’]s\b)", text):
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
                      r"\blawsuit|\bcourt\b|\barbitration\b|\bdispute")
_H_FIN = re.compile(r"(?i)\b(?:financing|spin\s*-?\s*out|restructur\w*|transaction)\b")


def _in_scope(h, lead):
    """(ok, reason). The headline carries the deal, or names a financing/spin-out the lead calls a stream/royalty."""
    if _RESULTS.search(h):
        return False, "results, recap, promotion or dispute"
    if _OUT_OF_SCOPE.search(h) or _OUT_OF_SCOPE.search(lead[:900]):
        return False, "oil and gas or non-mining"
    if _INTEREST.search(h) and _DEAL.search(h):
        return True, "headline"
    if _H_FIN.search(h) and _INTEREST.search(lead[:1200]) and _DEAL.search(lead[:1200]):
        return True, "headline financing, lead interest"
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
_RATE_BEFORE = re.compile(r"(\d{1,2}(?:\.\d{1,3})?)\s?%\d?\s+(?:\([^)]{0,20}\)\s*)?(?:[\w\-]+\s+){0,4}$")
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
    r"(?:(?:the\s+)?(?:Company|Optionee|[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,4})['’]s?\s+|the\s+|its\s+|their\s+)?" + _ADJ +
    r"((?:[A-Z][\w'’\-]*|del|de|la|des|du)(?:\s+(?:[A-Z][\w'’\-]*|del|de|la|des|du|\d)){0,4}?)"
    r"(?:\s*\([^)]{0,40}\))?\s+(?:(?:Gold|Silver|Copper|Tin|Tungsten|Nickel|Graphite|Lithium|Uranium|Zinc|"
    r"[A-Z][a-z]+\s*-\s*[A-Z][a-z]+|gold|silver|copper|gold\s*-\s*copper)\s+)?"
    r"(" + _PROP_WORD + r"|project|mine|property|deposit|concessions?|claims?|mineral\s+district|lease|operations?)\b")
_BAD_PROP = re.compile(r"(?i)^(?:the|company|its|a|an|all|this|such|our|certain|existing|additional|new|royalty|stream|nsr|"
                       r"optionee|each|mineral|tsx|cse|transaction|agreement|net|gross|two|three|other|several|these|"
                       r"those|any|both|which|and|or|canadian|quebec|ontario|nevada)$")


def _property(text, defs):
    for m in _PROP.finditer(text):
        name = m.group(1).strip()
        name = re.split(r"['’]s\s+", name)[-1]
        if _BAD_PROP.match(name.split()[0]) or _BAD_PROP.match(name) or re.search(r"Zorg", name):
            continue
        if re.match(r"(?i)(?:net|gross|royalt|stream|nsr|the)\b", name):
            continue
        if name.lower() in defs and defs[name.lower()] and not re.search(r"(?i)\b" + _SUFFIX + r"\b", defs[name.lower()]):
            return defs[name.lower()]
        return name
    m = re.search(r"\b(?:stream|royalty|NSR)\s+on\s+([A-Z]{2,6})\b", text)
    if m and m.group(1).lower() in defs:
        return defs[m.group(1).lower()]
    return None


# ------------------------------------------------------------------ price
_MONEY = r"((?:US|U\.S\.|C|CA|CAD|CDN|A|AU|AUD)?\s?\$|USD\s?|CAD\s?)\s?(\d[\d,]*(?:\.\d+)?)\s*(million|billion|M|MM|B|k)?\b"


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
_PARTY = r"((?:[A-Z][\w&'’.\-]*\s+){0,5}[A-Z][\w&'’.\-]*(?:\s*,?\s+" + _SUFFIX + r"\.?)?)"
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
    em = re.match(r"[^.,;]{0,30}?(?:\.\s*)?,?\s*an?\s*n?\s+entity\s+(?:managed|controlled|advised)\s+by\s+" + _PARTY, rest)
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
    m = re.search(r"pursuant\s+to\s+which\s+" + _PARTY + r"\s+(?:will|has\s+agreed\s+to|shall)\s+(?:acquire|purchase)", s)
    if m:
        buyer = _alias(m.group(1), defs, issuer)
        return buyer, (issuer if buyer != issuer else None)
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
    m = re.search(r"\b(?:on|over|in|at)\s+(?:the\s+)?" + _PARTY + r"['’]s?\s+" + _ADJ + r"[A-Z][^.]{0,60}?\b" + _PROP_WORD, s)
    if m:
        n = m.group(1)
        if n.lower() in ("company", "optionee"):
            return issuer if n.lower() == "company" else defs.get("optionee")
        if not re.match(r"(?i)(?:the|its)\b", n):
            return _alias(n, defs, issuer)
    if re.search(r"(?i)\b(?:on|over|in)\s+(?:the\s+)?(?:Company['’]s|its)\s+" + _ADJ + r"[A-Z]", s):
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


# ------------------------------------------------------------------ the reader
def analyse(headline, body):
    h, b = _prepare(headline, body)
    title = _title(h)
    b = _drop_title(b, title)
    defs, def_orgs = _definitions(b[:12000])
    issuer = _issuer(title, b)
    roy_orgs = _royalty_orgs(h + " " + b[:12000]) | {n for n in def_orgs if n and re.search(r"(?i)royalt|stream", n)}
    table = {}
    hm, bm = _mask_orgs(h, roy_orgs, table), _mask_orgs(b, roy_orgs, table)
    lead = bm[:1500]
    ok, reason = _in_scope(hm, lead)
    if not ok:
        return {"rows": [], "reason": reason}
    sents = _sentences(bm[:8000])
    D = None
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
    U = lambda v: _unmask(v, table)     # noqa: E731
    issuer_royco = bool(issuer and (re.search(r"(?i)royalt|stream", issuer) or _ROYCO.search(b[-4000:] + b[:3000])))
    # the interest: the most specific typed mention in the deal sentence, the headline, then the next sentences
    ments = _interest_mentions(D) + _interest_mentions(hm) + _interest_mentions(ctx)
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
    if metal is None:
        mm = re.search(r"(?i)\bon\s+(" + "|".join(_METALS) + r")(?:\s+and\s+(" + "|".join(_METALS) + r"))?\s+production", ctx)
        if mm:
            metal = mm.group(1).lower() + (", " + mm.group(2).lower() if mm.group(2) else "")
        elif re.search(r"(?i)covering\s+all\s+minerals", ctx):
            metal = "all minerals"
    prop = _property(D, defs) or _property(hm, defs) or _property(ctx, defs)
    buyer, seller = _parties(D, defs, issuer, issuer_royco, ctx)
    operator = _operator(D, b, defs, issuer, prop) or _operator(ctx, b, defs, issuer, prop)
    hd = hm + " " + D
    if re.search(r"(?i)\b(?:amend\w*|expands?\s+(?:\w+\s+){0,2}agreement|extend\w*|restructur\w*)\b", hd) and \
            not re.search(r"(?i)\bsale\s+of\s+(?:an?\s+)?option|\boption\s+to\s+(?:buy|acquire)", hd):
        action = "amendment"
        if not buyer or buyer == issuer:
            buyer = _named_after(r"with", hd, defs, issuer) or buyer
        if buyer == issuer:
            buyer = None
        seller = issuer
        operator = operator or issuer
    elif re.search(r"(?i)\b(?:repurchas\w*|reacquir\w*|buy[\s\-]?back|buy[\s\-]?down|underlying)\b", hd) or \
            (buyer and operator and buyer == operator) or \
            (buyer == issuer and re.search(r"(?i)\b(?:on|over)\s+(?:its|the\s+Company['’]s)\s+", hd)) or \
            re.search(r"(?i)\boption\s+to\s+(?:buy|acquire)[^.]{0,60}\bheld\s+by\s+the\s+Company", D):
        action = "buyback"
        operator = operator or buyer
        buyer = buyer or operator
    elif (seller and operator and seller == operator) or \
            re.search(r"(?i)\b(?:grant\w*|creat\w*|spin\s*-?\s*out|(?:stream|royalty)\s+financing|financing\s+transaction)\b", D) or \
            (typ in ("stream", "NPI") and not re.search(r"(?i)\bexisting\b", D)) or \
            (seller == issuer and not re.search(r"(?i)\b(?:sale\s+of\s+its|its\s+existing|held\s+by|an\s+existing|currently\s+being|"
                                                 r"under\s+option)\b", D)):
        action = "new"
        operator = operator or seller
        seller = seller or operator
    else:
        action = "transfer"
    price, cur = _price(hm, D + " " + " ".join(sents[di + 1:di + 3]), b, _default_currency(b))
    status = _status(hm, D)
    base = dict(type=typ, rate_pct=rate, metal=metal, property=U(prop), operator=U(operator), buyer=U(buyer),
                seller=U(seller), price=price, currency=cur if price is not None else None, action=action,
                status=status, price_note=None)
    rows = [base]
    # two properties in one deal sentence ('royalties on the Lunahuasi and Los Helados Projects')
    two = re.search(r"\bon\s+the\s+([A-Z][\w'’\-]*(?:\s+[A-Z][\w'’\-]*){0,3})\s+and\s+([A-Z][\w'’\-]*(?:\s+[A-Z][\w'’\-]*){0,3})\s+"
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
    import hashlib
    h = hashlib.sha1()
    with open(__file__, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


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
            "Spanish Mountain Gold Ltd. (the “Company” or “Spanish Mountain Gold”) (TSX-V: SPA) is pleased to "
            "announce that it has entered into a royalty agreement (the “Royalty Agreement”) with Wheaton Precious "
            "Metals Corp. (“Wheaton”), pursuant to which Wheaton will acquire a 1.5% net smelter returns royalty "
            "(“NSR”) on gold and silver production from the Spanish Mountain Gold Project (the “Project”) for "
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
    r = one("Franco-Nevada Announces Acquisition of 1.0% NSR on AngloGold’s Arthur Gold Project in Nevada",
            "Franco-Nevada Corporation (“Franco-Nevada” or the “Company”) (TSX & NYSE:FNV) is pleased to "
            "announce that its wholly-owned subsidiary has acquired an existing 1.0% net smelter return royalty (the "
            "“Royalty”) on AngloGold Ashanti plc’s (“AngloGold”) Arthur Gold Project from Altius Minerals "
            "Corporation (“Altius”) for $250 million in cash.")
    eq("FNV Arthur", (r["type"], r["rate_pct"], r["buyer"], r["seller"], r["action"], r["status"]),
       ("NSR", 1.0, "Franco-Nevada", "Altius Minerals", "transfer", "closed"))
    # a royalty company's name is not a royalty (VMET.TO 15833a041d39)
    eq("royalty company's financing", one("Versamet Royalties Closes C$142 Million Bought Deal Financing",
                                          "Versamet Royalties Corporation (“Versamet” or the “Company”) is pleased to "
                                          "announce that it has closed its previously announced bought deal public offering."), None)
    # royalty income, a lawsuit, oil and gas, music: not rows
    eq("royalty payment", one("NEWPORT RECEIVES AUD$385,012 QUARTERLY ROYALTY PAYMENT"), None)
    eq("results", one("Royalties Inc. Reports Q3 Results and Success on Capstone Copper Lawsuit for 2% NSR on Cozamin Mine"), None)
    eq("oil and gas", one("Wedgemount Resources Sells Royalty on Permian Basin Assets",
                          "Wedgemount announces an agreement to sell up to a five percent Overriding Royalty Interest in its "
                          "west central Texas oil and gas assets."), None)
    # a vendor NSR in a property purchase is a mention in passing
    eq("vendor NSR", one("XCITE RESOURCES INC CLOSES ACQUISITION OF TURGEON LAKE PROPERTY",
                         "Under the Agreement Xcite granted Bullion a 2% net smelter returns royalty on the Property."), None)
    # the facts-store round trip
    back = to_prediction(extract("Hemlo Explorers Announces Sale of Hawkins Gold Royalty",
                                 "Hemlo Explorers Inc. (the “Company”) (TSXV: HMLO) announced today the sale of its 0.5% net "
                                 "smelter return (“NSR”) royalty on the Hawkins Gold Project, currently being explored under "
                                 "option by E2Gold Inc., to Vox Royalty Corp. (NASDAQ: VOXR, TSX: VOXR) for gross cash proceeds of "
                                 "C$100,000."))
    eq("round trip", [(x["type"], x["rate_pct"], x["property"], x["operator"], x["buyer"], x["seller"], x["action"], x["price"])
                      for x in back["rows"]],
       [("NSR", 0.5, "Hawkins", "E2Gold", "Vox Royalty", "Hemlo Explorers", "transfer", 100000.0)])
    print("royalties %s: %s" % (VERSION, "ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if self_test(verbose=True) else 0)
