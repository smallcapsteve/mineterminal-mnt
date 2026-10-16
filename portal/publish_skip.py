"""OPTD step B (2026-10-06, approved by Justin): skip a publisher when nothing it reads has changed.

mnt-structured-sync runs 14 publishers every 30 minutes. Each one reads its reader's results (fx_runs /
fx_records), the matching events and a few lookup tables, recomputes its whole table and then finds that
nothing changed - about 15 minutes and 6-7 CPU minutes a run, mostly for nothing.

Before each publisher, before(label) takes a fingerprint of everything that publisher reads:
  - its reader's versions (fx_extractor_versions) and, for the active/candidate versions, every fx_runs row
    (count, latest ran_at, totals) and the fx_records keys (count, latest record_id, sum - index only);
  - the events (ticker, dates, slug, categories, review status - one index-only scan per run, all events);
  - any lookup tables / files it reads (READS / FILES / FILE_PARTS below, found by tracing each publisher on a copy);
  - the code (size + mtime of every .py and data file under /opt/mnt/app/portal, plus sync_structured.py);
  - today's UTC date;
  - and the publisher's own output tables as they are now (row count, rowid range and sum), so a table changed
    by anyone else is rebuilt.
If the fingerprint matches the one taken before the last successful run AND that full run was less than
FULL_EVERY_H (8) hours ago, the publisher is skipped. Otherwise it runs as before and after() stores the new
fingerprint. Any error here means "run it" - this can make the sync do less, never publish something wrong.

MEMSWAP narrow check (2026-10-15, Justin: "Reader: publish only what changed"). The check above treats ANY new
release as a change for all 14 publishers, because every reader stores a record for every release it reads (a
marker when it finds nothing) and the events digest covers every release. So in the daytime every publisher ran
every time. The narrow check asks instead: since this publisher's last successful run, did anything arrive that it
can actually use? It passes (= nothing relevant) only when ALL of these hold:
  - versions, code, date, lookup files and the publisher's own output tables are unchanged (as above);
  - no reader run turned into an error (fx_runs errors count unchanged);
  - every fx_records row added since the last run is NEW (record count grew by exactly the number of new rows,
    so nothing was deleted or re-read), and each of them carries its reader's found-flag set to 0 (NOTHING_FLAG,
    v2 2026-10-16; v1 required "no facts at all", which never held), and none of their releases
    carries this reader's tag (fx_extractor_versions.tag) - i.e. the reader found nothing in them and they would
    not even become a marker row;
  - the events digest, with those new releases left out, equals the digest taken before the last run - so no
    existing release was edited (categories, review status, ticker, slug, dates).
Publishers read only the releases their reader found something in plus those carrying their tag (traced in
permits_publish.load_items and its siblings), so a release failing all three tests cannot change their output.
SHADOW first: with narrow_shadow on, the publisher still runs exactly as before; after it runs we record whether its
output tables changed. A run where the narrow check said "nothing relevant" but the table changed is a MISS (the
narrow check would have been wrong) and is logged as such. Only with narrow_ON present does the narrow check skip.
  /opt/mnt/app/portal/publish_skip_narrow_ON   exists -> narrow check decides (skips for real)
  shadow log: /var/lib/mnt-publish-skip/narrow_shadow.log (one JSON line per publisher per run)
The 8-hour full rebuild and every switch above still apply on top.

Switches (no restart needed, read every run):
  /opt/mnt/app/portal/publish_skip_OFF   exists -> never skip (everything runs as before)
  /opt/mnt/app/portal/publish_skip_ONLY  exists -> only the labels listed in it (one per line) may be skipped
State: /var/lib/mnt-publish-skip/state.json (delete it to force every publisher to run once).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
import time

APP = "/opt/mnt/app"
DB = os.environ.get("MNT_PUBLISH_SKIP_DB", APP + "/portal/portal.db")
CODE_ROOT = os.environ.get("MNT_PUBLISH_SKIP_APP", APP)
STATE = os.environ.get("MNT_PUBLISH_SKIP_STATE", "/var/lib/mnt-publish-skip/state.json")
OFF_FILE = os.path.join(CODE_ROOT, "portal", "publish_skip_OFF")
ONLY_FILE = os.path.join(CODE_ROOT, "portal", "publish_skip_ONLY")
NARROW_ON_FILE = os.path.join(CODE_ROOT, "portal", "publish_skip_narrow_ON")
SHADOW_LOG = os.environ.get("MNT_PUBLISH_SKIP_SHADOW", os.path.join(os.path.dirname(STATE), "narrow_shadow.log"))
FULL_EVERY_H = float(os.environ.get("MNT_PUBLISH_FULL_EVERY_H", "8"))

# label (as printed by sync_structured) -> reader name in fx_*, output tables
MAP = {
    "drill_results":       ("drill_results", ["drill_results", "drill_intervals"]),
    "financings":          ("financings",  ["financings", "financing_events"]),
    "management_changes":  ("management",  ["management_changes"]),
    "resource_estimates":  ("resources",   ["resource_estimates"]),
    "economic_studies":    ("economics",   ["economic_studies"]),
    "production_results":  ("production",  ["production_results"]),
    "royalty_deals":       ("royalties",   ["royalty_deals"]),
    "exploration_programs": ("exploration", ["exploration_programs"]),
    "technical_reports":   ("technical",   ["technical_reports"]),
    "permits":             ("permits",     ["permits"]),
    "land_deals":          ("options",     ["land_deals"]),
    "debt_deals":          ("debt",        ["debt_deals"]),
    "mine_dev_events":     ("mine_dev",    ["mine_dev_events"]),
    "sampling_results":    ("sampling",    ["sampling_results"]),
}
READS = {}          # label -> other tables the publisher reads
COMMON_FILES = []
FILES = {}
# label -> (name, function(path) -> fingerprint) for files a publisher reads only part of.
# economics reads tickers.json only through economics_publish.company_names() (ticker -> company name, previous
# tickers included). The scrapers rewrite that file several times an hour for other fields, so fingerprint just
# the names it uses (checked 2026-10-06, relay task-20261006-220000-econtk1; Justin: "Yes, narrow it").
FILE_PARTS = {"economic_studies": [(APP + "/tickers.json", "names")]}
# Event columns the publishers read, taken from the covering index ix_events_list so the check never reads the
# release text (categories / slug sit after raw_body / raw_html in the row). raw_headline is not in that index;
# it is set when a release is stored and the 8-hour full rebuild covers a later edit.
EVENT_COLS = "event_id, review_status, ticker, published_at, classified_at, categories, slug, additional_tickers"
EVENT_INDEX = "ix_events_list"
CODE_EXT = (".py", ".json", ".txt", ".tsv", ".csv", ".yaml", ".yml")
# Web-only modules no publisher imports (traced on the copy 2026-10-06: the publishers load portal/db.py, facts.py,
# rowsync.py, the extractors and their helpers, never app.py or a *_api.py). They change often; leaving them out
# keeps a page edit from forcing all 14 publishers to rebuild.
CODE_SKIP = ("app.py",)
CODE_SKIP_SUFFIX = ("_api.py",)
# MEMSWAP narrow v2 (2026-10-16): every reader stores a record for every release it reads, and the record for a
# release where it found nothing still carries facts: its found-flag set to 0 and a "reason" (probe 6 on the newest
# ~220 records per reader: e.g. permits is_permit=0 on 203 of 206 unpublished, 0 of 18 published). So "a new record
# has facts" (v1) was true for every release and the shadow never said skip. v2: a new record is nothing-found only
# when its reader's flag below is present and exactly 0. Readers with no such flag (drill_results: its unpublished
# records still carry interval facts) always count new records as relevant.
NOTHING_FLAG = {
    "debt": "is_debt", "economics": "is_economic_study", "exploration": "is_program", "financings": "is_financing",
    "management": "is_management_change", "mine_dev": "is_event", "options": "is_deal", "permits": "is_permit",
    "production": "is_production", "resources": "is_resource_estimate", "royalties": "is_royalty",
    "sampling": "is_result", "technical": "is_report",
}
# inputs the narrow check compares exactly (the broad ones - events, runs:, records: - it replaces)
_NARROW_EXACT = ("code", "date", "versions")


def _log(msg):
    print("[publish_skip] " + msg, flush=True)


def _h():
    return hashlib.blake2b(digest_size=16)


def _feed(h, rows):
    n = 0
    for r in rows:
        h.update(repr(tuple(r)).encode("utf-8", "surrogatepass"))
        h.update(b"\x1e")
        n += 1
    return n


def _conn():
    c = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=30)
    c.execute("PRAGMA query_only=1")
    c.execute("PRAGMA busy_timeout=30000")
    return c


def _cols(c, table):
    return [r[1] for r in c.execute("PRAGMA table_info(%s)" % table)]


def _table_digest(c, table):
    h = _h()
    cols = _cols(c, table)
    if not cols:
        return "missing"
    n = _feed(h, c.execute("SELECT * FROM %s ORDER BY %s" % (table, ", ".join(cols))))
    return "%d:%s" % (n, h.hexdigest())


def _table_fp(c, table):
    """Cheap fingerprint of an output table: row count and rowid range / sum. Only its publisher writes the table and
    rowsync replaces a changed row (delete + insert, new rowid), so this moves whenever the table changes.
    WITHOUT ROWID tables (drill_intervals): row count only."""
    try:
        return repr(tuple(c.execute("SELECT count(*), max(rowid), total(rowid) FROM %s" % table).fetchone()))
    except sqlite3.OperationalError:
        return repr(tuple(c.execute("SELECT count(*) FROM %s" % table).fetchone()))


def _code_fp():
    h = _h()
    roots = [os.path.join(CODE_ROOT, "portal")]
    for root in roots:
        for d, dirs, files in os.walk(root):
            dirs[:] = sorted(x for x in dirs if x != "__pycache__" and not x.startswith("."))
            for f in sorted(files):
                if not f.endswith(CODE_EXT) or ".bak" in f or f in CODE_SKIP or f.endswith(CODE_SKIP_SUFFIX):
                    continue
                st = os.stat(os.path.join(d, f))
                h.update(("%s|%d|%d\n" % (os.path.relpath(os.path.join(d, f), root), st.st_size, st.st_mtime_ns)).encode())
    for f in ("sync_structured.py",):          # the publishers import nothing else from the top level
        st = os.stat(os.path.join(CODE_ROOT, f))
        h.update(("top/%s|%d|%d\n" % (f, st.st_size, st.st_mtime_ns)).encode())
    return h.hexdigest()


def _file_sha(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:16]
    except OSError:
        return "missing"


def _names_fp(path):
    """Digest of economics_publish.company_names(path) - the only part of tickers.json economics uses. Falls back
    to the whole file's sha if that function cannot be loaded (then economics simply runs more often)."""
    try:
        from portal.economics_publish import company_names
    except Exception:  # noqa: BLE001
        return "file:" + _file_sha(path)
    if not os.path.exists(path):
        return "missing"
    h = _h()
    n = _feed(h, sorted(company_names(path).items()))
    return "names:%d:%s" % (n, h.hexdigest())


