# ============================================================
# routes/account_delete.py
# /account/delete/* — the "खाता हटाएँ" button on /profile.
#
# Two proofs, because this cannot be undone:
#   • the account's password (skipped only for a Google-only account, which
#     never chose one), and
#   • a fresh OTP sent to the account's own email.
# A stolen phone with a logged-in session is not enough on its own — that is
# the case the OTP exists for, and the password covers a hijacked inbox.
#
# The erasing itself lives in services/account_delete.py; read its header for
# what is kept, what is wiped and why the users row is never deleted.
# ============================================================
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.db import User, get_db
from backend.routes.auth import (_LIMIT_SEND, _LIMIT_VERIFY, _burn_otp,
                                 _clear_otp_attempts, _otp_attempts_exceeded)
from backend.services import account_delete
from backend.utils.auth_utils import (generate_otp, get_current_user, is_otp_expired,
                                      otp_expiry_time, send_otp_email, verify_password)

router = APIRouter(prefix="/account/delete", tags=["account-delete"])


class DeleteRequest(BaseModel):
    otp:      str
    password: Optional[str] = None
    reason:   Optional[str] = None
    confirm:  bool = False


def _me(current_user: dict, db: Session) -> User:
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user or account_delete.is_deleted(user):
        raise HTTPException(404, "खाता नहीं मिला।")
    return user


def _mask(email: str) -> str:
    name, _, dom = (email or "").partition("@")
    return (name[:2] + "•" * max(1, len(name) - 2) + "@" + dom) if dom else ""


@router.get("/info")
def info(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """What the confirm box needs: whether to ask for a password, where the OTP goes."""
    user = _me(current_user, db)
    return {"success": True, "message": "", "data": {
        "has_password": account_delete.has_password(user),
        "email": _mask(user.email),
        "reasons": account_delete.REASONS,
    }}


@router.post("/otp", dependencies=[Depends(_LIMIT_SEND)])
def send_otp(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user = _me(current_user, db)
    otp = generate_otp()
    user.otp = otp
    user.otp_expiry = otp_expiry_time()
    db.commit()
    _clear_otp_attempts(user.email)
    if not send_otp_email(user.email, otp, purpose="delete"):
        return {"success": False, "message": "OTP ईमेल नहीं पहुँची। थोड़ी देर बाद दोबारा कोशिश करें।", "data": {}}
    return {"success": True, "message": f"OTP {_mask(user.email)} पर भेज दिया गया है।", "data": {}}


@router.post("", dependencies=[Depends(_LIMIT_VERIFY)])
def delete_account(body: DeleteRequest, current_user: dict = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    user = _me(current_user, db)
    if not body.confirm:
        return {"success": False, "message": "पहले पुष्टि वाला बॉक्स चुनें।", "data": {}}

    needs_pw = account_delete.has_password(user)
    if needs_pw and not verify_password(body.password or "", user.hashed_password):
        return {"success": False, "message": "पासवर्ड गलत है।", "data": {}}

    if not user.otp or not user.otp_expiry:
        return {"success": False, "message": "पहले OTP मँगाएँ।", "data": {}}
    if is_otp_expired(user.otp_expiry):
        return {"success": False, "message": "OTP expire हो गया। नया OTP मँगाएँ।", "data": {}}
    if not secrets.compare_digest(user.otp, (body.otp or "").strip()):
        if _otp_attempts_exceeded(user.email):
            return _burn_otp(db, user, user.email)
        return {"success": False, "message": "OTP गलत है।", "data": {}}

    email = user.email
    account_delete.erase(db, user, "password+otp" if needs_pw else "otp", body.reason or "")
    _clear_otp_attempts(email)
    return {"success": True,
            "message": "आपका खाता हटा दिया गया है। कृषि मित्र इस्तेमाल करने के लिए धन्यवाद।",
            "data": {}}
