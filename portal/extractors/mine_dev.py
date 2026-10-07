"""Mine Development & Operations reader, facts-store version (DEV_V1, 2026-09-28).

The source of the Mine Development & Operations page once it passes the accuracy gate. Written against the 65-item key
Justin confirmed on 2026-09-28 (51 releases with rows, 75 rows; claude/MNT_DEV_SET_LABELS_CONFIRMED_2026-09-28.json)
and the label guide claude/MNT_DEV_LABEL_GUIDE_2026-09-28.md.

Justin's rules (2026-09-27/28):

  1. ONE ROW PER EVENT a release reports as news for the issuer's own mine, plant or project (any interest it holds):
     build milestones (construction decision, construction start, construction progress, infrastructure,
     commissioning, first production, commercial production, ramp-up, expansion, site cleanup), operating status
     (restart, suspension, care and maintenance, closure, a routine operations update as a status update), incidents,
     and commercial events (offtake, shipment or sale, contract).
  2. MILESTONES ONLY (rule DG): the pieces of an ongoing build (camp, road, power line) are part of its progress row,
     unless one of them is the headline's news.
  3. STATUS: achieved (it happened), underway (in progress now), planned (a target with a date or a concrete step;
     vague intent is no row, rule DV). A construction or expansion decision is achieved; a restart decided but not
     yet running is planned (rule DS).
  4. FIELDS when stated: the mine (shared project-name helper), the event date (the target date for a planned row, the
     "as at" date for an underway one), capex (budget, spent or committed; a bare "$" with no declared currency keeps
     no currency, rule DC), overall % complete, and the figures stated with the milestone (Justin: "milestones plus
     early figures").
  5. NOT ROWS: exploration (drill results, field programs, "restarts drilling"), studies and permits on their own,
     financings on their own, pilot and lab test plants (rule DP), a royalty or stream holder's report on someone
     else's mine (rule DR), donations and appointments, events restated as background.

1.0.1 (2026-09-30, ACC150 + outside-tag samples; still the headline's event only):
  - FALSE EVENTS: "green light" only as an approval phrase, never inside a company or project name; a cue inside the
    issuer's own name (a company called "First <Metal>" announcing anything) is masked; exploration is not mining (ramp up drilling or a program,
    expansion of a property, land, claims, survey or drill program, restart or pause of fieldwork or exploration,
    exploration declines, drill roads and camps, "% complete" of a survey); "first <metal>" before a project, brine,
    converter or battery noun is not first production; a study, design, FEED or PEA headline (no decision in the lead)
    and pilot, test or demonstration plants (rule DP) give no build row; a loan or tranche "for the expansion" needs
    build news in the lead; a permit or court item about a facility is not its construction; offtakes and contracts
    need a company with a mine, plant or product of its own, and a property sale or forward sale is not an offtake;
    a natural hazard is an incident only with an evacuation, stand-down or damage and a stop at the company's site
    (rule DX), never "no damage"; relief pledges are donations; routine maintenance shutdowns and remediation after an
    incident are not suspension or site cleanup rows.
  - ONE EVENT, ONE ROW / RIGHT TYPE: groundbreaking for an expansion is the expansion's row; the expansion of a solar
    plant or power line is the infrastructure row; "ramping up the Phase II expansion" is the ramp-up row; a contract to
    sell product is an offtake; construction of a road, power line, portal or shaft is infrastructure; an accident,
    rescue or fatality headline gives the incident, not a build row.
  - STATUS from the headline's wording: an expansion is achieved when completed or decided, underway when initiated,
    advancing, on track or reported in a results release; a signed offtake or contract is achieved; a shipment being
    readied is planned; "starts laying track" is underway; a restart approved and begun today is achieved.
  - MINE: table text and verb phrases are not names ("Cash 16.1 ... Property", "X Presents Project"); a contractor's
    name ("<X> Mine Repair and Maintenance") is not a mine; the release's one project names a headline row only when the lead names it
    (accents folded, a one-word name like "Mon" counts), or for a shipment or offtake when the body says the product is produced there.
  - ANSWER-KEY GATE (round 2): "Accelerates <Mine> Ramp-Up" is a ramp-up; an expansion "to be completed in <year>" is planned; a
    wildfire or earthquake the headline says interrupted, suspended or closed the company's operations or shipping is an incident.
  - CAPTURE (rows stay >= 90% right): construction nears completion or on schedule, development progress, solar farms,
    performance tests, production at commercial levels or expected to commence, returns to full construction, first
    <product> sales, shipments commenced, contractors designated or retained, purchase orders, fire situations,
    accidents, rescue operations, commissioning updates.
  - FULL TEXT (2026-10-01; the box reads whole releases, where highlight lists and sub-headlines run into the lead):
    a study the lead mentions is a side item when the headline's own clause states its milestone as done or under way
    ("achieves first gold pour", "completes sinking of Shaft 1", "development exceeds 1,840 metres") with no study
    before it; a wildfire or earthquake is also an incident when the lead says staff were reduced or withdrawn,
    operations or underground work were suspended, or the site was damaged or reached (never when negated); in a
    financing headline a decision stated as taken ("Announces Construction Decision", "Confirming FID", "Board
    Approves") or a second clause of its own ("... and Provides Construction Update") is news; a production phase,
    stage, expansion or commercial production is a ramp-up object, as is "ramp-up of <the release's project>"; "Field
    Programs Ramp-Up" is exploration; a permit headline whose sub-headline says construction started keeps the start;
    pre-construction, early works and underground activities are not exploration; a stop of "exploration and
    development activities" at a non-exploration release is a suspension; a company whose lead says its product is
    sourced from its facility or names its own projects has a product of its own; "starter" and "construction" (a
    "Construction Facility" is a loan) are not plant names; a
    shaft sunk to final depth is achieved.

1.0.2 (2026-10-02, ACC150b re-check: page rows right but capture low; still the headline's event, plus what the label rules tie to it):
  - INCIDENT AND ITS STOP (the key's fatality / fire-cut-rail examples): an incident headline whose lead says operations or
    activities were suspended, halted or paused gives a suspension row too; a suspension headline caused by a fire, slip,
    collapse, flood, heavy rain or strike gives the incident row too; a COVID notice whose lead suspends operations gives the
    suspension; "Resolves Labour Action" with operations resuming is a restart (planned when the resumption is expected).
  - HEADLINE WORDINGS: fall of ground, employees strike, strike by the workforce, heavy rains / storms / landslides (hazard
    rule DX applies; "no injuries" does not cancel it), a slip on the leach pad; "Update Following Fire at" and "suspended due to
    ... following heavy rains" keep the incident; start of process plant operations (commissioning, achieved); custom or
    toll milling and contract mining agreements; leach pad expansion; infrastructure milestones and "advances toward
    commissioning" (construction progress); "recommence uranium production" (restart); "first gold concentrate agreement" is an
    offtake, not first production; "<plant> commissioning update" is under way whatever guidance clause precedes it.
  - DATED TARGETS: a planned event the headline states with its own date ("Production Expected to Commence in Q3 2026") is a
    row beside the headline's other event; rule DV's target date or concrete step may sit in the announcement ("targeting the
    mill restart in 2026", "FID expected in mid-2027", "will immediately implement a phased restart").
  - RESTARTS: a construction update at a mine being brought back online is the restart's row (planned while permits are
    pending); "Update on Resumption of Operations" whose lead says operations will resume is planned; "is ramping up as planned"
    is under way, not a plan.
  - NAMES: one event at two named mines ("at both <A> and <B>") or a region's operations whose lead lists the mines is one row per
    mine; "<Name> mine/operations" written in lower case names an unnamed headline row; "Bolivian Operation" names no mine.
  - GENERIC HEADLINES ("Provides Operations Update", "Q3 Results", "Update on <X> Operations") with no event of their own: the
    event the announcement states (within three sentences of it) is the news when stated as news - dated or just done, not a quote,
    a dated recap ("In August 2018, ..."), a bracketed aside or a state that continues - and not a deal or a piece of the build.

1.0.3 (2026-10-04: precision first; each change kept only when the rows it adds or removes were right on the dev labels):
  - WORDINGS: commissioning on track / started / "commissioning <the> circuit" / "update to <X> commissioning" / plant start-up /
    processing of mined ore begun ("commissioning and production ramp-up" is the ramp-up's one row); an agreement signed "for
    the construction of" a facility is the contract; a strike suspended or settled is a restart.
  - ONE ROW PER EVENT: the announcement's other commissioning, construction, infrastructure, shipment or build-contract
    milestones at the headline's mine (announcement + 3 sentences, done or under way, none the sentence forecasts).
  - NOT ROWS: evaluating a restart (rule DV); a battery or energy-storage system; a clarification of an agreement;
    compensation for an earlier incident; a hazard that cut a third party's power or rail; a deposit's "ramp-up activities";
    a site-access, camp or drilling contractor.
  - STATUS: a forecast or target in the event's clause, or a decision "to place / to restart", is never achieved;
    commissioning started, a staged return, transport begun, a restart project update and a blockade that remains are under
    way; "planned" before the event is planned (the headline's announced plan is rule DV's decision); ramp-up achieved only
    when the achieving word is at the event; "50% construction completion" is under way; a month with no year takes the
    release year, and the release date falls back to the first full date.

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per row (ordinal 0..n-1)
to_prediction(records) -> dict|None    what the accuracy judge compares

Self-tests: python3 -m portal.extractors.mine_dev
"""
from __future__ import annotations

import re
import unicodedata

from portal import facts as F
from portal import fingerprint as FP
from portal import project_names as PN
from portal.extractors import technical as T

NAME = "mine_dev"
VERSION = "1.0.4"  # 2026-10-04 FIX5: version only (the Technical reader helpers it borrows were rewritten ASCII-only, same behaviour); 2026-09-30: false events dropped (names, exploration, studies, financings, others' products), one event one row, headline status, wider headline capture; 2026-10-01: study side items, hazards at the site, decisions and updates in financing headlines, ramp-up objects, own products; full-text losses fixed; 2026-10-02: capture (incident and its stop, new headline wordings, dated targets in the headline or lead, resolved stops and restart works, one row per named mine, generic update headlines' announced event); 2026-10-03 FIX5: precision first - commissioning wordings, the announcement's other milestones at the headline's mine, contract and restart retypes, refusals of vague evaluations, non-mine products, past or third-party incidents, deposit ramp-ups and site-access contractors, forecasts never achieved
KIND = "mine_event"
TAG = "Mine Development & Operations"
TEXT_CAP = 40000
NEWS_SENTS = 14                     # the lead: headline + this many sentences carry the news
HEADLINE_ONLY = True                # Justin 2026-09-28: rows only for the event the headline announces (rules reader,
                                    # narrowed after honest sample 2); body sentences still give its date and figures

EVENT_TYPES = ("construction_decision", "construction_start", "construction_progress", "infrastructure", "site_cleanup",
               "commissioning", "first_production", "commercial_production", "ramp_up", "expansion", "restart",
               "suspension", "care_maintenance", "closure", "status_update", "incident", "offtake", "shipment",
               "contract")
STATUSES = ("achieved", "underway", "planned")
BUILD = ("construction_decision", "construction_start", "construction_progress", "infrastructure", "site_cleanup",
         "commissioning", "first_production", "commercial_production", "ramp_up", "expansion")
TXT_FIELDS = ("event_type", "mine", "status", "event_date", "incident_kind", "counterparty", "cause", "capex_currency",
              "capex_basis", "figures_json", "evidence")
NUM_FIELDS = ("capex", "capex_high", "pct_complete")

# ------------------------------------------------------------------ text
_FLS = re.compile(r"(?i)(?:^|\s)(?:cautionary\s+(?:note|statement|language)s?\b|forward[\s\-]+looking\s+(?:statements?|information)"
                  r"\s*(?:$|[A-Z:])|notice\s+regarding\s+forward|neither\s+(?:the\s+)?(?:tsx|canadian\s+securities|cse)\b|"
                  r"no\s+stock\s+exchange|to\s+view\s+the\s+source|qualified\s+persons?\s*(?:$|[A-Z:]))")
_ABOUT_CO = re.compile(r"(?:^|\s)About\s+(?:the\s+Company\b|Us\b|[A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5}\s*(?:[:.]|\s(?=[A-Z][a-z]+\s"
                       r"(?:is|was|Inc|Corp|Ltd|Limited|Resources|Metals|Mining|Gold|Silver|Copper|Energy|Minerals)\b)))")
_SPLIT = re.compile(r"(?<![\s(][A-Z]\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\bSt\.)(?<!\bMt\.)(?<!\bNo\.)(?<!\bvs\.)(?<!\bapprox\.)"
                    r"(?<=[.;!?])\s+(?=[A-Z\u201c\"\u2022\u25aa(])|\s+[\u2022\u25aa\u25cf\u00a7]\s+|\s+(?:-|\u2013)\s+(?=[A-Z])(?!(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d)")
_LEGAL_END = re.compile(r"\b(?:Corp|Inc|Ltd|Co|Pty|S\.A|L\.L\.C|U\.S|No)\.$")


def _prepare(headline, body):
    b = T._norm((body or "")[:TEXT_CAP]).replace("\u2010", "-").replace("\u2011", "-")
    b = re.sub(r"(?i)\bapprox\s+imately\b", "approximately", b)
    b = re.sub(r"\b(A|O|N|S|D|J|M|F)\s(ug|ct|ov|ep|ec|an|ar|ay|eb|un|ul)\b", r"\1\2", b)      # PDF gaps: "A ug 11", "N ovember"
    b = re.sub(r"\b(N)\s(ovember)\b|\b(O)\s(ctober)\b|\b(S)\s(eptember)\b", lambda m: "".join(g for g in m.groups() if g), b)
    b = re.sub(r"(?i)\bapproximatel\s+y\b", "approximately", b)
    b = re.sub(r"(?<=[A-Za-z])- (?=[A-Za-z])", "-", b)                          # "High- Grade" (a PDF line break)
    b = re.sub(r"https?://\S+", " ", b)
    b = re.sub(r"[\uf0a7\uf0b7\u2022\u25aa\u25cf]", " \u2022 ", b)
    b = T._flat(b)
    fls = _FLS.search(b, int(len(b) * 0.30))
    if fls:
        b = b[:fls.start()]
    for m in _ABOUT_CO.finditer(b, 600):
        b = b[:m.start()]
        break
    h = T._flat(T._norm(headline or "").replace("\u2010", "-").replace("\u2011", "-"))
    return h, b


def _sentences(b):
    raw, parts = [], []
    for p in _SPLIT.split(b):
        p = (p or "").strip(" \u2022")
        if not p:
            continue
        if raw and len(p) <= 12:
            raw[-1] += " " + p
        else:
            raw.append(p)
    for s in raw:
        if parts and (s[:1] == "(" and _LEGAL_END.search(parts[-1]) or re.match(r"^[a-z0-9$]", s)):
            parts[-1] += " " + s
        else:
            parts.append(s)
    return parts


# ------------------------------------------------------------------ event cues
_P = lambda s: re.compile(s, re.I)  # noqa: E731
CUES = [
    ("construction_decision", _P(r"\b(?:formal\s+)?(?:construction|production|development)\s+decision\b|\bdecision\s+to\s+(?:proceed|build|construct|"
                                 r"develop|advance|commence\s+(?:full\s+)?construction|start\s+construction)\b|\bfinal\s+investment\s+decision\b|\bFID\b|\b(?:receiv\w*|gets?|got|given|gave|gives|obtain\w*|secur\w*|grant\w*|wins?|won)\s+(?:(?:the|a|an|its|final|formal|official|board|"
                                 r"regulatory)\s+)*green[\s-]?light\b|\bgreen[\s-]?light(?:s|ed)?\s+(?:to|for)\s+(?:\w+\s+){0,3}(?:construction|build\w*|develop\w*|"
                                 r"proceed|start|restart|commenc\w*|expansion|mine|mining|production)\b|\bgreen[\s-]?lit\b|\bboard\s+(?:of\s+directors\s+)?"
                                 r"(?:has\s+)?approv\w+\s+(?:the\s+)?(?:construction|development|build)|\bproceed(?:ing|s)?\s+with\s+(?:the\s+)?(?:project\s+)?"
                                 r"(?:construction|development|build)\b|\bapprov\w+\s+(?:the\s+)?construction\s+of\b")),
    ("construction_start", _P(r"\b(?:re-?commenc|commenc|begin|began|begun|start)\w*\s+(?:of\s+)?(?:full[\s-]scale\s+|main\s+|early[\s-]works?\s+|"
                              r"(?:the\s+)?(?:project\s+)?)?construction\b|\bconstruction\s+(?:has\s+|have\s+)?(?:officially\s+)?(?:commenced|started|"
                              r"began|begins|begun|is\s+set\s+to\s+(?:begin|start))\b|\bbr(?:eaks?|oke)\s+ground\b|\bground[\s-]?breaking\b(?=\s+(?:ceremony|event|"
                              r"celebration|of|for|at|on|was|has|took|in)\b|\s*[.,;:]|\s*$)|"
                              r"\bstart\s+of\s+(?:full\s+)?construction\b")),
    ("construction_complete", _P(r"\bcomplet\w+\s+(?:the\s+)?(?:\w+\s+){0,2}construction\b|\bconstruction\s+(?:\w+\s+){0,6}?(?:is|was|has\s+been|have\s+been)\s+"
                                 r"(?:now\s+|substantially\s+|fully\s+|successfully\s+)?complet\w+|\bconstruction\s+complet(?:ed|ion)\b")),
    ("construction_progress", _P(r"\bconstruction\s+(?:update|progress|activities|milestones?)\b|\binfrastructure\s+milestones?\b|\bconstruction\s+(?:\w+\s+){0,3}?near(?:s|ing)?\s+"
                                 r"complet\w+|\bnear(?:s|ing)?\s+construction\s+complet\w+|\b(?:construction|project)\W{0,3}\s*"
                                 r"(?:is\s+|remains?\s+)?on\s+(?:schedule|track|budget)\b|\b(?:project\s+)?development\s+progress\b|\bconstruction\s+(?:is|was|remains|continues)\b|"
                                 r"\b(?:overall|project|construction|physical)\s+(?:progress|completion)\b|\badvanc\w+\s+(?:\w+\s+){0,2}?toward\w*\s+commissioning\b|\b(?:construction|project|development)\s+(?:\w+\s+){0,4}"
                                 r"(?:remains?|continues?|is|are)\s+(?:to\s+progress\s+)?on\s+(?:track|schedule|budget)\b|\bon\s+(?:schedule|budget)\b[^.]{0,40}"
                                 r"(?:construction|first\s+gold|first\s+production)|\b(?:mine|project)\s+development\s+update\b|"
                                 r"\b\d{1,3}(?:\.\d)?\s?%\s+(?:complete|completed|physical\s+completion)\b")),
    ("site_cleanup", _P(r"\b(?:early\s+)?(?:environmental\s+)?(?:clean[\s-]?up|remediation)\s+(?:activities|work|of\s+(?:the\s+)?legacy)|"
                        r"\blegacy\s+(?:site|mine\s+waste|waste)\s+(?:clean|remediat)")),
    ("commissioning", _P(r"\b(?:hot|wet|dry|cold)\s+commissioning\b|\bcommissioning\s+(?:of|is|has|activities|underway|began|begins|commenced|"
                         r"complete|completed|phase|process|update|progress)\b|\b(?:commenc|begin|began|start|complet)\w*\s+(?:the\s+)?(?:pre-)?commissioning\b|"
                         r"\b(?:commenc|begin|began|start)\w*\s+processing\s+(?:of\s+)?ore\b|\bprocessing\s+(?:of\s+ore\s+)?to\s+(?:start|commence|begin)\b|"
                         r"\bperformance\s+test\b|\bstart\s+of\s+(?:the\s+)?(?:process(?:ing)?\s+)?(?:plant|mill)\s+operations\b|"
                         r"\b(?:process(?:ing)?\s+)?(?:plant|mill)\s+(?:starts|begins|commences|started|began|commenced)\s+operations\b|"
                         r"\bcommissioned\b|\bfirst\s+ore\s+(?:to|through|into|was\s+fed|fed)\b|\bheat[\s-]up\b")),
    ("first_production", _P(r"\bfirst\s+(?:gold\s+|silver\s+|dor[e\u00e9]\s+)?pour\b|\bpours?\s+(?:its\s+|the\s+)?first\b|\bpoured\s+(?:its\s+|the\s+)?first\b|"
                            r"\bfirst\s+(?:gold|silver|dor[e\u00e9]|bars?|concentrate|copper\s+concentrate|zinc\s+concentrate|lead\s+concentrate|"
                            r"cathode|copper|ore\s+crushed|lithium|spodumene|production)\b(?!\s+(?:results|guidance|drill|hole|backed|nft|token|"
                            r"(?:concentrate\s+|offtake\s+|sales?\s+|purchase\s+)?(?:agreements?|contracts?|offtake)|"
                            r"discover\w*|resource|estimate|royalt\w*|stream|etf|fund|coin|mine\b|project|property|asset|acquisition|claims?|"
                            r"exports?|sales?|shipments?|deliver\w*|equivalent|and\s+silver\s+(?:discover|resource)|intercept\w*|wells?|minerals?|"
                            r"resources?|corp\w*|inc|ltd|metals|mining|evaluation|drill\w*|under\s+(?:the|its|our|new)|of\s+(?:\w+\s+){0,3}"
                            r"(?:sorbent|samples?|precursor|material|battery|cells?))|(?:\s+(?!(?:at|from|to|in|on|of|for|by|with|and)\b)[\w-]+){0,2}\s+(?:"
                            r"project|property|brine|converter|refinery|facility|deposit|discovery|company|claims|district|battery|recycling)\b)|"
                            r"\bfirst\s+(?:dor[e\u00e9]\s+)?(?:dispatch|bar)\b|\bproduction\s+(?:is\s+)?(?:expected|scheduled|targeted|set|slated|planned)\s+"
                            r"to\s+(?:commence|start|begin)\b")),
    ("commercial_production", _P(r"\bcommercial\s+production\b|\bproduc\w+\s+(?:\w+\s+){0,2}at\s+commercial\s+(?:levels|rates|scale)\b")),
    ("ramp_up", _P(r"\bramp[\s-]?up\b|\bramps?\s+up\b|\bramping\s+up\b|\bnameplate\s+(?:capacity|throughput|rate)\b|\bdesign\s+(?:capacity|"
                   r"throughput)\b|\bsteady[\s-]state\b")),
    ("expansion", _P(r"\bexpansion\s+(?:project|plan|program|of\s+the|to\s+\d|is|was|remains|construction|capital|decision)\b|"
                     r"\b(?:mill|plant|throughput|capacity|underground|phase\s+\w+|(?:leach\s+)?pad)\s+expansion\b|\bexpand\w*\s+(?:the\s+)?(?:[\w-]+\s+){0,2}?(?:mill|plant|"
                     r"throughput|capacity|processing)\b|\b(?:commenc|begin|began|start)\w*\s+(?:\w+\s+){0,4}sulphide\s+(?:ore|project|plant)\b|"
                     r"\bsulphide\s+expansion\b")),
    ("restart", _P(r"\brestart\w*\b|\bre-start\w*\b|\bresum\w+\s+(?:of\s+)?(?:full\s+|normal\s+)?(?:mining|operations|production|processing|"
                   r"milling|railway|rail|activities|shipments?)\b|\b(?:operations|mining|production|processing)\s+(?:have\s+|has\s+)?"
                   r"(?:resumed|recommenced)\b|\brecommenc\w+\s+(?:mining|operations|production|processing)\b|\bresumption\s+of\s+(?:\w+\s+){0,3}"
                   r"(?:mining|operations|production|processing|milling|activities|work|underground|open[\s-]pit|plant|mill)\b|"
                   r"\b(?:resum|recommenc)\w*\s+[a-z]+\s+(?:production|mining|operations|processing|milling)\b|"
                   r"\breopen\w*\s+(?:the\s+)?(?:mine|mill|plant)\b|\breturns?\s+to\s+(?:full\s+)?(?:construction|operations|production|mining)\b")),
    ("suspension", _P(r"\bsuspen(?:d|ds|ded|ding|sion)\b|\bcurtail\w*\b|\btemporar\w+\s+(?:halt|shut|stop|pause|clos)\w*|\bshut\s*down\b|"
                      r"\bshuts?\s+down\b|\bhalt\w*\s+(?:of\s+)?(?:all\s+)?(?:mining|operations|production|processing|milling|construction)\b|"
                      r"\bstop(?:s|ped|ping)?\s+(?:all\s+)?(?:mining\s+)?(?:operations|mining|production|processing|milling)\b|\bon\s+hold\b|"
                      r"\b(?:production|operations|mining|processing)\s+(?:\w+\s+){0,3}(?:to\s+)?paus\w+|"
                      r"\bpaus\w+\s+(?:\w+\s+){0,2}(?:mining|operations|production|processing)\b|\b(?:mining|operations|production|processing)\s+"
                      r"(?:\w+\s+){0,2}(?:paused|halted|stopped)\b|\blower\s+its\s+throughput\b")),
    ("care_maintenance", _P(r"\bcare\s+(?:and|&)\s+maintenance\b")),
    ("closure", _P(r"\bpermanent(?:ly)?\s+clos\w+\b|\bend\s+of\s+(?:the\s+)?mine\s+life\b")),
    ("incident", _P(r"\bfatal\w*\b|\bfatality\b|\bpassed\s+away\b|\bdeath\s+of\s+(?:an?\s+)?(?:employee|contractor|worker)|\bfire\s+(?:at|in|broke)\b|"
                    r"\b(?:wild|forest|bush)\s*fires?\b|\bexplosion\b|\bflood(?:ing|ed)?\s+(?:at|of|in)\s+(?:the\s+)?(?:mine|pit|underground|"
                    r"plant|site)|\b(?:ground|wall|pit\s+wall)\s+(?:collapse|failure)\b|\brockburst\b|\bseismic\s+event\b|"
                    r"\b(?:labou?r|union|workers?')\s+(?:strike|action|dispute|stoppage)\b|\bunion\s+(?:commences|begins|began)\s+strike\b|"
                    r"\bblockade\w*\b|\billegal\s+min(?:ers?|ing)\b|\bevacuat\w+\b|\bsecurity\s+incident\b|\bincident\s+at\b|"
                    r"\b(?:reports?|addresses)\s+(?:an?\s+)?(?:recent\s+)?incident\b|\bpolice\s+operation\b|\bearthquake\b|\baccident\b|"
                    r"\brescue\s+(?:and\s+recovery\s+)?operations?\b|\bfires?\s+(?:situation|update|near|threat\w*)\b|"
                    r"\bfall\s+of\s+ground\b|\b(?:employees|workers|miners|workforce)\s+(?:(?:go|went|are|were)\s+on\s+)?strike\b|"
                    r"\bstrike\s+action\b|\bstrike\s+by\s+(?:the\s+)?(?:[\w'\u2019]+\s+){0,3}(?:workers|workforce|employees|union\w*|miners)\b|\bheavy\s+(?:rains?|rainfall|snow\w*)\b|\btorrential\s+rain\w*|\b(?:tropical\s+storm|cyclone|"
                    r"hurricane|typhoon|landslide|mudslide|flash\s+flood\w*)\b|\bslip\s+(?:on|at)\s+(?:the\s+)?(?:heap\s+)?(?:leach\s+)?pad\b|"
                    r"\b(?:leach\s+pad|pit\s+wall|slope|tailings\s+dam)\s+(?:failure|slip|slide)\b")),
    ("offtake", _P(r"\boff-?take\b|\b(?:ore|concentrate)\s+(?:purchase\s+|sales?\s+)?agreement\b|\bsales\s+(?:and\s+purchase\s+)?agreement\s+"
                   r"(?:for|with)\b|\bsupply\s+(?:agreement|deal)\b")),
    ("shipment", _P(r"\bfirst\s+(?:[\w-]+\s+){0,2}?(?:sales?|shipments?|exports?)\b|\bshipments?\s+(?:have\s+|has\s+)?(?:commenced|begun|began|started)\b|"
                    r"\b(?:commenc|begin|began|start)\w*\s+(?:\w+\s+){0,2}?(?:shipments?|shipping|exports?|exporting)\b|\bshipment\s+of\s+(?:its\s+)?\d|\b(?:shipment|delivery)\s+of\s+(?:\w+\s+){0,3}(?:concentrates?|ore|lithium|dor[e\u00e9]|"
                    r"product|spodumene|cathode)\b|\b(?:second|third|fourth|fifth|\d+(?:st|nd|rd|th))\s+shipment\b|\bships?\s+(?:its\s+)?first\b|"
                    r"\bshipped\b(?=[^.;]{0,50}\b(?:concentrates?|ore|lithium|spodumene|cathodes?|dor[e\u00e9]|tonnes|wmt|dmt|cargo|vessel|port)\b)|"
                    r"\bloads?\s+[\d,]+\s*(?:tonne|t)\b|\brail\s+shipment\b")),
    ("contract", _P(r"\bEPCM?\b[^.]{0,40}\b(?:contract|agreement|contractor)\b|\bas\s+(?:the\s+)?EPCM?\b|\b(?:mining|construction|earthworks|"
                    r"underground)\s+(?:services\s+)?contract(?:or)?\b|\b(?:toll|custom)[\s-]?(?:milling|processing|treatment)\s+(?:agreement|contract)\b|"
                    r"\bcontract\s+mining\s+(?:agreement|contract|services)\b|\bpower\s+(?:purchase|"
                    r"supply)\s+agreement\b|\bcontracts?\s+(?:have\s+been\s+|has\s+been\s+|were\s+|was\s+)?awarded\b|\bawarded\s+(?:the\s+)?"
                    r"(?:\w+\s+){0,4}contract\b|\b(?:appoint|designat|select|retain|engag)\w*\s+(?:\w+\s+){0,5}?contractors?\b|"
                    r"(?-i:\b(?:[Cc]ontracts|[Rr]etains|[Ee]ngages)\s+(?:[A-Z][\w&.-]*\s+){1,4}(?:to|for)\b)|\bpurchase\s+orders?\b|"
                    r"\bplace[sd]?\s+(?:an?\s+)?orders?\s+for\b|\blong[\s-]lead\s+(?:items?\s+|equipment\s+)?(?:purchases?|orders?)\b")),
    ("infrastructure", _P(r"\bunderground\s+development\b|\braise\s+bore\b|\bventilation\s+(?:upgrade|raise|circuit|system)\b|\bshaft\s+(?:sinking|"
                          r"station|\d)\b|\bportal\b|\bdecline\b(?!\s+in\b)|\baccess\s+road\b|\btransmission\s+line\b|\bpower\s+line\b|"
                          r"\bsubstation\b|\btailings\s+(?:storage\s+)?facility\b|\bsolar\s+(?:farm|plant|power\s+plant|installation)\b")),
]
# 1.0.3: further commissioning wordings, appended to the 1.0.2 commissioning cue as further alternatives
_COMMISSIONING_MORE = (
    r"\bcommissioning\s+(?:campaign|(?:remains?\s+|is\s+)?(?:well\s+)?on\s+(?:track|schedule)|and\s+ramp[\s-]?up)\b|"
    r"\b(?:commenc|begin|began|start|complet|initiat)\w*\s+(?:the\s+)?(?:[\w-]+\s+){0,3}?(?:pre-)?commissioning\b|"
    r"\bupdate\s+(?:to|on)\s+(?:the\s+)?(?:[\w-]+\s+){0,3}?commissioning\b|"
    r"\b(?:is\s+)?commissioning\s+(?:the\s+|its\s+|a\s+|an\s+)?(?:[\w-]+\s+){0,4}?(?:plant|mill|circuit|concentrator|kiln|crusher)\b|"
    r"\b(?:commenc|begin|began|start)\w*\s+processing\s+(?:of\s+)?(?:[\w-]+\s+){0,2}?ore\b|"
    r"\b(?:plant|mill|circuit|concentrator|facility)\s+start[\s-]?up\b")
