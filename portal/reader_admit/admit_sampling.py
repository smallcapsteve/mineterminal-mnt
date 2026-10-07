"""Outside-tag admission rule for the Sampling & Geoscience Results reader (sampling). Round 7.

admit(headline, text, categories, out) -> (bool, short_reason)

A release that lacks the Sampling tag is admitted only when the reader's rows look like the release's own news:
either the reader flagged every row historical AND the release itself speaks of historic / previous-operator work
(an acquisition / program-start release presenting old data), or the headline announces a surface-sampling /
geoscience result and every row the reader found is of a kind the headline (or, for a discovery headline naming no
sample kind, the lead paragraphs, un-qualified by "previous" / "historic") talks about.
Everything else -- drill-result and drill-start releases, deals, financings, technical reports, historical reviews,
planned or merely completed programs -- is refused, because there the reader's rows are mostly background.
Round 2 (after a fresh 60-release check) adds: stricter historical path, wider drill-intercept headline detection,
drill-start releases, planned surveys, geophysics named only as a place, kinds the headline names only as work
completed or started, rows the lead qualifies as previous work, and releases where the reader split rock samples
over several rows.
Round 3 (with reader 1.0.1, 2026-09-30): the reader now flags deal / technical-report / compilation results historical
and no longer splits rock sample sets, so the all-historical path accepts a deal, technical-report or historical-data
headline as support (and ignores a "100%" ownership share), and the "two or more rock rows" refusal is dropped.
Round 4 (reader 1.0.1, after the conf3 check, 2026-09-30): the all-historical path now also needs the release to
frame the rows as someone's older work where it quotes them (a historic / previous-operator / government /
assessment word or citation in the sentence or the one before, or a year five or more years before the release), and
refuses rows quoted as the company's own earlier work or a program from the last two years (deal and program-start
releases quote the vendor's recent work, the company's restated results or a neighbour's samples, and the reader
flags them all historical). Also: depth language marks a drill release; a licence or permit grant is a deal-type
headline; "to drill / to carry out / to conduct" is planned work; survey data the company purchased is historical.
Round 5 (reader 1.0.1, after the ACC150b re-check of releases this rule tagged, 2026-10-02): refuses announced-only
work (the opening says a survey or program is contracted, about to start, starting or partway done, and the headline
reports no result), releases whose assays are still at the laboratory (the grades quoted are a recap), a discovery
headline over a release whose announcement is a drill intersection, and a new land / exploration position (a deal);
a known discovery named as a place ("on strike from its VMS discovery") is no longer read as a result word.
Row-level reader errors (sample or survey type, which grade, historical flag) are left to the reader.
Round 7 (FIX5, 2026-10-03; reader candidate 1.0.4; own tagging OFF after the round-5 rule scored 75.7% on a fresh
blind check -- announced or planned surveys admitted, historical-flag and survey-type errors): admits only releases
that report results. Refused before any other test, whatever the reader flagged: recaps of a past period (summaries,
year-in-review, a year's highlights, last year's work with next year's plans) and headlines saying the assays are
pending; a geophysics row whose survey method the release never names by its own words (resistivity from a VLF / EM
inversion read as IP). On the new-results path: a headline with no result language (a survey or program only
named) or whose news is work planned or starting before any result; a row whose grade is quoted only beside a
citation of an earlier release (restated); an acquisition / option headline whose new-flagged rows are not dated as
recent work where the grade is quoted (the vendor's or older samples); a kind or survey method the headline names
only as the reference for the new result ("correlates with the results of the summer soil program", "targets
previously defined") or qualifies as older work ("previous sampling returned ..."); "soil / till / sediment
sampling" no longer counts as rock sampling. Wider: plural method words ("radiometrics"), "geophysics identifies"
as a geophysical finding, and a generic "sample results" headline covering the kinds its announcement sentence
names. Financial / operating / annual reports and metallurgical testwork join the corporate headlines.
Round 7b (FIX5, 2026-10-03, after the held-back check: out 72.7%; revised on all ACC150c labels): whole release kinds
where the reader's rows are often wrong are refused -- exploration / corporate update or progress-report headlines with
no grade; "completes field work / program" headlines with no grade or results of their own after the verb; a headline
naming no sample kind over a release whose opening reports drill results (intercepts, holes, backpack drilling);
option / earn-in agreement headlines on the all-historical path (vendor's recent and older work mixed, rows of the
wrong kind, flag or project); and an all-historical output under a headline announcing results / assays of its own.
Standard library only; no names, tickers or ids.
"""
import re


def _rx(p):
    return re.compile(p, re.I)


# Short geophysics acronyms are matched case-sensitively, so "Mt Todd" or "Em" in a name are not surveys.
_ACR = r"(?-i:IP|EM|MT|AMT|CSAMT|VTEM|ZTEM|TEM|MAG)"

# ---- what kind of result a headline names (sample-kind families) ----
FAM_RX = {
    "rock": _rx(r"\b(samples?|sampling|sampled|grabs?|rock|chips?|channels?|trench\w*|boulders?|outcrops?|float|"
                r"prospecting|field ?work|reconnaissance|showings?)\b"),
    "soil": _rx(r"\bsoils?\b"),                       # soil and soil-gas geochemistry
    "till": _rx(r"\b(till|gold grains?|heavy minerals?)\b"),
    "sediment": _rx(r"\b(sediments?|bleg|stream)\b"),
    "mapping": _rx(r"\b(mapping|mapped|showings?|outcrops?|prospecting|reconnaissance)\b"),
    "geophysics": _rx(r"\b(magnetics?|magnetometer|airborne|geophysic\w*|chargeability|conductors?|electromagnetic|"
                      # round 7: plural / adjective forms ("ground radiometrics", "seismic")
                      r"radiometrics?|gravity|resistivity|magnetotellurics?|lidar|hyperspectral|satellite|seismic)\b"
                      r"|\b" + _ACR + r"\b"),
    "bulk": _rx(r"\bbulk[- ]sampl\w*"),
    "brine": _rx(r"\bbrines?\b"),
    "other_geochem": _rx(r"\b(biogeochem\w*|vegetation|bark|humus|lithogeochem\w*)\b"),
}
ROW_FAM = {"grab": "rock", "chip": "rock", "channel": "rock", "trench": "rock", "soil": "soil", "till": "till",
           "sediment": "sediment", "mapping": "mapping", "geophysics": "geophysics", "bulk": "bulk", "brine": "brine",
           "other_geochem": "other_geochem"}

