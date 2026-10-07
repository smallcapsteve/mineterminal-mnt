"""Publish the Mine Development & Operations reader into the table /mine-development reads (DEV_PUBLISH_V1, 2026-09-28).

The facts store holds what DEV_V1 (portal/extractors/mine_dev.py) found in every approved release. The page reads
mine_dev_events, which this module rebuilds from the ACTIVE mine_dev version.

What goes on the page (Justin, 2026-09-28, "narrow and confirm", then "Let's just release it and I will iterate on the
reader in the future"):
  1. TAGGED RELEASES ONLY: an approved release carrying the Mine Development & Operations tag. Rows the reader finds in
     untagged releases stay in the facts store and are not shown (their precision measured 37% on honest sample 2).
  2. One row per HEADLINE event the release reports for the issuer's own mine, plant or project (the reader's
     HEADLINE_ONLY mode): event type, mine, status (achieved / underway / planned), plus the date, capex, % complete,
     figures, incident kind and counterparty the reader found. Those last fields are stored but measured weak on fresh
     data (report-only on the gate), so the page shows event type, mine and status and links the release.
  3. A MARKER row (event_type NULL, n_rows 0) for every tagged release where the reader found no headline event, so
     "all tagged releases" follows the tag.
  4. flat table, newest first; no chaining (Justin: one row per event, not chained per mine).

compute() is a pure function of the items. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.mine_dev_publish
Self-tests: python3 -m portal.mine_dev_publish --selftest     (in-memory; touches nothing live)
Dry run:    python3 -m portal.mine_dev_publish --dry-run [--version X.Y.Z]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time

EXTRACTOR = "mine_dev"
TAG = "Mine Development & Operations"
DB = "/opt/mnt/app/portal/portal.db"
TABLE = "mine_dev_events"

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS mine_dev_events (
    md_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    slug              TEXT,
    event_type        TEXT,
    event_group       TEXT,
    mine              TEXT,
    status            TEXT,
    event_date        TEXT,
    capex             REAL,
    capex_high        REAL,
    capex_currency    TEXT,
    capex_basis       TEXT,
    pct_complete      REAL,
    figures_json      TEXT,
    incident_kind     TEXT,
    counterparty      TEXT,
    evidence          TEXT,
    date              TEXT,
    n_rows            INTEGER NOT NULL DEFAULT 1,
    tag_confirmed     INTEGER NOT NULL DEFAULT 1,
    raw_headline      TEXT,
    published_at      TEXT,
    extractor_version TEXT
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_mine_dev_pub    ON mine_dev_events(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_mine_dev_ticker ON mine_dev_events(ticker);
CREATE INDEX IF NOT EXISTS idx_mine_dev_event  ON mine_dev_events(event_id);
CREATE INDEX IF NOT EXISTS idx_mine_dev_type   ON mine_dev_events(event_type);
"""

_ROW_FIELDS = ("event_type", "event_group", "mine", "status", "event_date", "capex", "capex_high", "capex_currency",
               "capex_basis", "pct_complete", "figures_json", "incident_kind", "counterparty", "evidence", "date")
_COLS = ("event_id", "ordinal", "ticker", "slug") + _ROW_FIELDS + ("n_rows", "tag_confirmed", "raw_headline",
                                                                  "published_at")

GROUP = {}
for _t in ("construction_decision", "construction_start", "construction_progress", "infrastructure", "site_cleanup",
           "commissioning", "first_production", "commercial_production", "ramp_up", "expansion"):
    GROUP[_t] = "build"
for _t in ("restart", "suspension", "care_maintenance", "closure", "status_update"):
    GROUP[_t] = "status"
GROUP["incident"] = "incident"
for _t in ("offtake", "shipment", "contract"):
    GROUP[_t] = "commercial"

TYPE_LABELS = {"construction_decision": "Construction decision", "construction_start": "Construction start",
               "construction_progress": "Construction progress", "infrastructure": "Infrastructure",
               "site_cleanup": "Site cleanup", "commissioning": "Commissioning", "first_production": "First production",
               "commercial_production": "Commercial production", "ramp_up": "Ramp-up", "expansion": "Expansion",
               "restart": "Restart", "suspension": "Suspension", "care_maintenance": "Care & maintenance",
               "closure": "Closure", "status_update": "Operations update", "incident": "Incident",
               "offtake": "Offtake", "shipment": "Shipment / sale", "contract": "Contract"}
GROUP_LABELS = {"build": "Build milestones", "status": "Operating status", "incident": "Incidents",
                "commercial": "Offtake, sales & contracts"}
STATUS_LABELS = {"achieved": "Achieved", "underway": "Underway", "planned": "Planned"}


def _marker(ev):
    row = {c: None for c in _COLS}
    row.update(event_id=ev["event_id"], ordinal=0, ticker=ev.get("ticker"), slug=ev.get("slug"), n_rows=0,
               tag_confirmed=1, raw_headline=(ev.get("raw_headline") or "")[:500], published_at=ev.get("published_at"),
               date=(ev.get("published_at") or "")[:10] or None)
    return row


