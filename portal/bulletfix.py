"""BULLETFIX_V1 — bullets whose glyph sits on its own line (MNT, 2026-11-05).

Releases laid out as a two-column table (glyph in one cell, item text in the next:
SEC EDGAR exhibits, many Word-made PDFs) reach us with the bullet glyph on its own
line. Neither converter recognised that as a bullet:

  * release_format.reflow_text_html (text-only rows) printed "<p>●</p>" then the item
    as an ordinary paragraph;
  * pdf_html.pdf_to_html (rebuilt PDF HTML in release_html.db) did the same.

Two render-time helpers, used by release_format; neither writes any stored row:

  prep_text(text)  for reflow: joins a lone glyph line to the next text line
                   ("●\\n\\nItem" -> "• Item") and maps Wingdings/Symbol private-use
                   bullets (U+F0B7 etc.) to "•", so the existing bullet rule applies.
  fix_html(h)      for stored PDF HTML: "<p>●</p><p>Item</p>" -> list item; a lone
                   glyph right before an existing <ul> is dropped; inline private-use
                   bullets ("<p>\\uf0b7 Item</p>") become list items. Sub-level glyphs
                   (o, ◦, U+F0A7) nest under the item before them.

Lone "-", "–" and "*" are left alone on purpose: in the stored releases they are
signature rules and footnote marks as often as bullets.
"""
from __future__ import annotations

import re

VERSION = "bulletfix-1.1"

PUA = ""
TOP = "•●▪■‣⁃∙➢✓·○◆♦➤►" + ""
SUB = "o◦"
GLYPHS = TOP + SUB

_LONE_LINE = re.compile("^\\s*[" + re.escape(GLYPHS) + "]\\s*$")
_PUA_LEAD = re.compile("^(\\s*)[" + re.escape(PUA) + "]\\s*(?=\\S)")
_PAGE_NO = re.compile(r"^\s*(page\s*)?\d{1,3}(\s*(of|/)\s*\d{1,3})?\s*$", re.I)


def prep_text(text: str) -> str:
    if not text:
        return text
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = list(lines)
    n = len(out)
    i = 0
    while i < n:
        s = out[i]
        if _LONE_LINE.match(s):
            j = i + 1
            while j < n and not out[j].strip():
                j += 1
            if j < n and not _LONE_LINE.match(out[j]) and not _PAGE_NO.match(out[j]):
                g = s.strip()
                mark = "o" if g in SUB else "•"
                out[j] = mark + " " + out[j].strip()
                out[i] = ""
                i = j
                continue
        else:
            out[i] = _PUA_LEAD.sub(lambda m: m.group(1) + ("o " if m.group(0).strip() == "" else "• "), s, count=1)
        i += 1
    return "\n".join(out)


# ---------------------------------------------------------------- HTML

_WRAP_O = r"(?:<(?:strong|em)>\s*)*"
_WRAP_C = r"(?:\s*</(?:strong|em)>)*"
_LONE_P = re.compile(r"^<p>\s*" + _WRAP_O + "([" + re.escape(GLYPHS) + "])" + _WRAP_C + r"\s*</p>$", re.S)
_PUA_P = re.compile(r"^<p>(\s*" + _WRAP_O + ")([" + re.escape(PUA) + r"])\s*(.+)</p>$", re.S)
_P = re.compile(r"^<p(?:\s[^>]*)?>(.*)</p>$", re.S)
_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>")
_VOID = {"br", "img", "hr", "wbr", "col", "source"}


