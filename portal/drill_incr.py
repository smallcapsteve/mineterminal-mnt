"""SYNCMEM_INCR_V1 (2026-11-05; Justin: "Proper fix" for the reader sync's memory use).

portal.drill_publish rebuilds drill_results / drill_intervals from the whole facts store on every run in which any new
drill release arrived: about 15,700 releases, 994,000 intervals, ~2.8 GB and 5-70 minutes, usually for 1-4 new
releases. compute() is independent per ticker (the recap rule's `seen` set is per ticker; best interval, OCR notes and
the DRILLGAP fill are per release), so only the tickers whose inputs changed need computing again.

Per ticker, signature() hashes everything compute() reads for it: each tagged, approved release (event id, date,
headline) with the record ids the active version and the fill candidates hold for it, whether the active version ran
on it (DRILLGAP_V1), and the OCR fill / 'not reported' rows (DRILL_OCR_V1). Global inputs (active version, candidate
list, the kill switches, this file and drill_publish.py) are hashed separately; any change there means a full rebuild.

Modes (file /opt/mnt/app/portal/drill_incr_mode, one word; no file = off):
  off      drill_publish.publish() exactly as before.
  shadow   publish() exactly as before, then checks what incremental publishing would have done and logs one JSON
           line to /var/lib/mnt-publish-skip/drill_incr.log: `equal` (the per-ticker compute matches the full one for
           every changed ticker) and `miss` (tickers whose published rows changed although their signature did not).
  enforce  full publish() when there is no state, a global input changed, or the last full run is 8+ hours old and it
           is outside trading hours (or 24+ hours old at any time); otherwise only the changed tickers are loaded,
           computed and written (the same keep-unchanged-rows rule as portal/rowsync.py, so drill_id stays stable).
State: /var/lib/mnt-publish-skip/drill_incr.json (delete it to force one full run).
Read-only check: python3 -m portal.drill_incr verify [N]  (full compute vs per-ticker compute for N tickers; writes nothing)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import random
import sys
import time

from portal import drill_publish as P

MODE_FILE = "/opt/mnt/app/portal/drill_incr_mode"
STATE = "/var/lib/mnt-publish-skip/drill_incr.json"
LOG = "/var/lib/mnt-publish-skip/drill_incr.log"
FULL_EVERY_H = 8.0
FULL_MAX_H = 24.0
V = "SYNCMEM_INCR_V1"
_RES_COLS = ("event_id", "ticker", "project", "top_hole_id", "top_grade", "top_unit", "top_metal", "top_length_m",
             "top_summary", "n_intercepts", "raw_headline", "published_at", "sample_type", "extractor_version")


def mode():
    try:
        m = open(MODE_FILE).read().strip().lower()
        return m if m in ("off", "shadow", "enforce") else "off"
    except Exception:
        return "off"


def _log(rec):
    rec = dict(rec, v=V, at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
    print("[drill_incr] " + json.dumps(rec), flush=True)


def _load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return None


def _save_state(st):
    """Never raises: a state that cannot be saved means the next run compares against an older one (or runs in full)."""
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        tmp = STATE + ".tmp"
        json.dump(st, open(tmp, "w"))
        os.replace(tmp, STATE)
    except Exception as exc:  # noqa: BLE001
        print("[drill_incr] state not saved: %s: %s" % (type(exc).__name__, exc), flush=True)


def _file_fp(path):
    try:
        s = os.stat(path)
        return "%d:%d" % (s.st_size, s.st_mtime_ns)
    except Exception:
        return "missing"


def global_fp(conn, version):
    cands = [c for c in P.candidate_versions(conn) if c != version]
    parts = {"version": version, "cands": cands, "fill_off": os.path.exists(P.FILL_OFF),
             "ocr_off": os.path.exists(P.OCR_OFF), "ocr_db": os.path.exists(P.OCR_DB),
             "code": [_file_fp(P.__file__), _file_fp(__file__)]}
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:24], cands


def _ocr_rows():
    import sqlite3
    out = {}
    if os.path.exists(P.OCR_OFF) or not os.path.exists(P.OCR_DB):
        return out
    try:
        c = sqlite3.connect(f"file:{P.OCR_DB}?mode=ro", uri=True, timeout=10)
        for r in c.execute("SELECT event_id, hole_id, length_m, grade, from_m, to_m FROM ocr_fill"):
            out.setdefault(r[0], []).append(("f",) + tuple(r[1:]))
        for r in c.execute("SELECT event_id, depths FROM ocr_release"):
            out.setdefault(r[0], []).append(("r", r[1]))
        c.close()
    except Exception as exc:  # noqa: BLE001 - unreadable OCR store: every ticker's signature changes, which is safe
        out = {"__error__": [repr(exc)]}
    return out


def signature(conn, version, cands):
    """{ticker: hash} over everything compute() reads for that ticker. Streams rows; holds only small tuples."""
    like = "%|" + P.TAG + "|%"
    per = {}
    ev_ticker = {}
    q = ("SELECT e.ticker, e.event_id, e.published_at, e.raw_headline, r.record_id, r.ordinal FROM events e "
         "JOIN fx_records r ON r.event_id=e.event_id AND r.extractor=? AND r.version=? "
         "WHERE e.review_status='auto_approved' AND ('|' || COALESCE(e.categories,'') || '|') LIKE ?")
    for tk, eid, pub, hl, rid, ordn in conn.execute(q, (P.EXTRACTOR, version, like)):
        per.setdefault(tk or "", []).append(("a", eid, pub, hl, rid, ordn))
        ev_ticker[eid] = tk or ""
    if not os.path.exists(P.FILL_OFF) and P._has_table(conn, "fx_runs"):
        for cand in cands:
            q2 = ("SELECT e.ticker, e.event_id, e.published_at, e.raw_headline, r.record_id FROM fx_records r "
                  "JOIN events e ON e.event_id=r.event_id "
                  "WHERE r.extractor=? AND r.version=? AND r.ordinal=0 AND e.review_status='auto_approved' "
                  "AND ('|' || COALESCE(e.categories,'') || '|') LIKE ? "
                  "AND NOT EXISTS (SELECT 1 FROM fx_runs x WHERE x.event_id=r.event_id AND x.extractor=? AND x.version=?)")
            for tk, eid, pub, hl, rid in conn.execute(q2, (P.EXTRACTOR, cand, like, P.EXTRACTOR, version)):
                per.setdefault(tk or "", []).append(("c", cand, eid, pub, hl, rid))
                ev_ticker.setdefault(eid, tk or "")
    ocr = _ocr_rows()
    if "__error__" in ocr:
        return {tk: "ocr-error" for tk in per}
    for eid, rows in ocr.items():
        tk = ev_ticker.get(eid)
        if tk is not None:
            per[tk].extend(("o", eid) + tuple(x) for x in rows)
    return {tk: hashlib.blake2b(repr(sorted(v, key=repr)).encode("utf-8", "surrogatepass"), digest_size=12).hexdigest()
            for tk, v in per.items()}


def table_digest(conn, tickers=None):
    """{ticker: hash} of the published rows (drill_results incl. drill_id, and its intervals). Streams."""
    hs = {}
    for r in conn.execute("SELECT ticker, drill_id, %s FROM drill_results ORDER BY ticker, event_id" % ", ".join(_RES_COLS)):
        tk = r[0] or ""
        if tickers is not None and tk not in tickers:
            continue
        hs.setdefault(tk, hashlib.blake2b(digest_size=12)).update(repr(tuple(r)).encode("utf-8", "surrogatepass"))
    q = ("SELECT d.ticker, %s FROM drill_intervals i JOIN drill_results d ON d.event_id=i.event_id "
         "ORDER BY d.ticker, i.event_id, i.seq" % ", ".join("i." + c for c in P._IV_SYNC_COLS))
    for r in conn.execute(q):
        tk = r[0] or ""
        if tickers is not None and tk not in tickers:
            continue
        hs.setdefault(tk, hashlib.blake2b(digest_size=12)).update(repr(tuple(r)).encode("utf-8", "surrogatepass"))
    return {k: h.hexdigest() for k, h in hs.items()}


def _tmp_tickers(conn, tickers):
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _incr_tk (ticker TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM _incr_tk")
    conn.executemany("INSERT OR IGNORE INTO _incr_tk VALUES (?)", [(t,) for t in tickers])


def gather_tickers(conn, version, cands, tickers):
    """drill_publish.gather() restricted to `tickers` (same SQL, plus the ticker filter). Returns (items, src)."""
    _tmp_tickers(conn, tickers)
    like = "%|" + P.TAG + "|%"
    evs = {}
    for eid, tk, pub, hl in conn.execute(
            "SELECT e.event_id, e.ticker, e.published_at, e.raw_headline FROM events e "
            "JOIN fx_records r ON r.event_id=e.event_id AND r.extractor=? AND r.version=? "
            "WHERE e.review_status='auto_approved' AND ('|' || COALESCE(e.categories,'') || '|') LIKE ? "
            "AND COALESCE(e.ticker,'') IN (SELECT ticker FROM _incr_tk)", (P.EXTRACTOR, version, like)):
        evs[eid] = {"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl}
    facts = {}
    for eid, field, seq, num, text, unit, metal in conn.execute(
            "SELECT r.event_id, f.field, f.seq, f.value_num, f.value_text, f.unit, f.metal "
            "FROM fx_records r JOIN fx_facts f ON f.record_id=r.record_id JOIN events e ON e.event_id=r.event_id "
            "WHERE r.extractor=? AND r.version=? AND r.ordinal=0 AND COALESCE(e.ticker,'') IN (SELECT ticker FROM _incr_tk)",
            (P.EXTRACTOR, version)):
        if eid in evs:
            facts.setdefault(eid, []).append((field, seq, num, text, unit, metal))
    items = [(evs[e], P.parse_facts(facts.get(e, []))) for e in evs]
    src = {}
    if not os.path.exists(P.FILL_OFF) and cands and P._has_table(conn, "fx_runs"):
        seen = set(evs)
        for cand in cands:
            for eid, tk, pub, hl, rid in conn.execute(
                    "SELECT e.event_id, e.ticker, e.published_at, e.raw_headline, r.record_id FROM fx_records r "
                    "JOIN events e ON e.event_id=r.event_id "
                    "WHERE r.extractor=? AND r.version=? AND r.ordinal=0 AND e.review_status='auto_approved' "
                    "AND ('|' || COALESCE(e.categories,'') || '|') LIKE ? "
                    "AND COALESCE(e.ticker,'') IN (SELECT ticker FROM _incr_tk) "
                    "AND NOT EXISTS (SELECT 1 FROM fx_runs x WHERE x.event_id=r.event_id AND x.extractor=? AND x.version=?)",
                    (P.EXTRACTOR, cand, like, P.EXTRACTOR, version)).fetchall():
                if eid in seen:
                    continue
                seen.add(eid)
                fs = conn.execute("SELECT field, seq, value_num, value_text, unit, metal FROM fx_facts WHERE record_id=?",
                                  (rid,)).fetchall()
                items.append(({"event_id": eid, "ticker": tk, "published_at": pub, "raw_headline": hl},
                              P.parse_facts(fs)))
                src[eid] = cand
    return items, src


def compute_tickers(conn, version, cands, tickers):
    items, src = gather_tickers(conn, version, cands, tickers)
    rows, intervals, st = P.compute(items)
    for r in rows:
        r["extractor_version"] = src.get(r["event_id"], version)
    st.update(P.apply_ocr(intervals))
    return rows, intervals, st


def _norm_rows(rows, intervals):
    rr = sorted((tuple(r.get(c) for c in _RES_COLS) for r in rows))
    ii = sorted((tuple(i.get(c) for c in P._IV_SYNC_COLS) for i in intervals))
    return rr, ii


def write_tickers(conn, tickers, rows, intervals):
    """Make drill_results / drill_intervals for `tickers` equal to rows / intervals; leave every other row alone.
    Unchanged rows keep their drill_id (same rule as rowsync.sync_rows). Runs in one BEGIN IMMEDIATE transaction."""
    from portal import rowsync as RS
    _tmp_tickers(conn, tickers)
    new_eids = {r["event_id"] for r in rows}
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _incr_ev (event_id TEXT PRIMARY KEY)")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM _incr_ev")
        conn.executemany("INSERT OR IGNORE INTO _incr_ev VALUES (?)", [(e,) for e in new_eids])
        aff = RS._affinities(conn, "drill_results")
        norm = lambda c, v: RS._as_stored(v, aff.get(c, "BLOB"))
        existing = {}
        scope_eids = set()
        for r in conn.execute("SELECT drill_id, %s FROM drill_results WHERE COALESCE(ticker,'') IN (SELECT ticker FROM _incr_tk) "
                              "OR event_id IN (SELECT event_id FROM _incr_ev) ORDER BY drill_id" % ", ".join(_RES_COLS)):
            t = tuple(r)
            existing.setdefault(tuple(norm(c, v) for c, v in zip(_RES_COLS, t[1:])), []).append(t[0])
            scope_eids.add(t[1])
        ins, kept = [], 0
        for r in rows:
            k = tuple(norm(c, r.get(c)) for c in _RES_COLS)
            ids = existing.get(k)
            if ids:
                ids.pop(0)
                kept += 1
                if not ids:
                    del existing[k]
            else:
                ins.append({c: r.get(c) for c in _RES_COLS})
        dead = [i for ids in existing.values() for i in ids]
        # a row being replaced may still hold the event_id (UNIQUE): delete before inserting
        if dead:
            conn.executemany("DELETE FROM drill_results WHERE drill_id=?", [(i,) for i in dead])
        if ins:
            conn.executemany("INSERT INTO drill_results(%s) VALUES (%s)" % (", ".join(_RES_COLS), ", ".join(":" + c for c in _RES_COLS)), ins)
        res1 = {"kept": kept, "inserted": len(ins), "deleted": len(dead)}
        # intervals of every release in scope (old or new)
        iaff = RS._affinities(conn, "drill_intervals")
        inorm = lambda c, v: RS._as_stored(v, iaff.get(c, "BLOB"))
        scope_eids |= new_eids
        conn.execute("DELETE FROM _incr_ev")
        conn.executemany("INSERT OR IGNORE INTO _incr_ev VALUES (?)", [(e,) for e in scope_eids])
        cols = P._IV_SYNC_COLS
        have = {}
        for r in conn.execute("SELECT %s FROM drill_intervals WHERE event_id IN (SELECT event_id FROM _incr_ev)" % ", ".join(cols)):
            t = tuple(inorm(c, v) for c, v in zip(cols, tuple(r)))
            have[(t[0], t[1])] = t
        write, seen = [], set()
        for iv in intervals:
            t = tuple(inorm(c, iv.get(c)) for c in cols)
            k = (t[0], t[1])
            seen.add(k)
            if have.get(k) != t:
                write.append((k, {c: iv.get(c) for c in cols}, k in have))
        gone = [k for k in have if k not in seen]
        stale = gone + [k for k, _, had in write if had]
        if stale:
            conn.executemany("DELETE FROM drill_intervals WHERE event_id=? AND seq=?", stale)
        if write:
            conn.executemany("INSERT INTO drill_intervals(%s) VALUES (%s)" % (", ".join(cols), ", ".join(":" + c for c in cols)),
                             [p for _, p, _ in write])
        res2 = {"kept": len(have) - len(gone) - sum(1 for _, _, h in write if h), "inserted": len(write), "deleted": len(gone)}
        for tbl, res in (("drill_results", res1), ("drill_intervals", res2)):
            if res["inserted"] or res["deleted"]:
                try:
                    conn.execute(RS.FEEDVER_SQL, (tbl,))   # SPEEDFIX_FEEDVER_V1, as rowsync does
                except Exception:  # noqa: BLE001
                    pass
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"drill_results": res1, "drill_intervals": res2}


def _trading_hours():
    from zoneinfo import ZoneInfo
    t = dt.datetime.now(ZoneInfo("America/Toronto"))
    m = t.hour * 60 + t.minute
    return t.weekday() < 5 and 9 * 60 + 30 <= m < 16 * 60


def run(conn, version, publish):
    """Called by drill_publish.main() instead of publish(conn, version). Never publishes less safely than before:
    any error in the incremental path falls back to a full publish()."""
    m = mode()
    if m == "off":
        return publish(conn, version)
    t0 = time.time()
    try:
        gfp, cands = global_fp(conn, version)
        sig = signature(conn, version, cands)
    except Exception as exc:  # noqa: BLE001
        _log({"mode": m, "error": "signature: %s: %s" % (type(exc).__name__, exc), "action": "full"})
        return publish(conn, version)
    prev = _load_state()
    changed = sorted(t for t in set(sig) | set((prev or {}).get("sig", {}))
                     if sig.get(t) != (prev or {}).get("sig", {}).get(t))
    t_sig = round(time.time() - t0, 1)
    if m == "shadow" and _trading_hours():
        # keep trading hours light: publish as before, refresh the state, check nothing (checks run outside them)
        st = publish(conn, version)
        _save_state({"gfp": gfp, "sig": sig, "full_at": time.time()})
        _log({"mode": "shadow", "checked": False, "why": "trading hours", "changed": len(changed), "sig_s": t_sig})
        return st
    if m == "shadow":
        try:
            before = table_digest(conn)
        except Exception as exc:  # noqa: BLE001 - the check is optional; publishing is not
            st = publish(conn, version)
            _save_state({"gfp": gfp, "sig": sig, "full_at": time.time()})
            _log({"mode": "shadow", "checked": False, "error": "digest: %s: %s" % (type(exc).__name__, exc)})
            return st
        st = publish(conn, version)
        try:
            after = table_digest(conn)
        except Exception as exc:  # noqa: BLE001
            _save_state({"gfp": gfp, "sig": sig, "full_at": time.time()})
            _log({"mode": "shadow", "checked": False, "error": "digest after: %s: %s" % (type(exc).__name__, exc)})
            return st
        moved = sorted(t for t in set(before) | set(after) if before.get(t) != after.get(t))
        rec = {"mode": "shadow", "sig_s": t_sig, "tickers": len(sig), "changed": len(changed),
               "changed_sample": changed[:15], "published_changed": len(moved)}
        if prev is None or prev.get("gfp") != gfp:
            rec["note"] = "first run or global inputs changed: incremental would have run in full"
        else:
            miss = sorted(set(moved) - set(changed))
            rec["miss"] = len(miss)
            rec["miss_sample"] = miss[:15]
            if changed:
                try:
                    r_i, i_i, _ = compute_tickers(conn, version, cands, changed)
                    rows_f = [tuple(r) for r in conn.execute(
                        "SELECT %s FROM drill_results WHERE COALESCE(ticker,'') IN (SELECT ticker FROM _incr_tk)" % ", ".join(_RES_COLS))]
                    ivs_f = [tuple(r) for r in conn.execute(
                        "SELECT %s FROM drill_intervals WHERE event_id IN (SELECT event_id FROM drill_results WHERE "
                        "COALESCE(ticker,'') IN (SELECT ticker FROM _incr_tk))" % ", ".join(P._IV_SYNC_COLS))]
                    from portal import rowsync as RS
                    aff = RS._affinities(conn, "drill_results")
                    iaff = RS._affinities(conn, "drill_intervals")
                    nr = lambda t, cols, a: tuple(RS._as_stored(v, a.get(c, "BLOB")) for c, v in zip(cols, t))
                    inc_r = sorted(nr(tuple(r.get(c) for c in _RES_COLS), _RES_COLS, aff) for r in r_i)
                    inc_i = sorted(nr(tuple(i.get(c) for c in P._IV_SYNC_COLS), P._IV_SYNC_COLS, iaff) for i in i_i)
                    pub_r = sorted(nr(t, _RES_COLS, aff) for t in rows_f)
                    pub_i = sorted(nr(t, P._IV_SYNC_COLS, iaff) for t in ivs_f)
                    rec["equal"] = inc_r == pub_r and inc_i == pub_i
                    rec["rows"] = [len(inc_r), len(pub_r)]
                    rec["intervals"] = [len(inc_i), len(pub_i)]
                    if not rec["equal"]:
                        rec["diff_rows"] = [list(x) for x in sorted(set(inc_r) ^ set(pub_r))][:5]
                except Exception as exc:  # noqa: BLE001
                    rec["equal"] = None
                    rec["error"] = "compare: %s: %s" % (type(exc).__name__, exc)
        _save_state({"gfp": gfp, "sig": sig, "full_at": time.time()})
        rec["seconds"] = round(time.time() - t0, 1)
        _log(rec)
        return st
    # enforce
    age_h = (time.time() - prev["full_at"]) / 3600 if prev else None
    full_why = ("no state" if prev is None else "global inputs changed" if prev.get("gfp") != gfp
                else "full rebuild due (%.1f h)" % age_h if (age_h >= FULL_MAX_H or (age_h >= FULL_EVERY_H and not _trading_hours()))
                else None)
    if full_why:
        st = publish(conn, version)
        _save_state({"gfp": gfp, "sig": sig, "full_at": time.time()})
        _log({"mode": "enforce", "action": "full", "why": full_why, "seconds": round(time.time() - t0, 1)})
        return st
    if not changed:
        _log({"mode": "enforce", "action": "nothing changed", "sig_s": t_sig})
        _save_state(dict(prev, sig=sig))
        return {"incremental": True, "changed": 0}
    try:
        rows, intervals, st = compute_tickers(conn, version, cands, changed)
        wr = write_tickers(conn, changed, rows, intervals)
    except Exception as exc:  # noqa: BLE001
        _log({"mode": "enforce", "action": "full (incremental failed)", "error": "%s: %s" % (type(exc).__name__, exc)})
        st = publish(conn, version)
        _save_state({"gfp": gfp, "sig": sig, "full_at": time.time()})
        return st
    _save_state(dict(prev, sig=sig))
    rec = {"mode": "enforce", "action": "incremental", "changed": len(changed), "changed_sample": changed[:15],
           "rows": len(rows), "intervals": len(intervals), "write": wr, "sig_s": t_sig, "seconds": round(time.time() - t0, 1)}
    _log(rec)
    print("[drill_publish] " + json.dumps(dict(st, incremental=True, tickers=len(changed), version=version)))
    return st


def verify(n=40):
    """Read-only: full compute vs per-ticker compute for n random tickers (plus the 10 with most releases)."""
    import sqlite3
    conn = sqlite3.connect("file:%s?mode=ro" % P.DB, uri=True, timeout=30)
    version = P.active_version(conn)
    gfp, cands = global_fp(conn, version)
    t0 = time.time()
    items, src, _ = P.gather(conn, version)
    rows, ivs, _ = P.compute(items)
    for r in rows:
        r["extractor_version"] = src.get(r["event_id"], version)
    P.apply_ocr(ivs)
    t_full = time.time() - t0
    by_t = {}
    for r in rows:
        by_t.setdefault(r["ticker"] or "", [[], []])[0].append(r)
    ev_t = {r["event_id"]: (r["ticker"] or "") for r in rows}
    for i in ivs:
        by_t[ev_t[i["event_id"]]][1].append(i)
    tick = sorted(by_t, key=lambda t: -len(by_t[t][0]))[:10] + random.sample(sorted(by_t), min(n, len(by_t)))
    tick = sorted(set(tick))
    t1 = time.time()
    r_i, i_i, _ = compute_tickers(conn, version, cands, tick)
    t_inc = time.time() - t1
    bad = []
    got = {}
    ev_ti = {r["event_id"]: (r["ticker"] or "") for r in r_i}
    for r in r_i:
        got.setdefault(r["ticker"] or "", [[], []])[0].append(r)
    for i in i_i:
        got[ev_ti[i["event_id"]]][1].append(i)
    for t in tick:
        a = _norm_rows(*by_t.get(t, [[], []]))
        b = _norm_rows(*got.get(t, [[], []]))
        if a != b:
            bad.append(t)
    sig = signature(conn, version, cands)
    out = {"tickers_checked": len(tick), "mismatch": bad[:20], "full_s": round(t_full, 1), "incremental_s": round(t_inc, 2),
           "rows_full": len(rows), "intervals_full": len(ivs), "sig_tickers": len(sig), "published_tickers": len(by_t)}
    print("[drill_incr verify] " + json.dumps(out))
    return 0 if not bad else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        sys.exit(verify(int(sys.argv[2]) if len(sys.argv) > 2 else 40))
    print(__doc__)
