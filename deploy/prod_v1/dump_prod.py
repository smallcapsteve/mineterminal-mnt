"""PROD_V1 dev: dump the full text of the labelled releases (read-only), gzip+base64, one chunk."""
import base64, json, sqlite3, sys, zlib
c = sqlite3.connect("file:/opt/mnt/app/portal/portal.db?mode=ro", uri=True)
ids = sys.argv[2].split(",")
k, n = [int(x) for x in sys.argv[1].split("/")]
out = {}
for i, p in enumerate(ids):
    if i % n != k:
        continue
    r = c.execute("SELECT event_id, ticker, COALESCE(published_at, classified_at), raw_headline, raw_body, categories "
                  "FROM events WHERE event_id LIKE ?", (p + "%",)).fetchall()
    out[p] = [list(x) for x in r]
print(base64.b64encode(zlib.compress(json.dumps(out).encode(), 9)).decode())