# ---- words for a row's own sample type, looked for in the lead paragraphs ----
TYPE_RX = {
    "grab": _rx(r"grab|rock|select|outcrop|float|boulder|prospecting|surface sampl"),
    "chip": _rx(r"chip"),
    "channel": _rx(r"channel|panel"),
    "trench": _rx(r"trench"),
    "soil": _rx(r"soil"),
    "till": _rx(r"\btill\b|heavy mineral|gold grain"),
    "sediment": _rx(r"sediment|stream|bleg"),
    "other_geochem": _rx(r"biogeochem|vegetation|bark|humus|water sampl"),
    "bulk": _rx(r"bulk sampl"),
    "brine": _rx(r"brine"),
    "mapping": _rx(r"mapping|mapped"),
}
SURVEY_RX = {
    "IP": _rx(r"induced polari|chargeab|resistiv|\b(?-i:IP)\b"),
    "magnetics": _rx(r"magnet|\b(?-i:MAG)\b"),
    "EM": _rx(r"electromagnet|conductor|\b(?-i:EM|VTEM|ZTEM|TEM|HTDEM)\b"),
    "MT": _rx(r"magnetotelluric|\b(?-i:MT|AMT|CSAMT)\b"),
    "gravity": _rx(r"gravity"),
    "radiometric": _rx(r"radiometric|spectromet"),
    "lidar": _rx(r"lidar"),
    "hyperspectral": _rx(r"hyperspectral"),
    "remote_sensing": _rx(r"satellite|\b(?-i:ASTER)\b|remote[- ]sens|worldview"),
}
GEO_ANY = _rx(r"geophysic|survey")
# words that mark a result in the lead as someone's earlier work, not this release's news
OLD_QUAL = _rx(r"\b(previous\w*|prior|historic\w*|earlier|past|former|legacy|vintage)\W+(?:[\w-]+\W+){0,2}$")

# ---- headline language ----
# a result / discovery is announced
DISC_HL = _rx(r"\b(discover\w*|uncovers?|delineates?|defin(es|ed)|up to|identif\w*|outlines?|expands?|extends?|"
              r"confirms?|finds?|found|results?|assays?|returns?|reports?|high[- ]grade|g/t|gpt|ppm|ppb)\b|%")
# a narrower set, to tell "completes soil program" (no result) from "completes program, returns 5 g/t"
RESULT_HL = _rx(r"\b(results?|assays?|assayed|returns?|returned|grading|up to|identif\w*|discover\w*|outlines?|"
                r"reveals?|defines|reports|confirms|expands|g/t|gpt|ppm|ppb)\b|\d%")
# a grade figure in the headline: the release announces a new assay result
GRADE_HL = _rx(r"\d\s*(g/t|gpt|ppm|ppb|%|oz/t|grams? per tonne)")
# drill-result releases: the surface samples in them are nearly always property background
DRILL_HL = _rx(r"\b(drill\w*|intercepts?|intersect\w*|holes?|core|hits)\b"
               # round 4: depth language is drill-hole language ("assays end at 502 ft ... increasing with depth")
               r"|\b(with|at) depth\b|\bends? at [\d.,]+\s*(m|metres?|meters?|ft|feet)\b")
# a drill-style interval in the headline: "X g/t over N m", "N m at X g/t", "zone of N m", "N metres of X g/t"
INTERVAL_HL = _rx(r"\b(over|of|across)\s+[\d.,]+\s*(m|metres?|meters?|ft|feet)\b"
                  r"|[\d.,]+\s*(m|metres?|meters?|ft|feet)\s+(at|of|grading|averaging|@)\s")
# surface-sample words; "from surface" / "near surface" is drill-intercept depth language, not a sample kind
SURFACE_HL = _rx(r"\b(surface|samples?|sampling|channels?|trench\w*|chips?|outcrops?|grabs?|soils?|till)\b")
DEPTH_SURF = _rx(r"\b(from|near|at)[- ]surface\b")
LEAD_SURF = _rx(r"\b(grabs?|chips?|channels?|trench\w*|soils?|till|outcrops?|surface sampl\w*)\b")
# ("intercept" is left out: releases use it for channel samples too)
LEAD_DRILL = _rx(r"\b(drill\w*|holes?|core)\b")
# work being started on a drill program (the surface results quoted are the ones that made the target)
DRILL_START_HL = _rx(r"\b(commenc\w*|begins?|starts?|mobiliz\w*|underway|plans?|planned|to test|to follow[- ]up|"
                     r"prepares?|launch\w*|" + r"to (?:drill|carry out|conduct|undertake|begin|start|launch|complete))\b")
# a geophysical finding stated as new (not a known anomaly a hole was drilled into)
GEO_FIND_HL = _rx(r"\b(discover\w*|identif\w*|new|outlines?|reveals?|defines?)\W+(?:[\w,.-]+\W+){0,4}?"
                  r"(magnetic|chargeability|conductors?|electromagnetic|gravity|radiometric|" + _ACR + r")\b"
                  r"|\b(magnetic|gravity|radiometric|geophysical|" + _ACR + r")\s+(?:\w+\s+)?survey results?"
                  # round 7: the geophysics / survey itself is the subject of a finding verb
                  # ("Geophysics Identifies Potential Centre of Porphyry", "IP survey outlines ...")
                  r"|\b(geophysic\w*|surveys?)\s+(identif\w*|outlines?|reveals?|defines?|delineates?|detects?)\b")
# a geophysics headline that reports on a survey / its data, rather than naming a known feature as a place
GEO_SURVEY_HL = _rx(r"\b(surveys?|data|images?|imagery|results?|program\w*|anomal\w*|conductors?|chargeability|"
                    r"targets?)\b")
# a survey or sampling program the headline presents as future work ("targets for heliborne magnetic survey")
PLANNED_HL = _rx(r"\b(?:for|to (?:carry out|conduct|undertake|begin|start|launch))\s+"
                 r"(?:(?:a|an|the|its|new|planned|upcoming|follow[- ]up)\s+)?(?:[\w-]+\s+){0,3}?"
                 r"(surveys?|sampling|programs?|programmes?)\b")
