"""Publish the Property Options & Staking reader into the table /property-options reads (OPT_PUBLISH_V1, 2026-09-23).

The facts store holds what OPT_V1 (portal/extractors/options.py) found in every approved release. The page reads
land_deals, which this module rebuilds from the ACTIVE options version.

One row per land deal an item reports (Justin, 2026-09-23): options in and out (earn-ins included), staking, claim
purchases, property purchases and sales, at the deal's stage as of the item: proposed, signed, payment, completed,
amended or terminated.

What goes on the page:
  1. every approved item in which the reader found a deal, tagged Property Options & Staking or not;
  2. a MARKER row (deal_type NULL) for every tagged item that reports none, so 'show all' follows the tag;
  3. ONE DEAL, SEVERAL ITEMS: stages chain across releases (Justin: "one row per deal, stages chained"). Rows of the
     same company, property (portal/project_names.key: accents, "Project"/"Property", metal words ignored; PN_V1)
     and deal family (option in / option out / purchase / sale) within 1,825 days share a
     chain_key, unless they name different counterparties, the chain already ended (terminated; or a completed
     purchase), or a new LOI or agreement follows a signed deal after more than 180 days (a new deal on the same
     ground). A row with no property chains only through a named counterparty. Staking never chains: each staking
     is its own row. The newest item is the lead row (latest=1); its empty terms are filled from the chain, newest
     first.
  4. A row with no stated agreement date takes the item's date.

compute() is a pure function of the items so the accuracy gate can score what a candidate version would publish
without writing anything. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.options_publish
Self-tests: python3 -m portal.options_publish --selftest     (in-memory; touches nothing live)
Dry run:    python3 -m portal.options_publish --dry-run [--version X.Y.Z]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import date

from portal import project_names as PN

EXTRACTOR = "options"
TAG = "Property Options & Staking"
DB = "/opt/mnt/app/portal/portal.db"
TABLE = "land_deals"

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS land_deals (
    ld_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL DEFAULT 0,
    ticker            TEXT,
    slug              TEXT,
    deal_type         TEXT,
    stage             TEXT,
    property          TEXT,
    counterparty      TEXT,
    interest_pct      REAL,
    cash              REAL,
    currency          TEXT,
    shares            REAL,
    work              REAL,
    nsr               REAL,
    term              REAL,
    area              REAL,
    date              TEXT,
    metal             TEXT,
    jurisdiction      TEXT,
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
CREATE INDEX IF NOT EXISTS idx_land_deals_pub    ON land_deals(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_land_deals_ticker ON land_deals(ticker);
CREATE INDEX IF NOT EXISTS idx_land_deals_event  ON land_deals(event_id);
CREATE INDEX IF NOT EXISTS idx_land_deals_chain  ON land_deals(chain_key);
"""

_ROW_FIELDS = ("deal_type", "stage", "property", "counterparty", "interest_pct", "cash", "currency", "shares", "work",
               "nsr", "term", "area", "date", "metal", "jurisdiction")
_COLS = ("event_id", "ordinal", "ticker", "slug") + _ROW_FIELDS + (
    "filled_from", "chain_key", "chain_items", "first_reported", "stage_rank", "latest", "n_rows", "tag_confirmed",
    "raw_headline", "published_at")
_FILLABLE = ("property", "counterparty", "interest_pct", "cash", "currency", "shares", "work", "nsr", "term", "area",
             "metal", "jurisdiction")
CHAIN_DAYS = 1825
RENEW_DAYS = 180
STAGE_RANK = {"proposed": 1, "signed": 2, "payment": 3, "amended": 3, "completed": 4, "terminated": 5}
FAMILY = {"option_in": "in", "option_out": "out", "claim_purchase": "buy", "property_purchase": "buy",
          "property_sale": "sell", "staking": "stake"}
_CO_GENERIC = {"inc", "ltd", "corp", "corporation", "limited", "llc", "resources", "the", "mining", "minerals", "metals",
               "gold", "exploration", "explorations", "ventures", "b", "c", "and", "of", "co", "company"}

TYPE_LABELS = {"option_in": "Option in / earn-in", "option_out": "Option out", "staking": "Staking",
               "claim_purchase": "Claim purchase", "property_purchase": "Property purchase",
               "property_sale": "Property sale"}
STAGE_LABELS = {"proposed": "Proposed (LOI)", "signed": "Signed", "payment": "Payment made", "completed": "Completed",
                "amended": "Amended", "terminated": "Terminated"}


def _fold(s):
    s = unicodedata.normalize("NFKD", s or "").lower()
    return "".join(c for c in s if not unicodedata.combining(c))


def _key_words(s, generic):
    return [w for w in re.findall(r"[a-z0-9]+", _fold(s)) if w not in generic]


