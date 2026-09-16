"""Accuracy sets, evaluation and the auto-install gate (ACCURACY_V1, 2026-09-16).
Phase 2 of the revised plan (claude/MNT_INGESTION_PIPELINE_PLAN_REVISED_2026-09-16.md).

An ACCURACY SET is a JSON file in accuracy/sets/<name>.json: about 50 releases
for one tag, each with what a careful reader says the release contains. Claude
drafts the labels from the release text; Justin reviews every item (decision
2026-09-16: all 50, not a sample). Until every item is reviewed the set can be
measured against, but it cannot gate an install.

    {"schema": 1, "name": "drill_results", "tag": "Drill Results",
     "status": "draft" | "confirmed", "reviewer": "...", "reviewed_at": "...",
     "items": [{"n": 0, "event_id": "...", "ticker": "...", "body_sha1": "...",
                "review": "draft" | "confirmed" | "corrected" | "excluded",
                "expect": {...tag-specific...}, "note": "..."}]}

body_sha1 is facts.text_sha1(headline, body). If the release text changes
(re-ingest, repair), the item is STALE and is left out of the numbers.

PRECISION IS PER KEY FIELD (decision 2026-09-16). Each tag names its key
fields; a spec's judge() turns one prediction and one expectation into
outcomes per field: "tp" (claimed and right), "fp" (claimed and wrong), "fn"
(not claimed, should have been). precision = tp / (tp + fp) is the gate;
recall = tp / (tp + fn) and whole-row accuracy are reported, never gated.

THE GATE (plan, "Auto-install gate"). All must pass:
  1. the set is fully reviewed and has >= MIN_ITEMS scorable items
  2. self-tests pass
  3. every key field: >= MIN_CLAIMS claims and precision >= THRESHOLD (90%)
  4. no page loses more than MAX_ROW_LOSS (2%) of its rows
  5. every page returns 200

Self-tests: python3 -m portal.accuracy   (in-memory; touches nothing live)
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from portal import normalize as N

SCHEMA = 1
THRESHOLD = 0.90
MAX_ROW_LOSS = 0.02
MIN_ITEMS = 40
MIN_CLAIMS = 10
REVIEWED = ("confirmed", "corrected")
EXCLUDED = "excluded"
REVIEW_STATES = ("draft",) + REVIEWED + (EXCLUDED,)
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETS_DIR = os.path.join(APP_DIR, "accuracy", "sets")
PORTAL_URL = "http://127.0.0.1:8001"

EVAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS fx_eval_runs (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    set_name    TEXT NOT NULL,
    subject     TEXT NOT NULL,      -- 'stored:drill_results' or 'fx:<extractor>@<version>'
    set_sha     TEXT NOT NULL,
    set_usable  INTEGER NOT NULL,
    purpose     TEXT NOT NULL,      -- 'measure' | 'gate'
    passed      INTEGER,            -- gate outcome; NULL for a measurement
    run_at      TEXT NOT NULL DEFAULT (datetime('now')),
    summary     TEXT NOT NULL,      -- one line per key field
    report      TEXT NOT NULL       -- full JSON
);
CREATE INDEX IF NOT EXISTS ix_fx_eval_runs_set ON fx_eval_runs(set_name, run_at);
"""


class AccuracyError(ValueError):
    pass


def text_sha1(headline, body):
    """Identical to facts.text_sha1 (self-tested), repeated so this module imports without facts."""
    h = hashlib.sha1()
    h.update((headline or "").encode("utf-8"))
    h.update(bytes([0]))
    h.update((body or "").encode("utf-8"))
    return h.hexdigest()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ sets
def set_path(name):
    if not re.match("^[a-z][a-z0-9_]{0,62}$", name or ""):
        raise AccuracyError(f"bad set name {name!r}")
    return os.path.join(SETS_DIR, name + ".json")


def load_set(name_or_path):
    path = name_or_path if name_or_path.endswith(".json") else set_path(name_or_path)
    with open(path, encoding="utf-8") as fh:
        aset = json.load(fh)
    problems = validate_set(aset)
    if problems:
        raise AccuracyError(f"{path}: " + "; ".join(problems[:5]))
    return aset


def validate_set(aset):
    p = []
    if aset.get("schema") != SCHEMA:
        p.append(f"schema is {aset.get('schema')!r}, expected {SCHEMA}")
    for k in ("name", "tag", "status", "items"):
        if k not in aset:
            p.append(f"missing {k}")
    if aset.get("status") not in ("draft", "confirmed"):
        p.append(f"bad status {aset.get('status')!r}")
    seen = set()
    for i, it in enumerate(aset.get("items") or []):
        for k in ("event_id", "body_sha1", "review", "expect"):
            if k not in it:
                p.append(f"item {i}: missing {k}")
        if it.get("review") not in REVIEW_STATES:
            p.append(f"item {i}: bad review {it.get('review')!r}")
        if it.get("event_id") in seen:
            p.append(f"item {i}: duplicate event {it.get('event_id')}")
        seen.add(it.get("event_id"))
    return p


