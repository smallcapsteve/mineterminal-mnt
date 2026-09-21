#!/usr/bin/env python3
"""ECON_V1 stage check, run from the candidate tree against the LIVE database, read-only.

  1. the confirmed set, scored the way the gate will score it (through the publisher's rules);
  2. every approved release that mentions an NPV or an IRR, plus every tagged release, run through
     the reader and the publisher in memory: what the page would hold, which studies would be left
     out as someone else's, a sample of what detection adds outside the tag, and anything implausible;
  3. the reader's speed.
Writes nothing to portal.db.
"""
import json
import random
import sqlite3
import statistics
import sys
import time

sys.path.insert(0, ".")
from portal import accuracy as A  # noqa: E402
from portal import economics_publish as P  # noqa: E402
from portal import facts as F  # noqa: E402
from portal.extractors import economics as X  # noqa: E402

DB = "file:/opt/mnt/app/portal/portal.db?mode=ro"
conn = sqlite3.connect(DB, uri=True)
conn.row_factory = sqlite3.Row
names = P.company_names()


def parsed_of(recs):
    rows = {i: [(f.field, f.seq, f.value_num, f.value_text) for f in r.facts] for i, r in enumerate(recs)}
    return X.parse_records(rows)


# ---------------------------------------------------------------- 1. the set
aset = A.load_set("accuracy/sets/economics.json")
spec = A.SPECS["economics"]
events = A.load_events(conn, aset)
tick = {it["event_id"]: it["ticker"] for it in aset["items"]}


def predict(it, ev):
    p = parsed_of(X.extract(ev["raw_headline"] or "", ev["raw_body"] or ""))
    if not p.get("scenarios") or P.someone_elses(p, ev["ticker"], names):
        return None
    return {"rows": [{k: s.get(k) for k in ("scenario", "study_type", "context", "basis", "currency",
                                              "discount_pct", "npv_pre_tax", "npv_after_tax", "irr_pre_tax_pct",
                                              "irr_after_tax_pct", "payback_years", "initial_capex",
                                              "capex_sensitivity", "mine_life_years")} for s in p["scenarios"]]}


rep = A.evaluate(spec, aset, predict, events)
print("== 1. confirmed set, scored as the gate will score it")
for line in A.summary_lines(rep):
    print("  " + line)
bad = [f for f, d in rep["fields"].items() if d["key"] and (d["claims"] < A.MIN_CLAIMS or (d["precision"] or 0) < A.THRESHOLD)]
print("  set usable: %s %s" % (rep["set_usable"], rep["set_unusable_reasons"]))
print("  VERDICT: %s" % ("would pass on precision" if not bad and rep["set_usable"] and rep["n_stale"] == 0
                        else "WOULD FAIL: %s stale=%d" % (bad, rep["n_stale"])))

# ---------------------------------------------------------------- 2. the corpus
print("\n== 2. the corpus, in memory")
q = ("SELECT event_id, ticker, COALESCE(published_at, classified_at) AS published_at, raw_headline, raw_body, "
     "slug, categories FROM events WHERE review_status='auto_approved' AND ("
     " raw_body LIKE '%NPV%' OR raw_body LIKE '%net present value%' OR raw_body LIKE '%IRR%'"
     " OR raw_body LIKE '%internal rate of return%' OR raw_headline LIKE '%NPV%'"
     " OR ('|' || COALESCE(categories,'') || '|') LIKE '%|Economic Studies|%')")
items, times, errors = [], [], []
t_all = time.time()
for ev in conn.execute(q):
    t0 = time.perf_counter()
    try:
        recs = X.extract(ev["raw_headline"] or "", ev["raw_body"] or "")
    except Exception as e:  # noqa: BLE001
        errors.append((ev["event_id"][:10], "%s: %s" % (type(e).__name__, e)))
        continue
    times.append((time.perf_counter() - t0) * 1000)
    tagged = ("|" + (ev["categories"] or "") + "|").find("|Economic Studies|") >= 0
    p = parsed_of(recs)
    if p.get("scenarios") or tagged:
        items.append(({"event_id": ev["event_id"], "ticker": ev["ticker"], "published_at": ev["published_at"],
                       "raw_headline": ev["raw_headline"], "slug": ev["slug"], "tagged": tagged}, p))
