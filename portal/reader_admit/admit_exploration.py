"""Outside-tag admission rule for the Exploration Programs reader (miningnewsterminal.com).

admit(headline, text, categories, out) -> (bool, short_reason)

Called only for releases that do NOT carry the "Exploration Programs" tag but where the reader found rows.
The rule admits a release only when (a) the release is about the project the rows are on and its lead talks
about field work, and (b) the reader's rows look well-formed (a real project name, no combined program split
into several rows or listed twice, no fact-less rows outside program headlines). Everything else stays off the page. Standard library only, no I/O.

Round 2 (2026-09-30, after a fresh 60-release check of round-1 admissions) adds rules 8-12: every row size must be
stated in the release, the program type must be named in it, study releases are refused, a row whose facts sit
under another landholding's name is refused, and a project name missing its first word is refused.
Round 1 is kept unchanged in admit_exploration_v1.py.
"""
import re

# Words that mark a field program in the headline or lead paragraphs.
_PROGRAM_WORDS = re.compile(
    r"\b(?:drill\w*|holes?|metres|meters|surveys?|sampling|trench\w*|mapping|prospecting|geophysic\w*|"
    r"field\s+(?:program\w*|work|season)|exploration\s+(?:program\w*|work|campaign|update)|campaign)\b",
    re.I)

# Nouns a company uses for its own landholding: "<Name> (Gold) Project", "<Name> Property", "<Name> claims".
_HOLDING = r"(?:project|property|properties|claims?|claim\s+block|licen[cs]es?|concessions?|tenements?)"

# Words that are never a project name on their own (commodities, regions, adjectives).
_NOT_A_NAME = {
    "gold", "silver", "copper", "nickel", "cobalt", "zinc", "lead", "lithium", "uranium", "graphite", "vanadium",
    "tungsten", "antimony", "platinum", "palladium", "iron", "manganese", "tin", "molybdenum", "rare", "earth",
    "earths", "ree", "pgm", "pge", "potash", "phosphate", "helium", "hydrogen", "critical", "minerals", "metals",
    "battery", "polymetallic", "mongolian", "canadian", "quebec", "ontario", "nevada", "yukon", "mexican",
    "peruvian", "american", "african", "australian",
}

_LEAD_CHARS = 1000        # "lead paragraphs": headline plus the first ~1,000 characters of the body
_OWNED_LEAD_CHARS = 800   # where "its X Project" must appear for a project not named in the headline


def _named_in(project, s):
    return bool(re.search(r"(?<!\w)" + re.escape(project) + r"(?!\w)", s, re.I))


def _named_as_holding(project, s):
    """The text calls the name a landholding: '<name> [up to 4 words] Project|Property|Claims|Licence', where
    <name> is the leading one or two words of the reader's project ("Clay Howells" for "Clay Howells Rare Earth
    Element", "Aurex" for "Aurex-McQuesten"), so descriptive tails and spelling of the tail do not matter."""
    words = re.findall(r"[^\s\-]+", project or "")
    words = [w for w in words if w.lower().strip("().,") not in ("the",)]
    if not words:
        return False
    core = words[:2] if len(words) > 1 and words[1].lower() not in _NOT_A_NAME and \
        not re.match(_HOLDING + r"$", words[1], re.I) else words[:1]
    name = r"[\s\-]+".join(re.escape(w) for w in core)
    sep = r"[\s\-(),\"“”]+"
    return bool(re.search(r"(?<!\w)" + name + r"(?:" + sep + r"[\w\-&’'.]+){0,4}?" + sep + _HOLDING + r"\b", s, re.I))


def _owned_in_lead(project, lead_body):
    """'its / our / the Company's / 100%-owned / wholly-owned [up to 3 words] <project>' in the lead."""
    return bool(re.search(r"(?:\bits|\bour|company[’']s|\b100\s?%[- ]owned|wholly[- ]owned)\s+"
                          r"(?:[\w\-’'.]+\s+){0,3}?" + re.escape(project) + r"(?!\w)", lead_body, re.I))


