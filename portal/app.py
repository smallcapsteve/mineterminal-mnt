from __future__ import annotations
import json
import logging
import os
import re
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Header, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from portal import auth, db, ingest, backfill

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("portal")

BASE_DIR = Path(__file__).parent
app = FastAPI(
    title="MNT Portal",
    # B32 (2026-09-07): the interactive API docs published a browsable map of
    # every route, write endpoints included. Off in production.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# MNT_NEWS_API_V1_HOOK
try:
    from portal import news_api as _mnt_news_api  # noqa: E402
    _mnt_news_api.register(app)
except Exception as _e:  # pragma: no cover
    import logging as _lg; _lg.getLogger(__name__).exception('news_api register failed')

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

from portal.text_helpers import smart_title, clean_release_html
from portal.categorize import (
    CATEGORIES, CAT_TO_CODE, CODE_TO_CAT, parse_categories,
)
templates.env.filters["smart_title"] = smart_title
templates.env.filters["clean_html"] = clean_release_html


def _cat_chips(stored: str):
    """Jinja filter: pipe-delimited stored string -> [(code, name), ...]."""
    out = []
    if not stored:
        return out
    for name in parse_categories(stored):
        code = CAT_TO_CODE.get(name)
        if code:
            out.append((code, name))
    return out


templates.env.filters["cat_chips"] = _cat_chips

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def _startup() -> None:
    # OPSFIX item 5b (2026-10-05): this schema check took ~37 s on every start (it waits for the database write lock,
    # which the background jobs hold), and the worker served nothing meanwhile, so every restart or reload left MNT
    # unanswered for that long. The schema already exists, so the check now runs in the background.
    import threading as _t5, time as _tm5

    def _schema_and_backfill() -> None:
        t0 = _tm5.time()
        try:
            db.init_schema()
            n = backfill.run()
            if n:
                log.info("startup backfill: %d events", n)
        except Exception as e:
            log.exception("backfill failed: %s", e)
        log.info("startup schema check finished in %.1fs (in the background)", _tm5.time() - t0)

    _t5.Thread(target=_schema_and_backfill, name="schema-check", daemon=True).start()


# ----- public ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def feed(
    request: Request,
    ticker: str | None = None,
    cat: list[str] = Query(default=[]),
):
    tickers = db.list_tickers()
    # Resolve short-code filter selections to canonical category names.
    selected_codes = [c for c in cat if c in CODE_TO_CAT]
    selected_cat_names = [CODE_TO_CAT[c] for c in selected_codes]

    events = db.list_events(
        ticker=ticker,
        status="auto_approved",
        # MNT_TICKER_HISTORY_V1: the front page wants the newest 100; a ticker-filtered
        # view is being read as a company history, so give it the whole history (the
        # busiest ticker holds 183). Matches /api/v1/news/by-ticker, which caps at 500.
        limit=500 if ticker else 100,
        categories=selected_cat_names or None,
        columns=db.LIST_EVENT_COLUMNS,  # PERF_A14: skip the raw_* blobs
    )

    # Build category_counts: [(code, name, count), ...] in canonical order.
    raw_counts = dict(db.list_categories())  # name -> count
    category_counts = [
        (CAT_TO_CODE[name], name, raw_counts.get(name, 0))
        for name in CATEGORIES
        if raw_counts.get(name, 0) > 0
    ]

    return templates.TemplateResponse(request, "feed.html", {
        "request": request,
        "tickers": tickers,
        "events": events,
        "selected_ticker": ticker or "",
        "selected_cats": selected_codes,
        "category_counts": category_counts,
        "is_admin": auth.is_logged_in(request),
    })


@app.get("/event/{event_id}", response_class=HTMLResponse)
def event_detail(
    # EVENT_REDIRECT_NOCACHE_V1 — 302 + no-cache so corrected slugs don't get pinned
request: Request, event_id: str):
    """Legacy URL: 301-redirect to slug-based /news/{ticker}/{slug} for SEO."""
    row = db.get_event(event_id)
    if not row:
        raise HTTPException(404)
    ticker = (row["ticker"] or "unknown").lower()
    slug = row["slug"] or "release"
    return RedirectResponse(f"/news/{ticker}/{slug}", status_code=302, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})



@app.post("/ingest/{event_type}")
async def ingest_event(
    event_type: str,
    request: Request,
    x_mnt_timestamp: str | None = Header(default=None, alias="X-MNT-Timestamp"),
    x_mnt_signature: str | None = Header(default=None, alias="X-MNT-Signature"),
):
    body = await request.body()
    if not ingest.verify_hmac(body, x_mnt_timestamp, x_mnt_signature):
        log.warning("ingest: bad signature for %s", event_type)
        raise HTTPException(401, "bad signature")
    try:
        env = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "bad json")
    if env.get("event_type") != event_type:
        raise HTTPException(400, "event_type mismatch")
    row = backfill._row_from_envelope(env)
    if not row["event_id"]:
        raise HTTPException(400, "missing event_id")
    db.upsert_event(row)
    return JSONResponse({"ok": True, "event_id": row["event_id"]})


# ----- admin ----------------------------------------------------------
def _require_admin(request: Request) -> None:
    if not auth.is_logged_in(request):
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_form(request: Request, error: str | None = None):
    if auth.is_logged_in(request):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(request, "admin_login.html", {
        "request": request, "error": error,
    })


@app.post("/admin/login")
def admin_login(request: Request, password: str = Form(...)):
    if not auth.verify_password(password):
        return RedirectResponse("/admin/login?error=1", status_code=303)
    token = auth.make_session_token()
    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie(
        auth.SESSION_COOKIE, token,
        max_age=auth.SESSION_MAX_AGE,
        httponly=True, samesite="lax",
    )
    return resp


@app.post("/admin/logout")
def admin_logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(auth.SESSION_COOKIE)
    return resp


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, ticker: str | None = None, status: str | None = None):
    if not auth.is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    tickers = db.list_tickers()
    events = db.list_events_admin(ticker=ticker, status=status, limit=300)
    return templates.TemplateResponse(request, "admin.html", {
        "request": request,
        "tickers": tickers,
        "events": events,
        "selected_ticker": ticker or "",
        "selected_status": status or "",
        "state": status or "open",
        "is_admin": True,
    })


@app.post("/admin/events/bulk")
def admin_bulk_action(
    request: Request,
    action: str = Form(...),
    event_ids: list[str] = Form(default=[]),
):
    if not auth.is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    if action == "delete":
        db.delete_events(event_ids)
    elif action == "approve":
        db.set_status(event_ids, "auto_approved")
    elif action == "reject":
        db.set_status(event_ids, "rejected")
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/events/{event_id}/delete")
def admin_delete_one(request: Request, event_id: str):
    if not auth.is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    db.delete_events([event_id])
    return RedirectResponse("/admin", status_code=303)


@app.get("/healthz")
def healthz():
    return {"ok": True, "events": db.count_events()}



# ====== /financings tab (appended) ======
# financings_route_patch.py — append-only patch to portal/app.py
# Adds /financings route + helpers. Imports from portal.financing_extract
# at the top so fmt_money / fmt_warrant_summary are available.
from fastapi import Query
from fastapi.responses import HTMLResponse

# Lazy import — falls back to None formatting if module unavailable
try:
    from portal.financing_extract import fmt_money, fmt_warrant_summary  # type: ignore
except Exception:
    def fmt_money(n):
        if n is None:
            return None
        if n >= 1_000_000:
            return f"${n/1_000_000:.2f}M"
        if n >= 1_000:
            return f"${n/1_000:.0f}K"
        return f"${n:.0f}"

    def fmt_warrant_summary(unit_comp, strike, term_months):
        if not strike or not unit_comp:
            return None
        half = "half " if "half" in (unit_comp or "") else ""
        if term_months and term_months % 12 == 0:
            term = f"{term_months // 12}yr "
        elif term_months:
            term = f"{term_months}mo "
        else:
            term = ""
        return f"{half}{term}warrant at ${strike:.2f}".strip()


_FIN_STAGE = {"announcement": "Announced", "upsize": "Upsized", "amendment": "Terms changed",
              "tranche_close": "Tranche closed", "final_close": "Closed", "terminated": "Cancelled",
              "update": "Update", "mention": "Update"}


def _fin_releases(conn, rows):
    """FIN_DETAIL_V1: attach r["releases"] (oldest first) to each deal row. Reads the amount columns the
    FIN_V1 publisher adds when they exist; the legacy tables only have gross_total."""
    ids = [r["financing_id"] for r in rows if r.get("financing_id") is not None]
    for r in rows:
        r["releases"] = []
    if not ids:
        return
    cols = {c[1] for c in conn.execute("PRAGMA table_info(financing_events)")}
    extra = ", amount_offered, amount_this_close, amount_closed_total, is_duplicate" if "amount_offered" in cols else ""
    second = "second_financing_id" in cols
    if second:
        extra += ", second_financing_id, second_amount_this_close, second_amount_closed_total"
    by = {r["financing_id"]: r for r in rows}
    marks = ",".join("?" * len(ids))
    where = "financing_id IN (%s)" % marks + (" OR second_financing_id IN (%s)" % marks if second else "")
    q = ("SELECT event_id, financing_id, event_date, role, tranche_label, gross_total, unit_price, raw_headline%s "
         "FROM financing_events WHERE %s ORDER BY event_date, event_id") % (extra, where)
    for e in conn.execute(q, ids + ids if second else ids):
        e = dict(e)
        role = e.get("role") or ""
        closing = role in ("tranche_close", "final_close")
        # FIN_DETAIL_V2: a release that closed two separate deals is listed under both, with each deal's own figures
        targets = []
        if e.get("financing_id") in by:
            targets.append((e["financing_id"], False))
        if e.get("second_financing_id") in by and e.get("second_financing_id") != e.get("financing_id"):
            targets.append((e["second_financing_id"], True))
        for fid, is_second in targets:
            _fin_release_row(by[fid], e, role, closing, is_second)


def _fin_release_row(row, e, role, closing, is_second):
    """One line of a deal's release list (FIN_DETAIL_V2)."""
    if is_second:
        amt, tot = e.get("second_amount_this_close"), e.get("second_amount_closed_total")
    elif "amount_offered" in e:
        amt = e.get("amount_this_close") if closing else e.get("amount_offered")
        tot = e.get("amount_closed_total") if closing else None
    else:
        amt, tot = e.get("gross_total"), None
    stage = _FIN_STAGE.get(role, role.replace("_", " ").capitalize())
    if e.get("tranche_label") and closing and e["tranche_label"] != "final":
        stage += " (" + e["tranche_label"] + ")"
    row["releases"].append({
        "event_id": e["event_id"], "date": (e.get("event_date") or "")[:10], "stage": stage,
        "amount": fmt_money(amt) if amt else "",
        "total": fmt_money(tot) if tot and tot != amt else "",
        "price": "" if is_second else (("$%.3f" % e["unit_price"]) if e.get("unit_price") else ""),
        "headline": (e.get("raw_headline") or "")[:160], "copy": bool(e.get("is_duplicate"))})


@app.get("/financings", response_class=HTMLResponse)
def financings_page(
    request: Request,
    ticker: str | None = None,
    status: str | None = None,
    state: str | None = "all",
    page: int = 1,
):
    conn = db.get_conn()
    where, args = [], []
    if ticker:
        where.append("ticker = ?")
        args.append(ticker)
    if status:
        where.append("status = ?")
        args.append(status)
    # No implicit "status != 'mention'". It quietly removed 889 financings that
    # the Financings chip counts.
    # state = open | closed | all (mining lifecycle filter)
    from datetime import datetime as _dt_state, timedelta as _td_state
    cutoff_60d = (_dt_state.utcnow() - _td_state(days=60)).strftime("%Y-%m-%d")
    if state == "open":
        # Open: status in {announced, upsized, amended} AND last_update within 60 days
        where.append("(status IN ('announced','upsized','amended') AND last_update_at >= ?)")
        args.append(cutoff_60d)
    elif state == "closed":
        # Closed: explicit closed states OR stale announcements (>60d untouched)
        where.append("(status IN ('closed','tranche_closed','final_close','terminated') OR (status IN ('announced','upsized','amended') AND last_update_at < ?))")
        args.append(cutoff_60d)
    # else 'all' -> no extra filter
    sql = "SELECT * FROM financings"
    if where:
        sql += " WHERE " + " AND ".join(where)
    _cnt = "SELECT COUNT(*) FROM financings"
    if where:
        _cnt += " WHERE " + " AND ".join(where)
    total_filtered = conn.execute(_cnt, args).fetchone()[0]
    pages, page_no, _off = _paginate(total_filtered, page)
    sql += " ORDER BY last_update_at DESC, financing_id DESC LIMIT ? OFFSET ?"
    rows = list(conn.execute(sql, args + [_PAGE_SIZE, _off]))

    # Decorate rows with formatted amounts
    decorated = []
    for r in rows:
        d = dict(r)
        d["gross_announced_fmt"] = fmt_money(d.get("gross_announced"))
        d["gross_closed_fmt"] = fmt_money(d.get("gross_closed"))
        d["warrant_summary"] = fmt_warrant_summary(
            d.get("unit_comp"), d.get("warrant_strike"), d.get("warrant_term_months")
        )
        decorated.append(d)

    # FIN_DETAIL_V1 (2026-09-17): each deal row expands to the releases grouped into it
    _fin_releases(conn, decorated)

    # Side metrics
    total = conn.execute("SELECT COUNT(*) FROM financings").fetchone()[0]
    tickers = [r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM financings ORDER BY ticker"
    )]
    status_counts = list(conn.execute(
        "SELECT status, COUNT(*) FROM financings "
        "GROUP BY status ORDER BY 2 DESC"
    ))

    return templates.TemplateResponse(request, "financings.html", {
        "request": request,
        "rows": decorated,
        "total": total,
        "tickers": tickers,
        "status_counts": status_counts,
        "selected_ticker": ticker or "",
        "selected_status": status or "",
        # was `status or "open"` -- the wrong variable, so the state tabs
        # highlighted according to the status filter
        "state": state or "all",
        "total_filtered": total_filtered,
        "pages": pages,
        "page_no": page_no,
        "pager_url": "/financings",
        "pager_qs": (("&ticker=" + ticker) if ticker else "")
                    + (("&status=" + status) if status else "")
                    + (("&state=" + state) if state else ""),
        "is_admin": auth.is_logged_in(request),
    })


# ====== layout context patch (appended) ======
"""app_context_patch.py — append-only patch that monkey-patches the
existing /, /financings, /event/* responses to inject layout context
vars (now_str, latest_headline, latest_event_id, latest_news,
recent_financings, page) needed by the new base.html.
"""
import datetime as _dt

_orig_template_response = templates.TemplateResponse


def _now_str():
    return _dt.datetime.now().strftime("%A, %B %-d, %Y")


def _latest_news_data():
    """Returns (latest_headline, latest_event_id, [latest_news rows...])."""
    try:
        conn = db.get_conn()
        rows = list(conn.execute(
            "SELECT event_id, raw_headline, ticker, published_at "
            "FROM events WHERE review_status='auto_approved' "
            "ORDER BY published_at DESC LIMIT 12"
        ))
        if not rows:
            return None, None, []
        head = rows[0]
        return head["raw_headline"], head["event_id"], rows
    except Exception:
        return None, None, []


def _recent_financings_data():
    try:
        conn = db.get_conn()
        rows = list(conn.execute(
            """SELECT f.ticker, f.status, f.gross_announced, f.gross_closed,
                  fe.event_id AS last_event_id, fe.raw_headline AS last_headline
              FROM financings f
              LEFT JOIN financing_events fe
                ON fe.event_id = (
                  SELECT event_id FROM financing_events fe2
                  WHERE fe2.financing_id = f.financing_id
                    AND fe2.role IN ('announcement', 'upsize', 'tranche_close', 'final_close', 'amendment')
                  ORDER BY fe2.event_date DESC LIMIT 1
                )
              WHERE f.status != 'mention'
              ORDER BY f.last_update_at DESC LIMIT 8"""
        ))
        out = []
        for r in rows:
            d = dict(r)
            ga, gc = d.get("gross_announced"), d.get("gross_closed")
            def _fm(n):
                if n is None: return None
                if n >= 1_000_000: return f"${n/1_000_000:.2f}M"
                if n >= 1_000: return f"${n/1_000:.0f}K"
                return f"${n:.0f}"
            d["gross_announced_fmt"] = _fm(ga)
            d["gross_closed_fmt"] = _fm(gc)
            out.append(d)
        return out
    except Exception:
        return []


def _patched_template_response(*args, **kwargs):
    """Wrap TemplateResponse to inject layout context vars."""
    # Detect call style: TemplateResponse(request, "name", {ctx})
    # Or:                TemplateResponse("name", {"request": req, ...})
    ctx = None
    template_name = None
    if len(args) >= 2 and hasattr(args[0], "scope"):
        # request first, then name, then context
        template_name = args[1] if len(args) > 1 else kwargs.get("name")
        ctx = args[2] if len(args) > 2 else kwargs.get("context")
    elif args and isinstance(args[0], str):
        template_name = args[0]
        ctx = args[1] if len(args) > 1 else kwargs.get("context")
    else:
        return _orig_template_response(*args, **kwargs)

    if ctx is None:
        return _orig_template_response(*args, **kwargs)

    # Inject layout vars (only if not already set by caller)
    ctx.setdefault("now_str", _now_str())
    if "latest_headline" not in ctx or "latest_news" not in ctx:
        head, head_id, rows = _latest_news_data()
        ctx.setdefault("latest_headline", head)
        ctx.setdefault("latest_event_id", head_id)
        ctx.setdefault("latest_news", rows)
    ctx.setdefault("recent_financings", _recent_financings_data())
    # Page hint based on template name
    if "page" not in ctx and template_name:
        if template_name.startswith("feed"):
            ctx["page"] = "news"
        elif template_name.startswith("financ"):
            ctx["page"] = "financings"
        elif template_name.startswith("event"):
            ctx["page"] = "news"
        elif template_name.startswith("admin"):
            ctx["page"] = "admin"

    return _orig_template_response(*args, **kwargs)


templates.TemplateResponse = _patched_template_response


# ====== /search route (appended) ======
@app.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: str = "",
):
    q = (q or "").strip()
    rows = []
    if q:
        conn = db.get_conn()
        pattern = f"%{q}%"
        # Headline match boosted (search headlines first, then bodies if needed)
        rows = list(conn.execute(
            "SELECT * FROM events "
            "WHERE review_status='auto_approved' "
            "  AND (raw_headline LIKE ? OR raw_body LIKE ? OR ticker LIKE ?) "
            "ORDER BY published_at DESC LIMIT 200",
            (pattern, pattern, pattern),
        ))
    return templates.TemplateResponse(request, "search.html", {
        "request": request,
        "q": q,
        "events": rows,
        "page": "search",
        "is_admin": auth.is_logged_in(request),
    })


# ====== pretty_source Jinja filter (appended) ======
_SOURCE_PRETTY = {
    'company_ir_wp':  'Company Website',
    'company_site':   'Company Website',
    'companysite':    'Company Website',
    'company':        'Company Website',
    'wp_feed':        'Company Website',
    'newsfile':       'Newsfile',
    'cnw':            'CNW',
    'globenewswire':  'GlobeNewswire',
    'gnw':            'GlobeNewswire',
    'accesswire':     'Accesswire',
    'prnewswire':     'PR Newswire',
    'businesswire':   'BusinessWire',
    'sedar':          'SEDAR+',
    'sedarplus':      'SEDAR+',
}