def set_sha(aset):
    return hashlib.sha256(json.dumps(aset, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def set_usable(aset):
    """(usable_for_gate, reasons). Usable = confirmed, every item reviewed, enough items left."""
    reasons = []
    items = aset.get("items") or []
    if aset.get("status") != "confirmed":
        reasons.append(f"set status is {aset.get('status')!r}, not 'confirmed'")
    draft = [it.get("n", i) for i, it in enumerate(items) if it.get("review") == "draft"]
    if draft:
        reasons.append(f"{len(draft)} item(s) not reviewed yet")
    kept = [it for it in items if it.get("review") != EXCLUDED]
    if len(kept) < MIN_ITEMS:
        reasons.append(f"{len(kept)} items after exclusions; need {MIN_ITEMS}")
    return (not reasons), reasons


# ------------------------------------------------------------------ specs
@dataclass
class TagSpec:
    """How to score one tag.

    judge(pred, expect) -> {field: ["tp" | "fp" | "fn", ...]} for every field in
    key_fields + report_fields (an empty list means "nothing to score here").
    stored(conn, event_id) -> pred or None: what a legacy table shows today.
    from_records(records) -> pred or None: the same shape from facts Records."""
    name: str
    tag: str
    key_fields: tuple
    judge: object
    report_fields: tuple = ()
    stored: object = None
    from_records: object = None
    describe: dict = field(default_factory=dict)


SPECS = {}


def register_spec(spec):
    SPECS[spec.name] = spec
    return spec


def _ratio(a, b):
    return round(a / b, 4) if b else None


# ------------------------------------------------------------------ evaluation
def evaluate(spec, aset, predict, events):
    """Score predict(item, event) against every non-excluded item.

    events: {event_id: {"raw_headline", "raw_body", ...}} for the set's items.
    Returns a JSON-able report. Never raises for a bad prediction: an exception
    from predict is recorded as an error and scored as no prediction."""
    fields = tuple(spec.key_fields) + tuple(spec.report_fields)
    tally = {f: {"tp": 0, "fp": 0, "fn": 0} for f in fields}
    rep = {"set": aset["name"], "tag": aset["tag"], "set_sha": set_sha(aset), "spec": spec.name,
           "generated_at": _now(), "n_items": 0, "n_scored": 0, "n_excluded": 0, "n_stale": 0,
           "n_missing": 0, "n_errors": 0, "whole_row": {}, "fields": {}, "mistakes": [], "stale": []}
    rows_ok = 0
    for it in aset["items"]:
        rep["n_items"] += 1
        if it["review"] == EXCLUDED:
            rep["n_excluded"] += 1
            continue
        ev = events.get(it["event_id"])
        if ev is None:
            rep["n_missing"] += 1
            continue
        if text_sha1(ev["raw_headline"], ev["raw_body"]) != it["body_sha1"]:
            rep["n_stale"] += 1
            rep["stale"].append(it.get("n"))
            continue
        try:
            pred = predict(it, ev)
            err = None
        except Exception as e:  # noqa: BLE001  (a broken extractor is a result, not a crash)
            pred, err = None, f"{type(e).__name__}: {e}"
            rep["n_errors"] += 1
        out = spec.judge(pred, it["expect"])
        rep["n_scored"] += 1
        row_ok = True
        for f in fields:
            for o in out.get(f, []):
                tally[f][o] += 1
                if o != "tp":
                    if f in spec.key_fields:
                        row_ok = False
                    rep["mistakes"].append({"n": it.get("n"), "event_id": it["event_id"], "ticker": it.get("ticker"),
                                            "field": f, "outcome": o, "predicted": pred, "error": err,
                                            "review": it["review"]})
        rows_ok += 1 if row_ok else 0
    for f in fields:
        t = tally[f]
        rep["fields"][f] = dict(t, key=f in spec.key_fields, claims=t["tp"] + t["fp"],
                                precision=_ratio(t["tp"], t["tp"] + t["fp"]),
                                recall=_ratio(t["tp"], t["tp"] + t["fn"]),
                                describe=spec.describe.get(f, ""))
    rep["whole_row"] = {"correct": rows_ok, "scored": rep["n_scored"], "rate": _ratio(rows_ok, rep["n_scored"])}
    usable, reasons = set_usable(aset)
    rep["set_usable"] = usable
    rep["set_unusable_reasons"] = reasons
    return rep


def summary_lines(rep):
    out = []
    for f, d in rep["fields"].items():
        p = "n/a" if d["precision"] is None else f"{d['precision'] * 100:.1f}%"
        r = "n/a" if d["recall"] is None else f"{d['recall'] * 100:.1f}%"
        out.append(f"{f}{' (key)' if d['key'] else ''}: precision {p} ({d['tp']}/{d['claims']}), recall {r}")
    w = rep["whole_row"]
    out.append(f"whole row: {w['correct']}/{w['scored']}; stale {rep['n_stale']}, missing {rep['n_missing']}, "
               f"errors {rep['n_errors']}, excluded {rep['n_excluded']}")
    return out


def load_events(conn, aset):
    ids = [it["event_id"] for it in aset["items"]]
    got = {}
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        for r in conn.execute("SELECT event_id, ticker, published_at, raw_headline, raw_body, categories FROM events "
                              "WHERE event_id IN (%s)" % ",".join("?" * len(chunk)), chunk):
            got[r[0]] = {"event_id": r[0], "ticker": r[1], "published_at": r[2], "raw_headline": r[3],
                         "raw_body": r[4], "categories": r[5]}
    return got


def stored_predictor(spec, conn):
    if spec.stored is None:
        raise AccuracyError(f"spec {spec.name} has no stored() reader")
    return lambda it, ev: spec.stored(conn, it["event_id"])


def extractor_predictor(spec, extractor_spec):
    """For facts-store extractors: run the pure extract() in memory. Writes nothing."""
    if spec.from_records is None:
        raise AccuracyError(f"spec {spec.name} has no from_records() adapter")
    return lambda it, ev: spec.from_records(extractor_spec.extract(ev["raw_headline"] or "", ev["raw_body"] or ""))


# ------------------------------------------------------------------ site checks
# Page key (portal.pages.MNT_NAV) -> SQL returning that page's row count. Pages that
# list tagged releases count the tag; data pages count their table. v_fx_* views
# are added automatically. A query that errors is recorded as None, not a crash.
PAGE_SOURCES = {
    "drills": "SELECT COUNT(*) FROM drill_results",
    "resources": "SELECT COUNT(*) FROM resource_estimates",
    "financings": "SELECT COUNT(*) FROM financings",
    "management": "SELECT COUNT(*) FROM management_changes",
}


def page_row_counts(conn):
    counts = {}
    for key, sql in PAGE_SOURCES.items():
        try:
            counts[key] = conn.execute(sql).fetchone()[0]
        except sqlite3.Error:
            counts[key] = None
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='view' AND name LIKE 'v_fx_%'").fetchall():
        try:
            counts[name] = conn.execute(f"SELECT COUNT(*) FROM {name} WHERE tag_confirmed=1").fetchone()[0]
        except sqlite3.Error:
            counts[name] = None
    return counts


def nav_hrefs():
    from portal import pages
    hrefs = ["/"]
    for g in pages.MNT_NAV:
        for p in g.get("pages", []):
            if p.get("href") and p["href"] not in hrefs:
                hrefs.append(p["href"])
    return hrefs


def page_statuses(base=PORTAL_URL, hrefs=None, timeout=30):
    out = {}
    for h in hrefs if hrefs is not None else nav_hrefs():
        req = urllib.request.Request(base + h, headers={"User-Agent": "mnt-accuracy-gate"})
        try:
            class _NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *a, **k):
                    return None
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
                out[h] = r.status
        except urllib.error.HTTPError as e:
            out[h] = e.code
        except Exception as e:  # noqa: BLE001
            out[h] = f"{type(e).__name__}"
    return out


# ------------------------------------------------------------------ the gate
def gate_checks(rep, *, selftest_ok, rows_before, rows_after, pages):
    """The five checks, each {name, passed, detail}. passed = all passed."""
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    add("set reviewed", rep["set_usable"], "ok" if rep["set_usable"] else "; ".join(rep["set_unusable_reasons"]))
    add("enough items", rep["n_scored"] >= MIN_ITEMS, f"{rep['n_scored']} scored (stale {rep['n_stale']}, "
        f"missing {rep['n_missing']}); need {MIN_ITEMS}")
    add("self-tests", selftest_ok, "passed" if selftest_ok else "failed")
    for f, d in rep["fields"].items():
        if not d["key"]:
            continue
        ok = d["claims"] >= MIN_CLAIMS and d["precision"] is not None and d["precision"] >= THRESHOLD
        p = "n/a" if d["precision"] is None else f"{d['precision'] * 100:.1f}%"
        add(f"precision: {f}", ok, f"{p} on {d['claims']} claims; need {THRESHOLD * 100:.0f}% on {MIN_CLAIMS}+")
    lost = []
    for k, before in rows_before.items():
        after = rows_after.get(k)
        if before is None:
            continue
        if after is None:
            lost.append(f"{k}: {before} -> unreadable")
        elif before > 0 and (before - after) / before > MAX_ROW_LOSS:
            lost.append(f"{k}: {before} -> {after} (-{(before - after) / before * 100:.1f}%)")
    add("no page loses >2% of rows", not lost, "; ".join(lost) if lost else f"{len(rows_before)} pages checked")
    bad = {h: s for h, s in pages.items() if s != 200}
    add("every page returns 200", pages and not bad, f"{len(pages)} pages" if not bad else json.dumps(bad))
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


def ensure_eval_schema(conn):
    conn.executescript(EVAL_SCHEMA)


def record_run(conn, rep, subject, purpose, passed=None):
    """One short autocommit insert. Returns run_id."""
    ensure_eval_schema(conn)
    cur = conn.execute("INSERT INTO fx_eval_runs(set_name, subject, set_sha, set_usable, purpose, passed, summary, report) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       (rep["set"], subject, rep["set_sha"], 1 if rep["set_usable"] else 0, purpose,
                        None if passed is None else (1 if passed else 0), chr(10).join(summary_lines(rep)),
                        json.dumps(rep, default=str)))
    return cur.lastrowid


