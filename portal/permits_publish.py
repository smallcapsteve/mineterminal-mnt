"""Publish the Permits & Approvals reader into the table /permits-approvals reads (PERMIT_PUBLISH_V1, 2026-09-22).

The facts store holds what PERMIT_V1 (portal/extractors/permits.py) found in every approved release. The page reads
permits, which this module rebuilds from the ACTIVE permits version.

One row per permit or government approval an item reports (Justin, 2026-09-22), at its stage as of the item:
planned, applied, in review, granted, renewed or contested.

What goes on the page:
  1. every approved item in which the reader found a permit, tagged Permits & Approvals or not;
  2. a MARKER row (permit_type NULL) for every tagged item that reports none, so 'show all' follows the tag;
  3. ONE PERMIT, SEVERAL ITEMS: the stages chain (Justin: "Chain the stages"). Rows of the same company, project and
     permit type within 1,095 days share a chain_key, unless they name different authorities or permit numbers, or a
     granted permit is followed by a new application (that is a new permit), or two grants sit more than 180 days
     apart. The newest item is the lead row (latest=1); its empty fields are filled from the chain, newest first.
  4. A row with no stated stage date takes the item's date.

compute() is a pure function of the items so the accuracy gate can score what a candidate version would publish
without writing anything. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.permits_publish
Self-tests: python3 -m portal.permits_publish --selftest     (in-memory; touches nothing live)
Dry run:    python3 -m portal.permits_publish --dry-run [--version X.Y.Z]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import date

EXTRACTOR = "permits"
TAG = "Permits & Approvals"
DB = "/opt/mnt/app/portal/portal.db"

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS permits (
    pm_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    slug              TEXT,
    permit_type       TEXT,
    project           TEXT,
    status            TEXT,
    authority         TEXT,
    date              TEXT,
    permit_name       TEXT,
    permit_id         TEXT,
    term              TEXT,
    expiry            TEXT,
    scope             TEXT,
    holder            TEXT,
    jurisdiction      TEXT,
    metal             TEXT,
    evidence          TEXT,
    filled_from       TEXT,
    chain_key         TEXT,
    chain_items       INTEGER NOT NULL DEFAULT 1,
    first_reported    TEXT,
    stage_rank        INTEGER,
    latest            INTEGER NOT NULL DEFAULT 1,
    n_rows            INTEGER NOT NULL DEFAULT 1,
    tag_confirmed     INTEGER NOT NULL DEFAULT 0,
    raw_headline      TEXT,
    published_at      TEXT,
    extractor_version TEXT
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_permits_pub    ON permits(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_permits_ticker ON permits(ticker);
CREATE INDEX IF NOT EXISTS idx_permits_event  ON permits(event_id);
CREATE INDEX IF NOT EXISTS idx_permits_chain  ON permits(chain_key);
"""

_ROW_FIELDS = ("permit_type", "project", "status", "authority", "date", "permit_name", "permit_id", "term", "expiry",
               "scope", "holder", "jurisdiction", "metal", "evidence")
_COLS = ("event_id", "ordinal", "ticker", "slug") + _ROW_FIELDS + (
    "filled_from", "chain_key", "chain_items", "first_reported", "stage_rank", "latest", "n_rows", "tag_confirmed",
    "raw_headline", "published_at")
_FILLABLE = ("authority", "permit_id", "term", "expiry", "scope", "holder", "jurisdiction", "metal")
CHAIN_DAYS = 1095
REGRANT_DAYS = 180
STAGE_RANK = {"planned": 1, "applied": 2, "in_review": 3, "granted": 4, "renewed": 5, "contested": 6}
_GENERIC = {"the", "project", "projects", "property", "properties", "mine", "mines", "deposit", "deposits", "gold", "silver",
            "copper", "lithium", "uranium", "nickel", "zinc", "lead", "potash", "phosphate", "molybdenum", "graphite",
            "critical", "minerals", "mineral", "metals", "polymetallic", "claims", "de", "del", "la", "and", "au", "cu"}

TYPE_LABELS = {"drill_exploration": "Drill / exploration", "environmental_assessment": "Environmental assessment",
               "plan_of_operations": "Plan of operations / notice", "mining_licence": "Mining licence / lease",
               "construction_operating": "Construction / operating", "water": "Water",
               "land_community": "Land access / community", "government_policy": "Government / policy",
               "other": "Other"}
STATUS_LABELS = {"planned": "Planned", "applied": "Applied", "in_review": "In review", "granted": "Granted",
                 "renewed": "Renewed / amended", "contested": "Contested"}


