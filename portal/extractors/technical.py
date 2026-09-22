"""Technical Reports (NI 43-101) reader, facts-store version (TECH_V1, 2026-09-22).

The source of the Technical Reports page once it passes the accuracy gate. Written against the 50-item set Justin
confirmed on 2026-09-22 (48 items with rows, 54 rows).

The row shape and the rules are Justin's (2026-09-22):

  1. ONE ROW PER TECHNICAL REPORT an item reports: company, project, report type (property, resource, PEA, PFS, FS,
     other), effective date, filing date, author firm and QPs. An amended report is its own row, marked amended.
  2. STATUS: filed, commissioned (engaged, being prepared, "will be filed within 45 days", a study underway) or
     withdrawn. A commissioned row is replaced by the filed row for the same report when it arrives.
  3. SEDAR FILING DOCUMENTS COUNT: "find the information that should be in them, we need it". A consent or
     certificate of a qualified person is one row for the report it names; a report's cover pages are one row.
     A consent's filing date is the date it was signed (the item's date is the supported news release's).
  4. THE HEADLINE NUMBERS REPEAT on the row: the resource summary or the study economics, when the item states them.
  5. NOT ROWS: citations of an earlier report as background, JORC / S-K 1300-only reports, clarifications that
     name no report.
  6. PROJECT NAMES are the full name as the company writes it ("Powerline Uranium Project", "Mount Milligan Mine").

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per row (ordinal 0..n-1)
to_prediction(records) -> dict|None    what the accuracy judge compares

Self-tests: python3 -m portal.extractors.technical
"""
from __future__ import annotations

import json
import re
import unicodedata

from portal import facts as F

NAME = "technical"
VERSION = "1.0.0"
KIND = "tech_report"
TAG = "Technical Reports (NI 43-101)"
TEXT_CAP = 40000

TXT_FIELDS = ("report_type", "project", "status", "effective_date", "author_firm", "title", "report_date",
              "filing_date", "expected", "qps", "metal", "supports_release", "resource_json", "currency", "doc_kind")
NUM_FIELDS = ("amended", "npv", "npv_discount", "irr", "capex", "after_tax", "mine_life_years", "payback_years")

# ------------------------------------------------------------------ dates
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
           "nov": 11, "dec": 12}
_MON = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|" \
       r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
_DATE_RX = (r"(?:(" + _MON + r")\s*(\d{1,2})\s*(?:st|nd|rd|th)?\s*,?\s*((?:19|20)\d\d)"
            r"|(\d{1,2})\s*(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?(" + _MON + r")\s*,?\s*((?:19|20)\d\d)"
            r"|((?:19|20)\d\d)-(\d\d)-(\d\d))")
_DATE = re.compile(r"(?i)" + _DATE_RX)


def _iso(m):
    g = m.groups()
    try:
        if g[0]:
            mo, d, y = _MONTHS[g[0][:3].lower()], int(g[1]), int(g[2])
        elif g[3]:
            mo, d, y = _MONTHS[g[4][:3].lower()], int(g[3]), int(g[5])
        else:
            y, mo, d = int(g[6]), int(g[7]), int(g[8])
    except (KeyError, ValueError):
        return None
    if not (1 <= d <= 31 and 1 <= mo <= 12):
        return None
    return "%04d-%02d-%02d" % (y, mo, d)


def _date_at(s, pos=0, span=40):
    m = _DATE.search(s, pos, pos + span + 40)
    if m and m.start() - pos <= span:
        return _iso(m)
    return None


# ------------------------------------------------------------------ text preparation
_FLS = re.compile(r"(?i)\b(?:cautionary\s+(?:note|statement)s?\s+(?:regarding|on|concerning)\s+forward|forward[\s\-]+"
                  r"looking\s+(?:statements?|information)\s*(?:and|&)?\s*(?:cautionary)?[^.]{0,40}?(?:\n|:|This\s+"
                  r"(?:news\s+)?release)|neither\s+(?:the\s+)?(?:tsx|canadian\s+securities))")
_ABOUT = re.compile(r"(?:^|\s)About\s+(?:the\s+Company|[A-Z][\w&.'’\-]*(?:\s+[A-Z][\w&.'’\-]*){0,5})\s*(?::|\s(?=[A-Z][a-z]+\s"
                    r"(?:is|was|Inc|Corp|Ltd|Limited|Resources|Metals|Mining|Gold|Silver|Copper|Energy|Minerals)\b))")


def _norm(s):
    s = unicodedata.normalize("NFKC", s or "").replace(chr(160), " ").replace("­", "")
    s = s.replace("’", "'").replace("‘", "'")
    return s


def _flat(s):
    return re.sub(r"\s+", " ", s).strip()


def _prepare(headline, body, doc):
    b = _norm((body or "")[:TEXT_CAP])
    if not doc:
        m = _FLS.search(b, 600)
        if m:
            b = b[:m.start()]
        m = _ABOUT.search(b, 800)
        if m:
            b = b[:m.start()]
    b = re.sub(r"https?://\S+", " ", b)
    return _flat(_norm(headline)), _flat(b)


def _sentences(text):
    parts = re.split(r"(?<![\s(][A-Z]\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\bSt\.)(?<!\bMt\.)(?<!\bNo\.)(?<!\bvs\.)"
                     r"(?<=[.;!?])\s+(?=[A-Z“\"•▪(])|\s+[•▪●]\s+", text)
    return [p.strip() for p in parts if len(p.strip()) > 12]


# ------------------------------------------------------------------ report types, projects, firms
_T_FS = re.compile(r"(?i)(?<!pre-)(?<!pre)(?<!pre\s)(?<!preliminary\s)\b(?:definitive\s+|bankable\s+)?feasibility\s+study\b|\b(?:DFS|BFS)\b")
_T_PFS = re.compile(r"(?i)\bpre-?\s?feasibility\b|\bpreliminary\s+feasibility\b|\bPFS\b")
_T_PEA = re.compile(r"(?i)\bpreliminary\s+economic\s+assessment\b|\bPEA\b|\bscoping\s+study\b")
_T_RES = re.compile(r"(?i)\bmineral\s+resource(?:s)?(?:\s+(?:estimate|update|statement))?\b|\bresource\s+(?:estimate|update)\b|"
                    r"\bMRE\b|\bmineral\s+reserves?\b")
_T_MINE = re.compile(r"\bMine\b")


def _type_of(t, default=None):
    if not t:
        return default
    if _T_FS.search(t) and not re.search(r"(?i)pre-?\s?feasibility", _T_FS.search(t).group(0)):
        # "feasibility study" inside "pre-feasibility study" is excluded by the lookbehinds
        return "FS"
    if _T_PFS.search(t):
        return "PFS"
    if _T_PEA.search(t):
        return "PEA"
    if _T_RES.search(t):
        return "resource"
    return default


_SUFFIX = r"(?:Project|Property|Mine|Mines|Deposit|Projects|Properties)"
_CAPW = r"(?:[A-ZÀ-Ý0-9][\w'À-ÿ\-/.]*|\(\d\)|de|del|la|di|du|des|do|y|and|&|–|-|of)"
_PROJ_RX = re.compile(r"((?:[A-ZÀ-Ý][\w'À-ÿ\-/.]*)(?:\s+" + _CAPW + r"){0,6}?)\s+" + _SUFFIX + r"\b")
_PROJ_LOWER = re.compile(r"((?:[A-ZÀ-Ý][\w'À-ÿ\-/.]*)(?:\s+" + _CAPW + r"){0,5}?)\s+(?:project|property|mine|deposit)\b")
_BAD_LEAD = {"Acquire", "Acquires", "Acquisition", "Option", "Options", "Sell", "Sells", "Signs", "Closes", "Life", "Mine", "Plan",
             "Update", "Results", "Drill", "Drilling", "Ministry", "Mines", "Department", "The", "This", "Our", "Its", "Company", "Company's", "Each", "All", "New", "Its", "Technical", "Report",
             "NI", "Filing", "Files", "Filed", "Announces", "Updated", "Amended", "Revised", "Initial", "Maiden",
             "Mineral", "Resource", "Estimate", "Preliminary", "Economic", "Assessment", "Feasibility", "Study",
             "Pre-Feasibility", "Prefeasibility", "On", "For", "At", "In", "Of", "Wholly", "Owned", "100%",
             "Flagship", "A", "An", "PEA", "PFS", "MRE", "Report's", "Current", "Canadian", "National", "Instrument",
             "Standards", "Disclosure", "Mineral Projects", "Engages", "Commences", "Announcement", "Intent",
             "Complete", "Completes", "Supporting", "Support", "Confirming", "Including", "And", "Positive", "Such", "Other", "Any", "Both", "These", "Those", "Clarifies", "Clarification", "Page"}
_STOP_INNER = {"Technical", "Report", "Files", "Filed", "Filing", "Announces", "for", "on", "the", "The", "at",
               "Supporting", "NI", "Estimate", "Assessment", "Study", "Update", "Updated", "Owned", "Its", "Mineral",
               "Resource", "Resources", "Gold's", "Report,", "In", "in", "Of", "PEA", "PFS", "MRE", "to", "To",
               "Engages", "Write", "Complete", "Intent", "Preliminary", "Economic", "Feasibility", "Pre-Feasibility",
               "Filing", "Economics", "Positive", "Commences", "Commence", "Provides", "Provide", "Reports", "Receives",
               "Completes", "Begins", "Launches", "Initiates", "Starts", "Advances", "Delivers", "Outlines", "Defines",
               "Intersects", "Drills", "Expands", "Increases", "Highlights", "Confirms", "Unveils", "Publishes", "Releases",
               "Extends", "Improves", "Terms", "Acquisition", "Updates", "Announce", "Delivers", "Signs", "Enters", "Files"}