def _chunks(h: str) -> list[str]:
    """Split HTML into its top-level elements (text between them kept as its own chunk)."""
    out, depth, start, pos = [], 0, 0, 0
    for m in _TAG.finditer(h):
        closing, name, selfclose = m.group(1), m.group(2).lower(), m.group(3)
        if name in _VOID or selfclose:
            if depth == 0:
                if h[pos:m.start()].strip():
                    out.append(h[pos:m.start()].strip())
                out.append(m.group(0))
                pos = m.end()
            continue
        if not closing:
            if depth == 0:
                if h[pos:m.start()].strip():
                    out.append(h[pos:m.start()].strip())
                start = m.start()
            depth += 1
        else:
            depth -= 1
            if depth <= 0:
                depth = 0
                out.append(h[start:m.end()])
                pos = m.end()
    if h[pos:].strip():
        out.append(h[pos:].strip())
    return out


def _inner(chunk: str) -> str | None:
    m = _P.match(chunk)
    if not m:
        return None
    return m.group(1).strip()


def _build(items: list[tuple[int, str]]) -> str:
    """items: (level 1|2, inner html) -> nested <ul>."""
    out, open_sub, first = ["<ul>"], False, True
    for lvl, inner in items:
        if lvl == 2 and not first:
            if not open_sub:
                out.append("<ul>")
                open_sub = True
            out.append(f"<li>{inner}</li>")
            continue
        if open_sub:
            out.append("</ul>")
            open_sub = False
        if not first:
            out.append("</li>")
        out.append(f"<li>{inner}")
        first = False
    if open_sub:
        out.append("</ul>")
    out.append("</li></ul>")
    return "\n".join(out)


def fix_html(h: str) -> str:
    if not h or not any(g in h for g in GLYPHS):
        return h
    ch = _chunks(h)
    res: list[str] = []
    items: list[tuple[int, str]] = []
    changed = False
    mine: set[int] = set()            # indexes in res of lists built here

    def add(c: str, built: bool = False):
        # a list right after a list becomes one list, when either of them was built here
        if c.startswith("<ul>") and c.endswith("</ul>") and res and res[-1].startswith("<ul>") \
                and res[-1].endswith("</ul>") and (built or (len(res) - 1) in mine):
            res[-1] = res[-1][:-5].rstrip() + "\n" + c[4:].lstrip()
            mine.add(len(res) - 1)
            return
        res.append(c)
        if built:
            mine.add(len(res) - 1)

    def flush():
        if items:
            add(_build(items), True)
            items.clear()

    i = 0
    while i < len(ch):
        c = ch[i]
        m = _LONE_P.match(c)
        if m:
            nxt = ch[i + 1] if i + 1 < len(ch) else ""
            inner = _inner(nxt) if nxt else None
            if inner and not _LONE_P.match(nxt) and re.sub(r"<[^>]+>", "", inner).strip():
                items.append((2 if m.group(1) in SUB else 1, inner))
                changed = True
                i += 2
                continue
            if nxt.lower().startswith("<ul"):
                changed = True          # the item after it is already a list item
                i += 1
                continue
        mp = _PUA_P.match(c)
        if mp and re.sub(r"<[^>]+>", "", mp.group(3)).strip():
            items.append((2 if mp.group(2) in SUB else 1, (mp.group(1) + mp.group(3)).strip()))
            changed = True
            i += 1
            continue
        flush()
        add(c)
        i += 1
    flush()
    return "\n".join(res) if changed else h


# ---------------------------------------------------------------- MNT_FMTFIX_V1: website junk (bulletfix-1.1)
# Releases scraped from company websites sometimes carry the site's own furniture: the WordPress
# "Prev - <title> / Next - <title>" block (class content-nav, post-navigation, nav-links) and tags that were
# escaped into the text ("MAX POWER &lt;BR&gt; SYSTEM", "Kinross World &lt;/span&gt; \"&gt;").
# Render-time only; the stored release is unchanged.
_ESC_TAG = re.compile(
    r"&lt;\s*(/?)\s*(br|span|div|p|strong|b|i|em|font|a|u|small)"
    r"(?:\s+[a-z-]+\s*=\s*(?:\"[^\"<>]*\"|'[^'<>]*'|[^\s&<>]+))*\s*/?\s*&gt;(\s*[\"”]\s*&gt;)?", re.I)