def _key_words(s):
    s = unicodedata.normalize("NFKD", s or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]+", s) if w not in _GENERIC]


def chain_key(r, ticker):
    w = _key_words(r.get("project"))
    return "%s:%s:%s" % (ticker or "?", " ".join(w[:3]) or "-", r.get("permit_type") or "?")


def _days(a, b):
    try:
        return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)
    except (TypeError, ValueError):
        return 10 ** 6


def _auth_differ(a, b):
    if not a or not b:
        return False
    wa, wb = set(_key_words(a)), set(_key_words(b))
    return not (wa & wb)


def _marker(ev):
    row = {c: None for c in _COLS}
    row.update(event_id=ev["event_id"], ordinal=0, ticker=ev.get("ticker"), slug=ev.get("slug"), n_rows=0,
               chain_items=1, latest=1, tag_confirmed=1, raw_headline=(ev.get("raw_headline") or "")[:500],
               published_at=ev.get("published_at"))
    return row


def _joinable(group, row):
    last = group[-1]
    if any(g["event_id"] == row["event_id"] for g in group):
        return False
    if _days(last["published_at"], row["published_at"]) > CHAIN_DAYS:
        return False
    if any(_auth_differ(g["authority"], row["authority"]) for g in group):
        return False
    ids = {g["permit_id"] for g in group if g["permit_id"]}
    if row["permit_id"] and ids and row["permit_id"] not in ids:
        return False
    if last["status"] in ("granted", "renewed") and row["status"] in ("planned", "applied", "in_review"):
        return False          # a new application after a grant is a new permit
    if last["status"] == "granted" and row["status"] == "granted" and \
            _days(last["published_at"], row["published_at"]) > REGRANT_DAYS:
        return False
    return True