def _clean_proj(name, suffix):
    if re.search(r"\s[–—]\s|\s-\s", name):
        name = re.split(r"\s[–—]\s|\s-\s", name)[-1]
    ws = name.split()
    # cut at the last word that cannot be part of a name
    cut = 0
    for i, w in enumerate(ws):
        if w in _STOP_INNER or w.rstrip(",:;.") in _STOP_INNER or re.match(r"^\d{4}\.?$", w) or w.endswith((",", ":", ";")) \
                or (w.endswith(".") and len(w) > 3 and not re.match(r"^(?:[A-Z]\.)+$|^(?:Mt|St|Ste|Pt)\.$", w)):
            cut = i + 1
    ws = ws[cut:]
    while ws and (ws[0] in _BAD_LEAD or ws[0].lower() in ("and", "of", "&", "-", "–", "de", "y") or re.search(r"['’]s$", ws[0])):
        ws = ws[1:]
    while ws and ws[-1].lower() in ("and", "of", "&", "-", "–", "de", "y", "the"):
        ws = ws[:-1]
    if not ws:
        return None
    if ws[0][0].islower():
        return None
    s = " ".join(ws)
    if " and " in s:
        pre, post = s.rsplit(" and ", 1)
        if len(pre.split()) == 1 and post:
            s = post
    if re.search(r"\bof\s*$|\bLife\s+of\b", s):
        return None
    if len(s) < 2 or s in _BAD_LEAD:
        return None
    if not _pkey(s):
        return None
    return s + " " + suffix


def _projects_in(t, issuer=None):
    out = []
    for m in _PROJ_RX.finditer(t):
        suf = re.match(r"\s+(\S+)", t[m.end(1):m.end()]).group(1)
        if re.match(r"\s*(?:,\s*)?(?:Corp|Inc|Ltd|Limited|Canada|LLC|Company|Co)\b", t[m.end():m.end() + 14]):
            continue  # "Omai Gold Mines Corp." is the company
        p = _clean_proj(m.group(1), suf)
        if not p:
            continue
        if issuer and suf in ("Mines", "Mining") and set(_fold(_core(p)).split()) <= set(_fold(issuer).split()):
            continue
        out.append((m.start(), p))
    # a deposit is named inside its project: prefer the project
    out.sort(key=lambda x: (x[1].endswith(("Deposit", "Deposits")), x[0]))
    return out


def _core(p):
    return re.sub(r"\s+" + _SUFFIX + r"$", "", p or "").strip()


_PGEN = {"gold", "silver", "copper", "lithium", "uranium", "nickel", "zinc", "lead", "potash", "phosphate", "molybdenum",
         "graphite", "tungsten", "antimony", "critical", "minerals", "mineral", "metals", "polymetallic", "sulphide", "pge",
         "project", "property", "mine", "mines", "deposit", "projects", "properties", "the", "and", "flake", "au", "cu"}


def _pkey(p):
    return " ".join(w for w in re.findall(r"[a-z0-9]+", _fold(p)) if w not in _PGEN)


_FIRM_TYPE = (r"Consultants?|Consulting|Consultoria|Geoscience|Geosciences|Geomatics|Engineering|Engineers|Group|Associates|"
              r"Advisors|Geological\s+Services|Geosolutions|GeoSolutions|Solutions|Enterprises|Professionals|Partners|"
              r"Mining\s+Plus|Services|Environmental|Laboratories")
_LEGAL = r"(?:Inc|Ltd|Ltda|Limited|ULC|LLC|Corp|Co|Pty|Pte|S\.A|SA|GmbH|LLP)"
_POSTNOM_W = {"CET", "FEC", "MBA", "PhD", "Ph.D", "P.Eng", "P.Geo", "FAusIMM", "MAusIMM", "MAIG", "FAIG", "CGeol", "MIMMM",
              "MIChemE", "C.Eng", "FIMMM", "Eng", "Geo", "B.Sc", "M.Sc", "QP", "CPG", "P.E", "PE", "Pr.Sci.Nat", "SME-RM",
              "RM", "SME", "ing", "Ing", "FGS", "MSc", "BSc", "BEng", "MEng", "Pr.Eng", "Dipl.-Ing", "P.", "B.", "M.",
              "Mine", "Geology", "Owner", "President", "Principal", "Director", "Manager", "Senior", "Vice", "VP", "CEO",
              "Mr", "Ms", "Dr"}
_KNOWN = (r"SLR|Micon|P&E|AGP|Ausenco|WSP|SRK|RPA|Tetra\s+Tech|Hatch|Moose\s+Mountain|APEX|Caracle\s+Creek|Mining\s+Plus|"
          r"Sedgman|Kappes,?\s+Cassiday|Stantec|Golder|Wood|DRA|Lycopodium|GeoSim|Ginto|RESPEC|BBA|G\s*Mining|AMC|Cube|"
          r"Minetech|Mercator|InnovExplo|GE21|ERM|SGS|CSA\s+Global|Fuse\s+Advisors|Sims\s+Resources|WWC|Knight\s+Pi[eé]sold|"
          r"Fluor|AtkinsR[eé]alis|Hinterland|Dahrouge|MSA|Understood\s+Mineral\s+Resources|PLR\s+Resources|Evomine|Synectiq|"
          r"GRE|Global\s+Resource\s+Engineering|Nagy|Red\s+Pennant|Lions\s+Gate|English\s+River|Ausenco|Equilibrium\s+Mining|"
          r"pHase\s+Geochemistry|A-Z\s+Mining|DKT|Capps|Geodoz|Tetra\s+Tech|Watts,?\s+Griffis|Roscoe\s+Postle|Mine\s+Development\s+Associates|"
          r"Kirkham|Geotech|Moose|Magri|Stantec|Ecometrix|Lorax|Terrane|SRK\s+Consulting|Western\s+Water\s+Consultants|ABH|JDS|"
          r"Entech|Hard\s+Rock\s+Consulting|Mine\s+Technical\s+Services|Snowden|Optiro|Cube\s+Consulting|MPR|Kappes")
_NAMEW = r"(?:[A-Z&][\w&'\-]*\.?|\((?:Canada|USA|Pty|Geological\s+Services|UK)\)|&|de|do|da|and)"
_FIRM_RX = re.compile(r"((?:" + _NAMEW + r"\s+){0,5}?(?:(?:" + _FIRM_TYPE + r")(?:\s+" + _NAMEW + r"){0,3}?(?:\s*,?\s*" + _LEGAL +
                      r"\.?)?|[A-Z][\w&'\-]*\s*,?\s*" + _LEGAL + r"\b\.?)|\b(?:" + _KNOWN + r")\b(?:\s+" + _NAMEW + r"){0,4}?"
                      r"(?:\s*,?\s*" + _LEGAL + r"\b\.?)?)")
_FIRM_BAD = re.compile(r"(?i)^(?:the\s+)?(?:company|issuer|corporation|securities|commission|exchange|tsx|venture|"
                       r"canadian|british|ontario|alberta|toronto|vancouver|national|instrument|cim|standing|newsfile|"
                       r"globe|accesswire|cnw|prnewswire|board|sedar)\b|securities\s+commission|stock\s+exchange|^(?:NI|TSX|CSE)\b")


def _clean_firm(f):
    f = _flat(f).strip(" ,.;:")
    toks = f.split()
    while toks and (toks[0].rstrip(".,") in _POSTNOM_W or toks[0].lower() in ("and", "by", "of", "with", "from", "the", "for", "&")
                    or re.match(r"^[A-Z]\.$", toks[0])):
        toks = toks[1:]
    f = " ".join(toks)
    f = re.sub(r",?\s+(?:Inc|Ltd|Ltda|Limited|Corp|Corporation|LLC|ULC|LLP|Pty(?:\s+Ltd)?|Pte|S\.A|SA|GmbH)\.?$", "", f)
    f = re.sub(r",?\s+(?:Inc|Ltd|Limited|Corp|LLC|ULC)\.?$", "", f)
    f = re.sub(r"\s+d/b/a.*$", "", f).strip(" ,.")
    if len(f) < 2 or _FIRM_BAD.search(f) or not re.search(r"[A-Z]", f[:1]):
        return None
    return f


_FIRM_GEN = {"inc", "ltd", "limited", "corp", "corporation", "llc", "ulc", "pty", "co", "consulting", "consultants", "consultant",
             "engineering", "engineers", "group", "services", "canada", "international", "geological", "geoscience", "geosciences",
             "the", "and", "of", "mining", "geosolutions", "enterprises", "sa", "europe", "projects", "advisors", "resources",
             "resource", "usa", "us", "technical", "environmental", "solutions", "partners", "associates", "professionals",
             "mineral", "minerals", "independent", "firm", "e", "p"}


_CORP_WORDS = re.compile(r"(?i)\b(?:Gold|Silver|Metals|Minerals|Mines|Mining|Energy|Lithium|Uranium|Copper|Nickel|Exploration|"
                         r"Resources|Potash|Phosphate|Royalt\w*|Capital|Ventures)\s*$")


