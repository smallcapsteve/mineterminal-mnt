"""AUDIT1110_TIDYREL (2026-11-10, Justin's popups "Repeated headline + openers", "Wire boilerplate"; v2 the same day:
"Click Image" text, web-address letterhead, empty table columns).

Display only: the stored release is never changed. One call, tidy(html, headline), used where a release body is
shown (MNT's release page and the article feed MTP's pop-up reads).

Before the first real paragraph it drops: the headline when the body repeats it (also when split over lines),
"For Immediate Release" / "News Release" lines, the SEC filing header ("EX-99.1 ... EXHIBIT 99.1"), a lone web
address, and a letterhead block (street address, suite, city and postcode, phone; exchange-symbol lines only when an
address is there too). Anywhere it drops TheNewswire's copyright line and "View original content ..."; a
"SOURCE: ..." line only among the last four lines. A line that holds a picture is never dropped.
v2: the words "Click Image To View Full Size" go and the picture stays; a table column that is empty in every row
is removed (merged header cells shrink with it). A table is left alone if it holds another table, has cells merged
down rows, has rows of different widths, or if any text would change.
v3 (RELFMT3400_B, 2026-11-11, Justin: "do all A, B, & C. Start with B"), still display only:
  * an opening line that is only notice words, a release number, a date, a city, exchange symbols, a web address or
    address and phone details ("NEWS RELEASE: 21-10  NOVEMBER 01, 2021"; a letterhead on one line);
  * a short opening "NOT FOR DISTRIBUTION TO U.S. NEWSWIRE SERVICES ..." line (not a paragraph that goes on to say more);
  * "FOR IMMEDIATE RELEASE" / "NEWS RELEASE" / "PRESS RELEASE" at the very start of an opening paragraph (the words
    only); the headline when an opening line starts with it and goes straight on to the dateline ("... PROJECT Toronto,
    Ontario - December 2, 2021 - ..."), the headline only. A line that merely starts with the stored headline and
    carries on as the same sentence is left alone: the stored headline is often a shortened one;
  * Newsfile's "To view the source version of this press release, please visit ..." sentence, anywhere;
  * a web address over 60 characters is shown as "site.com/..." and stays a link to the full address.
"""
import html as _html
import re

_LEAF = re.compile(r"(?is)<(p|div|h[1-6]|center)\b[^>]*>((?:(?!</?(?:p|div|h[1-6]|center|table|tr|td|th|ul|ol|li|blockquote)\b).)*?)</\1\s*>")
_TAG = re.compile(r"(?s)<[^>]+>")
_OPENER = re.compile(r"(?i)^(?:for immediate release|(?:news|press|media) release)\W*$|^EX-\d+(?:\.\d+)?\b.{0,110}$|^exhibit \d+(?:\.\d+)?\W*$")
_ADDR = re.compile(
    r"(?i)^\W*(?:#?\d{1,6}(?:\s*-\s*\d{1,6})? [\w.' -]{2,40}\b(?:street|avenue|ave|road|blvd|boulevard|highway|hwy|parkway)\.?(?:,? (?:suite|unit|floor) \w+)?\W*$"
    r"|#?(?!(?:19|20)\d\d )\d{1,6}(?:\s*-\s*\d{1,6})? [\w.' -]{2,40}\b(?:st|rd|drive|dr|place|way|crescent|lane|court)\.?(?:,? (?:suite|unit|floor) \w+)?\W*$"
    r"|suite \d+\W*$|p\.? ?o\.? box \d+.{0,40}$|(?:phone|tel|telephone|fax|toll[ -]free)\s*[:.].{0,60}$"
    r"|[A-Z][\w.' ]{1,30},\s*[A-Z]{2}\.?,? +\d{5}(?:-\d{4})?\W*$"
    r"|[\w.' ]{2,30},\s*[\w.' ]{2,30},? +[A-Z]\d[A-Z] ?\d[A-Z]\d\W*$)")
