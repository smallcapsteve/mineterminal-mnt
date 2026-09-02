#!/usr/bin/env python3
'''MNT portal bootstrap — writes the portal package, templates, static files,
systemd unit, and seeds the admin password hash + session secret into .env.

Safe to re-run; file contents are overwritten but .env is only appended to
when MNT_ADMIN_PASSWORD_HASH / MNT_SESSION_SECRET are missing.
'''
from __future__ import annotations
import os
import secrets
import sys
import textwrap
from pathlib import Path

APP_ROOT = Path("/opt/mnt/app")
PORTAL = APP_ROOT / "portal"
TEMPLATES = PORTAL / "templates"
STATIC = PORTAL / "static"
SYSTEMD = Path("/etc/systemd/system/mnt-portal.service")
ENV_FILE = APP_ROOT / ".env"

FILES: dict[Path, str] = {}


def f(path: Path, body: str) -> None:
    FILES[path] = textwrap.dedent(body).lstrip("\n")


# --------------------------------------------------------------------------
# portal/__init__.py
# --------------------------------------------------------------------------
f(PORTAL / "__init__.py", "")

# --------------------------------------------------------------------------
# portal/db.py
# --------------------------------------------------------------------------
f(PORTAL / "db.py", r'''
    from __future__ import annotations
    import os
    import sqlite3
    import threading
    from pathlib import Path
    from typing import Iterator

    DB_PATH = Path(os.environ.get("MNT_PORTAL_DB", "/opt/mnt/app/portal/portal.db"))
    _LOCAL = threading.local()

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS events (
        event_id            TEXT PRIMARY KEY,
        event_type          TEXT,
        ticker              TEXT,
        company_id          TEXT,
        property_id         TEXT,
        source_url          TEXT,
        source_name         TEXT,
        published_at        TEXT,
        classified_at       TEXT,
        classifier_model    TEXT,
        classifier_confidence REAL,
        review_status       TEXT,
        raw_headline        TEXT,
        raw_excerpt         TEXT,
        raw_body            TEXT,
        raw_html            TEXT,
        payload_json        TEXT,
        ingested_at         TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_events_ticker       ON events(ticker);
    CREATE INDEX IF NOT EXISTS idx_events_published_at ON events(published_at DESC);
    CREATE INDEX IF NOT EXISTS idx_events_status       ON events(review_status);
    """


    def get_conn() -> sqlite3.Connection:
        conn = getattr(_LOCAL, "conn", None)
        if conn is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            _LOCAL.conn = conn
        return conn


    def init_schema() -> None:
        c = get_conn()
        c.executescript(SCHEMA)
        c.commit()


    def count_events() -> int:
        c = get_conn()
        return c.execute("SELECT COUNT(*) FROM events").fetchone()[0]


    def upsert_event(row: dict) -> None:
        c = get_conn()
        cols = [
            "event_id", "event_type", "ticker", "company_id", "property_id",
            "source_url", "source_name", "published_at", "classified_at",
            "classifier_model", "classifier_confidence", "review_status",
            "raw_headline", "raw_excerpt", "raw_body", "raw_html", "payload_json",
        ]
        vals = [row.get(k) for k in cols]
        placeholders = ",".join(["?"] * len(cols))
        assignments = ",".join(f"{k}=excluded.{k}" for k in cols if k != "event_id")
        c.execute(
            f"INSERT INTO events ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(event_id) DO UPDATE SET {assignments}",
            vals,
        )
        c.commit()


    def list_tickers() -> list[tuple[str, int]]:
        c = get_conn()
        rows = c.execute(
            "SELECT ticker, COUNT(*) AS n FROM events "
            "WHERE review_status = 'auto_approved' AND ticker IS NOT NULL "
            "GROUP BY ticker ORDER BY ticker"
        ).fetchall()
        return [(r["ticker"], r["n"]) for r in rows]


    def list_events(ticker: str | None = None, status: str | None = "auto_approved",
                    limit: int = 100, offset: int = 0) -> list[sqlite3.Row]:
        c = get_conn()
        where, args = [], []
        if status:
            where.append("review_status = ?")
            args.append(status)
        if ticker:
            where.append("ticker = ?")
            args.append(ticker)
        sql = "SELECT * FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY COALESCE(published_at, classified_at) DESC LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        return c.execute(sql, args).fetchall()


    def list_events_admin(ticker: str | None = None, status: str | None = None,
                          limit: int = 200, offset: int = 0) -> list[sqlite3.Row]:
        c = get_conn()
        where, args = [], []
        if status:
            where.append("review_status = ?")
            args.append(status)
        if ticker:
            where.append("ticker = ?")
            args.append(ticker)
        sql = "SELECT * FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY COALESCE(published_at, classified_at) DESC LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        return c.execute(sql, args).fetchall()


    def get_event(event_id: str) -> sqlite3.Row | None:
        c = get_conn()
        return c.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()


    def delete_events(ids: list[str]) -> int:
        if not ids:
            return 0
        c = get_conn()
        placeholders = ",".join(["?"] * len(ids))
        cur = c.execute(f"DELETE FROM events WHERE event_id IN ({placeholders})", ids)
        c.commit()
        return cur.rowcount


    def set_status(ids: list[str], status: str) -> int:
        if not ids:
            return 0
        c = get_conn()
        placeholders = ",".join(["?"] * len(ids))
        cur = c.execute(
            f"UPDATE events SET review_status = ? WHERE event_id IN ({placeholders})",
            [status, *ids],
        )
        c.commit()
        return cur.rowcount
''')

# --------------------------------------------------------------------------
# portal/auth.py
# --------------------------------------------------------------------------
f(PORTAL / "auth.py", r'''
    from __future__ import annotations
    import os
    import time
    from fastapi import Request
    from itsdangerous import BadSignature, TimestampSigner
    import bcrypt

    SESSION_COOKIE = "mnt_session"
    SESSION_MAX_AGE = 8 * 60 * 60  # 8 hours


    def _signer() -> TimestampSigner:
        secret = os.environ.get("MNT_SESSION_SECRET")
        if not secret:
            raise RuntimeError("MNT_SESSION_SECRET not set")
        return TimestampSigner(secret)


    def verify_password(plain: str) -> bool:
        stored = os.environ.get("MNT_ADMIN_PASSWORD_HASH", "")
        if not stored:
            return False
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8"))
        except Exception:
            return False


    def make_session_token() -> str:
        return _signer().sign(f"admin:{int(time.time())}").decode("utf-8")


    def valid_session(token: str | None) -> bool:
        if not token:
            return False
        try:
            _signer().unsign(token, max_age=SESSION_MAX_AGE)
            return True
        except BadSignature:
            return False


    def is_logged_in(request: Request) -> bool:
        return valid_session(request.cookies.get(SESSION_COOKIE))
''')

# --------------------------------------------------------------------------
# portal/ingest.py
# --------------------------------------------------------------------------
f(PORTAL / "ingest.py", r'''
    from __future__ import annotations
    import hashlib
    import hmac
    import os
    import time

    MAX_SKEW = 300  # 5 minutes


    def verify_hmac(body: bytes, ts_header: str | None, sig_header: str | None) -> bool:
        secret = os.environ.get("MNT_HMAC_SECRET")
        if not (secret and ts_header and sig_header):
            return False
        try:
            ts = int(ts_header)
        except (TypeError, ValueError):
            return False
        if abs(time.time() - ts) > MAX_SKEW:
            return False
        if not sig_header.startswith("sha256="):
            return False
        expected = hmac.new(
            secret.encode("utf-8"),
            f"{ts}.".encode("utf-8") + body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, sig_header[len("sha256=") :])
''')

# --------------------------------------------------------------------------
# portal/backfill.py
# --------------------------------------------------------------------------
f(PORTAL / "backfill.py", r'''
    from __future__ import annotations
    import json
    import logging
    from pathlib import Path

    from portal import db

    log = logging.getLogger("portal.backfill")

    EVENT_DIRS = [
        Path("/opt/mnt/app/data/events/auto"),
        Path("/opt/mnt/app/data/events/pending"),
    ]


    def _row_from_envelope(env: dict) -> dict:
        # payload may be a complex dict; serialize it
        payload = env.get("payload")
        if payload is not None and not isinstance(payload, str):
            try:
                payload = json.dumps(payload, default=str)
            except Exception:
                payload = None
        return {
            "event_id":               env.get("event_id"),
            "event_type":             env.get("event_type"),
            "ticker":                 env.get("ticker"),
            "company_id":             env.get("company_id"),
            "property_id":            env.get("property_id"),
            "source_url":             env.get("source_url"),
            "source_name":            env.get("source_name"),
            "published_at":           env.get("published_at"),
            "classified_at":          env.get("classified_at"),
            "classifier_model":       env.get("classifier_model"),
            "classifier_confidence":  env.get("classifier_confidence"),
            "review_status":          env.get("review_status"),
            "raw_headline":           env.get("raw_headline"),
            "raw_excerpt":            env.get("raw_excerpt"),
            "raw_body":               env.get("raw_body"),
            "raw_html":               env.get("raw_html"),
            "payload_json":           payload,
        }


    def run(force: bool = False) -> int:
        db.init_schema()
        existing = db.count_events()
        if existing and not force:
            log.info("backfill skipped; %d events already present", existing)
            return 0
        n = 0
        for d in EVENT_DIRS:
            if not d.exists():
                continue
            for p in sorted(d.glob("*.json")):
                try:
                    env = json.loads(p.read_text())
                except Exception:
                    log.warning("skipped unparseable file: %s", p)
                    continue
                row = _row_from_envelope(env)
                if not row["event_id"]:
                    continue
                db.upsert_event(row)
                n += 1
        log.info("backfill wrote %d events", n)
        return n


    if __name__ == "__main__":
        logging.basicConfig(level=logging.INFO)
        import sys
        force = "--force" in sys.argv
        print("backfilled:", run(force=force))
''')

# --------------------------------------------------------------------------
# portal/app.py
# --------------------------------------------------------------------------
f(PORTAL / "app.py", r'''
    from __future__ import annotations
    import json
    import logging
    import os
    from pathlib import Path

    from fastapi import FastAPI, Form, HTTPException, Header, Request
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
    app = FastAPI(title="MNT Portal")
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
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
    def feed(request: Request, ticker: str | None = None):
        tickers = db.list_tickers()
        events = db.list_events(ticker=ticker, status="auto_approved", limit=100)
        return templates.TemplateResponse("feed.html", {
            "request": request,
            "tickers": tickers,
            "events": events,
            "selected_ticker": ticker or "",
            "is_admin": auth.is_logged_in(request),
        })


    @app.get("/event/{event_id}", response_class=HTMLResponse)
    def event_detail(request: Request, event_id: str):
        row = db.get_event(event_id)
        if not row or (row["review_status"] != "auto_approved" and not auth.is_logged_in(request)):
            raise HTTPException(404)
        return templates.TemplateResponse("event.html", {
            "request": request,
            "event": row,
            "is_admin": auth.is_logged_in(request),
        })


    # ----- ingest ---------------------------------------------------------
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
        return templates.TemplateResponse("admin_login.html", {
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
        return templates.TemplateResponse("admin.html", {
            "request": request,
            "tickers": tickers,
            "events": events,
            "selected_ticker": ticker or "",
            "selected_status": status or "",
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
''')

# --------------------------------------------------------------------------
# templates/base.html
# --------------------------------------------------------------------------
f(TEMPLATES / "base.html", r'''
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{% block title %}MNT Portal{% endblock %}</title>
      <link rel="stylesheet" href="/static/style.css">
    </head>
    <body>
      <header class="topbar">
        <a class="brand" href="/">MineTerminal</a>
        <nav>
          {% if is_admin %}
            <a href="/admin">Admin</a>
            <form method="post" action="/admin/logout" class="inline">
              <button type="submit" class="linkbtn">Log out</button>
            </form>
          {% else %}
            <a href="/admin/login">Admin</a>
          {% endif %}
        </nav>
      </header>
      <main>
        {% block content %}{% endblock %}
      </main>
    </body>
    </html>
''')

# --------------------------------------------------------------------------
# templates/feed.html
# --------------------------------------------------------------------------
f(TEMPLATES / "feed.html", r'''
    {% extends "base.html" %}
    {% block title %}News feed — MNT{% endblock %}
    {% block content %}
      <section class="filters">
        <form method="get" action="/">
          <label for="ticker">Company:</label>
          <select name="ticker" id="ticker" onchange="this.form.submit()">
            <option value="">All companies ({{ events|length }} shown)</option>
            {% for t, n in tickers %}
              <option value="{{ t }}" {% if t == selected_ticker %}selected{% endif %}>
                {{ t }} &middot; {{ n }}
              </option>
            {% endfor %}
          </select>
          <noscript><button type="submit">Filter</button></noscript>
        </form>
      </section>

      {% if not events %}
        <p class="empty">No articles{% if selected_ticker %} for {{ selected_ticker }}{% endif %} yet.</p>
      {% else %}
        <ul class="events">
          {% for e in events %}
            <li class="event">
              <div class="event-meta">
                <span class="ticker">{{ e["ticker"] or "—" }}</span>
                <span class="source">{{ e["source_name"] or "" }}</span>
                <span class="date">{{ (e["published_at"] or e["classified_at"] or "")[:10] }}</span>
              </div>
              <h3><a href="/event/{{ e['event_id'] }}">{{ e["raw_headline"] or "(no headline)" }}</a></h3>
              {% if e["raw_excerpt"] %}
                <p class="excerpt">{{ e["raw_excerpt"][:300] }}{% if e["raw_excerpt"]|length > 300 %}…{% endif %}</p>
              {% endif %}
            </li>
          {% endfor %}
        </ul>
      {% endif %}
    {% endblock %}
''')

# --------------------------------------------------------------------------
# templates/event.html
# --------------------------------------------------------------------------
f(TEMPLATES / "event.html", r'''
    {% extends "base.html" %}
    {% block title %}{{ event["raw_headline"] or "Event" }} — MNT{% endblock %}
    {% block content %}
      <article class="event-detail">
        <p class="event-meta">
          <strong>{{ event["ticker"] or "—" }}</strong>
          &middot; {{ event["source_name"] or "" }}
          &middot; {{ (event["published_at"] or event["classified_at"] or "")[:19].replace("T", " ") }}
          {% if is_admin %}
            &middot; <span class="status status-{{ event['review_status'] }}">{{ event["review_status"] }}</span>
          {% endif %}
        </p>
        <h1>{{ event["raw_headline"] or "(no headline)" }}</h1>
        {% if event["source_url"] %}
          <p><a class="sourcelink" href="{{ event['source_url'] }}" target="_blank" rel="noopener noreferrer">Original source ↗</a></p>
        {% endif %}
        {% if event["raw_body"] %}
          <div class="body">{% for para in event["raw_body"].split("\n\n") %}<p>{{ para }}</p>{% endfor %}</div>
        {% elif event["raw_excerpt"] %}
          <p class="excerpt">{{ event["raw_excerpt"] }}</p>
        {% else %}
          <p class="empty">No body captured.</p>
        {% endif %}
        <p class="backlink"><a href="/">← Back to feed</a></p>
      </article>
    {% endblock %}
''')

# --------------------------------------------------------------------------
# templates/admin_login.html
# --------------------------------------------------------------------------
f(TEMPLATES / "admin_login.html", r'''
    {% extends "base.html" %}
    {% block title %}Admin login{% endblock %}
    {% block content %}
      <section class="login">
        <h1>Admin login</h1>
        {% if error %}<p class="error">Incorrect password.</p>{% endif %}
        <form method="post" action="/admin/login">
          <label for="password">Password</label>
          <input id="password" type="password" name="password" autofocus required>
          <button type="submit">Log in</button>
        </form>
      </section>
    {% endblock %}
''')

# --------------------------------------------------------------------------
# templates/admin.html
# --------------------------------------------------------------------------
f(TEMPLATES / "admin.html", r'''
    {% extends "base.html" %}
    {% block title %}Admin — MNT{% endblock %}
    {% block content %}
      <section class="admin">
        <h1>Admin</h1>
        <div class="notice">
          Default password is in use. Change the <code>MNT_ADMIN_PASSWORD_HASH</code> env var to rotate it.
        </div>
        <form class="filters" method="get" action="/admin">
          <label>Company:
            <select name="ticker" onchange="this.form.submit()">
              <option value="">All</option>
              {% for t, n in tickers %}
                <option value="{{ t }}" {% if t == selected_ticker %}selected{% endif %}>{{ t }} ({{ n }})</option>
              {% endfor %}
            </select>
          </label>
          <label>Status:
            <select name="status" onchange="this.form.submit()">
              {% for s in ["", "auto_approved", "pending", "rejected"] %}
                <option value="{{ s }}" {% if s == selected_status %}selected{% endif %}>{{ s or "all" }}</option>
              {% endfor %}
            </select>
          </label>
        </form>

        <form method="post" action="/admin/events/bulk" id="bulkform">
          <div class="bulkbar">
            <button type="submit" name="action" value="approve">Approve selected</button>
            <button type="submit" name="action" value="reject">Reject selected</button>
            <button type="submit" name="action" value="delete" class="danger"
                    onclick="return confirm('Delete the selected events? This cannot be undone.')">
              Delete selected
            </button>
            <span class="muted">{{ events|length }} shown</span>
          </div>
          <table class="events-table">
            <thead>
              <tr>
                <th><input type="checkbox" onclick="document.querySelectorAll('.rowcb').forEach(c=>c.checked=this.checked)"></th>
                <th>Date</th>
                <th>Ticker</th>
                <th>Source</th>
                <th>Headline</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {% for e in events %}
                <tr>
                  <td><input type="checkbox" class="rowcb" name="event_ids" value="{{ e['event_id'] }}"></td>
                  <td>{{ (e["published_at"] or e["classified_at"] or "")[:10] }}</td>
                  <td>{{ e["ticker"] or "" }}</td>
                  <td>{{ e["source_name"] or "" }}</td>
                  <td><a href="/event/{{ e['event_id'] }}">{{ (e["raw_headline"] or "(no headline)")[:90] }}</a></td>
                  <td><span class="status status-{{ e['review_status'] }}">{{ e["review_status"] or "" }}</span></td>
                  <td>
                    <button type="submit" formaction="/admin/events/{{ e['event_id'] }}/delete"
                            formmethod="post" class="danger small"
                            onclick="return confirm('Delete this event?')">Delete</button>
                  </td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </form>
      </section>
    {% endblock %}
''')

# --------------------------------------------------------------------------
# static/style.css
# --------------------------------------------------------------------------
f(STATIC / "style.css", r'''
    *, *::before, *::after { box-sizing: border-box; }
    body { margin: 0; font: 15px/1.5 system-ui, -apple-system, Segoe UI, sans-serif;
           color: #1a1a1a; background: #f7f7f6; }
    main { max-width: 960px; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
    a { color: #0b5aa6; text-decoration: none; }
    a:hover { text-decoration: underline; }

    .topbar { display: flex; justify-content: space-between; align-items: center;
              background: #111; color: #eee; padding: 0.75rem 1.25rem; }
    .topbar .brand { color: #fff; font-weight: 600; letter-spacing: 0.02em; }
    .topbar nav a, .topbar nav .linkbtn { color: #ddd; margin-left: 1rem; }
    .topbar nav .linkbtn { background: none; border: 0; cursor: pointer; font: inherit; }
    .topbar .inline { display: inline; }

    .filters { margin: 1rem 0 1.25rem; }
    .filters select { padding: 0.35rem 0.5rem; font: inherit; }

    .events { list-style: none; margin: 0; padding: 0; }
    .event { padding: 1rem 0; border-bottom: 1px solid #e1e1de; }
    .event-meta { font-size: 0.85rem; color: #666; display: flex; gap: 0.75rem; }
    .event-meta .ticker { font-weight: 600; color: #0b5aa6; }
    .event h3 { margin: 0.25rem 0 0.5rem; font-size: 1.1rem; }
    .event .excerpt { margin: 0; color: #333; }

    .event-detail h1 { line-height: 1.25; margin-top: 0.25rem; }
    .event-detail .body p { margin: 0.75em 0; }
    .event-detail .backlink { margin-top: 2rem; }
    .event-detail .sourcelink { font-size: 0.95rem; }

    .empty { color: #777; }

    .login { max-width: 360px; margin: 3rem auto; background: #fff;
             padding: 1.5rem; border: 1px solid #e1e1de; border-radius: 6px; }
    .login label { display: block; margin-bottom: 0.25rem; font-weight: 600; }
    .login input { width: 100%; padding: 0.5rem; font: inherit;
                   border: 1px solid #c9c9c5; border-radius: 4px; margin-bottom: 0.75rem; }
    .login button { padding: 0.55rem 1rem; background: #0b5aa6; color: #fff;
                    border: 0; border-radius: 4px; cursor: pointer; font: inherit; }
    .login .error { color: #b71c1c; }

    .admin .notice { background: #fff7d6; border: 1px solid #e6cf6f;
                     padding: 0.6rem 0.8rem; border-radius: 4px; margin-bottom: 1rem; font-size: 0.9rem; }
    .admin .filters { display: flex; gap: 1rem; align-items: center; margin-bottom: 1rem; }
    .admin .bulkbar { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.75rem; }
    .admin .muted { color: #888; margin-left: auto; font-size: 0.9rem; }
    .admin button { padding: 0.4rem 0.8rem; border: 1px solid #c9c9c5; background: #fafaf9;
                    border-radius: 4px; cursor: pointer; font: inherit; }
    .admin button.danger { background: #b71c1c; color: #fff; border-color: #8e1414; }
    .admin button.small { padding: 0.25rem 0.55rem; font-size: 0.85rem; }

    .events-table { width: 100%; border-collapse: collapse; background: #fff;
                    border: 1px solid #e1e1de; font-size: 0.92rem; }
    .events-table th, .events-table td { padding: 0.45rem 0.6rem; text-align: left;
                                         border-bottom: 1px solid #eee; vertical-align: top; }
    .events-table thead th { background: #f0f0ec; position: sticky; top: 0; }

    .status { font-size: 0.78rem; padding: 0.1rem 0.4rem; border-radius: 3px;
              background: #eee; color: #333; }
    .status-auto_approved { background: #d7f1d9; color: #1b5c22; }
    .status-pending       { background: #fff3bf; color: #7a5a00; }
    .status-rejected      { background: #f3d3d3; color: #8b1a1a; }
''')

# --------------------------------------------------------------------------
# systemd unit
# --------------------------------------------------------------------------
f(SYSTEMD, r'''
    [Unit]
    Description=MineTerminal portal (FastAPI)
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=simple
    User=mnt
    Group=mnt
    WorkingDirectory=/opt/mnt/app
    EnvironmentFile=/opt/mnt/app/.env
    ExecStart=/opt/mnt/app/.venv/bin/uvicorn portal.app:app --host 0.0.0.0 --port 80 --workers 2 --log-level info
    Restart=on-failure
    RestartSec=3
    StandardOutput=append:/opt/mnt/app/data/logs/portal.out
    StandardError=append:/opt/mnt/app/data/logs/portal.err
    AmbientCapabilities=CAP_NET_BIND_SERVICE
    CapabilityBoundingSet=CAP_NET_BIND_SERVICE

    [Install]
    WantedBy=multi-user.target
''')


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------
def write_files() -> None:
    for p, body in FILES.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
        print(f"wrote {p}  ({len(body)} bytes)")


def ensure_env_keys() -> None:
    """Append MNT_ADMIN_PASSWORD_HASH and MNT_SESSION_SECRET to .env if missing."""
    import bcrypt  # type: ignore
    text = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    keys = dict(
        line.split("=", 1) for line in text.splitlines()
        if line and not line.startswith("#") and "=" in line
    )
    added: list[str] = []
    if "MNT_ADMIN_PASSWORD_HASH" not in keys:
        pw = os.environ.get("MNT_PORTAL_SEED_PW", "m1234")
        h = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        added.append(f"MNT_ADMIN_PASSWORD_HASH={h}")
    if "MNT_SESSION_SECRET" not in keys:
        added.append(f"MNT_SESSION_SECRET={secrets.token_hex(32)}")
    if added:
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n".join(added) + "\n"
        ENV_FILE.write_text(text)
        print(f"appended {len(added)} keys to {ENV_FILE}: {[a.split('=',1)[0] for a in added]}")
    else:
        print(f"{ENV_FILE} already has auth keys; no changes")


def main() -> int:
    write_files()
    ensure_env_keys()
    # Make sure /opt/mnt/app/data/logs exists and is writable by mnt
    logs = APP_ROOT / "data" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
