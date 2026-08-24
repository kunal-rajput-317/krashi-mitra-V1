# ============================================================
# services/krashi_dukan.py
# कृषि दुकान — the local shop directory behind /krashi_dukan
#
# WHAT THIS IS. Real shops near the farmer, their real stock, their real
# counter price. We hold no inventory, take no payment for goods, promise no
# delivery and guarantee nothing about what is sold. The site's job ends at
# "this shop, this far away, has it at this price".
#
# WHAT THIS IS NOT. Not /dukanlisting — that sells an advertisement slot on a
# /bhav crop page and is a different business with different tables. Not /shop
# or /product either: that catalogue is untouched and still runs off the
# PRODUCTS array in frontend/shop.html.
#
# THE ONE RULE THAT CANNOT BEND. Shops are ranked by distance from the farmer
# and by nothing else. Not by plan, not by what they paid, not by how recently
# they paid. A directory whose order can be bought stops being worth reading,
# and the ordering is the only thing we actually have to sell.
# ============================================================

import math
import re
from datetime import datetime, timedelta

from backend.database.db import DukanCatalog, DukanItem, DukanShop
from backend.services import district_geo, free_month

# A season, not a month — the unit a shopkeeper actually thinks in, and the
# same span services/placements.py already collects /dukanlisting fees over.
# It is the fallback only: the term that actually applies is the shop's own
# `plan_months`, agreed on the call and settable per shop.
SEASON_MONTHS = 3

# What a listing may be sold in. Not a free integer: every extra length is a
# renewal date the admin has to remember and a sentence the caller has to say,
# and four options already cover "try it for a month" through "leave me alone
# for a year". 1 and 12 are also the two ends the guard clamps to everywhere.
PLAN_MONTHS = (1, 3, 6, 12)
MIN_PLAN_MONTHS, MAX_PLAN_MONTHS = 1, 12

# How near an expiry has to be before the panel says so. A shopkeeper needs
# time to find the money and a reason to bother; two weeks is long enough to
# ring twice and short enough that the call is still about *this* season.
EXPIRING_SOON_DAYS = 14

PLANS = ("season", "commission")

# What the admin can record after ringing a shop. Mirrors dealers.CALL_RESULTS
# in spirit: a no-answer is worth retrying, not forgetting.
CALL_RESULTS = ("interested", "callback", "no-answer", "not-interested", "wrong-number")

# Longest a farmer would plausibly travel for a bag of urea. Beyond this a
# "nearby shop" is a lie, so the product page stops offering one.
MAX_DISTANCE_KM = 150.0


# ── slugs ───────────────────────────────────────────────────

