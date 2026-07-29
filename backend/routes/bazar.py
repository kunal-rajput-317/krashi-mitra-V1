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
#   GET    /bazar/posts/{id}/comments      public
#   POST   /bazar/posts/{id}/comments      auth+profile — comment or ₹ offer
#   GET    /bazar/users/{id}               public profile card (auth optional)
#   POST   /bazar/users/{id}/follow        auth+profile — toggle
# ============================================================

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
)
from pydantic import BaseModel
from sqlalchemy import func, or_, desc
from sqlalchemy.orm import Session

from backend.database.db import (
    User, UserProfile, BazarPost, BazarLike, BazarComment, BazarFollow, get_db
)
from backend.utils.auth_utils import get_current_user, decode_access_token
from backend.utils.security import assert_media_matches

router = APIRouter(prefix="/bazar", tags=["bazar"])

# ── Media storage ────────────────────────────────────────────

BAZAR_UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads" / "bazar"
BAZAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v"}
MAX_IMAGE_BYTES = 50  * 1024 * 1024   # 50 MB
# Video duration (max 5 min) is enforced client-side in krashi_bajar.html —
# the server can't read duration without ffprobe, so it caps raw size instead.
MAX_VIDEO_BYTES = 120 * 1024 * 1024   # 120 MB (~5 min at phone-camera bitrate)


# ── Auth helpers ─────────────────────────────────────────────

def get_optional_user(request: Request) -> Optional[dict]:
    """Like get_current_user but returns None instead of 401 for guests."""
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    payload = decode_access_token(auth[7:].strip())
    if not payload:
        return None
    try:
        return {"user_id": int(payload["sub"]), "email": payload.get("email")}
    except (KeyError, ValueError):
        return None