_PART_FNS = {"names": _names_fp}


def _inputs(c, label, code_fp):
    ex, _tables = MAP[label]
    parts = {"code": code_fp, "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")}
    vers = c.execute("SELECT version, status FROM fx_extractor_versions WHERE extractor=? ORDER BY version",
                     (ex,)).fetchall()
    vers = [tuple(r) for r in vers]
    parts["versions"] = repr(vers)
    live = [v for v, s in vers if s in ("active", "candidate")]
    if not live:
        raise LookupError("no active version for reader %r" % ex)   # -> run it
    parts["events"] = _events_fp(c)
    for v in live:
        # fx_runs: aggregates over the primary-key range (a re-read sets ran_at to now, so max(ran_at) moves)
        parts["runs:" + v] = repr(tuple(c.execute(
            "SELECT count(*), max(ran_at), total(n_records), total(tag_confirmed), sum(status != 'ok') "
            "FROM fx_runs WHERE extractor=? AND version=?", (ex, v)).fetchone()))
        # fx_records keys: aggregates over the covering unique index (extractor, version, event_id, ordinal)
        parts["records:" + v] = repr(tuple(c.execute(
            "SELECT count(*), max(record_id), total(record_id) FROM fx_records "
            "WHERE extractor=? AND version=?", (ex, v)).fetchone()))
    for t in READS.get(label, ()):
        parts["read:" + t] = _table_digest(c, t)
    for f in COMMON_FILES + FILES.get(label, []):
        parts["file:" + f] = _file_sha(f)
    for f, kind in FILE_PARTS.get(label, ()):
        parts["%s:%s" % (kind, f)] = _PART_FNS[kind](f)
    return parts