def slugify(text: str) -> str:
    """ASCII slug, lowercase. Devanagari has no useful transliteration here, so
    a purely Hindi name falls back to the caller's alternative rather than
    producing an empty segment."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower())
    return re.sub(r"-{2,}", "-", s).strip("-")


def unique_slug(db, name: str, district: str = "", model=DukanShop) -> str:
    """`name-district`, then `-2`, `-3` … until it is free.

    The district rides in the slug on purpose: two "Kisan Krishi Kendra"s in
    different districts are the common case, not the edge case, and
    `kisan-krishi-kendra-bareilly` is a URL a farmer can read.
    """
    base = slugify(name) or "dukan"
    if district:
        d = slugify(district)
        if d and d not in base:
            base = f"{base}-{d}"
    slug, n = base, 2
    while db.query(model).filter(model.slug == slug).first():
        slug, n = f"{base}-{n}", n + 1
    return slug


# ── catalogue ───────────────────────────────────────────────

def validate_catalog(data: dict) -> str:
    """"" when the row is fit to save, else the message to show the admin."""
    if not (data.get("name_hi") or "").strip():
        return "उत्पाद का हिंदी नाम ज़रूरी है"
    if not (data.get("cat") or "").strip():
        return "श्रेणी चुनें"
    return ""


def catalog_all(db, only_active: bool = True) -> list:
    q = db.query(DukanCatalog)
    if only_active:
        q = q.filter(DukanCatalog.active.is_(True))
    return q.order_by(DukanCatalog.sort_order, DukanCatalog.name_hi).all()


def catalog_get(db, slug: str):
    return db.query(DukanCatalog).filter(
        DukanCatalog.slug == (slug or "").lower()).first()


def catalog_create(db, data: dict) -> DukanCatalog:
    slug = (data.get("slug") or "").strip().lower() or unique_slug(
        db, data.get("name_en") or data.get("name_hi") or "", model=DukanCatalog)
    row = DukanCatalog(
        slug       = slug,
        cat        = (data.get("cat") or "misc").strip(),
        emoji      = (data.get("emoji") or "").strip()[:8] or None,
        name_hi    = (data.get("name_hi") or "").strip(),
        name_en    = (data.get("name_en") or "").strip() or None,
        unit_hi    = (data.get("unit_hi") or "").strip() or None,
        desc_hi    = (data.get("desc_hi") or "").strip() or None,
        image_url  = (data.get("image_url") or "").strip() or None,
        active     = bool(data.get("active", True)),
        sort_order = int(data.get("sort_order") or 0),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def catalog_update(db, slug: str, data: dict):
    row = catalog_get(db, slug)
    if not row:
        return None
    for field in ("cat", "emoji", "name_hi", "name_en", "unit_hi",
                  "desc_hi", "image_url"):
        if field in data:
            value = (data.get(field) or "").strip()
            setattr(row, field, value or None)
    if "active" in data:
        row.active = bool(data["active"])
    if "sort_order" in data:
        row.sort_order = int(data.get("sort_order") or 0)
    # name_hi is the one field that may not be blanked — it is the card title
    # and the <h1>, and an empty one renders a nameless product page.
    if not (row.name_hi or "").strip():
        return None
    db.commit()
    db.refresh(row)
    return row


def catalog_delete(db, slug: str) -> bool:
    """Delete the product AND every shop's price for it.

    Leaving the items behind would strand rows pointing at a product page that
    no longer resolves — they would be invisible, uneditable, and would still
    count against the shop's listing. Cascade by hand because the join is by
    slug, not by a foreign key (see DukanItem's docstring).
    """
    row = catalog_get(db, slug)
    if not row:
        return False
    db.query(DukanItem).filter(DukanItem.product_slug == row.slug).delete()
    db.delete(row)
    db.commit()
    return True


# ── shops ───────────────────────────────────────────────────

def validate_shop(data: dict) -> str:
    if not (data.get("name") or "").strip():
        return "दुकान का नाम ज़रूरी है"
    if not (data.get("district") or "").strip():
        return "ज़िला ज़रूरी है — दूरी इसी से निकलती है"
    if not (data.get("license_no") or "").strip():
        return "लाइसेंस नंबर ज़रूरी है"
    plan = (data.get("plan") or "season").strip()
    if plan not in PLANS:
        return f"प्लान '{plan}' मान्य नहीं है"
    if plan == "commission":
        try:
            pct = float(data.get("commission_pct") or 0)
        except (TypeError, ValueError):
            return "कमीशन प्रतिशत एक संख्या होनी चाहिए"
        if not (0 < pct <= 30):
            return "कमीशन 0 से 30% के बीच होना चाहिए"
    if str(data.get("plan_months") or "").strip():
        try:
            months = int(float(str(data["plan_months"]).strip()))
        except (TypeError, ValueError):
            return "प्लान की अवधि महीनों में लिखें"
        if not (MIN_PLAN_MONTHS <= months <= MAX_PLAN_MONTHS):
            return (f"प्लान की अवधि {MIN_PLAN_MONTHS} से {MAX_PLAN_MONTHS} "
                    "महीने के बीच होनी चाहिए")
    return ""


def clean_months(value, default: int = SEASON_MONTHS) -> int:
    """A month count that is always sane, from anything a form or a JSON body
    can hand over. Clamped rather than rejected: this runs after validation, on
    the write path, where a silently-wrong expiry date is worse than a blunt
    one — a 0 would list a shop that is dark the moment it pays."""
    try:
        months = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default
    return max(MIN_PLAN_MONTHS, min(MAX_PLAN_MONTHS, months))


def plan_months_of(row) -> int:
    """The shop's agreed term. Rows written before the column existed read NULL
    and were on the 3-month season by default, so that is what they get."""
    return clean_months(getattr(row, "plan_months", None), SEASON_MONTHS)


def _apply_shop(row: DukanShop, data: dict) -> None:
    for field in ("name", "state", "district", "address", "phone", "whatsapp",
                  "license_no", "gstin", "since", "note", "call_result"):
        if field in data:
            setattr(row, field, (data.get(field) or "").strip() or None)
    if "plan" in data:
        plan = (data.get("plan") or "season").strip()
        row.plan = plan if plan in PLANS else "season"
    if "commission_pct" in data:
        try:
            row.commission_pct = float(data["commission_pct"]) or None
        except (TypeError, ValueError):
            row.commission_pct = None
    # A shop on the season plan has no percentage — leaving a stale one behind
    # would show a commission rate on a receipt for a flat fee.
    if row.plan == "season":
        row.commission_pct = None
    if "plan_months" in data:
        row.plan_months = clean_months(data["plan_months"], plan_months_of(row))
    for flag in ("verified", "active"):
        if flag in data:
            setattr(row, flag, bool(data[flag]))
    if "status" in data:
        row.status = (data.get("status") or "new").strip() or "new"
    if "owner_user_id" in data:
        try:
            row.owner_user_id = int(data["owner_user_id"]) or None
        except (TypeError, ValueError):
            row.owner_user_id = None
    for coord in ("lat", "lon"):
        if coord in data and str(data.get(coord) or "").strip():
            try:
                setattr(row, coord, float(data[coord]))
            except (TypeError, ValueError):
                pass


def geocode(row: DukanShop) -> bool:
    """Fill lat/lon from the district centroid when nobody typed better ones.

    A centroid is coarse — it puts every shop in Bareilly at the same point —
    but the question the product page asks is "which of these towns is nearer",
    and for that a centroid is exactly as good as a rooftop pin. Returns
    whether anything changed, so the caller knows to commit.
    """
    if row.lat is not None and row.lon is not None:
        return False
    coord = district_geo.coord_for(row.state or "", row.district or "")
    if not coord:
        return False
    row.lat, row.lon = coord
    return True


def shop_get(db, slug: str):
    return db.query(DukanShop).filter(DukanShop.slug == (slug or "").lower()).first()


def shop_all(db, only_live: bool = False) -> list:
    q = db.query(DukanShop)
    if only_live:
        q = q.filter(DukanShop.active.is_(True))
    rows = q.order_by(DukanShop.district, DukanShop.name).all()
    return [r for r in rows if is_live(r)] if only_live else rows


def shop_create(db, data: dict) -> DukanShop:
    row = DukanShop(
        slug = (data.get("slug") or "").strip().lower() or unique_slug(
            db, data.get("name") or "", data.get("district") or ""),
        name = (data.get("name") or "").strip(),
        plan = (data.get("plan") or "season").strip(),
    )
    _apply_shop(row, data)
    geocode(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def shop_update(db, slug: str, data: dict):
    row = shop_get(db, slug)
    if not row:
        return None
    _apply_shop(row, data)
    geocode(row)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def shop_delete(db, slug: str) -> bool:
    """Same hand-rolled cascade as catalog_delete, for the same reason."""
    row = shop_get(db, slug)
    if not row:
        return False
    db.query(DukanItem).filter(DukanItem.shop_slug == row.slug).delete()
    db.delete(row)
    db.commit()
    return True


def log_call(db, slug: str, result: str, note: str = ""):
    """Record that the shop was rung. `called_at` is what the call sheet reads
    to stop the same number being dialled twice in a morning."""
    row = shop_get(db, slug)
    if not row:
        return None
    row.called_at   = datetime.utcnow()
    row.call_count  = (row.call_count or 0) + 1
    row.call_result = (result or "").strip()[:40] or None
    if note:
        row.note = note.strip()[:400]
    if row.status == "new":
        row.status = "called"
    db.commit()
    db.refresh(row)
    return row


def record_payment(db, slug: str, amount: int, ref: str = "",
                   months: int | None = None):
    """Money actually arrived — typed in by hand, and that is the design.

    Copied deliberately from dealers.record_payment: a upi:// link hands off to
    the shopkeeper's own app and reports nothing back, so `paid_at` means one
    thing only — a human saw the credit in the bank app. Nothing automated may
    ever set it, because an auto-ticked "paid" is a fabricated receipt.

    Paying also lists the shop. The admin who just watched the money land has
    already made the trust decision; making them tick `active` separately only
    creates a shop that paid and never appeared.

    `months` is the override for this one payment — half a season taken as a
    part payment, a free month added to close a haggle. Left out, the shop's
    own agreed term applies, which is what a plain renewal wants: the caller
    types the amount and the date moves by exactly what was sold.
    """
    row = shop_get(db, slug)
    if not row:
        return None
    now  = datetime.utcnow()
    span = plan_months_of(row) if months is None else clean_months(months)
    # Renewals extend from whichever is later: paying early adds a season
    # rather than throwing away days already bought, and a lapsed shop's new
    # season starts today rather than backdated into a gap it was dark for.
    base = row.paid_until if (row.paid_until and row.paid_until > now) else now
    row.paid_at     = now
    row.paid_amount = int(amount)
    row.payment_ref = (ref or "").strip()[:80] or None
    row.paid_until  = base + timedelta(days=30 * span)
    row.status      = "listed"
    row.active      = True
    row.updated_at  = now
    db.commit()
    db.refresh(row)
    return row


# ── the free first month ────────────────────────────────────
#
# The offer itself — how long it runs, who may take it, what the page promises
# — lives in services/free_month.py, shared with /rental so a shopkeeper and a
# tractor owner are told the same thing. These three are the doorway, so that
# routes/admin_dukan.py keeps talking to this module about shops and never has
# to know how the offer is stored.

def may_free_month(row) -> bool:
    """Whether this shop can still be given its free month — never paid, never
    granted one. See free_month.may_grant on why it is once per shop."""
    return free_month.may_grant(row)


def on_free_month(row) -> bool:
    """On a free month, or on the far side of one that ran out. Distinguishes a
    gifted listing from a paid one everywhere the panel says "वैधता"."""
    return free_month.on_free_month(row)


def start_free_month(db, slug: str, months: int | None = None):
    """Grant the free month. None when the shop is unknown OR not eligible —
    the caller separates the two by checking `may_free_month` first, because
    "यह दुकान नहीं मिली" and "इसे मुफ़्त महीना पहले ही मिल चुका है" are
    different sentences for the person on the phone.

    Nothing here touches `paid_at`: a free month is not a payment, and the
    `paying` count below must keep meaning "money actually arrived".
    """
    row = shop_get(db, slug)
    if not row:
        return None
    return free_month.grant(db, row, months or free_month.FREE_MONTHS)


def is_live(row) -> bool:
    """Whether this shop may be rendered to a farmer.

    `active` is the admin's switch. The second clause is the whole of billing
    enforcement and it is deliberately asymmetric: a shop with NO clock running
    at all stays visible, because during onboarding an empty directory is worth
    less than an unbilled listing and there is nothing to show a shopkeeper on
    a phone. A shop whose clock has run out goes dark — whether that clock was
    a paid season or the free first month, because both were agreed as having
    an end, and a free month that never ends is not an offer.
    """
    if not row or not row.active:
        return False
    if row.paid_until and row.paid_until < datetime.utcnow():
        return False
    return True


def is_lapsed(row) -> bool:
    """Had a term, ran out — a paid season or the free first month. Either way
    it is what the admin panel flags for a call, and `on_free_month` says which
    call it is: a renewal, or the first ask for money."""
    return bool(row and row.paid_until and row.paid_until < datetime.utcnow())


def days_left(row) -> int | None:
    """Whole days until the listing goes dark, negative once it already has.

    None means no clock is running — the shop has neither paid nor taken the
    free month, and under `is_live`'s onboarding grace it stays visible until
    one of those happens. That is a different state from "0 days left" and the
    panel must not render it as one.

    Rounded DOWN, so the number never promises time that is not there: eleven
    hours to run reads as 0, which the panel says as "आज आखिरी दिन" — true, and
    the day the call has to happen. Rounding up would print "1 दिन बाकी" on a
    listing that dies before the shopkeeper picks up.

    The same floor makes an expired listing read as at least -1, so a shop that
    went dark an hour ago can never be reported as having 0 days left.
    """
    if not row or not row.paid_until:
        return None
    return math.floor((row.paid_until - datetime.utcnow()).total_seconds() / 86400)


def expiring_soon(row, within_days: int = EXPIRING_SOON_DAYS) -> bool:
    """Still live, but not for long. The renewal call worth making today.

    Gated on `is_live`, not on `active`: after the expiry there is nothing left
    to save, only to win back, and that shop belongs under `is_lapsed`. Two
    warnings about one shop read as two problems.
    """
    left = days_left(row)
    return bool(row and is_live(row) and left is not None and 0 <= left <= within_days)


# ── items ───────────────────────────────────────────────────

def validate_item(db, data: dict) -> str:
    if not (data.get("product_slug") or "").strip():
        return "उत्पाद चुनें"
    if not catalog_get(db, data.get("product_slug")):
        return "यह उत्पाद कैटलॉग में नहीं है"
    try:
        price = int(round(float(str(data.get("price")).strip())))
    except (TypeError, ValueError):
        return "कीमत एक संख्या होनी चाहिए"
    if price <= 0:
        return "कीमत ₹0 से ज़्यादा होनी चाहिए"
    mrp = data.get("mrp")
    if str(mrp or "").strip():
        try:
            if int(round(float(str(mrp).strip()))) < price:
                # An MRP below the price renders a negative "% off" — a typo,
                # not a discount. Same guard as dealer_products.validate.
                return "MRP कीमत से कम नहीं हो सकता"
        except (TypeError, ValueError):
            return "MRP एक संख्या होनी चाहिए"
    return ""


def _int_or_none(value):
    try:
        n = int(round(float(str(value).strip())))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def items_for_shop(db, shop_slug: str, only_active: bool = True) -> list:
    q = db.query(DukanItem).filter(DukanItem.shop_slug == shop_slug)
    if only_active:
        q = q.filter(DukanItem.active.is_(True))
    return q.order_by(DukanItem.sort_order, DukanItem.id).all()


def item_get(db, item_id: int):
    return db.query(DukanItem).filter(DukanItem.id == int(item_id)).first()


def item_create(db, shop_slug: str, data: dict):
    """None when this shop already prices this product — the caller turns that
    into "यह उत्पाद पहले से जुड़ा है", not a 500 on the unique constraint."""
    product_slug = (data.get("product_slug") or "").strip().lower()
    existing = db.query(DukanItem).filter(
        DukanItem.shop_slug == shop_slug,
        DukanItem.product_slug == product_slug).first()
    if existing:
        return None
    row = DukanItem(
        shop_slug    = shop_slug,
        product_slug = product_slug,
        price        = int(round(float(str(data.get("price")).strip()))),
        mrp          = _int_or_none(data.get("mrp")),
        unit_hi      = (data.get("unit_hi") or "").strip() or None,
        note         = (data.get("note") or "").strip()[:200] or None,
        in_stock     = bool(data.get("in_stock", True)),
        active       = bool(data.get("active", True)),
        sort_order   = int(data.get("sort_order") or 0),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def item_update(db, item_id: int, data: dict):
    row = item_get(db, item_id)
    if not row:
        return None
    if "price" in data:
        row.price = int(round(float(str(data["price"]).strip())))
    if "mrp" in data:
        row.mrp = _int_or_none(data.get("mrp"))
    for field in ("unit_hi", "note"):
        if field in data:
            setattr(row, field, (data.get(field) or "").strip() or None)
    for flag in ("in_stock", "active"):
        if flag in data:
            setattr(row, flag, bool(data[flag]))
    if "sort_order" in data:
        row.sort_order = int(data.get("sort_order") or 0)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def item_delete(db, item_id: int) -> bool:
    row = item_get(db, item_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


# ── the reads the public pages run on ───────────────────────

def off_pct(price, mrp) -> int:
    try:
        price, mrp = int(price or 0), int(mrp or 0)
    except (TypeError, ValueError):
        return 0
    return round((1 - price / mrp) * 100) if mrp > price > 0 else 0


def offers_for_product(db, product_slug: str) -> list:
    """Every live shop that stocks this product, as flat dicts.

    Returned unsorted by distance on purpose — the server has no farmer to
    measure from. `_shop_rows()` in the route emits lat/lon onto each card and
    the page re-sorts client-side once km_geo is known, the same shape the
    /bhav nearest-mandi panel already uses.
    """
    items = db.query(DukanItem).filter(
        DukanItem.product_slug == (product_slug or "").lower(),
        DukanItem.active.is_(True)).all()
    if not items:
        return []
    shops = {s.slug: s for s in db.query(DukanShop).filter(
        DukanShop.slug.in_([i.shop_slug for i in items])).all()}
    out = []
    for item in items:
        shop = shops.get(item.shop_slug)
        if not shop or not is_live(shop):
            continue
        out.append({
            "shop_slug": shop.slug,
            "shop_name": shop.name,
            "district":  shop.district or "",
            "state":     shop.state or "",
            "address":   shop.address or "",
            "phone":     shop.phone or "",
            "whatsapp":  shop.whatsapp or "",
            "license_no": shop.license_no or "",
            "since":     shop.since or "",
            "verified":  bool(shop.verified),
            "lat":       shop.lat,
            "lon":       shop.lon,
            "item_id":   item.id,
            "price":     item.price,
            "mrp":       item.mrp,
            "off":       off_pct(item.price, item.mrp),
            "unit_hi":   item.unit_hi or "",
            "note":      item.note or "",
            "in_stock":  bool(item.in_stock),
            "updated_at": item.updated_at,
        })
    # Cheapest first is the honest default for a farmer with no location set,
    # and it is a fact about the offers rather than a fact about who paid.
    out.sort(key=lambda o: (not o["in_stock"], o["price"]))
    return out


def sort_by_distance(offers: list, lat: float, lon: float) -> list:
    """Server-side distance sort, for callers that already know where the
    farmer is (a logged-in profile with geo_* set). Offers with no coordinates
    sink to the bottom rather than being dropped — an un-geocoded shop is still
    a real shop."""
    def key(o):
        if o.get("lat") is None or o.get("lon") is None:
            return (1, 0.0, o["price"])
        km = district_geo.haversine_km(lat, lon, o["lat"], o["lon"])
        o["distance_km"] = round(km, 1)
        return (0, km, o["price"])
    ranked = sorted(offers, key=key)
    return [o for o in ranked
            if o.get("distance_km") is None or o["distance_km"] <= MAX_DISTANCE_KM]


def stocked_products(db) -> list:
    """Catalogue rows that at least one live shop actually sells.

    The dukan home page shows only these. A product nobody stocks is a page
    with an empty shop list — a dead end for the farmer and a thin page for
    Google, and there is no version of showing it that helps either.
    """
    items = db.query(DukanItem).filter(DukanItem.active.is_(True)).all()
    if not items:
        return []
    live = {s.slug for s in db.query(DukanShop).filter(
        DukanShop.active.is_(True)).all() if is_live(s)}
    agg: dict = {}
    for item in items:
        if item.shop_slug not in live:
            continue
        bucket = agg.setdefault(item.product_slug, {"shops": 0, "min_price": None,
                                                    "max_price": None})
        bucket["shops"] += 1
        lo, hi = bucket["min_price"], bucket["max_price"]
        bucket["min_price"] = item.price if lo is None else min(lo, item.price)
        bucket["max_price"] = item.price if hi is None else max(hi, item.price)
    if not agg:
        return []
    rows = db.query(DukanCatalog).filter(
        DukanCatalog.slug.in_(list(agg)),
        DukanCatalog.active.is_(True)).all()
    out = []
    for row in rows:
        stat = agg[row.slug]
        out.append({
            "slug": row.slug, "cat": row.cat, "emoji": row.emoji or "🛒",
            "name_hi": row.name_hi, "name_en": row.name_en or "",
            "unit_hi": row.unit_hi or "", "desc_hi": row.desc_hi or "",
            "image_url": row.image_url or "", "has_image": bool(row.image_mime),
            "image_id": row.id,
            "shops": stat["shops"], "min_price": stat["min_price"],
            "max_price": stat["max_price"],
            "sort_order": row.sort_order,
        })
    out.sort(key=lambda p: (p["sort_order"], -p["shops"], p["name_hi"]))
    return out


def counts(db) -> dict:
    """The admin panel's header numbers."""
    shops = db.query(DukanShop).all()
    return {
        "shops":     len(shops),
        "live":      sum(1 for s in shops if is_live(s)),
        "lapsed":    sum(1 for s in shops if is_lapsed(s)),
        "expiring":  sum(1 for s in shops if expiring_soon(s)),
        "uncalled":  sum(1 for s in shops if not s.called_at),
        # Counted apart from `paying` on purpose: a free month is not revenue,
        # and a header that folded the two together would report a month of
        # giveaways as a month of sales.
        "free":      sum(1 for s in shops if on_free_month(s)),
        "paying":    sum(1 for s in shops if s.paid_at),
        "catalog":   db.query(DukanCatalog).count(),
        "items":     db.query(DukanItem).count(),
    }
