# ============================================================
# backend/routes/dukan.py
# KrashiMitra — "अपनी दुकान लिस्ट करें": paid, login-gated dealer subscriptions.
#
# Replaces the old anonymous, free, single-district /dukan/signup (shipped
# 2026-08-01) entirely — this is not an add-on tier next to it. A dealer now
# has to log in (the same account system farmers use — reused so a listing has
# a real users.id to author its krashi_bajar post as, see
# services/dealers.py::_sync_bazar_post), pick however many districts they
# want to be reachable in, and pay a monthly subscription:
# services/dealers.py::quote() — ₹199 for the first district, +₹50 for each
# additional one.
#
# ENDPOINTS (all Depends(get_current_user) — no anonymous path any more):
#   POST   /dukan/listings         create/add districts to the caller's account
#   GET    /dukan/mine             the caller's own districts + current price
#   DELETE /dukan/listings/{slug}  drop one district (must own the row)
#
# WHAT DOES NOT CHANGE from the old model:
#   • Never live, never verified from here. services/dealers.py::from_signup
#     still has no code path to either flag — a row lands status="new",
#     active=False exactly like the old public form did. The phone-verification
#     call stays a hard gate: paying does not itself put a dealer live (see
#     record_payment()'s owner_user_id branch) — only admin's approve() does.
#   • A working mobile number is still the one hard requirement.
#
# WHAT IS NEW:
#   • owner_user_id ties every district-row this account creates together, so
#     one subscription payment renews all of them (record_payment()) and the
#     bhav Tier-3 panel / krashi_bajar post both key off the whole account's
#     eligibility, not one row in isolation.
#   • Listing itself only ever happens on the crop+state Tier-3 bhav page
#     (services/buyers.py::for_bhav_panel) and as a krashi_bajar feed post
#     (services/dealers.py::_sync_bazar_post) — never on the district Tier-4
#     page, and never with a phone number visible outside the existing
#     /kharidar page.
# ============================================================

import base64
from datetime import datetime
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.db import Buyer, get_db, is_read_only_error
from backend.services import dealer_products, dealers
from backend.utils.auth_utils import get_current_user

router = APIRouter(prefix="/dukan", tags=["dukan"])

_MAX = {"name": 120, "state": 80, "district": 80, "market": 120,
        "phone": 20, "whatsapp": 20, "description": 400, "since": 40}

# One account, one district picker to spam — a real logged-in account is
# already far more friction than the old anonymous form had, so this is a
# sanity cap rather than an abuse defence.
_MAX_DISTRICTS = 10

OK = ("आपकी जानकारी मिल गई है। हमारी टीम आपके नंबर पर कॉल करके पुष्टि करेगी, "
      "उसी कॉल पर भुगतान लिंक भी भेजेगी।")
READ_ONLY = ("अभी सर्वर पर जानकारी सेव नहीं हो पा रही। थोड़ी देर बाद दोबारा "
             "कोशिश करें — या WhatsApp पर सीधे भेज दें।")


def _norm(s: Optional[str]) -> str:
    return " ".join((s or "").strip().lower().split())


class DistrictIn(BaseModel):
    state: str = ""
    district: str = ""
    market: str = ""


class ListingsIn(BaseModel):
    name: str = ""
    kind: str = "trader"
    phone: Optional[str] = ""
    whatsapp: Optional[str] = ""
    # The form posts a list; a comma string works too, same courtesy the old
    # endpoint gave curl/plain-HTML callers.
    commodities: Union[List[str], str] = ""
    # The dealer's own public blurb — "what I want to list". Deliberately NOT
    # `note`: that is the admin's private call log, services/dealers.py::_apply
    # gates it behind `trusted`, and it used to be the field the public kharidar
    # card rendered. Accepting `note` here would let a dealer write into the
    # call log about himself.
    description: Optional[str] = ""
    since: Optional[str] = ""
    districts: List[DistrictIn] = []


