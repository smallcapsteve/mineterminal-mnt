#!/bin/bash
# MGMT_V1 1.0.0 stage: build a candidate tree from the live files plus the new reader, publisher, spec
# and accuracy set, run every self-test, and reproduce the workspace measurement against live text.
# Read-only on portal.db. Installs nothing. (2026-09-17)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
REF="${MGMT_REF:?set MGMT_REF to the mineterminal-mnt commit to install}"
W=/var/tmp/mnt-mgmt1
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
RAW="https://raw.githubusercontent.com/smallcapsteve/mineterminal-mnt/$REF"

rm -rf $W && install -d -o mnt -g mnt $W/cand
tar -C $LIVE -cf - --exclude='portal.db*' --exclude='__pycache__' --exclude='*.bak*' --exclude='*.sqlite*' \
    portal accuracy | tar -C $W/cand -xf -
cp -p $LIVE/sync_structured.py $LIVE/accuracy_run.py $LIVE/facts_sync.py $W/cand/
cd $W/cand || exit 2

echo "--- fetching the new files from the repo at $REF"
for f in portal/extractors/mgmt_roles.py portal/extractors/management.py portal/management_publish.py \
         portal/accuracy_management.py portal/extractors/__init__.py sync_structured.py \
         accuracy/sets/management.json; do
  curl -fsSL "$RAW/$f" -o "$f" || { echo "FAIL fetching $f"; exit 3; }
done

echo "--- checking what arrived"
cat > $W/SUMS_NEW <<'SUMS'
e5b3eac1146dce639089414a31d0997252092741a18b59728adcb9a3ad7356ad  portal/extractors/mgmt_roles.py
d32a3ac09019db6354fee656d4afd5d0a07da4e455af84b135fda6372c910db6  portal/extractors/__init__.py
e4c6567cc3caee4045e9edf34896f3ab219a514697cff0193ce16744db7b58a9  sync_structured.py
SUMS
sha256sum -c --quiet $W/SUMS_NEW && echo "small files: byte-for-byte the workspace copies" \
  || { echo "NOTE: a small file differs from the workspace copy"; sha256sum -c $W/SUMS_NEW; }
for f in portal/extractors/management.py portal/management_publish.py portal/accuracy_management.py \
         accuracy/sets/management.json; do
  echo "  $(sha256sum $f)"
done

echo "--- accuracy.py: the live file plus the five-line import (the 60 KB file never travels)"
$PY - <<'PY' || exit 3
import hashlib
BASE = "f3a0545856fdbbc55561809956b3be659ca57353d74d700a9fee87d2674dea18"
ADD = ('\n\n# MGMT_SPEC_V1 (2026-09-17): /management-changes shows one row per person, which is a different shape\n'
       '# from the three specs above, so it is scored in its own module. Imported last, when TagSpec and\n'
       '# register_spec exist, so that importing portal.accuracy registers every spec.\n'
       'from portal import accuracy_management as _accuracy_management  # noqa: E402,F401\n')
p = "portal/accuracy.py"
s = open(p, encoding="utf-8").read()
if "accuracy_management" in s:
    print("accuracy.py already carries the import")
else:
    got = hashlib.sha256(s.encode()).hexdigest()
    if got != BASE:
        raise SystemExit("REFUSED: live accuracy.py is %s, expected %s" % (got[:16], BASE[:16]))
    open(p, "w", encoding="utf-8").write(s.rstrip("\n") + "\n" + ADD)
    print("accuracy.py: 5 lines added, now", hashlib.sha256(open(p, 'rb').read()).hexdigest()[:16])
PY
chown -R mnt:mnt $W/cand
chmod 755 $W

echo "--- self-tests"
for m in portal.facts portal.normalize portal.accuracy portal.extractors.financings \
         portal.extractors.drill_results portal.extractors.management; do
  runuser -u mnt -- $PY -m $m > $W/st_$m.txt 2>&1 \
    && echo "  $m rc=0 $(tail -1 $W/st_$m.txt)" || { echo "  $m FAILED"; tail -20 $W/st_$m.txt; exit 3; }
done
for m in portal.management_publish portal.financing_publish portal.drill_publish; do
  runuser -u mnt -- $PY -m $m --selftest > $W/st_$m.txt 2>&1 \
    && echo "  $m rc=0 $(tail -1 $W/st_$m.txt)" || { echo "  $m FAILED"; tail -25 $W/st_$m.txt; exit 3; }
done
runuser -u mnt -- $PY -c "import sys; sys.path.insert(0, '.'); from portal.extractors import REGISTRY; \
print('registry', [(s.name, s.version, s.code_sha[:12]) for s in REGISTRY])" || exit 3
runuser -u mnt -- $PY -c "import sys; sys.path.insert(0, '.'); from portal import accuracy as A; \
print('specs', sorted(A.SPECS))" || exit 3

echo "--- reproduction against live release text (nothing written)"
curl -fsSL "$RAW/deploy/mgmt_v1/repro_mgmt.py" -o $W/repro_mgmt.py || exit 3
chown mnt:mnt $W/repro_mgmt.py
runuser -u mnt -- $PY $W/repro_mgmt.py
echo "repro rc=$?"
echo "STAGE_MGMT_DONE $(date -u +%FT%TZ)"