def _firms_in(t, issuer=None):
    out = []
    for m in _FIRM_RX.finditer(t):
        raw = m.group(1)
        f = _clean_firm(raw)
        if not f:
            continue
        if issuer and _fold(f).split()[:1] == _fold(issuer).split()[:1]:
            continue
        if not [w for w in re.findall(r"[a-z0-9&]+", _fold(f)) if w not in _FIRM_GEN]:
            continue
        known = re.match(r"(?:" + _KNOWN + r")\b", f)
        if not known and _CORP_WORDS.search(re.sub(r",?\s*" + _LEGAL + r"\.?$", "", _flat(raw)).strip()):
            continue  # a mining company, not a consultancy
        if not known and not re.search(_FIRM_TYPE, f) and not re.search(r"\b" + _LEGAL + r"\b", raw):
            continue
        out.append((m.start(), f))
    return out


_AUTH_SENT = re.compile(r"(?i)\b(?:prepared|authored|completed|compiled)\b[^.]{0,160}?\bby\b|\bis\s+(?:now\s+)?preparing\b|"
                        r"\bnearing\s+completion\b|\bled\s+by\b|\b(?:prepared|authored|co-?authored|compiled|completed|led|written|signed|conducted|undertaken)\s+"
                        r"(?:(?:independently|jointly|under\s+the\s+(?:supervision|direction)\s+of)\s+)?(?:by\b|under\s+the\s+supervision)|"
                        r"\bindependent(?:ly)?\s+prepared\s+by\b|\bby\s+independent\s+(?:firm|consultants?)\b|\bqualified\s+persons?\b[^.]{0,60}"
                        r"\b(?:are|is|include|responsible)\b|\bwith\s+contributions?\s+from\b|\bengaged\b|\bretained\b")
_APPROVAL = re.compile(r"(?i)\b(?:reviewed\s+and\s+approved|approved\s+(?:the\s+)?(?:scientific|technical)|has\s+reviewed\s+and|"
                       r"verified\s+the\s+(?:scientific|technical))\b")


def _authors(text, issuer=None, strict=False):
    """(firms, qps) of a report, in the order the item names them; the lead firm first."""
    firms, qps = [], []
    sents = _sentences(text)
    ranked = []
    for i, s in enumerate(sents):
        if not _AUTH_SENT.search(s) or _APPROVAL.search(s):
            continue
        pri = 0 if re.search(r"(?i)(?:prepared|compiled|led|authored|written)\s+(?:independently\s+|jointly\s+)?by|independently\s+prepared|"
                             r"(?:is\s+(?:now\s+)?preparing|nearing\s+completion|engaged|retained)", s) \
            else 1 if re.search(r"(?i)supervision|by\s+independent|contributions?\s+from", s) else 2
        if not re.search(r"(?i)report|PEA|PFS|feasibility|estimate|assessment|study|qualified|43-101", s):
            continue
        if re.search(r"(?i)\b(?:historic\w*|in\s+(?:19|200)\d\d)\b", s) and pri > 0:
            continue
        ranked.append((pri, i, s))
    ranked.sort()
    for _p, _i, s in ranked:
        seg = re.sub(r"(?i)^.*?\bprepared\s+for\s+[^,()]{0,80}?(?:\([^)]*\)\s*)?(?=\s+by\b)", "", s)
        for _pos, f in _firms_in(seg, issuer):
            if f not in firms and not any(_fold(f) in _fold(x) or _fold(x) in _fold(f) for x in firms):
                firms.append(f)
        for q in _qps_in(seg):
            if q not in qps:
                qps.append(q)
        if strict and firms:
            break
    return firms, qps


def _fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    return "".join(c for c in s if not unicodedata.combining(c))


_POSTNOM = r"(?:P\.\s?Geo|P\.\s?Eng|P\.\s?Geol|Ph\.?\s?D|M\.\s?Sc|B\.\s?Sc|FAusIMM|MAusIMM|MAIG|FAIG|CPG|RM\s?SME|SME-RM|" \
           r"QP|C\.?P\.?G|Pr\.\s?Sci\.\s?Nat|Pr\.\s?Eng|FEC|CET|MBA|Dipl\.-Ing|PE|P\.E|MMSA|Géo|ing\.|géo\.|P\.Geo)\.?"
_PERSON = r"((?:Dr\.\s+)?[A-Z][a-zA-Z'\-]+(?:\s+[A-Z]\.)*(?:\s+[A-Z][a-zA-Z'\-]+){1,2})"
_QP_RX = re.compile(_PERSON + r"\s*,?\s*(?=" + _POSTNOM + r")")


def _qps_in(t):
    out = []
    for m in _QP_RX.finditer(t):
        n = re.sub(r"^(?:Dr\.\s+)", "", m.group(1)).strip()
        if re.match(r"(?:The|By|And|Prepared|Signed|Dated|Consent|Mr|Ms|Mrs|Qualified|Report|Authored|Co)\b", n):
            n = re.sub(r"^\S+\s+", "", n)
        if len(n.split()) < 2 or n in out:
            continue
        out.append(n)
    return out


# ------------------------------------------------------------------ numbers from the item
def _money(v, unit):
    try:
        x = float(v.replace(",", ""))
    except ValueError:
        return None
    u = (unit or "").lower()
    if u.startswith("b"):
        x *= 1e9
    elif u.startswith("m"):
        x *= 1e6
    return x


_NPV_RX = re.compile(r"(?i)(after[\s-]*tax|pre[\s-]*tax)?\s*(?:net\s+present\s+value|NPV)\s*(?:\(?\s*(\d{1,2}(?:\.\d)?)\s*%?\s*\)?)?"
                     r"[^$.%]{0,60}?(C\$|CA\$|CAD\s*\$?|US\$|USD\s*\$?|A\$|\$)\s?(\d[\d,]*(?:\.\d+)?)\s*(billion|million|B|M|bn|mm)?\b")
_IRR_RX = re.compile(r"(?i)(after[\s-]*tax|pre[\s-]*tax)?\s*(?:internal\s+rate\s+of\s+return|IRR)\s*(?:\([^)]{0,20}\))?[^%.]{0,40}?"
                     r"(\d{1,3}(?:\.\d+)?)\s*%|(\d{1,3}(?:\.\d+)?)\s*%\s*(after[\s-]*tax|pre[\s-]*tax)?\s*IRR")
_CUR = {"c$": "CAD", "ca$": "CAD", "cad": "CAD", "us$": "USD", "usd": "USD", "a$": "AUD", "$": None}


def _econ_from_text(t):
    if not t:
        return None
    npv = None
    for m in _NPV_RX.finditer(t):
        v = _money(m.group(4), m.group(5))
        if v is None or v < 1e6 and not m.group(5):
            continue
        cand = {"npv": v, "npv_discount": float(m.group(2)) if m.group(2) else None,
                "currency": _CUR.get(re.sub(r"\s", "", m.group(3).lower()).rstrip("$") + "$" if m.group(3).lower().strip() not in ("$",) and not m.group(3).lower().startswith(("cad", "usd")) else re.sub(r"\s|\$", "", m.group(3).lower()) or "$"),
                "after_tax": None if not m.group(1) else (1.0 if m.group(1).lower().startswith("after") else 0.0)}
        if npv is None or (cand["after_tax"] == 1.0 and npv["after_tax"] != 1.0):
            npv = cand
    irr = None
    for m in _IRR_RX.finditer(t):
        v = float(m.group(2) or m.group(3))
        tax = m.group(1) or m.group(4)
        at = None if not tax else tax.lower().startswith("after")
        if irr is None or (at and not irr[1]):
            irr = (v, at)
    if not npv and not irr:
        return None
    e = {"npv": None, "npv_discount": None, "irr": None, "capex": None, "currency": None, "after_tax": None,
         "mine_life_years": None, "payback_years": None}
    if npv:
        e.update(npv)
    if irr:
        e["irr"] = irr[0]
    m = re.search(r"(?i)payback[^.]{0,40}?(\d+(?:\.\d+)?)\s*years?|(\d+(?:\.\d+)?)[\s-]*years?\s+payback", t)
    if m:
        e["payback_years"] = float(m.group(1) or m.group(2))
    return e


def _econ_from_reader(headline, body):
    try:
        from portal.extractors import economics as E
        a = E.analyse(headline, body)
    except Exception:  # pragma: no cover - the headline numbers are a courtesy, never a failure
        return None, None
    sc = a.get("scenarios") or []
    if not sc:
        return None, a.get("study_type")
    s = sc[0]
    at = s.get("npv_after_tax") is not None
    return ({"npv": s.get("npv_after_tax") if at else s.get("npv_pre_tax"), "npv_discount": s.get("discount_pct"),
             "irr": s.get("irr_after_tax_pct") if s.get("irr_after_tax_pct") is not None else s.get("irr_pre_tax_pct"),
             "capex": s.get("initial_capex"), "currency": s.get("currency"), "after_tax": 1.0 if at else 0.0,
             "mine_life_years": s.get("mine_life_years"), "payback_years": s.get("payback_years")},
            a.get("study_type"))


