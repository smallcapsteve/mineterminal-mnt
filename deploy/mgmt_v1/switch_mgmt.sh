#!/bin/bash
# MGMT_V1 1.0.0 switch: run the accuracy gate, which activates the version only if it scores at least
# 90% precision on every key field and keeps enough of the rows the page shows today. On a pass the
# publisher rebuilds management_changes, one row per person. (2026-09-17)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
cd $LIVE || exit 2

BEFORE=$(runuser -u mnt -- $PY -c "import sqlite3;c=sqlite3.connect('file:portal/portal.db?mode=ro',uri=True);\
print(c.execute('select count(*) from management_changes').fetchone()[0])")
echo "rows before: $BEFORE"
runuser -u mnt -- $PY -c "import sqlite3;c=sqlite3.connect('file:portal/portal.db?mode=ro',uri=True);\
print('backfilled records', c.execute(\"select count(*) from fx_records where extractor='management' and version='1.0.0'\").fetchone()[0]);\
print('runs', c.execute(\"select count(*) from fx_runs where extractor='management' and version='1.0.0'\").fetchone()[0])"

echo "--- dry run of the publisher (writes nothing)"
runuser -u mnt -- $PY -m portal.management_publish --dry-run --version 1.0.0

echo "--- gate"
runuser -u mnt -- $PY accuracy_run.py gate management
rc=$?
echo "gate rc=$rc"

runuser -u mnt -- $PY -c "import sqlite3;c=sqlite3.connect('file:portal/portal.db?mode=ro',uri=True);\
print('versions', list(c.execute(\"select extractor,version,status from fx_extractor_versions where extractor='management'\")))"

if [ "$rc" = "0" ]; then
  echo "--- publishing"
  runuser -u mnt -- $PY -m portal.management_publish
  runuser -u mnt -- $PY -c "import sqlite3;c=sqlite3.connect('file:portal/portal.db?mode=ro',uri=True);\
print('rows now', c.execute('select count(*) from management_changes').fetchone()[0]);\
print('with a person', c.execute('select count(*) from management_changes where person is not null').fetchone()[0]);\
print('releases', c.execute('select count(distinct event_id) from management_changes').fetchone()[0]);\
print('roles', c.execute('select count(distinct role_canon) from management_changes').fetchone()[0]);\
print('sample', list(c.execute('select ticker, action, person, role, scope from management_changes order by published_at desc limit 5')))"
  echo "page: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/management-changes)"
  curl -s http://127.0.0.1:8001/management-changes | grep -c 'mgmt-person' | sed 's/^/rows rendered: /'
fi
echo "SWITCH_MGMT_DONE $(date -u +%FT%TZ)"
