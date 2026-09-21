#!/usr/bin/env python3
"""PROD baseline (read-only): what the Production Results tag holds today."""
import collections, random, re, sqlite3
c = sqlite3.connect("file:/opt/mnt/app/portal/portal.db?mode=ro", uri=True)
TAG = "Production Results"
rows = c.execute("SELECT event_id, ticker, COALESCE(published_at, classified_at), raw_headline, raw_body, categories "
                 "FROM events WHERE review_status='auto_approved'").fetchall()
tagged = [r for r in rows if ("|" + (r[5] or "") + "|").find("|" + TAG + "|") >= 0]
print("approved:", len(rows), "tagged:", len(tagged), "tickers:", len({r[1] for r in tagged}))
yr = collections.Counter((r[2] or "")[:4] for r in tagged); print("by year:", sorted(yr.items()))
print("co-tags:", collections.Counter(t for r in tagged for t in (r[5] or "").split("|") if t and t != TAG).most_common(10))
blen = [len(r[4] or "") for r in tagged]; blen.sort()
print("body length median/p10:", blen[len(blen)//2], blen[len(blen)//10], "under 400:", sum(1 for b in blen if b < 400))
H = lambda r: (r[3] or "")
pat = {
 "quarter (Q1..Q4)": r"\bQ[1-4]\b|\b(first|second|third|fourth)\s+quarter",
 "year / annual": r"\b(full[\s-]year|annual|fy\s?20\d\d|20\d\d\s+(production|results))",
 "month": r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
 "guidance": r"guidance|outlook|forecast",
 "record": r"\brecord\b",
 "financial results": r"financial\s+results|revenue|earnings|net income",
 "ounces/oz": r"\b(ounces?|oz|koz|GEOs?|AuEq|gold equivalent)\b",
 "tonnes/lb": r"\b(tonnes?|lbs?|pounds?)\b",
 "commercial production": r"commercial\s+production|first\s+(gold|pour|concentrate)",
 "AISC": r"\bAISC\b|all[\s-]in\s+sustaining",
}
for k, p in pat.items():
    print("  headline %-22s %4d" % (k, sum(1 for r in tagged if re.search(p, H(r), re.I))))
    print("  body     %-22s %4d" % (k, sum(1 for r in tagged if re.search(p, (r[4] or "")[:4000], re.I))))
metals = {"gold": r"\bgold\b|\bAu\b", "silver": r"\bsilver\b|\bAg\b", "copper": r"\bcopper\b", "zinc/lead": r"\bzinc\b|\blead\b",
          "uranium": r"uranium|U3O8", "lithium": r"lithium|spodumene", "PGM": r"platinum|palladium|PGM", "coal/iron": r"\bcoal\b|iron ore"}
print("metal in headline+lede:", {k: sum(1 for r in tagged if re.search(p, H(r) + " " + (r[4] or "")[:1500], re.I)) for k, p in metals.items()})
# how many tickers report repeatedly (producers)
per = collections.Counter(r[1] for r in tagged); print("tickers with 4+ tagged releases:", sum(1 for v in per.values() if v >= 4), per.most_common(15))
# untagged headlines that look like production reports
cand = [r for r in rows if r not in tagged and re.search(r"\b(production|produced|ounces)\b", H(r), re.I)
        and re.search(r"\bQ[1-4]\b|quarter|year|record|guidance|operat", H(r), re.I)]
print("untagged headline candidates:", len(cand))
rnd = random.Random(20260921)
print("\n-- 30 tagged headlines (random)")
for r in rnd.sample(tagged, 30): print("  %-9s %s %s" % (r[1], (r[2] or "")[:10], H(r)[:120]))
print("\n-- 20 untagged candidates (random)")
for r in rnd.sample(cand, min(20, len(cand))): print("  %-9s %s %s" % (r[1], (r[2] or "")[:10], H(r)[:120]))
print("BASELINE_DONE")
