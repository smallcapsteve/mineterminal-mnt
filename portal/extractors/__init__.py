"""Registry of extractors that write to the facts store (FACTS_V1, 2026-09-16).

To add one:

    from portal.extractors import economic_studies
    REGISTRY.append(economic_studies.SPEC)

where SPEC is a portal.facts.ExtractorSpec whose code_sha changes with its code,
so a code change without a version bump is refused at registration.

DRILL_V1 (2026-09-17): the new Drill Results reader is the first extractor here.
It replaces what /drills shows once the accuracy gate activates it; until then
the legacy drill_backfill.py keeps writing drill_results (portal/drill_publish.py
decides which runs). Financings, resources and management are NOT here; they
keep their own tables until they are rebuilt.
"""
from portal.extractors import drill_results as _drill_results

REGISTRY = [_drill_results.SPEC]
