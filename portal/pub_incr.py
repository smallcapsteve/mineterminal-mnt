"""PUB_INCR_V1 (2026-11-05; Justin: "All 14, in stages"): per-company publishing for the reader publishers.

Every publisher rebuilt its whole table on any run with a new release: load_items() reads every release and every
stored fact of the active reader version (~194,000 records), compute() builds all rows, rowsync writes the few that
changed. compute() works company by company for the publishers listed in ADAPTERS (checked one by one on
2026-11-05, claude/SYNCMEM_2026-11-05.md), so only companies whose inputs changed need re-reading.

How it works for one publisher (the drill version, portal/drill_incr.py, is the same idea):
  signature   per ticker, a hash of what the publisher reads for it: every release the reader version ran on (id,
              approval, dates, tags, slug, other tickers, and the run's time, text hash, status and record count),
              plus the publisher's extra inputs (exchange bulletins for the calendar, financing closings for warrant
              changes). Global inputs (version, code files, kill switches, company-name file) are hashed separately;
              any change there means a full rebuild.
  load        the changed tickers' rows of events, fx_runs and fx_records are copied into TEMP tables with the
              same names, so the publisher's own load_items()/compute() code runs unchanged and sees only them.
  write       only those tickers' rows, keeping unchanged rows and their ids (the rowsync rule), feed version
              bumped where rowsync would bump it.
  full        no state, global inputs changed, 8+ h since the last full run outside trading hours (24 h at most),
              more than MAX_EVENTS releases to redo, or any error: the publisher's own publish(), exactly as before.

Modes, per publisher (file /opt/mnt/app/portal/pub_incr_modes, JSON {"financings": "shadow", ...}; absent = off):
  off      publish() as before.
  shadow   publish() as before; outside trading hours also checks `equal` (per-company result == the full one for
           every changed ticker) and `miss` (tickers whose rows changed while their signature did not).
  enforce  per-company publishing.
Log: /var/lib/mnt-publish-skip/pub_incr.log. State: /var/lib/mnt-publish-skip/pub_incr_<name>.json.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib
import json
import os
import time

MODES_FILE = "/opt/mnt/app/portal/pub_incr_modes"
STATE_DIR = "/var/lib/mnt-publish-skip"
LOG = os.path.join(STATE_DIR, "pub_incr.log")
FULL_EVERY_H = 8.0
FULL_MAX_H = 24.0
MAX_EVENTS = 30000
_PD = os.path.dirname(os.path.abspath(__file__))   # PUB_INCR_V1.2 (2026-11-12): the headline is in the signature;
#   corrections lists and the filing figures are in the global fingerprint, by content
V = "PUB_INCR_V1.3"   # 2026-11-06: economics fingerprints the company-name map, not the file; shadow counts late arrivals

MGMT_COLS = ("event_id", "ordinal", "ticker", "action", "person", "role", "role_canon", "scope", "effective_date",
             "interim", "n_changes", "raw_headline", "published_at")


# ------------------------------------------------------------------ adapters: how each publisher builds its rows
def _std(table, id_col, cols=None):
    def build(M, conn, version, tickers):
        rows, st = M.compute(M.load_items(conn, version))
        return [dict(table=table, kind="rows", id=id_col, cols=tuple(cols or M._COLS),
                     const={"extractor_version": version}, rows=rows)]
    return build


def _economics(M, conn, version, tickers):
    rows, st = M.compute(M.load_items(conn, version), M.company_names())
    return [dict(table="economic_studies", kind="rows", id="es_id", cols=tuple(M._COLS),
                 const={"extractor_version": version}, rows=rows)]


def _calendar(M, conn, version, tickers):
    bull = [it for it in M.bulletin_items(conn) if tickers is None or (it[0].get("ticker") or "") in tickers]
    rows, st = M.compute(M.load_items(conn, version) + bull)
    return [dict(table="calendar_events", kind="replace", id="cal_id", cols=tuple(M._COLS),
                 const={"extractor_version": version}, rows=rows)]


def _warrants(M, conn, version, tickers):
    rows, st = M.compute(M.load_items(conn, version), M.closes_loader(conn))
    return [dict(table="warrant_changes", kind="replace", id="wc_id", cols=tuple(M._COLS),
                 const={"extractor_version": version}, rows=rows)]


def _financings(M, conn, version, tickers):
    deals, releases, st = M.compute(M.load_items(conn, version))
    M.link_announcements(conn, deals, releases)
    fin_rows, ev_rows = M.rows_for(deals, releases, version)
    return [dict(table="financings", kind="pk", id="financing_id", pk=("financing_id",),
                 cols=tuple(fin_rows[0].keys()) if fin_rows else None, const={}, rows=fin_rows,
                 stable_refs=[(ev_rows, ("financing_id", "second_financing_id"))], scope="ticker"),
            dict(table="financing_events", kind="pk", id="event_id", pk=("event_id",),
                 cols=tuple(ev_rows[0].keys()) if ev_rows else None, const={}, rows=ev_rows)]


def _production(M, conn, version, tickers):   # PUB_INCR_V1.3 (2026-11-13): same filing overlay + US hide rule as publish()
    rows, st = M.compute(M.load_items(conn, version))
    try:
        from portal import production_filings as _pf
        rows, _fst = _pf.apply([dict(r) for r in rows], conn, cols=list(M._COLS))
    except Exception:  # noqa: BLE001 - publish() keeps the reader's rows on an overlay error; so does this
        pass
    if tickers is not None:
        rows = [r for r in rows if (r.get("ticker") or "") in tickers]
    return [dict(table="production_results", kind="rows", id="pr_id", cols=tuple(M._COLS),
                 const={"extractor_version": version}, rows=rows)]


def _bulletin_sig(M, conn, version):
    per = {}
    for ev, p in M.bulletin_items(conn):
        per.setdefault(ev.get("ticker") or "", []).append(repr((ev, p)))
    return per


def _closings_sig(M, conn, version):
    per = {}
    try:
        q = ("SELECT fe.ticker, f.financing_id, fe.event_id, fe.event_date, fe.role, fe.amount_this_close, fe.is_duplicate, "
             "fe.warrant_strike, f.warrant_strike, fe.warrant_term_months, f.warrant_term_months FROM financing_events fe "
             "JOIN financings f ON f.financing_id = fe.financing_id")
        for r in conn.execute(q):
            per.setdefault(r[0] or "", []).append(repr(tuple(r)))
    except Exception as exc:  # noqa: BLE001 - no financing tables: closes_for() returns nothing for anyone
        per = {"__none__": [repr(exc)]}
    return per


ADAPTERS = {
    "management": dict(mod="portal.management_publish", build=_std("management_changes", "mgmt_id", MGMT_COLS),
                       tables=["management_changes"], cfiles=[_PD + "/management_overrides.json"]),
    "resources": dict(mod="portal.resources_publish", build=_std("resource_estimates", "res_id"),
                      tables=["resource_estimates"]),
    "production": dict(mod="portal.production_publish", build=_production,
                       tables=["production_results"],
                       cfiles=[_PD + "/production_overrides.json", _PD + "/production_filings.json",
                               _PD + "/production_filings.py"],
                       flags=[_PD + "/production_filings_OFF", _PD + "/production_filings_SHOWOLD"]),
    "mine_dev": dict(mod="portal.mine_dev_publish", build=_std("mine_dev_events", "md_id"), tables=["mine_dev_events"]),
    "sampling": dict(mod="portal.sampling_publish", build=_std("sampling_results", "sr_id"), tables=["sampling_results"]),
    "economics": dict(mod="portal.economics_publish", build=_economics, tables=["economic_studies"],
                      gfp_extra=lambda M: hashlib.sha256(json.dumps(M.company_names(), sort_keys=True,
                                                                   default=str).encode()).hexdigest()[:16]),
    "calendar": dict(mod="portal.calendar_publish", build=_calendar, tables=["calendar_events"], extra_sig=_bulletin_sig,
                     extra_modules=["portal.exchange_bulletins"]),
    "warrant_changes": dict(mod="portal.warrant_changes_publish", build=_warrants, tables=["warrant_changes"],
                            extra_sig=_closings_sig),
    "financings": dict(mod="portal.financing_publish", build=_financings, tables=["financings", "financing_events"],
                       cfiles=[_PD + "/financing_overrides.json"]),
}


# ------------------------------------------------------------------ plumbing
def mode(name):
    try:
        m = (json.load(open(MODES_FILE)) or {}).get(name, "off")
        return m if m in ("off", "shadow", "enforce") else "off"
    except Exception:
        return "off"


def _log(rec):
    rec = dict(rec, v=V, at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except Exception:
        pass
    print("[pub_incr] " + json.dumps(rec, default=str), flush=True)


def _state_path(name):
    return os.path.join(STATE_DIR, "pub_incr_%s.json" % name)


def _load_state(name):
    try:
        return json.load(open(_state_path(name)))
    except Exception:
        return None


def _save_state(name, st):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        p = _state_path(name)
        json.dump(st, open(p + ".tmp", "w"))
        os.replace(p + ".tmp", p)
    except Exception as exc:  # noqa: BLE001
        print("[pub_incr] state not saved: %s: %s" % (type(exc).__name__, exc), flush=True)


def _trading_hours():
    from zoneinfo import ZoneInfo
    t = dt.datetime.now(ZoneInfo("America/Toronto"))
    m = t.hour * 60 + t.minute
    return t.weekday() < 5 and 9 * 60 + 30 <= m < 16 * 60


def _file_fp(path):
    try:
        s = os.stat(path)
        return "%d:%d" % (s.st_size, s.st_mtime_ns)
    except Exception:
        return "missing"


def _content_fp(path):   # PUB_INCR_V1.2
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception:  # noqa: BLE001
        return "missing"


def global_fp(name, M, version):
    ad = ADAPTERS[name]
    files = [M.__file__, __file__, os.path.join(os.path.dirname(__file__), "rowsync.py")]
    for mn in ad.get("extra_modules", []):
        try:
            files.append(importlib.import_module(mn).__file__)
        except Exception:  # noqa: BLE001
            files.append("missing:" + mn)
    try:
        X = importlib.import_module("portal.extractors." + {"financings": "financings", "calendar": "corp_calendar"}.get(
            name, M.EXTRACTOR))
        files.append(X.__file__)
    except Exception:  # noqa: BLE001
        pass
    if ad.get("files"):
        files += [f for f in ad["files"](M) if f]
    parts = {"version": version, "files": [(f, _file_fp(f)) for f in files],
             "extra": ad["gfp_extra"](M) if ad.get("gfp_extra") else None,
             "content": [(f, _content_fp(f)) for f in ad.get("cfiles", [])],   # PUB_INCR_V1.2
             "flags": [(f, os.path.exists(f)) for f in ad.get("flags", [])],
             "rowsync_off": os.path.exists(os.path.join(os.path.dirname(__file__), "rowsync_OFF")),
             "env_off": os.environ.get("MNT_ROWSYNC_OFF")}
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:24]


def signature(name, M, conn, version):
    """{ticker: hash}. Streams the events index; holds one small tuple per release this version ran on."""
    runs = {}
    for eid, ran, sha, status, n in conn.execute(
            "SELECT event_id, ran_at, body_sha1, status, n_records FROM fx_runs WHERE extractor=? AND version=?",
            (M.EXTRACTOR, version)):
        runs[eid] = (ran, sha, status, n)
    for eid, hl in conn.execute("SELECT event_id, raw_headline FROM main.events"):   # PUB_INCR_V1.2
        x = runs.get(eid)
        if x is not None:
            runs[eid] = x + (hashlib.blake2b((hl or "").encode("utf-8", "surrogatepass"), digest_size=6).hexdigest(),)
    hs = {}
    q = ("SELECT COALESCE(ticker,''), event_id, review_status, COALESCE(published_at, classified_at), categories, "
         "additional_tickers, published_at, classified_at, slug FROM main.events INDEXED BY ix_events_list")
    try:
        cur = conn.execute(q)
    except Exception:  # noqa: BLE001 - no such index (tests): same columns from the table
        cur = conn.execute(q.replace(" INDEXED BY ix_events_list", ""))
    for r in cur:
        x = runs.get(r[1])
        if x is None:
            continue
        hs.setdefault(r[0], hashlib.blake2b(digest_size=12)).update(repr(tuple(r) + x).encode("utf-8", "surrogatepass"))
    ex = ADAPTERS[name].get("extra_sig")
    if ex:
        for tk, items in ex(M, conn, version).items():
            h = hs.setdefault(tk, hashlib.blake2b(digest_size=12))
            for it in sorted(items):
                h.update(("x" + it).encode("utf-8", "surrogatepass"))
    return {k: h.hexdigest() for k, h in hs.items()}


def _has_col(conn, table, col):
    return any(r[1] == col for r in conn.execute("PRAGMA main.table_info(%s)" % table))


def table_digest(conn, name):
    """{ticker: hash} of the published rows, ignoring row ids of the tables rebuilt with fresh ids, order-free."""
    per = {}
    for t in ADAPTERS[name]["tables"]:
        if not conn.execute("SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?", (t,)).fetchone():
            continue
        info = list(conn.execute("PRAGMA main.table_info(%s)" % t))
        rowid_alias = [r[1] for r in info if r[5] == 1 and "INT" in (r[2] or "").upper()]
        cols = [r[1] for r in info if r[1] not in rowid_alias]
        for r in conn.execute("SELECT COALESCE(ticker,''), %s FROM main.%s" % (", ".join(cols), t)):
            per.setdefault(r[0], []).append(repr((t,) + tuple(r[1:])))
    return {k: hashlib.blake2b("\n".join(sorted(v)).encode("utf-8", "surrogatepass"), digest_size=12).hexdigest()
            for k, v in per.items()}


_TEMP = ("events", "fx_runs", "fx_records")


def _scope_tables(conn, tickers):
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _pi_tk (ticker TEXT PRIMARY KEY)")
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _pi_ev (event_id TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM temp._pi_tk")
    conn.execute("DELETE FROM temp._pi_ev")
    conn.executemany("INSERT OR IGNORE INTO temp._pi_tk VALUES (?)", [(t,) for t in tickers])
    conn.execute("INSERT OR IGNORE INTO temp._pi_ev SELECT event_id FROM main.events "
                 "WHERE COALESCE(ticker,'') IN (SELECT ticker FROM temp._pi_tk)")
    return conn.execute("SELECT COUNT(*) FROM temp._pi_ev").fetchone()[0]


def _shadow_on(conn):
    """Copy the scoped rows into TEMP tables named like the real ones (unqualified names resolve to temp first)."""
    _shadow_off(conn)
    conn.execute("CREATE TEMP TABLE events AS SELECT * FROM main.events WHERE event_id IN (SELECT event_id FROM temp._pi_ev)")
    conn.execute("CREATE INDEX temp._pi_i1 ON events(event_id)")
    conn.execute("CREATE INDEX temp._pi_i2 ON events(ticker, published_at)")
    conn.execute("CREATE TEMP TABLE fx_runs AS SELECT * FROM main.fx_runs WHERE event_id IN (SELECT event_id FROM temp._pi_ev)")
    conn.execute("CREATE INDEX temp._pi_i3 ON fx_runs(extractor, version, event_id)")
    conn.execute("CREATE INDEX temp._pi_i4 ON fx_runs(event_id)")
    conn.execute("CREATE TEMP TABLE fx_records AS SELECT * FROM main.fx_records "
                 "WHERE event_id IN (SELECT event_id FROM temp._pi_ev)")
    conn.execute("CREATE INDEX temp._pi_i5 ON fx_records(extractor, version, ordinal)")
    conn.execute("CREATE INDEX temp._pi_i6 ON fx_records(event_id)")
    conn.execute("CREATE INDEX temp._pi_i7 ON fx_records(record_id)")


def _shadow_off(conn):
    for t in _TEMP:
        try:
            conn.execute("DROP TABLE IF EXISTS temp.%s" % t)
        except Exception:  # noqa: BLE001
            pass


def compute_scoped(name, M, conn, version, tickers):
    n_ev = _scope_tables(conn, tickers)
    if n_ev > MAX_EVENTS:
        raise OverflowError("%d releases to redo (more than %d): full rebuild" % (n_ev, MAX_EVENTS))
    _shadow_on(conn)
    try:
        specs = ADAPTERS[name]["build"](M, conn, version, set(tickers))
    finally:
        _shadow_off(conn)
    for s in specs:
        bad = [r.get("ticker") for r in s["rows"] if (r.get("ticker") or "") not in tickers]
        if bad:
            raise ValueError("%s: computed rows for tickers outside the changed set (%r)" % (s["table"], bad[:5]))
    return specs, n_ev


def _scope_sql(conn, s):
    if s.get("scope") == "ticker" or not _has_col(conn, s["table"], "event_id"):
        return "COALESCE(ticker,'') IN (SELECT ticker FROM temp._pi_tk)"
    return ("(COALESCE(ticker,'') IN (SELECT ticker FROM temp._pi_tk) OR "
            "event_id IN (SELECT event_id FROM temp._pi_ev))")


def write_scoped(conn, specs):
    """Make each table's rows in scope equal to the computed rows; leave every other row alone. One transaction."""
    from portal import rowsync as RS
    out = {}
    conn.execute("BEGIN IMMEDIATE")
    try:
        for s in specs:
            t, rows = s["table"], s["rows"]
            if s.get("stable_refs") is not None and rows:
                RS._stable_ids_now(conn, t, s["id"], rows, s["stable_refs"])
            where = _scope_sql(conn, s)
            aff = RS._affinities(conn, t)
            norm = lambda c, v: RS._as_stored(v, aff.get(c, "BLOB"))   # noqa: E731
            if s["kind"] == "pk":
                cols = list(s["cols"] or [])
                pk = list(s["pk"])
                have = {}
                if cols:
                    for r in conn.execute("SELECT %s FROM main.%s WHERE %s" % (", ".join(cols), t, where)):
                        tt = tuple(norm(c, v) for c, v in zip(cols, tuple(r)))
                        have[tuple(tt[cols.index(k)] for k in pk)] = tt
                else:
                    pkc = ", ".join(pk)
                    for r in conn.execute("SELECT %s FROM main.%s WHERE %s" % (pkc, t, where)):
                        have[tuple(norm(c, v) for c, v in zip(pk, tuple(r)))] = None
                write, seen = [], set()
                for p in rows:
                    tt = tuple(norm(c, p[c]) for c in cols)
                    k = tuple(tt[cols.index(x)] for x in pk)
                    seen.add(k)
                    if have.get(k) != tt:
                        write.append((k, {c: p[c] for c in cols}, k in have))
                gone = [k for k in have if k not in seen]
                stale = gone + [k for k, _, had in write if had]
                wsql = " AND ".join("%s=?" % k for k in pk)
                if stale:
                    conn.executemany("DELETE FROM main.%s WHERE %s" % (t, wsql), stale)
                if write:
                    conn.executemany("INSERT INTO main.%s(%s) VALUES (%s)" % (t, ", ".join(cols), ", ".join(":" + c for c in cols)),
                                     [p for _, p, _ in write])
                res = {"kept": len(have) - len(gone) - sum(1 for _, _, h in write if h), "inserted": len(write),
                       "deleted": len(gone)}
            else:
                cols = list(s["cols"]) + list(s["const"])
                params = [dict({c: r[c] for c in s["cols"]}, **s["const"]) for r in rows]
                if s["kind"] == "replace":
                    n = conn.execute("DELETE FROM main.%s WHERE %s" % (t, where)).rowcount
                    if params:
                        conn.executemany("INSERT INTO main.%s(%s) VALUES (%s)" % (t, ", ".join(cols), ", ".join(":" + c for c in cols)),
                                         params)
                    res = {"deleted": n, "inserted": len(params)}
                else:
                    existing = {}
                    for r in conn.execute("SELECT %s, %s FROM main.%s WHERE %s ORDER BY %s" % (s["id"], ", ".join(cols), t, where, s["id"])):
                        tt = tuple(r)
                        existing.setdefault(tuple(norm(c, v) for c, v in zip(cols, tt[1:])), []).append(tt[0])
                    ins, kept = [], 0
                    for p in params:
                        k = tuple(norm(c, p[c]) for c in cols)
                        ids = existing.get(k)
                        if ids:
                            ids.pop(0)
                            kept += 1
                            if not ids:
                                del existing[k]
                        else:
                            ins.append(p)
                    dead = [i for ids in existing.values() for i in ids]
                    if dead:
                        conn.executemany("DELETE FROM main.%s WHERE %s=?" % (t, s["id"]), [(i,) for i in dead])
                    if ins:
                        conn.executemany("INSERT INTO main.%s(%s) VALUES (%s)" % (t, ", ".join(cols), ", ".join(":" + c for c in cols)), ins)
                    res = {"kept": kept, "inserted": len(ins), "deleted": len(dead)}
            if s["kind"] in ("rows", "pk") and (res.get("inserted") or res.get("deleted")):
                try:
                    conn.execute(RS.FEEDVER_SQL, (t,))   # SPEEDFIX_FEEDVER_V1, as rowsync does
                except Exception:  # noqa: BLE001
                    pass
            out[t] = res
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return out


