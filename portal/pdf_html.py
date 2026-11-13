"""PDFHTML_V1 — rebuild readable HTML from a news-release PDF (MNT, 2026-10-02).

Why: releases collected from the exchanges (TMX filings, CSE) arrive as a PDF.
exchange_news.py stores pypdf's plain text in `raw_body` and nothing in
`raw_html`, and event.html then printed every *printed line* of the PDF as its
own <p>. Tables were flattened into one number per line and sentences were cut
wherever the PDF wrapped them.

This module reads the PDF itself (PyMuPDF) and returns sanitised HTML:

  * real <table>s, from PyMuPDF's table finder (ruled tables) plus a
    column-alignment finder for unruled ones;
  * paragraphs re-joined across line wraps and page breaks;
  * bullets as <ul><li>; bold-only short lines as sub-headings (<p><strong>);
  * inline bold / italic kept;
  * running headers/footers and page numbers dropped;
  * the headline (already shown as the page <h1>) dropped from the top.

It never invents text: every character in the output is a character PyMuPDF
read off the page. Output goes through html_sanitize like every other body.
"""
from __future__ import annotations

import collections
import html
import io
import os
import re

VERSION = "pdfhtml-1.5.0"   # FIGS_V1 (2026-11-11): pictures and drawn figures, when the caller asks for them;   # RELFMT3400_A (2026-11-11): line-end hyphens, sentence-tables, spacer columns, glyph bullets, page footers, Newsfile graphics;   # RULEDFIX_V2 (2026-11-11): part-ruled tables: two-column and small tables, fairer acceptance tests;   # RULEDFIX_V1 (2026-11-11): part-ruled tables with glued number cells are rebuilt from their words;   # TBLCOLS_V1 (2026-11-11): unruled tables get their columns from the gaps between words

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

MAX_PAGES = 12

_BULLET = re.compile("^\\s*([•●▪■‣⁃∙◦➢✓·—―o\\-–\\*�])\\s+")
_NUMBERED = re.compile(r"^\s*(\(?\d{1,2}[.)]|\(?[a-z][.)]|\(?[ivx]{1,4}[.)])\s+")
_PAGE_NO = re.compile(r"^\s*(page\s*)?\d{1,3}(\s*(of|/)\s*\d{1,3})?\s*$", re.I)
_PAGE_FOOT = re.compile(r"(?i)^.{0,60}\bpage\s+\d{1,3}\s+of\s+\d{1,3}\b.{0,20}$")       # RELFMT3400_A
_HYJOIN = chr(0xE000)      # marks a line-end hyphen join until the whole text is known (_resolve_hyphens)
_HYSITE = re.compile(r"([A-Za-z]{2,})-((?:</?(?:strong|em)>)*)" + _HYJOIN + r"((?:</?(?:strong|em)>)*)([a-z]{2,})")
_HYTAIL = frozenset("tion tions ation ations ization isation sion sions ment ments ity ities ness ance ence ally ously ized ised izing ising alization alized eralization eration erations ical ically ology ological ible ture tures tive tively ular ularly".split())
_SPACED = {"NEWSRELEASE": "NEWS RELEASE", "PRESSRELEASE": "PRESS RELEASE", "FORIMMEDIATERELEASE": "FOR IMMEDIATE RELEASE", "MEDIARELEASE": "MEDIA RELEASE"}
_NF_GRAPHIC = re.compile(r"(?is)^(.*?)\s*to view an enhanced version of th(?:is|e) (?:graphic|image|figure|table|map)s?,? please visit:?\s*(https?://\S+(?:\s\S+)?)\s*$")


def _resolve_hyphens(h: str) -> str:
    """HYPHEN_V1. A word hyphenated at the end of a printed line is joined to the next line with no space. The
    hyphen stays ("forward-looking") unless the same text shows the joined word and never the hyphenated one
    ("explor-" + "ation" where "exploration" is used elsewhere)."""
    if _HYJOIN not in h:
        return h
    plain = re.sub(r"<[^>]+>", " ", h).lower()
    seen = collections.Counter(re.findall(r"[a-z]+(?:-[a-z]+)*", plain.replace("-" + _HYJOIN, " ")))
    def fix(m):
        a, t1, t2, b = m.groups()
        tags = (t1 + t2).replace("</strong><strong>", "").replace("</em><em>", "")
        joined, hyph = (a + b).lower(), (a + "-" + b).lower()
        keep = not ((seen[joined] > 0 and seen[hyph] == 0) or (seen[hyph] == 0 and b.lower() in _HYTAIL))
        return a + ("-" if keep else "") + tags + b
    return _HYSITE.sub(fix, h).replace(_HYJOIN, "")


def _despace(h: str) -> str:
    """'N E W S   R E L E A S E' -> 'NEWS RELEASE', only when the wider gaps between the words are still there."""
    m = re.fullmatch(r"(\s*(?:<(?:strong|em)>)*)(.*?)((?:</(?:strong|em)>)*\s*)", h, re.S)
    if not m or "<" in m.group(2):
        return h
    t = m.group(2)
    toks = t.split()
    if len(toks) < 6 or sum(1 for x in toks if len(x) == 1) < 0.8 * len(toks):
        return h
    if "".join(toks).upper() in _SPACED:
        return m.group(1) + _SPACED["".join(toks).upper()] + m.group(3)
    parts = [w.replace(" ", "") for w in re.split(r" {2,}", t.strip())]
    if len(parts) < 2 or min(len(w) for w in parts) < 2:      # the word gaps are not there: leave it
        return h
    return m.group(1) + " ".join(parts) + m.group(3)
