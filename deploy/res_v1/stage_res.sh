#!/bin/bash
# RES_V1 1.0.16 stage: build a candidate tree from the live files plus the new reader, publisher,
# spec, page and accuracy set; run every self-test. Read-only on portal.db. Installs nothing.
# (2026-09-18)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
REF="${RES_REF:?set RES_REF to the mineterminal-mnt commit to install}"
W=/var/tmp/mnt-res1
M=/var/tmp/mnt-res
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
RAW="https://raw.githubusercontent.com/smallcapsteve/mineterminal-mnt/$REF"
READER_SHA=e4bcf28dd56ced379c27965b7e50070f864c7ce012254a4c62321c47e20cfcae
SET_SHA=643d533ab9bd6f8e59d1f43bbd22d1a94cea5dec48a19c6ca4525d4abec38dd3

rm -rf $W && install -d -o mnt -g mnt $W/cand
tar -C $LIVE -cf - --exclude='portal.db*' --exclude='__pycache__' --exclude='*.bak*' --exclude='*.sqlite*' \
    portal accuracy | tar -C $W/cand -xf -
cp -p $LIVE/sync_structured.py $LIVE/accuracy_run.py $LIVE/facts_sync.py $W/cand/
cd $W/cand || exit 2

echo "--- the reader and the set, from the measured copies in $M (neither travels again)"
echo "$READER_SHA  $M/resources.py"        | sha256sum -c - || { echo "REFUSED: the reader is not the measured 1.0.16"; exit 3; }
echo "$SET_SHA  $M/resources_set.json"     | sha256sum -c - || { echo "REFUSED: the accuracy set is not the built one"; exit 3; }
install -D -o mnt -g mnt -m 644 $M/resources.py        portal/extractors/resources.py
install -D -o mnt -g mnt -m 644 $M/resources_set.json  accuracy/sets/resources.json

echo "--- fetching the new files from the repo at $REF"
for f in portal/resources_publish.py portal/accuracy_resources.py portal/templates/resources.html; do
  curl -fsSL "$RAW/$f" -o "$f" || { echo "FAIL fetching $f"; exit 3; }
done
# byte-for-byte the workspace copies these were written and self-tested as
cat > $W/SUMS_NEW <<'SUMS'
cc5de8b951925219b6749c8ae5ed5b7058212ea32c967996cd4e6e0c2c28d3bd  portal/resources_publish.py
ab0fc604a65bb7a6d9f261c870a15328b33a9b6bae3bb1a2e1adb859828d508e  portal/accuracy_resources.py
b7e8861fc50768ac92fe023bffa1ba900bf959c89f96e323c2503e4b29ff55ef  portal/templates/resources.html
SUMS
sha256sum -c $W/SUMS_NEW || { echo "REFUSED: a file did not arrive as written"; exit 3; }
for f in deploy/res_v1/patch_accuracy_res.py deploy/res_v1/patch_app_res.py \
         deploy/res_v1/resources_page_block.py; do
  curl -fsSL "$RAW/$f" -o "$W/$(basename $f)" || { echo "FAIL fetching $f"; exit 3; }
done

echo "--- registering the spec, the extractor and the timer step (three exact anchors)"
$PY $W/patch_accuracy_res.py portal/accuracy.py portal/extractors/__init__.py sync_structured.py || exit 3

echo "--- the page: app.py is 91 KB and never travels, so the handler is swapped between its markers"
$PY $W/patch_app_res.py portal/app.py $W/resources_page_block.py || exit 3

chown -R mnt:mnt $W/cand
chmod 755 $W

echo "--- self-tests"
for m in portal.facts portal.normalize portal.accuracy portal.extractors.financings \
         portal.extractors.drill_results portal.extractors.management portal.extractors.resources; do
  runuser -u mnt -- $PY -m $m > $W/st_$m.txt 2>&1 \
    && echo "  $m rc=0 $(tail -1 $W/st_$m.txt)" || { echo "  $m FAILED"; tail -20 $W/st_$m.txt; exit 3; }
done
for m in portal.resources_publish portal.management_publish portal.financing_publish portal.drill_publish; do
  runuser -u mnt -- $PY -m $m --selftest > $W/st_$m.txt 2>&1 \
    && echo "  $m rc=0 $(tail -1 $W/st_$m.txt)" || { echo "  $m FAILED"; tail -30 $W/st_$m.txt; exit 3; }
done
runuser -u mnt -- $PY -c "import sys; sys.path.insert(0, '.'); from portal.extractors import REGISTRY; \
print('registry', [(s.name, s.version, s.code_sha[:12]) for s in REGISTRY])" || exit 3
runuser -u mnt -- $PY -c "import sys; sys.path.insert(0, '.'); from portal import accuracy as A; \
print('specs', sorted(A.SPECS)); import json; \
d=json.load(open('accuracy/sets/resources.json')); \
print('set', d['name'], d['status'], len(d['items']), 'items,', sum(len(i['expect']['rows']) for i in d['items']), 'rows')" || exit 3
runuser -u mnt -- $PY -c "import sys; sys.path.insert(0, '.'); import ast; \
ast.parse(open('portal/app.py').read()); print('app.py parses')" || exit 3
echo "STAGE_RES_DONE $(date -u +%FT%TZ)"
