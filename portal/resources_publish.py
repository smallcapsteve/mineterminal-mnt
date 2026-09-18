"""Publish the new Resource Estimates reader into the table /resources reads
(RES_PUBLISH_V1, 2026-09-18).

The facts store holds what RES_V1 (portal/extractors/resources.py) found in every release. The page
does not read the facts store directly: it reads resource_estimates. This module turns the ACTIVE
resources version into that table.

One row per deposit per category (Justin, 2026-09-18). The old table had exactly one row per
release -- 179 rows for 642 tagged releases -- with every category of every deposit folded into a
JSON column. A release stating measured, indicated and inferred tonnes for two pits was one row.

Every resource figure the release states is published, and the ones that restate an older or
another project's estimate are marked (context = 'background') rather than dropped (Justin,
2026-09-18).

Rules, in order, over tagged approved releases oldest first:
  1. the extractor found at least one figure (is_resource_estimate = 1)
  2. a row needs a category; a release that gives a tonnage with no category is tagged but not shown
  3. no cross-release suppression: a restated estimate is a real thing to show, marked background

compute() is a pure function of (events, facts) so the accuracy gate can count the rows a candidate
version would publish without writing anything. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.resources_publish
  - an active resources version exists -> publish it
  - none yet                           -> run the legacy resource_backfill.py (unchanged)
Once a version is active the legacy backfill never runs again (fix forward, never fall back). If
publishing fails after the switch, rows the legacy backfill wrote are removed rather than left on
the page wearing the new reader's name.

Self-tests: python3 -m portal.resources_publish --selftest   (in-memory; touches nothing live)
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import time

EXTRACTOR = "resources"
TAG = "Resource Estimates"
DB = "/opt/mnt/app/portal/portal.db"
LEGACY = "/opt/mnt/app/resource_backfill.py"

# The legacy columns kept below the new ones are not dead weight: /api/resources/recent.json serves
# summary, metal_focus, headline_oz_au, headline_t_metal and categories_json to MineTerminalPro, and
# dropping them would 500 that endpoint on another site.
TABLE_SQL = """
CREATE TABLE IF NOT EXISTS resource_estimates (
    res_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    deposit           TEXT,
    project           TEXT,
    category          TEXT,
    tonnes            REAL,
    grades_json       TEXT,
    contained_json    TEXT,
    cut_off           TEXT,
    basis             TEXT,
    context           TEXT,
    source_shape      TEXT,
    mre_type          TEXT,
    n_rows            INTEGER NOT NULL DEFAULT 1,
    summary           TEXT,
    metal_focus       TEXT,
    headline_oz_au    REAL,
    headline_t_metal  REAL,
    n_categories      INTEGER,
    categories_json   TEXT,
    raw_headline      TEXT,
    published_at      TEXT,
    extractor_version TEXT
);
"""

# built after the columns are in place, because the legacy table of the same name has neither
# `ordinal` nor `category` and an index on a missing column fails the whole script
INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_res_event_ord ON resource_estimates(event_id, ordinal);
CREATE INDEX IF NOT EXISTS ix_res_ticker    ON resource_estimates(ticker);
CREATE INDEX IF NOT EXISTS ix_res_published ON resource_estimates(published_at);
CREATE INDEX IF NOT EXISTS ix_res_oz_au     ON resource_estimates(headline_oz_au);
CREATE INDEX IF NOT EXISTS ix_res_category  ON resource_estimates(category);
CREATE INDEX IF NOT EXISTS ix_res_deposit   ON resource_estimates(deposit);
CREATE INDEX IF NOT EXISTS ix_res_context   ON resource_estimates(context);
"""

LB_PER_T = 2204.62262


# ------------------------------------------------------------------ how a row reads on the page
def fmt_tonnes(t):
    if t is None:
        return None
    if t >= 1e6:
        return "%.2f Mt" % (t / 1e6)
    if t >= 1e3:
        return "%.0f kt" % (t / 1e3)
    return "%.0f t" % t


