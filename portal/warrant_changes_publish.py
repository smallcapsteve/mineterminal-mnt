"""Publish the Warrant Changes reader into the table Mine Terminal Pro reads (WCH_PUBLISH_V1, 2026-10-07).

The facts store holds what WCH_V1 (portal/extractors/warrant_changes.py) found in every approved release. This module
rebuilds `warrant_changes` from the ACTIVE warrant_changes version: one row per change the reader found, in any
approved release (warrant notices are rarely tagged; the tag is only recorded, tag_confirmed).

THE FINANCING GATE (Justin, 2026-10-07: "Gate it, then ship"). A change may move, retire or reprice a warrant-expiry
event on MTP (publish = 1) only when
  1. it is a kind that changes the event: extension or acceleration (new date), repricing (new strike), or an exercise
     that leaves none of the group outstanding (n_remaining = 0: the event is retired);
  2. it matches ONE financing MNT stores (WM): same ticker, a closing with warrants on or before the release (+3 days),
     strike within 2% when the release states one, and the release's issue date within 7 days of that closing or its
     old expiry within 7 days of closing + term; a stated issue date or old expiry that points elsewhere rules the
     financing out; a strike-only match counts only for a financing whose warrants have not expired; a tie between
     financings is not a match;
  3. its dates make sense: an extension's new date is after the old one, within 6 years of the closing and no more
     than a month before the release; an acceleration's new date is between 10 days before and 130 days after the
     release and earlier than the old expiry; a repricing changes the strike.
Everything else is stored with publish = 0 and the reason (hold_reason); rows with affects = 1 and publish = 0 are the
review list. Measured on the three labelled draws before install (gate_eval.py): 40 published, 39 right, 1 not
verifiable; coverage 36% of the labelled event-changing rows.

compute() is a pure function of the items and the closings. publish() rebuilds the table in one short transaction.

Timer use (sync_structured.py): python3 -m portal.warrant_changes_publish
Self-tests: python3 -m portal.warrant_changes_publish --selftest     (in-memory; touches nothing live)
Dry run:    python3 -m portal.warrant_changes_publish --dry-run [--version X.Y.Z]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from datetime import date, timedelta

EXTRACTOR = "warrant_changes"
TAG = "Financings"
DB = "/opt/mnt/app/portal/portal.db"
TABLE = "warrant_changes"
EVENT_KINDS = ("extension", "acceleration", "repricing", "exercise")

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS warrant_changes (
    wc_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id               TEXT NOT NULL,
    ordinal                INTEGER NOT NULL DEFAULT 0,
    ticker                 TEXT,
    slug                   TEXT,
    change                 TEXT,
    status                 TEXT,
    n_warrants             REAL,
    strike_old             REAL,
    strike_new             REAL,
    issued                 TEXT,
    expiry_old             TEXT,
    expiry_new             TEXT,
    program_end            TEXT,
    n_exercised            REAL,
    proceeds               REAL,
    n_remaining            REAL,
    new_series_n           REAL,
    new_series_strike      REAL,
    new_series_term_months REAL,
    new_series_expiry      TEXT,
    affects                INTEGER NOT NULL DEFAULT 0,
    financing_id           TEXT,
    close_date             TEXT,
    term_months            INTEGER,
    expiry_before          TEXT,
    matched_by             TEXT,
    publish                INTEGER NOT NULL DEFAULT 0,
    hold_reason            TEXT,
    n_rows                 INTEGER NOT NULL DEFAULT 1,
    tag_confirmed          INTEGER NOT NULL DEFAULT 0,
    raw_headline           TEXT,
    published_at           TEXT,
    extractor_version      TEXT
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_wch_pub    ON warrant_changes(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_wch_ticker ON warrant_changes(ticker);
CREATE INDEX IF NOT EXISTS idx_wch_event  ON warrant_changes(event_id);
CREATE INDEX IF NOT EXISTS idx_wch_fin    ON warrant_changes(financing_id);
"""

_ROW_FIELDS = ("change", "status", "n_warrants", "strike_old", "strike_new", "issued", "expiry_old", "expiry_new",
               "program_end", "n_exercised", "proceeds", "n_remaining", "new_series_n", "new_series_strike",
               "new_series_term_months", "new_series_expiry")
