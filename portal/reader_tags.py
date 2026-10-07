#!/usr/bin/env python3
"""READER_TAGS_V1 (2026-09-30): a reader's own finds can give a release its tag.

The keyword tagger (portal.categorize) misses many releases a reader should show: the ACC150 check measured tag
coverage from 21% (Royalties) to 92% (Financings). Each reader already reads every release, so when the active reader
found something in a release that lacks its tag, an outside-tag ADMISSION RULE decides whether that find is the
release's own news (not an About paragraph, a restated result, someone else's project...). Admitted releases get the
reader's tag in events.categories, so the page, the home-page chips and the API all see it.

Each rule lives in portal/reader_admit/admit_<extractor>.py and defines admit(headline, text, categories, out) ->
(bool, reason), where text is the body with the boilerplate tail cut (cut() below), categories the release's tags and
out the reader's own output (portal.accuracy SPECS[extractor].from_records on the stored records). A rule only runs
when enabled in reader_tag_rules with the sha256 of the file it was measured with: an edited rule file is skipped until
it is re-measured and re-enabled. Rules and measurements: claude/MNT_READER_TAGGING_*_2026-09-30.md.

Tables (created here):
  reader_tag_rules(extractor PK, tag, rule_sha, status 'active'|'off', enabled_at, note)
  reader_tag_decisions(event_id, extractor, version, rule_sha, admit, reason, decided_at) -- one per rule run
  reader_tags(event_id, tag PK pair, extractor, version, rule_sha, reason, status 'active'|'dropped'|'revoked',
              before_categories, after_categories, added_at, ended_at)

Every run (a step in sync_structured.py right after facts_sync, before the publishers):
  1. for each enabled reader, decide the releases with a substantive find that lack the tag (or carry it only
     through this module) and have no decision for the current (version, rule_sha); store the decisions;
  2. admitted releases get a reader_tags row; rows whose release is no longer admitted (new version or rule) are
     'dropped' and the tag is taken off again where the tagger had not put it there;
  3. re-assert: every active row's release carries the tag (re-ingest recomputes categories). Adding keeps the
     CATEGORIES order and drops 'Corporate Updates' when it was the only other tag (TAGFIX v18 precedent).
Updates are compare-and-set on events.categories, in batches.

Kill switch: MNT_READER_TAGS_OFF=1 in the environment, or a file portal/reader_admit/OFF: the step does nothing and
tags already added stay. Undo: `python -m portal.reader_tags revoke <extractor>|all` sets the rule off, marks its rows
'revoked' and restores each release's categories (only where they are still what this module set, else it just removes
the tag if the tagger had not put it there). `status` prints counts. Fails soft: any error is printed, exit 0.
"""
import hashlib, importlib.util, json, os, re, sqlite3, sys, time, traceback

APP = "/opt/mnt/app"
DB = os.path.join(APP, "portal", "portal.db")
ADMIT_DIR = os.path.join(APP, "portal", "reader_admit")
OFF_FILE = os.path.join(ADMIT_DIR, "OFF")
BATCH = 300
CORP = "Corporate Updates"
TRIVIAL = ("reason", "iv_ok", "iv_reason", "iv_rule", "iv_src")
CAP = 15000
TAIL = re.compile(r"\n\s*(About [A-Z0-9]|ABOUT [A-Z0-9]|Forward[- ][Ll]ooking|FORWARD[- ]LOOKING|Cautionary [Nn]ote|"
                  r"CAUTIONARY|Neither (the )?TSX|NEITHER (THE )?TSX|Neither the Canadian Securities Exchange)")