# corporate / technical releases whose sample figures are background
HARD_NEG_HL = _rx(r"\b(resource estimate|technical report|43-101|pea|feasibility|plant|commissioning|financing|"
                  r"placement|agm|annual general|quarter\w*|year in review|corporate update|news release|"
                  # round 7: periodic financial / operating reports and metallurgical testwork
                  r"financial (results|statements)|annual (results|report)|year[- ]end|fiscal|interim|md&a|"
                  r"management'?s discussion|operating results|production results|metallurg\w*)\b")
# deals: acquisitions, options, staking, sales -- the figures quoted are usually the vendor's / old work
DEAL_HL = _rx(r"\b(acquir\w*|acquisition|option\w*|earn[- ]in|stakes?|staking|consolidates?|claims|agreement|"
              r"term sheet|letter of intent|sells?|sale|retains|engages|bond|merger|amalgamation|"
              # round 4: a licence or permit granted -- the grades quoted are the ones that made the project
              r"licen[cs]es?|permits?|granted)\b")
# historical data, compilations, desktop reviews and maps
HIST_HL = _rx(r"\bhistoric\w*\s+(?:[\w-]+\s+){0,2}?(results?|data|samples?|sampling|work|exploration|drill\w*|"
              r"discovery|assays?)\b|\bpreviously (reported|released|announced)\b"
              r"|\b(compil\w*|review|study|reinterpret\w*|reprocess\w*|map)\b")
# the release body speaks of old work by others: backs up a reader's "historical" flag
HIST_TEXT = _rx(r"\b(historic\w*|previous(ly)? (operator|owner|work|explor\w*)|prior (operator|owner|work)|"
                r"past (producer|work)|vintage|assessment (report|file)s?|government|legacy)\b")
# a status clause: "completes airborne survey and a large soil sampling program" -- the kinds named after a
# completed / started verb, up to the next punctuation, are work done, not results (unless the same clause
# carries a result word: "completes gravity survey and identifies targets")
STATUS_CLAUSE = _rx(r"\b(complet\w*|concludes?|commenc\w*|begins?|starts?|launch\w*|mobiliz\w*|initiat\w*|"
                    r"to (?:drill|carry out|conduct|undertake))\b"
                    r"[^,;:|\u2013\u2014]*?(?=[,;:|\u2013\u2014]|\s-\s|$)")
# work started / finished / planned, no result
STATUS_HL = _rx(r"\b(complet\w*|concludes?|commenc\w*|begins?|starts?|underway|mobiliz\w*|plans?|planned|collected|"
                r"submitted|pending|awaiting|prepares?|launch\w*)\b")
GRADE_LEAD = _rx(r"\d\s*(g/t|gpt|ppm|ppb|%|oz/t)")
# round 3: a technical-report filing, and an ownership share written as a percentage
TECH_HL = _rx(r"\btechnical report|\b43-101\b")
OWN_PCT = _rx(r"\b100\s*%")
# round 4: words near a quoted result that say it is someone's older work (a previous owner, a government survey,
# an assessment report, a citation, an old program)
OLD_NEAR = _rx(r"\b(historic\w*|previous\w*|prior|past|former|vintage|legacy|government|geological survey|"
               r"assessment|reported by)\b|\(\w[\w .&]*,? (?:19|20)\d\d\)")
# the company's own earlier work or a recent program quoted near a result: not old work by others
OWN_NEAR = _rx(r"\b(news|press) release dated|\b(work|sampling|program\w*|exploration|trenching|mapping|crews?) "
               r"(?:\w+ ){0,2}by the company\b|\b(the company'?s|our) (?:own )?(?:\d{4} )?(?:\w+ )?"
               r"(program\w*|sampling|work|exploration|crews?|team|trench\w*|samples)\b"
               # new work set beside the old: "results compare favorably to historic data", "confirm historic grades"
               r"|\b(compar\w*|confirm\w*|validat\w*|verif(?:y|ies|ied) (?:the )?histor\w*)\b(?:\W+\w+){0,3}?\W+histor\w*")
# a sentence boundary: ". " / "! " / "? ", a bullet, or a line break before a capital or bullet
SENT_END = re.compile(r"[.!?](?=\s)|[\u2022\u25cf\u25aa]|\n\s*(?=[\u2022\u25cf\u25aa\-*o]\s|[A-Z][A-Z])|;")
YEAR = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
# round 4: survey data bought from others (old data the company purchased) is historical. ("Acquired data" is
# left out: survey crews "acquire" their own new data.)
BOUGHT_DATA = _rx(r"\bpurchas\w*\b(?:[ \t\r\n,()-]+\w+){0,10}?[ \t\r\n,()-]+data\b")
ROCK = {"grab", "chip", "channel", "trench"}

# ---- round 5 (after the ACC150b re-check of reader-tagged releases, 2026-10-02) ----
# a known deposit or showing named as a place ("on strike from its 2017 VMS discovery", "at the Main discovery"):
# not a result word. ("The discovery of ..." stays a result.)
PLACE_DISC = _rx(r"\b(its|the|their|our)\s+(?:[\w-]+\s+){0,5}?discovery\b(?!\s+of\b)")
# the release's opening announcement says the work is contracted, about to start, starting or partway done --
# a survey or sampling program announced with no result yet
ANNOUNCE_LEAD = _rx(r"\b(?:announce|report)s?\w*\s+(?:that\s+)?(?:(?:it|the company|its partner(?: company)?|\w+)\s+)?"
                    r"(?:has\s+)?(?:contracted|engaged|retained|commissioned|"
                    r"will be (?:conducting|carrying|flying|undertaking|starting|commencing|completing)|"
                    r"is (?:now\s+)?(?:commencing|starting|initiating|mobiliz\w*|planning|conducting|underway|\d+\s*% complete)|"
                    r"plans to|intends to|is set to|is about to)\b"
                    r"|\bannounce\w* the (?:commencement|start|launch|mobili[sz]ation|initiation) of\b"
                    r"|\bscheduled to (?:begin|start|commence)\b|\bis now \d+\s*% complete\b")
# the release says its assays are still at the laboratory: the grades it quotes are earlier results
PENDING_LEAD = _rx(r"\bresults? (?:will|are expected to|are anticipated to) be (?:released|reported|announced|disclosed)"
                   r"|\b(?:all )?(?:samples?|assays?)\s+(?:\w+\s+){0,3}?(?:have|has) been\s+(?:shipped|sent|submitted|"
                   r"delivered|dispatched)\b"
                   r"|\b(?:receipt|received) of (?:all )?(?:the )?assay results\b(?:\W+\w+){0,12}?\W+(?:will be|upon)\b")