_END_SENT = re.compile(r"[.!?:;\"”’)\]]\s*$")
_URL_ONLY = re.compile(r"^https?://\S+$")
_IMG_URL = re.compile(r"\.(jpe?g|png|gif|webp)(\?\S*)?$", re.I)
_VIEW_GRAPHIC = re.compile(r"to view an enhanced version of th(is|e) (graphic|image|figure)", re.I)
_NUMERIC = re.compile(r"^[\s$€£(<>~≈±+\-–—%]*[\d.,]+[\s%)*†‡a-zA-Z/]*$|^[\s\-–—n/aNA.]+$")


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def _span_html(span: dict) -> str:
    t = span["text"]
    if not t:
        return ""
    e = _esc(t)
    flags = span.get("flags", 0)
    bold = bool(flags & 16) or "bold" in span.get("font", "").lower() or "black" in span.get("font", "").lower()
    ital = bool(flags & 2) or "italic" in span.get("font", "").lower() or "oblique" in span.get("font", "").lower()
    sup = bool(flags & 1)
    if not t.strip():
        return e
    if sup and len(t.strip()) <= 4:
        e = f"<sup>{e}</sup>"
    if ital:
        e = f"<em>{e}</em>"
    if bold:
        e = f"<strong>{e}</strong>"
    return e


def _merge_tags(h: str) -> str:
    """'<strong>a</strong><strong> b</strong>' -> '<strong>a b</strong>'."""
    for tag in ("strong", "em"):
        h = re.sub(rf"</{tag}>(\s*)<{tag}>", r"\1", h)
    return h


def _in_box(b, box, pad=1.5) -> bool:
    x0, y0, x1, y1 = b
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return box[0] - pad <= cx <= box[2] + pad and box[1] - pad <= cy <= box[3] + pad


# ---------------------------------------------------------------- tables

def _clean_cell(c) -> str:
    if c is None:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"([A-Za-z]{2}-)[ \t]*\n[ \t]*(?=[a-z]{2})", r"\1", str(c))).strip()


