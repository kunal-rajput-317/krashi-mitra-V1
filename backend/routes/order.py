# ============================================================
# backend/routes/order.py
# KrashiMitra — Order Router (Guest + Logged-in Users)
# ============================================================
# POST /order/log      → create a new order (returns tracking code)
# GET  /order/history  → fetch order history (JWT or session_id)
# ============================================================

import os
import string
import random
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Header
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
    product_name: str
    product_id:   Optional[int] = None
    quantity:     int = 1
    unit_price:   float
    total:        float
    phone:        str
    source:       str = "shop"       # "shop" or "mandi"
    session_id:   Optional[str] = None   # send if guest


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

    # Generate unique tracking code
    for _ in range(10):
        tracking_code = _generate_tracking_code()
        existing = db.query(Order).filter(Order.tracking_code == tracking_code).first()
        if not existing:
            break

    # Look up user name/email from users table for logged-in users
    user_email = None
    user_name  = None
    if user:
        db_user = db.query(User).filter(User.id == user["user_id"]).first()
        if db_user:
            user_email = db_user.email
            user_name  = db_user.name

    order = Order(
        tracking_code = tracking_code,
        user_id       = user["user_id"] if user else None,
        user_email    = user_email,
        user_name     = user_name,
        session_id    = body.session_id if not user else None,
        is_guest      = user is None,
        product_name  = body.product_name,
        product_id    = body.product_id,
        quantity      = body.quantity,
        unit_price    = body.unit_price,
        total         = body.total,
        phone         = body.phone,
        source        = body.source,
        status        = "Pending",
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
        })

    return {"success": True, "orders": orders}


# ── PUT /order/status — Admin updates order status ───────────

VALID_STATUSES = ["Pending", "Verified", "Purchased", "Delivered"]
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "krashimitra_admin_2026")


class StatusUpdateRequest(BaseModel):
    tracking_code: str
    status:        str       # Pending / Verified / Purchased / Delivered
    admin_key:     str       # must match ADMIN_SECRET


@router.put("/status")
def update_order_status(
    body: StatusUpdateRequest,
    db:   Session = Depends(get_db),
):
    # Verify admin key
    if body.admin_key != ADMIN_SECRET:
        return {"success": False, "message": "❌ Invalid admin key"}

    if body.status not in VALID_STATUSES:
        return {"success": False, "message": f"❌ Invalid status. Use: {', '.join(VALID_STATUSES)}"}

    order = db.query(Order).filter(Order.tracking_code == body.tracking_code).first()
    if not order:
        return {"success": False, "message": f"❌ Order {body.tracking_code} not found"}

    old_status = order.status
    order.status = body.status
    db.commit()

    return {
        "success":       True,
        "tracking_code": order.tracking_code,
        "old_status":    old_status,
        "new_status":    order.status,
        "message":       f"✅ {order.tracking_code}: {old_status} → {order.status}",
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
        })

    return {"success": True, "total": len(orders), "orders": orders}
