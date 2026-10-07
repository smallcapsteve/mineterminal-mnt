"""Publish the Sampling & Geoscience Results reader into the table /sampling-geoscience reads (SMP_PUBLISH_V1, 2026-09-29).

The facts store holds what SMP_V1 (portal/extractors/sampling.py) found in every approved release. The page reads
sampling_results, which this module rebuilds from the ACTIVE sampling version.

What goes on the page (Justin, 2026-09-28/29; released as an early version after four tuning rounds):
  1. SCOPE. Releases carrying the Sampling & Geoscience Results tag. With LOOKALIKES on, also untagged releases whose
     headline names a surface result and no drilling (the look-alike filter the fresh samples were drawn with); their
     rows are flagged tag_confirmed = 0. Rows the reader finds in any other untagged release stay in the facts store.
  2. ONE ROW PER SAMPLE TYPE per project the release reports results for: sample type (with the survey method for
     geophysics), project, historical flag, best grade (value, unit, metal), width, anomaly, sample count, line-km,
     bulk tonnes and an evidence quote. The page shows sample type and project (gated), and best grade and width with
     the early-version note; anomaly and sample count are stored, not shown (measured 46% / 61% on fresh data).
  3. A MARKER row (sample_type NULL, n_rows 0) for every tagged release where the reader found no result, so "all
     tagged releases" follows the tag.
  4. Flat table, newest first.

compute() is a pure function of the items. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.sampling_publish
Self-tests: python3 -m portal.sampling_publish --selftest     (in-memory; touches nothing live)
Dry run:    python3 -m portal.sampling_publish --dry-run [--version X.Y.Z]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time

EXTRACTOR = "sampling"
TAG = "Sampling & Geoscience Results"
DB = "/opt/mnt/app/portal/portal.db"
TABLE = "sampling_results"
# Look-alikes (untagged releases whose headline names a surface result): measured 10 of 15 rows right on the fresh
# samples, against ~90% inside the tag. Off until Justin says otherwise.
LOOKALIKES = False
STRICT = re.compile(r"\b(?:grab|chip|channel|rock|soil|till|trench\w*|outcrop|boulder|surface|prospecting)\s+(?:\w+\s+){0,2}"
                    r"(?:samples?|sampling|results?|assays?)\b|\b(?:IP|geophysical|magnetic|EM|gravity|soil|geochemical)\s+"
                    r"(?:survey\s+)?(?:results?|anomal\w+)|\bvisible gold\b|\bnew\s+\w*\s*showing", re.I)
NODRILL = re.compile(r"\bdrill\w*|\bholes?\b|\bintersect\w*|\bintercept\w*", re.I)

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sampling_results (
    sr_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    slug              TEXT,
    sample_type       TEXT,
    sample_group      TEXT,
    survey_type       TEXT,
    project           TEXT,
    historical        INTEGER NOT NULL DEFAULT 0,
    grade             REAL,
    grade_unit        TEXT,
    grade_metal       TEXT,
    width_m           REAL,
    anomaly_json      TEXT,
    sample_count      INTEGER,
    line_km           REAL,
    bulk_tonnes       REAL,
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
CREATE INDEX IF NOT EXISTS idx_sampling_pub    ON sampling_results(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_sampling_ticker ON sampling_results(ticker);
CREATE INDEX IF NOT EXISTS idx_sampling_event  ON sampling_results(event_id);
CREATE INDEX IF NOT EXISTS idx_sampling_type   ON sampling_results(sample_type);
"""

_ROW_FIELDS = ("sample_type", "sample_group", "survey_type", "project", "historical", "grade", "grade_unit", "grade_metal",
               "width_m", "anomaly_json", "sample_count", "line_km", "bulk_tonnes", "evidence", "date")
_COLS = ("event_id", "ordinal", "ticker", "slug") + _ROW_FIELDS + ("n_rows", "tag_confirmed", "raw_headline",
                                                                  "published_at")

GROUP = {"grab": "rock", "chip": "rock", "channel": "rock", "trench": "rock", "soil": "geochem", "till": "geochem",
         "sediment": "geochem", "other_geochem": "geochem", "geophysics": "geophysics", "bulk": "bulk_brine",
         "brine": "bulk_brine", "mapping": "mapping"}
