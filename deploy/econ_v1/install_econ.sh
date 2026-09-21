#!/bin/bash
# ECON_V1 1.0.0 install: put the staged reader, publisher, checker and accuracy set live, register the
# reader and start its backfill. The page (app.py) is NOT touched here: /economic-studies keeps showing
# the plain list of tagged releases until the gate has activated the reader and the publisher has
# built its table (page_econ.sh). Until a version is active the publisher step does nothing. (2026-09-21)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
W=/var/tmp/mnt-econ1
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
B=/var/tmp/mnt-econ1-backup-$(date -u +%Y%m%d-%H%M%S)
cd $W/cand || { echo "REFUSED: stage first"; exit 2; }

# the candidate tree must be the reviewed one, and the live shared files must still be the ones the
# patches were written against (nothing may have changed them since the stage)
cat > $W/SUMS_INSTALL <<'SUMS'
bc9bb8d4df3afe7dcf31d1670c4e9a5235b9a727e4a8b62965f5cb6503627f91  portal/extractors/econ_core.py
2a0d35884b250b700b22df4f3d7ab252244653606c2ce0ada64e4f0cd84953a0  portal/extractors/economics.py
cc3f46edf4fe15b30b02965098897642ec90cf8e7e140020aee012ef1fc38d30  portal/economics_publish.py
9317f352f09a0b9ebdaebc7141034b5f2e63898e095bfa3c78548736dda01779  portal/accuracy_economics.py
5eea34d53961c8800f22f4a862e1c54f10e65675d7b2437cf7f87b461d365497  portal/templates/economic_studies.html
SUMS
sha256sum -c --quiet $W/SUMS_INSTALL || { echo "REFUSED: the candidate tree is not the reviewed one"; exit 2; }
cat > $W/SUMS_LIVE <<'SUMS'
8af2a842084196eb082581e97e5cec5bd4323ec2b0405a09f27a5231cbaab33d  /opt/mnt/app/portal/accuracy.py
12bbf536e928c89ee43890fb05fddd8fa8f3a8b317d72d2e95cd5db0614a72f2  /opt/mnt/app/portal/extractors/__init__.py
06b32df53ee058f57b647f6cbb20460dd36aa7804497e43a9e7cf57ca90c8c77  /opt/mnt/app/sync_structured.py
SUMS
sha256sum -c --quiet $W/SUMS_LIVE || { echo "REFUSED: a live shared file changed since the stage"; exit 2; }
for f in portal/extractors/economics.py portal/economics_publish.py; do
  [ -e "$LIVE/$f" ] && { echo "REFUSED: $f already exists live"; exit 2; }
done
runuser -u mnt -- $PY -m portal.extractors.economics >/dev/null 2>&1 || { echo "REFUSED: reader self-test"; exit 2; }
runuser -u mnt -- $PY -m portal.economics_publish --selftest >/dev/null 2>&1 || { echo "REFUSED: publisher self-test"; exit 2; }

NEW="portal/extractors/econ_core.py portal/extractors/economics.py portal/economics_publish.py \
portal/accuracy_economics.py portal/templates/economic_studies.html accuracy/sets/economics.json"
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
c2=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/economic-studies)
c3=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/resources)
c4=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/drills)
echo "healthz: $code   /economic-studies: $c2   /resources: $c3   /drills: $c4"
reg=$(cd $LIVE && runuser -u mnt -- $PY -c "import sys; sys.path.insert(0, '.'); from portal.extractors import REGISTRY; \
from portal import accuracy as A; print(' '.join(s.name for s in REGISTRY), '|', ' '.join(sorted(A.SPECS)))" 2>&1)
echo "registry | specs: $reg"
if [ "$code" != "200" ] || [ "$c2" != "200" ] || [ "$c3" != "200" ] || [ "$c4" != "200" ] \
   || ! echo "$reg" | grep -q "economics .*|.*economics"; then
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
systemctl reset-failed fx-backfill-economics 2>/dev/null
systemd-run --unit fx-backfill-economics -p User=mnt -p WorkingDirectory=$LIVE \
  $PY $LIVE/facts_sync.py --backfill economics || exit 3
echo "INSTALL_ECON_DONE $(date -u +%FT%TZ)"
