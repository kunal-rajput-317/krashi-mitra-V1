# ============================================================
# backend/routes/bazar.py
# KrashiMitra — Krashi Bazar (social crop marketplace)
# ============================================================
# A Facebook-style feed where farmers post sell/buy listings
# with photos or videos.
#
# RULES:
#   • Guests can READ the feed, comments and public profiles.
#   • Posting, liking, commenting, offering and following need
#     a logged-in user WITH a farmer profile (user_profiles row).
#   • The blue "verified seller" tick = users.seller_verified,
#     toggled manually by the admin directly in the DB.
#
# ENDPOINTS:
#   GET    /bazar/feed                     public (auth optional)
#   GET    /bazar/me                       auth — gate info for frontend
#   POST   /bazar/posts                    auth+profile — multipart, media optional
#   DELETE /bazar/posts/{id}               owner
#   PATCH  /bazar/posts/{id}/status        owner — active|sold|closed
#   POST   /bazar/posts/{id}/like          auth+profile — toggle
#   GET    /bazar/posts/{id}/comments      public — parents with nested replies
#   POST   /bazar/posts/{id}/comments      auth+profile — comment, reply or ₹ offer
#   DELETE /bazar/posts/{id}/comments/{cid}  comment author OR post owner
#   POST   /bazar/comments/{id}/like       auth+profile — toggle
#   GET    /bazar/users/{id}               public profile card (auth optional)
#   POST   /bazar/users/{id}/follow        auth+profile — toggle
# ============================================================

import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Response
)
from pydantic import BaseModel
from sqlalchemy import func, or_, desc
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.database.db import (
    Buyer, User, UserProfile, BazarPost, BazarLike, BazarComment, BazarCommentLike,
    BazarFollow, get_db, acct, accts
)
from backend.routes.share import _FALLBACK_IMAGE, _HI_CROP_EN, _crop_image
from backend.services import media_db, media_store
from backend.utils.auth_utils import get_current_user, resolve_token_user
from backend.utils.security import IS_PROD, assert_media_matches
import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/bazar", tags=["bazar"])

# ── Media storage ────────────────────────────────────────────
# Bytes go to Cloudflare R2 (backend/services/media_store.py). This directory
# is the fallback for a developer running uvicorn with no R2 credentials — on
# Render it is wiped on every redeploy, which is why every listing photo posted
# before 14 Sep 2026 is a 404 today.
BAZAR_UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads" / "bazar"
BAZAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MEDIA_PREFIX = "bazar/"   # key prefix inside the R2 bucket

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v"}
# R2 serves back whatever Content-Type we store the object with, and a <video>
# tag will not play a file the browser is told is the wrong kind. Photos have no
# such table: they are all re-encoded to image/webp on the way in.
VIDEO_CONTENT_TYPES = {
    ".mp4":  "video/mp4",
    ".m4v":  "video/x-m4v",
    ".webm": "video/webm",
    ".mov":  "video/quicktime",
}
# The old caps were 50 MB / 120 MB, set when the only cost of a big file was a
# disk that threw it away anyway. Now the bytes are kept, and both numbers are
# about what the *farmer* can afford: 98% of this audience is on a phone on
# rural data, on both ends of the transfer.
#
# A photo is re-encoded to ~200 KB on arrival (media_store.shrink_image), so
# this cap only has to be wider than a phone camera's output, not than what we
# store. Video is stored as it arrives — no ffmpeg on this dyno — so 40 MB is
# roughly 30-40 seconds of 720p, and it is the real limit, not the 5-minute
# duration guard in krashi_bajar.html, which the server cannot check without
# ffprobe. Keep the two in the same neighbourhood or the client promises an
# upload the server refuses.
MAX_IMAGE_BYTES = 12 * 1024 * 1024   # 12 MB — a phone JPEG is 3-8 MB
MAX_VIDEO_BYTES = 40 * 1024 * 1024   # 40 MB — ~30-40s of phone video


# ── Rate limits ──────────────────────────────────────────────

# Every one of these actions costs something real on a free tier: a post can
# carry a 50 MB photo, an edit is a Neon write plus a re-render of a page whose
# bandwidth already suspended this site once (17 Aug 2026). They are also a
# quality floor — a listing whose price moves five times a day is not a price a
# buyer can act on, and a seller who renames himself weekly cannot be recognised
# by the buyer who spoke to him yesterday.
#
# Rolling windows, not calendar days: a calendar reset lets the limit be doubled
# by acting at 23:59 and again at 00:01.
MAX_POSTS_PER_DAY      = 10   # new listings per account per 24h
MAX_EDITS_PER_POST_DAY = 3    # edits to ONE listing per 24h
# The third limit of this set — how often the display name may change — belongs
# to the same policy but is enforced where the name is written: see
# NAME_CHANGE_COOLDOWN_DAYS in backend/routes/profile.py. Declaring it in both
# files would mean two numbers to keep equal and one day they would not be.


# ── Auth helpers ─────────────────────────────────────────────

def get_optional_user(request: Request, db: Session) -> Optional[dict]:
    """Like get_current_user but returns None instead of 401 for guests.

    Same validation as the strict dependency (live, verified, non-recycled
    account) — only the failure mode differs: guest instead of 401.

    `db` is a required positional argument, NOT `= Depends(get_db)`. This is
    called by hand from inside endpoints, not resolved by FastAPI, so a
    Depends() default would arrive as the sentinel object itself and blow up on
    `db.query()` — a 500 on the feed for every logged-in viewer, while guests
    saw nothing wrong. Pass the endpoint's own session.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    user = resolve_token_user(db, auth[7:].strip())
    return {"user_id": user.id, "email": user.email} if user else None


def require_profile(user_id: int, db: Session) -> UserProfile:
    """Selling/buying interactions need a completed farmer profile."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == acct(user_id)).first()
    if not profile:
        raise HTTPException(
            status_code=403,
            detail="PROFILE_REQUIRED",  # frontend shows 'पहले प्रोफ़ाइल बनाएं'
        )
    return profile


def _has_phone(profile: Optional[UserProfile]) -> bool:
    return bool(profile and profile.phone_number and profile.phone_number.strip())


def require_phone(profile: UserProfile):
    """Selling a crop or sending an offer needs a contact number — buyers and
    sellers must be reachable. Frontend redirects to the profile phone field."""
    if not _has_phone(profile):
        raise HTTPException(
            status_code=403,
            detail="PHONE_REQUIRED",
        )


