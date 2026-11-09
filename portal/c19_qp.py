"""C19_QP_V1 (2026-11-02, Justin popup: firm only, "let's push this out to live"): who prepared a resource estimate,
according to the release. Reads /var/lib/mnt-c19/qp.json ({"rows": {"<event_id>|<ordinal>": {"f": lead firm, "fs": firms,
"q": QP names, "b": basis, "w": quoted words}}}) written by /root/c19/c19_qp_update.py (frozen Haiku reader + second
look; blind check in claude/C19_AUDIT_2026-11-01.md). Re-checks the file at most once a minute; any error -> nothing
shown, so pages fall back to today's behaviour. Never touches portal.db."""
import json, os, time

PATH = "/var/lib/mnt-c19/qp.json"
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
    """{"firm": lead firm or "", "firms": [...], "qps": [...], "label": what to show, "why": quoted words} or None"""
    if not event_id:
        return None
    o = _rows().get("%s|%s" % (event_id, ordinal))
    if not o:
        return None
    firm, qps = o.get("f") or "", o.get("q") or []
    label = firm or ", ".join(qps[:2]) + (" et al." if len(qps) > 2 else "")
    if not label:
        return None
    return {"firm": firm, "firms": o.get("fs") or ([firm] if firm else []), "qps": qps, "label": label, "why": o.get("w") or ""}
