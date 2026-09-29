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

# MNT_RESOURCES_API_V1 (2026-09-28): /api/v1/resources JSON - every resource row, by category, with a historic flag
# (MTP's $/oz screener and Compare). Guarded like the other API hooks.
try:
    from portal import resources_api
    resources_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("resources_api register failed")


# MNT_MGMT_API_V1 (2026-09-28): /api/v1/management-changes JSON - who joined, left or changed role (MTP's Management
# tab). Guarded like the other API hooks.
try:
    from portal import mgmt_api
    mgmt_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("mgmt_api register failed")


# MNT_MINE_DEV_API_V1 (2026-09-29): /api/v1/mine-development JSON - the Mine Development & Operations events
# (MTP's company Production page). Guarded like the other API hooks.
try:
    from portal import mine_dev_api
    mine_dev_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("mine_dev_api register failed")


# MNT_ROW_CHECKS_V1 (2026-09-29, reader review fix 4; Justin: "Show, marked"): every family API's rows carry `check` --
# the reasons a row fails a plain sanity test (portal/row_checks.py) -- and a request sorted by size lists flagged rows
# under `unranked` instead of ranking them. /api/v1/row-checks serves the daily counts (mnt-row-checks.timer).
try:
    import json as _rc_json
    from starlette.responses import Response as _RcResponse
    from portal import row_checks as _rc
    _RC_PATHS = {"/api/v1/" + _f: _f for _f in _rc.CHECKS}

    @app.middleware("http")
    async def _row_checks_mw(request, call_next):
        resp = await call_next(request)
        fam = _RC_PATHS.get(request.url.path)
        if fam is None or resp.status_code != 200 or "json" not in (resp.headers.get("content-type") or "") \
                or resp.headers.get("content-encoding"):
            return resp
        body = b"".join([c async for c in resp.body_iterator])
        try:
            body = _rc_json.dumps(_rc.annotate(fam, _rc_json.loads(body), request.query_params.get("sort")),
                                  ensure_ascii=False).encode("utf-8")
        except Exception:  # pragma: no cover - a check never breaks a response
            pass
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in ("content-length", "content-type")}
        return _RcResponse(content=body, status_code=resp.status_code, headers=headers, media_type="application/json")

    @app.get("/api/v1/row-checks")
    def _row_checks_summary():
        try:
            with open("/var/lib/mnt-portal/row_checks.json") as fh:
                return _rc_json.load(fh)
        except Exception:
            return {"ok": False, "note": "no summary yet"}
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("row_checks middleware failed")



# MNT_SAMPLING_API_V1 (2026-09-29): /api/v1/sampling JSON for MTP company pages (Sampling & Geoscience).
# Guarded like the other API hooks: if this module ever fails to import, the site still serves.
try:
    from portal import sampling_api
    sampling_api.register(app)
except Exception:  # pragma: no cover
    import logging
    logging.getLogger(__name__).exception("sampling_api register failed")

__all__ = ["app"]
