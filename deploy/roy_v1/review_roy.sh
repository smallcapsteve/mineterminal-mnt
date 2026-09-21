#!/bin/bash
# ROY_V1 corpus review: build a scratch tree from the live files plus the Royalties & Streams reader and
# publisher at the given commit, run their self-tests, and start the read-only corpus review in the background
# ($W/repro.txt). Installs nothing and writes nothing outside $W. (2026-09-21)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
REF="${ROY_REF:?set ROY_REF to the mineterminal-mnt commit}"
W=/var/tmp/mnt-roy1
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
RAW="https://raw.githubusercontent.com/smallcapsteve/mineterminal-mnt/$REF"
systemctl stop fx-repro-roy 2>/dev/null; systemctl reset-failed fx-repro-roy 2>/dev/null
rm -rf $W/rev && install -d -o mnt -g mnt $W/rev $W/tools
tar -C $LIVE -cf - --exclude='portal.db*' --exclude='__pycache__' --exclude='*.bak*' --exclude='*.sqlite*' portal \
  | tar -C $W/rev -xf -
cd $W/rev || exit 2
for f in portal/extractors/royalties.py portal/royalties_publish.py; do
  curl -fsSL "$RAW/$f" -o "$f" || { echo "FAIL fetching $f"; exit 3; }
done
curl -fsSL "$RAW/deploy/roy_v1/repro_roy.py" -o $W/tools/repro_roy.py || { echo "FAIL fetching repro"; exit 3; }
curl -fsSL "$RAW/deploy/roy_v1/SUMS_REVIEW" -o $W/SUMS_REVIEW || { echo "FAIL fetching SUMS"; exit 3; }
sha256sum -c $W/SUMS_REVIEW || { echo "REFUSED: a file did not arrive as written"; exit 3; }
chown -R mnt:mnt $W
runuser -u mnt -- $PY -m portal.extractors.royalties | tail -1 || exit 3
runuser -u mnt -- $PY -m portal.royalties_publish --selftest | tail -1 || exit 3
systemd-run --unit fx-repro-roy -p User=mnt -p WorkingDirectory=$W/rev -p Nice=10 \
  /bin/bash -c "$PY $W/tools/repro_roy.py > $W/repro.txt 2>&1" >/dev/null && echo "review started"
echo "REVIEW_ROY_STARTED $(date -u +%FT%TZ)"
