# ============================================================
# backend/routes/news_curate.py
# KrashiMitra — AI News Auto-Pilot & Community Social Routes
# ============================================================

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.db import NewsComment, NewsLike, get_db
from backend.utils.auth_utils import decode_access_token, resolve_token_user
from backend.services.news_auto_service import (
    add_direct_post,
    curate_from_url,
    discard_post,
    edit_staged_post,
    generate_ai_agri_image,
    get_current_cycle_info,
    get_published_posts,
    get_staged_posts,
    publish_all_staged,
    publish_post,
    run_discovery_and_stage,
)

logger = logging.getLogger("krishi.news_curate_route")

router = APIRouter(prefix="/api/news", tags=["Krashi News Auto-Pilot"])

oauth2_scheme = HTTPBearer(auto_error=False)


def get_news_auth_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> dict:
    """Strictly requires user login for like & comment actions, while safely accepting valid JWT tokens."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="कृपया लाइक या कमेंट करने के लिए पहले लॉगिन करें।",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip()
    if not token or token in ["null", "undefined"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="कृपया लाइक या कमेंट करने के लिए पहले लॉगिन करें।",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Full DB user lookup
    try:
        user = resolve_token_user(db, token)
        if user:
            name = getattr(user, "name", None) or getattr(user, "full_name", None) or (user.email.split("@")[0] if getattr(user, "email", None) else "किसान भाई")
            return {"user_id": user.id, "name": name, "email": getattr(user, "email", "")}
    except Exception as e:
        logger.warning(f"resolve_token_user warning: {e}")

    # 2. JWT token decode fallback (valid cryptographically, even if verification flag was pending)
    payload = decode_access_token(token)
    if payload:
        uid = payload.get("sub") or payload.get("user_id") or payload.get("email") or "user"
        email = payload.get("email") or f"{uid}@krashimitra.in"
        name = payload.get("name") or str(uid)
        return {"user_id": uid, "name": name, "email": email}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="आपका लॉगिन सत्र (Token) समाप्त हो गया है। कृपया दोबारा लॉगिन करें।",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ── Pydantic Request Models ────────────────────────────────────

class CurateUrlRequest(BaseModel):
    url: str
    language: Optional[str] = "hi"


class FunnelPublishRequest(BaseModel):
    id: Optional[str] = None
    publish_all: bool = False


class FunnelDiscardRequest(BaseModel):
    id: str


class FunnelEditRequest(BaseModel):
    id: str
    updates: dict


class GenerateImageRequest(BaseModel):
    post_id: Optional[str] = None
    title: str
    category: Optional[str] = "crop"
    custom_prompt: Optional[str] = None


class DirectPublishRequest(BaseModel):
    post: dict
    publish_now: bool = True


class LikeRequest(BaseModel):
    user_id: Optional[str] = "anon"
    is_liked: Optional[bool] = True


class CommentRequest(BaseModel):
    author_name: Optional[str] = "किसान भाई"
    location: Optional[str] = None
    comment_text: str = Field(..., min_length=1, max_length=1000)


# ── Public Feed ────────────────────────────────────────────────

@router.get("/feed")
async def get_public_news_feed():
    """
    Returns all published auto-pilot & curated agricultural news articles.
    Consumed directly by frontend/krashi_news.html.
    """
    published = get_published_posts()
    return {
        "success": True,
        "count": len(published),
        "articles": published,
    }


# ── Admin Staging Funnel Endpoints ─────────────────────────────

@router.get("/funnel")
async def get_funnel_status():
    """Returns the current 3-4 day cycle information and staged posts waiting for review."""
    cycle_info = get_current_cycle_info()
    staged = get_staged_posts()
    return {
        "success": True,
        "cycle": cycle_info,
        "staged_posts": staged,
    }


@router.post("/funnel/publish")
async def publish_funnel_item(payload: FunnelPublishRequest):
    """Publishes a single post or bulk publishes all staged posts."""
    if payload.publish_all:
        count = publish_all_staged()
        return {"success": True, "message": f"{count} समाचार लेख सार्वजनिक फीड में लाइव कर दिए गए!", "count": count}

    if not payload.id:
        raise HTTPException(status_code=400, detail="Article ID is required")

    published = publish_post(payload.id)
    if not published:
        raise HTTPException(status_code=404, detail="लेख नहीं मिला")

    return {"success": True, "message": "समाचार प्रकाशित हो गया!", "article": published}


@router.post("/funnel/discard")
async def discard_funnel_item(payload: FunnelDiscardRequest):
    """Discards an unwanted draft from the staging funnel."""
    ok = discard_post(payload.id)
    if not ok:
        raise HTTPException(status_code=404, detail="लेख नहीं मिला")
    return {"success": True, "message": "लेख फ़नल से हटा दिया गया"}


@router.post("/funnel/edit")
async def edit_funnel_item(payload: FunnelEditRequest):
    """Edits a staged draft in the funnel."""
    updated = edit_staged_post(payload.id, payload.updates)
    if not updated:
        raise HTTPException(status_code=404, detail="लेख नहीं मिला")
    return {"success": True, "message": "लेख सफलतापूर्वक संपादित किया गया", "article": updated}


@router.post("/trigger-discovery")
async def trigger_ai_discovery():
    """Triggers an on-demand Gemini news discovery sweep (Days 1-3 simulation)."""
    new_items = await run_discovery_and_stage()
    return {
        "success": True,
        "message": f"Gemini ने {len(new_items)} नए कृषि समाचार संकलित कर फ़नल में सुरक्षित कर दिए हैं।",
        "staged_count": len(new_items),
        "articles": new_items,
    }


# ── Smart URL Curator ─────────────────────────────────────────

@router.post("/curate-url")
async def curate_news_from_url(payload: CurateUrlRequest):
    """
    Takes any agricultural news web link, scrapes it, and uses Gemini to create
    a complete news post with 3 takeaway bullets in the selected language.
    """
    try:
        curated_draft = await curate_from_url(payload.url, language=payload.language or "hi")
        return {"success": True, "article": curated_draft}
    except Exception as e:
        logger.error(f"Error curating URL {payload.url}: {e}")
        raise HTTPException(status_code=400, detail=f"वेबसाइट से समाचार पढ़ने में त्रुटि: {str(e)}")


@router.post("/publish-direct")
async def publish_news_direct(payload: DirectPublishRequest):
    """Saves a post directly or adds it to the staging queue."""
    try:
        saved = add_direct_post(payload.post, publish_now=payload.publish_now)
        msg = "समाचार प्रकाशित हो गया!" if payload.publish_now else "समाचार फ़नल में जोड़ दिया गया!"
        return {"success": True, "message": msg, "article": saved}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.post("/generate-image")
async def generate_news_image_route(payload: GenerateImageRequest):
    """Generates a relevant, high-resolution agricultural image using Gemini + Imagen 3 / Pollinations."""
    try:
        res = await generate_ai_agri_image(
            title=payload.title,
            category=payload.category or "crop",
            custom_prompt=payload.custom_prompt,
            post_id=payload.post_id,
        )
        return res
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        raise HTTPException(status_code=500, detail=f"इमेज तैयार करने में त्रुटि: {str(e)}")


# ── Social Community: Real DB Likes & Comments ─────────────────

def _calc_seed_likes(news_id: str) -> int:
    h = 0
    for ch in news_id:
        h = ((h << 5) - h) + ord(ch)
    return 260 + (abs(h) % 321)  # 260 to 580 likes


# ⚠️  /social/batch MUST be defined BEFORE /{news_id}/social,
#     otherwise FastAPI treats "social" as a {news_id} path param
#     and the batch endpoint is never reached.
@router.get("/social/batch")
async def get_batch_news_social(ids: str = "", db: Session = Depends(get_db)):
    """
    Returns live like counts and comment counts for multiple news IDs in 1 request.
    Example: GET /api/news/social/batch?ids=news-lead,km-auto-1,news-1

    Response is a flat dict keyed by news_id with `likes` and `comments` fields
    so the frontend can iterate Object.keys(response) directly.
    """
    news_id_list = [i.strip() for i in ids.split(",") if i.strip()]
    res = {}
    for nid in news_id_list:
        base_seed = _calc_seed_likes(nid)
        db_likes = db.query(NewsLike).filter(NewsLike.news_id == nid).count()
        comm_count = db.query(NewsComment).filter(NewsComment.news_id == nid, NewsComment.is_approved == True).count()
        res[nid] = {
            "likes": base_seed + db_likes,
            "comments": comm_count,
        }
    return res


@router.get("/{news_id}/social")
async def get_news_social(news_id: str, db: Session = Depends(get_db)):
    """
    Returns real comments and tallied likes for a news post.
    Comments start strictly at 0!
    """
    # 1. Tally Likes (Seeded organic base 260-580 + real DB likes)
    base_seed = _calc_seed_likes(news_id)
    db_likes = db.query(NewsLike).filter(NewsLike.news_id == news_id).count()
    total_likes = base_seed + db_likes

    # 2. Fetch real comments (Starts at 0)
    comments = (
        db.query(NewsComment)
        .filter(NewsComment.news_id == news_id, NewsComment.is_approved == True)
        .order_by(NewsComment.created_at.desc())
        .all()
    )

    comments_list = [
        {
            "id": c.id,
            "author_name": c.author_name,
            "location": c.location or "",
            "comment_text": c.comment_text,
            "created_at": c.created_at.strftime("%d %b %Y, %I:%M %p") if c.created_at else "हाल ही में",
        }
        for c in comments
    ]

    return {
        "success": True,
        "news_id": news_id,
        "total_likes": total_likes,
        "comment_count": len(comments_list),
        "comments": comments_list,
    }


@router.post("/{news_id}/like")
async def add_news_like(
    news_id: str,
    payload: LikeRequest,
    req: Request,
    current_user: dict = Depends(get_news_auth_user),
    db: Session = Depends(get_db),
):
    """Records an authenticated user like in the database and supports toggle/unlike."""
    user_ident = f"user-{current_user.get('user_id')}"

    existing = (
        db.query(NewsLike)
        .filter(NewsLike.news_id == news_id, NewsLike.user_identifier == user_ident)
        .first()
    )

    is_liked = payload.is_liked if payload.is_liked is not None else True

    if is_liked:
        if not existing:
            new_like = NewsLike(news_id=news_id, user_identifier=user_ident)
            db.add(new_like)
            try:
                db.commit()
            except Exception as e:
                db.rollback()
                logger.warning(f"Like commit warning: {e}")
    else:
        # User unliked
        if existing:
            db.delete(existing)
            try:
                db.commit()
            except Exception as e:
                db.rollback()
                logger.warning(f"Unlike commit warning: {e}")

    base_seed = _calc_seed_likes(news_id)
    total_likes = base_seed + db.query(NewsLike).filter(NewsLike.news_id == news_id).count()

    return {"success": True, "total_likes": total_likes, "is_liked": is_liked}


@router.post("/{news_id}/comment")
async def post_news_comment(
    news_id: str,
    payload: CommentRequest,
    current_user: dict = Depends(get_news_auth_user),
    db: Session = Depends(get_db),
):
    """Submits an authenticated farmer comment and makes it visible to all visitors."""
    author_name = (payload.author_name or "").strip()
    if not author_name or author_name in ["किसान भाई", "किसान साथी"]:
        author_name = current_user.get("name") or (current_user.get("email", "").split("@")[0] if current_user.get("email") else "किसान भाई")

    comment = NewsComment(
        news_id=news_id,
        author_name=author_name,
        location=payload.location.strip() if payload.location else None,
        comment_text=payload.comment_text.strip(),
        is_approved=True,
    )
    db.add(comment)
    try:
        db.commit()
        db.refresh(comment)
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving comment: {e}")
        raise HTTPException(status_code=500, detail="टिप्पणी सहेजने में विफल")

    # Fetch updated count and list
    updated_comments = (
        db.query(NewsComment)
        .filter(NewsComment.news_id == news_id, NewsComment.is_approved == True)
        .order_by(NewsComment.created_at.desc())
        .all()
    )

    return {
        "success": True,
        "message": "आपकी टिप्पणी पोस्ट हो गई!",
        "comment_count": len(updated_comments),
        "comment": {
            "id": comment.id,
            "author_name": comment.author_name,
            "location": comment.location or "",
            "comment_text": comment.comment_text,
            "created_at": comment.created_at.strftime("%d %b %Y, %I:%M %p"),
        },
    }
