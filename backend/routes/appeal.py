# ============================================================
# backend/routes/appeal.py
# KrashiMitra — "बेचना है / खरीदना है" appeals raised from /bhav price pages
#
# A price page tells a farmer the rate and then stops. This endpoint captures
# the sentence that comes next — "40 क्विंटल गेहूं है, कौन खरीदेगा?" — at the
# moment the intent exists, on the pages SEO traffic actually lands on.
#
# ENDPOINTS:
#   POST /appeal/crop     public (auth optional), rate-limited
#
# RULES:
#   • Login required (decided 2026-07-28, reversing the original open design).
#     An appeal is only worth acting on if we can get back to the person who
#     raised it, and the reply surface is KrashiBook — which needs an account to
#     exist at all. Enforced here, not only in the UI: the client gate is a
#     courtesy, this is the rule. Same posture as orders and bhav alerts.
#   • name + description are required; everything else is page context.
#   • Still length-capped and IP rate-limited: a logged-in writer is identified,
#     not trusted. Nothing here is ever rendered back to other users, so the
#     text is stored as typed and escaped at the point of display.
# ============================================================

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.db import CropAppeal, User, get_db
from backend.routes.bazar import get_optional_user
from backend.utils.security import rate_limit

router = APIRouter(prefix="/appeal", tags=["appeal"])

# 5 per 15 min per IP. A genuine farmer raises one appeal, maybe corrects it
# once; anything past this is a script, not a seller.
_LIMIT_APPEAL = rate_limit("crop_appeal", 5, 15 * 60)

# Field caps. Generous enough that no real appeal is truncated, tight enough
# that the table can't be used as free storage.
_MAX = {"name": 80, "description": 1000, "phone": 20,
        "commodity": 80, "state": 80, "district": 80,
        "quantity": 40, "page_url": 300}

_KINDS = {"sell", "buy"}

LOGIN_REQUIRED = "फसल बेचने/खरीदने का अनुरोध भेजने के लिए पहले लॉगिन करें।"
ACCOUNT_GONE = "आपका खाता अब मौजूद नहीं है — कृपया दोबारा लॉगिन करें।"


class AppealIn(BaseModel):
    kind: str = "sell"
    name: str = ""
    description: str = ""
    phone: Optional[str] = ""
    commodity: str = ""
    state: Optional[str] = ""
    district: Optional[str] = ""
    quantity: Optional[str] = ""
    page_url: Optional[str] = ""


def _clean(value: Optional[str], field: str) -> str:
    """Trim, collapse nothing, cut to the field's cap. Returns "" for None so
    callers can treat missing and blank identically."""
    return (value or "").strip()[:_MAX[field]]


def _clean_phone(value: Optional[str]) -> str:
    """One stored shape for a reachable number: 10 bare digits, +91 implied.

    The form now offers a fixed +91 next to a 10-digit box, but this endpoint is
    reachable without it, and the column had collected pasted country codes and
    runs of repeated digits. Anything that is a recognisable Indian number is
    reduced to its ten subscriber digits; anything else is kept as typed rather
    than thrown away — a number we cannot parse is still a lead a human can read.
    """
    raw = _clean(value, "phone")
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) > 10 and digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 10 else raw


@router.post("/crop", dependencies=[Depends(_LIMIT_APPEAL)])
def create_crop_appeal(payload: AppealIn, request: Request,
                       db: Session = Depends(get_db)):
    """Record one sell/buy appeal against a crop + place. Login required."""
    # Checked first: a guest has nothing to fix by editing the form, so tell him
    # what's actually wrong before validating fields he may not need to retype.
    user = get_optional_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail=LOGIN_REQUIRED)
    # Belt and braces on top of get_optional_user's own account check:
    # crop_appeals.user_id has a foreign key to users, so a row written for an
    # id that is not there any more would take the whole appeal down at commit
    # with a 500 rather than a fixable message. Same guard as /order/log.
    if not db.query(User).filter(User.id == user["user_id"]).first():
        raise HTTPException(status_code=401, detail=ACCOUNT_GONE)

    kind = (payload.kind or "").strip().lower()
    if kind not in _KINDS:
        raise HTTPException(status_code=400, detail="अमान्य अनुरोध।")

    name = _clean(payload.name, "name")
    description = _clean(payload.description, "description")
    commodity = _clean(payload.commodity, "commodity")

    # The required pair, plus the crop — without a crop the row can never be
    # matched to a buyer, so it is worth nothing in the table.
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="कृपया अपना नाम लिखें।")
    if len(description) < 5:
        raise HTTPException(status_code=400, detail="कृपया अपना संदेश लिखें।")
    if not commodity:
        raise HTTPException(status_code=400, detail="फसल की जानकारी नहीं मिली।")

    row = CropAppeal(
        kind=kind,
        name=name,
        description=description,
        phone=_clean_phone(payload.phone) or None,
        user_id=user["user_id"],
        commodity=commodity,
        state=_clean(payload.state, "state") or None,
        district=_clean(payload.district, "district") or None,
        quantity=_clean(payload.quantity, "quantity") or None,
        page_url=_clean(payload.page_url, "page_url") or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    where = row.district or row.state or ""
    # Only the contextual promise. The client owns the confirmation headline
    # ("भाई! आपकी बात कृषि मित्र तक पहुँचा दी गई है ✅") and renders this beneath
    # it, so repeating "दर्ज हो गई" here would say the same thing twice.
    msg = ((f"{where} में " if where else "")
           + ("खरीदार" if kind == "sell" else "बेचने वाले")
           + " मिलते ही हम आपसे संपर्क करेंगे।")
    return {"success": True, "message": msg, "data": {"id": row.id}}
