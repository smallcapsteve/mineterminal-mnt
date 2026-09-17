"""Publish the new Management Changes reader into the table /management-changes reads
(MGMT_PUBLISH_V1, 2026-09-17).

The facts store holds what MGMT_V1 (portal/extractors/management.py) found in every release. The page
does not read the facts store directly: it reads management_changes. This module turns the ACTIVE
management version into that table.

One row per person (Justin, 2026-09-17). The old table had exactly one row per release, so a release
that appointed three people showed one name and hid the other two inside a JSON column; 1,859 of its
3,030 rows named nobody at all.

Rules, in order, over tagged approved releases oldest first:
  1. the extractor found at least one change (is_management_change = 1)
  2. a change needs a person or a role; a release that only says the team was strengthened is tagged
     but not shown
  3. the same person, action and role announced again by the same company within 7 days is a wire copy
     of the first release, and is not shown twice

compute() is a pure function of (events, facts) so the accuracy gate can count the rows a candidate
version would publish without writing anything. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.management_publish
  - an active management version exists -> publish it
  - none yet                            -> run the legacy management_backfill.py (unchanged)
Once a version is active the legacy backfill never runs again (fix forward, never fall back). If
publishing fails after the switch, rows the legacy backfill wrote are removed rather than left on the
page wearing the new reader's name.

Self-tests: python3 -m portal.management_publish --selftest   (in-memory; touches nothing live)
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import time
import unicodedata
from datetime import date, timedelta

EXTRACTOR = "management"
TAG = "Management Changes"
DB = "/opt/mnt/app/portal/portal.db"
LEGACY = "/opt/mnt/app/management_backfill.py"
COPY_DAYS = 7

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS management_changes (
    mgmt_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    action            TEXT,
    person            TEXT,
    role              TEXT,
    role_canon        TEXT,
    scope             TEXT,
    effective_date    TEXT,
    interim           INTEGER NOT NULL DEFAULT 0,
    n_changes         INTEGER NOT NULL DEFAULT 1,
    raw_headline      TEXT,
    published_at      TEXT,
    extractor_version TEXT
);
"""