CUES = [(et, _P(rx.pattern + "|" + _COMMISSIONING_MORE) if et == "commissioning" else rx) for et, rx in CUES]
CUE = dict(CUES)
_GENERIC_HL = re.compile(r"(?i)\b(?:operations?|operational|operating|corporate|project|construction|development|mine|site|business|"
                         r"production)\s+(?:and\s+\w+\s+)?(?:update|outlook|review)\b|\bupdates?\s+on\s+(?:\w+\s+){0,4}(?:operations?|activities|"
                         r"projects?|mine|investments)\b|\b(?:quarter|Q[1-4]|year[\s-]end|annual|half[\s-]year)\b[^.;]{0,40}\bresults\b|"
                         r"\breview\s+of\s+(?:\w+\s+){0,2}(?:mine\s+)?(?:construction|operations|development)")
_STATUS_UPDATE_HL = re.compile(r"(?i)\b(?:operations?|operational|operating|mine|site)\s+update\b|\bupdate\s+on\s+(?:\w+\s+){0,3}operations\b")

# ------------------------------------------------------------------ what is not a mine event
_EXPLORATION = re.compile(r"(?i)\bdrill\w*\b|\bassays?\b|\bintercept\w*\b|\bintersect\w*\b|\bg/t\b|\bexploration\s+(?:program|"
                          r"activities|work|camp|season)\b|\bfield\s+(?:program|work|season|crew)|\bgeophysic\w*\b|\bsurvey\b|"
                          r"\bsampling\b|\bmapping\b|\bprospecting\b|\bchannel\s+samples?\b|\bresource\s+estimate\b")
_STUDY = re.compile(r"(?i)\b(?:feasibility|pre-feasibility|prefeasibility|PEA|PFS|DFS|scoping)\s+(?:study|work)\b|\btechnical\s+"
                    r"report\b|\bNI\s*43-101\b|\bmetallurgical\s+(?:test|results?|program)")
_PILOT = re.compile(r"(?i)\bpilot[\s-](?:scale|plant)\b|\bdemo(?:nstration)?\s+(?:plant|facility|facilities|module|circuit|scale)\b|\bpilot\s+(?:circuit|facility)\b|\btesting\s+lab\w*\b|\bprototype\b|"
                    r"\blab(?:oratory)?[\s-]scale\b|\btest\s+work\b|\bbench[\s-]scale\b|\b(?:production\s+)?test\s+(?:facility|plant)\b|\btrial\s+production\b|"
                    r"\bR&D\s+facilit\w+|\bresearch\s+(?:and\s+development\s+)?facilit\w+")
_NOT_OURS = re.compile(r"(?i)\bsecurities\s+commission\b|\btrading\s+halt\b|\bcease\s+trade\b|\bhalt\w*\s+(?:in\s+)?trading\b|"
                       r"\bsuspen\w+\s+(?:of\s+)?trading\b|\bmanagement\s+cease\b|\bcommissions?\s+(?:an?\s+|the\s+)?(?:\w+\s+){0,3}"
                       r"(?:report|study|survey|assessment|evaluation|review)\b|\bcommissioned\s+(?:an?\s+|the\s+)?(?:\w+\s+){0,3}(?:report|"
                       r"study|survey|assessment)\b|\bcommission\s+(?:fees?|paid|payable)\b")
_BACKGROUND = re.compile(r"(?i)\b(?:previously\s+(?:announced|disclosed|reported)|as\s+(?:previously\s+)?(?:announced|disclosed|reported)\s+"
                         r"(?:on|in)|(?:news\s+)?release\s+dated|since\s+(?:the\s+)?(?:achievement|declaration|start)\s+of|history\s+of|"
                         r"was\s+(?:built|constructed|commissioned)\s+in\s+(?:19|20)\d\d|operated\s+(?:from|until|between)\s+(?:19|20)\d\d|"
                         r"historically|formerly\s+(?:operated|produced))")
_DONATION = re.compile(r"(?i)\bdonat\w+\b|\bassistance\s+fund\b|\bcharit\w+\b|\bscholarship\b|\bsponsor\w*\b|\brelief\s+(?:efforts?|funds?)\b")
_APPOINT_HL = re.compile(r"(?i)\b(?:appoint\w*|promot\w*|names?|hires?|welcomes?|board\s+(?:changes?|appointment)|resign\w*|"
                         r"retire\w*)\b(?![^.]{0,40}\bcontractor\b)")
_FIN_HL = re.compile(r"(?i)\b(?:private\s+placement|financing|line\s+of\s+credit|credit\s+facility|loan|debentures?|bought\s+deal|"
                     r"offering|flow[\s-]through|warrants?|stock\s+options?)\b")
_ROYALTY_CO = re.compile(r"(?i)\b(?:royalt(?:y|ies)|streaming|stream(?:s)?)\b[^.]{0,40}\b(?:company|corp|inc|ltd|limited|plc)\b|"
                         r"\b(?:Franco-Nevada|Wheaton\s+Precious|Osisko\s+Gold\s+Royalties|OR\s+Royalties|Royal\s+Gold|Triple\s+Flag|"
                         r"Sandstorm|Metalla|Ecora|Elemental\s+Royalt|Gold\s+Royalty|Maverix|Vox\s+Royalty|Altius)\b")
_OIL_GAS = re.compile(r"(?i)\b(?:oil\s+(?:and|&)\s+gas|gas\s+well|oil\s+well|workover|natural\s+gas\s+(?:well|production)|barrels?\s+of\s+oil|"
                      r"petroleum\s+(?:licen[cs]e|well))\b")
_HOUSEKEEPING = re.compile(r"(?i)\bname\s+change\b|\bchanges?\s+(?:its\s+)?name\b|\bshare\s+consolidation\b|\bannual\s+(?:and\s+special\s+)?"
                           r"(?:general\s+)?meeting\b|\bAGM\b|\bvoting\s+results\b|\bnew\s+(?:ticker|trading\s+symbol)\b|\bnormal\s+course\s+issuer\s+bid\b")
# a release about exploration only: its lead has exploration words and no word of a mine or plant at work
_OPERATING = re.compile(r"(?i)\b(?:produc(?:ed|es|ing)|production\s+(?:of|was|increased|decreased|totall?ed|rates?|for\s+the\s+(?:quarter|month|year))|"
                        r"(?:gold|silver|copper|zinc|quarterly|record|total|monthly)\s+production|mining\s+rates?|stack\w*|leach\w*|mined|"
                        r"tonnes\s+(?:mined|processed|milled)|ounces\s+(?:sold|produced|poured)|mill(?:ed|ing)?|processing|process(?:ed)?\s+plant|plant|ore|tpd|tonnes\s+per\s+day|"
                        r"pour\w*|concentrate|dor[e\u00e9]|mining\s+operations?|underground\s+mine|open[\s-]pit\s+mine|commercial|construction\s+of\s+the\s+mine|"
                        r"heap\s+leach|smelter|refinery|shipments?|offtake|off-take|underground\s+development|mine\s+development|stop(?:e|es|ing)|"
                        r"pre-?construction|early\s+works|underground\s+activities)\b")
_QUOTE = re.compile(r"\u201c[^\u201d]{20,}\u201d|\"[^\"]{20,}\"")
_BAD_NAME = re.compile(r"(?i)\b(?:construction|progress|update|commissioning|production|development|expansion|restart|operations?|"
                       r"results?|return|high|record|achieves?|announces?|provides?|ramp-up|ramp|consistent|strong|solid)\b(?=.*\b(?:project|mine|property|mill|plant)\b)")
_LEAD_VERB = re.compile(r"(?i)^(?:pauses?|deliver|delivers|begins?|completes?|resumes?|restarts?|suspends?|announces?|reports?|provides?|commences?|"
                        r"starts?|achieves?|declares?|pours?|ships?|advances?|expands?|temporarily|successfully|to|at|the|of|for|and|on|from|"
                        r"accelerates?|initiates?|confirms?|enters?|signs?|receives?|approves?|updates?|halts?|stops?|re-?opens?|"
                        r"recommences?|ramps?|ramping|towards?|into|with|its|new|first|all|as|by|during|following|supports?|funds?|finances?)$")
_HL_DONE = re.compile(r"(?i)\b(?:complet(?:ed|es|ion\s+of)|finish(?:ed|es)|operational|meets|met|delivered|delivers|commissioned|newly\s+expanded|"
                      r"expanded\s+(?:mill|plant))\b")
_HL_TO_COME = re.compile(r"(?i)\b(?:to\s+be|will\s+be|expected\s+to\s+be|scheduled\s+to\s+be|targeted\s+to\s+be)\s+(?:complet|finish|"
                         r"commission|deliver|operational)\w*\b")
_HL_GOING = re.compile(r"(?i)\b(?:underway|under\s+way|progress\w*|advanc\w+|accelerat\w+|pushing\s+ahead|on\s+(?:track|schedule)|continu\w+|"
                       r"ramp\w*|initiat\w+|commenc\w+|begins?|began|start\w*|construction|development|proceeding|\d{1,3}\s?%\s+complete)\b")
_HL_DECIDE = re.compile(r"(?i)\b(?:announc\w*|approv\w*|decision|commit\w*|sanction\w*|go-ahead|launch\w*|increas\w+)\b")
_RESUMED_NOW = re.compile(r"(?i)\b(?:began|begun|commenced|resumed|restarted|recommenced)\b[^.;]{0,60}\btoday\b|\btoday\b[^.;]{0,60}\b(?:began|"
                          r"resumed|restarted|recommenced)\b|\b(?:has|have)\s+(?:now\s+|successfully\s+)?(?:resumed|restarted|recommenced)\b")
_NAME_VERB = re.compile(r"(?i)^(?:presents?|announces?|reports?|provides?|extends?|support|supports|places?|placing|drawdowns?|draws?|only|"
                        r"producing|future|existing|operating|updates?|receives?|completes?|begins?|commences?|achieves?|declares?)$")
_PERMIT_HL = re.compile(r"(?i)\bpermits?\b|\bright[\s-]of[\s-]way\b|\bapprovals?\b|\blicen[cs]es?\b|\bROD\b|\brecord\s+of\s+decision\b")

# 1.0.1 (2026-09-30): what makes a cue the release's own mine event (ACC150 and outside-tag samples, fix brief)
_PRODUCED_AT = re.compile(r"(?i)\b(?:produced|producing|produces|mined|processed|sourced)\s+(?:\w+\s+){0,6}?(?:at|from)\b")
_HAZARD_CUE = re.compile(r"(?i)wild\s*fire|forest\s+fire|bush\s*fire|\bfires?\s+(?:situation|update|near|threat)|earthquake|evacuat|"
                         r"heavy\s+(?:rain|snow)|rainfall|torrential|storm|cyclone|hurricane|typhoon|landslide|mudslide|flash\s+flood")
_HAZARD_EVAC = re.compile(r"(?i)(?<!\bnot\s)\bevacuat\w*\b(?!\s+(?:alert|notice|warning|watch|preparedness|plans?|routes?)\b)|\bdemobili[sz]\w*|"
                          r"\bclosure\s+order|\b(?:destroy\w*|burn(?:ed|t)\s+down)\b|\b(?:fatal\w*|injur\w*)\b")
_HAZARD_STOP = re.compile(r"(?i)\b(?:suspen\w+|halt\w*|paus\w+|stopped|shut\s*down|demobili[sz]\w*|closure\s+order|evacuation\s+order|ceased|"
                          r"curtail\w*)\b|\b(?:camps?|crews?|personnel|employees|workers|staff|team|site)\s+(?:\w+\s+){0,3}evacuated\b")
_HAZARD_HL_STOP = re.compile(r"(?i)\b(?:interrupt\w*|suspen\w+|halt\w*|shut\s*-?\s*down|stopp\w+|clos(?:ure|ed|es)|evacuat\w+)\s+(?:\w+\s+){0,5}?"
                             r"(?:due\s+to|because\s+of|caused\s+by|from|following|amid)\s+(?:the\s+)?(?:\w+\s+){0,2}"
                             r"(?:wild\s*fires?|forest\s+fires?|bush\s*fires?|fires?|earthquakes?)\b")
_HAZARD_NONE = re.compile(r"(?i)\bno\s+(?:\w+\s+){0,2}(?:damage|impact|fires?|effect)\b|\bnot\s+(?:\w+\s+){0,2}(?:affected|impacted|damaged)\b|"
                          r"\bunaffected\b")
_STUDY_LEAD = re.compile(r"(?i)\b(?:scoping|pre-?feasibility|feasibility|PEA|PFS|DFS)\s+(?:\w+\s+){0,2}?(?:study|studies|results?|outlines?|supports?)\b|"
                         r"\bpreliminary\s+economic\s+assessment\b|(?-i:\bFEED\b)|\bfront[\s-]end\s+engineering\b|\bcomplet\w+\s+(?:\w+\s+){0,4}design\b|"
                         r"\bdesign\s+work\b|\bstudy\s+(?:outlines?|results?|supports?|shows?|demonstrates?)\b")
_DECIDED = re.compile(r"(?i)\bcommit(?:s|ted|ment)\b|\bdecision\s+to\s+(?:proceed|build|construct|develop)\b|\bapprov\w+\s+(?:the\s+)?(?:development|"
                      r"construction|expansion)\b|\bsanction\w*\b|\b(?:investment|production|construction)\s+decision\s+(?:has\s+been|was)\s+"
                      r"(?:taken|made)\b|\b(?:construction|development|works?)\s+(?:\w+\s+){0,2}(?:(?:has|have)\s+(?:commenced|started|begun)|(?:is\s+|are\s+)?underway)\b|"
                      r"\b(?:commenced|started|began)\s+(?:full\s+)?construction\b")
_BUILD_NEWS = re.compile(r"(?i)\b(?:construction|works?|development|installation|procurement|commissioning|expansion|build)\b[^.;]{0,80}\b(?:underway|"
                         r"under\s+way|commenced|started|progress\w*|advanc\w+|complet\w+|ongoing|proceeding|on\s+(?:track|schedule))\b|"
                         r"\bprogress\s+(?:on|at|of|in)\s+(?:the\s+)?(?:[\w,-]+\s+){0,5}(?:construction|works|expansion|development|installation)\b|\b(?:commenced|started|began)\s+(?:\w+\s+){0,3}"
                         r"(?:construction|works|installation)\b")
_FIN_OBJECT = re.compile(r"(?i)\b(?:loan|draw\s*-?\s*downs?|drawdown|tranche|funding|financing|facilit(?:y|ies)|term\s+sheet|private\s+placement|"
                         r"bought\s+deal|debt|credit|debentures?|notes?\s+offering|offering)\b")
_PRODUCT = re.compile(r"(?i)\b(?:concentrates?|ore|dor[e\u00e9]|cathodes?|spodumene|hydroxide|carbonate|U3O8|uranium|yellowcake|pellets?|anode|"
                      r"mines?|mining\s+operations?|mill|plant|smelter|refinery|converter|produc(?:ed|es|ing|tion)|deposit|project)\b")
_EXPLO_STOP = re.compile(r"(?i)\b(?:paus|suspen|halt|stop|resum|restart|re-?start|recommenc)\w*\s+(?:\w+\s+){0,3}(?:exploration|drilling|field|"
                         r"prospecting|sampling|survey)")
_OPS_STOP = re.compile(r"(?i)\b(?:paus|suspen|halt|stop|resum|restart|re-?start|recommenc)\w*\s+(?:\w+\s+){0,3}(?:mining|production|processing|"
                       r"milling|mill|plant|mine)\b")
_RAMP_OBJECT = re.compile(r"(?i)\b(?:production|produc\w+|mill\w*|plant|throughput|output|mining|mine|operations?|concentrat\w*|processing|tpd|"
                          r"tonnes|nameplate|design|capacity|facility|circuit|underground|open[\s-]pit|stop(?:e|ing)|shaft|leach\w*|pour\w*|"
                          r"expansion|commercial|operational|(?:phase|stage)\s+(?:\d+|one|two|three|four|ii|iii|iv))\b")
_NOT_PRODUCTION_OBJECT = re.compile(r"(?i)[\s,:;-]*(?:(?:for|of|the|its|our|a|next|winter|summer|fall|spring|critical|minerals?|phase\s+\w+)\s+){0,4}"
                                    r"(?:drill\w*|explor\w*|programs?|programmes?|field\w*|surveys?|campaign|discovery)\b")
# 1.0.1 full-text fix (2026-10-01): kinds the full release text showed (lost rows)
_HL_FACT = re.compile(r"(?i)\b(?:achiev(?:es|ed)|exceed(?:s|ed)|surpass(?:es|ed)|complet(?:es|ed)|recently[\s-]completed|(?:far\s+)?ahead\s+of\s+"
                      r"schedule|advanc(?:es|ed)|under\s*way|pour(?:s|ed)|reach(?:es|ed|ing)|(?:has|have)\s+(?:begun|started|commenced))\b")
_HAZARD_STAND = re.compile(r"(?i)\b(?:reduc\w*|withdr[ae]w\w*|demobili[sz]\w*|sent\s+home|stood\s+down)\s+(?:the\s+)?(?:number\s+of\s+)?(?:[\w]+[\s-]+){0,2}?"
                           r"(?:staff|personnel|workers|employees|contractors|crews?|workforce)\b|\b(?:staff|personnel|workers|employees|"
                           r"contractors|crews?|workforce)\s+(?:\w+\s+){0,3}(?:withdrawn|reduced|demobili[sz]ed|sent\s+home|stood\s+down)\b")
_HAZARD_SITE_STOP = re.compile(r"(?i)\b(?:suspen\w+|halt\w*|paus\w+|stopp\w+|shut\s*down|curtail\w*)\s+(?:\w+\s+){0,3}?(?:underground|operations|"
                               r"mining|production|processing|milling|mill|plant|construction)\b|\b(?:operations|mining|production|processing|"
                               r"construction|underground\s+\w+)\s+(?:\w+\s+){0,5}?(?:have|has|were|was)\s+(?:been\s+)?(?:temporarily\s+)?"
                               r"(?:suspended|halted|paused|stopped|shut\s+down|curtailed)\b")
_HAZARD_DAMAGE = re.compile(r"(?i)\b(?:(?:was|were|been|is|are)\s+(?:\w+\s+){0,2}damaged|damaged\s+by|damage\s+(?:to|at)\s+(?:the\s+|our\s+|its\s+)?"
                            r"(?:\w+\s+){0,2}(?:site|property|camp|mine|equipment|infrastructure|plant|facilit\w+|assets?|buildings?)|assessment\s+"
                            r"of\s+(?:the\s+)?damage|swept\s+(?:\w+\s+){0,2}(?:through|over|across)|reached\s+(?:our|the|its)\s+(?:\w+\s+){0,2}"
                            r"(?:site|property|camp|mine))\b")
_OWN_PROJECTS = re.compile(r"(?i)\b(?:its|our)\s+(?:[\w'-]+\s+){0,3}?(?:projects?|mines?|deposits?)\b")
# 1.0.2 (2026-10-02): capture kinds from the ACC150b re-check (the page missed them)
_AS_PLANNED = re.compile(r"(?i)\b(?:as|according\s+to)\s+(?:planned|scheduled|expected|anticipated|forecast|plan|schedule)\b")
_COMPANION_STOP = re.compile(r"(?i)\b(?:operations|activities|mining|production|processing|milling|works?)\b(?:\s+(?!(?:if|may|could|would|not|no|never)\b)"
                             r"[\w,'\u2019-]+){0,5}?\s+(?:have|has|were|was|had|is|are)\s+(?:been\s+|now\s+)?(?:temporarily\s+|immediately\s+)?"
                             r"(?:suspended|halted|paused|stopped|shut\s+down|curtailed|ceased)\b|(?<!\bnot\s)(?<!\bno\s)\b(?:suspended|halted|paused|"
                             r"stopped|ceased|halting|stopping|pausing)\s+(?:all\s+)?(?:[\w-]+\s+){0,2}?(?:operations|activities|mining|production|processing|milling|work)\b|"
                             r"\b(?:is|are)\s+(?:now\s+)?(?:temporarily\s+)?(?:suspending|halting|pausing)\s+(?:all\s+)?(?:[\w-]+\s+){0,2}?(?:operations|activities|"
                             r"mining|production|processing|milling)\b")
_HEALTH_HL = re.compile(r"(?i)\b(?:covid|coronavirus|pandemic|outbreak|positive\s+(?:test|case)s?)\b")
_INCIDENT_CAUSE = re.compile(r"(?i)\b(?:due\s+to|as\s+a\s+result\s+of|following|after|caused\s+by|because\s+of)\s+(?:a|an|the)?\s*(?:[\w-]+\s+){0,3}?"
                             r"(?:fire|explosion|fatal\w*|accident|flood\w*|heavy\s+rains?|rainfall|storm|slip|collapse|fall\s+of\s+ground|landslide|"
                             r"mudslide|rockburst|seismic\s+event|strike|blockade|cyclone|hurricane)\b")
_RESTART_WORK = re.compile(r"(?i)\brestart(?:ing)?\s+(?:of\s+)?(?:the\s+)?(?:\w+\s+){0,3}?(?:mine|mill|plant|project|operations?|production)\b|"
                           r"\b(?:mine|mill|plant|project|operations?|production)\s+restart\b|\bback\s+(?:online|on[\s-]?line|into\s+(?:production|operation))\b|"
                           r"\b(?:resum|recommenc)\w+\s+(?:of\s+)?(?:\w+\s+)?(?:production|operations|mining)\b")
_RESOLVED = re.compile(r"(?i)\b(?:resolv\w*|end(?:s|ed|ing)?|settl\w*|conclud\w*|lift\w*|call(?:s|ed)?\s+off)\s+(?:the\s+|a\s+)?(?:\w+\s+){0,1}$")
_HL_INCIDENT_NEWS = re.compile(r"(?i)\bupdate\s+(?:\w+\s+)?(?:following|after)\s+(?:the\s+|a\s+)?(?:\w+\s+){0,2}$|\b(?:suspen\w+|halt\w*|"
                               r"paus\w+|stopp\w+|shut\s*down|disrupt\w*|interrupt\w*)\b[^;:|]{0,60}\b(?:due\s+to|following|after|caused\s+by)\s+"
                               r"(?:the\s+|a\s+)?(?:[\w-]+\s+){0,3}$")
_DECISION_TAKEN = re.compile(r"(?i)\b(?:confirm\w*|announc\w*|approv\w*|mak(?:es|ing)|made|reach\w*|tak(?:es|ing|en)|took|declar\w*)\s+"
                             r"(?:(?:the|a|an|its|formal|final|positive)\s+)*$")


_REGION_OPS = re.compile(r"^(?:(?:North|South|East|West|Central)\s+)?[A-Z][a-z]+(?:ian|ean|can|ese|ish)\s+(?:Operations?|Mines|Assets)$")


