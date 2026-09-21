"""Publish the Production Results reader into the table /production-results reads (PROD_PUBLISH_V1,
2026-09-21).

The facts store holds what PROD_V1 (portal/extractors/production.py) found in every approved release. The
page reads production_results, which this module rebuilds from the ACTIVE production version. Like
/economic-studies it replaces nothing: the URL showed a plain list of tagged releases, so there is no legacy
table and no legacy backfill.

One row per metal per period (Justin, 2026-09-21), of three kinds -- actual, guidance, milestone.

What goes on the page:
  1. every approved release in which the reader found a row, tagged Production Results or not (the tag
     misses real production releases -- Energy Fuels, Sierra Madre, Equinox guidance -- and leaks oil and
     gas, royalty payments and developers);
  2. a MARKER row (kind NULL) for every tagged release that states none, so the page follows the tag;
  3. GUIDANCE FOR A PERIOD THAT HAD ENDED by the release date is not a row of its own: it goes on the
     actual row for that period and metal as guided_low / guided_high (Justin, 2026-09-21), so the page can
     say whether guidance was met. Torex's January release shows FY2024 452,523 oz, guided 450,000-470,000.
     With no actual row to carry it, it is dropped -- it is a comparison, not news. The reader cannot do
     this: it never sees the release date.
  4. a restatement of figures already published (Torex's Q3 in its production release and again in its
     results) is shown both times (Justin, 2026-09-21).

compute() is a pure function of the items so the accuracy gate can score what a candidate version would
publish without writing anything. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.production_publish
Self-tests: python3 -m portal.production_publish --selftest     (in-memory; touches nothing live)
Dry run:    python3 -m portal.production_publish --dry-run [--version X.Y.Z]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time

EXTRACTOR = "production"
TAG = "Production Results"
DB = "/opt/mnt/app/portal/portal.db"

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS production_results (
    pr_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    slug              TEXT,
    kind              TEXT,
    period            TEXT,
    period_end        TEXT,
    metal             TEXT,
    unit              TEXT,
    qty               REAL,
    low               REAL,
    high              REAL,
    sold              REAL,
    aisc              REAL,
    guided_low        REAL,
    guided_high       REAL,
    milestone         TEXT,
    asset             TEXT,
    basis             TEXT,
    approx            INTEGER NOT NULL DEFAULT 0,
    n_rows            INTEGER NOT NULL DEFAULT 1,
    tag_confirmed     INTEGER NOT NULL DEFAULT 0,
    raw_headline      TEXT,
    published_at      TEXT,
    extractor_version TEXT
);
"""
INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_prod_pub    ON production_results(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_prod_ticker ON production_results(ticker);
CREATE INDEX IF NOT EXISTS idx_prod_event  ON production_results(event_id);
"""

_COLS = ("event_id", "ordinal", "ticker", "slug", "kind", "period", "period_end", "metal", "unit", "qty", "low",
         "high", "sold", "aisc", "guided_low", "guided_high", "milestone", "asset", "basis", "approx", "n_rows",
         "tag_confirmed", "raw_headline", "published_at")
_ROW_FIELDS = ("kind", "period", "metal", "unit", "qty", "low", "high", "sold", "aisc", "milestone", "asset",
               "basis", "approx")

_QEND = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}


def period_end(period):
    """'Q3 2025' -> '2025-09-30'; 'H1 2025' -> '2025-06-30'; 'FY 2025' -> '2025-12-31'; '2025-03' -> '2025-03-31'.
    A fiscal period ('Q1 FY2026') has no calendar end the reader knows: None."""
    p = (period or "").strip()
    m = re.fullmatch(r"Q([1-4]) (20\d\d)", p)
    if m:
        return "%s-%s" % (m.group(2), _QEND[m.group(1)])
    m = re.fullmatch(r"H([12]) (20\d\d)", p)
    if m:
        return "%s-%s" % (m.group(2), "06-30" if m.group(1) == "1" else "12-31")
    m = re.fullmatch(r"FY (20\d\d)", p)
    if m:
        return "%s-12-31" % m.group(1)
    m = re.fullmatch(r"(20\d\d)-(\d\d)", p)
    if m:
        import calendar
        return "%s-%s-%02d" % (m.group(1), m.group(2), calendar.monthrange(int(m.group(1)), int(m.group(2)))[1])
    return None


def fold_past_guidance(rows, published_at):
    """Guidance for a period that ended on or before the release date goes on the actual row."""
    day = (published_at or "")[:10]
    out = []
    actual = {(r["period"], r["metal"]): r for r in rows if r.get("kind") == "actual"}
    for r in rows:
        if r.get("kind") == "guidance":
            end = period_end(r.get("period"))
            if end and day and end <= day:
                a = actual.get((r["period"], r["metal"]))
                if a is not None and a.get("guided_low") is None and a.get("guided_high") is None:
                    a["guided_low"], a["guided_high"] = r.get("low"), r.get("high")
                continue
        out.append(r)
    return out


# ------------------------------------------------------------------ formatting (the page uses these)
def fmt_qty(v, unit=None):
    if v is None:
        return None
    a = abs(v)
    if unit == "lb" and a >= 1e6:
        s = ("%.3f" % (a / 1e6)).rstrip("0").rstrip(".") + "M lb"
    elif a >= 1e6:
        s = ("%.3f" % (a / 1e6)).rstrip("0").rstrip(".") + "M" + (" " + unit if unit else "")
    elif a >= 100:
        s = "{:,.0f}".format(a) + (" " + unit if unit else "")
    else:
        s = ("%.1f" % a).rstrip("0").rstrip(".") + (" " + unit if unit else "")
    return ("-" if v < 0 else "") + s


def fmt_range(low, high, unit=None):
    if low is None and high is None:
        return None
    if high is None:
        return "≥ " + fmt_qty(low, unit)
    if low is None:
        return "≤ " + fmt_qty(high, unit)
    if low == high:
        return fmt_qty(low, unit)
    return fmt_qty(low).replace(" ", "") + " – " + fmt_qty(high, unit)


MILESTONE_LABELS = {"commercial_production": "Commercial production", "first_pour": "First pour",
                    "resumption": "Operations resumed", "first_production": "First production",
                    "first_shipment": "First shipment", "restart": "Restart", "suspension": "Suspension"}


# ------------------------------------------------------------------ compute (pure)
def _marker(ev):
    row = {c: None for c in _COLS}
    row.update(event_id=ev["event_id"], ordinal=0, ticker=ev.get("ticker"), slug=ev.get("slug"), n_rows=0,
               approx=0, tag_confirmed=1, raw_headline=(ev.get("raw_headline") or "")[:500],
               published_at=ev.get("published_at"))
    return row


def compute(items):
    """items: iterable of (event, parsed); event = {event_id, ticker, published_at, raw_headline, slug, tagged};
    parsed = production.parse_records() output. Returns (rows, stats)."""
    items = sorted(items, key=lambda x: ((x[0].get("published_at") or ""), x[0]["event_id"]))
    out = []
    st = {"releases": 0, "published": 0, "rows": 0, "markers": 0, "tagged_published": 0, "untagged_published": 0,
          "actual": 0, "guidance": 0, "milestone": 0, "folded": 0}
    for ev, p in items:
        st["releases"] += 1
        rows = [dict(r) for r in (p.get("rows") or []) if r.get("kind")]
        n0 = sum(1 for r in rows if r["kind"] == "guidance")
        rows = fold_past_guidance(rows, ev.get("published_at"))
        # an 'actual' for a period that had not ended when the release came out is a plan or a year-to-date
        # figure read as a period ('250,000 ounces in 2026' in an October 2025 release): never a row
        day = (ev.get("published_at") or "")[:10]
        keep = [r for r in rows if not (r["kind"] == "actual" and day and (period_end(r.get("period")) or "0") > day)]
        st["future_actuals"] = st.get("future_actuals", 0) + len(rows) - len(keep)
        rows = keep
        st["folded"] += n0 - sum(1 for r in rows if r["kind"] == "guidance")
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
            row.update(guided_low=r.get("guided_low"), guided_high=r.get("guided_high"),
                       approx=1 if r.get("approx") else 0, period_end=period_end(r.get("period")),
                       event_id=ev["event_id"], ordinal=i, ticker=ev.get("ticker"), slug=ev.get("slug"),
                       n_rows=len(rows), tag_confirmed=1 if tagged else 0,
                       raw_headline=(ev.get("raw_headline") or "")[:500], published_at=ev.get("published_at"))
            out.append(row)
            st["rows"] += 1
            st[r["kind"]] = st.get(r["kind"], 0) + 1
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
    from portal.extractors import production as X
    found = {r[0] for r in conn.execute(
        "SELECT DISTINCT r.event_id FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
        "WHERE r.extractor=? AND r.version=? AND f.field='is_production' AND f.value_num=1",
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
                " WHERE r2.extractor=? AND r2.version=? AND f2.field='is_production' AND f2.value_num=1)",
                (EXTRACTOR, version, EXTRACTOR, version)):
            facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    return [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]


def _ensure_schema(conn):
    conn.executescript(TABLE_SQL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(production_results)")}
    for line in TABLE_SQL.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)", line)
        if m and m.group(1) not in have and m.group(1) != "pr_id":
            conn.execute("ALTER TABLE production_results ADD COLUMN %s %s" % (m.group(1), m.group(2)))
    conn.executescript(INDEX_SQL)


def publish(conn, version, log=print):
    if not re.match(r"^[0-9]+[.][0-9]+[.][0-9]+$", version or ""):
        raise ValueError("bad version %r" % (version,))
    t0 = time.time()
    rows, st = compute(load_items(conn, version))
    _ensure_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM production_results")
        conn.executemany(
            "INSERT INTO production_results(" + ", ".join(_COLS) + ", extractor_version) VALUES ("
            + ", ".join(":" + c for c in _COLS) + ", '" + version + "')", rows)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[production_publish] " + json.dumps(st))
    return st


# ------------------------------------------------------------------ self-tests
def _selftest():
    sys.path.insert(0, "/opt/mnt/app")
    from portal import facts as F
    from portal.extractors import production as X
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
    evs = [
        # a finished year's guidance printed beside its actual: folded onto the actual row
        ("e1", "TXG.TO", "2025-01-08", "Torex Gold Delivers on Full-Year Production Guidance 2024",
         "Torex reports fourth quarter gold production of 103,795 ounces and full-year gold production of 452,523 oz, "
         "within the Company's revised guidance range of 450,000 to 470,000 oz.", "Production Results"),
        # this year's guidance stays a row of its own
        ("e2", "ARTG.V", "2026-04-09", "Artemis Gold Announces Q1 2026 Production Results",
         "Blackwater produced 61,923 ounces of gold in Q1 2026. The Company is maintaining its full year production "
         "guidance of 265,000 to 290,000 ounces of gold.", "Production Results"),
        # tagged, no figures -> one marker
        ("e3", "FF.TO", "2026-03-31", "First Mining Announces Year-End 2025 Financial Results",
         "The Company advanced its Springpole project.", "Production Results|Financials"),
        # untagged with figures -> published, marked untagged
        ("e4", "SM.V", "2026-05-19", "Sierra Madre Reports Q1 2026 Results",
         "Sierra Madre produced 58,506 ounces of silver and 932 ounces of gold in Q1 2026.", "Financials"),
        # untagged, no figures -> nothing
        ("e5", "XYZ.V", "2026-01-05", "XYZ Drills 12 m of 3 g/t Gold", "Drilling continues.", "Drill Results"),
    ]
    for eid, tk, pub, hl, body, cats in evs:
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?, 'auto_approved')",
                     (eid, tk, pub, None, hl, body, eid + "-slug", cats))
    F.run_batch(conn, spec, [dict(r) for r in conn.execute("SELECT * FROM events")])
    rows, st = compute(load_items(conn, "9.9.9"))
    by = {}
    for r in rows:
        by.setdefault(r["event_id"], []).append(r)
    eq("past guidance folded", [(r["kind"], r["period"], r["qty"], r["guided_low"], r["guided_high"]) for r in by["e1"]],
       [("actual", "Q4 2024", 103795.0, None, None), ("actual", "FY 2024", 452523.0, 450000.0, 470000.0)])
    eq("current guidance kept", [(r["kind"], r["period"]) for r in by["e2"]], [("actual", "Q1 2026"), ("guidance", "FY 2026")])
    eq("marker", [(r["kind"], r["n_rows"]) for r in by["e3"]], [(None, 0)])
    eq("untagged published", [r["tag_confirmed"] for r in by["e4"]], [0, 0])
    eq("untagged, nothing -> absent", by.get("e5"), None)
    eq("stats", (st["published"], st["markers"], st["folded"]), (3, 1, 1))
    publish(conn, "9.9.9", log=lambda *_: None)
    publish(conn, "9.9.9", log=lambda *_: None)
    eq("idempotent", conn.execute("SELECT COUNT(*) FROM production_results").fetchone()[0], len(rows))
    eq("period_end", (period_end("Q3 2025"), period_end("H1 2025"), period_end("FY 2024"), period_end("2025-02"),
                      period_end("Q1 FY2026")), ("2025-09-30", "2025-06-30", "2024-12-31", "2025-02-28", None))
    eq("formats", (fmt_qty(452523, "oz"), fmt_qty(14e6, "lb"), fmt_range(265000, 290000, "oz"), fmt_range(375000, None, "oz")),
       ("452,523 oz", "14M lb", "265,000 – 290,000 oz", "≥ 375,000 oz"))
    print("production_publish: %s" % ("ok" if not bad else "%d FAILURES" % bad))
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
            print("[production_publish] dry run: no version given and none active")
            return 2
        rows, st = compute(load_items(conn, v))
        st.update(version=v)
        print("[production_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[production_publish] no active production version; nothing to publish")
        return 0
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[production_publish] FAILED publishing %s: %s: %s" % (version, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
