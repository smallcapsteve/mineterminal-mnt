#!/bin/bash
# RES_V1 1.0.16 install: put the staged reader, publisher and spec live and start the backfill.
# app.py and the template are NOT installed here: the new handler reads columns the legacy table
# does not have, so the page is patched only once the publisher has rebuilt the table. The legacy
# columns the old handler reads are kept in the new table for exactly that window. (2026-09-18)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
W=/var/tmp/mnt-res1
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
B=/var/tmp/mnt-res1-backup-$(date -u +%Y%m%d-%H%M%S)
[ -f $W/cand/portal/extractors/resources.py ] || { echo "REFUSED: stage first"; exit 2; }
[ -f $W/st_portal.resources_publish.txt ] || { echo "REFUSED: self-tests have not run"; exit 2; }
grep -q "failures: 0" $W/st_portal.resources_publish.txt || { echo "REFUSED: publisher self-test did not pass"; exit 2; }

FILES="portal/extractors/resources.py portal/resources_publish.py portal/accuracy_resources.py \
portal/extractors/__init__.py portal/accuracy.py sync_structured.py accuracy/sets/resources.json"

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
code2=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/resources)
code3=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8001/api/resources/recent.json")
echo "/resources: $code2   /api/resources/recent.json: $code3"
if [ "$code" != "200" ] || [ "$code2" != "200" ] || [ "$code3" != "200" ]; then
  echo "ROLLING BACK"
  for f in $FILES; do [ -f "$B/$f" ] && install -D -o mnt -g mnt -m 644 "$B/$f" "$LIVE/$f"; done
  rm -f $LIVE/portal/accuracy_resources.py $LIVE/portal/resources_publish.py \
        $LIVE/portal/extractors/resources.py $LIVE/accuracy/sets/resources.json
  find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
  systemctl restart mnt-portal
  sleep 4
  echo "healthz after rollback: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)"
  exit 3
fi

cd $LIVE || exit 2
echo "--- registering and backfilling the reader (the page is untouched until the gate activates it)"
systemd-run --unit=fx-backfill-resources --uid=mnt --gid=mnt \
  -p WorkingDirectory=/opt/mnt/app \
  $PY /opt/mnt/app/facts_sync.py --backfill resources || exit 3
echo "backfill started as fx-backfill-resources; follow with journalctl -u fx-backfill-resources"
echo "INSTALL_RES_DONE $(date -u +%FT%TZ)"