_NAV_OPEN = re.compile(r"<(div|nav|ul|section)\b[^>]*\bclass\s*=\s*[\"'][^\"']*\b(content-nav(?:_holder)?|post-navigation|nav-links|nav-previous|nav-next|blog-nav)\b[^\"']*[\"'][^>]*>", re.I)


def _drop_element(h, m):
    """Remove the element opened at match m (depth-aware for its own tag name)."""
    tag = m.group(1).lower()
    depth, pos = 1, m.end()
    rx = re.compile(r"<(/?)%s\b[^>]*>" % tag, re.I)
    for t in rx.finditer(h, pos):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return h[:m.start()] + h[t.end():]
    return h


def strip_site_junk(h: str) -> str:
    if not h:
        return h
    out = h
    if "&lt;" in out:
        out = _ESC_TAG.sub(lambda m: " " if m.group(2).lower() == "br" else "", out)
    for _ in range(4):
        m = _NAV_OPEN.search(out)
        if not m:
            break
        out = _drop_element(out, m)
    return out


# ---- DATA5_V1 (2026-11-05): PDF page footers ("Page", "2 | P a g e" and the lone page numbers beside them), lone box
# glyphs and OCR'd map labels (":s;" noise) dropped from exchange-PDF text and rebuilt PDF HTML. Wraps 1.1's
# prep_text / fix_html; any error falls back to their output.
import html as _d5_html_mod

_D5_PAGE = re.compile(r"^(?:(?:P\s?a\s?g\s?e|Page)(?:\s*\|?\s*\d{1,3})?|\d{1,3}\s*\|?\s*P\s?a\s?g\s?e)$")
_D5_NUM = re.compile(r"^\d{1,3}$")
_D5_GLYPH = re.compile(r"^[■□▪▫◆◇]$")
_D5_OCR = re.compile(r":[A-Za-z];")
_D5_P = re.compile(r"(?is)<p\b[^>]*>(.*?)</p>")


def _d5_junk(texts) -> set:
    bad = set()
    for i, t in enumerate(texts):
        s = (t or "").strip()
        if s and (_D5_PAGE.match(s) or _D5_GLYPH.match(s) or (len(s) < 80 and _D5_OCR.search(s))):
            bad.add(i)
    page = {i for i in bad if _D5_PAGE.match((texts[i] or "").strip())}
    for i, t in enumerate(texts):
        if i not in bad and _D5_NUM.match((t or "").strip()) and ((i - 1) in page or (i + 1) in page):
            bad.add(i)
    return bad


def _d5_text(text: str) -> str:
    lines = (text or "").split("\n")
    bad = _d5_junk(lines)
    return "\n".join(l for i, l in enumerate(lines) if i not in bad) if bad else text


def _d5_html(h: str) -> str:
    ms = list(_D5_P.finditer(h or ""))
    if not ms:
        return h
    texts = [_d5_html_mod.unescape(re.sub(r"(?s)<[^>]+>", "", m.group(1))) for m in ms]
    bad = _d5_junk(texts)
    if not bad:
        return h
    out, last = [], 0
    for i, m in enumerate(ms):
        if i in bad:
            out.append(h[last:m.start()])
            last = m.end()
    out.append(h[last:])
    return "".join(out)


_d5_prep_text_v11, _d5_fix_html_v11 = prep_text, fix_html


def prep_text(text: str) -> str:  # noqa: F811 - DATA5_V1 wrapper
    out = _d5_prep_text_v11(text)
    try:
        return _d5_text(out)
    except Exception:  # noqa: BLE001
        return out


def fix_html(h: str) -> str:  # noqa: F811 - DATA5_V1 wrapper
    out = _d5_fix_html_v11(h)
    try:
        return _d5_html(out)
    except Exception:  # noqa: BLE001
        return out


VERSION = VERSION + "+data5"