def _lower_suffix_name(t):
    """'... at its Rice Lake operations', '... at Tasiast mine': a name written before a lower-case mine word (1.0.2)."""
    for m in re.finditer(r"\b(?:at|its|the|of)\s+((?:[A-Z][\w\u00C0-\u00ff'-]*\s+){1,3}?)(mine|operations?|mill)\b", t):
        toks = [w for w in m.group(1).split()]
        while toks and (toks[0].lower() in _STOP_TOKENS or toks[0].lower() in _PLANT_WORDS or _LEAD_VERB.match(toks[0]) or
                        re.search(r"['\u2019]s$", toks[0])):
            toks = toks[1:]
        if toks and not any(re.search(r"['\u2019]s$|^(?:Company|Corporation|Inc|Ltd|Limited)$", w) for w in toks) and\
                not all(w.lower() in _GENERIC_NAME or w.lower() in _PLANT_WORDS for w in toks) and not _REGION_OPS.match(" ".join(toks) + " Operations"):
            return " ".join(toks) + " " + m.group(2)
    return None


def _split_mines(kept, h, sents, ann):
    """1.0.2: "First gold produced at both <A> and <B> projects": one row per named mine; a headline event at a region's
    operations whose announcement lists the mines ("the LaRonde Complex, the Goldex mine and the Canadian Malartic mine"): one row
    per listed mine."""
    out = []
    for c in kept:
        n = c["mine"] or ""
        parts = [p.strip() for p in re.split(r"\s+(?:and|&)\s+|,\s*", n) if p.strip()]
        if c["sent"] == 0 and len(parts) >= 2 and all(re.match(r"[A-Z]", p) and len(p) > 3 and not all(
                w.lower() in _GENERIC_NAME or w.lower() in _PLANT_WORDS for w in re.findall(r"[\w'-]+", p)) for p in parts):
            hh = h.title() if sum(ch.isupper() for ch in h) > 0.6 * max(1, sum(ch.isalpha() for ch in h)) else h
            for p in parts:
                mm = re.search(r"((?:[A-Z][\w'-]*\s+){0,2})" + re.escape(p), hh)
                pre = [w for w in (mm.group(1).split() if mm else []) if w.lower() not in _STOP_TOKENS and w.lower() not in ("both", "first",
                                                                                                                       "gold", "produced", "at")]
                out.append(dict(c, mine=" ".join(pre[-1:] + [p])))
            continue
        if c["sent"] == 0 and c["event_type"] in ("restart", "suspension", "care_maintenance", "closure") and\
                (not c["mine"] or _REGION_OPS.match(c["mine"]) or re.search(r"(?i)\boperations\s+in\s+[A-Z]", h)):
            names = []
            for t in sents[:ann + 3]:
                if not re.search(r"(?i)\bresum|\brestart|\bsuspen|\bhalt|\bcare\s+and|\bclos", t):
                    continue
                names = [m.group(1) + " " + m.group(2) for m in re.finditer(
                    r"(?:the\s+)?((?:[A-Z][\w\u00C0-\u00ff'-]*\s+){0,2}[A-Z][\w\u00C0-\u00ff'-]*)\s+(mine|Mine|Complex|complex|operation|Operation)\b", t)]
                names = [x for x in names if not _REGION_OPS.match(x) and not re.match(r"(?i)^(?:the|its|our|company)\b", x)]
                if len(names) >= 2:
                    break
            if len(names) >= 2:
                out += [dict(c, mine=x) for x in dict.fromkeys(names)]
                continue
        out.append(c)
    return out


def _companions(kept, h, sents, ann):
    """1.0.2: label rule (incident + suspension, as the key's fatality example): the lead says the headline's incident stopped
    operations -> a suspension row; a headline stop caused by an incident -> an incident row. Same mine, achieved."""
    out = []
    inc = next((c for c in kept if c["event_type"] == "incident"), None)
    sus = next((c for c in kept if c["event_type"] == "suspension"), None)
    if inc and not sus:
        for j, t in enumerate(sents[:16]):
            if _BACKGROUND.search(t) or _QUOTE.fullmatch(t.strip()):
                continue
            m = _COMPANION_STOP.search(t)
            if m and not re.search(r"(?i)\b(?:explor\w*|drill\w*|field|resum\w*|restart\w*|if|should|would|could|may)\b", t) and not\
                    re.search(r"(?i)\b(?:no|not|without|never)\b[^.;]{0,30}$", t[max(0, m.start() - 40):m.start()]):
                out.append(dict(inc, event_type="suspension", status="achieved", sent=j + 1, pos=m.start(), text=t, lo=m.start(), hi=m.end()))
                break
    if sus and not inc:
        for j, t in enumerate([h] + sents[:ann + 2]):
            m = _INCIDENT_CAUSE.search(t)
            if m and re.search(r"(?i)\b(?:power|electric\w*|grid|rail\w*|road|highway|port)\s+(?:supply\s+|line\s+|service\s+)?"
                                                             r"(?:interruption|outage|disruption|failure|closure)s?\b", t[max(0, m.start() - 60):m.end()]):
                m = None
            if m and not re.search(r"(?i)\b(?:no|not|without|avoid\w*|prevent\w*|risk|potential)\b[^.;]{0,30}$", t[max(0, m.start() - 40):m.start()]):
                out.append(dict(sus, event_type="incident", status="achieved", sent=j, pos=m.start(), text=t, lo=m.start(), hi=m.end(), support=[]))
                break
    return out


_COMPANION_TYPES = ("commissioning", "construction_start", "construction_progress", "infrastructure", "shipment", "contract")


def _body_companions(kept, body, sents, ann):
    """1.0.3: the other milestones the announcement states for the headline's mine (label rule: one row per event; the key's
    "first pour + commissioning + ramp-up" and "construction start + earthworks contract" releases). A body event is a row
    when it sits in the announcement or the three sentences after it, is a build, contract, shipment or restart milestone
    (not a stop, incident, deal or decision, which in the body are the headline's cause or history), is stated as done or
    under way (or planned with its own date), and is at the headline's mine (or names none)."""
    out = []
    hl_types = {c["event_type"] for c in kept}
    hl_mines = [c["mine"] for c in kept if c["mine"]]
    for c in body:
        et, t, lo = c["event_type"], c["text"], c["lo"]
        if et not in _COMPANION_TYPES or et in hl_types or c["sent"] > ann + 3:
            continue
        if et == "contract" and not hl_types & {"construction_start", "construction_decision", "construction_progress", "infrastructure"}:
            continue                                    # a contract goes with a build's start or progress (the earthworks contract)
        if any(o["event_type"] == et for o in out):
            continue
        if c["mine"] and hl_mines and not any(_same_mine(c["mine"], m) for m in hl_mines):
            continue                                    # another mine's event
        if c["status"] != "planned" and re.match(r"(?i)[^.;,]{0,50}?(?:\b(?:is|are|was|were|remains?)\s+)?(?:now\s+)?\b(?:forecast\w*|expected|"
                                                  r"scheduled|planned|targeted|set|slated|due)\s+to\b|[^.;,]{0,50}?\bwill\b", t[c["hi"]:]):
            continue                                    # 1.0.3: "commissioning is forecasted to commence": not under way yet
        if c["status"] == "planned" and (not _target_date(t[lo:lo + 120]) or "construction_progress" in hl_types):
            continue                                    # rule DG: a target inside a progress update is its next target
        if _QUOTE.search(t) or re.search(r"\b(?:[Ww]e|[Oo]ur)\b", t) or t[:lo].count("(") > t[:lo].count(")"):
            continue                                    # a comment or a bracketed aside
        if re.search(r"(?i)\b(?:existing|previous\w*|earlier|prior|since|history)\b", t[max(0, lo - 60):lo + 60]):
            continue
        out.append(dict(c, companion=True))
    return out


def _first_date(b):
    """The first full date in the release's opening (its dateline when the shared helper finds none), ISO, or None."""
    for d in T._DATE.finditer(b[:600]):
        iso = T._iso(d)
        if iso and re.match(r"^(?:19|20)\d\d-\d\d-\d\d$", iso):
            return iso
    return None


_FORECAST = re.compile(r"(?i)\b(?:targeted|targeting|expected|expects?|scheduled|anticipated|anticipates?|aims?\s+to|aiming\s+to|forecast\w*|"
                       r"slated|projected|planned\s+(?:for|to)|plans?\s+to|intends?\s+to|set\s+to|on\s+track\s+(?:to|for)|will|by\s+(?:the\s+)?end\s+of)\b")
_NOT_FORECAST = re.compile(r"(?i)\b(?:as|than)\s+(?:expected|anticipated|scheduled|planned|forecast)|\bahead\s+of\s+(?:schedule|plan)")
_DONE_AT = re.compile(r"(?i)\b(?:has|have|had)\s+(?:now\s+|successfully\s+|officially\s+)?(?:been\s+)?\w+(?:ed|en|un)\b|\b(?:was|were)\s+\w+ed\b|"
                      r"\b(?:achieved|completed|commenced|poured|declared|reached|delivered|shipped|began|begun|started|restarted|resumed)\b")


def _not_yet(s, lo, hi):
    """1.0.3: the event's own clause states it as a forecast or target ("initial shipment targeted by end of 2018",
    "is expected to restart", "has decided to place the mine on care and maintenance"), and says nothing that marks it done at
    the cue."""
    pre = re.split(r"[.;:|]|\s[-\u2013\u2014]\s|,\s+(?:and|while|but)\s", s[max(0, lo - 70):lo])[-1]
    post = re.split(r"[.;:|]|\s[-\u2013\u2014]\s|,\s+(?:and|while|but)\s", s[hi:hi + 80])[0]
    clause = pre + s[lo:hi] + post
    if _DONE_AT.search(s[max(0, lo - 25):hi + 20]):
        return False
    if _FORECAST.search(clause) and not _NOT_FORECAST.search(clause):
        return True
    if re.search(r"(?i)\b(?:decided|agreed|resolved|elected|intends?|plans?)\s+to\s+(?:\w+\s+){0,6}$", pre):
        return True
    return False


def _hl_fact(h, lo, hi):
    """The headline clause around a cue states the milestone as done or under way, and no study comes before the cue in that
    clause: the study the lead also mentions is a side item, not the subject (full-text fix, 2026-10-01)."""
    a = max([0] + [m.end() for m in re.finditer(r";|\s[-\u2013\u2014]\s|\|", h[:lo])])
    z = min([len(h)] + [hi + m.start() for m in re.finditer(r";|\s[-\u2013\u2014]\s|\|", h[hi:])])
    if _STUDY_LEAD.search(h[a:lo]) or _STUDY.search(h[a:lo]):
        return False
    return bool(_HL_FACT.search(h[max(a, lo - 60):min(z, hi + 60)]))


def _hazard_at_site(text):
    """Staff stood down, operations stopped or damage at the site (not negated): a natural hazard that hit the company."""
    if _HAZARD_STAND.search(text) or _HAZARD_SITE_STOP.search(text):
        return True
    return any(not re.search(r"(?i)\b(?:no|not|any|without|avoid\w*|prevent\w*)\b[^.;]{0,25}$", text[max(0, m.start() - 30):m.start()])
               for m in _HAZARD_DAMAGE.finditer(text))


def _own_name(issuer):
    """A regex for the issuer's own short name ("First Spodumene Minerals Corp." -> "First Spodumene"), or None when it is generic."""
    ws = re.findall(r"[A-Za-z][\w'&-]*", issuer or "")
    while ws and ws[-1].lower() in ("inc", "corp", "corporation", "ltd", "limited", "plc", "co", "company", "resources", "minerals", "metals",
                                    "mining", "mines", "ventures", "group", "holdings", "sa", "ag", "llc"):
        ws = ws[:-1]
    if not ws or (len(ws) == 1 and (len(ws[0]) < 5 or ws[0].lower() in _GENERIC_NAME or ws[0].lower() in _PLANT_WORDS)):
        return None
    return re.compile(r"(?i)\b" + r"\s+".join(re.escape(w) for w in ws) + r"\b")


def _company_like(name, b):
    """'XYZ Mine' when the text only ever writes 'XYZ Mine Repair and Maintenance': a contractor's name, not a mine (1.0.1)."""
    occ = [m.end() for m in re.finditer(re.escape(name), b)]
    return bool(occ) and all(re.match(r"\s+(?!(?:Project|Mine|Property|Complex|Operations?|Expansion|Phase|Stage|Plant|Mill|In|On|At|And|The|"
                                       r"For|To|Of|With|Is|Was|Has)\b)[A-Z][a-z]+", b[e:e + 30]) for e in occ)


def _is_own_event(et, s, lo, hi, cue, is_hl, projects=()):
    """False when the cue names exploration, land, a study or a product that is not the company's mine event (1.0.1)."""
    after, before = s[hi:hi + 60], s[max(0, lo - 60):lo]
    named_ramp = any(_core_in(q, " ".join(before.split()[-2:])) for q in projects)   # "Accelerates <Mine> Ramp-Up"
    ma = re.match(r"(?i)\s+of\s+(?:the\s+)?([^;,.]{3,40}?)\s*(?:[;,.]|$|\s(?:and|to|in|is|was|continu\w*|progress\w*)\b)", after)
    if ma and not named_ramp:                           # "ramp-up of <Mine>": the release's project and nothing else is the object
        g = [w.lower() for w in re.findall(r"[\w\u00C0-\u00ff'-]+", ma.group(1))]
        named_ramp = any(_core_in(q, ma.group(1)) and all(w in [x.lower() for x in re.findall(r"[\w\u00C0-\u00ff'-]+", q)] or w in (
            "mine", "project", "operation", "operations", "complex") for w in g) for q in projects)
    if et == "ramp_up" and re.search(r"(?i)ramp", cue) and (not (_RAMP_OBJECT.search(s[max(0, lo - 60):hi + 60]) or named_ramp) or
                                                          _NOT_PRODUCTION_OBJECT.match(after) or
                                                          re.search(r"(?i)\b(?:drill\w*|explor\w*|programs?|programmes?|field\w*)\s+$", before)):
        return False                                    # "Ramps Up Drilling", "Ramps Up Phase 2 Program", "for EV ramp up"
    if et == "expansion":
        if re.search(r"(?i)\b(?:hectares?|ha|acres?|km2|square|land|claims?|deposit|resource|mineraliz\w+|zone|target|strike)\s+$", before):
            return False                                # "9,055 Hectare Expansion", "Deposit Expansion Program"
        if re.match(r"(?i)[\s,]*(?:[\w'\u2019.&-]+\s+){0,4}?(?:propert(?:y|ies)|belts?\b|district|claims?|land|package|holdings?|surveys?|"
                    r"strategy|trend|footprint|portfolio)", after) and re.search(r"(?i)\bof\s+the\s*$", cue):
            return False                                # "Expansion of the X Property by Option", "... of the Surface EM Survey"
        if re.search(r"(?i)\bof\s+the\s*$", cue) and re.match(r"(?i)[\s,]*(?:[\w'\u2019.&-]+\s+){0,4}?project\b", after) and not re.search(
                r"(?i)\b(?:mill|plant|throughput|capacity|tpd|mtpa|production|underground|pit|processing|operations?|mine|shaft|wellfield)\b",
                s[max(0, lo - 80):hi + 80]):
            return False                                # "Expansion of the X Uranium Project" with nothing operating
        if re.search(r"(?i)\bprogram", cue + after[:12]) and re.search(r"(?i)\b(?:drill\w*|metres?|meters?|holes?|m\b)", s[max(0, lo - 60):hi + 60]):
            return False                                # "3,200-Metre Phase Four Expansion Program"
    if et in BUILD + ("restart",) and re.match(r"(?i)[\s:,-]*(?:[\w-]+\s+){0,2}?(?:design\b(?!\s+(?:capacity|throughput|rate))|stud(?:y|ies)\b|"
                                               r"(?-i:FEED)\b|preliminary\s+economic|PEA\b|PFS\b|scoping\b|feasibility\b|technical\s+report)", after):
        return False                                    # "Tailings Storage Facility Design", "X Mine Restart Preliminary Economic Assessment"
    if et in BUILD + ("restart",) and is_hl and re.search(r"(?i)\b(?:(?-i:FEED)|front[\s-]end\s+engineering|scoping|PEA|PFS|pre-?feasibility|"
                                                          r"feasibility|studies|study)\b[^.;]{0,40}$", before):
        return False                                    # "Commenced FEED on the X Sulphide Project", "PEA Supports Mine Expansion Plan"
    if et in BUILD and re.search(r"(?i)\b(?:approv\w*|permits?|licen[cs]es?|EIA|authori[sz]\w+|consent)\b[^.;]{0,60}\bfor\b[^.;]{0,60}$",
                                 s[max(0, lo - 120):lo])\
            and not re.match(r"(?i)construction\s+(?:has\s+|have\s+)?(?:officially\s+)?(?:commenced|started|began|begun)\b", cue):
        return False                                    # "Receives Approval of its EIA for the Construction ... of the Substation": a permit
    if is_hl and et in BUILD + ("restart",) and re.search(r"(?i)\b(?:appeal\w*|court|judicial|petition\w*|lawsuit|litigation|"
                                                                        r"injunction)\b", s[:lo]):
        return False                                    # a court matter about the facility
    if et in ("infrastructure", "construction_start", "construction_progress") and (
            re.search(r"(?i)\b(?:explor\w*|drill\w*)\s+(?:\w+\s+)?$", before) or
            re.match(r"(?i)[^.;]{0,30}\b(?:(?:drill|exploration)\s+(?:roads?|pads?|camps?|trails?)|field\s+camps?)\b", s[lo:hi + 40])):
        return False                                    # "Exploration Decline", "Construction of Drill Roads and Field Camp"
    if et == "construction_progress" and re.search(r"%", cue) and re.search(r"(?i)\b(?:survey|drill\w*|program\w*|stud(?:y|ies)|sampling|"
                                                                          r"explor\w*|assay\w*)\b[^.;]{0,30}$", before):
        return False                                    # "Magnetic Drone Survey over 90% completed"
    if et == "offtake":
        if re.search(r"(?i)\bforward\s+(?:\w+\s+)?$", before) or re.search(r"(?i)\bforward\s+sales?\b", cue):
            return False                                # a forward sale is a financing
        if re.search(r"(?i)\bsales?\s+agreement", cue) and re.match(r"(?i)[^.;]{0,70}\b(?:propert(?:y|ies)|claims?|shares|interest|assets?|subsidiary)\b",
                                                                      after):
            return False                                # the sale of a property, not of product
    if et == "expansion" and re.search(r"(?i)capital", cue) and re.search(r"(?i)\bsustaining\s+capital|\bAISC\b|all-in\s+sustaining|"
                                                                        r"closure\s+costs?", s[max(0, lo - 150):hi + 60]):
        return False                                    # a cost category ("sustaining capital, expansion capital, and closure costs")
    if et == "suspension" and re.search(r"(?i)\b(?:planned|annual|scheduled|routine)\s+(?:\w+\s+){0,2}maintenance\b|\bmaintenance\s+(?:shut\s*-?\s*down|"
                                        r"stoppage)", s[max(0, lo - 60):hi + 60]):
        return False                                    # a planned maintenance shutdown is routine
    if et in BUILD and re.search(r"(?i)\b(?:flow\s+)?batter(?:y|ies)\s+(?:energy\s+)?(?:system|storage)|\benergy\s+storage\b",
                                                         s[lo:hi + 60]):
        return False                                    # 1.0.3: a battery or energy-storage system commissioned is not a mine or plant event
    if et in ("offtake", "contract") and is_hl and re.search(r"(?i)\bclarif\w+\s+(?:on|of|regarding|to)?\s*(?:the\s+|its\s+)?"
                                                                                    r"(?:[\w-]+\s+){0,3}$", s[max(0, lo - 60):lo]):
        return False                                    # 1.0.3: a clarification about an existing agreement is not a new one
    if et == "incident" and re.search(r"(?i)\b(?:compensat\w+|reimburs\w+|insurance|affected\s+by|"
                                                                    r"lawsuit|claims?\s+(?:for|from|related))\b[^.;]{0,60}$", s[max(0, lo - 80):lo]):
        return False                                    # 1.0.3: compensation for an earlier incident is not the incident's news
    if et == "incident" and re.search(r"(?i)\b(?:power|electric\w*|grid|rail\w*|road|highway|port)\s+"
                                                                    r"(?:supply\s+|line\s+|service\s+)?(?:interruption|outage|disruption|failure|closure)s?\s+"
                                                                    r"(?:\w+\s+){0,2}(?:caused\s+by|due\s+to|from|following)\s+(?:the\s+)?(?:[\w-]+\s+){0,2}$",
                                                                    s[max(0, lo - 90):lo]):
        return False                                    # 1.0.3: a hazard that cut a third party's power or rail is not an incident at the site
    if et == "ramp_up" and re.search(r"(?i)\b(?:deposit|property|prospect|claims?|zone|target)\s+$", s[max(0, lo - 25):lo]):
        return False                                    # 1.0.3: a deposit's or property's "ramp-up activities" are not a mine ramp-up
    if et == "contract" and re.search(r"(?i)\b(?:site\s+access|access\s+road|camp|drill\w*|exploration|geotech\w*)\b",
                                                                  s[max(0, lo - 40):hi + 40]):
        return False                                    # 1.0.3: a site-access, camp or drilling contractor is not a mine build contract
    if et in ("restart", "expansion", "construction_start") and re.search(r"(?i)\b(?:evaluat\w+|assess\w*|consider\w*|review\w*|explor(?:e|es|ing)|"
                                                                              r"stud(?:y|ies|ying))\s+(?:(?:of|the|a|an|its|potential|possible)\s+)*"
                                                                              r"(?:[\w-]+\s+){0,3}$", s[max(0, lo - 60):lo]):
        return False                                    # 1.0.3 (rule DV): "to evaluate restart of production" is vague intent
    if et == "contract" and re.match(r"(?i)[^.;]{0,60}\b(?:stud(?:y|ies)|feasibility|PEA|assessment|audit|technical\s+report)\b", s[lo:hi + 60]):
        return False                                    # a consultant engaged for a study
    if et == "site_cleanup" and re.search(r"(?i)\b(?:suspen\w+|seismic\w*|flood\w*|collapse|incident|damage\w*|repair\w*|accident)\b",
                                          s[max(0, lo - 150):hi + 150]):
        return False                                    # remediation after an incident is repair, not early legacy cleanup
    return True

# ------------------------------------------------------------------ status
_PLANNED = re.compile(r"(?i)\b(?:expect\w*|anticipat\w*|plan(?:s|ned|ning)?\s+to|will(?!\s+be\s+(?:complete|completed)\b)|would|targets?\s+(?:to|for)|"
                      r"targeted|scheduled|intends?\s+to|forecast\w*|on\s+track\s+(?:to|for)|is\s+set\s+to|aims?\s+to|slated|upcoming|"
                      r"subject\s+to|to\s+(?:begin|commence|start|restart|resume|deliver|pour|achieve|reach|produce|declare)\b|proposed|potential|could|may|should|guidance|next\s+stage|in\s+advance\s+of|soon|to\s+be\s+\w+ed|future|longer[\s-]term|on\s+(?:schedule|track|budget)\s+(?:to|for)|fully\s+funded\s+to)\b")
_UNDERWAY = re.compile(r"(?i)\b(?:underway|under\s+way|ongoing|continu\w+|in\s+progress|progressing|advancing|advances|ramping|" + "headway|" + r"is\s+being|are\s+"
                       r"being|accelerat\w+|remains?\s+on\s+(?:track|schedule|budget)|is\s+(?:approximately\s+|now\s+|over\s+)?\d{1,3}(?:\.\d)?\s?%)\b")
_ACHIEVED = re.compile(r"(?i)\b(?:has|have|had)\s+(?:now\s+|successfully\s+|officially\s+)?(?:been\s+)?\w+(?:ed|en|un)\b|\b(?:achiev|complet|declar|"
                       r"commenc|pour|sign|award|execut|resum|restart|suspend|plac|receiv|approv|select|appoint|ship|deliver|load|report|"
                       r"announc|start|reach|enter|conclud|finaliz|finalis)(?:ed|es|s)\b|\bbegan\b|\bbegun\b|\bbroke\b|\bbreaks\b|\bbegins\b|"
                       r"\bstarts\b|\bcommences\b|\bpours\b|\bachieves\b|\bdeclares\b|\breports\b|\bsigns\b|\bplaces\b|\bis\s+now\b|"
                       r"\bwas\s+\w+ed\b|\bwere\s+\w+ed\b")

# ------------------------------------------------------------------ dates
_MON = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_Q = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}
_TARGET = re.compile(r"(?i)\b(?:(Q[1-4])\s*[-/,]?\s*((?:19|20)\d\d)|((?:19|20)\d\d)\s*[-/]?\s*(Q[1-4])|(first|second|third|fourth|1st|2nd|3rd|4th)"
                     r"\s+quarter\s+(?:of\s+)?(?:(?:calendar|fiscal)\s+(?:year\s+)?)?((?:19|20)\d\d)|(H[12])\s*[-/]?\s*((?:19|20)\d\d)|"
                     r"(first|second)\s+half\s+(?:of\s+)?((?:19|20)\d\d)|(?:the\s+)?end\s+of\s+((?:19|20)\d\d)|(mid)[\s-]((?:19|20)\d\d)|"
                     r"(early|late)[\s-]((?:19|20)\d\d)|(" + _MON + r")\.?\s+((?:19|20)\d\d)\b|(?:in|during|by)\s+((?:19|20)\d\d)\b)")
_ASAT = re.compile(r"(?i)\b(?:as\s+(?:at|of)|at|to|ended|ending|through)\s+(?:the\s+end\s+of\s+)?(" + T._DATE_RX + r"|" + _MON +
                   r"\.?\s+(?:19|20)\d\d|(?:the\s+)?end\s+of\s+(?:Q[1-4]|(?:first|second|third|fourth)\s+quarter)\s+(?:of\s+)?(?:19|20)\d\d)")
_ON_DATE = re.compile(r"(?i)\b(?:on|effective(?:\s+as\s+of)?|dated|as\s+of|since|from|afternoon\s+of|morning\s+of|evening\s+of)\s+(" +
                      T._DATE_RX + r")")


def _target_date(s):
    """The first target date in s: 2027-Q2, 2022-H2, 2028-Q4 (end of), 2026-06, 2026."""
    m = _TARGET.search(s)
    if not m:
        return None
    g = m.groups()
    if g[0]:
        return "%s-%s" % (g[1], g[0].upper())
    if g[2]:
        return "%s-%s" % (g[2], g[3].upper())
    if g[4]:
        return "%s-Q%d" % (g[5], _Q[g[4].lower()])
    if g[6]:
        return "%s-%s" % (g[7], g[6].upper())
    if g[8]:
        return "%s-H%d" % (g[9], 1 if g[8].lower() == "first" else 2)
    if g[10]:
        return "%s-Q4" % g[10]
    if g[11]:
        return g[12]
    if g[13]:
        return "%s-%s" % (g[14], "H1" if g[13].lower() == "early" else "H2")
    if g[15]:
        return "%s-%02d" % (g[16], _MONTHS[g[15][:3].lower()])
    if g[17]:
        return g[17]
    return None


def _asat(s):
    m = _ASAT.search(s)
    if not m:
        return None
    t = m.group(1)
    d = T._DATE.search(t)
    if d:
        return T._iso(d)
    mm = re.match(r"(?i)(" + _MON + r")\.?\s+((?:19|20)\d\d)", t)
    if mm:
        return "%s-%02d" % (mm.group(2), _MONTHS[mm.group(1)[:3].lower()])
    q = re.search(r"(?i)(Q[1-4]|first|second|third|fourth)\s+(?:quarter\s+)?(?:of\s+)?((?:19|20)\d\d)", t)
    if q:
        qq = q.group(1)
        return "%s-Q%d" % (q.group(2), int(qq[1]) if qq.upper().startswith("Q") else _Q[qq.lower()])
    return None


