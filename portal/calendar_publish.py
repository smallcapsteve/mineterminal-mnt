"""Publish the Calendar reader into the table Mine Terminal Pro reads (CAL_PUBLISH_V1, 2026-10-12).

The facts store holds what CAL_V1 (portal/extractors/corp_calendar.py) found in every approved release. This module
rebuilds `calendar_events` from the ACTIVE calendar version: one row per event a release reports, finished against the
release's date (year, "today", status; corp_calendar.rows_from).

The same event is usually reported more than once (the AGM date, then the voting results; a proposed consolidation,
then its effective date; a postponed meeting, then its new date). A later release about the same event supersedes
the earlier row (current = 0, superseded_by = the later row's event_id):
  - same ticker and kind, both dated, within a few days of each other (3 for meetings, results dates, calls and
    corporate actions, 2 for presentations, the same day for dividends with the same record date or none, 30 for
    NCIB windows);
  - same ticker and kind, the earlier one undated (proposed, postponed or announced without a day) and the later one
    within 400 days of it with the same detail, or any detail for a consolidation, name or symbol change,
    arrangement, spin-out or listing;
  - the later one postpones or cancels with no new date: the earlier dated row it replaces is superseded too.

Justin 2026-10-12: everything is shown, labelled. confirmed = 1 for the kinds measured right 90-98% of the time on
fresh releases (meetings, results dates, calls, dividends, presentations, NCIBs); confirmed = 0 for corporate actions
(consolidations, name / symbol changes, arrangements, spin-outs, listings, take-over bids, rights offerings: 38-45%),
which Mine Terminal Pro labels "unconfirmed". show = 0 (OTC / Frankfurt symbols, CO1) are stored and not served by
default. A row with no date and a future status is "date to be announced" (CN1).

compute() is a pure function of the items. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.calendar_publish
Self-tests: python3 -m portal.calendar_publish --selftest     (in-memory; touches nothing live)
Dry run:    python3 -m portal.calendar_publish --dry-run [--version X.Y.Z]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from datetime import date

EXTRACTOR = "calendar"
TAG = "Corporate Actions"
DB = "/opt/mnt/app/portal/portal.db"
TABLE = "calendar_events"
DATED = ("meeting", "results_release", "conference_call", "dividend", "presentation", "ncib")
CORPORATE = ("consolidation", "name_change", "symbol_change", "arrangement", "spinout", "listing", "takeover_bid",
             "rights_offering")
TOL = {"meeting": 3, "results_release": 3, "conference_call": 3, "presentation": 2, "dividend": 0, "ncib": 30}
SAME_ANY_DETAIL = ("consolidation", "name_change", "symbol_change", "arrangement", "spinout", "listing")

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS calendar_events (
    cal_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    slug              TEXT,
    kind              TEXT,
    status            TEXT,
    event_date        TEXT,
    exact             INTEGER NOT NULL DEFAULT 0,
    end_date          TEXT,
    record_date       TEXT,
    time              TEXT,
    detail            TEXT,
    venue             TEXT,
    role              TEXT,
    show              INTEGER NOT NULL DEFAULT 1,
    confirmed         INTEGER NOT NULL DEFAULT 0,
    current           INTEGER NOT NULL DEFAULT 1,
    superseded_by     TEXT,
    n_rows            INTEGER NOT NULL DEFAULT 1,
    tag_confirmed     INTEGER NOT NULL DEFAULT 0,
    raw_headline      TEXT,
    published_at      TEXT,
    extractor_version TEXT
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_cal_date   ON calendar_events(current, show, event_date);
CREATE INDEX IF NOT EXISTS idx_cal_ticker ON calendar_events(ticker);
CREATE INDEX IF NOT EXISTS idx_cal_event  ON calendar_events(event_id);
CREATE INDEX IF NOT EXISTS idx_cal_pub    ON calendar_events(published_at DESC);
"""

_ROW_FIELDS = ("kind", "status", "event_date", "exact", "end_date", "record_date", "time", "detail", "venue", "role",
               "show")
_COLS = ("event_id", "ordinal", "ticker", "slug") + _ROW_FIELDS + ("confirmed", "current", "superseded_by", "n_rows",
                                                                    "tag_confirmed", "raw_headline", "published_at")