def gate_and_activate(conn, facts, tagspec, extractor_spec, aset, *, selftest_ok, base=PORTAL_URL, hrefs=None,
                      log=print):
    """The auto-install step for a facts-store extractor whose candidate version is
    already backfilled. Evaluates in memory, checks the site, activates, re-checks,
    and undoes the activation if the site got worse. Returns the gate result."""
    name, version = extractor_spec.name, extractor_spec.version
    st = facts.version_status(conn, name, version)
    if st not in ("candidate", "retired"):
        raise AccuracyError(f"{name} {version} is {st!r}; only a candidate or retired version can be gated")
    if facts.pending_events(conn, name, version, limit=1):
        raise AccuracyError(f"{name} {version} is not fully backfilled; run facts_sync.py --backfill {name} first")
    rep = evaluate(tagspec, aset, extractor_predictor(tagspec, extractor_spec), load_events(conn, aset))
    rows_before = page_row_counts(conn)
    pages_before = page_statuses(base, hrefs)
    pre = gate_checks(rep, selftest_ok=selftest_ok, rows_before=rows_before, rows_after=rows_before, pages=pages_before)
    subject = f"fx:{name}@{version}"
    if not pre["passed"]:
        rep["gate"] = dict(pre, stage="before activation")
        record_run(conn, rep, subject, "gate", passed=False)
        log(f"[gate] {subject}: NOT installed; " + "; ".join(c["name"] for c in pre["checks"] if not c["passed"]))
        return rep["gate"]
    prev = facts.activate(conn, name, version, gate_report={"summary": summary_lines(rep), "set_sha": rep["set_sha"]})
    rows_after = page_row_counts(conn)
    pages_after = page_statuses(base, hrefs)
    post = gate_checks(rep, selftest_ok=selftest_ok, rows_before=rows_before, rows_after=rows_after, pages=pages_after)
    if not post["passed"]:
        if prev:
            facts.activate(conn, name, prev)
        else:
            conn.execute("UPDATE fx_extractor_versions SET status='candidate', activated_at=NULL "
                         "WHERE extractor=? AND version=?", (name, version))
        post["undone"] = f"re-activated {prev}" if prev else "returned to candidate"
    rep["gate"] = dict(post, stage="after activation", previous=prev, rows_before=rows_before, rows_after=rows_after)
    record_run(conn, rep, subject, "gate", passed=post["passed"])
    log(f"[gate] {subject}: {'INSTALLED' if post['passed'] else 'undone: ' + post['undone']}")
    return rep["gate"]