def compute(items):
    """items: [(event, parsed)] with event {event_id, ticker, published_at, raw_headline, slug, tagged} and parsed the
    reader's parse_records() dict. Returns (rows, stats)."""
    out = []
    st = {"items": 0, "untagged_skipped": 0, "releases_with_rows": 0, "rows": 0, "markers": 0}
    for ev, parsed in items:
        st["items"] += 1
        if not ev.get("tagged"):
            st["untagged_skipped"] += 1
            continue
        rows = [r for r in (parsed or {}).get("rows") or [] if r.get("event_type")]
        if not rows:
            out.append(_marker(ev))
            st["markers"] += 1
            continue
        st["releases_with_rows"] += 1
        for i, r in enumerate(rows):
            row = {c: None for c in _COLS}
            row.update(event_id=ev["event_id"], ordinal=i, ticker=ev.get("ticker"), slug=ev.get("slug"),
                       n_rows=len(rows), tag_confirmed=1, raw_headline=(ev.get("raw_headline") or "")[:500],
                       published_at=ev.get("published_at"))
            for k in ("event_type", "mine", "status", "event_date", "capex", "capex_high", "capex_currency",
                      "capex_basis", "pct_complete", "figures_json", "incident_kind", "counterparty"):
                row[k] = r.get(k)
            row["evidence"] = (r.get("evidence") or "")[:300] or None
            row["event_group"] = GROUP.get(r["event_type"])
            row["date"] = (ev.get("published_at") or "")[:10] or None
            out.append(row)
            st["rows"] += 1
    return out, st


# ------------------------------------------------------------------ reading the facts store
def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def active_version(conn):
    if not _has_table(conn, "fx_extractor_versions"):
        return None
    r = conn.execute("SELECT version FROM fx_extractor_versions WHERE extractor=? AND status='active'",
                     (EXTRACTOR,)).fetchone()
    return r[0] if r else None


def load_items(conn, version):
    """(event, parsed) for every approved release carrying the tag today that this version has read (those with no
    headline event become marker rows). Untagged releases are not loaded: the page shows tagged releases only."""
    from portal.extractors import mine_dev as X
    evs = {}
    like = "%" + TAG + "%"
    for eid, tk, pub, hl, slug, cats in conn.execute(
            "SELECT e.event_id, e.ticker, COALESCE(e.published_at, e.classified_at), e.raw_headline, e.slug, "
            "e.categories FROM events e JOIN fx_runs u ON u.event_id=e.event_id AND u.extractor=? "
            "AND u.version=? WHERE e.review_status='auto_approved' AND e.categories LIKE ?", (EXTRACTOR, version, like)):
        if ("|" + (cats or "") + "|").find("|" + TAG + "|") >= 0:
            evs[eid] = {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl, "slug": slug,
                        "tagged": True}
    facts = {}
    if evs:
        for eid, ordinal, field_, seq, num, text in conn.execute(
                "SELECT r.event_id, r.ordinal, f.field, f.seq, f.value_num, f.value_text "
                "FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
                "WHERE r.extractor=? AND r.version=? AND r.event_id IN "
                "(SELECT r2.event_id FROM fx_records r2 JOIN fx_facts f2 ON f2.record_id=r2.record_id "
                " WHERE r2.extractor=? AND r2.version=? AND f2.field='is_event' AND f2.value_num=1)",
                (EXTRACTOR, version, EXTRACTOR, version)):
            if eid in evs:
                facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    return [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]


def _ensure_schema(conn):
    conn.executescript(TABLE_SQL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(mine_dev_events)")}
    for line in TABLE_SQL.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)", line)
        if m and m.group(1) not in have and m.group(1) != "md_id":
            conn.execute("ALTER TABLE mine_dev_events ADD COLUMN %s %s" % (m.group(1), m.group(2)))
    conn.executescript(INDEX_SQL)


def publish(conn, version, log=print):
    if not re.match(r"^[0-9]+[.][0-9]+[.][0-9]+$", version or ""):
        raise ValueError("bad version %r" % (version,))
    t0 = time.time()
    rows, st = compute(load_items(conn, version))
    _ensure_schema(conn)
    # OPTD step A (2026-10-06): the same rowsync calls, run once before the write lock to work out the
    # differences; the locked pass below then only applies them (portal/rowsync.py, planning). Kill switch:
    # /opt/mnt/app/portal/rowsync_plan_OFF.
    from portal import rowsync as _rowsync_plan
    with _rowsync_plan.planning(conn):
        # OPSFIX item 1 (2026-10-05): write only the rows that changed; same table contents (portal/rowsync.py)
        from portal import rowsync
        st["rowsync"] = rowsync.sync_rows(conn, "mine_dev_events", "md_id", _COLS, rows, {"extractor_version": version})
    conn.execute("BEGIN IMMEDIATE")
    try:
        # OPSFIX item 1 (2026-10-05): write only the rows that changed; same table contents (portal/rowsync.py)
        from portal import rowsync
        st["rowsync"] = rowsync.sync_rows(conn, "mine_dev_events", "md_id", _COLS, rows, {"extractor_version": version})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[mine_dev_publish] " + json.dumps(st))
    return st


