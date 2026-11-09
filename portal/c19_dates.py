"""C19_DATES_V1 (2026-11-02, Justin popup: "Yes, MNT and MTP", amber at 3+ years): the date a restated resource estimate
is from. Reads /var/lib/mnt-c19/dates.json ({"rows": {"<event_id>|<ordinal>": {"d": date, "w": quoted words, "g": years
before the release}}}) written by /root/c19/c19_dates_update.py (frozen Haiku reader, blind check 96.4%). Re-checks the
file at most once a minute; any error -> no dates, so pages fall back to today's behaviour. Never touches portal.db."""
import json, os, time

PATH = "/var/lib/mnt-c19/dates.json"
OLD_YEARS = 3
_C = {"mtime": None, "rows": {}, "checked": 0.0}


def _rows():
    now = time.time()
    if now - _C["checked"] < 60:
        return _C["rows"]
    _C["checked"] = now
    try:
        m = os.stat(PATH).st_mtime
        if m != _C["mtime"]:
            with open(PATH) as f:
                _C["rows"] = json.load(f).get("rows", {})
            _C["mtime"] = m
    except Exception:
        pass
    return _C["rows"]


def get(event_id, ordinal):
    """{"d": "2010" | "2010-02" | "2010-02-01", "w": quoted words, "g": years before the release, "old": bool} or None"""
    if not event_id:
        return None
    o = _rows().get("%s|%s" % (event_id, ordinal))
    if not o:
        return None
    return {"d": o.get("d"), "w": o.get("w") or "", "g": o.get("g"), "old": (o.get("g") or 0) >= OLD_YEARS}
