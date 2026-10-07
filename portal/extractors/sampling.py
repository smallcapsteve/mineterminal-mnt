"""Sampling & Geoscience Results reader, facts-store version (SMP_V1, 2026-09-29).

The source of the Sampling & Geoscience page once it passes the accuracy gate. Written against the 78-item key Justin
confirmed on 2026-09-29 (claude/MNT_SMP_SET_LABELS_CONFIRMED_2026-09-29.json) and the label guide
claude/MNT_SMP_LABEL_GUIDE_2026-09-29.md.

Justin's rules (2026-09-28/29):

  1. ONE ROW PER SAMPLE TYPE per project for the results a release reports: rock samples (grab, chip, channel, trench),
     geochemistry (soil, till, sediment, other), geophysics (one row per survey method), bulk and brine samples, and
     mapping findings without assays.
  2. HISTORICAL results are rows too, flagged, when the release gives a value (a grade, an anomaly or a count). The
     issuer's own results repeated from an earlier release are not rows.
  3. RESULTS ONLY: plans, starts, samples collected or at the lab, and drill results are not rows.
  4. FIELDS: the best grade (the headline's for that sample type, else the highest of the lead metal; the lead interval
     of an "including" pair, rule SN), the width a channel, chip or trench grade is over, the anomaly a geochemical or
     geophysical survey found (metal and size), and the sample count.

MEASURED (honest, fresh blind samples; gate 90%): rules tuned over four rounds, each confirmed on a new 250-release sample.
The version shipped scores, on the last fresh sample (5): rows 89.7%, sample type 97.4%, project 90.8%, best grade 74.8%,
width 77.3%, anomaly 46.3%, sample count 61.4%. Released as an EARLY VERSION (Justin, 2026-09-29): row, sample type and
project are gated; the other fields are stored and reported, not gated (portal/accuracy_smp.py).

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per row (ordinal 0..n-1)
to_prediction(records) -> dict|None    what the accuracy judge compares

1.0.1 (2026-09-30, after the ACC150 blind check: rows 90.4% right, 69.5% of releases picked up). Each change names a
kind of release or error, none a company, project or release:
  - HISTORICAL FLAG BOTH WAYS. A deal (acquire, option, earn-in, staking, agreement, sale), a technical-report filing, a
    data compilation / review or a "historic results" headline presents older work: every result in it is historical,
    unless a deal headline itself reports a new result. More sentence cues: "previous workers / explorers / owners",
    "government ... samples", author-year citations "(Allen, 1982)", and "previous trenching / sampling" by others. The
    company's own earlier sampling cited to its news release is restated (no row), not historical. The headline is read
    without the issuer's name ("Discovery ... Metals", "Q2 Metals" are not discoveries or quarters).
  - NOTHING TO SHOW, NO ROW. Resource estimates and economic studies, financings / meetings / quarterlies / corporate
    updates, and metallurgy, recovery, processing or sales headlines give no row. A drill release (drill result, drill
    headline interval, generic assay headline over a drill program, or a drill program started / planned) keeps only the
    kinds its headline names as results (a drill start before any result: none; brine or bulk from holes: none; a
    geophysical feature only when stated as a new finding). Desktop reviews, studies and interpretations of existing
    data keep only historical rows (rule ST). A kind the headline names only as work completed, started, received or
    planned ("completes airborne survey and soil program", "targets for heliborne magnetic survey", "... still being
    investigated") needs a grade. Models and geophysical maps are desktop products. A gravity plant or circuit is not
    a gravity survey; "Mt" is not an MT survey (survey acronyms are matched in capitals).
  - TYPES. "Channel chip" / "chip-channel" samples are one chip row; grab samples taken from trenches are grab (no extra
    trench row); a dissolved grade (mg/L) is a brine sample, and a brine value written without its metal is read; a
    soil-gas survey is soil only; till is dropped for soil only when the text speaks of till as a material ("soil
    samples taken in till"); a bulk row needs a grade or a "bulk sample results" headline.
  - LONE MAPPING. A headline mapping row gives way once assayed rock rows stand (mapping rows are for findings without
    assays).
  - WIDER, WHERE ROWS STAY RIGHT. Besides headline rows and body rows graded in two sentences: a survey method the
    headline announces (or, for a generic "geophysical survey results" headline, a method in the first 15 sentences),
    and a grab / chip / channel type graded once in the lead of a release whose headline announces rock sampling. A
    widened row never repeats a type (and method) another row already has.

1.0.2 (2026-10-01, after fresh blind checks of releases found outside the tag: rows 76.5% / 83.8% right). Rows only when the
release itself announces this kind of news; each change names a kind of release or of framing, none a company or release:
  - DEALS READ THEIR FRAMING. A deal (acquire, option, staking, licence or permit granted, or a lead that announces one
    under a headline with no result) keeps a sentence's own old-work cue (historical). Otherwise the release's framing
    statements decide: the company's own earlier work (dated before this year, or cited to its release) is restated, no
    row; its due-diligence or this year's work, or the vendor's / optionor's / prospector's work dated within two years,
    is new (guide item 70); a sentence that goes on from one naming older work stays historical; with no word at all of
    whose work the results are, the deal is the news (no row). A neighbour's discovery named for comparison ("similar to
    X's new discovery, Y"): results at Y are the neighbour's. Bought or acquired survey data: its geophysics is
    historical, other kinds are background.
  - RESTATED RUNS. The past perfect ("had returned") is an earlier result; the sentence after a restated one (or after a
    short lead-in such as "In previous sampling.") is restated too unless it says it is new or dates itself this year;
    "the 244 g/t Au grab sample" refers to a known sample. A headline grade the body gives as older work by others is
    historical.
  - NOT THIS RELEASE'S NEWS. Awards and recognitions; a lead that announces plans under a headline with no result; "to
    drill / carry out / undertake / execute" headlines are plans; "historical drilling" is drilling, not old sampling;
    a lead on recently completed drilling or a hole's depth ("completed at a depth of 502 ft") makes a generic assay
    headline a drill release; "6.79 m @ 3.14% Cu from 80.47 m" is a hole's interval; "brine drill targets" or a
    "lithium brine project" is no brine sample; a soil, till or sediment anomaly the headline's result lies within,
    along or up-ice of is the place, not the news.
  FULL-TEXT LOSSES (same day, after tagged releases the live reader showed were checked on their full text; each change
  names a kind of release or wording, none a company or release):
  - A GENERIC SAMPLING HEADLINE ("X Samples 21 g/t Gold", "Assays up to ...") is a drill release only when the lead opens
    on the release's own drilling, read without the headline it repeats: "core" that is no drill core ("a central magnetic
    core", "the core X Project"), drilling by others or long ago in that clause ("previously reported, Y Mines drilled ... in
    the 1950s", "existing drill results", "2019 drill core") and a drill program whose results are still pending are not
    it, unless the release samples those holes ("re-sampling of archived drill core"); the release's own sampling,
    underground or stripping work comes first as surface work. Drill targets the headline defines, extends or supports are
    the outcome of surface work unless the lead opens on drilling; a drill rig bought in a second clause is no program.
  - HEADLINE WORDS READ IN THEIR CLAUSE. A resource named as the place of a new result ("10 km south of current mineral
    resource"); recoveries assumed for a metal equivalent, or a recovery figure after a field sample's grade ("trenching
    returns 5.26 g/t gold with 85.9% gravity recovery"); a corporate update "and new sampling results"; "acquisition and
    interpretation of a survey" (collecting data, not a deal); kinds found before review words ("identifies new IP
    anomalies ... review of historical data completed") stay new, and a review in a second clause or followed by the
    release's own grades does not make a desktop release; a completed survey that "highlights" or "supports" a finding.
  - ROWS. A mapping row gives way only to rock rows that stand; a bulk headline grade in an oxide the reader does not
    parse ("4.81% light rare earth oxide head grade") keeps the bulk row.

1.0.3 (2026-10-02, after the ACC150b blind re-check: page rows 83.5% right; outside-tag finds 90.1% right with the round-5
rule). Row accuracy on releases that truly have sampling or geoscience news; each change names a kind of release or
wording, none a company or release:
  - GEOPHYSICS, ONE ROW PER METHOD WITH A RESULT. A method the release names only among a survey's instruments or
    parameters ("magnetic, VLF and gamma-ray spectrometry at 100 m line-spacing") gives no widened row: its cue must sit
    next to a finding (anomaly, conductor, high or low, trend, lineament, structure). The resistivity or conductivity of a
    release whose only electrical survey is magnetotelluric (CSAMT, AMT, MT) is that survey's, not IP.
  - ONE SAMPLE SET, ONE ROW. Rock kinds named as one list ("forty chip, channel and grab samples range from 4.7% zinc (over
    0.6 m)", "channel and chip sample highlights") are one set: its grades go to the first kind with a length when given
    over a length, else to the first point kind (grab), and all of the set's grades follow the first. "Surface samples"
    names no method, so a channel-only release keeps its generic headline grade on the channel row. Heavy-mineral
    concentrate (HMC) gold values are till results; rock samples taken "from parts of the soil anomaly" are rock samples.
  - DRILLING IS NOT SAMPLING. Auger assays, samples, holes or drilling are drilling (guide), unless the auger is a soil
    survey's tool ("dutch / hand / soil augers"). A headline drill interval ("historical assays including 115.4 metres at
    1.21% Li2O") gives no row, old or new. A generic headline's lead is read after a letterhead (address, phone, listings),
    "grades ... intersected" in it is drilling, and drilling still to come (planned, scheduled, pads under construction)
    is not the release's drilling.
  - OLD OR NEW. In a release that reviews older data, the company's own new or follow-up survey or sampling is new. A new
    land, exploration or claim position (with no program or result in the headline) is a deal. Grades quoted for the
    occurrences a property "is host to", "the 1981 ... sampling program" and a geological survey branch are older work.
  - STATUS AND NAMES. "Conducts ... survey" in a headline names work, not a result. A project name holding a headline verb
    ("X Purchases Strategic Y Mine") is a headline fragment and is not used.

1.0.4 (2026-10-03, FIX5 after the ACC150c blind check: rows 87.1% right, 57.4% found; 22 releases with results showed
nothing). Rows for results the release reports but the reader missed; each change names a kind of release or wording, none a
company or release:
  - KIND CARRIED ON. A graded sentence that names no sample type but speaks of samples or assays ("The other two samples
    assayed 15.05 and 7.06 g/t Au") goes on with the kind the sentence before (or two before) named, else with the one rock
    or geochemical kind the headline names (geochemical kinds only for ppm / ppb values); such sentences add grades, not row
    support. A grade written before its own sample ("17.60 g/t Au from an outcrop grab sample") takes that sample's kind.
  - HEADLINE ROWS WITHOUT A GRADE. A headline that reports a named rock method's results ("Channel Assays Extend ...",
    "Results from Channel Sampling Program") keeps that row when the release gives no parseable grade; "rock / surface sample
    results" name no method and do not.
  - MORE KINDS SEEN. Boulders found and assayed ("high-grade gold-bearing boulders", "this boulder graded") and float ("quartz
    float", "from float") are grab samples; "chip channel" samples are chip samples. Not kinds: "selected results" / "select
    assay highlights" (a choice of results), a capitalised cue in a place name ("Pine Channel Project", "Soil Lake property"),
    "gold grain size".
  - WIDER, WHERE ROWS STAY RIGHT. Under a headline naming no kind: rock rows graded once when the lead announces rock / surface
    results ("has received rock geochemical results"), and a soil / till / sediment survey the release returns to (three
    sentences or more) with its anomaly and its own results or sample count. Brine values under a generic "sampling results"
    headline. A historical rock row graded in one sentence, when its source is named (historic, a year, operators, owners,
    government, a geological survey, a citation), outside plan and drill releases, and not when all its years are recent.
  - HISTORICAL FLAG PER GRADE. In a sentence quoting the release's own new results beside older work by others, each grade
    takes the nearest old- or new-work cue before it (a year within two years of the release is new); grades before an
    old-work clause after a clause break are new. "Historical trench" as a place is not older work.
  - TYPES. Channel samples become trench samples only when the release reports trench results of its own beside them or ties
    them to a trench ("from trench TR-11"), not for a "trenching program" or trenches named for other things.
  - VALUES. "5.26 grams per tonne (g/t) gold" and "97 g/t (2.83 opt) Ag" are read.
  REV B (same day, after a site-wide check: 70 releases, 12 tagged, lost their only grade and so their row):
  - A value written after ">" is a grade, as stated (1.0.3 behaviour; "Receives >10,000 g/t Ag Sample"). Values after
    threshold wording ("9 samples returned over 5 g/t Au", "above", "more than") are read for rows too and flagged; the best
    grade is the highest value stated, an explicit value when it is at least as high. A release with sampling results
    never loses its row only because its grades are written as ">X" / "over X".
  - (superseded in rev c) A widened row gave way only to another row of its type on the same project.
  REV C (same day, after the held-back half and a new blind set showed precision falling: 88.2 / 86.0). Each change kept
  only if it lowers row precision on neither fold (ACC150c dev, ACC150d):
  - NOT RESULTS. A concentrate produced ("produces 7.2% Li2O technical grade spodumene concentrate") is metallurgy. A target
    "identified through data compilation and modelling" is desktop work (rule ST). A finding the headline names as already
    announced ("area includes recently announced gold till anomaly") does not make a "completes survey" headline a result.
  - ONE-SENTENCE HISTORICAL ROWS NARROWED. Not when every graded sentence is about drilling, a resource or estimate,
    production or tonnes, or a historic place newly sampled ("previously unsampled historic X trenches return ...").
    "Historical trench results include ..." is older work (the place exclusion now yields to "results" / "yielded").
  - GEOCHEMICAL WIDENING NARROWED. Not when the release presents that kind as older or already-announced work.
  - WIDENED ROWS. Rev b's project-aware rule added rows on alias projects; now a widened row gives way to a strict row of its
    kind or to an earlier widened one (the first stands), so two prospects' threshold-graded rows no longer cancel out.
  - "vein float" is no float-sample cue (only "quartz / angular / mineralized float", "from / of / in float").
  - "Late last year we completed ..." dates the work; only "reported / announced ... last year" restates a result.

Self-tests: python3 -m portal.extractors.sampling
"""
from __future__ import annotations

import json
import re

from portal import facts as F
from portal import fingerprint as FP
from portal import project_names as PN
from portal.extractors import technical as T

NAME = "sampling"
VERSION = "1.0.6"  # 2026-10-06 FIX8: a five-digit sample number written without a comma is not a sample count (stored counts of 29,143-71,300); 2026-10-04 FIX5: version only (the Technical reader helpers it borrows were rewritten ASCII-only, same behaviour); 2026-10-01: rows only for the release's own news: deal framing, restated runs, context kinds, plans; full-text losses fixed; 2026-10-02: row accuracy: one row per sample set and per surveyed method, auger is drilling, follow-up surveys new; 2026-10-03 FIX5: results that showed nothing or part: untyped graded sentences inherit their kind, headline rock rows without a grade, boulders/float, lead-announced rock results, geochem and brine rows the release returns to, one-sentence historical rows with a named source, per-grade historical flag in mixed sentences, channel kept unless tied to trenches, chip channel = chip, place names and "selected results" are no kinds; rev b: a value after ">" is a grade again (1.0.3), threshold-only grades ("over 5 g/t") keep the row, the highest stated value wins, widened rows on two projects both stand; rev c: precision on two folds: concentrates are metallurgy, compilation/modelling targets are desktop, already-announced headline findings are not results, one-sentence historical rows not from drill/resource/production figures or historic places newly sampled, geochem widening not for kinds presented as older work, first widened row of a kind stands, no "vein float" cue
KIND = "sample_result"
TAG = "Sampling & Geoscience Results"
TEXT_CAP = 40000
LEAD_SENTS = 45
HEADLINE_ONLY = False               # rows only for the sample types the headline names
STRICT_ROWS = True                  # rows from the headline, or body rows with grades in two or more sentences
HIST_WIDE = True
GEO_WIDE = True
PLAN_NO_ROWS = True                 # a plan headline: body grades are earlier results, not rows

SAMPLE_TYPES = ("grab", "chip", "channel", "trench", "soil", "till", "sediment", "other_geochem", "geophysics", "bulk",
                "brine", "mapping")
ROCK = ("grab", "chip", "channel", "trench")
GEOCHEM = ("soil", "till", "sediment", "other_geochem")
WIDTH_TYPES = ("chip", "channel", "trench")
ANOMALY_TYPES = GEOCHEM + ("geophysics",)
TXT_FIELDS = ("sample_type", "survey_type", "project", "target", "grade_unit", "grade_metal", "anomaly_json", "operator",
              "evidence")
NUM_FIELDS = ("grade", "width_m", "sample_count", "historical", "line_km", "bulk_tonnes")

# ------------------------------------------------------------------ text
_FLS = re.compile(r"(?i)(?:^|\s)(?:cautionary\s+(?:note|statement|language)s?\b|forward[\s\-]+looking\s+(?:statements?|information)"
                  r"\s*(?:$|[A-Z:])|notice\s+regarding\s+forward|neither\s+(?:the\s+)?(?:tsx|canadian\s+securities|cse)\b|"
                  r"no\s+stock\s+exchange|to\s+view\s+the\s+source|on\s+behalf\s+of\s+the\s+board)")
_ABOUT_CO = re.compile(r"(?:^|\s)About\s+(?:the\s+Company\b|Us\b|[A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5}\s*(?:[:.]|\s(?=[A-Z][a-z]+\s"
                       r"(?:is|was|Inc|Corp|Ltd|Limited|Resources|Metals|Mining|Gold|Silver|Copper|Energy|Minerals)\b)))|"
                       r"(?:^|\s)ABOUT\s+[A-Z]")
# QA/QC and method paragraphs: they describe how samples were handled, not results
_QA = re.compile(r"(?i)\b(?:quality\s+(?:assurance|control)|QA/?QC|analytical\s+(?:procedures?|methods?)|sample\s+(?:preparation|"
                 r"analysis|handling|security)|chain\s+of\s+custody|were\s+(?:bagged|sealed|delivered|shipped|transported|sent|"
                 r"submitted)\b|(?:ALS|SGS|Bureau\s+Veritas|Actlabs|MSALABS|MS\s+Analytical|AGAT|Intertek)\b[^.]{0,80}\b(?:laborator|lab\b|"
                 r"analy[sz]ed|assayed|fire\s+assay|ICP)|fire\s+assay\s+(?:with|and|finish)|certified\s+reference\s+materials?|"
                 r"blanks?\s+and\s+(?:duplicates|standards)|standards?,\s+blanks|qualified\s+person|technical\s+(?:information|"
                 r"content)\s+(?:in|of)\s+this)")
_SPLIT = re.compile(r"(?<![\s(][A-Z]\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\bSt\.)(?<!\bMt\.)(?<!\bNo\.)(?<!\bvs\.)(?<!\bapprox\.)"
                    r"(?<!\bca\.)(?<![0-9]\.)(?<=[.;!?])\s+(?=[A-Z\u201c\"\u2022\u25aa(])|\s+[\u2022\u25aa\u25cf\u00a7\u27a2\u25ba]\s+|"
                    r"\s+(?:-|\u2013)\s+(?=[A-Z])(?!(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d)")


# Word-processor bullet glyphs (private-use code points), written with chr() so the file stays printable
_PUA_BULLETS = "".join(chr(c) for c in (0xF0A7, 0xF0B7, 0xF0D8))


def _prepare(headline, body):
    b = T._norm((body or "")[:TEXT_CAP]).replace("\u2010", "-").replace("\u2011", "-").replace("\u2013", "-")
    b = re.sub(r"(?<=[A-Za-z])- (?=[A-Za-z])", "-", b)                          # "High- Grade" (a PDF line break)
    b = re.sub(r"https?://\S+", " ", b)
    b = re.sub("[" + _PUA_BULLETS + "\u2022\u25aa\u25cf\u27a2\u25ba]", " \u2022 ", b)
    b = T._flat(b)
    fls = _FLS.search(b, int(len(b) * 0.25))
    if fls:
        b = b[:fls.start()]
    for m in _ABOUT_CO.finditer(b, 900):
        b = b[:m.start()]
        break
    h = T._flat(T._norm(headline or "").replace("\u2010", "-").replace("\u2011", "-").replace("\u2013", "-"))
    return h, b


def _sentences(b):
    out = []
    for p in _SPLIT.split(b):
        p = (p or "").strip(" \u2022")
        if not p:
            continue
        if out and (len(p) <= 12 or re.match(r"^[a-z0-9$(]", p)):
            out[-1] += " " + p
        else:
            out.append(p)
    return out


# ------------------------------------------------------------------ values
METALS = {"gold": "Au", "silver": "Ag", "copper": "Cu", "zinc": "Zn", "lead": "Pb", "nickel": "Ni", "cobalt": "Co",
          "lithium": "Li", "uranium": "U3O8", "antimony": "Sb", "tungsten": "W", "molybdenum": "Mo", "platinum": "Pt",
          "palladium": "Pd", "tin": "Sn", "cesium": "Cs", "caesium": "Cs", "tellurium": "Te", "bismuth": "Bi",
          "vanadium": "V", "manganese": "Mn", "graphite": "Cg", "graphitic carbon": "Cg", "rare earth": "TREO",
          "potassium": "K", "magnesium": "Mg", "iron": "Fe", "titanium": "Ti", "tantalum": "Ta", "niobium": "Nb",
          "gallium": "Ga", "germanium": "Ge", "indium": "In", "arsenic": "As", "helium": "He", "boron": "B",
          "scandium": "Sc", "chromium": "Cr", "barium": "Ba", "rubidium": "Rb", "beryllium": "Be", "mercury": "Hg"}
_SYM = (r"AuEq|AgEq|CuEq|ZnEq|NiEq|Au\s?Eq|Ag\s?Eq|Cu\s?Eq|Au-Eq|Ag-Eq|Cu-Eq|AuEQ|AgEQ|CuEQ|Au|Ag|Cu|Zn|Pb|Ni|Co|Li2O|Li|U3O8|eU3O8|U|Sb|W|WO3|Mo|MoS2|Pt|Pd|Sn|Cs2O|Cs|Te|Bi|V2O5|V|Mn|MnO|Cg|TGC|TREO|"
        r"REO|K2O|KCl|K|Fe2O3|Fe|TiO2|Ti|Ta2O5|Ta|Nb2O5|Nb|Ga2O3|Ga|Ge|In|As|He|B|Sc2O3|Sc|Cr2O3|Cr|BaSO4|Ba|Rb2O|Rb|"
        r"BeO|Be|Hg|3E|2E|PGE\+Au|PGM\+Au|PGE|PGM|Pt\+Pd|Pd\+Pt|AuEq|AgEq|CuEq|ZnEq|NiEq|PbEq|MoEq|Au\s?Eq|Ag\s?Eq|Cu\s?Eq|"
        r"Au-Eq|Ag-Eq|Cu-Eq|AuEQ|AgEQ|CuEQ")
_METAL_WORDS = r"lithium\s+oxide|gold|silver|copper|zinc|lead|nickel|cobalt|lithium|uranium|antimony|tungsten|molybdenum|platinum|palladium|tin|" \
               r"ca?esium|tellurium|bismuth|vanadium|manganese|graphitic\s+carbon|graphite|rare\s+earths?|potassium|magnesium|" \
               r"iron|titanium|tantalum|niobium|gallium|germanium|indium|arsenic|helium|boron|scandium|chromium|barium|" \
               r"rubidium|beryllium|mercury|gold\s+equivalent|silver\s+equivalent|copper\s+equivalent"
_UNIT = r"g/t|g\s?/\s?t|gpt|g/tonne|grams?\s+per\s+(?:metric\s+)?tonne|%|ppm|ppb|mg/l|mg/L|opt|oz/t|oz/ton|ounces?\s+per\s+ton"
_NUMV = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
# "12.5 g/t Au", "3.02% copper", "107.3 g/t PGMs", "665g/t AgEq", "0.26 g/t Gold"
# 1.0.4: the unit may be followed by its abbreviation or the value in another unit before the metal ("5.26 grams per tonne
# (g/t) gold", "97 g/t (2.83 opt) Ag")
_UNIT_PAREN = r"(?:\s*\(\s*(?:g/t|gpt|[\d.,]+\s*(?:opt|oz/t|oz/ton|ounces?\s+per\s+(?:short\s+)?ton|g/t|%|ppm|ppb))\s*\))?"
_GRADE_A = re.compile(r"(?<![\w.])" + _NUMV + r"\s*(?:\+\s*)?(" + _UNIT + r")" + _UNIT_PAREN + r"\s*(?:of\s+)?(" + _SYM + r"|" + _METAL_WORDS +
                      r")s?\b(?!-in-)", re.I)
# "gold values of up to 20.6 g/t", "copper grades up to 3.1%", "antimony up to 53.7%"
_GRADE_B = re.compile(r"\b(" + _METAL_WORDS + r"|" + _SYM + r")\b(?:\s+(?:values?|grades?|assays?|concentrations?|results?|contents?))?"
                      r"(?:\s+(?:of|ranging\s+from|returned|returning|reaching|as\s+high\s+as))?(?:\s+(?:[\d.,]+\s*(?:" + _UNIT + r")?\s*"
                      r"(?:to|-)\s*))?(?:\s+up\s+to|\s+of\s+up\s+to|\s+to)?\s+" + _NUMV + r"\s*(" + _UNIT + r")(?!\s*(?:" + _SYM + r")\b)",
                      re.I)
