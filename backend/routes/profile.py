# ============================================================
# backend/routes/profile.py
# KrashiMitra — Farmer Profile Router
# ============================================================

import base64
import io
import logging
import os
import uuid
from pathlib import Path
from PIL import Image, ImageOps
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from backend.database.db import UserProfile, User, BazarPost, BazarFollow, get_db, acct
from backend.utils.auth_utils import get_current_user
from backend.utils.security import assert_media_matches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])

# ── Profile Pic Upload Storage ───────────────────────────────
PROFILE_UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads" / "avatar"
PROFILE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB for profile avatar


# ── Request Models ───────────────────────────────────────────

class ProfileCreateRequest(BaseModel):
    # Personal
    full_name:            str
    phone_number:         Optional[str]  = None
    whatsapp_number:      Optional[str]  = None
    dob:                  Optional[str]  = None
    gender:               Optional[str]  = None
    education:            Optional[str]  = None
    occupation:           Optional[str]  = None
    farming_experience:   Optional[str]  = None
    family_size:          Optional[int]  = None

    # Location
    state:                Optional[str]  = None
    district:             Optional[str]  = None
    tehsil:               Optional[str]  = None
    village:              Optional[str]  = None
    pin_code:             Optional[str]  = None
    nearest_mandi:        Optional[str]  = None

    # Farm
    farm_size:            Optional[str]  = None
    farm_size_unit:       Optional[str]  = "acres"
    land_ownership:       Optional[str]  = None
    soil_type:            Optional[str]  = None
    irrigation_type:      Optional[str]  = None
    khasra_number:        Optional[str]  = None

    # Equipment
    eq_tractor:           Optional[bool] = False
    eq_pump:              Optional[bool] = False
    eq_thresher:          Optional[bool] = False
    eq_sprayer:           Optional[bool] = False
    eq_harvester:         Optional[bool] = False
    eq_none:              Optional[bool] = False

    # Crops
    primary_crop:         Optional[str]  = None
    crops_grown:          Optional[str]  = None
    farming_season:       Optional[str]  = None
    farming_type:         Optional[str]  = None
    yield_per_acre:       Optional[str]  = None
    crop_problems:        Optional[str]  = None

    # Schemes & Finance
    pm_kisan_registered:  Optional[bool] = False
    has_kcc:              Optional[bool] = False
    aadhaar_linked:       Optional[bool] = False
    fasal_bima:           Optional[bool] = False
    bank_name:            Optional[str]  = None
    annual_income:        Optional[str]  = None

    # Preferences
    preferred_language:   Optional[str]  = "hindi"
    advisory_type:        Optional[str]  = None
    special_needs:        Optional[str]  = None

    # Notifications
    notif_weather:        Optional[bool] = False
    notif_mandi:          Optional[bool] = False
    notif_scheme:         Optional[bool] = False
    notif_pest:           Optional[bool] = False
    notif_tips:           Optional[bool] = False
    notif_none:           Optional[bool] = False

    # Frontend sends "" for blank number inputs; treat blank as None so the
    # whole save doesn't 422 when family_size is left empty.
    @field_validator("family_size", "dob", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class ProfileUpdateRequest(BaseModel):
    # All fields optional — only sent fields get updated
    full_name:            Optional[str]  = None
    phone_number:         Optional[str]  = None
    whatsapp_number:      Optional[str]  = None
    dob:                  Optional[str]  = None
    gender:               Optional[str]  = None
    education:            Optional[str]  = None
    occupation:           Optional[str]  = None
    farming_experience:   Optional[str]  = None
    family_size:          Optional[int]  = None

    state:                Optional[str]  = None
    district:             Optional[str]  = None
    tehsil:               Optional[str]  = None
    village:              Optional[str]  = None
    pin_code:             Optional[str]  = None
    nearest_mandi:        Optional[str]  = None

    farm_size:            Optional[str]  = None
    farm_size_unit:       Optional[str]  = None
    land_ownership:       Optional[str]  = None
    soil_type:            Optional[str]  = None
    irrigation_type:      Optional[str]  = None
    khasra_number:        Optional[str]  = None

    eq_tractor:           Optional[bool] = None
    eq_pump:              Optional[bool] = None
    eq_thresher:          Optional[bool] = None
    eq_sprayer:           Optional[bool] = None
    eq_harvester:         Optional[bool] = None
    eq_none:              Optional[bool] = None

    primary_crop:         Optional[str]  = None
    crops_grown:          Optional[str]  = None
    farming_season:       Optional[str]  = None
    farming_type:         Optional[str]  = None
    yield_per_acre:       Optional[str]  = None
    crop_problems:        Optional[str]  = None

    pm_kisan_registered:  Optional[bool] = None
    has_kcc:              Optional[bool] = None
    aadhaar_linked:       Optional[bool] = None
    fasal_bima:           Optional[bool] = None
    bank_name:            Optional[str]  = None
    annual_income:        Optional[str]  = None

    preferred_language:   Optional[str]  = None
    advisory_type:        Optional[str]  = None
    special_needs:        Optional[str]  = None

    notif_weather:        Optional[bool] = None
    notif_mandi:          Optional[bool] = None
    notif_scheme:         Optional[bool] = None
    notif_pest:           Optional[bool] = None
    notif_tips:           Optional[bool] = None
    notif_none:           Optional[bool] = None

    # Frontend sends "" for blank number inputs; treat blank as None so the
    # whole save doesn't 422 when family_size is left empty.
    @field_validator("family_size", "dob", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class LocationUpdateRequest(BaseModel):
    """Auto-detected device location from the browser Geolocation API,
    reverse-geocoded client-side. `location` is a readable 'जिला, राज्य'."""
    lat:      float
    lon:      float
    location: Optional[str] = None

    @field_validator("lat")
    @classmethod
    def _valid_lat(cls, v):
        if v is None or not (-90.0 <= v <= 90.0):
            raise ValueError("lat out of range")
        return v

    @field_validator("lon")
    @classmethod
    def _valid_lon(cls, v):
        if v is None or not (-180.0 <= v <= 180.0):
            raise ValueError("lon out of range")
        return v


# ── Helper ───────────────────────────────────────────────────

def _profile_to_dict(p: UserProfile) -> dict:
    return {
        "id":                   p.id,
        "user_id":              p.user_id,
        # Personal
        "full_name":            p.name,
        "phone_number":         p.phone_number,
        "whatsapp_number":      p.whatsapp_number,
        "dob":                  p.dob,
        "gender":               p.gender,
        "education":            p.education,
        "occupation":           p.occupation,
        "farming_experience":   p.farming_experience,
        "family_size":          p.family_size,
        "avatar_url":           p.avatar_url,
        # Location
        "state":                p.state,
        "district":             p.district,
        "tehsil":               p.tehsil,
        "village":              p.village,
        "pin_code":             p.pin_code,
        "nearest_mandi":        p.nearest_mandi,
        # Auto-detected device location (separate from the address above)
        "geo_lat":              p.geo_lat,
        "geo_lon":              p.geo_lon,
        "geo_location":         p.geo_location,
        "geo_updated_at":       p.geo_updated_at,
        # Farm
        "farm_size":            p.farm_size,
        "farm_size_unit":       p.farm_size_unit,
        "land_ownership":       p.land_ownership,
        "soil_type":            p.soil_type,
        "irrigation_type":      p.irrigation_type,
        "khasra_number":        p.khasra_number,
        # Equipment
        "eq_tractor":           p.eq_tractor,
        "eq_pump":              p.eq_pump,
        "eq_thresher":          p.eq_thresher,
        "eq_sprayer":           p.eq_sprayer,
        "eq_harvester":         p.eq_harvester,
        "eq_none":              p.eq_none,
        # Crops
        "primary_crop":         p.primary_crop,
        "crops_grown":          p.crops_grown,
        "farming_season":       p.farming_season,
        "farming_type":         p.farming_type,
        "yield_per_acre":       p.yield_per_acre,
        "crop_problems":        p.crop_problems,
        # Schemes
        "pm_kisan_registered":  p.pm_kisan_registered,
        "has_kcc":              p.has_kcc,
        "aadhaar_linked":       p.aadhaar_linked,
        "fasal_bima":           p.fasal_bima,
        "bank_name":            p.bank_name,
        "annual_income":        p.annual_income,
        # Preferences
        "preferred_language":   p.language,
        "advisory_type":        p.advisory_type,
        "special_needs":        p.special_needs,
        # Notifications
        "notif_weather":        p.notif_weather,
        "notif_mandi":          p.notif_mandi,
        "notif_scheme":         p.notif_scheme,
        "notif_pest":           p.notif_pest,
        "notif_tips":           p.notif_tips,
        "notif_none":           p.notif_none,
        "created_at":           p.created_at,
        "updated_at":           p.updated_at,
    }


def _derive_primary_crop(body_primary_crop: Optional[str], crops_grown: Optional[str]) -> Optional[str]:
    if body_primary_crop and body_primary_crop.strip():
        return body_primary_crop.strip()
    if crops_grown:
        first = crops_grown.split(",")[0].strip()
        if first:
            return first
    return None  # no fabricated default — stays NULL until the user picks one


def _sync_user(user: User, profile: UserProfile, db: Session):
    """Keep the basic fields on the users table in sync with user_profiles.
    Avatar is deliberately NOT mirrored — user_profiles is its sole home."""
    # The profile form is the ONLY place a name can be edited — nothing else in
    # the backend writes users.name after signup — so without this line the two
    # tables drifted permanently the first time a farmer corrected his own name
    # (users kept the signup/Google value, user_profiles got the real one).
    # Direction is profile → users, matching alerts.display_name(): the name he
    # filled in wins over whatever the signup form or Google supplied.
    user.name               = (profile.name or "").strip() or user.name
    user.preferred_language = profile.language or user.preferred_language
    user.village            = profile.village  or user.village
    user.district           = profile.district or user.district
    user.primary_crop       = profile.primary_crop or user.primary_crop
    db.add(user)


# ── POST /profile ─────────────────────────────────────────────

@router.post("")
def create_profile(
    body:         ProfileCreateRequest,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    user_id = current_user["user_id"]

    existing = db.query(UserProfile).filter(UserProfile.user_id == acct(user_id)).first()
    if existing:
        return {
            "success": False,
            "message": "Profile पहले से बना हुआ है। Update करने के लिए PUT /profile use करें।",
            "data":    {}
        }

    account = db.query(User).filter(User.id == user_id).first()
    if not account or account.user_id is None:
        raise HTTPException(
            status_code=409,
            detail="खाता अभी verify नहीं हुआ — profile नहीं बन सका।",
        )

    profile = UserProfile(
        # The account number, in both columns. NOT users.id — see
        # UserProfile.user_id in backend/database/db.py.
        id                  = account.user_id,
        user_id             = account.user_id,
        # Personal
        name                = body.full_name,
        phone_number        = body.phone_number,
        whatsapp_number     = body.whatsapp_number,
        dob                 = body.dob,
        gender              = body.gender,
        education           = body.education,
        occupation          = body.occupation,
        farming_experience  = body.farming_experience,
        family_size         = body.family_size,
        # Location
        state               = body.state,
        district            = body.district,
        tehsil              = body.tehsil,
        village             = body.village,
        pin_code            = body.pin_code,
        nearest_mandi       = body.nearest_mandi,
        # Farm
        farm_size           = body.farm_size,
        farm_size_unit      = body.farm_size_unit or "acres",
        land_ownership      = body.land_ownership,
        soil_type           = body.soil_type,
        irrigation_type     = body.irrigation_type,
        khasra_number       = body.khasra_number,
        # Equipment
        eq_tractor          = body.eq_tractor  or False,
        eq_pump             = body.eq_pump     or False,
        eq_thresher         = body.eq_thresher or False,
        eq_sprayer          = body.eq_sprayer  or False,
        eq_harvester        = body.eq_harvester or False,
        eq_none             = body.eq_none     or False,
        # Crops
        primary_crop        = _derive_primary_crop(body.primary_crop, body.crops_grown),
        crops_grown         = body.crops_grown,
        farming_season      = body.farming_season,
        farming_type        = body.farming_type,
        yield_per_acre      = body.yield_per_acre,
        crop_problems       = body.crop_problems,
        # Schemes
        pm_kisan_registered = body.pm_kisan_registered or False,
        has_kcc             = body.has_kcc             or False,
        aadhaar_linked      = body.aadhaar_linked       or False,
        fasal_bima          = body.fasal_bima           or False,
        bank_name           = body.bank_name,
        annual_income       = body.annual_income,
        # Preferences
        language            = body.preferred_language or "hindi",
        advisory_type       = body.advisory_type,
        special_needs       = body.special_needs,
        # Notifications
        notif_weather       = body.notif_weather or False,
        notif_mandi         = body.notif_mandi   or False,
        notif_scheme        = body.notif_scheme  or False,
        notif_pest          = body.notif_pest    or False,
        notif_tips          = body.notif_tips    or False,
        notif_none          = body.notif_none    or False,
    )

    db.add(profile)

    user = db.query(User).filter(User.id == user_id).first()
    if user:
        _sync_user(user, profile, db)

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
    user_id = current_user["user_id"]

    profile = db.query(UserProfile).filter(UserProfile.user_id == acct(user_id)).first()
    if not profile:
        return {
            "success": False,
            "message": "Profile नहीं मिला। पहले POST /profile से profile बनाएं।",
            "data":    {}
        }

    # Apply only fields the caller actually sent (not None)
    str_map = {
        "full_name":          "name",
        "phone_number":       "phone_number",
        "whatsapp_number":    "whatsapp_number",
        "dob":                "dob",
        "gender":             "gender",
        "education":          "education",
        "occupation":         "occupation",
        "farming_experience": "farming_experience",
        "state":              "state",
        "district":           "district",
        "tehsil":             "tehsil",
        "village":            "village",
        "pin_code":           "pin_code",
        "nearest_mandi":      "nearest_mandi",
        "farm_size":          "farm_size",
        "farm_size_unit":     "farm_size_unit",
        "land_ownership":     "land_ownership",
        "soil_type":          "soil_type",
        "irrigation_type":    "irrigation_type",
        "khasra_number":      "khasra_number",
        "primary_crop":       "primary_crop",
        "crops_grown":        "crops_grown",
        "farming_season":     "farming_season",
        "farming_type":       "farming_type",
        "yield_per_acre":     "yield_per_acre",
        "crop_problems":      "crop_problems",
        "bank_name":          "bank_name",
        "annual_income":      "annual_income",
        "preferred_language": "language",
        "advisory_type":      "advisory_type",
        "special_needs":      "special_needs",
    }
    int_map = {"family_size": "family_size"}
    bool_map = {
        "eq_tractor":          "eq_tractor",
        "eq_pump":             "eq_pump",
        "eq_thresher":         "eq_thresher",
        "eq_sprayer":          "eq_sprayer",
        "eq_harvester":        "eq_harvester",
        "eq_none":             "eq_none",
        "pm_kisan_registered": "pm_kisan_registered",
        "has_kcc":             "has_kcc",
        "aadhaar_linked":      "aadhaar_linked",
        "fasal_bima":          "fasal_bima",
        "notif_weather":       "notif_weather",
        "notif_mandi":         "notif_mandi",
        "notif_scheme":        "notif_scheme",
        "notif_pest":          "notif_pest",
        "notif_tips":          "notif_tips",
        "notif_none":          "notif_none",
    }

    for req_field, db_field in str_map.items():
        val = getattr(body, req_field, None)
        if val is not None:
            setattr(profile, db_field, val)

    for req_field, db_field in int_map.items():
        val = getattr(body, req_field, None)
        if val is not None:
            setattr(profile, db_field, val)

    for req_field, db_field in bool_map.items():
        val = getattr(body, req_field, None)
        if val is not None:
            setattr(profile, db_field, val)

    # Re-derive primary_crop if crops_grown changed but primary_crop wasn't explicitly set
    if body.crops_grown is not None and body.primary_crop is None:
        first = body.crops_grown.split(",")[0].strip()
        if first:
            profile.primary_crop = first

    profile.updated_at = datetime.utcnow()

    user = db.query(User).filter(User.id == user_id).first()
    if user:
        _sync_user(user, profile, db)

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
    user_id = current_user["user_id"]

    profile = db.query(UserProfile).filter(UserProfile.user_id == acct(user_id)).first()
    if not profile:
        # No profile yet, but the caller IS authenticated — still return the
        # account email + signup name so the frontend can show them
        # (read-only email, name as prefill) and verify the session maps
        # to a real account.
        acct = db.query(User).filter(User.id == user_id).first()
        return {
            "success": False,
            "message": "Profile नहीं मिला। पहले POST /profile से profile बनाएं।",
            "data": {
                "email":     acct.email if acct else None,
                "full_name": acct.name  if acct else None,
            },
        }

    user = db.query(User).filter(User.id == user_id).first()
    data = _profile_to_dict(profile)
    
    # Query stats for the header card
    data["posts_count"] = db.query(BazarPost).filter(BazarPost.user_id == user_id).count()
    data["followers_count"] = db.query(BazarFollow).filter(BazarFollow.following_id == user_id).count()
    data["following_count"] = db.query(BazarFollow).filter(BazarFollow.follower_id == user_id).count()
    
    if user:
        data["email"]         = user.email
        data["auth_provider"] = user.auth_provider or "email"
        data["verified"]      = bool(user.seller_verified)

    return {
        "success": True,
        "message": "",
        "data":    data,
    }


# ── POST /profile/location — save auto-detected device location ──
# Called by frontend/location.js after the farmer grants the browser
# location permission. Guests (no token) never reach here — they keep
# their location only in localStorage. Auth'd users get it persisted on
# their user_profiles row (alongside the address fields) so weather/mandi
# can personalise across devices.

@router.post("/location")
def update_location(
    body:         LocationUpdateRequest,
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    user_id = current_user["user_id"]

    profile = db.query(UserProfile).filter(UserProfile.user_id == acct(user_id)).first()
    if not profile:
        # Verified users always have a profile (DB trigger), but stay defensive:
        # mint a bare one from the account name so the location never gets lost.
        account = db.query(User).filter(User.id == user_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="User नहीं मिला।")
        if account.user_id is None:
            raise HTTPException(
                status_code=409,
                detail="खाता अभी verify नहीं हुआ — स्थान सेव नहीं हो सका।",
            )
        # id AND user_id are the same account number; never users.id.
        profile = UserProfile(id=account.user_id, user_id=account.user_id,
                              name=account.name,
                              language=account.preferred_language or "hindi")
        db.add(profile)

    profile.geo_lat        = body.lat
    profile.geo_lon        = body.lon
    profile.geo_location   = (body.location or "").strip() or None
    profile.geo_updated_at = datetime.utcnow()
    profile.updated_at     = datetime.utcnow()
    db.commit()

    return {
        "success": True,
        "message": "स्थान सेव हो गया।",
        "data": {
            "geo_lat":      profile.geo_lat,
            "geo_lon":      profile.geo_lon,
            "geo_location": profile.geo_location,
        },
    }


# ── POST /profile/avatar — upload profile picture ────────────

@router.post("/avatar")
async def upload_avatar(
    file:         UploadFile = File(...),
    current_user: dict       = Depends(get_current_user),
    db:           Session    = Depends(get_db),
):
    user_id = current_user["user_id"]
    profile = db.query(UserProfile).filter(UserProfile.user_id == acct(user_id)).first()
    if not profile:
        raise HTTPException(
            status_code=403,
            detail="PROFILE_REQUIRED",
        )

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in IMAGE_EXTS:
        raise HTTPException(400, "केवल photo (jpg/jpeg/png/webp) upload करें।")

    # Read the whole upload into memory (bounded), verifying the magic bytes.
    raw = b""
    first = True
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        if first:
            # Extension says image; the bytes have to agree.
            assert_media_matches(chunk[:16], "image")
            first = False
        raw += chunk
        if len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(
                400,
                f"File बहुत बड़ी है — अधिकतम {MAX_IMAGE_BYTES // (1024*1024)} MB।",
            )

    # Downscale to a small square and re-encode as WebP, then store the image
    # itself (as a base64 data URI) in the DB rather than on disk. Render's free
    # tier has an ephemeral filesystem — anything written to uploads/ is wiped on
    # every restart/redeploy, which is why avatars kept "disappearing" while the
    # DB still held a /uploads/avatar/... path pointing at a now-missing file.
    # A ~256px WebP is only a few KB, so the data URI lives comfortably in the
    # (unbounded) TEXT column and survives restarts.
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)          # honour phone rotation
        img = img.convert("RGB")
        img = ImageOps.fit(img, (256, 256), Image.LANCZOS)  # center-crop to a square
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=80, method=6)
    except Exception as e:
        logger.exception("[profile] avatar processing failed: %s", e)
        raise HTTPException(400, "यह image process नहीं हो पाई। दूसरी photo try करें।")

    data_uri = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    profile.avatar_url = data_uri
    db.commit()

    return {
        "success": True,
        "message": "Profile picture upload हो गया।",
        "data": {
            "avatar_url": data_uri
        }
    }


# ── DELETE /profile/avatar — remove profile picture ──────────

@router.delete("/avatar")
def delete_avatar(
    current_user: dict    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    user_id = current_user["user_id"]
    profile = db.query(UserProfile).filter(UserProfile.user_id == acct(user_id)).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile नहीं मिला।")

    old_avatar = profile.avatar_url
    profile.avatar_url = None
    db.commit()

    # Remove the file from disk (only our own uploads, never external URLs)
    if old_avatar and "/uploads/avatar/" in old_avatar:
        try:
            old_name = old_avatar.split("/uploads/avatar/")[-1]
            (PROFILE_UPLOAD_DIR / old_name).unlink(missing_ok=True)
        except Exception:
            pass

    return {
        "success": True,
        "message": "Profile picture हटा दी गई।",
        "data": {"avatar_url": None},
    }
