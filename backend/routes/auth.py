# ============================================================
# backend/routes/auth.py
# KrashiMitra — Auth + Profile Router
# ============================================================
# COMPATIBILITY FIX:
#   All `X | None` replaced with Optional[X] — works on
#   Python 3.8, 3.9, 3.10, 3.11, 3.12
#
# ENDPOINTS:
#   POST /signup
#   POST /login
#   POST /verify-otp
#   POST /resend-otp
#   POST /forgot-password
#   POST /reset-password
#   GET  /me
#   GET  /profile       ← frontend calls this after login
#   PUT  /profile       ← frontend saveProfile()
#   POST /profile       ← frontend saveProfile() fallback
#   POST /user          ← legacy profile CRUD (unchanged)
#   GET  /user/{id}     ← legacy
#   PUT  /user/{id}     ← legacy
#   GET  /users         ← legacy
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from backend.database.db import User, UserProfile, get_db
from backend.utils.auth_utils import (
    hash_password,
    verify_password,
    validate_password_strength,
    generate_otp,
    otp_expiry_time,
    is_otp_expired,
    send_otp_email,
    create_access_token,
    get_current_user,
)

router = APIRouter()


# ── Request Models ───────────────────────────────────────────

class SignupRequest(BaseModel):
    name:     str
    email:    EmailStr
    password: str

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str

class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp:   str

class ResendOtpRequest(BaseModel):
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email:        EmailStr
    otp:          str
    new_password: str

class ProfileUpdateRequest(BaseModel):
    """Matches exactly what frontend saveProfile() sends."""
    full_name:          Optional[str] = None
    village:            Optional[str] = None
    district:           Optional[str] = None
    crops_grown:        Optional[str] = None
    preferred_language: Optional[str] = None

# Legacy profile models — unchanged
class UserProfileCreate(BaseModel):
    name:         str
    village:      Optional[str] = None
    district:     Optional[str] = None
    primary_crop: str = "Wheat"
    language:     str = "english"

class UserProfileUpdate(BaseModel):
    name:         Optional[str] = None
    village:      Optional[str] = None
    district:     Optional[str] = None
    primary_crop: Optional[str] = None
    language:     Optional[str] = None


# ── HELPERS ──────────────────────────────────────────────────

def _profile_response(user: User) -> dict:
    """Build profile dict matching what frontend applyProfile() reads."""
    return {
        "id":                 user.id,
        "full_name":          user.name,
        "name":               user.name,
        "email":              user.email,
        "village":            getattr(user, "village",      None),
        "district":           getattr(user, "district",     None),
        "primary_crop":       getattr(user, "primary_crop", None),
        "crops_grown":        getattr(user, "primary_crop", None),
        "preferred_language": getattr(user, "preferred_language", "hindi"),
        "is_verified":        user.is_verified,
        "created_at":         str(user.created_at),
    }


# ── AUTH ENDPOINTS ───────────────────────────────────────────

@router.post("/signup")
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    try:
        # Validate password strength first
        err = validate_password_strength(body.password)
        if err:
            return {"success": False, "message": err, "data": {}}

        existing = db.query(User).filter(User.email == body.email).first()
        if existing:
            if existing.is_verified:
                return {"success": False, "message": "यह email पहले से registered है।", "data": {}}
            # Resend OTP for unverified accounts
            otp                 = generate_otp()
            existing.otp        = otp
            existing.otp_expiry = otp_expiry_time()
            db.commit()
            email_sent = send_otp_email(body.email, otp, purpose="verification")
            return {
                "success": True,
                "message": "OTP दोबारा भेजा गया। कृपया email verify करें।",
                "data":    {"email_sent": email_sent}
            }

        otp      = generate_otp()
        new_user = User(
            name               = body.name,
            email              = body.email,
            hashed_password    = hash_password(body.password),
            is_verified        = False,
            otp                = otp,
            otp_expiry         = otp_expiry_time(),
            preferred_language = "hindi",
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # Email failure must NEVER cause 500 — user is already saved
        try:
            email_sent = send_otp_email(body.email, otp, purpose="verification")
        except Exception:
            email_sent = False

        if not email_sent:
            # Dev mode: OTP is printed to terminal — check uvicorn console
            return {
                "success": True,
                "message": "Account बना दिया गया। OTP terminal में print हुआ है (SMTP not configured)।",
                "data":    {"email_sent": False}
            }
        return {"success": True, "message": "OTP sent", "data": {}}

    except Exception as e:
        raise HTTPException(status_code=500, detail="Signup failed: " + str(e))


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.email == body.email).first()
        if not user:
            return {"success": False, "message": "Email या password गलत है।", "data": {}}
        if not user.is_verified:
            return {"success": False, "message": "कृपया पहले अपना email verify करें।", "data": {}}
        if not verify_password(body.password, user.hashed_password):
            return {"success": False, "message": "Email या password गलत है।", "data": {}}

        token = create_access_token(user_id=user.id, email=user.email)
        return {"success": True, "message": "Login successful", "data": {"token": token}}

    except Exception as e:
        raise HTTPException(status_code=500, detail="Login failed: " + str(e))


