"""TITLECASE_V2 (2026-09-28): turn an ALL-CAPS release headline into proper Title Case.

Replaces the body of portal/text_helpers.smart_title (which now calls smart_title() here and falls back to the old
code if this module is missing or raises). Same gate as before: only headlines that are at least 80% capital letters
are changed; anything already in mixed case is returned untouched.

What it fixes over the old rule:
  * A word was kept in capitals whenever it matched ANY ticker on the watchlist, so GOLD, FOR, DRILL, NEW, ONE... stayed
    shouted ("Lake Victoria GOLD Identifies ... Route FOR Imwelo"). Now a ticker stays in capitals only when the word
    is not an ordinary English word (per the lexicon below).
  * Mining abbreviations missing from the old list came out as words: "Rc Drilling", "G/T". Now RC, DD, AISC, MCTO,
    g/t, oz, km... come out right.
  * "ON", "IT", "LA", "AM", "PM" were always capitalised ("Based ON", "LA Colorada"); now only in context
    (", ON" = Ontario; a time before AM/PM).
  * "JAPAN'S" became "Japan'S"; dotted initials "B.C." became "B.c."; Roman numerals "PHASE II" became "Phase Ii";
    "NI 43-101" became "Ni 43-101".
  * Brand spellings (McEwen, IAMGOLD, NexGold, enCore, i-80) come from how the name is written in our own
    mixed-case headlines: portal/title_lexicon.json, built by build_lex.py from the release database.
"""
from __future__ import annotations

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LEX_PATH = os.path.join(HERE, "title_lexicon.json")

RSQ = chr(0x2019)          # right single quote
DASHES = {"-", chr(0x2013), chr(0x2014), "|", ":", ";"}

ACRONYMS = {
    # exchanges, regulators, listings
    "TSX", "TSXV", "CSE", "OTCQB", "OTCQX", "OTC", "OTCMKTS", "NYSE", "AMEX", "NASDAQ", "SEC", "SEDAR", "OSC", "BCSC",
    "ASC", "ASX", "LSE", "AIM", "FSE", "FINRA", "CIRO", "IIROC", "JSE", "BVL", "BMV", "SGX", "HKEX", "NEO",
    # titles and corporate
    "CEO", "CFO", "COO", "CTO", "CMO", "CSO", "CRO", "VP", "EVP", "SVP", "GM", "MD", "PLC", "LLC", "LP", "LLP", "SA",
    "SAS", "SPA", "AG", "AB", "ASA", "NV", "BV", "AGM", "AGSM", "EGM", "SGM", "MCTO", "CTO", "IPO", "ETF", "RSU", "DSU",
    "PSU", "ESOP", "ESG", "NCIB", "RTO", "SPAC", "LOI", "MOU", "MOA", "JV", "NDA", "NSR", "GR", "NPI", "ROFR", "EPCM",
    "EPC", "M&A", "R&D", "YOY", "YTD", "QOQ", "EBITDA", "AI", "KPI", "FAQ", "CEO's", "TMX", "CNW",
    # currencies, countries, provinces
    "USD", "CAD", "CDN", "AUD", "EUR", "GBP", "JPY", "CNY", "HKD", "CHF", "US", "USA", "UK", "EU", "UAE", "DRC", "PRC",
    "PNG", "NZ", "RSA", "BC", "AB", "QC", "SK", "MB", "NS", "NL", "NB", "PEI", "YT", "NWT", "NU", "NT",
    # mining and geology
    "NI43-101", "43-101", "43-101F1", "PEA", "PFS", "DFS", "FS", "BFS", "NPV", "IRR", "AISC", "AIC", "MRE", "JORC",
    "QAQC", "QA/QC", "QP", "UG", "DSO", "CIM", "EIS", "EIA", "ESIA", "EA", "EPA", "BLM", "USFS", "NOI", "POO", "EAC",
    "ROM", "BIF", "VMS", "VHMS", "SEDEX", "MVT", "IOCG", "IOA", "LCT", "PGM", "PGMS", "PGE", "PGES", "REE", "REES",
    "HREE", "LREE", "TREO", "TREE", "CRM", "EV", "EVS", "BESS", "LFP", "NMC", "SX", "EW", "SXEW", "SX-EW", "HPA",
    "HPQ", "RC", "DD", "RAB", "AC", "HQ", "NQ", "PQ", "BQ", "TSF", "SAG", "CIL", "CIP", "CIC", "ADR", "ISR", "ISL",
    "DLE", "GEO", "GEOS", "AUEQ", "CUEQ", "AGEQ", "ZNEQ", "NIEQ", "EM", "IP", "VLF", "VTEM", "MT", "XRD", "XRF",
    "ICP", "ICP-MS", "LIDAR", "UAV", "CSAMT", "AMT", "ZTEM", "TDEM", "HLEM", "BHEM", "DHEM", "FLEM", "MAG", "TMI",
    "LME", "COMEX", "LBMA", "BHP", "PPA", "MW", "MWH", "GW", "KWH", "HVAC", "LNG", "CO2", "GHG",
    # periods and times
    "Q1", "Q2", "Q3", "Q4", "H1", "H2", "FY", "CY", "MTD", "QTD",
    "URL", "API", "PDF", "SEO", "NFT", "OK",
}
# Capitalised only in context (see _token): these are also everyday words.
CONTEXT_ONLY = {"ON", "AM", "PM", "LA", "ID", "PE", "OR", "IN", "ME", "MA", "HI", "OH", "OK", "CO", "IT"}
ACRONYMS -= CONTEXT_ONLY - {"IT", "OK"}
PROVINCES_CTX = {"ON", "PE", "OR", "IN", "ME", "MA", "HI", "OH", "CO", "ID", "LA"}

