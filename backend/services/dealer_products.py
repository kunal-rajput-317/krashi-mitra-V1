# ============================================================
# services/dealer_products.py
# The catalogue behind /dukan/product — what a paying dealer actually sells.
#
# services/dealers.py owns the `buyers` row (who he is, where, is he paid).
# This module owns `dealer_products` (what he sells, at what price), and it is
# the only thing that writes to that table. Same split, same reason: a render
# path must never be able to open a write transaction against a Neon compute
# that has gone read-only.
#
# WHY THE SHAPE COPIES THE SHOP. name_hi / name_en / price / mrp / unit_hi are
# the fields routes/product.py::_hub_card() already renders, so a dealer's card
# and a KrashiMitra catalogue card are the same object to a farmer's eye. One
# design language, one discount calculation (off_pct below is the same formula
# as product.py::_off_pct), and no second visual vocabulary to keep in sync.
#
# ATTACHED TO THE ACCOUNT, NOT ONE DISTRICT. A dealer paying for three districts
# types his catalogue once. Lookups therefore key on owner_user_id when the
# listing has one and fall back to buyer_slug for admin-typed rows.
#
# THE BLOB IS NEVER LOADED ON A RENDER. DealerProduct.image_data is deferred()
# in the model and only image_of() below ever touches it; every card reads the
# `image_mime` presence flag and points at /dukan/product-image/<id>.webp.
# ============================================================
from datetime import datetime

from backend.database.db import DealerProduct
from backend.services import buyers as buyers_read

# A dealer is selling, not running a warehouse — and the card grid on a /bhav
# page has to stay scannable. Enough for a real shop, few enough that the panel
# never turns into a catalogue dump.
MAX_PER_DEALER = 12

_MAX = {"name_hi": 120, "name_en": 120, "unit_hi": 60, "badge": 24}


def off_pct(price, mrp) -> int:
    """The "% off" pill. Same formula as routes/product.py::_off_pct — a
    dealer's discount must not be computed differently from the shop's."""
    try:
        price, mrp = int(price or 0), int(mrp or 0)
    except (TypeError, ValueError):
        return 0
    return round((1 - price / mrp) * 100) if mrp > price > 0 else 0


def as_dict(p: DealerProduct) -> dict:
    """A product in the shape a card renders from. No blob — see the module
    docstring; `has_image` is what the template checks."""
    return {
        "id":        p.id,
        "name_hi":   p.name_hi or "",
        "name_en":   p.name_en or "",
        "price":     p.price,
        "mrp":       p.mrp,
        "unit_hi":   p.unit_hi or "",
        "badge":     p.badge or "",
        "off":       off_pct(p.price, p.mrp),
        "has_image": bool(p.image_mime),
        "active":    bool(p.active),
        # Cache-buster for the image URL, which is keyed by an id that never
        # changes and served with a long max-age.
        "v":         int(p.updated_at.timestamp()) if p.updated_at else 0,
    }


def _clean(data: dict) -> dict:
    """Whole rupees and trimmed strings. Prices are quoted in round numbers and
    paise on a listing card is a typo every time."""
    out = {}
    for field, limit in _MAX.items():
        if field in data:
            out[field] = (str(data.get(field) or "").strip()[:limit]) or None
    for field in ("price", "mrp"):
        if field in data:
            try:
                n = int(round(float(str(data.get(field)).strip())))
            except (TypeError, ValueError):
                n = 0
            out[field] = n if 0 < n <= 10_000_000 else None
    if "active" in data:
        out["active"] = bool(data.get("active"))
    if "sort_order" in data:
        try:
            out["sort_order"] = int(data.get("sort_order") or 0)
        except (TypeError, ValueError):
            out["sort_order"] = 0
    return out


