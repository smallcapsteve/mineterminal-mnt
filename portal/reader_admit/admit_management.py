"""Outside-tag admission rule for the Management Changes reader.

admit(headline, text, categories, out) -> (bool, short_reason)

A release that does not carry the "Management Changes" tag is admitted only when at least one of the
reader's rows names a real person AND a sentence of the release that names that person says, in plain
change language, that the person is joining, leaving or changing role (appointed, resigned, retiring,
stepping down, replaced, succeeded, has joined the board ...).  Everything else the reader picks up
outside the tag is background: quoted speakers, QPs, webinar hosts, lenders, AGM slates that were simply
re-elected, recaps of changes announced in an earlier release, deal terms that let someone "appoint a
director" without naming anyone, and junk "names" read from headings or tables.

Round 2 (2026-09-30), after a fresh sample of 60 round-1 admissions: also refused are "names" that are common
phrases (a heading or job title: the first word is an ordinary lower-case word in the body, or the name only ever
follows "a/an/the"), firms appointed or engaged for a piece of work, appointments to an outside body (a
government or industry council), a lender's or investor's right to nominate a director, and "welcome" said of
anything but a person taking a role.

Round 5 (2026-10-02), after the ACC150b blind re-check of the releases this rule had tagged (two thirds right):
- recaps.  In a periodic or review release (quarterly/annual results, production report, year in review,
  annual or shareholder letter, summary of the year, "provides (corporate) update") a change counts only when
  the sentence announces it now ("is pleased to announce", "has resigned", "will retire", "effective
  immediately", "welcomes X as"); a change told in the simple past as part of the period's highlights
  ("Appointed X to the Board in March 2024", "The appointment of X as ...", "X joined the Company as COO") is
  a recap of earlier news.  Not a recap release: one whose headline names a management change ("Corporate
  Update ~Appointment of COO~") or whose lead announces one ("pleased to announce the appointment of ...");
- a person described by a past status ("former directors X and Y have exercised their options", "vendor and
  retired geologist X"): counted only when the sentence also announces a change now.

Round 6 (2026-10-02), after the conf6 blind sample of round-5 admissions (88% right):
- wire-service listing pages (a category or company page listing many companies' headlines with time stamps)
  are never one company's news;
- history told in the simple past.  In a release whose headline and lead are about something else (a deal, a
  strategy statement, a feature, a meeting notice), a change told only in the simple past ("X was appointed to
  the Board of Y", "the recent appointment of its new CFO", "resigned from both positions on <date>", "Following
  X's resignation") is background, unless the sentence also announces it now (see round 5), puts it in the
  future or conditional ("would join", "is expected to"), or ties it to this release's deal ("In connection
  with the Acquisition, X was appointed", "concurrent with closing");
- a meeting notice (materials mailed, circular filed, shareholders urged to vote) is not a meeting-results
  release: past changes there are history and nominees are only standing;
- an appointment "as <title> of the <tribunal / council / ministry ...>" is to an outside body, like "appointed
  to the <council>" (round 2);
- a firm or its principal engaged as financial / financing advisor is a mandate, not a position.

Standard library only, deterministic, no I/O.
"""
import re

# ---------------------------------------------------------------------------------------------------------
# 1. Is the row's "person" a person?  (junk rows: table headings, place names, deal names, empty names)
# ---------------------------------------------------------------------------------------------------------
# Text normalisation (names and body): non-breaking spaces, Unicode hyphens and curly apostrophes.
_TRANS = str.maketrans({"\U000000a0": " ", "\U00002010": "-", "\U00002011": "-", "\U00002019": "'", "\U00002018": "'"})
_HONORIFIC = re.compile(r"^(?:messrs\.?|mr\.?|mrs\.?|ms\.?|dr\.?|prof\.?|sir)\s+", re.I)
# Words that never occur in a person's name but do occur in what the reader sometimes reads as one:
# organisations and deals ("Resulting Issuer", "Option Agreement", "Orfo Loan", "Auditor ..."), table and
# heading words ("Selected Drill", "Composite Assay", "Area Depth"), places ("... Lake", "... Zone"), and
# headline verbs picked up with a capitalised word ("Inform Confirms", "Electing Robert Wares").
_NOT_NAME_WORD = re.compile(
    r"\b(?:issuer|agreement|options?|loan|warrants?|claims?|property|project|company|corp|inc|ltd|limited|"
    r"resources|mining|metals|capital|group|consortium|nation|auditors?|legislation|"
    r"drill|assay|width|table|area|depth|historical|composite|studies|easting|northing|elevation|azimuth|dip|"
    r"results?|update|program|best|"
    r"lake|river|creek|brook|zone|deep|mine|"
    r"announces|confirms|electing|acquire)\b", re.I)


