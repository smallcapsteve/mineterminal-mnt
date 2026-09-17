#!/bin/bash
# MGMT_V1 1.0.0 install: put the staged candidate live, restart the portal, register and backfill the
# reader. The page keeps showing the legacy table until the accuracy gate activates the version.
# (2026-09-17)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
W=/var/tmp/mnt-mgmt1
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
B=/var/tmp/mnt-mgmt1-backup-$(date -u +%Y%m%d-%H%M%S)
[ -f $W/cand/portal/extractors/management.py ] || { echo "REFUSED: stage first"; exit 2; }
[ -f $W/st_portal.management_publish.txt ] || { echo "REFUSED: self-tests have not run"; exit 2; }
grep -q "failures: 0" $W/st_portal.management_publish.txt || { echo "REFUSED: publisher self-test did not pass"; exit 2; }

FILES="portal/extractors/mgmt_roles.py portal/extractors/management.py portal/management_publish.py \
portal/accuracy_management.py portal/extractors/__init__.py portal/accuracy.py sync_structured.py \
accuracy/sets/management.json"

install -d -o mnt -g mnt $B
for f in $FILES; do
  if [ -f "$LIVE/$f" ]; then install -D -o mnt -g mnt -m 644 "$LIVE/$f" "$B/$f"; fi
done
echo "backup: $B"

for f in $FILES; do
  install -D -o mnt -g mnt -m 644 "$W/cand/$f" "$LIVE/$f" || { echo "FAIL installing $f"; exit 3; }
done
find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
echo "installed:"
for f in $FILES; do echo "  $(sha256sum $LIVE/$f)"; done

systemctl restart mnt-portal
sleep 4
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)
  [ "$code" = "200" ] && break
  sleep 2
done
echo "healthz: $code"
code2=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/management-changes)
echo "/management-changes: $code2"
if [ "$code" != "200" ] || [ "$code2" != "200" ]; then
  echo "ROLLING BACK"
  for f in $FILES; do [ -f "$B/$f" ] && install -D -o mnt -g mnt -m 644 "$B/$f" "$LIVE/$f"; done
  rm -f $LIVE/portal/accuracy_management.py $LIVE/portal/management_publish.py \
        $LIVE/portal/extractors/management.py $LIVE/portal/extractors/mgmt_roles.py
  find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
  systemctl restart mnt-portal
  sleep 4
  echo "healthz after rollback: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)"
  exit 3
fi

cd $LIVE || exit 2
echo "--- registering and backfilling the reader (the page is untouched until the gate activates it)"
nohup runuser -u mnt -- $PY facts_sync.py --backfill management > /var/tmp/mnt-mgmt1-backfill.log 2>&1 &
echo "backfill started, pid $!; watch /var/tmp/mnt-mgmt1-backfill.log"
echo "INSTALL_MGMT_DONE $(date -u +%FT%TZ)"
