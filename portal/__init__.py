"""MNT portal package.

_UNIVERSE_GATE (2026-09-13) is installed here rather than in each caller, so
that everything importing portal.db gets the same rule about who is allowed on
the site: the web app, pipeline/run.py, and all six sync_*.py wire scrapers.

See portal/universe_gate.py for what it does and why it fails open.
"""
from portal import universe_gate as _universe_gate

_universe_gate.install()