_NOT_GRADE = re.compile(r"(?i)\b(?:recover(?:y|ies)\s+(?:of|rates?|to)?|cut[\s-]?off|threshold|above|greater\s+than|over|exceed\w*|>|\u2265|more\s+than|"
                        r"at\s+least|minimum|interest|ownership|owned|royalty|NSR|stake|equity|IRR|margin|increase|decrease|"
                        r"per\s+cent\s+of\s+the|of\s+the\s+(?:samples|shares)|dilution|confidence|probability|slope|dip|"
                        r"head\s+grade\s+of\s+the\s+resource|resource|reserve|indicated|inferred|measured|probable|proven|"
                        r"cut[\s-]?off|grade\s+control)\s*$")


def _unit(u):
    u = re.sub(r"\s+", " ", u.lower())
    if u.startswith("g") or u.startswith("gram"):
        return "g/t"
    if u in ("opt", "oz/t", "oz/ton") or u.startswith("ounce"):
        return "oz/t"
    if u == "mg/l":
        return "mg/L"
    return u


def _metal(m):
    m = re.sub(r"\s+", " ", (m or "").strip())
    lm = m.lower().rstrip("s") if m.lower() not in ("pgms", "pges") else m.lower()[:-1]
    if lm.endswith("equivalent"):
        return {"gold": "AuEq", "silver": "AgEq", "copper": "CuEq"}.get(lm.split()[0], "Eq")
    if lm == "lithium oxide":
        return "Li2O"
    if lm in METALS:
        return METALS[lm]
    if lm in ("rare earth", "rare earths"):
        return "TREO"
    m = re.sub(r"(?i)\s?-?\s?eq$", "Eq", m)
    if m.upper() in ("PGE", "PGM", "PGES", "PGMS"):
        return m.upper().rstrip("S")
    for s in re.split(r"\|", _SYM.replace("\\+", "+").replace("\\s?", "")):
        if m.lower() == s.lower():
            return s
    return m


# 1.0.4b: threshold wording ("9 samples returned over 5 g/t Au"); a grade after it is kept when the caller asks
_THR_PRE = re.compile(r"(?i)\b(?:above|greater\s+than|over|exceed\w*|more\s+than|at\s+least|in\s+excess\s+of)\s*$")


def _grades(s, thresholds=False):
    """[(pos, value, unit, metal, end)] for every grade written in s, in order. 1.0.4b: with thresholds=True a value
    written after threshold wording ("over 5 g/t Au") is kept too (the row builder flags it and prefers explicit values)."""
    out = []
    for rx, vi, ui, mi in ((_GRADE_A, 1, 2, 3), (_GRADE_B, 2, 3, 1)):
        for m in rx.finditer(s):
            try:
                v = float(m.group(vi).replace(",", ""))
            except ValueError:
                continue
            u = _unit(m.group(ui))
            raw = m.group(mi)
            if not re.match(r"(?i)" + _METAL_WORDS + r"$", raw.strip()) and len(raw.strip()) <= 3 and\
                    not (raw[:1].isupper() and (raw[1:2].islower() or raw.isupper() and (s.isupper() or len(raw) > 2 or
                                                                                          raw in ("AU", "AG", "CU", "ZN", "PB", "NI", "CO",
                                                                                                  "LI", "SB", "MO", "PT", "PD", "SN", "CS")))):
                continue                            # "Results In 20.6 GPT": "In" is a word, not indium
            if raw.strip().lower() in ("in", "as", "b", "be", "co") and not raw[:1].isupper():
                continue
            if raw.strip() in ("In", "As", "B", "Be") and mi == 1 and not re.match(r"\s*(?:values?|grades?|assays?|up\s+to|of)", s[m.end(mi):m.end(mi) + 12], re.I):
                continue
            met = _metal(raw)
            if u == "%" and v > 100:
                continue
            pre = s[max(0, m.start() - 30):m.start()]
            if _NOT_GRADE.search(pre) and not (thresholds and _THR_PRE.search(pre)) or\
                    re.match(r"\s*(?:cut[\s-]?off|recover)", s[m.end():m.end() + 15], re.I):
                continue
            if any(abs(p - m.start()) < 3 or (p <= m.start() < e) or (p <= m.start(vi) < e) for p, *_x, e in out):
                continue                            # "Gold and Silver up to 6.12 g/t Gold": the value is already read
            if met in ("Au", "Ag", "Cu", "Zn", "Ni") and re.match(r"(?i)\s*(?:eq\b|eq\.|equiv\w*)", s[m.end():m.end() + 12]):
                met += "Eq"                                     # "14.60 G/T GOLD EQ"
            out.append((m.start(), v, u, met, m.end()))
    out.sort()
    # "4.06% and 1.60% Copper": the bare first value shares the metal written after the second
    for pos, v, u, met, end in list(out):
        m = re.search(r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(%|g/t|gpt|ppm|ppb)\s*(?:and|&|,|to)\s*$", s[max(0, pos - 30):pos], re.I)
        if m and _unit(m.group(2)) == u:
            st = max(0, pos - 30) + m.start()
            if not any(p <= st < e for p, *_x, e in out):
                out.append((st, float(m.group(1).replace(",", "")), u, met, max(0, pos - 30) + m.end(2)))
    out.sort()
    # the same assay restated in another unit ("1,523.54 g/t Au (44.44 oz/t Au)"): keep the first
    TO_GPT = {"g/t": 1.0, "oz/t": 34.2857, "ppb": 0.001, "ppm": 1.0}
    drop = set()
    for i, (p1, v1, u1, m1, e1) in enumerate(out):
        for j in range(i + 1, len(out)):
            p2, v2, u2, m2, e2 = out[j]
            if p2 - e1 > 25:
                break
            if u1 != u2 and u1 in TO_GPT and u2 in TO_GPT and m1 == m2 and v1 and v2 and\
                    abs(v1 * TO_GPT[u1] - v2 * TO_GPT[u2]) <= 0.03 * v1 * TO_GPT[u1] and "(" in s[e1:p2 + 1]:
                drop.add(j)
    return [g for k, g in enumerate(out) if k not in drop]


_LEN = r"(\d+(?:\.\d+)?)\s*(m|metres?|meters?|ft|feet|foot|cm)\b"
_INTERVAL_A = re.compile(r"(?i)" + _LEN + r"\s*(?:\([^)]{0,20}\)\s*)?(?:of|@|at|grading|averaging|returning|with|:)\s+(?:an?\s+average\s+(?:of\s+)?)?")
_INTERVAL_B = re.compile(r"(?i)\s*(?:over|across|along)\s+(?:a\s+(?:true\s+width|length|width)\s+of\s+)?" + _LEN)


def _metres(v, u):
    u = u.lower()
    if u.startswith("f"):
        return round(v * 0.3048, 2)
    if u == "cm":
        return round(v / 100.0, 2)
    return v


def _width_for(s, gpos, gend):
    """The length written with the grade at [gpos, gend): '9.4 m grading 7.4 g/t' or '7.4 g/t over 9.4 m'."""
    for m in _INTERVAL_A.finditer(s[max(0, gpos - 45):gpos]):
        if m.end() + max(0, gpos - 45) >= gpos - 1:
            v = float(m.group(1))
            if 0 < v < 1000:
                return _metres(v, m.group(2))
    m = _INTERVAL_B.match(s[gend:gend + 45])
    if m:
        v = float(m.group(1))
        if 0 < v < 1000:
            return _metres(v, m.group(2))
    m = re.match(r"(?i)\s*(?:" + _SYM + r"|" + _METAL_WORDS + r"|,|\s|and|\+|\d|\.|g/t|%|ppm)*?\s*\(?(?:over|across)\s+" + _LEN,
                 s[gend:gend + 90])
    if m:
        v = float(m.group(1))
        if 0 < v < 1000:
            return _metres(v, m.group(2))
    return None


# ------------------------------------------------------------------ sample types
_P = lambda s: re.compile(s, re.I)  # noqa: E731
TYPE_CUES = [
    ("bulk", _P(r"\bbulk[\s-]sampl\w*|\bbulk\s+samples?\b|\bmini[\s-]bulk\b")),
    ("brine", _P(r"\bbrines?\b")),
    ("trench", _P(r"\btrench(?:es|ing|ed)?\b(?!\s+(?:rock|grab|float|select(?:ed)?|composite)\s+samples?)")),
    ("channel", _P(r"\bchannel(?:s|led)?\s*(?:samples?|sampling|cuts?|results?|assays?|\w{0,3}\d|[A-Z]{1,3}-?\d)?\b(?![\s-]+(?:width|length|river))|\bpanel\s+samples?\b|\bchip[\s-]channel\b")),
    ("chip", _P(r"(?<!rock\s)(?<!rock-)\bchip\s+(?:samples?|sampling|results?)\b|(?<!rock\s)(?<!rock-)\bchip\s+sample\w*\b|"
                r"\bcontinuous\s+chip\b")),
    ("grab", _P(r"\b(?:grab|float|boulder|outcrop|subcrop|rock|rock[\s-]chip|dump|talus|character)\s+(?:and\s+\w+\s+)?"
                r"(?:samples?|sampling|assays?|results?|geochemistry)\b|\bselect(?:ed)?\s+(?:grab\s+|rock\s+)?(?:samples?|sampling)\b|\bgrabs?\b|\bprospecting\s+samples?\b|\brock\s+samples?\b|"
                r"\bsurface\s+(?:rock\s+)?samples?\b|\bsampled\s+(?:outcrop|float|boulders?)\b|\b(?:glacial\s+)?float\s+boulders?\b|"
                r"\bsamples?\s+(?:taken\s+)?from\s+(?:glacial\s+)?(?:float|outcrop|subcrop)\b|"
                r"\b(?:from|of|in|quartz|mineralized|mineralised|angular)\s+float\b|"
                # 1.0.4: boulders found and assayed ("high-grade gold-bearing boulders", "this boulder graded 28.7 g/t Au")
                r"\b(?:high[\s-]grade|mineralized|mineralised|gold[\s-]bearing|radioactive|uraniferous|erratic|angular|"
                r"new|discovery)\s+(?:[\w-]+\s+){0,2}?boulders?\b|\bboulders?\s+(?:graded|assayed|returned|yielded|grading)\b")),
    ("till", _P(r"\btill\b|\bheavy[\s-]mineral\w*|\bgold[\s-]grains?\b(?!\s+size)|\bgrain\s+counts?\b|\bindicator\s+minerals?\b|\bKIMs?\b")),
    ("sediment", _P(r"\b(?:stream|lake|creek)[\s-]sediment\w*|\bBLEG\b|\bsilt\s+samples?\b|\bpan\s+concentrates?\b")),
    ("soil", _P(r"\bsoils?\b|\bsoil[\s-]gas\b|\bB[\s-]horizon\b|\bMMI\b|\bgold[\s-]in[\s-]soil\b|\bin[\s-]soils?\b")),
    ("other_geochem", _P(r"\bbiogeochem\w*|\b(?:tree|bark|needle|twig|conifer|spruce|fir)\s+(?:bark\s+|twig\s+)?(?:samples?|sampling|clippings?)\b|"
                         r"\blithogeochem\w*|\bvegetation\s+samples?\b|\bwater\s+samples?\b|\bhydrogeochem\w*")),
    ("geophysics", _P(r"\bgeophysic\w*|\b(?-i:IP|EM|MT|TDEM|MLEM|HLEM|VLF|UAV|ASTER)\b|\binduced[\s-]polari[sz]ation|\bchargeabilit\w+|\bresistivit\w+|\bmagnetic\w*|\bmag\b|"
                      r"\bmagnetometer|\bVTEM\w*|\bZTEM\w*|\belectromagnetic\w*|\bconductors?\b|"
                      r"\bconductiv\w+|\bmagnetotelluric\w*|\bMobileMT\b|\bgravity\b|\bradiometric\w*|\bspectrometer|\bLiDAR\b|"
                      r"\bhyperspectral\b|\bremote[\s-]sensing\b|\bsatellite\b|\bseismic\b|\bdrone[\s-]?(?:borne\s+)?mag|"
                      r"\bgradiometer\b|\bgamma[\s-]ray\b|\bair[\s-]?borne\s+survey|\bground\s+survey")),
    ("mapping", _P(r"\b(?:geological\s+)?mapping\b|\bprospecting\b|\breconnaissance\b|\bmapped\b")),
]
TCUE = dict(TYPE_CUES)
SURVEY = [("remote_sensing", _P(r"\bremote[\s-]sensing\b|\bsatellite\b|\b(?-i:ASTER)\b|\bWorldView\b|\bSentinel\b|\bLandsat\b")),
          ("hyperspectral", _P(r"\bhyperspectral\b")),
          ("MT", _P(r"\b(?-i:MT|CSAMT|AMT)\b|\bmagnetotelluric\w*|\bMobileMT\b")),
          ("IP", _P(r"\b(?-i:IP)\b|\binduced[\s-]polari[sz]ation|\bchargeabilit\w+|\bresistivit\w+|\bDCIP\b")),
          ("EM", _P(r"\bVTEM\w*|\bZTEM\w*|\b(?-i:TDEM|MLEM|HLEM|EM|FLEM|VLF)\b|\belectromagnetic\w*|\bconductors?\b|"
                    r"\bHeliTEM\b|\bSkyTEM\b|\bconductiv\w+")),
          ("magnetics", _P(r"\bmagnetic\w*|\bmag\b|\bmagnetometer|\bgradiometer\b|\bdrone[\s-]?(?:borne\s+)?mag")),
          ("gravity", _P(r"\bgravity\b")),
          ("radiometric", _P(r"\bradiometric\w*|\bspectrometer|\bgamma[\s-]ray\b")),
          ("lidar", _P(r"\bLiDAR\b")),
          ("seismic", _P(r"\bseismic\b"))]
_GEOPHYS_NOISE = re.compile(r"(?i)\bmagnetite\b|\bmagnetic\s+(?:separation|susceptibility\s+meter|concentrate|fraction|north)\b|"
                            r"\bnon[\s-]magnetic\b|\bconductor\s+(?:of|for)\s+(?:the\s+)?(?:project|board)\b|\bsatellite\s+(?:deposits?|"
                            r"zones?|pits?|targets?|bodies|mineralization|showings?)\b|"
                            r"\bgravity\s+(?:plant|circuit|concentrat\w*|separation|recover\w*|tables?|gold|fraction|feed)\b")


# 1.0.4: a capitalised cue followed by a place noun is part of a name, not a sample type
_NAME_TAIL = re.compile(r"\s*(?:[A-Z][\w'-]*\s+){0,2}(?i:projects?|property|properties|claims?|prospects?|showings?|deposits?|lakes?|"
                        r"rivers?|creeks?|bay|mine)\b")


def _types_in(s):
    """[(pos, type)] for every sample-type cue in s (grab cues that are part of a chip/channel/trench phrase dropped)."""
    out = []
    for t, rx in TYPE_CUES:
        for m in rx.finditer(s):
            if t == "geophysics" and _GEOPHYS_NOISE.search(s[max(0, m.start() - 20):m.end() + 25]):
                continue
            if t in ROCK + GEOCHEM and m.group(0)[:1].isupper() and not s.isupper() and _NAME_TAIL.match(s, m.end()):
                continue                                    # 1.0.4: a place name ("Pine Channel Project", "Soil Lake property")
            if t == "grab" and re.search(r"(?i)rock[\s-]chip", m.group(0)) and re.search(r"(?i)\bover\s+\d|\d\s*m\s+(?:of|@|at)\b",
                                                                                         s[m.end():m.end() + 80]):
                t2 = "chip"
            else:
                t2 = t
            if t2 == "till" and re.search(r"(?i)\bsoils?\b", s) and not re.search(r"(?i)\btill\s+(?:samples?|sampling|survey|"
                                                                                 r"geochem\w*|program|results?)\b|\bgold[\s-]grains?\b",
                                                                                 s) and\
                    re.search(r"(?i)\btill[\s-]+(?:material|cover\w*|overburden|blanket|deposits?|plain)\b|\b(?:samples?|soils?|"
                              r"taken|collected)\s+(?:\w+\s+){0,2}(?:in|from|on|over)\s+(?:the\s+)?(?:glacial\s+|thin\s+|thick\s+)?till\b",
                              s):
                continue                                    # "soil samples taken in till material"
            out.append((m.start(), t2))
    out.sort()
    # "chip-channel", "channel ... in trenches": the more specific wins at the same place
    # 1.0.1: "channel chip" / "chip-channel" samples are one chip sample set (guide: chip covers chip-channel)
    fixed = []
    for p, t in out:
        if t == "channel" and (re.match(r"(?i)(?:channel[\s-]+chips?|chip[\s-]+channel)\b", s[p:p + 20]) or
                               re.search(r"(?i)\bchips?[\s-]+$", s[max(0, p - 8):p])):
            t = "chip"                                  # 1.0.4: also "outcrop chip channel samples"
        if t == "chip" and any(q == "chip" and abs(q0 - p) <= 16 for q0, q in fixed):
            continue
        fixed.append((p, t))
    return fixed


# 1.0.3: auger holes are drilling (guide: "core, RC chips, sonic or auger holes are drilling"); a soil auger is the tool a
# soil survey samples a horizon with ("collected using dutch augers targeting the B horizon")
_AUGER_RES = re.compile(r"(?i)\bauger\s+(?:assays?|results?|samples?|sampling|drill\w*|holes?|values?|composites?|intervals?|"
                        r"intercepts?|program\w*)\b|\b(?:power|mechani[sz]ed)\s+auger\b(?!\s+soil)")
_AUGER_TOOL = re.compile(r"(?i)\b(?:soil|dutch|hand|hang|bucket)[\s-]+augers?\b|\baugers?\s+soil\b|\b(?:using|with|by)\s+(?:an?\s+)?(?:[\w-]+\s+){0,2}?"
                         r"augers?\b(?!\s+(?:drill\w*|holes?|rigs?))")


# 1.0.3: a project name is no sentence: a capitalised headline verb in it marks a headline fragment
_HL_VERB_IN_NAME = (r"\b(?:Purchases|Acquires|Announces|Reports|Signs|Options|Completes|Provides|Receives|Begins|Commences|"
                    r"Intersects|Drills|Samples|Discovers|Expands|Extends|Identifies|Confirms|Returns|Closes|Enters|Stakes)\b")
# 1.0.3: grades quoted for the known occurrences a property hosts ("the claims are host to approximately 40 nickel-copper
# occurrences with grab sample values up to 4615 ppm nickel") describe earlier finds, not this release's sampling
_KNOWN_OCC = re.compile(r"(?i)\b(?:is|are)\s+host(?:s|ed)?\s+to\s+(?:approximately\s+|about\s+|over\s+|more\s+than\s+|numerous\s+|"
                        r"several\s+|many\s+|\d+\s+)+(?:[\w-]+\s+){0,3}?(?:occurrences|showings|prospects)\b|"
                        r"\bknown\s+(?:mineral\s+)?(?:occurrences|showings)\s+(?:on\s+the\s+\w+\s+)?include\b")


# 1.0.3: a list of rock-sample kinds that share one noun ("chip, channel and grab samples", "channel and chip sample
# highlights"): one sample set
_ROCK_LIST_W = r"\b(?:grab|chip|channel|trench|rock|outcrop|float|boulder)\b"
# 1.0.4: also "selective grab samples and some chip samples"
_ROCK_LIST = re.compile(r"(?i)(?:rock[\s-]+)?" + _ROCK_LIST_W + r"(?:\s+samples?)?(?:\s*,\s*" + _ROCK_LIST_W + r"(?:\s+samples?)?)*\s*,?\s*"
                        r"(?:and|&|or)\s+(?:some\s+|other\s+|several\s+|a\s+few\s+)?" + _ROCK_LIST_W + r"\s+(?:samples?|sampling)\b")
_ROCK_WORD = {"grab": "grab", "chip": "chip", "channel": "channel", "trench": "trench"}


def _method_found(sents, method):
    """1.0.3: a survey method has a result of its own: its cue sits next to a finding (an anomaly, conductor, high or low,
    trend, lineament, structure, response or target) in a sentence that is not only a list of the survey's instruments
    and parameters ("flown with a magnetometer, VLF-EM receiver and gamma-ray spectrometer at 100 m line spacing")."""
    rx = dict(SURVEY).get(method)
    if rx is None:
        return True
    for s in sents:
        for m in rx.finditer(s):
            win = s[max(0, m.start() - 70):m.end() + 90]
            verb = re.search(r"(?i)\b(?:identif\w+|outlin\w+|delineat\w+|reveal\w+|defin\w+|detect\w+|mapped|show\w*|"
                             r"indicat\w+|highlight\w*)\b", win)
            noun = re.search(r"(?i)\b(?:anomal\w*|conductors?|conductive\s+(?:zones?|bodies|trends?|features?)|highs?|lows?|"
                             r"trends?|lineaments?|structures?|features?|responses?|signatures?|targets?|breaks?|faults?|"
                             r"contacts?)\b", win)
            gear = re.search(r"(?i)\b(?:equipped|consist\w*|compris\w*|instruments?|sensors?|receivers?|spectrometers?|"
                             r"spectrometry|magnetometers?|parameters?|line[\s-]spacing|recorded|acquired\s+using|flown\s+(?:at|"
                             r"with|using))\b", win)
            if verb or noun and not gear:
                return True
    return False


def _survey(s):
    """The geophysical method written first in s."""
    best = None
    for name, rx in SURVEY:
        for m in rx.finditer(s):
            if _GEOPHYS_NOISE.search(s[max(0, m.start() - 20):m.end() + 25]):
                continue
            if best is None or m.start() < best[0]:
                best = (m.start(), name)
            break
    return best[1] if best else "other"


# ------------------------------------------------------------------ what is not a result
_DRILL = re.compile(r"(?i)\bdrill\w*\b|\bhits\b|\boff-scale\b|\bradioactivity\b|\bholes?\b|\bDDH\b|\bintersect\w*\b|\bintercept\w*\b|\bcore\b|\bdownhole\b|\bRC\b|"
                    r"\breverse\s+circulation\b|\bsonic\b|\bauger\b|\b[A-Z]{1,5}[-_]?\d{2}[-_]\d{1,4}[A-Z]?\b|\bfrom\s+\d[\d.,]*\s*(?:m|metres)?\s+to\s+\d")
_PLAN = re.compile(r"(?i)\b(?:will\s+(?:be|begin|commence|start|include|focus|consist|test|follow|continue|comprise|target|undertake|"
                   r"complete|conduct|carry)|plans?\s+to|planned|planning|to\s+be\s+(?:collected|conducted|completed|carried|"
                   r"undertaken|sent|submitted|analy[sz]ed|assayed)|proposed|intends?\s+to|expect\w*\s+(?:to|in|by|shortly|soon)|"
                   r"scheduled|upcoming|next\s+(?:phase|step|season)|in\s+the\s+coming|pending|await\w*|outstanding|"
                   r"(?:are|is|were|was|have\s+been|has\s+been)\s+(?:being\s+)?(?:sent|submitted|shipped|delivered|dispatched)\s+(?:to|for)|"
                   r"commenc\w+|mobiliz\w+|mobilis\w+|underway|under\s+way|initiat\w+|launch\w*|begun|began|begins?|starts?|started|"
                   r"in\s+progress|ongoing|budget\w*|permit\w*|application)\b")
_RESULT = re.compile(r"(?i)\b(?:return\w*|yield\w*|assay\w*|grad(?:e|ed|ing)|results?|highlights?|values?|anomal\w+|conductors?|"
                     r"identif\w+|outlin\w+|defin\w+|delineat\w+|reveal\w+|confirm\w+|discover\w+|up\s+to|high\s+of|peak|"
                     r"averag\w+|report\w*|received|contain\w*|includ\w+|range|ranging|maximum|best|high[\s-]grade|elevated|"
                     r"significant|strong|coincident|trends?|zones?|targets?|showings?)\b")
_RESTATED = re.compile(r"(?i)\b(?:previously\s+(?:announced|reported|disclosed|released|published)|as\s+(?:previously\s+)?"
                       r"(?:announced|reported|disclosed)\s+(?:on|in)|(?:news|press)\s+releases?\s+(?:dated|of|on|issued)|see\s+(?:the\s+)?"
                       r"(?:company'?s?\s+)?(?:news|press)\s+release|reported\s+(?:on|in)\s+(?:" + T._MON + r"|(?:19|20)\d\d)|"
                       r"announced\s+(?:on|in)\s+(?:" + T._MON + r"|(?:19|20)\d\d)|(?:reported|announced|released|disclosed)\s+(?:\w+\s+){0,2}?"
                       r"(?:last|earlier\s+this)\s+(?:year|month|season)|(?:last|earlier\s+this)\s+(?:year|month|season)\s*(?:,\s*)?"
                       r"(?:\w+\s+){0,3}?(?:reported|announced|released|disclosed)|"
                       r"(?:19|20)\d\d\s+(?:news|press)\s+release|"
                       # 1.0.2: the past perfect places a result before this release ("initial sampling had returned 109 g/t")
                       r"had\s+(?:previously\s+)?(?:returned|yielded|assayed|graded|produced|outlined|defined|identified))")
_HIST = re.compile(r"(?i)\bhistoric(?:al|ally)?\s+(?:\w+\s+){0,2}(?:samples?|sampling|results?|assays?|grab|rock|chip|channel|"
                   r"trench\w*|soil|till|stream|sediment|silt|geochem\w*|geophysic\w*|surveys?|work|data|exploration|values?|"
                   r"prospecting|anomal\w+|grades?)\b|\bhistorically\b|\bprevious(?:ly)?\s+(?:operators?|owners?|explorers?|companies|operator)|"
                   r"\b(?:operators?|owners?)\s+of\s+the\s+(?:property|project)\s+in\b|\bprior\s+(?:operators?|owners?|work|exploration)|\bgovernment\s+(?:survey|"
                   r"geolog\w+|sampling|data)|\bgeological\s+surveys?\s+(?:of|branch)\b|\b(?:GSC|OGS|BCGS|MERN|MRNF|USGS)\b|\bminfile\b|\bassessment\s+"
                   r"(?:reports?|files?|work)\b|\bcompil\w+\s+(?:of\s+)?(?:historical|previous|past|existing)|\bin\s+(?:19[0-9]\d)\b|"
                   r"\b(?:19[0-9]\d)s\b|\bduring\s+the\s+(?:19|20)\d0s\b|\blegacy\s+data\b|"
                   # 1.0.3: "the 1981 regional stream sampling program"
                   r"\bthe\s+19[0-9]\d\s+(?:[\w-]+\s+){0,3}?(?:programs?|surveys?|sampling|campaigns?)\b|"
                   r"\bprevious\s+(?:work|exploration|(?:rock\s+|grab\s+|surface\s+|soil\s+)*sampling)\s+(?:at|on|by|in|has|have|returned|"
                   r"identified|discovered)\b|"
                   # 1.0.1: "previous workers collected", "government rock sample results", "(Allen, 1982)"
                   r"\b(?:previous|prior|past|earlier|former)\s+(?:workers|explorers|prospectors|geologists|operators?|owners?|"
                   r"optionors?|companies|programs?\s+by)\b|\bgovernment\s+(?:\w+\s+){0,2}(?:samples?|sampling|surveys?|data|results?|"
                   r"geolog\w+|assays?)\b|\((?!(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b)[A-Z][\w.&'-]*"
                   r"(?:\s+(?:[A-Z][\w.&'-]*|and|&|et\s+al\.?)){0,4},\s+(?:19|20)\d\d[a-z]?\)")
_NEIGHBOUR = re.compile(r"(?i)\b(?:adjacent|adjoin\w*|neighbou?r\w*|nearby|along\s+strike\s+from|next\s+to|bordering)\b[^.]{0,60}"
                        r"\b(?:property|properties|project|claims?|mine|company|companies)\b")
_MAPPING_FIND = re.compile(r"(?i)\b(?:identif\w+|discover\w+|outlin\w+|delineat\w+|traced|trac\w+\s+for|confirm\w+|mapped|"
                           r"extend\w*|expand\w*|reveal\w+|located|found|exposed|uncover\w+|recogni[sz]\w+|documented)\b")
_MAPPING_THING = re.compile(r"(?i)\b(?:showings?|outcrops?|pegmatites?|dykes?|dikes?|veins?|vein\s+systems?|zones?|structures?|"
                            r"shears?|shear\s+zones?|alteration|gossans?|breccias?|mineraliz\w+|mineralis\w+|skarns?|stockworks?|"
                            r"faults?|contacts?|intrusions?|intrusives?|occurrences?)\b")
_ANOM_KIND = [("conductor", _P(r"\bconductors?\b|\bconductive\s+(?:zones?|trends?|bodies|body|axes|axis|horizons?)\b")),
              ("trend", _P(r"\btrends?\b|\bcorridors?\b|\bbelts?\b")),
              ("zone", _P(r"\bzones?\b")),
              ("anomaly", _P(r"\banomal(?:y|ies|ous)\b|\bchargeability\s+(?:highs?|features?)\b|\blows?\b|\bhighs?\b|\btargets?\b"))]
_DIM2 = re.compile(r"(?i)(\d[\d,]*(?:\.\d+)?)\s*(m|metres?|meters?|km|kilometres?|kilometers?)?\s*(?:long\s+)?(?:by|x|\u00d7)\s*"
                   r"(?:up\s+to\s+)?(\d[\d,]*(?:\.\d+)?)\s*(m|metres?|meters?|km|kilometres?|kilometers?)\b")
_DIM1 = re.compile(r"(?i)(?:(?:strike\s+)?length\s+of|(?:over|for|across|along|extends?|extending|measur\w+|spans?|spanning|covers?|"
                   r"covering|up\s+to|approximately|about|~|>|more\s+than|over\s+a)\s+(?:a\s+)?(?:distance\s+of\s+|strike\s+length\s+of\s+|"
                   r"length\s+of\s+)?(?:approximately\s+|about\s+|over\s+|more\s+than\s+|~)?)(\d[\d,]*(?:\.\d+)?)\s*(m|metres?|meters?|km|"
                   r"kilometres?|kilometers?)\b|(\d[\d,]*(?:\.\d+)?)\s*[-\s]?(m|metres?|meters?|km|kilometres?|kilometers?)[\s-]+"
                   r"(?:long|in\s+length|strike|by|wide\s+and)\b")
_ANOM_METAL = re.compile(r"(?i)\b(" + _METAL_WORDS + r"|" + _SYM + r")[\s-]+in[\s-]+(?:soils?|till|sediments?|rock)\b|\b(" + _METAL_WORDS +
                         r"|" + _SYM + r")\s+(?:\w+\s+)?(?:geochemical\s+|soil\s+|till\s+)?anomal\w+|\banomal\w+\s+(?:in|of|for)\s+(" +
                         _METAL_WORDS + r"|" + _SYM + r")\b")
_COUNT = re.compile(r"(?i)(?:\btotal\s+of\s+|\b)(\d{1,3}(?:,\d{3})+|\d+)\s+(?:additional\s+|new\s+|surface\s+|outcrop\s+|B[\s-]horizon\s+|"
                    r"reconnaissance\s+|prospecting\s+|field\s+|individual\s+)*(?:(?:rock|grab|chip|channel|trench|soil|till|stream[\s-]sediment|"
                    r"sediment|silt|BLEG|brine|biogeochemical|tree|bark|float|boulder|outcrop|select(?:ed)?|character|dump|talus|"
                    r"composite|surface|lithogeochemical|heavy\s+mineral)\s*(?:and\s+\w+\s+|,\s*\w+\s+)?)+samples?\b")
_WORDNUM = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
            "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
            "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}
_COUNT_W = re.compile(r"(?i)\b(" + "|".join(_WORDNUM) + r")\s+(?:\w+\s+){0,2}(?:rock|grab|chip|channel|trench|soil|till|brine|float|"
                      r"boulder|outcrop|select|surface|composite|sediment)?\s*samples?\b")
_LINEKM = re.compile(r"(?i)(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?:line[\s-]?(?:km|kilometres?|kilometers?)|l-?km)\b")
_TONNES = re.compile(r"(?i)(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?:-\s*)?(?:dry\s+|wet\s+|metric\s+)?(?:tonnes?|t)\b(?!\s*/)")


def _num(x):
    return float(x.replace(",", ""))


_DIM_LW = re.compile(r"(?i)(\d[\d,]*(?:\.\d+)?)\s*(m|metres?|meters?|km|kilometres?|kilometers?)[\s-]+(?:long|in\s+length)\s*(?:,|and|by|x)\s*"
                     r"(?:up\s+to\s+|approximately\s+|about\s+)?(\d[\d,]*(?:\.\d+)?)\s*(m|metres?|meters?|km|kilometres?|kilometers?)[\s-]+wide")


def _metal_ok(tok):
    t = tok.strip()
    if re.match(r"(?i)(?:" + _METAL_WORDS + r")$", t):
        return True
    return len(t) > 3 or (t[:1].isupper() and (t[1:2].islower() or not t[1:2]) and t not in ("In", "As", "B", "Be"))


def _km(v, u):
    return _num(v) * (1000 if u.lower().startswith("k") else 1)


def _anomaly(texts, stype):
    """{'kind', 'metal', 'length_m', 'width_m'} from the row's sentences (headline first), or None."""
    kind = metal = None
    length = width = None
    for s in texts:
        if kind is None:
            for k, rx in _ANOM_KIND:
                if rx.search(s):
                    if k == "zone" and not re.search(r"(?i)\banomal|\bconduct|\bchargeab|\bsoil|\btill|\bgeochem|\bgeophys", s):
                        continue
                    if k == "anomaly" and re.search(r"(?i)\btargets?\b", s) and not re.search(r"(?i)\banomal|\bchargeab|\bhighs?\b|\blows?\b", s):
                        if stype != "geophysics":
                            continue
                    kind = k
                    break
        if metal is None and stype != "geophysics":
            for m in _ANOM_METAL.finditer(s):
                tok = m.group(1) or m.group(2) or m.group(3)
                if _metal_ok(tok):
                    metal = _metal(tok)
                    break
        if length is None:
            m = _DIM2.search(s) or _DIM_LW.search(s)
            if m:
                a, ua, b2, ub = m.group(1), m.group(2) or m.group(4), m.group(3), m.group(4)
                length, width = _km(a, ua), _km(b2, ub)
                if width > length:
                    length, width = width, length
            else:
                for m in _DIM1.finditer(s):
                    v, u = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
                    val = _km(v, u)
                    ctx = s[max(0, m.start() - 70):m.end() + 40]
                    if re.search(r"(?i)\b(?:line|spacing|spaced|grid|depth|deep|below|elevation|altitude|flight|intervals?|"
                                 r"station|from\s+the|away|south|north|east|west|of\s+the\s+(?:main|known)|over\s+\d[\d.,]*\s*m\s+"
                                 r"(?:of|@|at|grading))\b", ctx) and not re.search(r"(?i)\banomal|\bconductor|\btrend|\bzone\b|\bstrike", ctx):
                        continue
                    if re.search(r"(?i)\bg/t|\bgpt|%\s*(?:Cu|Zn|Li)", s[m.end():m.end() + 25]):
                        continue                            # "44 metres of 0.42 g/t": an interval, not a size
                    if re.search(r"(?i)\banomal|\bconductor|\btrend|\bzone|\bstrike|\bcorridor|\bfootprint|\blong\b", ctx):
                        length = val
                        mw = re.search(r"(?i)(?:and|,|by|up\s+to)\s+(\d[\d,]*(?:\.\d+)?)\s*(m|metres?|meters?|km)\s+wide", s[m.end():m.end() + 50])
                        if mw:
                            width = _km(mw.group(1), mw.group(2))
                        break
    if kind is None and metal is None and length is None:
        return None
    return {"kind": kind or "anomaly", "metal": metal, "length_m": length, "width_m": width}


_UNITS_W = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
            "eighteen": 18, "nineteen": 19}
