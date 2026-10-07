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
    # READER_TAGS_V1 (2026-09-30): a reader's admitted outside-tag finds give the release its tag, before the
    # publishers read events.categories (portal/reader_tags.py; kill switch portal/reader_admit/OFF)
    (['-m', 'portal.reader_tags'],           'reader_tags'),
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
    # PERMIT_PUBLISH_V1 (2026-09-22): publish the active permits reader, one row per permit at its stage.
    # There is no legacy reader: until a version is active it does nothing.
    (['-m', 'portal.permits_publish'],       'permits'),
    # OPT_PUBLISH_V1 (2026-09-23): publish the active options reader, one row per land deal at its stage.
    # There is no legacy reader: until a version is active it does nothing.
    (['-m', 'portal.options_publish'],       'land_deals'),
    # DEBT_PUBLISH_V1 (2026-09-24): publish the active debt reader, one row per debt instrument at its stage.
    # There is no legacy reader: until a version is active it does nothing.
    (['-m', 'portal.debt_publish'],          'debt_deals'),
    # DEV_PUBLISH_V1 (2026-09-28): publish the active mine_dev reader, one row per headline event of a tagged
    # release. There is no legacy reader: until a version is active it does nothing.
    (['-m', 'portal.mine_dev_publish'],      'mine_dev_events'),
    # SMP_PUBLISH_V1 (2026-09-29): publish the active sampling reader, one row per sample type per project of a
    # tagged release. There is no legacy reader: until a version is active it does nothing.
    (['-m', 'portal.sampling_publish'],      'sampling_results'),
    # ACCURACY_V1 (2026-09-16): re-measure pages against their accuracy sets at most once per 20 hours; always exits 0
    (['/opt/mnt/app/accuracy_run.py'],        'accuracy'),
]
# OPTD step B (2026-10-06): a publisher whose inputs have not changed since its last successful run is skipped,
# with a full rebuild at least every 8 hours (portal/publish_skip.py). Kill switch: portal/publish_skip_OFF.
try:
    from portal import publish_skip as _ps
except Exception as _e:  # noqa: BLE001 - without it everything runs as before
    print(f'[sync_structured] publish_skip unavailable ({_e}); running everything')
    _ps = None
for args, label in steps:
    _skip = _ps.before(label) if _ps else None
    if _skip and _skip.get('skip'):
        print(f'[sync_structured] {label}: skipped - {_skip["why"]}')
        continue
    if _skip:
        print(f'[sync_structured] {label}: running - {_skip["why"]}')
    print(f'[sync_structured] running {label} backfill')
    t0 = time.time()
    rc = subprocess.call([PY] + args, cwd='/opt/mnt/app')
    print(f'[sync_structured] {label}: rc={rc}  ({time.time()-t0:.1f}s)')
    if _ps:
        _ps.after(label, _skip, rc)
