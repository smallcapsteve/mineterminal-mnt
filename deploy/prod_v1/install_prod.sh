#!/bin/bash
# PROD_V1 1.0.0 install: put the staged reader, publisher, checker, template and accuracy set live, register
# the reader and start its backfill. The page (app.py) is NOT touched here: /production-results keeps showing
# the plain list of tagged releases until the gate has activated the reader and the publisher has built its
# table (page_prod.sh). Until a version is active the publisher step does nothing. (2026-09-21)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
W=/var/tmp/mnt-prod1
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
B=/var/tmp/mnt-prod1-backup-$(date -u +%Y%m%d-%H%M%S)
cd $W/cand || { echo "REFUSED: stage first"; exit 2; }

# the candidate tree must be the reviewed one (base + prod2 + prod3), and the live shared files must still be
# the ones the patches were written against (nothing may have changed them since the stage)
cat > $W/SUMS_INSTALL <<'SUMS'
0b62db8620c401a17450d85d08d1411785230d5f0f76ddeb2e17050629dbfc37  portal/extractors/production.py
5066b2f5775b521b2f043aa94cf7e0ba4c03926a98dab5bf2ba1daec0822fd42  portal/production_publish.py
37b9ce55d40853fd57f7f0e32122dffac0dfa5b38e8226ec353979a0208483c9  portal/accuracy_production.py
9791bfd074096a738d7692236d4bd38233364750b54dd68541e1e7768852d968  portal/templates/production_results.html
SUMS
sha256sum -c --quiet $W/SUMS_INSTALL || { echo "REFUSED: the candidate tree is not the reviewed one"; exit 2; }
for f in portal/accuracy.py:74c5a7d3fd8b portal/extractors/__init__.py:ce8548fb26e8 sync_structured.py:0787c8d7e4bb; do
  h=$(sha256sum "$LIVE/${f%%:*}" | cut -c1-12)
  [ "$h" = "${f##*:}" ] || { echo "REFUSED: live ${f%%:*} is $h, not ${f##*:} (changed since the stage)"; exit 2; }
done
for f in portal/extractors/production.py portal/production_publish.py; do
  [ -e "$LIVE/$f" ] && { echo "REFUSED: $f already exists live"; exit 2; }
done
runuser -u mnt -- $PY -m portal.extractors.production >/dev/null 2>&1 || { echo "REFUSED: reader self-test"; exit 2; }
runuser -u mnt -- $PY -m portal.production_publish --selftest >/dev/null 2>&1 || { echo "REFUSED: publisher self-test"; exit 2; }

NEW="portal/extractors/production.py portal/production_publish.py portal/accuracy_production.py \
portal/templates/production_results.html accuracy/sets/production.json"
SHARED="portal/extractors/__init__.py portal/accuracy.py sync_structured.py"

install -d -o mnt -g mnt $B
for f in $SHARED; do install -D -o mnt -g mnt -m 644 "$LIVE/$f" "$B/$f"; done
echo "backup: $B"
for f in $NEW $SHARED; do
  install -D -o mnt -g mnt -m 644 "$W/cand/$f" "$LIVE/$f" || { echo "FAIL installing $f"; exit 3; }
done
find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
echo "installed:"
for f in $NEW $SHARED; do echo "  $(sha256sum $LIVE/$f | cut -c1-12)  $f"; done

systemctl restart mnt-portal
sleep 4
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)
  [ "$code" = "200" ] && break
  sleep 2
done
c2=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/production-results)
c3=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/resources)
c4=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/drills)
echo "healthz: $code   /production-results: $c2   /resources: $c3   /drills: $c4"
reg=$(cd $LIVE && runuser -u mnt -- $PY -c "import sys; sys.path.insert(0, '.'); from portal.extractors import REGISTRY; \
from portal import accuracy as A; print(' '.join(s.name for s in REGISTRY), '|', ' '.join(sorted(A.SPECS)))" 2>&1)
echo "registry | specs: $reg"
if [ "$code" != "200" ] || [ "$c2" != "200" ] || [ "$c3" != "200" ] || [ "$c4" != "200" ] \
   || ! echo "$reg" | grep -q "production .*|.*production"; then
  echo "ROLLING BACK"
  for f in $SHARED; do install -D -o mnt -g mnt -m 644 "$B/$f" "$LIVE/$f"; done
  for f in $NEW; do rm -f "$LIVE/$f"; done
  find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
  systemctl restart mnt-portal
  sleep 4
  echo "healthz after rollback: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)"
  exit 3
fi

echo "--- registering and backfilling the reader over every approved release (the page is untouched)"
systemctl reset-failed fx-backfill-production 2>/dev/null
systemd-run --unit fx-backfill-production -p User=mnt -p WorkingDirectory=$LIVE \
  $PY $LIVE/facts_sync.py --backfill production || exit 3
echo "INSTALL_PROD_DONE $(date -u +%FT%TZ)"