def _res_from_reader(headline, body):
    try:
        from portal.extractors import resources as R
        a = R.analyse(headline, body)
    except Exception:  # pragma: no cover
        return None
    rows = a.get("rows") or []
    if not rows:
        return None
    out = []
    dep = rows[0].get("deposit")
    for r in rows:
        if r.get("deposit") != dep or len(out) >= 4:
            break
        g = (r.get("grades") or [{}])[0]
        c = (r.get("contained") or [{}])[0]
        out.append({"category": r.get("category"), "tonnes": r.get("tonnes"), "grade": g.get("value"),
                    "grade_unit": g.get("unit"), "metal": g.get("metal") or c.get("metal"),
                    "contained": c.get("value"), "contained_unit": c.get("unit")})
    return out or None


_METALS = ("gold", "silver", "copper", "nickel", "zinc", "lead", "cobalt", "lithium", "uranium", "antimony", "tungsten",
           "molybdenum", "graphite", "potash", "phosphate", "vanadium", "platinum", "palladium", "rare earth", "tin",
           "manganese", "iron", "titanium", "niobium", "tantalum", "helium", "coal", "fluorspar", "gallium", "germanium")


def _metal(t):
    f = _fold(t)
    got = [m for m in _METALS if re.search(r"\b" + m + r"\b", f)]
    return "+".join(got[:3]) or None


# ------------------------------------------------------------------ document kinds
_CONSENT = re.compile(r"(?i)^\s*(?:consent|certificate)\s+of\s+(?:a\s+)?(?:qualified|author)|\bhereby\s+consent\b|"
                      r"\bconsent\s+to\s+the\s+(?:public\s+)?filing\b|^\s*CONSENT\s+OF\b|\bdo\s+hereby\s+consent\b")
_COVER = re.compile(r"(?i)^\s*technical\s+report\s*\(NI\s*43-?101\)")


def _doc_kind(h, raw):
    head = (raw or "")[:1500]
    if re.match(r"(?i)\s*(?:consent|certificate)\s+of\s+(?:a\s+)?qualified", h) or \
            (re.search(r"(?i)\bconsent\b", head[:600]) and _CONSENT.search(head)):
        return "consent"
    if _COVER.match(h) and not re.search(r"(?i)\b(?:news\s+release|is\s+pleased\s+to\s+announce)\b", head[:1200]):
        return "cover"
    if re.search(r"(?i)^\s*(?:NI\s+43-101\s+)?TECHNICAL\s+REPORT\b", head[:300]) and \
            re.search(r"(?i)prepared\s+(?:by|for)|effective\s+date", head) and \
            not re.search(r"(?i)is\s+pleased\s+to\s+announce", head):
        return "cover"
    return "news"


# ------------------------------------------------------------------ helpers
def _quoted(t):
    return [(m.start(), _flat(m.group(1))) for m in re.finditer(r"[“\"]\s*([^”\"]{12,300}?)\s*[”\"]", t)]


def _report_title(t, after=0):
    """A report title: quoted after 'titled/entitled', or quoted and defined as the (Technical) Report."""
    best = None
    for m in re.finditer(r"(?i)(?:entitled|titled|title\s+of)\s*,?\s*:?\s*(?:[“\"]\s*([^”\"]{12,300}?)\s*[”\"]|'\s*([^']{12,300}?)\s*')", t):
        if m.start() < after:
            continue
        pre = t[max(0, m.start() - 60):m.start()]
        q = _flat(m.group(1) or m.group(2))
        if re.search(r"(?i)(?:news|press)\s+release\s*$|release\s+(?:dated\s+[^,]+,\s*)?$", pre) and \
                not re.search(r"(?i)technical\s+report\b", pre[-30:]):
            continue
        if not re.search(r"(?i)report|assessment|estimate|study|feasibility|43-101", q):
            continue
        best = (m.start(), q)
        break
    if best:
        return best
    for m in re.finditer(r"[“\"]\s*([^”\"]{12,300}?)\s*[”\"]\s*(?:,\s*[^()]{0,120})?\(\s*(?:the\s+)?[“\"]?\s*(?:Technical\s+Report|Report|"
                         r"\d{4}\s+(?:PFS|PEA|FS)|PEA|PFS|Updated\s+Technical\s+Report)", t):
        return (m.start(), _flat(m.group(1)))
    for m in re.finditer(r"[“\"]\s*((?:NI\s*43\s*-?\s*101\s+)?(?:Independent\s+)?Technical\s+Report\b[^”\"]{8,300}?|[^”\"]{4,200}?"
                         r"\bNI\s*43\s*-?\s*101\s+Technical\s+Report\b[^”\"]{0,200}?)\s*[”\"]", t):
        pre = t[max(0, m.start() - 60):m.start()]
        if re.search(r"(?i)(?:news|press)\s+release", pre):
            continue
        return (m.start(), _flat(m.group(1)))
    return None


def _all_titles(t):
    out = []
    pos = 0
    while True:
        r = _report_title(t[pos:])
        if not r:
            return out
        out.append((pos + r[0], r[1]))
        pos += r[0] + len(r[1]) + 2


def _effective(t):
    got = []
    for rx in (r"(?i)effective\s+date\s*(?:of|is|was|:|as\s+of)?\s*", r"(?i)\beffective\s+(?:as\s+(?:of|at)\s+)?(?=[A-Z0-9])",
               r"(?i)dated\s+effective\s+", r"(?i)effective\s+date\s+of\s+the\s+[\w\s\-]{3,50}?\s+(?:is|was)\s+",
               r"(?i)\bis\s+dated\s+(?=[A-Z][a-z]+\s+\d{1,2},?\s+\d{4},?\s+with\s+an\s+issue\s+date)"):
        for m in re.finditer(rx, t):
            d = _date_at(t, m.end(), 6)
            if d:
                got.append((m.start(), d))
    if not got:
        return None
    got.sort()
    from collections import Counter
    c = Counter(d for _p, d in got)
    top = max(c.values())
    return next(d for _p, d in got if c[d] == top)


def _report_date(t, title_pos=None):
    for m in re.finditer(r"(?i)(?:technical\s+report|report|study|assessment)[”\"]?\s*(?:\([^)]{0,40}\)\s*)?,?\s*(?:is\s+)?dated\s+"
                         r"(?!effective)(?:as\s+of\s+)?", t):
        pre = t[max(0, m.start() - 40):m.start()]
        if re.search(r"(?i)(?:news|press)\s+$", pre):
            continue
        d = _date_at(t, m.end(), 4)
        if d:
            return d
    for m in re.finditer(r"(?i)\bissue\s+date\s+(?:of\s+)?|\bamended\s+(?:and\s+restated\s+)?(?:as\s+of|on)\s+|\bsigning\s+date\s+(?:of\s+)?", t):
        d = _date_at(t, m.end(), 4)
        if d:
            return d
    return None


# ------------------------------------------------------------------ consents and cover pages
def _consent(h, b, raw):
    row = _blank("consent")
    tt = _report_title(b)
    if tt:
        row["title"] = tt[1]
    row["project"] = _project_from(row["title"]) or _project_from(b[:2500])
    row["report_type"] = _type_of(row["title"]) if row["title"] else None
    tail = b[tt[0]:] if tt else b
    row["effective_date"] = _effective(tail[:800]) or _effective(b)
    row["report_date"] = _report_date(b)
    if not row["report_date"] and tt:
        m = re.search(r"(?i)^[^.]{0,40}?dated\s+(?!effective)", tail[len(tt[1]) + 10:][:120])
        if m:
            row["report_date"] = _date_at(tail[len(tt[1]) + 10:], m.end(), 4)
    # signing date
    sign = None
    for m in re.finditer(r"(?i)\b(?:signed\s+and\s+dated|dated\s+and\s+signed|dated|signed)\s*(?:at\s+[A-Z][\w ,.]{0,40}?,?\s*)?"
                         r"(?:this\s+|on\s+(?:this\s+)?|:\s*|,\s*)(?=\d|[A-Z][a-z]+\s+\d)", b):
        if re.search(r"(?i)(?:release|report|letter)\s*[”\"]?\s*,?\s*$", b[max(0, m.start() - 25):m.start()]):
            continue
        d = _date_at(b, m.end(), 12)
        if d and m.start() > (len(b) * 0.35):
            sign = d
    if not sign:
        head = _DATE.search(b[:260])
        if head:
            sign = _iso(head)
    row["filing_date"] = sign or row["report_date"]
    # authors
    auth = re.search(r"(?i)(?:co-?authored|authored|prepared|written)\s+by\s+(.{0,600}?)(?:\(|\bwith\s+all\b|;|\.\s+[A-Z])", b)
    qps = []
    firms = []
    if auth:
        seg = auth.group(1)
        qps = _qps_in(seg) or [n.strip() for n in re.findall(r"([A-Z][a-z]+(?:\s+[A-Z]\.)?\s+[A-Z][a-z]+)\s*(?:,|and|$)", seg)]
        firms = [f for _p, f in _firms_in(seg)]
    bym = re.search(r"(?i)(?:P\.\s?Geo|P\.\s?Eng|FAusIMM|Ph\.?D)\.?\s+of\s+([A-Z&][^,(]{2,80}?)(?:\s*\(|,|\s+dated|\s+with)", b)
    if not firms and bym:
        f = _clean_firm(bym.group(1))
        if f:
            firms = [f]
    if not firms:
        top = _firms_in(raw[:250])
        if top:
            firms = [top[0][1]]
    if not firms:
        bottom = _firms_in(b[-500:])
        if bottom:
            firms = [bottom[-1][1]]
    if not qps:
        i = re.search(r"(?i)\bI\s*,\s*" + _PERSON, b)
        if i:
            qps = [re.sub(r"\s+", " ", i.group(1))]
    row["qps"] = qps
    row["author_firm"] = "; ".join(dict.fromkeys(firms)) or None
    sr = re.search(r"(?i)(?:news|press)\s+release\s+(?:of\s+[^.]{0,60}?)?(?:titled|entitled)\s*:?\s*[“\"]\s*([^”\"]{12,400}?)\s*[”\"]|"
                   r"following\s+news\s+release\s*:\s*[“\"]\s*([^”\"]{12,400}?)\s*[”\"]", b)
    if sr:
        row["supports_release"] = _flat(sr.group(1) or sr.group(2)).rstrip(",")
    econ = _econ_from_text(row["supports_release"])
    if econ:
        row.update(econ)
    row["metal"] = _metal((row["title"] or "") + " " + (row["supports_release"] or ""))
    row["amended"] = 1.0 if re.search(r"(?i)\bamended\b", row["title"] or "") else 0.0
    row["evidence"] = (tt[1] if tt else b[:200])[:200]
    return row


