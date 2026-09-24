# ============================================================
# backend/services/media_store.py
# KrashiMitra — where a farmer's photo actually lives
# ============================================================
# Every bazar photo ever uploaded was gone by 14 Sep 2026. All three listings
# that carried one returned 404: Render's disk is ephemeral, so `uploads/bazar/`
# is wiped on each redeploy while the DB keeps pointing at the missing file.
# A farmer photographs his crop, posts it, and the feed shows a black bar.
#
# Three homes were possible. This module is the third:
#
#   1. Postgres, the way avatars are stored (routes/profile.py). That works for
#      a 512px avatar thumbnail, but a crop photo is read on every feed render,
#      and every one of those reads burns Neon's metered compute — the tightest
#      ceiling this site has (100 CU-hrs/month).
#   2. A disk on Render. Render meters egress at 5 GB/month and suspended the
#      whole workspace over it on 17 Aug 2026. Serving media from the origin
#      puts photos on that same meter.
#   3. Cloudflare R2. Egress is free and never touches Render's meter at all;
#      the free tier is 10 GB of storage, 1M writes and 10M reads a month.
#
# NO boto3. R2 speaks the S3 API, and SigV4 is the ~40 lines below — while
# botocore would add ~50 MB resident to a 512 MB dyno on which the torch stack
# is already switched off to save exactly that. This matches how the rest of the
# repo treats vendors: Gemini and Ollama are plain HTTP too, no SDKs.
#
# CONFIG (all five required; missing any one disables R2 and the caller falls
# back to local disk, which is what keeps `uvicorn` working offline):
#
#   R2_ACCOUNT_ID          Cloudflare dashboard → R2 → Account ID
#   R2_ACCESS_KEY_ID       R2 → Manage API tokens → Object Read & Write
#   R2_SECRET_ACCESS_KEY   shown once, at token creation
#   R2_BUCKET              e.g. krashimitra-media
#   R2_PUBLIC_BASE         the bucket's public host, no trailing slash —
#                          https://media.krashimitra.in (custom domain) or the
#                          https://pub-<hash>.r2.dev address
#
#   R2_ENDPOINT            optional — overrides the S3 endpoint entirely, for
#                          another S3-compatible provider or a test double.
#
# One bucket setting is not optional: a CORS rule allowing GET from
# https://krashimitra.in. krashi_bajar.html draws a listing photo onto a
# <canvas> to build the WhatsApp share card, with img.crossOrigin='anonymous'.
# Without the rule the image simply fails to load and the card falls back to the
# crop placeholder — silent, not broken, but the photo is missing.
# ============================================================

import datetime as dt
import hashlib
import hmac
import io
import logging
import os
from typing import Optional, Tuple
from urllib.parse import quote

import requests
from PIL import Image, ImageOps

log = logging.getLogger(__name__)


# ── Stored-image shape ───────────────────────────────────────
# What comes off a phone is 3-8 MB of JPEG at 4000px. What a 390px feed card
# needs is a fraction of that, and the farmer looking at it is on rural data.
# Re-encoding on upload is the single biggest lever here: ~200 KB per photo
# means the 10 GB free tier holds ~50,000 of them instead of ~2,000.
MAX_EDGE     = 1600   # px on the long side — 2x a full-width phone card
WEBP_QUALITY = 82
# method=6 is Pillow's slowest/best WebP search. CPU, not storage, is what runs
# out first on a free dyno — the same reason GZipMiddleware runs at level 6 and
# not 9 — and method=4 is within a few percent of the size for a fraction of
# the time.
WEBP_METHOD  = 4
# A 50 MP decode is ~600 MB of RGB. Refuse before Pillow allocates it: the cap
# on upload bytes says nothing about pixel count, which is exactly what a
# decompression bomb exploits.
MAX_PIXELS   = 50_000_000

# Keys are UUIDs, so a given URL's bytes can never change.
CACHE_CONTROL = "public, max-age=31536000, immutable"

_ALGO      = "AWS4-HMAC-SHA256"
_REGION    = "auto"        # R2 accepts this and nothing else
_SERVICE   = "s3"
_EMPTY_SHA = hashlib.sha256(b"").hexdigest()


# ── Config ───────────────────────────────────────────────────

