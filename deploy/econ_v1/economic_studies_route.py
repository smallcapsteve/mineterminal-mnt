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
