# ============================================================
# backend/utils/edge_guard.py
# KrashiMitra — origin lock + per-IP flood guard
# ============================================================
#
# Cloudflare absorbs big floods, but two kinds of attack still reached Render:
#
#   1. Requests straight to the .onrender.com address, which skip Cloudflare
#      entirely (Render cannot firewall it, and old addresses are printed in
#      config/backend-origin.txt in this public repo).
#   2. Requests with a random query string (/bhav?x=123), which Cloudflare
#      treats as a new URL and never serves from cache. One laptop could keep
#      the free instance busy and burn the Render / Neon monthly quotas, which
#      suspend the site.
#
# ORIGIN LOCK (off until ORIGIN_SHIELD_SECRET is set):
#   A Cloudflare Transform Rule adds the header X-Origin-Shield: <secret> to
#   every request it forwards. With the env var set, any request without the
#   matching header gets a 403, so only traffic that came through Cloudflare
#   (cache, WAF, rate limit, DDoS protection) is served.
#   ORDER MATTERS: add the Transform Rule FIRST, check it, THEN set the env var
#   on Render. The other way round, every visitor gets a 403 until the rule
#   exists. /health stays open so Render's own health check (which hits the
#   instance directly, without Cloudflare) keeps passing.
#
# FLOOD GUARD (on by default, FLOOD_GUARD_PER_MIN=0 turns it off):
#   At most FLOOD_GUARD_PER_MIN requests per client IP per minute reach the
#   app. 300/min = 5 per second, sustained for a minute — no farmer or
#   Googlebot comes near it (the whole site averages about 1 request/second at
#   the origin), while a script hammering one URL is cut off within a second.
#   The IP is Cloudflare's CF-Connecting-IP (see security.client_ip). IPv6 is
#   counted per /64, because one connection hands out a whole /64. Requests
#   whose IP is private/unknown (local dev, tests) are never counted.
#
# Pure ASGI rather than BaseHTTPMiddleware: under a flood this runs on every
# request, and a rejected request should cost as close to nothing as possible.

import hmac
import ipaddress
import logging
import os
import time
from typing import Optional

from starlette.datastructures import Headers

from backend.utils.security import ip_from_headers

log = logging.getLogger(__name__)

SHIELD_HEADER = "x-origin-shield"
DEFAULT_PER_MINUTE = 300

# Paths every request is allowed through on. /health: Render's health check
# hits the instance directly, never via Cloudflare, and it touches no DB.
_OPEN_PATHS = {"/health"}

# Static assets: a first visit through a cold Cloudflare PoP fetches a page's
# whole set of CSS/JS/images from the origin at once. They are cheap files
# with immutable cache headers, so they do not count toward the flood limit.
_ASSET_EXT = {
    "css", "js", "mjs", "map", "png", "jpg", "jpeg", "webp", "gif", "svg",
    "ico", "avif", "woff", "woff2", "ttf",
}

# Bound the counter map. Past this many distinct IPs in one minute, reset it
# (fail open) rather than let a botnet grow memory on a 512 MB instance.
_MAX_KEYS = 50_000


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _is_asset(path: str) -> bool:
    last = path.rsplit("/", 1)[-1]
    return "." in last and last.rsplit(".", 1)[-1].lower() in _ASSET_EXT


def bucket_key(ip: str) -> Optional[str]:
    """The flood-guard counter key for an IP, or None to not count it."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None                       # "testclient", "unknown", junk
    if not addr.is_global:
        return None                       # localhost, LAN, Render internals
    if addr.version == 6:
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


class EdgeGuardMiddleware:
    def __init__(self, app, secret: Optional[str] = None,
                 per_minute: Optional[int] = None):
        self.app = app
        if secret is None:
            secret = os.getenv("ORIGIN_SHIELD_SECRET", "")
        self.secret = secret.strip().encode()
        self.per_minute = (_int_env("FLOOD_GUARD_PER_MIN", DEFAULT_PER_MINUTE)
                           if per_minute is None else per_minute)
        self._window = 0
        self._counts: dict = {}
        if self.secret:
            log.info("Origin lock ON: requests without %s are refused", SHIELD_HEADER)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") in _OPEN_PATHS:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)

        if self.secret:
            got = headers.get(SHIELD_HEADER, "").strip().encode()
            if not hmac.compare_digest(got, self.secret):
                await _reply(send, 403, b"Forbidden")
                return

        if self.per_minute > 0 and not _is_asset(scope.get("path", "")):
            peer = scope.get("client")
            key = bucket_key(ip_from_headers(headers, peer[0] if peer else ""))
            if key is not None:
                retry = self._hit(key)
                if retry is not None:
                    await _reply(
                        send, 429,
                        "बहुत ज़्यादा requests। थोड़ी देर बाद कोशिश करें।".encode(),
                        retry_after=retry,
                    )
                    return

        await self.app(scope, receive, send)

    def _hit(self, key: str) -> Optional[int]:
        """Count one request. Returns seconds to wait if over the limit.

        Fixed one-minute windows. Runs on the event loop with no await inside,
        so no lock is needed.
        """
        now = time.time()
        window = int(now // 60)
        if window != self._window or len(self._counts) > _MAX_KEYS:
            self._window = window
            self._counts = {}
        n = self._counts.get(key, 0) + 1
        self._counts[key] = n
        if n > self.per_minute:
            if n == self.per_minute + 1:
                log.warning("Flood guard: %s passed %d requests/min", key, self.per_minute)
            return max(1, 60 - int(now % 60))
        return None


async def _reply(send, status: int, body: bytes, retry_after: Optional[int] = None):
    headers = [
        (b"content-type", b"text/plain; charset=utf-8"),
        (b"content-length", str(len(body)).encode()),
        # Never let Cloudflare cache a refusal and hand it to real visitors.
        (b"cache-control", b"no-store"),
    ]
    if retry_after is not None:
        headers.append((b"retry-after", str(retry_after).encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
