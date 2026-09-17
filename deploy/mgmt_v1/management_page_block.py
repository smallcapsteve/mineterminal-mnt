# ====== /management-changes tab (appended 2026-09-14) ======
# MGMT_PUBLISH_V1 (2026-09-17): management_changes now holds ONE ROW PER PERSON, written by
# portal/management_publish.py from the active management reader. The role column carries the
# release's own wording and role_canon the one spelling the filter uses, so a role filter is
# possible for the first time (the old table spelled one role six ways).
import urllib.parse as _urlparse_mgmt

_MGMT_SCOPES = ("management", "board", "advisory")
_MGMT_ACTIONS = ("appointed", "departed", "changed")


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
        where.append("action = ?")
        args.append(action)
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
