"""MNT_DEV_AI_PREVIEW_V1 (2026-10-23): /mine-development-preview, the AI-reader hybrid for Mine Development.

A preview of what /mine-development would show once Mine Development is switched to the AI reader (plan:
claude/AIREADER_HYBRID_PLAN_2026-10-22.md). It reads `ai_mine_dev_events` from the AI harness's preview database
(/var/lib/mnt-aireader-pub/site_preview.db, written by `python -m aireader export dev`), never the live table, and it is
not linked from anywhere and tells search engines not to index it.

Each row carries ai_label:
  agreed   both the rules reader and the AI reader found the event
  AI-read  only the AI found it (shown with an "AI-read" badge)
  rules    the AI never read this release for Mine Development, so the rules' row stands as on the live page
Figures the two readers disagree on are left blank (`withheld`) and go to the review list.

Undo: remove this file and its register block in portal/serve.py (and templates/mine_development_preview.html);
the live page is untouched either way."""
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta

from fastapi import Request
from fastapi.responses import HTMLResponse

PREVIEW_DB = os.environ.get("MNT_AI_PREVIEW_DB", "/var/lib/mnt-aireader-pub/site_preview.db")
_SHOW = ("events", "all")
_STATUSES = ("achieved", "underway", "planned")
_LABELS = ("agreed", "AI-read", "rules")
log = logging.getLogger(__name__)


def _conn():
    if not os.path.exists(PREVIEW_DB):
        return None
    c = sqlite3.connect("file:%s?mode=ro" % PREVIEW_DB, uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    if not c.execute("SELECT 1 FROM sqlite_master WHERE name='ai_mine_dev_events'").fetchone():
        c.close()
        return None
    return c


def register(app, templates):
    from portal import auth
    from portal.app import _paginate, _PAGE_SIZE, _ticker_to_name
    from portal.mine_dev_publish import GROUP_LABELS, TYPE_LABELS

    @app.get("/mine-development-preview", response_class=HTMLResponse)
    def mine_development_preview(request: Request, ticker: str | None = None, days: int = 0, page: int = 1,
                                 group: str = "", type: str = "", status: str = "", label: str = ""):
        group = group if group in GROUP_LABELS else ""
        etype = type if type in TYPE_LABELS else ""
        status = status if status in _STATUSES else ""
        label = label if label in _LABELS else ""
        ctx = {"request": request, "is_admin": auth.is_logged_in(request), "page": "minedev",
               "rows": [], "total": 0, "releases": 0, "tickers": [], "selected_ticker": ticker or "",
               "days": days, "group": group, "etype": etype, "status": status, "label": label,
               "group_options": list(GROUP_LABELS.items()), "type_options": list(TYPE_LABELS.items()),
               "total_filtered": 0, "pages": 1, "page_no": 1, "pager_url": "/mine-development-preview", "pager_qs": "",
               "counts": {}, "built_at": None}
        conn = _conn()
        if conn is None:
            resp = templates.TemplateResponse(request, "mine_development_preview.html", ctx)
            resp.headers["X-Robots-Tag"] = "noindex, nofollow"
            return resp
        try:
            where, args = ["event_type IS NOT NULL"], []
            for col, val in (("ticker", ticker), ("event_group", group), ("event_type", etype), ("status", status),
                             ("ai_label", label)):
                if val:
                    where.append(col + " = ?")
                    args.append(val)
            if days and days > 0:
                where.append("published_at >= ?")
                args.append((datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d"))
            clause = " AND ".join(where)
            total_filtered = conn.execute("SELECT COUNT(*) FROM ai_mine_dev_events WHERE " + clause, args).fetchone()[0]
            pages, page_no, off = _paginate(total_filtered, page)
            rows = conn.execute(
                "SELECT event_id, ordinal, ticker, slug, raw_headline, published_at, event_type, event_group, mine, "
                "status, incident_kind, n_rows, ai_label, withheld FROM ai_mine_dev_events WHERE " + clause +
                " ORDER BY published_at DESC, event_id, ordinal LIMIT ? OFFSET ?", args + [_PAGE_SIZE, off]).fetchall()
            decorated, last = [], None
            for r in rows:
                d = dict(r)
                d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
                if d.get("ticker") and d.get("slug"):
                    d["url"] = "/news/%s/%s" % (d["ticker"].lower(), d["slug"])
                elif d.get("event_id"):
                    d["url"] = "/event/%s" % d["event_id"]
                else:
                    d["url"] = ""
                d["withheld"] = json.loads(d["withheld"]) if d.get("withheld") else []
                d["first_of_release"] = d.get("event_id") != last
                last = d.get("event_id")
                decorated.append(d)
            counts = {k: v for k, v in conn.execute("SELECT ai_label, COUNT(*) FROM ai_mine_dev_events GROUP BY 1")}
            meta = {k: v for k, v in conn.execute("SELECT k, v FROM preview_meta")}
            ctx.update(
                rows=decorated, total_filtered=total_filtered, pages=pages, page_no=page_no,
                total=sum(counts.values()), counts=counts, built_at=meta.get("dev_built_at"),
                releases=conn.execute("SELECT COUNT(DISTINCT event_id) FROM ai_mine_dev_events").fetchone()[0],
                tickers=[r[0] for r in conn.execute("SELECT DISTINCT ticker FROM ai_mine_dev_events "
                                                    "WHERE ticker IS NOT NULL ORDER BY ticker")],
                pager_qs="".join("&%s=%s" % (k, v) for k, v in (("ticker", ticker), ("days", days or ""),
                                                               ("group", group), ("type", etype), ("status", status),
                                                               ("label", label)) if v))
        finally:
            conn.close()
        resp = templates.TemplateResponse(request, "mine_development_preview.html", ctx)
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp
