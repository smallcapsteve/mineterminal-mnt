#!/usr/bin/env python3
"""PROD answer-key sample (read-only): 50 releases, stratified, with their bodies."""
import json, random, re, sqlite3
c = sqlite3.connect("file:/opt/mnt/app/portal/portal.db?mode=ro", uri=True)
TAG = "Production Results"
rows = c.execute("SELECT event_id, ticker, COALESCE(published_at, classified_at), raw_headline, raw_body, categories "
                 "FROM events WHERE review_status='auto_approved' AND length(raw_body) >= 400").fetchall()
tag = lambda r: ("|" + (r[5] or "") + "|").find("|" + TAG + "|") >= 0
H = lambda r: r[3] or ""
tagged = [r for r in rows if tag(r)]
OIL = r"\b(oil|natural gas|boe|barrels?|bbl|mcf)\b"
MILE = r"commercial production|first (gold|dor|pour|concentrate|shipment|delivery)|suspend|restart|resum|commenc\w+ (mining|production|operations)|achiev\w+ .{0,30}(production rate|nameplate)"
PER = r"\bQ[1-4]\b|quarter|full[\s-]year|annual|year[\s-]end|\b20\d\d (production|results)|month"
strata = {
 "out_of_scope": [r for r in tagged if re.search(OIL, H(r) + " " + (r[4] or "")[:1500], re.I) or re.search(r"royalty payment", H(r), re.I)],
 "milestone": [r for r in tagged if re.search(MILE, H(r), re.I) and not re.search(PER, H(r), re.I)],
 "guidance": [r for r in tagged if re.search(r"guidance|outlook", H(r), re.I)],
 "financial": [r for r in tagged if "Financials" in (r[5] or "") and not re.search(r"guidance", H(r), re.I)],
 "periodic": [r for r in tagged if re.search(PER, H(r), re.I) and re.search(r"production|produc|ounces|oz|tonnes|operat", H(r), re.I)],
 "untagged_candidate": [r for r in rows if not tag(r) and re.search(r"\b(production|produced|ounces)\b", H(r), re.I)
                        and re.search(r"\bQ[1-4]\b|quarter|year|record|guidance|operat", H(r), re.I)],
 "tagged_other": tagged,
}
want = {"periodic": 16, "guidance": 7, "milestone": 8, "financial": 5, "out_of_scope": 4, "untagged_candidate": 7, "tagged_other": 3}
rnd = random.Random(20260921)
seen, out = set(), []
for s in ("out_of_scope", "milestone", "guidance", "financial", "periodic", "untagged_candidate", "tagged_other"):
    pool = [r for r in strata[s] if r[0] not in seen]
    for r in rnd.sample(pool, min(want[s], len(pool))):
        seen.add(r[0])
        out.append({"event_id": r[0][:12], "ticker": r[1], "date": (r[2] or "")[:10], "stratum": s,
                    "categories": r[5], "headline": H(r), "n_body": len(r[4] or ""), "body": (r[4] or "")[:9000]})
print(json.dumps(out, ensure_ascii=False))
