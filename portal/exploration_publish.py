"""Publish the Exploration Programs reader into the table /exploration-programs reads (EXPL_PUBLISH_V1, 2026-09-21).

The facts store holds what EXPL_V1 (portal/extractors/exploration.py) found in every approved release. The page
reads exploration_programs, which this module rebuilds from the ACTIVE exploration version. It replaces nothing:
the URL showed a greyed "coming" tab, so there is no legacy table and no legacy backfill.

One row per field program a release reports (Justin, 2026-09-21): drilling, geophysics or ground work; planned,
started, underway or completed; the issuer's own, or a previous owner's (historical).

What goes on the page:
  1. every approved release in which the reader found a program, tagged Exploration Programs or not (281
     untagged releases announce programs in the headline -- most are tagged Drill Results);
  2. a MARKER row (program_type NULL) for every tagged release that reports none, so 'show all' follows the tag;
  3. ONE PROGRAM, SEVERAL RELEASES: planned -> started -> underway -> completed. Rows of the same company,
     type, project and season (or the same undated current program) within 540 days share a program_key. The
     newest release of a program is its lead row (is_latest=1); the page shows lead rows by default with the
     number of releases and the date the program was first reported. Historical rows chain on their own key
     (previous owner and year), so the same 1988 campaign cited by five releases is one program.

compute() is a pure function of the items so the accuracy gate can score what a candidate version would
publish without writing anything. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.exploration_publish
Self-tests: python3 -m portal.exploration_publish --selftest     (in-memory; touches nothing live)
Dry run:    python3 -m portal.exploration_publish --dry-run [--version X.Y.Z]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import date

EXTRACTOR = "exploration"
TAG = "Exploration Programs"
DB = "/opt/mnt/app/portal/portal.db"

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS exploration_programs (
    ep_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    slug              TEXT,
    program_type      TEXT,
    project           TEXT,
    status            TEXT,
    metres            REAL,
    holes             INTEGER,
    line_km           REAL,
    season            TEXT,
    phase             TEXT,
    historical        INTEGER NOT NULL DEFAULT 0,
    operator          TEXT,
    drill_method      TEXT,
    survey_type       TEXT,
    budget            REAL,
    currency          TEXT,
    target_metal      TEXT,
    contractor        TEXT,
    rigs              INTEGER,
    program_key       TEXT,
    program_releases  INTEGER NOT NULL DEFAULT 1,
    first_reported    TEXT,
    is_latest         INTEGER NOT NULL DEFAULT 1,
    n_rows            INTEGER NOT NULL DEFAULT 1,
    tag_confirmed     INTEGER NOT NULL DEFAULT 0,
    raw_headline      TEXT,
    published_at      TEXT,
    extractor_version TEXT
);
"""
INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_expl_pub    ON exploration_programs(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_expl_ticker ON exploration_programs(ticker);
CREATE INDEX IF NOT EXISTS idx_expl_event  ON exploration_programs(event_id);
CREATE INDEX IF NOT EXISTS idx_expl_prog   ON exploration_programs(program_key);
"""

_COLS = ("event_id", "ordinal", "ticker", "slug", "program_type", "project", "status", "metres", "holes", "line_km",
         "season", "phase", "historical", "operator", "drill_method", "survey_type", "budget", "currency",
         "target_metal", "contractor", "rigs", "program_key", "program_releases", "first_reported", "is_latest",
         "n_rows", "tag_confirmed", "raw_headline", "published_at")
_ROW_FIELDS = ("program_type", "project", "status", "metres", "holes", "line_km", "season", "phase", "historical",
               "operator", "drill_method", "survey_type", "budget", "currency", "target_metal", "contractor", "rigs")

PROGRAM_DAYS = 540
_GENERIC = {"the", "project", "property", "properties", "mine", "deposit", "claims", "claim", "gold", "silver",
            "copper", "lake", "mineral", "district", "de", "del", "la", "los", "las", "zone", "target", "prospect",
            "north", "south", "east", "west", "big", "little", "golden", "mount", "mt", "cerro"}


# ------------------------------------------------------------------ formatting (the page uses these)
TYPE_LABELS = {"drilling": "Drilling", "geophysics": "Geophysics", "ground": "Ground work"}
STATUS_LABELS = {"planned": "Planned", "started": "Started", "underway": "Underway", "completed": "Completed"}


def fmt_money(v, cur=None):
    if v is None:
        return None
    sym = {"USD": "US$", "CAD": "C$", "AUD": "A$"}.get(cur or "", "$")
    a = abs(v)
    if a >= 1e6:
        s = ("%.2f" % (a / 1e6)).rstrip("0").rstrip(".") + "M"
    else:
        s = "{:,.0f}".format(a)
    return sym + s


def fmt_int(v):
    if v is None:
        return None
    return "{:,.0f}".format(v)


# ------------------------------------------------------------------ compute (pure)
def _key_words(s):
    s = unicodedata.normalize("NFKD", s or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]+", s) if w not in _GENERIC]


def program_key(r, ticker):
    w = _key_words(r.get("project"))
    if not w:
        return None
    yrs = re.findall(r"(?:19|20)\d\d", r.get("season") or "")
    if r.get("historical"):
        op = _key_words(r.get("operator"))
        return "%s:%s:%s:H:%s:%s" % (ticker or "?", r.get("program_type"), w[0], op[0] if op else "?",
                                     yrs[0] if yrs else "?")
    ph = re.findall(r"\d+", r.get("phase") or "")
    return "%s:%s:%s:%s%s" % (ticker or "?", r.get("program_type"), w[0], yrs[0] if yrs else "cur",
                              (":p" + ph[0]) if ph else "")


def _days(a, b):
    try:
        return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)
    except (TypeError, ValueError):
        return 10 ** 6


def _marker(ev):
    row = {c: None for c in _COLS}
    row.update(event_id=ev["event_id"], ordinal=0, ticker=ev.get("ticker"), slug=ev.get("slug"), n_rows=0,
               program_releases=1, is_latest=1, tag_confirmed=1, historical=0, raw_headline=(ev.get("raw_headline") or "")[:500],
               published_at=ev.get("published_at"))
    return row


def compute(items):
    """items: iterable of (event, parsed); event = {event_id, ticker, published_at, raw_headline, slug, tagged};
    parsed = exploration.parse_records() output. Returns (rows, stats)."""
    items = sorted(items, key=lambda x: ((x[0].get("published_at") or ""), x[0]["event_id"]))
    out = []
    st = {"releases": 0, "published": 0, "rows": 0, "markers": 0, "tagged_published": 0, "untagged_published": 0,
          "drilling": 0, "geophysics": 0, "ground": 0, "historical": 0, "programs": 0, "repeat_rows": 0}
    for ev, p in items:
        st["releases"] += 1
        rows = [dict(r) for r in (p.get("rows") or []) if r.get("program_type")]
        tagged = bool(ev.get("tagged"))
        if not rows:
            if tagged:
                out.append(_marker(ev))
                st["markers"] += 1
            continue
        st["published"] += 1
        st["tagged_published" if tagged else "untagged_published"] += 1
        for i, r in enumerate(rows):
            row = {c: None for c in _COLS}
            row.update({k: r.get(k) for k in _ROW_FIELDS})
            row["historical"] = 1 if r.get("historical") else 0
            for k in ("holes", "rigs"):
                if row[k] is not None:
                    row[k] = int(row[k])
            row.update(event_id=ev["event_id"], ordinal=i, ticker=ev.get("ticker"), slug=ev.get("slug"),
                       n_rows=len(rows), tag_confirmed=1 if tagged else 0, program_key=program_key(r, ev.get("ticker")),
                       program_releases=1, is_latest=1, first_reported=(ev.get("published_at") or "")[:10] or None,
                       raw_headline=(ev.get("raw_headline") or "")[:500], published_at=ev.get("published_at"))
            out.append(row)
            st["rows"] += 1
            st[r["program_type"]] = st.get(r["program_type"], 0) + 1
            st["historical"] += row["historical"]
    # one program, several releases
    chains = {}
    for row in out:
        k = row["program_key"]
        if not k or row["program_type"] is None:
            continue
        ch = chains.setdefault(k, [])
        if ch and (row["historical"] or _days(ch[-1][-1]["published_at"], row["published_at"]) <= PROGRAM_DAYS) \
                and ch[-1][-1]["event_id"] != row["event_id"]:
            ch[-1].append(row)
        else:
            ch.append([row])
    n = 0
    for k, groups in chains.items():
        for g in groups:
            n += 1
            gid = "%s#%d" % (k, n)
            first = min((r["published_at"] or "")[:10] for r in g) or None
            for j, r in enumerate(g):
                r.update(program_key=gid, program_releases=len(g), first_reported=first,
                         is_latest=1 if j == len(g) - 1 else 0)
                st["repeat_rows"] += 0 if j == len(g) - 1 else 1
    st["programs"] = n + sum(1 for r in out if r["program_type"] and not r["program_key"])
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
    """(event, parsed) for every approved release this version found rows in, and every approved release
    carrying the tag today (those with none become marker rows)."""
    from portal.extractors import exploration as X
    found = {r[0] for r in conn.execute(
        "SELECT DISTINCT r.event_id FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
        "WHERE r.extractor=? AND r.version=? AND f.field='is_program' AND f.value_num=1",
        (EXTRACTOR, version))}
    evs = {}
    for eid, tk, pub, hl, slug, cats in conn.execute(
            "SELECT e.event_id, e.ticker, COALESCE(e.published_at, e.classified_at), e.raw_headline, e.slug, "
            "e.categories FROM events e JOIN fx_runs u ON u.event_id=e.event_id AND u.extractor=? "
            "AND u.version=? WHERE e.review_status='auto_approved'", (EXTRACTOR, version)):
        tagged = ("|" + (cats or "") + "|").find("|" + TAG + "|") >= 0
        if eid in found or tagged:
            evs[eid] = {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl, "slug": slug,
                        "tagged": tagged}
    facts = {}
    if found:
        for eid, ordinal, field_, seq, num, text in conn.execute(
                "SELECT r.event_id, r.ordinal, f.field, f.seq, f.value_num, f.value_text "
                "FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
                "WHERE r.extractor=? AND r.version=? AND r.event_id IN "
                "(SELECT r2.event_id FROM fx_records r2 JOIN fx_facts f2 ON f2.record_id=r2.record_id "
                " WHERE r2.extractor=? AND r2.version=? AND f2.field='is_program' AND f2.value_num=1)",
                (EXTRACTOR, version, EXTRACTOR, version)):
            facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    return [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]


def _ensure_schema(conn):
    conn.executescript(TABLE_SQL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(exploration_programs)")}
    for line in TABLE_SQL.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)", line)
        if m and m.group(1) not in have and m.group(1) != "ep_id":
            conn.execute("ALTER TABLE exploration_programs ADD COLUMN %s %s" % (m.group(1), m.group(2)))
    conn.executescript(INDEX_SQL)


def publish(conn, version, log=print):
    if not re.match(r"^[0-9]+[.][0-9]+[.][0-9]+$", version or ""):
        raise ValueError("bad version %r" % (version,))
    t0 = time.time()
    rows, st = compute(load_items(conn, version))
    _ensure_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM exploration_programs")
        conn.executemany(
            "INSERT INTO exploration_programs(" + ", ".join(_COLS) + ", extractor_version) VALUES ("
            + ", ".join(":" + c for c in _COLS) + ", '" + version + "')", rows)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[exploration_publish] " + json.dumps(st))
    return st


# ------------------------------------------------------------------ self-tests
def _selftest():
    sys.path.insert(0, "/opt/mnt/app")
    from portal import facts as F
    from portal.extractors import exploration as X
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
    fill = " The property is road accessible and hosts several gold showings along a regional structure." * 4
    evs = [
        ("e1", "ABC.V", "2026-03-02", "ABC Commences 5,000 Metre Drill Program at Alpha Gold Project",
         "Toronto, March 2, 2026 - ABC Gold Corp. is pleased to announce it has commenced a 5,000 metre diamond drill "
         "program at its Alpha Gold Project." + fill, "Exploration Programs"),
        ("e2", "ABC.V", "2026-06-20", "ABC Completes 5,000 Metre Drill Program at Alpha Gold Project",
         "Toronto, June 20, 2026 - ABC Gold Corp. has completed the 5,000 metre diamond drill program at its Alpha "
         "Gold Project." + fill, "Exploration Programs"),
        ("e3", "ABC.V", "2026-07-01", "ABC Announces Annual General Meeting Results",
         "Toronto, July 1, 2026 - ABC Gold Corp. announces the results of its annual meeting." + fill,
         "Shareholder Meetings|Exploration Programs"),
        ("e4", "XYZ.V", "2026-01-05", "XYZ Closes Private Placement",
         "Toronto, January 5, 2026 - XYZ Corp. has closed a private placement." + fill, "Financings"),
    ]
    for eid, tk, pub, hl, body, cats in evs:
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?, 'auto_approved')",
                     (eid, tk, pub, None, hl, body, eid + "-slug", cats))
    F.run_batch(conn, spec, [dict(r) for r in conn.execute("SELECT * FROM events")])
    rows, st = compute(load_items(conn, "9.9.9"))
    by = {}
    for r in rows:
        by.setdefault(r["event_id"], []).append(r)
    eq("started row", [(r["program_type"], r["project"], r["status"], r["metres"]) for r in by["e1"]],
       [("drilling", "Alpha", "started", 5000.0)])
    eq("completed row is the lead", [(r["status"], r["is_latest"], r["program_releases"], r["first_reported"])
                                     for r in by["e2"]], [("completed", 1, 2, "2026-03-02")])
    eq("start is not the lead", [r["is_latest"] for r in by["e1"]], [0])
    eq("same program", by["e1"][0]["program_key"] == by["e2"][0]["program_key"], True)
    eq("marker", [(r["program_type"], r["n_rows"]) for r in by["e3"]], [(None, 0)])
    eq("untagged, nothing -> absent", by.get("e4"), None)
    publish(conn, "9.9.9", log=lambda *_: None)
    publish(conn, "9.9.9", log=lambda *_: None)
    eq("idempotent", conn.execute("SELECT COUNT(*) FROM exploration_programs").fetchone()[0], len(rows))
    eq("formats", (fmt_money(1.5e6, "CAD"), fmt_int(8408.0)), ("C$1.5M", "8,408"))
    print("exploration_publish: %s" % ("ok" if not bad else "%d FAILURES" % bad))
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
            print("[exploration_publish] dry run: no version given and none active")
            return 2
        rows, st = compute(load_items(conn, v))
        st.update(version=v)
        print("[exploration_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[exploration_publish] no active exploration version; nothing to publish")
        return 0
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[exploration_publish] FAILED publishing %s: %s: %s" % (version, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
