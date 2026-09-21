#!/bin/bash
# ECON_V1 1.0.0 stage: build a candidate tree from the live files plus the Economic Studies reader,
# publisher, checker, page and accuracy set; run every self-test; start the corpus review
# (repro_econ.py) in the background. Read-only on portal.db. Installs nothing. (2026-09-21)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
REF="${ECON_REF:?set ECON_REF to the mineterminal-mnt commit to stage}"
W=/var/tmp/mnt-econ1
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
RAW="https://raw.githubusercontent.com/smallcapsteve/mineterminal-mnt/$REF"

systemctl stop fx-repro-econ 2>/dev/null; systemctl reset-failed fx-repro-econ 2>/dev/null
rm -rf $W && install -d -o mnt -g mnt $W/cand $W/tools
tar -C $LIVE -cf - --exclude='portal.db*' --exclude='__pycache__' --exclude='*.bak*' --exclude='*.sqlite*' \
    portal accuracy | tar -C $W/cand -xf -
cp -p $LIVE/sync_structured.py $LIVE/accuracy_run.py $LIVE/facts_sync.py $W/cand/
cd $W/cand || exit 2

echo "--- fetching from the repo at $REF"
for f in portal/extractors/econ_core.py portal/extractors/economics.py portal/economics_publish.py \
         portal/accuracy_economics.py portal/templates/economic_studies.html; do
  curl -fsSL "$RAW/$f" -o "$f" || { echo "FAIL fetching $f"; exit 3; }
done
for f in patch_shared_econ.py patch_app_econ.py economic_studies_route.py build_econ_set.py \
         repro_econ.py econ_labels_confirmed.json; do
  curl -fsSL "$RAW/deploy/econ_v1/$f" -o "$W/tools/$f" || { echo "FAIL fetching $f"; exit 3; }
done
cat > $W/SUMS <<'SUMS'
d368f79748f115e2f3edc03a54ea1c6d9637d467b17286b33a79e3ac45b4bf2a  portal/extractors/econ_core.py
b78fecec6305611694617b6455c25836459d5dac114bb67c82e5217e61beddfd  portal/extractors/economics.py
cc3f46edf4fe15b30b02965098897642ec90cf8e7e140020aee012ef1fc38d30  portal/economics_publish.py
9317f352f09a0b9ebdaebc7141034b5f2e63898e095bfa3c78548736dda01779  portal/accuracy_economics.py
5eea34d53961c8800f22f4a862e1c54f10e65675d7b2437cf7f87b461d365497  portal/templates/economic_studies.html
3b4c4054a90f3ea8ac6204cf934cbad2c3bc7df0f3411c67f91289d32824848b  ../tools/patch_shared_econ.py
1245cce6540ccd8695d910647f08b2ccbf50167014aac0fc49077ff8dacc55f7  ../tools/patch_app_econ.py
beec40a1f41cfe138c0c13b604570b2688847c0d75fa1f7ff4112a0482997061  ../tools/economic_studies_route.py
c2406ca8df8e543f01f05ed6c0a820f84a1d5ce0dbcaffc5fae2f4fd2aa1169b  ../tools/build_econ_set.py
5687b95a8191c1b76cd05d746669341ad6081af4e7d6c4f0860b477e50f7d582  ../tools/repro_econ.py
e994d94f0905eeeccb62698106fc6655e7dbd30b57fb6985b49aeecc4153090a  ../tools/econ_labels_confirmed.json
SUMS
sha256sum -c $W/SUMS || { echo "REFUSED: a file did not arrive as written"; exit 3; }

echo "--- the three shared files (refused unless byte for byte the live copies they were written against)"
$PY $W/tools/patch_shared_econ.py $W/cand || exit 3
echo "--- the page route (app.py never travels; refused unless it is the live c5d3d5155f60)"
$PY $W/tools/patch_app_econ.py portal/app.py $W/app.py.new $W/tools/economic_studies_route.py || exit 3
cp $W/app.py.new portal/app.py

chown -R mnt:mnt $W
echo "--- the accuracy set, from the live release text (read-only)"
runuser -u mnt -- $PY $W/tools/build_econ_set.py $W/tools/econ_labels_confirmed.json accuracy/sets/economics.json || exit 3
chmod 755 $W

echo "--- self-tests"
for m in portal.facts portal.normalize portal.accuracy portal.extractors.economics portal.extractors.financings \
         portal.extractors.drill_results portal.extractors.management portal.extractors.resources; do
  runuser -u mnt -- $PY -m $m > $W/st_$m.txt 2>&1 \
    && echo "  $m rc=0 $(tail -1 $W/st_$m.txt)" || { echo "  $m FAILED"; tail -20 $W/st_$m.txt; exit 3; }
done
for m in portal.economics_publish portal.resources_publish portal.management_publish; do
  runuser -u mnt -- $PY -m $m --selftest > $W/st_$m.txt 2>&1 \
    && echo "  $m rc=0 $(tail -1 $W/st_$m.txt)" || { echo "  $m FAILED"; tail -30 $W/st_$m.txt; exit 3; }
done
runuser -u mnt -- $PY -c "import sys; sys.path.insert(0, '.'); from portal.extractors import REGISTRY; \
print('registry', [(s.name, s.version, s.code_sha[:12]) for s in REGISTRY]); \
from portal import accuracy as A; print('specs', sorted(A.SPECS)); import ast; \
ast.parse(open('portal/app.py').read()); print('app.py parses')" || exit 3
grep -n "economics_publish" sync_structured.py | head -3

echo "--- the corpus review runs in the background: $W/repro.txt"
systemd-run --unit fx-repro-econ -p User=mnt -p WorkingDirectory=$W/cand \
  /bin/bash -c "$PY $W/tools/repro_econ.py > $W/repro.txt 2>&1" >/dev/null && echo "  started"
echo "STAGE_ECON_DONE $(date -u +%FT%TZ)"