# a result word for the announced-only check (narrower than RESULT_HL: "expands exploration", "reports update" are not)
ANN_RESULT = _rx(r"\b(results?|assays?|assayed|returns?|returned|grading|up to|identif\w*|discover\w*|outlines?|"
                 r"reveals?|defin\w*|confirms?|anomal\w*|g/t|gpt|ppm|ppb)\b|\d%")
# a drill intersection reported as the news
DRILL_NEWS = _rx(r"\b(drill\w*|holes?|core)\b(?:\W+\w+){0,6}?\W+(?:has |have )?(intersect\w*|intercept\w*)\b"
                 r"|\b(intersect\w*|intercept\w*)\b(?:\W+\w+){0,8}?\W+(drill\w*|holes?)\b")
# the sentence that carries the release's announcement starts at one of these
ANN_SENT = _rx(r"\b(?:pleased to|is announcing|announces|reports)\b")
# a land-position release (a new exploration / land package assembled): a deal, the grades quoted are the vendors'
LAND_HL = _rx(r"\b(land|exploration|claim|property)\s+(position|package)s?\b")

# ---- round 7 (FIX5, reader 1.0.4, 2026-10-03) ----
# a recap of a past period: year-in-review, summaries, highlights of a year, last year's results with next year's plans
RECAP_HL = _rx(r"\b(summar\w*|recap\w*|review of|in review|year[- ]in[- ]review|looks? back|"
               r"highlights? (?:of|from) (?:its |the |their )?(?:19|20)\d\d|"
               r"(?:19|20)\d\d (?:exploration |field |work )?(?:highlights|achievements|accomplishments|summary|review))\b")
# last period's work and next period's plans in one headline ("2019 Results and Outlines 2020 Plans",
# "2021 District Exploration and Announces 2022 Program")
YEAR_PLAN_HL = re.compile(r"(?i)\b((?:19|20)\d\d)\b.*?\b((?:19|20)\d\d)\s+(?:[\w-]+\s+){0,2}?"
                          r"(plans?|programs?|programmes?|budgets?|outlook|objectives|guidance|strategy)\b")
# the headline says the assays are still at the laboratory
# ("outstanding" is left out: "Assays Return Outstanding Grades")
PENDING_HL = _rx(r"\b(assays?|results?|analys[ie]s)\b(?:\W+\w+){0,4}?\W+(pending|awaited)\b"
                 r"|\b(pending|awaiting|awaits)\b(?:\W+\w+){0,3}?\W+(assays?|results?)\b")
# a kind the headline names only as the reference a new result is compared with ("survey correlates with the
# results of the summer soil program", "anomalies mirroring the known zones", "targets previously defined"):
# the part of the headline after such a word is background
REF_SPLIT = _rx(r"\b(correlat\w*|coincid\w*|mirror\w*|match\w*|overlap\w*|consistent with|similar to)\b")
PREV_KIND = _rx(r"\b(previously|earlier|already|historic(?:al(?:ly)?)?)\s+(defined|reported|identified|announced|"
                r"outlined|released|disclosed|known)\b")
# a kind the headline itself qualifies as older work ("Previous Sampling Returned up to 30 g/t", "historic soil
# anomalies"); "past-producing" names a mine, not older work
OLDQ_KIND = _rx(r"\b(previous\w*|prior|historic\w*|earlier|past(?![- ]produc)|former|legacy|vintage)\s+"
                r"(?:[\w-]+\s+){0,2}[\w-]+")
# non-rock media sampled: "soil sampling", "stream sediment samples", "till sampling program" are not rock sampling
NONROCK_SAMPLING = _rx(r"\b(soils?|soil[- ]gas|tills?|sediments?|bleg|brines?|biogeochemical|vegetation|water|bulk|"
                       r"geochemical|geochemistry)\s+(?:[\w-]+\s+)?(samples?|sampling|sampled|programs?|programmes?|"
                       r"surveys?|results?)\b")
# a geophysics row's method must be named by its own words somewhere in the release (resistivity from a VLF / EM /
# MT inversion is not an IP survey)
METHOD_RX = {
    "IP": re.compile(r"(?i:induced[- ]polari|chargeab)|\b(?:IP|DCIP|3DIP|3D IP)\b"),
    "EM": re.compile(r"(?i:electro-?magnet|conductor|conductiv|time[- ]domain|frequency[- ]domain)"
                     r"|\b(?:EM|VTEM|ZTEM|TEM|HTEM|AEM|TDEM|FDEM|MLEM|UTEM|VLF|VLF-EM|HLEM)\b"),
    "magnetics": re.compile(r"(?i:magnetic|magnetometer|aeromag)|\b(?:MAG|Mag)\b"),
    "MT": re.compile(r"(?i:magnetotelluric)|\b(?:MT|AMT|CSAMT)\b"),
    "gravity": _rx(r"gravity|gravimetr"),
    "radiometric": _rx(r"radiometric|spectromet|gamma[- ]ray|\bscintillomet"),
    "seismic": _rx(r"seismic"),
    "lidar": _rx(r"lidar"),
    "hyperspectral": _rx(r"hyperspectral"),
    "remote_sensing": re.compile(r"(?i:satellite|remote[- ]sens|worldview|sentinel|landsat)|\bASTER\b"),
}
# acquisitions and options (not permits or other agreements): the samples quoted are the vendor's or older work
BUY_HL = _rx(r"\b(acquires|acquiring|to acquire|acquisition|options|optioned|option agreements?|earn[- ]in|"
             r"purchases|to purchase|purchase agreement|stakes|staking|letter of intent|term sheet|enters? into)\b")
# words near a quoted grade that date it as recent (the vendor's recent, unreleased program is new under the guide)
RECENT_NEAR = _rx(r"\b(recent\w*|this (?:year|summer|season|spring|fall|autumn|winter)|last (?:summer|season|fall)|"
                  r"the company'?s|our)\b")
# a grade the release cites from an earlier release of its own
RESTATED_NEAR = _rx(r"\b(?:see|refer to)\s+(?:the\s+)?(?:company'?s\s+)?(?:news|press)\s+releases?\b"
                    r"|\b(?:news|press) releases? (?:dated|of|on|issued)\b"
                    r"|\bpreviously (?:reported|released|announced|disclosed|published)\b"
                    r"|\bas (?:previously )?(?:reported|announced|disclosed)\b"
                    r"|\(reported\b|\breported (?:on |in )?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.? \d")
