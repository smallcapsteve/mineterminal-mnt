#!/bin/bash
# ECON_V1 1.0.0 go-live: gate the backfilled reader, publish economic_studies, then give
# /economic-studies its own page. Each step stops the run if it fails; the page is switched only
# after the table exists, and is switched back if any page stops answering. (2026-09-21)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
W=/var/tmp/mnt-econ1
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
DB=$LIVE/portal/portal.db
B=/var/tmp/mnt-econ1-page-backup-$(date -u +%Y%m%d-%H%M%S)
q() { $PY -c "import sqlite3, sys; c = sqlite3.connect('file:$DB?mode=ro', uri=True); print(c.execute(sys.argv[1]).fetchall())" "$1"; }

systemctl is-active --quiet fx-backfill-economics && { echo "REFUSED: backfill still running"; exit 2; }
echo "backfill: $(systemctl show fx-backfill-economics -p Result --value 2>/dev/null)"
q "SELECT extractor, version, status FROM fx_extractor_versions WHERE extractor='economics'"
q "SELECT COUNT(*), SUM(status='error') FROM fx_runs WHERE extractor='economics' AND version='1.0.0'"
q "SELECT COUNT(*) FROM events WHERE review_status='auto_approved'"

echo "--- gate"
cd $LIVE || exit 2
runuser -u mnt -- $PY accuracy_run.py gate economics 2>&1 | tail -30
rc=${PIPESTATUS[0]}
st=$(q "SELECT status FROM fx_extractor_versions WHERE extractor='economics' AND version='1.0.0'")
echo "gate rc=$rc status=$st"
[ "$st" = "[('active',)]" ] || { echo "NOT ACTIVATED: the page is untouched"; exit 3; }

echo "--- publish"
runuser -u mnt -- $PY -m portal.economics_publish || { echo "PUBLISH FAILED: the page is untouched"; exit 3; }
q "SELECT COUNT(*), COUNT(scenario), COUNT(DISTINCT event_id), SUM(context='announced' AND scenario IS NOT NULL) FROM economic_studies"

echo "--- the page"
cur=$(sha256sum $LIVE/portal/app.py | cut -c1-12)
[ "$cur" = "c5d3d5155f60" ] || { echo "REFUSED: live app.py is $cur, not the c5d3d5155f60 the route was patched onto"; exit 3; }
new=$(sha256sum $W/cand/portal/app.py | cut -c1-12)
[ "$new" = "0d83dc2ec9b1" ] || { echo "REFUSED: candidate app.py is $new"; exit 3; }
install -d -o mnt -g mnt $B && install -o mnt -g mnt -m 644 $LIVE/portal/app.py $B/app.py
echo "backup: $B/app.py"
install -o mnt -g mnt -m 644 $W/cand/portal/app.py $LIVE/portal/app.py
find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
systemctl restart mnt-portal
sleep 4
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)
  [ "$code" = "200" ] && break
  sleep 2
done
bad=0
for p in / /economic-studies "/economic-studies?show=studies" "/economic-studies?show=all" "/economic-studies?study=FS" \
         /resources /drills /financings /management-changes /search; do
  c=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8001$p")
  echo "  $c $p"
  [ "$c" = "200" ] || bad=1
done
curl -s http://127.0.0.1:8001/economic-studies > $W/page.html
grep -q 'es-table' $W/page.html || bad=1
echo "healthz: $code   rows on page one: $(grep -c '<tr class=' $W/page.html)"
if [ "$code" != "200" ] || [ "$bad" != "0" ]; then
  echo "ROLLING BACK THE PAGE"
  install -o mnt -g mnt -m 644 $B/app.py $LIVE/portal/app.py
  find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
  systemctl restart mnt-portal
  sleep 4
  echo "healthz after rollback: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)"
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
echo "PAGE_ECON_DONE $(date -u +%FT%TZ)"