_TENS_W = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_NUMWORD = r"(?:(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[\s-](?:one|two|three|four|five|six|seven|eight|nine))?|" \
           r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|" \
           r"eighteen|nineteen)"
_CNT = re.compile(r"(?i)(?<![\w.$/-])(\d{1,3}(?:,\d{3})+|\d{1,6}|" + _NUMWORD + r")(?:\s*\(\d+\))?[\s-]+"
                  r"((?:[\w-]+[\s,]+){0,5}?)(?:samples?|sample\s+results|assays?|assay\s+results|sites)\b|"
                  r"\((?:N|n)\s*=\s*(\d{1,5})\)")
_CNT_KIND = [("brine", r"brine"), ("till", r"\btill\b|heavy\s+mineral|glacial"), ("sediment", r"sediment|silt|bleg|stream"),
             ("other_geochem", r"biogeochem|tree|bark|clipping|vegetation|lithogeochem"), ("soil", r"soils?\b|b[\s-]horizon"),
             ("trench", r"trench"), ("channel", r"channel"), ("chip", r"\bchip"),
             ("grab", r"\bgrab|\brock|\bfloat|\boutcrop|\bboulder|\bselect|\bprospecting|\bsubcrop|\bdump|\btalus|\bsurface")]


def _wordnum(w):
    w = w.lower().replace(",", "")
    if w.isdigit():
        return int(w)
    parts = re.split(r"[\s-]+", w)
    v = 0
    for x in parts:
        v += _TENS_W.get(x, 0) + _UNITS_W.get(x, 0)
    return v or None


def _counts(texts):
    """[(kind or None, value)] for every sample count written in texts, in order."""
    out = []
    for s in texts:
        for m in _CNT.finditer(s):
            if m.group(3):
                v, mid = int(m.group(3)), ""
                ctx = s[max(0, m.start() - 60):m.start()].lower()
            else:
                v, mid = _wordnum(m.group(1)), (m.group(2) or "").lower()
                ctx = mid + " " + s[max(0, m.start() - 25):m.start()].lower()
            if not v or v > 100000 or v < 1:
                continue
            if 1900 <= v <= 2099 and "," not in (m.group(1) or ""):
                continue                            # "2022 sampling program": a year
            if m.group(1) and v >= 10000 and "," not in m.group(1):
                continue                            # 1.0.6 (FIX8): "36105-25-66", "Sample 29143": a sample number, not a count
            if m.group(1) and m.group(1).lower() == "one":
                continue
            pre = s[max(0, m.start() - 14):m.start()].lower()
            post = s[m.end():m.end() + 45].lower()
            if re.search(r"(?:\bof|\bwhich|\bwith|\bincluding|\bto|\bfrom|\bthan|>|<|\bthe\s+first|\bof\s+the)\s*$", pre) and\
                    not re.search(r"(?:total\s+of|first|batch\s+of)\s*$", pre):
                continue                            # "14 of 23 samples": the 23 is its own match
            if re.match(r"\s*(?:returned|assayed|graded|yielded|ran|contained|reported|had|showed|were\s+above|exceed\w*)\s+"
                        r"(?:>|greater|above|over|more|values?\s+(?:above|over|greater)|in\s+excess)", post):
                continue                            # a count above a threshold
            if re.search(r"(?i)\bsites\b", m.group(0)) and not re.search(r"(?i)\bsampl", s[m.end():m.end() + 30]):
                continue
            if re.search(r"(?i)\b(?:hole|holes|drill|core|metres?\s+of\s+core)\b", mid):
                continue
            if re.match(r"(?i)(?:ppb|ppm|g/t|gpt|g\s|grams?|%|oz|opt|mg/l|kg|tonnes?|t\s|m\s|metres?|meters?|km|ft|feet)", mid):
                continue                            # "3,530 ppb Au from a sample": a value, not a count
            kind = None
            for k, rx in _CNT_KIND:
                if re.search(rx, mid or ctx):
                    kind = k
                    break
            if kind is None and mid == "" and m.group(3) is None:
                kind = None
            near = s[max(0, m.start() - 50):m.end() + 50].lower()
            score = (3 if re.search(r"total|comprised|consist|collected|taken|analy[sz]|results\s+(?:from|for|of)|assay\s+results|"
                                    r"received|program\s+(?:of|included)|survey\s+(?:of|included)|batch", near) else 0) +\
                (1 if kind else 0) - (2 if v <= 2 else 0)
            out.append((kind, v, s, score))
        m = re.search(r"(?i)\b\d+\s+of\s+(?:the\s+)?(\d{1,3}(?:,\d{3})+|\d+)\s+((?:[\w-]+\s+){0,3})samples?\b", s)
        if m:
            kind = next((k for k, rx in _CNT_KIND if re.search(rx, (m.group(2) or "").lower())), None)
            out.append((kind, int(_num(m.group(1))), s, 3))
    return out


def _count(texts, stype, rock_types=()):
    """The sample count for a row: the best-supported count of that type (a total, a collection), else a generic count
    in a sentence about that type when nothing else competes."""
    cs = _counts(texts)
    typed = [c for c in cs if c[0] == stype]
    if typed:
        best = max(typed, key=lambda c: c[3])
        return best[1] if best[3] >= 1 else None
    gen = [c for c in cs if c[0] is None and c[3] >= 3]
    if stype in ("chip", "channel", "trench"):
        gen = [c for c in gen if re.search(r"(?i)\b" + stype + r"|\btrench", c[2])]
    elif stype == "grab":
        if any(t != "grab" for t in rock_types):
            return None
        gen = [c for c in gen if not re.search(r"(?i)\bsoil|\btill\b|\bsediment|\bchannel|\btrench|\bbrine", c[2])]
    elif stype in GEOCHEM:
        w = {"soil": "soil", "till": "till", "sediment": "sediment|silt|bleg", "other_geochem": "biogeochem"}[stype]
        gen = [c for c in gen if re.search(r"(?i)\b(?:" + w + ")", c[2]) and not re.search(r"(?i)\brock|\bgrab|\bchannel|\btrench", c[2])]
    elif stype == "brine":
        gen = [c for c in gen if re.search(r"(?i)\bbrine", c[2])]
    else:
        gen = []
    vals = {c[1] for c in gen}
    return gen[0][1] if len(vals) == 1 else None


# ------------------------------------------------------------------ the analysis
def _issuer(b):
    ms = list(re.finditer(r"([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5})\s*(?:Inc|Corp|Ltd|Limited|Corporation|plc|Plc)?\.?,?\s*\(\s*(?:[\"\u201c]|"
                          r"the\s+[\"\u201c]|(?:TSXV?|TSX-V|CSE|NYSE|NEO|OTCQX|OTCQB|ASX|LSE|AIM)\b)", b[:1500]))
    return ms[0].group(1) if ms else None


def _abbrev(a, b):
    """'JPR Property' and 'JP Ross Property': the short name's letters are the long one's initials."""
    if not a or not b:
        return False
    if PN.same(a, b):
        return True
    wa = [w for w in re.findall(r"[A-Za-z][\w'-]*", a) if w.lower() not in ("project", "property", "claims", "mine")]
    wb = [w for w in re.findall(r"[A-Za-z][\w'-]*", b) if w.lower() not in ("project", "property", "claims", "mine")]
    for x, y in ((wa, wb), (wb, wa)):
        if len(x) == 1 and x[0].isupper() and len(y) >= 2:
            ini = "".join(w[0] for w in y).upper()
            if x[0] == ini or x[0] == "".join(w if w.isupper() else w[0] for w in y).upper():
                return True
    return False


def _row_type_for(s, pos_types, gpos, gend=None):
    """The sample type a grade at gpos in s belongs to: the nearest cue before it, else the nearest after.
    1.0.4: a grade written before its own sample ("17.60 g/t Au from an outcrop grab sample") takes that sample's kind."""
    if gend is not None:
        after = [(p, t) for p, t in pos_types if p >= gend and t != "mapping"]
        if after and _GRADE_FROM.match(s[gend:after[0][0]]):
            return after[0][1]
    before = [(p, t) for p, t in pos_types if p <= gpos and t != "mapping"]
    if before:
        return before[-1][1]
    after = [(p, t) for p, t in pos_types if p > gpos and t != "mapping"]
    return after[0][1] if after else None


# 1.0.4: words that make a headline sample type a result of its own, graded or not
_HL_ROCK_RES = re.compile(r"(?i)\b(?:results?|assays?|returns?|returned|returning|values|grades|grading|analys[ie]s)\b")
_LEAD_ROCK_RES = re.compile(r"(?i)\b(?:announc\w*|report\w*|receiv\w*|provid\w*|present\w*)\s+(?:[\w-]+\s+){0,6}?(?:rock|grab|surface|"
                            r"prospecting|outcrop|chip|channel)\s+(?:[\w-]+\s+){0,2}?(?:results?|assays?|values)\b")
# 1.0.4: cues of the release's own new work, and old-work cues that name a place rather than older results
_NEW_CUE = re.compile(r"\b(?-i:new|newly)\b|(?i:\brecent(?:ly)?\b|\bthis\s+(?:year|season|summer|fall|spring)\b|\bour\b|"
                      r"\bconfirm\w*|\bvalidat\w*)")
_HIST_PLACE = re.compile(r"(?i)historic\w*\s+(?:mine|workings?|adits?|shafts?|pits?|dumps?|trench|occurrences?|showings?)\b"
                         r"(?![^.]{0,40}\b(?:returned|assay\w*|grading|yielded)\b)")
# 1.0.4: older work named by its owner, its date or its source (not only "previous"): a historical row may stand on one sentence
_HIST_STRONG = re.compile(r"(?i)\bhistoric\w*|\b(?:19[0-9]\d|200\d)\b|\boperators?\b|\bowners?\b|\bgovernment\b|"
                          r"\bgeological\s+survey|\b(?-i:GSC|OGS|BCGS|USGS|USBM|MERN|SMDI|MINFILE)\b|\([A-Z][^()]{0,40},?\s+(?:19|20)\d\d\)")
_IN_TRENCH = re.compile(r"(?i)\btrench(?:es)?\s+(?:#\s*|no\.\s*)?[A-Z]{0,4}[-\s]?\d|\b(?:from|in|within|across|along|of|"
                        r"inside)\s+(?:the\s+|each\s+|a\s+|two\s+|three\s+|four\s+|\d+\s+)?trench(?:es)?\b(?!\s+program)")
_GRADE_FROM = re.compile(r"(?i)[^.;:()]{0,30}?\b(?:from|in|on)\s+(?:an?|the|one|two|three|\d+)\s+(?:[\w.-]+\s+){0,3}?$")
# 1.0.4: a geochemical survey's own results (not an anomaly named as the setting of other work)
_GEO_RES = re.compile(r"(?i)\b(?:soil|till|sediment|geochemical)\s+(?:geochemical\s+)?(?:samples?|sampling|survey|grid|program|"
                      r"geochemistry|assays?)\b[^.;]{0,80}?\b(?:results?|returned|outlin\w+|identif\w+|defin\w+|delineat\w+|"
                      r"reveal\w+|highlight\w*|show\w*)\b|\b(?:results?|assays?)\s+(?:for|from|of)\s+(?:[\w,-]+\s+){0,4}?(?:soil|till|"
                      r"sediment)\s+samples?\b")
# rev c: older figures from drilling, resources or production, and a historic place newly sampled, are no historical sample row
_HIST_NOT_SAMPLE = re.compile(r"(?i)\bresources?\b|\breserves?\b|\bestimate\b|\bproduc\w+|\btonnes\b|\bpreviously\s+unsampled\b|"
                              r"\bhistoric\w*\s+(?:[A-Z][\w'-]*\s+){1,3}(?:trench|trenches|mine|workings?|adits?|shafts?|pits?|showings?)\b")
_HL_ANNOUNCED = re.compile(r"(?i)\b(?:recently|previously)\s+(?:announced|reported|released|identified)\s+(?:[\w-]+\s+){0,4}?"
                           r"(?:anomal\w*|results?|discover\w*|showings?|occurrences?)\b")
_SAMPLE_WORD = re.compile(r"(?i)\bsampl\w*|\bassay\w*|\bvalues?\b|\breturn\w*")
_GENERIC_HL = re.compile(r"(?i)\b(?:samples?|sampling|sampled|assays?|values|grades|surface\s+results?|surface\s+(?:work|exploration)|rock\s+results?|"
                         r"field\s+(?:program|season|work)\s+results?|exploration\s+results?|prospecting)\b")

# ------------------------------------------------------------------ 1.0.1: what kind of release the headline makes it
# resource estimates and studies: the grades quoted are resource or study grades, and any sample figures background
_HL_RESOURCE = re.compile(r"(?i)\b(?:resource\s+(?:estimates?|update)|mineral\s+resources?|maiden\s+(?:\w+\s+){0,2}resources?|"
                          r"(?:inferred|indicated|measured)\s+(?:mineral\s+)?resources?|preliminary\s+economic|PEA|"
                          r"pre-?feasibility|feasibility\s+study)\b")
# corporate releases: financings, meetings, quarterlies, year-end reviews, corporate updates
_HL_CORPORATE = re.compile(r"(?i)\b(?:financing|private\s+placement|placement|flow[\s-]?through|AGM|annual\s+general|"
                           r"shareholder\s+meeting|quarter(?:ly)?|year[\s-]in[\s-]review|year[\s-]end\s+review|corporate\s+update|"
                           r"annual\s+report|financial\s+(?:results|statements)|MD&A|warrants?|listing|trading\s+symbol)\b|"
                           r"\b(?-i:Q[1-4])\s+(?:20\d\d|results|report|update|highlights)\b")
# deals: the figures an acquisition, option, staking or sale release quotes are the vendor's or older work
_HL_DEAL = re.compile(r"(?i)\b(?:acquir\w*|acquisition|options?|optioned|earn[\s-]?in|stakes?|staking|staked|consolidat\w+|"
                      r"term\s+sheet|letter\s+of\s+intent|LOI|agreement|purchas\w+|sells?|sale\s+of|divest\w*|posts?\s+bond)\b|"
                      # 1.0.2: a licence or permit granted is a deal-type release (the ground is the news)
                      r"\b(?:licen[cs]es?|concessions?|permits?)\s+(?:(?:is|are|has\s+been|have\s+been|was|were)\s+)?(?:granted|"
                      r"awarded|issued)\b|\b(?:granted|awarded|issued|receives?|received|obtains?|obtained)\s+(?:an?\s+|the\s+|its\s+)?"
                      r"(?:new\s+)?(?:exploration|mining|prospecting)\s+(?:licen[cs]es?|concessions?|permits?)\b")
# 1.0.3: a new land, exploration, claim or property position or package is ground assembled by deals (a deal-type headline
# when it names no program or result beside it)
_HL_LAND = re.compile(r"(?i)\b(?:land|exploration|claims?|property|mineral)\s+(?:positions?|packages?|holdings?)\b")
# 1.0.2: the lead announces a deal (acquisition, option, staking, purchase) when the headline reports no result of its own
_LEAD_DEAL = re.compile(r"(?i)\b(?:announce|report)\w*\b[^.]{0,80}?\b(?:entered\s+into|signed|executed|acquired|staked|optioned|"
                        r"expanded|completed\s+the\s+acquisition)\b[^.]{0,120}?\b(?:acquisition|acquire|option|purchase|staking|"
                        r"staked|claims?|agreement)\b")
