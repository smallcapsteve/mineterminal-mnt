"""The MNT facts store (FACTS_V1, 2026-09-16). Steps 1b and 1c of the revised plan
(claude/MNT_INGESTION_PIPELINE_PLAN_REVISED_2026-09-16.md).

One store for every extractor that ships from step 4 onwards. The four existing
extractors keep their own tables for now (plan, change 3).

Tables (all prefixed fx_, all in portal.db):

  fx_extractor_versions  one row per (extractor, version); status is
                         candidate | active | retired | rejected. At most one
                         active version per extractor (partial unique index).
  fx_runs                one row per (event, extractor, version) processed,
                         INCLUDING runs that found nothing. This is "measured
                         silence": how often an extractor fires inside and
                         outside its tag is a query, not a guess.
  fx_records             one row per extracted thing (a study, a royalty...).
                         Identity is (extractor, version, event_id, ordinal).
  fx_record_events       extra releases a record belongs to (multi-release
                         records such as a deal's announcement and close).
  fx_facts               the values: one row per (record, field, seq), with a
                         character span into the release text it came from.

Rules that matter:

- Append-only per version. A new version writes beside the old one; pages read
  only the ACTIVE version, so installing is activate() and rolling back is
  rollback(). No table rebuilds, no empty pages mid-run.
- Writes are short. write_event() runs inside a SAVEPOINT; callers commit in
  batches (run_batch, default 200 events) so the write lock is held for a
  moment, never for a whole backfill. See MNT_DB_LOCK_FINDINGS_2026-09-15.md:
  long write transactions are what dropped 915 ingests.
- Spans are CHARACTER offsets into the event's raw_headline or raw_body as
  Python str, and fx_runs.body_sha1 records which text they index, so a later
  re-ingest that changes the body makes stale spans detectable.
- The tag is a signal on the record (tag_confirmed), not a gate on whether an
  extractor runs. Views expose it; pages show tag-confirmed records by default.

Self-tests: python3 -m portal.facts   (in-memory database; touches nothing live)
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field

SCHEMA_VERSION = 1
NAME_RE = re.compile("^[a-z][a-z0-9_]{0,62}$")
VERSION_RE = re.compile("^[0-9]+[.][0-9]+[.][0-9]+$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS fx_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS fx_extractor_versions (
    extractor    TEXT NOT NULL,
    version      TEXT NOT NULL,
    kind         TEXT NOT NULL,
    tag          TEXT,
    status       TEXT NOT NULL DEFAULT 'candidate'
                 CHECK (status IN ('candidate', 'active', 'retired', 'rejected')),
    code_sha     TEXT,
    note         TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    activated_at TEXT,
    retired_at   TEXT,
    gate_report  TEXT,
    PRIMARY KEY (extractor, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_fx_one_active
    ON fx_extractor_versions(extractor) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS fx_runs (
    event_id      TEXT NOT NULL,
    extractor     TEXT NOT NULL,
    version       TEXT NOT NULL,
    tag_confirmed INTEGER NOT NULL,
    n_records     INTEGER NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('ok', 'error')),
    error         TEXT,
    body_sha1     TEXT,
    ran_at        TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (extractor, version, event_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_fx_runs_event ON fx_runs(event_id);

CREATE TABLE IF NOT EXISTS fx_records (
    record_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    extractor            TEXT NOT NULL,
    version              TEXT NOT NULL,
    kind                 TEXT NOT NULL,
    event_id             TEXT NOT NULL,
    ordinal              INTEGER NOT NULL,
    ticker               TEXT,
    published_at         TEXT,
    tag_confirmed        INTEGER NOT NULL,
    confidence           REAL,
    lifecycle_key        TEXT,
    resolved_company_id  TEXT,
    resolved_property_id TEXT,
    promoted_at          TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (extractor, version, event_id, ordinal),
    FOREIGN KEY (extractor, version)
        REFERENCES fx_extractor_versions(extractor, version)
);
CREATE INDEX IF NOT EXISTS ix_fx_records_kind   ON fx_records(kind, version, published_at);
CREATE INDEX IF NOT EXISTS ix_fx_records_ticker ON fx_records(ticker, kind);
CREATE INDEX IF NOT EXISTS ix_fx_records_event  ON fx_records(event_id);

CREATE TABLE IF NOT EXISTS fx_record_events (
    record_id INTEGER NOT NULL REFERENCES fx_records(record_id) ON DELETE CASCADE,
    event_id  TEXT NOT NULL,
    role      TEXT NOT NULL,
    PRIMARY KEY (record_id, event_id, role)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_fx_record_events_event ON fx_record_events(event_id);

CREATE TABLE IF NOT EXISTS fx_facts (
    fact_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id    INTEGER NOT NULL REFERENCES fx_records(record_id) ON DELETE CASCADE,
    field        TEXT NOT NULL,
    seq          INTEGER NOT NULL DEFAULT 0,
    value_num    REAL,
    value_text   TEXT,
    unit         TEXT,
    metal        TEXT,
    source_field TEXT CHECK (source_field IN ('raw_headline', 'raw_body') OR source_field IS NULL),
    span_start   INTEGER,
    span_end     INTEGER,
    confidence   REAL,
    UNIQUE (record_id, field, seq)
);
CREATE INDEX IF NOT EXISTS ix_fx_facts_field ON fx_facts(field, value_num);
"""