# ------------------------------------------------------------------ self-tests
def _selftest():
    sys.path.insert(0, "/opt/mnt/app")
    from portal import facts as F
    from portal.extractors import mine_dev as X
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))

    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, published_at TEXT, "
                       "classified_at TEXT, raw_headline TEXT, raw_body TEXT, slug TEXT, categories TEXT, "
                       "review_status TEXT)")
    F.ensure_schema(conn)
    spec = F.ExtractorSpec(EXTRACTOR, "9.9.9", X.KIND, TAG, X.extract, "selftest")
    fill = " The Company continues to advance its operations in Ontario and to review growth opportunities." * 4
    lead = "Toronto, %s -- ABC Gold Corp. (TSXV: ABC) (\"ABC\" or the \"Company\") "
    evs = [
        ("e1", "ABC.V", "2026-03-02", "ABC Gold Declares Commercial Production at the Alpha Mine",
         lead % "March 2, 2026" + "is pleased to announce that the Alpha Mine achieved commercial production effective "
                                  "March 1, 2026, following the ramp-up of the processing plant." + fill,
         TAG + "|Production Results"),
        ("e2", "ABC.V", "2026-06-01", "ABC Gold Announces Drill Results at Alpha",
         lead % "June 1, 2026" + "reports drill results from the Alpha Project, including 12.3 g/t gold over 4.0 metres."
         + fill, TAG),
        ("e3", "XYZ.V", "2026-01-05", "XYZ Silver Declares Commercial Production at the Beta Mine",
         lead % "January 5, 2026" + "is pleased to announce that the Beta Mine achieved commercial production effective "
                                    "January 1, 2026." + fill, "Production Results"),
    ]
    for eid, tk, pub, hl, body, cats in evs:
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?, 'auto_approved')",
                     (eid, tk, pub, None, hl, body, eid + "-slug", cats))
    F.run_batch(conn, spec, [dict(r) for r in conn.execute("SELECT * FROM events")])
    rows, st = compute(load_items(conn, "9.9.9"))
    by = {}
    for r in rows:
        by.setdefault(r["event_id"], []).append(r)
    eq("tagged headline event is a row",
       [(r["event_type"], r["event_group"], r["status"], r["n_rows"], r["date"]) for r in by.get("e1", [])],
       [("commercial_production", "build", "achieved", 1, "2026-03-02")])
    eq("the mine is named", bool(by.get("e1") and "Alpha" in (by["e1"][0]["mine"] or "")), True)
    eq("tagged release with no event is a marker", [(r["event_type"], r["n_rows"]) for r in by.get("e2", [])],
       [(None, 0)])
    eq("untagged release is not on the page, even with an event", by.get("e3"), None)
    rs, s2 = compute([({"event_id": "u", "ticker": "Q.V", "published_at": "2025-01-01", "raw_headline": "h",
                        "slug": "", "tagged": False}, {"rows": [{"event_type": "restart"}]}),
                      ({"event_id": "t", "ticker": "Q.V", "published_at": "2025-01-02", "raw_headline": "h",
                        "slug": "", "tagged": True}, {"rows": [{"event_type": "restart", "status": "planned"},
                                                               {"event_type": "incident", "status": "achieved"}]})])
    eq("compute: tag scope, one row per event, groups",
       [(r["event_id"], r["ordinal"], r["event_group"], r["n_rows"]) for r in rs],
       [("t", 0, "status", 2), ("t", 1, "incident", 2)])
    eq("stats", (s2["untagged_skipped"], s2["rows"], s2["markers"]), (1, 2, 0))
    eq("every type has a label and a group", sorted(set(X.EVENT_TYPES) - set(TYPE_LABELS) | set(X.EVENT_TYPES) - set(GROUP)),
       [])
    publish(conn, "9.9.9", log=lambda *_: None)
    publish(conn, "9.9.9", log=lambda *_: None)
    eq("idempotent", conn.execute("SELECT COUNT(*) FROM mine_dev_events").fetchone()[0], len(rows))
    print("mine_dev_publish: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return 1 if bad else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv:
        return _selftest()
    db = argv[argv.index("--db") + 1] if "--db" in argv else DB
    conn = sqlite3.connect(db, timeout=30, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=30000")
    version = active_version(conn)
    if "--dry-run" in argv:
        v = argv[argv.index("--version") + 1] if "--version" in argv else version
        if not v:
            print("[mine_dev_publish] dry run: no version given and none active")
            return 2
        rows, st = compute(load_items(conn, v))
        st.update(version=v)
        print("[mine_dev_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[mine_dev_publish] no active mine_dev version; nothing to publish")
        return 0
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[mine_dev_publish] FAILED publishing %s: %s: %s" % (version, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
