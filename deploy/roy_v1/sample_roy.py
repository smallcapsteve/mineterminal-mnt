#!/usr/bin/env python3
"""ROY answer-key sample (read-only, 2026-09-21): 50 releases, stratified. Prints chunk K/N of the sample as
gzip+base64 JSON with the full release text (capped at 30,000 characters)."""
import base64, json, random, re, sqlite3, sys, zlib
c = sqlite3.connect("file:/opt/mnt/app/portal/portal.db?mode=ro", uri=True)
TAG = "Royalties & Streams"
rows = c.execute("SELECT event_id, ticker, COALESCE(published_at, classified_at), raw_headline, raw_body, categories "
                 "FROM events WHERE review_status='auto_approved' AND length(raw_body) >= 400").fetchall()
tag = lambda r: ("|" + (r[5] or "") + "|").find("|" + TAG + "|") >= 0
H = lambda r: r[3] or ""
tagged = [r for r in rows if tag(r)]
DEAL = r"(?i)acqui|purchas|sell|sale|sold|buy[\s-]?back|buy[\s-]?down|repurchas|grant|amend|financing|stream|NSR|royalty\s+(?:agreement|transaction)"
NONMIN = r"(?i)music|TV cues|film|pharma|oil\s+and\s+gas|\bboe\b|barrels"
strata = {
 "tagged_deal": [r for r in tagged if re.search(DEAL, H(r)) and not re.search(NONMIN, H(r))],
 "tagged_stream": [r for r in tagged if re.search(r"(?i)\bstream", H(r))],
 "tagged_other": [r for r in tagged if not re.search(DEAL, H(r))],
 "out_of_scope": [r for r in tagged if re.search(NONMIN, H(r) + " " + (r[4] or "")[:2000])],
 "untagged_candidate": [r for r in rows if not tag(r) and re.search(r"(?i)\b(royalt\w*|stream|NSR)\b", H(r))],
 "passing_mention": [r for r in rows if not tag(r) and re.search(r"(?i)\bNSR\b|net\s+smelter\s+return", (r[4] or "")[:6000])
                     and re.search(r"(?i)drill|intersect|assay|resource|PEA|exploration", H(r))],
}
want = {"tagged_stream": 6, "tagged_deal": 18, "tagged_other": 8, "out_of_scope": 4, "untagged_candidate": 8, "passing_mention": 6}
rnd = random.Random(20260921)
seen, out = set(), []
for s in ("tagged_stream", "out_of_scope", "tagged_deal", "tagged_other", "untagged_candidate", "passing_mention"):
    pool = [r for r in strata[s] if r[0] not in seen]
    for r in rnd.sample(pool, min(want[s], len(pool))):
        seen.add(r[0])
        out.append({"event_id": r[0][:12], "ticker": r[1], "date": (r[2] or "")[:10], "stratum": s, "categories": r[5],
                    "headline": H(r), "n_body": len(r[4] or ""), "body": (r[4] or "")[:30000]})
k, n = [int(x) for x in sys.argv[1].split("/")]
part = [o for i, o in enumerate(out) if i % n == k]
print(len(out), {s: sum(1 for o in out if o["stratum"] == s) for s in want})
print(base64.b64encode(zlib.compress(json.dumps(part).encode(), 9)).decode())
