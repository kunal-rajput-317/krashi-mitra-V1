# ============================================================
# backend/utils/auth_utils.py
# KrashiMitra — Auth Utilities
# ============================================================
# COMPATIBILITY FIX:
#   Replaced all `X | None` syntax with Optional[X]
#   `X | Y` union syntax requires Python 3.10+
#   Optional[X] works on Python 3.8, 3.9, 3.10, 3.11, 3.12
# ============================================================

import calendar
import os
import re
import secrets
import smtplib
import traceback
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Optional

import bcrypt as _bcrypt
# ─────────────────────────────────────────────────────────────

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# Safe at module level: db.py imports nothing from this package, so there is no
# cycle. Model imports stay local to the functions that need them, to keep this
# module importable by tooling that only wants the password/OTP helpers.
from backend.database.db import get_db
import logging

log = logging.getLogger(__name__)

load_dotenv()


# ── Password Hashing ─────────────────────────────────────────

def _password_bytes(password: str) -> bytes:
    """Encode and truncate to bcrypt's 72-byte limit."""
    return password.encode("utf-8")[:72]

def hash_password(plain_password: str) -> str:
    """Hash a plain password using bcrypt."""
    return _bcrypt.hashpw(_password_bytes(plain_password), _bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against a bcrypt hash.

    Returns False (never raises) for a missing/blank/non-bcrypt hash. Legacy or
    re-imported rows can have a NULL hashed_password, and the old code did
    None.encode() → AttributeError, which escaped the `except ValueError` and
    surfaced as a 500 on /login. A passwordless account must fail closed, not crash.
    """
    if not hashed_password:
        return False
    try:
        return _bcrypt.checkpw(_password_bytes(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── Password Strength Validation ─────────────────────────────

# Passwords seen constantly in Indian sign-up data — a length+charclass rule
# alone happily accepts every one of them.
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "passw0rd",
    "12345678", "123456789", "1234567890", "qwerty123", "qwertyui",
    "abc12345", "admin123", "welcome1", "iloveyou", "letmein1",
    "india123", "krishna1", "krishna123", "farmer123", "kisan123",
    "krashimitra", "krashi123",
}


def validate_password_strength(password: str) -> Optional[str]:
    """
    Validate password meets minimum requirements.
    Rules: 8–70 chars, at least one letter and one number, not a common password.
    Returns None if valid, Hindi error string if invalid.

    The old rule was length>=6 only — the docstring claimed it enforced a letter
    and a number, but no such check existed, so "123456" was a valid password.
    """
    if len(password) > 70:
        return "पासवर्ड 70 characters से छोटा होना चाहिए।"
    if len(password) < 8:
        return "Password कम से कम 8 characters का होना चाहिए।"
    if not re.search(r"[A-Za-z]", password):
        return "Password में कम से कम एक अक्षर (letter) होना चाहिए।"
    if not re.search(r"\d", password):
        return "Password में कम से कम एक अंक (number) होना चाहिए।"
    if password.lower() in _COMMON_PASSWORDS:
        return "यह password बहुत आम है। कोई और password चुनें।"
    return None


# ── JWT ──────────────────────────────────────────────────────

JWT_SECRET       = os.getenv("JWT_SECRET", "change_this_secret_in_production")
JWT_ALGORITHM    = "HS256"
JWT_EXPIRY_HOURS = 24

def create_access_token(user_id: int, email: str) -> str:
    """Create a signed JWT. Payload: sub (user_id), email, iat, exp.

    `iat` is not decoration: `sub` is a users.id, and ids get recycled. Wipe the
    table (or roll the sequence back) and the next signup takes id 1 — a token
    minted for the PREVIOUS id 1 would still be inside its 24h window and would
    authenticate as the new account. iat is what lets resolve_token_user() tell
    those apart: a token issued before its account existed is not its token.
    """
    now = datetime.utcnow()
    payload = {
        "sub":   str(user_id),
        "email": email,
        # timegm, not .timestamp(): `now` is naive UTC and .timestamp() would
        # read it as local time (IST here) — a 5.5h-wrong iat.
        "iat":   calendar.timegm(now.utctimetuple()),
        "exp":   now + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    """Decode JWT. Returns payload dict or None on failure/expiry."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


# ── Protected Route Dependency ────────────────────────────────

bearer_scheme = HTTPBearer()

# iat is whole seconds while users.created_at carries microseconds, and the
# Google-signup path mints a token in the same second it writes the row — a
# strict comparison would reject a perfectly good token. This slack is safe
# because a recycled-id token is stale by hours or days, never by seconds.
TOKEN_AGE_SKEW_SECONDS = 120


def resolve_token_user(db, token: str) -> Optional["User"]:
    """The account a Bearer token really belongs to, or None.

    Decoding the JWT is not enough on its own. The signature only proves the
    token was issued by us; it says nothing about whether that account still
    exists, is still verified, or is even the same account it was issued for
    (users.id gets recycled — see create_access_token). Every check that used to
    be skipped lives here, so the strict and the guest-tolerant paths cannot
    drift apart:

      • token decodes and is unexpired  (jose checks exp)
      • it carries an iat              (tokens minted before this existed are dead)
      • the account still exists
      • the account is still verified  (un-verified by admin → token stops working)
      • it was issued AFTER that account was created (not a recycled id)
    """
    payload = decode_access_token(token)
    if not payload:
        return None
    try:
        user_id = int(payload.get("sub") or payload.get("user_id"))
    except (TypeError, ValueError):
        return None

    iat = payload.get("iat")
    if iat is None:
        return None

    from backend.database.db import User   # local import: db.py must stay importable on its own
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_verified:
        return None
    if user.created_at and datetime.utcfromtimestamp(iat) < (
        user.created_at - timedelta(seconds=TOKEN_AGE_SKEW_SECONDS)
    ):
        return None                       # issued before this account existed
    return user


def resolve_token_user_id(token: str, db=None) -> Optional[int]:
    """resolve_token_user() for the guest-tolerant helpers, which hold an
    Authorization header but not always a Session. Opens its own session only
    when a token is actually present, so guest traffic pays nothing."""
    if not token:
        return None
    if db is not None:
        user = resolve_token_user(db, token)
        return user.id if user else None
    from backend.database.db import SessionLocal
    own = SessionLocal()
    try:
        user = resolve_token_user(own, token)
        return user.id if user else None
    finally:
        own.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> dict:
    """
    Reusable FastAPI dependency for protected routes.
    Usage: current_user: dict = Depends(get_current_user)
    Raises HTTP 401 if the token is missing, invalid, expired, or no longer
    matches a live verified account (see resolve_token_user).

    The Session comes from Depends(get_db) — the same one the endpoint itself
    receives — so the check costs one indexed primary-key lookup and no extra
    connection. It must be a real dependency and not a plain default argument:
    FastAPI reads this signature, and a bare `db=None` would show up as an
    optional QUERY PARAMETER named "db" on every protected route.
    """
    user = resolve_token_user(db, credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Token invalid या expire हो गया है। दोबारा login करें।",
            headers     = {"WWW-Authenticate": "Bearer"},
        )
    return {"user_id": user.id, "email": user.email}


# ── OTP Utilities ────────────────────────────────────────────

OTP_EXPIRY_MINUTES = 10

def generate_otp() -> str:
    """Generate a 6-digit numeric OTP.

    Uses `secrets`, not `random`: random.randint draws from a Mersenne Twister
    whose internal state is recoverable from prior outputs, so an attacker who
    can trigger and observe a few OTPs (e.g. via their own signups) could
    predict the next one issued — including a victim's password-reset code.
    """
    return f"{secrets.randbelow(1_000_000):06d}"

def otp_expiry_time() -> datetime:
    """Return UTC expiry timestamp (10 min from now)."""
    return datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)

