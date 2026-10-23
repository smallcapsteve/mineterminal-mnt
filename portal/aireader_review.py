"""MNT_AI_REVIEW_V1 (2026-10-23): /aireader-review, the review list for the AI-reader hybrid.

Lists every row the hybrid holds back (plan: claude/AIREADER_HYBRID_PLAN_2026-10-22.md): rows where the AI reader and
the rules reader disagree on a figure, with what each read and a link to the release. Anyone with the address can read
it (it is not linked and tells search engines not to index it); recording a decision needs the MNT admin login.

Rows come from the AI harness's review database (/var/lib/mnt-aireader-pub/review.db, written by
`python -m aireader export review`), read-only. Decisions go to this site's own small database
(/var/lib/mnt-aireader-pub/decisions/review_decisions.db), keyed by row_key, which stays the same across rebuilds:
  ai     the AI reader is right
  rules  the rules reader is right
  wrong  both are wrong, or the row should not exist
Nothing here changes what the live pages show; the harness reads the decisions when a reader is switched on.

Undo: remove this file, templates/aireader_review.html and the register block in portal/serve.py."""
import json
import os
import sqlite3
import time

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

REVIEW_DB = os.environ.get("MNT_AI_REVIEW_DB", "/var/lib/mnt-aireader-pub/review.db")
DECISIONS_DB = os.environ.get("MNT_AI_DECISIONS_DB", "/var/lib/mnt-aireader-pub/decisions/review_decisions.db")
PAGE = 50
SECTIONS = {"dev": "Mine Development", "wch": "Warrants", "permits": "Permits", "expl": "Exploration", "smp": "Sampling"}
DECISIONS = {"ai": "AI is right", "rules": "Rules are right", "wrong": "Both wrong / not a real row"}
SHOW = ("open", "decided", "all")
FIELD_LABELS = {
    "event_type": "Event", "mine": "Mine", "status": "Status", "event_date": "Date", "pct_complete": "% complete",
    "change": "Change", "n_warrants": "Warrants", "strike_old": "Old price", "strike_new": "New price",
    "expiry_old": "Old expiry", "expiry_new": "New expiry", "issued": "Issued", "n_remaining": "Remaining",
    "permit_type": "Permit type", "project": "Project", "authority": "Authority", "date": "Date",
    "permit_name": "Permit", "program_type": "Program", "metres": "Metres", "holes": "Holes", "budget": "Budget",
    "sample_type": "Sample type", "best_grade": "Best grade", "sample_count": "Samples", "width_m": "Width (m)",
}


