#!/bin/bash
# PROD_V1 1.0.0 stage: build a candidate tree from the live files plus the Production Results reader,
# publisher, checker, page and accuracy set; run every self-test; start the corpus review (repro_prod.py)
# in the background. Read-only on portal.db. Installs nothing. (2026-09-21)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
REF="${PROD_REF:?set PROD_REF to the mineterminal-mnt commit to stage}"
W=/var/tmp/mnt-prod1
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
RAW="https://raw.githubusercontent.com/smallcapsteve/mineterminal-mnt/$REF"

systemctl stop fx-repro-prod 2>/dev/null; systemctl reset-failed fx-repro-prod 2>/dev/null
rm -rf $W && install -d -o mnt -g mnt $W/cand $W/tools
tar -C $LIVE -cf - --exclude='portal.db*' --exclude='__pycache__' --exclude='*.bak*' --exclude='*.sqlite*' \
    portal accuracy | tar -C $W/cand -xf -
cp -p $LIVE/sync_structured.py $LIVE/accuracy_run.py $LIVE/facts_sync.py $W/cand/
cd $W/cand || exit 2

echo "--- fetching from the repo at $REF"
for f in portal/extractors/production.py portal/production_publish.py portal/accuracy_production.py \
         portal/templates/production_results.html; do
  curl -fsSL "$RAW/$f" -o "$f" || { echo "FAIL fetching $f"; exit 3; }
done
for f in patch_shared_prod.py patch_app_prod.py production_results_route.py build_prod_set.py repro_prod.py \
         prod_labels_confirmed.json; do
  curl -fsSL "$RAW/deploy/prod_v1/$f" -o "$W/tools/$f" || { echo "FAIL fetching $f"; exit 3; }
done
curl -fsSL "$RAW/deploy/prod_v1/SUMS" -o $W/SUMS || { echo "FAIL fetching SUMS"; exit 3; }
sha256sum -c $W/SUMS || { echo "REFUSED: a file did not arrive as written"; exit 3; }

echo "--- the three shared files (refused unless the live copies they were written against)"
$PY $W/tools/patch_shared_prod.py $W/cand || exit 3
echo "--- the page route (app.py never travels; refused unless it is the live 0d83dc2ec9b1)"
$PY $W/tools/patch_app_prod.py portal/app.py $W/app.py.new $W/tools/production_results_route.py || exit 3
cp $W/app.py.new portal/app.py

chown -R mnt:mnt $W
echo "--- the accuracy set, from the live release text (read-only)"
runuser -u mnt -- env PYTHONPATH=$W/cand $PY $W/tools/build_prod_set.py $W/tools/prod_labels_confirmed.json accuracy/sets/production.json || exit 3
chmod 755 $W

echo "--- self-tests"
for m in portal.facts portal.normalize portal.accuracy portal.extractors.production portal.extractors.economics \
         portal.extractors.financings portal.extractors.drill_results portal.extractors.management portal.extractors.resources; do
  runuser -u mnt -- $PY -m $m > $W/st_$m.txt 2>&1 \
    && echo "  $m rc=0 $(tail -1 $W/st_$m.txt)" || { echo "  $m FAILED"; tail -20 $W/st_$m.txt; exit 3; }
done
for m in portal.production_publish portal.economics_publish portal.resources_publish portal.management_publish; do
  runuser -u mnt -- $PY -m $m --selftest > $W/st_$m.txt 2>&1 \
    && echo "  $m rc=0 $(tail -1 $W/st_$m.txt)" || { echo "  $m FAILED"; tail -30 $W/st_$m.txt; exit 3; }
done
runuser -u mnt -- $PY -c "import sys; sys.path.insert(0, '.'); from portal.extractors import REGISTRY; \
print('registry', [(s.name, s.version, s.code_sha[:12]) for s in REGISTRY]); \
from portal import accuracy as A; print('specs', sorted(A.SPECS)); import ast; \
ast.parse(open('portal/app.py').read()); print('app.py parses')" || exit 3
grep -n "production_publish" sync_structured.py | head -3

echo "--- the corpus review runs in the background: $W/repro.txt"
systemd-run --unit fx-repro-prod -p User=mnt -p WorkingDirectory=$W/cand \
  /bin/bash -c "$PY $W/tools/repro_prod.py > $W/repro.txt 2>&1" >/dev/null && echo "  started"
echo "STAGE_PROD_DONE $(date -u +%FT%TZ)"
