#!/usr/bin/env python3
"""sync_structured.py — periodic re-extraction of financings / drill_results / resource_estimates from events.

Runs the same logic as the original backfill scripts but is safe to run repeatedly:
they all DELETE then re-INSERT from current events. Designed to be invoked by
a systemd timer every 30 minutes.

DRILL_PUBLISH_V1 (2026-09-17): drill_results is written by portal.drill_publish, which runs
after facts_sync so newly extracted releases are included. While the new Drill Results reader
is not active it runs the legacy drill_backfill.py instead; once active, the legacy backfill
never runs again.

FIN_PUBLISH_V1 (2026-09-17): financings and financing_events are written by portal.financing_publish, after
facts_sync, on the same terms: the legacy financing_backfill.py runs only until a financings version is active.

MGMT_PUBLISH_V1 (2026-09-17): management_changes is written by portal.management_publish, on the same terms.
It moved from first to last in this list because it now reads the facts store, which facts_sync fills.

RES_PUBLISH_V1 (2026-09-18): resource_estimates is written by portal.resources_publish, on the same
terms, and moved for the same reason. With it, every structured page MNT builds comes from a
version-stamped, gated reader rather than a backfill script."""
import subprocess, time

PY = '/opt/mnt/app/.venv/bin/python3'
steps = [
    # FACTS_V1 (2026-09-16): incremental facts-store extraction for registered extractors
    (['/opt/mnt/app/facts_sync.py'],          'facts'),
    # DRILL_PUBLISH_V1 (2026-09-17): publish the active drill reader (or run the legacy backfill)
    (['-m', 'portal.drill_publish'],          'drill_results'),
    # FIN_PUBLISH_V1 (2026-09-17): publish the active financings reader (or run the legacy financing_backfill.py until one is active)
    (['-m', 'portal.financing_publish'],      'financings'),
    # MGMT_PUBLISH_V1 (2026-09-17): publish the active management reader, one row per person (or run the
    # legacy management_backfill.py until one is active)
    (['-m', 'portal.management_publish'],     'management_changes'),
    # RES_PUBLISH_V1 (2026-09-18): publish the active resources reader, one row per deposit per
    # category (or run the legacy resource_backfill.py until one is active). It moved from first
    # to last in this list because it now reads the facts store, which facts_sync fills.
    (['-m', 'portal.resources_publish'],      'resource_estimates'),
    # ECON_PUBLISH_V1 (2026-09-21): publish the active economics reader, one row per scenario. There is
    # no legacy reader: until a version is active it does nothing.
    (['-m', 'portal.economics_publish'],     'economic_studies'),
    # PROD_PUBLISH_V1 (2026-09-21): publish the active production reader, one row per metal per period.
    # There is no legacy reader: until a version is active it does nothing.
    (['-m', 'portal.production_publish'],    'production_results'),
    # ROY_PUBLISH_V1 (2026-09-21): publish the active royalties reader, one row per interest in a deal.
    # There is no legacy reader: until a version is active it does nothing.
    (['-m', 'portal.royalties_publish'],     'royalty_deals'),
    # EXPL_PUBLISH_V1 (2026-09-21): publish the active exploration reader, one row per field program.
    # There is no legacy reader: until a version is active it does nothing.
    (['-m', 'portal.exploration_publish'],   'exploration_programs'),
    # TECH_PUBLISH_V1 (2026-09-22): publish the active technical-reports reader, one row per report.
    # There is no legacy reader: until a version is active it does nothing.
    (['-m', 'portal.technical_publish'],     'technical_reports'),
    # ACCURACY_V1 (2026-09-16): re-measure pages against their accuracy sets at most once per 20 hours; always exits 0
    (['/opt/mnt/app/accuracy_run.py'],        'accuracy'),
]
for args, label in steps:
    print(f'[sync_structured] running {label} backfill')
    t0 = time.time()
    rc = subprocess.call([PY] + args, cwd='/opt/mnt/app')
    print(f'[sync_structured] {label}: rc={rc}  ({time.time()-t0:.1f}s)')