def D(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:  # noqa: BLE001
        return None


def _detail_key(r):
    return re.sub(r"\W+", " ", (r.get("detail") or "").lower()).strip()[:12]


def same_event(old, new):
    """Does the later row `new` report the same event as the earlier row `old` (same ticker assumed)?"""
    if old["kind"] != new["kind"]:
        return False
    k = old["kind"]
    od, nd = D(old["event_date"]), D(new["event_date"])
    if od and nd:
        if k == "dividend":
            return od == nd and (not old["record_date"] or not new["record_date"] or old["record_date"] == new["record_date"])
        return abs((od - nd).days) <= TOL.get(k, 3)
    op, np_ = D(old["published_at"]), D(new["published_at"])
    if od is None and op and np_ and 0 <= (np_ - op).days <= 400 and old["status"] in ("proposed", "postponed",
                                                                                         "scheduled"):
        return k in SAME_ANY_DETAIL or _detail_key(old) == _detail_key(new) or not _detail_key(old)
    if nd is None and od and new["status"] in ("postponed", "cancelled") and np_ and od >= np_:
        return k not in ("dividend", "ncib") and (_detail_key(old) == _detail_key(new) or k in ("meeting",
                                                                                              "results_release",
                                                                                              "conference_call"))
    return False


def _after_bulletin(old, new):
    """BULL_PUBLISH_V1: a release row about a corporate action an exchange bulletin already gave: same kind, published
    within 120 days after the bulletin, and undated or dated within 30 days of it."""
    if not str(old["event_id"]).startswith("bulletin:") or str(new["event_id"]).startswith("bulletin:"):
        return False
    if old["kind"] != new["kind"] or old["kind"] not in SAME_ANY_DETAIL:
        return False
    op, np_ = D(old["published_at"]), D(new["published_at"])
    if not (op and np_ and 0 <= (np_ - op).days <= 120):
        return False
    od, nd = D(old["event_date"]), D(new["event_date"])
    return nd is None or od is None or abs((od - nd).days) <= 30


def compute(items):
    """items: [(event, parsed)] with event {event_id, ticker, published_at, raw_headline, slug, tagged} and parsed the
    reader's parse_records() dict. -> (rows, stats)"""
    from portal.extractors import corp_calendar as X
    out = []
    st = {"releases": 0, "rows": 0, "current": 0, "superseded": 0, "by_kind": {}, "hidden": 0, "undated": 0}
    open_rows = {}      # ticker -> [row] still current
    for ev, parsed in sorted(items, key=lambda it: (str(it[0].get("published_at") or ""), it[0]["event_id"])):
        # BULL_PUBLISH_V1: an exchange bulletin brings its own finished rows
        rows = (parsed or {}).get("rows") if ev.get("bulletin") else X.rows_from(parsed or {}, ev.get("published_at"))
        if not rows:
            continue
        st["releases"] += 1
        tk = ev.get("ticker")
        for i, r in enumerate(rows):
            row = {c: None for c in _COLS}
            row.update(event_id=ev["event_id"], ordinal=i, ticker=tk, slug=ev.get("slug"), n_rows=len(rows),
                       tag_confirmed=1 if ev.get("tagged") else 0, raw_headline=(ev.get("raw_headline") or "")[:500],
                       published_at=ev.get("published_at"), kind=r["kind"], status=r["status"],
                       event_date=r.get("date"), exact=1 if r.get("exact") else 0, end_date=r.get("end_date"),
                       record_date=r.get("record_date"), time=(r.get("time") or None),
                       detail=(r.get("detail") or None), venue=r.get("venue"), role=r.get("role"),
                       show=0 if r.get("show") is False else 1,
                       confirmed=1 if (r["kind"] in DATED or ev.get("bulletin")) else 0, current=1)
            for old in open_rows.get(tk, []):
                if old["current"] and old["event_id"] != row["event_id"] and (same_event(old, row) or
                                                                               _after_bulletin(old, row)):
                    if str(old["event_id"]).startswith("bulletin:") and not ev.get("bulletin") and row["current"]:
                        # BULL_PUBLISH_V1: the exchange's notice stands; the later release row is the duplicate
                        row["current"], row["superseded_by"] = 0, old["event_id"]
                        st["superseded"] += 1
                        continue
                    old["current"], old["superseded_by"] = 0, row["event_id"]
                    st["superseded"] += 1
            open_rows.setdefault(tk, []).append(row)
            st["rows"] += 1
            st["by_kind"][row["kind"]] = st["by_kind"].get(row["kind"], 0) + 1
            st["hidden"] += 1 - row["show"]
            st["undated"] += 1 if not row["event_date"] else 0
            out.append(row)
    st["current"] = sum(r["current"] for r in out)
    return out, st


# ------------------------------------------------------------------ reading the store
def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def active_version(conn):
    if not _has_table(conn, "fx_extractor_versions"):
        return None
    r = conn.execute("SELECT version FROM fx_extractor_versions WHERE extractor=? AND status='active'",
                     (EXTRACTOR,)).fetchone()
    return r[0] if r else None


def load_items(conn, version):
    """(event, parsed) for every approved release this version found an event in."""
    from portal.extractors import corp_calendar as X
    with_rows = [r[0] for r in conn.execute(
        "SELECT DISTINCT r.event_id FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
        "WHERE r.extractor=? AND r.version=? AND f.field='is_event' AND f.value_num=1", (EXTRACTOR, version))]
    evs, facts = {}, {}
    for i in range(0, len(with_rows), 500):
        chunk = with_rows[i:i + 500]
        q = ",".join("?" * len(chunk))
        for eid, tk, pub, hl, slug, cats in conn.execute(
                "SELECT event_id, ticker, COALESCE(published_at, classified_at), raw_headline, slug, categories "
                "FROM events WHERE review_status='auto_approved' AND event_id IN (%s)" % q, chunk):
            evs[eid] = {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl, "slug": slug,
                        "tagged": ("|" + (cats or "") + "|").find("|" + TAG + "|") >= 0}
        for eid, ordinal, field_, seq, num, text in conn.execute(
                "SELECT r.event_id, r.ordinal, f.field, f.seq, f.value_num, f.value_text "
                "FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
                "WHERE r.extractor=? AND r.version=? AND r.event_id IN (%s)" % q, [EXTRACTOR, version] + chunk):
            facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    items = [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]
    items.sort(key=lambda it: (str(it[0]["published_at"] or ""), it[0]["event_id"]))
    return items


def bulletin_items(conn):
    """BULL_PUBLISH_V1: the stored exchange bulletins as compute() items (none when the table or module is absent)."""
    try:
        from portal import exchange_bulletins as XB
        return XB.calendar_items(conn)
    except Exception as exc:  # noqa: BLE001 - the bulletins are optional; the calendar publishes without them
        print("[calendar_publish] bulletins skipped: %s: %s" % (type(exc).__name__, str(exc)[:160]))
        return []


def _ensure_schema(conn):
    conn.executescript(TABLE_SQL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(calendar_events)")}
    for line in TABLE_SQL.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)", line)
        if m and m.group(1) not in have and m.group(1) != "cal_id":
            conn.execute("ALTER TABLE calendar_events ADD COLUMN %s %s" % (m.group(1), m.group(2)))
    conn.executescript(INDEX_SQL)


def publish(conn, version, log=print):
    if not re.match(r"^[0-9]+[.][0-9]+[.][0-9]+$", version or ""):
        raise ValueError("bad version %r" % (version,))
    t0 = time.time()
    rows, st = compute(load_items(conn, version) + bulletin_items(conn))
    _ensure_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM calendar_events")
        conn.executemany(
            "INSERT INTO calendar_events(" + ", ".join(_COLS) + ", extractor_version) VALUES ("
            + ", ".join(":" + c for c in _COLS) + ", '" + version + "')", rows)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[calendar_publish] " + json.dumps(st, sort_keys=True))
    return st


# ------------------------------------------------------------------ self-tests
def _selftest():
    sys.path.insert(0, "/opt/mnt/app")
    from portal import facts as F
    from portal.extractors import corp_calendar as X
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))

    # --- supersession, pure
    def R(eid, pub, kind, d, status="scheduled", detail=None, record=None):
        return {"event_id": eid, "published_at": pub, "kind": kind, "event_date": d, "status": status,
                "detail": detail, "record_date": record}
    eq("AGM date then its results", same_event(R("a", "2026-05-01", "meeting", "2026-06-18"),
                                               R("b", "2026-06-19", "meeting", "2026-06-18", "completed")), True)
    eq("two meetings a year apart", same_event(R("a", "2025-05-01", "meeting", "2025-06-18"),
                                               R("b", "2026-05-01", "meeting", "2026-06-17")), False)
    eq("proposed consolidation then its date", same_event(R("a", "2026-01-10", "consolidation", None, "proposed", "10:1"),
                                                          R("b", "2026-02-20", "consolidation", "2026-03-01", detail="10:1")), True)
    eq("meeting postponed with no new date", same_event(R("a", "2026-04-01", "meeting", "2026-05-10"),
                                                        R("b", "2026-05-01", "meeting", None, "postponed")), True)
    eq("two dividends", same_event(R("a", "2026-02-01", "dividend", "2026-03-15", record="2026-03-01"),
                                   R("b", "2026-05-01", "dividend", "2026-06-15", record="2026-06-01")), False)

    # --- through the facts store
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, published_at TEXT, "
                       "classified_at TEXT, raw_headline TEXT, raw_body TEXT, slug TEXT, categories TEXT, "
                       "review_status TEXT);")
    F.ensure_schema(conn)
    spec = F.ExtractorSpec(EXTRACTOR, "9.9.9", X.KIND, TAG, X.extract, "selftest")
    fill = " The Company continues to advance its projects in British Columbia and remains well funded." * 4
    lead = "Vancouver, British Columbia, %s - Alpha Gold Corp. (TSXV: ALP) (\"Alpha\" or the \"Company\") "
    evs = [("e1", "2026-05-01", "Alpha Gold Announces Date of Annual General Meeting",
            lead % "May 1, 2026" + "announces that its annual general meeting of shareholders will be held on June 18, "
            "2026 in Vancouver." + fill, "Shareholder Meetings"),
           ("e2", "2026-06-19", "Alpha Gold Announces Voting Results of Annual General Meeting",
            lead % "June 19, 2026" + "is pleased to announce the voting results of its annual general meeting of "
            "shareholders held on June 18, 2026." + fill, "Shareholder Meetings"),
           ("e3", "2026-06-20", "Alpha Gold Announces Proposed Share Consolidation",
            lead % "June 20, 2026" + "announces that it proposes to consolidate its common shares on the basis of one "
            "(1) post-consolidation share for every ten (10) pre-consolidation shares, subject to TSX Venture Exchange "
            "acceptance." + fill, TAG),
           ("e4", "2026-06-21", "Alpha Gold Reports Drill Results", lead % "June 21, 2026" + "reports 5.2 g/t gold "
            "over 12.0 metres." + fill, "Drill Results")]
    for eid, pub, hl, body, cats in evs:
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?, 'auto_approved')",
                     (eid, "ALP.V", pub + "T13:00:00", None, hl, body, eid + "-slug", cats))
    F.run_batch(conn, spec, [dict(r) for r in conn.execute("SELECT * FROM events")])
    publish(conn, "9.9.9", log=lambda *_: None)
    got = [tuple(r) for r in conn.execute("SELECT event_id, kind, status, event_date, current, superseded_by, confirmed, "
                                          "tag_confirmed FROM calendar_events ORDER BY cal_id").fetchall()]
    eq("published through the store", got,
       [("e1", "meeting", "scheduled", "2026-06-18", 0, "e2", 1, 0),
        ("e2", "meeting", "completed", "2026-06-18", 1, None, 1, 0),
        ("e3", "consolidation", "proposed", None, 1, None, 0, 1)])
    publish(conn, "9.9.9", log=lambda *_: None)
    eq("idempotent", conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0], 3)
    print("calendar_publish: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return 1 if bad else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv:
        return _selftest()
    db = argv[argv.index("--db") + 1] if "--db" in argv else DB
    if "--dry-run" in argv:
        conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=30)
        v = argv[argv.index("--version") + 1] if "--version" in argv else active_version(conn)
        if not v:
            print("[calendar_publish] dry run: no version given and none active")
            return 2
        rows, st = compute(load_items(conn, v) + bulletin_items(conn))
        st.update(version=v)
        print("[calendar_publish] dry run " + json.dumps(st, sort_keys=True))
        return 0
    conn = sqlite3.connect(db, timeout=30, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=30000")
    version = active_version(conn)
    if version is None:
        print("[calendar_publish] no active calendar version; nothing to publish")
        return 0
    try:
        from portal import pub_incr   # PUB_INCR_V1 (2026-11-05): per-company publishing, portal/pub_incr_modes
        pub_incr.run('calendar', conn, version, publish)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[calendar_publish] FAILED publishing %s: %s: %s" % (version, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