# ── Serialization helpers ────────────────────────────────────

def _author_info(user: Optional[User], profile: Optional[UserProfile]) -> dict:
    name     = (profile.name if profile and profile.name else (user.name if user else "किसान"))
    village  = (profile.village  if profile else None) or (user.village  if user else None)
    district = (profile.district if profile else None) or (user.district if user else None)
    location = ", ".join([p for p in [village, district] if p])
    avatar_url = profile.avatar_url if profile else None
    return {
        "user_id":  user.id if user else None,
        "name":     name,
        "avatar_url": avatar_url,
        "verified": bool(user.seller_verified) if user else False,
        "location": location,
    }


def _norm_place(s: Optional[str]) -> str:
    """Case/space-insensitive key for state & district matching. The /bhav tree
    and a farmer's profile spell the same district differently often enough
    ("Hardoi" / "hardoi " / "HARDOI") that an exact column compare would silently
    drop rows from the district page."""
    return " ".join((s or "").split()).lower()


def place_posts(db: Session, post_type: str, crop_slug: str,
                state: str, district: str, limit: int = 20) -> list:
    """Active posts of one kind for one crop in one district, newest first.

    The shared query behind BOTH the /bhav district page and the खरीदें panel,
    so the two can never disagree about what "this district's listings" means.
    Matches on the structured columns only — a row posted before those existed
    (state/district NULL) is invisible here by design rather than guessed at.
    """
    if not (crop_slug and district):
        return []
    q = (db.query(BazarPost)
           .filter(BazarPost.status == "active",
                   BazarPost.post_type == post_type,
                   func.lower(BazarPost.crop_slug) == _norm_place(crop_slug),
                   func.lower(BazarPost.district) == _norm_place(district)))
    if state:
        q = q.filter(func.lower(BazarPost.state) == _norm_place(state))
    return q.order_by(desc(BazarPost.created_at)).limit(max(1, min(limit, 50))).all()


def place_keys(db: Session, post_type: str = "buy") -> set:
    """{(crop_slug, state, district)} — all lowercased — that currently have at
    least one active post of this kind.

    ONE query for the whole set, because the callers ask ~14,000 times: the /bhav
    sitemap walks every crop×state×district, and every district page needs to
    know whether to show the खरीदार link. Asking per district would be 14k round
    trips; asking once and caching the answer is the same information.
    """
    rows = (db.query(BazarPost.crop_slug, BazarPost.state, BazarPost.district)
              .filter(BazarPost.status == "active",
                      BazarPost.post_type == post_type,
                      BazarPost.crop_slug.isnot(None),
                      BazarPost.district.isnot(None))
              .distinct().all())
    return {(_norm_place(c), _norm_place(s), _norm_place(d)) for c, s, d in rows}


def _shop_names(posts, db: Session) -> dict:
    """{user_id: shop name} for the /dukanlisting accounts among these posts.

    A dealer's feed post is written by services/dealers.py::_sync_bazar_post
    under his personal login, because that is the only users.id there is to
    author it as. Signed with his profile name it read as a private person
    advertising a business — "kunal rajput" over a व्यापारी card — which is
    both confusing and worse for him than the name he actually pays to
    advertise.
    """
    ids = {p.users_id for p in posts if (p.source or "") == "dukan" and p.users_id}
    if not ids:
        return {}
    rows = (db.query(Buyer)
              .filter(Buyer.owner_user_id.in_(ids))
              .order_by(Buyer.id).all())
    names = {}
    for r in rows:
        # First row wins, matching _sync_bazar_post's own `live[0]` choice, so
        # the card and the post text can never name two different firms.
        if r.name and r.owner_user_id not in names:
            names[r.owner_user_id] = r.name
    return names


def _signed_as(p: BazarPost, author: dict, shop_names: dict) -> dict:
    """The author as this POST should be signed — the shop for a dealer's own
    listing, the person everywhere else.

    Only the displayed name changes. user_id still points at the real account,
    so Follow follows the person and tapping through opens the real profile
    under the real name; nothing here hides who is behind the listing.
    """
    name = shop_names.get(p.users_id) if (p.source or "") == "dukan" else None
    return {**author, "name": name, "is_shop": True} if name else author


# Romanized Hindi crop names → the English keyword _crop_image() matches on.
#
# The crop field is free text and farmers type what is on their phone keyboard:
# the live feed holds "Green matar", "Mera kela teyyari hai" and "Ready for
# Sell". _HI_CROP_EN only covers Devanagari, so every one of those fell through
# to no photo. Matched per word, not on the whole string, because the crop is
# rarely alone in the field.
_ROMAN_CROP_EN = {
    "gehu": "wheat", "gehun": "wheat", "gahu": "wheat", "genhu": "wheat",
    "dhan": "paddy", "chawal": "rice", "basmati": "rice",
    "matar": "peas", "mattar": "peas", "aloo": "potato", "alu": "potato",
    "pyaz": "onion", "pyaaz": "onion", "kanda": "onion",
    "tamatar": "tomato", "makka": "maize", "makai": "maize",
    "sarson": "mustard", "chana": "chana", "ganna": "sugarcane",
    "lahsun": "garlic", "lehsun": "garlic", "mirch": "chilli", "mirchi": "chilli",
    "haldi": "turmeric", "moongfali": "groundnut", "mungfali": "groundnut",
    "arhar": "arhar", "tur": "arhar", "urad": "urad", "moong": "moong",
    "kapas": "cotton", "masur": "masur", "baingan": "brinjal",
    "adrak": "ginger", "bhindi": "bhindi", "kela": "banana", "aam": "mango",
    "seb": "apple", "soyabean": "soybean", "soybean": "soybean",
    "jau": "barley", "bajra": "bajra", "jowar": "jowar", "til": "sesamum",
    "gobhi": "cauliflower", "gobi": "cauliflower", "gajar": "carrot",
    "lauki": "bottle gourd", "kaddu": "pumpkin", "nimbu": "lemon",
    "anar": "pomegranate", "angoor": "grapes", "papita": "papaya",
    "amrud": "guava", "santra": "orange", "tarbuj": "watermelon",
    "palak": "spinach", "methi": "fenugreek", "dhaniya": "coriander",
    "mooli": "raddish", "shimla": "capsicum", "sahjan": "drumstick",
}