def _clean_name(p):
    p = _HONORIFIC.sub("", (p or "").translate(_TRANS).strip())
    return re.sub(r"\s+", " ", p)


# Particles, and given names that are also ordinary English (or geology) words, are left out of the common-word
# test below: "Will", "Grant", "Mark" or "Clay" used in lower case says nothing about the name.
_PARTICLES = {"de", "da", "del", "van", "von", "der", "la", "le", "di", "du", "dos", "das"}
_WORD_NAMES = set(
    "will mark grant bill frank rich dawn hope guy pat rob don art chase gene max joy faith grace drew jack carol "
    "lance cliff bob ray sandy rusty penny ruby amber crystal jean jay dean wade hunter sterling earl duke glen dale "
    "clay heath rock stone summer april june may august rose brook gray grey miles warren norman victor pierce reed "
    "rod nick sue bud ward lane wood holly ivy iris sky river autumn jade pearl skip chip ford carter mason baker "
    "cole bay page".split())


_STRIP = ".,;:()[]{}!?\"'\U0000201c\U0000201d\U00002019*"


def _lower_words(body):
    """The ordinary lower-case words of the body (e-mail addresses and web links left out)."""
    return {w for w in (t.strip(_STRIP) for t in body.split() if "@" not in t and "/" not in t)
            if w.islower() and w.isalpha()}


def _common_phrase(p, body, words):
    """A heading, a job title or a common phrase read as a name.  Two signs, both judged on the release body:
    - the first word (the "given name") is used in the body as an ordinary lower-case word ("Geotechnical
      Drilling", "Discussions Continuing", "District Valuer");
    - every mention of the "name" is preceded by an article ("an Authorised Land Officer"): people's names do not
      take "a", "an" or "the"."""
    first = p.split()[0].lower()
    if len(first) >= 3 and first not in _PARTICLES and first not in _WORD_NAMES and first in words:
        return True
    arts = [m.start() for m in re.finditer(re.escape(p), body)]
    return bool(arts) and all(re.search(r"\b(?:a|an|the)\s+$", body[max(0, k - 5):k], re.I) for k in arts)


def _is_person(p):
    """Two to five capitalised tokens, none of them a heading/place/deal word."""
    toks = p.split()
    if not 2 <= len(toks) <= 5:
        return False
    if _NOT_NAME_WORD.search(p):
        return False
    return all(t[:1].isupper() or t.lower() in ("de", "da", "del", "van", "von", "der", "la", "le", "di")
               for t in toks)


# ---------------------------------------------------------------------------------------------------------
# 2. Sentences.  Titles and initials keep their dots so that "Dr. X" and "R. Kim Tyler" stay in one sentence.
# ---------------------------------------------------------------------------------------------------------
# (Patterns start with a literal character so that they stay fast on 15,000-character bodies.)
_ABBR = re.compile(r"\.(?<=\b(?:Mr|MR|Ms|MS|Dr|DR|Jr|Sr|St|No|Co)\.)|\.(?<=\b(?:Mrs|MRS|Inc|INC|Ltd|LTD|Hon|Gov|Sen)\.)"
                   r"|\.(?<=\b(?:Corp|CORP|Prof)\.)|\.(?<=\bMessrs\.)")
_SPLIT = re.compile(r"[.!?](?<=[a-z0-9)\"\U0000201d'%][.!?])\s+(?=[A-Z\"\U0000201c(])|[\U00002022\U000025a0\U000025aa\U000025cf\U000025e6\U000025ba\U000025b6\U000025fe\U000025c6\U000027a2\U000027a4\U00002713\U00002714]|;\s|\n\s*\n")
# PDF-split hyphenated surnames: "Mercier -Langevin" / "Mercier- Langevin" -> "Mercier-Langevin"
_HYPH = re.compile(r" -(?=[A-Z][a-z])(?<=[a-z] -)|- (?=[A-Z][a-z])(?<=[a-z]- )")


def _norm(t):
    if not t.isascii():
        t = t.translate(_TRANS)
    return _ABBR.sub("", _HYPH.sub("-", t))


