# ============================================================
# backend/routes/profile.py
# KrashiMitra — Farmer Profile Router
# ============================================================
# STEP 3: POST /profile — Create farmer profile (JWT protected)
# STEP 4: PUT  /profile — Update profile         (JWT protected)
# STEP 5: GET  /profile — Fetch profile          (coming next)
# ============================================================

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from backend.database.db import UserProfile, get_db
from backend.utils.auth_utils import get_current_user

router = APIRouter(prefix="/profile", tags=["profile"])


# ── Request Models ───────────────────────────────────────────

class ProfileCreateRequest(BaseModel):
    full_name:          str
    phone_number:       Optional[str] = None
    state:              Optional[str] = None
    district:           Optional[str] = None
    village:            Optional[str] = None
    preferred_language: Optional[str] = "hindi"
    crops_grown:        Optional[str] = None   # comma-separated: "wheat,rice"
    farm_size:          Optional[str] = None   # e.g. "2.5 acres"


class ProfileUpdateRequest(BaseModel):
    # All fields optional — only sent fields get updated
    full_name:          Optional[str] = None
    phone_number:       Optional[str] = None
    state:              Optional[str] = None
    district:           Optional[str] = None
    village:            Optional[str] = None
    preferred_language: Optional[str] = None
    crops_grown:        Optional[str] = None
    farm_size:          Optional[str] = None


# ── Helper ───────────────────────────────────────────────────

def _profile_to_dict(p: UserProfile) -> dict:
    """Serialize a UserProfile row to a clean response dict."""
    return {
        "id":                 p.id,
        "user_id":            p.user_id,
        "full_name":          p.name,
        "phone_number":       p.phone_number,
        "state":              p.state,
        "district":           p.district,
        "village":            p.village,
        "preferred_language": p.language,
        "crops_grown":        p.crops_grown,
        "farm_size":          p.farm_size,
        "primary_crop":       p.primary_crop,
        "created_at":         p.created_at,
        "updated_at":         p.updated_at,
    }


# ── POST /profile ─────────────────────────────────────────────

@router.post("")
def create_profile(
    body:         ProfileCreateRequest,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Create a farmer profile for the logged-in user.

    - Requires Bearer token in Authorization header.
    - One profile per user — returns error if profile already exists.
    - full_name is the only required field; all others are optional.
    - crops_grown accepts comma-separated string: "wheat,rice,sugarcane"
    """
    user_id = current_user["user_id"]

    # Guard: profile already exists for this user
    existing = db.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).first()

    if existing:
        return {
            "success": False,
            "message": "Profile पहले से बना हुआ है। Update करने के लिए PUT /profile use करें।",
            "data":    {}
        }

    # Build new profile
    profile = UserProfile(
        user_id      = user_id,
        name         = body.full_name,
        phone_number = body.phone_number,
        state        = body.state,
        district     = body.district,
        village      = body.village,
        language     = body.preferred_language or "hindi",
        crops_grown  = body.crops_grown,
        farm_size    = body.farm_size,
        primary_crop = body.crops_grown.split(",")[0].strip()
                       if body.crops_grown else "Wheat",
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return {
        "success": True,
        "message": "Profile बना दिया गया।",
        "data":    _profile_to_dict(profile),
    }


# ── PUT /profile ──────────────────────────────────────────────

@router.put("")
def update_profile(
    body:         ProfileUpdateRequest,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Update the logged-in user's farmer profile.

    - Requires Bearer token in Authorization header.
    - Only fields present in the request body are updated.
    - Returns error if profile doesn't exist yet (use POST first).
    - crops_grown update also syncs primary_crop automatically.
    """
    user_id = current_user["user_id"]

    # Guard: profile must exist before updating
    profile = db.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).first()

    if not profile:
        return {
            "success": False,
            "message": "Profile नहीं मिला। पहले POST /profile से profile बनाएं।",
            "data":    {}
        }

    # Apply only the fields the caller actually sent
    if body.full_name          is not None: profile.name         = body.full_name
    if body.phone_number       is not None: profile.phone_number = body.phone_number
    if body.state              is not None: profile.state        = body.state
    if body.district           is not None: profile.district     = body.district
    if body.village            is not None: profile.village      = body.village
    if body.preferred_language is not None: profile.language     = body.preferred_language
    if body.farm_size          is not None: profile.farm_size    = body.farm_size

    if body.crops_grown is not None:
        profile.crops_grown  = body.crops_grown
        first = body.crops_grown.split(",")[0].strip()
        if first:
            profile.primary_crop = first

    profile.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(profile)

    return {
        "success": True,
        "message": "Profile update हो गया।",
        "data":    _profile_to_dict(profile),
    }


# ── GET /profile ──────────────────────────────────────────────

@router.get("")
def get_profile(
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Fetch the logged-in user's farmer profile.

    - Requires Bearer token in Authorization header.
    - Returns full profile data if found.
    - Returns clear Hindi error if profile not yet created.
    """
    user_id = current_user["user_id"]

    profile = db.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).first()

    if not profile:
        return {
            "success": False,
            "message": "Profile नहीं मिला। पहले POST /profile से profile बनाएं।",
            "data":    {}
        }

    return {
        "success": True,
        "message": "",
        "data":    _profile_to_dict(profile),
    }