def _on_date(s, lo=None, hi=None):
    ms = [m for m in _ON_DATE.finditer(s)]
    if lo is not None:
        after = [m for m in ms if (hi or lo) <= m.start() <= (hi or lo) + 90]
        before = [m for m in ms if lo - 120 <= m.start() < lo and not re.search(r"(?i)\band\b", s[m.end():lo])]
        ms = after[:1] or before[-1:]
    for m in ms:
        return T._iso(T._DATE.search(m.group(1)))
    return None


# ------------------------------------------------------------------ money and figures
_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_MULT = {"million": 1e6, "m": 1e6, "mm": 1e6, "mln": 1e6, "billion": 1e9, "b": 1e9, "bn": 1e9, "thousand": 1e3, "k": 1e3}
_MONEY = re.compile(r"(?<![\w.$])(?:(US|C|CA|CAD|CDN|USD|A|AU|AUD)\s?)?\$\s?" + _NUM + r"(?:\s*(million|billion|mln|bn|mm|m|b|k)\b)?"
                    r"(?:\s*(?:to|-|\u2013)\s*(?:(?:US|C|CA)?\s?\$\s?)?" + _NUM + r"(?:\s*(million|billion|mln|bn|mm|m|b)\b)?)?")
_CAPEX = re.compile(r"(?i)\b(?:initial|total|growth|upfront|up-front|construction|project|pre-production|preproduction|expansion|restart|"
                    r"development|direct)?\s*(?:(?:and\s+)?(?:sustaining\s+)?(?:capital\s+budget|capital\s+costs?|capital\s+expenditures?|"
                    r"capital\s+estimate|construction\s+budget|project\s+budget|capex|capital|total\s+spend(?:ing)?\s+to\s+date|"
                    r"spend(?:ing)?\s+to\s+date))\b")
_PCT = re.compile(r"(?i)(?:\b(?:overall|project|construction|physical|restart|total)\s+(?:\w+\s+){0,3}?(?:progress|completion|construction)?\s*"
                  r"(?:is|was|of|at|reached|stands\s+at|to)?\s*(?:now\s+)?(?:approximately\s+|about\s+|over\s+|more\s+than\s+|nearly\s+|~)?"
                  r"(\d{1,3}(?:\.\d)?)\s?%|(\d{1,3}(?:\.\d)?)\s?%\s+(?:complete|completed|physical\s+completion|completion))")
_SUB_AREA = re.compile(r"(?i)\b(?:engineering|procurement|earthworks|detailed\s+engineering|crushing|installation|refurbishment|"
                       r"camp|road|mill\s+building|plant\s+refurbishment|early\s+works)\b")


def _money(s):
    """[(start, end, value, high or None, currency or None)]"""
    out = []
    for m in _MONEY.finditer(s):
        cur, num, mult, num2, mult2 = m.groups()
        try:
            v = float(num.replace(",", ""))
            v2 = float(num2.replace(",", "")) if num2 else None
        except ValueError:
            continue
        mult = mult or mult2
        k = _MULT.get((mult or "").lower(), 1)
        tail = s[m.end():m.end() + 25].lower()
        if re.match(r"\s*(?:per|/)\s*(?:share|unit|ounce|oz|tonne|t\b|lb|pound)", tail):
            continue
        out.append((m.start(), m.end(), round(v * k, 2), round(v2 * k, 2) if v2 else None, _curr(cur)))
    return out


def _curr(tag):
    t = (tag or "").upper()
    return {"US": "USD", "USD": "USD", "C": "CAD", "CA": "CAD", "CAD": "CAD", "CDN": "CAD", "A": "AUD", "AU": "AUD",
            "AUD": "AUD"}.get(t)


def _declared_currency(b):
    t = b[:4000]
    if re.search(r"(?i)\ball\s+(?:dollar\s+)?(?:\(\$\)\s+)?(?:amounts|figures|references)[^.]{0,80}\b(?:US|U\.S\.|United\s+States)\s+dollars|"
                 r"\b(?:expressed|stated|presented|reported)\s+in\s+(?:US|U\.S\.|United\s+States)\s+dollars|"
                 r"\bunless\s+otherwise\s+(?:noted|stated|indicated)[^.]{0,60}\b(?:US|U\.S\.|United\s+States)\s+dollars", t):
        return "USD"
    if re.search(r"(?i)\ball\s+(?:dollar\s+)?(?:amounts|figures|references)[^.]{0,80}\bCanadian\s+dollars|\b(?:expressed|stated)\s+in\s+"
                 r"Canadian\s+dollars", t):
        return "CAD"
    return None


def _capex(sents, declared):
    """The project's capital figure: {'value', 'value_high', 'currency', 'basis'} or None."""
    best = None
    for n, s in enumerate(sents):
        around = " ".join(sents[max(0, n - 1):n + 2])
        if re.search(r"(?i)\bsustaining\s+capital\s+over\s+the\s+(?:life\s+of\s+mine|mine\s+life)|\bafter-tax\s+NPV|\bIRR\s+of|"
                     r"\b(?:PEA|PFS|feasibility\s+study)\s+(?:estimates?|outlines?)", around) and not re.search(r"(?i)\bconstruction\b", s):
            continue                                        # a study's summary, not the build's budget
        if len(_MONEY.findall(s)) > 5:
            continue                                        # a table flattened into a line
        for cm in _CAPEX.finditer(s):
            if re.search(r"(?i)\b(?:working|operating|share|equity|venture|human|debt|growth\s+and\s+sustaining)\s*$", s[max(0, cm.start() - 12):cm.start() + 1])\
                    or re.match(r"(?i)\s*(?:markets?|gains?|resources|structure|allocation|return|raise|raising)\b", s[cm.end():cm.end() + 12]):
                continue
            for x, y, v, v2, cur in _money(s):
                if v < 1e6:
                    continue
                gap = x - cm.end() if x >= cm.end() else cm.start() - y
                if gap > 90 or gap < -2:
                    continue
                between = s[min(cm.end(), y):max(cm.start(), x)]
                if re.search(r"(?i)\b(?:NPV|IRR|revenue|cash\s+flow|market\s+cap|financing|loan|facility|placement|royalt|stream|"
                             r"sustaining\s+capital\s+of|after-tax|funding|liquidity|cash|compared|per\s+share|income|earnings)\b", between) or\
                        re.search(r"(?i)\b(?:liquidity|funding\s+sources|cash\s+(?:and|flow|provided)|net\s+income|per\s+share)\b",
                                  s[max(0, x - 60):x]):
                    continue
                ctx = s[max(0, x - 80):y + 60].lower()
                if re.search(r"(?i)\boffset\s+by\s*$|\brevenue\b", s[max(0, x - 30):x]) or re.match(r"(?i)\s*(?:of\s+)?(?:pre-production\s+)?revenue", s[y:y + 30]):
                    continue
                basis = "budget"
                if re.match(r"(?i)\s*,?\s*(?:representing|or|being)\s+(?:approximately\s+)?\d{1,3}\s?%\s+of", s[y:y + 40]):
                    continue                                # a part of the budget: "US$54 million, representing 60% of the capital costs"
                if re.search(r"(?i)\bremaining\b[^.$]{0,40}$", s[max(0, cm.start() - 45):cm.start() + 1]) and x > cm.start():
                    continue                                # "remaining capital expenditures of $450 to $470 million"
                part = re.match(r"(?i)\s*(?:of|out\s+of)\s+(?:the\s+|its\s+)?(?:[\w'\u2019]+\s+){0,3}(?:(?:US|C|CA)?\$\s?[\d.,]+\s*(?:million|billion)\s+)?"
                                r"(?:initial\s+|guided\s+|total\s+)*(?:capital\s+)?(?:budget|capex|capital)", s[y:y + 70])
                direct = x >= cm.end() and re.match(r"(?i)\s*(?:of|is|was|at|totall?ing|remains\s+at|estimated\s+at|:)?\s*(?:approximately\s+|"
                                                    r"about\s+|~)?$", s[cm.end():x])
                spentish = re.search(r"\b(?:spent|incurred|to\s+date|expended|invested)\b", ctx) and not re.search(r"\bto\s+be\s+(?:spent|incurred|invested)\b", ctx)
                if re.search(r"(?i)\bspend(?:ing)?\s+to\s+date\b", s[cm.start():cm.end()]):
                    basis = "spent"
                elif part:
                    basis = "committed" if re.search(r"\bcommitted\b", s.lower()) and not re.search(r"\bspent\b", s.lower()) else "spent"
                elif direct and not re.search(r"(?i)\b(?:spent|incurred)\b", s[max(0, x - 20):x]):
                    basis = "budget"
                elif spentish and not re.search(r"\bbudget\s+of\b", s[max(0, x - 25):x].lower()):
                    basis = "spent"
                elif re.search(r"\bcommitted\b", ctx):
                    basis = "committed"
                if re.search(r"(?i)\bsustaining\b", s[max(0, cm.start() - 20):cm.end()]) and not re.search(r"(?i)initial", s[max(0, cm.start() - 30):cm.end()]):
                    continue
                rank = (0 if basis == "budget" else 1, n, gap)
                cand = (rank, {"value": v, "value_high": v2, "currency": cur or declared, "basis": basis})
                if best is None or cand[0] < best[0]:
                    best = cand
    return best[1] if best else None


def _pct(sents):
    overall, sub, strong = None, None, None
    for s in sents:
        for m in _PCT.finditer(s):
            v = float(m.group(1) or m.group(2))
            if not (1 <= v <= 100):
                continue
            pre = s[max(0, m.start() - 60):m.start() + 20]
            if re.search(r"(?i)\b(?:recover\w*|grade|interest|stake|owned|ownership|royalt\w*|increase|decrease|higher|lower|"
                         r"of\s+(?:the\s+)?(?:budget|capital)|IRR|margin|contingency|financ\w+|funded|drawn|placed|bonds?|"
                         r"nameplate|design\s+capacity|capacity|throughput|availability|utili[sz]ation|attributable|includes)\b",
                         s[max(0, m.start() - 45):m.end() + 25]) or re.search(r"(?i)\bstud(?:y|ies)\b[^.]{0,15}$", s[max(0, m.start() - 30):m.start()]):
                continue
            if m.group(2) and not re.search(r"(?i)\b(?:construction|project|overall|build|works|development|restart|refurbishment|"
                                            r"rebuild|expansion|installation|plant|mill|facility|mine|phase|engineering|procurement)\b", s[max(0, m.start() - 60):m.start()]):
                continue                                # a bare "N% complete" needs its subject
            if re.search(r"(?i)\b(?:tailings|TSF|liners?|pads?|conveyor|substation|power\s+line|pipeline|camp|road|airstrip|"
                         r"design|drilling|stud(?:y|ies))\b", s[max(0, m.start() - 40):m.start()]) and\
                    not re.search(r"(?i)\boverall\b", s[max(0, m.start() - 60):m.start()]):
                sub = sub if sub is not None else v
                continue
            if strong is None and re.search(r"(?i)\boverall\b|\btotal\s+project\b", s[max(0, m.start() - 100):m.end()]) and\
                    not re.search(r"(?i)\b(?:engineering|procurement|EPCM?|contract\s+works)\b", s[max(0, m.start() - 40):m.end()]):
                strong = v
            if _SUB_AREA.search(pre) and not re.search(r"(?i)\boverall\b|\bproject\b|\btotal\b", pre):
                sub = sub if sub is not None else v
                continue
            if re.search(r"(?i)\b(?:surface|underground|mine\s+development|plant|mill)\s+(?:construction\s+)?(?:progress|construction)\b",
                         s[max(0, m.start() - 60):m.start()]) and not re.search(r"(?i)\boverall\b", s[max(0, m.start() - 60):m.start()]):
                sub = sub if sub is not None else v
                continue
            if overall is None:
                overall = v
    return strong if strong is not None else overall if overall is not None else sub


_FIG_OZ = re.compile(r"(?i)(?:poured|produced|produces|production\s+(?:of|was)|pour\s+of|totall?ing|recovered|upwards\s+of|to)\s+(?:approximately\s+|over\s+|more\s+than\s+)?"
                     r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(ounces|oz)\b(?:\s+of\s+(gold|silver))?|(\d{1,3}(?:,\d{3})+|\d+)\s*(ounces|oz)\s+"
                     r"(?:of\s+)?(gold|silver)?\s*(?:were\s+|was\s+)?(?:poured|produced|recovered)")
_FIG_TPD = re.compile(r"(?i)(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*\+?\s*(?:tpd|tonnes\s+per\s+day|t/d|tons\s+per\s+day)\b")
_FIG_NAMEPLATE = re.compile(r"(?i)(\d{1,3}(?:\.\d)?)\s?%\s+of\s+(?:its\s+|the\s+)?(?:nameplate|design)\b")
_FIG_SHIP = re.compile(r"(?i)(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?:-\s*)?(?:wet\s+|dry\s+)?(?:metric\s+)?(tonnes?|t)\b(?![\s-]*(?:per|/)\s*(?:day|"
                       r"year|annum|month|hour))")


_FIG_REC = re.compile(r"(?i)\brecover(?:y|ies)\b[^.%\d]{0,50}?(?:approximately\s+)?"
                      r"(\d{2}(?:\.\d)?)\s?%|(\d{2}(?:\.\d)?)\s?%\s+(?:gold\s+|silver\s+|metallurgical\s+)?recover(?:y|ies)\b")
_FIG_TONNES_OUT = re.compile(r"(?i)\b(?:produced|mined|generated?)\s+(?:approximately\s+)?(\d{1,3}(?:,\d{3})+|\d+)\s*(?:tonnes|t)\s+of\s+"
                             r"(?:mineralized\s+material|ore|sulphide\s+ore)|(?:approximately\s+)?(\d{1,3}(?:,\d{3})+|\d+)\s*tonnes\s+of\s+"
                             r"(?:sulphide\s+)?ores?\b")


def _figures(event_type, s):
    f = []
    if _STUDY.search(s) or re.search(r"(?i)\b(?:can|could|would|should|may|might)\s+(?:be|result|allow|reach|achieve)\b|\bstudy\b", s):
        return f                                    # study results and possibilities are not reported figures
    s = re.sub(r"(?i)\b(?:expected|forecast\w*|guidance|outlook|anticipated|projected|projecting|planned|targeted|scheduled|estimated|"
               r"will|would|could|can\s+be|yielding|potential)\b[^.;]{0,120}", " ", s)
    s = re.sub(r"(?i)\b(?:expansion|increase\w*|expand\w*|ramp\w*|grow\w*|rais\w*)\s+(?:[\w,]+\s+){0,6}?(?:from\s+[\d,.]+\s*\w*\s+)?"
               r"to\s+[\d,.]+", " ", s)
    s = re.sub(r"(?i)\b(?:between\s+)?[\d,.]+\s*(?:and|to|-|\u2013)\s*[\d,.]+\s*(?:ounces|oz|ozs|tonnes|t|tpd)\b", " ", s)   # a range is a forecast
    if event_type in ("first_production", "ramp_up", "commercial_production"):
        for m in _FIG_OZ.finditer(s):
            num = m.group(1) or m.group(4)
            v = float(num.replace(",", ""))
            if v >= 10:
                f.append({"metric": "output", "value": v, "unit": "oz", "metal": (m.group(3) or m.group(6) or None)})
                break
        m = _FIG_NAMEPLATE.search(s)
        if m:
            f.append({"metric": "pct_nameplate", "value": float(m.group(1)), "unit": "%", "metal": None})
    if event_type in ("commercial_production", "ramp_up"):
        m = _FIG_TPD.search(s)
        if m and not re.search(r"(?i)\b(?:expand\w*|increase\w*|from)\s+(?:\w+\s+){0,3}$", s[max(0, m.start() - 25):m.start()]):
            f.append({"metric": "throughput", "value": float(m.group(1).replace(",", "")), "unit": "tpd", "metal": None})
    if event_type == "shipment":
        for m in _FIG_SHIP.finditer(s):
            if re.search(r"(?i)\b(?:capacity|per\s+(?:year|annum|month)|annual|target)\b", s[m.end():m.end() + 30]):
                continue
            f.append({"metric": "shipment", "value": float(m.group(1).replace(",", "")), "unit": "t", "metal": None})
    if event_type in ("commercial_production", "first_production", "ramp_up"):
        for m in _FIG_REC.finditer(s):
            v = float(m.group(1) or m.group(2))
            if 20 <= v <= 100:
                f.append({"metric": "recovery_pct", "value": v, "unit": "%", "metal": None})
    if event_type in ("ramp_up", "expansion"):
        m = _FIG_TONNES_OUT.search(s)
        if m:
            f.append({"metric": "output", "value": float((m.group(1) or m.group(2)).replace(",", "")), "unit": "t", "metal": None})
    return f


# ------------------------------------------------------------------ the analysis
def _status(event_type, s, lo, hi, headline=False):
    s = _AS_PLANNED.sub(lambda q: "#" * len(q.group(0)), s)   # 1.0.2: "is ramping up as planned" is going to plan, not a plan
    near = s[max(0, lo - 90):hi + 110]
    pre = s[max(0, lo - 90):lo]
    if event_type == "construction_decision":
        if re.search(r"(?i)\b(?:expect\w*|anticipat\w*|plan\w*|target\w*|toward\w*|towards|advancing\s+(?:to|toward)|ahead\s+of|in\s+advance\s+of|"
                     r"prior\s+to|pending|await\w*|potential|subject\s+to|would|will|ready|required|necessary|prepar\w+|as\s+soon\s+as|once|"
                     r"support|toward|path|until|point\s+of|closer\s+to|road\s*map\s+(?:to|toward\w*)|steps?\s+(?:to|toward\w*))\b", pre + s[hi:hi + 20]):
            return "planned"
        return "achieved"
    if headline and event_type in ("commissioning", "restart") and re.search(r"(?i)\b(?:update|progress)$", s[lo:hi]):
        return "underway"                               # 1.0.2: "<Plant> Commissioning Update" (a guidance clause before it is not its plan)
    if headline and event_type == "commissioning" and re.search(r"(?i)\bstart|\bbegin|\bbegan|\bcommenc", s[lo:hi]) and re.search(r"(?i)operations$", s[lo:hi]):
        return "achieved"                               # 1.0.2: "Start of Process Plant Operations"
    if event_type == "commissioning" and re.search(r"(?i)\b(?:start\w*|begin\w*|began|begun|commenc\w*|initiat\w*|launch\w*)\s+(?:of\s+)?(?:the\s+)?"
                                                   r"(?:[\w-]+\s+){0,3}?(?:pre-)?commissioning\b", s[max(0, lo - 50):hi + 1]) and not re.search(
            r"(?i)\b(?:to|will|expect\w*|plan\w*|target\w*|schedul\w*)\s+(?:\w+\s+){0,2}$", s[max(0, lo - 70):lo]):
        return "underway"                               # 1.0.3: commissioning started is under way (whatever was completed before it)
    if event_type == "commissioning" and re.match(r"(?i)\w*\s*(?:remains?\s+|is\s+)?(?:well\s+)?on\s+(?:track|schedule)\b",
                                                  s[lo + 13:hi + 30] if s[lo:lo + 13].lower() == "commissioning" else "-"):
        return "underway"                               # 1.0.3: "Commissioning On Track for First Copper Production in Q3 2026"
    if event_type == "restart" and re.search(r"(?i)\b(?:staged|phased|gradual|progressive)\s+(?:return|restart|resumption)", s[max(0, lo - 30):hi + 10]) and\
            not re.search(r"(?i)\b(?:will|to\s+(?:begin|start|implement)|expect\w*|plan\w*)\b", s[max(0, lo - 50):lo]):
        return "underway"                               # 1.0.3: a staged return of the workforce goes on
    if event_type not in ("construction_decision", "incident") and re.search(r"(?i)\b(?:planned|proposed|intended|anticipated|expected|"
                                                                            r"potential|possible|future)\s+(?:\w+\s+){0,1}$", s[max(0, lo - 30):lo]):
        return "planned"                                # 1.0.3: "Announces Planned Resumption of Operations"
    if headline and event_type in ("restart", "commissioning", "expansion") and re.match(r"(?i)\s+(?:project\s+|plan\s+|program\s+)?(?:update|progress)\b",
                                                                                          s[hi:hi + 25]):
        return "underway"                               # 1.0.3: "Provides Mine Restart Project Update"
    if event_type == "incident" and re.search(r"(?i)\b(?:remains?|continu\w+|ongoing|persist\w*)\s+(?:in\s+place|ongoing|unresolved)\b", s[hi:hi + 60]):
        return "underway"                               # 1.0.3: "blockade at main access gate remains in place"
    if event_type == "shipment" and re.search(r"(?i)\b(?:begin|began|begun|start|commenc)\w*\s+(?:transport|truck|haul)", s[max(0, lo - 10):hi]):
        return "underway"                               # 1.0.3: product transport to port has begun and continues
    if headline:                                        # 1.0.1: the headline's own wording around its event
        clause = re.split(r"[;:|]|\s[-\u2013\u2014]\s", s[max(0, lo - 60):lo])[-1] + s[lo:hi] + re.split(r"[;:|.]|\s[-\u2013\u2014]\s", s[hi:hi + 60])[0]
        if event_type == "expansion":
            if _HL_TO_COME.search(clause):
                return "planned"                        # "expansion ... to be completed in 2021"
            if _HL_DONE.search(clause):
                return "achieved"
            if _HL_GOING.search(clause):
                return "underway"
            if re.match(r"(?i)expand(?:s|ed)\b", s[lo:hi]) or _HL_DECIDE.search(clause):
                return "achieved"
            if re.search(r"(?i)\b(?:reports?|results|update)\b", s[:lo]):
                return "underway"                       # "Reports November Production and Underground Expansion"
        if event_type in ("offtake", "contract") and not re.search(r"(?i)\b(?:expects?\s+to|intends?\s+to|plans?\s+to|will|to\s+(?:sign|enter|"
                                                                   r"negotiate|finali[sz]e)|proposed|potential)\b", s[max(0, lo - 40):lo]):
            return "achieved"                           # a signed agreement, whatever the deal is "to develop"
        if event_type == "shipment" and re.search(r"(?i)\b(?:read(?:ies|ying|y\s+for)|prepar\w+|to\s+ship|will\s+ship)\b", s[max(0, lo - 40):hi]):
            return "planned"                            # "Readies Third Shipment ... by October 20th"
        if event_type == "infrastructure" and re.search(r"(?i)\b(?:starts?|begins?|began|commenc\w+)\s+\w+ing\b", clause):
            return "underway"                           # "Starts Laying Track at the Portal": the work goes on
    if event_type == "construction_progress":
        if re.match(r"(?i)[^.;]{0,20}\b(?:about\s+to|to\s+(?:commence|begin|start)|will\s+(?:commence|begin|start)|expected\s+to\s+(?:commence|begin|start))",
                    s[hi:hi + 50]):
            return "planned"
        return "underway"
    if event_type == "status_update":
        return "underway"
    if event_type == "incident":
        return "achieved"
    if event_type != "construction_decision" and _PLAN_PRE.search(s[max(0, lo - 45):lo]):
        return "planned"
    if headline and re.search(r"(?i)\b(?:plans?|intends?|proposes?|to)\s+(?:build|construct|develop|restart|resume|commence|begin|start|"
                              r"suspend|pause|halt)\b", s[:lo]):
        return "planned"                                # "Silvercorp Plans to Build a New ... Mill"
    if headline and event_type in ("restart", "suspension") and re.search(r"(?i)\b(?:restarting|suspending|resuming|halting|pausing)\b",
                                                                          s[lo:hi]) and not re.search(r"(?i)\b(?:is|are|has|have)\s+(?:been\s+)?$",
                                                                                                      s[max(0, lo - 15):lo]):
        return "planned"                                # "Cameco Temporarily Suspending Production": announced ahead
    plan = _PLANNED.search(s[max(0, lo - 55):lo]) or re.match(
        r"(?i)\s*(?:(?!(?:and|but|while|whereas|ongoing|underway)\b)[\w,.-]+\s+){0,8}?(?:is|are|was|remains?|now)?\s*(?:now\s+)?(?:expected|targeted|scheduled|anticipated|planned|forecast|"
        r"slated|on\s+track|set\s+to|outlook|to\s+be\s+\w+ed|will(?!\s+be\s+complete))\b", s[hi:hi + 90]) or re.search(r"(?i)\boutlook\b", s[max(0, lo - 40):hi + 30])
    if event_type == "restart" and (plan or re.search(r"(?i)\b(?:plans?|program|decision|financ\w*|fund\w*|loan|toward|towards|to\s+restart|"
                                                        r"for\s+(?:the\s+)?(?:mine\s+)?restart|restart\s+(?:plan|project|activities|of\s+the\s+mine|"
                                                        r"schedule|capital|budget))\b", near) and
                                  not re.search(r"(?i)\b(?:has|have)\s+(?:successfully\s+)?(?:restarted|resumed)|\brestarted\b|\bresumed\b|"
                                                r"\brecommenced\b", near) and not re.match(r"(?i)\s+(?:has\s+|have\s+)?(?:commenced|began|begun|started)\b", s[hi:hi + 20])):
        if re.search(r"(?i)\b(?:progress\w*|underway|ongoing|\d{1,3}\s?%\s+complete|on\s+(?:budget|schedule)|remains?\s+on|advanc\w+)\b", near) and not plan\
                and not _target_date(s[hi:hi + 30]):
            return "underway"
        return "planned"
    if event_type == "restart" and re.search(r"(?i)\b(?:progress|underway|ongoing|\d{1,3}\s?%\s+complete|remains?\s+on\s+(?:budget|"
                                             r"schedule|track))\b", near) and not re.search(r"(?i)\b(?:restarted|resumed|recommenced)\b", near):
        return "underway"
    past = re.search(r"(?i)\b(?:has|have|had)\s+(?:now\s+|successfully\s+)?(?:been\s+)?\w+(?:ed|en)\b|\b(?:poured|achieved|declared|commenced|"
                     r"began|completed|reached|announced|started|delivered|shipped|restarted|resumed|recommenced|reopened|suspended|"
                     r"halted|stopped|paused|curtailed)\b", pre[-45:] + s[lo:hi]) or re.match(r"(?i)\s+(?:produced|poured|achieved|declared|"
                                                                                   r"completed|reached|shipped|delivered|started|commenced)\b", s[hi:hi + 15])
    if plan and not past:
        return "planned"
    if not past and _TARGET.match(s[hi:hi + 45].lstrip(" ,:-in").strip()) or (not past and re.match(r"(?i)[^.;]{0,40}?\b(?:in|by|during|for)\s+"
                                                                                            r"(?:Q[1-4]|H[12]|the\s+(?:first|second|third|fourth)|"
                                                                                            r"(?:early|mid|late)[\s-]|(?:19|20)\d\d|" + _MON + r")",
                                                                                            s[hi:hi + 45]) and _target_date(s[hi:hi + 60])):
        return "planned"
    if event_type == "commissioning" and re.search(r"(?i)\bcomplet\w*\s+(?:\w+\s+){0,3}commissioning\b", s[max(0, lo - 50):hi]):
        return "achieved"
    if event_type in ("commissioning", "ramp_up"):
        if re.search(r"(?i)\b(?:complet(?:e|ed|es|ion)|achieved|achieves|reached|reaches|attain(?:s|ed)|finished)\b",
                     s[max(0, lo - 25):hi + 60] if headline else near) and not _UNDERWAY.search(near) and\
                not re.search(r"(?i)\b(?:near\w*|approach\w*|final\s+stages?|almost|substantially)\b", near):
            return "achieved"
        return "underway"
    if event_type == "infrastructure" and re.search(r"(?i)\bdevelopment\b", near) and (re.search(
            r"(?i)\b\d[\d,.]*\s*(?:m|metres|meters|ft|feet|km|kilometres|kilometers)\b", near) or re.search(r"(?i)\b(?:re)?commenc\w*|\bresum\w*|\bcontinu\w*|\badvanc\w*",
                                                                                   s[max(0, lo - 40):hi])) and\
            not re.search(r"(?i)\bbreak\s*through|\bholed\b|\breached\s+(?:the\s+)?(?:target|bottom|final)|\bfinal\s+depth\b|"
                          r"\bcomplet(?:es|ed)\s+(?:the\s+)?sinking\b", near):
        return "underway"                               # development advanced by metres, or restarted: the work goes on
    if event_type == "suspension" and re.search(r"(?i)\bto\s+(?:paus|suspend|halt|stop|shut)", s[lo:hi + 3]):
        return "planned"
    if event_type == "expansion" and re.search(r"(?i)\b(?:begins?|began|commenc\w+|starts?|started)\s+(?:\w+\s+){0,3}$", s[max(0, lo - 40):lo]):
        return "underway"                               # an expansion begun is being built
    if event_type in ("expansion", "infrastructure") and re.search(r"(?i)\b(?:begins?|began|commenc\w+|starts?|started|complet\w+|"
                                                                   r"finish\w*)\s+(?:\w+\s+){0,3}$", s[max(0, lo - 40):lo]):
        return "achieved"
    if event_type in ("expansion", "infrastructure") and (_UNDERWAY.search(near) or re.search(r"(?i)\bprogress\s+(?:on|at|of)\s+(?:\w+\s+){0,5}$",
                                                                                              s[max(0, lo - 60):lo])):
        return "underway"
    if event_type in ("expansion", "restart", "commissioning") and headline and re.search(r"(?i)\bupdate\b", s):
        return "underway"
    if event_type == "expansion" and re.search(r"(?i)\b(?:approv\w+|decision|plan)\b", near):
        return "achieved"
    return "achieved"


