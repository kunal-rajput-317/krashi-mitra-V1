# ============================================================
# backend/utils/auth_utils.py
# KrashiMitra — Auth Utilities
# ============================================================
# COMPATIBILITY FIX:
#   Replaced all `X | None` syntax with Optional[X]
#   `X | Y` union syntax requires Python 3.10+
#   Optional[X] works on Python 3.8, 3.9, 3.10, 3.11, 3.12
# ============================================================

import os
import re
import random
import smtplib
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Optional

# ── passlib + bcrypt compatibility patch ─────────────────────
# passlib is unmaintained and crashes reading bcrypt >= 4.0 version.
# This patch suppresses the AttributeError on startup.
import bcrypt as _bcrypt
if not hasattr(_bcrypt, "__about__"):
    import types
    _bcrypt.__about__ = types.SimpleNamespace(__version__=_bcrypt.__version__)
# ─────────────────────────────────────────────────────────────

from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()


# ── Password Hashing ─────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def _truncate(password: str) -> str:
    """Truncate to 72 bytes — bcrypt hard limit. Prevents crash."""
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")

def hash_password(plain_password: str) -> str:
    """Hash a plain password using bcrypt (safe — truncated to 72 bytes)."""
    return pwd_context.hash(_truncate(plain_password))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password — truncates before comparing to match hash."""
    return pwd_context.verify(_truncate(plain_password), hashed_password)


# ── Password Strength Validation ─────────────────────────────

def validate_password_strength(password: str) -> Optional[str]:
    """
    Validate password meets minimum requirements.
    Rules: min 6 chars, at least 1 letter, at least 1 number.
    Returns None if valid, Hindi error string if invalid.
    """
    if len(password) > 70:
        return "पासवर्ड 70 characters से छोटा होना चाहिए।"
    if len(password) < 6:
        return "Password कम से कम 6 characters का होना चाहिए।"
    return None


# ── JWT ──────────────────────────────────────────────────────

JWT_SECRET       = os.getenv("JWT_SECRET", "change_this_secret_in_production")
JWT_ALGORITHM    = "HS256"
JWT_EXPIRY_HOURS = 24

def create_access_token(user_id: int, email: str) -> str:
    """Create a signed JWT. Payload: sub (user_id), email, exp."""
    payload = {
        "sub":   str(user_id),
        "email": email,
        "exp":   datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
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

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    Reusable FastAPI dependency for protected routes.
    Usage: current_user: dict = Depends(get_current_user)
    Raises HTTP 401 if token is missing, invalid, or expired.
    """
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail      = "Token invalid या expire हो गया है। दोबारा login करें।",
            headers     = {"WWW-Authenticate": "Bearer"},
        )
    return {
        "user_id": int(payload["sub"]),
        "email":   payload["email"],
    }


# ── OTP Utilities ────────────────────────────────────────────

OTP_EXPIRY_MINUTES = 10

def generate_otp() -> str:
    """Generate a 6-digit numeric OTP."""
    return str(random.randint(100000, 999999))

def otp_expiry_time() -> datetime:
    """Return UTC expiry timestamp (10 min from now)."""
    return datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)

def is_otp_expired(otp_expiry: datetime) -> bool:
    """Return True if OTP has expired."""
    return datetime.utcnow() > otp_expiry


# ── Email Sender ─────────────────────────────────────────────

SMTP_EMAIL    = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587

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

    # Guard — if SMTP not configured, print OTP to terminal (dev mode)
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print(f"⚠️  SMTP not configured. DEV OTP for {to_email}: {otp}")
        print(f"    Add SMTP_EMAIL and SMTP_PASSWORD to .env for real emails.")
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
        print(f"⚠️  SMTP auth failed — check SMTP_EMAIL / SMTP_PASSWORD in .env")
        return False
    except smtplib.SMTPException as e:
        print(f"⚠️  SMTP error to {to_email}: {e}")
        return False
    except OSError as e:
        print(f"⚠️  Network error sending email to {to_email}: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Unexpected email error to {to_email}: {e}")
        return False