# ============================================================
# routes/admin_pay.py
# /admin/pay/link — the owner makes a one-off payment link.
#
# For money that belongs to no listing, tick or sponsor row: a custom plan
# agreed on the phone, a part payment, anything. The owner types the amount,
# what it is for and (optionally) who pays; the result is a signed
# /pay/link/{token} URL whose page shows exactly that, with the QR.
#
# Signed because the page prints the owner's text on krashimitra.in — see
# services/pay_links.py for why an editable version would be a liability.
#
# Like every other collect button, making a link records nothing. The money is
# real only once it is seen in the bank app and entered in हिसाब (ledger),
# where the link's own reference (link-XXXXXXXXXX) is what to match it by.
# ============================================================
from fastapi import APIRouter, Depends, HTTPException

from backend.routes.admin import require_admin
from backend.services import pay_links, upi

router = APIRouter(prefix="/admin/pay", tags=["admin-pay"])


@router.post("/link")
def make_link(payload: dict, _: str = Depends(require_admin)):
    if not upi.configured():
        raise HTTPException(400, "KM_UPI_ID सेट नहीं है — पेमेंट लिंक नहीं बन सकता")
    try:
        req = pay_links.make_link(payload.get("amount"), payload.get("purpose") or "",
                                  payload.get("payer") or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    note = f"KrashiMitra {req['purpose']}"
    link = upi.link(req["amount"], note=note, ref=req["ref"])
    return {"success": True, **req, "link": link, "qr_svg": upi.qr_svg(link),
            "whatsapp": pay_links.whatsapp_text(req["payer"], req["amount"],
                                                req["purpose"], req["url"])}
