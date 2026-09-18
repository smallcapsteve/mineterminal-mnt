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
