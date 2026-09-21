#!/usr/bin/env python3
"""EXPL corpus run (read-only): the candidate reader over every approved release. Writes a summary and a
random sample of rows (with the sentence each came from) to /var/tmp/mnt-expl/corpus_<tag>.json."""
import collections, json, random, sqlite3, sys, time
sys.path.insert(0, sys.argv[1])            # the candidate tree
from portal.extractors import exploration as X
tag = sys.argv[2]
c = sqlite3.connect("file:/opt/mnt/app/portal/portal.db?mode=ro", uri=True)
rows = c.execute("SELECT event_id, ticker, COALESCE(published_at, classified_at), raw_headline, raw_body, categories "
                 "FROM events WHERE review_status='auto_approved'").fetchall()
t0 = time.time()
out, st = [], collections.Counter()
errs = []
for eid, tk, pub, hl, body, cats in rows:
    tagged = ("|" + (cats or "") + "|").find("|Exploration Programs|") >= 0
    try:
        a = X.analyse(hl or "", body or "")
    except Exception as e:  # noqa
        errs.append((eid, repr(e)[:200])); continue
    rs = a["rows"]
    st["releases"] += 1
    st["tagged"] += tagged
    if rs:
        st["with_rows"] += 1
        st["tagged_with_rows" if tagged else "untagged_with_rows"] += 1
    for r in rs:
        st["rows"] += 1
        st["type_" + r["program_type"]] += 1
        st["status_" + r["status"]] += 1
        st["historical"] += bool(r["historical"])
        out.append({"e": eid[:12], "t": tk, "d": (pub or "")[:10], "tg": int(tagged), "h": (hl or "")[:140],
                    **{k: r.get(k) for k in ("program_type", "project", "status", "metres", "holes", "season", "phase",
                                             "historical", "operator", "line_km")},
                    "src": (r.get("_src") or "HEADLINE")[:260]})
st["seconds"] = round(time.time() - t0, 1)
st["errors"] = len(errs)
rnd = random.Random(20260921)
sample = rnd.sample(out, min(200, len(out)))
json.dump({"stats": st, "errors": errs[:20], "sample": sample,
           "by_ticker_top": collections.Counter(r["t"] for r in out).most_common(15)},
          open("/var/tmp/mnt-expl/corpus_%s.json" % tag, "w"))
print(json.dumps(st))