# 1.0.2: awards and recognitions: the discovery is background
_HL_AWARD = re.compile(r"(?i)\bawards?\b|\bprizes?\b|\brecogni[sz]ed\s+(?:with|for|as|by)\b")
# releases about older data: compilations, data reviews, technical-report filings, "historic results" (1.0.2: not
# "historical drilling data", which is drilling)
_HL_OLD_DATA = re.compile(r"(?i)\bhistoric\w*\s+(?!(?:[\w-]+\s+){0,2}?drill)(?:[\w-]+\s+){0,2}?(?:results?|data|samples?|sampling|work|exploration|discovery|"
                          r"assays?|grades?)\b|\bcompil\w+|\bdata\s+(?:review|compilation)|\breview\w*\s+(?:of\s+)?(?:the\s+)?"
                          r"(?:historical\s+|previous\s+|existing\s+|past\s+)(?:data|results|work|exploration)|\btechnical\s+report|"
                          r"\b43-101\b|\blegacy\s+data|\bpreviously\s+(?:reported|released|announced)|\bgovernment\b")
# desktop work: reviews, studies and interpretations of data already in hand give no new result (rule ST)
_HL_DESKTOP = re.compile(r"(?i)\breviews\b|\breview\s+of\b|\bdesktop\b|\b(?:geological|structural|data)\s+(?:and\s+\w+\s+)?"
                         r"stud(?:y|ies)\b")
# the lead announces a desktop product: an interpretation, compilation or review of existing data
_LEAD_DESKTOP = re.compile(r"(?i)\b(?:pleased\s+to\s+(?:report|announce|provide|present|share)|announces?|reports?|provides?|"
                           r"presents?|completed?)\s+(?:on\s+)?(?:the\s+)?(?:results\s+of\s+)?(?:an?\s+|the\s+|its\s+)?"
                           r"(?:[\w-]+\s+){0,3}?(?:interpretation|re-?interpretation|compilation|data\s+review|desktop\s+(?:study|review))"
                           r"\s+(?:of|on)\s+[^.;]{0,30}?\b(?:existing|historical|historic|previous|legacy|past|archival|government|"
                           r"regional|public|available|older)\b")
# the headline states a new result of its own (a grade, or a result / discovery verb)
_HL_NEW_RESULT = re.compile(r"(?i)\b(?:reports?|reported|returns?|returned|samples|sampled|sampling\s+results?|discover\w*|"
                            r"identif\w+|confirms?|outlines?|defines?|delineates?|locates?|finds?|found|intersects?|assays?|"
                            r"yields?|grading|up\s+to|results?)\b")
# drilling: a drill result, or a drill program started, planned or finished
_HL_DRILL_RES = re.compile(r"(?i)\b(?:drills|drilled|drill(?:ing)?\s+(?:results?|holes?|intercepts?|core|assays?|intersects?|"
                           r"returns?|hits?|confirms?|extends?|expands?|continues?|reveals?|on|at)|intersect\w*|intercept\w*|hits|holes?|DDH|"
                           r"core)\b")
_HL_DRILL_PROG = re.compile(r"(?i)\bdrill(?:ing)?\s+(?:program\w*|campaign|update|targets?|permits?|season|rig|contract\w*|"
                            r"plans?|phase)\b|\b(?:commenc\w+|begins?|began|starts?|started|mobiliz\w+|resumes?|launch\w*|plans?|"
                            r"prepar\w+|permitted|conclud\w+|complet\w+|underway|continues?)\s+(?:\w+\s+){0,3}?drill\w*|"
                            r"\bdrill\w*\s+(?:is\s+|are\s+)?(?:underway|starts?|begins?|commences?|continues?)|\bfor\s+drill\w*|"
                            r"\bto\s+(?:be\s+)?drill\w*|\bdrill[\s-](?:test\w*|ready)")
# an interval in the headline ("5.3 m at 6.57 g/t", "1.19% CuEq over 24.6 metres"): a drill intercept unless the
# headline names a surface sample
_HL_INTERVAL = re.compile(r"(?i)\b(?:over|of|across)\s+[\d.,]+\s*(?:m|metres?|meters?|ft|feet)\b|"
                          r"[\d.,]+\s*(?:m|metres?|meters?|ft|feet)\s+(?:at|of|grading|averaging|@)\s")
_HL_SURFACE = re.compile(r"(?i)\b(?:surface\s+(?:samples?|sampling|results?|exploration|work|program)|samples?|sampling|sampled|"
                         r"grabs?|rock|chips?|channels?|trench\w*|outcrops?|boulders?|float|soils?|till|prospecting|mapping)\b")
# a geophysical finding stated as new
_HL_GEO_FIND = re.compile(r"(?i)\b(?:discover\w*|identif\w*|new|outlines?|reveals?|defines?|delineates?|confirms?)\W+"
                          r"(?:[\w,.-]+\W+){0,4}?(?:magnetic|chargeability|conductors?|conductive|electromagnetic|gravity|"
                          r"radiometric|resistivity|IP|EM|MT|VTEM)\b|\b(?:magnetic|gravity|radiometric|geophysical|IP|EM|MT|"
                          r"VTEM|airborne|electromagnetic)\s+(?:\w+\s+)?survey\s+(?:results?|identifies|outlines|defines|"
                          r"confirms|highlights|reveals)")
# a lead that opens on drilling (a program, holes, core, intercepts), not a drill station or drill road
_LEAD_DRILL = re.compile(r"(?i)\b(?:drill(?:ing)?\s+(?:program\w*|results?|holes?|core|campaign|intercepts?)|diamond\s+drill\w*|"
                         r"drill(?:ed|s)|holes?|core|intersected|intercepted|"     # 1.0.3: "grades up to 6.93% nickel intersected"
                         # 1.0.2: "an update on the recently completed drilling at ...", "results of CVZ-67, completed at a depth
                         # of 502 ft": a hole's depth
                         r"(?:recent(?:ly)?|completed|latest|ongoing|current|maiden|initial)\s+(?:completed\s+)?(?:[\w-]+\s+)?drilling|"
                         r"(?:completed|drilled|ended|terminated)\s+(?:to|at)\s+a\s+(?:total\s+|final\s+)?depth\s+of|end\s+of\s+hole|EOH)\b")
# metallurgy, processing and sales: not exploration sampling
_HL_MET2 = re.compile(r"(?i)\bmineralog\w+|\brecover(?:y|ies)\b|\bextraction\b|\bDLE\b|\bpilot\s+(?:plant|test\w*|scale)|"
                      r"\b(?:gold|metal|concentrate)\s+sales?\b|\bsales?\s+of\b|\bprocessing\s+(?:plant|results?)|\bcommissioning\b")
# 1.0.2 (2026-10-01, full-text losses): drill words that do not make a release a drill release.
# drill targets a release defines, extends, supports or ranks are the outcome of its surface work
_HL_DRILL_TARGET_OUT = re.compile(r"(?i)\b(?:defin\w*|identif\w*|extends?|extended|extending|generat\w*|outlin\w*|delineat\w*|"
                                  r"confirm\w*|support\w*|refin\w*|prioriti[sz]\w*|highlight\w*|new)\s+(?:of\s+)?"
                                  r"(?:[\w-]+\s+){0,3}?drill(?:ing)?[\s-]+targets?\b")
# "core" that is not drill core: "a central magnetic core", "the core Kittson Project"
_CORE_NOT_DRILL = re.compile(r"(?i)\b(?:magnetic|central|inner|outer|intrusive|granitic|dome)\s+core\b|"
                             r"\bcore\s+(?:[A-Z][\w-]*\s+){0,3}(?:projects?|property|properties|claims?|assets?|areas?|land|"
                             r"holdings?|licen[cs]es?|tenements?)\b")
# a drill program named in other words ("an update for its second phase of drilling", "20 drill pads")
_LEAD_DRILL2 = re.compile(r"(?i)\b(?:phase|stage|round|season|program|programme|campaign)\s+of\s+(?:[\w-]+\s+)?drilling\b|"
                          r"\bdrill\s+(?:pads?|platforms?)\b")
# samples taken from drill holes or core ("re-sampling of archived drill core", "infill sampling on historical diamond drill
# holes"): drilling, however old
_SAMPLED_CORE = re.compile(r"(?i)\bsampl\w*\s+(?:[\w-]+\s+){0,3}?(?:of|on|from)\s+(?:[\w-]+\s+){0,3}?(?:drill\s*(?:holes?|core)|"
                           r"core|holes?|cuttings)\b|\bcore\s+(?:re-?)?sampl\w*")
# the drill program's own results are still to come ("Thorn Project 2017 drill results are pending", "Results of this work will
# be released as they become available"): the drilling is not what the release reports
_DRILL_PENDING = re.compile(r"(?i)(?<!remaining\s)(?<!additional\s)(?<!further\s)\b(?:drill(?:ing)?\s+(?:assay\s+)?results?|"
                            r"results?\s+(?:of|from)\s+(?:this|that|the)\s+(?:work|drilling|drill\s+program))\s+(?:are|is|remain)?\s*"
                            r"(?:still\s+)?(?:pending|awaited|outstanding|will\s+be\s+(?:released|reported|announced))")


def _old_work(s):
    """s speaks of older work by others (historic results, previous operators, government data, a citation), not of
    historic mines, workings, showings or drilling as places."""
    return bool(_HIST.search(s)) and not re.search(r"(?i)\bhistoric\w*\s+(?:mine|workings?|adits?|shafts?|pits?|dumps?|"
                                                    r"mining|production|trench(?:es)?|showings?|occurrences?|high|low|district|camp|"
                                                    r"drill\w*|holes?|intercepts?|intersections?)\b"
                                                    r"(?![^.]{0,40}\b(?:returned|assay|grading|results?|yielded|samples?\s+(?:returned|collected\s+by|"
                                                    r"from\s+the\s+(?:19|20)))\b)", s)


def _hist_split(s, ry, own_rx):
    """1.0.4: in a sentence that quotes the release's own new results beside older work by others ("rock chip samples assayed
    6.76% WO3 ... historic USBM sampling returned 8.48%"), each grade goes with the nearest old- or new-work cue before it
    (else the first after it); grades before an old-work clause that follows a clause break are new. None when the
    sentence is not such a mix."""
    if not _old_work(s):
        return None
    olds = [m.start() for m in _HIST.finditer(s) if not _HIST_PLACE.match(s, m.start())]
    nws = [m.start() for m in _NEW_CUE.finditer(s)] + [m.start() for m in own_rx.finditer(s)] + (
        [m.start() for m in re.finditer(r"\b20[0-4]\d\b", s) if int(m.group(0)) >= ry - 2] if ry else [])
    if olds and not nws and _grades(s[:olds[0]]) and re.search(r"(?i)(?:[,;]\s*(?:and\s+|while\s+|whereas\s+)?|\b(?:while|whereas)\s+)"
                                                               r"(?:the\s+)?$", s[max(0, olds[0] - 12):olds[0]]):
        nws = [0]                                       # "... assayed 6.76% WO3, and historic sampling returned 8.48%"
    if not olds or not nws:
        return None

    def split(gp):
        before = [(q, True) for q in olds if q < gp] + [(q, False) for q in nws if q < gp]
        if before:
            return max(before)[1]
        return min([(q, True) for q in olds] + [(q, False) for q in nws])[1]
    return split