SOURCE_FIELDS = ("raw_headline", "raw_body")


class FactsError(ValueError):
    """A write that would put malformed data in the store. Raised, never swallowed."""


# ------------------------------------------------------------------ data types
@dataclass
class Fact:
    field: str
    value_num: float | None = None
    value_text: str | None = None
    unit: str | None = None
    metal: str | None = None
    source_field: str | None = None
    span: tuple | None = None          # (start, end) character offsets
    confidence: float | None = None
    seq: int = 0


@dataclass
class Record:
    kind: str
    facts: list = field(default_factory=list)
    confidence: float | None = None
    ticker: str | None = None          # defaults to the event's ticker
    lifecycle_key: str | None = None
    also_events: list = field(default_factory=list)   # [(event_id, role)]


@dataclass
class ExtractorSpec:
    """What the runner needs to know about an extractor.

    extract(headline, body) -> list[Record]. It must be a pure function of the
    text: no database access, no network, no clock."""
    name: str
    version: str
    kind: str
    tag: str
    extract: object
    code_sha: str | None = None


# ------------------------------------------------------------------ connection
def connect(path):
    """A connection configured the way the portal's is: autocommit, WAL,
    30-second busy timeout, foreign keys on (needed for the cascades)."""
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_schema(conn):
    """Create the fx_ tables if missing. Additive only; never alters existing tables."""
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO fx_meta(key, value) VALUES ('schema_version', ?)",
                 (str(SCHEMA_VERSION),))
    got = conn.execute("SELECT value FROM fx_meta WHERE key='schema_version'").fetchone()[0]
    if int(got) != SCHEMA_VERSION:
        raise FactsError(f"fx schema_version is {got}, this code expects {SCHEMA_VERSION}")


def file_blob_sha(path):
    """git blob sha1 of a file: the same id `git hash-object` prints, so a spec's
    code_sha can be checked against the repository."""
    with open(path, "rb") as fh:
        data = fh.read()
    return hashlib.sha1((b"blob %d" % len(data)) + bytes([0]) + data).hexdigest()


def text_sha1(headline, body):
    h = hashlib.sha1()
    h.update((headline or "").encode("utf-8"))
    h.update(bytes([0]))
    h.update((body or "").encode("utf-8"))
    return h.hexdigest()


# ------------------------------------------------------------------ versions
def register_version(conn, extractor, version, kind, tag, code_sha=None, note=None):
    if not NAME_RE.match(extractor or ""):
        raise FactsError(f"bad extractor name {extractor!r}")
    if not NAME_RE.match(kind or ""):
        raise FactsError(f"bad kind {kind!r}")
    if not VERSION_RE.match(version or ""):
        raise FactsError(f"bad version {version!r}; use MAJOR.MINOR.PATCH")
    row = conn.execute("SELECT kind, code_sha FROM fx_extractor_versions WHERE extractor=? AND version=?",
                       (extractor, version)).fetchone()
    if row is None:
        conn.execute("INSERT INTO fx_extractor_versions(extractor, version, kind, tag, code_sha, note) "
                     "VALUES (?,?,?,?,?,?)", (extractor, version, kind, tag, code_sha, note))
        return "registered"
    if row["kind"] != kind:
        raise FactsError(f"{extractor} {version} is registered with kind {row['kind']!r}, not {kind!r}")
    if code_sha and row["code_sha"] and row["code_sha"] != code_sha:
        raise FactsError(f"{extractor} {version} code changed ({row['code_sha'][:12]} -> {code_sha[:12]}) "
                         "without a version bump")
    return "exists"