_SYM = re.compile(r"(?i)^(?:(?:trading symbols?\W*)?(?:tsx(?:[ .-]?v| venture)?|nyse(?: american)?|nasdaq|cse|otc(?:q[xb])?|fse|fra|asx)\s*:\s*[A-Z0-9.]{1,7}\W*)+$")
_WEB = re.compile(r"(?i)^(?:www\.|https?://)[^\s]{4,70}$")
_BOILER = re.compile(r"(?i)^(?:copyright \(c\) \d{4} thenewswire\b.{0,60}|click image to view full size\W*|view original content.{0,200})$")
_SOURCE = re.compile(r"^SOURCE:? .{2,90}$")
_HINT = re.compile(r"(?i)thenewswire|click image|view original content|SOURCE")
_CLICK = re.compile(r"(?i)(?:<br\s*/?>\s*)?click image to view full size")
_TBL = re.compile(r"(?is)<table\b[^>]*>.*?</table>")
_TR = re.compile(r"(?is)(<tr\b[^>]*>)(.*?)(</tr\s*>)")
_CELL = re.compile(r"(?is)<(t[dh])\b([^>]*)>(.*?)</\1\s*>")
_COLSPAN = re.compile(r"(?i)\s*\bcolspan\s*=\s*[\"']?(\d+)[\"']?")
_ROWSPAN = re.compile(r"(?i)\browspan\s*=\s*[\"']?(?!1\b)\d")