def fmt_grade(g):
    v, u, m = g.get("value"), g.get("unit") or "", g.get("metal") or ""
    if v is None:
        return ""
    s = ("%g" % round(v, 4)) + ((" " + u) if u else "")
    return (s + " " + m).strip()


def fmt_contained(c):
    v, u, m = c.get("value"), c.get("unit") or "", c.get("metal") or ""
    if v is None:
        return ""
    if u == "oz":
        s = ("%.2f Moz" % (v / 1e6)) if v >= 1e6 else ("%.0f koz" % (v / 1e3)) if v >= 1e4 \
            else ("%.1f koz" % (v / 1e3)) if v >= 1e3 else ("%.0f oz" % v)
    elif u == "lb":
        s = ("%.1f Mlb" % (v / 1e6)) if v >= 1e6 else ("%.0f klb" % (v / 1e3)) if v >= 1e3 \
            else ("%.0f lb" % v)
    elif u == "t":
        s = ("%.0f kt" % (v / 1e3)) if v >= 1e4 else ("%.0f t" % v)
    else:
        s = ("%g" % v) + ((" " + u) if u else "")
    return (s + " " + m).strip()


def summary_of(r):
    """One line, the way the figure is said out loud: 6.30 Mt @ 1.85 g/t Au for 375 koz Au."""
    bits = []
    t = fmt_tonnes(r.get("tonnes"))
    if t:
        bits.append(t)
    gs = ", ".join(x for x in (fmt_grade(g) for g in r.get("grades") or []) if x)
    if gs:
        bits.append(("@ " + gs) if bits else gs)
    cs = ", ".join(x for x in (fmt_contained(c) for c in r.get("contained") or []) if x)
    if cs:
        bits.append(("for " + cs) if bits else cs)
    return " ".join(bits) or None


def headline_oz_au(r):
    """Contained gold in troy ounces, for ranking. Only gold, only when the release states it."""
    for c in r.get("contained") or []:
        if (c.get("metal") or "").lower() in ("au", "gold") and c.get("unit") == "oz":
            return float(c["value"])
    return None


def headline_t_metal(r):
    """Contained metal in tonnes, whichever metal the release leads with."""
    for c in r.get("contained") or []:
        if c.get("unit") == "t":
            return float(c["value"])
        if c.get("unit") == "lb":
            return float(c["value"]) / LB_PER_T
    return None


def metal_focus(r):
    for g in r.get("grades") or []:
        if g.get("metal"):
            return g["metal"]
    for c in r.get("contained") or []:
        if c.get("metal"):
            return c["metal"]
    return None


def compute(items):
    """items: iterable of (event, parsed), event = {event_id, ticker, published_at, raw_headline},
    parsed = the analyse()-shaped dict. Returns (rows, stats); rows are dicts ready to insert."""
    items = sorted(items, key=lambda x: ((x[0].get("published_at") or ""), x[0]["event_id"]))
    rows, stats = [], {"releases": 0, "no_figures": 0, "published": 0, "rows": 0, "background": 0,
                       "with_tonnage": 0, "with_grade": 0, "with_deposit": 0}
    for ev, p in items:
        stats["releases"] += 1
        found = [r for r in (p.get("rows") or []) if r.get("category")]
        if not p.get("is_resource_estimate") or not found:
            stats["no_figures"] += 1
            continue
        cats = [{"category": r.get("category"), "stat": summary_of(r) or ""} for r in found]
        cjson = json.dumps(cats, ensure_ascii=False)
        ncat = len({r.get("category") for r in found})
        for i, r in enumerate(found):
            rows.append({
                "event_id": ev["event_id"], "ordinal": i, "ticker": ev.get("ticker"),
                "deposit": r.get("deposit"), "project": p.get("project"), "category": r.get("category"),
                "tonnes": r.get("tonnes"),
                "grades_json": json.dumps(r.get("grades") or [], ensure_ascii=False),
                "contained_json": json.dumps(r.get("contained") or [], ensure_ascii=False),
                "cut_off": r.get("cut_off"), "basis": r.get("basis") or "resource",
                "context": r.get("context") or "announced", "source_shape": r.get("source"),
                "mre_type": p.get("mre_type"), "n_rows": len(found),
                "summary": summary_of(r), "metal_focus": metal_focus(r),
                "headline_oz_au": headline_oz_au(r), "headline_t_metal": headline_t_metal(r),
                "n_categories": ncat, "categories_json": cjson,
                "raw_headline": (ev.get("raw_headline") or "")[:500],
                "published_at": ev.get("published_at")})
            stats["background"] += (r.get("context") == "background")
            stats["with_tonnage"] += (r.get("tonnes") is not None)
            stats["with_grade"] += bool(r.get("grades"))
            stats["with_deposit"] += bool(r.get("deposit"))
        stats["published"] += 1
        stats["rows"] += len(found)
    return rows, stats