ELEMENTS = {
    "Au", "Ag", "Cu", "Ni", "Zn", "Pb", "Co", "Fe", "Pt", "Pd", "Li", "Mo", "Mn", "Sn", "Ti", "Cr", "W", "Bi", "Sb", "Te",
    "Hg", "Cd", "Be", "Mg", "Al", "Si", "Ga", "Tl", "Nb", "Ta", "Zr", "Hf", "Sc", "Y", "La", "Ce", "Pr", "Nd", "Sm",
    "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "U", "V", "Rh", "Ir", "Os", "Ru", "Re", "Ge", "In", "As",
    "U3O8", "V2O5", "Li2O", "TiO2", "Fe2O3", "CaCO3", "CuEq", "AuEq", "AgEq", "NiEq", "ZnEq", "WO3", "MoS2", "LiOH",
    "Li2CO3", "ZnO", "MgO", "CaF2", "K2O", "P2O5", "Nb2O5", "Ta2O5",
}
ELEMENTS_LOWER = {e.lower(): e for e in ELEMENTS}
# One- or two-letter element symbols that are also words or initials: only as a symbol when a grade/number is near.
ELEMENT_CTX = {"in", "as", "be", "co", "w", "u", "y", "v", "la", "pr", "re", "ho", "er", "tm", "os", "ir", "ge", "ta",
               "hf", "sc", "ce", "eu", "gd", "tb", "dy", "lu", "yb", "sm", "nd", "tl", "ga", "si", "al", "mg", "cd",
               "hg", "te", "bi", "cr", "ti", "mn", "fe", "sn", "rh", "ru", "nb", "zr", "li", "mo", "pd", "pt"}

UNITS = {"g/t", "gpt", "oz", "koz", "moz", "oz/t", "lb", "lbs", "mlbs", "mlb", "km", "m", "cm", "mm", "kg", "g", "t",
         "kt", "mt", "mtpa", "ktpa", "tpd", "tph", "ppm", "ppb", "ha", "km2", "m2", "m3", "cps", "g/l", "mg/l", "ft",
         "mw", "kw", "kv", "bbl", "boe"}