def _crop_photo(crop: Optional[str]) -> str:
    """A stock photo of the crop, for a listing whose owner uploaded none.

    Most listings carry no photo, and a feed of grey text boxes is the main
    reason the page looked unfinished on a phone. These are the same
    licence-checked, self-hosted crop photos /bhav and the share cards use —
    resolved server-side so there is one crop→photo table, not a second copy in
    JavaScript, and returned as a krashimitra.in URL so Netlify serves it and it
    never touches Render's metered egress.
    """
    if not crop:
        return ""
    name = crop.strip()
    # _crop_image never returns nothing — an unmatched crop gets the site's OG
    # banner, which is right for a link preview and wrong here. A card showing
    # the KrashiMitra logo where the crop should be is worse than a card showing
    # an emoji tile, so an unmatched crop comes back empty and the page decides.
    url = _crop_image(_HI_CROP_EN.get(name, name))
    if url and url != _FALLBACK_IMAGE:
        return url
    for token in re.findall(r"[a-z]+", name.lower()):
        en = _ROMAN_CROP_EN.get(token)
        if not en:
            continue
        url = _crop_image(en)
        if url and url != _FALLBACK_IMAGE:
            return url
    return ""


def _post_to_dict(p: BazarPost, author: dict, liked: bool, is_mine: bool,
                  shop_names: Optional[dict] = None) -> dict:
    author = _signed_as(p, author, shop_names or {})
    return {
        "id":             p.id,
        "post_type":      p.post_type,
        "crop":           p.crop,
        "text":           p.text,
        "media_url":      p.media_url,
        "media_type":     p.media_type,
        "crop_image":     _crop_photo(p.crop),
        "price":          p.price,
        "old_price":      p.old_price,
        "quantity":       p.quantity,
        "unit":           p.unit,
        "location":       p.location or author.get("location") or "",
        "crop_slug":      p.crop_slug,
        "state":          p.state,
        "district":       p.district,
        "status":         p.status,
        "likes_count":    p.likes_count or 0,
        "comments_count": p.comments_count or 0,
        "created_at":     p.created_at.isoformat() if p.created_at else None,
        "updated_at":     p.updated_at.isoformat() if p.updated_at else None,
        "author":         author,
        "liked_by_me":    liked,
        "is_mine":        is_mine,
    }


def _authors_for(posts, db: Session) -> dict:
    """Batch-load author info for a list of posts → {user_id: author_dict}."""
    ids = {p.users_id for p in posts}
    if not ids:
        return {}
    users    = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}
    # user_profiles is keyed on the account number (users.user_id), not on
    # users.id like every other table here — so it comes back keyed the wrong
    # way and has to be re-keyed through `users` before callers can index it by
    # post author id. See UserProfile.user_id in backend/database/db.py.
    by_acct  = {pr.user_id: pr for pr in
                db.query(UserProfile).filter(UserProfile.user_id.in_(accts(ids))).all()}
    profiles = {uid: by_acct.get(u.user_id) for uid, u in users.items()}
    return {uid: _author_info(users.get(uid), profiles.get(uid)) for uid in ids}


# ── GET /bazar/me — frontend gate info ───────────────────────

