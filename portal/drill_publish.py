"""Publish the new Drill Results reader into the tables /drills reads (DRILL_PUBLISH_V1, 2026-09-17).

The facts store holds what DRILL_V1 (portal/extractors/drill_results.py) found in every
release. Pages do not read the facts store directly yet: /drills, /api/drills/recent.json,
the MTP company counts and the ticker rename all read drill_results. This module turns the
ACTIVE drill_results version into:

  drill_results    one row per release that reports new drill assays (the columns the old
                   backfill wrote, plus extractor_version)
  drill_intervals  every accepted interval of those releases, for the expandable rows

Rules, in order, over tagged approved releases oldest first:
  1. the extractor said the release is a drill result (is_result = 1)
  2. at least one accepted interval was not already published by an earlier release of the
     same ticker (the old backfill's recap rule: repeats and wire copies are skipped)
  3. the best interval is the extractor's; if that one was published before, the best fresh
     interval of the same metal family (else any) takes its place

compute() is a pure function of (events, facts) so the accuracy gate can count the rows a
candidate version would publish without writing anything. publish() rebuilds both tables in
one short transaction.

Timer use (sync_structured.py): python3 -m portal.drill_publish
  - an active drill_results version exists  -> publish it
  - none yet                                -> run the legacy drill_backfill.py (unchanged)
Once a version is active the legacy backfill never runs again (Justin, 2026-09-17: fix forward
on the new reader, never fall back). If publishing fails after the switch, rows the legacy
backfill wrote are removed rather than left on the page.

Self-tests: python3 -m portal.drill_publish --selftest   (in-memory; touches nothing live)
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time

EXTRACTOR = "drill_results"
TAG = "Drill Results"
DB = "/opt/mnt/app/portal/portal.db"
LEGACY = "/opt/mnt/app/drill_backfill.py"

TO_PPM = {"g/t": 1.0, "ppm": 1.0, "ppb": 0.001, "%": 10000.0, "oz/t": 34.2857, "opt": 34.2857, "kg/t": 1000.0,
          "gms": 1.0}

SCHEMA = """
CREATE TABLE IF NOT EXISTS drill_results (
    drill_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT NOT NULL UNIQUE,
    ticker        TEXT,
    project       TEXT,
    top_hole_id   TEXT,
    top_grade     REAL,
    top_unit      TEXT,
    top_metal     TEXT,
    top_length_m  REAL,
    top_summary   TEXT,
    n_intercepts  INTEGER,
    raw_headline  TEXT,
    published_at  TEXT,
    sample_type   TEXT
);
CREATE INDEX IF NOT EXISTS ix_drill_ticker      ON drill_results(ticker);
CREATE INDEX IF NOT EXISTS ix_drill_published   ON drill_results(published_at);
CREATE INDEX IF NOT EXISTS ix_drill_topscore    ON drill_results(top_grade, top_length_m);
CREATE TABLE IF NOT EXISTS drill_intervals (
    event_id         TEXT NOT NULL,
    seq              INTEGER NOT NULL,
    hole_id          TEXT,
    from_m           REAL,
    to_m             REAL,
    length_m         REAL,
    grade            REAL,
    unit             TEXT,
    metal            TEXT,
    summary          TEXT,
    including        INTEGER NOT NULL DEFAULT 0,
    is_best          INTEGER NOT NULL DEFAULT 0,
    reported_before  INTEGER NOT NULL DEFAULT 0,
    src              TEXT,
    PRIMARY KEY (event_id, seq)
) WITHOUT ROWID;
"""


def family(metal):
    m = (metal or "").split("+")[0]
    if m.endswith("Eq"):
        m = m[:-2]
    return m.upper()


def fmt_grade(g):
    if g is None:
        return ""
    if g >= 1000:
        s = "%.1f" % g
    elif g >= 1:
        s = "%.2f" % g
    else:
        s = "%.3f" % g
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def summary(grade, unit, metal, length_m):
    if grade is None or length_m is None:
        return ""
    u = unit or "g/t"
    g = fmt_grade(grade) + ("%" if u == "%" else " " + u)
    return f"{g} {metal or ''} / {length_m:g}m".replace("  ", " ")


def parse_facts(rows):
    """rows: iterable of (field, seq, value_num, value_text, unit, metal) for one release's record.
    Returns {"is_result", "reason", "project", "best_seq", "intervals": [...] } (intervals in seq order)."""
    top = {}
    ivs = {}
    for field, seq, num, text, unit, metal in rows:
        if field.startswith("iv_"):
            d = ivs.setdefault(int(seq), {"seq": int(seq)})
            key = field[3:]
            if key == "grade":
                d.update(grade=num, unit=unit, metal=metal)
            elif key in ("length_m", "from_m", "to_m"):
                d[key] = num
            elif key in ("ok", "including"):
                d[key] = bool(num)
            else:
                d[key] = text
        elif int(seq) == 0:
            top[field] = num if num is not None else text
    return {"is_result": top.get("is_result") == 1.0, "reason": top.get("release_reason"),
            "project": top.get("project"),
            "best_seq": int(top["best_seq"]) if top.get("best_seq") is not None else None,
            "intervals": [ivs[k] for k in sorted(ivs)]}


def _key(iv):
    return (round(iv.get("length_m") or 0.0, 1), round(iv.get("grade") or 0.0, 2), iv.get("metal"))


def _value(iv):
    return (iv.get("grade") or 0.0) * TO_PPM.get(iv.get("unit"), 1.0) * (iv.get("length_m") or 0.0)


def compute(items):
    """items: iterable of (event, parsed), event = {event_id, ticker, published_at, raw_headline},
    in any order. Returns (rows, intervals, stats); rows/intervals are dicts ready to insert."""
    items = sorted(items, key=lambda x: ((x[0].get("published_at") or ""), x[0]["event_id"]))
    seen = {}
    rows, intervals = [], []
    stats = {"releases": 0, "not_result": 0, "no_accepted_interval": 0, "recap": 0, "published": 0, "intervals": 0}
    for ev, p in items:
        stats["releases"] += 1
        if not p["is_result"]:
            stats["not_result"] += 1
            continue
        ok = [iv for iv in p["intervals"] if iv.get("ok") and iv.get("grade") is not None and iv.get("length_m")]
        if not ok:
            stats["no_accepted_interval"] += 1
            continue
        tseen = seen.setdefault(ev.get("ticker") or "", set())
        fresh = [iv for iv in ok if _key(iv) not in tseen]
        if not fresh:
            stats["recap"] += 1
            continue
        fresh_keys = {_key(iv) for iv in fresh}
        tseen.update(fresh_keys)
        best = next((iv for iv in fresh if iv["seq"] == p["best_seq"]), None)
        if best is None:
            ref = next((iv for iv in ok if iv["seq"] == p["best_seq"]), None)
            pool = [iv for iv in fresh if not iv.get("including")] or fresh
            same = [iv for iv in pool if ref is not None and family(iv.get("metal")) == family(ref.get("metal"))]
            best = max(same or pool, key=_value)
        eid = ev["event_id"]
        rows.append({
            "event_id": eid, "ticker": ev.get("ticker"), "project": p["project"], "top_hole_id": best.get("hole"),
            "top_grade": best["grade"], "top_unit": best.get("unit"), "top_metal": best.get("metal"),
            "top_length_m": best["length_m"],
            "top_summary": summary(best["grade"], best.get("unit"), best.get("metal"), best["length_m"]),
            "n_intercepts": len(ok), "raw_headline": (ev.get("raw_headline") or "")[:500],
            "published_at": ev.get("published_at"), "sample_type": "drill"})
        for iv in ok:
            intervals.append({
                "event_id": eid, "seq": iv["seq"], "hole_id": iv.get("hole"), "from_m": iv.get("from_m"),
                "to_m": iv.get("to_m"), "length_m": iv["length_m"], "grade": iv["grade"], "unit": iv.get("unit"),
                "metal": iv.get("metal"),
                "summary": summary(iv["grade"], iv.get("unit"), iv.get("metal"), iv["length_m"]),
                "including": 1 if iv.get("including") else 0, "is_best": 1 if iv is best else 0,
                "reported_before": 0 if _key(iv) in fresh_keys else 1, "src": iv.get("src")})
        stats["published"] += 1
        stats["intervals"] += len(ok)
    return rows, intervals, stats


# ------------------------------------------------------------------ reading the facts store
def active_version(conn):
    r = conn.execute("SELECT version FROM fx_extractor_versions WHERE extractor=? AND status='active'",
                     (EXTRACTOR,)).fetchone() if _has_table(conn, "fx_extractor_versions") else None
    return r[0] if r else None


def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def load_items(conn, version):
    """(event, parsed) for every approved release carrying the Drill Results tag today that this
    version wrote a record for. The tag is read from events now, as the page does."""
    evs = {}
    for eid, tk, pub, hl in conn.execute(
            "SELECT e.event_id, e.ticker, e.published_at, e.raw_headline FROM events e "
            "JOIN fx_records r ON r.event_id=e.event_id AND r.extractor=? AND r.version=? "
            "WHERE e.review_status='auto_approved' AND ('|' || COALESCE(e.categories,'') || '|') LIKE ?",
            (EXTRACTOR, version, "%|" + TAG + "|%")):
        evs[eid] = {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl}
    facts = {}
    for eid, field, seq, num, text, unit, metal in conn.execute(
            "SELECT r.event_id, f.field, f.seq, f.value_num, f.value_text, f.unit, f.metal "
            "FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id "
            "WHERE r.extractor=? AND r.version=? AND r.ordinal=0", (EXTRACTOR, version)):
        if eid in evs:
            facts.setdefault(eid, []).append((field, seq, num, text, unit, metal))
    return [(evs[e], parse_facts(facts.get(e, []))) for e in evs]


def current_event_ids(conn):
    return {r[0] for r in conn.execute("SELECT event_id FROM drill_results")}


def publish(conn, version, log=print):
    """Rebuild drill_results and drill_intervals from `version` in one transaction. Returns stats."""
    import re
    if not re.match(r"^[0-9]+[.][0-9]+[.][0-9]+$", version or ""):
        raise ValueError(f"bad version {version!r}")
    t0 = time.time()
    rows, intervals, st = compute(load_items(conn, version))
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(drill_results)")}
    for col in ("sample_type", "extractor_version"):
        if col not in cols:
            conn.execute(f"ALTER TABLE drill_results ADD COLUMN {col} TEXT")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM drill_results")
        conn.executemany(
            "INSERT INTO drill_results(event_id, ticker, project, top_hole_id, top_grade, top_unit, top_metal, "
            "top_length_m, top_summary, n_intercepts, raw_headline, published_at, sample_type, extractor_version) "
            "VALUES (:event_id,:ticker,:project,:top_hole_id,:top_grade,:top_unit,:top_metal,:top_length_m,"
            ":top_summary,:n_intercepts,:raw_headline,:published_at,:sample_type,'" + version + "')", rows)
        conn.execute("DELETE FROM drill_intervals")
        conn.executemany(
            "INSERT INTO drill_intervals(event_id, seq, hole_id, from_m, to_m, length_m, grade, unit, metal, summary, "
            "including, is_best, reported_before, src) VALUES (:event_id,:seq,:hole_id,:from_m,:to_m,:length_m,"
            ":grade,:unit,:metal,:summary,:including,:is_best,:reported_before,:src)", intervals)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    st["seconds"] = round(time.time() - t0, 2)
    st["version"] = version
    log("[drill_publish] " + json.dumps(st))
    return st


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
        rows, intervals, st = compute(load_items(conn, v))
        cur = current_event_ids(conn)
        new = {r["event_id"] for r in rows}
        st.update(version=v, current_rows=len(cur), removed=len(cur - new), added=len(new - cur))
        print("[drill_publish] dry run " + json.dumps(st))
        return 0
    if version is None:
        print("[drill_publish] no active drill_results version; running the legacy drill_backfill.py")
        return subprocess.call([sys.executable, LEGACY])
    try:
        publish(conn, version)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[drill_publish] FAILED publishing {version}: {type(exc).__name__}: {exc}")
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(drill_results)")}
            if "extractor_version" not in cols or conn.execute(
                    "SELECT 1 FROM drill_results WHERE extractor_version IS NULL LIMIT 1").fetchone():
                conn.execute("DELETE FROM drill_results" + (" WHERE extractor_version IS NULL"
                                                            if "extractor_version" in cols else ""))
                print("[drill_publish] removed rows written by the legacy reader (no fallback after the switch)")
        except Exception as exc2:  # noqa: BLE001
            print(f"[drill_publish] could not clear legacy rows: {exc2}")
        return 1


# ------------------------------------------------------------------ self-tests
def _selftest():
    bad = 0

    def ok(name, cond):
        nonlocal bad
        bad += not cond
        print(("  ok    " if cond else "  FAIL  ") + name)

    def iv(seq, g, u, m, l, ok_=True, incl=False, hole=None):
        rows = [("iv_grade", seq, g, None, u, m), ("iv_length_m", seq, l, None, "m", None),
                ("iv_ok", seq, 1.0 if ok_ else 0.0, None, None, None), ("iv_src", seq, None, "text", None, None)]
        if incl:
            rows.append(("iv_including", seq, 1.0, None, None, None))
        if hole:
            rows.append(("iv_hole", seq, None, hole, None, None))
        return rows

    def rec(is_result, best, *ivs, project="P"):
        rows = [("is_result", 0, 1.0 if is_result else 0.0, None, None, None), ("project", 0, None, project, None, None)]
        if best is not None:
            rows.append(("best_seq", 0, float(best), None, None, None))
        for x in ivs:
            rows += x
        return parse_facts(rows)

    ev = lambda eid, tk, pub: {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": "H " + eid}
    items = [
        (ev("e1", "AAA", "2026-01-01"), rec(True, 0, iv(0, 5.0, "g/t", "Au", 10.0, hole="H-1"), iv(1, 20.0, "g/t", "Au", 1.0, incl=True))),
        (ev("e2", "AAA", "2026-02-01"), rec(True, 0, iv(0, 5.0, "g/t", "Au", 10.0), iv(1, 2.0, "g/t", "Au", 30.0, hole="H-2"))),
        (ev("e3", "AAA", "2026-03-01"), rec(True, 0, iv(0, 5.0, "g/t", "Au", 10.0))),
        (ev("e4", "BBB", "2026-01-15"), rec(False, None, iv(0, 1.0, "%", "Cu", 5.0, ok_=False))),
        (ev("e5", "BBB", "2026-01-20"), rec(True, 0, iv(0, 0.355, "%", "Ni", 7.0))),
        (ev("e0", "CCC", "2025-12-01"), rec(True, None, iv(0, 1.0, "g/t", "Au", 2.0, ok_=False))),
    ]
    rows, ivs, st = compute(items)
    byid = {r["event_id"]: r for r in rows}
    ok("published e1, e2, e5", sorted(byid) == ["e1", "e2", "e5"])
    ok("e3 is a recap of e1", st["recap"] == 1)
    ok("e4 not a result, e0 no accepted interval", st["not_result"] == 1 and st["no_accepted_interval"] == 1)
    ok("e1 best is seq 0 with its hole", byid["e1"]["top_grade"] == 5.0 and byid["e1"]["top_hole_id"] == "H-1")
    ok("e2 best replaced by its fresh interval", byid["e2"]["top_grade"] == 2.0 and byid["e2"]["top_length_m"] == 30.0)
    ok("e2 keeps both intervals, one marked reported before",
       sorted((x["seq"], x["reported_before"]) for x in ivs if x["event_id"] == "e2") == [(0, 1), (1, 0)])
    ok("including flag carried", [x["including"] for x in ivs if x["event_id"] == "e1"] == [0, 1])
    ok("one best per release", all(sum(x["is_best"] for x in ivs if x["event_id"] == e) == 1 for e in byid))
    ok("summary keeps three decimals below 1", byid["e5"]["top_summary"] == "0.355% Ni / 7m")
    ok("summary g/t", summary(13.53, "g/t", "Au", 13.4) == "13.53 g/t Au / 13.4m")
    ok("summary large grade", summary(1841.14, "g/t", "Ag", 16.8) == "1841.1 g/t Ag / 16.8m")

    # the database path, end to end, on an in-memory store
    from portal import facts as F
    conn = F.connect(":memory:")
    F.ensure_schema(conn)
    conn.execute("CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, published_at TEXT, raw_headline TEXT, "
                 "raw_body TEXT, categories TEXT, review_status TEXT)")
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO drill_results(event_id, ticker, top_summary) VALUES ('old1','AAA','legacy row')")
    F.register_version(conn, EXTRACTOR, "1.0.0", "drill_result", TAG)
    def ext(hl, body):
        if "none" in hl:
            return []
        fs = [F.Fact("is_result", value_num=1.0), F.Fact("project", value_text="Proj"), F.Fact("best_seq", value_num=0.0),
              F.Fact("iv_grade", value_num=3.0, unit="g/t", metal="Au"), F.Fact("iv_length_m", value_num=4.0, unit="m"),
              F.Fact("iv_ok", value_num=1.0), F.Fact("iv_hole", value_text="DH-1")]
        return [F.Record("drill_result", facts=fs)]
    spec = F.ExtractorSpec(EXTRACTOR, "1.0.0", "drill_result", TAG, ext)
    for i, (hl, cats) in enumerate([("drill a", "Drill Results"), ("drill b", "Drill Results|Financings"),
                                    ("drill untagged", "Financings"), ("none", "Drill Results")]):
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)", (f"x{i}", f"T{i}", f"2026-01-0{i + 1}", hl, "body",
                                                                  cats, "auto_approved"))
    F.run_batch(conn, spec, F.pending_events(conn, EXTRACTOR, "1.0.0"))
    ok("no active version yet", active_version(conn) is None)
    F.activate(conn, EXTRACTOR, "1.0.0")
    st = publish(conn, "1.0.0", log=lambda s: None)
    got = [r[0] for r in conn.execute("SELECT event_id FROM drill_results ORDER BY event_id")]
    ok("publish writes tagged results only, legacy row gone", got == ["x0", "x1"])
    ok("intervals written", conn.execute("SELECT COUNT(*) FROM drill_intervals").fetchone()[0] == 2)
    ok("extractor_version stamped", [tuple(r) for r in conn.execute("SELECT DISTINCT extractor_version FROM drill_results")] == [("1.0.0",)])
    ok("summary row", tuple(conn.execute("SELECT top_summary, top_hole_id FROM drill_results WHERE event_id='x0'").fetchone())
       == ("3 g/t Au / 4m", "DH-1"))
    ok("publish is repeatable", publish(conn, "1.0.0", log=lambda s: None)["published"] == 2)
    print(f"failures: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
