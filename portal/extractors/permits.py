"""Permits & Approvals reader, facts-store version (PERMIT_V1, 2026-09-22).

The source of the Permits & Approvals page once it passes the accuracy gate. Written against the 50-item set Justin
confirmed on 2026-09-22 (41 items with rows, 73 rows).

The row shape and the rules are Justin's (2026-09-22):

  1. ONE ROW PER PERMIT or government approval an item reports: company, project, permit type, issuing authority,
     status, date, and term or expiry when stated. Types: drill/exploration, environmental assessment, plan of
     operations or notice, mining licence or lease, construction or operating, water, land access or community
     agreement, government or policy action, other.
  2. STAGES CHAIN across releases: planned -> applied -> in review -> granted, plus renewed (renewed, extended,
     amended) and contested (denied, revoked, suspended, challenged). A planned row is any permit the company names
     as still needed or says it will apply for.
  3. OUT OF SCOPE: stock exchange, shareholder, court and M&A approvals; mineral claims staked or registered;
     permits already held and mentioned in passing.
  4. An exploration-stage environmental approval that authorises drilling (a Peru DIA, a Mendoza EIR) is a drill
     permit; a BLM or USFS approval named with the permit is a plan of operations or notice.

analyse(headline, body) -> dict        full result (pure; no database, no clock)
extract(headline, body) -> [Record]    one record per row (ordinal 0..n-1)
to_prediction(records) -> dict|None    what the accuracy judge compares

The text helpers (normalising, sentence splitting) are the Technical Reports reader's.

1.0.2 (PERMIT_V2, 2026-09-24; Justin: "Can we look at fixing these", the 09-24 scope review): project names come from
the shared helper portal/project_names.py (answer-key project recall 85.2% -> 96.4%, precision 100%); a row whose
own sentence names no authority takes the one another sentence ties to a permit ("received the required permits
from the Saskatchewan Ministry of Environment"), never a federal agency for a provincial approval or the reverse
(authority recall 66.7% -> 80.5%, precision 100%); term and expiry are read from the row's other sentences and, in a
one-permit release, the body ("is valid for 3 years", "valid from September 1, 2024 to September 30, 2027"); new
holder (a subsidiary, former owner or title holder named as holding the permit) and scope (drill pads, platforms,
holes, wells, metres, hectares the permit allows) fields; a project being acquired is not the permit's project; a
headline mention that only inherited the release's main project joins the body row that names its own.

1.0.3 (JUR_V2, 2026-09-26; Justin: "Can we fix this", about 1 jurisdiction in 20 wrong, e.g. Ruby Creek shown as USA):
the jurisdiction rule, which Property Options also uses, no longer counts a place that belongs to something else -- a
US securities or newswire legend ("may not be offered or sold in the United States"), a ticker ("USA: STXPF"), a
currency, a listing, an office or incorporation, an address block, a company or other name ("Lithium Chile Inc.",
"Cerro Colorado", "Franco-Nevada", "1287398 BC Ltd.", "the University of Nevada", "the Business Corporations Act
(Ontario)"), a project named after a country (Benton's "Panama Project" in Ontario) -- nor anything after the company's
own "About ..." paragraph. "Located in ..." decides only in the headline or the first 3 sentences. Otherwise each
mention votes for its country and the answer is that country's most-named province or state. All-capitals headlines
are read; ", BC", "B.C." and some regions (Golden Triangle, Athabasca Basin, Red Lake, Timmins...) count; more states,
provinces and countries are known; one spelling per place ("USA", "Quebec", "Newfoundland and Labrador").

1.0.4 (JUR_ROW, 2026-09-26; Justin: "Fix this", a Permits row showed one place per release): a release that names
more than one project gives each row the place its own project's sentences name (a quarterly report's Goose water
licence is Nunavut, Canada, not Mali from the Fekola paragraphs); the release's place when those sentences name none,
or only the country the release already narrows to a province. A release naming one project is unchanged.

1.0.6 (READERFIX, 2026-09-30; the ACC150 measurement: rows right 81.7%, status 75%, and the outside-tag finds): rows
go on the project named in or next to the permit sentence -- a permit sentence that names its ground in lower case ("a
drill permit on its nearby X project"), the project an earlier sentence named with the same permit, the property a
target, zone or deposit sits in, never a neighbour ("adjoins", "borders") nor a name built from headline words ("...
to Help Finance Project", "Reviews Project Portfolio"); one permit is one row (a Record of Decision or FONSI folds into
the plan or statement it decides, a DIA/FTA or generic environmental permit into the drill permit it authorises, an
acronym the release defines is its permit, the same permit restated with the same quantities later without its
project is not copied onto the main project); background is dropped: permits already held ("pursuant to", "in place",
"grants the holder the exclusive right", "owing to receipt of", "its approved ..."), a permit named as a place ("the
northern zone of the mining permit"), the permit an application is made on, "further to" recaps, stages more than two
months (or a year) before the release, concessions, licences and water rights that come with a property deal, tickers,
an NCIB "Notice of Intention", an acronym the release defines as something else ("Earn-In Agreement (EIA)"), baseline
"environmental studies"; status: a refusal in other words or a permit before the courts is contested, a modification
is renewed, an application under review / deemed complete / at its final stage is in review, a grant the company is
waiting for is in review, a grant said not to have happened or a permitting process only started is planned, an
application only scheduled ("expected to submit") is planned, a renewal still pending is in review, an application
restated from earlier is in review; the stage date skips the date a release announced it; the dateline falls back to
the first date at the top. The jurisdiction rule Property Options borrows is unchanged (its code_sha does not move).

1.0.7 (OWN_NEWS, 2026-10-01; FIX2 after the outside-tag checks: rows right 72.5-79.7% on releases found without the
tag): the reader writes rows only for the release's own permit news. Never: a release by a company outside mining or a
newswire listing page; a Notice of Intention to exercise an option; claims staked or applied for, ground added or
mining rights bought; a stage of long ago (a year before 1990, "historic"); a grant the sentence sends the reader to an
earlier news release for; an assessment the work is excluded from. In a release whose headline names no permit (a deal,
a drill start, a financing, results, a corporate update), also not: the ground the company holds described ("consists
of", "comprises ... granted licences", "holds a 60% interest in", "under an active permit", "maintains all required
permits", "the company's three exploration licences", "the approved Plan of Operations providing for"), a permit "in
hand", "is approved for this area", "issued by" as a description, a grant quoted as earlier news or listed among past
milestones, the company boilerplate, an item of a numbered list of the company's holdings, an assessment among
technical work streams, "all permits", a hypothetical ("may be increased", "If a drill permit is received"), conditions
attached to something else, licences transferred to another company, a grant dated more than two months back, any
permit in a release that options out, sells or spins out the property, and a new officer's past work. Rows go on the
right ground: the ground named right after the permit ("an exploration license at <Name>") in such a release, the place
a sentence opens with ("At <Name>, ...", "<Name> - Received ...") or names in lower case ("for the <Name> operation"),
the place the passage just named when the release is about several projects, and the project a deposit, zone, prospect,
target, extension or claim block belongs to (the same name called a project, the one project the lead calls the
company's own, the place the headline ends on, or the release's only project); a permit document's qualifier ("Draft
Mine Plan of Operations") is no project; a short name's fullest form is never a part's. One row per permit: a Notice of
Intent that starts a mining-lease application is that application; an assessment filed for drill permits is the drill
permit (guide QD). Stages said in other words: a grant the company looks forward to is in review; one it makes a
condition ("following issuance of", "when approved, will allow") is planned; an application underway or being prepared
is planned; "has been submitted" beats plans named next to it; "has received a drilling permit required to start" is
granted; a modified or expanded permit is renewed; an amendment under review is in review; an assessment being advanced
or concluded is in review; a bare "reject" is contested; "extension of the exploration license" is renewed. "IBAS" is
no IBA; a word-processor bullet starts a sentence.

1.0.7 FIX3 (2026-10-01, same version; full-text losses fixed): on full release texts the 1.0.6/1.0.7 filters dropped
real tagged permit news. Now: an acronym the release defines by permit words this reader does not spell out
("Environmental Impact Authorization (EIA)", "Environment Impact Statement (EIS)", "(Declaracion Impacto Ambiental) (the
DIA)") stays that permit; "Further to its news release dated <date>, it has now received ..." is news (the cue refers to
the earlier release); Ministers who "have accepted the environmental assessment approval" decided it; "Completes <Land
Access> Agreement" is signed; Peru's "Authorization to Initiate (Exploration) Activities" is a drill permit, and a stage
word inside a permit's name is not its stage; a reclamation bond posted for an approved permit is that permit's news. Stages: "in the process of
receiving the grant" and "approved for admittance" are in review; "enabling application to <agency> for <permit>" is
planned; "Following receipt of <permit> in <earlier month>" is a past grant (the date checks decide), not a condition.
Background: the assessment something "was approved with"; a permit described as the subject of "provides/includes/
details" whose sentence has no stage word before it.

1.0.8 (FIX4, 2026-10-02; the ACC150b re-check: rows right 88.5%, status 78.9%, type 85.9%, and right rows the
1.0.6-1.0.7 fixes had lost): a stage word standing between two permits belongs to the nearer one within its clause ("the
LP, which has now been granted, followed by the installation license"; "the LI remains under suspension, the LP was
revalidated"), and an assessment whose only stage word went to another permit but which is being advanced is in review.
One permit named twice is one row: an assessment that is the drill permit's own form ("Environmental Impact Assessment -
Semi-detailed ("EIA-Sd") drill permit application"), the permit another one is for ("Environmental Clearance
Certificates for Exclusive Prospecting License 7071", "the LP for the Full Mining License"), an "FTA environmental
permit", the generic environmental permit an ESIA leads to, the assessment a project description or project notice
starts (guide QE: in review once filed). Rows kept apart: other permits still needed ("Environmental permits will be
required in advance of construction"), the next amendment of a permit held ("the next anticipated extension of the
current Plan of Operations"). Brazil's licences: Licenca Previa / LP (an assessment decision), License of Installation,
License of Operation / LO (LP and LO only where the release defines them; never a "social licence to operate").
Background: a grant "in the past" or "years ago", ground held described by what a licence covers, "permits in place" in
a headline, an agency's remit ("in charge of environmental permitting"), an agency named after a permit ("FAST-41
Permitting Council"), environmental and social studies. Whose ground: not a project named in a clause about earlier
news, not a region's portfolio ("<Province> Gold Projects"), no "Project Notice"; "Mt" is "Mountain". Stages: an
application still to be filed beats a grant anticipated after it; a fresh filing beats a grant the company looks forward
to; hopeful of receiving and an attributive "approved" in an expectation are awaited; a filed amendment is applied; a
permit expansion or amendment named as a noun is renewed (planned when proposed, in review when initiated); "extension
to a previously issued" permit is renewed; the approvals "remaining ... include", "future licensing", "is necessary",
"request of", "to be filed" are still to come; "challenging" as an adjective is no challenge; "permitting progressing"
is in review. Types: a mine permit is a mining licence (labels throughout), an Advanced Exploration Permit is an
exploration permit, a drill permit the BLM or US Forest Service approves is a plan of operations or notice (guide QA).

1.0.9 (FIX5, 2026-10-04; the ACC150c measurement: rows right 84.2% but under half the rows shown, status 71.2%,
authority found 50.9%): seven changes, each measured alone against 1.0.8. (1) Whose stage word it is: a work the release
starts ("Receives <Permit> and Commences Drilling") is no review; a stage word across a semicolon belongs to another
statement; a grant the sentence reports after the submission ("submitted a Notice of Intent ... and has received
approval subject to bonding") is the stage; an "approval process" is under way, not a grant; the resource-estimate caveat
("may be materially affected by environmental, permitting, legal, title ...") names no permit. (2) Stages not reached
yet: a FONSI or approval the company looks forward to is in review; "planning for drill permit applications", "initiated
acquiring all necessary permits" and a permitting process only commenced are planned; a filing another sentence states
is applied, dated to its last step ("the final volume on <date>"), a weekday before a stated date allowed. (3) One row
per project a permit is for ("permits for drilling on its <A>, <B> and <C> Properties") and per community an agreement is
signed with ("Benefit Agreements with the <A>, <B> and <C>", each defined earlier). (4) Issuing bodies named in full:
boards, commissions, panels, services, divisions and branches, national and regional governments, Spanish- and
Portuguese-named agencies, a county a permit comes "from", the bureau of a department ("Department of the Interior's
Bureau of Land Management"), the body a permit is "issued by"; a newly known body never displaces one the earlier patterns
found, nor is taken from next to another kind of permit. (5) Project names that are no names: a dropped acronym put back
("<ABC> Lithium Property"), an address, a province ("New <Province> Project"), headline words. (6) More permit names: land
use permits and licences (an Inuit or First Nation land use licence is "other"), Aquifer Protection Permit, Permit to
Take Water, Air Quality Permit, reclamation plan approvals, safety production permits, archaeology certificates; a short
project name the release defines is shown in full; operations suspended for an expired permit do not make the permit
contested. (7) A permit named only by what it allows ("the permit to fly an airborne survey", "authorization ... to
transport ... to full-scale operations"), typed by that work, only in a release that names no permit otherwise.

Self-tests: python3 -m portal.extractors.permits
"""
from __future__ import annotations

import re

from portal import facts as F
from portal import fingerprint as FP
from portal import project_names as PN
from portal.extractors import technical as T

NAME = "permits"
VERSION = "1.0.9"  # 2026-10-01: own permit news only, rows on the parent project, one row per permit, stage wordings; full-text losses fixed; 2026-10-02: accuracy (FIX4) -- stage words between permits, one permit named twice, Brazil LP/LI/LO, mine permit and BLM types, stage wordings; 2026-10-04 FIX5: whose stage word it is, stages not reached yet, one row per named project or community, issuing bodies named in full, project names that are no names, more permit names, a permit named by what it allows; authority names whole or blank
KIND = "permit"
TAG = "Permits & Approvals"
TEXT_CAP = 40000

TXT_FIELDS = ("permit_type", "project", "status", "authority", "date", "permit_name", "permit_id", "term", "expiry",
              "scope", "holder", "jurisdiction", "metal", "evidence")
NUM_FIELDS = ()

STATUSES = ("planned", "applied", "in_review", "granted", "renewed", "contested")
STAGE_RANK = {"planned": 1, "applied": 2, "in_review": 3, "granted": 4, "renewed": 5, "contested": 6}

# ------------------------------------------------------------------ what a permit is called
_L = r"licen[cs]es?"
_PERMITS = [
    # the most specific names first; an earlier match claims its span
    # 1.0.8: an Advanced Exploration Permit is an exploration permit (guide: drill_exploration)
    ("drill_exploration", r"Advanced\s+Exploration\s+Permits?"),
    ("other", r"conditional\s+use\s+(?:mining\s+)?permits?(?:\s*\(CUP\))?"),
    ("other", r"change\s+of\s+(?:land\s+)?use\s+of\s+(?:the\s+)?soils?(?:\s*\(\s*CUS\s*\))?"),
    ("other", r"export\s+" + _L + r"(?!\s+(?:requirements?|regimes?|controls?|rules?|restrictions?))"),
    ("other", r"sectoral\s+permits?"),
    ("other", r"(?:bulk[\s-]+sampl\w*|explosives?|road\s+use|special\s+use|forestry|timber\s+cutting)\s+(?:permits?|" + _L + r")"),
    ("other", r"Mine\s+Safety\s+Regulations?"),
    ("government_policy", r"FAST-41(?:\s+(?:designation|coverage|transparency\s+project))?"),
    ("government_policy", r"(?:(?:named|designated|recogni[sz]ed|selected|identified)\s+(?:as\s+)?an?\s+(?:provincial\s+|federal\s+|national\s+|EU\s+)?(?:major\s+)?|(?<=\s)an?\s+)(?:priority|strategic)\s+(?:major\s+)?projects?(?:\s+(?:status|designation))?(?=[^.]{0,80}\b(?:Province|Government|Ministry|Premier|Minister|federal|provincial|British\s+Columbia|Ontario|Quebec|Qu\u00e9bec|EU|European|State\b|designat))"),
    ("government_policy", r"competent\s+authority\s+for\s+(?:the\s+)?(?:environmental\s+)?permitting"),
    ("plan_of_operations", r"Plans?\s+of\s+Operations?(?:\s*\(\s*(?:PoO|POO|PoOs)\s*\))?"),
    # 1.0.6: an NCIB's "Notice of Intention to Make a Normal Course Issuer Bid" is not a permit
    ("plan_of_operations", r"Notices?\s+of\s+Intent(?:ion)?(?:\s*\(\s*NOI\s*\))?(?!\s+to\s+(?:acquire|purchase|merge|enter|complete|sell|option|make|renew|launch))"
                           r"(?![^.]{0,120}\b(?:issuer\s+bid|NCIB)\b)"),
    ("plan_of_operations", r"notice[\s-]+level\s+(?:permits?|exploration\s+permits?|approvals?)"),
    ("plan_of_operations", r"(?:Decision\s+Record|Finding\s+of\s+No\s+Significant\s+Impact|FONSI)"),
    ("drill_exploration", r"(?:Declaraci[o\u00f3]n\s+de\s+Impacto\s+Ambiental|\bDIA\b)(?:\s+(?:environmental\s+)?(?:drilling\s+)?permits?)?"),
    ("drill_exploration", r"(?:Informe\s+T[e\u00e9]cnico\s+Sustentatorio|\bFTA\b|Ficha\s+T[e\u00e9]cnica\s+Ambiental)"),
    ("drill_exploration", r"minimum\s+impact\s+activit(?:y|ies)(?:\s*\(\s*MIA\s*\))?(?:\s+(?:permits?|applications?|consents?))?"),
    ("drill_exploration", r"(?:Authori[sz]ation|Autorisation)\s+(?:for|of|pour)\s+(?:des\s+)?(?:impact[\s-]*causing\s+)?(?:exploration\s+)?(?:work|travaux|activities)(?:\s+(?:for|with|\u00e0)\s+impacts?)?(?:\s*\(\s*ATI\s*\))?"),
    ("drill_exploration", r"\bATI\b(?:\s+permits?)?"),
    # 1.0.7 (FIX3): Peru's Authorization to Initiate (Exploration) Activities, the last permit before drilling
    ("drill_exploration", r"(?:Authori[sz]ation|Autorizaci[o\u00f3]n)\s+(?:to\s+(?:Initiate|Commence|Start|Begin)|de\s+Inicio\s+de)\s+(?:(?:Exploration|Mining)\s+)?"
                          r"(?:Activities|Actividades)(?:\s+de\s+Exploraci[o\u00f3]n)?(?:\s*\(\s*[\"\u201c]?AIEA[\"\u201d]?\s*\))?"),
    ("drill_exploration", r"work\s+authori[sz]ations?"),
    ("drill_exploration", r"Class\s+(?:[1-4]|I{1,3}|IV)\s+(?:(?:Exploration|Mining|Quartz)\s+)?(?:Notifications?|Approvals?|Permits?|Programs?|Land\s+Use\s+Permits?)"),
    ("drill_exploration", r"Notices?\s+of\s+Work(?:\s*\(\s*NoW\s*\))?"),
    ("drill_exploration", r"Drill(?:ing)?\s+Notices?(?:\s+permits?)?"),
    ("drill_exploration", r"(?:early\s+)?exploration\s+plans?(?=\s+(?:approval|was\s+approved|were\s+approved|has\s+been\s+approved|"
                           r"have\s+been\s+approved|application))"),
    ("drill_exploration", r"(?:early\s+)?exploration\s+plans?\s+approvals?"),
    ("drill_exploration", r"prospecting\s+(?:plans?|" + _L + r"|permits?|rights?)"),
    ("drill_exploration", r"(?:(?:diamond|RC|core|reverse\s+circulation)\s+)?drill(?:ing)?\s+(?:permits?|" + _L + r"|approvals?|authori[sz]ations?)"),
    ("drill_exploration", r"permits?\s+(?:to|for)\s+(?:the\s+)?(?:drill|drilling|conduct\s+(?:diamond\s+)?drilling)"),
    ("drill_exploration", r"exploration\s+(?:work\s+)?(?:permits?|" + _L + r"|concessions?|authori[sz]ations?|approvals?)(?:\s*\(\s*EPs?\s*\))?"),
    ("drill_exploration", r"(?:environmental\s+)?(?:impact\s+)?(?:report|EIR)\s+update"),
    ("environmental_assessment", r"Environmental\s+Compliance\s+Report(?:\s*\(\s*RECAPE\s*\))?|\bRECAPE\b"),
    ("environmental_assessment", r"(?:Initial\s+)?Project\s+Description(?=[^.]{0,120}(?:assessment|Environmental|Impact))"),
    ("environmental_assessment", r"Manifestaci[o\u00f3]n\s+de\s+Impacto\s+Ambiental|Manifestos?\s+de\s+Impacto\s+Ambiental"),
    ("environmental_assessment", r"(?:provincial\s+|federal\s+)?environmental\s+(?:and\s+social\s+)?(?:impact\s+)?(?:assessments?|statements?|studies|study)(?:\s+(?:approval|certificate|decision))?(?:\s*\(\s*(?:EIA|ESIA|EIS|EA|MIA|EIA/RIMA)\s*\))?"),
    ("environmental_assessment", r"(?:federal\s+)?impact\s+assessments?(?:\s*\(\s*IA\s*\))?"),
    ("environmental_assessment", r"\b(?:ESIA|EIA|EIS)\b"),
    ("environmental_assessment", r"environmental\s+(?:permits?|" + _L + r"|approvals?|authori[sz]ations?|clearances?|certificates?|certification)(?:\s*\(\s*[A-Z]{2,5}\s*\))?"),
    ("environmental_assessment", r"Record\s+of\s+Decision"),
    # PERMIT_V1 recall fix (2026-09-22): Ontario's ECA is its environmental permit
    ("environmental_assessment", r"Environmental\s+Compliance\s+Approvals?(?:\s*\(\s*ECA\s*\))?"),
    ("mining_licence", r"(?:small[\s-]+scale\s+)?mining\s+(?:" + _L + r"|leases?|concessions?|permits?|titles?|rights?(?!\s+(?:holder|over\s+claims))|registration\s+certificates?)"),
    ("mining_licence", r"Mining\s+Registration\s+Certificate"),
    # 1.0.8: a mine permit ("Small Mine Permit", "Industrial Mineral Mine Permit", "the mine permit application") is the
    # permit to mine (guide: mining_licence), not a plant's construction or operating permit
    ("mining_licence", r"(?:(?:small|large)[\s-]+|industrial\s+mineral\s+)?mine\s+(?:permits?|" + _L + r")"),
    ("mining_licence", r"exploitation\s+(?:" + _L + r"|concessions?|permits?)"),
    # 1.0.8: Brazil's three-stage environmental licensing -- the preliminary licence (LP) approves the project's
    # environmental viability (an assessment decision); the installation (LI) and operating (LO) licences follow. The
    # bare acronyms LP and LO count only where the release defines them (analyse)
    ("environmental_assessment", r"Licen[\u00e7c]a\s+Pr[\u00e9e]via"),
    ("environmental_assessment", r"\bLP\b"),
    ("construction_operating", r"(?:Licen[cs]e|Licen[\u00e7c]a)\s+(?:of\s+|de\s+)(?:Installation|Instala[\u00e7c][\u00e3a]o|Operation|Opera[\u00e7c][\u00e3a]o)|"
                               r"(?<!social\s)Licen[cs]e\s+to\s+Operate(?=\s*\(\s*[\"\u201c]?\s*LO\b)"),
    ("construction_operating", r"\bLO\b"),
    ("construction_operating", r"(?:Licen[cs]e|Licen[cs]ing)\s+to\s+(?:Prepare|Construct)[^.,;]{0,40}?(?=\s|,|\.|$)"),
    ("construction_operating", r"(?:Installation|Construction)\s+Licen[cs]e(?:\s*\(\s*LI\s*\))?"),
    ("construction_operating", r"\bLI\b"),
    ("construction_operating", r"(?:construction|operating|operation|mill|plant|processing|pollutant\s+control(?:\s+facility)?|industrial)\s+(?:permits?|" + _L + r"|authori[sz]ations?)|mine\s+authori[sz]ations?"),
    ("water", r"water\s+(?:use\s+|supply\s+|discharge\s+|withdrawal\s+)?(?:permits?|" + _L + r"|rights?|authori[sz]ations?|concessions?)"),
    ("land_community", r"(?:long[\s-]term\s+)?(?:surface\s+)?(?:land|surface|site)\s+access\s+agreements?"),
    ("land_community", r"access\s+(?:agreements?|arrangements?)"),
    ("land_community", r"surface\s+(?:use|rights?)\s+agreements?"),
    # 1.0.7: the acronym in capitals only ("IBAS" is a US defence programme)
    ("land_community", r"Impact\s+(?:and\s+)?Benefits?\s+Agreements?|(?-i:\bIBAs?\b)"),
    ("land_community", r"(?:exploration|relationship|co-?operation|collaboration|participation|community(?:\s+development)?|benefits?)\s+agreements?(?=[^.]{0,160}(?:First\s+Nations?|Nation\b|Indigenous|communit|M\u00e9tis|Metis|Band\b|Nishnaabeg|Anishinaabe|Cree|Inuit|iwi|ejido))"),
    ("land_community", r"community\s+support"),
]
# FIX5: permits named in words the list above did not know -- a land use permit or licence (the northern and Alaskan
# exploration permit), water takings and aquifer protection, air quality, reclamation plan approvals, a safety
# production permit, archaeology certificates
_PERMITS_MORE = [
    ("drill_exploration", r"(?:Miscellaneous\s+)?land[\s-]+use\s+(?:permits?|" + _L + r")(?:\s*\(\s*MLUP\s*\))?"),
    ("water", r"Aquifer\s+Protection\s+Permits?(?:\s*\(\s*APP\s*\))?|Permits?\s+to\s+Take\s+Water(?:\s*\(\s*PTTW\s*\))?"),
    ("other", r"Air\s+Quality\s+(?:Control\s+)?Permits?(?:\s*\(\s*AQP\s*\))?"),
    ("other", r"(?:Mined\s+Land\s+)?Reclamation\s+Plans?(?:\s*\(\s*MLRP\s*\))?\s+approvals?|(?:Mined\s+Land\s+)?Reclamation\s+Plans?(?:\s*\(\s*MLRP\s*\))?(?=\s+(?:approval|was\s+approved|has\s+been\s+approved))"),
    ("construction_operating", r"safety\s+production\s+permits?"),
    ("other", r"archaeolog\w*\s+(?:certificates?|clearances?|permits?)(?:\s*\(\s*CIRA\s*\))?"),
]
_PERMITS = _PERMITS[:1] + _PERMITS_MORE + _PERMITS[1:]
# FIX5: a permit named only by what it allows ("the permit (the "Permit") to fly an airborne ... survey", "final
# authorization from <agency> ... to advance ... to full-scale operations", "a permit to advance further activities on
# <Project>"); typed by that work (_ctype)
_GEN_PERMIT = (r"(?:(?:final|regulatory|government(?:al)?|ministerial|necessary|required)\s+)?(?:permit|authori[sz]ation|"
               r"(?<=regulatory\s)approval|(?<=government\s)approval|(?<=ministerial\s)approval)s?(?:\s*\([^)]{0,30}\))?"
               r"(?:\s+from\s+(?:the\s+)?(?:[A-Z][\w\-.]*,?\s+(?:and\s+|of\s+|for\s+)?|\([A-Z]+\)\s+){1,10})?"
               r"\s+to\s+(?:fly|conduct|carry\s+out|commence|advance|begin|start|proceed\s+with|undertake|transport|operate|construct|"
               r"drill|explore|perform|build|resume|restart|mine)\b(?:\s+(?:out|with))?")
_GEN_PERMIT = r"(?<!\ball\s)(?<!\bany\s)" + _GEN_PERMIT
_GEN_RX = re.compile(r"(?i)" + _GEN_PERMIT)
_PERMITS = _PERMITS + [("other", _GEN_PERMIT)]
# acronym-only patterns are case-sensitive; everything else ignores case
_PERMIT_RX = [(t, re.compile(p) if re.fullmatch(r"\\b[()?:A-Z|\\bs]+(?:\(\?:[^)]*\)\?)?", p) else re.compile(r"(?i)" + p))
              for t, p in _PERMITS]

_GENERIC_HL = re.compile(r"(?i)\b(?:permits?|" + _L + r"|approvals?|authori[sz]ations?)\b")
_DRILLISH = re.compile(r"(?i)\b(?:drill\w*|trench\w*|excavat\w*|explor\w*|work\s+program|stripping)\b")

# ------------------------------------------------------------------ stages
_W = r"[^.;]{0,%d}?"
_ST_CONTESTED = re.compile(r"(?i)\b(?:den(?:ied|ial|ies)|refus\w+|reject\w*|revok\w+|revocation|cancel+(?:ed|ation)|"
                           r"suspen(?:ded|sion|ds)|appeal\w*|challeng(?:e|es|ed)\b|challenging(?=\s*,|\s+(?:of\s+)?(?:the|its|their|this|that|an?)\s)|unfavou?rable|injunction|annul\w*|quash\w*|"
                           r"moratorium|overturn\w*|nullif\w+|"
                           # 1.0.6: a refusal said in other words, and a permit before the courts
                           r"declin(?:ed|es|ing)\s+(?:to\s+(?:issue|grant|approve|renew)|the\s+(?:issuance|approval|grant|renewal|application))|"
                           r"not\s+(?:to\s+)?approv(?:e|ed|ing)|(?:is|was|were)\s+not\s+(?:approved|granted|issued|renewed)|"
                           r"litigation|lawsuit|judicial\s+review|legal\s+(?:challenge|action|proceedings?)|amparo)")
_ST_RENEWED = re.compile(r"(?i)\b(?:renew\w*|extended\s+(?:for|until|by|to|through)|extension\s+(?:of|to)\s+(?:the\s+|its\s+|an?\s+)?(?!all\b)"
                         r"(?:[\w\-]+\s+){0,3}?(?:permit|licen|term|lease|validity|expiry|concession|authori)|(?:term|permit|licen[cs]e|lease)\s+extension|"
                         # 1.0.8: "Receives Drill Permit Expansion", "permit amendment"
                         r"(?:permit|licen[cs]e|approval|authori[sz]ation)s?\s+(?:expansion|amendment|modification)s?\b|"
                         r"(?<!as\s)amend(?:ed|s|ing|ment)(?!\))|updated\s+and\s+revised|revised\s+(?:and\s+updated\s+)?(?:drill|exploration|permit|licen)|"
                         r"re-?issu\w+|expand\w*\s+(?:its|the|our)?\s*(?:permit|authori|approv)|"
                         r"(?:minor\s+|major\s+)?modifications?\s+(?:to|of)\s+(?:the\s+|its\s+|our\s+)?(?:\w+\s+){0,3}(?:permit|plan|licen[cs]e|approval|notice)s?\b)|"
                         r"\b(?:additional|more|further)\s+(?:\d+\s+)?(?:drill\s+)?(?:pads?|sites?|holes?|disturbance)|"
                         r"\bauthori[sz]ed\s+for\s+an\s+additional")
_ST_GRANTED = re.compile(r"(?i)\b(?:rec(?:ei|ie)v(?:ed|es|ing)|(?:named|recogni[sz]ed|selected|identified)\s+(?:as\s+)?an?\s+(?:\w+\s+){0,2}(?:priority|strategic)|receipt\s+of|grant(?:ed|s|ing)?|issu(?:ed|es|ance)|approv(?:ed|es|al|als)|"
                         r"obtain(?:ed|s)|award(?:ed|s)|secur(?:ed|es)|ruled|rules|ruling|designat(?:ed|es|ion)|lift(?:ed|s)|"
                         r"authori[sz](?:ed|es)|permitted|in\s+hand|green\s+light|positive\s+decision|favou?rable\s+"
                         r"(?:decision|opinion)|tacit\w*\s+approv\w*|now\s+(?:holds|has)|"
                         # 1.0.7 (FIX3): the decision-makers accept the assessment's approval or recommendation (a
                         # northern review board's report is decided by the Ministers "accepting" it)
                         r"(?:has|have|had)\s+accepted\s+(?=(?:the\s+)?(?:[\w\-]+\s+){0,4}?(?:approvals?|recommendations?|decisions?)\b))")
_ST_SIGNED = re.compile(r"(?i)\b(?:sign(?:ed|s|ing)|execut(?:ed|es)|conclud(?:ed|es)|entered\s+into|finali[sz]ed|reached|"
                        r"complet(?:ed|es)(?=\s+(?:(?:an?|the|its|their|definitive|long[\s-]term)\s+)*(?:[\w\-]+\s+){0,3}agreements?\b)|"  # 1.0.7 (FIX3)
                        r"expressed\s+(?:strong\s+|their\s+|its\s+)?support|support(?:s|ed)?\s+(?:for|the)|endors\w+)")
_ST_REVIEW = re.compile(r"(?i)\b(?:under\s+review|in\s+review|being\s+reviewed|review\s+process|reviewing|"
                        r"(?:is|are|remains?)\s+pending|pending\s+(?:approval|review|decision)|underway|under\s+way|"
                        r"in\s+progress|being\s+finali[sz]ed|process\s+of\s+being|(?<!process\sof\s)applying\s+for|awaits?|awaiting|commenc(?:ed|es|ing|ement)|initiat(?:ed|es|ion)|launch(?:ed|es)|start(?:ed|s)|"
                        r"begun|began|comment\s+period|public\s+(?:consultation|comment|hearing)|hearings?|accept(?:ed|ance)\s+"
                        r"(?:of\s+)?(?:the\s+)?(?:initial\s+)?project\s+description|negotiat\w+|in\s+discussions?|"
                        r"(?:is|are)\s+(?:currently\s+)?(?:being\s+)?(?:advanced|progressing|advancing)|permitting\s+process\s+is|"
                        r"(?<=ting\s)progressing|"   # 1.0.8: "environmental permitting progressing"
                        # 1.0.6: "at the very last stage of obtaining the environmental license"
                        r"(?:final|last|late|advanced)\s+stages?\s+of\s+(?:obtaining|securing|receiving|the)\b|"
                        # 1.0.6: an application found complete is under review
                        r"(?:deemed|declared|found)\s+(?:[\w\u2019'\-]+\s+){0,10}?(?:to\s+be\s+)?complete\b|notice\s+of\s+completion|completeness)")
_ST_APPLIED = re.compile(r"(?i)\b(?:submit(?:ted|s|ting)|submission|appl(?:ied|ies)\s+for|(?:has|have)\s+applied|"
                         r"application\s+(?:for|to|was|has|with)|applications?\s+(?:has|have)\s+been|lodg(?:ed|es)|"
                         r"filed|files|filing\s+of|registered\s+(?:the|an?)\s+application|requested|request\s+(?:for|of))")
_ST_PLANNED = re.compile(r"(?i)\b(?:will\s+(?:apply|submit|seek|file|require|need|be\s+(?:required|needed|submitted|sought|"
                         r"applying|filed))|plans?\s+to\s+(?:apply|submit|seek|file|obtain)|planned|intends?\s+to|intention\s+to|"
                         r"expects?\s+to\s+(?:submit|apply|file|begin|commence|start|initiate)|anticipat\w+|"
                         r"(?:is|are)\s+(?:still\s+)?(?:required|needed|necessary)|remain(?:s|ing)?\s+(?:to\s+be\s+obtained|outstanding|required)|"
                         r"future\s+(?:licen[cs]ing|permitting)\b|"   # 1.0.8: "future licensing initiatives to migrate to the <licence>"
                         r"still\s+(?:required|needed)|must\s+(?:now\s+)?(?:submit|obtain|apply)|subsequent\s+step|next\s+steps?|"
                         r"in\s+preparation|preparing|to\s+be\s+(?:submitted|obtained|filed)|proceed(?:ing)?\s+to|required\s+(?:for|before|prior)|"
                         r"will\s+(?:commence|begin|start|initiate)|process\s+of\s+applying|commenced\s+the\s+application\s+process|"
                         r"(?:include|including|includes)\s+[^.]{0,60}permitting|will\s+require|would\s+require|requires?|"
                         r"(?<!order\s)to\s+(?:commence|begin|start|initiate|negotiate|finali[sz]e|pursue|file|submit|lodge)\b)")   # 1.0.6
_FUTURE = re.compile(r"(?i)\b(?:will|would|shall|can|may|could|expects?\s+to|expected\s+to|(?:expects?|anticipates?)\s+(?:the\s+)?receipt|anticipat\w+|upon|once|following\s+(?:the\s+)?receipt|"
                     r"subject\s+to|pending|prior\s+to|before|until|await\w*|remains?\s+subject|if\s+|when\s+|in\s+order\s+to|"
                     r"planned|plans?\s+to|intends?\s+to|seek\w*|needed|required|necessary|to\s+obtain|to\s+secure|to\s+receive|"
                     r"to\s+be|eventual|potential|future)\b")   # 1.0.6: "to be approved", "the eventual receipt of"
_BACKGROUND = re.compile(r"(?i)\b(?:already\s+(?:holds?|has|have|received|obtained|granted|in\s+place|permitted)|"
                         r"fully[\s-]+permitted|existing\s+(?:permits?|" + _L + r"|approvals?|authori[sz]ations?|agreements?)|"
                         r"currently\s+holds?|(?:holds?|held)\s+(?:all|the|a|an|its)\s+[^.]{0,30}(?:permit|" + _L + r")|"
                         r"under\s+(?:its|the)\s+(?:existing|current)|in\s+good\s+standing|valid\s+(?:permits?|" + _L + r")|"
                         r"(?:on|under|within|across)\s+(?:its|the|our|their)\s+(?:[A-Z][\w\-]*\s+){0,4}(?:prospecting|exploration|mining)\s+"
                         r"(?:permits?|" + _L + r")\b(?!\s+application)|(?:adjacent|next)\s+to\s+(?:the\s+)?(?:[A-Z][\w\-]*\s+){0,4}\S*\s*"
                         r"(?:mining|exploration)\s+(?:permits?|" + _L + r")|"
                         r"as\s+(?:previously\s+)?(?:announced|reported|disclosed)\s+(?:on|in)\s+(?:[A-Z][a-z]+\s+\d{1,2},\s+)?(?:19|20)\d\d|"
                         # PERMIT_V1 audit fixes (2026-09-22): tenure described, permits already in hand
                         r"(?:tenure|property|project|package)\s+(?:\w+\s+){0,3}?(?:comprises|includes|consists\s+of|is\s+made\s+up\s+of)\s+"
                         r"(?:\w+\s+){0,4}?(?:granted|contiguous)|"
                         r"in[\s-]hand\s+(?:\w+\s+){0,2}(?:permits?|approvals?|licen)|"
                         r"under\s+(?:the\s+Company['\u2019]s|its|the|our)\s+(?:remaining|existing|current|approved|valid)|"
                         r"(?:IBA|Agreement)\s+(?:\(\s*IBA\s*\)\s+)?partners|remains?\s+in\s+place|per\s+the\s+terms\s+of)")
_NOT_PERMIT_CTX = re.compile(r"(?i)\b(?:TSX|TSXV|TSX\s+Venture|CSE|NYSE|NASDAQ|stock\s+exchange|the\s+Exchange|shareholders?|"
                             r"court|Final\s+Order|Interim\s+Order|arrangement|Investment\s+Canada|Competition\s+Act|"
                             r"antitrust|SAMR|merger|takeover|private\s+placement|financing|DTC|listing|warrants?|"
                             r"options?\s+(?:grant|to\s+purchase)|stock\s+options?|RSUs?|share\s+(?:consolidation|capital))\b")
_DEAL_HL = re.compile(r"(?i)\b(?:(?:final|conditional|exchange|TSXV?|CSE|shareholder|court|regulatory)\s+approvals?\b[^.]{0,80}"
                      r"\b(?:arrangement|acquisition|transaction|merger|listing|option|consolidation|spin[\s-]?out|amalgamation|"
                      r"plan\s+of\s+arrangement|financing|placement|name\s+change)|approv\w+\s+(?:of\s+)?(?:the\s+)?(?:plan\s+of\s+)?"
                      r"arrangement|(?:Investment\s+Canada|Competition\s+Act|antitrust)\b|\bapproval\s+for\s+(?:the\s+)?"
                      r"(?:acquisition|consolidation|spin[\s-]?out|option|name\s+change|listing))")

# ------------------------------------------------------------------ authorities
_AUTH_KNOWN = [
    (r"(?:U\.?S\.?\s+)?Bureau\s+of\s+Land\s+Management(?:\s*\(\s*BLM\s*\))?|\bBLM\b", "Bureau of Land Management"),
    (r"(?:U\.?S\.?(?:D\.?A\.?)?\s+)?(?:USDA\s+)?Forest\s+Service(?:\s*\(\s*USFS\s*\))?|\bUSFS\b", "U.S. Forest Service"),
    (r"(?:British\s+Columbia|BC)\s+Environmental\s+Assessment\s+Office(?:\s*\(\s*EAO\s*\))?|\bEAO\b", "British Columbia Environmental Assessment Office"),
    (r"Impact\s+Assessment\s+Agency\s+of\s+Canada(?:\s*\(\s*IAAC\s*\))?|\bIAAC\b", "Impact Assessment Agency of Canada"),
    (r"Canadian\s+Nuclear\s+Safety\s+Commission(?:\s*\(\s*CNSC\s*\))?|\bCNSC\b", "Canadian Nuclear Safety Commission"),
    (r"\bSEMARNAT\b", "SEMARNAT"),
    (r"\bMAPEG\b", "MAPEG"),
    (r"National\s+Mining\s+Agency(?:\s*\(\s*ANM\s*\))?|Ag[e\u00ea]ncia\s+Nacional\s+de\s+Minera[c\u00e7][a\u00e3]o|\bANM\b", "National Mining Agency (ANM)"),
    (r"Ag[e\u00ea]ncia\s+Portuguesa\s+do\s+Ambiente(?:\s*\(\s*APA\s*\))?|Portuguese\s+Environment(?:al)?\s+Agency|\bAPA\b", "Ag\u00eancia Portuguesa do Ambiente (APA)"),
    (r"\bSEMAS\b", "SEMAS"),
    (r"\bSEMAD\b", "SEMAD"),
    (r"\bIBAMA\b", "IBAMA"),
    (r"\bEMNRD\b|Energy,\s+Min(?:erals|es),?\s+and\s+Natural\s+Resources\s+Department", "New Mexico Energy, Minerals and Natural Resources Department (EMNRD)"),
    (r"\bMETI\b|Ministry\s+of\s+Economy,\s+Trade\s+and\s+Industry", "Ministry of Economy, Trade and Industry (METI)"),
    (r"\bMERN\b|\bMRNF\b|Minist[e\u00e8]re\s+des\s+Ressources\s+naturelles\s+et\s+des\s+For[e\u00ea]ts", "Qu\u00e9bec Minist\u00e8re des Ressources naturelles et des For\u00eats"),
    (r"\bMFFP\b|Minist[e\u00e8]re\s+des\s+For[e\u00ea]ts,\s+de\s+la\s+Faune\s+et\s+des\s+Parcs", "Qu\u00e9bec Minist\u00e8re des For\u00eats, de la Faune et des Parcs"),
    (r"\bDOC\b|Department\s+of\s+Conservation", "Department of Conservation"),
    (r"Chief\s+(?:Gold|Permitting)\s+Commissioner", "Chief Gold Commissioner"),
    (r"Federal\s+Court\s+of\s+Appeals?[^.,;()]{0,30}(?:\(\s*TRF1\s*\))?|\bTRF1\b", "Federal Court of Appeals (TRF1)"),
    (r"General\s+(?:Superintendence|Department)\s+of\s+Irrigation[^.,;]{0,20}", "General Superintendence of Irrigation"),
]
_AUTH_KNOWN = [(re.compile(p if re.fullmatch(r"\\b[A-Z0-9]+\\b(?:\|\\b[A-Z0-9]+\\b)*", p) else r"(?i)" + p), n)
               for p, n in _AUTH_KNOWN]
_AUTH_ACRO_CS = re.compile(r"\b(?:BLM|USFS|EAO|IAAC|CNSC|SEMARNAT|MAPEG|ANM|APA|SEMAS|SEMAD|IBAMA|EMNRD|METI|MERN|MRNF|MFFP|DOC|TRF1)\b")
_PLACE = (r"(?:Ontario|Quebec|Qu\u00e9bec|British\s+Columbia|BC|Saskatchewan|Manitoba|Alberta|Yukon|Nunavut|Northwest\s+Territories|"
          r"Newfoundland(?:\s+and\s+Labrador)?|Nova\s+Scotia|New\s+Brunswick|Nevada|Idaho|Wyoming|Utah|Arizona|Montana|"
          r"Alaska|Oregon|California|Colorado|New\s+Mexico|South\s+Dakota|Washington|Mendoza|Sonora|Chihuahua|Durango|"
          r"Guerrero|Zacatecas|Goi[a\u00e1]s|Par[a\u00e1]|Minas\s+Gerais|Andalusia|Huelva|Western\s+Australia|Queensland|"
          r"New\s+South\s+Wales|Victoria|Otago|Antofagasta|Atacama|Vichada|Hokkaido|Dajab[o\u00f3]n|Kayseri|Cajamarca|Jun[i\u00ed]n|"
          r"Ancash|Arequipa|Salta|Jujuy|San\s+Juan|Santa\s+Cruz|Sinaloa|Oaxaca|Bahia|Tocantins|Mato\s+Grosso|Northern\s+Territory|"
          r"South\s+Australia|Tasmania|Castilla\s+y\s+Le[o\u00f3]n|Alentejo|Lapland)")
_AUTH_GENERIC = re.compile(
    r"\b((?:" + _PLACE + r"(?:['\u2019]s)?\s+)?(?:Provincial\s+|Federal\s+|State\s+)?(?:Ministry|Minist[e\u00e8]re|Department|Secretariat|Secretar[i\u00ed]a|"
    r"Directorate|Superintendence|Office|Agency)\s+(?:of|for|des|de|du|da|do)\s+(?:the\s+)?"
    r"(?:[A-Z][\w'\-]*|and|of|&|des|de|la|et|du|,(?=\s+[A-Z]))(?:\s+(?:[A-Z][\w'\-]*|and|of|&|des|de|la|et|du|,(?=\s+[A-Z])))*"
    r"(?:\s+of\s+" + _PLACE + r")?)")
_AUTH_GOV = re.compile(r"\b((?:Government\s+of\s+(?:the\s+)?" + _PLACE + r")|(?:Province\s+of\s+" + _PLACE + r")|(?:State\s+of\s+" + _PLACE +
                       r")|(?:" + _PLACE + r"\s+(?:Government|government))|(?:[A-Z][a-z]+\s+County))\b")
_AUTH_NATION = re.compile(r"\b((?:[A-Z][\w'\-]+\s+){1,3}(?:First\s+Nations?|Cree\s+Nation|M\u00e9tis\s+Nation|Nishnaabeg|Anishinaabe[kg]?)|"
                          r"(?:First\s+Nations?\s+of\s+[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+){0,2}))")


# FIX5: issuing and reviewing bodies named in full that the patterns above did not know -- boards, commissions,
# panels, services, divisions and branches ("<Region> Land and Water Board", "<Country> Geology and Mines Commission",
# "Joint Review Panel", "US Army Corps of Engineers", "Environmental Assessment Division of the Government of
# <Province>"), a national or regional government ("Government of <Country>", "Regional Government of <Region>",
# "<Province> government"), Spanish- and Portuguese-named agencies ("Servicio Nacional de ...") and a county
# ("<Name> County")
_AW = r"(?:[A-Z](?![\w\-]*['\u2019]s\b)[\w'\u2019\-]*\.?|U\.S\.|and|of|&|for)"
_AUTH_BODY = re.compile(
    r"\b((?:(?:U\.?S\.?|United\s+States|[A-Z][\w'\u2019\-]+)\s+)(?:" + _AW + r"\s+){0,6}?"
    r"(?:Board|Commission|Panel|Corps\s+of\s+Engineers|Service|Division|Branch|Inspectorate|Dept\.)"
    r"(?:\s+of\s+(?:the\s+)?(?:Government\s+of\s+)?[A-Z][\w\-]+(?:\s+(?:and\s+)?[A-Z][\w\-]+){0,3})?)(?!\w)(?!['\u2019]s\b)(?!\s+(?:and\s+)?[A-Z][\w\-]*['\u2019]s\b)(?!\s+of\s+(?:the\s+)?[A-Z])"
    r"(?:\s*\(\s*[\"\u201c]?([A-Z][A-Z&]{1,8})[\"\u201d]?\s*\))?")
_AUTH_BODY_NOT = re.compile(r"(?i)\b(?:Securities|Appeals|Exchange|Directors|Advisory|Trust|Transfer|Corporation|Company|Inc|Ltd|"
                            r"Energy\s+Regulator|Stock|Investment|Trade|Revenue|Tax|Postal|News|Wire|Fire|Police|Health|School|"
                            r"Parole|Labou?r|Employment|Immigration|Customs|Audit|Accounting|Standards)\b")
_AUTH_NATIONAL = re.compile(
    r"\b((?:Regional\s+|Federal\s+|National\s+|Provincial\s+|State\s+)?Government\s+of\s+(?:the\s+)?(?:Republic\s+of\s+(?:the\s+)?)?"
    r"[A-Z](?![\w\-]*['\u2019]s\b)[\w\-]+(?:\s+(?:and\s+)?[A-Z](?![\w\-]*['\u2019]s\b)[\w\-]+){0,2}|"
    r"(?:Servicio|Ministerio|Secretar[\u00edi]a|Direcci[\u00f3o]n|Instituto|Agencia|Autoridad|Superintendencia|Comisi[\u00f3o]n)\s+"
    r"(?:(?:[A-Z][\w\u00e0-\u00ff'\-]*|de|del|la|las|los|y|e|do|da|dos|das)\s+){0,7}[A-Z][\w\u00e0-\u00ff'\-]*|"
    r"(?:[A-Z][\w'\u2019\-]+\s+){0,2}[A-Z][\w'\u2019\-]+\s+County(?:\s+(?:[A-Z][\w\-]+\s+){0,3}(?:Department|Board(?:\s+of\s+Supervisors)?|Commission))?|"
    r"(?:Newfoundland\s+and\s+Labrador|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+government(?=\s+(?:authori[sz]ation|approval|permit|has|granted|issued|approved)))\b")


_AUTH_NEW = {}      # FIX5: sentence -> the bodies only the FIX5 patterns found in it (filled with _AUTH_CACHE)


class _CutName(str):
    """FIX5 r2: a body's name that the release writes longer (or otherwise) than the patterns read it. It stands for
    that body while the rows are built, so no other body takes its place, and it is never published."""
    __slots__ = ()
_AUTH_VERBS_TITLE = {"Receives", "Received", "Secures", "Obtains", "Announces", "Submits", "Confirms", "Reports", "Provides",
                     "Grants", "Granted", "Approves", "Approved", "Files", "Completes", "Advances", "Signs", "Commences",
                     "Begins", "Starts", "Launches", "Initiates", "Updates", "Applies", "Expands", "Receipt", "Update"}


def _authorities(s):
    out, new = [], set()
    for rx, name in _AUTH_KNOWN:
        for m in rx.finditer(s):
            if m.group(0).isupper() and not _AUTH_ACRO_CS.fullmatch(m.group(0).strip()):
                continue
            out.append((m.start(), m.end(), name))
    taken = [(a, b) for a, b, _ in out]
    cut = []
    for rx in (_AUTH_BODY, _AUTH_GENERIC, _AUTH_GOV, _AUTH_NATION, _AUTH_NATIONAL):
        for m in rx.finditer(s):
            if any(a <= m.start() < b or m.start() <= a < m.end() for a, b in taken):
                continue
            if any(m.start() < b and a < m.end() and not (m.start() <= a and b <= m.end()) for a, b, _, _ in cut):
                continue        # FIX5 r2: part of a name found cut short (only a longer reading of it may stand)
            name = re.sub(r"[\s,]+$", "", m.group(1))
            if rx is _AUTH_BODY:
                if _AUTH_BODY_NOT.search(name) or re.match(r"(?i)(?:The|This|Our|Its|Their|A|An|Such|Each|Any)\s", name) or \
                        any(w in _AUTH_VERBS_TITLE or w.isupper() and len(w) > 4 for w in name.split()):
                    continue
            written = name = re.sub(r"\s+(?:and|of|the|des|de|du|&)$", "", name)
            if rx is _AUTH_BODY and m.group(2):
                name = name + " (" + m.group(2) + ")"
            if len(name.split()) < 2:
                continue
            if rx is not _AUTH_BODY and re.search(r"(?i)\b(?:Mines?|Mining|Minerals?|Resources?|Gold|Metals?|Corp|Inc|Ltd)\s*$", name) and \
                    not re.match(r"(?i)(?:\w+\s+)?(?:Ministry|Minist|Department|Agency|Office|Secretar|Direct)", name):
                continue
            whole = _auth_whole(s, m.start(1), m.start(1) + len(written), written)
            if not whole:
                cut.append((m.start(), m.end(), name, rx in (_AUTH_BODY, _AUTH_NATIONAL)))
                continue
            if whole[2] != written:
                name = whole[2] + name[len(written):]
            out.append((whole[0], max(m.end(), whole[1]), name))
            taken.append((whole[0], max(m.end(), whole[1])))
            if rx in (_AUTH_BODY, _AUTH_NATIONAL):
                new.add(name)
    # FIX5 r2: a body whose name is cut short still stands where the release names it, unless a whole reading of it
    # was found or it only qualifies the body named right after it ("State of <A> <Known Department>")
    for a, b, name, is_new in cut:
        full = [n for x, y, n in out if re.fullmatch(r"\s*\(\s*[\"\u201c]\s*", s[y:a])]
        if full and not isinstance(full[0], _CutName):
            out.append((a, b, full[0]))         # ("<Short name>"): the body just named in full
        elif not any(x < b and a < y or b <= x and not s[b:x].strip() for x, y, _ in out):
            out.append((a, b, _CutName(name)))
            if is_new:
                new.add(name)
    out.sort()
    return out, new


# ------------------------------------------------------------------ places, ids, terms
_COUNTRY = r"(?:Canada|USA|United\s+States(?:\s+of\s+America)?|Mexico|Peru|Chile|Argentina|Brazil|Colombia|Ecuador|Bolivia|" \
           r"Portugal|Spain|Turkey|T\u00fcrkiye|Japan|Australia|New\s+Zealand|Morocco|Dominican\s+Republic|Guyana|Finland|Sweden|" \
           r"Norway|Ireland|Serbia|Greenland|Tanzania|Ghana|Namibia|Botswana|Zambia|Mongolia|Kazakhstan|Philippines|Indonesia|" \
           r"Panama|Guatemala|Honduras|Nicaragua|" \
           r"Papua\s+New\s+Guinea|Equatorial\s+Guinea|Guinea|Mali|Burkina\s+Faso|C[\u00f4o]te\s+d['\u2019]Ivoire|Ivory\s+Coast|Senegal|" \
           r"Nigeria|Sierra\s+Leone|Liberia|Democratic\s+Republic\s+of\s+(?:the\s+)?Congo|DRC|South\s+Africa|Zimbabwe|Kenya|" \
           r"Ethiopia|Egypt|Sudan|Eritrea|Saudi\s+Arabia|Madagascar|Mozambique|Malawi|Angola|Uganda|Cameroon|Gabon|" \
           r"Kyrgyz(?:stan|\s+Republic)|Uzbekistan|Armenia|Slovakia|Bosnia(?:\s+and\s+Herzegovina)?|Kosovo|Scotland|Wales|" \
           r"Fiji|Solomon\s+Islands|Paraguay|Uruguay|Venezuela|Suriname|French\s+Guiana|Costa\s+Rica|El\s+Salvador|Poland|" \
           r"Czech\s+Republic|Czechia|Romania|Bulgaria|Hungary|Greece|Germany|Niger)"
# JUR_V2 (2026-09-26): more states, provinces and mining regions for the jurisdiction only (_PLACE, which the
# authority patterns use, is unchanged). A region stands for its province: "the Golden Triangle" is British Columbia.
_PLACE_MORE = (r"(?:Minnesota|Michigan|Wisconsin|Maine|North\s+Carolina|South\s+Carolina|Texas|Missouri|Tennessee|"
               r"North\s+Dakota|Nebraska|Arkansas|Oklahoma|Kentucky|Pennsylvania|Alabama|Vermont|(?:West\s+)?Virginia|Jalisco|Nayarit|"
               r"Michoac[a\u00e1]n|Coahuila|Guanajuato|Hidalgo|Quer[e\u00e9]taro|Nuevo\s+Le[o\u00f3]n|San\s+Luis\s+Potos[i\u00ed]|Baja\s+California(?:\s+Sur)?|Catamarca|Neuqu[e\u00e9]n|"
               r"R[i\u00ed]o\s+Negro|Chubut|Coquimbo|Tarapac[a\u00e1]|Golden\s+Triangle|Athabasca\s+Basin|Nunavik|Eeyou\s+Istchee|"
               r"Chibougamau|Timmins|Sudbury|Red\s+Lake|Flin\s+Flon|B\.C\.|QC|Prince\s+Edward\s+Island)")
_PLACE_RX = re.compile(r"\b(" + _PLACE_MORE + r"|" + _PLACE + r")(?![\w-])(?:,?\s+(" + _COUNTRY + r")\b)?|\b(" + _COUNTRY + r")\b")
_PROVINCE_COUNTRY = {"ontario": "Canada", "quebec": "Canada", "qu\u00e9bec": "Canada", "british columbia": "Canada", "bc": "Canada",
                     "saskatchewan": "Canada", "manitoba": "Canada", "alberta": "Canada", "yukon": "Canada", "nunavut": "Canada",
                     "northwest territories": "Canada", "newfoundland": "Canada", "newfoundland and labrador": "Canada",
                     "nova scotia": "Canada", "new brunswick": "Canada", "nevada": "USA", "idaho": "USA", "wyoming": "USA",
                     "utah": "USA", "arizona": "USA", "montana": "USA", "alaska": "USA", "oregon": "USA", "california": "USA",
                     "colorado": "USA", "new mexico": "USA", "south dakota": "USA", "washington": "USA", "mendoza": "Argentina",
                     "sonora": "Mexico", "chihuahua": "Mexico", "durango": "Mexico", "guerrero": "Mexico", "zacatecas": "Mexico",
                     "goi\u00e1s": "Brazil", "goias": "Brazil", "par\u00e1": "Brazil", "para": "Brazil", "minas gerais": "Brazil",
                     "andalusia": "Spain", "huelva": "Spain", "western australia": "Australia", "queensland": "Australia",
                     "new south wales": "Australia", "victoria": "Australia", "otago": "New Zealand", "antofagasta": "Chile", "atacama": "Chile", "vichada": "Colombia", "hokkaido": "Japan", "dajab\u00f3n": "Dominican Republic", "dajabon": "Dominican Republic", "kayseri": "T\u00fcrkiye", "cajamarca": "Peru", "jun\u00edn": "Peru", "junin": "Peru", "ancash": "Peru", "arequipa": "Peru", "salta": "Argentina", "jujuy": "Argentina", "san juan": "Argentina", "santa cruz": "Argentina", "sinaloa": "Mexico", "oaxaca": "Mexico", "bahia": "Brazil", "tocantins": "Brazil", "mato grosso": "Brazil", "northern territory": "Australia", "south australia": "Australia", "tasmania": "Australia", "castilla y le\u00f3n": "Spain", "castilla y leon": "Spain", "alentejo": "Portugal", "lapland": "Finland"}
_PROVINCE_COUNTRY.update({s: "USA" for s in (
    "minnesota", "michigan", "wisconsin", "maine", "north carolina", "south carolina", "texas", "missouri", "tennessee",
    "north dakota", "nebraska", "arkansas", "oklahoma", "kentucky", "pennsylvania", "alabama", "vermont", "virginia",
    "west virginia")})
_PROVINCE_COUNTRY.update({s: "Mexico" for s in (
    "jalisco", "nayarit", "michoac\u00e1n", "michoacan", "coahuila", "guanajuato", "san luis potos\u00ed", "san luis potosi",
    "baja california", "baja california sur", "hidalgo", "quer\u00e9taro", "queretaro", "nuevo le\u00f3n", "nuevo leon")})
_PROVINCE_COUNTRY.update({"catamarca": "Argentina", "neuqu\u00e9n": "Argentina", "neuquen": "Argentina", "r\u00edo negro": "Argentina",
                          "rio negro": "Argentina", "chubut": "Argentina", "coquimbo": "Chile", "tarapac\u00e1": "Chile",
                          "tarapaca": "Chile", "prince edward island": "Canada", "b.c.": "Canada", "qc": "Canada"})
# a region, camp or town that stands for its province
_REGION_PROVINCE = {"golden triangle": "British Columbia", "athabasca basin": "Saskatchewan", "nunavik": "Quebec",
                    "eeyou istchee": "Quebec", "chibougamau": "Quebec", "timmins": "Ontario", "sudbury": "Ontario",
                    "red lake": "Ontario", "flin flon": "Manitoba"}
# one spelling per place on the page
_CANON = {"United States": "USA", "United States of America": "USA", "Qu\u00e9bec": "Quebec", "BC": "British Columbia",
          "B.C.": "British Columbia", "QC": "Quebec", "Newfoundland": "Newfoundland and Labrador", "Turkey": "T\u00fcrkiye",
          "Goias": "Goi\u00e1s", "Para": "Par\u00e1", "Junin": "Jun\u00edn", "Dajabon": "Dajab\u00f3n", "Castilla y Leon": "Castilla y Le\u00f3n",
          "Michoacan": "Michoac\u00e1n", "San Luis Potosi": "San Luis Potos\u00ed", "Neuquen": "Neuqu\u00e9n", "Rio Negro": "R\u00edo Negro",
          "Tarapaca": "Tarapac\u00e1", "Cote d'Ivoire": "C\u00f4te d'Ivoire", "C\u00f4te d\u2019Ivoire": "C\u00f4te d'Ivoire",
          "Cote d\u2019Ivoire": "C\u00f4te d'Ivoire", "Ivory Coast": "C\u00f4te d'Ivoire", "Kyrgyz Republic": "Kyrgyzstan",
          "Democratic Republic of Congo": "DRC", "Democratic Republic of the Congo": "DRC",
          "Bosnia": "Bosnia and Herzegovina", "Czechia": "Czech Republic",
          "Queretaro": "Quer\u00e9taro", "Nuevo Leon": "Nuevo Le\u00f3n"}


# FIX5 r2: an authority is the body's whole name as the release writes it, or nothing. Where the patterns read a name
# short, it is read whole: the capitalised words just before it that are part of it ("San <Name> County", "General
# Directorate of ...", "Regional State Administrative Agency of ..."), a state or country the patterns do not list
# ("<State> Department of ..."), the list that goes on after it ("Ministry of <A>, <B> and <C>", "Secretaria de <A> y
# <B>"), a word the line wrap split ("... and Labr ador"), and a short name the release defines stands for the full one.
# A title-case word before the name that is not part of it ("From", "Following") is left off. Where it cannot be read
# whole, it is left blank: a capitalised word straight after it ("<Name> Commission Hearing"), two bodies in one ("<A>
# Canada and <B>", "Department of <A> and <B> Government"), a possessive ("<Company>'s Board"), a report title, more
# than four words before it.
_AUTH_LEAD_WORDS = frozenset((
    "The A An This That These Those From By With To For And Of In On At Its Their Our Under Between Including Both Each "
    "Per Via As Into Upon Before After Through Following Additionally Also However Furthermore Moreover Meanwhile Recently "
    "Today Separately Subsequently Finally Further Previously Currently Once When While If Since During Update Updates "
    "Highlights Approvals Approval Permits Permit Applications Application Then Now Next Where Whereas "
    "Accordingly Therefore Thereafter Thus Likewise Similarly Additional").split())
_AUTH_NATIONALITY = re.compile(r"[A-Z][a-z]+(?:ian|ean|ese|ish|ican)|Greek|Swiss|Thai|French|Dutch|Irish|Welsh|Czech|Slovak")
_AUTH_PLACES = re.compile(r"(?:" + _PLACE_MORE + r"|" + _PLACE + r"|" + _COUNTRY + r")(?![\w-])")
_AUTH_HEADS = (r"Ministry|Minist[e\u00e8]re|Department|Dept\.|Secretariat|Secretar[i\u00ed]a|Directorate|Superintendence|Office|"
               r"Agency|Board|Commission|Panel|Corps\s+of\s+Engineers|Service|Division|Branch|Inspectorate|Government|"
               r"government|County|Nations?|Band|Association|Council|Servicio|Ministerio|Direcci[o\u00f3]n|Instituto|Agencia|"
               r"Autoridad|Superintendencia|Comisi[o\u00f3]n")
_AUTH_HEAD_END = re.compile(r"\b(?:" + _AUTH_HEADS + r")(?:\s*\([^)]*\))?$")
_AUTH_TWO = re.compile(r"\b(?:" + _AUTH_HEADS + r")\b.*?(?:\band|&|,)\s+(?:the\s+)?(?:[A-Z][\w'\-]*\s+){0,4}(?:" +
                       _AUTH_HEADS + r")\b")
_AUTH_DOC = re.compile(r"\b(?:Reports?|Study|Studies|Update|Highlights|Permits?|Licen[cs]es?|Project|Property|Act|Website)\b")
_AUTH_LIST_ON = re.compile(r"\s*(?:,\s*(?:and\s+|&\s+)?|\s(?:and|y|e|et|&)\s+)[A-Z]")
_AUTH_DATELINE = re.compile(r"\s+[A-Z][\w.]+(?:\s+[A-Z][\w.]+){0,2}\s*,\s*(?:[A-Z][\w.]*\s*){1,3}"
                            r"(?:[\u2013\u2014-]|,\s*(?:January|February|March|April|May|June|July|August|September|October|"
                            r"November|December|\d))")


def _split_word(s, left, frag, rest):
    """FIX5 r2: whether a capitalised word and the lower-case piece after it are one word the line wrap split ("Labr"
    "ador", "Nor" "thwest"): together they begin a place, or the release writes them as one word elsewhere."""
    return bool(_AUTH_PLACES.match(left + frag + rest)) or bool(re.search(r"\b" + re.escape(left + frag) + r"\b", s))


def _auth_whole(s, x, e, name):
    """FIX5 r2: (start, end, name) of the whole name the match at s[x:e] stands for, or None when it cannot be read whole.
    e is where the written name ends (before any acronym in brackets)."""
    w = name.split()
    while w and w[0] in _AUTH_LEAD_WORDS:          # "From <Name> County", "Following <Name> Board"
        x = s.index(w[0], x) + len(w[0])
        x += len(s[x:]) - len(s[x:].lstrip())
        w = w[1:]
    if len(w) < 2 or w[0] in _AUTH_VERBS_TITLE or s[x:x + len(w[0])] != w[0]:
        return None
    name = " ".join(w) if name.split() != w else name
    # before the name: a state or country the patterns do not list, or capitalised words that are part of the name
    # ("San <Name> County", "General Directorate of ..."); not a title-case word, a nationality, a possessive or a
    # heading
    pm = re.search(r"(?:^|[^\w'\u2019.\-])((?:" + _PLACE_MORE + r"|" + _COUNTRY + r")(?:['\u2019]s)?)\s+$", s[max(0, x - 80):x])
    if pm and not re.match(_PLACE, name):
        x -= len(s[max(0, x - 80):x]) - pm.start(1)
        name = pm.group(1) + " " + name
    else:
        k, lead = x, []
        while True:
            pw = re.search(r"(?<![\w'\u2019.\-])([A-Za-z][\w'\u2019\-]*\.?)[ \t]+$", s[max(0, k - 60):k])
            if not pw:
                break
            t = pw.group(1)
            if t.islower():
                fw = re.search(r"([A-Z][\w'\u2019\-]*) $", s[max(0, k - 60):max(0, k - 60) + pw.start(1)])
                if fw and _split_word(s, fw.group(1), t, s[k - 1:]):
                    return None                    # "Nor thwest <Name>": the line wrap split the word before the name
                break
            if not t[0].isupper() or t in _AUTH_LEAD_WORDS or t in _AUTH_VERBS_TITLE or re.search(r"['\u2019]s$", t) or \
                    _AUTH_NATIONALITY.fullmatch(t) or t in ("US", "U.S.", "USA") or t.isupper() and len(t) >= 5:
                break
            if len(lead) == 4:
                return None
            lead.insert(0, t)
            k = max(0, k - 60) + pw.start(1)
        if lead:
            x, name = k, " ".join(lead) + " " + name
    if re.search(r"[\"\u201c(]\s*$", s[max(0, x - 3):x]) and re.match(r"\s*[\"\u201d]", s[e:e + 3]):
        return None                                # ("<Short> Board"): the short name the release defines
    # after the name
    after = s[e:e + 160]
    if re.match(r"-+(?:\s|$)", after) or name.endswith("-"):
        name = name.rstrip("-").rstrip()
        e += len(after) - len(after.lstrip("-"))
        after = after.lstrip("-")
    fm = re.match(r" ([a-z]+)", after)
    if fm and re.search(r"[A-Z][\w'\u2019\-]*$", name):
        tail = " ".join(name.split()[-3:])         # "... and Labr ador": a word the line wrap split
        joined = tail + after[1:]
        for i in [0] + [j + 1 for j, c in enumerate(tail) if c == " "]:
            pj = _AUTH_PLACES.match(joined, i)
            if pj and pj.end() >= len(tail) + len(fm.group(1)):
                name = name[:len(name) - len(tail)] + joined[:pj.end()]
                e += 1 + pj.end() - len(tail)
                after = after[1 + pj.end() - len(tail):]
                break
        else:
            if _split_word(s, name.split()[-1], fm.group(1), after[fm.end():]):
                return None
    if re.search(r"(?:" + _PLACE_MORE + r"|" + _PLACE + r"|" + _COUNTRY + r")$", name):
        if re.match(r"\s+(?:and|y|e|et|&)\s+[A-Z]", after):
            return None                            # "Government of <A> and <B>": a longer place or two places
    elif not _AUTH_HEAD_END.search(name) and not re.match(r"\s*\(", after):
        # "Ministry of <A>, <B> and <C>", "Secretaria de <A> y <B>": the list belongs to the name
        k, ok = 0, 0
        while True:
            lm = re.match(r"(\s*,\s*(?:and\s+|&\s+)?|\s+(?:and|&|y|e)\s+)([A-Z][\w'\u2019\-]*(?:\s+[A-Z][\w'\u2019\-]*){0,3})(?![\w'\u2019\-])",
                          after[k:])
            if not lm:
                break
            k += lm.end()
            if re.search(r"and|&|\by\b|\be\b", lm.group(1)):
                ok = k
                break
        if ok:
            more = after[:ok]
            if re.search(r"\b(?:" + _AUTH_HEADS + r")\b", more) or _AUTH_PLACES.search(more) or _AUTH_DOC.search(more):
                return None
            name, after, e = name + more.rstrip(), after[ok:], e + ok
        elif _AUTH_LIST_ON.match(after):
            return None
    nx = re.match(r" ([A-Z][\w'\u2019\-]*)", after)
    if nx and not (nx.group(1) in _AUTH_LEAD_WORDS or nx.group(1) in _AUTH_VERBS_TITLE or re.search(r"(?:s|ed)$", nx.group(1)) or
                   _AUTH_DATELINE.match(after)):
        return None                                # "<Name> Commission Hearing": the name goes on
    # inside the name: a possessive, a company, a report title, two bodies, a place between other words
    words = name.split()
    if any(re.search(r"['\u2019]s$", t) and not _AUTH_PLACES.fullmatch(t[:-2]) for t in words) or \
            re.search(r"\b(?:Inc|Corp|Ltd|Limited|LLC|Company|Corporation)\b", name) or \
            _AUTH_DOC.search(name) or any(t in _AUTH_VERBS_TITLE for t in words) or _AUTH_TWO.search(name):
        return None
    for pm in _AUTH_PLACES.finditer(name):
        if pm.start() > 0 and pm.end() < len(name) and \
                not re.search(r"(?:\b(?:of|de|del|da|do|dos|das|du|des)\s+(?:the\s+)?|^(?:[A-Z]\w+\s+){0,2})$", name[:pm.start()]) and \
                not re.match(r"\s*['\u2019]s\b", name[pm.end():]):
            return None                            # "Ministry of <A> Canada and <B>"
    return x, e, name


_HQ_LINE = re.compile(r"(?i)\b(?:suite|street|avenue|\bave\b|floor|tel|phone|fax|www\.|@|V\d[A-Z]\s?\d[A-Z]\d|M\d[A-Z]\s?\d[A-Z]\d|newsfile|"
                      r"globe\s*newswire|business\s*wire|accesswire|news\s+release)")
_LOCATED = re.compile(r"(?i)\b(?:located|situated|lies|sits)\s+(?:\w+\s+){0,6}?in\s+(?:the\s+)?(?:[\w\-]+\s+){0,4}?")
# JUR_V2: sentences that name places for other reasons -- US securities and newswire legends, where an offering is
# sold, reporting-issuer forms. Skipped whole only when they name no project, property, claims, deposit or mine.
_JUR_BOILER = re.compile(
    r"(?i)securities\s+(?:act|laws?|commission|regulators?|and\s+exchange)|U\.?\s?S\.?\s+persons?|news\s?wire|dissemination|"
    r"absent\s+(?:registration|an\s+(?:applicable\s+)?exemption)|registration\s+requirements?|offered\s+or\s+sold|"
    r"solicitation\s+of\s+an\s+offer|non-brokered\s+basis|prospectus|accredited\s+investors?|Multilateral\s+Instrument|"
    r"registrant|jurisdiction\s+of\s+incorporation|failure\s+to\s+comply\s+with\s+this\s+restriction")
_JUR_PROJECT_WORDS = re.compile(r"(?i)\b(?:projects?|propert(?:y|ies)|claims?|deposits?|mines?|concessions?|licen[cs]es?|"
                                r"tenements?|prospects?|district|belt|camp)\b")
# ... and single mentions next to such wording: "sold in the United States", "OTCQB in the United States", "United
# States dollars", "headquartered in Vancouver, Canada", "incorporated under the laws of the Province of Ontario"
# (the legend words only before the United States, the listing words only before a country, the office words before any
# place: "incorporated under the laws of British Columbia", "based in Vancouver, British Columbia")
_JUR_NEAR_US = re.compile(
    r"(?i)(?:securities|news\s?wire|dissemination|distribution|registration|registered|offered\s+or\s+sold|offer\s+to\s+(?:sell|buy)|"
    r"persons|benefit\s+of|exemption|accredited|brokered|prospectus)\b[^.;]{0,60}$")
_JUR_NEAR_LISTING = re.compile(r"(?i)(?:\bOTC\w*|Nasdaq|NYSE|\blisted\b|\blisting|uplisting|\btrading\b|Frankfurt|stock\s+exchange|"
                               r"dollars?|currency)\b[^.;]{0,30}$")
_JUR_NEAR_OFFICE = re.compile(r"(?i)(?:headquarter\w*|head\s+office|based\s+in|offices?\s+in|incorporated|laws\s+of|"
                              r"Multilateral)\b[^.;]{0,60}$")
_JUR_NEAR_AFTER = re.compile(r"(?i)\s*:\s*[A-Z]{2,6}\b|\s*-\s*based\b|\W{0,3}(?:securities|news\s?wire|dollars?|currency|tariffs?|persons|investors?|"
                             r"market\b|listing|stock\s+exchange|federal\s+government|government\s+bonds?|legal\s+counsel)")
# JUR_V2: the company's own "About ..." paragraph, the qualified person's paragraph, the board sign-off: the rest of
# the release is not about this project
_JUR_STOP = re.compile(
    r"(?:^|\s)(?:About\s+(?:the\s+Company\b|Us\b|(?!the\s+(?:\w+\s+){0,4}?(?:Property|Project|Claims|Option|Agreement|"
    r"Transaction|Acquisition|Deposit|Mine)s?\b)[A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,5}\s*(?:[:.]|\(|\s(?=[A-Z][a-z]+\s)))|"
    r"Qualified\s+Persons?\b(?!\s+(?:as\s+defined|under))|On\s+[Bb]ehalf\s+of\s+the\s+Board)")
# a place inside another name: Lithium Chile Inc., Cerro Colorado, Cobre Panama, Franco-Nevada, Norway House, the
# University of Nevada, 1287398 BC Ltd., the Business Corporations Act (Ontario), the Supreme Court of British Columbia
_NAME_BEFORE_OK = {"north", "south", "east", "west", "northern", "southern", "eastern", "western", "central", "northeast",
                   "northwest", "southeast", "southwest", "northeastern", "northwestern", "southeastern", "southwestern",
                   "mid", "upper", "lower", "coastal", "rural", "remote", "in", "at", "of", "and", "from", "to", "for",
                   "across", "throughout", "within", "near", "outside", "the", "a", "both", "including", "while", "also",
                   "all", "into", "northernmost", "southernmost", "province", "state", "territory", "republic", "prolific",
                   "whereas", "as", "each", "where", "with", "on", "by", "is", "was", "are",
                   # a place before a place: "Clayton Valley Nevada", "Esmeralda County Nevada", "Kivalliq Region Nunavut"
                   "valley", "county", "district", "basin", "range", "mountains", "lake", "river", "creek", "hills",
                   "island", "peninsula", "region", "territory", "township", "canyon", "desert", "plateau", "belt",
                   "trough", "camp", "area", "division", "park", "coast", "shield", "craton", "greenstone"}
_ORG_AFTER = re.compile(r"\)?(?:\s+[A-Z][\w&'\u2019\-]*){0,2}\s+(?:Inc|Corp|Corporation|Ltd|Limited|LLC|L\.L\.C|Pty|Plc|PLC|S\.A|"
                        r"S\.A\.C|AB|GmbH|ULC|Co|Company|Resources|Royalt\w*|Capital|Ventures|Holdings)\b|"
                        r"\s+(?:House|Pit|Bureau|University|Securities|Stock|Dollars?|City|Springs|Hydro|Power|Energy)\b")
# after a country only: the national government, army, treasury, geological survey are not where the project is
_ORG_AFTER_COUNTRY = re.compile(r"\s+(?:Congress|Presidential|President|Treasury|Army|Navy|Geological\s+Survey|"
                                r"Department\s+of\s+(?:Defen[cs]e|Energy|Commerce|State|the\s+Treasury)|Export|Import|"
                                r"Government['\u2019]s)\b")
_NAME_BEFORE_BAD = re.compile(r"(?i)(?:University|Supreme\s+Court|Court\s+of\s+(?:Appeal|King['\u2019]s\s+Bench)|Superior\s+Court|"
                              r"laws|Securities\s+Commission|College|Bank|Geological\s+Survey)\s+(?:of\s+)?(?:the\s+)?(?:Province\s+of\s+|State\s+of\s+)?$|"
                              r"\bAct\b[\w\s,]{0,20}\(\s*$|\w-$|"
                              r"\b(?:Company|Corporation|Trust|Exchange|Commission|Chamber|Council)\s+of\s+(?:the\s+)?$|"
                              r"\b(?:Ltd|Limited|Inc|Corp|LLC|Pty|PLC|S\.A)\.?\s+of\s+(?:the\s+)?$|\b\d{5,}\s+$|"
                              r"\b(?:Association|Institute|Society|Order|Ordre|Federation)\s+(?:of|des?)\s+(?:[A-Z][\w&'\u2019\-]*\s+|and\s+|of\s+){0,5}"
                              r"(?:of\s+|des?\s+|du\s+)?(?:the\s+)?(?:Province\s+of\s+)?$")
# JUR_V2: words that make a name even in a headline: Grupo Mexico, Minera Chile, Cerro Colorado, Lithium Chile
_NAME_BEFORE_ALWAYS = re.compile(r"(?i)(?:^|[\s(])(?:Grupo|Minera|Minera\u00e7\u00e3o|Mineracao|Cerro|Cobre|Compa[\u00f1n][i\u00ed]a|Banco|Empresa|"
                                 r"Sociedad|Franco|Lithium|Nickel|Uranium|Cobalt|Graphite|Potash|Vanadium)\s+$")


def _place_name(m):
    if m.group(1):
        p = re.sub(r"\s+", " ", m.group(1))
        if p in ("BC", "QC", "Victoria", "Washington", "Para", "Par\u00e1") and not m.group(2):
            if not (p in ("BC", "QC") and re.search(r",\s*$", m.string[max(0, m.start() - 3):m.start()])):
                return None   # JUR_V2: ", BC" / ", QC" (after a town or a property) is British Columbia / Quebec
        rg = _REGION_PROVINCE.get(p.lower())
        if rg:
            return "%s, Canada" % rg
        c = m.group(2) or _PROVINCE_COUNTRY.get(p.lower())
        p, c = _CANON.get(p, p), _CANON.get(re.sub(r"\s+", " ", c), re.sub(r"\s+", " ", c)) if c else c
        return "%s, %s" % (p, c) if c else p
    p = re.sub(r"\s+", " ", m.group(3))
    return _CANON.get(p, p)


def _place_ok(s, m, hl=False):
    """JUR_V2: False when the match is part of another name or of an address, not a place the release is about."""
    before, after = s[max(0, m.start() - 60):m.start()], s[m.end():m.end() + 60]
    if _NAME_BEFORE_BAD.search(before) or _ORG_AFTER.match(after) or _NAME_BEFORE_ALWAYS.search(before) or \
            (m.group(3) and _ORG_AFTER_COUNTRY.match(after)):
        return False
    if m.group(1) and re.match(r"(?i)\s+(?:targets?|zones?|trends?|veins?|pits?|showings?|prospects?|anomal(?:y|ies)|grids?)\b|"
                               r"\s+(?:Property|Properties|Claims?|County)\b", after):
        return False   # a named target or property: the "California target" in Chihuahua, the "Colorado Pit", the
        #                "Virginia Property" in Newfoundland; a US county: "Hidalgo County, New Mexico"
    if m.group(3) and (re.match(r"\s+(?:(?:Gold|Silver|Copper|Nickel|Zinc|Lithium|Uranium)\s+)?(?:Project|Property|Lake|Zone|"
                                r"Claims?|Deposit|Creek|River|Hill|Grid|Showing|Target|Vein)s?\b", after) or
                       (re.search(r"(?i)\bthe\s+$", before) and
                        re.match(r"(?i)\s+(?:(?:gold|silver|copper|nickel|zinc|lithium|uranium)\s+)?(?:project|property|lake|claims?)\b",
                                 after))):
        return False   # a project named after a country: Benton's "Panama Gold Project" / "the Panama property" is in Ontario
    b70 = s[max(0, m.start() - 70):m.start()]
    if _JUR_NEAR_OFFICE.search(b70) or _JUR_NEAR_AFTER.match(after) or \
            (m.group(3) and _JUR_NEAR_LISTING.search(b70)) or \
            (m.group(3) and _place_name(m) == "USA" and _JUR_NEAR_US.search(b70)):
        return False
    if m.group(1) and re.match(r"(?i)(?:Santa\s|San\s|Virginia|West\s+Virginia)", m.group(1)) and not m.group(2) and \
            not re.match(r"(?i)\s+(?:province|state)", after) and \
            not re.search(r"(?i)(?:(?:province|state)\s+of|county,?|southwest(?:ern)?|west(?:ern)?|southern)\s+$", before):
        return False   # "Santa Cruz", "San Juan", "Virginia" name many places and projects: only "Santa Cruz Province",
        #                ", Argentina", "Pittsylvania County, Virginia"
    if re.search(r"(?i)\b(?:Vancouver|Toronto|Calgary|Montreal|Montr\u00e9al|Halifax|Saskatoon|Kelowna|Edmonton|Winnipeg|Ottawa|"
                 r"Reno|Denver|Perth|Sydney|Brisbane|Melbourne|London)\s*,?\s*$", before):
        return False   # the office's city
    win = s[max(0, m.start() - 90):m.end() + 60]
    if _HQ_LINE.search(win) and re.search(r"(?i)suite|street|avenue|\bave\b|floor|tel\b|phone|fax|www\.|@|"
                                          r"[VM]\d[A-Z]\s?\d[A-Z]\d|\b\d{5}\b", win):
        return False   # an address block
    if not hl and s[:m.start()].strip() and not (sum(ch.isupper() for ch in s[:200]) > 0.6 * sum(ch.isalpha() for ch in s[:200])):
        pw = re.search(r"(?:^|[\s(])([A-Z][\w'\u2019]*)\s$", before)
        if pw and not pw.group(1).lower().endswith(("'s", "\u2019s")) and pw.group(1).lower() not in _NAME_BEFORE_OK \
                and s[:m.start()].strip() != pw.group(1):
            return False   # "Lithium Chile", "Cerro Colorado", "Paladin Canada", "Victoria Resources"
    return True


def _jur_case(s):
    """JUR_V2: words in capitals ("TENORIBA PROJECT, SIERRA MADRE, MEXICO", "PROPERTY IN NEVADA") are read in title case
    so their places are found; same length, so positions hold. True with it when most of the line is in capitals."""
    letters = [ch for ch in s[:300] if ch.isalpha()]
    caps = bool(letters) and sum(ch.isupper() for ch in letters) >= 0.6 * len(letters)
    t = re.sub(r"\b[A-Z\u00c0-\u00dd][A-Z\u00c0-\u00dd'\u2019]{2,}\b", lambda m: m.group(0) if m.group(0) in ("USA", "DRC", "NWT") else m.group(0).title(), s)
    t = re.sub(r"(?<=\s)(?:And|Of|The|Del|De)(?=\s)", lambda m: m.group(0).lower(), t) if caps else t
    return t, caps


def _jurisdiction(h, sents):
    """Where the project is. JUR_V2 (2026-09-26): places that are part of another name, an address, a securities or
    newswire legend, a currency or a listing are not counted, nor anything after the company's "About ..." paragraph;
    "located in ..." in the headline or the first 3 sentences decides; otherwise every mention votes for its country
    (the headline twice, "located in" three times) and the answer is the winning country's most-named province or
    state, else the country. The "About ..." paragraph is read only when nothing is named before it."""
    body, rest = [], []
    for i, s in enumerate(sents[:60]):
        if i >= 2 and _JUR_STOP.match(s):
            rest = sents[i:60]
            break
        body.append(s)
    r = _jur_votes([h] + body)
    if r is None and rest:
        r = _jur_votes([""] + rest)   # nothing named before the company's own paragraph: read it
    return r


def _jur_votes(lines):
    votes, pvotes, first = {}, {}, {}
    for i, s in enumerate(lines):
        if not s or (_JUR_BOILER.search(s) and not _JUR_PROJECT_WORDS.search(s)):
            continue
        s, caps = _jur_case(s)
        loose = i == 0 or caps   # a headline or an all-capitals line: capitals say nothing about names
        lm = _LOCATED.search(s) if i <= 40 else None
        if lm and i <= 3:
            ms = [m for m in _PLACE_RX.finditer(s, lm.end() - 1, lm.end() + 70) if _place_ok(s, m, loose) and _place_name(m)]
            if ms:
                n = _place_name(ms[0])
                if "," not in n:   # "located in Canada's Northwest Territories": the province that follows
                    for m2 in ms[1:]:
                        n2 = _place_name(m2)
                        if "," in n2 and n2.endswith(", " + n):
                            return n2
                return n
        for m in _PLACE_RX.finditer(s):
            after = s[m.end():m.end() + 30]
            if re.match(r"\s*,?\s*(?:" + T._MON + r")\.?\s*\d", after) or \
                    re.match(r"\s*[,/]?\s*(?:[(\[]\s*(?:" + T._MON + r"|\d|Newsfile|GLOBE|Globe|CNW|Marketwired|Business|ACCESS|Accesswire)|"
                             r"--|[\u2013\u2014]\s*(?:" + T._MON + r"|\d|\(|[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,4}\s+(?:Corp|Inc|Ltd|"
                             r"Limited|Resources|Mining|Metals|Minerals|Gold|Silver|Copper|Lithium|Uranium|Energy|Exploration)\b))", after):
                continue   # a dateline: "VANCOUVER, BC (October 17, 2024)", "Toronto, Ontario -- ", "Reno, Nevada \u2013 ABC Corp."
            if not _place_ok(s, m, loose):
                continue
            n = _place_name(m)
            if not n:
                continue
            w = 2 if i == 0 else 3 if lm and m.start() >= lm.end() - 1 and m.start() < lm.end() + 70 else 1
            ctry = n.split(", ")[-1]
            votes[ctry] = votes.get(ctry, 0) + w
            first.setdefault(ctry, (i, m.start()))
            if "," in n:
                pvotes[n] = pvotes.get(n, 0) + w
                first.setdefault(n, (i, m.start()))
    if not votes:
        return None
    ctry = max(votes, key=lambda x: (votes[x], (-first[x][0], -first[x][1])))
    provs = [p for p in pvotes if p.endswith(", " + ctry)]
    if provs:
        return max(provs, key=lambda x: (pvotes[x], (-first[x][0], -first[x][1])))
    return ctry


def _several_projects(rows, hl_projs, projs_all):
    """JUR_ROW (1.0.4): the release names more than one project (its rows' projects and every project the headline
    and body name, the same project counted once)."""
    seen = []
    for p in [r["project"] for r in rows] + [p for _, p in hl_projs] + [p for _, p in projs_all]:
        if p and _pwords(p) and not any(_same_project(p, q) for q in seen):
            seen.append(p)
            if len(seen) > 1:
                return True
    return False


_PWORD_RX = re.compile(r"(?i)\b(?:projects?|propert(?:y|ies)|mines?|deposits?)\b")


def _row_lines(r, lines, issuer, cache):
    """JUR_ROW (1.0.4): the text about this row's project: the headline (first; None when it does not count) and every
    sentence naming the project, cut to the part about it -- after the name up to the next project or project word
    ("the Mount Milligan Mine in British Columbia and the Oksut Mine in Turkey" is Turkey for Oksut; "Kami (iron ore)
    as well as the Curipamba copper-gold project in Ecuador" names no place for Kami; the name itself is not read, so
    "Texas Canyon Project, Nevada" is Nevada), or, for a defined term, the words before it ("in Saskatchewan, Canada
    (the \"Goldfields Project\") and Chiapas, Mexico (the \"Ixhuatan Project\")"). A sentence that does not name the
    project does not count, not even the row's own (its permit may belong to another project: Taca Taca's ESIA on a
    row inherited by Enterprise)."""
    words = _pwords(r["project"])
    seq = T._pkey(r["project"]).split()
    # the name itself, not its words elsewhere ("Cobre Panama" hides no "Government of Panama"): the words in order, and
    # a one-word name only before a project word ("the Panama Project")
    hide = re.compile(r"(?i)(?<![\w-])" + r"[\s\-]+(?:[\w'\u2019]+[\s\-]+){0,2}?".join(re.escape(w) for w in seq) + r"(?![\w-])" +
                      (r"(?=\s+(?:[\w\-]+\s+){0,2}?(?:projects?|propert(?:y|ies)|mines?|deposits?|claims?|prospects?)\b)"
                       if len(seq) == 1 else ""))
    place_name = bool(_PLACE_RX.fullmatch(_strip_suffix(r["project"]).strip()))   # "Minas Gerais Project" keeps its place
    named = []
    for i, x in enumerate(lines):
        k = cache.get(x)
        if k is None:
            k = cache[x] = (set(T._pkey(x).split()), _projects(x, issuer) if x else [])
        kw, ps = k
        mine = bool(x) and words <= kw
        at = [j for j, (p, n) in enumerate(ps) if _same_project(n, r["project"]) or words <= _pwords(n)]
        other = [ps[j][0] for j in range(len(ps)) if j not in at]
        if not mine:
            named.append(None)
            continue
        if at:
            a = ps[at[0]][0]
            m0 = _PWORD_RX.search(x, a, a + 90)
            b0 = m0.end() if m0 else a
        else:
            m = re.search(r"\b" + re.escape(max(words, key=len)), T._fold(x))
            a = b0 = m.start() if m else 0
        if not place_name:
            x = hide.sub(lambda m: " " * len(m.group(0)), x)   # the name's own words ("Texas" Canyon) are not places
        if not other:
            named.append(x)
            continue
        if re.search(r"\(\s*(?:the\s+)?[\"\u201c'\u2018]?\s*$", x[max(0, a - 12):a]):
            prev = [p for p in other if p < a]
            named.append(x[max(prev) if prev else 0:a])
            continue
        nxt = [p for p in other if p > a]
        end = min(nxt) if nxt else len(x)
        m1 = _PWORD_RX.search(x, b0, end)
        named.append(x[b0:m1.start() if m1 else end])
    return named


def _row_juris(r, h, body_sents, juris, cache, issuer=None):
    """JUR_ROW (1.0.4): where this row's project is, from the text naming it (_row_lines); the release's answer when
    that names no place, or only the country the release already narrows to a province."""
    if not _pwords(r["project"]):
        return juris
    named = _row_lines(r, [h] + list(body_sents), issuer, cache)
    body = [x for x in named[1:] if x]
    jr = _jurisdiction(named[0] or "", body) if body or named[0] else None
    if not jr:
        return juris
    if juris and "," not in jr and juris.endswith(", " + jr):
        return juris
    return jr


_ID_RX = re.compile(r"(?i)\b(?:permit|licen[cs]e|lease|resolution|authori[sz]ation|file|approval|title|certificate)s?\s*\(?\s*(?:No\.?|Number|#|N[\u00bao\u00b0]\.?)\s*"
                    r"([A-Z]{0,4}[\-\s]?\d[\w\-/]{2,24}(?:\s*(?:and|&|,)\s*(?:No\.?\s*)?[A-Z]{0,4}[\-\s]?\d[\w\-/]{2,24})*)")
_TERM_RX = re.compile(r"(?i)\b(?:(?:valid|term|period|duration)\s+(?:of\s+|for\s+)?(?:an?\s+)?(?:initial\s+)?(?:period\s+of\s+)?|"
                      r"for\s+(?:an?\s+)?(?:(?:additional|further|initial)\s+)?(?:period\s+of\s+)?)"
                      r"((?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|twenty-five|thirty)"
                      r"(?:\s*\(\d{1,2}\))?[\s-]+(?:year|month)s?)")
_TERM_PRE = re.compile(r"(?i)\b((?:\d{1,2}|one|two|three|four|five|ten|twenty|thirty)(?:\s*\(\d{1,2}\))?[\s-]+(?:year|month))s?\s+"
                       r"(?:[\w\-]+\s+){0,3}?(?:permit|licen[cs]e|lease|term|renewal|agreement|authori[sz]ation|window|period)")
_EXPIRY_RX = re.compile(r"(?i)\b(?:valid\s+(?:until|through|to)|expir(?:es|y|ing|ation)(?:\s+date)?(?:\s+(?:on|of|in))?|until)\s+"
                        r"(" + T._DATE_RX + r")")


# ------------------------------------------------------------------ helpers
_VERBS_HL = {"Accelerates", "Receives", "Received", "Secures", "Secured", "Obtains", "Obtained", "Announces", "Submits",
             "Submitted", "Commences", "Marks", "Granted", "Grants", "Applies", "Applying", "Signs", "Signed", "Files",
             "Launches", "Initiates", "Begins", "Starts", "Advances", "Prepares", "Completes", "Enters", "Awarded",
             "Approves", "Approved", "Approval", "Initiation", "Permit", "Permits", "Authorization", "Authorisation",
             "Licence", "License", "Update", "Provides", "Reports", "Expands", "Expand", "Work", "Drill", "Drilling",
             "Plans", "Plan", "Permitting", "Renewal", "Term", "Environmental", "Assessment", "Support", "Community",
             "Strong", "Receipt", "Anniversary", "Acquire", "Acquires", "To", "With", "Its", "Their", "Maverick",
             "For", "At", "On", "Advance", "Advances", "Advancing", "Expanding", "Located", "Strategically", "Authorizing",
             "Following", "Near", "Towards"}
# 1.0.6: headline words that are never part of a project's name ("... to Help Finance Project", "Unlocks Key Milestone
# for Project Advancement", "Closes Deal to Purchase Four Projects", "Reviews Project Portfolio", "... Will See <Plant>
# Commissioned and <Name> Mine"); a name made only of such words or of nationality words is no name
_HL_JUNK = {"File", "Filing", "Help", "Helps", "Finance", "Finances", "Fund", "Funds", "Eliminate", "Eliminates", "Purchase", "Purchases",
            "Reviews", "Review", "Secure", "Unlock", "Unlocks", "Will", "See", "Sees", "Commissioned", "Deliver",
            "Delivers", "Delivered", "Supporting", "Highlighting", "Positions", "Reactivate"}
_JUNK_CORE = {"american", "south", "north", "east", "west", "central", "latin", "indonesian", "mexican", "peruvian",
              "canadian", "australian", "african", "chilean", "brazilian", "colombian", "ecuadorian", "argentine",
              "argentinian", "zealand", "portfolio", "advancement", "development", "expansion", "optimization",
              "district", "regional", "flagship", "other", "various", "respective", "company", "group", "intrusive",
              "magmatic", "complex", "two", "three", "four", "five", "six", "several", "multiple", "federal", "strategic",
              "investment", "specific", "capital", "efficient", "very", "large", "transformative", "key", "milestone",
              "milestones"}
_ROLE_RX = re.compile(r"(?i)\b(?:president|ceo|cfo|chair(?:man|person)?|director|officer|vice)\b")
_NOT_PROJ_AFTER = {"Advancement", "Description", "Notice", "Notices", "Application", "Approval", "Status", "Area", "Site", "Team", "Manager", "Update", "Highlights", "Overview", "Location",
                   "Background", "Details", "Summary", "Portfolio", "Pipeline", "Financing", "Development", "Plan",
                   "To", "EIA", "ESIA", "Environmental", "Permit", "Permits", "Execution", "Files", "The", "Is", "Will",
                   "Has", "Was", "And", "Of", "In", "At"}


_LEAD_CHARS = 900          # the headline and the lead paragraph
_BODY_NAME_AFTER = re.compile(r"\s+(?:(?:Permitting|Review|Assessment|Approvals?)\s+)?(?:Agency|Office|Branch|Division|Board|Council|Commission|Tribunal)\b")


def _mentions(s, base, lead=True):
    """Permit mentions in a sentence: (start, end, type, name) with earlier patterns claiming their spans."""
    got = []
    for typ, rx in _PERMIT_RX:
        for m in rx.finditer(s):
            a, b = m.start(), m.end()
            if b - a < 2:
                continue
            if any(a < y and x < b for x, y, _, _ in got):
                continue
            name = re.sub(r"\s+", " ", m.group(0)).strip()
            if _BODY_NAME_AFTER.match(s, b):
                continue
            # 1.0.8: "permitting" in an authority's description ("SEMARNAT, the federal agency in charge of
            # environmental permitting") names the agency's remit, not a permit
            if re.match(r"(?i)ting\b", s[b:b + 4]) and \
                    re.search(r"(?i)\b(?:in\s+charge\s+of|responsible\s+for|oversee\w*|regulat\w+|administer\w*)\s+(?:the\s+|all\s+)?(?:[\w\-]+\s+){0,2}$", s[max(0, a - 60):a]):
                continue
            if typ == "government_policy" and re.search(r"(?i)priority|strategic", m.group(0)) and not lead:
                continue
            if typ == "drill_exploration" and re.match(r"(?i)DIA\b|Declaraci", name) and \
                    not _DRILLISH.search(s[max(0, a - 200):b + 200]):
                typ = "environmental_assessment"   # Portugal's DIA is the EIA decision itself
            got.append((a, b, typ, name))
    got.sort()
    return [(a + base, b + base, t, n) for a, b, t, n in got]


_STRONG_PLANNED = re.compile(r"(?i)\b(?:subsequent\s+step|next\s+steps?\s+(?:is|are|will|would|includes?|in|for|towards?|to|being)\b|process\s+of\s+applying|commenced\s+the\s+application\s+"
                             r"process|(?:is|are|will\s+be)\s+(?:still\s+)?required|remains?\s+(?:to\s+be\s+obtained|outstanding)|"
                             r"must\s+(?:now\s+)?(?:submit|obtain)|will\s+require|to\s+be\s+(?:submitted|obtained|filed|lodged)|"
                             r"(?:intends?|plans?|expects?)\s+to\s+(?:submit|apply|file|seek|obtain|begin|commence|initiate)|"
                             r"will\s+(?:submit|apply|file|seek)|proceed(?:ing)?\s+to\s+(?:the\s+)?|planned\s+for\s+(?:submission|filing)|"
                             r"(?:contracts?|engage[sd]?|retain(?:s|ed)?|consultants?)\s+(?:\w+\s+){0,3}(?:for|to\s+(?:prepare|complete|support))\s+"
                             r"(?:the\s+|its\s+|an?\s+)?(?:[\w\-]+\s+){0,3}(?:permit|licen[cs]e)\s+applications?|"
                             r"(?:next|upcoming|remaining|key)\s+(?:\w+\s+){0,2}(?:permitting\s+)?(?:milestones?|steps?)\s+(?:are|is|include|will)|"
                             # 1.0.6: an application still being written or only scheduled ("is expected to submit its
                             # application", "prepares to submit", "preparation of the permit application")
                             r"(?:expected|anticipated|scheduled|targeted|targets?|aims?|prepares?|preparing|ready)\s+to\s+(?:submit|apply|file|lodge)|"
                             r"prepar(?:ation|ing|es?)\s+(?:of\s+|for\s+)?(?:the\s+|its\s+|an?\s+)?(?:formal\s+)?(?:[\w\-]+\s+){0,5}?(?:submission|application|filing)s?\b|"
                             r"(?:steps?|path(?:way)?|milestones?)\s+(?:in|to|towards?|for)\s+(?:obtaining|securing|receiving|getting))")
_PAST_DONE = re.compile(r"(?i)\b(?:has|have|had)\s+(?:now\s+)?(?:been\s+)?(?:received|recieved|granted|issued|approved|obtained|secured)|"
                        r"\b(?:was|were)\s+(?:received|granted|issued|approved)|\brec(?:ei|ie)ved\b")
# 1.0.6 (status): a grant the release is waiting for is under review; a refusal is contested; a grant said not to have
# happened is not one ("no exploitation permit has been granted to date"); an explicit review beats the submission
# that started it ("the NoW submission is now under technical review"); a renewal still in progress is under review.
_FINITE_APPLIED = re.compile(r"(?i)\b(?:files|filed|submits|submitted|applies|applied|lodges|lodged|has\s+applied|"
                             r"made\s+(?:an?\s+|its\s+)?applications?)\b")
_AWAITED = re.compile(r"(?i)\b(?:anticipat\w*|expect(?:s|ed|ing|ation)?|await\w*|in\s+anticipation|pending|"
                      r"prepar\w*\s+for\s+(?:the\s+)?receipt|on\s+track\s+(?:for|to)|imminent|to\s+be\s+approved|"
                      r"in\s+(?:a\s+few|the\s+(?:coming|next)(?:\s+few)?)\s+(?:days|weeks|months))\b")
_REVIEW_STRONG = re.compile(r"(?i)\b(?:under\s+(?:technical\s+|active\s+|regulatory\s+|final\s+)?review|in\s+review|being\s+(?:reviewed|evaluated|assessed|processed)|"
                            r"referred\s+(?:for|to)|consultation\s+(?:phase|period|process)|process\s+of\s+consultation|comment\s+period|under\s+evaluation|"
                            r"(?:deemed|declared|found)\s+(?:[\w\u2019'\-]+\s+){0,10}?(?:to\s+be\s+)?complete\b|completeness|"
                            r"(?:has\s+been|have\s+been|was|were|been)\s+accepted|application\s+accepted|accepted\s+(?:for\s+review|as\s+complete)|"
                            r"review\s+(?:has\s+)?(?:now\s+)?(?:commenced|begun|began|started|begins)|"
                            r"remains?\s+(?:subject\s+to|in|under)\s+(?:the\s+)?(?:\w+\s+){0,3}(?:review|evaluation|process)|"
                            r"(?:process\s+(?:is\s+)?(?:remains?\s+)?in\s+progress))")
_NEG_BEFORE = re.compile(r"(?i)(?:\b(?:not|never)\s+(?:yet\s+)?(?:been\s+)?|\bnot\s+yet\s+|\byet\s+to\s+(?:be\s+)?|"
                         r"\bno\s+(?:[\w\-]+\s+){0,5}(?:has|have|had|was|were|is|are)\s+(?:yet\s+)?(?:been\s+)?|\bwithout\s+(?:\w+\s+)?)$")
_RENEW_PENDING = re.compile(r"(?i)\b(?:process\s+(?:to|of)\s+renew\w*|renewal\s+(?:application|process|request)s?\s+(?:is|are|was|were|has|have|remains?)\b|"
                            r"appl(?:y|ied|ies|ication)\s+(?:for\s+)?(?:the\s+|a\s+)?renewal|pending\s+renewal|awaiting\s+(?:the\s+)?renewal|"
                            r"(?:time|period)\s+for\s+(?:the\s+)?renewal|for\s+the\s+renewal\s+of|renewal\s+(?:is|are)\s+(?:pending|underway|in\s+progress))")
_RENEW_DONE = re.compile(r"(?i)\b(?:(?:has|have|had)\s+(?:now\s+)?been\s+(?:renewed|extended|approved|granted)|(?:was|were)\s+(?:renewed|extended|approved|granted)|"
                         r"rec(?:ei|ie)ved|approv(?:ed|al)\s+of\s+(?:the\s+)?renewal)")
_ATTRIB = re.compile(r"(?i)\b(?:the|its|our|their|an?|company['\u2019]s|newly|recently|previously|already|currently|existing|valid)\s+"
                     r"(?:\w+\s+)?$")
_APPLIED_ACT = re.compile(r"(?i)\b(?:submitted|filed|lodged|applied|registered|made\s+(?:an?\s+|its\s+|the\s+)?application|"
                          r"(?:has|have)\s+(?:now\s+)?(?:submitted|filed|applied|lodged)|submits|files|applies)\b")


# 1.0.7 (status, guide QP/QE/QR): stages said in other words
# - a grant named as a noun the company prepares for, looks forward to or makes a condition ("looking forward to
#   receipt of our drill permit", "following issuance of the Small Mine permit", "Granting of the DIA will allow",
#   "in support of receiving mining permit", "when approved, will allow"): awaited (in review) when the company says it is
#   waiting, otherwise still needed (planned)
_GRANT_AWAITED = re.compile(r"(?i)\b(?:look(?:s|ing)?\s+forward\s+to|prepar\w*\s+for|await\w*|in\s+anticipation\s+of|hop(?:e|es|eful|ing)\s+(?:of|for)|"
                            r"anticipat\w+|expect\w*)\s+(?:the\s+)?(?:receipt|receiving|issuance|granting|grant|approval)\b[^.;]{0,25}$")
_GRANT_NEEDED = re.compile(r"(?i)(?:\b(?:following|upon|after|on|subject\s+to|pending|conditional\s+(?:up)?on|precedent\s+(?:including|of)|"
                           r"in\s+support\s+of)\s+(?:the\s+)?(?:earlier\s+of\W+(?:\(\w+\)\s*)*)?"
                           r"(?:receipt|receiving|issuance|granting|grant|approval)\s+(?:of\s+)?(?:the\s+|an?\s+|its\s+|our\s+)?"
                           r"(?:[\w\-]+\s+){0,4}$|^\W{0,3}(?:the\s+)?(?:granting|issuance|approval)\s+of\s+(?:the\s+|an?\s+|its\s+)?(?:[\w\-]+\s+){0,3}$)")
_GRANT_IN_PROCESS = re.compile(r"(?i)\bin\s+the\s+process\s+of\s+(?:receiving|obtaining|securing|being\s+(?:granted|issued))\b[^.;]{0,140}$")
_ADMITTED = re.compile(r"(?i)^[^.;]{0,160}?\b(?:approved|accepted|admitted)\s+for\s+(?:admittance|admission|evaluation|processing)\b")
_APP_ENABLED = re.compile(r"(?i)\b(?:enabl\w+|allow\w*|permitting|paving\s+the\s+way\s+for|ahead\s+of|in\s+preparation\s+for)\s+(?:the\s+|an?\s+|its\s+)?"
                          r"(?:formal\s+)?(?:applications?|submissions?|filings?)\b[^.;]{0,80}$")
_WHEN_GRANT = re.compile(r"(?i)^[\s,]{0,3}(?:when|once|if|until)\s+(?:it\s+is\s+|they\s+are\s+)?(?:approved|granted|issued|received)\b")
# - an application still being written or only begun ("application ... is underway", "in the process of submitting",
#   "preparation of the Plan of Operations is underway", "being prepared for submission", "in advance of <permit>")
_APP_PREP = re.compile(r"(?i)\b(?:in\s+the\s+process\s+of\s+(?:submitting|applying|preparing|filing)|being\s+prepared|"
                       r"(?:preparation|drafting)\s+of|finali[sz]ing|in\s+advance\s+of)\b")
_APP_UNDERWAY = re.compile(r"(?i)^[^.;]{0,25}?\bapplications?\s+(?:\w+\s+){0,6}?(?:is|are)\s+(?:now\s+|currently\s+)?(?:underway|in\s+progress|being\s+prepared)")
_SUBMIT_DONE = re.compile(r"(?i)\b(?:has|have|had)\s+(?:now\s+)?been\s+(?:submitted|filed|lodged)|\b(?:was|were)\s+(?:submitted|filed|lodged)\b")
# - a permit modified or expanded ("The modified Drill Permit increases the area", "approval ... to expand the number of
#   drill pad locations")
_MODIFIED = re.compile(r"(?i)\b(?:modified|amended|expanded|updated)\s+(?:[\w\-]+\s+){0,1}$")
_EXPANDS = re.compile(r"(?i)^[^.;]{0,120}?\bto\s+(?:expand|increase|extend)\s+the\s+(?:number|area|permitted|scope|footprint)\b|"
                     r"^[^.;]{0,40}?\b(?:increases|expands|extends)\s+the\s+(?:number|area|permitted|scope|footprint)\b")


def _status_fix(st, s, a, e, typ, dl_ym=None):
    """1.0.7: the stage, corrected for the wordings above."""
    pre, post = s[max(0, a - 120):a], s[e:e + 160]
    # 1.0.7 (FIX3): a grant being received now ("is now in the process of receiving the final grant ... for the three
    # exploration permits"), and a filing admitted for evaluation ("approved for admittance by the Ministry"), are under
    # review
    if st == "granted" and _GRANT_IN_PROCESS.search(s[max(0, a - 160):a]) and not _PAST_DONE.search(s[max(0, a - 60):e + 40]):
        return "in_review"
    if st == "granted" and _ADMITTED.match(post):
        return "in_review"
    # 1.0.8: a permit expansion or amendment named as a noun ("the proposed 2025 drill permit expansion", "initiating
    # ... environmental permit modifications") is still to come or under way, not done
    if st == "renewed" and re.match(r"(?i)s?\s+(?:expansion|amendment|modification)s?\b", post):
        if re.search(r"(?i)\b(?:proposed|planned|future|next|potential|anticipated)\s+(?:[\w\-]+\s+){0,2}$", s[max(0, a - 40):a]):
            return "planned"
        if re.search(r"(?i)\b(?:initiat\w*|commenc\w*|begin\w*|began|start(?:s|ed|ing)?|seek\w*|pursu\w*|underway)\b", s[max(0, a - 100):a]):
            return "in_review"
    # 1.0.8: an amended or expanded permit the company has filed for is applied ("has filed two amended Notice of Intent
    # permits", "filed an application for the expanded mining permit")
    if st == "renewed" and re.search(r"(?i)\b(?:amended|modified|expanded|revised|updated)\s+(?:[\w\-]+\s+){0,1}$", s[max(0, a - 40):a]) and \
            _APPLIED_ACT.search(s[max(0, a - 120):a]) and not _RENEW_DONE.search(s[max(0, a - 120):e + 60]):
        return "applied"
    # 1.0.8: a grant listed among the approvals still required ("Remaining regulatory requirements to commence
    # construction include receipt of the <permit>") is still needed
    if st == "granted" and not _PAST_DONE.search(s[max(0, a - 60):e + 40]) and \
            re.search(r"(?i)\b(?:remaining|outstanding|required|pending|future|next)\s+(?:[\w\-]+\s+){0,3}(?:approvals?|permits?|authori[sz]ations?|"
                      r"licen[cs]es?|requirements?|milestones?|steps?)\b[^.;]{0,80}\binclud\w*\b[^.;]{0,160}$", s[:a]):
        return "planned"
    # 1.0.8: "the Company expects to be able to deliver ... an approved Exploitation Concession licence during the third
    # quarter": a grant the company expects, named as an attribute, is awaited
    if st == "granted" and re.search(r"(?i)\b(?:an?|the|its)\s+(?:approved|granted|issued)\s+(?:[\w\-]+\s+){0,1}$", s[max(0, a - 30):a]) and \
            re.search(r"(?i)\b(?:expects?|expected|anticipat\w+|aims?|targets?|hop(?:e|es|eful)|on\s+(?:track|schedule))\b[^.;]*$", s[:a]) and \
            not _PAST_DONE.search(s[:e + 40]):
        return "in_review"
    # 1.0.7 (FIX3): an application the sentence names as what something else will make possible ("enabling
    # application to <agency> for the <permit>") is still to be made
    if st == "applied" and _APP_ENABLED.search(s[max(0, a - 120):a]) and not _APPLIED_ACT.search(s[max(0, a - 120):a]):
        return "planned"
    if st == "granted" and not _PAST_DONE.search(s[max(0, a - 60):e + 40]) and \
            re.search(r"(?i)\b(?:look(?:s|ing)?\s+forward\s+to|await(?:s|ing)?|hop(?:e|es|eful|ing)\s+(?:of|for|to\s+receive))\s+"
                      r"(?:receiv\w+\s+|obtain\w+\s+)?(?:the\s+|an?\s+|its\s+|our\s+|their\s+)?(?:(?:[\w\-]+\s+){0,2}|(?:[\w\-]+\s+){1,6}\(\W{0,2}|"
                      r"[^.;]{0,120}?\band\s+(?:formal\s+|final\s+)?(?:approval|receipt|issuance)\s+of\s+(?:the\s+|its\s+)?(?:[\w\-]+\s+){0,2})$",
                      s[max(0, a - 220):a]):
        return "in_review"      # FIX5: "looking forward to a FONSI and formal approval of the EPOO": awaited
    if st == "granted" and not _PAST_DONE.search(s[max(0, a - 60):e + 40]):
        if _GRANT_AWAITED.search(s[max(0, a - 90):a]):
            return "in_review"
        # 1.0.7 (FIX3): "Following receipt of the <permit> in <month year before the release>" is a grant that
        # happened, not one still needed (the date checks then decide whether it is news)
        if _GRANT_NEEDED.search(s[max(0, a - 90):a]) and dl_ym and \
                [1 for mo, y in _MONTH_YEAR.findall(post[:60]) if mo and _ym(mo, y) < dl_ym]:
            return st
        if _GRANT_NEEDED.search(s[max(0, a - 90):a]) or _WHEN_GRANT.match(post):
            return "planned"
    if st in ("applied", "in_review") and typ != "environmental_assessment" and \
            (re.search(r"(?i)\bplanning\s+(?:for|of)\s+(?:the\s+|its\s+|an?\s+)?(?:[\w\-]+\s+){0,3}$", s[max(0, a - 60):a]) and
             re.match(r"(?i)\s*applications?\b", s[e:e + 20]) or
             re.search(r"(?i)\b(?:initiat\w*|commenc\w*|began|begun|start(?:ed|s)?)\s+(?:the\s+process\s+of\s+)?(?:acquiring|obtaining|securing)\s+"
                       r"(?:all\s+)?(?:the\s+)?(?:necessary\s+|required\s+)?$", s[max(0, a - 80):a])) and \
            not _SUBMIT_DONE.search(s[max(0, a - 60):e + 60]):
        return "planned"        # FIX5: "Planning for drill permit applications is now underway", "initiated acquiring all
        #                         necessary permits": nothing filed yet
    if st in ("applied", "in_review") and typ != "environmental_assessment" and \
            (_APP_UNDERWAY.match(post) or _APP_PREP.search(s[max(0, a - 60):a])) and not _SUBMIT_DONE.search(s[max(0, a - 60):e + 60]):
        return "planned"
    if st == "planned" and _SUBMIT_DONE.search(s[max(0, a - 40):e + 60]) and \
            not re.search(r"(?i)\b(?:will|to\s+be|expected|anticipated|once|when)\b", s[max(0, a - 40):e + 30]):
        return "applied"
    if st == "planned" and re.search(r"(?i)\b(?:has|have|had)\s+(?:now\s+)?(?:received|obtained|secured|been\s+granted|been\s+issued)\s+(?:an?\s+|the\s+|its\s+)?(?:[\w\-]+\s+){0,3}$", s[max(0, a - 60):a]):
        return "granted"
    if st == "granted" and (_MODIFIED.search(s[max(0, a - 25):a]) or _EXPANDS.match(post)):
        return "renewed"
    if st == "renewed" and _REVIEW_STRONG.search(s[max(0, a - 120):e + 120]) and not _RENEW_DONE.search(s[max(0, a - 60):e + 60]):
        return "in_review"
    # 1.0.8 (guide QE): a project description or project notice filed starts the assessment -- in review
    if typ == "environmental_assessment" and st in ("applied", "planned") and \
            re.match(r"(?i)(?:initial\s+)?project\s+(?:description|notice)", s[a:e]) and \
            re.search(r"(?i)\b(?:fil(?:ed|es|ing)|submit(?:ted|s|ting)|submission|lodg(?:ed|es|ing))\b", s[max(0, a - 80):e + 40]) and \
            not re.search(r"(?i)\b(?:will|would|intends?|plans?|expects?|expected|to\s+be|prepar\w+|once|when)\b", s[max(0, a - 80):a]):
        return "in_review"
    if typ == "environmental_assessment" and st in ("granted", "planned", "applied") and \
            re.search(r"(?i)\b(?:conclud(?:e|es|ing)|advanc(?:e|es|ing)|ongoing)\s+(?:the\s+|its\s+|our\s+)?(?:[\w\-]+\s+){0,2}$", s[max(0, a - 50):a]) and \
            not _PAST_DONE.search(s[max(0, a - 60):e + 40]):
        return "in_review"
    return st


def _ea_underway(win, rel_a, rel_b):
    """1.0.6 (QE): an assessment the company is preparing or completing is under way ("engages <consultant> for
    the completion of an EIS", "that <Company> prepare an Environmental Assessment") -- not one it completed earlier, and
    not the submission of it."""
    pre = win[max(0, rel_a - 60):rel_a]
    return bool(re.search(r"(?i)\b(?:(?:prepar|complet)(?:e|es|ing)|conduct(?:s|ing)?|undertak(?:e|es|ing)|(?:preparation|completion)\s+of)\s+"
                          r"(?:an?|the|its|their)\s+(?:[\w\-/]+\s+){0,3}$", pre) and
                not re.search(r"(?i)\b(?:following|after|upon|since|with|once)\s+(?:the\s+)?(?:successful\s+)?(?:complet|prepar)", pre) and
                not re.search(r"(?i)\b(?:will|would|expects?|expected|anticipat\w*|targets?|targeted|result\s+in|plans?)\b[^.;]{0,30}"
                              r"(?:complet|prepar|conduct|undertak)\w*\s+(?:of\s+)?(?:an?|the|its|their)\s+(?:[\w\-/]+\s+){0,3}$", pre) and
                not re.match(r"(?i)[\s(\u201c\"\u201d)A-Z]{0,12}(?:submission|filing|application|notification)", win[rel_b:rel_b + 20]))


_WHICH = re.compile(r"(?i)^[\W]{0,4}(?:which|that)\s+(?:\w+\s+){0,3}$")


def _gap(t):
    """1.0.8: how far a stage word sits from a permit: characters, plus a clause break ("the LI remains under
    suspension, the LP was revalidated")."""
    return len(t) + (1000 if re.search(r"[,;:(]|\b(?:and|but|while|whereas|though|although)\b", t) else 0)


def _stage_near(s, a, b, typ=None, spans=()):
    """The stage a sentence gives the permit at s[a:b]: the nearest cue, with contested and renewed winning ties.
    spans: the sentence's other permit mentions (1.0.8: a cue standing between two permits belongs to the nearer one --
    "the Licenca Previa ("LP"), which has now been granted, followed by the installation license")."""
    lo, hi = max(0, a - 170), min(len(s), b + 170)
    win = s[lo:hi]
    rel_a, rel_b = a - lo, b - lo
    oth = [(x - lo, y - lo) for x, y in spans if (y <= a or x >= b) and lo <= x and y <= hi]
    cues = [("contested", _ST_CONTESTED), ("renewed", _ST_RENEWED), ("granted", _ST_GRANTED),
            ("in_review", _ST_REVIEW), ("applied", _ST_APPLIED), ("planned", _ST_PLANNED)]
    if typ == "land_community":
        cues.insert(3, ("granted", _ST_SIGNED))
    cands = []
    negated = False
    for st, rx in cues:
        for m in rx.finditer(win):
            d = rel_a - m.end() if m.end() <= rel_a else (m.start() - rel_b if m.start() >= rel_b else 0)
            if st == "in_review" and \
                    re.match(r"(?i)commenc|initiat|launch|start|beg[iau]n", win[m.start():m.end()]) and \
                    re.match(r"(?i)\W{0,3}(?:(?:on|of|with|the|its|a|an|our|their|this|that|new|first|initial|phase|"
                             r"[\d,.\-]+|\d{4}|[\w\-]+-(?:metre|meter|hole|m)s?|metres?|meters?|m)\W{1,3}){0,5}"
                             r"(?:diamond\s+|core\s+|RC\s+|surface\s+|underground\s+|exploration\s+|field\s+)?"
                             r"(?:drill\w*|exploration|trench\w*|mobili[sz]\w*|construction|operations|production|mining|"
                             r"field\s+work|work\s+program|survey\w*|sampling)\b", win[m.end():m.end() + 70]) and \
                    not re.match(r"(?i)[^.;]{0,50}\b(?:permit\w*|review|assessment|consultation|process|application)", win[m.end():m.end() + 50]):
                continue           # FIX5: "Receives <Permit> and Commences Drilling": the work started, not a review
            if d > 0 and ";" in (win[m.end():rel_a] if m.end() <= rel_a else win[rel_b:m.start()]):
                continue           # FIX5: a stage word across a semicolon belongs to another statement ("Applies for
                #                    <Permit>; Grants Stock Options")
            if st == "contested" and re.match(r"(?i)suspen", win[m.start():m.end()]) and \
                    re.search(r"(?i)\b(?:operations?|production|mining|activities|work|works|drilling)\s+(?:[\w\-]+\s+){0,8}$", win[max(0, m.start() - 80):m.start()]) and \
                    not re.search(r"(?i)permit|licen|approv|authori", win[max(0, m.start() - 80):m.start()]):
                continue           # FIX5: "operations ... were temporarily suspended ... due to the expiration of its permit":
                #                    the work stopped, the permit was not suspended
            if st == "granted" and re.match(r"(?i)approv\w*\s+(?:process|phase|stage|timeline|pathway|path)\b", win[m.start():m.end() + 12]):
                cands.append((d, "in_review", m.start(), m.end()))
                continue           # FIX5: "the final step in the federal approval process for the EA": a process under way
            if st == "granted" and _NEG_BEFORE.search(win[max(0, m.start() - 60):m.start()]):
                negated = True     # 1.0.6: "has not been granted", "no ... has been awarded", "without the need for"
                continue
            if st == "granted" and re.match(r"(?i)(?:approved|granted|issued)\s+[a-z]", win[m.start():m.end() + 2]) and \
                    _ATTRIB.search(win[max(0, m.start() - 30):m.start()]) and \
                    (m.start() >= rel_b or len(win[m.end():rel_a]) > 45 or
                     re.search(r"(?i)\band\b|[,;]|\bwith\b|\bfor\b", win[m.end():rel_a])):
                continue           # 1.0.6: "its approved Mine Plan and an updated EIS", "these newly granted areas"
            if st == "applied" and re.match(r"(?i)(?:submitted|filed|lodged)\b", win[m.start():m.end()]) and \
                    re.search(r"(?i)\b(?:the|its|our|their|an?)\s+(?:previously\s+|already\s+|recently\s+)?$", win[max(0, m.start() - 25):m.start()]) and \
                    m.end() <= rel_a and len(win[m.end():rel_a]) <= 25 and re.search(r"(?i)\b(?:approv|grant|issu|receiv)\w*", win[:m.start()]):
                continue           # 1.0.6: "received approval of the previously submitted Notice of Intent"
            if (st == "granted" or re.search(r"\s", win[rel_a:rel_b])) and typ != "government_policy" and \
                    m.start() >= rel_a and m.end() <= rel_b and d == 0:
                continue           # 1.0.6: the permit's own name ("Industrial Approval") is not its stage; 1.0.7 (FIX3):
                #                    whatever stage word the name holds ("Authorization to Initiate Activities")
            if d > 0 and any((y <= m.start() and (_gap(win[y:m.start()]) < _gap(win[m.end():rel_a]) or _WHICH.match(win[y:m.start()])))
                             if m.end() <= rel_a else (x >= m.end() and _gap(win[m.end():x]) < _gap(win[rel_b:m.start()])) for x, y in oth):
                continue           # 1.0.8: the cue sits between this permit and another, nearer the other
            cands.append((d, st, m.start(), m.end()))
    if not cands:
        if typ == "environmental_assessment" and _ea_underway(win, rel_a, rel_b):
            return "in_review", win
        # 1.0.8: an assessment being advanced or concluded whose only stage word belonged to another permit ("continued
        # advancing environmental assessment work, planning for submission of the EIS")
        if typ == "environmental_assessment" and spans and \
                re.search(r"(?i)(?<!\bto\s)(?<!\bhelp\s)\b(?:concluding|advancing|advances?(?:\s+through)?)\s+(?:the\s+|its\s+|our\s+)?(?:[\w\-]+\s+){0,2}$",
                          win[max(0, rel_a - 50):rel_a]):
            return "in_review", win
        return ("planned", win) if negated else (None, None)
    # 1.0.6: "the required drill permit applications" names the permit, not its stage, when another cue gives one
    if any(c[1] != "planned" for c in cands):
        cands = [c for c in cands if not (c[1] == "planned" and re.match(r"(?i)require", win[c[2]:c[3]]) and
                                          re.search(r"(?i)\b(?:the|all|any|its|our|other|necessary)\s+$", win[max(0, c[2] - 12):c[2]]))]
    cands = [c for c in cands if not (c[1] in ("renewed", "contested") and
                                      re.search(r"(?i)\b(?:can|may|could|will|would)\s+(?:be\s+)?(?:\w+\s+){0,2}$", win[max(0, c[2] - 30):c[2]]))]
    if not cands:
        return None, None
    cands.sort(key=lambda x: (x[0], -STAGE_RANK[x[1]]))
    best = cands[0]
    if best[1] == "applied" and best[3] <= rel_a:
        # FIX5: "submitted a Notice of Intent ... and has received approval subject to bonding": the grant the same
        # sentence reports after the submission is the stage
        g = re.search(r"(?i)^[^.;]{0,140}?\b(?:and|which|that|it)\s+(?:has\s+|have\s+|was\s+|were\s+)?(?:now\s+|since\s+|subsequently\s+)?"
                      r"(?:received\s+(?:the\s+|its\s+|an?\s+|final\s+)?(?:approval|permit|authori[sz]ation|licen[cs]e)|been\s+(?:granted|issued|approved)|"
                      r"(?:was|were)\s+(?:granted|issued|approved))\b(?!\s+(?:the|an?|its)\s+(?:[\w\-]+\s+){0,3}(?:number|receipt|acknowledg\w*|reference))",
                      win[rel_b:])
        if g and not re.search(r"(?i)\b(?:will|would|expects?|expected|anticipat\w*|await\w*|once|when|if|upon)\b", win[rel_b:rel_b + g.end()]):
            return "granted", win
    for d, st, ms, me in cands:
        if st in ("contested", "renewed") and d <= best[0] + 60 and d < 110 and \
                (me <= rel_a + 2 or re.match(r"(?i)renew|extend|amend|modif|suspen|revok|den|refus|reject|cancel|appeal|challeng|unfav|annul|quash|declin|not",
                                            win[ms:me])):
            best = (d, st, ms, me)
            break
    d, st, ms, me = best
    if d > 150:
        return None, None
    # 1.0.6: "it is anticipated that drilling permits will be received": the grant is awaited, not planned
    if st == "planned" and re.match(r"(?i)anticipat|expect", win[ms:me]) and \
            any(c[1] == "granted" and c[0] <= 60 for c in cands):
        st = "in_review"
    # 1.0.6: "anticipates receiving a FONSI ... with approval of the EA": a grant named as a noun in a sentence about
    # what the company expects is still awaited
    if st == "granted" and re.match(r"(?i)approval|receipt|receiving|issuance|grant\b|granting", win[ms:me]) and \
            re.search(r"(?i)\b(?:anticipat(?:es|ed|ing)|expects?|expected|expecting|awaits?|awaiting)\b", win[:ms]) and \
            not _PAST_DONE.search(win[:ms]):
        return "in_review", win
    if st == "granted" and re.search(r"(?i)\bdraft\s+(?:[\w\-]+\s+){0,2}$", win[max(0, ms - 30):ms]):
        return "in_review", win    # 1.0.6: a draft approval or decision is still under review
    if typ == "government_policy":
        if st != "contested" or re.search(r"(?i)\b(?:ruled|rules|designat|lift|revers)", win):
            st = "granted"
    # 1.0.6 (QE): an assessment the company is preparing or completing is under way ("engages <consultant> for
    # the completion of an EIS", "that <Company> prepare an Environmental Assessment")
    if typ == "environmental_assessment" and st in ("granted", "planned") and _ea_underway(win, rel_a, rel_b):
        return "in_review", win
    # 1.0.6: a permitting process the company has only started ("we have commenced the drill permitting process",
    # "Begins Exploration Permitting Process") is a permit still to be applied for
    if st == "in_review" and typ != "environmental_assessment" and \
            (re.match(r"(?i)ting\b", s[b:b + 4]) or re.search(r"(?i)permitting(?:\s+process)?$", s[a:b])) and \
            re.match(r"(?i)commenc|initiat|start|begin|began|begun|launch", win[ms:me]):
        return "planned", win
    # 1.0.6: an application explicitly under review is in review, whatever submission cue sits nearer
    if st in ("applied", "planned") and _REVIEW_STRONG.search(win) and \
            not re.search(r"(?i)\b(?:will|would|expects?\s+to|plans?\s+to)\s+(?:\w+\s+){0,3}(?:be\s+)?(?:reviewed|accepted)", win):
        return "in_review", win
    # 1.0.6: a renewal still being processed
    if st == "renewed" and _RENEW_PENDING.search(win) and not _RENEW_DONE.search(win):
        return "in_review", win
    # a grant or submission spoken of in the future is still to come
    sp = _STRONG_PLANNED.search(s[max(0, a - 260):b + 140])
    if sp and st != "planned" and not _PAST_DONE.search(s[max(0, a - 80):b + 80]):
        return "planned", win
    if st == "granted" and re.match(r"(?i)approv\w*\s+(?:of\s+)?", win[ms:me]) and \
            re.match(r"(?i)[^.;]{0,80}?\b(?:is|are|remains?)\s+(?:now\s+|currently\s+)?(?:expected|anticipated|targeted|pending)", win[me:]):
        return "in_review", win    # "approval of the ESIA is expected in 2026": under review
    if st in ("granted", "applied", "in_review", "renewed"):
        pre = win[max(0, ms - 60):ms]
        fut = _FUTURE.search(pre) and (not re.search(r"(?i)\b(?:has|have|had|was|were|been)\b", win[max(0, ms - 25):ms]) or
                                       re.search(r"(?i)\b(?:once|when|until|after|upon|if|unless)\b[^.;]{0,50}$", pre))
        # 1.0.6: "approval expected mid-2024", "receipt ... is anticipated within two weeks"
        post_await = st == "granted" and re.match(r"(?i)[^.;]{0,60}?\b(?:is|are)?\s*(?:expected|anticipated)\b", win[me:])
        if fut or post_await:
            if st == "granted" and (_AWAITED.search(win[max(0, ms - 80):me]) or post_await or _AWAITED.search(win[me:me + 60]) or
                                    _REVIEW_STRONG.search(win)):
                st = "in_review"   # 1.0.6: a permit the company is waiting for ("anticipates approval of")
            elif st == "granted" and re.search(r"(?i)\bapplication|\bapplied|submitted", win):
                st = "applied"
            elif st in ("granted", "renewed"):
                st = "planned"
            elif st == "in_review" and not _REVIEW_STRONG.search(win):
                st = "planned"
            elif st == "applied" and not _APPLIED_ACT.search(win[max(0, ms - 40):me + 40]):
                st = "planned"     # 1.0.6: "is expected to submit", "the submission ... expected in Q4"
    return st, win


def _clean_hl_proj(p):
    ws = p.split()
    cut = 0
    for i, w in enumerate(ws[:-1]):
        if w in _VERBS_HL or w in _HL_JUNK or w.upper() == w and len(w) > 3 and w not in ("II", "III"):
            cut = i + 1
    ws = ws[cut:]
    while ws and (ws[0][:1].islower() or ws[0] in ("And", "Of", "The", "&")):
        ws = ws[1:]
    if _ROLE_RX.search(" ".join(ws)) or (ws and _pwords(" ".join(ws)) and _pwords(" ".join(ws)) <= _JUNK_CORE):
        return None                    # 1.0.6: "President/CEO of ...", "<Nationality> Gold Property"
    for i, w in enumerate(ws):
        if re.search(r"['\u2019]s?$", w) and i < len(ws) - 1:   # another company's project: "Santana Minerals' Bendigo"
            return None
    if ws and ws[0] in ("Final", "Execution"):
        return None
    # 1.0.7: a permit document's own qualifier ("the Draft Mine Plan of Operations") is no project name
    if ws and ws[0] in ("Draft", "Revised", "Amended", "Proposed", "Updated", "Preliminary", "Modified"):
        return None
    if all(w in ("Major", "Priority", "Strategic", "Project", "Projects", "Provincial", "Federal", "National", "A", "An")
           for w in ws):
        return None                    # "a Major Priority Project" is a designation, not a name
    if any(w in ("Ministry", "Department", "Agency", "Office", "Bureau", "Government", "Commission", "Secretariat",
                 "Directorate", "Minister", "Minist\u00e8re") for w in ws):
        return None
    return " ".join(ws) if len(ws) >= 2 else None


def _projects(t, issuer, spans=()):
    # PERMIT_V2 (1.0.2): candidate names come from the shared helper portal/project_names.py; this reader keeps its
    # own filters (a permit's own name, "adjacent to", another company's project) on top
    out = []
    low = t.lower()
    for pos, p in PN.find(t, issuer):
        # the helper counts positions in its own normalised copy (quotes dropped, capitals re-cased); find the name here
        w0 = p.split()[0].lower()
        # 1.0.6: the full name first -- its first word alone can be another name's ("<Town> Field Office" before
        # the neighbour's "<Town> Flats Project")
        w0 = p.lower() if low.find(p.lower()) >= 0 else (" ".join(p.split()[:2]).lower()
                                                         if low.find(" ".join(p.split()[:2]).lower()) >= 0 else w0)
        k = low.find(w0, max(0, pos - 120))
        if k < 0 or k > pos + 120:
            k = low.find(w0)
        pos = k if k >= 0 else pos
        end = t.find(p.split()[-1], pos) + len(p.split()[-1]) if p.split()[-1] in t[pos:pos + len(p) + 40] else pos + len(p)
        if any(a <= pos < b or pos < a < end for a, b in spans):
            continue
        q = _clean_hl_proj(p) if len(p.split()) >= 2 else None
        pre = t[max(0, pos - 30):pos]
        if re.search(r"(?i)\b(?:adjacent\s+to|near|next\s+to|neighbou?ring|along\s+strike\s+from|(?:south|north|east|west)\s+of|"
                     r"owned\s+by|operated\s+by|including|adjoins?|adjoining|borders?|bordering|abuts?|abutting|"
                     r"contiguous\s+(?:to|with))\s+(?:the\s+|its\s+)?(?:[\w\-\u2019']+\s+){0,3}$", t[max(0, pos - 60):pos]):
            continue
        pm = re.search(r"([A-Z][\w\-]*)['\u2019]s?\s+$", pre)
        if pm and pm.group(1) not in ("Company", "Corporation") and not (issuer and pm.group(1) in issuer):
            continue
        # PERMIT_V2: a project being bought or optioned is not the one the permit is for ("... and Enters into
        # Agreement to Acquire the Nueva Celti Project")
        if re.search(r"(?i)\b(?:acquir\w*|acquisition\s+of|purchas\w*|option\s+(?:to\s+earn|on)|LOI\s+(?:for|on)|"
                     r"letter\s+of\s+intent\s+(?:for|on|to\s+acquire))\s+(?:(?:the|a|an|its|\d+%)\s+)*(?:[\w\-]+\s+){0,3}$",
                     t[max(0, pos - 70):pos]):
            continue
        # 1.0.8: a region's group of projects ("Newfoundland Gold Projects", "Yukon Properties") is a portfolio, not
        # the ground a permit is for
        if q and re.search(r"(?i)\b(?:projects|properties)$", q) and \
                _PLACE_RX.fullmatch(" ".join(w for w in q.split() if w.lower() in _pwords(q))):
            continue
        if q:
            q = re.sub(r"^(?:[Tt]he\s+)?Company['\u2019\u02bc]s\s+", "", q)
            # PERMIT_V2: "the San Antonio and Terranova claims" are two properties, one row each downstream
            for part in PN._parts(q):
                out.append((pos, part))
    for m in re.finditer(r"(?:^|(?<=[\s(\u201c\"'])(?<![A-Z][\w'\-]\s)(?<![A-Z][\w'\-]{2}\s))Project\s+([A-Z][\w'\-]+)(?=[\s,.;)])", t):
        if m.group(1) in _NOT_PROJ_AFTER or m.group(1).isupper():
            continue
        prev = t[max(0, m.start() - 20):m.start()].split()
        if prev and prev[-1][:1].isupper() and prev[-1] not in ("The", "the", "Its", "A", "(", "At", "For", "On"):
            continue
        out.append((m.start(), "Project " + m.group(1)))
    return sorted(out)


def _pwords(p):
    return set(T._pkey(p or "").split())


def _one_edit(x, y):
    if abs(len(x) - len(y)) > 1 or min(len(x), len(y)) < 4:
        return False
    if len(x) == len(y):
        return sum(p != q for p, q in zip(x, y)) == 1
    if len(x) > len(y):
        x, y = y, x
    return any(y[:i] + y[i + 1:] == x for i in range(len(y)))


def _abbr(ws):
    """1.0.8: "Mt"/"Mtn" and "Mount"/"Mountain" name the same place word."""
    return {"mount" if w in ("mt", "mtn", "mount", "mountain") else w for w in ws}


def _same_project(a, b):
    if a and b and PN.same(a, b):
        return True
    wa, wb = _abbr(_pwords(a)), _abbr(_pwords(b))
    if not wa or not wb:
        return not wa and not wb
    if wa <= wb or wb <= wa:
        return True
    if all(w in wb or any(_one_edit(w, v) for v in wb) for w in wa):
        return True
    # "QGQ Project" for the Quesnelle Gold Quartz Mine Project
    ia = "".join(w[0] for w in re.findall(r"[A-Za-z]+", _strip_suffix(a))).lower()
    ib = "".join(w[0] for w in re.findall(r"[A-Za-z]+", _strip_suffix(b))).lower()
    return (len(wa) == 1 and len(next(iter(wa))) >= 3 and ib.startswith(next(iter(wa)))) or \
        (len(wb) == 1 and len(next(iter(wb))) >= 3 and ia.startswith(next(iter(wb))))


# FIX5: one permit or approval for several named projects is one row per project (guide QX): "permits for drilling on
# its <A>, <B> and <C> Properties", "for the Company's <A> and <B> projects", "the <A> project, the <B> project, and the
# <C> project"
_LN = r"(?<![/\w])(?:[A-Z](?![\w\-]*['\u2019]s\b)[\w'\u2019\-]*|de|del|la|el)(?:\s+(?:[A-Z](?![\w\-]*['\u2019]s\b)[\w'\u2019\-]*|de|del|la|el)){0,2}"
_LIST_PL = re.compile(r"\b(?:(?:the|its|our|their)\s+|(?:the\s+)?(?:Company|[A-Z][\w\-]+)['\u2019]s\s+)?(?:(?:wholly|100%)[\s-]owned\s+)?"
                      r"(" + _LN + r"(?:\s*,\s*" + _LN + r")*\s*,?\s+and\s+" + _LN + r")\s+([Pp]rojects|[Pp]roperties|PROJECTS|PROPERTIES)\b")
_LIST_SG = re.compile(r"\b(?:the\s+)?(?:historic\s+)?(" + _LN + r")\s+([Pp]roject|[Pp]roperty)(?:\s*,\s*(?:the\s+)?(?:historic\s+)?"
                      r"(" + _LN + r")\s+(?:[Pp]roject|[Pp]roperty)){0,3},?\s+and\s+(?:the\s+)?(?:historic\s+)?" + _LN + r"\s+(?:[Pp]roject|[Pp]roperty)\b")
_LIST_BAD = {"Company", "Gold", "Silver", "Copper", "Mining", "Exploration", "Mineral", "Option", "Earn", "Joint", "Phase",
             "North", "South", "East", "West", "Central", "Two", "Three", "Both", "Several", "Other", "New", "All", "These", "Such"}


_PARTY = r"(?:(?-i:[A-Z]{2,6})\b|(?:[A-Z][\w'\u2019\-]+\s+){1,3}(?:First\s+Nations?|Dene\s+Nation|Cree\s+Nation|Nation|Band|M[e\u00e9]tis\s+Nation))"
_PARTY_LIST = re.compile(r"\bwith\s+(?:each\s+of\s+)?(?:the\s+)?(" + _PARTY + r"(?:\s*,\s*(?:the\s+)?" + _PARTY + r")*\s*,?\s+and\s+(?:the\s+)?" + _PARTY + r")")


def _split_parties(s, a, e):
    """FIX5: the communities an agreement at s[a:e] is signed with, when it names several ("Benefit Agreements with the
    <A>, <B>, and <C>", each defined as a Nation earlier): one row per counterparty (guide QM)."""
    m = _PARTY_LIST.search(s, e, min(len(s), e + 120))
    if not m or m.start() - e > 40:
        return []
    return [x.strip() for x in re.split(r"\s*,\s*(?:and\s+)?(?:the\s+)?|\s+and\s+(?:the\s+)?", m.group(1)) if x.strip()]


def _split_names(s, a, e):
    """FIX5: the project names a list next to the permit at s[a:e] gives, with the head noun, or []."""
    best = None
    for rx in (_LIST_PL, _LIST_SG):
        for m in rx.finditer(s, e):
            d = m.start() - e
            if d > 100 or (best and d >= best[0]) or \
                    not re.search(r"(?i)\b(?:for|on|at|over|covering)\s+(?:(?:the|its|our|their|both|two|three|all)\s+|(?:the\s+)?(?:Company|[A-Z][\w\-]+)['\u2019]s\s+)*$",
                                  s[e:m.start()]) or ";" in s[e:m.start()]:
                continue        # the list the permit is "for", "on" or "at"
            if rx is _LIST_PL:
                names = [x.strip() for x in re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+", m.group(1)) if x.strip()]
                head = "Property" if m.group(2).lower().startswith("propert") else "Project"
            else:
                names = [x.strip() for x in re.findall(r"(?:^|,\s*(?:and\s+)?|\s+and\s+)(?:the\s+)?(?:historic\s+)?(" + _LN + r")\s+(?:[Pp]roject|[Pp]roperty)",
                                                        m.group(0))]
                head = m.group(2).title()
            if len(names) < 2 or any(n.split()[0] in _LIST_BAD or n.lower() in ("the", "its") for n in names):
                continue
            best = (d, [n + " " + head for n in names])
    return best[1] if best else []


def _strip_suffix(p):
    return re.sub(r"\s+(?:Project|Property|Mine|Mines|Deposit|Projects|Properties)$", "", p or "")


def _main_project(projs):
    if not projs:
        return None
    count, first = {}, {}
    for pos, p in projs:
        k = T._pkey(p)
        count[k] = count.get(k, 0) + 1
        first.setdefault(k, (pos, p))
    k = max(count, key=lambda x: (count[x], -first[x][0]))
    return first[k][1]


def _project_near(a, projs_s, hl_proj, main_proj):
    near = None
    for p_pos, p in projs_s:
        dist = abs(p_pos - a)
        if near is None or dist < near[0]:
            near = (dist, p)
    if near and near[0] < 220:
        p = near[1]
        # PERMIT_V2: a mine or deposit inside the project the headline names ("the Phoenix ISR mine" at Wheeler River)
        if hl_proj and not _same_project(p, hl_proj) and re.search(r"(?i)\b(?:Mine|Deposit|Zone|Pit)$", p) and \
                re.search(r"(?i)\b(?:Project|Property)$", hl_proj):
            return hl_proj
        # 1.0.6: a deposit, zone or target inside the release's main project is that project ("the <X> Deposit"
        # at the <Y> Gold Project, "the <Z> Target" at the <W> Property)
        if main_proj and not _same_project(p, main_proj) and _PART_RX.search(p) and _WHOLE_RX.search(main_proj):
            return main_proj
        # the headline's fuller name for the same project
        for q in (hl_proj, main_proj):
            if q and _same_project(p, q) and len(q) > len(p):
                return q
        return p
    p = hl_proj or main_proj
    if p and main_proj and not _same_project(p, main_proj) and _PART_RX.search(p) and _WHOLE_RX.search(main_proj):
        return main_proj
    return p


# 1.0.6: a permit sentence that names the ground it covers in lower case ("a mining license covering the <X>
# Cu/Zn massive sulfide showing", "a drill permit on its nearby <Y> Ridge project"): that ground is the permit's
# project, not the release's main one
_NAMED_AT = re.compile(r"\b(?:at|on|for|over|covering)\s+(?:the\s+|its\s+|our\s+|their\s+)?(?:(?:nearby|neighbou?ring|adjacent|"
                       r"wholly[\s-]owned|100%[\s-]owned|newly[\s-]\w+|recently[\s-]\w+)\s+)?"
                       r"((?:[A-Z][a-z\u00e0-\u00ff'\u2019\-]+)(?:\s+(?:[A-Z][a-z\u00e0-\u00ff'\u2019\-]+|de|del|la|el)){0,2})"
                       r"((?:\s+[\w/\-]+){0,3}?\s+(?:project|property|claims|showing|land\s+package)\b)")
_NAMED_NOT = re.compile(r"(?i)\b(?:the|its|our|this|that|phase|company|corporation|ministry|department|bureau|government|"
                        r"province|state|office|agency|forest|service|nation|board|exchange|mining|exploration|environmental|"
                        r"drill|drilling|permit|plan|notice|operations?|contract|issues?|draft|national|federal|provincial|"
                        r"mineral|licen[cs]e|concession|approval|assessment|statement|impact)\b")


def _named_ground(s, a, e, issuer, text):
    """(distance, position, name) of ground the permit sentence names in lower case next to the permit, or None."""
    best = None
    for m in _NAMED_AT.finditer(s, max(0, a - 120), min(len(s), e + 140)):
        n = m.group(1).strip()
        if m.start(1) < e and m.end(1) > a:
            continue                      # inside the permit's own name
        if _NAMED_NOT.search(n) or _PLACE_RX.fullmatch(n) or (issuer and n.split()[0] in issuer) or len(n) < 4 or \
                re.search(r"['\u2019]s?$", n):
            continue
        d = m.start() - e if m.start() >= e else a - m.end()
        best = best if best is not None and best[0] <= max(d, 0) else (max(d, 0), m.start(1), n + " Project")
    return best


_PART_RX = re.compile(r"(?i)\b(?:Deposits?|Zones?|Pits?|Targets?|Prospects?|Showings?|Veins?|Target\s+Complex|Anomal(?:y|ies))$")
_WHOLE_RX = re.compile(r"(?i)\b(?:Project|Property|Properties|Projects)$")


_NATION = re.compile(r"(?i)First\s+Nations?|Nation\b|Nishnaabeg|Anishinaabe|Cree|M\u00e9tis|Metis|Band\b|communit|County\b|"
                     r"Council\b|iwi|ejido")


_AUTH_CACHE = {}


def _auth_list(s):
    if s not in _AUTH_CACHE:
        if len(_AUTH_CACHE) > 400:
            _AUTH_CACHE.clear()
            _AUTH_NEW.clear()
        _AUTH_CACHE[s], _AUTH_NEW[s] = _authorities(s)
    return _AUTH_CACHE[s]


def _auth_new(s):
    """FIX5: the bodies in s that only the FIX5 patterns know."""
    _auth_list(s)
    return _AUTH_NEW.get(s, ())


def _short(sents, cap=1200, piece=700):
    """Tables and SEDAR report pages run for thousands of characters without a full stop: cut them into pieces so
    every look-around stays local (a 40k-character run otherwise costs seconds)."""
    out = []
    for s in sents:
        while len(s) > cap:
            k = s.rfind(" ", piece - 200, piece + 200)
            k = k if k > 0 else piece
            out.append(s[:k])
            s = s[k:].lstrip()
        out.append(s)
    return out


def _auth_near(s, a, b, typ, gov_ok=False):
    # FIX5: the body named right after the permit as its issuer ("the Land Use License issued by the <Region> Inuit
    # Association") is the authority, whatever kind of body it is
    m = re.match(r"\s*(?:\([^)]{0,40}\)\s*)?,?\s*(?:(?:which|that)\s+)?(?:(?:was|were|has\s+been|have\s+been)\s+)?(?:issued|granted)\s+by\s+(?:the\s+)?"
                 r"([A-Z][\w\-]+(?:\s+(?:[A-Z][\w\-]+|of\s+the|of|and|de)){0,6}(?<!\sof)(?<!\sthe)(?<!\sand)(?<!\sde))(?![\w'\u2019])", s[b:b + 120])
    if m and len(m.group(1).split()) >= 2 and not re.search(r"\b(?:Inc|Corp|Ltd|Limited|LLC|Company)\b", m.group(1)) and \
            not re.match(r"['\u2019]s\b", s[b + m.end(1):b + m.end(1) + 3]):
        k = b + m.start(1)
        known = [n for x, y, n in _auth_list(s) if x == k]
        if known:
            return known[0]
        whole = _auth_whole(s, k, b + m.end(1), m.group(1))
        return whole[2] if whole else _CutName(m.group(1))
    best = best_new = None
    for x, y, name in _auth_list(s):
        is_nation = bool(_NATION.search(name))
        if is_nation and re.search(r"\bCounty\b", name) and b <= x <= b + 40 and \
                re.search(r"(?i)\b(?:from|by)\s+(?:the\s+)?(?:[A-Z][\w\-]+\s+){0,2}$", s[max(0, x - 30):x]):
            is_nation = False   # FIX5: "Extension for Drill Permit from <Name> County" -- the county issued it
        if typ == "land_community" and not is_nation and name not in ("Department of Conservation",):
            continue
        if typ not in ("land_community", "other") and is_nation:
            continue
        if typ == "government_policy" and not re.search(r"(?i)court|TRF", name) and \
                not (gov_ok and re.search(r"(?i)^(?:Province|Government|State)\s+of|Government$|Ministry|Minist", name)):
            continue
        if re.search(r"(?i)\b(?:in|of|located|within|near)\s+(?:the\s+)?$", s[max(0, x - 14):x]) and \
                re.match(r"(?i)(?:State|Province)\s+of|[A-Z][a-z]+\s+County", name):
            continue
        if re.match(r"\s*['\u2019]s\s+(?:[A-Z][\w\-]*\s+){0,4}(?:Bureau|Service|Agency|Division|Branch|Office|Board|Commission)\b", s[y:y + 60]):
            continue            # FIX5: "the US Department of the Interior's Bureau of Land Management": the bureau issued it
        d = a - y if y <= a else (x - b if x >= b else 0)
        d = max(d, 0)
        if name in _auth_new(s):
            if x >= b and re.search(r"(?i)\b(?:approval|permit|licen[cs]e|authori[sz]ation|consent)s?\b", s[b:x]):
                continue        # "requires a change of land use approval from <body>": that approval's body
            if d <= 160 and (best_new is None or d < best_new[0]):
                best_new = (d, name)
            continue
        if best is None or d < best[0]:
            best = (d, name)
    if best and best[0] <= 160:
        return best[1]
    if best_new:
        return best_new[1]      # FIX5: a newly known body only where the known patterns name none
    if typ == "government_policy" and not gov_ok:
        return _auth_near(s, a, b, typ, True)
    return None


# PERMIT_V2 (1.0.2): when a row's own sentence names no authority, another sentence of the release often does
# ("The ATI permit is issued by Quebec's Ministry of ...", "received the required permits from the Saskatchewan
# Ministry of Environment", "accepted by the ... EAO"). Only a sentence that ties an authority to a permit counts.
_AUTH_TIE = re.compile(r"(?i)\b(?:from|by|to|with|before)\s+(?:the\s+)?(?:State\s+of\s+|Province\s+of\s+)?$")
_PERMIT_WORD = re.compile(r"(?i)\bpermit|licen[cs]|approv|authori[sz]|assessment|\bEA\b|\bEIA|\bEIS\b|notice\s+of|"
                          r"plan\s+of\s+operations?|application|consent|project\s+description|concession")
_TYPE_WORDS = {"drill_exploration": r"drill|explor|work|trench|program|ATI|notice\s+of\s+work",
               "environmental_assessment": r"environment|assessment|\bEA\b|EIA|EIS|impact|project\s+description",
               "plan_of_operations": r"plan\s+of\s+operations?|notice|drill|explor",
               "mining_licence": r"mining|licen[cs]e|lease|concession|exploitation",
               "construction_operating": r"construct|operat|licen[cs]e|facility|plant|mill",
               "water": r"water", "land_community": r"agreement|access|community|nation",
               "government_policy": r"priority|strategic|designat|policy", "other": r"permit|approv"}


def _release_auth(row, sents, typ):
    cands = []
    tw = re.compile(r"(?i)" + _TYPE_WORDS.get(typ, "permit"))
    for i, t_ in enumerate(sents):
        if not _PERMIT_WORD.search(t_):
            continue
        for x, y, name in _auth_list(t_):
            if name in _auth_new(t_):
                # FIX5: a newly known body next to another kind of permit ("review with the NPC" of the mine permit)
                # is that permit's, not this one's
                near = sorted((min(abs(x - pe), abs(pa - y)), pt) for pa, pe, pt, _ in _mentions(t_, 0))
                if near and near[0][1] != typ and near[0][0] < 150:
                    continue
            if not _AUTH_TIE.search(t_[max(0, x - 30):x]) and \
                    not re.match(r"(?i)\s*(?:\(\s*[\"\u201c]?\w+[\"\u201d]?\s*\)\s*)?(?:has|have|had)?\s*(?:issued|granted|approved|accepted|"
                                 r"authori[sz]ed|signed)", t_[y:y + 40]) and \
                    not re.search(r"(?i)\b(?:rec(?:ei|ie)v(?:ed|es)|obtained|secured)\s+(?:the\s+)?$", t_[max(0, x - 30):x]) and \
                    not _OF_HAS_GRANTED.match(t_[y:y + 70]):
                continue          # FIX5: "received <body> authorization", "<body> of the <Country> has approved"
            if _auth_near(t_, x, y, typ) != name:
                continue          # the same type rules as a row's own sentence (nations, courts, places)
            fed = bool(re.search(r"(?i)\bCanad|\bFederal|U\.?S\.?\b|Bureau\s+of\s+Land|Forest\s+Service|CNSC|IAAC", name))
            label = (row.get("permit_name") or "") + " " + row["sent"][max(0, row["a"] - 60):row["e"] + 20]
            if re.search(r"(?i)\bprovincial|\bstate\b", label) and fed or re.search(r"(?i)\bfederal", label) and not fed:
                continue          # a provincial approval is not the federal agency's, and the reverse
            # a permitting verb next to the authority ("received ... from", "submitted to", "issued by"), not
            # "consultations with" or "support from"
            if not _AUTH_VERB.search(t_[max(0, x - 110):x]) and not _AUTH_VERB.match(t_[y:y + 40].lstrip(" )\u201d\"(\u201c")) and \
                    not _OF_HAS_GRANTED.match(t_[y:y + 70]):
                continue
            words = [w for w in re.findall(r"[A-Za-z]{4,}", row.get("permit_name") or "")
                     if w.lower() not in ("permit", "permits", "approval", "approvals", "licence", "license", "application")]
            score = (2 if tw.search(t_) else 0) + (1 if any(w.lower() in t_.lower() for w in words) else 0) + \
                (1 if row["project"] and row["project"].split()[0] in t_ else 0) + \
                (1 if re.match(r"\s*(?:The|This|These|Such)\s+(?:[\w\-]+\s+){0,2}(?:permits?|licen[cs]es?|approvals?|"
                               r"authori[sz]ations?)\b", t_) else 0)      # "The permit was issued by ..."
            if _GEN_RX.fullmatch(row.get("permit_name") or ""):
                head = re.search(r"(?i)permit|authori[sz]ation|approval", row["permit_name"]).group(0)
                if re.search(r"(?i)\b" + head + r"s?\s+(?:from|by)\s+(?:the\s+)?$", t_[max(0, x - 40):x]):
                    score += 3      # FIX5: "authorization from <body> to proceed": the body named with the permit's own word
            cands.append((score, -i, name, name in _auth_new(t_)))
    if not cands:
        return None
    if any(not c[3] for c in cands):
        cands = [c for c in cands if not c[3]]   # FIX5: a newly known body only where the known patterns tie none
    if len({c[2] for c in cands}) == 1 and max(c[0] for c in cands) >= 1:
        return cands[0][2]        # the only authority the release ties to a permit like this one
    best = max(cands)
    return best[2] if best[0] >= 2 else None


_OF_HAS_GRANTED = re.compile(r"(?i)\s*o\s?f\s+(?:the\s+)?[A-Z][^.;,()]{0,40}?\s+(?:has|have|had)\s+(?:issued|granted|approved|accepted)")
_AUTH_VERB = re.compile(r"(?i)\b(?:rec(?:ei|ie)v\w*|receipt|grant\w*|issu\w*|approv\w*|submit\w*|appl(?:y|ied|ies|ication)\w*|"
                        r"filed|fil(?:es|ing)|review\w*|accept\w*|obtain\w*|secur\w*|authori[sz]\w*|permitting|"
                        r"has\s+(?:issued|granted|approved|accepted))\b")


# PERMIT_V2 (1.0.2): a permit's term or expiry is often a sentence away from the permit ("The ATI permit was issued
# on February 16, 2026, and is valid for 3 years."; "valid from September 1, 2024 to September 30, 2027")
_VALID_FROM = re.compile(r"(?i)\b(?:valid(?:ity)?(?:\s+period)?|in\s+(?:force|effect)|effective|years?)\s+from\s+")
_UNTIL = re.compile(r"(?i)\b(?:valid(?:ity)?(?:\s+period)?|in\s+(?:force|effect)|expir\w*|renewed|extended|rights?\b[^.]{0,80}?|"
                    r"holds?\s+a\s+validity\s+period)\s+(?:until|through|to)\s+")
_TERM_WORDS = re.compile(r"(?i)\bpermit(?!ting)|licen[cs]e|lease|approv|authori[sz]|concession|title|\bDIA\b|\bATI\b|notice")
_TERM_WORDS_AGR = re.compile(r"(?i)\bpermit(?!ting)|licen[cs]e|lease|agreement|approv|authori[sz]|concession")
# a duration that is not the permit's: a project or mine life, a consulting or marketing contract, a review timeline
_TERM_NOT = re.compile(r"(?i)\b(?:project|mine|operating)\s+life|life[\s-]+of[\s-]+mine|investor\s+relations|consult\w*|"
                       r"marketing|NEPA\s+process|timeline|time\s*frame|study|studies|offtake|production\s+sharing|"
                       r"PSC\b|scoping|process\s+(?:is|will|to)")


def _term_in(t_):
    """(term as written, expiry date) a sentence gives for a permit, or (None, None)."""
    m = _VALID_FROM.search(t_)
    if m:
        ds = list(re.finditer(r"(?i)" + T._DATE_RX, t_[m.end():m.end() + 90]))
        if len(ds) >= 2 and re.search(r"(?i)\b(?:to|until|through)\b", t_[m.end() + ds[0].end():m.end() + ds[1].start()]):
            d1, d2 = ds[0].group(0).strip(), ds[1].group(0).strip()
            tm = _TERM_RX.search(t_) or _TERM_PRE.search(t_)
            return ((tm.group(1) + " (" if tm else "") + d1 + " to " + d2 + (")" if tm else ""), T._iso(ds[1]))
    tm = _TERM_RX.search(t_) or _TERM_PRE.search(t_)
    if tm:
        return tm.group(1), None
    m = _UNTIL.search(t_)
    if m:
        d = re.match(r"(?i)\s*(?:" + T._DATE_RX + r")", t_[m.end():m.end() + 40])
        if d:
            return "until " + d.group(0).strip(), T._iso(re.search(r"(?i)" + T._DATE_RX, d.group(0)))
    return None, None


# PERMIT_V2 (1.0.2): who holds the permit, when the release says it is someone other than the company itself (a
# subsidiary, a former owner, the title holder), and what the permit allows (holes, platforms, wells, metres,
# hectares, tonnes a day).
_ORG = (r"((?:Mr\.|Ms\.|Mrs\.)\s+[A-Z][\w\-]+(?:\s+[A-Z][\w\-]+){0,2}|"
        r"[A-Z][\w&'\-]*(?:\s+(?:[A-Z][\w&'\-]*|de|del|y|&|and)){0,6}?\s*,?\s+"
        r"(?:S\.A\.(?:\s*de\s*C\.V\.)?|S\.A\.C\.|S\.A\.S\.|SAS|S\.R\.L\.|SRL|S\.L\.|Sarl|SARL|SARLU|Lda\.?|Ltda\.?|"
        r"Ltd\.?|Limited|Inc\.?|Corp\.?|Corporation|LLC|L\.L\.C\.|Pty\.?\s+Ltd\.?|GmbH|AB|Oy|AS|SpA|S\.p\.A\.)"
        r"(?![\w]))")
_HOLDER_RX = [
    re.compile(r"(?i:(?:permits?|licen[cs]es?|concessions?|titles?|authori[sz]ations?|approvals?|PLs?)\b[^.;]{0,60}?"
               r"(?:(?<!formerly\s)held\s+by|in\s+the\s+name\s+of|(?:issued|granted|awarded|registered)\s+to)|"
               r"on\s+behalf\s+of|(?:mining\s+)?(?:title|permit|licen[cs]e)\s+holder,?)\s+(?:(?:the\s+Company['\u2019]s|its)\s+"
               r"(?:\d+%[\s-]+owned\s+|wholly[\s-]+owned\s+)?(?:[A-Z][a-z]+\s+)?subsidiary,?\s+)?" + _ORG),
    re.compile(r"(?i:former\s+(?:property\s+)?owner|vendor|optionor),?\s+" + _ORG +
               r"(?=,?\s+(?:had|has|have|holds?|obtained|received|applied|submitted))"),
]
_SCOPE_RX = re.compile(r"(?i)\b((?:up\s+to\s+|a\s+(?:total|maximum)\s+of\s+)?(?:\d[\d,.]*|one|two|three|four|five|six|seven|"
                       r"eight|nine|ten|twelve|fifteen|twenty|thirty|forty|fifty)(?:\s*\(\d+\))?\s*"
                       r"(?:(?:diamond\s+|RC\s+|core\s+)?drill\s*holes?|holes?|drill\s+(?:pads|platforms|sites)|pads|platforms|"
                       r"wells|trenches|line\s+kilomet(?:re|er)s|met(?:re|er)s\s+of\s+(?:diamond\s+|core\s+|RC\s+|reverse\s+"
                       r"circulation\s+)?drilling|(?<=up\sto\s)[\d,]{3,}\s*met(?:re|er)s|(?:tonnes|tons)\s+(?:per|a)\s+(?:day|year)|"
                       r"tpd|(?:tonne\s+)?bulk\s+samples?|(?:hectares|ha|acres)(?=[^.]{0,40}\b(?:disturb|surface|clear)))(?=\W))")


def _holder_in(sents_, issuer, lead=""):
    # the company itself, as its dateline names it ("Upside Gold Corp. (" ... "CSE: UG)")
    own = {m.group(1).lower() for m in re.finditer(r"([A-Z][\w\-]{2,})[\w\s.&,\-]{0,50}?\(\s*[\u201c\"]?[^)]{0,40}?"
                                                  r"(?:TSX|CSE|NYSE|OTC|ASX|NASDAQ|TSXV|Company)", lead[:1500])}
    for t_ in sents_:
        for rx in _HOLDER_RX:
            m = rx.search(t_)
            if not m:
                continue
            n = re.sub(r"\s+", " ", m.group(1)).strip(" ,")
            if re.match(r"(?i)(?:the\s+)?(?:Company|Corporation|Issuer)\b", n) or (issuer and n.split()[0] in issuer):
                continue
            if not n[:1].isupper() or re.search(r"\b[A-Z]{3,}\s+[A-Z]{3,}\b", n):
                continue          # "THE BOARD Power One ..." is a run of headline capitals, not a name
            if n.split()[0].lower() in own:
                continue
            return n[:120]
    return None


def _scope_in(sents_):
    for t_ in sents_:
        if not re.search(r"(?i)\b(?:allow|authori[sz]|permit(?:s|ting)?\s+(?:for|to|the)|approv\w*\s+(?:for|to)|to\s+(?:drill|"
                         r"conduct|construct|complete|carry|undertake)|cover|include)", t_):
            continue
        ms = []
        for m in _SCOPE_RX.finditer(t_):
            x = re.sub(r"\s+", " ", m.group(1)).strip()
            if re.match(r"(?:19|20)\d\d\b", x) or re.match(r"\d+\.\d", x):
                continue          # "2021 drill hole" is a year; "16.0 metres" is an assay interval
            if x.lower() not in [y.lower() for y in ms]:
                ms.append(x)
        if ms:
            return "; ".join(ms[:2])[:120]
    return None


def _clean_name(n):
    n = re.sub(r"\s+", " ", n).strip(" ,;:")
    if n.isupper() and len(n) > 5:
        n = n.title()
    return n[:1].upper() + n[1:] if n else n


_EA_GENERIC = re.compile(r"(?i)^environmental\s+(?:permits?|licen[cs]es?|approvals?|authori[sz]ations?|clearances?)$")


def _ctype(typ, name, s, auth, hl):
    """Justin's type rules on top of the name."""
    if typ == "other" and _GEN_RX.fullmatch(name):
        k = s.lower().find(name.lower())
        after = s[k + len(name):k + len(name) + 120] if k >= 0 else ""
        if re.search(r"(?i)\b(?:operat\w*|production|processing|plant|mill|construct\w*|recovery|restart|resume|transport\w*)", name + " " + after):
            return "construction_operating"
        if re.search(r"(?i)\b(?:drill\w*|explor\w*|survey\w*|geophysic\w*|prospecting|trench\w*|sampl\w*)", name + " " + after) or \
                not re.search(r"(?i)\b(?:remediat\w*|clean\w*|road|water)", after) and _DRILLISH.search(hl + " " + s):
            return "drill_exploration"
        return "other"
    if typ == "drill_exploration" and re.match(r"(?i)land[\s-]+use\s+licen", name) and \
            re.search(r"(?i)\b(?:Inuit|First\s+Nations?|Association|Corporation)\b", s):
        return "other"          # FIX5: a land use licence an Inuit association or a First Nation issues for its lands
    if typ == "drill_exploration" and auth in ("Bureau of Land Management", "U.S. Forest Service"):
        return "plan_of_operations"
    if typ == "environmental_assessment" and re.search(r"(?i)\breport\b", name) and _DRILLISH.search(s + " " + hl):
        return "drill_exploration"
    if typ == "environmental_assessment" and _EA_GENERIC.match(name) and re.search(r"(?i)\bDIA\b|drill", s):
        return "drill_exploration"
    return typ


_NAME_GEN = {"permit", "permits", "licence", "licences", "license", "licenses", "approval", "approvals", "authorization",
             "authorisation", "authorizations", "application", "the", "a", "of", "for", "to", "update", "updated", "and",
             "long", "term", "long-term", "provincial", "federal", "major", "new", "additional", "process", "work",
             "drilling", "drill", "exploration", "notice", "level", "environmental", "impact", "assessment", "study",
             "statement", "agreements", "agreement", "land", "access", "surface", "mining", "mine", "title", "titles",
             "certificate", "registration", "lease", "leases", "concession", "concessions", "term", "renewal", "revised",
             "plan", "plans", "operations", "operation", "social", "studies", "notices", "permitting"}


def _name_core(n):
    return {w for w in re.findall(r"[a-z0-9]+", T._fold(n or "")) if w not in _NAME_GEN}


def _initials(n):
    ws = [w for w in re.findall(r"[A-Za-z]+", n or "") if w.lower() not in ("of", "and", "the", "for", "de", "du", "des")]
    return "".join(w[0] for w in ws).lower()


def _stem(w):
    return re.sub(r"(?:ing|ions?|ed|es|e|s)$", "", w) if len(w) > 5 else w


def _names_compatible(a, b):
    ca, cb = _name_core(a), _name_core(b)
    if not ca or not cb or ca & cb:
        return True
    if {_stem(w) for w in ca} & {_stem(w) for w in cb}:
        return True            # 1.0.8: "Operating License" is the "license to operate"
    ia, ib = _initials(a), _initials(b)
    return any(x in ib for x in ca if len(x) >= 2) or any(x in ia for x in cb if len(x) >= 2)


_KNOWN_NAMES = {n for _, n in _AUTH_KNOWN}


def _auth_words(a):
    return {w for w in re.findall(r"[a-z]+", T._fold(a or "")) if w not in ("of", "the", "and", "for", "ministry", "department",
                                                                          "government", "province", "state", "de", "du", "des")}


def _auth_merge(ra, fa):
    """Two mentions can be the same permit unless they name two different bodies."""
    if not ra or not fa or ra == fa:
        return True
    if _auth_words(ra) & _auth_words(fa):
        return True
    if re.match(r"(?i)(?:State|Province|Government)\s+of\b|.*\bGovernment$", ra) or \
            re.match(r"(?i)(?:State|Province|Government)\s+of\b|.*\bGovernment$", fa):
        return True
    return (ra in _KNOWN_NAMES) != (fa in _KNOWN_NAMES)


_ACQ = re.compile(r"(?i)\b(?:acquir\w+|acquisition|purchas\w+|option\s+to\s+earn|interest\s+in\s+(?:a|the)\s+|letter\s+of\s+intent|LOI)\b")
# 1.0.6 (held permits): a permit the company already holds, named as what it works under or as what a property is,
# is background in any stage -- "undertaken pursuant to an exploration permit", "all major environmental approvals in
# place", "in compliance with the requirements issued in the RCA Environmental Approval", "the exploration permit grants
# the holder the exclusive right to", "X is a mining concession granted by", "the property has an approved exploration
# permit", "our recently signed exploration agreement", "one of the largest environmental assessment approved projects"
_HELD_PRE = re.compile(r"(?i)(?:\bpursuant\s+to\s+(?:an?|the|its|our|their)\s+(?:[\w\-]+\s+){0,3}|"
                       r"\b(?:compliance|accordance|conformity)\s+with\s+(?:the\s+)?(?:[\w\-]+\s+){0,5}|"
                       r"\b(?:has|have|holds?|had)\s+(?:an?|the|all|its|valid)\s+(?:[\w\-]+\s+){0,2}(?:approved|valid|granted|active|current|required|necessary)\s+(?:[\w\-]+\s+){0,2}|"
                       r"(?<!received\s)(?<!obtained\s)(?<!secured\s)\b(?:its|our|their)\s+(?:recently\s+|previously\s+|newly\s+)?(?:approved|granted|issued|signed|executed)\s+(?:[\w\-]+\s+){0,2}|"
                       r"\b(?:the|its|our)\s+(?:recently|previously)\s+(?:approved|granted|issued|signed|executed)\s+(?:[\w\-]+\s+){0,2}|"
                       r"\b(?:its|our|their|the)\s+original\s+(?:[\w\-]+\s+){0,2}|"
                       # 1.0.7 (FIX3): the permit something was approved with ("a spur road which was approved with the
                       # environmental assessment for the mine")
                       r"\b(?:approved|permitted|authori[sz]ed|covered)\s+(?:with|under|through|as\s+part\s+of)\s+(?:the|its|our|their)\s+(?:[\w\-]+\s+){0,2}|"
                       # the permit that made the reported work possible ("an aggressive step-out owing to receipt of the
                       # Exploration Plan of Operations")
                       r"\b(?:owing|thanks|due)\s+to\s+(?:the\s+)?(?:receipt|approval|grant(?:ing)?|issuance)\s+of\s+(?:the|its|an?|our)\s+(?:[\w\-]+\s+){0,3})$")
_HELD_AROUND = re.compile(r"(?i)^[^.;]{0,12}?(?<!\bnow\s)(?:\b(?:is|are|already|now)\s+)?in\s+place\b|"
                          r"^[^.;]{0,20}?\b(?:gives?|grants?|confers?|provides?)\s+(?:the\s+)?(?:holder|company|[A-Z][\w\-]*)\s+(?:the\s+)?(?:exclusive\s+|sole\s+)?rights?\s+to\b")
_HELD_POST = re.compile(r"(?i)^(?:\s*\([^)]{0,30}\))?\s+(?:approved|permitted)\s+(?:[\w\-]+\s+){0,2}(?:projects?|mines?|developments?|operations?)\b")
_HELD_IS = re.compile(r"(?i)\b(?:is|are)\s+an?\s+(?:[\w\-]+\s+){0,2}$")
# 1.0.6 (a permit named as a place): "the northern zone of the mining permit", "the target is in a Mineral Exploration
# Permit", "the mining concession areas", "concession fees"
_PLACE_PRE = re.compile(r"(?i)(?:\b(?:zones?|areas?|parts?|portions?|boundar(?:y|ies)|limits?|territory|footprint|perimeter|"
                        r"corners?|edges?|sections?|sides?)\s+of\s+(?:its|the|our|their|this|that|each)\s+(?:[\w\-]+\s+){0,3}|"
                        r"\b(?:is|are|lies|lie|located|situated|sits)\s+(?:with)?in\s+(?:an?|the|its|our|their)\s+(?:[\w\-]+\s+){0,3}|"
                        r"\b(?:throughout|across|within|inside)\s+(?:the|its|our|their|this|that|each)\s+(?:[\w\-]+\s+){0,3}|"
                        # the permit a new one is converted from ("conversion of the existing exploration license to a
                        # mining license")
                        r"\b(?:conver(?:t|ts|ted|ting|sion)|upgrad\w+)\s+(?:of\s+)?(?:a\s+portion\s+of\s+|part\s+of\s+)?(?:the|its|an?|our|existing)\s+(?:[\w\-]+\s+){0,3}|"
                        # the permit an application is made on ("the licences applied for are for the exploration
                        # permit No. ...", "applications covering the existing exploration licence")
                        r"\b(?:applied\s+for|applications?|requests?)\s+(?:(?:are|is|were|was)\s+(?:for|over|on|covering)|covering|over)\s+"
                        r"(?:the|its|our|their|existing)\s+(?:[\w\-]+\s+){0,3})$")
_PLACE_POST = re.compile(r"(?i)^(?:\s*\([^)]{0,30}\))?\s+(?:areas?|boundar(?:y|ies)|blocks?|holders?|fees?|payments?|taxes|polygons?|"
                         r"grid|limits?)\b")
_DEAL_TENURE_HL = re.compile(r"(?i)\b(?:acquir\w*|acquisition|options?|optioned|purchas\w*|letter\s+of\s+intent|LOI|sale\s+of|sells?|"
                             r"divest\w*|earn[\s-]?in|ownership)\b")
_GRANT_ACT = re.compile(r"(?i)\b(?:has|have|had|was|were)\s+(?:now\s+)?(?:been\s+)?(?:received|granted|issued|approved|awarded|renewed)|"
                        r"\breceived\b|\breceipt\s+of|\b(?:granted|issued|approved)\s+(?:by|to|on)\b")
# 1.0.7 (FIX3): a reclamation bond posted for an approved permit is that permit's last step ("has posted a reclamation
# bond with the BLM as part of the requirement for its approved drilling permit"): news, not a permit held
_BOND_POSTED = re.compile(r"(?i)\b(?:has|have)\s+(?:now\s+)?post(?:ed)?\s+(?:an?\s+|the\s+|its\s+)?(?:(?:reclamation|surety|financial|"
                          r"performance)\s+)?bond\b")
_DESCRIBES = re.compile(r"(?i)^(?:\s*\([^)]{0,40}\))*\s+(?:provides|includes|details|describes|contemplates|outlines|sets\s+out)\b")
_NOW_NEWS = re.compile(r"(?i)\b(?:has|have)\s+(?:now|just)\b|\bnow\s+(?:in\s+the\s+process|received|obtained|secured|granted|been)\b")
_TICKER_PRE = re.compile(r"(?:TSX|TSXV|TSX-V|CSE|NYSE|NYSE\s+American|OTC\w*|ASX|NASDAQ|AMEX|FSE|Frankfurt|LSE|AIM|BVL|JSE)\s*[:\-]\s*$")
_ANNIV = re.compile(r"(?i)anniversary")
_CLAIMS = re.compile(r"(?i)\bclaim\s+blocks?\b|\bmineral\s+claims?\b|\bstak(?:ed|ing)\b")
_MONTH_YEAR = re.compile(r"(?i)\b(?:in|on|during|since|announced)\s+(?:(?:early|mid|late)[\s-]+)?((?:" + T._MON + r"|Q[1-4]|H[12]))?\.?,?\s*(?:\d{1,2},?\s+)?((?:19|20)\d\d)\b")
_LEASE_IDS = re.compile(r"(?i)\b(?:Leases|Licen[cs]es|Permits|Concessions|Titles|Tenures)\s+(?:Nos?\.?\s*)?(\d{4,})\s*(?:,|and|&)\s*"
                        r"(?:No\.?\s*)?(\d{4,})(?:\s*(?:,|and|&)\s*(?:No\.?\s*)?(\d{4,}))?")

# 1.0.7 (OWN_NEWS): a release whose headline says it is about something else (a deal, a drill start, a financing,
# results, a corporate update) names permits mostly as background. Its rows need the permit's own news; these are the
# ways such releases mention permits the company already holds or that changed stage long ago.
# - the headline names no permit or permitting at all
_HL_TOPIC = re.compile(r"(?i)\bpermit|\blicen[cs]|\bapprov|\bauthori[sz]|\bconcession|\blease\b|\bEIA\b|\bESIA\b|\bEIS\b|"
                       r"\bEA\b|environmental|notice\s+of|plan\s+of\s+operations?|record\s+of\s+decision|\bROD\b|\bDIA\b|"
                       r"agreement|consultation|fast-41|priority\s+project|\bNOI\b|\bNoW\b|support|judicial|appeal|"
                       r"injunction|moratorium|suspen\w+")
# - a mining release names at least one of these (a cannabis or technology company's zoning permit is not ours)
_MINING_RX = re.compile(r"(?i)\b(?:mines?|mining|minerali[sz]\w*|minerals?|drill\w*|explor\w*|deposits?|ore|claims?|concessions?|"
                        r"tenements?|metals?|gold|silver|copper|nickel|zinc|cobalt|manganese|tungsten|vanadium|molybdenum|"
                        r"antimony|iron|platinum|palladium|pgms?|lithium|uranium|graphite|potash|phosphate|diamonds?|coal|"
                        r"tailings|quarry|rare\s+earths?|oil|gas|petroleum|brine)\b")
# - the company gives a property away: "Options <X> Project to <Y>", "Spin-out of <X> Properties", "Sells <X> to <Y>"
_ASSET = r"(?:[\w'\u2019&.,\-]+\s+){0,5}?(?:projects?|propert(?:y|ies)|claims|assets?|portfolio|tenements|licen[cs]es|interests?)\b"
_DISPOSAL_HL = re.compile(r"(?i)\b(?:options|sells|vends)\s+(?:out\s+)?" + _ASSET + r"[^.;]{0,40}?\bto\s+[A-Z]|"
                          r"\bspin[\s-]?(?:out|off)\s+(?:of\s+)?" + _ASSET + r"|\bdivest")
# - the ground the company holds, described: "the property consists of four granted exploration licences", "comprises
#   4,047 hectares of granted ... licences", "holds a 100% interest in the ... Exploration License", "interests over land
#   holdings ... which includes the exploration permit granted to", "under an active exploration permit"
_TENURE_PRE = re.compile(r"(?i)(?:\b(?:consists?|consisting|composed|made\s+up)\s+of\b|\bcompris(?:es|ing|ed)\b|"
                         r"\b(?:holds?|has|owns?|had)\s+(?:an?\s+|the\s+)?(?:[\d.]+\s*%\s+|majority\s+|controlling\s+)?"
                         r"(?:interest|stake|ownership)\s+(?:in|over)\b|"
                         r"\b(?:holds?|owns?|controls?)\s+(?:[\d.]+\s*%\s+of\s+)?(?:the|its|all|an?)\b|"
                         r"\b(?:land\s+(?:holdings?|position|package)|tenure\s+position)\b|"
                         r"\b(?:under|with)\s+(?:an?|the|its|their)\s+(?:currently\s+)?(?:active|valid|current|existing)\s+)"
                         r"[^.;]{0,110}$")
_HOLDINGS_LIST = re.compile(r"(?i)\b(?:portfolio|propert(?:y|ies)|holdings|assets|land\s+package)\s+(?:currently\s+|now\s+)?"
                            r"(?:consists?\s+of|compris(?:es|ing)|includes?)\s*:?\s*(?:\(?1[).]|\(?i[).]|\(?a[).])")
# - a permit held, said as a possession: "With drill permits in hand", "the Project's approved environmental
#   assessment", "the mining concession issued by the National Mining Agency" (no finite verb: a description)
_HELD_HAND = re.compile(r"(?i)^[^.;]{0,15}?\bin\s+hand\b")
_HELD_POSS = re.compile(r"(?i)\b[\w\-]+['\u2019]s?\s+(?:recently\s+|previously\s+)?(?:approved|granted|issued|valid|current|active|existing)\s+"
                        r"(?:[\w\-]+\s+){0,2}$")
_PARTICIPLE_POST = re.compile(r"(?i)^(?:\s*\([^)]{0,30}\))?\s*,?\s+(?:issued|granted|approved|awarded)\s+(?:by|to|under)\b")
_FINITE_GRANT = re.compile(r"(?i)\b(?:has|have|had|was|were|is|are)\s+(?:now\s+|recently\s+|just\s+)?(?:been\s+)?"
                           r"(?:received|granted|issued|approved|awarded|obtained|secured)\b|"
                           r"\b(?:received|obtained|secured)\b|\bnow\s+(?:been\s+)?(?:granted|approved|issued|received|in\s+hand)\b")
# - earlier news quoted: "(see August 2, 2022 news release)", "Recently <Co> announced that ...", "as announced on"
_EARLIER_NEWS = re.compile(r"(?i)\(\s*(?:see|refer\s+to|as\s+announced)\b[^)]{0,90}\b(?:news|press)\s+releases?\b|"
                           r"\b(?:recently|earlier|previously|had)\s+(?:[\w\-]+\s+){0,2}announced\b|"
                           r"\bas\s+(?:previously\s+|first\s+)?(?:announced|reported|disclosed)\b|"
                           r"\bannounced\s+(?:that\s+)?(?:on|in)\s+(?:" + T._MON + r")")
# - a recap of past milestones ("... having achieved key milestones including:")
_RECAP = re.compile(r"(?i)\b(?:achieved|completed|reached|accomplished)\s+(?:[\w\-]+\s+){0,3}milestones?,?\s*"
                    r"(?:including|such\s+as|to\s+date|:)")
# - claims staked or applied for, ground added: not permits (guide QT), in any wording
_STAKING = re.compile(r"(?i)\bstak(?:ed|ing)\b|\bland\s+position\b|\bapplications?\s+for\s+(?:an?\s+)?(?:additional\s+|further\s+|new\s+)?"
                      r"(?:\d[\d,]*|one|two|three|four|five|six|seven|eight|nine|ten)?\s*(?:new\s+)?(?:mining\s+|mineral\s+)?claims\b|"
                      r"\b(?:secure|acquire|purchase|purchased|acquired|secured|acquiring)\s+(?:100%\s+of\s+)?the\s+mining\s+rights\s+to\b")
# - 1.0.8: a grant said to be in the past, and ground held described by what the permit covers
_PAST_GRANT = re.compile(r"(?i)\b(?:(?:was|were|had\s+been|have\s+been|has\s+been)\s+(?:\w+\s+)?(?:issued|granted|approved|obtained|received)\s+"
                         r"(?:[\w\-]+\s+){0,2}in\s+the\s+past\b|in\s+the\s+past\b[^.;]{0,40}\b(?:issued|granted|approved|obtained|received)\b|"
                         r"\b(?:\d+|two|three|four|five|six|seven|eight|nine|ten|several|many)\s+years\s+ago\b)")
_HOLDS_COVERING = re.compile(r"(?i)\b(?:now\s+|currently\s+)?(?:holds?|owns?)\s+(?:an?|one|two|three|four|five|six|\d+)\s+"
                             r"(?:\d+%[\s-]*owned\s+|wholly[\s-]owned\s+|granted\s+|active\s+|valid\s+)?(?:[\w\-]+\s+){0,2}$")
# - a stage of long ago: "lease applications were lodged in 1888", "historic mining leases"
_HISTORIC = re.compile(r"(?i)\bhistoric(?:al|ally)?\s+(?:[\w\-]+\s+){0,2}$")
_OLD_YEAR = re.compile(r"(?i)(?:\b(?:in|since|during|year|circa)\s+|\b" + T._MON + r"\.?\s+(?:\d{1,2},?\s+)?)(?:1[0-8]\d\d|19[0-8]\d)\b|"
                       r"\b1[0-8]\d0s\b")
# - a Notice of Intent(ion) to exercise an option or to buy is a deal step, not a permit
_NOI_DEAL = re.compile(r"(?i)^\W{0,3}(?:ion)?\s+to\s+(?:exercise|acquire|purchase|terminate|complete\s+the\s+(?:acquisition|purchase))\b")
# - a newswire listing page (other companies' headlines with timestamps) is not the company's news
_LISTING = re.compile(r"\d{4}-\d\d-\d\d \d\d?:\d\d (?:AM|PM)")
# - the company's boilerplate paragraph ("ABOUT <CO> ... <Co> is a mining and exploration company ...")
_BOILER = re.compile(r"(?:\bABOUT\s+[A-Z]|\bAbout\s+[A-Z]).{0,120}?\b(?:is|are)\s+an?\s+(?:[\w\-,]+\s+){0,12}?"
                     r"(?:company|corporation|explorer|developer|producer)\b")
# - an assessment named among technical work streams ("resource modelling, beneficiation test work, environmental
#   assessment, and operation logistics"): a study, not a permitting step
_WORKLIST = re.compile(r"(?i)\b(?:test\s*work|model(?:l)?ing|estimation|logistics|metallurg\w+|geotechnical|engineering|"
                       r"hydrogeolog\w+|mine\s+planning|trade-?off|scoping|economic\s+(?:analysis|studies))\b")
# - all permits at once ("has obtained all permits to drill in this area"): no one permit is named
_ALL_PERMITS = re.compile(r"(?i)\ball\s+(?:the\s+|its\s+|of\s+the\s+)?(?:required\s+|necessary\s+|relevant\s+|applicable\s+|needed\s+)?$")
# - a hypothetical ("the mining license may be increased further pending ...")
_MAYBE = re.compile(r"(?i)^[^.;]{0,25}?\b(?:may|might|could)\s+(?:also\s+|potentially\s+)?be\s+\w+ed\b")
# - an assessment filed for drill permits (guide QD) ("an EIA report, to be submitted to SEMARNAT for drill permits")
_EA_FOR_DRILL = re.compile(r"(?i)^[^.;]{0,140}?\bfor\s+(?:the\s+|its\s+|their\s+)?(?:\w+\s+)?drill(?:ing)?\s+(?:permits?|authori[sz]ations?|approvals?)\b")
# - 1.0.8: one permit named twice in a row: the assessment is the drill permit's form ("Environmental Impact Assessment
#   - Semi-detailed ("EIA-Sd") drill permit application"); a permit named as what another one is for ("Environmental
#   Clearance Certificates ("ECC") for Exclusive Prospecting License", "the LP for the Full Mining License")
_EA_IS_DRILL = re.compile(r"(?i)^\s*(?:[-\u2013\u2014]\s*[\w\-]+)?[\s)\"\u201d]*(?:\(\s*[\"\u201c]?[\w\-]+[\"\u201d]?\s*\)\s*)?[\s)\"\u201d]*"
                          r"(?:drill(?:ing)?|exploration)\s+permits?\b")
_FOR_PERMIT = re.compile(r"(?i)[)\"\u201d\s]*(?:[\w\-]+[)\"\u201d\s]*){0,2}(?:\(\s*[\"\u201c]?[\w\-]+[\"\u201d]?\s*\)\s*)?"
                         r"\s*for\s+(?:the\s+|its\s+|an?\s+)?(?:[\w\-]+\s+){0,2}")
# - 1.0.8: a project named in a clause about earlier news is that earlier permit's ground
_GENERIC_PERMITS = re.compile(r"(?i)^(?:[\w\-]+\s+)?(?:permits|licen[cs]es|approvals|authori[sz]ations)$")
_STILL_NEEDED = re.compile(r"(?i)\b(?:will\s+(?:also\s+)?be\s+(?:required|needed)|(?:is|are)\s+(?:still\s+|also\s+)?(?:required|needed)|"
                           r"still\s+(?:required|needed)|will\s+(?:need|require)|remain\s+to\s+be\s+obtained|outstanding)\b")
_APP_TO_FILE = re.compile(r"(?i)\b(?:intends?|plans?|expects?|expected|anticipat\w+|scheduled|prepar\w+|will|to)\s+(?:\w+\s+){0,2}"
                          r"(?:file|filed|submit|submitted|apply|lodge|lodged)\b")
_US_FED = re.compile(r"\b(?:BLM|USFS)\b|Bureau\s+of\s+Land\s+Management|(?:U\.?S\.?|United\s+States|USDA)\s+Forest\s+Service")
_AWAIT_WORDS = re.compile(r"(?i)\b(?:anticipat\w*|expect\w*|await\w*|look(?:s|ing)?\s+forward\s+to|hop(?:e|es|eful|ing))\b")
_NOW_FILED = re.compile(r"(?i)\b(?:has|have)\s+(?:now\s+|just\s+|today\s+)?(?:formally\s+)?(?:filed|submitted|lodged|applied)\b")
_EARLIER_CLAUSE = re.compile(r"(?i)\b(?:previously|earlier|recently)\s+(?:announced|reported|disclosed)\b|\bas\s+(?:previously\s+)?announced\b")
# - 1.0.8: a further change to a permit the company holds ("The next anticipated extension of the current Plan of
#   Operations, currently under internal review", "a further expansion of the USFS PoO") is its own permit step, not the
#   permit's earlier grant
_NEXT_AMEND = re.compile(r"(?i)\b(?:next|further|future|subsequent|planned|proposed|anticipated)\s+(?:anticipated\s+|planned\s+|proposed\s+)?"
                         r"(?:extension|expansion|amendment|modification|enlargement)s?\s+(?:of|to)\s+(?:the\s+|its\s+|our\s+)?"
                         r"(?:current\s+|existing\s+|approved\s+)?(?:[\w\-]+\s+){0,2}$")
# - a new officer's or director's past work ("led permitting ... environmental assessment" at other companies)
_PEOPLE_HL = re.compile(r"(?i)\b(?:appoint\w*|joins?|names?\s+(?:new\s+)?(?:ceo|president|director|chair)|resign\w*|"
                        r"board\s+(?:of\s+directors|appointment|changes?)|management\s+changes?|retire\w*)\b")
_BIO = re.compile(r"(?i)\b(?:experience|career|served|serving\s+as|previously|formerly|background|track\s+record|"
                  r"(?:he|she)\s+(?:was|has|led|is)|his|her|led\s+the|responsible\s+for|role\s+(?:at|with|as))\b")


_STAGE_VERB = re.compile(r"(?i)\b(?:receiv\w*|grant\w*|issu\w*|approv\w*|obtain\w*|submit\w*|filed|lodged|renew\w*|sign\w*|"
                         r"execut\w*|award\w*|authori[sz]\w*|accept\w*)")


_VERB_OF = {"granted": r"(?i)\b(?:rec(?:ei|ie)v\w*|grant\w*|issu\w*|approv\w*|obtain\w*|award\w*|authori[sz]\w*|sign\w*|execut\w*)",
            "applied": r"(?i)\b(?:submit\w*|filed|lodged|appl(?:ied|ication))",
            "renewed": r"(?i)\b(?:renew\w*|extend\w*|amend\w*|approv\w*|receiv\w*|issu\w*)",
            "contested": r"(?i)\b(?:den\w+|refus\w+|revok\w+|suspend\w*|appeal\w*|reject\w*)"}


def _stage_date(r, dateline):
    """The date the stage happened when a sentence about it states one ('on October 10, 2025, the Company received ...');
    otherwise None and the item's date stands."""
    if not dateline:
        return None
    for t_ in r.get("sents") or [r["sent"]]:
        if t_ is r["sent"] and r["hl"]:
            continue
        got = []
        for m in re.finditer(r"(?i)" + T._DATE_RX, t_):
            pre = t_[max(0, m.start() - 40):m.start()]
            if re.search(r"(?i)\b(?:until|through|to|expir\w*|valid|from|dated|effective|between|and|before|after|by)\s*$", pre):
                continue
            # 1.0.6: the date a news release announced it ("the permit previously announced on January 18") is not
            # the stage's date
            if re.search(r"(?i)\b(?:announced|reported|disclosed|released|news\s+release|press\s+release)\s+(?:on\s+|of\s+|dated\s+)?$", pre):
                continue
            wk = re.search(r"(?i)\bon\s+(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s*$", pre)
            if not re.search(r"(?i)\bon\s*$|^\s*,", pre[-5:] + t_[m.end():m.end() + 2]) and not re.search(r"(?i)\bon\s*$", pre) and \
                    not wk and not (got and re.search(r"(?i)\band\s+(?:the\s+)?(?:final|second|last)\s+(?:[\w\-]+\s+){0,2}on\s*$", pre)):
                continue
            ctx = t_[max(0, m.start() - 90):m.end() + 90]
            if (wk or re.match(r"\s*,", t_[m.end():m.end() + 3])):
                ctx = t_[max(0, m.start() - 90):m.end() + 220]    # FIX5: "on Friday, <date>, through ... received"
            verbs = _VERB_OF.get(r["status"])
            if not verbs or not (re.search(verbs, ctx) or got and re.search(r"(?i)\band\s+(?:the\s+)?(?:final|second|last)\b", pre)):
                continue
            iso = T._iso(m)
            if iso and iso <= dateline and iso >= "%04d%s" % (int(dateline[:4]) - 1, dateline[4:]):
                got.append(iso)
        if got:
            return max(got)     # FIX5: "the initial volume issued on <date>, and the final volume on <date>": the
            #                     stage is the last step
    return None


def _ym(mo, y):
    """A month index for 'June 2023', 'Q2 2023' or '2023' (a bare year counts as its December)."""
    mo = (mo or "").lower()
    if mo[:1] == "q":
        m = int(mo[1]) * 3
    elif mo[:1] == "h" and mo[1:2].isdigit():
        m = int(mo[1]) * 6
    else:
        m = T._MONTHS.get(mo[:3], 12)
    return int(y) * 12 + m


def _place_skip(t):
    """Drop the dateline ('VANCOUVER, British Columbia, June 25, 2026 --') so the office is not the project's place."""
    return re.sub(r"^[^.]{0,200}?\b(?:19|20)\d\d\s*(?:--|[\u2013\u2014:/]|-\s)", " ", t[:1200], count=1) + t[1200:]


# PERMIT_V1 recall fix (2026-09-22): a headline that reports a permit without naming one of the permit patterns --
# "Receives Approval for Drill Program", "Submits Permit Application", "Commences Permitting", "Permit Renewed".
# Only the headline is read this way; the body still needs a named permit.
_HL_GENERIC = re.compile(
    r"(?i)\bpermit\s+applications?\b|\bpermits?\b|\bpermitting(?:\s+process)?\b|"
    r"\b(?:(?:BLM|USFS|final|regulatory|government|ministerial)\s+)?(?:approvals?|authori[sz]ations?)\s+"
    r"(?:(?:from|by)\s+[^,.;]{1,40}?\s+)?(?:to|for)\s+(?:(?:the|its|an?|extensive|expanded|phase\s+\w+|\d[\d,.]*[\s-]*"
    r"(?:metres?|meters?|m|foot|feet|ft|holes?))\s+)*(?:[\w\-/]+\s+){0,4}?(?:drill\w*|exploration|trench\w*|work|field|"
    r"construct\w*|build)(?:\s+(?:and\s+)?(?:drill\w*\s+)?(?:programs?|plans?|activities|work))?|"
    r"\bregulatory\s+approvals?\b(?=[^.]{0,80}\bdrill)|(?<=\bReceipt\sof\s)regulatory\s+approvals?\b")
_HL_STAGE = re.compile(r"(?i)\b(?:rec(?:ei|ie)v|grant|approv|obtain|issu|secur|award|submit|fil(?:es|ed|ing)|appl(?:y|ies|ied)|"
                       r"lodg|commenc|initiat|begin|begins|start|renew|extend|authori[sz])")
_HL_OTHERS = re.compile(r"(?i)\b(?:acknowledg\w*|congratulat\w*|welcomes?)\b|\bgranted\s+to\s+[A-Z]")
_HL_NOT_PERMIT = re.compile(r"(?i)\b(?:private\s+placement|financings?|offerings?|listing|IPO|grant\s+from|re-?log|"
                            r"drill\s+core|shares?|warrants?|options?|transaction|acquisition|name\s+change)\b")
_HL_PERMITTING = re.compile(r"(?i)\b(?:commenc|initiat|begin|begins|start|launch)\w*\s+(?:the\s+|its\s+)?(?:[\w\-,]+\s+){0,5}?"
                            r"permitting\b")
_HL_PERMIT_VERB = re.compile(r"(?i)\b(?:rec(?:ei|ie)v\w*|receipt|grant\w*|approv\w*|obtain\w*|issu\w*|secur\w*|award\w*|submit\w*|"
                             r"fil(?:es|ed|ing)|appl(?:y|ies|ied|ication)|lodg\w*|renew\w*|extend\w*|in\s+hand)\b")
_HL_BUILD = re.compile(r"(?i)\b(?:plant|construction|mill|facility|refinery|processing)\b")


_CAVEAT = re.compile(r"(?i)\b(?:materially\s+)?affected\s+by\s+(?:[\w\-]+,?\s+){0,3}(?:environmental|permitting)\b[^.;]{0,60}?\b(?:legal|title|taxation)\b")


# ------------------------------------------------------------------ the item
_FLS = re.compile(r"\b(?:Cautionary\s+(?:Note|Statement|Language)s?\s+(?:[Rr]egarding|[Cc]oncerning|[Aa]bout|on|[Ww]ith\s+[Rr]espect\s+to)\s+)?"
                  r"(?:Forward[\s-]+Looking\s+(?:Statements?|Information)|FORWARD[\s-]+LOOKING\s+(?:STATEMENTS?|INFORMATION))\b|"
                  r"(?i:\bthis\s+(?:news\s+|press\s+)?release\s+(?:contains|includes|may\s+contain)\s+(?:certain\s+)?\W?forward)")


# ------------------------------------------------------------------ 1.0.5: several projects per release (helper 1.0.5)
_PM_PART = r"\s+(?:portion|part|sector|area|zone|showing|target|block|grid)s?\b"


def _pm_part_of(name, text):
    """The release calls the name a part of something ('the Sullipek East portion of its flagship Vortex/Vallieres
    Project', 'Sullipek East Showing'): not a project of its own for this purpose."""
    core = re.sub(r"(?i)\s+(?:Project|Property|Projects|Properties|Mine)$", "", name or "").strip()
    return bool(core) and re.search(r"(?i)\b" + re.escape(core) + _PM_PART, text) is not None


_PM_FIRST = {"la", "el", "san", "santa", "mount", "mt", "west", "east", "north", "south", "upper", "lower", "new", "big",
             "little", "red", "lac", "lake", "rio", "cerro", "monte", "le", "les", "st", "saint", "black", "white",
             "grand", "golden", "gold", "silver", "copper"}
_PM_GENERIC = re.compile(r"(?i)^(?:production|highlighting|development|pipeline|dual|mexican|svp|neighbou?ring|flagship|"
                         r"near-mine|u\.s\.|us|canadian|nevada|australian|quarter|base\s+case|record|extension|"
                         r"engineering|tailings|ounce|hectare|discovered|ownership|transparency|fast-41|project\s+permitting|"
                         r"permitting|ug|cv|spin-out|ramp-up|basin|next|milestone|gold\s+copper|copper\s+gold)\b")
# rev 4: a name written as a reference point in the sentence ('near the Meadowbank Mine', '11 km from the Thompson Mine')
_PM_NEAR = r"(?i)(?:\bnear(?:by)?|adjacent\s+to|next\s+to|proxim\w*\s+to|surround\w*|along\s+strike\s+from|\bkm\b[^.]{0,30})\s+" \
           r"(?:the\s+|its\s+)?(?:[\w'\-]+\s+){0,2}"


def _pm_short(p):
    """The short form a release uses for a project: 'Lagoa Salgada Polymetallic Project' -> 'Lagoa', 'La Preciosa
    Project' -> 'La Preciosa'."""
    ws = re.sub(r"(?i)\s+(?:Projects?|Property|Properties|Mines?|Complex|Deposits?|Concessions?|Claims?)$", "",
                p or "").split()
    if not ws:
        return None
    k = 2 if ws[0].lower() in _PM_FIRST and len(ws) > 1 else 1
    s = " ".join(ws[:k])
    return s if len(s) >= 4 and s.lower() not in _PM_SHORT_BAD else None


# rev 5: short words that are never a project's short name on their own
_PM_SHORT_BAD = {"project", "projects", "property", "mine", "detailed", "contact", "initial", "final", "main", "central",
                 "base", "new", "north", "south", "east", "west", "phase", "stage", "mining", "mineral", "exploration"}
# rev 5: capitalised words that may stand straight before a project's short name ('At Lagoa', "the Company's Kon\u00e9")
_PM_LEAD_OK = {"at", "in", "the", "for", "on", "of", "and", "its", "our", "their", "to", "with", "from", "as", "by",
               "company's", "corporation's", "while", "both", "each", "all", "a", "an", "this", "that"}
_PM_TAIL_OK = {"project", "projects", "property", "properties", "mine", "mines", "deposit", "deposits", "claims",
               "concession", "concessions", "complex", "permit", "permits", "licence", "license", "lease",
               "plan", "drill", "drilling", "exploration", "environmental", "water", "eis", "eia", "esia", "ea",
               "notice", "application", "approval", "certificate", "authorization", "authorisation"}   # rev 6


def _pm_joined(s, m, full):
    """rev 5: the short name at s[m.start():m.end()] is part of another capitalised name -- a capitalised word
    straight before it ('New Brunswick', "Pure Energy's Clayton", 'Mine Centre', 'North Thompson') or straight after
    it that is not the project's own next word ('Quiulacocha Community', 'Brunswick Mining Act')."""
    pre = re.search(r"([A-Z][\w'\u2019\-]*)\s+$", s[max(0, m.start() - 40):m.start()])
    if pre and pre.group(1).lower().replace("\u2019", "'") not in _PM_LEAD_OK:
        return True
    if re.match(r"(?:\s+[A-Z][\w'\u2019\-]*){0,3}\s+(?:Resources?|Resource['\u2019]s|Inc|Corp|Corporation|Ltd|Limited|plc|LLC)\b",
                s[m.end():m.end() + 60]):
        return True               # the company ('Nickel Rock Resource's Nickel Project')
    if re.match(r"\s+(?:area|zone|target|prospect|showing|trend|corridor)s?\b", s[m.end():m.end() + 30], re.I):
        return True               # a place inside a project ('in Petit Yao area')
    con = re.match(r"\s+(do|de|da|dos|das|del|di|du|des)\s+[A-Z]", s[m.end():m.end() + 30])
    if con and not (full or "")[len(m.group(0)):].lower().startswith(" " + con.group(1) + " "):
        return True               # a longer name ('Buti\u00e1-Fazenda do Posto')
    nxt = re.match(r"\s+([A-Z][\w'\-]*)", s[m.end():m.end() + 40])
    if nxt:
        rest = (full or "")[len(m.group(0)):].split()
        w = nxt.group(1)
        if w.lower() not in _PM_TAIL_OK and not (rest and rest[0].lower() == w.lower()):
            return True
    return False


def _pm_project_at(b, s, a, cur, names, others=(), issuer=None):
    """A permit sentence that names no project in full, on a release about several projects: the project it names in
    short form ('At Lagoa Salgada, the permit ...'), and only then -- no guessing from nearby text (rev 4: the flattened
    text made a look-back pick the wrong project). Never a generic name, the company's own name ('Regulus Concessions'),
    a name the sentence uses as a reference point ('near the Meadowbank Mine'), the tail of a longer name ('Peak' of
    'Spring Peak'), or the one it already has."""
    if len(names) < 2:
        return None
    if b.find(s[:60]) < 0:
        return None
    co = (issuer or "").split()[:1]
    allp = [p for p in dict.fromkeys(list(names) + list(others)) if p]
    junk = [p for p in allp if _PM_GENERIC.search(p)]
    cands = [p for p in allp if not _PM_GENERIC.search(p) and not (co and p.split()[:1] == co)
             and not any(_same_project(p, q) for q in junk)
             and not re.search(r"(?i)\b(?:deposits?|prospects?|targets?|zones?|showings?)$", p)]   # rev 5: not a part
    csh = _pm_short(cur) if cur else None
    if csh and any(abs(m.start() - a) <= 200
                   for m in re.finditer(r"(?<![\w'])" + re.escape(csh) + r"(?![\w'])", s)):
        return None               # rev 6: the sentence names the row's own project near the permit words
    own = []
    for p in cands:
        sh = _pm_short(p)
        if not sh:
            continue
        ms = [m for m in re.finditer(r"(?<![\w'])" + re.escape(sh) + r"(?![\w'])", s) if abs(m.start() - a) <= 200]
        m = min(ms, key=lambda m: abs(m.start() - a)) if ms else None
        if not m or re.search(_PM_NEAR + r"$", s[:m.start()]) or _pm_joined(s, m, p):
            continue
        if any(q != p and len(q) > len(p) and re.search(r"[\w'\-]+\s+" + re.escape(sh) + r"(?![\w'])", q) for q in cands):
            continue
        own.append(p)
    p = own[0] if own and len({PN.key(x) for x in own}) == 1 else None
    if p and not (cur and _same_project(p, cur)):
        return p
    return None


# 1.0.6 (one permit, one row): a decision document is the decision on the plan or statement it closes (a Record of
# Decision or FONSI on a Plan of Operations, NOI or EIS); an exploration-stage environmental approval is the drill
# permit it authorises (a Peru DIA, FTA or "environmental permit" beside the drill permit); a generic environmental
# permit beside the EIA/ESIA at the same stage is that assessment's approval; a granted EA beside a granted Plan of
# Operations is the plan's NEPA review.
_DECISION = re.compile(r"(?i)record\s+of\s+decision|decision\s+record|finding\s+of\s+no\s+significant|\bFONSI\b|\bROD\b")
_GENV_DRILL = re.compile(r"(?i)^(?:environmental\s+(?:permits?|approvals?|authori[sz]ations?|licen[cs]es?)|DIA\b.*|Declaraci.*|FTA|Ficha.*|"
                         r"Informe.*|EIA[\s-]*sd|semi[\s-]*detailed.*)$")
_GENV = re.compile(r"(?i)^environmental\s+(?:permits?|approvals?|authori[sz]ations?|licen[cs]es?|clearances?|certificates?)$")


def _NOI_LEASE(x, m):
    return bool(re.match(r"(?i)notices?\s+of\s+intent", x["permit_name"] or "") and m["permit_type"] == "mining_licence" and
                re.search(r"(?i)\b(?:mining\s+)?(?:lease|licen[cs]e|concession)", x["sent"]))


def _fold_into(x, m):
    """True when row x is another name or stage document of row m's permit (same project checked by the caller)."""
    xn, mn = x["permit_name"] or "", m["permit_name"] or ""
    if not x["project"] and m["project"] and x["permit_type"] == m["permit_type"] and x["status"] == m["status"] and \
            _names_compatible(xn, mn) and _auth_merge(x["authority"], m["authority"]):
        return True        # the same permit, once with its project and once without
    if _DECISION.search(xn) and not _DECISION.search(mn) and m["permit_type"] in ("plan_of_operations", "environmental_assessment"):
        return True
    if _NOI_LEASE(x, m):
        return True        # 1.0.7: the Notice of Intent that starts a mining-lease application is that application
    # 1.0.8 (guide QE): the assessment a project description or project notice starts is that filing's row
    if x["permit_type"] == m["permit_type"] == "environmental_assessment" and x["status"] in ("planned", "in_review") and \
            re.match(r"(?i)(?:initial\s+)?project\s+(?:description|notice)", mn) and \
            re.search(r"(?i)assessment|\bE?SIA\b|\bEIA\b|\bEIS\b|\bEA\b|statement", xn):
        return True
    # 1.0.8: "The submission of the ESIA is a prerequisite for obtaining an environmental permit": the generic
    # environmental permit the sentence ties to the assessment is that assessment's decision, at whatever stage
    if _GENV.match(xn) and not _GENV.match(mn) and m["permit_type"] == "environmental_assessment" and \
            x["permit_type"] in ("drill_exploration", "environmental_assessment") and \
            x.get("sent") is not None and x.get("sent") in (m.get("sents") or [m.get("sent")]):
        return True
    if x["status"] != m["status"]:
        return False
    if x["permit_type"] == "environmental_assessment" and re.match(r"(?i)environmental\s+assessment", xn) and \
            m["permit_type"] == "plan_of_operations" and x["status"] == "granted":
        return True
    if _GENV_DRILL.match(xn) and not _GENV_DRILL.match(mn) and m["permit_type"] == "drill_exploration" and \
            x["permit_type"] in ("drill_exploration", "environmental_assessment"):
        return True
    # 1.0.8: "FTA environmental permit", "DIA environmental approval": the generic words name the exploration-stage
    # environmental approval itself (guide QD), one row
    if _GENV.match(xn) and not _GENV.match(mn) and m["permit_type"] == "drill_exploration" and \
            x["permit_type"] in ("drill_exploration", "environmental_assessment") and \
            re.search(r"(?i)\b(?:DIA|FTA|ITS|EIA[\s-]*sd)\s+environmental\s+(?:permits?|approvals?|authori[sz]ations?|licen[cs]es?|"
                      r"clearances?|certificates?)\b|(?:Ficha|Declaraci|Informe)[^.;]{0,60}\)?\s*environmental\s+(?:permit|approval)",
                      (x.get("sent") or "") + " " + (m.get("sent") or "")):
        return True
    return bool(_GENV.match(xn) and not _GENV.match(mn) and m["permit_type"] == "environmental_assessment" and
                x["permit_type"] in ("drill_exploration", "environmental_assessment"))


def _fold_rows(rows):
    out = []
    for r in rows:
        tgt = main = None
        for q in out:
            if q["project"] and r["project"] and not _same_project(q["project"], r["project"]):
                continue
            if _fold_into(r, q):
                tgt, main = q, q
            elif _fold_into(q, r):
                tgt, main = q, r
            if tgt is not None:
                break
        if tgt is None:
            out.append(r)
            continue
        noi = r if main is not r else dict(tgt)
        if main is r:
            for k in ("permit_type", "permit_name", "status", "sent", "a", "e", "hl", "hlc", "inh"):
                tgt[k] = r[k]
        if _NOI_LEASE(noi, tgt):
            tgt["status"] = noi["status"]       # 1.0.7: the lease is at the stage its Notice of Intent states
        if not tgt["project"]:
            tgt["project"] = r["project"]
        tgt["sents"] += [x for x in r["sents"] if x not in tgt["sents"]]
        if not tgt["authority"]:
            tgt["authority"] = r["authority"]
    return out


def _facts_nums(s):
    """1.0.6: the quantities a sentence states (not years): "25 concessions", "244 sq km" -- two sentences sharing one
    speak of the same permit."""
    s = re.sub(r"(?<=\d) (?=\d\b)", "", s or "")        # a digit split off by text extraction ("24 4 sq km")
    return {n.replace(",", "") for n in re.findall(r"\b\d[\d,.]*\d\b|\b\d\b", s)} - \
        {n for n in re.findall(r"\b(?:19|20)\d\d\b", s)}


# 1.0.7 (FIX3): an acronym defined by permit words this reader's names do not spell out ("Environmental Impact
# Authorization ("EIA")", "Environment Impact Statement ("EIS")", "(Declaracion Impacto Ambiental) (the "DIA")") is
# still that permit; only a definition with no permit word ("Earn-In Agreement", "Exploration Information Systems")
# makes the acronym something else
_ACRO_PERMITISH = re.compile(r"(?i)\b(?:environment|impact|permi[st]|licen[cs]|authori[sz]|approv|assessment|declara|ambiental)")


def _acro_defs(t):
    """1.0.6: acronyms the release defines for a permit ("Installation License (LI)"): the acronym is that permit."""
    out = {}
    for m in re.finditer(r"\(\s*(?:the\s+)?[\u201c\"'\u2018]?\s*([A-Z][A-Za-z\-]{1,7})\s*[\u201d\"'\u2019]?\s*\)", t[:TEXT_CAP]):
        pre = t[max(0, m.start() - 90):m.start()].rstrip()
        ms = _mentions(pre, 0)
        if ms and ms[-1][1] >= len(pre) - 2 and ms[-1][3].upper() != m.group(1).upper() and len(ms[-1][3]) > len(m.group(1)):
            out.setdefault(m.group(1), ms[-1][3])
        elif m.group(1).isupper() and not (ms and ms[-1][1] >= len(pre) - 2):
            # an acronym the release defines as something that is not a permit ("Earn-In Agreement (the "EIA")"):
            # its bare mentions are that thing (None), never a permit
            ws = re.findall(r"[A-Za-z][\w\u2019']*", pre)[-len(m.group(1)):]
            if len(ws) == len(m.group(1)) and all(w[:1].isupper() for w in ws) and \
                    "".join(w[0] for w in ws).upper() == m.group(1) and not _ACRO_PERMITISH.search(" ".join(ws)):
                out.setdefault(m.group(1), None)
    return out


def _first_date(b):
    """1.0.6: the release's date when it has no dateline: the first full date at the top ("May 27, 2025 <Company>
    Breaks Ground ...")."""
    m = re.search(r"(?i)" + T._DATE_RX, b[:400])
    return T._iso(m) if m else None


def _glue(sents):
    """1.0.6: "... from the U.S. Bureau of Land Management" is one sentence, not two. 1.0.7: a word-processor bullet
    (private-use symbol characters) starts a new sentence, as the standard bullets do."""
    out = []
    for x in [p for y in sents for p in re.split(r"\s[\uf0a7\uf0b7\uf0d8\uf076\uf0fc\uf06e]\s", y) if p.strip()]:
        if out and re.search(r"\bU\.S\.(?:A\.)?$", out[-1]):
            out[-1] = out[-1] + " " + x
        else:
            out.append(x)
    return out


# 1.0.7 (multi-project releases): the place a sentence or passage is about when it names it without "Project" --
# "At Springpole, continued advancing environmental assessment work", "Ada Tepe - Received its final operating
# permits", "The Santas Glorias property is ... The Company's environmental application ... has been accepted"
_PNAME = r"([A-Z][\w'\u2019\-]+(?:\s+(?:[A-Z][\w'\u2019\-]+|de|del|la|el|do|da)){0,3})"
_HEAD_AT = re.compile(r"^(?:[A-Z][\w ]{0,30}:\s*)?\W{0,3}(?:At|On|For|In|Within)\s+(?:the\s+|its\s+|our\s+|their\s+)?(?:(?:flagship|100%[\s-]owned|wholly[\s-]owned)\s+)?" +
                      _PNAME + r"(?:\s+(?:project|property|mine))?\s*(?:\((?:[^)]{0,40})\)\s*)?,")
_HEAD_DASH = re.compile(r"^\W{0,3}" + _PNAME + r"\s+(?:Project\s+|Property\s+|Mine\s+)?[\u2013\u2014:-]\s+[A-Z]")
_LOWER_PLACE = re.compile(r"\b(?:[Tt]he|[Ii]ts|[Oo]ur|[Tt]heir)\s+(?:(?:wholly|100%)[\s-]owned\s+)?" + _PNAME +
                          r"\s+(?:project|property|mine|deposit|claims|concessions?|operations?)\b(?!\s+[A-Z])")
_HEAD_WORDS = re.compile(r"(?i)\b(?:permitting|permits?|update|highlights?|outlook|program(?:me)?s?|results?|summary|next|"
                         r"community|relations|technical|information|corporate|financial|exploration|drilling|environmental|"
                         r"social|sustainability|advanced|qualified|person|statements?|about|overview|background|"
                         r"milestones?|objectives?|catalysts?|plans?|activities|work|studies|study|review|guidance|impact|construction|"
                         r"production|mining|development|access|closure|reclamation|approvals?|expansion|phase|stage|"
                         r"additional|further|underground|federal|provincial)\b")
_HEAD_NOT = re.compile(r"(?i)^(?:the|this|that|these|its|our|their|a|an|each|all|both|present|year|end|least|times?|"
                       r"q[1-4]|h[12]|first|second|third|fourth|last|next|addition|particular|summary|total|"
                       r"january|february|march|april|may|june|july|august|september|october|november|december|"
                       r"\d+|company|corporation|management|highlights?|update|outlook|overview|exploration|drilling|"
                       r"permitting|corporate|financial|operations?|development|sustainability|esg|environmental)\b")


# 1.0.7: the ground a permit is for, named right after it without "Project" ("an application for an exploration
# license at <Name>", "the exploration license for <Name>", "nine mining concessions in <Name>")
_AFTER_AT = re.compile(r"^\s*(?:\([^)]{0,40}\)\s*)?(?:for\s+(?:drilling|exploration|the\s+drill(?:ing)?)\s+(?:activities\s+|programs?\s+|work\s+)?)?"
                       r"(?:at|for|in|on|over|covering)\s+(?:the\s+)?" + _PNAME + r"(?=\s*[,.;)]|\s+(?:near|have|has|had|is|are|was|were|which|and|to|in|from|by|with)\b)")


# 1.0.7 (sub-property rows): a deposit, zone, prospect, target, extension or claim block is reported on its project
_SUBPART = re.compile(r"(?i)\b(?:Deposits?|Zones?|Pits?|Targets?|Prospects?|Showings?|Veins?|Target\s+Complex|Anomal(?:y|ies)|"
                      r"Claims?|Claim\s+(?:Group|Block)s?|Extensions?|Area\s+Claims)$")
_LEAD_OWN = re.compile(r"\b(?:[Ii]ts|[Oo]ur|[Tt]heir|the\s+Company['\u2019]s|the\s+Corporation['\u2019]s)\s+"
                       r"(?:(?:flagship|100\s*%[\s-]*owned|wholly[\s-]+owned|newly[\s-]+acquired|optioned|key|advanced)\s+)*"
                       r"([A-Z][\w'\u2019\-\u2010]+(?:\s+[A-Z][\w'\u2019\-\u2010]+){0,3})((?:\s+[a-z][\w\-\u2013]*){0,3}?)\s+([Pp]roject|[Pp]roperty)\b")
_HL_AT = re.compile(r"\b(?:at|for|on)\s+(?:the\s+|its\s+)?([A-Z][\w'\u2019\-]+(?:\s+[A-Z][\w'\u2019\-]+){0,2})\s*$")


def _parent_project(part, h, b, issuer, wholes):
    """1.0.7: the project a deposit, zone, prospect, target, extension or claim block belongs to: the same name called a
    project in the release; else the one project the lead paragraph calls the company's own; else the place the
    headline ends on ("... Drilling at <Name>"); else the release's only project. None when it cannot tell."""
    core = _SUBPART.sub("", part or "").strip()
    core = re.sub(r"(?i)\s+(?:Gold|Silver|Copper|Nickel|Lithium|Uranium|VMS|PGM|Zinc|Area)$", "", core).strip()
    if core and re.search(r"(?i)\b" + re.escape(core) + r"\s+(?:[\w\-]+\s+){0,2}?(?:project|property)\b", b):
        m = re.search(r"\b" + re.escape(core) + r"(?:\s+[A-Z][\w\-]*){0,2}\s+(?:Project|Property)\b", b)
        return m.group(0) if m else core + " Project"
    lead = [m for m in _LEAD_OWN.finditer(b[:1500]) if _place_ok_name(m.group(1), issuer)]
    names = list(dict.fromkeys(m.group(1).strip() + " " + m.group(3).title() for m in lead))
    names = [n for n in names if not _SUBPART.search(n) and T._pkey(n) != T._pkey(part)]
    if len({T._pkey(_strip_suffix(n)) for n in names}) == 1:
        return names[0]
    ha = _HL_AT.search(h)
    if ha and _place_ok_name(ha.group(1), issuer) and not _SUBPART.search(ha.group(1)):
        return ha.group(1)
    ws = [q for q in wholes if _WHOLE_RX.search(q) and not _SUBPART.search(q)]
    if len(ws) == 1:
        return ws[0]
    return None


def _place_ok_name(n, issuer):
    if not n or len(n) < 3 or n.isupper() or re.fullmatch(r"(?i)(?:projects?|propert(?:y|ies)|mines?|company|site|area)", n) or \
            _HEAD_NOT.match(n) or _HEAD_WORDS.search(n) or _PLACE_RX.fullmatch(n) or \
            re.search(r"(?i)\b(?:First\s+Nations?|Nation|Band|Cree|M[\u00e9e]tis|communit\w*|County|ejido)\b", n):
        return False
    if issuer and n.split()[0] in issuer.split()[:1]:
        return False
    return not re.search(r"(?i)\b(?:Ministry|Department|Agency|Office|Bureau|Government|Commission|Inc|Corp|Ltd|"
                         r"Limited|Resources|Mining|Minerals|Metals|Exchange|Nation|Council|Board|Court)\b", n)


def _head_place(s, issuer):
    """1.0.7: the place a sentence opens with ("At <Name>, ...", "<Name> - Received ...")."""
    for rx in (_HEAD_AT, _HEAD_DASH):
        m = rx.match(s)
        if m and _place_ok_name(m.group(1).strip(), issuer):
            return m.group(1).strip()
    return None


def _lookback_place(b, s, issuer, back=500):
    """1.0.7: the last place the passage just before a sentence names as the subject of its text (a lower-case "the
    <Name> property", or a sentence opening with the place); None when the passage names none. A capitalised project
    name there is not used: passages name neighbours and comparisons that way."""
    p = b.find(s[:60])
    if p <= 0:
        return None
    w = b[max(0, p - back):p]
    best = None
    for m in _LOWER_PLACE.finditer(w):
        n = m.group(1).strip()
        if _place_ok_name(n, issuer) and (best is None or m.start(1) > best[0]):
            best = (m.start(1), n)
    for m in re.finditer(r"(?:(?<=[.;\u2022\u25aa\u25cf:])|^)\s*(?=\S)", w):
        n = _head_place(w[m.end():m.end() + 120], issuer)
        if n and (best is None or m.end() > best[0]):
            best = (m.end(), n)
    return best[1] if best else None


def _fullest(n, names):
    """The fullest name the release gives a place named in short form."""
    cands = [q for q in names if q and _same_project(n, q) and not _SUBPART.search(q)]
    return max(cands, key=len) if cands else n


def _own_news_bg(s, a, e, st, typ, name, off_topic, disposal, people, recap_span, b, dl_ym=None):
    """1.0.7 (OWN_NEWS): True when the permit at s[a:e] is background, not the release's own permit news."""
    pre, post = s[max(0, a - 160):a], s[e:e + 80]
    clause = s[max(0, a - 170):e + 170]
    # in any release: a Notice of Intention to exercise an option; claims staked or applied for; a stage of long ago
    if re.match(r"(?i)notice\s+of\s+intent", name) and _NOI_DEAL.match(post):
        return True
    if typ in ("mining_licence", "drill_exploration") and _STAKING.search(clause) and \
            not re.search(r"(?i)\b(?:drill|exploration|environmental|mining\s+(?:licen|lease|permit))\w*\s+permits?\b", s[a:e]):
        return True
    p = b.find(s[:60])
    # a grant the sentence sends the reader to an earlier news release for; an assessment the work is excluded from
    if st in ("granted", "renewed") and re.search(r"(?i)\(\s*(?:see|refer\s+to)\b[^)]{0,90}\b(?:news|press)\s+releases?\b", s):
        return True
    if re.search(r"(?i)\b(?:exclu\w+|exempt\w*)\s+from\s+(?:[\w\-]+\s+){0,8}$", s[max(0, a - 100):a]):
        return True
    if _HISTORIC.search(s[max(0, a - 40):a]) or _OLD_YEAR.search(clause) or \
            (p >= 0 and _OLD_YEAR.search(b[max(0, p - 250):p])):
        return True
    # 1.0.8: a grant said to be in the past ("Exploration permits were issued in the past for drilling atop <X>"), and
    # ground the company holds described by what a permit covers ("now holds one 100%-owned exploration license
    # covering the <X> prospect")
    if st in ("granted", "renewed") and _PAST_GRANT.search(s[max(0, a - 120):e + 120]):
        return True
    if st in ("granted", "renewed", "in_review") and _HOLDS_COVERING.search(s[max(0, a - 70):a]) and \
            re.match(r"(?i)s?\s*(?:\([^)]{0,30}\)\s*)?,?\s*(?:covering|over|that\s+covers?|which\s+covers?)\b", post):
        return True
    if not off_topic:
        return False
    held = st in ("granted", "renewed", "in_review")
    finite = _FINITE_GRANT.search(clause)
    # the ground the company holds, described ("consists of", "holds a 60% interest in", "under an active permit")
    if held and _TENURE_PRE.search(pre) and not finite:
        return True
    # ... and an item of a numbered list of the company's holdings ("the portfolio currently consists of: 1) ...
    # 4) Exploration Licences - the Company has applied for several exploration licences ...")
    if p >= 0 and _HOLDINGS_LIST.search(b[max(0, p + a - 900):p + a]) and \
            re.search(r"(?:^|\s)(?:\d{1,2}|[ivx]{1,4})\)\s[^)]{0,300}$", b[max(0, p + a - 300):p + a]):
        return True
    if held and (_HELD_HAND.match(post) or _HELD_POSS.search(s[max(0, a - 60):a])):
        return True
    if st == "granted" and _PARTICIPLE_POST.match(post) and \
            not re.search(r"(?i)\b(?:has|have|had|was|were)\s+(?:now\s+|recently\s+)?(?:been\s+)?(?:received|granted|issued|approved|awarded|obtained|secured)\b|"
                          r"\b(?:received|obtained|secured)\b", clause):
        return True
    # earlier news quoted, a recap of past milestones
    if st in ("granted", "renewed") and _EARLIER_NEWS.search(s[max(0, a - 170):e + 90]):
        return True
    if st in ("granted", "renewed") and recap_span[0] <= p < recap_span[1]:
        return True
    # the company boilerplate paragraph
    if p >= 0 and _BOILER.search(b[max(0, p - 500):p + len(s)]):
        return True
    # an assessment among technical work streams; all permits at once; a hypothetical
    if typ == "environmental_assessment" and len(_WORKLIST.findall(clause)) >= 2:
        return True
    if _ALL_PERMITS.search(s[max(0, a - 40):a]) and re.match(r"(?i)permits|approvals|licen[cs]es", name.split()[0] if name else ""):
        return True
    if _MAYBE.match(post):
        return True
    # a permit described in the present tense ("A drill permit is approved for this area"), a hypothetical "If a drill
    # permit is received for <X>, ..."
    if held and re.match(r"(?i)^\s+(?:is|are)\s+(?:currently\s+|already\s+)?(?:approved|permitted|valid|active|held)\b", post):
        return True
    if re.search(r"(?i)\b(?:if|should|unless)\s+(?:an?|the|its|any)\s+(?:[\w\-]+\s+){0,3}$", s[max(0, a - 40):a]) and \
            re.match(r"(?i)^[^.;,]{0,40}?\b(?:is|are|were|be)\s+(?:received|granted|approved|issued|obtained)", post):
        return True
    # conditions attached to something else ("fulfilling all applicable requirements associated with the project
    # environmental assessments"); the transfer of licences between companies; the approved permit a program runs
    # under ("with the approved Plan of Operations providing for"); licences counted as holdings ("the company's three
    # exploration licenses in this area"); "maintains all required operating permits"
    if re.search(r"(?i)\brequirements?\s+(?:associated\s+with|of|under|in)\s+(?:the\s+)?(?:[\w\-]+\s+){0,3}$", pre):
        return True
    if st == "renewed" and re.search(r"(?i)\btransfer\s+of\s+(?:the\s+)?(?:[\w\-]+\s+){0,4}$", pre) and \
            re.match(r"[^.;]{0,40}?\bto\s+[A-Z]", post):
        return True
    if held and re.search(r"(?i)\b(?:the|its|their)\s+(?:recently\s+|previously\s+|newly\s+)?(?:approved|granted|permitted|issued)\s+(?:[\w\-]+\s+){0,2}$",
                          s[max(0, a - 50):a]) and not _BOND_POSTED.search(s[max(0, a - 200):a]):
        return True
    if held and re.search(r"(?i)['\u2019]s?\s+(?:\d+|two|three|four|five|six|seven|eight|nine|ten)\s+(?:[\w\-]+\s+){0,2}$", s[max(0, a - 40):a]) and \
            not finite:
        return True
    if held and re.search(r"(?i)\b(?:maintains?|holds?|retains?)\s+(?:all\s+)?(?:the\s+)?(?:required\s+|necessary\s+|its\s+)?(?:[\w\-]+\s+){0,2}$",
                          s[max(0, a - 50):a]):
        return True
    # a grant dated well before the release (whatever stage the sentence starts with: "the first of three drilling
    # permits submitted by the Company, which was granted ... in May 2023")
    if dl_ym and re.search(r"(?i)\b(?:granted|approved|issued|received|obtained|awarded)\b", clause):
        yms = [_ym(mo, y) for mo, y in _MONTH_YEAR.findall(clause)]
        if yms and max(yms) < dl_ym - 2:
            return True
    # a release giving the property away: the licences that go with it are the property
    if disposal:
        return True
    # a new officer's or director's past work
    if people and _BIO.search(s):
        return True
    return False


def analyse(headline, body):
    h, b = T._prepare(headline, body, False)
    # PERMIT_V1 audit fix (2026-09-22): the forward-looking-statements section lists permits in the abstract
    # ("future water rights acquisitions"); it is not read once it starts in the back part of the release
    fls = _FLS.search(b, int(len(b[:TEXT_CAP]) * 0.5))
    if fls and fls.start() < TEXT_CAP:
        b = b[:fls.start()]
    if not re.search(r"(?i)permit|licen[cs]e|approv|authori[sz]|concession|lease|assessment|EIA|ESIA|agreement|"
                     r"Notice\s+of|Plan\s+of\s+Operation|consent|designation|permitting|priority\s+project|strategic\s+project",
                     h + " " + b[:TEXT_CAP]):
        return {"rows": [], "reason": "no_permit_words"}
    if _DEAL_HL.search(h) and not _mentions(h, 0):
        return {"rows": [], "reason": "deal_approval"}
    if _ANNIV.search(h):
        return {"rows": [], "reason": "anniversary"}
    # 1.0.7: not a mining company's release (a cannabis zoning permit, a software licence)
    if not _MINING_RX.search(h + " " + b[:TEXT_CAP]):
        return {"rows": [], "reason": "not_mining"}
    if len(_LISTING.findall(b[:TEXT_CAP])) >= 3:
        return {"rows": [], "reason": "listing_page"}
    # 1.0.7 (OWN_NEWS): the headline says the release is about something else
    off_topic = not _HL_TOPIC.search(h)
    disposal = off_topic and bool(_DISPOSAL_HL.search(h))
    people = off_topic and bool(_PEOPLE_HL.search(h))
    rc = _RECAP.search(b)
    recap_span = (rc.end(), rc.end() + 2500) if rc and off_topic else (-1, -1)
    issuer = T._issuer(b)
    full = h + " . " + b
    hl_projs = _projects(h, issuer)
    hl_proj = hl_projs[0][1] if hl_projs else None
    q = re.search(r"['\u2018\u201c\"]([A-Za-z][A-Za-z\s\-]{2,40}?)['\u2019\u201d\"]\s+(?:[A-Za-z\-]+\s+){0,3}?(PROJECT|PROPERTY|MINE|DEPOSIT)\b", h, re.I)
    if q and (not hl_proj or _same_project(hl_proj, q.group(1))):
        hl_proj = q.group(1).strip().title() + " " + q.group(2).title()
    projs_all = _projects(b[:6000], issuer)
    # PERMIT_V2: the helper's main project, unless this reader's own filters set it aside (another company's
    # "Cariboo Gold Project" next door, a project being acquired)
    main_proj = PN.primary(h, b, issuer)
    if main_proj and (projs_all or hl_projs) and \
            not any(_same_project(main_proj, p) for pos, p in list(projs_all) + list(hl_projs)):
        main_proj = None
    if not main_proj:
        main_proj = _main_project(projs_all)
        if main_proj and not any(_same_project(main_proj, p) for pos, p in projs_all if pos < 900):
            main_proj = None
    if hl_proj and not main_proj:
        main_proj = hl_proj
    # 1.0.6: the helper's main project built from headline words ("... Milestones That Will See <Plant> Commissioned
    # and <Name> Mine in Production") is the shorter name this reader finds for it
    if main_proj and any(w in _HL_JUNK or w in _VERBS_HL for w in main_proj.split()):
        own = [p for _, p in list(hl_projs) + list(projs_all) if _same_project(p, main_proj) and len(p) < len(main_proj)]
        if own:
            main_proj = own[0]
    # 1.0.6: a target, zone or deposit is not the release's main project when the headline names the property it
    # sits in ("Breaks Ground at <X> Target ... at <Y> Hills" with "the <Y> Hills Property" in the lead)
    if main_proj and _PART_RX.search(main_proj):
        hk = set(T._pkey(h).split())
        whole = [p for pos, p in projs_all if pos < 1500 and _WHOLE_RX.search(p) and _pwords(_strip_suffix(p)) and
                 _pwords(_strip_suffix(p)) <= hk and not _same_project(p, main_proj)]
        if whole:
            main_proj = whole[0]
    _rp_cache = []

    def rp_names():
        """1.0.5: the projects the helper says the release is about, when it is about several; only those this
        reader's own finder also names in the headline or opening text (its filters: no neighbour, no project
        being bought, no other company's)."""
        if not _rp_cache:
            try:
                rp = PN.release_projects(h, b, issuer)
            except Exception:
                rp = {}
            seen = list(projs_all) + list(hl_projs)
            _rp_cache.append([p for p in rp.get("projects", []) if any(_same_project(p, q) for _, q in seen)
                              and not _pm_part_of(p, h + " " + b)]
                             if rp.get("scope") == "several" else [])
        return _rp_cache[0]

    metal = T._metal(h + " " + b[:2500])
    acro = _acro_defs(h + " . " + b)
    # 1.0.6: a release that ties its DIA to drilling means the drill permit by every mention of it
    dia_drill = bool(re.search(r"(?i)(?:\bDIA\b|Declaraci[o\u00f3]n\s+de\s+Impacto)[^.]{0,200}\b(?:drill|platform)|"
                               r"\b(?:drill|platform)\w*[^.]{0,200}(?:\bDIA\b|Declaraci[o\u00f3]n\s+de\s+Impacto)", h + " . " + b[:TEXT_CAP]))
    juris = None
    dl = T._dateline(b) or _first_date(b) or ""
    dl_ym = int(dl[:4]) * 12 + int(dl[5:7]) if dl else None

    sents = [(h, True)] + [(x, False) for x in _short(_glue(T._sentences(b)))]
    juris = _jurisdiction(h, [x for x, _ in sents[1:]])
    found = []
    generic = []
    recent = []        # 1.0.6: (sentence index, permit name, project) of permits named with their project
    deal_hl = bool(_DEAL_TENURE_HL.search(h))
    # 1.0.7: the release's project names, and whether it is about several projects
    known_names = [p for _, p in list(hl_projs) + list(projs_all)]
    wholes = []
    for p in known_names:
        if not _PART_RX.search(p) and not _PM_GENERIC.search(p) and not any(_same_project(p, q) for q in wholes):
            wholes.append(p)
    multi_rel = len(wholes) >= 2
    parent_cache = {}
    for si, (s, is_hl) in enumerate(sents):
        ms = _mentions(s, 0, is_hl or b.find(s[:80]) < _LEAD_CHARS)
        if is_hl and not ms and not _DEAL_HL.search(s) and not _CLAIMS.search(s):
            g = _HL_GENERIC.search(s)
            if g and re.match(r"(?i)approv|authori|BLM|USFS|final|regulatory|government|minist", g.group(0)) and \
                    _HL_NOT_PERMIT.search(s):
                g = None
            if g and re.match(r"(?i)permitting", g.group(0)) and not _HL_PERMITTING.search(s):
                g = None                   # "Towards the Permitting of ..." is not a stage
            if g and re.match(r"(?i)permits?\b(?!\s+application)", g.group(0)) and not _HL_PERMIT_VERB.search(s):
                g = None                   # "Drilling at its Diguifara Gold Permit" names a tenure
            if g and _HL_STAGE.search(s) and not _HL_OTHERS.search(s) and \
                    (_DRILLISH.search(s + " " + b[:1500]) or _HL_BUILD.search(s)):
                generic.append((s, g.start(), g.end(), g.group(0)))
        if not ms:
            continue
        if len(found) > 200:
            break
        if not is_hl and _NOT_PERMIT_CTX.search(s) and re.search(r"(?i)\b(?:approv|accept)", s) and \
                all(t == "other" for _, _, t, _ in ms):
            continue
        spans = [(a, e) for a, e, _, _ in ms]
        projs_s = _projects(s, issuer, spans)
        for a, e, typ, name in ms:
            if _CAVEAT.search(s[max(0, a - 160):e + 160]):
                continue           # FIX5: the resource-estimate caveat ("may be materially affected by environmental,
                #                    permitting, legal, title, taxation ...") names no permit
            if name.isupper() and name in acro and acro[name] is None:
                continue           # 1.0.6: an acronym the release defined as something else (EIA = Earn-In Agreement)
            nkey = re.sub(r"s$", "", (acro.get(name, name) if name.isupper() else name).lower())
            if any(abs(p_pos - a) < 220 for p_pos, _ in projs_s):
                recent.append((si, nkey, _project_near(a, projs_s, hl_proj, main_proj)))
            if re.match(r"(?i)environmental\s+(?:and\s+social\s+)?stud(?:y|ies)$", name) and \
                    not re.match(r"(?i)\s*(?:\([^)]{0,12}\)\s*)?(?:applications?|approvals?|submissions?|permits?|reports?)\b", s[e:e + 40]):
                continue           # 1.0.6: baseline "environmental studies" are work, not a permit
            if name in ("LP", "LO") and name not in acro:
                continue           # 1.0.8: the Brazilian licence acronyms only where the release defines them
            # 1.0.8: one permit named twice in a row -- an assessment that is the drill permit's own form ("an
            # Environmental Impact Assessment - Semi-detailed ("EIA-Sd") drill permit application"), and the permit a
            # named approval is for ("Environmental Clearance Certificates for Exclusive Prospecting License 7071",
            # "the LP for the Full Mining License"): the first names the news, the second what it is for
            if typ == "environmental_assessment" and _EA_IS_DRILL.match(s[e:e + 80]):
                continue
            if any(e2 <= a and a - e2 <= 60 and _FOR_PERMIT.fullmatch(s[e2:a]) for a2, e2, _, _ in ms):
                continue
            if is_hl and _HELD_AROUND.search(s[e:e + 60]):
                continue           # 1.0.8: "drill permits in place to allow ..." in a headline is held, not news
            if typ == "environmental_assessment" and dia_drill and re.match(r"(?i)DIA\b|Declaraci", name):
                typ = "drill_exploration"
            # 1.0.7 (QD): an assessment filed to obtain drill permits is the drill permit
            if typ == "environmental_assessment" and _EA_FOR_DRILL.match(s[e:e + 160]):
                typ = "drill_exploration"
            st, win = _stage_near(s, a, e, typ, spans)
            if not st:
                continue
            st = _status_fix(st, s, a, e, typ, dl_ym)
            clause = s[max(0, a - 170):e + 170]
            if not is_hl:
                bg = _BACKGROUND.search(clause)
                if bg and (st in ("granted", "renewed") or re.match(r"(?i)on|under|within|across|adjacent|next", bg.group(0))):
                    continue
                # 1.0.6: held permits, a permit named as a place, a ticker, an acronym defined as something else
                pre_, post_ = s[max(0, a - 90):a], s[e:e + 60]
                if st in ("granted", "renewed", "in_review", "planned") and \
                        (_HELD_PRE.search(pre_) or _HELD_POST.match(post_) or _HELD_AROUND.search(post_) or
                         (_HELD_IS.search(pre_) and re.match(r"(?i)\s+granted\b", post_))) and \
                        not (st == "granted" and _BOND_POSTED.search(s[max(0, a - 200):a])):
                    continue
                if _PLACE_PRE.search(pre_) or _PLACE_POST.match(post_):
                    continue
                ft = st == "granted" and \
                    [m for m in re.finditer(r"(?i)\b(?:further\s+to|regarding\s+the\s+receipt|previously\s+(?:announced|reported))\b",
                                            s[max(0, a - 200):a])]
                # 1.0.7 (FIX3): "Further to its news release dated <date>, it has now received the drill permit" refers
                # to the earlier release, not to the permit: a fresh stage said after the cue is the release's news
                if ft and not _NOW_NEWS.search(s[max(0, a - 200) + ft[-1].end():a]):
                    continue
                if st in ("granted", "renewed") and dl_ym:
                    yms = [_ym(mo, y) for mo, y in _MONTH_YEAR.findall(s[max(0, a - 250):e + 120])]   # 1.0.6: 250
                    yms += [int("20" + y) * 12 + 12 for y in re.findall(r"(?i)Resolution\s+N[o\u00ba\u00b0]?\.?\s*\d+/(\d\d)\b",
                                                                        s[max(0, a - 40):e + 160])]
                    # 1.0.6: more than two months before the release, or (a year alone) an earlier year
                    if yms and (max(yms) < dl_ym - 2 or
                                (max(yms) % 12 == 0 and max(yms) // 12 - 1 < (dl_ym - 1) // 12 and
                                 not re.search(r"(?i)\b(?:dec(?:ember)?|q4|h2)\b", s[max(0, a - 250):e + 120]))):
                        continue
                if _ANNIV.search(clause):
                    continue
                if _own_news_bg(s, a, e, st, typ, name, off_topic, disposal, people, recap_span, b, dl_ym):
                    continue
                if _ACQ.search(s[max(0, a - 100):a]) and st == "granted":
                    continue
                # 1.0.6 (QR): an application made earlier and restated is still pending -- in review
                if st == "applied" and (re.search(r"(?i)\b(?:already|previously|earlier)\s+(?:been\s+)?(?:submitted|filed|lodged|applied)", clause) or
                                        (dl_ym and [1 for mo, y in _MONTH_YEAR.findall(s[max(0, a - 120):e + 120])
                                                    if _ym(mo, y) < dl_ym and not re.match(r"(?i)q|h\d", mo or "")] and
                                         _APPLIED_ACT.search(clause) and not _PAST_DONE.search(clause))):
                    st = "in_review"
            if _TICKER_PRE.search(s[max(0, a - 12):a]):
                continue
            # 1.0.6: in a release about buying, selling or optioning ground, the concessions, licences, leases and water
            # rights that come with it are the property, not permit news -- unless a grant or an application is stated
            if deal_hl and not is_hl and st in ("granted", "renewed", "in_review") and \
                    (typ in ("mining_licence", "water") or
                     (typ == "drill_exploration" and re.search(r"(?i)licen|concession|lease|title|right", name))) and \
                    not _GRANT_ACT.search(clause) and not re.search(r"(?i)applic|submit|appl(?:y|ied|ies)\b", clause):
                continue
            if typ == "land_community" and st == "planned" and not re.search(r"(?i)agreement", name):
                continue
            if not is_hl and _DESCRIBES.match(s[e:e + 60]) and not _STAGE_VERB.search(s[max(0, a - 120):a]):
                continue           # 1.0.7 (FIX3): "The DIA provides the details for the drilling program that <Co>
                #                    intends to carry out": the permit described, the stage word belongs to the program
            # 1.0.8: a project named after the permit in a clause about earlier news ("..., following the Company's
            # previously announced receipt of regulatory approval for its <X> Project") is the earlier permit's
            pjs = [(pp, q) for pp, q in projs_s if not (pp > e and _EARLIER_CLAUSE.search(s[e:pp]))]
            proj = _project_near(a, pjs, hl_proj, main_proj)
            # PERMIT_V2: a project this sentence does not name is inherited (the release's main project)
            inh = not any(abs(p_pos - a) < 220 for p_pos, _ in pjs) and not (is_hl and hl_proj)
            if inh and not is_hl and len(projs_all) + len(hl_projs) > 1:
                p2 = _pm_project_at(b, s, a, proj, rp_names(), [q for _, q in projs_all], issuer)
                if p2:
                    proj, inh = p2, False     # 1.0.5: its passage's project, not the release's main one
            if not is_hl:
                ng = _named_ground(s, a, e, issuer, b)
                if ng and (inh or (ng[0] <= 80 and not any(abs(p_pos - a) < ng[0] + 10 for p_pos, _ in pjs))) and \
                        not (proj and _same_project(proj, ng[2])):
                    proj, inh = ng[2], False
            if inh and not is_hl:
                # 1.0.6: "the EIA was submitted" is the EIA a sentence or two before named with its project
                for si2, k2, p2 in reversed(recent):
                    if si - si2 > 2:
                        break
                    if k2 == nkey and si2 < si and p2:
                        proj, inh = p2, False
                        break
            if not is_hl:
                # 1.0.7: the ground named right after the permit ("an exploration license at <Name>"), in a release
                # about something else or when the headline names it too
                am = _AFTER_AT.match(s[e:e + 80])
                if am and (off_topic or am.group(1).strip().lower() in h.lower()) and _place_ok_name(am.group(1).strip(), issuer) and \
                        not (proj and _same_project(proj, am.group(1).strip())):
                    proj, inh = _fullest(am.group(1).strip(), known_names), False
            if inh and not is_hl:
                # 1.0.7: the place the sentence opens with ("At <Name>, ...", "<Name> - Received ...")
                hp = _head_place(s, issuer)
                if not hp:
                    lps = [(abs(m.start(1) - a), m.group(1).strip()) for m in _LOWER_PLACE.finditer(s)
                           if _place_ok_name(m.group(1).strip(), issuer) and abs(m.start(1) - a) < 220]
                    hp = min(lps)[1] if lps else None
                if hp:
                    proj, inh = _fullest(hp, known_names), False
            if inh and not is_hl and multi_rel and off_topic:
                # 1.0.7: in a release about something else that names several projects, the place the passage just
                # named
                lp = _lookback_place(b, s, issuer)
                if lp:
                    proj, inh = _fullest(lp, known_names), False
            # 1.0.7: a deposit, zone, prospect, target or claim block is reported on its project
            if proj and _SUBPART.search(proj):
                if proj not in parent_cache:
                    parent_cache[proj] = _parent_project(proj, h, b, issuer, wholes)
                proj = parent_cache[proj] or proj
            auth = _auth_near(s, a, e, typ)
            ctyp = _ctype(typ, name, s, auth, h)
            hlc = is_hl or s[:60].lower() == h[:60].lower()     # the headline, or its copy at the top of the body
            found.append({"permit_type": ctyp, "project": proj, "status": st, "authority": auth,
                          "permit_name": _clean_name(acro.get(name, name) if name.isupper() else name),
                          "hl": is_hl, "sent": s, "a": a, "e": e, "inh": inh,
                          "hlc": hlc, "amend": bool(_NEXT_AMEND.search(s[max(0, a - 90):a]))})

    if not found:
        for s, a, e, name in generic[:1]:
            st, _w = _stage_near(s, a, e)
            if st == "planned" and re.search(r"(?i)\b(?:initiates|commences|begins|starts)\b[^.]{0,80}\bfollowing\s+(?:the\s+)?receipt", s):
                st = "granted"          # "Initiates Drilling ... Following Receipt of Regulatory Approval"
            gtyp = "construction_operating" if _HL_BUILD.search(s) and not _DRILLISH.search(s) else "drill_exploration"
            gauth = _auth_near(s, a, e, gtyp)
            found.append({"permit_type": _ctype(gtyp, name, s, gauth, h), "project": hl_proj or main_proj,
                          "status": st or "granted", "authority": gauth, "permit_name": _clean_name(name),
                          "hl": True, "sent": s, "a": a, "e": e, "inh": not hl_proj, "hlc": True})
            generic = generic[:1]

    # one row per permit: merge mentions of the same permit (type, project, authority and name agreeing)
    rows = []
    for f in found:
        home = None
        for r in rows:
            same_type = r["permit_type"] == f["permit_type"] or \
                {r["permit_type"], f["permit_type"]} == {"plan_of_operations", "drill_exploration"} and \
                (not r["authority"] or not f["authority"])
            hl_row = r if r["hl"] and not f["hl"] else f if f["hl"] and not r["hl"] else None
            loose = hl_row is not None and r["status"] == f["status"] and hl_row["project"] and \
                (hl_row.get("inh") or not any(_same_project(hl_row["project"], p) for _, p in projs_all))
            # PERMIT_V2: a headline mention that only inherited the release's project joins the row that names its own
            loose = loose or (r["status"] == f["status"] and
                              (r.get("inh") and r.get("hlc") and not f.get("inh") or
                               f.get("inh") and f.get("hlc") and not r.get("inh")))
            # 1.0.6: the same permit restated later without its project ("With 244 sq km of mining concessions now
            # granted ...") is the row that names its project, not a copy on the release's main project
            loose = loose or (r["status"] == f["status"] and not r["hl"] and not f["hl"] and
                              bool(r.get("inh")) != bool(f.get("inh")) and
                              (r["permit_name"] or "").lower() == (f["permit_name"] or "").lower() and
                              bool(_facts_nums(r["sent"]) & _facts_nums(f["sent"])))
            if not same_type or not (_same_project(r["project"], f["project"]) or loose):
                continue
            if bool(r.get("amend")) != bool(f.get("amend")):
                continue           # 1.0.8: the next amendment of a permit is not the permit's earlier grant
            if r["status"] != f["status"] and any(
                    x["status"] == "planned" and _GENERIC_PERMITS.match(x["permit_name"] or "") and
                    not _GENERIC_PERMITS.match(y["permit_name"] or "") and
                    STAGE_RANK[y["status"]] >= 3 and _STILL_NEEDED.search(x["sent"][max(0, x["a"] - 60):x["e"] + 80])
                    for x, y in ((r, f), (f, r))):
                continue           # 1.0.8: "Environmental permits will be required in advance of construction" are
                #                    other permits still needed, not the assessment under review
            if not _auth_merge(r["authority"], f["authority"]):
                continue
            if not _names_compatible(r["permit_name"], f["permit_name"]):
                continue
            home = r
            break
        if home is None:
            nf = dict(f)
            nf["sents"] = [f["sent"]]
            rows.append(nf)
            continue
        if f["sent"] not in home["sents"]:
            home["sents"].append(f["sent"])
        if "plan_of_operations" in (home["permit_type"], f["permit_type"]):
            home["permit_type"] = "plan_of_operations"
        if not home["authority"] and f["authority"]:
            home["authority"] = f["authority"]
        if f["project"] and (not home["project"] or len(f["project"]) > len(home["project"]) and f["hl"]):
            home["project"] = f["project"]
        elif home.get("inh") and (home.get("hlc") or not home["hl"]) and not f.get("inh") and f["project"]:
            home["project"] = f["project"]   # PERMIT_V2: the project a sentence names beats an inherited one
            home["inh"] = False
        elif home["hl"] and not f["hl"] and f["project"] and \
                not any(_same_project(home["project"], p) for _, p in projs_all):
            home["project"] = f["project"]   # the headline's loose name, the body's project
        hs, fs_ = home["status"], f["status"]
        take = False
        if hs == fs_:
            take = False
        elif {hs, fs_} == {"planned", "in_review"} and home["permit_type"] != "environmental_assessment" and \
                _APP_TO_FILE.search((home if hs == "planned" else f)["sent"]) and \
                _AWAITED.search((f if hs == "planned" else home)["sent"]) and \
                not _REVIEW_STRONG.search((f if hs == "planned" else home)["sent"]):
            take = fs_ == "planned"   # 1.0.8: the application is still to be filed, so a grant "anticipated" after
            #                           it is not under review yet
        elif hs == "in_review" and fs_ == "applied" and home["permit_type"] != "environmental_assessment" and \
                _NOW_FILED.search(f["sent"]) and _AWAIT_WORDS.search(home["sent"]) and \
                not _REVIEW_STRONG.search(home["sent"]) and not _REVIEW_STRONG.search(f["sent"]):
            take = True        # 1.0.8: "has now filed an application for the expanded mining permit" beats "we look
            #                    forward to the receipt of" it
        elif fs_ == "planned":
            # 1.0.6: a filing named only as a noun ("Filing of EIA Notification triggers ...") while another
            # sentence says it is still to be filed
            take = hs == "applied" and not _FINITE_APPLIED.search(home["sent"])
            if take and any(_FINITE_APPLIED.search(x) and not re.search(r"(?i)\b(?:will|to\s+be|expects?|plans?|intends?)\b", x)
                                            for x in home["sents"]):
                take = False   # FIX5: another sentence says the company filed it ("The Company submitted the EIS
                #                Addendum in two parts")
        elif hs == "planned" and fs_ == "applied" and not _FINITE_APPLIED.search(f["sent"]):
            take = False
        elif fs_ in ("renewed", "contested") and hs in ("granted", "applied", "in_review", "planned"):
            take = True
        elif hs == "applied" and fs_ == "in_review" and _REVIEW_STRONG.search(f["sent"]):
            take = True        # 1.0.6: "Application Submitted" in the headline, "being reviewed" in the body
        elif not home["hl"] and (f["hl"] or STAGE_RANK[fs_] > STAGE_RANK[hs]):
            take = True
        elif hs == "planned":
            take = True
        if take:
            for k in ("status", "sent", "a", "e"):
                home[k] = f[k]
            if f["hl"] or not home["hl"]:
                home["permit_name"] = f["permit_name"]
            home["hl"] = home["hl"] or f["hl"]

    if any(not _GEN_RX.fullmatch(r["permit_name"] or "") for r in rows):
        rows = [r for r in rows if not _GEN_RX.fullmatch(r["permit_name"] or "")]   # FIX5: a named permit is that news
    else:
        for r in rows:
            if r["permit_type"] == "other" and not re.search(r"(?i)remediat|clean[\s-]?up|\broad\b|water", r["sent"]) and \
                    _DRILLISH.search(h + " " + b[:1500]):
                r["permit_type"] = "drill_exploration"   # FIX5: a permit for "further activities" in a release about drilling
    rows = _fold_rows(rows)
    # the fullest name the release gives each project ("QGQ Project" is the Quesnelle Gold Quartz Mine Project)
    names = [p for _, p in hl_projs] + [p for _, p in projs_all]
    for r in rows:
        for q in names:
            if r["project"] and q != r["project"] and _same_project(r["project"], q) and \
                    (len(_pwords(q)) > len(_pwords(r["project"])) or
                     # 1.0.8: the spelled-out form of an abbreviated name ("Pickett Mt." is the Pickett Mountain Project)
                     len(_pwords(q)) == len(_pwords(r["project"])) and re.search(r"\bMtn?\b", r["project"]) and
                     not re.search(r"\bMtn?\b", q)):
                r["project"] = q
    rows2 = []
    for r in rows:
        names = []
        for t_ in [r["sent"]] + [x for x in r["sents"] if x is not r["sent"]]:
            k = t_.lower().find((r["permit_name"] or "\0").lower()) if t_ is not r["sent"] else r["a"]
            if k < 0:
                continue
            names = _split_names(t_, k, k + (r["e"] - r["a"] if t_ is r["sent"] else len(r["permit_name"])))
            if names:
                break
        parties = _split_parties(r["sent"], r["a"], r["e"]) if r["permit_type"] == "land_community" and not r["authority"] else []
        if len(parties) >= 2:
            for pt in parties:
                rr = dict(r)
                if pt.isupper():
                    dm = re.search(r"((?:[A-Z][\w'\u2019\-]+\s+){1,5})\(\s*[\"\u201c]?" + re.escape(pt) + r"[\"\u201d]?\s*\)", b)
                    pt = dm.group(1).strip() + " (" + pt + ")" if dm else pt
                rr["authority"] = pt
                rows2.append(rr)
        elif len(names) >= 2 and (not r["project"] or any(_same_project(r["project"], n) for n in names)):
            for nm in names:
                rr = dict(r)
                rr["project"] = nm
                rows2.append(rr)
        else:
            rows2.append(r)
    rows = rows2
    # FIX5: a short name the release defines for its project ("<Full Name> Underground Mine (\u201c<ABC> Underground
    # Mine\u201d)") is shown as the full name
    aliases = {m_.group(2).strip().lower(): m_.group(1).strip() for m_ in re.finditer(
        r"\b((?:[A-Z][\w'\u2019\-]+\s+){1,4}(?:Underground\s+|Open[\s-]Pit\s+)?(?:Mine|Project|Property))\s*\(\s*[\"\u201c]\s*"
        r"((?:[A-Z][\w\-]*\s+){0,3}(?:Underground\s+|Open[\s-]Pit\s+)?(?:Mine|Project|Property))\s*[\"\u201d]", b[:6000])}
    for r in rows:
        p_ = r["project"]
        if p_ and p_.lower() in aliases and not _same_project(p_, aliases[p_.lower()]):
            r["project"] = aliases[p_.lower()]
    # FIX5: a project name that is no name -- only generic words left after the reader dropped an acronym ("<ABC>
    # Lithium Property" read as "Lithium Property": the acronym is put back), an address (a postal code, "Suite"), a
    # province or state ("Drilling Permit for New <Province> Project"), headline words ("Third Quarter Financial And
    # <Name> Project")
    for r in rows:
        p_ = r["project"]
        if not p_:
            continue
        q_ = re.sub(r"^.*\b(?:Quarter|Financial|Results|Update|Report|Highlights)s?\s+(?:And|and|&)\s+", "", p_)
        if q_ != p_ and _pwords(q_):
            r["project"] = p_ = q_
        if not _pwords(p_):
            m_ = re.search(r"\b((?-i:[A-Z][A-Z0-9]{1,6}))\s+" + re.escape(p_) + r"\b", h + " . " + b[:3000], re.I)
            r["project"] = m_.group(1) + " " + p_ if m_ and m_.group(1) not in ("ITS", "THE", "FOR", "AT", "ON", "OF") else None
        elif re.search(r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b|\bSuite\b|\bStreet\b", p_) or \
                re.search(r"(?i)\bNew\s+" + re.escape(p_), h + " " + b[:3000]) and \
                re.match(r"(?i)(?:Brunswick|South\s+Wales|Mexico|Zealand|Caledonia|York|Jersey|Hampshire)\s+(?:Project|Property)$", p_):
            r["project"] = None
    body_sents = [x for x, hl_ in sents if not hl_]
    # JUR_ROW (1.0.4): a release naming several projects gives each row its own project's place
    multi = _several_projects(rows, hl_projs, projs_all)
    jcache = {}
    for r in rows:
        if not r["authority"]:
            r["authority"] = _release_auth(r, body_sents, r["permit_type"])
        # 1.0.8 (guide QA): a drill permit the BLM or the US Forest Service approves is a plan of operations or notice
        if r["permit_type"] == "drill_exploration" and \
                (r["authority"] in ("Bureau of Land Management", "U.S. Forest Service") or
                 not r["authority"] and any(_US_FED.search(x) for x in r["sents"])):
            r["permit_type"] = "plan_of_operations"
    out = []
    for r in rows:
        s = r["sent"]
        clause = s[max(0, r["a"] - 200):r["e"] + 220]
        pid = _ID_RX.search(clause)
        term = _TERM_RX.search(clause) or _TERM_PRE.search(clause)
        exp = None
        for t_ in [clause] + r["sents"]:
            exp = _EXPIRY_RX.search(t_)
            if exp:
                break
        # PERMIT_V2: the row's other sentences, then (one-permit releases, or a sentence naming this permit) the body
        term_t, exp_iso = (term.group(1), None) if term else (None, None)
        if not term_t or not exp:
            nm = re.sub(r"(?i)\b(?:permits?|licen[cs]es?|approvals?|the|an?)\b", " ", r["permit_name"] or "").split()
            tw_ = _TERM_WORDS_AGR if r["permit_type"] == "land_community" else _TERM_WORDS
            pool = list(r["sents"]) + [x for x in body_sents if x not in r["sents"] and tw_.search(x) and
                                       not _TERM_NOT.search(x) and
                                       (len(rows) == 1 or any(w.lower() in x.lower() for w in nm if len(w) > 2))]
            for t_ in pool:
                a_, b_ = _term_in(t_)
                if a_ and not term_t:
                    term_t = a_
                if b_ and not exp_iso and not exp:
                    exp_iso = b_
                if term_t and (exp or exp_iso):
                    break
        ev = s if len(s) <= 200 else s[max(0, r["a"] - 60):max(0, r["a"] - 60) + 200]
        row = {"permit_type": r["permit_type"], "project": r["project"], "status": r["status"],
               "authority": r["authority"], "date": _stage_date(r, dl), "permit_name": r["permit_name"],
               "permit_id": pid.group(1).strip() if pid else None,
               "term": term_t,
               "expiry": T._iso(re.search(T._DATE_RX, exp.group(1), re.I)) if exp else exp_iso,
               "scope": _scope_in(r["sents"] + ([x for x in body_sents if not _TERM_NOT.search(x)] if len(rows) == 1 else [])),
               "holder": _holder_in(r["sents"] + (body_sents if len(rows) == 1 else []), issuer, b),
               "jurisdiction": _row_juris(r, h, body_sents, juris, jcache, issuer) if multi else juris, "metal": metal, "evidence": ev.strip()}
        # numbered leases or licences renewed together are one row each (they chain and expire separately)
        ids = None
        for t_ in r["sents"]:          # PERMIT_V1 audit fix: the row's own sentences only
            m = _LEASE_IDS.search(t_)
            if m and r["permit_type"] == "drill_exploration" and re.match(r"(?i)(?:Tenures|Titles|Leases)", m.group(0)):
                m = None                   # claim tenures listed next to a drill permit are not permits
            if m and r["permit_type"] in ("mining_licence", "drill_exploration", "water"):
                ids = [x for x in m.groups() if x]
                break
        if ids and len(ids) > 1:
            spans = []
            for t_ in r["sents"]:
                spans = re.findall(r"(?i)from\s+(" + T._DATE_RX + r")\s+(?:to|until|through)\s+(" + T._DATE_RX + r")", t_)
                if len(spans) == len(ids):
                    break
            ends = []
            for t_ in r["sents"]:
                ends = [T._iso(m) for m in re.finditer(r"(?i)" + T._DATE_RX, t_)
                        if re.search(r"(?i)\b(?:to|until|through)\s+$", t_[max(0, m.start() - 12):m.start()])]
                if len(ends) == len(ids):
                    break
            for j, i in enumerate(ids):
                rr = dict(row)
                rr["permit_id"] = i
                if len(ends) == len(ids):
                    rr["expiry"] = ends[j]
                out.append(rr)
        else:
            out.append(row)
    for r in out:
        if isinstance(r["authority"], _CutName):
            r["authority"] = None       # FIX5 r2: authority names whole or blank
    return {"rows": out[:8], "reason": None if out else "no_stage"}


# ------------------------------------------------------------------ records
def extract(headline: str, body: str) -> list:
    a = analyse(headline, body)
    if not a["rows"]:
        return [F.Record(KIND, facts=[F.Fact("is_permit", value_num=0.0),
                                      F.Fact("reason", value_text=a["reason"] or "none")], confidence=0.0)]
    out = []
    for r in a["rows"]:
        fs = [F.Fact("is_permit", value_num=1.0)]
        for k in TXT_FIELDS:
            v = r.get(k)
            if v not in (None, ""):
                fs.append(F.Fact(k, value_text=str(v)[:300]))
        out.append(F.Record(KIND, facts=fs, confidence=1.0))
    return out


def parse_records(rows_by_ordinal):
    """{ordinal: [(field, seq, value_num, value_text)]} -> the analyse()-shaped dict."""
    rows = []
    for ordinal in sorted(rows_by_ordinal):
        r = {k: None for k in TXT_FIELDS}
        yes = False
        for field_, seq, num, text in rows_by_ordinal[ordinal]:
            if field_ == "is_permit":
                yes = num == 1.0
            elif field_ in TXT_FIELDS:
                r[field_] = text
        if yes and r["status"]:
            rows.append(r)
    return {"is_permit": bool(rows), "rows": rows}


JUDGED = ("permit_type", "project", "status", "authority", "date", "permit_name", "permit_id", "expiry", "jurisdiction",
          "metal", "term", "holder")     # PERMIT_V2: term and holder are on the page, so the judge sees them


def to_prediction(records):
    if not records:
        return None
    rows = {i: [(f.field, f.seq, f.value_num, f.value_text) for f in rec.facts] for i, rec in enumerate(records)}
    p = parse_records(rows)
    if not p["rows"]:
        return None
    return {"rows": [{k: r.get(k) for k in JUDGED} for r in p["rows"]]}


def _borrowed_source(mod, alias, user_file):
    """The source of the parts of another reader this reader uses: every `alias.NAME` in user_file, plus whatever
    those parts use from that module's top level, followed to the end. A change anywhere else in that module
    leaves this reader's fingerprint alone; a change to anything it runs changes it."""
    import ast
    src = open(mod.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    top = {}
    for node in tree.body:
        if isinstance(node, ast.If) and "__main__" in (ast.get_source_segment(src, node.test) or ""):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [(a.asname or a.name).split(".")[0] for a in node.names]
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            tg = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [n.id for t in tg for n in ast.walk(t) if isinstance(n, ast.Name)]
        else:
            # module-level code that changes a name (a loop filling a table, a .update() call): filed under every
            # name it stores into or calls a method on
            names = [n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)]
            names += [n.value.id for n in ast.walk(node)
                      if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)]
        for nm in names:
            top.setdefault(nm, []).append(node)
    user = ast.parse(open(user_file, encoding="utf-8").read())
    want = sorted({n.attr for n in ast.walk(user)
                   if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == alias})
    seen, nodes, stack = set(), [], list(want)
    while stack:
        nm = stack.pop()
        if nm in seen:
            continue
        seen.add(nm)
        for node in top.get(nm, ()):
            if node not in nodes:
                nodes.append(node)
                stack.extend(n.id for n in ast.walk(node) if isinstance(n, ast.Name))
    lines = src.splitlines()
    parts = []
    for node in sorted(nodes, key=lambda n: n.lineno):
        first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        parts.append("\n".join(lines[first - 1:node.end_lineno]))
    return "uses " + " ".join(want) + "\n" + "\n\n".join(parts)


def _code_sha():
    # PERMIT_V2 (1.0.2): portal/fingerprint.py -- this file, plus exactly the code it runs from the Technical reader
    # and from the shared project-name helper, so a change to either bumps this reader (1.0.1 hashed Technical by hand
    # with _borrowed_source below, which would have missed the helper)
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

    fill = " The property is road accessible and hosts several gold showings along a regional structure." * 3
    lead = "Vancouver, British Columbia, March 2, 2026 -- ABC Gold Corp. (TSXV: ABC) (\"ABC\" or the \"Company\") "

    def rows(h, b):
        return [(r["permit_type"], r["status"], r["project"], r["authority"]) for r in analyse(h, lead + b + fill)["rows"]]

    eq("drill permit granted",
       rows("ABC Receives Drill Permit for Alpha Gold Project",
            "is pleased to announce it has received a drilling permit from the Ontario Ministry of Mines for its Alpha Gold "
            "Project in Ontario."),
       [("drill_exploration", "granted", "Alpha Gold Project", "Ontario Ministry of Mines")])
    eq("plan of operations with BLM",
       rows("ABC Submits Plan of Operations for Beta Project",
            "has submitted a Plan of Operations to the Bureau of Land Management (BLM) for its Beta Project in Nevada."),
       [("plan_of_operations", "applied", "Beta Project", "Bureau of Land Management")])
    eq("EA started",
       rows("ABC Commences Environmental Assessment for Gamma Copper Project",
            "announces that the British Columbia Environmental Assessment Office has accepted the Initial Project "
            "Description, formally commencing the environmental assessment of its Gamma Copper Project."),
       [("environmental_assessment", "in_review", "Gamma Copper Project", "British Columbia Environmental Assessment Office")])
    eq("planned permit",
       rows("ABC Provides Update on Delta Project",
            "reports progress at its Delta Project. The Company will apply for a mining lease for the Delta Project later "
            "this year."),
       [("mining_licence", "planned", "Delta Project", None)])
    eq("exchange approval is not a permit",
       rows("ABC Receives TSXV Approval for Acquisition of Epsilon Property",
            "has received conditional approval from the TSX Venture Exchange for its acquisition of the Epsilon Property."),
       [])
    eq("court approval is not a permit",
       rows("ABC Obtains Final Court Approval for Plan of Arrangement",
            "has obtained a final order of the Supreme Court of British Columbia approving the plan of arrangement."), [])
    eq("background permit is not a row",
       rows("ABC Starts Drilling at Zeta Project",
            "has started its fully permitted drill program at the Zeta Project, under its existing exploration permit."), [])
    eq("renewal",
       rows("ABC Receives Mining Lease Renewal for Eta Mine",
            "announces that its mining lease at the Eta Mine has been renewed for a further thirty (30) years."),
       [("mining_licence", "renewed", "Eta Mine", None)])
    eq("community agreement",
       rows("ABC Signs Exploration Agreement with Theta First Nation",
            "has signed an exploration agreement with Theta First Nation covering its Iota Project."),
       [("land_community", "granted", "Iota Project", "Theta First Nation")])
    recs = extract("ABC Receives Drill Permit for Alpha Gold Project",
                   lead + "has received a drilling permit for its Alpha Gold Project." + fill)
    p = to_prediction(recs)
    eq("round trip", [(x["status"], x["project"]) for x in p["rows"]], [("granted", "Alpha Gold Project")])
    eq("no permit words", analyse("ABC Closes Private Placement", lead + "closed a private placement." + fill)["rows"], [])
    # PERMIT_V1 recall fix (2026-09-22): headlines that report a permit without naming a permit pattern
    upd = "announces an update on its exploration plans."
    eq("approval for drill program", rows("ABC Receives Approval for Drill Program at Kappa Gold Project", upd),
       [("drill_exploration", "granted", "Kappa Gold Project", None)])
    eq("BLM approval -> plan of operations", rows("ABC Receives BLM Approval for Drill Program at Kappa Gold Project", upd),
       [("plan_of_operations", "granted", "Kappa Gold Project", "Bureau of Land Management")])
    eq("submits permit application", rows("ABC Submits Permit Application for Drill Program at Kappa Gold Project", upd),
       [("drill_exploration", "applied", "Kappa Gold Project", None)])
    eq("initiates permitting (FIX5: a permitting process only started is planned, guide QP)",
       rows("ABC Initiates Permitting Process to Drill Kappa Gold Project", upd),
       [("drill_exploration", "planned", "Kappa Gold Project", None)])
    eq("ECA", [r[:2] for r in rows("ABC Receives Final Environmental Compliance Approval", upd)],
       [("environmental_assessment", "granted")])
    eq("priority project", rows("ABC's Kappa Gold Project Named a Priority Project by the Province of British Columbia", upd),
       [("government_policy", "granted", "Kappa Gold Project", "Province of British Columbia")])
    eq("identified as a major priority project",
       rows("ABC's Kappa Gold Project Identified as a Major Priority Project by the Government of British Columbia", upd),
       [("government_policy", "granted", "Kappa Gold Project", "Government of British Columbia")])
    eq("a tenure named 'Permit' is not a permit",
       rows("ABC Announces Start of Drilling at its Daina Gold Permit", upd), [])
    eq("typo recieved", [r[:2] for r in rows("Drilling Permit Recieved on Kappa Gold Project", upd)],
       [("drill_exploration", "granted")])
    eq("approval for a placement is not a permit",
       rows("ABC Receives Approval for Private Placement to Fund Drill Program", upd), [])
    eq("approval to re-log core is not a permit",
       rows("ABC Receives Approval to Re-log and Sample 2014 Drill Core from its Kappa Project", upd), [])
    # PERMIT_V1 audit fixes (2026-09-22): the 60-release audit of corpus run c2
    eq("tenure described is not a grant",
       rows("ABC Reports Resource at Kappa Gold Project", "reports a resource. The Kappa Gold Project comprises three "
            "granted and contiguous exploration permits covering 900 km2."), [])
    eq("an agency's name is not a permit",
       rows("ABC Reports Road Milestone", "has received support from the Impact Assessment Agency of Canada for the road."), [])
    eq("claim tenures do not split a drill permit",
       len(rows("ABC Receives Drill Permit for Kappa Gold Project", "has received its drilling permit for the Kappa Gold "
                "Project, which grew with recently approved claims tenures 1137374 and 1137373.")), 1)
    eq("contracts for an application are planned",
       [r[:2] for r in rows("ABC Secures Contracts for Bulk Sample Permit Application at Kappa Gold Project", upd)],
       [("other", "planned")])
    # FP_NARROW: the fingerprint takes the Technical code this reader runs, and none of the rest
    b = FP.borrowed_source(T, "T", __file__)
    eq("fingerprint: Technical code used", ("_DATE_RX = " in b, "def _prepare(" in b), (True, True))
    eq("fingerprint: Technical code not used", ("def extract(" in b, "SPEC = " in b, "def _projects_in(" in b),
       (False, False, False))
    pb = FP.borrowed_source(PN, "PN", __file__)
    eq("fingerprint: helper code used", all(("def %s(" % f) in pb for f in ("find", "primary", "same", "_parts")), True)
    eq("fingerprint: helper followed", FP.uses(__file__, "portal.project_names"), True)
    # PERMIT_V2 (1.0.2)
    r = analyse("Alpha Metals Receives Drill Permit for Birch Lake Project",
                "TORONTO, June 3, 2026 -- Alpha Metals Corp. (TSXV: ALP) is pleased to announce that it has received its "
                "drill permit for the Birch Lake Project. The permit was issued by the Ontario Ministry of Mines and is "
                "valid for two years. It allows up to 12 drill pads.")["rows"]
    eq("authority from another sentence", [x["authority"] for x in r], ["Ontario Ministry of Mines"])
    eq("term from another sentence", [x["term"] for x in r], ["two years"])
    eq("scope", [x["scope"] for x in r], ["up to 12 drill pads"])
    r = analyse("Beta Gold Receives Drill Permit for Cedar Project and Agrees to Acquire the Gamma Project",
                "VANCOUVER, May 1, 2026 -- Beta Gold Corp. (CSE: BGC) announces that it has received a drill permit for "
                "its Cedar Project. The Company has also agreed to acquire the Gamma Project from a private vendor. The "
                "Gamma Project hosts historic workings. The Gamma Project is 20 km away.")["rows"]
    eq("a project being acquired is not the permit's", [x["project"] for x in r], ["Cedar Project"])
    r = analyse("Delta Resources Receives Exploration Permit",
                "LIMA, April 2, 2026 -- Delta Resources Ltd. (TSXV: DRL) is pleased to announce that the exploration "
                "permit for the Huaca Project, held by Minera Delta Peru S.A.C., the Company's wholly-owned subsidiary, "
                "has been approved. The permit is valid from April 1, 2026 to March 31, 2029.")["rows"]
    eq("holder, term and expiry", [(x["holder"], x["term"], x["expiry"]) for x in r],
       [("Minera Delta Peru S.A.C.", "April 1, 2026 to March 31, 2029", "2029-03-31")])
    eq("provincial approval is not the federal agency's",
       _release_auth({"permit_name": "Provincial Environmental Assessment Approval", "project": None, "a": 0, "e": 10,
                      "sent": "Provincial Environmental Assessment Approval"},
                     ["The Company completed the review by the Canadian Nuclear Safety Commission for the licence."],
                     "environmental_assessment"), None)
    # JUR_V2 (1.0.3): the jurisdiction rule
    eq("juris: a securities legend is not a place",
       _jurisdiction("Dark Star Makes Payment Under Letter of Intent",
                     ["The Khan West Project is set in Namibia's renowned Erongo uranium province.",
                      "The securities have not been registered under the United States Securities Act of 1933 and may not "
                      "be offered or sold in the United States absent registration."]), "Namibia")
    eq("juris: a ticker is not a place; '(the Project)' is not a dateline",
       _jurisdiction("Stuhini Stakes Additional Land at Ruby Creek",
                     ["Stuhini Exploration Ltd. (TSXV: STU) ( USA : STXPF) announces staking on the Ruby Creek Project "
                      "in Northern British Columbia (the \"Project\").",
                      "The project is located 20 kilometres east of Atlin, BC ."]), "British Columbia, Canada")
    eq("juris: a project named after a country",
       _jurisdiction("Benton Completes Option on Baril Lake Project and Plans Drilling on Panama Project in Red Lake "
                     "Mining District",
                     ["Benton entered an agreement with Rio Tinto Exploration Canada Inc.",
                      "It will drill the Panama Lake gold project in the Red Lake Mining District.",
                      "A second series of holes will test the Panama Zone.",
                      "Maxtech may earn an interest in the Panama Gold Project and the Panama property."]), "Ontario, Canada")
    eq("juris: names that hold a place",
       _jurisdiction("Mammoth Reports Results From Tenoriba Project",
                     ["The Tenoriba property is in the Sierra Madre precious metal belt, Mexico.",
                      "The Cerro Colorado area remains untested.", "Cerro Colorado contains ledges of quartz.",
                      "Dr. Ressel obtained his PhD from the University of Nevada, Reno.",
                      "Lithium Chile Inc. and Franco-Nevada were not involved."]), "Mexico")
    eq("juris: the country's mentions count for its state",
       _jurisdiction("Century Lithium's Angel Island Added to FAST-41",
                     ["Angel Island, in Esmeralda County, Nevada, was added to the dashboard.",
                      "It hosts one of the largest lithium deposits in the United States.",
                      "It is one of few advanced lithium projects in the United States."]), "Nevada, USA")
    eq("juris: 'located in' late in the release is another project's",
       _jurisdiction("Origen Sells Newfoundland Lithium Project",
                     ["The Newfoundland Lithium assets are an exceptional opportunity.", "Highlights follow.",
                      "The deal closes soon.", "Terms are below.",
                      "NewPeak has a right of first refusal on the Los Sapitos Lithium Project located in Argentina."]),
       "Newfoundland and Labrador, Canada")
    eq("juris: offering provinces, and an all-capitals headline",
       _jurisdiction("ABC OPTIONS BURRO CREEK GOLD PROPERTY IN ARIZONA",
                     ["The private placement is offered on a non-brokered basis in the Provinces of Alberta, Yukon and "
                      "Ontario.", "The Burro Creek property is in Mohave County, Arizona."]), "Arizona, USA")
    eq("juris: the About paragraph and an address are not the project's",
       _jurisdiction("ABC Stakes Claims in Qu\u00e9bec",
                     ["ABC staked 120 claims in Qu\u00e9bec.", "The claims cover a greenstone belt.",
                      "About ABC Corp. ABC holds projects in Nevada, Nevada and Nevada.",
                      "1111 Melville Street, Suite 1000 Vancouver, BC V6E 3V6, Canada"]), "Quebec, Canada")
    eq("juris: a named target, a company name, a trust company",
       [_jurisdiction("Aztec Receives Drill Permit at Cervantes Gold-Copper Project, Sonora, Mexico",
                      ["Drilling will test the primary California target zone.", "The California target is open."]),
        _jurisdiction("Pan Global Welcomes Approval of Grupo Mexico's Adjacent Los Frailes Mine",
                      ["Los Frailes is adjacent to the Escacena Project in southern Spain."]),
        _jurisdiction("Five Star Completes Qualifying Transaction",
                      ["The Catalao Project is located in the Coromandel district of Goias State, Brazil.",
                       "Shares are held by Computershare Trust Company of Canada, as escrow agent.",
                       "Computershare Trust Company of Canada will release them."])],
       ["Sonora, Mexico", "Spain", "Goi\u00e1s, Brazil"])
    eq("juris: the About paragraph is read when nothing comes before it",
       _jurisdiction("Canadian North Amends Consultants' Options",
                     ["The board amended options.", "The options vest over two years.",
                      "About Canadian North Resources Inc. The Ferguson Lake property is in the Kivalliq Region of "
                      "Nunavut, Canada."]), "Nunavut, Canada")
    eq("juris: a valley before its state, a provincial survey, a bracketed newswire dateline",
       [_jurisdiction("Noram Receives Permits for Zeus Drill Campaign",
                      ["Permits for drilling the Zeus Lithium Project in Clayton Valley Nevada were received."]),
        _jurisdiction("Exploits Consolidates Dog Bay Claims",
                      ["The rocks were mapped by the Newfoundland and Labrador Geological Survey."]),
        _jurisdiction("Boron One Receives Approval for its Geological Elaborate",
                      ["December 11, 2023 Victoria, BC [ACCESSWIRE] Boron One Holdings Inc. announces the approval."])],
       ["Nevada, USA", "Newfoundland and Labrador, Canada", None])
    eq("juris: a property named after a state; a conference town",
       [_jurisdiction("Sky Gold Acquires Second Gold Property in Central Newfoundland",
                      ["The second property is known as the Virginia Property, in Central Newfoundland.",
                       "The Virginia Property comprises 100 hectares."]),
        _jurisdiction("Northisle Provides Update", ["The North Island Project is in British Columbia.",
                                                    "Events: Denver Gold Forum, Colorado Springs, CO."])],
       ["Newfoundland and Labrador, Canada", "British Columbia, Canada"])
    eq("juris: ', QC' after a property; 'Ireland-based' is an office",
       [_jurisdiction("Emgold to Sell its East-West Property, QC to O3 Mining", ["Emgold sells East-West."]),
        _jurisdiction("Sokoman Completes Drilling at Clarks Brook",
                      ["Core will be examined by experts from Dublin, Ireland -based, Earth Tectonics Ltd.",
                       "Clarks Brook is in central Newfoundland."])],
       ["Quebec, Canada", "Newfoundland and Labrador, Canada"])
    eq("juris: a region stands for its province",
       _jurisdiction("XYZ Options Property in the Golden Triangle", ["XYZ optioned the Tami property."]),
       "British Columbia, Canada")
    # JUR_ROW (1.0.4): each row's own place when the release names several projects
    q2 = ("reports its second quarter results. The Fekola Mine in Mali produced 120,000 ounces of gold. Fekola Regional "
          "drilling continued in Mali. The Mali government signed a new mining convention for Fekola. At the Goose "
          "Project in Nunavut, the Company received the Type A Water Licence from the Nunavut Water Board. Construction "
          "of the Goose Project continues. Otjikoto in Namibia produced 40,000 ounces.")
    eq("juris per row: a quarterly's Goose licence is Nunavut, not Mali",
       [(r["project"], r["jurisdiction"]) for r in analyse("ABC Reports Second Quarter 2026 Results", lead + q2 + fill)["rows"]],
       [("Goose Project", "Nunavut, Canada")])
    two = ("received a drilling permit from the Ontario Ministry of Mines for its Alpha Gold Project in Ontario. The "
           "Company also received a drill permit from the Quebec Ministry of Natural Resources for its Beta Project in Quebec.")
    eq("juris per row: two projects, two provinces",
       sorted((r["project"], r["jurisdiction"]) for r in analyse("ABC Receives Drill Permits for Alpha and Beta", lead + two + fill)["rows"]),
       [("Alpha Gold Project", "Ontario, Canada"), ("Beta Project", "Quebec, Canada")])
    mix = ("reports its results. Drilling continued at the Mount Milligan Mine in British Columbia and the Oksut Mine in "
           "Turkey. The Company received the operating permit for the Oksut Mine from the Turkish Ministry of Environment. "
           "Mount Milligan produced 40,000 ounces. Mount Milligan is in British Columbia.")
    eq("juris per row: a sentence naming two projects counts from this one's name",
       [(r["project"], r["jurisdiction"]) for r in analyse("ABC Reports Second Quarter Results", lead + mix + fill)["rows"]],
       [("Oksut Mine", "T\u00fcrkiye")])
    dt = ("is pleased to announce plans to advance its gold projects in Saskatchewan, Canada (the \"Goldfields Project\") "
          "and Chiapas, Mexico (the \"Ixhuatan Project\"). The Company received a drill permit for the Ixhuatan Project "
          "from the Mexican authorities. Drilling will start at the Goldfields Project in June.")
    eq("juris per row: a defined term's place comes before it",
       [(r["project"], r["jurisdiction"]) for r in analyse("ABC Announces Plans for Gold Projects", lead + dt + fill)["rows"]],
       [("Ixhuatan Project", "Mexico")])
    tc = ("has received a drilling permit for its Texas Canyon Project, Nevada, and continues work at its Golden Trail "
          "Project in Idaho. The Golden Trail Project lies 40 km from the Texas border.")
    eq("juris per row: a place inside the project's name is not read",
       [(r["project"], r["jurisdiction"]) for r in analyse("ABC Receives Drill Permit for Texas Canyon", lead + tc + fill)["rows"]],
       [("Texas Canyon Project", "Nevada, USA")])
    one = ("received a drilling permit for its Alpha Gold Project. The Alpha Gold Project is in Canada, 40 km from the "
           "Beta Project. The Beta Project lies near Timmins, Ontario.")
    eq("juris per row: the project's sentences say only Canada, the release says Ontario",
       [r["jurisdiction"] for r in analyse("ABC Receives Drill Permit for Alpha Gold Project", lead + one + fill)["rows"]],
       ["Ontario, Canada"])
    # 1.0.5: several projects per release (helper 1.0.5)
    two = ("provides an update on its Alpha Gold Project and its Beta Copper Project. At the Alpha Gold Project, "
           "construction of the mill continues on schedule. The Company received the water licence from the Nunavut "
           "Water Board in May. At the Beta Copper Project, drilling resumed in June. The Company also received a drill "
           "permit for Beta Copper from the Bureau of Land Management for the fall program.")
    eq("1.0.5 each permit takes the project its sentence names",
       sorted(r["project"] for r in analyse("ABC Provides Project Updates", lead + two + fill)["rows"]),
       ["Alpha Gold Project", "Beta Copper Project"])
    part = ("received the permits for its Alpha Gold Project and Beta Copper Project. The Company received the drilling "
            "permit from the Ministry for the Beta Copper portion of its flagship Alpha Gold Project.")
    eq("1.0.5 a portion of a project is not its own project", _pm_part_of("Beta Copper Project", part), True)
    eq("1.0.5 a short name in the permit sentence wins", _pm_project_at(
        "At Mont Sorcier, drilling continued. At Lagoa Salgada, the environmental licence was granted in May.",
        "At Lagoa Salgada, the environmental licence was granted in May.", 0, None,
        ["Mont Sorcier High Purity DRI Iron Project", "Lagoa Salgada Polymetallic Project"]),
       "Lagoa Salgada Polymetallic Project")
    eq("1.0.5 no neighbour, company or generic name", (
        _pm_project_at("x. Silver Range has received prospecting permits near the Meadowbank Mine in Nunavut.",
                       "Silver Range has received prospecting permits near the Meadowbank Mine in Nunavut.", 0, None,
                       ["Atlantis Property", "Meadowbank Mine"]),
        _pm_project_at("x. Regulus received drill permits for the Regulus Concessions.",
                       "Regulus received drill permits for the Regulus Concessions.", 0, None,
                       ["Antakori Project", "Regulus Concessions"], (), "Regulus Resources Inc."),
        _pm_project_at("x. It has FAST-41 Transparency Project status.", "It has FAST-41 Transparency Project status.", 0,
                       None, ["Bend Copper-Gold Project", "FAST-41 Transparency Project"])), (None, None, None))
    far = "The drill permit was received for the program" + " and the crews" * 20 + " at Loki."
    eq("1.0.5 rev 5: not inside another name, not far from the permit words", (
        _pm_project_at("x. EIA law is the New Brunswick Mining Act.", "EIA law is the New Brunswick Mining Act.", 0, None,
                       ["Nash Creek Project", "Brunswick No. 12 Mine"]),
        _pm_project_at("x. The BLM approved a plan at Pure Energy's Clayton Valley project.",
                       "The BLM approved a plan at Pure Energy's Clayton Valley project.", 8, None,
                       ["McGee Lithium Project", "Clayton Valley Project"]),
        _pm_project_at("x. " + far, far, 4, None, ["Loki Project", "Ldg Diamond Project"]),
        _pm_project_at("x. A permit for Loki was received.", "A permit for Loki was received.", 2, None,
                       ["Loki Project", "Ldg Diamond Project"])), (None, None, None, "Loki Project"))
    el = ("The Eliza Plan of Operations Permit has been submitted and awaiting final government approval for the "
          "Passynak and Belmont areas.")
    eq("1.0.5 rev 6: the row's own project named near the permit words stays", _pm_project_at(
        "x. " + el, el, 15, "Eliza High-Grade Silver and Copper Project",
        ["Eliza High-Grade Silver and Copper Project", "Passynak Mine"]), None)
    # 1.0.6 (READERFIX): project, one row per permit, background, stage wording
    def r6(h, b):
        return [(r["permit_type"], r["status"], r["project"]) for r in analyse(h, lead + b + fill)["rows"]]
    eq("1.0.6 an NCIB notice of intention is not a permit",
       r6("ABC Announces Normal Course Issuer Bid", "has filed a Notice of Intention to Make a Normal Course Issuer Bid "
          "with the TSX Venture Exchange."), [])
    eq("1.0.6 a refusal in other words is contested",
       r6("ABC Provides Permit Update for Alpha Gold Project", "reports that the Ministry declined to issue the drill "
          "permit for its Alpha Gold Project in Ontario."), [("drill_exploration", "contested", "Alpha Gold Project")])
    eq("1.0.6 a permit before the courts is contested",
       r6("ABC Provides Permit Update for Alpha Gold Project", "reports that the environmental licence for its Alpha Gold "
          "Project is subject to a judicial review filed by a local group."),
       [("environmental_assessment", "contested", "Alpha Gold Project")])
    eq("1.0.6 a modification is renewed",
       r6("ABC Receives Approval for Alpha Gold Project", "has received approval of a minor modification to its Plan of "
          "Operations from the Bureau of Land Management for its Alpha Gold Project in Nevada."),
       [("plan_of_operations", "renewed", "Alpha Gold Project")])
    eq("1.0.6 the final stage of obtaining a licence is in review",
       r6("ABC Provides Update on Alpha Gold Project", "is at the final stage of obtaining the environmental licence for "
          "its Alpha Gold Project in Brazil."), [("environmental_assessment", "in_review", "Alpha Gold Project")])
    eq("1.0.6 an application deemed complete is in review",
       r6("ABC Provides Update on Alpha Gold Project", "reports that its mining lease application for the Alpha Gold "
          "Project has been deemed complete by the Department of Mines."), [("mining_licence", "in_review", "Alpha Gold Project")])
    eq("1.0.6 an application only scheduled is planned",
       r6("ABC Provides Update on Alpha Gold Project", "is expected to submit its mining licence application for the Alpha "
          "Gold Project in the third quarter."), [("mining_licence", "planned", "Alpha Gold Project")])
    eq("1.0.6 a grant said not to have happened is not granted",
       r6("ABC Provides Update on Alpha Gold Project", "notes that no exploitation permit has been granted to date for its "
          "Alpha Gold Project."), [("mining_licence", "planned", "Alpha Gold Project")])
    eq("1.0.6 a FONSI the company anticipates is awaited, and folds into the assessment",
       r6("ABC Provides Update on Alpha Gold Project", "anticipates receiving a Finding of No Significant Impact for the "
          "Alpha Gold Project in 2026 with approval of the Environmental Assessment."),
       [("environmental_assessment", "in_review", "Alpha Gold Project")])
    eq("1.0.6 a permitting process only started is planned",
       r6("ABC Begins Drill Permitting at Alpha Gold Project", "has commenced the drill permitting process at its Alpha "
          "Gold Project in Nevada."), [("drill_exploration", "planned", "Alpha Gold Project")])
    eq("1.0.6 a submission under review is in review",
       r6("ABC Provides Update on Alpha Gold Project", "reports that its Notice of Work submission for the Alpha Gold "
          "Project is now under technical review by the Ministry."), [("drill_exploration", "in_review", "Alpha Gold Project")])
    eq("1.0.6 a renewal still pending is in review",
       r6("ABC Provides Update on Alpha Gold Project", "has applied for the renewal of the exploration licence for its "
          "Alpha Gold Project, which is pending."), [("drill_exploration", "in_review", "Alpha Gold Project")])
    eq("1.0.6 an approval expected later is in review",
       r6("ABC Provides Update on Alpha Gold Project", "reports that approval of the Plan of Operations for its Alpha Gold "
          "Project is expected mid-2026."), [("plan_of_operations", "in_review", "Alpha Gold Project")])
    eq("1.0.6 a draft approval is still under review",
       r6("ABC Reports Public Meeting on Draft Government Approval of Its Mining Licence", "reports that the public meeting "
          "on the draft government approval of the mining licence for its Alpha Gold Project will be held in April."),
       [("mining_licence", "in_review", "Alpha Gold Project")])
    eq("1.0.6 an application made earlier and restated is in review",
       r6("ABC Provides Update on Alpha Gold Project", "The Company submitted its mining lease application for the Alpha "
          "Gold Project in October 2025 and continues baseline work."), [("mining_licence", "in_review", "Alpha Gold Project")])
    ea = "The Company has engaged a consultant for the completion of an Environmental Impact Statement for the project."
    eq("1.0.6 an assessment being completed is under way",
       _stage_near(ea, ea.find("Environmental"), ea.find(" for the project"), "environmental_assessment")[0], "in_review")
    eq("1.0.6 a permit sentence naming its ground in lower case",
       r6("ABC Provides Update on Alpha Gold Project", "drilling continues at the Alpha Gold Project. The Company also "
          "received a drill permit on its nearby Delta project in Ontario."), [("drill_exploration", "granted", "Delta Project")])
    eq("1.0.6 the project an earlier sentence named with the same permit",
       r6("ABC Provides Update on Alpha Gold Project and Beta Project", "The Beta Project Environmental Impact Assessment "
          "was prepared in 2025. Drilling continued at the Alpha Gold Project. The Environmental Impact Assessment was "
          "submitted to the Ministry in February."), [("environmental_assessment", "applied", "Beta Project")])
    eq("1.0.6 headline words are not a project, nor is a neighbour",
       (_clean_hl_proj("Help Finance Project"), _clean_hl_proj("Reviews Project Portfolio"),
        [p for _, p in _projects("The claims adjoin the Beta Copper Project to the north.", None)]), (None, None, []))
    eq("1.0.6 a zone or target inside the main project is that project",
       _project_near(0, [(5, "Gamma Zone")], None, "Alpha Gold Project"), "Alpha Gold Project")
    eq("1.0.6 a main project built from headline words is the reader's own name for it",
       r6("ABC Letter to Shareholders Lays Out Milestones That Will See Mill Commissioned and Alpha Mine in Production",
          "The Alpha Mine received its drill permits in February."), [("drill_exploration", "granted", "Alpha Mine")])
    eq("1.0.6 held permits are background",
       (r6("ABC Drills 12 m of 5 g/t Gold at Alpha Gold Project", "drilling at the Alpha Gold Project was undertaken "
           "pursuant to an exploration permit issued by the Ministry."),
        r6("ABC Reports Resource for Alpha Gold Project", "notes that all major environmental approvals are in place for "
           "the Alpha Gold Project."),
        r6("ABC Reports Results at Alpha Gold Project", "The exploration permit grants the holder the exclusive right to "
           "explore the Alpha Gold Project for three years."),
        r6("ABC Drills 12 m of 5 g/t Gold at Alpha Gold Project", "These holes are an aggressive step-out owing to receipt "
           "of the Exploration Plan of Operations at the Alpha Gold Project.")), ([], [], [], []))
    eq("1.0.6 a permit named as a place, or as what an application is made on",
       (bool(_PLACE_PRE.search("The new target lies in the northern zone of the ")),
        bool(_PLACE_PRE.search("The licences applied for are for the ")), bool(_PLACE_PRE.search("has applied for the "))),
       (True, True, False))
    eq("1.0.6 a recap of an earlier receipt is background",
       r6("ABC Starts Drilling at Alpha Gold Project", "Further to the receipt of the drill permit announced earlier, "
          "drilling has started at the Alpha Gold Project."), [])
    eq("1.0.6 a grant within two months of the release is its news",
       r6("ABC Drills 12 m of 5 g/t Gold at Alpha Gold Project", "The Company received the drill permit for the Alpha Gold "
          "Project in January 2026 and has completed 20 holes."), [("drill_exploration", "granted", "Alpha Gold Project")])
    eq("1.0.6 folds: decision document, exploration environmental approval, generic permit beside the EIA",
       tuple(_fold_into({"permit_type": xt, "status": "granted", "permit_name": xn, "project": "A", "authority": None},
                        {"permit_type": mt, "status": "granted", "permit_name": mn, "project": "A", "authority": None})
             for xt, xn, mt, mn in (("plan_of_operations", "FONSI", "plan_of_operations", "Plan of Operations"),
                                    ("environmental_assessment", "DIA", "drill_exploration", "Drill Permit"),
                                    ("environmental_assessment", "Environmental Permit", "environmental_assessment", "EIA"),
                                    ("mining_licence", "Mining Licence", "drill_exploration", "Drill Permit"))),
       (True, True, True, False))
    eq("1.0.6 a Record of Decision on an EIS is one row",
       r6("ABC Receives Record of Decision for Alpha Gold Project", "The Bureau of Land Management issued the Record of "
          "Decision (ROD) approving the Environmental Impact Statement (EIS) for the Alpha Gold Project in Nevada."),
       [("environmental_assessment", "granted", "Alpha Gold Project")])
    eq("1.0.6 an acronym the release defines: its permit, or not a permit",
       (_acro_defs("the Installation License (LI) was filed"), _acro_defs('an Earn-In Agreement (the "EIA") with')),
       ({"LI": "Installation License"}, {"EIA": None}))
    eq("1.0.6 an Earn-In Agreement (EIA) is not an assessment",
       r6("ABC Drilling Update at Alpha Gold Project", "In 2024 ABC entered into an Earn-In Agreement (the \"EIA\") with "
          "Major Mining. Under the EIA, Major Mining was granted an option to earn 70% of the Alpha Gold Project."), [])
    eq("1.0.6 the same permit restated with its quantities is one row",
       r6("ABC Provides Update on Delta Project", "At the Alpha Gold Project, 25 mining concessions are now granted. "
          "Drilling continued at the Delta Project. With 25 mining concessions now granted, the team is working with "
          "local communities."), [("mining_licence", "granted", "Alpha Gold Project")])
    rs = {"status": "granted", "hl": False, "sent": "It has received the drill permit previously announced on February 10, "
          "2026 for the project."}
    rs["sents"] = [rs["sent"]]
    rt = dict(rs, sent="On February 10, 2026, the Company received the drill permit for the project.")
    rt["sents"] = [rt["sent"]]
    eq("1.0.6 the date a release announced it is not the stage's date",
       (_stage_date(rs, "2026-03-02"), _stage_date(rt, "2026-03-02")), (None, "2026-02-10"))
    eq("1.0.6 small helpers: first date, U.S. sentence glue, ticker",
       (_first_date("May 27, 2025 ABC Breaks Ground at Alpha"),
        _glue(["It received approval from the U.S.", "Bureau of Land Management."]),
        bool(_TICKER_PRE.search("ABC (NYSE: "))),
       ("2025-05-27", ["It received approval from the U.S. Bureau of Land Management."], True))
    # 1.0.7 (OWN_NEWS): a release about something else writes rows only for its own permit news
    up = "ABC Provides Update on Alpha Gold Project"
    eq("1.0.7 not a mining release, a newswire listing page",
       (analyse("Leaf Co Signs Supply Deal", "Leaf Co. reports that its partner has been granted its Conditional Use "
                "Permit by the city zoning administrator to operate a manufacturing facility.")["rows"],
        analyse("Precious Metals News", "2026-03-02 10:14 AM EDT | Other Corp. Receives Drill Permit for Its Project "
                "2026-03-02 09:10 AM EDT | Third Corp. Reports Drilling 2026-03-01 08:00 AM EDT | Fourth Corp. Closes "
                "Placement. The Ministry has approved the drill permit for the gold project.")["rows"]),
       ([], []))
    eq("1.0.7 the property given away: its permits are the property",
       r6("ABC Options Alpha Gold Project to Major Mining PLC", "Drill targets have been defined and a drill permit has "
          "been approved for further drilling at the Alpha Gold Project."), [])
    eq("1.0.7 held ground described: consists of, in hand, is approved for this area, possessive, maintains",
       [r6("ABC Commences Drilling at Alpha Gold Project", "The Alpha Gold Project comprises 4,000 hectares of granted "
           "mining and exploration licences in Chile."),
        r6("ABC Receives Proceeds from Warrant Exercises", "\"With drill permits in hand, we expect to move quickly at the "
           "Alpha Gold Project.\""),
        r6("ABC Exploration Update", "A drill permit is approved for this area of the Alpha Gold Project."),
        r6("ABC Provides Royalty Update", "The operator will complete monitoring plans outlined in the Alpha Gold Project's "
           "approved environmental assessment."),
        r6("ABC Closes Placement to Secure Alpha Gold Project", "The Alpha mill is approved and maintains all required "
           "operating permits.")],
       [[], [], [], [], []])
    eq("1.0.7 earlier news: a grant 'issued by' as a description, a see-release reference, a dated grant",
       [r6("ABC Announces Resource for Alpha Gold Project", "The resource sits within the mining concession issued by the "
           "National Mining Agency."),
        r6("ABC Intersects 20 m of 2 g/t Gold at Alpha Gold Project", "Drilling extends north where the surface access "
           "agreements were recently signed (see August 2, 2025 news release)."),
        r6("ABC Makes New Discovery at Alpha Gold Project", "Alpha was the first of three drilling permits submitted by "
           "the Company, which was granted by the Ministry in May 2025.")],
       [[], [], []])
    eq("1.0.7 staking, a stage of long ago, an option notice, a new director's past work",
       [r6("ABC Increases Land Position at Alpha Gold Project", "ABC made application for an additional 18 claims; the "
           "land position was expanded to secure the mining rights to areas needed for roads."),
        r6(up, "In January 1888 prospectors reported high grades and eight gold mining lease applications were lodged "
               "across the property."),
        r6("ABC to Exercise Option on Alpha Gold Project", "ABC has issued a Notice of Intention to exercise the property "
           "option and will make the final payment."),
        r6("ABC Appoints New Director", "Ms. Smith has 20 years of experience and previously led the environmental "
           "impact assessment of the Omega Mine.")],
       [[], [], [], []])
    eq("1.0.7 hypotheticals and conditions are not stages",
       [r6(up, "If a drill permit is received for the Delta project, some metres may be diverted there."),
        r6(up, "The mining license may be increased further pending results of the drilling program."),
        r6(up, "Funding is subject to fulfilling all applicable requirements associated with the project environmental "
               "assessments.")],
       [[], [], []])
    eq("1.0.7 the boilerplate paragraph is not the release's news",
       r6("ABC Files Quarterly Report", "ABOUT ABC GOLD CORP. ABC Gold Corp. is a mining and exploration company "
          "progressing the Alpha Gold Project to start-up having now received a mining permit for the Project."), [])
    # rows on the right ground
    eq("1.0.7 the ground named right after the permit, in a release about something else",
       r6("ABC Commences Trading on the TSXV", "We advance exploration on the Alpha Gold Project and the Delta Creek "
          "Project, with an application for an exploration license at Delta Creek near the town."),
       [("drill_exploration", "applied", "Delta Creek Project")])
    eq("1.0.7 the place a sentence opens with",
       r6("ABC Reports Second Quarter Results", "reports its results. At Delta, the Company continued advancing environmental "
          "assessment work, planning for submission of the EIS in 2026. At the Alpha Gold Project, drilling continued."),
       [("environmental_assessment", "in_review", "Delta")])
    eq("1.0.7 a release about several projects: the place the passage just named",
       r6("ABC Provides Corporate Update", "Drilling continued at the Alpha Gold Project and the Omega Project. The Delta "
          "Creek property is 100 km from Lima and has good access. The Company's water permits have been received for "
          "drilling."), [("water", "granted", "Delta Creek")])
    eq("1.0.7 a claim block or deposit is reported on its project",
       r6("ABC Completes Surface Program at the Beta Claims", "The Company has received an Exploration Permit for the "
          "Beta claims within its flagship Alpha Gold Project."), [("drill_exploration", "granted", "Alpha Gold Project")])
    eq("1.0.7 a permit document's qualifier is no project name", _clean_hl_proj("Draft Mine"), None)
    # one row per permit
    eq("1.0.7 the Notice of Intent that starts a mining-lease application is that application",
       r6("ABC Applies for Mining Lease at Alpha Gold Project", "ABC has now initiated the process to receive a Mining "
          "Lease for the mining claims related to the Beta Zone with the submission of a Notice of Intent to the Ministry "
          "of Mines."),
       [("mining_licence", "applied", "Alpha Gold Project")])
    eq("1.0.7 an assessment filed for drill permits is the drill permit (QD)",
       r6("ABC Outlines 2026 Catalysts for Alpha Gold Project", "The surveys will form the basis of an Environmental "
          "Impact Assessment report, to be submitted to the Federal Environmental Office for drill permits."),
       [("drill_exploration", "planned", "Alpha Gold Project")])
    # stages said in other words
    eq("1.0.7 stage wordings",
       [r6(up, s_) for s_ in (
           "The Company is looking forward to receipt of its drill permit for the Alpha Gold Project within Q2.",
           "Mining at the Alpha Gold Project will begin following issuance of the Small Mine Permit.",
           "The Plan of Operations, when approved, will allow drilling at the Alpha Gold Project.",
           "An exploration drill permit application for the Alpha Gold Project is underway.",
           "A drill permit application has been submitted for the Alpha Gold Project, and the Company is finalizing "
           "plans to commence drilling.",
           "The Company has received a drilling permit required to start its program at the Alpha Gold Project.",
           "The modified Drill Permit for the Alpha Gold Project increases the area permitted by 74%.",
           "An amended Notice of Intent for the Alpha Gold Project is currently under review with the Bureau of Land "
           "Management.",
           "The Company is advancing environmental assessment work at the Alpha Gold Project.",
           "On February 5, 2026 the Ministry decided to reject the mining lease application for the Alpha Gold Project.",
           "The Ministry approved a two-year extension of the exploration license for the Alpha Gold Project.")],
       [[("drill_exploration", "in_review", "Alpha Gold Project")], [("mining_licence", "planned", "Alpha Gold Project")],  # 1.0.8: mine permit
        [("plan_of_operations", "planned", "Alpha Gold Project")], [("drill_exploration", "planned", "Alpha Gold Project")],
        [("drill_exploration", "applied", "Alpha Gold Project")], [("drill_exploration", "granted", "Alpha Gold Project")],
        [("drill_exploration", "renewed", "Alpha Gold Project")], [("plan_of_operations", "in_review", "Alpha Gold Project")],
        [("environmental_assessment", "in_review", "Alpha Gold Project")], [("mining_licence", "contested", "Alpha Gold Project")],
        [("drill_exploration", "renewed", "Alpha Gold Project")]])
    eq("1.0.7 small helpers: IBAS is no IBA, a word-processor bullet starts a sentence",
       ([n for _, _, _, n in _mentions("under the Industrial Base and Sustainability (IBAS) program", 0)],
        _glue(["Highlights: \uf0b7 Alpha \u2013 drilling continued \uf0b7 Delta \u2013 Received its operating permits"])),
       ([], ["Highlights:", "Alpha \u2013 drilling continued", "Delta \u2013 Received its operating permits"]))
    # 1.0.7 (FIX3): full-text losses -- tagged permit news the 1.0.6/1.0.7 filters dropped
    eq("1.0.7 FIX3 an acronym defined by permit words is that permit; one defined otherwise is not",
       (_acro_defs('an Environmental Impact Authorization ("EIA") was granted'),
        _acro_defs("the Exploration Information Systems (EIS) project"), _acro_defs('an Earn-In Agreement (the "EIA") with'),
        r6(up, 'ABC has filed an application to extend the term of the Environmental Impact Authorization ("EIA") for the '
               'Alpha Gold Project and has initiated legal proceedings to protest the lack of a formal response.'),
        r6(up, "The Company has received an Exploration Information Systems (EIS) grant for the Alpha Gold Project.")),
       ({}, {"EIS": None}, {"EIA": None}, [("environmental_assessment", "in_review", "Alpha Gold Project")], []))
    eq("1.0.7 FIX3 'further to' an earlier release, a stage reported now is news",
       [r6("ABC Completes Option of Alpha Gold Project to Major Mining", "Further to its news release dated July 30, 2026, "
           "ABC has now received an outstanding drill permit and has satisfied all conditions of the option agreement for "
           "the Alpha Gold Project."),
        r6("ABC Completes Option of Alpha Gold Project to Major Mining", "Further to its news release dated July 30, 2026, "
           "ABC received an outstanding drill permit for the Alpha Gold Project."),
        r6(up, "Further to the news release dated June 7, 2026, ABC is now in the process of receiving the final grant "
               "(Permis de Recherches) for the three exploration permits of the Alpha Gold Project.")],
       [[("drill_exploration", "granted", "Alpha Gold Project")], [],
        [("drill_exploration", "in_review", "Alpha Gold Project")]])
    eq("1.0.7 FIX3 decision words: Ministers accept the approval, an agreement completed, a permit named 'to Initiate'",
       [r6("ABC Reports Government Approvals for the Alpha Road", "The Responsible Ministers have accepted the "
           "environmental assessment approval for the Alpha Road, which serves the Alpha Gold Project."),
        r6("ABC Completes Land Access Agreement with Major Utility", "ABC has signed a lease with Major Utility for land "
           "required for the Alpha Gold Project."),
        r6("ABC Receives Authorisation to Initiate Activities at Its Alpha Gold Project", "ABC has received approval of its "
           "Authorization to Initiate Exploration Activities (\"AIEA\") from the Ministry of Energy and Mines and is fully "
           "permitted to carry out a drilling program at its Alpha Gold Project.")],
       [[("environmental_assessment", "granted", "Alpha Gold Project")], [("land_community", "granted", "Alpha Gold Project")],
        [("drill_exploration", "granted", "Alpha Gold Project")]])
    eq("1.0.7 FIX3 a reclamation bond posted for the approved permit is the permit's news",
       r6("ABC Updates Progress at the Alpha Gold Property", "ABC has posted a reclamation bond with the Bureau of Land "
          "Management as part of the requirement for its approved drilling permit at the Alpha Gold Property."),
       [("plan_of_operations", "granted", "Alpha Gold Property")])
    eq("1.0.7 FIX3 stages: admitted for evaluation, an application something will enable, a dated 'following receipt'",
       [r6(up, 'An environmental impact declaration (Declaracion Impacto Ambiental) (the "DIA") for the Alpha Gold Project '
               "has been approved for admittance by the Ministry of Energy and Mines. The DIA provides the coordinates for "
               "the 40-hole drilling program that ABC intends to carry out."),
        r6(up, "Upon completion, ABC expects to have its access approvals, enabling application to the regional government "
               "for the Authorisation to Commence Activities at the Alpha Gold Project."),
        r6(up, 'Following receipt of the Alpha Gold Project Environmental Approval (the "RCA") in November 2025, ABC '
               "completed the scheduled submission of the critical permits to the mining agency in February 2026."),
        r6(up, "Following receipt of the Alpha Gold Project Environmental Approval, ABC will start construction.")],
       [[("drill_exploration", "in_review", "Alpha Gold Project")], [("drill_exploration", "planned", "Alpha Gold Project")],
        [], [("environmental_assessment", "planned", "Alpha Gold Project")]])
    eq("1.0.7 FIX3 the assessment something was approved with is held",
       r6(up, "ABC plans a 50 km spur road to the Alpha Gold Project which was approved with the environmental assessment "
              "for the mine."), [])
    # 1.0.8 (FIX4): accuracy -- one permit named twice, Brazil's LP/LI/LO, a stage word between two permits, background,
    # whose ground, one row per permit, stage wordings, types
    eq("1.0.8 one permit named twice: the assessment that is the drill permit, the permit another one is for",
       [r6("ABC Files Drill Permit at Alpha Gold Project", 'ABC has formally submitted an Environmental Impact Assessment - '
           'Semi-detailed ("EIA-Sd") drill permit application for the Alpha Gold Project.'),
        r6(up, 'The Ministry of Environment has issued the Environmental Clearance Certificates ("ECC") for Exclusive '
               'Prospecting License ("EPL") 7071 covering the Alpha Gold Project, clearing the way for drilling.')],
       [[("drill_exploration", "applied", "Alpha Gold Project")], [("drill_exploration", "granted", "Alpha Gold Project")]])
    eq("1.0.8 Brazil's LP, LI and LO; no social licence to operate",
       [r6("ABC Receives the LP for the Full Mining License at Alpha Gold Project", 'The State Environmental Council has issued '
           'the Licenca Previa ("LP") for the Full Mining License at the Alpha Gold Project. This is expected to lead to the '
           'request of both the installation license ("LI") and the operating license ("LO") during March 2026.'),
        r6(up, "ABC maintains its social licence to operate with local communities at the Alpha Gold Project. The licence "
               "to operate is strong.")],
       [[("environmental_assessment", "granted", "Alpha Gold Project"), ("construction_operating", "planned", "Alpha Gold Project"),
         ("construction_operating", "planned", "Alpha Gold Project")], []])
    def _st8(s_, nm):
        ms_ = _mentions(s_, 0)
        a_, e_, t_, _n = [m_ for m_ in ms_ if m_[3] == nm][0]
        return _stage_near(s_, a_, e_, t_, [(x_, y_) for x_, y_, _, _ in ms_])[0]
    eq("1.0.8 a stage word between two permits belongs to the nearer one, within its clause",
       (_st8('the preliminary licence ("LP"), which has now been granted, followed by the installation license ("LI")',
             "installation license"),
        _st8("Though the LI remains under suspension, the LP was revalidated by SEMAS in 2022.", "LI")),
       (None, "contested"))
    eq("1.0.8 background: a grant in the past, ground held, held in a headline, an agency's remit, an agency named "
       "after a permit",
       [r6(up, "Exploration permits were issued in the past for drilling atop the Alpha Gold Project, where uranium was "
               "intersected."),
        r6("ABC Submits Exploration Permit Application for Delta Project", "ABC has submitted an exploration permit "
           "application for the Delta Project. ABC now holds one 100%-owned exploration license covering the Omega prospect."),
        r6("ABC Receives Conditional Listing Approval; drill permits in place to allow for immediate exploration",
           "ABC has received conditional approval to list its shares."),
        r6("ABC Receives Regulatory Approval for Tailings at Alpha Gold Project", "SEMARNAT, the federal agency in charge of "
           "environmental permitting, has approved modifications to the existing operating permit for the Alpha Gold Project."),
        r6(up, "SLR will oversee modifications to the already submitted Plan of Operations for the Alpha Gold Project and will "
               "support engagement with the FAST-41 Permitting Council.")],
       [[], [("drill_exploration", "applied", "Delta Project")], [],
        [("construction_operating", "renewed", "Alpha Gold Project")], [("plan_of_operations", "in_review", "Alpha Gold Project")]])
    eq("1.0.8 whose ground: not the earlier permit's, not a region's portfolio, Mt is Mountain, no 'Project Notice'",
       (r6("ABC Secures Second Drilling Approval", "ABC has received a Notice of Approval for its drilling notification at the "
           "Delta Project. This approval represents the second drilling authorization granted to ABC, following the "
           "previously announced receipt of approval for its Alpha Gold Project."),
        [p_ for _, p_ in _projects("ABC receives drill permits at its Yukon Gold Projects and the Alpha Gold Project", None)],
        _same_project("Alpha Mt Project", "Alpha Mountain Project"),
        [p_ for _, p_ in _projects("filing of the Project Notice for the Alpha Gold Project", None)]),
       ([("drill_exploration", "granted", "Delta Project")], ["Alpha Gold Project"], True, ["Alpha Gold Project"]))
    eq("1.0.8 one row per permit: FTA environmental permit, the assessment a project description starts, the generic "
       "permit an ESIA leads to; other permits still needed and the next amendment stay apart",
       [r6("ABC Receives FTA Environmental Permit for the Alpha Gold Project", "ABC has received the FTA environmental permit "
           "for its drilling program at the Alpha Gold Project from the Ministry of Energy and Mines."),
        r6(up, "ABC has filed the Initial Project Description with the Impact Assessment Agency of Canada for the Alpha Gold "
               "Project. The filing of the Initial Project Description is the first step in the Environmental and Social Impact "
               "Assessment, approval of which is required under federal law."),
        r6(up, "ABC has submitted the ESIA for the Alpha Gold Project. The submission of the ESIA is a prerequisite for "
               "obtaining an environmental permit."),
        r6(up, "The ESIA for the Alpha Gold Project is under review by the Ministry. Environmental permits will be required in "
               "advance of construction."),
        r6(up, "ABC received a Plan of Operations from the Bureau of Land Management for the Alpha Gold Project. The next "
               "anticipated extension of the current Plan of Operations, currently under internal review, will open new areas "
               "to drilling."),
        _names_compatible("Operating License", "license to operate")],
       [[("drill_exploration", "granted", "Alpha Gold Project")], [("environmental_assessment", "in_review", "Alpha Gold Project")],
        [("environmental_assessment", "applied", "Alpha Gold Project")],
        [("environmental_assessment", "in_review", "Alpha Gold Project"), ("environmental_assessment", "planned", "Alpha Gold Project")],
        [("plan_of_operations", "granted", "Alpha Gold Project"), ("plan_of_operations", "planned", "Alpha Gold Project")], True])
    eq("1.0.8 stage wordings",
       [r6(up, s_) for s_ in (
           "ABC intends to file its Installation License application for the Alpha Gold Project in August 2026. The Company "
           "anticipates it will be granted the Installation License three months thereafter.",
           "We look forward to the receipt of the expanded mining permit for the Alpha Gold Project. The Company has now filed "
           "an application for the expanded mining permit.",
           "The Company is hopeful of receiving the completed Exploitation Concession for the Alpha Gold Project in the third "
           "quarter.",
           "ABC expects to deliver a feasibility study and an approved Exploitation Concession for the Alpha Gold Project during "
           "the third quarter.",
           "Figure 1 shows the currently permitted area and the proposed 2026 drill permit expansion at the Alpha Gold Project.",
           "ABC has been granted an extension to a previously issued water permit for the Alpha Gold Project.",
           "ABC has filed two amended Notice of Intent permits with the Bureau of Land Management for the Alpha Gold Project.",
           "Remaining regulatory requirements to commence construction at the Alpha Gold Project include receipt of the "
           "Provincial Pollutant Control Facility Permit.",
           "This is the foundation of future licensing initiatives to migrate to the Full Mining License at the Alpha Gold "
           "Project during 2027.",
           "Baseline data will be incorporated into an ESIA for the Alpha Gold Project which is necessary for an application for "
           "a mining license.",
           "At the Alpha Gold Project, mining license application submission, environmental permitting progressing.",
           "BMR began the project by initiating operating and environmental permit modifications at the Alpha Gold Project.")]
       + [r6("ABC Receives Drill Permit Expansion at Alpha Gold Project", "The expanded permit adds 40 drill pads.")],
       [[("construction_operating", "planned", "Alpha Gold Project")], [("mining_licence", "applied", "Alpha Gold Project")],
        [("mining_licence", "in_review", "Alpha Gold Project")], [("mining_licence", "in_review", "Alpha Gold Project")],
        [("drill_exploration", "planned", "Alpha Gold Project")], [("water", "renewed", "Alpha Gold Project")],
        [("plan_of_operations", "applied", "Alpha Gold Project")],
        [("construction_operating", "planned", "Alpha Gold Project")],
        [("mining_licence", "planned", "Alpha Gold Project")], [("mining_licence", "planned", "Alpha Gold Project")],
        [("mining_licence", "applied", "Alpha Gold Project"), ("environmental_assessment", "in_review", "Alpha Gold Project")],
        [("environmental_assessment", "in_review", "Alpha Gold Project")], [("drill_exploration", "renewed", "Alpha Gold Project")]])
    eq("1.0.8 'challenging' as an adjective is no challenge",
       (bool(_ST_CONTESTED.search("the LP is the most critical and challenging to secure")),
        bool(_ST_CONTESTED.search("lawsuits challenging, among other things, the issuance"))), (False, True))
    eq("1.0.8 types: an Advanced Exploration Permit, a BLM drill permit; environmental and social studies are no permit",
       [r6(up, "ABC has applied for an Advanced Exploration Permit for the Alpha Gold Project."),
        r6(up, "The Bureau of Land Management approved the drill permit for the Alpha Gold Project."),
        r6(up, "Having completed all required environmental and social studies, ABC submitted its drill permit application for "
               "the Alpha Gold Project.")],
       [[("drill_exploration", "applied", "Alpha Gold Project")], [("plan_of_operations", "granted", "Alpha Gold Project")],
        [("drill_exploration", "applied", "Alpha Gold Project")]])
    # FIX5 (1.0.9)
    def r9(h, b):
        return [(r["permit_type"], r["status"], r["project"], r["authority"]) for r in analyse(h, lead + b + fill)["rows"]]
    eq("FIX5 stage: the work a release starts is no review; a stage word across a semicolon is another statement",
       [r9("ABC Receives 5-Year Exploration Permit and Commences 18,000-metre Drill Program at Alpha Gold Project",
           "announces the permit.")[0][1],
        r9("ABC Applies for 5-yr Exploration Permit; Grants Stock Options", "applies for a permit on the Alpha Property.")[0][1]],
       ["granted", "applied"])
    eq("FIX5 stage: a grant reported after the submission; an approval process; the resource caveat",
       [r9(up, "The Company submitted a Notice of Intent to drill with the Bureau of Land Management for the Alpha Gold "
               "Project and has received approval subject to the completion of bonding."),
        r9(up, "The hearing represents the final step in the federal approval process for the Alpha Gold Project's "
               "Environmental Assessment."),
        r9(up, "The estimate of mineral resources at the Alpha Gold Project may be materially affected by environmental "
               "permitting, legal, title, taxation, sociopolitical, marketing, or other relevant issues.")],
       [[("plan_of_operations", "granted", "Alpha Gold Project", "Bureau of Land Management")],
        [("environmental_assessment", "in_review", "Alpha Gold Project", None)], []])
    eq("FIX5 awaited and planned: looking forward to a FONSI; planning for applications; permitting only commenced",
       [r9(up, "ABC is looking forward to a Finding of No Significant Impact (\"FONSI\") and formal approval of the "
               "Plan of Operations for the Alpha Gold Project late this year."),
        r9(up, "Planning for drill permit applications at the Alpha Gold Project is now underway."),
        r9("ABC Commences Permitting of Alpha Property for 2026 Drill Program", "begins permitting.")],
       [[("plan_of_operations", "in_review", "Alpha Gold Project", None)],
        [("drill_exploration", "planned", "Alpha Gold Project", None)],
        [("drill_exploration", "planned", "Alpha Property", None)]])
    fl = analyse("ABC Announces Filing of Environmental Impact Statement",
                 lead + "announces the submission of the Environmental Impact Statement (\"EIS\") for the environmental "
                 "assessment of the Alpha Gold Project. "
                 "The Company submitted the EIS in two parts with the initial volume issued on January 7, 2026, and the final "
                 "volume on February 20, 2026. This phase of the process gives the public an opportunity to submit their "
                 "views of the EIS." + fill)["rows"]
    eq("FIX5 a filing another sentence states is applied, dated to its last step",
       [(r["status"], r["date"]) for r in fl], [("applied", "2026-02-20")])
    eq("FIX5 one row per project the permit is for, one row per community an agreement is signed with",
       [sorted(x[2] for x in r9("ABC Receives Permits for Drilling on its Alpha, Beta and Gamma Properties",
                                "announces the permits.")),
        sorted(x[3] for x in r9(up, "The submission included letters of support from the Alder River Dene Nation (ARDN) "
                                    "and the Birch Lake Dene Nation (BLDN). In addition, ABC has signed Benefit Agreements "
                                    "with the ARDN and BLDN for the Alpha Gold Project to support Indigenous "
                                    "employment and training."))],
       [["Alpha Property", "Beta Property", "Gamma Property"],
        ["Alder River Dene Nation (ARDN)", "Birch Lake Dene Nation (BLDN)"]])
    eq("FIX5 authorities named in full: a board, a national government, a county, a bureau, an issuer named after the permit",
       [r9(up, "ABC has received a land use permit for the Alpha Gold Project from the Alder Valley Land and Water Board."),
        r9(up, "The Government of Ruritania has granted a two-year renewal of the prospecting licence for the Alpha Gold "
               "Project."),
        r9("ABC Receives One Year Extension for Drill Permit from Alder County", "for the Alpha Gold Project."),
        r9(up, "The US Department of the Interior's Bureau of Land Management approved the Notice of Intent for the "
               "Alpha Gold Project."),
        r9("ABC Receives Final Permits for Alpha Gold Project",
           "is in receipt of the Land Use License issued by the Alder Inuit Association for the Alpha Gold Project.")],
       [[("drill_exploration", "granted", "Alpha Gold Project", "Alder Valley Land and Water Board")],
        [("drill_exploration", "renewed", "Alpha Gold Project", "Government of Ruritania")],
        [("drill_exploration", "granted", "Alpha Gold Project", "Alder County")],
        [("plan_of_operations", "granted", "Alpha Gold Project", "Bureau of Land Management")],
        [("other", "granted", "Alpha Gold Project", "Alder Inuit Association")]])
    eq("FIX5 project names that are no names: an acronym put back, a province, a defined short name",
       [[x[2] for x in r9("ABC Receives Drill Permit for its ABCD Lithium Property in NWT", "announces the permit.")],
        [x[2] for x in r9("ABC Secures Drilling Permit for New Brunswick Project", "announces the permit.")],
        [x[2] for x in r9("ABC Resumes Operations at the AU Underground Mine",
                          "announces that operations resumed at its Alder Underground Mine (\u201cAU Underground "
                          "Mine\u201d). The Company's operations at the AU Underground Mine were temporarily suspended due "
                          "to the expiration of its safety production permit. ABC received its safety production permit "
                          "renewal.")]],
       [["ABCD Lithium Property"], [None], ["Alder Underground Mine"]])
    eq("FIX5 permits named in more words; the operations suspended are not the permit",
       [r9("ABC Receives Final Permit Required to Restart the Alpha Mine",
           "is pleased to announce it has received all permits for the Alpha Mine. ABC received the amended Mined Land "
           "Reclamation Plan (MLRP) approval from the State of Arizona. The MLRP, along with the Aquifer Protection Permit "
           "(APP) issued this month, completes the approvals."),
        [x[:2] for x in r9("ABC Resumes Operations at the AU Underground Mine",
                           "announces that operations resumed at its Alder Underground Mine (\u201cAU Underground "
                           "Mine\u201d). The Company's operations at the AU Underground Mine were temporarily suspended "
                           "due to the expiration of its safety production permit. ABC received its safety production "
                           "permit renewal.")]],
       [[("other", "renewed", "Alpha Mine", "State of Arizona"), ("water", "granted", "Alpha Mine", None)],
        [("construction_operating", "renewed")]])
    eq("FIX5 a permit named by what it allows, only where no permit is named",
       [r9("ABC Receives Airborne Survey Permit", "has received the permit (the \"Permit\") to fly an airborne "
                                                  "geophysical survey on its Alpha Property."),
        r9("ABC Receives Drill Permit", "has received a drill permit for the Alpha Property, and the permit to conduct "
                                         "drilling follows.")],
       [[("drill_exploration", "granted", "Alpha Property", None)], [("drill_exploration", "granted", "Alpha Property", None)]])
    # FIX5 r2: authority names whole or blank
    def an(t):
        return [str(n) if not isinstance(n, _CutName) else None for _, _, n in _authorities(t)[0]]
    eq("FIX5 r2 a name read whole: a word before it, a list after it, a wrapped word, a state the patterns do not list",
       [an("The drill permit extension came from San Alfonso County."),
        an("ABC received approval from the Ministry of Rivers, Forests and Parks (MRFP) for the drill program."),
        an("A registration was submitted to the Lake Assessment Division of the Government of Newfoundland and Labr ador "
           "in relation to the road."),
        an("ABC filed a notice with the Minnesota Department of Lakes for the drill program."),
        an("ABC Signs Exploration Agreement With Alder Lake First Nation")],
       [["San Alfonso County"], ["Ministry of Rivers, Forests and Parks"],
        ["Lake Assessment Division of the Government of Newfoundland and Labrador"], ["Minnesota Department of Lakes"],
        ["Alder Lake First Nation"]])
    eq("FIX5 r2 a name not read whole is blank: two bodies, a name that goes on, a possessive, a report title",
       [an("Input came from the Ministry of Rivers Canada and Climate Change, Fisheries Canada and Transport Canada."),
        an("This is the key step to scheduling a Federal Commission Hearing date."),
        an("ABC Gold's Board and Management approved the plan."),
        an("See the Technical Report Alder Mining Division for details.")],
       [[None], [None], [None], [None]])
    eq("FIX5 r2 a short name the release defines stands for the full name",
       an("the Zedland Ministry of Rivers, Lakes and Parks (\u201cMinistry of Rivers\u201d) has approved the amended "
          "Environmental Impact Assessment."),
       ["Zedland Ministry of Rivers, Lakes and Parks", "Zedland Ministry of Rivers, Lakes and Parks"])
    eq("FIX5 r2 rows: the whole name, or blank",
       [r9("ABC Receives Drill Permit for Alpha Gold Project",
           "is pleased to announce it has received a drilling permit from the Ministry of Rivers, Forests and Parks for "
           "its Alpha Gold Project in Ontario."),
        r9("ABC Receives Drill Permit for Alpha Gold Project",
           "is pleased to announce it has received a drilling permit from the Ministry of Rivers Canada and Climate "
           "Change, Fisheries Canada and Transport Canada for its Alpha Gold Project in Ontario, with the support of "
           "Alder Lake First Nation.")],
       [[("drill_exploration", "granted", "Alpha Gold Project", "Ministry of Rivers, Forests and Parks")],
        [("drill_exploration", "granted", "Alpha Gold Project", None)]])
    eq("fingerprint: stable", _code_sha(), SPEC.code_sha)
    print("permits: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return bad


if __name__ == "__main__":
    import sys
    sys.exit(1 if self_test("-v" in sys.argv) else 0)