# ------------------------------------------------------------------ Drill Results
_HOLE_STRIP = re.compile("[^A-Z0-9]")
_WORD = re.compile("[a-z0-9]+")
PROJECT_STOPWORDS = {"the", "of", "at", "its", "on", "in", "and", "project", "projects", "property", "properties",
                     "deposit", "prospect", "mine", "claims", "district", "area", "company"}
PROJECT_GENERIC = {"high", "grade", "gold", "silver", "copper", "nickel", "zinc", "lead", "lithium", "uranium",
                   "antimony", "palladium", "platinum", "polymetallic", "porphyry", "vms", "epithermal", "base",
                   "metals", "metal", "rare", "earth", "earths", "potash", "graphite", "tungsten", "cobalt", "north",
                   "south", "east", "west", "main", "zone", "trend", "belt", "new"}


def _hole(s):
    return _HOLE_STRIP.sub("", (s or "").upper()) or None


def _words(s):
    return {w for w in _WORD.findall((s or "").lower()) if w not in PROJECT_STOPWORDS}


def project_matches(pred, accepted):
    """A predicted project is right if it names an accepted project and adds at most
    one unrelated word ("Columba High-Grade Silver" for Columba: yes; "Offering for
    exploration on its Bald Hill Antimony" for Bald Hill: no)."""
    pw = _words(pred)
    if not pw:
        return False
    for name in accepted or []:
        gw = _words(name)
        if not gw:
            continue
        if gw <= pw and len(pw - gw - PROJECT_GENERIC) <= 1:
            return True
        if pw <= gw and len(pw - PROJECT_GENERIC) >= 1:
            return True
    return False


def metal_key(token):
    """Canonical metal for comparison: "gold" -> Au, "PGM+Au" -> PGM+Au, unknown -> upper-cased token."""
    t = (token or "").strip()
    if not t:
        return None
    return N.metal(t) or "+".join(N.metals(t)) or re.sub("[^A-Za-z0-9+]", "", t).upper() or None


def grade_matches(p_grade, p_unit, p_metal, g):
    """Same metal (canonical), same grade in ppm within 1.5% or one rounding step."""
    if p_grade is None or g.get("grade") is None:
        return False
    pm, gm = metal_key(p_metal), metal_key(g.get("metal"))
    if pm is None or pm != gm:
        return False
    pu, gu = N.grade_unit(p_unit or ""), N.grade_unit(g.get("unit") or "")
    if pu is None or gu is None:
        return False
    a, b = N.grade_to_ppm(float(p_grade), pu), N.grade_to_ppm(float(g["grade"]), gu)
    if a is None or b is None:
        return False
    step = 0.0051 * N.TO_PPM[gu]
    return abs(a - b) <= max(0.015 * max(abs(a), abs(b)), step)


def length_matches(p_len, g_len):
    if p_len is None or g_len is None:
        return False
    return abs(float(p_len) - float(g_len)) <= max(0.015 * float(g_len), 0.051)