def _pretty_source(name):
    if not name:
        return ''
    s = str(name).strip()
    key = s.lower().replace('-', '_').replace(' ', '_')
    if key in _SOURCE_PRETTY:
        return _SOURCE_PRETTY[key]
    # Strip suffix like 'companysite:athenagoldcorp.com' -> 'companysite'
    head = re.split(r'[:/@]', key, maxsplit=1)[0]
    if head in _SOURCE_PRETTY:
        return _SOURCE_PRETTY[head]
    # Substring fallback
    for k, v in _SOURCE_PRETTY.items():
        if k in key:
            return v
    return name

templates.env.filters['pretty_source'] = _pretty_source
# ====== end pretty_source ======


# ====== SEO additions (appended) ======
from fastapi.responses import PlainTextResponse, Response as _SeoResponse

_SITE_BASE = "https://miningnewsterminal.com"
_NONALNUM_SEO = re.compile(r"[^a-z0-9]+")


def _seo_slugify(s, max_len=80):
    if not s:
        return ""
    s = str(s).lower()
    s = _NONALNUM_SEO.sub("-", s).strip("-")
    return s[:max_len].rstrip("-")


def _seo_meta_description(text, max_len=155):
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", "", str(text))  # strip HTML
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= max_len:
        return t
    return t[:max_len].rsplit(" ", 1)[0] + "…"


@app.get("/news/{ticker}/{slug}", response_class=HTMLResponse)
def news_article(request: Request, ticker: str, slug: str):
    """Slug-based article URL — primary canonical URL for SEO."""
    conn = db.get_conn()
    row = conn.execute(
        "SELECT * FROM events WHERE LOWER(ticker)=? AND slug=? "
        "AND review_status='auto_approved' LIMIT 1",
        (ticker.lower(), slug.lower()),
    ).fetchone()
    if not row:
        # SLUGALIAS_V1 (2026-09-25): an address a release used to have forwards to the one it has now.
        try:
            moved = conn.execute(
                "SELECT e.ticker, e.slug FROM event_slug_aliases a JOIN events e ON e.event_id = a.event_id "
                "WHERE a.ticker=? AND a.old_slug=? AND e.review_status='auto_approved' LIMIT 1",
                (ticker.lower(), slug.lower()),
            ).fetchone()
        except Exception:  # noqa: BLE001 - no alias table yet: plain 404 as before
            moved = None
        if moved and moved[1] and (moved[1] != slug.lower() or (moved[0] or '').lower() != ticker.lower()):   # TICKER_RENAME_V1: a renamed ticker forwards too
            return RedirectResponse(f"/news/{moved[0].lower()}/{moved[1]}", status_code=301)
        raise HTTPException(404)
    canonical = f"{_SITE_BASE}/news/{ticker.lower()}/{slug}"
    desc = _seo_meta_description(row["raw_body"] or row["raw_excerpt"] or "")
    return templates.TemplateResponse(request, "event.html", {
        "request": request,
        "event": row,
        "is_admin": auth.is_logged_in(request),
        "canonical_url": canonical,
        "meta_description": desc,
        "is_article": True,
        "page": "news",
    })


@app.get("/sitemap.xml")
def sitemap_xml():
    """Sitemap index (MNT_SPEED_V1, 2026-09-25). One file held all ~137,000 release addresses; the protocol
    allows 50,000 per file, so it is now an index over the static pages and numbered files of 40,000."""
    b = _sitemap_build()
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
           f'  <sitemap><loc>{_SITE_BASE}/sitemap-pages.xml</loc></sitemap>']
    for i, (_body, lastmod) in enumerate(b["news"], 1):
        lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
        out.append(f'  <sitemap><loc>{_SITE_BASE}/sitemap-news-{i}.xml</loc>{lm}</sitemap>')
    out.append('</sitemapindex>')
    return _SeoResponse("\n".join(out), media_type="application/xml")


@app.get("/sitemap-pages.xml")
def sitemap_pages_xml():
    return _SeoResponse(_sitemap_build()["pages"], media_type="application/xml")


@app.get("/sitemap-news-{n:int}.xml")
def sitemap_news_xml(n: int):
    news = _sitemap_build()["news"]
    if n < 1 or n > len(news):
        raise HTTPException(404)
    return _SeoResponse(news[n - 1][0], media_type="application/xml")


import time as _time_sm
from xml.sax.saxutils import escape as _xml_esc
from urllib.parse import quote as _url_q
_SITEMAP_CHUNK = 40000
_SITEMAP_TTL = 3600.0
_sitemap_cache = {}


def _sitemap_build():
    """Every sitemap file, built together and kept for an hour per worker (the build reads ~137k rows)."""
    hit = _sitemap_cache.get("b")
    now = _time_sm.monotonic()
    if hit is not None and now - hit[0] < _SITEMAP_TTL:
        return hit[1]
    head = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    pages = list(head)
    pages.append(f'  <url><loc>{_SITE_BASE}/</loc>'
                 f'<changefreq>hourly</changefreq><priority>1.0</priority></url>')
    seen = {"/"}
    try:
        nav_hrefs = [p.get("href") for g in _mnt_pages.MNT_NAV for p in g.get("pages", [])]
    except Exception:
        nav_hrefs = []
    for href in ["/financings"] + nav_hrefs:
        if href and href.startswith("/") and href not in seen:
            seen.add(href)
            pages.append(f'  <url><loc>{_SITE_BASE}{_xml_esc(href)}</loc>'
                         f'<changefreq>daily</changefreq><priority>0.8</priority></url>')
    pages.append('</urlset>')

    conn = db.get_conn()
    rows = conn.execute(
        "SELECT ticker, slug, published_at FROM events "
        "WHERE review_status='auto_approved' "
        "  AND slug IS NOT NULL AND slug != '' "
        "  AND ticker IS NOT NULL "
        "ORDER BY published_at ASC, event_id ASC"   # oldest first: earlier files stay stable as news arrives
    ).fetchall()
    urls = []
    for r in rows:
        ticker = (r["ticker"] or "").lower()
        slug = r["slug"]
        if not ticker or not slug:
            continue
        # percent-encode the path parts: some backfilled slugs carry characters XML cannot hold (first
        # candidate test: news-1 failed to parse at one such slug). The site decodes them back on arrival.
        loc = f"{_SITE_BASE}/news/{_url_q(ticker, safe='')}/{_url_q(slug, safe='-._~')}"
        urls.append((_xml_esc(loc), (r["published_at"] or "")[:10]))
    news = []
    for i in range(0, max(len(urls), 1), _SITEMAP_CHUNK):
        chunk = urls[i:i + _SITEMAP_CHUNK]
        out = list(head)
        for loc, lastmod in chunk:
            if lastmod:
                out.append(f'  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod></url>')
            else:
                out.append(f'  <url><loc>{loc}</loc></url>')
        out.append('</urlset>')
        news.append(("\n".join(out), max((lm for _, lm in chunk if lm), default="")))
    built = {"pages": "\n".join(pages), "news": news}
    _sitemap_cache["b"] = (now, built)
    return built


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt():
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /admin/\n"
        f"Sitemap: {_SITE_BASE}/sitemap.xml\n"
    )
# ====== end SEO additions ======


# ====== Analytics dashboard (appended) ======
import hashlib as _hashlib_an
import secrets as _secrets_an
from datetime import datetime as _dt_an, timedelta as _td_an

# Bot UA detection (server-side filter — keeps the views table clean of crawlers)
_BOT_UA_RE = re.compile(
    r"(?:bot|crawler|spider|slurp|fetcher|preview|prerender|"
    r"googlebot|bingbot|yandex|duckduckbot|baiduspider|"
    r"facebookexternalhit|twitterbot|linkedinbot|whatsapp|"
    r"telegram|discordbot|slackbot|pinterest|applebot|"
    r"semrush|ahrefs|mj12bot|petalbot|seznambot|sogou|"
    r"chatgpt|gptbot|claude|perplexity|amazonbot|bytedance)",
    re.I,
)

# Daily-rotating salt for hashing IPs (PII protection — IPs are never stored raw)
_IP_SALT_FILE = "/var/lib/mnt-portal/ip-salt"
def _get_daily_ip_salt():
    """Returns a random secret rotated each day (per-day uniqueness without long-term linkability)."""
    import os
    today = _dt_an.utcnow().strftime("%Y-%m-%d")
    try:
        os.makedirs("/var/lib/mnt-portal", exist_ok=True)
        with open(_IP_SALT_FILE) as f:
            stored_day, salt = f.read().strip().split(":", 1)
        if stored_day == today:
            return salt
    except (OSError, ValueError):
        pass
    salt = _secrets_an.token_hex(16)
    try:
        with open(_IP_SALT_FILE, "w") as f:
            f.write(f"{today}:{salt}")
    except OSError:
        pass
    return salt


