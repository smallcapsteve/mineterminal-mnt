"""
Admin API for the mining portal.

Drop this file into:
    /opt/mnt/app/portal/admin.py

Then in /opt/mnt/app/portal/app.py add ONE line near the other route registrations:
    from portal.admin import router as admin_router
    app.include_router(admin_router)

Restart:
    systemctl restart mnt-portal

Authentication: same HMAC scheme as /ingest/{event_type}.
Headers required:
    X-MNT-Timestamp: <unix_seconds>
    X-MNT-Sig:       sha256=<hex>
Sig base = f"{ts}.".encode() + body_bytes
HMAC key = MNT_HMAC_SECRET env var
Skew window = 5 minutes
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import logging
import os
import time
from typing import Any, Dict, Iterable, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

SKEW_SECONDS = 300


def _hmac_secret() -> bytes:
    secret = os.environ.get("MNT_HMAC_SECRET", "")
    if not secret:
        raise HTTPException(500, "server misconfigured: MNT_HMAC_SECRET missing")
    return secret.encode("utf-8")


def _verify_hmac(request: Request, body: bytes) -> None:
    ts = request.headers.get("X-MNT-Timestamp", "")
    sig = request.headers.get("X-MNT-Sig", "")
    if not ts or not sig:
        raise HTTPException(401, "missing X-MNT-Timestamp / X-MNT-Sig")
    try:
        ts_int = int(ts)
    except ValueError:
        raise HTTPException(401, "bad timestamp")
    if abs(time.time() - ts_int) > SKEW_SECONDS:
        raise HTTPException(401, "timestamp skew")
    base = f"{ts}.".encode("utf-8") + body
    expected = "sha256=" + hmac.new(_hmac_secret(), base, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(401, "bad signature")


@router.post("/scrape")
async def admin_scrape(request: Request) -> JSONResponse:
    body = await request.body()
    _verify_hmac(request, body)

    try:
        payload: Dict[str, Any] = json.loads(body) if body else {}
    except json.JSONDecodeError:
        raise HTTPException(400, "invalid JSON body")

    ticker: str = (payload.get("ticker") or "").strip()
    source: str = (payload.get("source") or "").strip()
    source_params: Dict[str, Any] = payload.get("source_params") or {}
    try:
        limit = int(payload.get("limit") or 50)
    except (TypeError, ValueError):
        raise HTTPException(400, "limit must be an integer")
    if not source:
        raise HTTPException(400, "source is required")
    if not isinstance(source_params, dict):
        raise HTTPException(400, "source_params must be an object")

    src_mod = _load_source(source)
    cfg = {"ticker": ticker, "source": source, "source_params": source_params}

    db = _lazy_import("portal.db")
    backfill = _lazy_import("pipeline.backfill", required=False)

    ingested = 0
    skipped = 0
    errors: List[Dict[str, Any]] = []
    headlines: List[Dict[str, Any]] = []

    try:
        summaries: Iterable[Dict[str, Any]] = src_mod.list_recent(cfg, limit=limit)
    except Exception as e:
        log.exception("list_recent failed for %s/%s", ticker, source)
        return JSONResponse(
            {"ok": False, "stage": "list_recent", "error": str(e)[:500]},
            status_code=500,
        )

    for summary in summaries:
        try:
            full = src_mod.fetch_body(summary)
        except Exception as e:
            errors.append({
                "summary_url": summary.get("source_url"),
                "stage": "fetch_body",
                "error": str(e)[:300],
            })
            continue

        url = full.get("source_url") or summary.get("source_url")
        published_at = full.get("published_at") or summary.get("published_at")
        try:
            event_id = src_mod.event_id_for(url, published_at)
        except Exception as e:
            errors.append({
                "summary_url": url,
                "stage": "event_id_for",
                "error": str(e)[:300],
            })
            continue

        env = {
            "event_type": "news_article",
            "event_id": event_id,
            "ticker": full.get("ticker") or summary.get("ticker") or ticker,
            "source": source,
            "source_url": url,
            "published_at": published_at,
            "raw_headline": full.get("raw_headline") or summary.get("raw_headline"),
            "raw_body": _strip_leading_headline(full.get("raw_body"), full.get("raw_headline") or summary.get("raw_headline")),
            "raw_html": _strip_imgs(full.get("raw_html")),
            "raw_excerpt": full.get("raw_excerpt"),
            "review_status": "auto_approved",
        }

        try:
            if backfill is not None and hasattr(backfill, "_row_from_envelope"):
                row = backfill._row_from_envelope(env)
            else:
                row = env
            result = db.upsert_event(row)
            is_new = _decide_is_new(result)
        except Exception as e:
            errors.append({
                "summary_url": url,
                "stage": "upsert_event",
                "error": str(e)[:300],
            })
            continue

        if is_new:
            ingested += 1
        else:
            skipped += 1

        if env["raw_headline"] and len(headlines) < 5:
            headlines.append({"headline": env["raw_headline"], "url": url})

    return JSONResponse({
        "ok": True,
        "ticker": ticker,
        "source": source,
        "limit": limit,
        "ingested": ingested,
        "skipped": skipped,
        "errors": errors[:10],
        "error_count": len(errors),
        "sample_headlines": headlines,
    })


@router.get("/status")
async def admin_status(
    request: Request,
    ticker: str = "",
    since_minutes: int = 60,
    limit: int = 20,
) -> JSONResponse:
    _verify_hmac(request, b"")

    db = _lazy_import("portal.db")

    try:
        rows = db.list_events_admin(ticker=ticker or None, limit=limit)
    except Exception as e:
        log.warning("list_events_admin failed: %s", e)
        rows = []

    return JSONResponse({
        "ok": True,
        "ticker": ticker or None,
        "since_minutes": since_minutes,
        "count": len(rows),
        "events": [_row_to_dict(r) for r in rows],
    })


_ALLOWED_SOURCES = {
    "accesswire", "cnw", "companysite",
    "globenewswire", "globenewswire_gnews", "company_ir_wp", "newsfile", "selfhosted",
}


def _load_source(name: str):
    if name not in _ALLOWED_SOURCES:
        raise HTTPException(400, f"unknown source: {name}")
    try:
        return importlib.import_module(f"sources.{name}")
    except ImportError as e:
        raise HTTPException(500, f"failed to import sources.{name}: {e}")


def _lazy_import(modname: str, required: bool = True):
    try:
        return importlib.import_module(modname)
    except ImportError:
        if required:
            raise HTTPException(500, f"module not importable: {modname}")
        return None


def _decide_is_new(result: Any) -> bool:
    if isinstance(result, tuple) and len(result) >= 2:
        return bool(result[1])
    if isinstance(result, dict) and "is_new" in result:
        return bool(result["is_new"])
    if isinstance(result, bool):
        return result
    return True


def _row_to_dict(r: Any) -> Dict[str, Any]:
    # Normalize sqlite3.Row / dict / attr-object to a plain dict first.
    try:
        d = dict(r)
    except (TypeError, ValueError):
        d = None
    if isinstance(d, dict):
        return {
            "event_id": d.get("event_id"),
            "ticker": d.get("ticker"),
            "headline": d.get("raw_headline") or d.get("headline"),
            "published_at": str(d.get("published_at")) if d.get("published_at") else None,
            "source": d.get("source"),
            "source_url": d.get("source_url"),
        }
    return {
        "event_id": getattr(r, "event_id", None),
        "ticker": getattr(r, "ticker", None),
        "headline": getattr(r, "raw_headline", None) or getattr(r, "headline", None),
        "published_at": str(getattr(r, "published_at", "") or "") or None,
        "source": getattr(r, "source", None),
        "source_url": getattr(r, "source_url", None),
    }


def _strip_leading_headline(body, headline):
    if not body or not headline:
        return body
    import re
    h = headline.strip()
    if not h:
        return body
    pattern = r"^\\s*" + re.escape(h) + r"\\s*[\\r\\n]+"
    return re.sub(pattern, "", body, count=1, flags=re.IGNORECASE)


def _strip_imgs(html):
    if not html: return html
    import re
    return re.sub(r"<img\\b[^>]*/?>", "", html, flags=re.IGNORECASE)
