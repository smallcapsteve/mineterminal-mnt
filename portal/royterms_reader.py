#!/usr/bin/env python3
"""Rules-only royalty / stream terms reader (C8 step 3, label guide v3).

read(headline, text, ticker="") -> {"interests": [...], "considerations": [...], "terms": [...]}

Pure Python 3 standard library; no network, no AI.  General rules only.

CLI:  python3 reader/royterms_reader.py tune out_tune.json
      (reads tune/full_NN.txt relative to the current directory)
"""
import json
import os
import re
import sys
import time

# --------------------------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------------------------

_SPLIT_WORDS = ["royalties", "royalty", "smelter", "expenditures", "expenditure", "exploration", "agreement",
                "payments", "payment", "purchase", "interest", "commitments", "commitment", "consideration",
                "anniversary", "Company", "common", "shares", "million", "option", "property", "warrants",
                "returns", "previously", "approval", "favour", "favor", "issuance", "assume", "Superior"]
_SPLIT_RES = [re.compile(r"\b" + r" ?".join(re.escape(c) for c in w) + r"\b", re.I) for w in _SPLIT_WORDS]

_NUMWORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
             "eight": "8", "nine": "9", "ten": "10", "fifteen": "15", "twenty": "20", "fifty": "50"}


def normalise(t):
    t = t.replace(" ", " ").replace("’", "'").replace("‘", "'").replace("“", '"')
    t = t.replace("”", '"').replace("–", "-").replace("—", "-").replace("", " ")
    t = re.sub(r"[ \t]+", " ", t)
    for rx in _SPLIT_RES:
        t = rx.sub(lambda m: m.group(0).replace(" ", ""), t)
    t = re.sub(r"\(\s+", "(", t)
    t = re.sub(r"\s+\)", ")", t)
    t = re.sub(r"(\d)\s*,\s*(\d{3})\b", r"\1,\2", t)
    t = re.sub(r"(\d)\s*,\s*(\d{3})\b", r"\1,\2", t)
    t = re.sub(r"\$\s+(?=\d)", "$", t)
    # "$1,0 00,000" -> "$1,000,000" when the joined figure is validly grouped
    t = re.sub(r"(\$\d[\d,]*) (\d[\d,]*\d)", lambda m: (m.group(1) + m.group(2)) if re.fullmatch(
        r"\$\d{1,3}(?:,\d{3})+", m.group(1) + m.group(2)) and not re.fullmatch(r"\$\d{1,3}(?:,\d{3})*", m.group(1))
        else m.group(0), t)
    t = re.sub(r"(\d)\s+%", r"\1%", t)
    t = re.sub(r"(\d)\s*-?\s*per\s*-?\s*cent\b", r"\1%", t, flags=re.I)
    t = re.sub(r"(\d)\s*percent\b", r"\1%", t, flags=re.I)
    t = re.sub(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|fifty)\s*(?:-\s*)?(?:percent|per cent)\b",
               lambda m: _NUMWORDS[m.group(1).lower()] + "%", t, flags=re.I)
    t = re.sub(r"\b(step|buy)\s*-\s*(down|back|up)\b", r"\1-\2", t, flags=re.I)
    t = re.sub(r"(?<=\w) -(?=\w)", "-", t)
    t = re.sub(r"(?<=[a-z])- (?=[a-z])", "-", t)
    return t


_ABBR = re.compile(r"(?:\b(?:Inc|Corp|Ltd|Mr|Mrs|Ms|Dr|No|St|Co|Jr|Sr|approx|U\.S|Nos|vs|[A-Z]|i|ii|iii|iv|vi|vii|viii|ix))\.$")


def split_sentences(t):
    parts = re.split(r"(?<=[.;!?])\s+(?=[A-Z(\[\"'0-9])", t)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if out and _ABBR.search(" " + out[-1][-14:]):
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return out


# --------------------------------------------------------------------------------------------
# money
# --------------------------------------------------------------------------------------------

_CUR = r"(?-i:US\s?\$|USD\s?\$|U\.S\.\s?\$|C\s?\$|CAD\s?\$|CDN\s?\$|Cdn\s?\$|CA\$|A\s?\$|AU\s?\$|AUD\s?\$|\$)"
_NUM = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_MULT = r"(?:\s?-?\s?(?:million|billion|thousand)\b|(?<=\d)\s?[MBK]\b|(?<=\d)k\b)"
_MONEY_RE = re.compile(r"(?<![\w.])(" + _CUR + r")\s?(" + _NUM + r")(" + _MULT + r")?"
                       r"(?:\s?(USD|US dollars|Canadian dollars|Cdn|CAD|AUD|Australian dollars|CDN)\b)?", re.I)
_WMONEY_RE = re.compile(r"(?<![\w.$])(" + _NUM + r")(\s?(?:million|billion))?\s+(Canadian dollars|US dollars|USD|CAD|"
                        r"cash payment)", re.I)


def _mult(s):
    s = (s or "").strip().lstrip("-").strip().lower()
    return {"million": 1e6, "billion": 1e9, "thousand": 1e3, "m": 1e6, "b": 1e9, "k": 1e3}.get(s, 1.0)


def _cur_of(prefix, suffix, default):
    p = (prefix or "").upper().replace(" ", "").replace(".", "")
    s = (suffix or "").upper()
    if "AUSTRALIAN" in s or s == "AUD":
        return "AUD"
    if "CANADIAN" in s or s in ("CAD", "CDN"):
        return "CAD"
    if s in ("USD", "US DOLLARS") or "U.S." in s:
        return "USD"
    if p.startswith("US"):
        return "USD"
    if p.startswith("C"):
        return "CAD"
    if p.startswith("A"):
        return "AUD"
    return default


def money_spans(s, default_cur):
    """-> list of (start, end, amount, currency)"""
    out = []
    for m in _MONEY_RE.finditer(s):
        try:
            v = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        v *= _mult(m.group(3))
        out.append((m.start(), m.end(), v, _cur_of(m.group(1), m.group(4), default_cur)))
    return out


def word_money(s, default_cur):
    out = []
    for m in _WMONEY_RE.finditer(s):
        v = float(m.group(1).replace(",", "")) * _mult(m.group(2))
        cur = _cur_of("", m.group(3), default_cur)
        out.append((m.start(), m.end(), v, cur))
    return out


def first_price(s, default_cur):
    ms = money_spans(s, default_cur)
    if ms:
        return ms[0]
    wm = word_money(s, default_cur)
    return wm[0] if wm else None


# --------------------------------------------------------------------------------------------
# interest mentions
# --------------------------------------------------------------------------------------------

_RATE = r"(\d{1,2}(?:\.\d+)?)%"
# type words, longest first.  group name -> family
_TYPES = [
    (r"net\s+smelter\s+returns?\s+(?:\((?:NSR|\"NSR\")\)\s+)?(?:production\s+)?royalt(?:y|ies)(?:\s+interest)?", "NSR"),
    (r"net\s+smelter\s+(?:ro\s?yalty|royalties)(?:\s+interest)?", "NSR"),
    (r"net\s+smelter\s+returns?(?:\s+\(NSR\))?", "NSR"),
    (r"NSR(?:\s+production)?(?:\s+royalt(?:y|ies))?", "NSR"),
    (r"gross\s+(?:revenue|overriding|metal|value|sales)(?:\s+[\w-]+){0,2}?\s+royalt(?:y|ies)(?:\s+interest)?", "GRR"),
    (r"royalty\s+on\s+gross\s+(?:sales\s+)?revenue", "GRR"),
    (r"(?:GRR|GMR|GVR|GOR)\b", "GRR"),
    (r"gross\s+royalty", "GRR"),
    (r"net\s+profits?\s+(?:interest|royalty)", "NPI"),
    (r"NPI\b", "NPI"),
    (r"revenue\s+share", "other"),
    (r"royalt(?:y|ies)", "other"),
]
_TYPE_ALT = "|".join("(?:%s)" % p for p, _ in _TYPES)
_TYPE_RES = [(re.compile(p, re.I), f) for p, f in _TYPES]
_FILL = r"(?:(?!of\b|the\b|for\b|to\b|and\b|in\b|on\b|or\b|at\b|by\b|with\b)[A-Za-z][\w-]*\s+){0,3}?"
# A: rate then type ("2% net smelter returns royalty", "2.0% precious metals royalty", "3.0% NSR 1 royalty")
_MENT_A = re.compile(r"(?<![\d.])" + _RATE + r"\s+" + _FILL + r"(" + _TYPE_ALT + r")", re.I)
# B: type then rate ("NSR royalties of 2.5%", "NSR royalty in the amount of 3.0%", "royalty equal to 2%")
_MENT_B = re.compile(r"(" + _TYPE_ALT + r")\s+(?:\([^)]{0,20}\)\s+)?(?:(?:in\s+favou?r\s+of\s+[\w&.,' -]{1,40}?|"
                     r"applicable\s+on\s+[\w ]{1,40}?|on\s+(?:future\s+)?(?:[\w-]+\s+){0,2}production|which|that|is|is\s+for|was)\s+)?"
                     r"(?:of|in\s+the\s+amount\s+of|equal\s+to|is|is\s+for|of\s+approximately)\s+"
                     r"(?:an?\s+)?" + _RATE, re.I)
_MENT_C = re.compile(r"royalt(?:y|ies)\s+(?:of|equal\s+to)\s+" + _RATE + r"\s+of\s+the\s+net\s+smelter\s+returns?", re.I)
# rate-less typed mentions
_MENT_NR = re.compile(r"(sliding[- ]scale\s+(?:[\w-]+\s+){0,3}?(?:" + _TYPE_ALT + r")|underlying\s+(?:NSR|net\s+smelter)"
                      r"[\w ]{0,25}?royalt(?:y|ies)|(?:" + _TYPE_ALT + r"))", re.I)