def _cover(h, b, raw):
    row = _blank("cover")
    m = re.search(r"(?i)(?:report|this\s+report)\s+(?:titled|entitled)\s*[“\"]\s*([^”\"]{12,300}?)\s*[”\"]", b)
    if m:
        row["title"] = m.group(1).strip()
    else:
        lines = [x.strip() for x in raw[:1500].splitlines()]
        start = next((i for i, x in enumerate(lines) if re.search(r"(?i)technical\s+report", x)), None)
        if start is not None:
            got = []
            for x in lines[start:start + 6]:
                if not x and got:
                    break
                if re.search(r"\d+[:,]\d|°|\bmE\b|\bUTM\b|\bZone\b|(?i:prepared|effective|suite|street)", x):
                    break
                if x:
                    got.append(x)
            if got:
                row["title"] = _flat(" ".join(got))
    if not row["title"]:
        head = b[:600]
        mm = re.search(r"(?i)((?:NI\s+43-101\s+)?TECHNICAL\s+REPORT.{5,200}?)\s+(?:Prepared|PREPARED|EFFECTIVE|Effective|"
                       r"[A-Z][\w.&]+\s+(?:Resources|Metals|Mining|Minerals)\s+(?:Inc|Corp|Ltd))", head)
        if mm:
            row["title"] = mm.group(1).strip()
    row["project"] = _project_from(row["title"])
    if not row["project"]:
        from collections import Counter
        c = Counter(p for _i, p in _projects_in(b[:14000]) if not p.endswith(("Properties", "Projects")))
        row["project"] = c.most_common(1)[0][0] if c else None
    row["report_type"] = _type_of(row["title"], "property")
    row["effective_date"] = _effective(b[:3000])
    pb = re.search(r"(?i)prepared\s+by\s*:?\s*(.{0,300})", b[:3000])
    if pb:
        row["qps"] = _qps_in(pb.group(1))[:6]
        firms = [f for _p, f in _firms_in(pb.group(1)[:200])]
        pf = re.search(r"(?i)prepared\s+for\s*:?\s*(.{0,120})", b[:3000])
        client = set(_fold(pf.group(1)).split()[:4]) - {"inc", "ltd", "corp", "limited", "the"} if pf else set()
        firms = [f for f in firms if not (client & set(_fold(f).split())) and len(f.split()) <= 6]
        row["author_firm"] = "; ".join(firms[:3]) or None
        d = _DATE.search(pb.group(1))
        if d:
            row["report_date"] = _iso(d)
    rd = re.search(r"(?i)and\s+dated\s+", b[:4000])
    if rd:
        row["report_date"] = _date_at(b, rd.end(), 4) or row["report_date"]
    row["metal"] = _metal(row["title"] or "")
    row["amended"] = 1.0 if re.search(r"(?i)\bamended\b", row["title"] or "") else 0.0
    row["evidence"] = (row["title"] or b[:200])[:200]
    return row


def _project_from(t):
    if not t:
        return None
    ps = _projects_in(t)
    if ps:
        return ps[0][1]
    return None


# ------------------------------------------------------------------ news releases
_FILED_HL = re.compile(r"(?i)\b(?:re-?)?(?:files?|filed|filing|file)\b|\bavailable\s+on\s+SEDAR|\bposts?\b[^.]{0,40}\breport|"
                       r"\b(?:publishes|published|releases|released)\b[^.]{0,60}technical\s+report")
_REPORT_WORD = re.compile(r"(?i)technical\s+report|43-?101\s+report|\b(?:PEA|PFS|MRE|feasibility|pre-?feasibility|resource\s+"
                          r"estimate|mineral\s+resource|economic\s+assessment)\b|\breport\b")
_FILED_BODY = re.compile(r"(?i)\b(?:(?:has|have)\s+(?:now\s+|today\s+)?(?:completed\s+and\s+)?filed|announces?\s+(?:today\s+)?(?:the\s+)?(?:filing|that\s+it\s+has\s+filed)|"
                         r"(?:was|were|been|is|being)\s+filed|filed\s+(?:on|under|with|to)\s+(?:SEDAR|the\s+Company)|"
                         r"(?:is|are)\s+(?:now\s+)?available\s+(?:on|under|at)\s+(?:SEDAR|the\s+Company|www\.sedar)|"
                         r"the\s+filing\s+(?:on\s+SEDAR\+?\s+)?of|will\s+be\s+(?:SEDAR\s+)?filed\s+today|filed\s+(?:an?|the|its)\s+)")
_COMM = re.compile(r"(?i)within\s+(?:the\s+next\s+)?(?:45|forty-?five)\s*(?:\(45\)\s*)?days|"
                   r"\b(?:engag|retain|commission|appoint|contract|hire)\w*\s+(?:[^.]|\.(?!\s+[A-Z][a-z])){0,140}?\bto\s+(?:prepare|write|complete|author|produce|"
                   r"update|undertake)\b|\bintent(?:ion)?\s+to\s+(?:complete|prepare|file)|"
                   r"\b(?:is|are)\s+(?:currently\s+|now\s+)?(?:preparing\s+(?:a|an|the|its)\b|being\s+prepared|in\s+preparation|underway)|\bnear(?:ing|s)\s+completion|"
                   r"\bwill\s+(?:shortly|soon)\s+be\s+filed|\bwill\s+be\s+filed\s+(?:shortly|in\s+the\s+coming|on\s+SEDAR\+?\s+(?:shortly|within|in))|"
                   r"\bplans?\s+to\s+(?:prepare|complete|publish|deliver)\s+(?:a|an|the)\s+(?:new|updated)|"
                   r"\bcommenc\w+\s+(?:the\s+)?preparation\s+of|\bwill\s+be\s+filing\s+an?\b|\bwill\s+file\s+an?\b|"
                   r"\bexpected\s+to\s+be\s+(?:completed|delivered|filed|released|published)\b|\bis\s+expected\s+(?:in|by)\s+(?:Q[1-4]|H[12]|the\s+(?:first|second|third|fourth)|early|mid|late)|"
                   r"\b(?:underway|in\s+progress)\s+and\s+(?:is\s+)?expected|\bproceed\s+with\s+(?:a\s+)?re-?filing\b|\bre-?commit\w*\s+to\s+another|\bto\s+(?:prepare|write)\s+(?:a|an|the)\s+(?:new\s+|updated\s+|independent\s+)?(?:NI\s*43-?101|technical)")
_WITHDRAWN = re.compile(r"(?i)\b(?:remov\w+|withdr[ae]w\w*|retract\w*)\s+(?:the\s+|its\s+|an?\s+)?(?:independent\s+)?(?:\w+\s+){0,3}?technical\s+report|"
                        r"technical\s+report[^.]{0,80}?(?:has|have|was|were)\s+been\s+(?:removed|withdrawn|retracted)")
_BACKGROUND = re.compile(r"(?i)\b(?:see|refer\s+to|reference\s+(?:is\s+made\s+)?to|as\s+(?:disclosed|described|detailed|reported|outlined)\s+in|"
                         r"(?:more|further)\s+(?:details|information)\s+(?:can\s+be\s+found\s+)?in|summari[sz]ed\s+(?:from|in)|"
                         r"available\s+for\s+review|contained\s+in|in\s+accordance\s+with)\b")
_NOT_43101 = re.compile(r"(?i)\bS-K\s*1300\b|\bJORC\b")
_EXPECT = re.compile(r"(?i)(within\s+(?:the\s+next\s+)?(?:45|forty-?five)\s*(?:\(45\)\s*)?days|(?:in|by|during)\s+(?:the\s+)?(?:early|mid|late)?\s*-?\s*"
                     r"(?:Q[1-4]|H[12]|first|second|third|fourth)\s*(?:quarter|half)?\s*(?:of\s+)?(?:(?:19|20)\d\d)?|"
                     r"(?:in|by)\s+(?:early|mid|late)[\s-]+(?:(?:19|20)\d\d|" + _MON + r")|shortly|in\s+the\s+(?:coming|next)\s+(?:weeks|months)|"
                     r"in\s+the\s+future|(?:\d|four|six|two|three)\s*(?:to|-|–)\s*(?:\d|six|eight|four)\s+weeks)")