def judge_drill(pred, expect):
    """pred: None or {project, hole, grade, unit, metal, length_m, n_intercepts}
    expect: {is_result, intercepts: [{hole, length_m, alt_lengths?, grade, unit, metal}], projects: [..]}
    alt_lengths: other lengths the release itself states for the same interval (a headline
    rounding, or true width beside drilled length); either is accepted.

    row        a row exists (tp) for a release that reports new drill results
    intercept  the row's headline intercept (grade, unit, metal AND length) is one
               of the release's new intercepts
    hole       the hole shown is the hole of that intercept
    project    the project shown names the release's project"""
    out = {"row": [], "intercept": [], "hole": [], "project": []}
    is_result = bool(expect.get("is_result"))
    gold = expect.get("intercepts") or []
    projects = expect.get("projects") or []
    if pred is None:
        if is_result:
            out["row"].append("fn")
            if gold:
                out["intercept"].append("fn")
        return out
    out["row"].append("tp" if is_result else "fp")
    if pred.get("grade") is not None:
        if not is_result:
            out["intercept"].append("fp")
        else:
            same_grade = [g for g in gold if grade_matches(pred["grade"], pred.get("unit"), pred.get("metal"), g)]
            full = [g for g in same_grade if any(length_matches(pred.get("length_m"), x)
                                                 for x in [g.get("length_m")] + list(g.get("alt_lengths") or []))]
            out["intercept"].append("tp" if full else "fp")
            if pred.get("hole"):
                cands = [g for g in (full or same_grade) if g.get("hole")]
                if cands:
                    ok = any(_hole(g["hole"]) == _hole(pred["hole"]) for g in cands)
                else:
                    ok = _hole(pred["hole"]) in {_hole(g.get("hole")) for g in gold if g.get("hole")}
                out["hole"].append("tp" if ok else "fp")
    if pred.get("project"):
        out["project"].append("tp" if project_matches(pred["project"], projects) else "fp")
    elif is_result and projects:
        out["project"].append("fn")
    return out


def stored_drill(conn, event_id):
    r = conn.execute("SELECT project, top_hole_id, top_grade, top_unit, top_metal, top_length_m, n_intercepts "
                     "FROM drill_results WHERE event_id=?", (event_id,)).fetchone()
    if r is None:
        return None
    return {"project": r[0], "hole": r[1], "grade": r[2], "unit": r[3], "metal": r[4], "length_m": r[5],
            "n_intercepts": r[6]}


register_spec(TagSpec(
    name="drill_results", tag="Drill Results", key_fields=("row", "intercept", "hole", "project"),
    judge=judge_drill, stored=stored_drill,
    describe={"row": "a row is shown only for releases reporting new drill results",
              "intercept": "the headline intercept (grade, metal, length) is a real new intercept from the release",
              "hole": "the hole shown is the hole that intercept came from",
              "project": "the project shown is the release's project"}))


