"""RELFMT_V1 — how a stored release body becomes the page body (MNT, 2026-10-02).

Three jobs, all at render time, none of which change a stored row:

1. pdf_html_for(event_id)
   Exchange-path releases (source tmx / cse) have no raw_html. PDFHTML_V1
   (pdf_html.py, run by the mnt-pdfhtml job) rebuilds HTML from the original
   PDF into /opt/mnt/app/data/release_html.db. This looks it up.

2. reflow_text_html(raw_body, headline)
   For text-only rows that have no rebuilt HTML yet (PDF unreadable, docx, or
   not processed yet). Before this, event.html printed each line of the PDF
   text as its own <p>. This re-joins wrapped lines into paragraphs, keeps
   bullets and short headings, and keeps runs of number-heavy lines (what is
   left of a table) one row per line instead of one paragraph.

3. polish_tables(html)
   For wire HTML: marks numeric cells class="num" (right-aligned by CSS)
   unless the source already set an alignment, so columns of figures line up.

Everything returned is passed through html_sanitize by the caller or is built
from escaped text here.
"""
from __future__ import annotations

import html as _html
import os
import re
import sqlite3
import threading

RELEASE_HTML_DB = os.environ.get("MNT_RELEASE_HTML_DB", "/opt/mnt/app/data/release_html.db")
_LOCAL = threading.local()


# ------------------------------------------------------------------ 1. lookup

def _con():
    c = getattr(_LOCAL, "con", None)
    if c is None:
        if not os.path.exists(RELEASE_HTML_DB):
            return None
        c = sqlite3.connect(f"file:{RELEASE_HTML_DB}?mode=ro", uri=True, check_same_thread=False)
        _LOCAL.con = c
    return c


def pdf_html_for(event_id) -> str:
    if not event_id:
        return ""
    try:
        c = _con()
        if c is None:
            return ""
        r = c.execute("SELECT html FROM release_html WHERE event_id=? AND status='ok'", (str(event_id),)).fetchone()
        if not r or not r[0]:
            return ""
        from .html_sanitize import sanitize_release_html  # second line of defence; stored copy is already clean
        return sanitize_release_html(r[0])
    except Exception:  # noqa: BLE001 - a missing/locked side store must never break a page
        return ""


# ------------------------------------------------------------------ 2. reflow

_BUL = re.compile(r"^\s*([•●▪■‣⁃∙◦➢·\-–\*]|o(?=\s))\s+")
_NUM_ITEM = re.compile(r"^\s*(\(?\d{1,2}[.)]|\(?[a-h][.)]|\(?[ivx]{1,4}[.)])\s+\S")
_ENDS = re.compile(r"([.!?]|[.!?][\"”’)])\s*$")
_NUMTOK = re.compile(r"^[($€£<>~±+\-–]*\d[\d.,]*[%)*]*$")
_PAGE_NO = re.compile(r"^\s*(page\s*)?\d{1,3}(\s*(of|/)\s*\d{1,3})?\s*$", re.I)


