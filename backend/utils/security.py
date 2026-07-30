# ============================================================
# backend/utils/security.py
# KrashiMitra — Boot guards, rate limiting, security headers
# ============================================================

import logging
import os
import time
import threading
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

IS_PROD = bool(os.getenv("RENDER"))

_access_log = logging.getLogger("krashimitra.access")

# Values that ship in the repo as fallbacks — safe locally, fatal in production.
_INSECURE_DEFAULTS = {
    "JWT_SECRET": "change_this_secret_in_production",
    "ADMIN_PASS": "krashi2025",
}


def assert_secrets_configured() -> None:
    """
    Refuse to boot in production with repo-default secrets.

    The fallbacks in auth_utils/admin are published in a public repo: a default
    JWT_SECRET lets anyone forge a token for any user_id, and a default
    ADMIN_PASS opens the admin panel (which can swap models and spend API
    credit). Locally these defaults stay usable so `uvicorn` still just runs.
    """
    if not IS_PROD:
        return

    bad = []
    for name, insecure in _INSECURE_DEFAULTS.items():
        value = os.getenv(name, "").strip()
        if not value:
            bad.append(f"{name} is not set")
        elif value == insecure:
            bad.append(f"{name} is still the public repo default")

    secret = os.getenv("JWT_SECRET", "").strip()
    if secret and secret not in ("", _INSECURE_DEFAULTS["JWT_SECRET"]) and len(secret) < 32:
        bad.append("JWT_SECRET is shorter than 32 characters")

    if bad:
        raise RuntimeError(
            "Refusing to start — insecure production config:\n  - "
            + "\n  - ".join(bad)
            + "\n\nSet these in the Render dashboard (Environment → Add). Generate a"
            "\nJWT_SECRET with:  python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )


# ── Rate limiting ────────────────────────────────────────────
# In-process sliding window, keyed by client IP + bucket name. KrashiMitra runs
# as a single Render instance, so a shared store (Redis) would be cost with no
# benefit today. If the service is ever scaled to >1 instance these limits
# become per-instance — move the counters to Redis at that point.

_hits: dict = defaultdict(deque)
_hits_lock = threading.Lock()

# Bound the key space so a flood of spoofed X-Forwarded-For values can't grow
# the dict without limit (the old per-email login tracker had this bug).
_MAX_TRACKED_KEYS = 20_000


def client_ip(request: Request) -> str:
    """Real client IP. Render terminates TLS and forwards via X-Forwarded-For,
    so the left-most entry is the caller; fall back to the socket peer."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _prune(now: float) -> None:
    """Drop buckets whose newest hit is old. Called under _hits_lock."""
    stale = [k for k, dq in _hits.items() if not dq or now - dq[-1] > 3600]
    for k in stale:
        del _hits[k]


def check_rate_limit(key: str, limit: int, window: int) -> Optional[int]:
    """
    Record a hit for `key`. Returns None if allowed, else seconds to wait.
    Sliding window: at most `limit` hits in the trailing `window` seconds.
    """
    now = time.time()
    with _hits_lock:
        if len(_hits) > _MAX_TRACKED_KEYS:
            _prune(now)
            if len(_hits) > _MAX_TRACKED_KEYS:
                _hits.clear()  # under active abuse — reset rather than grow

        dq = _hits[key]
        while dq and now - dq[0] > window:
            dq.popleft()

        if len(dq) >= limit:
            return max(1, int(window - (now - dq[0])))

        dq.append(now)
        return None


def rate_limit(bucket: str, limit: int, window: int):
    """
    FastAPI dependency factory. Usage:

        @router.post("/ask", dependencies=[Depends(rate_limit("ask", 20, 60))])

    Raises 429 with Retry-After when the caller exceeds `limit` per `window`.
    """
    def _dep(request: Request):
        retry = check_rate_limit(f"{bucket}:{client_ip(request)}", limit, window)
        if retry is not None:
            raise HTTPException(
                status_code=429,
                detail="बहुत ज़्यादा requests। कृपया थोड़ी देर बाद दोबारा कोशिश करें।",
                headers={"Retry-After": str(retry)},
            )
    return _dep


# ── Security headers ─────────────────────────────────────────

# ── Upload content sniffing ──────────────────────────────────
# Uploads were accepted on the strength of their filename extension alone, so
# ".jpg" was taken at face value regardless of what the bytes actually were.
# Check the magic number and make sure the real format matches the extension
# the caller claimed.

def _is_image(head: bytes) -> bool:
    return (
        head.startswith(b"\xff\xd8\xff")                      # JPEG
        or head.startswith(b"\x89PNG\r\n\x1a\n")              # PNG
        or head.startswith(b"GIF87a") or head.startswith(b"GIF89a")
        or (head.startswith(b"RIFF") and head[8:12] == b"WEBP")
    )


def _is_video(head: bytes) -> bool:
    return (
        head[4:8] == b"ftyp"                                  # MP4 / MOV / M4V
        or head.startswith(b"\x1a\x45\xdf\xa3")               # WebM / Matroska
    )


def sniff_media_kind(head: bytes) -> Optional[str]:
    """Return 'image' | 'video' | None from a file's leading bytes."""
    if _is_image(head):
        return "image"
    if _is_video(head):
        return "video"
    return None


def assert_media_matches(head: bytes, expected: str) -> None:
    """Raise 400 unless the bytes really are the media kind we expect."""
    actual = sniff_media_kind(head)
    if actual != expected:
        raise HTTPException(
            400,
            "यह file असली photo/video नहीं लग रही। दूसरी file चुनें।",
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Baseline response headers.

    No Content-Security-Policy yet: the frontend leans on inline `onclick=`
    handlers and innerHTML templating throughout, so any policy strict enough
    to matter would need 'unsafe-inline' (which buys nothing) or a refactor of
    every page. frame-ancestors is enforced via X-Frame-Options instead, which
    covers the clickjacking case that actually applies to us.
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(self), microphone=(), camera=()"
        )
        if IS_PROD:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Tags each request with an id and logs one line when it completes.

    Replaces uvicorn.access (disabled in logging_config) so the access line
    carries the same request id as every application log emitted while
    handling it — which is what makes a traceback traceable back to the call
    that produced it. Honours an inbound X-Request-ID so a proxy-assigned id
    survives, and echoes it back on the response.
    """

    async def dispatch(self, request: Request, call_next):
        import time

        from backend.utils.logging_config import new_request_id, request_id_var

        rid = (request.headers.get("X-Request-ID") or "").strip()[:64] or new_request_id()
        token = request_id_var.set(rid)
        started = time.perf_counter()
        # Everything that logs must stay inside this try: resetting the context
        # var before emitting the access line would strip the id off the one
        # record whose whole job is to carry it.
        try:
            response = await call_next(request)

            elapsed_ms = (time.perf_counter() - started) * 1000
            # Static assets and the keep-alive ping are the bulk of traffic and
            # say nothing when they succeed; keep them at DEBUG so INFO reads.
            if response.status_code >= 500:
                level = logging.ERROR
            elif response.status_code >= 400:
                level = logging.WARNING
            elif request.url.path == "/health" or "." in request.url.path.rsplit("/", 1)[-1]:
                level = logging.DEBUG
            else:
                level = logging.INFO

            _access_log.log(
                level,
                "%s %s -> %d (%.0fms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            response.headers.setdefault("X-Request-ID", rid)
            return response
        except Exception:
            # The handler in main.py turns this into a 500 and logs the
            # traceback; here we only add the timing, then re-raise so that
            # handler still runs.
            _access_log.exception(
                "%s %s -> unhandled exception after %.0fms",
                request.method,
                request.url.path,
                (time.perf_counter() - started) * 1000,
            )
            raise
        finally:
            request_id_var.reset(token)