def _outputs(c, label):
    return {t: _table_fp(c, t) for t in MAP[label][1]}


def _load_state():
    try:
        with open(STATE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(st, fh, indent=1, sort_keys=True)
    os.replace(tmp, STATE)


_CODE = {}


def _events_fp(c, exclude=None):
    """One digest of the event columns publishers read, from one index-only scan per sync run (cached). It covers
    all events, not only those a reader has read: every reader reads every release, so in practice a new release
    changes every reader's fx_runs anyway, and the skip pays off in the quiet hours when nothing changes at all.
    With exclude (a set of event_ids): the same digest with those releases left out (narrow check), cached per set."""
    key = "events" if not exclude else ("events-x", frozenset(exclude))
    if key not in _CODE:
        h = _h()
        n = 0
        for r in c.execute("SELECT %s FROM events INDEXED BY %s" % (EVENT_COLS, EVENT_INDEX)):
            if exclude and r[0] in exclude:
                continue
            h.update(repr(tuple(r)).encode("utf-8", "surrogatepass"))
            h.update(b"\x1e")
            n += 1
        _CODE[key] = "%d:%s" % (n, h.hexdigest())
    return _CODE[key]


# ------------------------------------------------------------------ MEMSWAP narrow check
def _tag_of(c, ex):
    r = c.execute("SELECT tag FROM fx_extractor_versions WHERE extractor=? AND status='active'", (ex,)).fetchone()
    return (r[0] if r else None) or None


def _narrow_snapshot(c, label):
    """What the narrow check needs next time: the newest record_id, record counts and run errors per live version."""
    ex, _t = MAP[label]
    vers = [v for v, s in c.execute("SELECT version, status FROM fx_extractor_versions WHERE extractor=?", (ex,))
            if s in ("active", "candidate")]
    snap = {"max_rid": c.execute("SELECT max(record_id) FROM fx_records").fetchone()[0] or 0, "cnt": {}, "err": {}}
    for v in vers:
        snap["cnt"][v] = c.execute("SELECT count(*) FROM fx_records WHERE extractor=? AND version=?", (ex, v)).fetchone()[0]
        snap["err"][v] = c.execute("SELECT count(*) FROM fx_runs WHERE extractor=? AND version=? AND status != 'ok'",
                                   (ex, v)).fetchone()[0]
    return snap


def _narrow(c, label, ins, outs, prev):
    """(nothing_relevant: bool, why: str, snapshot). nothing_relevant=True only when every test in the module
    docstring passes. Any doubt -> False."""
    snap = _narrow_snapshot(c, label)
    pn = prev.get("narrow") if prev else None
    if not pn or "events_fp" not in pn:
        return False, "no narrow baseline yet", snap
    for k in _NARROW_EXACT:
        if ins.get(k) != prev["in"].get(k):
            return False, k + " changed", snap
    for k in set(ins) | set(prev["in"]):
        if k.startswith(("read:", "file:", "names:")) and ins.get(k) != prev["in"].get(k):
            return False, k + " changed", snap
    if outs != prev["out"]:
        return False, "output table changed by someone else", snap
    if set(snap["cnt"]) != set(pn["cnt"]):
        return False, "live versions changed", snap
    if snap["err"] != pn["err"]:
        return False, "reader errors changed", snap
    ex, _t = MAP[label]
    tag = _tag_of(c, ex)
    new_events = set()
    for v in snap["cnt"]:
        rows = c.execute("SELECT record_id, event_id FROM fx_records WHERE record_id > ? AND extractor=? AND version=?",
                         (pn["max_rid"], ex, v)).fetchall()
        if snap["cnt"][v] - pn["cnt"][v] != len(rows):
            return False, "records removed or re-read (%s: %+d count, %d new)" % (v, snap["cnt"][v] - pn["cnt"][v], len(rows)), snap
        flag = NOTHING_FLAG.get(ex)
        if rows and not flag:
            return False, "%s has no found-nothing flag; any new record counts" % ex, snap
        for rid, eid in rows:
            fl = [x for (x,) in c.execute("SELECT value_num FROM fx_facts WHERE record_id=? AND field=?", (rid, flag))]
            if fl != [0]:
                return False, "new release %s: %s found something (%s=%s)" % (eid[:12], ex, flag, fl or "missing"), snap
            new_events.add(eid)
    if tag:
        for eid in new_events:
            r = c.execute("SELECT categories FROM events WHERE event_id=?", (eid,)).fetchone()
            if r and ("|" + (r[0] or "") + "|").find("|" + tag + "|") >= 0:
                return False, "new release %s carries the %s tag" % (eid[:12], tag), snap
    if _events_fp(c, new_events) != pn["events_fp"]:
        return False, "an existing release changed (or one arrived unread)", snap
    return True, "%d new release(s), none relevant" % len(new_events), snap


def _shadow(rec):
    try:
        os.makedirs(os.path.dirname(SHADOW_LOG), exist_ok=True)
        with open(SHADOW_LOG, "a") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    except OSError:
        pass


def before(label):
    """None = not handled here (run it). Otherwise {'skip': bool, 'why': str, ...}; pass it to after()."""
    if label not in MAP:
        return None
    t0 = time.time()
    try:
        if "code" not in _CODE:
            _CODE["code"] = _code_fp()
        c = _conn()
        try:
            ins = _inputs(c, label, _CODE["code"])
            outs = _outputs(c, label)
            prev = _load_state().get(label)
            try:
                n_ok, n_why, n_snap = _narrow(c, label, ins, outs, prev)
            except Exception as exc:  # noqa: BLE001 - narrow check failing means "relevant"
                n_ok, n_why, n_snap = False, "narrow check failed (%s)" % type(exc).__name__, None
        finally:
            c.close()
        info = {"skip": False, "in": ins, "out_before": outs, "secs": round(time.time() - t0, 1),
                "narrow": {"ok": n_ok, "why": n_why, "snap": n_snap}}
        if os.path.exists(OFF_FILE):
            info["why"] = "publish_skip_OFF"
        elif os.path.exists(ONLY_FILE) and label not in open(ONLY_FILE).read().split():
            info["why"] = "not in publish_skip_ONLY"
        elif not prev:
            info["why"] = "no earlier run recorded"
        else:
            age_h = (time.time() - prev["full_at"]) / 3600.0
            changed = sorted(k for k in set(ins) | set(prev["in"]) if ins.get(k) != prev["in"].get(k))
            out_changed = sorted(k for k in set(outs) | set(prev["out"]) if outs.get(k) != prev["out"].get(k))
            if age_h >= FULL_EVERY_H:
                info["why"] = "full rebuild due (last %.1f h ago)" % age_h
            elif not changed and not out_changed:
                info["skip"] = True
                info["why"] = ("nothing it reads has changed since the run at %s UTC (%.1f h ago; full rebuild every %g h)"
                               % (time.strftime("%H:%M", time.gmtime(prev["full_at"])), age_h, FULL_EVERY_H))
            elif n_ok and os.path.exists(NARROW_ON_FILE):
                info["skip"] = True
                info["why"] = "narrow: %s (last full run %.1f h ago)" % (n_why, age_h)
            else:
                info["why"] = "changed: " + ", ".join(changed + ["table " + x for x in out_changed])[:300]
                info["why"] += " | narrow: %s" % (("would skip - " if n_ok else "") + n_why)
        info["why"] += " [checked in %.1fs]" % (time.time() - t0)
        return info
    except Exception as exc:  # noqa: BLE001 - any doubt means run it
        _log("%s: check failed (%s: %s) - running it" % (label, type(exc).__name__, exc))
        return {"skip": False, "why": "check failed", "in": None}


def after(label, info, rc):
    """Record a successful run (rc == 0); forget the label after a failure so the next run publishes."""
    if not info:
        return
    if info.get("skip"):
        # a narrow skip moves the narrow baseline forward (the new releases are now known to be irrelevant); the
        # broad fingerprint is left as it was, so the 8-hour full rebuild still comes due on time
        n = info.get("narrow") or {}
        if n.get("ok") and n.get("snap"):
            try:
                st = _load_state()
                if label in st:
                    st[label]["narrow"] = dict(n["snap"], events_fp=_CODE.get("events"))
                    _save_state(st)
            except Exception as exc:  # noqa: BLE001
                _log("%s: could not move the narrow baseline (%s) - it will run next time" % (label, exc))
                try:
                    st = _load_state(); st.pop(label, None); _save_state(st)
                except Exception:  # noqa: BLE001
                    pass
        return
    try:
        st = _load_state()
        if rc == 0 and info.get("in"):
            c = _conn()
            try:
                outs = _outputs(c, label)
            finally:
                c.close()
            n = info.get("narrow") or {}
            if n.get("why") is not None:
                out_changed = outs != info.get("out_before")
                rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "label": label,
                       "narrow_says_skip": bool(n.get("ok")), "output_changed": out_changed, "why": n.get("why")}
                if n.get("ok") and out_changed:
                    rec["MISS"] = True
                    _log("%s: NARROW MISS - the narrow check said nothing relevant, but the table changed" % label)
                _shadow(rec)
            ent = {"in": info["in"], "out": outs, "full_at": time.time(),
                   "full_at_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())}
            if n.get("snap"):
                ent["narrow"] = dict(n["snap"], events_fp=info["in"].get("events"))
            st[label] = ent
        else:
            st.pop(label, None)
        _save_state(st)
    except Exception as exc:  # noqa: BLE001
        _log("%s: could not record the run (%s: %s) - it will simply run next time" % (label, type(exc).__name__, exc))
        try:
            st = _load_state()
            if st.pop(label, None) is not None:
                _save_state(st)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":   # report only: what would be skipped right now (reads, never writes)
    for lb in (sys.argv[1:] or list(MAP)):
        r = before(lb)
        print("%-22s %-5s %s" % (lb, "SKIP" if r and r["skip"] else "run", r and r.get("why")))
