"""Publish the Technical Reports reader into the table /technical-reports reads (TECH_PUBLISH_V1, 2026-09-22).

The facts store holds what TECH_V1 (portal/extractors/technical.py) found in every approved release and SEDAR+
document. The page reads technical_reports, which this module rebuilds from the ACTIVE technical version.

One row per NI 43-101 technical report an item reports (Justin, 2026-09-22): filed, commissioned or withdrawn.

What goes on the page:
  1. every approved item in which the reader found a report, tagged Technical Reports (NI 43-101) or not;
  2. a MARKER row (report_type NULL) for every tagged item that reports none, so 'show all' follows the tag;
  3. ONE REPORT, SEVERAL ITEMS: commissioned -> filed (-> withdrawn). Rows of the same company, project and report
     type (an amended report chains on its own) within 540 days share a report_key, unless both state different
     effective dates. The results release that said "a technical report will be filed within 45 days", the news
     release announcing the filing and the consent of each QP are one report. The newest item is the lead row
     (is_latest=1); empty fields on the lead are filled from the other items of the same report, newest first --
     which is how the headline numbers of the results release repeat on the filed row (Justin: "Repeat").
  4. A filed row with no stated filing date takes the item's date.

compute() is a pure function of the items so the accuracy gate can score what a candidate version would publish
without writing anything. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.technical_publish
Self-tests: python3 -m portal.technical_publish --selftest     (in-memory; touches nothing live)
Dry run:    python3 -m portal.technical_publish --dry-run [--version X.Y.Z]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import date

EXTRACTOR = "technical"
TAG = "Technical Reports (NI 43-101)"
DB = "/opt/mnt/app/portal/portal.db"

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS technical_reports (
    tr_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    slug              TEXT,
    report_type       TEXT,
    project           TEXT,
    status            TEXT,
    effective_date    TEXT,
    report_date       TEXT,
    filing_date       TEXT,
    expected          TEXT,
    author_firm       TEXT,
    qps               TEXT,
    title             TEXT,
    amended           INTEGER NOT NULL DEFAULT 0,
    metal             TEXT,
    resource_json     TEXT,
    npv               REAL,
    npv_discount      REAL,
    irr               REAL,
    capex             REAL,
    currency          TEXT,
    after_tax         INTEGER,
    mine_life_years   REAL,
    payback_years     REAL,
    supports_release  TEXT,
    doc_kind          TEXT,
    filled_from       TEXT,
    report_key        TEXT,
    report_items      INTEGER NOT NULL DEFAULT 1,
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
CREATE INDEX IF NOT EXISTS idx_tech_pub    ON technical_reports(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_tech_ticker ON technical_reports(ticker);
CREATE INDEX IF NOT EXISTS idx_tech_event  ON technical_reports(event_id);
CREATE INDEX IF NOT EXISTS idx_tech_key    ON technical_reports(report_key);
"""

_ROW_FIELDS = ("report_type", "project", "status", "effective_date", "report_date", "filing_date", "expected",
               "author_firm", "qps", "title", "amended", "metal", "resource_json", "npv", "npv_discount", "irr", "capex",
               "currency", "after_tax", "mine_life_years", "payback_years", "supports_release", "doc_kind")
_COLS = ("event_id", "ordinal", "ticker", "slug") + _ROW_FIELDS + (
    "filled_from", "report_key", "report_items", "first_reported", "is_latest", "n_rows", "tag_confirmed", "raw_headline",
    "published_at")
# what the lead row may borrow from the other items of the same report
_FILLABLE = ("report_type", "effective_date", "report_date", "author_firm", "qps", "title", "metal", "resource_json", "npv",
             "npv_discount", "irr", "capex", "currency", "after_tax", "mine_life_years", "payback_years")
REPORT_DAYS = 540
_GENERIC = {"the", "project", "projects", "property", "properties", "mine", "mines", "deposit", "deposits", "gold", "silver",
            "copper", "lithium", "uranium", "nickel", "zinc", "lead", "potash", "phosphate", "molybdenum", "graphite",
            "critical", "minerals", "mineral", "metals", "polymetallic", "claims", "de", "del", "la", "and", "au", "cu"}

TYPE_LABELS = {"property": "Property", "resource": "Resource", "PEA": "PEA", "PFS": "PFS", "FS": "FS", "other": "Other"}
STATUS_LABELS = {"filed": "Filed", "commissioned": "Commissioned", "withdrawn": "Withdrawn"}


def fmt_money(v, cur=None):
    if v is None:
        return None
    sym = {"USD": "US$", "CAD": "C$", "AUD": "A$"}.get(cur or "", "$")
    a = abs(v)
    if a >= 1e9:
        s = ("%.2f" % (a / 1e9)).rstrip("0").rstrip(".") + "B"
    elif a >= 1e6:
        s = ("%.1f" % (a / 1e6)).rstrip("0").rstrip(".") + "M"
    else:
        s = "{:,.0f}".format(a)
    return ("-" if v < 0 else "") + sym + s


