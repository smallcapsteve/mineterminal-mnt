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
        if len(t) < 130 and _OPENER.match(t):
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
    if not h:
        return h
    for a, b, _why, _t in reversed(cuts(h, headline)):
        h = h[:a] + h[b:]
    if "lick" in h and _CLICK.search(h):
        h = _CLICK.sub("", h)
    if "<table" in h.lower():
        h = _TBL.sub(lambda m: empty_columns(m.group(0))[0], h)
    return h