def version_status(conn, extractor, version):
    row = conn.execute("SELECT status FROM fx_extractor_versions WHERE extractor=? AND version=?",
                       (extractor, version)).fetchone()
    return row["status"] if row else None


def active_version(conn, extractor):
    row = conn.execute("SELECT version FROM fx_extractor_versions WHERE extractor=? AND status='active'",
                       (extractor,)).fetchone()
    return row["version"] if row else None


def activate(conn, extractor, version, gate_report=None):
    """Make version the one pages read. Returns the version it replaced (or None)."""
    st = version_status(conn, extractor, version)
    if st is None:
        raise FactsError(f"{extractor} {version} is not registered")
    if st == "rejected":
        raise FactsError(f"{extractor} {version} was rejected; register a new version")
    prev = active_version(conn, extractor)
    if prev == version:
        return prev
    conn.execute("SAVEPOINT fx_activate")
    try:
        if prev:
            conn.execute("UPDATE fx_extractor_versions SET status='retired', retired_at=datetime('now') "
                         "WHERE extractor=? AND version=?", (extractor, prev))
        conn.execute("UPDATE fx_extractor_versions SET status='active', activated_at=datetime('now'), "
                     "retired_at=NULL, gate_report=COALESCE(?, gate_report) WHERE extractor=? AND version=?",
                     (json.dumps(gate_report) if gate_report is not None else None, extractor, version))
        conn.execute("RELEASE fx_activate")
    except Exception:
        conn.execute("ROLLBACK TO fx_activate")
        conn.execute("RELEASE fx_activate")
        raise
    return prev


def rollback(conn, extractor):
    """Re-activate the most recently retired version. Returns it, or None if there is none."""
    row = conn.execute("SELECT version FROM fx_extractor_versions WHERE extractor=? AND status='retired' "
                       "ORDER BY retired_at DESC, activated_at DESC LIMIT 1", (extractor,)).fetchone()
    if row is None:
        return None
    activate(conn, extractor, row["version"])
    return row["version"]


def reject(conn, extractor, version, reason):
    st = version_status(conn, extractor, version)
    if st == "active":
        raise FactsError(f"{extractor} {version} is active; activate another version or roll back first")
    conn.execute("UPDATE fx_extractor_versions SET status='rejected', note=? WHERE extractor=? AND version=?",
                 (reason, extractor, version))


def purge_version(conn, extractor, version, batch=500):
    """Delete a non-active version's rows, in small transactions. Returns records deleted."""
    if version_status(conn, extractor, version) == "active":
        raise FactsError("refusing to purge the active version")
    total = 0
    while True:
        conn.execute("BEGIN IMMEDIATE")
        ids = [r[0] for r in conn.execute("SELECT record_id FROM fx_records WHERE extractor=? AND version=? "
                                          "LIMIT ?", (extractor, version, batch))]
        if ids:
            conn.execute("DELETE FROM fx_records WHERE record_id IN (%s)" % ",".join("?" * len(ids)), ids)
        conn.execute("COMMIT")
        total += len(ids)
        if len(ids) < batch:
            break
    conn.execute("DELETE FROM fx_runs WHERE extractor=? AND version=?", (extractor, version))
    return total


# ------------------------------------------------------------------ writing
def _check_fact(f, headline, body):
    if not isinstance(f, Fact):
        raise FactsError(f"expected Fact, got {type(f).__name__}")
    if not NAME_RE.match(f.field or ""):
        raise FactsError(f"bad field name {f.field!r}")
    if f.value_num is None and f.value_text is None:
        raise FactsError(f"fact {f.field!r} has no value")
    if f.value_num is not None and not isinstance(f.value_num, (int, float)):
        raise FactsError(f"fact {f.field!r} value_num is {type(f.value_num).__name__}")
    if f.value_num is not None and f.value_num != f.value_num:
        raise FactsError(f"fact {f.field!r} value_num is NaN")
    if f.span is not None:
        if f.source_field not in SOURCE_FIELDS:
            raise FactsError(f"fact {f.field!r} has a span but source_field={f.source_field!r}")
        s, e = f.span
        text = headline if f.source_field == "raw_headline" else body
        if not (isinstance(s, int) and isinstance(e, int) and 0 <= s < e <= len(text or "")):
            raise FactsError(f"fact {f.field!r} span {f.span} outside {f.source_field} (len {len(text or '')})")
    if f.confidence is not None and not (0.0 <= f.confidence <= 1.0):
        raise FactsError(f"fact {f.field!r} confidence {f.confidence} outside 0..1")


