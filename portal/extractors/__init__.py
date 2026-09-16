"""Registry of extractors that write to the facts store (FACTS_V1, 2026-09-16).

Empty until step 4 (Economic Studies). To add one:

    from portal.extractors import economic_studies
    REGISTRY.append(economic_studies.SPEC)

where SPEC is a portal.facts.ExtractorSpec whose code_sha is
portal.facts.file_blob_sha(__file__), so a code change without a version bump
is refused at registration.

The four existing extractors (drills, financings, resources, management) are
NOT here; they keep their own tables until a consumer needs them moved.
"""
REGISTRY = []
