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
    db.init_schema()
    try:
        n = backfill.run()
        if n:
            log.info("startup backfill: %d events", n)
    except Exception as e:
        log.exception("backfill failed: %s", e)


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
        limit=100,
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


@app.get("/financings", response_class=HTMLResponse)
def financings_page(
    request: Request,
    ticker: str | None = None,
    status: str | None = None,
    state: str | None = "open",
):
    conn = db.get_conn()
    where, args = [], []
    if ticker:
        where.append("ticker = ?")
        args.append(ticker)
    if status:
        where.append("status = ?")
        args.append(status)
    else:
        where.append("status != ?")
        args.append("mention")
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
    sql += " ORDER BY last_update_at DESC, financing_id DESC LIMIT 500"
    rows = list(conn.execute(sql, args))

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
        "state": status or "open",
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
    """XML sitemap — submit to Google Search Console & Bing Webmaster Tools."""
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT ticker, slug, published_at FROM events "
        "WHERE review_status='auto_approved' "
        "  AND slug IS NOT NULL AND slug != '' "
        "  AND ticker IS NOT NULL "
        "ORDER BY published_at DESC"
    ).fetchall()

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

    # Static pages
    out.append(f'  <url><loc>{_SITE_BASE}/</loc>'
               f'<changefreq>hourly</changefreq><priority>1.0</priority></url>')
    out.append(f'  <url><loc>{_SITE_BASE}/financings</loc>'
               f'<changefreq>daily</changefreq><priority>0.8</priority></url>')

    for r in rows:
        ticker = (r["ticker"] or "").lower()
        slug = r["slug"]
        if not ticker or not slug:
            continue
        loc = f"{_SITE_BASE}/news/{ticker}/{slug}"
        lastmod = (r["published_at"] or "")[:10] or ""
        if lastmod:
            out.append(f'  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod></url>')
        else:
            out.append(f'  <url><loc>{loc}</loc></url>')

    out.append('</urlset>')
    return _SeoResponse("\n".join(out), media_type="application/xml")


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


def _log_pageview(request, event_id=None, ticker=None):
    """Log a pageview. Catches all errors — must never break a request."""
    try:
        ua = request.headers.get("user-agent") or ""
        is_bot = 1 if _BOT_UA_RE.search(ua) else 0
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
        raise HTTPException(404)
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
def financings_page(request: Request, ticker: str | None = None, status: str | None = None, state: str | None = "open"):  # noqa: F811
    _log_pageview(request, ticker=ticker)
    return _orig_fin(request, ticker=ticker, status=status, state=state)
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


@app.get("/drills", response_class=HTMLResponse)
def drills_page(
    request: Request,
    ticker: str | None = None,
    days: int = 90,
):
    """Drill results lifecycle table — top intercepts grouped by company."""
    conn = db.get_conn()
    where, args = [], []
    if ticker:
        where.append("dr.ticker = ?")
        args.append(ticker)
    if days and days > 0:
        cutoff = (_dt_drill.utcnow() - _td_drill(days=days)).strftime("%Y-%m-%d")
        where.append("substr(dr.published_at, 1, 10) >= ?")
        args.append(cutoff)
    sql = (
        "SELECT dr.*, e.slug FROM drill_results dr "
        "LEFT JOIN events e ON e.event_id = dr.event_id "
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY dr.published_at DESC LIMIT 500"
    rows = list(conn.execute(sql, args))

    decorated = []
    for r in rows:
        d = dict(r)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        # Build URL to article
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        decorated.append(d)

    total = conn.execute("SELECT COUNT(*) FROM drill_results").fetchone()[0]
    distinct_tickers = list(conn.execute(
        "SELECT DISTINCT ticker FROM drill_results "
        "WHERE ticker IS NOT NULL ORDER BY ticker"
    ))
    tickers_list = [r[0] for r in distinct_tickers]

    return templates.TemplateResponse(request, "drills.html", {
        "request": request,
        "is_admin": auth.is_logged_in(request),
        "page": "drills",
        "rows": decorated,
        "total": total,
        "tickers": tickers_list,
        "selected_ticker": ticker or "",
        "days": days,
    })
# ====== end drills route ======


# ====== /resources route (Resource Estimates) (appended) ======
@app.get("/resources", response_class=HTMLResponse)
def resources_page(
    request: Request,
    ticker: str | None = None,
    days: int = 365,
):
    conn = db.get_conn()
    where, args = [], []
    if ticker:
        where.append("re.ticker = ?")
        args.append(ticker)
    if days and days > 0:
        from datetime import datetime as _dt_res, timedelta as _td_res
        cutoff = (_dt_res.utcnow() - _td_res(days=days)).strftime("%Y-%m-%d")
        where.append("substr(re.published_at, 1, 10) >= ?")
        args.append(cutoff)
    sql = (
        "SELECT re.*, e.slug FROM resource_estimates re "
        "LEFT JOIN events e ON e.event_id = re.event_id "
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY re.published_at DESC LIMIT 500"
    rows = list(conn.execute(sql, args))

    decorated = []
    for r in rows:
        d = dict(r)
        d["company_name"] = _ticker_to_name(d.get("ticker") or "") or (d.get("ticker") or "")
        if d.get("ticker") and d.get("slug"):
            d["url"] = f"/news/{d['ticker'].lower()}/{d['slug']}"
        elif d.get("event_id"):
            d["url"] = f"/event/{d['event_id']}"
        else:
            d["url"] = ""
        decorated.append(d)

    total = conn.execute("SELECT COUNT(*) FROM resource_estimates").fetchone()[0]
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
        "tickers": [r[0] for r in distinct_tickers],
        "selected_ticker": ticker or "",
        "days": days,
    })
# ====== end /resources route ======

import json as _j_drill
def _from_json(s):
    if not s: return []
    try: return _j_drill.loads(s)
    except Exception: return []
templates.env.filters['from_json'] = _from_json

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
    for row in conn.execute("SELECT ticker, COUNT(*) FROM resource_estimates GROUP BY ticker"):
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