# ------------------------------------------------------------------ self-tests
def _selftest():
    import tempfile
    results = []

    def ok(name, cond):
        results.append((name, bool(cond)))

    def eq(name, got, want):
        results.append((name, got == want))
        if got != want:
            print(f"  FAIL {name}: got {got!r}, want {want!r}")

    try:
        from portal import facts as F
        ok("text_sha1 identical to facts", text_sha1("h", "b") == F.text_sha1("h", "b"))
    except ImportError:
        ok("text_sha1 stable", text_sha1("h", "b") == text_sha1("h", "b"))

    # project matching
    ok("project exact", project_matches("Columba", ["Columba"]))
    ok("project plus generic words", project_matches("Columba High-Grade Silver", ["Columba"]))
    ok("project 'Project' suffix", project_matches("Fondaway Canyon Project", ["Fondaway Canyon"]))
    ok("project shorter name", project_matches("Sela Creek", ["Sela Creek Gold Project"]))
    ok("project fragment refused", not project_matches("Offering for exploration on its Bald Hill Antimony", ["Bald Hill"]))
    ok("project other name refused", not project_matches("Pilar", ["Goldfields"]))
    ok("project empty refused", not project_matches("", ["X"]))
    ok("project generic-only refused", not project_matches("Gold", ["Gold Creek"]))
    ok("project any accepted name", project_matches("North Fork Zone", ["Fondaway Canyon", "North Fork"]))

    # grade and length matching
    g = {"grade": 8.8, "unit": "g/t", "metal": "Au", "length_m": 8.1, "hole": "FCG22-01"}
    ok("grade equal", grade_matches(8.8, "g/t", "Au", g))
    ok("grade gold name", grade_matches(8.80, "gpt", "gold", g))
    ok("grade rounding step", grade_matches(8.795, "g/t", "Au", g))
    ok("grade wrong metal", not grade_matches(8.8, "g/t", "Ag", g))
    ok("grade wrong value", not grade_matches(3.0, "g/t", "Au", g))
    ok("grade eq is not metal", not grade_matches(8.8, "g/t", "AuEq", g))
    ok("grade ppm vs g/t", grade_matches(8800, "ppb", "Au", g))
    ok("grade pct vs g/t mismatch", not grade_matches(8.8, "%", "Au", g))
    ok("grade pct small rounding", grade_matches(0.81, "%", "Cu", {"grade": 0.81, "unit": "%", "metal": "Cu"}))
    ok("length equal", length_matches(8.1, 8.1))
    ok("length feet converted", length_matches(82.3, 82.296))
    ok("length wrong", not length_matches(59.3, 8.1))
    ok("metal unknown never matches unknown", not grade_matches(1.0, "g/t", "", {"grade": 1.0, "unit": "g/t", "metal": ""}))
    ok("metal compound", grade_matches(2.1, "g/t", "PGM+Au", {"grade": 2.1, "unit": "g/t", "metal": "PGM+Au"}))
    ok("metal odd tokens differ", not grade_matches(2.1, "%", "KCl", {"grade": 2.1, "unit": "%", "metal": "K2O"}))
    ok("metal odd tokens same", grade_matches(2.1, "%", "MoS2Eq", {"grade": 2.1, "unit": "%", "metal": "MoS2 Eq"}))

    # judge
    exp = {"is_result": True, "projects": ["Fondaway Canyon"], "intercepts": [
        {"hole": "FCG22-01", "grade": 8.8, "unit": "g/t", "metal": "Au", "length_m": 8.1},
        {"hole": "FCG22-01", "grade": 3.0, "unit": "g/t", "metal": "Au", "length_m": 59.3}]}
    good = {"project": "Fondaway Canyon", "hole": "FCG-22-01", "grade": 3.0, "unit": "g/t", "metal": "Au", "length_m": 59.3}
    eq("judge all right", judge_drill(good, exp), {"row": ["tp"], "intercept": ["tp"], "hole": ["tp"], "project": ["tp"]})
    eq("judge length paired wrong", judge_drill(dict(good, length_m=8.1), exp)["intercept"], ["fp"])
    exp_alt = dict(exp, intercepts=[dict(exp["intercepts"][1], length_m=56.6, alt_lengths=[59.3])])
    eq("judge alt length accepted", judge_drill(good, exp_alt)["intercept"], ["tp"])
    eq("judge wrong hole", judge_drill(dict(good, hole="FCG22-09"), exp)["hole"], ["fp"])
    eq("judge no hole shown", judge_drill(dict(good, hole=None), exp)["hole"], [])
    eq("judge missing row", judge_drill(None, exp), {"row": ["fn"], "intercept": ["fn"], "hole": [], "project": []})
    eq("judge row on non-result", judge_drill(good, {"is_result": False, "intercepts": [], "projects": ["Fondaway Canyon"]}),
       {"row": ["fp"], "intercept": ["fp"], "hole": [], "project": ["tp"]})
    eq("judge correct silence", judge_drill(None, {"is_result": False}), {"row": [], "intercept": [], "hole": [], "project": []})
    eq("judge project fragment", judge_drill(dict(good, project="Offering for exploration on its Fondaway"), exp)["project"], ["fp"])
    eq("judge project missing", judge_drill(dict(good, project=None), exp)["project"], ["fn"])

    # sets
    def item(n, eid, body, expect, review="confirmed"):
        return {"n": n, "event_id": eid, "ticker": "T.V", "body_sha1": text_sha1("H" + eid, body),
                "review": review, "expect": expect}
    events = {}
    items = []
    for n in range(45):
        eid = f"e{n}"
        body = f"body {n}"
        events[eid] = {"raw_headline": "H" + eid, "raw_body": body}
        items.append(item(n, eid, body, exp if n < 40 else {"is_result": False}))
    aset = {"schema": 1, "name": "drill_results", "tag": "Drill Results", "status": "confirmed", "items": items}
    eq("validate ok", validate_set(aset), [])
    ok("validate catches duplicate", validate_set(dict(aset, items=items + [items[0]])))
    eq("usable", set_usable(aset), (True, []))
    d = dict(aset, status="draft", items=[dict(items[0], review="draft")] + items[1:])
    u = set_usable(d)
    ok("unusable when draft", not u[0] and len(u[1]) == 2)
    few = dict(aset, items=[dict(it, review="excluded") if it["n"] < 10 else it for it in items])
    ok("unusable when too few after exclusions", not set_usable(few)[0])
    ok("set_sha changes with content", set_sha(aset) != set_sha(d))

    # evaluate: 40 result items predicted right, 5 non-results with one false row; one stale; one broken
    events["e3"] = dict(events["e3"], raw_body="re-ingested text")

    def predict(it, ev):
        if it["n"] == 7:
            raise RuntimeError("boom")
        if it["n"] == 41:
            return good
        return good if it["expect"].get("is_result") else None
    rep = evaluate(SPECS["drill_results"], aset, predict, events)
    eq("eval scored", rep["n_scored"], 44)
    eq("eval stale", (rep["n_stale"], rep["stale"]), (1, [3]))
    eq("eval errors", rep["n_errors"], 1)
    eq("eval row counts", {k: rep["fields"]["row"][k] for k in ("tp", "fp", "fn")}, {"tp": 38, "fp": 1, "fn": 1})
    eq("eval row precision", rep["fields"]["row"]["precision"], round(38 / 39, 4))
    eq("eval intercept fp from false row", rep["fields"]["intercept"]["fp"], 1)
    eq("eval whole row", rep["whole_row"]["correct"], 42)
    ok("eval mistakes carry item", any(m["n"] == 7 and m["error"] for m in rep["mistakes"]))
    ok("eval json-able", json.dumps(rep))
    ok("summary lines", len(summary_lines(rep)) == 5 and "precision" in summary_lines(rep)[0])

    # gate
    rows = {"drills": 100, "resources": 50}
    pages200 = {"/": 200, "/drills": 200}
    g1 = gate_checks(rep, selftest_ok=True, rows_before=rows, rows_after=rows, pages=pages200)
    ok("gate passes", g1["passed"])
    eq("gate check count", len(g1["checks"]), 9)
    ok("gate fails on 500", not gate_checks(rep, selftest_ok=True, rows_before=rows, rows_after=rows,
                                            pages={"/": 200, "/drills": 500})["passed"])
    ok("gate fails on no pages", not gate_checks(rep, selftest_ok=True, rows_before=rows, rows_after=rows, pages={})["passed"])
    ok("gate allows 2% loss", gate_checks(rep, selftest_ok=True, rows_before=rows, rows_after={"drills": 98, "resources": 50},
                                          pages=pages200)["passed"])
    ok("gate fails on 3% loss", not gate_checks(rep, selftest_ok=True, rows_before=rows,
                                                rows_after={"drills": 97, "resources": 50}, pages=pages200)["passed"])
    ok("gate fails on unreadable page", not gate_checks(rep, selftest_ok=True, rows_before=rows,
                                                        rows_after={"drills": None, "resources": 50}, pages=pages200)["passed"])
    ok("gate allows a new page", gate_checks(rep, selftest_ok=True, rows_before=rows,
                                             rows_after=dict(rows, v_fx_x=5), pages=pages200)["passed"])
    ok("gate fails on selftest", not gate_checks(rep, selftest_ok=False, rows_before=rows, rows_after=rows, pages=pages200)["passed"])
    rep_draft = evaluate(SPECS["drill_results"], d, predict, events)
    ok("gate fails on draft set", not gate_checks(rep_draft, selftest_ok=True, rows_before=rows, rows_after=rows,
                                                  pages=pages200)["passed"])

    def predict_bad_project(it, ev):
        return dict(good, project="Offering for exploration") if it["expect"].get("is_result") else None
    rep_bad = evaluate(SPECS["drill_results"], aset, predict_bad_project, events)
    gb = gate_checks(rep_bad, selftest_ok=True, rows_before=rows, rows_after=rows, pages=pages200)
    ok("gate fails on one key field", not gb["passed"] and [c["name"] for c in gb["checks"] if not c["passed"]] == ["precision: project"])
    few_claims = dict(rep, fields=dict(rep["fields"], hole=dict(rep["fields"]["hole"], claims=3, tp=3, fp=0, precision=1.0)))
    ok("gate fails on too few claims", not gate_checks(few_claims, selftest_ok=True, rows_before=rows, rows_after=rows,
                                                       pages=pages200)["passed"])

    # database: row counts, stored reader, record_run, gate_and_activate with the real facts module
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute("CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, published_at TEXT, raw_headline TEXT, "
                 "raw_body TEXT, categories TEXT, review_status TEXT)")
    conn.execute("CREATE TABLE drill_results (event_id TEXT, project TEXT, top_hole_id TEXT, top_grade REAL, top_unit TEXT, "
                 "top_metal TEXT, top_length_m REAL, n_intercepts INTEGER)")
    conn.execute("INSERT INTO drill_results VALUES ('e1','Fondaway Canyon','FCG22-01',3.0,'g/t','Au',59.3,4)")
    eq("stored reader", stored_drill(conn, "e1")["length_m"], 59.3)
    eq("stored reader none", stored_drill(conn, "zz"), None)
    rc = page_row_counts(conn)
    eq("row counts", (rc["drills"], rc["resources"]), (1, None))
    rid = record_run(conn, rep, "stored:drill_results", "measure")
    eq("record_run", conn.execute("SELECT set_name, purpose, passed FROM fx_eval_runs WHERE run_id=?", (rid,)).fetchone(),
       ("drill_results", "measure", None))

    try:
        from portal import facts as F
    except ImportError:
        F = None
    if F is not None:
        c2 = F.connect(":memory:")
        c2.execute("CREATE TABLE events (event_id TEXT PRIMARY KEY, ticker TEXT, published_at TEXT, raw_headline TEXT, "
                   "raw_body TEXT, categories TEXT, review_status TEXT)")
        F.ensure_schema(c2)
        for eid, ev in events.items():
            c2.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)", (eid, "T.V", "2026-09-01", ev["raw_headline"],
                                                                     ev["raw_body"], "Drill Results", "auto_approved"))

        def demo_extract(headline, body):
            n = int(headline[2:])
            if n >= 40:
                return []
            return [F.Record("demo", facts=[F.Fact("grade", value_num=3.0, unit="g/t", metal="Au")])]

        def from_records(recs):
            if not recs:
                return None
            return dict(good)
        spec_demo = TagSpec(name="demo_set", tag="Drill Results", key_fields=("row", "intercept", "hole", "project"),
                            judge=judge_drill, from_records=from_records)
        ex = F.ExtractorSpec("demo_ex", "1.0.0", "demo", "Drill Results", demo_extract, "sha1")
        F.register_version(c2, "demo_ex", "1.0.0", "demo", "Drill Results", "sha1")
        aset2 = dict(aset, name="demo_set")
        try:
            gate_and_activate(c2, F, spec_demo, ex, aset2, selftest_ok=True, hrefs=[], log=lambda *_: None)
            ok("gate refuses before backfill", False)
        except AccuracyError:
            ok("gate refuses before backfill", True)
        F.run_batch(c2, ex, F.pending_events(c2, "demo_ex", "1.0.0", limit=1000))
        PAGE_SOURCES_SAVED = dict(PAGE_SOURCES)
        PAGE_SOURCES.clear()
        global page_statuses
        real_ps = page_statuses
        try:
            page_statuses = lambda base=None, hrefs=None, timeout=30: {"/": 200}  # noqa: E731
            r1 = gate_and_activate(c2, F, spec_demo, ex, aset2, selftest_ok=True, log=lambda *_: None)
            ok("gate installs", r1["passed"] and F.active_version(c2, "demo_ex") == "1.0.0")
            ok("gate recorded", c2.execute("SELECT passed FROM fx_eval_runs WHERE purpose='gate'").fetchone()[0] == 1)
            try:
                gate_and_activate(c2, F, spec_demo, ex, aset2, selftest_ok=True, log=lambda *_: None)
                ok("gate refuses active version", False)
            except AccuracyError:
                ok("gate refuses active version", True)
            # second version: site breaks after activation -> undone, first version back
            ex2 = F.ExtractorSpec("demo_ex", "1.0.1", "demo", "Drill Results", demo_extract, "sha2")
            F.register_version(c2, "demo_ex", "1.0.1", "demo", "Drill Results", "sha2")
            F.run_batch(c2, ex2, F.pending_events(c2, "demo_ex", "1.0.1", limit=1000))
            calls = {"n": 0}

            def flaky(base=None, hrefs=None, timeout=30):
                calls["n"] += 1
                return {"/": 200} if calls["n"] == 1 else {"/": 500}
            page_statuses = flaky
            r2 = gate_and_activate(c2, F, spec_demo, ex2, aset2, selftest_ok=True, log=lambda *_: None)
            ok("gate undoes on broken page", not r2["passed"] and F.active_version(c2, "demo_ex") == "1.0.0"
               and "re-activated 1.0.0" in r2["undone"])
            # third version: precision fails -> never activated
            ex3 = F.ExtractorSpec("demo_ex", "1.0.2", "demo", "Drill Results", demo_extract, "sha3")
            F.register_version(c2, "demo_ex", "1.0.2", "demo", "Drill Results", "sha3")
            F.run_batch(c2, ex3, F.pending_events(c2, "demo_ex", "1.0.2", limit=1000))
            spec_bad = TagSpec(name="demo_set", tag="Drill Results", key_fields=("row", "intercept", "hole", "project"),
                               judge=judge_drill, from_records=lambda recs: dict(good, grade=99.0) if recs else None)
            page_statuses = lambda base=None, hrefs=None, timeout=30: {"/": 200}  # noqa: E731
            r3 = gate_and_activate(c2, F, spec_bad, ex3, aset2, selftest_ok=True, log=lambda *_: None)
            ok("gate blocks low precision", not r3["passed"] and r3["stage"] == "before activation"
               and F.version_status(c2, "demo_ex", "1.0.2") == "candidate")
            # first-ever version failing after activation returns to candidate
            ex4 = F.ExtractorSpec("other_ex", "1.0.0", "demo", "Drill Results", demo_extract, "sha4")
            F.register_version(c2, "other_ex", "1.0.0", "demo", "Drill Results", "sha4")
            F.run_batch(c2, ex4, F.pending_events(c2, "other_ex", "1.0.0", limit=1000))
            calls["n"] = 0
            page_statuses = flaky
            r4 = gate_and_activate(c2, F, spec_demo, ex4, aset2, selftest_ok=True, log=lambda *_: None)
            ok("gate returns first version to candidate", not r4["passed"]
               and F.version_status(c2, "other_ex", "1.0.0") == "candidate")
        finally:
            page_statuses = real_ps
            PAGE_SOURCES.update(PAGE_SOURCES_SAVED)

    # page_statuses against a real local server
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            code = {"/": 200, "/bad": 500, "/moved": 302}.get(self.path, 404)
            self.send_response(code)
            if code == 302:
                self.send_header("Location", "/")
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    eq("page statuses", page_statuses(base, ["/", "/bad", "/moved", "/nope"]),
       {"/": 200, "/bad": 500, "/moved": 302, "/nope": 404})
    srv.shutdown()
    ok("sets dir under app", SETS_DIR.endswith(os.path.join("accuracy", "sets")) and tempfile is not None)

    failed = [n for n, good_ in results if not good_]
    for n in failed:
        print("  FAIL", n)
    print(f"accuracy selftest: {len(results) - len(failed)}/{len(results)} passed")
    return not failed


if __name__ == "__main__":
    import sys
    sys.exit(0 if _selftest() else 1)
