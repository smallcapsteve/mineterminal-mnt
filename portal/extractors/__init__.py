"""Registry of extractors that write to the facts store (FACTS_V1, 2026-09-16).

To add one:

    from portal.extractors import economic_studies
    REGISTRY.append(economic_studies.SPEC)

where SPEC is a portal.facts.ExtractorSpec whose code_sha changes with its code,
so a code change without a version bump is refused at registration.

DRILL_V1 (2026-09-17): the new Drill Results reader is the first extractor here.
It replaces what /drills shows once the accuracy gate activates it; until then
the legacy drill_backfill.py keeps writing drill_results (portal/drill_publish.py
decides which runs). Resources are NOT here yet; they keep their own table until
they are rebuilt.
"""
from portal.extractors import drill_results as _drill_results
from portal.extractors import financings as _financings
from portal.extractors import management as _management

# FIN_V1 (2026-09-17): the new financings reader; portal/financing_publish.py publishes the active version
# MGMT_V1 (2026-09-17): the new management-changes reader, one record per person;
# portal/management_publish.py publishes the active version
REGISTRY = [_drill_results.SPEC, _financings.SPEC, _management.SPEC]
