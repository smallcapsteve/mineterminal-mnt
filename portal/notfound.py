"""UXFIX6_V1 (2026-11-09, UX sweep): a styled "Page not found" page for browsers instead of {"detail":"Not Found"}.

Registered from serve.py (two marked lines). Only a 404 for a browser request (Accept: text/html) outside /api/ is
changed; API paths, non-browser clients and every other status go through FastAPI's own handler unchanged. If the
template cannot render, a small static page is sent, so a missing page can never turn into a server error.
Undo: delete the two marked lines in serve.py (and this file), then reload the app.
"""
from fastapi.exception_handlers import http_exception_handler as _default_http_exception_handler
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException as _StarletteHTTPException

_FALLBACK = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
             "<meta name=viewport content='width=device-width,initial-scale=1'><title>Page not found</title></head>"
             "<body style='font:16px/1.5 system-ui,sans-serif;margin:40px 16px;color:#1a1a1a'><h1>Page not found</h1>"
             "<p>That page doesn't exist, or the link is out of date. <a href='/'>Go to the home page</a>.</p></body></html>")


def register(app, templates, ctx=None, site=""):
    @app.exception_handler(_StarletteHTTPException)
    async def _not_found(request, exc):
        if (exc.status_code == 404 and not request.url.path.startswith("/api/")
                and "text/html" in request.headers.get("accept", "")):
            try:
                c = ctx(request) if ctx else {}
                c = dict(c); c.setdefault("site_name", site)
                return templates.TemplateResponse(request, "404.html", c, status_code=404)
            except Exception:
                return HTMLResponse(_FALLBACK, status_code=404)
        return await _default_http_exception_handler(request, exc)
