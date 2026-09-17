#!/usr/bin/env python3
"""sync_structured.py — periodic re-extraction of financings / drill_results / resource_estimates from events.

Runs the same logic as the original backfill scripts but is safe to run repeatedly:
they all DELETE then re-INSERT from current events. Designed to be invoked by
a systemd timer every 30 minutes.

DRILL_PUBLISH_V1 (2026-09-17): drill_results is written by portal.drill_publish, which runs
after facts_sync so newly extracted releases are included. While the new Drill Results reader
is not active it runs the legacy drill_backfill.py instead; once active, the legacy backfill
never runs again."""
import subprocess, time

PY = '/opt/mnt/app/.venv/bin/python3'
steps = [
    (['/opt/mnt/app/financing_backfill.py'],  'financings'),
    (['/opt/mnt/app/resource_backfill.py'],   'resource_estimates'),
    (['/opt/mnt/app/management_backfill.py'], 'management_changes'),
    # FACTS_V1 (2026-09-16): incremental facts-store extraction for registered extractors
    (['/opt/mnt/app/facts_sync.py'],          'facts'),
    # DRILL_PUBLISH_V1 (2026-09-17): publish the active drill reader (or run the legacy backfill)
    (['-m', 'portal.drill_publish'],          'drill_results'),
    # ACCURACY_V1 (2026-09-16): re-measure pages against their accuracy sets at most once per 20 hours; always exits 0
    (['/opt/mnt/app/accuracy_run.py'],        'accuracy'),
]
for args, label in steps:
    print(f'[sync_structured] running {label} backfill')
    t0 = time.time()
    rc = subprocess.call([PY] + args, cwd='/opt/mnt/app')
    print(f'[sync_structured] {label}: rc={rc}  ({time.time()-t0:.1f}s)')