# ------------------------------------------------------------------ reading the facts store
def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def active_version(conn):
    r = conn.execute("SELECT version FROM fx_extractor_versions WHERE extractor=? AND status='active'",
                     (EXTRACTOR,)).fetchone() if _has_table(conn, "fx_extractor_versions") else None
    return r[0] if r else None


def load_items(conn, version):
    """(event, parsed) for every approved release carrying the Resource Estimates tag today that this
    version wrote records for. One release has one record per figure, so facts are grouped by ordinal."""
    from portal.extractors import resources as X
    evs = {}
    for eid, tk, pub, hl in conn.execute(
            "SELECT DISTINCT e.event_id, e.ticker, e.published_at, e.raw_headline FROM events e "
            "JOIN fx_records r ON r.event_id=e.event_id AND r.extractor=? AND r.version=? "
            "WHERE e.review_status='auto_approved' AND ('|' || COALESCE(e.categories,'') || '|') LIKE ?",
            (EXTRACTOR, version, "%|" + TAG + "|%")):
        evs[eid] = {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl}
    facts = {}
    for eid, ordinal, field_, seq, num, text, unit, metal in conn.execute(
            "SELECT r.event_id, r.ordinal, f.field, f.seq, f.value_num, f.value_text, f.unit, f.metal "
            "FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
            "WHERE r.extractor=? AND r.version=?", (EXTRACTOR, version)):
        if eid in evs:
            facts.setdefault(eid, {}).setdefault(ordinal, []).append(
                _F(field_, seq, num, text, unit, metal))
    return [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]


class _F:
    """The five fields portal.extractors.resources.parse_records reads off a Fact."""
    __slots__ = ("field", "seq", "value_num", "value_text", "unit", "metal")

    def __init__(self, field, seq, value_num, value_text, unit, metal):
        self.field, self.seq = field, seq
        self.value_num, self.value_text = value_num, value_text
        self.unit, self.metal = unit, metal


def current_event_ids(conn):
    if not _has_table(conn, "resource_estimates"):
        return set()
    return {r[0] for r in conn.execute("SELECT DISTINCT event_id FROM resource_estimates")}


_COLS = ("event_id", "ordinal", "ticker", "deposit", "project", "category", "tonnes", "grades_json",
         "contained_json", "cut_off", "basis", "context", "source_shape", "mre_type", "n_rows",
         "summary", "metal_focus", "headline_oz_au", "headline_t_metal", "n_categories",
         "categories_json", "raw_headline", "published_at")


def publish(conn, version, log=print):
    """Rebuild resource_estimates from `version` in one transaction. Returns stats."""
    if not re.match(r"^[0-9]+[.][0-9]+[.][0-9]+$", version or ""):
        raise ValueError(f"bad version {version!r}")
    t0 = time.time()
    rows, st = compute(load_items(conn, version))
    _ensure_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM resource_estimates")
        conn.executemany(
            "INSERT INTO resource_estimates(" + ", ".join(_COLS) + ", extractor_version) VALUES ("
            + ", ".join(":" + c for c in _COLS) + ", '" + version + "')", rows)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[resources_publish] " + json.dumps(st))
    return st


