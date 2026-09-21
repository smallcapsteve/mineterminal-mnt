#!/bin/bash
# ROY_V1 install: put the staged reader, publisher, checker, template and accuracy set live, register the
# reader and start its backfill. The page (app.py, pages.py) is NOT touched here: /royalties-streams does not
# exist until the gate has activated the reader and the publisher has built its table (page_roy.sh). Until a
# version is active the publisher step does nothing. (2026-09-21)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
W=/var/tmp/mnt-roy1
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
B=/var/tmp/mnt-roy1-backup-$(date -u +%Y%m%d-%H%M%S)
cd $W/cand || { echo "REFUSED: stage first"; exit 2; }
[ "${ROY_CONFIRM:-}" = "install-royalties" ] || { echo "REFUSED: set ROY_CONFIRM=install-royalties"; exit 2; }
# the candidate tree must be the reviewed one (repo reader + roy2-roy4), and the live shared files must still be
# the ones the patches were written against (nothing may have changed them since the stage)
cat > $W/SUMS_INSTALL <<'SUMS'
8fdcca5d6c7d7e37dc005aae9e227cc8a11a84c7e6ad37164912eb70f68693e5  portal/extractors/royalties.py
e05662b6332b382a34b8a32edf9ed35bc938aa1edda78f37417f125c6699009b  portal/royalties_publish.py
2ee93344e61a701d45493e5aeb95bb093103bf75edea3c95e36e6666b5a8b012  portal/accuracy_royalties.py
e6f743ce6850bc918683f0003b9d23e715344ccbca9b5f0ce460e20ef12c7089  portal/templates/royalties_streams.html
SUMS
sha256sum -c --quiet $W/SUMS_INSTALL || { echo "REFUSED: the candidate tree is not the reviewed one"; exit 2; }
for f in portal/accuracy.py:193f37cabecb portal/extractors/__init__.py:c8af2eb32080 sync_structured.py:982c3f99f96a; do
  h=$(sha256sum "$LIVE/${f%%:*}" | cut -c1-12)
  [ "$h" = "${f##*:}" ] || { echo "REFUSED: live ${f%%:*} is $h, not ${f##*:} (changed since the stage)"; exit 2; }
done
for f in portal/extractors/royalties.py portal/royalties_publish.py; do
  [ -e "$LIVE/$f" ] && { echo "REFUSED: $f already exists live"; exit 2; }
done
runuser -u mnt -- $PY -m portal.extractors.royalties >/dev/null 2>&1 || { echo "REFUSED: reader self-test"; exit 2; }
runuser -u mnt -- $PY -m portal.royalties_publish --selftest >/dev/null 2>&1 || { echo "REFUSED: publisher self-test"; exit 2; }

NEW="portal/extractors/royalties.py portal/royalties_publish.py portal/accuracy_royalties.py \
portal/templates/royalties_streams.html accuracy/sets/royalties.json"
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
# the portal takes 12-30 s to answer after a restart while backfills are running
for i in $(seq 1 45); do
  code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz)
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
   || ! echo "$reg" | grep -q "royalties .*|.*royalties"; then
  echo "ROLLING BACK"
  for f in $SHARED; do install -D -o mnt -g mnt -m 644 "$B/$f" "$LIVE/$f"; done
  for f in $NEW; do rm -f "$LIVE/$f"; done
  find $LIVE/portal -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
  systemctl restart mnt-portal
  for i in $(seq 1 45); do
    c=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/healthz); [ "$c" = "200" ] && break; sleep 2
  done
  echo "healthz after rollback: $c"
  exit 3
fi

echo "--- registering and backfilling the reader over every approved release (no page exists yet)"
systemctl reset-failed fx-backfill-royalties 2>/dev/null
systemd-run --unit fx-backfill-royalties -p User=mnt -p WorkingDirectory=$LIVE \
  $PY $LIVE/facts_sync.py --backfill royalties || exit 3
echo "INSTALL_ROY_DONE $(date -u +%FT%TZ)"