def is_otp_expired(otp_expiry: Optional[datetime]) -> bool:
    """Return True if the OTP has expired — and True when we can't tell.

    users.otp_expiry is nullable, and rows reach that state routinely: a
    Google-auth signup never sets one, and an account whose OTP was already
    consumed has it cleared. Both call sites (routes/auth.py verify-otp and
    reset-password) passed the column straight in, so a NULL turned
    `datetime.utcnow() > None` into a TypeError and surfaced as a 500 on OTP
    verification rather than "code expired, request a new one".

    Fails closed, matching verify_password above: no expiry on record means
    no valid OTP, never an open door.
    """
    if otp_expiry is None:
        return True
    return datetime.utcnow() > otp_expiry


# ── Email Sender ─────────────────────────────────────────────

SMTP_EMAIL = (
    os.getenv("SMTP_EMAIL")
    or os.getenv("EMAIL_USER")
    or os.getenv("GMAIL_USER")
    or ""
).strip()
SMTP_PASSWORD = (
    os.getenv("SMTP_PASSWORD")
    or os.getenv("SMTP_APP_PASSWORD")
    or os.getenv("EMAIL_PASSWORD")
    or os.getenv("GMAIL_APP_PASSWORD")
    or os.getenv("SMTP_CODE")
    or ""
).replace(" ", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM_EMAIL = (
    os.getenv("RESEND_FROM_EMAIL")
    or os.getenv("RESEND_FEOM_EMAIL")  # common typo; keep deploys forgiving
    or os.getenv("FROM_EMAIL")
    or SMTP_EMAIL
).strip()

def _send_with_resend(to_email: str, subject: str, body: str) -> bool:
    """Send email through Resend HTTPS API, which works on Render free tier."""
    if not RESEND_API_KEY or not RESEND_FROM_EMAIL:
        return False

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": RESEND_FROM_EMAIL,
                "to": [to_email],
                "subject": subject,
                "text": body,
            },
            timeout=15,
        )
        if response.status_code < 400:
            return True

        log.warning(f"⚠️  Resend email error {response.status_code}: {response.text[:500]}")
        return False
    except Exception as e:
        log.warning(f"⚠️  Resend network error to {to_email}: {e}")
        return False