def _published_scoped(conn, s):
    """The table's rows in scope, as comparable tuples (no id column)."""
    from portal import rowsync as RS
    t = s["table"]
    cols = [c for c in (list(s["cols"] or []) + list(s["const"])) if c != (s["id"] if s["kind"] != "pk" else None)]
    if s["kind"] == "pk" and s.get("stable_refs") is not None:
        cols = [c for c in cols if c != s["id"]]
    aff = RS._affinities(conn, t)
    return sorted(tuple(RS._as_stored(v, aff.get(c, "BLOB")) for c, v in zip(cols, tuple(r)))
                  for r in conn.execute("SELECT %s FROM main.%s WHERE %s" % (", ".join(cols), t, _scope_sql(conn, s)))), cols


def _computed(conn, s, cols):
    from portal import rowsync as RS
    aff = RS._affinities(conn, s["table"])
    return sorted(tuple(RS._as_stored(dict(r, **s["const"]).get(c), aff.get(c, "BLOB")) for c in cols) for r in s["rows"])


def _fin_seed_map(conn, specs):
    """financings: compare deal references by the deal's (ticker, seed release), since deal numbers differ."""
    m_pub = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT financing_id, ticker, seed_event_id FROM main.financings")}
    m_new = {r["financing_id"]: (r["ticker"], r["seed_event_id"]) for r in specs[0]["rows"]}
    return m_pub, m_new


