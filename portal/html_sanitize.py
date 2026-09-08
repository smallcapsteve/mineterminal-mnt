"""Allow-list HTML sanitiser for stored newswire content (B20).

Applied at ingest, so the stored copy in events.raw_html is clean, and again
as the last stage of clean_release_html, so the 15,747 rows already stored
render safely without being rewritten.

Deliberately runs AFTER the cosmetic V1-V5 scrubbers in the render path:
those key off `class` and `data-widget_type`, so sanitising first would
break related-posts stripping. `class` is therefore kept in the allow-list.
"""
from __future__ import annotations

import re

import nh3

# Structural tags a press release legitimately uses. Everything else is
# dropped (its text content is kept, which is what nh3 does by default for
# non-`clean_content_tags`).
ALLOWED_TAGS = {
    "p", "br", "hr", "div", "span", "section", "article", "main",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "strike", "small", "mark",
    "sub", "sup", "abbr", "cite", "q", "blockquote", "pre", "code",
    "ul", "ol", "li", "dl", "dt", "dd",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption",
    "colgroup", "col",
    "a", "img", "figure", "figcaption",
}

# Tags whose *contents* are discarded too, not just the tag itself.
#
# `form` is deliberately NOT here. ASP.NET WebForms wraps the entire page body
# in a single <form runat="server">, so treating form as content-destroying
# deletes the whole article: measured against the live corpus it removed 501
# <td>, 479 <p> and 445 <span> from one release alone. Same reasoning for
# input/button/select/textarea - they are simply left out of ALLOWED_TAGS, so
# the tag is stripped and any text inside it survives.
CLEAN_CONTENT_TAGS = {"script", "style", "iframe", "object", "embed",
                      "noscript", "template", "svg", "math"}

ALLOWED_ATTRIBUTES = {
    "*": {"class", "id", "title", "dir", "lang", "style"},
    "a": {"href", "target", "name"},  # `rel` is set by link_rel=
    "img": {"src", "alt", "width", "height", "srcset", "sizes", "loading"},
    "td": {"colspan", "rowspan", "align", "valign", "width"},
    "th": {"colspan", "rowspan", "align", "valign", "width", "scope"},
    "table": {"width", "border", "cellpadding", "cellspacing", "align"},
    "col": {"span", "width"},
    "colgroup": {"span", "width"},
    "ol": {"start", "type"},
}

ALLOWED_URL_SCHEMES = {"http", "https", "mailto", "tel"}

# A style attribute is dropped entirely if it contains any of these. CSS is
# not parsed, so anything that could smuggle a URL or an expression goes.
_DANGEROUS_STYLE = re.compile(
    r"(?:javascript\s*:|expression\s*\(|url\s*\(|@import|behaviou?r\s*:|-moz-binding)",
    re.I,
)
_STYLE_ATTR = re.compile(r"""\sstyle\s*=\s*(?P<q>["'])(?P<val>.*?)(?P=q)""",
                         re.I | re.DOTALL)


def _strip_dangerous_styles(html: str) -> str:
    """nh3 passes `style` through verbatim, so screen the values ourselves."""
    def _repl(m: re.Match) -> str:
        return "" if _DANGEROUS_STYLE.search(m.group("val")) else m.group(0)
    return _STYLE_ATTR.sub(_repl, html)


def sanitize_release_html(html: str | None) -> str:
    """Return `html` with scripts, event handlers and hostile URLs removed."""
    if not html:
        return html or ""
    try:
        pre = _strip_dangerous_styles(html)
        return nh3.clean(
            pre,
            tags=ALLOWED_TAGS,
            clean_content_tags=CLEAN_CONTENT_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            url_schemes=ALLOWED_URL_SCHEMES,
            link_rel="noopener noreferrer",
            strip_comments=True,
        )
    except Exception:
        # Never let a sanitiser failure pass raw markup through. The config is
        # smoke-tested at import (below), so reaching here means bad *input*,
        # not bad config - fall back to nh3's own defaults, which are strict.
        return nh3.clean(html)


def _smoke_test() -> None:
    """Fail loudly at import if the allow-list config is invalid.

    Without this, a ValueError from nh3.clean is caught by the except above
    and the module quietly degrades to nh3 defaults - sanitising correctly
    but discarding tables, classes and the cosmetic scrubbers' hooks.
    """
    probe = ('<p class="x" style="text-align:center">t</p>'
             '<table><tr><td>c</td></tr></table>'
             # ASP.NET wraps whole pages in one <form>; content inside it must
             # survive. Regression guard for the 2026-09-08 measurement.
             '<form><table><tr><td>inform</td></tr></table></form>'
             '<script>alert(1)</script><img src=x onerror="alert(1)">')
    out = nh3.clean(
        probe, tags=ALLOWED_TAGS, clean_content_tags=CLEAN_CONTENT_TAGS,
        attributes=ALLOWED_ATTRIBUTES, url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer", strip_comments=True,
    )
    for forbid in ("<script", "onerror", "alert(1)"):
        if forbid in out:
            raise RuntimeError(f"sanitizer let through {forbid!r}: {out!r}")
    for expect in ('class="x"', "text-align:center", "<td>", "inform"):
        if expect not in out:
            raise RuntimeError(
                f"sanitizer config rejected {expect!r}; got {out!r}"
            )


_smoke_test()
