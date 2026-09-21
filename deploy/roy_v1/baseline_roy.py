#!/usr/bin/env python3
"""ROY baseline (read-only, 2026-09-21): what the Royalties & Streams tag holds today."""
import collections, random, re, sqlite3
c = sqlite3.connect("file:/opt/mnt/app/portal/portal.db?mode=ro", uri=True)
TAG = "Royalties & Streams"
rows = c.execute("SELECT event_id, ticker, COALESCE(published_at, classified_at), raw_headline, raw_body, categories "
                 "FROM events WHERE review_status='auto_approved'").fetchall()
tagged = [r for r in rows if ("|" + (r[5] or "") + "|").find("|" + TAG + "|") >= 0]
print("approved:", len(rows), "tagged:", len(tagged), "tickers:", len({r[1] for r in tagged}))
print("by year:", sorted(collections.Counter((r[2] or "")[:4] for r in tagged).items()))
print("co-tags:", collections.Counter(t for r in tagged for t in (r[5] or "").split("|") if t and t != TAG).most_common(12))
blen = sorted(len(r[4] or "") for r in tagged)
print("body median/p10:", blen[len(blen)//2], blen[len(blen)//10], "under 400:", sum(1 for b in blen if b < 400))
H = lambda r: r[3] or ""
B = lambda r: (r[4] or "")[:5000]
pat = {
 "NSR": r"\bNSR\b|net\s+smelter", "GRR/gross": r"\bGRR\b|gross\s+(revenue|overriding)", "NPI": r"\bNPI\b|net\s+profits?\s+interest",
 "stream": r"\bstream", "sells/sale of royalty": r"(sell|sale|sold|dispos)\w*\s+(?:of\s+)?(?:an?\s+|its\s+|the\s+)?(?:\w+\s+){0,3}(royalt|stream)",
 "acquires royalty": r"acqui\w*\s+(?:an?\s+|the\s+)?(?:\w+\s+){0,3}(royalt|stream)",
 "buyback/repurchase": r"buy[\s-]?back|repurchas|buy[\s-]?down", "grants/creates royalty": r"grant\w*\s+(?:an?\s+)?(?:\w+\s+){0,2}royalt",
 "percent": r"\d+(?:\.\d+)?\s?%", "US$ amount": r"(US|C|CA|A)?\$\s?\d", "payment received": r"royalty\s+(payment|revenue|income)",
 "GEO": r"\bGEOs?\b|gold\s+equivalent", "quarterly results": r"\bQ[1-4]\b|quarter|financial\s+results",
}
for k, p in pat.items():
    print("  %-26s headline %4d  body %4d" % (k, sum(1 for r in tagged if re.search(p, H(r), re.I)),
                                             sum(1 for r in tagged if re.search(p, B(r), re.I))))
names = re.compile(r"(?i)royalt(y|ies)\s+(corp|inc|ltd|limited)|franco|wheaton|osisko\s+gold\s+royalt|sandstorm|triple\s+flag|metalla|gold\s+royalty|elemental|versamet|vox\s+royalty")
print("issuer is a royalty co (name in headline):", sum(1 for r in tagged if names.search(H(r))))
per = collections.Counter(r[1] for r in tagged); print("top tickers:", per.most_common(15))
cand = [r for r in rows if r not in tagged and re.search(r"(?i)\b(royalt\w*|stream|NSR)\b", H(r))]
print("untagged headline candidates:", len(cand))
rnd = random.Random(20260921)
print("\n-- 40 tagged headlines (random)")
for r in rnd.sample(tagged, min(40, len(tagged))): print("  %-9s %s %s" % (r[1], (r[2] or "")[:10], H(r)[:125]))
print("\n-- 20 untagged candidates (random)")
for r in rnd.sample(cand, min(20, len(cand))): print("  %-9s %s %s" % (r[1], (r[2] or "")[:10], H(r)[:125]))
print("BASELINE_DONE")
