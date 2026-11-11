#!/usr/bin/env python3
"""USX_SECPROD_V1 - lay figures read from a company's own SEC filings over the release reader's production rows.
The figures file is written by sec_prod.py (MTP side). apply(rows, conn) is called by production_publish.publish()
right after compute(); it changes nothing when the file is missing, unreadable or empty.

For each figure (company, period, metal):
  - a company-level 'actual' row the reader already has for it (asset empty) takes the filing's quantity, keeping its
    sold / cost / guidance columns and its release. It is left as it is when the two agree within 0.5% and the
    release's figure is printed at least as precisely as the filing's (232,396 t against 512.3 million lb);
  - otherwise a row is added on the company's results release nearest the filing date (35 days before to 7 after);
    a figure with no such release is left out and counted.
Rows for single mines (asset filled), guidance rows and rows of other companies are never touched.
Columns the table will not take empty (approx) are filled with the table's own default or 0 (2026-11-11: the first
live publish was refused on approx = empty; nothing had been written).
2026-11-11 gaps: a year-end results release that also declares a dividend (Harmony) and DRDGOLD's "trading
statement and trading update" count as results releases; a plain trading statement still does not.
Kill switch: /opt/mnt/app/portal/production_filings_OFF.

Trial (read-only, prints before / after):   production_filings.py --trial FIGURES.json"""
import datetime
import json
import os
import re
import sys

FIGURES = "/opt/mnt/app/portal/production_filings.json"
OFF = "/opt/mnt/app/portal/production_filings_OFF"
_RESULTS = re.compile(r"(?i)result|quarter|\b[1-4]Q\d\d|earnings|operating update|operational update|trading update|half[- ]year|interim|six months|year ended")
_NOT = re.compile(r"(?i)general meeting|\bAGM\b|exploration|drill|reserves?|trading statement(?! and trading update)")


def _day(s):
    try:
        return datetime.date.fromisoformat((s or "")[:10])
    except Exception:
        return None


def _sig(v):
    return len(("%d" % round(abs(v))).rstrip("0")) or 1


def _must(conn):
    """{column: value to use when empty} for the table's NOT NULL columns."""
    d = {"approx": 0}
    try:
        for cid, name, typ, notnull, dflt, pk in conn.execute("PRAGMA table_info(production_results)"):
            if notnull and not pk:
                if dflt is None:
                    d[name] = 0 if (typ or "").upper() in ("INTEGER", "REAL") else ""
                else:
                    t = str(dflt).strip("'")
                    d[name] = int(t) if re.fullmatch(r"-?\d+", t) else t
    except Exception:
        pass
    return d


