"""Portal text helpers: smart title casing + link sanitization + related-posts scrubber.

Three render-time transforms applied by Jinja filters:
  * smart_title(s):   ALL-CAPS headlines → Title Case (preserves acronyms,
                      element symbols, and known tickers from tickers.json).
  * clean_release_html(html, source_url):
                      - strip related-posts / "more news" widgets
                      - unwrap <a> tags pointing to the source company's own
                        domain (so users stay on the portal)
                      - mark external links target=_blank / rel=noopener
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# ---- acronym & element tables -------------------------------------------------

_ACRONYMS = {
    "TSX", "TSXV", "CSE", "OTCQB", "OTCQX", "OTC", "NYSE", "AMEX", "NASDAQ",
    "SEC", "SEDAR", "OSC", "BCSC", "ASC", "ASX", "LSE", "AIM", "FINRA",
    "CFTC", "CIRO", "IIROC", "FSRA",
    "CEO", "CFO", "COO", "CTO", "CMO", "CSO", "CRO", "VP", "EVP", "SVP",
    "COB", "MD", "GM",
    "USD", "CAD", "AUD", "EUR", "GBP", "JPY", "CNY", "HKD", "CHF",
    "IPO", "ETF", "GST", "HST", "PST", "RSU", "ESOP", "ESG",
    "M&A", "R&D", "YOY", "YTD", "QOQ", "EBITDA", "AI", "ML", "IT",
    "LOI", "MOU", "JV", "NDA", "NSR", "NPV", "IRR", "PEA", "PFS", "DFS",
    "KPI", "SOP", "FAQ",
    "USA", "US", "UK", "EU", "UAE", "DRC", "PRC", "ROK", "NZ",
    "NYC", "LA", "SF", "BC", "AB", "ON", "QC", "SK", "MB", "NS", "NL", "PE",
    "NI43-101", "43-101", "43-101F1", "PGM", "PGMS", "REE", "HREE", "LREE",
    "BHP", "LME", "COMEX", "LBMA", "JORC", "QAQC", "QP",
    "UG", "DSO", "CIM", "MRE", "EIS", "EA", "EPA",
    "ROM", "BIF", "VMS", "SEDEX", "MVT", "IOCG", "IOA",
    "EM", "IP", "MT", "PET", "XRD", "XRF", "ICP", "FA",
    "Q1", "Q2", "Q3", "Q4", "H1", "H2", "FY", "CY", "MTD", "QTD",
    "AM", "PM", "EST", "EDT", "PST", "PDT", "MST", "MDT", "UTC", "GMT", "ET", "PT",
    "ID", "URL", "API", "HTML", "XML", "PDF", "CSV", "SEO",
}

_ELEMENTS = {
    "Au", "Ag", "Cu", "Ni", "Zn", "Pb", "Co", "Fe", "Pt", "Pd", "Li",
    "Mo", "Mn", "Sn", "Ti", "Cr", "W", "Bi", "Sb", "Te",
    "Hg", "Cd", "Be", "Mg", "Al", "Si", "Ga", "Tl",
    "Nb", "Ta", "Zr", "Hf", "Sc", "Y", "La", "Ce", "Pr", "Nd", "Sm",
    "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "U",
    "Rh", "Ir", "Os", "Ru", "Re",
    "U3O8", "V2O5", "Li2O", "TiO2", "Fe2O3", "CaCO3", "CuEq", "AuEq", "NiEq",
}
_ELEMENTS_LOWER = {e.lower(): e for e in _ELEMENTS}

_SMALL = {
    "a", "an", "and", "as", "at", "but", "by", "de", "du", "en", "for",
    "from", "in", "into", "is", "nor", "of", "on", "onto", "or",
    "per", "so", "the", "to", "up", "upon", "via", "vs", "with", "yet",
    "over",
}

def _load_known_tickers() -> set[str]:
    for p in (Path("/opt/mnt/app/tickers.json"), Path(__file__).parent.parent / "tickers.json"):
        try:
            if p.exists():
                data = json.loads(p.read_text())
                return {(t.get("ticker") or "").split(".")[0].upper()
                        for t in data if t.get("ticker")}
        except Exception:
            continue
    return set()

_TICKERS = _load_known_tickers()

_PUNCT_SPLIT = re.compile(r"^(\W*)(.*?)(\W*)$", re.DOTALL)

def _titleize_token(tok: str, first: bool) -> str:
    m = _PUNCT_SPLIT.match(tok)
    if not m: return tok
    lead, core, trail = m.group(1), m.group(2), m.group(3)
    if not core: return tok
    if any(ch.isdigit() for ch in core):
        return lead + core + trail
    core_upper = core.upper()
    if core_upper in _ACRONYMS: return lead + core_upper + trail
    if core_upper in _TICKERS:  return lead + core_upper + trail
    if core.lower() in _ELEMENTS_LOWER:
        return lead + _ELEMENTS_LOWER[core.lower()] + trail
    if "-" in core and len(core) > 2:
        parts = core.split("-")
        out = [_titleize_token(p, first=(i == 0 and first)) for i, p in enumerate(parts)]
        return lead + "-".join(out) + trail
    if "/" in core:
        parts = core.split("/")
        out = [_titleize_token(p, first=(i == 0 and first)) for i, p in enumerate(parts)]
        return lead + "/".join(out) + trail
    if "'" in core or "\u2019" in core:
        return lead + core.title() + trail
    lower = core.lower()
    if lower in _SMALL and not first:
        return lead + lower + trail
    return lead + lower[0].upper() + lower[1:] + trail


def smart_title(s: str | None) -> str:
    if not s: return s or ""
    letters = [c for c in s if c.isalpha()]
    if not letters: return s
    ratio_upper = sum(1 for c in letters if c.isupper()) / len(letters)
    if ratio_upper < 0.80: return s
    tokens = s.split()
    out = [_titleize_token(tok, first=(i == 0)) for i, tok in enumerate(tokens)]
    return " ".join(out)


# ---- related-posts / "more news" scrubber -----------------------------------

# Phrases that, when they appear as a heading or widget label, mark the start
# of a post-listing block we want to strip (along with everything after it in
# the same container).
_STOP_HEADING_RE = re.compile(
    r"\b(?:"
    r"more\s+news(?:\s+stories)?"
    r"|related\s+(?:posts|stories|articles|news)"
    r"|recent\s+(?:posts|news|articles)"
    r"|latest\s+(?:posts|news|articles|updates)"
    r"|other\s+news"
    r"|you\s+may\s+also\s+(?:like|read|enjoy)"
    r"|keep\s+reading"
    r"|more\s+articles"
    r"|read\s+(?:next|more\s+stories)"
    r"|news(?:\s+(?:archive|releases))"
    r"|archive"
    r"|more\s+from"
    r")\b",
    re.I,
)

# CSS classes / data-widget-types that are always post-listing widgets —
# safe to strip regardless of surrounding text.
_POST_WIDGET_PATTERNS = [
    re.compile(r"uael-post", re.I),               # Ultimate Addons post widgets
    re.compile(r"elementor-widget-uael-posts", re.I),
    re.compile(r"\brelated-posts?\b", re.I),
    re.compile(r"\byarpp(-related)?\b", re.I),    # Yet Another Related Posts Plugin
    re.compile(r"\bwp-block-latest-posts", re.I),
    re.compile(r"\bpost-navigation\b", re.I),
    re.compile(r"\bnav-(?:links|below|next-previous)\b", re.I),
    re.compile(r"\bjetpack-related-posts\b", re.I),
    re.compile(r"\bcrp_related", re.I),           # Contextual Related Posts
    re.compile(r"\btrx_addons_box_related", re.I),
    re.compile(r"\bpt-cv-view\b", re.I),          # Content Views Pro
]


def _matches_post_widget(el) -> bool:
    if not hasattr(el, "attrs"):
        return False
    attrs = el.attrs or {}
    classes = " ".join(attrs.get("class") or [])
    wt = attrs.get("data-widget_type") or ""
    blob = classes + " " + wt
    return any(p.search(blob) for p in _POST_WIDGET_PATTERNS)


def _heading_is_stop_marker(el) -> bool:
    if getattr(el, "name", None) not in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return False
    try:
        txt = el.get_text(" ", strip=True)
    except Exception:
        return False
    if not txt or len(txt) > 80:
        return False
    return bool(_STOP_HEADING_RE.search(txt))


def _strip_post_widgets_and_tail(soup) -> None:
    """Remove related-posts widgets outright; when we hit a 'stop heading'
    inside the document body, delete the heading and everything after it."""
    # Pass 1: strip obvious post widgets anywhere.
    # Re-scan until stable — removing a parent can orphan children
    for _ in range(3):
        changed = False
        for el in list(soup.find_all(True)):
            # Skip elements whose parent was already detached
            if el.parent is None and el.name not in ("[document]",):
                continue
            try:
                if _matches_post_widget(el):
                    el.decompose()
                    changed = True
            except Exception:
                continue
        if not changed:
            break

    # Pass 2: find the first 'stop heading' still in the tree and truncate.
    stop = None
    for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        if _heading_is_stop_marker(el):
            stop = el
            break
    if stop is None:
        return

    # Walk from the stop heading up toward the root; at each level, delete
    # all following siblings. Then delete the stop heading itself.
    node = stop
    while node is not None and node.parent is not None:
        # collect next siblings (skip pure whitespace nav/nothing — we kill all)
        nxt = list(node.find_next_siblings())
        for sib in nxt:
            sib.decompose()
        node = node.parent
        # stop once we reach a root-ish element (body/html/document)
        if getattr(node, "name", None) in ("[document]", "html", "body"):
            break
    stop.decompose()


# ---- link cleaner ------------------------------------------------------------

def _host(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return ""


def _same_site(a_host: str, b_host: str) -> bool:
    if not a_host or not b_host: return False
    if a_host == b_host: return True
    def _base(h: str) -> str:
        parts = h.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else h
    return _base(a_host) == _base(b_host)


def clean_release_html(html: str, source_url: str = "") -> str:
    """Strip related-posts cruft, unwrap same-site links, tag external links."""
    if not html:
        return html or ""
    src_host = _host(source_url)
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return html

    # 1) Related-posts / more-news scrubber (does the heavy lifting)
    _strip_post_widgets_and_tail(soup)

    # 2) Link rewriting
    for a in list(soup.find_all("a")):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("#"):
            continue
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        h = _host(href)
        if not h:
            a.unwrap()
            continue
        if _same_site(h, src_host):
            a.unwrap()
            continue
        a["target"] = "_blank"
        a["rel"] = "noopener noreferrer"

    return str(soup)


# QUALITY_V3_PATCH
# Additional scrubbing rules for known leaks:
#   - "BACK TO NEWS" nav text (Nine Mile Metals-style theme)
#   - "SHARE THIS POST" / "SHARE THIS" orphan labels
#   - Tracking pixels (newsinfo/, alt="info")
#   - Corporate logo trailing image (alt="Corporate Logo")
#   - Broken image-alt ("Cannot view this image? Visit:")
# This re-wraps clean_release_html (as loaded above) with a second pass.

_V3_TRAILING_STOP_RE = re.compile(
    r"^(?:"
    r"back\s+to\s+news|"
    r"back\s+to\s+all\s+news|"
    r"back\s+to\s+newsroom|"
    r"back\s+to\s+press|"
    r"back\s+to\s+all\s+press|"
    r"share\s+this\s+post|"
    r"share\s+this|"
    r"share\s+this\s+article|"
    r"share\s+this\s+news|"
    r"share\s+on\s+social|"
    r"follow\s+us|"
    r"enter\s+your\s+details|"
    r"sign\s+up\s+for\s+news|"
    r"sign\s+up\s+to\s+our\s+newsletter|"
    r"join\s+our\s+mailing|"
    r"indicates\s+required\s+fields"
    r")\s*$",
    re.I,
)
# QUALITY_V3b_PATCH
# Additionally, drop any element with class 'skip-link' / 'screen-reader-text'
# or role='navigation' at the top of the document (accessibility a11y chrome).
_V3b_SKIP_CLASSES = re.compile(
    r"(?:skip-link|screen-reader-text|a11y-skip|aria-hidden)",
    re.I,
)

def _v3_strip_trailing_chrome(soup):
    """Walk descendants in reverse; delete trailing chrome text/img nodes
    until we hit real article content."""
    # Collect candidate text-only stop nodes and delete their ancestors+tail
    for el in list(soup.find_all(string=True)):
        try:
            s = (el.strip() if hasattr(el, "strip") else str(el).strip())
        except Exception:
            continue
        if not s:
            continue
        if not _V3_TRAILING_STOP_RE.match(s):
            continue
        # Guard: el may be detached due to earlier decomposition
        try:
            node = el.parent
        except Exception:
            node = None
        if node is None:
            continue
        while node is not None and getattr(node, "parent", None) is not None:
                name = getattr(node, "name", "") or ""
                if name in ("p", "div", "section", "article", "h1", "h2", "h3", "h4",
                            "h5", "h6", "li", "ul", "ol", "footer", "aside", "nav",
                            "span", "a", "button"):
                    # delete node + all following siblings in its parent
                    parent = node.parent
                    if parent is None:
                        break
                    try:
                        siblings = list(parent.children)
                        seen = False
                        for sib in siblings:
                            if sib is node:
                                seen = True
                            if seen and hasattr(sib, "decompose"):
                                sib.decompose()
                            elif seen:
                                try:
                                    sib.extract()
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    break
                node = node.parent
    # Strip a11y skip-links (can appear at top or bottom of body)
    for el in list(soup.find_all(True)):
        if el.parent is None:
            continue
        cls = " ".join((el.attrs.get("class") or []))
        if cls and _V3b_SKIP_CLASSES.search(cls):
            el.decompose()
            continue
        # Also catch literal anchor text "Skip to content"
        if el.name == "a":
            txt = el.get_text(strip=True).lower()
            if txt in ("skip to content", "skip to main content", "skip to navigation"):
                el.decompose()
                continue
    # Strip specific trailing images
    for im in list(soup.find_all("img")):
        if im.parent is None:
            continue
        alt = (im.get("alt") or "").strip()
        src_attr = (im.get("src") or "")
        if alt == "info" and "newsinfo" in src_attr.lower():
            im.decompose()
            continue
        if alt.lower() == "corporate logo":
            im.decompose()
            continue
        # Clean the "Cannot view this image? Visit:" alt that newsfile injects
        if alt.lower().startswith("cannot view this image"):
            im["alt"] = ""
    # Tail-trim pass: peel trailing empty/nav leaves.
    _V3_ORPHAN_NAV = re.compile(r"^(?:back|share|more|next|prev(?:ious)?)\s*$", re.I)
    # Skip trivial containers (images/hr/br/iframe don't count as "content-bearing"
    # when hunting for the last real content node).
    _V3_VOID_TAGS = {"br", "hr", "img", "meta", "link", "source", "wbr", "input"}
    for _ in range(20):
        changed = False
        leaves = [el for el in soup.find_all(True)
                  if el.parent is not None and not el.find(True)]
        if not leaves:
            break
        # Work from the end of the DOM backwards
        last = leaves[-1]
        # Skip content-bearing media/void tags - we want to stop BEFORE them
        if last.name in _V3_VOID_TAGS:
            break
        txt = (last.get_text(strip=True) or "")
        if not txt:
            # Empty leaf - peel it
            last.decompose()
            changed = True
        elif len(txt) <= 18 and _V3_ORPHAN_NAV.match(txt):
            # Orphan nav word - peel it
            last.decompose()
            changed = True
        if not changed:
            break
    return soup

# Wrap the existing clean_release_html so we run the v3 pass on its output
try:
    _v3_prev_clean = clean_release_html  # noqa: F821
except NameError:
    _v3_prev_clean = None

if _v3_prev_clean is not None:
    def clean_release_html(html_str, source_url=""):  # noqa: F811
        cleaned = _v3_prev_clean(html_str, source_url)
        if not cleaned:
            return cleaned
        try:
            soup = BeautifulSoup(cleaned, "html.parser")  # noqa: F821
        except Exception:
            return cleaned
        _v3_strip_trailing_chrome(soup)
        return str(soup)

# QUALITY_V4_PATCH (append-only)
# Adds:
#  * "Download the PDF here" / "Download the Presentation" / etc. trailing stops
#  * fusion-meta-info / mk-blog-author / blog-single-meta / blog-single-title
#    trailing chrome class patterns (from Avada & mk-* WP themes)
#  * Leading-chrome stripper: decompose top-of-body "By Posted <date> In <cat>"
#    meta blocks (mk-* blog theme) and author bylines
# All prior V3 behavior preserved; this just widens the regex sets and
# re-wraps clean_release_html with an extra pass.

import re as _re_v4  # local alias to avoid shadowing if re already imported
try:
    from bs4 import BeautifulSoup as _BS4_V4
except Exception:
    _BS4_V4 = BeautifulSoup  # type: ignore[name-defined]

_V3_TRAILING_STOP_RE = _re_v4.compile(
    r"^(?:"
    r"back\s+to\s+news|"
    r"back\s+to\s+all\s+news|"
    r"back\s+to\s+newsroom|"
    r"back\s+to\s+press|"
    r"back\s+to\s+all\s+press|"
    r"share\s+this\s+post|"
    r"share\s+this|"
    r"share\s+this\s+article|"
    r"share\s+this\s+news|"
    r"share\s+on\s+social|"
    r"follow\s+us|"
    r"enter\s+your\s+details|"
    r"sign\s+up\s+for\s+news|"
    r"sign\s+up\s+to\s+our\s+newsletter|"
    r"join\s+our\s+mailing|"
    r"indicates\s+required\s+fields|"
    r"download\s+the\s+pdf\s+here|"
    r"download\s+the\s+pdf|"
    r"download\s+the\s+presentation|"
    r"download\s+the\s+document|"
    r"download\s+document|"
    r"download\s+presentation|"
    r"download\s+pdf|"
    r"view\s+the\s+presentation|"
    r"view\s+presentation|"
    r"link\s+to\s+offering\s+document|"
    r"offering\s+document|"
    r"posted\s+in\s+[a-z ,&-]+$|"
    r"related\s+posts?|"
    r"recent\s+posts?|"
    r"more\s+posts?|"
    r"leave\s+a\s+comment|"
    r"0\s+comments?|"
    r"no\s+comments?|"
    r"author:\s*admin\d*|"
    r"by\s+admin\d+"
    r")\s*$",
    _re_v4.I,
)

_V3b_SKIP_CLASSES = _re_v4.compile(
    r"(?:skip-link|screen-reader-text|a11y-skip|aria-hidden|"
    r"fusion-meta-info|fusion-meta-info-wrapper|fusion-single-author-wrapper|"
    r"fusion-sharing-box|fusion-related-posts|"
    r"mk-blog-author|mk-post-meta-structured-data|mk-post-cat|mk-post-date|"
    r"blog-single-meta|blog-single-author|blog-single-tags|blog-single-title|"
    r"post-meta|entry-meta|author-meta|single-post-meta|"
    r"sharedaddy|sd-sharing|jp-relatedposts|"
    r"addtoany_share_save_container)",
    _re_v4.I,
)

# --- Leading-chrome: the mk-* theme (and a few others) put a big author/date
# block at the TOP of the post, right after the title. Strip it.
_V4_LEADING_META_RE = _re_v4.compile(
    r"^\s*by\s*(?:posted\s+)?(?:january|february|march|april|may|june|"
    r"july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}"
    r"(?:\s*in\s+[a-z ,&-]+)?\s*$",
    _re_v4.I,
)
_V4_LEADING_POSTED_RE = _re_v4.compile(
    r"^\s*posted\s+(?:january|february|march|april|may|june|"
    r"july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}\s*$",
    _re_v4.I,
)
_V4_LEADING_IN_CAT_RE = _re_v4.compile(
    r"^\s*in\s+[a-z][a-z ,&-]{1,50}$",
    _re_v4.I,
)
_V4_LEADING_BY_AUTHOR_RE = _re_v4.compile(
    r"^\s*by(?:\s+[a-z][a-z .'-]{1,40})?\s*$",
    _re_v4.I,
)
_V4_LEADING_ADMIN_RE = _re_v4.compile(
    r"^\s*(?:author:\s*)?admin\d*\s*$",
    _re_v4.I,
)

def _v4_strip_leading_chrome(soup):
    """Peel leading meta/author/date/category chrome from the top of the body.
    Walks the body's leading children and removes nodes whose visible text
    matches a known leading-chrome pattern. Stops at the first substantive node.
    """
    # Operate at the document top level (soup itself acts as root container
    # when BeautifulSoup parses a fragment)
    roots = [soup]
    # If there's an explicit <body> or <article>, prefer it
    for name in ("body", "article", "main"):
        found = soup.find(name)
        if found is not None:
            roots = [found]
            break

    for root in roots:
        # Iterate over a COPY of direct children since we may decompose
        for _ in range(30):  # bounded loop — at most ~30 leading nodes
            changed = False
            # Get first non-empty child element
            first = None
            for c in list(getattr(root, "children", [])):
                # Skip NavigableStrings that are pure whitespace
                if hasattr(c, "name") and c.name is None:
                    s = str(c).strip()
                    if not s:
                        continue
                    first = c
                    break
                if hasattr(c, "name"):
                    # Skip void/empty containers
                    txt_probe = (c.get_text(strip=True) if hasattr(c, "get_text") else "")
                    if not txt_probe and c.name not in ("img", "hr", "br"):
                        # Empty container, peel it
                        try:
                            c.decompose()
                            changed = True
                            break
                        except Exception:
                            continue
                    first = c
                    break
            if first is None:
                break

            # If it's a text node that matches a leading stop, extract it
            if hasattr(first, "name") and first.name is None:
                s = str(first).strip()
                if (_V4_LEADING_META_RE.match(s) or _V4_LEADING_POSTED_RE.match(s)
                    or _V4_LEADING_IN_CAT_RE.match(s) or _V4_LEADING_BY_AUTHOR_RE.match(s)
                    or _V4_LEADING_ADMIN_RE.match(s)):
                    try:
                        first.extract()
                        changed = True
                    except Exception:
                        break
                else:
                    break
                if changed:
                    continue
                break

            # Element node — check its text + class
            txt = first.get_text(" ", strip=True) if hasattr(first, "get_text") else ""
            cls = " ".join((first.attrs.get("class") or [])) if hasattr(first, "attrs") else ""
            hit = False
            if cls and _V3b_SKIP_CLASSES.search(cls):
                hit = True
            elif txt and len(txt) <= 200:
                if (_V4_LEADING_META_RE.match(txt) or _V4_LEADING_POSTED_RE.match(txt)
                    or _V4_LEADING_IN_CAT_RE.match(txt) or _V4_LEADING_BY_AUTHOR_RE.match(txt)
                    or _V4_LEADING_ADMIN_RE.match(txt)):
                    hit = True
                else:
                    # Composite leading block: "By Posted April 20, 2026 In News"
                    # (all on one line, from mk-blog-meta theme)
                    if _re_v4.match(
                        r"^\s*by\s+posted\s+(?:january|february|march|april|"
                        r"may|june|july|august|september|october|november|"
                        r"december)\s+\d{1,2},?\s+\d{4}\s+in\s+[a-z ,&-]+\s*$",
                        txt, _re_v4.I,
                    ):
                        hit = True
            if hit:
                try:
                    first.decompose()
                    changed = True
                except Exception:
                    break
            else:
                break
            if not changed:
                break
    return soup


# Re-wrap clean_release_html: v3 already wrapped it once. We wrap again so
# the new pipeline is:  raw -> v1 (base) -> v3 trailing -> v4 leading
try:
    _v4_prev_clean = clean_release_html  # noqa: F821
except NameError:
    _v4_prev_clean = None

if _v4_prev_clean is not None:
    def clean_release_html(html_str, source_url=""):  # noqa: F811
        cleaned = _v4_prev_clean(html_str, source_url)
        if not cleaned:
            return cleaned
        try:
            soup = _BS4_V4(cleaned, "html.parser")
        except Exception:
            return cleaned
        try:
            _v4_strip_leading_chrome(soup)
        except Exception:
            pass
        return str(soup)
# END QUALITY_V4_PATCH


# ============================================================================
# QUALITY_V5_PATCH  (2026-04-25)  — position-aware trailing-chrome cleanup
# Further chrome cleanup triggered by Steve's spot-check:
#   * SX.CN 499c0c85 : trailing Recent posts / Newsletter / Contact Us /
#     Lorem ipsum Elementor widgets leaking into body
#   * NOM.CN bc0ab344: trailing Corporate Presentation / NI 43-101 /
#     Subscribe / Just take me to the Report buttons
#   * STCU.CN 665857da: mid-article "Share this story" + elementor
#     post-navigation "TAKE ME BACK" button (bdt-advanced-button)
#   * NINE.CN e0e704be: WP Rocket lazy-loaded images (data-lazy-src)
# ----------------------------------------------------------------------------
# Key mechanics over V3/V4:
#   A) position-aware trailing-cut:
#      for stopwords that only make sense as end-of-release chrome
#      (Recent posts, Newsletter, Contact Us, Corporate Presentation,
#      NI 43-101, Subscribe, etc.), a match is only treated as a
#      "trailing cut point" if it sits in the last 40% of the document.
#      Otherwise the matched widget is surgically decomposed (safe).
#   B) widget-class zap: decompose specific Elementor widget classes that
#      are always chrome in a press-release (elementor-location-popup,
#      elementor-widget-form, elementor-widget-post-navigation,
#      bdt-advanced-button, etc.).
#   C) lazy-src promoter: when <img src="data:image/svg..."> has a
#      data-lazy-src attribute, replace src with data-lazy-src's value.
#   D) SOURCE-marker truncator: ACCESS Newswire releases end with
#      <p>SOURCE: <Company></p>; everything after that paragraph at the
#      outermost-block level is chrome — decompose following siblings.
# ============================================================================

import re as _re_v5

try:
    from bs4 import BeautifulSoup as _BS4_V5
except Exception:
    _BS4_V5 = BeautifulSoup  # type: ignore[name-defined]

# Trailing-chrome stopwords (in addition to V4's list)
_V5_TRAILING_STOP_RE = _re_v5.compile(
    r"^(?:"
    r"newsletter|"
    r"contact\s+us|"
    r"corporate\s+presentation|"
    r"ni\s*[-]?\s*43[-\s]*101|"
    r"ni[-\s]*43[-\s]*101\s+technical\s+report|"
    r"just\s+take\s+me\s+to\s+the\s+report|"
    r"subscribe|"
    r"subscribe\s+to\s+our\s+newsletter|"
    r"send\s+message|"
    r"more\s+news\s+stories|"
    r"about\s+us|"
    r"lorem\s+ipsum.*|"
    r"get\s+the\s+latest\s+company\s+news[\w\s]*|"
    r"enter\s+your\s+details.*|"
    r"recent\s+posts?|"
    r"sign\s+up\s+for\s+our\s+news\s+alerts|"
    r"read\s+more|"
    r"read\s+more\s+news"
    r")\s*[.!:]?\s*$",
    _re_v5.I,
)

# Stopwords that can appear mid-content (not trailing): decompose widget only
_V5_WIDGET_LABEL_RE = _re_v5.compile(
    r"^\s*(?:"
    r"share\s+this\s+story|"
    r"share\s+this\s+release|"
    r"share\s+this\s+post"
    r")\s*[.!:]?\s*$",
    _re_v5.I,
)

# Widget classes that are ALWAYS chrome in a press-release context
_V5_WIDGET_CHROME_CLASSES = _re_v5.compile(
    r"(?:"
    r"elementor-location-popup|"
    r"elementor-widget-form|"
    r"elementor-widget-post-navigation|"
    r"elementor-widget-bdt-gravity-form|"
    r"bdt-advanced-button|"
    r"bdt-gravity-form-button|"
    r"elementor-post-navigation|"
    r"jet-listing-grid|"
    r"elementor-widget-jet-listing-grid|"
    r"jet-smart-listing"
    r")",
    _re_v5.I,
)


def _v5_outermost_block_ancestor(node):
    """Walk up from 'node' returning the outermost ancestor whose parent is a
    root/body-like element. Returns None if node is detached.
    """
    if node is None:
        return None
    cursor = node
    target = None
    for _ in range(30):
        try:
            parent = cursor.parent
        except Exception:
            parent = None
        if parent is None:
            return target
        pname = (getattr(parent, "name", "") or "").lower()
        if pname in ("body", "[document]", "article", "main", "html", ""):
            return cursor
        target = cursor
        cursor = parent
    return target


def _v5_nearest_widget_ancestor(node, max_levels=8):
    """Walk up at most max_levels looking for an element whose class contains
    'elementor-widget'. Returns the widget element or None.
    """
    if node is None:
        return None
    cursor = node
    for _ in range(max_levels):
        if cursor is None or getattr(cursor, "parent", None) is None:
            return None
        try:
            cls_attr = cursor.attrs.get("class") if hasattr(cursor, "attrs") else None
        except Exception:
            cls_attr = None
        if cls_attr:
            cls_str = " ".join(cls_attr) if isinstance(cls_attr, list) else str(cls_attr)
            if "elementor-widget" in cls_str.lower():
                return cursor
        cursor = cursor.parent
    return None


def _v5_strip_widgets_by_label(soup):
    """Decompose any <elementor-widget> whose visible text matches a short
    mid-content chrome label (e.g. "Share this story"). Does NOT touch
    siblings.
    """
    try:
        widgets = list(soup.select(".elementor-widget"))
    except Exception:
        return soup
    for widget in widgets:
        if widget.parent is None:
            continue
        try:
            txt = widget.get_text(" ", strip=True)
        except Exception:
            continue
        if not txt or len(txt) > 80:
            continue
        if _V5_WIDGET_LABEL_RE.match(txt):
            try:
                widget.decompose()
            except Exception:
                pass
    return soup


def _v5_strip_trailing_widget_chrome(soup):
    """For each V5 trailing-stopword hit, walk up to the outermost block
    ancestor and delete THAT ancestor + following siblings — BUT only
    when the match is in the last 40% of the document (to avoid nuking
    mid-content matches).
    """
    try:
        html_str = str(soup)
    except Exception:
        return soup
    total_len = max(1, len(html_str))
    cut_threshold = int(total_len * 0.55)  # match must be past 55% of doc

    candidates = []
    try:
        all_strings = list(soup.find_all(string=True))
    except Exception:
        return soup
    for el in all_strings:
        try:
            s = str(el).strip()
        except Exception:
            continue
        if not s:
            continue
        if _V5_TRAILING_STOP_RE.match(s):
            candidates.append(el)

    for el in candidates:
        try:
            if el.parent is None:
                continue
        except Exception:
            continue

        # Position check: find approximate position of this text in the doc
        try:
            s = str(el).strip()
        except Exception:
            continue
        match_pos = html_str.find(s)
        trailing = match_pos >= cut_threshold

        if trailing:
            # Walk up to outermost block ancestor and delete it + siblings
            target = _v5_outermost_block_ancestor(el.parent)
            if target is None or target.parent is None:
                continue
            try:
                siblings = list(target.parent.children)
            except Exception:
                continue
            non_empty = [
                s2 for s2 in siblings
                if getattr(s2, "name", None) or (
                    hasattr(s2, "strip") and str(s2).strip()
                )
            ]
            if len(non_empty) <= 1:
                # would nuke the body — fall back to widget decompose
                widget = _v5_nearest_widget_ancestor(el.parent)
                if widget is not None and widget.parent is not None:
                    try:
                        widget.decompose()
                    except Exception:
                        pass
                continue
            seen = False
            for sib in siblings:
                if sib is target:
                    seen = True
                if seen:
                    if hasattr(sib, "decompose"):
                        try:
                            sib.decompose()
                        except Exception:
                            pass
                    else:
                        try:
                            sib.extract()
                        except Exception:
                            pass
        else:
            # Mid-doc match: surgical decompose of the containing widget
            widget = _v5_nearest_widget_ancestor(el.parent)
            if widget is not None and widget.parent is not None:
                try:
                    widget.decompose()
                except Exception:
                    pass
    return soup


def _v5_strip_widget_chrome_classes(soup):
    """Decompose any element whose class list contains a V5 chrome class."""
    try:
        all_elems = list(soup.find_all(True))
    except Exception:
        return soup
    for el in all_elems:
        if el.parent is None:
            continue
        try:
            cls_attr = el.attrs.get("class") if hasattr(el, "attrs") else None
        except Exception:
            continue
        if not cls_attr:
            continue
        cls_str = " ".join(cls_attr) if isinstance(cls_attr, list) else str(cls_attr)
        if cls_str and _V5_WIDGET_CHROME_CLASSES.search(cls_str):
            try:
                el.decompose()
            except Exception:
                pass
    return soup


def _v5_promote_lazy_src(soup):
    """Promote data-lazy-src/srcset/sizes to src/srcset/sizes when src is a
    data:image placeholder (WP Rocket lazy-loading fix).
    """
    try:
        imgs = list(soup.find_all("img"))
    except Exception:
        return soup
    for im in imgs:
        try:
            src = im.attrs.get("src", "") or ""
        except Exception:
            continue
        lazy = im.attrs.get("data-lazy-src", "") or im.attrs.get("data-getimg", "") or im.attrs.get("data-src", "") or ""  # MTP_DATA_GETIMG_PROMOTER_V1
        if lazy and (
            not src
            or src.startswith("data:image")
            or src.startswith("data:application")
        ):
            im["src"] = lazy
        lazy_set = im.attrs.get("data-lazy-srcset", "") or ""
        if lazy_set:
            im["srcset"] = lazy_set
        lazy_sizes = im.attrs.get("data-lazy-sizes", "") or ""
        if lazy_sizes:
            im["sizes"] = lazy_sizes
        for k in ("data-lazy-src", "data-lazy-srcset", "data-lazy-sizes", "data-getimg", "data-src"):  # MTP_DATA_GETIMG_PROMOTER_V1
            if k in im.attrs:
                try:
                    del im.attrs[k]
                except Exception:
                    pass
    return soup


def _v5_truncate_after_source_marker(soup):
    """ACCESS Newswire releases end with <p>SOURCE: <company></p>; keep that
    paragraph but decompose all following siblings at the outermost-block
    level. Only fires when the paragraph text is exactly SOURCE: <name>
    (nothing else), so legitimate inline mentions of SOURCE: don't trigger.
    """
    try:
        paras = list(soup.find_all(["p", "div", "span"]))
    except Exception:
        return soup
    for p in paras:
        if p.parent is None:
            continue
        try:
            txt = p.get_text(" ", strip=True)
        except Exception:
            continue
        if not txt or len(txt) > 120:
            continue
        if _re_v5.match(
            r"^\s*SOURCE\s*:?\s*[A-Z][A-Za-z0-9 ,&.'()\-/]{2,100}\s*$",
            txt,
        ):
            target = _v5_outermost_block_ancestor(p)
            if target is None or target.parent is None:
                continue
            try:
                siblings = list(target.parent.children)
            except Exception:
                continue
            seen_target = False
            for sib in siblings:
                if sib is target:
                    seen_target = True
                    continue  # KEEP the SOURCE paragraph's container
                if seen_target:
                    if hasattr(sib, "decompose"):
                        try:
                            sib.decompose()
                        except Exception:
                            pass
                    else:
                        try:
                            sib.extract()
                        except Exception:
                            pass
            break
    return soup


# Re-wrap clean_release_html — chain v5 after v4
try:
    _v5_prev_clean = clean_release_html  # noqa: F821
except NameError:
    _v5_prev_clean = None

if _v5_prev_clean is not None:
    def clean_release_html(html_str, source_url=""):  # noqa: F811
        cleaned = _v5_prev_clean(html_str, source_url)
        if not cleaned:
            return cleaned
        try:
            soup = _BS4_V5(cleaned, "html.parser")
        except Exception:
            return cleaned
        try:
            _v5_promote_lazy_src(soup)
        except Exception:
            pass
        try:
            _v5_strip_widget_chrome_classes(soup)
        except Exception:
            pass
        try:
            _v5_strip_widgets_by_label(soup)
        except Exception:
            pass
        try:
            _v5_truncate_after_source_marker(soup)
        except Exception:
            pass
        try:
            _v5_strip_trailing_widget_chrome(soup)
        except Exception:
            pass
        return str(soup)
# END QUALITY_V5_PATCH
