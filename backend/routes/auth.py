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
#   POST /auth/google
#
# Profile endpoints (GET/POST/PUT /profile) live in routes/profile.py.
# The unauthenticated legacy CRUD (POST /user, GET|PUT /user/{id}, GET /users)
# was removed — see the note at the bottom of this file.
# ============================================================

import logging
import os
import secrets
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
from backend.utils.security import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

# Per-IP caps. The OTP endpoints each send an email on success, so without a
# limit anyone can use /signup, /resend-otp or /forgot-password to mailbomb a
# third party through our Resend account (and burn its quota). The verify
# endpoints are capped per-IP as well as per-email so a spread-out brute force
# can't sidestep the per-email counter.
_LIMIT_SEND   = rate_limit("otp_send",   5,  15 * 60)   # 5 emails / 15 min / IP
_LIMIT_VERIFY = rate_limit("otp_verify", 20, 15 * 60)   # 20 tries / 15 min / IP
_LIMIT_LOGIN  = rate_limit("login",      20, 15 * 60)   # 20 logins / 15 min / IP

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()

# Auth handlers used to return `detail=f"Login failed: {e}"`, putting the raw
# exception — SQLAlchemy errors naming tables/columns, driver messages, file
# paths — in the HTTP response where an attacker reads it for free. Log the
# detail where we can see it; tell the caller nothing.
_GENERIC_500 = "कुछ गड़बड़ हो गई। कृपया थोड़ी देर बाद दोबारा कोशिश करें।"


def _log_error(label: str, exc: Exception) -> None:
    logger.exception("[auth] %s failed: %s", label, exc)


MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_MINUTES = 15
_login_attempts = {}

# Wrong-OTP tries allowed per email before the OTP is burned. A 6-digit code is
# only 1,000,000 possibilities — with no cap, an attacker could call
# /forgot-password for any known email and brute-force the reset code inside
# its 10-minute window. Five tries makes that a 1-in-200,000 shot per code.
MAX_OTP_ATTEMPTS = 5
_otp_attempts = {}

# Both dicts are keyed by caller-supplied email, so bound them: an attacker
# posting a million unique addresses would otherwise grow them until the Render
# instance OOMs. At the cap we drop the oldest half rather than clear outright,
# so a flood can't wipe an in-progress lockout on a real account.
_MAX_TRACKED_EMAILS = 10_000


def _login_key(email: str) -> str:
    return (email or "").strip().lower()