def _span(d):
    """'2024-06-30' / '2024-06' / '2024-Q2' / '2024-H1' / '2024' -> (first month index, last month index), months since year 0."""
    if not d:
        return None
    m = re.match(r"^((?:19|20)\d\d)(?:-(\d\d)(?:-\d\d)?|-Q([1-4])|-H([12]))?$", d)
    if not m:
        return None
    y = int(m.group(1)) * 12
    if m.group(2):
        return (y + int(m.group(2)) - 1,) * 2
    if m.group(3):
        q = int(m.group(3))
        return (y + 3 * q - 3, y + 3 * q - 1)
    if m.group(4):
        hh = int(m.group(4))
        return (y + 6 * hh - 6, y + 6 * hh - 1)
    return (y, y + 11)


def _dates_near(s, lo, hi):
    """Explicit dates written around a cue: ISO strings for full dates and 'Month YYYY'."""
    out = []
    w0 = max(0, lo - 120)
    w = s[w0:hi + 120]
    for d in T._DATE.finditer(w):
        iso = T._iso(d)
        if iso:
            out.append(iso)
    for m in re.finditer(r"(?i)\b(" + _MON + r")\.?,?\s+((?:19|20)\d\d)\b", w):
        out.append("%s-%02d" % (m.group(2), _MONTHS[m.group(1)[:3].lower()]))
    return out


_GENERIC_NAME = {"mine", "mines", "project", "projects", "property", "gold", "silver", "copper", "zinc", "lead", "nickel", "lithium",
                 "complex", "mill", "plant", "operations", "operation", "north", "south", "east", "west", "lake", "river", "mountain",
                 "creek", "hill", "deposit", "district", "the", "and", "mining", "underground", "open", "phase", "stage"}


def _same_mine(a, b):
    if not a or not b:
        return a == b
    if PN.same(a, b) or PN.key(a) in PN.key(b) or PN.key(b) in PN.key(a):
        return True
    wa = {w.lower() for w in re.findall(r"[A-Za-z\u00C0-\u00ff]{4,}", a)} - _GENERIC_NAME
    wb = {w.lower() for w in re.findall(r"[A-Za-z\u00C0-\u00ff]{4,}", b)} - _GENERIC_NAME
    return bool(wa & wb)


_PLANT_WORDS = {"processing", "expanded", "new", "tailings", "tpd", "nearby", "oxide", "sulphide", "sulfide", "flotation", "gold", "silver",
                "copper", "zinc", "lead", "mill", "plant", "leach", "heap", "carbon", "cip", "cil", "gravity", "pilot", "demonstration",
                "central", "main", "second", "first", "third", "phase", "stage", "metals", "mining", "resources", "minerals", "company",
                "corp", "inc", "ltd", "limited", "lithium", "graphite", "uranium", "nickel", "cobalt", "manganese", "anode", "battery",
                "concentrate", "concentrator", "toll", "milling", "industrial", "commercial", "modular", "our", "its", "the", "a", "starter", "construction"}


_EQUIP_WORDS = {"float", "sart", "ball", "sag", "second", "third", "new", "process", "processing", "expansion", "expanded", "tonne", "tonnes", "per", "day",
                "circuit", "service", "infrastructure", "projects", "crusher", "crushing", "grinding", "flotation", "leach", "cil", "cip",
                "tailings", "filter", "sorter", "ore", "stage", "phase", "line", "unit", "units", "equipment", "fleet"}


_STOP_TOKENS = {"with", "of", "and", "for", "the", "to", "at", "on", "from", "by", "in", "into", "intent", "closing", "recycling",
                "manufacturing", "letter"}


def _equipment(name):
    """'Second Ball Mill', 'Expansion Process Plant', 'Tonne Per Day Mill': equipment, not a mine or a named plant."""
    ws = [w.lower() for w in re.findall(r"[A-Za-z\u00C0-\u00ff]+", name or "")]
    return bool(ws) and all(w in _EQUIP_WORDS or w in _GENERIC_NAME or w in _PLANT_WORDS or w.isdigit() for w in ws)


def _core_in(name, text):
    """A distinctive word of the name is written in the text ("Balabag" in "TVIRD Balabag Gold and Silver Project")."""
    name, text = _fold(name or ""), _fold(text or "")   # 1.0.1: "Espigao" (helper) is the text's "Espig\u00e3o"
    ws = ({w.lower() for w in re.findall(r"[A-Za-z]{4,}", name)} | {w.lower() for w in re.findall(r"\b[A-Z]{3}\b", name)}) - _GENERIC_NAME
    if not ws:                                          # 1.0.1: a short name ("Mon Gold Mine"): its 3-letter word
        ws = {w.lower() for w in re.findall(r"\b[A-Za-z]{3}\b", name)} - _GENERIC_NAME
    return any(re.search(r"(?i)\b" + re.escape(w) + r"\b", text) for w in ws)


