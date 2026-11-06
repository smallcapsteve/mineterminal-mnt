"""SECFIX_V1 (MNT_FMTFIX2_V1, 2026-11-05): EDGAR-style tables and blank space in release HTML, at render time."""
from __future__ import annotations

import re

VERSION = "secfix-1.1"

# ---------------------------------------------------------------- MNT_FMTFIX2_V1: EDGAR-style tables and blank space (bulletfix-1.2)
# SEC exhibits (and some wire copies) lay tables out with spacer columns, "$" in a cell of its own and ")" / "%" in
# the next cell, plus empty logo tables and hundreds of empty paragraphs. compact_tables() rebuilds only tables whose
# cells are at least 30% empty or that have a lone currency cell, and keeps the original table unless every letter and
# digit survives in the same order. tidy_blocks() drops empty paragraphs and turns "<p>(bullet)Text</p>" runs into lists.
_TBL = re.compile(r"(?is)<table\b[^>]*>.*?</table>")
_TR = re.compile(r"(?is)<tr\b[^>]*>(.*?)</tr>")
_CELL = re.compile(r"(?is)<(t[dh])\b([^>]*)>(.*?)</\1>")
_CUR = {"$", "US$", "C$", "CA$", "A$", "EUR", "GBP", "R$", "MXN$", chr(0x20ac), chr(0xa3)}
_TAIL = {")", "%", ")%", "%)", "*", ")*"}
_NBSP = chr(0xa0)


def _ctext(x):
    return re.sub(r"\s+", " ", html_unescape(re.sub(r"(?s)<[^>]+>", " ", x)).replace(_NBSP, " ")).strip()


def html_unescape(x):
    import html as _h
    return _h.unescape(x)


def _sig(x):
    return re.sub(r"[^0-9A-Za-z]", "", _ctext(x))


def _compact_one(t):
    if re.search(r"(?is)<table\b", t[6:]):
        return t                                  # nested table: leave it
    rows = []
    total = empty = lone = 0
    for rm in _TR.finditer(t):
        cells = []
        for cm in _CELL.finditer(rm.group(1)):
            tx = _ctext(cm.group(3))
            cs = re.search(r"(?i)colspan\s*=\s*[\"']?(\d+)", cm.group(2))
            cells.append([cm.group(1).lower(), tx, cm.group(3), int(cs.group(1)) if cs else 1])
            total += 1
            if not tx:
                empty += 1
            elif tx in _CUR:
                lone += 1
        rows.append(cells)
    if total < 6 or not (empty >= 0.3 * total or lone):
        return t
    out_rows = []
    for cells in rows:
        first_has = bool(cells and cells[0][1])
        vals = []                                  # [tag, html]
        pend = ""
        for tag, tx, inner, span in cells:
            if not tx:
                continue
            if tx in _CUR:
                pend = tx
                continue
            if tx in _TAIL and vals:
                vals[-1][1] = vals[-1][1].rstrip() + tx
                continue
            inner = re.sub(r"(?is)\s(style|class|width|height|align|valign|bgcolor|nowrap)\s*=\s*(\"[^\"]*\"|'[^']*'|\S+)", "", inner)
            inner = re.sub(r"(?is)</?(?:p|div)\b[^>]*>", " ", inner).strip()   # 1.1: "$" and figure on one line
            vals.append([tag, pend + inner])
            pend = ""
        if not vals:
            continue
        out_rows.append((first_has, vals))
    if not out_rows:
        return ""                                  # an empty logo / spacer table
    ncol = max(len(v) for _, v in out_rows)
    html_rows = []
    for first_has, vals in out_rows:
        if len(vals) < ncol:
            pad = [["td", ""]] * (ncol - len(vals))
            vals = (vals[:1] + pad + vals[1:]) if first_has else (pad + vals)
        html_rows.append("<tr>" + "".join("<%s>%s</%s>" % (g, h, g) for g, h in vals) + "</tr>")
    new = '<table class="sec-compact">' + "".join(html_rows) + "</table>"
    if _sig(new) != _sig(t):
        return t                                   # something would be lost: keep the original
    return new


def compact_tables(h):
    if not h or "<table" not in h.lower():
        return h
    return _TBL.sub(lambda m: _compact_one(m.group(0)), h)


_BUL = "[" + chr(0x2022) + chr(0x25cf) + chr(0x25aa) + chr(0xb7) + "]"
_EMPTY_BLOCK = re.compile(r"(?is)<(p|div)\b[^>]*>(?:\s|&nbsp;|&#160;|" + _NBSP + r"|<br\s*/?>|<(?:span|font|b|i|strong|em)\b[^>]*>\s*</(?:span|font|b|i|strong|em)>)*</\1>")
_BULLET_BODY = r"<(p|div)\b[^>]*>\s*(?:<(?:span|font)\b[^>]*>\s*)*" + _BUL + r"\s*(?:</(?:span|font)>\s*)*((?:(?!<(?:p|div)\b).)+?)</(?:p|div)>"   # 1.1: <div> bullets too
_BULLET_P = re.compile(r"(?is)" + _BULLET_BODY)


def tidy_blocks(h):
    if not h:
        return h
    out = h
    for _ in range(3):
        n = _EMPTY_BLOCK.sub("", out)
        if n == out:
            break
        out = n
    out = re.sub(r"(?i)(<br\s*/?>\s*){3,}", "<br><br>", out)

    def lists(m):
        items = [x[1] for x in _BULLET_P.findall(m.group(0))]
        return "<ul>" + "".join("<li>%s</li>" % x.strip() for x in items) + "</ul>"
    out = re.sub(r"(?is)(?:" + _BULLET_BODY + r"\s*){2,}", lists, out)
    return out
