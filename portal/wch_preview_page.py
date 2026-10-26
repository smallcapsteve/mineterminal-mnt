"""MNT_WCH_AI_PREVIEW_V1 (2026-10-26): /warrant-expiries-preview, the AI-reader hybrid for Warrants.

A preview of how Mine Terminal Pro's warrant-expiry events would change once the Warrants reader is switched to the AI
hybrid (plan: claude/AIREADER_HYBRID_PLAN_2026-10-22.md). It reads /var/lib/mnt-aireader-pub/wch_preview.db, built by
mnt-relay payloads/aidisp/wch_preview.py: the merged warrant changes run through this site's own financing gate, then
MTP's own apply_wch() for every financing whose expiry the live changes or the hybrid changes touch. Nothing live is
read or changed; the page is not linked and tells search engines not to index it.

Undo: remove this file, templates/warrant_expiries_preview.html and the MNT_WCH_AI_PREVIEW_V1 block in portal/serve.py."""
import json
import os
import sqlite3

from fastapi import Request
from fastapi.responses import HTMLResponse

PREVIEW_DB = os.environ.get("MNT_WCH_PREVIEW_DB", "/var/lib/mnt-aireader-pub/wch_preview.db")
OUTCOMES = {
    "new_change": "Moved by the AI reader only",
    "different": "Moved differently",
    "change_dropped": "Live change not kept",
    "retired": "Retired (all exercised) by the AI reader",
    "unretired": "Live retirement not kept",
    "same": "Same as today",
}
_SHOW = ("changed", "all")
_LABELS = ("agreed", "AI-read")


def _conn():
    if not os.path.exists(PREVIEW_DB):
        return None
    c = sqlite3.connect("file:%s?mode=ro" % PREVIEW_DB, uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    if not c.execute("SELECT 1 FROM sqlite_master WHERE name='ai_warrant_events'").fetchone():
        c.close()
        return None
    return c


def _money(v, cur):
    if v in (None, ""):
        return ""
    v = float(v)
    s = "%.1fM" % (v / 1e6) if v >= 1e6 else "%.0fK" % (v / 1e3) if v >= 1e3 else "%.0f" % v
    return ("US$" if (cur or "").upper() == "USD" else "$") + s


def _price(v, cur):
    if v in (None, ""):
        return "price not read"
    return ("US$" if (cur or "").upper() == "USD" else "$") + ("%.3f" % float(v)).rstrip("0").rstrip(".")


def register(app, templates):
    from portal import auth
    from portal.app import _paginate, _PAGE_SIZE, _ticker_to_name

    @app.get("/warrant-expiries-preview", response_class=HTMLResponse)
    def warrant_expiries_preview(request: Request, ticker: str | None = None, show: str = "changed", outcome: str = "",
                                 label: str = "", page: int = 1):
        show = show if show in _SHOW else "changed"
        outcome = outcome if outcome in OUTCOMES else ""
        label = label if label in _LABELS else ""
        ctx = {"request": request, "is_admin": auth.is_logged_in(request), "page": "wexpreview", "rows": [],
               "tickers": [], "selected_ticker": ticker or "", "show": show, "outcome": outcome, "label": label,
               "outcomes": OUTCOMES, "counts": {}, "stats": {}, "built_at": None, "total_filtered": 0, "pages": 1,
               "page_no": 1, "pager_url": "/warrant-expiries-preview", "pager_qs": ""}
        conn = _conn()
        if conn is None:
            resp = templates.TemplateResponse(request, "warrant_expiries_preview.html", ctx)
            resp.headers["X-Robots-Tag"] = "noindex, nofollow"
            return resp
        try:
            where, args = ["(in_window_live = 1 OR in_window_ai = 1)"], []
            if show == "changed":
                where.append("outcome <> 'same'")
            for col, val in (("ticker", ticker), ("outcome", outcome), ("ai_label", label)):
                if val:
                    where.append(col + " = ?")
                    args.append(val)
            clause = " AND ".join(where)
            total_filtered = conn.execute("SELECT COUNT(*) FROM ai_warrant_events WHERE " + clause, args).fetchone()[0]
            pages, page_no, off = _paginate(total_filtered, page)
            rows = []
            for r in conn.execute("SELECT * FROM ai_warrant_events WHERE " + clause +
                                  " ORDER BY MIN(CASE WHEN in_window_live=1 THEN live_date ELSE '9999' END, "
                                  "CASE WHEN in_window_ai=1 THEN ai_date ELSE '9999' END), ticker LIMIT ? OFFSET ?",
                                  args + [_PAGE_SIZE, off]).fetchall():
                d = dict(r)
                d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
                d["fin_txt"] = "%s financing closed %s, %d-month warrants at %s" % (
                    _money(d["gross"], d["currency"]) or "Unsized", d["closed"], d["term_months"] or 0,
                    _price(d["strike"], d["currency"]))
                d["outcome_label"] = OUTCOMES.get(d["outcome"], d["outcome"])
                d["ai_url"] = ("/news/%s/%s" % ((d["ticker"] or "").lower(), d["ai_slug"])) if d.get("ai_slug") else ""
                rows.append(d)
            counts = {k: v for k, v in conn.execute(
                "SELECT outcome, COUNT(*) FROM ai_warrant_events WHERE in_window_live = 1 OR in_window_ai = 1 GROUP BY 1")}
            meta = {k: v for k, v in conn.execute("SELECT k, v FROM preview_meta")}
            ctx.update(rows=rows, total_filtered=total_filtered, pages=pages, page_no=page_no, counts=counts,
                       stats=json.loads(meta.get("wch_stats") or "{}"), built_at=meta.get("wch_built_at"),
                       tickers=[x[0] for x in conn.execute(
                           "SELECT DISTINCT ticker FROM ai_warrant_events WHERE (in_window_live = 1 OR in_window_ai = 1) "
                           "AND ticker IS NOT NULL ORDER BY ticker")],
                       pager_qs="".join("&%s=%s" % (k, v) for k, v in (("ticker", ticker), ("show", show),
                                                                       ("outcome", outcome), ("label", label)) if v))
        finally:
            conn.close()
        resp = templates.TemplateResponse(request, "warrant_expiries_preview.html", ctx)
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp
