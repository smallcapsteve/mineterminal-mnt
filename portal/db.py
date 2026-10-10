from __future__ import annotations
import os
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(os.environ.get("MNT_PORTAL_DB", "/opt/mnt/app/portal/portal.db"))

# PERF_A14 (2026-09-04): raw_html (14.9 KB avg), raw_body (8.2 KB) and
# raw_excerpt (0.9 KB) are never rendered by the feed, yet SELECT * pulled
# 3.3 MB off disk on every homepage request. Callers needing only list
# metadata pass columns=LIST_EVENT_COLUMNS. The default stays "*", so no
# other caller changes behaviour. Internal constant, never user input.
LIST_EVENT_COLUMNS = (
    "event_id, event_type, ticker, company_id, property_id, source_url, "
    "source_name, published_at, classified_at, classifier_model, "
    "classifier_confidence, review_status, raw_headline, ingested_at, "
    "categories, slug, additional_tickers"
)
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
    categories          TEXT,
    ingested_at         TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_ticker       ON events(ticker);
CREATE INDEX IF NOT EXISTS idx_events_published_at ON events(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_status       ON events(review_status);
CREATE INDEX IF NOT EXISTS idx_events_categories   ON events(categories);
"""


def get_conn() -> sqlite3.Connection:
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None -> autocommit. Without it a plain SELECT
        # opens a deferred read transaction that these long-lived
        # thread-local connections never close, which pins a WAL
        # snapshot forever: the WAL cannot be checkpointed, it grew to
        # 516MB, and writers started exceeding the busy timeout and
        # returning 500 from /ingest (915 dropped writes on 2026-09-15).
        # Safe because every write path here is one statement + commit.
        conn = sqlite3.connect(DB_PATH, check_same_thread=False,
                               timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        _LOCAL.conn = conn
    return conn


def init_schema() -> None:
    c = get_conn()
    c.executescript(SCHEMA)
    # Idempotent migration: add categories column to pre-existing tables
    try:
        c.execute("SELECT categories FROM events LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE events ADD COLUMN categories TEXT")
    # MNT_SPEED_V1 (2026-09-25): the listing index. Every category and company filter reads only these
    # columns, so with it no list page touches the release text (1.3 s -> tens of ms per query at 139k
    # releases). Here rather than in SCHEMA because it names columns added by later migrations; on a
    # database that already has it this is a no-op. Undo: DROP INDEX ix_events_list.
    try:
        c.execute("CREATE INDEX IF NOT EXISTS ix_events_list ON events("
                  "review_status, COALESCE(published_at, classified_at), categories, ticker, "
                  "additional_tickers, published_at, classified_at, event_id, slug)")
    except sqlite3.OperationalError:
        pass
    # MNT_SPEED_V2 (2026-09-25): the company news feed's ticker lookups (news_api by-ticker).
    try:
        c.execute("CREATE INDEX IF NOT EXISTS ix_events_uticker ON events(upper(ticker))")
        c.execute("CREATE INDEX IF NOT EXISTS ix_events_addl ON events(additional_tickers) "
                  "WHERE additional_tickers IS NOT NULL AND additional_tickers <> ''")
    except sqlite3.OperationalError:
        pass
    c.commit()


def count_events() -> int:
    c = get_conn()
    return c.execute("SELECT COUNT(*) FROM events").fetchone()[0]


def _auto_categorize(row: dict) -> str | None:
    """Compute categories from the event row using the categorizer. Returns
    a pipe-delimited string, or None if no categories matched / error.
    Never raises."""
    try:
        from portal.categorize import categorize, format_categories
        body = row.get("raw_body") or row.get("raw_excerpt") or ""
        cats = categorize(row.get("raw_headline"), body)
        s = format_categories(cats)
        return s or None
    except Exception:
        return None



import re as _re_slug

def _auto_slug(headline, max_len=80):
    s = _re_slug.sub(r'[^a-z0-9]+', '-', (headline or '').lower()).strip('-')
    return (s[:max_len].rstrip('-') or 'release')

def upsert_event(row: dict) -> None:
    if not row.get("slug"):
        row["slug"] = _auto_slug(row.get("raw_headline") or "")
    # Auto-compute categories if not provided by the caller
    if not row.get("categories"):
        row["categories"] = _auto_categorize(row)

    c = get_conn()
    cols = [
        "event_id", "event_type", "ticker", "company_id", "property_id",
        "source_url", "source_name", "published_at", "classified_at",
        "classifier_model", "classifier_confidence", "review_status",
        "raw_headline", "raw_excerpt", "raw_body", "raw_html", "payload_json",
        "categories",
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


# MNT_SPEED_V1 (2026-09-25): the homepage company dropdown scanned every release on every request
# (~0.8 s at 139k releases). It only changes when news arrives, so it is cached for 5 minutes,
# the same rule as the category chip counts below.
_TICKERS_TTL = 300.0
_tickers_cache: tuple = ()


def list_tickers() -> list[tuple[str, int]]:
    global _tickers_cache
    now = time.monotonic()
    if _tickers_cache and (now - _tickers_cache[0]) < _TICKERS_TTL:
        return _tickers_cache[1]
    result = _list_tickers_uncached()
    _tickers_cache = (now, result)
    return result


def _list_tickers_uncached() -> list[tuple[str, int]]:
    c = get_conn()
    rows = c.execute(
        "SELECT ticker, COUNT(*) AS n FROM events "
        "WHERE review_status = 'auto_approved' AND ticker IS NOT NULL "
        "GROUP BY ticker"
    ).fetchall()
    counts: dict[str, int] = {r["ticker"]: r["n"] for r in rows}
    # Also count additional_tickers (multi-tag). Each event row contributes
    # to every additional ticker it carries.
    addl_rows = c.execute(
        "SELECT additional_tickers FROM events "
        "WHERE review_status = 'auto_approved' "
        "AND additional_tickers IS NOT NULL AND additional_tickers != ''"
    ).fetchall()
    for r in addl_rows:
        for t in (r["additional_tickers"] or "").strip("|").split("|"):
            t = (t or "").strip().upper()
            if t:
                counts[t] = counts.get(t, 0) + 1
    return sorted(counts.items())


# PERF_A14 (2026-09-04): this scans every auto_approved event to produce nine
# counts, costing 0.31s on every homepage request. The counts only move when
# the scraper ingests, so they are cached for 5 minutes. Article listings are
# NOT cached; only the category chip counts can lag, by at most _CATEGORY_TTL.
_CATEGORY_TTL = 300.0
_category_cache: tuple = ()
import threading as _down3_threading
_category_lock = _down3_threading.Lock()  # DOWN3: one recount at a time, see list_categories


def list_categories() -> list[tuple[str, int]]:
    # DOWN3 (2026-10-07): when the 5-minute copy expired, every waiting request recounted all releases at
    # once (67% of MNT's CPU during the 10-07 outage). Now one request recounts and the others keep using
    # the previous counts; only the very first fill after a start waits.
    global _category_cache
    cache = _category_cache
    if cache and (time.monotonic() - cache[0]) < _CATEGORY_TTL:
        return cache[1]
    if cache:
        if not _category_lock.acquire(blocking=False):
            return cache[1]
    else:
        _category_lock.acquire()
    try:
        cache = _category_cache
        if cache and (time.monotonic() - cache[0]) < _CATEGORY_TTL:
            return cache[1]
        result = _list_categories_uncached()
        _category_cache = (time.monotonic(), result)
        return result
    finally:
        _category_lock.release()


def _list_categories_uncached() -> list[tuple[str, int]]:
    """Return ordered list of (category, count) pairs across auto_approved
    events. Uses the canonical category list from portal.categorize so
    order is stable.
    """
    try:
        from portal.categorize import CATEGORIES
    except Exception:
        # Kept in sync with portal.categorize.CATEGORIES. This copy is only
        # reached if that import fails; it was missing Management Changes and
        # Mergers & Acquisitions, so a failed import silently hid two chips.
        CATEGORIES = (
            "Financings", "Drill Results", "Resource Estimates",
            "Management Changes", "Economic Studies", "Production Results",
            "Financials", "Mergers & Acquisitions",
            "Marketing Announcement", "Corporate Updates",
        )
    c = get_conn()
    counts = {cat: 0 for cat in CATEGORIES}
    # DOWN3: SQLite groups identical category strings, so Python loops over a few thousand groups, not every release.
    for r in c.execute(
        "SELECT categories, COUNT(*) AS n FROM events "
        "WHERE review_status='auto_approved' AND categories IS NOT NULL "
        "AND categories <> '' GROUP BY categories"
    ):
        for cat in (r["categories"] or "").split("|"):
            cat = cat.strip()
            if cat in counts:
                counts[cat] += r["n"]
    return [(cat, counts[cat]) for cat in CATEGORIES]


def list_events(ticker: str | None = None, status: str | None = "auto_approved",
                categories: list[str] | None = None,
                limit: int = 100, offset: int = 0,
                columns: str = "*") -> list[sqlite3.Row]:
    c = get_conn()
    where, args = [], []
    if status:
        where.append("review_status = ?")
        args.append(status)
    if ticker:
        where.append("(ticker = ? OR ('|' || COALESCE(additional_tickers, '') || '|') LIKE ?)")
        args.append(ticker)
        args.append(f"%|{ticker}|%")
    if categories:
        # Match OR of any selected category; a release is tagged if ANY
        # selected cat appears as a pipe-delimited token in its categories.
        cat_clauses = []
        for cat in categories:
            cat_clauses.append(
                "(categories = ? OR categories LIKE ? "
                " OR categories LIKE ? OR categories LIKE ?)"
            )
            args.extend([
                cat,
                f"{cat}|%",
                f"%|{cat}",
                f"%|{cat}|%",
            ])
        where.append("(" + " OR ".join(cat_clauses) + ")")
    sql = "SELECT " + columns + " FROM events"
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
        where.append("(ticker = ? OR ('|' || COALESCE(additional_tickers, '') || '|') LIKE ?)")
        args.append(ticker)
        args.append(f"%|{ticker}|%")
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

# ====== _FUZZY_DUPE_GUARD: cross-source duplicate prevention (appended) ======
import re as _re_dupe
from datetime import datetime as _dt_dupe, timedelta as _td_dupe

_NOISE_PREFIX_RE = _re_dupe.compile(
    r"^(?:CORRECTION(?:\s+FROM\s+SOURCE)?:?\s*|RETRANSMISSION:?\s*|REPLACEMENT:?\s*|UPDATE:?\s*|REPEAT:?\s*|AMENDED\s+AND\s+RESTATED:?\s*)",
    _re_dupe.I,
)

def _normalize_dupe_hl(s):
    s = _NOISE_PREFIX_RE.sub('', (s or '').strip())
    return _re_dupe.sub(r'[^a-z0-9]+', '', s.lower())[:120]

def _find_fuzzy_dupe(conn, ticker, headline, published_at, window_hours=48):
    if not ticker or not headline:
        return None
    try:
        d = _dt_dupe.fromisoformat((published_at or '').replace('Z', '+00:00'))
    except Exception:
        return None
    lo = (d - _td_dupe(hours=window_hours)).strftime('%Y-%m-%dT%H:%M:%S')
    hi = (d + _td_dupe(hours=window_hours)).strftime('%Y-%m-%dT%H:%M:%S')
    norm = _normalize_dupe_hl(headline)
    rows = conn.execute(
        'SELECT event_id, raw_headline FROM events '
        'WHERE ticker = ? AND published_at >= ? AND published_at <= ?',
        (ticker, lo, hi)
    ).fetchall()
    for eid, rhl in rows:
        rnorm = _normalize_dupe_hl(rhl)
        if not rnorm:
            continue
        if (
            (len(norm) >= 30 and len(rnorm) >= 30 and norm[:60] == rnorm[:60])
            or rnorm.startswith(norm[:50])
            or norm.startswith(rnorm[:50])
        ):
            return eid
    return None

# Wrap original upsert_event
_orig_upsert_event = upsert_event

def upsert_event(row):  # noqa: F811
    # WIRETITLE_V1 (2026-09-28): drop a trailing wire-service name (" - PR Newswire Canada", " - newswire.ca")
    # from the headline before it is stored. Rollback: /var/backups/mnt/wiretitle-*/db.py
    try:
        from portal.wiretitle import strip_wire as _strip_wire
        if row.get("raw_headline"):
            row["raw_headline"] = _strip_wire(row["raw_headline"])
    except Exception:
        pass
    # MNT_FIX_20261003 (CFEMAIL_V1 + HLFIX_V1): wire pages served through Cloudflare hide every contact address as
    # "[email protected]"; the address is in the markup, so it is decoded here, before the release is stored. The
    # headline is cleaned the same way for every source ("p.1 ", "News Release dated ... - ", "( TREO )", a leading
    # "13:30 ET "), and a wire headline that runs on into the release's opening sentence is cut back to the title.
    # Exchange headlines are repaired against the converted PDF later, by pdfhtml_job. Rollback: /var/backups/mnt/mntfix-*/
    try:
        from portal.cfemail import decode_row as _cf_decode_row
        _h, _b, _x, _n = _cf_decode_row(row.get("raw_html"), row.get("raw_body"), row.get("raw_excerpt"))
        if _n:
            row["raw_html"], row["raw_body"], row["raw_excerpt"] = _h, _b, _x
    except Exception:
        pass
    try:
        from portal.headline_fix import repair as _hl_repair, clean_headline as _hl_clean
        if row.get("raw_headline"):
            if (row.get("source_name") or "").lower() in ("tmx", "cse"):
                row["raw_headline"] = _hl_clean(row["raw_headline"])
            else:
                row["raw_headline"] = _hl_repair(row.get("source_name"), row["raw_headline"])[0]
    except Exception:
        pass
    # If this is a brand-new insert and a fuzzy dupe exists, skip
    eid = row.get('event_id')
    conn = get_conn()
    if eid:
        existing = conn.execute('SELECT event_id FROM events WHERE event_id = ?', (eid,)).fetchone()
        if existing:
            # Same event_id — original upsert (just an update); allow
            return _orig_upsert_event(row)
    dupe = _find_fuzzy_dupe(
        conn,
        row.get('ticker'),
        row.get('raw_headline'),
        row.get('published_at'),
    )
    if dupe and dupe != eid:
        # First-source-wins: don't insert this duplicate
        return None
    return _orig_upsert_event(row)
# ====== end _FUZZY_DUPE_GUARD ======

# ====== MNT_AUD3_GUARD_V1 (2026-09-30, MTP site audit 2): copies and non-releases kept out at ingest ======
# Rollback: copy db.py back from /var/backups/mnt/aud3-mnt-code-*/db.py
_AUD3_LANDING_URL = _re_dupe.compile(r'businesswire\.com/newsroom/industry/', _re_dupe.I)
_AUD3_LANDING_HL = _re_dupe.compile(r'^mining and minerals breaking news and press releases$', _re_dupe.I)
_aud3_prev_upsert = upsert_event

def _aud3_skip(row):
    hl = (row.get('raw_headline') or '').strip()
    url = row.get('source_url') or ''
    if _AUD3_LANDING_URL.search(url) or _AUD3_LANDING_HL.match(hl):
        return 'landing page'
    if hl and not _re_dupe.search(r'[A-Za-z]{3}', hl):
        return 'no words in the headline'
    tk, eid = row.get('ticker'), row.get('event_id')
    if url and tk and hl:
        conn = get_conn()
        if eid and conn.execute('SELECT 1 FROM events WHERE event_id = ?', (eid,)).fetchone():
            return None                      # an update of a stored release
        norm = _normalize_dupe_hl(hl)
        for (rhl,) in conn.execute('SELECT raw_headline FROM events WHERE ticker = ? AND source_url = ? LIMIT 50', (tk, url)).fetchall():
            if norm and _normalize_dupe_hl(rhl) == norm:
                return 'same address and headline already stored'
    return None

def upsert_event(row):  # noqa: F811
    try:
        if _aud3_skip(row):
            return None
    except Exception:
        pass
    return _aud3_prev_upsert(row)
# ====== end MNT_AUD3_GUARD_V1 ======


# ====== DATEDUP_V1 (2026-10-10, Justin): one duplicate rule for every collector ======
# A release already stored (visible) under the same ticker within 3 days, with the same headline once ticker
# codes are removed (and the same body when the dates are more than a day apart, or the headline is generic),
# is not stored again. Exception: a wire copy replaces a stored exchange (TMX/CSE) copy -- Justin: keep the
# wire copy. Everything is logged in dup_guard_log with the removed row in full. Rule: portal/dupguard.py.
# Fails open: any error stores the release as before. Rollback: /var/backups/mnt/datedup-live-*/db.py
_datedup_prev_upsert = upsert_event
_datedup_log_ready = False


def _datedup_alias(conn, old, kept_id):
    """DATEDUP_V1.4: the removed copy's /news/<ticker>/<slug> address forwards to the kept copy."""
    try:
        if old and old.get("slug") and old.get("ticker"):
            conn.execute("INSERT OR IGNORE INTO event_slug_aliases (ticker, old_slug, event_id, source) VALUES (?,?,?,?)",
                         (old["ticker"].lower(), old["slug"].lower(), kept_id, "DATEDUP_V1"))
            conn.commit()
    except Exception:                                        # noqa: BLE001
        pass


def upsert_event(row):  # noqa: F811
    global _datedup_log_ready
    try:
        from portal import dupguard as _G
        conn = get_conn()
        eid = row.get("event_id")
        if eid and conn.execute("SELECT 1 FROM events WHERE event_id = ?", (eid,)).fetchone():
            return _datedup_prev_upsert(row)                 # an update of a stored release
        if not _datedup_log_ready:
            _G.ensure_log(conn)
            _datedup_log_ready = True
        if eid and _G.was_removed(conn, eid):
            return None                                      # already removed as a copy; do not bring it back
        twin = _G.find_visible_twin(conn, row)
        if not twin:
            return _datedup_prev_upsert(row)
        if _G.new_copy_replaces(row, twin):          # DATEDUP_V1.1: wire over exchange, unless dated >1 day later
            old = _G.load_row(conn, twin["event_id"])
            _G.log(conn, "replaced_exchange", old, row, True)
            conn.execute("DELETE FROM events WHERE event_id = ?", (twin["event_id"],))
            conn.commit()
            res = _datedup_prev_upsert(row)
            if not conn.execute("SELECT 1 FROM events WHERE event_id = ?", (eid,)).fetchone():
                _G.restore_row(conn, old)                    # the wire copy was refused further down: keep the old one
                _G.log(conn, "restored", old, row, False)
                conn.commit()
            else:
                _datedup_alias(conn, old, eid)
            return res
        _G.log(conn, "skipped_new", row, twin, True)   # DATEDUP_V1.3: full row kept so a wrong block can be undone
        conn.commit()
        return None
    except Exception:                                        # noqa: BLE001
        try:
            get_conn().rollback()
        except Exception:                                    # noqa: BLE001
            pass
        return _datedup_prev_upsert(row)
# ====== end DATEDUP_V1 ======
