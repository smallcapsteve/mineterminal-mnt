#!/bin/bash
# FACTS_PAR_V1: start a backfill (a full re-read of the corpus by one reader) the standard way: 3 reader processes,
# low priority (nice 10, readers nice 19, idle I/O), queued behind any backfill already running (facts_sync.py
# waits for its turn and logs "queued behind ..."). Usage: fx_backfill.sh NAME [UNIT_SUFFIX]
# Logs: journalctl -u fx-backfill-<UNIT_SUFFIX or NAME>
set -u
NAME=${1:?usage: fx_backfill.sh NAME [UNIT_SUFFIX]}; SUF=${2:-$NAME}
APP=/opt/mnt/app; PY=$APP/.venv/bin/python3
case "$NAME" in *[!a-z0-9_]*) echo "bad reader name: $NAME"; exit 2;; esac
case "$SUF" in *[!a-z0-9_-]*) echo "bad unit suffix: $SUF"; exit 2;; esac
systemctl reset-failed fx-backfill-$SUF 2>/dev/null
# BFGUARD_V1 2026-10-06: inside the background cap and the site guard, like every other one-off job
exec systemd-run --unit fx-backfill-$SUF --slice=mnt-batch-oneoff.slice -p User=mnt -p WorkingDirectory=$APP -p CPUQuota=300% -p Nice=10 \
  -p IOSchedulingClass=idle $PY $APP/facts_sync.py --backfill $NAME