def _bad_name(project):
    words = re.findall(r"[A-Za-z]+", project or "")
    if not words:
        return "no project"
    if all(w.lower() in _NOT_A_NAME for w in words):
        return "project is a commodity/region word"
    if re.search(r"[’']s\s+\w", project):
        return "project is another owner's (possessive)"
    return None


def _without_headline(headline, text):
    """Body text with the release's own copy of the headline removed (many bodies start with it)."""
    t = re.sub(r"\s+", " ", text)
    h = re.sub(r"\s+", " ", headline).strip()
    if h:
        k = t.lower().find(h.lower())
        if k >= 0:
            t = t[:k] + " " + t[k + len(h):]
    return t


def _split_program(rows):
    """Two rows of different program types on the same project and owner that are the same program: same
    season, or the same planned/started/underway status. The guide makes a combined program ONE row (drilling
    if drilling is part of it, otherwise ground), so the reader has split it. Two completed programs without
    a shared season are left alone: those are usually genuinely separate past programs."""
    for a in rows:
        for b in rows:
            if a is b or a.get("program_type") == b.get("program_type") or a.get("project") != b.get("project"):
                continue
            if bool(a.get("historical")) != bool(b.get("historical")):
                continue
            same_season = bool(a.get("season")) and a.get("season") == b.get("season")
            same_live_status = a.get("status") == b.get("status") and a.get("status") != "completed"
            if same_season or same_live_status:
                return True
    return False


def _has_facts(row):
    return any(row.get(k) not in (None, "") for k in
               ("metres", "holes", "line_km", "season", "budget", "contractor", "rigs"))


# ---------------------------------------------------------------------------------------------------------------
# Round 2 helpers (added after the fresh 60-release check)
# ---------------------------------------------------------------------------------------------------------------

_NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
              10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen",
              17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty", 30: "thirty", 40: "forty", 50: "fifty"}


def _digits_pattern(s):
    """'12200' -> '12[, .]?200': the integer part with optional thousands separators."""
    out = ""
    for k, ch in enumerate(s):
        if k and (len(s) - k) % 3 == 0:
            out += r"[,\s  .']?"
        out += ch
    return out


