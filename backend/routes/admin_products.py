# ============================================================
# routes/admin_products.py
# Admin API for the /product catalogue — /admin/catalogue/*
#
# WHAT THIS UNLOCKS. The catalogue was a `const PRODUCTS = [...]` literal
# inside frontend/shop.html: adding a product meant hand-editing a 94-entry JS
# array and shipping a deploy. Every product is also an affiliate placement, so
# a catalogue that could only grow at a laptop was revenue that could only grow
# at a laptop. This router is the phone-shaped version of that edit.
#
# THE MODEL IS OVERLAY, NOT OWNERSHIP. services/shop_catalog.py merges these
# rows over shop.html rather than replacing it, so:
#
#   * editing a committed product writes a NEW row with the same slug, and the
#     original entry in shop.html is never touched;
#   * DELETE on such a row is therefore a REVERT — the committed product shows
#     through again — while DELETE on a panel-added product really removes it;
#   * a product that must come down but lives in shop.html is switched off with
#     active:false, which hides it everywhere without destroying anything.
#
# Nothing here can damage the committed catalogue, which is the property that
# makes it safe to hand this to someone editing from a phone at a mandi.
#
# NEON GOES READ-ONLY WITHOUT WARNING, and reads keep working throughout — so
# the panel looks healthy while every save 500s. Same guard and the same
# wording as admin_dukan.py and admin_articles.py: say that nothing was saved.
# ============================================================
import base64
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.routes.admin import admin_db, require_admin
from backend.services import shop_catalog

# NOT /admin/products — routes/admin.py has owned that prefix for dealer
# products since before this existed, and its {product_id} is an integer, so a
# slug here would 422 against the wrong route. "catalogue" is also the more
# honest name: this edits the KrashiMitra catalogue, not a dealer's stock.
router = APIRouter(prefix="/admin/catalogue", tags=["admin-catalogue"])

# A pack shot off a phone camera is a few MB; past this it is either a mistake
# or a RAW file, and the 512 MB dyno cannot afford to find out which.
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _write(fn, *args, **kwargs):
    """Run a write, and name the one failure that is not a bug."""
    from backend.database.db import is_read_only_error
    try:
        return fn(*args, **kwargs)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        if is_read_only_error(e):
            raise HTTPException(
                503,
                "Database is read-only (Neon plan limit) — nothing was saved. "
                "Leave the form open and save again once the DB accepts writes."
            )
        raise HTTPException(500, str(e))


def _row_dict(r, baseline: set) -> dict:
    return {
        "slug": r.slug, "cat": r.cat or "", "emoji": r.emoji or "",
        "badge": r.badge or "", "badge_class": r.badge_class or "",
        "name_hi": r.name_hi or "", "name_en": r.name_en or "",
        "name_kn": r.name_kn or "",
        "desc_hi": r.desc_hi or "", "desc_en": r.desc_en or "",
        "desc_kn": r.desc_kn or "",
        "unit_hi": r.unit_hi or "", "unit_en": r.unit_en or "",
        "unit_kn": r.unit_kn or "",
        "price": r.price, "mrp": r.mrp,
        "image_url": r.image_url or "", "has_image": bool(r.image_mime),
        "img": (f"/product/img/{r.id}.webp" if r.image_mime else (r.image_url or "")),
        "affil_amazon": r.affil_amazon or "",
        "affil_flipkart": r.affil_flipkart or "",
        "active": bool(r.active), "sort_order": r.sort_order,
        # The one thing the panel cannot work out for itself, and the thing
        # that decides whether "delete" means revert or remove.
        "source": "override" if r.slug in baseline else "added",
    }