def validate(data: dict) -> str:
    """The minimum a card needs to be worth rendering. "" when fine."""
    if len((str(data.get("name_hi") or "")).strip()) < 2:
        return "प्रोडक्ट का नाम डालें"
    try:
        price = int(round(float(str(data.get("price")).strip())))
    except (TypeError, ValueError):
        return "सही कीमत डालें"
    if price <= 0:
        return "सही कीमत डालें"
    # An MRP below the price would render a negative "% off" — it is a typo, not
    # a discount, and it reaches a farmer as a lie about a saving.
    mrp = data.get("mrp")
    if mrp not in (None, "", 0):
        try:
            if int(round(float(str(mrp).strip()))) < price:
                return "MRP कीमत से कम नहीं हो सकता"
        except (TypeError, ValueError):
            return "सही MRP डालें"
    return ""


def for_buyer(db, buyer_slug: str, owner_user_id=None, *, only_active=True) -> list:
    """This dealer's catalogue, as card dicts.

    Keys on the ACCOUNT when there is one so a multi-district dealer types his
    products once; falls back to the single row for admin-typed listings.
    """
    q = db.query(DealerProduct)
    if owner_user_id:
        q = q.filter(DealerProduct.owner_user_id == owner_user_id)
    else:
        q = q.filter(DealerProduct.buyer_slug == buyer_slug)
    if only_active:
        q = q.filter(DealerProduct.active.is_(True))
    rows = q.order_by(DealerProduct.sort_order.asc(),
                      DealerProduct.id.asc()).all()
    return [as_dict(r) for r in rows]


def create(db, buyer_slug: str, owner_user_id, data: dict) -> DealerProduct | None:
    if count_for(db, buyer_slug, owner_user_id) >= MAX_PER_DEALER:
        return None
    row = DealerProduct(buyer_slug=buyer_slug, owner_user_id=owner_user_id or None,
                        price=0, name_hi="")
    for key, value in _clean(data).items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    buyers_read.invalidate()
    return row


def update(db, product_id: int, data: dict) -> DealerProduct | None:
    row = db.query(DealerProduct).filter(DealerProduct.id == product_id).first()
    if not row:
        return None
    for key, value in _clean(data).items():
        setattr(row, key, value)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    buyers_read.invalidate()
    return row


def delete(db, product_id: int) -> bool:
    row = db.query(DealerProduct).filter(DealerProduct.id == product_id).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    buyers_read.invalidate()
    return True


def count_for(db, buyer_slug: str, owner_user_id=None) -> int:
    q = db.query(DealerProduct)
    if owner_user_id:
        q = q.filter(DealerProduct.owner_user_id == owner_user_id)
    else:
        q = q.filter(DealerProduct.buyer_slug == buyer_slug)
    return q.count()


def get(db, product_id: int) -> DealerProduct | None:
    return db.query(DealerProduct).filter(DealerProduct.id == product_id).first()


def set_image(db, product_id: int, b64: str | None,
              mime: str = "image/webp") -> DealerProduct | None:
    """Attach (or clear, with b64=None) the product photo.

    Both columns move together: `image_mime` is the presence flag every card
    checks, and leaving it set with no blob behind it renders a broken <img>
    on a farmer-facing page.
    """
    row = db.query(DealerProduct).filter(DealerProduct.id == product_id).first()
    if not row:
        return None
    row.image_data = b64 or None
    row.image_mime = mime if b64 else None
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    buyers_read.invalidate()
    return row


def image_of(db, product_id: int) -> tuple[str, str] | None:
    """(base64, mime) or None. The only reader of the deferred blob."""
    row = (db.query(DealerProduct)
             .filter(DealerProduct.id == product_id,
                     DealerProduct.image_mime.isnot(None))
             .first())
    if not row or not row.image_data:
        return None
    return row.image_data, row.image_mime or "image/webp"


def all_by_key(db) -> dict:
    """Every active product, grouped for the read cache in services/buyers.py.

    Returns {("u", owner_user_id): [...], ("s", buyer_slug): [...]} so that
    module can attach a catalogue to each buyer dict in ONE query rather than
    one per dealer per page render.
    """
    out: dict = {}
    rows = (db.query(DealerProduct)
              .filter(DealerProduct.active.is_(True))
              .order_by(DealerProduct.sort_order.asc(), DealerProduct.id.asc())
              .all())
    for r in rows:
        key = ("u", r.owner_user_id) if r.owner_user_id else ("s", r.buyer_slug)
        out.setdefault(key, []).append(as_dict(r))
    return out