def _one_row_per_event(conn):
    """True when the table can hold only one row per release: the legacy shape.

    resource_estimates as the old backfill created it declares `event_id TEXT NOT NULL UNIQUE`, which
    SQLite enforces through sqlite_autoindex_resource_estimates_1 -- exactly what this publisher
    replaces. SQLite cannot drop a constraint, so a table of that shape has to be rebuilt rather than
    altered. The management ship found this out the hard way: the first publish after the gate died on
    `UNIQUE constraint failed: management_changes.event_id` and the page was empty for five minutes."""
    for row in conn.execute("PRAGMA index_list(resource_estimates)"):
        name, unique = row[1], row[2]
        if not unique:
            continue
        cols = [r[2] for r in conn.execute('PRAGMA index_info("%s")' % str(name).replace('"', '""'))]
        if cols == ["event_id"]:
            return True
    return False


def _ensure_schema(conn):
    """The table this publisher needs: one row per deposit per category, so event_id repeats.

    A legacy table of the same name is rebuilt (its rows come back from the facts store on this same
    run); anything else just gains the columns it is missing."""
    if _has_table(conn, "resource_estimates") and _one_row_per_event(conn):
        conn.execute("DROP TABLE resource_estimates")
    conn.executescript(TABLE_SQL)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(resource_estimates)")}
    for col, decl in (("ordinal", "INTEGER NOT NULL DEFAULT 0"), ("deposit", "TEXT"),
                      ("category", "TEXT"), ("tonnes", "REAL"), ("grades_json", "TEXT"),
                      ("contained_json", "TEXT"), ("cut_off", "TEXT"), ("basis", "TEXT"),
                      ("context", "TEXT"), ("source_shape", "TEXT"), ("mre_type", "TEXT"),
                      ("n_rows", "INTEGER NOT NULL DEFAULT 1"), ("summary", "TEXT"),
                      ("metal_focus", "TEXT"), ("headline_oz_au", "REAL"),
                      ("headline_t_metal", "REAL"), ("n_categories", "INTEGER"),
                      ("categories_json", "TEXT"), ("project", "TEXT"), ("ticker", "TEXT"),
                      ("raw_headline", "TEXT"), ("published_at", "TEXT"),
                      ("extractor_version", "TEXT")):
        if col not in cols:
            conn.execute(f"ALTER TABLE resource_estimates ADD COLUMN {col} {decl}")
    conn.executescript(INDEX_SQL)


