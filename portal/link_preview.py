"""Link previews for every MNT page (LINK_PREVIEW_V1, 2026-09-16).

What a shared miningnewsterminal.com link shows in iMessage, Slack, X,
LinkedIn, Facebook, WhatsApp, Discord and Teams. The tag set, its order and the
share image layout follow MineTerminal Pro's seo.js exactly, so links from the
two sites look like one family.

The tags themselves live in templates/base.html. This module supplies:

- the Jinja globals base.html reads (LP_IMAGE, LP_DEFAULT_DESC, lp_canonical);
- /favicon.ico and /apple-touch-icon.png at the site root, which chat apps and
  browsers request without reading any HTML (both were 404 before).

Registered from portal/serve.py, like typeahead. If it is ever not registered,
base.html skips the whole block (it tests `lp_canonical is defined`) and the
site renders exactly as it did before, minus the previews.

Rollback: remove the two lines in serve.py and restart mnt-portal.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi.responses import FileResponse, Response

SITE = "https://miningnewsterminal.com"
IMAGE = SITE + "/static/og-default.png"
IMAGE_ALT = "MiningNewsTerminal - the junior mining news terminal"
DEFAULT_DESC = (
    "Real-time news for CSE, TSXV and TSX junior miners: news releases, drill "
    "results, resource estimates, financings, M&A and management changes."
)

# Query parameters that change what a page is about. Everything else (days=,
# has=, tracking tags) is dropped from the canonical address.
_KEEP = ("ticker", "cat", "q", "page")

_STATIC = Path(__file__).parent / "static"


def canonical(request=None) -> str:
    try:
        path = request.url.path or "/"
        qs = [(k, v) for k, v in request.query_params.multi_items()
              if k in _KEEP and v and not (k == "page" and v == "1")]
        return SITE + path + ("?" + urlencode(qs) if qs else "")
    except Exception:
        return SITE + "/"


def register(app, templates) -> None:
    g = templates.env.globals
    g["LP_IMAGE"] = IMAGE
    g["LP_IMAGE_ALT"] = IMAGE_ALT
    g["LP_DEFAULT_DESC"] = DEFAULT_DESC
    g["lp_canonical"] = canonical

    def _file(name, media_type):
        def _serve():
            p = _STATIC / name
            if not p.is_file():
                return Response(status_code=404)
            return FileResponse(p, media_type=media_type,
                                headers={"Cache-Control": "public, max-age=86400"})
        _serve.__name__ = "lp_" + name.replace(".", "_").replace("-", "_")
        return _serve

    app.add_api_route("/favicon.ico", _file("favicon.ico", "image/x-icon"),
                      methods=["GET", "HEAD"], include_in_schema=False)
    app.add_api_route("/apple-touch-icon.png", _file("apple-touch-icon.png", "image/png"),
                      methods=["GET", "HEAD"], include_in_schema=False)