def _review():
    if not os.path.exists(REVIEW_DB):
        return None
    c = sqlite3.connect("file:%s?mode=ro" % REVIEW_DB, uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def _decisions(write=False):
    if write:
        os.makedirs(os.path.dirname(DECISIONS_DB), exist_ok=True)
    elif not os.path.exists(DECISIONS_DB):
        return None
    c = sqlite3.connect(DECISIONS_DB, timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS decisions (row_key TEXT PRIMARY KEY, section TEXT, event_id TEXT, "
              "decision TEXT NOT NULL, note TEXT, decided_at TEXT)")
    return c


def _fmt(v):
    if v is None or v == "" or v == []:
        return ""
    if isinstance(v, dict):
        if "value" in v:
            return " ".join(str(x) for x in (v.get("value"), v.get("unit"), v.get("metal")) if x not in (None, ""))
        if "amount" in v:
            return " ".join(str(x) for x in (v.get("amount"), v.get("currency")) if x not in (None, ""))
        return ", ".join("%s %s" % (k, _fmt(x)) for k, x in v.items() if _fmt(x))
    if isinstance(v, list):
        return "; ".join(_fmt(x) for x in v if _fmt(x))
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (int, float)) and abs(v) >= 10000:
        return "{:,}".format(v)
    return str(v)


def _fields(ai):
    out = []
    for k, v in ai.items():
        s = _fmt(v)
        if s and k not in ("evidence", "ordinal", "figures", "figures_json", "anomaly", "next_target"):
            out.append((FIELD_LABELS.get(k, k.replace("_", " ").capitalize()), s[:160]))
    return out[:12]


def register(app, templates):
    from portal import auth
    from portal.app import _ticker_to_name

    @app.get("/aireader-review", response_class=HTMLResponse)
    def aireader_review(request: Request, section: str = "", show: str = "open", ticker: str = "", page: int = 1,
                        saved: str = ""):
        section = section if section in SECTIONS else ""
        show = show if show in SHOW else "open"
        page = max(1, page)
        admin = auth.is_logged_in(request)
        ctx = {"request": request, "is_admin": admin, "page": "aireview", "rows": [], "sections": SECTIONS,
               "decision_labels": DECISIONS, "section": section, "show": show, "ticker": ticker, "page_no": page,
               "pages": 1, "total": 0, "counts": {}, "decided": {}, "built_at": None, "saved": saved, "qs": ""}
        rv = _review()
        if rv is None:
            resp = templates.TemplateResponse(request, "aireader_review.html", ctx)
            resp.headers["X-Robots-Tag"] = "noindex, nofollow"
            return resp
        try:
            have_dec = os.path.exists(DECISIONS_DB)
            if have_dec:
                rv.execute("ATTACH DATABASE ? AS d", ("file:%s?mode=ro" % DECISIONS_DB,))
                have_dec = bool(rv.execute("SELECT 1 FROM d.sqlite_master WHERE name='decisions'").fetchone())
            where, args = ["1=1"], []
            if section:
                where.append("r.section = ?"); args.append(section)
            if ticker:
                where.append("r.ticker = ?"); args.append(ticker.upper())
            if have_dec:
                join = " LEFT JOIN d.decisions x ON x.row_key = r.row_key"
                cols = ", x.decision AS decision, x.note AS note, x.decided_at AS decided_at"
                if show == "open":
                    where.append("x.row_key IS NULL")
                elif show == "decided":
                    where.append("x.row_key IS NOT NULL")
            else:
                join, cols = "", ", NULL AS decision, NULL AS note, NULL AS decided_at"
                if show == "decided":
                    where.append("0")
            clause = " AND ".join(where)
            total = rv.execute("SELECT COUNT(*) FROM review_rows r" + join + " WHERE " + clause, args).fetchone()[0]
            pages = max(1, (total + PAGE - 1) // PAGE)
            page = min(page, pages)
            rows = [dict(r) for r in rv.execute(
                "SELECT r.rid, r.row_key, r.section, r.event_id, r.ticker, r.slug, r.headline, r.published_at, r.level, "
                "r.ai_json, r.disagree_json" + cols + " FROM review_rows r" + join + " WHERE " + clause +
                " ORDER BY r.published_at DESC, r.event_id, r.ordinal LIMIT ? OFFSET ?", args + [PAGE, (page - 1) * PAGE])]
            out = []
            for r in rows:
                ai = json.loads(r["ai_json"] or "{}")
                dis = json.loads(r["disagree_json"] or "{}")
                r["section_label"] = SECTIONS.get(r["section"], r["section"])
                r["company"] = _ticker_to_name(r["ticker"] or "") or (r["ticker"] or "")
                r["url"] = ("/news/%s/%s" % (r["ticker"].lower(), r["slug"])) if r.get("ticker") and r.get("slug") \
                    else "/event/%s" % r["event_id"]
                r["fields"] = _fields(ai)
                r["disagree"] = [(FIELD_LABELS.get(f, f.replace("_", " ").capitalize()), _fmt(d.get("ai")) or "—",
                                  _fmt(d.get("rules")) or "—") for f, d in dis.items()]
                r["decision"] = {"decision": r["decision"], "note": r["note"], "decided_at": r["decided_at"]} \
                    if r.get("decision") else None
                out.append(r)
            counts = {s: {"total": n, "decided": 0} for s, n in
                      rv.execute("SELECT section, COUNT(*) FROM review_rows GROUP BY section")}
            if have_dec:
                for s, n in rv.execute("SELECT r.section, COUNT(*) FROM review_rows r JOIN d.decisions x "
                                       "ON x.row_key = r.row_key GROUP BY r.section"):
                    if s in counts:
                        counts[s]["decided"] = n
            meta = {k: v for k, v in rv.execute("SELECT k, v FROM preview_meta")}
            qs = "".join("&%s=%s" % (k, v) for k, v in (("section", section), ("show", show), ("ticker", ticker)) if v)
            ctx.update(rows=out, total=total, pages=pages, page_no=page, counts=counts, built_at=meta.get("review_built_at"),
                       qs=qs)
        finally:
            rv.close()
        resp = templates.TemplateResponse(request, "aireader_review.html", ctx)
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp

    @app.post("/aireader-review/decide")
    def aireader_review_decide(request: Request, row_key: str = Form(...), decision: str = Form(...),
                               note: str = Form(""), back: str = Form("")):
        if not auth.is_logged_in(request):
            return RedirectResponse("/admin/login", status_code=303)
        dest = back if back.startswith("/aireader-review") else "/aireader-review"
        rv = _review()
        if rv is None or decision not in list(DECISIONS) + ["clear"]:
            return RedirectResponse(dest, status_code=303)
        try:
            r = rv.execute("SELECT section, event_id FROM review_rows WHERE row_key=?", (row_key,)).fetchone()
        finally:
            rv.close()
        if r is None:
            return RedirectResponse(dest, status_code=303)
        dc = _decisions(write=True)
        try:
            if decision == "clear":
                dc.execute("DELETE FROM decisions WHERE row_key=?", (row_key,))
            else:
                dc.execute("INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?)",
                           (row_key, r["section"], r["event_id"], decision, (note or "")[:500],
                            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
            dc.commit()
        finally:
            dc.close()
        sep = "&" if "?" in dest else "?"
        return RedirectResponse(dest + sep + "saved=1#r-" + row_key, status_code=303)