# ------------------------------------------------------------------ self-tests
def _selftest():
    bad = 0

    def ok(name, cond):
        nonlocal bad
        bad += not cond
        print(("  ok    " if cond else "  FAIL  ") + name)

    def g(metal, value, unit):
        return {"metal": metal, "value": value, "unit": unit}

    def row(dep, cat, t, grades=(), contained=(), ctx="announced", cut=None):
        return {"deposit": dep, "category": cat, "tonnes": t, "grades": list(grades),
                "contained": list(contained), "cut_off": cut, "basis": "resource",
                "context": ctx, "source": "table"}

    def parsed(rows, project="Foo", mtype="Maiden"):
        return {"is_resource_estimate": bool(rows), "rows": rows, "project": project,
                "mre_type": mtype}

    def ev(eid, tk, pub):
        return {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": "H " + eid}

    items = [
        (ev("e1", "AAA", "2026-01-01"), parsed([
            row("Foo", "Indicated", 6.3e6, [g("Au", 1.85, "g/t")], [g("Au", 375000.0, "oz")]),
            row("Foo", "Inferred", 2.1e6, [g("Au", 1.20, "g/t")], [g("Au", 81000.0, "oz")])])),
        (ev("e2", "AAA", "2026-01-02"), parsed([
            row("Bar", "Indicated", 8.2e6, [g("Cu", 0.46, "%")], [g("Cu", 8.3e7, "lb")]),
            row("Bar", "Indicated", 7.0e6, [g("Cu", 0.40, "%")], [], ctx="background")])),
        (ev("e3", "BBB", "2026-01-03"), parsed([])),
        (ev("e4", "BBB", "2026-01-04"), parsed([row("Baz", None, 1.0e6)])),
    ]
    rows, st = compute(items)
    byid = {}
    for r in rows:
        byid.setdefault(r["event_id"], []).append(r)
    ok("one row per deposit per category", [len(byid.get(e, [])) for e in ("e1", "e2", "e3", "e4")]
       == [2, 2, 0, 0])
    ok("a figure with no category is not published", "e4" not in byid)
    ok("a release with no figures is not published", "e3" not in byid)
    ok("ordinals are 0..n-1", sorted(r["ordinal"] for r in byid["e1"]) == [0, 1])
    ok("n_rows counts the rows of that release", {r["n_rows"] for r in byid["e1"]} == {2})
    ok("a restated estimate is published and marked",
       [r["context"] for r in byid["e2"]] == ["announced", "background"] and st["background"] == 1)
    ok("counts add up", st["rows"] == len(rows) == 4 and st["published"] == 2
       and st["no_figures"] == 2 and st["with_tonnage"] == 4 and st["with_grade"] == 4)
    ok("summary reads the way the figure is said",
       byid["e1"][0]["summary"] == "6.30 Mt @ 1.85 g/t Au for 375 koz Au")
    ok("contained gold in ounces is the ranking figure",
       (byid["e1"][0]["headline_oz_au"], byid["e2"][1]["headline_oz_au"]) == (375000.0, None))
    ok("contained pounds become tonnes of metal",
       round(byid["e2"][0]["headline_t_metal"]) == round(8.3e7 / LB_PER_T))
    ok("metal focus is the metal graded", byid["e2"][0]["metal_focus"] == "Cu")
    ok("every category of the release travels with each of its rows",
       [c["category"] for c in json.loads(byid["e1"][0]["categories_json"])] == ["Indicated", "Inferred"]
       and byid["e1"][0]["n_categories"] == 2)
    ok("tonnages read in mining units",
       (fmt_tonnes(6.3e6), fmt_tonnes(630000.0), fmt_tonnes(620.0), fmt_tonnes(None))
       == ("6.30 Mt", "630 kt", "620 t", None))
    ok("contained figures read in mining units",
       (fmt_contained(g("Au", 2.5e6, "oz")), fmt_contained(g("Au", 375000.0, "oz")),
        fmt_contained(g("Au", 4200.0, "oz")), fmt_contained(g("Cu", 8.3e7, "lb")),
        fmt_contained(g("Sb", 67000.0, "t")))
       == ("2.50 Moz Au", "375 koz Au", "4.2 koz Au", "83.0 Mlb Cu", "67 kt Sb"))

    # the database path, end to end, on an in-memory store
    from portal import facts as F
    from portal.extractors import resources as X
    conn = F.connect(":memory:")
    F.ensure_schema(conn)
    conn.execute("CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, published_at TEXT, "
                 "raw_headline TEXT, raw_body TEXT, categories TEXT, review_status TEXT)")
    # the legacy shape: one row per release, UNIQUE on event_id. This is the constraint that emptied
    # the management page for five minutes on 2026-09-17, so the test creates it deliberately.
    conn.execute("CREATE TABLE resource_estimates (res_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "event_id TEXT NOT NULL UNIQUE, "
                 "ticker TEXT, project TEXT, summary TEXT, headline_oz_au REAL, headline_t_metal REAL, "
                 "metal_focus TEXT, raw_headline TEXT, published_at TEXT, n_categories INTEGER, "
                 "mre_type TEXT, categories_json TEXT)")
    conn.execute("CREATE INDEX ix_res_ticker ON resource_estimates(ticker)")
    conn.execute("INSERT INTO resource_estimates(event_id, ticker) VALUES ('old1','AAA')")
    ok("the test starts from the legacy one-row-per-release shape", _one_row_per_event(conn))
    F.register_version(conn, EXTRACTOR, X.VERSION, X.KIND, TAG)
    rows_in = [
        ("x0", "T0", "2026-01-01", "Acme Gold Announces Maiden Mineral Resource Estimate for the Foo Project",
         "Acme Gold Corp. is pleased to announce the maiden mineral resource estimate for its Foo Project. "
         "Indicated Mineral Resources of 6.3 million tonnes grading 1.85 g/t Au for 375,000 ounces of gold. "
         "Inferred Mineral Resources total 2.1 million tonnes averaging 1.20 g/t Au containing 81,000 ounces.",
         "Resource Estimates"),
        ("x1", "T1", "2026-01-02", "Beta Metals Engages Consultant to Prepare Resource Update",
         "Beta Metals Corp. announces that it has engaged an independent consultant to prepare an updated "
         "mineral resource estimate for its Bar Project in due course.", "Resource Estimates"),
        ("x2", "T2", "2026-01-03", "Gamma Mining Announces Resource Estimate for the Baz Project",
         "Gamma Mining Ltd. announces Indicated Mineral Resources of 4.0 million tonnes grading 0.90% Cu.",
         "Drill Results"),
    ]
    conn.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,'auto_approved')", rows_in)
    F.run_batch(conn, X.SPEC, F.pending_events(conn, EXTRACTOR, X.VERSION))
    ok("no active version yet", active_version(conn) is None)
    F.activate(conn, EXTRACTOR, X.VERSION)
    st2 = publish(conn, X.VERSION, log=lambda s: None)
    got = [tuple(r) for r in conn.execute(
        "SELECT event_id, ordinal, deposit, category, tonnes FROM resource_estimates "
        "ORDER BY event_id, ordinal")]
    ok("the legacy one-row-per-release table was rebuilt", not _one_row_per_event(conn))
    ok("tagged releases only, legacy row gone",
       [x[0] for x in got] == ["x0", "x0"] and not any(x[0] == "old1" for x in got))
    ok("two categories, two rows, one release",
       sorted((x[3], x[4]) for x in got) == [("Indicated", 6300000.0), ("Inferred", 2100000.0)])
    ok("the deposit is named", {x[2] for x in got} == {"Foo"})
    ok("a release that only promises an estimate is not published", not any(x[0] == "x1" for x in got))
    ok("an untagged release is not published", not any(x[0] == "x2" for x in got))
    ok("extractor_version stamped",
       [tuple(r) for r in conn.execute("SELECT DISTINCT extractor_version FROM resource_estimates")]
       == [(X.VERSION,)])
    ok("publish is repeatable", publish(conn, X.VERSION, log=lambda s: None)["rows"] == st2["rows"])
    ok("dry run counts without writing",
       compute(load_items(conn, X.VERSION))[1]["rows"] == st2["rows"])
    print("failures: %d" % bad)
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
        rows, st = compute(load_items(conn, v))
        cur = current_event_ids(conn)
        new = {r["event_id"] for r in rows}
        st.update(version=v, current_events=len(cur), removed=len(cur - new), added=len(new - cur))
        print("[resources_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[resources_publish] no active resources version; running the legacy resource_backfill.py")
        return subprocess.call([sys.executable, LEGACY])
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[resources_publish] FAILED publishing {version}: {type(exc).__name__}: {exc}")
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(resource_estimates)")}
            if "extractor_version" not in cols or conn.execute(
                    "SELECT 1 FROM resource_estimates WHERE extractor_version IS NULL LIMIT 1").fetchone():
                conn.execute("DELETE FROM resource_estimates" + (" WHERE extractor_version IS NULL"
                                                                 if "extractor_version" in cols else ""))
                print("[resources_publish] removed rows written by the legacy reader (no fallback after the switch)")
        except Exception as exc2:  # noqa: BLE001
            print(f"[resources_publish] could not clear legacy rows: {exc2}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