@router.post("/verify-otp")
def verify_otp(body: VerifyOtpRequest, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.email == body.email).first()
        if not user:
            return {"success": False, "message": "Email registered नहीं है।", "data": {}}
        if user.is_verified:
            return {"success": True, "message": "Email पहले से verified है। Login करें।", "data": {}}
        if not user.otp or not user.otp_expiry:
            return {"success": False, "message": "OTP नहीं मिला। Signup दोबारा करें।", "data": {}}
        if is_otp_expired(user.otp_expiry):
            return {"success": False, "message": "OTP expire हो गया। Signup दोबारा करें।", "data": {}}
        if user.otp != body.otp.strip():
            return {"success": False, "message": "OTP गलत है। दोबारा check करें।", "data": {}}

        user.is_verified = True
        user.otp         = None
        user.otp_expiry  = None
        db.commit()
        return {"success": True, "message": "Email verify हो गया। अब login करें।", "data": {}}

    except Exception as e:
        raise HTTPException(status_code=500, detail="OTP verification failed: " + str(e))


@router.post("/resend-otp")
def resend_otp(body: ResendOtpRequest, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.email == body.email).first()
        if not user:
            return {"success": True, "message": "अगर यह email registered है तो OTP भेज दिया गया है।", "data": {}}
        if user.is_verified:
            return {"success": False, "message": "यह email पहले से verified है। Login करें।", "data": {}}

        otp             = generate_otp()
        user.otp        = otp
        user.otp_expiry = otp_expiry_time()
        db.commit()

        email_sent = send_otp_email(body.email, otp, purpose="verification")
        if not email_sent:
            return {"success": False, "message": "OTP email नहीं पहुंची। थोड़ी देर बाद दोबारा try करें।", "data": {}}
        return {"success": True, "message": "अगर यह email registered है तो OTP भेज दिया गया है।", "data": {}}

    except Exception as e:
        raise HTTPException(status_code=500, detail="Resend OTP failed: " + str(e))


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.email == body.email).first()
        if not user:
            return {"success": True, "message": "अगर यह email registered है तो OTP भेज दिया गया है।", "data": {}}
        if not user.is_verified:
            return {"success": False, "message": "कृपया पहले अपना email verify करें।", "data": {}}

        otp             = generate_otp()
        user.otp        = otp
        user.otp_expiry = otp_expiry_time()
        db.commit()

        email_sent = send_otp_email(body.email, otp, purpose="reset")
        if not email_sent:
            return {"success": False, "message": "OTP email नहीं पहुंची। थोड़ी देर बाद दोबारा try करें।", "data": {}}
        return {"success": True, "message": "अगर यह email registered है तो OTP भेज दिया गया है।", "data": {}}

    except Exception as e:
        raise HTTPException(status_code=500, detail="Forgot password failed: " + str(e))


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.email == body.email).first()
        if not user:
            return {"success": False, "message": "Email registered नहीं है।", "data": {}}
        if not user.otp or not user.otp_expiry:
            return {"success": False, "message": "Reset OTP नहीं मिला। पहले Forgot Password करें।", "data": {}}
        if is_otp_expired(user.otp_expiry):
            return {"success": False, "message": "OTP expire हो गया। Forgot Password दोबारा करें।", "data": {}}
        if user.otp != body.otp.strip():
            return {"success": False, "message": "OTP गलत है। दोबारा check करें।", "data": {}}

        err = validate_password_strength(body.new_password)
        if err:
            return {"success": False, "message": err, "data": {}}

        user.hashed_password = hash_password(body.new_password)
        user.otp             = None
        user.otp_expiry      = None
        db.commit()
        return {"success": True, "message": "Password reset हो गया। अब login करें।", "data": {}}

    except Exception as e:
        raise HTTPException(status_code=500, detail="Reset password failed: " + str(e))


