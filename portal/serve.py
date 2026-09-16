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

__all__ = ["app"]
