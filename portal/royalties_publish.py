"""Publish the Royalties & Streams reader into the table /royalties-streams reads (ROY_PUBLISH_V1, 2026-09-21).

The facts store holds what ROY_V1 (portal/extractors/royalties.py) found in every approved release. The page
reads royalty_deals, which this module rebuilds from the ACTIVE royalties version. It replaces nothing: the
URL showed a plain list of tagged releases, so there is no legacy table and no legacy backfill.

One row per royalty or stream interest a release reports as news (Justin, 2026-09-21).

What goes on the page:
  1. every approved release in which the reader found a row, tagged Royalties & Streams or not (the tag
     misses real deals -- DeepRock's net profits stream -- and leaks music royalties, AGM results and index
     inclusions);
  2. a MARKER row (type NULL) for every tagged release that reports none, so 'show all' follows the tag;
  3. ONE DEAL, SEVERAL RELEASES: the announcement and the closing, or the seller's and the buyer's release of
     the same stream, each keep their row (Justin, 2026-09-21), and share a deal_key. The newest release of a
     deal is its lead row (is_latest=1); the page shows lead rows by default with the number of releases and
     the date the deal was first reported. A deal is the same property and type within 400 days.

compute() is a pure function of the items so the accuracy gate can score what a candidate version would
publish without writing anything. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.royalties_publish
Self-tests: python3 -m portal.royalties_publish --selftest     (in-memory; touches nothing live)
Dry run:    python3 -m portal.royalties_publish --dry-run [--version X.Y.Z]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import date

EXTRACTOR = "royalties"
TAG = "Royalties & Streams"
DB = "/opt/mnt/app/portal/portal.db"

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS royalty_deals (
    rd_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    slug              TEXT,
    type              TEXT,
    rate_pct          REAL,
    metal             TEXT,
    property          TEXT,
    operator          TEXT,
    buyer             TEXT,
    seller            TEXT,
    price             REAL,
    currency          TEXT,
    price_note        TEXT,
    action            TEXT,
    status            TEXT,
    deal_key          TEXT,
    deal_releases     INTEGER NOT NULL DEFAULT 1,
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
CREATE INDEX IF NOT EXISTS idx_roy_pub    ON royalty_deals(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_roy_ticker ON royalty_deals(ticker);
CREATE INDEX IF NOT EXISTS idx_roy_event  ON royalty_deals(event_id);
CREATE INDEX IF NOT EXISTS idx_roy_deal   ON royalty_deals(deal_key);
"""

_COLS = ("event_id", "ordinal", "ticker", "slug", "type", "rate_pct", "metal", "property", "operator", "buyer",
         "seller", "price", "currency", "price_note", "action", "status", "deal_key", "deal_releases",
         "first_reported", "is_latest", "n_rows", "tag_confirmed", "raw_headline", "published_at")
_ROW_FIELDS = ("type", "rate_pct", "metal", "property", "operator", "buyer", "seller", "price", "currency",
               "price_note", "action", "status")

DEAL_DAYS = 400
_GENERIC = {"the", "project", "mine", "property", "deposit", "concessions", "concession", "claims", "gold", "silver",
            "copper", "tin", "lake", "mineral", "district", "de", "del", "la", "los", "las", "operations", "complex"}


# ------------------------------------------------------------------ formatting (the page uses these)
TYPE_LABELS = {"NSR": "NSR", "GRR": "GRR", "NPI": "NPI", "stream": "Stream", "other": "Royalty"}
ACTION_LABELS = {"new": "New / granted", "transfer": "Bought / sold", "buyback": "Buyback / buy-down",
                 "amendment": "Amended"}


def fmt_money(v, cur=None):
    if v is None:
        return None
    sym = {"USD": "US$", "CAD": "C$", "AUD": "A$"}.get(cur or "", "$")
    a = abs(v)
    if a >= 1e9:
        s = ("%.2f" % (a / 1e9)).rstrip("0").rstrip(".") + "B"
    elif a >= 1e6:
        s = ("%.2f" % (a / 1e6)).rstrip("0").rstrip(".") + "M"
    else:
        s = "{:,.0f}".format(a)
    return sym + s


def fmt_rate(v):
    if v is None:
        return None
    return ("%.3f" % v).rstrip("0").rstrip(".") + "%"


