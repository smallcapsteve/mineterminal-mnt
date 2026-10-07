"""Resource estimates extractor, facts-store version (RES_V1). Third of the three rebuilds.

Replaces portal/resource_extract.py as the source of /resource-estimates once it passes the accuracy
gate. The measured baseline for the live reader (2026-09-17, 642 tagged auto-approved releases):

  rows on the page   179 releases, one row each, categories hidden in a JSON column
  finds a table in   226 of 642, nothing in 416 -- and 116 of those 416 carry a category word,
                     a tonnage and a grade, so the figures are there and are not being read
  project            missing on 60 of 226
  mre_type           169 Update against 57 Maiden, which is not what the releases say

What this reader does differently:

  1. ONE ROW PER DEPOSIT PER CATEGORY (Justin, 2026-09-17). Goldgroup states four deposits with four
     categories each in a single table; West Red Lake states two deposits; Orogen puts the deposit
     inside the category cell ("Inferred Ermitano"). One row per release flattened all of it.
  2. FOUR SHAPES, NOT ONE. A release states its figures as a table flattened to one cell per line, or
     as a whole row on one line, or in prose, or only in the headline -- Nord Resources' entire body
     is a single sentence and every figure is in the headline. All four are read.
  3. BACKGROUND IS MARKED, NOT DROPPED (Justin, 2026-09-17). Adyton restates a 2021 Feni Island
     resource beside the 2026 Gameta one; both are published and only one is news.
  4. NO INVENTED FIGURES. Where the column mapping cannot be established the row is still emitted with
     its deposit and category and no numbers, rather than numbers guessed from magnitude.
  5. NOTHING IS A ROW WITHOUT A CATEGORY AND A FIGURE. 263 of the 642 tagged releases -- filings with
     no numbers, drill programmes, "we have engaged a consultant to update the estimate" -- state no
     estimate at all, and the right answer for them is no rows.

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per row (ordinal 0..n-1)
to_prediction(records) -> dict|None    what the accuracy judge compares

1.0.20 (2026-09-27): the release's project onto the shared project-name helper portal/project_names.py,
conservatively (like Exploration 1.2.2, Production and Drill Results 1.0.6). release_project stays the first choice.
The helper (PN.projects: its main project first) only
  - fills a blank: with a project the headline names (not when the headline names a second project, not a company
    name, not a cut-off fragment -- "Lawrence" of "Silver Bell-St. Lawrence", "Recuperada" of "Nueva Recuperada"), or
    else with the helper's main project when it is also PN.primary, project-level, in the opening text, written
    before Project/Property/Mine..., at least twice as common as any other project, and the headline is not a
    company-wide one (reserves and resources statements, production, results, guidance, several projects, royalties);
  - rewrites 1.0.19's name in the text's own spelling when it is the same project ("ZEUS LITHIUM" -> "Zeus Lithium",
    "O'Brien gold" -> "O'Brien", "CASTELO DE SONHOS" -> "Castelo de Sonhos");
  - replaces a name that is no project -- one starting in lower case ("ir Los Ricos North", "wholly-owned
    Diablillos") or one the helper will not read as a name ("Mpama South as the") -- with a project-level name that
    shares a word with it or that the headline names.
  Rows without their own deposit take the project, as before. The fingerprint also covers the helper.

1.0.22 (2026-09-30, ACC150 fix): what is not a row of the release's own estimate is dropped, and tables are read more
fully. Measured on the ACC150 labels: in-tag rows right 79.5% -> 96.8%, row recall 16.6% -> 22.1%.
  Not rows (dropped one by one, in _not_rows):
  - another company's deposit (guide section 1): judged from the words before the row's figures (for a table, before
    the table) -- analogue / neighbouring / bordering / "near the known" / "within N km of" / comparison wording,
    "cannot verify", "not indicative", a "Source:" footnote, a list of the belt's "notable deposits" (its whole
    paragraph), and another company named as the owner: "X's [Name] project", "X Corp. has / announced / where",
    "(X, <date>)", "(X News Release", "see X's news release", "X's filings / website" (also just after the figures),
    a ticker that is not the issuer's. The issuer's names (and a company the headline reports on, unless the
    headline places it next door or as an investee) never count; royalty and stream releases are exempt;
  - Total lines of a table (a sum of rows already published; none ever matched a label);
  - a tonnage under 1,000 t (a grade or a figure in thousands read as tonnes) -- the tonnage, not the row;
  - a row with neither a deposit nor a tonnage (contained metal from a portfolio or summary sentence);
  - a higher-grade subset ("the high-grade Core Zone, which has ...", guide section 4) and a bound ("in excess of");
  - the same tonnage and grades copied under a second category (the copy whose category has its own row);
  - a tonnage-less summary row whose figures a full row of the same deposit and category already states;
  - "4,100 tonnes per day" (a throughput); a category after "converting ... to" (where metal moved, not a label).
  Deposit names: a column label or unit run, a date, a footnote marker ("Gold3,4", "(2)"), a category ("Beta M&I"),
  a dollar figure, a metal alone, a sentence fragment ("Ontario. The newly acquired", "... at a") or a leading digit
  is no deposit; the row takes its prose project or the release's project instead. A country / province / state
  under a deposit heading is the table's location column, not a deposit. A metal symbol inside a name is no metal
  ("La Colorada"). "Koula (Open Pit)" is not wrapped in the project name again.
  Categories: "Indicated & Measured" / "Probable & Proven", "M&I" in prose (not the '("M&I")' definition), "Proven +
  Probable" in a total line, and a label the PDF wrapped ("Sub-total Proven and" / "Probable ...") are one category.
  Tables: the category on its own line with all its cells on the next line; "<Deposit> <Category> <cells>" rows; a
  one-line header grouped into columns ("Tonnes Au Grade Ag Grade Contained Au ..."); "(000)", "('000)", "(million)",
  "xMillion", "x billion", "M Ozs" unit headers applied; ounces and pounds columns are always contained metal;
  "eU3O8" and an "As" column are metals; a footnote digit glued to a label ("Resource1 54 ...") is no cell.
  Prose: "metric tonnes", "0.85 g/t of gold" (the metal after "of"), "as well as an Indicated" (not a trailing
  label), a decimal the PDF split ("6. 1 million tonnes").
  Grades with no metal take the release's only precious (g/t, oz) or base (%, lb) metal, else are not published.
  A row without its own cut-off takes the cut-off stated nearest to it (after de-duplication) rather than the
  release's first. Column and unit parsing is cached (pure functions of the label): about 2x faster.
  Technical (portal/extractors/technical.py) calls analyse() through a function-level import that its fingerprint
  does not follow: its resource summary changes with this version while its code_sha does not.

1.0.23 (2026-10-01, FIX2): outside the tag the reader wrote rows for releases whose news is something else. Measured on
the fresh outside-tag samples (all finds, no admission rule): conf3 rows right 72.3% -> 98.9%, conf4 89.6% -> 99.2%.
  Whose figures (_wh_context / _wh_whose): what the figures' own sentence -- or, when it names nobody ("There is an
  additional Indicated Resource of ..."), the one before it in the same paragraph -- says last before them decides.
  The issuer (its dateline names and tickers, "the Company", "our"), its own projects (named in the headline, or as
  "its / the Company's / 100%-owned / an interest in the / owns the / acquire the" X project, a defined term, a
  company it takes over) and "The project ..." for one of them point to the issuer; a neighbour wording ("the
  adjacent X project", "The nearby X deposit"), a distance from our ground ("located 4 km south of the Licenses",
  "35km east of the Mt Venn Project", "located adjacent to Sitka's RC Gold project") with a deposit named in passing
  in front of it, another company as the owner ("X's deposit", "held / owned / operated by X", "X owns", "a joint
  venture between X and Y", "the Y deposit of X Mining", 'X Inc. ("ABC") Y project', "X Resources recently
  announced", a ticker or a website that is not the issuer's), a deposit the release places next to its ground and
  names again as a sentence's subject, a list of notable / worldwide deposits, and a hedge ("reportedly", "is
  reported to include") point to somebody else. A link or a report credit to somebody else right after the figures
  does too. When the figures' own sentence points to the issuer, a company named nearby (1.0.22's window) no longer
  drops the row. Royalty and stream releases (headline, a royalty company, an issuer holding a royalty, a royalty-heavy
  opening -- not an NSR a deal grants, not a sediment stream) stay exempt.
  Not rows: an exploration target (and a tonnage that is one end of a range); a subset after a lead-in that names it
  ("A high-grade subset ... consists of: o ...; and o ...", "Included within the global resource is ..."); a deposit
  named by its owner ("X Lithium's"); one figure of one category under two names (the company total under the
  release's project and the footnote under the project it comes from: the named one stays).
  Categories: "indicated and inferred" / "Indicated plus Inferred" stated as one figure is a Total row (kept when it
  has a tonnage, dropped when it has none).
  Prose: the tonnage written right in front of its category is its own ("16 Mt indicated grading ... 34 Mt inferred",
  "270 kt of Proven Mineral Reserves", "a 5.0 million tonnes Indicated Mineral Resource ..."), with the grades of its
  own clause; "totals 1,687,000 tonnes" (the words in between hold no digit); tons that reconcile with the stated
  ounces as tonnes are tonnes; "0.015% molybdenum", "0.33 g/t platinum" read in full; "ounces gold equivalent at
  0.99 g/t" is AuEq; "669 ppm lithium" is Li. A row that states only contained metal joins the one row of its deposit
  and category that states the tonnage.
  Names: a bullet list's project from its lead-in ("estimates for the Porvenir Project, effective ...:"); an owner in
  front of a name ("TDG Gold's AuWEST"), a trailing verb ("Cameron Lake Deposit hosts"), an oxide formula ("Ho2O"),
  "Tonnage Cg In-situ", "Feasibility Study", a headline verb ("Intersect Broad", "UPDATE KUBI GOLD") and
  "Intellectual Property" are no deposit. A headline about something else (a director, a conference, a financing, a
  share issue, a drill rig, financial statements) does not announce an estimate its opening paragraph describes.
  Technical (portal/extractors/technical.py) calls analyse(): its resource summary changes with this version.

1.0.23 (2026-10-01, FIX3): on the full release text (the box reads it whole; the graders saw cut text) FIX1/FIX2 lost
47 tagged releases the live reader showed (and ~1,360 untagged ones); 45 of 47 get rows again, the two left are a
neighbour's deposit and a per-metal company total.
  Tables whose rows carry only a name (read_grids): the category printed over a column group ("Indicated | Inferred"
  over "Tonnes Grade Ounces" twice, or "Indicated" / "Inferred" on lines of their own), as a heading over a block
  ("Indicated Resources", "Total Proven and Probable Gold Mineral Reserves"), in the caption ("Table 1: Inferred
  resource statement") or on the block's first row ("Measured Kappa ..." then "Lambda ..."); rows one per line,
  one cell per line, or cells under a name the PDF wrapped ("High Grade Oxide and / Transitional (>0.25% / Cu)").
  A column group per year or "Current / Previous" takes the current one; rows named by their date take the latest;
  a heading "Compared to ..." and a price or cut-off sensitivity table are not the estimate; a table "as at" the year
  before is background; a combined heading over rows that "Total Proven" / "Total Probable" lines close files each
  row under its part. Total lines (also "Theta Total") stay out. Every row needs its tonnage; the header must map to
  exactly one tonnage column per group, nothing but a cut-off in front, the same columns in every group.
  Headers: labels that wrap across lines, each ending at its unit ("Tonnes (Mt) Ag (g/t) Contained / Ag (Moz) ...");
  a label line over its unit line ("Tonnes" / "kt" / "Grade" / "g/t Au"); labels over units ("kt g/t Au koz Au");
  metals over their column pairs ("Gold Copper" over "Grade (g/t) Ounces (millions) ..."); units "g/tonne",
  "(t*1000)", "(1000's)", "',000", "kozs", "TrOz", "Ktons", "K tons" (short), "oz/ton"; "Cg" (graphitic carbon);
  "Au Eq*" is AuEq.
  Whose figures: a company named as a landmark the issuer's ground is placed by ("100 km northwest of X's Y mine.")
  owns no figures; a cue separated from the figures by a section heading ("About X", "Notes") does not count; a
  table's window starts at the table, not at the paragraphs above it; the sentence that introduces a table owns it.
  Prose: "stand at / stood at / increased to" read the contained metal that follows; what follows "including" is a
  part of the figure already read; a release whose only figures are prose totals with no deposit and no tonnage
  ("Measured & Indicated Total Resource of 537,300 ounces of gold") keeps them (not changes, deltas, sensitivities); a
  summary that repeats a table row (an equivalent's figure, or one rounded to two figures) is that row.

1.0.24 (2026-10-04, FIX5): deposit names and second-metal grades, measured on the ACC150c dev half (deposit P/R
74.4/67.8 -> 90.4/86.3, grade 77.1/73.4 -> 87.2/83.4, rows unchanged in number and right more often).
  Grades: a deposit heading the PDF printed between a header and its rows ("kt g/t g/t k oz k oz" / "Alpha Sur 1" /
  "(Open pit)") is no part of the header, so a table's second metal keeps its column; one tonnage stated once per metal
  ("... 8.85 g/t Au (1,813,000 tonnes), as well as ... 7.33 g/t silver (1,813,000 tonnes)") is one row with both grades;
  a graphite deposit's % carbon grade is Cg; "MoO 3" / "V 2O5" (a subscript set apart) are MoO3 / V2O5.
  Deposits: a column label ("Content", "Deposit and Category", "Mineralization Type", "In-Situ Graphite (kt)") is no
  deposit; a caption "<Owner> Corp. - <Name> Project" names the project; a prose row with no name takes the one its own
  sentence gives ("Alpha has Proven and Probable reserves of ...", "estimate at Gamma consisting of ...", "Delta deposit -
  ...") or, failing that, one of the three sentences before it in the paragraph -- and that own-sentence name outranks
  the release's project; a block's lead row name ("Alpha Mexico Proven ...") carries to the rows below it; a heading
  wrapped over lines ("Beta" / "Norte 1" / "(Open Pit)") is joined; a commodity after a project's name ("Alpha Gold",
  "Beta Energy Metals") is dropped.
  Tonnes: "0.6 7 million tonnes" (a decimal the PDF split) is 0.67 million.

Self-tests: python3 -m portal.extractors.resources
"""
from __future__ import annotations

import bisect
import functools
import re
import unicodedata

from portal import facts as F
from portal import project_names as PN   # 1.0.20: the shared project-name helper
from portal import fingerprint as FP     # 1.0.21: fingerprints follow exactly the helper code this reader runs

NAME = "resources"
VERSION = "1.0.24"  # 2026-10-01: whose figures, read sentence by sentence; targets, subsets, combined categories; full-text losses fixed; 2026-10-04 FIX5: deposit names (column labels, owner captions, the figures' own or previous sentence, a block's lead name, wrapped headings, commodity tails) and second-metal grades (header past a deposit heading, one tonnage per metal, Cg, MoO3), split decimals; rev b: a pronoun or "Company's" is no deposit name
KIND = "resource_estimate"
TAG = "Resource Estimates"
MAX_ROWS = 40

# ------------------------------------------------------------------ vocabulary
# canonical category -> the spellings that mean it, longest first at match time
_CAT_CANON = [
    # 1.0.22: "Indicated & Measured" and "Probable & Proven" are the same two categories, written backwards
    ("Measured & Indicated", r"measured\s*(?:&|and|\+|,)\s*indicated|indicated\s*(?:&|and|\+)\s*measured|"
                             r"m\s*(?:&|\+)\s*i\b"),
    ("Proven & Probable", r"prove[nd]\s*(?:&|and|\+)\s*probable|probable\s*(?:&|and|\+)\s*prove[nd]|p\s*(?:&|\+)\s*p\b"),
    ("Measured", r"measured"),
    ("Indicated", r"indicated"),
    ("Inferred", r"inferred"),
    ("Proven", r"prove[nd]"),
    ("Probable", r"probable"),
    ("Total", r"total|combined|grand\s+total|global"),
]
_CAT_ALT = "|".join("(?:%s)" % p for _, p in _CAT_CANON)

# metal names and symbols -> the symbol the page shows
_METAL = {
    "gold": "Au", "silver": "Ag", "copper": "Cu", "lead": "Pb", "zinc": "Zn", "nickel": "Ni",
    "cobalt": "Co", "antimony": "Sb", "tin": "Sn", "tungsten": "W", "molybdenum": "Mo",
    "uranium": "U3O8", "lithium": "Li2O", "palladium": "Pd", "platinum": "Pt", "rhodium": "Rh",
    "iron": "Fe", "manganese": "Mn", "vanadium": "V2O5", "graphite": "C", "caesium": "Cs2O",
    "cesium": "Cs2O", "tantalum": "Ta2O5", "gallium": "Ga", "niobium": "Nb2O5", "phosphate": "P2O5",
    "potash": "KCl", "scandium": "Sc2O3", "titanium": "TiO2", "chromium": "Cr2O3",
    "rare earth": "TREO", "rare earths": "TREO", "bismuth": "Bi", "tellurium": "Te",
    "platinum group": "PGE", "sulphur": "S", "sulfur": "S", "barite": "BaSO4", "fluorspar": "CaF2",
    "silica": "SiO2",
}
_SYMBOLS = ("Au", "Ag", "Cu", "Pb", "Zn", "Ni", "Co", "Sb", "Sn", "W", "Mo", "U", "U3O8", "Li",
            "Li2O", "LCE", "Pd", "Pt", "Rh", "Ir", "Ru", "Os", "Fe", "Mn", "V", "V2O5", "TREO",
            "TREO", "REO", "Nd2O3", "Pr6O11", "Dy2O3", "Tb4O7", "NdPr", "Cs2O", "Ta2O5", "Ga",
            "Nb2O5", "P2O5", "KCl", "Sc2O3", "TiO2", "Cr2O3", "Bi", "Te", "Cd", "S", "C", "PGE",
            "PGM", "3E", "4E", "6E", "BaSO4", "CaF2", "Zr", "Hf", "Be", "Sr", "Y", "La", "Ce",
            # Troy Minerals' 98.91% SiO2 is a high-purity silica grade, not an impossible one (1.0.19)
            "SiO2", "WO3",
            "eU3O8",   # 1.0.22: a gamma-probe uranium grade
            "Cg",      # 1.0.23 FIX3: graphitic carbon, a graphite deposit's grade ("4.50% Cg")
            "MoO3")    # FIX5: molybdenum trioxide, as a molybdenum grade is often stated ("234.6 ppm MoO3")
# the oxide each element is reported as, for bodies that lost the subscript
_OXIDE = {"Li": "Li2O", "Cs": "Cs2O", "Ta": "Ta2O5", "Nb": "Nb2O5", "V": "V2O5", "U": "U3O8",
          "P": "P2O5", "Ti": "TiO2", "Sc": "Sc2O3", "Cr": "Cr2O3", "Nd": "Nd2O3", "Pr": "Pr6O11",
          "Dy": "Dy2O3", "Tb": "Tb4O7", "W": "WO3", "Sn": "SnO2", "Mo": "MoO3", "Be": "BeO",
          "Zr": "ZrO2", "Al": "Al2O3", "Si": "SiO2", "Fe": "Fe2O3", "Mn": "MnO"}
_EQ_SUFFIX = re.compile(r"(?i)^([A-Za-z0-9]{1,6})[-\s]?eq(?:uivalent)?$")

_TONNAGE_WORD = re.compile(r"(?i)\b(tonnage|tonnes|tonne|tons|ton|mass|ore|material|quantity|"
                           r"k\s*tonnes|m\s*tonnes|kt|mt)\b")
_CLASS_WORD = re.compile(r"(?i)^\s*(classification|class|category|categories|resource\s+category|"
                         r"confidence|type|zone|deposit|area|domain|pit)\s*:?\s*$")

# unit -> (kind, multiplier to the base the page stores)
#   tonnage base = tonnes, contained mass base = tonnes, contained count base = troy ounces
_TONNAGE_UNITS = {
    "t": 1.0, "tonne": 1.0, "tonnes": 1.0, "mt": 1e6, "kt": 1e3, "000s": 1e3, "000": 1e3,
    "k": 1e3, "m": 1e6, "kilotonnes": 1e3, "megatonnes": 1e6, "million tonnes": 1e6,
    "thousand tonnes": 1e3, "ktonnes": 1e3, "mtonnes": 1e6, "ton": 0.90718474, "tons": 0.90718474,
    "short tons": 0.90718474, "st": 0.90718474, "kshort": 907.18474,
}
_GRADE_UNITS = {"%": "%", "g/t": "g/t", "gpt": "g/t", "g per tonne": "g/t", "ppm": "ppm",
                "g/tonne": "g/t", "grams/tonne": "g/t", "grams per tonne": "g/t",   # 1.0.23 FIX3
                "oz/ton": "oz/t", "oz au/ton": "oz/t", "oz ag/ton": "oz/t",
                "ppb": "ppb", "oz/t": "oz/t", "opt": "oz/t", "kg/t": "kg/t", "g/m3": "g/m3",
                "lb/t": "lb/t", "cpht": "cpht", "ct/t": "ct/t"}
_CONTAINED_UNITS = {
    "oz": ("oz", 1.0), "ozs": ("oz", 1.0), "ounces": ("oz", 1.0), "troy ounces": ("oz", 1.0),
    "koz": ("oz", 1e3), "k oz": ("oz", 1e3), "moz": ("oz", 1e6), "m oz": ("oz", 1e6),
    "m ozs": ("oz", 1e6), "k ozs": ("oz", 1e3),   # 1.0.22
    "troz": ("oz", 1.0), "tr oz": ("oz", 1.0),    # 1.0.23 FIX3: "Ag TrOz (000's)", "(kozs)"
    "kozs": ("oz", 1e3), "mozs": ("oz", 1e6),
    "lb": ("lb", 1.0), "lbs": ("lb", 1.0), "pounds": ("lb", 1.0), "mlb": ("lb", 1e6),
    "mlbs": ("lb", 1e6), "m lbs": ("lb", 1e6), "klb": ("lb", 1e3), "klbs": ("lb", 1e3),
    "kt": ("t", 1e3), "mt": ("t", 1e6), "t": ("t", 1.0), "tonnes": ("t", 1.0), "kg": ("kg", 1.0),
    "carats": ("ct", 1.0), "mct": ("ct", 1e6),
}


def metal_of(text):
    """('Au', False) for gold, ('CuEq', True) for a copper-equivalent, None for anything else."""
    s = re.sub(r"[()\[\].,;:*]", " ", (text or "")).strip()     # (1.0.23 FIX3: "Au Eq*" -- a footnote star)
    if not s:
        return None
    m = _EQ_SUFFIX.match(s.replace(" ", ""))
    if m:
        base = m.group(1)
        for sym in _SYMBOLS:
            if sym.lower() == base.lower():
                return (sym + "Eq", True)
        low = base.lower()
        if low in _METAL:
            return (_METAL[low] + "Eq", True)
        return None
    low = s.lower()
    if low in _METAL:
        return (_METAL[low], False)
    for sym in _SYMBOLS:
        if sym.lower() == low:
            return (sym, False)
    words = low.split()
    if len(words) <= 3:
        for w in words:
            if w in _METAL:
                return (_METAL[w], False)
            for sym in _SYMBOLS:
                if sym.lower() == w:
                    return (sym, False)
    return None


# ------------------------------------------------------------------ text
_WS = re.compile("[ \\t\\xa0\\u2000-\\u200b\\u202f\\u205f\\u3000]+")


def clean(text: str) -> str:
    """Normalise punctuation and spacing WITHOUT touching line structure.

    The management reader folds single newlines away, because a release lifted out of a PDF wraps
    mid-sentence. Here the opposite is true: a table reaches us as one cell per line, so the line
    breaks carry the table and must survive."""
    t = unicodedata.normalize("NFKC", text or "")
    for dash in (0x2010, 0x2011, 0x2012, 0x2013, 0x2212):
        t = t.replace(chr(dash), "-")
    t = t.replace(chr(0x2014), " - ").replace(chr(0xad), "")
    t = t.replace(chr(0x2018), "'").replace(chr(0x2019), "'")
    t = t.replace(chr(0x201c), '"').replace(chr(0x201d), '"')
    t = t.replace(chr(0xfffc), " ")
    t = re.sub(r"\r\n?", "\n", t)
    t = _WS.sub(" ", t)
    # "0.85% Li" / "2" / "O" is one grade, not lithium. A PDF puts the subscript on its own line.
    t = re.sub(r"([A-Za-z])\s*\n\s*(\d)\s*\n\s*([A-Z][a-z]?\d?)(?=\b)", r"\1\2\3", t)
    t = re.sub(r"\b([A-Z][a-z]?)\s*\n\s*(\d[A-Z][a-z]?\d*)(?=\b)", r"\1\2", t)
    # Imagine Lithium's body lost the subscript altogether and left "0.85% Li" on one line and
    # "O in the Indicated category" on the next. A grade of lithium metal and a grade of lithium
    # oxide are different numbers, so the element is restored to the oxide the industry reports.
    t = re.sub(r"\b([A-Z][a-z]?)\s*\n\s*\d?O\d?(?=\b)",
               lambda m: _OXIDE.get(m.group(1), m.group(1)), t)
    # FIX5: an oxide whose subscript the PDF set apart on the same line: "234.6 ppm MoO 3", "0.34% V 2O5"
    t = re.sub(r"\b(V|U|Li|Cs|Ta|Nb|Mo|W|Ti|Sc|Cr|Nd|Dy|Tb|Pr|Be|Sn) (\d)O(\d?)\b", r"\1\2O\3", t)
    t = re.sub(r"\b(MoO|WO|TiO|SnO|BeO) (\d)\b", r"\1\2", t)
    return "\n".join(ln.strip() for ln in t.split("\n"))


def lines_of(text: str) -> list:
    return [ln for ln in clean(text).split("\n")]


def reflow(text: str, min_len: int = 45) -> str:
    """Rejoin lines that a PDF wrapped mid-sentence, leaving table cells alone.

    Patriot's resource statement runs across three lines, and splitting on newlines before reading
    it meant the sentence never existed -- two of the three releases this reader missed were that
    one bug. A wrapped line is long and ends without punctuation; a table cell is short, so only
    lines of at least min_len characters absorb the line below them."""
    out = []
    for ln in text.split("\n"):
        if (out and out[-1] and ln and len(out[-1]) >= min_len
                and not re.search(r"[.;:!?]$", out[-1]) and not _RE_BARE_UNIT.match(ln)):
            out[-1] = out[-1] + " " + ln
        else:
            out.append(ln)
    return "\n".join(out)


_RE_NUM = re.compile(r"(?i)^[<>~]?\s*\(?\s*(-?\d[\d,\s]*(?:\.\d+)?)\s*\)?\s*"
                     r"(%|g\s*/\s*t|gpt|ppm|ppb|oz\s*/\s*t|opt|kg\s*/\s*t|"
                     r"k?\s*oz|m\s*oz|ounces|m?\s*lbs?|pounds|kt|mt|t|tonnes|kg|m|km|ft)?\s*$")
_RE_BARE_UNIT = re.compile(r"(?i)^\s*\(?\s*("
                           r"%|g\s*/\s*t|gpt|ppm|ppb|oz\s*/\s*t|opt|kg\s*/\s*t|"
                           r"[km]?\s*ozs?|ounces|troy\s+ounces|tr\.?\s*ozs?|m?\s*lbs?|pounds|k?\s*t|mt|"   # 1.0.22: ozs
                           r"tonnes?|000s?|k|m|kg|c\$?\s*/\s*t|us\$?\s*/\s*t|\$\s*/\s*t|"
                           r"'000s?|000's|x?\s*millions?|thousands?"   # 1.0.22
                           r")\s*\)?\s*$")


def is_number(line: str) -> bool:
    return bool(line) and bool(_RE_NUM.match(line)) and any(c.isdigit() for c in line)


def number_of(line: str):
    """('6.5', 'mt') for '6.5 Mt'; None when the line is not a bare figure. '-' reads as empty."""
    if not line:
        return None
    if line.strip() in ("-", "--", "n/a", "N/A", "nil", "\u2014"):
        return ("", None)
    m = _RE_NUM.match(line)
    if not m or not any(c.isdigit() for c in line):
        return None
    raw = m.group(1).replace(",", "").replace(" ", "")
    unit = (m.group(2) or "").lower().replace(" ", "") or None
    try:
        float(raw)
    except ValueError:
        return None
    return (raw, unit)


_RE_CAT_LINE = re.compile(r"(?i)^\s*(?:total\s+)?(?P<cat>" + _CAT_ALT + r")"
                          r"\s*(?:mineral\s*)?(?:resources?|reserves?)?"
                          r"(?P<tail>[^\d]{0,40}?)\s*[:\-]?\s*$")


def category_of(line: str):
    """('Indicated', '') for an 'Indicated' cell, ('Inferred', 'Ermitano') when the deposit is in it."""
    if not line or len(line) > 70:
        return None
    m = _RE_CAT_LINE.match(line)
    if not m:
        return None
    raw = m.group("cat")
    canon = None
    for name, pat in _CAT_CANON:
        if re.fullmatch("(?i)" + pat, raw.strip()):
            canon = name
            break
    if canon is None:
        return None
    if canon != "Total" and re.match(r"(?i)^\s*total\b", line):
        canon = canon  # "Total Inferred" is still the Inferred category
    tail = re.sub(r"(?i)\b(mineral|resources?|reserves?|category|categories)\b", " ",
                  m.group("tail") or "")
    tail = re.sub(r"[\*\u2020\u2021\+]+", " ", tail)
    tail = _WS.sub(" ", tail).strip(" ,.;:()-")
    return (canon, tail)


# ------------------------------------------------------------------ table columns
_RE_CUTOFF = re.compile(r"(?i)\bcut[\s\-]?off\b|\bcog\b|\bnsr\s*cut")
_RE_PAREN = re.compile(r"\(([^)]*)\)")


_TONNE_PHRASE = [
    (re.compile(r"(?i)\b(?:k|thousand)\s+tonn?es?\b"), " kt "),
    (re.compile(r"(?i)\b(?:m|million)\s+tonn?es?\b"), " mt "),
    (re.compile(r"(?i)\btonn?es?\s*0{3}'?s?\b"), " kt "),
    (re.compile(r"(?i)\b(?:k|thousand)\s+tons\b"), " kshort "),    # 1.0.23 FIX3: thousands of short tons
    (re.compile(r"(?i)\bktons\b"), " kt "),                           # 1.0.23 FIX3: "Ktons", kilotonnes
]


@functools.lru_cache(maxsize=8192)   # 1.0.22: a pure function of the label, and the hottest one on big tables
def _unit_in(s):
    """(kind, unit, mult) for the first unit token in s, longest match first."""
    low = " " + re.sub(r"[()\[\]]", " ", (s or "").lower()) + " "
    low = low.replace("/ ", "/").replace(" /", "/")
    # "K tonnes" is a thousand tonnes, not a tonne -- fold the phrase before any unit is matched
    for rx, rep in _TONNE_PHRASE:
        low = rx.sub(rep, low)
    for key in sorted(_GRADE_UNITS, key=len, reverse=True):
        if re.search(r"(?<![\w/])" + re.escape(key) + r"(?![\w/])", low):
            return ("grade", _GRADE_UNITS[key], 1.0)
    for key in sorted(_CONTAINED_UNITS, key=len, reverse=True):
        if re.search(r"(?<![\w/])" + re.escape(key) + r"(?![\w/])", low):
            u, mult = _CONTAINED_UNITS[key]
            # "('000 oz gold)" is thousands of ounces: Thunder Gold's 514 was 514,000 oz, and the
            # arithmetic check then threw the whole row away as a shifted mapping (1.0.19)
            if mult == 1.0 and re.search(r"(?<![\d,.])'?000'?s?(?![\d,.])", low):
                mult = 1e3
            return ("mass", u, mult)
    for key in sorted(_TONNAGE_UNITS, key=len, reverse=True):
        if re.search(r"(?<![\w/])" + re.escape(key) + r"(?![\w/])", low):
            return ("mass", "t", _TONNAGE_UNITS[key])
    return (None, None, 1.0)


def parse_col(label: str) -> dict:
    """One table column: what it holds, for which metal, in what unit. (A fresh dict every call: callers edit it.)"""
    return dict(_parse_col(label))


@functools.lru_cache(maxsize=8192)
def _parse_col(label):
    return tuple(_parse_col_uncached(label).items())


def _parse_col_uncached(label):
    col = {"label": label, "kind": "other", "metal": None, "eq": False, "unit": None, "mult": 1.0,
           "paren_unit": False}
    s = (label or "").strip()
    if not s:
        return col
    if _CLASS_WORD.match(s):
        col["kind"] = "class"
        return col
    inner = " ".join(_RE_PAREN.findall(s))
    outer = _RE_PAREN.sub(" ", s)
    # 1.0.22: "Pounds ('000)", "Tons ('000)": a bracket holding only a thousands (or millions) marker scales the
    # unit outside it. Read as a unit of its own, "('000)" made every such column a tonnage in thousands.
    scale = 1.0
    if inner and _RE_THOUSANDS.match(inner):
        scale = 1e6 if re.search(r"(?i)million", inner) else 1e3
        inner = ""
    kind, unit, mult = _unit_in(inner if inner else outer if scale != 1.0 else s)
    mult *= scale
    if kind is None and scale != 1.0:
        kind, unit, mult = "mass", "t", scale      # a bare "(000)" column: tonnes, in thousands
    col["paren_unit"] = bool(inner and kind) or (scale != 1.0 and bool(kind))
    if kind is None and inner:
        kind, unit, mult = _unit_in(outer)
    met = metal_of(outer) or metal_of(inner)
    # 1.0.22: an "As (ppm)" column is arsenic; "as" is too common a word to be a symbol anywhere else
    if not met and re.fullmatch(r"\s*As\s*", outer or ""):
        met = ("As", False)
    if met:
        col["metal"], col["eq"] = met
    col["unit"], col["mult"] = unit, mult
    if _RE_CUTOFF.search(s):
        col["kind"] = "cutoff"
    elif kind == "grade":
        col["kind"] = "grade"
    elif kind == "mass":
        # a mass column with a metal on it is contained metal; without one it is the tonnage
        # (1.0.22: ounces and pounds are always metal)
        if col["metal"] and not _TONNAGE_WORD.search(outer) or unit in ("oz", "lb", "ct"):
            col["kind"] = "contained"
            if unit == "t" and mult == 1.0 and re.search(r"(?i)\b(kt|mt)\b", s):
                pass
        else:
            col["kind"] = "tonnage"
            col["metal"] = None
    # 1.0.22: "Tonnes (million)", "xMillion Tonnes", "Tonnes (000)" scale the tonnage column. Only "000", "K" or
    # "M" in a unit were read before, and a 423.4 million tonne estimate reached the page as 423.4 t
    if col["kind"] in ("tonnage", "contained") and col["mult"] == 1.0 \
            and re.search(r"(?i)[*x\u00d7]\s*1,?000(?:,?000)?\b", s):    # 1.0.23 FIX3: "Tonnage (t*1000)", "(x1,000)"
        col["mult"] = 1e6 if re.search(r"(?i)[*x\u00d7]\s*1,?000,?000\b", s) else 1e3
    if col["kind"] == "tonnage" and col["mult"] == 1.0:
        if re.search(r"(?i)(?:\bx\s*|\b)millions?\b", s):
            col["mult"] = 1e6
        elif re.search(r"(?i)\bthousands?\b|(?<![\d,.])'?000'?s?(?![\d,.])", s):
            col["mult"] = 1e3
    elif col["kind"] == "contained" and col["mult"] == 1.0 and col["unit"] in ("oz", "lb"):
        if re.search(r"(?i)(?:\bx\s*|\b)billions?\b", s):
            col["mult"] = 1e9
        elif re.search(r"(?i)(?:\bx\s*|\b)millions?\b", s):
            col["mult"] = 1e6
        elif re.search(r"(?i)\bthousands?\b", s):
            col["mult"] = 1e3
    elif col["kind"] == "other" and not col["unit"] and _TONNAGE_WORD.search(outer) \
            and re.search(r"(?i)(?:\bx\s*|\b)millions?\b", s) and not metal_of(outer):
        col.update(kind="tonnage", unit="t", mult=1e6)
    return col


_HEADER_WORDS = set("""class classification category categories resource resources reserve reserves
mineral tonnage tonnes tonne tons ton grade grades average avg contained metal metals cut cutoff
cut-off off nsr cog quantity total troy ounces ounce oz pounds lbs lb million thousand k m t kt mt
date dated effective unit units per and of the in type zone deposit pit domain area recovery price
equivalent eq net smelter return value estimated rounded density tonnages cog. no. size
location country jurisdiction property orebody lithology facies""".split())   # 1.0.22: the last line


_RE_NUMBERED_BLOCK = re.compile(r"(?i)^\s*(?:pit|zone|block|area|lens|stage|phase|target|domain|"
                                r"pushback|panel|level|shoot)\s+\d{1,3}\s*$")


def _is_header_material(ln: str) -> bool:
    """True when the line is a column label rather than a deposit name or a sentence.

    A keyword test is not enough: 'Mineral Resource Statement - Mt. Jamie Deposit' contains 'Mt'
    and would read as a tonnage column, which is how West Red Lake's second deposit went missing.
    So every word outside the parentheses has to be header vocabulary."""
    if not ln or len(ln) > 60:
        return False
    # "Pit 1" is a block heading, not a column label. Both its words are header vocabulary, so
    # the line was being filed with the header run and McFarlane Lake's two pits never became
    # deposits at all.
    if _RE_NUMBERED_BLOCK.match(ln):
        return False
    if _CLASS_WORD.match(ln) or _RE_BARE_UNIT.match(ln):
        return True
    if re.fullmatch(r"As(?:\s*\([^)]*\))?", ln.strip()):     # 1.0.22: an arsenic column
        return True
    outside = _RE_PAREN.sub(" ", ln)
    words = [w for w in re.split(r"[\s,;:/\\|\-]+", outside.lower()) if w]
    words = [w.strip(".%$()") for w in words]
    words = [w for w in words if w]
    if not words:
        return bool(_unit_in(ln)[0])
    for w in words:
        if w in _HEADER_WORDS or w.isdigit():
            continue
        if metal_of(w) or _unit_in(w)[0]:
            continue
        return False
    return True


_RE_VALUE_COL = re.compile(r"(?i)\bnsr\b|\$|\bvalue\b|recover|density|\bsg\b|specific\s+gravity|strip|"
                           r"\bprice\b|thickness|\bwidth\b")


def build_columns(run: list, n_values: int, one: bool = True) -> list:
    """Map a header run onto n_values data cells, or [] when it cannot be done honestly. (one=False, 1.0.23 FIX3:
    keep every tonnage column, for a table that prints one column group per category.)"""
    _one = _one_tonnage if one else list
    run = [x for x in run if x]
    if not run:
        return []
    # two-row header: every metal on one row, every unit on the next
    tail = []
    k = len(run) - 1
    while k >= 0 and _RE_BARE_UNIT.match(run[k]):
        tail.append(run[k])
        k -= 1
    tail.reverse()
    if len(tail) == n_values and n_values >= 2:
        # XXIX prints the cut-off ("0.15% CuEq", "Cut-Off") between the names and the units; it
        # labels the block, not a column, and taking the last n lines shifted every name by two
        heads = [x for x in run[:k + 1] if not _CLASS_WORD.match(x)
                 and not _RE_CUTOFF.search(x) and not re.search(r"\d", x)][-n_values:]
        if len(heads) == n_values:
            return _one([parse_col(h + " (" + u.strip("() ") + ")")
                         for h, u in zip(heads, tail)])
        return _one([parse_col("(" + u.strip("() ") + ")") for u in tail])

    merged = []
    for ln in run:
        if _CLASS_WORD.match(ln):
            continue
        # "Au Ounces" then "(koz)" is one column. Reading "Ounces" as the unit and "(koz)" as a
        # column of its own made an eighth column out of seven, and the mapping then ran a place
        # out -- RUA Gold's tonnage came back as its contained ounces.
        if _RE_BARE_UNIT.match(ln) and merged \
                and (merged[-1]["unit"] is None or not merged[-1]["paren_unit"]) \
                and (merged[-1]["metal"] or _TONNAGE_WORD.search(merged[-1]["label"])
                     or _RE_THOUSANDS.match(ln) and merged[-1]["unit"]):   # 1.0.22: "Pounds" / "('000)"
            merged[-1] = parse_col(merged[-1]["label"] + " (" + ln.strip("() ") + ")")
            continue
        merged.append(parse_col(ln))
    usable = [c for c in merged if c["unit"]]
    # 1.0.19: a value column this reader cannot parse (Class 1 Nickel's "NSR (C$/t)") holds its place
    # instead of vanishing. Dropping it let a row with one blank cell map eight values onto eight
    # parsed columns, one place out after the gap: Co 0.44% where the table says 0.02%, NiEq 88%,
    # contained Ni and Cu swapped. A row that fits only because a column was dropped cannot say which
    # cell is missing, so it states no figures rather than shifted ones.
    # (a label carrying figures -- "Gold Price $/oz 1,700 1,700 1,500" -- is a note, not a column)
    unparsed = [c for c in merged if not c["unit"] and _RE_VALUE_COL.search(c["label"] or "")
                and not re.search(r"\d", c["label"] or "")]
    if unparsed and len(usable) == n_values:
        return []
    if len(usable) == n_values:
        return _one(usable)
    # the cut-off is often printed once per deposit block rather than once per row
    if len(usable) == n_values + 1:
        without = [c for c in usable if c["kind"] != "cutoff"]
        if len(without) == n_values:
            return _one(without)
        return []
    # A header with more columns than the row has values is a header this reader has not
    # understood. Taking the last n of them drops the leading columns silently, which is how
    # Fireweed's 6.3 Mt of ore came back as 94. Better to state no figures than the wrong ones.
    return []


def _may_reuse(header, last_header, n_values, last_n):
    """Whether the previous row's columns still apply to this one.

    Two cases. Orogen prints a group label between the two halves of one table, so the header run
    in force has no units in it at all and the real header is above both. Canadian Palladium
    prints one header line and then five rows, and by the third the header is out of the look-back
    window -- but the header run has not changed, so the mapping has not either."""
    if n_values != last_n or not last_n:
        return False
    return not header_strength(header) or list(header) == (last_header or [])


def header_strength(run):
    """How many of a header run's lines actually carry a unit.

    Zero means there is no header here -- Orogen prints "Resources (inclusive of reserve)" between
    its reserve rows and its resource rows, and the table's real header is above both. A header
    with units that simply does not fit the row is a different thing: it is this table's header,
    read wrongly, and the previous table's columns must not stand in for it.
    """
    return sum(1 for ln in run if ln and not _CLASS_WORD.match(ln) and parse_col(ln)["unit"])


def _best_columns(cands):
    """Of the mappings that fit, take the one that names the most metals.

    A units-only header maps the columns but leaves every grade unlabelled, and an unlabelled
    grade is a figure with no metal against it -- true, and useless on the page."""
    best, score = [], -1
    for c in cands:
        if not c:
            continue
        sc = sum(1 for x in c if x["metal"])
        if sc > score:
            best, score = c, sc
    best = _borrow_metals(best)
    # Every resource row states a tonnage. A mapping of four columns or more that finds none has
    # not understood the header -- XXIX's 62,706 kt of ore was being read as contained copper.
    if len(best) >= 4 and not any(c["kind"] == "tonnage" for c in best):
        return []
    return best


def _borrow_metals(cols):
    """A table lists its grades and its contained metal in the same order. Where the grade columns
    lost their labels and the contained columns kept theirs, read the metals across."""
    g = [c for c in cols if c["kind"] == "grade"]
    cm = [c for c in cols if c["kind"] == "contained"]
    if g and cm and len(g) == len(cm):
        for a, b in zip(g, cm):
            if a["metal"] is None and b["metal"]:
                a["metal"], a["eq"] = b["metal"], b["eq"]
    return cols


def _one_tonnage(cols):
    """A row states one tonnage. Later mass columns are contained metal, whatever the header lost."""
    seen = False
    for c in cols:
        if c["kind"] != "tonnage":
            continue
        if seen:
            c["kind"] = "contained"
        else:
            seen = True
    return cols


# ------------------------------------------------------------------ table reading
_RE_CAPTION = re.compile(r"(?i)^\s*table\s*\d*[a-z]?\s*[-:.]\s*(.*)$")
_RE_STOP = re.compile(r"(?i)^\s*(notes?\b|notes to\b|qualified person|about \w|forward[\s-]?looking|"
                      r"for (?:further|more) information|on behalf of|neither the\b|source:|"
                      r"cautionary|disclaimer|contact\b)")
_RE_RESERVE_WORD = re.compile(r"(?i)\breserves?\b")
_RE_RESOURCE_WORD = re.compile(r"(?i)\bresources?\b")
_RE_CUTOFF_VAL = re.compile(
    r"(?i)(?:cut[\s\-]?off[^.\n\d]{0,40}?(?P<a>[\d][\d,.]*)\s*(?P<au>%|g\s*/\s*t|gpt|ppm|c?\$?\s*/\s*t)"
    r"|(?P<b>[\d][\d,.]*)\s*(?P<bu>%|g\s*/\s*t|gpt|ppm|c?\$?\s*/\s*t)[^.\n]{0,30}?cut[\s\-]?off)")


def cutoff_in(text: str):
    """'0.8% SbEq' from 'a break-even cut-off grade of 0.8% SbEq'."""
    if not text:
        return None
    m = _RE_CUTOFF_VAL.search(text)
    if not m:
        return None
    val = m.group("a") or m.group("b")
    unit = (m.group("au") or m.group("bu") or "").replace(" ", "")
    after = text[m.end():m.end() + 14]
    met = None
    mm = re.match(r"\s*([A-Za-z][A-Za-z0-9]{0,5}(?:Eq)?)", after)
    if mm:
        got = metal_of(mm.group(1))
        if got:
            met = got[0]
    return (val + unit + (" " + met if met else "")).strip()


_RE_DEP_NOISE = re.compile(
    r"(?i)\b(summary of the|summary of|mineral resource statement|mineral resource estimate|"
    r"resource estimate|mineral resources?|mineral reserves?|resources?|reserves?|statement|"
    r"estimate[sd]?|classification|as at|as of|effective date)\b")


def _is_figure_tok(t):
    """'42,252', '0.42', '393' are figures; '31,' and '2026' in a date are not."""
    t = t.strip("()*,;")
    if not re.fullmatch(r"\d[\d.,]*", t):
        return False
    if re.fullmatch(r"(?:19|20)\d\d", t):
        return False
    return "." in t or "," in t or len(t) >= 3


def deposit_name(line: str):
    """'Rowan Mine Deposit' out of 'Mineral Resource Statement - Rowan Mine Deposit'."""
    if not line or len(line) > 110:
        return None
    s = _RE_CAPTION.sub(r"\1", line)
    s = re.sub(r"(?i)\s*[@(]?\s*(?:at\s+)?[\d.,]+\s*(?:%|g/t|gpt|ppm|c?\$?\s*/\s*t)[^,]{0,30}?"
               r"cut[\s\-]?off\s*\)?\s*$", " ", s)
    s = re.sub(r"(?i)\bcut[\s\-]?off\b.*$", " ", s)
    s = re.sub(r"(?i)[,\-\s]*(?:january|february|march|april|may|june|july|august|september|"
               r"october|november|december)\s+\d{1,2},?\s+\d{4}\s*$", " ", s)
    s = re.sub(r"(?i)[,\-\s]*(?:and\s+)?(?:as\s+)?(?:at|of)\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{0,2},?\s*\d{4}\S*\s*$", " ", s)
    s = re.sub(r"\s*@.*$", " ", s)
    s = re.sub(r"(?i)\([^)]*\b(?:table|subset|inclusive|see)\b[^)]*\)", " ", s)
    s = _RE_DEP_NOISE.sub(" ", s)
    s = re.sub(r"[\*\u2020\u2021]+", " ", s)
    s = re.sub(r"^[\s\-:,.]+|[\s\-:,.]+$", "", s)
    # a trailing digit is a footnote marker ("Auld 3") unless it numbers a block ("Pit 1")
    if not re.search(r"(?i)\b(pit|zone|block|area|lens|stage|phase|target|domain|pushback|"
                     r"panel|level|shoot)\s+\d{1,3}\s*$", s):
        s = re.sub(r"\s+\d\s*$", "", s)
    s = _WS.sub(" ", s).strip(" ,.;:-")
    if len(s) < 2 or len(s) > 70 or s.isdigit():
        return None
    # (1.0.22: a metal name is not a deposit, but "La Colorada" is not lanthanum)
    if _CLASS_WORD.match(s) or metal_of(s) and all(metal_of(w) for w in re.split(r"[\s,/&-]+", s) if w):
        return None
    # "0.15% CuEq" is the cut-off the block was reported at, not the name of a place
    # ... and so is "0.15% & 1.00% CuEq", two cut-offs for a total over two blocks
    if re.fullmatch(r"(?i)[\d.,]+\s*(?:%|g/t|gpt|ppm|c?\$?\s*/\s*t)"
                    r"(?:\s*(?:&|and|/|,)\s*[\d.,]+\s*(?:%|g/t|gpt|ppm|c?\$?\s*/\s*t))*"
                    r"\s*[A-Za-z0-9]{0,6}", s):
        return None
    if s.count("(") != s.count(")"):
        return None
    # "Summary of maiden Mineral Resource Estimate for the Regnault gold deposit" leaves
    # "maiden for the Regnault gold deposit" once the boilerplate is out; the name starts where
    # the lower-case connectives stop.
    while True:
        m = re.match(r"^([a-z][\w'-]*)\s+(?=\S)", s)
        if not m:
            break
        s = s[m.end():]
    s = s.strip(" ,.;:-")
    if len(s) < 2 or len(s) > 70:
        return None
    # a stray units row is not a deposit: "M g/t g/t g/t % % % koz C$/t" reached the page as one
    toks = [t for t in re.split(r"[\s,;|]+", s) if t]
    if not toks:
        return None
    # "Pit 1" and "Zone 2" are names; the numeral on the end of a name is part of the name, and
    # counting it as a figure rejected McFarlane Lake's two pits and left both rows under the
    # block heading above them.
    numbered = len(toks) >= 2 and re.fullmatch(r"\d{1,3}", toks[-1])
    body = toks[:-1] if numbered else toks
    unitish = sum(1 for t in body
                  if _RE_BARE_UNIT.match(t.strip(".,")) or re.fullmatch(r"[\d.,]+", t))
    toks = body or toks
    if unitish * 2 >= len(toks):
        return None
    # "Goldfield (Kemess Underground - East 42,252 0.42 393)" is a row of figures run into a name
    if sum(1 for t in body if _is_figure_tok(t)) >= 2:
        return None
    # a deposit has a name: "new" is what was left of a sentence, not a place
    if not any(t[:1].isupper() for t in toks):
        return None
    # stripping " at Dec 31, 2024" off "Ermitano and at Dec 31, 2024" leaves a dangling "and"
    s = re.sub(r"(?i)[\s,]+(?:and|or|&|with|plus|inclusive)\s*$", "", s).strip(" ,.;:-")
    if len(s) < 2:
        return None
    return s


def _row(deposit, category, source, pos):
    return {"deposit": deposit, "category": category, "tonnes": None, "grades": [], "contained": [],
            "cut_off": None, "basis": "resource", "context": "announced", "source": source,
            "effective_date": None, "pos": pos, "confidence": "high", "_win": ""}


_LB_PER_T = 2204.62262


_PRECIOUS = {"Au", "AuEq", "Pt", "Pd", "Rh", "PGE", "PGM", "3E", "4E", "6E"}


# the richest a resource's average grade can be, in percent -- beyond it the figure is a share, a
# change or a recovery ("46% increase", "50% interest", "Recovery: 81.5% Li2O") (1.0.19)
_MAX_PCT = {"Au": 1.0, "Ag": 5.0, "Pt": 1.0, "Pd": 1.0, "Rh": 1.0, "AuEq": 1.0, "AgEq": 5.0,
            "PdEq": 1.0, "PGE": 1.0, "Li2O": 8.0, "Li": 4.0, "LCE": 20.0, "Cu": 40.0, "CuEq": 40.0,
            "Ni": 25.0, "NiEq": 25.0, "Co": 10.0, "Zn": 60.0, "Pb": 80.0, "Mo": 10.0, "Sn": 30.0,
            "W": 30.0, "WO3": 40.0, "U3O8": 70.0, "Sb": 60.0, "Cs2O": 40.0, "Ta2O5": 10.0,
            "Nb2O5": 20.0, "TREO": 30.0, "V2O5": 10.0}


def _impossible_pct(g):
    if g.get("unit") != "%" or g.get("value") is None:
        return False
    cap = _MAX_PCT.get(g.get("metal"))
    return cap is not None and g["value"] > cap


def _implausible_gpt(g):
    """No resource averages 200 g/t gold, or 5,000 g/t of anything. Sitka's total row came back
    with its 3,829 thousand ounces read as a 3,829 g/t grade (RES 1.0.19)."""
    if g.get("unit") != "g/t" or not g.get("value"):
        return False
    return g["value"] > 5000 or (g.get("metal") in _PRECIOUS and g["value"] > 200)


def _checked(row):
    """Refuse a positional mapping the release itself contradicts (RES 1.0.18, 2026-09-18).

    `build_columns` keeps only the header columns whose unit it can parse, so a column it does not
    understand -- Class 1 Nickel's "NSR (C$/t)", sitting between the grade group and the contained
    group -- vanishes instead of holding its place. The column count can then match the value count
    by coincidence and every value after the gap lands one place out. Two things the release states
    catch it: no ore is 100% metal, and contained metal is tonnage times grade."""
    if any(g["unit"] == "%" and (g["value"] or 0) >= 100 for g in row["grades"]) \
            or any(_implausible_gpt(g) or _impossible_pct(g) for g in row["grades"]):
        row["tonnes"], row["grades"], row["contained"] = None, [], []
        row["confidence"] = "low"
        return row
    t, grades = row["tonnes"], {}
    for g in row["grades"]:
        if g["metal"] and g["value"]:
            grades.setdefault(g["metal"], (g["value"], g["unit"]))
    worst = 1.0
    if t:
        for c in row["contained"]:
            got, want = c.get("value"), None
            g = grades.get(c.get("metal"))
            if not got or not g:
                continue
            if g[1] == "%" and c["unit"] in ("t", "lb"):
                want = t * g[0] / 100.0 * (_LB_PER_T if c["unit"] == "lb" else 1.0)
            elif g[1] == "g/t" and c["unit"] == "oz":
                want = t * g[0] / 31.1034768
            elif g[1] == "g/t" and c["unit"] == "t":
                want = t * g[0] / 1e6
            if want:
                r = got / want
                worst = max(worst, r, 1.0 / r)
    # Within 3x is agreement: contained metal is often quoted after recovery, and the grade is
    # rounded. Beyond 20x nothing about ore explains it and the positional mapping is simply out,
    # so the row states no figures -- including the grades, because a shifted block shifts them
    # too: Class 1 Nickel's 0.44% cobalt is really its nickel-equivalent, and the 88% beside it is
    # a C$/t net smelter return. In between, only the contained block is condemned.
    if worst > 20.0:
        row["tonnes"], row["grades"], row["contained"] = None, [], []
        row["confidence"] = "low"
    elif worst > 3.0:
        row["contained"] = []
        row["confidence"] = "low"
    return row


def _fill(row, cols, vals):
    for c, pair in zip(cols, vals):
        raw, _ = pair
        if raw == "":
            continue
        try:
            v = float(raw)
        except ValueError:
            continue
        if c["kind"] == "tonnage":
            row["tonnes"] = v * c["mult"]
        elif c["kind"] == "grade":
            row["grades"].append({"metal": c["metal"], "value": v, "unit": c["unit"]})
        elif c["kind"] == "contained":
            row["contained"].append({"metal": c["metal"], "value": v * c["mult"], "unit": c["unit"]})
        elif c["kind"] == "cutoff" and row["cut_off"] is None:
            row["cut_off"] = ("%g" % v) + (c["unit"] or "")
    return _checked(row)


def _name_total(r, rows):
    """What a "Total" line in a block of rows sums (RES 1.0.19, Orogen's Ermitano table).

    "Total Reserves" under a Proven row and a Probable row is the Proven & Probable reserve, not a
    category of its own. "Total Inferred" under Inferred rows for two deposits is the two deposits
    together; filing it under the first of them doubled that deposit's Inferred tonnage."""
    block = []
    for k in reversed(rows):
        if k.get("_win") != r.get("_win") or k["source"] != r["source"]:
            break
        block.append(k)
    cats = {k["category"] for k in block}
    if r["category"] == "Total" and r["basis"] == "reserve" and {"Proven", "Probable"} <= cats \
            and "Proven & Probable" not in cats:
        r["category"] = "Proven & Probable"
        return
    if r["category"] in ("Total", "Proven & Probable", "Measured & Indicated"):
        return
    names = []
    for k in reversed(block):
        if k["category"] == r["category"] and k["deposit"] and k["deposit"] not in names:
            names.append(k["deposit"])
    # (FIX5: the rows above may carry their block's lead name; the heading in force over them still counts)
    if len(names) >= 2 and (r["deposit"] in names or r["deposit"]
                            and r["deposit"] in {k.get("_dep0") for k in block if k["category"] == r["category"]}):
        r["deposit"] = " and ".join(names) if len(names) == 2 else ", ".join(names)
        r["category"] = "Total"


# a table under "HISTORICAL RESOURCES" restates old estimates (McFarlane Lake's McMillan total)
_RE_HIST_CAPTION = re.compile(r"(?i)^\s*(?:table\s*\d*[a-z]?\s*[-:.]?\s*)?historic(?:al)?\s+"
                              r"(?:mineral\s+)?(?:resources?|reserves?|estimates?)\b")


def _introduces_historic(para):
    """A paragraph that hands over to a table of historical estimates."""
    return bool(re.search(r"(?i)\bhistoric(?:al)?\s+(?:mineral\s+)?(?:resources?|estimates?)\b", para)
                and re.search(r"(?i)\b(?:below|following|table)\b", para)
                and not re.search(r"(?i)\b(?:supersed\w*|replac\w*)\b", para))


# 1.0.22 ----------------------------------------------------------- table helpers
_RE_THOUSANDS = re.compile(r"(?i)^\s*\(?\s*(?:x\s*)?(?:'?,?000'?s?|1,?000'?s|thousands?|millions?)\s*\)?\s*$")   # 1.0.23 FIX3: 1000's
_RE_EMPTY_CELL = re.compile(r"^(?:-{1,2}|\.|n/?a|nil|\u2014)$", re.I)


def _cells_of(line):
    """[('9.28', None), ...] for a line that is nothing but a row of figures ("9.28 1.39 27.6 0.97 0.33"),
    else []. Dashes are empty cells. A year or a lone footnote number is not a row."""
    toks = line.split()
    if len(toks) < 2 or len(toks) > 30:
        return []
    out = []
    for t in toks:
        if _RE_EMPTY_CELL.match(t):
            out.append(("", None))
            continue
        n = number_of(t)
        if n is None or not n[0]:
            return []
        out.append(n)
    if len([v for v in out if v[0]]) < 2 or all(re.fullmatch(r"(?:19|20)\d\d", v[0]) for v in out if v[0]):
        return []
    return out


# the country, province or state a table's location column prints beside each deposit
_LOCATION_SET = {
    "canada", "usa", "u.s.a", "united states", "mexico", "peru", "chile", "argentina", "bolivia", "brazil", "colombia",
    "ecuador", "guatemala", "honduras", "nicaragua", "panama", "dominican republic", "australia", "new zealand",
    "papua new guinea", "png", "fiji", "indonesia", "philippines", "china", "mongolia", "kazakhstan", "kyrgyzstan",
    "kyrgyz republic", "uzbekistan", "turkey", "t\u00fcrkiye", "greenland", "finland", "sweden", "norway", "ireland",
    "portugal", "spain", "serbia", "bulgaria", "romania", "greece", "armenia", "russia", "south africa", "namibia",
    "botswana", "zimbabwe", "zambia", "tanzania", "kenya", "ghana", "mali", "burkina faso", "c\u00f4te d'ivoire",
    "cote d'ivoire", "ivory coast", "senegal", "guinea", "liberia", "sierra leone", "niger", "nigeria", "morocco",
    "egypt", "ethiopia", "sudan", "eritrea", "madagascar", "mozambique", "drc", "congo", "angola", "saudi arabia",
    "ontario", "quebec", "qu\u00e9bec", "british columbia", "bc", "b.c", "alberta", "saskatchewan", "manitoba", "yukon",
    "nunavut", "newfoundland", "labrador", "newfoundland and labrador", "nova scotia", "new brunswick",
    "northwest territories", "nwt", "nevada", "arizona", "alaska", "idaho", "montana", "utah", "colorado", "wyoming",
    "california", "oregon", "washington", "new mexico", "south dakota", "minnesota", "michigan", "texas",
    "western australia", "queensland", "new south wales", "victoria", "tasmania", "northern territory", "sonora",
    "chihuahua", "durango", "zacatecas", "sinaloa", "jalisco", "oaxaca", "guerrero"}


def _is_location(line):
    s = re.sub(r"[\s,.;:*()\d]+$", "", (line or "").strip()).lower()
    return bool(s) and len(s) <= 40 and s in _LOCATION_SET


def read_tables(ls: list) -> list:
    """Rows from tables that reach us as one cell per line."""
    rows, header, deposit, dep_cut, dep_basis = [], [], None, None, None
    dep_line = ""
    hist = False
    dirty = False
    # Orogen prints its reserve rows and its resource rows under one header with a group label
    # in between; the label resets the header run, so the last good mapping is kept and reused
    # for any later row of the same width.
    last_cols, last_n, last_header = [], 0, None
    blk = None      # 1.0.22: the line the current table starts on (its caption, deposit heading or header)
    lead_dep, last_row_i = None, -9   # FIX5: the name a block's first row carries
    dep_i = None    # 1.0.22: the line the deposit in force was read from
    i = 0
    while i < len(ls):
        ln = ls[i]
        if not ln:
            i += 1
            continue
        wide = rowline_of(ln)
        lead = None
        if not wide:
            # 1.0.22: "Antenna Probable 2,489 2.20 176" -- the deposit in front of the category, one row per line
            lead = _lead_rowline(ln)
            if lead:
                wide = lead[1]
        if wide and not category_of(ln):
            canon, tail, vals = wide
            if lead:
                tail = lead[0] if not (deposit and _RE_SCENARIO.search(deposit)) else "%s (%s)" % (lead[0], deposit)
            cols = _best_columns([
                wide_columns([x for x in ls[max(0, i - 8):i] if x], len(vals)),
                build_columns(header, len(vals)),
                last_cols if _may_reuse(header, last_header, len(vals), last_n) else []])
            # FIX5: "Alpha Peru Proven 1.0 169 ..." then "Probable 2.9 106 ...": the name on a block's first row is the
            # next rows' too, until a heading or another name (never a Total line's)
            if lead and lead[0]:
                lead_dep = deposit_name(lead[0])
            elif not tail and lead_dep and (not dirty or i - last_row_i > 2):
                lead_dep = None
            carry = not lead and not re.match(r"(?i)\s*(?:sub-?\s?|grand\s+)?totals?\b", ln)
            r = _row((deposit_name(tail) if tail else None) or (lead_dep if carry else None) or deposit, canon,
                     "rowline", i)
            last_row_i = i
            r["_dep0"] = (deposit_name(tail) if tail else None) or deposit
            r["_win"] = dep_line
            r["_blk"] = i if blk is None else blk
            if cols:
                _fill(r, cols, vals)
                last_cols, last_n, last_header = cols, len(vals), list(header)
            else:
                r["confidence"] = "low"
            if r["cut_off"] is None:
                r["cut_off"] = dep_cut
            if canon in ("Proven", "Probable", "Proven & Probable") or dep_basis == "reserve" \
                    or (_RE_RESERVE_WORD.search(ln) and not _RE_RESOURCE_WORD.search(ln)):
                r["basis"] = "reserve"
            if re.match(r"(?i)\s*total\b", ln):
                _name_total(r, rows)
            r["_hist"] = hist
            rows.append(r)
            dirty = True
            i += 1
            continue
        cat = category_of(ln)
        if cat:
            vals = []
            j = i + 1
            while j < len(ls):
                if not ls[j]:
                    j += 1
                    continue
                n = number_of(ls[j])
                if n is None:
                    # 1.0.22: the category on a line of its own and the row's cells all on the next line
                    # ("Indicated" / "9.28 1.39 27.6 0.97 ..."), as a PDF table often arrives
                    if not vals:
                        vals = _cells_of(ls[j])
                        if vals:
                            j += 1
                    break
                vals.append(n)
                j += 1
            # a footnote marker after the last cell: XXIX's "... 490 | 1,613 | 433 | 1 | ." is eight
            # figures and a "1", and nine values found a nine-column reading of the header (1.0.19)
            if last_n and len(vals) == last_n + 1 and re.fullmatch(r"\d", vals[-1][0] or "") \
                    and not vals[-1][1]:
                vals = vals[:-1]
            if len([v for v in vals if v[0]]) >= 2:
                # A header that is present but does not fit is a header this reader cannot read.
                # Borrowing the previous table's columns then puts the previous table's meanings
                # on these numbers -- RUA Gold's tonnage came back as its contained ounces that
                # way. Where the mapping cannot be established the row keeps its deposit and its
                # category and states no figures.
                cols = _best_columns([build_columns(header, len(vals)),
                                      last_cols if _may_reuse(header, last_header, len(vals),
                                                              last_n) else []])
                r = _row((deposit_name(cat[1]) if cat[1] else None) or deposit, cat[0], "table", i)
                r["_win"] = dep_line
                r["_blk"] = i if blk is None else blk
                if cols:
                    _fill(r, cols, vals)
                    last_cols, last_n, last_header = cols, len(vals), list(header)
                else:
                    r["confidence"] = "low"
                if r["cut_off"] is None:
                    r["cut_off"] = dep_cut
                if cat[0] in ("Proven", "Probable", "Proven & Probable") or dep_basis == "reserve":
                    r["basis"] = "reserve"
                r["_hist"] = hist
                rows.append(r)
                dirty = True
                i = j
                continue
            # A category line with no figures under it is not a row: Goldgroup's North Pit block
            # prints "Measured" and then nothing. Only a Total heading above a block of categories
            # is a heading -- treating any empty category line as one swallowed the deposit name.
            nxt = next((x for x in ls[i + 1:i + 5] if x), "")
            # "Total" as the first line of a new header block (XXIX: "Pit Constrained", "Out of
            # Pit", then "Total") heads the sum of the blocks above; its rows are not the last block's
            if cat[0] == "Total" and dirty and re.fullmatch(r"(?i)\s*(?:grand\s+)?totals?\s*", ln) \
                    and _is_header_material(nxt):
                # the sum of the blocks is the project's figure, under the project's name
                deposit, dep_cut, dep_line, dep_basis = None, None, ln, None
            # (1.0.22: a bare "Total" over rows written one per line heads the sum of the blocks above, too)
            if cat[0] == "Total" and re.fullmatch(r"(?i)\s*(?:grand\s+)?totals?\s*", ln) and rowline_of(nxt):
                deposit, dep_cut, dep_line, dep_basis = None, None, ln, None
            elif cat[0] == "Total" and category_of(nxt):
                d = deposit_name(ln)
                deposit, dep_cut, dep_line = d, cutoff_in(ln), ln
                dep_basis = "reserve" if _RE_RESERVE_WORD.search(ln) else None
            i += 1
            continue
        lead_dep = None                     # FIX5: a line that is no row ends the block a lead name covers
        # 1.0.22: "(000)" under "Tonnes" is the column's unit (thousands of tonnes), not a figure: read as a
        # figure, it left the tonnage column in tonnes and a 528,000 t reserve reached the page as 528 t
        if _RE_THOUSANDS.match(ln) and header and not dirty:
            header.append(ln)
            i += 1
            continue
        if number_of(ln) is not None:
            if dep_cut is None and is_number(ln):
                dep_cut = ln.strip()
            i += 1
            continue
        if _RE_STOP.match(ln) or (len(ln) > 90 and not _is_header_material(ln)):
            # Fireweed prints eleven tables with paragraphs between them. Once a table has ended,
            # its columns are gone: carrying them to the next table read 6.3 Mt of ore as 94.
            header, deposit, dep_cut, dep_basis, dirty = [], None, None, None, False
            last_cols, last_n, last_header = [], 0, None
            blk = None
            hist = _introduces_historic(ln)
            i += 1
            continue
        if len(ln) <= 90 and _RE_HIST_CAPTION.search(ln):
            hist = True
        if _is_header_material(ln):
            if dirty:
                header, dirty = [], False
            if not header and blk is None:
                blk = i
            header.append(ln)
            del header[:-40]
            i += 1
            continue
        # 1.0.22: a country, province or state is the table's location column, not a deposit: a table printing
        # "<mine>" / "<country>" / "Proven ..." filed every row of a company-wide statement under the country
        if _is_location(ln) and (dep_i is not None and all(not x or number_of(x) for x in ls[dep_i + 1:i])
                                 or any(re.match(r"(?i)\s*(?:location|country|jurisdiction)\b", h) for h in header)):
            i += 1
            continue
        d = deposit_name(ln)
        if re.fullmatch(r"(?i)\(\s*(?:open[\s-]?pit|underground|in[\s-]?pit|out[\s-]?of[\s-]?pit)\s*\)", ln.strip()):
            # FIX5: "Alpha" / "Norte 1" / "(Open Pit)": a block heading the PDF wrapped over lines, its scenario last
            parts, k = [], i - 1
            while k >= 0 and len(parts) < 2:
                x = ls[k]
                if not x:
                    k -= 1
                    continue
                if number_of(x) is not None or rowline_of(x) or category_of(x) or _is_header_material(x) \
                        or len(x) > 40 or re.search(r"\d[\d,]*\.\d|\d,\d{3}", x):
                    break
                dn = deposit_name(re.sub(r"(?:\s+\d){1,3}\s*$", "", x))
                if not dn:
                    break
                parts.insert(0, dn)
                k -= 1
            if parts:
                d = "%s %s" % (" ".join(parts), ln.strip())
        if d:
            if blk is None:
                blk = i
            dep_i = i
            deposit, dep_cut, dep_line = d, cutoff_in(ln), ln
            dep_basis = "reserve" if _RE_RESERVE_WORD.search(ln) and not _RE_RESOURCE_WORD.search(ln) \
                else None
        i += 1
    return rows


# ------------------------------------------------------------------ a whole row on one line
_RE_ROWLINE = re.compile(
    r"(?i)^\s*(?P<cat>" + _CAT_ALT + r")"
    r"(?P<tail>[^\d\n]{0,34}?)\s*"
    r"(?P<vals>(?:[<>~]?\d[\d,.]*\s*(?:%|g/t|gpt|ppm|oz|koz|moz|kt|mt|t|lbs?|mlbs?)?[\s|]+){2,}"
    r"[<>~]?\d[\d,.]*\s*(?:%|g/t|gpt|ppm|oz|koz|moz|kt|mt|t|lbs?|mlbs?)?)\s*$")
_RE_CELL = re.compile(r"(?i)([<>~]?\d[\d,.]*)\s*(%|g/t|gpt|ppm|oz|koz|moz|kt|mt|t|lbs?|mlbs?)?")


_RE_LEAD_ROW = re.compile(r"(?i)^(?P<dep>[^\W\d_][^\d\n]{1,48}?)\s+(?P<rest>(?:total\s+)?(?:" + _CAT_ALT + r")\b.*)$")


def _lead_rowline(line):
    """('Antenna', rowline) for 'Antenna Probable 2,489 2.20 176': a deposit name, then a whole row on one line."""
    if not line or len(line) > 200:
        return None
    m = _RE_LEAD_ROW.match(line)
    if not m or len(m.group("dep").split()) > 6 or not all(
            w[:1].isupper() or w[:1] in "(-&" or w.lower() in _NAME_PARTICLE | {"and", "y", "of"}
            for w in m.group("dep").split()):
        return None
    wide = rowline_of(m.group("rest"))
    if not wide or wide[0] == "Total":
        return None
    if _is_location(m.group("dep")):
        return "", wide                       # the location column: the deposit is the heading above
    dep = deposit_name(m.group("dep"))
    # "Sub-total Proven and Probable 24.40 ...": the combined line of the deposit block above
    if re.fullmatch(r"(?i)\s*sub-?\s?totals?\s*", m.group("dep")) and wide[0] in ("Proven & Probable",
                                                                                "Measured & Indicated"):
        return "", wide
    if not dep or re.match(r"(?i)\s*(?:total|sub-?total)\b", dep) or _is_header_material(m.group("dep")):
        return None
    return dep, wide


def rowline_of(line: str):
    """('Indicated', 'Ermitano', [('797', None), ...]) for 'Inferred Ermitano 2,355 59.2 2.14'."""
    if not line or len(line) > 260:
        return None
    m = _RE_ROWLINE.match(line)
    if not m:
        return None
    canon = None
    for name, pat in _CAT_CANON:
        if re.fullmatch("(?i)" + pat, m.group("cat").strip()):
            canon = name
            break
    if canon is None:
        return None
    tail = re.sub(r"(?i)\b(mineral|resources?|reserves?|category)\b", " ", m.group("tail") or "")
    # 1.0.22: "Total Proven + Probable" is one category; stripping the "+" read it as Proven
    tail = re.sub(r"(?i)\b(prove[nd]|measured)\s*\+\s*(probable|indicated)\b", r"\1 & \2", tail)
    tail = re.sub(r"[\*\u2020\u2021\+]+", " ", tail)
    tail = _WS.sub(" ", tail).strip(" ,.;:()-")
    # "Total M&I" and "Total Inferred" name a category, not a deposit called M&I
    if canon == "Total" and tail:
        inner = category_of(tail)
        if inner:
            canon, tail = inner[0], inner[1]
    vals = [(c[0].lstrip("<>~").replace(",", ""), (c[1] or "").lower() or None)
            for c in _RE_CELL.findall(m.group("vals"))]
    vals = [v for v in vals if v[0] not in ("", ".")]
    # 1.0.22: "Total Measured Mineral Resource1 54 0.152 164" -- a footnote marker glued to the label is no cell
    vs = m.start("vals")
    if vals and vs and line[vs - 1].isalpha() and re.fullmatch(r"\d", vals[0][0]):
        vals = vals[1:]
    if len(vals) < 2:
        return None
    return (canon, tail, vals)


_LABEL_PREFIX = {"contained", "total", "average", "avg", "avg.", "recovered", "in-situ", "insitu", "payable"}
_LABEL_SUFFIX = {"grade", "grades", "metal", "ounces", "ozs", "oz", "pounds", "lbs", "equivalent", "eq", "eq."}


def _label_groups(toks, n):
    """A one-line header's words grouped into n column labels, or None: a group starts at a tonnage word, a metal or
    a prefix ("Contained", "Average"); "Grade" and "Metal" close the group before them. Leading class words go."""
    groups, open_prefix = [], False
    for t in toks:
        low = t.lower().strip(".,:")
        if not groups and (_CLASS_WORD.match(t) or low in ("reserve", "reserves", "resource", "resources", "mineral")):
            continue
        key = bool(_TONNAGE_WORD.fullmatch(t)) or bool(metal_of(t))
        if low in _LABEL_PREFIX:
            groups.append([t])
            open_prefix = True
        elif low in _LABEL_SUFFIX and groups and not open_prefix:
            groups[-1].append(t)
        elif open_prefix:
            groups[-1].append(t)
            open_prefix = False
        elif key or not groups:
            groups.append([t])
        else:
            groups[-1].append(t)
    return [" ".join(g) for g in groups] if len(groups) == n else None


def wide_columns(prev_lines: list, n_values: int, one: bool = True) -> list:
    """Columns for a one-line row, from header rows that are themselves whitespace-separated."""
    _one = _one_tonnage if one else list
    cands = []
    for ln in prev_lines:
        toks = [t for t in re.split(r"\s{1,}", ln.strip()) if t]
        if len(toks) < max(3, n_values - 1):
            continue
        # the row above a one-line row is usually another one-line row, and reading its figures
        # as column labels left every grade in Canadian Palladium's table with no metal on it
        if rowline_of(ln) or category_of(toks[0]) or _lead_rowline(ln):
            continue
        if sum(1 for t in toks if is_number(t)) * 2 >= len(toks):
            continue
        cands.append(toks)
    if not cands:
        return []
    units = None
    labels = None
    for toks in cands[::-1]:
        if all(_RE_BARE_UNIT.match(t) or t in ("%",) for t in toks):
            if units is None:
                units = toks
        elif labels is None:
            labels = toks
    if units and len(units) == n_values:
        if labels and len(labels) > n_values:
            # 1.0.22: "Category Tonnes Au Grade Ag Grade Contained Au Contained Ag" over "(Mt) (g/t) (g/t) (Moz)
            # (Moz)" is five columns of one to two words each; the last five words named none of them right
            labels = _label_groups(labels, n_values) or labels[-n_values:]
        if labels and len(labels) >= n_values:
            labels = labels[-n_values:]
            return _one([parse_col(l + " (" + u + ")") for l, u in zip(labels, units)])
        return _one([parse_col("(" + u + ")") for u in units])
    if labels and len(labels) == n_values:
        return _one([parse_col(t) for t in labels])
    return []


# 1.0.23 (2026-10-01, FIX3) ---------------------------------------- rows a table labels only by name
# A table often prints its categories once -- over its column groups ("Indicated | Inferred", then "Tonnes Grade
# Ounces" twice) or as a heading over a block of rows ("Indicated Resources") -- and gives each row only the deposit's
# name: "Phase 1 16.1 0.41 212,000 4.1 0.43 56,000". The readers above take a row's category from its own line, so
# such a table published nothing on the full release text (before 1.0.22, only its Total line, with every category's
# figures run together). read_grids reads those rows, and the rows above whose header they could not map.
_RE_GRID_CELL = re.compile(r"(?i)^(?:[<>~]?\(?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\)?%?|-{1,2}|\.{1,2}|n/?a|nil)$")
_RE_GRID_NUMBERED = (r"(?i)pit|zone|block|area|lens|stage|phase|target|domain|pushback|panel|level|shoot|no\.?|"
                     r"vein|lode|unit|horizon|pad|dump|stockpile|tsf|pod|sector|seam|reef|structure|shear|cut|bench")
_GRID_ABBR = {"meas": "Measured", "ind": "Indicated", "inf": "Inferred", "prov": "Proven", "prob": "Probable"}
_RE_GRID_ABBR = re.compile(r"(?i)^\s*(?:total\s+)?(meas|ind|inf|prov|prob)\.?(?:\s*(?:\+|&|and)\s*(meas|ind|inf|prov|prob)\.?)?\s*$")
_RE_GRID_DATE = re.compile(r"(?i)(?:\d{1,2}[-/ ])?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?[-/ ,]*"
                           r"(?:\d{1,2},?\s*)?((?:19|20)\d\d)\d?")
_RE_GRID_ASAT = re.compile(r"(?i)\b(?:as\s+(?:at|of)|effective(?:\s+date)?(?:\s+of)?)\s+(?:[A-Z][a-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+)?"
                           r"((?:19|20)\d\d)")
_RE_GRID_TOTAL = re.compile(r"(?i)^\s*(?:grand\s+|sub[\s-]?)?totals?\b|\b(?:sub[\s-]?)?totals?\s*(?:\(\d\))?\s*$")
# a row that is a change, a comparison, a price or a cut-off case, not an estimate
_RE_GRID_SKIP = re.compile(r"(?i)%|\bchange\b|\bdifferen\w*|\bvariance\b|\bincrease\b|\bdecrease\b|\bprevious\b|"
                           r"\bprior\b|\bcompar\w*|(?<!\d)(?:19|20)\d\d(?!\d)|\b(?:january|february|march|april|june|"
                           r"july|august|september|october|november|december)\b|\$|\bprice\b|\bcosts?\b|"
                           r"\brecover\w*|\bnsr\b|\bcut[\s-]?off\b|\bsensitivit\w*")
_RE_GRID_CAT = re.compile(r"(?i)(?<![\w&])(?:" + "|".join("(?:%s)" % p for n, p in _CAT_CANON if n != "Total")
                          + r")(?!\w)")
_RE_GRID_SENS = re.compile(r"(?i)\bsensitivit\w*|\bgold\s+prices?\b|\bmetal\s+prices?\b")
_RE_GRID_CMP = re.compile(r"(?i)\b(?:compar\w*|previous|prior|last\s+year|difference|change)\b")
_RE_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
             r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")
_GRID_WORDS = set("""mineral minerals resource resources reserve reserves total category categories classification class
project projects deposit deposits zone zones area areas property properties vein veins name material type mine mines
estimate estimates estimated and of the by in at as for inclusive exclusive to compared statement summary year end
year-end ni 43-101 cim attributable basis""".split())
_GRID_CLASS = set("""category categories classification class resource reserve mineral type material project deposit
zone area property vein veins name mine domain scenario segment location structure lens pit""".split())


def _canon_cat(raw):
    for name, pat in _CAT_CANON:
        if re.fullmatch("(?i)" + pat, (raw or "").strip()):
            return name
    return None


def _cat_words(ln):
    """(the category phrases of a line in order, its other words in lower case)."""
    s = re.sub(r"\(\s*\d{1,2}\s*\)|[*\u2020\u2021]+", " ", ln)
    cats, rest, at = [], [], 0
    for m in _RE_GRID_CAT.finditer(s):
        rest.append(s[at:m.start()])
        at = m.end()
        cats.append(_canon_cat(re.sub(r"\s+", " ", m.group(0))))
    rest.append(s[at:])
    words = [w for w in re.split(r"[\s,;:/()\-]+", " ".join(rest).lower()) if w]
    return [c for c in cats if c], words


def _cat_groups(ln):
    """['Indicated', 'Inferred'] for a header line that names one column group per category ("Indicated Inferred",
    "Proven Reserves Probable Reserves Total Proven and Probable", "Project Measured Indicated Total M&I Inferred")."""
    if not ln or len(ln) > 120:
        return None
    first = _RE_GRID_CAT.search(ln)
    if not first or re.search(r"\d", re.sub(r"\(\s*\d{1,2}\s*\)|43-101", " ", ln[first.start():])):
        return None
    # (the table's title may stand in front: "Omega Gold (100%) Measured Resource Indicated Resource ...")
    pre, ln = ln[:first.start()], ln[first.start():]
    if len(pre.split()) > 6 or re.search(r"[a-z]{3,}\s+[a-z]{3,}", pre):
        return None
    cats, words = _cat_words(ln)
    if len(cats) < 2 or len(set(cats)) != len(cats):
        return None
    if any(w not in _GRID_WORDS and not metal_of(w) for w in words):
        return None
    last = list(_RE_GRID_CAT.finditer(ln))[-1]
    if re.fullmatch(r"(?i)[\s\w]*?\btotals?\s*", ln[last.end():]) and re.search(r"(?i)\btotal", ln[last.end():]):
        cats.append("Total")
    return cats


def _heading_cat(ln):
    """('Indicated', False) for a heading over a block of rows ("Indicated Resources", "2018 Indicated Estimate",
    "Total Proven and Probable Gold Mineral Reserves"); ('Indicated', True) for a heading over a comparison
    ("Compared to 2017 Indicated Estimate")."""
    if not ln or len(ln) > 110:
        return None
    s = re.sub(r"\([^()]*\)", " ", ln)
    s = re.sub(r"(?i)\b" + _RE_MONTH + r"\s*\d{0,2},?\s*(?:19|20)\d\d\b|(?<!\d)(?:19|20)\d\d(?!\d)|\b43-101\b", " ", s)
    if re.search(r"\d", s):
        return None
    cats, words = _cat_words(s)
    if len(cats) != 1:
        return None
    if any(w not in _GRID_WORDS and w not in ("previous", "prior", "last") and not metal_of(w) for w in words):
        return None
    return cats[0], bool(_RE_GRID_CMP.search(s))


def _year_groups(ln):
    """(groups, the current one) for a header that prints one column group per date: "2025 2024(2)",
    "Dec 31, 2017 Dec 31, 2016", "Current Resource (March 2, 2017) Previous Resource (June 22, 2016)"."""
    if not ln or len(ln) > 120:
        return None
    low = ln.lower()
    cur, prv = re.search(r"\bcurrent\b", low), re.search(r"\b(?:previous|prior)\b", low)
    if cur and prv:
        return (2, 0 if cur.start() < prv.start() else 1)
    years = [int(y) for y in re.findall(r"(?<!\d)((?:19|20)\d\d)(?!\d)", ln)]
    if len(years) < 2 or len(set(years)) != len(years):
        return None
    s = re.sub(r"(?<!\d)(?:19|20)\d\d(?!\d)|\(\s*\d{1,2}\s*\)|\b\d{1,2}(?:st|nd|rd|th)?\b", " ", low)
    s = re.sub(r"\b" + _RE_MONTH + r"(?!\w)", " ", s)
    if any(w not in _GRID_WORDS and w not in ("dec", "effective", "date") for w in re.split(r"[\s,;:/()\-]+", s) if w):
        return None
    return (len(years), years.index(max(years)))


_RE_SEG_TOK = re.compile(r"\([^()]*\)|[^\s()]+")


def _seg_unit(t):
    """Whether a header token is a column's unit: "(Mt)", "(g/t Au)", "(000's)", "%", "kt", "Ounces"."""
    if t.startswith("("):
        b = t.strip("() ")
        if re.search(r"\d", b) and not (_RE_THOUSANDS.match(b) or re.search(r"(?i)[*x]\s*1,?000", b)):
            return False                       # "(100%)", "(1-6)", "(March 2, 2017)": no unit
        return bool(b) and (bool(_unit_in(b)[0]) or bool(_RE_THOUSANDS.match(b)) or "%" in b)
    return bool(_RE_BARE_UNIT.match(t)) or bool(re.fullmatch(r"(?i)(?:k|m|'?000'?s?) (?:tonn?es?|tons?|t|oz|ozs|lbs?|ounces)", t)) \
        or bool(re.fullmatch(r"(?i)k\s?tons|ktonnes|mtonnes|(?:million|thousand) (?:tonn?es?|tons?|ounces|oz|pounds|lbs?)", t))


def _seg_columns(lines, n):
    """Columns for a header whose labels wrap across lines (1.0.23 FIX3). Two shapes:
      - every label ends at its unit: "Tonnes (Mt) Ag (g/t) Contained / Ag (Moz) Au (g/t) Contained / Au (Moz)",
        "Category Type k tonnes Ag (g/t) Au (g/t) ...", "Dry Tonnes (million) Gold Grade (g/t Au) Insitu Gold (million
        ounces)";
      - a row of labels over a row of units: "Tonnes Grade Ounces Tonnes Grade Ounces" over "(000's) (g/t Au) (000's)
        (000's) ..." or "kt g/t Au koz Au kt ..."."""
    toks = []
    for t in _RE_SEG_TOK.findall(" ".join(lines)):
        # "k tonnes", "M oz": a scale and its unit are one token
        if toks and re.fullmatch(r"(?i)k|m|million|thousand|'?000'?s?", toks[-1]) \
                and re.fullmatch(r"(?i)tonn?es?|tons?|t|oz|ozs|lbs?|ounces", t):
            toks[-1] += " " + t
        else:
            toks.append(t)
    toks = [t for t in toks if not (t.startswith("(") and not _seg_unit(t))]   # "(1)", "(incl. stockpiles)"
    # lines of labels over lines of units ("kt g/t Au koz Au ...": a metal after a unit is the unit's), the header
    # one row per line or one cell per line: the last n units, and the labels on the lines above them
    units, li = [], len(lines)
    while li > 0 and len(units) < n:
        ut = _RE_SEG_TOK.findall(lines[li - 1])
        if not ut or not _seg_unit(ut[0]) or not all(_seg_unit(t) or metal_of(t) for t in ut):
            break
        grp = []
        for t in ut:
            if _seg_unit(t) or not grp:
                grp.append(t)
            else:
                grp[-1] += " " + t
        units = grp + units
        li -= 1
    labels = [t for t in _RE_SEG_TOK.findall(" ".join(lines[max(0, li - 3 * n):li]))
              if not t.startswith("(") and t.lower() not in _GRID_CLASS] if li > 0 else []
    # (a header one label per line: "Tonnes" / "Ag TrOz" / "Au TrOz" / "Cu" ... over the units)
    line_labels = [x for x in lines[max(0, li - n - 4):li] if x.strip().lower() not in _GRID_CLASS
                   and 0 < len(x.split()) <= 3 and not _seg_unit(x.strip())]
    if len(units) == n and len(line_labels) >= n and len(lines[max(0, li - n):li]) == n \
            and all(0 < len(x.split()) <= 3 for x in lines[li - n:li]):
        cols = [parse_col(lab + " (" + u.strip("() ") + ")") for lab, u in zip(line_labels[-n:], units)]
        if all(c["unit"] for c in cols):
            return cols
    if len(units) == n and len(labels) >= n:
        labels = _label_groups(labels[-3 * n:], n) or labels[-n:]
        cols = [parse_col(lab + " (" + u.strip("() ") + ")") for lab, u in zip(labels, units)]
        if all(c["unit"] for c in cols):
            return cols
    # "Tonnes" with no unit under it, then "Au Cu AuEq Au Cu AuEq" over "g/t % g/t Oz Lbs Oz"
    ton = [t for t in labels if _TONNAGE_WORD.fullmatch(t)]
    if len(units) == n - 1 >= 2 and len(ton) == 1 and len(labels) >= n and all(metal_of(t) for t in labels[-(n - 1):]):
        cols = [parse_col(ton[0])] + [parse_col(lab + " (" + u.strip("() ") + ")")
                                      for lab, u in zip(labels[-(n - 1):], units)]
        if all(c["unit"] for c in cols) and cols[0]["kind"] == "tonnage":
            return cols
    # a row of labels over a row of units, the header one cell per line
    k = len(toks)
    while k > 0 and (_seg_unit(toks[k - 1]) or metal_of(toks[k - 1]) and k >= 2 and _seg_unit(toks[k - 2])):
        k -= 1
    units = []
    for t in toks[k:]:
        if _seg_unit(t) or not units:
            units.append(t)
        else:
            units[-1] += " " + t
    labels = [t for t in toks[:k] if t.lower() not in _GRID_CLASS]
    if len(units) == n and len(labels) >= n and not any(_seg_unit(t) for t in labels):
        labels = _label_groups(labels, n) or labels[-n:]
        cols = [parse_col(lab + " (" + u.strip("() ") + ")") for lab, u in zip(labels, units)]
        if all(c["unit"] for c in cols):
            return cols
    # every label ends at its unit
    segs, cur = [], []
    for j, t in enumerate(toks):
        nxt = toks[j + 1:j + 3]
        if _seg_unit(t) and not (not t.startswith("(") and nxt and (nxt[0].startswith("(") or len(nxt) == 2 and (
                metal_of(nxt[0]) and nxt[1].startswith("(") and _seg_unit(nxt[1])
                and _unit_in(t)[0] == _unit_in(nxt[1].strip("() "))[0]))):   # "Oz Au (koz)" is one column
            # the unit goes in brackets: "Au Eq* g/t" is an AuEq grade, not gold
            segs.append(" ".join(cur + [t if t.startswith("(") or not cur else "(" + t + ")"]))
            cur = []
        else:
            cur.append(t)
    if len(segs) != n:
        return []
    cols = [parse_col(s) for s in segs]
    return cols if all(c["unit"] for c in cols) else []


def _grid_fits(c, n, k):
    """A mapping that can be split into k column groups: k tonnage columns, nothing but a cut-off in front of the
    first, and every group the same columns in the same order ("Tonnes Grade Ounces" under each category)."""
    if not c or len(c) != n:
        return False
    tpos = [j for j, x in enumerate(c) if x["kind"] == "tonnage"]
    if len(tpos) != k or any(x["kind"] in ("grade", "contained") for x in c[:tpos[0]]):
        return False
    if k > 1:
        size = tpos[1] - tpos[0]
        shape = [(x["kind"], x["metal"]) for x in c[tpos[0]:tpos[0] + size]]
        if any([(x["kind"], x["metal"]) for x in c[t:t + size]] != shape for t in tpos[1:]):
            return False
    return True


@functools.lru_cache(maxsize=8192)
def _unit_or_metal(w):
    return bool(_RE_BARE_UNIT.match(w) or metal_of(w))


def _prose_words(ln):
    """How many lower-case words of three letters or more a line holds, units and metals aside ("kt g/t Au koz Au"
    is a header, "the PFS Update and the royalty value model" is not)."""
    return sum(1 for w in re.findall(r"\b[a-z]{3,}\b", ln) if not _unit_or_metal(w))


def _pair_columns(lines, n):
    """Columns for a header that alternates a label line and its unit line: "Tonnes" / "kt" / "Grade" / "g/t Au" /
    "Ounces" / "koz Au" (1.0.23 FIX3)."""
    joined = []
    for ln in lines:                                   # "(million" / "ounces)": one bracket over two lines
        if joined and joined[-1].count("(") > joined[-1].count(")"):
            joined[-1] += " " + ln
        else:
            joined.append(ln)
    cols, pend, last = [], None, None
    for ln in joined:
        ut = _RE_SEG_TOK.findall(ln)
        # a unit line is an abbreviation or a bracket ("kt", "g/t Au", "(koz)"); "Tonnes", "Ounces" are labels
        unit = bool(ut) and len(ut) <= 3 and _seg_unit(ut[0]) and all(_seg_unit(t) or metal_of(t) for t in ut) \
            and not re.fullmatch(r"(?i)tonn?es?|tons?|tonnage|ounces|pounds", ut[0])
        if unit and pend is not None:
            u = " ".join(ut)
            last = pend + " " + u if "(" in u else pend + " (" + u + ")"
            cols.append(parse_col(last))
            pend = None
        elif unit and last is not None and ut[0].startswith("("):
            last += " " + " ".join(ut)                     # "Ag" / "TrOz" / "(000's)": a unit over two lines
            cols[-1] = parse_col(last)
        else:
            pend, last = ln, None
    return cols if len(cols) == n and all(c["unit"] for c in cols) else []


def _grid_columns(hdr, n, k, cache):
    """The header's columns for a row of n cells, with exactly k tonnage columns (one per column group)."""
    key = (hdr, n, k)
    if key not in cache:
        best, score = [], -1
        # "(OP= Open Pit, UG= Underground ...)" is a key to the table, and a sentence is no column label
        hl = [x for x in hdr if "=" not in x and len(x) <= 120 and not re.search(r"[a-z]{2}\.\s*$", x)
              and _prose_words(_RE_PAREN.sub(" ", x)) < 4 and not re.search(r"\d,\d{3}|\d\.\d", x)]
        cands = [_pair_columns(hl, n), _seg_columns(hl, n), wide_columns(hl[-8:], n, one=False),
                 build_columns(hl, n, one=False)]
        # FIX5: a deposit heading printed between the header and its rows ("kt g/t g/t k oz k oz" / "Alpha Sur 1" /
        # "(Open pit)") is no part of the header: read the header up to its last line of units as well
        ul = [j for j, x in enumerate(hl) if _RE_SEG_TOK.findall(x) and _seg_unit(_RE_SEG_TOK.findall(x)[0])
              and all(_seg_unit(t) or metal_of(t) for t in _RE_SEG_TOK.findall(x))]
        if ul and ul[-1] < len(hl) - 1 and not any(_is_header_material(x) for x in hl[ul[-1] + 1:]):
            th = hl[:ul[-1] + 1]
            cands += [_pair_columns(th, n), _seg_columns(th, n), wide_columns(th[-8:], n, one=False),
                      build_columns(th, n, one=False)]
        for c in cands:
            if not _grid_fits(c, n, k) or re.search(r"(?i)\bgrades?\b", " ".join(hl)) and \
                    not any(x["kind"] == "grade" for x in c):    # a "Grade" header and no grade read: misread
                continue
            sc = sum(1 for x in c if x["metal"])
            if sc > score:
                best, score = c, sc
        best = _borrow_metals([dict(x) for x in best]) if best else []
        # "Gold Copper Silver Molybdenum" over "Grade (g/t) Ounces (millions) Grade (%) Pounds (millions) ...": each
        # metal heads a grade column and the contained column after it
        mline = next((x for x in hl if len(x.split()) >= 2 and all(metal_of(w) for w in x.split())), None)
        if best and mline and not any(c["metal"] for c in best):
            metals, mi = [metal_of(w) for w in mline.split()], -1
            for c in best:
                if c["kind"] == "grade":
                    mi += 1
                if c["kind"] in ("grade", "contained") and 0 <= mi < len(metals):
                    c["metal"], c["eq"] = metals[mi]
        g = [c for c in best if c["kind"] == "grade"]
        cm = [c for c in best if c["kind"] == "contained"]
        if g and len(g) == len(cm):                # and the other way: "Grade (g/t Ag)" names "Ounces (000's)"
            for a, b in zip(g, cm):
                if b["metal"] is None and a["metal"]:
                    b["metal"], b["eq"] = a["metal"], a["eq"]
        cache[key] = best
    return cache[key]


def _grid_line(ln):
    """('Phase 1', [('16.1', None), ...]) for a line that is a row label and its cells, ('', cells) for a line of
    cells only, else None. A bracketed footnote number after the label ("George (8) 13,662,000 ...") is no cell."""
    if not ln or len(ln) > 260:
        return None
    toks = ln.split()
    k = len(toks)
    while k > 0 and _RE_GRID_CELL.match(toks[k - 1]):
        k -= 1
    # "Phase 1 16.1 0.41 ...", "No. 300 514,000 ...": the number of a numbered block is part of its name
    if 0 < k < len(toks) and re.fullmatch(r"\d{1,3}[A-Za-z]?", toks[k]) and re.fullmatch(_RE_GRID_NUMBERED, toks[k - 1]):
        k += 1
    cells = toks[k:]
    if k and cells and re.fullmatch(r"\(\d{1,2}\)", cells[0]):
        cells = cells[1:]
    if len(cells) < 2 or len(cells) > 30:
        return None
    label = " ".join(toks[:k])
    if label and (not re.search(r"[A-Za-z]", label) or len(label) > 80):
        return None
    vals = []
    for c in cells:
        if re.fullmatch(r"(?i)-{1,2}|\.{1,2}|n/?a|nil", c):
            vals.append(("", None))
            continue
        vals.append((c.lstrip("<>~").strip("()%").replace(",", ""), None))
    if sum(1 for v in vals if v[0]) < 2 or all(re.fullmatch(r"(?:19|20)\d\d", v[0]) for v in vals if v[0]):
        return None
    return label, vals


def _grid_cpl(ls, i):
    """(cells, the next line) when the label on line i has its cells on the lines below it, one per line."""
    vals, j, first = [], i + 1, True
    while j < len(ls) and len(vals) < 30:
        x = ls[j]
        if not x:
            j += 1
            continue
        nb = number_of(x) if x.count("(") == x.count(")") else None    # "2021)": a citation's year, not a cell
        if nb is None:
            break
        if not (first and re.fullmatch(r"\(\d{1,2}\)", x.strip())):    # a footnote marker under the label
            vals.append(nb)
        first = False
        j += 1
    if sum(1 for v in vals if v[0]) < 2 or all(re.fullmatch(r"(?:19|20)\d\d", v[0]) for v in vals if v[0]):
        return None                                        # "2023" / "2022": a header's dates, not a row
    return vals, j


def _grid_rows(st, label, vals, i, prev, cache):
    """The rows one table line states (see read_grids)."""
    lab = re.sub(r"\s+", " ", label).strip(" :;,*")
    if re.match(r"\d+\.\d", lab):
        return []                                  # "1.00 indicated 2,479,000 ...": a cut-off case of a sensitivity table
    total = bool(_RE_GRID_TOTAL.search(lab))
    own, dep, named = None, None, False
    if lab == "\x00":                                     # a row named by its date (read_grids)
        total = False
    elif prev is not None:                                   # a row the readers above read without figures
        own, dep, total = prev["category"], prev["deposit"], False
        if dep and re.match(r"(?i)(?:current|previous|prior|updated|new|old)\b", dep):
            dep = None                                     # the heading of a comparison's column group
        if not dep and st["dep"]:
            dep = st["dep"]                                # the deposit heading over the block
        # "Sigma Proven 8 1.9 500" then "Probable 108 2.9 10,000": the name printed on a block's first row is
        # every row's in the block
        if st["lead"] and re.fullmatch(r"(?i)(?:total\s+)?(?:" + _CAT_ALT + r")(?:\s+(?:mineral\s+)?(?:resources?|reserves?))?",
                                       lab):
            dep = st["lead"]
    else:
        cats, _w = _cat_words(lab)
        if len(cats) > 1:
            return []
        if cats:                                           # "Proven (UG) Sulphides", "Measured Kappa"
            own, total = cats[0], False
            dep = _deposit_or_none(deposit_name(re.sub(r"(?i)\b(?:total|mineral|resources?|reserves?)\b", " ",
                                                       _RE_GRID_CAT.sub(" ", lab))))
            if dep is None and st["lead"] and not _RE_GRID_TOTAL.match(lab):
                dep = st["lead"]
        elif _RE_GRID_ABBR.match(lab):                     # "Meas + Ind", "Total Inf"
            m = _RE_GRID_ABBR.match(lab)
            own = _GRID_ABBR[m.group(1).lower()] if not m.group(2) else \
                {"Measured&Indicated": "Measured & Indicated", "Proven&Probable": "Proven & Probable"}.get(
                    _GRID_ABBR[m.group(1).lower()] + "&" + _GRID_ABBR[m.group(2).lower()])
            if own is None:
                return []
            total = False
        elif _RE_GRID_SKIP.search(_RE_PAREN.sub(" ", lab)):   # (a grade domain's "(>0.25% Cu)" is a name's part)
            return []
        else:
            dep = None if total else _deposit_or_none(deposit_name(lab))
            # "Delta North Open Pit 45,146,000 ..." then "Underground 918,000 ...": the scenario row below a
            # named one is the same deposit's
            sm = re.match(r"(?i)^(?P<n>.*?\S)\s+(?P<s>open[\s-]?pit|underground|in[\s-]?pit|out[\s-]?of[\s-]?pit)$", lab)
            if sm:
                st["scen"] = None if total else _deposit_or_none(deposit_name(sm.group("n")))
                if st["scen"] and dep:
                    dep, named = "%s - %s" % (st["scen"], sm.group("s")), True
            elif re.fullmatch(r"(?i)open[\s-]?pit|underground|in[\s-]?pit|out[\s-]?of[\s-]?pit", lab) and not total:
                if st["scen"]:
                    dep, named = "%s - %s" % (st["scen"], lab), True
            else:
                st["scen"] = None
            if not total and not dep:
                return []
    st["last_own"] = own
    m = re.match(r"(?i)^(?P<d>[^\W\d_][\w'\-]*(?:\s+[\w'\-]+){0,3}?)\s+(?:" + _CAT_ALT + r")\b", lab)
    if m and not _RE_GRID_TOTAL.match(lab) and not _cat_words(m.group("d"))[0] and _deposit_or_none(m.group("d")):
        st["lead"] = _deposit_or_none(m.group("d"))
    if st["cmp"] or st["skip"]:
        return []
    n = len(vals)
    if own is not None:
        if st["groups"]:
            return []
        plan = [(1, [own])]
    elif st["groups"]:
        plan = [(len(st["groups"]), st["groups"])]
    else:
        one = st["head"] or st["cap"] or st["carry"]
        if not one:
            return []
        plan = [(1, [one])]
    if st["ygrp"]:
        plan = [(st["ygrp"][0], None)] + plan
    cols, cats, year = [], None, False
    for k, cs in plan:
        cols = _grid_columns(tuple(st["hdr"]), n, k, cache)
        if cols:
            cats, year = cs, cs is None
            break
    if not cols:
        return []
    tpos = [j for j, c in enumerate(cols) if c["kind"] == "tonnage"]
    lead = list(range(tpos[0]))
    size = (tpos[1] - tpos[0]) if len(tpos) > 1 else len(cols) - tpos[0]
    spans = [list(range(t, min(t + size, len(cols)))) for t in tpos]
    if year:
        spans = [spans[st["ygrp"][1]]]
        one = own or st["head"] or st["cap"] or st["carry"]
        if st["groups"] or not one:
            return []
        cats = [one]
    if prev is None and st["dep"] and (not dep or len(lab) <= 4 or _RE_SCENARIO.search(lab)) and not total \
            and not named:
        dep = "%s (%s)" % (st["dep"], dep or lab) if (dep or lab) and dep != st["dep"] else st["dep"]
    out = []
    for g, cat in zip(spans, cats):
        idx = lead + g
        gv = [vals[j] for j in idx]
        if not any(v[0] and float(v[0] or 0) for v in [vals[j] for j in g]):   # "-" or "0 0.00 0": none
            continue
        r = _row(dep, "Total" if total else cat, "table", i)
        r["_win"] = st["win"]
        r["_blk"] = i if st["blk"] is None else st["blk"]
        _fill(r, [cols[j] for j in idx], gv)
        seen = set()
        r["grades"] = [x for x in r["grades"] if not ((x["metal"], x["unit"]) in seen or seen.add((x["metal"], x["unit"])))]
        seen = set()
        r["contained"] = [x for x in r["contained"]
                          if not ((x["metal"], x["unit"]) in seen or seen.add((x["metal"], x["unit"])))]
        if _figureless(r) or r["tonnes"] is None or r["tonnes"] < 1000:   # a table row states its tonnage
            continue
        if r["category"] in ("Proven", "Probable", "Proven & Probable") or st["basis"] == "reserve":
            r["basis"] = "reserve"
        r["_hist"] = st["hist"] or st.get("older", False)
        r["_grid"] = "named" if named else True
        out.append(r)
    if own is not None and out and not total:
        st["carry"] = own
    return out


_GRID_PARTS = {"Proven & Probable": ("Proven", "Probable"), "Measured & Indicated": ("Measured", "Indicated")}


def _grid_state(st=None, hist=False):
    st = st if st is not None else {}
    st.update(hdr=[], groups=None, ygrp=None, head=None, cmp=False, cap=None, dep=None, carry=None, data=False,
              win="", blk=None, hist=hist, basis=None, pend=[], last_head=None, skip=False, under=[], last_own=None,
              lead=None, cap_i=None, yrs=[], dated=False, scen=None)
    return st


def read_grids(ls, done=None):
    """Rows of tables whose rows carry only a name, their category printed over a column group, as a heading or in
    the caption (see above). done: {line: row} that read_tables read -- a row it read with figures stays its own;
    one it read without (a header it could not map) is read again here."""
    done = done or {}
    rows, cache = [], {}
    st = _grid_state()
    # a table "as at June 30, 2021" in a release whose estimate is "as at June 30, 2022" restates the year before:
    # its rows are the earlier estimate, quoted for comparison (guide section 6: background)
    asat = {}
    for k, x in enumerate(ls):
        # (a table's title, not a sentence of the notes: "... which has an effective date of March 11, 2024.")
        m = _RE_GRID_ASAT.search(x) if x and len(x) <= 130 and _RE_RES_WORD.search(x) and not x[0].islower() \
            and not re.search(r"\.\s*$", x) and sum(1 for w in re.findall(r"\b[a-z]{3,}\b", x)
                                                  if w not in _GRID_WORDS and not _RE_BARE_UNIT.match(w)) <= 3 else None
        if m:
            asat[k] = int(m.group(1))
    newest = max(asat.values()) if len(set(asat.values())) >= 2 else None
    older = False
    i = 0
    while i < len(ls):
        ln = ls[i]
        if not ln:
            i += 1
            continue
        if newest and i in asat:
            older = asat[i] < newest
        st["older"] = older
        prev = done.get(i)
        if prev is not None and not _figureless(prev):
            st["data"], st["pend"] = True, []
            if prev["category"] != "Total" and prev["source"] == "rowline":
                st["carry"] = prev["category"]
            i += 1
            continue
        g = _grid_line(ln)
        label, vals, j = None, None, i + 1
        if g is not None:
            label, vals = g
            if (not label or label[:1] == "(" or label[:1].islower()) and st["pend"]:
                used = st["pend"][-3:]                                  # a label the PDF wrapped above its cells
                label = " ".join(used + [label]).strip()
                if not st["data"] and st["hdr"][-len(used):] == used:
                    del st["hdr"][-len(used):]
        elif number_of(ln) is None and len(ln) <= 60 and re.search(r"[A-Za-z]", ln):
            # (a word of a sentence the PDF printed one word per line is no row label: "... ounces;" / "Smith" / "2021)")
            pl = next((x for x in reversed(ls[max(0, i - 3):i]) if x), "")
            cpl = _grid_cpl(ls, i) if not re.search(r"[,;]\s*$|^(?:and|of|the|with|a|an|to|in|for|by|at)$", pl) else None
            if cpl is not None:
                label, (vals, j) = ln, cpl
                # "Bulk" / "Underground" / cells: a name the PDF broke over two lines between two rows
                if st["data"] and st["pend"] and all(len(x) <= 25 for x in st["pend"][-2:]):
                    label = " ".join(st["pend"][-2:] + [ln])
        if g is not None and not label:                   # cells with no label to them
            st["data"], st["pend"] = True, []
            i += 1
            continue
        if label and _RE_GRID_DATE.fullmatch(label.strip()):
            # rows named by their effective date ("28-Nov-2025 4,050 14.78 ...", then "31-Jul-2024 ..."): the latest
            # is the estimate, the others are the ones it replaces
            later = [int(m.group(1)) for x in ls[i + 1:i + 6] if x
                     for m in [re.match(r"(?:\d{1,2}[-/ ])?[A-Za-z]{3,9}[-/ ,]*(?:\d{1,2},?\s*)?((?:19|20)\d\d)", x)] if m]
            if later and int(_RE_GRID_DATE.fullmatch(label.strip()).group(1)) < max(later) or st["dated"]:
                st["data"], st["pend"] = True, []
                i = j
                continue
            st["dated"] = True
            label = "\x00"                                         # the release's project, as named elsewhere
        if label:
            got = _grid_rows(st, label, vals, i, prev, cache)
            rows += got
            own = st["last_own"]
            if own is None:
                st["under"] += [r for r in got if st["head"] in _GRID_PARTS and r["category"] == st["head"]]
            elif _RE_GRID_TOTAL.match(label) and own in _GRID_PARTS.get(st["head"], ()):
                # "Proven and Probable Mineral Reserves" over rows that a "Total Proven" line, then a "Total Probable"
                # line, close: the rows above each such total are that part's, not the combined category's
                for r in st["under"]:
                    r["category"] = own
                st["under"] = []
            st["data"], st["pend"] = True, []
            i = j
            continue
        yg = _year_groups(ln)
        if yg:
            st.update(ygrp=yg, hdr=[] if st["data"] else st["hdr"], data=False, pend=[])
            if st["blk"] is None:
                st["blk"] = i
            i += 1
            continue
        if number_of(ln) is not None:
            # "2023" / "2022" on lines of their own over a header: one column group per year
            yrs = []
            for x in ls[i:i + 8]:
                if x and re.fullmatch(r"(?:19|20)\d\d(?:\s*\(\d\))?", x):
                    yrs.append(int(x[:4]))
                elif x:
                    break
            if len(yrs) >= 2 and len(set(yrs)) == len(yrs) and not st["data"]:
                st["ygrp"] = (len(yrs), yrs.index(max(yrs)))
            i += 1
            continue
        nlow = _prose_words(ln)
        if _RE_STOP.match(ln) or nlow >= 6 or (len(ln) > 90 and nlow >= 5) \
                or (len(ln) > 60 and nlow >= 2 and re.search(r"\d,\d{3}|\d\.\d", ln)):   # a line of prose ends the table
            if not _RE_STOP.match(ln) and st["cap_i"] is not None and i - st["cap_i"] <= 4 and not st["data"]:
                st["cap_i"] = i               # a caption that runs over a second line
                i += 1
                continue
            _grid_state(st, _introduces_historic(ln))
            i += 1
            continue
        if _RE_CAPTION.match(ln) or (len(ln) <= 120 and _RE_HIST_CAPTION.search(ln)):
            _grid_state(st, bool(_RE_HIST_CAPTION.search(ln)) or st["hist"])
            st["win"], st["blk"], st["cap_i"] = ln, i, i
            st["skip"] = bool(_RE_GRID_SENS.search(ln))      # a gold-price or cut-off sensitivity table
            cats, _w = _cat_words(ln)
            st["cap"] = cats[0] if len(set(cats)) == 1 else None
            if _RE_RESERVE_WORD.search(ln) and not _RE_RESOURCE_WORD.search(ln):
                st["basis"] = "reserve"
            i += 1
            continue
        cg = _cat_groups(ln)
        if cg:
            st.update(groups=cg, hdr=[] if st["data"] else st["hdr"], data=False, carry=None, head=None, cmp=False,
                      pend=[])
            if st["blk"] is None:
                st["blk"] = i
            i += 1
            continue
        hc = _heading_cat(ln)
        if hc:
            if st["last_head"] is not None and not st["data"] and not st["pend"]:
                # "Indicated" / "Inferred" on lines of their own over a header: one column group each
                st["groups"] = (st["groups"] or [st["last_head"]]) + [hc[0]]
                st["head"] = None
            else:
                if st["data"]:
                    st["groups"], st["dep"] = None, None
                st.update(head=hc[0], cmp=hc[1], carry=None, under=[], lead=None)
            st["last_head"], st["pend"] = hc[0], []
            if st["blk"] is None:
                st["blk"] = i
            i += 1
            continue
        st["last_head"] = None
        if _RE_GRID_SENS.search(ln):
            st["skip"] = True
        # "2023 Mineral Reserves & Resources" over one column group, "2024 Mineral Reserves & Resources" over the next
        ym = re.match(r"((?:19|20)\d\d)\b(.*)$", ln)
        if ym and not st["data"] and all(w in _GRID_WORDS or w in ("change", "&") for w in
                                         re.split(r"[\s,;:/()\-]+", ym.group(2).lower()) if w):
            y = int(ym.group(1))
            st["yrs"] = (st["yrs"][st["yrs"].index(y) + 1:] if y in st["yrs"] else st["yrs"]) + [y]   # a title's year first
            if len(st["yrs"]) >= 2:
                st["ygrp"] = (len(st["yrs"]), st["yrs"].index(max(st["yrs"])))
        wrap = st["pend"] and ln.count(")") > ln.count("(") and st["pend"][-1].count("(") > st["pend"][-1].count(")")
        if not wrap and (_is_header_material(ln) or _seg_unit(ln.strip())):
            if st["data"]:
                st.update(hdr=[], data=False, dep=None, lead=None, scen=None)
            st["hdr"].append(ln)
            del st["hdr"][:-40]
            st["pend"] = []
        else:
            st["pend"].append(ln)
            del st["pend"][:-4]
            if not st["data"]:
                st["hdr"].append(ln)
                del st["hdr"][:-40]
            nxt = next((x for x in ls[i + 1:i + 3] if x), "")
            nxt_row = bool(_grid_line(nxt) and _grid_line(nxt)[0]
                           or re.match(r"[A-Za-z].*?(?:\s(?:-{1,2}|NA|n/a)){2,}\s*$", nxt))
            d = deposit_name(ln) if nxt_row and len(ln) <= 50 and not re.search(r"\s(?:-{1,2}|NA|n/a)(?:\s|$)", ln) \
                else None
            if d and re.search(r"\b(?!(?:de|del|la|las|los|el|du|des|da|do|dos|y|of|the|and)\b)[a-z]{2,}", d):
                d = None                          # "Breakdown by Deposit" is a caption, not a deposit heading
            if d:
                st["dep"] = d
        i += 1
    return rows


# ------------------------------------------------------------------ prose
# "classified as a Proven & Probable Mineral Reserve" is one category; read as two, NVRO's
# 2.32 Mt P&P reserve was published as Proven (1.0.19)
_RE_CAT_WORD = re.compile(r"(?i)\b(measured\s+(?:and|&|\+)\s+indicated|prove[nd]\s*(?:and|&|\+)\s*probable|"
                          # 1.0.22: the two written backwards, and the abbreviation ("8.8Mt @ 3.9% CuEq M&I and ...")
                          r"indicated\s*(?:and|&|\+)\s*measured|probable\s*(?:and|&|\+)\s*prove[nd]|M\s?[&+]\s?I|"
                          r"measured|indicated|inferred|proven|proved|probable)\b")
_RE_RES_WORD = re.compile(r"(?i)\b(resources?|reserves?|mre\b)")
# a trailing label: "... 66 ppm Ga, Indicated, and 33.4 Mt ... Inferred,"
# "... for 128,000 indicated tonnes of LCE" labels the tonnes; the estimate is in front of it
_RE_TRAILING = re.compile(r"(?i)^\s*(?:[,;.)]|and\b|category\b|classification\b|"
                          r"tonnes?\b|ounces\b|oz\b|pounds\b|lbs?\b|t\b|$)")
# "1.0 million tonnes grading 1.00 g/t Au for an indicated resource of 33 koz Au" -- the tonnage
# and the grade are in front of the category and only the contained metal follows it
_RE_TRAILING_BEFORE = re.compile(r"(?i)(?<!well\s)\b(?:for|as)\s+(?:an?\s+)?$")   # 1.0.22: not "as well as an"
_MULT_WORD = {"million": 1e6, "billion": 1e9, "thousand": 1e3, "m": 1e6, "k": 1e3, "b": 1e9}

# "totalling 67,000 tonnes of antimony" is contained metal; "Resources total 6.3 million tonnes"
# is ore. The verb does not decide it -- the word after the unit does (RES 1.0.16, 2026-09-18).
_RE_AFTER_TONNES = re.compile(r"(?i)^\s*(?:of\s+)?(?:contained\s+)?(?P<m>[A-Za-z][A-Za-z0-9]{0,8})\b")


# 'a contained lithium carbonate equivalent ("LCE") of 3.75 Mt Indicated' -- the metal is named
# in front of the figure (a domain's "(Ag-Zn-Pb-Sn) of 13.84 Mt" is not). Patriot's 3.75 Mt of LCE
# was published as an Indicated ore tonnage (1.0.19)
_RE_METAL_OF = re.compile(r"(?i)(?<![\w-])(?P<m>[A-Za-z][A-Za-z0-9]{0,8})[\"\u201d')\s]*\s+of\s+$")


def _metal_in_front(text, pos):
    m = _RE_METAL_OF.search(text[max(0, pos - 30):pos])
    return bool(m and metal_of(m.group("m")))


def _tonnes_are_metal(after: str) -> bool:
    m = _RE_AFTER_TONNES.match(after or "")
    return bool(m and metal_of(m.group("m")))


_RE_P_TONNES = re.compile(
    # 1.0.23: the words in between hold no digit -- "totals 1,687,000 tonnes" was read as "totals 1,687," + 000 t
    r"(?i)(?P<pre>\b(?:containing|contains|comprising|including|includes|of\s+contained)\b[^.\d]{0,24}"
    r"|(?P<soft>\b(?:for|totalling|totaling|totals?)\b[^.\d]{0,24}))?"
    r"\b(?P<n>\d[\d,.]*)\s*(?P<mult>million|billion|thousand)?\s*(?:metric\s+|dry\s+)?"   # 1.0.22: metric
    r"(?P<u>tonnes|tonne|tons|ton|mt|kt|t)\b"
    # 1.0.22: "4,100 tonnes per day" is a mill's throughput, not a tonnage
    r"(?!\s*(?:per|/|a)\s*(?:day|d|year|yr|annum|month|hour|hr)\b)")
_RE_P_GRADE = re.compile(
    r"(?i)\b(?P<n>\d[\d,.]*)\s*(?P<u>%|g\s*/\s*t|gpt|ppm|ppb|oz\s*/\s*t|opt)\s*"
    r"(?:of\s+(?=[A-Za-z]))?"      # 1.0.22: "0.85 g/t of gold" -- the metal after "of", not the last one before
    r"(?P<m>[A-Za-z][A-Za-z0-9]{0,13}(?:\s?\d+[A-Za-z]?\d*)?)?")   # 1.0.23: "molybdenum", "palladium" in full
_RE_P_CONTAINED = re.compile(
    r"(?i)\b(?P<n>\d[\d,.]*)\s*(?P<mult>million|billion|thousand)?\s*"
    r"(?P<u>ounces|oz|koz|moz|pounds|lbs|lb|mlbs|mlb|klbs|klb|kt|kg|tonnes|t)\b(?!\s*/)"
    r"(?:\s*(?:\(\"?[^)\"]{0,10}\"?\))?\s*(?:of\s+)?(?:contained\s+)?(?P<m>[A-Za-z][A-Za-z0-9]{0,8})?)?")
# "increased by 2.57 million tonnes of ore" states a change, not a level
_RE_BARE_DELTA = re.compile(r"(?i)\b(?:an?\s+)?(?:increase|decrease|addition|reduction)\s+of\b|\bsensitivit\w*|"
                            r"\b(?:ranging|range)\b")   # 1.0.23 FIX3
_RE_DELTA = re.compile(r"(?i)\b(increas\w+\s+by|decreas\w+\s+by|grew\s+by|fell\s+by|"
                       r"year[\s-]on[\s-]year|net\s+of|depletion|compared\s+(?:to|with)|"
                       r"versus|up\s+from|down\s+from|addition\s+of)\b")
# A percentage is only a grade when nothing after it says otherwise. Two families sit right after
# the figure, where _RE_DELTA never looked because it reads the words BEFORE one:
#   a change  -- "693% increase in Inferred tonnes", how Class 1 Nickel writes every highlight
#   a share   -- "99.5% recovery", "63% of the contained metal", a recovery or a proportion
# The match is anchored at the character after the unit, so a real grade is never caught: in
# "1.02% Ni of the Indicated category" the metal sits in between (RES 1.0.17, 2026-09-18).
_RE_DELTA_AFTER = re.compile(r"(?i)^\s*(?:increase|decrease|growth|reduction|gain|decline|drop|"
                             r"rise|fall|improvement|uplift|higher|lower|greater|more|less|"
                             r"above|below|recovery|recoveries|recovered|recovery\s+rate|"
                             r"dilution|payable|of\s+the|of\s+total|of\s+all)\b")
_RE_NOT_GRADE_BEFORE = re.compile(r"(?i)\b(?:recover(?:y|ies|ed)|dilution|payab\w*|strip\s+ratio|of\s+which)"
                                  r"\b[^\d.;]{0,12}$")
_RE_CONTAINED_MARK = re.compile(
    r"(?i)\b(containing|contains|comprising|for|totalling|totaling|totals?|includes?|including|"
    r"contained|"
    # 1.0.23 FIX3: "Reserves stand at 5.56 Moz of gold", "Inferred Resources increased to 3.6 Moz of gold"
    r"stand\s+at|stands\s+at|stood\s+at|(?:increased|decreased|grew|rose|fell)\s+to|amount(?:s|ed)?\s+to)\b")


def _num(raw, mult_word=None, unit_mult=1.0):
    try:
        v = float(str(raw).replace(",", "").rstrip("."))
    except ValueError:
        return None
    if mult_word:
        v *= _MULT_WORD.get(mult_word.lower(), 1.0)
    return v * unit_mult


_METAL_STOP = set("""and or of for the a an at with in to per from containing contains total
grading averaging average grade cut off within including includes plus is are was were be been
million thousand billion tonnes tonne ounces pounds category categories estimated""".split())


def _metal_near(token, window, before_pos, after_text=""):
    """The metal a figure belongs to: the word after it, else the nearest one before it.

    'at 1.02% Sb and 1.06 g/t Au' reads Sb then Au. Getting this off by one -- which an over-greedy
    capture did -- silently relabels every grade in the sentence."""
    if token:
        tok = token.strip()
        if tok.lower().split()[0] not in _METAL_STOP:
            got = metal_of(tok.replace(" ", ""))
            if not got and re.match(r"[A-Za-z]{2,}", tok):
                # 1.23: "0.78% Cu\n2" (a footnote marker), "0.015% molybdenum" read in full
                got = metal_of(re.match(r"[A-Za-z]+", tok).group(0))
            if got and not got[1] and re.match(r"(?i)\s*(?:\w+\s+)?equiv|\s*eq\b", after_text or ""):
                return (got[0] + "Eq", True)
            if got:
                return got
    tail = window[max(0, before_pos - 60):before_pos]
    words = re.findall(r"[A-Za-z][A-Za-z0-9]{1,14}", tail)[::-1]
    for i, w in enumerate(words):
        got = metal_of(w)
        if got:
            # 1.0.23: "396,468 ounces gold equivalent at 0.99 g/t" -- an equivalent grade, not gold's
            if not got[1] and i and re.fullmatch(r"(?i)equiv\w*|eq", words[i - 1]):
                return (got[0] + "Eq", True)
            return got
    return (None, False)


def _parse_window(win: str) -> dict:
    out = {"tonnes": None, "grades": [], "contained": []}
    pending_metal = []
    for m in _RE_P_TONNES.finditer(win):
        if m.group("pre") and not m.group("soft"):
            continue
        # "3.3 kt of lead" is metal whatever comes in front of it; only "for"/"totalling" were
        # checked, and Vizsla's 31.6 kt of lead was published as an Indicated tonnage (1.0.19)
        u = (m.group("u") or "").lower()
        mult = {"mt": 1e6, "kt": 1e3}.get(u, 1.0)
        if u in ("tons", "ton"):
            mult = 0.90718474
        v = _num(m.group("n"), m.group("mult"), mult)
        after_u = win[m.end("u"):m.end("u") + 24]
        if _metal_in_front(win, m.start("n")):
            continue
        # "resulted in a decrease of 7.96 million tonnes in the Inferred resources" (1.0.19)
        if re.search(r"(?i)\b(?:increase|decrease|reduction|decline|drop|growth|gain|addition)s?\s+"
                     r"(?:of|by)\s+(?:approximately\s+|about\s+|~\s*)?$", win[max(0, m.start("n") - 40):m.start("n")]):
            continue
        if _tonnes_are_metal(after_u):
            # kept as what it is -- a brine's "48 kt LCE" is its contained metal, not its ore
            if v and not m.group("soft") and not m.group("pre"):
                met = metal_of(_RE_AFTER_TONNES.match(after_u).group("m"))
                pending_metal.append({"metal": met[0] if met else None, "value": v, "unit": "t"})
            continue
        if v and v >= 1:
            out["tonnes"] = v
            break
    for m in _RE_P_GRADE.finditer(win):
        v = _num(m.group("n"))
        if v is None:
            continue
        # "at a 500 ppm cut-off grade" states the cut-off, not the grade of the resource. The
        # phrase has to be the next thing after the figure, with no other number in between, or
        # every grade in "697 ppm Li at a 500 ppm cut-off" would go with it.
        after = win[m.end("u"):m.end("u") + 30]
        mm = re.search(r"(?i)cut[\s-]?off|\bcog\b", after)
        if (mm and not re.search(r"[\d,;]", after[:mm.start()])) \
                or _RE_CUTOFF.search(win[max(0, m.start() - 22):m.start()]):
            continue
        # "693% increase in Inferred tonnes" is a change, not a grade
        if _RE_DELTA_AFTER.match(after):
            continue
        # "Recovery: 81.5% Li2O" -- a label in front of the figure says what it is just as well as
        # a word after it; Imagine Lithium's recovery was published as a second Li2O grade (1.0.19)
        if _RE_NOT_GRADE_BEFORE.search(win[max(0, m.start() - 24):m.start()]):
            continue
        # "Inferred resources have also grown by 63%" -- a change (Abitibi, 1.0.19)
        if re.search(r"(?i)\bby\s+$", win[max(0, m.start() - 6):m.start()]):
            continue
        # no ore is 100% metal: a percentage that high is a share, a recovery or a change,
        # whatever word follows it
        if "%" in (m.group("u") or "") and v >= 100:
            continue
        met, eq = _metal_near(m.group("m"), win, m.start(), win[m.end():m.end() + 16])
        unit = _GRADE_UNITS.get((m.group("u") or "").lower().replace(" ", ""), m.group("u"))
        if met == "Li2O" and unit in ("ppm", "ppb") and re.match(r"(?i)lithium\b", m.group("m") or ""):
            met = "Li"            # 1.0.23: "669 ppm lithium" in a brine is lithium, not its oxide
        g = {"metal": met, "value": v, "unit": unit, "eq": eq}
        if _impossible_pct(g) or _implausible_gpt(g):
            continue
        out["grades"].append(g)
    mark = _RE_CONTAINED_MARK.search(win)
    # "34.5 million tonnes averaging 0.46 g/t Au (514,000 oz. Au)" -- the bracket after the grade
    # holds the contained metal as surely as "for" or "containing" does (1.0.19)
    if not mark:
        mark = next((x for x in re.finditer(
            r"(?i)\d\s*(?:g\s*/\s*t|gpt|%|ppm)\s*(?P<m>[A-Za-z][A-Za-z0-9]{0,5})\.?\s*(?=\(\s*\d)", win)
            if metal_of(x.group("m"))), None)
    if mark:
        for m in _RE_P_CONTAINED.finditer(win, mark.end()):
            # 1.0.23 FIX3: "stood at 3.3 Moz of gold, including 0.68 Moz in Frasers": what follows "including" is
            # a part of the figure already read
            if out["contained"] and re.search(r"(?i)\b(?:including|includes|of\s+which)\b", win[mark.end():m.start()]) \
                    and not re.search(r"(?i)\b(?:including|includes|of\s+which)\b", win[mark.start():mark.end()]):
                break
            u = (m.group("u") or "").lower()
            base, umult = _CONTAINED_UNITS.get(u, (None, None))
            if base is None:
                continue
            v = _num(m.group("n"), m.group("mult"), umult)
            if v is None:
                continue
            # a tonne-unit figure is contained METAL only when a metal follows it. Without this
            # the ore tonnage is published twice: once as tonnes and once as tonnes of the metal
            # the release happens to be about, because _metal_near falls back to the nearest
            # metal BEFORE the figure when nothing follows it.
            if base == "t" and not _tonnes_are_metal(win[m.end("u"):m.end("u") + 24]):
                continue
            met, _eq = _metal_near(m.group("m"), win, m.start(), win[m.end():m.end() + 16])
            out["contained"].append({"metal": met, "value": v, "unit": base})
    for x in pending_metal:
        if not any(c["unit"] == "t" and abs(c["value"] - x["value"]) < 1e-6 for c in out["contained"]):
            out["contained"].append(x)
    return out


# where one category's clause ends and the next begins: "..., and 5.3 Mt", "and 839,000 tons",
# "and an additional 515,000 ounces", "and 1,614,000 Inferred ounces" (RES 1.0.19, 2026-09-22)
_RE_CLAUSE_JOIN = re.compile(
    r"(?i)(?:,\s*)?\b(?:and|plus)\s+(?:an?\s+(?:additional|further)\s+)?"
    r"(?=\d[\d,.]*\s*(?:million|billion|thousand)?\s*(?:(?:measured|indicated|inferred|proven|probable)\s+)?"
    r"(?:tonnes|tonne|tons|mt|kt|ounces|oz|koz|moz)\b)")


_RE_JOIN_QTY = re.compile(r"(?i)\d[\d,.]*\s*(?:million|billion|thousand)?\s*"
                         r"(?:(?:measured|indicated|inferred|proven|probable)\s+)?"
                         r"(?P<u>tonnes|tonne|tons|mt|kt|ounces|oz|koz|moz)\b")


# "..., 168.2 koz of gold, and 11.6 Moz of silver in the indicated category, and 246.0 Mlbs of
# copper, ..., and 1.7 Moz of silver in the Inferred category" -- a list of metals, not clauses
_RE_METAL_QTY = re.compile(r"(?i)\d[\d,.]*\s*(?:million|billion|thousand)?\s*"
                           r"(?:ounces|oz|koz|moz|pounds|lbs?|mlbs?|klbs?)\b")


def _clause_split(part, lo, hi):
    """The first clause join between two category labels, outside brackets, or None."""
    for m in _RE_CLAUSE_JOIN.finditer(part, lo):
        if m.start() >= hi:
            break
        seg = part[lo:m.start()]
        if seg.count("(") > seg.count(")"):
            continue
        q = _RE_JOIN_QTY.match(part, m.end())
        if q is None:
            continue
        # "3.3 kt of lead, and 7.9 kt of zinc" lists metal, not the next clause
        oz = q.group("u").lower() in ("ounces", "oz", "koz", "moz")
        if not oz and _tonnes_are_metal(part[q.end():q.end() + 24]):
            continue
        # "LCE of 3.75 Mt Indicated and 1.09 Mt Inferred": the second figure is what the first is
        if not oz:
            prev = list(_RE_P_TONNES.finditer(part, 0, lo))
            if prev and _metal_in_front(part, prev[-1].start("n")):
                continue
        # ounces join metals as often as clauses: "506,052 ounces of gold and 7.8 million ounces
        # of silver plus an Inferred ..." -- a connector before the next label means a list
        if oz and _RE_METAL_QTY.search(part[lo:m.start()]):
            continue
        if oz:
            rest = re.sub(r"\([^)]*\)", " ", part[q.end():hi])
            if re.search(r"(?i)\b(?:and|plus)\b|,", rest):
                continue
        return m.start()
    return None


def _tonnage_before(before):
    """The tonnage nearest the end of `before`, as (value, start) -- ore, not metal -- or None."""
    for m in reversed(list(_RE_P_TONNES.finditer(before))):
        if _tonnes_are_metal(before[m.end("u"):m.end("u") + 24]) or _metal_in_front(before, m.start("n")):
            continue
        u = (m.group("u") or "").lower()
        mult = {"mt": 1e6, "kt": 1e3}.get(u, 1.0)
        if u in ("tons", "ton"):
            mult = 0.90718474
        v = _num(m.group("n"), m.group("mult"), mult)
        if v and v >= 1:
            return v, m.start("n"), len(before) - m.end()
    return None


def _parse_clause(before, after):
    """One clause, label in the middle. The tonnage nearest the label is the clause's: "4,290,000
    tons in the Indicated Category grading 0.062%" has it in front, "185,000 ounces in the Indicated
    category (5.66Mt @ 1.02 g/t)" behind. Grades go with the tonnage when they follow it in front of
    the label, else they are the ones after the label."""
    got = _parse_window(after)
    tb = _tonnage_before(before)
    if tb is None:
        # "now stands at 5.81 Moz Indicated and 26.00 Moz Inferred": contained metal only, in front
        if got["tonnes"] is None and not got["contained"]:
            last = list(_RE_P_CONTAINED.finditer(before))
            if last and len(before) - last[-1].end() <= 3:
                v = _num(last[-1].group("n"))
                got["contained"] = [c for c in _parse_window(before)["contained"]
                                    if v and abs(c["value"] - v * round(c["value"] / v)) < 1e-6
                                    and round(c["value"] / v) in (1, 1000, 1000000)][-1:]
        return got
    if got["tonnes"] is not None:
        m = _RE_P_TONNES.search(after)
        if m is not None and m.start("n") <= tb[2]:
            return got
    seg = _parse_window(before[tb[1]:])
    got["tonnes"] = tb[0]
    if seg["grades"]:
        got["grades"] = seg["grades"]
    if seg["contained"]:
        got["contained"] = seg["contained"]
    # "1.16 Moz at 1.90 g/t Au within 19.0 MT Indicated": the grade is in front of the tonnage
    if not got["grades"] or not got["contained"]:
        whole = _parse_window(before)
        got["grades"] = got["grades"] or whole["grades"]
        got["contained"] = got["contained"] or whole["contained"]
    return got


# 1.0.23: helpers of read_prose
def _right_before(before, tb):
    """The tonnage stands right in front of the category: "16 Mt indicated", "270 kt of Proven"."""
    return tb[2] <= 3 or tb[2] <= 8 and bool(re.fullmatch(r"[\s)\"']*(?:of\s+)?(?:the\s+)?", before[len(before) - tb[2]:]))


def _joined_categories(part, hits):
    """Indexes k where category k and k+1 are named together as one ("indicated and inferred", "Indicated plus
    Inferred", "measured, indicated and inferred"), unless the sentence splits the figure ("... respectively")."""
    if re.search(r"(?i)\brespectively\b", part):
        return set()
    return {k for k in range(len(hits) - 1)
            if re.fullmatch(r"(?i)\s*(?:,\s*)?(?:and|&|\+|plus|or|,)\s*", part[hits[k].end():hits[k + 1].start()])}


def _combined_row(part, hits, k, joined):
    """One Total row for the categories named together from hit k on; None when the sentence gives it no figure."""
    j = k
    while j in joined:
        j += 1
    hs, he = hits[k].start(), hits[j].end()
    nxt = hits[j + 1].start() if j + 1 < len(hits) else len(part)
    prv = hits[k - 1].end() if k else 0
    trailing = bool(_RE_TRAILING.match(part[he:he + 6])) or bool(_RE_TRAILING_BEFORE.search(part[max(0, hs - 10):hs]))
    got = _parse_window(part[prv:hs] if trailing else part[he:nxt])
    if got["tonnes"] is None and not trailing:
        tb = _tonnage_before(part[prv:hs])
        if tb is not None and _right_before(part[prv:hs], tb):
            got["tonnes"] = tb[0]
    if got["tonnes"] is None and not got["contained"]:
        return None
    r = _row(None, "Total", "prose", hs)
    r["_win"], r["_combined"] = part, True
    r["tonnes"] = _metric_tons(part, got)
    r["grades"] = [{"metal": x["metal"], "value": x["value"], "unit": x["unit"]} for x in got["grades"]]
    r["contained"] = got["contained"]
    r["cut_off"] = cutoff_in(part)
    if _RE_RESERVE_WORD.search(part) and not _RE_RESOURCE_WORD.search(part):
        r["basis"] = "reserve"
    return r


def _metric_tons(part, got):
    """"969,000 tons at 2.25 g/t ... 69,600 oz": tons whose ounces reconcile at the stated grade in metric tonnes and
    not in short tons are metric tonnes."""
    t = got.get("tonnes")
    gpt = [g["value"] for g in got.get("grades") or [] if g["unit"] == "g/t" and g["value"]]
    if not t or not gpt or not re.search(r"(?i)\btons?\b", part):
        return t
    for m in re.finditer(r"(?i)\b(\d[\d,.]*)\s*(million|thousand)?\s*tons?\b", part):
        raw = _num(m.group(1), m.group(2))
        if not raw or abs(raw * 0.90718474 - t) > 1e-3 * t:
            continue
        ozs = [_num(o.group(1), o.group(2), {"koz": 1e3, "moz": 1e6}.get(o.group(3).lower(), 1.0))
               for o in re.finditer(r"(?i)\b(\d[\d,.]*)\s*(million|thousand)?\s*(oz|ounces|koz|moz)\b", part)]
        for g in gpt:
            fits = lambda tt: any(o and abs(tt * g / 31.1035 - o) <= 0.03 * o for o in ozs)
            if fits(raw) and not fits(t):
                return raw
    return t


def read_prose(text: str) -> list:
    """Rows from sentences: 'Inferred Mineral Resource of 6.5 Mt at 1.02% Sb for 67 kt of antimony'."""
    rows = []
    base = 0        # 1.0.22: where each line starts in the text, so every row knows where it was read
    for line in text.split("\n"):
        lbase, base = base, base + len(line) + 1
        cur = 0
        for part in re.split(r"(?<=[.;])\s+", line):
            part = part.strip()
            at = line.find(part, cur) if part else -1
            if at >= 0:
                cur = at + len(part)
            at = lbase + max(at, 0)
            if len(part) < 20 or len(part) > 460 or not _RE_RES_WORD.search(part):
                continue
            if _RE_DELTA.search(part):
                continue
            hits = list(_RE_CAT_WORD.finditer(part))
            # 1.0.22: 'Measured and Indicated ("M&I")' defines the abbreviation; it is one label, not two
            hits = [h for k, h in enumerate(hits)
                    if not (k and re.fullmatch(r'\s*\(\s*"?\s*', part[hits[k - 1].end():h.start()]))
                    # "... after converting 0.91 Moz to M&I": where metal moved to, not a label for the figure
                    and not re.search(r"(?i)\b(?:convert\w*|conversion|upgrad\w*|reclassif\w*|transferr?\w*|migrat\w*)\b"
                                      r"[^;]{0,50}\b(?:to|into)\s+(?:the\s+)?$", part[max(0, h.start() - 70):h.start()])]
            if not hits:
                continue
            # 1.0.23: "an indicated and inferred resource of 69,600 oz", "an Indicated plus Inferred resource of
            # 5.3Mt": one figure for two categories together is their total, never either one (filed as Total)
            joined = _joined_categories(part, hits)
            splits = [_clause_split(part, hits[k].end(), hits[k + 1].start())
                      for k in range(len(hits) - 1)]
            for k, h in enumerate(hits):
                if k - 1 in joined:
                    continue
                canon = None
                for name, pat in _CAT_CANON:
                    if re.fullmatch("(?i)" + pat, h.group(1).strip()):
                        canon = name
                        break
                if canon is None:
                    continue
                if k in joined:
                    r = _combined_row(part, hits, k, joined)
                    if r is not None:
                        r["_at"], r["_part_at"] = at + h.start(), at
                        r["_proj"], r["_proj_kind"] = project_and_kind(part)
                        rows.append(r)
                    continue
                nxt = hits[k + 1].start() if k + 1 < len(hits) else len(part)
                prv = hits[k - 1].end() if k else 0
                trailing = bool(_RE_TRAILING.match(part[h.end():h.end() + 6])) \
                    or bool(_RE_TRAILING_BEFORE.search(part[max(0, h.start() - 10):h.start()]))
                win = part[prv:h.start()] if trailing else part[h.end():nxt]
                got = _parse_window(win)
                # A sentence that lists one clause per category -- "3.1 Mt grading 0.85% Li2O in the
                # Indicated category and 5.3 Mt grading 0.91% Li2O in the Inferred category" -- has
                # its figures on either side of the label. Reading only one side filed Imagine
                # Lithium's 5.3 Mt as Indicated and Noble Plains' 839,000 tons at the Indicated
                # grade. Where "and <quantity>" marks where one clause ends, the clause decides.
                lsp = splits[k - 1] if k else None
                rsp = splits[k] if k + 1 < len(hits) else None
                if lsp is not None or rsp is not None:
                    left = lsp if lsp is not None else prv
                    right = rsp if rsp is not None else nxt
                    got = _parse_clause(part[left:h.start()], part[h.end():right])
                    win = part[left:right]
                elif got["tonnes"] is None and not trailing:
                    # "outlines a 930,000 tonnes inferred resource ... containing 13,400,000 lbs Cu"
                    before = part[prv:h.start()]
                    tb = _tonnage_before(before)
                    # "Greater than 1 billion tonne Inferred Resource" is a bound, not the estimate
                    if tb is not None and _right_before(before, tb) and not re.search(
                            r"(?i)\b(?:greater|more)\s+than\s*$|\bover\s*$|\bup\s+to\s*$|[>~]\s*$",
                            before[:tb[1]]):
                        got["tonnes"] = tb[0]
                elif got["tonnes"] is not None and not trailing:
                    # 1.0.23: "16 Mt indicated grading 0.66% CuEq ... 34 Mt inferred grading ...": the tonnage
                    # written right in front of the category is its own; the one after its grades is the next one's
                    before = part[prv:h.start()]
                    tb = _tonnage_before(before)
                    after = part[h.end():nxt]
                    ta, ga = _RE_P_TONNES.search(after), _RE_P_GRADE.search(after)
                    if tb is not None and _right_before(before, tb) and ta and ga and ga.start() < ta.start() \
                            and not re.search(r"(?i)\b(?:greater|more)\s+than\s*$|\bover\s*$|\bup\s+to\s*$|[>~]\s*$",
                                              before[:tb[1]]):
                        got["tonnes"] = tb[0]
                        # "with a 1.72g/t Au average within 993,000t indicated resource, and with a 1.59g/t average
                        # within a 1,703,000t inferred resource": the grades of the clause in front are its own
                        joins = [j.end() for j in re.finditer(r",\s*(?:and|plus)\b|;", before[:tb[1]])]
                        if not k or joins:
                            gb = _parse_window(before[(joins[-1] if joins else 0):tb[1]])["grades"]
                            if gb:
                                got["grades"] = gb
                got["tonnes"] = _metric_tons(part, got)
                if got["tonnes"] is None and not got["contained"]:
                    continue
                r = _row(None, canon, "prose", h.start())
                r["_win"] = part
                r["_at"], r["_part_at"] = at + h.start(), at
                # Adyton restates Feni Island beside the Wapolu estimate it is announcing. Falling
                # back to the release's project put Feni Island's 60.4 Mt under Wapolu.
                r["_proj"], r["_proj_kind"] = project_and_kind(part)
                r["tonnes"] = got["tonnes"]
                r["grades"] = [{"metal": x["metal"], "value": x["value"], "unit": x["unit"]}
                               for x in got["grades"]]
                r["contained"] = got["contained"]
                r["cut_off"] = cutoff_in(part)
                if canon in ("Proven", "Probable", "Proven & Probable") or (
                        _RE_RESERVE_WORD.search(part) and not _RE_RESOURCE_WORD.search(part)):
                    r["basis"] = "reserve"
                rows.append(r)
    return rows


# ------------------------------------------------------------------ release-level judgement
_RE_ANNOUNCES = re.compile(r"(?i)\b(mineral\s+resources?|resource\s+estimate|mre\b|mineral\s+reserves?|"
                           r"reserve\s+estimate|s-k\s*1300|resources?\s+and\s+reserves?|"
                           r"(?:maiden|initial|inaugural|updated?|indicated|inferred|measured)\s+"
                           r"(?:\w+\s+){0,2}resources?|resources?\s+of\s+\d)", re.I)
_RE_NOT_ANNOUNCING = re.compile(
    r"(?i)\b(drill(ing)?\s+(results?|programme?|intercepts?)|intersects?|intercepts?|"
    r"commenc\w+|engages?\b|to\s+complete|nears?\s+completion|impending|imminent|upcoming|"
    r"planned|set\s+to\b|moving\s+into|expansion\s+drill|infill\s+drill|"
    r"exploration\s+potential|new\s+zones?\s+of)\b")
_RE_OTHER_NEWS = re.compile(
    r"(?i)\b(?:resign\w*|appoint\w*|director|officer|ceo|cfo|conference|present(?:s|ing|ation)?\s+at|webinar|summit|"
    r"private\s+placement|financing|flow[\s-]through|warrants?|stock\s+options?|option\s+grant|share\s+(?:issu\w+|"
    r"consolidation)|shares\s+for\s+debt|interest\s+payment|annual\s+general|agm\b|drill\s+rig|mobiliz\w+|"
    r"listing|lists\s+on|name\s+change|quarterly\s+(?:filing|financial)|financial\s+(?:statements|results))\b")
_RE_STUDY_NEWS = re.compile(r"(?i)technical\s+report|43-101|feasibility|economic\s+assessment|\bpea\b|\bpfs\b")
_RE_MAIDEN = re.compile(r"(?i)\b(maiden|initial|inaugural|first(?:-ever)?|debut)\b")
_RE_UPDATE = re.compile(r"(?i)\b(updated?|increases?|increased|expand\w*|grow\w*|revis\w*|"
                        r"restat\w*|upgrad\w*|significantly\s+increases)\b")
_RE_FILING = re.compile(r"(?i)\b(files?|filing|publishes?|submitt?ed)\b")
_RE_BACKGROUND = re.compile(
    r"(?i)\b(previously\s+(?:reported|announced|disclosed|stated|released)|historical(?:ly)?|"
    r"historic\b|prior\s+(?:estimate|resource)|currently\s+(?:has|hosts|carries)|"
    r"existing\s+(?:mineral\s+)?resource|was\s+first\s+reported|first\s+reported\s+in|"
    r"inventory\b|portfolio\s+of\s+projects|across\s+its\s+projects)\b"
    # "within areas of historic drilling" dates the drilling, not the estimate (1911 Gold, 1.0.19)
    r"(?!\s+(?:drill\w*|workings?|mining|mine\b|production|data|shafts?|underground|sampl\w*))")


def _own_bullet(r):
    """The bullet a prose row was read from. A run of bullets reaches us as one sentence; the
    word that marks an estimate as old has to be in the row's own bullet."""
    win = r.get("_win") or ""
    if r.get("source") != "prose":
        return win
    pos = r.get("pos") or 0
    lo = max((m.end() for m in re.finditer(r"[\u2022\u25aa\u25a0]", win[:pos])), default=0)
    m = re.search(r"[\u2022\u25aa\u25a0]", win[pos:])
    return win[lo:pos + m.start()] if m else win[lo:]


_RE_PROJECT = re.compile(
    r"(?i)(?:^|\b)(?:at|for|on|of|to|the|its|their|our)\s+"
    r"(?:its|the|their|our|100%[\s-]?owned|wholly[\s-]?owned)?\s*"
    r"((?:[A-Z][\w'\u2019\-\.]*|\d+)"
    r"(?:\s+(?:[A-Z][\w'\u2019\-\.]*|\d+|and|de|del|la|el|y)){0,3})\s+"
    r"(projects?|deposits?|mines?|properties|property|zones?|prospects?|royalty|veins?|pits?|"
    r"targets?|districts?|complex|claims?)\b")


# 1.0.23: a headline verb read as the first word of a project name
_RE_HEAD_VERB = re.compile(r"(?i)(?:intersects?|updates?|staking|stakes?|drills?|drilling|expands?|extends?|acquires?|"
                           r"announces?|reports?|completes?|commences?|begins?|starts?|continues?|confirms?|defines?|"
                           r"discovers?|identifies|identify|receives?|signs?|files?|closes?|provides?)\b")


def release_project(headline: str, body_head: str = "") -> str | None:
    for src in (headline or "", body_head or ""):
        m = _RE_PROJECT.search(src)
        if m and re.fullmatch(r"(?i)intellectual\s+propert(?:y|ies)", m.group(1) + " " + m.group(2)):
            m = _RE_PROJECT.search(src, m.end())    # 1.0.23: intellectual property is no mineral property
        if m:
            name = _WS.sub(" ", m.group(1)).strip(" ,.;:-")
            name = re.sub(r"(?i)^(?:producing|past[\s-]?producing|former|new|flagship|"
                          r"wholly[\s-]?owned|100%[\s-]?owned|its|the|company's)\s+", "", name)
            name = re.sub(r"(?i)[\s,]+(?:and|or|de|del|la|el|y)\s*$", "", name).strip(" ,.;:-")
            name = _named(name)
            if name and not _CLASS_WORD.match(name) and len(name) > 2:
                return name
    return None


# a release describes its project before it names it, and "one of the Highest-Grade Open Pitable
# Copper Projects in Canada" is a description. A name made only of these is not a name.
_NOT_A_NAME = set("""high higher highest low lower lowest grade grades open pit pitable pits large
larger largest small robust significant significantly new newly modeled modelled potential key
main core flagship advanced near nearby long longer district scale world class
tier leading premier emerging growing producing past total combined initial maiden updated
first second third best quality strategic critical major minor multiple several other various
underground surface bulk global regional local
disclosure standards standard instrument national report reports technical summary statement
company companies corporation corp inc ltd limited plc holdings issuer news release
filing filings sedar sedarplus""".split())


# A deposit has a name. These say the candidate is a piece of a sentence instead: a verb it opens
# on, a finite verb inside it, the vocabulary of a qualified person or a company, a bullet, or a
# quote that never closes. Seventeen such names reached the page at 1.0.17, through all three of
# the paths that produce a deposit, which is why the test lives in qualify() where they all meet.
_RE_CLAUSE_VERB = re.compile(r"(?i)^(?:accompany|acquire|acquires|announce[sd]?|based|comprise[sd]?|"
                             r"contain[sd]?|filed|includ(?:e|es|ing)|locat(?:e|ed)|please|prepared|"
                             r"present(?:s|ed)?|provide[sd]?|pursuant|refer|report(?:s|ed)?|represent[sd]?|"
                             r"review|see|us(?:e|ed|ing))\b")
_RE_CLAUSE_IN = re.compile(r"(?i)\b(?:has\s+an?|have\s+an?|is\s+the|are\s+in|was\s+the|were\s+in|"
                           r"selected\s+as|for\s+additional|pursuant\s+to|refer\s+to|"
                           r"in\s+accordance|revenue\s+factor|per\s+recovered)\b")
_RE_CLAUSE_CORP = re.compile(r"(?i)(?:\bInc\b|\bLtd\b|\bLLC\b|\bLLP\b|\bPLC\b|\bCorp\b|"
                             r"\bConsulting\b|\bConsultants\b|qualified\s+person)")
_RE_EFFECTIVE = re.compile(r"(?i)[\s,(-]*\beffective\b[^)]*\)?\s*$")
_NAME_PARTICLE = {"la", "le", "el", "de", "del", "da", "do", "du", "von", "van", "der", "den"}


def _place(name):
    """The name of a place, or None when the candidate is a piece of a sentence."""
    if not name:
        return name
    # "Guillermina Deposit (effective March 31, 2025)" is a name wearing a date, not a clause
    # NOT "()" in the strip set: that ate the closing bracket off every scenario-qualified name,
    # turning "Opemiska (Pit Constrained)" into "Opemiska (Pit Constrained". _RE_EFFECTIVE already
    # consumes its own opening bracket.
    s = _RE_EFFECTIVE.sub("", name).strip(" ,.;:-")
    if not s:
        return None
    if s[0] in "\u2022\u00b7*-\u2013\u2014" or s.count('"') % 2 or s.count("\u201d") != s.count("\u201c"):
        return None
    # "wholly owned Eagle", "tonnes in Alexo South", "historic Bayhorse Silver" are a name with the
    # tail of a sentence still attached to the front. deposit_name() strips leading lower-case words
    # for exactly this reason; doing it here as well RECOVERS the name instead of discarding the
    # row's deposit, which over the 387 names on the page is the difference between nine real
    # deposits being kept and nine rows falling back to their project name.
    while True:
        m = re.match(r"^([a-z][\w'-]*)\s+(?=\S)", s)
        # a particle belongs to the name it precedes: "la Fortuna", "del Toro"
        if not m or m.group(1).lower() in _NAME_PARTICLE:
            break
        s = s[m.end():]
    s = s.strip(" ,.;:-")
    if not s:
        return None
    if _RE_CLAUSE_VERB.match(s) or _RE_CLAUSE_IN.search(s) or _RE_CLAUSE_CORP.search(s):
        return None
    first = re.split(r"[\s,;/]+", s)[0]
    if first[:1].islower() and first.lower() not in _NAME_PARTICLE:
        return None
    # not _named() here: it rejects a name whose first word is descriptive, which is right for a
    # project ("Highest-Grade Open Pitable Copper") and wrong for a deposit -- it turns down "Pit 1".
    return s


def _named(name):
    """A project name has at least one word that is a name rather than a description."""
    toks = [t for t in re.split(r"[\s,;/]+", name or "") if t]
    if not toks:
        return None
    while toks and toks[-1].lower() in ("and", "or", "de", "del", "la", "el", "y"):
        toks.pop()
    if not toks or not any(t[:1].isupper() for t in toks):
        return None

    def descriptive(t):
        parts = [x for x in re.split(r"[-/]", re.sub(r"[^a-z-/]", "", t.lower())) if x]
        return bool(parts) and all(x in _NOT_A_NAME for x in parts)

    # a name that opens on a description is a description: "Highest-Grade Open Pitable Copper"
    if descriptive(toks[0]) or all(descriptive(t) for t in toks):
        return None
    return " ".join(toks)


# symbols too easily struck by an ordinary word to carry a release on their own
_NEVER_INFERRED = {"Ir", "Os", "Ru", "Y", "W", "V", "U", "C", "S", "P", "Be", "Sr", "La", "Ce"}


_PRECIOUS_NAMES = {"gold": "Au", "silver": "Ag", "platinum": "Pt", "palladium": "Pd"}
_BASE_NAMES = {"copper": "Cu", "nickel": "Ni", "zinc": "Zn", "cobalt": "Co", "lithium": "Li2O", "antimony": "Sb",
               "tungsten": "WO3", "molybdenum": "Mo", "uranium": "U3O8", "graphite": "C", "vanadium": "V2O5",
               "manganese": "Mn", "tin": "Sn"}


def _metal_by_unit(text):
    """{unit: metal} for the units whose metal the whole release leaves in no doubt: g/t and oz when it names one
    precious metal only, % and lb when it names one base or battery metal only (1.0.22)."""
    low = text.lower()
    out = {}
    prec = [v for k, v in _PRECIOUS_NAMES.items() if re.search(r"\b" + k + r"\b", low)]
    if len(prec) == 1:
        out.update({"g/t": prec[0], "oz": prec[0], "oz/t": prec[0]})
    base = [v for k, v in _BASE_NAMES.items() if re.search(r"\b" + k + r"\b", low)]
    if len(base) == 1 and not re.search(r"\blead\b", low):
        out.update({"%": base[0], "lb": base[0]})
    return out


def release_metal(headline: str, body_head: str = "") -> str | None:
    """The metal a release is about, when it is about exactly one.

    A gold company's table often labels its grade column "Grade (g/t)" and nothing else, and a
    grade with no metal against it is a figure a reader cannot use. Where the headline names one
    metal and only one, that is the metal."""
    found = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9]{0,8}", (headline or "") + " " + (body_head or "")[:300]):
        if len(w) <= 2 and w not in _SYMBOLS:
            continue          # "ir@adytonresources.com" is not iridium
        got = metal_of(w)
        if got and not got[1] and got[0] not in _NEVER_INFERRED:
            found.add(got[0])
    return next(iter(found)) if len(found) == 1 else None


# a block of one deposit reported under one set of mining assumptions
_RE_SCENARIO = re.compile(r"(?i)\b(pit[\s-]?constrained|constrained|open[\s-]?pit|out[\s-]?of[\s-]?pit|"
                          r"in[\s-]?pit|underground|hybrid|scenario|starter|stockpile|"
                          r"total\s+resources?)\b")
_ZONE_NOUNS = ("zone", "zones", "pegmatite", "pegmatites", "vein", "veins", "lens", "lode")


def project_and_kind(text: str):
    """(name, noun) for the first project or zone a passage names, or (None, None)."""
    m = _RE_PROJECT.search(text or "")
    # "a Consolidated Mineral Resource, which includes the Rigel and Vega caesium zones, totalling
    # 108.0 Mt" -- the zones it includes are part of the figure, not its name (Patriot, 1.0.19)
    while m and re.search(r"(?i)\b(?:includes?|including|excludes?|excluding)\s*$",
                          (text or "")[max(0, m.start() - 20):m.start()]):
        m = _RE_PROJECT.search(text, m.end())
    if not m:
        return (None, None)
    # "in the South Zone, West Zone and central part of the Gate Zone" names three zones; the
    # figure is theirs together, not the first one's (Kodiak, 1.0.19)
    if re.match(r"\s*(?:,|and\b|&)\s*(?:the\s+)?[A-Z][\w'\u2019\-]*(?:\s+[A-Z][\w'\u2019\-]*)?\s+"
                r"(?i:zones?|deposits?|pits?|veins?|targets?)\b", text[m.end():]):
        return (None, None)
    name = _WS.sub(" ", m.group(1)).strip(" ,.;:-")
    name = re.sub(r"(?i)^(?:producing|past[\s-]?producing|former|new|flagship|"
                  r"wholly[\s-]?owned|100%[\s-]?owned|its|the|company's)\s+", "", name)
    name = re.sub(r"(?i)[\s,]+(?:and|or|de|del|la|el|y)\s*$", "", name).strip(" ,.;:-")
    name = _named(name)
    if not name or _CLASS_WORD.match(name) or len(name) <= 2:
        return (None, None)
    return (name, (m.group(2) or "").lower())


def qualify(deposit, project, kind=None):
    """Project, then zone, then scenario in brackets (Justin, 2026-09-18).

    A table headed "Underground Mining Scenario" and a sentence about "the Rigel and Vega zones"
    each name half of what a reader needs. Neither is a deposit on its own, and two rows for one
    deposit under two mining assumptions have to be recognisable as the same rock."""
    deposit = _place(deposit)
    if not deposit or not project:
        return deposit
    have = set(_norm_dep(deposit).split())
    if have & set(_norm_dep(project).split()):
        return deposit
    # (1.0.22: not when the name outside the brackets is already a deposit's: "Koula (Open Pit)")
    if _RE_SCENARIO.search(deposit) and not _pn_proper(re.sub(r"\([^)]*\)|\b(?:OP|UG)\b", " ", deposit)):
        return "%s (%s)" % (project, deposit)
    if kind in _ZONE_NOUNS:
        return "%s - %s" % (project, deposit)
    return deposit


def release_announces(headline: str, body_head: str = "") -> bool:
    """Is this release reporting an estimate, or only mentioning one?

    Goldgroup's headline says only 'Files Updated Technical Report on San Francisco Gold Project'
    and the estimate is announced in the first paragraph, so the body opening counts too. What
    disqualifies a release is in the headline: drill results, a programme about to start, a
    consultant engaged to prepare an update later."""
    h = headline or ""
    # "Highlights Robust Initial Mineral Resource ... and Upcoming Drill Program" is an
    # announcement with a trailing aside; "Outstanding drilling results ..." is not an
    # announcement at all. What the headline leads with is what decides it.
    if _RE_NOT_ANNOUNCING.search(h[:70]):
        return False
    # 1.0.23: a headline about something else -- a director, a conference, a financing, a share issue, a drill rig --
    # is not made an announcement by an estimate its opening paragraph describes
    if _RE_OTHER_NEWS.search(h) and not (_RE_ANNOUNCES.search(h) or _RE_STUDY_NEWS.search(h)):
        return False
    return bool(_RE_ANNOUNCES.search(h) or _RE_ANNOUNCES.search((body_head or "")[:900]))


def mre_type(headline: str, body_head: str = "") -> str | None:
    h = (headline or "") + " " + (body_head or "")[:400]
    if _RE_MAIDEN.search(h):
        return "Maiden"
    if _RE_UPDATE.search(h):
        return "Update"
    if _RE_FILING.search(headline or ""):
        return "Restated"
    return None


def _fold(s):
    """Accents off, so Trojarova read from the headline and Trojarova read from the table are the
    same deposit. They were not, and the release published two rows instead of one."""
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _norm_dep(d):
    if not d:
        return ""
    s = re.sub(r"(?i)\b(project|deposit|mine|property|zone|prospect|the)\b", " ", _fold(d))
    return _WS.sub(" ", re.sub(r"[^\w\s]", " ", s)).strip().lower()


_SRC_RANK = {"table": 0, "rowline": 1, "prose": 2, "headline": 3}


def _is_round(t):
    return bool(t) and t >= 1000 and float("%.1g" % t) == t


def _merge_same_figures(rows):
    """Two readings of one row are one row.

    Kenorland's table names the deposit and its prose names the project, so the same 14.5 Mt was
    published twice under two names. Where the category, the basis and the figures agree, the more
    specific name wins and the duplicate goes."""
    out = []
    for r in rows:
        twin = None
        for k in out:
            if k["category"] != r["category"] or k["basis"] != r["basis"]:
                continue
            # two rows of one table under two names are two rows: East Bull's in-pit Indicated
            # 16.3 Mt and its total Indicated 16.5 Mt are 1.2% apart, and the total was lost
            # (identical figures under two names are still one row read twice)
            if k["source"] in ("table", "rowline") and r["source"] in ("table", "rowline") \
                    and k["deposit"] and r["deposit"] and _norm_dep(k["deposit"]) != _norm_dep(r["deposit"]) \
                    and k["tonnes"] and r["tonnes"] and k["tonnes"] != r["tonnes"]:
                continue
            # a headline rounds: "1 BILLION TONNE" is the body's 1,050 Mt -- and so does a body that
            # repeats its headline, so a one-figure tonnage under the same name gets the same room
            tol = 0.02
            if "headline" in (k["source"], r["source"]) or (
                    (_is_round(k["tonnes"]) or _is_round(r["tonnes"]))
                    and _norm_dep(k["deposit"]) == _norm_dep(r["deposit"])):
                tol = 0.1
            if k["tonnes"] and r["tonnes"] and _same_figures(k, r, tol):
                twin = k
                break
        if twin is None:
            out.append(r)
            continue
        if len(_norm_dep(r["deposit"]).split()) > len(_norm_dep(twin["deposit"]).split()):
            twin["deposit"] = r["deposit"]
        twin["grades"] = _union_grades(twin["grades"], r["grades"])
        _add_metals(twin, r)          # FIX5
        if not twin["contained"] and r["contained"]:
            twin["contained"] = r["contained"]
    return out


def _union_grades(a, b):
    """Patriot states its consolidated estimate twice, once with two grades and once with four.
    Where the second reading repeats every grade of the first and adds others -- each for a named
    metal, one per metal -- the row carries the fuller reading (1.0.19)."""
    if not a:
        return b
    if not b or len(b) <= len(a):
        return a
    metals = [g["metal"] for g in b]
    if None in metals or len(set(metals)) != len(metals):
        return a
    key_b = {(g["metal"], g["unit"], g["value"]) for g in b}
    if all((g["metal"], g["unit"], g["value"]) in key_b for g in a):
        return b
    return a


def _add_metals(a, b):
    """FIX5: one tonnage stated once per metal -- "an Inferred Resource of 515,700 ounces of gold at 8.85 g/t Au
    (1,813,000 tonnes) ... and an Inferred Resource of 390,600 ounces of silver at 7.33 g/t silver (1,813,000 tonnes)" --
    is one row with both grades: the second reading's metals the first lacks are added to it."""
    if not a["tonnes"] or not b["tonnes"] or abs(a["tonnes"] - b["tonnes"]) > 0.005 * max(a["tonnes"], b["tonnes"]):
        return
    have = {g["metal"] for g in a["grades"]}
    new = [g for g in b["grades"] if g["metal"] and g["metal"] not in have]
    if not a["grades"] or not new or len({g["metal"] for g in new}) != len(new) \
            or any(g["metal"] in have for g in b["grades"]):
        return
    a["grades"] = a["grades"] + [dict(g) for g in new]
    havec = {c["metal"] for c in a["contained"]}
    a["contained"] = a["contained"] + [dict(c) for c in b["contained"] if c["metal"] and c["metal"] not in havec]


def _dedupe(rows):
    """One row per deposit, category and basis. A second figure for the same three is a different
    cut-off, not a duplicate -- Cruz states its estimate at 500 ppm and again at 300 ppm."""
    groups = {}
    for r in rows:
        groups.setdefault((_norm_dep(r["deposit"]), r["category"], r["basis"]), []).append(r)
    out = []
    for key in groups:
        g = sorted(groups[key], key=lambda r: (_SRC_RANK.get(r["source"], 9), r["pos"]))
        kept = []
        for r in g:
            same = next((k for k in kept if _same_figures(k, r)), None)
            if same is None:
                kept.append(r)
            elif same["source"] != r["source"] and not same["grades"] and r["grades"]:
                same["grades"] = r["grades"]
            else:
                _add_metals(same, r)      # FIX5
        # The figure the release states in prose is the base case. A second figure for the same
        # deposit and category is only an alternative cut-off when the cut-off actually differs;
        # otherwise it is a deposit this reader failed to tell apart, and calling it an
        # alternative would put a wrong mark on a row that is simply under-named.
        # Cruz states its estimate at 300 ppm first and calls the 500 ppm case its base case.
        # The base case is the one the release says it is, not the one that comes first.
        base = next((r for r in kept if re.search(r"(?i)\bbase[\s-]?case\b", r.get("_win") or "")),
                    None)
        if base is None:
            base = next((r for r in kept if r["source"] in ("prose", "headline")),
                        kept[0] if kept else None)
        for r in kept:
            if r is base or r["context"] != "announced":
                continue
            if base is not None and r["cut_off"] and base["cut_off"] and r["cut_off"] != base["cut_off"]:
                r["context"] = "alternative cut-off"
        out.extend(kept)
    out.sort(key=lambda r: (r["pos"], r["category"]))
    return out


def _figureless(r):
    return r["tonnes"] is None and not r["grades"] and not r["contained"]


def _same_figures(a, b, tol=0.02):
    # a headline that names a category but no figure is the same row as the table that has them
    if _figureless(a) or _figureless(b):
        return True
    # Military Metals' headline carries the grades and no tonnage; the table carries both. One row.
    if (a["tonnes"] is None) != (b["tonnes"] is None):
        pairs_a = {(g["metal"], g["value"]) for g in a["grades"]}
        pairs_b = {(g["metal"], g["value"]) for g in b["grades"]}
        if pairs_a & pairs_b:
            return True
    if a["tonnes"] and b["tonnes"]:
        hi = max(a["tonnes"], b["tonnes"])
        if abs(a["tonnes"] - b["tonnes"]) > tol * hi:
            return False
        return True
    if a["tonnes"] or b["tonnes"]:
        return False
    return (a["cut_off"] or "") == (b["cut_off"] or "")


# ------------------------------------------------------------------ the whole release
# ------------------------------------------------------------------ 1.0.20: the shared project-name helper
_PN_SUF = re.compile(r"(?i)\s+(?:projects?|property|properties|claims?|concessions?|permits?|licen[cs]es?|mines?|complex|"
                     r"deposits?|prospects?|zones?|targets?|districts?|camp|underground|open[\s\-]*pit|operations?)$")
_PN_LEVEL1 = re.compile(r"(?i)\s(?:projects?|property|properties|claims?|concessions?|mines?|complex|permits?|"
                        r"licen[cs]es?|operations?)$")
_PN_REAL = (r"(?:\s+[A-Z][\w'\u2019\-]*){0,2}\s+(?:projects?|property|properties|mine|mines|claims|concessions?|complex|"
            r"deposits?|prospect|operations?)\b")
_PN_BAD_LEAD = {
    # a description, a drilling method, a number, a nationality or a corporate word is not a project
    "extend", "extends", "extending", "work", "interval", "expanded", "current", "underground", "encouraging", "strong",
    "prospect", "deposit", "reverse", "diamond", "core", "auger", "rc", "drill", "drilling", "sampling", "trenching",
    "maritime", "mining", "exploration", "regional", "land", "surface", "mineral", "main", "updated", "maiden", "initial",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "several", "both", "multiple", "new",
    "canadian", "american", "mexican", "peruvian", "chilean", "australian", "african", "brazilian", "argentine",
    "colombian", "ecuadorian", "nevada", "quebec", "ontario", "british", "global", "north", "south", "company", "group",
    "producing", "flagship", "combined", "total", "consolidated", "other", "our", "its", "the", "development",
    "outperforming", "operating", "ounce", "ounces", "million", "multi-million", "historic", "historical", "announcement",
    "classification", "high-grade", "district-scale", "previously", "announced", "controlled", "wholly", "owned", "first",
    "second", "third", "qualifying", "bonanza", "argentinian", "annual", "verification", "generate", "vertically",
    "precious", "identified", "highest-grade", "value-add", "re-scoped", "integrated", "upgraded",
    # rev 4: report words, stages, generic geology, deals
    "stage", "target", "targets", "sedar", "ownership", "geophysical", "footwall", "zone", "tailings", "option",
    "reduced", "potential", "pea", "feasibility", "develop", "advance", "large", "municipality", "a", "an",
    "portfolio", "project", "intrusion", "contact", "only", "rights", "water", "focused"}
_PN_BAD_WORD = {"option", "exercise", "coo", "ceo", "cfo", "survey", "over", "appointed", "ownership", "portfolio",
                "royalty", "stream", "financing", "placement"}
_PN_GENERIC_ONE = {"island", "lake", "creek", "mountain", "river", "hill", "belt", "valley", "point", "pond", "tailings",
                   "sudbury", "centre", "center", "north", "south", "east", "west", "main", "golden"}
_PN_METAL_WORD = r"(?:gold|silver|copper|zinc|lead|nickel|cobalt|lithium|uranium|tin|tungsten|iron|pge|pgm|au|ag|cu|zn|pb|ni|co)"
_PN_NEIGHBOUR = (r"(?i)\b(?:adjoin(?:s|ing)?|adjacent(?:\s+to)?|on\s+trend\s+(?:from|with)|neighbou?r(?:s|ing)?|next\s+to|"
                 r"contiguous\s+(?:to|with)|along\s+strike\s+(?:from|of)|near(?![\-\s]+surface)|"
                 r"(?:north|south|east|west)(?:east|west)?\s+of)\b[^.]{0,60}")
_PN_GEOLOGY = {"breccia", "pipe", "pipes", "porphyry", "vein", "veins", "system", "systems", "intrusion", "intrusive",
               "skarn", "pegmatite", "pegmatites", "dyke", "dykes", "sill", "stockwork", "shear", "fault", "trend",
               "corridor", "anomaly", "anomalies", "target", "targets", "zone", "zones", "uranium", "ree", "rare", "earth",
               "earths", "critical", "minerals", "gold", "silver", "copper", "lithium", "exploration"}
_PN_GENERIC_DEP = {
    "open", "pit", "underground", "constrained", "pit-constrained", "out", "of", "total", "combined", "base", "case",
    "oxide", "sulphide", "sulfide", "transition", "fresh", "tailings", "stockpile", "stockpiles", "heap", "leach", "in",
    "situ", "in-situ", "and", "the", "measured", "indicated", "inferred", "resource", "resources", "mineral", "estimate",
    "high", "low", "grade", "high-grade", "scenario", "mining", "surface", "deep", "shallow", "global", "main", "zone",
    "zones", "deposit", "project", "area", "north", "south", "east", "west", "central", "upper", "lower", "near",
    "satellite", "satellites", "primary", "hard", "rock", "saprolite", "laterite", "vein", "veins", "including",
    "excluding", "inclusive", "exclusive", "cut-off", "out-of-pit", "pit-shell", "shell", "optimised", "optimized"}
_PN_VERB = re.compile(r"(?i)\b(?:introduces|announces|reports|files|acquires|aqcuires|acquired|completes|expands|increases|"
                      r"updates|delivers|provides|drills|intersects|commences|receives|closes|becomes|progresses|"
                      r"outlines|begins|starts|signs|confirms|extends|identifies|launches|reviews|secures|achieves|"
                      r"renegotiates|appointed|exercises|grants|discovers|returns|stakes|advances|proven)\b")
_PN_BAD_LAST = {"expansion", "development", "study", "plant", "program", "programme", "update", "estimate", "report",
                "igneous", "intrusive", "focused"}
_PN_PARTICLE = {"de", "del", "da", "do", "dos", "das", "du", "des", "la", "le", "y", "of", "the", "di", "en"}
_PN_STARTERS = {"the", "its", "our", "at", "on", "in", "for", "from", "of", "to", "and", "with", "by", "as", "a", "an",
                "this", "their", "company", "company's", "updated", "maiden", "initial", "mineral", "ni", "gold",
                "silver", "copper", "owned", "announces", "files", "reports", "project", "property", "mine"}
_PN_ART = r"(?:La|El|Los|Las|San|Santa|Le|Les)"
_PN_FOLLOW_OK = {  # words that may follow a project name without making it a longer one
    "project", "projects", "property", "properties", "mine", "mines", "deposit", "deposits", "zone", "zones", "claims",
    "concession", "district", "camp", "complex", "prospect", "target", "trend", "area", "open", "pit", "underground",
    "mineral", "resource", "resources", "reserve", "reserves", "technical", "report", "pea", "pfs", "feasibility", "gold",
    "silver", "copper", "zinc", "nickel", "lithium", "uranium", "graphite", "cobalt", "tin", "tungsten", "drill", "drilling",
    "exploration", "phase", "program", "update", "results", "and", "the", "in", "is", "was", "has", "north", "south",
    "east", "west", "main", "extension", "expansion", "operation", "operations", "joint", "venture", "jv", "ni", "maiden",
    "initial", "updated", "estimate", "study", "polymetallic", "vms", "porphyry", "system", "belt", "corridor", "pegmatite"}
_PN_OPER = re.compile(r"\b((?:[A-Z][\w'\u2019\-]*\s+){1,3})(?:Gold\s+|Silver\s+|Copper\s+)?(?:Operations?|Mine|Project|Property)\b")
_PN_COMPANY_WIDE = re.compile(
    r"(?i)reserves?\s+(?:and|&)\s+(?:mineral\s+)?resources?|resources?\s+(?:and|&)\s+(?:mineral\s+)?reserves?|"
    r"reserve\s+and\s+resource|\b(?:mineral|ore)\s+reserves?\b|\bproduc(?:tion|es|ed)\b|operating\s+results|"
    r"financial\s+results|guidance|\b(?:projects|mines|operations|assets|properties|assessments)\b|royalt|"
    r"\bquarter\b|full\s+year|year[\s\-]+end|outlook|\b(?:19|20)\d\d\s+results\b|\bQ[1-4]\b")
_PN_CORP = r"\s+(?:Corp|Corporation|Inc|Ltd|Limited|Resources|Mining|Metals|Minerals|Ventures|Holdings|Mineras|LLC|Plc)\b"


def _pn_page(name):
    """A helper name in this page's form: no trailing Project/Mine/Deposit...; a list, a description or a
    report word is not taken ('Tom and Jason Deposits', 'Two Gold Producing Mines', 'NI43-101 Technical Report')."""
    s = (name or "").strip()
    for _ in range(3):
        s = _PN_SUF.sub("", s).strip()
    if not s or len(s) < 3 or re.search(r"(?i)\s(?:and|&)\s", s) or s.split()[0].lower() in _PN_BAD_LEAD:
        return None
    if s.split()[-1].lower() in _PN_BAD_LAST or re.search(r"43-?\s?101", s) or _PN_VERB.search(s):
        return None
    ws = [w.lower() for w in re.findall(r"[\w'\u2019\-]+", s)]
    if set(ws) & _PN_BAD_WORD or (len(ws) == 1 and ws[0] in _PN_GENERIC_ONE) or re.search(_PN_CORP, s) \
            or re.search(r"(?i)eq\d*$", s) or re.match(r"(?i)" + _PN_METAL_WORD + r"(?:-" + _PN_METAL_WORD + r")+\s", s):
        return None                                       # a deal, a company, a bare place word, 'CuEq1', 'Copper-Zinc-... X'
    if s.split()[0].lower() == "new" and len(s.split()) == 1:
        return None
    if not (s[:1].isupper() or s[:1].isdigit()) or len(s.split()[0]) == 1:
        return None
    return s


def _pn_casefix(name, text):
    """The name as the text writes it most often among forms that capitalise every word but particles and shout no
    long word ('CASTELO DE SONHOS' -> 'Castelo de Sonhos'); else word by word: a word the text also writes in lower
    or title case is title-cased, one it only ever writes in capitals stays so ('ZEUS LITHIUM' -> 'Zeus Lithium' when
    the text also says 'Zeus lithium'; 'ELG', 'PAK', 'CV5' stay)."""
    forms = {}
    for m in re.finditer(r"(?<![\w])" + re.escape(name) + r"(?![\w])", text or "", re.I):
        forms[m.group(0)] = forms.get(m.group(0), 0) + 1

    def capitalised(f):
        ws = [w for w in re.split(r"[\s\-/]+", f) if w]
        return bool(ws) and ws[0][:1].isupper() and all(
            (w[:1].isupper() or w[:1].isdigit() or w.lower() in _PN_PARTICLE) and not (len(w) >= 3 and w.isupper())
            for w in ws)

    mixed = sorted(((k, f) for f, k in forms.items() if capitalised(f) and not f.isupper()), reverse=True)
    if mixed:
        return mixed[0][1]
    out, first = [], True
    for w in re.split(r"(\s+|-|/)", name):
        if re.search(r"[A-Za-z]", w) and not re.search(r"\d", w):
            seen = {m.group(0) for m in re.finditer(r"(?<![\w])" + re.escape(w) + r"(?![\w])", text or "", re.I)}
            # a short word counts only in title case: 'FAD', 'TLC' are no 'fad', 'tlc'
            lower_too = w.capitalize() in seen if len(w) <= 3 else any(not f.isupper() for f in seen)
            if w.lower() in _PN_PARTICLE and not first:
                w = w.lower()
            elif w.isupper() and lower_too:
                w = w.capitalize()
            elif not w.isupper() and not lower_too and len(w) <= 4:
                w = w.upper()
        if re.search(r"[A-Za-z0-9]", w):
            first = False
        out.append(w)
    return "".join(out)


def _pn_article(name, text):
    """'Guitarra' -> 'La Guitarra' when the text mostly writes the article."""
    if re.match(_PN_ART + r"\s", name):
        return name
    arts = {}
    for m in re.finditer(r"\b(" + _PN_ART + r")\s+" + re.escape(name) + r"\b", text or ""):
        arts[m.group(1)] = arts.get(m.group(1), 0) + 1
    bare = len(re.findall(r"\b" + re.escape(name) + r"\b", text or "")) - sum(arts.values())
    if arts and sum(arts.values()) >= bare:
        return max(arts, key=arts.get) + " " + name
    return name


def _pn_occ(name, text):
    return len(re.findall(r"(?i)(?<![\w])" + re.escape(name) + r"(?![\w])", text or "")) if name else 0


def _pn_words(name):
    return set(PN.key(name or "").split())


def _pn_real(name, text):
    """The text writes the name before Project/Property/Mine/Claims/Deposit... (any case)."""
    return bool(name) and bool(re.search(re.escape(name) + _PN_REAL, text or "", re.I))


def _pn_fragment(name, text):
    """Every occurrence follows a hyphen, 'St.' or 'Mine': 'Lawrence' of 'Silver Bell-St. Lawrence', 'Centre' of
    'Mine Centre'."""
    occ = [m.start() for m in re.finditer(r"(?<![\w\-])" + re.escape(name) + r"\b", text or "")]
    if not occ:
        return False
    for i in occ:
        pre = text[max(0, i - 40):i]
        if not (re.search(r"(?:-\s*|\bSt\.?\s*)$", pre) or re.search(r"\bMine\s+$", pre)):
            return False
    return True


def _pn_longer(name, text):
    """The text mostly writes the name after the same capitalised word: the name is longer ('Nueva Recuperada')."""
    pre, n = {}, 0
    for m in re.finditer(r"(?<![\w\-])" + re.escape(name) + r"\b", text or ""):
        n += 1
        w = re.search(r"([A-Z][\w'\u2019\.]*)\s+$", text[max(0, m.start() - 30):m.start()])
        if w and w.group(1).lower() not in _PN_STARTERS and not re.search(r"['\u2019]s?$", w.group(1)) \
                and not w.group(1).isupper():
            pre[w.group(1)] = pre.get(w.group(1), 0) + 1
    post = {}
    for m in re.finditer(r"(?<![\w\-])" + re.escape(name) + r"\s+([A-Z][\w'\u2019]*)", text or ""):
        w = m.group(1)
        if w.lower() not in _PN_FOLLOW_OK and not w.isupper():
            post[w] = post.get(w, 0) + 1
    k = max(list(pre.values()) + list(post.values()) + [0])
    return k >= 2 and 2 * k >= n


def _pn_dominant(new, cands, text):
    """At least twice as common as any other project-level name the helper finds."""
    n = _pn_occ(new, text)
    if n < 2:
        return False
    for x in cands:
        p = _pn_page(x)
        if p and _PN_LEVEL1.search(x) and not (_pn_words(p) & _pn_words(new)) and n < 2 * _pn_occ(p, text):
            return False
    return True


def _pn_no_name(own, text):
    """1.0.19's name is no project: it starts in lower case ('ir Los Ricos North', 'wholly-owned Diablillos'), starts
    with a description word ('Exploration', 'PEA', 'Advance'), ends on a function word ('Mpama South as the',
    'Turnagain Project Open') or carries a verb ('... Project Outlines'). A real name the helper merely does not know
    ('CV5', 'BMC', 'Gbongogo') is kept."""
    ws = own.split()
    if not ws:
        return False
    if ws[0][:1].islower():
        return True
    if ws[0].lower().strip(",.;:") in _PN_BAD_LEAD - {"current", "north", "south", "main", "global", "new", "central"} \
            or _PN_VERB.search(own):
        return True
    return ws[-1].lower().strip(",.;:") in {"the", "of", "and", "as", "with", "within", "including", "open",
                                             "below", "for", "to", "in", "on", "at", "by", "from"}


def _pn_proper(dep):
    """A row's own deposit names somewhere: a capitalised word beyond pit / scenario / category words
    ('ELG Open Pit' does, 'Open Pit' and 'Pit Constrained' do not)."""
    return any(w[:1].isupper() and w.lower() not in _PN_GENERIC_DEP for w in re.findall(r"[A-Za-z][\w'\u2019\-]*", dep or ""))


def _release_project_pn(head, body, own, rows=None):
    """1.0.20: the release's project -- 1.0.19's release_project (own), filled, respelt or corrected by the shared
    helper (see the notes above) -- unless the change would fold a row into another row's deposit (E3's
    'Clearwater' 3.9 Mt and 'Clearwater Lithium' 2.2 Mt stay two rows), or a new project would sit over rows that
    already name other deposits (Torex's 'ELG Open Pit' is not 'EPO (ELG Open Pit)')."""
    new = _pn_pick(head, body, own)
    if new == own or not rows:
        return new
    have = [r.get("deposit") or r.get("_proj") for r in rows]
    named = [d for d in have if d]
    if len(named) < len(have) and _norm_dep(new) != _norm_dep(own or "") \
            and _norm_dep(new) in {_norm_dep(d) for d in named}:
        return own
    if not own and any(_pn_proper(d) and not (_pn_words(d) & _pn_words(new)) for d in named):
        return own
    return new


def _pn_pick(head, body, own):
    """The helper's choice for the release's project, before the rows are consulted."""
    h = " ".join((head or "").split())
    b = body or ""
    t = h + "\n" + b
    try:
        cands = PN.projects(h, b)
    except Exception:
        return own
    if not cands:
        return own
    hw = _pn_words(h)
    named = [x for x in cands if _pn_words(x) and _pn_words(x) <= hw | {"project", "property"}]
    pick = named[0] if named else cands[0]
    for x in named:                                       # 'Los Ricos South' over 'Los Ricos' when both are named
        if _pn_words(x) > _pn_words(pick):
            pick = x
    new = _pn_page(pick)
    if not new:
        return own
    new = _pn_casefix(_pn_article(new, t), t)
    if not new or not (new[:1].isupper() or new[:1].isdigit()):
        return own
    level1 = bool(_PN_LEVEL1.search(pick))
    if not own and all(w.lower() in _PN_GEOLOGY for w in re.findall(r"[A-Za-z]+", new)):
        return own                                        # a kind of rock, not a project ('Breccia Pipe')
    if not own:
        if len(re.findall(re.escape(new) + _PN_CORP, t)) * 2 >= max(1, _pn_occ(new, t)):
            return own                                    # a company name
        if _pn_fragment(new, t) or _pn_longer(new, t):
            return own                                    # a cut-off name
        if re.match(re.escape(new) + r"\s+[A-Za-z]+(?:s|ed)\b", h, re.I) and not re.match(re.escape(new) + r"\s+(?:Mines?|Projects?|Properties|Claims|Deposits?|Operations?)\b", h, re.I):
            return own                                    # the headline's subject: the company ('Standard Lithium Drills')
        if re.search(r"(?i)\b(?:with|from|by)\s+(?:the\s+)?" + re.escape(new) + r"\b", h):
            return own                                    # a counterparty ('... Option Agreement with MMC')
        if re.search(_PN_NEIGHBOUR + re.escape(new), t[:1500]):
            return own                                    # a neighbour ('... Adjoining Barrick's Pueblo Viejo')
        if named:
            if _PN_COMPANY_WIDE.search(h) and not _pn_dominant(new, cands, t):
                return own
            if [x for x in named if _pn_page(x) and not (_pn_words(_pn_page(x)) & _pn_words(new))
                    and (_PN_LEVEL1.search(x) or not level1)]:
                return own                                # the headline names a second project
            return new
        early = bool(_pn_words(new)) and _pn_words(new) <= set(PN.key(" ".join(b[:1500].split())).split())
        if not (early and level1 and _pn_real(new, t)):
            return own
        try:
            prim = PN.primary(h, b)
        except Exception:
            prim = None
        if prim is None or PN.key(prim) != PN.key(pick):
            return own
        if sum(1 for x in cands if _PN_LEVEL1.search(x)) >= 4 or _PN_COMPANY_WIDE.search(h):
            return own                                    # a portfolio or company-wide release
        if not _pn_dominant(new, cands, t):
            return own
        for m in _PN_OPER.finditer(h):
            o = m.group(1).strip()
            if _pn_page(o) and not (_pn_words(o) & _pn_words(new)):
                return own                                # the headline names another operation
        return new
    if PN.key(own) and PN.key(own) == PN.key(new):
        if own != new and (own.isupper() or re.search(r"\s[a-z]+$", own)) and not (new.isupper() and not own.isupper()):
            return new                                    # the same project, in the text's own spelling
        return own
    placed = _place(own)
    if placed and placed != own and not _pn_no_name(placed, t):
        # the page already shows 1.0.19's name cleaned ('historic Belmont' reads 'Belmont'): only the same name
        # in a cleaner form replaces it ('ir Los Ricos South' -> 'Los Ricos South'), never a different one
        return new if PN.key(placed) == PN.key(new) and level1 else own
    if level1 and _pn_no_name(own, t) and (_pn_words(own) & _pn_words(new) or (named and _pn_dominant(new, cands, t))) \
            and not _pn_fragment(new, t) and not _pn_longer(new, t) \
            and len(re.findall(re.escape(new) + _PN_CORP, t)) * 2 < max(1, _pn_occ(new, t)) \
            and not (_PN_COMPANY_WIDE.search(h) and not _pn_dominant(new, cands, t)):
        return new
    return own


# ------------------------------------------------------------------ 1.0.22: rows that are not the company's estimate
# Guide section 1, "somebody else's deposit". A release that describes its own ground by the resources of the ground
# next door, of an analogue, of the famous deposits of the belt, or of a company it holds shares in, states figures
# that are not its own, and the right answer for them is no row. The words around a row say whose figures they are:
#   a. wording that places the figures on other ground or offers them as a comparison (before the figures):
#      "analogous", "neighbouring", "bordering", "near the known", "notable deposits (of the belt) include",
#      "for example", "within N km of";
#   b. wording that disowns or credits them: "cannot verify", "not (necessarily) indicative", a "Source:" footnote,
#      "see X's news release", "(X News Release, ...)", "X's website";
#   c. another company named as the owner close before the figures: "X's [Name] project / deposit / mine",
#      "X Corp. has / announced / where ...", "(X, December 31, 2020)", a stock ticker that is not the issuer's.
# X counts only when none of its words belong to the issuer (the '("X" or the "Company")' parenthesis, the name in
# front of the issuer's ticker, the headline's first words) or to the row's own deposit. Not counted: a name after
# "by" (the consultant, a JV partner's estimate "by X for the Y project"), after "the" or before Island/Lake/River
# (a place), and releases about royalties or streams, where the operator is necessarily another company and the
# guide still publishes the deposit.
_OWN_GENERIC = {"the", "company", "corporation", "corp", "inc", "ltd", "limited", "plc", "gold", "metals", "metal",
                "mining", "mines", "minerals", "resources", "resource", "silver", "copper", "exploration", "ventures",
                "group", "and", "of", "effective", "date", "project", "mine", "deposit", "new", "north", "south", "east",
                "west", "canada", "canadian", "lithium", "nickel", "uranium", "battery", "energy", "mineral",
                # a report, not a company: "see PEA press release", "see the MRE news release"
                "pea", "pfs", "dfs", "bfs", "fs", "mre", "ni", "study", "report", "technical", "news", "press",
                "release", "previous", "prior", "earlier", "recent", "latest", "updated", "maiden", "initial"}
_OC_SP = r"[ \n]+"
_OC_NAME = r"[A-Z][\w&\-]*(?:(?:" + _OC_SP + r"(?:and|&))?" + _OC_SP + r"[A-Z][\w&\-]*){0,3}"
_OC_MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_OC_BEFORE = re.compile(r"\b(analog\w*|neighbou?ring|bordering|near the known|for example|resembl\w+|"
                        r"(?:geological )?parallels to|similarities with|"
                        r"within \d+ ?(?:k ?m|kms|kilomet\w+) of)\b")
# a list of the belt's or district's deposits covers its whole paragraph
_OC_LIST = re.compile(r"\bnotable (?:[\w\-]+ ){0,2}(?:deposits|projects|mines|discoveries)\b|"   # 1.0.23: any notable list
                      r"\b(?:deposits|projects|mines) worldwide\b|"
                      r"\bdeposits (?:in|of|from) the (?:belt|district|region|camp|area) include\b")
_OC_AROUND = re.compile(r"\b(cannot verify|not (?:necessarily )?indicative)\b")
_OC_SOURCE = re.compile(r"\bSource:")
_OC_CITE = re.compile(r"\b[Ss]ee\s+(" + _OC_NAME + r")\s*(?:['\u2019]s?)?\s+(?:\w+\s+){0,2}(?:[Nn]ews|[Pp]ress|NEWS|PRESS)\s+"
                      r"(?:[Rr]elease|RELEASE)")
_OC_POSS = re.compile(r"\b(" + _OC_NAME + r")\.?[ ]?(?:['\u2019]s|s['\u2019])" + _OC_SP + r"(?:\([^()]{0,30}\)" + _OC_SP + r")?"
                      r"((?:[A-Za-z0-9][\w\-]*" + _OC_SP + r"){0,4})"
                      r"(?i:project|deposit|mine|property|discovery|claims|operation|filings|website)\b")
_OC_CORP = re.compile(r"\b(" + _OC_NAME + r")" + _OC_SP + r"(?:Corp\w*|Inc|Ltd|Limited|plc|Metals|Mining)\b\.?,?"
                      + r"(?:" + _OC_SP + r"?\([^()]{0,40}\))?" + _OC_SP
                      + r"(?:has|have|had|where|announced|reported|released|published|"
                      r"((?:[A-Z][\w\-]*" + _OC_SP + r"){1,2})(?i:project|deposit|mine|property))\b")
_OC_DATED = re.compile(r"\((" + _OC_NAME + r"),[ ]+" + _OC_MONTH + r"[ ]+\d")
_OC_NEWS = re.compile(r"\((" + _OC_NAME + r")" + _OC_SP + r"(?:News|Press)" + _OC_SP + r"Release\b")
_OC_TICKER = re.compile(r"\((?:TSX[\-.]?V?|ASX|CSE|NYSE(?: American)?|NASDAQ|AIM|LSE|JSE|OTC\w*)\s*[:\-]\s*([A-Z0-9.]{2,6})\)")
_OC_PLACE = re.compile(r"(?:Island|Lake|River|Bay|Creek|Point|Cove|Harbou?r|Mountain|Hill|Peak|Valley|Brook|Pond|"
                       r"Falls|Landing|Arm)\b")
_OC_ROYALTY = re.compile(r"(?i)\broyalt(?:y|ies)\b|\bstream(?:s|ing)?\b(?!\s+(?:sediment|bed|flow|channel))")
_OC_PHRASES = ((_OC_BEFORE, 700, 60, True), (_OC_AROUND, 700, 400, True), (_OC_SOURCE, 0, 500, False))


def _issuer(head, text):
    """The issuer's name words and tickers, from the headline and the lead; and whether the release is about
    royalties or streams."""
    lead = head + "\n" + text[:2000]
    names = []
    for m in re.finditer(r"\(([^()]{0,160}?\"(?:the\s+)?(?:Company|Corporation|Issuer)\"[^()]{0,160})\)", lead, re.I):
        names += re.findall(r"\"([^\"]{1,50})\"", m.group(1))
    for m in re.finditer(r"(" + _OC_NAME + r")\.?,?[ ]*\((?:TSX|ASX|CSE|NYSE|NASDAQ|OTC|FSE|AIM|LSE)", lead):
        names.append(m.group(1))
    names.append(" ".join(head.split()[:3]))
    # a company the headline names is what the release reports on ("... reports on X's Maiden Resource Estimate",
    # "... an initial resource estimate by X for the Y project") -- unless the headline places it next door
    names += re.findall(r"\b[A-Z][\w&\-]*", re.split(r"(?i)\b(?:adjacent|near|next\s+to|proximity|bordering|"
                                                   r"neighbou?r\w*|contiguous|along\s+strike|analog\w*|similar|"
                                                   r"interest\s+in|stake\s+in|investment\s+in|shares\s+(?:of|in))\b",
                                                   head)[0])
    words = {w.lower() for n in names for w in re.findall(r"[^\W\d_]+", n)} - _OWN_GENERIC
    tickers = set(re.findall(r"\b[A-Z0-9]{2,6}\b", " ".join(re.findall(r"\([^()]{0,120}\)", lead))))
    return words, tickers, bool(_OC_ROYALTY.search(lead))


def _royalty_release(head, text):
    """1.0.23: a release about a royalty or a stream, where the operator is necessarily another company: its headline
    says royalty or stream, the issuer is a royalty or streaming company ("X Royalties Inc.", "a royalty company"), or
    the opening says the issuer holds or acquired one. Not an NSR a deal grants in passing, not the streams a
    sediment sample came from."""
    for m in _OC_ROYALTY.finditer(head):
        if not re.search(r"(?i)\b(?:sediments?|samples?)\b", head[max(0, m.start() - 40):m.start()]):
            return True
    # ... or a royalty company's report on its portfolio: the word comes back again and again
    if sum(1 for m in _OC_ROYALTY.finditer(text[:6000])
           if not re.search(r"(?i)\b(?:sediments?|samples?|creeks?|drainages?)\b\W+(?:\w+\W+){0,2}$",
                            text[max(0, m.start() - 40):m.start()])) >= 5:
        return True
    top = text[:1500]
    return bool(re.search(r"(?i)\broyalt(?:y|ies)\s+(?:corp\w*|inc|ltd|limited|plc)\b|"
                          r"\bstreaming\s+(?:corp\w*|inc|ltd|limited)\b|"
                          r"\b(?:royalty|streaming)(?:\s+and\s+(?:royalty|streaming))?\s+(?:company|corporation|business|"
                          r"portfolio)\b|\b(?:holds?|owns?|acquired?|acquires|purchased?|purchases|has)\s+(?:a|an|the)\s+"
                          r"(?:[\d.]+%\s+)?(?:[\w\-]+\s+){0,4}?(?:\([^()]{0,12}\)\s+)?(?:royalty|stream)\b", top))


def _oc_whole(text, m):
    """False when the match starts inside a longer capitalised name, or right after "the" or "by"."""
    if m.group(1).split()[0] == "The":
        return False
    before = text[max(0, m.start(1) - 20):m.start(1)].split()
    if not before:
        return True
    if before[-1].lower() in ("the", "by"):
        return False
    return not re.match(r"[A-Z][\w&\-]*$", before[-1])


def _oc_foreign(name, own_words):
    ws = [w for w in (x.lower() for x in re.findall(r"[^\W\d_]+", name)) if w not in _OWN_GENERIC]
    return bool(ws) and not any(w in own_words for w in ws)


def _owner_context(head, text):
    """Once per release: the phrases of kinds a and b, and every place another company is named as an owner."""
    words, tickers, royalty = _issuer(head, text)
    low = text.lower() if len(text.lower()) == len(text) else text
    phrases = []
    for rx, a, b, lower in _OC_PHRASES:
        for m in rx.finditer(low if lower else text):
            phrases.append((m.start(), m.end(), a, b))
    lists = []
    for m in _OC_LIST.finditer(low):
        para = re.search(r"\n[ ]*\n", text[m.end():m.end() + 2500])
        lists.append((m.start(), m.end() + (para.start() if para else 2500)))
    mentions = []
    if not royalty:
        for rx in (_OC_POSS, _OC_CORP, _OC_DATED, _OC_NEWS, _OC_CITE):
            for m in rx.finditer(text):
                proj = " ".join((m.group(2) or "").split()) if rx.groups >= 2 else ""
                if rx is _OC_POSS and _OC_PLACE.match(proj) and len(proj.split()) == 1:   # "X's Island Mine": a place, not an owner
                    continue
                if rx is _OC_CORP and proj.startswith("The "):
                    continue          # 1.0.23: "... from X Resources Inc. The Y deposit hosts": a new sentence, not X's

                cite = rx in (_OC_NEWS, _OC_CITE) or rx is _OC_POSS and re.search(r"(?i)(?:filings|website)$", m.group(0))
                # ("refer to the X's filings" is a citation even after "the")
                whole = _oc_whole(text, m) or cite and re.search(r"(?i)\bthe\s+$", text[max(0, m.start() - 6):m.start()])
                # 1.0.23 FIX3: "25 km northwest of X's Y mine" places the issuer's ground; X owns the landmark
                mark = not cite and bool(_RE_OC_LANDMARK.search(text[max(0, m.start() - 40):m.start()]))
                if whole and _oc_foreign(m.group(1), words):
                    mentions.append((m.start(), m.end(), " ".join(m.group(1).split()), proj, bool(cite), mark))
        for m in _OC_TICKER.finditer(text):
            if m.group(1) not in tickers:
                mentions.append((m.start(), m.end(), "", "", False, False))
    # 1.0.23 FIX3: where the release's sections start ("About X", "Qualified Person", "Notes", "Forward-looking")
    stops, at = [], 0
    for ln in text.split("\n"):
        if _RE_STOP.match(ln):
            stops.append(at)
        at += len(ln) + 1
    return phrases, mentions, royalty, lists, stops


_RE_OC_LANDMARK = re.compile(r"(?i)\b(?:north|south|east|west)(?:[\s-]?(?:north|south|east|west))?(?:ern|erly)?\s+of\s+"
                             r"(?:the\s+)?$")


def _table_top(text, at):
    """1.0.23 FIX3: where the table holding the figures at `at` starts -- the first line below the last line of
    prose above them. 1.0.22 measured its window from the start of the block read_tables was in, which runs back
    over bullet points and paragraphs to a neighbour the CEO compares the project with."""
    ls = text[:at].split("\n")
    pos = at - len(ls[-1])
    for ln in reversed(ls[:-1]):
        nlow = len(re.findall(r"\b[a-z]{3,}\b", ln))
        if nlow >= 5 or nlow >= 2 and re.search(r"[.:;!?][\"')]*\s*$", ln):   # prose, or the end of a sentence
            break
        pos -= len(ln) + 1
    return pos


def _foreign_row(r, text, ctx):
    """True when the words around the row's figures place them on another company's deposit."""
    lo, hi = r.get("_blk_at"), r.get("_at")
    if hi is None:
        return False
    lo = hi if lo is None else min(lo, hi)
    phrases, mentions, royalty, lists, stops = ctx
    if royalty:
        return False
    if any(a <= lo and hi <= b for a, b in lists):
        return True
    if r.get("source") in ("table", "rowline"):
        lo = max(lo, _table_top(text, hi))       # 1.0.23 FIX3: the table, not the prose paragraphs above it

    def apart(x, y):                              # 1.0.23 FIX3: a section heading between them
        return any(min(x, y) < p < max(x, y) for p in stops)
    for start, end, a, b in phrases:
        if start >= lo - a and end <= hi + b and not apart(start, lo if start < lo else hi):
            return True
    dep = {w.lower() for w in re.findall(r"[^\W\d_]+", str(r.get("deposit") or ""))}
    for start, end, name, proj, cite, mark in mentions:
        if mark and start < lo and re.search(r"[.!?][\"')]*\s", text[end:lo]):
            continue      # 1.0.23 FIX3: a landmark the issuer's ground is placed by, in a sentence of its own
        if cite and hi <= start <= hi + 400 and (not name or _oc_foreign(name, dep)) and not apart(hi, start):
            return True                           # "(X News Release, ...)", "refer to X's filings" after the figures
        if start < lo - 700 or end > hi + 60:
            continue
        if name and not _oc_foreign(name, dep):
            continue                              # the name is part of the row's own deposit name
        if lo - end <= 300:
            return True
        # further back: only when the project it owns is named again between it and the figures
        if len(proj) >= 4 and proj in " ".join(text[end:hi].split()):
            return True
    return False


# ------------------------------------------------------------------ 1.0.23: whose figures, read sentence by sentence
# A release about something else -- a drill programme, a financing, an option, a staking, an appointment -- often
# describes its ground by the estimates around it. 1.0.22 looked for a few words within a fixed number of characters;
# 1.0.23 reads the figures' own sentence: what that sentence (or, when it names nobody -- "There is an additional
# Indicated Resource of ..." -- the sentence before it, in the same paragraph) says last before the figures decides
# whose they are (_wh_whose). It points to the issuer when it names the issuer (its dateline names and tickers), "the
# Company", "our", one of the issuer's own projects (named in the headline, or introduced as "its / the Company's /
# 100%-owned / flagship X", "an interest in / an option on / owns / acquire the X project", a defined term, a company
# it takes over) or "The project / The deposit" when the last one named was one of those. It points to somebody else
# when it is:
#   - a neighbour wording in front of a deposit named in passing: "the adjacent Meliadine project", "The nearby Mel
#     deposit";
#   - a distance from the issuer's ground with a deposit named in passing in front of it: "The Mel deposit ... located
#     4 km south of the Licenses", "the Gruyere Deposit just 35km east of the Mt Venn Project", "The Blackdome Zone
#     located 26km to the south", "the Florin Gold deposit, located adjacent to Sitka's RC Gold project" ("our
#     property is located 25 km north of <a town>" places our ground and is not counted; nor are drill holes "600
#     metres northeast of" our deposit); or a place we are measured against that "hosts" the figures ("10 km west of
#     X's producing Gamma Mine, which hosts ...");
#   - a deposit named in passing that the release places next to, along strike from or "similar to" its ground, again
#     as a sentence's subject ("adjacent to the Cameron Lake claim group" ... "The Cameron Lake Deposit hosts ...");
#   - another company as the owner: "X's deposit", "held / owned / operated by X", "X owns a 100% interest in",
#     "a joint venture between X and Y", "the Y deposit of X Mining", 'X Inc. ("ABC") Y project', "X Resources
#     recently announced", a ticker or a website that is not the issuer's -- and what it owns, wherever named again;
#   - a list of notable or worldwide deposits, a table with an owner column, an analogue;
#   - a hedge only a third party's figures get: "reportedly", "is reported to include".
# After the figures, a credit to somebody else's source does the same: a link to another company's website
# ("(https://<another company>.com/...)") or a parenthesis naming another company's report.
# When the figures' own sentence points to the issuer, 1.0.22's company-named-nearby window no longer drops the row.
# Royalty and stream releases stay exempt (the operator is another company by definition).
_WH_NAME = r"[A-Z][\w'&\-]*(?:[ \n](?:(?:de|del|la|las|los|el|du|des|da|do|dos|y)[ ])?[A-Z0-9][\w'&\-]*){0,4}"
_WH_NOUN = (r"(?:[Pp]rojects?|PROJECTS?|[Pp]ropert(?:y|ies)|PROPERT(?:Y|IES)|[Dd]eposits?|DEPOSITS?|[Mm]ines?|MINES?|"
            r"[Cc]laims?|[Cc]laim\s+group|[Ll]icen[cs]es?|[Cc]oncessions?|[Tt]enements?|[Zz]ones?|[Pp]rospects?|"
            r"[Oo]perations?|[Cc]omplex)\b")
_WH_OWNER_NOUN = (r"(?:[Pp]rojects?|PROJECTS?|[Pp]ropert(?:y|ies)|PROPERT(?:Y|IES)|[Dd]eposits?|DEPOSITS?|[Mm]ines?|MINES?|"
                  r"[Oo]perations?|[Dd]iscovery|[Cc]laims)\b")
_WH_DESC = r"(?:[ \n](?:[a-z][\w\-]*|\([A-Za-z]{2,6}\)|[A-Z]{2,4}\b)){0,4}?[ \n]"   # "volcanogenic massive sulfide (VMS)"
_WH_DIR = (r"(?:[Nn]orth|[Ss]outh)(?:[\s-]?(?:[Ee]ast|[Ww]est))?(?:ern|erly)?|[Ee]ast(?:ern|erly)?|[Ww]est(?:ern|erly)?|"
           r"(?:NNE|NNW|SSE|SSW|ENE|ESE|WNW|WSW|NE|NW|SE|SW|N|S|E|W)(?=\s+of\b)")
_WH_DIST = r"\d+(?:\.\d+)?\s?(?:km|kms|kilomet\w+|miles?)\b"
# "located 4 km south of the Licenses", "35km east of the Mt Venn Project", "located 26km to the south", "located
# adjacent to Sitka's RC Gold project"
_WH_DISTANCE = re.compile(
    r"(?:\b(?:located|lies|lying|situated)\s+(?:just\s+|immediately\s+|directly\s+|approximately\s+|about\s+|some\s+|"
    r"roughly\s+|only\s+)?)?(?:\b" + _WH_DIST + r"\s+)?(?:(?P<rel>to\s+the\s+)(?:" + _WH_DIR + r")\b|(?:\b(?:" + _WH_DIR +
    r")\s+of|\b(?:adjacent|next)\s+to)\s+"
    r"(?P<obj>(?:the\s+|its\s+|our\s+)?(?:Company's\s+)?(?:" + _WH_NAME + r")(?:" + _WH_DESC + _WH_NOUN + r")?|"
    r"(?:the|its|our)\s+(?:Company's\s+)?(?:[a-z]+\s+){0,2}(?:[Ll]icen[cs]es?|[Pp]ropert(?:y|ies)|[Pp]rojects?|[Cc]laims?|"
    r"[Tt]enements?|[Cc]oncessions?|ground)\b))")
_WH_OWNREF = re.compile(r"(?:the|its|our)\s+(?:Company's\s+)?(?:[a-z]+\s+){0,2}(?:[Ll]icen[cs]es?|[Pp]ropert(?:y|ies)|"
                        r"[Pp]rojects?|[Cc]laims?|[Tt]enements?|[Cc]oncessions?|ground)\b")
_WH_URL = re.compile(r"(?:https?://|\bwww\.)(?:www\.)?([A-Za-z0-9\-]+)(?:\.[A-Za-z0-9\-]+)*\.[a-z]{2,4}\b")
_WH_PEERS = re.compile(r"(?i)\bnotable\s+(?:[\w\-]+\s+){0,2}(?:deposits|projects|mines|discoveries|operations)\b|"
                       r"\b(?:deposits|projects|mines)\s+worldwide\b|"
                       r"\banalog(?:ue|ous)?\b|(?-i:\b(?:Project|Deposit|Name)\s+(?:Company|Owner|Operator)\b)")
_WH_EXCHANGES = {"TSX", "TSXV", "ASX", "CSE", "NYSE", "NASDAQ", "OTC", "OTCQB", "OTCQX", "OTCPK", "PINK", "FSE", "AIM",
                 "LSE", "JSE", "NEO", "CBOE", "BVL", "BMV", "FWB", "XETRA", "AMEX", "MKT", "NSR", "LOI", "MOU", "CEO",
                 "CFO", "NI", "PEA", "PFS", "DFS", "MRE", "USD", "CAD", "AUD", "US", "NYSEAMERICAN", "AMERICAN"}
_WH_ABBR = {"inc", "ltd", "corp", "co", "no", "mt", "st", "ste", "approx", "dr", "mr", "ms", "mrs", "jr", "sr", "vs",
            "fig", "al", "est", "ft", "e.g", "i.e", "u.s", "p.geo", "ph.d", "s.a", "b.c", "nos"}
_WH_BOUND = re.compile(r"[.!?][\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])|\n[ ]*\n|[\u2022\u25aa\u25a0\u25e6]")
_WH_DIRWORDS = {"north", "south", "east", "west", "upper", "lower", "extension", "central"}
_WH_GENERIC = (_OWN_GENERIC - _WH_DIRWORDS) | {
                              "projects", "property", "properties", "deposits", "mines", "claims", "claim", "group",
                              "licence", "licences", "license", "licenses", "concession", "concessions", "tenement",
                              "tenements", "zone", "zones", "prospect", "operation", "operations", "complex", "zinc",
                              "lead", "cobalt", "graphite", "iron", "tin", "tungsten", "antimony", "porphyry", "vms",
                              "rare", "earth", "ree", "pgm", "pge", "a", "an", "in", "on", "at", "to", "for", "with",
                              "by", "its", "our", "their", "area", "district", "camp", "belt"}
_WH_NOT_OWNER = re.compile(r"(?i)consult|geoscien|engineer|associates|services|laborator|newsfile|newswire|wire\b|"
                           r"globe|government|department|survey|ministry|university|institute")
_WH_FILINGS = re.compile(r"(?i)sedar|sec\.gov|edgar|asx\.com|newsfile|globenewswire|businesswire|prnewswire|"
                         r"accesswire|images\.|cnw|marketwired|youtube|linkedin|twitter|facebook|x\.com")


def _wh_toks(name):
    """The distinctive words of a name; a hyphenated name is one word ("Lawyers-Ranch" is not "Lawyers")."""
    return [w for w in re.findall(r"[^\W_]+(?:-[^\W_]+)*", (name or "").lower())
            if w not in _WH_GENERIC and not w.isdigit()]


def _wh_same(t, o):
    """Name t (read in the text) is our name o, or refines it ("Boardwalk" / "Boardwalk Brine", "Los Ricos North" /
    "Los Ricos") -- but a name without our name's direction is somebody else's: "Brookbank" is not "Brookbank East",
    and "Cameron Lake" is not "West Cameron"."""
    return (t <= o or o <= t) and not ((o - t) & _WH_DIRWORDS)


def _wh_starts(text):
    """Where each sentence starts: after a full stop that is not an abbreviation's, at a blank line, at a bullet."""
    out = [0]
    for m in _WH_BOUND.finditer(text):
        g = m.group(0)
        if g[0] in ".!?":
            w = re.search(r"([\w.]+)$", text[max(0, m.start() - 12):m.start()])
            if w and (w.group(1).lower() in _WH_ABBR or len(w.group(1)) == 1):
                continue
            out.append(m.end())
        elif g[0] == "\n":
            out.append(m.end())
        else:
            out.append(m.start())
    return out


def _wh_issuer(head, text):
    """The issuer's distinctive name words and its own tickers -- from the dateline and the first lines only (a
    neighbour's "(ASX: ABC)" further down is not the issuer's) -- and the companies the headline reports on."""
    top = head + "\n" + text[:1500]
    names = []
    m = re.search(r"\(([^()]{0,160}?\"\s*(?:the\s+)?(?:Company|Corporation|Issuer)\s*\"[^()]{0,160})\)", top, re.I)
    if m:
        names += re.findall(r"\"([^\"]{1,50})\"", m.group(1))
    # the short names the dateline gives the issuer: 'West Red Lake Gold Mines Ltd. ("West Red Lake" or "WRLG")'
    m = re.search(r"(?:Inc|Corp\w*|Ltd|Limited|plc|LLC)\b", text[:500])
    m = m and re.match(r"\.?,?\s*\((\s*\"[^\"]{1,40}\"(?:\s*(?:,|or|and)\s*(?:the\s+)?\"[^\"]{1,40}\")*\s*)\)",
                       text[m.end():m.end() + 140])
    if m:
        names += re.findall(r"\"([^\"]{1,40})\"", m.group(1))
    m = re.search(r"(" + _OC_NAME + r")\.?,?[ ]*\((?:TSX|ASX|CSE|NYSE|NASDAQ|OTC|FSE|AIM|LSE)", head + "\n" + text[:400])
    if m:
        names.append(m.group(1))
    # the company the release names most often, when it is named far more often than any other (a dateline
    # that is only an address: "1 University Avenue ... NEWS RELEASE Centerra Gold 2016 Year-End ...")
    cands = {}
    for c in re.finditer(r"(" + _OC_NAME + r")\.?,?[ ]*(?:\((?:TSX|ASX|CSE|NYSE|NASDAQ|OTC|FSE|AIM|LSE)|"
                         r"(?:Inc|Corp\w*|Ltd|Limited|plc)\b)", text[:3000]):
        t = _wh_toks(c.group(1))
        if t and t[0] not in cands and len(t[0]) >= 3:
            cands[t[0]] = len(re.findall(r"(?i)\b" + re.escape(t[0]) + r"\b", text))
    best = sorted(cands.items(), key=lambda kv: -kv[1])
    if not names and best and best[0][1] >= 3 and (len(best) == 1 or best[0][1] >= 2 * best[1][1]):
        names.append(best[0][0])
    names.append(" ".join(head.split()[:2]))
    hh = re.split(r"(?i)\b(?:adjacent|near|next\s+to|proximity|bordering|neighbou?r\w*|contiguous|along\s+strike|"
                  r"analog\w*|similar|interest\s+in|stake\s+in|investment\s+in|shares\s+(?:of|in))\b", head)[0]
    names += [x.group(1) for x in re.finditer(
        r"\b((?:[A-Z][\w&\-]*\s+){0,2}[A-Z][\w&\-]*)\s+(?i:Resources|Limited|Ltd|Inc|Corp\w*|Mining|Metals|Minerals|"
        r"Ventures|Exploration|Energy|Holdings)\b(?!\s+(?i:district|camp|division|belt|region))", hh)]
    names += [x.group(1) for x in re.finditer(r"\b([A-Z][\w&\-]*(?:\s+[A-Z][\w&\-]*){0,2})(?:'s|(?<=s)')\s+(?:[\w\-]+\s+){0,3}"
                                              + _WH_NOUN, hh)]
    tickers = set(re.findall(r"\b[A-Z0-9]{2,6}\b", " ".join(re.findall(r"\([^()]{0,120}\)", head + "\n" + text[:600]))))
    # the issuer's ticker is also a name it goes by ("WRLG's Rowan Property")
    names += [t for t in tickers if t.isalpha() and t not in _WH_EXCHANGES]
    sets = []
    for n in names:
        t = frozenset(w for w in _wh_toks(n) if len(w) >= 2)
        if t and t not in sets:
            sets.append(t)
    return sets, tickers


def _wh_own_names(head, text, iw=frozenset()):
    """The issuer's own projects: those its headline names (not one it places next door) and those the body
    introduces as its own."""
    out = []
    hh = re.split(r"(?i)\b(?:adjacent|near|next\s+to|proximity|bordering|neighbou?r\w*|along\s+strike|surrounding|"
                  r"analog\w*|similar|interest\s+in|stake\s+in|investment\s+in|shares\s+(?:of|in))\b", head)[0]
    for m in _RE_PROJECT.finditer(hh):
        out.append(m.group(1))
    out += [m.group(1) for m in re.finditer(r"(" + _WH_NAME + r")" + _WH_DESC + _WH_NOUN, hh)]
    # what the headline names, in runs of capitalised words ("... to Purchase the Advanced Challacollo Silver - Gold
    # Project": Challacollo is the release's own)
    out += [x for x in re.split(r"\s*(?:\b(?i:on|the|and|at|to|for|of|in|with|from|by|its|a|an|as|over|into|near|"
                                r"adjacent|announces?|reports?|provides?|commences?|completes?|signs?|enters?|"
                                r"executes?|closes?|files?)\b|[,;:.()!?|\u2013\u2014]+|\s-\s)\s*", hh) if x and x[:1].isupper()]
    for m in re.finditer(r"\b(?:[Ii]ts|[Oo]ur|[Tt]he\s+Company's|Company's|100%[\s-]*owned|[Ww]holly[\s-]*owned|"
                         r"[Ff]lagship|(?P<deal>interest\s+in\s+the|option\s+(?:on|over|to\s+acquire)\s+the|acquire\s+the|"
                         r"acquisition\s+of\s+the|owns?\s+(?:a\s+)?(?:\d+%\s+(?:interest\s+in\s+|of\s+)?)?the)|"
                         r"About\s+the)\s+(?:[a-z][\w\-]*\s+){0,3}(" + _WH_NAME + r")"
                         + _WH_DESC + _WH_NOUN, text):
        if m.group("deal"):
            lead = re.split(r"[.!?]\s", text[max(0, m.start() - 150):m.start()])[-1]
            if not (re.search(r"\b(?:[Tt]he\s+Company|Company's|[Ww]e|[Oo]ur|[Ii]ts)\b|^\W*$", lead)
                    or set(_wh_toks(lead)) & iw):
                continue
        out.append(m.group(2))
    # a company the issuer takes over or merges with, or a controlling interest it acquires: 'TVIRD has acquired all
    # of the outstanding capital stock of SageCapital Partners, Inc.' -- what that company owns becomes the issuer's
    # (a minority stake in another company does not: "acquires 15.03% interest in X")
    for m in re.finditer(r"\b(?:acquir\w*|purchas\w*|acquisition\s+of|merger\s+with|amalgamation\s+with|merge\s+with)\s+"
                         r"(?:all\s+of\s+)?(?:(?:the\s+)?(?:issued\s+and\s+)?outstanding\s+(?:capital\s+stock|shares|"
                         r"securities)\s+of\s+|(?:an?\s+)?(?:indirect\s+)?(?P<pct>\d+(?:\.\d+)?)%\s+(?:equity\s+)?(?:interest|stake)\s+"
                         r"in\s+)?(?:the\s+)?(" + _WH_NAME + r")", text, re.I):
        if m.group("pct") and float(m.group("pct")) < 50:
            continue
        if not m.group(2)[:1].isupper():
            continue
        lead = re.split(r"[.!?]\s", text[max(0, m.start() - 200):m.start()])[-1]
        if re.search(r"\b(?:[Tt]he\s+Company|Company's|[Ww]e|[Oo]ur|[Ii]ts)\b", lead) or set(_wh_toks(lead)) & iw:
            out.append(m.group(2))
    # a defined term: 'the Frontera; Clinton; and Taruca properties (the "Properties")' -- every name in the list
    for m in re.finditer(r"(" + _WH_NAME + r")\s+" + _WH_NOUN + r"\s*\(\s*(?:the\s+)?\"(?:Project|Propert)", text):
        out.append(m.group(1))
        lst = re.split(r"[:.]|\bthe\s", text[max(0, m.start() - 120):m.start()])[-1]
        if re.fullmatch(r"(?:\s*(?:and\s+)?" + _WH_NAME + r"\s*[;,]\s*)+(?:and\s+)?", lst):
            out += re.findall(_WH_NAME, lst)
    return [set(t) for t in (_wh_toks(n) for n in out) if t]


def _wh_context(head, text):
    """Once per release: every place that says whose the next figures are, as (position, end, own?)."""
    inames, tickers = _wh_issuer(head, text)
    iw = {w for n in inames for w in n if len(w) >= 2}

    def issuer(t):
        return any(n <= t for n in inames)
    owns = _wh_own_names(head, text, iw)

    for m in re.finditer(r"\b(" + _WH_NAME + r")(?:'s|(?<=s)')\s+(?:[a-z][\w\-]*\s+){0,3}(" + _WH_NAME + r")" + _WH_DESC
                         + _WH_NOUN, text):
        if issuer(set(_wh_toks(m.group(1)))) and _wh_toks(m.group(2)):
            owns.append(set(_wh_toks(m.group(2))))

    def own(name):
        t = set(_wh_toks(name))
        if t and t <= _WH_DIRWORDS:
            return False                         # "to the West" names no deposit
        return not t or issuer(t) or any(_wh_same(t, o) for o in owns)

    # an abbreviation the release defines for one of its own names: 'Mt. Labo Exploration and Development Corp.
    # ("MLEDC")'
    for m in re.finditer(r"\(\s*(?:the\s+)?\"\s*([A-Z][\w&\-]{1,12})\s*\"", text):
        b = re.search(r"(" + _WH_NAME + r"(?:\s+(?:and|&)\s+" + _WH_NAME + r")?)[\s,.]*(?:Inc|Corp\w*|Ltd|Limited)?\.?,?\s*$",
                      text[max(0, m.start() - 160):m.start()])
        if b and own(b.group(1)) and _wh_toks(b.group(1)) and _wh_toks(m.group(1)):
            owns.append(set(_wh_toks(m.group(1))))

    def rare(name):
        """A neighbour is named in passing; a deposit the release keeps coming back to is its own."""
        t = _wh_toks(name)
        return bool(t) and len(re.findall(r"(?i)\b" + r"\W+".join(re.escape(w) for w in t) + r"\b", text)) <= 3

    marks, objects, neighbours, confirmed = [], [], set(), set()
    starts = _wh_starts(text)

    def named_before(pos):
        """The last deposit or project named before pos, in the same sentence."""
        k = bisect.bisect_right(starts, pos) - 1
        sub = list(re.finditer(r"(" + _WH_NAME + r")" + _WH_DESC + _WH_NOUN, text[max(starts[k], pos - 200):pos]))
        return sub[-1].group(1) if sub else None

    # another company as the owner -- and what it owns is somebody else's deposit wherever the release names it
    for m in re.finditer(r"\b(" + _WH_NAME + r")\.?(?:'s|(?<=s)')\s+(?:\([^()]{0,40}\)\s+)?(?:(?!(?i:mill|plant|smelter|"
                         r"refinery|facilit\w*|for|of|on|in|at|to|with|by|from|option|interest|royalty|stake|right|"
                         r"agreement)\b)[\w\-.@]+\s+){0,5}?" + _WH_OWNER_NOUN, text):
        n = m.group(1)
        if n.split()[0] not in ("The", "This", "Its", "Our") and not own(n) and not _OC_PLACE.match(text, m.end(1) + 3):
            marks.append((m.start(), m.end(), False))
            pm = re.search(r"(" + _WH_NAME + r")" + _WH_DESC + _WH_OWNER_NOUN, text[m.end(1) + 2:m.end()])
            if pm and not own(pm.group(1)):
                confirmed.add(pm.group(1))
    for m in re.finditer(r"\b(?i:held|owned|operated|controlled)\s+by\s+(" + _WH_NAME + r")", text):
        if m.group(1).split()[0] != "The" and not own(m.group(1)) and not _WH_NOT_OWNER.search(m.group(1)) and \
                not re.search(r"(?i)interests?\W+(?:\w+\W+){0,2}$", text[max(0, m.start() - 30):m.start()]):
            marks.append((m.start(), m.end(), False))
            n = named_before(m.start())
            if n and not own(n):
                confirmed.add(n)
    for m in re.finditer(r"\b(" + _WH_NAME + r")\s+(?:owns|holds|operates|controls)\s+(?:a|an|the|its|\d)", text):
        if m.group(1).split()[0] not in ("The", "This", "It") and not own(m.group(1)) \
                and not _WH_NOT_OWNER.search(m.group(1)):
            marks.append((m.start(), m.end(), False))
            pm = re.search(r"\bthe\s+(" + _WH_NAME + r")" + _WH_DESC + _WH_NOUN, text[m.end():m.end() + 120])
            if pm and not own(pm.group(1)):
                confirmed.add(pm.group(1))
    for m in re.finditer(r"(?i:joint\s+venture\s+between)\s+(" + _WH_NAME + r")\s+and\s+(" + _WH_NAME + r")", text):
        if not own(m.group(1)) and not own(m.group(2)):
            marks.append((m.start(), m.end(), False))
            n = named_before(m.start())
            if n and not own(n):
                confirmed.add(n)
    for m in re.finditer(r"(" + _WH_NAME + r")" + _WH_DESC + _WH_OWNER_NOUN + r"\s+of\s+(" + _WH_NAME +
                         r")\s+(?:Corp\w*|Inc|Ltd|Limited|Mines|Mining|plc)\b", text):
        if not own(m.group(2)):
            marks.append((m.start(), m.end(), False))
            if not own(m.group(1)):
                confirmed.add(m.group(1))
    for m in re.finditer(r"\b(" + _WH_NAME + r")\s+(?:Corp\w*|Inc|Ltd|Limited|plc)\b\.?,?(?:\s*\([^()]{0,40}\))?\s+(" +
                         _WH_NAME + r")" + _WH_DESC + _WH_OWNER_NOUN, text):
        if not own(m.group(1)) and not _WH_NOT_OWNER.search(m.group(1)) and m.group(2).split()[0] != "The":
            marks.append((m.start(), m.end(), False))     # 'Thesis Gold Inc. ("TAU") Lawyers-Ranch project'
            if not own(m.group(2)):
                confirmed.add(m.group(2))
    for m in re.finditer(r"\b(" + _WH_NAME + r")\s+(?:Corp\w*|Inc|Ltd|Limited|plc|Mining|Mines|Metals|Resources|Minerals|"
                         r"Gold|Copper|Energy)\.?,?\s+(?:recently\s+)?(?:announced|reported|has\s+(?:announced|reported|"
                         r"published|released))\b", text):
        if not own(m.group(1)) and not _WH_NOT_OWNER.search(m.group(1)):
            marks.append((m.start(), m.end(), False))
    for m in _OC_TICKER.finditer(text):
        b = re.search(r"(" + _WH_NAME + r")[\s.,]*(?:\([^()]{0,80}\)[\s.,]*)*$", text[max(0, m.start() - 200):m.start()])
        if m.group(1) not in tickers and not (b and own(b.group(1)) and _wh_toks(b.group(1))):
            marks.append((m.start(), m.end(), False))
    for m in _WH_URL.finditer(text):
        if not _WH_FILINGS.search(m.group(0)) and not any(w in m.group(1).lower().replace("-", "") for w in iw):
            marks.append((m.start(), m.end(), False))

    def passing(name):
        """Somebody else's for sure (an owner is named), or named only in passing."""
        return name in confirmed or rare(name)

    # a distance from our own ground: what lies there is somebody else's, and so is the deposit named before it --
    # unless the sentence goes on to the ground it was measured from ("... 50 km west of the Company's X project,
    # which hosts ...") or the deposit named before it is one of ours or one the release keeps coming back to
    for m in _WH_DISTANCE.finditer(text):
        obj = m.group("obj")
        if obj is not None:
            if not (_WH_OWNREF.match(obj) or own(obj) and _wh_toks(obj)):
                # "10 km west of X's producing Gamma Mine, which hosts ...": the figures that follow are the
                # place's we were measured against
                if re.match(r"[^.;]{0,60}?(?:,?\s*(?:which|that)\s+(?:hosts?|has|contains?|includes?)|,\s*(?:hosting|containing|"
                            r"with))\b", text[m.end():m.end() + 90]):
                    marks.append((m.end() - 1, m.end(), False))
                continue
            if re.match(r"\s*,?\s*(?:which|that|where|whose)\b", text[m.end():m.end() + 12]):
                continue
        elif not m.group("rel") or not re.search(r"\d|located|lies|lying|situated", m.group(0)):
            continue
        sub = named_before(m.start())
        if not sub or not _wh_toks(sub) or own(sub) or not passing(sub):
            continue                              # drill holes "600 metres northeast of Gryphon" are ours
        neighbours.add(sub)
        marks.append((m.end() - 1, m.end(), False))
    # a deposit placed next to, along strike from or compared with ours, and named in passing
    for m in re.finditer(r"(?i:adjacent\s+to|next\s+to|proximal\s+to|contiguous\s+(?:to|with)|bordering|borders|"
                         r"along\s+strike\s+(?:from|of|with)|on\s+trend\s+(?:with|from|of)|similar\s+to|"
                         r"analog\w*\s+(?:to|of))\s+(?:the\s+)?(?:[a-z][\w\-]*\s+){0,3}(" + _WH_NAME + r")"
                         + _WH_DESC + _WH_NOUN, text):
        objects.append((m.start(), m.end()))
        if not own(m.group(1)) and passing(m.group(1)):
            neighbours.add(m.group(1))
    # neighbour wording in front of a deposit that is not one of ours
    for m in re.finditer(r"\b(?:[Tt]he|[Aa]n?)\s+(?:adjacent|nearby|neighbou?ring|bordering)\s+(?:[a-z][\w\-]*\s+){0,2}"
                         r"(" + _WH_NAME + r")" + _WH_DESC + _WH_OWNER_NOUN, text):
        if not own(m.group(1)) and passing(m.group(1)):
            marks.append((m.start(), m.end(), False))
            neighbours.add(m.group(1))
    # a list of the region's or the world's deposits, a table with an owner column, a comparison
    for m in _WH_PEERS.finditer(text):
        marks.append((m.start(), m.end(), False))
    # a hedge
    for m in re.finditer(r"(?i)\breportedly\b|\b(?:is|are|was|were)\s+reported\s+to\s+(?:host|contain|include|have)", text):
        marks.append((m.start(), m.end(), False))
    # the issuer and its own projects
    for m in re.finditer(r"\b(?:[Tt]he\s+Company|Company's|[Tt]he\s+Corporation|Corporation's|[Oo]ur|[Ww]e)\b", text):
        marks.append((m.start(), m.end(), True))
    known = {w for n in inames for w in n} | {w for o in owns for w in o}
    seen_names = {}
    for m in re.finditer(r"\b" + _WH_NAME, text):
        g = m.group(0)
        if g not in seen_names:
            t = set(_wh_toks(g))
            seen_names[g] = bool(t & known) and not t <= _WH_DIRWORDS and (
                issuer(t) or any(_wh_same(t, o) for o in owns))
        if seen_names[g] and not any(a <= m.start() < b for a, b in objects):
            marks.append((m.start(), m.end(), True))
    # a neighbour's name again, as the subject of a later sentence ("The Cameron Lake Deposit hosts ...")
    for n in neighbours | confirmed:
        t = _wh_toks(n)
        if not t:
            continue
        for m in re.finditer(r"(?i)\b" + r"\W+".join(re.escape(w) for w in t) + r"\b", text):
            k = bisect.bisect_right(starts, m.start()) - 1
            if (n in confirmed or m.start() - starts[k] <= 60) and not own(text[m.start():m.end() + 30].split(",")[0]):
                marks.append((m.start(), m.end(), False))
    # "The project hosts ...": the issuer's, unless the last project of that kind named was a neighbour's
    for m in re.finditer(r"(?:^|(?<=[.!?:]\s)|(?<=\n))(?:The|This)\s+(project|property|deposit|mine)\b", text):  # anaphors
        last = None
        for k in re.finditer(r"(" + _WH_NAME + r")" + _WH_DESC + r"(?i:" + m.group(1) + r")\b",
                             text[max(0, m.start() - 1200):m.start()]):
            last = k.group(1)
        if last and _wh_toks(last):
            if own(last):
                marks.append((m.start(), m.end(), True))
            elif any(set(_wh_toks(last)) <= set(_wh_toks(x)) for x in neighbours | confirmed):
                marks.append((m.start(), m.end(), False))
    # an own-name match that sits inside a longer neighbour's name, or vice versa: the longer one decides
    marks.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    out, last_end = [], -1
    for s, e, k in marks:
        if out and s < out[-1][1] and k != out[-1][2] and e <= out[-1][1]:
            continue
        out.append((s, e, k))
    return {"marks": out, "at": [x[0] for x in out], "starts": starts, "iw": iw}


def _wh_credit(text, at, iw):
    """After the figures, before the sentence is over: a link to somebody else's website, or a parenthesis that
    names another company's report."""
    seg = text[at:at + 400]
    end = re.search(r"[.!?]\s+[A-Z(]|\n\s*\n", seg)
    seg = seg[:end.start() + 1] if end else seg
    for m in re.finditer(r"\(\s*(?:https?://)?(?:www\.)?([a-z0-9\-]+)(?:\s*\.\s*[a-z]{2,4}){1,2}\b[^()]{0,80}\)", seg):
        dom = m.group(1).lower()
        if not _WH_FILINGS.search(m.group(0)) and not any(w in dom.replace("-", "") for w in iw):
            return True
    for m in re.finditer(r"\([^()]{0,80}?(?:[Rr]eport|[Rr]elease|[Aa]nnouncement|[Ss]tatement)[^()]{0,40}?,\s*(" + _WH_NAME +
                         r")\s+(?:Limited|Ltd|Inc|Corp\w*|plc)\b", seg):
        if not _WH_NOT_OWNER.search(m.group(1)) and not (set(_wh_toks(m.group(1))) & iw):
            return True
    return False


def _wh_whose(r, text, wctx):
    """Whose the row's figures are, from what its own sentence -- or, when that sentence names nobody ("There is
    an additional Indicated Resource of ..."), the one before it in the same paragraph -- says last before them:
    "own" when that is the figures' own sentence and it points to the issuer, "foreign" when it points to somebody
    else, None when nothing says."""
    at = r.get("_at") if r.get("source") != "table" else r.get("_blk_at")
    if at is None:
        return None
    if r.get("source") == "table" and r.get("_at") is not None:
        at = max(at, _table_top(text, r["_at"]))     # 1.0.23 FIX3: the table's own top, not its reading block's
    starts, marks = wctx["starts"], wctx["marks"]
    i = bisect.bisect_right(starts, at) - 1
    hi = at
    for k in range(2):
        lo = starts[i] if i >= 0 else 0
        last = lo < at - 900 or "\n\n" in text[lo:hi].rstrip("\n")
        if last:
            lo = max(lo, text.rfind("\n\n", 0, hi) + 2, at - 900)
        j = bisect.bisect_left(wctx["at"], hi) - 1          # the last mark before hi
        if j >= 0 and marks[j][0] >= lo:
            # (1.0.23 FIX3: a table has no sentence of its own -- the sentence that introduces it, in the same
            # paragraph, is its: "The updated resource at the Company's Alpha Gold project ... was estimated by consultants")
            return "foreign" if not marks[j][2] else ("own" if k == 0 or r.get("source") == "table" else None)
        if last or re.search(r"\n[ ]*\n[ ]*$", text[max(0, lo - 12):lo]):
            return None                           # the sentence opens a paragraph: nothing before it counts
        hi, i = lo, i - 1
        if i < 0:
            break
    return None


# 1.0.23: an exploration target is a conceptual range, never a classified estimate, even when the sentence calls
# the method an "Inferred Resource Estimate" ("... to define an exploration target of between 19.06 million tonnes
# and 23.30 million tonnes"); and a tonnage given as a range is a target, not an estimate.
_RE_TARGET = re.compile(r"(?i)\bexploration\s+targets?\b|\btarget\s+(?:range|tonnage)s?\b")
_RE_RANGE = re.compile(r"(?i)\bbetween\s+\d[\d,.]*\s*(?:million|billion|thousand|mt|kt|t)?\s*(?:tonnes|tons|t)?\s*and\s+\d|"
                       r"\b\d[\d,.]*\s*(?:-|to)\s*\d[\d,.]*\s*(?:million\s+tonnes|million\s+tons|mt|kt)\b")


def _target_row(r):
    if r.get("source") not in ("prose", "headline"):
        return False
    win, pos = r.get("_win") or "", r.get("pos") or 0
    if _RE_TARGET.search(win[:pos]):
        return True
    for m in _RE_RANGE.finditer(win) if r["tonnes"] else ():
        for x in re.findall(r"\d[\d,.]*", m.group(0)):
            v = _num(x)
            if v and any(abs(v * k - r["tonnes"]) <= 0.005 * r["tonnes"] for k in (1, 1e3, 1e6, 1e9)):
                return True                       # the row's tonnage is one end of a range
    return False


# 1.0.23: a subset quoted after a lead-in that names it as one, however long the list that follows: "A high-grade
# subset of the Updated Resource ... consists of: o Indicated resources of ...; and o Inferred resources of ...",
# "Included within the "global" Mineral Resource is a Measured and Indicated "high grade zinc zone" of 13.5 Mt"
_RE_SUBSET_LEAD = re.compile(r"(?i)\bsubset\b|(?:^|[.:]\s+|\n)(?-i:Included)\s+within\s+(?:the|this|these)\b|"
                             r"\b(?:higher|high)[\s-]grade\s+(?:core|portion|subset|component)\b")


def _subset_before(r, text):
    at = r.get("_at")
    if r.get("source") != "prose" or at is None:
        return False
    back = text[max(0, at - 450):at]
    cut = max([m.end() for m in re.finditer(r"[.!?]\s+(?=[A-Z\"])|\n[ ]*\n", back)] or [0])
    return bool(_RE_SUBSET_LEAD.search(back[cut:]))


def _owner_named(r):
    """The deposit read is a company's possessive ("X Lithium's"): the figures are named by their owner, and on this
    page the owner is another company."""
    d = r.get("deposit") or ""
    return bool(re.search(r"(?:'s|(?<=s)')$", d)) and not re.search(r"(?i)\b(?:company|corporation)'s$", d)


# Guide section 4: a higher-grade subset quoted inside a resource ("the high-grade Core Zone, which has ...", "within
# the Indicated, a higher-grade portion of ...", "of which ...") is part of a row already published, not a row.
_RE_SUBSET = re.compile(r"(?i)\b(?:higher|high)[\s-]grade\s+(?:core|portion|subset|component)\b|\bsubset\b")


_RE_BOUND = re.compile(r"(?i)\b(?:in\s+excess\s+of|more\s+than|greater\s+than|exceeding|upwards\s+of|at\s+least|over|>)"
                       r"\s*(\d[\d,.]*)\s*(million|billion|thousand)?\s*(tonnes|tonne|tons|mt|kt|t)\b")


def _bound_row(r):
    """A prose row whose tonnage is a bound ("resources in excess of 100 Mt"): a bound is not an estimate."""
    if r.get("source") not in ("prose", "headline") or not r["tonnes"]:
        return False
    for m in _RE_BOUND.finditer(r.get("_win") or ""):
        u = m.group(3).lower()
        v = _num(m.group(1), m.group(2), {"mt": 1e6, "kt": 1e3}.get(u, 0.90718474 if u.startswith("ton") and
                                                                        u != "tonne" and u != "tonnes" else 1.0))
        if v and abs(v - r["tonnes"]) <= 0.01 * r["tonnes"]:
            return True
    return False


def _subset_row(r):
    """A prose row whose own clause introduces a higher-grade part of an estimate."""
    if r.get("source") != "prose":
        return False
    win = r.get("_win") or ""
    pos = r.get("pos") or 0
    lo = max((m.end() for m in re.finditer(r"[\u2022\u25aa\u25a0;]", win[:pos])), default=0)
    return bool(_RE_SUBSET.search(win[max(lo, pos - 160):pos + 40]))


# A deposit has a name. Column labels, units, footnote markers, dates and dollar figures are not one.
_NOT_DEPOSIT = {"revenue", "revenues", "geos", "segment", "segments", "orebody", "orebodies", "property", "properties",
                "location", "uncapped", "capped", "summary", "change", "changes", "subtotal", "sub-total", "variance",
                "difference", "notes", "source", "facies", "material", "lithology", "category", "classification",
                "year", "end", "year-end", "operations", "operation", "mines", "average", "contained",
                "in-situ", "insitu", "cg",   # 1.0.23: "Tonnage Cg In-situ" (a graphite table's header),
                "feasibility", "study"}       # "the Feasibility Study pit"
_COLUMN_WORDS = {"content", "contents", "historical", "historic", "mineralization", "mineralisation", "situ"}   # FIX5
# FIX5 rev b: a name that opens with a pronoun or the issuer's self-reference is a sentence's subject
_PRONOUN_LEAD = {"it", "its", "this", "these", "that", "those", "they", "their", "we", "our", "he", "she", "which",
                 "there", "here", "company", "company's", "companies'", "corporation", "corporation's"}
_JUNK_WORDS = (_HEADER_WORDS | _NOT_DEPOSIT) - {"zone", "deposit", "pit", "area", "domain", "and", "of", "the", "in",
                                                "type", "total", "k", "m", "t"}
_RE_DEP_CAT = re.compile(r"(?i)\s*(?:[-,(]\s*)?\b(?:total\s+)?(?:measured|indicated|inferred|proven|proved|probable|"
                         r"m\s*&\s*i|p\s*&\s*p)\b.*$")
_RE_DEP_DATE = re.compile(r"(?i)[\s,-]*\b(?:january|february|march|april|may|june|july|august|september|october|"
                          r"november|december)\s+\d{1,2},?\s+\d{4}\b[\s,-]*")


def _deposit_or_none(d):
    """The deposit name cleaned of what is not a name, or None when nothing of a name is left."""
    if not d:
        return d
    s = _WS.sub(" ", str(d)).strip()
    # 1.0.23: "TDG Gold's AuWEST", "Celsius' advanced-stage Maalinao-...": the owner in front is no part of the name
    s = re.sub(r"^[A-Z][\w&\-]*(?:\s+[A-Z][\w&\-]*){0,3}(?:'s|(?<=s)')\s+(?:[a-z][\w\-]*\s+){0,2}(?=[A-Z])", "", s)
    s = _RE_DEP_DATE.sub(" ", s).strip(" ,.;:-")
    s = re.sub(r"(?<=[a-z\u00e9])\d(?:\s*,\s*\d)*$", "", s)                  # "C\u00f4t\u00e9 Gold3,4": footnote markers
    s = re.sub(r"\s*\((?:\d{1,2}(?:\s*,\s*\d{1,2})*|[a-z])\)", "", s).strip()   # "(2)", "(a)"
    if "(" in s and (s.count("(") != s.count(")") or re.search(r"\$|/oz|/t\b|\d", s[s.index("("):])):
        s = s[:s.index("(")].strip(" ,.;:-")                             # "Crevier (Scenario for a pit at US$82/kg"
    cut = _RE_DEP_CAT.search(s)
    if cut and cut.start() > 0:
        s = s[:cut.start()].strip(" ,.;:-")                              # "Cosal\u00e1 M&I", "Sub-total Proven"
    elif cut:
        return None
    if re.fullmatch(r"(?i)(?:sub|sub-?total|total|grand\s+total|totals)", s):
        return None
    if not s or not re.match(r"[^\W\d_]", s) or re.search(r"[a-z]{3,}\.\s+[A-Z]", s) \
            or re.search(r"\$|/oz\b|%", s):
        return None
    words = [w for w in re.split(r"[\s,;/()+-]+", s.lower()) if w]
    if not words or all(w in _METAL or w in ("deposit", "deposits", "project", "zone", "mine") for w in words):
        return None                                                      # "Gold": a metal is not a deposit
    # FIX5: a column label is no deposit -- "Content", "Deposit and Category", "Mineralization Type", "In-Situ Graphite (kt)"
    if all(w in _HEADER_WORDS or w in _NOT_DEPOSIT or w in _COLUMN_WORDS for w in words) \
            or (sum(1 for w in words if w in _COLUMN_WORDS or w in _JUNK_WORDS or _unit_in(w)[0] and len(w) <= 3) * 2
                >= len(words) >= 2 and any(w in _COLUMN_WORDS for w in words)):
        return None
    junk = sum(1 for w in words if w in _JUNK_WORDS or _unit_in(w)[0] and len(w) <= 3) \
        + sum(1 for t in re.findall(r"[^\W\d_]\w*", s)
              if len(t) >= 2 and (t in _SYMBOLS or _EQ_SUFFIX.match(t) and metal_of(t)))
    if junk == len(words) or (junk >= 2 and junk * 2 >= len(words)):
        return None
    if words[-1] in ("at", "a", "an", "of", "the", "for", "to", "and", "in", "on", "with", "by"):
        return None
    # 1.0.23: "Cameron Lake Deposit hosts" -- the verb of the sentence is no part of the name
    s = re.sub(r"\s+(?:hosts?|has|have|contains?|includes?|comprises?|is|are|was|were)$", "", s)
    # 1.0.23: "Ho2O" (a column of the oxide table) is no deposit
    if all(re.fullmatch(r"[A-Z][a-z]?\d+O\d*", t) for t in s.split()):
        return None
    return s


_RE_METAL_TAIL = re.compile(r"(?i)\s+(?:gold|silver|copper|zinc|nickel|cobalt|lithium|uranium|graphite|antimony|"
                            r"tungsten|molybdenum|palladium|platinum|vanadium|tantalum|"
                            r"(?:energy|battery|base|precious|critical)\s+(?:metals?|minerals?))$")


def _no_metal_tail(name):
    """FIX5: 'Alpha' of 'Alpha Gold' (from "the Alpha Gold Project"), 'Beta' of 'Beta Energy Metals': the commodity after
    a project's name is not part of it."""
    if re.search(r"[\d/%<>]", name):
        return name
    s = name
    while True:                     # "Alpha Gold and Copper", "Alpha gold cobalt": every commodity word goes
        t = re.sub(r"(?i)[\s,]+(?:and|&)$", "", _RE_METAL_TAIL.sub("", s)).strip(" ,-")
        if t == s:
            break
        s = t
    if s == name or not re.search(r"[A-Za-z]{3,}", s) or not s[:1].isupper() or s.lower() in _NOT_A_NAME \
            or all(metal_of(w) for w in s.split()) \
            or s.lower() in ("the", "north", "south", "east", "west", "new", "main", "big", "red", "black", "white"):
        return name
    return s


def _copies(rows):
    """Rows that repeat another row's tonnage and grades under a second category.

    "an Indicated Resource of ... (4,726,000 tonnes) and an Inferred Resource of ... (1,813,000 tonnes)" filed the
    Inferred 1,813,000 t under Indicated as well. One tonnage and grade belong to one category; a combined category
    equal to one of its parts (Proven & Probable = Probable when there is no Proven) is not a copy. Of two copies, the
    one whose category already has another row for the same deposit is the stray."""
    drop = set()
    for i, a in enumerate(rows):
        for j in range(i + 1, len(rows)):
            b = rows[j]
            if not a["tonnes"] or a["tonnes"] != b["tonnes"] or a["basis"] != b["basis"] \
                    or a["category"] == b["category"] or a["category"] in b["category"] \
                    or b["category"] in a["category"]:
                continue
            ga = sorted((g["metal"] or "", g["value"]) for g in a["grades"])
            if ga != sorted((g["metal"] or "", g["value"]) for g in b["grades"]):
                continue
            for x, y in ((a, b), (b, a)):
                if any(k is not x and k is not y and k["category"] == x["category"] and k["basis"] == x["basis"]
                       and _norm_dep(k["deposit"]) == _norm_dep(x["deposit"]) and k["tonnes"] != x["tonnes"]
                       for k in rows):
                    drop.add(id(x))
                    break
    return drop


def _join_wrapped_categories(ls):
    """1.0.22: "Sub-total Proven and" / "Probable 24.40 2.70 ..." is one label, Proven & Probable, that the PDF wrapped;
    read as two lines it filed the subtotal as Probable. Joined with a space, so every later line keeps its position."""
    out = list(ls)
    for i in range(len(out) - 1):
        a, b = out[i], out[i + 1]
        if (re.search(r"(?i)\b(?:prove[nd]|measured)\s*(?:and|&|\+)\s*$", a)
                and re.match(r"(?i)\s*(?:probable|indicated)\b", b)) or \
                (re.search(r"(?i)\b(?:prove[nd]|measured)\s*$", a) and len(a) <= 40
                 and re.match(r"(?i)\s*(?:and|&|\+)\s*(?:probable|indicated)\b", b)):
            out[i], out[i + 1] = a + " " + b, ""
    return out


def _not_rows(rows, head, text, project=None):
    """1.0.22: drop what the release states that is not a row of its own estimate.
      - a Total line: a table total sums rows already published (not one of ~50 such rows ever matched a label);
      - a tonnage under 1,000 t: a grade, a count or a figure in thousands read as tonnes -- the tonnage is dropped;
      - a row with neither a deposit nor a tonnage: contained metal from a portfolio or summary sentence;
      - a higher-grade subset of an estimate (guide section 4);
      - another company's deposit (guide section 1);
      - a row copied under a second category."""
    ctx, wctx, kept, bare = None, None, [], []
    for r in rows:
        if r["category"] == "Total" and not (r.get("_combined") and r["tonnes"]):   # 1.0.23: "indicated and
            continue                                                                  # inferred of 3.2 Mt" stays
        if _target_row(r) or _subset_before(r, text) or _owner_named(r):              # 1.0.23
            continue
        if r["tonnes"] is not None and r["tonnes"] < 1000:
            r["tonnes"] = None
        if not r["deposit"] and r["tonnes"] is None:
            if r.get("source") == "prose" and r["contained"] and not r["grades"] \
                    and not _RE_DELTA.search(r.get("_win") or "") \
                    and not _RE_BARE_DELTA.search(r.get("_win") or ""):
                bare.append(r)
            continue
        if _subset_row(r) or _bound_row(r):
            continue
        if ctx is None:
            ctx = _owner_context(head, text)
        if wctx is None:                                       # 1.0.23: whose figures, sentence by sentence
            wctx = _wh_context(head, text) if not _royalty_release(head, text) else {}
        whose = _wh_whose(r, text, wctx) if wctx else None
        # the figures' own sentence naming one of the issuer's deposits outweighs a company named nearby
        if whose != "own" and _foreign_row(r, text, ctx):
            continue
        if whose == "foreign" or (wctx and r.get("source") == "prose" and r.get("_at") is not None
                                  and _wh_credit(text, r["_at"], wctx["iw"])):
            continue
        kept.append(r)
    if not kept and bare:
        ctx = ctx if ctx is not None else _owner_context(head, text)
        if wctx is None:
            wctx = _wh_context(head, text) if not _royalty_release(head, text) else {}
        # 1.0.23 FIX3: a release whose only figures are totals stated in prose with no deposit and no tonnage
        # ("Measured & Indicated Total Resource of 537,300 ounces of gold and 8.1 million ounces of silver", "Proven
        # and Probable Reserves stand at 5.56 Moz of gold") still states its own estimate; the rule above is for
        # a summary sentence beside the rows that state it in full
        kept = [r for r in bare if not (_subset_row(r) or _bound_row(r))
                and not (wctx and _wh_whose(r, text, wctx) == "foreign") and not _foreign_row(r, text, ctx)]
    drop = _copies(kept)
    kept = [r for r in kept if id(r) not in drop]
    # a summary sentence's contained metal for a deposit and category the table states in full is the same row
    return [r for r in kept if r["tonnes"] is not None or not any(
        k is not r and k["tonnes"] is not None and _restates(r, k) for k in kept)]


_SUBJ_NAME = r"((?:[A-Z][\w'\u2019\-]*)(?:\s+(?:[A-Z][\w'\u2019\-]*|de|del|la|el|y|do|da|dos)){0,3})"
_SUBJ_GEO = r"(?:\s+(?:breccia|deposit|zone|vein|pit|project|property|mine|pegmatite|lens|orebody|complex))?"
_RE_SUBJ_LEAD = re.compile(r"^\W*(?:The\s+)?" + _SUBJ_NAME + _SUBJ_GEO + r"\s+(?:has|hosts?|contains?|comprises?|includes?|"
                           r"consists?\s+of)\b(?=[^.;]{0,60}?(?i:measured|indicated|inferred|prove[nd]|probable|"
                           r"reserves?|resources?|\d))")
_RE_SUBJ_BULLET = re.compile(r"^\W*" + _SUBJ_NAME + r"\s+(?:deposit|zone|project|property|mine|pit)\s*[-:\u2013\u2014]\s")
_RE_SUBJ_AT = re.compile(r"(?i:\b(?:resources?|reserves?|estimate|mre))\s+(?:at|for|on)\s+(?:the\s+)?" + _SUBJ_NAME
                         + _SUBJ_GEO + r"(?![\w'\u2019\-])")
_SUBJ_STOP = {"company", "corporation", "corp", "inc", "ltd", "us", "usd", "cad", "ni", "december", "january", "february",
              "march", "april", "may", "june", "july", "august", "september", "october", "november", "measured",
              "indicated", "inferred", "proven", "probable", "mineral", "total", "this", "these", "its", "our", "their",
              "year", "end", "year-end", "q1", "q2", "q3", "q4", "canada", "mexico", "peru", "chile", "nevada",
              "pea", "pfs", "dfs", "bfs", "fs", "mre", "study", "report", "plan", "update", "estimate", "the", "a", "an",
              "phase", "stage", "mine", "project", "property", "deposit", "zone", "resource", "resources", "reserve",
              "reserves", "technical", "preliminary", "feasibility", "economic", "assessment"}


def _subject_name(win):
    """FIX5: the deposit a prose row's own sentence names -- "Alpha has Proven and Probable reserves of ...", "The Beta
    breccia contains ... Inferred", "the probable mineral reserve at ABC contains ...", "a Mineral Resource Estimate at
    Gamma consisting of ...", "Delta deposit - historical resource: 16 Mt indicated ..."."""
    for rx in (_RE_SUBJ_LEAD, _RE_SUBJ_AT, _RE_SUBJ_BULLET):
        m = rx.search(win or "")
        if not m:
            continue
        name = _WS.sub(" ", m.group(1)).strip()
        if name.split()[0].lower() in _SUBJ_STOP or name.lower() in _SUBJ_STOP or _CLASS_WORD.match(name) \
                or _RE_GRID_CAT.search(name) or not _named(name):
            continue
        name = _place(_deposit_or_none(name))
        if name:
            return name
    return None


def _prev_sentence_name(text, at):
    """FIX5: a sentence that states figures and names nothing takes the deposit one of the three sentences before it
    (same paragraph) names: "... the Alpha deposit is located at ..." then "an Indicated Mineral Resource Estimate of
    5.5 Mt ..."."""
    back = text[max(0, at - 900):at]
    para = re.split(r"\n[ \t]*\n|\n\s*[\u2022\u25aa\u25cf\uf0b7\u2013\u2014-]\s", back)[-1]
    sents = [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z\u201c\"(])", para.strip()) if x.strip()]
    for prev in sents[::-1][:3]:
        name, kind = project_and_kind(prev)
        name = _place(_deposit_or_none(name)) if name else _subject_name(prev)
        # a name the release gives is written as one: "the Alpha underground mine" names no deposit
        if name and all(w[:1].isupper() or w[:1].isdigit() or w.lower() in _NAME_PARTICLE for w in name.split()):
            return name
    return None


def _lead_in_project(text, part_at):
    """1.0.23: a list item takes its project from the list's lead-in: "Mineral Resource and Mineral Reserve estimates
    for the Porvenir Project, effective December 31, 2022: (bullet) 270 kt of Proven Mineral Reserves ..."."""
    back = text[max(0, part_at - 1200):part_at]
    colon = back.rfind(":")
    if colon < 0 or re.search(r"[.!?]\s+[A-Z]|\n[ ]*\n", back[colon + 1:]):
        return (None, None)
    lead = re.split(r"[.!?]\s+", back[:colon])[-1][-300:]
    if len(lead) < 8:
        return (None, None)
    name, kind = project_and_kind(lead)
    return (_pn_casefix(name, text) or name, kind) if name and name.isupper() else (name, kind)


def _fold_contained(rows):
    """1.0.23: a row is one deposit and one category. "an indicated mineral resource of 1.325 million tonnes LCE" and
    "the average grade of the indicated mineral resources was 669 ppm lithium (over ... 372,845,000 tonnes)" are one
    row: a row that states only contained metal goes into the one row of the same deposit and category that states
    the tonnage, when there is exactly one such row and it has no contained metal of its own."""
    drop = set()
    for r in rows:
        if r["tonnes"] is not None or r["grades"] or not r["contained"] \
                or any((c["value"] or 0) < 1000 for c in r["contained"]):
            continue                      # (3.12 "lb" is a figure whose unit header was not read)
        cands = [k for k in rows if k is not r and k["tonnes"] is not None and k["category"] == r["category"]
                 and k["basis"] == r["basis"] and _norm_dep(k["deposit"]) == _norm_dep(r["deposit"])]
        if len(cands) == 1 and not cands[0]["contained"]:
            cands[0]["contained"] = r["contained"]
            drop.add(id(r))
    return [r for r in rows if id(r) not in drop]


def _two_names(rows):
    """1.0.23: one figure of one category filed under two deposit names -- a company total the reader filed under
    the release's project, and the footnote that credits the same figure to the project it comes from -- is one
    row, the one whose name the release gives."""
    drop = set()
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a["category"] != b["category"] or a["basis"] != b["basis"] \
                    or _norm_dep(a["deposit"]) == _norm_dep(b["deposit"]) or a.get("_dep_fb") == b.get("_dep_fb"):
                continue
            if a["tonnes"] or b["tonnes"]:
                same = a["tonnes"] and b["tonnes"] and abs(a["tonnes"] - b["tonnes"]) <= 0.005 * a["tonnes"]
            else:
                ca = sorted((c["unit"] or "", c["value"]) for c in a["contained"])   # "LCE" read two ways
                same = bool(ca) and ca == sorted((c["unit"] or "", c["value"]) for c in b["contained"])
            if same:
                drop.add(id(a if a.get("_dep_fb") else b))
    return [r for r in rows if id(r) not in drop]


def _restates(r, k):
    """r (no tonnage) repeats k: same category and basis, a compatible deposit, and every figure r states is k's."""
    if r["category"] != k["category"] or r["basis"] != k["basis"] or not (r["contained"] or r["grades"]):
        return False
    a, b = set(_norm_dep(r["deposit"]).split()), set(_norm_dep(k["deposit"]).split())
    if a and b and not (a <= b or b <= a) and not r.get("_dep_fb") \
            and not (len(r["contained"]) >= 2 and not r["grades"]
                     and all(any(x["metal"] == c["metal"] and x["value"] and c["value"]
                                 and abs(x["value"] - c["value"]) <= 0.02 * max(x["value"], c["value"])
                                 for x in k["contained"]) for c in r["contained"])):
        # (1.0.23 FIX3: a name the row only borrowed from the release does not tell them apart; FIX5: nor does a name
        # beside two or more contained figures that are exactly another row's -- the same estimate summarised)
        return False

    def has(fig, figs, eq=False):
        # (1.0.23 FIX3: a summary's "88 million pounds of zinc equivalent" is the table's 87.9 Mlb of zinc --
        # the same contained figure, under the metal or its equivalent; and a summary rounds: "1.0 million ounces"
        # is the table's 1,062 koz)
        tol = 0.1 if eq and fig["value"] and float("%.2g" % fig["value"]) == fig["value"] else 0.02
        return any((x["metal"] == fig["metal"] or not x["metal"] or not fig["metal"]
                    or eq and x["metal"].replace("Eq", "") == fig["metal"].replace("Eq", "")) and x["value"]
                   and abs(x["value"] - fig["value"]) <= tol * max(x["value"], fig["value"]) for x in figs)
    return all(has(c, k["contained"], True) for c in r["contained"]) and all(has(g, k["grades"]) for g in r["grades"])


def analyse(headline: str, body: str) -> dict:
    head = clean(headline or "")
    text = clean(body or "")
    res = {"is_resource_estimate": False, "rows": [], "project": None, "mre_type": None,
           "announces": False, "reason": "no_figures"}

    lines = _join_wrapped_categories(text.split("\n"))
    rows = read_tables(lines)
    if _RE_GRID_CAT.search(text):                            # 1.0.23 FIX3: rows a table labels only by name
        rows += read_grids(lines, {r["pos"]: r for r in rows})
    offs = [0]                          # 1.0.22: where each line starts, so every row knows where it was read
    for ln in lines:
        offs.append(offs[-1] + len(ln) + 1)
    for r in rows:
        r["_at"], r["_blk_at"] = offs[r["pos"]], offs[r.get("_blk", r["pos"])]
    # "6. 1 million tonnes": a decimal the PDF split (the same length, so every position still holds)
    ptext = re.sub(r"(?i)(\d)\. (\d{1,3})(?=\s*(?:million|billion|thousand|mt|moz|koz|kt|%|g/t)\b)", r"\1.\2 ",
                   reflow(text))
    # FIX5: "0.6 7 million tonnes", a decimal the PDF split after its first digit
    ptext = re.sub(r"(?i)(?<![\d.,])(\d\.\d) (\d)(?=\s*(?:million|billion|mt|moz|koz|kt)\b)", r"\1\2 ", ptext)
    rows += read_prose(ptext)
    for r in read_prose(head + "."):
        r["source"], r["pos"], r["_win"] = "headline", -1, head
        r["_at"] = r["_blk_at"] = None
        rows.append(r)
    if not rows:
        return res

    announces = release_announces(head, text)
    project = _release_project_pn(head, text, release_project(head, text[:1500]), rows)   # 1.0.20
    if project and _RE_HEAD_VERB.match(project):
        project = None    # 1.0.23: "Intersect Broad" (Zones), "UPDATE KUBI GOLD" (Project): a headline's verb is no name
    res["announces"] = announces
    res["project"] = project
    res["mre_type"] = mre_type(head, text)

    # one cut-off stated anywhere and no column for it: Military Metals puts it in the notes
    doc_cut = cutoff_in(text) or cutoff_in(head)
    # 1.0.22: where the release states several cut-offs, a row takes the one stated nearest to it, not the first
    cuts = [(m.start(), m) for m in _RE_CUTOFF_VAL.finditer(text)]
    if len({m.group("a") or m.group("b") for _p, m in cuts}) <= 1:
        cuts = []
    only_metal = release_metal(head, text)
    by_unit = None
    for r in rows:
        if only_metal:
            for fig in r["grades"] + r["contained"]:
                if fig["metal"] is None:
                    fig["metal"] = only_metal
        # 1.0.22: a grade with no metal is a figure no reader can use. Where the whole release names one metal of the
        # kind the unit is used for (g/t: a precious metal; %: a base or battery metal), the grade is that metal's;
        # otherwise it is not published
        if any(g["metal"] is None for g in r["grades"] + r["contained"]):
            if by_unit is None:
                by_unit = _metal_by_unit(head + "\n" + text)
            for fig in r["grades"] + r["contained"]:
                if fig["metal"] is None:
                    fig["metal"] = by_unit.get(fig["unit"])
            r["grades"] = [g for g in r["grades"] if g["metal"]]
        # once the metal is known: Canada Nickel's "46% Increase" is no nickel grade
        r["grades"] = [g for g in r["grades"] if not (_impossible_pct(g) or _implausible_gpt(g))]
        for g in r["grades"]:
            if g["metal"] == "C" and g["unit"] == "%":
                g["metal"] = "Cg"           # FIX5: a graphite deposit's grade is graphitic carbon ("10.27% Cg")
        # 1.0.22: a column label, a footnote, a date or a piece of a sentence is no deposit name
        r["deposit"] = _deposit_or_none(r["deposit"])
        if not r["deposit"]:
            if r.get("_proj") is None and r.get("source") == "prose" and r.get("_at") is not None:
                r["_proj"], r["_proj_kind"] = _lead_in_project(text, r["_part_at"])     # 1.0.23
            r["_dep_fb"] = not _deposit_or_none(r.get("_proj"))                        # 1.0.23
            r["deposit"] = _deposit_or_none(r.get("_proj")) or _deposit_or_none(project)
            r["deposit"] = qualify(r["deposit"], project, r.get("_proj_kind"))
            if r["deposit"] and not _deposit_or_none(r.get("_proj")) and r.get("source") == "prose":
                # FIX5: the deposit the figures' own sentence names ("Beta hosts Indicated mineral resources of ...")
                # outranks the release's project, which may be another of the company's projects
                own = _subject_name(r.get("_win") or "")
                if own and not (set(_norm_dep(own).split()) & set(_norm_dep(r["deposit"]).split())):
                    r["deposit"] = own
            if not r["deposit"] and r.get("source") == "prose":            # FIX5
                r["deposit"] = _subject_name(r.get("_win") or "")
                if not r["deposit"] and r.get("_part_at") is not None:
                    r["deposit"] = _prev_sentence_name(text, r["_part_at"])
        elif r.get("_grid") != "named":                  # (1.0.23 FIX3: "Discovery - Underground" is whole)
            q = qualify(r["deposit"], project)
            if not q:
                # FIX5: "Northco Minerals Corp. - Alpha Project" (a caption naming the owner, then the project), "Inc"
                # (the end of a wrapped caption): no place, so the part after the owner, else the release's project
                m = re.search(r"\s[-\u2013\u2014]\s+([^-\u2013\u2014]+)$", r["deposit"])
                q = qualify(_deposit_or_none(m.group(1).strip()), project) if m else None
                if not q:
                    q = qualify(_deposit_or_none(r.get("_proj")) or _deposit_or_none(project), project)
                    r["_dep_fb"] = True
            r["deposit"] = q
            # 1.0.23 FIX3: an orebody code ("BA", "SW") read from a table's row label is shown with its project
            if r.get("_grid") and project and r["deposit"] and re.fullmatch(r"[A-Z0-9]{1,3}", r["deposit"]):
                r["deposit"] = "%s - %s" % (project, r["deposit"])
        if r["cut_off"] is None:
            r["cut_off"] = doc_cut
            at = r.get("_blk_at") if r.get("_blk_at") is not None else r.get("_at")
            if cuts and at is not None:
                near = min(cuts, key=lambda c: abs(c[0] - at))[0]
                r["_near_cut"] = cutoff_in(text[near:near + 160])   # set after _dedupe: shown, not used to split
        if not announces or r.get("_hist") or _RE_BACKGROUND.search(_own_bullet(r)):
            r["context"] = "background"

    rows = _not_rows(rows, head, text, project)   # 1.0.22
    rows = [r for r in rows if not _figureless(r)]
    rows = _merge_same_figures(sorted(rows, key=lambda r: (_SRC_RANK.get(r["source"], 9), r["pos"])))
    rows = _fold_contained(_two_names(_dedupe(rows)))[:MAX_ROWS]   # 1.0.23: _two_names, _fold_contained
    for r in rows:
        if r["deposit"]:
            r["deposit"] = _no_metal_tail(r["deposit"])      # FIX5
            if r["deposit"] and r["deposit"].split()[0].lower().replace("\u2019", "'") in _PRONOUN_LEAD:
                # FIX5 rev b: "It", "Company's": a sentence's subject is no name; the release's project when it is
                # written as a name ("Kahuna Diamond"), else none
                pj = _deposit_or_none(project)
                pj = _no_metal_tail(pj) if pj else None
                r["deposit"] = pj if pj and pj.split()[0].lower().replace("\u2019", "'") not in _PRONOUN_LEAD and all(
                    w[:1].isupper() or w[:1].isdigit() or w.lower() in _NAME_PARTICLE for w in pj.split()) else None
        if r.get("_near_cut"):
            r["cut_off"] = r["_near_cut"]
        r.pop("_near_cut", None)
        r.pop("_win", None)
        for k in ("_at", "_blk_at", "_blk", "_part_at"):
            r.pop(k, None)
        r.pop("_proj", None)
        r.pop("_proj_kind", None)
        r.pop("_hist", None)
        for k in ("_combined", "_dep_fb", "_part_at", "_grid", "_dep0"):   # 1.0.23 (FIX5: _dep0)
            r.pop(k, None)
    res["rows"] = rows
    res["is_resource_estimate"] = bool(rows)
    res["reason"] = "rows" if rows else "no_figures"
    return res


# ------------------------------------------------------------------ facts store adapter
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["rows"]:
        return [F.Record(KIND, facts=[F.Fact("is_resource_estimate", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"])], confidence=0.0)]
    out = []
    for r in a["rows"]:
        fs = [F.Fact("is_resource_estimate", value_num=1.0),
              F.Fact("category", value_text=r["category"]),
              F.Fact("context", value_text=r["context"]),
              F.Fact("basis", value_text=r["basis"]),
              F.Fact("source_shape", value_text=r["source"])]
        if r["deposit"]:
            fs.append(F.Fact("deposit", value_text=r["deposit"]))
        if r["tonnes"] is not None:
            fs.append(F.Fact("tonnes", value_num=float(r["tonnes"]), unit="t"))
        for i, gr in enumerate(r["grades"]):
            fs.append(F.Fact("grade", value_num=float(gr["value"]), unit=gr["unit"],
                             metal=gr["metal"], seq=i))
        for i, cm in enumerate(r["contained"]):
            fs.append(F.Fact("contained", value_num=float(cm["value"]), unit=cm["unit"],
                             metal=cm["metal"], seq=i))
        if r["cut_off"]:
            fs.append(F.Fact("cut_off", value_text=str(r["cut_off"])))
        if a["mre_type"]:
            fs.append(F.Fact("mre_type", value_text=a["mre_type"]))
        if a["project"]:
            fs.append(F.Fact("project", value_text=a["project"]))
        out.append(F.Record(KIND, facts=fs,
                            confidence=1.0 if r["confidence"] == "high" else 0.5))
    return out


def parse_records(rows_by_ordinal):
    """{ordinal: [Fact]} -> the analyse()-shaped dict."""
    rows, is_re, project, mtype = [], False, None, None
    for ordinal in sorted(rows_by_ordinal):
        r = {"deposit": None, "category": None, "tonnes": None, "grades": [], "contained": [],
             "cut_off": None, "basis": "resource", "context": "announced", "source": None}
        for f in rows_by_ordinal[ordinal]:
            if f.field == "is_resource_estimate":
                is_re = is_re or f.value_num == 1.0
            elif f.field == "tonnes":
                r["tonnes"] = f.value_num
            elif f.field == "grade":
                r["grades"].append({"metal": f.metal, "value": f.value_num, "unit": f.unit})
            elif f.field == "contained":
                r["contained"].append({"metal": f.metal, "value": f.value_num, "unit": f.unit})
            elif f.field == "source_shape":
                r["source"] = f.value_text
            elif f.field == "project":
                project = f.value_text
            elif f.field == "mre_type":
                mtype = f.value_text
            elif f.field in r:
                r[f.field] = f.value_text
        if r["category"]:
            rows.append(r)
    return {"is_resource_estimate": is_re and bool(rows), "rows": rows, "project": project,
            "mre_type": mtype}


def to_prediction(records):
    if not records:
        return None
    return prediction_from(parse_records({i: rec.facts for i, rec in enumerate(records)}))


def prediction_from(a):
    if not a.get("is_resource_estimate") or not a.get("rows"):
        return None
    return {"mre_type": a.get("mre_type"),
            "rows": [{"deposit": r["deposit"], "category": r["category"], "tonnes": r["tonnes"],
                      "grades": r["grades"], "contained": r["contained"], "cut_off": r["cut_off"],
                      "basis": r["basis"], "context": r["context"]} for r in a["rows"]]}


def _code_sha():
    # 1.0.21: this file whole, plus exactly the helper code this reader runs (portal/fingerprint.py): a helper
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
            print(f"  FAIL {name}: got {got!r}, want {want!r}")
        elif verbose:
            print(f"  ok   {name}")

    def sig(a):
        return [(r["deposit"], r["category"], r["tonnes"]) for r in a["rows"]]

    # a table flattened to one cell per line, with the group headers above the unit row
    mili_body = "\n".join([
        "Inferred Mineral Resource of 6.5 Mt at 1.02% Sb and 1.06 g/t Au for 67 kt of antimony",
        "Table 1 - Trojarova Mineral Resource Estimate - April 6, 2026",
        "Classification", "Tonnage", "Average Grade", "Contained Metal",
        "(Mt)", "Sb (%)", "Au (g/t)", "Sb (kt)", "Au (koz)",
        "Inferred", "6.5", "1.02", "1.06", "67", "222", "Notes:",
        "Mineral Resources are estimated at a break-even cut-off grade of 0.8% SbEq."])
    a = analyse("Military Metals Files Maiden Inferred Mineral Resource Estimate for Trojarova Project",
                mili_body)
    eq("one row, table beats the prose that repeats it", sig(a), [("Trojarova", "Inferred", 6500000.0)])
    eq("cut-off from the notes", a["rows"][0]["cut_off"], "0.8% SbEq")
    eq("maiden", a["mre_type"], "Maiden")
    eq("grades keep their metals", [(g["metal"], g["value"]) for g in a["rows"][0]["grades"]],
       [("Sb", 1.02), ("Au", 1.06)])
    eq("contained is normalised to the base unit",
       [(c["metal"], c["value"], c["unit"]) for c in a["rows"][0]["contained"]],
       [("Sb", 67000.0, "t"), ("Au", 222000.0, "oz")])

    # two deposits under one header: the second heading must not read as a tonnage column
    wrlg = "\n".join([
        "Mineral Resource Statement - Rowan Mine Deposit", "Classification", "Tonnes (t)",
        "Gold Grade (g/t)", "Gold Troy Ounces (oz Au)",
        "Indicated", "754,514", "13.03", "334,825", "Inferred", "360,323", "15.31", "179,013",
        "Mineral Resource Statement - Mt. Jamie Deposit", "Classification", "Tonnes (t)",
        "Gold Grade (g/t)", "Gold Troy Ounces (oz Au)",
        "Indicated", "108,775", "14.13", "49,407", "Inferred", "92,972", "11.97", "35,791"])
    eq("one row per deposit per category", sig(analyse("Gold Co Significantly Increases Rowan MRE", wrlg)),
       [("Rowan Mine Deposit", "Indicated", 754514.0), ("Rowan Mine Deposit", "Inferred", 360323.0),
        ("Mt. Jamie Deposit", "Indicated", 108775.0), ("Mt. Jamie Deposit", "Inferred", 92972.0)])

    # a category line with nothing under it is not a row, and is not a deposit name either
    gga = "\n".join(["Cut-off (Au g/t)", "Category", "K tonnes", "Au (g/t)", "Gold (K oz)",
                     "North Pit Mine OP", "0.08", "Measured",
                     "Indicated", "4,630", "0.30", "44.3", "Inferred", "8,764", "0.26", "72.7"])
    a = analyse("Goldgroup Files Updated Technical Report on San Francisco Gold Project",
                "The Company filed an updated technical report. Current Measured and Indicated "
                "resources are stated below.\n" + gga)
    eq("empty category line", sig(a), [("North Pit Mine OP", "Indicated", 4630000.0),
                                       ("North Pit Mine OP", "Inferred", 8764000.0)])
    eq("K tonnes is a thousand tonnes", a["rows"][0]["tonnes"], 4630000.0)
    eq("block cut-off", a["rows"][0]["cut_off"], "0.08")

    # a whole row on one line, with the deposit inside the category cell
    ogn = "\n".join(["Tonnes", "(k)", "Ag", "(g/t)", "Au", "(g/t)", "Silver", "(Koz)", "Gold", "(Koz)",
                     "Proven  797 85 3.65 2,173 93", "Resources (inclusive of reserve)",
                     "Inferred Ermitano* 2,355 59.2 2.14 4,480 162",
                     "Inferred Navidad 2,267 81 3.42 5,910 249"])
    a = analyse("Orogen Announces Mineral Resource and Reserve Update on Producing Ermitano Royalty", ogn)
    eq("deposit inside the category cell",
       [(r["deposit"], r["category"], r["basis"]) for r in a["rows"]],
       [("Ermitano", "Proven", "reserve"), ("Ermitano", "Inferred", "resource"),
        ("Navidad", "Inferred", "resource")])

    # prose, including a category that trails its figures
    a = analyse("Patriot Files Technical Report on the Shaakichiuwaanaan Mineral Resource Estimate",
                "The Project hosts mineral resources of 108.0 Mt at 1.40% Li2O and 166 ppm Ta2O5, "
                "Indicated, and 33.4 Mt at 1.33% Li2O and 155 ppm Ta2O5, Inferred.")
    eq("trailing category", [(r["category"], r["tonnes"]) for r in a["rows"]],
       [("Indicated", 108000000.0), ("Inferred", 33400000.0)])

    a = analyse("Fathom Announces Maiden Mineral Resource Estimate, Gochager Lake Deposit",
                "Total Indicated Mineral Resources of 858,701 tonnes at 0.41% Ni, 0.12% Cu and "
                "0.03% Co (0.57% NiEq), containing 7.7 million pounds of nickel.")
    eq("metals do not slide along the sentence",
       [(g["metal"], g["value"]) for g in a["rows"][0]["grades"]],
       [("Ni", 0.41), ("Cu", 0.12), ("Co", 0.03), ("NiEq", 0.57)])

    # releases that state no estimate
    eq("a filing with no figures", analyse(
        "Kuya Silver Files NI 43-101 Technical Report for Silver Kings Project",
        "The Company today filed on a voluntary basis a technical report with an effective date of "
        "September 5, 2021.")["rows"], [])
    eq("an intention is not an estimate", analyse(
        "Minaurum Engages SGS to Complete Mineral Resource Update on the Alamos Silver Project",
        "The Company has engaged SGS to update its mineral resource estimate on Alamos.")["rows"], [])
    eq("boilerplate states nothing", analyse(
        "Company Reports Drill Results",
        "An Inferred Mineral Resource has a lower level of confidence relative to a Measured or "
        "Indicated Mineral Resource.")["rows"], [])

    # a drill-results release that restates the existing resource is background, not news
    a = analyse("Outstanding drilling results from high-grade core to drive impending resource update",
                "The Ming Mine currently hosts 50.4 Mt of Measured and Indicated Mineral Resources "
                "at 2.0% for 1,016 kt copper equivalent.")
    eq("background when the release announces nothing",
       [(r["category"], r["context"]) for r in a["rows"]],
       [("Measured & Indicated", "background")])

    # 1.0.19 -- one clause per category, figures on either side of the label
    a = analyse("Imagine Lithium Highlights Initial Mineral Resource",
                "The Property contains NI 43-101 compliant Mineral Resources of 3.1 Mt grading 0.85% "
                "Li2O in the Indicated category and 5.3 Mt grading 0.91% Li2O in the Inferred category.\n"
                "Recovery: 81.5% Li2O, based on SGS metallurgical testing.")
    eq("clause per category", [(r["category"], r["tonnes"], [g["value"] for g in r["grades"]])
                               for r in a["rows"]],
       [("Indicated", 3100000.0, [0.85]), ("Inferred", 5300000.0, [0.91])])
    a = analyse("Noble Plains Files Technical Report on Maiden Resource",
                "The report is on the maiden uranium resource at Duck Creek of 4,290,000 tons in the "
                "Indicated Category grading 0.062 %U3O8 for 5.32 million pounds and 839,000 tons in the "
                "Inferred Category grading 0.09% U3O8 for 1.04 million pounds.")
    eq("tonnage in front, grade behind", [(r["category"], round(r["tonnes"])) for r in a["rows"]],
       [("Indicated", 3891823), ("Inferred", 761128)])
    a = analyse("NVRO Files Technical Report and Maiden Reserve",
                "The reserve is 2,320,000 tonnes at 0.74% Cu (plus 0.09% Co and 0.10% Ni) for 17,200 "
                "tonnes of contained copper (of which 75% is recoverable), classified as a Proven & "
                "Probable Mineral Reserve, with 930,000 tonnes in the Proven Mineral Reserve category "
                "and 1,390,000 tonnes in the Probable Mineral Reserve category.")
    eq("P&P is one category", sorted((r["category"], r["tonnes"]) for r in a["rows"]),
       [("Probable", 1390000.0), ("Proven", 930000.0), ("Proven & Probable", 2320000.0)])
    eq("a share is not a grade, contained copper is copper",
       [([g["value"] for g in r["grades"]], [(c["metal"], c["value"]) for c in r["contained"]])
        for r in a["rows"] if r["category"] == "Proven & Probable"],
       [([0.74, 0.09, 0.1], [("Cu", 17200.0)])])
    a = analyse("Thunder Gold Announces Mineral Resource Estimate for Tower Mountain",
                "Indicated Resource of 34.5 million tonnes averaging 0.46 g/t Au (514,000 oz. Au);")
    eq("bracketed contained ounces", [(c["metal"], c["value"]) for c in a["rows"][0]["contained"]],
       [("Au", 514000.0)])
    eq("thousands of ounces in a header", parse_col("('000 oz gold)")["mult"], 1000.0)
    eq("a list of zones names no one zone", project_and_kind(
        "The drill hole density in the South Zone, West Zone and central part of the Gate Zone"),
       (None, None))

    recs = extract("Military Metals Files Maiden Inferred Mineral Resource Estimate for Trojarova Project",
                   mili_body)
    eq("one record per row", len(recs), 1)
    p = to_prediction(recs)
    eq("prediction shape", (p["rows"][0]["deposit"], p["rows"][0]["category"], p["mre_type"]),
       ("Trojarova", "Inferred", "Maiden"))

    # 1.0.20: the shared helper
    eq("helper names in this page's form", [_pn_page(n) for n in (
        "Lac Dor\u00e9 Vanadium Property", "Tom and Jason Deposits", "Two Gold Producing Mines", "NI43-101 Technical Report",
        "Previously Announced Bralorne Gold Project", "Eagle River Underground Mine", "Decade Aqcuires Property")],
       ["Lac Dor\u00e9 Vanadium", None, None, None, None, "Eagle River", None])
    eq("the text's own spelling", [
        _pn_casefix("CASTELO DE SONHOS", "CASTELO DE SONHOS\nthe Castelo de Sonhos gold project"),
        _pn_casefix("ZEUS LITHIUM", "ZEUS LITHIUM DEPOSIT\nthe Zeus lithium brine"),
        _pn_casefix("PAK LITHIUM", "PAK LITHIUM PROJECT\nthe PAK lithium project"),
        _pn_casefix("Elg", "the ELG Mine Complex"),
        _pn_article("Guitarra", "La Guitarra plant; La Guitarra Complex")],
       ["Castelo de Sonhos", "Zeus Lithium", "PAK Lithium", "ELG", "La Guitarra"])
    eq("a longer name", [_pn_longer("Treaty", "the Treaty Creek project. Treaty Creek hosts"),
                         _pn_longer("Moss", "the Moss Mine; Moss Mine gold")], [True, False])
    eq("cut-off names", [_pn_fragment("Lawrence", "the Silver Bell-St. Lawrence Property"),
                         _pn_longer("Recuperada", "the Nueva Recuperada project. Nueva Recuperada"),
                         _pn_longer("Tower Gold", "the Tower Gold Project; Tower Gold"),
                         _pn_fragment("St. Lawrence Gold", "Silver Bell - St. Lawrence Gold Project")], [True, True, False, True])
    eq("a name that is no project", [_pn_no_name(n, "") for n in (
        "ir Los Ricos North", "wholly-owned Diablillos", "Mpama South as the", "Current", "CV5", "BMC", "Gbongogo")],
       [True, True, True, False, False, False, False])
    eq("rows that already name a deposit", [_pn_proper(d) for d in ("ELG Open Pit", "Open Pit", "Pit Constrained", None)],
       [True, False, False, False])
    eq("deals, companies and bare place words", [_pn_page(n) for n in (
        "Lind Option Exercise", "Erin Ventures Piskanja Boron Property", "Island", "CuEq1",
        "Copper-Zinc-Silver-Gold Marshall Lake Project", "Perseus Progresses Nyanzaga Gold Project")],
       [None, None, None, None, None, None])
    # 1.0.22 -- what is not a row of the release's own estimate, and tables read more fully
    def cats(a):
        return [(r["deposit"], r["category"], r["tonnes"]) for r in a["rows"]]

    a = analyse("Northco Reports Mineral Resource for the Alpha Project", "\n".join([
        "Classification", "Tonnes (t)", "Gold Grade (g/t)", "Gold (oz)",
        "Indicated", "754,514", "13.03", "334,825", "Inferred", "360,323", "15.31", "179,013",
        "Total", "1,114,837", "13.73", "513,838"]))
    eq("a table's Total line is not a row", [r["category"] for r in a["rows"]], ["Indicated", "Inferred"])
    a = analyse("Northco Reports Mineral Resource for the Alpha Project", "\n".join([
        "Table 1. Alpha Project Mineral Resource Estimate", "Tonnes", "(Mt)", "Au", "(g/t)", "Cu", "(%)",
        "Au", "(koz)", "Indicated", "9.28 1.39 0.97 415", "Inferred", "0.86 1.06 0.87 29"]))
    eq("the category on its own line, the cells on the next", cats(a),
       [("Alpha Project", "Indicated", 9280000.0), ("Alpha Project", "Inferred", 860000.0)])
    eq("... with every column", [(g["metal"], g["value"]) for g in a["rows"][0]["grades"]], [("Au", 1.39), ("Cu", 0.97)])
    a = analyse("Northco Reports Mineral Reserves", "\n".join([
        "Property", "Location", "Classification", "Tonnes (Mt)", "Ag (g/t)", "Contained Ag (Moz)",
        "Alpha", "Peru", "Proven", "6.2", "168", "33.5", "Probable", "3.7", "170", "20.1",
        "La Beta", "(92.3%)", "Mexico", "Proven", "4.0", "395", "50.8"]))
    eq("a location column is not a deposit; 'La Beta' is no lanthanum", cats(a),
       [("Alpha", "Proven", 6200000.0), ("Alpha", "Probable", 3700000.0), ("La Beta", "Proven", 4000000.0)])
    eq("thousands and millions in a tonnage header",
       [parse_col("Tonnes (000)")["mult"], parse_col("Classification Tonnes (million)")["mult"],
        parse_col("xMillion Tonnes")["mult"], parse_col("Tons ('000)")["mult"], parse_col("Pounds ('000)")["kind"]],
       [1000.0, 1000000.0, 1000000.0, 907.18474, "contained"])
    a = analyse("Northco Updates Mineral Reserves", "\n".join([
        "Mineral Reserves", "Location Classification Tonnes", "(000)", "Au", "(g/t)", "Au", "(koz)",
        "Stockpile Proven 962 1.32 41", "Antenna Probable 2,489 2.20 176", "Koula Probable 786 5.35 135",
        "Total Proven + Probable 4,237 2.58 352"]))
    eq("the deposit in front of the category, one row per line", cats(a),
       [("Stockpile", "Proven", 962000.0), ("Antenna", "Probable", 2489000.0), ("Koula", "Probable", 786000.0),
        (None, "Proven & Probable", 4237000.0)])
    eq("a one-line header grouped into its columns",
       _label_groups("Reserve Category Tonnes Au Grade Ag Grade Contained Au Contained Ag".split(), 5),
       ["Tonnes", "Au Grade", "Ag Grade", "Contained Au", "Contained Ag"])
    eq("a column label, a unit run, a date or a sentence is no deposit name",
       [_deposit_or_none(d) for d in ("Tonnes eU3O8 Contained metal", "Average Grade Contained Metal3",
                                      "DECEMBER 13, 2021 - UNDERGROUND", "Alpha Gold3,4", "Beta M&I", "Sub-total Proven",
                                      "Ontario. The newly acquired", "2028 Alpha", "Gold", "Mt. Jamie Deposit")],
       [None, None, "UNDERGROUND", "Alpha Gold", "Beta", None, None, None, None, "Mt. Jamie Deposit"])
    eq("another company's deposit is not a row", analyse(
        "Northco Starts Drilling at Alpha", "The Alpha Property is 10 km west of Southco Mining Corp.'s producing "
        "Gamma Mine, which hosts Proven and Probable Mineral Reserves of 702 Mt at 0.24% copper.")["rows"], [])
    eq("nor is an analogue", analyse(
        "Northco Starts Drilling at Alpha", "An analogous target model is Eastco's Delta discovery, which hosts "
        "Indicated mineral resources of 121 Mt for 3.4 million ounces of gold.")["rows"], [])
    a = analyse("Northco Starts Drilling at Alpha", "The property is part of the Epsilon Belt. Notable deposits from "
                "the belt include: Zeta Mine with Proven and Probable Reserves of 230 million tonnes at 0.3 g/t Au; "
                "the Eta deposit with a current Indicated Mineral Resource of 22.2 million tonnes at a gold grade of "
                "1.11 g/t; and the Theta Project with an Inferred Mineral Resource of 347.49 million tonnes grading "
                "0.63 g/t gold (7.00 million ounces).")
    eq("nor the belt's notable deposits, however long the list", a["rows"], [])
    a = analyse("Northco Reports on Westco's Maiden Resource Estimate for the Alpha Deposit",
                "Northco Inc. reports that Westco Minerals Inc. has today announced a pit-constrained inferred "
                "resource of 44.9 million tonnes grading 1.28% nickel at the Alpha deposit.")
    eq("a company the headline reports on is not somebody else", cats(a), [("Alpha", "Inferred", 44900000.0)])
    a = analyse("Northco Publishes Study for the Alpha Gold Project",
                "The project hosts an Indicated Resource of 1,438,500 ounces of gold at an average grade of 9.47 g/t "
                "Au (4,726,000 tonnes) and an Inferred Resource of 515,700 ounces of gold at an average grade of 8.85 "
                "g/t Au (1,813,000 tonnes), as well as an Indicated Resource of 891,600 ounces of silver at an average "
                "grade of 5.86 g/t Ag (4,726,000 tonnes).")
    eq("one tonnage, one category", sorted((r["category"], r["tonnes"]) for r in a["rows"]),
       [("Indicated", 4726000.0), ("Inferred", 1813000.0)])
    eq("a higher-grade subset is not a row", analyse(
        "Northco Quarterly Report", "The high-grade Core Zone, which has a current Mineral Resource of 8.8Mt @ 3.9% "
        "CuEq M&I and 10.9Mt @ 3.8% CuEq Inferred, remains open down-plunge.")["rows"], [])
    eq("Indicated & Measured is M&I", [r["category"] for r in analyse(
        "Northco Annual Results", "Indicated & Measured Mineral Resources at the Alpha mine increased to 111,000 "
        "contained gold ounces (380,000 tonnes at 9.0 g/t Au).")["rows"]], ["Measured & Indicated"])
    eq("a wrapped label is one category", [r["category"] for r in read_tables(_join_wrapped_categories([
        "Category Tonnes Au Grade Ag Grade Contained Au Contained Ag", "(Mt) (g/t) (g/t) (Moz) (Moz)",
        "Proven 7.42 2.66 4.28 0.64 1.02", "Probable 16.97 2.72 4.12 1.48 2.25", "Sub-total Proven and",
        "Probable 24.40 2.70 4.17 2.12 3.27"]))], ["Proven", "Probable", "Proven & Probable"])
    eq("a mill's throughput is not a tonnage", analyse(
        "Northco Focuses on Restart", "More material in the Measured & Indicated Resource categories supports a "
        "mine life at 4,100 tonnes per day mill feed.")["rows"], [])
    eq("a bound is not an estimate", analyse(
        "Northco Completes Exploration", "The district hosts delineated measured and indicated resources in excess of "
        "100 Mt at an average grade of 14% Cg.")["rows"], [])
    a = analyse("Northco Updates on Alpha", "At a cut-off grade of 0.45 g/t, the Indicated Resource is estimated at "
                "10,900,000 metric tonnes at a grade of 0.85 g/t of gold, 0.80 g/t of silver and 0.06% of copper.")
    eq("metric tonnes, and the metal after 'of'", [(r["tonnes"], [(g["metal"], g["value"]) for g in r["grades"]])
                                                   for r in a["rows"]],
       [(10900000.0, [("Au", 0.85), ("Ag", 0.8), ("Cu", 0.06)])])
    a = analyse("Northco Identifies Targets", "The Alpha Shear Zone hosts a gold Mineral Resource of 6. 1 million "
                "tonnes grading 2.25 g/t, totaling 450,000 ounces of Indicated Resources, and 3.4 million tonnes "
                "grading 1.44 g/t, totaling 160,000 ounces in Inferred Resources.")
    eq("a decimal the PDF split", [r["tonnes"] for r in a["rows"]], [6100000.0, 3400000.0])
    # (1.0.23 FIX3: beside a table that states the figures in full; a release's only figures are kept, see below)
    eq("figures with neither a deposit nor a tonnage are no row", [r["source"] for r in analyse(
        "Northco Reports", "Measured and indicated mineral resources are estimated to total approximately 797 "
        "million ounces of silver and 10.6 million ounces of gold.\n\nTable 1: Alpha Mineral Resources\n"
        "Category Tonnes (Mt) Ag (g/t) Ag (Moz)\nIndicated 40.0 120 154.3")["rows"]], ["table"])
    # ---- 1.0.23: whose figures, read sentence by sentence (made-up names)
    def rows_of(h, b):
        return [(r["deposit"], r["category"], r["tonnes"]) for r in analyse(h, b)["rows"]]

    eq("1.0.23 the adjacent project of another company is not a row", rows_of(
        "Northco Expands Alpha Project",
        "The Alpha project is located next to the Zeta gold project of Westco Mines Ltd. The adjacent Zeta project "
        "has approximately 14.5 million tonnes of Proven and Probable Reserves grading 7.32 g/t gold. There is an "
        "additional Indicated Resource of 20.7 million tonnes grading 4.95 g/t gold."), [])
    eq("1.0.23 nor a deposit placed a distance from our ground", rows_of(
        "Northco Signs Letter of Intent to Option Properties",
        "The Mu deposit is a typical nickel resource located 4 km south of the Licenses and reportedly hosting "
        "82.5 million pounds of nickel (4.3 Mt @ 0.875% Ni as an indicated resource)."), [])
    eq("1.0.23 nor one the release places next to its ground", rows_of(
        "Northco Enters Due-Diligence Period on the West Kappa Gold Project",
        "The Project is adjacent to the Kappa Lake claim group, as shown in Figure 1. The Kappa Lake Deposit hosts "
        "Measured and Indicated mineral resources of approximately 3.5 million tonnes grading 2.45 g/t Au. In "
        "addition, the deposit hosts underground Inferred mineral resources of approximately 6.5 million tonnes "
        "grading 2.54 g/t Au."), [])
    eq("1.0.23 nor one another company owns", rows_of(
        "Northco Moves Drill to the Alpha Lithium Project",
        "The Alpha Lithium property is located 25 km north of the town of Sigma. It is hosted within the Omicron "
        "Field which is host to Southco Lithium's deposit with reported proven and probable reserves of 17.06 Mt "
        "grading 0.94% Li2O."), [])
    eq("1.0.23 nor one a link credits to another company", rows_of(
        "Northco Moves Drill to the Alpha Lithium Project",
        "The Alpha Lithium property is near the Rho Lithium Deposit which is estimated to contain measured and "
        "indicated resources of 17.18 Mt grading 1.01% Li2O (https://westcolithium.com/rho-project)."), [])
    eq("1.0.23 the release's own estimate is kept beside a neighbour", rows_of(
        "Northco Commences Drilling at Alpha",
        "Northco Inc. (\"Northco\" or the \"Company\") (TSXV: NCO) owns 100% of the Alpha Project, located adjacent "
        "to Westco's Gamma mine. The Alpha deposit hosts an Indicated Resource of 2.0 million tonnes grading 2.9 "
        "g/t Au."), [("Alpha", "Indicated", 2000000.0)])
    eq("1.0.23 so is an acquisition target's", rows_of(
        "Northco to Acquire the Omega Gold Project",
        "Northco Inc. (\"Northco\" or the \"Company\") (TSXV: NCO) has agreed to acquire the Omega Gold Project from "
        "Westco Resources Inc. The Omega deposit hosts an inferred resource of 5.0 million tonnes at 1.2 g/t gold."),
       [("Omega", "Inferred", 5000000.0)])
    eq("1.0.23 a royalty release keeps the operator's figures", len(rows_of(
        "Northco Royalty Update on the Omega Mine",
        "The Omega mine, owned and operated by Westco Mining Corp., hosts Proven and Probable Reserves of 20.5 "
        "million tonnes at 1.6 g/t gold.")), 1)
    eq("1.0.23 an exploration target is no estimate", rows_of(
        "Northco Announces Decision to Focus on Glass",
        "The exploration target was calculated in the same way the Alpha Inferred Resource Estimate was, to define "
        "an exploration target of between 19.06 million tonnes and 23.30 million tonnes."), [])
    eq("1.0.23 indicated and inferred stated together is a Total", rows_of(
        "Northco Appoints CEO",
        "The Alpha project hosts a graphite resource with a historical estimate of 3.2 million tonnes of indicated "
        "and inferred at an average grade of 17%."), [("Alpha", "Total", 3200000.0)])
    eq("1.0.23 and with no tonnage it is no row", rows_of(
        "Northco Intersects 12 Metres", "The Alpha deposit contains over 47,000 tonnes of nickel and 34,000 tonnes "
        "of copper in indicated and inferred historical resources."), [])
    eq("1.0.23 tons whose ounces reconcile as tonnes are tonnes", [r["tonnes"] for r in analyse(
        "Northco Closes Placement", "Exploration will begin at the Company's Alpha prospect where an indicated and "
        "inferred resource of 69,600 oz Au exists (969,000 tons at 2.25 g/t Au).")["rows"]], [969000.0])
    eq("1.0.23 a subset after its lead-in is no row", rows_of(
        "Northco Reports Year-End Results",
        "The Alpha deposit hosts a resource that consists of: o An indicated resource of 3,206,000 ounces of gold at an average grade of "
        "0.49 g/t Au and totalling 203.8 million tonnes; and o An inferred resource of 325,000 oz of gold at 0.42 "
        "g/t Au and totalling 24.1 Mt. A high-grade subset of the Alpha resource, applying a cut-off of 0.5 g/t Au, "
        "consists of: o Indicated resources of 1,765,000 oz Au at an average grade of 1.01 g/t Au and totalling "
        "54.2 Mt; and o Inferred resources of 143,000 oz Au at an average grade of 0.91 g/t Au and totalling 4.9 Mt."),
       [("Alpha", "Indicated", 203800000.0), ("Alpha", "Inferred", 24100000.0)][::-1])
    eq("1.0.23 nor a zone included within the resource", [r["tonnes"] for r in analyse(
        "Northco Files Claim", "Alpha is a deposit with a Measured and Indicated global Mineral Resource of 70.4 "
        "million tonnes grading 3.4% zinc. Included within the global Mineral Resource is a Measured and Indicated "
        "high grade zinc zone of 13.5 million tonnes grading 11.2% zinc.")["rows"]], [70400000.0])
    a = analyse("Northco Files Quarterly Statements",
                "Northco is a development company with a total of 16.0 million tonnes of lithium carbonate equivalent "
                "(LCE) Measured and Indicated mineral resources1 in Alberta. 1: The mineral resource Technical Report "
                "for the Kappa District Project identified 16.0Mt LCE (measured & indicated).")
    eq("1.0.23 one figure under two names is the named one", [r["deposit"] for r in a["rows"]], ["Kappa District"])
    eq("1.0.23 the tonnage written in front of its category", [(r["category"], r["tonnes"]) for r in analyse(
        "Northco Signs MOUs", "Alpha deposit historical resource: 16 Mt indicated grading 0.66% copper equivalent "
        "(0.38% Cu & 0.22 g/t Au) 34 Mt inferred grading 0.64% copper equivalent (0.36% Cu & 0.22 g/t Au).")["rows"]],
       [("Indicated", 16000000.0), ("Inferred", 34000000.0)])
    a = analyse("Northco Reports First Quarter Results",
                "Mineral Resource and Mineral Reserve estimates for the Omega Project, effective December 31, 2022:\n"
                "\u25e6 270 kt of Proven Mineral Reserves averaging 2.70 g/t Au, 13.6 g/t Ag and 3.14% Zn;\n"
                "\u25e6 5,524 kt of Probable Mineral Reserves averaging 3.09 g/t Au, 10.2 g/t Ag and 2.96% Zn.")
    eq("1.0.23 kt in front of the category, and the list's lead-in names the project", sig(a),
       [("Omega", "Proven", 270000.0), ("Omega", "Probable", 5524000.0)])
    eq("1.0.23 'totals 1,687,000 tonnes'", [r["tonnes"] for r in analyse(
        "Northco Announces Study", "Indicated Mineral Resource totals 1,687,000 tonnes grading 10.8 g/t gold "
        "containing 586,000 oz gold.")["rows"]], [1687000.0])
    a = analyse("Northco Commences Testing", "Northco declared an indicated mineral resource of 1.325 million tonnes "
                "LCE at the Alpha Project. The average grade of the indicated mineral resources was 669 ppm lithium "
                "(over a total tonnage of 372,845,000 tonnes).")
    eq("1.0.23 contained metal and tonnage of one category are one row",
       [(r["tonnes"], [g["metal"] for g in r["grades"]], len(r["contained"])) for r in a["rows"]],
       [(372845000.0, ["Li"], 1)])
    eq("1.0.23 metal words read in full", [(g["metal"], g["value"]) for g in analyse(
        "Northco Update", "The Alpha deposit hosts an inferred resource of 129 million tonnes grading 0.35% copper, "
        "0.015% molybdenum and 0.33 g/t platinum.")["rows"][0]["grades"]],
       [("Cu", 0.35), ("Mo", 0.015), ("Pt", 0.33)])
    eq("1.0.23 'ounces gold equivalent at 0.99 g/t'", _metal_near(None, "396,468 ounces gold equivalent at ", 34),
       ("AuEq", True))
    eq("1.0.23 names that are no deposit", [_deposit_or_none(x) for x in (
        "Kappa Lake Deposit hosts", "Ho2O", "Tonnage Cg In-situ", "Westco Gold's Omega", "Feasibility Study")],
       ["Kappa Lake Deposit", None, None, "Omega", None])
    eq("1.0.23 an owner read as the deposit", _owner_named({"deposit": "Southco Lithium's"}), True)
    eq("1.0.23 intellectual property is no mineral property",
       release_project("Northco Completes Acquisition of Intellectual Property Rights"), None)
    eq("1.0.23 a headline about something else is no announcement", release_announces(
        "Northco Announces Director Resignation", "The Alpha project hosts an Indicated Mineral Resource of 2 Mt."),
       False)
    eq("1.0.23 a royalty release, not a royalty word", (
        _royalty_release("Northco Royalties Inc. Presents Alpha", "Northco Royalties Inc. is a royalty company."),
        _royalty_release("Northco Commences Work at Alpha", "Sediments from four adjacent streams returned gold.")),
       (True, False))
    # ---- 1.0.23 FIX3: rows a table labels only by name, and the full text's other losses (made-up names)
    def figs(h, b):
        return [(r["deposit"], r["category"], r["tonnes"], [(g["metal"], g["value"]) for g in r["grades"]],
                 [(c["metal"], c["value"]) for c in r["contained"]], r["context"]) for r in analyse(h, b)["rows"]]

    def cells(lines):
        return "\n".join(lines)

    eq("FIX3 one column group per category, one row per line", figs(
        "Northco Announces Maiden Resource at Alpha", cells([
            "Table 1: Alpha Mineral Resource Estimate", "Indicated Inferred",
            "Area Tonnes", "(Mt)", "Grade", "(g/t Au)", "Contained", "Gold (oz Au)",
            "Tonnes", "(Mt)", "Grade", "(g/t Au)", "Contained", "Gold (oz Au)",
            "Phase 1 16.1 0.41 212,000 4.1 0.43 56,000", "Phase 2 20.2 0.31 200,000 3.6 0.31 37,000",
            "Total 36.2 0.35 412,000 7.7 0.37 93,000"])),
       [("Phase 1", "Indicated", 16100000.000000002, [("Au", 0.41)], [("Au", 212000.0)], "announced"),
        ("Phase 1", "Inferred", 4099999.9999999995, [("Au", 0.43)], [("Au", 56000.0)], "announced"),
        ("Phase 2", "Indicated", 20200000.0, [("Au", 0.31)], [("Au", 200000.0)], "announced"),
        ("Phase 2", "Inferred", 3600000.0, [("Au", 0.31)], [("Au", 37000.0)], "announced")])
    eq("FIX3 column groups one cell per line, a cut-off column in front, (t*1000)", [x[:3] for x in figs(
        "Northco Files Technical Report for Alpha", cells([
            "2019 Mineral Resource Estimate", "Indicated", "Inferred", "Scenario", "CUT-OFF", "(g/t)",
            "Tonnage", "(t*1000)", "Gold", "(g/t)", "Gold", "Ounces", "Tonnage", "(t*1000)", "Gold", "(g/t)", "Gold",
            "Ounces", "Selective", "1.50", "1,442", "2.53", "117,000", "8,759", "2.58", "728,000"]))],
       [("Selective", "Indicated", 1442000.0), ("Selective", "Inferred", 8759000.0)])
    eq("FIX3 a category heading over rows that carry only a name", [x[:4] for x in figs(
        "Northco Announces Resource for Alpha", cells([
            "Table 1. Summary of the Mineral Resource Estimate for the Alpha Project",
            "Classification Material type Tonnes", "(Mt)", "Silver", "(g/t)", "Gold", "(g/t)", "Silver", "(Moz)",
            "Gold", "(Koz)", "Indicated", "Open Pit 4.83 97 0.13 15.03 20.05", "TOTAL 5.05 101 0.13 16.32 21.70",
            "Inferred", "Open Pit 0.17 73 0.07 0.41 0.43"]))],
       [("Alpha (Open Pit)", "Indicated", 4830000.0, [("Ag", 97.0), ("Au", 0.13)]),
        ("Alpha (Open Pit)", "Inferred", 170000.0, [("Ag", 73.0), ("Au", 0.07)])])
    eq("FIX3 the caption names the category", [x[:3] for x in figs(
        "Northco Files Technical Report for Its Alpha Project", cells([
            "Table 1: Inferred resource statement for the Alpha Project", "Mineral", "Type", "Tonnes", "Grade",
            "Au", "AuEq", "g/t", "g/t", "Oxide", "9,057,000", "0.54", "0.66", "Sulphide", "57,214,000", "0.59", "0.71"]))],
       [("Oxide", "Inferred", 9057000.0), ("Sulphide", "Inferred", 57214000.0)])
    eq("FIX3 one column group per year: the current one", [x[:4] for x in figs(
        "Northco Announces Year-End Reserves", cells([
            "Northco Year-End Gold Mineral Reserves", "2025 2024", "Property",
            "Tonnes (kt) Grade (g/t) Contained", "Gold (koz) Tonnes (kt) Grade (g/t) Contained", "Gold (koz)",
            "Proven and Probable Gold Mineral Reserves", "Alpha Mine 470,332 0.28 4,294 264,512 0.33 2,826",
            "Total 470,332 0.28 4,294 264,512 0.33 2,826"]))],
       [("Alpha Mine", "Proven & Probable", 470332000.0, [("Au", 0.28)])])
    eq("FIX3 a comparison heading's rows and a sensitivity table are not the estimate", [x[:3] for x in figs(
        "Northco Updates Alpha Resource", cells([
            "Table 1: Alpha Resource", "Classification Tonnes", "('000's) Ag g/t Au g/t", "2025 Indicated Estimate",
            "Beta 4,237 240 2.20", "Compared to 2024 Indicated Estimate", "Beta 3,959 232 2.18",
            "Notes:", "Table 2: Sensitivity of the Alpha resource to gold price", "Indicated Inferred",
            "Tonnes (kt) Au (g/t) Tonnes (kt) Au (g/t)", "Base 4,237 2.20 1,015 1.82"]))],
       [("Beta", "Indicated", 4237000.0)])
    eq("FIX3 a combined heading over rows that part totals close", [x[:3] for x in figs(
        "Northco Updates Reserves", cells([
            "Silver-Gold Proven and Probable Mineral Reserves", "Tonnes", "Ag", "g/t", "Au", "g/t Ag oz Au oz",
            "Alpha 74,000 244 0.53 580,000 1,300", "Total Proven 74,000 244 0.53 580,000 1,300",
            "Beta 687,000 283 0.73 6,248,000 16,100", "Total Probable 687,000 283 0.73 6,248,000 16,100"]))
        if x[0] in ("Alpha", "Beta")],
       [("Alpha", "Proven", 74000.0), ("Beta", "Probable", 687000.0)])
    eq("FIX3 a header whose labels wrap: each ends at its unit", [x[:4] for x in figs(
        "Northco Reports Reserves and Resources", cells([
            "Summary of Northco's total mineral reserves and resources", "Tonnes (Mt) Ag (g/t) Contained",
            "Ag (Moz) Au (g/t) Contained", "Au (Moz)", "Inferred Resources 404.0 51 507.7 0.73 5.7"]))],
       [("Northco's total", "Inferred", 404000000.0, [("Ag", 51.0), ("Au", 0.73)])])
    eq("FIX3 a label line over its unit line", [x[:5] for x in figs(
        "Northco Reports Resources", cells([
            "Table 2: Beta Project Mineral Resource Estimate", "Indicated", "Inferred", "Tonnes", "kt", "Grade",
            "g/t Au", "Ounces", "koz Au", "Tonnes", "kt", "Grade", "g/t Au", "Ounces", "koz Au",
            "Gamma", "14,068", "1.39", "629", "7,316", "1.37", "322"]))],
       [("Gamma", "Indicated", 14068000.0, [("Au", 1.39)], [("Au", 629000.0)]),
        ("Gamma", "Inferred", 7316000.0, [("Au", 1.37)], [("Au", 322000.0)])])
    eq("FIX3 rows named by their date: the latest", [x[:3] for x in figs(
        "Northco Expands Alpha Reserves", cells([
            "Table 3: Alpha mineral reserve estimate", "Effective date", "Proven Probable Proven & Probable",
            "Tonnes", "(kt)", "Grade Au", "(g/t)", "Oz Au", "(koz)", "Tonnes", "(kt)", "Grade Au", "(g/t)",
            "Oz Au", "(koz)", "Tonnes", "(kt)", "Grade Au", "(g/t)", "Oz Au", "(koz)",
            "28-Nov-2025 1,708 9.92 545 2,659 11.21 958 4,367 10.70 1,503",
            "31-Jul-2024 1,886 11.25 682 1,989 10.33 660 3,875 10.78 1,343"]))],
       [(None, "Probable", 2659000.0), (None, "Proven", 1708000.0), (None, "Proven & Probable", 4367000.0)])
    eq("FIX3 a table as at the year before restates it", [(x[1], x[2], x[5]) for x in figs(
        "Northco Reports Reserves and Resources as at June 30, 2025", cells([
            "Summary of Northco's total mineral reserves and resources, as at June 30, 2025", "",
            "Tonnes (Mt) Ag (g/t)", "Inferred Resources 404.0 51",
            "Summary of Northco's total mineral reserves and resources, as at June 30, 2024", "",
            "Tonnes (Mt) Ag (g/t)", "Inferred Resources 417.3 47"]))],
       [("Inferred", 404000000.0, "announced"), ("Inferred", 417300000.0, "background")])
    eq("FIX3 units: g/tonne, (1000's), ',000, kozs, TrOz, Ktons, K tons, oz/ton", [
        (c["kind"], c["unit"], c["mult"]) for c in map(parse_col, (
            "Grade (g/tonne Au)", "Tonnes (1000's)", "Tonnes (',000)", "Ag (kozs)", "Ag TrOz (000's)", "Ktons",
            "K tons", "Grade (oz Au/ton)"))],
       [("grade", "g/t", 1.0), ("tonnage", "t", 1000.0), ("tonnage", "t", 1000.0), ("contained", "oz", 1000.0),
        ("contained", "oz", 1000.0), ("tonnage", "t", 1000.0), ("tonnage", "t", 907.18474), ("grade", "oz/t", 1.0)])
    eq("FIX3 graphitic carbon and a starred equivalent", (metal_of("Cg"), metal_of("Au Eq*")),
       (("Cg", False), ("AuEq", True)))
    eq("FIX3 a landmark the issuer's ground is placed by is no owner", [x[:3] for x in figs(
        "Northco Reports Maiden Resource at Alpha",
        "The Alpha project is located 100 km northwest of Westco's Zeta mine (Figure 2).\nFigure 2: Regional map.\n"
        "Table 1: Alpha Mineral Resource\nCategory Tonnes (Mt) Cu (%)\nIndicated 23.3 0.37")],
       [("Alpha", "Indicated", 23300000.0)])
    eq("FIX3 a neighbour named in the paragraphs above the table, not in its own", [x[:3] for x in figs(
        "Northco Files Report for the Alpha Project",
        "We plan to grow the resource, which shows mineralization similar to the neighboring Zeta mine. The drill "
        "program starts in May and will test depth extensions.\n\n" + "Drilling totals 40,472 m in 164 holes and "
        "55 holes in the south sector of the project area.\n" * 9 + "MINERAL RESOURCE ESTIMATE STATEMENT\n"
        "Category Ktons Au g/t\nNorth\nMeasured 35,554.4 0.66")],
       [("North", "Measured", 35554400.0)])
    eq("FIX3 a cue in another section of the release", [x[:3] for x in figs(
        "Northco Files Technical Report for Alpha",
        "The updated resource at the Company's Alpha project was estimated by consultants.\n"
        "Table 1: Alpha Mineral Resource\nCategory Tonnes Au (g/t)\nIndicated 1,357,000 2.55\n"
        "About Northco\nThe Kappa Break cuts the property but is not necessarily indicative of mineralization "
        "hosted on the company's property.")],
       [("Alpha", "Indicated", 1357000.0)])
    eq("FIX3 a release's only figures stated as totals in prose", [(x[1], x[4]) for x in figs(
        "Northco Files NI 43-101 Technical Report",
        "Measured & Indicated Total Resource of 537,300 ounces of gold plus an Inferred Total Resource of "
        "147,300 ounces of gold.")],
       [("Measured & Indicated", [("Au", 537300.0)]), ("Inferred", [("Au", 147300.0)])])
    eq("FIX3 'stand at' and 'including'", [(r["category"], [(c["metal"], c["value"]) for c in r["contained"]])
                                           for r in read_prose(
        "Proven and Probable Reserves stand at 5.56 Moz of gold and 3.38 Moz of silver. The Measured and "
        "Indicated Resources stood at 3.3 Moz of gold, including 0.68 Moz in the Beta zone.")],
       [("Proven & Probable", [("Au", 5560000.0), ("Ag", 3380000.0)]), ("Measured & Indicated", [("Au", 3300000.0)])])
    eq("FIX3 a summary repeats the table: an equivalent's figure, and a rounded one", (
        _restates({"category": "Inferred", "basis": "resource", "deposit": None, "_dep_fb": True, "grades": [],
                   "contained": [{"metal": "ZnEq", "value": 88e6}]},
                  {"category": "Inferred", "basis": "resource", "deposit": "Beta", "grades": [],
                   "contained": [{"metal": "Zn", "value": 87.883e6}]}),
        _restates({"category": "Indicated", "basis": "resource", "deposit": "Alpha", "grades": [],
                   "contained": [{"metal": "Au", "value": 1.0e6}]},
                  {"category": "Indicated", "basis": "resource", "deposit": "Alpha", "grades": [],
                   "contained": [{"metal": "Au", "value": 1.062e6}]})), (True, True))
    eq("FIX3 a name the PDF wrapped above its cells, a block's name on its first row, scenario rows", [x[:3] for x in figs(
        "Northco Reports Resources", cells([
            "Table 1: Alpha Mineral Resources", "Category Type Tonnes", "(Mt)", "Cu Grade", "(%)", "Indicated",
            "High Grade Oxide and", "Transitional (>0.25%", "Cu)", "28 0.35", "Low Grade Sulphide",
            "(0.15-0.25% Cu) 323 0.19", "Notes:", "Table 2: Beta Reserves", "Mine Category Tonnes Grade",
            "(g/tonne Au)", "Beta Proven 212,000 12.2", "Probable 847,000 12.2", "Notes:",
            "Table 3: Gamma Resources", "Indicated Inferred", "Tonnes (t) Grade (g/t Au) Tonnes (t) Grade (g/t Au)",
            "Delta Open Pit 45,146,000 0.78 26,631,000 0.72", "Underground - - 918,000 4.57"]))],
       [("High Grade Oxide and Transitional", "Indicated", 28000000.0),
        ("Low Grade Sulphide", "Indicated", 323000000.0), ("Beta", "Proven", 212000.0), ("Beta", "Probable", 847000.0),
        ("Delta - Open Pit", "Indicated", 45146000.0), ("Delta - Open Pit", "Inferred", 26631000.0),
        ("Delta - Underground", "Inferred", 918000.0)])
    eq("FIX3 metals over their column pairs", [x[3:5] for x in figs(
        "Northco Updates Resources", cells([
            "Indicated Resources", "Deposit Tonnes (000)", "Gold Copper",
            "Grade (g/t) Ounces (millions) Grade (%) Pounds (millions)", "Alpha 1,667,000 0.48 25.9 0.14 5,120"]))],
       [([("Au", 0.48), ("Cu", 0.14)], [("Au", 25900000.0), ("Cu", 5120000000.0)])])
    eq("FIX3 a sentence printed one word per line is no table", figs(
        "Northco Drills Alpha", cells(["The", "Zeta", "deposit", "has", "2.47", "million", "ounces;", "Inferred",
                                       "Smith", "2021)", "(4)"])), [])
    # ---------------------------------------------------------------- 1.0.24 FIX5
    eq("FIX5 a deposit heading between the header and its rows; a heading the PDF wrapped", figs(
        "Northco Updates Mineral Resources at Alpha", cells([
            "Mineral Resources", "Grade Values Metal Content", "Mine Classification Tonnage Au Ag Au Ag",
            "kt g/t g/t k oz k oz", "Alpha Sur 1", "(Open pit)", "Measured 5,192.24 0.91 17.07 151.32 2,849.04",
            "Beta", "Norte 1", "(Open Pit)", "Measured 8.12 18.66 25.98 4.87 6.78", "Notes:", "1. Totals may not add."])),
       [("Alpha Sur (Open pit)", "Measured", 5192240.0, [("Au", 0.91), ("Ag", 17.07)], [("Au", 151320.0), ("Ag", 2849040.0)],
         "announced"),
        ("Beta Norte (Open Pit)", "Measured", 8119.999999999999, [("Au", 18.66), ("Ag", 25.98)], [("Au", 4870.0), ("Ag", 6780.0)],
         "announced")])
    eq("FIX5 a column label is no deposit", [_deposit_or_none(x) for x in (
        "Content", "Deposit and Category", "Mineralization Type", "In-Situ Graphite (kt)", "Main Zone")],
       [None, None, None, None, "Main Zone"])
    eq("FIX5 the commodity after a project's name", [_no_metal_tail(x) for x in (
        "Alpha Gold", "Beta Energy Metals", "Golden Zone", "Gamma Copper-Gold", "Red Gold")],
       ["Alpha", "Beta", "Golden Zone", "Gamma Copper-Gold", "Red Gold"])
    eq("FIX5 a row's own sentence names its deposit, else the sentence before it", [x[:2] for x in figs(
        "Northco Announces Director Appointment", cells([
            "Alpha has Proven and Probable reserves of 1.47 million tonnes grading 3.40% copper and 1.88 g/t gold.", "",
            "Discovered in 2012, the Gamma deposit is located at the southern end of the belt. The horizons remain open at "
            "depth. In 2021, an updated mineral resource estimate was completed with an Indicated Mineral Resource "
            "Estimate of 5.5 Mt grading 1.53% Ni and 0.13% Cu."]))],
       [("Alpha", "Proven & Probable"), ("Gamma", "Indicated")])
    eq("FIX5 the deposit the figures' sentence names outranks the headline's project", [x[:2] for x in figs(
        "Northco Approves Drill Program on Omega Target",
        "Northco Gold holds the Omega Project. Beta hosts Indicated mineral resources of 8.3 million tonnes grading 0.70 "
        "g/t gold containing 188,000 ounces of gold.")], [("Beta", "Indicated")])
    eq("FIX5 a caption naming the owner, then the project", [x[:2] for x in figs(
        "Northco Provides Exploration Updates", cells([
            "The updated Mineral Resource estimate is presented in the table below.", "Table 2:", "",
            "Summary of Mineral Resources - March 15, 2022", "Northco Minerals Corp. - Delta Project", "Category",
            "Tonnage", "(000 t)", "Grade", "(g/t Au)", "Contained Metal", "(000 oz Au)", "Indicated", "12,500", "0.94",
            "376", "Notes:"]))], [("Delta Project", "Indicated")])
    eq("FIX5 the name on a block's first row is the next rows'", [(r["deposit"], r["category"]) for r in read_tables(
        _join_wrapped_categories(clean(cells([
            "Northco Mineral Reserves as at June 30, 2026",
            "Property Location Category Tonnes (Mt) Ag (g/t) Contained Ag (Moz)", "Gold Segment",
            "Alpha Mexico Proven 3.6 325 37.3", "Probable 7.0 252 56.9", "Beta Argentina Proven 0.3 199 1.9",
            "Probable 0.8 181 4.7", "Notes:"])).split("\n")))],
       [("Alpha Mexico", "Proven"), ("Alpha Mexico", "Probable"), ("Beta Argentina", "Proven"),
        ("Beta Argentina", "Probable")])
    eq("FIX5 one tonnage stated once per metal is one row with both grades", [x[2:4] for x in figs(
        "Northco Receives Drill Permit for Alpha",
        "The Mineral Resource Estimate reported an Indicated Resource of 1,438,500 ounces of gold at an average grade "
        "of 9.47 g/t Au (4,726,000 tonnes); and an Inferred Resource of 515,700 ounces of gold at an average grade of "
        "8.85 g/t Au (1,813,000 tonnes), as well as an Indicated Resource of 891,600 ounces of silver at an average grade "
        "of 5.86 g/t Ag (4,726,000 tonnes); and an Inferred Resource of 390,600 ounces of silver at an average grade of "
        "7.33 g/t silver (1,813,000 tonnes).")][:1], [(1813000.0, [("Au", 8.85), ("Ag", 7.33)])])
    eq("FIX5 graphitic carbon; an oxide's subscript set apart", ([x[3] for x in figs(
        "Northco Announces Graphite Resource at Alpha", "\n\n".join([
            "Table 1: Mineral Resources (at 3.5% Cg Cut-Off) - Alpha Project", "Mineral Resource Category", "Tonnes (kt)",
            "Graphitic Carbon (%)", "In-Situ Graphite (kt)", "Indicated*", "120,163", "10.27", "12,345", "Notes:"]))],
        clean("0.34% V 2O5 and 234.6 ppm MoO 3"), metal_of("MoO3")),
       ([[("Cg", 10.27)]], "0.34% V2O5 and 234.6 ppm MoO3", ("MoO3", False)))
    eq("FIX5 a decimal the PDF split after its first digit", [x[1:3] for x in figs(
        "Northco Drills Alpha", "Alpha Main Zone has a current resource estimate: Inferred Resources 0.6 7 million "
        "tonnes @ 5.31g/t for 115,000 ounces.")], [("Inferred", 670000.0)])
    eq("the fingerprint covers the helper", "FP" in _code_sha.__code__.co_names and FP.borrowed_source(PN, "PN", __file__).split("\n")[0] != "uses ", True)

    print(f"resources self-test: {'ok' if not bad else str(bad) + ' failures'}")
    return bad


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(1 if self_test() else 0)
