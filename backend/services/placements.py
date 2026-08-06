# ============================================================
# backend/services/placements.py
# Which /bhav page a paying dealer is shown on, and in which of its 3 slots.
#
# THE SPLIT THIS MODULE EXISTS FOR. services/buyers.py answers "may this shop
# be shown at all" — active, verified, subscription current. That is
# eligibility. This module answers "and where", which is the thing money is
# actually exchanged for:
#
#     /bhav/{crop}/{state}/{district}   ₹199/month, +₹50 per extra district
#     /bhav/{crop}/{state}              ₹999/month, +₹999 per extra state
#
# Keeping them apart is what makes a lapse safe: a placement is never deleted
# when a subscription ends, but for_page() resolves every slug through
# buyers.by_id(), which drops anyone unpaid, unverified or hidden. His slots
# empty themselves and fill again on renewal, with nothing to remember.
#
# READS ARE HOT, WRITES ARE RARE. A /bhav render must not query this table —
# there are ~10,000 of those pages and one owner setting slots by hand. The
# whole table is a few dozen rows, so it is cached whole and dropped on write,
# the same shape services/buyers.py already uses for the same reason.
# ============================================================
import logging
import threading
import time
from datetime import datetime

from backend.database.db import DealerPlacement, SessionLocal
from backend.services import buyers as buyers_read

logger = logging.getLogger(__name__)

# Three, because that is what the panel renders. Not a config knob: the number
# is baked into the page design and into what a dealer is told he is buying.
SLOTS = 3

# Rupees per month, as quoted on /dukanlisting. Held here so the admin panel,
# the receipt and the page copy cannot drift apart.
PRICE_DISTRICT = 199        # first district
PRICE_DISTRICT_EXTRA = 50   # each additional district
PRICE_STATE = 999           # first state
PRICE_STATE_EXTRA = 999     # each additional state

# The list price, shown struck through beside the offer price.
#
# THIS IS A PROMISE, NOT A DECORATION. A crossed-out number that was never
# charged and never will be is a false reference price — the thing India's
# CCPA dark-pattern rules are about, and the same kind of claim /dukanlisting
# explicitly promises farmers we do not make about ranking. So these are the
# real list prices: when the introductory period ends, THIS is what a new
# dealer pays, and every surface says "शुरुआती ऑफर" rather than implying a
# discount that has already been taken away from someone.
LIST_DISTRICT = 599
LIST_STATE = 1999

_TTL = 120.0                # seconds; the floor under a missed invalidate()
_cache: list | None = None
_at = -1.0
_lock = threading.Lock()


def norm(s: str) -> str:
    """Slug spelling is the join key between this table and a URL, and a URL is
    always lowercase here."""
    return " ".join((s or "").strip().lower().split())


def page_key(crop: str, state: str, district: str = "") -> tuple:
    return (norm(crop), norm(state), norm(district))


def page_url(crop: str, state: str, district: str = "") -> str:
    crop, state, district = page_key(crop, state, district)
    return f"/bhav/{crop}/{state}/{district}" if district else f"/bhav/{crop}/{state}"


def price_for(district: str, n_existing: int = 0) -> int:
    """What one more slot of this kind costs today. `n_existing` is how many of
    that kind the dealer already holds, so the second district is ₹50 and not
    another ₹199."""
    if norm(district):
        return PRICE_DISTRICT if n_existing == 0 else PRICE_DISTRICT_EXTRA
    return PRICE_STATE if n_existing == 0 else PRICE_STATE_EXTRA


def list_price_for(district: str) -> int:
    """The struck-through number beside it. Only ever the FIRST slot's list
    price: "₹599 ₹50" next to an add-on district would be nonsense."""
    return LIST_DISTRICT if norm(district) else LIST_STATE


def invalidate() -> None:
    global _cache, _at
    with _lock:
        _cache, _at = None, -1.0


def _row_dict(r) -> dict:
    return {
        "id":       r.id,
        "slug":     r.buyer_slug,
        "crop":     r.crop_slug,
        "state":    r.state_slug,
        "district": r.district_slug or "",
        "rank":     r.rank,
        "price":    r.price,
        "url":      page_url(r.crop_slug, r.state_slug, r.district_slug or ""),
    }