# ------------------------------------------------------------------ compute (pure)
def _key_words(s):
    s = unicodedata.normalize("NFKD", s or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]+", s) if w not in _GENERIC]


def deal_key(r):
    w = _key_words(r.get("property"))
    if not w:
        return None
    return "%s:%s" % (r.get("type") or "?", w[0])


def _days(a, b):
    try:
        return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)
    except (TypeError, ValueError):
        return 10 ** 6


def _marker(ev):
    row = {c: None for c in _COLS}
    row.update(event_id=ev["event_id"], ordinal=0, ticker=ev.get("ticker"), slug=ev.get("slug"), n_rows=0,
               deal_releases=1, is_latest=1, tag_confirmed=1, raw_headline=(ev.get("raw_headline") or "")[:500],
               published_at=ev.get("published_at"))
    return row


def compute(items):
    """items: iterable of (event, parsed); event = {event_id, ticker, published_at, raw_headline, slug, tagged};
    parsed = royalties.parse_records() output. Returns (rows, stats)."""
    items = sorted(items, key=lambda x: ((x[0].get("published_at") or ""), x[0]["event_id"]))
    out = []
    st = {"releases": 0, "published": 0, "rows": 0, "markers": 0, "tagged_published": 0, "untagged_published": 0,
          "new": 0, "transfer": 0, "buyback": 0, "amendment": 0, "deals": 0, "repeat_rows": 0}
    for ev, p in items:
        st["releases"] += 1
        rows = [dict(r) for r in (p.get("rows") or []) if r.get("type")]
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
            row.update(event_id=ev["event_id"], ordinal=i, ticker=ev.get("ticker"), slug=ev.get("slug"),
                       n_rows=len(rows), tag_confirmed=1 if tagged else 0, deal_key=deal_key(r),
                       deal_releases=1, is_latest=1, first_reported=(ev.get("published_at") or "")[:10] or None,
                       raw_headline=(ev.get("raw_headline") or "")[:500], published_at=ev.get("published_at"))
            out.append(row)
            st["rows"] += 1
            st[r.get("action") or "new"] = st.get(r.get("action") or "new", 0) + 1
    # one deal, several releases: chain rows with the same key reported within DEAL_DAYS of the previous one
    chains = {}
    for row in out:
        k = row["deal_key"]
        if not k or row["type"] is None:
            continue
        ch = chains.setdefault(k, [])
        if ch and ch[-1] and _days(ch[-1][-1]["published_at"], row["published_at"]) <= DEAL_DAYS \
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
                r.update(deal_key=gid, deal_releases=len(g), first_reported=first, is_latest=1 if j == len(g) - 1 else 0)
                st["repeat_rows"] += 0 if j == len(g) - 1 else 1
    st["deals"] = n + sum(1 for r in out if r["type"] and not r["deal_key"])
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
    from portal.extractors import royalties as X
    found = {r[0] for r in conn.execute(
        "SELECT DISTINCT r.event_id FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
        "WHERE r.extractor=? AND r.version=? AND f.field='is_royalty' AND f.value_num=1",
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
                " WHERE r2.extractor=? AND r2.version=? AND f2.field='is_royalty' AND f2.value_num=1)",
                (EXTRACTOR, version, EXTRACTOR, version)):
            facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    return [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]


def _ensure_schema(conn):
    conn.executescript(TABLE_SQL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(royalty_deals)")}
    for line in TABLE_SQL.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)", line)
        if m and m.group(1) not in have and m.group(1) != "rd_id":
            conn.execute("ALTER TABLE royalty_deals ADD COLUMN %s %s" % (m.group(1), m.group(2)))
    conn.executescript(INDEX_SQL)


def publish(conn, version, log=print):
    if not re.match(r"^[0-9]+[.][0-9]+[.][0-9]+$", version or ""):
        raise ValueError("bad version %r" % (version,))
    t0 = time.time()
    rows, st = compute(load_items(conn, version))
    _ensure_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM royalty_deals")
        conn.executemany(
            "INSERT INTO royalty_deals(" + ", ".join(_COLS) + ", extractor_version) VALUES ("
            + ", ".join(":" + c for c in _COLS) + ", '" + version + "')", rows)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[royalties_publish] " + json.dumps(st))
    return st


# ------------------------------------------------------------------ self-tests
def _selftest():
    sys.path.insert(0, "/opt/mnt/app")
    from portal import facts as F
    from portal.extractors import royalties as X
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
    sale = ("Hayasa Metals Inc. (TSXV: HAY) (\"Hayasa\" or the \"Company\") is pleased to announce the sale of a 1.25% "
            "Net Smelter Return (\"NSR\") royalty covering all minerals produced from the Urasar gold-copper project "
            "in northern Armenia to Franco-Nevada Corporation (\"Franco-Nevada\") and EMX Royalty Corporation (\"EMX\"), "
            "for US$1,000,000 cash.")
    close = ("Hayasa Metals Inc. (TSXV: HAY) (\"Hayasa\" or the \"Company\") is pleased to announce that it has completed "
             "its previously announced sale of a 1.25% Net Smelter Return (\"NSR\") royalty covering all minerals produced "
             "from the Urasar gold-copper project in northern Armenia to Franco-Nevada Corporation (\"FNV\") and EMX "
             "Royalty Corporation (\"EMX\"). The NSR was sold for an aggregate cash purchase price of US$1,000,000.")
    evs = [
        ("e1", "HAY.V", "2025-01-07", "Hayasa Metals Announces Sale of 1.25% NSR over Urasar Mineral District, Armenia for US$1M",
         sale, "Royalties & Streams"),
        ("e2", "HAY.V", "2025-01-22", "Hayasa Metals Closes Joint Royalty Agreement with EMX and Franco-Nevada", close,
         "Royalties & Streams"),
        # tagged, no deal -> one marker
        ("e3", "VMET.TO", "2026-02-09", "Versamet Royalties Closes C$142 Million Bought Deal Financing",
         "Versamet Royalties Corporation (\"Versamet\" or the \"Company\") is pleased to announce that it has closed its "
         "bought deal public offering.", "Financings|Royalties & Streams"),
        # untagged, no deal -> absent
        ("e4", "XYZ.V", "2026-01-05", "XYZ Drills 12 m of 3 g/t Gold",
         "The property carries a 2% NSR held by a prospector.", "Drill Results"),
    ]
    for eid, tk, pub, hl, body, cats in evs:
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?, 'auto_approved')",
                     (eid, tk, pub, None, hl, body, eid + "-slug", cats))
    F.run_batch(conn, spec, [dict(r) for r in conn.execute("SELECT * FROM events")])
    rows, st = compute(load_items(conn, "9.9.9"))
    by = {}
    for r in rows:
        by.setdefault(r["event_id"], []).append(r)
    eq("sale row", [(r["type"], r["rate_pct"], r["property"], r["seller"], r["action"], r["price"]) for r in by["e1"]],
       [("NSR", 1.25, "Urasar", "Hayasa Metals", "new", 1000000.0)])
    eq("closing row", [(r["status"], r["is_latest"], r["deal_releases"], r["first_reported"]) for r in by["e2"]],
       [("closed", 1, 2, "2025-01-07")])
    eq("announcement is not the lead row", [r["is_latest"] for r in by["e1"]], [0])
    eq("same deal", by["e1"][0]["deal_key"] == by["e2"][0]["deal_key"], True)
    eq("marker", [(r["type"], r["n_rows"]) for r in by["e3"]], [(None, 0)])
    eq("passing mention -> absent", by.get("e4"), None)
    publish(conn, "9.9.9", log=lambda *_: None)
    publish(conn, "9.9.9", log=lambda *_: None)
    eq("idempotent", conn.execute("SELECT COUNT(*) FROM royalty_deals").fetchone()[0], len(rows))
    eq("formats", (fmt_money(55e6, "USD"), fmt_money(1.05e9, "USD"), fmt_money(6000, "CAD"), fmt_rate(1.25), fmt_rate(3.0)),
       ("US$55M", "US$1.05B", "C$6,000", "1.25%", "3%"))
    print("royalties_publish: %s" % ("ok" if not bad else "%d FAILURES" % bad))
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
            print("[royalties_publish] dry run: no version given and none active")
            return 2
        rows, st = compute(load_items(conn, v))
        st.update(version=v)
        print("[royalties_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[royalties_publish] no active royalties version; nothing to publish")
        return 0
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[royalties_publish] FAILED publishing %s: %s: %s" % (version, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