def compute(items):
    """items: iterable of (event, parsed); event = {event_id, ticker, published_at, raw_headline, slug, tagged};
    parsed = permits.parse_records() output. Returns (rows, stats)."""
    items = sorted(items, key=lambda x: ((x[0].get("published_at") or ""), x[0]["event_id"]))
    out = []
    st = {"items": 0, "published": 0, "rows": 0, "markers": 0, "tagged_published": 0, "untagged_published": 0,
          "chains": 0, "repeat_rows": 0, "filled": 0}
    for ev, p in items:
        st["items"] += 1
        rows = [dict(r) for r in (p.get("rows") or []) if r.get("status")]
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
            row.update({k: r.get(k) for k in _ROW_FIELDS if k in r})
            if not row["date"]:
                row["date"] = (ev.get("published_at") or "")[:10] or None
            row.update(event_id=ev["event_id"], ordinal=i, ticker=ev.get("ticker"), slug=ev.get("slug"), n_rows=len(rows),
                       tag_confirmed=1 if tagged else 0, chain_key=chain_key(row, ev.get("ticker")), chain_items=1,
                       latest=1, stage_rank=STAGE_RANK.get(row["status"]),
                       first_reported=(ev.get("published_at") or "")[:10] or None,
                       raw_headline=(ev.get("raw_headline") or "")[:500], published_at=ev.get("published_at"))
            out.append(row)
            st["rows"] += 1
            st["status_" + row["status"]] = st.get("status_" + row["status"], 0) + 1
            st["type_" + (row["permit_type"] or "?")] = st.get("type_" + (row["permit_type"] or "?"), 0) + 1
    chains = {}
    for row in out:
        k = row["chain_key"]
        if not k or row["status"] is None:
            continue
        groups = chains.setdefault(k, [])
        home = None
        for g in reversed(groups):
            if _joinable(g, row):
                home = g
                break
        if home is not None:
            home.append(row)
        else:
            groups.append([row])
    n = 0
    for k, groups in chains.items():
        for g in groups:
            n += 1
            gid = "%s#%d" % (k, n)
            first = min((r["published_at"] or "")[:10] for r in g) or None
            for j, r in enumerate(g):
                r.update(chain_key=gid, chain_items=len(g), first_reported=first, latest=1 if j == len(g) - 1 else 0)
                st["repeat_rows"] += 0 if j == len(g) - 1 else 1
            lead = g[-1]
            src = []
            for other in reversed(g[:-1]):
                for f in _FILLABLE:
                    if lead.get(f) in (None, "") and other.get(f) not in (None, ""):
                        lead[f] = other[f]
                        src.append(other["event_id"][:12])
                        st["filled"] += 1
            lead["filled_from"] = ",".join(dict.fromkeys(src)) or None
    st["chains"] = n
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
    """(event, parsed) for every approved item this version found rows in, and every approved item carrying the
    tag today (those with none become marker rows)."""
    from portal.extractors import permits as X
    found = {r[0] for r in conn.execute(
        "SELECT DISTINCT r.event_id FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
        "WHERE r.extractor=? AND r.version=? AND f.field='is_permit' AND f.value_num=1",
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
                " WHERE r2.extractor=? AND r2.version=? AND f2.field='is_permit' AND f2.value_num=1)",
                (EXTRACTOR, version, EXTRACTOR, version)):
            facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    return [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]


def _ensure_schema(conn):
    conn.executescript(TABLE_SQL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(permits)")}
    for line in TABLE_SQL.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)", line)
        if m and m.group(1) not in have and m.group(1) != "pm_id":
            conn.execute("ALTER TABLE permits ADD COLUMN %s %s" % (m.group(1), m.group(2)))
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
        st["rowsync"] = rowsync.sync_rows(conn, "permits", "pm_id", _COLS, rows, {"extractor_version": version})
    conn.execute("BEGIN IMMEDIATE")
    try:
        # OPSFIX item 1 (2026-10-05): write only the rows that changed; same table contents (portal/rowsync.py)
        from portal import rowsync
        st["rowsync"] = rowsync.sync_rows(conn, "permits", "pm_id", _COLS, rows, {"extractor_version": version})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[permits_publish] " + json.dumps(st))
    return st


# ------------------------------------------------------------------ self-tests
def _selftest():
    sys.path.insert(0, "/opt/mnt/app")
    from portal import facts as F
    from portal.extractors import permits as X
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
    lead = "Toronto, %s -- ABC Gold Corp. (TSXV: ABC) (\"ABC\" or the \"Company\") "
    evs = [
        ("e1", "ABC.V", "2026-03-02", "ABC Applies for Drill Permit at Alpha Gold Project",
         lead % "March 2, 2026" + "has applied for a drilling permit from the Ontario Ministry of Mines for its Alpha "
                                  "Gold Project." + fill, TAG),
        ("e2", "ABC.V", "2026-05-15", "ABC Receives Drill Permit for Alpha Gold Project",
         lead % "May 15, 2026" + "has received a drilling permit from the Ontario Ministry of Mines for its Alpha Gold "
                                 "Project. The permit is valid for three years." + fill, TAG),
        ("e3", "ABC.V", "2026-06-01", "ABC Receives Final Court Approval for Plan of Arrangement",
         lead % "June 1, 2026" + "has obtained the final order approving the arrangement." + fill, TAG),
        ("e4", "XYZ.V", "2026-01-05", "XYZ Closes Private Placement",
         lead % "January 5, 2026" + "has closed a private placement." + fill, "Financings"),
    ]
    for eid, tk, pub, hl, body, cats in evs:
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?, 'auto_approved')",
                     (eid, tk, pub, None, hl, body, eid + "-slug", cats))
    F.run_batch(conn, spec, [dict(r) for r in conn.execute("SELECT * FROM events")])
    rows, st = compute(load_items(conn, "9.9.9"))
    by = {}
    for r in rows:
        by.setdefault(r["event_id"], []).append(r)
    eq("applied row", [(r["permit_type"], r["status"], r["latest"], r["date"]) for r in by["e1"]],
       [("drill_exploration", "applied", 0, "2026-03-02")])
    eq("granted row is the lead", [(r["status"], r["latest"], r["chain_items"], r["first_reported"], r["authority"])
                                   for r in by["e2"]],
       [("granted", 1, 2, "2026-03-02", "Ontario Ministry of Mines")])
    eq("same permit", by["e1"][0]["chain_key"] == by["e2"][0]["chain_key"], True)
    eq("marker for a tagged court approval", [(r["permit_type"], r["n_rows"]) for r in by["e3"]], [(None, 0)])
    eq("untagged, nothing -> absent", by.get("e4"), None)
    publish(conn, "9.9.9", log=lambda *_: None)
    publish(conn, "9.9.9", log=lambda *_: None)
    eq("idempotent", conn.execute("SELECT COUNT(*) FROM permits").fetchone()[0], len(rows))
    print("permits_publish: %s" % ("ok" if not bad else "%d FAILURES" % bad))
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
            print("[permits_publish] dry run: no version given and none active")
            return 2
        rows, st = compute(load_items(conn, v))
        st.update(version=v)
        print("[permits_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[permits_publish] no active permits version; nothing to publish")
        return 0
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[permits_publish] FAILED publishing %s: %s: %s" % (version, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
