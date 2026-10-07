"""Shared project-name helper (PROJ_NAMES_V1, 2026-09-23).

One place that answers "which mineral project is this release about?" for every reader. Before this, eight readers
named projects eight ways (Economic Studies borrowed Resources' release_project, Permits borrowed Technical's
helpers, the others had their own), and the project field was the most common error on four pages.

    from portal import project_names as PN
    PN.primary(headline, body)          -> "Hemlo Property" | None   the release's main project
    PN.find(text)                       -> [(pos, "Hemlo Property"), ...]   every named project, in order
    PN.projects(headline, body)         -> ["Hemlo Property", "Côté Mine"]  distinct, main one first
    PN.clean(raw)                       -> a candidate name trimmed of lead-ins, verbs and descriptions, or None
    PN.bare(name)                       -> the name without a trailing "Project", for a column headed Project
    PN.key(name) / PN.same(a, b)        -> comparison that ignores "Project", metal words and accents

A reader that uses this module gets its code hashed into its fingerprint automatically (portal.facts fingerprints
follow borrowed code; see PN_FINGERPRINT below), and the accuracy gate warns when a reader that outputs a project
field does not use it.

Quality is measured on the SHARED TEST SET: every project, property, asset or deposit label in every answer key
(accuracy/sets/*.json). A new reader's key joins the test set when its spec names its project label path
(TagSpec attribute `project_labels`, or LABEL_PATHS below), so the helper is re-measured on every reader it serves.

1.0.1 (2026-09-23), from the Economic Studies full-corpus comparison: lower-case suffixes after "the" ("the Panuco
silver-gold project"); runs of capitals inside a text read as title case; money, phone numbers, element symbols,
lower-case metal descriptions, "Resumption of", regions after a comma and region-only names come off; "Project
Finance/Loan/Team/Management" is not a project; a mill ranks last; one count per project however the body spells it,
and a combined "A and B Projects" counts half for each; the portfolio rule (no single project) needs three
project-level names each mentioned twice or more. Shared test set, primary project: hit 222 -> 236, wrong 23 -> 21,
none 26 -> 14 (of 271). Economic Studies key set, project: P 94.4% -> 94.5%, R 92.7% -> 94.5%; blind set unchanged.

1.0.2 (2026-09-23), from the Options full-corpus comparison (1.0.0 vs 1.0.1 on 4,194 releases, 21 names worse):
"Sur" is a Spanish place word, not the French headline word ("Filo Sur"); "Which / Holds / Advancing" end a name
("Magpie Mines Which Holds Large Vanadium Deposits", "Substantial Compliance Advancing Exploration"); "Mine Workings",
"Mine Tailings" are not mines; a dash between a name and a headline verb is not a line break ("Hi-View News Release-
Acquires Additional Claims"); "New Zealand" is a place.

1.0.3 (2026-09-24), from the Economic Studies 1.0.6 full-corpus check (about a dozen real names left blank on
multi-project releases): a portfolio (no single project) now needs three projects discussed about equally -- the third
within a third of the most-discussed, and named at least twice -- so "Segilola Mine" 16 / "Douta" 12 / "Guitry" 1 is
about Segilola; when the first 4,000 characters name no project (a long wire header), the whole body counts; a name
that repeats a word is a list of assets, not a name ("ELG Underground Media Luna Underground Morelos Complex"); a
commodity phrase is not a name ("Platinum Group Metal Project").

1.0.4 (2026-09-25), from Technical Reports 1.0.1's full-corpus comparison: a dotted name is a name ("K.Hill";
initials such as "B.C." or "U.S." still end a lead-in); "Road" is not a lead word ("Gold Road Mine"), "Accessible"
ends one ("Road Accessible Gold Project"); "(1)" keeps its bracket ("TitanBeach One (1) Project"); headline words
Restart, Infill, Successful, Near-Term, Modelled, External and Lode cannot start a name; a lone Lake, River, Creek,
Hill, Mountain, Valley, Bay, Canyon, Ridge or Road (or Ball, Rod, Stamp before "Mill") is not a name, but "Mineral
Ridge", "Table Mountain" and "Voisey's Bay" are; initials without their last dot ("U.S", "B.C", "B.Sc") still end a
lead-in; a plural with a number word, nations and metals is not a name ("Four Chilean Copper Projects"), while
"Colombian Gold Projects" stays (Options' region names); "Mine Technical Services" is a consultancy. New:
find_with(text, fallback, issuer), the shared adapter -- the helper's names first, the reader's own finder when the
helper names none, never a mill, deposits after projects.
"""
import re
import unicodedata

VERSION = "1.0.5"  # 2026-09-27: several projects per release -- release_projects(), project_at() (see _selftest)

# where each answer key keeps its project-name labels: (container, field). A container of None means a list at the
# top of expect. New readers: add a line here (or give the TagSpec a `project_labels` attribute).
LABEL_PATHS = {
    "drill_results": (None, "projects"),
    "economics": ("rows", "project"),
    "exploration": ("rows", "project"),
    "permits": ("rows", "project"),
    "technical": ("rows", "project"),
    "production": ("rows", "asset"),
    "resources": ("rows", "deposit"),
    "royalties": ("rows", "property"),
}

SUFFIX = r"(?:Projects?|Property|Properties|Mines?|Deposits?|Prospects?|Claims?|Concessions?|Complex|Mill)"
# 1.0.1: what find() accepts after a name: any case ("the Panuco silver-gold project"), and not "Mines", which names
# companies and institutions far more often than projects ("Nevada Gold Mines", "Colorado School of Mines")
_SUFFIX_FIND = r"(?i:projects?|property|properties|mine|deposits?|prospects?|claims?|concessions?|complex|mill)"
_SUFFIX_RX = re.compile(r"\s+" + SUFFIX + r"$")
_UP = r"A-ZÀ-Ý"
_W = r"[\w'’À-ÿ\-/.]"
_METAL_LC = (r"(?:gold|silver|copper|uranium|lithium|nickel|zinc|lead|antimony|tungsten|cobalt|graphite|potash|vanadium|"
             r"manganese|molybdenum|tin|iron|pgm|pge|ree|polymetallic|porphyry|oxide|base|precious|metals?|rare|earths?)")
# a word inside a name: capitalised, a joining word, or (1.0.1) a metal word the release writes in lower case
_CAPW = (r"(?:[" + _UP + r"0-9]" + _W + r"*|\(\d\)|de|del|la|las|los|di|du|des|do|da|y|and|&|of|"
         + _METAL_LC + r"(?:-" + _METAL_LC + r")*)")
_METAL = (r"(?:Gold|Silver|Copper|Uranium|Lithium|Nickel|Zinc|Lead|Antimony|Tungsten|Cobalt|Graphite|Potash|Vanadium|"
          r"Titanium|Chromium|Chrome|Platinum|Palladium|Niobium|Tantalum|Scandium|Magnesium|"     # 1.0.2
          r"Manganese|Molybdenum|Tin|Iron|Rare\s+Earths?|REE|PGE|PGM|Critical\s+Minerals?|Polymetallic|Base\s+Metals?|"
          r"Precious\s+Metals?|Gold-Silver|Silver-Gold|Gold-Copper|Copper-Gold|Cu-Au|Au-Ag|Ni-Cu(?:-PGE)?|VMS|Porphyry|"
          r"Oxide|Heap\s+Leach|Au|Ag|Cu)")
_FIND_RX = re.compile(r"((?:[" + _UP + r"0-9]" + _W + r"*)(?:\s+" + _CAPW + r"){0,6}?)\s+" + _SUFFIX_FIND + r"\b")

# words that cannot start or be a name: verbs and nouns of headlines, determiners, descriptions
_LEAD = set("""The This That These Those Its Our Their His Her A An All Each Both Other Any Such Several Multiple
Company Company's Company’s Corporation Issuer About Re Further Additional New Newly First Maiden Initial Final
Flagship Core Main Principal Primary Wholly Owned Wholly-Owned 100% 100%-Owned Past Past-Producing Producing Former
Historic Historical Advanced Advanced-Stage Early Early-Stage Late Large Larger High High-Grade Highest Low Robust
Stronger Bigger Better Improved Enhanced Expanded Optimized Optimised Simplified Smaller Lower Higher
Adjusted Base-Case Overall Entire Whole Combined Standalone Stand-Alone
Significant Strategic Critical Major Priority District District-Scale Scale World World-Class Tier Tier-One Premier
Emerging Underexplored Accessible Adjacent Neighbouring Nearby Operating Current Recent Ongoing Planned Proposed
Updated Amended Revised Positive Preliminary Economic Assessment Feasibility Pre-Feasibility Prefeasibility Study
Technical Report NI Mineral Resource Resources Reserve Reserves Estimate MRE PEA PFS DFS FS Update Results Drill
Drilling Program Programs Exploration Phase Winter Summer Spring Fall Autumn Q1 Q2 Q3 Q4 Mining Mines Mine Ministry
Department Government Acquire Acquires Acquired Acquisition Option Options Optioned Sell Sells Sale Signs Signed
Closes Closed Closing Announces Announce Announced Reports Reported Provides Provide Receives Received Files Filed
Filing Commences Commenced Begins Began Starts Started Launches Initiates Completes Completed Completion Advances
Advancing Delivers Outlines Defines Intersects Drills Expands Expanded Extends Increases Highlights Confirms Unveils
Publishes Releases Improves Updates Enters Engages Welcomes Adds Secures Obtains Grants Granted Approves Approved
Submits Submitted Applies Mobilizes Prepares Plans Continues Resumes Discovers Returns Identifies Achieves Reaches
Pours Produces Ships Restarts Suspends Halts Joins Appoints Agreement Agrees Terms Letter Intent Definitive
Binding Non-Binding Financing Private Placement Offering Life Plan Page On For At In Of To From With And Near Along
Toward Towards Across Into Onto Over Under Within Than
Full Growth Increased Increasing Expanding Targeting Building Developing Growing One Small Grade SAG VP CEO CFO COO
Chief Officer Director Board Exploitation Strategic Stake Its Recently
Acquired Newly-Acquired Independent Explore Explores Exploring Advance Develop Developing Test Tests Testing Relinquished
Retained Remaining Existing Adjoining Contiguous Surrounding Underlying Subject Said Above Following Underground Surface
Open Open-Pit Pit Undeveloped Economically Robust Highly Fully Viable Attractive Compelling Profitable Leading
Largest First-Ever Upcoming Material Style Regarding Top Top-Tier Typical Orogenic Combined Confirming Portfolio Celebrates Determines Proven Permitted Fully-Permitted
Restart Infill Successful Near-Term Modelled Modeled External Lode""".split())
_ELEM = {"Au", "Ag", "Cu", "Ni", "Pt", "Pd", "Zn", "Pb", "Co", "Mo", "Li", "U", "W", "Sb", "Sn", "Fe", "V", "PGE",
         "PGM", "REE", "Nd", "Pr", "Dy", "Tb", "Te", "Bi", "Mn", "Ga", "Ge", "In"}