@router.get("/me")
def bazar_me(
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    user_id = current_user["user_id"]
    user    = db.query(User).filter(User.id == user_id).first()
    profile = db.query(UserProfile).filter(UserProfile.user_id == acct(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {
        "success": True,
        "message": "",
        "data": {
            "user_id":     user.id,
            "name":        (profile.name if profile and profile.name else user.name),
            "has_profile": profile is not None,
            "has_phone":   _has_phone(profile),
            "avatar_url":  profile.avatar_url if profile else None,
            "verified":    bool(user.seller_verified),
        },
    }


# ── GET /bazar/feed ──────────────────────────────────────────

@router.get("/media/{key}")
def get_media(key: str):
    """Serve a listing photo out of bazar_media.

    The whole viability of storing media in Postgres rests on this handler's
    headers. The key is a uuid and its bytes never change, so the response is
    immutable and Cloudflare may hold it at the edge indefinitely — which turns
    "a photo is read on every feed render", the original objection to Postgres,
    into roughly one read per photo per cache period. Without these headers
    this route would bill Neon's metered compute for every scroll.

    404s (rather than erroring) on an unknown key: the feed card already carries
    an onerror that drops the media block, so a missing photo costs a farmer a
    picture, not a broken listing.
    """
    row = media_db.get(key)
    if not row:
        raise HTTPException(404, "Media नहीं मिला।")
    data, content_type = row
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "CDN-Cache-Control": "public, max-age=31536000, immutable",
            # Same rule the R2 bucket needs: krashi_bajar.html draws this image
            # onto a <canvas> with crossOrigin='anonymous' to build the WhatsApp
            # share card, and without it the photo silently drops out.
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/feed")
def get_feed(
    post_type: Optional[str] = None,     # "sell" | "buy" | None = all
    crop:      Optional[str] = None,
    q:         Optional[str] = None,
    page:      int = 1,
    page_size: int = 10,
    user:      Optional[int] = None,     # filter: posts by one user
    # Structured filters — how /bhav asks for "this district's listings".
    # Omitted by krashi_bajar.html, which wants the whole feed.
    crop_slug: Optional[str] = None,
    state:     Optional[str] = None,
    district:  Optional[str] = None,
    request:   Request = None,
    db:        Session = Depends(get_db),
):
    me = get_optional_user(request, db) if request else None

    query = db.query(BazarPost).filter(BazarPost.status != "closed")

    if post_type in ("sell", "buy"):
        query = query.filter(BazarPost.post_type == post_type)
    if crop:
        query = query.filter(BazarPost.crop.ilike(f"%{crop.strip()}%"))
    if crop_slug:
        query = query.filter(func.lower(BazarPost.crop_slug) == _norm_place(crop_slug))
    if state:
        query = query.filter(func.lower(BazarPost.state) == _norm_place(state))
    if district:
        query = query.filter(func.lower(BazarPost.district) == _norm_place(district))
    if user:
        query = query.filter(BazarPost.users_id == user)
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(
            BazarPost.text.ilike(like),
            BazarPost.crop.ilike(like),
            BazarPost.location.ilike(like),
        ))

    total     = query.count()
    page      = max(1, page)
    page_size = min(max(1, page_size), 30)
    posts = (query.order_by(desc(BazarPost.created_at))
                  .offset((page - 1) * page_size)
                  .limit(page_size).all())

    authors  = _authors_for(posts, db)
    my_likes = set()
    if me and posts:
        my_likes = {
            l.post_id for l in db.query(BazarLike)
            .filter(BazarLike.users_id == me["user_id"],
                    BazarLike.post_id.in_([p.id for p in posts])).all()
        }
    # Which of these authors does the viewer already follow? (for the
    # Follow button on feed cards)
    if me and authors:
        followed = {
            r[0] for r in db.query(BazarFollow.following_id)
            .filter(BazarFollow.follower_id == me["user_id"],
                    BazarFollow.following_id.in_(list(authors.keys()))).all()
        }
        for uid, a in authors.items():
            a["is_following"] = uid in followed

    shops = _shop_names(posts, db)
    items = [
        _post_to_dict(
            p,
            authors.get(p.users_id, {"user_id": p.users_id, "name": "किसान",
                                     "verified": False, "location": ""}),
            liked=p.id in my_likes,
            is_mine=bool(me and me["user_id"] == p.users_id),
            shop_names=shops,
        )
        for p in posts
    ]
    return {
        "success": True,
        "message": "",
        "data": {
            "posts": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": page * page_size < total,
        },
    }


# ── GET /bazar/posts/{post_id} ───────────────────────────────

@router.get("/posts/{post_id}")
def get_single_post(
    post_id: int,
    request: Request = None,
    db:      Session = Depends(get_db),
):
    me = get_optional_user(request, db) if request else None
    post = db.query(BazarPost).filter(BazarPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post नहीं मिला।")

    authors = _authors_for([post], db)
    author = authors.get(post.users_id, {"user_id": post.users_id, "name": "किसान",
                                             "verified": False, "location": ""})
    liked = False
    if me:
        liked = db.query(BazarLike).filter(
            BazarLike.users_id == me["user_id"],
            BazarLike.post_id == post_id
        ).first() is not None
    is_mine = bool(me and me["user_id"] == post.users_id)

    return {
        "success": True,
        "message": "",
        "data": _post_to_dict(post, author, liked=liked, is_mine=is_mine,
                              shop_names=_shop_names([post], db))
    }


# ── POST /bazar/posts — create listing ───────────────────────

async def _read_upload(media: UploadFile, media_type: str, max_bytes: int) -> bytes:
    """Read an upload into memory, refusing it the moment it is too big.

    Bounded by max_bytes, which is why holding the whole file is safe on a
    512 MB instance: the caps below are what make this a few tens of MB and not
    a swap storm. The magic number is checked on the first chunk, before the
    rest of the body is even pulled off the socket — the extension only ever
    told us what the caller *claims*.
    """
    buf, size, first = bytearray(), 0, True
    while True:
        chunk = await media.read(1024 * 1024)
        if not chunk:
            break
        if first:
            assert_media_matches(chunk[:16], media_type)
            first = False
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(
                400,
                f"File बहुत बड़ी है — अधिकतम {max_bytes // (1024*1024)} MB।",
            )
        buf.extend(chunk)
    if not buf:
        raise HTTPException(400, "File खाली है। दोबारा try करें।")
    return bytes(buf)


async def _save_media(media: UploadFile) -> tuple:
    """Validate + store an uploaded image/video. Returns (url, media_type).

    Photos are re-encoded to a bounded WebP first — a 4000px phone JPEG becomes
    ~200 KB, which is what the 390px feed card actually needs and what makes the
    R2 free tier last. Video is stored as uploaded; transcoding needs ffmpeg,
    which this dyno does not have and could not afford the CPU for.

    Storage is R2 when configured and the local disk when it is not, so
    `uvicorn` still runs offline with no credentials. The disk branch is dev
    only: on Render it is wiped every redeploy, which is how every photo posted
    before 14 Sep 2026 was lost. See backend/services/media_store.py.
    """
    ext = os.path.splitext(media.filename or "")[1].lower()
    if ext in IMAGE_EXTS:
        media_type, max_bytes = "image", MAX_IMAGE_BYTES
    elif ext in VIDEO_EXTS:
        media_type, max_bytes = "video", MAX_VIDEO_BYTES
    else:
        raise HTTPException(400, "केवल photo (jpg/png/webp) या video (mp4/webm) upload करें।")

    raw = await _read_upload(media, media_type, max_bytes)

    if media_type == "image":
        try:
            data, content_type, ext = media_store.shrink_image(raw)
        except ValueError as e:
            log.info("[bazar] rejected image upload: %s", e)
            raise HTTPException(400, "यह photo पढ़ी नहीं जा सकी। दूसरी file चुनें।")
    else:
        data = raw
        content_type = VIDEO_CONTENT_TYPES.get(ext, "video/mp4")

    fname = f"{uuid.uuid4().hex}{ext}"

    if not media_store.enabled():
        # In production the disk below is Render's, which is wiped on the next
        # redeploy. Silently writing there is what lost every photo this feature
        # ever held, and it looked like success for months.
        #
        # Refusing was the right call over writing to that disk — but it meant
        # that from 14 Sep 2026, with R2 deferred for want of a payment method,
        # a farmer could not attach a photo at all. So production now falls back
        # to Postgres (services/media_db.py), which is where avatars already
        # live. Images only, and under a hard byte cap: Neon's 0.5 GB ceiling
        # is shared with all 22 tables and filling it turns the whole site
        # read-only. Both limits are enforced by media_db.put().
        if IS_PROD:
            if media_type != "image":
                raise HTTPException(
                    503,
                    "अभी सिर्फ photo डाल सकते हैं, video नहीं। "
                    "बाकी listing अभी भी डाल सकते हैं।",
                )
            try:
                url = await run_in_threadpool(
                    media_db.put, data, fname, content_type
                )
            except Exception:
                log.exception("[bazar] database media store failed")
                raise HTTPException(
                    503,
                    "फोटो upload अभी बंद है — थोड़ी देर बाद try करें। "
                    "बाकी listing अभी भी डाल सकते हैं।",
                )
            return url, media_type
        dest = BAZAR_UPLOAD_DIR / fname
        try:
            dest.write_bytes(data)
        except Exception:
            dest.unlink(missing_ok=True)
            raise HTTPException(500, "File save नहीं हो पाई। दोबारा try करें।")
        return f"/uploads/bazar/{fname}", media_type

    try:
        # Blocking HTTP inside an async endpoint would hold the event loop for
        # the whole upload and stall every other request on the single
        # instance. The threadpool is what keeps the feed responsive.
        url = await run_in_threadpool(
            media_store.put, data, f"{MEDIA_PREFIX}{fname}", content_type
        )
    except Exception:
        log.exception("[bazar] R2 upload failed")
        raise HTTPException(502, "Photo upload नहीं हो पाया। दोबारा try करें।")
    return url, media_type


@router.post("/posts")
async def create_post(
    post_type:    str                  = Form("sell"),
    crop:         Optional[str]        = Form(None),
    text:         Optional[str]        = Form(None),
    price:        Optional[float]      = Form(None),
    old_price:    Optional[float]      = Form(None),
    quantity:     Optional[float]      = Form(None),
    unit:         Optional[str]        = Form("क्विंटल"),
    # Set by the /bhav panel, which knows exactly which crop and district the
    # farmer was looking at. krashi_bajar.html omits them and falls back to the
    # profile below, so the existing composer is unaffected.
    crop_slug:    Optional[str]        = Form(None),
    state:        Optional[str]        = Form(None),
    district:     Optional[str]        = Form(None),
    source:       Optional[str]        = Form(None),
    media:        Optional[UploadFile] = File(None),
    current_user: dict                 = Depends(get_current_user),
    db:           Session              = Depends(get_db),
):
    user_id = current_user["user_id"]
    profile = require_profile(user_id, db)
    require_phone(profile)   # selling needs a reachable contact number

    if post_type not in ("sell", "buy"):
        post_type = "sell"
    if not (text and text.strip()) and not media:
        raise HTTPException(400, "कुछ लिखें या photo/video जोड़ें।")

    # Checked BEFORE the upload, so a capped account never spends our disk and
    # bandwidth on a file we are about to refuse.
    since = datetime.utcnow() - timedelta(days=1)
    todays = (db.query(func.count(BazarPost.id))
                .filter(BazarPost.users_id == user_id,
                        BazarPost.created_at >= since)
                .scalar() or 0)
    if todays >= MAX_POSTS_PER_DAY:
        raise HTTPException(
            429,
            f"एक दिन में {MAX_POSTS_PER_DAY} से ज़्यादा listing नहीं डाल सकते। "
            "कल फिर कोशिश करें।",
        )

    media_url, media_type = (None, None)
    if media and media.filename:
        media_url, media_type = await _save_media(media)

    location = ", ".join([p for p in [profile.village, profile.district] if p])

    # The page the farmer posted from wins over the profile: he may be selling a
    # crop lying in a different district from the one he registered with, and
    # the /bhav page is the district he was actually looking at.
    post = BazarPost(
        users_id   = user_id,
        post_type  = post_type,
        crop       = (crop or "").strip() or None,
        text       = (text or "").strip() or None,
        media_url  = media_url,
        media_type = media_type,
        price      = price,
        old_price  = old_price,
        quantity   = quantity,
        unit       = (unit or "क्विंटल").strip(),
        location   = location,
        crop_slug  = (crop_slug or "").strip() or None,
        state      = (state or "").strip() or (profile.state or None),
        district   = (district or "").strip() or (profile.district or None),
        source     = (source or "").strip() or "bazar",
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    user   = db.query(User).filter(User.id == user_id).first()
    author = _author_info(user, profile)
    return {
        "success": True,
        "message": "पोस्ट हो गया! 🎉",
        "data":    _post_to_dict(post, author, liked=False, is_mine=True),
    }


# ── DELETE /bazar/posts/{id} ─────────────────────────────────

@router.delete("/posts/{post_id}")
def delete_post(
    post_id:      int,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    post = db.query(BazarPost).filter(BazarPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post नहीं मिला।")
    if post.users_id != current_user["user_id"]:
        raise HTTPException(403, "सिर्फ अपना post delete कर सकते हैं।")

    if post.media_url:
        # Three eras of storage: R2 objects, rows in bazar_media (the interim
        # store while R2 is deferred), and files on the local disk from before
        # either (plus whatever a developer uploads offline). owns() picks the
        # right one; all are best-effort, because a storage hiccup must never
        # stop a farmer from removing his own listing.
        if media_store.owns(post.media_url):
            media_store.delete(post.media_url)
        elif media_db.owns(post.media_url):
            media_db.delete(post.media_url)
        elif post.media_url.startswith("/uploads/"):
            try:
                (BAZAR_UPLOAD_DIR / Path(post.media_url).name).unlink(missing_ok=True)
            except Exception:
                pass
    db.query(BazarLike).filter(BazarLike.post_id == post_id).delete()
    db.query(BazarComment).filter(BazarComment.post_id == post_id).delete()
    db.delete(post)
    db.commit()
    return {"success": True, "message": "Post delete हो गया।", "data": {}}


# ── PATCH /bazar/posts/{id} — edit a listing ─────────────────

class EditPostRequest(BaseModel):
    """Every field optional, and "absent" is not "null".

    A farmer fixing a mistyped price sends only `price`; nothing else on the
    listing should move. Pydantic's `model_fields_set` is what separates a field
    the client actually sent from one it left out, so sending `"old_price": null`
    clears the struck-through price while omitting it leaves it alone. Reading
    `None` as "unchanged" would have made clearing a wrong number impossible.
    """
    post_type: Optional[str]   = None
    crop:      Optional[str]   = None
    text:      Optional[str]   = None
    price:     Optional[float] = None
    old_price: Optional[float] = None
    quantity:  Optional[float] = None
    unit:      Optional[str]   = None


@router.patch("/posts/{post_id}")
def edit_post(
    post_id:      int,
    body:         EditPostRequest,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Edit your own listing — text and numbers only, never the media.

    Media is deliberately out of scope: an upload here would write another file
    to Render's ephemeral disk, which already loses every photo on redeploy.
    Replacing a photo waits for object storage; until then the honest options
    are keep it or delete the post.
    """
    post = db.query(BazarPost).filter(BazarPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post नहीं मिला।")
    if post.users_id != current_user["user_id"]:
        raise HTTPException(403, "सिर्फ अपना post edit कर सकते हैं।")

    sent = body.model_fields_set
    if not sent:
        raise HTTPException(400, "कुछ बदला नहीं।")

    # ── Validate before touching the row, so a rejected edit changes nothing
    # and does not burn one of the day's three.
    if "post_type" in sent and body.post_type not in ("sell", "buy"):
        raise HTTPException(400, "Post type sell या buy होना चाहिए।")
    for field in ("price", "old_price", "quantity"):
        v = getattr(body, field)
        if field in sent and v is not None and v < 0:
            raise HTTPException(400, "भाव या मात्रा ऋणात्मक नहीं हो सकती।")
    if "unit" in sent and not (body.unit or "").strip():
        raise HTTPException(400, "इकाई खाली नहीं रह सकती।")
    # A post is allowed to be text-only or media-only, never neither — the same
    # rule create_post enforces, which an edit could otherwise walk around by
    # blanking the text of a post whose photo never existed.
    if "text" in sent and not (body.text or "").strip() and not post.media_url:
        raise HTTPException(400, "Photo नहीं है, तो विवरण खाली नहीं कर सकते।")

    # ── Rate limit, on a rolling 24h window stamped at the window's first edit.
    now = datetime.utcnow()
    window = post.edit_window_start
    used = post.edit_count or 0
    if window is None or (now - window) >= timedelta(days=1):
        window, used = now, 0          # window expired → this edit opens a new one
    elif used >= MAX_EDITS_PER_POST_DAY:
        mins_left = int((window + timedelta(days=1) - now).total_seconds() // 60) + 1
        hrs, mins = divmod(mins_left, 60)
        wait = f"{hrs} घंटे {mins} मिनट" if hrs else f"{mins} मिनट"
        raise HTTPException(
            429,
            f"एक दिन में {MAX_EDITS_PER_POST_DAY} बार ही edit कर सकते हैं। "
            f"{wait} बाद फिर कोशिश करें।",
        )

    # ── Apply only what was sent.
    changed = False
    if "post_type" in sent and post.post_type != body.post_type:
        post.post_type = body.post_type; changed = True
    if "crop" in sent:
        v = (body.crop or "").strip() or None
        if post.crop != v: post.crop = v; changed = True
    if "text" in sent:
        v = (body.text or "").strip() or None
        if post.text != v: post.text = v; changed = True
    if "unit" in sent:
        v = (body.unit or "").strip()
        if post.unit != v: post.unit = v; changed = True
    for field in ("price", "old_price", "quantity"):
        if field in sent:
            v = getattr(body, field)
            if getattr(post, field) != v:
                setattr(post, field, v); changed = True

    # An edit that changes nothing is not an edit: it must not spend one of the
    # three, or a double-tapped Save would.
    if not changed:
        return {"success": True, "message": "कुछ बदला नहीं।",
                "data": {"edits_left": max(0, MAX_EDITS_PER_POST_DAY - used)}}

    post.edit_window_start = window
    post.edit_count = used + 1
    post.updated_at = now
    db.commit()
    db.refresh(post)

    author = _authors_for([post], db).get(post.users_id, {})
    return {
        "success": True,
        "message": "✓ Listing update हो गई।",
        "data": {
            "post": _post_to_dict(post, author, liked=False, is_mine=True),
            "edits_left": max(0, MAX_EDITS_PER_POST_DAY - post.edit_count),
        },
    }


# ── PATCH /bazar/posts/{id}/status ───────────────────────────

class StatusRequest(BaseModel):
    status: str  # active | sold | closed


@router.patch("/posts/{post_id}/status")
def set_post_status(
    post_id:      int,
    body:         StatusRequest,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    if body.status not in ("active", "sold", "closed"):
        raise HTTPException(400, "Status active, sold या closed होना चाहिए।")
    post = db.query(BazarPost).filter(BazarPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post नहीं मिला।")
    if post.users_id != current_user["user_id"]:
        raise HTTPException(403, "सिर्फ अपना post update कर सकते हैं।")
    post.status = body.status
    db.commit()
    return {"success": True, "message": "Status update हो गया।", "data": {"status": post.status}}


# ── POST /bazar/posts/{id}/like — toggle ─────────────────────

@router.post("/posts/{post_id}/like")
def toggle_like(
    post_id:      int,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    user_id = current_user["user_id"]
    require_profile(user_id, db)

    post = db.query(BazarPost).filter(BazarPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post नहीं मिला।")

    existing = (db.query(BazarLike)
                  .filter(BazarLike.post_id == post_id,
                          BazarLike.users_id == user_id).first())
    if existing:
        db.delete(existing)
        post.likes_count = max(0, (post.likes_count or 0) - 1)
        liked = False
    else:
        db.add(BazarLike(post_id=post_id, users_id=user_id))
        post.likes_count = (post.likes_count or 0) + 1
        liked = True
    db.commit()
    return {
        "success": True, "message": "",
        "data": {"liked": liked, "likes_count": post.likes_count},
    }


# ── Comments & offers ────────────────────────────────────────

class CommentRequest(BaseModel):
    text:         Optional[str]   = None
    kind:         str             = "comment"   # "comment" | "offer"
    offer_amount: Optional[float] = None
    parent_id:    Optional[int]   = None        # set to reply to a comment


@router.get("/posts/{post_id}/comments")
def get_comments(
    post_id: int,
    request: Request = None,
    db:      Session = Depends(get_db),
):
    post = db.query(BazarPost).filter(BazarPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post नहीं मिला।")

    me = get_optional_user(request, db) if request else None

    comments = (db.query(BazarComment)
                  .filter(BazarComment.post_id == post_id)
                  .order_by(BazarComment.created_at.asc())
                  .limit(200).all())
    authors = _authors_for(comments, db)

    # Which of these the viewer has already liked — one query for the whole
    # thread, not one per comment.
    liked_ids = set()
    if me and comments:
        liked_ids = {row[0] for row in db.query(BazarCommentLike.comment_id).filter(
            BazarCommentLike.users_id == me["user_id"],
            BazarCommentLike.comment_id.in_([c.id for c in comments]),
        ).all()}

    # The post's owner may remove anything under his own listing; everyone else
    # may remove only what they wrote.
    my_id = me["user_id"] if me else None
    is_post_owner = bool(my_id and post.users_id == my_id)

    def _one(c: BazarComment) -> dict:
        return {
            "id":           c.id,
            "kind":         c.kind,
            "text":         c.text,
            "offer_amount": c.offer_amount,
            "parent_id":    c.parent_id,
            "likes_count":  c.likes_count or 0,
            "liked_by_me":  c.id in liked_ids,
            "can_delete":   bool(my_id and (c.users_id == my_id or is_post_owner)),
            "created_at":   c.created_at.isoformat() if c.created_at else None,
            "author":       authors.get(c.users_id, {"user_id": c.users_id, "name": "किसान",
                                                     "verified": False, "location": ""}),
        }

    # Flat list, parents first with their replies nested under them. The client
    # renders exactly two levels, so the shape it needs is built here rather
    # than reassembled in JavaScript.
    by_parent: dict = {}
    for c in comments:
        if c.parent_id:
            by_parent.setdefault(c.parent_id, []).append(c)

    items = []
    for c in comments:
        if c.parent_id:
            continue
        row = _one(c)
        row["replies"] = [_one(r) for r in by_parent.get(c.id, [])]
        items.append(row)

    return {"success": True, "message": "", "data": {"comments": items}}


@router.post("/posts/{post_id}/comments")
def add_comment(
    post_id:      int,
    body:         CommentRequest,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    user_id = current_user["user_id"]
    profile = require_profile(user_id, db)

    post = db.query(BazarPost).filter(BazarPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post नहीं मिला।")

    kind = body.kind if body.kind in ("comment", "offer") else "comment"
    if kind == "offer":
        require_phone(profile)   # purchase offers need a reachable contact number
        if not body.offer_amount or body.offer_amount <= 0:
            raise HTTPException(400, "सही offer amount डालें।")
    elif not (body.text and body.text.strip()):
        raise HTTPException(400, "Comment खाली नहीं हो सकता।")

    # Replies are one level deep and no deeper. Answering a reply attaches to
    # that reply's own parent, so the thread stays two levels on a 390px screen
    # instead of marching off the right edge.
    parent_id = None
    if body.parent_id:
        parent = db.query(BazarComment).filter(
            BazarComment.id == body.parent_id,
            BazarComment.post_id == post_id,     # never across posts
        ).first()
        if not parent:
            raise HTTPException(404, "जिस comment का जवाब दे रहे हैं वह नहीं मिला।")
        parent_id = parent.parent_id or parent.id
        if kind == "offer":
            # An offer is a number against the listing, not against a sentence
            # in the thread; nesting one would hide it from the seller.
            raise HTTPException(400, "Offer किसी comment का जवाब नहीं हो सकता।")

    comment = BazarComment(
        post_id      = post_id,
        users_id     = user_id,
        kind         = kind,
        text         = (body.text or "").strip() or None,
        offer_amount = body.offer_amount if kind == "offer" else None,
        parent_id    = parent_id,
        likes_count  = 0,
    )
    db.add(comment)
    post.comments_count = (post.comments_count or 0) + 1
    db.commit()
    db.refresh(comment)

    user = db.query(User).filter(User.id == user_id).first()
    return {
        "success": True,
        "message": "Offer भेज दिया! 💰" if kind == "offer" else "Comment जुड़ गया।",
        "data": {
            "id":           comment.id,
            "kind":         comment.kind,
            "text":         comment.text,
            "offer_amount": comment.offer_amount,
            "created_at":   comment.created_at.isoformat(),
            "author":       _author_info(user, profile),
            "parent_id":    comment.parent_id,
            "likes_count":  0,
            "liked_by_me":  False,
            "can_delete":   True,
            "replies":      [],
            "comments_count": post.comments_count,
        },
    }


# ── DELETE /bazar/posts/{post_id}/comments/{comment_id} ──────

@router.delete("/posts/{post_id}/comments/{comment_id}")
def delete_comment(
    post_id:      int,
    comment_id:   int,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Remove a comment, offer or reply.

    Two people may do it: whoever wrote it, and whoever owns the listing — a
    farmer has to be able to clear abuse or a wrong price off his own post
    without waiting for us. Deleting a top-level comment takes its replies with
    it, because a reply to nothing is unreadable.
    """
    user_id = current_user["user_id"]
    post = db.query(BazarPost).filter(BazarPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post नहीं मिला।")

    comment = db.query(BazarComment).filter(
        BazarComment.id == comment_id,
        BazarComment.post_id == post_id,
    ).first()
    if not comment:
        raise HTTPException(404, "Comment नहीं मिला।")

    if comment.users_id != user_id and post.users_id != user_id:
        raise HTTPException(403, "सिर्फ अपना comment delete कर सकते हैं।")

    # A parent takes its replies down with it; count them BEFORE the delete.
    doomed = [comment.id]
    if not comment.parent_id:
        doomed += [r.id for r in db.query(BazarComment.id).filter(
            BazarComment.parent_id == comment.id).all()]

    db.query(BazarCommentLike).filter(
        BazarCommentLike.comment_id.in_(doomed)).delete(synchronize_session=False)
    db.query(BazarComment).filter(
        BazarComment.id.in_(doomed)).delete(synchronize_session=False)

    # Never below zero: these counters predate the column and some rows drifted.
    post.comments_count = max(0, (post.comments_count or 0) - len(doomed))
    db.commit()

    return {
        "success": True,
        "message": "Comment हटा दिया।",
        "data": {"deleted": doomed, "comments_count": post.comments_count},
    }


# ── POST /bazar/comments/{comment_id}/like ───────────────────

@router.post("/comments/{comment_id}/like")
def toggle_comment_like(
    comment_id:   int,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Toggle. The unique constraint on (comment_id, user_id) is what makes a
    double-tap idempotent rather than a second like."""
    user_id = current_user["user_id"]
    require_profile(user_id, db)

    comment = db.query(BazarComment).filter(BazarComment.id == comment_id).first()
    if not comment:
        raise HTTPException(404, "Comment नहीं मिला।")

    existing = db.query(BazarCommentLike).filter(
        BazarCommentLike.comment_id == comment_id,
        BazarCommentLike.users_id == user_id,
    ).first()

    if existing:
        db.delete(existing)
        liked = False
    else:
        db.add(BazarCommentLike(comment_id=comment_id, users_id=user_id))
        liked = True
    db.flush()

    # Counted from the rows rather than incremented, so a counter that has
    # drifted heals itself on the next tap instead of drifting further.
    comment.likes_count = db.query(func.count(BazarCommentLike.id)).filter(
        BazarCommentLike.comment_id == comment_id).scalar() or 0
    db.commit()

    return {
        "success": True,
        "message": "",
        "data": {"liked": liked, "likes_count": comment.likes_count},
    }


# ── Public profile card ──────────────────────────────────────

@router.get("/users/{user_id}")
def get_public_profile(
    user_id: int,
    request: Request = None,
    db:      Session = Depends(get_db),
):
    me      = get_optional_user(request, db) if request else None
    user    = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User नहीं मिला।")
    profile = db.query(UserProfile).filter(UserProfile.user_id == acct(user_id)).first()

    posts_count     = db.query(BazarPost).filter(BazarPost.users_id == user_id).count()
    followers_count = db.query(BazarFollow).filter(BazarFollow.following_id == user_id).count()
    following_count = db.query(BazarFollow).filter(BazarFollow.follower_id == user_id).count()

    is_following = False
    if me and me["user_id"] != user_id:
        is_following = (db.query(BazarFollow)
                          .filter(BazarFollow.follower_id == me["user_id"],
                                  BazarFollow.following_id == user_id)
                          .first()) is not None

    recent = (db.query(BazarPost)
                .filter(BazarPost.users_id == user_id, BazarPost.status != "closed")
                .order_by(desc(BazarPost.created_at)).limit(6).all())
    author = _author_info(user, profile)
    # No shop_names here on purpose. This card's whole job is to say who the
    # account actually is, and a dealer's own posts listed under his real name
    # and face is the point — the shopfront name belongs on the feed, where a
    # farmer meets the listing cold and has no other context for it.
    recent_posts = [
        _post_to_dict(p, author, liked=False,
                      is_mine=bool(me and me["user_id"] == user_id))
        for p in recent
    ]

    member_since = user.created_at.strftime("%b %Y") if user.created_at else None

    return {
        "success": True,
        "message": "",
        "data": {
            "user_id":          user.id,
            "name":             author["name"],
            "avatar_url":       author.get("avatar_url"),
            "verified":         bool(user.seller_verified),
            "location":         author["location"],
            "state":            profile.state if profile else None,
            "crops_grown":      profile.crops_grown if profile else None,
            "primary_crop":     profile.primary_crop if profile else user.primary_crop,
            "farming_experience": profile.farming_experience if profile else None,
            "farming_type":     profile.farming_type if profile else None,
            "member_since":     member_since,
            "posts_count":      posts_count,
            "followers_count":  followers_count,
            "following_count":  following_count,
            "is_following":     is_following,
            "is_me":            bool(me and me["user_id"] == user_id),
            "recent_posts":     recent_posts,
        },
    }


# ── Followers / Following lists ──────────────────────────────

def _follow_user_cards(ids, viewer_id, db) -> list:
    """Build user cards for an ordered list of user ids, marking whether the
    viewer already follows each one (so the list can show Follow/Following)."""
    if not ids:
        return []
    users    = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}
    # Re-keyed account number → users.id, same reason as _authors_for above.
    by_acct  = {pr.user_id: pr for pr in
                db.query(UserProfile).filter(UserProfile.user_id.in_(accts(ids))).all()}
    profiles = {uid: by_acct.get(u.user_id) for uid, u in users.items()}
    following_set = set()
    if viewer_id:
        rows = (db.query(BazarFollow.following_id)
                  .filter(BazarFollow.follower_id == viewer_id,
                          BazarFollow.following_id.in_(ids)).all())
        following_set = {r[0] for r in rows}
    cards = []
    for uid in ids:                       # preserve caller's ordering
        if uid not in users:
            continue
        info = _author_info(users.get(uid), profiles.get(uid))
        cards.append({
            "user_id":      uid,
            "name":         info["name"],
            "avatar_url":   info.get("avatar_url"),
            "verified":     info["verified"],
            "location":     info["location"],
            "is_following": uid in following_set,
            "is_me":        bool(viewer_id and viewer_id == uid),
        })
    return cards


@router.get("/users/{user_id}/followers")
def list_followers(
    user_id: int,
    request: Request = None,
    db:      Session = Depends(get_db),
):
    """Users who follow user_id (most recent first)."""
    me   = get_optional_user(request, db) if request else None
    rows = (db.query(BazarFollow.follower_id)
              .filter(BazarFollow.following_id == user_id)
              .order_by(desc(BazarFollow.created_at)).all())
    ids  = [r[0] for r in rows]
    cards = _follow_user_cards(ids, me["user_id"] if me else None, db)
    return {"success": True, "message": "", "data": {"users": cards, "count": len(cards)}}


@router.get("/users/{user_id}/following")
def list_following(
    user_id: int,
    request: Request = None,
    db:      Session = Depends(get_db),
):
    """Users that user_id follows (most recent first)."""
    me   = get_optional_user(request, db) if request else None
    rows = (db.query(BazarFollow.following_id)
              .filter(BazarFollow.follower_id == user_id)
              .order_by(desc(BazarFollow.created_at)).all())
    ids  = [r[0] for r in rows]
    cards = _follow_user_cards(ids, me["user_id"] if me else None, db)
    return {"success": True, "message": "", "data": {"users": cards, "count": len(cards)}}


# ── POST /bazar/users/{id}/follow — toggle ───────────────────

@router.post("/users/{user_id}/follow")
def toggle_follow(
    user_id:      int,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    me = current_user["user_id"]
    require_profile(me, db)

    if me == user_id:
        raise HTTPException(400, "खुद को follow नहीं कर सकते।")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404, "User नहीं मिला।")

    existing = (db.query(BazarFollow)
                  .filter(BazarFollow.follower_id == me,
                          BazarFollow.following_id == user_id).first())
    if existing:
        db.delete(existing)
        following = False
    else:
        db.add(BazarFollow(follower_id=me, following_id=user_id))
        following = True
    db.commit()

    followers_count = (db.query(BazarFollow)
                         .filter(BazarFollow.following_id == user_id).count())
    return {
        "success": True,
        "message": "Follow कर लिया! 🤝" if following else "Unfollow हो गया।",
        "data": {"following": following, "followers_count": followers_count},
    }


log.info("[bazar.py] loaded successfully")
