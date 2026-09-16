# ============================================================
# services/shop_catalog.py
# The editable half of the /product catalogue.
#
# WHAT WAS WRONG. The catalogue was a `const PRODUCTS = [...]` literal inside
# frontend/shop.html. Adding a product meant hand-editing a 94-entry JS array
# and shipping a deploy — impossible from a phone, and slow enough that the
# catalogue simply stopped growing. Every product is also an affiliate
# placement, so a catalogue that cannot grow is revenue that cannot grow.
#
# THE SHAPE: BASELINE + OVERLAY.
#
#   baseline   frontend/shop.html's PRODUCTS  — 94 committed products
#   overlay    the shop_products table        — what the panel writes
#
# A row whose slug matches a baseline entry REPLACES it, field by field, and
# only for the fields that are actually filled in. A row with a new slug is an
# addition. `active=False` hides a product from every surface. Nothing is
# migrated, nothing is deleted, and the baseline is never rewritten — so if
# this table is empty, or Neon is asleep, or the query throws, /product renders
# exactly what it rendered before this file existed. That is the whole safety
# story, and it is why the merge is additive rather than a migration.
#
# WHY THE CACHE IS TIME-BASED, NOT mtime-BASED. routes/product.py's baseline
# cache watches shop.html's mtime, which is free. A database has no mtime, and
# _get_products() is now on the hot path of every /bhav district page — the
# affiliate shelf calls it on each render. A query per render would put the
# highest-traffic page on the site behind a Neon round trip, and a suspended
# compute takes seconds to wake. So the overlay is fetched at most once every
# TTL_SECONDS, a failed fetch keeps serving the last good copy, and the panel
# calls invalidate() after a write so an edit shows up immediately rather than
# up to a minute later.
# ============================================================
from __future__ import annotations

import re
import time

# The panel's ids must not collide with the hand-numbered ones in shop.html's
# PRODUCTS (currently 1..94). shop.html's cart addressing uses that number, so
# an overlap would put a farmer's tap on the wrong product.
ID_OFFSET = 100_000

TTL_SECONDS = 60.0

# Every field the overlay may carry. Kept in step with the ShopProduct model
# and with routes/product.py's _STR_FIELDS — a field missing here is a field
# the panel can edit and the page silently ignores.
TEXT_FIELDS = (
    "cat", "emoji", "badge", "badge_class",
    "name_hi", "name_en", "name_kn",
    "desc_hi", "desc_en", "desc_kn",
    "unit_hi", "unit_en", "unit_kn",
    "affil_amazon", "affil_flipkart",
)
INT_FIELDS = ("price", "mrp")

_cache: dict = {"at": 0.0, "rows": None}

# routes/product.py indexes these keys directly — p['price'], p['desc_en'] —
# because every entry in shop.html's PRODUCTS has always carried them. An
# overlay row is a sparse patch, which is right for an override (a blank box
# must not erase a live value) and wrong for an ADDITION, where there is no
# committed entry underneath to supply the rest. So a panel-added product is
# filled out to a whole one here, and a missing key becomes an empty string
# rather than a KeyError on a live page.
#
# `img` is deliberately allowed to stay empty: a product typed in from a phone
# may not have a photo for another minute, and product.py falls back to the
# emoji rather than rendering a broken image.
ADDED_DEFAULTS = {
    "cat": "misc", "emoji": "📦", "badge": "", "badgeClass": "", "img": "",
    "name_hi": "", "name_en": "", "name_kn": "",
    "desc_hi": "", "desc_en": "", "desc_kn": "",
    "unit_hi": "", "unit_en": "", "unit_kn": "",
    "price": 0, "mrp": 0,
    "affil_amazon": "", "affil_flipkart": "",
}


# ── slug ────────────────────────────────────────────────────

def slugify(name_en: str) -> str:
    """Must stay identical to routes/product.py::_slugify and to shop.html's
    getProductSlug(), because all three have to name the same URL."""
    s = re.sub(r"[()%]", "", (name_en or "").lower())
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


# ── reading ─────────────────────────────────────────────────

