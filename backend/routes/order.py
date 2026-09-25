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
# resolve_token_user_id, NOT decode_access_token — and it has to be imported.
# _get_token_optional() below called it inside a bare `except Exception: pass`,
# so the NameError it raised on every request was swallowed and the caller was
# handed None: a logged-in farmer's pre-book came back 401 "पहले लॉगिन करें"
# and his order history came back empty. Nothing in the UI could show that,
# because the only page that posted orders (shop.html) was retired first.
from backend.utils.auth_utils import resolve_token_user_id

router = APIRouter(prefix="/order", tags=["order"])


# ── Helpers ──────────────────────────────────────────────────

def _generate_tracking_code() -> str:
    """Generate a short unique tracking code like KM-A3X7B2."""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choices(chars, k=6))
    return f"KM-{code}"


def _get_token_optional(authorization: str = None):
    """Try to parse JWT from Authorization header. Returns user dict or None.

    resolve_token_user_id() does the real work: the signature alone does not
    prove the account still exists, is verified, or that its id was not
    recycled — and an order must not be filed against the wrong account."""
    try:
        if authorization and authorization.startswith("Bearer "):
            uid = resolve_token_user_id(authorization.split(" ")[1])
            return {"user_id": uid} if uid else None
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

    # A JWT carries a user_id, not a promise that the account still exists.
    # Deleting an account leaves every token already issued to it valid and
    # sitting in a browser, and orders.user_id has a foreign key to users — so
    # the row below used to be built with a dangling id and die at commit with a
    # 500, after the farmer had filled in the whole form. Stop at the lookup and
    # tell him to sign in again, which is the one thing that actually fixes it.
    db_user = db.query(User).filter(User.id == user["user_id"]).first()
    if not db_user:
        raise HTTPException(401, "आपका खाता अब मौजूद नहीं है — कृपया दोबारा लॉगिन करें।")
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


# ── Order statuses (used by the admin panel) ─────────────────

VALID_STATUSES = ["Pending", "Booked", "Quoted", "Purchased",
                  "Dispatched", "Delivered", "Cancelled", "Unavailable", "Out of Stock"]

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


# ── Order admin lives in routes/admin.py ─────────────────────
# PUT /order/status, PUT /order/quote and GET /order/all used to live here,
# guarded by an admin_key compared with != against a default that sat in
# this public repo, with no lockout — GET /order/all even took the key in
# the URL and returned every order's name, email and phone. Nothing called
# them: the panel uses /admin/orders/{code}/status and /quote behind
# require_admin (Basic auth + brute-force lockout). Removed 25 Sep 2026;
# never re-add an admin route outside require_admin.