def _blank(kind):
    return {"report_type": None, "project": None, "status": "filed", "effective_date": None, "author_firm": None,
            "title": None, "report_date": None, "filing_date": None, "expected": None, "qps": [], "amended": 0.0,
            "metal": None, "resource": None, "npv": None, "npv_discount": None, "irr": None, "capex": None,
            "currency": None, "after_tax": None, "mine_life_years": None, "payback_years": None,
            "supports_release": None, "doc_kind": kind, "evidence": None}


def _issuer(b):
    m = re.search(r"([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5})\s*,?\s*(?:\((?:TSX|CSE|NYSE|NASDAQ|OTC|CBOE|NEO|ASX|TSXV)|"
                  r"\((?:the\s+)?[“\"][^”\"]{1,40}[”\"]\s*(?:or\s+(?:the\s+)?[“\"](?:Company|Corporation|Issuer)))", b[:1500])
    return m.group(1) if m else None


def _dateline(b):
    """The release's own date: 'SASKATOON, Saskatchewan, May 22, 2026 –', 'London March 26 th 2026 :' or
    '(Newsfile Corp. - May 29, 2025)': the first date near the top that a dash, colon or bracket closes."""
    for d in _DATE.finditer(b[:700]):
        if re.match(r"\s{0,2}(?:[–—:/)]|-(?!\d)|\s-\s)", b[d.end():d.end() + 4]):
            return _iso(d)
    return None


def _firms_near(t, issuer=None):
    return _authors(t, issuer)[0]


_RES_WORDS = re.compile(r"(?i)\b(?:initial|maiden|inaugural|updated?|first|new)\s+(?:inferred\s+|combined\s+)?(?:mineral\s+)?resource|"
                        r"\bresource\s+estimate\b|\bMRE\b|\bmineral\s+resource\s+(?:estimate|statement|update)\b")
_DRILLY = re.compile(r"(?i)\b(?:drill\w*|metres?|meters?|holes?|program(?:me)?|survey|sampling)\b")
_STRONG_FILED = re.compile(r"(?i)\b(?:has|have)\s+(?:now\s+|today\s+)?(?:completed\s+and\s+)?filed|\b(?:was|were|been)\s+filed|"
                           r"announces?\s+(?:today\s+)?(?:the\s+)?filing|announce\s+(?:the\s+)?filing|filed\s+(?:on|under|with)\s+SEDAR|"
                           r"\bfiled\s+(?:the|an?|its)\b|today\s+filed|\b(?:is|are)\s+(?:now\s+)?available\s+(?:on|under|at)|"
                           r"will\s+be\s+(?:SEDAR\s+)?filed\s+today|\bFiles\b|\bFiled\b")


_TRW = re.compile(r"(?i)technical\s+report|43\s*-?\s*101|\bPEA\b|\bPFS\b|\bDFS\b|feasibility|resource\s+estimate|\bMRE\b|economic\s+assessment")
_TRW2 = re.compile(r"(?i)technical\s+report|43\s*-?\s*101|\bPEA\b|\bPFS\b|\bDFS\b|feasibility\s+study|resource\s+estimate|\bMRE\b|"
                   r"economic\s+assessment|\bthe\s+report\b|mineral\s+resource")
_NONTECH = re.compile(r"(?i)early\s+warning|material\s+change\s+report|business\s+acquisition\s+report|annual\s+report|form\s+40-?F|"
                      r"\b20-F\b|\b10-K\b|information\s+circular|financial\s+statements|\bMD&A\b|prospectus|offering\s+document|"
                      r"insider\s+report|annual\s+information\s+form(?![^.]{0,80}technical)|\bAIF\b(?![^.]{0,80}technical)")
_STRONG_BODY = re.compile(r"(?i)\b(?:has|have)\s+(?:now\s+|today\s+|recently\s+)?(?:completed\s+and\s+)?(?:publicly\s+)?filed|"
                          r"\bannounce[sd]?\s+(?:today\s+)?(?:the\s+)?filing|\bannounce\s+that\s+it\s+has\s+filed|"
                          r"\b(?:was|were|has\s+been|have\s+been)\s+(?:publicly\s+)?filed\s+(?:today\s+)?(?:on|with|under)\s+(?:SEDAR|the)|"
                          r"\b(?:company|corporation)\s+(?:today\s+|recently\s+)?filed\s+(?:an?|the|its)\b|today\s+filed|"
                          r"will\s+be\s+(?:SEDAR\s+)?filed\s+today")
_BG_ANY = re.compile(r"(?i)\b(?:see|refer(?:ence)?|for\s+(?:further|more|additional)|additional\s+information|please\s+consult|"
                     r"described\s+in|summari[sz]ed\s+(?:in|from)|can\s+be\s+found|copies|a\s+copy|previously\s+filed|"
                     r"most\s+recent(?:ly)?|current\s+technical\s+report)\b")


def _nontech(s):
    if re.search(r"(?i)technical\s+report\s+summary|\bS-K\s*1300\b", s):
        return True
    return bool(_NONTECH.search(s)) and not re.search(r"(?i)technical\s+reports?\b|43\s*-?\s*101\s+(?:technical\s+)?report", s)


def _near(rx1, rx2, s, span):
    a = [m.start() for m in rx1.finditer(s)]
    if not a:
        return False
    for m in rx2.finditer(s):
        if any(abs(m.start() - x) <= span for x in a):
            return True
    return False


_WILL_FILE = re.compile(r"(?i)\b(?:will|shall|to)\s+(?:shortly\s+|soon\s+)?be\s+(?:SEDAR\s+)?filed\b(?!\s+today)|"
                        r"will\s+be\s+(?:included|contained|summari[sz]ed|detailed|presented)\s+in\s+(?:an?|the)\s+(?:NI\s*43\s*-?\s*101\s+)?"
                        r"(?:compliant\s+)?technical\s+report|within\s+(?:the\s+next\s+)?(?:45|forty-?five)\s*(?:\(45\)\s*)?days")


_NEG = re.compile(r"(?i)^(?:after|if|upon|once|should|in\s+the\s+event)\b[^.]{0,200}\b(?:shall|will)\b|\bafter\s+the\s+(?:company|optionee|corporation|purchaser)\s+has\s+(?:incurred|spent|completed)|\bno\s+(?:new\s+|updated\s+|independent\s+)?(?:NI\s*43\s*-?\s*101\s+)?(?:compliant\s+)?technical\s+report\s+(?:will|shall|is|was|has)|"
                  r"\b(?:is|was|are|were)\s+not\s+(?:currently\s+)?required|\bnot\s+(?:be\s+)?required\s+to\s+file|"
                  r"\bwill\s+not\s+(?:be\s+)?(?:fil|prepar|complet|publish)|\bincorrectly\s+stated|\bdoes\s+not\s+(?:intend|plan|expect)\s+to\s+(?:file|prepare|complete)|"
                  r"\bno\s+(?:longer\s+)?(?:intends?|plans?)\s+to\s+(?:file|prepare|complete)")


def _old_years(s, year):
    """A sentence about an engagement or filing years before the release: 'In 2010 SRK was engaged ...'."""
    if not year:
        return False
    ys = [int(y) for y in re.findall(r"\b((?:19|20)\d\d)\b", s)]
    return bool(ys) and max(ys) <= year - 2


def _past_filing(s, rel_date):
    """'recently filed ...' or 'filed ... on <date>' with the date well before the release: a background mention."""
    if re.search(r"(?i)\brecently\s+(?:publicly\s+)?filed|\bpreviously\s+filed|\bfiled\s+(?:earlier|last)\b", s):
        return True
    if re.search(r"(?i)pleased\s+to\s+announce|\btoday\b|\bannounces?\b", s):
        return False
    cands = []
    for d in re.finditer(r"(?i)\bfiled\b(?:[^.;]|\.(?=\w)){0,160}?\bon\s+(?=" + _DATE_RX + ")", s):
        m = _DATE.match(s, d.end())
        if m:
            cands.append(_iso(m))
    for d in re.finditer(r"(?i)\bon\s+(?=" + _DATE_RX + r")", s):
        m = _DATE.match(s, d.end())
        if m and re.match(r"(?i),?\s+(?:the\s+company|the\s+corporation|[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})\s+(?:has\s+)?filed\b", s[m.end():m.end() + 60]):
            cands.append(_iso(m))
    for iso in cands:
        if iso and (not rel_date or not (_shift(rel_date, -10) <= iso <= _shift(rel_date, 3))):
            return True
    return False


def _shift(iso, days):
    import datetime as _dt
    try:
        return (_dt.date.fromisoformat(iso) + _dt.timedelta(days=days)).isoformat()
    except ValueError:
        return iso


def _comm_ok(s):
    """'is underway' only counts when the report or study is what is underway, not a drill programme."""
    ms = [m for m in _COMM.finditer(s)]
    if not ms or not all(re.search(r"(?i)underway|in\s+progress", m.group(0)) for m in ms) or _WILL_FILE.search(s):
        return True
    rw = r"technical\s+report|43\s*-?\s*101|\bPEA\b|\bPFS\b|\bDFS\b|feasibility|resource\s+estimate|\bMRE\b|economic\s+assessment|" \
         r"mineral\s+resource|resource\s+update|scoping\s+study"
    for m in ms:
        pre = s[max(0, m.start() - 160):m.start()]
        subj = " ".join(pre.split()[-6:])
        if re.search(r"(?i)drill|program|campaign|survey|trench|sampling|exploration", subj):
            continue
        if re.search(rw, pre, re.I) or re.search(r"(?i)^\W*(?:\w+\W+){0,2}to\s+support\b[^.]{0,80}(?:" + rw + ")", s[m.end():m.end() + 120]):
            return True
    return False