def compare(name, conn, specs):
    out = {}
    if name == "financings":
        m_pub, m_new = _fin_seed_map(conn, specs)
        for s in specs:
            pub, cols = _published_scoped(conn, dict(s, kind="rows", id="financing_id") if s["table"] == "financings" else s)
            refs = [i for i, c in enumerate(cols) if c in ("financing_id", "second_financing_id")]
            pub = sorted(tuple(m_pub.get(v, v) if i in refs else v for i, v in enumerate(t)) for t in pub)
            new = sorted(tuple(m_new.get(v, v) if i in refs else v for i, v in enumerate(t)) for t in _computed(conn, s, cols))
            out[s["table"]] = (pub == new, len(new), len(pub), [list(x) for x in sorted(set(pub) ^ set(new))][:3])
        return out
    for s in specs:
        pub, cols = _published_scoped(conn, s)
        new = _computed(conn, s, cols)
        out[s["table"]] = (pub == new, len(new), len(pub), [list(x) for x in sorted(set(pub) ^ set(new))][:3])
    return out


def run(name, conn, version, publish):
    """Called by <publisher>.main() instead of publish(conn, version). Any problem: publish(conn, version)."""
    m = mode(name)
    if m == "off" or name not in ADAPTERS:
        return publish(conn, version)
    t0 = time.time()
    try:
        M = importlib.import_module(ADAPTERS[name]["mod"])
        gfp = global_fp(name, M, version)
        sig = signature(name, M, conn, version)
    except Exception as exc:  # noqa: BLE001
        _log({"pub": name, "mode": m, "error": "signature: %s: %s" % (type(exc).__name__, exc), "action": "full"})
        return publish(conn, version)
    prev = _load_state(name)
    psig = (prev or {}).get("sig", {})
    changed = sorted(t for t in set(sig) | set(psig) if sig.get(t) != psig.get(t))
    t_sig = round(time.time() - t0, 1)
    if m == "shadow":
        if _trading_hours():
            st = publish(conn, version)
            _save_state(name, {"gfp": gfp, "sig": sig, "full_at": time.time()})
            _log({"pub": name, "mode": "shadow", "checked": False, "why": "trading hours", "changed": len(changed), "sig_s": t_sig})
            return st
        try:
            before = table_digest(conn, name)
        except Exception as exc:  # noqa: BLE001
            before = None
            err = "digest: %s: %s" % (type(exc).__name__, exc)
        st = publish(conn, version)
        rec = {"pub": name, "mode": "shadow", "sig_s": t_sig, "tickers": len(sig), "changed": len(changed),
               "changed_sample": changed[:12]}
        try:
            if before is None:
                raise RuntimeError(err)
            after = table_digest(conn, name)
            moved = sorted(t for t in set(before) | set(after) if before.get(t) != after.get(t))
            rec["published_changed"] = len(moved)
            if prev is None or prev.get("gfp") != gfp:
                rec["note"] = "first run or global inputs changed: per-company would have run in full"
            else:
                miss = sorted(set(moved) - set(changed))
                if miss:   # V1.1: data that arrived while this run was publishing shows in a signature taken now
                    sig2 = signature(name, M, conn, version)
                    late = sorted(t for t in miss if sig2.get(t) != sig.get(t))
                    miss = sorted(set(miss) - set(late))
                    rec.update(late=len(late), late_sample=late[:12])
                rec.update(miss=len(miss), miss_sample=miss[:12])
                if changed:
                    t1 = time.time()
                    specs, n_ev = compute_scoped(name, M, conn, version, changed)
                    rec["scoped_s"], rec["scoped_releases"] = round(time.time() - t1, 1), n_ev
                    cmp_ = compare(name, conn, specs)
                    rec["equal"] = all(v[0] for v in cmp_.values())
                    rec["tables"] = {k: {"equal": v[0], "rows": [v[1], v[2]]} for k, v in cmp_.items()}
                    if not rec["equal"]:
                        rec["diff"] = {k: v[3] for k, v in cmp_.items() if not v[0]}
        except Exception as exc:  # noqa: BLE001 - the check is optional; the publish already happened as before
            rec["equal"] = None
            rec["error"] = "check: %s: %s" % (type(exc).__name__, str(exc)[:300])
        _save_state(name, {"gfp": gfp, "sig": sig, "full_at": time.time()})
        rec["seconds"] = round(time.time() - t0, 1)
        _log(rec)
        return st
    # enforce
    age_h = (time.time() - prev["full_at"]) / 3600 if prev else None
    why = ("no state" if prev is None else "global inputs changed" if prev.get("gfp") != gfp
           else "full rebuild due (%.1f h)" % age_h if (age_h >= FULL_MAX_H or (age_h >= FULL_EVERY_H and not _trading_hours()))
           else None)
    if why:
        st = publish(conn, version)
        _save_state(name, {"gfp": gfp, "sig": sig, "full_at": time.time()})
        _log({"pub": name, "mode": "enforce", "action": "full", "why": why, "seconds": round(time.time() - t0, 1)})
        return st
    if not changed:
        _save_state(name, dict(prev, sig=sig))
        _log({"pub": name, "mode": "enforce", "action": "nothing changed", "sig_s": t_sig})
        return {"incremental": True, "changed": 0}
    try:
        specs, n_ev = compute_scoped(name, M, conn, version, changed)
        wr = write_scoped(conn, specs)
    except Exception as exc:  # noqa: BLE001
        _log({"pub": name, "mode": "enforce", "action": "full (per-company failed)", "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])})
        st = publish(conn, version)
        _save_state(name, {"gfp": gfp, "sig": sig, "full_at": time.time()})
        return st
    _save_state(name, dict(prev, sig=sig))
    rec = {"pub": name, "mode": "enforce", "action": "per-company", "changed": len(changed), "changed_sample": changed[:12],
           "releases": n_ev, "write": wr, "sig_s": t_sig, "seconds": round(time.time() - t0, 1)}
    _log(rec)
    return rec