def write_event(conn, spec_or_name, version, event, records, tag_confirmed, status="ok", error=None):
    """Replace one event's output for one extractor version. Idempotent.

    event: mapping with event_id, ticker, published_at, raw_headline, raw_body.
    Runs inside a SAVEPOINT, so it nests inside a caller's batch transaction.
    Validates everything before writing anything."""
    extractor = spec_or_name.name if isinstance(spec_or_name, ExtractorSpec) else spec_or_name
    st = version_status(conn, extractor, version)
    if st is None:
        raise FactsError(f"{extractor} {version} is not registered")
    if st in ("retired", "rejected"):
        raise FactsError(f"{extractor} {version} is {st}; it cannot be written")
    headline, body = event["raw_headline"], event["raw_body"]
    records = list(records or [])
    if status == "ok":
        for r in records:
            if not isinstance(r, Record):
                raise FactsError(f"expected Record, got {type(r).__name__}")
            if not r.facts:
                raise FactsError(f"record of kind {r.kind!r} has no facts")
            seen = set()
            for f in r.facts:
                _check_fact(f, headline, body)
                if (f.field, f.seq) in seen:
                    raise FactsError(f"duplicate fact {f.field!r} seq {f.seq} in one record")
                seen.add((f.field, f.seq))
    else:
        records = []
    kind_row = conn.execute("SELECT kind FROM fx_extractor_versions WHERE extractor=? AND version=?",
                            (extractor, version)).fetchone()
    for r in records:
        if r.kind != kind_row["kind"]:
            raise FactsError(f"{extractor} {version} writes kind {kind_row['kind']!r}, got {r.kind!r}")

    eid = event["event_id"]
    conn.execute("SAVEPOINT fx_write")
    try:
        conn.execute("DELETE FROM fx_records WHERE extractor=? AND version=? AND event_id=?",
                     (extractor, version, eid))
        for ordinal, r in enumerate(records):
            cur = conn.execute(
                "INSERT INTO fx_records(extractor, version, kind, event_id, ordinal, ticker, published_at, "
                "tag_confirmed, confidence, lifecycle_key) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (extractor, version, r.kind, eid, ordinal, r.ticker or event["ticker"],
                 event["published_at"], 1 if tag_confirmed else 0, r.confidence, r.lifecycle_key))
            rid = cur.lastrowid
            for other_eid, role in r.also_events:
                conn.execute("INSERT OR IGNORE INTO fx_record_events(record_id, event_id, role) VALUES (?,?,?)",
                             (rid, other_eid, role))
            conn.executemany(
                "INSERT INTO fx_facts(record_id, field, seq, value_num, value_text, unit, metal, source_field, "
                "span_start, span_end, confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [(rid, f.field, f.seq, f.value_num, f.value_text, f.unit, f.metal, f.source_field,
                  f.span[0] if f.span else None, f.span[1] if f.span else None, f.confidence)
                 for f in r.facts])
        conn.execute(
            "INSERT OR REPLACE INTO fx_runs(event_id, extractor, version, tag_confirmed, n_records, status, "
            "error, body_sha1, ran_at) VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
            (eid, extractor, version, 1 if tag_confirmed else 0, len(records), status,
             (error or "")[:500] or None, text_sha1(headline, body)))
        conn.execute("RELEASE fx_write")
    except Exception:
        conn.execute("ROLLBACK TO fx_write")
        conn.execute("RELEASE fx_write")
        raise
    return len(records)


def has_tag(categories, tag):
    return tag in (categories or "").split("|")


# ------------------------------------------------------------------ running
EVENT_COLS = "event_id, ticker, published_at, raw_headline, raw_body, categories"


def pending_events(conn, extractor, version, limit=2000, only_tagged=None, since=None):
    """Approved events this version has not processed yet, newest first.

    Two steps on purpose: pick the ids first (walks the published_at index,
    no text), then load headline and body for just those. Sorting whole rows
    would drag every raw_body through the sorter."""
    sql = ("SELECT e.event_id FROM events e WHERE e.review_status='auto_approved' "
           "AND NOT EXISTS (SELECT 1 FROM fx_runs x WHERE x.extractor=? AND x.version=? AND x.event_id=e.event_id)")
    args = [extractor, version]
    if only_tagged:
        sql += " AND ('|' || COALESCE(e.categories, '') || '|') LIKE ?"
        args.append("%|" + only_tagged + "|%")
    if since:
        sql += " AND e.published_at >= ?"
        args.append(since)
    sql += " ORDER BY e.published_at DESC LIMIT ?"
    args.append(limit)
    ids = [r[0] for r in conn.execute(sql, args)]
    out = []
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        got = {r["event_id"]: r for r in conn.execute(
            "SELECT " + EVENT_COLS + " FROM events WHERE event_id IN (%s)" % ",".join("?" * len(chunk)), chunk)}
        out.extend(got[e] for e in chunk if e in got)
    return out