def _fold(s):
    """Accents dropped ("Espig\u00e3o" -> "Espigao"), same length for plain Latin text."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


_PLAN_PRE = re.compile(r"(?i)(?:(?<!due\s)(?<!up\s)(?<!prior\s)(?<!according\s)(?<!addition\s)(?<!related\s)(?<!led\s)(?<!owing\s)"
                       r"(?<!pursuant\s)(?<!compared\s)(?<!leading\s)(?<!contributed\s)\bto(?:\s+(?:re-?)?[a-z]+\s+the)?|"
                       r"\bto\s+(?:finance|fund|support|advance|enable|facilitate|accelerate)(?:\s+(?:the|its))?(?:\s+[A-Z][\w'-]*){1,3}|"
                       r"\b(?:required|needed|permits?|permitting|approvals?)\s+(?:required\s+)?for(?:\s+(?:the|an?|its))?(?:\s+[A-Za-z]+){0,3}|"
                       r"\b(?:advance|move|progress|transition)\s+(?:in)?to(?:wards?)?(?:\s+(?:the|an?))?|"
                       r"\b(?:used|utili[sz]ed|earmarked|allocated|applied)\s+(?:for|to|towards)(?:\s+(?:the|an?))?|"
                       r"\b(?:PEA|PFS|study|studies|plans?|webinar|presentation|proposal)\s+(?:for|on)(?:\s+(?:the|an?|its))?(?:\s+[A-Z][\w'-]*){0,4}|\bto\s+(?:finance|fund|support|advance|enable|prepare\s+for|facilitate)(?:\s+the)?|\bstrategy\s+of|\bpath\s+to(?:wards?)?|"
                       r"\btowards?(?:\s+(?:a|the))?|\bin\s+order\s+to|\brequired\s+to|\bnecessary\s+to|\bready\s+(?:for|to)(?:\s+(?:a|the))?|"
                       r"\bas\s+soon\s+as|\bin\s+preparation\s+for(?:\s+(?:a|the))?|\bprepar\w+\s+for(?:\s+(?:a|the))?|\bexcited\s+to|\bplans?\s+(?:to|for)(?:\s+(?:a|the))?|"
                       r"\bseeks?\s+to|\bintends?\s+to|\baims?\s+to|\bgoal\s+of|\bpotential(?:ly)?|\bproposed)\s*$")
_NEGATED = re.compile(r"(?i)\b(?:does\s+not\s+include|do\s+not\s+include|excluding|excludes?|exclusive\s+of|not\s+including|no\s+assumption\s+of|"
                      r"without)\b[^.;]{0,90}$")


def _clean_name(n):
    """'High Return La Yaqui Grande Project' -> 'La Yaqui Grande Project'; None when nothing name-like is left."""
    if not n:
        return None
    ws = n.split()
    if len(re.findall(r"\d", n)) > 3 and (re.search(r"\d\.\d", n) or len([w for w in ws if re.search(r"\d", w)]) > 1):
        return None                                     # 1.0.1: table text ("Cash 16.1 6.7 Inventories 8.4 18.3 Property")
    cut = max((k for k, w in enumerate(ws) if k and _NAME_VERB.match(w)), default=None)
    if cut is not None:
        ws = ws[cut + 1:]                               # 1.0.1: "X Lithium Presents Project", "Extend ... and Support Future Mine"
    while len(ws) > 1 and (_BAD_NAME.search(" ".join(ws)) or _LEAD_VERB.match(ws[0]) or _NAME_VERB.match(ws[0])):
        ws = ws[1:]
    c = " ".join(ws)
    if not ws or _BAD_NAME.search(c) or re.match(r"(?i)^(?:the\s+)?(?:mines?|projects?|property|mill|plant|operations?|complex|facility)$", c) or\
            len(ws) < 2 and not re.match(r"[A-Z]", c):
        return None
    if all(w.lower().strip(".,'") in _GENERIC_NAME or w.lower().strip(".,'") in _PLANT_WORDS for w in ws):
        return None                                     # 1.0.1: "Graphite Mine" alone names no mine
    if _REGION_OPS.match(c):
        return None                                     # 1.0.2: "Bolivian Operation", "Russian Operations" name a country's mines
    return c


_FAMILY = {"commercial_production": r"(?i)\bcommercial\s+production\b", "first_production": r"(?i)\bfirst\s+(?:gold|pour|dor|bar|concentrate)",
           "shipment": r"(?i)\bshipment|\bshipped|\bdeparted|\bdelivered\b|\btrucks?\b", "suspension": r"(?i)\bsuspen|\bhalt|\bshut",
           "restart": r"(?i)\brestart|\bresum|\brecommenc", "incident": r"(?i)\bincident|\bfatal|\bfire|\binjur|\baccident",
           "construction_start": r"(?i)\bconstruction\b|\bground", "care_maintenance": r"(?i)\bcare\s+and\s+maintenance"}


def _issuer(b):
    ms = list(re.finditer(r"([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5})\s*(?:Inc|Corp|Ltd|Limited|Corporation|plc|Plc)?\.?,?\s*\(\s*(?:[\"\u201c]|"
                          r"the\s+[\"\u201c]|(?:TSXV?|TSX-V|CSE|NYSE|NEO|OTCQX|OTCQB|ASX|LSE|AIM)\b)", b[:1500]))
    for m in ms:                                        # the one the release defines as "the Company" or gives a ticker
        if re.match(r"(?i)[^)]{0,40}\b(?:company|TSXV?|TSX-V|CSE|NYSE|NEO|OTC\w*|ASX|LSE|AIM|FRA)\b", b[m.end():m.end() + 60]):
            return m.group(1)
    return ms[0].group(1) if ms else None


def analyse(headline, body):
    h, b = _prepare(headline, body)
    res = {"rows": [], "reason": None}
    sents = _sentences(b)
    if (re.match(r"(?i)^\s*(?:news\s+release|press\s+release|news|nr)?\s*[-:.]?\s*$", h) or re.match(
            r"(?i)^\s*(?:securities\s+(?:may\s+not|and\s+exchange)|not\s+for\s+(?:distribution|dissemination)|form\s+8-k|united\s+states\s+"
            r"securities|this\s+news\s+release|\d+\s*$)", h)) and sents:
        k = next((i for i, t in enumerate(sents[:8]) if re.search(r"(?i)\b(?:announce|report|provide|pleased)\w*\b", t)), 0)
        h = sents[k][:300]
    issuer = _issuer(b) or ""
    if _ROYALTY_CO.search(issuer) or (re.search(r"(?i)\b(?:royalt(?:y|ies)|stream)\b", issuer)):
        res["reason"] = "royalty or stream holder (rule DR)"
        return res
    if _DONATION.search(h) and not re.search(r"(?i)\bsuspen|\bresum|\brestart|\bclos", h):
        res["reason"] = "donation"
        return res
    if re.search(r"(?i)\b(?:issued\s+on\s+behalf\s+of|paid\s+(?:advertisement|promotion|advertorial)|sponsored\s+content|"
                 r"this\s+(?:article|content)\s+(?:was\s+)?(?:paid|sponsored))\b", b[:600]):
        res["reason"] = "promotional article"
        return res
    if _OIL_GAS.search(h):
        res["reason"] = "oil and gas, not a mine"
        return res
    if _HOUSEKEEPING.search(h) and not any(rx.search(h) for _, rx in CUES):
        res["reason"] = "corporate housekeeping"
        return res
    ap = _APPOINT_HL.search(h[:120])
    if ap and not any(rx.search(h[:ap.start()]) for _, rx in CUES) and not re.search(r"(?i)\bcontractor\b|\bEPCM?\b", h) and\
            re.search(r"(?i)\b(?:appoint\w*|promot\w*|names?|hires?|welcomes?)\b[^.]{0,80}\b(?:as|to)\b|\b(?:CEO|COO|CFO|President|"
                      r"Director|Chief|Vice|VP|Manager|Board)\b", h[:160]):
        res["reason"] = "appointment"
        return res
    news = [h] + sents[:NEWS_SENTS]
    names = PN.release_projects(headline or "", body or "")
    proj_list = [c for c in (_clean_name(n) for n in (names.get("projects") or [])) if c and not _equipment(c) and not _company_like(c, b)]
    lead_text = " ".join(news)
    ann = next((k for k, t in enumerate(sents[:8]) if re.search(r"(?i)\b(?:announc|report|pleased|provid|advis|updat)\w*\b", t)), 2) + 1

    found_in = {}
    # 1.0.1: the body (before "About") says the product is made at the release's one project: a shipment's or offtake's source
    source_named = len(proj_list) == 1 and any(_core_in(proj_list[0], t) and _PRODUCED_AT.search(t) for t in sents[:NEWS_SENTS * 3])

    def mine_for(i, s, pos, et=None):
        if sum(ch.isupper() for ch in s) > 0.6 * max(1, sum(ch.isalpha() for ch in s)):
            s = s.title()                               # an all-caps headline: the helper reads names in title case
        def dist(q, ln):                                # a name just before the cue ("Turmalina Mine Ramp-up") is its subject
            return pos - (q + ln) if q + ln <= pos else q - pos + 5
        if s not in found_in:
            found_in[s] = PN.find(s)                    # 1.0.1: one look-up per sentence (speed; same result)
        f = [(q, c, len(n)) for q, c, n in ((q, _clean_name(n), n) for q, n in found_in[s]) if c and not _equipment(c) and not re.search(
            r"(?i)\b(?:to\s+(?:install|build|construct|supply|design)(?:\s+(?:a|an|the|its|new))?|draw\s*-?\s*downs?\s+(?:on|of|under|from)\s+the|"
            r"loan|credit)\s*$", s[max(0, q - 40):q])]
        if not f and len(proj_list) <= 1:              # "Don Mario Plant": a plant the helper does not know
            for m in re.finditer(r"\b((?:[A-Z][\w\u00C0-\u00ff'-]+\s+){1,3})(Plant|Mill|Facility|Complex|Concentrator|Refinery|Smelter|Operation)\b", s):
                toks = m.group(1).split()
                while toks and (_LEAD_VERB.match(toks[0]) or toks[0].lower() in _PLANT_WORDS or toks[0].lower() in _EQUIP_WORDS):
                    toks = toks[1:]                     # "Bar From Don Mario Plant" -> "Don Mario Plant"
                if not toks or any(t.lower() in _PLANT_WORDS or t.lower() in _EQUIP_WORDS or t.lower() in _STOP_TOKENS for t in toks):
                    continue
                name = " ".join(toks + [m.group(2)])
                if _REGION_OPS.match(name):
                    continue                            # 1.0.2: "Bolivian Operation" names a country's mines, not one
                f.append((m.end() - len(name), name, len(name)))
        if len(proj_list) > 1:
            for q in proj_list:                         # the release's projects named bare in this sentence ("at Krumovgrad")
                core = [w for w in re.findall(r"[A-Za-z\u00C0-\u00ff][\w\u00C0-\u00ff'-]{3,}", q) if w.lower() not in _GENERIC_NAME]
                for w in core[:1]:
                    mm = re.search(r"\b" + re.escape(w) + r"\b", s, re.I)
                    if mm and not any(a <= mm.start() < a + ln for a, c, ln in f):
                        f.append((mm.start(), q, len(w)))
        if f:
            best = min(f, key=lambda t: dist(t[0], t[2]))
            n = best[1]
            if not re.match(r"(?i)^(?:(?:the|its|our|this|that|a|new|gold|silver|copper)\s+)+(?:mines?|projects?|property)$|^(?:mines?|projects?|property)$", n):
                for q in proj_list:                     # the helper's cleaner name for the same project
                    if PN.same(q, n) or PN.key(q) in PN.key(n):
                        return q
                return n
        if len(proj_list) == 1:
            if i == 0 and not _core_in(proj_list[0], " ".join(news[:ann + 2])) and not (et in ("shipment", "offtake") and source_named):
                return None                             # 1.0.1: the release's one project, but not named where it tells its news
            return proj_list[0]
        if proj_list and i == 0:
            return None                                 # the headline names no mine: let the body sentences name it
        if proj_list:
            try:
                p = PN.project_at(lead_text, lead_text.find(s) + pos, proj_list)
            except Exception:   # pragma: no cover - helper edge cases
                p = None
            return p or proj_list[0]
        return None

    seen = {}
    hl_types = set()
    lead6 = " ".join([h] + sents[:6])
    explo_only = bool(_EXPLORATION.search(lead6)) and not _OPERATING.search(lead6)
    # 1.0.1: facts about the whole release that decide whether a headline cue is its news
    own_name = _own_name(issuer)                        # the issuer's own name ("First <Metal>", "<X>Light") is not an event
    lead8 = " ".join([h] + sents[:8])
    hazard_ok = (bool(_HAZARD_EVAC.search(lead8)) and bool(_HAZARD_STOP.search(lead8)) or bool(_HAZARD_HL_STOP.search(h))) and\
        not _HAZARD_NONE.search(h)                      # 1.0.1: or the headline says the hazard stopped operations or shipping
    if not hazard_ok and not _HAZARD_NONE.search(h):   # full text: staff stood down, operations stopped or damage at the site
        hazard_ok = _hazard_at_site(" ".join([h] + sents[:10]))
    announce = " ".join([h] + sents[:ann])
    announce2 = " ".join([h] + sents[:ann + 2])         # the announcement and the two sentences after it
    def lead_target(et):
        """1.0.2: the target date the announcement gives for a headline event ("FID by the end of Q1 2026", "targeting the mill
        restart in 2026"): rule DV's date can sit in the lead, not only in the headline."""
        for t in sents[:ann + 3]:
            if _BACKGROUND.search(t) or _QUOTE.search(t):
                continue
            for q in CUE[et].finditer(t):
                d = _target_date(t[q.end():q.end() + 100]) or _target_date(t[max(0, q.start() - 60):q.start()])
                if d:
                    return d
                if re.search(r"(?i)\b(?:immediately|with\s+immediate\s+effect)\b", t[max(0, q.start() - 60):q.end() + 60]):
                    return "now"                            # "will immediately implement a phased restart": a concrete step
        return None
    study_lead = bool(_STUDY_LEAD.search(announce)) and not _DECIDED.search(" ".join([h] + sents[:ann + 3]))
    pilot_lead = _PILOT.search(announce2)
    build_news = next((t for t in sents[:8] if _BUILD_NEWS.search(t) and not _QUOTE.search(t) and not _BACKGROUND.search(t) and
                       not re.search(r"(?i)\b(?:we|our|us)\b", t)), None)      # a CEO's "we" is comment, not news
    explo_access = bool(re.search(r"(?i)\b(?:explor\w*|drill\w*|targets?|prospect\w*)\b", announce2 + " ".join(sents[ann + 2:ann + 4]))) and\
        not re.search(r"(?i)\b(?:mine|mining|bulk\s+sample|production|mill|plant|processing)\b", announce2)
    producer = bool(proj_list) or bool(_PRODUCT.search(lead6)) or bool(_PRODUCED_AT.search(lead6)) or bool(_OWN_PROJECTS.search(lead8)) or\
        bool(own_name and re.search(own_name.pattern + r"(?:\s+[\w-]+){0,2}['\u2019]s?\s+(?:[\w-]+\s+){0,2}(?:projects?|mines?|deposits?)\b", lead8))
    # full text: "sourced from its facility", "one or more of <Issuer>'s projects": the company has a product or project of its own
    for i, s in enumerate(news):
        is_hl = i == 0
        if not is_hl and _BACKGROUND.search(s) and not re.search(r"(?i)\btoday\b|\bis\s+pleased\b", s):
            continue
        if not is_hl and _QUOTE.fullmatch(s.strip()):
            pass
        pilot = _PILOT.search(s)
        explo = _EXPLORATION.search(s)
        study = _STUDY.search(s)
        sm = own_name.sub(lambda q: "#" * len(q.group(0)), s) if own_name else s
        for et, rx in CUES:
            for m in rx.finditer(sm):
                lo, hi = m.start(), m.end()
                win = s[max(0, lo - 70):hi + 70]
                if _NOT_OURS.search(win) or _NEGATED.search(s[max(0, lo - 100):lo]):
                    continue
                if re.search(r"(?i)\b(?:welcomes?|applauds?|congratulates?|celebrates?\s+(?:the\s+)?government)\b", s[max(0, lo - 60):lo]):
                    continue                                # "Frontier Lithium Welcomes Start of Construction on the Berens Bridge": someone else's
                if not is_hl and re.search(r"(?i)\b(?:news\s+release|press\s+release|release\s+dated|previously\s+(?:announced|reported|disclosed)|"
                                           r"as\s+(?:previously\s+)?announced)\b[^.]{0,80}$", s[max(0, lo - 100):lo]) and\
                        et in ("construction_decision", "construction_start", "first_production", "commercial_production", "commissioning",
                               "incident", "offtake", "contract"):
                    continue
                if explo_only and not is_hl and not _OPERATING.search(s) and et != "incident":
                    continue
                if explo_only and (not is_hl or et != "restart" or not re.search(
                        r"(?i)\b(?:mine|mining|mill\w*|plant|production|operations|processing)\b", s[lo:hi + 30])) and et in (
                        "restart", "suspension", "infrastructure", "construction_start", "care_maintenance", "construction_progress", "status_update"):
                    continue
                if et == "construction_complete":
                    et = "construction_progress"
                    cc = True
                else:
                    cc = False
                if et == "care_maintenance" and re.search(r"(?i)\b(?:after|following|from|out\s+of|emerg\w+\s+from|years\s+(?:on|in|of))\b"
                                                          r"[^.;]{0,35}$", s[max(0, lo - 45):lo]):
                    continue
                if et in ("commercial_production", "first_production") and re.search(
                        r"(?i)\b(?:at\s+the\s+start\s+of|upon|once|until|when|prior\s+to|before|beginning\s+(?:at|with|from))\s+(?:the\s+)?"
                        r"(?:\w+\s+){0,2}$", s[max(0, lo - 40):lo]):
                    continue
                if et in ("restart", "suspension") and re.match(r"(?i)[^.;]{0,30}\b(?:explor\w*|drill\w*|field\s*(?:work|program\w*|activit\w+|season)|"
                                                                r"sampling|geophysic\w*|discussions?|talks|negotiations?|process\s+(?:to|of|for)\b|"
                                                                r"results?\s+from|wells?\b|permitting|work\s+on\s+(?:the\s+)?(?:\w+\s+){0,2}(?:PEA|stud\w+|"
                                                                r"assessment|report|preliminary|feasibility))", s[hi:hi + 40]):
                    continue
                if et in ("restart", "suspension") and re.search(r"(?i)\b(?:explor\w*|drill\w*|field\s*work|survey|sampling)\s+(?:\w+\s+)?$",
                                                                 s[max(0, lo - 30):lo]):
                    continue                                # 1.0.1: "Initiates Exploration Restart"
                if et == "suspension" and re.search(r"(?i)\b(?:area|section|stope|level|zone|heading)\s+(?:\w+\s+){0,4}$", s[max(0, lo - 40):lo]):
                    continue
                if et == "expansion" and (re.search(r"(?i)\b(?:international|global|corporate|business|geographic|strategic\s+growth)\s+$",
                                                    s[max(0, lo - 30):lo]) or
                                          re.match(r"(?i)[^.;]{0,25}\b(?:tailings|camp|road|land|claims|portfolio|team|office|footprint)\b",
                                                   s[hi - 12:hi + 30])):
                    continue
                if et == "construction_progress" and re.search(r"(?i)\b(?:engineering|procurement|EPCM?|design|FEED)\b[^.;]{0,30}$", s[max(0, lo - 40):lo]):
                    continue                                # "engineering, procurement and construction activities": a scope
                if et == "construction_progress" and not cc and re.search(r"(?i)\b(?:contract\w*|scope|responsib\w+|will\s+(?:include|provide|perform))\b", s)\
                        and not re.search(r"(?i)\d{1,3}\s?%|\bprogress\w*|underway|ongoing|on\s+(?:schedule|budget)|ahead\s+of|\bupdate\b", s):
                    continue
                if et == "incident" and (_QUOTE.search(s[max(0, lo - 200):hi + 20]) and not is_hl or re.search(
                        r"(?i)\bpassed\s+away\b", s[lo:hi]) and not re.search(r"(?i)\b(?:employee|contractor|worker|miner|operator)\b", win) or
                        re.search(r"(?i)\bpower\s+(?:generation|plant|station)|\belectricity\b|\bgas\s+(?:processing|plant|well)|\boil\b", win)):
                    continue
                if re.search(r"(?i)\b(?:adjoin\w*|adjacent|neighbou?ring|nearby|next\s+to|along\s+strike\s+from|near\s+to)\b", win) and\
                        et in ("restart", "first_production", "commercial_production", "construction_start", "construction_decision",
                               "suspension", "expansion"):
                    continue                                # a neighbour's mine
                if et in ("restart", "first_production", "commercial_production", "construction_start", "construction_decision", "suspension",
                          "expansion") and re.search(r"(?i)\b(?:adjoin\w*|adjacent\s+to|neighbou?ring|next\s+to)\b", re.split(r"[.;]", s[:lo])[-1]):
                    continue                                # 1.0.1: "X adjoins Y Mines' Z Gold Mine, where production was restarted"
                if et == "shipment" and (re.search(r"(?i)\b(?:each|every|per|any|future|subsequent)\s+$", s[max(0, lo - 12):lo]) or
                                         re.match(r"(?i)[^.;]{0,50}\b(?:plant|equipment|modules?|mill|crusher|machinery|units?|trucks|fleet|"
                                                  r"excavators?|drills?)\b", s[lo:hi + 50])):
                    continue
                if et == "commissioning" and re.match(r"(?i)[^.;]{0,40}\b(?:electrical|power|transmission)\s+line|\bsubstation\b", s[hi:hi + 50]):
                    continue                                # a power line commissioned is the infrastructure row
                if et in ("offtake", "contract") and re.search(r"(?i)\b(?:progress\w*|pursu\w*|advanc\w*|work(?:ing)?\s+(?:on|towards)|continues?\s+to|"
                                                              r"explor\w+\s+the\s+potential|potential\s+of|seeking|in\s+discussions?)\b[^.;]{0,40}$",
                                                              s[max(0, lo - 70):lo]):
                    continue
                if et == "infrastructure" and re.search(r"(?i)\bportal\b|\baccess\s+road\b|\btransmission\s+line\b|\bpower\s+line\b|\bsubstation\b|"
                                                        r"\btailings\b|\bventilation\b", m.group(0)) and not re.search(
                        r"(?i)\b(?:construct\w*|buil[dt]\w*|complet\w*|expan\w+|rais\w+|lift\w*|commission\w*|install\w*|upgrad\w*|begin\w*|"
                        r"began|start\w*|commenc\w*|energi[sz]\w*|blast\w*|excavat\w*|collar\w*|finish\w*|develop\w*)\b", win):
                    continue                                # a facility described, not built
                if et == "construction_progress" and re.search(r"(?i)\b(?:suspend\w*|halt\w*|paus\w+|stop\w*)\s+(?:\w+\s+){0,2}$", s[max(0, lo - 35):lo]):
                    continue
                if et == "construction_decision" and re.search(r"(?i)\bgreen[\s-]?light", m.group(0)) and re.search(
                        r"(?i)\b(?:department|ministry|government|regulator\w*|agency|authority|commission|board\s+of\s+review|'s)\b", s[max(0, lo - 60):lo]):
                    continue                                # a regulator's green light is a permit
                if et == "site_cleanup" and re.search(r"(?i)\b(?:requir\w+|order\w*|must|court|ruling|claim|lawsuit|judg\w+)\b", win):
                    continue
                if re.search(r"(?i)\b(?:after|since|following|upon|prior\s+to|less\s+than\s+(?:\w+\s+){0,2}after)\s+(?:the\s+)?(?:\w+\s+){0,2}"
                             r"(?:reaching|achieving|declaring|restarting|resuming|commencing|starting|completing|the)?\s*$", s[max(0, lo - 40):lo])\
                        and et in ("construction_decision", "construction_start", "commercial_production", "first_production", "restart",
                                   "commissioning", "suspension", "care_maintenance", "incident") and not (
                            is_hl and et == "incident" and _HL_INCIDENT_NEWS.search(s[:lo])):
                    continue                                # 1.0.2: but "Provides Update Following Fire at", "Suspended ... Following Heavy Rains"
                if re.search(r"(?i)\b(?:announced|reported|declared)\s+(?:\w+\s+){0,5}$", s[max(0, lo - 60):lo]) and\
                        _ON_DATE.search(s[hi:hi + 80]) and not re.search(r"(?i)\btoday\b", s[max(0, lo - 80):hi + 40]) and not is_hl and\
                        re.search(r"(?i)\b(?:and|also|previously|then)\b|\b[A-Z]{2,5}\s+announced\b", s[max(0, lo - 80):lo]):
                    continue                                    # "DPM announced first concentrate production on March 14, 2019 and ..."
                if et == "commercial_production" and not re.search(r"(?i)\b(?:achiev|declar|reach|commenc|enter|begin|began|start|attain|"
                                                                   r"effective|at\s+commercial\s+(?:levels|rates|scale)|of\s+commercial\s+production\s+at|in\s+commercial\s+"
                                                                   r"production)\w*", s[max(0, lo - 70):hi + 40]):
                    continue
                if et == "commercial_production" and re.search(r"(?i)^\s*rates?\b", s[hi:hi + 10]) or\
                        et == "commercial_production" and re.search(r"(?i)\b(?:quarter|month|year)\s+of\s*$", s[max(0, lo - 25):lo]):
                    continue
                if et == "commissioning" and not is_hl and not re.search(r"(?i)\b(?:plant|mill|circuit|concentrator|facility|processing|crusher|crushing|"
                                                          r"smelter|refinery|mine|project|operation|kiln|leach|flotation|sulphide|oxide|"
                                                          r"heap|power|substation|shaft|hoist|ventilation|equipment)\b", win) or\
                        et == "commissioning" and re.search(r"(?i)\bairstrip|\bsupport\s+for\s+(?:the\s+)?commissioning", win):
                    continue
                if et == "incident" and re.search(r"(?i)\bring\s+of\s+fire\b|\bfire\s+assay|\bfire\s+(?:and|&)\s+|\bfire[\s-]?(?:proof|"
                                                  r"suppression|safety|protection)", win):
                    continue
                if et == "suspension" and not re.search(r"(?i)^[^.]{0,50}\b(?:mining|operations?|production|processing|mill\w*|plant|mine|"
                                                        r"construction|activities|shipments?|haulage|rail|crushing|dor[e\u00e9]|development|"
                                                        r"circuit|facility)\b",
                                                        s[lo:hi + 60]) and not re.search(r"(?i)\b(?:mining|operations?|production|"
                                                                                         r"processing|mill\w*|plant|mine|construction|development|"
                                                                                         r"circuit)\s+(?:[\w,]+\s+){0,6}$", s[max(0, lo - 70):lo]):
                    continue
                if et == "suspension" and re.search(r"(?i)\billegal\b|\bdiscussions?\b|\bnegotiations?\b|\bdividend|\bguidance\b", win):
                    continue
                if et == "offtake" and re.search(r"(?i)\bsatisfactory\b|\bconditions?\b|\bsubject\s+to\b|\bcondition\s+precedent\b|"
                                                 r"\bseek\w*\b|\bfuture\b", win):
                    continue
                if et == "ramp_up" and not re.search(r"(?i)ramp", m.group(0)) and not re.search(
                        r"(?i)\b(?:reach\w*|achiev\w*|attain\w*|operat\w+\s+at|exceed\w*)\b[^.]{0,30}$", s[max(0, lo - 50):lo]):
                    continue
                if et == "ramp_up" and re.search(r"(?i)\b(?:increas\w*|expand\w*|upgrad\w*|from\s+\d)\b[^.]{0,40}(?:nameplate|design)|"
                                                 r"(?:nameplate|design)\s+(?:capacity\s+)?(?:of|by|to|from)\s+\d", win):
                    continue
                if pilot and et in ("commissioning", "first_production", "construction_start", "construction_progress", "restart"):
                    continue
                if et in ("restart", "suspension", "incident", "commissioning", "infrastructure", "contract") and explo and\
                        not (et == "incident" and hazard_ok) and\
                        re.search(r"(?i)\bdrill\w*|\bexploration|\bfield|\bsurvey|\bgeophysic|\bsampling|\bprospect|\bassays?\b|\bveins?\b|"
                                  r"\bg/t\b", win):
                    continue
                if et == "incident" and re.search(r"(?i)\balong\s+strike|\bstrike\s+(?:length|extent|direction)|\bon\s+strike\b", win):
                    continue
                if et == "incident" and not _HAZARD_CUE.search(m.group(0)) and re.search(r"(?i)\bno\s+(?:injuries|incident)|\bsafety\s+(?:record|performance|statistics)|"
                                                  r"\bLTI\b|\blost[\s-]time\b|\bwithout\s+(?:a|an)\s+", win):
                    continue
                if et in ("construction_decision", "construction_start") and study and re.search(
                        r"(?i)\b(?:would|could|assum\w+|study|PEA|PFS|feasibility|scenario)\b", win):
                    continue
                if et == "expansion" and re.search(r"(?i)\b(?:land\s+(?:package|position)|claims?|mineral\s+resources?|resource\s+(?:estimate|base|"
                                                   r"expansion|growth)|exploration|footprint|along\s+strike|mineraliz\w*)\b", win):
                    continue
                if et == "shipment" and re.search(r"(?i)\bsamples?\b|\bcore\b|\bbulk\s+sample\s+(?:was\s+)?shipped\s+to\s+(?:a\s+)?lab", win):
                    continue
                if et == "contract" and re.search(r"(?i)\bdrill\w*\s+contract|\bconsult\w*|\bengineering\s+study|\bfeed\b", win):
                    continue
                if et == "contract" and not re.search(r"(?i)\b(?:award\w*|sign\w*|execut\w*|enter\w*|select\w*|appoint\w*|engag\w*|"
                                                      r"retain\w*|agreed\s+(?:to|with|on|terms)|conclud\w*|finaliz\w*|reache[sd]|announc\w*|amend\w*|"
                                                      r"terminat\w*|mobili[sz]\w*|designat\w*|contracts|plac\w+|initiat\w*|issu\w+)\b", s[max(0, lo - 70):hi + 70]):
                    continue
                if et == "offtake" and re.search(r"(?i)\bterminat\w+|\bno\s+offtake|\bwithout\s+(?:an?\s+)?offtake", win) is None and\
                        re.search(r"(?i)\b(?:potential|seek\w*|interest\s+from|discussions?|negotiat\w+)\b", win) and not re.search(
                            r"(?i)\b(?:sign\w*|execut\w*|enter\w*|agreed|binding|term\s+sheet|MOU|memorandum)\b", win):
                    continue
                if et == "ramp_up" and re.search(r"(?i)\b(?:would|could|study|PEA|PFS|feasibility|scenario|years?\s+\d)\b", win) and not is_hl:
                    continue
                if not is_hl and (i > 6 and et in ("infrastructure", "expansion") or i > 12 and et == "contract"):
                    continue
                if not _is_own_event(et, s, lo, hi, m.group(0), is_hl, proj_list):
                    continue                                # 1.0.1: exploration, land, studies or someone else's product (see _is_own_event)
                if et == "incident" and _HAZARD_CUE.search(m.group(0)) and not hazard_ok:
                    continue                                # 1.0.1: a wildfire or earthquake with no evacuation, stop or damage at our site
                if is_hl and et in BUILD + ("restart",) and study_lead and et not in ("restart",) and not _hl_fact(h, lo, hi):
                    continue                                # 1.0.1: a study's headline ("Expansion Plan", scoping study) is not a build
                if is_hl and pilot_lead and et in ("commissioning", "first_production", "construction_start", "construction_progress",
                                                   "expansion", "commercial_production", "shipment"):
                    continue                                # 1.0.1: rule DP, the release is about a pilot, test or demonstration plant
                if is_hl and et in ("expansion", "construction_start", "construction_progress", "construction_decision", "infrastructure") and\
                        _FIN_OBJECT.search(h[:lo]) and not build_news and not (
                            et == "construction_decision" and (re.search(r"(?i)approv", m.group(0)) or _DECISION_TAKEN.search(h[max(0, lo - 40):lo]) or
                                                               lead_target(et)))\
                        and not re.search(r"(?i)(?:\band|;)\s*(?:provides?|announces?|reports?|gives?)\b",
                                          h[[f.end() for f in _FIN_OBJECT.finditer(h[:lo])][-1]:lo]):
                    continue                                # 1.0.1: a loan or tranche "for the expansion" with no build news of its own
                if et == "construction_start" and re.match(r"(?i)[^.;]{0,15}\bof\s+(?:the\s+|a\s+|an\s+|its\s+)?(?:[\w-]+\s+){0,2}(?:roads?|power\s*lines?|"
                                                           r"transmission\s+lines?|portal|decline|shaft|substation|airstrip|bridge|"
                                                           r"conveyor)\b", s[hi:hi + 50]):
                    et = "infrastructure"                   # 1.0.1: "Commencement of Construction of the Winter Road" is the road's row
                if is_hl and et in ("infrastructure", "construction_start", "construction_progress") and re.search(
                        r"(?i)\b(?:signs?|signed|execut\w+|enters?\s+into|entered\s+into|awards?|awarded|finali[sz]\w+)\s+(?:an?\s+|the\s+)?"
                        r"(?:[\w-]+\s+){0,3}?(?:agreement|contract|letter\s+of\s+intent|LOI|MOU)\s+(?:with\s+[^;:|]{2,60}?\s+)?for\s+(?:the\s+)?"
                        r"(?:[\w,-]+\s+){0,9}$", re.split(r"[;:|]|\s[-\u2013\u2014]\s", s[max(0, lo - 160):lo])[-1]) and not re.search(
                        r"(?i)\b(?:loan|credit|financ\w+|funding|stream\w*|royalt\w*|off-?take|purchase|sale|option|acquisition|"
                        r"permit\w*\s+agreement)\b", s[max(0, lo - 160):lo]):
                    et = "contract"                         # 1.0.3: "Signs Agreement with X for the Construction of the Power Line"
                if et == "contract" and re.search(r"(?i)\bcontracts?\s+to\s+(?:sell|supply|deliver)\b|\b(?:sales?|supply)\s+contract\b",
                                                  s[max(0, lo - 10):hi + 40]):
                    et = "offtake"                          # 1.0.1: a contract to sell the company's product is an offtake
                if et == "infrastructure" and explo_access and re.search(r"(?i)\broads?\b|\bcamp\b|\btrails?\b|\bairstrip\b", s[max(0, lo - 20):hi + 20]):
                    continue                                # 1.0.1: access roads or camps built for exploration give no row
                if is_hl and et in ("suspension", "restart") and _EXPLO_STOP.search(announce2) and not _OPS_STOP.search(announce2) and not (
                        not explo_only and re.search(r"(?i)\b(?:paus|suspen|halt|stop)\w*\s+(?:\w+\s+){0,3}development\s+(?:activities|work)\b",
                                                     announce2)):
                    continue                                # 1.0.1: the release says the pause or restart is of exploration
                if et in ("offtake", "contract") and not producer:
                    continue                                # 1.0.1: a supply deal by a company with no mine, plant or product of its own
                if et == "ramp_up" and re.match(r"(?i)[^.;]{0,40}\b(?:post|after|following)\s+(?:the\s+)?(?:[\w-]+\s+){0,3}(?:shutdowns?|suspensions?|"
                                                r"stoppages?|halts?|closures?)\b", s[hi:hi + 80]):
                    et = "restart"
                if is_hl and et == "suspension" and re.match(r"(?i)\w*\s+of\s+(?:the\s+)?(?:[\w'-]+\s+){0,2}?(?:strike|blockade|labou?r\s+action|"
                                                           r"work\s+stoppage)\b", s[hi - 2:hi + 50]):
                    et = "restart"                          # 1.0.3: "suspension of strike at X mine": the strike ended, work resumes
                resolved = is_hl and et == "incident" and bool(_RESOLVED.search(s[max(0, lo - 40):lo])) and bool(
                    re.search(r"(?i)\bresum\w*|\brestart\w*|\breturn\w*\s+to\s+(?:work|normal)", " ".join(sents[:ann + 1])))
                settled = is_hl and et == "incident" and not resolved and bool(
                    _RESOLVED.search(s[max(0, lo - 40):lo]) or re.search(r"(?i)\b(?:settlement|end|resolution)\s+of\s+(?:the\s+)?(?:[\w'-]+\s+){0,2}$",
                                                                       s[max(0, lo - 40):lo])) and re.search(r"(?i)strike|labou?r|union|stoppage", m.group(0))
                if resolved or settled:                     # 1.0.2: "Resolves Labour Action": operations resume, a restart (label guide)
                    et = "restart"                          # 1.0.3: "Settlement of Miners Strike" with no resumption yet: planned
                st = _status(et, s, lo, hi, is_hl)
                if st == "achieved" and et not in ("construction_decision", "incident", "offtake", "contract") and _not_yet(s, lo, hi):
                    st = "planned"                          # 1.0.3: a forecast or target is never achieved
                if settled:
                    st = "planned"
                if resolved:
                    rs = next(t for t in sents[:ann + 1] if re.search(r"(?i)\bresum\w*|\brestart\w*|\breturn\w*\s+to\s+(?:work|normal)", t))
                    st = "planned" if re.search(r"(?i)\b(?:expect\w*|will|later\s+(?:today|this\s+week)|to\s+(?:resume|restart|return))\b", rs) else "achieved"
                if is_hl and et == "restart" and st == "planned" and _RESUMED_NOW.search(" ".join(sents[:ann + 1])):
                    st = "achieved"                         # 1.0.1: "Receives Approval for Resumption ..." and operations "began today"
                if is_hl and et in ("expansion", "construction_progress", "construction_start") and _FIN_OBJECT.search(h[:lo]) and build_news:
                    st = "underway"                         # 1.0.1: a drawdown for an expansion whose build is under way
                if et == "construction_progress" and st == "planned" and not is_hl and not cc:
                    continue
                if et == "construction_start" and re.match(r"(?i)\s*ceremony\b", s[hi:hi + 12]) and not re.search(
                        r"(?i)\b(?:held|took\s+place|celebrated|hosted|marked)\b", s):
                    st = "planned"                          # a ground-breaking ceremony announced ahead of the day
                if cc:
                    st = "underway" if re.search(r"(?i)\b(?:near\w*|approach\w*|substantially|almost)\b|\b\d{1,3}\s?%", s[max(0, lo - 40):hi + 10])\
                        else ("planned" if st == "planned" else "achieved")
                if et in ("construction_decision", "expansion") and st == "planned" and not (resolved or settled) and not (_target_date(s[lo:]) or _target_date(s[max(0, lo - 80):lo]) or
                                                                                   is_hl and lead_target(et)):
                    continue                                    # rule DV: a decision still to come needs its target date
                if st == "planned" and (not is_hl and i > 4):
                    continue
                if st == "planned" and _QUOTE.search(s[max(0, lo - 200):hi + 20]) and not is_hl:
                    continue
                if st == "planned" and et in ("construction_start", "first_production", "commercial_production", "restart", "commissioning",
                                              "expansion", "infrastructure", "contract", "offtake") and not (resolved or settled) and not (_target_date(s[lo:]) or _target_date(s[max(0, lo - 80):lo]) or
                                                                     re.search(r"(?i)\b(?:decision|financing|funding|loan|contract|"
                                                                               r"agreement|approv\w+|closes?|closed|placing|placed)\b", s) or
                                                                     is_hl and lead_target(et) or
                                                                     is_hl and re.search(r"(?i)\bannounc\w*\s+(?:the\s+|its\s+)?(?:planned|proposed)\s+$",
                                                                                         s[max(0, lo - 40):lo])):
                    continue                                    # rule DV: no date and no concrete step (1.0.3: a restart the
                                                                # headline announces as planned is the decision itself)
                mine = mine_for(i, s, lo, et)
                key = (et, (PN.key(mine) if mine else None))
                cand = {"event_type": et, "status": st, "mine": mine, "sent": i, "pos": lo, "text": s, "lo": lo, "hi": hi}
                if any(k[0] == et for k in seen) and mine and re.search(r"(?i)\b(?:mill|plant|processing|concentrator)\b", mine):
                    key = next(k for k in seen if k[0] == et)
                if key not in seen:
                    key = next((k for k, v in seen.items() if k[0] == et and (_same_mine(v["mine"], mine) or not v["mine"] or not mine or (
                        v["sent"] == 0 and i <= 3 and (_core_in(mine, v["text"]) or _core_in(v["mine"], s))))), key)
                    if key in seen and not seen[key]["mine"] and mine and (_core_in(mine, s) or _core_in(mine, " ".join(news[:12]))):
                        seen[key]["mine"] = mine            # the unnamed row takes the name the release gives later
                if key in seen:
                    old = seen[key]
                    if i > old["sent"] and i <= 8:
                        old.setdefault("support", []).append((s, lo, hi, st))
                    continue
                if et in ("construction_progress", "construction_start") and any(k[0] == "commissioning" and k[1] == key[1] for k in seen)\
                        and et == "construction_progress" and not is_hl:
                    continue
                seen[key] = cand
                if is_hl:
                    hl_types.add(et)
                break
    # routine operations update (rule DU as Justin decided)
    su = _STATUS_UPDATE_HL.search(h)
    live = [m for m in _OPERATING.finditer(" ".join(sents[:8])) if not re.search(
        r"(?i)\b(?:future|potential|proposed|planned|expected|targeted|would|could|anticipated|undeveloped|feasibility)\b[^.]{0,30}$",
        " ".join(sents[:8])[max(0, m.start() - 50):m.start()])]
    if su and not (hl_types - {"status_update"}) and not re.search(r"(?i)\bexploration\b|\bdrill", h[:su.start()]) and not explo_only and\
            live and not re.search(r"(?i)\bundeveloped\b|\bpre-(?:development|production)\b", " ".join(sents[:5])):
        hl_types.add("status_update")
        mine = proj_list[0] if proj_list else None
        seen[("status_update", PN.key(mine) if mine else None)] = {"event_type": "status_update", "status": "underway", "mine": mine,
                                                                   "sent": 0, "pos": 0, "text": h, "lo": 0, "hi": 0}
    cands = sorted(seen.values(), key=lambda c: (c["sent"], c["pos"]))
    mk = lambda c: PN.key(c["mine"]) if c["mine"] else None  # noqa: E731
    # a financing, exploration, study or permit headline without an event of its own reports none
    if not hl_types and (_FIN_HL.search(h) or _EXPLORATION.search(h) or _STUDY.search(h) or _PERMIT_HL.search(h)):
        res["reason"] = "financing / exploration / study / permit news"
        return res
    # milestones only (rule DG)
    MILESTONE = ("construction_decision", "construction_start", "commissioning", "first_production", "commercial_production",
                 "expansion", "restart")
    rel = _span(T._dateline(b) or _first_date(b))       # 1.0.3: a bare "August 11, 2025" dateline (no city) is the release date
    for c in cands:                                     # a headline event dated after the release is still to come
        if rel and c["sent"] == 0 and c["status"] == "achieved" and not re.search(
                r"(?i)\b(?:has|have|had)\s+(?:been\s+)?\w+ed\b|\b(?:achieved|completed|commenced|began|poured|declared|restarted|resumed|"
                r"started|reached|suspended|halted)\b", c["text"][max(0, c["lo"] - 40):c["hi"]]):
            td = _target_date(c["text"][c["hi"]:c["hi"] + 60])
            mo = re.match(r"(?i)\s+(?:in|by|during|from)\s+(?:early\s+|mid-?\s*|late\s+)?(" + _MON + r")\b(?!\.?\s*,?\s*(?:\d|19|20))", c["text"][c["hi"]:c["hi"] + 40])
            if not td and mo and rel[0] == rel[1]:      # 1.0.3: "First Copper Sales in September" (no year): the release's year
                td = "%04d-%02d" % (rel[0] // 12, _MONTHS[mo.group(1)[:3].lower()])
            if td and _span(td) and _span(td)[0] > rel[1]:
                c["status"] = "planned"
    for c in cands:                                     # "Restart of MTL in Q1 2026" reported after Q1 2026 happened
        if rel and c["status"] == "planned" and c["event_type"] not in ("construction_decision",):
            td = _target_date(c["text"][c["hi"]:c["hi"] + 40])
            if td and _span(td) and _span(td)[1] < rel[0] and not _PLANNED.search(c["text"][max(0, c["lo"] - 40):c["hi"] + 40]):
                c["status"] = "achieved"
    kept = []
    for c in cands:
        et, same = c["event_type"], [k for k in cands if k is not c and mk(k) == mk(c)]
        hl = c["sent"] == 0
        # a target inside another event's release is that event's next target, not a row of its own
        if c["status"] == "planned" and et in ("first_production", "commercial_production", "commissioning", "ramp_up",
                                               "construction_start", "construction_progress", "expansion", "restart") and\
                any(k["event_type"] in BUILD + ("restart",) and k["event_type"] != et and k["status"] != "planned" and
                    (et != "restart" or k["sent"] == 0) for k in same) and not (
                    hl and _target_date(c["text"][c["hi"]:c["hi"] + 50]) and not any(k["event_type"] == "construction_progress" for k in same)):
            continue                                    # 1.0.2: but a dated target the headline itself states is headline news
                                                        # ("Begins Commissioning; Production Expected to Commence in Q3 2026"),
                                                        # except in a progress update, where it is the next target (rule DG)
        if et == "infrastructure" and not hl and (same or c["sent"] > 2 or c["status"] == "planned"):
            continue
        if et == "infrastructure" and not hl and _PERMIT_HL.search(h):
            continue
        if et == "construction_progress" and any(k["event_type"] in MILESTONE and k["sent"] <= max(c["sent"], 3) and k["status"] != "planned"
                                                 for k in same):
            continue
        if et == "ramp_up" and not hl and (c["sent"] > 3 or c["status"] == "planned" or any(
                k["event_type"] in ("commercial_production", "first_production", "commissioning") for k in same)):
            continue
        if et in ("commissioning", "first_production", "commercial_production") and not hl and c["sent"] > 5:
            continue
        if et == "suspension" and not hl and any(k["event_type"] == "restart" and k["status"] == "achieved" for k in same):
            continue
        if et == "restart" and not hl and c["status"] == "achieved" and any(
                k["sent"] == 0 and k["event_type"] in ("suspension", "care_maintenance", "closure") for k in same):
            continue                                    # the news is the stop; the earlier restart is its history
        if et == "construction_progress" and c["status"] == "achieved" and any(
                k["event_type"] in ("infrastructure", "expansion") and (k["text"] == c["text"] or k["sent"] <= 1) for k in cands):
            continue                                    # a finished decline or tailings lift is the infrastructure row
        if et == "ramp_up" and not hl and any(k["event_type"] == "restart" and k["status"] != "planned" for k in same):
            continue
        if et == "construction_progress" and hl and not re.search(r"(?i)\bconstruct\w*|\binstall\w*|\berect\w*|\bbuil[dt]\b|\bearthworks?\b|"
                                                                  r"\bconcrete\b|\d{1,3}\s?%\s+complete|\bfabricat\w*|\bcommission\w*|\bschedule\b|"
                                                                  r"\bbudget\b|\bdecline\b|\bportal\b|\bshaft\b|\bmill\b|\bplant\b",
                                                                  " ".join(sents[:10])):
            continue                                    # a "development update" with nothing being built
        if et == "status_update" and any(k is not c and k["sent"] <= 6 and k["status"] != "planned" for k in cands):
            continue                                    # the update reports an event: the event is the row
        if rel and c["status"] == "achieved" and not hl and et not in ("status_update",):
            old = [d for d in _dates_near(c["text"], c["lo"], c["hi"]) if _span(d) and _span(d)[1] < rel[0] - 5]
            if old and not re.search(r"(?i)\btoday\b|\bthis\s+(?:week|month|quarter)\b", c["text"]):
                continue                                # an event dated half a year before the release is history
        kept.append(c)
    if HEADLINE_ONLY:
        body = [c for c in kept if c["sent"] > 0 and c["event_type"] != "status_update"]
        kept = [c for c in kept if c["sent"] == 0 and c["event_type"] != "status_update"]
        gm = _GENERIC_HL.search(h)
        if not kept and gm and not re.search(r"(?i)\b(?:programs?|exploration|drill\w*)\b",
                                             h[max(0, gm.start() - 30):gm.end()] + re.split(r"(?i)\s+and\s+|[;:|]", h[gm.end():])[0]):
            # 1.0.2: a generic headline ("Provides Operations Update", "Q3 Results", "Update on <X> Operations") announces no
            # event of its own; the event its announcement states is the news, when stated as news (dated or just done, not a
            # quote, a dated recap, a bracketed aside or a state that continues), and not a commercial deal or a piece of the build
            for c in body:
                t, lo_, hi_ = c["text"], c["lo"], c["hi"]
                if c["sent"] > ann + 3 or c["event_type"] in ("contract", "offtake", "infrastructure", "shipment"):
                    continue
                if _QUOTE.search(t) or re.match(r"(?i)\s*(?:in|during|on|since|by)\s+(?:early\s+|late\s+|mid-?)?(?:" + _MON + r"|Q[1-4]|20\d\d)", t):
                    continue                        # a quote, or a sentence opening on a past date ("In August 2018, ...")
                if t[:lo_].count("(") > t[:lo_].count(")") or re.search(r"(?i)\bcontinu\w*\b[^.;]{0,40}$", t[max(0, lo_ - 50):lo_]):
                    continue                        # inside brackets, or a state that continues
                if c["status"] == "achieved" and not (_dates_near(t, lo_, hi_) or re.search(
                        r"(?i)\btoday\b|\bthis\s+(?:week|month)\b|\b(?:in|on|during)\s+" + _MON + r"\b|\b(?:has|have)\s+(?:now\s+)?(?:been\s+)?\w+ed\b", t)):
                    continue                        # an achieved body event must carry its date (or be just done: "has restarted")
                hx = t.lower().find(h[:60].lower())
                if 0 <= hx and lo_ < hx + len(h) or re.search(r"\b(?:[Ww]e|[Oo]ur)\b", t):
                    continue                        # the cue is the headline repeated in the dateline, or a first-person comment
                if re.search(r"(?i)\b(?:call\w*\s+for|recommend\w*|threat\w*|seek\w*|request\w*|propos\w*)\s+(?:the\s+|a\s+)?$", t[max(0, lo_ - 40):lo_]):
                    continue                        # "calling for the suspension": not (yet) the event
                if c["event_type"] == "incident" and any(k["event_type"] == "restart" and k["text"] == t for k in body):
                    continue                        # the strike a restart ends is its cause, not news (label guide)
                if c["mine"] and not _core_in(c["mine"], " ".join([h, t] + sents[:ann])):
                    c = dict(c, mine=None)          # the release's project, but not named where it tells this news
                if re.search(r"(?i)\bwill\s+(?:be\s+)?$", t[max(0, lo_ - 20):lo_]):
                    c = dict(c, status="planned")   # "will be suspending operations"
                kept.append(c)
        # 1.0.1: one event, one row
        if any(c["event_type"] == "incident" for c in kept) and re.search(r"(?i)\b(?:fatal\w*|accident|rescue|collapse|explosion|injur\w*|"
                                                                          r"death|died)\b", h):
            kept = [c for c in kept if c["event_type"] not in BUILD]   # "Rescue ... in Shaft 1 ... completed": the accident, not the shaft
        for c in list(kept):
            if c["event_type"] == "construction_start" and any(k["event_type"] == "expansion" and 0 <= k["lo"] - c["hi"] <= 40 for k in kept):
                kept.remove(c)                          # "Groundbreaking for Phase III Expansion": the expansion's row
            elif c["event_type"] == "expansion" and any(k["event_type"] == "infrastructure" and 0 <= k["lo"] - c["hi"] <= 40 for k in kept):
                kept.remove(c)                          # "Phase 2 Expansion of the Solar Plant": the facility's row
            elif c["event_type"] == "expansion" and any(k["event_type"] == "ramp_up" and 0 <= c["lo"] - k["hi"] <= 40 for k in kept):
                kept.remove(c)                          # "Ramping up the ... Phase II expansion project": the ramp-up's row
        for c in list(kept):
            if c["event_type"] == "commissioning" and c["sent"] == 0 and any(
                    k["event_type"] == "ramp_up" and k["sent"] == 0 and 0 <= k["lo"] - c["hi"] <= 25 and
                    re.match(r"(?i)\s+and\s+(?:production\s+)?$", h[c["hi"]:k["lo"]]) for k in kept):
                kept.remove(c)                      # 1.0.3: "Commissioning and Production Ramp Up": the ramp-up's row
        kept += _companions(kept, h, sents, ann)    # 1.0.2: the stop an incident caused, the incident that caused a stop
        if not kept and _HEALTH_HL.search(h):       # 1.0.2: a COVID notice whose lead says operations were suspended (label COVID rule)
            for j, t in enumerate(sents[:10]):
                mm = _COMPANION_STOP.search(t)
                if mm and not _BACKGROUND.search(t) and not re.search(r"(?i)\b(?:explor\w*|drill\w*|if|should|would|could|may)\b", t) and\
                        not re.search(r"(?i)\b(?:no|not|without|never)\b[^.;]{0,30}$", t[max(0, mm.start() - 40):mm.start()]):
                    kept.append({"event_type": "suspension", "status": "achieved", "mine": mine_for(j + 1, t, mm.start(), "suspension"),
                                 "sent": 0, "pos": mm.start(), "text": t, "lo": mm.start(), "hi": mm.end()})
                    break
        for c in kept:                              # 1.0.2: a construction update at a mine being brought back is the restart's
            if c["sent"] == 0 and c["event_type"] == "construction_progress" and _RESTART_WORK.search(" ".join([h] + sents[:ann + 4])) and\
                    not any(k["event_type"] == "restart" for k in kept):
                c["event_type"] = "restart"             # still awaiting permits: planned (rule DS); otherwise the work is under way
                c["status"] = "planned" if re.search(r"(?i)\bpermit\w*", " ".join([h] + sents[:ann + 1])) else "underway"
        lead_r = " ".join(sents[:ann + 2])
        for c in kept:                              # 1.0.2: "Update on Resumption of Operations" when the lead says operations will resume
            if c["sent"] == 0 and c["event_type"] == "restart" and c["status"] == "underway" and re.search(
                    r"(?i)\b(?:will|to)\s+(?:\w+\s+){0,3}(?:resume|restart|recommence)\b", lead_r) and not re.search(
                    r"(?i)\b(?:resumed|restarted|recommenced|is\s+resuming|are\s+resuming|has\s+begun|have\s+begun)\b", lead_r):
                c["status"] = "planned"
        for c in kept:                              # 1.0.2: an unnamed headline row takes "<Name> mine/operations" (lower case) from
            if c["mine"] is None and c["sent"] == 0 and len(proj_list) <= 1:   # the headline or announcement ("at its Rice Lake operations")
                c["mine"] = _lower_suffix_name(" ".join([h] + sents[:ann + 1]))
        kept = _split_mines(kept, h, sents, ann)    # 1.0.2: one event at two or more named mines is one row per mine
        if kept:
            kept += _body_companions(kept, body, sents, ann)   # 1.0.3: the announcement's other milestones at the same mine
        if not kept:
            res["reason"] = "no headline event"
            return res
    # without a headline event, a release needs its event in the first sentences: a passing mention is not the news
    generic = re.search(r"(?i)\bprovides?\s+(?:an?\s+)?(?:corporate\s+|project\s+|operational\s+|operations\s+)?update\b", h)
    if kept and not any(c["sent"] == 0 for c in kept) and not any(c["sent"] <= (8 if generic else 3) for c in kept):
        res["reason"] = "event only in passing"
        return res
    if not kept:
        res["reason"] = "no mine event"
        return res
    declared = _declared_currency(b)
    build_row = next((c for c in kept if c["event_type"] in ("construction_progress", "construction_decision", "construction_start",
                                                               "expansion", "restart", "commissioning", "commercial_production",
                                                               "first_production")), None)
    capex = pct = None
    if build_row:
        # capex and % complete belong to the build row's project: its own sentences, sentences naming it, or any lead sentence
        # when the release is about that one project
        one_proj = len(proj_list) <= 1 and len({mk(k) for k in kept}) <= 1
        bw = [w for w in re.findall(r"[A-Za-z\u00C0-\u00ff]{4,}", build_row["mine"] or "") if w.lower() not in (
            "mine", "project", "property", "gold", "silver", "copper", "complex", "mill", "plant", "operations")]
        own = {build_row["text"]} | {t for t, a, z, st2 in build_row.get("support", [])}
        ow = set()                                      # distinctive words of the release's other projects
        for q in proj_list + [k["mine"] for k in kept if k["mine"]]:
            if build_row["mine"] and (PN.same(q, build_row["mine"]) or PN.key(q) in PN.key(build_row["mine"]) or
                                      PN.key(build_row["mine"]) in PN.key(q)):
                continue
            ow |= {w for w in re.findall(r"[A-Za-z\u00C0-\u00ff]{4,}", q) if w.lower() not in (
                "mine", "project", "property", "gold", "silver", "copper", "complex", "mill", "plant", "operations", "north", "south",
                "east", "west", "lake", "river", "mountain", "creek", "hill")}
        ow -= set(bw)
        pool = []
        for t in [h] + sents[:30]:
            if re.search(r"(?i)\b(?:private\s+placement|tranche|bought\s+deal|offering|proceeds|gross\s+proceeds|convertible|debentures?|"
                         r"credit\s+facility|stream(?:ing)?\s+(?:agreement|deal)|royalty\s+(?:agreement|financing))\b", t) and\
                    not re.search(r"(?i)\b(?:capital\s+cost|capex|construction\s+budget|project\s+budget|initial\s+capital)\b", t):
                continue
            named = bw and any(w.lower() in t.lower() for w in bw)
            other = any(w.lower() in t.lower() for w in ow)
            if one_proj or t in own or named or not other:
                pool.append(t)
        capex = _capex(pool, declared)
        pct = _pct(pool)
    FIG_ORDER = ("commercial_production", "first_production", "ramp_up", "shipment", "expansion", "commissioning")
    fig_row = {}
    for c in sorted((c for c in kept if c["event_type"] in FIG_ORDER), key=lambda c: FIG_ORDER.index(c["event_type"])):
        fig_row.setdefault(mk(c), c)                    # the figures stated with a mine's milestones go on one row
    for c in kept:
        s, lo, hi = c["text"], c["lo"], c["hi"]
        et, st = c["event_type"], c["status"]
        r = {k: None for k in TXT_FIELDS + NUM_FIELDS}
        r.update(event_type=et, status=st, mine=c["mine"])
        # dates: the row's own sentence first, then the later lead sentences that repeat its event
        places = [(s, lo, hi)] + [(t, a, z) for t, a, z, st2 in c.get("support", []) if st2 == st]
        for t, a, z in places:
            if st == "planned":
                d = _target_date(t[a:]) or _target_date(t[max(0, a - 80):a])
            elif st == "underway":
                d = _asat(t) if et in ("construction_progress", "expansion", "restart", "status_update") else None
            else:
                d = _on_date(t, a, z)
            if d:
                r["event_date"] = d
                break
        if not r["event_date"] and st == "underway" and et in ("construction_progress", "expansion", "restart"):
            for t in sents[:15]:
                if re.search(r"(?i)\b\d{1,3}(?:\.\d)?\s?%\s+(?:complete|completed)|\bprogress\b", t) and not _BACKGROUND.search(t):
                    d = _asat(t)
                    if d:
                        r["event_date"] = d
                        break
        if not r["event_date"] and st == "achieved" and c["sent"] == 0 and et in _FAMILY:
            for t in sents[:5]:
                if re.search(_FAMILY[et], t) and not _BACKGROUND.search(t):
                    d = _on_date(t)
                    if d and d != T._dateline(b):
                        r["event_date"] = d
                        break
        if et == "incident":
            r["incident_kind"] = _incident_kind(s)
        if et in ("contract", "offtake", "shipment", "construction_start", "construction_progress", "expansion"):
            cp_src = [s] + [t for t, a, z, st2 in c.get("support", [])] + ([h] if c["sent"] else [])
            if et in ("contract", "offtake", "shipment"):
                cp_src += sents[:6]
            r["counterparty"] = _counterparty(cp_src, issuer)
        if et in ("suspension", "care_maintenance", "restart"):
            cm = re.search(r"(?i)\b(?:due\s+to|in\s+response\s+to|as\s+a\s+result\s+of|because\s+of|following)\s+([^.;,]{4,80})", s[lo:])
            r["cause"] = cm.group(1).strip() if cm else None
        figs = []
        nb = []
        if et in FIG_ORDER and fig_row.get(mk(c)) is c:
            mw = [w for w in re.findall(r"[A-Za-z\u00c0-\u00ff]{4,}", c["mine"] or "") if w.lower() not in ("mine", "project", "property", "gold",
                                                                                               "silver", "copper", "complex")]
            allt = [h] + sents[:40]
            one_mine = len({PN.key(x["mine"]) if x["mine"] else None for x in cands}) == 1 and len(proj_list) <= 1
            for j in range(c["sent"] + 1, len(allt)):
                t = allt[j]
                named = mw and any(w.lower() in t.lower() for w in mw)
                if one_mine and j <= 25 and not re.search(r"(?i)\b(?:since|to\s+date|life[\s-]of[\s-]mine|LOM|historic\w*|annual\w*|per\s+"
                                                         r"(?:year|annum)|reserves?|resources?|cumulative)\b", t):
                    named = True                            # one mine in the release: its lead sentences are about it
                keyw = re.search(r"(?i)\b(?:shipment|shipped|throughput|tpd|recover\w*|poured|produced|produces|production|mined|ramp\w*|"
                                 r"generated?|averag\w+|loads?|departed|delivered)\b", t)
                if not keyw or len(t) > 600 or len(re.findall(r"\d[\d,.]*", t)) > 12:
                    continue                                # a table flattened into one line
                if j <= c["sent"] + 3 or named:
                    if not _BACKGROUND.search(t) and not re.search(r"(?i)\b(?:guidance|outlook|forecast|expected\s+to|will|budget(?:ed)?\s+"
                                                                   r"for|target(?:ed|s)?|plan(?:ned)?\s+to)\b", t[:120]):
                        nb.append((t, 0, 0))
        for t, a, z in (places + nb if et not in FIG_ORDER or fig_row.get(mk(c)) is c else places[:1]):
            for f in _figures(et, t):
                if not any(g["metric"] == f["metric"] for g in figs):
                    figs.append(f)
        if c is build_row:
            if capex:
                r["capex"], r["capex_high"] = capex["value"], capex["value_high"]
                r["capex_currency"], r["capex_basis"] = capex["currency"], capex["basis"]
            if pct is not None and et in ("construction_progress", "expansion", "restart", "commissioning", "construction_start",
                                          "commercial_production"):
                r["pct_complete"] = pct
        if figs:
            import json as _json
            r["figures_json"] = _json.dumps(figs, sort_keys=True)
        r["evidence"] = s[max(0, lo - 60):hi + 80][:300]
        res["rows"].append(r)
    return res


_CP_NAME = r"((?:[A-Z][\w&.'\u00C0-\u00ff\-]*|de|del|la|y)(?:\s+(?:[A-Z][\w&.'\u00C0-\u00ff\-]*|de|del|la|y|AG|LLC|SA|S\.A\.)){0,5})"
_CP = [re.compile(r"\b(?:agreement|contract|term\s+sheet|arrangement|MOU|memorandum|deal|partnership|joint\s+venture)\s+(?:\w+\s+){0,2}?with\s+"
                  r"(?:its\s+(?:partner|contractor)\s+)?" + _CP_NAME),
       re.compile(r"\bbetween\s+[^.;]{2,60}?\s+and\s+" + _CP_NAME),
       re.compile(_CP_NAME + r"\s+(?:was|has\s+been|have\s+been)\s+(?:awarded|selected|appointed|engaged|contracted|retained)\b"),
       re.compile(r"\b(?:awarded|awards)\s+(?:\w+\s+){0,5}?to\s+" + _CP_NAME),
       re.compile(r"(?i:\b(?:shipment|concentrate|cargo)\b[^.;]{0,60}?\bto\s+)" + _CP_NAME),
       re.compile(r"\b(?:and|with)\s+" + _CP_NAME + r"\s+(?:commence|begin|start)\w*\s+construction"),
       re.compile(r"\b(?:partnership|partnering|partners?)\s+(?:with,?\s+)?(?:(?:one|some)\s+of\s+[^,]{5,80},\s+)?" + _CP_NAME),
       re.compile(r"\b(?:appointment|appointed|appoints|selection|selected|engaged|engagement)\s+(?:of\s+)?" + _CP_NAME +
                  r"(?=[^.;]{0,120}\bcontractor\b)")]
_CP_BAD = re.compile(r"(?i)^(?:the|a|an|its|our|this|that|these|each|all|both|company|corporation|government|ministry|province|state|"
                     r"project|mine|board|management|we|it|us)\b|^(?:January|February|March|April|May|June|July|August|September|October|"
                     r"November|December|Q[1-4])\b")


def _counterparty(texts, issuer):
    """Who the contract, offtake or shipment is with - a name as the release writes it, never the issuer itself."""
    iw = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", issuer or "")} - {"resources", "mining", "metals", "gold", "silver", "corp"}
    for t in texts:
        hits = sorted(((m.start(m.lastindex), m) for rx in _CP for m in rx.finditer(t)), key=lambda x: x[0])
        for _, m in hits:
            n = m.group(m.lastindex)
            if t.isupper() or sum(ch.isupper() for ch in t) > 0.6 * sum(ch.isalpha() for ch in t):
                n = re.split(r"\s+(?:AT|FOR|IN|OF|TO|A|AN|THE|ON|WITH|AND|FROM|AS)\b", n)[0]
            n = re.sub(r"\s+(?:de|del|la|y)$", "", n.strip(" .,'\u2019"))
            if len(n) < 3 or _CP_BAD.search(n) or n.isupper() and len(n) > 30:
                continue
            nw = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", n)]
            if iw and nw and (nw[0] in iw or set(nw) <= iw):
                continue
            return n
    return None


def _incident_kind(s):
    t = s.lower()
    for k, rx in (("fatality", r"fatal|died|passed\s+away|death"), ("weather", r"wildfire|forest\s+fire|bush\s*fire|evacuat|storm|hurricane|"
                                                                               r"flood|rain"),
                  ("fire", r"\bfire\b|explosion"), ("geotechnical", r"collapse|rockburst|seismic|pit\s+wall"),
                  ("labour", r"strike|union|labou?r|stoppage"), ("community", r"blockade|protest|illegal\s+min|community"),
                  ("security", r"security|police|armed|attack|abduct"), ("injury", r"injur"), ("environmental", r"spill|tailings")):
        if re.search(rx, t):
            return k
    return "other"


# ------------------------------------------------------------------ records
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["rows"]:
        return [F.Record(KIND, facts=[F.Fact("is_event", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"] or "none")], confidence=0.0)]
    out = []
    for r in a["rows"]:
        fs = [F.Fact("is_event", value_num=1.0)]
        for k in TXT_FIELDS:
            v = r.get(k)
            if v not in (None, ""):
                fs.append(F.Fact(k, value_text=str(v)[:300]))
        for k in NUM_FIELDS:
            v = r.get(k)
            if v is not None:
                fs.append(F.Fact(k, value_num=float(v)))
        out.append(F.Record(KIND, facts=fs, confidence=1.0))
    return out


def parse_records(rows_by_ordinal):
    """{ordinal: [(field, seq, value_num, value_text)]} -> the analyse()-shaped dict."""
    import json as _json
    rows = []
    for ordinal in sorted(rows_by_ordinal):
        r = {k: None for k in TXT_FIELDS + NUM_FIELDS}
        yes = False
        for field_, seq, num, text in rows_by_ordinal[ordinal]:
            if field_ == "is_event":
                yes = num == 1.0
            elif field_ in TXT_FIELDS:
                r[field_] = text
            elif field_ in NUM_FIELDS:
                r[field_] = num
        if yes and r["event_type"]:
            r["figures"] = _json.loads(r["figures_json"]) if r.get("figures_json") else []
            r["capex_obj"] = ({"value": r["capex"], "value_high": r["capex_high"], "currency": r["capex_currency"],
                               "basis": r["capex_basis"]} if r.get("capex") is not None else None)
            rows.append(r)
    return {"is_event": bool(rows), "rows": rows}


JUDGED = ("event_type", "mine", "status", "event_date", "pct_complete", "incident_kind", "counterparty")


def to_prediction(records):
    if not records:
        return None
    rows = {i: [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts] for i, rec in enumerate(records)}
    p = parse_records(rows)
    if not p["rows"]:
        return None
    return {"rows": [dict({k: r.get(k) for k in JUDGED}, figures=r["figures"], capex=r["capex_obj"]) for r in p["rows"]]}


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
    lead = "Toronto, Ontario, March 2, 2026 -- ABC Gold Corp. (TSX: ABC) (\"ABC\" or the \"Company\") "

    def rows(h, b, keys=("event_type", "status", "mine")):
        return [tuple(r[k] for k in keys) for r in analyse(h, lead + b + fill)["rows"]]

    eq("first gold pour", rows("ABC Gold Announces First Gold Pour at the Alpha Mine",
                               "is pleased to announce the first gold pour at its Alpha Mine on February 27, 2026.",
                               ("event_type", "status", "mine", "event_date")),
       [("first_production", "achieved", "Alpha Mine", "2026-02-27")])
    eq("commercial production", rows("ABC Gold Declares Commercial Production at the Alpha Mine",
                                     "has declared commercial production at the Alpha Mine effective March 1, 2026."),
       [("commercial_production", "achieved", "Alpha Mine")])
    eq("construction update with % and capex",
       [(r["event_type"], r["status"], r["pct_complete"], r["capex"], r["capex_currency"]) for r in
        analyse("ABC Gold Provides Construction Update on the Alpha Project",
                lead + "is pleased to provide a construction update on the Alpha Project. Overall construction is 64% complete. "
                "The initial capital cost of US$250 million remains on budget." + fill)["rows"]],
       [("construction_progress", "underway", 64.0, 250000000.0, "USD")])
    eq("suspension", rows("ABC Gold Temporarily Suspends Operations at the Alpha Mine",
                          "has temporarily suspended operations at the Alpha Mine due to a wildfire in the region."),
       [("suspension", "achieved", "Alpha Mine")])                  # headline only: the wildfire is its cause
    eq("restart planned with a date", rows("ABC Gold Closes Financing to Restart the Alpha Mine",
                                           "has closed a C$5 million financing to fund the restart of the Alpha Mine, "
                                           "which is expected to restart in Q3 2026.", ("event_type", "status", "event_date")),
       [("restart", "planned", "2026-Q3")])
    eq("restarting drilling is not a mine restart",
       rows("ABC Gold Restarts Drilling at the Alpha Project", "has restarted its drilling program at the Alpha Project."), [])
    eq("commissioning a report is not commissioning",
       rows("ABC Gold Commissions NI 43-101 Technical Report", "has commissioned an independent technical report."), [])
    eq("pilot plant is not a row (rule DP)",
       rows("ABC Gold Commissions Pilot Plant", "has successfully commissioned its pilot plant at the testing lab."), [])
    eq("along strike is not a strike", rows("ABC Gold Extends Mineralization Along Strike at the Alpha Project",
                                            "drilling has extended mineralization 500 metres along strike."), [])
    eq("an appointment is not a row", rows("ABC Gold Appoints Chief Operating Officer",
                                           "has appointed Jane Doe as Chief Operating Officer. Ms. Doe led the construction of "
                                           "the Beta Mine."), [])
    eq("target dates", [_target_date(x) for x in ("in Q2 2027", "second half of 2022", "by the end of 2028", "in June 2026",
                                                  "during 2026", "early 2027")],
       ["2027-Q2", "2022-H2", "2028-Q4", "2026-06", "2026", "2027-H1"])
    recs = extract("ABC Gold Announces First Gold Pour at the Alpha Mine",
                   lead + "is pleased to announce the first gold pour at its Alpha Mine on February 27, 2026." + fill)
    p = to_prediction(recs)
    eq("round trip", [(x["event_type"], x["status"], x["mine"]) for x in p["rows"]], [("first_production", "achieved", "Alpha Mine")])
    eq("no-event record", to_prediction(extract("ABC Gold Closes Private Placement", lead + "has closed a private placement." + fill)), None)
    # 1.0.1 (2026-09-30): false events, one event one row, status from the headline's wording, wider headline capture
    eq("green light only as an approval", (rows("Greenlight Minerals Announces Results of Annual Meeting", "announces the voting results."),
                                           rows("ABC Gold Receives Green Light to Build the Alpha Mine",
                                                "has received the green light from its board to build the Alpha Mine.")),
       ([], [("construction_decision", "achieved", "Alpha Mine")]))
    eq("the issuer's own name is not an event",
       [r["event_type"] for r in analyse("First Spodumene Announces New Gold Discovery at the Alpha Project",
                                         "Vancouver, March 2, 2026 -- First Spodumene Minerals Corp. (TSXV: FSP) (the \"Company\") announces a "
                                         "new gold discovery from sampling at the Alpha Project." + fill)["rows"]], [])
    eq("ramping up drilling is not a ramp-up", (rows("ABC Gold Ramps Up Drilling at the Alpha Project", "has added two drill rigs."),
                                                rows("ABC Gold Ramps Up Production at the Alpha Mine",
                                                     "continues to ramp up production at the Alpha Mine mill.")),
       ([], [("ramp_up", "underway", "Alpha Mine")]))
    eq("land and programs are not an expansion", (rows("ABC Gold Announces Significant Expansion of the Alpha Property by Option",
                                                       "has optioned ten claims next to the Alpha Property."),
                                                  rows("ABC Gold Updates on its 9,055 Hectare Expansion of the Alpha Complex",
                                                       "has acquired new claims."),
                                                  rows("ABC Gold Advances With 3,200-Metre Phase Four Expansion Program",
                                                       "will drill 3,200 metres at the Alpha Project.")), ([], [], []))
    eq("restart of fieldwork or a study is not a restart", (rows("ABC Gold Announces Restart of Fieldwork in Peru", "has restarted field work."),
                                                            rows("ABC Gold Restarts Work on the Preliminary Economic Assessment",
                                                                 "has restarted work on the PEA for the Alpha Project.")), ([], []))
    eq("a first-in-region project is not first production",
       rows("ABC Gold Acquires the Beta Project - Ontario's First Lithium Brine Project", "has acquired the Beta Project."), [])
    eq("a property sale and a forward sale are not offtakes",
       (rows("ABC Gold Announces Termination of Sales Agreement with XYZ for the Alpha Property", "has terminated the property sale."),
        rows("ABC Gold Provides Update for its Uranium Forward Sales Agreement", "received funds under its forward sales agreement.")), ([], []))
    eq("a supply deal without a mine, plant or product of its own",
       [r["event_type"] for r in analyse("XYZ Wins Long Term Supply Agreement for Solar Power Solutions",
                                         "Toronto, March 2, 2026 -- XYZ Corp. (CSE: XYZ) announces a long term supply agreement for solar "
                                         "power solutions with a development agency.")["rows"]], [])
    eq("a contract to sell product is an offtake",
       rows("ABC Gold Awarded Contract to Sell $18.5 Million of Uranium from the Alpha Mill", "has been awarded a contract to sell uranium."),
       [("offtake", "achieved", "Alpha Mill")])
    eq("mine names from table text or verb phrases", [_clean_name(x) for x in ("Cash 16.1 6.7 Inventories 8.4 18.3 Property",
                                                                            "Drawdown of Alpha Mine", "Beta Lithium Presents Project",
                                                                            "Only Producing Graphite Mine", "Place Gamma Mine")],
       [None, "Alpha Mine", None, None, "Gamma Mine"])
    eq("a contractor's name is not a mine", (_company_like("XYZ Mine", "awarded to XYZ Mine Repair and Maintenance. XYZ Mine Repair will"),
                                             _company_like("Alpha Mine", "the Alpha Mine Expansion at the Alpha Mine.")), (True, False))
    eq("financing for an expansion", (rows("ABC Gold Draws Down US$40 Million Loan for the Phase 2 Expansion of the Alpha Mine",
                                           "has drawn US$40 million under its loan."),
                                      rows("ABC Gold Draws Down US$40 Million Loan for the Phase 2 Expansion of the Alpha Mine",
                                           "has drawn US$40 million under its loan. Construction of the Phase 2 Expansion is well underway.")),
       ([], [("expansion", "underway", "Alpha Mine")]))
    eq("study and design work is not a build", (rows("ABC Gold Completes Tailings Storage Facility Design", "has completed the design work."),
                                                rows("ABC Gold PEA Supports Alpha Mine Expansion Plan", "announces the results of a PEA."),
                                                rows("ABC Gold Commenced FEED on the Alpha Sulphide Project", "has commenced FEED work.")), ([], [], []))
    eq("a wildfire pause of exploration is not an incident",
       (rows("ABC Gold Responds to Forest Fires near the Alpha Project", "has temporarily suspended its exploration activities at the Alpha "
                                                                         "Project as a precaution."),
        rows("ABC Gold Provides Update on Wildfire at the Alpha Project", "has evacuated its camp and crews and suspended field work at the "
                                                                          "Alpha Project.")),
       ([], [("incident", "achieved", "Alpha Project")]))
    eq("no damage and relief pledges", (rows("No Damage from Earthquake to ABC Gold's Alpha Mine", "reports no damage."),
                                        rows("ABC Gold Commits US$1 Million to Support Earthquake Relief Efforts", "will donate funds.")), ([], []))
    eq("one expansion, one row", rows("ABC Gold Announces Groundbreaking for Phase III Expansion of the Alpha Mine",
                                      "held a groundbreaking for the Phase III expansion of the Alpha Mine."), [("expansion", "achieved", "Alpha Mine")])
    eq("a fatal accident is an incident, not the shaft", [r[0] for r in rows("Rescue and Recovery Operations in Shaft 1 at the Alpha Project Completed",
                                                                            "three workers died after a kibble accident in Shaft 1.")],
       ["incident"])
    eq("remediation after a seismic suspension is not site cleanup",
       [r[0] for r in rows("Mining at the Alpha Mine Suspended; Remediation Work Continues", "suspended mining after seismic activity.")],
       ["suspension"])
    eq("headline events the reader missed", (rows("ABC Gold Announces Alpha Construction Nears Completion", "construction continues."),
                                            rows("ABC Gold Returns to Full Construction at the Alpha Mine", "has resumed all site activities."),
                                            rows("ABC Gold Completes Process Plant Performance Test at the Alpha Mine", "completed the test."),
                                            rows("ABC Gold Contracts XYZ Water to Install a Plant at the Alpha Mine", "has contracted XYZ Water.")),
       ([("construction_progress", "underway", None)], [("restart", "achieved", "Alpha Mine")], [("commissioning", "achieved", "Alpha Mine")],
        [("contract", "achieved", "Alpha Mine")]))
    eq("status from the headline's wording", (rows("ABC Gold Initiates Alpha Mill Expansion", "has started work on the mill expansion."),
                                              rows("ABC Gold Reports Q3 Results; Phase II Expansion Remains on Track for Completion by Mid-2027",
                                                   "reports its results."),
                                              rows("ABC Gold Readies Third Shipment of Concentrate from the Alpha Mine by October 20",
                                                   "will deliver the concentrate."),
                                              rows("ABC Gold Starts Laying Track at the Alpha Mine Portal", "is laying track in the portal.")),
       ([("expansion", "underway", "Alpha Mill")], [("expansion", "underway", None)], [("shipment", "planned", "Alpha Mine")],
        [("infrastructure", "underway", "Alpha Mine")]))
    eq("routine maintenance, court and permit items", (rows("ABC Gold Completes Annual Plant Maintenance Shutdown at the Alpha Mine",
                                                            "completed its annual plant maintenance shutdown on schedule."),
                                           rows("Community Appeals Dismissal of Petition on the Alpha Mine Tailings Storage Facility Raise",
                                                "has filed a notice of appeal."),
                                           rows("ABC Gold Receives Approval of its EIA for the Construction of the Substation at the Alpha Project",
                                                "has received the environmental approval.")), ([], [], []))
    eq("names with accents or one short word", (_core_in("Espigao Project", "production from the Espig\u00e3o d'Oeste operation"),
                                                _core_in("Mon Gold Mine", "RESTART OPERATIONS AT THE MON GOLD MINE"),
                                                _core_in("Mon Gold Mine", "restart operations at the mine")), (True, True, False))
    xh = "ABC Gold Announces 2027 Guidance; Mine and Mill Throughput Expansion from 3,500 to 4,200 Tonnes per Day to be Completed in 2027"
    eq("a named mine's ramp-up; an expansion still to be completed",
       (rows("ABC Gold Accelerates Alpha Ramp-Up", "reports a ramp-up in activity at the Alpha Mine."),
        _status("expansion", xh, xh.index("Expansion"), xh.index("Expansion") + 9, True)),
       ([("ramp_up", "underway", "Alpha Mine")], "planned"))
    eq("a forest fire that interrupted the company's shipping is an incident",
       [r[0] for r in rows("ABC Gold Announces Resumption of Rail Services Following Interruptions Due to Forest Fires",
                           "announces that rail services from its Alpha Mine have resumed.")], ["restart", "incident"])
    eq("a shipment's source: the one project the body says the product is produced at",
       rows("ABC Lithium Loads 20,000 Tonne Shipment of Concentrate to XYZ",
            "announces that it will load 20,000 tonnes of concentrate to XYZ at the port. XYZ will prepay half of the cargo. The "
            "cargo shows the steady performance of the plant. Its concentrate is produced at its plant at its Alpha Project in Brazil."),
       [("shipment", "achieved", "Alpha Project")])
    # 1.0.1 full-text fix (2026-10-01): what the whole release text showed
    hi_ = "HIGHLIGHTS: 130,000 metres of drilling is underway since the 2024 Updated Feasibility Study was published. "
    eq("a study the lead mentions is a side item when the headline's milestone is done",
       (rows("ABC Gold Achieves First Gold Pour at its Alpha Mine on Budget", hi_ + "announces the first gold pour at the Alpha Mine."),
        rows("Alpha Mine Underground Development Exceeds 1,840 Metres in August", hi_ + "reports 1,842 metres of underground development."),
        rows("ABC Gold PEA Supports Alpha Mine Expansion Plan", hi_ + "announces the results of a PEA.")),
       ([("first_production", "achieved", "Alpha Mine")], [("infrastructure", "underway", "Alpha Mine")], []))
    eq("a hazard that stood down staff, stopped operations or damaged the site is an incident",
       ([r[0] for r in rows("ABC Gold Takes Precautionary Measures due to Wildfires", "has temporarily reduced the number of non-essential "
                                                                                     "staff and contractors at the Alpha Mine.")],
        [r[0] for r in rows("ABC Gold Provides Update on Forest Fire Situation", "advises that operations at the Alpha Mine site have been "
                                                                                 "suspended and staff withdrawn.")],
        [r[0] for r in rows("ABC Gold Comments on Wildfire Situation", "reports that its storage site at the Alpha Project was damaged by "
                                                                       "the wildfires.")],
        rows("ABC Gold Comments on Wildfire Situation", "reports that the wildfires caused no damage to the Alpha Project.")),
       (["incident"], ["incident", "suspension"], ["incident"], []))   # 1.0.2: the stop the hazard caused is its own row
    eq("a decision or an update in a financing headline",
       (rows("ABC Gold Closes US$75 Million Project Financing and Announces Construction Decision for the Alpha Project",
             "has closed the financing."),
        rows("ABC Gold Closes Third Tranche of Construction Facility and Provides Construction Update",
             "has closed the tranche, and we report that installation of the mill continues."),
        rows("ABC Gold Announces Private Placement Securing Sufficient Funding to Construction Decision", "has arranged a placement.")),
       ([("construction_decision", "achieved", "Alpha Project")], [("construction_progress", "underway", None)], []))
    eq("ramp-up objects: phase, stage, expansion, commercial production, a named project",
       ([r[0] for r in rows("ABC Gold Reports Q3 Results; Phase Two Ramp Up Advancing", "reports its results.")],
        [r[0] for r in rows("ABC Gold Reports Q2 Results and Significant Stage 3 Expansion Ramp-Up Progress", "reports its results.")],
        [r[0] for r in rows("ABC Gold Reports Q3 Production, Driven by Successful Ramp-Up of Alpha", "reports production at the Alpha Mine.")],
        rows("ABC Gold Field Programs Ramp-Up at the Alpha Project", "has started field work."),
        rows("ABC Gold Announces Ramp-Up of Alpha Evaluation Activities in 2026", "will test the Alpha Mine.")),
       (["ramp_up"], ["ramp_up"], ["ramp_up"], [], []))
    eq("a permit headline whose sub-headline says construction started",
       [r[0] for r in rows("ABC Gold Receives Permits for Second Portal Accessing the Alpha Deposit Construction Started",
                           "has received the permits; construction of the portal at the Alpha Mine has already begun.")], ["construction_start"])
    eq("the company's own product or projects",
       ([r["event_type"] for r in analyse("XYZ Signs Multi-Year Supply Agreement", "Calgary, March 2, 2026 -- XYZ Corp. (TSXV: XYZ) (the \"Company\") "
                               "has entered into a multi-year supply agreement for its metakaolin. The metakaolin will be sourced from its "
                               "recently upgraded Beta facility." + fill)["rows"]],
        [r["event_type"] for r in analyse("XYZ Signs Non-Binding Offtake MOU with a Steel Maker", "Vancouver, March 2, 2026 -- XYZ Corp. (CSE: XYZ) (the "
                               "\"Company\") has executed a non-binding MOU for long-term supply. The agreement will be subject to an "
                               "investment into the development of one or more of its projects." + fill)["rows"]]),
       (["offtake"], ["offtake"]))
    eq("development work and suspensions outside exploration",
       ([r[0] for r in rows("ABC Gold Announces Resumption of Planned Site Activities at the Alpha Gold Project",
                            "announces the resumption of planned site activities at its Alpha Gold Project following a temporary suspension. "
                            "Personnel onsite support pre-construction, early works and exploration drilling activities.")],
        [r[0] for r in rows("ABC Gold Announces Temporary Suspension of Activities in Quebec",
                            "is temporarily suspending exploration and development activities at its Alpha Complex. The Alpha Complex "
                            "has a 930 metre shaft and a 2,000 tonne per day mill.")]),
       (["restart"], ["suspension"]))
    eq("a starter operation is not a plant name; a shaft sunk to final depth",
       (rows("ABC Gold Secures US$45 Million Loan to Fund Heap Leach Starter Operation; Board of Directors Approves Construction Decision",
             "has executed a gold loan."),
        rows("Alpha Successfully Completes Sinking of Shaft 1 to its Final Depth of 1,000 Metres", "completed the sinking of Shaft 1 at "
             "the Alpha Mine.")),
       ([("construction_decision", "achieved", None)], [("infrastructure", "achieved", "Alpha Mine")]))
    # 1.0.2 (2026-10-02): capture kinds from the ACC150b re-check
    eq("new incident wordings: fall of ground, employees strike, heavy rains that halted processing, a leach pad slip",
       ([r[0] for r in rows("ABC Gold Provides Update on Fall of Ground Incident at the Alpha Mine", "provides an update on the fall of "
                            "ground incident at the Alpha Mine on March 1, 2026.")],
        [r[0] for r in rows("Unionized employees strike at Alpha mine", "announces that unionized employees at its Alpha mine today "
                            "initiated a strike.")],
        [r[0] for r in rows("ABC Gold Provides Update on Heavy Rains in Chile No injuries reported", "is providing an update on its Alpha "
                            "Mine. The rains caused water accumulation in the pit, halting the processing of ore.")],
        [r[0] for r in rows("ABC Gold Provides Update on Heavy Rains", "reports heavy rains near the Alpha Mine with no impact on "
                            "operations.")]),
       (["incident"], ["incident"], ["incident", "suspension"], []))
    eq("an update following a fire is the fire's row", [r[0] for r in rows("ABC Gold Provides Update Following Fire at the Alpha Mine Crusher",
                                                                           "provides an update on the fire at its Alpha Mine.")], ["incident"])
    eq("start of plant operations, custom milling, contract mining, leach pad expansion, infrastructure milestones",
       (rows("ABC Gold Announces Alpha Gold Mine Start of Process Plant Operations", "announces the start of operations of the process plant."),
        [r[0] for r in rows("ABC Gold Announces a Custom Milling Contract with XYZ Mining for its Alpha Bulk Sample", "has signed a custom "
                            "milling contract with XYZ Mining Corp.")],
        [r[0] for r in rows("ABC Gold Signs Contract Mining Agreement for the Alpha Mine", "has signed a contract mining agreement.")],
        rows("ABC Gold Provides Operations Update; Alpha Phase 2 Pad Expansion Preparations Underway", "provides an update."),
        [r[0] for r in rows("ABC Gold Announces Completion of Major Processing Plant Infrastructure Milestones", "has completed the conveyor "
                            "at its Alpha Plant.")]),
       ([("commissioning", "achieved", "Alpha Gold Mine")], ["contract"], ["contract"], [("expansion", "underway", None)],
        ["construction_progress"]))
    eq("a first concentrate agreement is an offtake, not first production",
       [r[0] for r in rows("ABC Gold Signs First Gold Concentrate Agreement with XYZ Partners", "has signed an offtake agreement for the "
                           "gold concentrate of its Alpha Mine.")], ["offtake"])
    eq("a commissioning update after a guidance clause is under way",
       rows("ABC Gold Announces Q1 EBITDA Guidance of US$52 Million/ Alpha South Commissioning Update",
            "provides an update. Commissioning of the Alpha South processing plant is progressing well.", ("event_type", "status")),
       [("commissioning", "underway")])
    eq("a planned headline event whose target date is in the lead; an immediate restart",
       (rows("ABC Energy Achieves Milestone to Recommence Uranium Production at the Alpha Mill", "submitted its reactivation plan. The "
             "Company is targeting the mill restart in 2027.", ("event_type", "status", "event_date")),
        rows("ABC Gold Completes US$240 Million Term Loan to Advance Alpha Toward Final Investment Decision", "has completed a term loan. "
             "A final investment decision is expected in mid-2027.", ("event_type", "status")),
        rows("ABC Gold to Restart Operations under Government Order", "is pleased to report the order. The Company will immediately "
             "implement a phased restart at the Alpha Mine.", ("event_type", "status"))),
       ([("restart", "planned", "2027")], [("construction_decision", "planned")], [("restart", "planned")]))
    eq("an incident's stop and a stop's incident (one row each)",
       (rows("ABC Gold Reports Contractor Fatality at the Alpha Gold Project", "regrets to report a fatal accident at the Alpha Gold "
             "Project. Activities at the Project have been temporarily suspended to allow for an investigation."),
        rows("ABC Gold Announces Suspension of Operations at Alpha", "announces a suspension of operations at the Alpha mine as a result "
             "of a large slip on the heap leach pad."),
        [r[0] for r in rows("ABC Gold Reports Fatality at the Alpha Mine", "regrets to report a fatality. Operations were not suspended.")]),
       ([("incident", "achieved", "Alpha Gold Project"), ("suspension", "achieved", "Alpha Gold Project")],
        [("suspension", "achieved", "Alpha Mine"), ("incident", "achieved", "Alpha Mine")], ["incident"]))
    eq("a resolved labour action is a restart",
       rows("ABC Gold Resolves Labour Action at the Alpha Mine", "is pleased to report the resolution of the labour action at the Alpha "
            "Mine and the expected resumption of operations later today."), [("restart", "planned", "Alpha Mine")])
    eq("a construction update at a mine being brought back is the restart",
       (rows("ABC Silver Provides Construction Update at the Alpha Property", "is pleased to provide an update from the Alpha mine. "
             "Rehabilitation is in its final stages. We expect to bring the mine and plant back online in the coming weeks.",
             ("event_type", "status")),
        rows("ABC Silver Provides Update on Permitting and Construction Progress at the Alpha Mine", "is pleased to provide an update. "
             "Construction activities associated with a restart of the mine continue while permitting advances.", ("event_type", "status"))),
       ([("restart", "underway")], [("restart", "planned")]))
    eq("a dated target in the headline is its own row",
       rows("ABC Gold Begins Commissioning at Alpha; Production Expected to Commence in Q3 2026", "has begun commissioning at its Alpha "
            "Mine.", ("event_type", "status", "event_date")),
       [("commissioning", "underway", None), ("first_production", "planned", "2026-Q3")])
    eq("a target in a progress update is its next target; 'Gold and Silver Project' is one name",
       ([r[0] for r in rows("ABC Gold Provides Q2 Update on Alpha Mine Construction Progress; 87% Complete and on Schedule to Pour First "
                            "Gold in Q4 2026", "provides an update. Construction of the mill is 87% complete.")],
        [r[2] for r in rows("ABC Gold Provides Construction Update on the Alpha Balabag Gold and Silver Project", "provides an update. "
                            "Construction of the mill is 87% complete.")]),
       (["construction_progress"], ["Alpha Balabag Gold and Silver Project"]))
    eq("a COVID notice with operations suspended",
       [r[0] for r in rows("ABC Gold Provides Notification of Two Positive Covid-19 Cases at Alpha Operations", "was informed of two "
                           "positive cases. As a result, the Company is temporarily suspending operations until test results are received.")],
       ["suspension"])
    eq("names: lower-case mine word, country operations, two mines, a listed region",
       ([r[2] for r in rows("Unionized employees strike at Tasiast mine", "announces that unionized employees at its Tasiast mine today "
                            "initiated a strike.")],
        [_clean_name(x) for x in ("Bolivian Operation", "Barani Mine", "Raglan Mine", "South African Operations")],
        [r[2] for r in rows("ABC Gold Reports Q2 Results; First Gold Produced at Both Round Mountain Phase W and Bald Mountain Vantage "
                            "Complex Projects", "reports its results.")],
        rows("ABC Gold Provides Update on Resumption of Operations in Quebec", "provides an update. Mining activities will be permitted "
             "to resume beginning on April 15, 2026. Accordingly, the Company is taking steps to resume its operations (the Alpha Complex, "
             "the Beta mine and the Gamma mine).")),
       (["Tasiast Mine"], [None, "Barani Mine", "Raglan Mine", None], ["Round Mountain Phase W", "Bald Mountain Vantage Complex"],
        [("restart", "planned", "Alpha Complex"), ("restart", "planned", "Beta mine"), ("restart", "planned", "Gamma mine")]))
    eq("a generic headline's announced event; a dated recap is not news",
       ([r[0] for r in rows("ABC Gold Provides an Update on Greek Investments", "provides an update. The Company announces it will move the "
                            "Alpha development project into care and maintenance by Q2 2026.")],
        [r[0] for r in rows("ABC Gold Provides Q3 Operational Update", "provides an update. In August 2018, the Company commissioned its "
                            "phase 1 plant at the Alpha Mine.")]),
       (["care_maintenance"], []))
    eq("a generic headline: no first-person comment, no call for a suspension, no strike a restart ends; 'will be suspending'",
       ([r[0] for r in rows("ABC Gold Provides Q3 Operations Update", "provides an update. We are working to reach a construction "
                            "decision on the Alpha Project by the end of 2026.")],
        [r[0] for r in rows("ABC Gold Provides Update on Philippines Mining Operations", "provides an update. The regulator today issued "
                            "an order calling for the suspension of the Alpha operation.")],
        [r[0] for r in rows("ABC Gold Provides Post-Strike Production Update", "provides an update. Operations resumed at the Alpha Mine "
                            "on March 1, 2026 after 57 days of work stoppage as a result of the strike by unionized employees.")],
        rows("ABC Gold Provides Update on Alpha and Beta Operations", "today announced that it will be suspending operations at its "
             "Alpha Mine.", ("event_type", "status"))),
       ([], [], ["restart"], [("suspension", "planned")]))
    eq("ramping up as planned is under way", rows("ABC Gold Provides Update on Turkish Operations", "is pleased to report its Alpha "
                                                  "processing plant is ramping up as planned.", ("event_type", "status")),
       [("ramp_up", "underway")])
    # 1.0.3 (2026-10-04): commissioning wordings, the announcement's other milestones, retypes and refusals, status
    eq("commissioning wordings",
       (rows("ABC Gold's Alpha Project Awarded Operational License - Commissioning On Track for First Copper Production in Q3 2026",
             "has received the licence for the Alpha Project.", ("event_type", "status"))[:1],
        rows("ABC Gold Commissioning Silver Milling Circuit at the Alpha Mine", "is commissioning the circuit at the Alpha Mine.",
             ("event_type", "status")),
        rows("ABC Gold Provides an Update to Alpha Mine Commissioning", "provides an update.", ("event_type", "status")),
        rows("ABC Gold Commences Alpha Plant Commissioning", "has begun commissioning.", ("event_type", "status")),
        rows("ABC Gold Announces Alpha SX Plant Start-up", "announces the start-up of the plant.", ("event_type", "status"))),
       ([("commissioning", "underway")], [("commissioning", "underway")], [("commissioning", "underway")], [("commissioning", "underway")],
        [("commissioning", "underway")]))
    eq("commissioning and production ramp-up in one headline: the ramp-up's row",
       [r[0] for r in rows("ABC Gold Provides Update on Alpha Project Commissioning and Production Ramp Up", "provides an update on the "
                           "Alpha Project ramp-up.")], ["ramp_up"])
    eq("commissioning started is under way (not achieved by a construction completed before it)",
       rows("ABC Gold Completes Construction and Starts Wet Commissioning at the Alpha Mine", "provides an update. All significant "
            "construction is now complete.", ("event_type", "status")), [("commissioning", "underway")])
    eq("a strike suspended or settled ends the stop: a restart (planned until work resumes)",
       (rows("ABC Gold Announces Suspension of Strike at Alpha Mine", "announced that the strike by unionized employees at its Alpha mine "
             "has been suspended.", ("event_type", "status")),
        rows("ABC Gold Announces Settlement of Miners Strike at Alpha Mine", "has reached an agreement with the union at its Alpha Mine.",
             ("event_type", "status"))),
       ([("restart", "achieved")], [("restart", "planned")]))
    eq("restart statuses: a planned resumption, a restart project update",
       (rows("ABC Gold Announces Planned Resumption of Operations at the Alpha Mine", "plans to resume operations.", ("event_type", "status")),
        rows("ABC Gold Provides Mine Restart Project Update", "provides an update on the Alpha Mine restart.", ("event_type", "status"))),
       ([("restart", "planned")], [("restart", "underway")]))
    eq("not events: evaluating a restart (rule DV), a battery storage system, a clarification of an agreement",
       (rows("ABC Graphite to Evaluate Restart of Graphite Production at Alpha Mine", "will evaluate a restart."),
        rows("ABC Nickel Provides an Update on the Evaluation of a Toll Milling Restart", "continues its evaluation."),
        rows("XYZ Energy Announces Commissioning of New Flow Battery System in Hebei", "has commissioned a battery storage system."),
        rows("ABC Gold Provides Clarification on Ore Purchase Agreement with XYZ Partners", "clarifies the agreement for the Alpha Mine.")),
       ([], [], [], []))
    eq("an agreement signed for the construction of a facility is the contract",
       [r[0] for r in rows("ABC Gold Signs an Agreement with XYZ Power for the Engineering, Permitting and Construction of the Alpha Power Line",
                           "has signed the agreement.")], ["contract"])
    eq("the announcement's other milestones at the headline's mine; not one forecast to come",
       (rows("ABC Gold Announces the Start of Construction at the Alpha Gold Project", "is pleased to announce the start of construction "
             "at the Alpha Gold Project. The Company has awarded the earthworks contract to XYZ Civil Limited.", ("event_type", "status")),
        rows("ABC Gold Announces First Gold Pour at the Alpha Mine", "is pleased to announce the first gold pour at the Alpha Mine. "
             "Wet commissioning of the Alpha processing plant was completed recently.", ("event_type", "status")),
        rows("ABC Gold Announces First Gold Pour at the Alpha Mine", "is pleased to announce the first gold pour at the Alpha Mine. "
             "Commissioning of the Alpha oxide plant is forecasted to commence at the end of 2027.", ("event_type", "status"))),
       ([("construction_start", "achieved"), ("contract", "achieved")], [("first_production", "achieved"), ("commissioning", "achieved")],
        [("first_production", "achieved")]))
    eq("statuses: a completion percentage, a ramp-up beside another achievement, a blockade in place, a month target",
       (rows("Alpha Surpasses 50% Construction Completion", "reports progress at Alpha. Construction of the plant continues.",
             ("event_type", "status")),
        rows("ABC Gold Achieves Record Free Cash Flow as Alpha Ramp-up Drives Production Growth", "reports its results.",
             ("event_type", "status")),
        rows("ABC Gold Initiates Re-start of Operations at Alpha Mine: Blockade at Main Access Gate Remains in Place",
             "has initiated a restart.", ("event_type", "status")),
        rows("ABC Copper Announces Alpha SX Plant Start-up with First Copper Sales in September", "announces the start-up.",
             ("event_type", "status"))),
       ([("construction_progress", "underway")], [("ramp_up", "underway")], [("restart", "achieved"), ("incident", "underway")],
        [("commissioning", "underway"), ("shipment", "planned")]))
    eq("a forecast or target is never achieved",
       (rows("ABC Gold Announces Initial Shipment of Concentrate Targeted by End of 2026", "announces that the initial shipment of "
             "concentrate from the Alpha Mine is targeted by the end of 2026.", ("event_type", "status")),
        rows("ABC Gold Provides Update on the Alpha Mine", "provides an update. The Alpha mine operator has decided to temporarily place "
             "the mine on care and maintenance during April 2026.", ("event_type", "status"))),
       ([("shipment", "planned")], [("care_maintenance", "planned")]))
    eq("refusals: compensation for an earlier incident, a third party's power cut, a deposit's ramp-up activities, a site-access contractor",
       ([r[0] for r in rows("ABC Gold Announces Agreement for Compensation to Community Members Affected by the Incident at its Alpha Pile",
                            "has agreed to compensate members of the community.")],
        [r[0] for r in rows("ABC Gold Announces Temporary Suspension of Operations at Alpha due to Power Interruptions Caused by Forest Fires",
                            "has temporarily suspended operations at the Alpha Mine.")],
        rows("ABC Gold Provides Update on Alpha Gold Mill and Beta Gold Deposit Ramp-Up Activities", "provides an update."),
        rows("ABC Gold Selects Site Access Contractor for the Alpha Project", "has selected a contractor to build the site access.")),
       ([], ["suspension"], [], []))
    print("mine_dev: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test(verbose="-v" in sys.argv) else 0)
