#!/usr/bin/env python3
"""MNT_CAPCHECK_V4 (2026-11-10, round 10: exact pairing with the guard's row, see mkcap4.py). Was: MNT_CAPCHECK_V3 (2026-11-10, round 7). V2 plus one more kind of first catch:
  * unmatched: a wire/site copy was on MNT first, the exchange path did not recognise it (the TSXV title is only
    "News release" and the PDF headline it read was body text or a footnote), posted its own copy, and the duplicate
    guard dropped that copy against the wire/site copy (dup_guard_log 'skipped_new', exchange source, kept = a
    wire/site copy). The ledger says 'ingested', so V1/V2 scored the release as exchange-only although MNT showed
    the wire copy first. V3 pairs such a ledger row with the guard's row by ticker and time (first_seen within 15 min).
'pct' / 'pct_3day' (and the alert) count first + late + unmatched; 'pct_v2' / 'pct_3day_v2' keep the V2 numbers and
'pct_first' / 'pct_3day_first' the V1 numbers. Read-only on both databases.
Usage: capcheck3.py [--days 10] [--dry] [--list]   (--dry writes nothing; --list prints the newly counted rows)"""
import datetime as dt, hashlib, json, os, re, sqlite3, sys, collections as C
EXDB = "/var/lib/mnt-exchange/exchange_news.db"; PDB = "/opt/mnt/app/portal/portal.db"
OUT = "/var/lib/mnt-exchange/capture.json"; THRESH = 50.0
EXCH = ("tmx", "cse"); PAIR_S = 900
days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 10
dry = "--dry" in sys.argv; show = "--list" in sys.argv
ex = sqlite3.connect(f"file:{EXDB}?mode=ro", uri=True, timeout=30)
pt = sqlite3.connect(f"file:{PDB}?mode=ro", uri=True, timeout=30)
today = dt.datetime.now(dt.timezone.utc).date()
since = (today - dt.timedelta(days=days)).isoformat()


def uid_for(source, ticker, date, title):           # exchange_news.uid_for (the id the exchange path gives its copy)
    return hashlib.sha1("|".join([source, ticker, date[:10], re.sub(r"[^a-z0-9]+", "", (title or "").lower())[:80]])
                        .encode()).hexdigest()


def is_exch(s): return (s or "").split(":")[0].lower() in EXCH


def ts(s):
    try: return dt.datetime.fromisoformat((s or "").replace("T", " ")[:19])
    except ValueError: return None


_src = {}
def src_of(eid):
    if eid not in _src:
        r = pt.execute("SELECT source_name FROM events WHERE event_id=?", (eid,)).fetchone()
        _src[eid] = r[0] if r else None
    return _src[eid]


# dup_guard_log since a few days before the window: find the first id by binary search on the rowid
fwd, rev, repl, logsrc = C.defaultdict(list), C.defaultdict(list), C.defaultdict(list), {}
skips = C.defaultdict(list)                         # V3: TICKER -> [at, kept_id, kept_source, used]
skip_eid, skip_day = {}, C.defaultdict(list)        # V4: the same rows by the skipped copy's id, and by (TICKER, release date)
try:
    hi = pt.execute("SELECT max(id) FROM dup_guard_log").fetchone()[0] or 0
    lo, bound = 1, (today - dt.timedelta(days=days + 3)).isoformat()
    while lo < hi:
        mid = (lo + hi) // 2
        r = pt.execute("SELECT at FROM dup_guard_log WHERE id >= ? ORDER BY id LIMIT 1", (mid,)).fetchone()
        if r is None or (r[0] or "") >= bound: hi = mid
        else: lo = mid + 1
    for action, eid, kept, tk, s, pub, at, ks in pt.execute(
            "SELECT action, event_id, kept_id, ticker, source_name, published_at, at, kept_source FROM dup_guard_log "
            "WHERE id >= ?", (lo,)):
        if action == "skipped_new" and is_exch(s) and ks and not is_exch(ks) and ts(at):
            _row = [ts(at), kept, ks, False]; skips[(tk or "").upper()].append(_row)
            if eid: skip_eid[eid] = _row
            skip_day[((tk or "").upper(), (pub or "")[:10])].append(_row)
        if not eid: continue
        logsrc.setdefault(eid, s)
        if kept: fwd[eid].append(kept)
        if action == "skipped_new" and kept: rev[kept].append(eid)
        if action == "replaced_exchange" and is_exch(s) and kept:
            repl[((tk or "").upper(), (pub or "")[:10])].append(kept)
    log_ok = True
except sqlite3.Error as e:
    print("dup_guard_log not read:", e, file=sys.stderr); log_ok = False


def resolve(eid, depth=0, seen=None):
    """The source of the copy MNT shows now for eid (following the guard's log when eid is gone), or None when that
    copy is an exchange copy or nothing can be found."""
    seen = seen if seen is not None else set()
    if not eid or depth > 6 or eid in seen: return None
    seen.add(eid)
    s = src_of(eid)
    if s is not None:
        return None if is_exch(s) else s
    for k in fwd.get(eid, []):
        r = resolve(k, depth + 1, seen)
        if r: return r
    for e2 in rev.get(eid, []):
        s2 = src_of(e2)
        if s2 and not is_exch(s2): return s2
    return None


