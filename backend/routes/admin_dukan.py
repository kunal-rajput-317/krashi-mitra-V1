# ============================================================
# routes/admin_dukan.py
# Admin API for कृषि दुकान — /admin/dukan/*
#
# A SEPARATE ROUTER FROM admin.py's dealer endpoints, on purpose. Those sell an
# advertisement slot on a /bhav crop page (Buyer / DealerProduct); these run a
# directory of real shops and what they stock (DukanShop / DukanCatalog /
# DukanItem). The auth and the read-only guard are shared because they are
# infrastructure; nothing else is.
#
# THE PAYMENT MECHANICS ARE DELIBERATELY IDENTICAL to /dukanlisting's — the
# same services/upi.py collect link, the same hand-entered confirmation, the
# same "a upi:// link reports nothing back, so only a human who saw the credit
# may set paid_at" rule. Same rail, separate books.
#
# EVERYTHING HERE IS ADMIN-ENTERED. There is no self-serve form yet, by design:
# shops are found and typed in by hand, and that is also when the plan is set.
# ============================================================

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.routes.admin import admin_db, require_admin
from backend.services import krashi_dukan as dukan

router = APIRouter(prefix="/admin/dukan", tags=["admin-dukan"])


def _write(fn, *args, **kwargs):
    """Read-only guard, worded for this panel.

    Neon's free tier flips the compute read-only without warning, and reads
    keep working throughout — so a shop typed in during an episode would
    otherwise die with a 500 after the owner keyed a whole address off a phone
    call. Say what happened and that nothing was saved.
    """
    from backend.database.db import is_read_only_error
    try:
        return fn(*args, **kwargs)
    except HTTPException:
        raise
    except Exception as e:
        if is_read_only_error(e):
            raise HTTPException(
                503,
                "Database is read-only (Neon plan limit) — nothing was saved. "
                "Write it down and re-enter once the DB accepts writes."
            )
        raise HTTPException(500, str(e))


