from __future__ import annotations
import os
import time
from fastapi import Request
from itsdangerous import BadSignature, TimestampSigner
import bcrypt

SESSION_COOKIE = "mnt_session"
SESSION_MAX_AGE = 8 * 60 * 60  # 8 hours


def _signer() -> TimestampSigner:
    secret = os.environ.get("MNT_SESSION_SECRET")
    if not secret:
        raise RuntimeError("MNT_SESSION_SECRET not set")
    return TimestampSigner(secret)


def verify_password(plain: str) -> bool:
    stored = os.environ.get("MNT_ADMIN_PASSWORD_HASH", "")
    if not stored:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8"))
    except Exception:
        return False


def make_session_token() -> str:
    return _signer().sign(f"admin:{int(time.time())}").decode("utf-8")


def valid_session(token: str | None) -> bool:
    if not token:
        return False
    try:
        _signer().unsign(token, max_age=SESSION_MAX_AGE)
        return True
    except BadSignature:
        return False


def is_logged_in(request: Request) -> bool:
    return valid_session(request.cookies.get(SESSION_COOKIE))
