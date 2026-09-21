#!/bin/bash
# PROD_V1 go-live: gate the backfilled reader (unless the 30-minute job already has), publish
# production_results, then give /production-results its own page. Each step stops the run if it fails; the
# page is switched only after the table exists, and is switched back if any page stops answering. (2026-09-21)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
W=/var/tmp/mnt-prod1
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
DB=$LIVE/portal/portal.db
B=/var/tmp/mnt-prod1-page-backup-$(date -u +%Y%m%d-%H%M%S)
q() { $PY -c "import sqlite3, sys; c = sqlite3.connect('file:$DB?mode=ro', uri=True); print(c.execute(sys.argv[1]).fetchall())" "$1"; }

systemctl is-active --quiet fx-backfill-production && { echo "REFUSED: backfill still running"; exit 2; }
echo "backfill: $(systemctl show fx-backfill-production -p Result --value 2>/dev/null)"
V=${PROD_VERSION:?set PROD_VERSION}
q "SELECT extractor, version, status FROM fx_extractor_versions WHERE extractor='production'"
q "SELECT COUNT(*), SUM(status='error') FROM fx_runs WHERE extractor='production' AND version='$V'"
q "SELECT COUNT(*) FROM events WHERE review_status='auto_approved'"

echo "--- gate"
cd $LIVE || exit 2
st=$(q "SELECT status FROM fx_extractor_versions WHERE extractor='production' AND version='$V'")
rc=-
if [ "$st" != "[('active',)]" ]; then
  runuser -u mnt -- $PY accuracy_run.py gate production 2>&1 | tail -30
  rc=${PIPESTATUS[0]}
  st=$(q "SELECT status FROM fx_extractor_versions WHERE extractor='production' AND version='$V'")
fi
echo "gate rc=$rc status=$st"
[ "$st" = "[('active',)]" ] || { echo "NOT ACTIVATED: the page is untouched"; exit 3; }

echo "--- publish"
runuser -u mnt -- $PY -m portal.production_publish || { echo "PUBLISH FAILED: the page is untouched"; exit 3; }
q "SELECT kind, COUNT(*), COUNT(DISTINCT event_id), SUM(tag_confirmed) FROM production_results GROUP BY kind"

echo "--- the page"
cur=$(sha256sum $LIVE/portal/app.py | cut -c1-12)
[ "$cur" = "0d83dc2ec9b1" ] || { echo "REFUSED: live app.py is $cur, not the 0d83dc2ec9b1 the route was patched onto"; exit 3; }
new=$(sha256sum $W/cand/portal/app.py | cut -c1-12)
[ "$new" = "9ee84f7a22a3" ] || { echo "REFUSED: candidate app.py is $new"; exit 3; }
install -d -o mnt -g mnt $B && install -o mnt -g mnt -m 644 $LIVE/portal/app.py $B/app.py
echo "backup: $B/app.py"
install -o mnt -g mnt -m 644 $W/cand/portal/app.py $LIVE/portal/app.py
find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
systemctl restart mnt-portal
sleep 4
# the portal takes 12-30 s to answer after a restart while backfills are running
for i in $(seq 1 45); do
  code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)
  [ "$code" = "200" ] && break
  sleep 2
done
bad=0
for p in / /production-results "/production-results?kind=guidance" "/production-results?kind=milestone" \
         "/production-results?show=all" "/production-results?metal=gold" /economic-studies /resources /drills \
         /financings /management-changes /search; do
  c=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8001$p")
  echo "  $c $p"
  [ "$c" = "200" ] || bad=1
done
curl -s http://127.0.0.1:8001/production-results > $W/page.html
grep -q 'pr-table' $W/page.html || bad=1
code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)
echo "healthz: $code   rows on page one: $(grep -c '<tr class=' $W/page.html)"
if [ "$code" != "200" ] || [ "$bad" != "0" ]; then
  echo "ROLLING BACK THE PAGE"
  install -o mnt -g mnt -m 644 $B/app.py $LIVE/portal/app.py
  find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
  systemctl restart mnt-portal
  for i in $(seq 1 45); do
    c=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz); [ "$c" = "200" ] && break; sleep 2
  done
  echo "healthz after rollback: $c"
  exit 3
fi
$PY - $W/page.html <<'PY'
import html, re, sys
h = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'<span class="muted">(.*?)</span>', h, re.S)
print("  counts:", " ".join(html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).split()) if m else "?")
t = h[h.find("<tbody>"):h.find("</tbody>")]
for tr in re.findall(r"<tr.*?</tr>", t, re.S)[:25]:
    cells = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split()) for c in re.findall(r"<td.*?</td>", tr, re.S)]
    print("  | " + " | ".join(cells)[:190])
PY
echo "PAGE_PROD_DONE $(date -u +%FT%TZ)"