def _window(sent, key):
    """Text around the name, inside its sentence: long PDF "sentences" otherwise pull in unrelated verbs."""
    k = sent.find(key)
    return sent[max(0, k - 220): k + 260]


def _windows(sents, keys, limit=12):
    """One window per sentence that names the person."""
    out = []
    for raw in sents:
        if any(k in raw for k in keys):
            sent = " ".join(raw.split())
            key = next((k for k in keys if k in sent), None)
            if key:
                out.append(_window(sent, key))
                if len(out) >= limit:
                    break
    return out


# ---------------------------------------------------------------------------------------------------------
# 3. Change language around the person.
# ---------------------------------------------------------------------------------------------------------
# Joining / leaving / changing role, said of the person in the same sentence.
_CHANGE = re.compile(
    # appointed / resigned / retiring / stepping down (not "re-appointed", "reappointed")
    r"(?<!re-)(?<!re)\b(?:appoint(?:ed|s|ment)?|resign(?:ed|s|ing|ation)?|step(?:s|ped|ping)? down|"
    r"retir(?:e|es|ed|ing|ement)|did not (?:seek|stand)|not (?:be )?stand(?:ing)? for re-?election|"
    # replacing / succeeding someone, promoted, departure, leaving, death
    r"replac(?:e|ed|es|ing)|succeed(?:s|ed|ing)? (?:him|her|(?-i:[A-Z]))|successor|promot(?:ed|ion) (?:to|of)\b|"
    r"departure of|'s departure|(?:is |will be )?leaving (?:the|his|her) (?:position|role|company|board)|"
    r"passed away|passing of|terminated the employment|"
    # joining: "has joined the Company as", "joining our board", "addition of X to its Board", "welcome X as"
    r"addition of [^.]{0,80}?\bto (?:its|the|our) (?:board|advisory|management|team)|"
    r"(?:hired|hires|engaged|engages|retained) (?:mr |ms |mrs |dr )?(?-i:[A-Z])[^.]{0,50}?\bas (?:its |the |a |an )?|"
    r"has been named|named (?:as )?(?:the )?(?:new|interim|acting)|"
    r"welcom(?:e|es|ed|ing)\b[^.]{0,80}?\b(?:as (?:a |an |the |our |its )?(?:new |interim |acting )?(?:chief|ceo|cfo|coo|"
    r"president|director|chair|vice|vp|advisor|adviser|member|officer|manager|head|general counsel|corporate secretary|"
    r"(?:senior |chief |exploration |project )?geologist)|to (?:the|our|its) (?:board|team|company|management))\b|"
    r"join(?:s|ed|ing)?\b(?: (?:the|our|its|his|her))?(?: (?-i:[A-Z])[\w'-]*){0,4} (?:board|team|company|management|as\b)|"
    r"join(?:s|ed|ing)? (?:the |our |its )?(?:board|team|company|management)|"
    # new / incoming / takes on a role
    r"new (?:member|chief|ceo|cfo|coo|president|director|chair|vice|vp|advisor|strategic advisor|technical advisor)|"
    r"incoming|takes? on the (?:role|position)|assum(?:e|es|ed|ing) (?:a |the )?(?:new )?(?:role|position)|"
    r"accepted the position|will (?:serve|be) (?:as )?(?:the )?(?:new |interim )?(?:chief|ceo|cfo|coo|president|chair|"
    r"director|vice|vp)|reconstituted)", re.I)

# In a shareholder-meeting release only these count (election of a slate is not a change; "appointed the
# following officers" after the meeting is routine re-appointment).
_MEETING_STRONG = re.compile(
    r"\b(?:resign(?:ed|s|ing|ation)?|step(?:s|ped|ping)? down|retir(?:e|es|ed|ing|ement)|"
    r"did not (?:seek|stand)|not (?:be )?stand(?:ing)? for re-?election|replac(?:e|ed|es|ing)|"
    r"succeed(?:s|ed|ing)?|(?:has|have|was|were|will be) (?:been )?appointed|passed away|passing of|"
    r"addition of [^.]{0,80}?\bto (?:its|the|our) board|new (?:member|chief|ceo|cfo|"
    r"president|director|chair)|reconstituted)", re.I)
_MEETING_HEADLINE = re.compile(
    r"\b(?:AGM|AGSM|annual(?: general)?(?: and special)? meeting|special meeting|shareholders'? meeting|"
    r"meeting of (?:share|stock)holders)\b", re.I)