per = C.defaultdict(lambda: {"releases": 0, "on_wire": 0, "late": 0, "unm": 0, "by": C.Counter(), "late_by": C.Counter(),
                             "late_how": C.Counter(), "unm_by": C.Counter()})
used = C.Counter(); newly = []; left = []
for uid, d, st, me, src, tk, title, fs in ex.execute(
        "SELECT uid, published_date, status, matched_event, source, ticker, title, first_seen FROM releases "
        "WHERE published_date >= ? AND published_date < ? AND status != 'skipped'", (since, today.isoformat())):
    day = dt.date.fromisoformat(d[:10])
    if day.weekday() > 4: continue
    p = per[d[:10]]; p["releases"] += 1
    s = src_of(me) if me and me != uid else None
    if s is None and me and me != uid and logsrc.get(me) and not is_exch(logsrc[me]):
        s = logsrc[me]                            # the wire/site copy the ledger matched was there first; the guard
                                                  # swapped it later (e.g. a Newsfile short version) -> still first
    if s and not is_exch(s):
        p["on_wire"] += 1; p["by"][s.split(":")[0]] += 1; continue
    if not log_ok: continue
    late, how, still_exch = None, "", False
    for c in [x for x in (me, uid_for(src or "", tk or "", d, title)) if x]:
        if src_of(c) is None:
            late = resolve(c)
            if late: how = "followed"; break
        elif is_exch(src_of(c)):
            still_exch = True                     # this release's exchange copy is still what MNT shows
    if not late and not still_exch:
        key = ((tk or "").upper(), d[:10])
        for k in repl.get(key, [])[used[key]:]:
            used[key] += 1
            late = resolve(k)
            if late: how = "replaced(ticker+date)"; break
    if late:
        p["late"] += 1; p["late_by"][late.split(":")[0]] += 1; p["late_how"][how] += 1; continue
    t0 = ts(fs); best = None                      # V3: the guard dropped the exchange copy against a wire/site copy
    if st == "ingested":                          # V4: exact pairing first (the copy's id, then ticker + release date)
        for _r in [skip_eid.get(c) for c in (me, uid_for(src or "", tk or "", d, title)) if c] + skip_day.get(((tk or "").upper(), d[:10]), []):
            if _r and not _r[3]: best = (0, _r); break
    if best is None and t0 and st == "ingested":
        for row in skips.get((tk or "").upper(), []):
            gap = abs((row[0] - t0).total_seconds())
            if not row[3] and gap <= PAIR_S and (best is None or gap < best[0]): best = (gap, row)
    if best:
        best[1][3] = True; ks = best[1][2].split(":")[0]
        p["unm"] += 1; p["unm_by"][ks] += 1; newly.append((d[:10], tk, ks, (title or "")[:50]))
    else:
        left.append((d[:10], tk, st, (title or "")[:50]))

rows = []
for d in sorted(per):
    p = per[d]; n = p["releases"]
    rows.append({"date": d, "releases": n, "on_wire": p["on_wire"], "late": p["late"], "unmatched": p["unm"],
                 "pct": round(100.0 * (p["on_wire"] + p["late"] + p["unm"]) / n, 1) if n else None,
                 "pct_v2": round(100.0 * (p["on_wire"] + p["late"]) / n, 1) if n else None,
                 "pct_first": round(100.0 * p["on_wire"] / n, 1) if n else None,
                 "by_source": dict(p["by"].most_common()), "late_by_source": dict(p["late_by"].most_common()),
                 "late_how": dict(p["late_how"]), "unmatched_by_source": dict(p["unm_by"].most_common())})
# run in the morning (11:20 UTC): today is left out, so the three most recent full weekdays are judged
judged = [r for r in rows if r["releases"] >= 10][-3:]
tot_r = sum(r["releases"] for r in judged); tot_w = sum(r["on_wire"] for r in judged); tot_l = sum(r["late"] for r in judged)
tot_u = sum(r["unmatched"] for r in judged)
pc = lambda x: round(100.0 * x / tot_r, 1) if tot_r else None
pct3 = pc(tot_w + tot_l + tot_u)
res = {"version": "MNT_CAPCHECK_V4", "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
       "threshold_pct": THRESH, "judged_days": [r["date"] for r in judged], "pct_3day": pct3,
       "pct_3day_v2": pc(tot_w + tot_l), "pct_3day_first": pc(tot_w),
       "alert": bool(pct3 is not None and pct3 < THRESH), "log_read": log_ok, "days": rows}
if show:
    for r in rows: print(r["date"], "n", r["releases"], "first", r["on_wire"], "late", r["late"], "unmatched", r["unmatched"],
                         "| V3", r["pct"], "V2", r["pct_v2"], "V1", r["pct_first"], "|", r["unmatched_by_source"])
    print("3-day:", res["judged_days"], "V3", pct3, "V2", res["pct_3day_v2"], "V1", res["pct_3day_first"])
    print("newly counted:", len(newly))
    for x in newly: print("  +", *x)
    print("still exchange-only:", len(left))
    for x in left: print("  -", *x)
else:
    print(json.dumps(res, indent=1))
if not dry:
    tmp = OUT + ".tmp"; json.dump(res, open(tmp, "w"), indent=1); os.replace(tmp, OUT)
