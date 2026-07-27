# ============================================================
# backend/routes/order.py
# KrashiMitra — Order Router
# ============================================================
# POST /order/log      → create a new order — LOGIN REQUIRED
# GET  /order/history  → fetch order history (JWT or legacy session_id)
#
# Placing an order requires a login. A pre-book is answered later with a quote,
# and a guest order was reachable only through a localStorage session_id — clear
# the browser and the farmer never saw the price he asked for. History still
# honours session_id so orders placed before the gate remain visible.
# ============================================================

import os
import string
import random
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.db import get_db, Order, User
from backend.utils.auth_utils import decode_access_token

router = APIRouter(prefix="/order", tags=["order"])


# ── Helpers ──────────────────────────────────────────────────

def _generate_tracking_code() -> str:
    """Generate a short unique tracking code like KM-A3X7B2."""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choices(chars, k=6))
    return f"KM-{code}"


def _get_token_optional(authorization: str = None):
    """Try to parse JWT from Authorization header. Returns user dict or None."""
    try:
        if authorization and authorization.startswith("Bearer "):
            token = authorization.split(" ")[1]
            payload = decode_access_token(token)
            if not payload:
                return None
            return {
                "user_id": int(payload.get("user_id") or payload.get("sub")),
                "email": payload.get("email"),
            }
    except Exception:
        pass
    return None


# ── Pydantic Models ──────────────────────────────────────────

class OrderCreateRequest(BaseModel):
    product_name:  str
    product_id:    Optional[int] = None
    quantity:      int = 1
    unit_price:    float
    total:         float
    phone:         str
    source:        str = "shop"       # "shop" / "mandi" / "prebook"
    session_id:    Optional[str] = None   # send if guest
    customer_name: Optional[str] = None   # farmer name (pre-book form)
    pincode:       Optional[str] = None   # delivery pincode (pre-book demand map)


class OrderResponse(BaseModel):
    id:            int
    tracking_code: str
    product_name:  str
    product_id:    Optional[int] = None
    quantity:      int
    unit_price:    float
    total:         float
    phone:         str
    source:        str
    status:        str
    created_at:    str


# ── POST /order/log ──────────────────────────────────────────