def analyse(headline, body):
    h, b = _prepare(headline, body)
    res = {"rows": [], "reason": None}
    sents = _sentences(b)
    if (re.match(r"(?i)^\s*(?:news\s+release|press\s+release|news|nr)?\s*[-:.]?\s*$", h) or re.match(
            r"(?i)^\s*(?:securities\s+(?:may\s+not|and\s+exchange)|not\s+for\s+(?:distribution|dissemination)|this\s+news\s+"
            r"release|\d+\s*$|DDH\b)", h)) and sents:
        k = next((i for i, t in enumerate(sents[:8]) if re.search(r"(?i)\b(?:announce|report|provide|pleased)\w*\b", t)), 0)
        h = sents[k][:300]
    issuer = _issuer(b) or ""
    names = PN.release_projects(headline or "", body or "")
    proj_list = [p for p in (names.get("projects") or []) if p]
    # 1.0.3: a headline fragment taken as a name ("X Purchases Strategic Y Mine"): it holds a headline verb
    proj_list = [p for p in proj_list if not re.search(_HL_VERB_IN_NAME, p)] or proj_list
    if len(proj_list) <= 1:
        sub = re.compile(r"(?i)\b(?:prospect|zone|deposit|showing|target|complex|mine|vein|occurrence|trend)s?$")
        if not proj_list or sub.search(proj_list[0]):
            from collections import Counter as _C
            cnt = _C()
            for t in [h] + sents[:12]:
                for _q, n in PN.find(t):
                    if re.search(r"(?i)\b(?:project|property|claims|concession|permit|license|licence)$", n) and\
                            not re.search(r"(?i)^(?:the\s+)?(?:gold|silver|copper|lithium|epithermal|porphyry|exploration)\s", n):
                        cnt[n] += 1
            if cnt:
                top = cnt.most_common(1)[0][0]
                if not proj_list or not PN.same(top, proj_list[0]):
                    proj_list = [top]
    rel = T._dateline(b)
    rel_year = int(rel[:4]) if rel else None

    # the news: headline + lead sentences before the QA / method section
    lead = []
    for i, s in enumerate(sents[:LEAD_SENTS]):
        if i > 3 and _QA.search(s) and not _grades(s):
            continue
        lead.append(s)
    news = [h] + lead
    hl_types = [t for _p, t in _types_in(h)]
    # "...correspond to EM targets", "gravity anomalies associated with magnetic targets": context, when the headline
    # has another result; "...Mineralization at Eastern Magnetic Anomaly": a target's name, never a survey result
    ctx, name = set(), set()
    for m in TCUE["geophysics"].finditer(h):
        if re.search(r"(?i)\b(?:correspond\w*|coincid\w*|associated|along|within|beneath|below|near|adjacent|upslope|"
                     r"underlying)\s+(?:to|with|from)?\s*(?:the\s+|an?\s+|known\s+|existing\s+|previous(?:ly\s+identified)?\s+)*$",
                     h[max(0, m.start() - 40):m.start()]):
            ctx.add(m.start())
        if re.search(r"\b(?i:at|on|of|near|in|into|along|testing|tested|test|drilled\s+on)\s+(?i:the\s+)?"
                     r"(?:[A-Z][\w'-]*\s+){0,4}$", h[max(0, m.start() - 50):m.start()]) and\
                re.match(r"\w*(?:\s+[A-Z][\w'-]*)?\s+(?:Anomal(?:y|ies)|Targets?|Zones?|Trends?|Highs?|Lows?|Corridor|"
                         r"Embayment|ANOMAL(?:Y|IES)|TARGETS?|ZONES?|TRENDS?)\b", h[m.start():m.start() + 50]):
            name.add(m.start())
    hl_ctx = ctx | name
    # 1.0.2: a geochemical anomaly the headline's result lies in or beside ("discovers a new zone within the 2.2 km
    # gold-in-soil trend", "drills ... up-ice of the gold-in-till anomaly") is where the news is, not the news
    geo_ctx = set()
    if re.search(r"(?i)\b(?:discover\w*|identif\w*|confirms?|intersect\w*|drills?|drilled|drilling|returns?|samples?|"
                 r"outlines?|defines?|reveals?|finds?|found)\b", h):
        for p0, t0 in _types_in(h):
            if t0 in ("soil", "till", "sediment") and re.search(
                    r"(?i)\b(?:within|along|beneath|below|under(?:lying)?|near|adjacent\s+to|up-?ice\s+(?:of|from)|down-?ice\s+"
                    r"(?:of|from)|associated\s+with|coincident\s+with|correspond\w*\s+(?:to|with)|on\s+trend\s+with)\s+(?:the\s+|"
                    r"an?\s+|known\s+|existing\s+|large\s+|broad\s+|strong\s+|\d[\d.,]*\s*-?\s*(?:km|kilomet\w+|m|met\w+)\s+"
                    r"(?:long\s+)?)*(?:[\w-]+[\s-]+in[\s-]+|[\w-]+[\s-]+)?$", h[max(0, p0 - 70):p0]):
                geo_ctx.add(p0)
    if hl_ctx or geo_ctx:
        all_t = _types_in(h)
        kept = [(p, t) for p, t in all_t if not (t == "geophysics" and p in hl_ctx or p in geo_ctx)]
        if not kept and ctx - name:
            hl_ctx = name
            kept = [(p, t) for p, t in all_t if not (t == "geophysics" and p in hl_ctx or p in geo_ctx)]
        hl_types = [t for _p, t in kept]
        hl_ctx = hl_ctx | geo_ctx
    h_res = h
    for m in TCUE["geophysics"].finditer(h):
        if m.start() in hl_ctx:
            h_res = h_res[:m.start()] + " " * (m.end() - m.start()) + h_res[m.end():]
    hl_methods = {nm for nm, rx in SURVEY if any(not _GEOPHYS_NOISE.search(h_res[max(0, m.start() - 20):m.end() + 25])
                                                 for m in rx.finditer(h_res))}
    hl_grades = _grades(h)
    hl_generic = bool(_GENERIC_HL.search(h)) and not [t for t in hl_types if t != "mapping"]
    hl_drill_only = bool(_DRILL.search(_HL_DRILL_TARGET_OUT.sub(" ", h))) and not hl_types and not hl_generic
    hl_met = bool(re.search(r"(?i)\bmetallurg\w*|\btest\s*work|\bsorting\b|\bleach\s+tests?|\bflotation\s+tests?|\bpilot\s+plant|"
                            r"\b\d+(?:\.\d+)?\s*%\s*pure\b|\bpurity\b|\bbattery[\s-]grade\b|"
                            # rev c: a concentrate produced is a metallurgical product, not a field sample
                            r"\b(?:produc\w+|spodumene|technical[\s-]grade|chemical[\s-]grade)\s+(?:[\w\"'%.-]+\s+){0,5}?concentrates?\b",
                            h))
    hl_plan = bool(re.search(r"(?i)\b(?:start\w*|launch\w*|commenc\w+|commencement|begin\w*|began|initiat\w+|mobiliz\w+|mobilis\w+|"
                             r"plans?|planned|underway|to\s+(?:begin|start|commence|conduct|drill|carry\s+out|undertake|execute|perform)|kicks?\s+off|"
                             r"prepar\w+\s+for)\b", h)) and\
        not hl_grades and not re.search(r"(?i)\b(?:results?|returns?|identif\w+|outlin\w+|defin\w+|confirm\w+|reveal\w+|"
                                         r"discover\w+|anomal\w+)\b", h) or bool(re.search(
        r"(?i)^(?:[\w.&'-]+\s+){0,5}(?:plans?|launch\w*|commenc\w+|start\w*|begin\w*|initiat\w+|mobiliz\w+)\b", h)) and not hl_grades

    # 1.0.2: a headline with no result over a lead that announces plans ("an update on exploration activities planned for
    # 2020"): a plan release
    if not hl_grades and not _types_in(h) and not _HL_NEW_RESULT.search(h) and any(re.search(
            r"(?i)\b(?:announce|provide|present|report)\w*\s+(?:an?\s+)?(?:update\s+on\s+|outline\s+of\s+)?(?:the\s+|its\s+)?"
            r"(?:[\w-]+\s+){0,4}?(?:plans?|planned|proposed|upcoming)\b", x) for x in sents[:3]):
        hl_plan = True
    # rev c: a result the headline names as already announced ("includes recently announced gold till anomaly") is not
    # this release's finding
    h_new = _HL_ANNOUNCED.sub(" ", h)
    hl_done = bool(re.search(r"(?i)\b(?:complet\w+|finish\w+|wraps?\s+up|concludes?)\b", h)) and not hl_grades and\
        not re.search(r"(?i)\b(?:results?|returns?|assays?|identif\w+|outlin\w+|defin\w+|confirm\w+|reveal\w+|discover\w+|"
                      r"anomal\w+|highlights?|grad(?:es|ing)|grade\s+of|yields?|intersect\w*)\b", h_new)
    if re.search(r"(?i)\b(?:plan\w*|will|to\s+(?:commence|begin|start|test|drill)|commenc\w+|launch\w*|start\w*|mobiliz\w+|"
                 r"prepar\w+|returns?\s+to)\b[^|]{0,80}\b(?:follow(?:ing|s)?(?:\s+up)?(?:\s+on)?|after|building\s+on|based\s+on)\b",
                 h) or re.search(r"(?i)\b(?:will|to)\s+(?:explore|test|target|follow\s+up)\b", h) and not re.search(
                 r"(?i)\b(?:returns?|returned|results?\s+(?:of|include|show)|identif\w+|discover\w+)\b", h.split(" will ")[0]):
        hl_plan = True
        hl_grades = []
    if not hl_grades and re.search(r"(?i)\b(?:refine\w*|updat\w+|build\w*|construct\w*)\s+(?:the\s+|its\s+|a\s+)?(?:[\w-]+\s+){0,2}"
                                   r"model(?:s|l?ing)?\b|\bre-?interpret\w*|\bre-?process\w*|\bre-?model\w*|"
                                   r"\b(?:gravity|magnetic|geophysical|radiometric)\s+maps?\b|"
                                   # rev c: "... identified through data compilation and modelling"
                                   r"\b(?:through|from|by)\s+(?:[\w-]+\s+){0,3}?(?:compilation|modell?ing|re-?interpretation)\b", h):
        res["reason"] = "modelling / reinterpretation (rule ST)"
        return res
    rows = {}                                           # key -> row dict
    # 1.0.4: the lead announces surface sampling results ("has received rock geochemical results from an inaugural field
    # program") under a headline that names no kind
    lead_rock_res = any(_LEAD_ROCK_RES.search(x) and not _DRILL.search(x) for x in lead[:3])

    def project_for(i, s, pos):
        if len(proj_list) == 1:
            return proj_list[0]
        if not proj_list:
            f = PN.find(s)
            return f[0][1] if f else None
        f = [(q, n) for q, n in PN.find(s)]
        if f:
            best = min(f, key=lambda t: abs(t[0] - pos))
            for p in proj_list:
                if PN.same(p, best[1]) or PN.key(p) in PN.key(best[1]) or PN.key(best[1]) in PN.key(p):
                    return p
        for p in proj_list:
            core = [w for w in re.findall(r"[A-Za-z\u00c0-\u00ff][\w\u00c0-\u00ff'-]{3,}", p) if w.lower() not in (
                "project", "property", "gold", "silver", "copper", "mine", "claims", "lithium", "north", "south", "east", "west")]
            if core and re.search(r"\b" + re.escape(core[0]) + r"\b", s, re.I):
                return p
        text = " ".join(news)
        try:
            at = PN.project_at(text, text.find(s) + pos, proj_list)
        except Exception:   # pragma: no cover - helper edge cases
            at = None
        return at or proj_list[0]

    def add(stype, i, s, pos, hist, grade=None, width=None, survey=None):
        proj = project_for(i, s, pos)
        if stype == "geophysics" and not survey:
            survey = _survey(s)
        k = (stype, survey if stype == "geophysics" else None, PN.key(proj) if proj else None, hist)
        # a later sentence naming no other project folds into the release's one row of that type
        if k not in rows:
            for k2 in rows:
                if k2[0] == stype and k2[1] == k[1] and k2[3] == hist and (k2[2] is None or k[2] is None):
                    if k2[2] is None and proj:
                        rows[k2]["project"] = proj
                    k = k2
                    break
        r = rows.get(k)
        if r is None:
            r = rows[k] = {"sample_type": stype, "survey_type": survey if stype == "geophysics" else None, "project": proj,
                           "historical": hist, "sents": [], "grades": [], "first": (i, pos), "evidence": s[max(0, pos - 60):pos + 160]}
        if s not in r["sents"]:
            r["sents"].append(s)
        if grade:
            inc = bool(re.search(r"(?i)\b(?:incl(?:uding|\.)?|with|containing)\s+(?:a\s+(?:higher[\s-]grade\s+portion\s+of\s+)?)?[^.;]{0,25}$",
                                 s[max(0, grade[0] - 40):grade[0]]))
            avg = bool(re.search(r"(?i)\baverag\w*\s*(?:grade\s+)?(?:of\s+)?$", s[max(0, grade[0] - 25):grade[0]]))
            thr = bool(re.search(r"(?i)(?:>|\u2265|greater\s+than|above|over|exceed\w*|in\s+excess\s+of|at\s+least|more\s+than|"
                                 r"anomalous\s+(?:at|threshold\s+of))\s*$", s[max(0, grade[0] - 25):grade[0]]))
            r["grades"].append((i,) + grade + (width, inc, avg, thr))
        return r

    hl_type_set = {t for t in hl_types if t != "mapping"}
    geo_specific = {_survey(s) for s in news if TCUE["geophysics"].search(s)} - {"other"}
    hl_bulk_grade = bool(re.search(r"(?i)\bbulk[\s-]sampl\w*\s+results?\b|\bbulk\b.{0,80}\d\s*(?:g/t|gpt|%)|\d\s*(?:g/t|gpt|%).{0,80}"
                                   r"\bbulk\b", h)) and not re.search(r"(?i)\bmineralog", h)
    if hl_met:
        res["reason"] = "metallurgical test work"
        return res
    # 1.0.1: releases whose figures are not exploration sampling results (the headline read without the issuer's
    # name, so "Discovery ... Metals" or "Q2 Metals" is not a discovery or a quarter)
    hn = h
    iw = issuer.split()
    for k in range(len(iw), 0, -1):
        mi = re.match(r"(?i)\s*" + r"\s+".join(re.escape(w) for w in iw[:k]) + r"(?![\w-])", h)
        if mi and (k > 1 or len(iw) == 1):
            hn = h[mi.end():]
            break
    mres = _HL_RESOURCE.search(hn)
    if mres and not re.search(r"(?i)\b(?:host\w*|contain\w*|with\s+an?\s+(?:existing|current|historical))\b[^,;]{0,60}$",
                              hn[:mres.start()]) and not (
            # 1.0.2 (2026-10-01): a resource named as the place of a new result ("10 km south of current mineral resource",
            # "discovers gold mineralization west of the existing mineral resource"): the result is the news
            re.search(r"(?i)\b(?:of|from|beyond|outside(?:\s+of)?|near|adjacent\s+to|along\s+strike\s+(?:of|from))\s+(?:the\s+|its\s+)?"
                      r"(?:current|existing|known|defined|updated|20\d\d)\s+$", hn[:mres.start()]) and
            (hl_grades or _HL_NEW_RESULT.search(hn[:mres.start()]))):
        res["reason"] = "resource estimate or economic study"
        return res
    if _HL_CORPORATE.search(hn) and not hl_type_set and not hl_grades and not re.search(
            r"(?i)\b(?:discover\w*|delineat\w+|identif\w+|outlin\w+|defin\w+|samples|sampled|assays?|returns?|"
            r"sampling\s+results?|(?:exploration|geochemical|survey)\s+results?)\b", hn):   # 1.0.2 (2026-10-01): "... and new
        res["reason"] = "corporate release"                                                # sampling results"
        return res
    # 1.0.2 (2026-10-01): the recoveries assumed in a metal-equivalent note are not metallurgy, and a field sample's grade
    # named before a recovery figure ("trenching returns 5.26 g/t gold with 85.9% gravity recovery") is a sampling result
    mmet = _HL_MET2.search(re.sub(r"(?i)\bassum\w+\s+(?:mill\s+|metallurgical\s+|process(?:ing)?\s+)?recover(?:y|ies)\b",
                         lambda m: " " * len(m.group(0)), hn))
    if mmet and not hl_bulk_grade and not (hl_type_set & set(ROCK + GEOCHEM) and any(
            g[0] < mmet.start() + len(h) - len(hn) for g in hl_grades)):
        res["reason"] = "metallurgy, processing or sales"
        return res
    if _HL_AWARD.search(hn) and not hl_grades:
        res["reason"] = "award or recognition"          # 1.0.2: the discovery honoured is background
        return res
    # 1.0.1: a deal, a data compilation or review, or a technical-report filing presents older work: its results are
    # historical, unless (for a deal) the headline itself reports a new result
    # 1.0.2: a data compilation, review or technical report keeps that; a deal (headline, or a lead that announces one under
    # a headline with no result of its own) reads how the release frames its results (deal_frame below)
    old_rel = bool(_HL_OLD_DATA.search(hn))
    # 1.0.2 (2026-10-01): "completes acquisition and interpretation of aeromagnetic survey" is collecting data, not a deal
    hn_deal = re.sub(r"(?i)\b(?:data\s+acquisition|acquisition\s+(?:and\s+\w+\s+)?of\s+(?:[\w-]+\s+){0,4}?(?:surveys?|data|imagery))\b",
                     " ", hn)
    deal_rel = not old_rel and not (_HL_NEW_RESULT.search(hn) or _grades(h)) and (
        bool(_HL_DEAL.search(hn_deal)) or not hl_type_set and any(_LEAD_DEAL.search(x) for x in lead[:3]) or
        bool(_HL_LAND.search(hn)) and not re.search(r"(?i)\b(?:programs?|programmes?|results?|surveys?|sampling|samples)\b", hn))
    hist_rel = old_rel
    hl_techrep = bool(re.search(r"(?i)\btechnical\s+report|\b43-101\b", hn))
    # 1.0.1: a desktop review, study or interpretation of existing data: only its historical rows stand
    desk_rel = bool(_HL_DESKTOP.search(hn)) or any(_LEAD_DESKTOP.search(x) for x in lead[:2])
    # 1.0.2 (2026-10-01): a headline that reports a new result of its own beside the review or old-data words. The kinds named
    # with a finding before those words are new ("identifies new large IP anomalies ... compilation and review of historical
    # data completed"); a review that is not in the headline's first clause ("A - re-analyses of soil samples; B - initial
    # review of LiDAR") or that is followed by the release's own grades ("study targets and samples up to 72 g/t gold") does
    # not make the whole release a desktop review
    new_hl_types = set()
    m_rev = [m for rx in (_HL_OLD_DATA, _HL_DESKTOP) for m in [rx.search(hn)] if m]
    if m_rev:
        first_rev = min(m.start() for m in m_rev)
        pre = hn[:first_rev]
        if re.search(r"(?i)\b(?:identif\w*|discover\w*|outlin\w*|defin\w*|delineat\w*|reveal\w*|detect\w*|returns?|returned|"
                     r"samples|sampled|confirms?)\b", pre):
            new_hl_types = {t for _p, t in _types_in(pre) if t in hl_type_set}
        if desk_rel and _HL_DESKTOP.search(hn) and not any(_LEAD_DESKTOP.search(x) for x in lead[:2]) and (
                re.search(r"[;|]", hn[:first_rev]) and not re.search(r"(?i)\b(?:reviews?|stud(?:y|ies)|desktop)\b",
                                                                     re.split(r"[;|]", hn)[0]) or
                hl_grades and re.search(r"(?i)(?:[;|]|\band\b)\s+(?:[\w-]+\s+){0,2}?(?:samples|sampled|sampling\s+returns|"
                                        r"returns|assays?\s+returns?)\b[^;|]{0,40}?\d", hn[first_rev:])):
            desk_rel = False
    # 1.0.1: a drill release (a drill result, or a drill program started, planned or finished): its surface samples and
    # geophysics are background, except the kinds the headline itself names as results
    hl_surf = bool(hl_type_set) or bool(_HL_SURFACE.search(re.sub(r"(?i)\b(?:from|near|at)[\s-]surface\b", " ", h)))
    hl_interval = bool(_HL_INTERVAL.search(hn)) and not hl_surf
    if hl_interval:
        # "3.63 g/t over 9.0 m": a channel or trench interval when the lead opens on surface sampling, not drilling
        lead_t = " ".join(lead[:6])
        ms = re.search(r"(?i)\b(?:grabs?|chips?|channels?|trench\w*|soils?|till|outcrops?|surface\s+sampl\w*)\b", lead_t)
        md = _LEAD_DRILL.search(lead_t)
        hl_interval = not ms or (md is not None and md.start() < ms.start())
    hl_drill_res = bool(_HL_DRILL_RES.search(hn)) or hl_interval
    hl_drill = hl_drill_res or bool(_HL_DRILL_PROG.search(_HL_DRILL_TARGET_OUT.sub(" ", hn)))
    # 1.0.2 (2026-10-01): drill targets the headline defines or extends ("extends drilling targets", "definition of drill
    # targets ... completion of surface geochemistry") make a drill release only when the lead opens on drilling
    tgt_out = not hl_drill and bool(_HL_DRILL_PROG.search(hn))
    if (hl_generic or tgt_out) and not hl_drill:
        # "Assays up to 181 g/t silver": a generic assay headline over a drill program the lead opens on
        # 1.0.2 (2026-10-01): the lead's own drilling only, read without the headline it repeats: not "core" that is no drill
        # core, not drilling by others or long ago ("P.A.T Mines drilled ... in the 1950s", "existing drill results", "2019
        # drill core") unless the release samples those holes, and not a drill program whose results are still to come;
        # and the release's own sampling ("has located and sampled the vein showings") counts as surface work
        pend = any(_DRILL_PENDING.search(x) for x in lead[:10])
        ry0 = rel_year
        md = ms = None
        off = 0
        # 1.0.3: when a letterhead (address, phone, exchange listings) fills the first sentences, the lead starts at the
        # announcement
        l0 = next((k for k, x in enumerate(lead[:12]) if re.search(r"(?i)\b(?:announc\w*|pleased|reports?|provides?)\b", x)), 0)
        for x in (lead[l0:l0 + 3] if l0 >= 3 else lead[:3]):
            xs = x.replace(h, " " * len(h)) if len(h) > 20 else x
            if md is None and not pend:
                for m in sorted(list(_LEAD_DRILL.finditer(xs)) + list(_LEAD_DRILL2.finditer(xs)), key=lambda q: q.start()):
                    if m.group(0).lower() == "core" and _CORE_NOT_DRILL.search(xs[max(0, m.start() - 25):m.end() + 60]):
                        continue
                    # the clause the drill word is in (a sentence the splitter left joined is read by its own clauses)
                    cb = r"(?<!\bInc)(?<!\bCorp)(?<!\bLtd)(?<!\bCo)(?<!\bNo)(?<![A-Z])[.;!?](?:\s+(?=[A-Z\"\u201c(])|$)"
                    c0 = max([q.end() for q in re.finditer(cb, xs[:m.start()])] or [0])
                    c1 = next((q.start() + 1 for q in re.finditer(cb, xs[m.end():])), len(xs) - m.end()) + m.end()
                    cl = xs[c0:c1]
                    if re.search(r"(?i)\b(?:planned|will|scheduled|upcoming|proposed|to\s+(?:commence|begin|start)|under\s+"
                                 r"construction)\b", cl):
                        continue                        # 1.0.3: drilling still to come is not what the release reports
                    if (re.search(r"(?i)\b(?:historic\w*|previous(?:ly)?|prior|past|former|legacy|archiv\w+|existing|vintage)\b", cl) or
                            ry0 and any(int(y) <= ry0 - 3 for y in re.findall(r"\b(?:19[5-9]\d|20[0-4]\d)\b", cl))) and\
                            not _SAMPLED_CORE.search(cl):
                        continue
                    md = off + m.start()
                    break
            if ms is None:
                m = re.search(r"(?i)\b(?:grabs?|chips?|channels?|trench\w*|soils?|till|outcrops?|rock|surface|prospecting|"
                              r"geophysic\w*|survey)\b", x)
                m2 = re.search(r"(?i)\b(?:underground|stripp(?:ing|ed)|showings?)\b|\bsampl(?:ed|ing|es?)\b(?!\s+(?:[\w-]+\s+)"
                               r"{0,3}?(?:of|on|from)\s+(?:[\w-]+\s+){0,3}?(?:drill|core|holes?|cuttings)\b)", xs)
                if m2 and re.search(r"(?i)\b(?:drill\w*|core|holes?)\s+(?:[\w-]+\s+)?$", xs[max(0, m2.start() - 30):m2.start()]):
                    m2 = None
                ps = [q.start() for q in (m, m2) if q]
                if ps:
                    ms = off + min(ps)
            off += len(x) + 1
        lead_drill = md is not None and (ms is None or md < ms)
        if hl_generic:
            hl_drill = hl_drill_res = lead_drill
        else:
            hl_drill = lead_drill
    drill_keep = set(hl_type_set)
    if hl_drill_res:
        drill_keep -= {"brine", "bulk"}                 # brine from a drill hole, bulk "samples" of core are drilling
        if not _HL_GEO_FIND.search(hn):
            drill_keep.discard("geophysics")            # the known anomaly a hole was drilled into
    if hl_drill and not hl_drill_res:
        ds = re.search(r"(?i)\b(?:commenc\w+|begins?|began|starts?|started|mobiliz\w+|resumes?|launch\w*|plans?|prepar\w+|"
                       r"permitted|underway|to\s+test|to\s+follow[\s-]?up|"
                       r"acquir\w+|purchas\w+|buys?|bought)\b", hn)   # 1.0.2 (2026-10-01): "...; acquires RC drill rig"
        rs = _HL_NEW_RESULT.search(hn)
        if ds and rs and rs.start() < ds.start():
            hl_drill = False                            # "announces new discovery ... and plans its drill program"
        elif ds and not _HL_GEO_FIND.search(hn):
            drill_keep = set()                          # "commences drilling to test the vein, samples up to 54 g/t"
    # 1.0.1: kinds the headline names only as work done, started or planned ("completes airborne survey and a large soil
    # sampling program", "targets for heliborne magnetic survey", "receives final products of the survey"): such a row
    # needs a grade
    rest = re.sub(r"(?i)\b(?:complet\w*|conclud\w*|commenc\w*|begins?|starts?|launch\w*|mobiliz\w*|initiat\w*|receiv\w*|"
                  r"conducts|conducting|"                                       # 1.0.3: "conducts LiDAR survey over ..."
                  r"for\s+(?:(?:a|an|the|its|new|planned|upcoming|follow[\s-]?up)\s+)?(?:[\w-]+\s+){0,3}?"
                  r"(?=(?:[\w-]+\s+)?(?:surveys?|sampling|programs?|programmes?)\b))[^,;:|]*?(?=[,;:|]|\s-\s|$)",
                  lambda m: m.group(0) if re.search(r"(?i)\b(?:results?|assays?|returns?|returned|identif\w*|discover\w*|"
                                                    r"outlin\w*|reveal\w*|defin\w*|confirm\w*|anomal\w*|grad(?:es|ing|ed)|"
                                                    # 1.0.2 (2026-10-01): "survey highlights new targets", "receives
                                                    # data supporting the drill target"
                                                    r"highlights?|supporting|shows?|showing|indicates?|indicating)\b",
                                                    m.group(0)) else " ",
                  re.sub(r",(?=(?:\s+[\w-]+){1,3}\s+(?:and|&)\s)", " ", h_new))   # "magnetic, VLF and LiDAR survey": one list
    # ... and a clause that ends "still being investigated", "pending", "awaited"
    rest = re.sub(r"(?i)(?:^|(?<=[,;:|]))[^,;:|]*?\b(?:(?:still\s+)?being\s+(?:investigated|evaluated|analy[sz]ed)|under\s+"
                  r"investigation|pending|awaited)\b", " ", rest)
    hl_status_only = {t for t in hl_type_set} - {t for _p, t in _types_in(rest)}
    # 1.0.1: "grab samples collected from quartz veins uncovered by trenches": grab samples, not a trench row
    lead_all = " ".join(lead[:25])
    grab_in_trench = bool(re.search(r"(?i)\bgrab\s+samples?\s+(?:[\w-]+\s+){0,6}?(?:from|in|within|along|of)\s+(?:[\w-]+\s+){0,5}?"
                                    r"trench", lead_all)) and not re.search(r"(?i)\b(?:channel|chip)\s+(?:samples?|sampling)\b",
                                                                            lead_all)
    # 1.0.2: a deal release (acquisition, option, staking, licence) quotes three kinds of results, and the release says which
    # by how it frames them: older work by others (historic, previous owners or operators, government, a citation) is
    # historical; the company's own earlier work (dated before this year, or cited to its news release) is restated
    # background, no row; the company's own work this year (a due-diligence program) or the vendor's, optionor's or
    # prospector's recent work (dated within two years, guide item 70) is new. A sentence's own old-work cue decides
    # for that sentence; otherwise the release's framing statements decide, and with none the results stay historical.
    years_all = [int(y) for y in re.findall(r"\b(?:19[5-9]\d|20[0-4]\d)\b", b[:800])]
    ry = rel_year or (max(years_all) if years_all else None)
    # the issuer's short names: those defined beside "the Company" ("Eloro", or the "Company")
    shorts = []
    for mq in re.finditer(r"\(([^()]{0,120}?[\"\u201c]\s*(?:Company|Corporation|Issuer)\s*[\"\u201d][^()]{0,60}?)\)", b[:2000]):
        shorts += [x for x in re.findall(r"[\"\u201c]\s*([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,2})\s*[\"\u201d]", mq.group(1))
                   if x not in ("Company", "Corporation", "Issuer")]
        break
    who = r"|".join([r"(?-i:" + re.escape(x) + r")" for x in shorts[:3]] + [r"the\s+company", r"we"])
    own_rx = re.compile(r"(?i)\b(?:" + who + r")\s+(?:\w+\s+){0,2}?(?:collected|took|completed|conducted|performed|carried\s+out|"
                        r"undertook|sampled|discovered)\b|\b(?:our|the\s+company'?s|" + who + r"'s)\s+(?:[\w-]+\s+){0,2}?"
                        r"(?:program\w*|sampling|field\s*work|crews?|geologists|consultants)\b|\bby\s+(?:the\s+)?(?:company|" + who +
                        r")(?:'s)?\s+(?:geologists|consultants|crews?|personnel|staff)?\b|\bcompany\s+(?:geologists|consultants|"
                        r"crews?|personnel|staff)\b")
    work_rx = re.compile(r"(?i)\b(?:completed|collected|conducted|performed|carried\s+out|undertook|sampled|discovered|returned|"
                         r"assay\w*|defined|identified|included?|results?|program\w*|sampling)\b")
    vendor_rx = re.compile(r"(?i)\b(?:vendors?|optionors?|prospectors?|syndicate|title\s+holders?|private\s+owners?|current\s+"
                           r"owners?)\b")
    future_rx = re.compile(r"(?i)\b(?:will|plans?|planned|planning|expect\w*|intends?|propos\w+|upcoming|schedul\w+|to\s+(?:commence|"
                           r"begin|start|conduct|complete|carry\s+out))\b")
    deal_frame = "hist"
    # the headline names whom the ground comes from ("... Option to Acquire the X Property from the Y Syndicate")
    hl_vendor = bool(re.search(r"\b(?i:acquir\w*|option\w*|purchas\w*)\b.{0,80}\b(?i:from)\s+(?:the\s+)?(?:[A-Z][\w.&'-]*\s*){1,5}", hn))
    if deal_rel:
        ev = set()
        for x in lead[:40]:
            yrs = [int(y) for y in re.findall(r"\b(?:19[5-9]\d|20[0-4]\d)\b", x)]
            if not ry or future_rx.search(x) or not work_rx.search(x) or _HIST.search(x) or re.search(
                    r"(?i)\b(?:previous|prior|past|earlier|former|historic\w*)\b", x):
                continue
            if own_rx.search(x):
                if re.search(r"(?i)\bdue[\s-]diligence\b", x) or yrs and max(yrs) >= ry and not _RESTATED.search(x):
                    ev.add("own_new")
                elif yrs and max(yrs) < ry or _RESTATED.search(x):
                    ev.add("own_old")
            elif yrs and min(yrs) >= ry - 2 and not _RESTATED.search(x) and (vendor_rx.search(x) or hl_vendor or re.search(
                    r"\bby\s+(?:the\s+)?[A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){0,3}\s+(?:in|during)\s+(?:19|20)\d\d\b", x)):
                ev.add("vendor_new")
        if ev == {"own_old"}:
            deal_frame = "drop"
        elif ev and "own_old" not in ev:
            deal_frame = "new"
        elif not ev and not any(_HIST.search(x) or ry and any(int(y) <= ry - 5 for y in re.findall(
                r"\b(?:19[5-9]\d|20[0-4]\d)\b", x)) for x in lead[:40]):
            deal_frame = "drop"                         # no word of whose work it is: the deal is the news

    # 1.0.2: another company's discovery or project named as a comparison ("geology similar to that of X Resource's new
    # gold discovery, Gunners Cove"): results quoted for that place are the neighbour's
    nb_places = set()
    for mq in re.finditer(r"\b([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,3})(?:'s|\u2019s)\s+(?:new\s+|recent\s+)?(?:[\w-]+\s+){0,2}?"
                          r"(?:discovery|project|property|deposit|mine)\s*,?\s+(?:the\s+)?([A-Z][\w-]+(?:\s+[A-Z][\w-]+){0,2})",
                          " ".join([h] + lead[:12])):
        owner = mq.group(1)
        if not any(x and (x in owner or owner in x) for x in shorts + [issuer]) and not re.match(r"(?i)the\s+company\b", owner):
            nb_places.add(mq.group(2))
    # 1.0.2: the news is survey data bought or acquired: its geophysics rows are historical, other kinds are background
    data_bought = bool(re.search(r"(?i)\b(?:purchas\w+|acquir\w+|acquisition|obtain\w+|bought)\s+(?:of\s+)?(?:[\w-]+\s+){0,7}?"
                                 r"\(?(?:geophysical|survey|IP|EM|magnetic|airborne|chargeability|resistivity|gravity|polari[sz]ation)\)?\s+(?:[\w-]+\s+)"
                                 r"{0,2}?data\b", " ".join([hn] + lead[:2])))
    # 1.0.3: a release whose only electrical survey is magnetotelluric (CSAMT, AMT, MT) reports resistivity from that survey,
    # not from an IP survey
    news_txt = " ".join(news)
    mt_only = bool(re.search(r"\b(?:CSAMT|AMT|MT)\b|(?i:magnetotelluric)", news_txt)) and not re.search(
        r"\bIP\b|\bDCIP\b|(?i:induced[\s-]polari[sz]ation|chargeabilit)", news_txt)
    hl_hist_vals = {(g[1], g[3]) for x in lead if _old_work(x) and not own_rx.search(x) and h[:60] not in x for g in _grades(x)
                    if (_hist_split(x, ry, own_rx) or (lambda _p: True))(g[0])}
    hl_echo = any((g[1], g[3]) in hl_hist_vals for g in _grades(h))
    restated_at = set()
    inh_sents = set()                                   # 1.0.4: sentences read with an inherited kind (they add grades, not rows)
    last_typed = None                                   # 1.0.4: (sentence, kind, historical) of the last body sentence naming a kind
    hl_kinds = hl_type_set & set(ROCK + GEOCHEM)
    list_sents = {}                                     # 1.0.3: kind -> list sentences that name it beside another
    list_type = {}                                      # 1.0.3: (sentence, list) -> the kind its grades go to
    for i, s in enumerate(news):
        is_hl = i == 0
        if is_hl and hl_plan:
            continue
        tl = _types_in(s)
        if is_hl and hl_ctx:
            tl = [(p, t) for p, t in tl if not (t == "geophysics" and p in hl_ctx or p in geo_ctx)]
        inh = None
        if not tl and not is_hl and _grades(s) and _SAMPLE_WORD.search(s) and not _DRILL.search(s):
            # 1.0.4: a graded sentence that names no sample type ("The other two samples assayed 15.05 and 7.06 g/t Au",
            # "Of the 148 samples ... ranging up to 0.34% nickel") goes on with the kind the sentence before named, else
            # with the one rock or geochemical kind the headline names
            if last_typed and i - last_typed[0] <= 2:
                inh = last_typed[1:]
            elif len(hl_kinds) == 1:
                inh = (next(iter(hl_kinds)), False)
            if inh and inh[0] in GEOCHEM and not any(g[2] in ("ppm", "ppb") for g in _grades(s)):
                inh = None                              # a geochemical kind's values are written in ppm / ppb
            if inh:
                tl = [(0, inh[0])]
                inh_sents.add(s)
        if not tl and not (is_hl and hl_generic):
            continue
        hist = _old_work(s) or bool(inh and inh[1]) or not is_hl and bool(_KNOWN_OCC.search(s)) or not is_hl and i + 1 < len(news) and bool(re.match(
            r"(?i)(?:this|these|the)\s+(?:[\w-]+\s+)?(?:samples?|values?|results?|anomal\w+)\s+(?:was|were|is|are|came|comes?)\b",
            news[i + 1])) and _old_work(news[i + 1])        # 1.0.3: "... 275 ppb Au stream sediment. This sample was the
                                                            # highest value from the 1981 government program."
        if hist and re.search(r"(?i)\b(?:we|our|the\s+company|" + re.escape(issuer.split()[0] if issuer else "@@") +
                              r")\s+(?:collected|took|sampled|completed)\b|\bthis\s+(?:year|season|summer|fall|spring)\b|\bnew\b", s):
            hist = bool(re.search(r"(?i)\b(?:historical|previous\s+operators?)\b[^.]{0,60}\b(?:returned|grading|assay|values?)\b", s))
        # 1.0.1: "previous trenching returned 132 m at 0.5% Cu": older work; the company's own earlier sampling, cited to
        # its news release, is restated (no row), anyone else's is historical
        if not is_hl and re.search(r"(?i)\b(?:previous|prior|earlier|past|former)\s+(?!to\b|than\b)(?:\w+\s+)?(?:trenching|trenches|sampling|"
                                   r"soil\s+(?:sampling|surveys?|geochemistry)|rock\s+sampling|surveys?|prospecting)\b", s):
            if re.search(r"(?i)\b(?:news|press)\s+releases?\b|\b(?:our|we|the\s+company'?s?)\b" + (
                    r"|\b" + re.escape(issuer.split()[0]) + r"\b" if issuer else ""), s):
                continue
            hist = True
        # 1.0.2 (2026-10-01): kinds the headline reports as new findings before its review words stay new
        # 1.0.3: the company's own new or follow-up survey or sampling, in a release that also reviews older data, is new
        own_new_s = hist_rel and not is_hl and not hist and not hl_techrep and (own_rx.search(s) or re.search(
            r"(?i)\b(?:new|recent(?:ly\s+completed)?|follow[\s-]?up|this\s+year'?s?|current)\s+(?:[\w-]+\s+){0,3}?(?:surveys?|"
            r"sampling|programs?|programmes?|samples?)\b", s) or ry and any(int(y) >= ry for y in re.findall(r"\b20[0-4]\d\b", s)))
        hist = hist or hist_rel and not (new_hl_types & {t for _p, t in tl}) and not own_new_s or deal_rel and is_hl
        # 1.0.4: a sentence that quotes the release's own new results beside older work by others ("rock chip samples assayed
        # 6.76% WO3 ... historic USBM sampling returned 8.48%"): each grade goes with the nearest old- or new-work cue before it
        split = _hist_split(s, ry, own_rx) if not is_hl and not hist_rel and not deal_rel else None
        if deal_rel and not is_hl and not hist and i > 1 and _HIST.search(news[i - 1]) and not (own_rx.search(s) or vendor_rx.search(s)):
            hist = True                                 # 1.0.2: the sentence goes on with the older work just named
        if deal_rel and not is_hl and not hist:
            if deal_frame == "drop":
                continue                                # 1.0.2: the company's own earlier results: restated background
            hist = deal_frame == "hist"
        own_prev = re.search(r"(?i)\b(?:our|the\s+company'?s|" + re.escape(issuer.split()[0] if issuer else "@@") +
                             r"'?s?)\s+(?:\w+\s+){0,2}(?:previous|prior|earlier|initial|first|20\d\d)\s+(?:\w+\s+){0,2}"
                             r"(?:program|campaign|sampling|work|phase|results?)", s)
        if not is_hl and _RESTATED.search(s) and (not hist or own_prev):
            restated_at.add(i)
            continue
        # 1.0.2: a sentence that goes on from a restated lead-in ("Last month, X reported results from its initial
        # program." / "... (see news release dated ...). In previous sampling.") is restated too, unless it says it is new
        # or dates itself this year
        if not is_hl and not hist and not _grades(news[i - 1]) and (
                i - 1 in restated_at and re.search(r"(?i)(?<!previously\s)\b(?:reported|announced|released|disclosed|published)\b"
                                                   r"[^.]{0,80}?\bresults?\b", news[i - 1]) or
                i - 2 in restated_at and len(news[i - 1]) < 80 and re.search(r"(?i)\b(?:previous|prior|earlier|past)\b",
                                                                              news[i - 1])) and not re.search(
                r"(?i)\b(?:new|newly|recent(?:ly)?|latest|additional|further|follow[\s-]?up|current|received|this\s+(?:year|"
                r"season|summer|program))\b", s) and not (ry and any(int(y) >= ry for y in re.findall(r"\b20[0-4]\d\b", s))):
            continue
        if not is_hl and _NEIGHBOUR.search(s):
            continue
        if not is_hl and nb_places and any(re.search(r"\b" + re.escape(pl) + r"\b", s) for pl in nb_places) and\
                not own_rx.search(s):
            continue                                    # 1.0.2: results at a neighbour's named discovery
        grades = _grades(s, thresholds=True)            # 1.0.4b: a row never rests on explicit values only
        kinds_s = [(_p, t) for _p, t in tl if t in ROCK + GEOCHEM + ("brine", "bulk")]
        if kinds_s and not is_hl:
            last_typed = (i, kinds_s[-1][1], hist if split is None else split(kinds_s[-1][0]))
        plan = _PLAN.search(s)
        drill = _DRILL.search(s)
        result_word = _RESULT.search(s)
        if not is_hl and plan and not grades and not re.search(r"(?i)\b(?:identif|outlin|defin|delineat|reveal|confirm|returned|"
                                                               r"anomal|conductor|highlight|detect)\w*", s):
            continue
        pos_types = tl if tl else [(0, "grab")]
        seen_t = set()
        # rows carried by grades: each grade goes to its own sample type
        for gpos, v, u, met, gend in grades:
            if drill and not tl:
                continue
            if is_hl and hl_interval and _width_for(s, gpos, gend) is not None:
                continue                                # 1.0.3: a headline drill interval ("historical assays including
                                                        # 115.4 metres at 1.21% Li2O") is no sample row, old or new
            if not is_hl and re.search(r"(?i)\bthe\s+$", s[max(0, gpos - 5):gpos]):
                continue                                # 1.0.2: "where the 244 g/t Au rock chip was found": a known sample
            t = _row_type_for(s, pos_types, gpos, gend)
            # 1.0.3: one sample set named as a list of rock kinds ("forty chip, channel and grab samples range from 4.7%
            # zinc (over 0.6 m)", "channel and chip sample highlights include"): its grade is the set's. A grade given over a
            # length goes to the first kind named that has a length (chip, channel, trench); a point grade to the first
            # point-sample kind (grab, rock), else the first kind
            ml = [q for q in _ROCK_LIST.finditer(s[:gpos]) if not any(q.end() < pp < gpos for pp, _t in pos_types)]
            if ml and (i, ml[-1].start()) in list_type:
                t = list_type[(i, ml[-1].start())]     # the set's later grades follow its first one
            elif ml:
                items = re.findall(r"(?i)(?:rock[\s-]+)?" + _ROCK_LIST_W, ml[-1].group(0))
                # "rock chip" with no length is a grab sample (guide SR); with a length it is a chip sample
                kinds = [("grab" if re.match(r"(?i)rock[\s-]+chip", x) else _ROCK_WORD.get(x.lower(), "grab")) for x in items]
                wl = _width_for(s, gpos, gend)
                wk = [k for k in kinds if k in WIDTH_TYPES] or ["chip" for x in items if re.match(r"(?i)rock[\s-]+chip", x)]
                t = (wk or kinds)[0] if wl is not None else next((k for k in kinds if k not in WIDTH_TYPES), kinds[0])
                for k in kinds:
                    list_sents.setdefault((k, hist), set()).add(s)  # the other kinds in the list are reported here too
                list_type[(i, ml[-1].start())] = t
            if t is None or t == "mapping":
                t = "grab" if (is_hl and hl_generic) or re.search(r"(?i)\bsampl(?:es?|ing|ed)\b|\bprospecting\b", s) else None
            if t is None or t == "geophysics":
                continue
            # 1.0.3: a geochemical anomaly or grid named as the place of rock samples ("rock samples from other parts of the
            # main soil anomaly include 15.9 g/t gold") does not hold their grade; heavy-mineral concentrate values (HMC,
            # often g/t) are till results
            geo_place = bool(re.search(r"(?i)\b(?:grab|chip|channel|rock|outcrop|float|boulder)\s+samples?\b[^.;]{0,40}?\b(?:from|within|"
                                       r"in|inside|of|on|across|over|along)\s+(?:the\s+|a\s+|an\s+)?(?:[\w-]+\s+){0,3}?(?:[\w-]+[\s-]+in[\s-]+)?"
                                       r"(?:soil|till|sediment)[\s-]+(?:anomal\w*|grids?|trends?|targets?|areas?|corridors?)\b[^.;]{0,40}$",
                                       s[max(0, gpos - 160):gpos]))
            if t in GEOCHEM and u not in ("ppm", "ppb") and (geo_place or not re.search(
                    r"(?i)\b(?:soil|till|sediment|silt|BLEG|biogeochem\w*)\b[^.;]{0,40}$", s[max(0, gpos - 60):gpos])) and\
                    not (t == "till" and re.search(r"(?i)\bheavy[\s-]mineral|\bHMC\b", s[max(0, gpos - 200):gpos])):
                rk = [pt for pp, pt in pos_types if pt in ROCK and pp <= gpos + 60]
                t = rk[-1] if rk else ("grab" if re.search(r"(?i)\brock|\bgrab|\bsamples?\b", s) else None)
                if t is None:
                    continue
            if is_hl and hl_type_set and t not in hl_type_set:
                t = sorted(hl_type_set, key=lambda x: SAMPLE_TYPES.index(x))[0] if len(hl_type_set) == 1 else t
            if t == "trench" and grab_in_trench:
                t = "grab"
            if u == "mg/L" and t != "other_geochem":
                t = "brine"                                 # 1.0.1: a dissolved grade (mg/L Li) is a brine sample
            if drill and re.search(r"(?i)\b(?:hole|DDH|drill\w*|intersect\w*|core)\b", s[max(0, gpos - 90):gpos]) and\
                    not re.search(r"(?i)\b(?:trench|channel|chip|grab|rock|soil|surface)\b", s[max(0, gpos - 60):gpos]):
                continue                                    # a drill interval in a mixed sentence
            if re.match(r"(?i)[^.;]{0,40}?\b(?:from|fr\.?)\s+\d[\d.,]*\s*(?:m|metres?|meters?|ft|feet)\b(?!\s*(?:wide|long|thick|of|away))",
                        s[gend:gend + 60]) and re.search(r"\d\s*(?:m|metres?|meters?|ft|feet)\s*(?:@|at|of|grading)", s[max(0, gpos - 40):gpos + 1]):
                continue                                    # 1.0.2: "6.79m @ 3.14% Cu from 80.47m": a hole's interval
            if plan and not result_word and not is_hl:
                continue
            w = _width_for(s, gpos, gend) if t in WIDTH_TYPES or t in ("grab", "bulk") else None
            if t in ("grab", "bulk") and w is not None:
                body_w = [x for x in (_types_in(" ".join(lead[:25]))) if x[1] in WIDTH_TYPES]
                if re.search(r"(?i)\bchip", s):
                    t = "chip"
                elif is_hl and body_w:
                    t = body_w[0][1]                        # "Samples 5.8 m at 3.1% Cu": the release's channel or trench row
                elif t == "bulk":
                    t = "channel"
            # 1.0.2: a headline grade that the body gives as older work by others is historical
            hg = hist if split is None else split(gpos)
            add(t, i, s, gpos, hg or is_hl and hl_echo, (gpos, v, u, met, gend, is_hl),
                w if t in WIDTH_TYPES else None)
            seen_t.add(t)
        # rows carried by anomalies, surveys and findings
        for p, t in tl:
            if t in seen_t and t not in ANOMALY_TYPES:
                continue
            if t in ROCK + ("bulk", "brine") and not grades:
                if is_hl and t in ROCK and _HL_ROCK_RES.search(s) and not plan and not re.match(r"(?i)(?:rock|surface)\b", s[p:p + 8]):
                    add(t, i, s, p, hist)               # 1.0.4: "Channel Assays Extend ...", "Results from Channel Sampling"
                elif is_hl and t in ("bulk", "brine") and result_word and not plan and (t == "bulk" or re.match(
                        r"(?i)brines?\s+(?:samples?|sampling|assays?|results?|grades?|values?|analys[ie]s|concentrations?|chemistry)\b|"
                        r"brines?\b[^.;]{0,40}?\d[\d,.]*\s*mg/l", s[p:p + 80])):
                    add(t, i, s, p, hist)               # 1.0.2: "brine drill targets", "lithium brine project": no sample
                continue
            if t == "mapping":
                if not grades and not plan and not drill and\
                        (re.search(r"(?i)\b(?:mapping|prospecting|reconnaissance|mapped)\b[^.]{0,120}\b(?:identif|discover|outlin|delineat|"
                                   r"trac|confirm|reveal|found|expos|uncover|recogni|document|extend)\w*\b[^.]{0,80}" + _MAPPING_THING.pattern[4:], s) or
                         re.search(r"(?i)\b(?:identif|discover|outlin|delineat|trac|confirm|reveal|found|expos|uncover|recogni|"
                                   r"document|extend)\w*\b[^.]{0,80}\b(?:by|during|through)\s+(?:geological\s+)?(?:mapping|prospecting)", s)):
                    add("mapping", i, s, p, hist)
                continue
            if t in ANOMALY_TYPES:
                near = s[max(0, p - 120):p + 160]
                finding = re.search(r"(?i)\b(?:identif\w+|outlin\w+|defin\w+|delineat\w+|reveal\w+|confirm\w+|detect\w+|highlight\w*|"
                                    r"return\w*|show\w*|indicat\w+|anomal\w+|conductors?|chargeab\w+|resistiv\w+|trends?|highs?|lows?|"
                                    r"results?|values?|up\s+to|peak|elevated|coincident|targets?)\b", near)
                if not finding:
                    continue
                if drill and t == "geophysics" and re.search(r"(?i)\bdrill\w*\s+(?:test|target)|\bborehole\s+(?:EM|geophysics)|"
                                                            r"\bdownhole\b", s):
                    continue
                if t == "geophysics":
                    sv = _survey(s[p:p + 40])
                    if sv == "other":
                        sv = _survey(s[max(0, p - 40):p + 60])
                    if sv == "IP" and mt_only:
                        sv = "MT"                       # 1.0.3: the resistivity of a CSAMT / MT survey is that survey's
                    if sv == "EM" and re.match(r"(?i)conduct", s[p:p + 8]):
                        other = [x for x in (_survey(s[:p]), _survey(s[p + 8:])) if x not in ("other", "EM")]
                        if other or re.search(r"(?i)\b(?:MT|magnetotelluric|IP|induced|resistiv)", s):
                            continue                        # "a conductive anomaly" in an MT or IP result is that survey's
                    if not is_hl and not re.search(r"(?i)\bsurvey|\bdata\b|\bflown\b|\binversion|\bmodel", s):
                        continue
                    if sv == "other" and (geo_specific or not (is_hl or re.search(r"(?i)\bgeophysic\w*\s+(?:survey|results?|data)|"
                                                                                   r"\bairborne\s+survey", s))):
                        continue
                    if not re.search(r"(?i)\banomal|\bconductor|\bchargeab|\bresistiv|\bhighs?\b|\blows?\b|\btargets?\b|\btrends?\b|"
                                     r"\bfeatures?\b|\bstructures?\b|\blineaments?\b|\bidentif|\boutlin|\bdefin|\bdelineat|\breveal|"
                                     r"\bconfirm|\bdetect|\bshow", near):
                        continue
                    if not is_hl and not re.search(r"(?i)\b(?:survey|data|results?|anomal\w*|conductors?|identified|outlined|"
                                                   r"defined|interpreted|inversion|modell?ing)\b", s):
                        continue
                    add("geophysics", i, s, p, hist, survey=sv)
                else:
                    add(t, i, s, p, hist)
                    seen_t.add(t)
    # decide which rows stand
    out = []
    wide_ids = set()
    for k, r in rows.items():
        st = r["sample_type"]
        hl = r["first"][0] == 0
        n_sents = len((set(r["sents"]) - inh_sents) | list_sents.get((st, r["historical"]), set()))
        if not hl and r["first"][0] > 30 and not r["grades"]:
            continue
        an = _anomaly(([h] if (hl or st in hl_type_set) else []) + r["sents"], st) if st in ANOMALY_TYPES else None
        cnt = _count(([h] if hl else []) + r["sents"] + [x for x in sents if x not in r["sents"]], st,
                     tuple(x["sample_type"] for x in rows.values() if x["sample_type"] in ROCK and not x["historical"]))\
            if st not in ("geophysics", "mapping") and not r["historical"] else None
        if r["historical"]:
            if not (r["grades"] or (an and (an.get("metal") or an.get("length_m"))) or cnt):
                continue                                # historical rows need a value (rule SH)
            if st == "geophysics" and not (an and an.get("length_m")):
                continue
        elif hl_plan and (not r["grades"] or PLAN_NO_ROWS):
            continue                                    # a program start: only reported grades make a row
        elif st in ANOMALY_TYPES and not hl and not r["grades"] and st not in hl_type_set:
            # a survey mentioned in passing: it needs a finding with some substance
            if not (an and (an.get("metal") or an.get("length_m"))) and not cnt and n_sents < 2:
                continue
        if hl_done and not r["grades"] and not (an and (an.get("metal") or an.get("length_m")) and st not in hl_type_set):
            continue                                    # "completes soil program": no finding yet (1.0.1: nor a body anomaly
                                                        # standing in for the program the headline completes)
        if HEADLINE_ONLY and not hl:
            continue
        if st in GEOCHEM and any(_AUGER_RES.search(x) for x in r["sents"]) and\
                not any(_AUGER_TOOL.search(x) for x in r["sents"] + lead[:25]):
            continue                                    # 1.0.3: auger assays are drilling (guide), not a soil survey
        wide = False
        if STRICT_ROWS and not hl and not (r["grades"] and n_sents >= 2):
            # 1.0.1 (widened where the rows stay right): a survey method the headline announces, reported in the body
            # ("reports airborne geophysical survey results" -> the magnetics and EM findings), and a rock sample type
            # graded once in the lead of a release whose headline announces rock sampling
            if st == "geophysics" and not r["historical"] and "geophysics" in hl_type_set and (
                    r["survey_type"] in hl_methods if hl_methods else
                    r["first"][0] < 15 and r["survey_type"] not in ("lidar", "remote_sensing", "other")) and\
                    _method_found(r["sents"] + lead[:25], r["survey_type"]):
                wide = True
            elif st in ("grab", "chip", "channel") and not r["historical"] and r["grades"] and r["first"][0] < 25 and\
                    (hl_type_set & set(ROCK) or _GENERIC_HL.search(h) and not hl_type_set or hl_grades and not hl_type_set or
                     lead_rock_res and not hl_type_set):
                wide = True
            elif GEO_WIDE and st in ("soil", "till", "sediment") and not r["historical"] and r["first"][0] < 25 and\
                    n_sents >= 3 and an and (an.get("metal") or an.get("length_m")) and not (hl_type_set - {st}) and\
                    (cnt or any(_GEO_RES.search(x) for x in r["sents"])) and\
                    not any(TCUE[st].search(x) and (_old_work(x) or _HL_ANNOUNCED.search(x)) for x in r["sents"] + lead):
                # rev c: not when the release also presents that kind as older or already-announced work
                wide = True                             # 1.0.4: a geochemical survey the release returns to, with its anomaly
            elif st == "brine" and not r["historical"] and r["first"][0] < 25 and hl_generic and\
                    any(x[3] == "mg/L" for x in r["grades"]):
                wide = True                             # 1.0.4: "reports sampling results" over brine values
            elif HIST_WIDE and st in ROCK and r["historical"] and r["grades"] and r["first"][0] < 30 and not hl_plan and\
                    not hl_drill and\
                    any(_HIST_STRONG.search(x) for x in r["sents"]) and\
                    not all(_DRILL.search(news[g[0]]) or _HIST_NOT_SAMPLE.search(news[g[0]]) for g in r["grades"]) and not (ry and (lambda ys: ys and min(ys) >= ry - 2)(
                        [int(y) for x in r["sents"] for y in re.findall(r"\b(?:19[0-9]\d|20[0-4]\d)\b", x)])):
                wide = True                             # 1.0.4: older work by others the release quotes with a grade
            else:
                continue                                # narrowed: the headline's rows, and body rows the release returns to
        # mapping rows are for findings without assays (1.0.2, 2026-10-01: judged against the rock rows that stand, below)
        lone_map = st == "mapping"
        if hl_drill_only and not hl and not r["grades"] and st not in ("geophysics",):
            continue
        if desk_rel and not r["historical"] and st not in new_hl_types:
            continue                                    # 1.0.1: desktop work, no new result
        if hl_drill and not r["historical"] and st not in drill_keep:
            continue                                    # 1.0.1: a drill release's surface / geophysics background
        if data_bought and st != "geophysics":
            continue                                    # 1.0.2: a release about bought survey data
        if st == "bulk" and not r["grades"] and not re.search(r"(?i)\bbulk[\s-]sampl\w*\s+results?\b", h) and\
                not hl_bulk_grade:      # 1.0.2 (2026-10-01): "bulk sample returns 4.81% light rare earth oxide head grade"
            continue                                    # 1.0.1: a bulk row is its result (nuggets seen: no row)
        if st in hl_status_only and not r["grades"]:
            continue                                    # 1.0.1: named in the headline only as work done or planned
        # best grade (rule SB): the headline's for this type, else the highest of the lead metal
        g = None
        grs = r["grades"]
        hg = [x for x in grs if x[6]]
        pool = hg or grs
        if hg and all(x[9] for x in hg) and any(not x[9] and x[4] == hg[0][4] and x[3] == hg[0][3] for x in grs):
            # the headline gives only an average (rule SB4): take the peak of that metal
            pool = [x for x in grs if not x[9] and x[4] == hg[0][4] and x[3] == hg[0][3]]
        if st in GEOCHEM and any(x[3] in ("ppm", "ppb") for x in pool):
            pool = [x for x in pool if x[3] in ("ppm", "ppb")]        # a soil value is written in ppm / ppb
        elif st in GEOCHEM:
            pool = [x for x in pool if not (x[3] == "oz/t" or x[3] == "g/t" and x[2] >= 10)]   # 247 g/t is a rock
        if pool:
            lead_metal = pool[0][4]
            same = [x for x in pool if x[4] == lead_metal and x[3] == pool[0][3]]
            same = [x for x in same if not x[9]] or same               # an average is never best (rule SB4)
            ex = [x for x in same if not x[10]]                        # nor a threshold ("> 300 ppm Cu") ...
            if ex and max(x[2] for x in ex) >= max(x[2] for x in same):
                same = ex                                               # 1.0.4b: ... unless it is the highest value stated
            if st in WIDTH_TYPES and hg:
                g = hg[0]                               # the headline's lead interval (rule SN)
            elif st in WIDTH_TYPES:
                withw = [x for x in same if x[7] is not None and not x[8]] or [x for x in same if x[7] is not None]
                g = max(withw, key=lambda x: x[2]) if withw else max(same, key=lambda x: x[2])
            else:
                g = max(same, key=lambda x: x[2])
        if g is None and st == "brine":
            # 1.0.1: "up to 237 mg/L at the second well": a brine value written without its metal
            for x in ([h] if hl else []) + r["sents"]:
                mb = re.search(r"(?i)(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*mg/l\b", x)
                if mb:
                    mt = "Li" if re.search(r"(?i)\blithium\b|\bLi\b", h + " " + x) else None
                    g = (0, mb.start(), _num(mb.group(1)), "mg/L", mt, mb.end(), hl, None, False, False, False)
                    break
        # channel samples cut in trenches are trench samples (convention). 1.0.4: only when the release reports trench results
        # of its own beside them, or ties the channel samples to a trench ("from trench TR-11", "across the trench"); a
        # "trenching program" or trenches named as places for other things leave the channel row as the release names it
        if st == "channel" and (any(k2[0] == "trench" and k2[3] == r["historical"] and r2["grades"] for k2, r2 in rows.items()) or
                                any(_IN_TRENCH.search(x) for x in r["sents"])):
            st = "trench"
        l20 = " ".join(lead[:20])
        if st == "grab" and hl and hl_generic and not any(t == "grab" and not re.match(r"(?i)surface\s+samples?\b", l20[p0:p0 + 20])
                                                          for p0, t in _types_in(l20)):
            # 1.0.3: "surface samples" names no sampling method: a release whose only method is channel keeps it
            spec = {t for _p, t in _types_in(" ".join(lead[:20])) if t in WIDTH_TYPES}
            if len(spec) == 1:
                st = spec.pop()
                if st == "channel" and re.search(r"(?i)\btrench", " ".join(lead[:12])):
                    st = "trench"
        row = {"sample_type": st, "survey_type": r["survey_type"], "project": r["project"], "target": None,
               "historical": r["historical"] or data_bought and st == "geophysics", "operator": None,
               "best_grade": ({"value": g[2], "unit": g[3], "metal": g[4]} if g else None),
               "width_m": (g[7] if g and st in WIDTH_TYPES else None),
               "anomaly": an, "sample_count": cnt,
               "line_km": None, "bulk_tonnes": None, "evidence": r["evidence"][:300]}
        if st == "geophysics":
            for s in r["sents"]:
                m = _LINEKM.search(s)
                if m:
                    row["line_km"] = _num(m.group(1))
                    break
        if st == "bulk":
            for s in r["sents"]:
                m = _TONNES.search(s)
                if m:
                    row["bulk_tonnes"] = _num(m.group(1))
                    break
        if wide:
            wide_ids.add(id(row))
        out.append((r["first"], row, lone_map and hl))
    # mapping rows give way to the new rock rows that stand (a headline mapping row only to assayed ones), not to a rock
    # mention that itself gives no row
    rock_new = [o for _f, o, _m in out if o["sample_type"] in ROCK and not o["historical"]]
    out = [(f, r) for f, r, mh in out if not (r["sample_type"] == "mapping" and rock_new and (
        not mh or any(o["best_grade"] for o in rock_new)))]
    out.sort(key=lambda x: x[0])
    # the same grade under two sample types: the generic one (a headline's "samples") is the specific one's shadow
    kept = []
    for f, r in out:
        g = r["best_grade"]
        twin = g and any(o is not r and o["best_grade"] and o["historical"] == r["historical"] and
                         abs(o["best_grade"]["value"] - g["value"]) < 1e-9 and o["best_grade"]["metal"] == g["metal"]
                         for _f, o in out)
        if twin and any(o is not r and o["sample_type"] == r["sample_type"] and o["project"] != r["project"] and
                        o["best_grade"] and abs(o["best_grade"]["value"] - g["value"]) < 1e-9 and (o in [x for _f2, x in kept])
                        for _f, o in out):
            continue
        if twin and r["sample_type"] == "grab" and any(o["sample_type"] in WIDTH_TYPES + ("bulk", "soil", "till") and
                                                      o["best_grade"] and abs(o["best_grade"]["value"] - g["value"]) < 1e-9
                                                      for _f, o in out if o is not r):
            continue
        kept.append((f, r))
    kept = [(f, r) for f, r in kept if r["historical"] or not (r["best_grade"] and any(
        o["historical"] and o["best_grade"] and o["sample_type"] == r["sample_type"] and
        abs(o["best_grade"]["value"] - r["best_grade"]["value"]) < 1e-9 for _f, o in kept))]
    # a project written two ways ("JPR Property" / "JP Ross Property"): one row per type
    final = []
    for f, r in kept:
        dup = next((o for _f, o in final if o["sample_type"] == r["sample_type"] and o["survey_type"] == r["survey_type"] and
                    o["historical"] == r["historical"] and _abbrev(o["project"], r["project"])), None)
        if dup:
            if r["best_grade"] and (not dup["best_grade"] or r["best_grade"]["metal"] == dup["best_grade"]["metal"] and
                                    r["best_grade"]["unit"] == dup["best_grade"]["unit"] and
                                    r["best_grade"]["value"] > dup["best_grade"]["value"] and r["sample_type"] not in WIDTH_TYPES):
                dup["best_grade"] = r["best_grade"]
            continue
        final.append((f, r))
    out = final
    # 1.0.1: a widened row never repeats a sample type (and survey method) another row already has
    # rev c: ... nor does a widened row cancel an earlier widened one (when two prospects' rows of a kind are both widened,
    # the first stands; once threshold values count, they no longer cancel each other out)
    out = [(f, r) for k, (f, r) in enumerate(out) if id(r) not in wide_ids or not any(
        o is not r and o["sample_type"] == r["sample_type"] and o["survey_type"] == r["survey_type"] and
        o["historical"] == r["historical"] and (id(o) not in wide_ids or k2 < k)
        for k2, (_f, o) in enumerate(out))]
    res["rows"] = [r for _f, r in out]
    if not res["rows"]:
        res["reason"] = "no sampling or geoscience result"
    return res


