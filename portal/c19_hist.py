"""C19_HIST_V1 (2026-11-01, Justin popup: "Yes, MNT and MTP"): historical-estimate flag for resource rows.
Reads /var/lib/mnt-c19/hist_flags.json ({"keys": ["<event_id>|<ordinal>", ...]}) written by /root/c19/c19_update.py
(frozen rules classify2.py sha16 16938d52e24cbfdf). Re-checks the file at most once a minute; any error -> no flags,
so the page falls back to today's behaviour. Never touches portal.db."""
import json, os, time

PATH = "/var/lib/mnt-c19/hist_flags.json"
_C = {"mtime": None, "keys": frozenset(), "checked": 0.0}


def _keys():
    now = time.time()
    if now - _C["checked"] < 60:
        return _C["keys"]
    _C["checked"] = now
    try:
        m = os.stat(PATH).st_mtime
        if m != _C["mtime"]:
            with open(PATH) as f:
                _C["keys"] = frozenset(json.load(f).get("keys", []))
            _C["mtime"] = m
    except Exception:
        pass
    return _C["keys"]


def is_hist(event_id, ordinal) -> bool:
    if not event_id:
        return False
    return ("%s|%s" % (event_id, ordinal)) in _keys()
