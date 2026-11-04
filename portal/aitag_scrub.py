"""AITAG_SCRUB_V1 (2026-11-04): strip reader-provenance fields from MNT's public JSON feeds.

Justin, 2026-11-04 (popup "Strip from public feeds"): the feeds should not say which reader found a row.
For every /api/ response with a JSON body this removes
  ai_label, ai_fields, reader_qty             (any depth)
  reader      when it is "hybrid" or "rules"
  source      when it is "ai" or "reader"
and replaces any string value of a "note" key that mentions an AI / automatic reading with a neutral source line.
Nothing in the database changes; the page templates are unaffected. Off switch: touch /etc/mnt-aitag-scrub-off
(checked per request, no restart).

Registered from portal/serve.py, guarded: if this module fails to import the site serves unchanged.
"""
import json, os, re

DROP = {"ai_label", "ai_fields", "reader_qty"}
NOTE_KEYS = {"note", "side_note", "reader_note", "source_note"}
NOTE_BAD = re.compile(r"\bAI\b|Claude|Sonnet|Haiku|read automatically|automatically|rules reader|may be missing|Early version", re.I)
NEUTRAL = "Source: company news releases."
OFF = "/etc/mnt-aitag-scrub-off"


def _clean(o):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if k in DROP:
                continue
            if k == "reader" and v in ("hybrid", "rules"):
                continue
            if k == "source" and v in ("ai", "reader"):
                continue
            if k in NOTE_KEYS and isinstance(v, str) and NOTE_BAD.search(v):
                out[k] = NEUTRAL
                continue
            out[k] = _clean(v)
        return out
    if isinstance(o, list):
        return [_clean(x) for x in o]
    return o


def scrub_bytes(body):
    """Return cleaned JSON bytes, or None when nothing changed / not JSON."""
    try:
        data = json.loads(body)
    except Exception:
        return None
    new = _clean(data)
    if new == data:
        return None
    return json.dumps(new, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def register(app):
    from starlette.responses import Response

    @app.middleware("http")
    async def _aitag_scrub(request, call_next):   # AITAG_SCRUB_V1
        response = await call_next(request)
        body = None
        try:
            if not request.url.path.startswith("/api/"):
                return response
            if os.path.exists(OFF):
                return response
            ctype = response.headers.get("content-type", "")
            if "json" not in ctype:
                return response
            enc = (response.headers.get("content-encoding") or "").lower()
            if enc not in ("", "gzip"):
                return response
            chunks = [c async for c in response.body_iterator]
            body = b"".join(chunks)
            if enc == "gzip":
                import gzip
                raw = gzip.decompress(body)
                cleaned = scrub_bytes(raw)
                new = gzip.compress(cleaned, 6) if cleaned is not None else None
            else:
                new = scrub_bytes(body)
            headers = {k: v for k, v in response.headers.items() if k.lower() not in ("content-length",)}
            return Response(content=new if new is not None else body, status_code=response.status_code,
                            headers=headers, media_type=None)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("aitag scrub failed")
            if body is not None:   # the original body was already read: send it unchanged
                headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
                return Response(content=body, status_code=response.status_code, headers=headers, media_type=None)
            return response


if __name__ == "__main__":
    # self-test
    sample = {"reader": "hybrid", "items": [{"ai_label": "AI-read", "x": 1, "terms": {"note": "Royalties and payments read by an AI reader"}},
                                            {"source": "ai", "ai_fields": ["all"], "reader_qty": 3, "qty": 5},
                                            {"source": "company", "reader": "someone"}], "note": "Read from each release"}
    out = json.loads(scrub_bytes(json.dumps(sample)))
    assert "reader" not in out and out["note"] == "Read from each release"
    assert out["items"][0] == {"x": 1, "terms": {"note": NEUTRAL}}
    assert out["items"][1] == {"qty": 5}
    assert out["items"][2] == {"source": "company", "reader": "someone"}
    assert scrub_bytes(json.dumps({"a": 1})) is None
    print("aitag_scrub selftest ok")
