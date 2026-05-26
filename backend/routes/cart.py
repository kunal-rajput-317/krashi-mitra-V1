# ============================================================
# backend/routes/cart.py
# KrashiMitra — Cart Router (Guest + Logged-in Users)
# ============================================================
# GET    /cart              → fetch cart (JWT or session_id)
# POST   /cart/update       → add/update/remove item
# POST   /cart/merge        → merge guest cart into user cart after login
# DELETE /cart/clear        → clear entire cart
# ============================================================

from fastapi import APIRouter, Depends, Query, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from typing import Optional

from backend.database.db import get_db, Base
from backend.utils.auth_utils import get_current_user

router = APIRouter(prefix="/cart", tags=["cart"])


# ── SQLAlchemy Model ─────────────────────────────────────────

class CartItem(Base):
    __tablename__ = "carts"

    id         = Column(Integer,  primary_key=True, autoincrement=True)  # surrogate PK
    user_id    = Column(Integer,  nullable=True)   # NULL for guests
    session_id = Column(String,   nullable=True)   # NULL for logged-in users
    product_id = Column(Integer,  nullable=False)
    quantity   = Column(Integer,  nullable=False, default=1)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        # Ensures same product can't appear twice for same user or same guest session
        {"extend_existing": True},
    )


# ── Pydantic Models ──────────────────────────────────────────

class CartUpdateRequest(BaseModel):
    product_id: int
    quantity:   int             # 0 = remove item
    session_id: Optional[str] = None   # send if guest


class CartMergeRequest(BaseModel):
    session_id: str             # the guest session to merge in


# ── Helpers ──────────────────────────────────────────────────

def _get_token_optional(authorization: str = None):
    """Try to parse JWT from Authorization header. Returns user dict or None."""
    try:
        from backend.utils.auth_utils import decode_access_token
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


def _cart_response(rows) -> dict:
    return {str(r.product_id): r.quantity for r in rows}


# ── GET /cart ─────────────────────────────────────────────────
# Works for both guests (pass ?session_id=xxx) and logged-in users (JWT)

@router.get("")
def get_cart(
    session_id:   Optional[str] = Query(None),
    db:           Session       = Depends(get_db),
    authorization: Optional[str] = Header(None),   # ← reads actual HTTP header
):
    user = _get_token_optional(authorization)

    if user:
        # Logged-in: fetch by user_id
        rows = db.query(CartItem).filter(
            CartItem.user_id == user["user_id"]
        ).all()
    elif session_id:
        # Guest: fetch by session_id
        rows = db.query(CartItem).filter(
            CartItem.session_id == session_id,
            CartItem.user_id    == None
        ).all()
    else:
        rows = []

    return {"success": True, "cart": _cart_response(rows)}


# ── POST /cart/update ─────────────────────────────────────────
# Works for both guest and logged-in users

@router.post("/update")
def update_cart(
    body:         CartUpdateRequest,
    db:           Session = Depends(get_db),
    authorization: Optional[str] = Header(None),   # ← reads actual HTTP header
):
    user = _get_token_optional(authorization)

    if user:
        # Logged-in user
        item = db.query(CartItem).filter(
            CartItem.user_id    == user["user_id"],
            CartItem.product_id == body.product_id
        ).first()

        if body.quantity <= 0:
            if item:
                db.delete(item)
        else:
            if item:
                item.quantity   = body.quantity
                item.updated_at = datetime.utcnow()
            else:
                db.add(CartItem(
                    user_id    = user["user_id"],
                    session_id = None,
                    product_id = body.product_id,
                    quantity   = body.quantity,
                ))

    elif body.session_id:
        # Guest user
        item = db.query(CartItem).filter(
            CartItem.session_id == body.session_id,
            CartItem.user_id    == None,
            CartItem.product_id == body.product_id
        ).first()

        if body.quantity <= 0:
            if item:
                db.delete(item)
        else:
            if item:
                item.quantity   = body.quantity
                item.updated_at = datetime.utcnow()
            else:
                db.add(CartItem(
                    user_id    = None,
                    session_id = body.session_id,
                    product_id = body.product_id,
                    quantity   = body.quantity,
                ))
    else:
        return {"success": False, "message": "session_id या token जरूरी है।"}

    db.commit()
    return {"success": True}


# ── POST /cart/merge ──────────────────────────────────────────
# Called right after login — merges guest cart into user cart
# If same product exists in both, user cart quantity wins

@router.post("/merge")
def merge_cart(
    body:         CartMergeRequest,
    current_user: dict    = Depends(get_current_user),   # JWT required
    db:           Session = Depends(get_db),
):
    user_id = current_user["user_id"]

    # Get all guest items
    guest_items = db.query(CartItem).filter(
        CartItem.session_id == body.session_id,
        CartItem.user_id    == None
    ).all()

    for guest_item in guest_items:
        # Check if this product already exists in user's cart
        existing = db.query(CartItem).filter(
            CartItem.user_id    == user_id,
            CartItem.product_id == guest_item.product_id
        ).first()

        if existing:
            # User already has this item → add quantities together
            existing.quantity   += guest_item.quantity
            existing.updated_at  = datetime.utcnow()
        else:
            # New item → move to user cart
            db.add(CartItem(
                user_id    = user_id,
                session_id = None,
                product_id = guest_item.product_id,
                quantity   = guest_item.quantity,
            ))

        # Delete the guest row
        db.delete(guest_item)

    db.commit()

    # Return the merged cart
    rows = db.query(CartItem).filter(CartItem.user_id == user_id).all()
    return {
        "success": True,
        "message": f"{len(guest_items)} items आपके cart में merge हो गए।",
        "cart":    _cart_response(rows)
    }


# ── DELETE /cart/clear ───────────────────────────────────────

@router.delete("/clear")
def clear_cart(
    session_id:    Optional[str] = Query(None),
    db:            Session       = Depends(get_db),
    authorization: Optional[str] = Header(None),   # ← reads actual HTTP header
):
    user = _get_token_optional(authorization)

    if user:
        db.query(CartItem).filter(CartItem.user_id == user["user_id"]).delete()
    elif session_id:
        db.query(CartItem).filter(
            CartItem.session_id == session_id,
            CartItem.user_id    == None
        ).delete()
    else:
        return {"success": False, "message": "session_id या token जरूरी है।"}

    db.commit()
    return {"success": True}  
