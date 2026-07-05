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

import os
import httpx

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
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

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()

MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_MINUTES = 15
_login_attempts = {}


def _login_key(email: str) -> str:
    return (email or "").strip().lower()


def _norm_email(email: str) -> str:
    """Canonical form for storing/comparing emails: trimmed + lowercased."""
    return (email or "").strip().lower()


def _ensure_profile(db: Session, user: User):
    """Every verified account gets a user_profiles row (created lazily here,
    prefilled from signup data). Farm fields stay NULL until the farmer fills
    them — this just guarantees the users ↔ user_profiles 1:1 for verified
    accounts. Caller commits."""
    exists = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if exists:
        return
    db.add(UserProfile(
        user_id  = user.id,
        name     = user.name,
        language = user.preferred_language or "hindi",
    ))


def _find_user_by_email(db: Session, email: str) -> Optional[User]:
    """Case-insensitive email lookup.

    Emails were historically stored with whatever casing the user typed, so
    `User.email == body.email` missed `VPS@Gmail.com` vs `vps@gmail.com` —
    login failed and re-signup created a duplicate account. Match
    case-insensitively and, if legacy duplicates exist for the same address,
    prefer the verified (real) account over an unverified husk.
    """
    return (
        db.query(User)
        .filter(func.lower(User.email) == _norm_email(email))
        .order_by(User.is_verified.desc(), User.id.asc())
        .first()
    )


def _attempt_state(email: str) -> dict:
    key = _login_key(email)
    now = datetime.utcnow()
    state = _login_attempts.get(key)
    if not state or state["reset_at"] <= now:
        state = {"count": 0, "reset_at": now + timedelta(minutes=LOGIN_WINDOW_MINUTES)}
        _login_attempts[key] = state
    return state


def _blocked_login_response(email: str) -> Optional[dict]:
    state = _attempt_state(email)
    if state["count"] < MAX_LOGIN_ATTEMPTS:
        return None
    retry_after = max(1, int((state["reset_at"] - datetime.utcnow()).total_seconds()))
    return {
        "success": False,
        "message": f"Too many wrong attempts. Please try again after {retry_after // 60 + 1} minutes or reset password.",
        "data": {
            "locked": True,
            "forgot_available": True,
            "retry_after_seconds": retry_after,
        },
    }


def _record_failed_login(email: str) -> dict:
    state = _attempt_state(email)
    state["count"] += 1
    remaining = max(0, MAX_LOGIN_ATTEMPTS - state["count"])
    return {
        "attempts_remaining": remaining,
        "forgot_available": True,
        "locked": remaining == 0,
        "retry_after_seconds": max(1, int((state["reset_at"] - datetime.utcnow()).total_seconds())),
    }


def _clear_failed_login(email: str):
    _login_attempts.pop(_login_key(email), None)


# ── Request Models ───────────────────────────────────────────

class SignupRequest(BaseModel):
    name:     str
    email:    EmailStr
    password: str
    confirm_password: Optional[str] = None

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
    confirm_password: Optional[str] = None

class GoogleAuthRequest(BaseModel):
    id_token: str

class ProfileUpdateRequest(BaseModel):
    """Matches exactly what frontend saveProfile() sends."""
    full_name:          Optional[str] = None
    phone_number:       Optional[str] = None
    state:              Optional[str] = None
    village:            Optional[str] = None
    district:           Optional[str] = None
    farm_size:          Optional[str] = None
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


# (Profile-building helpers were removed along with the duplicate /profile
#  handlers — the canonical profile logic lives in routes/profile.py.)


# ── AUTH ENDPOINTS ───────────────────────────────────────────

@router.post("/signup")
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    try:
        if body.confirm_password is not None and body.password != body.confirm_password:
            return {"success": False, "message": "Password और Confirm Password match नहीं कर रहे।", "data": {}}

        # Validate password strength first
        err = validate_password_strength(body.password)
        if err:
            return {"success": False, "message": err, "data": {}}

        existing = _find_user_by_email(db, body.email)
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
            email              = _norm_email(body.email),
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
        blocked = _blocked_login_response(body.email)
        if blocked:
            return blocked

        user = _find_user_by_email(db, body.email)
        if not user:
            data = _record_failed_login(body.email)
            return {"success": False, "message": "Email या password गलत है। Forgot password use कर सकते हैं।", "data": data}
        if not user.is_verified:
            return {"success": False, "message": "कृपया पहले अपना email verify करें।", "data": {}}
        if not verify_password(body.password, user.hashed_password):
            data = _record_failed_login(body.email)
            return {"success": False, "message": "Email या password गलत है। Forgot password use कर सकते हैं।", "data": data}

        _clear_failed_login(body.email)
        token = create_access_token(user_id=user.id, email=user.email)
        return {"success": True, "message": "Login successful", "data": {"token": token}}

    except Exception as e:
        raise HTTPException(status_code=500, detail="Login failed: " + str(e))