def run_batch(conn, spec, events, batch=200, log=None):
    """Run spec over events, committing every `batch` events.

    Extraction happens BEFORE the write transaction opens, so the write lock is
    held only for the inserts, never while an extractor is thinking (on the
    43,530-release scale test the lock hold with extraction inside was up to
    619 ms). An extractor exception, or output that fails validation
    (FactsError), is recorded as an error run and does not stop the rest; a
    database error is not caught: the batch rolls back and the run stops.
    Returns counts."""
    register_version(conn, spec.name, spec.version, spec.kind, spec.tag, spec.code_sha)
    counts = {"events": 0, "records": 0, "errors": 0, "tagged": 0, "fired_tagged": 0, "fired_untagged": 0,
              "max_txn_ms": 0.0, "extract_ms": 0.0, "skipped": None}
    status = version_status(conn, spec.name, spec.version)
    if status in ("retired", "rejected"):
        # e.g. after rollback() while the newer code is still registered: skip, don't crash the timer
        counts["skipped"] = status
        return counts
    import time as _t
    for i in range(0, len(events), batch):
        chunk = events[i:i + batch]
        t_ex = _t.monotonic()
        prepared = []
        for ev in chunk:
            tagged = has_tag(ev["categories"], spec.tag)
            try:
                recs = spec.extract(ev["raw_headline"] or "", ev["raw_body"] or "")
                prepared.append((ev, tagged, recs, None))
            except Exception as exc:  # recorded as an error run, not swallowed
                prepared.append((ev, tagged, [], f"{type(exc).__name__}: {exc}"))
        counts["extract_ms"] += (_t.monotonic() - t_ex) * 1000
        t0 = _t.monotonic()
        conn.execute("BEGIN IMMEDIATE")
        try:
            for ev, tagged, recs, err in prepared:
                n = 0
                if err is None:
                    try:
                        n = write_event(conn, spec.name, spec.version, ev, recs, tagged)
                    except FactsError as exc:
                        err = f"FactsError: {exc}"
                if err is not None:
                    counts["errors"] += 1
                    write_event(conn, spec.name, spec.version, ev, [], tagged, status="error", error=err)
                counts["events"] += 1
                counts["records"] += n
                counts["tagged"] += 1 if tagged else 0
                if n and tagged:
                    counts["fired_tagged"] += 1
                elif n:
                    counts["fired_untagged"] += 1
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        counts["max_txn_ms"] = max(counts["max_txn_ms"], round((_t.monotonic() - t0) * 1000, 1))
        if log:
            log(f"[facts] {spec.name} {spec.version}: {counts['events']}/{len(events)} events, "
                f"{counts['records']} records, {counts['errors']} errors")
    counts["extract_ms"] = round(counts["extract_ms"], 1)
    return counts


# ------------------------------------------------------------------ reading
def build_view(conn, kind, fields):
    """(Re)create v_fx_<kind>: one row per record of the ACTIVE version, one
    column per field. fields: [(name, 'num'|'text')]; a 'num' field also gets
    <name>_unit. Only seq 0 is pivoted; repeated values stay in fx_facts."""
    if not NAME_RE.match(kind):
        raise FactsError(f"bad kind {kind!r}")
    cols = []
    for name, typ in fields:
        if not NAME_RE.match(name) or typ not in ("num", "text"):
            raise FactsError(f"bad view field {(name, typ)!r}")
        if typ == "num":
            cols.append(f"MAX(CASE WHEN f.field='{name}' THEN f.value_num END) AS {name}")
            cols.append(f"MAX(CASE WHEN f.field='{name}' THEN f.unit END) AS {name}_unit")
        else:
            cols.append(f"MAX(CASE WHEN f.field='{name}' THEN f.value_text END) AS {name}")
    sql = (f"CREATE VIEW v_fx_{kind} AS SELECT r.record_id, r.event_id, r.ordinal, r.ticker, r.published_at, "
           f"r.tag_confirmed, r.confidence, r.lifecycle_key, r.version, "
           + ", ".join(cols) +
           " FROM fx_records r JOIN fx_extractor_versions v ON v.extractor=r.extractor AND v.version=r.version "
           "AND v.status='active' LEFT JOIN fx_facts f ON f.record_id=r.record_id AND f.seq=0 "
           f"WHERE r.kind='{kind}' GROUP BY r.record_id")
    conn.execute("SAVEPOINT fx_view")
    try:
        conn.execute(f"DROP VIEW IF EXISTS v_fx_{kind}")
        conn.execute(sql)
        conn.execute("RELEASE fx_view")
    except Exception:
        conn.execute("ROLLBACK TO fx_view")
        conn.execute("RELEASE fx_view")
        raise


