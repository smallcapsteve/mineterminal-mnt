"""TAGINCR_V1 (2026-11-05; Justin: "Can we make these fixes too"): the reader-tag step looks only at new records
between full passes.

portal.reader_tags.decide() looks, for each enabled rule, through every record of the reader's active version
(~194,000) for releases with a substantive find, no tag and no decision yet - every run (300-430 s), and finds 0-1.
Record ids only grow (fx_records.record_id is the rowid), and once a release is decided it is never a candidate
again for the same (version, rule), so between runs the only new candidates are records added since the last pass.
Two things can still make an OLD record a candidate: its release losing the tag later, or becoming approved later.
A full pass catches those: every 8 hours outside trading hours (24 hours at most), and whenever the version or the
rule changes.

Modes (file /opt/mnt/app/portal/tag_incr_mode, one word; no file = off):
  off      reader_tags.decide() exactly as before.
  shadow   decide() exactly as before (the full candidate list), and also works out the new-records-only list; logs
           how many the full list had that the short list did not (`late`: what would have waited for the next full
           pass) to /var/lib/mnt-publish-skip/tag_incr.log.
  enforce  the new-records-only list, with the full pass on the schedule above.
State: /var/lib/mnt-publish-skip/tag_incr.json (delete it to force full passes). Any error: the full pass, as before.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time

MODE_FILE = "/opt/mnt/app/portal/tag_incr_mode"
STATE = "/var/lib/mnt-publish-skip/tag_incr.json"
LOG = "/var/lib/mnt-publish-skip/tag_incr.log"
FULL_EVERY_H = 8.0
FULL_MAX_H = 24.0
V = "TAGINCR_V1"


def mode():
    try:
        m = open(MODE_FILE).read().strip().lower()
        return m if m in ("off", "shadow", "enforce") else "off"
    except Exception:
        return "off"


def _log(rec, log=print):
    rec = dict(rec, v=V, at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
    log("[tag_incr] " + json.dumps(rec))


def _load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def _save(st):
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        json.dump(st, open(STATE + ".tmp", "w"))
        os.replace(STATE + ".tmp", STATE)
    except Exception as exc:  # noqa: BLE001 - next run then does a full pass
        print("[tag_incr] state not saved: %s: %s" % (type(exc).__name__, exc))


def _trading_hours():
    from zoneinfo import ZoneInfo
    t = dt.datetime.now(ZoneInfo("America/Toronto"))
    m = t.hour * 60 + t.minute
    return t.weekday() < 5 and 9 * 60 + 30 <= m < 16 * 60


def decide(conn, A, key, version, rule_sha, tag, mod, log, RT):
    """Called by reader_tags.run() instead of RT.decide(...). Returns what RT.decide returns."""
    m = mode()
    if m == "off":
        return RT.decide(conn, A, key, version, rule_sha, tag, mod, log)
    t0 = time.time()
    try:
        base = RT.base_of(key)
        top = conn.execute("SELECT MAX(record_id) FROM fx_records").fetchone()[0] or 0   # before any candidate query
        states = _load()
        sk = "%s|%s|%s" % (key, version, rule_sha)
        prev = states.get(sk)
        mark = prev["mark"] if prev else None
        if m == "shadow":
            full = RT.candidates(conn, key, base, version, rule_sha, tag)
            short = RT.candidates(conn, key, base, version, rule_sha, tag, since=mark) if mark is not None else None
        else:
            age_h = (time.time() - prev["full_at"]) / 3600 if prev else None
            why = ("no state" if prev is None else "full pass due (%.1f h)" % age_h
                   if (age_h >= FULL_MAX_H or (age_h >= FULL_EVERY_H and not _trading_hours())) else None)
            if why:
                full, short = RT.candidates(conn, key, base, version, rule_sha, tag), None
            else:
                full, short = None, RT.candidates(conn, key, base, version, rule_sha, tag, since=mark)
    except Exception as exc:  # noqa: BLE001 - the full pass, exactly as before
        _log({"key": key, "mode": m, "error": "%s: %s" % (type(exc).__name__, exc), "action": "full"}, log)
        return RT.decide(conn, A, key, version, rule_sha, tag, mod, log)
    t_q = round(time.time() - t0, 1)
    todo = full if full is not None else short
    res = RT.decide(conn, A, key, version, rule_sha, tag, mod, log, todo=todo)
    rec = {"key": key, "mode": m, "query_s": t_q, "mark": mark, "top": top}
    if m == "shadow":
        rec["full"] = len(full)
        if short is None:
            rec["note"] = "first pass: no mark yet"
        else:
            late = sorted(set(full) - set(short))
            rec.update(short=len(short), late=len(late), late_sample=late[:10],
                       extra=len(set(short) - set(full)))
    else:
        rec.update(action="full" if full is not None else "new records only", todo=len(todo))
    states = _load()
    old = states.get(sk) or {}
    states[sk] = {"mark": top, "full_at": time.time() if (m == "shadow" or full is not None) else old.get("full_at", time.time())}
    _save(states)
    rec["seconds"] = round(time.time() - t0, 1)
    _log(rec, log)
    return res