def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _conf() -> dict:
    """Read config on every call, never at import.

    Module-level constants would freeze whatever the environment looked like
    when the first `backend.*` import ran, which makes the setting untestable
    and makes boot order matter. It is five os.getenv calls.
    """
    return {
        "account":  _env("R2_ACCOUNT_ID"),
        "key":      _env("R2_ACCESS_KEY_ID"),
        "secret":   _env("R2_SECRET_ACCESS_KEY"),
        "bucket":   _env("R2_BUCKET"),
        "endpoint": _env("R2_ENDPOINT").rstrip("/"),
        "public":   _env("R2_PUBLIC_BASE").rstrip("/"),
    }


def enabled() -> bool:
    """True only when a complete set of credentials is present.

    Half-configured is treated as off. A bucket with no public base would
    upload bytes nobody can read back, and the listing would carry a URL that
    404s — the exact failure this module exists to end.
    """
    c = _conf()
    return bool(
        (c["endpoint"] or c["account"])
        and c["key"] and c["secret"] and c["bucket"] and c["public"]
    )


def _endpoint(c: dict) -> str:
    return c["endpoint"] or f'https://{c["account"]}.r2.cloudflarestorage.com'


def public_url(key: str) -> str:
    return f'{_conf()["public"]}/{key.lstrip("/")}'


def owns(url: Optional[str]) -> bool:
    """Is this URL one we put in R2? Decides whether a delete has anything to do."""
    base = _conf()["public"]
    return bool(url and base and url.startswith(base + "/"))


def key_for(url: str) -> str:
    return url[len(_conf()["public"]) + 1:]


# ── Image re-encoding ────────────────────────────────────────

def shrink_image(raw: bytes) -> Tuple[bytes, str, str]:
    """Re-encode an uploaded photo as a bounded WebP.

    Returns (bytes, content_type, extension). Raises ValueError if the bytes
    are not a decodable image or are implausibly large in pixels; the caller
    turns that into the Hindi 400 the farmer sees.

    An animated GIF collapses to its first frame. That is deliberate — the
    alternative is storing an animation nobody uploaded on purpose.
    """
    try:
        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        if w * h > MAX_PIXELS:
            raise ValueError(f"image is {w}x{h}, over the {MAX_PIXELS} pixel limit")
        # Phones record orientation in EXIF rather than rotating the pixels;
        # without this the crop photo lands on its side and stays that way.
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"could not decode image: {e}") from e
    return buf.getvalue(), "image/webp", ".webp"


# ── SigV4 ────────────────────────────────────────────────────