TYPE_LABELS = {"grab": "Grab / rock", "chip": "Chip", "channel": "Channel", "trench": "Trench", "soil": "Soil",
               "till": "Till", "sediment": "Stream / lake sediment", "other_geochem": "Other geochemistry",
               "geophysics": "Geophysics", "bulk": "Bulk sample", "brine": "Brine", "mapping": "Mapping / prospecting"}
GROUP_LABELS = {"rock": "Rock samples", "geochem": "Soil, till & sediment", "geophysics": "Geophysics",
                "bulk_brine": "Bulk & brine", "mapping": "Mapping"}
SURVEY_LABELS = {"IP": "IP", "magnetics": "Magnetics", "EM": "EM", "MT": "MT", "gravity": "Gravity",
                 "radiometric": "Radiometric", "lidar": "LiDAR", "hyperspectral": "Hyperspectral", "seismic": "Seismic",
                 "remote_sensing": "Remote sensing", "other": "Other"}


def lookalike(headline):
    return bool(STRICT.search(headline or "")) and not NODRILL.search(headline or "")


def _marker(ev):
    row = {c: None for c in _COLS}
    row.update(event_id=ev["event_id"], ordinal=0, ticker=ev.get("ticker"), slug=ev.get("slug"), n_rows=0,
               historical=0, tag_confirmed=1, raw_headline=(ev.get("raw_headline") or "")[:500],
               published_at=ev.get("published_at"), date=(ev.get("published_at") or "")[:10] or None)
    return row


def compute(items, lookalikes=None):
    """items: [(event, parsed)] with event {event_id, ticker, published_at, raw_headline, slug, tagged} and parsed the
    reader's parse_records() dict. Returns (rows, stats)."""
    lookalikes = LOOKALIKES if lookalikes is None else lookalikes
    out = []
    st = {"items": 0, "untagged_skipped": 0, "lookalike_releases": 0, "releases_with_rows": 0, "rows": 0,
          "historical_rows": 0, "markers": 0}
    for ev, parsed in items:
        st["items"] += 1
        tagged = bool(ev.get("tagged"))
        if not tagged and not (lookalikes and lookalike(ev.get("raw_headline"))):
            st["untagged_skipped"] += 1
            continue
        rows = [r for r in (parsed or {}).get("rows") or [] if r.get("sample_type")]
        if not rows:
            if tagged:
                out.append(_marker(ev))
                st["markers"] += 1
            continue
        st["releases_with_rows"] += 1
        st["lookalike_releases"] += 0 if tagged else 1
        for i, r in enumerate(rows):
            row = {c: None for c in _COLS}
            g = r.get("best_grade") or {}
            row.update(event_id=ev["event_id"], ordinal=i, ticker=ev.get("ticker"), slug=ev.get("slug"),
                       n_rows=len(rows), tag_confirmed=1 if tagged else 0,
                       raw_headline=(ev.get("raw_headline") or "")[:500], published_at=ev.get("published_at"))
            row.update(sample_type=r["sample_type"], sample_group=GROUP.get(r["sample_type"]),
                       survey_type=r.get("survey_type") if r["sample_type"] == "geophysics" else None,
                       project=r.get("project"), historical=1 if r.get("historical") else 0,
                       grade=g.get("value"), grade_unit=g.get("unit"), grade_metal=g.get("metal"),
                       width_m=r.get("width_m"),
                       anomaly_json=json.dumps(r["anomaly"], sort_keys=True) if r.get("anomaly") else None,
                       sample_count=r.get("sample_count"), line_km=r.get("line_km"), bulk_tonnes=r.get("bulk_tonnes"),
                       evidence=(r.get("evidence") or "")[:300] or None,
                       date=(ev.get("published_at") or "")[:10] or None)
            out.append(row)
            st["rows"] += 1
            st["historical_rows"] += row["historical"]
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


