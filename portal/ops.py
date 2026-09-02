"""
HMAC-signed operational endpoints for remote administration.

All endpoints under /ops/* require a valid HMAC signature over the request
body using the same scheme as /ingest (X-MNT-Timestamp + X-MNT-Signature,
5-minute skew window, verified via portal.ingest.verify_hmac).

Security model: equivalent to SSH. Whoever holds MNT_HMAC_SECRET can execute
arbitrary commands as the portal's OS user (mnt). A narrow sudoers rule
permits a few systemctl operations for service management. Nothing here
escalates beyond mnt + those whitelisted systemctl targets.

Endpoints:
    POST /ops/ping     -> liveness + identity check
    POST /ops/exec     -> run a shell command, capture stdout/stderr/rc
    POST /ops/read     -> read a file off disk
    POST /ops/write    -> write a file to disk
"""
from __future__ import annotations

import asyncio
import base64
import getpass
import json
import logging
import os
import platform
import socket
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from portal import ingest

log = logging.getLogger("portal.ops")

router = APIRouter(prefix="/ops", tags=["ops"])

DEFAULT_TIMEOUT_S = 60.0
MAX_TIMEOUT_S = 600.0
MAX_READ_BYTES = 8 * 1024 * 1024          # 8 MiB
MAX_OUTPUT_BYTES = 2 * 1024 * 1024        # 2 MiB per stream
MAX_WRITE_BYTES = 16 * 1024 * 1024        # 16 MiB


async def _require_hmac(
    request: Request,
    x_mnt_timestamp: Optional[str],
    x_mnt_signature: Optional[str],
) -> bytes:
    body = await request.body()
    if not ingest.verify_hmac(body, x_mnt_timestamp, x_mnt_signature):
        peer = request.client.host if request.client else "?"
        log.warning("ops: bad signature from %s for %s", peer, request.url.path)
        raise HTTPException(401, "bad signature")
    return body


def _parse_json(body: bytes) -> dict:
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "bad json")


@router.post("/ping")
async def ops_ping(
    request: Request,
    x_mnt_timestamp: Optional[str] = Header(default=None, alias="X-MNT-Timestamp"),
    x_mnt_signature: Optional[str] = Header(default=None, alias="X-MNT-Signature"),
):
    await _require_hmac(request, x_mnt_timestamp, x_mnt_signature)
    return {
        "ok": True,
        "user": getpass.getuser(),
        "host": socket.gethostname(),
        "cwd": os.getcwd(),
        "python": platform.python_version(),
        "ts": time.time(),
    }


@router.post("/exec")
async def ops_exec(
    request: Request,
    x_mnt_timestamp: Optional[str] = Header(default=None, alias="X-MNT-Timestamp"),
    x_mnt_signature: Optional[str] = Header(default=None, alias="X-MNT-Signature"),
):
    body = await _require_hmac(request, x_mnt_timestamp, x_mnt_signature)
    payload = _parse_json(body)

    cmd = payload.get("cmd")
    if not isinstance(cmd, str) or not cmd.strip():
        raise HTTPException(400, "cmd (string) required")

    cwd = payload.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        raise HTTPException(400, "cwd must be string")

    timeout_s = float(payload.get("timeout_s") or DEFAULT_TIMEOUT_S)
    timeout_s = min(max(timeout_s, 1.0), MAX_TIMEOUT_S)

    log.info("ops.exec cmd=%r cwd=%r timeout=%.1fs", cmd[:200], cwd, timeout_s)

    start = time.time()
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    except Exception as e:
        log.exception("ops.exec failed to spawn: %s", e)
        raise HTTPException(500, f"spawn failed: {e}")

    timed_out = False
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        timed_out = True
        try:
            proc.kill()
        except Exception:
            pass
        try:
            stdout_b, stderr_b = await proc.communicate()
        except Exception:
            stdout_b, stderr_b = b"", b""

    rc = proc.returncode if proc.returncode is not None else -1

    def _decode(b: bytes, limit: int) -> tuple[str, bool]:
        truncated = len(b) > limit
        if truncated:
            b = b[:limit]
        return b.decode("utf-8", errors="replace"), truncated

    so, so_trunc = _decode(stdout_b or b"", MAX_OUTPUT_BYTES)
    se, se_trunc = _decode(stderr_b or b"", MAX_OUTPUT_BYTES)
    if timed_out:
        se = (se + f"\n[ops] timeout after {timeout_s:.1f}s; process killed\n").lstrip()

    return {
        "rc": rc,
        "stdout": so,
        "stderr": se,
        "stdout_truncated": so_trunc,
        "stderr_truncated": se_trunc,
        "duration_s": round(time.time() - start, 3),
        "timed_out": timed_out,
    }


