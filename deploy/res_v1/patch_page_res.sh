#!/bin/bash
# RES_V1 page: swap the /resources handler in portal/app.py and install the new template. Run only
# AFTER the switch, because the new handler reads deposit, category, tonnes, grades_json and
# contained_json -- columns the legacy table does not have. (2026-09-18)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
REF="${RES_REF:?set RES_REF}"
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
RAW="https://raw.githubusercontent.com/smallcapsteve/mineterminal-mnt/$REF"
B=/var/tmp/mnt-res-page-backup-$(date -u +%Y%m%d-%H%M%S)

runuser -u mnt -- $PY -c "
import sqlite3, sys
c = sqlite3.connect('file:$LIVE/portal/portal.db?mode=ro', uri=True)
cols = {r[1] for r in c.execute('PRAGMA table_info(resource_estimates)')}
missing = {'deposit','category','tonnes','grades_json','contained_json'} - cols
if missing:
    sys.exit('REFUSED: the table has not been rebuilt yet, missing %s' % sorted(missing))
n = c.execute('select count(*) from resource_estimates').fetchone()[0]
if not n:
    sys.exit('REFUSED: resource_estimates is empty; publish before patching the page')
print('table is the new shape,', n, 'rows')
" || exit 2

install -d -o mnt -g mnt $B
cp -p $LIVE/portal/app.py $B/app.py
cp -p $LIVE/portal/templates/resources.html $B/resources.html
echo "backup: $B"

curl -fsSL "$RAW/deploy/res_v1/resources_page_block.py" -o /var/tmp/res_block.py || exit 3
curl -fsSL "$RAW/deploy/res_v1/patch_app_res.py" -o /var/tmp/patch_app_res.py || exit 3
curl -fsSL "$RAW/portal/templates/resources.html" -o /var/tmp/res_template.html || exit 3
echo "  $(sha256sum /var/tmp/res_template.html)"

$PY /var/tmp/patch_app_res.py $LIVE/portal/app.py /var/tmp/res_block.py || exit 3
install -o mnt -g mnt -m 644 /var/tmp/res_template.html $LIVE/portal/templates/resources.html
find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
echo "app.py     $(sha256sum $LIVE/portal/app.py)"
echo "template   $(sha256sum $LIVE/portal/templates/resources.html)"
runuser -u mnt -- $PY -c "import ast; ast.parse(open('$LIVE/portal/app.py').read()); print('app.py parses')" || exit 3

systemctl restart mnt-portal
for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)
  [ "$code" = "200" ] && break
  sleep 3
done
echo "healthz $code"
for u in "/resources" "/resources?has=data" "/resources?days=365" "/resources?page=2" \
         "/api/resources/recent.json" "/api/companies/stage-signals.json"; do
  echo "  $u -> $(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8001$u")"
done
if [ "$code" != "200" ]; then
  echo "ROLLING BACK"
  install -o mnt -g mnt -m 644 $B/app.py $LIVE/portal/app.py
  install -o mnt -g mnt -m 644 $B/resources.html $LIVE/portal/templates/resources.html
  find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
  systemctl restart mnt-portal
  sleep 5
  echo "healthz after rollback $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)"
  exit 3
fi
curl -s http://127.0.0.1:8001/resources | grep -c 'res-deposit' | sed 's/^/deposit cells rendered: /'
curl -s http://127.0.0.1:8001/resources | grep -o '<td class="res-num">[^<]*' | head -8
curl -s "http://127.0.0.1:8001/api/resources/recent.json" | head -c 400; echo
echo "PATCH_PAGE_RES_DONE $(date -u +%FT%TZ)"