# ── PROFILE ENDPOINTS ─────────────────────────────────────────
# Frontend calls GET/PUT/POST /profile — these MUST exist
# or fetch() throws a network error mis-reported as "API not running"

@router.get("/me")
@router.get("/profile")
def get_profile(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """GET /profile — called by loadUserProfile() on every page load."""
    try:
        user = db.query(User).filter(User.id == current_user["user_id"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User नहीं मिला।")
        return {"success": True, "message": "", "data": _profile_response(user)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Profile fetch failed: " + str(e))


@router.put("/profile")
def update_profile(
    body: ProfileUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """PUT /profile — called by saveProfile() in frontend."""
    try:
        user = db.query(User).filter(User.id == current_user["user_id"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User नहीं मिला।")

        if body.full_name is not None:
            user.name = body.full_name
        if body.preferred_language is not None:
            user.preferred_language = body.preferred_language
        if body.village is not None and hasattr(user, "village"):
            user.village = body.village
        if body.district is not None and hasattr(user, "district"):
            user.district = body.district
        if body.crops_grown is not None and hasattr(user, "primary_crop"):
            user.primary_crop = body.crops_grown

        db.commit()
        db.refresh(user)
        return {"success": True, "message": "Profile updated।", "data": _profile_response(user)}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Profile update failed: " + str(e))


@router.post("/profile")
def create_profile(
    body: ProfileUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """POST /profile — fallback upsert from frontend saveProfile()."""
    try:
        user = db.query(User).filter(User.id == current_user["user_id"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User नहीं मिला।")

        if body.full_name is not None:
            user.name = body.full_name
        if body.preferred_language is not None:
            user.preferred_language = body.preferred_language
        if body.village is not None and hasattr(user, "village"):
            user.village = body.village
        if body.district is not None and hasattr(user, "district"):
            user.district = body.district
        if body.crops_grown is not None and hasattr(user, "primary_crop"):
            user.primary_crop = body.crops_grown

        db.commit()
        db.refresh(user)
        return {"success": True, "message": "Profile saved।", "data": _profile_response(user)}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Profile save failed: " + str(e))


# ── LEGACY PROFILE CRUD (UNCHANGED) ──────────────────────────

@router.post("/user")
def create_user(body: UserProfileCreate, db: Session = Depends(get_db)):
    user = UserProfile(
        name         = body.name,
        village      = body.village,
        district     = body.district,
        primary_crop = body.primary_crop,
        language     = body.language
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Profile created.", "user": {
        "id": user.id, "name": user.name, "village": user.village,
        "district": user.district, "primary_crop": user.primary_crop,
        "language": user.language, "created_at": str(user.created_at)
    }}


@router.get("/user/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(UserProfile).filter(UserProfile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {
        "id": user.id, "name": user.name, "village": user.village,
        "district": user.district, "primary_crop": user.primary_crop,
        "language": user.language, "created_at": str(user.created_at)
    }


@router.put("/user/{user_id}")
def update_user(user_id: int, body: UserProfileUpdate, db: Session = Depends(get_db)):
    user = db.query(UserProfile).filter(UserProfile.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if body.name:         user.name         = body.name
    if body.village:      user.village      = body.village
    if body.district:     user.district     = body.district
    if body.primary_crop: user.primary_crop = body.primary_crop
    if body.language:     user.language     = body.language
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return {"message": "Profile updated.", "user": {
        "id": user.id, "name": user.name, "village": user.village,
        "district": user.district, "primary_crop": user.primary_crop,
        "language": user.language
    }}


@router.get("/users")
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(UserProfile).all()
    return {"total": len(users), "users": [
        {"id": u.id, "name": u.name, "district": u.district, "primary_crop": u.primary_crop}
        for u in users
    ]}