def send_otp_email(to_email: str, otp: str, purpose: str = "verification") -> bool:
    """
    Send OTP email. purpose = 'verification' | 'reset'.
    Returns True on success, False on any failure.
    Never raises — exceptions are caught and logged only.
    """
    if purpose == "reset":
        subject = "KrashiMitra — Password Reset OTP"
        body    = (
            f"नमस्ते,\n\n"
            f"आपका पासवर्ड रीसेट OTP है: {otp}\n\n"
            f"यह OTP {OTP_EXPIRY_MINUTES} मिनट में expire हो जाएगा।\n\n"
            f"अगर आपने यह request नहीं की, तो इस email को ignore करें।\n\n"
            f"— KrashiMitra Team"
        )
    else:
        subject = "KrashiMitra — Email Verification OTP"
        body    = (
            f"नमस्ते,\n\n"
            f"KrashiMitra में आपका स्वागत है!\n\n"
            f"आपका verification OTP है: {otp}\n\n"
            f"यह OTP {OTP_EXPIRY_MINUTES} मिनट में expire हो जाएगा।\n\n"
            f"— KrashiMitra Team"
        )

    if _send_with_resend(to_email, subject, body):
        return True

    # Guard — if SMTP not configured, print OTP to terminal (dev mode)
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        log.warning(f"⚠️  SMTP not configured. DEV OTP for {to_email}: {otp}")
        log.info("    Add RESEND_API_KEY + RESEND_FROM_EMAIL, or SMTP_EMAIL + SMTP_PASSWORD.")
        return False

    try:
        msg            = MIMEMultipart()
        msg["From"]    = SMTP_EMAIL
        msg["To"]      = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        return True

    except smtplib.SMTPAuthenticationError:
        log.info(
            "⚠️  SMTP auth failed — check SMTP_EMAIL and Gmail app password. "
            "Use a 16-character app password, not your normal Gmail password."
        )
        return False
    except smtplib.SMTPException as e:
        log.warning(f"⚠️  SMTP error to {to_email}: {e}")
        return False
    except OSError as e:
        log.warning(f"⚠️  Network error sending email to {to_email}: {e}")
        return False
    except Exception as e:
        log.warning(f"⚠️  Unexpected email error to {to_email}: {e}")
        return False
    
    log.info("✅ auth_utils.py loaded successfully")