_STREAM_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)%\s+of\s+(?:the\s+)?(?:(?-i:[A-Z][\w']*)\s+)?(payable\s+)?"
                        r"(gold|silver|platinum|palladium|copper|cobalt|nickel|zinc)(?:\s+and\s+(gold|silver|platinum|"
                        r"palladium|copper))?(?!\s+(?:spot|market|price|prices))(?:\s+(?:production|equivalent|ounces|produced))?", re.I)
_BARE_STEP_RE = re.compile(r"(?:dropping|drop|step-down|stepping\s+down|stepped\s+down|reduc\w+|decreas\w+|falls?|fall)\s+to\s+"
                           r"(\d{1,3}(?:\.\d+)?)%|(\d{1,3}(?:\.\d+)?)%\s+thereafter", re.I)

_EXCL_BEFORE = re.compile(r"(buy\s?back|buy-back|buy-down|buy\s+down|purchase|repurchase|repurchased|remaining|leaving|"
                          r"reduced\s+to|bought\s+back|reduce\s+to)(?:\s+[\w-]+){0,5}\s+$", re.I)
_EXCL_NEAR = re.compile(r"(?:\bfirst|\badditional|part\s+of\s+a\s+total|combined\s+basis:?|pro-?forma)\W*(?:\w+\W+){0,1}$", re.I)

_NONMINING = re.compile(r"\b(cannabis|marijuana|music|film|oil\s+and\s+gas|hemp)\b", re.I)
_METALS = ["gold", "silver", "copper", "platinum", "palladium", "nickel", "zinc", "uranium", "lithium", "tin", "cobalt",
           "graphite", "antimony", "tungsten"]


def family_of(type_text):
    for rx, f in _TYPE_RES:
        if rx.fullmatch(type_text.strip()):
            return f
    tl = type_text.lower()
    if "smelter" in tl or "nsr" in tl:
        return "NSR"
    if "gross" in tl or "grr" in tl or "gmr" in tl:
        return "GRR"
    if "profit" in tl:
        return "NPI"
    return "other"


_PROP_RE = re.compile(r"\b(?:on|at|from|over|covering)\s+(?:the\s+|its\s+|all\s+of\s+the\s+|each\s+of\s+the\s+)?"
                      r"((?:(?:core|non-core)\s+)?[\"']?[A-Z][\w'&.-]*[\"']?(?:\s+(?:[A-Z][\w'&.-]*|de|del|of|and|la)){0,5})"
                      r"(?:\s+(?:property|properties|project|claims?|mine|concessions?|claim\s+block|deposit|licen[cs]e))?")
_PROP_STOP = {"The", "Company", "Agreement", "Option", "Closing", "December", "January", "February", "March", "April",
              "May", "June", "July", "August", "September", "October", "November", "TSX", "TSXV", "NYSE", "Exchange",
              "Project", "Property", "Properties", "Transaction", "NI", "National", "CIM", "Effective", "Approval"}


def find_property(s, start):
    seg = s[start:start + 160]
    m = _PROP_RE.search(seg)
    if not m:
        return None
    p = m.group(1).strip(" .,'\"")
    if not p or p.split()[0] in _PROP_STOP:
        return None
    return p


_HOLDER_FAV = re.compile(r"in\s+favou?r\s+of\s+(?:the\s+)?((?-i:[A-Z0-9][\w&.'-]*(?:\s+[A-Z0-9][\w&.'-]*){0,4})|optionor|vendors?|sellers?)",
                         re.I)
_HOLDER_SUBJ = re.compile(r"((?:[Tt]he\s+)?(?:(?:property\s+)?vendors?|optionors?|sellers?|[A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,4}))\s+(?:will|shall|would)?\s*(?:also\s+)?"
                          r"(?:retain|retains|retained|retaining|holds|hold|will\s+be\s+granted)\b")


def detect_mentions(s):
    """-> list of dict(start, end, rate, family, type_text)"""
    out = []
    taken = []

    def ok_span(a, b):
        for x, y in taken:
            if a < y and x < b:
                return False
        return True

    for rx, kind in ((_MENT_C, "C"), (_MENT_A, "A"), (_MENT_B, "B")):
        for m in rx.finditer(s):
            if kind == "A":
                rate, tt = m.group(1), m.group(2)
            elif kind == "B":
                tt, rate = m.group(1), m.group(2)
            else:
                rate, tt = m.group(1), "net smelter returns"
            if not ok_span(m.start(), m.end()):
                continue
            before = s[max(0, m.start() - 60):m.start()]
            weak = False
            if _EXCL_BEFORE.search(before):
                if kind != "B" and re.search(r"of\s+(?:the|this|its)\s+(?:up\s+to\s+)?$", before, re.I):
                    weak = True
                else:
                    continue
            if kind != "B" and _EXCL_NEAR.search(before[-30:]):
                continue
            after = s[m.end():m.end() + 25].lower()
            if kind == "A" and re.match(r"\s*(?:cut-?off|value|basis|calculation)", after):
                continue
            fam = family_of(tt)
            if kind == "C":
                fam = "NSR"
            try:
                r = float(rate)
            except ValueError:
                continue
            if r <= 0 or r > 30:
                continue
            taken.append((m.start(), m.end()))
            out.append({"start": m.start(), "end": m.end(), "rate": r, "family": fam, "type_text": tt.strip(), "weak": weak})
    out.sort(key=lambda x: x["start"])
    return out


# --------------------------------------------------------------------------------------------
# sentence classification
# --------------------------------------------------------------------------------------------

_FIN_RE = re.compile(r"private\s+placement|non-brokered|brokered|\bfinancing\b|offering|per\s+unit|units?\s+at\s+a\s+price|"
                     r"credit\s+(?:facility|agreement)|\bloan\b|\bdebt\b|warrants?\s+(?:entitl|will\s+entitl)|stock\s+options?|"
                     r"incentive|gross\s+proceeds|flow-through|finder|draw\s?down|cash\s+on\s+hand|invested|expended|"
                     r"\bspent\b|deferred|per\s+ounce|per\s+oz|/oz|for\s+every|outstanding\s+shares|issued\s+and\s+"
                     r"outstanding|market\s+cap|revenue\s+of|net\s+present\s+value|\bNPV\b|capital\s+cost|collateral|"
                     r"in\s+prior\s+exploration|interest\s+payments?|(?:finder'?s?|advisory|arrangement|break|termination|standby|management|"
                     r"origination|success)\s+fees?|\bbudget|capital\s+expenditures?|\bcapex\b|\b(?:royalty|stream|total|annual)\s+revenues?|revenues?\s+(?:of|was|were|totall?ed)\b|valued\s+at", re.I)
_ROYWORD = re.compile(r"royalt|\bNSR\b|\bGRR\b|\bGMR\b|smelter|\bstream", re.I)
_DEAL_RE = re.compile(r"\bpa(?:y|id|ying|yable|yments?)\b|\bissu(?:e|ed|es|ing|ance|ances)\b|consideration|in\s+exchange|"
                      r"purchase\s+price|\bin\s+shares\b|\bincur|\bspend|\bcommitments?\b|receiv\w*\s+(?:\w+\s+){0,2}[\d$]|"
                      r"\bfunding\b|\bupfront\b|\bdeposit\b|\bsettle|\bsatisf|\bbonus\b|entitled\s+to|\bfor\s+(?:a\s+)?(?:total\s+)?(?:cash\s+)?(?:US|C|CDN|A|AU)?\s?\$", re.I)
_INSTAL_RE = re.compile(r"anniversar|\byear\s?\d|\d\s?(?:st|nd|rd|th)\s+year|\bon\s+or\s+before\b|within\s+\d+\s+days|"
                        r"thereafter|install?ments?|initial\s+(?:cash\s+)?payment|first\s+year|upon\s+closing|on\s+signing|"
                        r"on\s+closing|upon\s+signing|firm\s+commitment", re.I)
_BUY_RE = re.compile(r"buy\s?back|buy-back|buy-down|buy\s+down|repurchas|purchase\s+(?:up\s+to\s+)?(?:one[- ]half|half|"
                     r"\d+(?:\.\d+)?%|the\s+NSR|all)|right\s+to\s+(?:purchase|acquire)\s+(?:up\s+to\s+)?(?:\d|one|half)|"
                     r"reduced?\s+(?:the\s+(?:NSR|royalty|GRR)\s+)?to\s+\d+(?:\.\d+)?%\s+(?:by|for|upon|on)\s+(?:(?:the|a|an)\s+)?(?:[\w']+\s+){0,3}?(?:payment|paying|\$|cash)|can\s+purchase|may\s+(?:be\s+)?purchase|"
                     r"(?:be|been)\s+purchased|may\s+purchase|bought\s+back", re.I)


# --------------------------------------------------------------------------------------------
# main reader
# --------------------------------------------------------------------------------------------

def _default_currency(t):
    if re.search(r"(?:all\s+)?(?:dollar\s+figures|amounts|currency|figures|dollar\s+amounts|monetary\s+amounts)(?:\s+presented)?\s+"
                 r"(?:are\s+|is\s+)?(?:expressed\s+|stated\s+|reported\s+|presented\s+)?in\s+(?:US\$?|U\.S\.|United\s+States|USD)|"
                 r"\(all\s+amounts\s+in\s+United\s+States\s+dollars\)|all\s+amounts\s+in\s+US|"
                 r"\(\s*US\$\s*\)\s+dollars\s+unless", t, re.I):
        return "USD"
    if re.search(r"all\s+(?:dollar\s+figures|amounts|currency)\s+(?:are\s+)?in\s+(?:A\$|AUD|Australian)", t, re.I):
        return "AUD"
    return "CAD"


def _cut_about(t):
    head = t[:400]
    for m in re.finditer(r"\bAbout\s+([A-Z][\w.&'-]+)", t):
        w = m.group(1)
        if m.start() < 300 or w in ("The", "the"):
            continue
        if w.rstrip(".") in head:
            return t[:m.start()]
    return t


def _round(x):
    if x is None:
        return None
    return round(x, 4)


class Interest(object):
    def __init__(self, fam, rate, type_text, sent, pos):
        self.fam = fam
        self.rate = rate
        self.type_text = type_text
        self.sents = [sent]
        self.first = sent
        self.pos = pos
        self.metal = None
        self.prop = None
        self.holder = None
        self.payer = None
        self.event = None
        self.scope = "subject"
        self.quote = None
        self.id = None
        self.rates_seen = []
        self.sliding = False
        self.cons = []      # list of (component, amount, currency, shared, new)
        self.spos = {sent: [pos]}
        self.split_total = None
        self.force_block = None
        self.receiver_is_issuer = None
        self.receiver = None
        self.prop_fixed = False


def read(headline, text, ticker=""):
    full = (headline or "") + ". " + (text or "")
    if _NONMINING.search(full[:3000]):
        return {"interests": [], "considerations": [], "terms": []}
    t = normalise(full)
    t = _cut_about(t)
    cur0 = _default_currency(t)
    S = split_sentences(t)
    S = [s[:4000] for s in S]
    n = len(S)

    stream_ctx = bool(re.search(r"\bstream|precious\s+metals?\s+purchase|\bPMPA\b|silver\s+purchase\s+agreement|"
                                r"gold\s+purchase\s+(?:and\s+sale\s+)?agreement", t, re.I))
    deal_ctx = bool(re.search(r"\boption|acquir|purchase|sale\s+agreement|\bsold\b|\bsell|\bvendors?\b|\boptionors?\b", t, re.I))

    interests = []
    terms = []

    deal = deal_sentences(S, cur0)
    blocks = deal_blocks(deal)

    def block_of(si):
        """nearest deal block for a sentence (containing, else preceding within 4, else following within 3)."""
        best = None
        for k, bl in enumerate(blocks):
            if bl[0] <= si <= bl[-1]:
                return k
            if bl[-1] < si and si - bl[-1] <= 4:
                d = si - bl[-1]
            elif bl[0] > si and bl[0] - si <= 3:
                d = bl[0] - si + 0.5
            else:
                continue
            if best is None or d < best[0]:
                best = (d, k)
        return best[1] if best else None

    # ---------------- royalty mentions ----------------
    ment_by_sent = {}
    for si, s in enumerate(S):
        if re.search(r"combined\s+basis", s, re.I):
            continue
        if re.search(r"\bportfolio\b", s, re.I) and \
                not re.search(r"\b(?:acquir|grant|retain|sell|sold|purchas|transfer)", s, re.I):
            continue
        ms = detect_mentions(s)
        # list continuation: "NSR royalties of 2.5% on the Vendor Claims and 1.5% applicable on claims ..."
        extra = []
        for m in ms:
            cm = re.match(r"\s*(?:on|at|in|over)\s[^.;%]{0,60}?\band\s+(\d{1,2}(?:\.\d+)?)%\s+(?:applicable\s+)?(?:on|to|in|at)\b",
                          s[m["end"]:m["end"] + 100])
            if not cm:
                cm = re.match(r"\s*(?:and|&)\s+(\d{1,2}(?:\.\d+)?)%\s+(?:at|on|in|,|respectively)", s[m["end"]:m["end"] + 40])
            if cm:
                p0 = m["end"] + cm.start(1)
                extra.append({"start": p0, "end": p0 + len(cm.group(1)) + 1, "rate": float(cm.group(1)),
                              "family": m["family"], "type_text": m["type_text"]})
        ms = sorted(ms + extra, key=lambda x: x["start"])
        if ms:
            ment_by_sent[si] = ms

    typed_rated = {(m["family"]) for ms in ment_by_sent.values() for m in ms if m["family"] != "other"}
    has_nsr_word = bool(re.search(r"net\s+smelter|\bNSR\b", t, re.I))

    def find_interest(fam, rate, prop):
        for it in interests:
            if it.fam == "stream":
                continue
            if it.fam == fam and abs((it.rate or -1) - (rate or -1)) < 0.011:
                if prop and it.prop and not _same_prop(prop, it.prop):
                    continue
                return it
        return None

    def touch(it, si, pos):
        if si not in it.sents:
            it.sents.append(si)
        it.spos.setdefault(si, [])
        if pos not in it.spos[si]:
            it.spos[si].append(pos)

    weak_ments = []
    split_map = {}
    for si in sorted(ment_by_sent):
        s = S[si]
        ms = ment_by_sent[si]
        # parenthetical split "(1% in favour of A and 1% in favour of B)"
        fav = re.findall(r"(\d+(?:\.\d+)?)%\s+in\s+favou?r\s+of\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})", s)
        for m in ms:
            if m.get("weak"):
                weak_ments.append((si, m))
                continue
            fam, rate = m["family"], m["rate"]
            ctx = s[max(0, m["start"] - 80):m["end"] + 120]
            pre = s[max(0, m["start"] - 45):m["start"]].lower()
            if fam == "other":
                low = ctx.lower()
                if "revenue share" in m["type_text"].lower():
                    fam = "other"
                elif re.search(r"existing\s+royalty|underlying\s+royalty|royalty\s+which\s+is", low):
                    fam = "other"
                elif has_nsr_word and (find_interest("NSR", rate, None) or ("NSR" not in typed_rated)):
                    # bare "3% royalty" in a release that names the royalty an NSR elsewhere
                    fam = "NSR"
            prop = find_property(s, m["end"])
            if (fam, rate) in split_map:
                for y in split_map[(fam, rate)]:
                    touch(y, si, m["start"])
                continue
            if fav and len(fav) >= 2 and fam == "NSR" and abs(sum(float(x) for x, _ in fav) - rate) < 0.011:
                for x, h in fav:
                    it = None
                    for y in interests:
                        if y.fam == fam and y.rate == float(x) and y.holder and h.split()[0] in y.holder:
                            it = y
                    if it is None:
                        it = Interest(fam, float(x), m["type_text"], si, m["start"])
                        it.prop = prop
                        it.holder = h
                        it.split_total = rate
                        interests.append(it)
                    touch(it, si, m["start"])
                    split_map.setdefault((fam, rate), [])
                    if it not in split_map[(fam, rate)]:
                        split_map[(fam, rate)].append(it)
                continue
            holder = None
            hm = _HOLDER_FAV.search(s[max(0, m["start"] - 10):m["end"] + 80])
            if hm:
                holder = hm.group(1)
            it = find_interest(fam, rate, prop)
            if it is not None and holder and it.holder and holder.split()[-1].lower() != it.holder.split()[-1].lower():
                it = None
            existing_here = bool(re.search(r"(?:existing|underlying)\s+(?:[\w-]+\s+){0,2}$", pre)) and \
                not re.search(r"acqui\w+\s+(?:an?\s+|the\s+)?existing\s+$", pre)
            preexisting = bool(re.search(r"pre-existing\s+(?:[\w-]+\s+){0,2}$", pre))
            if it is not None and existing_here and it.event not in ("existing", "held"):
                it = None
            if it is not None and it.event == "existing" and not existing_here and \
                    re.search(r"\b(?:retain|grant)", s, re.I):
                it = None
            if it is not None and re.search(r"\b(?:retain|grant)\w*", s, re.I):
                # the same rate in a different property deal is a different royalty
                b_old = {block_of(x) for x in it.sents}
                b_new = block_of(si)
                if b_new is not None and None not in b_old and b_new not in b_old and \
                        all(re.search(r"\b(?:retain|grant)\w*", S[x], re.I) for x in it.sents):
                    it = None
            if it is None:
                it = Interest(fam, rate, m["type_text"], si, m["start"])
                it.prop = prop
                it.holder = holder
                if preexisting:
                    it.event = "held"
                    it.scope = "underlying"
                elif existing_here:
                    it.event = "existing"
                interests.append(it)
            else:
                touch(it, si, m["start"])
                if not it.prop and prop:
                    it.prop = prop
                if not it.holder and holder:
                    it.holder = holder
            if re.search(r"sliding[- ]scale", ctx, re.I):
                it.sliding = True

    # "buy back three-quarters of the 1% NSR": the base royalty, when the release names it nowhere else
    for si, m in weak_ments:
        if m["family"] == "other":
            continue
        fam = m["family"]
        it = find_interest(fam, m["rate"], None)
        if it is None:
            it = Interest(fam, m["rate"], m["type_text"], si, m["start"])
            it.prop = find_property(S[si], m["end"])
            interests.append(it)
        else:
            touch(it, si, m["start"])

    # rate-less typed mentions (sliding scale, underlying NSR) when no rated interest of that family exists
    for si, s in enumerate(S):
        for m in _MENT_NR.finditer(s):
            tt = m.group(1)
            low = tt.lower()
            if not (low.startswith("sliding") or low.startswith("underlying")):
                continue
            fam = family_of(re.sub(r"^(sliding[- ]scale|underlying)\s+", "", tt, flags=re.I)) if low.startswith("sliding") \
                else "NSR"
            if low.startswith("sliding") and re.search(r"\d+(?:\.\d+)?%", s[max(0, m.start() - 30):m.end() + 30]):
                continue
            if low.startswith("sliding") and any(it.fam == fam for it in interests):
                near = _nearest_interest([x for x in interests if x.fam == fam], si, S)
                if near is not None:
                    near.sliding = True
                    touch(near, si, m.start())
                continue
            if low.startswith("underlying") and any(it.fam == fam and it.event == "existing" for it in interests):
                continue
            it = Interest(fam, None, tt, si, m.start())
            it.prop = find_property(s, m.end())
            it.sliding = low.startswith("sliding")
            if low.startswith("underlying"):
                it.event = "existing"
                it.scope = "underlying"
            interests.append(it)

    # rate-less references ("the NSR", "the GRR", "the Royalty") -> the one interest of that family not named here
    for si, s in enumerate(S):
        for m in re.finditer(r"\b(?:the|this|such|an?|additional)\s+(?:additional\s+|sliding[- ]scale\s+|underlying\s+)?(NSR|GRR|GMR|net\s+smelter\s+returns?\s+royalty|"
                             r"royalty\s+on\s+gross\s+(?:sales\s+)?revenue|gross\s+\w+\s+royalty|(?-i:Royalty))\b", s, re.I):
            fam = family_of(m.group(1)) if m.group(1) != "Royalty" else None
            named = [it for it in interests if si in it.spos and any(abs(p - m.start()) < 40 for p in it.spos[si])]
            if named:
                continue
            cands = [it for it in interests if it.fam != "stream" and (fam is None or it.fam == fam) and it.rate is not None]
            here = {id(it) for it in interests if si in it.spos}
            free = [it for it in cands if id(it) not in here]
            sl = [it for it in cands if it.sliding]
            earlier = [(max(p for p in it.spos[si] if p < m.start()), it) for it in cands
                       if si in it.spos and any(p < m.start() for p in it.spos[si])]
            if earlier:
                continue
            if len(cands) == 1:
                touch(cands[0], si, m.start())
            elif len(free) == 1 and here:
                touch(free[0], si, m.start())
            elif "sliding" in m.group(0).lower() and len(sl) == 1:
                touch(sl[0], si, m.start())

    # ---------------- streams ----------------
    streams = []
    if stream_ctx:
        cur_stream = None
        for si, s in enumerate(S):
            if _FIN_RE.search(s) and not re.search(r"stream|deliver|payable", s, re.I):
                continue
            if re.search(r"reserves?\s+and\s+resources\s+have\s+been\s+calculated|attributable\s+reserves", s, re.I):
                continue
            events = []
            for m in _STREAM_RE.finditer(s):
                metals = [m.group(3).lower()] + ([m.group(4).lower()] if m.group(4) else [])
                events.append((m.start(), "rate", float(m.group(1)), metals, m.end()))
            for m in _BARE_STEP_RE.finditer(s):
                v = m.group(1) or m.group(2)
                # skip if the same position is a "X% of payable metal" mention
                if any(abs(e[1 + 0] if False else 0) for e in []):
                    pass
                events.append((m.start(), "step", float(v), None, m.end()))
            events.sort()
            # k4: "25% of the gold production and 25% of the silver production converted to gold equivalent" -> one stream
            if re.search(r"equivalent", s, re.I):
                rates_ev = [e for e in events if e[1] == "rate"]
                if len(rates_ev) >= 2 and len({e[2] for e in rates_ev}) == 1 and \
                        len({m for e in rates_ev for m in e[3]}) >= 2:
                    first = rates_ev[0]
                    mets = []
                    for e in rates_ev:
                        for m0 in e[3]:
                            if m0 not in mets:
                                mets.append(m0)
                    events = [e for e in events if e[1] != "rate" or e is first]
                    events = [(first[0], "rate", first[2], ["+".join(mets)], first[4]) if e is first else e for e in events]
            clean = []
            for e in events:
                if e[1] == "step" and any(x[1] == "rate" and x[0] <= e[0] + 20 and e[0] <= x[4] for x in events if x is not e):
                    # "dropping to 67% of payable gold" -> handled as rate mention of same metal
                    continue
                clean.append(e)
            for e in clean:
                if e[1] == "rate":
                    if e[2] > 100:
                        continue
                    # skip delivery shares that look like ownership ("100% interest")
                    prop = _stream_prop(s, e[4])
                    for metal in e[3]:
                        st = None
                        for x in streams:
                            if (x.metal == metal.replace("+", " and ") or metal in getattr(x, "metals", [])) and (prop is None or x.prop is None or _same_prop(prop, x.prop)):
                                st = x
                                break
                        if st is None or (prop and st.prop and not _same_prop(prop, st.prop)):
                            st = Interest("stream", e[2], "stream", si, e[0])
                            st.metals = metal.split("+")
                            st.metal = metal.replace("+", " and ")
                            st.prop = prop
                            st.rates_seen = [e[2]]
                            streams.append(st)
                        else:
                            if si not in st.sents:
                                st.sents.append(si)
                            if st.prop is None and prop:
                                st.prop = prop
                            if e[2] not in st.rates_seen:
                                terms.append({"kind": "stepdown", "_it": st, "from_rate": st.rates_seen[-1],
                                              "to_rate": e[2], "unit": "%% of payable %s" % metal,
                                              "trigger": _trigger(s, e[4]), "quote": _q(s, e[0])})
                                st.rates_seen.append(e[2])
                        cur_stream = st
                else:
                    st = cur_stream
                    if st is None:
                        cands = [x for x in streams]
                        st = cands[-1] if cands else None
                    if st is not None and e[2] not in st.rates_seen and e[2] < st.rates_seen[-1]:
                        terms.append({"kind": "stepdown", "_it": st, "from_rate": st.rates_seen[-1], "to_rate": e[2],
                                      "unit": "%% of payable %s" % st.metal, "trigger": _trigger(s, e[4]),
                                      "quote": _q(s, e[0])})
                        st.rates_seen.append(e[2])
        # streams mentioned with a rate only if the text calls it a stream; drop ownership-like mentions
        streams = [x for x in streams if x.rate is not None and x.rate > 0]
        # terminated streams (no rate)
    term_streams = []
    found = []
    for si, s in enumerate(S):
        m = re.search(r"(?:terminat\w*|not\s+to\s+proceed\s+with|cancell?ed)\s+(?:\w+\s+){0,6}?((?:silver|gold|copper|precious\s+metals?)"
                      r"\s+(?:stream|purchase\s+agreement))", s, re.I)
        if m:
            found.append((m.group(0).isupper(), si, m))
    if found:
        found.sort(key=lambda x: (x[0], x[1]))       # prefer body text over an ALL-CAPS headline
        _, si, m = found[0]
        st = Interest("stream", None, m.group(1), si, m.start())
        st.event = "terminated"
        st.metal = m.group(1).split()[0].lower()
        term_streams.append(st)

    for st in streams:
        interests.append(st)
    interests.extend(term_streams)

    if not interests:
        return {"interests": [], "considerations": [], "terms": []}

    # ---------------- events, holders, payer ----------------
    issuer, issuer_alias = _issuer(t)
    issuer_royco = bool(issuer and re.search(r"royalt|stream", issuer, re.I)) or bool(re.search(
        r"\b(?:is|as)\s+(?:a|an|the)\s+(?:[\w'-]+\s+){0,5}?(?:royalty|streaming)\s+(?:and\s+(?:streaming|royalty)\s+)?company",
        normalise(full), re.I))
    issuer_receives = (not issuer_royco) and bool(re.search(r"(?:will|has|have)\s+(?:also\s+)?receiv\w*\s+(?:an?\s+)?(?:aggregate\s+)?(?:upfront\s+)?"
                                     r"(?:deposit\s+)?(?:US\s?\$|C\s?\$|\$|upfront|deposit|cash)", t, re.I))
    iw_all = (set(re.findall(r"[a-z0-9]+", (issuer or "").lower())) | set(re.findall(r"[a-z0-9]+", (issuer_alias or "").lower()))) - \
        {"the", "inc", "corp", "ltd", "resources", "mining", "gold", "silver", "metals", "precious", "corporation", "limited"}
    for it in interests:
        if it.fam != "stream":
            continue
        for x in it.sents:
            rm = re.search(r"([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})\s+(?:will|shall|would)\s+(?:be\s+entitled\s+to\s+|have\s+the\s+right\s+to\s+)?"
                           r"(?:receive|purchase)\s+(?:\d+(?:\.\d+)?)%\s+of", S[x])
            if rm:
                sw = set(re.findall(r"[a-z0-9]+", rm.group(1).lower()))
                it.receiver_is_issuer = bool(sw & (iw_all | {"company"}))
                it.receiver = rm.group(1)
                break
    for it in interests:
        s = S[it.first]
        ctx = " ".join(S[i] for i in it.sents[:3])
        if it.event is None:
            loc = S[it.first][max(0, it.pos - 110):it.pos + 60]
            if not re.search(r"\b(?:sell|sold|sale|acquir|grant|retain|transfer|purchas|dispos)",
                             S[it.first][max(0, it.pos - 60):it.pos + 40], re.I) and \
                    re.search(r"\bits\s+(?:existing\s+)?\d+(?:\.\d+)?%", loc[-75:]):
                it.event = "held"
            else:
                it.event = _local_event(it, S[it.first], deal_ctx)
            if it.event is None:
                for back in range(0, 4):
                    j = it.first - back
                    if j < 0:
                        break
                    if _EVENT_VERB.search(S[j]):
                        it.event = _event(it, S[j], deal_ctx, issuer_receives)
                        break
            if it.event is None:
                it.event = _event(it, ctx, deal_ctx, issuer_receives)
        if it.event in ("existing",) and it.scope == "subject":
            if not re.search(r"\b(?:retain|grant|acquir|sell|sold|purchas)", ctx, re.I):
                it.scope = "underlying"
        if it.event == "held" and deal_ctx and re.search(r"collateral|security", ctx, re.I):
            it.scope = "underlying"
        it.quote = _q(s, it.pos)
    _parties(S, t, interests, _display(issuer, issuer_alias), issuer_alias, iw_all, issuer_royco)
    for it in interests:
        s = S[it.first]
        if it.metal is None:
            for mt in _METALS:
                if re.search(r"\b%s\b" % mt, s[max(0, it.pos - 60):it.pos + 140], re.I):
                    it.metal = mt
                    break

    # ---------------- terms: buyback ----------------
    exercised = False
    for si, s in enumerate(S):
        if not _BUY_RE.search(s):
            continue
        if not _ROYWORD.search(s) and not re.search(r"buy\s?back|buy-back|buy-down|buy\s+down|repurchas", s, re.I):
            continue
        if exercised and re.search(r"exercis\w+\s+the\s+buy\s?back|extension", s, re.I):
            continue
        if re.search(r"(?:paid|has\s+paid|completed|exercised)\b.{0,60}buy\s?back|repurchase\s+of\s+(?:a\s+)?(?:significant\s+)?"
                     r"portion|buyback\s+we\s+have\s+just\s+completed|recently\s+paid", s, re.I):
            # buyback exercised
            exercised = True
            for it in interests:
                if si in it.sents or it is _nearest_interest(interests, si, S):
                    it.event = "bought_back"
                    break
            continue
        terms.extend(_buybacks(s, si, interests, S, cur0))

    # ---------------- terms: stepdowns (royalty) ----------------
    for si, s in enumerate(S):
        for it in interests:
            if it.fam == "stream":
                continue
            if si not in it.sents:
                continue
            m = re.search(r"(?:will\s+be\s+|is\s+)?reduced\s+to\s+(\d+(?:\.\d+)?)%", s)
            if m and not re.search(r"\$|payment\s+of|buy|purchase|repurchas|for\s+(?:a\s+)?(?:cash\s+)?(?:payment|\d[\d,.]*\s*(?:million|,000))", s, re.I) and \
                    it.rate is not None and float(m.group(1)) < it.rate:
                terms.append({"kind": "stepdown", "_it": it, "from_rate": it.rate, "to_rate": float(m.group(1)),
                              "unit": "%", "trigger": _trigger(s, 0), "quote": _q(s, m.start())})
            if re.search(r"not\s+payable\s+on\s+the\s+first|payable\s+(?:only\s+)?on\s+(?:proceeds\s+from\s+)?(?:any\s+)?"
                         r"production\s+in\s+excess\s+of|take\s+effect\s+(?:upon|once|after|when)|takes\s+effect", s, re.I):
                to = None if (it.sliding or re.search(r"sliding", s, re.I)) else it.rate
                terms.append({"kind": "stepdown", "_it": it, "from_rate": 0.0, "to_rate": to, "unit": "%",
                              "trigger": _trigger(s, 0), "quote": _q(s, 0)})
            m = re.search(r"(?:apply|applies|payable)\s+.{0,130}?\bto\s+(?:December|January|February|March|April|May|June|July|"
                          r"August|September|October|November)\s+\d{1,2},\s+\d{4}", s)
            if m and it.rate:
                terms.append({"kind": "stepdown", "_it": it, "from_rate": it.rate, "to_rate": 0.0, "unit": "%",
                              "trigger": _trigger(s, m.start()), "quote": _q(s, m.start())})
    for it in interests:
        if it.fam != "stream" and it.sliding and not any(x["kind"] == "stepdown" and x["_it"] is it for x in terms):
            terms.append({"kind": "stepdown", "_it": it, "from_rate": None, "to_rate": None, "unit": "%",
                          "trigger": "sliding scale", "quote": _q(S[it.first], it.pos)})

    # ---------------- terms: stream delivery, ongoing payment step, inflation ----------------
    live_streams = [x for x in interests if x.fam == "stream" and x.event != "terminated"]
    if live_streams:
        ongoing = None
        for si, s in enumerate(S):
            pm = list(re.finditer(r"(\d{1,2}(?:\.\d+)?)%\s+of\s+the\s+(?:\w+\s+)?(?:spot|market)\s+(?:gold\s+|silver\s+)?prices?", s, re.I))
            if not pm:
                continue
            vals = [float(x.group(1)) for x in pm]
            if ongoing is None:
                ongoing = (s[max(0, pm[0].start() - 10):pm[0].end() + 80], vals[0])
            seq = [ongoing[1]] + [v for v in vals if True]
            prev = ongoing[1]
            for v in vals:
                if v != prev and re.search(r"increase|rise|then|thereafter|step|at\s+which", s, re.I):
                    if not any(x["kind"] == "stepdown" and x.get("unit", "").startswith("% of spot") and
                               x["from_rate"] == prev and x["to_rate"] == v for x in terms):
                        terms.append({"kind": "stepdown", "_it": live_streams[0], "_for_all": True, "from_rate": prev,
                                      "to_rate": v, "unit": "% of spot (ongoing payment)", "trigger": _trigger(s, 0),
                                      "quote": _q(s, 0)})
                    prev = v
        for st in live_streams:
            for mt in (getattr(st, "metals", None) or [st.metal]):
                terms.append({"kind": "stream", "_it": st, "metal": mt, "delivery_pct": st.rate,
                              "ongoing_payment": ongoing[0].strip() if ongoing else None, "threshold": None,
                              "quote": _q(S[st.first], st.pos)})
        for si, s in enumerate(S):
            if re.search(r"inflation\s+adjustment|annual\s+escalation|escalat\w+", s, re.I) and \
                    re.search(r"per\s+(?:gold\s+)?ounce|ongoing\s+payment|market\s+price|per\s+ounce", s, re.I):
                terms.append({"kind": "stepdown", "_it": live_streams[0], "_for_all": True, "from_rate": None,
                              "to_rate": None, "unit": "US$/oz (ongoing payment)", "trigger": _trigger(s, 0),
                              "quote": _q(s, 0)})
                break

    # ---------------- terms: cap, minimum, aoi ----------------
    for si, s in enumerate(S):
        if re.search(r"\buncapped\b", s, re.I) and re.search(r"stream|royalt", s, re.I):
            it = _nearest_interest(interests, si, S, prefer_fam="stream" if live_streams else None)
            if it is not None and not any(x["kind"] == "cap" and x["_it"] is it for x in terms):
                terms.append({"kind": "cap", "_it": it, "amount": None, "unit": None, "what": "uncapped",
                              "quote": _q(s, 0)})
        for m in re.finditer(r"(?:capped\s+at|cap\s+of|up\s+to\s+a\s+cap\s+of|to\s+a\s+maximum\s+of|maximum\s+(?:of\s+)?)\s*"
                             r"(?:the\s+first\s+)?(" + _CUR + r"\s?" + _NUM + r"(?:" + _MULT + r")?|" + _NUM +
                             r"(?:\s?(?:million))?\s+(?:oz|ounces)(?:\s+of\s+(?:gold|silver)(?:\s+equivalent)?)?)", s, re.I):
            if not re.search(r"royalt|NSR|stream", s, re.I):
                continue
            amt_txt = m.group(1)
            if "$" in amt_txt:
                ms = money_spans(amt_txt, cur0)
                if not ms:
                    continue
                amount, unit = ms[0][2], ms[0][3]
            else:
                mm = re.match(r"(" + _NUM + r")(\s?million)?", amt_txt)
                amount = float(mm.group(1).replace(",", "")) * (1e6 if mm.group(2) else 1)
                unit = "oz"
            it = _interest_before(interests, si, m.start(), S)
            terms.append({"kind": "cap", "_it": it, "amount": amount, "unit": unit, "what": _q(s, m.start()),
                          "quote": _q(s, m.start())})
        for m in re.finditer(r"(?:advance(?:d)?|minimum)\s+(?:minimum\s+|advance\s+|annual\s+)?(?:\w+\s+){0,2}?"
                             r"(?:royalty|NSR)\s+payments?\s+(?:of\s+)?(" + _CUR + r"\s?" + _NUM + r"(?:" + _MULT + r")?)", s, re.I):
            ms = money_spans(m.group(1), cur0)
            if not ms:
                continue
            it = _interest_before(interests, si, m.start(), S)
            per = "annual" if re.search(r"annual", s, re.I) else ("monthly" if re.search(r"month", s, re.I) else None)
            terms.append({"kind": "minimum", "_it": it, "amount": ms[0][2], "unit": ms[0][3], "period": per,
                          "start": None, "credited": "yes" if re.search(r"credited|deductible|offset\s+against|recoverable", s, re.I) else "unstated",
                          "quote": _q(s, m.start())})
        for m in re.finditer(r"minimum\s+(?:(gold|silver|platinum)\s+)?deliveries\s+of\s+(" + _NUM + r")\s+(?:oz|ounces)", s, re.I):
            it = _nearest_interest(interests, si, S, prefer_fam="stream")
            terms.append({"kind": "minimum", "_it": it, "amount": float(m.group(2).replace(",", "")), "unit": "oz",
                          "period": "annual" if re.search(r"each|annual|per\s+year", s, re.I) else None,
                          "start": None, "credited": "unstated", "quote": _q(s, m.start())})
        # area of interest / influence / stream area / royalty coverage
        am = re.search(r"area\s+of\s+(?:interest|influence)|Stream\s+Area:|royalty\s+property\s+covers|"
                       r"(?:are|is)\s+subject\s+to\s+the\s+(?:Stream|Royalty)", s)
        if am and not re.search(r"^Figure|\bFigure\s+\d", s[:40]):
            it = None
            # the interest named in the same clause
            best = None
            for x in interests:
                if si in x.sents:
                    d = abs(x.pos - am.start()) if x.first == si else 999
                    if best is None or d < best[0]:
                        best = (d, x)
            if best and best[0] < 999:
                it = best[1]
            if it is None:
                it = _nearest_interest(interests, si, S, prefer_fam="stream" if re.search("Stream", s) else None)
            if not any(x["kind"] == "aoi" and x["_it"] is it for x in terms):
                terms.append({"kind": "aoi", "_it": it, "extent": _q(s, am.start()), "quote": _q(s, am.start())})
    # royalty stated to cover N acres / hectares in its own sentence
    for it in interests:
        if it.fam == "stream":
            continue
        s = S[it.first]
        seg = s[it.pos:it.pos + 160]
        m = re.search(r"\((\d[\d,.]*\s+(?:acres|hectares|ha))\)", seg)
        if m and not any(x["kind"] == "aoi" and x["_it"] is it for x in terms):
            terms.append({"kind": "aoi", "_it": it, "extent": m.group(1), "quote": _q(s, it.pos)})

    # ---------------- one royalty per optioned project ----------------
    # "Upon completion of the A Option or the B Option, X shall retain a 2% NSR on the project subject to the option"
    for it in list(interests):
        if it.fam == "stream" or it.split_total:
            continue
        s0 = S[it.first]
        if not re.search(r"(?:each|the)\s+(?:project|property|claims?|concession)\s+subject\s+to\s+the\s+(?:applicable\s+)?option|"
                         r"on\s+each\s+(?:such\s+)?(?:project|property|concession)\b", s0, re.I):
            continue
        prev = [k for k, bl in enumerate(blocks) if bl[-1] < it.first and it.first - bl[0] <= 20 and
                any(v["comp"] in ("cash", "shares", "work", "share_value") for si in bl for v in deal[si]["vals"])]
        if len(prev) < 2:
            continue
        def bprop(k):
            for si in blocks[k]:
                for x in (S[si - 1] if si > 0 else "", S[si]):
                    m = re.search(r"\b(?:the\s+)?((?-i:[A-Z][\w-]+(?:\s+[A-Z][\w-]+){0,2}))\s+(?:Option|Property|Project|Concession)\b", x)
                    if m and m.group(1).split()[0] not in _PROP_STOP:
                        return m.group(1)
            return None
        it.force_block = prev[-1]
        it.prop = bprop(prev[-1]) or it.prop
        it.prop_fixed = True
        for k in prev[:-1]:
            c = Interest(it.fam, it.rate, it.type_text, it.first, it.pos)
            c.prop, c.holder, c.event, c.scope, c.quote, c.metal = it.prop, it.holder, it.event, it.scope, it.quote, it.metal
            c.payer = it.payer
            c.sents = list(it.sents)
            c.spos = dict(it.spos)
            c.force_block = k
            c.prop = bprop(k) or c.prop
            c.prop_fixed = True
            interests.append(c)
            for tm in list(terms):
                if tm.get("_it") is it and tm["kind"] in ("buyback", "minimum", "cap"):
                    t2 = dict(tm)
                    t2["_it"] = c
                    terms.append(t2)

    # ---------------- considerations ----------------
    _considerations(S, interests, cur0, deal, blocks)

    # ---------------- property shown on the site ----------------
    _assign_properties(S, t, normalise(headline or ""), interests)

    # ---------------- output ----------------
    interests.sort(key=lambda x: (x.first, x.pos))
    for k, it in enumerate(interests):
        it.id = "i%d" % (k + 1)
    out_i = []
    for it in interests:
        out_i.append({"id": it.id, "type": it.fam, "type_text": it.type_text, "rate": _round(it.rate), "metal": it.metal,
                      "property": it.prop, "holder": it.holder, "payer": it.payer, "event": it.event,
                      "scope": it.scope, "quote": it.quote})
    out_c = []
    for it in interests:
        for comp, amt, cur, shared, _new in it.cons:
            rec = {"for": [it.id], "cash": None, "currency": None, "shares": None, "share_value": None,
                   "share_currency": None, "deposit": None, "work": None, "other": None, "schedule": None,
                   "paid_by": None, "paid_to": None, "shared": shared}
            rec[comp] = _round(amt)
            if comp == "share_value":
                rec["share_currency"] = cur
            elif comp != "shares":
                rec["currency"] = cur
            else:
                # a share count has no currency of its own; the record carries the deal's currency
                others = [c[2] for c in it.cons if c[0] in ("cash", "work", "deposit", "share_value") and c[2]]
                rec["currency"] = others[0] if others else cur0
            out_c.append(rec)
    out_t = []
    seen = []
    for tm in terms:
        it = tm.pop("_it", None)
        for_all = tm.pop("_for_all", False)
        if it is None:
            it = interests[0] if len(interests) == 1 else None
        if for_all:
            f = [x.id for x in interests if x.fam == "stream" and x.event != "terminated"]
        else:
            f = [it.id] if it is not None else []
        tm2 = {"kind": tm["kind"], "for": f if len(f) != 1 else f[0]}
        for k, v in tm.items():
            if k != "kind":
                tm2[k] = v
        # merge duplicate terms (same kind and key numbers) -> one term for several interests
        key = _term_key(tm2)
        dup = None
        for prev in seen:
            if prev[0] == key:
                dup = prev[1]
                break
        if dup is not None:
            fl = dup["for"] if isinstance(dup["for"], list) else [dup["for"]]
            for x in (f or []):
                if x not in fl:
                    fl.append(x)
            dup["for"] = fl if len(fl) != 1 else fl[0]
            continue
        seen.append((key, tm2))
        out_t.append(tm2)
    return {"interests": out_i, "considerations": out_c, "terms": out_t}


def _term_key(tm):
    k = tm["kind"]
    if k == "buyback":
        return (k, tm.get("pct"), tm.get("price"), tm.get("deadline"))
    if k == "stepdown":
        return (k, tm.get("from_rate"), tm.get("to_rate"), tm.get("unit"))
    if k == "stream":
        return (k, str(tm.get("for")), tm.get("metal"))
    if k in ("cap", "minimum"):
        return (k, tm.get("amount"), str(tm.get("for")))
    return (k, str(tm.get("for")))


def _same_prop(a, b):
    wa = set(re.findall(r"[a-z0-9]+", a.lower())) - {"the", "of", "and", "claims", "claim", "property", "project", "mine",
                                                       "core", "non"}
    wb = set(re.findall(r"[a-z0-9]+", b.lower())) - {"the", "of", "and", "claims", "claim", "property", "project", "mine",
                                                       "core", "non"}
    if not wa or not wb:
        return True
    return bool(wa & wb)


def _stream_prop(s, end):
    m = re.match(r"\s*(?:production\s+)?(?:from|at)\s+(?:the\s+)?(?:[A-Z][\w]*s\s+)?([A-Z0-9][\w-]*(?:\s+[A-Z][\w-]*){0,3})\s+"
                 r"(mine|project|deposit)", s[end:end + 80])
    if m:
        return m.group(1) + " " + m.group(2)
    return None


def _q(s, pos, n=25):
    words = s[max(0, pos - 60):].split()
    if pos > 60 and words:
        words = words[1:]
    return " ".join(words[:n])


def _trigger(s, pos):
    m = re.search(r"(?:until|after|once|upon|when|above|thereafter|following|on\s+sales\s+of|in\s+excess\s+of|"
                  r"not\s+payable\s+on|to\s+December|at\s+which)[^.;]{0,120}", s[pos:], re.I)
    if m:
        return m.group(0).strip()
    return None


_EVENT_VERB = re.compile(r"terminat|not\s+to\s+proceed|pre-existing|already\s+owned|existing|underlying|assum|\bsold\b|\bsells?\b|"
                         r"\bretain|\bgrant|in\s+favou?r\s+of|\bacquir|\bpurchas|\bholds?\b|\bowns?\b|subject\s+to|agreement\s+has\s+been\s+reached", re.I)


_SUFFIX = r"(?:Inc|Corp|Corporation|Ltd|Limited|Plc|PLC|LLC|Ltda|S\.A|SpA)"
_NAME = r"(?-i:[A-Z][\w&.'-]*(?:\s+(?:[A-Z][\w&.'-]*|of|and|de|del|&)){0,5})"


_NAME_CUT = {"Property", "Project", "Mine", "Columbia", "Ontario", "Quebec", "Alberta", "Canada", "BC", "President", "CEO",
             "RELEASE", "Release", "NEWS", "PRESS", "News", "Press", "Vancouver", "Toronto", "Montreal", "of",
             "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
             "December", "Inc", "Corp", "Ltd", "Limited"}


def _clean_name(nm):
    if not nm:
        return None
    w = nm.replace(",", " ").split()
    k = 0
    for i, x in enumerate(w):
        if x in _NAME_CUT or (x.endswith((".", ":")) and not re.fullmatch(r"(?:[A-Z]\.)+", x)):
            k = i + 1
    w = w[k:]
    # leading ALL-CAPS headline words glued in front of a normal-case name
    while len(w) > 2 and w[0].isupper() and len(w[0]) > 1 and any(not x.isupper() for x in w[1:]) and \
            (w[1].isupper() or len(w[0]) > 3 or w[0] in ("IN", "OF", "ON", "THE", "AND", "TO", "FOR", "AT", "A")):
        w = w[1:]
    return " ".join(w) or None


def _clean_alias(a):
    if not a:
        return None
    a = a.strip(" '\"")
    if re.search(r"TSX|CSE|NYSE|ASX|OTC|:|\d", a) or a in ("Company",):
        return None
    return a


def _issuer(t):
    """issuing company: the name before its '(... or the Company)' alias; else the dateline name that 'is pleased' /
    'announces'; else the first corporate name outside a wire dateline."""
    head = t[:2500]
    pre_tick = r"\s*,?\s*(?:[\(\[][^()\[\]]{0,60}[\)\]]\s*,?\s*)*?"
    m = re.search(r"(" + _NAME + r")\s*,?\s+" + _SUFFIX + r"\b\.?" + pre_tick +
                  r"\(([^()]{0,160}?\bthe\s+[\"']?\s?Company\s?[\"']?[^()]{0,40})\)", head)
    if m:
        al = None
        am = re.match(r"\s*[\"']?\s*([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})\s*[\"']?\s*(?:,|or\b)", m.group(2))
        if am and am.group(1) not in ("Company",) and not am.group(1).startswith("The"):
            al = am.group(1)
        return _clean_name(m.group(1)), _clean_alias(al)
    m = re.search(r"(" + _NAME + r")\s*,?\s+" + _SUFFIX + r"\b\.?" + pre_tick +
                  r"(?:\(\s*[\"']?\s?([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,2})\s?[\"']?\s*\)\s*)?"
                  r"(?:[^.()]{0,40}?)(?:(?:is|are)\s+pleased|announces|today\s+announced|reports|(?:has|have)\s+(?:entered|signed|closed|completed|agreed)|"
                  r"(?:has|have)\s+[^.()]{0,30}?signed)", head)
    if m:
        return _clean_name(m.group(1)), _clean_alias(m.group(2))
    for x in re.finditer(r"(" + _NAME + r")\s+" + _SUFFIX + r"\b\.?", head):
        if head[max(0, x.start() - 2):x.start()].strip().endswith("("):
            continue
        return _clean_name(x.group(1)), None
    return None, None


def _display(name, alias):
    if name and alias and not (set(re.findall(r"[a-z0-9]+", alias.lower())) & set(re.findall(r"[a-z0-9]+", name.lower()))):
        return "%s (%s)" % (name, alias)
    return name


def _strip_caps(nm):
    """drop a run of ALL-CAPS headline words glued in front of a normal-case company name."""
    w = nm.split()
    k = 0
    while k < len(w) - 1 and w[k].isupper() and len(w[k]) > 1 and not w[k + 1].isupper():
        k += 1
    if k and any(not x.isupper() for x in w[k:]):
        return " ".join(w[k:])
    return nm


_ROLE = r"(?:vendors?|optionors?|optioner|sellers?|purchasers?|optionees?)"


def _parties(S, t, interests, issuer, alias, iw, issuer_royco):
    """holder (who receives) and payer (owner / operator / optionee who pays) from general patterns."""
    tl = t
    # defined-term roles: "(the Vendor)", "(the "Sellers")", ", the optionor,"
    role_alias = None
    rm = re.search(r"\(\s*(?:the\s+)?[\"']?\s*(" + _ROLE + r")\s*[\"']?\s*\)|,\s+the\s+(" + _ROLE + r")\b", tl, re.I)
    if rm:
        role_alias = "the " + (rm.group(1) or rm.group(2))
    # operator / owner of a royalty property: "<mine>, owned and operated by X", "X's <Name> Project"
    _OWN = (r"(?:Project|Mine|mine|project|Property|property|Complex|deposit|Claims|claims)\b[^.;]{0,80}?"
            r"(?:owned\s+and\s+operated|operated\s+and\s+owned|operated|owned)\s+by\s+(" + _NAME + r")")
    _POSS = (r"(" + _NAME + r")(?:'s|\s+(?:LLC|Inc|Corp|Ltd)s)\s+(?:\([^()]{1,20}\)\s+)?(?:[A-Z][\w-]*\s+){1,3}(?:Gold\s+|Copper\s+)?"
             r"(?:Project|Mine|Property)")

    owners = []     # (owner, anchor words)
    for rx in (_OWN, _POSS):
        for m in re.finditer(rx, tl):
            if rx is _OWN:
                ctxw = " ".join(tl[max(0, m.start() - 60):m.start()].split()[-4:])
            else:
                ctxw = tl[m.end(1):m.end()]
            anchors = {w for w in re.findall(r"\b[A-Z][a-z]{3,}\b", ctxw)} - set(_PROP_STOP) - \
                set(m.group(1).split()) - {"Project", "Mine", "Property", "Claims", "Gold", "Copper", "Silver"}
            owners.append((_resolve_alias(m.group(1), tl), anchors))

    def operator_for(it):
        s0 = S[it.first]
        nxt = [p for x in interests if x is not it and it.first in x.spos for p in x.spos[it.first] if p > it.pos]
        seg = s0[it.pos:min(nxt) if nxt else it.pos + 250]
        for rx in (_OWN, _POSS):
            m = re.search(rx, seg)
            if m:
                return _resolve_alias(m.group(1), tl)
        words = set(re.findall(r"\b[A-Z][a-z]{3,}\b", " ".join(S[x] for x in it.sents[:3])))
        hit = sorted([(-len(an & words), k, o) for k, (o, an) in enumerate(owners) if an & words])
        if hit:
            return hit[0][2]
        distinct = {o for o, _ in owners}
        return owners[0][0] if len(distinct) == 1 else None

    # counterparty paying the issuer (issuer is the vendor): "X can acquire", "sold to X", "purchaser ... is X"
    cp = None
    for rx in (r"(" + _NAME + r")\s+(?:can|may|will|shall)\s+(?:have\s+the\s+(?:option|right)\s+to\s+)?(?:acquire|earn)\b",
               r"\bsold\s+to\s+(" + _NAME + r")", r"purchaser\s+of\s+the\s+property\s+is\s+(?:privately-owned\s+|privately\s+held\s+)?(" + _NAME + r")",
               r"\boption\s+(?:agreement\s+)?with\s+(" + _NAME + r")\s*\((?:[\"']?\w+[\"']?)\)\s+pursuant\s+to\s+which\s+(?:\w+\s+){0,2}will\s+have\s+the\s+option",
               r"(?:purchase\s+and\s+sale|sale)\s+agreement\s+with\s+(" + _NAME + r")",
               r"consideration\s+for\s+(" + _NAME + r")\s+acquiring", r"(?:under\s+option|optioned)\s+to\s+(" + _NAME + r")",
               r"option\s+(?:agreement\s+)?(?:\w+\s+){0,3}?with\s+(" + _NAME + r")"):
        m = re.search(rx, tl)
        if m and not (set(re.findall(r"[a-z0-9]+", m.group(1).lower())) & (iw | {"company"})) and \
                m.group(1).split()[0] not in _PROP_STOP:
            cp = _resolve_alias(m.group(1), tl)
            break
    # stream counterparty: "stream ... with X"
    sm = re.search(r"(?:stream|purchase\s+agreement|PMPA|streaming)\w*\s+(?:transaction\s+|agreement\s+|arrangement\s+)?(?:\([^()]{0,50}\)\s+)?with\s+(" + _NAME + r")", tl)
    stream_cp = sm.group(1) if sm else None
    am = re.search(r"(?:agreement|arrangement)\s+(?:\([^()]{0,50}\)\s+)?with\s+(" + _NAME + r")", tl)
    agreement_cp = am.group(1) if am else None

    def is_issuer(x):
        if not x:
            return False
        w = set(re.findall(r"[a-z0-9]+", x.lower()))
        return bool(w & (iw | {"company"})) or bool(re.match(r"(?:the\s+)?company$", x.strip(), re.I))

    vendors_defined = bool(re.search(r"\(\s*(?:together,?\s+)?the\s+[\"']?Vendors?[\"']?\s*\)", tl))
    for it in interests:
        _party_one(it, S, tl, issuer, issuer_royco, cp, stream_cp, agreement_cp, role_alias, vendors_defined,
                   operator_for, is_issuer)
        it.holder = _tidy(it.holder)
        it.payer = _tidy(it.payer)


def _party_one(it, S, tl, issuer, issuer_royco, cp, stream_cp, agreement_cp, role_alias, vendors_defined, operator_for, is_issuer):
    if True:
        s = S[it.first]
        pre = s[:it.pos]
        post = s[it.pos:]
        h = it.holder
        operator = operator_for(it)
        if it.fam == "stream":
            if h is None:
                if it.receiver and not it.receiver_is_issuer:
                    h = it.receiver
                elif it.receiver_is_issuer or (it.event == "terminated" and issuer_royco) or it.event == "acquired":
                    h = issuer
                elif stream_cp:
                    h = stream_cp
            if it.payer is None:
                if it.event == "granted":
                    it.payer = issuer
                elif it.event == "terminated" and not issuer_royco:
                    it.payer = issuer
                elif it.event in ("acquired", "terminated"):
                    it.payer = stream_cp or agreement_cp or operator
            it.holder = h
            return
        if h is None:
            m = None
            for x in re.finditer(r"grant\w*\s+(?:to\s+)?(?:the\s+)?(" + _ROLE + r"|" + _NAME + r")\s+(?:an?\s+)?(?:aggregate\s+)?(?=\d|a\b|an\b|royalty|NSR)", pre):
                m = x
            if m is None:
                m = re.search(r"grant\w*\s+to\s+(?:the\s+)?(" + _ROLE + r"|" + _NAME + r")", pre)
            if m:
                h = m.group(1)
        if h is None:
            for x in it.sents:
                m = re.search(r"\bsold\b[^;]{0,100}?\bto\s+(" + _NAME + r")", S[x])
                if m:
                    h = m.group(1)
                    break
        if h is None:
            m = re.search(r"^[^;]{0,120}?\bpayable\s+to\s+(?:the\s+)?(" + _ROLE + r"|" + _NAME + r")", post)
            if m:
                h = m.group(1)
        if h is None and it.event == "granted":
            m = re.search(r"^[^;]{0,90}?\bto\s+(?:the\s+)?(?:certain\s+of\s+the\s+|each\s+of\s+the\s+)?(" + _ROLE + r"|" + _NAME + r")", post)
            if m and m.group(1).split()[0] not in _PROP_STOP:
                h = m.group(1)
        if h is None:
            m = re.search(r"^[^;]{0,120}?(?:retained|held|granted)\s+by\s+(?:the\s+)?(" + _ROLE + r"|" + _NAME + r")", post)
            if m:
                h = m.group(1)
        if h is None:
            m = re.search(r"^[^;]{0,160}?in\s+favou?r\s+of\s+(?:the\s+)?(" + _ROLE + r"|" + _NAME + r")", post, re.I)
            if m:
                h = m.group(1)
        if h is None:
            m = re.search(r"^[^;]{0,60}?\((" + _NAME + r")\s+\d+(?:\.\d+)?%\s+and\s+(" + _NAME + r")\s+\d+(?:\.\d+)?%\)", post)
            if m:
                h = m.group(1) + " and " + m.group(2)
        if h is None:
            m = None
            for x in re.finditer(r"((?:[Tt]he\s+)?(?:(?:property\s+)?" + _ROLE + r"|" + _NAME + r"|it))\s+(?:will|shall|would|has|have|may)?\s*(?:also\s+)?"
                                 r"(?:be\s+entitled\s+to|retain|retains|retained|retaining|holds|hold|will\s+be\s+granted|be\s+granted)\b(?!\s+(?:a|the|an)\s+(?:\d+-year\s+)?(?:right|option))", pre[-160:]):
                gap = pre[-160:][x.end():]
                if it.event != "existing" and (len(gap) <= 45 or re.search(r"\d%|royalt|\bNSR\b", gap, re.I)):
                    m = x
            if m:
                h = m.group(1)
                if h.lower() == "it":
                    cm = re.search(r"\b(?:If|if|when|When)\s+(" + _NAME + r")\s+elects", pre)
                    h = cm.group(1) if cm else None
        if h is not None and re.match(r"(?:the\s+)?company$", h.strip(), re.I) and issuer:
            h = issuer
        if h is not None and h.split()[0] in _PROP_STOP and not re.match(r"(?:The|the)\s", h):
            h = None
        if h is None and it.event in ("held",) and re.search(r"\b(?:its|our)\s+(?:pre-existing\s+|existing\s+)?\d", pre[-40:] + post[:6], re.I):
            h = issuer
        if h is None and re.search(r"\b[A-Z]\w*s\s+pre-existing\s*$", pre[-40:]):
            h = issuer
        if h is None and it.event == "acquired" and issuer:
            h = issuer
        if h is None and it.event in ("retained", "granted") and it.scope == "subject" and \
                "revenue share" not in (it.type_text or "").lower():
            if role_alias:
                h = role_alias
            elif agreement_cp and not is_issuer(agreement_cp):
                h = agreement_cp
        it.holder = h
        # payer
        if it.payer is None:
            if it.event == "sold" or (it.event == "existing" and re.search(r"previously\s+sold", s, re.I)):
                it.payer = issuer
            elif it.event in ("retained", "granted") and "revenue share" not in (it.type_text or "").lower():
                if is_issuer(h) or (h is None and issuer_royco):
                    it.payer = cp
                else:
                    it.payer = issuer
            elif it.event == "existing":
                if re.search(r"assum\w+\s+(?:\w+\s+){0,4}(?:obligation|responsibility)", s, re.I):
                    it.payer = issuer
            elif it.event in ("acquired", "held", "bought_back"):
                it.payer = operator if it.event != "bought_back" else issuer
                if it.payer is None and it.event == "acquired" and (vendors_defined or re.search(r"\bvendors?\b", s, re.I)):
                    it.payer = agreement_cp


_PKEY = r"(?:(?-i:Property|Properties|Project|Mine|Claims|Claim\s+Block|Concessions?|Pluton|Deposit|Licen[cs]e|PROPERTY|PROJECT|MINE)|property|properties|project|mine|mines|claims|concessions?|deposit)"
_PNAME_RE = re.compile(r"((?-i:[A-Z][\w'&.-]*(?:\s+(?:[A-Z][\w'&.-]*|de|del|des|du|la|and)){0,4}))((?:\s+(?:(?-i:[a-z][\w-]*)|(?-i:[A-Z][a-z]+-[A-Za-z][\w-]*))){0,2})\s+"
                       r"(" + _PKEY + r")\b")
_PNAME_BAD = {"The", "This", "These", "Its", "Our", "Their", "An", "A", "Option", "Company", "Agreement", "Optioned", "Each",
              "All", "Such", "Said", "Subject", "Acquired", "Additional", "Royalty", "Stream", "Mining", "Exploration", "New",
              "Vendor", "Vendors", "Optionor", "Remaining", "Other", "Both", "Two", "Three", "Four", "Five", "Its",
              "Acquire", "Acquires", "Acquired", "Acquiring", "Acquisition", "Options", "Optioning", "Enters", "Announces",
              "Signs", "Closes", "Completes", "Sells", "Buys", "Reports", "Expands", "Increases", "Begins", "Into", "To",
              "Of", "On", "At", "In", "For", "And", "Amends", "Update", "Grants", "Grant", "Sale", "Purchase", "Agreement",
              "Definitive", "Binding", "Letter", "Intent", "Terms", "Under", "Upon", "Following", "Within", "With", "From"}


_COMMOD = {"gold", "silver", "copper", "zinc", "nickel", "uranium", "lithium", "cobalt", "platinum", "palladium", "rare", "earth",
           "antimony", "tin", "graphite", "tungsten", "polymetallic", "base", "metals", "precious", "copper-gold", "gold-silver"}


def _pnames(txt):
    out = []
    for m in _PNAME_RE.finditer(txt):
        name = m.group(1).strip()
        toks = name.split()
        cut0 = [k for k, x in enumerate(toks) if x.endswith("'s") or (x.endswith(".") and not re.fullmatch(r"(?:[A-Z]\.)+", x))]
        if cut0 and cut0[-1] < len(toks) - 1:
            toks = toks[cut0[-1] + 1:]
        while toks and (toks[0] in _PNAME_BAD or toks[0].title() in _PNAME_BAD or toks[0] in _PROP_STOP or
                        toks[0].isupper() and len(toks) > 1 and not toks[1].isupper()):
            toks = toks[1:]
        while toks and toks[-1] in ("and", "de", "del", "des", "du", "la"):
            toks = toks[:-1]
        # "Eldorado Gold's Tocantinzinho" -> "Tocantinzinho"; "Resources Inc. Shares Rattlesnake Hills" -> "Rattlesnake Hills"
        cut = [k for k, x in enumerate(toks) if x.endswith("'s") or (x.endswith(".") and not re.fullmatch(r"(?:[A-Z]\.)+", x))]
        if cut and cut[-1] < len(toks) - 1:
            toks = toks[cut[-1] + 1:]
        if not toks:
            continue
        desc = m.group(2).strip().split()
        if desc and desc[0].lower() in ("and", "or", "of", "the", "to", "in", "on", "for", "with", "that", "which", "is", "are", "at",
                                        "into", "enters", "by", "from", "its", "a", "an"):
            continue
        if any(x in ("Corporation", "Corp", "Inc", "Ltd", "Limited") for x in toks):
            continue
        key = m.group(3)
        if key.isupper():
            # ALL-CAPS headline: keep the (up to) two name words in front of the keyword, minus commodities and verbs
            tt = [x.title() for x in (toks + desc)]
            while tt and (tt[-1].lower().replace("/", " ").split()[0] in _COMMOD or "/" in tt[-1]):
                tt = tt[:-1]
            tt = tt[-2:]
            bad = [k for k, x in enumerate(tt) if x in _PNAME_BAD or x in _PROP_STOP]
            if bad:
                tt = tt[bad[-1] + 1:]
            if not tt:
                continue
            toks, desc, key = tt, [], key.title()
        if re.search(r"\b(?:Corp|Inc|Ltd|Limited|Resources|Royalties|Mining|Minerals|Metals|Exploration|Gold\s+Corp|Ventures|Capital)\b",
                     " ".join(toks)) and len(toks) > 1 and toks[-1] in ("Resources", "Royalties", "Mining", "Minerals", "Metals",
                                                                       "Exploration", "Ventures", "Capital"):
            continue
        if toks[-1].endswith("s") and toks[-1][:-1] and re.match(r".*[a-z]s$", toks[-1]) and len(toks) == 1 and \
                toks[0] not in ("Claims",) and False:
            continue
        phrase = " ".join(toks + desc + [key])
        out.append((m.start(), " ".join(toks), phrase))
    return out


def _assign_properties(S, t, headline, interests):
    """property as the release names it: the named property next to the royalty, the defined term the royalty sentence
    points to ("on the Property"), or the release's single headline property."""
    defined = {}
    for m in re.finditer(r"(" + _PNAME_RE.pattern + r")\s*\(\s*(?:the\s+)?[\"']?\s?(?:[\w-]+,?\s+or\s+the\s+)?(Property|Project|Claims|Properties|"
                         r"Mine)\s?[\"']?\s*\)", t):
        pn = _pnames(m.group(1))
        if pn:
            defined.setdefault(m.group(5).lower(), pn[0][2])
    aliases = {}
    for m in re.finditer(r"(" + _PNAME_RE.pattern + r")\s*\(\s*[\"']?\s?((?-i:[A-Z][A-Za-z]{1,8}))\s?[\"']?\s*\)", t):
        pn = _pnames(m.group(1))
        if pn and m.group(5) not in ("Property", "Project", "Claims", "Mine", "TSX", "TSXV", "CSE"):
            aliases.setdefault(m.group(5), pn[0][2])
    body_names = {}
    for _, n, ph in _pnames(t.replace(headline, " ") if headline else t):
        body_names.setdefault(n, ph)

    def body_version(n, ph):
        toks = n.split()
        for k in range(len(toks)):
            suf = " ".join(toks[k:])
            if suf in body_names:
                return body_names[suf]
        body = t.replace(headline, " ") if headline else t
        best = None
        for i in range(len(toks)):
            for j in range(len(toks), i, -1):
                run = toks[i:j]
                if run[0] in ("and", "de", "del", "des", "du", "la") or run[-1] in ("and", "de", "del", "des", "du", "la"):
                    continue
                if all(x.lower() in _COMMOD or x in _PNAME_BAD for x in run):
                    continue
                if len(run) == 1 and (len(run[0]) < 5 or run[0].lower() in _COMMOD or run[0] in _PNAME_BAD):
                    continue
                if re.search(r"\b" + re.escape(" ".join(run)) + r"\b", body):
                    if best is None or len(run) > len(best):
                        best = run
                    break
        if best and len(best) < len(toks):
            return " ".join(best) + " " + ph.split()[-1]
        return ph
    hp = {p[1]: body_version(p[1], p[2]) for p in _pnames(headline)}
    main = list(hp.values())[0] if len(hp) == 1 else None
    if main is None and len(hp) > 1:
        # several properties in the headline: the one the first deal sentence names
        for x in S[1:12]:
            if re.search(r"acqui|option|purchas", x, re.I):
                inx = [ph for n, ph in hp.items() if n in x]
                if len(inx) == 1:
                    main = inx[0]
                break
    if main is None:
        lead = _pnames(t[:1500])
        names = {}
        for _, n, ph in lead:
            names.setdefault(n, ph)
        if len(names) == 1:
            main = list(names.values())[0]
    for it in interests:
        if it.prop_fixed:
            continue
        if it.fam == "stream" and it.prop:
            continue
        s0 = S[it.first]
        nxt = [p for x in interests if x is not it and it.first in x.spos for p in x.spos[it.first] if p > it.pos]
        end = min(nxt) if nxt else it.pos + (320 if it.fam == "stream" else 170)
        seg = s0[it.pos:end].replace('"', "")
        prop = None
        m = re.search(r"\b(?:on|at|covering|over|from|in)\s+(?:the\s+|its\s+|all\s+of\s+the\s+|each\s+of\s+the\s+|a\s+portion\s+of\s+the\s+)?", seg)
        for mm in re.finditer(r"\b(?:on|at|covering|over|from|in)\s+(?:the\s+|its\s+|all\s+of\s+the\s+|each\s+of\s+the\s+|the\s+core\s+|"
                              r"non-core\s+)?", seg):
            pn = _pnames(seg[mm.end():mm.end() + 90])
            if pn and pn[0][0] == 0:
                prop = pn[0][2]
                break
        if prop is None and aliases:
            am = re.search(r"\b(?:on|at|from|over|covering)\s+(?:the\s+)?(" + "|".join(re.escape(a) for a in aliases) + r")\b", seg)
            if am:
                prop = aliases[am.group(1)]
        if prop is None:
            # "1% and 0.5% at A and B, respectively"
            rm = re.search(r"(\d+(?:\.\d+)?)%\s+and\s+(\d+(?:\.\d+)?)%[^;]{0,40}?\b(?:at|on|for)\s+(?:the\s+)?"
                           r"((?-i:[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,3}))\s+and\s+((?-i:[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,3})),?\s+respectively", s0)
            if rm and it.rate is not None:
                if abs(float(rm.group(1)) - it.rate) < 0.011:
                    prop = rm.group(3)
                elif abs(float(rm.group(2)) - it.rate) < 0.011:
                    prop = rm.group(4)
        if prop is None:
            gm = re.search(r"\b(?:on|over|covering|to)\s+(?:the|these|this|such)\s+(Property|Project|Claims|claims|property|project|Properties|claim)\b", seg)
            if gm:
                prop = defined.get(gm.group(1).lower())
        if prop is None:
            # the property named just before the royalty in its sentence, or in the deal sentence(s) just before
            pre = re.split(r"[;:]", s0[max(0, it.pos - 110):it.pos])[-1].replace('"', "")
            pn = _pnames(pre)
            om = list(re.finditer(r"(?-i:([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,2}))\s+Option\b", pre))
            if pn:
                prop = pn[-1][2]
            elif om and om[-1].group(1).split()[0] not in _PNAME_BAD:
                prop = om[-1].group(1)
        if prop is None and it.fam != "stream":
            for back in (1, 2):
                j = it.first - back
                if j < 0:
                    break
                pn = _pnames(S[j])
                other = any(x is not it and j in x.spos for x in interests)
                if pn and not other and re.search(r"\binterest\s+in|\bacquir|\bpurchas|\boption", S[j], re.I):
                    prop = pn[0][2]
                    break
        if prop is None and it.fam == "stream":
            # "the Ming Gold Stream" -> the property whose name it carries
            for x in re.finditer(r"(?-i:([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,2}))\s+(?:Gold\s+|Silver\s+|Copper\s+)?(?:Stream|PMPA)\b", t):
                w0 = x.group(1).split()[0]
                if w0 in _PNAME_BAD or w0 in _PROP_STOP:
                    continue
                cand = [ph for _, n, ph in _pnames(t) if n.split()[0] == w0]
                if cand:
                    prop = cand[0]
                    break
        if prop is None:
            prop = main
        it.prop = prop


def _tidy(name, subject=False):
    """cut a captured name at a sentence break: object names keep the first part, subject names the last."""
    if not name:
        return name
    parts = [p.strip() for p in re.split(r"(?<=[a-z0-9])\.\s+(?=[A-Z])", name) if p.strip()]
    if len(parts) > 1:
        good = [p for p in parts if len(p) >= 3 and p.split()[0] not in ("The", "This", "These", "It", "NSR", "Stream",
                                                                          "Royalty", "GRR", "Each", "All")]
        name = good[0] if good else parts[0]
    name = re.sub(r"\s+(?:The|This|These|It)$", "", name.strip())
    return name.strip(" ,.")


def _resolve_alias(x, t):
    """'MVT' -> the name defined with ("MVT") in the release; 'European Uranium Resources' -> '... (EUU)'."""
    if not x:
        return x
    if not re.fullmatch(r"[A-Z]{2,6}", x.strip()):
        m = re.search(re.escape(x.strip()) + r"(?:\s+" + _SUFFIX + r"\.?)?,?\s*\(\s*[\"']?\s?([A-Z][A-Za-z]{1,9})\s?[\"']?\s*\)", t)
        if m and m.group(1) not in ("TSX", "TSXV", "CSE", "NYSE") and not (set(re.findall(r"[a-z0-9]+", m.group(1).lower())) &
                                                                         set(re.findall(r"[a-z0-9]+", x.lower()))):
            return "%s (%s)" % (x, m.group(1))
        return x
    m = re.search(r"(" + _NAME + r")(?:\s+" + _SUFFIX + r"\.?)?,?\s*\(\s*[\"']?\s?" + re.escape(x.strip()) + r"\s?[\"']?\s*\)", t)
    return (m.group(1) + (" " + m.group(0)[len(m.group(1)):].split("(")[0].strip(" ,") if False else "")) if m else x


def _local_event(it, s, deal_ctx):
    """event from the words right around the mention, or None."""
    pre = s[max(0, it.pos - 60):it.pos].lower()
    win = s[max(0, it.pos - 30):it.pos + 140].lower()
    if re.search(r"previously\s+(?:sold|granted|acquired|issued)", win):
        return "existing"
    if re.search(r"acqui\w+\s+(?:an?\s+|the\s+)?existing\s+$", pre):
        return "acquired"
    if re.search(r"entitled\s+to\s+(?:an?\s+)?$", pre):
        return "granted"
    if re.search(r"subject\s+to\s+(?:an?\s+|the\s+)?$", pre) and not re.search(r"existing|underlying", s[max(0, it.pos - 30):it.pos + 60], re.I):
        return "retained" if deal_ctx else "existing"
    return None


def _event(it, ctx, deal_ctx, issuer_receives):
    low = ctx.lower()
    if re.search(r"terminat|not\s+to\s+proceed|cancell?ed", low) and it.fam == "stream" and it.rate is None:
        return "terminated"
    if re.search(r"pre-existing|already\s+owned|already\s+holds", low):
        return "held"
    if re.search(r"existing\s+(?:\d+(?:\.\d+)?%\s+)?(?:net|nsr|royalty|gross)|subject\s+to\s+an?\s+(?:existing\s+)?"
                 r"(?:\d+(?:\.\d+)?%\s+)?(?:underlying|existing)|underlying|assum\w+\s+(?:\w+\s+){0,3}obligation", low):
        return "existing"
    if it.fam == "stream":
        if it.receiver_is_issuer is not None:
            return "acquired" if it.receiver_is_issuer else "granted"
        return "granted" if issuer_receives else "acquired"
    if re.search(r"\bsold\b|\bsells?\b|\bselling\b", low) and re.search(r"royalt|grr|nsr", low) and \
            not re.search(r"retain", low):
        return "sold"
    if re.search(r"\bretain|\bretaining\b|\bretains\b|\bretained\b", low):
        if not deal_ctx or re.search(r"drill|results|assays?", low) and not re.search(r"option|acquir|sale|sold|purchase", low):
            return "held"
        return "retained"
    if re.search(r"\bgrant|\bgranted\b|\bwill\s+be\s+granted\b|agreement\s+has\s+been\s+reached", low):
        return "granted"
    if re.search(r"in\s+favou?r\s+of", low):
        return "retained" if deal_ctx else "existing"
    if re.search(r"\bacquir|\bacquisition|\bpurchas|\bbuy\b", low):
        return "acquired"
    if re.search(r"\bholds?\b|\bowns?\b|\bits\s+\d", low):
        return "held"
    if re.search(r"subject\s+to", low):
        return "existing"
    return "existing" if not deal_ctx else "retained"


def _nearest_interest(interests, si, S, prefer_fam=None):
    best = None
    for it in interests:
        if prefer_fam and it.fam != prefer_fam:
            continue
        for x in it.sents:
            d = si - x
            score = d if d >= 0 else 1000 - d
            if best is None or score < best[0]:
                best = (score, it)
    if best is None and prefer_fam:
        return _nearest_interest(interests, si, S)
    return best[1] if best else None


def _interest_before(interests, si, pos, S):
    """interest whose mention precedes position pos in sentence si (same sentence first, else nearest earlier)."""
    best = None
    for it in interests:
        for x in it.sents:
            if x == si:
                p = it.pos if it.first == si else 0
                d = (0, pos - p if p <= pos else 10000 + p - pos)
            elif x < si:
                d = (si - x, 0)
            else:
                d = (1000 + x - si, 0)
            if best is None or d < best[0]:
                best = (d, it)
    return best[1] if best else None


_FRAC = {"one half": 0.5, "one-half": 0.5, "half": 0.5, "three-quarters": 0.75, "three quarters": 0.75,
         "one third": 1 / 3.0, "one-third": 1 / 3.0, "two-thirds": 2 / 3.0, "a quarter": 0.25, "one quarter": 0.25}


def _buybacks(s, si, interests, S, cur0):
    out = []
    # interest this right belongs to
    it = None
    m_of = re.search(r"of\s+the\s+(\d+(?:\.\d+)?)%\s+(?:[\w-]+\s+){0,3}?(?:" + _TYPE_ALT + r")", s, re.I)
    if m_of:
        r = float(m_of.group(1))
        for x in interests:
            if x.rate is not None and abs(x.rate - r) < 0.011 and x.fam != "stream":
                it = x
                break
    if it is None:
        m_und = re.search(r"underlying\s+royalty", s, re.I)
        if m_und:
            # "... right to purchase 1.0% of the underlying royalty" -> the underlying interest
            buy_pos = _BUY_RE.search(s).start()
            for x in interests:
                if x.first == si and x.pos < buy_pos and "underlying" in S[si][max(0, x.pos - 5):x.pos + 40].lower():
                    it = x
        if it is None:
            buy_pos = _BUY_RE.search(s).start()
            it = _interest_before([x for x in interests if x.fam != "stream"] or interests, si, buy_pos, S)
    if it is None or it.fam == "stream":
        return out
    of_rate = it.rate
    if it.split_total and re.search(r"(?<![\d.])%s%%" % re.escape(("%g" % it.split_total)), s):
        of_rate = it.split_total
    # split into tranche clauses: "... for $X, and thereafter ... for $Y"; "$A for the first 1% and $B for an additional 0.5%"
    # who may exercise: a named or role subject -> the payor; passive wording with no agent -> unclear
    who = "unclear"
    bm0 = _BUY_RE.search(s)
    win = s[max(0, bm0.start() - 70):bm0.end() + 60]
    am = re.search(r"([\w']+)\s+(?:may|can|shall|will|has|have|having|retains?|is|was|being|been)\b[^.;()]{0,45}?"
                   r"(?:buy|purchas|repurchas|acquire|reduc|right|option)", win, re.I)
    if am and am.group(1).lower() not in ("which", "it", "that", "nsr", "royalty", "grr", "interest", "and", "or", "who"):
        who = "payor"
    if re.search(r"(?:option|right)\s+for\s+(?:the\s+)?[A-Z][\w']*\s+to\s+(?:buy|purchas|repurchas|acquire|reduce)|"
                 r"reduced\s+to\s+\d+(?:\.\d+)?%\s+(?:by|for|upon|on)\b[^.;]{0,40}?(?:payment|paying)|"
                 r"bought\s+back\s+from|purchased\s+(?:by|from)\s+|repurchased\s+(?:by|from)\s+|bought\s+back\s+by", win, re.I):
        who = "payor"
    deadline = None
    dm = re.search(r"(?:at\s+any\s+time(?:\s+prior\s+to\s+commercial\s+production)?|(?:any\s?time\s+)?(?:prior\s+to|before)\s+"
                   r"(?:the\s+)?(?:commencement\s+of\s+)?commercial\s+production|on\s+or\s+(?:prior\s+to|before)\s+\w+\s+\d{1,2},\s+\d{4}|"
                   r"within\s+\d+\s+days\s+after[^,.;]{0,80})", s, re.I)
    if dm:
        deadline = dm.group(0)

    # several prices: "on or prior to D for US$X, and thereafter, at any time, for US$Y"
    prices = [p for p in money_spans(s, cur0)]
    wprices = word_money(s, cur0)
    # pct parsing: the first share named in the buyback clause, ignoring "of the R% NSR" (the base rate)
    pct = None
    bm = _BUY_RE.search(s)
    seg = s[max(0, bm.start() - 60):bm.end() + 120]
    lo = max(0, bm.start() - 80)
    cands = []
    for m in re.finditer(r"(?<![\d.])(\d+(?:\.\d+)?)%", s[lo:bm.end() + 150]):
        p0 = lo + m.start()
        pre = s[max(0, p0 - 14):p0].lower()
        post = s[p0 + len(m.group(0)):p0 + len(m.group(0)) + 25].lower()
        if re.search(r"(?:of\s+the(?:\s+up\s+to)?|of\s+this|of\s+its|leaving\s+(?:\w+\s+){0,2}(?:with\s+)?an?|reduced\s+to|up\s+to\s+the)\s*$", pre):
            continue
        if re.match(r"\s*(?:interest|ownership|of\s+the\s+payable)", post):
            continue
        if p0 < bm.start() - 30 and not re.match(r"\s*of\s+(?:the|this|which)\b", post):
            continue
        if p0 < bm.start() and re.match(r"\s*(?:[\w-]+\s+){0,2}?(?:" + _TYPE_ALT + r")", post + s[p0 + len(m.group(0)) + 25:p0 + len(m.group(0)) + 60], re.I) \
                and not re.match(r"\s*of\s+(?:the|this|which)\b", post):
            continue
        cands.append((p0, float(m.group(1)), "pct"))
    for m in re.finditer(r"\b(one[- ]half|half|three[- ]quarters|one[- ]third|two-thirds|all\b|the\s+(?:NSR|royalty|GRR)\b)", s[lo:bm.end() + 120], re.I):
        p0 = lo + m.start()
        if p0 < bm.start() - 30:
            continue
        tok = m.group(1).lower().replace(" ", "-")
        if tok.startswith("the"):
            if not re.match(r"\s*(?:for|may\s+be|can\s+be|at\s+any)", s[lo + m.end():lo + m.end() + 15], re.I):
                continue
            cands.append((p0, 1.0, "frac"))
        elif tok == "all":
            cands.append((p0, 1.0, "frac"))
        else:
            cands.append((p0, _FRAC.get(tok, _FRAC.get(tok.replace("-", " "), 0.5)), "frac"))
    cands.sort()
    reduced = re.search(r"(?:may\s+be\s+|be\s+)?reduced?\s+(?:the\s+(?:NSR|royalty|GRR)\s+)?to\s+(\d+(?:\.\d+)?)%", seg, re.I)
    if not cands and re.search(r"\b(?:which|it)\s+(?:may|can)\s+be\s+(?:re)?purchased|(?:right|option)\s+to\s+(?:re)?purchase\s+(?:the|such)\s+(?:NSR|royalty)\b",
                               seg, re.I):
        cands = [(bm.start(), 1.0, "frac")]
    if reduced and of_rate is not None:
        pct = of_rate - float(reduced.group(1))
    elif cands:
        p0, v, kind = cands[0]
        if kind == "frac":
            pct = v * of_rate if of_rate is not None else None
        else:
            pct = v
    # "40% of the NSR" -> fraction of the NSR (r11: main NSR)
    if pct is not None and of_rate is not None and pct > of_rate + 0.011:
        pct = round(pct / 100.0 * of_rate, 4)
    # tranche pattern: "$A for the first 1% and $B for an additional 0.5%"
    tr = list(re.finditer(r"(" + _CUR + r"\s?" + _NUM + r"(?:" + _MULT + r")?(?:\s+(?:USD|CAD|Cdn))?)\s+for\s+(?:the\s+first|an\s+additional|"
                          r"the\s+remaining|a\s+further)\s+(\d+(?:\.\d+)?)%", s, re.I))
    if len(tr) >= 2:
        for x in tr:
            ms = money_spans(x.group(1), cur0)
            out.append(_bb(it, float(x.group(2)), of_rate, ms[0][2], ms[0][3], None, deadline, who, s, x.start()))
        return out
    # "buy back 1% NSR for $500,000 ... and the remaining 1% NSR for 1,000,000 Canadian dollars"
    tr2 = list(re.finditer(r"(?:buy\s?back|purchase|and\s+the\s+remaining|and\s+an\s+additional|and\s+a\s+further|"
                           r"and\s+the\s+(?:second|other))\s+(\d+(?:\.\d+)?)%\s+(?:of\s+the\s+)?"
                           r"(?:NSR\s+|royalty\s+)?(?:\w+\s+){0,4}?for\s+(?:a\s+payment\s+of\s+|an\s+additional\s+|a\s+further\s+)?(" + _CUR + r"?\s?" + _NUM +
                           r"(?:" + _MULT + r")?)(?:\s+(?:Canadian\s+dollars|US\s+dollars|USD|CAD))?", s, re.I))
    if len(tr2) >= 2:
        for x in tr2:
            ms = money_spans(x.group(2), cur0) or [(0, 0, float(re.sub(r"[^\d.]", "", x.group(2).split()[0]) or 0) *
                                                   (1e6 if "million" in x.group(2).lower() else 1), cur0)]
            out.append(_bb(it, float(x.group(1)), of_rate, ms[0][2], ms[0][3], None, deadline, who, s, x.start()))
        return out
    # price(s)
    pr = [p for p in prices if not re.match(r"\s*(?:per\s+(?:ounce|oz|share)|/oz)", s[p[1]:p[1] + 12], re.I)]
    # drop amounts that are royalty-payment thresholds ("in excess of C$4,000,000") or caps
    pr = [p for p in pr if not re.search(r"(?:in\s+excess\s+of|exceed\w*|capped\s+at|maximum\s+of)\s*$", s[max(0, p[0] - 25):p[0]], re.I)]
    # keep only prices after the buyback cue start - 10
    pr = [p for p in pr if p[0] >= bm.start() - 10 or re.search(r"buy", s[p[1]:p[1] + 40], re.I)]
    if not pr and wprices:
        pr = [w for w in wprices if w[0] >= bm.start() - 10]
    if not pr:
        m1 = re.search(r"for\s+(?:a\s+|the\s+)?(?:one-time\s+)?(\d+(?:\.\d+)?)\s+million", s[bm.start():], re.I)
        if m1:
            pr = [(0, 0, float(m1.group(1)) * 1e6, cur0)]
    per1 = re.search(r"(?:per|for\s+each|for\s+every)\s+(?:each\s+)?(\d+(?:\.\d+)?)%", s, re.I)
    if len(pr) >= 2 and re.search(r"thereafter|after\s+which|and\s+(?:after|before)", s, re.I):
        # one right priced by date (r06)
        dls = re.findall(r"(on\s+or\s+(?:prior\s+to|before)\s+\w+\s+\d{1,2},\s+\d{4}|thereafter(?:,\s+at\s+any\s+time)?)", s, re.I)
        for k, p in enumerate(pr[:3]):
            out.append(_bb(it, pct, of_rate, p[2], p[3], None, dls[k] if k < len(dls) else deadline, who, s, p[0]))
        return out
    price = cur = None
    ptxt = None
    # first price in the clause; a "per 1%" unit price is multiplied out unless a total is also stated
    unit = [p for p in pr if re.match(r"\s*(?:\(?\s*)?(?:per|for\s+each|for\s+every)\s+(?:each\s+)?\d", s[p[1]:p[1] + 25], re.I)]
    whole = [p for p in pr if p not in unit]
    tranche_add = re.search(r"(?:,\s*|\s)(?:and|plus)\s+(?:an\s+additional|a\s+further|the\s+remaining|the\s+second|another)\s+"
                            r"(\d+(?:\.\d+)?%|half|one[- ]half)", s[bm.start():], re.I)
    if tranche_add and len(whole) >= 2:
        whole = whole[:1]
    if whole:
        price, cur = whole[0][2], whole[0][3]
        if per1 and pct and float(per1.group(1)) > 0 and not unit and len(whole) == 1:
            ptxt = s[max(0, whole[0][0] - 5):whole[0][1] + 30]
            price = price * pct / float(per1.group(1))
    elif unit and pct and per1 and float(per1.group(1)) > 0:
        price, cur = unit[0][2] * pct / float(per1.group(1)), unit[0][3]
        ptxt = s[max(0, unit[0][0] - 5):unit[0][1] + 30]
    elif re.search(r"fair\s+(?:market\s+)?value", s, re.I):
        ptxt = "fair value"
    if price is None and pct is None and not re.search(r"buy\s+down|buy-down|buy\s?back|repurchase", s, re.I):
        return out
    out.append(_bb(it, pct, of_rate, price, cur, ptxt, deadline, who, s, bm.start()))
    # a second right in the same sentence: "and an additional 40% of the NSR may be purchased for fair value"
    m2 = re.search(r"(?:and|while)\s+an\s+additional\s+(\d+(?:\.\d+)?)%\s+of\s+the\s+(?:NSR|royalty)\s+may\s+be\s+purchased\s+for\s+"
                   r"(fair\s+value|" + _CUR + r"\s?" + _NUM + r"(?:" + _MULT + r")?)", s, re.I)
    if not m2 and tranche_add and pr:
        # "... and an additional 0.5% for $1,000,000"
        seg2 = s[bm.start() + tranche_add.start():]
        tok = tranche_add.group(1).lower()
        p2 = float(tok.rstrip("%")) if tok.endswith("%") else (0.5 * of_rate if of_rate else None)
        if p2 is not None and of_rate is not None and p2 > of_rate:
            p2 = round(p2 / 100.0 * of_rate, 4)
        ms = money_spans(seg2, cur0) or word_money(seg2, cur0)
        if ms:
            out.append(_bb(it, p2, of_rate, ms[0][2], ms[0][3], None, None, who, s, bm.start() + tranche_add.start()))
    if m2:
        p2 = float(m2.group(1))
        if of_rate is not None and p2 > of_rate:
            p2 = round(p2 / 100.0 * of_rate, 4)
        ms = money_spans(m2.group(2), cur0)
        out.append(_bb(it, p2, of_rate, ms[0][2] if ms else None, ms[0][3] if ms else None,
                       None if ms else m2.group(2), None, who, s, m2.start()))
    return out


def _bb(it, pct, of_rate, price, cur, ptxt, deadline, who, s, pos):
    return {"kind": "buyback", "_it": it, "pct": _round(pct), "of_rate": of_rate, "price": _round(price),
            "currency": cur, "price_text": ptxt, "deadline": deadline, "who": who, "quote": _q(s, pos)}


# --------------------------------------------------------------------------------------------
# considerations
# --------------------------------------------------------------------------------------------

_SHARES_RE = re.compile(r"(?<![\d.,$])(" + _NUM + r")(\s?million)?\s+(?:(?:(?-i:[A-Z][A-Za-z]*)|common|consideration|"
                        r"ordinary|additional|new|fully\s+paid)\s+){0,3}(shares|units)\b", re.I)
_SEP_RE = re.compile(r"(?:one-time\s+(?:cash\s+)?payment\s+of|purchase\s+price\s+of|for\s+a\s+one-time\s+payment\s+of)\s*$", re.I)
_NEW_RE = re.compile(r"\b(?:additional|further|another)\b", re.I)
_COND_RE = re.compile(r"\bbonus\b|entitled\s+to|upon\s+(?:the\s+)?(?:completion|delivery|announcement|achievement|publication)\s+of|"
                      r"production\s+decision|\bif\s+(?:a|an|the|any)\b|in\s+the\s+event|milestone|under\s+certain\s+circumstances|"
                      r"\bshould\s+\w+\s+(?:elect|exercise)|one-time\s+payment\s+to\s+increase", re.I)


def _components(s, cur0, consumed):
    """-> list of dict(comp, v, cur, tot, paren, pos, sep, fin)"""
    out = []
    depth = []
    d = 0
    for ch in s:
        if ch == "(":
            d += 1
        depth.append(d)
        if ch == ")" and d > 0:
            d -= 1
    paren_total = []
    for m in re.finditer(r"\(([^()]{0,200})\)", s):
        if re.search(r"\btotal", m.group(1), re.I):
            paren_total.append((m.start(), m.end()))

    def in_total_paren(p):
        return any(x <= p < y for x, y in paren_total)

    def fin(a, b):
        return bool(_FIN_RE.search(s[max(0, a - 120):b + 60]))

    def shouty(a, b):
        seg = [c for c in s[max(0, a - 40):b + 40] if c.isalpha()]
        return len(seg) > 12 and sum(1 for c in seg if c.isupper()) > 0.75 * len(seg)

    monies = money_spans(s, cur0)
    last = (0, None)
    for (a, b, v, cur) in monies:
        if any(x <= a < y for x, y in consumed) or shouty(a, b):
            continue
        before = s[max(0, a - 90):a]
        after = s[b:b + 70]
        bl = before.lower()
        al = after.lower()
        if re.match(r"\s*(?:per\s+(?:ounce|oz|share|common\s+share|unit|tonne|pound|lb|year|annum|month)|/oz|/t\b|/lb|/month)", al):
            continue
        if re.search(r"(?:exercisable\s+at|exercise\s+price\s+of|price\s+of|at\s+a\s+price\s+of|in\s+excess\s+of|inclusive\s+of|"
                     r"including|capped\s+at|cap\s+of|maximum\s+of|up\s+to|value\s+of\s+the\s+company|lesser\s+of|greater\s+of)\s*(?:approximately\s+)?$", bl):
            continue
        if re.match(r"\s+of\s+(?:which|the)\b|,?\s+(?:consisting|comprised|comprising|made\s+up)\s+of", al) or \
                re.search(r"of\s+which\s*$", bl):
            continue
        if re.match(r"\s*(?:in\s+)?cash\s+on\s+hand", al):
            continue
        tot = bool(re.search(r"(?:totall?ing|totals?\s+of|a\s+total\s+of|aggregate\s+(?:total\s+)?(?:of\s+)?|"
                             r"in\s+the\s+aggregate\s+amount\s+of|total\s+(?:upfront\s+)?(?:cash\s+)?consideration\s+(?:paid\s+)?"
                             r"(?:for\s+[\w\s]{0,40}?)?(?:of|was)|total\s+(?:of\s+)?)\s*(?:approximately\s+)?(?:" + _CUR + r")?$",
                             bl[-60:])) or in_total_paren(a)
        comp = None
        if re.match(r"\s*(?:in\s+)?(?:\(?further\)?\s+|additional\s+)?(?:exploration|work)\s*(?:and\s+development\s+)?"
                    r"(?:expenditures?|commitments?|spending|program)|\s*(?:work\s+)?commitment|\s*in\s+expenditures|"
                    r"\s*on\s+exploration|\s*(?:in\s+|of\s+)?exploration\s+(?:and\s+development\s+)?expenditures|\s*(?:in|of)\s+(?:exploration\s+)?work\b", al) or \
                re.search(r"(?:expenditures?|work\s+commitments?)\s+(?:commitments?\s+)?(?:of|totall?ing|in\s+the\s+aggregate\s+"
                          r"amount\s+of)\s+(?:at\s+least\s+)?(?:approximately\s+)?(?:USD\s+|US\s+)?$|"
                          r"(?:incur|spending|spend)\s+(?:a\s+further\s+|at\s+least\s+|an\s+additional\s+)?$|"
                          r"cost\s+of\s+not\s+less\s+than\s*$|\bfunding\s+$", bl):
            comp = "work"
        elif re.match(r"\s*(?:in|of)\s+(?:common\s+|consideration\s+)?(?:shares?|share\s+payments)|\s*payable\s+in\s+(?:common\s+)?shares|"
                      r"\s*(?:Australian\s+dollars\s+)?in\s+shares", al) or \
                re.search(r"having\s+(?:a|an)\s+(?:deemed\s+|aggregate\s+)?value\s+of\s+(?:approximately\s+)?$|"
                          r"equivalent\s+to\s+approximately\s*$|equaling\s*$", bl):
            comp = "share_value"
        elif re.search(r"upfront|deposit|advance\s+amount", bl[-60:] + " " + al[:40]) or \
                re.search(r"in\s+exchange\s+for\s+(?:a\s+)?(?:total\s+)?consideration\s+of\s*$", bl):
            comp = "deposit"
        elif re.match(r"\s*(?:USD\s+|CAD\s+|Canadian\s+dollars\s+)?(?:in\s+)?cash|\s*(?:USD\s+)?(?:in\s+)?cash\s+payments?", al) or \
                re.search(r"(?:cash\s+payments?\s+(?:totall?ing|of)|cash\s+consideration\s+of|pay(?:ing)?\s+(?:to\s+)?(?:[A-Z][\w]*\s+){0,3}|"
                          r"paid\s+(?:to\s+)?(?:[A-Z][\w]*\s+){0,3}|payments?\s+of|consideration\s+of|price\s+of|the\s+sum\s+of|"
                          r"payment\s+(?:to\s+[A-Z][\w]*\s+)?of)\s*(?:a\s+total\s+of\s+|an\s+aggregate\s+of\s+|approximately\s+)?"
                          r"(?:USD\s+)?$", bl[-70:]):
            comp = "cash"
        elif re.search(r"\bfor\s+(?:a\s+total\s+of\s+|approximately\s+)?(?:USD\s+)?$", bl[-30:]) and \
                re.search(r"acquir|purchas|\bsold\b|\bsell|\bsale\b|transfer|exchange|consideration|option|royalt|\bNSR\b|stream", s, re.I):
            comp = "cash"
        elif len(monies) <= 2 and re.search(r"\bpa(?:y|id|yable|yments?|ying)\b|purchase\s+price", s, re.I):
            comp = "cash"
        elif last[1] and a - last[0] < 90 and \
                not re.search(r"shares?|expenditure|work|royalt|NSR|exploration|[.;:]|\b(?:for|of)\s*$", s[last[0]:a], re.I):
            comp = last[1]      # "$15,000 within 5 days, $20,000 on the first anniversary and $30,000 ..."
        if comp is None:
            continue
        last = (b, comp)
        out.append({"comp": comp, "v": v, "cur": cur, "tot": tot, "paren": depth[a] > 0 and not in_total_paren(a),
                    "pos": a, "sep": bool(_SEP_RE.search(bl)), "fin": fin(a, b),
                    "for": bool(re.search(r"\bfor\s+(?:a\s+|the\s+)?(?:cash\s+)?(?:payment\s+of\s+)?$", bl[-30:]))})
    for m in _SHARES_RE.finditer(s):
        a = m.start()
        if any(x <= a < y for x, y in consumed) or shouty(a, m.end()):
            continue
        before = s[max(0, a - 60):a].lower()
        after = s[m.end():m.end() + 40].lower()
        if m.group(3).lower() == "units" and not re.search(r"consideration", s, re.I):
            continue
        if re.search(r"(?:inclusive\s+of|including|of\s+which|options?\s+to\s+purchase|warrants?\s+to\s+purchase|"
                     r"exercisable\s+into|up\s+to)\s*$", before):
            continue
        if re.match(r"\s*(?:issued\s+and\s+)?outstanding|\s*at\s+a\s+price|\s*for\s+gross", after):
            continue
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if m.group(2) and v < 1000:
            v *= 1e6
        if v < 1000:
            continue
        tot = bool(re.search(r"(?:aggregate\s+of|a\s+total\s+of|totall?ing|total\s+of)\s*(?:approximately\s+)?$", before)) or \
            in_total_paren(a)
        out.append({"comp": "shares", "v": v, "cur": None, "tot": tot, "paren": depth[a] > 0 and not in_total_paren(a),
                    "pos": a, "sep": False, "fin": fin(a, m.end()), "for": False})
    # shares x deemed / issue price -> share value
    pm = re.search(r"(?:deemed|underlying|issue)\s+price\s+of\s+(" + _CUR + r"\s?" + _NUM + r")\s+per\s+(?:common\s+)?share", s, re.I)
    if pm:
        sh = [x for x in out if x["comp"] == "shares" and not x["fin"]]
        if sh and not any(x["comp"] == "share_value" for x in out):
            ms = money_spans(pm.group(1), cur0)
            if ms:
                x = dict(sh[0])
                x["comp"] = "share_value"
                x["v"] = sh[0]["v"] * ms[0][2]
                x["cur"] = ms[0][3]
                out.append(x)
    # "satisfy the payment obligation of $X through the issuance of N shares" -> share value
    if re.search(r"(?:satisf|settl)\w*\s+.{0,80}(?:through|by)\s+(?:the\s+)?issu", s, re.I):
        for x in out:
            if x["comp"] == "cash":
                x["comp"] = "share_value"
    return [x for x in out if not x["fin"]]


def _sentence_values(comps, s):
    """collapse one sentence's component mentions -> list of dict(comp, v, cur, tot, sep)"""
    res = []
    by = {}
    for c in comps:
        by.setdefault(c["comp"], []).append(c)
    mm = re.search(r"each\s+of\s+the\s+((?:\w+(?:,\s*|\s+and\s+)){1,5}\w+)\s+anniversar", s, re.I)
    mult = len(re.split(r",\s*|\s+and\s+", mm.group(1))) if mm else 1
    for k, lst in by.items():
        tots = [c for c in lst if c["tot"]]
        if tots:
            seen = []
            for c in tots:
                if not any(abs(c["v"] - v) < 1 for v in seen):
                    seen.append(c["v"])
                    res.append({"comp": k, "v": c["v"], "cur": c["cur"], "tot": True, "sep": False})
            continue
        seps = [c for c in lst if c["sep"]]
        rest = [c for c in lst if not c["sep"]]
        for c in seps:
            res.append({"comp": k, "v": c["v"], "cur": c["cur"], "tot": False, "sep": True})
        if rest:
            outside = [c for c in rest if not c["paren"]]
            use = outside if outside else rest
            res.append({"comp": k, "v": sum(c["v"] for c in use) * mult, "cur": use[0]["cur"], "tot": False, "sep": False})
    return res


def deal_sentences(S, cur0):
    """-> dict si -> dict(vals, raw, instal, term, new, roy)"""
    deal = {}
    for si, s in enumerate(S):
        if not _DEAL_RE.search(s) and not ((si - 1) in deal and _INSTAL_RE.search(s)):
            continue
        consumed = []
        bm = _BUY_RE.search(s)
        if bm and _ROYWORD.search(s) and not re.search(r"(?:paid|recently\s+paid)\b.{0,60}buy\s?back", s, re.I):
            m = re.search(r"\(with\s+an?\s+\d+(?:\.\d+)?%\s+buy\s?back[^)]*\)", s, re.I)
            if m:
                consumed.append((m.start(), m.end()))
            else:
                consumed.append((max(0, bm.start() - 60), len(s)))
        for m in re.finditer(r"(?:capped\s+at|cap\s+of|maximum\s+of|in\s+excess\s+of)\s*[^,;]{0,40}", s, re.I):
            consumed.append((m.start(), m.end()))
        for m in re.finditer(r"advance(?:d)?\s+(?:minimum\s+)?(?:\w+\s+){0,2}?(?:royalty|NSR)\s+payments?|minimum\s+(?:\w+\s+)?deliveries",
                             s, re.I):
            consumed.append((m.start(), len(s)))
        if re.search(r"\b(?:royalty|NSR|stream)\s+(?:revenue|payments?\s+to\s+the\s+company)|made\s+royalty\s+payments", s, re.I) and \
                not re.search(r"acquir|consideration|purchase\s+price|in\s+exchange", s, re.I):
            continue
        raw = _components(s, cur0, consumed)
        if not raw:
            continue
        deal[si] = {"vals": _sentence_values(raw, s), "raw": raw, "instal": bool(_INSTAL_RE.search(s)),
                    "term": bool(re.search(r"terminat", s, re.I)), "new": bool(_NEW_RE.search(s)),
                    "cond": bool(_COND_RE.search(s)),
                    "roy": bool(_ROYWORD.search(s))}
    return deal


def deal_blocks(deal):
    """consecutive deal sentences (gap <= 2); a conditional (bonus / milestone) sentence closes its block."""
    blocks = []
    for si in sorted(deal):
        if blocks and si - blocks[-1][-1] <= 2 and not deal[blocks[-1][-1]].get("cond") and \
                not (deal[si].get("cond") and False):
            blocks[-1].append(si)
        else:
            blocks.append([si])
    return blocks


def block_records(b, deal, skip=None):
    """-> list of dict(comp, v, cur, new)"""
    skip = skip or set()
    totals = {}
    for si in b:
        for v in deal[si]["vals"]:
            if v["tot"]:
                totals[v["comp"]] = True
    recs = []
    acc = {}
    for si in b:
        d = deal[si]
        for v in d["vals"]:
            if (si, v["comp"]) in skip:
                continue
            k = v["comp"]
            if totals.get(k):
                if v["tot"] or v["sep"] or not d["instal"]:
                    recs.append({"comp": k, "v": v["v"], "cur": v["cur"], "new": d["new"]})
                    acc[k] = None
                continue
            if d["instal"] and acc.get(k) is not None and not v["sep"]:
                recs[acc[k]]["v"] += v["v"]
            else:
                recs.append({"comp": k, "v": v["v"], "cur": v["cur"], "new": d["new"]})
                acc[k] = None if v["sep"] else len(recs) - 1
    return recs


def _considerations(S, interests, cur0, deal, blocks):
    if not deal:
        return
    streams = [x for x in interests if x.fam == "stream" and x.event != "terminated"]
    royalties = [x for x in interests if x.fam != "stream" and "revenue share" not in (x.type_text or "").lower()]
    terminated = [x for x in interests if x.event == "terminated"]

    def add(it, recs, shared):
        for r in recs:
            it.cons.append((r["comp"], r["v"], r["cur"], shared, r.get("new", False)))

    # per-mention pairing: "sold X for $A, in addition to Y previously sold for $B"
    skip = set()
    for si, d in deal.items():
        fors = [v for v in d["raw"] if v["for"] and v["comp"] == "cash"]
        if len(fors) < 2:
            continue
        ments = []
        for it in royalties:
            for p in it.spos.get(si, []):
                ments.append((p, it))
        ments.sort(key=lambda x: x[0])
        if len({id(x[1]) for x in ments}) < 2:
            continue
        for v in fors:
            prev = [m for m in ments if m[0] < v["pos"]]
            if prev:
                prev[-1][1].cons.append(("cash", v["v"], v["cur"], False, False))
        skip.add((si, "cash"))

    brecs = [(b, block_records(b, deal, skip)) for b in blocks]

    # termination payments -> terminated interest
    if terminated:
        keep = []
        for b, recs in brecs:
            tb = [si for si in b if deal[si]["term"]]
            if tb:
                for it in terminated:
                    add(it, block_records(tb, deal, skip), False)
                rest = [si for si in b if not deal[si]["term"]]
                if rest:
                    keep.append((rest, block_records(rest, deal, skip)))
            else:
                keep.append((b, recs))
        brecs = keep

    if streams:
        allrecs = []
        for b, recs in brecs:
            for r in recs:
                if r["comp"] in ("deposit", "shares", "share_value"):
                    allrecs.append(r)
        for it in streams:
            add(it, allrecs, len(streams) > 1)

    if royalties:
        assigned = {}
        for it in royalties:
            if it.event in ("held", "terminated"):
                continue
            if it.force_block is not None:
                assigned.setdefault(it.force_block, []).append(it)
                continue
            best = None
            for x in sorted(it.sents):
                for k, (b, recs) in enumerate(brecs):
                    if not [r for r in recs if r["comp"] != "deposit"]:
                        continue
                    if b[0] <= x <= b[-1]:
                        dd = 0
                    elif b[-1] < x:
                        dd = x - b[-1]
                        if dd > 4:
                            continue
                    else:
                        dd = (b[0] - x) + 0.5
                        if dd > 3.5:
                            continue
                    if best is None or dd < best[0]:
                        best = (dd, k)
                if best is not None and best[0] == 0:
                    break
            if best is not None:
                assigned.setdefault(best[1], []).append(it)
        # a release-level royalty deal (the price sentence names the royalties) applies to unassigned subject royalties
        done = {id(x) for v in assigned.values() for x in v}
        roy_blocks = [k for k, (b, recs) in enumerate(brecs) if recs and any(deal[si]["roy"] for si in b)]
        if len(roy_blocks) == 1:
            k = roy_blocks[0]
            for it in royalties:
                if id(it) in done or it.event in ("held", "terminated", "existing"):
                    continue
                assigned.setdefault(k, []).append(it)
        # conditional-payment blocks (bonus / milestone) follow the royalty deal just before them
        for k, (b, recs) in enumerate(brecs):
            if k in assigned or not recs or not all(deal[si].get("cond") for si in b):
                continue
            prevk = [j for j in assigned if brecs[j][0][-1] < b[0] and b[0] - brecs[j][0][-1] <= 4]
            if prevk:
                assigned[k] = list(assigned[max(prevk, key=lambda j: brecs[j][0][-1])])
                continue
            near = [it for it in royalties if it.event not in ("held", "terminated") and
                    any(0 < b[0] - x <= 3 for x in it.sents)]
            if near:
                assigned[k] = near
        for k, its in assigned.items():
            recs = [r for r in brecs[k][1] if r["comp"] != "deposit"]
            per = _per_recipient(S, deal, brecs[k][0], its) if len(its) > 1 else None
            for it in its:
                if per is not None:
                    add(it, per[id(it)], False)
                else:
                    add(it, recs, len(its) > 1)

    # de-duplicate near-equal components per interest (keep the more precise figure); "further"/"additional" are new
    for it in interests:
        res = []
        for c in it.cons:
            dup = None
            if not c[4]:
                for j, r in enumerate(res):
                    if r[0] == c[0] and abs(r[1] - c[1]) <= max(1.0, 0.012 * max(r[1], c[1])):
                        dup = j
                        break
            if dup is None:
                res.append(c)
            elif _precision(c[1]) > _precision(res[dup][1]):
                res[dup] = c
        it.cons = res


_RECIP_RE = re.compile(r"\bto\s+(?:the\s+)?(?:property\s+)?(?:vendors?,?\s+|optionors?,?\s+)?"
                       r"((?-i:[A-Z][\w.&'-]*(?:\s+[A-Z][\w.&'-]*){0,4}))(?:\s*\(((?-i:[A-Z]{2,6}))\))?")


def _per_recipient(S, deal, block, its):
    """payments to several named recipients in one sentence -> per-interest records when each holder matches one."""
    holders = []
    for it in its:
        h = it.holder or ""
        toks = {w for w in re.findall(r"[A-Za-z0-9]+", h) if len(w) >= 3 and w[0].isupper()}
        if not toks:
            return None
        holders.append(toks)
    for si in block:
        s = S[si]
        recs = [m for m in _RECIP_RE.finditer(s)]
        if len(recs) < 2:
            continue
        segs = []
        start = 0
        for m in recs:
            name = m.group(1)
            words = set(re.findall(r"[A-Za-z0-9]+", name))
            initials = "".join(w[0] for w in name.split() if w[0].isupper())
            if m.group(2):
                words.add(m.group(2))
            words.add(initials)
            segs.append((start, m.end(), words))
            start = m.end()
        match = {}
        for it, toks in zip(its, holders):
            hit = [j for j, sg in enumerate(segs) if toks & sg[2]]
            if len(hit) != 1:
                return None
            match[id(it)] = hit[0]
        if len(set(match.values())) != len(its):
            return None
        out = {}
        for it in its:
            a, b, _ = segs[match[id(it)]]
            vals = [v for v in deal[si]["raw"] if a <= v["pos"] < b]
            out[id(it)] = [{"comp": v["comp"], "v": v["v"], "cur": v["cur"], "new": False}
                           for v in _sentence_values(vals, s[a:b])]
        # other sentences of the block (if any) are not split
        return out
    return None


def _precision(v):
    s = ("%.2f" % v).rstrip("0").rstrip(".")
    return len(s.rstrip("0"))


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------

def parse_tune_file(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    lines = raw.split("\n")
    head = lines[0]
    m = re.match(r"####\s+(\d+)\s+\[[^\]]*\]\s+(\S+)\s+\S+\s+\|\s*(.*)$", head)
    n, ticker, headline = (int(m.group(1)), m.group(2), m.group(3)) if m else (None, "", "")
    k = raw.find("FULL TEXT")
    text = raw[k + len("FULL TEXT"):] if k >= 0 else ""
    return n, ticker, headline, text


def main(argv):
    if len(argv) < 3:
        print("usage: royterms_reader.py TUNE_DIR OUT.json")
        return 2
    d, outp = argv[1], argv[2]
    files = sorted(f for f in os.listdir(d) if re.match(r"full_\d+\.txt$", f))
    res = []
    times = []
    for f in files:
        n, ticker, headline, text = parse_tune_file(os.path.join(d, f))
        t0 = time.time()
        r = read(headline, text, ticker)
        times.append(time.time() - t0)
        r = {"n": n, "interests": r["interests"], "considerations": r["considerations"], "terms": r["terms"]}
        res.append(r)
    json.dump(res, open(outp, "w"), indent=1)
    if times:
        sys.stderr.write("read %d releases; mean %.4fs max %.4fs per release\n" % (len(times), sum(times) / len(times),
                                                                                     max(times)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