_NATION = {"US", "U.S.", "U.S", "Canadian", "American", "Mexican", "Peruvian", "Chilean", "Argentine", "Argentinian", "Brazilian",
           "Colombian", "Ecuadorian", "Australian", "African", "European", "Nordic", "Swedish", "Finnish", "Norwegian",
           "Spanish", "Portuguese", "Irish", "Scottish", "Quebec", "Ontario", "Nevada", "Yukon", "Idaho", "Arizona"}
_NUMWORD = {"Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Several", "Both"}
_NOT_ALONE = {"Brazilian", "Australian", "Peruvian", "Chilean", "Argentine", "Argentinian", "Colombian", "Ecuadorian",
              "African", "European", "Nordic", "Two", "Three", "Four", "Five", "Key", "Canadian", "American", "Mexican", "EA", "Ha", "Secure", "One", "Mill", "Grade", "Open", "Pit",
              "Lake", "River", "Creek", "Hill", "Mountain", "Valley", "Bay", "Canyon", "Ridge", "Road",   # 1.0.4
              "Ball", "Rod", "Stamp"}
_GEO = {"Lake", "River", "Creek", "Hill", "Mountain", "Valley", "Bay", "Canyon", "Ridge", "Road"}
# 1.0.4: a word that ends a lead-in elsewhere but starts these place names: "Mineral Ridge", "Table Mountain"
_GEO_FIRST = {"Mineral", "Table", "Voisey's", "Voisey’s", "Hudson's", "Hudson’s"}
_INNER_STOP = set("""Technical Report Files Filed Filing Announces Announce Reports Provides Receives Completes Begins
Launches Initiates Starts Advances Delivers Outlines Defines Intersects Drills Expands Increases Highlights Confirms
Unveils Publishes Releases Extends Improves Updates Enters Signs Secures Obtains Commences Acquires Closes Options
Estimate Assessment Study Update Updated Mineral Resource Resources PEA PFS MRE DFS Preliminary Economic Feasibility
Pre-Feasibility Positive Results Drilling Program Exploration for on the at in to from with The At In Of On For To
From With Including Granted Grants Initiates Initiate Mobilizes Achieves Reaches Discovers Identifies Resumes
Continues Approves Approved Received Submits Applies Pours Produces Restarts Suspends Halts Joins Appoints Agrees Sells Practices Practice Maximizes Maximize Extraction Reclamation
Signed Acquired Awards Award Stakes Staked Backs Supports Applauds Congratulates Celebrates Determines Confirming
About Strategy Overview Summary Transfer These Those Our Their Its Regarding Clarifies Information President
Vice Manager Officer Chair Chairman Annonce Annoncent Des Pour Relancer Avec Dans Which Holds Hold Holding Advancing Accelerates Accelerate Prepares Prepare Plans Receives Welcomes Figure Table Map Photo Appendix Corp
Corp. Inc Inc. Ltd Ltd. Limited Corporation LLC Plc Accessible""".split())
_METAL_CHAIN = re.compile(r"^(?:[A-Z][a-z]?|PGE|REE)(?:[-/](?:[A-Z][a-z]?|PGE|REE))+$")   # Cu-Zn-Au-Ag, Ni-Cu-PGE
_DESCRIPTIVE = {"large", "scale", "high", "grade", "world", "class", "tier", "one", "district", "open", "pit", "near",
                "surface", "past", "producing", "drill", "ready", "shovel", "wholly", "owned", "advanced", "stage", "early", "late", "bulk", "tonnage",
                "low", "cost", "long", "life", "multi", "million", "ounce", "oz"}
_JOIN = {"and", "of", "&", "-", "–", "de", "del", "la", "las", "los", "di", "du", "des", "do", "da", "y", "the"}
_JOIN_LEAD = _JOIN - {"la", "las", "los"}                  # "La Colorada", "Los Azules" start with an article
_GENERIC = set("""gold silver copper lithium uranium nickel zinc lead potash phosphate molybdenum graphite tungsten antimony
cobalt vanadium manganese tin iron critical minerals mineral metals metal polymetallic sulphide pge pgm ree rare earth earths
oxide heap leach base precious porphyry vms project projects property properties mine mines deposit deposits prospect
prospects claim claims concession concessions complex the and of au ag cu flake""".split())
_COMPANY_AFTER = re.compile(r"\s*(?:,\s*)?(?:Corp|Corporation|Inc|Ltd|Limited|LLC|Company|Co|Plc|PLC|S\.A|SA|AG|NL|"
                            r"Resources|Royalt)\b")
_COMPANY_WORD = re.compile(r"(?i)^(?:mining|resources|metals|minerals|royalties|royalty|exploration|explorers|ventures|"
                           r"capital|energy|holdings|group|corp|inc|ltd)$")
_CONTEXT_NOT_OURS = re.compile(r"(?i)\b(?:adjacent\s+to|near|next\s+to|neighbou?ring|along\s+strike\s+from|"
                               r"(?:south|north|east|west)(?:east|west)?\s+of|owned\s+by|operated\s+by|"
                               r"similar\s+to|analogous\s+to|like)\s+(?:the\s+|its\s+)?(?:[\w\-’']+\s+){0,2}$")
_ACRO = {"IP", "EM", "RC", "JV", "NI", "PGE", "REE", "VMS", "TSX", "CSE", "BC", "MT", "USA", "US", "NWT", "II", "III",
         "IV", "PGM", "DSO", "CGP", "RSM"}


def _tc(w):
    """A word as a title-case headline writes it, for the word lists: "INITIATES" -> "Initiates"."""
    return w if not w.isupper() or w in _ACRO or len(w) < 2 else w[:1] + w[1:].lower()


# 1.0.1: after a project's suffix, these words make it something else: "US$220M Project Loan", "Project Management"
_AFTER_SUFFIX = {"financing", "finance", "financed", "loan", "loans", "debt", "team", "teams", "manager", "managers",
                 "director", "directors", "management", "mandate", "engineer", "engineers", "lead", "leader",
                 "coordinator", "controls", "services", "developer", "developers", "generator", "generators", "design",
                 "designs", "contract", "contracts", "contractor", "contractors", "engineering", "operator", "operators",
                 "workings", "tailings", "waste", "dump", "dumps"}     # 1.0.2: "Historical Mine Workings"
_MILLISH = re.compile(r"(?i)\b(?:Mill|Processing|Concentrator|Plant|Refinery|Smelter)\b")
_MONEY = re.compile(r"^(?:(?:US|C|CA|CAD|USD|A|AU|AUD)?\$|US\$?|USD|CAD)?\d[\d.,]*(?:M|MM|B|BN|Bn|K|m|bn|k|million|billion)?$|^(?:US|C|A)?\$")
# 1.0.1: "the Yerington, Nevada Copper Project" is the Yerington Copper Project in Nevada
_REGION = re.compile(r"^(?:Nevada|Arizona|Idaho|Utah|Montana|Alaska|Wyoming|Colorado|California|Oregon|Washington|"
                     r"New\s+Mexico|South\s+Dakota|North\s+Dakota|Texas|Arkansas|Minnesota|Michigan|Wisconsin|Maine|"
                     r"Virginia|Georgia|Tennessee|Missouri|Ontario|Qu[eé]bec|Per[uú]|British\s+Columbia|B\.?C\.?|Yukon|Nunavut|"
                     r"Saskatchewan|Manitoba|Alberta|Newfoundland(?:\s+and\s+Labrador)?|Labrador|Nova\s+Scotia|"
                     r"New\s+Brunswick|NWT|Northwest\s+Territories|Canada|USA|U\.S\.A?\.?|Mexico|M[eé]xico|Chile|Argentina|"
                     r"Brazil|Colombia|Ecuador|Bolivia|Guyana|Suriname|Ghana|Mali|Namibia|Australia|Finland|Sweden|Norway|"
                     r"Spain|Portugal|Serbia|Greenland|Tanzania|Kenya|Senegal|Guinea|Burkina\s+Faso|Philippines|"
                     r"Indonesia|Mongolia|Kazakhstan|Turkey|T[uü]rkiye|Ireland|Scotland|Wales|Botswana|Zambia|"
                     r"Western\s+Australia|Queensland|New\s+South\s+Wales|Sonora|Chihuahua|Durango|Sinaloa|Zacatecas|"
                     r"Jalisco|Oaxaca|Guerrero|Salta|Jujuy|Catamarca|San\s+Juan|Santa\s+Cruz|New\s+Zealand|Zealand)$")


def _region_cut(ws):
    """"Yerington, Nevada Copper" -> "Yerington Copper": a place after a comma is where the project is, not its name."""
    for i, w in enumerate(ws[:-1]):
        if not w.endswith(","):
            continue
        rest = ws[i + 1:]
        for j in range(len(rest), 0, -1):
            if _REGION.match(" ".join(rest[:j]).rstrip(",")) and \
                    all(re.fullmatch(_METAL, x) or x.lower() in _JOIN for x in rest[j:]):
                return ws[:i] + [w.rstrip(",")] + rest[j:]
    return ws


def fold(s):
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    return "".join(c for c in s if not unicodedata.combining(c))


def key(name):
    """The name's identity: accents, case, punctuation and generic words (Project, Gold, Mine...) dropped."""
    ws = [w for w in re.findall(r"[a-z0-9]+", fold(name)) if w not in _GENERIC]
    return " ".join(ws)