# work planned, prepared or starting, named as the headline's news ("Plans Follow-up on Significant Soil Anomaly",
# "Mobilizes Crew; ..."): when it comes before any result language, the results quoted are the reasons for the work
WORK_START_HL = _rx(r"\b(plans?|planned|planning|prepares?|preparing|to follow[- ]up|to test|commenc\w*|begins?|"
                    r"starts?|mobiliz\w*|mobilis\w*|launch\w*|initiat\w*|underway|"
                    r"to (?:drill|carry out|conduct|undertake|begin|start|launch|complete))\b")
# the work's own first results reported after it ("Survey Underway; Initial Results Show Strong Conductors")
FIRST_RESULTS_HL = _rx(r"\b(initial|first|preliminary|early|partial)\s+(?:[\w-]+\s+){0,2}?(results?|assays?)\b")
# round 7b: an exploration / corporate / project update or progress report: a period's news, mostly recapped
UPDATE_HL = _rx(r"\b(updates?|progress report)\b")
# round 7b: an option / earn-in agreement (the optionee earns into the vendor's ground): the vendor's recent work and
# older work are mixed in these releases, and the reader's historical rows are often of the wrong kind, flag or project
OPTION_HL = _rx(r"\b(options?|optioned|optioning|earn[- ]in|earn an? (?:\d+%? )?interest)\b")
# round 7b: work finished as the headline's news ("Completes Field Work on Newly Identified Targets")
DONE_HL = _rx(r"\b(complet\w*|conclud\w*|finish\w*|wraps? up)\b")
# round 7b: the release's own results named after a work-status verb ("Completes Trenching; Assays Return ...")
OWN_RESULT_AFTER = _rx(r"\b(results?|assays?|assayed|returns?|returned|yields?|yielded|grading)\b")
# round 7b: drill-result language in the opening of a release whose headline names no sample kind
OPEN_DRILL = re.compile(r"(?i:\bdrill(?:ing|ed)?\s+(?:results?|intercepts?|intersections?)\b"
                        r"|\b(?:intercepts?|intersections?|intersected)\b|\bbackpack drill\w*)"
                        r"|\b[Hh]oles?\s+[A-Z]{0,4}[-\d]*\d")
# the generic sample words that put "rock" in a headline's kinds without naming a rock method
GENERIC_SAMPLE = _rx(r"\b(samples?|sampling|sampled)\b")
# any result language in a headline (grades, finds, anomalies, "returns", "yields", "shows" ...)
ANY_RESULT_HL = _rx(r"\b(results?|assays?|assayed|returns?|returned|grading|grades?|up to|identif\w*|discover\w*|"
                    r"outlines?|reveals?|defin\w*|delineat\w*|confirms?|anomal\w*|conductors?|chargeability|"
                    r"yields?|shows?|finds?|found|intersects?|extends?|expands?|high[- ]grade|bonanza|values|"
                    r"mineraliz\w*|mineralis\w*|significant|strong|robust|encouraging|positive|impressive|elevated|"
                    r"anomalous|g/t|gpt|ppm|ppb|oz/t)\b|\d\s*(%|g/t|gpt|ppm|ppb|oz/t|grams? per tonne)")


def _val_rx(v):
    """A regex for a grade value as releases write it: 3560 -> 3,560 / 3560(.0); 4.71 -> 4.71(0)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    ip, _, dp = ("%.6f" % v).rstrip("0").partition(".")
    if len(ip) > 3:
        ip = ip[:-3] + ",?" + ip[-3:]
    tail = (r"\." + dp + r"0*") if dp else r"(?:\.0+)?"
    return re.compile(r"(?<![\d.,])" + ip + tail + r"(?![\d])")


def _release_year(body):
    ys = [int(y) for y in YEAR.findall(body[:800])]
    return max(ys) if ys else None


def _old_support(row, hl, body):
    """How the release frames the row's grade where it quotes it (outside the headline):
    "old"  -- some place is framed as older work by others: a historic / previous / government / assessment word or
              a citation in its sentence or the one before, or a year five or more years before the release;
    "own"  -- every place it is quoted is the company's own earlier work ("see news release dated ...", "our 2024
              program") or a program from the last two years;
    "none" -- neither. Rows with no grade fall back to the body speaking of historic work."""
    v = (row.get("best_grade") or {}).get("value")
    vrx = _val_rx(v) if v is not None else None
    if vrx is None:
        return "old" if HIST_TEXT.search(body) else "none"
    start = len(hl) if body[:len(hl) + 40].strip().startswith(hl.strip()[:40]) else 0
    ry = _release_year(body)
    seen = own = 0
    for m in vrx.finditer(body, start):
        seen += 1
        # the sentence the value sits in (at most 400 characters back), plus the rest of its clause
        # (and the sentence before it, which often carries the "historic work includes:" lead-in)
        head = body[max(0, m.start() - 500):m.start()]
        cuts = [0]
        for x in SENT_END.finditer(head):
            # a bullet right after a full stop or line break does not make an empty sentence
            if len(re.sub(r"\W", "", head[cuts[-1]:x.start()])) >= 12:
                cuts.append(x.end())
        cur = head[cuts[-1]:]
        prev = head[cuts[-2]:cuts[-1]] if len(cuts) > 1 else ""
        # the rest of the value's own clause (up to the next comma, bracket, "and" or sentence end)
        tail = body[m.end():m.end() + 80]
        tc = re.search(r"[,;(]|\band\b|[.!?](?=\s)", tail)
        cur = cur + body[m.start():m.end()] + (tail[:tc.start()] if tc else tail)
        yrs = [int(y) for y in YEAR.findall(cur)]
        # the company's own earlier work or a recent program (within two years of the release) is not old work
        if OWN_NEAR.search(prev + " " + cur) or (ry and any(y >= ry - 2 for y in yrs)):
            own += 1
            continue
        win = prev + " " + cur
        if OLD_NEAR.search(win) or (ry and any(int(y) <= ry - 5 for y in YEAR.findall(win))):
            return "old"
    return "own" if seen and own == seen else "none"


def _announcement(opening):
    """The sentence of the opening that carries the release's announcement ("... is pleased to announce that ...")."""
    m = ANN_SENT.search(opening)
    if not m:
        return ""
    e = re.search(r"[.!?](?=\s)", opening[m.end():])
    return opening[m.start():m.end() + (e.start() if e else 400)]


