from __future__ import annotations
import hashlib
import hmac
import os
import time

MAX_SKEW = 300  # 5 minutes


def verify_hmac(body: bytes, ts_header: str | None, sig_header: str | None) -> bool:
    secret = os.environ.get("MNT_HMAC_SECRET")
    if not (secret and ts_header and sig_header):
        return False
    try:
        ts = int(ts_header)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - ts) > MAX_SKEW:
        return False
    if not sig_header.startswith("sha256="):
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{ts}.".encode("utf-8") + body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header[len("sha256=") :])