def chain_key(r, ticker, uniq):
    fam = FAMILY.get(r.get("deal_type"), "?")
    if fam == "stake":
        return "%s:stake:%s" % (ticker or "?", uniq)
    w = PN.key(r.get("property")).split()          # OPT_V1e (PN_V1): the shared project-name key
    if w:
        return "%s:%s:%s" % (ticker or "?", fam, " ".join(w[:3]))
    c = _key_words(r.get("counterparty"), _CO_GENERIC)
    if c:
        return "%s:%s:cp=%s" % (ticker or "?", fam, " ".join(c[:2]))
    return "%s:%s:none:%s" % (ticker or "?", fam, uniq)


def _days(a, b):
    try:
        return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)
    except (TypeError, ValueError):
        return 10 ** 6


def _cp_differ(a, b):
    if not a or not b:
        return False
    wa, wb = set(_key_words(a, _CO_GENERIC)), set(_key_words(b, _CO_GENERIC))
    return bool(wa and wb) and not (wa & wb)


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
    if any(_cp_differ(g["counterparty"], row["counterparty"]) for g in group):
        return False
    stages = {g["stage"] for g in group}
    if "terminated" in stages:
        return False                          # a terminated deal is over; the next one on the ground is new
    if FAMILY.get(row["deal_type"]) in ("buy", "sell") and "completed" in stages:
        return False                          # a closed purchase or sale is over
    if row["stage"] in ("proposed", "signed") and stages & {"signed", "payment", "amended", "completed"} and \
            _days(last["published_at"], row["published_at"]) > RENEW_DAYS:
        return False                          # a new LOI / agreement long after a signed deal is a new deal
    if row["stage"] == "proposed" and stages & {"payment", "completed", "amended"}:
        return False
    return True