_MEETING_OUTCOME = re.compile(r"\b(?:results?|voting|vote|elect\w*|approv\w*)\b", re.I)

# A change reported as already announced in an earlier release (shareholder letters, recaps).
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_RECAP = re.compile(
    r"\b(?:previously announced|as announced|announced (?:on|in) |news release dated|announcement dated|"
    r"on " + _MONTH + r" \d{1,2}\s?(?:st|nd|rd|th)?,? \d{4},? [^.]{0,60}?\bannounced)", re.I)

# ... unless the same sentence is this release announcing the change ("pleased to announce the appointment of X
# as full-time COO, following his appointment as interim COO as announced on January 20").
_ANNOUNCING = re.compile(r"\b(?:pleased to announce|announces|today announced|is announcing|wishes to announce)\b", re.I)

# The named person stays on ("other than X and Y, who shall continue to act as directors, all directors will
# resign"): the change language in the sentence is about someone else.
_CONTINUES = r"[^.]{0,60}?\b(?:who (?:shall|will) (?:continue|remain)|continu(?:e|es|ing) to (?:act|serve)|will remain)"

# Biography: a change dated to a bare past year ("joined the Company in 2015 as CFO", "his retirement in 2022",
# "was appointed in 2019 to ...") is career history, not this release's news.
_BIO_YEAR = re.compile(r"^[^.]{0,60}?\b(?:in|since|from) (?:early |late |mid-?)?(?:19|20)\d\d\b(?! ?(?:annual|agm))", re.I)


# Change language whose object is not a position at the company:
# - a firm appointed or engaged ("has appointed Terrane Geoscience Inc and ...", "firm, ILF Group, appointed to
#   complete the study"): the appointee is an organisation, or the appointment is to carry out a piece of work;
# - an appointment to an outside body ("has been appointed to the Mining Advisory Council of ..."): the person's
#   position at the company does not change.  (Board committees are internal and still count.)
_ORG_OBJECT = re.compile(
    r"^[\s,]*(?:(?:the |a )?(?-i:[A-Z])[\w&'.-]*\s+){1,5}(?:Inc|Ltd|Limited|Corp|Corporation|LLC|LLP|SpA|S\.?A|GmbH|"
    r"Pty|Group|Consulting|Consultants|Engineers|Engineering|Geoscience|Geosciences|Partners|Associates)\b"
    r"|^\s*to (?:complete|conduct|undertake|carry out|perform|prepare|deliver|review|audit|design|build)\b")
_OUTSIDE_BODY = re.compile(
    r"^\s*to (?:the |a |an )?(?:[\w'&-]+ ){0,6}(?:council|commission|association|chamber|institute|society|"
    r"authority|agency|federation|foundation|ministry|panel|forum|tribunal|senate|parliament|cabinet)\b", re.I)


# ... or "appointed in succession to Y as President of the tribunal": the title is held at the outside body (round 6).
_OUTSIDE_TITLE = re.compile(
    r"\bas (?:the )?(?:[\w'-]+ ){0,3}(?:of|to|on) (?:the |a |an )?(?:[\w'&-]+ ){0,4}(?:tribunal|court|council|commission|"
    r"association|chamber|institute|society|authority|agency|federation|foundation|ministry|panel|forum|senate|parliament|"
    r"cabinet)\b", re.I)


def _news_change(pattern, w):
    """True when the window has change language that is not dated to a bare past year, not about a firm hired
    for a task and not an appointment to an outside body."""
    for m in pattern.finditer(w):
        after = w[m.end():m.end() + 90]
        if _BIO_YEAR.search(after[:70]) or _ORG_OBJECT.search(after) or _OUTSIDE_BODY.search(after) \
                or _OUTSIDE_TITLE.search(after):
            continue
        return True
    return False


# A board seat promised in deal terms: a lender's or investor's right to nominate or appoint a director ("will
# be entitled to nominate X for appointment and election as a director", "the right to appoint one director").
# That is a future possibility, not a change in this release.  (A director the company itself nominates for
# first election, or an investor's nominee who is actually appointed, still counts: guide 1.1.)
_PROPOSED = re.compile(r"\b(?:entitled|right|rights) to (?:nominate|appoint)\b", re.I)


