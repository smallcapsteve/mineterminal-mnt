"""Process entry point for the MNT portal (2026-09-14).

The unit runs `uvicorn portal.serve:app`, not `uvicorn portal.app:app`. It is
the same application object — imported, not copied — plus the additive blocks
that live in modules of their own. Today that is one: the /api/search
type-ahead behind the nav search box (MNT_TYPEAHEAD_V1).

Why the indirection exists. app.py is 2,000 lines and grows by blocks appended
to its end. A block added from a session that can only write whole files has to
resend all 2,000 lines to add two, and that is how a file that nobody reads
end-to-end acquires a change nobody meant to make. A module plus this three-line
entry point costs one line in the systemd unit instead.

What it costs if it is forgotten: point the unit back at portal.app:app and the
site still runs, unchanged, minus the search dropdown — /api/search 404s and
the box falls back to the plain text search it was before. Nothing else in the
application depends on this file.
"""
from portal.app import app, templates
from portal import typeahead

typeahead.register(app)

# LINK_PREVIEW_V1 (2026-09-16): share-card tags on every page + root icons.
from portal import link_preview
link_preview.register(app, templates)

# MNT_DRILLS_API_V1 (2026-09-17): /api/v1/drills JSON for MTP's /drilling and company pages.
# Guarded like the news API hook: if this module ever fails to import, the site still serves.
try:
    from portal import drills_api
    drills_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("drills_api register failed")


# MNT_FINANCINGS_API_V1 (2026-09-17): /api/v1/financings JSON for MTP's /financings and
# company pages. Guarded like the drills hook: if this module ever fails to import, the
# site still serves.
try:
    from portal import financings_api
    financings_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("financings_api register failed")


# MNT_ECONOMICS_API_V1 (2026-09-21): /api/v1/economics JSON for MTP company pages.
# Guarded like the other API hooks: if this module ever fails to import, the site still serves.
try:
    from portal import economics_api
    economics_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("economics_api register failed")


# MNT_PRODUCTION_API_V1 (2026-09-21): /api/v1/production JSON for MTP company pages.
# Guarded like the other API hooks: if this module ever fails to import, the site still serves.
try:
    from portal import production_api
    production_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("production_api register failed")


# MNT_ROYALTIES_API_V1 (2026-09-21): /api/v1/royalties JSON for MTP company pages.
# Guarded like the other API hooks: if this module ever fails to import, the site still serves.
try:
    from portal import royalties_api
    royalties_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("royalties_api register failed")


# MNT_EXPLORATION_API_V1 (2026-09-22): /api/v1/exploration JSON for MTP company pages.
# Guarded like the other API hooks: if this module ever fails to import, the site still serves.
try:
    from portal import exploration_api
    exploration_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("exploration_api register failed")


# MNT_TECHNICAL_API_V1 (2026-09-22): /api/v1/technical JSON for MTP company pages.
# Guarded like the other API hooks: if this module ever fails to import, the site still serves.
try:
    from portal import technical_api
    technical_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("technical_api register failed")


# MNT_PERMITS_API_V1 (2026-09-23): /api/v1/permits JSON for MTP company pages.
# Guarded like the other API hooks: if this module ever fails to import, the site still serves.
try:
    from portal import permits_api
    permits_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("permits_api register failed")


# MNT_PROPERTY_OPTIONS_API_V1 (2026-09-23): /api/v1/property-options JSON for MTP company pages.
# Guarded like the other API hooks: if this module ever fails to import, the site still serves.
try:
    from portal import property_options_api
    property_options_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("property_options_api register failed")


# MNT_DEBT_API_V1 (2026-09-25): /api/v1/debt JSON for MTP company pages.
# Guarded like the other API hooks: if this module ever fails to import, the site still serves.
try:
    from portal import debt_api
    debt_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("debt_api register failed")

__all__ = ["app"]