rows, st = P.compute(items, names)
print("  releases read: %d in %.0fs; extract errors: %d %s" % (len(times), time.time() - t_all, len(errors), errors[:5]))
times.sort()
print("  speed: median %.1f ms, p95 %.1f ms, max %.0f ms" % (statistics.median(times), times[int(len(times) * .95)], times[-1]))
print("  publisher stats: " + json.dumps(st))
real = [r for r in rows if r["scenario"]]
rel = {}
for r in real:
    rel.setdefault(r["event_id"], []).append(r)
ann = {e for e, rs in rel.items() if rs[0]["context"] == "announced"}
print("  releases with rows: %d (announced %d, restating %d); tagged %d, untagged %d" % (
    len(rel), len(ann), len(rel) - len(ann), sum(1 for rs in rel.values() if rs[0]["tag_confirmed"]),
    sum(1 for rs in rel.values() if not rs[0]["tag_confirmed"])))
print("  rows: %d (announced %d); markers %d" % (len(real), sum(1 for r in real if r["context"] == "announced"),
                                                   len(rows) - len(real)))
by_study = {}
for r in real:
    by_study[r["study_type"]] = by_study.get(r["study_type"], 0) + 1
print("  rows by study type: %s" % by_study)

print("\n  -- left out as someone else's study (all):")
for ev, p in items:
    if p.get("scenarios") and P.someone_elses(p, ev["ticker"], names):
        print("    %-9s %s | owner %r | issuer %r | %s" % (ev["ticker"], (ev["published_at"] or "")[:10], p["owner_name"],
                                                         names.get(ev["ticker"], ""), (ev["raw_headline"] or "")[:80]))

rnd = random.Random(20260921)
for label, pick in (("untagged, announced", [e for e in rel if e in ann and not rel[e][0]["tag_confirmed"]]),
                    ("untagged, restating", [e for e in rel if e not in ann and not rel[e][0]["tag_confirmed"]]),
                    ("tagged, announced", [e for e in rel if e in ann and rel[e][0]["tag_confirmed"]])):
    sample = rnd.sample(sorted(pick), min(15, len(pick)))
    print("\n  -- sample: %s (%d of %d)" % (label, len(sample), len(pick)))
    for e in sample:
        r = rel[e][0]
        print("    %-9s %s %-3s %-28s NPV %-10s IRR %-6s | %s" % (
            r["ticker"], (r["published_at"] or "")[:10], r["study_type"] or "-", (r["scenario"] or "")[:28],
            P.fmt_money(r["npv_after_tax"] or r["npv_pre_tax"], r["currency"]), P.fmt_pct(r["irr_after_tax_pct"]),
            (r["raw_headline"] or "")[:70]))

print("\n  -- implausible values (all):")
for r in real:
    why = []
    v = r["npv_after_tax"] or r["npv_pre_tax"]
    if v is not None and (v > 3e10 or v < 1e5):
        why.append("npv %s" % P.fmt_money(v, r["currency"]))
    for k in ("irr_after_tax_pct", "irr_pre_tax_pct"):
        if r[k] is not None and (r[k] > 300 or r[k] <= 0):
            why.append("%s %s" % (k, r[k]))
    if r["payback_years"] is not None and r["payback_years"] > 25:
        why.append("payback %s" % r["payback_years"])
    if r["initial_capex"] is not None and (r["initial_capex"] > 2e10 or r["initial_capex"] < 1e5):
        why.append("capex %s" % P.fmt_money(r["initial_capex"], r["currency"]))
    if r["discount_pct"] is not None and r["discount_pct"] not in (3, 4, 5, 6, 7, 8, 9, 10, 12, 15):
        why.append("discount %s" % r["discount_pct"])
    if why:
        print("    %-9s %s %-24s %s | %s" % (r["ticker"], (r["published_at"] or "")[:10], (r["scenario"] or "")[:24],
                                         "; ".join(why), (r["raw_headline"] or "")[:60]))
print("REPRO_ECON_DONE")