def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sign(method: str, key: str, body: bytes, headers: dict,
          query: Optional[dict] = None) -> Tuple[str, dict]:
    """Return (url, headers) for a signed path-style S3 request.

    `headers` in is the set to sign alongside host / x-amz-date /
    x-amz-content-sha256, lowercase keys. Authorization is added last, after
    SignedHeaders has been computed from the others — signing the signature
    would be circular.

    `query` is the request's parameters, used by the bucket-level operations
    (ListObjectsV2). SigV4 signs them, so they are built here once and returned
    glued onto the URL — a caller that appended its own `?…` afterwards would
    send a request whose signature covers a different URL than the one it asked
    for, and get a 403 that says nothing about why.
    """
    c   = _conf()
    ep  = _endpoint(c)
    now = dt.datetime.now(dt.timezone.utc)
    amz_date  = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    payload_sha = hashlib.sha256(body).hexdigest() if body else _EMPTY_SHA

    h = {k.lower(): v for k, v in (headers or {}).items() if v}
    h["host"] = ep.split("://", 1)[1]
    h["x-amz-content-sha256"] = payload_sha
    h["x-amz-date"] = amz_date

    signed_names = ";".join(sorted(h))
    canonical_headers = "".join(f"{k}:{h[k]}\n" for k in sorted(h))
    # An empty key addresses the bucket itself, and `/bucket/` is a different
    # resource from `/bucket` to a signature even where both route the same.
    obj = key.lstrip("/")
    canonical_uri = "/" + quote(f'{c["bucket"]}/{obj}' if obj else c["bucket"],
                                safe="/~")
    # Sorted by name, each part percent-encoded — the canonical form SigV4
    # specifies, which is not the same as whatever order a dict iterates in.
    canonical_query = "&".join(
        f"{quote(str(k), safe='~')}={quote(str(v), safe='~')}"
        for k, v in sorted((query or {}).items())
    )
    canonical_request = "\n".join([
        method, canonical_uri, canonical_query,
        canonical_headers, signed_names, payload_sha,
    ])

    scope = f"{datestamp}/{_REGION}/{_SERVICE}/aws4_request"
    to_sign = "\n".join([
        _ALGO, amz_date, scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])
    k = _hmac(("AWS4" + c["secret"]).encode("utf-8"), datestamp)
    k = _hmac(k, _REGION)
    k = _hmac(k, _SERVICE)
    k = _hmac(k, "aws4_request")
    signature = hmac.new(k, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    h["Authorization"] = (
        f'{_ALGO} Credential={c["key"]}/{scope}, '
        f"SignedHeaders={signed_names}, Signature={signature}"
    )
    return f"{ep}{canonical_uri}" + (f"?{canonical_query}" if canonical_query else ""), h


# ── Operations ───────────────────────────────────────────────
# Both are blocking. bazar.py calls put() through run_in_threadpool so a large
# upload does not stall the event loop for every other request on the instance;
# delete_post is a sync endpoint and already runs in FastAPI's threadpool.

def put(data: bytes, key: str, content_type: str) -> str:
    """Store bytes and return the public URL. Raises RuntimeError on failure."""
    if not enabled():
        raise RuntimeError("R2 is not configured")
    url, headers = _sign("PUT", key, data, {
        "content-type":  content_type,
        "cache-control": CACHE_CONTROL,
    })
    r = requests.put(url, data=data, headers=headers, timeout=60)
    if r.status_code >= 300:
        log.error("[media_store] PUT %s -> %s %s", key, r.status_code, r.text[:300])
        raise RuntimeError(f"R2 upload failed ({r.status_code})")
    log.info("[media_store] stored %s (%d bytes)", key, len(data))
    return public_url(key)


def delete(url: str) -> bool:
    """Best effort — a leftover object costs a fraction of a cent, and a failed
    delete must never stop a farmer from removing his own listing."""
    if not (enabled() and owns(url)):
        return False
    try:
        signed_url, headers = _sign("DELETE", key_for(url), b"", {})
        r = requests.delete(signed_url, headers=headers, timeout=20)
        return r.status_code < 300
    except Exception:
        log.warning("[media_store] delete failed for %s", url, exc_info=True)
        return False


# ── How full is the bucket ───────────────────────────────────
# R2's free tier is 10 GB of storage, and nothing on this site was watching it.
# The number could be read from Cloudflare's GraphQL analytics, but that needs a
# second credential (an account API token) which is not the same thing as the S3
# key pair above — so this counts the bucket with the credentials that are
# already set, and the panel has a real storage meter the day R2 is switched on
# rather than the day somebody remembers to mint another token.
#
# This costs ONE Class A operation per page of 1000 keys, against a free
# allowance of 1,000,000 a month, and infra_service memoises the whole panel for
# five minutes. At ~200 KB a photo the 10 GB tier is ~50,000 objects, i.e. 50
# pages — which is why LIST_MAX_PAGES exists: a bucket that outgrows the count
# reports what it counted and says so, instead of spending a minute and a
# thousand operations to be exact about a number that is already alarming.

LIST_MAX_PAGES = 60


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def usage(prefix: str = "") -> dict:
    """Count the objects in the bucket.

    Returns {ok, objects, bytes, truncated, error}. Never raises: this is called
    by the admin infra panel, and a storage probe that can 500 is a probe that
    takes down the page that exists to tell you what is broken.

    `truncated` True means the walk stopped at LIST_MAX_PAGES and the figures
    are a floor, not a total. The caller must say so rather than print them as
    if they were the whole bucket.
    """
    out = {"ok": False, "objects": 0, "bytes": 0, "truncated": False, "error": ""}
    if not enabled():
        out["error"] = "R2 is not configured"
        return out

    import xml.etree.ElementTree as ET

    token = None
    try:
        for _ in range(LIST_MAX_PAGES):
            q = {"list-type": "2", "max-keys": "1000"}
            if prefix:
                q["prefix"] = prefix
            if token:
                q["continuation-token"] = token
            url, headers = _sign("GET", "", b"", {}, q)
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code >= 300:
                out["error"] = f"HTTP {r.status_code}: {r.text[:160]}"
                return out
            root = ET.fromstring(r.content)
            for node in root:
                if _strip_ns(node.tag) != "Contents":
                    continue
                out["objects"] += 1
                for field in node:
                    if _strip_ns(field.tag) == "Size":
                        out["bytes"] += int(field.text or 0)
            token = next((c.text for c in root
                          if _strip_ns(c.tag) == "NextContinuationToken"), None)
            if not token:
                break
        else:
            out["truncated"] = True
        out["ok"] = True
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    return out