# Someone hired for a task (investor relations, market making, consulting, audit) is not a position change.
# Round 6: a financial or project-financing advisor is a firm (or its principal) engaged for a mandate.
_TASK_HIRE = re.compile(r"\b(?:investor relations|financ(?:ial|ing) advis[eo]rs?|market[- ]mak\w+|marketing services|"
                        r"consulting services|consultants?|"
                        r"auditors?)\b", re.I)
# ... but "VP Investor Relations" / "Director of Investor Relations" is an officer position.
_IR_OFFICER = re.compile(r"\b(?:vp|vice[- ]president|director|manager|head|officer)[, ]+(?:of )?investor relations", re.I)


# A position word, needed when the reader gave the row no role.
_ROLE_WORD = re.compile(
    r"\b(?:chief|ceo|cfo|coo|president|directors?|chair(?:man|woman|person)?|officers?|executive|manager|"
    r"vice|vp|secretary|treasurer|advisors?|advisers?|geologist|controller|superintendent|head of|board)\b", re.I)


# Round 5: recaps in periodic and review releases.  Results releases, production reports, year-in-review and
# summary releases, annual or shareholder letters and "(corporate) update" releases list the period's events,
# appointments among them, usually announced in an earlier release.  There a change counts only when its
# sentence announces it now: an announcing verb in the present ("announces", "is pleased to announce", "would
# like to announce", "reports the appointment", "welcomes X as"), "today" or "effective immediately", the
# present perfect ("has resigned", "has been appointed", "has joined"), something under way ("is retiring") or
# still to come ("will step down", "will be appointed", "will succeed").  A change told in the simple past
# ("Appointed X to the Board in March 2024", "X joined the Company as COO", "The appointment of X as ...",
# "Announced the appointment of X") is the period's history.
_PERIODIC_HEAD = re.compile(
    r"\b(?:results?|quarter(?:ly)?|q[1-4]|(?:first|second|third|fourth) quarter|year[- ]end|full[- ]year|fiscal|"
    r"half[- ]year|interim report|annual (?:report|letter|review|update|investor|shareholder)|year[- ]in[- ]review|"
    r"year[- ]end review|review of|summary|letters?|highlights|production|financials?|"
    r"achievements|milestones|updates?|outlook)\b", re.I)
# The lead says the same: a letter to investors, or a look back at the year.
_PERIODIC_LEAD = re.compile(
    r"\b(?:dear (?:fellow )?(?:shareholders?|investors?|stakeholders?|unitholders?)|letter to (?:shareholders|investors)|"
    r"year[- ]in[- ]review|(?:milestones|achievements|highlights) (?:achieved |from )?(?:this |the )?(?:past )?year)\b", re.I)
_NEWS_NOW = re.compile(
    r"\b(?:announc(?:e|es|ing)\b|reports? the (?:appointment|resignation|retirement|departure)|today|"
    r"effective immediately|with immediate effect|"
    r"welcom(?:es|ing)\b|(?:pleased|delighted|happy|excited|proud) to (?:welcome|appoint|add|have)|"
    r"accepts? the resignation|"
    r"reports? that|(?:has|have) (?:also |(?!previously|formerly)\w+ly )?(?:been )?(?:appointed|named|elected|promoted|hired|engaged|added|resigned|retired|"
    r"stepped down|joined|tendered|decided to|agreed to|accepted|left|departed|assumed|taken on|taken over|become|"
    r"chosen|elected)|"
    r"(?:is|are) (?:retiring|stepping down|leaving|joining|resigning|departing|being appointed)|"
    r"to (?:retire|step down|resign) from\b|"
    r"will (?:also )?(?:be (?:appointed|named|joining|stepping down|retiring|leaving|replaced|succeeded)|retire|resign|"
    r"step down|join|succeed|replace|assume|become|serve|take over|take on|transition|leave|depart|not (?:seek|stand|be standing)))",
    re.I)


# Round 5: a person described by a past status ("former non-executive directors X and Y have exercised their
# options", "property vendor and retired geologist X noted", "X, the former CEO, ...") left that post before this
# release; the words "former" / "retired" (and the change words around them) are a description, not news.  Such a
# mention counts only when the sentence also announces a change now (see _NEWS_NOW: "X, the former CFO, has
# resigned as a director").
# "former CEO X", "retired geologist X": the status word with up to four title words, straight before the name
# (not "Y retired and X was appointed", where "retired" is Y's verb).
_STATUS_BEFORE = re.compile(
    r"\b(?:former|retired)(?: (?!(?:and|or|as|from|in|on|at|was|were|has|had|is|who|after|but|to|effective)\b)"
    r"[\w.,'-]+){0,4} $", re.I)
