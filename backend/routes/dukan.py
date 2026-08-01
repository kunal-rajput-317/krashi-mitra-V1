# ============================================================
# backend/routes/dukan.py
# KrashiMitra — "अपनी दुकान लिस्ट करें": dealer supply that arrives without a
# phone call.
#
# The खरीदार directory is seeded the hard way, by ringing traders one at a time.
# That does not scale and it is not meant to — the first ten calls are how we
# learn what a dealer will actually pay for. This endpoint is what catches the
# eleventh: the dealer who finds the district page himself, sees three of his
# competitors listed on it, and wants in.
#
# So it is deliberately NOT a substitute for the calls. Nobody finds this form
# until the directory already exists and ranks; it only stops us losing the
# dealers who come looking.
#
# ENDPOINTS:
#   POST /dukan/signup    public, no auth, rate-limited
#
# RULES:
#   • No login. Unlike /appeal/crop, the person filling this in is a trader with
#     no reason to hold a farmer's account, and a signup wall on the supply side
#     costs listings we are otherwise paying phone calls to get. The trade is
#     that an unauthenticated row is worth less, which is exactly why it lands
#     inactive.
#   • Never live, never verified. The row goes to the admin queue as a REQUEST
#     to be listed. services/dealers.py::from_signup has no code path to either
#     flag — the blue tick is a claim we make to a farmer about a stranger's
#     phone number, and it costs one real phone call.
#   • A working mobile number is the one hard requirement: the entire value of a
#     row here is being able to ring it back.
# ============================================================

from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.db import get_db, is_read_only_error
from backend.services import dealers
from backend.utils.security import rate_limit

router = APIRouter(prefix="/dukan", tags=["dukan"])

# 3 per hour per IP. A dealer lists his firm once. The limit is low because the
# cost of a false positive is one phone call to a number we already have, and
# the cost of an open form is a table full of spam nobody will ever ring.
_LIMIT_SIGNUP = rate_limit("dukan_signup", 3, 60 * 60)

_MAX = {"name": 120, "state": 80, "district": 80, "market": 120,
        "phone": 20, "whatsapp": 20, "note": 400, "since": 40}

OK = ("आपकी जानकारी मिल गई है। हमारी टीम आपके नंबर पर कॉल करके पुष्टि करेगी, "
      "उसके बाद आपका नाम आपके जिले के किसानों को दिखने लगेगा।")
READ_ONLY = ("अभी सर्वर पर जानकारी सेव नहीं हो पा रही। थोड़ी देर बाद दोबारा "
             "कोशिश करें — या WhatsApp पर सीधे भेज दें।")


class DukanIn(BaseModel):
    name: str = ""
    kind: str = "trader"
    state: Optional[str] = ""
    district: Optional[str] = ""
    market: Optional[str] = ""
    # The form posts a list; a comma string is accepted too so the endpoint
    # stays usable from a plain HTML post or curl.
    commodities: Union[List[str], str] = ""
    phone: Optional[str] = ""
    whatsapp: Optional[str] = ""
    note: Optional[str] = ""
    since: Optional[str] = ""


@router.post("/signup")
async def dukan_signup(
    payload: DukanIn,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_LIMIT_SIGNUP),
):
    data = {
        "name":        (payload.name or "").strip()[:_MAX["name"]],
        "kind":        payload.kind,
        "state":       (payload.state or "").strip()[:_MAX["state"]],
        "district":    (payload.district or "").strip()[:_MAX["district"]],
        "market":      (payload.market or "").strip()[:_MAX["market"]],
        "commodities": payload.commodities,
        "phone":       (payload.phone or "").strip()[:_MAX["phone"]],
        "whatsapp":    (payload.whatsapp or "").strip()[:_MAX["whatsapp"]],
        "note":        (payload.note or "").strip()[:_MAX["note"]],
        "since":       (payload.since or "").strip()[:_MAX["since"]],
    }
    problem = dealers.validate(data)
    if problem:
        raise HTTPException(400, problem)

    try:
        dealers.from_signup(db, data)
    except Exception as e:
        # Same Neon read-only case the admin panel handles, but this reader is a
        # trader who will never see a 500 page and simply concludes we are
        # broken. Give him the WhatsApp fallback instead.
        if is_read_only_error(e):
            raise HTTPException(503, READ_ONLY)
        raise HTTPException(500, "जानकारी सेव नहीं हो पाई। दोबारा कोशिश करें।")

    return {"success": True, "message": OK, "data": {}}
