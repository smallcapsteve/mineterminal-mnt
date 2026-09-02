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
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
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


def list_tickers() -> list[tuple[str, int]]:
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


def list_categories() -> list[tuple[str, int]]:
    """Return ordered list of (category, count) pairs across auto_approved
    events. Uses the canonical category list from portal.categorize so
    order is stable.
    """
    try:
        from portal.categorize import CATEGORIES
    except Exception:
        CATEGORIES = (
            "Financings", "Drill Results", "Resource Estimates",
            "Economic Studies", "Production Results", "Financials",
            "Marketing Announcement", "Corporate Updates",
        )
    c = get_conn()
    counts = {cat: 0 for cat in CATEGORIES}
    for r in c.execute(
        "SELECT categories FROM events "
        "WHERE review_status='auto_approved' AND categories IS NOT NULL "
        "AND categories <> ''"
    ):
        for cat in (r["categories"] or "").split("|"):
            cat = cat.strip()
            if cat in counts:
                counts[cat] += 1
    return [(cat, counts[cat]) for cat in CATEGORIES]


def list_events(ticker: str | None = None, status: str | None = "auto_approved",
                categories: list[str] | None = None,
                limit: int = 100, offset: int = 0) -> list[sqlite3.Row]:
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