def compute(items):
    """items: iterable of (event, parsed); event = {event_id, ticker, published_at, raw_headline, slug, tagged};
    parsed = options.parse_records() output. Returns (rows, stats)."""
    items = sorted(items, key=lambda x: ((x[0].get("published_at") or ""), x[0]["event_id"]))
    out = []
    st = {"items": 0, "published": 0, "rows": 0, "markers": 0, "tagged_published": 0, "untagged_published": 0,
          "chains": 0, "repeat_rows": 0, "filled": 0}
    for ev, p in items:
        st["items"] += 1
        rows = [dict(r) for r in (p.get("rows") or []) if r.get("deal_type") and r.get("stage")]
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
                       tag_confirmed=1 if tagged else 0, chain_items=1, latest=1, stage_rank=STAGE_RANK.get(row["stage"]),
                       chain_key=chain_key(row, ev.get("ticker"), "%s/%d" % (ev["event_id"][:12], i)),
                       first_reported=(ev.get("published_at") or "")[:10] or None,
                       raw_headline=(ev.get("raw_headline") or "")[:500], published_at=ev.get("published_at"))
            out.append(row)
            st["rows"] += 1
            st["stage_" + row["stage"]] = st.get("stage_" + row["stage"], 0) + 1
            st["type_" + row["deal_type"]] = st.get("type_" + row["deal_type"], 0) + 1
    chains = {}
    for row in out:
        k = row["chain_key"]
        if not k or row["deal_type"] is None:
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
    """(event, parsed) for every approved item this version found a deal in, and every approved item carrying the
    tag today (those with none become marker rows)."""
    from portal.extractors import options as X
    found = {r[0] for r in conn.execute(
        "SELECT DISTINCT r.event_id FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
        "WHERE r.extractor=? AND r.version=? AND f.field='is_deal' AND f.value_num=1",
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
                " WHERE r2.extractor=? AND r2.version=? AND f2.field='is_deal' AND f2.value_num=1)",
                (EXTRACTOR, version, EXTRACTOR, version)):
            facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    return [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]


def _ensure_schema(conn):
    conn.executescript(TABLE_SQL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(land_deals)")}
    for line in TABLE_SQL.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)", line)
        if m and m.group(1) not in have and m.group(1) != "ld_id":
            conn.execute("ALTER TABLE land_deals ADD COLUMN %s %s" % (m.group(1), m.group(2)))
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
        st["rowsync"] = rowsync.sync_rows(conn, "land_deals", "ld_id", _COLS, rows, {"extractor_version": version})
    conn.execute("BEGIN IMMEDIATE")
    try:
        # OPSFIX item 1 (2026-10-05): write only the rows that changed; same table contents (portal/rowsync.py)
        from portal import rowsync
        st["rowsync"] = rowsync.sync_rows(conn, "land_deals", "ld_id", _COLS, rows, {"extractor_version": version})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[options_publish] " + json.dumps(st))
    return st


# ------------------------------------------------------------------ self-tests
def _selftest():
    sys.path.insert(0, "/opt/mnt/app")
    from portal import facts as F
    from portal.extractors import options as X
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
        ("e1", "ABC.V", "2026-03-02", "ABC Gold Signs Option to Acquire Alpha Property",
         lead % "March 2, 2026" + "has entered into an option agreement with Beta Minerals Inc. (\"Beta\") pursuant to "
                                  "which the Company may acquire a 100% interest in the Alpha Property by making cash "
                                  "payments totalling $250,000 over four years." + fill, TAG),
        ("e2", "ABC.V", "2027-05-15", "ABC Gold Exercises Option on Alpha Property",
         lead % "May 15, 2027" + "has exercised its option and now holds a 100% interest in the Alpha Property under "
                                 "the option agreement with Beta Minerals Inc." + fill, TAG),
        ("e3", "ABC.V", "2026-06-01", "ABC Gold Stakes New Claims at Gamma Lake",
         lead % "June 1, 2026" + "has staked 45 mineral claims covering 2,300 hectares at its Gamma Lake Property." + fill,
         "Mergers & Acquisitions"),
        ("e4", "ABC.V", "2026-07-01", "ABC Gold Grants Stock Options",
         lead % "July 1, 2026" + "has granted incentive stock options to directors." + fill, TAG),
        ("e5", "XYZ.V", "2026-01-05", "XYZ Closes Private Placement",
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
    eq("signed row", [(r["deal_type"], r["stage"], r["latest"], r["date"]) for r in by["e1"]],
       [("option_in", "signed", 0, "2026-03-02")])
    eq("exercise is the lead, cash filled from the chain",
       [(r["stage"], r["latest"], r["chain_items"], r["first_reported"], r["cash"], r["counterparty"]) for r in by["e2"]],
       [("completed", 1, 2, "2026-03-02", 250000.0, "Beta Minerals")])
    eq("same deal", by["e1"][0]["chain_key"] == by["e2"][0]["chain_key"], True)
    eq("untagged staking is published", [(r["deal_type"], r["tag_confirmed"], r["area"]) for r in by["e3"]],
       [("staking", 0, 2300.0)])
    eq("marker for tagged stock options", [(r["deal_type"], r["n_rows"]) for r in by["e4"]], [(None, 0)])
    eq("untagged, nothing -> absent", by.get("e5"), None)
    # chain rules on synthetic rows
    E = lambda eid, pub: {"event_id": eid, "ticker": "Q.V", "published_at": pub, "raw_headline": "", "slug": "",
                          "tagged": True}
    R = lambda typ, stage, prop, cp=None: {"rows": [{"deal_type": typ, "stage": stage, "property": prop,
                                                     "counterparty": cp}]}
    rs, _ = compute([(E("a", "2024-01-01"), R("option_in", "signed", "Kappa Property", "Beta Corp")),
                     (E("b", "2024-06-01"), R("option_in", "terminated", "Kappa Property")),
                     (E("c", "2025-01-01"), R("option_in", "signed", "Kappa Property", "Delta Inc")),
                     (E("d", "2025-02-01"), R("option_in", "signed", "Kappa Property", "Omega Ltd"))])
    ck = [r["chain_key"] for r in rs]
    eq("terminated ends the chain; another optionor is another deal",
       [ck[0] == ck[1], ck[1] == ck[2], ck[2] == ck[3]], [True, False, False])
    rs, _ = compute([(E("a", "2024-01-01"), R("staking", "signed", "Gamma Lake")),
                     (E("b", "2024-02-01"), R("staking", "signed", "Gamma Lake"))])
    eq("staking never chains", rs[0]["chain_key"] == rs[1]["chain_key"], False)
    rs, _ = compute([(E("a", "2024-01-01"), R("property_purchase", "proposed", "Sigma Property", "Theta Mining")),
                     (E("b", "2024-03-01"), R("property_purchase", "completed", "Sigma Property", "Theta Mining Ltd")),
                     (E("c", "2024-04-01"), R("option_out", "signed", "Sigma Property", "Rho Corp"))])
    eq("LOI -> closing chains; option out is another family",
       [rs[0]["chain_key"] == rs[1]["chain_key"], rs[1]["chain_key"] == rs[2]["chain_key"], rs[1]["latest"]],
       [True, False, 1])
    rs, _ = compute([(E("a", "2024-01-01"), R("option_in", "signed", None, None)),
                     (E("b", "2024-02-01"), R("option_in", "payment", None, None))])
    eq("no property, no counterparty: no chain", rs[0]["chain_key"] == rs[1]["chain_key"], False)
    publish(conn, "9.9.9", log=lambda *_: None)
    publish(conn, "9.9.9", log=lambda *_: None)
    eq("idempotent", conn.execute("SELECT COUNT(*) FROM land_deals").fetchone()[0], len(rows))
    print("options_publish: %s" % ("ok" if not bad else "%d FAILURES" % bad))
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
            print("[options_publish] dry run: no version given and none active")
            return 2
        rows, st = compute(load_items(conn, v))
        st.update(version=v)
        print("[options_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[options_publish] no active options version; nothing to publish")
        return 0
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[options_publish] FAILED publishing %s: %s: %s" % (version, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
