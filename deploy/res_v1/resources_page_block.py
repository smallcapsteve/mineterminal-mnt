# ====== /resources route (Resource Estimates) (appended) ======
@app.get("/resources", response_class=HTMLResponse)
def resources_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    has: str = "all",
):
    conn = db.get_conn()
    # RES_V1 (2026-09-18): resource_estimates now holds one row per deposit per category, so this
    # LEFT JOIN yields one output row per resource figure, plus one row per tagged release that
    # states none. Driven by the TAG: of 642 tagged releases only about 300 state any figures.
    where, args = _cat_where("Resource Estimates", ticker)
    # TICKER_QUALIFY_V1 (2026-09-16): the joined table also has a ticker column.
    where = where.replace("(ticker = ?", "(e.ticker = ?")
    where = [where]
    if days and days > 0:
        from datetime import datetime as _dt_res, timedelta as _td_res
        cutoff = (_dt_res.utcnow() - _td_res(days=days)).strftime("%Y-%m-%d")
        # RES_PAGER_V1 (2026-09-18): no substr(). Comparing the whole timestamp against a bare
        # date is the same test for ISO-8601 text -- '2026-09-18T11:00' and '2026-09-18' both sort
        # after '2026-09-18' -- and it saves building a new string for all 44,932 rows scanned.
        where.append("COALESCE(e.published_at, e.classified_at) >= ?")
        args.append(cutoff)
    base = " AND ".join(where)
    clause = base + (" AND re.event_id IS NOT NULL" if has == "data" else "")

    # RES_PAGER_V1 (2026-09-18): the pager used to COUNT(*) the LEFT JOIN, which cost 0.64s. The
    # plan was already optimal -- SCAN e, covering-index probe on re -- but the tag test is a LIKE
    # on a built-up string, so it cannot be pushed ahead of the join and the probe ran for all
    # 44,932 events rather than the 672 tagged ones. The same scan WITHOUT the join costs 0.017s.
    #
    # The page shows one row per resource figure, plus one row per tagged release that states
    # none, so the total is an identity that needs no join over events at all:
    #
    #     tagged releases  +  resource rows  -  tagged releases that have rows
    #
    # The last two come off resource_estimates, which is 1,100 rows. Checked against the old count
    # over 168 combinations of ticker, window and filter: identical every time, including releases
    # with no publish date, which fall back to their classified date on one side of the sum only.
    n_rows, n_with_rows = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT re.event_id) FROM resource_estimates re "
        "JOIN events e ON e.event_id = re.event_id WHERE " + base, args).fetchone()
    if has == "data":
        total_filtered = n_rows
    else:
        n_events = conn.execute("SELECT COUNT(*) FROM events e WHERE " + base, args).fetchone()[0]
        total_filtered = n_events + n_rows - n_with_rows
    pages, page_no, _off = _paginate(total_filtered, page)
    sql = (
        "SELECT e.event_id, e.ticker, e.slug, e.raw_headline, "
        "       COALESCE(e.published_at, e.classified_at) AS published_at, "
        "       re.project, re.deposit, re.category, re.tonnes, re.grades_json, "
        "       re.contained_json, re.cut_off, re.basis, re.context, re.summary, "
        "       re.mre_type, re.metal_focus, re.headline_oz_au, re.ordinal, re.n_rows "
        "FROM events e "
        "LEFT JOIN resource_estimates re ON re.event_id = e.event_id "
        "WHERE " + clause +
        " ORDER BY published_at DESC, e.event_id, re.ordinal LIMIT ? OFFSET ?"
    )
    rows = list(conn.execute(sql, args + [_PAGE_SIZE, _off]))
    # the count above already worked this out, and it is the same number
    with_data = n_with_rows

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

    total = conn.execute("SELECT COUNT(*) FROM resource_estimates").fetchone()[0]
    releases = conn.execute("SELECT COUNT(DISTINCT event_id) FROM resource_estimates").fetchone()[0]
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