def _bound(store: dict) -> None:
    if len(store) > _MAX_TRACKED_EMAILS:
        for key in list(store)[: len(store) // 2]:
            store.pop(key, None)


def _otp_attempts_exceeded(email: str) -> bool:
    """Count a wrong-OTP try. True once this email is over the cap."""
    key = _login_key(email)
    _bound(_otp_attempts)
    count = _otp_attempts.get(key, 0) + 1
    _otp_attempts[key] = count
    return count >= MAX_OTP_ATTEMPTS


def _clear_otp_attempts(email: str) -> None:
    _otp_attempts.pop(_login_key(email), None)


def _burn_otp(db: Session, user: User, email: str) -> dict:
    """Too many wrong guesses — invalidate the code so the window closes."""
    user.otp        = None
    user.otp_expiry = None
    db.commit()
    _clear_otp_attempts(email)
    return {
        "success": False,
        "message": "बहुत बार गलत OTP डाला गया। नया OTP मांगें।",
        "data": {"otp_invalidated": True},
    }


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
    _bound(_login_attempts)
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
    # Plain str, not EmailStr, on purpose: a strict EmailStr rejects addresses the
    # client-side regex lets through (e.g. "a..b@gmail.com") with a 422, and the
    # login form then shows a misleading "check your password". Login only needs to
    # look the email up — a bad/unknown address falls through to the normal
    # "email or password wrong" message. Signup/forgot keep EmailStr (OTP delivery).
    email:    str
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


# (Profile-building helpers were removed along with the duplicate /profile
#  handlers — the canonical profile logic lives in routes/profile.py.)


# ── AUTH ENDPOINTS ───────────────────────────────────────────

@router.post("/signup", dependencies=[Depends(_LIMIT_SEND)])
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
            _clear_otp_attempts(body.email)   # fresh code → fresh 5 tries
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
        _log_error("Signup", e)
        raise HTTPException(status_code=500, detail=_GENERIC_500)


@router.post("/login", dependencies=[Depends(_LIMIT_LOGIN)])
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
        # Account has no usable password — NULL hash (legacy/re-imported row) or a
        # Google-only account (GOOGLE_OAUTH sentinel). "wrong password" would be
        # misleading; point the farmer at the flow that actually works.
        if not user.hashed_password or user.hashed_password == "GOOGLE_OAUTH":
            return {"success": False,
                    "message": "इस account का password set नहीं है। 'Password भूल गए?' से नया password बनाएं, या Google से login करें।",
                    "data": {"needs_password_reset": True}}
        if not verify_password(body.password, user.hashed_password):
            data = _record_failed_login(body.email)
            return {"success": False, "message": "Email या password गलत है। Forgot password use कर सकते हैं।", "data": data}

        _clear_failed_login(body.email)
        token = create_access_token(user_id=user.id, email=user.email)
        return {"success": True, "message": "Login successful", "data": {"token": token}}

    except Exception as e:
        _log_error("Login", e)
        raise HTTPException(status_code=500, detail=_GENERIC_500)


@router.post("/verify-otp", dependencies=[Depends(_LIMIT_VERIFY)])
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
        if not secrets.compare_digest(user.otp, body.otp.strip()):
            if _otp_attempts_exceeded(body.email):
                return _burn_otp(db, user, body.email)
            return {"success": False, "message": "OTP गलत है। दोबारा check करें।", "data": {}}

        user.is_verified = True
        user.otp         = None
        user.otp_expiry  = None
        _clear_otp_attempts(body.email)
        _ensure_profile(db, user)   # verified user → profile row exists
        db.commit()
        return {"success": True, "message": "Email verify हो गया। अब login करें।", "data": {}}

    except Exception as e:
        _log_error("OTP verification", e)
        raise HTTPException(status_code=500, detail=_GENERIC_500)


@router.post("/resend-otp", dependencies=[Depends(_LIMIT_SEND)])
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
        _clear_otp_attempts(body.email)   # fresh code → fresh 5 tries

        email_sent = send_otp_email(body.email, otp, purpose="verification")
        if not email_sent:
            return {"success": False, "message": "OTP email नहीं पहुंची। थोड़ी देर बाद दोबारा try करें।", "data": {}}
        return {"success": True, "message": "अगर यह email registered है तो OTP भेज दिया गया है।", "data": {}}

    except Exception as e:
        _log_error("Resend OTP", e)
        raise HTTPException(status_code=500, detail=_GENERIC_500)


@router.post("/forgot-password", dependencies=[Depends(_LIMIT_SEND)])
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
        _clear_otp_attempts(body.email)   # fresh code → fresh 5 tries

        email_sent = send_otp_email(body.email, otp, purpose="reset")
        if not email_sent:
            return {"success": False, "message": "OTP email नहीं पहुंची। थोड़ी देर बाद दोबारा try करें।", "data": {}}
        return {"success": True, "message": "अगर यह email registered है तो OTP भेज दिया गया है।", "data": {}}

    except Exception as e:
        _log_error("Forgot password", e)
        raise HTTPException(status_code=500, detail=_GENERIC_500)


@router.post("/reset-password", dependencies=[Depends(_LIMIT_VERIFY)])
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
        if not secrets.compare_digest(user.otp, body.otp.strip()):
            if _otp_attempts_exceeded(body.email):
                return _burn_otp(db, user, body.email)
            return {"success": False, "message": "OTP गलत है। दोबारा check करें।", "data": {}}

        err = validate_password_strength(body.new_password)
        if err:
            return {"success": False, "message": err, "data": {}}

        user.hashed_password = hash_password(body.new_password)
        user.otp             = None
        user.otp_expiry      = None
        db.commit()
        _clear_otp_attempts(body.email)
        _clear_failed_login(body.email)
        return {"success": True, "message": "Password reset हो गया। अब login करें।", "data": {}}

    except Exception as e:
        _log_error("Reset password", e)
        raise HTTPException(status_code=500, detail=_GENERIC_500)


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
            # `or ""` guards legacy rows whose hashed_password is NULL — the old
            # Neon migration added the column as a nullable VARCHAR, so pre-existing
            # accounts can have None here, and None.startswith() would 500.
            if user.auth_provider != "google" and not (user.hashed_password or "").startswith("$2"):
                user.auth_provider = "google"
            _ensure_profile(db, user)   # verified user → profile row exists
            db.commit()

        _clear_failed_login(email)
        token = create_access_token(user_id=user.id, email=user.email)
        return {"success": True, "message": "Google login successful", "data": {"token": token}}

    except httpx.TimeoutException:
        return {"success": False, "message": "Google server से response नहीं मिला। दोबारा try करें।", "data": {}}
    except Exception as e:
        _log_error("Google login", e)
        raise HTTPException(status_code=500, detail=_GENERIC_500)


# ── /profile and /me ─────────────────────────────────────────
# Intentionally NOT defined in this router. The dedicated full-field
# profile router (backend/routes/profile.py, prefix="/profile") owns
# GET/POST/PUT /profile, so every farmer-profile field is persisted and
# returned. Earlier this file registered its own /profile handlers that —
# because auth_router is included before profile_router — shadowed the real
# ones and silently dropped most fields on save. They were removed to fix
# that. Do not re-add /profile here.


# ── LEGACY PROFILE CRUD — REMOVED ────────────────────────────
# POST /user, GET /user/{id}, PUT /user/{id} and GET /users used to live here.
# All four were unauthenticated: GET /users dumped every farmer's name,
# district and crop to anonymous callers, and PUT /user/{id} let anyone rewrite
# anyone else's profile by guessing an integer. Nothing in frontend/ or admin/
# called them — they were dead code with a live IDOR. The authenticated
# equivalents live in routes/profile.py (prefix="/profile"), which reads the
# user from the JWT. Do not re-add these.

print("✅ auth.py loaded successfully")
