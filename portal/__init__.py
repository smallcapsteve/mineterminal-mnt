"""MNT portal package.

Two gates are installed here rather than in each caller, so that everything
importing portal.db gets the same rules: the web app, pipeline/run.py, all six
sync_*.py wire scrapers, and exchange_news.py.

_UNIVERSE_GATE (2026-09-13) decides who is allowed on the site.
_JV_GATE (2026-09-13) cross-files a release that names a second universe
company in its headline, so a joint-venture announcement appears under both
partners rather than only the one the collector picked.

Order is deliberate. The universe gate is installed first, so the JV gate wraps
it and runs outermost: a release for a company outside the universe is parked
for review first and only then considered for cross-filing, rather than being
tagged on its way to a queue.

Both fail open — see each module for why.
"""
from portal import universe_gate as _universe_gate
from portal import jv_gate as _jv_gate

_universe_gate.install()
_jv_gate.install()