def _number_positions(value, text):
    """Where a row's number (metres, holes, line-km) is written in the release: digits with or without thousands
    separators, a decimal with point or comma, a spelled-out small number, or '5k' / '5 thousand'."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return []
    pats = []
    iv = int(round(v))
    if abs(v - iv) < 1e-9:
        pats.append(r"(?<![\d.,])" + _digits_pattern(str(iv)) + r"(?:[.,]0+)?(?!\d)")
        if iv in _NUM_WORDS:
            pats.append(r"\b" + _NUM_WORDS[iv] + r"\b")
        if iv >= 1000 and iv % 100 == 0:
            pats.append(r"(?<![\d.])" + re.escape("%g" % (iv / 1000)) + r"\s?(?:k\b|thousand)")
    else:
        ip, fp = ("%.3f" % v).rstrip("0").split(".")
        pats.append(r"(?<!\d)" + _digits_pattern(ip) + r"[.,]" + fp)
    pos = []
    for p in pats:
        pos += [m.start() for m in re.finditer(p, text, re.I)]
    return sorted(pos)


def _feet_match(metres, text):
    """The release gives the length in feet and the reader converted it (within 2%)."""
    for m in re.finditer(r"(\d[\d,]*(?:\.\d+)?)\s*(?:feet|ft\b|foot)", text, re.I):
        try:
            f = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if f and abs(f * 0.3048 - metres) / metres < 0.02:
            return True
    return False


def _ungrounded_size(row, text):
    """A metres / holes / line-km figure on the row that the release never states."""
    for k in ("metres", "holes", "line_km"):
        v = row.get(k)
        if v in (None, "", 0):
            continue
        if _number_positions(v, text):
            continue
        if k == "metres" and _feet_match(float(v), text):
            continue
        return k
    return None


# Words the release must use somewhere for the reader's program type to be real.
_TYPE_WORDS = {
    "drilling": re.compile(r"\b(?:drill\w*|bore\s?holes?|holes?)\b", re.I),
    "geophysics": re.compile(r"\b(?:geophysic\w*|surveys?|induced\s+polari[sz]ation|resistivity|magnetic\w*|"
                             r"magnetometer|electromagnetic|airborne|gravity|radiometric|spectrometr\w*|lidar|"
                             r"seismic|flown|heli\w*)\b|(?-i:\b(?:IP|EM|VTEM|ZTEM)\b)", re.I),
    "ground": re.compile(r"\b(?:sampl\w*|soils?|till|rock|grab|chip|channel\w*|trench\w*|mapping|mapped|"
                         r"prospect(?:ing|ed|ors?)|reconnaissance|geolog\w*\s+(?:work|program\w*|crew|team)|"
                         r"field\s+(?:program\w*|work|season|crew|team)|exploration\s+(?:program\w*|work|campaign))\b",
                         re.I),
}

# Headlines of study releases: a PEA / PFS / DFS / feasibility / economic or scoping study.
_STUDY_HEADLINE = re.compile(r"\b(?:PFS|PEA|DFS|pre-?feasibility|feasibility|preliminary\s+economic|"
                             r"economic\s+(?:study|assessment|analysis)|scoping\s+study)\b", re.I)

# A named landholding elsewhere in the release: "<Name> [commodity] Project|Property|Claims|Concession|Licence".
_COMMODITY_WORD = (r"(?:Gold|Silver|Copper|Nickel|Zinc|Lithium|Uranium|Cobalt|Tin|Tungsten|Vanadium|Graphite|"
                   r"Rare\s+Earths?|REE|Polymetallic|Base\s+Metals?|[A-Z][a-z]+-[A-Z][a-z]+)")
_HOLDING_NAME = re.compile(r"((?:[A-Z][\w’'\-]*\s+){1,3})(?:" + _COMMODITY_WORD + r"\s+){0,2}"
                           r"(?:Project|Property|Claims|Concession|Licence|License)\b")
_NOT_NAME_WORDS = {"the", "its", "our", "their", "and", "of", "a", "an", "this", "that", "project", "property",
                   "exploration", "mining", "resources", "minerals", "metals", "company", "corp", "inc", "ltd",
                   "announces", "received", "receives", "highlights", "new", "flagship", "key", "other", "both",
                   "each", "all", "said", "gold", "silver", "copper", "critical", "battery"}


def _other_holdings(text, row_projects):
    """Names of landholdings in the release that are not any of the reader's row projects."""
    mine = set()
    for p in row_projects:
        mine.update(w.lower() for w in re.findall(r"[\w’']+", p or ""))
    names = set()
    for m in _HOLDING_NAME.finditer(text):
        words = [w for w in m.group(1).split() if w.lower().strip(".,") not in _NOT_NAME_WORDS]
        if not words:
            continue
        name = words[-1].strip(".,")
        parts = [w.lower() for w in re.split(r"[-\s]+", name) if w]
        if len(name) < 3 or name.lower() in mine or name.isdigit() or name.lower() in ("mine", "mines") or \
                all(w in _NOT_A_NAME for w in parts):
            continue
        names.add(name)
    return names


def _filed_under_other_project(row, text, row_projects):
    """Every place the release states the row's facts (its metres, holes, line-km or the named previous operator)
    is closer to another landholding's name than to the row's own project: the reader has filed that program under
    the wrong one of several projects."""
    p = (row.get("project") or "").strip()
    if not p:
        return False
    key = re.findall(r"[\w’']+", p)[0]
    others = _other_holdings(text, row_projects)
    if not others:
        return False
    pos = []
    for k in ("metres", "holes", "line_km"):
        if row.get(k):
            pos += _number_positions(row[k], text)
    op = str(row.get("operator") or "")
    if op and not op.lower().startswith("previous"):
        first = re.findall(r"[\w’']+", op)
        if first and len(first[0]) >= 4:
            pos += [m.start() for m in re.finditer(r"(?<!\w)" + re.escape(first[0]) + r"(?!\w)", text)]
    if not pos:
        return False

    def last_mention(name, upto):
        found = [m.start() for m in re.finditer(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text[:upto], re.I)]
        return found[-1] if found else -1

    for q in pos:
        if last_mention(key, q) >= max(last_mention(o, q) for o in others):
            return False
    return True