def same(a, b):
    """Two names for one project: equal keys, or one key's words inside the other's ("Hemlo" / "Hemlo Gold Mine")."""
    ka, kb = set(key(a).split()), set(key(b).split())
    if not ka or not kb:
        return False
    return ka <= kb or kb <= ka


def _tcword(w):
    if w.strip() in _ACRO or re.match(r"^\s*[A-Z]{1,3}\d", w):
        return w
    x = re.sub(r"(?:^|(?<=[\s\-(“\"‘/]))[a-zà-ÿ]", lambda m: m.group(0).upper(), w.lower())
    return re.sub(r"(?<=[’'])[a-zà-ÿ](?=[a-zà-ÿ]{2})", lambda m: m.group(0).upper(), x)     # "VAL-D’OR" -> "Val-D’Or"


def _caps(w):
    letters = [c for c in w if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


_PART_WORDS = {"north", "south", "east", "west", "central", "upper", "lower", "extension", "deep", "ne", "nw", "se", "sw",
               "main", "zone", "new", "west-central", "far", "ii", "iii", "2", "3", "river", "lake", "lakes", "creek",
               "hill", "hills", "mountain", "mountains", "bay", "valley", "ridge", "point", "island", "peak", "canyon",
               "falls", "brook", "gulch", "pass", "range", "basin", "mine", "mines"}


def _one_count(a, b):
    """For counting mentions: two names of one project, stricter than same(). "PCH Project" and "PCH Ionic Adsorption
    Clay Project", or "Bazooka Property" inside "Bazooka and Arrowhead Properties"; not "Skoonka" and "Skoonka North"."""
    ka, kb = key(a).split(), key(b).split()
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    (s, sn), (l, ln) = sorted(((ka, a), (kb, b)), key=lambda x: len(x[0]))
    if re.search(r"(?i)\s(?:and|&)\s", ln):
        return set(s) <= set(l)
    return l[:len(s)] == s and not (set(l[len(s):]) & _PART_WORDS)


def _titlecase_caps(s):
    """A headline in capitals reads as title case, so its verbs come off like any other headline's. 1.0.1: so does a
    run of three or more words in capitals inside a longer text ("EMERITA GRANTED TWO ADDITIONAL PROPERTIES ...")."""
    letters = [c for c in s if c.isalpha()]
    if len(letters) > 3 and sum(c.isupper() for c in letters) / len(letters) > 0.9:
        return " ".join(_tcword(w) for w in s.split(" "))
    if not re.search(r"[A-Z]{2,}\S*\s+[A-Z]{2,}\S*\s+[A-Z]{2,}", s):
        return s
    parts = re.split(r"(\s+)", s)                      # words at even positions, the whitespace between at odd
    ws = parts[0::2]
    out, i = [], 0
    while i < len(ws):
        j = i
        while j < len(ws) and (_caps(ws[j]) or ws[j] in ("&", "-", "–")):
            j += 1
        if j - i >= 3:
            out.extend(_tcword(w) for w in ws[i:j])
            i = j
        else:
            out.append(ws[i])
            i += 1
    parts[0::2] = out
    return "".join(parts)


def clean(raw, suffix=None):
    """Trim a captured candidate to its name. Returns "<name> <suffix>" (suffix as written) or None."""
    if not raw:
        return None
    s = re.sub(r"\s+", " ", raw).strip(" ,.;:-–—\"“”()")
    if re.search(r"\(\d{1,2}$", s):
        s += ")"                                          # 1.0.4: "TitanBeach One (1)" keeps its bracket
    s = re.sub(r"(\w)-\s+(?=([" + _UP + r"][\w'’]*))",           # 1.0.1: "Lawyers- Ranch" (a line break) -> "Lawyers-Ranch";
               lambda m: m.group(0) if (m.group(2) in _INNER_STOP or _tc(m.group(2)) in _INNER_STOP or m.group(2) in _LEAD)
               else m.group(1) + "-", s)                   # 1.0.2: not before a headline verb ("Release- Acquires")
    if re.search(r"\s[–—]\s|\s-\s", s):                   # "Files Report – Volney" : take the part after the dash
        s = re.split(r"\s[–—]\s|\s-\s", s)[-1]
    ws = _region_cut(s.split())
    cut = 0
    for i, w in enumerate(ws):
        bare = w.rstrip(",:;.")
        if re.match(r"^\(?\d{3}\)?[-.]\d{3}[-.]\d{4}$|^\d{3}-\d{3}-\d{4}$", bare) or \
                re.search(r"(?i)^(?:https?:|www\.)|\w\.\w+/|\.(?:com|ca|net|org)\b", bare):
            cut = i + 1                                   # a phone number or a web address
        elif w.lower() == "of" and i > 0 and (ws[i - 1] in _LEAD or _tc(ws[i - 1]) in _LEAD or ws[i - 1] in _INNER_STOP):
            cut = i + 1                                   # "Portfolio of ...", "Results of ..."
        elif _MONEY.match(bare) and re.search(r"\$|[A-Za-z]$", bare) and i < len(ws) - 1:
            cut = i + 1                                   # "US$220M Kelly", "C$5.2M Burnthut"
        elif bare in _INNER_STOP or _tc(bare) in _INNER_STOP or w.endswith((",", ":", ";")) or re.match(r"^(?:19|20)\d\d\.?$", w) or \
                (w.endswith(".") and len(w) >= 3 and not re.match(r"^(?:[A-Z]\.)+$|^(?:Mt|St|Ste|Pt|Ft|No|Co)\.$", w)) or \
                re.search(r"(?i)-(?:rich|bearing|hosted|dominant|type|style)$", bare):
            cut = i + 1
        elif _METAL_CHAIN.match(bare) and i < len(ws) - 1 or re.match(r"^\d+\.$", w) or re.match(r"^[A-Z]\.[A-Z]", w) and not re.match(r"^[A-Z]\.[A-Z][a-z]{2,}", w):   # 1.0.4: "K.Hill" is a name; initials ("B.C.", "U.S", "B.Sc") end a lead-in
            cut = i + 1                                   # "James Bay Cu-Zn-Au-Ag Nottaway", "Figure 1. Bullseye"
        elif w.lower() == "of" and i > 0 and re.search(r"(?:tion|sion|ment|ance|ence|ing|al|ale|ate)$", ws[i - 1].lower()):
            cut = i + 1                                   # 1.0.1: "Resumption of Plomosas", "Approval of Neita"
        elif re.search(r"['’]s?$", w) and i < len(ws) - 1 and not re.match(r"^(?:St|Mt)\b", ws[0]):
            cut = i + 1                                   # "Kinross' Great Bear", "IsoEnergy’s Hurricane"
    full, ws = ws, ws[cut:]
    while ws and (ws[0] in _LEAD or ws[0].lower().endswith("-based") or re.match(r"^(?:TiO2?|U3O8|Li2O|V2O5|Nb2O5|Ta2O5)$", ws[0]) or len(ws) > 1 and ws[0] in _NUMWORD and (ws[1] in _LEAD or _tc(ws[1]) in _LEAD) or _tc(ws[0]) in _LEAD or ws[0].lower() in _JOIN_LEAD or
                  _MONEY.match(ws[0]) and re.search(r"\$|[A-Za-z]$", ws[0]) or
                  all(x in _DESCRIPTIVE for x in re.split(r"[-/]", ws[0].lower()) if x) and "-" in ws[0] or re.match(r"^\d", ws[0]) and not re.match(r"^\d+[A-Za-z]", ws[0])):
        ws = ws[1:]
    while ws and (ws[-1].lower() in _JOIN or ws[-1] in ("JV", "Joint", "Venture")):
        ws = ws[:-1]
    # the name keeps its metal words as the release writes them ("Nevada North Lithium Project"; key() and same()
    # ignore them), but a chain of element symbols is a description, not part of the name: "Diablillos Ag-Au"
    while len(ws) > 1 and (_METAL_CHAIN.match(ws[-1]) or re.fullmatch(_METAL_LC + r"(?:-" + _METAL_LC + r")*", ws[-1]) or
                           ws[-1] in ("and", "&") or "/" in ws[-1] and
                           all(re.fullmatch(_METAL, x, re.I) for x in ws[-1].split("/"))):
        ws = ws[:-1]                                      # 1.0.1: "the Urasar gold-copper project" -> "Urasar"
    while len(ws) > 2 and ws[-1] in _ELEM and ws[-2] in _ELEM:
        while len(ws) > 1 and ws[-1] in _ELEM:
            ws = ws[:-1]                                  # "Blue Lake Cu Ni Pt Pd" -> "Blue Lake"
    while ws and (ws[-1].lower() in _JOIN or ws[-1].endswith("-")):
        ws = ws[:-1]
    if not ws or not ws[0][:1].isupper() and not ws[0][:1].isdigit():
        return None
    if all(re.fullmatch(_METAL, w, re.I) or w in _LEAD or _tc(w) in _LEAD or w.lower() in _JOIN for w in ws):
        return None                                        # "Gold Project", "Flagship Project", "Gold and Silver Project"
    if re.search(r"['’]s?$", ws[-1]):
        return None                                        # "Company's project" names the owner, not the project
    if _COMPANY_WORD.match(ws[-1]):
        return None                                        # "Bunker Hill Mining" is the company
    for part in re.split(r"\s+(?:and|&|or)\s+", " ".join(ws), flags=re.I):   # "Kulyk Lake and Daly Lake" is two names
        caps = [w.lower() for w in part.split() if w[:1].isupper() and w.lower() not in _JOIN]
        if any(caps[i] in caps[i + 2:] for i in range(len(caps))):     # "Cuiú Cuiú", "Iska Iska" repeat side by side
            return None                                    # 1.0.3: "ELG Underground Media Luna Underground Morelos"
    if all(re.fullmatch(_METAL, w, re.I) or w.lower() in ("group", "metal", "metals", "element", "elements", "mineral",
                                                          "minerals", "critical", "battery") or w.lower() in _JOIN
           for w in ws):
        return None                                        # 1.0.3: "Platinum Group Metal Project"
    if any(w in ("Other", "Various", "Several", "Multiple") for w in ws):
        return None                                        # "Lithium and Other Energy Materials Projects"
    if ws and ws[0] in _GEO and 0 < cut < len(full) and full[cut - 1] in _GEO_FIRST and full[cut] == ws[0]:
        ws = [full[cut - 1]] + ws                          # 1.0.4: "Mineral Ridge", "Table Mountain", "Voisey's Bay"
        if cut >= 2 and full[cut - 2] in ("North", "South", "East", "West"):
            ws = [full[cut - 2]] + ws                      # "South Voisey's Bay"
    if len(ws) == 1 and (ws[0] in _NOT_ALONE or ws[0] in _ELEM or _REGION.match(ws[0])):
        return None                                        # "its Key Project", "a Canadian project", "the EA Project"
    groups = [g.strip() for g in re.split(r"\s+(?:and|&|or)\s+|,\s*", " ".join(ws)) if g.strip()]
    if all(_REGION.match(g) or g in _NATION for g in groups) and (len(groups) > 1 or suffix and suffix.lower().endswith("s")):
        return None                                        # "its Nevada projects", "British Columbia and Quebec"
    if suffix and suffix.lower().endswith("s") and \
            all(w in _NATION or w in _NUMWORD or re.fullmatch(_METAL, w, re.I) for w in ws) and \
            any(w in _NUMWORD for w in ws):
        return None                                        # 1.0.4: "Four Chilean Copper Projects"
    name = " ".join(ws)
    if len(name) < 2 or not key(name):
        return None
    return name + (" " + suffix if suffix else "")


def _unquote(t):
    """Quotation marks around a name hide it: 'AT THE ‘COPPER VALLEY’ PROJECT', 'the "Nevada North" project'."""
    t = re.sub(r"[“”\"‘]", " ", t)
    return re.sub(r"’(?=\s+" + SUFFIX + r"\b)", " ", t, flags=re.I)


_HL_STUDY = re.compile(r"(?:['’]s?|\bat|\bon|\bfor|\bof)\s+(?:the\s+|its\s+)?([" + _UP + r"][\w\-’'À-ÿ]+(?:\s+[" + _UP +
                       r"][\w\-’'À-ÿ]+){0,2})\s+(?:Pre-Feasibility|Prefeasibility|Feasibility|PEA|PFS|DFS|"
                       r"Preliminary\s+Economic|Scoping|Mineral\s+Resource|Resource\s+Estimate|MRE|Technical\s+Report|"
                       r"Drill(?:ing)?|Exploration|Permit)\b")


def bare(name):
    """The name without a trailing "Project" ("Nevada North Lithium Project" -> "Nevada North Lithium"), for a page
    whose column is already headed Project. "Mine", "Property" and "Deposit" stay: they say what the thing is."""
    return re.sub(r"(?i)\s+Projects?$", "", name) if name else name


def find(text, issuer=None):
    """Every named project in text, in order: [(position, "Name Suffix")]. Skips company names ("Omai Gold Mines
    Corp."), another company's project ("Kinross' Great Bear" is kept only when Kinross is the issuer) and projects
    named only as neighbours ("adjacent to the Hemlo Mine")."""
    t = _titlecase_caps(_unquote(text or ""))
    out = []
    for m in _FIND_RX.finditer(t):
        mid_word = m.start() > 0 and not re.match(r"[\s(“\"‘'\[/–—]", t[m.start() - 1])
        if m.start() == 0 and re.match(r"\s+(?:Mines|Mining)\b", t[m.end(1):]):
            continue                                       # "Idaho Champion Gold Mines Files ..." opens on the issuer
        suf = re.match(r"\s+(\S+)", t[m.end(1):m.end()]).group(1)
        if suf[:1].islower() and not re.search(r"(?i)(?:\bthe|\bits|\bour|\btheir|\bhis|['’]s?)\s+$",
                                                t[max(0, m.start() - 12):m.start()]):
            continue                                       # "Compelling project": lower case needs "the X project"
        if t[m.end():m.end() + 1] == "-":
            continue                                       # "Property-Wide", "Mine-Scale"
        nxt = re.match(r"[\s-]+([A-Za-z]+)", t[m.end():m.end() + 20])
        if nxt and nxt.group(1).lower() in _AFTER_SUFFIX or re.match(r"\s+Technical\s+Services\b", t[m.end():m.end() + 25]):
            continue                                       # "Project Finance", "Project Management", "Project Loan"
        low = suf.lower()
        suf = suf[:1].upper() + suf[1:].lower()            # "the Panuco silver-gold project" -> "... Project"
        if _COMPANY_AFTER.match(t[m.end():m.end() + 16]) and low in ("mines", "mine", "mining", "property", "properties"):
            continue
        if _CONTEXT_NOT_OURS.search(t[max(0, m.start() - 50):m.start()]):
            continue
        raw = m.group(1)
        if mid_word:                                       # 1.0.1: "PGM+Au+Ni Deposit" does not name "Ni"; the
            raw = " ".join(raw.split()[1:])                # capture began inside "6,215-acre", so its first word goes
            if not raw:
                continue
        before = re.search(r"([" + _UP + r"][\w’'\-]+(?:\s+[" + _UP + r"][\w’'\-]+){0,2}),\s+$", t[max(0, m.start() - 40):m.start()])
        if before:                                         # "its Yerington, Nevada Copper Project": the place is not the name
            ws = raw.split()
            for j in range(min(3, len(ws)), 0, -1):
                if _REGION.match(" ".join(ws[:j])):
                    raw = before.group(1) + " " + " ".join(ws[j:])
                    break
        name = clean(raw, suf)
        if not name:
            continue
        if issuer and low in ("mines",) and set(key(name).split()) <= set(key(issuer).split()):
            continue
        out.append((m.start(), name))
    return out


_SINGULAR = {"projects": "Project", "properties": "Property", "deposits": "Deposit", "mines": "Mine",
             "prospects": "Prospect", "concessions": "Concession", "claims": "Claims"}


def _parts(name):
    """"AurMac and Hyland Projects" -> ["AurMac Project", "Hyland Project"]; any other name -> [name]. A singular suffix
    keeps an "and" inside one name: "Rough and Ready Mine"."""
    m = re.match(r"^(.+?)\s+(?:and|&)\s+(.+?)\s+(\w+)$", name or "")
    if not m or m.group(3).lower() not in _SINGULAR:
        return [name]
    suf = _SINGULAR[m.group(3).lower()]
    out = [clean(x, suf) for x in re.split(r",\s*", m.group(1)) + [m.group(2)]]
    return [x for x in out if x] or [name]


def projects(headline, body, issuer=None, limit=8000):
    """Distinct projects, the main one first, then in order of first mention."""
    main = primary(headline, body, issuer)
    seen, out = [], []
    for _p, n in ([(0, main)] if main else []) + find(headline, issuer) + find((body or "")[:limit], issuer):
        if not any(same(n, s) for s in seen):
            seen.append(n)
            out.append(n)
    return out


def primary(headline, body, issuer=None):
    """The project a release is about.

    1. A project the headline names ("... at its Hemlo Project"), preferring a project over a deposit inside it;
       when the headline names only a deposit or zone and the body names one project at least twice, that project.
    2. A name the headline gives without a suffix ("Closes Financing for Burnthut Drilling") that the body calls a
       project.
    3. The body's most-mentioned project among those named in its first 4,000 characters (earliest on a tie),
       unless the body spreads evenly over three or more projects that it each names more than once (a portfolio
       update names no single project).
    """
    head = headline or ""
    body = body or ""
    hs = find(head, issuer)
    counts, body_keys = {}, set()
    for _p, n0 in find(body, issuer):
        body_keys.add(key(n0))
        ps = _parts(n0)
        for n in ps:                                       # 1.0.1: "AurMac and Hyland Projects": half a mention each
            k = key(n)
            if not k:
                continue
            if k not in counts:                            # 1.0.1: one count per project, whatever it is called
                k = next((k2 for k2, c in counts.items() if _one_count(c[0], n)), k)
            c = counts.setdefault(k, [n, 0, _p, len(ps) > 1])
            c[1] += 1 if len(ps) == 1 else 0.5
            if c[3] and len(ps) == 1:
                c[0], c[3] = n, False                      # the body's own spelling over one made from a combined name
    if hs:
        firsts = ([n for _p, n in hs if not re.search(r"(?i)\bDeposits?$", n) and not _MILLISH.search(n)] or
                  [n for _p, n in hs if not _MILLISH.search(n)] or [hs[0][1]])   # 1.0.1: a mill or plant is last
        n = firsts[0]
        hk = key(n).split()
        same_case = [c for c in counts.values() if c[0].lower() == n.lower()]
        if same_case:                                      # the body's capitals: "PAK Lithium Project"
            n = max(same_case, key=lambda v: v[1])[0]
        for c in sorted(counts.values(), key=lambda v: (-v[1], v[2])):
            ck = key(c[0]).split()
            if key(n) in body_keys:                        # 1.0.1: the body uses the headline's full name
                break
            if ck and len(ck) < len(hk) and hk[-len(ck):] == ck:
                n = c[0]                                   # "Positions Westmoreland": the body says "Westmoreland"
                break
        if re.search(r"(?i)\bDeposits?$", n) and counts:
            projs = [v for v in counts.values() if re.search(r"(?i)\b(?:Projects?|Property|Properties)$", v[0])
                     and key(v[0]) != key(n) and v[2] < 3000]
            if projs:                                      # "Loki Flake Deposit" sits in the Key Lake South Project
                return max(projs, key=lambda v: (v[1], -v[2]))[0]
        if _MILLISH.search(n) and hk:                      # 1.0.1: "Montauban Mill" -> the Montauban Project
            kin = [v for v in counts.values() if not _MILLISH.search(v[0]) and key(v[0]).split()[:1] == hk[:1]]
            if kin:
                return max(kin, key=lambda v: (v[1], -v[2]))[0]
        return n
    m = _HL_STUDY.search(_titlecase_caps(_unquote(head)))
    if m:
        n = clean(m.group(1))
        if n and not re.search(r"(?i)(?:mining|resources|metals|minerals|gold|silver|copper|corp|inc|ltd)$", n):
            for c in counts.values():                      # the body's full name for it, when it gives one
                if same(c[0], n):
                    return c[0]
            return n
    if counts:
        hf = " " + " ".join(re.findall(r"[a-z0-9]+", fold(_titlecase_caps(head)))) + " "
        first_word = hf.split()[0] if hf.split() else ""
        for n, _c, _p, _s in sorted(counts.values(), key=lambda v: (-v[1], v[2])):
            k = key(n)
            if len(k) >= 4 and (" " + k + " ") in hf and k.split()[0] != first_word:
                return n
        top = sorted(counts.values(), key=lambda v: (bool(_MILLISH.search(v[0])), -v[1], v[2]))
        big = [v for v in top if re.search(r"(?i)\b(?:Projects?|Propert(?:y|ies)|Mines?|Claims|Concessions?|Complex)$",
                                           v[0])]                # a deposit or prospect sits inside a project
        # 1.0.3: a portfolio needs three projects discussed about equally (each within a third of the most-discussed,
        # and at least twice); "Segilola Mine" 16 / "Douta Project" 12 / "Guitry" 1 is a release about Segilola
        if len(big) >= 3 and big[2][1] >= 2 and big[2][1] * 1.5 >= big[0][1]:
            return None
        early = {key(n) for _p, n in find(body[:4000], issuer)}
        if not early:                                      # 1.0.3: a long wire header before the text
            early = {key(n) for _p, n in find(body, issuer)}
        for n, c, _p, _s in top:
            if key(n) in early and not _MILLISH.search(n):
                return n
        for n, c, _p, _s in top:                           # 1.0.1: a mill only when nothing else is named early
            if key(n) in early:
                return n
    return None


# ------------------------------------------------------------------ the shared adapter (1.0.4)
_MILL_END = re.compile(r"(?i)\bMills?$")


def find_with(text, fallback=None, issuer=None):
    """The projects a text names, for a reader moving onto the helper: [(position, "Name Suffix")].

    The helper's own names (find()) first; when it names none, the reader's own finder, called as
    fallback(text, issuer) and returning the same shape; never a mill (it processes ore -- a release is not about
    it); a deposit after the projects, which it sits inside. Lifted from Technical Reports 1.0.1 (_pn_in), where
    the fallback kept ~29 real names the helper could not read (Giyani's "K.Hill", "RDM Mines").
    """
    found = find(text or "", issuer)
    if not found and fallback is not None:
        found = list(fallback(text or "", issuer) or [])
    out = [(p, n) for p, n in found if n and not _MILL_END.search(n)]
    out.sort(key=lambda x: (bool(re.search(r"(?i)\bDeposits?$", x[1])), x[0]))
    return out


# ------------------------------------------------------------------ several projects (1.0.5, PN_MULTI_V1, 2026-09-27)
# For readers that write one row per project. Nothing above changes, and a reader's fingerprint only takes these
# functions when it calls them (portal/fingerprint.py follows the code a reader uses), so adding them moves no reader.
#
#   PN.release_projects(headline, body)  -> {"scope": "one"|"several"|"portfolio"|"none", "projects": [...],
#                                            "why": "..."}   the projects the release reports on, main one first
#   PN.subject_text(body)                -> the release's own news: cut at "About <Company>", Qualified Person,
#                                            forward-looking and contact blocks
#   PN.project_at(text, pos, names)      -> which of names the passage at pos is about (same sentence first, then
#                                            the nearest earlier mention in the same paragraph)
#   PN.split_by_project(text, names)     -> {name: text of the sentences about it}

_SUBJECT_END = re.compile(
    r"(?:^|\n|\.\s+|\s{2,})(?:"
    r"About\s+(?!the\s+(?:[A-Z]\w+\s+){0,4}(?:Project|Property|Deposit|Mine|Claims|Prospect|Transaction|Offering|"
    r"Royalty|Stream|Agreement|Program|Study|PEA|Company)\b)(?:[A-Z0-9][\w&.,'’\-]*\s+){0,6}?"
    r"(?:Inc|Corp|Corporation|Ltd|Limited|Plc|LLC|S\.A|Resources|Mining|Mines|Metals|Minerals|Gold|Silver|Copper|"
    r"Uranium|Lithium|Royalt(?:y|ies)|Exploration|Energy|Capital|Ventures|Holdings|Group|Company)\b\.?"
    r"|Qualified\s+Persons?(?:\s+Statement)?\b|QP\s+Statement|Technical\s+Information\b|Technical\s+Disclosure\b"
    r"|(?:Cautionary|Forward[\s-]Looking)\s+(?:Note|Notes|Statements?|Information|Language)\b"
    r"|On\s+(?:B|b)ehalf\s+of\s+the\s+Board\b|For\s+(?:further|more|additional)\s+information\b"
    r"|Neither\s+(?:the\s+)?TSX\b|Neither\s+the\s+Canadian\s+Securities\s+Exchange\b)")
# 1.0.5: a headline or opening that says the release covers a portfolio, not a list of named projects
_PORTFOLIO_HL = re.compile(
    r"(?i)\b(?:portfolio|royalty\s+package|package\s+of\s+(?:\w+\s+){0,2}(?:royalt|stream|propert|project|claim)|"
    r"(?:[3-9]|[1-9]\d{1,2}|three|four|five|six|seven|eight|nine|ten|eleven|twelve|several|multiple)\s+"
    r"(?:[\w\-]+\s+){0,2}(?:royalties|streams|properties|projects|assets|claim\s+blocks|mines))\b")
# "adds Marr Lake to its portfolio", "Increases Portfolio by Acquiring ... Railroad Valley": one project added
_PORTFOLIO_ADD = re.compile(r"(?i)\b(?:to\s+(?:its|the|our)?\s*(?:[\w\-]+\s+){0,3}portfolio|(?:expands?|increases?|grows?|"
                            r"strengthens?|adds?\s+to|builds?)\s+(?:its\s+|the\s+)?(?:[\w\-]+\s+){0,3}portfolio)\b")
_PORTFOLIO_N = re.compile(r"(?i)\b(?:[3-9]|[1-9]\d{1,2}|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+"
                          r"(?:[\w\-]+\s+){0,2}(?:royalties|streams|properties|projects|assets)\b")
# a headline project that belongs to someone else or is only a comparison: "near New Found Gold's Queensway Project",
# "adjacent to Brewer", "analogous to Candelaria"
_HL_NOT_OURS = re.compile(r"(?i)\b(?:near|adjacent\s+to|next\s+to|bordering|surrounding|neighbou?ring|along\s+strike\s+"
                          r"(?:from|of)|analogous\s+to|similar\s+to|like|south|north|east|west)\s+(?:the\s+|its\s+)?"
                          r"(?:[\w\-’'.]+\s+){0,4}$")
_SENT_END = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9“\"(•\-])|\n\s*\n|\n\s*[•\-–]\s*")
_PARA_END = re.compile(r"\n\s*\n|\n(?=\s*[A-Z][A-Za-z’' \-]{2,60}(?:Project|Property|Deposit|Mine|Claims|Prospect)s?\s*\n)")