def _is_data_line(s: str) -> bool:
    toks = s.split()
    if len(toks) < 3:
        return False
    nums = sum(1 for t in toks if _NUMTOK.match(t))
    return nums >= 3 and nums >= 0.4 * len(toks)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def reflow_text_html(text: str, headline: str = "") -> str:
    if not text:
        return ""
    lines = [l.rstrip() for l in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lens = sorted(len(l.strip()) for l in lines if len(l.strip()) > 20)
    width = lens[int(len(lens) * 0.9)] if lens else 80
    full = max(40, int(width * 0.72))

    blocks = []   # [kind, [lines]]   kind: p | li | rows
    prev = None
    for raw in lines:
        s = raw.strip()
        if not s:
            prev = None
            continue
        if _PAGE_NO.match(s):
            continue
        if _is_data_line(s):
            if blocks and blocks[-1][0] == "rows" and prev is not None:
                blocks[-1][1].append(s)
            else:
                blocks.append(["rows", [s]])
            prev = s
            continue
        bullet = bool(_BUL.match(s)) or bool(_NUM_ITEM.match(s))
        new = (
            prev is None or bullet
            or (blocks and blocks[-1][0] == "rows")
            or (len(prev) < full and _ENDS.search(prev) is not None)
            or (len(prev) < width * 0.9 and _ENDS.search(prev) is not None and (s[:1].isupper() or s[:1] in "\"“("))
        )
        if not new and blocks and len(blocks[-1][1]) == 1 and len(prev) < full and _ENDS.search(prev) is None \
                and blocks[-1][0] == "p" and _looks_heading(prev) and (s[:1].isupper() or s[:1].isdigit()):
            new = True   # the previous line was a heading on its own
        if new:
            if bullet:
                blocks.append(["li", [_BUL.sub("", s, count=1)]])
            else:
                blocks.append(["p", [s]])
        else:
            blocks[-1][1].append(s)
        prev = s

    def join(parts):
        out = ""
        for p in parts:
            if not out:
                out = p
            elif out.endswith("-") and not out.endswith(" -") and p[:1].islower():
                out = out[:-1] + p
            elif out.endswith(("(", "“", "/")) or p[:1] in ",.;:)”" or (out.endswith('"') and out.count('"') % 2 == 1) \
                    or (p[:1] == '"' and out.count('"') % 2 == 1):
                out = out + p
            else:
                out = out + " " + p
        return out

    # drop the headline from the top (it is the page <h1>)
    if headline:
        hn = _norm(headline)
        while blocks and blocks[0][0] == "p":
            bt = _norm(join(blocks[0][1]))
            if len(bt) >= 12 and (bt in hn or hn.startswith(bt)):
                blocks.pop(0)
                continue
            # headline wrapped and glued to the first paragraph
            if hn and bt.startswith(hn) and len(hn) >= 20:
                cut = blocks[0][1]
                acc = ""
                while cut and _norm(acc + cut[0]) and hn.startswith(_norm(acc + " " + cut[0])):
                    acc += " " + cut.pop(0)
                if not cut:
                    blocks.pop(0)
            break

    out, in_list = [], False
    for kind, parts in blocks:
        if kind == "li":
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>" + _html.escape(join(parts), quote=False) + "</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if kind == "rows":
            out.append('<p class="txt-rows">' + "<br>".join(_html.escape(p, quote=False) for p in parts) + "</p>")
        else:
            t = join(parts)
            esc = _html.escape(t, quote=False)
            if len(parts) == 1 and _looks_heading(t):
                out.append('<p class="pdf-sub"><strong>' + esc + "</strong></p>")
            else:
                out.append("<p>" + esc + "</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _looks_heading(s: str) -> bool:
    s = s.strip()
    if not (3 <= len(s) <= 70) or _ENDS.search(s) or re.search(r"\b(19|20)\d\d\b|--|[(),]", s):
        return False
    words = s.split()
    if len(words) > 9 or not s[:1].isupper():
        return False
    caps = sum(1 for w in words if w[:1].isupper() or not w[:1].isalpha())
    return caps >= max(1, int(len(words) * 0.6))


# ------------------------------------------------------------------ 3. tables

_CELL_NUM = re.compile(r"^[\s$€£(<>~≈±+\-–—]*\d[\d\s.,]*[%)*†‡]*\s*$|^\s*[\-–—]\s*$|^\s*n/?a\s*$", re.I)
_TD_OPEN = re.compile(r"<td\b([^>]*)>", re.I)


def polish_tables(h: str) -> str:
    """Add class="num" to <td> whose whole text is a figure, unless the source
    already aligns the cell (align= or a text-align style)."""
    if not h or "<td" not in h.lower():
        return h
    out, pos = [], 0
    hl = h.lower()  # DOWN3 (2026-10-07): lowered once, not once per table cell; same result
    for m in _TD_OPEN.finditer(h):
        attrs = m.group(1)
        end = hl.find("</td>", m.end())
        if end < 0:
            break
        inner = h[m.end():end]
        txt = _html.unescape(re.sub(r"<[^>]+>", "", inner)).replace("\xa0", " ").strip()
        if txt and _CELL_NUM.match(txt) and not re.search(r"\balign\s*=|text-align", attrs, re.I):
            if re.search(r'\bclass\s*=\s*"', attrs, re.I):
                attrs = re.sub(r'(\bclass\s*=\s*")', r"\1num ", attrs, count=1, flags=re.I)
            else:
                attrs = attrs + ' class="num"'
            out.append(h[pos:m.start()])
            out.append("<td" + attrs + ">")
            pos = m.end()
    out.append(h[pos:])
    return "".join(out)


# ------------------------------------------------------------------ self-test

def _self_test() -> None:
    t = ("Peruvian Metals Announces Third Quarter\nProduction at the Aguila Norte Processing\nPlant\n"
         "Edmonton, Alberta--(Newsfile Corp. - October 1, 2026) -\nPeruvian Metals Corp (TSXV: PER)\n(OTCQB: DUVNF)\n"
         "(\"Peruvian Metals\" or the \"Company\") announces third quarter production results and the start of a detailed\n"
         "auger drilling program on the tailings area at its 80-per-cent-owned Aguila Norte processing plant in Peru.\n"
         "During the third quarter of 2026, the Plant processed a total of 9,065 metric tonnes (\"mt\"). The Plant has\n"
         "achieved full production capacity for 9 of the previous 10 quarters.\n"
         "Qualified Person\n"
         "Jeffrey Reeder, P. Geo., is the Qualified Person who has reviewed and approved the technical contents.\n"
         "Hole From To Width Au\nBK-01 12.0 15.0 3.0 9.21\nBK-02 39.0 44.0 5.0 0.90\n"
         "• first point of the list\n• second point\n")
    h = reflow_text_html(t, "Peruvian Metals Announces Third Quarter Production at the Aguila Norte Processing Plant")
    assert "Announces Third Quarter" not in h, h
    assert "the start of a detailed auger drilling" in h, h
    assert '<p class="pdf-sub"><strong>Qualified Person</strong></p>' in h, h
    assert "BK-01 12.0 15.0 3.0 9.21<br>BK-02" in h, h
    assert "<li>first point of the list</li>" in h, h
    p = polish_tables('<table><tr><td>Gold</td><td>1,234</td><td align="right">5</td><td class="x">(4.5%)</td></tr></table>')
    assert '<td class="num">1,234</td>' in p and '<td align="right">5</td>' in p and 'class="num x"' in p, p


_self_test()