SCHEMA = """
CREATE TABLE IF NOT EXISTS reader_tag_rules (
    extractor TEXT PRIMARY KEY, tag TEXT NOT NULL, rule_sha TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
    enabled_at TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS reader_tag_decisions (
    event_id TEXT NOT NULL, extractor TEXT NOT NULL, version TEXT NOT NULL, rule_sha TEXT NOT NULL,
    admit INTEGER NOT NULL, reason TEXT, decided_at TEXT,
    PRIMARY KEY (event_id, extractor, version, rule_sha));
CREATE TABLE IF NOT EXISTS reader_tags (
    event_id TEXT NOT NULL, tag TEXT NOT NULL, extractor TEXT NOT NULL, version TEXT, rule_sha TEXT, reason TEXT,
    status TEXT NOT NULL DEFAULT 'active', before_categories TEXT, after_categories TEXT, added_at TEXT, ended_at TEXT,
    PRIMARY KEY (event_id, tag));
CREATE INDEX IF NOT EXISTS ix_reader_tags_status ON reader_tags(status, extractor);
"""


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def cut(body):
    """The body as the rules were measured on: boilerplate tail (About / forward-looking...) cut, capped."""
    b = body or ""
    m = TAIL.search(b, 1200)
    return (b[:m.start()] if m else b)[:CAP]


def has_rows(x):
    """True when the reader's page output holds at least one row (same test as the accuracy scorer)."""
    if not x:
        return False
    if isinstance(x, dict):
        for k in ("rows", "changes", "intercepts"):
            if k in x:
                return bool(x[k])
        flags = [v for k, v in x.items() if k.startswith("is_")]
        return bool(flags[0]) if flags else True
    return bool(x)


def split(cats):
    return [c for c in (cats or "").split("|") if c]


def order():
    try:
        from portal.categorize import CATEGORIES
        return list(CATEGORIES)
    except Exception:  # noqa: BLE001
        return []


def with_tag(cats, tag, order_):
    """categories string with tag added (CATEGORIES order; unknown tags keep their place at the end);
    'Corporate Updates' goes when it was the only other tag."""
    cur = split(cats)
    if tag in cur:
        return cats
    new = [c for c in cur if c != CORP] + [tag]
    rank = {c: i for i, c in enumerate(order_)}
    new.sort(key=lambda c: rank.get(c, len(rank)))
    return "|".join(new)


def without_tag(cats, tag):
    cur = [c for c in split(cats) if c != tag]
    return "|".join(cur) if cur else CORP


def off():
    return os.environ.get("MNT_READER_TAGS_OFF") == "1" or os.path.exists(OFF_FILE)


def rule_file(extractor):
    return os.path.join(ADMIT_DIR, "admit_%s.py" % extractor)


