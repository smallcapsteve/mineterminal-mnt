#!/usr/bin/env python3
"""sync_structured.py — periodic re-extraction of financings / drill_results / resource_estimates from events.

Runs the same logic as the original backfill scripts but is safe to run repeatedly:
they all DELETE then re-INSERT from current events. Designed to be invoked by
a systemd timer every 30 minutes."""
import subprocess, time

scripts = [
    ('/opt/mnt/app/financing_backfill.py',  'financings'),
    ('/opt/mnt/app/drill_backfill.py',      'drill_results'),
    ('/opt/mnt/app/resource_backfill.py',   'resource_estimates'),
    ('/opt/mnt/app/management_backfill.py', 'management_changes'),
    # FACTS_V1 (2026-09-16): incremental facts-store extraction; a no-op until an extractor is registered
    ('/opt/mnt/app/facts_sync.py',          'facts'),
]
for path, label in scripts:
    print(f'[sync_structured] running {label} backfill')
    t0 = time.time()
    rc = subprocess.call(['/opt/mnt/app/.venv/bin/python3', path])
    print(f'[sync_structured] {label}: rc={rc}  ({time.time()-t0:.1f}s)')