def _ensure_pageviews_schema():
    conn = db.get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pageviews (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            path        TEXT NOT NULL,
            event_id    TEXT,
            ticker      TEXT,
            referrer    TEXT,
            user_agent  TEXT,
            ip_hash     TEXT,
            is_bot      INTEGER NOT NULL DEFAULT 0,
            viewed_at   TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pv_event   ON pageviews(event_id);
        CREATE INDEX IF NOT EXISTS idx_pv_ticker  ON pageviews(ticker);
        CREATE INDEX IF NOT EXISTS idx_pv_path    ON pageviews(path);
        CREATE INDEX IF NOT EXISTS idx_pv_viewed  ON pageviews(viewed_at);
        CREATE INDEX IF NOT EXISTS idx_pv_bot     ON pageviews(is_bot);
    """)
    conn.commit()


_ensure_pageviews_schema()


# OPS5 item 3 (2026-10-06): while this flag file exists, page views come from nginx's log (mnt-pv-ingest, once a
# minute) and are not written during the request. Checked at most every 5 s. Remove the file to switch back.
_PV_VIA_NGINX = "/opt/mnt/app/data/pv_via_nginx"
_pv_via_nginx_cache = [0.0, False]
def _pv_via_nginx():
    import os as _os_pv, time as _time_pv
    now = _time_pv.monotonic()
    if now - _pv_via_nginx_cache[0] > 5:
        _pv_via_nginx_cache[0] = now
        _pv_via_nginx_cache[1] = _os_pv.path.exists(_PV_VIA_NGINX)
    return _pv_via_nginx_cache[1]


def _log_pageview(request, event_id=None, ticker=None):
    """Log a pageview. Catches all errors — must never break a request."""
    if _pv_via_nginx():   # OPS5 item 3
        return
    try:
        ua = request.headers.get("user-agent") or ""
        is_bot = 1 if _BOT_UA_RE.search(ua) else 0
        if is_bot:  # OPSFIX item 8 (2026-10-05): bot views are not stored; human views are kept 1 year
            return
        ref = (request.headers.get("referer") or "")[:500]
        # Use X-Forwarded-For (set by nginx) when present; fall back to client IP
        xff = request.headers.get("x-forwarded-for") or ""
        ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "")
        salt = _get_daily_ip_salt()
        ip_hash = _hashlib_an.sha256((salt + ":" + ip).encode()).hexdigest()[:16] if ip else ""
        path = str(request.url.path)[:500]
        conn = db.get_conn()
        conn.execute(
            "INSERT INTO pageviews(path, event_id, ticker, referrer, user_agent, ip_hash, is_bot, viewed_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                path, event_id, ticker, ref, ua[:500], ip_hash, is_bot,
                _dt_an.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
            ),
        )
        conn.commit()
    except Exception as _e:  # pragma: no cover
        log.warning("pageview log failed: %s", _e)


# Wrap news_article so every article view is logged
_orig_news_article = news_article
def news_article(request: Request, ticker: str, slug: str):  # noqa: F811
    conn = db.get_conn()
    row = conn.execute(
        "SELECT * FROM events WHERE LOWER(ticker)=? AND slug=? "
        "AND review_status='auto_approved' LIMIT 1",
        (ticker.lower(), slug.lower()),
    ).fetchone()
    if not row:
        return _orig_news_article(request, ticker, slug)   # SLUGALIAS_V1: a known old address 301s, anything else 404s
    _log_pageview(request, event_id=row["event_id"], ticker=row["ticker"])
    canonical = f"{_SITE_BASE}/news/{ticker.lower()}/{slug}"
    desc = _seo_meta_description(row["raw_body"] or row["raw_excerpt"] or "")
    return templates.TemplateResponse(request, "event.html", {
        "request": request,
        "event": row,
        "is_admin": auth.is_logged_in(request),
        "canonical_url": canonical,
        "meta_description": desc,
        "is_article": True,
        "page": "news",
    })
# Re-register the route to use the wrapped version
app.routes[:] = [r for r in app.routes if not (
    getattr(r, "path", None) == "/news/{ticker}/{slug}"
    and getattr(r, "endpoint", None) is _orig_news_article
)]
app.get("/news/{ticker}/{slug}", response_class=HTMLResponse)(news_article)


# ====== /admin/analytics dashboard ======
def _window_cutoff(window):
    if window == "24h":
        return (_dt_an.utcnow() - _td_an(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
    if window == "7d":
        return (_dt_an.utcnow() - _td_an(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    if window == "30d":
        return (_dt_an.utcnow() - _td_an(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    return "1970-01-01T00:00:00"  # all-time


@app.get("/admin/analytics", response_class=HTMLResponse)
def admin_analytics(request: Request, window: str = "7d"):
    if not auth.is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    if window not in ("24h", "7d", "30d", "all"):
        window = "7d"
    cutoff = _window_cutoff(window)
    conn = db.get_conn()
    # Headline numbers
    totals = conn.execute(
        "SELECT COUNT(*) AS total, "
        "SUM(CASE WHEN is_bot=0 THEN 1 ELSE 0 END) AS humans, "
        "SUM(CASE WHEN is_bot=1 THEN 1 ELSE 0 END) AS bots, "
        "COUNT(DISTINCT ip_hash) AS uniques "
        "FROM pageviews WHERE viewed_at >= ?",
        (cutoff,),
    ).fetchone()
    # Top articles
    top_articles = conn.execute(
        "SELECT pv.event_id, pv.ticker, e.raw_headline, e.slug, "
        " COUNT(*) AS views, COUNT(DISTINCT pv.ip_hash) AS uniques "
        "FROM pageviews pv "
        "LEFT JOIN events e ON e.event_id = pv.event_id "
        "WHERE pv.viewed_at >= ? AND pv.is_bot = 0 AND pv.event_id IS NOT NULL "
        "GROUP BY pv.event_id ORDER BY views DESC LIMIT 25",
        (cutoff,),
    ).fetchall()
    # Top tickers
    top_tickers = conn.execute(
        "SELECT ticker, COUNT(*) AS views, COUNT(DISTINCT ip_hash) AS uniques "
        "FROM pageviews WHERE viewed_at >= ? AND is_bot = 0 AND ticker IS NOT NULL "
        "GROUP BY ticker ORDER BY views DESC LIMIT 15",
        (cutoff,),
    ).fetchall()
    # Top referrers
    top_referrers = conn.execute(
        "SELECT "
        " CASE "
        "   WHEN referrer = '' OR referrer IS NULL THEN '(direct)' "
        "   WHEN referrer LIKE '%miningnewsterminal.com%' THEN '(internal)' "
        "   ELSE referrer "
        " END AS source, "
        " COUNT(*) AS views "
        "FROM pageviews WHERE viewed_at >= ? AND is_bot = 0 "
        "GROUP BY source ORDER BY views DESC LIMIT 10",
        (cutoff,),
    ).fetchall()
    # Daily trend
    daily = conn.execute(
        "SELECT substr(viewed_at, 1, 10) AS day, "
        " SUM(CASE WHEN is_bot=0 THEN 1 ELSE 0 END) AS humans, "
        " SUM(CASE WHEN is_bot=1 THEN 1 ELSE 0 END) AS bots "
        "FROM pageviews WHERE viewed_at >= ? "
        "GROUP BY day ORDER BY day ASC",
        (cutoff,),
    ).fetchall()
    # Top paths (catches non-article visits — feed, financings, search)
    top_paths = conn.execute(
        "SELECT path, COUNT(*) AS views FROM pageviews "
        "WHERE viewed_at >= ? AND is_bot = 0 AND event_id IS NULL "
        "GROUP BY path ORDER BY views DESC LIMIT 10",
        (cutoff,),
    ).fetchall()

    # Decorate articles with the slug URL for direct linking
    decorated_articles = []
    for r in top_articles:
        d = dict(r)
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        else:
            d["url"] = f"/event/{d['event_id']}" if d.get("event_id") else ""
        decorated_articles.append(d)

    return templates.TemplateResponse(request, "admin_analytics.html", {
        "request": request,
        "is_admin": True,
        "window": window,
        "totals": dict(totals) if totals else {"total": 0, "humans": 0, "bots": 0, "uniques": 0},
        "top_articles": decorated_articles,
        "top_tickers": [dict(r) for r in top_tickers],
        "top_referrers": [dict(r) for r in top_referrers],
        "top_paths": [dict(r) for r in top_paths],
        "daily": [dict(r) for r in daily],
        "page": "admin",
    })
# ====== end analytics ======


# ====== Pageview logging for non-article routes (appended) ======
_log_other_routes_hooked = True

# Wrap feed
_orig_feed = feed
def feed(request: Request, ticker: str | None = None, cat: list[str] = Query(default=[])):  # noqa: F811
    _log_pageview(request)
    return _orig_feed(request, ticker=ticker, cat=cat)
app.routes[:] = [r for r in app.routes if not (
    getattr(r, "path", None) == "/" and getattr(r, "endpoint", None) is _orig_feed
)]
app.get("/", response_class=HTMLResponse)(feed)

# Wrap financings_page
_orig_fin = financings_page
def financings_page(request: Request, ticker: str | None = None, status: str | None = None, state: str | None = "all", page: int = 1):  # noqa: F811
    # state defaults to "all" and page is forwarded: this wrapper is the
    # route FastAPI actually serves, so its defaults are the real ones.
    _log_pageview(request, ticker=ticker)
    return _orig_fin(request, ticker=ticker, status=status, state=state,
                     page=page)
app.routes[:] = [r for r in app.routes if not (
    getattr(r, "path", None) == "/financings" and getattr(r, "endpoint", None) is _orig_fin
)]
app.get("/financings", response_class=HTMLResponse)(financings_page)

# Wrap search_page
_orig_search = search_page
def search_page(request: Request, q: str = ""):  # noqa: F811
    _log_pageview(request)
    return _orig_search(request, q=q)
app.routes[:] = [r for r in app.routes if not (
    getattr(r, "path", None) == "/search" and getattr(r, "endpoint", None) is _orig_search
)]
app.get("/search", response_class=HTMLResponse)(search_page)
# ====== end pageview hooks ======


# ====== Analytics dashboard v2 — Hour/Day/Month/Year granularity ======
from datetime import datetime as _dt_v2, timedelta as _td_v2
from calendar import monthrange as _monthrange_v2

def _v2_period_bounds(granularity: str, period: str | None):
    """Return (start_iso, end_iso, label, prev_period, next_period) for the requested granularity.

    granularity in {'hour','day','month','year'}
    period format:
      hour:  YYYY-MM-DD       (a specific day, shown as 24 hourly bars)
      day:   YYYY-MM          (a specific month, shown as N daily bars)
      month: YYYY             (a specific year, shown as 12 monthly bars)
      year:  ignored          (all years, shown as N yearly bars)
    """
    today = _dt_v2.utcnow().date()

    if granularity == "hour":
        try:
            d = _dt_v2.strptime(period, "%Y-%m-%d").date() if period else today
        except ValueError:
            d = today
        start = _dt_v2(d.year, d.month, d.day, 0, 0, 0)
        end   = start + _td_v2(days=1)
        label = d.strftime("%A, %B %-d, %Y")
        prev = (d - _td_v2(days=1)).isoformat()
        nxt  = (d + _td_v2(days=1)).isoformat() if d < today else None
        return start.strftime("%Y-%m-%dT%H:%M:%S"), end.strftime("%Y-%m-%dT%H:%M:%S"), label, prev, nxt

    if granularity == "day":
        # period = "YYYY-MM" → show 1st through last-day-of-month
        if period:
            try:
                y, m = [int(x) for x in period.split("-")]
            except (ValueError, AttributeError):
                y, m = today.year, today.month
        else:
            y, m = today.year, today.month
        last_day = _monthrange_v2(y, m)[1]
        start = _dt_v2(y, m, 1, 0, 0, 0)
        end   = _dt_v2(y, m, last_day, 23, 59, 59) + _td_v2(seconds=1)
        label = start.strftime("%B %Y")
        # prev month
        if m == 1:
            prev = f"{y - 1}-12"
        else:
            prev = f"{y}-{m - 1:02d}"
        # next month (cap at current)
        if m == 12:
            nxt_y, nxt_m = y + 1, 1
        else:
            nxt_y, nxt_m = y, m + 1
        nxt = f"{nxt_y}-{nxt_m:02d}" if (nxt_y, nxt_m) <= (today.year, today.month) else None
        return start.strftime("%Y-%m-%dT%H:%M:%S"), end.strftime("%Y-%m-%dT%H:%M:%S"), label, prev, nxt

    if granularity == "month":
        # period = "YYYY" → show 12 months of that year
        try:
            y = int(period) if period else today.year
        except ValueError:
            y = today.year
        start = _dt_v2(y, 1, 1, 0, 0, 0)
        end   = _dt_v2(y + 1, 1, 1, 0, 0, 0)
        label = str(y)
        prev = str(y - 1)
        nxt  = str(y + 1) if y < today.year else None
        return start.strftime("%Y-%m-%dT%H:%M:%S"), end.strftime("%Y-%m-%dT%H:%M:%S"), label, prev, nxt

    # year (all-time)
    start_iso = "1970-01-01T00:00:00"
    end_iso   = (_dt_v2.utcnow() + _td_v2(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    return start_iso, end_iso, "All time", None, None


def _v2_buckets(conn, granularity, start_iso, end_iso):
    """Return list of {label, views, visitors} buckets, gap-filled."""
    if granularity == "hour":
        # 24 hourly bars
        rows = conn.execute(
            "SELECT substr(viewed_at, 1, 13) AS bucket, "
            " SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) AS views, "
            " COUNT(DISTINCT CASE WHEN is_bot = 0 THEN ip_hash END) AS visitors "
            "FROM pageviews "
            "WHERE viewed_at >= ? AND viewed_at < ? "
            "GROUP BY bucket",
            (start_iso, end_iso),
        ).fetchall()
        seen = {r["bucket"]: r for r in rows}
        out = []
        d = _dt_v2.strptime(start_iso, "%Y-%m-%dT%H:%M:%S")
        for h in range(24):
            key = (d + _td_v2(hours=h)).strftime("%Y-%m-%dT%H")
            label = f"{h:02d}:00"
            r = seen.get(key)
            out.append({"label": label, "views": r["views"] if r else 0, "visitors": r["visitors"] if r else 0})
        return out

    if granularity == "day":
        # daily bars across the month
        rows = conn.execute(
            "SELECT substr(viewed_at, 1, 10) AS bucket, "
            " SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) AS views, "
            " COUNT(DISTINCT CASE WHEN is_bot = 0 THEN ip_hash END) AS visitors "
            "FROM pageviews "
            "WHERE viewed_at >= ? AND viewed_at < ? "
            "GROUP BY bucket",
            (start_iso, end_iso),
        ).fetchall()
        seen = {r["bucket"]: r for r in rows}
        out = []
        d_start = _dt_v2.strptime(start_iso, "%Y-%m-%dT%H:%M:%S").date()
        d_end   = _dt_v2.strptime(end_iso, "%Y-%m-%dT%H:%M:%S").date()
        d = d_start
        while d < d_end:
            key = d.isoformat()
            label = str(d.day)
            r = seen.get(key)
            out.append({"label": label, "views": r["views"] if r else 0, "visitors": r["visitors"] if r else 0})
            d += _td_v2(days=1)
        return out

    if granularity == "month":
        rows = conn.execute(
            "SELECT substr(viewed_at, 1, 7) AS bucket, "
            " SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) AS views, "
            " COUNT(DISTINCT CASE WHEN is_bot = 0 THEN ip_hash END) AS visitors "
            "FROM pageviews "
            "WHERE viewed_at >= ? AND viewed_at < ? "
            "GROUP BY bucket",
            (start_iso, end_iso),
        ).fetchall()
        seen = {r["bucket"]: r for r in rows}
        y = int(start_iso[:4])
        out = []
        names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        for m in range(1, 13):
            key = f"{y}-{m:02d}"
            r = seen.get(key)
            out.append({"label": names[m-1], "views": r["views"] if r else 0, "visitors": r["visitors"] if r else 0})
        return out

    # year
    rows = conn.execute(
        "SELECT substr(viewed_at, 1, 4) AS bucket, "
        " SUM(CASE WHEN is_bot = 0 THEN 1 ELSE 0 END) AS views, "
        " COUNT(DISTINCT CASE WHEN is_bot = 0 THEN ip_hash END) AS visitors "
        "FROM pageviews "
        "WHERE viewed_at >= ? AND viewed_at < ? "
        "GROUP BY bucket "
        "ORDER BY bucket",
        (start_iso, end_iso),
    ).fetchall()
    return [{"label": r["bucket"], "views": r["views"] or 0, "visitors": r["visitors"] or 0} for r in rows]


# Replace the existing /admin/analytics route
_orig_admin_analytics = admin_analytics
def admin_analytics(request: Request, granularity: str = "day", period: str | None = None):  # noqa: F811
    if not auth.is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    if granularity not in ("hour", "day", "month", "year"):
        granularity = "day"
    start_iso, end_iso, label, prev_period, next_period = _v2_period_bounds(granularity, period)
    conn = db.get_conn()
    buckets = _v2_buckets(conn, granularity, start_iso, end_iso)

    totals = conn.execute(
        "SELECT COUNT(*) AS total, "
        " SUM(CASE WHEN is_bot=0 THEN 1 ELSE 0 END) AS humans, "
        " SUM(CASE WHEN is_bot=1 THEN 1 ELSE 0 END) AS bots, "
        " COUNT(DISTINCT CASE WHEN is_bot=0 THEN ip_hash END) AS uniques, "
        " COUNT(DISTINCT CASE WHEN is_bot=0 THEN event_id END) AS articles_read "
        "FROM pageviews WHERE viewed_at >= ? AND viewed_at < ?",
        (start_iso, end_iso),
    ).fetchone()

    top_articles = conn.execute(
        "SELECT pv.event_id, pv.ticker, e.raw_headline, e.slug, "
        " COUNT(*) AS views, COUNT(DISTINCT pv.ip_hash) AS uniques "
        "FROM pageviews pv "
        "LEFT JOIN events e ON e.event_id = pv.event_id "
        "WHERE pv.viewed_at >= ? AND pv.viewed_at < ? "
        "  AND pv.is_bot = 0 AND pv.event_id IS NOT NULL "
        "GROUP BY pv.event_id ORDER BY views DESC LIMIT 25",
        (start_iso, end_iso),
    ).fetchall()
    top_tickers = conn.execute(
        "SELECT ticker, COUNT(*) AS views, COUNT(DISTINCT ip_hash) AS uniques "
        "FROM pageviews WHERE viewed_at >= ? AND viewed_at < ? AND is_bot = 0 AND ticker IS NOT NULL "
        "GROUP BY ticker ORDER BY views DESC LIMIT 15",
        (start_iso, end_iso),
    ).fetchall()
    top_referrers = conn.execute(
        "SELECT "
        " CASE "
        "   WHEN referrer = '' OR referrer IS NULL THEN '(direct)' "
        "   WHEN referrer LIKE '%miningnewsterminal.com%' THEN '(internal)' "
        "   ELSE referrer "
        " END AS source, "
        " COUNT(*) AS views "
        "FROM pageviews WHERE viewed_at >= ? AND viewed_at < ? AND is_bot = 0 "
        "GROUP BY source ORDER BY views DESC LIMIT 10",
        (start_iso, end_iso),
    ).fetchall()

    decorated_articles = []
    for r in top_articles:
        d = dict(r)
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        else:
            d["url"] = f"/event/{d['event_id']}" if d.get("event_id") else ""
        decorated_articles.append(d)

    return templates.TemplateResponse(request, "admin_analytics.html", {
        "request": request,
        "is_admin": True,
        "page": "admin",
        "granularity": granularity,
        "period": period or "",
        "period_label": label,
        "prev_period": prev_period,
        "next_period": next_period,
        "buckets": buckets,
        "totals": dict(totals) if totals else {"total": 0, "humans": 0, "bots": 0, "uniques": 0, "articles_read": 0},
        "top_articles": decorated_articles,
        "top_tickers": [dict(r) for r in top_tickers],
        "top_referrers": [dict(r) for r in top_referrers],
    })
# Re-register route
app.routes[:] = [r for r in app.routes if not (
    getattr(r, "path", None) == "/admin/analytics"
    and getattr(r, "endpoint", None) is _orig_admin_analytics
)]
app.get("/admin/analytics", response_class=HTMLResponse)(admin_analytics)
# ====== end analytics v2 ======


# ====== /drills route + ticker→name lookup helper (appended) ======
from datetime import datetime as _dt_drill, timedelta as _td_drill
import json as _json_drill

_TICKERS_NAME_INDEX: dict[str, str] | None = None


# ---- /company/{ticker} → redirect to filtered feed (clean URL alias) ----
@app.get("/company/{ticker}", response_class=HTMLResponse)
def company_page(request: Request, ticker: str):
    """Pretty per-company URL. Resolves previous tickers to canonical, then redirects."""
    canonical = _resolve_canonical_ticker(ticker.upper())
    return RedirectResponse(
        f"/?ticker={canonical}",
        status_code=302,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ---- Company / ticker history helpers ----

import json as _json_co
import sqlite3 as _sqlite3_co
import shutil as _shutil_co
from datetime import datetime as _dt_co, timezone as _tz_co

_TICKERS_PATH = "/opt/mnt/app/tickers.json"
_TICKERS_BAK_DIR = "/opt/mnt/app/.bak"


def _load_tickers_raw() -> list[dict]:
    return _json_co.load(open(_TICKERS_PATH))


def _save_tickers_raw(data: list[dict]):
    """Write tickers.json with a timestamped backup."""
    os.makedirs(_TICKERS_BAK_DIR, exist_ok=True)
    ts = _dt_co.now(_tz_co.utc).strftime("%Y%m%dT%H%M%SZ")
    _shutil_co.copy2(_TICKERS_PATH, f"{_TICKERS_BAK_DIR}/tickers_{ts}.json.bak")
    open(_TICKERS_PATH, "w").write(_json_co.dumps(data, indent=2))
    # bust the cached name map
    global _TICKERS_NAME_INDEX
    _TICKERS_NAME_INDEX = None


def _resolve_canonical_ticker(ticker: str) -> str:
    """If ticker matches a previous_tickers entry, return the current ticker.
    Otherwise return ticker as-is."""
    try:
        for t in _load_tickers_raw():
            for prev in (t.get("previous_tickers") or []):
                if (prev.get("ticker") or "").upper() == ticker.upper():
                    return (t.get("ticker") or "").upper()
    except Exception:
        pass
    return ticker.upper()


def _all_tickers_for_company(canonical: str) -> list[str]:
    """Return [canonical, ...prev_tickers] for the company that owns canonical."""
    canonical = canonical.upper()
    try:
        for t in _load_tickers_raw():
            if (t.get("ticker") or "").upper() == canonical:
                return [canonical] + [
                    (p.get("ticker") or "").upper()
                    for p in (t.get("previous_tickers") or [])
                    if p.get("ticker")
                ]
    except Exception:
        pass
    return [canonical]


def _rename_ticker_in_db(old: str, new: str) -> dict:
    """Bulk-rewrite ticker references in DB tables. Returns counts."""
    counts = {}
    con = _sqlite3_co.connect("/opt/mnt/app/portal/portal.db")
    con.execute("PRAGMA busy_timeout = 30000")
    cur = con.cursor()
    for tbl, col in (
        ("events", "ticker"),
        ("financing_events", "ticker"),
        ("financings", "ticker"),
        ("drill_results", "ticker"),
        ("resource_estimates", "ticker"),
    ):
        try:
            cur.execute(f"UPDATE {tbl} SET {col}=? WHERE {col}=?", (new, old))
            if cur.rowcount:
                counts[tbl] = cur.rowcount
        except _sqlite3_co.OperationalError:
            pass  # table missing
    con.commit()
    con.close()
    return counts


def _admin_or_redirect(request: Request):
    if not auth.is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=302)
    return None


# ---- Admin: list companies ----

@app.get("/admin/companies", response_class=HTMLResponse)
def admin_companies(request: Request, q: str | None = None):
    redir = _admin_or_redirect(request)
    if redir:
        return redir
    rows = _load_tickers_raw()
    if q:
        ql = q.lower()
        rows = [
            t for t in rows
            if ql in (t.get("ticker") or "").lower()
            or ql in (t.get("name") or "").lower()
            or any(ql in (p.get("ticker") or "").lower() for p in (t.get("previous_tickers") or []))
        ]
    rows = sorted(rows, key=lambda t: (t.get("ticker") or "").upper())
    return templates.TemplateResponse(request, "admin_companies.html", {
        "request": request,
        "is_admin": True,
        "tickers": rows,
        "q": q or "",
    })


@app.get("/admin/companies/{ticker}/edit", response_class=HTMLResponse)
def admin_company_edit_form(request: Request, ticker: str):
    redir = _admin_or_redirect(request)
    if redir:
        return redir
    rows = _load_tickers_raw()
    rec = next((t for t in rows if (t.get("ticker") or "").upper() == ticker.upper()), None)
    if not rec:
        raise HTTPException(404, "company not found")
    return templates.TemplateResponse(request, "admin_company_edit.html", {
        "request": request,
        "is_admin": True,
        "rec": rec,
        "saved": False,
        "error": None,
    })


@app.post("/admin/companies/{ticker}/edit")
async def admin_company_edit_save(
    request: Request,
    ticker: str,
):
    redir = _admin_or_redirect(request)
    if redir:
        return redir
    form = await request.form()
    new_name = (form.get("name") or "").strip()
    new_ticker = (form.get("ticker") or "").strip().upper()
    # previous_tickers come as repeating "prev_ticker" / "prev_ended_at"
    prev_tickers = []
    pts = form.getlist("prev_ticker") if hasattr(form, "getlist") else form.get("prev_ticker", [])
    pds = form.getlist("prev_ended_at") if hasattr(form, "getlist") else form.get("prev_ended_at", [])
    if not isinstance(pts, list):
        pts = [pts] if pts else []
    if not isinstance(pds, list):
        pds = [pds] if pds else []
    for tk, dt in zip(pts, pds):
        tk = (tk or "").strip().upper()
        dt = (dt or "").strip()
        if tk:
            entry = {"ticker": tk}
            if dt:
                entry["ended_at"] = dt
            prev_tickers.append(entry)

    rows = _load_tickers_raw()
    idx = next((i for i, t in enumerate(rows) if (t.get("ticker") or "").upper() == ticker.upper()), -1)
    if idx < 0:
        raise HTTPException(404, "company not found")

    rec = rows[idx]
    error = None

    # If ticker is changing, perform bulk rename in DB and add old to previous_tickers
    db_changes = {}
    if new_ticker and new_ticker != (rec.get("ticker") or "").upper():
        # Check no other entry already owns the new ticker
        if any((t.get("ticker") or "").upper() == new_ticker
               for j, t in enumerate(rows) if j != idx):
            error = f"Another company already uses ticker {new_ticker}; refusing to overwrite."
        else:
            old = (rec.get("ticker") or "").upper()
            # Auto-add old to previous_tickers
            prev_tickers.append({
                "ticker": old,
                "ended_at": _dt_co.now(_tz_co.utc).strftime("%Y-%m-%d"),
            })
            rec["ticker"] = new_ticker
            db_changes = _rename_ticker_in_db(old, new_ticker)

    if error is None:
        if new_name:
            rec["name"] = new_name
            rec["name_source"] = "admin_edit"
        if prev_tickers:
            # de-dupe by ticker, keep latest entry
            seen = {}
            for p in prev_tickers:
                seen[p["ticker"]] = p
            rec["previous_tickers"] = list(seen.values())
        elif "previous_tickers" in rec and not prev_tickers:
            rec["previous_tickers"] = []
        rows[idx] = rec
        _save_tickers_raw(rows)

    return templates.TemplateResponse(request, "admin_company_edit.html", {
        "request": request,
        "is_admin": True,
        "rec": rec,
        "saved": error is None,
        "error": error,
        "db_changes": db_changes,
    })


# ---- Admin: per-company article list with delete ----

@app.get("/admin/companies/{ticker}/articles", response_class=HTMLResponse)
def admin_company_articles(request: Request, ticker: str):
    redir = _admin_or_redirect(request)
    if redir:
        return redir
    canonical = _resolve_canonical_ticker(ticker.upper())
    rows = _load_tickers_raw()
    rec = next((t for t in rows if (t.get("ticker") or "").upper() == canonical), None)
    if not rec:
        raise HTTPException(404, "company not found")
    # Aggregate all tickers (current + previous) — show every article that ever
    # belonged to this company.
    tickers_for_company = _all_tickers_for_company(canonical)
    placeholders = ",".join(["?"] * len(tickers_for_company))
    addt_likes = " OR ".join(["('|' || COALESCE(additional_tickers, '') || '|') LIKE ?" for _ in tickers_for_company])
    conn = db.get_conn()
    events = conn.execute(
        f"SELECT event_id, ticker, additional_tickers, source_name, "
        f"  raw_headline, slug, "
        f"  COALESCE(published_at, classified_at) as date, categories, "
        f"  review_status "
        f"FROM events "
        f"WHERE UPPER(ticker) IN ({placeholders}) OR ({addt_likes}) "
        f"ORDER BY date DESC LIMIT 500",
        [t.upper() for t in tickers_for_company]
        + [f"%|{t.upper()}|%" for t in tickers_for_company],
    ).fetchall()
    return templates.TemplateResponse(request, "admin_company_articles.html", {
        "request": request,
        "is_admin": True,
        "rec": rec,
        "tickers_for_company": tickers_for_company,
        "events": events,
        "deleted": request.query_params.get("deleted"),
    })


@app.post("/admin/companies/{ticker}/articles/{event_id}/delete")
def admin_company_article_delete(request: Request, ticker: str, event_id: str):
    redir = _admin_or_redirect(request)
    if redir:
        return redir
    db.delete_events([event_id])
    return RedirectResponse(
        f"/admin/companies/{ticker}/articles?deleted=1",
        status_code=303,
    )


# ---- Admin: edit per-event additional tickers ----

@app.get("/admin/events/{event_id}/tickers", response_class=HTMLResponse)
def admin_event_tickers_form(request: Request, event_id: str, back: str | None = None):
    redir = _admin_or_redirect(request)
    if redir:
        return redir
    conn = db.get_conn()
    row = conn.execute(
        "SELECT event_id, ticker, additional_tickers, raw_headline, slug "
        "FROM events WHERE event_id=?", (event_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "event not found")
    addtl_str = (row["additional_tickers"] or "").strip("|")
    addtl = [a for a in addtl_str.split("|") if a]
    return templates.TemplateResponse(request, "admin_event_tickers.html", {
        "request": request,
        "is_admin": True,
        "event": row,
        "additional_tickers": addtl,
        "back": back or "/admin",
        "saved": False,
    })


@app.post("/admin/events/{event_id}/tickers")
async def admin_event_tickers_save(request: Request, event_id: str):
    redir = _admin_or_redirect(request)
    if redir:
        return redir
    form = await request.form()
    raw_addtl = form.get("additional_tickers") or ""
    back = form.get("back") or "/admin"
    parts = [p.strip().upper() for p in re.split(r"[,\s]+", raw_addtl) if p.strip()]
    primary = (form.get("ticker") or "").strip().upper()
    parts = [p for p in dict.fromkeys(parts) if p and p != primary]
    val = ("|" + "|".join(parts) + "|") if parts else None
    conn = db.get_conn()
    conn.execute("UPDATE events SET additional_tickers=? WHERE event_id=?",
                 (val, event_id))
    conn.commit()
    return RedirectResponse(back, status_code=303)








def _ticker_to_name(ticker: str) -> str:
    global _TICKERS_NAME_INDEX
    if _TICKERS_NAME_INDEX is None:
        try:
            data = _json_drill.load(open("/opt/mnt/app/tickers.json"))
            idx: dict[str, str] = {}
            for r in data:
                if not isinstance(r, dict) or not r.get("ticker"):
                    continue
                nm = r.get("name", "") or ""
                idx[r["ticker"]] = nm
                # also resolve previous tickers to the same name
                for prev in (r.get("previous_tickers") or []):
                    pt = (prev.get("ticker") or "")
                    if pt:
                        idx[pt] = nm
            _TICKERS_NAME_INDEX = idx
        except Exception:
            _TICKERS_NAME_INDEX = {}
    name = _TICKERS_NAME_INDEX.get(ticker, "")
    # stub-name filter: drop "Txg" for "TXG.TO" (auto-discovered placeholder)
    if name and ticker:
        base = ticker.split(".")[0]
        if name.upper() == base.upper() or name.upper() == ticker.upper():
            return ""
    return name

# Jinja filter: resolve ticker to full company name (used on lists)
templates.env.filters['company_name'] = _ticker_to_name


# MNT_NAV_V2 (2026-09-16): nav groups and data-page specs live in portal/pages.py.
from portal import pages as _mnt_pages  # noqa: E402
_mnt_pages.register(templates)


@app.get("/drills", response_class=HTMLResponse)
def drills_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    has: str = "all",
):
    """Drill results lifecycle table — top intercepts grouped by company."""
    conn = db.get_conn()
    # Driven by the TAG, not by drill_results: 376 tagged releases have no
    # parseable intercept and used to be invisible here. has=data brings back
    # the old extracted-only view.
    where, args = _cat_where("Drill Results", ticker)
    # TICKER_QUALIFY_V1 (2026-09-16): the joined table also has a ticker column.
    where = where.replace("(ticker = ?", "(e.ticker = ?")
    where = [where]
    if days and days > 0:
        cutoff = (_dt_drill.utcnow() - _td_drill(days=days)).strftime("%Y-%m-%d")
        where.append("substr(COALESCE(e.published_at, e.classified_at), 1, 10) >= ?")
        args.append(cutoff)
    if has == "data":
        where.append("dr.event_id IS NOT NULL")
    clause = " AND ".join(where)
    _cnt = ("SELECT COUNT(*) FROM events e "
            "LEFT JOIN drill_results dr ON dr.event_id = e.event_id "
            "WHERE " + clause)
    # MNT_SPEED_V1 (2026-09-25): counts cached 5 minutes; 50 rows a page (was 200).
    _dkey = ("drills", ticker or "", days if days and days > 0 else 0, has,
             cutoff if days and days > 0 else "")
    total_filtered = _speed_cached(_dkey + ("filtered",), lambda: conn.execute(_cnt, args).fetchone()[0])
    _DRILLS_PAGE = 50
    pages = max(1, (int(total_filtered or 0) + _DRILLS_PAGE - 1) // _DRILLS_PAGE)
    try:
        page_no = min(max(1, int(page or 1)), pages)
    except (TypeError, ValueError):
        page_no = 1
    _off = (page_no - 1) * _DRILLS_PAGE
    sql = (
        "SELECT e.event_id, e.ticker, e.slug, e.raw_headline, "
        "       COALESCE(e.published_at, e.classified_at) AS published_at, "
        "       dr.project, dr.top_hole_id, dr.top_summary, dr.top_grade, "
        "       dr.top_unit, dr.top_metal, dr.top_length_m, dr.n_intercepts "
        "FROM events e "
        "LEFT JOIN drill_results dr ON dr.event_id = e.event_id "
        "WHERE " + clause +
        " ORDER BY published_at DESC LIMIT ? OFFSET ?"
    )
    rows = list(conn.execute(sql, args + [_DRILLS_PAGE, _off]))
    with_data = _speed_cached(_dkey + ("with_data",), lambda: conn.execute(
        "SELECT COUNT(*) FROM events e "
        "JOIN drill_results dr ON dr.event_id = e.event_id "
        "WHERE " + clause, args).fetchone()[0])

    # DATA_PAGE_DETAIL_V1 (2026-09-17): every accepted interval of the releases on this page, for
    # the expandable rows. One query for the page; absent table (before the new reader publishes)
    # simply means no expandable rows.
    _ivs = {}
    _ids = [r["event_id"] for r in rows]
    if _ids:
        try:
            # MNT_SPEED_V1: only the count here; the intervals load when a row is opened.
            for iv in conn.execute(
                    "SELECT event_id, COUNT(*) FROM drill_intervals WHERE event_id IN (%s) GROUP BY event_id"
                    % ",".join("?" * len(_ids)), _ids):
                _ivs[iv[0]] = iv[1]
        except _sqlite3_co.OperationalError:
            _ivs = {}

    decorated = []
    for r in rows:
        d = dict(r)
        d["intervals"] = []
        d["intervals_n"] = _ivs.get(d["event_id"], 0)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        # Build URL to article
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        decorated.append(d)

    total = _speed_cached(("drills_total",), lambda: conn.execute("SELECT COUNT(*) FROM drill_results").fetchone()[0])
    tickers_list = _speed_cached(("drills_tickers",), lambda: [r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM drill_results "
        "WHERE ticker IS NOT NULL ORDER BY ticker"
    )])

    # DATA_PAGE_V1 (2026-09-16): same queries as before, laid out by
    # data_page.html from pages.PAGE_SPECS["drills"]. tagged_total feeds the
    # coverage line: tagged releases under the company/window filter, ignoring has=.
    _tt_where, _tt_args = _cat_where("Drill Results", ticker)
    _tt_where = [_tt_where]
    if days and days > 0:
        _tt_where.append("substr(COALESCE(e.published_at, e.classified_at), 1, 10) >= ?")
        _tt_args.append(cutoff)
    tagged_total = _speed_cached(_dkey + ("tagged",), lambda: conn.execute(
        "SELECT COUNT(*) FROM events e WHERE " + " AND ".join(_tt_where), _tt_args
    ).fetchone()[0])
    return templates.TemplateResponse(request, "data_page.html", {
        "spec": _mnt_pages.PAGE_SPECS["drills"],
        "tagged_total": tagged_total,
        "request": request,
        "is_admin": auth.is_logged_in(request),
        "page": "drills",
        "rows": decorated,
        "total": total,
        "tickers": tickers_list,
        "selected_ticker": ticker or "",
        "days": days,
        "total_filtered": total_filtered,
        "pages": pages,
        "page_no": page_no,
        "pager_url": "/drills",
        "pager_qs": (("&ticker=" + ticker) if ticker else "")
                    + (("&days=" + str(days)) if days else "")
                    + (("&has=" + has) if has and has != "all" else ""),
        "has": has,
        "with_data": with_data,
    })
# ====== end drills route ======


# MNT_SPEED_V1 (2026-09-25): one release's intervals, fetched when its /drills row is opened. The page used to
# build every interval of every release into itself (2.5 MB per page). Same markup as before, from
# templates/_dp_detail_table.html.
@app.get("/drills/intervals/{event_id:path}", response_class=HTMLResponse)
def drills_intervals_fragment(request: Request, event_id: str):
    conn = db.get_conn()
    det = []
    try:
        for iv in conn.execute(
                "SELECT event_id, seq, hole_id, from_m, to_m, length_m, summary, including, is_best, reported_before "
                "FROM drill_intervals WHERE event_id = ? ORDER BY seq", (event_id,)):
            ivd = dict(iv)
            ivd["note"] = "best" if ivd["is_best"] else ("reported earlier" if ivd["reported_before"] else "")
            det.append(ivd)
    except _sqlite3_co.OperationalError:
        det = []
    resp = templates.TemplateResponse(request, "_dp_detail_table.html", {
        "request": request, "spec": _mnt_pages.PAGE_SPECS["drills"], "det": det})
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


# ====== /resources route (Resource Estimates) (appended) ======
@app.get("/resources", response_class=HTMLResponse)
def resources_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    has: str = "all",
):
    # RES_PAGE_V2 (2026-09-18): this page is built from resource_estimates alone. It used to be
    # driven off events -- _cat_where() against 43,591 approved releases, four LIKEs per row, then
    # a LEFT JOIN -- which cost about 1.3 of its 2.0 seconds and could not use an index, because
    # two of those four patterns start with a wildcard. /financings has always read its own table
    # and answers in 0.2s; this now does the same.
    #
    # What made it possible is that the publisher writes a MARKER row (category NULL, n_rows 0)
    # for every tagged release that states no figures, so the set of rows the page shows lives
    # entirely in one 1,443-row table: 1,100 real figures and 343 markers.
    conn = db.get_conn()
    where, args = ["1=1"], []
    if ticker:
        where.append("re.ticker = ?")
        args.append(ticker)
    if days and days > 0:
        from datetime import datetime as _dt_res, timedelta as _td_res
        # re.published_at is already COALESCE(published_at, classified_at) -- the publisher stores
        # the date this page sorts and filters by, so no expression is needed on the column here
        where.append("re.published_at >= ?")
        args.append((_dt_res.utcnow() - _td_res(days=days)).strftime("%Y-%m-%d"))
    if has == "data":
        where.append("re.category IS NOT NULL")
    clause = " AND ".join(where)

    total_filtered = conn.execute(
        "SELECT COUNT(*) FROM resource_estimates re WHERE " + clause, args).fetchone()[0]
    pages, page_no, _off = _paginate(total_filtered, page)
    rows = list(conn.execute(
        "SELECT event_id, ticker, slug, raw_headline, published_at, project, deposit, category, "
        "       tonnes, grades_json, contained_json, cut_off, basis, context, summary, mre_type, "
        "       metal_focus, headline_oz_au, ordinal, n_rows "
        "FROM resource_estimates re WHERE " + clause +
        " ORDER BY published_at DESC, event_id, ordinal LIMIT ? OFFSET ?",
        args + [_PAGE_SIZE, _off]))
    with_data = conn.execute(
        "SELECT COUNT(DISTINCT re.event_id) FROM resource_estimates re "
        "WHERE " + clause + " AND re.category IS NOT NULL", args).fetchone()[0]

    decorated = []
    last_event = None
    for r in rows:
        d = dict(r)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        # a release stating several figures prints its ticker, company and date once, on the first
        d["first_of_release"] = d.get("event_id") != last_event
        last_event = d.get("event_id")
        decorated.append(d)

    # the headline counts describe real estimates, so they leave the markers out
    total = conn.execute(
        "SELECT COUNT(*) FROM resource_estimates WHERE category IS NOT NULL").fetchone()[0]
    releases = conn.execute(
        "SELECT COUNT(DISTINCT event_id) FROM resource_estimates "
        "WHERE category IS NOT NULL").fetchone()[0]
    distinct_tickers = list(conn.execute(
        "SELECT DISTINCT ticker FROM resource_estimates "
        "WHERE ticker IS NOT NULL ORDER BY ticker"
    ))
    return templates.TemplateResponse(request, "resources.html", {
        "request": request,
        "is_admin": auth.is_logged_in(request),
        "page": "resources",
        "rows": decorated,
        "total": total,
        "releases": releases,
        "tickers": [r[0] for r in distinct_tickers],
        "selected_ticker": ticker or "",
        "days": days,
        "total_filtered": total_filtered,
        "pages": pages,
        "page_no": page_no,
        "pager_url": "/resources",
        "pager_qs": (("&ticker=" + ticker) if ticker else "")
                    + (("&days=" + str(days)) if days else "")
                    + (("&has=" + has) if has and has != "all" else ""),
        "has": has,
        "with_data": with_data,
    })
# ====== end /resources route ======
# ====== /economic-studies route (Economic Studies) ECON_PAGE_V1 (2026-09-21) ======
# Built from economic_studies alone, the table portal/economics_publish.py writes from the active
# ECON_V1 reader: one row per scenario, plus a marker row (scenario NULL) for each tagged release that
# states no figures. It replaces the plain list of tagged releases this URL used to show, which is
# why "/economic-studies" is no longer in _CATEGORY_PAGES below: a route registered there first would
# shadow this one.
#
# show = announced  studies this release announces (default)
#        studies    every release stating economics, restated studies included and marked
#        all        every release above plus tagged releases that state no figures
_ECON_SHOW = ("announced", "studies", "all")
_ECON_DEFAULT_SHOW = "announced"


@app.get("/economic-studies", response_class=HTMLResponse)
def economic_studies_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    study: str = "",
    show: str = _ECON_DEFAULT_SHOW,
):
    conn = db.get_conn()
    show = show if show in _ECON_SHOW else _ECON_DEFAULT_SHOW
    study = study if study in ("PEA", "PFS", "FS") else ""
    ctx = {"request": request, "is_admin": auth.is_logged_in(request), "page": "economic",
           "rows": [], "total": 0, "releases": 0, "tickers": [], "selected_ticker": ticker or "",
           "days": days, "study": study, "show": show, "total_filtered": 0, "pages": 1, "page_no": 1,
           "pager_url": "/economic-studies", "pager_qs": "", "announced": 0}
    have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='economic_studies'").fetchone()
    if not have:
        # before the first publish there is nothing to show, and the page still answers 200
        return templates.TemplateResponse(request, "economic_studies.html", ctx)

    where, args = ["1=1"], []
    if show == "announced":
        where.append("es.scenario IS NOT NULL AND es.context = 'announced'")
    elif show == "studies":
        where.append("es.scenario IS NOT NULL")
    if ticker:
        where.append("es.ticker = ?")
        args.append(ticker)
    if study:
        where.append("es.study_type = ?")
        args.append(study)
    if days and days > 0:
        from datetime import datetime as _dt_es, timedelta as _td_es
        where.append("es.published_at >= ?")
        args.append((_dt_es.utcnow() - _td_es(days=days)).strftime("%Y-%m-%d"))
    clause = " AND ".join(where)

    total_filtered = conn.execute("SELECT COUNT(*) FROM economic_studies es WHERE " + clause,
                                  args).fetchone()[0]
    pages, page_no, _off = _paginate(total_filtered, page)
    rows = list(conn.execute(
        "SELECT event_id, ordinal, ticker, slug, raw_headline, published_at, project, study_type, "
        "       context, scenario, basis, currency, discount_pct, npv_pre_tax, npv_after_tax, "
        "       irr_pre_tax_pct, irr_after_tax_pct, payback_years, initial_capex, capex_sensitivity, "
        "       aisc, aisc_unit, mine_life_years, n_rows, tag_confirmed, other_owner "
        "FROM economic_studies es WHERE " + clause +
        " ORDER BY published_at DESC, event_id, ordinal LIMIT ? OFFSET ?",
        args + [_PAGE_SIZE, _off]))

    decorated, last_event = [], None
    for r in rows:
        d = dict(r)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        # a release stating several scenarios prints its ticker, company, date and study once
        d["first_of_release"] = d.get("event_id") != last_event
        last_event = d.get("event_id")
        decorated.append(d)

    ctx.update(
        rows=decorated, total_filtered=total_filtered, pages=pages, page_no=page_no,
        total=conn.execute("SELECT COUNT(*) FROM economic_studies WHERE scenario IS NOT NULL").fetchone()[0],
        releases=conn.execute("SELECT COUNT(DISTINCT event_id) FROM economic_studies "
                              "WHERE scenario IS NOT NULL").fetchone()[0],
        announced=conn.execute("SELECT COUNT(DISTINCT event_id) FROM economic_studies "
                               "WHERE scenario IS NOT NULL AND context='announced'").fetchone()[0],
        tickers=[r[0] for r in conn.execute("SELECT DISTINCT ticker FROM economic_studies "
                                            "WHERE ticker IS NOT NULL ORDER BY ticker")],
        pager_qs=(("&ticker=" + ticker) if ticker else "") + (("&days=" + str(days)) if days else "")
                 + (("&study=" + study) if study else "")
                 + (("&show=" + show) if show != _ECON_DEFAULT_SHOW else ""))
    return templates.TemplateResponse(request, "economic_studies.html", ctx)


# The page prints figures with the publisher's own formatters, so a figure reads the same on the page
# as in the table it came from.
from portal.economics_publish import (fmt_money as _es_money, fmt_pct as _es_pct,   # noqa: E402
                                      fmt_years as _es_years, fmt_unit_cost as _es_unit)


def _es_npv(r, which="after"):
    v = r.get("npv_after_tax") if which == "after" else r.get("npv_pre_tax")
    return _es_money(v, r.get("currency")) or "—"


def _es_scenario(s):
    if not s:
        return "—"
    return s[:1].upper() + s[1:]


templates.env.filters["es_money"] = lambda v, cur=None: _es_money(v, cur) or "—"
templates.env.filters["es_pct"] = lambda v: _es_pct(v) or "—"
templates.env.filters["es_years"] = lambda v: _es_years(v) or "—"
templates.env.filters["es_unit"] = lambda v, unit=None, cur=None: _es_unit(v, unit, cur) or "—"
templates.env.filters["es_scenario"] = _es_scenario
# ====== end /economic-studies route ======
# ====== /production-results route (Production Results) PROD_PAGE_V1 (2026-09-21) ======
# Built from production_results alone, the table portal/production_publish.py writes from the active PROD_V1
# reader: one row per metal per period (actual or guidance), a row per completed milestone, and a marker row
# (kind NULL) for each tagged release that states none. It replaces the plain list of tagged releases this
# URL used to show, which is why "/production-results" is no longer in _CATEGORY_PAGES below: a route
# registered there first would shadow this one.
#
# show = rows   every row a release states (default)
#        all    also tagged releases that state no figures
_PROD_SHOW = ("rows", "all")
_PROD_KINDS = ("actual", "guidance", "milestone", "recovered")   # PROD13 (2026-09-28): recovered rows


@app.get("/production-results", response_class=HTMLResponse)
def production_results_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    kind: str = "",
    metal: str = "",
    show: str = "rows",
):
    conn = db.get_conn()
    show = show if show in _PROD_SHOW else "rows"
    kind = kind if kind in _PROD_KINDS else ""
    ctx = {"request": request, "is_admin": auth.is_logged_in(request), "page": "production",
           "rows": [], "total": 0, "releases": 0, "tickers": [], "metals": [], "selected_ticker": ticker or "",
           "days": days, "kind": kind, "metal": metal, "show": show, "total_filtered": 0, "pages": 1,
           "page_no": 1, "pager_url": "/production-results", "pager_qs": ""}
    have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='production_results'").fetchone()
    if not have:
        # before the first publish there is nothing to show, and the page still answers 200
        return templates.TemplateResponse(request, "production_results.html", ctx)

    where, args = ["1=1"], []
    if show == "rows":
        where.append("pr.kind IS NOT NULL")
    if ticker:
        where.append("pr.ticker = ?")
        args.append(ticker)
    if kind:
        where.append("pr.kind = ?")
        args.append(kind)
    if metal:
        where.append("pr.metal = ?")
        args.append(metal)
    if days and days > 0:
        from datetime import datetime as _dt_pr, timedelta as _td_pr
        where.append("pr.published_at >= ?")
        args.append((_dt_pr.utcnow() - _td_pr(days=days)).strftime("%Y-%m-%d"))
    clause = " AND ".join(where)

    total_filtered = conn.execute("SELECT COUNT(*) FROM production_results pr WHERE " + clause, args).fetchone()[0]
    pages, page_no, _off = _paginate(total_filtered, page)
    rows = list(conn.execute(
        "SELECT event_id, ordinal, ticker, slug, raw_headline, published_at, kind, period, metal, unit, qty, low, "
        "       high, sold, aisc, guided_low, guided_high, milestone, asset, basis, approx, n_rows, tag_confirmed "
        "FROM production_results pr WHERE " + clause +
        " ORDER BY published_at DESC, event_id, ordinal LIMIT ? OFFSET ?", args + [_PAGE_SIZE, _off]))

    decorated, last_event = [], None
    for r in rows:
        d = dict(r)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        d["first_of_release"] = d.get("event_id") != last_event
        last_event = d.get("event_id")
        decorated.append(d)

    ctx.update(
        rows=decorated, total_filtered=total_filtered, pages=pages, page_no=page_no,
        total=conn.execute("SELECT COUNT(*) FROM production_results WHERE kind IS NOT NULL").fetchone()[0],
        releases=conn.execute("SELECT COUNT(DISTINCT event_id) FROM production_results WHERE kind IS NOT NULL").fetchone()[0],
        tickers=[r[0] for r in conn.execute("SELECT DISTINCT ticker FROM production_results "
                                            "WHERE ticker IS NOT NULL AND kind IS NOT NULL ORDER BY ticker")],
        metals=[r[0] for r in conn.execute("SELECT metal FROM production_results WHERE metal IS NOT NULL "
                                           "GROUP BY metal ORDER BY COUNT(*) DESC")],
        pager_qs=(("&ticker=" + ticker) if ticker else "") + (("&days=" + str(days)) if days else "")
                 + (("&kind=" + kind) if kind else "") + (("&metal=" + metal) if metal else "")
                 + (("&show=" + show) if show != "rows" else ""))
    return templates.TemplateResponse(request, "production_results.html", ctx)


# The page prints figures with the publisher's own formatters, so a figure reads the same on the page as in
# the table it came from.
from portal.production_publish import (fmt_qty as _pr_qty, fmt_range as _pr_range,   # noqa: E402
                                       MILESTONE_LABELS as _PR_MILESTONES)

templates.env.filters["pr_qty"] = lambda v, unit=None: _pr_qty(v, unit) or "—"
templates.env.filters["pr_range"] = lambda lo, hi=None, unit=None: _pr_range(lo, hi, unit) or "—"
templates.env.filters["pr_milestone"] = lambda m: _PR_MILESTONES.get(m or "", (m or "").replace("_", " ").capitalize())
# ====== end /production-results route ======
# ====== /mine-development route (Mine Development & Operations) DEV_PAGE_V1 (2026-09-28) ======
# Built from mine_dev_events alone, the table portal/mine_dev_publish.py writes from the active DEV_V1 reader: one
# row per headline event a release TAGGED Mine Development & Operations reports for the issuer's own mine, plant or
# project (build milestones, operating status, incidents, offtakes/shipments/contracts), and a marker row
# (event_type NULL) for each tagged release where the reader found none. The page shows event type, mine and status;
# the date, capex, % complete and figures the reader stores are not shown yet (Justin 2026-09-28: released as an
# early version, "I will iterate on the reader in the future").
#
# show = events  every event row (default)
#        all     also tagged releases with no event read
_MD_SHOW = ("events", "all")
_MD_STATUSES = ("achieved", "underway", "planned")

from portal.mine_dev_publish import (TYPE_LABELS as _MD_TYPES, GROUP_LABELS as _MD_GROUPS,  # noqa: E402
                                     STATUS_LABELS as _MD_STATUS_LABELS)


@app.get("/mine-development", response_class=HTMLResponse)
def mine_development_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    group: str = "",
    type: str = "",
    status: str = "",
    show: str = "events",
):
    conn = db.get_conn()
    show = show if show in _MD_SHOW else "events"
    group = group if group in _MD_GROUPS else ""
    etype = type if type in _MD_TYPES else ""
    status = status if status in _MD_STATUSES else ""
    ctx = {"request": request, "is_admin": auth.is_logged_in(request), "page": "minedev",
           "rows": [], "total": 0, "releases": 0, "tickers": [], "selected_ticker": ticker or "",
           "days": days, "group": group, "etype": etype, "status": status, "show": show,
           "group_options": list(_MD_GROUPS.items()), "type_options": list(_MD_TYPES.items()),
           "total_filtered": 0, "pages": 1, "page_no": 1, "pager_url": "/mine-development", "pager_qs": ""}
    have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='mine_dev_events'").fetchone()
    if not have:
        # before the first publish there is nothing to show, and the page still answers 200
        return templates.TemplateResponse(request, "mine_development.html", ctx)

    where, args = ["1=1"], []
    if show == "events" or group or etype or status:
        where.append("md.event_type IS NOT NULL")
    if ticker:
        where.append("md.ticker = ?")
        args.append(ticker)
    if group:
        where.append("md.event_group = ?")
        args.append(group)
    if etype:
        where.append("md.event_type = ?")
        args.append(etype)
    if status:
        where.append("md.status = ?")
        args.append(status)
    if days and days > 0:
        from datetime import datetime as _dt_md, timedelta as _td_md
        where.append("md.published_at >= ?")
        args.append((_dt_md.utcnow() - _td_md(days=days)).strftime("%Y-%m-%d"))
    clause = " AND ".join(where)

    total_filtered = conn.execute("SELECT COUNT(*) FROM mine_dev_events md WHERE " + clause, args).fetchone()[0]
    pages, page_no, _off = _paginate(total_filtered, page)
    rows = list(conn.execute(
        "SELECT event_id, ordinal, ticker, slug, raw_headline, published_at, event_type, event_group, mine, status, "
        "       incident_kind, n_rows "
        "FROM mine_dev_events md WHERE " + clause +
        " ORDER BY published_at DESC, event_id, ordinal LIMIT ? OFFSET ?", args + [_PAGE_SIZE, _off]))

    decorated, last_event = [], None
    for r in rows:
        d = dict(r)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        d["first_of_release"] = d.get("event_id") != last_event
        last_event = d.get("event_id")
        decorated.append(d)

    ctx.update(
        rows=decorated, total_filtered=total_filtered, pages=pages, page_no=page_no,
        total=conn.execute("SELECT COUNT(*) FROM mine_dev_events WHERE event_type IS NOT NULL").fetchone()[0],
        releases=conn.execute("SELECT COUNT(DISTINCT event_id) FROM mine_dev_events "
                              "WHERE event_type IS NOT NULL").fetchone()[0],
        tickers=[r[0] for r in conn.execute("SELECT DISTINCT ticker FROM mine_dev_events "
                                            "WHERE ticker IS NOT NULL AND event_type IS NOT NULL ORDER BY ticker")],
        pager_qs=(("&ticker=" + ticker) if ticker else "") + (("&days=" + str(days)) if days else "")
                 + (("&group=" + group) if group else "") + (("&type=" + etype) if etype else "")
                 + (("&status=" + status) if status else "") + (("&show=" + show) if show != "events" else ""))
    return templates.TemplateResponse(request, "mine_development.html", ctx)


templates.env.filters["md_type"] = lambda t: _MD_TYPES.get(t or "", (t or "").replace("_", " ").capitalize())
templates.env.filters["md_status"] = lambda s: _MD_STATUS_LABELS.get(s or "", "—")
# ====== end /mine-development route ======
# ====== /sampling-geoscience route (Sampling & Geoscience Results) SMP_PAGE_V1 (2026-09-29) ======
# Built from sampling_results alone, the table portal/sampling_publish.py writes from the active SMP_V1 reader: one row
# per sample type per project a release TAGGED Sampling & Geoscience Results reports results for (rock samples,
# soil / till / sediment geochemistry, geophysics by survey method, bulk and brine samples, mapping findings), with
# historical results flagged, and a marker row (sample_type NULL) for each tagged release where the reader found none.
# The page shows sample type, project, best grade and width; anomaly and sample count are stored, not shown yet
# (Justin 2026-09-29: released as an early version).
#
# show = results  every result row (default)
#        all      also tagged releases with no result read
# hist = all | new | historical
_SMP_SHOW = ("results", "all")
_SMP_HIST = ("all", "new", "historical")

from portal.sampling_publish import (TYPE_LABELS as _SMP_TYPES, GROUP_LABELS as _SMP_GROUPS,  # noqa: E402
                                     SURVEY_LABELS as _SMP_SURVEYS)


def _smp_num(v):
    if v is None:
        return ""
    s = "{:,.4f}".format(float(v)).rstrip("0").rstrip(".")
    return s or "0"


def _smp_grade(r):
    if r.get("grade") is None:
        return ""
    g = "%s %s %s" % (_smp_num(r["grade"]), r.get("grade_unit") or "", r.get("grade_metal") or "")
    if r.get("width_m") is not None and r.get("sample_type") in ("chip", "channel", "trench"):
        g += " over %s m" % _smp_num(r["width_m"])
    return " ".join(g.split())


@app.get("/sampling-geoscience", response_class=HTMLResponse)
def sampling_geoscience_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    group: str = "",
    type: str = "",
    hist: str = "all",
    show: str = "results",
):
    conn = db.get_conn()
    show = show if show in _SMP_SHOW else "results"
    hist = hist if hist in _SMP_HIST else "all"
    group = group if group in _SMP_GROUPS else ""
    stype = type if type in _SMP_TYPES else ""
    ctx = {"request": request, "is_admin": auth.is_logged_in(request), "page": "sampling",
           "rows": [], "total": 0, "releases": 0, "tickers": [], "selected_ticker": ticker or "",
           "days": days, "group": group, "stype": stype, "hist": hist, "show": show,
           "group_options": list(_SMP_GROUPS.items()), "type_options": list(_SMP_TYPES.items()),
           "total_filtered": 0, "pages": 1, "page_no": 1, "pager_url": "/sampling-geoscience", "pager_qs": ""}
    have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='sampling_results'").fetchone()
    if not have:
        # before the first publish there is nothing to show, and the page still answers 200
        return templates.TemplateResponse(request, "sampling_geoscience.html", ctx)

    where, args = ["1=1"], []
    if show == "results" or group or stype or hist != "all":
        where.append("sr.sample_type IS NOT NULL")
    if ticker:
        where.append("sr.ticker = ?")
        args.append(ticker)
    if group:
        where.append("sr.sample_group = ?")
        args.append(group)
    if stype:
        where.append("sr.sample_type = ?")
        args.append(stype)
    if hist == "new":
        where.append("sr.historical = 0")
    elif hist == "historical":
        where.append("sr.historical = 1")
    if days and days > 0:
        from datetime import datetime as _dt_smp, timedelta as _td_smp
        where.append("sr.published_at >= ?")
        args.append((_dt_smp.utcnow() - _td_smp(days=days)).strftime("%Y-%m-%d"))
    clause = " AND ".join(where)

    total_filtered = conn.execute("SELECT COUNT(*) FROM sampling_results sr WHERE " + clause, args).fetchone()[0]
    pages, page_no, _off = _paginate(total_filtered, page)
    rows = list(conn.execute(
        "SELECT event_id, ordinal, ticker, slug, raw_headline, published_at, sample_type, survey_type, project, "
        "       historical, grade, grade_unit, grade_metal, width_m, n_rows "
        "FROM sampling_results sr WHERE " + clause +
        " ORDER BY published_at DESC, event_id, ordinal LIMIT ? OFFSET ?", args + [_PAGE_SIZE, _off]))

    decorated, last_event = [], None
    for r in rows:
        d = dict(r)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        d["grade_text"] = _smp_grade(d)
        d["first_of_release"] = d.get("event_id") != last_event
        last_event = d.get("event_id")
        decorated.append(d)

    ctx.update(
        rows=decorated, total_filtered=total_filtered, pages=pages, page_no=page_no,
        total=conn.execute("SELECT COUNT(*) FROM sampling_results WHERE sample_type IS NOT NULL").fetchone()[0],
        releases=conn.execute("SELECT COUNT(DISTINCT event_id) FROM sampling_results "
                              "WHERE sample_type IS NOT NULL").fetchone()[0],
        tickers=[r[0] for r in conn.execute("SELECT DISTINCT ticker FROM sampling_results "
                                            "WHERE ticker IS NOT NULL AND sample_type IS NOT NULL ORDER BY ticker")],
        pager_qs=(("&ticker=" + ticker) if ticker else "") + (("&days=" + str(days)) if days else "")
                 + (("&group=" + group) if group else "") + (("&type=" + stype) if stype else "")
                 + (("&hist=" + hist) if hist != "all" else "") + (("&show=" + show) if show != "results" else ""))
    return templates.TemplateResponse(request, "sampling_geoscience.html", ctx)


templates.env.filters["smp_type"] = lambda t: _SMP_TYPES.get(t or "", (t or "").replace("_", " ").capitalize())
templates.env.filters["smp_survey"] = lambda s: _SMP_SURVEYS.get(s or "", s or "")
# ====== end /sampling-geoscience route ======
# ====== /royalties-streams route (Royalties & Streams) ROY_PAGE_V1 (2026-09-21) ======
# Built from royalty_deals alone, the table portal/royalties_publish.py writes from the active ROY_V1 reader:
# one row per royalty or stream interest a release reports as news -- bought, sold, granted, bought back or
# amended -- and a marker row (type NULL) for each tagged release that reports none.
#
# show = deals     the newest release of each deal (default); a deal reported more than once says so
#        releases  every release's row, announcements and closings alike
#        all       also tagged releases that report no deal
_ROY_SHOW = ("deals", "releases", "all")
_ROY_TYPES = ("NSR", "GRR", "NPI", "stream", "other")
_ROY_ACTIONS = ("new", "transfer", "buyback", "amendment", "held")
# ROY_PAGE_V1.1 (2026-09-28): view = deal (default) | vendor | held | any, from royalty_deals.kind
_ROY_KINDS = ("deal", "vendor", "held", "any")


@app.get("/royalties-streams", response_class=HTMLResponse)
def royalties_streams_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    type: str = "",
    action: str = "",
    show: str = "deals",
    kind: str = "deal",
):
    conn = db.get_conn()
    show = show if show in _ROY_SHOW else "deals"
    rtype = type if type in _ROY_TYPES else ""
    action = action if action in _ROY_ACTIONS else ""
    kind = kind if kind in _ROY_KINDS else "deal"
    ctx = {"request": request, "is_admin": auth.is_logged_in(request), "page": "royalties",
           "rows": [], "total": 0, "releases": 0, "tickers": [], "selected_ticker": ticker or "",
           "days": days, "rtype": rtype, "action": action, "show": show, "kind": kind, "kind_counts": {},
           "total_filtered": 0, "pages": 1,
           "page_no": 1, "pager_url": "/royalties-streams", "pager_qs": ""}
    have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='royalty_deals'").fetchone()
    if not have:
        # before the first publish there is nothing to show, and the page still answers 200
        return templates.TemplateResponse(request, "royalties_streams.html", ctx)

    where, args = ["1=1"], []
    has_kind = any(r[1] == "kind" for r in conn.execute("PRAGMA table_info(royalty_deals)"))
    if show != "all":
        where.append("rd.type IS NOT NULL")
    if has_kind and kind != "any":
        where.append("(COALESCE(rd.kind, 'deal') = ? OR rd.type IS NULL)")
        args.append(kind)
    if show == "deals":
        where.append("rd.is_latest = 1")
    if ticker:
        where.append("rd.ticker = ?")
        args.append(ticker)
    if rtype:
        where.append("rd.type = ?")
        args.append(rtype)
    if action:
        where.append("rd.action = ?")
        args.append(action)
    if days and days > 0:
        from datetime import datetime as _dt_rd, timedelta as _td_rd
        where.append("rd.published_at >= ?")
        args.append((_dt_rd.utcnow() - _td_rd(days=days)).strftime("%Y-%m-%d"))
    clause = " AND ".join(where)

    total_filtered = conn.execute("SELECT COUNT(*) FROM royalty_deals rd WHERE " + clause, args).fetchone()[0]
    pages, page_no, _off = _paginate(total_filtered, page)
    rows = list(conn.execute(
        "SELECT event_id, ordinal, ticker, slug, raw_headline, published_at, type, rate_pct, metal, property, "
        "       operator, buyer, seller, price, currency, action, status, deal_releases, first_reported, is_latest, "
        "       n_rows, tag_confirmed" + (", COALESCE(kind, 'deal') AS kind " if has_kind else ", 'deal' AS kind ") +
        "FROM royalty_deals rd WHERE " + clause +
        " ORDER BY published_at DESC, event_id, ordinal LIMIT ? OFFSET ?", args + [_PAGE_SIZE, _off]))

    decorated, last_event = [], None
    for r in rows:
        d = dict(r)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        d["first_of_release"] = d.get("event_id") != last_event
        last_event = d.get("event_id")
        decorated.append(d)

    ctx.update(
        rows=decorated, total_filtered=total_filtered, pages=pages, page_no=page_no,
        total=conn.execute("SELECT COUNT(*) FROM royalty_deals WHERE type IS NOT NULL AND is_latest=1"
                           + (" AND COALESCE(kind, 'deal') = 'deal'" if has_kind else "")).fetchone()[0],
        releases=conn.execute("SELECT COUNT(DISTINCT event_id) FROM royalty_deals WHERE type IS NOT NULL").fetchone()[0],
        tickers=[r[0] for r in conn.execute("SELECT DISTINCT ticker FROM royalty_deals "
                                            "WHERE ticker IS NOT NULL AND type IS NOT NULL ORDER BY ticker")],
        pager_qs=(("&ticker=" + ticker) if ticker else "") + (("&days=" + str(days)) if days else "")
                 + (("&type=" + rtype) if rtype else "") + (("&action=" + action) if action else "")
                 + (("&show=" + show) if show != "deals" else "") + (("&kind=" + kind) if kind != "deal" else ""),
        kind_counts=({r[0]: r[1] for r in conn.execute(
            "SELECT COALESCE(kind, 'deal'), COUNT(*) FROM royalty_deals WHERE type IS NOT NULL AND is_latest=1 "
            "GROUP BY 1")} if has_kind else {}))
    return templates.TemplateResponse(request, "royalties_streams.html", ctx)


# The page prints figures with the publisher's own formatters, so a figure reads the same on the page as in
# the table it came from.
from portal.royalties_publish import (fmt_money as _rd_money, fmt_rate as _rd_rate,   # noqa: E402
                                      TYPE_LABELS as _RD_TYPES, ACTION_LABELS as _RD_ACTIONS)

templates.env.filters["rd_money"] = lambda v, cur=None: _rd_money(v, cur) or "—"
templates.env.filters["rd_rate"] = lambda v: _rd_rate(v) or ""
templates.env.filters["rd_type"] = lambda t: _RD_TYPES.get(t or "", t or "—")
templates.env.filters["rd_action"] = lambda a: _RD_ACTIONS.get(a or "", a or "—")
# ====== end /royalties-streams route ======
# ====== /exploration-programs route (Exploration Programs) EXPL_PAGE_V1 (2026-09-21) ======
# Built from exploration_programs alone, the table portal/exploration_publish.py writes from the active EXPL_V1
# reader: one row per field program a release reports -- drilling, geophysics or ground work; planned, started,
# underway or completed; the issuer's own, or a previous owner's (historical) -- and a marker row
# (program_type NULL) for each tagged release that reports none.
#
# show = programs  the newest release of each program (default); a program reported more than once says so
#        releases  every release's row
#        all       also tagged releases that report no program
# work = current   the company's own programs (default) | historical: previous owners' work | both
_EXPL_SHOW = ("programs", "releases", "all")
_EXPL_TYPES = ("drilling", "geophysics", "ground")
_EXPL_STATUS = ("planned", "started", "underway", "completed")
_EXPL_WORK = ("current", "historical", "both")


@app.get("/exploration-programs", response_class=HTMLResponse)
def exploration_programs_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    type: str = "",
    status: str = "",
    work: str = "current",
    show: str = "programs",
):
    conn = db.get_conn()
    show = show if show in _EXPL_SHOW else "programs"
    ptype = type if type in _EXPL_TYPES else ""
    status = status if status in _EXPL_STATUS else ""
    work = work if work in _EXPL_WORK else "current"
    ctx = {"request": request, "is_admin": auth.is_logged_in(request), "page": "exploration",
           "rows": [], "total": 0, "releases": 0, "tickers": [], "selected_ticker": ticker or "",
           "days": days, "ptype": ptype, "status": status, "work": work, "show": show, "total_filtered": 0,
           "pages": 1, "page_no": 1, "pager_url": "/exploration-programs", "pager_qs": ""}
    have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='exploration_programs'").fetchone()
    if not have:
        # before the first publish there is nothing to show, and the page still answers 200
        return templates.TemplateResponse(request, "exploration_programs.html", ctx)

    where, args = ["1=1"], []
    if show != "all":
        where.append("ep.program_type IS NOT NULL")
    if show == "programs":
        where.append("ep.is_latest = 1")
    if work == "current":
        where.append("ep.historical = 0")
    elif work == "historical":
        where.append("ep.historical = 1")
    if ticker:
        where.append("ep.ticker = ?")
        args.append(ticker)
    if ptype:
        where.append("ep.program_type = ?")
        args.append(ptype)
    if status:
        where.append("ep.status = ?")
        args.append(status)
    if days and days > 0:
        from datetime import datetime as _dt_ep, timedelta as _td_ep
        where.append("ep.published_at >= ?")
        args.append((_dt_ep.utcnow() - _td_ep(days=days)).strftime("%Y-%m-%d"))
    clause = " AND ".join(where)

    total_filtered = conn.execute("SELECT COUNT(*) FROM exploration_programs ep WHERE " + clause, args).fetchone()[0]
    pages, page_no, _off = _paginate(total_filtered, page)
    rows = list(conn.execute(
        "SELECT event_id, ordinal, ticker, slug, raw_headline, published_at, program_type, project, status, metres, "
        "       holes, line_km, season, phase, historical, operator, drill_method, survey_type, budget, currency, "
        "       target_metal, contractor, rigs, program_releases, first_reported, is_latest, n_rows, tag_confirmed "
        "FROM exploration_programs ep WHERE " + clause +
        " ORDER BY published_at DESC, event_id, ordinal LIMIT ? OFFSET ?", args + [_PAGE_SIZE, _off]))

    decorated, last_event = [], None
    for r in rows:
        d = dict(r)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        d["first_of_release"] = d.get("event_id") != last_event
        last_event = d.get("event_id")
        decorated.append(d)

    ctx.update(
        rows=decorated, total_filtered=total_filtered, pages=pages, page_no=page_no,
        total=conn.execute("SELECT COUNT(*) FROM exploration_programs WHERE program_type IS NOT NULL AND is_latest=1 "
                           "AND historical=0").fetchone()[0],
        releases=conn.execute("SELECT COUNT(DISTINCT event_id) FROM exploration_programs "
                              "WHERE program_type IS NOT NULL").fetchone()[0],
        tickers=[r[0] for r in conn.execute("SELECT DISTINCT ticker FROM exploration_programs "
                                            "WHERE ticker IS NOT NULL AND program_type IS NOT NULL ORDER BY ticker")],
        pager_qs=(("&ticker=" + ticker) if ticker else "") + (("&days=" + str(days)) if days else "")
                 + (("&type=" + ptype) if ptype else "") + (("&status=" + status) if status else "")
                 + (("&work=" + work) if work != "current" else "") + (("&show=" + show) if show != "programs" else ""))
    return templates.TemplateResponse(request, "exploration_programs.html", ctx)


# The page prints figures with the publisher's own formatters, so a figure reads the same on the page as in
# the table it came from.
from portal.exploration_publish import (fmt_money as _ep_money, fmt_int as _ep_int,   # noqa: E402
                                        TYPE_LABELS as _EP_TYPES, STATUS_LABELS as _EP_STATUS)

templates.env.filters["ep_money"] = lambda v, cur=None: _ep_money(v, cur) or "—"
templates.env.filters["ep_int"] = lambda v: _ep_int(v) or ""
templates.env.filters["ep_type"] = lambda t: _EP_TYPES.get(t or "", t or "—")
templates.env.filters["ep_status"] = lambda s: _EP_STATUS.get(s or "", s or "—")
# ====== end /exploration-programs route ======
# ====== /technical-reports route (Technical Reports) TECH_PAGE_V1 (2026-09-22) ======
# Built from technical_reports alone, the table portal/technical_publish.py writes from the active TECH_V1 reader:
# one row per NI 43-101 technical report an item reports -- filed, commissioned or withdrawn, from news releases and
# from SEDAR+ documents (QP consents, report pages) -- and a marker row (status NULL) for each tagged item that
# reports none.
#
# show = reports   the newest item of each report (default); a report named by several items says so
#        items     every item's row
#        all       also tagged items that report no report
_TR_SHOW = ("reports", "items", "all")
_TR_TYPES = ("property", "resource", "PEA", "PFS", "FS", "other")
_TR_STATUS = ("filed", "commissioned", "withdrawn")


def _tr_resource_text(js):
    """'M&I 27.3 Mt @ 1.40% Li2O · Inferred 18.6 Mt' from the stored summary, or None."""
    import json as _json_tr
    try:
        rows = _json_tr.loads(js) if js else None
    except ValueError:
        return None
    if not rows:
        return None
    out = []
    for x in rows[:3]:
        bits = [x.get("category") or ""]
        if x.get("tonnes"):
            t = float(x["tonnes"])
            bits.append(("%.1f Mt" % (t / 1e6)) if t >= 1e6 else ("{:,.0f} t".format(t)))
        if x.get("grade") is not None:
            bits.append("@ %s %s %s" % (("%.3g" % float(x["grade"])), x.get("grade_unit") or "", x.get("metal") or ""))
        elif x.get("contained") is not None:
            c = float(x["contained"])
            bits.append(("%.2f M" % (c / 1e6) if c >= 1e6 else "{:,.0f} ".format(c)) + (x.get("contained_unit") or "")
                        + " " + (x.get("metal") or ""))
        out.append(" ".join(b for b in bits if b).strip())
    return " · ".join(o for o in out if o) or None


@app.get("/technical-reports", response_class=HTMLResponse)
def technical_reports_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    type: str = "",
    status: str = "",
    show: str = "reports",
):
    conn = db.get_conn()
    show = show if show in _TR_SHOW else "reports"
    rtype = type if type in _TR_TYPES else ""
    status = status if status in _TR_STATUS else ""
    ctx = {"request": request, "is_admin": auth.is_logged_in(request), "page": "technical",
           "rows": [], "total": 0, "releases": 0, "tickers": [], "selected_ticker": ticker or "",
           "days": days, "rtype": rtype, "status": status, "show": show, "total_filtered": 0,
           "pages": 1, "page_no": 1, "pager_url": "/technical-reports", "pager_qs": ""}
    have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='technical_reports'").fetchone()
    if not have:
        # before the first publish there is nothing to show, and the page still answers 200
        return templates.TemplateResponse(request, "technical_reports.html", ctx)

    where, args = ["1=1"], []
    if show != "all":
        where.append("tr.status IS NOT NULL")
    if show == "reports":
        where.append("tr.is_latest = 1")
    if ticker:
        where.append("tr.ticker = ?")
        args.append(ticker)
    if rtype:
        where.append("tr.report_type = ?")
        args.append(rtype)
    if status:
        where.append("tr.status = ?")
        args.append(status)
    if days and days > 0:
        from datetime import datetime as _dt_tr, timedelta as _td_tr
        where.append("tr.published_at >= ?")
        args.append((_dt_tr.utcnow() - _td_tr(days=days)).strftime("%Y-%m-%d"))
    clause = " AND ".join(where)

    total_filtered = conn.execute("SELECT COUNT(*) FROM technical_reports tr WHERE " + clause, args).fetchone()[0]
    pages, page_no, _off = _paginate(total_filtered, page)
    rows = list(conn.execute(
        "SELECT event_id, ordinal, ticker, slug, raw_headline, published_at, report_type, project, status, "
        "       effective_date, filing_date, expected, author_firm, qps, title, amended, metal, resource_json, npv, "
        "       npv_discount, irr, capex, currency, after_tax, doc_kind, report_items, first_reported, is_latest, "
        "       n_rows, tag_confirmed "
        "FROM technical_reports tr WHERE " + clause +
        " ORDER BY published_at DESC, event_id, ordinal LIMIT ? OFFSET ?", args + [_PAGE_SIZE, _off]))

    decorated, last_event = [], None
    for r in rows:
        d = dict(r)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        d["resource_text"] = _tr_resource_text(d.get("resource_json"))
        d["first_of_release"] = d.get("event_id") != last_event
        last_event = d.get("event_id")
        decorated.append(d)

    ctx.update(
        rows=decorated, total_filtered=total_filtered, pages=pages, page_no=page_no,
        total=conn.execute("SELECT COUNT(*) FROM technical_reports WHERE status IS NOT NULL AND is_latest=1").fetchone()[0],
        releases=conn.execute("SELECT COUNT(DISTINCT event_id) FROM technical_reports "
                              "WHERE status IS NOT NULL").fetchone()[0],
        tickers=[r[0] for r in conn.execute("SELECT DISTINCT ticker FROM technical_reports "
                                            "WHERE ticker IS NOT NULL AND status IS NOT NULL ORDER BY ticker")],
        pager_qs=(("&ticker=" + ticker) if ticker else "") + (("&days=" + str(days)) if days else "")
                 + (("&type=" + rtype) if rtype else "") + (("&status=" + status) if status else "")
                 + (("&show=" + show) if show != "reports" else ""))
    return templates.TemplateResponse(request, "technical_reports.html", ctx)


# The page prints figures with the publisher's own formatters, so a figure reads the same on the page as in
# the table it came from.
from portal.technical_publish import (fmt_money as _tr_money,   # noqa: E402
                                      TYPE_LABELS as _TR_TYPE_LABELS, STATUS_LABELS as _TR_STATUS_LABELS)

templates.env.filters["tr_money"] = lambda v, cur=None: _tr_money(v, cur) or "—"
templates.env.filters["tr_type"] = lambda t: _TR_TYPE_LABELS.get(t or "", t or "—")
templates.env.filters["tr_status"] = lambda s: _TR_STATUS_LABELS.get(s or "", s or "—")
# ====== end /technical-reports route ======
# ====== /permits-approvals route (Permits & Approvals) PERMIT_PAGE_V1 (2026-09-22) ======
# Built from permits alone, the table portal/permits_publish.py writes from the active PERMIT_V1 reader: one row per
# permit or government approval an item reports, at its stage as of the item (planned, applied, in review, granted,
# renewed or contested), chained across releases, and a marker row (status NULL) for each tagged item that reports
# none.
#
# show = permits   the newest item of each permit (default); a permit named by several items says so
#        items     every item's row
#        all       also tagged items that report no permit
# scope = tagged   releases carrying the Permits & Approvals tag (default: the reader is checked on these)
#         all      also untagged releases the reader found a permit in (less checked; Justin to decide the default)
_PM_SHOW = ("permits", "items", "all")
_PM_SCOPE = ("tagged", "all")
_PM_TYPES = ("drill_exploration", "environmental_assessment", "plan_of_operations", "mining_licence",
             "construction_operating", "water", "land_community", "government_policy", "other")
_PM_STATUS = ("planned", "applied", "in_review", "granted", "renewed", "contested")


@app.get("/permits-approvals", response_class=HTMLResponse)
def permits_approvals_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    type: str = "",
    status: str = "",
    show: str = "permits",
    scope: str = "tagged",
):
    conn = db.get_conn()
    show = show if show in _PM_SHOW else "permits"
    scope = scope if scope in _PM_SCOPE else "tagged"
    ptype = type if type in _PM_TYPES else ""
    status = status if status in _PM_STATUS else ""
    ctx = {"request": request, "is_admin": auth.is_logged_in(request), "page": "permits",
           "rows": [], "total": 0, "releases": 0, "tickers": [], "selected_ticker": ticker or "",
           "days": days, "ptype": ptype, "status": status, "show": show, "scope": scope, "total_filtered": 0,
           "pages": 1, "page_no": 1, "pager_url": "/permits-approvals", "pager_qs": "",
           "type_options": [("", "All permits")] + [(k, _PM_TYPE_LABELS[k]) for k in _PM_TYPES],
           "status_options": [("", "Any stage")] + [(k, _PM_STATUS_LABELS[k]) for k in _PM_STATUS]}
    have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='permits'").fetchone()
    if not have:
        # before the first publish there is nothing to show, and the page still answers 200
        return templates.TemplateResponse(request, "permits_approvals.html", ctx)

    where, args = ["1=1"], []
    scope_sql = " AND tag_confirmed = 1" if scope == "tagged" else ""
    if scope == "tagged":
        where.append("pm.tag_confirmed = 1")
    if show != "all":
        where.append("pm.status IS NOT NULL")
    if show == "permits":
        where.append("pm.latest = 1")
    if ticker:
        where.append("pm.ticker = ?")
        args.append(ticker)
    if ptype:
        where.append("pm.permit_type = ?")
        args.append(ptype)
    if status:
        where.append("pm.status = ?")
        args.append(status)
    if days and days > 0:
        from datetime import datetime as _dt_pm, timedelta as _td_pm
        where.append("pm.published_at >= ?")
        args.append((_dt_pm.utcnow() - _td_pm(days=days)).strftime("%Y-%m-%d"))
    clause = " AND ".join(where)

    total_filtered = conn.execute("SELECT COUNT(*) FROM permits pm WHERE " + clause, args).fetchone()[0]
    pages, page_no, _off = _paginate(total_filtered, page)
    rows = list(conn.execute(
        "SELECT event_id, ordinal, ticker, slug, raw_headline, published_at, permit_type, project, status, authority, "
        "       date, permit_name, permit_id, term, expiry, jurisdiction, metal, chain_items, first_reported, latest, "
        "       n_rows, tag_confirmed, scope, holder "   # PERMIT_V2 page: "allows ..." / "held by ..."
        "FROM permits pm WHERE " + clause +
        " ORDER BY published_at DESC, event_id, ordinal LIMIT ? OFFSET ?", args + [_PAGE_SIZE, _off]))

    decorated, last_event = [], None
    for r in rows:
        d = dict(r)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        d["first_of_release"] = d.get("event_id") != last_event
        last_event = d.get("event_id")
        decorated.append(d)

    ctx.update(
        rows=decorated, total_filtered=total_filtered, pages=pages, page_no=page_no,
        total=conn.execute("SELECT COUNT(*) FROM permits WHERE status IS NOT NULL AND latest=1" + scope_sql).fetchone()[0],
        releases=conn.execute("SELECT COUNT(DISTINCT event_id) FROM permits WHERE status IS NOT NULL" + scope_sql).fetchone()[0],
        tickers=[r[0] for r in conn.execute("SELECT DISTINCT ticker FROM permits "
                                            "WHERE ticker IS NOT NULL AND status IS NOT NULL" + scope_sql + " ORDER BY ticker")],
        pager_qs=(("&ticker=" + ticker) if ticker else "") + (("&days=" + str(days)) if days else "")
                 + (("&type=" + ptype) if ptype else "") + (("&status=" + status) if status else "")
                 + (("&show=" + show) if show != "permits" else "") + (("&scope=" + scope) if scope != "tagged" else ""))
    return templates.TemplateResponse(request, "permits_approvals.html", ctx)


# The page prints types and stages with the publisher's own labels, so they read the same everywhere.
from portal.permits_publish import TYPE_LABELS as _PM_TYPE_LABELS, STATUS_LABELS as _PM_STATUS_LABELS  # noqa: E402

templates.env.filters["pm_type"] = lambda t: _PM_TYPE_LABELS.get(t or "", t or "—")
templates.env.filters["pm_status"] = lambda s: _PM_STATUS_LABELS.get(s or "", s or "—")
# ====== end /permits-approvals route ======
# ====== /property-options route (Property Options & Staking) OPT_PAGE_V1 (2026-09-23) ======
# Built from land_deals alone, the table portal/options_publish.py writes from the active OPT_V1 reader: one row per
# land deal an item reports (option in or out, earn-in, staking, claim or property purchase, property sale), at its
# stage as of the item (proposed, signed, payment, completed, amended or terminated), chained across releases, and a
# marker row (deal_type NULL) for each tagged item that reports none.
#
# show = deals   the newest item of each deal (default); a deal named by several items says so
#        items   every item's row
#        all     also tagged items that report no deal
# scope = tagged releases carrying the Property Options & Staking tag (default: the reader is checked on these)
#         all    also untagged releases the reader found a deal in (less checked; Justin to decide the default)
_LD_SHOW = ("deals", "items", "all")
_LD_SCOPE = ("tagged", "all")
_LD_TYPES = ("option_in", "option_out", "staking", "claim_purchase", "property_purchase", "property_sale")
_LD_STAGES = ("proposed", "signed", "payment", "completed", "amended", "terminated")


@app.get("/property-options", response_class=HTMLResponse)
def property_options_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    type: str = "",
    stage: str = "",
    show: str = "deals",
    scope: str = "tagged",
):
    conn = db.get_conn()
    show = show if show in _LD_SHOW else "deals"
    scope = scope if scope in _LD_SCOPE else "tagged"
    dtype = type if type in _LD_TYPES else ""
    stage = stage if stage in _LD_STAGES else ""
    ctx = {"request": request, "is_admin": auth.is_logged_in(request), "page": "options",
           "rows": [], "total": 0, "releases": 0, "tickers": [], "selected_ticker": ticker or "",
           "days": days, "dtype": dtype, "stage": stage, "show": show, "scope": scope, "total_filtered": 0,
           "pages": 1, "page_no": 1, "pager_url": "/property-options", "pager_qs": "",
           "type_options": [("", "All deals")] + [(k, _LD_TYPE_LABELS[k]) for k in _LD_TYPES],
           "stage_options": [("", "Any stage")] + [(k, _LD_STAGE_LABELS[k]) for k in _LD_STAGES]}
    have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='land_deals'").fetchone()
    if not have:
        # before the first publish there is nothing to show, and the page still answers 200
        return templates.TemplateResponse(request, "property_options.html", ctx)

    where, args = ["1=1"], []
    scope_sql = " AND tag_confirmed = 1" if scope == "tagged" else ""
    if scope == "tagged":
        where.append("ld.tag_confirmed = 1")
    if show != "all":
        where.append("ld.deal_type IS NOT NULL")
    if show == "deals":
        where.append("ld.latest = 1")
    if ticker:
        where.append("ld.ticker = ?")
        args.append(ticker)
    if dtype:
        where.append("ld.deal_type = ?")
        args.append(dtype)
    if stage:
        where.append("ld.stage = ?")
        args.append(stage)
    if days and days > 0:
        from datetime import datetime as _dt_ld, timedelta as _td_ld
        where.append("ld.published_at >= ?")
        args.append((_dt_ld.utcnow() - _td_ld(days=days)).strftime("%Y-%m-%d"))
    clause = " AND ".join(where)

    total_filtered = conn.execute("SELECT COUNT(*) FROM land_deals ld WHERE " + clause, args).fetchone()[0]
    pages, page_no, _off = _paginate(total_filtered, page)
    rows = list(conn.execute(
        "SELECT event_id, ordinal, ticker, slug, raw_headline, published_at, deal_type, stage, property, counterparty, "
        "       interest_pct, cash, currency, shares, work, nsr, term, area, date, metal, chain_items, first_reported, "
        "       latest, n_rows, tag_confirmed, jurisdiction "   # OPT 1.0.5 page: where the property is
        "FROM land_deals ld WHERE " + clause +
        " ORDER BY published_at DESC, event_id, ordinal LIMIT ? OFFSET ?", args + [_PAGE_SIZE, _off]))

    decorated, last_event = [], None
    for r in rows:
        d = dict(r)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        d["first_of_release"] = d.get("event_id") != last_event
        last_event = d.get("event_id")
        decorated.append(d)

    ctx.update(
        rows=decorated, total_filtered=total_filtered, pages=pages, page_no=page_no,
        total=conn.execute("SELECT COUNT(*) FROM land_deals WHERE deal_type IS NOT NULL AND latest=1" + scope_sql).fetchone()[0],
        releases=conn.execute("SELECT COUNT(DISTINCT event_id) FROM land_deals WHERE deal_type IS NOT NULL" + scope_sql).fetchone()[0],
        tickers=[r[0] for r in conn.execute("SELECT DISTINCT ticker FROM land_deals "
                                            "WHERE ticker IS NOT NULL AND deal_type IS NOT NULL" + scope_sql + " ORDER BY ticker")],
        pager_qs=(("&ticker=" + ticker) if ticker else "") + (("&days=" + str(days)) if days else "")
                 + (("&type=" + dtype) if dtype else "") + (("&stage=" + stage) if stage else "")
                 + (("&show=" + show) if show != "deals" else "") + (("&scope=" + scope) if scope != "tagged" else ""))
    return templates.TemplateResponse(request, "property_options.html", ctx)


# The page prints types and stages with the publisher's own labels, so they read the same everywhere.
from portal.options_publish import TYPE_LABELS as _LD_TYPE_LABELS, STAGE_LABELS as _LD_STAGE_LABELS  # noqa: E402


def _ld_money(v, cur=None):
    if v is None:
        return ""
    sym = {"USD": "US$", "AUD": "A$", "CAD": "$"}.get(cur or "CAD", "$")
    if v >= 1e6:
        return "%s%.2fM" % (sym, v / 1e6) if v % 1e6 else "%s%dM" % (sym, int(v / 1e6))
    return "%s%s" % (sym, format(int(round(v)), ","))


def _ld_count(v):
    if v is None:
        return ""
    return ("%.2fM" % (v / 1e6)).replace(".00M", "M") if v >= 1e6 else format(int(round(v)), ",")


def _ld_num(v):
    if v is None:
        return ""
    return ("%.2f" % v).rstrip("0").rstrip(".")


templates.env.filters["ld_type"] = lambda t: _LD_TYPE_LABELS.get(t or "", t or "—")
templates.env.filters["ld_stage"] = lambda s: _LD_STAGE_LABELS.get(s or "", s or "—")
templates.env.filters["ld_money"] = _ld_money
templates.env.filters["ld_count"] = _ld_count
templates.env.filters["ld_num"] = _ld_num
# ====== end /property-options route ======
# ====== /debt-credit route (Debt & Credit Facilities) DEBT_PAGE_V1 (2026-09-24) ======
# Built from debt_deals alone, the table portal/debt_publish.py writes from the active DEBT_V1 reader: one row per debt
# instrument an item reports (convertible debenture or note, loan, credit facility, notes or bonds, gold loan,
# prepayment), at its stage as of the item (proposed, signed, closed, drawn, amended, converted, repaid, terminated,
# or interest paid),
# chained across releases, and a marker row (instrument NULL) for each tagged item that reports none.
#
# side  = borrower  the company borrows (default; Justin 2026-09-24: lending rows are shown, borrowing by default)
#         lender    the company lends or holds another company's debt (rule DL)
#         all       both
# show  = deals   the newest item of each debt (default); a debt named by several items says so
#         items   every item's row
#         all     also tagged items that report no debt
# scope = tagged  releases carrying the Debt & Credit Facilities tag (default)
#         all     also untagged releases the reader found debt in
_DD_SHOW = ("deals", "items", "all")
_DD_SCOPE = ("tagged", "all")
_DD_SIDE = ("borrower", "lender", "all")
_DD_TYPES = ("convertible_debenture", "convertible_note", "loan", "credit_facility", "notes", "gold_loan", "prepayment")
_DD_STAGES = ("proposed", "signed", "closed", "drawn", "amended", "converted", "repaid", "terminated", "interest_paid")


@app.get("/debt-credit", response_class=HTMLResponse)
def debt_credit_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    type: str = "",
    stage: str = "",
    side: str = "borrower",
    show: str = "deals",
    scope: str = "tagged",
):
    conn = db.get_conn()
    show = show if show in _DD_SHOW else "deals"
    scope = scope if scope in _DD_SCOPE else "tagged"
    side = side if side in _DD_SIDE else "borrower"
    dtype = type if type in _DD_TYPES else ""
    stage = stage if stage in _DD_STAGES else ""
    ctx = {"request": request, "is_admin": auth.is_logged_in(request), "page": "debt",
           "rows": [], "total": 0, "releases": 0, "tickers": [], "selected_ticker": ticker or "",
           "days": days, "dtype": dtype, "stage": stage, "side": side, "show": show, "scope": scope,
           "total_filtered": 0, "pages": 1, "page_no": 1, "pager_url": "/debt-credit", "pager_qs": "",
           "type_options": [("", "All debt")] + [(k, _DD_TYPE_LABELS[k]) for k in _DD_TYPES],
           "stage_options": [("", "Any stage")] + [(k, _DD_STAGE_LABELS[k]) for k in _DD_STAGES]}
    have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='debt_deals'").fetchone()
    if not have:
        # before the first publish there is nothing to show, and the page still answers 200
        return templates.TemplateResponse(request, "debt_credit.html", ctx)

    where, args = ["1=1"], []
    scope_sql = " AND tag_confirmed = 1" if scope == "tagged" else ""
    if scope == "tagged":
        where.append("dd.tag_confirmed = 1")
    if show != "all":
        where.append("dd.instrument IS NOT NULL")
    if show == "deals" and stage != "interest_paid":
        where.append("dd.latest = 1")                    # interest payments sit on a chain below its latest stage
    if side != "all":
        # marker rows (no instrument) have no side; they show under every side when show=all
        where.append("(dd.side = ? OR dd.instrument IS NULL)")
        args.append(side)
    if ticker:
        where.append("dd.ticker = ?")
        args.append(ticker)
    if dtype:
        where.append("dd.instrument = ?")
        args.append(dtype)
    if stage:
        where.append("dd.stage = ?")
        args.append(stage)
    if days and days > 0:
        from datetime import datetime as _dt_dd, timedelta as _td_dd
        where.append("dd.published_at >= ?")
        args.append((_dt_dd.utcnow() - _td_dd(days=days)).strftime("%Y-%m-%d"))
    clause = " AND ".join(where)

    total_filtered = conn.execute("SELECT COUNT(*) FROM debt_deals dd WHERE " + clause, args).fetchone()[0]
    pages, page_no, _off = _paginate(total_filtered, page)
    rows = list(conn.execute(
        "SELECT event_id, ordinal, ticker, slug, raw_headline, published_at, instrument, stage, side, principal, "
        "       principal_total, currency, rate_pct, rate_text, maturity, term_months, lender, borrower, related_party, "
        "       secured, conversion_price, conversion_text, warrants, warrant_strike, project, date, chain_items, "
        "       first_reported, latest, n_rows, tag_confirmed "
        "FROM debt_deals dd WHERE " + clause +
        " ORDER BY published_at DESC, event_id, ordinal LIMIT ? OFFSET ?", args + [_PAGE_SIZE, _off]))

    decorated, last_event = [], None
    for r in rows:
        d = dict(r)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        d["first_of_release"] = d.get("event_id") != last_event
        last_event = d.get("event_id")
        decorated.append(d)

    side_sql = "" if side == "all" else " AND side = '%s'" % side      # side is one of _DD_SIDE, never user text
    ctx.update(
        rows=decorated, total_filtered=total_filtered, pages=pages, page_no=page_no,
        total=conn.execute("SELECT COUNT(*) FROM debt_deals WHERE instrument IS NOT NULL AND latest=1"
                           + scope_sql + side_sql).fetchone()[0],
        releases=conn.execute("SELECT COUNT(DISTINCT event_id) FROM debt_deals WHERE instrument IS NOT NULL"
                              + scope_sql + side_sql).fetchone()[0],
        tickers=[r[0] for r in conn.execute("SELECT DISTINCT ticker FROM debt_deals WHERE ticker IS NOT NULL AND "
                                            "instrument IS NOT NULL" + scope_sql + side_sql + " ORDER BY ticker")],
        pager_qs=(("&ticker=" + ticker) if ticker else "") + (("&days=" + str(days)) if days else "")
                 + (("&type=" + dtype) if dtype else "") + (("&stage=" + stage) if stage else "")
                 + (("&side=" + side) if side != "borrower" else "")
                 + (("&show=" + show) if show != "deals" else "") + (("&scope=" + scope) if scope != "tagged" else ""))
    return templates.TemplateResponse(request, "debt_credit.html", ctx)


# The page prints types and stages with the publisher's own labels, so they read the same everywhere.
from portal.debt_publish import TYPE_LABELS as _DD_TYPE_LABELS, STAGE_LABELS as _DD_STAGE_LABELS  # noqa: E402

_DD_SYM = {"USD": "US$", "AUD": "A$", "CAD": "C$", "GBP": "£", "EUR": "€"}


def _dd_money(v, cur=None):
    if v is None:
        return ""
    sym = _DD_SYM.get(cur or "CAD", "$")
    if v >= 1e9:
        return ("%s%.2fB" % (sym, v / 1e9)).replace(".00B", "B")
    if v >= 1e6:
        return ("%s%.2fM" % (sym, v / 1e6)).replace(".00M", "M")
    return "%s%s" % (sym, format(int(round(v)), ","))


def _dd_price(v, cur=None):
    if v is None:
        return ""
    return "%s%s" % (_DD_SYM.get(cur or "CAD", "$"), ("%.4f" % v).rstrip("0").rstrip(".") if v < 1 else "%.2f" % v)


def _dd_count(v):
    if v is None:
        return ""
    return ("%.2fM" % (v / 1e6)).replace(".00M", "M") if v >= 1e6 else format(int(round(v)), ",")


def _dd_num(v):
    if v is None:
        return ""
    return ("%.3f" % v).rstrip("0").rstrip(".")


def _dd_term(m):
    if m is None:
        return ""
    m = int(round(m))
    return ("%d-year" % (m // 12)) if m % 12 == 0 and m >= 12 else ("%d-month" % m)


templates.env.filters["dd_type"] = lambda t: _DD_TYPE_LABELS.get(t or "", t or "—")
templates.env.filters["dd_stage"] = lambda s: _DD_STAGE_LABELS.get(s or "", s or "—")
templates.env.filters["dd_money"] = _dd_money
templates.env.filters["dd_price"] = _dd_price
templates.env.filters["dd_count"] = _dd_count
templates.env.filters["dd_num"] = _dd_num
templates.env.filters["dd_term"] = _dd_term
# ====== end /debt-credit route ======

import json as _j_drill
def _from_json(s):
    if not s: return []
    try: return _j_drill.loads(s)
    except Exception: return []
templates.env.filters['from_json'] = _from_json

# RES_V1 (2026-09-18): /resources prints figures with the publisher's own formatters, so a tonnage
# reads the same on the page as in the table it came from and the two cannot drift apart.
from portal.resources_publish import (fmt_tonnes as _res_fmt_t, fmt_grade as _res_fmt_g,   # noqa: E402
                                      fmt_contained as _res_fmt_c)


def _res_t(v):
    return _res_fmt_t(v) or "\u2014"


def _res_grades(s):
    return [x for x in (_res_fmt_g(g) for g in _from_json(s)) if x]


def _res_contained(s):
    return [x for x in (_res_fmt_c(c) for c in _from_json(s)) if x]


templates.env.filters['res_t'] = _res_t
templates.env.filters['res_grades'] = _res_grades
templates.env.filters['res_contained'] = _res_contained

# ---------- JSON endpoints for cross-site embedding (MTP) ----------
@app.get("/api/financings/recent.json")
def api_financings_recent(limit: int = 8):
    limit = max(1, min(limit, 50))
    conn = db.get_conn()
    rows = conn.execute(
        """
        SELECT f.financing_id, f.seed_event_id AS event_id, f.ticker, f.announced_at, f.kind, f.status,
               f.gross_announced, f.gross_closed, f.unit_price,
               e.source_url, e.raw_headline,
               substr(COALESCE(e.raw_body, e.raw_excerpt, ''), 1, 1200) AS raw_excerpt
        FROM financings f
        LEFT JOIN events e ON e.event_id = f.seed_event_id
        WHERE f.announced_at IS NOT NULL
        ORDER BY f.announced_at DESC LIMIT ?
        """,
        (limit,)
    ).fetchall()
    out = [dict(r) for r in rows]
    return JSONResponse(out, headers={"Cache-Control": "public, max-age=300"})


@app.get("/api/drills/recent.json")
def api_drills_recent(limit: int = 8):
    limit = max(1, min(limit, 50))
    conn = db.get_conn()
    rows = conn.execute(
        """
        SELECT d.drill_id, d.event_id, d.ticker, d.project, d.top_hole_id, d.top_grade, d.top_unit,
               d.top_metal, d.top_length_m, d.top_summary, d.n_intercepts, d.raw_headline,
               d.published_at,
               e.source_url,
               substr(COALESCE(e.raw_body, e.raw_excerpt, ''), 1, 1200) AS raw_excerpt
        FROM drill_results d
        LEFT JOIN events e ON e.event_id = d.event_id
        WHERE d.published_at IS NOT NULL
        ORDER BY d.published_at DESC LIMIT ?
        """,
        (limit,)
    ).fetchall()
    out = [dict(r) for r in rows]
    return JSONResponse(out, headers={"Cache-Control": "public, max-age=300"})


@app.get("/api/resources/recent.json")
def api_resources_recent(limit: int = 8):
    limit = max(1, min(limit, 50))
    conn = db.get_conn()
    rows = conn.execute(
        """
        SELECT r.res_id, r.event_id, r.ticker, r.project, r.summary, r.headline_oz_au, r.headline_t_metal,
               r.metal_focus, r.mre_type, r.raw_headline, r.published_at,
               e.source_url,
               substr(COALESCE(e.raw_body, e.raw_excerpt, ''), 1, 1200) AS raw_excerpt
        FROM resource_estimates r
        LEFT JOIN events e ON e.event_id = r.event_id
        WHERE r.published_at IS NOT NULL
          -- RES_V1 (2026-09-18): the table now holds one row per deposit per category.
          -- MineTerminalPro reads this endpoint expecting one row per release, so it gets the
          -- first row of each; without this, eight "recent" rows could come off two releases.
          -- RES_PAGE_V2 (2026-09-18): the table also holds a marker row for each tagged
          -- release that states no figures. This feed is a list of resource estimates, so the
          -- markers are not part of it.
          AND r.category IS NOT NULL
          AND r.ordinal = (SELECT MIN(x.ordinal) FROM resource_estimates x
                           WHERE x.event_id = r.event_id AND x.category IS NOT NULL)
        ORDER BY r.published_at DESC LIMIT ?
        """,
        (limit,)
    ).fetchall()
    out = [dict(r) for r in rows]
    return JSONResponse(out, headers={"Cache-Control": "public, max-age=300"})




# ===== MTP_EVENT_DETAIL_V25_BEGIN — JSON endpoint for full-article modal =====
@app.get("/api/event/{event_id}.json")
def api_event_detail(event_id: str):
    """Return one event's full headline + body for cross-site article modal."""
    conn = db.get_conn()
    row = conn.execute(
        "SELECT event_id, ticker, raw_headline, raw_body, raw_html, raw_excerpt, "
        "source_url, source_name, published_at, slug, categories "
        "FROM events WHERE event_id = ?",
        (event_id,)
    ).fetchone()
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    d = dict(row)
    return JSONResponse(d, headers={"Cache-Control": "public, max-age=600"})
# ===== MTP_EVENT_DETAIL_V25_END =====

@app.get("/api/companies/stage-signals.json")
def api_companies_stage_signals():
    """Return ticker -> {has_resource, has_economic_study, n_drill_results}."""
    import re as _re
    conn = db.get_conn()
    out = {}
    # 1. resource_estimates table — strong signal
    # RES_V1 (2026-09-18): a release now has several rows, so this counts releases, not rows
    # RES_PAGE_V2 (2026-09-18): markers are tagged releases that state no figures, so they do
    # not make a company look like it has a resource
    for row in conn.execute("SELECT ticker, COUNT(DISTINCT event_id) FROM resource_estimates "
                            "WHERE category IS NOT NULL GROUP BY ticker"):
        tk = row[0]
        if not tk: continue
        out.setdefault(tk, {})["has_resource"] = True
        out[tk]["resource_table_n"] = row[1]
    # 2. events with Resource Estimates category
    for row in conn.execute("SELECT ticker, COUNT(*) FROM events WHERE categories LIKE '%Resource Estimates%' GROUP BY ticker"):
        tk = row[0]
        if not tk: continue
        out.setdefault(tk, {})["has_resource"] = True
        out[tk]["resource_event_n"] = row[1]
    # 3. economic study — text-match event titles for PEA/PFS/FS keywords
    pat = _re.compile(r"\b(PEA|PFS|DFS|preliminary[- ]economic[- ]assessment|pre[- ]?feasibility|definitive[- ]feasibility|feasibility[- ]study)\b", _re.IGNORECASE)
    for row in conn.execute("SELECT ticker, raw_headline FROM events WHERE published_at >= date('now','-3 years') AND raw_headline IS NOT NULL"):
        tk, head = row
        if tk and head and pat.search(head):
            out.setdefault(tk, {})["has_economic_study"] = True
            out[tk]["economic_study_n"] = out[tk].get("economic_study_n", 0) + 1
    # 4. n_drill_results from drill_results table
    for row in conn.execute("SELECT ticker, COUNT(*) FROM drill_results GROUP BY ticker"):
        tk = row[0]
        if not tk: continue
        out.setdefault(tk, {})["n_drill_results"] = row[1]
    return JSONResponse(out, headers={"Cache-Control": "public, max-age=600"})


# --- admin API (added 2026-05-04) ---
from portal.admin import router as admin_router
app.include_router(admin_router)


# ====== MTP company links (appended) ======
"""MNT_MTP_TICKER_LINKS_V1 — link the ticker column through to a company's
Overview page on MineTerminalPro.

Two facts drive the design:
  * MNT stores tickers with an exchange suffix ("ACRE.CN"); MTP stores them
    bare ("ACRE"), with the exchange in its own field. The suffix has to be
    stripped or the link resolves to nothing.
  * MTP covers only part of our universe (CSE plus a handful of TSXV). A
    ticker it does not hold falls back to MTP's company directory, i.e. a
    click that does not do what it promised. So a link is rendered only for
    tickers MTP actually has; the rest stay plain text.

The company list comes from MinePortal on this same box — the source MTP
itself renders from. It is cached on disk and refreshed on a background
thread, so a page render never waits on a network call and a restart does
not lose the list. If the list is unavailable the filter returns "" and every
ticker renders as plain text: it degrades to today's behaviour, not to
broken links.
"""
import json as _json_mtp
import os as _os_mtp
import threading as _thr_mtp
import time as _time_mtp
import urllib.request as _req_mtp

_MTP_COMPANY_URL = "https://mineterminalpro.com/companies/"
_MTP_SOURCE_URL = "http://127.0.0.1:8090/api/companies"
_MTP_CACHE_PATH = "/var/lib/mnt-portal/mtp-companies.json"
_MTP_TTL_S = 6 * 3600
_MTP_FETCH_TIMEOUT_S = 10

_mtp_state = {"tickers": frozenset(), "fetched_at": 0.0, "refreshing": False}
_mtp_lock = _thr_mtp.Lock()


def _mtp_base_ticker(value):
    """'ACRE.CN' -> 'ACRE'. MTP keys companies on the bare symbol."""
    if not value:
        return ""
    return str(value).strip().upper().split(".")[0]


def _mtp_parse(payload):
    rows = payload.get("companies") if isinstance(payload, dict) else payload
    out = set()
    for row in rows or []:
        if isinstance(row, dict):
            base = _mtp_base_ticker(row.get("ticker"))
            if base:
                out.add(base)
    return frozenset(out)


def _mtp_read_cache():
    try:
        with open(_MTP_CACHE_PATH) as fh:
            blob = _json_mtp.load(fh)
        return frozenset(blob.get("tickers") or []), float(blob.get("fetched_at") or 0.0)
    except Exception:
        return frozenset(), 0.0


def _mtp_write_cache(tickers, fetched_at):
    try:
        _os_mtp.makedirs(_os_mtp.path.dirname(_MTP_CACHE_PATH), exist_ok=True)
        tmp = _MTP_CACHE_PATH + ".tmp"
        with open(tmp, "w") as fh:
            _json_mtp.dump({"tickers": sorted(tickers), "fetched_at": fetched_at}, fh)
        _os_mtp.replace(tmp, _MTP_CACHE_PATH)
    except Exception as exc:
        log.warning("mtp company cache write failed: %s", exc)


def _mtp_refresh():
    """Background thread only — never called on a request path."""
    try:
        with _req_mtp.urlopen(_MTP_SOURCE_URL, timeout=_MTP_FETCH_TIMEOUT_S) as resp:
            payload = _json_mtp.loads(resp.read().decode("utf-8"))
        tickers = _mtp_parse(payload)
        if not tickers:
            log.warning("mtp company list came back empty; keeping previous")
            return
        now = _time_mtp.time()
        with _mtp_lock:
            _mtp_state["tickers"] = tickers
            _mtp_state["fetched_at"] = now
        _mtp_write_cache(tickers, now)
        log.info("mtp company list refreshed: %d tickers", len(tickers))
    except Exception as exc:
        log.warning("mtp company list refresh failed: %s", exc)
    finally:
        with _mtp_lock:
            _mtp_state["refreshing"] = False


def _mtp_tickers():
    with _mtp_lock:
        tickers = _mtp_state["tickers"]
        stale = (_time_mtp.time() - _mtp_state["fetched_at"]) > _MTP_TTL_S
        start = stale and not _mtp_state["refreshing"]
        if start:
            _mtp_state["refreshing"] = True
    if start:
        _thr_mtp.Thread(target=_mtp_refresh, name="mtp-companies", daemon=True).start()
    return tickers


# MTP's company page is split into sections, each with its own address (D1).
# Slugs verified against the live tab strip 2026-09-08. "capital" was renamed
# to "insider-sales" on 2026-09-07 and financings moved to a Financials
# sub-page; old /capital links still redirect, but we target the current names.
_MTP_SECTION_PATHS = {
    "overview": "",
    "economic-study": "/economic-study",
    "mining": "/mining",
    "news": "/news",
    "financials": "/financials",
    "financings": "/financials/financings",
    "management": "/management",
    "insider-sales": "/insider-sales",
    "sedar": "/sedar",
}


def _mtp_company_url(ticker, section=None):
    """Jinja filter. MTP URL for a company, or "" when MTP has no page for it.

    The optional section sends the reader to the part of the company page that
    matches the row they clicked (H6) rather than always to Overview. An
    unrecognised section falls back to Overview rather than inventing an
    address that does not exist -- a general link beats a broken one.
    """
    base = _mtp_base_ticker(ticker)
    if not base or base not in _mtp_tickers():
        return ""
    key = (section or "overview").strip().lower()
    path = _MTP_SECTION_PATHS.get(key)
    if path is None:
        log.warning("unknown MTP section %r; linking to Overview", section)
        path = ""
    return _MTP_COMPANY_URL + base + path


_mtp_state["tickers"], _mtp_state["fetched_at"] = _mtp_read_cache()
templates.env.filters["mtp_url"] = _mtp_company_url
_mtp_tickers()  # cold cache -> kicks off the first background refresh
# ====== end MTP company links ======


# ====== search index (appended) ======
"""MNT_SEARCH_FTS_V1 - /search backed by an FTS5 index instead of a full scan.

Before: `raw_headline/raw_body LIKE '%term%'` read every approved article on
every search - 15,815 rows, ~124 MB of body text - and `SELECT *` additionally
pulled `raw_html` (214 MB across the table) that the results list never
renders. Measured 1.35-1.93s per search at the origin.

After: an FTS5 index (`events_fts`, external-content over `events`) kept
current by three triggers, plus the narrow column list PERF_A14 added for
exactly this reason.

Two deliberate choices, both Justin's:
  * Word-start matching, so "gold" still finds Goldfield and Goldcorp but no
    longer matches inside "marigold". The alternative, a trigram index,
    preserves substring matching exactly at 2-3x the index size.
  * Newest first, unchanged. FTS5 offers relevance ranking (bm25); keeping
    published_at DESC means the only change a reader notices is the speed.

The schema is created here as well as by hand so a database rebuilt from
scratch gets the index instead of silently reverting to a full scan - the
mistake recorded as H3 against the H1 index fix.
"""
import threading as _thr_fts

# Letters and digits only. Everything else is punctuation to the tokenizer, and
# letting it through would be FTS5 query syntax rather than search text.
_FTS_TERM_RE = re.compile(r"[0-9A-Za-z\u00c0-\u024f]+")

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    raw_headline, raw_body, ticker,
    content='events', content_rowid='rowid'
);
CREATE TRIGGER IF NOT EXISTS events_fts_ai AFTER INSERT ON events BEGIN
  INSERT INTO events_fts(rowid, raw_headline, raw_body, ticker)
  VALUES (new.rowid, new.raw_headline, new.raw_body, new.ticker);