SMALL = {"a", "an", "and", "as", "at", "but", "by", "de", "del", "des", "du", "en", "for", "from", "in", "into",
         "is", "nor", "of", "on", "onto", "or", "per", "so", "the", "to", "up", "upon", "via", "vs", "vs.", "with", "yet",
         "over", "y", "e", "da", "do", "dos", "das", "von", "van", "der"}   # casefix-r4: La/Le/Les stay capitalised
TIMEZONES = {"EST", "EDT", "PST", "PDT", "MST", "MDT", "CST", "CDT", "UTC", "GMT", "ET", "PT", "CET", "AEST", "AEDT"}
EXCH_BEFORE = re.compile(r"^\W*(?:TSX|TSXV|TSX-V|TSX\.V|CSE|OTCQB|OTCQX|OTC|OTCMKTS|NYSE|NYSE-A|NASDAQ|ASX|AIM|LSE|FSE|"
                         r"FRA|FRANKFURT)\W*:$|^\W*(?:SYMBOL|TICKER)\W*:?$", re.I)
ROMAN = {"II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII", "XIII", "XIV", "XV", "XX"}
DOTTED = re.compile(r"^(?:[A-Za-z]\.)+[A-Za-z]?$")
PUNCT_SPLIT = re.compile(r"^(\W*)(.*?)(\W*)$", re.DOTALL)
HAS_DIGIT = re.compile(r"\d")

_LEX = None
_TICKERS = None


def _lexicon():
    global _LEX
    if _LEX is None:
        try:
            with open(LEX_PATH) as f:
                d = json.load(f)
            _LEX = (d.get("special") or {}, set(d.get("words") or ()))
        except Exception:
            _LEX = ({}, set())
    return _LEX


def _tickers():
    global _TICKERS
    if _TICKERS is None:
        try:
            from portal import text_helpers as TH
            _TICKERS = set(getattr(TH, "_TICKERS", set()) or set())
        except Exception:
            _TICKERS = set()
    return _TICKERS


def _cap(w):
    return w[:1].upper() + w[1:].lower() if w else w


def _plain(core):
    """Title-case one alphabetic word, with apostrophes handled (JAPAN'S -> Japan's, O'BRIEN -> O'Brien)."""
    for q in ("'", RSQ):
        if q in core:
            a, _, b = core.partition(q)
            if len(a) == 1 and len(b) > 1 and a.upper() in ("O", "D", "L"):
                return a.upper() + q + _cap(b)
            return _cap(a) + q + b.lower()
    return _cap(core)


