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
import re

VERSION = "pdfhtml-1.0.3"

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

MAX_PAGES = 12

_BULLET = re.compile("^\\s*([•●▪■‣⁃∙◦➢✓·—―o\\-–\\*])\\s+")
_NUMBERED = re.compile(r"^\s*(\(?\d{1,2}[.)]|\(?[a-z][.)]|\(?[ivx]{1,4}[.)])\s+")
_PAGE_NO = re.compile(r"^\s*(page\s*)?\d{1,3}(\s*(of|/)\s*\d{1,3})?\s*$", re.I)
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
    return re.sub(r"\s+", " ", str(c)).strip()


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


def _ruled_tables(page) -> list[tuple[tuple, str]]:
    found = []
    try:
        tf = page.find_tables()  # strategy "lines": only tables drawn with rules
    except Exception:  # noqa: BLE001
        return found
    for t in getattr(tf, "tables", []) or []:
        try:
            rows = t.extract()
        except Exception:  # noqa: BLE001
            continue
        h = _table_html(rows)
        if h:
            found.append((tuple(t.bbox), h))
    return found


def _aligned_tables(lines: list[dict]) -> list[tuple[tuple, str, set]]:
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
                h = _table_html(rows)
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
    aligned = _aligned_tables(lines)
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


def pdf_to_html(data: bytes, headline: str = "") -> str:
    doc = fitz.open(stream=data, filetype="pdf")
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
            if not text or _PAGE_NO.match(text):
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
                if cur["html"].endswith("-") and not cur["html"].endswith(" -") and text[:1].islower():
                    cur["html"] = cur["html"][:-1] + h  # hyphenated word wrap
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
        plain = re.sub(r"<[^>]+>", "", h).strip()
        if _URL_ONLY.match(plain):
            u = html.unescape(plain)
            if _IMG_URL.search(u):
                if out and _VIEW_GRAPHIC.search(re.sub(r"<[^>]+>", "", out[-1])):
                    out.pop()  # "To view an enhanced version of this graphic, please visit:"
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
    return "\n".join(out)


def stats(h: str) -> dict:
    return {t: len(re.findall(rf"<{t}[\s>]", h)) for t in ("p", "li", "table", "tr", "td", "th", "strong")}