def stats(conn, extractor, version):
    """The standing numbers for one version: coverage inside the tag and firing outside it."""
    r = conn.execute(
        "SELECT COUNT(*) AS runs, SUM(tag_confirmed) AS tagged, "
        "SUM(CASE WHEN n_records>0 AND tag_confirmed=1 THEN 1 ELSE 0 END) AS fired_tagged, "
        "SUM(CASE WHEN n_records>0 AND tag_confirmed=0 THEN 1 ELSE 0 END) AS fired_untagged, "
        "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors, SUM(n_records) AS records "
        "FROM fx_runs WHERE extractor=? AND version=?", (extractor, version)).fetchone()
    out = {k: (r[k] or 0) for k in r.keys()}
    out["facts"] = conn.execute("SELECT COUNT(*) FROM fx_facts f JOIN fx_records r ON r.record_id=f.record_id "
                                "WHERE r.extractor=? AND r.version=?", (extractor, version)).fetchone()[0]
    out["coverage_in_tag"] = round(out["fired_tagged"] / out["tagged"], 4) if out["tagged"] else None
    return out


def span_text(conn, fact_id):
    """The exact release text a fact came from, or None if its span is stale or absent."""
    row = conn.execute(
        "SELECT f.source_field, f.span_start, f.span_end, e.raw_headline, e.raw_body, x.body_sha1 "
        "FROM fx_facts f JOIN fx_records r ON r.record_id=f.record_id "
        "JOIN events e ON e.event_id=r.event_id "
        "LEFT JOIN fx_runs x ON x.extractor=r.extractor AND x.version=r.version AND x.event_id=r.event_id "
        "WHERE f.fact_id=?", (fact_id,)).fetchone()
    if row is None or row["span_start"] is None:
        return None
    if row["body_sha1"] != text_sha1(row["raw_headline"], row["raw_body"]):
        return None
    text = row["raw_headline"] if row["source_field"] == "raw_headline" else row["raw_body"]
    return text[row["span_start"]:row["span_end"]]