def _word(core, ctx):
    """core: letters only (maybe with - / . ' inside). ctx: dict(first, prev, next, prev_digit, next_digit)."""
    special, words = _lexicon()
    up = core.upper()
    low = core.lower()
    near_num = ctx["prev_digit"] or ctx["next_digit"] or ctx.get("prev_unit", False)
    # 1. dotted initials: B.C., U.S., S.A.
    if DOTTED.match(core):
        return up
    # 2. units after a number: 3.11 G/T, 1,200 OZ, 300 M
    if low in UNITS and ctx["prev_digit"]:
        return low
    # 3. NI 43-101
    if up == "NI" and re.match(r"[0-9]{2}-[0-9]{3}", ctx["next"]):     # casefix-r5: NI 43-101, NI 62-103
        return "NI"
    # 4. context-only abbreviations
    if up in ("AM", "PM") and ctx["prev_digit"]:
        return up
    if up in PROVINCES_CTX and ctx["prev"].endswith(",") and not ctx["next"]:
        return up                               # "..., Timmins, ON" at the end
    if up in PROVINCES_CTX and ctx["prev"].endswith(",") and ctx["next"][:1] in ("", "(", "-", chr(0x2013)):
        return up
    if up == "MT" and ctx["trail"].startswith("."):
        return "Mt"                             # MT. TODD -> Mt. Todd
    # casefix-r3: time zones only after a time; a symbol after an exchange name or "symbol"
    if up in TIMEZONES:
        return up if (ctx["prev_digit"] or ctx["prev"].strip(".,").upper() in ("AM", "PM", "A.M", "P.M")) else _plain(core)
    if EXCH_BEFORE.match(ctx["prev"]) and len(core) <= 6 and core.isalpha() and up not in ("SYMBOL", "SYMBOLS"):
        if ctx["prev"].rstrip().endswith(":") or (low not in words and low not in SMALL):
            return up
    # 5. Roman numerals
    if up in ROMAN:
        return up
    if up == "LIFE" and ctx["next"].upper().startswith("OFFERING"):
        return "LIFE"                           # Listed Issuer Financing Exemption
    # 5b. an element symbol next to a grade or width: 0.5 G/T AU, 1.2% CU, 2.1% LI2O
    if low in ELEMENTS_LOWER and near_num and low not in ("in", "as", "be"):
        return ELEMENTS_LOWER[low]
    # 6. lexicon: how our own mixed-case headlines write this word (acronyms, brands, units)
    form = special.get(low)
    if form and up not in CONTEXT_ONLY and not (low in SMALL and not ctx["first"]):
        if low in UNITS and not ctx["prev_digit"]:
            pass
        elif ctx["first"] and form[:1].islower() and low not in ("i-80", "ienergy", "enCore".lower()):
            return form[:1].upper() + form[1:] if form.islower() else form
        else:
            return form
    # 7. curated acronyms
    if up in ACRONYMS:
        return up
    # 8. element symbols (always for unambiguous ones; the short word-like ones only next to a number)
    if low in ELEMENTS_LOWER and low not in ("in", "as", "be") and (low not in ELEMENT_CTX or near_num or len(low) > 2):
        if not (low in words and not near_num):
            return ELEMENTS_LOWER[low]
    # 9. tickers stay in capitals only when they are not ordinary words
    if up in _tickers() and len(up) >= 2 and low not in words and low not in SMALL and up not in CONTEXT_ONLY:  # casefix-r6
        return up
    # 10. hyphenated / slashed words: each part on its own
    for sep in ("-", "/"):
        if sep in core and len(core) > 2:
            parts = core.split(sep)
            out = []
            for i, p in enumerate(parts):
                if not p:
                    out.append(p)
                    continue
                c2 = dict(ctx)
                c2["first"] = ctx["first"] and i == 0
                c2["prev_digit"] = ctx["prev_digit"] if i == 0 else False
                c2["next_digit"] = ctx["next_digit"] if i == len(parts) - 1 else False
                c2["trail"] = ""
                out.append(_word(p, c2) if not HAS_DIGIT.search(p) else p)
            if sep == "-" or not ctx["first"]:
                return sep.join(out)
            return sep.join(out)
    # 11. small words
    if low in SMALL and not ctx["first"]:
        return low
    return _plain(core)


def _is_shouting(s):
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) >= 0.80


def smart_title(s):
    if not s:
        return s or ""
    if not _is_shouting(s):
        return s
    toks = s.split()
    out = []
    first = True
    for i, tok in enumerate(toks):
        m = PUNCT_SPLIT.match(tok)
        lead, core, trail = (m.group(1), m.group(2), m.group(3)) if m else ("", tok, "")
        if not core:
            out.append(tok)
            if tok.strip() in DASHES or tok.endswith((":", ";")):
                first = True
            continue
        prev = toks[i - 1] if i else ""
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        ctx = {
            "first": first or lead.startswith(("(", "\"", chr(0x201C))) and i == 0,
            "prev": prev, "next": nxt, "trail": trail,
            "prev_digit": bool(HAS_DIGIT.search(prev)) and not prev.endswith((",", ";", ":")),
            "next_digit": bool(HAS_DIGIT.search(nxt)),
            "prev_unit": prev.strip(",;:()").lower() in UNITS or prev.endswith("%"),
        }
        if HAS_DIGIT.search(core):
            word = core                         # 43-101, 3TS, A2GOLD, Q3, 2,500M: as written
        else:
            word = _word(core, ctx)
        out.append(lead + word + trail)
        first = trail.endswith((":", ";")) or (trail.endswith(("?", "!")) and True)
        if tok in DASHES:
            first = True
    return " ".join(out)