def _fams(s):
    # round 7: "soil sampling", "stream sediment samples", "till sampling program" name that medium, not rock samples
    rock_s = NONROCK_SAMPLING.sub(lambda m: m.group(1), s)
    return {f for f, r in FAM_RX.items() if r.search(rock_s if f == "rock" else s)}


def _old_free(s):
    """The headline with the (up to three) words after "previous", "historic", "prior" ... removed: "Previous
    Sampling Returned up to 30 g/t" names no fresh sampling."""
    return OLDQ_KIND.sub(" ", s)


def _grade_quotes(row, hl, body):
    """Each place the release body (after its copy of the headline) quotes the row's best grade, as
    (sentence before, the value's sentence up to the value, the 600 characters after it)."""
    v = (row.get("best_grade") or {}).get("value")
    vrx = _val_rx(v) if v is not None else None
    if vrx is None:
        return []
    vrx = re.compile(vrx.pattern + r"(?![.,]\d)")
    start = len(hl) if body[:len(hl) + 40].strip().startswith(hl.strip()[:40]) else 0
    res = []
    for m in vrx.finditer(body, start):
        head = body[max(0, m.start() - 500):m.start()]
        cuts = [0]
        for x in SENT_END.finditer(head):
            if len(re.sub(r"\W", "", head[cuts[-1]:x.start()])) >= 12:
                cuts.append(x.end())
        res.append((head[cuts[-2]:cuts[-1]] if len(cuts) > 1 else "", head[cuts[-1]:], body[m.end():m.end() + 600]))
    return res


def _sentence_rest(after):
    e = re.search(r"[.!?](?=\s)|\n\s*\n|[\u2022\u25cf\u25aa]", after)
    return after[:e.start()] if e else after


def _restated(row, hl, body):
    """True when the row's grade is not in the headline and every place the body quotes it cites an earlier
    release ("see news release dated ...", "previously reported", "(reported August 4, 2015)") in its sentence or
    in a next sentence that refers back to it ("These early results ... (see press release dated ...)"): a restated
    result, not this release's news."""
    v = (row.get("best_grade") or {}).get("value")
    vrx = _val_rx(v) if v is not None else None
    if vrx is None or vrx.search(hl):
        return False
    qs = _grade_quotes(row, hl, body)
    if not qs:
        return False
    for prev, cur, after in qs:
        rest = _sentence_rest(after)
        nxt = _sentence_rest(after[len(rest) + 1:])[:300]
        # the next sentence counts only when it refers back to these results ("These early results ...")
        if not re.match(r"\s*(these|those|such|the above|both)\b", nxt, re.I):
            nxt = ""
        if not RESTATED_NEAR.search(cur + rest + nxt):
            return False
    return True


def _recent(row, hl, body, ry):
    """True when some place the body quotes the row's grade dates it as recent work (a year within two years of the
    release in its own sentence, or "recent" / "this summer" / "the company's" wording there or in the sentence
    before)."""
    for prev, cur, after in _grade_quotes(row, hl, body):
        sent = cur + _sentence_rest(after)
        # (years only from the value's own sentence: the sentence before is often the dateline)
        if RECENT_NEAR.search(prev + " " + sent) or (ry and any(int(y) >= ry - 2 for y in YEAR.findall(sent))):
            return True
    return False


def _fresh_mention(rx, lead):
    """True if rx matches somewhere in the lead that is not qualified as previous / historic work."""
    for m in rx.finditer(lead):
        if not OLD_QUAL.search(lead[max(0, m.start() - 40):m.start()]):
            return True
    return False