def _shop_dict(db, row) -> dict:
    """One shop as the panel wants it: the row, plus the two things it can only
    learn by looking elsewhere — how many items it lists, and whether its paid
    season has run out."""
    return {
        "slug": row.slug, "name": row.name,
        "state": row.state or "", "district": row.district or "",
        "address": row.address or "", "phone": row.phone or "",
        "whatsapp": row.whatsapp or "", "license_no": row.license_no or "",
        "gstin": row.gstin or "", "since": row.since or "", "note": row.note or "",
        "lat": row.lat, "lon": row.lon,
        "plan": row.plan, "commission_pct": row.commission_pct,
        "verified": bool(row.verified), "active": bool(row.active),
        "status": row.status, "owner_user_id": row.owner_user_id,
        "called_at": row.called_at.isoformat() if row.called_at else None,
        "call_count": row.call_count or 0, "call_result": row.call_result or "",
        "paid_at": row.paid_at.isoformat() if row.paid_at else None,
        "paid_amount": row.paid_amount, "payment_ref": row.payment_ref or "",
        "paid_until": row.paid_until.isoformat() if row.paid_until else None,
        "live": dukan.is_live(row), "lapsed": dukan.is_lapsed(row),
        "items": len(dukan.items_for_shop(db, row.slug, only_active=False)),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ── shops ───────────────────────────────────────────────────

@router.get("/shops")
async def list_shops(
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.services import upi
    rows = dukan.shop_all(db)
    return {"success": True,
            "shops":  [_shop_dict(db, r) for r in rows],
            "counts": dukan.counts(db),
            "plans":  list(dukan.PLANS),
            "call_results": list(dukan.CALL_RESULTS),
            # So the panel can grey out collect and say why, instead of
            # generating a QR that points nowhere.
            "upi": {"configured": upi.configured(), "vpa": upi.vpa(),
                    "amount": upi.DEFAULT_AMOUNT}}


@router.post("/shops")
async def create_shop(
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    problem = dukan.validate_shop(payload)
    if problem:
        raise HTTPException(400, problem)
    row = _write(dukan.shop_create, db, payload)
    return {"success": True, "shop": _shop_dict(db, row), "counts": dukan.counts(db)}


@router.patch("/shops/{slug}")
async def update_shop(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Also the approve path and the plan switch: {"active": true} or
    {"plan": "commission", "commission_pct": 5}. Both are settable only from
    here — there is no public route into either."""
    current = dukan.shop_get(db, slug)
    if not current:
        raise HTTPException(404, "Unknown shop")
    # Validate only when the payload carries a field validate_shop judges — a
    # lone {"active": true} must not be rejected for having no name in it.
    if any(k in payload for k in ("name", "district", "license_no",
                                  "plan", "commission_pct")):
        merged = _shop_dict(db, current)
        merged.update(payload)
        problem = dukan.validate_shop(merged)
        if problem:
            raise HTTPException(400, problem)
    row = _write(dukan.shop_update, db, slug, payload)
    if not row:
        raise HTTPException(404, "Unknown shop")
    return {"success": True, "shop": _shop_dict(db, row), "counts": dukan.counts(db)}


@router.delete("/shops/{slug}")
async def delete_shop(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Deletes the shop AND every price it listed — see krashi_dukan.shop_delete
    for why that cascade is hand-rolled."""
    if not _write(dukan.shop_delete, db, slug):
        raise HTTPException(404, "Unknown shop")
    return {"success": True, "counts": dukan.counts(db)}


@router.post("/shops/{slug}/call")
async def log_call(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    row = _write(dukan.log_call, db, slug,
                 (payload.get("result") or ""), (payload.get("note") or ""))
    if not row:
        raise HTTPException(404, "Unknown shop")
    return {"success": True, "shop": _shop_dict(db, row), "counts": dukan.counts(db)}


@router.get("/shops/{slug}/collect")
async def collect(
    slug:    str,
    amount:  str = "",
    purpose: str = "",
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """UPI QR + deep link + a ready-to-send WhatsApp message for one shop.

    A request to pay, never a record of one. The payment is only real once a
    human sees it in the bank app and posts it to /payment below. `amount`
    stays editable per request because a first-season price is a real
    negotiation, not a constant — and on the commission plan there is no
    standing number at all, only whatever this month's redemptions came to.
    """
    from backend.services import upi
    row = dukan.shop_get(db, slug)
    if not row:
        raise HTTPException(404, "Unknown shop")
    if not upi.configured():
        raise HTTPException(
            503,
            "UPI is not configured — set KM_UPI_ID and KM_UPI_NAME in the "
            "environment, then restart. Nothing is hardcoded on purpose: a "
            "wrong VPA sends a shopkeeper's money to a stranger."
        )
    pack = upi.collect(row.name or "", row.district or "",
                       amount or None, purpose or "कृषि दुकान लिस्टिंग")
    pack["plan"] = row.plan
    pack["commission_pct"] = row.commission_pct
    return {"success": True, "collect": pack}


@router.post("/shops/{slug}/payment")
async def record_payment(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Mark a shop paid. Hand-entered from the bank app, by design — there is
    no callback that could do it, so this is the only thing that sets paid_at."""
    from backend.services import upi
    amount = upi.clean_amount(payload.get("amount"), default=0)
    if amount < upi.MIN_AMOUNT:
        raise HTTPException(
            400,
            f"Enter the amount actually received (₹{upi.MIN_AMOUNT}–₹{upi.MAX_AMOUNT})")
    months = payload.get("months")
    try:
        months = max(1, min(12, int(months))) if months else None
    except (TypeError, ValueError):
        months = None
    row = _write(dukan.record_payment, db, slug, amount,
                 (payload.get("ref") or ""), months)
    if not row:
        raise HTTPException(404, "Unknown shop")
    return {"success": True, "shop": _shop_dict(db, row), "counts": dukan.counts(db)}


# ── catalogue ───────────────────────────────────────────────

@router.get("/catalog")
async def list_catalog(
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Includes inactive rows — this is the editor, not the shop front. `cats`
    rides along so the panel's category picker is never a second hardcoded
    copy of product.py's list."""
    from backend.routes.product import CAT_LABELS
    rows = dukan.catalog_all(db, only_active=False)
    return {"success": True, "cats": CAT_LABELS, "catalog": [{
        "id": r.id, "slug": r.slug, "cat": r.cat, "emoji": r.emoji or "",
        "name_hi": r.name_hi, "name_en": r.name_en or "",
        "unit_hi": r.unit_hi or "", "desc_hi": r.desc_hi or "",
        "image_url": r.image_url or "", "has_image": bool(r.image_mime),
        "active": bool(r.active), "sort_order": r.sort_order,
    } for r in rows]}


@router.post("/catalog")
async def create_catalog(
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    problem = dukan.validate_catalog(payload)
    if problem:
        raise HTTPException(400, problem)
    row = _write(dukan.catalog_create, db, payload)
    return {"success": True, "slug": row.slug, "id": row.id, "counts": dukan.counts(db)}


@router.patch("/catalog/{slug}")
async def update_catalog(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    row = _write(dukan.catalog_update, db, slug, payload)
    if not row:
        raise HTTPException(404, "Unknown product (or the Hindi name was blanked)")
    return {"success": True, "slug": row.slug}


@router.delete("/catalog/{slug}")
async def delete_catalog(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Deletes the product AND every shop's price for it. Nothing else could
    happen: those rows would point at a page that no longer resolves."""
    if not _write(dukan.catalog_delete, db, slug):
        raise HTTPException(404, "Unknown product")
    return {"success": True, "counts": dukan.counts(db)}


@router.post("/catalog/{slug}/image")
async def upload_catalog_image(
    slug: str,
    file: UploadFile = File(...),
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Same pipeline as admin.py's dealer product photo: re-encoded small and
    stored in Postgres, because Render's free tier wipes uploads/ on restart."""
    import base64
    import io

    from PIL import Image, ImageOps

    row = dukan.catalog_get(db, slug)
    if not row:
        raise HTTPException(404, "Unknown product")

    raw = b""
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        raw += chunk
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(400, "Image too large — 8 MB max")
    if not raw:
        raise HTTPException(400, "Empty upload")

    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)          # honour phone rotation
        img = img.convert("RGB")
        # contain, not a centre-crop — a square crop cuts the label off a bag.
        img.thumbnail((480, 480), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=82, method=6)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Could not read that image — try another file")

    def _save():
        row.image_data = base64.b64encode(buf.getvalue()).decode("ascii")
        row.image_mime = "image/webp"
        db.commit()
        return row

    _write(_save)
    return {"success": True, "bytes": len(buf.getvalue())}


@router.delete("/catalog/{slug}/image")
async def delete_catalog_image(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    row = dukan.catalog_get(db, slug)
    if not row:
        raise HTTPException(404, "Unknown product")

    def _clear():
        row.image_data = None
        row.image_mime = None
        db.commit()
        return row

    _write(_clear)
    return {"success": True}


# ── items: one shop's price for one catalogue product ───────

@router.get("/shops/{slug}/items")
async def list_items(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    if not dukan.shop_get(db, slug):
        raise HTTPException(404, "Unknown shop")
    catalog = {c.slug: c for c in dukan.catalog_all(db, only_active=False)}
    rows = dukan.items_for_shop(db, slug, only_active=False)
    return {"success": True, "items": [{
        "id": i.id, "product_slug": i.product_slug,
        # The catalogue name rides along so the panel never joins two responses
        # to render a row — and says so plainly when a product was deleted out
        # from under an item.
        "name_hi": (catalog[i.product_slug].name_hi
                    if i.product_slug in catalog else "(हटाया गया उत्पाद)"),
        "price": i.price, "mrp": i.mrp, "off": dukan.off_pct(i.price, i.mrp),
        "unit_hi": i.unit_hi or "", "note": i.note or "",
        "in_stock": bool(i.in_stock), "active": bool(i.active),
        "sort_order": i.sort_order,
        "updated_at": i.updated_at.isoformat() if i.updated_at else None,
    } for i in rows]}


@router.post("/shops/{slug}/items")
async def create_item(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    if not dukan.shop_get(db, slug):
        raise HTTPException(404, "Unknown shop")
    problem = dukan.validate_item(db, payload)
    if problem:
        raise HTTPException(400, problem)
    row = _write(dukan.item_create, db, slug, payload)
    if not row:
        raise HTTPException(400, "यह उत्पाद इस दुकान में पहले से जुड़ा है — उसी को बदलें")
    return {"success": True, "id": row.id, "counts": dukan.counts(db)}


@router.patch("/items/{item_id}")
async def update_item(
    item_id: int,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    if "price" in payload or "mrp" in payload:
        current = dukan.item_get(db, item_id)
        if not current:
            raise HTTPException(404, "Unknown item")
        problem = dukan.validate_item(db, {
            "product_slug": current.product_slug,
            "price": payload.get("price", current.price),
            "mrp":   payload.get("mrp",   current.mrp)})
        if problem:
            raise HTTPException(400, problem)
    row = _write(dukan.item_update, db, item_id, payload)
    if not row:
        raise HTTPException(404, "Unknown item")
    return {"success": True}


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    if not _write(dukan.item_delete, db, item_id):
        raise HTTPException(404, "Unknown item")
    return {"success": True, "counts": dukan.counts(db)}