@router.get("")
async def list_products(
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Everything the editor needs in one payload.

    `catalogue` is the MERGED list — what /product actually serves right now —
    so the panel shows the live catalogue rather than only the rows it has
    written. `edited` is the overlay, keyed by slug, so a row can be opened for
    editing. `cats` rides along so the category picker is never a second
    hardcoded copy of product.py's list.
    """
    from backend.database.db import ShopProduct
    from backend.routes.product import CAT_LABELS, _get_products

    baseline = shop_catalog.baseline_slugs()
    rows = db.query(ShopProduct).order_by(ShopProduct.sort_order, ShopProduct.id).all()
    edited = {r.slug: _row_dict(r, baseline) for r in rows}

    def _live_link(v) -> str:
        """'not_available_x.webp' is how the catalogue spells "no link". It must
        never reach the panel's link box, or saving the row would write that
        placeholder back as if it were a URL."""
        v = (v or "").strip()
        return "" if v.startswith("not_available_") else v

    live = [{
        "slug": p["slug"], "name_hi": p.get("name_hi", ""),
        "name_en": p.get("name_en", ""), "cat": p.get("cat", ""),
        "emoji": p.get("emoji", ""), "price": p.get("price"),
        "unit_hi": p.get("unit_hi", ""), "img": p.get("img", ""),
        # The full URLs ride along so the panel can edit a price or paste an
        # affiliate link inline, without a round trip per row just to read what
        # is already on screen.
        "affil_amazon": _live_link(p.get("affil_amazon")),
        "affil_flipkart": _live_link(p.get("affil_flipkart")),
        "has_amazon": bool(_live_link(p.get("affil_amazon"))),
        "state": ("added" if p["slug"] in edited and p["slug"] not in baseline
                  else "edited" if p["slug"] in edited else "committed"),
    } for p in _get_products()]

    return {"success": True, "cats": CAT_LABELS, "catalogue": live,
            "edited": edited, "hidden": sorted(shop_catalog.hidden_slugs(db))}


@router.get("/{slug}")
async def get_product(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """The editable row for one product.

    When no overlay row exists yet, this returns the committed product's own
    values with `source: "committed"`, so the form opens pre-filled with what
    the page currently shows instead of blank — the difference between editing
    a product and retyping one.
    """
    row = shop_catalog.get(db, slug)
    if row:
        return {"success": True, "product": _row_dict(row, shop_catalog.baseline_slugs())}

    from backend.routes.product import _get_by_slug
    p = _get_by_slug().get(slug)
    if not p:
        raise HTTPException(404, "Unknown product")
    return {"success": True, "product": {
        "slug": slug, "cat": p.get("cat", ""), "emoji": p.get("emoji", ""),
        "badge": p.get("badge", ""), "badge_class": p.get("badgeClass", ""),
        "name_hi": p.get("name_hi", ""), "name_en": p.get("name_en", ""),
        "name_kn": p.get("name_kn", ""),
        "desc_hi": p.get("desc_hi", ""), "desc_en": p.get("desc_en", ""),
        "desc_kn": p.get("desc_kn", ""),
        "unit_hi": p.get("unit_hi", ""), "unit_en": p.get("unit_en", ""),
        "unit_kn": p.get("unit_kn", ""),
        "price": p.get("price"), "mrp": p.get("mrp"),
        "image_url": p.get("img", ""), "has_image": False, "img": p.get("img", ""),
        "affil_amazon": p.get("affil_amazon", ""),
        "affil_flipkart": p.get("affil_flipkart", ""),
        "active": True, "sort_order": 0, "source": "committed",
    }}


@router.post("/{slug}/preview", response_class=HTMLResponse)
async def preview_product(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """The real product page with unsaved edits applied, stored nowhere.

    Rendered by routes/product.py::render_product — the same function that
    serves the live page, not a copy that can drift from it. Returned as HTML
    so the panel can drop it into a 390px iframe, which is the width almost all
    of this site's traffic reads at and the only width where a broken layout is
    visible.

    Nothing is written. A preview of a product that does not exist yet is
    allowed too: the payload is merged onto an empty skeleton, so "+ नया
    प्रोडक्ट" can be looked at before it is saved.
    """
    from backend.routes.product import render_product
    from backend.services.shop_catalog import ADDED_DEFAULTS

    problem = shop_catalog.validate(payload, existing=True)
    if problem:
        raise HTTPException(400, problem)

    from backend.routes.product import _get_by_slug
    base = _get_by_slug().get(slug) or {**ADDED_DEFAULTS, "slug": slug, "id": 0}
    p = dict(base)
    for k, v in payload.items():
        if k in ("active", "sort_order"):
            continue
        key = "badgeClass" if k == "badge_class" else ("img" if k == "image_url" else k)
        if k in ("price", "mrp"):
            try:
                p[key] = int(v) if str(v).strip() not in ("", "None") else 0
            except (TypeError, ValueError):
                pass
        else:
            p[key] = (v or "").strip()
    return render_product(p)


@router.post("")
async def create_product(
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    problem = shop_catalog.validate(payload)
    if problem:
        raise HTTPException(400, problem)
    row = _write(shop_catalog.create, db, payload)
    return {"success": True, "slug": row.slug,
            "url": f"/product/{row.slug}"}


@router.patch("/{slug}")
async def update_product(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Edit a product.

    A slug with no overlay row yet is a committed product being edited for the
    first time: the row is created here from the page's current values plus the
    change, so the caller never has to know which of the two cases it is in.
    """
    problem = shop_catalog.validate(payload, existing=True)
    if problem:
        raise HTTPException(400, problem)

    if not shop_catalog.get(db, slug):
        from backend.routes.product import _get_by_slug
        base = _get_by_slug().get(slug)
        if not base:
            raise HTTPException(404, "Unknown product")
        seed = {
            "slug": slug, "cat": base.get("cat", "misc"),
            "name_hi": base.get("name_hi", ""), "name_en": base.get("name_en", ""),
            "name_kn": base.get("name_kn", ""),
            "desc_hi": base.get("desc_hi", ""), "desc_en": base.get("desc_en", ""),
            "desc_kn": base.get("desc_kn", ""),
            "unit_hi": base.get("unit_hi", ""), "unit_en": base.get("unit_en", ""),
            "unit_kn": base.get("unit_kn", ""),
            "emoji": base.get("emoji", ""), "badge": base.get("badge", ""),
            "badge_class": base.get("badgeClass", ""),
            "price": base.get("price"), "mrp": base.get("mrp"),
            "image_url": base.get("img", ""),
            "affil_amazon": base.get("affil_amazon", ""),
            "affil_flipkart": base.get("affil_flipkart", ""),
        }
        seed.update(payload)
        row = _write(shop_catalog.create, db, seed)
        return {"success": True, "slug": row.slug, "created_override": True}

    row = _write(shop_catalog.update, db, slug, payload)
    if not row:
        raise HTTPException(404, "Unknown product")
    return {"success": True, "slug": row.slug}


@router.delete("/{slug}")
async def delete_product(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Remove the overlay row — a revert for a committed product, a real delete
    for one added here. To take a committed product DOWN, PATCH it with
    active:false instead; this endpoint cannot touch shop.html."""
    row = shop_catalog.get(db, slug)
    if not row:
        raise HTTPException(404, "Nothing to remove — this product is not edited here")
    reverted = slug in shop_catalog.baseline_slugs()
    _write(shop_catalog.delete, db, slug)
    return {"success": True, "reverted": reverted}


@router.post("/{slug}/image")
async def upload_product_image(
    slug: str,
    file: UploadFile = File(...),
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Replace a product's photo, stored in Postgres.

    This is the endpoint that fixes the catalogue's oldest content bug: most
    products reuse a handful of stock pack shots, so the tarpaulin shows a drip
    kit and the storage bags show another company's branded feed sack. Upload
    the right picture and the merge prefers it over the committed path — on the
    product page, the hub card and anywhere else that reads the catalogue.
    """
    from PIL import Image, ImageOps

    row = shop_catalog.get(db, slug)
    if not row:
        # Editing a committed product's photo is the same first-edit case as
        # PATCH: seed the overlay row, then attach the image to it.
        from backend.routes.product import _get_by_slug
        base = _get_by_slug().get(slug)
        if not base:
            raise HTTPException(404, "Unknown product")
        row = _write(shop_catalog.create, db, {
            "slug": slug, "cat": base.get("cat", "misc"),
            "name_hi": base.get("name_hi", ""), "name_en": base.get("name_en", ""),
            "unit_hi": base.get("unit_hi", ""), "desc_hi": base.get("desc_hi", ""),
            "emoji": base.get("emoji", ""), "price": base.get("price"),
            "mrp": base.get("mrp"), "image_url": base.get("img", ""),
            "affil_amazon": base.get("affil_amazon", ""),
            "affil_flipkart": base.get("affil_flipkart", ""),
        })

    raw = b""
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        raw += chunk
        if len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(400, "Image too large — 8 MB max")
    if not raw:
        raise HTTPException(400, "Empty upload")

    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)      # honour phone rotation
        img = img.convert("RGB")
        # contain, not a centre crop — a square crop cuts the label off a bag.
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
        shop_catalog.invalidate()
        return row

    _write(_save)
    return {"success": True, "bytes": len(buf.getvalue()),
            "img": f"/product/img/{row.id}.webp"}


@router.delete("/{slug}/image")
async def delete_product_image(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Drop the uploaded photo and fall back to image_url (and through that, to
    whatever shop.html committed)."""
    row = shop_catalog.get(db, slug)
    if not row:
        raise HTTPException(404, "Unknown product")

    def _clear():
        row.image_data = None
        row.image_mime = None
        db.commit()
        shop_catalog.invalidate()

    _write(_clear)
    return {"success": True}