def _pick_project(lists):
    firsts = [c[0][1] for c in lists if c]
    for p in firsts:
        if not p.endswith(("Deposit", "Deposits")):
            return p
    return firsts[0] if firsts else None


def _expected_in(sents):
    for s in sents:
        e = _EXPECT.search(s)
        if e:
            return _flat(e.group(1))
    return None


def _news(h, b, full):
    issuer = _issuer(b)
    sents = _sentences(b)
    fsents = _sentences(full)
    rows = []

    hl_filed = bool(_FILED_HL.search(h) and _TRW.search(h) and not _nontech(h))
    hl_comm = bool(_COMM.search(h) or re.search(r"(?i)\b(?:engages?|retains?|intent|commissions?|commences?\s+preparation|nearing\s+completion|"
                                               r"complet(?:es|ed|ion)|to\s+issue)\b|\breceives?\s+(?:the\s+|an?\s+|its\s+)?(?:[\w\-]+\s+){0,3}?"
                                               r"(?:technical\s+report|PEA|PFS|DFS|feasibility\s+study|pre-?feasibility|resource\s+estimate|MRE|economic\s+assessment)", h)) \
        and bool(_TRW.search(h)) and not _NEG.search(h)
    rel = _dateline(b)
    year = int(rel[:4]) if rel else None
    hl_withdrawn = bool(_WITHDRAWN.search(h) or re.search(r"(?i)\bremoves?\b[^.]{0,60}technical\s+report", h))

    title = _report_title(b)
    tt = title[1] if title else None
    if tt and re.search(r"(?i)^(?:[\w&.'\-]+\s+){0,4}(?:announces|reports|intersects|drills|files|closes|provides)\b", tt):
        tt = None

    filed_s = [s for s in sents if _FILED_BODY.search(s) and _TRW.search(s) and not _nontech(s)
               and not _BACKGROUND.search(s[:40])
               and not (_WILL_FILE.search(s) and not re.search(r"(?i)\b(?:has|have)\s+(?:now\s+)?filed|\b(?:was|been)\s+filed", s))]
    filed_s = [s for s in filed_s if not _NEG.search(s) and not _old_years(s, year)]
    if not hl_filed:
        filed_s = [s for s in filed_s if not _past_filing(s, rel)]
    strong_s = [s for s in filed_s if _STRONG_BODY.search(s) and not _BG_ANY.search(s)]
    comm_s = [s for s in fsents if (_near(_COMM, _TRW2, s, 70) or (_WILL_FILE.search(s) and _TRW.search(s))) and not _nontech(s)
              and not re.search(r"(?i)\bwill\s+be\s+(?:SEDAR\s+)?filed\s+today\b", s)
              and not _NEG.search(s) and not _old_years(s, year) and _comm_ok(s)
              and (s in sents or s == h or _WILL_FILE.search(s)
                   or not all(re.search(r"(?i)underway|in\s+progress", m.group(0)) for m in _COMM.finditer(s)))]
    wd_s = [s for s in sents if _WITHDRAWN.search(s)]

    status = None
    if hl_withdrawn or wd_s:
        status = "withdrawn"
    elif hl_filed or strong_s:
        status = "filed"
        pending = any(_WILL_FILE.search(x) and not _NEG.search(x) for x in sents)
        if pending and not re.search(r"(?i)\b(?:has|have)\s+(?:now\s+)?filed|\b(?:was|been)\s+filed|announces?\s+(?:the\s+)?filing|"
                                     r"filed\s+on\s+SEDAR|today\s+filed|will\s+be\s+(?:SEDAR\s+)?filed\s+today", b + " " + h):
            status = "commissioned"
    if status is None and (hl_comm or comm_s):
        status = "commissioned"
    if status is None:
        return rows, "no_report_statement"
    if status == "filed":
        filed_s = strong_s + [x for x in filed_s if x not in strong_s]

    lead = (filed_s if status == "filed" else wd_s if status == "withdrawn" else comm_s or filed_s or [h])
    lead = lead[0] if lead else h
    proj = _pick_project([_projects_in(h, issuer), _projects_in(tt, issuer) if tt else [], _projects_in(lead, issuer)])
    if not proj or proj.endswith(("Deposit", "Deposits")):
        from collections import Counter
        allp = Counter(p for _i, p in _projects_in(b[:8000], issuer) if not p.endswith(("Deposit", "Deposits", "Properties", "Projects")))
        if allp:
            proj = allp.most_common(1)[0][0]
    if not proj:
        for src in (h, lead):
            lp = re.search(r"((?:[A-ZÀ-Ý][\w'À-ÿ\-/.]*)(?:\s+" + _CAPW + r"){0,5}?)\s+(project|property)\b", src)
            if lp:
                proj = _clean_proj(lp.group(1), lp.group(2).title())
                if proj:
                    break
    if status == "commissioned" and lead != h and not hl_comm:
        rtype = _type_of(lead) or _type_of(tt) or _type_of(re.sub(r"(?i)supporting\s+|confirming\s+", "", h))
    else:
        rtype = _type_of(tt) or _type_of(re.sub(r"(?i)supporting\s+|confirming\s+", "", h)) or _type_of(lead)
    hp = _projects_in(h, issuer)
    if not rtype:
        if hp and _T_MINE.search(hp[0][1]) and not _T_RES.search(b[:3000]):
            rtype = "other"
        elif status == "commissioned" and not re.search(r"(?i)\b(?:has|have)\s+completed\s+(?:an?\s+)?(?:independent\s+)?"
                                                        r"(?:National\s+Instrument\s+|NI\s*)?43|\b(?:has|have)\s+completed[^.]{0,60}technical\s+report|"
                                                        r"\bamended\s+(?:NI\s*43\s*-?\s*101\s+)?technical\s+report", b + " " + h):
            rtype = "resource" if re.search(r"(?i)\bresources?\b", h) and not re.search(r"(?i)\bresources?\s+(?:inc|corp|ltd|limited)\b", h) \
                and _RES_WORDS.search(b[:3000] + " " + h + " resource estimate") and re.search(r"(?i)resource\s+(?:expansion|estimate|update|increase)|"
                                                                                         r"(?:new|updated|maiden|initial|expanded)\s+(?:\w+\s+)?resource", h) else None
        else:
            rtype = "property"
    if rtype == "property":
        i = sents.index(lead) if lead in sents else 0
        near = " ".join([h, tt or ""] + filed_s[:3] + sents[i + 1:i + 3])
        if _RES_WORDS.search(near) and not re.search(r"(?i)\bhistoric(?:al)?\s+(?:mineral\s+)?(?:resource|estimate)", near):
            rtype = "resource"
    main = _blank("news")
    main.update(report_type=rtype, project=proj, status=status, title=tt)
    ctx = " ".join(filed_s[:3] + ([tt] if tt else []))
    if title:
        ctx = b[max(0, title[0] - 400):title[0] + len(tt or "") + 600] + " " + ctx
    main["effective_date"] = _effective(ctx) or (_effective(b) if status != "commissioned" else None)
    main["report_date"] = _report_date(ctx)
    firms, qps = _authors(b, issuer)
    hw = _fold(h).split()[:1]
    firms = [f for f in firms if not (hw and _fold(f).split()[:1] == hw and not re.match(r"(?:" + _KNOWN + r")\b", f))]  # the issuer named in the headline
    main["author_firm"] = "; ".join(firms) or None
    main["qps"] = qps
    main["amended"] = 1.0 if re.search(r"(?i)\b(?:amended|revised|restated)\s+(?:and\s+restated\s+)?(?:NI\s*43-?101\s+|independent\s+)?"
                                       r"(?:technical\s+)?reports?\b|revised\s+version\s+of\s+(?:its|the)\s+(?:NI\s*43-?101\s+)?technical\s+report", h + " " + " ".join(filed_s[:2] + comm_s[:1])) else 0.0
    main["metal"] = _metal(" ".join([h, tt or "", proj or ""])) or _metal(b[:1500])
    if status == "filed":
        m = re.search(r"(?i)filed\s+(?:on\s+SEDAR\+?\s+)?on\s+", b)
        main["filing_date"] = (_date_at(b, m.end(), 4) if m else None) or _dateline(b)
    if status == "commissioned":
        i = sents.index(lead) if lead in sents else -1
        main["expected"] = _expected_in([lead] + (sents[i + 1:i + 3] if i >= 0 else []) + comm_s[:2] + [h])
        main["filing_date"] = None
    main["evidence"] = lead[:200]
    if rtype in ("PEA", "PFS", "FS"):
        econ, _st = _econ_from_reader(h, b)
        if econ:
            main.update({k: v for k, v in econ.items() if v is not None})
    if rtype in ("resource", "PEA", "PFS", "FS"):
        main["resource"] = _res_from_reader(h, b)
    rows.append(main)

    # further reports: a replacement or a planned study named separately from the main report
    def _pk2(p):
        return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in _pkey(p or "").split())
    seen = {(_pk2(proj), status, rtype)}
    for s in comm_s:
        if s == lead:
            continue
        t2 = _type_of(s)
        if not t2 and not re.search(r"(?i)technical\s+report|43-?101|\bthe\s+report\b", s):
            continue
        if re.search(r"(?i)within\s+(?:45|forty)", s) and status == "filed":
            continue
        if status == "filed" and re.search(r"(?i)\b(?:was|were|had\s+been)\s+(?:engaged|retained|commissioned|appointed|responsible)\b", s):
            continue
        if _DRILLY.search(s) and not re.search(r"(?i)technical\s+report|\bPEA\b|\bPFS\b|feasibility\s+study|economic\s+assessment", s):
            continue
        ps = _projects_in(s, issuer)
        p2 = ps[0][1] if ps else proj
        same_proj = _pk2(p2) == _pk2(proj)
        key = (_pk2(p2), "commissioned", t2)
        if key in seen:
            continue
        if same_proj and status == "commissioned" and (t2 is None or t2 == rtype or rtype is None):
            if rtype is None and t2:
                main["report_type"] = rtype = t2
            continue
        if same_proj and status == "filed" and t2 in (None, rtype) and not re.search(r"(?i)\bnew\b|\bupdated\b", s):
            continue
        seen.add(key)
        r2 = _blank("news")
        r2.update(report_type=t2 if t2 or status != "withdrawn" else rtype, project=p2, status="commissioned", evidence=s[:200],
                  metal=main["metal"], amended=1.0 if status == "withdrawn" or re.search(r"(?i)\bamended\b", s) else 0.0)
        i = fsents.index(s)
        r2["expected"] = _expected_in([s] + fsents[i + 1:i + 3])
        fs = _firms_near(s, issuer)
        r2["author_firm"] = "; ".join(fs) or None
        rows.append(r2)
    # one filing statement naming several projects: one row per project
    for s in filed_s[:3]:
        if not re.search(r"(?i)technical\s+reports?\b", s):
            continue
        ps = [p for _i, p in _projects_in(s, issuer)]
        for a, c in re.findall(r"(?:the\s+)?([A-Z][\w'\-]+)\s+(?:and|,)\s+(?:the\s+)?([A-Z][\w'\-]+)\s+(?:Projects|Properties|projects|properties)\b", s):
            ps += [a + " Project", c + " Project"]
        keys = [k for k in dict.fromkeys(_pkey(p) for p in ps) if k]
        keys = [k for k in keys if not any(k != o and (set(k.split()) <= set(o.split()) or set(o.split()) <= set(k.split())) and len(o) < len(k) for o in keys)]
        if len(keys) >= 2:
            out = []
            titles = _all_titles(b)
            for key in keys:
                r2 = dict(main)
                full_ = [q for _i, q in _projects_in(b, issuer) if _pkey(q) == key]
                r2["project"] = full_[0] if full_ else next(p for p in ps if _pkey(p) == key)
                tl = [x for _i, x in titles if key and key.split()[0] in _fold(x)]
                r2["title"] = tl[0] if tl else None
                out.append(r2)
            rows = out + rows[1:]
            break
    rows = [r for r in rows if r.get("project") or r.get("report_type")]
    return rows, (None if rows else "no_named_report")