def subject_text(body, limit=8000):
    """The part of the release that is its news. Cut at the company's own "About <Company>" paragraph, the qualified
    person and technical-information notes, forward-looking statements, "On behalf of the Board", contacts and the
    exchange disclaimer -- where a portfolio's other projects are named without being reported on. The cut is never
    inside the first 200 characters (a dateline can read "About ...")."""
    b = (body or "")[:limit]
    m = _SUBJECT_END.search(b, 200)
    return b[:m.start() + (1 if m and b[m.start():m.start() + 1] == "." else 0)] if m else b


_PROJ_LEVEL = re.compile(r"(?i)\b(?:Projects?|Propert(?:y|ies)|Mines?|Complex|Concessions?|Operations?)$")
_SUB_LEVEL = re.compile(r"(?i)\b(?:Deposits?|Prospects?|Zones?|Claims?|Targets?|Showings?|Pits?|Veins?)$")
# first words that make a headline "name" a description, not a project ("Low Capital Intensity Project", "Extend
# Property Position", "Related Royalties", "Average Annual Gold Production Over 12 Year Mine", "Newest Gold Mine")
_HL_DESCRIPTION = set("""include includes extend extends related average annual capital intensity newest largest
agreement royalty royalties stream production year years target targets indium silica district scale grade cost
""".split())
_LIST_SUFFIX = {"projects": "Project", "properties": "Property", "deposits": "Deposit", "mines": "Mine",
                "prospects": "Prospect", "concessions": "Concession", "claims": "Claims", "royalties": "Royalty",
                "streams": "Stream", "assets": "Asset"}
