#!/bin/bash
# RES_V1 1.0.16 switch: measure, then run the accuracy gate, which activates the version only if it
# scores at least 90% precision on every key field and keeps enough of the releases the page shows
# today. On a pass the publisher rebuilds resource_estimates, one row per deposit per category --
# which means DROPPING the legacy table, because its `event_id TEXT NOT NULL UNIQUE` cannot be
# altered away and is exactly the shape being replaced. (2026-09-18)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
cd $LIVE || exit 2
RO="file:portal/portal.db?mode=ro"

BEFORE=$(runuser -u mnt -- $PY -c "import sqlite3;c=sqlite3.connect('$RO',uri=True);\
print(c.execute('select count(*) from resource_estimates').fetchone()[0])")
echo "rows before: $BEFORE"
runuser -u mnt -- $PY -c "import sqlite3;c=sqlite3.connect('$RO',uri=True);\
print('backfilled records', c.execute(\"select count(*) from fx_records where extractor='resources' and version='1.0.16'\").fetchone()[0]);\
print('runs', c.execute(\"select count(*) from fx_runs where extractor='resources' and version='1.0.16'\").fetchone()[0])"

echo "--- measure (scores the candidate without activating anything)"
runuser -u mnt -- $PY accuracy_run.py measure resources
echo "measure rc=$?"

echo "--- dry run of the publisher (writes nothing)"
runuser -u mnt -- $PY -m portal.resources_publish --dry-run --version 1.0.16

echo "--- gate"
runuser -u mnt -- $PY accuracy_run.py gate resources
rc=$?
echo "gate rc=$rc"

runuser -u mnt -- $PY -c "import sqlite3;c=sqlite3.connect('$RO',uri=True);\
print('versions', list(c.execute(\"select extractor,version,status from fx_extractor_versions where extractor='resources'\")))"

if [ "$rc" = "0" ]; then
  echo "--- publishing"
  runuser -u mnt -- $PY -m portal.resources_publish
  runuser -u mnt -- $PY -c "import sqlite3;c=sqlite3.connect('$RO',uri=True);\
print('rows now', c.execute('select count(*) from resource_estimates').fetchone()[0]);\
print('releases', c.execute('select count(distinct event_id) from resource_estimates').fetchone()[0]);\
print('with a tonnage', c.execute('select count(*) from resource_estimates where tonnes is not null').fetchone()[0]);\
print('with a deposit', c.execute('select count(*) from resource_estimates where deposit is not null').fetchone()[0]);\
print('background', c.execute(\"select count(*) from resource_estimates where context='background'\").fetchone()[0]);\
print('categories', list(c.execute('select category, count(*) from resource_estimates group by category order by 2 desc')));\
print('sample', list(c.execute('select ticker, deposit, category, tonnes, summary from resource_estimates order by published_at desc limit 5')))"
  echo "the page still runs the OLD handler here; it reads summary and categories_json, which the new table keeps"
  echo "/resources: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/resources)"
  echo "/api/resources/recent.json: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/api/resources/recent.json)"
fi
echo "SWITCH_RES_DONE $(date -u +%FT%TZ)"
