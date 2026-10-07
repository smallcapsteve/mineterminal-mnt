"""Registry of extractors that write to the facts store (FACTS_V1, 2026-09-16).

To add one:

    from portal.extractors import economic_studies
    REGISTRY.append(economic_studies.SPEC)

where SPEC is a portal.facts.ExtractorSpec whose code_sha changes with its code,
so a code change without a version bump is refused at registration.

DRILL_V1 (2026-09-17): the new Drill Results reader is the first extractor here.
It replaces what /drills shows once the accuracy gate activates it; until then
the legacy drill_backfill.py keeps writing drill_results (portal/drill_publish.py
decides which runs).

RES_V1 (2026-09-18): the Resource Estimates reader completes the set -- financings,
management and now resources all read from the facts store. Every page MNT extracts
is version-stamped, backfilled and gated; no legacy backfill writes a page any more
once its reader is active.
"""
from portal.extractors import drill_results as _drill_results
from portal.extractors import financings as _financings
from portal.extractors import management as _management
from portal.extractors import resources as _resources
from portal.extractors import economics as _economics
from portal.extractors import production as _production
from portal.extractors import royalties as _royalties
from portal.extractors import exploration as _exploration
from portal.extractors import technical as _technical
from portal.extractors import permits as _permits
from portal.extractors import options as _options
from portal.extractors import debt as _debt
from portal.extractors import mine_dev as _mine_dev
from portal.extractors import sampling as _sampling

# FIN_V1 (2026-09-17): the new financings reader; portal/financing_publish.py publishes the active version
# MGMT_V1 (2026-09-17): the new management-changes reader, one record per person;
# portal/management_publish.py publishes the active version
# RES_V1 (2026-09-18): the new Resource Estimates reader, one record per deposit per category;
# portal/resources_publish.py publishes the active version
# ECON_V1 (2026-09-21): the Economic Studies reader, one record per scenario; the first reader for a
# tag with no page of its own before it. portal/economics_publish.py publishes the active version
# PROD_V1 (2026-09-21): the Production Results reader, one record per metal per period or milestone;
# portal/production_publish.py publishes the active version
REGISTRY = [_drill_results.SPEC, _financings.SPEC, _management.SPEC, _resources.SPEC, _economics.SPEC,
            _production.SPEC,
            # ROY_V1 (2026-09-21): the Royalties & Streams reader, one record per interest in a deal;
            # portal/royalties_publish.py publishes the active version
            _royalties.SPEC,
            # EXPL_V1 (2026-09-21): the Exploration Programs reader, one record per field program;
            # portal/exploration_publish.py publishes the active version
            _exploration.SPEC,
            # TECH_V1 (2026-09-22): the Technical Reports reader, one record per NI 43-101 report;
            # portal/technical_publish.py publishes the active version
            _technical.SPEC,
            # PERMIT_V1 (2026-09-22): the Permits & Approvals reader, one record per permit at its stage;
            # portal/permits_publish.py publishes the active version
            _permits.SPEC,
            # OPT_V1 (2026-09-23): the Property Options & Staking reader, one record per land deal at its stage;
            # portal/options_publish.py publishes the active version
            _options.SPEC,
            # DEBT_V1 (2026-09-24): the Debt & Credit Facilities reader, one record per debt instrument at its
            # stage; portal/debt_publish.py publishes the active version
            _debt.SPEC,
            # DEV_V1 (2026-09-28): the Mine Development & Operations reader, one record per headline event;
            # portal/mine_dev_publish.py publishes the active version (tagged releases only)
            _mine_dev.SPEC,
            # SMP_V1 (2026-09-29): the Sampling & Geoscience Results reader, one record per sample type per
            # project; portal/sampling_publish.py publishes the active version (tagged releases)
            _sampling.SPEC]
