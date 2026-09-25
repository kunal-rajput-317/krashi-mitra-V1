# ============================================================
# backend/utils/conditional_get.py
# KrashiMitra — "not modified" answers for server-rendered pages
#
# Render bills every byte this process sends against a 5 GB/month cap. When
# Cloudflare's copy of a page expires (1 h for /bhav, 3 h for the rest) it asks
# this origin again, and until 26 Sep 2026 the answer was always the whole page,
# ~20-50 KB gzipped, even when not one character had changed. About half of
# /bhav's ~34k pages report from mandis that no longer send prices, so most of
# those refreshes were the same page, over and over.
#
# An ETag fixes that. It is a hash of the rendered body, so a revalidation that
# carries it back (If-None-Match) gets a ~0.3 KB 304 when the page is the same,
# and the full page the moment any byte differs. Googlebot and Bingbot send
# If-None-Match too; Cloudflare answers those itself from cache.
#
# Why a hash of the body and NOT the Last-Modified the /bhav pages already send:
# that header is the price's REPORT DATE, at day resolution. The 10:00 and
# 13:00 fetches add mandis to a page without changing its date, so answering
# If-Modified-Since from it would pin the morning's prices at the edge all day.
# If-Modified-Since alone is therefore ignored (RFC 9110 lets a server do that),
# and every request without If-None-Match gets the full page as before.
#
# Scope: GET/HEAD, 200, text/html, publicly cacheable, no Set-Cookie. JSON APIs,
# personal pages and anything already carrying an ETag pass straight through.
# The page is still rendered — this saves bandwidth, not CPU.
#
# Must sit INSIDE GZipMiddleware (added before it in main.py): the hash is of
# the uncompressed body, so it does not depend on which encoding was asked for.
# The tag is weak (W/) for the same reason — the gzip and identity bodies differ
# byte-for-byte but are the same page.
# ============================================================

import hashlib

# Response headers a 304 must repeat (RFC 9110 §15.4.5) plus the two the edge
# reads to decide how long the refreshed copy may be kept.
_KEEP_ON_304 = {b"etag", b"cache-control", b"cdn-cache-control", b"expires",
                b"last-modified", b"vary", b"content-location", b"date"}

# A body this large is not one of our pages; stop buffering and pass it on.
_MAX_BUFFER = 2 * 1024 * 1024


def etag_for(body: bytes) -> str:
    return 'W/"' + hashlib.blake2b(body, digest_size=12).hexdigest() + '"'


def _matches(if_none_match: str, etag: str) -> bool:
    """Weak comparison, which is what If-None-Match uses: the W/ prefix is
    ignored on both sides. Cloudflare re-weakens tags when it re-encodes a
    body, so a revalidation may send the tag with or without it."""
    if if_none_match.strip() == "*":
        return True
    want = etag[2:] if etag.startswith("W/") else etag
    for tag in if_none_match.split(","):
        tag = tag.strip()
        if tag.startswith("W/"):
            tag = tag[2:]
        if tag == want:
            return True
    return False


def _cacheable_html(status: int, headers: list) -> bool:
    if status != 200:
        return False
    ctype = cc = b""
    for k, v in headers:
        k = k.lower()
        if k == b"content-type":
            ctype = v.lower()
        elif k == b"cache-control":
            cc = v.lower()
        elif k in (b"etag", b"set-cookie", b"content-encoding"):
            return False
    if not ctype.startswith(b"text/html"):
        return False
    return not any(d in cc for d in (b"no-store", b"private"))


class ConditionalGetMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("GET", "HEAD"):
            await self.app(scope, receive, send)
            return

        inm = ""
        for k, v in scope.get("headers") or []:
            if k == b"if-none-match":
                inm = v.decode("latin-1")
                break

        start = None
        chunks: list[bytes] = []
        size = 0
        passthrough = False

        async def _send(message):
            nonlocal start, size, passthrough
            if passthrough:
                await send(message)
                return

            if message["type"] == "http.response.start":
                if not _cacheable_html(message["status"], message.get("headers") or []):
                    passthrough = True
                    await send(message)
                    return
                start = message
                return

            if message["type"] != "http.response.body" or start is None:
                await send(message)
                return

            body = message.get("body", b"")
            chunks.append(body)
            size += len(body)
            if message.get("more_body", False):
                if size > _MAX_BUFFER:          # a stream, not a page: give up
                    passthrough = True
                    await send(start)
                    await send({"type": "http.response.body",
                                "body": b"".join(chunks), "more_body": True})
                return

            full = b"".join(chunks)
            etag = etag_for(full)
            headers = list(start.get("headers") or []) + [(b"etag", etag.encode())]

            if inm and _matches(inm, etag):
                kept = [(k, v) for k, v in headers if k.lower() in _KEEP_ON_304]
                await send({"type": "http.response.start", "status": 304,
                            "headers": kept})
                await send({"type": "http.response.body", "body": b""})
                return

            await send({**start, "headers": headers})
            await send({"type": "http.response.body", "body": full})

        await self.app(scope, receive, _send)