# built after the columns are in place, because the legacy table of the same name has neither
# `ordinal` nor `role_canon` and an index on a missing column fails the whole script
INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_mgmt_event_ord ON management_changes(event_id, ordinal);
CREATE INDEX IF NOT EXISTS ix_mgmt_ticker    ON management_changes(ticker);
CREATE INDEX IF NOT EXISTS ix_mgmt_published ON management_changes(published_at);
CREATE INDEX IF NOT EXISTS ix_mgmt_scope     ON management_changes(scope);
CREATE INDEX IF NOT EXISTS ix_mgmt_role      ON management_changes(role_canon);
CREATE INDEX IF NOT EXISTS ix_mgmt_person    ON management_changes(person);
"""


def surname(name):
    """The last real word of a name, accents folded: how two spellings of one person are matched."""
    t = unicodedata.normalize("NFKD", name or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    w = [x for x in re.sub(r"[^a-z ]", " ", t.lower()).split() if len(x) > 1]
    return w[-1] if w else ""


def _day(s):
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def compute(items):
    """items: iterable of (event, parsed), event = {event_id, ticker, published_at, raw_headline},
    parsed = the analyse()-shaped dict. Returns (rows, stats); rows are dicts ready to insert."""
    items = sorted(items, key=lambda x: ((x[0].get("published_at") or ""), x[0]["event_id"]))
    rows, stats = [], {"releases": 0, "no_change": 0, "published": 0, "rows": 0, "wire_copies": 0,
                       "named": 0, "role_only": 0}
    seen = {}
    for ev, p in items:
        stats["releases"] += 1
        changes = [c for c in (p.get("changes") or []) if c.get("person") or c.get("role")]
        if not p.get("is_management_change") or not changes:
            stats["no_change"] += 1
            continue
        day = _day(ev.get("published_at"))
        keep = []
        for c in changes:
            k = (ev.get("ticker") or "", surname(c.get("person")), c.get("action"), c.get("role_canon"))
            if k[1]:
                before = seen.get(k)
                if before is not None and before[0] != ev["event_id"] and day is not None \
                        and before[1] is not None and day - before[1] <= timedelta(days=COPY_DAYS):
                    stats["wire_copies"] += 1
                    continue
                seen[k] = (ev["event_id"], day)
            keep.append(c)
        if not keep:
            stats["no_change"] += 1
            continue
        for i, c in enumerate(keep):
            rows.append({"event_id": ev["event_id"], "ordinal": i, "ticker": ev.get("ticker"),
                         "action": c.get("action"), "person": c.get("person"), "role": c.get("role"),
                         "role_canon": c.get("role_canon"), "scope": c.get("scope"),
                         "effective_date": c.get("effective_date"), "interim": 1 if c.get("interim") else 0,
                         "n_changes": len(keep), "raw_headline": (ev.get("raw_headline") or "")[:500],
                         "published_at": ev.get("published_at")})
            stats["named" if c.get("person") else "role_only"] += 1
        stats["published"] += 1
        stats["rows"] += len(keep)
    return rows, stats


# ------------------------------------------------------------------ reading the facts store
def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def active_version(conn):
    r = conn.execute("SELECT version FROM fx_extractor_versions WHERE extractor=? AND status='active'",
                     (EXTRACTOR,)).fetchone() if _has_table(conn, "fx_extractor_versions") else None
    return r[0] if r else None


def load_items(conn, version):
    """(event, parsed) for every approved release carrying the Management Changes tag today that this
    version wrote records for. One release has one record per change, so facts are grouped by ordinal."""
    from portal.extractors import management as X
    evs = {}
    for eid, tk, pub, hl in conn.execute(
            "SELECT DISTINCT e.event_id, e.ticker, e.published_at, e.raw_headline FROM events e "
            "JOIN fx_records r ON r.event_id=e.event_id AND r.extractor=? AND r.version=? "
            "WHERE e.review_status='auto_approved' AND ('|' || COALESCE(e.categories,'') || '|') LIKE ?",
            (EXTRACTOR, version, "%|" + TAG + "|%")):
        evs[eid] = {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl}
    facts = {}
    for eid, ordinal, field_, seq, num, text in conn.execute(
            "SELECT r.event_id, r.ordinal, f.field, f.seq, f.value_num, f.value_text "
            "FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
            "WHERE r.extractor=? AND r.version=?", (EXTRACTOR, version)):
        if eid in evs:
            facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    return [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]


def current_event_ids(conn):
    if not _has_table(conn, "management_changes"):
        return set()
    return {r[0] for r in conn.execute("SELECT DISTINCT event_id FROM management_changes")}


def publish(conn, version, log=print):
    """Rebuild management_changes from `version` in one transaction. Returns stats."""
    if not re.match(r"^[0-9]+[.][0-9]+[.][0-9]+$", version or ""):
        raise ValueError(f"bad version {version!r}")
    t0 = time.time()
    rows, st = compute(load_items(conn, version))
    _ensure_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM management_changes")
        conn.executemany(
            "INSERT INTO management_changes(event_id, ordinal, ticker, action, person, role, role_canon, scope, "
            "effective_date, interim, n_changes, raw_headline, published_at, extractor_version) "
            "VALUES (:event_id,:ordinal,:ticker,:action,:person,:role,:role_canon,:scope,:effective_date,"
            ":interim,:n_changes,:raw_headline,:published_at,'" + version + "')", rows)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[management_publish] " + json.dumps(st))
    return st


def _ensure_schema(conn):
    """The legacy table has the same name and most of the same columns; add what it is missing."""
    conn.executescript(TABLE_SQL)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(management_changes)")}
    for col, decl in (("ordinal", "INTEGER NOT NULL DEFAULT 0"), ("role_canon", "TEXT"),
                      ("effective_date", "TEXT"), ("interim", "INTEGER NOT NULL DEFAULT 0"),
                      ("extractor_version", "TEXT"), ("n_changes", "INTEGER NOT NULL DEFAULT 1"),
                      ("role", "TEXT"), ("scope", "TEXT"), ("person", "TEXT"), ("action", "TEXT"),
                      ("ticker", "TEXT"), ("raw_headline", "TEXT"), ("published_at", "TEXT")):
        if col not in cols:
            conn.execute(f"ALTER TABLE management_changes ADD COLUMN {col} {decl}")
    conn.executescript(INDEX_SQL)


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
        rows, st = compute(load_items(conn, v))
        cur = current_event_ids(conn)
        new = {r["event_id"] for r in rows}
        st.update(version=v, current_events=len(cur), removed=len(cur - new), added=len(new - cur))
        print("[management_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[management_publish] no active management version; running the legacy management_backfill.py")
        return subprocess.call([sys.executable, LEGACY])
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[management_publish] FAILED publishing {version}: {type(exc).__name__}: {exc}")
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(management_changes)")}
            if "extractor_version" not in cols or conn.execute(
                    "SELECT 1 FROM management_changes WHERE extractor_version IS NULL LIMIT 1").fetchone():
                conn.execute("DELETE FROM management_changes" + (" WHERE extractor_version IS NULL"
                                                                 if "extractor_version" in cols else ""))
                print("[management_publish] removed rows written by the legacy reader (no fallback after the switch)")
        except Exception as exc2:  # noqa: BLE001
            print(f"[management_publish] could not clear legacy rows: {exc2}")
        return 1


# ------------------------------------------------------------------ self-tests
def _selftest():
    bad = 0

    def ok(name, cond):
        nonlocal bad
        bad += not cond
        print(("  ok    " if cond else "  FAIL  ") + name)

    def ch(action, person, role, canon, scope, eff=None, interim=False):
        return {"action": action, "person": person, "role": role, "role_canon": canon, "scope": scope,
                "effective_date": eff, "interim": interim}

    def ev(eid, tk, pub):
        return {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": "H " + eid}

    items = [
        (ev("e1", "AAA", "2026-01-01"), {"is_management_change": True, "changes": [
            ch("appointed", "Jane Doe", "Director", "Director", "board"),
            ch("appointed", "John Roe", "Chief Financial Officer", "Chief Financial Officer", "management",
               eff="2026-02-01")]}),
        (ev("e2", "AAA", "2026-01-03"), {"is_management_change": True, "changes": [
            ch("appointed", "Jane Doe", "Director", "Director", "board")]}),           # wire copy of e1
        (ev("e3", "AAA", "2026-06-01"), {"is_management_change": True, "changes": [
            ch("appointed", "Jane Doe", "Director", "Director", "board")]}),           # months later: real
        (ev("e4", "BBB", "2026-01-05"), {"is_management_change": False, "changes": []}),
        (ev("e5", "BBB", "2026-01-06"), {"is_management_change": True, "changes": [
            ch("appointed", None, None, None, None)]}),                                 # nothing to show
        (ev("e6", "BBB", "2026-01-07"), {"is_management_change": True, "changes": [
            ch("appointed", None, "Chief Executive Officer", "Chief Executive Officer", "management")]}),
    ]
    rows, st = compute(items)
    byid = {}
    for r in rows:
        byid.setdefault(r["event_id"], []).append(r)
    ok("one row per person", [len(byid.get(e, [])) for e in ("e1", "e2", "e3", "e6")] == [2, 0, 1, 1])
    ok("wire copy inside a week dropped", st["wire_copies"] == 1)
    ok("the same appointment months later is not a copy", "e3" in byid)
    ok("a release with no change is not shown", "e4" not in byid and "e5" not in byid)
    ok("a role with no person is still a row", byid["e6"][0]["role"] == "Chief Executive Officer")
    ok("n_changes counts the rows of that release", {r["n_changes"] for r in byid["e1"]} == {2})
    ok("ordinals are 0..n-1", sorted(r["ordinal"] for r in byid["e1"]) == [0, 1])
    ok("effective date carried", byid["e1"][1]["effective_date"] == "2026-02-01")
    ok("counts add up", st["rows"] == len(rows) and st["named"] + st["role_only"] == len(rows))
    ok("surname folds accents and initials", (surname("Daniel Mu" + chr(0xf1) + "iz Quintanilla"), surname("Kevin M. Keough"))
       == ("quintanilla", "keough"))

    # the database path, end to end, on an in-memory store
    from portal import facts as F
    from portal.extractors import management as X
    conn = F.connect(":memory:")
    F.ensure_schema(conn)
    conn.execute("CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, published_at TEXT, raw_headline TEXT, "
                 "raw_body TEXT, categories TEXT, review_status TEXT)")
    conn.execute("CREATE TABLE management_changes (mgmt_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT, "
                 "ticker TEXT, action TEXT, person TEXT, role TEXT, scope TEXT, n_changes INTEGER, "
                 "changes_json TEXT, raw_headline TEXT, published_at TEXT)")
    conn.execute("INSERT INTO management_changes(event_id, ticker, person) VALUES ('old1','AAA',NULL)")
    F.register_version(conn, EXTRACTOR, X.VERSION, X.KIND, TAG)
    rows_in = [
        ("x0", "T0", "2026-01-01", "Western Star Resources Appoints Garland Scott to the Board of Directors",
         "Western Star Resources Inc. announces the appointment of Garland Scott to the Board of Directors.",
         "Management Changes"),
        ("x1", "T1", "2026-01-02", "Company Announces CFO Transition",
         "The Company announces that Jane Doe has resigned as Chief Financial Officer and that John Roe has been "
         "appointed Chief Financial Officer.", "Management Changes|Financings"),
        ("x2", "T2", "2026-01-03", "Untagged Appointment",
         "The Company appoints Alice Stone as Chief Executive Officer.", "Financings"),
        ("x3", "T3", "2026-01-04", "Vortex Metals Strengthens Executive Leadership Team",
         "Vortex Metals Corp. announces that it has strengthened its executive leadership team.",
         "Management Changes"),
    ]
    conn.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,'auto_approved')", rows_in)
    F.run_batch(conn, X.SPEC, F.pending_events(conn, EXTRACTOR, X.VERSION))
    ok("no active version yet", active_version(conn) is None)
    F.activate(conn, EXTRACTOR, X.VERSION)
    st2 = publish(conn, X.VERSION, log=lambda s: None)
    got = [tuple(r) for r in conn.execute(
        "SELECT event_id, ordinal, person, role_canon, scope, action FROM management_changes ORDER BY event_id, ordinal")]
    ok("tagged releases only, legacy row gone",
       [g[0] for g in got] == ["x0", "x1", "x1"] and not any(g[0] == "old1" for g in got))
    ok("two people, two rows, one release",
       sorted((g[2], g[5]) for g in got if g[0] == "x1") == [("Jane Doe", "departed"), ("John Roe", "appointed")])
    ok("scope and canonical role stored", got[0][3:5] == ("Director", "board"))
    ok("nobody named, nothing published", not any(g[0] == "x3" for g in got))
    ok("extractor_version stamped",
       [tuple(r) for r in conn.execute("SELECT DISTINCT extractor_version FROM management_changes")] == [(X.VERSION,)])
    ok("publish is repeatable", publish(conn, X.VERSION, log=lambda s: None)["rows"] == st2["rows"])
    ok("dry run counts without writing", compute(load_items(conn, X.VERSION))[1]["rows"] == st2["rows"])
    print(f"failures: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
