#!/bin/bash
# ROY_V1 stage: build a candidate tree from the live files plus the Royalties & Streams reader, publisher,
# checker, page and accuracy set; run every self-test. Read-only on portal.db. Installs nothing. (2026-09-21)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
REF="${ROY_REF:?set ROY_REF to the mineterminal-mnt commit to stage}"
W=/var/tmp/mnt-roy1
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
RAW="https://raw.githubusercontent.com/smallcapsteve/mineterminal-mnt/$REF"

rm -rf $W/cand && install -d -o mnt -g mnt $W/cand $W/tools
tar -C $LIVE -cf - --exclude='portal.db*' --exclude='__pycache__' --exclude='*.bak*' --exclude='*.sqlite*' \
    portal accuracy | tar -C $W/cand -xf -
cp -p $LIVE/sync_structured.py $LIVE/accuracy_run.py $LIVE/facts_sync.py $W/cand/
cd $W/cand || exit 2

echo "--- fetching from the repo at $REF"
for f in portal/extractors/royalties.py portal/royalties_publish.py portal/accuracy_royalties.py \
         portal/templates/royalties_streams.html; do
  curl -fsSL "$RAW/$f" -o "$f" || { echo "FAIL fetching $f"; exit 3; }
done
for f in patch_shared_roy.py patch_app_roy.py patch_pages_roy.py royalties_route.py build_roy_set.py \
         roy_labels_confirmed.json roy2.patch roy3.patch roy4.patch; do
  curl -fsSL "$RAW/deploy/roy_v1/$f" -o "$W/tools/$f" || { echo "FAIL fetching $f"; exit 3; }
done
curl -fsSL "$RAW/deploy/roy_v1/SUMS" -o $W/SUMS || { echo "FAIL fetching SUMS"; exit 3; }
sha256sum -c $W/SUMS || { echo "REFUSED: a file did not arrive as written"; exit 3; }

echo "--- the reader: the repo copy plus the corpus-review patches (roy2-roy4)"
for p in roy2 roy3 roy4; do patch -p1 -s < $W/tools/$p.patch || { echo "FAIL applying $p"; exit 3; }; done
h=$(sha256sum portal/extractors/royalties.py | cut -c1-16)
[ "$h" = "8fdcca5d6c7d7e37" ] || { echo "REFUSED: patched reader is $h"; exit 3; }
echo "--- the three shared files (refused unless the live copies they were written against)"
$PY $W/tools/patch_shared_roy.py $W/cand || exit 3
echo "--- the page: app.py route and the nav tab (refused unless the live copies they were written against)"
$PY $W/tools/patch_app_roy.py portal/app.py $W/app.py.new $W/tools/royalties_route.py || exit 3
cp $W/app.py.new portal/app.py
$PY $W/tools/patch_pages_roy.py portal/pages.py $W/pages.py.new || exit 3
cp $W/pages.py.new portal/pages.py

chown -R mnt:mnt $W
echo "--- the accuracy set, from the live release text (read-only)"
runuser -u mnt -- env PYTHONPATH=$W/cand $PY $W/tools/build_roy_set.py $W/tools/roy_labels_confirmed.json accuracy/sets/royalties.json || exit 3
chmod 755 $W

echo "--- self-tests"
for m in portal.facts portal.accuracy portal.extractors.royalties portal.extractors.production portal.extractors.economics \
         portal.extractors.financings portal.extractors.drill_results portal.extractors.management portal.extractors.resources; do
  runuser -u mnt -- $PY -m $m > $W/st_$m.txt 2>&1 \
    && echo "  $m rc=0 $(tail -1 $W/st_$m.txt)" || { echo "  $m FAILED"; tail -20 $W/st_$m.txt; exit 3; }
done
for m in portal.royalties_publish portal.production_publish portal.economics_publish; do
  runuser -u mnt -- $PY -m $m --selftest > $W/st_$m.txt 2>&1 \
    && echo "  $m rc=0 $(tail -1 $W/st_$m.txt)" || { echo "  $m FAILED"; tail -30 $W/st_$m.txt; exit 3; }
done
runuser -u mnt -- $PY -c "import sys; sys.path.insert(0, '.'); from portal.extractors import REGISTRY; \
print('registry', [(s.name, s.version, s.code_sha[:12]) for s in REGISTRY]); \
from portal import accuracy as A; print('specs', sorted(A.SPECS)); import ast; \
ast.parse(open('portal/app.py').read()); import portal.pages as PG; print('app.py parses; nav', \
[p for g in PG.MNT_NAV for p in g['pages'] if 'Royalt' in p['label']])" || exit 3
grep -n "royalties_publish" sync_structured.py | head -3
echo "--- sums of the staged candidate"
sha256sum portal/extractors/royalties.py portal/royalties_publish.py portal/accuracy_royalties.py \
  portal/templates/royalties_streams.html accuracy/sets/royalties.json portal/accuracy.py portal/extractors/__init__.py \
  sync_structured.py portal/app.py portal/pages.py | cut -c1-12,65-
echo "STAGE_ROY_DONE $(date -u +%FT%TZ)"