def _table_html(rows: list[list]) -> str:
    # drop columns that are empty in every row (spacer columns)
    if not rows:
        return ""
    ncol = max(len(r) for r in rows)
    rows = [list(r) + [None] * (ncol - len(r)) for r in rows]
    keep = [j for j in range(ncol) if any(_clean_cell(r[j]) for r in rows)]
    if len(keep) < 2:
        return ""
    rows = [[r[j] for j in keep] for r in rows]
    rows = [r for r in rows if any(_clean_cell(c) for c in r)]
    if len(rows) < 2:
        return ""
    out = ["<table class=\"pdf-table\">"]
    # header: first row if it has no numeric cells (and later rows do)
    def numeric_cells(r):
        return sum(1 for c in r if _clean_cell(c) and _NUMERIC.match(_clean_cell(c)))
    nh = 0
    while nh < min(3, len(rows) - 1) and numeric_cells(rows[nh]) == 0:
        nh += 1
    body = rows
    if nh and sum(numeric_cells(r) for r in rows[nh:]):
        out.append("<thead>" + "".join("<tr>" + "".join(f"<th>{_esc(_clean_cell(c))}</th>" for c in r) + "</tr>"
                                       for r in rows[:nh]) + "</thead>")
        body = rows[nh:]
    out.append("<tbody>")
    for r in body:
        cells = []
        for c in r:
            t = _clean_cell(c)
            cls = ' class="num"' if t and _NUMERIC.match(t) else ""
            cells.append(f"<td{cls}>{_esc(t)}</td>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


_why: list = []     # diagnostics only: why _rebuild_ruled kept PyMuPDF's table (last 200)
_samples = None     # diagnostics only: set to a list to collect (reason, PyMuPDF rows, rebuilt rows)


def _refuse(reason: str, old=None, new=None):
    _why.append(reason)
    del _why[:-200]
    if _samples is not None:
        _samples.append((reason, [[_clean_cell(c) for c in r] for r in (old or [])[:4]], [list(r) for r in (new or [])[:7]]))
    return None



_GLUED = re.compile(r"^[($<>~\-]*\d[\d.,]*[%)*]*(\s+[($<>~\-]*\d[\d.,]*[%)*]*)+$")


def _glued_rows(rows) -> int:
    """Rows that hold a cell made of two or more separate numbers ('71.00 158.00')."""
    return sum(1 for r in rows if any(_GLUED.match(_clean_cell(c)) for c in r))


def _rebuild_ruled(words: list, bbox: tuple, rows_old: list[list]) -> list[list[str]] | None:
    """RULEDFIX_V1. A table drawn with only some of its rules comes back from PyMuPDF with several rows or
    columns in one cell. Rebuild it from the words inside its box: printed lines become rows, word gaps become
    columns. Returns None (the PyMuPDF table stands) unless the rebuilt table holds exactly the same words,
    has fewer glued rows, at least as many columns, and no row made only of one- or two-character scraps
    (a number wrapped inside a narrow cell)."""
    x0, y0, x1, y1 = bbox
    ws = [w for w in words if w[4].strip() and x0 - 1 <= (w[0] + w[2]) / 2 <= x1 + 1 and y0 - 1 <= (w[1] + w[3]) / 2 <= y1 + 1]
    if len(ws) < 6:
        return _refuse("few words", rows_old)
    hs = sorted(w[3] - w[1] for w in ws)
    size = hs[len(hs) // 2] or 9
    ws.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines: list[list] = []
    for w in ws:
        cy = (w[1] + w[3]) / 2
        if lines and abs(cy - lines[-1][0]) <= 0.45 * size:
            lines[-1][1].append(w)
        else:
            lines.append([cy, [w]])
    rows = [sorted(l[1], key=lambda w: w[0]) for l in lines]
    new = _river_core(rows, size, 0.15, 2, 2)
    if not new:
        return _refuse("no columns found", rows_old, [[" ".join(w[4] for w in r)] for r in rows])
    blob = lambda rr: re.sub(r"[^a-z0-9]+", "", " ".join(_clean_cell(c) for r in rr for c in r).lower())  # noqa: E731
    b_old, b_new = blob(rows_old), blob(new)
    # RULEDFIX_V2: the rebuilt table is every word printed inside the box, once. PyMuPDF repeats the text of cells
    # that overlap, so the test is that no word it read is missing, not that the letter counts are equal.
    for r in rows_old:
        for c in r:
            for p in re.split(r"[\s\-]+", _clean_cell(c)):
                p = re.sub(r"[^a-z0-9]+", "", p.lower())
                if len(p) >= 3 and p not in b_new:
                    return _refuse("text would be lost", rows_old, new)
    if len(b_new) > 1.25 * max(1, len(b_old)):
        return _refuse("much more text than PyMuPDF read", rows_old, new)
    used = lambda rr: sum(1 for j in range(max(len(r) for r in rr)) if any(j < len(r) and _clean_cell(r[j]) for r in rr))  # noqa: E731
    gnum = lambda rr: sum(len(_clean_cell(c).split()) for r in rr for c in r if _GLUED.match(_clean_cell(c)))  # noqa: E731
    if gnum(new) >= gnum(rows_old):                   # numbers still sharing a cell: must go down
        return _refuse("glued numbers not fewer", rows_old, new)
    widest = lambda rr: max(sum(1 for c in r if _clean_cell(c)) for r in rr)  # noqa: E731
    if used(new) < used(rows_old) and widest(new) < widest(rows_old):
        return _refuse("fewer columns", rows_old, new)
    for r in new:
        cells = [c for c in r if c]
        if cells and all(len(c) <= 2 for c in cells) and any(ch.isdigit() for c in cells for ch in c):
            return _refuse("scrap row (wrapped number)", rows_old, new)
    return new


def _ruled_tables(page) -> list[tuple[tuple, str]]:
    found = []
    try:
        tf = page.find_tables()  # strategy "lines": only tables drawn with rules
    except Exception:  # noqa: BLE001
        return found
    words = None
    for t in getattr(tf, "tables", []) or []:
        try:
            rows = t.extract()
        except Exception:  # noqa: BLE001
            continue
        h = _table_html(rows)
        if h and _glued_rows(rows):
            try:    # RULEDFIX_V1: only for tables that show glued number cells; any doubt keeps PyMuPDF's table
                if words is None:
                    words = page.get_text("words", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP)
                r2 = _rebuild_ruled(words, tuple(t.bbox), rows)
                h2 = _table_html(r2) if r2 else ""
                if h2:
                    h = h2
            except Exception:  # noqa: BLE001
                pass
        if h:
            found.append((tuple(t.bbox), h))
    return found


def _river_rows(run_lines: list[dict], words: list) -> list[list[str]] | None:
    """TBLCOLS_V1. Columns of an unruled table from the vertical gaps ("rivers") that stay clear of words in
    its number rows, instead of from the gaps inside each printed line. Splits cells the line-gap method glues
    together ('71.00 158.00'; a header printed as one run of text). Returns rows of cell text, or None when
    the words cannot be matched to the lines or fewer than three columns come out. Never drops a word."""
    rows = []
    for ln in run_lines:
        x0, y0, x1, y1 = ln["bbox"]
        ws = sorted((w for w in words if w[4].strip() and y0 - 1 <= (w[1] + w[3]) / 2 <= y1 + 1
                     and w[0] >= x0 - 1.5 and w[2] <= x1 + 1.5), key=lambda w: w[0])
        if re.sub(r"\s+", "", "".join(w[4] for w in ws)) != re.sub(r"\s+", "", _line_text(ln)):
            return None
        rows.append(ws)
    hs = sorted(ln["bbox"][3] - ln["bbox"][1] for ln in run_lines)
    return _river_core(rows, hs[len(hs) // 2] or 9, 0.4)


def _river_core(rows: list[list], size: float, share: float, min_rows: int = 3, min_cols: int = 3) -> list[list[str]] | None:
    """Rows of words (PyMuPDF 'words' tuples, left to right) -> rows of cell text, columns from the word gaps."""
    def is_num(t):
        return bool(re.search(r"\d", t)) and bool(_NUMERIC.match(t))
    data = [ws for ws in rows if ws and sum(1 for w in ws if is_num(w[4])) >= max(2, share * len(ws))]
    if len(data) < min_rows:
        return None
    data_ids = {id(ws) for ws in data}
    lo = min(w[0] for ws in data for w in ws)
    hi = max(w[2] for ws in data for w in ws)
    step = 0.5
    n = int((hi - lo) / step) + 2
    cover = [0] * n
    for ws in data:
        mark = set()
        for w in ws:
            mark.update(range(int((w[0] - lo) / step), int((w[2] - lo) / step) + 1))
        for k in mark:
            if 0 <= k < n:
                cover[k] += 1
    allowed = len(data) // 5                      # one stray row in five may sit across a gap
    min_gap = max(2.5, 0.45 * size)
    cols, start, gap_from = [], None, None        # [x0, x1] of each column
    for k in range(n + 1):
        full = k < n and cover[k] > allowed
        if full:
            if start is None:
                if cols and gap_from is not None and (k - gap_from) * step < min_gap:
                    start = cols.pop()[0]       # gap too narrow to be a column break: same column
                else:
                    start = lo + k * step
            gap_from = None
        elif start is not None:
            cols.append([start, lo + k * step])
            start, gap_from = None, k
    if len(cols) < min_cols:
        return None
    def col_of(w):
        best, ov = None, 0.0
        for j, (a, b) in enumerate(cols):
            o = min(w[2], b) - max(w[0], a)
            if o > ov:
                best, ov = j, o
        return best
    numcol = [0] * len(cols)
    cnt = [0] * len(cols)
    for ws in data:
        for w in ws:
            j = col_of(w)
            if j is not None:
                cnt[j] += 1
                numcol[j] += 1 if is_num(w[4]) else 0
    numeric = [cnt[j] > 0 and numcol[j] * 2 > cnt[j] for j in range(len(cols))]
    out = []
    for ws in rows:
        row = [""] * len(cols)
        units = ws
        if id(ws) not in data_ids:               # a heading or label line: a run of words that fits one column stays whole
            runs = []
            for w in ws:
                if runs and w[0] - runs[-1][-1][2] < min_gap:
                    runs[-1].append(w)
                else:
                    runs.append([w])
            units = []
            for run in runs:
                u = (run[0][0], run[0][1], run[-1][2], run[-1][3], " ".join(x[4] for x in run))
                over = [q for q, (a, b) in enumerate(cols) if min(u[2], b) - max(u[0], a) > 0]
                if len(over) <= 1 or (len(runs) == 1 and len(over) >= 3):   # one column, or a title across the table
                    units.append(u)
                else:
                    units.extend(run)
        for w in units:
            j = col_of(w)
            if len(units) == 1 and w is not ws[0] and len(ws) > 1:        # the title: one cell, where it starts
                j = next((q for q, (a, b) in enumerate(cols) if min(w[2], b) - max(w[0], a) > 0), j)
            if j is None:                         # the word sits in a gap (a header over a right-aligned column)
                cx = (w[0] + w[2]) / 2
                right = next((q for q, (a, b) in enumerate(cols) if a > cx), None)
                left = right - 1 if right not in (None, 0) else (len(cols) - 1 if right is None else None)
                if right is not None and ((numeric[right] and id(ws) not in data_ids) or left is None):   # a footnote mark after a label stays with the label
                    j = right
                elif left is not None and right is not None:
                    j = left if cx - cols[left][1] <= cols[right][0] - cx else right
                else:
                    j = left if left is not None else 0
            row[j] = (row[j] + " " + w[4]).strip()
        out.append(row)
    return out


def _aligned_tables(lines: list[dict], words: list | None = None) -> list[tuple[tuple, str, set]]:
    """Unruled tables: runs of >=3 consecutive lines that each split into >=3
    cells separated by wide horizontal gaps, with cell starts lining up."""
    def cells_of(ln):
        spans = [s for s in ln["spans"] if s["text"].strip()]
        if not spans:
            return []
        cells, cur, last_x1 = [], None, None
        size = max(s["size"] for s in spans) or 9
        for s in spans:
            x0 = s["bbox"][0]
            if cur is None or x0 - last_x1 > size * 1.2:
                cur = {"x0": x0, "text": s["text"].strip()}
                cells.append(cur)
            else:
                cur["text"] = (cur["text"] + " " + s["text"].strip()).strip() if x0 - last_x1 > size * 0.15 else cur["text"] + s["text"].strip()
            last_x1 = s["bbox"][2]
        return cells

    out = []
    i = 0
    while i < len(lines):
        run = []
        j = i
        while j < len(lines):
            cs = cells_of(lines[j])
            if len(cs) >= 3:
                run.append((j, cs))
                j += 1
            else:
                break
        if len(run) >= 3:
            # column anchors: cluster x0 of cells
            xs = sorted(c["x0"] for _, cs in run for c in cs)
            anchors = []
            for x in xs:
                if not anchors or x - anchors[-1][-1] > 12:
                    anchors.append([x])
                else:
                    anchors[-1].append(x)
            cols = [sum(a) / len(a) for a in anchors if len(a) >= max(2, len(run) // 3)]
            numericish = sum(1 for _, cs in run for c in cs[1:] if _NUMERIC.match(c["text"]))
            if len(cols) >= 3 and numericish >= len(run):
                rows = []
                for _, cs in run:
                    row = [""] * len(cols)
                    for c in cs:
                        k = min(range(len(cols)), key=lambda q: abs(cols[q] - c["x0"]))
                        row[k] = (row[k] + " " + c["text"]).strip()
                    rows.append(row)
                filled = [c for r in rows for c in r if c]
                toks = [t for c in filled for t in c.split()]
                if filled and sum(1 for c in filled if re.search(r"\d", c)) < 0.2 * len(filled) \
                        and sum(1 for t in toks if re.search(r"\d", t)) < 0.08 * len(toks) and len(toks) > 3.5 * len(filled):
                    i = j                    # RELFMT3400_A: mostly words in long cells - sentences, not a table
                    continue
                h = _table_html(rows)
                if h and words:
                    try:    # TBLCOLS_V1: more columns from the word gaps, only when every character is kept
                        r2 = _river_rows([lines[k] for k, _ in run], words)
                        h2 = _table_html(r2) if r2 else ""
                        used = lambda rr: sum(1 for j in range(max(len(r) for r in rr)) if any(j < len(r) and r[j] for r in rr))  # noqa: E731
                        fill = lambda rr: sum(1 for r in rr for c in r if c) / max(1, len(rr) * used(rr))  # noqa: E731
                        better = used(r2) > used(rows) or (used(r2) >= 3 and fill(r2) >= fill(rows) + 0.15)   # RELFMT3400_A: fewer spacer cells
                        if h2 and better and _norm(re.sub(r"<[^>]+>", "", h2)) == _norm(re.sub(r"<[^>]+>", "", h)):
                            h = h2
                    except Exception:  # noqa: BLE001 - the line-gap table stands
                        pass
                if h:
                    idx = {k for k, _ in run}
                    x0 = min(lines[k]["bbox"][0] for k in idx); y0 = min(lines[k]["bbox"][1] for k in idx)
                    x1 = max(lines[k]["bbox"][2] for k in idx); y1 = max(lines[k]["bbox"][3] for k in idx)
                    out.append(((x0, y0, x1, y1), h, idx))
            i = j
        else:
            i = max(j, i + 1)
    return out


# ---------------------------------------------------------------- text

_FIG = None          # FIGS_V1: set by pdf_to_html() for one conversion: {"out": [...], "url": "...", "rep": {xrefs}}
FIG_MAX = 14         # pictures per release
FIG_MAX_BYTES = 8_000_000


def _figures(page, table_boxes) -> list[tuple[float, str, tuple]]:
    """FIGS_V1. Pictures on a page, as (y, html, box). A picture is a stored image shown at least 150 x 100 pt, or a dense
    group of drawn lines and shapes (a map, section or chart) at least 200 x 130 pt. Each is a snapshot of that part
    of the page, so labels printed over it are in the picture. Left out: logos and letterhead art (small, at the top
    of page 1, or repeated on several pages), page-size backgrounds and scans, anything lying over a rebuilt table,
    drawn groups with a lot of text inside (a ruled or shaded table, a text box), blank areas."""
    cfg = _FIG
    if cfg is None or len(cfg["out"]) >= FIG_MAX or cfg.get("bytes", 0) >= FIG_MAX_BYTES:
        return []
    pr = page.rect
    parea = max(1.0, pr.width * pr.height)
    regs = []
    try:
        infos = page.get_image_info(xrefs=True)
    except Exception:  # noqa: BLE001
        infos = []
    for im in infos:
        r = fitz.Rect(im["bbox"]) & pr
        if r.is_empty or r.width < 150 or r.height < 100 or im.get("width", 0) < 300 or im.get("height", 0) < 200:
            continue
        if r.width * r.height > 0.85 * parea or im.get("xref", 0) in cfg["rep"]:
            continue
        if page.number == 0 and r.y0 < pr.y0 + 0.2 * pr.height and r.height < 0.3 * pr.height:
            continue                                   # letterhead art: a banner or logo at the top of page 1
        regs.append([r, "img"])
    try:
        drawings = page.get_drawings() if len(regs) < 6 else []
        if len(drawings) <= 60000 and sum(len(d.get("items") or ()) for d in drawings) >= 60:
            for c in page.cluster_drawings(drawings=drawings, x_tolerance=5, y_tolerance=5):
                c = fitz.Rect(c) & pr
                if c.is_empty or c.width < 200 or c.height < 130 or c.width * c.height > 0.85 * parea:
                    continue
                if sum(len(d.get("items") or ()) for d in drawings if fitz.Rect(d["rect"]).intersects(c)) >= 40:
                    regs.append([c, "vec"])
    except Exception:  # noqa: BLE001
        pass
    if not regs:
        return []
    merged = []
    for r, k in sorted(regs, key=lambda x: (x[0].y0, x[0].x0)):
        for m in merged:
            if (m[0] + (-6, -6, 6, 6)).intersects(r):
                m[0] |= r
                m[1] = "img" if "img" in (m[1], k) else "vec"
                break
        else:
            merged.append([fitz.Rect(r), k])
    try:
        words = page.get_text("words")
    except Exception:  # noqa: BLE001
        words = []
    out = []
    for r, k in merged:
        if any(abs((fitz.Rect(b) & r).get_area()) > 0.3 * r.get_area() for b in table_boxes):
            continue
        inside = sum(len(w[4]) for w in words if r.contains(fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)))
        if inside > (1500 if k == "img" else 400):
            continue                                   # prose or a table lies here: not a picture
        if len(cfg["out"]) >= FIG_MAX or cfg.get("bytes", 0) >= FIG_MAX_BYTES:
            break
        r = (r + (-3, -3, 3, 3)) & pr
        z = max(0.8, min(2.0, 1400.0 / r.width))
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=r, alpha=False, colorspace=fitz.csRGB)
            if pix.is_unicolor:
                continue
            data = pix.tobytes("jpeg", jpg_quality=78)
            if len(data) < 0.06 * pix.width * pix.height:          # little detail: is it a black-and-white icon?
                sm = pix.samples
                step = 3 * max(1, (len(sm) // 3) // 30000)
                idx = range(0, len(sm) - 2, step)
                flat = sum(1 for i in idx
                           if max(sm[i], sm[i + 1], sm[i + 2]) - min(sm[i], sm[i + 1], sm[i + 2]) < 28 and not 60 < sm[i] < 200)
                if flat >= 0.95 * len(idx):
                    continue                           # an envelope, an arrow, a social-media mark
        except Exception:  # noqa: BLE001
            continue
        n = len(cfg["out"]) + 1
        cfg["out"].append({"n": n, "page": page.number + 1, "kind": k, "w": pix.width, "h": pix.height, "jpeg": data,
                           "bbox": [round(v, 1) for v in r], "chars_inside": inside, "labels": ""})
        cfg["bytes"] = cfg.get("bytes", 0) + len(data)
        u = html.escape(f'{cfg["url"]}{n}.jpg')
        out.append((r.y0, tuple(r), f'<p><a href="{u}"><img src="{u}" alt="Figure" width="{pix.width}" height="{pix.height}" loading="lazy"></a></p>'))
    return [(y, h, box) for y, box, h in out]


def _page_items(page):
    """Yield ('table', y0, html) and ('line', line-dict) items in reading order."""
    ruled = _ruled_tables(page)
    d = page.get_text("dict", sort=True, flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP)
    lines = []
    for b in d.get("blocks", []):
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            if not any(s["text"].strip() for s in ln["spans"]):
                continue
            if ln.get("dir", (1, 0))[0] < 0.9:  # rotated text (side labels)
                continue
            if any(_in_box(ln["bbox"], box) for box, _ in ruled):
                continue
            ln["_block"] = id(b)
            lines.append(ln)
    # merge lines that share a baseline (PyMuPDF sometimes splits a visual line)
    lines.sort(key=lambda l: (round(l["bbox"][3] / 2.5), l["bbox"][0]))
    merged = []
    for ln in lines:
        if merged and abs(merged[-1]["bbox"][3] - ln["bbox"][3]) < 2.5 and ln["bbox"][0] >= merged[-1]["bbox"][2] - 1:
            m = merged[-1]
            gapx = ln["bbox"][0] - m["bbox"][2]
            if gapx > 1.0 and not _line_text(m).endswith(" ") and not _line_text(ln).startswith(" "):
                sp0 = dict(ln["spans"][0]); sp0["text"] = " "
                sp0["bbox"] = (m["bbox"][2], ln["bbox"][1], ln["bbox"][0], ln["bbox"][3])
                m["spans"] = m["spans"] + [sp0]
            m["spans"] = m["spans"] + ln["spans"]
            m["bbox"] = (min(m["bbox"][0], ln["bbox"][0]), min(m["bbox"][1], ln["bbox"][1]),
                         max(m["bbox"][2], ln["bbox"][2]), max(m["bbox"][3], ln["bbox"][3]))
        else:
            merged.append(dict(ln))
    lines = merged
    try:
        words = page.get_text("words", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP)
    except Exception:  # noqa: BLE001
        words = None
    aligned = _aligned_tables(lines, words)
    used = set()
    items = []
    for box, h in ruled:
        items.append(("table", box[1], h))
    for box, h, idx in aligned:
        used |= idx
        items.append(("table", box[1], h))
    for k, ln in enumerate(lines):
        if k in used:
            continue
        items.append(("line", ln["bbox"][1], ln))
    if _FIG is not None:                             # FIGS_V1
        try:
            figs = _figures(page, [b for b, _ in ruled] + [b for b, _, _ in aligned])
            for k, (fy, fh, fbox) in enumerate(figs):
                rec = _FIG["out"][len(_FIG["out"]) - len(figs) + k]
                keep = []
                for it in items:                     # words printed inside the picture are in the picture
                    if it[0] == "line" and _in_box(it[2]["bbox"], fbox, 0):
                        rec["labels"] += " " + _line_text(it[2])
                    else:
                        keep.append(it)
                items = keep
                items.append(("table", fy, fh))
        except Exception:  # noqa: BLE001 - a picture must never cost the text
            pass
    items.sort(key=lambda it: it[1])
    return items, page.rect.width


def _line_text(ln) -> str:
    return "".join(s["text"] for s in ln["spans"])


def _strip_bullet(ln) -> dict:
    """The line without its leading bullet glyph (which may sit in its own span)."""
    spans = [dict(s) for s in ln["spans"]]
    for k, sp in enumerate(spans):
        if sp["text"].strip():
            if _BULLET.match(sp["text"].strip() + " "):          # glyph alone in its span
                rest = sp["text"].strip()[1:]
                sp["text"] = _BULLET.sub("", sp["text"].strip() + " ", count=1) if rest.strip() == "" else _BULLET.sub("", sp["text"], count=1)
            else:
                sp["text"] = _BULLET.sub("", sp["text"], count=1)
            if not sp["text"].strip() and k + 1 < len(spans):
                spans[k + 1]["text"] = spans[k + 1]["text"].lstrip()
            break
    return {**ln, "spans": spans}


def _line_html(ln) -> str:
    return _merge_tags("".join(_span_html(s) for s in ln["spans"]))


def _all_bold(ln) -> bool:
    sp = [s for s in ln["spans"] if s["text"].strip()]
    return bool(sp) and all((s.get("flags", 0) & 16) or "bold" in s.get("font", "").lower() for s in sp)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def pdf_to_html(data: bytes, headline: str = "", figures: list | None = None, fig_url: str = "") -> str:
    """figures: pass an empty list to get the release's pictures (FIGS_V1): it is filled with dicts holding the JPEG
    bytes, and the HTML shows them as <img src="{fig_url}{n}.jpg">. Without it no pictures are looked for."""
    global _FIG
    doc = fitz.open(stream=data, filetype="pdf")
    _FIG = None
    if figures is not None and fig_url:
        cnt = collections.Counter()
        try:
            for pno, page in enumerate(doc):
                if pno >= MAX_PAGES:
                    break
                for x in {im[0] for im in page.get_images(full=True)}:
                    cnt[x] += 1
        except Exception:  # noqa: BLE001
            pass
        _FIG = {"out": figures, "url": fig_url, "rep": {x for x, c in cnt.items() if c >= 2}}
    pages = []
    for pno, page in enumerate(doc):
        if pno >= MAX_PAGES:
            break
        pages.append(_page_items(page))
    # running headers / footers: identical short text at the same height on >= 2 pages
    seen = collections.Counter()
    for items, _w in pages:
        for kind, y, obj in items:
            if kind == "line":
                seen[(_norm(_line_text(obj))[:60], round(y / 5))] += 1
    repeat = {k for k, n in seen.items() if n >= 2 and len(pages) >= 2 and k[0]}

    blocks: list[tuple[str, str]] = []  # (kind, html) kind in p, li, h, table
    cur = None  # current paragraph dict
    prev = None

    def flush():
        nonlocal cur
        if cur and cur["html"].strip():
            blocks.append((cur["kind"], cur["html"].strip(), cur.get("x0", 0.0)))
        cur = None

    body_x0 = None
    for items, width in pages:
        xs = [o["bbox"][0] for k, _, o in items if k == "line"]
        if xs:
            body_x0 = min(xs) if body_x0 is None else min(body_x0, min(xs))
        right = max([o["bbox"][2] for k, _, o in items if k == "line"] or [width])
        for kind, y, obj in items:
            if kind == "table":
                flush()
                blocks.append(("table", obj, 0.0))
                prev = None
                continue
            ln = obj
            text = _line_text(ln).strip()
            if not text or _PAGE_NO.match(text) or (len(text) < 90 and _PAGE_FOOT.match(text)):
                continue
            if (_norm(text)[:60], round(y / 5)) in repeat:
                continue
            size = max((s["size"] for s in ln["spans"] if s["text"].strip()), default=10)
            gap = (ln["bbox"][1] - prev["bbox"][3]) if prev is not None and ln["bbox"][1] >= prev["bbox"][1] else 999
            bullet = _BULLET.match(text) or (_NUMBERED.match(text) and len(text) > 6)
            starts_new = (
                cur is None or bullet or gap > size * 0.65
                or (prev is not None and prev["bbox"][2] < right - size * 4 and _END_SENT.search(_line_text(prev)))
                or (prev is not None and _all_bold(ln) != _all_bold(prev) and len(text) < 120 and _all_bold(ln))
                or (prev is not None and _all_bold(prev) and not _all_bold(ln) and _END_SENT.search(_line_text(prev)) is None and len(_line_text(prev)) < 90 and prev["bbox"][2] < right - size * 4)
            )
            # a list item's wrapped lines hang to the right of its bullet; a line back at
            # (or left of) the bullet's x is the next paragraph, not more of the item
            if not starts_new and cur is not None and cur["kind"] == "li" and ln["bbox"][0] <= cur["x0"] + 2:
                starts_new = True
            # continuation across a page break: previous paragraph didn't end a sentence
            if (gap == 999 and cur is not None and cur["kind"] == "p" and not bullet and not _END_SENT.search(cur["text"])
                    and (text[:1].islower() or not _all_bold(ln)) and len(cur["text"]) > 60):
                starts_new = False
            h = _line_html(ln)
            if starts_new:
                flush()
                if bullet and _BULLET.match(text):
                    h = _line_html(_strip_bullet(ln))
                    cur = {"kind": "li", "html": h, "text": text, "x0": ln["bbox"][0]}
                else:
                    cur = {"kind": "p", "html": h, "text": text}
            else:
                tail = re.sub(r"(?:\s|</(?:strong|em)>)+$", "", cur["html"])
                if re.search(r"[A-Za-z]{2}-$", tail) and re.match(r"(?:<(?:strong|em)>)*[a-z]{2}", h.lstrip()):
                    cur["html"] = cur["html"].rstrip() + _HYJOIN + h.lstrip()    # HYPHEN_V1, settled in _resolve_hyphens
                else:
                    cur["html"] = _merge_tags(cur["html"].rstrip() + " " + h.lstrip())
                cur["text"] += " " + text
            prev = ln
        prev = None  # new page
    flush()

    # drop the headline (it is the page <h1>) from the top: leading blocks whose
    # text is part of the headline, within the first few blocks
    if headline:
        hn = _norm(headline)
        for _ in range(6):
            if not blocks or blocks[0][0] == "table":
                break
            bt = _norm(re.sub(r"<[^>]+>", "", blocks[0][1]))
            if bt and len(bt) >= 12 and bt in hn:
                blocks.pop(0)
            else:
                break

    out = []
    levels: list[float] = []          # x0 of each open <ul>
    def close_lists():
        while levels:
            levels.pop()
            out.append("</li></ul>")
    for kind, h, x0 in blocks:
        if kind == "li":                   # an <li> stays open so a deeper list can nest inside it
            if not levels:
                levels.append(x0); out.append(f"<ul><li>{h}")
            elif x0 > levels[-1] + 6:
                levels.append(x0); out.append(f"<ul><li>{h}")
            else:
                while len(levels) > 1 and x0 < levels[-1] - 6:
                    levels.pop(); out.append("</li></ul>")
                out.append(f"</li><li>{h}")
            continue
        close_lists()
        if kind == "table":
            out.append(h)
            continue
        h = _despace(h)
        plain = re.sub(r"<[^>]+>", "", h).strip()
        g = _NF_GRAPHIC.match(html.unescape(plain)) if "nhanced version" in plain else None
        if g:
            u = re.sub(r"\s+", "", g.group(2))
            if _IMG_URL.search(u):
                if g.group(1).strip():
                    out.append(f"<p>{_esc(g.group(1).strip())}</p>")
                out.append(f'<p><a href="{html.escape(u)}"><img src="{html.escape(u)}" alt="Figure" loading="lazy"></a></p>')
                continue
        if _URL_ONLY.match(plain):
            u = html.unescape(plain)
            if _IMG_URL.search(u):
                if out and _VIEW_GRAPHIC.search(re.sub(r"<[^>]+>", "", out[-1])):
                    cap = re.sub(r"(?is)\s*to view an enhanced version of th(?:is|e) (?:graphic|image|figure).*$", "", re.sub(r"<[^>]+>", "", out[-1])).strip()
                    out.pop()  # "To view an enhanced version of this graphic, please visit:"
                    if len(cap) > 3:
                        out.append(f"<p>{cap}</p>")       # RELFMT3400_A: text already escaped
                out.append(f'<p><a href="{html.escape(u)}"><img src="{html.escape(u)}" alt="Figure" loading="lazy"></a></p>')
            else:
                out.append(f'<p><a href="{html.escape(u)}">{_esc(u)}</a></p>')
            continue
        if True:
            plain = re.sub(r"<[^>]+>", "", h)
            if re.fullmatch(r"\s*<strong>.*</strong>\s*", h, re.S) and len(plain) < 140 and "<strong>" not in h[8:-9]:
                out.append(f'<p class="pdf-sub">{h}</p>')
            else:
                out.append(f"<p>{h}</p>")
    close_lists()
    return _resolve_hyphens("\n".join(out))


_BADCH = chr(0xFFFD)
_BADTOK = re.compile("[A-Za-z]*(?:" + _BADCH + "[A-Za-z]*)+")


LIGWORDS = "/opt/mnt/app/data/ligwords.tsv"     # word<TAB>count, lower case, built by mkligwords.py from wire releases
_LIGS = ("ti", "tt", "fi", "fl", "ff", "ft", "ffi", "ffl", "tf", "th", "f", "t")
_ligvocab = None


def _lig_vocab() -> dict:
    global _ligvocab
    if _ligvocab is None:
        _ligvocab = {}
        try:
            with open(LIGWORDS, encoding="utf-8") as fh:
                for line in fh:
                    w, _, c = line.rstrip("\n").partition("\t")
                    if w:
                        _ligvocab[w] = int(c or 1)
        except OSError:
            pass
    return _ligvocab


def fix_unmapped(h: str, ref_text: str = "") -> tuple[str, int]:
    """UNMAPPED_V2. Some PDFs give no character for a joined letter pair ("Corpora?on", "Bri?sh", "Of?ice": the
    ti / tt / fi / ffi ligature of the font). Each damaged word is tried with the pairs a font joins; it is replaced
    only when exactly one result is a known word, or one is at least 8 times more common than the next. Anything
    else is left as it is. ref_text is not used (the stored text of such a release is damaged the same way).
    Returns (html, words repaired)."""
    if _BADCH not in h:
        return h, 0
    vocab = _lig_vocab()
    if not vocab:
        return h, 0
    import itertools
    cache = {}
    fixed = 0

    def one(m):
        nonlocal fixed
        tok = m.group()
        parts = tok.split(_BADCH)
        if sum(len(p) for p in parts) < 2 or len(parts) > 4:
            return tok
        if tok not in cache:
            got = []
            for combo in itertools.product(_LIGS, repeat=len(parts) - 1):
                w = "".join(p + c for p, c in zip(parts, combo + ("",)))
                n = vocab.get(w.lower(), 0)
                if n:
                    got.append((n, combo))
            got.sort(reverse=True)
            if got and (len(got) == 1 or got[0][0] >= 8 * got[1][0]):
                up = "".join(parts).isupper() and len("".join(parts)) > 1
                combo = got[0][1]
                cache[tok] = "".join(p + (c.upper() if up else c) for p, c in zip(parts, combo + ("",)))
                if parts[0] == "" and len(parts[1]) > 0 and parts[1][0].islower() is False and not up:
                    cache[tok] = cache[tok][0].upper() + cache[tok][1:]
            else:
                cache[tok] = tok
        if cache[tok] != tok:
            fixed += 1
        return cache[tok]

    return _BADTOK.sub(one, h), fixed


FIG_ROOT = "/var/lib/mnt-relimg"                        # served by nginx as /relimg/ (RELIMG_V1)
FIG_URL = "https://miningnewsterminal.com/relimg/%s/%s/"   # % (event_id[:2], event_id)


def save_figures(event_id: str, figures: list, root: str = FIG_ROOT) -> int:
    """Write a release's pictures as <root>/<id[:2]>/<id>/<n>.jpg, replacing any older set. Returns bytes written."""
    if not re.fullmatch(r"[0-9a-f]{16,64}", event_id or ""):
        return 0
    d = os.path.join(root, event_id[:2], event_id)
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.endswith(".jpg") or f.endswith(".tmp"):
                os.remove(os.path.join(d, f))
        if not figures:
            try:
                os.rmdir(d)
            except OSError:
                pass
    n = 0
    if figures:
        os.makedirs(d, mode=0o755, exist_ok=True)
        for f in figures:
            p = os.path.join(d, "%d.jpg" % int(f["n"]))
            with open(p + ".tmp", "wb") as fh:
                fh.write(f["jpeg"])
            os.chmod(p + ".tmp", 0o644)
            os.replace(p + ".tmp", p)
            n += len(f["jpeg"])
    return n


def unreadable(text: str) -> bool:
    """True when the text is mostly characters the PDF has no meaning for (a font without a character table)."""
    chars = [c for c in text if not c.isspace()]
    bad = sum(1 for c in chars if c == _BADCH or ord(c) < 32 or 0x7F <= ord(c) < 0xA0)
    return len(chars) >= 200 and bad > 0.08 * len(chars)


def stats(h: str) -> dict:
    return {t: len(re.findall(rf"<{t}[\s>]", h)) for t in ("p", "li", "table", "tr", "td", "th", "strong")}