@router.post("/verify-otp")
def verify_otp(body: VerifyOtpRequest, db: Session = Depends(get_db)):
    try:
        user = _find_user_by_email(db, body.email)
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
        _ensure_profile(db, user)   # verified user → profile row exists
        db.commit()
        return {"success": True, "message": "Email verify हो गया। अब login करें।", "data": {}}

    except Exception as e:
        raise HTTPException(status_code=500, detail="OTP verification failed: " + str(e))


@router.post("/resend-otp")
def resend_otp(body: ResendOtpRequest, db: Session = Depends(get_db)):
    try:
        user = _find_user_by_email(db, body.email)
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
        user = _find_user_by_email(db, body.email)
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
        if body.confirm_password is not None and body.new_password != body.confirm_password:
            return {"success": False, "message": "New password और Confirm Password match नहीं कर रहे।", "data": {}}

        user = _find_user_by_email(db, body.email)
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
        _clear_failed_login(body.email)
        return {"success": True, "message": "Password reset हो गया। अब login करें।", "data": {}}

    except Exception as e:
        raise HTTPException(status_code=500, detail="Reset password failed: " + str(e))


# ── GOOGLE OAUTH ─────────────────────────────────────────────

@router.post("/auth/google")
def google_login(body: GoogleAuthRequest, db: Session = Depends(get_db)):
    """Verify a Google id_token, then find-or-create user and return a JWT."""
    try:
        resp = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": body.id_token},
            timeout=10,
        )
        if resp.status_code != 200:
            return {"success": False, "message": "Google login verify नहीं हो पाया। दोबारा try करें।", "data": {}}

        info = resp.json()

        # Ensure token was issued for our application
        if GOOGLE_CLIENT_ID and info.get("aud") != GOOGLE_CLIENT_ID:
            return {"success": False, "message": "Google token mismatch। सही account से try करें।", "data": {}}

        email     = (info.get("email") or "").strip().lower()
        google_id = (info.get("sub")   or "").strip()

        if not email:
            return {"success": False, "message": "Google account से email नहीं मिली।", "data": {}}
        if not info.get("email_verified"):
            return {"success": False, "message": "Google email verified नहीं है।", "data": {}}

        name = info.get("name") or email.split("@")[0]

        # Look up by google_id first (handles email-change edge case), fallback to email
        user = None
        if google_id:
            user = db.query(User).filter(User.google_id == google_id).first()
        if not user:
            user = _find_user_by_email(db, email)

        if not user:
            user = User(
                name               = name,
                email              = email,
                hashed_password    = "GOOGLE_OAUTH",  # sentinel — bcrypt never matches this
                is_verified        = True,
                auth_provider      = "google",
                google_id          = google_id,
                preferred_language = "hindi",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            _ensure_profile(db, user)   # Google users are verified from the start
            db.commit()
        else:
            # Patch any missing fields on returning Google user
            if not user.google_id and google_id:
                user.google_id = google_id
            if not user.is_verified:
                user.is_verified = True
            if user.auth_provider != "google" and not user.hashed_password.startswith("$2"):
                user.auth_provider = "google"
            _ensure_profile(db, user)   # verified user → profile row exists
            db.commit()

        _clear_failed_login(email)
        token = create_access_token(user_id=user.id, email=user.email)
        return {"success": True, "message": "Google login successful", "data": {"token": token}}

    except httpx.TimeoutException:
        return {"success": False, "message": "Google server से response नहीं मिला। दोबारा try करें।", "data": {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Google login failed: " + str(e))


# ── /profile and /me ─────────────────────────────────────────
# Intentionally NOT defined in this router. The dedicated full-field
# profile router (backend/routes/profile.py, prefix="/profile") owns
# GET/POST/PUT /profile, so every farmer-profile field is persisted and
# returned. Earlier this file registered its own /profile handlers that —
# because auth_router is included before profile_router — shadowed the real
# ones and silently dropped most fields on save. They were removed to fix
# that. Do not re-add /profile here.


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

print("✅ auth.py loaded successfully")