def admit(headline, text, categories, out):
    rows = (out or {}).get("rows") if isinstance(out, dict) else None
    if not rows:
        return False, "no rows"
    hl = headline or ""
    body = text or ""
    lead = hl + " " + body[:2000]
    # the body after its copy of the headline (most releases repeat the headline first)
    b0 = len(hl) if body[:len(hl) + 40].strip().startswith(hl.strip()[:40]) else 0
    opening = body[b0:b0 + 1500]
    hl_nopct = OWN_PCT.sub(" ", hl)
    grade_in_hl = bool(GRADE_HL.search(hl_nopct))

    # 0. (round 7) Release kinds whose rows are never this release's own results, whatever the reader flagged:
    #    0a. recaps of a past period (year-in-review, summaries, last year's results with next year's plans): the
    #        results were released before (guide: restated results are no row);
    if RECAP_HL.search(hl):
        return False, "recap headline"
    yp = YEAR_PLAN_HL.search(hl)
    if yp and int(yp.group(2)) > int(yp.group(1)) and not grade_in_hl:
        return False, "last period's work and next period's plans"
    #    0b. the headline says the assays are still pending (the grades quoted are a recap);
    if PENDING_HL.search(hl) and not grade_in_hl:
        return False, "headline: assays pending"
    #    0b'. (7b) an exploration / corporate update or progress report with no grade in the headline: the
    #        reader's rows in these are mostly recapped or background results;
    if UPDATE_HL.search(hl) and not grade_in_hl:
        return False, "update headline"
    #    0c. a geophysics row whose survey method the release never names by its own words (the reader read a
    #        resistivity or magnetic feature of another survey as this method).
    alltext = hl + " " + body
    for r in rows:
        if r.get("sample_type") == "geophysics":
            mrx = METHOD_RX.get(r.get("survey_type") or "")
            if mrx is not None and not mrx.search(alltext):
                return False, "survey method not named: " + str(r.get("survey_type"))

    # 1. Acquisition / program-start / partner-drill releases that restate old sampling: admitted when the reader
    #    flagged every row historical AND the release itself talks about historic / previous-operator / government
    #    work AND the headline does not announce a new assay (a grade in the headline means the results are new,
    #    so an all-historical output is the reader misreading them). Otherwise the flag is unsupported: refuse.
    if all(r.get("historical") for r in rows):
        # round 3: a deal, technical-report or historical-data headline backs the flag by itself (reader 1.0.1 flags
        # every result in such a release historical), and an ownership share ("100%") is not a grade
        old_hl = HIST_HL.search(hl) or DEAL_HL.search(hl) or TECH_HL.search(hl) or LAND_HL.search(hl)
        # (7b) a headline announcing results / assays of its own counts like a grade ("Announces High-Grade Gold
        # Results at its Newly Acquired Mine": the results are new, an all-historical output misreads them)
        grade_hl = GRADE_HL.search(OWN_PCT.sub(" ", hl)) or OWN_RESULT_AFTER.search(hl)
        if not ((HIST_TEXT.search(body) or old_hl) and (not grade_hl or HIST_HL.search(hl))):
            return False, "historical flag unsupported"
        # round 4: every row must be quoted as older work where the release gives it. A deal or program-start
        # release often quotes the vendor's or prospector's recent program (new results under the guide), the
        # company's own earlier results (restated: no row), or a neighbour's discovery, and the reader flags them
        # all historical; only results the release itself frames as historic are safe.
        # (7b) option / earn-in agreements are refused on this path
        if OPTION_HL.search(hl):
            return False, "option agreement quoting older work"
        sup = [_old_support(r, hl, body) for r in rows]
        if "own" in sup:
            return False, "historical row is the company's own or recent work"
        if "old" not in sup:
            return False, "historical rows not framed as old work"
        return True, "all rows historical"

    # 2. Reader self-consistency:
    #    - a brine unit (mg/L) on a rock row is a mistyped brine sample;
    #    - a mapping-only output on a release whose lead gives assays means the reader missed the assayed samples;
    #    - two or more rock rows (grab / chip / channel / trench): the reader's rock typing is unreliable when a
    #      release mixes sample methods -- it splits "channel chip" samples into channel + chip, adds a trench row
    #      for grab samples taken from trenches, or keys one sample set twice (4 of 10 such releases carry a wrong row,
    #      against about 1 in 30 for a single rock row).
    for r in rows:
        bg = r.get("best_grade") or {}
        unit = (bg.get("unit") or "").lower()
        if r.get("sample_type") in ROCK and unit == "mg/l":
            return False, "rock row with brine unit"
    if all(r.get("sample_type") == "mapping" for r in rows) and GRADE_LEAD.search(lead):
        return False, "mapping-only on assayed release"
    # (round 3: the "two or more rock rows" refusal is dropped -- reader 1.0.1 keys channel-chip samples as one chip
    # row and grab samples taken from trenches as grab, the splits that rule was guarding against)

    # 3. Technical reports, resource estimates, plants, financings, quarterlies, corporate updates.
    if HARD_NEG_HL.search(hl):
        return False, "corporate/technical headline"
    # 4. Historical results, compilations, desktop reviews / studies / maps.
    if HIST_HL.search(hl):
        return False, "historical/review headline"
    # 4b. Survey or sampling presented as future work ("identifies targets for heliborne survey").
    if PLANNED_HL.search(hl):
        return False, "planned-work headline"
    # 4c. (round 5) Assays still at the laboratory ("samples have been shipped to the lab", "results will be
    #     released upon compilation"): the grades the release quotes are earlier results recapped, unless the
    #     headline itself gives a grade.
    if PENDING_LEAD.search(opening) and not GRADE_HL.search(OWN_PCT.sub(" ", hl)):
        return False, "assays pending: rows are a recap"
    # 4d. (round 7) A row whose grade the release quotes only beside a citation of an earlier release ("see news
    #     release dated ...", "previously reported", "(reported August 4, 2015)"): restated, not this release's news.
    for r in rows:
        if _restated(r, hl, body):
            return False, "row restated from an earlier release"

    hf = _fams(hl)
    hl_surf = DEPTH_SURF.sub(" ", hl)
    # 5. Drill-result releases: admitted only if the headline also names surface samples, or a NEW geophysical
    #    finding ("discovers large magnetic anomaly", "magnetic survey results"). A headline interval
    #    ("5.3 m at 6.57 g/t", "zone of 284 m from surface") with no surface-sample word is a drill intercept,
    #    unless the lead itself opens on surface sampling rather than drilling.
    drill = bool(DRILL_HL.search(hl))
    if not drill and INTERVAL_HL.search(hl) and not SURFACE_HL.search(hl_surf):
        ms, md = LEAD_SURF.search(body[:1500]), LEAD_DRILL.search(body[:1500])
        drill = not ms or (md is not None and md.start() < ms.start())
    if drill:
        surf = hf - {"geophysics"}
        if not surf and not GEO_FIND_HL.search(hl):
            return False, "drill headline"
        # 5b. Drill-start releases that lead with the drill start ("commences drilling to test the new vein,
        #     samples up to 54 g/t"): the surface results are the ones that made the target, already reported.
        #     A headline that first announces a new result, then the drilling ("discovers soil anomaly and
        #     prepares targets for drilling"), is kept.
        ds, rs = DRILL_START_HL.search(hl), RESULT_HL.search(hl)
        if ds and not GEO_FIND_HL.search(hl) and (not rs or ds.start() < rs.start()):
            return False, "drill-start headline"
        if not surf:
            hf = {"geophysics"}
    # 6. Deals (acquire, option, stake, sell, agreements): only when the headline itself reports a sampling result.
    #    (round 5: a new land / exploration position assembled is a deal too)
    if DEAL_HL.search(hl) and not (hf and DISC_HL.search(hl)):
        return False, "deal headline"
    if LAND_HL.search(hl) and not DISC_HL.search(OWN_PCT.sub(" ", hl)):
        return False, "deal headline"
    # 6b. (round 7) An acquisition / option headline that quotes a sampling result: the samples are the vendor's or
    #     older work. A row the reader keys as new is kept only when the release dates its grade as recent work
    #     where it quotes it (the vendor's recent, unreleased program is new under the guide).
    if BUY_HL.search(hl):
        ry = _release_year(body)
        for r in rows:
            if not r.get("historical") and not _recent(r, hl, body, ry):
                return False, "deal headline: new flag not supported"
    # 7. Headline must announce a result: name a sample / survey kind, or use discovery / result language.
    if not hf and not DISC_HL.search(hl):
        return False, "no result headline"
    # 8. "Completes soil program", "commences sampling": work done or planned, no result.
    #    (round 5: a known deposit named as a place -- "on strike from its VMS discovery" -- is not a result word;
    #    "defining a chargeability anomaly" is one)
    hl_res = PLACE_DISC.sub(" ", hl)
    # 7b. (round 7) The headline must carry result language (a grade, a find, an anomaly, "results", "returns",
    #     "yields", ...): a headline that only names a survey or sampling program announces the work, not results.
    if not (ANY_RESULT_HL.search(hl_res) or GEO_FIND_HL.search(hl_res)):
        return False, "no result language in headline"
    if STATUS_HL.search(hl) and not (RESULT_HL.search(hl_res) or GEO_FIND_HL.search(hl_res) or ANN_RESULT.search(hl_res)):
        return False, "program-status headline"
    # 8d. (round 7) Work planned or starting is the headline's news, before any result language.
    ws, rs = WORK_START_HL.search(hl_res), ANY_RESULT_HL.search(hl_res)
    if ws and (rs is None or ws.start() < rs.start()) and not GEO_FIND_HL.search(hl_res[:ws.start()]) \
            and not FIRST_RESULTS_HL.search(hl_res[ws.end():]):
        return False, "work planned or starting"
    # 8e. (7b) Work finished is the headline's news ("Completes Field Work on Newly Identified Targets"): unless the
    #     headline then gives a grade or the work's own results / assays, the rows are earlier or background results.
    wd = DONE_HL.search(hl_res)
    if wd and not grade_in_hl and not OWN_RESULT_AFTER.search(hl_res[wd.end():]) \
            and not (rs is not None and rs.start() < wd.start() and OWN_RESULT_AFTER.search(hl_res[:wd.start()])):
        return False, "work completed, no result in headline"
    # 8a. (round 5) Announced-only work: the opening announcement says a survey or sampling program is contracted,
    #     about to start, starting or partway done, and the headline reports no result. Any rows are the reasons for
    #     the program (older results, known anomalies), not its results.
    if ANNOUNCE_LEAD.search(opening) and not (ANN_RESULT.search(hl_res) or GEO_FIND_HL.search(hl_res)):
        return False, "announced-only program"
    # 8b. Geophysics named only as a place ("discovers favourable rocks on the southern IP trend"): the headline
    #     must report on a survey, its data or a geophysical feature found, else the feature is known background.
    if hf == {"geophysics"} and not (GEO_SURVEY_HL.search(hl) or GEO_FIND_HL.search(hl)):
        return False, "geophysics only as a place"

    # 8c. (round 4) Survey data bought or taken over from others ("the purchase of undocumented IP data ... has
    #     resulted in a new target"): the data are historical, so a row the reader keys as new is wrong.
    if BOUGHT_DATA.search(lead) and not all(r.get("historical") for r in rows):
        return False, "bought data keyed as new"
    rowfams = {ROW_FAM.get(r.get("sample_type"), "?") for r in rows}

    # 9. Sampling headline: every row must be of a kind the headline names (other kinds are property background,
    #    e.g. old soil anomalies quoted in a trench-results release). Rock sampling covers mapping findings.
    if hf:
        # 9a. A kind the headline names only as work completed or started has no result in this release.
        rest = STATUS_CLAUSE.sub(lambda m: m.group(0) if RESULT_HL.search(m.group(0)) else " ", hl)
        status_only = hf - _fams(rest)
        if rowfams & status_only:
            return False, "row kind named only as work done: " + ",".join(sorted(rowfams & status_only))
        # 9b. (round 7) A kind the headline names only as the reference for a new result ("drone MAG survey
        #     correlates with the results of the summer soil program", "seismic anomalies correlating with IP
        #     targets previously defined"): that kind's results were reported before.
        before_ref = REF_SPLIT.split(hl, 1)[0]
        fresh_hl = _old_free(PREV_KIND.sub(" ", before_ref))
        fresh = _fams(fresh_hl)
        ref_only = hf - fresh
        if rowfams & ref_only:
            return False, "row kind named only as reference: " + ",".join(sorted(rowfams & ref_only))
        # (geophysics: the same, method by method -- "seismic anomalies correlating with IP targets")
        for r in rows:
            mrx = METHOD_RX.get(r.get("survey_type") or "") if r.get("sample_type") == "geophysics" else None
            if mrx is not None and mrx.search(hl) and not mrx.search(fresh_hl):
                return False, "survey method named only as reference: " + str(r.get("survey_type"))
        missing = rowfams - hf - ({"mapping"} if "rock" in hf else set())
        # 9c. (round 7) A headline reporting generic "sample results" names no medium; the kinds the opening
        #     announcement sentence reports ("the first assay results for rock and soil samples") are covered.
        if missing and hf == {"rock"} and not FAM_RX["rock"].search(GENERIC_SAMPLE.sub(" ", hl)):
            # (the announcement after the body's copy of the headline, wherever a letterhead puts that copy)
            k = body[:1500].find(hl.strip()[:40]) if hl.strip() else -1
            ann = _announcement(body[k + len(hl.strip()):k + len(hl.strip()) + 1500] if k >= 0 else opening)
            missing = {f for f in missing if not (f in FAM_RX and _fresh_mention(FAM_RX[f], ann))}
        if missing:
            return False, "row kind not in headline: " + ",".join(sorted(missing))
        return True, "sampling headline"

    # 10. Discovery headline naming no sample kind ("discovers new zone"): every row's type must appear in the
    #     headline or lead paragraphs, where a release states its own news -- and not only as "previous trenching",
    #     "historic soils" (older work quoted to support new targets).
    # 10a. (round 5) A discovery headline over a drill release: the opening reports drilling before any surface
    #      sample, so the surface results quoted are the background that led to the hole. Only the
    #      announcement sentence counts ("is pleased to announce that drilling has intersected ..."); drill targets,
    #      drill-ready prospects and old holes quoted further on do not.
    if DRILL_NEWS.search(_announcement(opening)):
        return False, "discovery headline over a drill release"
    # 10b. (7b) A headline naming no sample kind over a release whose opening reports drill results (intercepts,
    #      holes, backpack drilling): a drill or mixed release; its surface rows are mostly background.
    if OPEN_DRILL.search(opening):
        return False, "discovery headline, drill results in the opening"
    for r in rows:
        st = r.get("sample_type")
        if st == "geophysics":
            srx = SURVEY_RX.get(r.get("survey_type") or "") or GEO_ANY
        else:
            srx = TYPE_RX.get(st)
        if not srx or not srx.search(lead):
            return False, "type not in lead: " + str(st)
        if not _fresh_mention(srx, lead):
            return False, "type in lead only as old work: " + str(st)
    return True, "discovery headline"