# "the Saxby Gold Royalty and the Uley Graphite Royalty", "Spring Valley and Moonlight Royalties": a royalty or stream
# names its property; find() takes only project suffixes, so these are read here


def _split_list(name):
    """"Quinn Lake And Grub Line Properties" -> ["Quinn Lake Property", "Grub Line Property"]; "A, B and C Projects"
    likewise, in any case of "and"; a singular suffix keeps its "and" ("Rough and Ready Mine"). Unlike _parts() it
    reads "And" and "&" written in capitals, as a headline in capitals comes out of _titlecase_caps()."""
    m = re.match(r"^(.+?)\s+(?:[Aa]nd|AND|&)\s+(.+?)\s+(\w+)$", name or "")
    if not m or m.group(3).lower() not in _LIST_SUFFIX:
        return [name]
    suf = _LIST_SUFFIX[m.group(3).lower()]
    out = [clean(x, suf) for x in re.split(r",\s*", m.group(1)) + [m.group(2)]]
    return [x for x in out if x] or [name]


def _mentions(text, issuer=None):
    """[(pos, name)] for every project named in text, a combined "A and B Projects" split into its parts at the same
    position."""
    out = []
    for p, n in find(text, issuer):
        for x in _split_list(n):
            out.append((p, x))
    return out


_ROY_LIST = re.compile(r"(?i:\bthe\s+|\bits\s+)((?:[" + _UP + r"0-9]" + _W + r"*)(?:\s+" + _CAPW + r"){0,5}?)\s+"
                       r"(?i:(?:gold|silver|copper|graphite|lithium|nickel|uranium)\s+)?(?i:royalty|stream)\s+"
                       r"(?i:and|&)\s+(?i:the\s+)?((?:[" + _UP + r"0-9]" + _W + r"*)(?:\s+" + _CAPW + r"){0,5}?)\s+"
                       r"(?i:royalty|stream)\b"
                       r"|(?i:\bthe\s+|\bits\s+|\bof\s+|\bsale\s+of\s+)((?:[" + _UP + r"0-9]" + _W + r"*)(?:\s+" + _CAPW +
                       r"){0,4}?)\s+(?i:and|&)\s+((?:[" + _UP + r"0-9]" + _W + r"*)(?:\s+" + _CAPW + r"){0,4}?)\s+"
                       r"(?i:royalties|streams)\b")