@router.post("/listings")
async def create_listings(
    payload: ListingsIn,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create (or add districts to) the caller's dealer account.

    Additive, not a replace-all: re-submitting to add one more district skips
    any (state, district) the account already has rather than duplicating it
    or touching that row's call/payment history.
    """
    user_id = current_user["user_id"]
    base = {
        "name":          (payload.name or "").strip()[:_MAX["name"]],
        "kind":          payload.kind,
        "commodities":   payload.commodities,
        "phone":         (payload.phone or "").strip()[:_MAX["phone"]],
        "whatsapp":      (payload.whatsapp or "").strip()[:_MAX["whatsapp"]],
        "description":   (payload.description or "").strip()[:_MAX["description"]],
        "since":         (payload.since or "").strip()[:_MAX["since"]],
        "owner_user_id": user_id,
    }

    incoming = [d for d in (payload.districts or []) if (d.district or "").strip()]
    incoming = incoming[:_MAX_DISTRICTS]
    if not incoming:
        raise HTTPException(400, "कम से कम एक जिला चुनें")

    problem = dealers.validate({**base, "district": incoming[0].district})
    if problem:
        raise HTTPException(400, problem)

    existing_keys = {(_norm(r.state), _norm(r.district))
                     for r in dealers.for_owner(db, user_id)}

    try:
        created = 0
        for d in incoming:
            key = (_norm(d.state), _norm(d.district))
            if key in existing_keys:
                continue
            existing_keys.add(key)
            dealers.from_signup(db, {
                **base,
                "state":    (d.state or "").strip()[:_MAX["state"]],
                "district": (d.district or "").strip()[:_MAX["district"]],
                "market":   (d.market or "").strip()[:_MAX["market"]],
            })
            created += 1
    except Exception as e:
        if is_read_only_error(e):
            raise HTTPException(503, READ_ONLY)
        raise HTTPException(500, "जानकारी सेव नहीं हो पाई। दोबारा कोशिश करें।")

    total = len(dealers.for_owner(db, user_id))
    return {"success": True, "message": OK, "data": {
        "created":         created,
        "district_count":  total,
        "price":           dealers.quote(total) if total else 0,
    }}


@router.get("/mine")
async def my_listings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The caller's own districts, verification/payment status, and the
    current monthly price — so the page can show "your listings" instead of a
    blank form on a repeat visit."""
    rows = dealers.for_owner(db, current_user["user_id"])
    now = datetime.utcnow()
    items = [{
        "slug":       r.slug,
        "state":      r.state or "",
        "district":   r.district or "",
        "market":     r.market or "",
        "active":     bool(r.active),
        "verified":   bool(r.verified),
        "status":     r.status,
        "paid_until": r.paid_until.isoformat() if r.paid_until else None,
        "paying":     bool(r.paid_until and r.paid_until > now),
    } for r in rows]
    # Business fields live per-row (so an admin can hand-correct one district
    # without touching the rest), but they are the same account — the first
    # row is a fine default for prefilling "add another district" so the
    # dealer never has to retype their own firm name and phone.
    lead = rows[0] if rows else None
    business = {
        "name":        lead.name if lead else "",
        "kind":        lead.kind if lead else "trader",
        "phone":       lead.phone if lead else "",
        "whatsapp":    lead.whatsapp if lead else "",
        "commodities": (lead.commodities or "").split(",") if lead and lead.commodities else [],
        "description": lead.description if lead else "",
        "since":       lead.since if lead else "",
    } if lead else None
    return {"success": True, "data": {
        "listings":        items,
        "district_count":  len(items),
        "price":           dealers.quote(len(items)) if items else 0,
        "business":        business,
    }}


@router.get("/product-image/{product_id}.webp")
def product_image(product_id: int, db: Session = Depends(get_db)):
    """A product photo, served as bytes.

    Public and unauthenticated — it renders on the /bhav cards a farmer sees.
    Served from here rather than inlined as a data URI so the high-traffic bhav
    HTML stays small and the browser caches the photo across pages; the blob is
    deferred() on the model and this is its only reader.

    Cached hard: the URL is keyed by an id that never changes, so a replaced
    photo relies on the ?v= cache-buster the card appends from `updated_at`.
    """
    pack = dealer_products.image_of(db, product_id)
    if not pack:
        raise HTTPException(404, "no image")
    b64, mime = pack
    try:
        raw = base64.b64decode(b64)
    except Exception:
        raise HTTPException(404, "no image")
    return Response(content=raw, media_type=mime,
                    headers={"Cache-Control": "public, max-age=604800"})


# ── The dealer's own catalogue ────────────────────────────────
# He types what he sells; the admin puts the photos on (see routes/admin.py).
# That split is deliberate: an image accepted from a public form is a
# moderation queue nobody has time to run, on a surface where a bad picture
# goes out under our own verified tick.

class ProductIn(BaseModel):
    name_hi: str = ""
    name_en: Optional[str] = ""
    price: Optional[float] = None
    mrp: Optional[float] = None
    unit_hi: Optional[str] = ""
    badge: Optional[str] = ""


def _my_listing(db, user_id):
    """The caller's own account, or None. Products hang off the account, so any
    of his rows will do — the first is as good as the last."""
    rows = dealers.for_owner(db, user_id)
    return rows[0] if rows else None


@router.get("/products")
async def my_products(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _my_listing(db, current_user["user_id"])
    if not row:
        return {"success": True, "data": {"products": [], "max": dealer_products.MAX_PER_DEALER}}
    return {"success": True, "data": {
        "products": dealer_products.for_buyer(db, row.slug, row.owner_user_id,
                                              only_active=False),
        "max": dealer_products.MAX_PER_DEALER,
    }}


@router.post("/products")
async def add_product(
    payload: ProductIn,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _my_listing(db, current_user["user_id"])
    if not row:
        raise HTTPException(400, "पहले अपनी दुकान लिस्ट करें")
    data = payload.model_dump()
    problem = dealer_products.validate(data)
    if problem:
        raise HTTPException(400, problem)
    try:
        created = dealer_products.create(db, row.slug, row.owner_user_id, data)
    except Exception as e:
        if is_read_only_error(e):
            raise HTTPException(503, READ_ONLY)
        raise HTTPException(500, "प्रोडक्ट सेव नहीं हो पाया।")
    if not created:
        raise HTTPException(400, f"ज्यादा से ज्यादा {dealer_products.MAX_PER_DEALER} प्रोडक्ट जोड़ सकते हैं")
    return {"success": True, "data": dealer_products.as_dict(created)}


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ownership is checked here, not in the service — dealer_products.delete()
    is also the admin's tool and must not grow an auth check of its own."""
    row = _my_listing(db, current_user["user_id"])
    product = dealer_products.get(db, product_id)
    if not row or not product:
        raise HTTPException(404, "प्रोडक्ट नहीं मिला")
    owns = (product.owner_user_id and product.owner_user_id == row.owner_user_id) \
        or product.buyer_slug == row.slug
    if not owns:
        raise HTTPException(404, "प्रोडक्ट नहीं मिला")
    dealer_products.delete(db, product_id)
    return {"success": True, "data": {}}


@router.delete("/listings/{slug}")
async def delete_listing(
    slug: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Drop one district. Ownership-checked here, not in the service layer —
    dealers.delete() is also the admin's tool and must not gain an auth check
    that would then apply to admin calls too."""
    row = db.query(Buyer).filter(Buyer.slug == slug).first()
    if not row or row.owner_user_id != current_user["user_id"]:
        raise HTTPException(404, "लिस्टिंग नहीं मिली")
    dealers.delete(db, slug)
    return {"success": True, "data": {}}