@router.post("/log")
def create_order(
    body:          OrderCreateRequest,
    db:            Session       = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    user = _get_token_optional(authorization)
    if not user:
        raise HTTPException(401, "ऑर्डर करने के लिए पहले लॉगिन करें।")

    # Generate unique tracking code
    for _ in range(10):
        tracking_code = _generate_tracking_code()
        existing = db.query(Order).filter(Order.tracking_code == tracking_code).first()
        if not existing:
            break

    # Look up user name/email from users table for logged-in users
    user_email = None
    user_name  = None
    db_user = db.query(User).filter(User.id == user["user_id"]).first()
    if db_user:
        user_email = db_user.email
        user_name  = db_user.name

    order = Order(
        tracking_code = tracking_code,
        user_id       = user["user_id"],
        user_email    = user_email,
        user_name     = user_name,
        session_id    = None,
        is_guest      = False,
        product_name  = body.product_name,
        product_id    = body.product_id,
        quantity      = body.quantity,
        unit_price    = body.unit_price,
        total         = body.total,
        phone         = body.phone,
        source        = body.source,
        status        = "Pending",
        customer_name = body.customer_name,
        pincode       = body.pincode,
    )

    db.add(order)
    db.commit()
    db.refresh(order)

    return {
        "success":       True,
        "tracking_code": order.tracking_code,
        "order_id":      order.id,
        "message":       f"ऑर्डर सफलतापूर्वक बना! Tracking: {order.tracking_code}",
    }


# ── GET /order/history ───────────────────────────────────────

@router.get("/history")
def get_order_history(
    session_id:    Optional[str] = Query(None),
    db:            Session       = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    user = _get_token_optional(authorization)

    if user:
        rows = db.query(Order).filter(
            Order.user_id == user["user_id"]
        ).order_by(Order.created_at.desc()).limit(50).all()
    elif session_id:
        rows = db.query(Order).filter(
            Order.session_id == session_id,
            Order.user_id    == None,
        ).order_by(Order.created_at.desc()).limit(50).all()
    else:
        return {"success": True, "orders": []}

    orders = []
    for o in rows:
        orders.append({
            "id":            o.id,
            "tracking_code": o.tracking_code,
            "user_id":       o.user_id,
            "user_email":    o.user_email,
            "user_name":     o.user_name,
            "is_guest":      o.is_guest,
            "product_name":  o.product_name,
            "product_id":    o.product_id,
            "quantity":      o.quantity,
            "unit_price":    o.unit_price,
            "total":         o.total,
            "phone":         o.phone,
            "source":        o.source,
            "status":        o.status,
            "created_at":    o.created_at.isoformat() if o.created_at else "",
            "pincode":       o.pincode,
            "customer_name": o.customer_name,
            "quote_total":   o.quote_total,
            "delivery_info": o.delivery_info,
            "dealer_name":   o.dealer_name,
            "quote_note":    o.quote_note,
            "quoted_at":     o.quoted_at.isoformat() if o.quoted_at else None,
        })

    return {"success": True, "orders": orders}


# ── PUT /order/status — Admin updates order status ───────────

VALID_STATUSES = ["Pending", "Booked", "Quoted", "Purchased",
                  "Dispatched", "Delivered", "Cancelled", "Unavailable", "Out of Stock"]
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "krashimitra_admin_2026")

# "Out of Order" was the wrong phrase — in English that describes a broken
# machine, not a product the dealer has run out of. Renamed to "Out of Stock".
# orders.status stores the label itself, so rows written before the rename still
# say "Out of Order"; this maps them (and any stale admin tab still posting the
# old value) onto the new one instead of 400-ing or leaving a farmer looking at
# a status nothing recognises. Keyed lowercase — matching is case-insensitive.
LEGACY_STATUS_ALIAS = {"out of order": "Out of Stock"}


def canonical_status(status: str) -> str:
    """Trim, then fold a retired status label onto its replacement."""
    s = (status or "").strip()
    return LEGACY_STATUS_ALIAS.get(s.lower(), s)


class StatusUpdateRequest(BaseModel):
    tracking_code: str
    status:        str       # Pending / Booked / Quoted / Purchased / Delivered
    admin_key:     str       # must match ADMIN_SECRET


@router.put("/status")
def update_order_status(
    body: StatusUpdateRequest,
    db:   Session = Depends(get_db),
):
    # Verify admin key
    if body.admin_key != ADMIN_SECRET:
        return {"success": False, "message": "❌ Invalid admin key"}

    next_status = canonical_status(body.status)
    if next_status not in VALID_STATUSES:
        return {"success": False, "message": f"❌ Invalid status. Use: {', '.join(VALID_STATUSES)}"}

    order = db.query(Order).filter(Order.tracking_code == body.tracking_code).first()
    if not order:
        return {"success": False, "message": f"❌ Order {body.tracking_code} not found"}

    old_status = order.status
    order.status = next_status
    db.commit()

    return {
        "success":       True,
        "tracking_code": order.tracking_code,
        "old_status":    old_status,
        "new_status":    order.status,
        "message":       f"✅ {order.tracking_code}: {old_status} → {order.status}",
    }


# ── PUT /order/quote — Admin sends a quote for a pre-book ─────

class QuoteUpdateRequest(BaseModel):
    tracking_code: str
    admin_key:     str
    quote_total:   float                 # full price incl. delivery + our commission
    delivery_info: str                   # dealer + delivery details shown to the farmer
    dealer_name:   Optional[str] = None
    quote_note:    Optional[str] = None


@router.put("/quote")
def send_order_quote(
    body: QuoteUpdateRequest,
    db:   Session = Depends(get_db),
):
    """Owner attaches a quote to a pre-book after sourcing a local dealer.
    Sets status='Quoted' — the farmer then sees it via the 🔔 notification bell."""
    if body.admin_key != ADMIN_SECRET:
        return {"success": False, "message": "❌ Invalid admin key"}

    order = db.query(Order).filter(Order.tracking_code == body.tracking_code).first()
    if not order:
        return {"success": False, "message": f"❌ Order {body.tracking_code} not found"}

    order.quote_total   = body.quote_total
    order.delivery_info = body.delivery_info
    order.dealer_name   = body.dealer_name
    order.quote_note    = body.quote_note
    order.status        = "Quoted"
    order.quoted_at     = datetime.utcnow()
    db.commit()

    return {
        "success":       True,
        "tracking_code": order.tracking_code,
        "status":        order.status,
        "quote_total":   order.quote_total,
        "message":       f"✅ Quote sent for {order.tracking_code}: ₹{order.quote_total}",
    }


# ── GET /order/all — Admin views all orders ──────────────────

@router.get("/all")
def get_all_orders(
    admin_key: str     = Query(...),
    limit:     int     = Query(100, le=500),
    db:        Session = Depends(get_db),
):
    if admin_key != ADMIN_SECRET:
        return {"success": False, "message": "❌ Invalid admin key"}

    rows = db.query(Order).order_by(Order.created_at.desc()).limit(limit).all()

    orders = []
    for o in rows:
        orders.append({
            "id":            o.id,
            "tracking_code": o.tracking_code,
            "user_id":       o.user_id,
            "user_email":    o.user_email,
            "user_name":     o.user_name,
            "is_guest":      o.is_guest,
            "session_id":    o.session_id,
            "product_name":  o.product_name,
            "quantity":      o.quantity,
            "unit_price":    o.unit_price,
            "total":         o.total,
            "phone":         o.phone,
            "source":        o.source,
            "status":        o.status,
            "created_at":    o.created_at.isoformat() if o.created_at else "",
            "customer_name": o.customer_name,
            "pincode":       o.pincode,
            "quote_total":   o.quote_total,
            "delivery_info": o.delivery_info,
            "dealer_name":   o.dealer_name,
            "quote_note":    o.quote_note,
            "quoted_at":     o.quoted_at.isoformat() if o.quoted_at else None,
        })

    return {"success": True, "total": len(orders), "orders": orders}