def _row_to_product(r) -> dict:
    """One DB row in the shape routes/product.py already understands.

    Empty strings are dropped rather than written through as "": an overlay row
    is a patch, and a blank box in the panel means "leave the committed value
    alone", not "erase the description on a live page".
    """
    p = {"slug": r.slug, "id": ID_OFFSET + int(r.id), "_src": "db"}
    for f in TEXT_FIELDS:
        v = (getattr(r, f, None) or "").strip()
        if v:
            # The page reads `badgeClass`; the column is snake_case like every
            # other column. Translate here so neither side has to bend.
            p["badgeClass" if f == "badge_class" else f] = v
    for f in INT_FIELDS:
        v = getattr(r, f, None)
        if v is not None:
            p[f] = int(v)
    # An uploaded photo wins over a committed path: it is the newer statement
    # about what this product looks like, and it is the only way to correct a
    # baseline entry that points at the wrong picture.
    if r.image_mime:
        p["img"] = f"/product/img/{r.id}.webp"
    elif (r.image_url or "").strip():
        p["img"] = r.image_url.strip()
    return p


def overlay(db) -> list[dict]:
    """Active overlay rows, oldest first. Takes a session; callers without one
    want overlay_cached()."""
    from backend.database.db import ShopProduct
    rows = (db.query(ShopProduct)
              .filter(ShopProduct.active.is_(True))
              .order_by(ShopProduct.sort_order, ShopProduct.id)
              .all())
    return [_row_to_product(r) for r in rows]


def hidden_slugs(db) -> set:
    """Slugs switched off in the panel. A baseline product cannot be deleted —
    shop.html still lists it — so hiding is how one is taken down."""
    from backend.database.db import ShopProduct
    return {s for (s,) in db.query(ShopProduct.slug)
                            .filter(ShopProduct.active.is_(False)).all()}


def _fetch() -> tuple:
    """(overlay rows, hidden slugs) straight from the database.

    Opens its own session: the callers on the hot path — _get_products(), and
    through it the affiliate shelf — are render helpers with no `db` to borrow,
    and holding a request's pooled connection open across a page render is how
    a 512 MB dyno runs out of connections.
    """
    from backend.database.db import SessionLocal
    db = None
    try:
        db = SessionLocal()
        return overlay(db), hidden_slugs(db)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def overlay_cached() -> tuple:
    """(overlay rows, hidden slugs), at most one query per TTL_SECONDS.

    Never raises. A missing table (a fresh test database), a sleeping compute
    or a read-only episode all land in the same place: keep whatever was last
    known good, and if nothing is known yet, return nothing — which makes
    merge() a no-op and the catalogue exactly the committed baseline.
    """
    now = time.monotonic()
    cached = _cache["rows"]
    if cached is not None and (now - _cache["at"]) < TTL_SECONDS:
        return cached
    try:
        fresh = _fetch()
    except Exception:
        return cached if cached is not None else ([], set())
    _cache["rows"] = fresh
    _cache["at"] = now
    return fresh


def invalidate() -> None:
    """Drop the cache so the next read hits the database.

    Called after every panel write. With more than one worker process only the
    one that served the write clears its own copy; the others catch up within
    TTL_SECONDS, which is the price of not holding a shared cache.
    """
    _cache["rows"] = None
    _cache["at"] = 0.0


def merge(baseline: list[dict]) -> list[dict]:
    """The catalogue /product actually serves: baseline, patched by the overlay.

    Order is deliberate — committed products keep their hand-arranged order and
    panel additions land at the end, so adding a product never reshuffles the
    hub under a farmer who had learned where things were.
    """
    rows, hidden = overlay_cached()
    if not rows and not hidden:
        return baseline

    by_slug = {p["slug"]: p for p in rows}
    out, used = [], set()
    for p in baseline:
        slug = p["slug"]
        if slug in hidden:
            continue
        patch = by_slug.get(slug)
        if patch:
            used.add(slug)
            merged = dict(p)
            merged.update({k: v for k, v in patch.items() if k != "id"})
            out.append(merged)
        else:
            out.append(p)
    for slug, p in by_slug.items():
        if slug not in used and slug not in hidden:
            # An addition has no committed entry underneath it, so it is filled
            # out to a complete product here — see ADDED_DEFAULTS.
            whole = dict(ADDED_DEFAULTS)
            whole.update(p)
            out.append(whole)
    return out