END;
CREATE TRIGGER IF NOT EXISTS events_fts_ad AFTER DELETE ON events BEGIN
  INSERT INTO events_fts(events_fts, rowid, raw_headline, raw_body, ticker)
  VALUES ('delete', old.rowid, old.raw_headline, old.raw_body, old.ticker);
END;
CREATE TRIGGER IF NOT EXISTS events_fts_au AFTER UPDATE ON events BEGIN
  INSERT INTO events_fts(events_fts, rowid, raw_headline, raw_body, ticker)
  VALUES ('delete', old.rowid, old.raw_headline, old.raw_body, old.ticker);
  INSERT INTO events_fts(rowid, raw_headline, raw_body, ticker)
  VALUES (new.rowid, new.raw_headline, new.raw_body, new.ticker);
END;
"""

_SEARCH_COLS = ", ".join("e." + _c.strip() for _c in db.LIST_EVENT_COLUMNS.split(","))

_SEARCH_SQL_FTS = (
    "SELECT " + _SEARCH_COLS + " FROM events_fts "
    "JOIN events e ON e.rowid = events_fts.rowid "
    "WHERE events_fts MATCH ? AND e.review_status='auto_approved' "
    "ORDER BY e.published_at DESC LIMIT 200"
)

_SEARCH_SQL_LIKE = (
    "SELECT " + _SEARCH_COLS + " FROM events e "
    "WHERE e.review_status='auto_approved' "
    "  AND (e.raw_headline LIKE ? OR e.raw_body LIKE ? OR e.ticker LIKE ?) "
    "ORDER BY e.published_at DESC LIMIT 200"
)


def _fts_match_query(q):
    """User text -> a safe FTS5 MATCH expression, or "" if there is nothing to search.

    Every term is quoted, so FTS5 operators a visitor happens to type - AND, OR,
    NOT, -, *, quotes, parentheses - are treated as text rather than syntax. The
    trailing * on each term is what gives word-start matching.
    """
    terms = _FTS_TERM_RE.findall(q or "")
    return " ".join('"%s"*' % t for t in terms[:12])


def _fts_rebuild():
    """Background only - a full rebuild takes ~15s and holds a write lock."""
    try:
        conn = db.get_conn()
        conn.execute("INSERT INTO events_fts(events_fts) VALUES('rebuild')")
        conn.commit()
        log.info("events_fts rebuilt")
    except Exception as exc:
        log.warning("events_fts rebuild failed: %s", exc)


def _fts_ensure_schema():
    try:
        conn = db.get_conn()
        conn.executescript(_FTS_SCHEMA)
        conn.commit()
        # count(*) on an external-content FTS table reads through to the CONTENT
        # table, so it reports the full row count even when the index is empty
        # and cannot be used as a population check. This cost one wasted build
        # on 2026-09-08. The index's own storage is events_fts_data; an empty
        # index holds <= 2 rows there.
        blocks = conn.execute("SELECT COUNT(*) FROM events_fts_data").fetchone()[0]
        if blocks <= 2 and conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]:
            log.warning("events_fts is empty; rebuilding in the background")
            _thr_fts.Thread(target=_fts_rebuild, name="events-fts-rebuild",
                            daemon=True).start()
    except Exception as exc:
        log.warning("events_fts schema check failed: %s", exc)


_orig_search_page = search_page


def search_page(request: Request, q: str = ""):  # noqa: F811
    q = (q or "").strip()
    rows = []
    if q:
        conn = db.get_conn()
        match = _fts_match_query(q)
        if match:
            try:
                rows = list(conn.execute(_SEARCH_SQL_FTS, (match,)))
            except Exception as exc:
                # A search must never 500. Fall back to the old scan: slow, but
                # correct, and it keeps working if the index is ever dropped.
                log.warning("fts search failed for %r, falling back to scan: %s", q, exc)
                pattern = "%" + q + "%"
                rows = list(conn.execute(_SEARCH_SQL_LIKE, (pattern, pattern, pattern)))
    return templates.TemplateResponse(request, "search.html", {
        "request": request,
        "q": q,
        "events": rows,
        "page": "search",
        "is_admin": auth.is_logged_in(request),
    })


app.routes[:] = [r for r in app.routes if not (
    getattr(r, "path", None) == "/search"
    and getattr(r, "endpoint", None) is _orig_search_page
)]
app.get("/search", response_class=HTMLResponse)(search_page)

_fts_ensure_schema()
# ====== end search index ======


# ====== /management-changes tab (appended 2026-09-14) ======
# MGMT_PUBLISH_V1 (2026-09-17): management_changes now holds ONE ROW PER PERSON, written by
# portal/management_publish.py from the active management reader. The role column carries the
# release's own wording and role_canon the one spelling the filter uses, so a role filter is
# possible for the first time (the old table spelled one role six ways).
import urllib.parse as _urlparse_mgmt

_MGMT_SCOPES = ("management", "board", "advisory")
_MGMT_ACTIONS = ("appointed", "departed", "changed")
# MGMT_V1 1.1: the page's three filters cover the reader's six actions
_MGMT_ACTION_GROUPS = {"appointed": ("appointed",), "departed": ("departed", "resigned", "retired"),
                       "changed": ("changed", "promoted")}


@app.get("/management-changes", response_class=HTMLResponse)
def management_changes_page(
    request: Request,
    ticker: str = None,
    scope: str = None,
    action: str = None,
    role: str = None,
    page: int = 1,
):
    conn = db.get_conn()
    where, args = [], []
    if ticker:
        where.append("ticker = ?")
        args.append(ticker)
    if scope in _MGMT_SCOPES:
        where.append("scope = ?")
        args.append(scope)
    if action in _MGMT_ACTIONS:
        acts = _MGMT_ACTION_GROUPS[action]
        where.append("action IN (%s)" % ",".join("?" * len(acts)))
        args.extend(acts)
    has_canon = False
    try:
        has_canon = "role_canon" in {r[1] for r in conn.execute("PRAGMA table_info(management_changes)")}
    except Exception:
        has_canon = False
    if role and has_canon:
        where.append("role_canon = ?")
        args.append(role)
    sql = "SELECT * FROM management_changes"
    if where:
        sql += " WHERE " + " AND ".join(where)
    try:
        _cnt = "SELECT COUNT(*) FROM management_changes"
        if where:
            _cnt += " WHERE " + " AND ".join(where)
        total_filtered = conn.execute(_cnt, args).fetchone()[0]
        pages, page_no, _off = _paginate(total_filtered, page)
        # one row per person, so the release's people stay together and in the order it named them
        sql += (" ORDER BY published_at DESC, event_id DESC, ordinal ASC LIMIT ? OFFSET ?"
                if has_canon else " ORDER BY published_at DESC, mgmt_id DESC LIMIT ? OFFSET ?")
        rows = list(conn.execute(sql, args + [_PAGE_SIZE, _off]))
        total = conn.execute("SELECT COUNT(*) FROM management_changes").fetchone()[0]
        tickers = [r[0] for r in conn.execute(
            "SELECT DISTINCT ticker FROM management_changes "
            "WHERE ticker IS NOT NULL ORDER BY ticker")]
        roles = sorted(r[0] for r in conn.execute(      # the forty commonest, listed alphabetically
            "SELECT role_canon FROM management_changes WHERE role_canon IS NOT NULL "
            "GROUP BY role_canon HAVING COUNT(*) >= 5 ORDER BY COUNT(*) DESC LIMIT 40")) if has_canon else []
    except Exception:
        # the table is created by portal/management_publish.py; an empty page is a
        # better answer than a 500 if the first run has not happened yet
        rows, total, tickers, roles = [], 0, [], []
        total_filtered, pages, page_no = 0, 1, 1

    return templates.TemplateResponse(request, "management.html", {
        "request": request,
        "page": "management",
        "rows": rows,
        "total": total,
        "tickers": tickers,
        "roles": roles,
        "selected_ticker": ticker,
        "selected_action": action,
        "selected_role": role,
        "scope": scope,
        "total_filtered": total_filtered,
        "pages": pages,
        "page_no": page_no,
        "pager_url": "/management-changes",
        "pager_qs": (("&ticker=" + ticker) if ticker else "")
                    + (("&scope=" + scope) if scope else "")
                    + (("&action=" + action) if action else "")
                    + (("&role=" + _urlparse_mgmt.quote(role)) if role else ""),
    })



# ====== generic category pages (appended 2026-09-15) ======
# One list page per category, driven entirely by events.categories. The count
# shown here and the count on the front-page chip are the same query, so they
# cannot disagree. No default date window, no extra status filter, and the true
# total is always stated rather than silently truncated.
_CATEGORY_PAGES = [
    ("/mergers-acquisitions", "Mergers & Acquisitions", "mna"),
    ("/share-capital", "Share Capital & Compensation", "sharecap"),
]
_CAT_PAGE_SIZE = 100


def _cat_where(cat, ticker=None):
    """WHERE clause matching one category as a pipe-delimited token."""
    where = [
        "review_status = 'auto_approved'",
        "(categories = ? OR categories LIKE ? OR categories LIKE ? "
        " OR categories LIKE ?)",
    ]
    args = [cat, cat + "|%", "%|" + cat, "%|" + cat + "|%"]
    if ticker:
        where.append(
            "(ticker = ? OR ('|' || COALESCE(additional_tickers, '') || '|') LIKE ?)"
        )
        args.extend([ticker, "%|" + ticker + "|%"])
    return " AND ".join(where), args


# ====== MNT_SPEED_V1 (2026-09-25): short cache for counts and company lists ======
# The count and the company dropdown on each list page only change when news arrives, but each one read
# every release on every request. Cached per worker for 5 minutes, like the homepage chip counts.
import time as _time_speed
_SPEED_TTL = 300.0
_speed_cache = {}


def _speed_cached(key, fn):
    now = _time_speed.monotonic()
    hit = _speed_cache.get(key)
    if hit is not None and now - hit[0] < _SPEED_TTL:
        return hit[1]
    val = fn()
    if len(_speed_cache) > 5000:
        _speed_cache.clear()
    _speed_cache[key] = (now, val)
    return val
# ====== end MNT_SPEED_V1 cache ======


def _make_category_page(url, cat_name, page_key):
    def _page(request: Request, ticker: str = None, page: int = 1):
        conn = db.get_conn()
        clause, args = _cat_where(cat_name, ticker)
        total = _speed_cached(("cat_total", cat_name, ticker or ""), lambda: conn.execute(
            "SELECT COUNT(*) FROM events WHERE " + clause, args
        ).fetchone()[0])
        pages = max(1, (total + _CAT_PAGE_SIZE - 1) // _CAT_PAGE_SIZE)
        page_no = min(max(1, page), pages)
        offset = (page_no - 1) * _CAT_PAGE_SIZE
        events = list(conn.execute(
            "SELECT " + db.LIST_EVENT_COLUMNS + " FROM events WHERE " + clause
            + " ORDER BY COALESCE(published_at, classified_at) DESC "
              "LIMIT ? OFFSET ?",
            args + [_CAT_PAGE_SIZE, offset],
        ))
        tclause, targs = _cat_where(cat_name)
        tickers = _speed_cached(("cat_tickers", cat_name), lambda: [r[0] for r in conn.execute(
            "SELECT DISTINCT ticker FROM events WHERE " + tclause
            + " AND ticker IS NOT NULL ORDER BY ticker", targs)])
        return templates.TemplateResponse(request, "category.html", {
            "request": request,
            "page": page_key,
            "cat_name": cat_name,
            "cat_url": url,
            "events": events,
            "total": total,
            "pages": pages,
            "page_no": page_no,
            "first_n": offset + 1 if total else 0,
            "last_n": offset + len(events),
            "tickers": tickers,
            "selected_ticker": ticker,
            "is_admin": auth.is_logged_in(request),
        })

    _page.__name__ = "category_page_" + page_key
    return _page


for _cat_url, _cat_name, _cat_key in _CATEGORY_PAGES:
    app.get(_cat_url, response_class=HTMLResponse)(
        _make_category_page(_cat_url, _cat_name, _cat_key)
    )
# ====== end generic category pages ======


# ====== pagination helper (appended 2026-09-15) ======
# Shared by /financings, /drills, /resources and /management-changes, which all
# used to end in "LIMIT 500" and say nothing when they hit it.
_PAGE_SIZE = 200


def _paginate(total, page):
    """-> (pages, clamped page number, offset)."""
    try:
        page = int(page or 1)
    except (TypeError, ValueError):
        page = 1
    pages = max(1, (int(total or 0) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page_no = min(max(1, page), pages)
    return pages, page_no, (page_no - 1) * _PAGE_SIZE
# ====== end pagination helper ======

# RELFMT_V1 (2026-10-02): table polish on wire HTML; rebuilt PDF HTML / reflowed text
# for exchange (TMX/CSE) releases that have no HTML. See release_format.py.
from portal.release_format import pdf_html_for as _rf_pdf_html, reflow_text_html as _rf_reflow, polish_tables as _rf_polish


def _rf_clean_html(h, source_url=""):
    return _rf_polish(clean_release_html(h, source_url))


templates.env.filters["clean_html"] = _rf_clean_html
templates.env.filters["pdf_html"] = _rf_pdf_html
templates.env.filters["reflow_text"] = _rf_reflow
