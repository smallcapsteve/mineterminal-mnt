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

1.0.4 (2026-09-30, from the ACC150 blind labels and the outside-tag samples):
  - PROJECT NAMES: the full name the release defines for a short form, with the short form kept in brackets
    ("NRW Project" -> "North Ridge West Project (NRW)"); never a headline fragment ("Ownership of X Project" -> "X
    Project"; "Target Project", "Selects Mine", "Robust Project" -> none), the issuer or a firm written with a company
    form ("Acme Mines", "Omni Projects SA"), an activity the release calls a project ('the carbon-in-leach circuit (the
    "CIL Project")'), or a deposit when the release names the project that holds it; "Alpha Operations" and "Beta
    District" are read. When the name is not one, the project the report sentence, the sentence before it or the
    headline names is taken.
  - SEVERAL PROJECTS: a study to come goes on the project its own sentence names (else the one the sentence before
    names), not the headline's or the flagship; a filing sentence makes one row per project only when it files several
    reports ("technical reports on A and B", "a technical report for each of A and B, respectively entitled ..."), not
    for one report on two projects or a neighbour named in passing.
  - NOT ROWS: studies in the About paragraph or footnotes (except the Company's own study with a timing, Justin's QC
    extended: "... is commencing the preparation of an updated PEA that is expected in early 2026"); another company's filing or study ("Northwind announced the
    filing of ...", a partner's or buyer's study, "filed under <other>'s SEDAR profile"); a royalty or streaming
    company's recap of its operators' studies; environmental (EIA/ESIA) documents; a study "underway", "in progress",
    "planned" or "expected to be completed" with no timing; a programme (drilling, test work, mining) that is what is
    "nearing completion"; "Completes Acquisition ... PEA Economics".
  - FILED only when this report is what was filed: not a citation ("the report that the Company has filed", "from which
    information is extracted", "is detailed in a report entitled ...", "filed on SEDAR in September 2016"), not a report
    dated over a year before the release (unless amended, re-filed or new), not "has filed a title opinion ..., and is
    preparing a 43-101 report" (that report is commissioned).
  - A STUDY STILL TO COME carries no earlier report's effective date (over 12 months before the release) or title; a
    recent effective date the release states is kept. A commissioned row with no project is not written.

1.0.5 (2026-10-01, from the outside-tag samples conf3 and conf4): a row only for the release's own report news.
  - NOT A REPORT IN HAND: an engagement for other work ("engaged to optimize the flotation design", "Engages X as
    Interim Consultant to Facilitate ..."); a programme that is what is underway or nearing completion ("The
    geotechnical program ... is also nearing completion", "Drilling to support the upcoming MRE is nearing
    completion"); a "will be filed" line about a report dated over a year before the release; an engagement told as the
    history of a report filed long ago ("K92 engaged Mincore to complete the PEA" beside that PEA's 2018 title); a
    resource estimate to come with no report, filing, 45-day rule or author in view (the round-4 admission rule R8;
    Justin's ruling pending, _V5_ESTIMATE_NEEDS_REPORT).
  - THE STUDY'S OWN PROJECT: the clause of a list that names the report; a project its sentence names alone ("At Castle
    Mountain, a pre-feasibility study is underway"); the place it opens with ("Regarding Terronera, ..."); the one
    other project the sentence before names; never the issuer's portfolio ("All Four Acme Projects"), a description
    ("a Stand-Out Oxide ... Development Project"), or a mine the release places inside a project ("the Mohave Project,
    including the Rosebud Mine" -> Mohave Project). An engagement cut after "Inc." is read whole.
  - ONE ROW PER REPORT: the same study named on a deposit is the project's study; "Pre - feasibility" is a PFS; a
    commissioning headline types the study, not a titled earlier report in the body.
  - AUTHOR AND DATE: no "Ni-Cu-Co" or "Qualified Person" heading as a firm, no caption ("Prepared by X"), history
    timeline ("2012: X was retained") or firm engaged for other work; a division ("Met-Chem, a division of DRA") is the
    author; "commissioned/hired/appointed X", "performed by X" name authors. A study to come takes the effective date
    the release gives for its report or for its own study type, not an earlier report's.
  - CITED, NOT FILED: "has filed ... effective March 2, 2017" in a March 29, 2018 release is a citation (to the day), and
    "Papua New Guinea" does not make a report new.
  - FULL TEXT (2026-10-01, the tagged releases the box reads in full that 1.0.4 stopped showing): a report in hand said
    in other words is a row again -- headlines "Commences ... Technical Report", "Completes Site Visit & Technical
    Report on X", "Technical Report Completed on X", "... due for completion", "to Amend Technical Report", "Reports
    Updated Technical Report"; body lines "is in the process of preparing", "has commenced work on", "expects to file",
    "45 days from the date hereof", "X has completed a NI 43-101 Technical Report", "anticipates completion of a
    technical report", "early in the New Year". "Is pleased to report that it has filed" is the filing, not a citation.
    Filings also read: "has completed the filings of", "has added the Technical Report on X to SEDAR", "accepted for
    filing ... can be viewed on SEDAR"; a new-report headline with a body filing line is filed; a filed report sits on
    the project its report words name ("the Frog Property 43-101 Report"); "Technical Reports on the A and B Gold Mines,
    respectively" are two rows; "the Technical Report discloses a mineral resource" types it. Text formats: Unicode
    hyphens ("NI43\u2010101") read as "-", and a closing quote ends a sentence.

1.0.6 (2026-10-04, FIX5 from the ACC150c blind labels: report date, QPs, authors):
  - REPORT DATE: the date the release gives for the report itself -- "issued September 8, 2026", "an issue date / a report
    date / a revised and amended date of ...", "bearing the date of signature of ...", else the date a title or "(the
    "Technical Report")" is "dated" -- on a filed or withdrawn report and in a consent; it comes before any other "dated"
    ('... and dated January 29, 2019 supersedes the report dated December 20, 2017'). Never a news release's, prospectus' or
    standard's date (also a quoted release title: 'news release: "... IRR," dated ...'), "dated effective", or a date before
    the report's effective date; a report still to come has none.
  - QP NAMES: initials first ("W. Lewis", "R.M. Gowans", "D. Grant Feasby"), accents, post-nominals in brackets ("Louis
    Cohalan (MAIG)") or without stops ("MSc", "BSc", "P.G.", "P.ENG", "FIMMM"), ending at a word boundary ("Page QUALIFIED"
    is not a name: "PE" is not the start of "PERSONS"); no degree or heading words ("BSc Geology", "Deepak Malhotra PhD" ->
    "Deepak Malhotra", "Inc Edward Saunders" -> "Edward Saunders"), no "Star Diamond's"; one name once ("Scott Wilson" /
    "Scott E. Wilson"). A consent's author list is not cut at an initial ("co-authored by James L. Pearson, P.Eng., ...").
  - AUTHOR LINES: "will be contracted to complete the ... Technical Report", "X is the author of the Technical Report", "The
    MRE ... was under the supervision of X ... and has reviewed and approved" (the author line comes before the approval),
    "The MRE was undertaken by X", a list after "prepared by the following Qualified Persons:" (up to an approval line);
    "prepared by A and B ... under the supervision of the Qualified Person C" names C; laboratory work ("All analyses ...
    were performed by ALS ...") names no author; a closing quote ends a sentence ('... funding." NI 43-101 ...').

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
from portal import fingerprint as FP
from portal import project_names as PN

NAME = "technical"
VERSION = "1.0.6"  # 2026-10-01: only the release's own report news, on the study's own project, author and date; full-text losses fixed; 2026-10-04 FIX5: report date as stated, QP names and author lines read right
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
_ABOUT = re.compile(r"(?:^|\s)About\s+(?:the\s+Company|[A-Z][\w&.'\u2019\-]*(?:\s+[A-Z][\w&.'\u2019\-]*){0,5})\s*(?::|\s(?=[A-Z][a-z]+\s"
                    r"(?:is|was|Inc|Corp|Ltd|Limited|Resources|Metals|Mining|Gold|Silver|Copper|Energy|Minerals)\b))")


def _norm(s):
    s = unicodedata.normalize("NFKC", s or "").replace(chr(160), " ").replace("\u00ad", "")
    s = s.replace("\u2019", "'").replace("\u2018", "'")
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
                     r"(?<=[.;!?])\s+(?=[A-Z\u201c\"\u2022\u25aa(])|\s+[\u2022\u25aa\u25cf]\s+", text)
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
    t = re.sub(r"(?i)\bpre\s*-\s*feasibility", "pre-feasibility", t)     # 1.0.5: a PDF's "Pre - feasibility" is a PFS
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
_CAPW = r"(?:[A-Z\u00c0-\u00dd0-9][\w'\u00c0-\u00ff\-/.]*|\(\d\)|de|del|la|di|du|des|do|y|and|&|\u2013|-|of)"
_PROJ_RX = re.compile(r"((?:[A-Z\u00c0-\u00dd][\w'\u00c0-\u00ff\-/.]*)(?:\s+" + _CAPW + r"){0,6}?)\s+" + _SUFFIX + r"\b")
_PROJ_LOWER = re.compile(r"((?:[A-Z\u00c0-\u00dd][\w'\u00c0-\u00ff\-/.]*)(?:\s+" + _CAPW + r"){0,5}?)\s+(?:project|property|mine|deposit)\b")
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
    if re.search(r"\s[\u2013\u2014]\s|\s-\s", name):
        name = re.split(r"\s[\u2013\u2014]\s|\s-\s", name)[-1]
    ws = name.split()
    # cut at the last word that cannot be part of a name
    cut = 0
    for i, w in enumerate(ws):
        if w in _STOP_INNER or w.rstrip(",:;.") in _STOP_INNER or re.match(r"^\d{4}\.?$", w) or w.endswith((",", ":", ";")) \
                or (w.endswith(".") and len(w) > 3 and not re.match(r"^(?:[A-Z]\.)+$|^(?:Mt|St|Ste|Pt)\.$", w)):
            cut = i + 1
    ws = ws[cut:]
    while ws and (ws[0] in _BAD_LEAD or ws[0].lower() in ("and", "of", "&", "-", "\u2013", "de", "y") or re.search(r"['\u2019]s$", ws[0])):
        ws = ws[1:]
    while ws and ws[-1].lower() in ("and", "of", "&", "-", "\u2013", "de", "y", "the"):
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


def _pn_in(t, issuer=None):
    """1.0.1: the projects a text names, from the shared helper, in _projects_in's shape: [(position, "Name Suffix")],
    a deposit after the projects. _projects_in, _clean_proj and _pkey stay as they were for the Permits reader,
    which borrows them (it moves to the helper in its own release)."""
    # 1.0.2: the shared adapter (helper 1.0.4) does what this function did in 1.0.1: helper names first, this
    # reader's own finder when the helper names none, no mills, deposits after projects; "(1)" is kept by the helper
    return PN.find_with(t, _projects_in, issuer)


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
          r"Minetech|Mercator|InnovExplo|GE21|ERM|SGS|CSA\s+Global|Fuse\s+Advisors|Sims\s+Resources|WWC|Knight\s+Pi[e\u00e9]sold|"
          r"Fluor|AtkinsR[e\u00e9]alis|Hinterland|Dahrouge|MSA|Understood\s+Mineral\s+Resources|PLR\s+Resources|Evomine|Synectiq|"
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
    f = re.sub(r"^[A-Z][\w.]*-based\s+", "", f)       # 1.0.5: "Montreal-based Met-Chem" is Met-Chem
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
        if re.search(r"-\s*Co\.?\s*$", raw) or re.search(r"(?i)\bqualified\s+persons?\b|\bproject\b|\bdeposit\b", f):
            continue      # 1.0.5: "Gochager Lake Ni-Cu-Co" (cobalt, not a company form), a "Qualified Person" heading
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
                        r"\b(?:are|is|include|responsible)\b|\bwith\s+contributions?\s+from\b|\bengaged\b|\bretained\b|"
                        r"\b(?:commissioned|hired|appointed|selected)\b|\b(?:performed|carried\s+out|headed(?:\s+up)?)\s+by\b")  # 1.0.5
_APPROVAL = re.compile(r"(?i)\b(?:reviewed\s+and\s+approved|approved\s+(?:the\s+)?(?:scientific|technical)|has\s+reviewed\s+and|"
                       r"verified\s+the\s+(?:scientific|technical))\b")


# 1.0.6: more ways a release names who writes the report: "will be contracted to complete the ... Technical Report", "X of
# Y is the author of the Technical Report", "The MRE ... was under the supervision of X"
_AUTH_MORE = re.compile(r"(?i)\bcontracted\b|\bis\s+the\s+(?:lead\s+)?author\s+of\b|\bauthors?\s+of\s+the\s+(?:technical\s+)?report\b|"
                        r"\b(?:was|were|is|are)\s+(?:completed\s+|prepared\s+)?under\s+the\s+(?:direct\s+)?supervision\s+of\b")
_AUTH_CUE = re.compile(r"(?i)\b(?:prepared|authored|co-?authored|compiled|completed|written|undertaken|estimated|led)\s+"
                       r"(?:independently\s+|jointly\s+)?by\b|"
                       r"\bunder\s+the\s+(?:direct\s+)?supervision\s+of\b|\bis\s+the\s+(?:lead\s+)?author\s+of\b")


# 1.0.6: not an author line -- laboratory work ("All analyses used for the Resource Estimates were performed by ALS ...
# Laboratories", "relied on analytical work completed by SGS ...")
_LAB_WORK = re.compile(r"\b(?:analys[ie]s|assays?|assaying|analytical\s+work|sample\s+preparation)\b[^.]{0,60}?\b(?:performed|completed|"
                       r"carried\s+out|conducted|done|undertaken)\s+(?:\w+\s+)?by\b")


def _author_before_approval(s):
    """1.0.6: a sentence that says who prepared the report or estimate before it says that person approved this release's
    technical content ("The MRE ... was under the supervision of X, P.Eng., ... and has reviewed and approved the content
    of this news release") names an author."""
    a, b = _AUTH_CUE.search(s), _APPROVAL.search(s)
    return bool(a and b and a.start() < b.start())


def _authors(text, issuer=None, strict=False):
    """(firms, qps) of a report, in the order the item names them; the lead firm first."""
    firms, qps = [], []
    sents = _v6_split(_sentences(text))      # 1.0.6: a closing quote ends a sentence here too ('... funding." NI 43-101 ...')
    # 1.0.6: a lead-in that ends in a colon or semicolon ("The Report was prepared by the following Qualified Persons;")
    # carries the list that follows it
    joined = []
    for i, x in enumerate(sents):
        if x.endswith((":", ";")):
            for y in sents[i + 1:i + 30]:
                if not _qps_in(y) and len(y) > 80 or _APPROVAL.search(y):
                    break
                x += " " + y
        joined.append(x)
    sents = joined
    ranked = []
    for i, s in enumerate(sents):
        if not (_AUTH_SENT.search(s) or _AUTH_MORE.search(s)):
            continue
        if _APPROVAL.search(s) and not _author_before_approval(s):
            continue
        if _LAB_WORK.search(s):
            continue      # 1.0.6: laboratory work
        pri = 0 if re.search(r"(?i)(?:prepared|compiled|led|authored|written|performed|carried\s+out|headed(?:\s+up)?)\s+"
                             r"(?:independently\s+|jointly\s+)?by|independently\s+prepared|"
                             r"(?:is\s+(?:now\s+)?preparing|nearing\s+completion|engaged|retained|commissioned|hired|appointed)", s) \
            else 1 if re.search(r"(?i)supervision|by\s+independent|contributions?\s+from", s) else 2
        if pri == 0 and re.match(r"(?i)\W*prepared\s+by\b", s):
            pri = 2       # 1.0.5: a figure or page caption ("Prepared by X"), not the report's author line
        if re.search(r"(?:^|\s)(?:19|20)\d\d\s*:\s", s):
            continue      # 1.0.5: a history timeline ("2012: Wardrop ... was retained to ...")
        eng = _V5_ENGAGE.search(s)
        if eng and not re.search(r"(?i)\b(?:prepared|compiled|authored|written|performed|carried\s+out|led|headed(?:\s+up)?)\s+"
                                 r"(?:independently\s+|jointly\s+)?by\b", s) and not _v5_purpose_ok(s, eng.start()):
            continue      # 1.0.5: a firm engaged for other work ("engaged Whittle to complete an optimization of the mine plan")
        if not re.search(r"(?i)report|PEA|PFS|feasibility|estimate|assessment|study|qualified|43-101|\bMRE\s+(?:was|were|is|has\s+been)\b", s):
            continue
        if re.search(r"(?i)\b(?:historic\w*|in\s+(?:19|200)\d\d)\b", s) and pri > 0:
            continue
        ranked.append((pri, i, s))
    ranked.sort()
    for _p, _i, s in ranked:
        seg = re.sub(r"(?i)^.*?\bprepared\s+for\s+[^,()]{0,80}?(?:\([^)]*\)\s*)?(?=\s+by\b)", "", s)
        # 1.0.5: "Met-Chem of Montreal, Quebec, a division of DRA Americas Inc." -> the division that wrote it
        for m in re.finditer(r"\bby\s+([A-Z][\w&'\-]+(?:\s+[A-Z][\w&'\-]+){0,2})(?:\s+(?:of|in)\s+[A-Z][^,()]{0,30}(?:,\s*[A-Z]"
                             r"[^,()]{0,30})?)?,\s+an?\s+(?:division|subsidiary|unit|business\s+unit)\s+of\s+", seg):
            d = _clean_firm(m.group(1))
            if d and d not in firms and not (issuer and _fold(d).split()[:1] == _fold(issuer).split()[:1]):
                firms.append(d)
        for _pos, f in _firms_in(seg, issuer):
            if f not in firms and not any(_fold(f) in _fold(x) or _fold(x) in _fold(f) for x in firms):
                firms.append(f)
        # 1.0.6: "prepared by A, P.Geo. and B, M.Sc., ... under the supervision of the Qualified Person ("QP"), C" -- C is the QP
        mq = re.search(r"(?i)\bunder\s+the\s+(?:direct\s+)?supervision\s+of\s+(?:the\s+)?(?:independent\s+)?(?:qualified\s+persons?|QPs?)\b",
                       seg)
        segq = seg[mq.end():] if mq and _qps_in(seg[mq.end():]) else seg
        # 1.0.6: one name once ("Scott Wilson" and "Scott E. Wilson")
        for q in _qps_in(segq):
            if q not in qps and not any(_fold(q).split()[-1:] == _fold(x).split()[-1:] for x in qps):
                qps.append(q)
        if strict and firms:
            break
    return firms, qps


def _fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    return "".join(c for c in s if not unicodedata.combining(c))


_POSTNOM = r"(?:P\.\s?Geo|P\.\s?Eng|P\.\s?Geol|Ph\.?\s?D|M\.\s?Sc|B\.\s?Sc|FAusIMM|MAusIMM|MAIG|FAIG|CPG|RM\s?SME|SME-RM|" \
           r"QP|C\.?P\.?G|Pr\.\s?Sci\.\s?Nat|Pr\.\s?Eng|FEC|CET|MBA|Dipl\.-Ing|PE|P\.E|MMSA|G\u00e9o|ing\.|g\u00e9o\.|P\.Geo)\.?"
_PERSON = r"((?:Dr\.\s+)?[A-Z][a-zA-Z'\-]+(?:\s+[A-Z]\.)*(?:\s+[A-Z][a-zA-Z'\-]+){1,2})"


# 1.0.6: a QP's name may open with initials ("W. Lewis", "R.M. Gowans", "Mr. A. San Martin") or carry accents ("F\u00e1bio
# Val\u00e9rio", "Maxime Dup\u00e9r\u00e9"); post-nominals may stand in brackets ("Louis Cohalan (MAIG)", "Simon Mortimer (M.Sc.,
# FAIG)"), be written without stops ("MSc", "BSc", "P.G.", "FIMMM", "FGS") and end at a word boundary ("PE" is not the start of
# "PERSONS")
_NAME_W = r"[A-Z\u00c0-\u00dd][a-z\u00df-\u00ff][a-zA-Z\u00c0-\u00ff'\-]*"
_PERSON_QP = (r"((?:Dr\.\s+)?(?:(?:[A-Z]\.\s?){1,3}\s*" + _NAME_W + r"(?:\s+" + _NAME_W + r")?|" + _NAME_W + r"(?:\s+[A-Z]\.)*"
              r"(?:\s+" + _NAME_W + r"){1,2}))")
_POSTNOM_QP = r"(?:" + _POSTNOM[len("(?:"):-len(r")\.?")] + r"|(?i:P\.\s?Eng|P\.\s?Geo)|P\.\s?G\.|M\.?\s?Sc|B\.?\s?Sc|M\.S\.|FIMMM|FGS|" \
              r"FSAIMM|MIGI|Pr\.?\s?Sci\.?,?\s?Nat)\.?(?![A-Za-z])"
# words that are not part of a person's name ("BSc Geology", "Page QUALIFIED", "Inc Edward Saunders")
_NOT_NAME = {"Sc", "BSc", "MSc", "Hons", "Geology", "Geological", "Geologist", "Engineering", "Engineer", "Eng", "Mining", "Mine",
             "Chemical", "Metallurgy", "Metallurgical", "Disclosure", "Persons", "Person", "Qualified", "Independent", "Technical",
             "Information", "Report", "Consultant", "Consulting", "Principal", "Senior", "Vice", "President", "Director", "Manager",
             "Page", "Note", "Notes", "The", "By", "And", "Prepared", "Signed", "Dated", "Consent", "Mr", "Ms", "Mrs", "Authored", "Co",
             "Inc", "Ltd", "Corp", "Limited", "LLC", "PhD"}
_QP_NAME_RX = re.compile(_PERSON_QP + r"\s*,?\s*\(?\s*(?=" + _POSTNOM_QP + r")")


def _qps_in(t):
    out = []
    for m in _QP_NAME_RX.finditer(t):
        n = re.sub(r"^(?:Dr\.\s+)", "", m.group(1)).strip()
        toks = n.split()
        while toks and toks[0] in _NOT_NAME:
            toks = toks[1:]
        while toks and re.match(r"(?:Ph\.?D|[BM]\.?Sc|DIC|Hons|MBA|[BM]Eng)\.?$", toks[-1]):
            toks = toks[:-1]      # "Deepak Malhotra PhD, QP", "Robin Rankin MSc DIC MAusIMM"
        n = " ".join(toks)
        if any(w.strip(".") in _NOT_NAME or re.match(r"[BM]\.?Sc", w) for w in toks) or len(toks) < 2:
            continue
        if n in out or re.search(r"'s$", n):
            continue      # a company's own QPs ("Star Diamond's QP's") are not a name
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
    return [(m.start(), _flat(m.group(1))) for m in re.finditer(r"[\u201c\"]\s*([^\u201d\"]{12,300}?)\s*[\u201d\"]", t)]


def _report_title(t, after=0):
    """A report title: quoted after 'titled/entitled', or quoted and defined as the (Technical) Report."""
    best = None
    for m in re.finditer(r"(?i)(?:entitled|titled|title\s+of)\s*,?\s*:?\s*(?:[\u201c\"]\s*([^\u201d\"]{12,300}?)\s*[\u201d\"]|'\s*([^']{12,300}?)\s*')", t):
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
    for m in re.finditer(r"[\u201c\"]\s*([^\u201d\"]{12,300}?)\s*[\u201d\"]\s*(?:,\s*[^()]{0,120})?\(\s*(?:the\s+)?[\u201c\"]?\s*(?:Technical\s+Report|Report|"
                         r"\d{4}\s+(?:PFS|PEA|FS)|PEA|PFS|Updated\s+Technical\s+Report)", t):
        return (m.start(), _flat(m.group(1)))
    for m in re.finditer(r"[\u201c\"]\s*((?:NI\s*43\s*-?\s*101\s+)?(?:Independent\s+)?Technical\s+Report\b[^\u201d\"]{8,300}?|[^\u201d\"]{4,200}?"
                         r"\bNI\s*43\s*-?\s*101\s+Technical\s+Report\b[^\u201d\"]{0,200}?)\s*[\u201d\"]", t):
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
    for m in re.finditer(r"(?i)(?:technical\s+report|report|study|assessment)[\u201d\"]?\s*(?:\([^)]{0,40}\)\s*)?,?\s*(?:is\s+)?dated\s+"
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


# 1.0.6: how a release states the report's own date
_RDATE_STATED = re.compile(r"(?i)\b(?:issue|signing|signature)\s+date\s*(?:of|is|was|:)?\s*|\breport\s+date\s+(?:of|is|was)\s+|"
                           r"\bdate\s+of\s+(?:signature|issue|signing)\s*(?:of\s+)?(?:the\s+)?|\b(?:revised|amended)(?:\s+and\s+(?:revised|amended))?\s+date\s+(?:of|is|was)\s+|"
                           r"\b(?:issued|signed)\s+(?:on\s+)?(?=[A-Z0-9])")
_RDATE_DATED = re.compile(r"(?i)\bdated\s+(?!effective)(?:as\s+of\s+)?")
_RDATE_TIED = re.compile(r"(?i)(?:report|study|assessment|estimate|[\u201d\")])\W{0,3}(?:\b(?:and|which|that)\b\s*)?"
                         r"(?:\b(?:is|was)\b\s*)?$")
_RDATE_NOT = re.compile(r"(?i)(?:releas\s?es?|prospectus|supplements?|circular|information\s+form|agreements?|letters?|guidelines|standards|MD&A|"
                        r"statements?|effectively|news)\W{0,4}$")


def _report_date_stated(t, eff=None):
    """1.0.6: the report's own issue or signing date ('issued September 8, 2026', 'bearing the date of signature of the January
    28th 2021', 'a revised and amended date of August 9, 2022'), else the date the report is 'dated' ('... Canada" dated
    April 11, 2024', '(the "Technical Report") and is dated November 8, 2024'); never a release's, prospectus' or
    standard's date, nor 'dated effective'."""
    for rx, tied in ((_RDATE_STATED, False), (_RDATE_DATED, True), (_RDATE_DATED, False)):
        for m in rx.finditer(t):
            pre = t[max(0, m.start() - 400):m.start()].rstrip(" ,(")
            if tied and not _RDATE_TIED.search(pre[-60:]):
                continue      # first a date tied to the report: '"<title>" dated', '(the "Technical Report") and is dated'
            if _RDATE_NOT.search(pre[-40:]):
                continue
            q = re.search(r"[\u201c\"]([^\u201c\u201d\"]{4,380})[\u201d\"],?$", pre)
            if q and _RDATE_NOT.search(re.sub(r"(?i)\s*(?:titled|entitled|:)\s*$", "", pre[:q.start()].rstrip())[-40:]):
                continue      # the quoted title is a news release's: 'news release: "... IRR," dated August 6, 2026'
            if re.match(r"\W{0,3}[^()]{0,30}\(\s*the\s+[\u201c\"]?\s*(?:news|press)\s+release", t[m.end():m.end() + 60], re.I):
                continue
            d = _date_at(t, m.end(), 6)
            if d and not (eff and d < eff):      # a report is not dated before its effective date
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
        # 1.0.6: 'of a Technical Report titled "..." by X, P.Geo. ..., dated July 6, 2026 (the "Technical Report")'
        row["report_date"] = _report_date_stated(b[tt[0]:tt[0] + len(tt[1]) + 400], row["effective_date"])
    if not row["report_date"] and tt:
        m = re.search(r"(?i)^[^.]{0,40}?dated\s+(?!effective)", tail[len(tt[1]) + 10:][:120])
        if m:
            row["report_date"] = _date_at(tail[len(tt[1]) + 10:], m.end(), 4)
    # signing date
    sign = None
    for m in re.finditer(r"(?i)\b(?:signed\s+and\s+dated|dated\s+and\s+signed|dated|signed)\s*(?:at\s+[A-Z][\w ,.]{0,40}?,?\s*)?"
                         r"(?:this\s+|on\s+(?:this\s+)?|:\s*|,\s*)(?=\d|[A-Z][a-z]+\s+\d)", b):
        if re.search(r"(?i)(?:release|report|letter)\s*[\u201d\"]?\s*,?\s*$", b[max(0, m.start() - 25):m.start()]):
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
    auth = re.search(r"(?i)(?:co-?authored|authored|prepared|written)\s+by\s+(.{0,600}?)(?:\(|\bwith\s+all\b|;|" +
                     r"(?<![\s(.][A-Z])(?<![\s(.][A-Z][a-z])\.\s+[A-Z])", b)       # 1.0.6: not cut at "James L. Pearson"
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
    sr = re.search(r"(?i)(?:news|press)\s+release\s+(?:of\s+[^.]{0,60}?)?(?:titled|entitled)\s*:?\s*[\u201c\"]\s*([^\u201d\"]{12,400}?)\s*[\u201d\"]|"
                   r"following\s+news\s+release\s*:\s*[\u201c\"]\s*([^\u201d\"]{12,400}?)\s*[\u201d\"]", b)
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
    m = re.search(r"(?i)(?:report|this\s+report)\s+(?:titled|entitled)\s*[\u201c\"]\s*([^\u201d\"]{12,300}?)\s*[\u201d\"]", b)
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
                if re.search(r"\d+[:,]\d|\u00b0|\bmE\b|\bUTM\b|\bZone\b|(?i:prepared|effective|suite|street)", x):
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
        c = Counter(p for _i, p in _pn_in(b[:14000]) if not p.endswith(("Properties", "Projects")))
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
    ps = _pn_in(t)
    if ps:
        return ps[0][1]
    return None


# ------------------------------------------------------------------ news releases
# 1.0.5 (full text): a report document (not a study or an estimate alone)
_V6_DOC = r"(?:technical\s+report|(?:NI\s*)?43\s*-?\s*101(?:\s+compliant)?\s+(?:technical\s+)?report)"
# 1.0.5 (full text): other filing statements -- "has completed the filings of ... Technical Reports", "has added the
# Technical Report on X to SEDAR", "a ... report has been accepted for filing by the Exchange and can be viewed on SEDAR"
_V6_FILED = (r"\b(?:has|have)\s+(?:now\s+)?completed\s+(?:the\s+)?filings?\s+of\b|\b(?:has|have)\s+(?:now\s+)?(?:added|posted|uploaded)\s+"
             r"[^.]{0,120}?\bto\s+SEDAR|\baccepted\s+for\s+filing\b[^.]{0,120}?\b(?:can|may)\s+be\s+viewed\s+(?:on|under|at)\b[^.]{0,40}SEDAR")
_FILED_HL = re.compile(r"(?i)\b(?:re-?)?(?:files?|filed|filing|filings|file)\b|\bavailable\s+on\s+SEDAR|\bposts?\b[^.]{0,40}\breport|"
                       r"\b(?:publishes|published|releases|released)\b[^.]{0,60}technical\s+report")
_REPORT_WORD = re.compile(r"(?i)technical\s+report|43-?101\s+report|\b(?:PEA|PFS|MRE|feasibility|pre-?feasibility|resource\s+"
                          r"estimate|mineral\s+resource|economic\s+assessment)\b|\breport\b")
_FILED_BODY = re.compile(r"(?i)\b(?:(?:has|have)\s+(?:now\s+|today\s+)?(?:completed\s+and\s+)?filed|announces?\s+(?:today\s+)?(?:the\s+)?(?:filing|that\s+it\s+has\s+filed)|"
                         r"(?:was|were|been|is|being)\s+filed|filed\s+(?:on|under|with|to)\s+(?:SEDAR|the\s+Company)|"
                         r"(?:is|are)\s+(?:now\s+)?available\s+(?:on|under|at)\s+(?:SEDAR|the\s+Company|www\.sedar)|"
                         r"the\s+filing\s+(?:on\s+SEDAR\+?\s+)?of|will\s+be\s+(?:SEDAR\s+)?filed\s+today|filed\s+(?:an?|the|its)\s+|" + _V6_FILED + ")")
_COMM = re.compile(r"(?i)within\s+(?:the\s+next\s+)?(?:45|forty-?five)\s*(?:\(45\)\s*)?days|"
                   r"\b(?:engag|retain|commission|appoint|contract|hire)\w*\s+(?:[^.]|\.(?!\s+[A-Z][a-z])){0,140}?\bto\s+(?:prepare|write|complete|author|produce|"
                   r"update|undertake|carry\s+out|conduct|perform)\b|\bintent(?:ion)?\s+to\s+(?:complete|prepare|file)|"
                   r"\b(?:is|are)\s+(?:currently\s+|now\s+)?(?:preparing\s+(?:a|an|the|its)\b|being\s+prepared|in\s+preparation|underway)|\bnear(?:ing|s)\s+completion|"
                   r"\bwill\s+(?:shortly|soon)\s+be\s+filed|\bwill\s+be\s+filed\s+(?:shortly|in\s+the\s+coming|on\s+SEDAR\+?\s+(?:shortly|within|in))|"
                   r"\bplans?\s+to\s+(?:prepare|complete|publish|deliver)\s+(?:a|an|the)\s+(?:new|updated)|"
                   r"\bcommenc\w+\s+(?:the\s+)?preparation\s+of|\bwill\s+be\s+filing\s+an?\b|\bwill\s+file\s+an?\b|"
                   r"\bexpected\s+to\s+be\s+(?:completed|delivered|filed|released|published)\b|\bis\s+expected\s+(?:in|by)\s+(?:Q[1-4]|H[12]|the\s+(?:first|second|third|fourth)|early|mid|late)|"
                   r"\b(?:underway|in\s+progress)\s+and\s+(?:is\s+)?expected|\bproceed\s+with\s+(?:a\s+)?re-?filing\b|\bre-?commit\w*\s+to\s+another|\bto\s+(?:prepare|write)\s+(?:a|an|the)\s+(?:new\s+|updated\s+|independent\s+)?(?:NI\s*43-?101|technical)"
                   # 1.0.5 (full text): other ways a release says its report is in hand or due
                   r"|\bin\s+the\s+process\s+of\s+(?:preparing|completing|finali[sz]ing|updating)\b"
                   r"|\b(?:has|have)\s+(?:now\s+)?(?:commenced|begun|started|initiated)\s+(?:work\s+on|(?:the\s+)?preparation\s+of)\b"
                   r"|\b(?:anticipates?|expects?|intends?|plans?)\s+(?:to\s+file|filing)\b"
                   r"|\b(?:45|forty-?five)\s*(?:\(45\)\s*)?days\s+(?:from|of|after)\s+(?:the\s+date\s+(?:hereof|of\s+this)|today)"
                   r"|\b(?:anticipates?|expects?)\s+(?:the\s+)?completion\s+of\s+(?:a|an|the|its)\s+(?:[\w\-]+\s+){0,5}?" + _V6_DOC +
                   r"|" + _V6_DOC + r"s?\s+(?:(?:is|are)\s+)?due\s+for\s+completion\b"
                   r"|" + _V6_DOC + r"s?\s+(?:[\w\-]+\s+){0,2}?to\s+be\s+completed\s+(?:in|by|during|within|before)\b(?!\s+(?:the\s+)?(?:company|corporation|issuer)\b)"
                   r"|\b(?:has|have)\s+(?:now\s+)?completed\s+(?:a|an|the|its)\s+(?:[\w\-]+\s+){0,3}?(?:NI\s*43\s*-?\s*101\s+)?"
                   r"(?:technical\s+report|43\s*-?\s*101\s+report)"
                   r"|\b(?:technical\s+report|43\s*-?\s*101\s+report)\s+(?:has|have)\s+(?:now\s+)?been\s+completed")
_WITHDRAWN =re.compile(r"(?i)\b(?:remov\w+|withdr[ae]w\w*|retract\w*)\s+(?:the\s+|its\s+|an?\s+)?(?:independent\s+)?(?:\w+\s+){0,3}?technical\s+report|"
                        r"technical\s+report[^.]{0,80}?(?:has|have|was|were)\s+been\s+(?:removed|withdrawn|retracted)")
_BACKGROUND = re.compile(r"(?i)\b(?:see|refer\s+to|reference\s+(?:is\s+made\s+)?to|as\s+(?:disclosed|described|detailed|reported|outlined)\s+in|"
                         r"(?:more|further)\s+(?:details|information)\s+(?:can\s+be\s+found\s+)?in|summari[sz]ed\s+(?:from|in)|"
                         r"available\s+for\s+review|contained\s+in|in\s+accordance\s+with)\b")
_NOT_43101 = re.compile(r"(?i)\bS-K\s*1300\b|\bJORC\b")
_EXPECT = re.compile(r"(?i)(within\s+(?:the\s+next\s+)?(?:45|forty-?five)\s*(?:\(45\)\s*)?days|(?:in|by|during)\s+(?:the\s+)?(?:early|mid|late)?\s*-?\s*"
                     r"(?:Q[1-4]|H[12]|first|second|third|fourth)\s*(?:quarter|half)?\s*(?:of\s+)?(?:(?:19|20)\d\d)?|"
                     r"(?:in|by)\s+(?:early|mid|late)[\s-]+(?:(?:19|20)\d\d|" + _MON + r")|shortly|in\s+the\s+(?:coming|next)\s+(?:weeks|months)|"
                     r"in\s+the\s+future|(?:\d|four|six|two|three)\s*(?:to|-|\u2013)\s*(?:\d|six|eight|four)\s+weeks)")


def _blank(kind):
    return {"report_type": None, "project": None, "status": "filed", "effective_date": None, "author_firm": None,
            "title": None, "report_date": None, "filing_date": None, "expected": None, "qps": [], "amended": 0.0,
            "metal": None, "resource": None, "npv": None, "npv_discount": None, "irr": None, "capex": None,
            "currency": None, "after_tax": None, "mine_life_years": None, "payback_years": None,
            "supports_release": None, "doc_kind": kind, "evidence": None}


def _issuer(b):
    m = re.search(r"([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5})\s*,?\s*(?:\((?:TSX|CSE|NYSE|NASDAQ|OTC|CBOE|NEO|ASX|TSXV)|"
                  r"\((?:the\s+)?[\u201c\"][^\u201d\"]{1,40}[\u201d\"]\s*(?:or\s+(?:the\s+)?[\u201c\"](?:Company|Corporation|Issuer)))", b[:1500])
    return m.group(1) if m else None


def _dateline(b):
    """The release's own date: 'SASKATOON, Saskatchewan, May 22, 2026 \u2013', 'London March 26 th 2026 :' or
    '(Newsfile Corp. - May 29, 2025)': the first date near the top that a dash, colon or bracket closes."""
    for d in _DATE.finditer(b[:700]):
        if re.match(r"\s{0,2}(?:[\u2013\u2014:/)]|-(?!\d)|\s-\s)", b[d.end():d.end() + 4]):
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
                          r"will\s+be\s+(?:SEDAR\s+)?filed\s+today|" + _V6_FILED)
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


# ------------------------------------------------------------------ 1.0.3: several projects per release (helper 1.0.5)
def _tr_several(h, b, issuer):
    """The projects the helper says the release reports on, when it reports on several; only those this reader's
    own finder also names in the headline or the opening 8,000 characters (its filters: no neighbour, no other
    company's). [] for a one-project release."""
    try:
        rp = PN.release_projects(h, b, issuer)
    except Exception:
        return []
    if rp.get("scope") != "several":
        return []
    seen = [q for _i, q in _pn_in(h, issuer)] + [q for _i, q in _pn_in(b[:8000], issuer)]
    return [p for p in rp.get("projects", []) if any(PN.same(p, q) for q in seen)]


_TR_FIRST = {"la", "el", "san", "santa", "mount", "mt", "west", "east", "north", "south", "upper", "lower", "new", "big",
             "little", "red", "lac", "lake", "rio", "cerro", "monte", "le", "les", "st", "saint", "black", "white",
             "grand", "golden", "gold", "silver", "copper"}
_TR_GENERIC = re.compile(r"(?i)^(?:production|highlighting|development|pipeline|dual|mexican|svp|neighbou?ring|"
                         r"near-mine|u\.s\.|us|canadian|nevada|australian|zone|reasonable)\b")


def _tr_short(p):
    """The short form a release uses for a project: 'Lagoa Salgada Polymetallic Project' -> 'Lagoa', 'La Preciosa
    Project' -> 'La Preciosa', 'Knauss Creek Property' -> 'Knauss'."""
    ws = re.sub(r"(?i)\s+(?:Projects?|Property|Properties|Mines?|Complex|Deposits?|Concessions?)$", "", p or "").split()
    if not ws:
        return None
    k = 2 if ws[0].lower() in _TR_FIRST and len(ws) > 1 else 1
    s = " ".join(ws[:k])
    return s if len(s) >= 3 else None


def _tr_project_at(b, s, names, others=(), look_back=True):
    """The project (one of names, or of others the reader finds) the report sentence s is about, on a release about
    several projects: the one the sentence names in its short form ('At Lagoa Salgada, the Optimized Feasibility
    Study ...', 'the Knauss Creek Report'); else, when look_back, the nearest mention in the 300 characters before it
    (PN.project_at) -- this reader's text has no paragraphs, so no further. None when unsure."""
    if len(names) < 2 or not s:
        return None
    i = b.find(s[:60])
    if i < 0:
        return None
    cands = [p for p in dict.fromkeys(list(names) + list(others)) if p and not _TR_GENERIC.search(p)]
    own = [p for p in cands if _tr_short(p) and re.search(r"(?<![\w'])" + re.escape(_tr_short(p)) + r"(?![\w'])", s)]
    if own:
        return own[0] if len({PN.key(p) for p in own}) == 1 else None
    if not look_back:
        return None
    lo = max(0, i - 300)
    try:
        return PN.project_at(b[lo:i + len(s)], i - lo, [n for n in names if not _TR_GENERIC.search(n)])
    except Exception:
        return None


# ------------------------------------------------------------------ 1.0.4: whose report, which project, is it news
# A timing a planned study states ("expected in Q2 2026", "by year end", "in the coming weeks").
_V4_TIMING = re.compile(
    r"(?i)\b(?:Q[1-4]|H[12]|[1-4]Q)\b|\b(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+(?:quarter|half)\b|"
    r"\b(?:in|by|during|before|for|early|mid|late|end\s+of|until|around)\s*-?\s*(?:the\s+)?(?:early\s+|mid\s*-?\s*|late\s+)?"
    r"(?:(?:19|20)\d\d\b|" + _MON + r"(?![a-z]))|"
    r"\b(?:this|next|coming|the\s+coming)\s+(?:spring|summer|fall|autumn|winter|year|quarter|month|months|weeks|"
    r"few\s+(?:weeks|months))\b|\b(?:spring|summer|fall|autumn|winter)\s+(?:of\s+)?(?:19|20)\d\d\b|\byear[\s-]end\b|"
    r"\bend\s+of\s+(?:the\s+)?(?:calendar\s+|fiscal\s+)?(?:year|quarter|month|(?:19|20)\d\d)\b|"
    r"\b(?:calendar|fiscal)\s+(?:year\s+)?(?:19|20)\d\d\b|\bshortly\b|\bin\s+the\s+new\s+year\b|"
    r"\bin\s+the\s+(?:coming|next)\s+(?:few\s+)?"
    r"(?:days|weeks|months)\b|\bwithin\s+(?:the\s+next\s+)?(?:\d+(?:\s*(?:-|\u2013|to)\s*\d+)?|[a-z]+(?:-[a-z]+)?)\s*(?:\(\d+\)\s*)?(?:calendar\s+|business\s+)?"
    r"(?:days|weeks|months)\b|\b(?:\d{1,2}|two|three|four|six|eight)\s*(?:to|-|\u2013)\s*(?:\d+|six|eight|four|twelve)\s+(?:weeks|months)\b")
# weak commissioning language: counts only with a timing in the same sentence
_V4_WEAK = re.compile(r"(?i)underway|in\s+progress|expected\s+to\s+be\s+(?:completed|delivered|released|published)|"
                      r"completion\s+of\s+(?:a|an|the|its)\b|due\s+for\s+completion|to\s+be\s+completed\s+(?:in|by|during|within|before)|"
                      r"\bplans?\s+to\b|\bintent(?:ion)?\s+to\b|\bexpected\s+(?:in|by)\b")
# a sentence about an environmental permit document (EIA, ESIA, EIS): its "technical reports" are not NI 43-101
_V4_ENV = re.compile(r"\bE?S?IA\b|\bEIS\b|\bEA\s+process|(?i:environmental\s+(?:and\s+social\s+)?impact|"
                     r"environmental\s+assessment|environmental\s+(?:permit|approval|authorit)|baseline\s+stud)")
# the thing nearing completion / underway is a programme, not a report
_V4_PROGRAM = re.compile(r"(?i)\b(?:drill\w*|program(?:me)?s?|campaign|survey|trench\w*|sampling|exploration|geotechnical|"
                         r"test\s*-?\s*work|testing|optimi[sz]ation|metallurg\w*|construction|commissioning|permitting|"
                         r"engineering\s+work|work\s+program|evaluation\s+of)\b")
_V4_RW = re.compile(r"(?i)technical\s+report|43\s*-?\s*101|\bPEA\b|\bPFS\b|\bDFS\b|\bBFS\b|feasibility|resource\s+estimat\w*|"
                    r"\bMRE\b|economic\s+assessment|mineral\s+resources?\b|resource\s+update|scoping\s+study|\bthe\s+report\b")
# a citation of an earlier report inside a filing sentence
_V4_CITE = re.compile(r"(?i)\b(?:report|study|assessment)\s*[\u201d\"]?\s*,?\s*(?:that|which)\s+(?:the\s+(?:company|corporation)|"
                      r"we|it|[A-Z][\w&\-]+)\s+(?:has\s+|had\s+|have\s+|previously\s+)?filed\b|\bfrom\s+which\s+[^.]{0,80}?"
                      r"(?:extracted|derived|taken|summari[sz]ed)|\breferred\s+to\s+(?:above|herein|in\s+this)|"
                      r"\b(?:is|are|was|were)\s+(?:detailed|described|summari[sz]ed|contained|set\s+out|presented|disclosed)\s+in\s+"
                      r"(?:a|the|its|our)\s+(?:[\w\-]+\s+){0,4}?(?:technical\s+)?report|\(\s*(?:see|refer)\b|"
                      r"\b(?:see|refer\s+to)\s+(?:the\s+)?(?:[\w\-]+\s+){0,3}?(?:technical\s+)?report\s+(?:titled|entitled|dated)")
_V4_REFILE = re.compile(r"(?i)\b(?:amended|revised|restated|re-?filed|re-?filing|re-?issu\w*|re-?addressed|updated|"
                        r"new(?=\s+(?:[\w\-]+\s+){0,3}?(?:technical|report|NI|43|PEA|PFS|feasibility|pre-?feasibility|mineral|resource|"
                        r"MRE|study|estimate)))\b")    # 1.0.5: "new" describes the report (not "Papua New Guinea")
# a filing verb and the end of its clause (the report must be what was filed)
_V4_FILEVERB = re.compile(r"(?i)\b(?:has|have)\s+(?:now\s+|today\s+|recently\s+)?(?:completed\s+and\s+)?(?:publicly\s+)?(?:re-?)?filed\b|"
                          r"\b(?:announces?|reports?|confirms?)\s+(?:today\s+)?(?:the\s+)?(?:sedar\+?\s+)?(?:re-?)?filing\b|"
                          r"\b(?:company|corporation)\s+(?:today\s+|recently\s+)?filed\b|\btoday\s+filed\b")
_V4_CLAUSE_END = re.compile(r",\s*and\b|;|\band\s+(?:is|are|has|have|will)\b")
# the issuer, a company, a firm: not a project
_V4_CORP_AFTER = re.compile(r"\s*,?\s*(?:\(\w+\)\s*)?(?:Corp(?:oration)?|Inc|Incorporated|Ltd|Limited|LLC|Pty|plc|PLC|S\.?A\.?|"
                            r"GmbH|AG|ULC|SAC|S\.A\.C)\b")
_V4_HEADVERB = re.compile(r"(?:Announce|Report|Provide|Select|Start|Complete|Commence|Receive|Acquire|File|Engage|Retain|"
                          r"Deliver|Advance|Begin|Launch|Update|Upgrade|Close|Expand|Intersect|Initiate|Appoint|Hire|Contract|"
                          r"Sign|Grant|Extend|Increase|Achieve|Accelerate|Award|Outline|Confirm|Unveil|Publish|Release|"
                          r"Redefine|Define)(?:s|d|ed|es)?")
_V4_JOIN = {"of", "the", "to", "for", "at", "on", "in", "and", "&", "a", "an", "its", "our", "with", "from", "by"}
# headline adjectives and nouns that open a phrase, not a name ("Robust Project Economics", "Summary of Key Results")
_V4_HEADADJ = {"Robust", "Positive", "Strong", "Significant", "Major", "Excellent", "Updated", "Maiden", "Initial",
               "Additional", "Improved", "Expanded", "Larger", "Higher", "Record", "Outstanding", "Encouraging",
               "Exceptional", "Optimized", "Optimised", "Enhanced", "Overall", "Summary", "Largest", "Premier",
               "Undeveloped", "Results", "Highlights", "Economics", "Economic", "Study", "Studies", "Estimate"}
# words that open real names although the release also writes them in lower case ("West Ridge", "New Hope")
_V4_PLACE = _TR_FIRST | {"central", "northern", "southern", "eastern", "western", "new", "old", "great", "high", "long",
                         "deep", "twin", "hidden", "lost", "blue", "green", "grey", "gray", "pine", "cedar", "bear", "eagle"}
_V4_SUF = re.compile(r"(?i)\s+(?:Projects?|Property|Properties|Mines?|Deposits?|Complex|Operations?|District|Zones?|Prospects?|"
                     r"Claims?|Concessions?)$")
_V4_COMMOD = re.compile(r"(?i)^(?:gold|silver|copper|zinc|lead|nickel|cobalt|lithium|uranium|graphite|potash|phosphate|vanadium|"
                        r"tungsten|antimony|molybdenum|manganese|iron|tin|titanium|polymetallic|porphyry|oxide|pge|pgm|ree|"
                        r"rare|earths?|critical|minerals?|metals?|base|precious|heap|leach|coal|brine|clay|flake|sulphide|"
                        r"sulfide|[a-z]{1,3}(?:-[a-z]{1,3}){1,4}|(?:gold|silver|copper|zinc|lead|nickel)(?:-(?:gold|silver|"
                        r"copper|zinc|lead|nickel|cobalt|pge))+)$")
# a current resource the report states ("indicates an inferred resource of ...", "43-101 resource estimation report")
_V4_RES_STATED = re.compile(r"(?i)\b(?:inferred|indicated|measured|M&I)\s+(?:mineral\s+)?resources?\s+(?:of|estimate|totall?ing|"
                            r"containing)\b|\bresource\s+estimation\s+report\b")
# short forms that name a study, a standard, a person or a firm, not a project ("PEA", "NI", "QP")
_V4_NOT_SF = re.compile(r"(?i)\b(?:assessment|study|studies|estimate|estimation|feasibility|economic|resources?|reserves?|"
                        r"instrument|standards?|person|persons|associates|consult\w*|engineering|services|corp\w*|inc|ltd|"
                        r"limited|company|group|exchange|agreement|plan|program(?:me)?|report|analysis|development|"
                        r"environmental|impact|net|present|value|internal|rate|return|life|cost)\b|"
                        r"^(?:PEA|PFS|FS|DFS|BFS|MRE|NI|QP|QPs|EIA|ESIA|EIS|IRR|NPV|AISC|LOM|TSX|TSXV|CSE|OTC|JV|MOU|LOI)$")
_V4_NAME_GENERIC = {"the", "gold", "silver", "copper", "mining", "mines", "metals", "minerals", "resources", "corp", "inc", "ltd",
                    "limited", "corporation", "company", "and", "of", "group", "capital", "energy", "exploration"}
# the issuer is a royalty or streaming company: so it calls itself ("... is a gold-focused royalty and streaming company")
_V4_ROYALTY = re.compile(r"(?i)\b(?:is|as)\s+(?:a|an|the)\s+(?:[\w\-&,]+\s+){0,6}?(?:royalty|streaming|royalty\s+(?:and|&)\s+"
                         r"streaming|streaming\s+(?:and|&)\s+royalty)\s+(?:company|corporation|business)\b")


def _v4_date_iso(s):
    """Every date in s as ISO, month-only dates as the 1st ('September 2016')."""
    out = [_iso(m) for m in _DATE.finditer(s)]
    for m in re.finditer(r"(?i)\b(" + _MON + r")\s*,?\s*((?:19|20)\d\d)\b", s):
        try:
            out.append("%04d-%02d-01" % (int(m.group(2)), _MONTHS[m.group(1)[:3].lower()]))
        except KeyError:
            pass
    return [d for d in out if d]


def _v4_months(a, b):
    """Months from ISO date a to ISO date b (b later -> positive)."""
    try:
        return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])
    except (TypeError, ValueError):
        return None


class _V4:
    """What the release says about itself: the issuer's words and aliases, other companies it names, the short forms
    it defines, its date."""

    def __init__(self, h, b, issuer):
        self.h, self.b, self.issuer = h, b, issuer
        # the release's date: its dateline, else the first date near the top
        self.rel = _dateline(b) or next((d for d in (_iso(m) for m in _DATE.finditer(b[:1500])) if d), None)
        lead = b[:1500]
        own = set(re.findall(r"[a-z0-9]+", _fold(issuer or "")))
        # the issuer when the reader's finder misses it: "Acme Mines' (TSX: ACM)", and the headline's subject
        # ("Acme Mines announces ...")
        m = re.search(r"([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,4})['\u2019]?s?\s*\(\s*(?:TSX|TSXV|TSX-V|NYSE|NASDAQ|Nasdaq|CSE|ASX|"
                      r"OTC|AIM|LSE|FSE)\b", lead)
        if m:
            own |= set(re.findall(r"[a-z0-9]+", _fold(m.group(1))))
        m = re.match(r"\W*([A-Z][\w&.\-\u2019']*(?:\s+[A-Z][\w&.\-\u2019']*){0,3})\s+(?i:announces?|reports?|files?|provides?|receives?|"
                     r"engages?|completes?|delivers?|releases?|commences?|outlines?|updates?|confirms?|begins?|launches?|"
                     r"closes?|acquires?|signs?|intersects?|drills?)\b", h)
        subject = set(re.findall(r"[a-z0-9]+", _fold(m.group(1)))) if m and not _TRW.search(m.group(1)) else set()
        own |= subject
        # a royalty or streaming company: its name says so (the name the release defines as "the Company", else the
        # issuer the finder read, else the headline's subject), or it describes itself so ("XYZ is a
        # gold-focused royalty and streaming company"); its release recaps its operators' studies
        m = re.search(r"([A-Z][\w&.\-\u2019']*(?:\s+(?:[A-Z][\w&.\-\u2019']*|&|and|de)){0,5})\s*,?\s*(?:\([^()]{0,60}\)\s*)*"
                      r"\([^()]{0,60}?[\u201c\"]\s*(?:the\s+)?(?:Company|Corporation|Issuer)\s*[\u201d\"]", lead)
        name = set(re.findall(r"[a-z0-9]+", _fold(m.group(1)))) if m else set()
        if m:
            own |= name
        name = name or (set(re.findall(r"[a-z0-9]+", _fold(issuer or ""))) if issuer else subject)
        self.royalty = any(w.startswith(("royalt", "stream")) for w in name) or any(
            (name - _V4_NAME_GENERIC) & set(re.findall(r"[a-z0-9]+", _fold(" ".join(lead[:d.start()].split()[-4:]))))
            for d in _V4_ROYALTY.finditer(lead))
        at = lead.find(issuer) + len(issuer) if issuer and issuer in lead else -1
        for m in re.finditer(r"\(\s*(?:the\s+)?[\u201c\"]\s*([^\u201d\"]{2,30}?)\s*[\u201d\"]\s*(?:,|or|\))([^)]{0,40})", lead):
            # the issuer's own short names: given right after it, or with "the Company"
            if (0 <= m.start() - at <= 120 or re.search(r"(?i)company|corporation|issuer", m.group(2))) and \
                    not re.search(r"(?i)\b(?:project|property|mine|deposit|report|study)\b", m.group(1)):
                own |= set(re.findall(r"[a-z0-9]+", _fold(m.group(1))))
        self.own = own - {"the", "company", "corporation", "inc", "corp", "ltd", "limited", "mining", "mines", "resources",
                          "gold", "silver", "metals", "minerals", "and", "of", "exploration", "ventures", "energy",
                          "copper", "lithium", "uranium", "nickel", "group"}
        self._others = self._sf = self._wc = None
        self._fixed, self._names = {}, {}

    @property
    def others(self):
        """Other companies the release names with a corporate form, and the aliases it gives them."""
        if self._others is None:
            self._others = self._other_companies()
        return self._others

    @property
    def sf(self):
        if self._sf is None:
            self._sf = self._short_forms(self.h + " . " + self.b)
        return self._sf

    def _other_companies(self):
        b, out = self.b, set()
        for m in re.finditer(r"([A-Z][\w&.\-\u2019']*(?:\s+[A-Z][\w&.\-\u2019']*){0,4})\s*,?\s+(?:Corp(?:oration)?|Inc|Ltd|Limited|LLC|"
                             r"plc|S\.A)\.?\s*(?:\([^)\u201c\u201d\"]{0,40}\)\s*)*(?:\(\s*(?:the\s+)?[\u201c\"]([^\u201d\"]{2,25})[\u201d\"])?", b):
            words = set(re.findall(r"[a-z0-9]+", _fold(m.group(1)))) - {"the", "and", "of"}
            first = m.group(1).split()[0]
            if not words or words & self.own or first in ("The", "This", "Our", "Its", "A", "An") or _firms_in(m.group(0)):
                continue
            if len(first) >= 3:
                out.add(first)
            if m.group(2):
                out.add(m.group(2).split()[0])
        return out

    @staticmethod
    def _short_forms(t):
        """{"NRW": ("North Ridge West", "Project")}: a short form the release defines in brackets for a longer name
        whose words' initials spell it ('North Ridge West Project ("NRW" or the "Project")', 'Las Palmas Sur
        ("LPS") Project', 'Rio y Monte (RyM) gold-silver project', 'Lake Kira project ("LK Project")')."""
        out = {}
        for m in re.finditer(r"\(\s*(?:the\s+)?[\u201c\"]?\s*([A-Z][A-Za-z0-9&]{1,6})(?:\s+(Project|Property|Mine|Deposit|project|"
                             r"property))?\s*[\u201d\"]?\s*(?:(?:,|or|and)\s*[^)]{0,40})?\)", t):
            sf = m.group(1)
            if sum(1 for c in sf if c.isupper()) < 2 or sf in out or _V4_NOT_SF.fullmatch(sf):
                continue
            toks = re.findall(r"[^\s(),;:\u201c\u201d\"]+", t[max(0, m.start() - 160):m.start()])
            suffix = m.group(2)
            nxt = re.match(r"\s*(?:[\w\-]+\s+){0,2}?(Project|Property|Mine|Deposit|project|property|mine)\b", t[m.end():m.end() + 40])
            if nxt:
                suffix = suffix or nxt.group(1)
            if not suffix and not re.search(r"(?<![\w\-])" + re.escape(sf) + r"\s+(?:[\w\-]+\s+)?(?:Project|Property|Mine|project|"
                                            r"property|mine)\b", t):
                # a short form for a project is written as one somewhere ("the NRW project"); "PEA", "MRE", "QP" are not
                if not any(_V4_SUF.match(" " + x) for x in toks[-3:]):
                    continue
            found = None
            for skip in range(0, 5):
                end = len(toks) - skip
                if end <= 0:
                    break
                tail = toks[end:]
                if tail and not all(_V4_SUF.match(" " + x) or _V4_COMMOD.match(x.lower()) or re.match(r"^[A-Z]$", x)
                                    for x in tail):
                    break
                for k in range(len(sf), len(sf) + 3):
                    win = toks[max(0, end - k):end]
                    if len(win) < 2 or not win[0][:1].isupper() or re.search(r"['\u2019]s$", win[0]):
                        continue
                    ini = "".join(p[:1] for w in win for p in re.split(r"[/\-]", w) if p)
                    ini2 = "".join(w[:1] for w in win)
                    if sf.lower() in (ini.lower(), ini2.lower()):
                        found = (" ".join(win), suffix or next((x for x in tail if _V4_SUF.match(" " + x)), None))
                        break
                if found:
                    break
            if found and not _V4_NOT_SF.search(found[0]) and not _V4_NOT_SF.fullmatch(sf):
                out[sf] = (found[0], (found[1] or "Project").title())
        return out

    def own_timed(self, s):
        """A sentence in the About paragraph that counts: the issuer's own study with a timing ('... the Company ... is
        commencing the preparation of an updated PEA that is expected in early 2026'), not a reference note or footnote
        ('Northwind News Release dated May 24, 2023 (Technical Report to be filed within 45 days)', '*Please see ...')."""
        if not _v4_timed(s, self.rel) or re.search(r"(?i)\bnews\s+release\s+(?:dated|issued|of)\b|\bplease\s+see\b|"
                                                    r"\bsee\s+(?:the\s+)?footnote|(?:^|\s)\*", s):
            return False      # a reference note or footnote (it runs into the sentence and brings its report's type)
        s = re.sub(r"\s+About\s+[A-Z].*$", "", s)        # the next heading, run into the sentence
        return bool(re.search(r"(?i)\bthe\s+(?:Company|Corporation)\b|\b(?:we|our)\b", s) or
                    set(re.findall(r"[a-z0-9]+", _fold(s))) & self.own)

    def is_other(self, s):
        """The sentence reports another company's study or filing: its subject is a company the release names that is
        not the issuer ('Northwind announced the filing of ...', '(\u201cPartner\u201d) (TSXV: PTR), disclosed a new PEA'), or the
        study is to be completed or filed by that company."""
        if not self.own:
            return False
        m = re.match(r"\W*\(\s*[\u201c\"]([^\u201d\"]{2,25})[\u201d\"]\s*\)\s*(?:\([^)]{0,60}\)\s*)*,?\s+(?:has\s+|had\s+|recently\s+)*"
                     r"(?:announced|disclosed|filed|released|published|reported)\b", s)
        if m and not set(re.findall(r"[a-z0-9]+", _fold(m.group(1)))) & self.own:
            return True                  # '("Partner") (TSXV: PTR), disclosed a new PEA' (the name ended the sentence before)
        for m in re.finditer(r"(?:^|[.;:]\s+|,\s+)((?:[A-Z][\w&\u2019'\-]*\.?)(?:\s+(?:[A-Z][\w&\u2019'\-]*\.?|&)){0,4})\s*"
                             r"(?:\([^)]{0,60}\)\s*)*,?\s+(?:has\s+|had\s+|have\s+|recently\s+|today\s+|also\s+)*"
                             r"(announced|announces|disclosed|discloses|filed|files|appointed|appoints|engaged|engages|"
                             r"retained|retains|commissioned|released|releases|published|publishes|is\s+(?:currently\s+)?"
                             r"preparing|completed|plans|expects)\b", s):
            subj = m.group(1)
            ws = set(re.findall(r"[a-z0-9]+", _fold(subj)))
            if not ws or ws & self.own or subj.split()[0] in ("The", "This", "It", "We", "Our", "Management", "Company",
                                                              "Corporation", "Board", "On", "In", "As", "Mr.", "Mr", "Ms.",
                                                              "Dr.", "Dr", "CEO", "President", "Each", "All", "Both", "Its"):
                continue
            if _firms_in(subj) or re.match(r"(?:" + _KNOWN + r")\b", subj):
                continue
            corpish = subj.split()[0] in self.others or re.search(r"(?i)\b(?:mining|mines|gold|resources|metals|minerals|"
                                                                   r"royalt\w*|corp\w*|inc|ltd|limited)\b", subj)
            if corpish or not re.match(r"(?i)is\s|completed|plans|expects", m.group(2)):
                return True
        for m in re.finditer(r"(?i)\b(?:completed|prepared|conducted|filed|carried\s+out|funded)\s+by\s+([A-Z][\w&\u2019'\-]*)", s):
            if m.group(1) in self.others:
                return True
        for m in re.finditer(r"\b(?:under|on)\s+([A-Z][\w&\u2019'\-]*)(?:\s+[A-Z][\w&\u2019'\-]*){0,3}['\u2019]s\s+(?:SEDAR|corporate|issuer|profile)", s):
            if not set(re.findall(r"[a-z0-9]+", _fold(m.group(1)))) & self.own:
                return True
        return False

    # -------------------------------------------------------------- names
    def _phrase_word(self, w):
        """The release writes w as an ordinary lower-case word more than as a name ('Target Project', 'Two New
        Properties', 'Key Growth Projects', 'Ownership of ...')."""
        if len(w) < 3:
            return False
        wc = self._counts()
        low, up = wc[w.lower()], wc[w[:1].upper() + w[1:].lower()]
        return low >= 1 and (low > up or (low >= 2 and up <= 2))

    def _counts(self):
        """How often the release writes each word, as written (case kept)."""
        if self._wc is None:
            from collections import Counter
            self._wc = Counter(x[:-2] if x.endswith(("'s", "\u2019s")) else x
                               for x in re.findall(r"[\w'\u2019\-]+", self.h + " " + self.b))
        return self._wc

    def fix_name(self, p):
        """A project name the page can show: the full name for a defined short form ('NRW Project' -> 'North Ridge
        West Project (NRW)'); no headline fragment ('Target Project', 'Selects Mine', 'Ownership of X Project' ->
        'X Project'); not the issuer or a firm; not an activity the release calls a project ('the carbon-in-leach
        circuit (the "CIL Project")'); a deposit becomes the project that holds it when the release says so. None when
        nothing is left."""
        if not p:
            return p
        if p not in self._fixed:
            self._fixed[p] = self._fix_name(p)
        return self._fixed[p]

    def _fix_name(self, p):
        p = re.sub(r"\s+", " ", p).strip()
        ms = _V4_SUF.search(p)
        suffix = p[ms.start():].strip() if ms else ""
        core = p[:ms.start()] if ms else p
        ws = core.split()
        # a headline fragment: leading headline verbs and adjectives, joining words and ordinary words go
        cut = False
        while ws and (_V4_HEADVERB.fullmatch(ws[0]) or ws[0] in _V4_HEADADJ or ws[0].lower() in _V4_JOIN or
                      (not _V4_COMMOD.match(ws[0].lower()) and _fold(ws[0]) not in _V4_PLACE and self._phrase_word(ws[0]))):
            cut = cut or not (_V4_HEADVERB.fullmatch(ws[0]) or ws[0].lower() in _V4_JOIN)
            ws = ws[1:]
        dist = [w for w in ws if not _V4_COMMOD.match(w.lower())]
        if not dist or all(_fold(w) in _V4_PLACE and self._phrase_word(w) for w in dist):
            return None
        if cut and self._counts()[dist[0].lower()]:
            return None      # what is left of a phrase is still an ordinary word ("Block Cave" -> "Cave")
        core = " ".join(ws)
        # a defined short form -> the full name, the short form kept in brackets
        k = re.sub(r"[\u201c\u201d\"()]", "", dist[0])
        if len(dist) == 1 and k in self.sf:
            long, suf = self.sf[k]
            if _V4_SUF.search(" " + long):
                return "%s (%s)" % (long, k)
            return "%s %s (%s)" % (long, suf, k)
        # the issuer ('Acme Mines'), or a firm / company the release writes with a company form ('Omni Projects SA')
        cw = set(re.findall(r"[a-z0-9]+", _fold(core))) - {"mines", "mining", "gold", "silver", "resources"}
        if cw and cw <= self.own and suffix.lower() in ("", "mines", "mining"):
            return None
        if cw & self.own and suffix.lower() in ("projects", "properties"):
            return None      # 1.0.5: the issuer's portfolio ("All Four Acme Projects"), not one project
        if self._descriptive((core + " " + suffix).strip()):
            return None      # 1.0.5: a sub-headline phrase ("... Remains a Stand-Out Oxide Silver-Gold Development Project")
        if suffix.lower() in ("mines", "mining") and \
                re.search(r"(?<![\w\-])" + re.escape(core + " " + suffix) + _V4_CORP_AFTER.pattern, self.h + " " + self.b):
            return None      # "Acme Mines" is "Acme Mines Ltd."
        t = self.h + " " + self.b
        seen = [m.end() for m in re.finditer(r"(?<![\w\-])" + re.escape((core + " " + suffix).strip()) + r"(?![\w\-])", t)]
        if seen and all(_V4_CORP_AFTER.match(t, i) for i in seen):
            return None      # every time the release writes it, it is a company ("Omni Projects SA (Proprietary) Limited")
        # an activity the release defines as a "project" ('... leach circuit (the "CIL Project")')
        m = re.search(r"([a-z][a-z\-]+\s+[a-z][a-z\-]+)\s*\(\s*(?:the\s+)?[\u201c\"]\s*" + re.escape(core) + r"\s+Project\s*[\u201d\"]\s*\)",
                      self.b, re.I)
        if m and m.group(1)[:1].islower() and m.group(1).split()[-1].islower() and \
                not re.search(r"(?i)(?<![\w\-])" + re.escape(core) + r"(?![\w\-])", self.b[max(0, m.start() - 60):m.end(1)]):
            return None
        name = (core + " " + suffix).strip()
        # a deposit (or zone) inside a project the release names: '<X> deposit(s) at/on/of the <Y> Project'
        if re.search(r"(?i)\b(?:Deposits?|Zones?)$", name):
            m = re.search(r"(?i)" + re.escape(core) + r"\s+(?:[\w\-]+\s+){0,2}?(?:deposits?|zones?)\s*,?\s+(?:at|on|of|within|"
                          r"in|part\s+of)\s+(?:the\s+|our\s+|its\s+|the\s+company['\u2019]s\s+)?((?:[A-Z][\w'\u00c0-\u00ff\-]*)(?:\s+(?:[A-Z]"
                          r"[\w'\u00c0-\u00ff\-]*|de|la|y|del)){0,4})\s+(Project|Property|Mine|project|property|mine)\b", self.b)
            if m and not re.search(r"(?i)\b(?:deposits?|zones?)\b", m.group(1)):
                return m.group(1) + " " + m.group(2).title()
            m = re.search(r"\b" + re.escape(core) + r"\s+(?:[\w\-]+\s+)?(Project|Property|Mine)\b", self.h + " " + self.b)
            if m:
                return core + " " + m.group(1)
        if re.search(r"(?i)\b(?:Mines?|Deposits?|Zones?)$", name):
            # 1.0.5: a mine inside the project the release names around it ('the Mohave Project ..., including the
            # past-producing Rosebud Mine')
            m = re.search(r"((?:[A-Z][\w'\u00c0-\u00ff\-]*)(?:\s+(?:[A-Z][\w'\u00c0-\u00ff\-]*|de|la|y|del)){0,4})\s+(Project|Property)"
                          r"\b[^.;]{0,80}?\binclud(?:ing|es)\s+(?:the\s+)?(?:[\w\-,%]+\s+){0,5}?" + re.escape(core) + r"\b", self.b)
            if m and not re.search(r"(?i)\b(?:mines?|deposits?|zones?)\b", m.group(1)):
                q = self.fix_name(m.group(1) + " " + m.group(2))
                if q:
                    return q
        return name

    def _descriptive(self, name):
        """1.0.5: every time the release writes the name, an indefinite article opens it ("Diablillos Remains a
        Stand-Out Oxide Silver-Gold Development Project"): a description, not a name."""
        t = self.h + " . " + self.b
        pre = [t[max(0, m.start() - 4):m.start()] for m in re.finditer(r"(?<![\w\-])" + re.escape(name) + r"(?![\w\-])", t)]
        return bool(pre) and all(re.search(r"(?i)\ban?\s+$", x) for x in pre)

    def names_in(self, s, bare=True):
        """The projects sentence s names (helper finder, then, when bare, short forms written alone), repaired."""
        if (s, bare) not in self._names:
            self._names[(s, bare)] = self._names_in(s, bare)
        return list(self._names[(s, bare)])

    def _names_in(self, s, bare):
        out = []
        for _i, p in _pn_in(s, self.issuer):
            q = self.fix_name(p)
            if q and q not in out:
                out.append(q)
        for sf in (self.sf if bare else ()):
            if re.search(r"(?<![\w\-])" + re.escape(sf) + r"(?![\w\-])", s) and not any("(%s)" % sf in q for q in out):
                q = self.fix_name(sf + " " + self.sf[sf][1])
                if q and q not in out:
                    out.append(q)
        for m in re.finditer(r"\b((?:[A-Z][\w'\u00c0-\u00ff\-]*)(?:\s+[A-Z][\w'\u00c0-\u00ff\-]*){0,3})\s+(Operations?|District|Complex)\b", s):
            q = PN.clean(m.group(1), m.group(2))
            q = self.fix_name(q) if q else None
            if q and q not in out and not any(PN.same(q, o) for o in out):
                out.append(q)
        return out


def _v4_same(a, b):
    """Two names for one project (the helper's test: one name's key words inside the other's)."""
    return bool(a and b and PN.same(a, b))


def _v4_in(p, s):
    """The name's distinctive words all appear in s."""
    ws = [w for w in PN.key(p).split() if len(w) > 1]
    fs = _fold(s)
    return bool(ws) and all(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", fs) for w in ws)


def _v4_weak_only(s):
    """All the commissioning language in s is weak (underway, in progress, expected to be completed, plans to)."""
    ms = [m.group(0) for m in _COMM.finditer(s)]
    return bool(ms) and all(_V4_WEAK.search(x) for x in ms) and not _WILL_FILE.search(s)


def _v4_timed(s, rel=None):
    """The sentence states a timing that is not in a year before the release ('in November 2015' dates an earlier
    study, not this one)."""
    y = int(rel[:4]) if rel else None
    for m in _V4_TIMING.finditer(s):
        ys = [int(v) for v in re.findall(r"(?:19|20)\d\d", s[m.start():m.end() + 8])]
        if not (y and ys and max(ys) < y):
            return True
    return False


def _v4_cue_ok(s, rel=None):
    """A commissioning sentence counts only when it is about a report: not an environmental (EIA/ESIA) document; weak
    language needs a timing; and what is 'nearing completion' / 'underway' / 'expected' is the report, not a programme
    ('the geotechnical program ... is nearing completion', 'mining of the Oxide mineral resource nearing completion')."""
    if _V4_ENV.search(s) or not _V4_RW.search(s):
        return False
    if _v4_weak_only(s) and not _v4_timed(s, rel):
        return False
    weak = list(re.finditer(r"(?i)\bnear(?:ing|s)?\s+completion|underway|in\s+progress|expected\s+to\s+be\s+(?:completed|"
                            r"delivered|released|published)", s))

    def programme(m):
        last = " ".join(s[max(0, m.start() - 90):m.start()].split()[-7:])
        return bool(_V4_PROGRAM.search(last) and not _V4_RW.search(last) or
                    re.search(r"(?i)\b(?:mining|drilling|processing|production|construction|work|program(?:me)?|campaign)\s+"
                              r"(?:of|on|at|for|within)\b", last))
    strong = _WILL_FILE.search(s) or [x for x in _COMM.finditer(s)
                                      if not re.search(r"(?i)near|underway|in\s+progress|expected", x.group(0))]
    return bool(strong or not weak or not all(programme(m) for m in weak))


def _v4_near(s, span=90):
    """_near measured between the spans: the report word within span characters of the cue's end or start (every
    sentence _near(_COMM, _TRW2, s, 70) accepts, and a report word after a long cue: 'engagement of <firm> to prepare
    an independent NI 43-101 estimate')."""
    rw = [(m.start(), m.end()) for m in _TRW2.finditer(s)]
    if not rw:
        return False
    for m in _COMM.finditer(s):
        for a, b in rw:
            if a <= m.end() + span and b >= m.start() - span:
                return True
    return False


def _v4_old_cited(s, rel, h):
    """A filing sentence about an earlier report: a citation form, or the report's date or effective date is over a
    year before the release (and nothing says it is amended, re-filed or new)."""
    for m in _V4_CITE.finditer(s):
        if not (re.match(r"(?i)report", m.group(0)) and re.search(r"(?i)\b(?:to|we|and)\s+$", s[max(0, m.start() - 12):m.start()])):
            return True    # 1.0.5 (full text): "is pleased to report that it has filed ..." is the news, not a citation
    if not rel or _V4_REFILE.search(s + " " + h):
        return False
    for m in re.finditer(r"(?i)\b(?:dated|effective\s+(?:date\s+)?(?:of|as\s+of|is|was)?|effective)\s*:?\s*", s):
        for d in _v4_date_iso(s[m.end():m.end() + 30])[:1]:
            gap = _v4_months(d, rel)
            if gap is not None and (gap > 12 or gap == 12 and _v5_days(d, rel) > 365):   # 1.0.5: to the day
                return True
    for m in re.finditer(r"(?i)\bfiled\b[^.;]{0,120}?\b(?:on|in)\s+(" + _MON + r"\s*(?:\d{1,2}\s*,?\s*)?(?:19|20)\d\d|(?:19|20)\d\d)\b", s):
        d = _v4_date_iso(m.group(1)) or ["%s-01-01" % m.group(1)[-4:]]
        gap = _v4_months(d[0], rel)
        if gap is not None and gap > 2:
            return True
    return False


def _v4_files_report(s):
    """The filing verb's object is a report (in the same clause): 'has filed a title opinion ..., and is preparing a
    43-101 report' files something else."""
    ms = list(_V4_FILEVERB.finditer(s))
    if not ms:
        return True
    for m in ms:
        tail = s[m.end():m.end() + 200]
        cut = _V4_CLAUSE_END.search(tail)
        if _TRW.search(tail[:cut.start()] if cut else tail) or _TRW.search(s[max(0, m.start() - 160):m.start()]):
            return True
    return False


def _v4_hl_comm(h):
    """The headline itself says a report is in hand: commissioning language, or 'completes' / 'receives' with the
    report as its object (not 'Completes Acquisition ... with Robust PEA Economics')."""
    if _NEG.search(h) or not _TRW.search(h):
        return False
    if _COMM.search(h) and not (_v4_weak_only(h) and not _V4_TIMING.search(h)):
        return True
    rep = r"(?:technical\s+reports?|NI\s*43-?101|43-?101|PEA|PFS|DFS|feasibility\s+study|pre-?feasibility|resource\s+estimate|MRE|" \
          r"economic\s+assessment|preliminary\s+economic)"
    return bool(re.search(r"(?i)\b(?:engages?|engaged|retains?|retained|commissions?|intent|commences?\s+preparation|nearing\s+"
                          r"completion|to\s+issue|awards?)\b", h)) or \
        bool(re.search(r"(?i)\b(?:complet(?:es|ed|ion)|receives?|receipt)\s+(?:of\s+)?(?:the\s+|an?\s+|its\s+)?(?:[\w\-]+\s+){0,4}?"
                       + rep, h)) or \
        bool(re.search(r"(?i)" + rep + r"[^,;:]{0,60}?\b(?:(?:has|have)\s+(?:now\s+)?been\s+completed|(?:is|are)\s+(?:now\s+)?complete)\b",
                       h)) or _v6_hl_comm(h)


# 1.0.5 (full text): headline forms of a report in hand -- "Commences Updated NI 43-101 Technical Report for X", "Completes
# Site Visit & Technical Report on X", "NI 43-101 Technical Report Completed on X", "Technical Report due for completion in
# January", "to Amend Technical Report on X", "Reports Updated Technical Report ..., Delivering ... NPV"
_V6_RES_IN = re.compile(r"(?i)\b(?:technical\s+)?reports?\s+(?:discloses?|includes?|contains?|presents?|outlines?|sets?\s+out|supports?)\s+"
                        r"(?:an?\s+|the\s+)?(?:company'?s\s+|corporation'?s\s+)?(?:updated\s+|maiden\s+|initial\s+|first\s+|current\s+)?"
                        r"(?:mineral\s+)?(?:resource|reserve)(?:\s+estimate)?s?\b")
_V6_HL_NEW = (r"\b(?:reports?|announces?|releases?|delivers?|unveils?|publishes?)\s+(?:the\s+)?(?:results\s+of\s+)?"
              r"(?:an?\s+|its\s+)?(?:updated|new|amended)\s+(?:NI\s*43\s*-?\s*101\s+)?technical\s+report\b")
_V6_REP = r"(?:technical\s+reports?|NI\s*43\s*-?\s*101(?:\s+(?:compliant\s+)?(?:technical\s+)?report)?|43\s*-?\s*101\s+report)"
_V6_HL = re.compile(r"(?i)\b(?:commenc(?:es|ed|ing|ement\s+of)|begins?|initiates?|starts?|launch(?:es)?|to\s+amend|amends?|"
                    r"complet(?:es|ed|ion\s+of))\s+(?:work\s+on\s+)?(?:the\s+|an?\s+|its\s+)?(?:[\w\-]+\s+(?:&\s+|and\s+)?){0,4}?"
                    + _V6_REP + r"|\b" + _V6_REP + r"\s+(?:(?:has|have)\s+(?:now\s+)?been\s+|(?:is|was)\s+(?:now\s+)?)?(?:completed|due\s+for\s+"
                    r"completion|commenced)\b|" + _V6_HL_NEW)


def _v6_hl_comm(h):
    return bool(_V6_HL.search(h))


# ------------------------------------------------------------------ 1.0.5: the release's own report, on its own project
# tasks that are not writing a report
_V5_OTHER_WORK = re.compile(r"(?i)(?:optimi[sz]e|facilitate|assist|support|oversee|manage|advise|represent|review|audit|design|"
                            r"explore|drill|test|operate|build|construct|negotiate|raise|identify|evaluate\s+opportunit)\w*$")
_V5_ENGAGE = re.compile(r"(?i)\b(?:engag|retain|commission|appoint|contract|hire)\w*")
# a report document, not only an estimate: the technical report, its filing, the 45-day rule, an engaged author
_V5_DOC = re.compile(r"(?i)technical\s+report|43\s*-?\s*101|\bfil(?:e|ed|es|ing)\b|SEDAR|\b(?:45|forty-?five)\b[^.]{0,12}days|"
                     r"\b(?:engag|retain|commission|hire|contract|appoint)\w*")
_V5_EST_ONLY = re.compile(r"(?i)^(?:(?:mineral\s+)?resources?(?:\s+(?:estimat\w*|update|statement))?|MRE|resource\s+estimat\w*|"
                          r"mineral\s+resources?\s+estimat\w*)$")
# an estimate with no report in view is not a report row, as the round-4 admission rule (R8) says (labels disagree;
# Justin's ruling pending: False writes those rows again)
_V5_ESTIMATE_NEEDS_REPORT = True
# the opening of a clause: where its subject is
_V5_CLAUSE = re.compile(r"(?:^|;\s+|:\s+|,\s+(?:and|while|but)\s+(?=(?:[Tt]he|[Aa]n?|[Ii]ts|[Oo]ur|[Tt]his|[Tt]hese|[Ww]e|"
                        r"[A-Z][\w\-]+)\s)|\.\s+|\b(?i:at\s+which\s+(?:time|point)|after\s+which|following\s+which|when|once|"
                        r"whereupon)\s+)")


def _v5_days(a, b):
    """Days from ISO date a to ISO date b (0 when either is unreadable)."""
    import datetime as _dt
    try:
        return (_dt.date.fromisoformat(b) - _dt.date.fromisoformat(a)).days
    except (TypeError, ValueError):
        return 0


def _v5_purpose_ok(t, at):
    """The engagement at position `at` is for a report: what the firm is engaged to do (its first to-verb, not "to
    announce") is not other work -- a task that is not writing ("to optimize the flotation design ... in order to produce
    concentrates", "as Interim Consultant to Facilitate ... Feasibility Study Engineering") or a programme or task named
    before any report ("to complete an optimization of the mine plan ... in advance of developing the PFS") -- and a report
    is its object ("to conduct an independent assessment of the project and prepare a feasibility-level NI 43-101
    technical report", "to model, estimate and report an updated MRE"). With no to-verb ("engages X for the PEA") it is."""
    tail = t[at:at + 240]
    head = re.split(r"(?i)\bto\s+[a-z]+\b|(?<=[a-z0-9)])\.\s", tail)[0][:90]
    if _V4_RW.search(head) and not _V4_PROGRAM.search(head[:_V4_RW.search(head).start()]):
        return True       # the report is what is engaged ("Commissions Update of the PEA to Reflect ...", "Retains X for its MRE")
    for m in re.finditer(r"(?i)\bto\s+(?:(?:immediately|now|further|independently|jointly|also)\s+)?(?!(?:the|a|an|its|their|our|this|that|"
                         r"these|those|be|date|which|whom|it|them|him|her|us)\b)([a-z]+)\b", tail):
        if re.match(r"(?i)(?:announce|report|provide|inform|advise|confirm|update)$", m.group(1)) and \
                re.match(r"(?i)\s+(?:that|on|the\s+(?:market|shareholders))\b", tail[m.end():]):
            continue      # "is pleased to announce that ..."
        if _V5_OTHER_WORK.match(m.group(1)):
            return False
        obj = re.split(r"(?<=[a-z0-9)])\.\s", tail[m.end():m.end() + 160])[0]      # its object, to the end of the sentence
        rw, pg = _V4_RW.search(obj), _V4_PROGRAM.search(obj)
        return bool(rw) and not (pg and pg.start() < rw.start())
    return True


def _v5_engage_ok(s):
    """A sentence whose only commissioning language is an engagement counts when one engagement is for a report."""
    ms = list(_COMM.finditer(s))
    eng = [m for m in ms if _V5_ENGAGE.match(m.group(0))]
    if not eng or len(eng) < len(ms) or _WILL_FILE.search(s):
        return True
    return any(_v5_purpose_ok(s, m.start()) for m in eng)


def _v5_hl_comm(h):
    """_v4_hl_comm, with an engagement for other work taken out of the headline first."""
    for m in list(_V5_ENGAGE.finditer(h))[::-1]:
        if not _v5_purpose_ok(h, m.start()):
            h = h[:m.start()] + "with" + h[m.end():]
    return _v4_hl_comm(h)


def _v5_subject_ok(s):
    """What is underway / nearing completion / in progress / expected is the report, not a programme: the subject of the
    clause ('The geotechnical program at the pit to ... convert mineral resources to reserves is also nearing completion',
    'Drilling to support the upcoming mineral resource estimate is nearing completion'), the thing before ', which is' or
    a bare 'expected to be' ('the Marimaca Feasibility Study, which is underway', 'a pre-feasibility study expected to be
    released in Q4'), the object of 'nearing completion of'. Only when all the commissioning language is weak."""
    weak = list(re.finditer(r"(?i)\bnear(?:ing|s)?\s+completion|underway|in\s+progress|expected\s+to\s+be\s+(?:completed|"
                            r"delivered|released|published)", s))
    if not weak or _WILL_FILE.search(s) or [x for x in _COMM.finditer(s)
                                            if not re.search(r"(?i)near|underway|in\s+progress|expected", x.group(0))]:
        return True
    for m in weak:
        pre = s[:m.start()]
        rel_ = re.search(r"(?i)(?:,|\b(?:which|that))\s*(?:(?:which|that)\s+)?(?:(?:is|are)\s+)?(?:currently\s+|now\s+|also\s+)?$", pre)
        if re.match(r"(?i)\s+of\b", s[m.end():]):
            first = " ".join(s[m.end():].split()[1:7])          # "nearing completion of <what>"
        elif rel_:
            first = " ".join(pre[:rel_.start()].split()[-6:])    # "<what>, which is underway", "<what>, expected to be ..."
        elif m.group(0)[:8].lower() == "expected" and not re.search(r"(?i)\b(?:is|are|was|were|be|been)\s+(?:also\s+|now\s+|"
                                                                       r"currently\s+)?$", pre):
            first = " ".join(pre.split()[-6:])                  # "<what> expected to be released in Q4"
        else:
            starts = [c.end() for c in _V5_CLAUSE.finditer(s, 0, m.start())]
            head = s[starts[-1] if starts else 0:m.start()]     # the clause's subject
            head = re.sub(r"(?i)^(?:the\s+|in\s+addition,?\s+|additionally,?\s+|also,?\s+|further(?:more)?,?\s+)+", "", head)
            first = " ".join(head.split()[:5])
        if not (_V4_PROGRAM.search(first) and not _V4_RW.search(first)):
            return True
    return False


def _v5_stale(s, rel):
    """A commissioning sentence about a report it dates more than a year before the release: a sentence carried over
    from an earlier release or a reference note ('the MDA Technical Report dated January 24, 2020 will be filed on
    SEDAR' in a May 2021 release). Not when it says the report is amended, re-filed, updated or new."""
    if not rel or _V4_REFILE.search(s):
        return False
    for m in re.finditer(r"(?i)\b(?:report|study|assessment|estimate)\s*[\u201d\"]?\s*,?\s*(?:\([^)]{0,40}\)\s*)?(?:is\s+)?(?:dated|with\s+an\s+"
                         r"effective\s+date\s+of|effective\s+(?:as\s+(?:of|at)\s+)?)\s*", s):
        d = _date_at(s, m.end(), 6)
        if d and _v5_days(d, rel) > 365:
            return True
    return False


_V5_TYPE_RX = {"FS": _T_FS, "PFS": _T_PFS, "PEA": _T_PEA, "resource": _T_RES}


def _v5_history(s, b, rel, old):
    """An engagement told as history: 'K92 engaged Mincore to complete the PEA for the expansion ...' with no timing, in
    a release that cites a titled report covering that study dated or effective over a year before the release (the
    report that engagement produced). `old` caches the old titles' texts."""
    if not rel or _v4_timed(s, rel) or not [m for m in _COMM.finditer(s) if _V5_ENGAGE.match(m.group(0))] or \
            re.search(r"(?i)\b(?:will|is\s+(?:now\s+)?preparing|are\s+(?:now\s+)?preparing|underway|in\s+progress|has\s+"
                      r"(?:now\s+)?(?:engaged|retained|commissioned)|have\s+(?:now\s+)?(?:engaged|retained|commissioned)|"
                      r"to\s+be\s+(?:completed|filed|prepared))\b", s):
        return False
    t = _type_of(s)
    if not t or re.search(r"(?i)\b(?:updated?|new|maiden|initial|inaugural|first|current)\b", s):
        return False      # a new or updated study is this release's, whatever an older report covered
    if old.get("titles") is None:
        got = []
        for i, q in _all_titles(b):
            ds = _v4_date_iso(b[i:i + len(q) + 250])
            if ds and all(_v5_days(d, rel) > 365 for d in ds[:2]):
                got.append(q)
        old["titles"] = got
    return any(_V5_TYPE_RX[t].search(q) for q in old["titles"])


_V5_TW = {"FS": r"(?:FS|DFS|BFS|(?<!pre-)(?<!pre)(?<!pre\s)feasibility\s+study)", "PFS": r"(?:PFS|pre-?\s?feasibility(?:\s+study)?)",
          "PEA": r"(?:PEA|preliminary\s+economic\s+assessment)",
          "resource": r"(?:MRE|(?:mineral\s+)?resource\s+estimate|mineral\s+resources?|(?:the|this|updated|new)\s+estimate)"}
_V5_ANYTW = re.compile(r"(?i)\b(?:" + "|".join(_V5_TW.values()) + r"|(?:technical\s+)?report)\b")


def _v5_effective(b, rtype):
    """The effective date the release gives for the report itself ('a Report effective 12 June 2026', 'the technical
    report ... with an effective date of ...'), else for the row's own study ('The effective date of the FS is April 28,
    2025', 'The ... Mineral Resource Estimate ... has an effective date of September 4, 2018'): the report or study word
    nearest before the date phrase (or named in it) decides whose date it is; a report date earlier than the study's is
    an earlier report's. None when the release gives neither."""
    own, typed = None, None
    tw = re.compile(r"(?i)\b" + _V5_TW[rtype] + r"\b") if rtype in _V5_TW else None
    for s in _sentences(b):
        if not re.search(r"(?i)effective", s):
            continue
        for m in re.finditer(r"(?i)\beffective\s+(?:date\s+)?(?:of\s+the\s+([\w\-\s]{2,40}?)\s+(?:is|was|will\s+be)\s+|of\s+|is\s+|was\s+|"
                             r"as\s+(?:of|at)\s+|:\s*|on\s+)?", s):
            d = _date_at(s, m.end(), 4)
            if not d:
                continue
            what = "the " + m.group(1) if m.group(1) else None
            if not what:
                near = list(_V5_ANYTW.finditer(s[max(0, m.start() - 120):m.start()]))
                what = near[-1].group(0) if near else ""
            if re.search(r"(?i)report", what) and not (tw and tw.search(what)) and not re.search(r"(?i)resource|economic|feasib", what):
                own = own or d
            elif tw and tw.search(what):
                typed = typed or d
    if own and typed and own < typed:
        return typed      # a report dated before the study it reports is an earlier report the release cites
    return own or typed


def _v5_estimate_only(s, prev, h):
    """The sentence's only report word is a resource estimate and nothing near it speaks of a report document (a
    technical report, NI 43-101, a filing or SEDAR, the 45-day rule, an engaged author) -- in it, the sentence before it,
    or the headline; a consulting firm named in it or the sentence before is the report's author): 'the maiden MRE ... is
    nearing completion, results expected to be announced in February', 'an updated MRE is expected to be completed in
    2026'. A resource estimate is the Resources page's news; the report is not yet in view."""
    rws = [m.group(0) for m in _V4_RW.finditer(s)]
    if not rws or not all(_V5_EST_ONLY.match(_flat(x)) for x in rws):
        return False
    return not (_V5_DOC.search(s) or _V5_DOC.search(prev or "") or _V5_DOC.search(h) or _firms_in(s) or _firms_in(prev or ""))


_V5_OPENER = re.compile(r"(?:Regarding|Concerning|As\s+for|As\s+to|With\s+(?:respect|regard)\s+to)\s+(?:the\s+)?"
                        r"((?:[A-Z][\w'\-]+)(?:\s+(?:[A-Z][\w'\-]+|de|del|la|y)){0,3})\s*,\s")
_V5_NOT_PLACE = re.compile(r"(?i)^(?:" + _MON + r"|Q[1-4]|H[12]|(?:19|20)\d\d|Phase|Stage|Year|Total|Overall|Addition|Summary|"
                           r"Conclusion|Particular|General|Fiscal|Calendar|Turn|Order|Light|Line|Short|Parallel|Response|"
                           r"Accordance|Connection|Respect|Terms|Fact|Future)\b")


def _v5_join(ss):
    """Sentences as the release wrote them: an engagement cut after a firm's company form continues in the bracketed
    piece after it ('... has engaged Mine Development Associates, Inc.' + '("MDA") to carry out a PEA of the ...
    project')."""
    out = []
    for x in ss:
        if out and x[:1] == "(" and not re.match(r"\(\s*(?:\d{1,2}|[a-z]|[ivx]+)\s*\)", x) and _V5_ENGAGE.search(out[-1]) \
                and re.search(r"\b(?:Inc|Ltd|Corp|Co|Limited|LLC|Pty|S\.A)\.$", out[-1]):
            out[-1] = out[-1] + " " + x
        else:
            out.append(x)
    return out


def _v5_core(q):
    """The bare form a release uses for a project: 'Media Luna Project' -> 'Media Luna', 'Midlothian Nickel Sulphide
    Project' -> 'Midlothian', 'North Ridge West Project (NRW)' -> 'North Ridge West'."""
    q = re.sub(r"\s*\([^)]*\)\s*$", "", q or "")
    q = _V4_SUF.sub("", q)
    ws = q.split()
    while len(ws) > 1 and _V4_COMMOD.match(ws[-1].lower()):
        ws = ws[:-1]
    return " ".join(ws)


def _v5_known(v4, issuer):
    """[(name, [forms])]: the projects the release names with a suffix (repaired) and writes more than once, each with
    the forms it may be written in alone: the full name, its bare core when that reads as a name, a defined short form.
    Built once per release, and only for a study whose sentence names no project of its own."""
    if getattr(v4, "_v5k", None) is None:
        out = []
        for _i, p in _pn_in(v4.h + " . " + v4.b, issuer):
            q = v4.fix_name(p)
            if not q or q.endswith(("Projects", "Properties", "Deposit", "Deposits")) or any(q == x for x, _f in out):
                continue
            forms = [re.sub(r"\s*\([^)]*\)\s*$", "", q)]
            core = _v5_core(q)
            if len(core) >= 4 and core[:1].isupper() and core not in forms and not (
                    set(re.findall(r"[a-z0-9]+", _fold(core))) <= v4.own) and not (
                    " " not in core and (v4._phrase_word(core) or v4._counts()[core.lower()])):
                forms.append(core)
            sf = re.search(r"\(([A-Z][A-Za-z0-9&]{1,6})\)$", q)
            sf_ = sf.group(1) if sf else None
            if sf:
                forms.append(sf.group(1))
            full_ = [f for f in forms if " " in f or f == sf_]
            if len(re.findall(r"(?i)(?<![\w\-])(?:" + "|".join(re.escape(f) for f in full_) + r")(?![\w\-])", v4.h + " " + v4.b)) < 2:
                continue      # a name the release writes in full once (a table heading, "Pre-Production Capital Costs Mine")
            out.append((q, forms))
        v4._v5k = out
    return v4._v5k


def _v5_mentions(v4, issuer, t):
    """[(end, name)] of the known projects written in t."""
    got = []
    for q, forms in _v5_known(v4, issuer):
        for f in forms:
            for m in re.finditer(r"(?<![\w\-])" + re.escape(f) + r"(?![\w\-])", t):
                got.append((m.end(), q))
    return sorted(got)


def _v5_lead_project(v4, issuer, b, lead, pj):
    """1.0.5: the project of a study still to come when its sentence names no project with a suffix of its own: the
    project its own clause names in a list of items ('...; X has been commissioned to update a 43-101 report on the
    Buckingham Graphite Project; ...'), a project it names alone ('At Castle Mountain, a pre-feasibility study is
    underway'), the place it opens with ('Regarding Terronera, a final update to the pre-feasibility study is being
    prepared'), else the one other project the sentence before it names, alone or in full ('In 2019 we completed the
    infill program at Media Luna ... These ounces will be considered in a feasibility study, which is underway') -- not the
    headline's. None when the sentence's own choice stands."""
    parts = [x for x in re.split(r"\s*;\s+|\s+[\u2022\u25aa\u25cf]\s+", lead) if x.strip()]
    if len(parts) > 1:
        own = [x for x in parts if _COMM.search(x) and _V4_RW.search(x)] or [x for x in parts if _V4_RW.search(x)]
        if own:
            n_ = v4.names_in(own[0])
            others = [q for x in parts if x is not own[0] for q in v4.names_in(x)]
            if n_ and others:
                return n_[0]
    if v4.names_in(lead):
        return None
    inlead = _v5_mentions(v4, issuer, lead)
    if inlead and len({q for _e, q in inlead}) == 1:
        return inlead[0][1]
    m = _V5_OPENER.match(lead)
    if m and not _V5_NOT_PLACE.match(m.group(1)) and not (set(re.findall(r"[a-z0-9]+", _fold(m.group(1)))) & v4.own) \
            and not v4._phrase_word(m.group(1).split()[0]):
        hit = [q for _e, q in _v5_mentions(v4, issuer, m.group(1))]
        return hit[0] if hit else m.group(1)
    i = b.find(lead[:60])
    prev = _v5_join(_sentences(b[max(0, i - 1200):i]))[-1:] if i > 0 else []
    if prev:
        # named in full, or alone after a preposition of place ('at Media Luna'), not as a modifier ('the Heap
        # Reprocessing material')
        got = [q for e, q in _v5_mentions(v4, issuer, prev[0]) if _V4_SUF.search(" " + prev[0][:e].split()[-1]) or
               re.search(r"(?i)\b(?:at|on|in|for|of|from|to|across|within)\s+(?:the\s+)?" + re.escape(_v5_core(q)) + r"$", prev[0][:e]) or
               re.search(r"\s+(?:[Pp]roject|[Pp]roperty|[Mm]ine|[Dd]eposit|[Cc]omplex|[Oo]peration)", prev[0][e:e + 30][:12])]
        if got and all(_v4_same(got[0], q) for q in got + v4.names_in(prev[0])) and \
                not (pj and (_v4_same(pj, got[0]) or _v4_in(pj, prev[0]))):
            return got[0]      # the sentence before names one other project and no other, alone or in full
    return None


def _news(h, b, full):
    issuer = _issuer(b)
    v4 = _V4(h, b, issuer)
    sents = _v6_split(_v5_join(_sentences(b)))      # 1.0.5: "... Inc." + "(\u201cMDA\u201d) to carry out a PEA ..." is one sentence
    fsents = _v6_split(_v5_join(_sentences(full)))  # 1.0.5 (full text): a closing quote ends a sentence
    rows = []

    hl_filed = bool(_FILED_HL.search(h) and _TRW.search(h) and not _nontech(h))
    hl_comm = _v5_hl_comm(h)     # 1.0.4: "Completes Acquisition ... PEA Economics" is no report; 1.0.5: nor other work
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
        # 1.0.4: a citation of an earlier report ("the report that the Company has filed", "... dated April 2, 2014 ...
        # has been filed", "filed on SEDAR in September 2016"), or a filing sentence about something else
        filed_s = [s for s in filed_s if not _v4_old_cited(s, v4.rel, h) and _v4_files_report(s)]
    filed_s = [s for s in filed_s if not v4.is_other(s)]     # 1.0.4: another company's filing
    strong_s = [s for s in filed_s if _STRONG_BODY.search(s) and not _BG_ANY.search(s)]
    body_s = set(sents)
    # 1.0.4: only the release's own text (not the About paragraph, footnotes to other companies' releases); a report
    # word near the cue (measured between the spans); weak language with a timing; not an EIA, a condition, a drill
    # programme or another company's study
    comm_s = [s for s in fsents if (s in body_s or v4.own_timed(s))
              and (_v4_near(s) or (_WILL_FILE.search(s) and _TRW.search(s)))
              and not _nontech(s)
              and not re.search(r"(?i)\bwill\s+be\s+(?:SEDAR\s+)?filed\s+today\b", s)
              and not _NEG.search(s) and not _old_years(s, year) and _comm_ok(s)
              and _v4_cue_ok(s, v4.rel) and not v4.is_other(s)]
    # 1.0.5: an engagement for other work, a programme underway, a report dated over a year ago, an estimate with no
    # report in view are not a report in hand
    fprev = {x: (fsents[i - 1] if i else "") for i, x in reversed(list(enumerate(fsents)))}
    old5 = {}
    comm_s = [s for s in comm_s if _v5_engage_ok(s) and _v5_subject_ok(s) and not _v5_stale(s, v4.rel)
              and not _v5_history(s, b, v4.rel, old5)
              and not (_V5_ESTIMATE_NEEDS_REPORT and _v5_estimate_only(s, fprev.get(s), h))]
    wd_s = [s for s in sents if _WITHDRAWN.search(s)]

    status = None
    if hl_withdrawn or wd_s:
        status = "withdrawn"
    elif hl_filed or strong_s or (filed_s and re.search(r"(?i)" + _V6_HL_NEW, h)):
        # 1.0.5 (full text): "Releases Updated Technical Report on X" + "The Technical Report has been filed on SEDAR and
        # can be found on the Company's website" is a filing
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
    proj = _pick_project([_pn_in(h, issuer), _pn_in(tt, issuer) if tt else [], _pn_in(lead, issuer)])
    lead_i = sents.index(lead) if lead in sents else -1
    if status == "filed" and lead != h:
        # 1.0.5 (full text): the report the filing sentence names is on its own project ('has added the Technical Report on
        # the 100% owned Genesis PGM/ Polymetallic Project to SEDAR' under a headline about an "Alaskan Project"; 'Shag
        # Property IP Survey ... and acceptance of the Frog Property National Instrument 43-101 Report')
        rp = _v6_report_project(lead, issuer) or (_v6_report_project(h, issuer) if not _pn_in(lead, issuer) else None)
        if rp and not (proj and _v4_same(rp, proj)):
            proj = rp
    if not proj:
        # 1.0.4: names the finder does not read -- "Alpha Operations", "Beta Mining District", a defined short form
        proj = next(iter(v4.names_in(h) + (v4.names_in(lead) if lead != h else [])), None)
    if status == "commissioned" and lead != h:
        # 1.0.4: a study belongs to the project its own sentence names (not the headline's or the flagship), and when
        # it names none, to the one the sentence before it names
        pj = v4.fix_name(proj) if proj else None
        ln = v4.names_in(lead, bare=not pj)
        if ln and not (pj and any(_v4_same(pj, q) for q in ln)):
            proj = ln[0]
        elif not ln and lead_i > 0 and not (pj and _v4_in(pj, sents[lead_i - 1] + " " + h)):
            pn = v4.names_in(sents[lead_i - 1])
            if pn:
                proj = pn[0]
        got = _v5_lead_project(v4, issuer, b, lead, pj)     # 1.0.5: its clause, a bare name, its opening, the sentence before
        if got:
            proj = got
    _rp = []

    def rp_names():
        if not _rp:
            _rp.append(_tr_several(h, b, issuer))
        return _rp[0]

    if (not proj or proj.endswith(("Deposit", "Deposits", "Projects", "Properties")) or _TR_GENERIC.search(proj)) \
            and lead != h and rp_names():
        # 1.0.3: the report sentence's project (a plural "Alpha and Beta Projects" or a generic "Production Mine" is
        # not one project)
        p_at = _tr_project_at(b, lead, rp_names(), [q for _i, q in _pn_in(b[:8000], issuer)], look_back=False)
        if p_at:
            proj = p_at
    if not proj or proj.endswith(("Deposit", "Deposits")):
        # 1.0.1: the helper's main project for the release (the headline's, else the body's most-discussed). A mill
        # is not what a report covers; a plural ("Alexo-Dundonald Nickel-Copper-PGE Projects") becomes the body's
        # singular name for it
        pp = PN.primary(h, b, issuer)
        if pp and re.search(r"(?i)\bMills?$", pp):
            pp = None
        if pp and pp.endswith(("Properties", "Projects")):
            pp = next((q for _i, q in _pn_in(b[:8000], issuer) if PN.same(q, pp)
                       and not q.endswith(("Deposit", "Deposits", "Properties", "Projects"))), None)
        if pp and not (proj and pp.endswith(("Deposit", "Deposits"))):
            proj = pp
    if not proj or proj.endswith(("Deposit", "Deposits")):
        from collections import Counter
        allp = Counter(p for _i, p in _pn_in(b[:8000], issuer) if not p.endswith(("Deposit", "Deposits", "Properties", "Projects")))
        if allp:
            proj = allp.most_common(1)[0][0]
    if not proj:
        for src in (h, lead):
            lp = re.search(r"((?:[A-Z\u00c0-\u00dd][\w'\u00c0-\u00ff\-/.]*)(?:\s+" + _CAPW + r"){0,5}?)\s+(project|property)\b", src)
            if lp:
                proj = PN.clean(lp.group(1), lp.group(2).title())
                if proj:
                    break
    if proj:
        # 1.0.4: a name the page can show (no headline fragment, company, defined short form or deposit); when the
        # name is not one, the project the report sentence, the one before it or the headline names
        fixed = v4.fix_name(proj)
        if not fixed:
            for src in [lead] + ([sents[lead_i - 1]] if lead_i > 0 else []) + [h]:
                got = v4.names_in(src)
                if got:
                    fixed = got[0]
                    break
        if not fixed:
            fixed = v4.fix_name(PN.primary(h, b, issuer))
        proj = fixed
    if status == "commissioned" and lead != h and not hl_comm:
        rtype = _type_of(lead) or _type_of(tt) or _type_of(re.sub(r"(?i)supporting\s+|confirming\s+", "", h))
    elif status == "commissioned" and hl_comm:
        # 1.0.5: the headline names the study commissioned; a titled report in its body is an earlier one it builds on
        rtype = _type_of(re.sub(r"(?i)supporting\s+|confirming\s+", "", h)) or _type_of(lead) or _type_of(tt)
    else:
        rtype = _type_of(tt) or _type_of(re.sub(r"(?i)supporting\s+|confirming\s+", "", h)) or _type_of(lead)
    hp = _pn_in(h, issuer)
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
        # 1.0.5 (full text): "The Technical Report discloses a mineral resource" types the report further down the release
        near += " " + " ".join(x for x in sents if _V6_RES_IN.search(x))
        if (_RES_WORDS.search(near) or _V4_RES_STATED.search(near) or _V6_RES_IN.search(near)) and \
                not re.search(r"(?i)\bhistoric(?:al)?\s+(?:mineral\s+)?(?:resource|estimate)", near):
            rtype = "resource"
    if status == "commissioned" and title and v4.rel:
        # 1.0.4: a titled report dated over a year before the release is an earlier report the release cites, not the
        # study still to come: neither its title nor its dates go on the row
        ds = _v4_date_iso(b[title[0]:title[0] + len(tt or "") + 250])
        if ds and all((_v4_months(d, v4.rel) or 0) > 12 for d in ds):
            title, tt = None, None
    main = _blank("news")
    main.update(report_type=rtype, project=proj, status=status, title=tt)
    ctx = " ".join(filed_s[:3] + ([tt] if tt else []))
    if title:
        ctx = b[max(0, title[0] - 400):title[0] + len(tt or "") + 600] + " " + ctx
    main["effective_date"] = _effective(ctx) or (_effective(b) if status != "commissioned" else None)
    if status == "commissioned":
        # 1.0.5: the date the release gives as this report's, or this study's, effective date ('with a Report effective 12
        # June 2026 and an MRE effective 9 June 2026', 'The effective date of the FS is April 28, 2025'), before any other
        main["effective_date"] = _v5_effective(b, rtype) or main["effective_date"]
    if status == "commissioned" and v4.rel:
        # 1.0.4: nor an effective date over a year old; the new estimate's own recent effective date is kept
        gap = _v4_months(main["effective_date"], v4.rel) if main["effective_date"] else None
        if gap is not None and gap > 12:
            main["effective_date"] = None
        if not main["effective_date"]:
            e2 = _effective(b)
            gap = _v4_months(e2, v4.rel) if e2 else None
            if gap is not None and 0 <= gap <= 12:
                main["effective_date"] = e2
    main["report_date"] = _report_date(ctx)
    if status != "commissioned":
        # 1.0.6: the date the release states for the report itself comes first ('"Amended ... Report", and dated January 29,
        # 2019 supersedes the report dated December 20, 2017'); a report still to come has none
        main["report_date"] = _report_date_stated(ctx, main["effective_date"]) or main["report_date"]
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
        return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in PN.key(p or "").split())
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
        ps = v4.names_in(s)      # 1.0.4: the sentence's own projects, repaired (was _pn_in(s))
        p2 = ps[0] if ps else proj
        if proj and any(_v4_same(proj, q) for q in ps):
            p2 = proj
        if not ps and rp_names():     # 1.0.3: only a project the sentence itself names (short form), and not the main one
            p_at = _tr_project_at(b, s, rp_names(), [q for _i, q in _pn_in(b[:8000], issuer)], look_back=False)
            if p_at and not (proj and PN.same(p_at, proj)) and not p_at.endswith(("Deposit", "Deposits")):
                p2 = v4.fix_name(p_at)
        if not p2:
            continue
        same_proj = _pk2(p2) == _pk2(proj)
        if not same_proj and t2 and t2 == rtype and re.search(r"(?i)\b(?:Deposits?|Zones?)$", p2):
            continue      # 1.0.5: the same kind of study named on a deposit is the project's study, not a second report
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
    # one filing statement naming several projects: one row per project -- 1.0.4: only when it files several
    # reports ("technical reports on A and B"); one report covering two projects, or a sentence that also names a
    # neighbouring or former project ("adjacent to its flagship X", "formerly known as Y"), is one row
    # several reports also in the singular: "an amended technical report for each of its A and B projects,
    # respectively entitled ..."
    plural = re.compile(r"(?i)\b(?:technical|43\s*[-\u2010\u2011\u2013]?\s*101)\s+reports\b|\breport\s+(?:for|on)\s+each\s+of\b|"
                        r"\brespectively\b")
    for s in ([h] if hl_filed and plural.search(h) else []) + filed_s[:3]:
        if not plural.search(s):
            continue
        ps = [p for _i, p in _pn_in(s, issuer)]
        ps = [p for p in ps if not p.endswith(("Deposit", "Deposits"))] or ps   # 1.0.1: a deposit sits inside the project (Orosur: Anza / Pepas)
        for a, c in re.findall(r"(?:the\s+)?([A-Z][\w'\-]+)\s+(?:and|,)\s+(?:the\s+)?([A-Z][\w'\-]+)\s+(?:Projects|Properties|projects|properties)\b", s):
            ps += [a + " Project", c + " Project"]
        # 1.0.5 (full text): "Technical Reports on the Alpha and Beta Gold Mines, respectively" -- two mines, one report each
        mines = {}
        for a, c, w in re.findall(r"(?:the\s+)?([A-Z][\w'\-]+)\s+(?:and|,)\s+(?:the\s+)?([A-Z][\w'\-]+)\s+((?:[A-Z][a-z]+\s+)?)Mines\b", s):
            if not w or _V4_COMMOD.match(w.strip()):
                mines.update({PN.key(q): q for q in (a + " " + w + "Mine", c + " " + w + "Mine")})
        ps += list(mines.values())
        keys = [k for k in dict.fromkeys(PN.key(p) for p in ps) if k]
        keys = [k for k in keys if not any(k != o and (set(k.split()) <= set(o.split()) or set(o.split()) <= set(k.split())) and len(o) < len(k) for o in keys)]
        if len(keys) >= 2:
            out = []
            titles = _all_titles(b)
            for key in keys:
                r2 = dict(main)
                full_ = [q for _i, q in _pn_in(b, issuer) if PN.key(q) == key]
                r2["project"] = v4.fix_name(mines.get(key) or (full_[0] if full_ else next(p for p in ps if PN.key(p) == key)))
                tl = [x for _i, x in titles if key and key.split()[0] in _fold(x)]
                r2["title"] = tl[0] if tl else None
                out.append(r2)
            rows = out + rows[1:]
            break
    rows = [r for r in rows if r.get("project") or r.get("report_type")]
    # 1.0.4: a study still to come must be placed on a project and must be the issuer's own (a royalty or streaming
    # company's release recaps its operators' studies); one row per report
    rows = [r for r in rows if r["status"] != "commissioned" or (r.get("project") and not v4.royalty)]
    uniq, keys = [], set()
    for r in rows:
        k = (PN.key(r.get("project") or ""), r["status"], r.get("report_type"))
        if k not in keys:
            keys.add(k)
            uniq.append(r)
    rows = uniq
    return rows, (None if rows else "no_named_report")


# ------------------------------------------------------------------ public API
_ANY = re.compile(r"(?i)technical\s+report|43\s*-?\s*101|\bPEA\b|\bPFS\b|feasibility|resource\s+estimate|\bMRE\b|"
                  r"economic\s+assessment|qualified\s+person")


_V6_DASHES = {0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2212: "-"}


def _v6_text(t):
    """1.0.5 (full text): Unicode hyphens ("NI43\u2010101", "Pre\u2010feasibility" in PDF text) read as "-"."""
    return t.translate(_V6_DASHES) if t else t


def _v6_split(ss):
    """1.0.5 (full text): a sentence that ends inside a closing quote starts a new sentence ('... ultimately,
    production." The updated NI 43-101 Technical Report is expected ...'); the shared splitter runs them together."""
    out = []
    for x in ss:
        out += [p for p in re.split(r'(?<=[.!?][\u201d"])\s+(?=[A-Z])', x) if p.strip()]
    return out


def _v6_report_project(s, issuer):
    """The project a report word in s is tied to: '<X Project> (National Instrument|NI) 43-101 Report' or 'Technical Report
    (on|for) (the|its) [100% owned] <X Project>'. One project only."""
    got = []
    for i, p in _pn_in(s, issuer):
        if p.endswith(("Deposit", "Deposits")):
            continue
        j = s.find(p, max(0, i - 5))
        if j < 0:
            continue
        after = s[j + len(p):j + len(p) + 40]
        before = s[max(0, j - 80):j]
        if re.match(r"(?i)\s*(?:National\s+Instrument\s+|NI\s*)?43\s*-?\s*101\s+(?:technical\s+)?report|\s*technical\s+report", after) or \
                re.search(r"(?i)" + _V6_DOC + r"\s+(?:on|for)\s+(?:the\s+|its\s+|our\s+)?(?:[\w%'\-]+\s+){0,3}?$", before):
            if not any(_v4_same(p, q) for q in got):
                got.append(p)
    return got[0] if len(got) == 1 else None


def analyse(headline, body):
    headline, body = _v6_text(headline), _v6_text(body)
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
    # 1.0.1: this file whole, and exactly the shared-helper code it runs (portal/fingerprint.py follows every portal
    # module this file imports), so a helper release changes this reader's fingerprint too
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
    # 1.0.3: several projects per release (helper 1.0.5)
    r = analyse("ABC Provides Update on Alpha Gold and Beta Copper Projects",
                "Toronto, March 2, 2026 - ABC Gold Corp. (TSXV: ABC) provides an update on its Alpha Gold Project and its "
                "Beta Copper Project. At the Alpha Gold Project, construction of the mill continues on schedule and the "
                "Alpha Gold Project remains on budget. At the Beta Copper Project, drilling resumed in June and the Beta "
                "Copper Project camp was expanded. An updated mineral resource estimate at Beta Copper has been completed and "
                "a technical report supporting it will be filed on SEDAR+ within 45 days." + fill)
    eq("1.0.3 the report takes the project its sentence names", [(x["status"], x["project"]) for x in r["rows"]],
       [("commissioned", "Beta Copper Project")])
    eq("1.0.3 a short name in the report sentence wins", _tr_project_at(
        "At Mont Sorcier, drilling continued. At Lagoa Salgada, the Optimized Feasibility Study is nearing completion.",
        "At Lagoa Salgada, the Optimized Feasibility Study is nearing completion.",
        ["Mont Sorcier High Purity DRI Iron Project", "Lagoa Salgada Polymetallic Project"]),
       "Lagoa Salgada Polymetallic Project")
    eq("1.0.3 short forms", (_tr_short("La Preciosa Project"), _tr_short("Knauss Creek Property"),
                             _tr_short("Cam Copper Project")), ("La Preciosa", "Knauss", "Cam"))
    # 1.0.4: project names, whose study, background, filed only when filed, no old dates on a study to come
    lead4 = "Toronto, March 2, 2026 - ABC Gold Corp. (TSXV: ABC) (\"ABC\" or the \"Company\") "

    def rows4(hl, body):
        return [(x["status"], x["report_type"], x["project"], x["effective_date"], x["title"]) for x in analyse(hl, body)["rows"]]
    eq("1.0.4 a defined short form becomes the full name", rows4(
        "ABC Reports Drill Results and Provides NRW Project Update",
        lead4 + "reports drill results from its North Ridge West Project (\"NRW\" or the \"Project\"). Summit Geoscience has been "
        "engaged to complete the maiden mineral resource estimate of the NRW project, and a technical report will be filed "
        "within 45 days of its release." + fill),
       [("commissioned", "resource", "North Ridge West Project (NRW)", None, None)])
    eq("1.0.4 a study goes on the project its own sentence names", rows4(
        "ABC Provides Update on Alpha Gold Project",
        lead4 + "provides an update on its Alpha Gold Project, where drilling continues. At its Gamma Copper Project, the Company "
        "has engaged Summit Geoscience to prepare an updated mineral resource estimate and technical report for the Gamma "
        "Copper Project, expected in Q3 2026." + fill),
       [("commissioned", "resource", "Gamma Copper Project", None, None)])
    eq("1.0.4 no headline fragment for a name, and 'Completes Acquisition ... PEA Economics' is no report", rows4(
        "ABC Completes Acquisition of 100% Ownership of Beta Lithium Project with Robust PEA Economics",
        lead4 + "has completed the acquisition of 100% ownership of the Beta Lithium Project. The Company's ownership interest "
        "was 50% before the transaction. Pre-feasibility study work is ongoing." + fill), [])
    v = _V4("ABC Completes Acquisition of 100% Ownership of Beta Lithium Project",
            "ABC Gold Corp. (TSXV: ABC) completes the acquisition of 100% ownership of the Beta Lithium Project. Omni Projects SA "
            "(Proprietary) Limited will provide engineering; our ownership stake grows.", "ABC Gold Corp.")
    eq("1.0.4 names: fragment, headline verb, company, headline adjective",
       [v.fix_name(x) for x in ("Ownership of Beta Lithium Project", "Selects Mine", "Omni Projects", "Robust Project")],
       ["Beta Lithium Project", None, None, None])
    eq("1.0.4 another company's filing is not a row", rows4(
        "ABC Provides Property Update",
        lead4 + "provides an update on its Delta Property. On February 25, 2026, Northwind announced the filing of an "
        "independent preliminary economic assessment for the Kappa Mine, which adjoins the Delta Property." + fill), [])
    eq("1.0.4 'the report that the Company has filed' is a citation", rows4(
        "ABC Commences Exploration Program on Alpha Gold Project",
        lead4 + "has commenced the program recommended in the NI 43-101 technical report that the Company has filed on SEDAR+ "
        "for the Alpha Gold Project." + fill), [])
    eq("1.0.4 a study in the About paragraph is not a row", rows4(
        "ABC Closes Private Placement",
        lead4 + "has closed a private placement of $2 million." + fill * 4 + " About the Company: ABC is advancing the Alpha "
        "Gold Project, where a feasibility study is currently being prepared by Summit Geoscience."), [])
    eq("1.0.4 the Company's own timed study in the About paragraph is a row; a footnote citing a release is not", [
        [(x[0], x[1]) for x in rows4(
            "ABC Files NI 43-101 Technical Report for the Alpha Gold Project",
            lead4 + "announces that a NI 43-101 technical report on the Alpha Gold Project has been filed on SEDAR+." + fill * 4 +
            " About the Company: ABC is advancing the Alpha Gold Project. The Company announced an updated mineral resource "
            "estimate in February 2026, and is commencing the preparation of an updated PEA that is expected in early "
            "2027." + x)] for x in ("", " (1) Northwind News Release dated May 24, 2026 (Technical Report to be filed within "
                                    "45 days of news release).")],
       [[("filed", "property"), ("commissioned", "PEA")]] * 2)
    eq("1.0.4 a footnote after the About paragraph citing another company's release is not a row", rows4(
        "ABC Reports Drill Results at Alpha Gold Project",
        lead4 + "reports drill results from the Alpha Gold Project." + fill * 4 + " About the Company: ABC is exploring the "
        "Alpha Gold Project, next to the Kappa deposit (1). (1) Northwind News Release dated May 24, 2026 (Technical Report "
        "to be filed within 45 days of news release) For further information on ABC, contact the Company."), [])
    eq("1.0.4 'a technical report for each of' A and B files several reports", [x[2] for x in rows4(
        "ABC Files Amended Technical Reports",
        lead4 + "has filed an amended technical report for each of its Alpha and Beta projects, respectively entitled "
        "\"Technical Report on the Alpha Project\" and \"Technical Report on the Beta Property\"." + fill)],
       ["Alpha Project", "Beta Property"])
    eq("1.0.4 a study underway with no timing is not a row; with a timing it is", [rows4(
        "ABC Reports Drill Results at Alpha Gold Project",
        lead4 + "reports drill results. A feasibility study on the Alpha Gold Project is underway" + t + "." + fill)
        for t in ("", " and expected to be completed in Q4 2026")],
       [[], [("commissioned", "FS", "Alpha Gold Project", None, None)]])
    eq("1.0.4 a royalty company's recap of an operator's study is not a row", rows4(
        "XYZ Royalties Provides Portfolio Update",
        "Toronto, March 2, 2026 - XYZ Royalties Corp. (TSXV: XYZ) (\"XYZ\" or the \"Company\") provides an update. At the "
        "Omega Gold Project, the operator has engaged Summit Geoscience to prepare a preliminary economic assessment, expected in Q3 "
        "2026." + fill), [])
    eq("1.0.4 filing a title opinion is not filing the report", rows4(
        "ABC Provides Update on Beta Property Option",
        lead4 + "provides an update on the Beta Property option. The Company has filed a title opinion on the licences "
        "comprising the Beta Property, and is preparing a NI 43-101 geological report on the Beta Property." + fill),
       [("commissioned", None, "Beta Property", None, None)])
    eq("1.0.4 a report still to come takes no earlier report's date or title", rows4(
        "ABC Announces Updated Mineral Resource Estimate for Alpha Gold Project",
        "Toronto, March 15, 2023 - ABC Gold Corp. (TSXV: ABC) (\"ABC\" or the \"Company\") announces an updated mineral "
        "resource estimate for the Alpha Gold Project. A technical report supporting the estimate will be filed on SEDAR+ "
        "within 45 days. The previous technical report, titled \"Technical Report and Initial Mineral Resource Estimate of "
        "the Alpha Gold Project\" with an effective date of March 1, 2021, is available on SEDAR+." + fill),
       [("commissioned", "resource", "Alpha Gold Project", None, None)])
    eq("1.0.4 one report on two projects is one row", [x[2] for x in rows4(
        "ABC Files NI 43-101 Technical Report on the Alpha Gold Project",
        lead4 + "announced the filing of a technical report entitled \"NI 43-101 Technical Report on the Alpha Gold Project "
        "and Beta Gold Project, Nevada\"." + fill)], ["Alpha Gold Project"])
    eq("1.0.4 an EIA to be filed is not an NI 43-101 report", rows4(
        "ABC Files Environmental Impact Assessment for Alpha Mine",
        lead4 + "has filed an environmental impact assessment. The final EIA study will be filed following the completion of "
        "the pre-feasibility study on the Alpha Mine." + fill), [])
    # 1.0.5: the release's own report, on its own project, by its own author
    eq("1.0.5 an engagement for other work is not a report in hand", [rows4(
        "ABC Reports Third Quarter Results", lead4 + "reports its third quarter results. Summit Mineral Consultants Ltd. was "
        "engaged to optimize the flotation design based on the feasibility study work completed in 2025 in order to produce "
        "saleable concentrates at the Alpha Gold Mine." + fill), rows4(
        "ABC Engages Jane Doe as Interim Consultant to Facilitate Alpha Gold Project Feasibility Study Engineering",
        lead4 + "has engaged Jane Doe to support the Alpha Gold Project on an interim basis until a project director is "
        "hired." + fill)], [[], []])
    eq("1.0.5 an engagement cut after the firm's company form still reads", [x[:3] for x in rows4(
        "ABC ENGAGES SUMMIT FOR PRELIMINARY ECONOMIC ASSESSMENT",
        lead4 + "has engaged Summit Mining Consultants, Inc. (\"Summit\") to carry out a Preliminary Economic Assessment "
        "(\"PEA\") of the Alpha zinc project in California. Summit is an independent engineering firm based in Reno. "
        "Completion of the PEA is expected in the first quarter of 2027. Summit co-authored a 2015 feasibility study for "
        "the Kappa Mountain mine of another company and the Kappa Mountain mine went into production." + fill)],
       [("commissioned", "PEA", "Alpha Project")])
    eq("1.0.5 a programme nearing completion is not the report; a study 'which is expected' is", [rows4(
        "ABC Highlights Alpha Progress", lead4 + "provides an update on the Alpha Gold Project. The geotechnical program at "
        "the main pit to support the feasibility study update is also nearing completion." + fill), [x[:2] for x in rows4(
        "ABC Reports Metallurgical Results at Alpha Gold Project", lead4 + "reports metallurgical results. This test program "
        "will define recovery equations for the Alpha PEA, which is expected to be released by the end of 2026." + fill)]],
       [[], [("commissioned", "PEA")]])
    eq("1.0.5 a report the sentence dates over a year before the release is carried over", rows4(
        "ABC Discovers High Grades at Alpha", "Reno, Nevada / May 26, 2021 - ABC Gold Corp. (TSXV: ABC) (\"ABC\" or the "
        "\"Company\") reports drill results from the Alpha gold project. In accordance with NI 43-101 the Summit Technical "
        "Report dated January 24, 2020 will be filed on SEDAR." + fill), [])
    eq("1.0.5 an estimate with no report in view is not a row; with an engaged author it is", [rows4(
        "ABC Reports High Grade Assays", lead4 + "reports assays from the Alpha Gold Project. The drill holes will form the "
        "basis of the maiden mineral resource estimate for the Alpha Gold Project, which is nearing completion, with results "
        "expected to be announced in April 2026." + fill), [x[:2] for x in rows4(
        "ABC Reports High Grade Assays", lead4 + "reports assays from the Alpha Gold Project. Summit Geoscience has been hired "
        "to complete the updated mineral resource estimate, expected in Q3 2026." + fill)]],
       [[], [("commissioned", "resource")]])
    eq("1.0.5 an engagement told as the history of a report filed long ago is not a row", rows4(
        "ABC Announces First Quarter Results from the Alpha Gold Mine", lead4 + "reports first quarter production. ABC "
        "engaged Summit Engineering Pty Ltd to complete the PEA for the expansion of the processing plant. The technical "
        "report containing the PEA, titled \"Independent Technical Report and Preliminary Economic Assessment of the Alpha "
        "Gold Mine\" with an effective date of September 30, 2024 is available on SEDAR." + fill), [])
    eq("1.0.5 the clause of a list that names the report; a 'Regarding X,' opener", [[x[2] for x in rows4(
        "ABC Update on Exploration Projects", lead4 + "reports on several projects. Claims were staked; \uf06c Application "
        "has been made for a drill program on the Beta Project; \uf06c Jane Smith has been commissioned to update a 43-101 "
        "report on the Gamma Graphite Project; \uf06c a property has been acquired." + fill)], [x[2] for x in rows4(
        "ABC Provides 2026 Production Guidance for the Alpha Mine", lead4 + "provides guidance for the Alpha Mine. Regarding "
        "Tierra Alta, a final update to the pre-feasibility study is currently being prepared, expected in Q3 2026." + fill)]],
       [["Gamma Graphite Project"], ["Tierra Alta"]])
    eq("1.0.5 the study's sentence names its project alone", [x[2] for x in rows4(
        "ABC Reports Production from the Alpha Mine", lead4 + "reports production from the Alpha Mine and progress at the "
        "Castle Peak Project. Haulage on the Castle Peak Project road resumed. Gold sales rose by ten percent. At Castle "
        "Peak, a pre-feasibility study is underway and expected in Q4 2026." + fill)], ["Castle Peak Project"])
    eq("1.0.5 the sentence before names the study's own project in its bare form", [x[2] for x in rows4(
        "ABC Reports Year-End Reserves for the Alpha Complex", lead4 + "reports reserves for the Alpha Complex and the "
        "Gamma project, and the Gamma project budget. In 2025 we completed the infill drill program at Gamma and "
        "upgraded the resource. These ounces will "
        "be considered in a feasibility study, which is underway and is expected to be complete in H1 2027." + fill)],
       ["Gamma Project"])
    eq("1.0.5 names: the issuer's portfolio, a description, a mine inside the project",
       [x[2] for x in rows4("All Four ABC Projects Active This Fall", lead4 + "reports on its four projects. At the Delta "
                            "Project, sampling will commence. This data will be incorporated into an NI 43-101 technical "
                            "report being prepared on this project and expected to be released later this year." + fill)] +
       [x[2] for x in rows4("ABC Closes Financing", lead4 + "closed a financing. The proceeds will advance ABC's flagship "
                            "Omega Project, including the past-producing Kappa Mine. The financing was oversubscribed. The "
                            "Company is currently preparing a National Instrument 43-101 Technical Report, expected in Q2 "
                            "2026. The Kappa Mine had production, the Kappa Mine shaft is open and the Kappa Mine mill was "
                            "rebuilt." + fill)] +
       [_V4("ABC Remains a Stand-Out Oxide Development Project", "ABC Gold Corp. (TSXV: ABC) reports on its Delta Property.",
            "ABC Gold Corp.").fix_name("Stand-Out Oxide Development Project")],
       ["Delta Project", "Omega Project", None])
    eq("1.0.5 one study named on a deposit is one row; a PDF's 'Pre - feasibility' is a PFS", [x[:3] for x in rows4(
        "ABC Reports First Quarter Results", lead4 + "reports results. The resources will be used to support the "
        "Pre-Feasibility Study (PFS) for the Alpha River Project, expected to be completed in the second half of 2026. With the "
        "update to the Gryphon deposit resource estimate, the resources will be used to support the Pre - feasibility study "
        "('PFS') expected to be completed in the second half of 2026." + fill)], [("commissioned", "PFS", "Alpha River Project")])
    eq("1.0.5 the headline names the study commissioned, not a titled earlier report", [x[1] for x in rows4(
        "ABC Commissions Updated Preliminary Economic Assessment for the Alpha Gold Project",
        "Toronto, November 1, 2026 - ABC Gold Corp. (TSXV: ABC) has engaged Summit Engineering to prepare an updated PEA for "
        "the Alpha Gold Project. The PEA will use the mineral resource estimate in the report titled \"Mineral Resource "
        "Estimate Technical Report for the Alpha Gold Project\" with an effective date of January 25, 2026." + fill)], ["PEA"])
    eq("1.0.5 'Papua New Guinea' is not a new report; an effective date a year and a month old is cited", rows4(
        "ABC Announces Drill Results", "Toronto, March 29, 2026 - ABC Gold Corp. (TSXV: ABC) reports drill results. ABC has "
        "filed and made available on its SEDAR profile a technical report titled \"Independent Technical Report, Alpha "
        "Gold Project, Papua New Guinea\" with an effective date of March 2, 2025, that provides information on the "
        "geology." + fill), [])
    eq("1.0.5 firms: a Ni-Cu-Co name, a Qualified Person heading, a caption, a timeline, a division, a headline verb, a "
       "firm engaged for other work",
       [[f for _p, f in _firms_in("for the Gochager Lake Ni-Cu-Co Deposit, prepared by Caracle Creek International "
                                  "Consulting Inc.")],
        _authors("Qualified Person The Alpha West PGE-Ni-Cu-Co + Au project 2026 Resource estimate was prepared by Jane "
                 "Smith, P.Geo., of SGS Geological Services, an independent Qualified Person.")[0],
        _authors("Prepared by TRU Group Resource Estimate Details are below. The mineral resource estimate was prepared by "
                 "Chris Doe, M.Sc. of Valorose Consulting, Inc.")[0][:1],
        _authors("2012: Wardrop, a Tetra Tech Company (Tetra Tech) was retained to prepare a PEA. The updated resource "
                 "estimate was prepared by APEX Geoscience Ltd.")[0],
        _authors("The PEA was prepared by Montreal-based Met-Chem, a division of DRA Americas Inc., and will be filed "
                 "on SEDAR.")[0][:1],
        _authors("ABC has commissioned Micon International to complete an updated PEA on the Alpha project.")[0],
        _authors("ABC Engages Wood Canada Limited to Prepare a PEA. ABC has engaged Wood Canada Limited (Wood) to prepare "
                 "a PEA.", "ABC Gold Corp.")[0][:1],
        _authors("Summit Consulting was engaged to optimize the mine plan in advance of the PFS. The PFS will be prepared by "
                 "Ausenco Engineering Canada Inc.")[0]],
       [["Caracle Creek International Consulting"], ["SGS Geological Services"], ["Valorose Consulting"],
        ["APEX Geoscience"], ["Met-Chem"], ["Micon"], ["Wood Canada"], ["Ausenco Engineering"]])
    eq("1.0.5 effective dates: the report's own, the study's own, not an earlier report's", [
        _v5_effective("The report is titled \"MRE and Technical Report\", prepared by Summit, with a Report effective 12 June "
                      "2026 and an MRE effective 9 June 2026.", "resource"),
        _v5_effective("The study is derived using the mineral resource estimate effective as at September 15, 2024. The "
                      "effective date of the FS is April 28, 2025, and a technical report will be filed within 45 days.", "FS"),
        _v5_effective("Effective date of the estimate is June 14, 2018. It replaces the maiden estimate included in a "
                      "Technical Report completed by Summit with an effective date of September 30, 2017.", "resource")],
       ["2026-06-12", "2025-04-28", "2018-06-14"])
    eq("1.0.5 a study to come takes its own effective date", [x[3] for x in rows4(
        "ABC Delivers Feasibility Study for the Alpha Gold Project", "Toronto, April 28, 2026 - ABC Gold Corp. (TSXV: ABC) "
        "announces a feasibility study for the Alpha Gold Project. The study uses the mineral resource estimate effective "
        "as at September 15, 2025. The effective date of the FS is April 28, 2026, and a NI 43-101 technical report will be "
        "filed within 45 days. The estimate has an effective date of September 15, 2025." + fill)], ["2026-04-28"])
    # 1.0.5 (full text): releases the full text showed were lost
    eq("1.0.5ft a headline 'Commences ... Technical Report'; a closing quote ends a sentence", [x[:3] + (r["expected"],) for x, r in zip(
        rows4("ABC Commences Updated NI 43-101 Technical Report for the Alpha Gold Project", lead4 + "is pleased to announce "
              "that it has commenced work on an updated NI 43-101 Technical Report for its Alpha Gold Project. CEO Jane Doe "
              "commented: \"Together with the ongoing environmental permitting process, this work moves us toward production.\" "
              "The updated NI 43-101 Technical Report is expected to be completed in the coming months." + fill),
        analyse("ABC Commences Updated NI 43-101 Technical Report for the Alpha Gold Project", lead4 + "is pleased to announce "
                "that it has commenced work on an updated NI 43-101 Technical Report for its Alpha Gold Project. CEO Jane Doe "
                "commented: \"Together with the ongoing environmental permitting process, this work moves us toward "
                "production.\" The updated NI 43-101 Technical Report is expected to be completed in the coming months." + fill)["rows"])],
       [("commissioned", None, "Alpha Gold Project", "in the coming months")])
    eq("1.0.5ft quote split, Unicode hyphens", (_v6_split(["He said: \"We advance.\" The report is due."]),
                                                _v6_text("NI43\u2010101 Pre\u2011feasibility")),
       (["He said: \"We advance.\"", "The report is due."], "NI43-101 Pre-feasibility"))
    eq("1.0.5ft 'pleased to report that it has filed' is the filing, not a citation", [x[:3] for x in rows4(
        "ABC Updates NI 43-101 Technical Report for the Alpha Uranium Project", lead4 + "is pleased to report that it has filed "
        "an updated technical report for the Company's Alpha Uranium Project. The updated technical report has an effective "
        "date of January 30, 2026." + fill)], [("filed", "property", "Alpha Uranium Project")])
    eq("1.0.5ft body cues: in the process of preparing; 45 days from the date hereof; has completed a report; anticipates "
       "completion of a report; early in the New Year", [[x[:3] for x in rows4(hl, lead4 + bd + fill)] for hl, bd in (
        ("ABC Announces Securities Commission Review", "is in the process of preparing a new technical report on the Alpha "
         "Property and anticipates filing it on or before the date that is 45 days from the date hereof."),
        ("ABC Highlights Gold Potential at Alpha", "is pleased to announce that Summit Mining Services has completed a "
         "detailed NI 43-101 Technical Report on the Alpha Project."),
        ("ABC Provides Update on Acquisition", "Management anticipates completion of a NI 43-101 compliant technical report "
         "on the Alpha Vanadium Project to be completed in the coming weeks."),
        ("ABC Provides Update", "Compliant updated NI 43-101 Technical Reports on the Alpha Project are expected to be "
         "completed early in the New Year."))],
       [[("commissioned", None, "Alpha Property")], [("commissioned", "property", "Alpha Project")],
        [("commissioned", None, "Alpha Vanadium Project")], [("commissioned", None, "Alpha Project")]])
    eq("1.0.5ft not a report in hand: a condition ('needs to be completed by the Company'), a programme to be completed",
       [rows4("If the Proposal Succeeds, a Compliant NI 43-101 Report Needs to Be Completed by the Company", lead4 + "reports "
              "on talks with the landowners at the Alpha Mine." + fill),
        rows4("ABC Reports Fourth Quarter Results", lead4 + "reports results. An infill drilling program at the Alpha Project "
              "is planned to be completed in 2026 to upgrade resources to a feasibility study level." + fill)], [[], []])
    eq("1.0.5ft headline forms: 'Completes Site Visit & Technical Report', 'Technical Report Completed on', 'to Amend "
       "Technical Report'", [x[0] + x[2] for x in [(rows4(hl, lead4 + "reports on its Alpha Gold Project." + fill) or [("none", None, "")])[0] for hl in (
        "ABC COMPLETES SITE VISIT & TECHNICAL REPORT ON THE ALPHA GOLD PROJECT",
        "NI 43-101 Technical Report Completed on the Alpha Gold Project",
        "ABC to Amend Technical Report on the Alpha Gold Project")]],
       ["commissionedAlpha Gold Project"] * 3)
    eq("1.0.5ft 'Announces Updated Technical Report' with a body filing line is filed; 'Reports Updated Technical Report' "
       "alone is commissioned", [[x[:3] for x in rows4(hl, lead4 + bd + fill)] for hl, bd in (
        ("ABC Announces Updated Technical Report on the Alpha Property", "announces an updated NI 43-101 technical report on "
         "the Alpha Property. The Technical Report has been filed on SEDAR and can be found on the Company's website. The "
         "Technical Report discloses a mineral resource."),
        ("ABC Reports Updated Technical Report for the Alpha Project, Delivering US$3.2 Billion NPV", "reports the results "
         "of an updated NI 43-101 Technical Report for the Alpha Project."))],
       [[("filed", "resource", "Alpha Property")], [("commissioned", None, "Alpha Project")]])
    eq("1.0.5ft filing statements: added to SEDAR, accepted for filing and viewable on SEDAR, completed the filings of",
       [[x[:3] for x in rows4(hl, lead4 + bd + fill)] for hl, bd in (
        ("ABC Completes Alpha PGM Technical Report, Seeks Partner for Road Accessible Beta Project", "has added the "
         "Technical Report on its 100% owned Alpha PGM Project to SEDAR."),
        ("ABC Completes Gamma Property IP Survey and Exchange Acceptance of the Delta Property 43-101 Report", "is pleased "
         "to report that a recently prepared Delta property National Instrument 43-101 report has been accepted for filing "
         "by the Exchange and can be viewed on the Company's SEDAR profile."),
        ("ABC Completes Alpha and Beta Gold Mine Technical Report Filings", "is pleased to report the Company has completed "
         "the filings of independent NI 43-101 Technical Reports on the Alpha and Beta Gold Mines, respectively."))],
       [[("filed", "property", "Alpha PGM Project")], [("filed", "property", "Delta Property")],
        [("filed", "other", "Beta Gold Mine"), ("filed", "other", "Alpha Gold Mine")]])
    # 1.0.6 (FIX5): report date, QP names, author lines
    def rd6(hl, body):
        return [(x["status"], x["report_date"], x["effective_date"]) for x in analyse(hl, lead4 + body + fill)["rows"]]
    eq("1.0.6 report date: a title 'dated', 'issued', a date of signature; not 'dated effective' or a release's date",
       [rd6("ABC Files NI 43-101 Technical Report on the Alpha Gold Project", "has filed the technical report titled \"NI 43-101 "
            "Technical Report on the Alpha Gold Project, Ontario\" dated February 20, 2026, with an effective date of January 15, "
            "2026."),
        rd6("ABC Files NI 43-101 Technical Reports on the Alpha Gold Project", "further to its news release dated January 5, 2026, "
            "has filed the technical report on the Alpha Gold Project. The technical report, issued February 27, 2026 with an "
            "effective date of January 5, 2026, is available on SEDAR+."),
        rd6("ABC Files NI 43-101 Technical Report on the Alpha Gold Project", "has filed the technical report titled \"NI 43-101 "
            "Technical Report on the Alpha Gold Project\", bearing the date of signature of the February 3rd 2026."),
        rd6("ABC Files NI 43-101 Technical Report on the Alpha Gold Project", "further to its news release dated February 1, 2026, "
            "has filed the technical report titled \"NI 43-101 Technical Report on the Alpha Gold Project\" dated effective "
            "January 15, 2026.")],
       [[("filed", "2026-02-20", "2026-01-15")], [("filed", "2026-02-27", "2026-01-05")], [("filed", "2026-02-03", None)],
        [("filed", None, "2026-01-15")]])
    eq("1.0.6 report date: the report's own date before a superseded one; none before the effective date or on a study to come",
       [rd6("ABC Files Amended Technical Report for the Alpha Mine", "has filed an amended technical report. The report entitled "
            "\"Amended NI 43-101 Technical Report, Alpha Project\", and dated January 29, 2026 supersedes the report dated "
            "December 20, 2024 that was previously filed on SEDAR."),
        rd6("ABC Files NI 43-101 Technical Report on the Alpha Gold Project", "has filed the technical report titled \"NI 43-101 "
            "Technical Report on the Alpha Gold Project\" dated March 30, 2025 with an effective date of October 31, 2025."),
        [x["report_date"] for x in analyse("ABC Announces Maiden Mineral Resource Estimate at Alpha Gold Project", lead4 + "announces a maiden "
                               "mineral resource estimate. A technical report dated as of today will be filed within 45 days."
                               + fill)["rows"]]],
       [[("filed", "2026-01-29", None)], [("filed", None, "2025-10-31")], [None]])
    eq("1.0.6 a consent's report date: not the supported release's",
       [x["report_date"] for x in analyse("Consent of qualified person (NI 43-101)",
        "CONSENT OF QUALIFIED PERSON\nRe: Filing of a Technical Report supporting the press release titled \"ABC Updates its Alpha "
        "Project Mineral Resource Estimate\", dated May 21, 2026. I, Jane Smith, do hereby consent to the public filing by ABC of "
        "a Technical Report titled \"Updated Mineral Resource Estimate on the Alpha Gold Project\" by Jane Smith, P.Geo. of P&E "
        "Mining Consultants Inc., dated July 6, 2026 (the \"Technical Report\").\n" + ("x " * 200) +
        "\nDated this 6th day of July, 2026\nJane Smith, P.Geo.")["rows"]], ["2026-07-06"])
    eq("1.0.6 QP names", [_qps_in("prepared by Mr. W. Lewis, P.Geo., Mr. A. San Martin, MAusIMM (CP) and Mr. R.M. Gowans, B.Sc., "
                                  "P.Eng., of Micon"),
                          _qps_in("co-authored by Michael G. Hester (FAusIMM), Simon Mortimer (M.Sc., FAIG) and Adam Johnston"
                                  " (FAusIMM(CP)) dated"),
                          _qps_in("Independent consultants, F\u00e1bio Val\u00e9rio (P.Geo.) and Porfirio Cabaleiro (P.Eng.), of GE21"),
                          _qps_in("7 | Page QUALIFIED PERSONS The estimate was prepared by Robin Rankin MSc DIC MAusIMM (CP)"),
                          _qps_in("by Bernardo Viana, BSc Geology, FAIG and Deepak Malhotra PhD, QP and Mr. Jim Brebner P.ENG. who"),
                          _qps_in("who are Star Diamond's QP's under the definition of NI 43-101")],
       [["W. Lewis", "A. San Martin", "R.M. Gowans"], ["Michael G. Hester", "Simon Mortimer", "Adam Johnston"],
        ["F\u00e1bio Val\u00e9rio", "Porfirio Cabaleiro"], ["Robin Rankin"], ["Bernardo Viana", "Deepak Malhotra", "Jim Brebner"], []])

    def au6(hl, body):
        return [(x["author_firm"], x["qps"]) for x in analyse(hl, lead4 + body + fill)["rows"]]
    eq("1.0.6 author lines: an MRE undertaken by, contracted to complete, supervision then approval, a list after a colon",
       [au6("ABC Files NI 43-101 Updated Mineral Resource Estimate for the Alpha Gold Project", "has filed the technical report "
            "titled \"Updated Mineral Resource Estimate of the Alpha Gold Project\". The MRE was undertaken by Fred Brown, P.Geo. "
            "and Eugene Puritch, P.Eng., FEC, CET of P&E Mining Consultants Inc."),
        au6("ABC Completes Resampling Program on Its Alpha Property for an Updated Resource Estimate", "completed its core "
            "resampling program at the Alpha Property. Sue Bird, P.Eng., of Moose Mountain Technical Services will be contracted "
            "to complete the new NI 43-101 compliant resource estimation and Technical Report."),
        au6("ABC Files NI 43-101 Technical Report for the Alpha Gold Project", "has filed the technical report on the Alpha Gold "
            "Project. The Mineral Resource Estimate was under the supervision of Eugene Puritch, P.Eng., FEC, CET, President of "
            "P&E Mining Consultants Inc., who is independent, and has reviewed and approved the contents of this news release."),
        au6("ABC Files NI 43-101 Technical Report for the Alpha Lithium Project", "has filed the technical report on the Alpha "
            "Lithium Project. The Report was prepared by the following Qualified Persons; Alex Haluszka P. Geo. of Montrose "
            "Environmental Solutions Canada Inc., Kevin Piepgrass, P.Geo.")],
       [[("P&E Mining Consultants", ["Fred Brown", "Eugene Puritch"])], [("Moose Mountain Technical Services", ["Sue Bird"])],
        [("P&E Mining Consultants", ["Eugene Puritch"])],
        [("Montrose Environmental", ["Alex Haluszka", "Kevin Piepgrass"])]])
    eq("1.0.6 not authors: laboratory work, the people a QP supervised; a closing quote ends a sentence",
       [au6("ABC Files NI 43-101 Feasibility Study for the Alpha Mine", "has filed the feasibility study technical report on the "
            "Alpha Mine, prepared by BBA Inc. All analyses used for the Resource Estimates were performed by ALS Minerals "
            "Laboratories."),
        au6("ABC Files NI 43-101 Technical Report for the Alpha Mine", "has filed the technical report on the Alpha Mine. The MRE "
            "was prepared by Warren Black, M.Sc., P.Geo. and Tyler Acorn, M.Sc., of APEX Geoscience Ltd under the supervision of "
            "the Qualified Person (\"QP\"), Michael Dufresne, M.Sc., P.Geo., President of APEX Geoscience Ltd."),
        au6("ABC Files NI 43-101 Feasibility Study for the Alpha Gold Project", "has filed the feasibility study technical report "
            "on the Alpha Gold Project, prepared by Roma Oil and Mining Associates Limited. \"With the engagement of Omega "
            "Advisers Limited, with a mandate to secure project debt financing, we have visibility to the funding.\" NI 43-101 "
            "Feasibility Study Highlights follow.")],
       [[("BBA", [])], [("APEX Geoscience", ["Michael Dufresne"])], [("Roma Oil and Mining Associates", [])]])
    eq("no report words", analyse("ABC Closes Private Placement", "ABC closed a private placement." + fill)["rows"], [])
    print("technical: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test("-v" in sys.argv) else 0)