# ── writing ─────────────────────────────────────────────────

def validate(payload: dict, *, existing: bool = False) -> str | None:
    """The message to show the owner, or None. Deliberately short: this panel
    is used from a phone, and a validation wall is how a product does not get
    added at all."""
    from backend.routes.product import CAT_LABELS
    if not existing:
        if not (payload.get("name_en") or "").strip():
            return "English name is required — the URL is built from it."
        if not slugify(payload.get("name_en", "")):
            return "That English name has no letters or digits to build a URL from."
    if not existing and not (payload.get("name_hi") or "").strip():
        return "Hindi name is required — it is what the farmer reads."
    cat = (payload.get("cat") or "").strip()
    if cat and cat not in CAT_LABELS:
        return f"Unknown category '{cat}'."
    if not existing and not cat:
        return "Pick a category."
    for f in INT_FIELDS:
        v = payload.get(f)
        if v in (None, ""):
            continue
        try:
            if int(v) < 0:
                return f"{f} cannot be negative."
        except (TypeError, ValueError):
            return f"{f} must be a whole number."
    for f in ("affil_amazon", "affil_flipkart"):
        v = (payload.get(f) or "").strip()
        if v and not v.startswith(("http://", "https://")):
            return "An affiliate link must start with http:// or https://"
    return None


def _apply(row, payload: dict) -> None:
    """Copy the fields present in `payload` onto a row.

    A key that is absent is left alone; a key sent as "" clears that column.
    The panel sends only what its form holds, so this is what lets one field be
    corrected without re-typing the other fourteen.
    """
    for f in TEXT_FIELDS + ("image_url",):
        if f in payload:
            v = payload.get(f)
            setattr(row, f, (v or "").strip() or None)
    for f in INT_FIELDS:
        if f in payload:
            v = payload.get(f)
            setattr(row, f, int(v) if str(v).strip() not in ("", "None") else None)
    if "active" in payload:
        row.active = bool(payload["active"])
    if "sort_order" in payload:
        try:
            row.sort_order = int(payload["sort_order"])
        except (TypeError, ValueError):
            pass


def get(db, slug: str):
    from backend.database.db import ShopProduct
    return db.query(ShopProduct).filter(ShopProduct.slug == slug).first()


def create(db, payload: dict):
    """Add a product, or start overriding a committed one.

    A slug that already exists in shop.html is NOT an error: that is exactly
    how a baseline product gets edited — the panel creates an overlay row with
    the same slug and the merge prefers it from then on.
    """
    from backend.database.db import ShopProduct
    slug = (payload.get("slug") or "").strip() or slugify(payload.get("name_en", ""))
    if get(db, slug):
        raise ValueError(f"'{slug}' is already being edited here — open it instead.")
    row = ShopProduct(slug=slug, cat=(payload.get("cat") or "misc").strip(),
                      name_hi=(payload.get("name_hi") or "").strip(),
                      name_en=(payload.get("name_en") or "").strip())
    _apply(row, payload)
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate()
    return row


def update(db, slug: str, payload: dict):
    row = get(db, slug)
    if not row:
        return None
    _apply(row, payload)
    db.commit()
    db.refresh(row)
    invalidate()
    return row


def delete(db, slug: str) -> bool:
    """Remove the overlay row.

    For a panel-added product that is a real delete and the page 404s. For an
    overlay on a committed product it is a REVERT: the row goes and shop.html's
    original entry shows through again. Both are what "delete" should mean in
    each case, and neither can destroy a committed product.
    """
    row = get(db, slug)
    if not row:
        return False
    db.delete(row)
    db.commit()
    invalidate()
    return True


def baseline_slugs() -> set:
    """Slugs that exist in shop.html, so the panel can tell an addition from an
    override and say so in the list."""
    from backend.routes.product import _parse_shop_html, _SHOP_HTML
    try:
        return {p["slug"] for p in _parse_shop_html(_SHOP_HTML.read_text(encoding="utf-8"))}
    except Exception:
        return set()