# ------------------------------------------------------------------ records
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["rows"]:
        return [F.Record(KIND, facts=[F.Fact("is_result", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"] or "none")], confidence=0.0)]
    out = []
    for r in a["rows"]:
        fs = [F.Fact("is_result", value_num=1.0)]
        flat = dict(r)
        g = r.get("best_grade") or {}
        flat["grade"], flat["grade_unit"], flat["grade_metal"] = g.get("value"), g.get("unit"), g.get("metal")
        flat["anomaly_json"] = json.dumps(r["anomaly"], sort_keys=True) if r.get("anomaly") else None
        flat["historical"] = 1.0 if r.get("historical") else 0.0
        for k in TXT_FIELDS:
            v = flat.get(k)
            if v not in (None, ""):
                fs.append(F.Fact(k, value_text=str(v)[:300]))
        for k in NUM_FIELDS:
            v = flat.get(k)
            if v is not None:
                fs.append(F.Fact(k, value_num=float(v)))
        out.append(F.Record(KIND, facts=fs, confidence=1.0))
    return out


def parse_records(rows_by_ordinal):
    """{ordinal: [(field, seq, value_num, value_text)]} -> the analyse()-shaped dict."""
    rows = []
    for ordinal in sorted(rows_by_ordinal):
        r = {k: None for k in TXT_FIELDS + NUM_FIELDS}
        yes = False
        for field_, seq, num, text in rows_by_ordinal[ordinal]:
            if field_ == "is_result":
                yes = num == 1.0
            elif field_ in TXT_FIELDS:
                r[field_] = text
            elif field_ in NUM_FIELDS:
                r[field_] = num
        if yes and r["sample_type"]:
            rows.append({"sample_type": r["sample_type"], "survey_type": r["survey_type"], "project": r["project"],
                         "target": r["target"], "historical": bool(r["historical"]), "operator": r["operator"],
                         "best_grade": ({"value": r["grade"], "unit": r["grade_unit"], "metal": r["grade_metal"]}
                                        if r["grade"] is not None else None),
                         "width_m": r["width_m"], "anomaly": json.loads(r["anomaly_json"]) if r["anomaly_json"] else None,
                         "sample_count": int(r["sample_count"]) if r["sample_count"] is not None else None,
                         "line_km": r["line_km"], "bulk_tonnes": r["bulk_tonnes"], "evidence": r["evidence"]})
    return {"is_result": bool(rows), "rows": rows}


JUDGED = ("sample_type", "survey_type", "project", "historical", "best_grade", "width_m", "anomaly", "sample_count")


def to_prediction(records):
    if not records:
        return None
    rows = {i: [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts] for i, rec in enumerate(records)}
    p = parse_records(rows)
    if not p["rows"]:
        return None
    return {"rows": [{k: r.get(k) for k in JUDGED} for r in p["rows"]]}


# The fingerprint (FP_AUTO_V1): this file whole, plus exactly the code it reaches in the Technical reader (T.) and the
# shared project-name helper (PN.); see portal/fingerprint.py.
SPEC = F.ExtractorSpec(NAME, VERSION, KIND, TAG, extract, FP.code_sha(__file__))


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

    fill = " The Company continues to advance its projects in Ontario and remains well funded." * 3
    lead = "Vancouver, British Columbia, March 2, 2026 -- ABC Gold Corp. (TSXV: ABC) (\"ABC\" or the \"Company\") "

    def rows(h, b, keys=("sample_type", "project")):
        out = []
        for r in analyse(h, lead + b + fill)["rows"]:
            t = []
            for k in keys:
                v = r[k]
                if k == "best_grade" and v:
                    v = (v["value"], v["unit"], v["metal"])
                t.append(v)
            out.append(tuple(t))
        return out

    eq("grab headline", rows("ABC Gold Grab Samples Return up to 12.5 g/t Au at the Alpha Project",
                             "is pleased to report that 37 grab samples collected at the Alpha Project returned up to 12.5 g/t Au.",
                             ("sample_type", "project", "best_grade", "sample_count")),
       [("grab", "Alpha Project", (12.5, "g/t", "Au"), 37)])
    eq("channel with width", rows("ABC Gold Channel Sampling Returns 9.4 m Grading 7.4 g/t Gold at the Alpha Project",
                                  "reports channel sampling results from the Alpha Project, including 9.4 m grading 7.4 g/t gold.",
                                  ("sample_type", "best_grade", "width_m")),
       [("channel", (7.4, "g/t", "Au"), 9.4)])
    eq("soil anomaly", rows("ABC Gold Soil Survey Outlines 1.9 km Gold Anomaly at the Alpha Project",
                            "reports that its soil sampling program at the Alpha Project outlined a gold-in-soil anomaly measuring "
                            "1,900 m by 650 m.", ("sample_type", "anomaly")),
       [("soil", {"kind": "anomaly", "metal": "Au", "length_m": 1900.0, "width_m": 650.0})])
    eq("IP survey", rows("ABC Gold IP Survey Identifies Chargeability Anomalies at the Alpha Project",
                         "reports that the induced polarization survey identified three strong chargeability anomalies.",
                         ("sample_type", "survey_type")), [("geophysics", "IP")])
    eq("a plan is not a result", rows("ABC Gold Begins Soil Sampling Program at the Alpha Project",
                                      "has commenced a soil sampling program at the Alpha Project; results are expected in the fall."), [])
    eq("drill results are not a row", rows("ABC Gold Drills 12 m of 3.1 g/t Au at the Alpha Project",
                                           "reports drill hole AB-26-001 intersected 12 m of 3.1 g/t Au."), [])
    eq("grades", [(v, u, m) for _p, v, u, m, _e in _grades("up to 3.02% copper and 59.6 g/t Ag, 1,590g/t silver, 405 mg/L Li")],
       [(3.02, "%", "Cu"), (59.6, "g/t", "Ag"), (1590.0, "g/t", "Ag"), (405.0, "mg/L", "Li")])
    recs = extract("ABC Gold Grab Samples Return up to 12.5 g/t Au at the Alpha Project",
                   lead + "reports 37 grab samples from the Alpha Project returned up to 12.5 g/t Au." + fill)
    p = to_prediction(recs)
    eq("round trip", [(x["sample_type"], x["best_grade"]["value"]) for x in p["rows"]], [("grab", 12.5)])
    eq("no-result record", to_prediction(extract("ABC Gold Closes Private Placement", lead + "has closed a private placement." + fill)),
       None)
    # ---- 1.0.1 behaviours
    two_grab = ("Grab samples collected at the Beta Property returned up to 8.2 g/t Au from quartz veins. "
                "The grab samples also returned up to 25 g/t Ag.")
    old_work = "The property was explored by previous operators in the 1980s. "   # 1.0.2: a deal says whose work it quotes
    eq("1.0.1 deal release: results are historical", rows("ABC Gold Signs Option Agreement to Acquire the Beta Property",
                                                          "has signed an option agreement to acquire the Beta Property. " + old_work +
                                                          two_grab,
                                                          ("sample_type", "historical")), [("grab", True)])
    eq("1.0.1 deal headline that reports a result: new", rows("ABC Gold Acquires the Beta Property and Samples 8.2 g/t Au",
                                                               "has acquired the Beta Property. " + two_grab,
                                                               ("sample_type", "historical")), [("grab", False)])
    eq("1.0.1 resource estimate: no row", rows("ABC Gold Announces Maiden Inferred Resource at the Beta Property",
                                               "announces a maiden inferred resource. " + two_grab), [])
    eq("1.0.1 financing: no row", rows("ABC Gold Closes Flow-Through Financing", "has closed a financing. " + two_grab), [])
    eq("1.0.1 drill result: surface samples are background", rows("ABC Gold Intersects 12 m of 3.1 g/t Au at the Beta Property",
                                                                    "reports drill hole BP-26-001 intersected 12 m of 3.1 g/t Au. " +
                                                                    two_grab), [])
    eq("1.0.1 drill start: restated samples are background", rows("ABC Gold Mobilizes Drill Rig to Test Vein Where Grab Samples Returned 8.2 g/t Au",
                                                                   "has commenced drilling at the Beta Property. " + two_grab), [])
    eq("1.0.1 result first, then drilling: kept", rows("ABC Gold Grab Samples Return 8.2 g/t Au and Company Plans Drilling",
                                                        "reports that " + two_grab), [("grab", "Beta Property")])
    eq("1.0.1 channel chip samples are one chip row", rows("ABC Gold Samples 5.2 g/t Au over 3.0 m at the Beta Property",
                                                            "reports channel chip samples returned 5.2 g/t Au over 3.0 m. Channel chip "
                                                            "samples from the east zone returned 2.1 g/t Au over 1.5 m.",
                                                            ("sample_type", "width_m")), [("chip", 3.0)])
    eq("1.0.1 grab samples taken from trenches stay grab", rows("ABC Gold Reports Assays up to 11.3 g/t Au at the Beta Property",
                                                               "received assays up to 11.3 g/t Au from 102 grab samples collected from quartz "
                                                               "veins uncovered by trenches. Trench T-22 samples returned up to 9.4 g/t Au. "
                                                               "Trench T-25 samples returned up to 8.0 g/t Au.", ("sample_type",)),
       [("grab",)])
    eq("1.0.1 a dissolved grade is brine", rows("ABC Lithium Samples 409 mg/L Li at Surface at the Beta Salar",
                                               "reports surface samples at the Beta Salar returned 409 mg/L Li.", ("sample_type",)),
       [("brine",)])
    eq("1.0.1 Mt is a place, not an MT survey", [t for _p, t in _types_in("soil samples at the Mt Todd project")], ["soil"])
    eq("1.0.1 soil gas is soil", [t for _p, t in _types_in("a soil gas survey outlined hydrogen anomalies")], ["soil"])
    eq("1.0.1 kinds named only as work completed", rows("ABC Gold Discovers New Showing, Completes Airborne Magnetic Survey and Soil "
                                                        "Program at the Beta Property",
                                                        "has completed an airborne magnetic survey that outlined several magnetic "
                                                        "anomalies. Soil samples outlined a gold anomaly; assays are pending."), [])
    eq("1.0.1 headline survey, methods in the body", rows("ABC Gold Reports Airborne Geophysical Survey Results at the Beta Property",
                                                         "reports results of the airborne survey flown in June. The magnetic survey "
                                                         "data outlined a 3 km long magnetic anomaly along the main shear.",
                                                         ("sample_type", "survey_type")), [("geophysics", "magnetics")])
    eq("1.0.1 desktop review: no new row", rows("ABC Gold Reviews Conductors on the Beta Property",
                                               "reports that a review of the airborne survey identified three conductors."), [])
    eq("1.0.1 a gravity plant is not a survey", [t for _p, t in _types_in("the gravity plant and its gravity circuit")], [])
    lead2 = "Vancouver, March 2, 2026 -- Discovery Metals Corp. (TSXV: DSC) (\"Discovery\" or the \"Company\") "
    eq("1.0.1 the issuer's name is not headline language",
       [(r["sample_type"], r["historical"]) for r in analyse("Discovery Metals to Acquire 100% of the Beta Property",
                                                               lead2 + "has agreed to acquire the Beta Property. " + old_work +
                                                               two_grab + fill)["rows"]],
       [("grab", True)])
    eq("1.0.1 earlier sampling cited to the company's release is restated",
       rows("ABC Gold Samples up to 8.2 g/t Au at the Beta Property",
            "reports grab samples returned up to 8.2 g/t Au. Previous channel sampling (ABC news release May 2, 2025) returned "
            "9.9 g/t Au over 1.0 m. Previous channel sampling at the zone returned 9.9 g/t Au over 1.0 m.",
            ("sample_type", "historical")), [("grab", False)])
    eq("1.0.1 a rock type graded once in the lead of a sampling release", rows(
        "ABC Gold Samples up to 12.5 g/t Au at the Beta Property",
        "reports grab samples returned up to 12.5 g/t Au. Grab samples from the west zone returned 3.3 g/t Au. Chip samples "
        "across the main vein returned 4.1 g/t Au over 2.0 m.", ("sample_type",)), [("grab",), ("chip",)])
    eq("1.0.1 previous workers' and cited results are historical", rows(
        "ABC Gold Provides Update on the Beta Property",
        "reports that previous workers collected grab samples grading up to 50.9 g/t Au at the Beta showing. Grab samples "
        "(Allen, 1982) returned up to 12 g/t Au at the Beta showing.", ("sample_type", "historical")), [("grab", True)])
    # ---- 1.0.2 behaviours (rows only for the release's own news)
    eq("1.0.2 award release: no row", rows("ABC Gold and Its Team Recognized with Discovery of the Year Award",
                                           "is pleased to announce it received the award for its Beta discovery. " + two_grab), [])
    eq("1.0.2 licence granted is a deal", rows("Exploration Licence Granted on the Beta Project",
                                               "announces that the exploration licence covering the Beta Project has been granted. " +
                                               old_work + two_grab, ("sample_type", "historical")), [("grab", True)])
    eq("1.0.2 lead announces the deal", rows("ABC Gold Expands Beta Project",
                                             "is pleased to announce it has expanded, through staking of 12 new claims, the Beta "
                                             "Property. " + old_work + two_grab, ("sample_type", "historical")), [("grab", True)])
    eq("1.0.2 historical drilling in the headline: new samples stay new", rows(
        "ABC Gold Samples 13.3% Copper; Rock Chip Results Support Historical Drilling Data at the Beta Property",
        "reports rock chip samples returned up to 13.3% Cu. Rock chip samples along strike returned 4.2% Cu.",
        ("sample_type", "historical")), [("grab", False)])
    eq("1.0.2 a lead that gives a hole's depth", rows("BP-67 ASSAYS END AT 502 FT (153 M) IN LI GRADE OF 1220 PPM, INCREASING WITH DEPTH",
                                                "is pleased to announce the assay results of BP-67, completed at a depth of 502 ft. "
                                                "Clay and mudstone were reached at 202 ft. The grade of 1220 ppm Li at the end of "
                                                "BP-67 is the highest yet."), [])
    eq("1.0.2 a generic grade headline over recent drilling", rows(
        "ABC Gold Discovers Second Gold Zone, Grades up to 36.4 g/t Au",
        "is pleased to provide an update on the recently completed drilling at the Beta prospect. Grab samples returned up to "
        "36.4 g/t Au. Grab samples from the pit returned 11.6 g/t Au."), [])
    lead3 = "Vancouver, August 4, 2020 -- ABC Energy Corp. (TSXV: ABE) (\"ABC\" or the \"Company\") "
    eq("1.0.2 deal: the company's own earlier work is restated", [
        r["sample_type"] for r in analyse("ABC Energy Amends Terms of Option to Acquire the Beta Project",
                                          lead3 + "has amended the option to acquire the Beta Project. In late 2018 Company "
                                          "consultants completed a reconnaissance sampling program at Beta. " + two_grab + fill)["rows"]],
       [])
    lead4 = "Toronto, October 8, 2019 -- ABC Resources Ltd. (TSXV: ABR) (\"ABC\" or the \"Company\") "
    eq("1.0.2 deal: the company's due-diligence sampling this year is new", [
        (r["sample_type"], r["historical"]) for r in analyse(
            "ABC Resources Granted Option to Acquire the Beta Property",
            lead4 + "has been granted an option to acquire the Beta Property. " + old_work + "In August 2019, ABC performed "
            "due diligence sampling at Beta. " + two_grab + fill)["rows"]], [("grab", False)])
    lead5 = "Vancouver, April 27, 2026 -- ABC Metals Corp. (CSE: ABM) (\"ABC\" or the \"Company\") "
    eq("1.0.2 deal: the prospector's recent work is new", [
        (r["sample_type"], r["historical"]) for r in analyse(
            "ABC Metals Options the Beta Property from a Yukon Prospector",
            lead5 + "has entered into an option agreement to acquire the Beta Property. " + old_work + "Exploration completed "
            "by the prospector in 2025 included grab sampling of the main vein. " + two_grab + fill)["rows"]], [("grab", False)])
    eq("1.0.2 deal: results with no word of whose work they are", rows("ABC Gold to Acquire the Beta Property",
                                                                       "has agreed to acquire the Beta Property. " + two_grab), [])
    eq("1.0.2 to drill and carry out soil surveys is a plan", rows(
        "ABC Gold to Drill the Beta Targets and Carry Out Soil Surveys",
        "reports it will drill the Beta zone. Soil samples outlined a gold anomaly. Soil samples returned up to 120 ppb Au."), [])
    eq("1.0.2 brine drill targets are not a brine sample", rows("ABC Lithium Identifies Multiple Brine Drill Targets on the Beta Project",
                                                               "identified brine drill targets from a seismic survey.",
                                                               ("sample_type",)), [])
    eq("1.0.2 an interval with its downhole depth is a hole's", rows(
        "ABC Gold Samples up to 4.2% Cu at the Beta Property",
        "reports rock chip samples returned up to 4.2% Cu. Rock chip samples near the pit include 6.79 m @ 3.14% Cu from 80.47 m.",
        ("sample_type", "best_grade")), [("grab", (4.2, "%", "Cu"))])
    eq("1.0.2 a geochemical anomaly named as the place of the news", rows(
        "ABC Gold Discovers New Gold Zone at the Beta Project within 2.2 Kilometre Gold-in-Soil Trend",
        "reports trench samples returned 9.1 g/t Au over 2 m. Trench T-2 returned 3.0 g/t Au over 12 m.", ("sample_type",)),
       [("trench",)])
    eq("1.0.2 the past perfect is an earlier result", rows(
        "ABC Gold Reports Trench Assays from the Beta Vein",
        "reports trench samples returned 37.5 g/t Au over 1.0 m. Trench T-3 returned 15.7 g/t Au over 0.6 m. Initial surface "
        "sampling had returned a grab sample of 109 g/t Au. Initial grab sampling had returned 5.6 g/t Au.", ("sample_type",)),
       [("trench",)])
    eq("1.0.2 a sentence that goes on with restated results", rows(
        "ABC Gold IP Survey Identifies Porphyry Target at the Beta Project",
        "reports a new IP survey outlined a 1.2 km long chargeability anomaly. The IP survey data defined a second chargeability "
        "high. Five new showings yielded grab samples up to 7.25% Cu (see ABC news release dated November 3, 2022). In previous "
        "sampling. A total of 17 rock grab samples returned values up to 9.06% Cu. Grab samples also returned up to 4.6 g/t Pt.",
        ("sample_type",)), [("geophysics",)])
    eq("1.0.2 guard: new results after a sentence that quotes earlier ones stay", rows(
        "ABC Gold Channel Samples Return 9.25 g/t Au at the Beta Property",
        "has received assays for its channel sampling program. Fifty channel samples were collected near the previously "
        "announced grab samples of 41.2 g/t Au. Channel highlights include 1.0 m at 9.25 g/t Au and 0.5 m at 2.2 g/t Au. "
        "Channel 4 returned 0.5 m at 1.9 g/t Au.", ("sample_type",)), [("channel",)])
    eq("1.0.2 results at a neighbour's named discovery", rows(
        "ABC Gold Acquires Three New Gold Projects",
        "has acquired three projects. The ground has geology similar to that of XYZ Metal's new gold discovery, Gunners Cove. "
        + old_work + "Grab samples collected in the Gunners Cove area assayed up to 2.14 g/t Au. Grab samples at Gunners Cove "
        "returned 9.1 g/t Ag."), [])
    eq("1.0.2 bought survey data: its geophysics is historical", rows(
        "Chargeability Target Identified in New IP Data",
        "is pleased to announce the purchase of private Induced Polarization (IP) data which has resulted in the discovery of a "
        "new chargeability target 1.9 km across. Trench samples returned 4.7 g/t Au over 23 m. Trench T8 returned 1.9 g/t Au "
        "over 11 m.", ("sample_type", "historical")), [("geophysics", True)])
    eq("1.0.2 a known sample referred to is not a result", rows(
        "ABC Gold Advances the Beta Project",
        "has recommenced work at Beta. Rock chip samples outlined a broad zone. The grid now covers the area where the 244 g/t "
        "Au grab sample was collected. A second grid covers the area where the 36.5 g/t Au grab sample was collected."), [])
    eq("1.0.2 a headline grade the body gives as older work", rows(
        "ABC Gold Outlines Drill Target, Rock Chip Samples up to 22 g/t Au",
        "reports on the Beta prospect. Historic underground sampling by previous operators in 2008 returned rock chip samples "
        "up to 22 g/t Au. Rock chip samples in the second working returned up to 8.2 g/t Au.",
        ("historical", "best_grade")), [(True, (22.0, "g/t", "Au")), (False, (8.2, "g/t", "Au"))])
    eq("1.0.2 a lead that announces plans", rows(
        "ABC Gold Provides Exploration and Health and Safety Update",
        "is pleased to provide an update on partner-funded exploration activities planned for 2026. Rock samples from the new "
        "exposures returned up to 0.47% Cu. Grab samples on the ridge returned up to 21.1 g/t Au."), [])
    # 1.0.2 (2026-10-01): full-text losses on tagged releases
    eq("1.0.2b drilling long ago in the lead does not make a sampling headline a drill release", rows(
        "ABC Gold Samples 21 g/t Gold at the Beta Target",
        "is pleased to announce it has located and sampled the Beta vein showings. As previously reported, XYZ Mines drilled "
        "extensively a series of veins near the boundary in the 1950s. Several grab samples from the vein returned 13 g/t and "
        "21 g/t gold.", ("sample_type", "best_grade")), [("grab", (21.0, "g/t", "Au"))])
    eq("1.0.2b a magnetic core is not drill core", rows(
        "ABC Metals Acquires the Beta REE Project, Initial Samples Returning up to 6.17% TREO",
        "has entered into an option agreement to acquire the Beta REE Project, a circular magnetic anomaly with a central magnetic "
        "core of 2 km in diameter. One sample taken by the vendor in 2025 returned 6.17% TREO.", ("sample_type", "historical")),
       [("grab", False)])
    eq("1.0.2b a drill program whose results are pending is not what a sampling headline reports", rows(
        "ABC Metals Samples 16% Cobalt at the Beta Project and Provides an Update",
        "is pleased to announce project updates. ABC completed ten core drill holes at the Gamma Zone. Gamma drill results are "
        "pending at this time. Grab samples at Beta returned up to 16% Co. Grab samples at Beta also returned 4.4% Co.",
        ("sample_type",)), [("grab",)])
    eq("1.0.2b guard: re-sampling of archived drill core stays drilling", rows(
        "ABC Gold Samples 50.9 g/t PGE over 0.45 metres at the Beta Property",
        "reports 50.9 g/t PGE over 0.45 metres at its Beta property. Results are from re-sampling of archived drill core from "
        "holes drilled in the 1970s."), [])
    eq("1.0.2b guard: a sampling headline over the release's own drill program stays drilling", rows(
        "ABC Gold Samples up to 8.62 g/t Au over 38 cm at Beta",
        "is pleased to announce results from the Phase 2 backpack drilling program at the Beta claims. The crew completed 27 "
        "short holes. Hole B-21 assayed 8.62 g/t Au over 38 cm."), [])
    eq("1.0.2b drill targets a release extends are the outcome of its surface results", rows(
        "ABC Gold Extends Drilling Targets at the Beta Property",
        "is pleased to announce the receipt of soil sample analytical results from the fall program. The soil sampling program "
        "identified gold soil anomalies with values up to 88 ppb Au. A total of 334 soil samples were collected.",
        ("sample_type",)), [("soil",)])
    eq("1.0.2b guard: drill targets over a drill-program lead stay a drill release", rows(
        "ABC Silver Identifies Drill Targets at Beta",
        "is pleased to provide an update for its second phase of drilling at Beta. The Company has identified locations for 20 "
        "drill pads. Channel sample 80 returned 568 g/t Ag over 0.5 m. Channel sample 81 returned 210 g/t Ag over 0.5 m."), [])
    eq("1.0.2b a resource named as the place of a new result", rows(
        "ABC Gold Reports up to 203 g/t Gold from Outcrop Sample Located 10 km South of Current Mineral Resource",
        "reports results from its regional program. Outcrop samples returned 203 g/t gold and 54.2 g/t gold.",
        ("sample_type", "best_grade")), [("grab", (203.0, "g/t", "Au"))])
    eq("1.0.2b recoveries assumed for a metal equivalent are not metallurgy", rows(
        "AuEq Assumes Mill Recoveries of 85% for Au. ABC Gold Channel Samples Average 9.22 g/t AuEq on the 3430 Sublevel",
        "announces results from a systematic underground channel sampling program. Channel samples averaged 9.22 g/t AuEq over a "
        "strike length of 130 m. Channel samples on the crosscut averaged 7.1 g/t AuEq.", ("sample_type",)), [("channel",)])
    eq("1.0.2b a trench grade named before a recovery figure is a sampling result", rows(
        "Initial Results from Trenching Return 5.26 g/t Gold with 85.9% Gravity Recovery from the Beta Property",
        "provides initial results for samples from the fall trenching program. Sample T-2 returned 5.26 g/t gold.",
        ("sample_type", "best_grade")), [("trench", (5.26, "g/t", "Au"))])
    eq("1.0.2b guard: a concentrate recovery headline stays metallurgy", rows(
        "ABC Produces High Recovery (89%) and High Grade Spodumene Concentrate (6.1% Li2O) from Beta Sample",
        "announces 4.47 tonnes of 6.09% Li2O concentrate from boulder samples."), [])
    eq("1.0.2b a corporate update with new sampling results", rows(
        "ABC Gold Provides Corporate Update and New Sampling Results",
        "provides a corporate update and new results from sampling completed this fall. Five continuous channel samples across "
        "a mineralized outcrop averaged 5.6 g/t gold over 4 m. Nine channel samples on the road returned 2.36% copper over 2 m.",
        ("sample_type",)), [("channel",)])
    eq("1.0.2b acquisition of survey data is not a deal", rows(
        "ABC Completes Acquisition and Interpretation of Aeromagnetic Drone Survey at Beta. Upcoming work to focus on new magnetic anomaly",
        "has completed detailed magnetic data acquisition for the project and identified a new magnetic anomaly of 6 x 2 km "
        "from the drone survey.", ("sample_type", "survey_type", "historical")), [("geophysics", "magnetics", False)])
    eq("1.0.2b a new survey finding named before the headline's review words stays new", rows(
        "ABC Identifies New Large IP Anomalies at Beta Compilation and Review of Historical Data Completed",
        "announces completion of the IP survey on Beta. The IP survey outlined three significant anomalies around a strong "
        "conductor.", ("sample_type", "survey_type", "historical")), [("geophysics", "IP", False)])
    eq("1.0.2b study targets beside the release's own sample grades", rows(
        "ABC Gold Continues Exploration of New Structural Study Targets and Samples up to 72.0 g/t Gold at the Rome Target",
        "reports that mapping and sampling of outcrops found within the Rome Target returned 72.0 g/t gold. Samples taken from "
        "the Rome Target returned an average grade of 42.18 g/t gold.", ("sample_type",)), [("grab",)])
    eq("1.0.2b a review in the headline's second clause", sorted({t for (t,) in rows(
        "Beta Zinc Property - Re-Analyses of Over-Limit Soil Samples; Gamma Zinc Property - Initial Review of LiDAR Survey Results",
        "announces that four soil samples from the Beta Zinc Property were re-analysed and reported values up to 128 ppm "
        "silver. The soil samples returned 12.7% combined zinc-lead.", ("sample_type",))}), ["soil"])
    eq("1.0.2b a completed survey whose headline highlights new targets", rows(
        "ABC Completes Airborne Radiometric Survey of the Beta Project Survey Highlights Multiple New Uranium Targets",
        "announces the initial results of the airborne radiometric survey. The radiometric survey outlined significant new "
        "thorium and uranium targets, including a thorium zone measuring 800 m x 450 m.", ("sample_type", "survey_type")),
       [("geophysics", "radiometric")])
    eq("1.0.2b a drill rig bought in a second clause", rows(
        "ABC Provides Further Results from the Alpha Target; Acquires RC Drill Rig",
        "provides results from 24 boulder samples at Alpha, with values from 11.6 to 200.3 g/t gold. Boulder samples also "
        "returned up to 1.13% Cu.", ("sample_type",)), [("grab",)])
    eq("1.0.2b a mapping finding is not displaced by a rock mention that gives no row", rows(
        "Detailed Mapping Identifies Extensive Quartz Veins and Discovers New Gold Occurrence at the Beta Project",
        "has mapped an area of extensive quartz veins at Beta. Mapping has also discovered a new gold occurrence associated with "
        "breccia dykes. The mapping identified a 200 m band of volcanic rocks. A single grab sample returned 1.4 g/t Au.",
        ("sample_type",)), [("mapping",)])
    eq("1.0.2b a bulk sample headline grade in an oxide the reader does not parse", rows(
        "Beta Deposit 30 Tonne Bulk Sample Returns 4.81% Light Rare Earth Oxide Head Grade",
        "announces initial composite head assay results for the 30 tonne bulk sample collected from its Beta Property.",
        ("sample_type",)), [("bulk",)])
    # ---- 1.0.3 behaviours (2026-10-02: row accuracy on releases that truly have sampling or geoscience news)
    eq("1.0.3 the resistivity of a CSAMT survey is MT, not IP", sorted(rows(
        "ABC Gold Reports Positive Results from Geophysical Surveys at the Beta Project",
        "announces results of a CSAMT survey and a ground gravity survey at Beta. The CSAMT survey was undertaken to identify zones "
        "of electrical resistivity and conductivity related to vein systems. Results of the CSAMT survey defined several "
        "kilometre-scale resistive zones (CSAMT anomalies). Results of the gravity survey define a basement high along the "
        "structural corridor.", ("sample_type", "survey_type"))), [("geophysics", "MT"), ("geophysics", "gravity")])
    eq("1.0.3 a method named only as a survey parameter gives no row", sorted(rows(
        "ABC Gold Announces Results of Airborne Geophysics Survey on the Beta Project",
        "has completed a detailed helicopter airborne geophysical survey over Beta and received the final report. Survey "
        "parameters comprise high-resolution helicopter magnetic, VLF and gamma-ray spectrometry at 100 metre line-spacing. "
        "Known mineralization is associated with well-defined areas of magnetic lows in the survey data.",
        ("sample_type", "survey_type"))), [("geophysics", "magnetics")])
    eq("1.0.3 one sample set named as a list of rock kinds", rows(
        "ABC Metals Outlines a Zinc Discovery at the Beta Project",
        "provides new results from Beta. Forty individual chip, channel and grab samples are reported and range from 4.7% zinc "
        "(over 0.6 m width) to 354 ppm zinc. Individual continuous channels include 10.9 metres @ 0.4% zinc. Channel samples on the "
        "ridge include 5.2 metres @ 0.3% zinc. Chip samples on the gossan returned 1.2% zinc over 2 m.",
        ("sample_type", "best_grade")), [("chip", (4.7, "%", "Zn")), ("channel", (0.4, "%", "Zn"))])
    eq("1.0.3 channel and chip sample highlights are one channel row", rows(
        "ABC Silver Reports Assays from the Beta Program",
        "announces results of rock and soil analyses from Beta. Highlights from five channel and chip samples include 4,500 g/t "
        "silver over 0.85 metres; and 3,480 g/t silver over 1.6 metres. Channel and chip sample highlights from the zone include: "
        "4,500 g/t silver over 0.85 metres; 1,546 g/t silver over 1.45 metres; and 202 g/t silver, 10.1% zinc over 1.32 metres.",
        ("sample_type",)), [("channel",)])
    eq("1.0.3 auger assays are drilling, not a soil row", rows(
        "ABC Gold Reports Discovery of Gold Concentrated in 2 Metre Thick Soil Layer at Beta",
        "is pleased to announce recent exploration results from Beta. New auger assay results show that gold mineralization is "
        "located in a 2 metre thick lateritic soil layer. Of the 235 samples analysed from within the laterite soil layer, the "
        "highest grade returned was 2.45 g/t Au."), [])
    eq("1.0.3 guard: a soil survey sampled with a power auger stays soil", rows(
        "ABC Gold Soil Sampling Outlines Gold-in-Soil Anomaly at the Beta Project",
        "reports results of detailed power auger soil sampling at Beta. The power auger soil sampling outlined a gold-in-soil "
        "anomaly 800 m long with values up to 100 ppb Au.", ("sample_type",)), [("soil",)])
    eq("1.0.3 a headline drill interval gives no row, old or new", rows(
        "ABC Metals to Acquire the Beta Lithium Property with Historical Assays Including 115.4 Metres at 1.21% Li2O",
        "has entered into option agreements to acquire the Beta Property. " + old_work + "Two historical drill holes returned "
        "115.4 m at 1.21% Li2O. The vendors drilled six holes totalling 1,287 metres."), [])
    eq("1.0.3 the company's own follow-up survey beside a review of older data is new", rows(
        "ABC Gold Completes Beta Project Data Review and Follow Up IP Survey that Identifies Untested Targets",
        "announces the completion of a review of historical data at Beta. The follow-up IP survey completed by ABC identified two "
        "strong chargeability anomalies 800 m long. The new IP survey also outlined a resistivity high.",
        ("sample_type", "survey_type", "historical")), [("geophysics", "IP", False)])
    eq("1.0.3 a new exploration or land position is a deal: quoted results are the older work", rows(
        "ABC Resources Establishes New 600 km2 Exploration Position at its Beta Project",
        "is pleased to announce that it has established a new exploration position at Beta. Reviews of historical work "
        "conducted by previous operators indicate regionally extensive gold occurrences. Extensive gold-in-soil anomalism "
        "extends along corridors over 43 km. Soil values of up to 10.3 ppb Au outline the corridor. Soil geochemistry in the "
        "eastern corridor returned up to 5.9 ppb Au.",
        ("sample_type", "historical")), [("soil", True)])
    eq("1.0.3 'surface samples' names no method: a channel-only release keeps its channel row", rows(
        "ABC Gold Discovers New Gold Lode; Surface Sampling Returns up to 92.55 g/t Gold",
        "is pleased to announce the discovery of a new structure at Beta. High-grade results were returned from close-spaced "
        "channels. Highlights of channel sampling: 66.83 g/t Au over 0.7 m; 48.45 g/t Au over 0.7 m (including 92.55 g/t Au over "
        "0.3 m). Figure 1 shows the location of the surface samples.", ("sample_type", "best_grade")),
       [("channel", (92.55, "g/t", "Au"))])
    eq("1.0.3 heavy-mineral concentrate values are till results", rows(
        "ABC Gold Doubles the Size of the Gold-in-Till Anomaly at the Beta Property",
        "announces 90 new results from the summer till survey. The results define a large gold-in-till anomaly. Highlights include: "
        "3 till samples containing above 100 gold grains; heavy mineral concentrate (HMC) from 5 samples returning gold values "
        "above 5 g/t Au (16.90, 14.50, 9.52, 6.44 g/t Au). Four contiguous till samples returned more than 10 g/t Au in HMC "
        "(18.8, 16.9, 14.5 and 10.2 g/t Au).", ("sample_type",)), [("till",)])
    eq("1.0.3 rock samples from a soil anomaly are rock samples", rows(
        "ABC Gold Announces 2340 g/t Gold in a Rock Sample from the Beta Property",
        "announces partial results from the program. A talus sample assayed 2340 g/t gold. Rock samples from other parts of the "
        "main soil anomaly include 15.9 g/t gold and 9.26 g/t gold. Prospecting focused on a 3.5 km long gold-in-soil anomaly.",
        ("sample_type",)), [("grab",)])
    eq("1.0.3 the lead starts after a letterhead: assays received for a drill program", [
        r["sample_type"] for r in analyse("ABC RECEIVES BETA PROPERTY ASSAY RESULTS",
                                          "ABC GOLD INC. Suite 200 - 1985 Main Street, Vancouver, B.C. Phone: (778) 555-0100. "
                                          "Fax: (778) 555-0101. TSX VENTURE EXCHANGE - ABC March 19, 2026. Frankfurt Exchange "
                                          "Listed. Vancouver, British Columbia - ABC Gold Inc. (the \"Company\") (TSXV: ABC) "
                                          "announces the receipt of all assay results for the 2025 drill program at the Beta "
                                          "Property. Results will be released upon compilation. The northern anomaly coincides "
                                          "with grab samples returning up to 5.18 g/t Au." + fill)["rows"]], [])
    eq("1.0.3 drilling still to come is not the lead's drilling", rows(
        "ABC Samples 26.67 g/t Gold over 2 Metres at the Beta Zone",
        "announces initial assay results from its first field campaign at Beta. Beta hosts a 4.5 km long gold trend. In 2026, "
        "inaugural drill programs are planned at Beta. The Company has received results from 169 channel samples at Beta. "
        "Channel samples returned 26.67 g/t Au over 2 m.", ("sample_type",)), [("channel",)])
    eq("1.0.3 grades 'intersected' in the lead are drilling", rows(
        "ABC Metals Confirms High-Grade Mineralization in the New Zone with Assays Grading up to 6.93% Nickel",
        "confirms the presence of high-grade nickel in the newly discovered zone, with grades up to 6.93% nickel intersected. "
        "Assays grading up to 6.93% nickel confirm the zone."), [])
    eq("1.0.3 grades quoted for the occurrences a property hosts are older finds", rows(
        "ABC Gold Provides Update on the Beta Project, Samples Grading Up to 50.98 g/t Gold",
        "advises on its option of the Beta project. Known mineral occurrences include the Butch occurrence where previous workers "
        "collected grab samples grading up to 50.98 g/t gold. In addition, the Beta claims are host to approximately 40 "
        "nickel-copper occurrences with grab sample values ranging up to 4615 ppm nickel.", ("sample_type", "historical")),
       [("grab", True)])
    eq("1.0.3 an old program named by its year is older work", _old_work(
        "This sample was the highest value returned from the 1981 regional stream sampling program."), True)
    eq("1.0.3 a headline fragment with a headline verb is no project name",
       [bool(re.search(_HL_VERB_IN_NAME, x)) for x in ("ABC Silver Purchases Strategic Beta Mine", "Discovery Project")],
       [True, False])
    eq("1.0.3 a survey the headline only says is being conducted gives no row", rows(
        "ABC Gold Conducts LiDAR Survey Over the Entire Beta Property",
        "will be conducting an airborne LiDAR survey over Beta. The LiDAR survey forms part of the initial steps to delineate "
        "drill locations and identify new targets."), [])
    # ---- 1.0.4 behaviours (2026-10-03 FIX5: releases whose sampling results showed nothing or only part)
    eq("1.0.4 a graded sentence naming no kind goes on with the kind before it", rows(
        "ABC Gold Prospecting Returns up to 20.1 g/t Au from Float at the Beta Project",
        "reports new results from prospecting at Beta. Three float samples were collected west of the showing. One sample of "
        "quartz float assayed 20.1 g/t Au. The other two samples assayed 15.0 and 7.1 g/t Au.", ("sample_type", "best_grade")),
       [("grab", (20.1, "g/t", "Au"))])
    eq("1.0.4 ... else with the one kind the headline names", rows(
        "ABC Nickel Surface Sample Program Identifies Extension of Nickel Mineralization at the Beta Project",
        "announces assay results from 148 surface samples at Beta. The program focused on the B target. Of the 148 samples "
        "submitted, the samples ranged from 0.15% Ni to 0.34% nickel.", ("sample_type", "best_grade")),
       [("grab", (0.34, "%", "Ni"))])
    eq("1.0.4 a headline that reports channel results with no grade keeps its row", rows(
        "ABC Silver Announces Results from Channel Sampling Program at the Beta Project",
        "announces results from channel sampling on an underground adit at Beta. The program included a total of 34 channel "
        "samples taken across the walls of the adit.", ("sample_type", "sample_count")), [("channel", 34)])
    eq("1.0.4 guard: 'rock sample results' names no method, so no headline row without a grade", rows(
        "ABC Zinc Announces Rock Sample Results from the Beta Property",
        "announces zinc sample results from Beta. Representative chip samples were collected from surface showings."), [])
    eq("1.0.4 high-grade boulders are grab samples", rows(
        "ABC Gold Discovers High-Grade Gold-Bearing Boulders at the Beta Project",
        "reports the discovery of high-grade gold-bearing boulders during prospecting at Beta. This boulder graded 28.7 g/t Au. "
        "A second boulder graded 6.0 g/t Au.", ("sample_type", "best_grade")), [("grab", (28.7, "g/t", "Au"))])
    eq("1.0.4 'selected results' and 'select assay highlights' are no select samples",
       [t for _p, t in _types_in("Selected results are shown below. Select assay highlights include 1.2 g/t Au.")], [])
    eq("1.0.4 a sample word inside a place name is no sample type",
       [t for _p, t in _types_in("results from its Pine Channel Project and the Soil Lake property; channel samples")],
       ["channel"])
    eq("1.0.4 a typeless headline over a lead that announces rock results", rows(
        "ABC Gold Confirms High-Grade Gold Mineralization at the Beta Project",
        "has received rock geochemical results from its inaugural program at Beta. Grab samples of quartz vein returned "
        "7.1 g/t Au and 6.9 g/t Au.", ("sample_type",)), [("grab",)])
    eq("1.0.4 work done last year is not a restated result", rows(
        "ABC Lithium Channel Assays Extend the Beta Pegmatite",
        "announces assay results from a channel sampling program at Beta. Late last year we completed two channels; channel "
        "sample 2 returned 1.56% Li2O over 1.20 metres.", ("sample_type", "best_grade", "width_m")),
       [("channel", (1.56, "%", "Li2O"), 1.2)])
    eq("1.0.4 own new and older grades in one sentence each take their own flag", sorted(rows(
        "ABC Tungsten Samples up to 6.76% WO3 at the Beta Mine",
        "announces assay results from recent sampling at Beta. Rock chip samples from inside the mine assayed 6.76% WO3, and "
        "historic USBM sampling from within the mine returned 8.48% WO3.", ("sample_type", "historical", "best_grade"))),
       [("grab", False, (6.76, "%", "WO3")), ("grab", True, (8.48, "%", "WO3"))])
    eq("1.0.4 a historical trench result quoted once with its source stands", sorted(rows(
        "ABC Gold Soil Survey Outlines Gold Anomaly at the Beta Project",
        "reports that its soil sampling program outlined a gold-in-soil anomaly 250 m by 100 m. A nearby historical trench "
        "returned 34.3 m grading 0.85 g/t gold in 1998.", ("sample_type", "historical"))), [("soil", False), ("trench", True)])
    eq("1.0.4 guard: 'previous sampling' alone (whose?) gives no one-sentence historical row", rows(
        "ABC Gold Announces Trenching Results at the Beta Target, Including 30 m at 1.24 g/t Au",
        "announces results of its trenching program at Beta. Trench BBT002 returned 30 m at 1.24 g/t Au. Previous channel "
        "sampling from the main pit returned up to 71 g/t Au.", ("sample_type", "historical")), [("trench", False)])
    eq("1.0.4 float from a historical trench is a new sample", _old_work("Quartz vein float from historical trench."), False)
    eq("1.0.4 channel samples from a trenching program stay channel", rows(
        "ABC Nickel Reports Channel Sampling Results at the Beta Project, Including 0.94% Ni over 17.0 metres",
        "reports channel sampling results from a recent trenching program at Beta. Channel sampling highlights include 0.94% "
        "Ni over 17.0 metres.",
        ("sample_type",)), [("channel",)])
    eq("1.0.4 guard: channel samples tied to a trench are trench samples", rows(
        "ABC Gold Reports Channel Sampling Results at the Beta Project, Including 0.73 g/t Au over 19.8 metres",
        "reports channel sampling results at Beta. Channel samples from trench T-21-3 returned 0.73 g/t Au over 19.8 metres.",
        ("sample_type",)), [("trench",)])
    eq("1.0.4 chip channel samples are chip samples", [t for _p, t in _types_in("42 outcrop chip channel samples")], ["chip"])
    eq("1.0.4 a grade written before its own sample takes that sample's kind", sorted(rows(
        "ABC Gold Reports Surface Sampling Highlights at the Beta Project",
        "reports surface sampling highlights from Beta: 18.12 g/t Au from a 0.30m outcrop channel sample of a quartz vein; "
        "17.60 g/t Au from an outcrop grab sample of a quartz vein.", ("sample_type", "best_grade"))),
       [("channel", (18.12, "g/t", "Au")), ("grab", (17.6, "g/t", "Au"))])
    eq("1.0.4 a soil survey the release returns to, under a headline naming no kind", rows(
        "ABC Gold Outlines New Geochemical Anomalies at the Beta Properties",
        "is pleased to report assay results for 606 soil samples collected at Beta. The soil samples were collected at 100 m "
        "spacing. The new soil results outlined a gold anomaly 5.3 km long. The gold-in-soil anomaly remains open.",
        ("sample_type", "sample_count")), [("soil", 606)])
    eq("1.0.4 guard: a soil anomaly named as the setting of the headline's trenches gives no row", rows(
        "ABC Gold Announces Trenching Results at the Beta Target, Including 30 m at 1.24 g/t Au",
        "announces results of its trenching program at Beta, which lies within a 16 km gold-in-soil anomaly. Trench BBT002 "
        "returned 30 m at 1.24 g/t Au. Gold-in-soil anomalism suggests folding controls the gold. Gold-in-soil contours "
        "highlight the trend to the east of the gold-in-soil anomaly.", ("sample_type",)), [("trench",)])
    eq("1.0.4 brine values under a sampling-results headline", rows(
        "ABC Lithium Reports Sampling Results at the Beta Salar",
        "reports results from near-surface brine sampling at the Beta Salar, with values up to 216 mg/L lithium.",
        ("sample_type", "best_grade")), [("brine", (216.0, "mg/L", "Li"))])
    eq("1.0.4 a unit's abbreviation or other-unit value before the metal; 1.0.4b: a value after '>' is a grade as stated",
       [(v, u, m) for _p, v, u, m, _e in _grades("5.26 grams per tonne (g/t) gold, >42.8 g/t silver, up to 97 g/t (2.83 opt) Ag")],
       [(5.26, "g/t", "Au"), (42.8, "g/t", "Ag"), (97.0, "g/t", "Ag")])
    eq("1.0.4b a headline over-limit value is the result", rows(
        "ABC Silver Receives >10,000 g/t Ag Sample at the Beta Project",
        "reports that a grab sample from the Beta vein returned >10,000 g/t Ag, above the upper detection limit.",
        ("sample_type", "best_grade")), [("grab", (10000.0, "g/t", "Ag"))])
    eq("1.0.4b grades written only as 'over X' keep the row", rows(
        "ABC Gold Reports Trench Results at the Beta Project",
        "reports results from trench sampling at Beta. Trench samples from the main zone: 9 samples returned over 5 g/t Au.",
        ("sample_type", "best_grade")), [("trench", (5.0, "g/t", "Au"))])
    eq("1.0.4b a higher explicit value is preferred to a threshold", rows(
        "ABC Gold Reports Trench Results at the Beta Project",
        "reports results from trench sampling at Beta. Trench samples from the main zone: 9 samples returned over 5 g/t Au, "
        "with values up to 12.3 g/t Au.", ("sample_type", "best_grade")), [("trench", (12.3, "g/t", "Au"))])
    eq("1.0.4 gold grain size is no till sample", [t for _p, t in _types_in("information on gold grain size and head grade")], [])
    eq("1.0.4 'grab samples and some chip samples' is one set: a point grade goes to grab", rows(
        "ABC Silver Announces Results at the Beta Project",
        "reports historical exploration at Beta, by Noranda in 1985, yielded selective grab samples and some chip samples "
        "including up to 377.1 g/t Ag.", ("sample_type", "historical")), [("grab", True)])
    # ---- 1.0.4 rev c (2026-10-03: precision on two folds)
    eq("rev c a concentrate produced is metallurgy, not a sample", rows(
        "ABC Lithium Produces 7.2% Li2O Technical Grade Spodumene Concentrate from Beta Sample",
        "reports metallurgical results from a composite sample of the Beta deposit. Rock samples returned 7.2% Li2O."), [])
    eq("rev c a target found through data compilation and modelling is desktop work", rows(
        "Untested Geophysical Anomaly Identified Through Data Compilation and Modelling at the Beta Project",
        "provides an update on its data compilation. The modelling identified an untested VTEM conductor anomaly."), [])
    eq("rev c a completed survey whose headline names only an already-announced anomaly", rows(
        "ABC Completes Drone MAG Survey; Area Includes Recently Announced Gold Till Anomaly at the Beta Property",
        "has flown a detailed drone magnetic survey over Beta. The magnetic survey was flown along 25 m lines. The gold "
        "grain anomaly in till was announced in March. The MAG data will be interpreted."), [])
    eq("rev c older resource or drill figures give no one-sentence historical row", rows(
        "ABC Lithium Assays up to 2.69% Li2O in Channel Samples at the Beta Property",
        "reports channel samples returned up to 2.69% Li2O over 1.03 m. The pegmatite was drilled in 1955 and 1956, leading to "
        "a historical resource estimate of 1.5 million tonnes grading 1.3% Li2O.", ("sample_type", "historical")),
       [("channel", False)])
    eq("rev c a historic place newly sampled gives no one-sentence historical row", rows(
        "ABC Samples 87 g/t Silver at the Beta Property",
        "reports grab samples returned up to 87 g/t Ag. Previously unsampled historic Gamma Eastern Trenches return a "
        "float sample yielding 3.1% Cu, 12 g/t Ag.", ("sample_type", "historical")), [("grab", False)])
    eq("rev c 'vein float' is no float-sample cue", [t for _p, t in _types_in("quartz vein float returned 32.9 g/t Au")], [])
    eq("rev c guard: historical trench results are older work", _old_work("Historical trench results include 6.82 g/t Au."), True)
    # ---- 1.0.6 (FIX8, 2026-10-06)
    eq("1.0.6 a sample number is not a count", [v for _k, v, _s, _sc in _counts(["36105-25-66 grab samples returned 830 ppb gold."])], [])
    eq("1.0.6 a count written with its comma stays", [v for _k, v, _s, _sc in _counts(["A total of 23,000 till samples were collected."])], [23000])
    eq("1.0.6 a small count stays", [v for _k, v, _s, _sc in _counts(["The program included a total of 34 channel samples."])], [34])
    print("sampling: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test(verbose="-v" in sys.argv) else 0)