def apply(rows, conn, path=None, cols=None):
    st = {"figures": 0, "updated": 0, "added": 0, "same": 0, "no_release": 0}
    path = path or FIGURES
    if os.path.exists(OFF) or not os.path.exists(path):
        return rows, st
    try:
        figs = json.load(open(path)).get("rows") or []
    except Exception:
        return rows, st
    st["figures"] = len(figs)
    must = _must(conn)
    by_tk = {}
    for f in figs:
        by_tk.setdefault(f["ticker"], []).append(f)
    cols = cols or (list(rows[0].keys()) if rows else [])
    have = {}
    evrows = {}
    for r in rows:
        if r.get("ticker") in by_tk:
            evrows.setdefault(r["event_id"], []).append(r)
            if r.get("kind") == "actual" and not r.get("asset"):
                have.setdefault((r["ticker"], r.get("period"), (r.get("metal") or "").lower()), []).append(r)
    left = []
    for tk, fl in by_tk.items():
        evs = [dict(event_id=e, slug=s, raw_headline=h, published_at=p) for e, s, h, p in conn.execute(
            "SELECT event_id, slug, raw_headline, COALESCE(published_at, classified_at) FROM events "
            "WHERE ticker=? AND review_status='auto_approved'", (tk,))]
        evs = [e for e in evs if _day(e["published_at"]) and (e["event_id"] in evrows or
               (_RESULTS.search(e["raw_headline"] or "") and not _NOT.search(e["raw_headline"] or "")))]
        nxt = {}
        for f in fl:
            hit = have.get((tk, f["period"], f["metal"].lower()))
            if hit:
                for r in hit:
                    q = r.get("qty")
                    if q is not None and (r.get("unit") or f["unit"]) == f["unit"]:
                        rel = abs(float(q) - f["qty"]) / max(abs(f["qty"]), 1.0)
                        if rel < 1e-9 or (rel < 0.005 and _sig(float(q)) >= int(f.get("sig") or 99)):
                            st["same"] += 1
                            continue
                    r["qty"] = float(f["qty"]); r["unit"] = f["unit"]; r["approx"] = must.get("approx", 0)
                    r["low"] = r["high"] = None
                    if f.get("basis"):
                        r["basis"] = f["basis"]
                    st["updated"] += 1
                continue
            fd = _day(f["filed"])
            best = None
            for e in evs:
                d = (_day(e["published_at"]) - fd).days
                if -35 <= d <= 7:
                    k = (0 if e["event_id"] in evrows else 1, abs(d))
                    if best is None or k < best[0]:
                        best = (k, e)
            if not best:
                st["no_release"] += 1
                left.append("%s %s %s" % (tk, f["period"], f["metal"]))
                continue
            e = best[1]
            n = nxt.get(e["event_id"], 100)
            nxt[e["event_id"]] = n + 1
            r = {c: None for c in cols}
            r.update(event_id=e["event_id"], ordinal=n, ticker=tk, slug=e["slug"], kind="actual", period=f["period"],
                     period_end=f["period_end"], metal=f["metal"], unit=f["unit"], qty=float(f["qty"]),
                     basis=f.get("basis") or None, n_rows=len(evrows.get(e["event_id"], [])) or 1, tag_confirmed=1,
                     raw_headline=(e["raw_headline"] or "")[:500], published_at=e["published_at"])
            for k, v in must.items():
                if k in r and r[k] is None:
                    r[k] = v
            rows.append(r)
            st["added"] += 1
    if left:
        st["left_out"] = left[:60]
    return rows, st


def _trial(path):
    import copy, sqlite3
    sys.path.insert(0, "/opt/mnt/app")
    from portal import production_publish as P
    conn = sqlite3.connect("file:%s?mode=ro" % P.DB, uri=True)
    v = P.active_version(conn)
    rows, st0 = P.compute(P.load_items(conn, v))
    tks = sorted({f["ticker"] for f in json.load(open(path))["rows"]})
    key = lambda r: (r["ticker"], r.get("metal") or "", r.get("period_end") or "", r.get("period") or "", r["event_id"], r.get("ordinal") or 0)
    before = {(r["event_id"], r["ordinal"]): copy.deepcopy(r) for r in rows if r["ticker"] in tks}
    nb = len(rows)
    rows, st = apply(rows, conn, path, list(P._COLS))
    print("version", v, "| rows before", nb, "after", len(rows), "|", json.dumps({k: x for k, x in st.items() if k != "left_out"}))
    print("must-have columns:", _must(conn), "| rows that would be refused:", sum(1 for r in rows for k in _must(conn) if k in r and r[k] is None))
    lo = st.get("left_out", [])
    print("no release on MNT to hang it on (%d): %s" % (len(lo), "; ".join(lo)))
    print("%-8s %-7s %-8s %15s %15s %-3s %-10s %s" % ("company", "metal", "period", "was", "now", "", "basis", "release"))
    for r in sorted((r for r in rows if r["ticker"] in tks and r.get("kind") == "actual" and not r.get("asset") and (r.get("period_end") or "") >= "2025-07-01"), key=key):
        b = before.get((r["event_id"], r["ordinal"]))
        was = "-" if b is None else ("{:,.0f}".format(b["qty"]) if b.get("qty") is not None else "none")
        now = "{:,.0f}".format(r["qty"]) if r.get("qty") is not None else "none"
        flag = "" if was == now else ("NEW" if b is None else "CHG")
        print("%-8s %-7s %-8s %15s %15s %-3s %-10s %s %s %s" % (r["ticker"], r["metal"], r["period"], was, now, r.get("unit") or "", r.get("basis") or "", (r["published_at"] or "")[:10], (r["raw_headline"] or "")[:30], flag))
    other = [r for r in rows if r["ticker"] not in tks]
    print("rows of other companies:", len(other), "(untouched)")


if __name__ == "__main__":
    if "--trial" in sys.argv:
        _trial(sys.argv[sys.argv.index("--trial") + 1])
