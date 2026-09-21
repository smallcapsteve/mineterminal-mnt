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
_PROD_KINDS = ("actual", "guidance", "milestone")


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