# "X, the former President", "X and Y (former directors of the Company)": set off by a comma or a bracket (not
# "X retired as a director", where "retired" is the verb).
_STATUS_AFTER = re.compile(r"^(?: and [^,.;()]{0,40}?)?\s*[,(]\s*(?:(?:the|a|an|our|its|his|her|both) )?(?:former|retired)\b",
                           re.I)


def _status_mention(name, w):
    k = w.find(name)
    if k < 0:
        return False
    return bool(_STATUS_BEFORE.search(w[max(0, k - 60):k]) or _STATUS_AFTER.match(w[k + len(name):k + len(name) + 70]))


# ... unless the release itself announces a management change: the headline names one ("Appoints CFO",
# "Corporate Update ~Appointment of Chief Operating Officer~", "Changes to Management") or the lead announces one
# ("is pleased to announce the appointment of a new director, the grant of stock options and ...").
_HEAD_CHANGE = re.compile(
    r"\b(?:appoint\w*|resign\w*|retire(?:s|ment)?|steps? down|stepping down|succession|leadership (?:change|transition)\w*|"
    r"management (?:change|appointment|team change)\w*|(?:board|executive|management|leadership|organi[sz]ational|personnel) changes|"
    r"changes to (?:the |its )?(?:board|management|executive|leadership)|names? (?:new )?(?:ceo|cfo|coo|president|chair\w*)|"
    r"new (?:ceo|cfo|coo|president|chair\w*|director|board member)|joins|"
    r"(?:addition|additions|adds?|added) [^.]{0,50}?\bto (?:the |its |our )?(?:board|management team))\b", re.I)
_LEAD_CHANGE = re.compile(
    r"\b(?:pleased to announce|announces|is announcing|today announced|reports)\b[^.]{0,60}?\b(?:the )?"
    r"(?:appointment|resignation|retirement|departure)s? of\b", re.I)


def _recap_release(headline, body):
    if _HEAD_CHANGE.search(headline or "") or _LEAD_CHANGE.search(body[:800]):
        return False
    return bool(_PERIODIC_HEAD.search(headline or "") or _PERIODIC_LEAD.search(body[:1500]))


# Round 6: a wire service's category or company page (many companies' headlines, each with a time stamp, "Items
# per page") is not one company's news release; a headline on it that announces an appointment is someone else's.
# Single releases carry at most two distinct clock times (a conference call in ET and PT); listing pages 16 or more.
_STAMP = re.compile(r"\b\d{1,2}:\d{2}(?: ?[AP]\.?M\.?)? ?(?:ET|EST|EDT|PT|PST|PDT|GMT|UTC|BST|CET)\b")
_LISTING = re.compile(r"\b(?:items per page|news listings)\b", re.I)


def _listing_page(body):
    head = body[:3000]
    return bool(_LISTING.search(head)) or len(set(_STAMP.findall(body))) >= 5


# Round 6: history told in the simple past.  In a release whose headline and lead are about something else, a
# change told only in the simple past ("X was appointed to the Board of Y", "resigned from both positions on
# December 22", "X joined the Company as", "the recent appointment of its new CFO", "newly appointed CEO X",
# "Following X's resignation, ...") is background: the change was news in an earlier release.  It still counts
# when the sentence announces it now (_NEWS_NOW), puts it in the future or the conditional, or ties it to this
# release's own deal (_NEXT: "In connection with the Acquisition, X was appointed", "concurrent with closing").
_PAST_TOLD = re.compile(
    r"\b(?:(?:was|were) (?:\w+ ){0,2}(?:appointed|named|elected|hired|promoted|engaged|added)|resigned|retired|joined|hired|"
    r"stepped down|departed|(?:recent(?:ly)?|newly)[ -](?:appoint\w*|named|hired|elected|added)|announced the (?:appointment|resignation|"
    r"retirement|departure)|following (?:the |his |her |their |(?-i:[A-Z])[\w'-]* )?(?-i:[A-Z])?[\w'-]*'s (?:resignation|retirement|departure))\b", re.I)
