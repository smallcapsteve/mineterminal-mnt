#!/bin/bash
# Gate the backfilled economics candidate and republish /economic-studies from it. If the gate does
# not pass, the active version and the page are unchanged. (2026-09-21)
set -u
[ "$(hostname)" = "mnt-scraper-01" ] || { echo "REFUSED: wrong host"; exit 2; }
LIVE=/opt/mnt/app
PY=$LIVE/.venv/bin/python3
DB=$LIVE/portal/portal.db
VER="${ECON_VERSION:?set ECON_VERSION}"
q() { $PY -c "import sqlite3, sys; c = sqlite3.connect('file:$DB?mode=ro', uri=True); print(c.execute(sys.argv[1]).fetchall())" "$1"; }
systemctl is-active --quiet fx-backfill-economics && { echo "REFUSED: backfill still running"; exit 2; }
journalctl -u fx-backfill-economics --no-pager -o cat | tail -2
q "SELECT version, status FROM fx_extractor_versions WHERE extractor='economics' ORDER BY version"
q "SELECT COUNT(*), SUM(status='error') FROM fx_runs WHERE extractor='economics' AND version='$VER'"
cd $LIVE || exit 2
runuser -u mnt -- $PY accuracy_run.py gate economics 2>&1 | tail -25
st=$(q "SELECT status FROM fx_extractor_versions WHERE extractor='economics' AND version='$VER'")
echo "status $VER: $st"
[ "$st" = "[('active',)]" ] || { echo "NOT ACTIVATED: the page still shows the previous version"; exit 3; }
runuser -u mnt -- $PY -m portal.economics_publish || exit 3
q "SELECT extractor_version, COUNT(*), COUNT(scenario), SUM(context='announced' AND scenario IS NOT NULL) FROM economic_studies GROUP BY 1"
q "SELECT COUNT(DISTINCT a.event_id) FROM economic_studies a JOIN economic_studies b ON a.event_id=b.event_id AND a.ordinal<b.ordinal AND a.npv_after_tax=b.npv_after_tax"
for p in /economic-studies "/economic-studies?show=all" /resources /drills; do
  echo "  $(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8001$p") $p"
done
echo "GATE_ECON_DONE $(date -u +%FT%TZ)"