def require_profile(user_id: int, db: Session) -> UserProfile:
    """Selling/buying interactions need a completed farmer profile."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
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


def _post_to_dict(p: BazarPost, author: dict, liked: bool, is_mine: bool) -> dict:
    return {
        "id":             p.id,
        "post_type":      p.post_type,
        "crop":           p.crop,
        "text":           p.text,
        "media_url":      p.media_url,
        "media_type":     p.media_type,
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
        "author":         author,
        "liked_by_me":    liked,
        "is_mine":        is_mine,
    }


def _authors_for(posts, db: Session) -> dict:
    """Batch-load author info for a list of posts → {user_id: author_dict}."""
    ids = {p.user_id for p in posts}
    if not ids:
        return {}
    users    = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}
    profiles = {pr.user_id: pr for pr in
                db.query(UserProfile).filter(UserProfile.user_id.in_(ids)).all()}
    return {uid: _author_info(users.get(uid), profiles.get(uid)) for uid in ids}


# ── GET /bazar/me — frontend gate info ───────────────────────

@router.get("/me")
def bazar_me(
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    user_id = current_user["user_id"]
    user    = db.query(User).filter(User.id == user_id).first()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
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
    me = get_optional_user(request) if request else None

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
        query = query.filter(BazarPost.user_id == user)
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
            .filter(BazarLike.user_id == me["user_id"],
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

    items = [
        _post_to_dict(
            p,
            authors.get(p.user_id, {"user_id": p.user_id, "name": "किसान",
                                    "verified": False, "location": ""}),
            liked=p.id in my_likes,
            is_mine=bool(me and me["user_id"] == p.user_id),
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
    me = get_optional_user(request) if request else None
    post = db.query(BazarPost).filter(BazarPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post नहीं मिला।")

    authors = _authors_for([post], db)
    author = authors.get(post.user_id, {"user_id": post.user_id, "name": "किसान",
                                            "verified": False, "location": ""})
    liked = False
    if me:
        liked = db.query(BazarLike).filter(
            BazarLike.user_id == me["user_id"],
            BazarLike.post_id == post_id
        ).first() is not None
    is_mine = bool(me and me["user_id"] == post.user_id)

    return {
        "success": True,
        "message": "",
        "data": _post_to_dict(post, author, liked=liked, is_mine=is_mine)
    }


# ── POST /bazar/posts — create listing ───────────────────────

async def _save_media(media: UploadFile) -> tuple:
    """Validate + save an uploaded image/video. Returns (url, media_type)."""
    ext = os.path.splitext(media.filename or "")[1].lower()
    if ext in IMAGE_EXTS:
        media_type, max_bytes = "image", MAX_IMAGE_BYTES
    elif ext in VIDEO_EXTS:
        media_type, max_bytes = "video", MAX_VIDEO_BYTES
    else:
        raise HTTPException(400, "केवल photo (jpg/png/webp) या video (mp4/webm) upload करें।")

    fname = f"{uuid.uuid4().hex}{ext}"
    dest  = BAZAR_UPLOAD_DIR / fname
    size  = 0
    first = True
    try:
        with open(dest, "wb") as f:
            while True:
                chunk = await media.read(1024 * 1024)
                if not chunk:
                    break
                if first:
                    # The extension only told us what the caller *claims*.
                    # Check the magic number before a single byte lands on disk.
                    assert_media_matches(chunk[:16], media_type)
                    first = False
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        400,
                        f"File बहुत बड़ी है — अधिकतम {max_bytes // (1024*1024)} MB।",
                    )
                f.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception:
        dest.unlink(missing_ok=True)
        raise HTTPException(500, "File save नहीं हो पाई। दोबारा try करें।")
    return f"/uploads/bazar/{fname}", media_type


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

    media_url, media_type = (None, None)
    if media and media.filename:
        media_url, media_type = await _save_media(media)

    location = ", ".join([p for p in [profile.village, profile.district] if p])

    # The page the farmer posted from wins over the profile: he may be selling a
    # crop lying in a different district from the one he registered with, and
    # the /bhav page is the district he was actually looking at.
    post = BazarPost(
        user_id    = user_id,
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
    if post.user_id != current_user["user_id"]:
        raise HTTPException(403, "सिर्फ अपना post delete कर सकते हैं।")

    if post.media_url:
        try:
            (BAZAR_UPLOAD_DIR / Path(post.media_url).name).unlink(missing_ok=True)
        except Exception:
            pass
    db.query(BazarLike).filter(BazarLike.post_id == post_id).delete()
    db.query(BazarComment).filter(BazarComment.post_id == post_id).delete()
    db.delete(post)
    db.commit()
    return {"success": True, "message": "Post delete हो गया।", "data": {}}


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
    if post.user_id != current_user["user_id"]:
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
                          BazarLike.user_id == user_id).first())
    if existing:
        db.delete(existing)
        post.likes_count = max(0, (post.likes_count or 0) - 1)
        liked = False
    else:
        db.add(BazarLike(post_id=post_id, user_id=user_id))
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


@router.get("/posts/{post_id}/comments")
def get_comments(
    post_id: int,
    db:      Session = Depends(get_db),
):
    post = db.query(BazarPost).filter(BazarPost.id == post_id).first()
    if not post:
        raise HTTPException(404, "Post नहीं मिला।")

    comments = (db.query(BazarComment)
                  .filter(BazarComment.post_id == post_id)
                  .order_by(BazarComment.created_at.asc())
                  .limit(200).all())
    authors = _authors_for(comments, db)
    items = [{
        "id":           c.id,
        "kind":         c.kind,
        "text":         c.text,
        "offer_amount": c.offer_amount,
        "created_at":   c.created_at.isoformat() if c.created_at else None,
        "author":       authors.get(c.user_id, {"user_id": c.user_id, "name": "किसान",
                                                "verified": False, "location": ""}),
    } for c in comments]
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

    comment = BazarComment(
        post_id      = post_id,
        user_id      = user_id,
        kind         = kind,
        text         = (body.text or "").strip() or None,
        offer_amount = body.offer_amount if kind == "offer" else None,
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
            "comments_count": post.comments_count,
        },
    }


# ── Public profile card ──────────────────────────────────────

@router.get("/users/{user_id}")
def get_public_profile(
    user_id: int,
    request: Request = None,
    db:      Session = Depends(get_db),
):
    me      = get_optional_user(request) if request else None
    user    = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User नहीं मिला।")
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

    posts_count     = db.query(BazarPost).filter(BazarPost.user_id == user_id).count()
    followers_count = db.query(BazarFollow).filter(BazarFollow.following_id == user_id).count()
    following_count = db.query(BazarFollow).filter(BazarFollow.follower_id == user_id).count()

    is_following = False
    if me and me["user_id"] != user_id:
        is_following = (db.query(BazarFollow)
                          .filter(BazarFollow.follower_id == me["user_id"],
                                  BazarFollow.following_id == user_id)
                          .first()) is not None

    recent = (db.query(BazarPost)
                .filter(BazarPost.user_id == user_id, BazarPost.status != "closed")
                .order_by(desc(BazarPost.created_at)).limit(6).all())
    author = _author_info(user, profile)
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
    profiles = {pr.user_id: pr for pr in
                db.query(UserProfile).filter(UserProfile.user_id.in_(ids)).all()}
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
    me   = get_optional_user(request) if request else None
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
    me   = get_optional_user(request) if request else None
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


print("[bazar.py] loaded successfully")