def _all() -> list:
    """Every placement, cached. Never raises: a /bhav page that cannot read this
    table renders without a dealer panel, which is how it looked yesterday."""
    global _cache, _at
    now = time.time()
    if _cache is not None and (now - _at) < _TTL:
        return _cache
    rows: list = []
    try:
        db = SessionLocal()
        try:
            rows = [_row_dict(r) for r in db.query(DealerPlacement).all()]
        finally:
            db.close()
    except Exception as e:
        logger.warning("placement read failed, rendering no panel: %s", e)
        return _cache or []
    with _lock:
        _cache, _at = rows, now
    return rows


def for_page(crop: str, state: str, district: str = "") -> list:
    """The dealers to render on one page, best rank first.

    Each slug is resolved through buyers.by_id(), which is where eligibility
    lives — so a lapsed or hidden dealer silently drops out of his slot and the
    page shows one fewer card rather than a dead listing.
    """
    key = page_key(crop, state, district)
    out = []
    for p in _all():
        if (p["crop"], p["state"], p["district"]) != key:
            continue
        dealer = buyers_read.by_id(p["slug"])
        if not dealer:
            continue                      # unpaid / unverified / hidden
        out.append((p["rank"], dealer))
    return [d for _rank, d in sorted(out, key=lambda x: x[0])]


def for_dealer(slug: str) -> list:
    """Every slot one dealer holds, for the admin panel. Ordered so the state
    pages (the ₹999 product) read before the district ones."""
    slug = (slug or "").strip()
    mine = [p for p in _all() if p["slug"] == slug]
    return sorted(mine, key=lambda p: (bool(p["district"]), p["crop"], p["state"],
                                       p["district"], p["rank"]))


def slots_on(crop: str, state: str, district: str = "") -> list:
    """[{rank, slug|None}] for all 3 slots of a page — what the admin box shows
    so "who is already at rank 1" is answerable before overwriting them."""
    key = page_key(crop, state, district)
    held = {p["rank"]: p for p in _all()
            if (p["crop"], p["state"], p["district"]) == key}
    out = []
    for rank in range(1, SLOTS + 1):
        p = held.get(rank)
        out.append({"rank": rank, "slug": p["slug"] if p else None,
                    "placement_id": p["id"] if p else None})
    return out


def set_placement(db, buyer_slug: str, crop: str, state: str,
                  district: str = "", rank: int = 1, price: int | None = None):
    """Put one dealer in one slot. Returns the row, or None if `rank` is out of
    range.

    Two collisions are resolved here rather than left to the database, because
    both are ordinary admin actions and neither should be an error:

      * somebody else holds this slot  → they lose it (the panel shows who,
        before you click)
      * this dealer already holds another slot on this page → it moves, rather
        than him appearing twice on one page
    """
    try:
        rank = int(rank)
    except (TypeError, ValueError):
        return None
    if rank not in range(1, SLOTS + 1):
        return None

    crop, state, district = page_key(crop, state, district)
    if not crop or not state:
        return None

    q = db.query(DealerPlacement).filter(
        DealerPlacement.crop_slug == crop,
        DealerPlacement.state_slug == state,
        DealerPlacement.district_slug == district)
    for other in q.all():
        if other.rank == rank or other.buyer_slug == buyer_slug:
            db.delete(other)
    db.flush()

    row = DealerPlacement(
        buyer_slug=buyer_slug, crop_slug=crop, state_slug=state,
        district_slug=district, rank=rank,
        price=price if price is not None else price_for(district),
        created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate()
    return row


def clear_placement(db, placement_id: int) -> bool:
    row = db.query(DealerPlacement).filter(DealerPlacement.id == placement_id).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    invalidate()
    return True


def clear_for_dealer(db, buyer_slug: str) -> int:
    """Called when a listing is deleted. Placements outlive a lapse on purpose,
    but not the row they point at — that would leave a slot held by a dealer
    who no longer exists, and it would look empty rather than wrong."""
    rows = db.query(DealerPlacement).filter(
        DealerPlacement.buyer_slug == buyer_slug).all()
    for r in rows:
        db.delete(r)
    if rows:
        db.commit()
        invalidate()
    return len(rows)


def counts() -> dict:
    """Admin summary: how many slots are sold, and how many dealers are paying
    for nothing because nobody put them on a page."""
    all_rows = _all()
    placed = {p["slug"] for p in all_rows}
    return {
        "slots":     len(all_rows),
        "state":     sum(1 for p in all_rows if not p["district"]),
        "district":  sum(1 for p in all_rows if p["district"]),
        "dealers":   len(placed),
    }