# Words that may stand directly before a property name without being part of it.
_BEFORE_NAME_OK = {"the", "its", "our", "their", "a", "an", "and", "of", "at", "on", "in", "to", "for", "from", "with",
                   "by", "as", "this", "that", "new", "newly", "flagship", "owned", "100%-owned", "wholly-owned",
                   "greater", "broader", "historic", "historical", "former", "past", "key", "core", "advanced",
                   "district", "regional", "company", "company’s", "company's"}
_HOLDING_AFTER = (r"(?:[\s\-]+(?:" + _COMMODITY_WORD + r"|Phosphate|Iron|Potash|Diamond|Diamonds))*"
                  r"\s+(?:Project|Property|Claims|Deposit|Mine)\b")
_HOLDING_AFTER_RX = re.compile(_HOLDING_AFTER, re.I)


def _issuer_words(headline, text):
    """Words of the issuer's name: the first capitalised words of the headline and the name before the
    '("Company")' / '(TSX...' definition in the lead."""
    words = set(w.lower() for w in re.findall(r"[A-Z][\w\-]+", headline)[:3])
    m = re.search(r"([A-Z][\w.&\- ]{2,60}?)\s*\((?:the\s+)?[“\"]|([A-Z][\w.&\- ]{2,60}?)\s*\((?:TSX|CSE|NYSE|ASX|NASDAQ)",
                  text[:1500])
    if m:
        words.update(w.lower() for w in (m.group(1) or m.group(2)).split())
    return words


def _name_missing_first_word(project, body, issuer):
    """Every time the release names the property ('<X> <project> [commodity] Project/Property/Deposit/Mine'), a
    further capitalised word X stands in front of the reader's name, and X is not an article, a possessive or the
    issuer's name: the reader has dropped the first word of the name ('Hill' for 'Silver Hill', 'Standard' for
    'Gold Standard'), usually because it looks like a commodity."""
    if not project:
        return False
    occ = [m for m in re.finditer(r"(?<![\w\-’'])" + re.escape(project), body, re.I)
           if _HOLDING_AFTER_RX.match(body, m.end())]
    if not occ:
        return False
    for m in occ:
        w = re.findall(r"([\w’'%\-]+)\s+$", body[max(0, m.start() - 40):m.start()])
        if not w:
            return False
        w = w[0]
        if not w[:1].isupper() or w.lower() in _BEFORE_NAME_OK or w.endswith(("’s", "'s")) or w.lower() in issuer:
            return False
    return True