_TESTS = [
    ("A2GOLD COMMENCES RC DRILLING AT TARGET PENTE AT EASTSIDE GOLD-SILVER PROJECT",
     "A2GOLD Commences RC Drilling at Target Pente at Eastside Gold-Silver Project"),
    ("LAKE VICTORIA GOLD IDENTIFIES PREFERRED PROCESSING ROUTE FOR IMWELO NEAR-SURFACE MINERALIZATION",
     "Lake Victoria Gold Identifies Preferred Processing Route for Imwelo Near-Surface Mineralization"),
    ("INDEPENDENCE GOLD INTERCEPTS 3.11 G/T GOLD AND 48.69 G/T SILVER OVER 8.03 METRES, 3TS PROJECT, BC",
     "Independence Gold Intercepts 3.11 g/t Gold and 48.69 g/t Silver over 8.03 Metres, 3TS Project, BC"),
    ("ACME SECURES US$30 MILLION FROM JAPAN'S HANWA", "Acme Secures US$30 Million from Japan's Hanwa"),
    ("COMPANY FILES NI 43-101 TECHNICAL REPORT FOR PHASE II", "Company Files NI 43-101 Technical Report for Phase II"),
    ("DRILLING BASED ON NEW MODEL AT MT. TODD, TIMMINS, ON", "Drilling Based on New Model at Mt. Todd, Timmins, ON"),
    ("LA COLORADA UPDATE", "La Colorada Update"),
    ("STEADRIGHT PROVIDES MCTO STATUS UPDATE", "Steadright Provides MCTO Status Update"),
    ("O'BRIEN APPOINTED CEO OF B.C. EXPLORER", "O'Brien Appointed CEO of B.C. Explorer"),
    ("RESULTS: THE BEST HOLE TO DATE", "Results: The Best Hole to Date"),
    ("Already Mixed Case Headline Stays As Is", "Already Mixed Case Headline Stays As Is"),
    ("DRILLS 1.2% CU AND 0.5 G/T AU OVER 100 M", "Drills 1.2% Cu and 0.5 g/t Au over 100 m"),
    ("INTERCEPTS 450 G/T AG OVER 2 M", "Intercepts 450 g/t Ag over 2 m"),
    ("CLOSES FIRST TRANCHE OF LIFE OFFERING", "Closes First Tranche of LIFE Offering"),
    ("TARACHI GOLD CLOSES FINANCING (CSE: TRG)", "Tarachi Gold Closes Financing (CSE: TRG)"),
    ("TINKA LISTS ON OTCQB UNDER TICKER SYMBOL TKRFF", "Tinka Lists on OTCQB Under Ticker Symbol TKRFF"),
    ("WHAT MAKES IT WORK: CALL AT 10:00 AM EST", "What Makes It Work: Call at 10:00 AM EST"),
    ("DRILLING AT RAMSEY PROJECT, LA PAZ COUNTY, ARIZONA", "Drilling at Ramsey Project, La Paz County, Arizona"),
    ("EARLY WARNING REPORT PURSUANT TO NI 62-103", "Early Warning Report Pursuant to NI 62-103"),
    ("RECORD CASH FLOW IN 2018", "Record Cash Flow in 2018"),
]


def self_test(verbose=True):
    bad = 0
    for inp, want in _TESTS:
        got = smart_title(inp)
        if got != want:
            bad += 1
            if verbose:
                print("FAIL", repr(inp), "\n   got ", repr(got), "\n   want", repr(want))
    if verbose:
        print(f"titlecase self-test {len(_TESTS) - bad}/{len(_TESTS)}")
    return bad
