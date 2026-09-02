"""MNT News API v1 — read-only JSON for cross-site consumption (e.g. MTP).

Three endpoints, all GET, all CORS-allowed:
  /api/v1/news/recent              list recent approved articles
  /api/v1/news/by-ticker/{ticker}  list articles for one ticker
  /api/v1/news/article/{event_id}  single article with cleaned full HTML body

Registered from portal.app via news_api.register(app). Only depends on
portal.text_helpers (clean_release_html, smart_title) and a sqlite3
connection at the standard portal DB path.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from portal.text_helpers import clean_release_html, smart_title

DB_PATH = "/opt/mnt/app/portal/portal.db"
SITE_BASE = "https://miningnewsterminal.com"
CORS_ORIGIN = "*"  # public read-only feed

_IMG_RE = re.compile(r'<img[^>]+src=[\'"]([^\'"]+)[\'"]', re.I)
_CATEGORY_LABELS = {
    "drill": "Drill Results",
    "fin": "Financing",
    "rsrc": "Resource Estimate",
    "mna": "M&A",
    "perm": "Permitting",
    "earn": "Earnings",
    "ops": "Operations",
    "corp": "Corporate",
}


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout = 30000")
    return c


def _first_img(html: str) -> Optional[str]:
    if not html:
        return None
    m = _IMG_RE.search(html)
    if not m:
        return None
    src = m.group(1).strip()
    if src.startswith(("data:", "javascript:")):
        return None
    return src


def _excerpt(row: sqlite3.Row, max_len: int = 280) -> str:
    s = (row["raw_excerpt"] or "").strip()
    if not s:
        s = (row["raw_body"] or "").strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


def _categories(raw: Optional[str]) -> list[dict[str, str]]:
    if not raw:
        return []
    out = []
    for code in [c.strip() for c in raw.split(",") if c.strip()]:
        out.append({"code": code, "label": _CATEGORY_LABELS.get(code, code)})
    return out


def _row_to_card(row: sqlite3.Row) -> dict[str, Any]:
    """Light-weight article card (for list views)."""
    ticker = (row["ticker"] or "").strip()
    slug = (row["slug"] or "release").strip()
    return {
        "event_id": row["event_id"],
        "ticker": ticker,
        "headline": smart_title(row["raw_headline"] or "") if row["raw_headline"] else "",
        "source_name": row["source_name"] or "",
        "source_url": row["source_url"] or "",
        "published_at": row["published_at"] or row["classified_at"] or "",
        "slug": slug,
        "url": f"{SITE_BASE}/news/{ticker.lower()}/{slug}" if ticker and slug else None,
        "categories": _categories(row["categories"]),
        "excerpt": _excerpt(row),
        "thumbnail_url": _first_img(row["raw_html"] or ""),
    }


def _row_to_full(row: sqlite3.Row) -> dict[str, Any]:
    """Full article including cleaned body HTML."""
    card = _row_to_card(row)
    body = ""
    if row["raw_html"]:
        try:
            body = clean_release_html(row["raw_html"], row["source_url"] or "")
        except Exception:
            body = row["raw_html"]
    elif row["raw_body"]:
        body = "<div>" + (row["raw_body"] or "").replace("\n\n", "</div><div>") + "</div>"
    card["body_html"] = body
    return card


def _json(payload: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(
        payload,
        status_code=status,
        headers={
            "Access-Control-Allow-Origin": CORS_ORIGIN,
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Cache-Control": "public, max-age=60",
            "X-MNT-API-Version": "1",
        },
    )


def register(app) -> None:
    @app.get("/api/v1/news/recent")
    def news_recent(limit: int = 50, offset: int = 0, category: Optional[str] = None):
        limit = max(1, min(int(limit or 50), 200))
        offset = max(0, int(offset or 0))
        con = _conn()
        sql = (
            "SELECT * FROM events "
            "WHERE review_status IN ('auto_approved','approved') "
            "  AND coalesce(raw_headline,'') <> '' "
        )
        params: list[Any] = []
        if category:
            sql += " AND categories LIKE ? "
            params.append(f"%{category}%")
        sql += " ORDER BY published_at DESC, ingested_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = con.execute(sql, params).fetchall()
        return _json({
            "ok": True,
            "count": len(rows),
            "limit": limit,
            "offset": offset,
            "category": category,
            "items": [_row_to_card(r) for r in rows],
        })

    @app.get("/api/v1/news/by-ticker/{ticker}")
    def news_by_ticker(ticker: str, limit: int = 20, offset: int = 0):
        limit = max(1, min(int(limit or 20), 200))
        offset = max(0, int(offset or 0))
        ticker_u = (ticker or "").strip().upper()
        if not ticker_u:
            raise HTTPException(400, "ticker required")
        con = _conn()
        # Match exact ticker AND bare-symbol prefix (to handle suffix variations).
        bare = ticker_u.split(".")[0]
        rows = con.execute(
            "SELECT * FROM events "
            "WHERE review_status IN ('auto_approved','approved') "
            "  AND (upper(ticker) = ? OR upper(ticker) LIKE ?) "
            "  AND coalesce(raw_headline,'') <> '' "
            "ORDER BY published_at DESC, ingested_at DESC LIMIT ? OFFSET ?",
            (ticker_u, bare + ".%", limit, offset),
        ).fetchall()
        return _json({
            "ok": True,
            "ticker": ticker_u,
            "count": len(rows),
            "limit": limit,
            "offset": offset,
            "items": [_row_to_card(r) for r in rows],
        })

    @app.get("/api/v1/news/article/{event_id}")
    def news_article(event_id: str):
        if not event_id or len(event_id) < 6:
            raise HTTPException(400, "event_id required")
        con = _conn()
        row = con.execute(
            "SELECT * FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if not row:
            return _json({"ok": False, "error": "not_found"}, status=404)
        return _json({"ok": True, "article": _row_to_full(row)})