@router.post("/read")
async def ops_read(
    request: Request,
    x_mnt_timestamp: Optional[str] = Header(default=None, alias="X-MNT-Timestamp"),
    x_mnt_signature: Optional[str] = Header(default=None, alias="X-MNT-Signature"),
):
    body = await _require_hmac(request, x_mnt_timestamp, x_mnt_signature)
    payload = _parse_json(body)

    path = payload.get("path")
    if not isinstance(path, str) or not path:
        raise HTTPException(400, "path required")

    max_bytes = int(payload.get("max_bytes") or MAX_READ_BYTES)
    max_bytes = min(max_bytes, MAX_READ_BYTES)
    offset = int(payload.get("offset") or 0)

    try:
        p = Path(path)
        size = p.stat().st_size
        with p.open("rb") as f:
            if offset:
                f.seek(offset)
            data = f.read(max_bytes)
    except FileNotFoundError:
        raise HTTPException(404, f"not found: {path}")
    except IsADirectoryError:
        raise HTTPException(400, f"is a directory: {path}")
    except PermissionError as e:
        raise HTTPException(403, f"permission denied: {e}")
    except Exception as e:
        raise HTTPException(500, f"read failed: {e}")

    try:
        content = data.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        content = base64.b64encode(data).decode("ascii")
        encoding = "base64"

    return {
        "path": str(p),
        "size": size,
        "offset": offset,
        "bytes_read": len(data),
        "truncated": (offset + len(data)) < size,
        "encoding": encoding,
        "content": content,
    }


@router.post("/write")
async def ops_write(
    request: Request,
    x_mnt_timestamp: Optional[str] = Header(default=None, alias="X-MNT-Timestamp"),
    x_mnt_signature: Optional[str] = Header(default=None, alias="X-MNT-Signature"),
):
    body = await _require_hmac(request, x_mnt_timestamp, x_mnt_signature)
    payload = _parse_json(body)

    path = payload.get("path")
    content = payload.get("content")
    encoding = payload.get("encoding", "utf-8")
    mode = payload.get("mode")
    mkdirs = bool(payload.get("mkdirs", False))
    append = bool(payload.get("append", False))

    if not isinstance(path, str) or not path:
        raise HTTPException(400, "path required")
    if not isinstance(content, str):
        raise HTTPException(400, "content (string) required")

    if encoding == "utf-8":
        data = content.encode("utf-8")
    elif encoding == "base64":
        try:
            data = base64.b64decode(content)
        except Exception as e:
            raise HTTPException(400, f"bad base64: {e}")
    else:
        raise HTTPException(400, f"unsupported encoding: {encoding}")

    if len(data) > MAX_WRITE_BYTES:
        raise HTTPException(413, f"content too large: {len(data)} > {MAX_WRITE_BYTES}")

    try:
        p = Path(path)
        if mkdirs:
            p.parent.mkdir(parents=True, exist_ok=True)
        flag = "ab" if append else "wb"
        with p.open(flag) as f:
            f.write(data)
        if mode is not None:
            os.chmod(p, int(mode))
    except PermissionError as e:
        raise HTTPException(403, f"permission denied: {e}")
    except Exception as e:
        raise HTTPException(500, f"write failed: {e}")

    return {
        "ok": True,
        "path": str(p),
        "bytes_written": len(data),
        "appended": append,
    }