def _key_words(s):
    s = unicodedata.normalize("NFKD", s or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]+", s) if w not in _GENERIC]


def report_key(r, ticker):
    w = _key_words(r.get("project"))
    if not w:
        return None
    return "%s:%s:%s%s" % (ticker or "?", " ".join(w[:3]), r.get("report_type") or "?", ":A" if r.get("amended") else "")


def _days(a, b):
    try:
        return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)
    except (TypeError, ValueError):
        return 10 ** 6


def _marker(ev):
    row = {c: None for c in _COLS}
    row.update(event_id=ev["event_id"], ordinal=0, ticker=ev.get("ticker"), slug=ev.get("slug"), n_rows=0, amended=0,
               report_items=1, is_latest=1, tag_confirmed=1, raw_headline=(ev.get("raw_headline") or "")[:500],
               published_at=ev.get("published_at"))
    return row


def _joinable(group, row):
    last = group[-1]
    if last["event_id"] == row["event_id"]:
        return False
    if _days(last["published_at"], row["published_at"]) > REPORT_DAYS:
        return False
    effs = {g["effective_date"] for g in group if g["effective_date"] and g["status"] != "commissioned"}
    if row["effective_date"] and effs and row["effective_date"] not in effs:
        return False
    return True


def compute(items):
    """items: iterable of (event, parsed); event = {event_id, ticker, published_at, raw_headline, slug, tagged};
    parsed = technical.parse_records() output. Returns (rows, stats)."""
    items = sorted(items, key=lambda x: ((x[0].get("published_at") or ""), x[0]["event_id"]))
    out = []
    st = {"items": 0, "published": 0, "rows": 0, "markers": 0, "tagged_published": 0, "untagged_published": 0,
          "filed": 0, "commissioned": 0, "withdrawn": 0, "sedar_docs": 0, "reports": 0, "repeat_rows": 0, "filled": 0}
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
            if isinstance(r.get("qps"), list):
                row["qps"] = "; ".join(r["qps"]) or None
            if r.get("resource") and not row.get("resource_json"):
                row["resource_json"] = json.dumps(r["resource"], separators=(",", ":"))
            row["amended"] = 1 if r.get("amended") else 0
            if row["after_tax"] is not None:
                row["after_tax"] = int(row["after_tax"])
            if row["status"] == "filed" and not row["filing_date"]:
                row["filing_date"] = (ev.get("published_at") or "")[:10] or None
            row.update(event_id=ev["event_id"], ordinal=i, ticker=ev.get("ticker"), slug=ev.get("slug"), n_rows=len(rows),
                       tag_confirmed=1 if tagged else 0, report_key=report_key(row, ev.get("ticker")), report_items=1,
                       is_latest=1, first_reported=(ev.get("published_at") or "")[:10] or None,
                       raw_headline=(ev.get("raw_headline") or "")[:500], published_at=ev.get("published_at"))
            out.append(row)
            st["rows"] += 1
            st[row["status"]] = st.get(row["status"], 0) + 1
            st["sedar_docs"] += 1 if row.get("doc_kind") in ("consent", "cover") else 0
    # one report, several items; an untyped row (a consent that does not say) joins the typed report of its project
    chains = {}
    for row in out:
        k = row["report_key"]
        if not k or row["status"] is None:
            continue
        if k.split(":")[2] == "?":
            base = ":".join(k.split(":")[:2]) + ":"
            typed = [kk for kk in chains if kk.startswith(base) and kk.split(":")[2] != "?" and
                     _joinable(chains[kk][-1], row)]
            if typed:
                k = typed[-1]
                row["report_key"] = k
        ch = chains.setdefault(k, [])
        if ch and _joinable(ch[-1], row):
            ch[-1].append(row)
        else:
            ch.append([row])
    n = 0
    for k, groups in chains.items():
        for g in groups:
            n += 1
            gid = "%s#%d" % (k, n)
            first = min((r["published_at"] or "")[:10] for r in g) or None
            filed = [r for r in g if r["status"] == "filed"]
            for j, r in enumerate(g):
                r.update(report_key=gid, report_items=len(g), first_reported=first, is_latest=1 if j == len(g) - 1 else 0)
                st["repeat_rows"] += 0 if j == len(g) - 1 else 1
            lead = g[-1]
            if lead["status"] == "commissioned" and filed:
                pass  # a later "will be filed" restatement never outranks a filing: impossible by order, kept for clarity
            src = []
            for other in reversed(g[:-1]):
                for f in _FILLABLE:
                    if lead.get(f) in (None, "") and other.get(f) not in (None, ""):
                        lead[f] = other[f]
                        src.append(other["event_id"][:12])
                        st["filled"] += 1
            lead["filled_from"] = ",".join(dict.fromkeys(src)) or None
    st["reports"] = n + sum(1 for r in out if r["status"] and not r["report_key"])
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
    from portal.extractors import technical as X
    found = {r[0] for r in conn.execute(
        "SELECT DISTINCT r.event_id FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
        "WHERE r.extractor=? AND r.version=? AND f.field='is_report' AND f.value_num=1",
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
                " WHERE r2.extractor=? AND r2.version=? AND f2.field='is_report' AND f2.value_num=1)",
                (EXTRACTOR, version, EXTRACTOR, version)):
            facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    items = []
    for e in evs:
        p = X.parse_records(facts.get(e, {}))
        for r in p["rows"]:
            r["resource_json"] = json.dumps(r.pop("resource"), separators=(",", ":")) if r.get("resource") else None
        items.append((evs[e], p))
    return items


def _ensure_schema(conn):
    conn.executescript(TABLE_SQL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(technical_reports)")}
    for line in TABLE_SQL.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)", line)
        if m and m.group(1) not in have and m.group(1) != "tr_id":
            conn.execute("ALTER TABLE technical_reports ADD COLUMN %s %s" % (m.group(1), m.group(2)))
    conn.executescript(INDEX_SQL)


def publish(conn, version, log=print):
    if not re.match(r"^[0-9]+[.][0-9]+[.][0-9]+$", version or ""):
        raise ValueError("bad version %r" % (version,))
    t0 = time.time()
    rows, st = compute(load_items(conn, version))
    _ensure_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM technical_reports")
        conn.executemany(
            "INSERT INTO technical_reports(" + ", ".join(_COLS) + ", extractor_version) VALUES ("
            + ", ".join(":" + c for c in _COLS) + ", '" + version + "')", rows)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[technical_publish] " + json.dumps(st))
    return st


# ------------------------------------------------------------------ self-tests
def _selftest():
    sys.path.insert(0, "/opt/mnt/app")
    from portal import facts as F
    from portal.extractors import technical as X
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
        ("e1", "ABC.V", "2026-03-02", "ABC Announces Maiden Mineral Resource Estimate at Alpha Gold Project",
         "Toronto, March 2, 2026 - ABC Gold Corp. (TSXV: ABC) is pleased to announce a maiden mineral resource estimate "
         "for its Alpha Gold Project. A technical report supporting the mineral resource estimate will be filed on "
         "SEDAR+ within 45 days." + fill, "Resource Estimates"),
        ("e2", "ABC.V", "2026-04-15", "ABC Files NI 43-101 Technical Report for Alpha Gold Project Mineral Resource Estimate",
         "Toronto, April 15, 2026 - ABC Gold Corp. (TSXV: ABC) announces that it has filed the technical report "
         "supporting the maiden mineral resource estimate for its Alpha Gold Project. The report, with an effective "
         "date of February 20, 2026, was prepared by P&E Mining Consultants Inc." + fill, TAG),
        ("e3", "ABC.V", "2026-05-01", "ABC Announces Annual General Meeting Results",
         "Toronto, May 1, 2026 - ABC Gold Corp. announces the results of its annual meeting." + fill,
         "Shareholder Meetings|" + TAG),
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
    eq("commissioned row", [(r["report_type"], r["project"], r["status"], r["is_latest"]) for r in by["e1"]],
       [("resource", "Alpha Gold Project", "commissioned", 0)])
    eq("filed row is the lead", [(r["status"], r["is_latest"], r["report_items"], r["first_reported"], r["filing_date"],
                                  r["effective_date"], r["author_firm"]) for r in by["e2"]],
       [("filed", 1, 2, "2026-03-02", "2026-04-15", "2026-02-20", "P&E Mining Consultants")])
    eq("same report", by["e1"][0]["report_key"] == by["e2"][0]["report_key"], True)
    eq("marker", [(r["report_type"], r["n_rows"]) for r in by["e3"]], [(None, 0)])
    eq("untagged, nothing -> absent", by.get("e4"), None)
    publish(conn, "9.9.9", log=lambda *_: None)
    publish(conn, "9.9.9", log=lambda *_: None)
    eq("idempotent", conn.execute("SELECT COUNT(*) FROM technical_reports").fetchone()[0], len(rows))
    eq("formats", (fmt_money(1.59e9, "CAD"), fmt_money(454e6, "USD")), ("C$1.59B", "US$454M"))
    print("technical_publish: %s" % ("ok" if not bad else "%d FAILURES" % bad))
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
            print("[technical_publish] dry run: no version given and none active")
            return 2
        rows, st = compute(load_items(conn, v))
        st.update(version=v)
        print("[technical_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[technical_publish] no active technical version; nothing to publish")
        return 0
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[technical_publish] FAILED publishing %s: %s: %s" % (version, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