# ------------------------------------------------------------------ public API
_ANY = re.compile(r"(?i)technical\s+report|43\s*-?\s*101|\bPEA\b|\bPFS\b|feasibility|resource\s+estimate|\bMRE\b|"
                  r"economic\s+assessment|qualified\s+person")


def analyse(headline, body):
    if not _ANY.search(headline or "") and not _ANY.search((body or "")[:TEXT_CAP]):
        return {"rows": [], "doc_kind": "news", "reason": "no_report_words"}
    raw = _norm(body or "")
    hh = _flat(_norm(headline))
    kind = _doc_kind(hh, raw)
    h, b = _prepare(headline, body, kind != "news")
    if kind == "consent":
        row = _consent(h, b, raw)
        return {"rows": [row], "doc_kind": kind, "reason": None}
    if kind == "cover":
        row = _cover(h, b, raw)
        return {"rows": [row], "doc_kind": kind, "reason": None}
    full = _flat(re.sub(r"https?://\S+", " ", _norm((body or "")[:TEXT_CAP])))
    m = _FLS.search(full, 600)
    if m:
        full = full[:m.start()]
    rows, reason = _news(h, b, full)
    if _NOT_43101.search(h) and not re.search(r"(?i)43-?101", h):
        rows, reason = [], "not_ni43101"
    return {"rows": rows, "doc_kind": kind, "reason": reason}


def _as_text(k, v):
    if k == "qps":
        return "; ".join(v) if v else None
    return str(v)[:300] if v not in (None, "") else None


def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["rows"]:
        return [F.Record(KIND, facts=[F.Fact("is_report", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"] or "none")], confidence=0.0)]
    out = []
    for r in a["rows"]:
        fs = [F.Fact("is_report", value_num=1.0)]
        r = dict(r)
        r["resource_json"] = json.dumps(r["resource"], separators=(",", ":")) if r.get("resource") else None
        for k in TXT_FIELDS:
            t = _as_text(k, r.get(k))
            if t:
                fs.append(F.Fact(k, value_text=t if k != "resource_json" else r[k][:4000]))
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
            if field_ == "is_report":
                yes = num == 1.0
            elif field_ in NUM_FIELDS:
                r[field_] = num
            elif field_ in TXT_FIELDS:
                r[field_] = text
        if yes and r["status"]:
            r["amended"] = bool(r["amended"])
            r["qps"] = [q for q in (r["qps"] or "").split("; ") if q]
            try:
                r["resource"] = json.loads(r.pop("resource_json")) if r.get("resource_json") else None
            except ValueError:
                r["resource"] = None
            rows.append(r)
    return {"is_report": bool(rows), "rows": rows}


JUDGED = ("report_type", "project", "status", "effective_date", "author_firm", "title", "report_date", "filing_date",
          "expected", "qps", "amended", "metal", "npv", "irr", "capex", "resource")


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

    fill = " The project is road accessible and hosts several gold showings along a regional structure." * 3
    r = analyse("ABC Files NI 43-101 Technical Report for the Alpha Gold Project",
                "Toronto, March 2, 2026 - ABC Gold Corp. (TSXV: ABC) (\"ABC\" or the \"Company\") announces that it has filed "
                "an independent NI 43-101 technical report titled \"NI 43-101 Technical Report on the Alpha Gold Project, Ontario\" "
                "with an effective date of January 15, 2026. The report was prepared by P&E Mining Consultants Inc." + fill)
    eq("filed row", [(x["status"], x["report_type"], x["project"], x["effective_date"], x["author_firm"]) for x in r["rows"]],
       [("filed", "property", "Alpha Gold Project", "2026-01-15", "P&E Mining Consultants")])
    r = analyse("ABC Announces Maiden Mineral Resource Estimate at Alpha Gold Project",
                "Toronto, March 2, 2026 - ABC Gold Corp. (TSXV: ABC) is pleased to announce a maiden mineral resource estimate "
                "for its Alpha Gold Project. A technical report supporting the mineral resource estimate will be filed on "
                "SEDAR+ within 45 days." + fill)
    eq("45 days -> commissioned", [(x["status"], x["report_type"], x["expected"]) for x in r["rows"]],
       [("commissioned", "resource", "within 45 days")])
    r = analyse("ABC Intersects 2.1 g/t Gold over 30 m at Alpha",
                "Toronto, March 2, 2026 - ABC Gold Corp. (TSXV: ABC) reports drill results. For further information, please "
                "see the technical report titled \"NI 43-101 Technical Report on the Alpha Gold Project\" filed on SEDAR+." + fill)
    eq("background citation is not a row", r["rows"], [])
    r = analyse("ABC Announces Filing of Early Warning Report",
                "Toronto, March 2, 2026 - Mr. X has filed an early warning report under National Instrument 62-103." + fill)
    eq("early warning report is not a technical report", r["rows"], [])
    r = analyse("Consent of qualified person (NI 43-101)",
                "CONSENT OF QUALIFIED PERSON\nI, Jane Smith, P.Geo., consent to the public filing of the technical report "
                "titled \"Preliminary Economic Assessment for the Beta Copper Project\" dated May 1, 2026 with an effective date "
                "of March 31, 2026 (the \"Technical Report\").\n" + ("x " * 200) + "\nDated this 5th day of May, 2026\nJane Smith, P.Geo.")
    eq("consent", [(x["status"], x["report_type"], x["project"], x["effective_date"], x["filing_date"], x["doc_kind"])
                   for x in r["rows"]],
       [("filed", "PEA", "Beta Copper Project", "2026-03-31", "2026-05-05", "consent")])
    recs = extract("ABC Files NI 43-101 Technical Report for the Alpha Gold Project",
                   "Toronto, March 2, 2026 - ABC Gold Corp. (TSXV: ABC) announces that it has filed an NI 43-101 technical "
                   "report on its Alpha Gold Project." + fill)
    p = to_prediction(recs)
    eq("round trip", [(x["status"], x["project"]) for x in p["rows"]], [("filed", "Alpha Gold Project")])
    eq("no report words", analyse("ABC Closes Private Placement", "ABC closed a private placement." + fill)["rows"], [])
    print("technical: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test("-v" in sys.argv) else 0)