def _royalty_names(text):
    """[(pos, "Name")] for two or more properties named as royalties or streams in one phrase: "the Saxby Gold Royalty
    and the Uley Graphite Royalty", "Sale of Spring Valley and Moonlight Royalties". A single "X Royalty" is not read:
    it is far more often a company ("Electric Royalties", "Vox Royalty") or a word ("Restated Royalty")."""
    out = []
    t = _titlecase_caps(_unquote(text or ""))
    for m in _ROY_LIST.finditer(t):
        raws = [x for x in m.groups() if x]
        names = [clean(x) for x in raws]
        names = [n for n in names if n and not _COMPANY_WORD.match(n.split()[-1]) and
                 not re.search(r"(?i)^(?:net|gross|smelter|nsr|gr|production|producing|revenue|metal|precious|"
                               r"existing|additional|new|two|three)\b", n)]
        if len(names) >= 2:
            out.extend((m.start(), n) for n in names)
    return out


def _drop_headline(text, head):
    """The text without a copy of the headline at its start (most stored bodies open with it), so a word the headline
    alone uses is not taken as the news naming it."""
    h = " ".join(re.findall(r"[a-z0-9]+", fold(head)))[:80]
    if len(h) < 12:
        return text
    words = re.finditer(r"\S+", text[:len(head) + 400])
    acc, end = "", 0
    for m in words:
        acc = (acc + " " + " ".join(re.findall(r"[a-z0-9]+", fold(m.group(0))))).strip()
        end = m.end()
        if len(acc) >= len(h):
            break
    i = acc.find(h[:40])
    if i < 0 or i > 200:
        return text
    tail = " ".join(re.findall(r"[a-z0-9]+", fold(head)))[-30:]
    j = fold(text[:len(head) + 400]).rfind(tail.split()[-1]) if tail.split() else -1
    cut = max(end, j + len(tail.split()[-1]) if j >= 0 else 0)
    return text[cut:]


def _group(mentions):
    """Mentions grouped by project: [[name, count, first_pos]], one entry however the text spells it."""
    groups = []
    for p, n in mentions:
        if not key(n):
            continue
        g = next((g for g in groups if key(g[0]) == key(n)), None) or \
            next((g for g in groups if _one_count(g[0], n)), None)
        if g is None:
            groups.append([n, 1, p])
        else:
            g[1] += 1
            if len(n) > len(g[0]) and _one_count(g[0], n) and not re.search(r"(?i)\s(?:and|&)\s", n):
                g[0] = n                                  # the fuller spelling: "Hemlo" -> "Hemlo Gold Project"
    return groups


def _inside(sub, groups):
    """A deposit, zone or claim named inside a project the release also names: "the JAC Deposit on the Diablillos
    Project", "Getty North Deposit" in the Getty Project -- one project, not two. Any shared name word counts."""
    ks = set(key(sub).split()) - _PART_WORDS
    for g in groups:
        if g[0] is sub or not _PROJ_LEVEL.search(g[0]):
            continue
        if ks & (set(key(g[0]).split()) - _PART_WORDS):
            return True
    return False


def _listed_together(text, names, window=600):
    """Project-level names written as one list early in the text: "on its Spring Peak and Lodestar projects", "the
    Alpha Project, the Beta Property and the Gamma Project". Returns the names in that list (two or more), else []."""
    best = []
    for sent in _SENT_END.split(text[:window]):
        if not re.search(r"(?i)\b(?:and|&)\b|,", sent):
            continue
        ms = []
        for _p, x in _mentions(sent):
            if _HL_NOT_OURS.search(sent[max(0, _p - 45):_p]):
                continue                                   # "near New Found Gold's Queensway Project"
            n = next((n for n in names if same(n, x)), None)
            if n and n not in ms:
                ms.append(n)
        if len(ms) >= 2 and len(ms) > len(best):
            best = ms
    return best


def release_projects(headline, body, issuer=None, limit=8000):
    """The projects a release reports on, for a reader that writes one row per project.

    Counts only project-level names (Project, Property, Mine, Complex, Concession) and properties named by a royalty or
    stream; a deposit, zone, prospect or claim counts only when the release names no project, since readers that
    report deposits (Resources, Drill Results) already keep one row per deposit. Only the news counts (subject_text):
    a project named only in the About paragraph is not reported on.

    scope "several": the headline names two or more projects ("Drills Spring Peak and Lodestar Projects", "Saxby and
        Uley Royalties"); or the news lists two or more together in its opening lines and names each at least twice;
        or it discusses two or more, each at least twice and the second at least a third as much as the first.
    scope "portfolio": the headline or opening says portfolio / N (3+) royalties or properties / a package, or five or
        more projects are each discussed; projects lists the named ones (up to 25), e.g. for "Portfolio: A, B, C".
    scope "one": one project (primary()'s answer when it agrees); scope "none": no project named in the news.
    """
    head = headline or ""
    news = _drop_headline(subject_text(body, limit), head)
    th = _titlecase_caps(_unquote(head))
    hs = [(p, n) for p, n in _mentions(head, issuer) + _royalty_names(head)
          if not _MILLISH.search(n) and not _HL_NOT_OURS.search(th[max(0, p - 45):p])]
    hs.sort(key=lambda x: x[0])
    allg = [g for g in _group(_mentions(news, issuer) + _royalty_names(news)) if not _MILLISH.search(g[0])]
    proj = [g for g in allg if not _SUB_LEVEL.search(g[0]) or not _inside(g[0], allg)]
    has_proj = any(_PROJ_LEVEL.search(g[0]) for g in proj)
    if has_proj:
        proj = [g for g in proj if not _SUB_LEVEL.search(g[0])]
    ranked = sorted(proj, key=lambda g: (-g[1], g[2]))
    hnames = []
    for _p, n in hs:
        if any(same(n, x) for x in hnames):
            continue
        if _SUB_LEVEL.search(n) and (has_proj or any(_PROJ_LEVEL.search(x) for _q, x in hs) or _inside(n, allg)):
            continue                                       # "JAC Deposit on Diablillos": the deposit is inside
        g = next((g for g in proj if same(g[0], n) and _one_count(g[0], n)), None)
        listed = any(q == _p for q, _x in hs if _x != n)  # split from one "A and B Properties" phrase
        if hnames and not g and not listed and \
                not any(same(n, x) for _q, x in _mentions(news, issuer) + _royalty_names(news)):
            continue                                       # a second headline "name" the news never uses is not one
        if set(fold(n).split()[:1]) & _HL_DESCRIPTION:
            continue                                       # "Capital Intensity Project", "Related Royalties"
        hnames.append(g[0] if g else n)
    # the headline names projects without their suffix ("No Response on Silicon Ridge ... Quartz for Snow White"):
    # a news project whose whole name the headline spells counts as a headline name
    fh = " " + " ".join(re.findall(r"[a-z0-9]+", fold(th))) + " "
    for g in sorted(proj, key=lambda g: g[2]):
        k = key(g[0])
        if len(k) >= 4 and (" " + k + " ") in fh and not any(same(g[0], x) for x in hnames) and \
                (_PROJ_LEVEL.search(g[0]) or not has_proj):
            at = fh.find(" " + k + " ")
            if not _HL_NOT_OURS.search(fh[max(0, at - 45):at + 1]):
                hnames.append(g[0])
    main = primary(head, body, issuer)
    ph = _PORTFOLIO_HL.search(th)
    port = bool(ph and not (len(hnames) == 1 and _PORTFOLIO_ADD.search(th))
                or not ph and _PORTFOLIO_N.search(news[:300]) and not hnames)
    big = [g for g in ranked if g[1] >= 2]
    if port and len(hnames) < 2:
        names = hnames + [g[0] for g in ranked if not any(same(g[0], x) for x in hnames)]
        return {"scope": "portfolio", "projects": names[:25],
                "why": "portfolio wording" + ("" if names else "; no project named")}
    if len(big) >= 5 and big[4][1] * 3 >= big[0][1] and not hnames:
        return {"scope": "portfolio", "projects": [g[0] for g in ranked][:25], "why": "five or more projects discussed"}
    if len(hnames) >= 2:
        return {"scope": "several", "projects": hnames, "why": "headline names %d projects" % len(hnames)}
    together = [n for n in _listed_together(news, [g[0] for g in big])]
    if hnames:
        one = hnames[0]
        others = [x for x in together if not same(x, one)]
        if others and any(same(one, x) for x in together):
            return {"scope": "several", "projects": [one] + others, "why": "headline project listed with others"}
        return {"scope": "one", "projects": [main if main and same(main, one) else one], "why": "headline names one project"}
    if len(big) >= 2 and big[1][1] * 3 >= big[0][1]:
        names = [g[0] for g in big if g[1] * 3 >= big[0][1]]
        return {"scope": "several", "projects": names, "why": "%d projects discussed" % len(names)}
    if len(together) >= 2:
        return {"scope": "several", "projects": together, "why": "listed together in the opening"}
    if main:
        return {"scope": "one", "projects": [main], "why": "one project discussed"}
    if ranked:
        return {"scope": "one", "projects": [ranked[0][0]], "why": "one project named"}
    return {"scope": "none", "projects": [], "why": "no project named in the news"}


def project_at(text, pos, names, issuer=None):
    """Which of `names` the passage at `pos` in text is about: the one its sentence names (the nearest before pos when
    it names several, else the nearest after); failing that, the nearest mention earlier in the same paragraph (a
    heading or lead sentence); else None."""
    if not names:
        return None
    ms = []
    for p, n in _mentions(text, issuer):
        hit = next((x for x in names if same(x, n) and (_one_count(x, n) or key(x) == key(n))), None)
        if hit:
            ms.append((p, hit))
    s0, s1 = 0, len(text)
    for m in _SENT_END.finditer(text):
        if m.end() <= pos:
            s0 = m.end()
        elif m.start() >= pos:
            s1 = m.start()
            break
    inside = [(p, n) for p, n in ms if s0 <= p < s1]
    if inside:
        before = [(p, n) for p, n in inside if p <= pos]
        return (before[-1] if before else inside[0])[1]
    p0 = 0
    for m in _PARA_END.finditer(text):
        if m.end() > pos:
            break
        p0 = m.end()
    earlier = [(p, n) for p, n in ms if p0 <= p < pos]
    if earlier:
        return earlier[-1][1]
    return None


