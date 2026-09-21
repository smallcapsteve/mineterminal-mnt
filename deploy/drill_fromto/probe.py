"""DRILL from-to probe (read-only, 2026-09-21): how often intervals carry from/to, and the CADY release."""
import sqlite3, json
c = sqlite3.connect("file:/opt/mnt/app/portal/portal.db?mode=ro", uri=True)
q = lambda s, a=(): c.execute(s, a).fetchall()
print("cols", [r[1] for r in q("PRAGMA table_info(drill_intervals)")])
print("active", q("SELECT version FROM fx_extractor_versions WHERE extractor='drill_results' AND status='active'"))
print("totals", q("SELECT COUNT(*), SUM(from_m IS NOT NULL), SUM(to_m IS NOT NULL), COUNT(DISTINCT event_id) FROM drill_intervals"))
print("releases with no from on any interval", q("SELECT COUNT(*) FROM (SELECT event_id FROM drill_intervals GROUP BY event_id HAVING SUM(from_m IS NOT NULL)=0)"))
ev = q("SELECT event_id, raw_headline, raw_body FROM events WHERE slug='cadillac-mines-extends-kerr-addison-mineralization-over-350'")
for eid, hl, body in ev:
    print("EVENT", eid, hl)
    for r in q("SELECT * FROM drill_intervals WHERE event_id=?", (eid,)):
        print("  ", r)
    i = body.find("From")
    print("BODY_LEN", len(body))
    print(json.dumps(body[max(0, i - 1500): i + 3500]))