# ---- v3 (RELFMT3400_B) ----
_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_F_NOTICE = re.compile(r"(?i)\bfor immediate release\b|\b(?:news|press|media) release\b")
_FRAGS = [   # (counts as an address/phone signal, pattern) - removed in this order
    (1, re.compile(r"(?i)(?:\bweb(?:site)?\s*:?\s*)?(?:https?://|www\.)\S+|\b[\w.-]+@[\w-]+\.[\w.]+")),
    (0, re.compile(r"(?i)\b" + _MON + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+(?:19|20)\d\d\b|\b\d{1,2}(?:st|nd|rd|th)?\s+" + _MON + r"\.?,?\s+(?:19|20)\d\d\b")),
    (1, re.compile(r"(?i)\b(?:tel(?:ephone)?|phone|ph|fax|toll[ -]?free)\b\.?\s*:?\s*\+?[\d(][\d\s().\-]{6,18}\d|\(\d{3}\)\s*\d{3}[\s.\-]\d{4}\b|\b(?:1[\s.\-])?\d{3}[\s.\-]\d{3}[\s.\-]\d{4}\b")),
    (1, re.compile(r"(?i)\b[ABCEGHJ-NPRSTVXY]\d[A-Z][ -]?\d[A-Z]\d\b")),
    (1, re.compile(r"(?i)\b(?:suite|unit|ste\.?|floor|p\.?\s?o\.? box)\s*#?\s*\d+\w?\b|#\s*\d+\b")),
    (1, re.compile(r"(?i)\b\d{1,6}(?:\s*[-–]\s*\d{1,6})?\s+(?:[\w.']+\s+){0,4}(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|way|place|highway|hwy|crescent|court|lane)\b\.?")),
    (0, re.compile(r"(?i)(?:trading symbols?\s*:?\s*)?\(?\b(?:tsx[ .-]?v(?:enture)?(?: exchange)?|tsxv|tsx(?: venture(?: exchange)?)?|nyse(?:[ -]?(?:american|mkt|arca))?|nasdaq|cse|cnsx|otc[ -]?(?:qb|qx|bb|pink)?|fse|fra(?:nkfurt)?|lse|aim|asx|bvl|omx)\s*:\s*[A-Z0-9][A-Z0-9.]{0,7}\)?")),
    (0, re.compile(r"(?i)(?:\b(?:no\.?|number|nr\.?)\s*|#\s*)?\b\d{2,4}\s*[-–]\s*\d{1,3}\b")),
    (0, re.compile(r"(?i)\b(?:vancouver|toronto|calgary|montr[eé]al|ottawa|halifax|winnipeg|saskatoon|regina|kelowna|victoria|edmonton|qu[eé]bec(?: city)?|longueuil|val-d'or|rouyn-noranda|thunder bay|sudbury|timmins|kirkland lake|st\. john's|whitehorse|yellowknife|surrey|burnaby|north vancouver|west vancouver|mississauga|oakville|denver|reno|spokane|british columbia|alberta|ontario|manitoba|saskatchewan|nova scotia|new brunswick|newfoundland(?: and labrador)?|yukon|canada|b\.?c\.?|ab|on|qc|sk|mb|ns|nb|nl|yt)\b\.?")),
]
_NFD = re.compile(r"(?is)^\W*(?:this (?:news|press) release is )?not (?:intended )?for (?:release|distribution|dissemination|publication)\b.{0,260}\b(?:united states|u\.s\.a\.|u\.s\.|usa|u\.s|us)(?![a-z])")
_NOTICE_PREFIX = re.compile(r"^((?:\s|<[^>]+>)*)(?:FOR IMMEDIATE RELEASE|For Immediate Release|For immediate release|NEWS RELEASE|PRESS RELEASE|MEDIA RELEASE)\b(?:\s|&nbsp;|[.:,;–—\-])*(?=(?:<[^>]+>|\s)*[A-Z0-9“\"(])")
_NEWSFILE = re.compile(r"(?is)\s*to view the source version of this (?:press|news) release,? please visit:?\s*(?:<a\b[^>]*>)?\s*https?://(?:www\.)?newsfilecorp\.com/release/\d+[^\s<]*\s*(?:</a>)?\.?")
_EMPTYP = re.compile(r"(?i)<p\b[^>]*>(?:\s|&nbsp;)*</p>\s*")
_LONGURL = re.compile(r"https?://[^\s<>\"']{57,}")
_SPLIT = re.compile(r"(<[^>]+>)")
_DATELINE = re.compile(r"^[A-Z][\w.'é-]+(?: [A-Z][\w.'é-]+){0,3},\s*[A-Z][\w.é]+\.?(?: [A-Z][\w.é]+){0,2},?\s*(?:[–—\-:(,]|" + _MON + r"\b)")


def _furniture(t):
    """(has a notice word, address/phone signals, words left over, letters left over) once the furniture pieces
    are taken out of a line."""
    s = _F_NOTICE.sub(" ", t)
    notice = s != t
    sig = 0
    for counts, rx in _FRAGS:
        s2 = rx.sub(" ", s)
        if s2 != s and counts:
            sig += 1
        s = s2
    rem = re.sub(r"[^A-Za-z0-9]+", " ", s).split()
    return notice, sig, rem, sum(len(w) for w in rem)


def _is_furniture(t):
    if len(t) > 260:
        return False
    notice, sig, rem, n = _furniture(t)
    if (notice or sig >= 2) and n <= 4:
        return True
    return sig >= 3 and len(rem) <= 6 and n <= 45        # a one-line letterhead: company name + address + phone + web


def _is_nfd(t):
    """A short 'not for distribution to U.S. newswire services ...' line with nothing after it but furniture."""
    if len(t) > 330:
        return False
    m = None
    for m in re.finditer(r"(?i)\b(?:united states|u\.s\.a\.|u\.s\.|usa|u\.s|us)(?![a-z])", t):
        pass
    if not m or not _NFD.match(t):
        return False
    rest = re.sub(r"(?i)^\W*(?:of america|news\s?wire services?|wire services?)?\W*", "", t[m.end():])
    return not rest or (_furniture(rest)[3] <= 4)


def _strip_headline(inner, hn):
    """inner html of a line that starts with the headline and carries on -> inner without the headline, else None."""
    acc, i, n = "", 0, len(inner)
    while i < n and len(acc) < len(hn):
        if inner[i] == "<":
            j = inner.find(">", i)
            if j < 0:
                return None
            i = j + 1
            continue
        if inner[i] == "&":
            j = inner.find(";", i, i + 9)
            ch = _html.unescape(inner[i:j + 1]) if j > 0 else "&"
            i = (j + 1) if j > 0 else i + 1
        else:
            ch = inner[i]
            i += 1
        acc += _norm(ch)
        if not hn.startswith(acc):
            return None
    if acc != hn:
        return None
    rest = inner[i:]
    if len(_norm(_text(rest))) < 12:
        return None
    lead = "".join(re.findall(r"<[^/][^>]*>", inner[:i]))           # tags opened before the cut stay open
    closed = re.findall(r"</(\w+)", inner[:i])
    for c in closed:
        lead = re.sub(r"<%s\b[^>]*>" % c, "", lead, count=1)
    return lead + re.sub(r"^(?:\s|&nbsp;|[;:,.–—\-])+", "", rest)


def _pre(h, headline=""):
    """Edits inside the opening lines: notice words at the start of a paragraph, a headline that a line starts with."""
    table = re.search(r"(?i)<table\b", h)
    head_end = min(table.start() if table else len(h), 9000)
    hn = _norm(headline)
    out, n = [], 0
    for m in _LEAF.finditer(h, 0, head_end):
        inner = m.group(2)
        if "<img" in inner.lower() or not _text(inner):
            continue
        n += 1
        if n > 14:
            break
        t = _text(inner)
        new = None
        pm = _NOTICE_PREFIX.match(inner)
        if pm and not _is_furniture(t) and len(_norm(_text(inner[pm.end():]))) >= 12:
            new = pm.group(1) + inner[pm.end():]
        cur = new if new is not None else inner
        if hn and len(hn) >= 20 and _norm(_text(cur)).startswith(hn) and _norm(_text(cur)) != hn:
            cut = _strip_headline(cur, hn)
            if cut is not None:
                rest = _text(cut)
                if _DATELINE.match(rest) and re.search(r"(?i)\b" + _MON + r"\.?\s+\d{1,2}|\b(?:19|20)\d\d\b", rest[:90]):
                    new = cut
        if new is not None:
            out.append((m.start(2), m.end(2), new))
        if len(t) >= 140:
            break
    for a, b, new in reversed(out):
        h = h[:a] + new + h[b:]
    return h


def _short_url(u):
    m = re.match(r"https?://(?:www\.)?([^/?#]+)", u)
    return (m.group(1) if m else u[:40]) + "/…"


def _urls(h):
    """A web address over 60 characters is shown short and stays (or becomes) a link to the full address."""
    if "http" not in h:
        return h
    parts, depth, out = _SPLIT.split(h), 0, []
    for p in parts:
        if p.startswith("<"):
            low = p[:3].lower()
            if low == "<a " or low == "<a>":
                depth += 1
            elif p[:4].lower() == "</a>":
                depth = max(0, depth - 1)
            out.append(p)
        elif depth:
            out.append(_short_url(p.strip()) if _LONGURL.fullmatch(p.strip()) else p)
        else:
            def link(m):
                u = m.group(0)
                tail = ""
                while u and u[-1] in ".,;:)":
                    tail, u = u[-1] + tail, u[:-1]
                return '<a href="%s" rel="noopener noreferrer">%s</a>%s' % (u.replace('"', "%22"), _short_url(u), tail)
            out.append(_LONGURL.sub(link, p))
    return "".join(out)


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _text(inner):
    return re.sub(r"\s+", " ", _html.unescape(_TAG.sub(" ", inner)).replace("\xa0", " ")).strip()


def cuts(h, headline=""):
    """[(start, end, why, text)] of the lines tidy() drops, in document order, one entry per line."""
    out = []
    table = re.search(r"(?i)<table\b", h)
    head_end = min(table.start() if table else len(h), 9000)
    hn = _norm(headline)
    run, run_spans, syms, addr, n = "", [], [], False, 0
    for m in _LEAF.finditer(h, 0, head_end):
        if "<img" in m.group(2).lower():
            continue
        t = _text(m.group(2))
        if not t:
            continue
        n += 1
        if n > 14:
            break
        cand = run + _norm(t)
        if hn and len(cand) >= 12 and hn.startswith(cand):
            run, run_spans = cand, run_spans + [(m.start(), m.end(), "headline repeated", t)]
            if len(run) >= 0.9 * len(hn):
                out += run_spans
                run, run_spans = "", []
            continue
        run, run_spans = "", []
        if _is_furniture(t):                                   # v3
            addr = addr or _furniture(t)[1] >= 2
            out.append((m.start(), m.end(), "opening notice" if _F_NOTICE.search(t) else "letterhead", t))
        elif _is_nfd(t):                                       # v3
            out.append((m.start(), m.end(), "not for distribution", t))
        elif len(t) < 130 and _OPENER.match(t):
            out.append((m.start(), m.end(), "opening notice", t))
        elif len(t) < 70 and _ADDR.match(t):
            addr = True
            out.append((m.start(), m.end(), "letterhead", t))
        elif len(t) < 70 and _SYM.match(t):
            syms.append((m.start(), m.end(), "letterhead", t))
        elif len(t) < 80 and _WEB.match(t):
            out.append((m.start(), m.end(), "web address", t))
        elif len(t) >= 140:
            break
    if addr:
        out += syms
    if "ewsfilecorp.com/release/" in h:                       # v3: the sentence alone on its line
        for m in _LEAF.finditer(h):
            if _NEWSFILE.fullmatch(m.group(2).strip()):
                out.append((m.start(), m.end(), "newsfile source line", _text(m.group(2))))
    if _HINT.search(h):
        leaves = [(m.start(), m.end(), _text(m.group(2))) for m in _LEAF.finditer(h) if "<img" not in m.group(2).lower()]
        leaves = [x for x in leaves if x[2]]
        for a, b, t in leaves:
            if len(t) < 300 and _BOILER.match(t):
                out.append((a, b, "wire boilerplate", t))
        for a, b, t in leaves[-4:]:
            if _SOURCE.match(t):
                out.append((a, b, "wire boilerplate", t))
    by_span = {}
    for x in out:
        by_span.setdefault((x[0], x[1]), x)
    return sorted(by_span.values())


def empty_columns(t):
    """One table's html -> (table html, columns removed). Removes grid columns that are empty in every row."""
    if re.search(r"(?i)<table\b", t[6:]) or _ROWSPAN.search(t):
        return t, 0
    rows = []                                              # (row match, [[cell match, span, empty]])
    for rm in _TR.finditer(t):
        cells = []
        for cm in _CELL.finditer(rm.group(2)):
            sp = _COLSPAN.search(cm.group(2))
            cells.append([cm, max(1, int(sp.group(1))) if sp else 1, not _text(cm.group(3)) and "<img" not in cm.group(3).lower()])
        if cells:
            rows.append((rm, cells))
    if len(rows) < 2:
        return t, 0
    width = sum(c[1] for c in rows[0][1])
    if not 3 <= width <= 40 or any(sum(c[1] for c in cells) != width for _rm, cells in rows):
        return t, 0
    cover = [[i for i, c in enumerate(cells) for _ in range(c[1])] for _rm, cells in rows]
    drop = set()
    for col in range(width):
        kinds = [("e" if (c[2] and c[1] == 1) else ("s" if c[1] > 1 else "x")) for c in (cells[cv[col]] for (_rm, cells), cv in zip(rows, cover))]
        if "x" not in kinds and "e" in kinds:
            drop.add(col)
    for (_rm, cells), cv in zip(rows, cover):              # a merged cell with text keeps at least one of its columns
        for i, c in enumerate(cells):
            mine = [col for col in range(width) if cv[col] == i]
            if c[1] > 1 and not c[2] and all(col in drop for col in mine):
                drop.discard(mine[0])
    if not drop or len(drop) > width - 2:
        return t, 0
    new = t
    for (rm, cells), cv in reversed(list(zip(rows, cover))):
        parts = []
        for i, (cm, span, empty) in enumerate(cells):
            gone = sum(1 for col in range(width) if cv[col] == i and col in drop)
            if gone == span:
                continue
            if gone:
                attrs = _COLSPAN.sub("", cm.group(2)) + ((' colspan="%d"' % (span - gone)) if span - gone > 1 else "")
                parts.append("<%s%s>%s</%s>" % (cm.group(1), attrs, cm.group(3), cm.group(1)))
            else:
                parts.append(cm.group(0))
        new = new[:rm.start()] + rm.group(1) + "".join(parts) + rm.group(3) + new[rm.end():]
    if _norm(_text(new)) != _norm(_text(t)):
        return t, 0                                        # some text would change: leave the table as it is
    return new, len(drop)


def tidy(h, headline=""):
    """Runs the pass until nothing more changes (at most three times): dropping a letterhead can bring the next
    opening line into reach, and tidying twice must equal tidying once."""
    for _ in range(3):
        new = _once(h, headline)
        if new == h:
            break
        h = new
    return h


def _once(h, headline=""):
    if not h:
        return h
    try:                                                       # v3: edits inside the opening lines
        h = _pre(h, headline)
    except Exception:  # noqa: BLE001 - display only: never break a page
        pass
    for a, b, _why, _t in reversed(cuts(h, headline)):
        h = h[:a] + h[b:]
    try:                                                       # v3: Newsfile sentence inside a paragraph; long addresses
        if "ewsfilecorp.com/release/" in h:
            h = _NEWSFILE.sub("", h)
        h = _urls(h)
    except Exception:  # noqa: BLE001
        pass
    if "lick" in h and _CLICK.search(h):
        h = _CLICK.sub("", h)
    if "<table" in h.lower():
        h = _TBL.sub(lambda m: empty_columns(m.group(0))[0], h)
    return h