def load_items(conn, version, lookalikes=None):
    """(event, parsed) for every approved release carrying the tag today that this version has read (those with no
    result become marker rows), plus, with look-alikes on, untagged releases where the reader found a result."""
    from portal.extractors import sampling as X
    lookalikes = LOOKALIKES if lookalikes is None else lookalikes
    evs = {}
    like = "%" + TAG + "%"
    for eid, tk, pub, hl, slug, cats in conn.execute(
            "SELECT e.event_id, e.ticker, COALESCE(e.published_at, e.classified_at), e.raw_headline, e.slug, "
            "e.categories FROM events e JOIN fx_runs u ON u.event_id=e.event_id AND u.extractor=? "
            "AND u.version=? WHERE e.review_status='auto_approved' AND e.categories LIKE ?", (EXTRACTOR, version, like)):
        if ("|" + (cats or "") + "|").find("|" + TAG + "|") >= 0:
            evs[eid] = {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl, "slug": slug,
                        "tagged": True}
    with_rows = {r[0] for r in conn.execute(
        "SELECT DISTINCT r.event_id FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
        "WHERE r.extractor=? AND r.version=? AND f.field='is_result' AND f.value_num=1", (EXTRACTOR, version))}
    if lookalikes:
        todo = [e for e in with_rows if e not in evs]
        for i in range(0, len(todo), 500):
            chunk = todo[i:i + 500]
            for eid, tk, pub, hl, slug in conn.execute(
                    "SELECT event_id, ticker, COALESCE(published_at, classified_at), raw_headline, slug FROM events "
                    "WHERE review_status='auto_approved' AND event_id IN (%s)" % ",".join("?" * len(chunk)), chunk):
                if lookalike(hl):
                    evs[eid] = {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl, "slug": slug,
                                "tagged": False}
    facts = {}
    wanted = [e for e in evs if e in with_rows]
    for i in range(0, len(wanted), 500):
        chunk = wanted[i:i + 500]
        for eid, ordinal, field_, seq, num, text in conn.execute(
                "SELECT r.event_id, r.ordinal, f.field, f.seq, f.value_num, f.value_text "
                "FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
                "WHERE r.extractor=? AND r.version=? AND r.event_id IN (%s)" % ",".join("?" * len(chunk)),
                [EXTRACTOR, version] + chunk):
            facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    return [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]


def _ensure_schema(conn):
    conn.executescript(TABLE_SQL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(sampling_results)")}
    for line in TABLE_SQL.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)", line)
        if m and m.group(1) not in have and m.group(1) != "sr_id":
            conn.execute("ALTER TABLE sampling_results ADD COLUMN %s %s" % (m.group(1), m.group(2)))
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
        st["rowsync"] = rowsync.sync_rows(conn, "sampling_results", "sr_id", _COLS, rows, {"extractor_version": version})
    conn.execute("BEGIN IMMEDIATE")
    try:
        # OPSFIX item 1 (2026-10-05): write only the rows that changed; same table contents (portal/rowsync.py)
        from portal import rowsync
        st["rowsync"] = rowsync.sync_rows(conn, "sampling_results", "sr_id", _COLS, rows, {"extractor_version": version})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[sampling_publish] " + json.dumps(st))
    return st


