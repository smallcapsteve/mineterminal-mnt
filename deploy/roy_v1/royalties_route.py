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
_ROY_ACTIONS = ("new", "transfer", "buyback", "amendment")


@app.get("/royalties-streams", response_class=HTMLResponse)
def royalties_streams_page(
    request: Request,
    ticker: str | None = None,
    days: int = 0,
    page: int = 1,
    type: str = "",
    action: str = "",
    show: str = "deals",
):
    conn = db.get_conn()
    show = show if show in _ROY_SHOW else "deals"
    rtype = type if type in _ROY_TYPES else ""
    action = action if action in _ROY_ACTIONS else ""
    ctx = {"request": request, "is_admin": auth.is_logged_in(request), "page": "royalties",
           "rows": [], "total": 0, "releases": 0, "tickers": [], "selected_ticker": ticker or "",
           "days": days, "rtype": rtype, "action": action, "show": show, "total_filtered": 0, "pages": 1,
           "page_no": 1, "pager_url": "/royalties-streams", "pager_qs": ""}
    have = conn.execute("SELECT 1 FROM sqlite_master WHERE name='royalty_deals'").fetchone()
    if not have:
        # before the first publish there is nothing to show, and the page still answers 200
        return templates.TemplateResponse(request, "royalties_streams.html", ctx)

    where, args = ["1=1"], []
    if show != "all":
        where.append("rd.type IS NOT NULL")
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
        "       n_rows, tag_confirmed "
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
        total=conn.execute("SELECT COUNT(*) FROM royalty_deals WHERE type IS NOT NULL AND is_latest=1").fetchone()[0],
        releases=conn.execute("SELECT COUNT(DISTINCT event_id) FROM royalty_deals WHERE type IS NOT NULL").fetchone()[0],
        tickers=[r[0] for r in conn.execute("SELECT DISTINCT ticker FROM royalty_deals "
                                            "WHERE ticker IS NOT NULL AND type IS NOT NULL ORDER BY ticker")],
        pager_qs=(("&ticker=" + ticker) if ticker else "") + (("&days=" + str(days)) if days else "")
                 + (("&type=" + rtype) if rtype else "") + (("&action=" + action) if action else "")
                 + (("&show=" + show) if show != "deals" else ""))
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
