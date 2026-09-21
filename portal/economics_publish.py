"""Publish the Economic Studies reader into the table /economic-studies reads (ECON_PUBLISH_V1,
2026-09-21).

The facts store holds what ECON_V1 (portal/extractors/economics.py) found in every approved release.
The page does not read the facts store directly: it reads economic_studies. This module turns the
ACTIVE economics version into that table. Unlike the four pages before it, it replaces nothing -- the
URL showed a plain list of tagged releases -- so there is no legacy table and no legacy backfill.

One row per scenario (Justin, 2026-09-18), pre-tax and after-tax as columns of the same row, a named
case a row of its own, a percentage sweep not a row at all.

What goes on the page (Justin, 2026-09-18: tag plus detection):
  1. every approved release in which the reader found economics, tagged Economic Studies or not;
  2. a MARKER row (scenario NULL, n_rows 0) for every tagged release that states none -- a filing
     notice, a webinar, "we have begun a PEA" -- so the page follows the tag and is one table, as
     /resources does since RES_PAGE_V2;
  3. a study restated from an earlier release is shown and marked context = 'background', never
     dropped, so a reader can see what the company is still citing;
  4. a study the release plainly credits to ANOTHER company is left out. Peloton (PMC.CN) relaying
     Surge's webinar quotes Surge's Nevada North PEA; published under PMC that is a nine-billion-
     dollar project credited to the wrong issuer. It is not moved to Surge either: Surge's own release
     already carries that study, and a moved copy would show it twice. The test is by company name
     (tickers.json), because Peloton's release names no exchange symbol at all -- and moving studies
     by symbol filed a Westhaven recap under Dundee, whose symbol was the only one it printed. A
     tagged release whose study is left out keeps its marker row.

compute() is a pure function of (items, company names) so the accuracy gate can score what a candidate
version would publish without writing anything. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.economics_publish
  - an active economics version exists -> publish it
  - none yet                            -> do nothing (there is no legacy reader to fall back to)

Self-tests: python3 -m portal.economics_publish --selftest   (in-memory; touches nothing live)
Dry run:    python3 -m portal.economics_publish --dry-run [--version X.Y.Z]   (reads only)
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time

EXTRACTOR = "economics"
TAG = "Economic Studies"
DB = "/opt/mnt/app/portal/portal.db"
TICKERS = "/opt/mnt/app/tickers.json"

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS economic_studies (
    es_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    slug              TEXT,
    project           TEXT,
    study_type        TEXT,
    context           TEXT,
    scenario          TEXT,
    basis             TEXT,
    currency          TEXT,
    discount_pct      REAL,
    npv_pre_tax       REAL,
    npv_after_tax     REAL,
    irr_pre_tax_pct   REAL,
    irr_after_tax_pct REAL,
    payback_years     REAL,
    initial_capex     REAL,
    capex_sensitivity REAL,
    opex              REAL,
    opex_unit         TEXT,
    aisc              REAL,
    aisc_unit         TEXT,
    mine_life_years   REAL,
    throughput_tpd    REAL,
    annual_production REAL,
    production_unit   TEXT,
    n_rows            INTEGER NOT NULL DEFAULT 1,
    tag_confirmed     INTEGER NOT NULL DEFAULT 0,
    raw_headline      TEXT,
    published_at      TEXT,
    other_owner       TEXT,
    extractor_version TEXT
);
"""
INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_econ_pub    ON economic_studies(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_econ_ticker ON economic_studies(ticker);
CREATE INDEX IF NOT EXISTS idx_econ_event  ON economic_studies(event_id);
"""

_COLS = ("event_id", "ordinal", "ticker", "slug", "project", "study_type", "context",
         "scenario", "basis", "currency", "discount_pct", "npv_pre_tax", "npv_after_tax",
         "irr_pre_tax_pct", "irr_after_tax_pct", "payback_years", "initial_capex", "capex_sensitivity",
         "opex", "opex_unit", "aisc", "aisc_unit", "mine_life_years", "throughput_tpd",
         "annual_production", "production_unit", "n_rows", "tag_confirmed", "raw_headline",
         "published_at", "other_owner")
_SCEN_FIELDS = ("scenario", "basis", "currency", "discount_pct", "npv_pre_tax", "npv_after_tax",
                "irr_pre_tax_pct", "irr_after_tax_pct", "payback_years", "initial_capex",
                "capex_sensitivity", "opex", "opex_unit", "aisc", "aisc_unit", "mine_life_years",
                "throughput_tpd", "annual_production", "production_unit")


# ------------------------------------------------------------------ formatting (the page uses these)
_CUR = {"CAD": "C$", "USD": "US$", "AUD": "A$"}


def fmt_money(v, cur=None):
    """9.214e9, 'USD' -> 'US$9.21B'; 532e6, 'CAD' -> 'C$532M'."""
    if v is None:
        return None
    sym = _CUR.get(cur or "", "$")
    a = abs(v)
    if a >= 1e9:
        s = ("%.2f" % (a / 1e9)).rstrip("0").rstrip(".") + "B"
    elif a >= 1e6:
        s = ("%.1f" % (a / 1e6)).rstrip("0").rstrip(".") + "M"
    elif a >= 1e3:
        s = "{:,.0f}".format(a)
    else:
        s = ("%.2f" % a).rstrip("0").rstrip(".")
    return ("-" if v < 0 else "") + sym + s


def fmt_pct(v):
    return None if v is None else ("%.1f" % v).rstrip("0").rstrip(".") + "%"


def fmt_years(v):
    return None if v is None else ("%.1f" % v).rstrip("0").rstrip(".") + " yr"


def fmt_unit_cost(v, unit, cur=None):
    if v is None:
        return None
    s = _CUR.get(cur or "", "$") + "{:,.0f}".format(v) if v >= 100 else _CUR.get(cur or "", "$") + "%g" % v
    return s + ("/" + unit if unit else "")


# ------------------------------------------------------------------ attribution
def company_names(path=TICKERS):
    """Ticker -> company name, from the watchlist MNT already uses for its pages. A previous ticker
    resolves to the same name, as it does in portal/app.py. Unreadable means empty: then nothing is
    ever left out, which is the safe direction."""
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for r in data:
        if not isinstance(r, dict) or not r.get("ticker"):
            continue
        nm = r.get("name") or ""
        out[r["ticker"]] = nm
        for prev in (r.get("previous_tickers") or []):
            if isinstance(prev, dict) and prev.get("ticker"):
                out.setdefault(prev["ticker"], nm)
    return out


def someone_elses(parsed, issuer, names):
    """True when the release credits the study, by name, to a company that is not the issuer."""
    from portal.extractors import econ_core as C
    owner = parsed.get("owner_name")
    return bool(owner) and not C.same_company(owner, names.get(issuer or "", ""))


# ------------------------------------------------------------------ compute (pure)
def _marker(ev, p, other_owner=None):
    """A tagged release with no row of its own. When the figures it states are another company's
    study, the marker says whose, and carries none of that study's project or type: under the
    issuer's ticker they would read as the issuer's own."""
    row = {c: None for c in _COLS}
    row.update(event_id=ev["event_id"], ordinal=0, ticker=ev.get("ticker"), slug=ev.get("slug"),
               project=None if other_owner else p.get("project"),
               study_type=None if other_owner else p.get("study_type"), n_rows=0, tag_confirmed=1,
               raw_headline=(ev.get("raw_headline") or "")[:500], published_at=ev.get("published_at"),
               other_owner=(other_owner or None) and other_owner[:120])
    return row


def compute(items, names):
    """items: iterable of (event, parsed); event = {event_id, ticker, published_at, raw_headline,
    slug, tagged}; parsed = economics.parse_records() output; names = company_names().
    Returns (rows, stats)."""
    items = sorted(items, key=lambda x: ((x[0].get("published_at") or ""), x[0]["event_id"]))
    rows = []
    st = {"releases": 0, "published": 0, "rows": 0, "markers": 0, "tagged_published": 0,
          "untagged_published": 0, "background_rows": 0, "someone_elses": 0}
    for ev, p in items:
        st["releases"] += 1
        scen = [s for s in (p.get("scenarios") or []) if s.get("scenario")]
        tagged = bool(ev.get("tagged"))
        skip = bool(scen) and someone_elses(p, ev.get("ticker"), names)
        if not scen or skip:
            if skip:
                st["someone_elses"] += 1
            if tagged:
                rows.append(_marker(ev, p, p.get("owner_name") if skip else None))
                st["markers"] += 1
            continue
        st["published"] += 1
        st["tagged_published" if tagged else "untagged_published"] += 1
        for i, s in enumerate(scen):
            row = {c: None for c in _COLS}
            row.update({k: s.get(k) for k in _SCEN_FIELDS})
            row.update(event_id=ev["event_id"], ordinal=i, ticker=ev.get("ticker"),
                       slug=ev.get("slug"), project=p.get("project"), study_type=p.get("study_type"),
                       context=p.get("context"), n_rows=len(scen), tag_confirmed=1 if tagged else 0,
                       raw_headline=(ev.get("raw_headline") or "")[:500],
                       published_at=ev.get("published_at"))
            rows.append(row)
            st["rows"] += 1
            st["background_rows"] += 1 if p.get("context") == "background" else 0
    return rows, st


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
    """(event, parsed) for every approved release this version found economics in, and every approved
    release carrying the tag today (those that state none become marker rows)."""
    from portal.extractors import economics as X
    found = {r[0] for r in conn.execute(
        "SELECT DISTINCT r.event_id FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
        "WHERE r.extractor=? AND r.version=? AND f.field='is_economic_study' AND f.value_num=1",
        (EXTRACTOR, version))}
    evs = {}
    for eid, tk, pub, hl, slug, cats in conn.execute(
            "SELECT e.event_id, e.ticker, COALESCE(e.published_at, e.classified_at), e.raw_headline, e.slug, "
            "e.categories FROM events e JOIN fx_runs u ON u.event_id=e.event_id AND u.extractor=? "
            "AND u.version=? WHERE e.review_status='auto_approved'", (EXTRACTOR, version)):
        tagged = ("|" + (cats or "") + "|").find("|" + TAG + "|") >= 0
        if eid in found or tagged:
            evs[eid] = {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl,
                        "slug": slug, "tagged": tagged}
    facts = {}
    if found:
        for eid, ordinal, field_, seq, num, text in conn.execute(
                "SELECT r.event_id, r.ordinal, f.field, f.seq, f.value_num, f.value_text "
                "FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
                "WHERE r.extractor=? AND r.version=? AND r.event_id IN "
                "(SELECT r2.event_id FROM fx_records r2 JOIN fx_facts f2 ON f2.record_id=r2.record_id "
                " WHERE r2.extractor=? AND r2.version=? AND f2.field='is_economic_study' AND f2.value_num=1)",
                (EXTRACTOR, version, EXTRACTOR, version)):
            facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    return [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]


def current_event_ids(conn):
    if not _has_table(conn, "economic_studies"):
        return set()
    return {r[0] for r in conn.execute("SELECT DISTINCT event_id FROM economic_studies")}


def _ensure_schema(conn):
    conn.executescript(TABLE_SQL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(economic_studies)")}
    for line in TABLE_SQL.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)", line)
        if m and m.group(1) not in have and m.group(1) != "es_id":
            conn.execute("ALTER TABLE economic_studies ADD COLUMN %s %s" % (m.group(1), m.group(2)))
    conn.executescript(INDEX_SQL)


def publish(conn, version, log=print, names=None):
    """Rebuild economic_studies from `version` in one transaction. Returns stats."""
    if not re.match(r"^[0-9]+[.][0-9]+[.][0-9]+$", version or ""):
        raise ValueError("bad version %r" % (version,))
    t0 = time.time()
    rows, st = compute(load_items(conn, version), company_names() if names is None else names)
    _ensure_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM economic_studies")
        conn.executemany(
            "INSERT INTO economic_studies(" + ", ".join(_COLS) + ", extractor_version) VALUES ("
            + ", ".join(":" + c for c in _COLS) + ", '" + version + "')", rows)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[economics_publish] " + json.dumps(st))
    return st


# ------------------------------------------------------------------ self-tests
def _selftest():
    sys.path.insert(0, "/opt/mnt/app")
    from portal import facts as F
    from portal.extractors import economics as X
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
        # an announced study, tagged
        ("e1", "SLI.V", "2026-01-02", "Smackover Lithium Announces PEA for the Smackover Project",
         "The PEA uses a discount rate of 8%. NPV (After-Tax) | $ million | 4,992 | IRR (After-Tax) | % | 24.0%",
         "Economic Studies"),
        # someone else's study, relayed the way Peloton wrote it: no exchange symbol anywhere
        ("e2", "PMC.CN", "2026-01-03", "Surge Battery Metals Presents Their Preliminary Economic Assessment",
         "In June, 2025, Surge Battery Metals (Surge) released a Preliminary Economic Assessment (PEA) on their "
         "Nevada North Lithium Project. After-tax NPV8%: US$9.21 Billion. After-tax IRR: 22.8%.", "Corporate Updates"),
        # tagged, states nothing
        ("e3", "ABC.V", "2026-01-04", "ABC Engages Consultant to Begin PEA", "Work will begin next month.",
         "Economic Studies"),
        # untagged, states nothing -- must not appear at all
        ("e4", "XYZ.V", "2026-01-05", "XYZ Drills 12 m of 3 g/t Gold", "Drilling continues.", "Drill Results"),
        # a partner's symbol printed and the issuer's not: still the issuer's own study (the Westhaven /
        # Dundee recap that moving-by-symbol got wrong)
        ("e5", "WHN.V", "2026-01-06", "Westhaven Gold and Dundee Corporation Announce Closing",
         "Dundee Corporation (TSX: DC.A) has invested. Westhaven's Shovelnose PEA shows a C$454 million "
         "after-tax net present value and 43.2% IRR.", "Corporate Updates"),
        ("e6", "NILI.V", "2026-01-01", "Surge Webinar", "Surge will hold a webinar.", "Corporate Updates"),
    ]
    for eid, tk, pub, hl, body, cats in evs:
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?, 'auto_approved')",
                     (eid, tk, pub, None, hl, body, eid + "-slug", cats))
    events = [dict(r) for r in conn.execute("SELECT * FROM events")]
    F.run_batch(conn, spec, events)
    items = load_items(conn, "9.9.9")
    names = {"SLI.V": "Smackover Lithium Ltd.", "PMC.CN": "Peloton Minerals Corporation",
             "WHN.V": "Westhaven Gold Corp.", "NILI.V": "Surge Battery Metals Inc."}
    rows, st = compute(items, names)
    by = {}
    for r in rows:
        by.setdefault(r["event_id"], []).append(r)
    eq("announced study published", [(r["ticker"], r["npv_after_tax"]) for r in by.get("e1", [])],
         [("SLI.V", 4992e6)])
    eq("announced study is tagged", by["e1"][0]["tag_confirmed"], 1)
    eq("someone else's study left out", by.get("e2"), None)
    eq("tagged, no figures -> one marker", [(r["scenario"], r["n_rows"]) for r in by.get("e3", [])], [(None, 0)])
    eq("untagged, no figures -> nothing", by.get("e4"), None)
    eq("a partner's symbol does not take the issuer's study", [(r["ticker"], r["npv_after_tax"]) for r in by.get("e5", [])],
       [("WHN.V", 454e6)])
    eq("stats", (st["published"], st["markers"], st["someone_elses"]), (2, 1, 1))
    publish(conn, "9.9.9", log=lambda *_: None, names=names)
    eq("table rows", conn.execute("SELECT COUNT(*) FROM economic_studies").fetchone()[0], 3)
    eq("version stamped", conn.execute("SELECT DISTINCT extractor_version FROM economic_studies").fetchone()[0],
       "9.9.9")
    publish(conn, "9.9.9", log=lambda *_: None, names=names)
    eq("publishing twice is idempotent", conn.execute("SELECT COUNT(*) FROM economic_studies").fetchone()[0], 3)
    eq("money", (fmt_money(9.214e9, "USD"), fmt_money(532e6, "CAD"), fmt_money(24e6, None)),
       ("US$9.21B", "C$532M", "$24M"))
    eq("pct and years", (fmt_pct(22.8), fmt_pct(48.0), fmt_years(3.25)), ("22.8%", "48%", "3.2 yr"))
    print("economics_publish: %s" % ("ok" if not bad else "%d FAILURES" % bad))
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
            print("[economics_publish] dry run: no version given and none active")
            return 2
        rows, st = compute(load_items(conn, v), company_names())
        st.update(version=v, current_events=len(current_event_ids(conn)))
        print("[economics_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[economics_publish] no active economics version; nothing to publish")
        return 0
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[economics_publish] FAILED publishing %s: %s: %s" % (version, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