def admit(headline, text, categories, out):
    rows = list((out or {}).get("rows") or []) if isinstance(out, dict) else list(out or [])
    if not rows:
        return False, "no rows"
    headline = headline or ""
    text = text or ""
    body = _without_headline(headline, text)
    lead = headline + "\n" + text[:_LEAD_CHARS]

    # Rule 1 -- release about something else (financing, AGM, marketing, M&A, resource, results...) whose lead
    # never mentions field work: its program rows come from background paragraphs. Completed programs there
    # are still rows (the guide records the issuer's and previous owners' past programs whenever mentioned),
    # but a planned/started/underway program that the lead does not mention is a passing intention: reject.
    if not _PROGRAM_WORDS.search(lead) and any(r.get("status") != "completed" for r in rows):
        return False, "live program not in lead"

    for r in rows:
        p = (r.get("project") or "").strip()
        # Rule 2 -- the reader's project must be a real project name (not a commodity, region or
        # "Other Co's X" possessive, which marks someone else's project).
        why = _bad_name(p)
        if why:
            return False, why
        # Rule 3 -- the release must be about the issuer's own project: named in the headline, or introduced in
        # the lead as the company's own ("its X Project", "the Company's 100%-owned X"). Background mentions
        # of side projects, other companies' projects (a neighbour, a royalty operator, a promoter's other
        # client) and zones or deposits used instead of the property fail here.
        if not (_named_in(p, headline) or _owned_in_lead(p, body[:_OWNED_LEAD_CHARS])):
            return False, "row project not the release's own project"
        # Rule 4 -- the body (not just the headline) calls the name a project/property/claims/licence. Catches
        # headline fragments taken as names ("Include", "Well") and zone/deposit names used for the property.
        if not _named_as_holding(p, body):
            return False, "project not named as a property"

    # Rule 5 -- the same metres or hole count on two rows: the reader has listed one program twice (e.g. once
    # as "started" and once as "completed", or under a zone name and under the property name).
    metres = [r.get("metres") for r in rows if r.get("metres")]
    holes = [r.get("holes") for r in rows if r.get("holes")]
    if len(metres) != len(set(metres)) or len(holes) != len(set(holes)):
        return False, "same program listed twice"

    # Rule 6 -- rows of different types for the same project and season/live status: one combined program
    # that the reader has split (the guide wants one row).
    if _split_program(rows):
        return False, "combined program split into rows"

    # Rule 7 -- rows with no concrete fact (no metres, holes, line-km, season, budget, contractor, rigs) are
    # only trusted when the headline itself is about the field program; otherwise they are usually an
    # agreement's work commitment or a passing mention.
    if not all(_has_facts(r) for r in rows) and not _PROGRAM_WORDS.search(headline):
        return False, "fact-less row, headline not about a program"

    # ---- Round 2 rules -------------------------------------------------------------------------------------
    # Rule 8 -- every size on a row (metres, holes, line-km) must be written in the release (digits, words,
    # "5k", or feet the reader converted). A size the release never states was supplied by the reader from
    # elsewhere or computed; on short corporate releases (an option amendment, an appointment, an ESG
    # agreement) it is a whole invented program.
    for r in rows:
        k = _ungrounded_size(r, text)
        if k:
            return False, "row %s not stated in release" % k

    # Rule 9 -- the release must use the vocabulary of the row's program type somewhere (drilling: drill/holes;
    # geophysics: survey/IP/magnetic/EM/airborne...; ground: sampling/mapping/trenching/prospecting...).
    # Otherwise the reader has invented the type from a passing reference.
    for r in rows:
        rx = _TYPE_WORDS.get(r.get("program_type"))
        if rx is not None and not rx.search(text):
            return False, "program type not in release"

    # Rule 10 -- study releases (PEA, PFS, feasibility, economic study) whose headline is not about field work:
    # the drilling they mention is the resource database behind the study or its infill history, which the guide
    # excludes ("resource and study work"), and the reader splits it by year or files it under the wrong permit.
    if _STUDY_HEADLINE.search(headline) and not _PROGRAM_WORDS.search(headline):
        return False, "study release"

    # Rule 11 -- a release covering several landholdings (land deals, year reviews, district updates): a row
    # whose facts are stated under another landholding's name is filed under the wrong project.
    projects = [r.get("project") for r in rows]
    for r in rows:
        if _filed_under_other_project(r, text, projects):
            return False, "row facts stated under another project"

    # Rule 12 -- the reader's project name is missing the first word of the property's name as the release writes
    # it (the reader drops a leading word that looks like a commodity or adjective). The page would show a wrong
    # project name, and a truncated name also stops rules 3-4 from recognising another owner's property.
    issuer = _issuer_words(headline, text)
    for r in rows:
        if _name_missing_first_word((r.get("project") or "").strip(), body, issuer):
            return False, "project name missing its first word"

    return True, "program news on headline project"
