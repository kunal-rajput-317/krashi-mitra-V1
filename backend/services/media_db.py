# ============================================================
# backend/services/media_db.py
# KrashiMitra — where a farmer's photo lives until R2 is affordable
# ============================================================
# media_store.py (Cloudflare R2) is the intended home and its code is finished.
# R2 will not activate without a payment method on file, which the owner does
# not have, so it is deferred. The consequence was not "photos don't persist" —
# `_save_media()` in routes/bazar.py deliberately answers **503** in production
# when R2 is off, rather than write to a disk Render wipes on every redeploy.
# So from 14 Sep 2026 a farmer could not attach a photo at all.
#
# This module is the stopgap, and it is deliberately the *smallest* thing that
# unblocks that: the bytes go in Postgres, exactly as avatars already do in
# routes/profile.py. It mirrors media_store's interface (enabled / put /
# public_url / owns / key_for / delete) so bazar.py picks a backend and calls
# the same four functions either way, and so the day R2 turns on is a config
# change rather than a rewrite.
#
# THE TWO RULES THAT KEEP THIS SAFE
#
# 1. Images only. Videos are refused. A video is up to 40 MB against a 0.5 GB
#    database, and in the 2.5 months the feature has existed **not one video
#    has ever been uploaded** — so this costs nothing real and removes the only
#    way a single upload could threaten the whole site.
#
# 2. A hard byte cap. Neon's free tier is 0.5 GB for the ENTIRE database and
#    ~0.36 GB was already in use. Filling it does not degrade the bazar — it
#    flips the whole compute read-only (SQLSTATE 25006) and every write on
#    every feature starts failing. MAX_TOTAL_BYTES is what stands between a
#    photo upload and a site-wide outage, so it is checked before every write.
#
# Reads are the other half. Postgres was rejected for media once because a
# crop photo is read on every feed render and Neon's compute is the tightest
# ceiling here. That is why routes/bazar.py serves /bazar/media/{key} with an
# immutable Cache-Control: the key is a uuid and its bytes never change, so
# Cloudflare can hold it at the edge effectively forever and Postgres sees
# roughly one read per photo per cache period instead of one per render.

import logging
import os
from typing import Optional, Tuple

from backend.database.db import BazarMedia, SessionLocal

log = logging.getLogger(__name__)

# The public origin. Not the Render host: this URL is stored in a row and read
# back long after the origin may have been renamed — which has happened twice.
SITE = os.getenv("PUBLIC_SITE_URL", "https://krashimitra.in").rstrip("/")

# Must match the route in routes/bazar.py (router prefix "/bazar").
PREFIX = "/bazar/media/"

# ~60 MB. Room for roughly 300 photos at the ~200 KB shrink_image() produces,
# while leaving Neon's 0.5 GB with headroom for the 22 tables that matter more.
# Raise it only after checking actual database size, never by guessing.
MAX_TOTAL_BYTES = 60 * 1024 * 1024


def enabled() -> bool:
    """Always available — if the app is up, it has a database."""
    return True


def public_url(key: str) -> str:
    return f"{SITE}{PREFIX}{key.lstrip('/')}"


def owns(url: Optional[str]) -> bool:
    """Is this URL served by this module? Decides whether a delete has work.

    Matches on the PATH, not the full URL: rows written while the site answered
    on a different host must still be recognised as ours, or deleting a listing
    would silently orphan its bytes in the table forever.
    """
    return bool(url and PREFIX in url)


def key_for(url: str) -> str:
    return url.split(PREFIX, 1)[1]


def total_bytes() -> int:
    from sqlalchemy import func
    db = SessionLocal()
    try:
        return int(db.query(func.coalesce(func.sum(BazarMedia.bytes), 0)).scalar() or 0)
    finally:
        db.close()


def put(data: bytes, key: str, content_type: str) -> str:
    """Store bytes and return the public URL. Raises RuntimeError on failure."""
    if not content_type.startswith("image/"):
        # See rule 1 above. The caller turns this into a farmer-readable message.
        raise RuntimeError("only images can be stored in the database")

    used = total_bytes()
    if used + len(data) > MAX_TOTAL_BYTES:
        log.error("[media_db] cap reached: %d + %d > %d — refusing upload",
                  used, len(data), MAX_TOTAL_BYTES)
        raise RuntimeError("media storage is full")

    db = SessionLocal()
    try:
        db.merge(BazarMedia(key=key, content_type=content_type,
                            data=data, bytes=len(data)))
        db.commit()
    except Exception:
        db.rollback()
        log.exception("[media_db] failed to store %s", key)
        raise RuntimeError("could not store media")
    finally:
        db.close()

    log.info("[media_db] stored %s (%d bytes, %.1f MB of %.0f MB used)",
             key, len(data), (used + len(data)) / 1048576, MAX_TOTAL_BYTES / 1048576)
    return public_url(key)


def get(key: str) -> Optional[Tuple[bytes, str]]:
    """(bytes, content_type) for the handler, or None when the key is unknown."""
    db = SessionLocal()
    try:
        row = db.get(BazarMedia, key)
        return (row.data, row.content_type) if row else None
    finally:
        db.close()


def delete(url: str) -> bool:
    """Best effort — a failed delete must never stop a farmer removing his own
    listing. An orphaned row costs bytes against the cap, not correctness."""
    if not owns(url):
        return False
    db = SessionLocal()
    try:
        row = db.get(BazarMedia, key_for(url))
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True
    except Exception:
        db.rollback()
        log.warning("[media_db] delete failed for %s", url, exc_info=True)
        return False
    finally:
        db.close()