def file_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def load_rule(extractor):
    path = rule_file(extractor)
    spec = importlib.util.spec_from_file_location("reader_admit_%s" % extractor, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ensure_schema(conn):
    conn.executescript(SCHEMA)


def cas(conn, event_id, old, new):
    """compare-and-set events.categories; True when written."""
    cur = conn.execute("UPDATE events SET categories=? WHERE event_id=? AND COALESCE(categories,'')=?",
                       (new, event_id, old or ""))
    return cur.rowcount == 1


def decide(conn, A, extractor, version, rule_sha, tag, mod, log):
    """Step 1: decisions for releases with a substantive find, no tag, and no decision for (version, rule_sha)."""
    spec = A.SPECS[extractor]
    q = ("SELECT DISTINCT r.event_id FROM fx_records r JOIN events e ON e.event_id=r.event_id "
         "WHERE r.extractor=? AND r.version=? AND e.review_status='auto_approved' "
         "AND (('|' || COALESCE(e.categories,'') || '|') NOT LIKE ? OR EXISTS (SELECT 1 FROM reader_tags g "
         "WHERE g.event_id=r.event_id AND g.tag=? AND g.status='active')) "
         "AND EXISTS (SELECT 1 FROM fx_facts f WHERE f.record_id=r.record_id AND f.field NOT LIKE 'is_%%' "
         "AND f.field NOT IN (%s)) "
         "AND NOT EXISTS (SELECT 1 FROM reader_tag_decisions d WHERE d.event_id=r.event_id AND d.extractor=? "
         "AND d.version=? AND d.rule_sha=?)" % ",".join("?" * len(TRIVIAL)))
    todo = [r[0] for r in conn.execute(q, (extractor, version, "%|" + tag + "|%", tag) + TRIVIAL
                                       + (extractor, version, rule_sha)).fetchall()]
    n_yes = errs = 0
    for k in range(0, len(todo), BATCH):
        rows = []
        for e in todo[k:k + BATCH]:
            h, b, cats = conn.execute("SELECT raw_headline, COALESCE(raw_body,''), COALESCE(categories,'') "
                                      "FROM events WHERE event_id=?", (e,)).fetchone()
            try:
                out = spec.from_records(A.records_from_store(conn, extractor, version, e))
                # rules were measured on releases without the tag: never show them the tag this module added
                if not has_rows(out):
                    ok, why = False, "reader output has no row"
                else:
                    ok, why = mod.admit(h or "", cut(b), [c for c in split(cats) if c != tag], out)
                    ok = bool(ok)
            except Exception as x:  # noqa: BLE001  a rule error rejects the release, never breaks the run
                ok, why = False, "error: %s" % type(x).__name__
                errs += 1
            n_yes += ok
            rows.append((e, extractor, version, rule_sha, 1 if ok else 0, (why or "")[:120], now()))
        conn.executemany("INSERT OR REPLACE INTO reader_tag_decisions VALUES (?,?,?,?,?,?,?)", rows)
        conn.commit()
    log("[reader_tags] %s %s: decided %d, admitted %d, rule errors %d" % (extractor, version, len(todo), n_yes, errs))
    return len(todo), n_yes


def settle(conn, extractor, version, rule_sha, tag, log):
    """Step 2: admitted -> active row; active rows no longer admitted -> dropped (tag taken off)."""
    t = now()
    new = conn.execute(
        "SELECT d.event_id, d.reason, COALESCE(e.categories,'') FROM reader_tag_decisions d JOIN events e "
        "ON e.event_id=d.event_id WHERE d.extractor=? AND d.version=? AND d.rule_sha=? AND d.admit=1 "
        "AND NOT EXISTS (SELECT 1 FROM reader_tags g WHERE g.event_id=d.event_id AND g.tag=? AND g.status='active')",
        (extractor, version, rule_sha, tag)).fetchall()
    conn.executemany(
        "INSERT OR REPLACE INTO reader_tags(event_id, tag, extractor, version, rule_sha, reason, status, "
        "before_categories, after_categories, added_at, ended_at) VALUES (?,?,?,?,?,?,'active',?,NULL,?,NULL)",
        [(e, tag, extractor, version, rule_sha, why, cats, t) for e, why, cats in new])
    # an active row whose release has a current decision of 'no' (new version or rule): drop it
    gone = conn.execute(
        "SELECT g.event_id FROM reader_tags g JOIN reader_tag_decisions d ON d.event_id=g.event_id "
        "AND d.extractor=g.extractor AND d.version=? AND d.rule_sha=? WHERE g.extractor=? AND g.tag=? "
        "AND g.status='active' AND d.admit=0", (version, rule_sha, extractor, tag)).fetchall()
    # an active row whose release has no decision at all for the current (version, rule): the reader no longer
    # finds anything there (every tagged-by-us release is re-decided in step 1)
    gone += conn.execute(
        "SELECT g.event_id FROM reader_tags g WHERE g.extractor=? AND g.tag=? AND g.status='active' AND NOT EXISTS "
        "(SELECT 1 FROM reader_tag_decisions d WHERE d.event_id=g.event_id AND d.extractor=g.extractor "
        "AND d.version=? AND d.rule_sha=?)", (extractor, tag, version, rule_sha)).fetchall()
    n_drop = sum(untag(conn, e, tag, "dropped") for (e,) in gone)
    conn.commit()
    log("[reader_tags] %s: new rows %d, dropped %d" % (extractor, len(new), n_drop))


def untag(conn, event_id, tag, status):
    row = conn.execute("SELECT before_categories, after_categories FROM reader_tags WHERE event_id=? AND tag=?",
                       (event_id, tag)).fetchone()
    cur = conn.execute("SELECT COALESCE(categories,'') FROM events WHERE event_id=?", (event_id,)).fetchone()
    if row and cur:
        before, after = row
        others = conn.execute("SELECT COUNT(*) FROM reader_tags WHERE event_id=? AND tag<>? AND status='active'",
                              (event_id, tag)).fetchone()[0]
        if tag not in split(before) and tag in split(cur[0]):
            # restore the exact pre-tag categories only when nothing else of ours is on the release
            target = before if (after is not None and cur[0] == after and not others) else without_tag(cur[0], tag)
            cas(conn, event_id, cur[0], target)
    conn.execute("UPDATE reader_tags SET status=?, ended_at=? WHERE event_id=? AND tag=?",
                 (status, now(), event_id, tag))
    return 1


def reassert(conn, log):
    """Step 3: every active row's release carries its tag."""
    order_ = order()
    rows = conn.execute("SELECT g.event_id, g.tag FROM reader_tags g JOIN events e "
                        "ON e.event_id=g.event_id WHERE g.status='active' "
                        "AND ('|' || COALESCE(e.categories,'') || '|') NOT LIKE ('%|' || g.tag || '|%')").fetchall()
    n = 0
    for k in range(0, len(rows), BATCH):
        for e, tag in rows[k:k + BATCH]:
            # read fresh: an earlier row in this loop may have tagged the same release
            cats = conn.execute("SELECT COALESCE(categories,'') FROM events WHERE event_id=?", (e,)).fetchone()[0]
            new = with_tag(cats, tag, order_)
            if cas(conn, e, cats, new):
                conn.execute("UPDATE reader_tags SET after_categories=? WHERE event_id=? AND tag=?", (new, e, tag))
                n += 1
        conn.commit()
    log("[reader_tags] re-asserted %d of %d" % (n, len(rows)))
    return n


def run(conn=None, log=print):
    if off():
        log("[reader_tags] off (kill switch)")
        return
    own = conn is None
    conn = conn or sqlite3.connect(DB, timeout=120)
    try:
        ensure_schema(conn)
        sys.path.insert(0, APP)
        import portal.accuracy as A
        act = dict(conn.execute("SELECT extractor, version FROM fx_extractor_versions WHERE status='active'"))
        for extractor, tag, rule_sha in conn.execute(
                "SELECT extractor, tag, rule_sha FROM reader_tag_rules WHERE status='active' ORDER BY extractor").fetchall():
            try:
                if extractor not in act or extractor not in A.SPECS:
                    log("[reader_tags] %s: no active version, skipped" % extractor)
                    continue
                if file_sha(rule_file(extractor)) != rule_sha:
                    log("[reader_tags] %s: rule file changed since it was measured, skipped" % extractor)
                    continue
                if A.SPECS[extractor].tag != tag:
                    log("[reader_tags] %s: tag mismatch, skipped" % extractor)
                    continue
                mod = load_rule(extractor)
                decide(conn, A, extractor, act[extractor], rule_sha, tag, mod, log)
                settle(conn, extractor, act[extractor], rule_sha, tag, log)
            except Exception:  # noqa: BLE001
                conn.rollback()
                log("[reader_tags] %s failed:\n%s" % (extractor, traceback.format_exc(limit=3)))
        reassert(conn, log)
    finally:
        if own:
            conn.close()


def enable(conn, extractor, note=""):
    """Installer use: turn a measured rule on (its file must already be in portal/reader_admit/)."""
    import portal.accuracy as A
    ensure_schema(conn)
    conn.execute("INSERT OR REPLACE INTO reader_tag_rules VALUES (?,?,?,'active',?,?)",
                 (extractor, A.SPECS[extractor].tag, file_sha(rule_file(extractor)), now(), note))
    conn.commit()


def revoke(conn, which):
    ensure_schema(conn)
    exts = [r[0] for r in conn.execute("SELECT extractor FROM reader_tag_rules")] if which == "all" else [which]
    n = 0
    for ex in exts:
        conn.execute("UPDATE reader_tag_rules SET status='off' WHERE extractor=?", (ex,))
        for e, tag in conn.execute("SELECT event_id, tag FROM reader_tags WHERE extractor=? AND status='active'",
                                   (ex,)).fetchall():
            n += untag(conn, e, tag, "revoked")
        conn.commit()
    print("[reader_tags] revoked %d rows for %s" % (n, ",".join(exts)))


def status(conn):
    ensure_schema(conn)
    for r in conn.execute("SELECT extractor, tag, rule_sha, status, enabled_at FROM reader_tag_rules ORDER BY 1"):
        print("rule", r)
    for r in conn.execute("SELECT extractor, status, COUNT(*) FROM reader_tags GROUP BY 1, 2 ORDER BY 1, 2"):
        print("tags", r)
    for r in conn.execute("SELECT extractor, version, rule_sha, SUM(admit), COUNT(*) FROM reader_tag_decisions "
                          "GROUP BY 1, 2, 3 ORDER BY 1"):
        print("decisions", r)


def selftest():
    o = ["Financings", "Drill Results", "Royalties & Streams", "Property Options & Staking", CORP]
    assert with_tag("Property Options & Staking", "Royalties & Streams", o) == "Royalties & Streams|Property Options & Staking"
    assert with_tag(CORP, "Drill Results", o) == "Drill Results"
    assert with_tag("", "Drill Results", o) == "Drill Results"
    assert with_tag("Drill Results", "Drill Results", o) == "Drill Results"
    assert with_tag("Zeta|" + CORP + "|Financings", "Drill Results", o) == "Financings|Drill Results|Zeta"
    assert without_tag("Drill Results", "Drill Results") == CORP
    assert without_tag("Financings|Drill Results", "Drill Results") == "Financings"
    assert cut("x" * 1300 + "\nAbout Foo Corp\nboiler") == "x" * 1300
    assert not has_rows({"rows": []}) and has_rows({"rows": [1]}) and not has_rows(None) and not has_rows({"is_x": False})
    # a full cycle on an in-memory database
    conn = sqlite3.connect(":memory:")
    ensure_schema(conn)
    conn.execute("CREATE TABLE events(event_id TEXT, categories TEXT)")
    conn.execute("INSERT INTO events VALUES ('e1', ?)", (CORP,))
    conn.execute("INSERT INTO reader_tags(event_id, tag, extractor, status, before_categories, added_at) "
                 "VALUES ('e1', 'Drill Results', 'drill_results', 'active', ?, 'now')", (CORP,))
    global order
    keep = order
    order = lambda: o  # noqa: E731
    try:
        reassert(conn, lambda *_: None)
        assert conn.execute("SELECT categories FROM events").fetchone()[0] == "Drill Results"
        untag(conn, "e1", "Drill Results", "revoked")
        assert conn.execute("SELECT categories FROM events").fetchone()[0] == CORP
        assert conn.execute("SELECT status FROM reader_tags").fetchone()[0] == "revoked"
    finally:
        order = keep
    print("reader_tags selftest ok")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    try:
        if cmd == "selftest":
            selftest()
        elif cmd == "run":
            run()
        else:
            sys.path.insert(0, APP)
            c = sqlite3.connect(DB, timeout=120)
            if cmd == "status":
                status(c)
            elif cmd == "revoke":
                revoke(c, sys.argv[2])
            elif cmd == "enable":
                enable(c, sys.argv[2], " ".join(sys.argv[3:]))
                status(c)
            c.close()
    except Exception:  # noqa: BLE001  never break sync_structured
        traceback.print_exc()
    sys.exit(0)