_GATE_FIELDS = ("affects", "financing_id", "close_date", "term_months", "expiry_before", "matched_by", "publish",
                "hold_reason")
_COLS = ("event_id", "ordinal", "ticker", "slug") + _ROW_FIELDS + _GATE_FIELDS + ("n_rows", "tag_confirmed",
                                                                                  "raw_headline", "published_at")


# ------------------------------------------------------------------ the gate (pure)
def D(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:  # noqa: BLE001
        return None


def add_months(d, n):
    m = d.month - 1 + int(n)
    y, m = d.year + m // 12, m % 12 + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, min(d.day, day))
        except ValueError:
            continue


def affects(row):
    k = row.get("change")
    if k not in EVENT_KINDS:
        return False
    if k == "exercise":
        return row.get("n_remaining") is not None and float(row["n_remaining"]) == 0
    return True


def match(row, closes, rel):
    """closes: [(financing_id, close_date, strike, term_months)] for the ticker. -> ((fid, cd, strike, term, how), None)
    or (None, why)."""
    cand = [x for x in closes if x[1] <= rel + timedelta(days=3)]
    if not cand:
        return None, "no stored financing with warrants"
    st = row.get("strike_old")
    iss = [D(x) for x in (row.get("issued") or []) if D(x)]
    old = D(row.get("expiry_old"))
    hits = []
    for fid, cd, fs, term in cand:
        s_ok = st is not None and abs(st - fs) <= max(0.005, 0.02 * fs)
        if st is not None and not s_ok:
            continue
        i_ok = any(abs((d - cd).days) <= 7 for d in iss)
        o_ok = bool(old and term and abs((old - add_months(cd, term)).days) <= 7)
        if (iss and not i_ok and not o_ok) or (old and term and not o_ok and not i_ok):
            continue                            # a stated issue date or old expiry points elsewhere
        if i_ok or o_ok:
            how = "issue date" if i_ok else "old expiry"
            hits.append((2 + s_ok, fid, cd, fs, term, how + (" + strike" if s_ok else "")))
        elif s_ok:
            exp = add_months(cd, term) if term else None
            if exp is None or exp >= rel - timedelta(days=30):
                hits.append((1, fid, cd, fs, term, "strike only"))
    if not hits:
        return None, "no financing matches strike / issue date / old expiry"
    best = max(h[0] for h in hits)
    top = {h[1] for h in hits if h[0] == best}
    if len(top) > 1:
        return None, "ambiguous: %d financings fit" % len(top)
    return [h for h in hits if h[0] == best][0][1:], None


def sane(row, fin, rel):
    fid, cd, fs, term = fin[:4]
    cur = add_months(cd, term) if term else None
    new = D((row.get("expiry_new") or [None])[0])
    k = row["change"]
    if k == "extension":
        base = D(row.get("expiry_old")) or cur
        return bool(new and base and new > base and new <= cd + timedelta(days=6 * 366)
                    and new >= rel - timedelta(days=31))
    if k == "acceleration":
        top = D(row.get("expiry_old")) or cur
        return bool(new and rel - timedelta(days=10) <= new <= rel + timedelta(days=130) and (top is None or new < top))
    if k == "repricing":
        return row.get("strike_new") is not None and row.get("strike_new") != row.get("strike_old")
    if k == "exercise":
        return row.get("n_remaining") is not None and float(row["n_remaining"]) == 0
    return False


def compute(items, closes_for):
    """items: [(event, parsed)] with event {event_id, ticker, published_at, raw_headline, slug, tagged} and parsed the
    reader's parse_records() dict; closes_for(ticker) -> [(financing_id, close_date, strike, term)]. -> (rows, stats)"""
    out = []
    st = {"releases": 0, "rows": 0, "affects": 0, "published": 0, "held": {}, "by_change": {}}
    for ev, parsed in items:
        rows = [r for r in (parsed or {}).get("rows") or [] if r.get("change")]
        if not rows:
            continue
        st["releases"] += 1
        rel = D(ev.get("published_at"))
        for i, r in enumerate(rows):
            row = {c: None for c in _COLS}
            row.update(event_id=ev["event_id"], ordinal=i, ticker=ev.get("ticker"), slug=ev.get("slug"),
                       n_rows=len(rows), tag_confirmed=1 if ev.get("tagged") else 0,
                       raw_headline=(ev.get("raw_headline") or "")[:500], published_at=ev.get("published_at"))
            for k in _ROW_FIELDS:
                v = r.get(k)
                row[k] = "|".join(v) if isinstance(v, list) else v
            row["issued"] = row["issued"] or None
            row["expiry_new"] = row["expiry_new"] or None
            row["affects"], row["publish"] = 1 if affects(r) else 0, 0
            st["rows"] += 1
            st["by_change"][r["change"]] = st["by_change"].get(r["change"], 0) + 1
            if row["affects"]:
                st["affects"] += 1
                fin, why = (None, "no release date") if rel is None else match(r, closes_for(ev.get("ticker")), rel)
                if fin:
                    fid, cd, fs, term, how = fin
                    row.update(financing_id=str(fid), close_date=cd.isoformat(), term_months=term, matched_by=how,
                               expiry_before=add_months(cd, term).isoformat() if term else None)
                    if sane(r, fin, rel):
                        row["publish"] = 1
                    else:
                        why = "dates do not make sense for the change"
                if not row["publish"]:
                    row["hold_reason"] = why
                    st["held"][why] = st["held"].get(why, 0) + 1
                st["published"] += row["publish"]
            out.append(row)
    return out, st


# ------------------------------------------------------------------ reading the store
def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def active_version(conn):
    if not _has_table(conn, "fx_extractor_versions"):
        return None
    r = conn.execute("SELECT version FROM fx_extractor_versions WHERE extractor=? AND status='active'",
                     (EXTRACTOR,)).fetchone()
    return r[0] if r else None


def closes_loader(conn):
    """closes_for(ticker): the ticker's closings that carry warrants (financing_events joined to financings)."""
    cache = {}
    ok = _has_table(conn, "financings") and _has_table(conn, "financing_events")

    def closes_for(ticker):
        if not ok or not ticker:
            return []
        if ticker not in cache:
            rows = conn.execute(
                "SELECT f.financing_id, fe.event_date, COALESCE(fe.warrant_strike, f.warrant_strike), "
                "COALESCE(fe.warrant_term_months, f.warrant_term_months) FROM financing_events fe "
                "JOIN financings f ON f.financing_id = fe.financing_id WHERE fe.ticker = ? "
                "AND (fe.role LIKE '%close%' OR fe.amount_this_close IS NOT NULL) AND COALESCE(fe.is_duplicate,0) = 0 "
                "AND COALESCE(fe.warrant_strike, f.warrant_strike) IS NOT NULL", (ticker,)).fetchall()
            out = []
            for fid, d, s, t in rows:
                try:
                    if D(d) and float(s) > 0:
                        out.append((fid, D(d), float(s), int(float(t)) if t else None))
                except (TypeError, ValueError):
                    continue
            cache[ticker] = out
        return cache[ticker]
    return closes_for


def load_items(conn, version):
    """(event, parsed) for every approved release this version found a change in."""
    from portal.extractors import warrant_changes as X
    with_rows = [r[0] for r in conn.execute(
        "SELECT DISTINCT r.event_id FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
        "WHERE r.extractor=? AND r.version=? AND f.field='is_change' AND f.value_num=1", (EXTRACTOR, version))]
    evs, facts = {}, {}
    for i in range(0, len(with_rows), 500):
        chunk = with_rows[i:i + 500]
        q = ",".join("?" * len(chunk))
        for eid, tk, pub, hl, slug, cats in conn.execute(
                "SELECT event_id, ticker, COALESCE(published_at, classified_at), raw_headline, slug, categories "
                "FROM events WHERE review_status='auto_approved' AND event_id IN (%s)" % q, chunk):
            evs[eid] = {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl, "slug": slug,
                        "tagged": ("|" + (cats or "") + "|").find("|" + TAG + "|") >= 0}
        for eid, ordinal, field_, seq, num, text in conn.execute(
                "SELECT r.event_id, r.ordinal, f.field, f.seq, f.value_num, f.value_text "
                "FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
                "WHERE r.extractor=? AND r.version=? AND r.event_id IN (%s)" % q, [EXTRACTOR, version] + chunk):
            facts.setdefault(eid, {}).setdefault(ordinal, []).append((field_, seq, num, text))
    items = [(evs[e], X.parse_records(facts.get(e, {}))) for e in evs]
    items.sort(key=lambda it: (str(it[0]["published_at"] or ""), it[0]["event_id"]))
    return items


def _ensure_schema(conn):
    conn.executescript(TABLE_SQL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(warrant_changes)")}
    for line in TABLE_SQL.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+(TEXT|REAL|INTEGER)", line)
        if m and m.group(1) not in have and m.group(1) != "wc_id":
            conn.execute("ALTER TABLE warrant_changes ADD COLUMN %s %s" % (m.group(1), m.group(2)))
    conn.executescript(INDEX_SQL)


def publish(conn, version, log=print):
    if not re.match(r"^[0-9]+[.][0-9]+[.][0-9]+$", version or ""):
        raise ValueError("bad version %r" % (version,))
    t0 = time.time()
    rows, st = compute(load_items(conn, version), closes_loader(conn))
    _ensure_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM warrant_changes")
        conn.executemany(
            "INSERT INTO warrant_changes(" + ", ".join(_COLS) + ", extractor_version) VALUES ("
            + ", ".join(":" + c for c in _COLS) + ", '" + version + "')", rows)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[warrant_changes_publish] " + json.dumps(st, sort_keys=True))
    return st


# ------------------------------------------------------------------ self-tests
def _selftest():
    sys.path.insert(0, "/opt/mnt/app")
    from portal import facts as F
    from portal.extractors import warrant_changes as X
    bad = 0

    def eq(name, got, want):
        nonlocal bad
        if got != want:
            bad += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))

    # --- the gate, pure
    cl = [("F1", date(2024, 3, 1), 0.25, 24), ("F2", date(2024, 9, 1), 0.40, 24), ("F3", date(2024, 9, 20), 0.40, 24)]
    ext = {"change": "extension", "status": "proposed", "strike_old": 0.25, "issued": ["2024-03-01"],
           "expiry_old": "2026-03-01", "expiry_new": ["2027-03-01"]}
    rel = date(2026, 2, 1)
    fin, why = match(ext, cl, rel)
    eq("issue date + strike finds the financing", (fin and fin[0], fin and fin[4], why), ("F1", "issue date + strike", None))
    eq("extension dates make sense", sane(ext, fin, rel), True)
    eq("an extension backwards does not", sane(dict(ext, expiry_new=["2025-12-01"]), fin, rel), False)
    eq("strike that fits nothing", match(dict(ext, strike_old=0.9), cl, rel), (None, "no financing matches strike / issue date / old expiry"))
    eq("stated issue date pointing elsewhere rules it out", match(dict(ext, issued=["2023-01-01"], expiry_old=None), cl, rel)[0], None)
    eq("two closings, same strike, strike only: ambiguous", match({"change": "repricing", "strike_old": 0.40}, cl, rel),
       (None, "ambiguous: 2 financings fit"))
    eq("closing after the release is not a candidate", match(dict(ext), cl, date(2024, 2, 1)),
       (None, "no stored financing with warrants"))
    acc = {"change": "acceleration", "status": "effective", "strike_old": 0.40, "issued": ["2024-09-01"],
           "expiry_new": ["2026-03-15"]}
    fin2, _ = match(acc, cl, rel)
    eq("acceleration picks the tranche by issue date", fin2 and fin2[0], "F2")
    eq("acceleration within 130 days", (sane(acc, fin2, rel), sane(dict(acc, expiry_new=["2026-09-01"]), fin2, rel)), (True, False))
    eq("what changes an event", (affects({"change": "exercise", "n_remaining": 0.0}), affects({"change": "exercise", "n_remaining": 5.0}),
                                 affects({"change": "incentive"}), affects({"change": "repricing"})), (True, False, False, True))
    rows, st = compute([({"event_id": "a", "ticker": "ABC.V", "published_at": "2026-02-01T12:00:00", "raw_headline": "h",
                          "slug": "s", "tagged": False},
                         {"rows": [ext, dict(ext, change="incentive"), dict(ext, strike_old=0.9)]})],
                       lambda t: cl if t == "ABC.V" else [])
    eq("compute: published, stored, held",
       [(r["change"], r["affects"], r["publish"], r["financing_id"], r["hold_reason"], r["issued"], r["expiry_new"]) for r in rows],
       [("extension", 1, 1, "F1", None, "2024-03-01", "2027-03-01"), ("incentive", 0, 0, None, None, "2024-03-01", "2027-03-01"),
        ("extension", 1, 0, None, "no financing matches strike / issue date / old expiry", "2024-03-01", "2027-03-01")])
    eq("stats", (st["rows"], st["affects"], st["published"]), (3, 2, 1))

    # --- through the facts store
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, published_at TEXT, "
                       "classified_at TEXT, raw_headline TEXT, raw_body TEXT, slug TEXT, categories TEXT, "
                       "review_status TEXT);"
                       "CREATE TABLE financings (financing_id TEXT PRIMARY KEY, ticker TEXT, warrant_strike REAL, "
                       "warrant_term_months REAL);"
                       "CREATE TABLE financing_events (event_id TEXT, financing_id TEXT, ticker TEXT, role TEXT, "
                       "warrant_strike REAL, warrant_term_months REAL, event_date TEXT, amount_this_close REAL, "
                       "is_duplicate INTEGER);")
    F.ensure_schema(conn)
    conn.execute("INSERT INTO financings VALUES ('F1', 'ABC.V', 0.25, 24)")
    conn.execute("INSERT INTO financing_events VALUES ('c1', 'F1', 'ABC.V', 'tranche_close', NULL, NULL, '2024-03-01', 1e6, 0)")
    spec = F.ExtractorSpec(EXTRACTOR, "9.9.9", X.KIND, TAG, X.extract, "selftest")
    fill = " The Company continues to advance its projects in Ontario and remains well funded." * 4
    lead = "Vancouver, British Columbia, %s -- ABC Gold Corp. (TSXV: ABC) (\"ABC\" or the \"Company\") "
    evs = [("e1", "ABC.V", "2026-02-01", "ABC Gold Announces Proposed Extension of Warrants",
            lead % "February 1, 2026" + "announces that it intends to extend the expiry date of 5,000,000 common share "
            "purchase warrants issued on March 1, 2024 and exercisable at $0.25 per share. The expiry date of the "
            "warrants will be extended from March 1, 2026 to March 1, 2027, subject to TSX Venture Exchange approval."
            + fill, "Corporate Updates"),
           ("e2", "ABC.V", "2026-02-02", "ABC Gold Closes Private Placement",
            lead % "February 2, 2026" + "has closed a private placement of 2,000,000 units." + fill, TAG)]
    for eid, tk, pub, hl, body, cats in evs:
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?, 'auto_approved')",
                     (eid, tk, pub, None, hl, body, eid + "-slug", cats))
    F.run_batch(conn, spec, [dict(r) for r in conn.execute("SELECT * FROM events")])
    publish(conn, "9.9.9", log=lambda *_: None)
    got = [tuple(r) for r in conn.execute("SELECT event_id, change, status, expiry_new, financing_id, matched_by, publish, "
                                          "tag_confirmed FROM warrant_changes ORDER BY wc_id").fetchall()]
    eq("published through the store", got,
       [("e1", "extension", "proposed", "2027-03-01", "F1", "issue date + strike", 1, 0)])
    publish(conn, "9.9.9", log=lambda *_: None)
    eq("idempotent", conn.execute("SELECT COUNT(*) FROM warrant_changes").fetchone()[0], 1)
    print("warrant_changes_publish: %s" % ("ok" if not bad else "%d FAILURES" % bad))
    return 1 if bad else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv:
        return _selftest()
    db = argv[argv.index("--db") + 1] if "--db" in argv else DB
    if "--dry-run" in argv:
        conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=30)
        v = argv[argv.index("--version") + 1] if "--version" in argv else active_version(conn)
        if not v:
            print("[warrant_changes_publish] dry run: no version given and none active")
            return 2
        rows, st = compute(load_items(conn, v), closes_loader(conn))
        st.update(version=v)
        print("[warrant_changes_publish] dry run " + json.dumps(st, sort_keys=True))
        return 0
    conn = sqlite3.connect(db, timeout=30, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=30000")
    version = active_version(conn)
    if version is None:
        print("[warrant_changes_publish] no active warrant_changes version; nothing to publish")
        return 0
    try:
        from portal import pub_incr   # PUB_INCR_V1 (2026-11-05): per-company publishing, portal/pub_incr_modes
        pub_incr.run('warrant_changes', conn, version, publish)
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[warrant_changes_publish] FAILED publishing %s: %s: %s" % (version, type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