# ------------------------------------------------------------------ self-tests
def _selftest():
    conn = connect(":memory:")
    conn.executescript("CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, published_at TEXT, "
                       "raw_headline TEXT, raw_body TEXT, categories TEXT, review_status TEXT)")
    ensure_schema(conn)
    ensure_schema(conn)  # idempotent
    body1 = "The PEA shows an after-tax NPV of $412 million and an IRR of 31%."
    body2 = "Drilling continues. No study."
    conn.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?)", [
        ("e1", "AAA.V", "2026-09-01", "AAA PEA", body1, "Economic Studies", "auto_approved"),
        ("e2", "BBB.V", "2026-09-02", "BBB drills", body2, "Drill Results", "auto_approved"),
        ("e3", "CCC.V", "2026-09-03", "CCC PEA", body1, "Corporate Updates", "auto_approved"),
        ("e4", "DDD.V", "2026-09-04", "DDD", "x", "Economic Studies", "pending_review"),
    ])
    passed = []

    def ok(name, cond):
        if not cond:
            raise AssertionError("selftest failed: " + name)
        passed.append(name)

    def extract_v1(headline, body):
        i = body.find("NPV of $")
        if i < 0:
            return []
        j = body.find(" million", i)
        num = float(body[i + 8:j])
        return [Record(kind="economic_study", confidence=0.9, facts=[
            Fact("npv_after_tax", value_num=num * 1e6, unit="CAD", source_field="raw_body", span=(i + 7, j + 8)),
            Fact("study_type", value_text="PEA", source_field="raw_headline", span=(4, 7)),
        ])]

    spec1 = ExtractorSpec("economic_studies", "1.0.0", "economic_study", "Economic Studies", extract_v1, "sha-a")
    pend = pending_events(conn, "economic_studies", "1.0.0")
    ok("pending skips unapproved", [e["event_id"] for e in pend] == ["e3", "e2", "e1"])
    ok("pending only_tagged", [e["event_id"] for e in pending_events(conn, "economic_studies", "1.0.0",
                                                                    only_tagged="Economic Studies")] == ["e1"])
    c = run_batch(conn, spec1, pend, batch=2)
    ok("run counts", c["events"] == 3 and c["records"] == 2 and c["errors"] == 0)
    ok("measured silence", c["fired_tagged"] == 1 and c["fired_untagged"] == 1 and c["tagged"] == 1)
    ok("pending empty after run", pending_events(conn, "economic_studies", "1.0.0") == [])
    ok("silent run recorded", conn.execute("SELECT n_records FROM fx_runs WHERE event_id='e2'").fetchone()[0] == 0)
    s = stats(conn, "economic_studies", "1.0.0")
    ok("stats", s["runs"] == 3 and s["fired_untagged"] == 1 and s["coverage_in_tag"] == 1.0 and s["facts"] == 4)

    ev1 = conn.execute("SELECT " + EVENT_COLS + " FROM events WHERE event_id='e1'").fetchone()
    conn.execute("BEGIN")
    write_event(conn, "economic_studies", "1.0.0", ev1, extract_v1("", body1), True)
    write_event(conn, "economic_studies", "1.0.0", ev1, extract_v1("", body1), True)
    conn.execute("COMMIT")
    ok("rewrite idempotent", conn.execute("SELECT COUNT(*) FROM fx_records WHERE event_id='e1'").fetchone()[0] == 1
       and conn.execute("SELECT COUNT(*) FROM fx_facts").fetchone()[0] == 4)
    write_event(conn, "economic_studies", "1.0.0", ev1, [], True)
    ok("rewrite to nothing cascades facts", conn.execute("SELECT COUNT(*) FROM fx_facts").fetchone()[0] == 2)
    write_event(conn, "economic_studies", "1.0.0", ev1, extract_v1("", body1), True)

    fid = conn.execute("SELECT f.fact_id FROM fx_facts f JOIN fx_records r USING(record_id) "
                       "WHERE r.event_id='e1' AND f.field='npv_after_tax'").fetchone()[0]
    ok("span text", span_text(conn, fid) == "$412 million")
    conn.execute("UPDATE events SET raw_body = raw_body || ' Edited.' WHERE event_id='e1'")
    ok("stale span detected", span_text(conn, fid) is None)
    conn.execute("UPDATE events SET raw_body = ? WHERE event_id='e1'", (body1,))

    def bad(name, fn):
        try:
            fn()
        except FactsError:
            passed.append(name)
            return
        raise AssertionError("selftest failed (no FactsError): " + name)

    bad("span out of range", lambda: write_event(conn, "economic_studies", "1.0.0", ev1, [
        Record("economic_study", [Fact("npv_after_tax", value_num=1.0, source_field="raw_body", span=(0, 9999))])], True))
    bad("no value", lambda: write_event(conn, "economic_studies", "1.0.0", ev1, [
        Record("economic_study", [Fact("npv_after_tax")])], True))
    bad("wrong kind", lambda: write_event(conn, "economic_studies", "1.0.0", ev1, [
        Record("royalty", [Fact("nsr_pct", value_num=2.0)])], True))
    bad("bad field name", lambda: write_event(conn, "economic_studies", "1.0.0", ev1, [
        Record("economic_study", [Fact("NPV After", value_num=2.0)])], True))
    bad("duplicate field", lambda: write_event(conn, "economic_studies", "1.0.0", ev1, [
        Record("economic_study", [Fact("irr", value_num=2.0), Fact("irr", value_num=3.0)])], True))
    bad("empty record", lambda: write_event(conn, "economic_studies", "1.0.0", ev1, [Record("economic_study")], True))
    bad("unregistered", lambda: write_event(conn, "nope", "1.0.0", ev1, [], True))
    bad("code change without bump", lambda: register_version(conn, "economic_studies", "1.0.0", "economic_study",
                                                             "Economic Studies", "sha-b"))
    bad("bad version string", lambda: register_version(conn, "economic_studies", "v2", "economic_study", "x"))
    ok("failed write left data intact", conn.execute("SELECT COUNT(*) FROM fx_facts").fetchone()[0] == 4)

    def extract_boom(headline, body):
        if "Drilling" in body:
            raise RuntimeError("boom")
        return []
    spec_err = ExtractorSpec("economic_studies", "1.0.1", "economic_study", "Economic Studies", extract_boom, "sha-c")
    c = run_batch(conn, spec_err, pending_events(conn, "economic_studies", "1.0.1"))
    ok("extractor exception recorded", c["errors"] == 1 and conn.execute(
        "SELECT status, error FROM fx_runs WHERE version='1.0.1' AND event_id='e2'").fetchone()[1] == "RuntimeError: boom")

    def extract_malformed(headline, body):
        return [Record("economic_study", [Fact("irr", value_num=1.0, source_field="raw_body", span=(0, 10**6))])]
    spec_bad = ExtractorSpec("economic_studies", "1.0.2", "economic_study", "Economic Studies", extract_malformed, "sha-e")
    c = run_batch(conn, spec_bad, pending_events(conn, "economic_studies", "1.0.2"))
    ok("malformed output recorded as error", c["errors"] == 3 and c["records"] == 0 and conn.execute(
        "SELECT COUNT(*) FROM fx_runs WHERE version='1.0.2' AND status='error' AND error LIKE 'FactsError:%'").fetchone()[0] == 3
       and conn.execute("SELECT COUNT(*) FROM fx_records WHERE version='1.0.2'").fetchone()[0] == 0)
    reject(conn, "economic_studies", "1.0.2", "test")

    build_view(conn, "economic_study", [("npv_after_tax", "num"), ("study_type", "text")])
    ok("view empty before activation", conn.execute("SELECT COUNT(*) FROM v_fx_economic_study").fetchone()[0] == 0)
    ok("activate", activate(conn, "economic_studies", "1.0.0", {"precision": 0.95}) is None)
    rows = list(conn.execute("SELECT ticker, npv_after_tax, npv_after_tax_unit, study_type, tag_confirmed "
                             "FROM v_fx_economic_study ORDER BY ticker"))
    ok("view pivots active version", [tuple(r) for r in rows] ==
       [("AAA.V", 412e6, "CAD", "PEA", 1), ("CCC.V", 412e6, "CAD", "PEA", 0)])

    def extract_v2(headline, body):
        recs = extract_v1(headline, body)
        for r in recs:
            r.facts[0].value_num = r.facts[0].value_num / 1e6
            r.facts[0].unit = "CAD_M"
        return recs
    spec2 = ExtractorSpec("economic_studies", "2.0.0", "economic_study", "Economic Studies", extract_v2, "sha-d")
    run_batch(conn, spec2, pending_events(conn, "economic_studies", "2.0.0"))
    ok("v2 beside v1, pages still on v1", conn.execute("SELECT MAX(npv_after_tax) FROM v_fx_economic_study").fetchone()[0] == 412e6)
    ok("activate v2 returns v1", activate(conn, "economic_studies", "2.0.0") == "1.0.0")
    ok("pages on v2", conn.execute("SELECT MAX(npv_after_tax) FROM v_fx_economic_study").fetchone()[0] == 412.0)
    ok("one active only", conn.execute("SELECT COUNT(*) FROM fx_extractor_versions WHERE status='active'").fetchone()[0] == 1)
    try:
        conn.execute("UPDATE fx_extractor_versions SET status='active' WHERE version='1.0.0'")
        raise AssertionError("selftest failed: second active allowed")
    except sqlite3.IntegrityError:
        passed.append("index forbids two active")
    bad("retired cannot be written", lambda: write_event(conn, "economic_studies", "1.0.0", ev1, [], True))
    ok("runner skips a retired version", run_batch(conn, spec1, [ev1])["skipped"] == "retired")
    ok("rollback returns v1", rollback(conn, "economic_studies") == "1.0.0")
    ok("pages back on v1", conn.execute("SELECT MAX(npv_after_tax) FROM v_fx_economic_study").fetchone()[0] == 412e6)
    bad("cannot purge active", lambda: purge_version(conn, "economic_studies", "1.0.0"))
    reject(conn, "economic_studies", "1.0.1", "test")
    ok("purge candidate", purge_version(conn, "economic_studies", "2.0.0", batch=1) == 2
       and conn.execute("SELECT COUNT(*) FROM fx_runs WHERE version='2.0.0'").fetchone()[0] == 0)
    bad("rejected cannot activate", lambda: activate(conn, "economic_studies", "1.0.1"))
    ok("fk cascade on", conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1)
    ok("integrity", conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
       and conn.execute("PRAGMA foreign_key_check").fetchall() == [])
    return passed


if __name__ == "__main__":
    p = _selftest()
    print(f"facts selftest: {len(p)}/{len(p)} passed")
