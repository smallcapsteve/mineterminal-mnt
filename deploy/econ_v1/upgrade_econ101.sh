#!/bin/bash
# ECON 1.0.1: replace the reader's two files with the reviewed 1.0.1 and start its backfill as a
# candidate. 1.0.0 stays active -- and the page keeps showing its table -- until the gate passes 1.0.1
# (gate_econ.sh). (2026-09-21)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
W=/var/tmp/mnt-econ1
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
B=/var/tmp/mnt-econ101-backup-$(date -u +%Y%m%d-%H%M%S)
cd $W/cand || exit 2
printf '%s  %s\n%s  %s\n' \
  16a97c86b7b9facb616a276c6507077b190af314ae6132e8db07b7ef286bc145 portal/extractors/econ_core.py \
  33f8b5d9ee97d1e620bbce749a52ea682556d86876af63ac676917c75769ceb2 portal/extractors/economics.py \
  | sha256sum -c --quiet - || { echo "REFUSED: the candidate is not the reviewed 1.0.1"; exit 2; }
printf '%s  %s\n%s  %s\n' \
  bc9bb8d4df3afe7dcf31d1670c4e9a5235b9a727e4a8b62965f5cb6503627f91 $LIVE/portal/extractors/econ_core.py \
  2a0d35884b250b700b22df4f3d7ab252244653606c2ce0ada64e4f0cd84953a0 $LIVE/portal/extractors/economics.py \
  | sha256sum -c --quiet - || { echo "REFUSED: live is not 1.0.0"; exit 2; }
systemctl is-active --quiet fx-backfill-economics && { echo "REFUSED: a backfill is running"; exit 2; }
FILES="portal/extractors/econ_core.py portal/extractors/economics.py"
install -d -o mnt -g mnt $B
for f in $FILES; do install -D -o mnt -g mnt -m 644 "$LIVE/$f" "$B/$f"; done
echo "backup: $B"
for f in $FILES; do install -o mnt -g mnt -m 644 "$W/cand/$f" "$LIVE/$f"; done
find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
for f in $FILES; do echo "  $(sha256sum $LIVE/$f | cut -c1-12)  $f"; done
systemctl restart mnt-portal
sleep 4
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)
  [ "$code" = "200" ] && break
  sleep 2
done
c2=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/economic-studies)
v=$(cd $LIVE && runuser -u mnt -- $PY -c "import sys; sys.path.insert(0, '.'); from portal.extractors import economics as X; print(X.VERSION)" 2>&1)
echo "healthz: $code   /economic-studies: $c2   reader: $v"
if [ "$code" != "200" ] || [ "$c2" != "200" ] || [ "$v" != "1.0.1" ]; then
  echo "ROLLING BACK"
  for f in $FILES; do install -o mnt -g mnt -m 644 "$B/$f" "$LIVE/$f"; done
  find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
  systemctl restart mnt-portal
  exit 3
fi
systemctl reset-failed fx-backfill-economics 2>/dev/null
systemd-run --unit fx-backfill-economics -p User=mnt -p WorkingDirectory=$LIVE \
  $PY $LIVE/facts_sync.py --backfill economics || exit 3
echo "UPGRADE_ECON101_DONE $(date -u +%FT%TZ)"
