import re, sqlite3, json
c = sqlite3.connect("file:/opt/mnt/app/portal/portal.db?mode=ro", uri=True)
IDS = ["d5f64adab574", "021e7fa4a6f5", "4d697c7dba45", "d7daba4a7b7b", "d691a2d633fc", "47ad8a47949a",
       "fd8a0cf231ef", "ba6bd331d4df", "ba4cf96fbeab", "f22e73961e8c"]
PAT = re.compile(r"(?i)(guidance|outlook|produced|production of|pounds of|ounces of gold|AISC|poured)")
out = {}
for p in IDS:
    r = c.execute("SELECT ticker, raw_body FROM events WHERE event_id LIKE ?", (p + "%",)).fetchone()
    b = " ".join((r[1] or "")[9000:].split())
    snips, last = [], -1
    for m in PAT.finditer(b):
        if m.start() < last:
            continue
        s = b[max(0, m.start() - 160): m.end() + 220]
        snips.append(s); last = m.end() + 220
        if sum(map(len, snips)) > 2600:
            break
    out[p] = {"ticker": r[0], "tail_len": len(b), "snips": snips}
print(json.dumps(out, ensure_ascii=True))