def split_by_project(text, names, issuer=None):
    """{name: the sentences of text about it}, each sentence given to project_at()'s answer at its start; sentences
    about none of them are left out. A reader can run its own extraction on each part to get one row per project."""
    out = {n: [] for n in names}
    pos = 0
    for m in list(_SENT_END.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        sent = text[pos:end]
        if sent.strip():
            here = {x for q, y in _mentions(sent, issuer) for x in names if same(x, y)}
            if len(here) >= 2:                             # a sentence naming several goes to each of them
                for n in names:
                    if n in here:
                        out[n].append(sent.strip())
            else:
                n = project_at(text, pos + len(sent) - len(sent.lstrip()), names, issuer)
                if n is not None:
                    out[n].append(sent.strip())
        pos = m.end() if m else len(text)
    return {n: " ".join(v) for n, v in out.items()}


# ------------------------------------------------------------------ fingerprint
# Readers fingerprint exactly the helper code they run (portal/fingerprint.py). Drill Results, Resources and
# Royalties hashed this file whole until 1.0.5 moved them onto fingerprint.py too; the value is kept as it was.
PN_FINGERPRINT = "whole-file"


# ------------------------------------------------------------------ self-test
def _selftest():
    ok = [0, 0]

    def eq(label, got, want):
        ok[1] += 1
        if got == want:
            ok[0] += 1
        else:
            print(f"FAIL {label}: got {got!r}, want {want!r}")

    eq("headline project", primary("Orla Files Technical Report for its Camino Rojo Project", ""), "Camino Rojo Project")
    eq("metal word kept", clean("Hemlo Gold", "Property"), "Hemlo Gold Property")
    eq("bare", (bare("Nevada North Lithium Project"), bare("Hemlo Mine"), bare(None)), ("Nevada North Lithium", "Hemlo Mine", None))
    eq("symbol chain off", clean("Diablillos Ag-Au", "Project"), "Diablillos Project")
    eq("verb lead-in off", clean("Receives Drill Permit for Elida", "Project"), "Elida Project")
    eq("about lead-in off", clean("About Elida Porphyry", "Project"), "Elida Porphyry Project")
    eq("company is not a project", find("Omai Gold Mines Corp. reports"), [])
    eq("possessive: another company's", clean("Kinross' Great Bear", "Project"), "Great Bear Project")
    eq("neighbour skipped", find("drilling adjacent to the Hemlo Mine continues"), [])
    eq("caps headline", primary("PAN AMERICAN ACHIEVES GUIDANCE AT ITS LA COLORADA MINE", ""), "La Colorada Mine")
    eq("flagship alone is not a name", clean("Flagship", "Project"), None)
    eq("gold project alone is not a name", clean("Gold", "Project"), None)
    eq("company word", clean("Bunker Hill Mining", None), None)
    eq("body when headline has none", primary("Closes Private Placement",
                                              "Proceeds fund work at the Burnthut Project. The Burnthut Project ..."),
       "Burnthut Project")
    eq("headline word the body names", primary("Closes Financing for Burnthut Drilling",
                                               "work on the Kremer Project and the Burnthut Property. Burnthut Property "
                                               "drilling ... Burnthut Property"), "Burnthut Property")
    eq("deposit in headline, project in body", primary("Intersects 12 m at the Rainbow Deposit",
                                                        "The Rainbow Deposit lies within the Kelly Project. The Kelly "
                                                        "Project covers ... the Kelly Project"), "Kelly Project")
    eq("portfolio names no single project", primary("Corporate Update",
                                                    "the Alpha Project ... the Beta Project ... the Gamma Project ... "
                                                    "the Alpha Project ... the Beta Project ... the Gamma Project"), None)
    eq("one mention each: the first early one", primary("Closes Private Placement",
                                                        "the Alpha Project ... the Beta Project ... the Gamma Project"),
       "Alpha Project")
    eq("same ignores suffix and metal", same("Hemlo", "Hemlo Gold Mine"), True)
    eq("same is not loose", same("Hemlo", "Hemlo North"), True)
    eq("different", same("Côté", "Gosselin"), False)
    eq("accent-blind key", key("Côté Gold Mine"), "cote")
    eq("projects list", projects("Update on the Alpha Project", "the Alpha Project and the Beta Property"),
       ["Alpha Project", "Beta Property"])
    eq("year cut", clean("2025 Kelly", "Project"), "Kelly Project")
    eq("dash split", clean("NI 43-101 Report – Volney", "Property"), "Volney Property")
    eq("quoted name", primary("APPLICATION FOR MINING LICENSE AT THE ‘COPPER VALLEY’ PROJECT", ""), "Copper Valley Project")
    eq("company verb", primary("Mustang Energy Corp Accelerates Ford Lake Project with Permit", ""), "Ford Lake Project")
    eq("metal chain", primary("Prepares to Drill James Bay Cu-Zn-Au-Ag Nottaway Project", ""), "Nottaway Project")
    eq("figure caption", clean("Figure 1. Bullseye", "Claims"), "Bullseye Claims")
    eq("issuer mines at start", find("Idaho Champion Gold Mines Files Revised AIF"), [])
    eq("possessive study headline", primary("Meridian Mining’s Cabaçal Pre-Feasibility Study Delivers NPV", ""), "Cabaçal")
    eq("headline verb the body drops", key(primary("Laramide Positions Westmoreland Uranium Project for Development",
                                                   "the Westmoreland Uranium Project ... the Westmoreland Project")),
       "westmoreland")
    eq("descriptive hyphen", clean("Large-Scale Tower", "Project"), "Tower Project")
    # 1.0.1 (Economic Studies full-corpus comparison, 2026-09-23)
    eq("lower-case suffix", find("work on the Panuco silver-gold project continues"), [(12, "Panuco Project")])
    eq("lower-case suffix needs 'the'", find("Compelling project economics"), [])
    eq("money cut", clean("US$220M Kelly", "Project"), "Kelly Project")
    eq("money alone", clean("220M", "Project"), None)
    eq("project finance", find("Arranges US$220M Project Loan with Lenders"), [])
    eq("project management", find("Appoints Vice President, Project Management"), [])
    eq("mill last", primary("Restarts the Madsen Mill and the Rowan Project", ""), "Rowan Project")
    eq("comma region", clean("Yerington, Nevada Copper", "Project"), "Yerington Copper Project")
    eq("region list", clean("British Columbia and Quebec", "Prospect"), None)
    eq("region plural", clean("Nevada lithium", "Projects"), None)
    eq("study 'of'", primary("Results of Los Reyes Preliminary Economic Assessment", ""), "Los Reyes")
    eq("metals with join", clean("Gold and Silver", "Project"), None)
    eq("bare any case", bare("Kelly project"), "Kelly")
    eq("caps run", find("EMERITA GRANTED TWO ADDITIONAL PROPERTIES IN SPAIN"), [])
    eq("caps run keeps the name", primary("FRONTIER LITHIUM INITIATES MINE AND MILL FEASIBILITY STUDY FOR THE PAK LITHIUM "
                                          "PROJECT in Ontario", "the PAK Lithium Project"), "PAK Lithium Project")
    eq("possessive owner", clean("Company's", "Project"), None)
    eq("lower-case metal description", clean("Ermitaño gold and silver", "Mine"), "Ermitaño Mine")
    eq("element symbols", clean("Blue Lake Cu Ni Pt Pd", "Property"), "Blue Lake Property")
    eq("process noun + of", clean("Resumption of Plomosas Silver", "Project"), "Plomosas Silver Project")
    eq("number word kept", clean("Two Peaks", "Project"), "Two Peaks Project")
    eq("number + lead word", clean("Two Additional", "Properties"), None)
    eq("not alone", (clean("Key", "Project"), clean("Canadian", "Project")), (None, None))
    eq("phone number", clean("BC V6E 3V7 778-788-4836", "Prospect"), None)
    eq("word start", find("the Luanga PGM+Au+Ni Deposit"), [])
    eq("combined counts half each", primary("Update", "the AurMac and Hyland Projects. The AurMac Property ... "
                                                      "the Hyland Project ... the AurMac Property"), "AurMac Property")
    eq("mentions of one project", primary("Drilling at PCH", "the PCH Project ... the PCH Ionic Adsorption Clay project "
                                                            "... the Alces Lake Property"), "PCH Project")
    eq("north is another project", primary("Update", "the Shovelnose Gold Project, the Shovelnose Gold Project, the "
                                                     "Skoonka Gold Project, the Skoonka North Project, the Prospect "
                                                     "Valley Gold Project"), "Shovelnose Gold Project")
    eq("body confirms full name", primary("Files Report for the West Hawk Lake Project",
                                          "the West Hawk Lake Project ... the High Lake property ... Lake Property"),
       "West Hawk Lake Project")
    eq("comma region in text", find("PEA Results for Its Yerington, Nevada Copper Project"), [(31, "Yerington Copper Project")])
    eq("inside a number", find("the 6,215-acre Solar Lithium Project"), [(6, "Solar Lithium Project")])
    eq("suffix-hyphen word", find("Launch Property-Wide Mapping"), [])
    eq("verbs of headlines", (primary("VIZSLA SILVER AWARDS EPCM AND MINE DESIGN CONTRACTS FOR THE PANUCO PROJECT", ""),
                              primary("Study Confirms Economically Robust Copper Project", ""),
                              primary("US Copper Stakes Additional Claims", "")), ("Panuco Project", None, None))
    eq("nationality plural", (clean("Swedish", "Properties"), clean("Chilean and Canadian", "Projects")), (None, None))
    eq("sentence end", clean("US. These", "Projects"), None)
    eq("web address", clean("6ix.com/event/recap About El Quevar", "Project"), "El Quevar Project")
    eq("mill-only headline, project in body", primary("Completes Montauban Mill Building",
                                                      "the Montauban Project ... the Montauban Mill ... Montauban Project"),
       "Montauban Project")
    eq("a prospect inside a project is not a portfolio", primary("Exploration Update",
       "the Secret Pass Gold Project ... Secret Pass Gold Project ... Secret Pass Property ... the Tin Cup Prospect ... "
       "Tin Cup Prospect ... the FM Prospect ... FM Prospect"), "Secret Pass Gold Project")
    eq("newline in caps run", _titlecase_caps("TO EXPLORE ADVANCING \nVAN DYKE ISCR PROJECT"),
       "To Explore Advancing \nVan Dyke Iscr Project")
    # 1.0.2 (Options full-corpus comparison, 2026-09-23)
    eq("Sur is a place word", clean("Filo Sur", "Project"), "Filo Sur Project")
    eq("which holds ends a name", clean("Magpie Mines Which Holds Large Vanadium And Titanium", "Deposits"), None)
    eq("advancing ends a name", clean("Substantial Compliance Advancing", None), None)
    eq("mine workings", find("Early Exploration Identifies Pegmatite Outcropping and Historical Mine Workings"), [])
    eq("dash before a verb", clean("Hi-View News Release- Acquires Additional", "Claims"), None)
    eq("dash line break still joins", clean("Lawyers- Ranch", "Project"), "Lawyers-Ranch Project")
    eq("new zealand is a place", clean("New Zealand", None), None)
    # 1.0.3 rev 4 (Economic Studies full-corpus comparison, 2026-09-24)
    eq("an adjective is not a name", clean("Adjusted", "Project"), None)
    eq("practice words end a name", find("How Surface Mining Maximizes Precious Metal Extraction and Reclamation Practices Mine"), [])
    # 1.0.3 (Economic Studies 1.0.6 full-corpus check, 2026-09-24)
    eq("two projects discussed unequally is not a portfolio",
       primary("Reports Q1 Results", "the Segilola Mine ... Segilola Mine ... Segilola Mine ... Segilola Mine ... the "
                                     "Douta Project ... Douta Project ... Douta Project ... the Guitry Project"), "Segilola Mine")
    eq("three projects discussed equally is still a portfolio",
       primary("Corporate Update", "the Alpha Project, Beta Project, Gamma Project; Alpha Project, Beta Project, "
                                   "Gamma Project; Alpha Project, Beta Project, Gamma Project"), None)
    eq("a long wire header", primary("Closes Private Placement", "x" * 4100 + " the Cabaçal Gold-Copper Project"),
       "Cabaçal Gold-Copper Project")
    eq("a list of assets", clean("ELG Underground Media Luna Underground Morelos", "Complex"), None)
    eq("two names that share a word", (clean("Kulyk Lake and Daly Lake", "Properties"),
                                         clean("Borland East and Borland North", None)),
       ("Kulyk Lake and Daly Lake Properties", "Borland East and Borland North"))
    eq("a doubled name is a name", (clean("Cuiú Cuiú", "Project"), clean("Iska Iska", "Project")),
       ("Cuiú Cuiú Project", "Iska Iska Project"))
    eq("a commodity phrase", clean("Platinum Group Metal", "Project"), None)
    # 1.0.4 (Technical Reports 1.0.1 full-corpus comparison, 2026-09-25)
    eq("a dotted name", clean("K.Hill Manganese", "Project"), "K.Hill Manganese Project")
    eq("initials still end a lead-in", clean("B.C. Kelly", "Project"), "Kelly Project")
    eq("Road is part of a name", clean("Gold Road", "Mine"), "Gold Road Mine")
    eq("road accessible is not a name", clean("Road Accessible Gold", "Project"), None)
    eq("a numbered name keeps its bracket", clean("TitanBeach One (1)", "Project"), "TitanBeach One (1) Project")
    eq("headline words", (clean("Near-Term", "Project"), clean("Modelled", "Deposits"), clean("External", "Mine"),
                          clean("Restart", "Project"), clean("Infill", "Project"), clean("Lode", "Claims")), (None,) * 6)
    eq("a name ending in Lode", clean("Mother Lode", "Project"), "Mother Lode Project")
    eq("a lone generic word", (clean("Lake", "Property"), clean("Bay", "Project")), (None, None))
    eq("a plural of nations and metals", clean("Four Chilean Copper", "Projects"), None)
    eq("a nation and a metal, singular, stays (Options regions)", clean("Colombian Gold", None), "Colombian Gold")
    eq("a nation and a metal, plural, stays (Options regions)", clean("Colombian Gold", "Projects"),
       "Colombian Gold Projects")
    eq("initials without the last dot", (clean("Known U.S", "Deposit"), clean("Refusal Over B.C", "Claims"),
                                         clean("B.Sc", "Mine")), (None, None, None))
    eq("a lone Road, a Ball Mill", (clean("Mine Road", "Project"), clean("Ball", "Mill")), (None, None))
    eq("place names after a cut word", [n for _p, n in find("the Mineral Ridge Project, the Table Mountain Project and South Voisey's Bay Claims")], ["Mineral Ridge Project", "Table Mountain Project", "South Voisey's Bay Claims"])
    eq("a consultancy is not a mine", find("Ms. Stella Searston, RM-SME Mine Technical Services Geology"), [])
    eq("adapter: helper first, no mill", [n for _p, n in find_with("the Alpha Project and the Beacon Gold Mill")],
       ["Alpha Project"])
    eq("adapter: the reader's finder when the helper names none",
       [n for _p, n in find_with("nothing here", lambda t, i: [(0, "Old Name Project")])], ["Old Name Project"])
    eq("adapter: a deposit after its project",
       [n for _p, n in find_with("the Pepas Deposit in the Anza Project")], ["Anza Project", "Pepas Deposit"])
    # 1.0.5 (PN_MULTI_V1, 2026-09-27): several projects per release, for readers that write one row per project
    _b = ("VANCOUVER - Silver Spruce reports on its Kelly and Lodestar projects. At the Kelly Project, drilling "
          "returned 5 g/t gold over 10 m. The Kelly Project covers 2,000 ha. At the Lodestar Project, sampling returned "
          "1.2% copper. The Lodestar Project is road accessible.\n\nAbout Silver Spruce Resources Inc.\nThe company "
          "also holds the Mystery Project and the Marilyn Property.")
    _r = release_projects("Silver Spruce Drills Kelly and Lodestar Projects", _b)
    eq("several: a headline list", (_r["scope"], _r["projects"]), ("several", ["Kelly Project", "Lodestar Project"]))
    eq("several: the About paragraph is not news", "Mystery" in subject_text(_b), False)
    eq("several: project_at", (project_at(_b, _b.index("1.2% copper"), _r["projects"]),
                               project_at(_b, _b.index("2,000 ha"), _r["projects"])), ("Lodestar Project", "Kelly Project"))
    _s = split_by_project(subject_text(_b), _r["projects"])
    eq("several: split", ("5 g/t" in _s["Kelly Project"], "1.2%" in _s["Lodestar Project"], "1.2%" in _s["Kelly Project"],
                          "Kelly and Lodestar" in _s["Lodestar Project"]), (True, True, False, True))
    eq("several: two royalties", release_projects(
        "Vox Royalty Enters into Binding Agreements to Acquire the Saxby Gold Royalty and the Uley Graphite Royalty",
        "Vox has agreed to acquire the Saxby gold royalty and the Uley graphite royalty.")["projects"], ["Saxby", "Uley"])
    eq("several: a royalty company is not a project", release_projects(
        "Electric Royalties to Acquire 1% NSR on Cancet Lithium Project",
        "Electric Royalties Ltd. will acquire a 1% NSR on the Cancet Lithium Project. The Cancet Lithium Project is in "
        "Quebec.")["projects"], ["Cancet Lithium Project"])
    eq("several: a portfolio", release_projects("Barrick Agrees to Sell Royalty Portfolio to Maverix Metals",
                                                "a portfolio of 22 royalties, including the Eskay Creek Project")["scope"],
       "portfolio")
    eq("several: adding to a portfolio is one project", release_projects(
        "Conquest Options Marr Lake to add to Critical Metals Portfolio",
        "Conquest has optioned the Marr Lake Project. The Marr Lake Project adds to the Wisa Lake Property.")["scope"], "one")
    eq("several: a neighbour in the headline", release_projects(
        "Trius Completes Purchase of Gander West Property Near New Found Gold's Queensway Project",
        "the Gander West Property, located near New Found Gold's Queensway Project. The Gander West Property ...")["projects"],
       ["Gander West Property"])
    eq("several: a deposit inside its project", release_projects(
        "AbraSilver Intersects 31.5 Metres at JAC Deposit on Diablillos Project",
        "Drilling at the JAC Deposit on the Diablillos Project ... the Diablillos Project ... the JAC Deposit")["scope"], "one")
    eq("several: headline names without suffix", release_projects(
        "Rogue Corporate Update: No Response from Québec on Silicon Ridge, Quartz Marketing for Snow White",
        "an update on the Silicon Ridge Project and the Snow White Project. The Silicon Ridge Project awaits a response. "
        "Quartz from the Snow White Project is being marketed.")["projects"], ["Silicon Ridge Project", "Snow White Project"])
    eq("several: a capital And in a list", release_projects("QUINN LAKE AND GRUB LINE PROPERTIES FIELD WORK",
                                                            "work on the Quinn Lake and Grub Line properties")["projects"],
       ["Quinn Lake Property", "Grub Line Property"])
    eq("several: a description is not a second project", release_projects(
        "Ero Announces Inaugural PEA for Furnas, Outlines Low Capital Intensity Project",
        "the Furnas Copper-Gold Project ... Furnas Copper-Gold Project ... a low capital intensity project")["scope"], "one")
    eq("several: one and none", (release_projects("Closes Private Placement", "work at the Burnthut Project. The Burnthut "
                                                  "Project ...")["scope"],
                                 release_projects("Announces AGM Results", "All resolutions passed.")["scope"]), ("one", "none"))
    print(f"project_names selftest: {ok[0]}/{ok[1]} passed")
    return ok[0] == ok[1]


if __name__ == "__main__":
    import sys
    sys.exit(0 if _selftest() else 1)