_NEXT = re.compile(r"\b(?:would|expected to|to (?:join|be appointed|become|serve|replace|succeed)|"
                   r"(?:in connection with|concurrent(?:ly)? with|upon|on|at|following|after|prior to|as part of) (?:the |this )?"
                   r"(?:[\w'-]+ ){0,3}?(?:closing|completion|acquisition|transaction|arrangement|amalgamation|merger|spin-?out|"
                   r"listing|financing|offering|private placement|business combination|qualifying transaction|agreement)s?)\b", re.I)
# Round 6: a meeting notice ("Mails AGM Materials - Encourages Shareholders to Vote", "Files Circular") is not a
# meeting-results release, unless the headline also reports results or an election.
_MEETING_NOTICE = re.compile(r"\b(?:mails?|mailing|mailed|circular|proxy|notice of|encourag\w+|urg\w+|remind\w*|files?)\b", re.I)
_MEETING_DONE = re.compile(r"\b(?:results?|elected|election of directors|re-?elect\w*|approved|approves)\b", re.I)


def _rows(out):
    if isinstance(out, dict):
        return out.get("changes") or []
    return out or []


def admit(headline, text, categories, out):
    """-> (bool, short_reason).  `categories` is not used: which other tags a release carries says little about
    whether a management change is its own news (they appear under Financings, M&A, Drill Results ...)."""
    rows = _rows(out)
    if not rows:
        return False, "no rows"
    # Junk or empty "person" (table headings, place and deal names, unnamed roles): never enough on its own.
    people = [(r, n) for r, n in ((r, _clean_name(r.get("person"))) for r in rows) if _is_person(n)]
    if not people:
        return False, "no named person"
    body = _norm(text or "")
    words = _lower_words(body)
    people = [(r, n) for r, n in people if not _common_phrase(n, body, words)]
    if not people:
        return False, "name is a common phrase"
    if _listing_page(body):
        return False, "wire listing page"
    # Shareholder-meeting results (not a meeting notice or a release that merely mentions the meeting date).
    meeting = bool(_MEETING_HEADLINE.search(headline or "") and _MEETING_OUTCOME.search(headline or "")
                   and not (_MEETING_NOTICE.search(headline or "") and not _MEETING_DONE.search(headline or "")))
    # A release about something else: the headline names no management change and the lead announces none.
    other_news = not meeting and not (_HEAD_CHANGE.search(headline or "") or _LEAD_CHANGE.search(body[:800]))
    # Periodic or review release (round 5): a change must be announced now, not told as the period's history.
    recap = not meeting and _recap_release(headline, body)
    sents = _SPLIT.split(_norm(headline or "") + "\n\n" + body)
    upper_head = _norm(headline or "").title() if (headline or "").isupper() else ""
    refused = []                                       # why windows with change language were refused
    for r, name in people:
        last = name.split()[-1]
        keys = {name, last} if len(last) >= 3 else {name}
        wins = [_window(upper_head, k) for k in keys if upper_head and k in upper_head][:1]   # all-capitals headline
        wins += _windows(sents, keys)
        # Recap: once the release says this person's change was announced before (shareholder letters,
        # quarterly/annual results), later mentions of the person ("my decision to join") are not new news.
        if any(_RECAP.search(w) and not _ANNOUNCING.search(w) for w in wins):
            refused.append("announced before")
            continue
        for w in wins:
            if not _news_change(_MEETING_STRONG if meeting else _CHANGE, w):
                continue                               # no change language about this person here
            if re.search(re.escape(name) + _CONTINUES, w):
                refused.append("continues")            # the named person continues; the change is others'
            elif _TASK_HIRE.search(w) and not _IR_OFFICER.search(w):
                refused.append("task hire")            # hired for a task, not a position
            elif _PROPOSED.search(w):
                refused.append("proposed")             # a nomination right in deal terms, not a change
            elif not r.get("role") and not _ROLE_WORD.search(w):
                refused.append("no role")              # role-less row with no position in sight
            elif (recap or _status_mention(name, w)) and not _NEWS_NOW.search(w):
                refused.append("recap" if recap else "past status")   # periodic recap, or a former/retired person
            elif other_news and _PAST_TOLD.search(w) and not _NEWS_NOW.search(w) and not _NEXT.search(w):
                refused.append("told as history")      # history told in the simple past
            else:
                return True, "meeting: named change" if meeting else "named change"
    return False, "no named change" + (" (" + ", ".join(sorted(set(refused))) + ")" if refused else "")