# ------------------------------------------------------------------ self-tests
def _selftest():
    sys.path.insert(0, "/opt/mnt/app")
    from portal import facts as F
    from portal.extractors import sampling as X
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
    fill = " The Company continues to advance its projects in Ontario and remains well funded." * 4
    lead = "Vancouver, British Columbia, %s -- ABC Gold Corp. (TSXV: ABC) (\"ABC\" or the \"Company\") "
    evs = [
        ("e1", "ABC.V", "2026-03-02", "ABC Gold Grab Samples Return up to 12.5 g/t Au at the Alpha Project",
         lead % "March 2, 2026" + "is pleased to report that 37 grab samples collected at the Alpha Project returned up "
                                  "to 12.5 g/t Au." + fill, TAG + "|Exploration Programs"),
        ("e2", "ABC.V", "2026-06-01", "ABC Gold Closes Private Placement",
         lead % "June 1, 2026" + "has closed a private placement of 2,000,000 units." + fill, TAG),
        ("e3", "XYZ.V", "2026-01-05", "XYZ Silver Soil Survey Results Outline 1.9 km Gold Anomaly at the Beta Project",
         lead % "January 5, 2026" + "reports that its soil sampling program at the Beta Project outlined a gold-in-soil "
                                    "anomaly measuring 1,900 m by 650 m." + fill, "Exploration Programs"),
        ("e4", "QRS.V", "2026-02-05", "QRS Gold Channel Sampling Returns 9.4 m Grading 7.4 g/t Gold at the Gamma Project",
         lead % "February 5, 2026" + "reports channel sampling results from the Gamma Project, including 9.4 m grading "
                                     "7.4 g/t gold." + fill, "Corporate Updates"),
    ]
    for eid, tk, pub, hl, body, cats in evs:
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?, 'auto_approved')",
                     (eid, tk, pub, None, hl, body, eid + "-slug", cats))
    F.run_batch(conn, spec, [dict(r) for r in conn.execute("SELECT * FROM events")])
    rows, st = compute(load_items(conn, "9.9.9", lookalikes=False), lookalikes=False)
    by = {}
    for r in rows:
        by.setdefault(r["event_id"], []).append(r)
    eq("tagged result is a row",
       [(r["sample_type"], r["sample_group"], r["grade"], r["grade_unit"], r["grade_metal"], r["sample_count"],
         r["n_rows"], r["tag_confirmed"], r["date"]) for r in by.get("e1", [])],
       [("grab", "rock", 12.5, "g/t", "Au", 37, 1, 1, "2026-03-02")])
    eq("the project is named", bool(by.get("e1") and "Alpha" in (by["e1"][0]["project"] or "")), True)
    eq("tagged release with no result is a marker", [(r["sample_type"], r["n_rows"]) for r in by.get("e2", [])],
       [(None, 0)])
    eq("untagged releases stay off with look-alikes off", (by.get("e3"), by.get("e4")), (None, None))
    rows2, st2 = compute(load_items(conn, "9.9.9", lookalikes=True), lookalikes=True)
    by2 = {}
    for r in rows2:
        by2.setdefault(r["event_id"], []).append(r)
    eq("look-alike with a result is a row, flagged untagged",
       [(r["sample_type"], r["tag_confirmed"], r["anomaly_json"] is not None) for r in by2.get("e3", [])],
       [("soil", 0, True)])
    eq("look-alike channel row keeps its width", [(r["sample_type"], r["width_m"]) for r in by2.get("e4", [])],
       [("channel", 9.4)])
    eq("lookalike filter", (lookalike("Grab Samples Return 5 g/t"), lookalike("Drills 12 m and Soil Sampling Results")),
       (True, False))
    rs, s3 = compute([({"event_id": "u", "ticker": "Q.V", "published_at": "2025-01-01", "raw_headline": "Closes Deal",
                        "slug": "", "tagged": False}, {"rows": [{"sample_type": "grab"}]}),
                      ({"event_id": "t", "ticker": "Q.V", "published_at": "2025-01-02", "raw_headline": "h",
                        "slug": "", "tagged": True}, {"rows": [{"sample_type": "geophysics", "survey_type": "IP"},
                                                               {"sample_type": "grab", "historical": True}]})],
                     lookalikes=True)
    eq("compute: scope, one row per type, groups, historical",
       [(r["event_id"], r["ordinal"], r["sample_group"], r["survey_type"], r["historical"], r["n_rows"]) for r in rs],
       [("t", 0, "geophysics", "IP", 0, 2), ("t", 1, "rock", None, 1, 2)])
    eq("stats", (s3["untagged_skipped"], s3["rows"], s3["historical_rows"], s3["markers"]), (1, 2, 1, 0))
    eq("every type has a label and a group", sorted(set(X.SAMPLE_TYPES) - set(TYPE_LABELS) | set(X.SAMPLE_TYPES) - set(GROUP)),
       [])
    publish(conn, "9.9.9", log=lambda *_: None)
    n1 = conn.execute("SELECT COUNT(*) FROM sampling_results").fetchone()[0]
    publish(conn, "9.9.9", log=lambda *_: None)
    eq("idempotent", conn.execute("SELECT COUNT(*) FROM sampling_results").fetchone()[0], n1)
    eq("published as configured", n1, len(rows if not LOOKALIKES else rows2))
    print("sampling_publish: %s" % ("ok" if not bad else "%d FAILURES" % bad))
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
            print("[sampling_publish] dry run: no version given and none active")
            return 2
        for la in (False, True):
            rows, st = compute(load_items(conn, v, lookalikes=la), lookalikes=la)
            st.update(version=v, lookalikes=la)
            print("[sampling_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[sampling_publish] no active sampling version; nothing to publish")
        return 0
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[sampling_publish] FAILED publishing %s: %s: %s" % (version, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
