# ============================================================
# backend/routes/dukanlisting.py
# KrashiMitra — "अपनी दुकान लिस्ट करें": paid, login-gated dealer subscriptions.
#
# Replaces the old anonymous, free, single-district /dukan/signup (shipped
# 2026-08-01) entirely — this is not an add-on tier next to it. A dealer now
# has to log in (the same account system farmers use — reused so a listing has
# a real users.id to author its krashi_bajar post as, see
# services/dealers.py::_sync_bazar_post), pick however many districts they
# want to be reachable in, and pay a monthly subscription:
# services/dealers.py::quote() — ₹199 for the first district, +₹50 for each
# additional one.
#
# ENDPOINTS (all Depends(get_current_user) — no anonymous path any more):
#   POST   /dukanlisting/listings         create/add districts to the caller's account
#   GET    /dukanlisting/mine             the caller's own districts + current price
#   DELETE /dukanlisting/listings/{slug}  drop one district (must own the row)
#
# WHAT DOES NOT CHANGE from the old model:
#   • Never live, never verified from here. services/dealers.py::from_signup
#     still has no code path to either flag — a row lands status="new",
#     active=False exactly like the old public form did. The phone-verification
#     call stays a hard gate: paying does not itself put a dealer live (see
#     record_payment()'s owner_user_id branch) — only admin's approve() does.
#   • A working mobile number is still the one hard requirement.
#
# WHAT IS NEW:
#   • owner_user_id ties every district-row this account creates together, so
#     one subscription payment renews all of them (record_payment()) and the
#     bhav Tier-3 panel / krashi_bajar post both key off the whole account's
#     eligibility, not one row in isolation.
#   • WHERE a dealer is shown is a separate, paid decision — see
#     services/placements.py, which now sells five tiers from one district page
#     up to a whole crop nationally, priced per SEASON (3 months) rather than
#     per month. This route sells only the self-serve one — "मेरा पूरा जिला",
#     every crop page in his district — because that is the only tier a shop
#     can buy without a phone call; the wide tiers are quoted by hand.
#     Paying alone shows him nowhere; the admin picks the pattern and the rank.
#     A phone number still appears only on the /kharidar page.
# ============================================================

import base64
from datetime import datetime
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.db import Buyer, get_db, is_read_only_error
from backend.services import dealer_products, dealers, placements
from backend.utils.auth_utils import get_current_user

router = APIRouter(prefix="/dukanlisting", tags=["dukan"])

_MAX = {"name": 120, "state": 80, "district": 80, "market": 120,
        "phone": 20, "whatsapp": 20, "description": 400, "since": 40}

# One account, one district picker to spam — a real logged-in account is
# already far more friction than the old anonymous form had, so this is a
# sanity cap rather than an abuse defence.
_MAX_DISTRICTS = 10

OK = ("आपकी जानकारी मिल गई है। हमारी टीम आपके नंबर पर कॉल करके पुष्टि करेगी, "
      "उसी कॉल पर भुगतान लिंक भी भेजेगी।")
READ_ONLY = ("अभी सर्वर पर जानकारी सेव नहीं हो पा रही। थोड़ी देर बाद दोबारा "
             "कोशिश करें — या WhatsApp पर सीधे भेज दें।")


def _norm(s: Optional[str]) -> str:
    return " ".join((s or "").strip().lower().split())


class DistrictIn(BaseModel):
    state: str = ""
    district: str = ""
    market: str = ""


class ListingsIn(BaseModel):
    name: str = ""
    kind: str = "trader"
    phone: Optional[str] = ""
    whatsapp: Optional[str] = ""
    # The form posts a list; a comma string works too, same courtesy the old
    # endpoint gave curl/plain-HTML callers.
    commodities: Union[List[str], str] = ""
    # The dealer's own public blurb — "what I want to list". Deliberately NOT
    # `note`: that is the admin's private call log, services/dealers.py::_apply
    # gates it behind `trusted`, and it used to be the field the public kharidar
    # card rendered. Accepting `note` here would let a dealer write into the
    # call log about himself.
    description: Optional[str] = ""
    since: Optional[str] = ""
    districts: List[DistrictIn] = []
    # Which of the five products he is asking for — see
    # services/placements.py::TIERS. It does not change what is created here
    # (every plan still becomes rows for the districts he named, and none of
    # them live); it is recorded so the admin ringing him knows what he asked
    # for before quoting a price. An unknown value falls back to the self-serve
    # tier rather than being rejected: a stale cached page must not break a
    # signup.
    plan: Optional[str] = ""
    # WHICH CROP PAGES HE IS BUYING — ₹50 each, counted once across the account
    # however many districts he picked. Half the bill, so it is validated in
    # services/dealers.py::_apply rather than trusted.
    plan_crops: List[str] = []


@router.post("/listings")
async def create_listings(
    payload: ListingsIn,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create (or add districts to) the caller's dealer account.

    Additive, not a replace-all: re-submitting to add one more district skips
    any (state, district) the account already has rather than duplicating it
    or touching that row's call/payment history.
    """
    user_id = current_user["user_id"]
    # The self-serve form only ever sells the metered plan; "custom" is a
    # single page negotiated by hand and never arrives here. An unknown value
    # falls back rather than rejecting the signup — a stale cached page must
    # never cost us a lead.
    plan = (payload.plan or "").strip().lower()
    if plan != "metered":
        plan = placements.DEFAULT_PLAN
    base = {
        "name":          (payload.name or "").strip()[:_MAX["name"]],
        "kind":          payload.kind,
        "commodities":   payload.commodities,
        "phone":         (payload.phone or "").strip()[:_MAX["phone"]],
        "whatsapp":      (payload.whatsapp or "").strip()[:_MAX["whatsapp"]],
        "description":   (payload.description or "").strip()[:_MAX["description"]],
        "since":         (payload.since or "").strip()[:_MAX["since"]],
        "owner_user_id": user_id,
        "plan":          plan,
        "plan_crops":    payload.plan_crops or [],
    }

    incoming = [d for d in (payload.districts or []) if (d.district or "").strip()]
    incoming = incoming[:_MAX_DISTRICTS]
    if not incoming:
        raise HTTPException(400, "कम से कम एक जिला चुनें")

    problem = dealers.validate({**base, "district": incoming[0].district})
    if problem:
        raise HTTPException(400, problem)

    existing_keys = {(_norm(r.state), _norm(r.district))
                     for r in dealers.for_owner(db, user_id)}

    # Written to `note`, the admin-only call log, and never through _apply() —
    # which drops `note` from untrusted input on purpose, so a dealer cannot
    # write into his own call log. This is the route stamping what it was told,
    # not the dealer's text. The tier itself is a real column (Buyer.plan); this
    # line is the human-readable twin the caller actually reads, built from
    # placements.TIERS rather than typed out, so a reprice cannot leave the
    # call log quoting a number we no longer charge.
    # Generated entirely from our own rate card — NOTHING the dealer typed goes
    # in here, not even his chosen crops. `plan_crops` has its own column and
    # the panel renders it from there; concatenating it into this string would
    # be a write path from the signup form straight into the private call log,
    # which is the one thing this field must never have.
    n_crops = len(dealers.normalise_plan_crops(base["plan_crops"]))
    plan_note = (f"[प्लान] {placements.plan_label(plan)} — "
                 f"{len(incoming)} जिला × ₹{placements.PRICE_DISTRICT} + "
                 f"{n_crops} फसल × ₹{placements.PRICE_CROP} = "
                 f"₹{placements.quote(len(incoming), n_crops)}/सीज़न "
                 f"({placements.SEASON_MONTHS} माह)")

    try:
        created = 0
        for d in incoming:
            key = (_norm(d.state), _norm(d.district))
            if key in existing_keys:
                continue
            existing_keys.add(key)
            row = dealers.from_signup(db, {
                **base,
                "state":    (d.state or "").strip()[:_MAX["state"]],
                "district": (d.district or "").strip()[:_MAX["district"]],
                "market":   (d.market or "").strip()[:_MAX["market"]],
            })
            if plan_note and row is not None:
                row.note = plan_note
            created += 1
        if plan_note:
            db.commit()
    except Exception as e:
        if is_read_only_error(e):
            raise HTTPException(503, READ_ONLY)
        raise HTTPException(500, "जानकारी सेव नहीं हो पाई। दोबारा कोशिश करें।")

    rows = dealers.for_owner(db, user_id)
    total = len(rows)
    crops = dealers.crops_of(rows)
    return {"success": True, "message": OK, "data": {
        "created":         created,
        "district_count":  total,
        "crop_count":      len(crops),
        "plan":            plan,
        "plan_label":      placements.plan_label(plan),
        "price":           dealers.quote(total, len(crops)) if total else 0,
        "breakdown":       placements.breakdown(total, len(crops)) if total else None,
    }}


@router.get("/crops")
async def crops_for_district(state: str = "", district: str = ""):
    """Which crop pages exist in this district, and what each one actually did.

    THIS IS THE HONEST HALF OF THE RATE CARD. Every crop here costs the same
    ₹50, but the pages behind them are not the same: impressions per crop page
    run from 0 to 46 across UP districts. Rather than price that difference
    with a formula nobody could explain on a phone call, the number is put in
    front of the dealer while he picks. He buys the pages worth buying, the
    dead ones go unsold, and a flat ₹50 comes out fair without any arithmetic.
    It is also the churn defence: he chose it with the figure on screen.

    Deliberately open — no login. A dealer weighing up whether to sign up at
    all is exactly who this has to convince, and there is nothing private here:
    it is our own inventory's performance.

    `impressions: null` means we have no data (no snapshot yet, or Search
    Console has never reported that URL) and renders as nothing at all. Zero
    means Google showed it to nobody, and renders as zero. Conflating them
    would either invent traffic or claim a page is dead when we simply do not
    know.
    """
    from backend.routes import bhav
    from backend.services import page_stats

    s_slug = _norm(state).replace(" ", "-")
    d_slug = _norm(district).replace(" ", "-")
    if not s_slug or not d_slug:
        raise HTTPException(400, "राज्य और जिला दोनों चाहिए")

    idx = bhav._get_index()
    out = []
    for c_slug, commodity in idx.get("crops", {}).items():
        if not bhav._is_crop(commodity):
            continue
        if d_slug not in idx.get("dists", {}).get(c_slug, {}).get(s_slug, {}):
            continue
        stats = page_stats.for_page(c_slug, s_slug, d_slug)
        out.append({
            "slug":        c_slug,
            "name_hi":     bhav._hindi_name(commodity),
            "name_en":     commodity,
            "url":         placements.page_url(c_slug, s_slug, d_slug),
            "impressions": stats["impressions"] if stats else None,
            "clicks":      stats["clicks"] if stats else None,
        })

    # Busiest first. A dealer scanning a list of forty crops should meet the
    # ones worth his ₹50 before he gets bored, and the ones showing nothing
    # should be the ones he has to scroll for.
    out.sort(key=lambda c: (-(c["impressions"] or 0), c["name_hi"]))
    return {"success": True, "data": {
        "state":        s_slug,
        "district":     d_slug,
        "crops":        out,
        "crop_rate":    placements.PRICE_CROP,
        "district_rate": placements.PRICE_DISTRICT,
        "window_days":  page_stats.WINDOW_DAYS,
        # So the page can say "आंकड़े N दिन पुराने हैं" rather than presenting a
        # month-old snapshot as this morning's.
        "stats_age_days": page_stats.snapshot_age_days(),
        "stats_stale":    page_stats.is_stale(),
    }}


@router.get("/quote")
async def price_quote(districts: int = 1, crops: int = 0):
    """The live price readout, computed server-side.

    The form does the same arithmetic in JS for instant feedback, but this is
    the number that governs — one endpoint the page and the admin panel can
    both call means the dealer can never be shown a total the backend would
    not charge.
    """
    return {"success": True, "data": placements.breakdown(districts, crops)}


@router.get("/mine")
async def my_listings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The caller's own districts, verification/payment status, and the
    current per-season price — so the page can show "your listings" instead of
    a blank form on a repeat visit."""
    rows = dealers.for_owner(db, current_user["user_id"])
    now = datetime.utcnow()
    items = [{
        "slug":       r.slug,
        "state":      r.state or "",
        "district":   r.district or "",
        "market":     r.market or "",
        "active":     bool(r.active),
        "verified":   bool(r.verified),
        "status":     r.status,
        "paid_until": r.paid_until.isoformat() if r.paid_until else None,
        "paying":     bool(r.paid_until and r.paid_until > now),
    } for r in rows]
    # Business fields live per-row (so an admin can hand-correct one district
    # without touching the rest), but they are the same account — the first
    # row is a fine default for prefilling "add another district" so the
    # dealer never has to retype their own firm name and phone.
    lead = rows[0] if rows else None
    business = {
        "name":        lead.name if lead else "",
        "kind":        lead.kind if lead else "trader",
        "phone":       lead.phone if lead else "",
        "whatsapp":    lead.whatsapp if lead else "",
        "commodities": (lead.commodities or "").split(",") if lead and lead.commodities else [],
        "description": lead.description if lead else "",
        "since":       lead.since if lead else "",
    } if lead else None
    plan = dealers.plan_of(rows)
    crops = dealers.crops_of(rows)
    return {"success": True, "data": {
        "listings":        items,
        "district_count":  len(items),
        "plan":            plan,
        "plan_label":      placements.plan_label(plan),
        "plan_crops":      crops,
        "crop_count":      len(crops),
        "price":           dealers.quote(len(items), len(crops)) if items else 0,
        "breakdown":       placements.breakdown(len(items), len(crops)) if items else None,
        "business":        business,
    }}


# Long enough that a renewal call and a UPI transfer both fit inside it without
# his listing ever going dark, short enough that it is not background noise he
# learns to ignore. Shared with the admin panel's renewal list via
# services/dealers.py so the two views can never disagree.
_EXPIRY_WARN_DAYS = dealers.EXPIRY_WARN_DAYS
_SEASON = placements.SEASON_MONTHS


@router.get("/subscription")
async def my_subscription(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The dealer's own subscription state, for the KrashiBook alert.

    Derived live from `paid_until` on every request — no scheduler, no stored
    "reminder sent" flag, nothing to fall out of sync. Same parse-on-request
    shape as /crop-calendar/nudges, and for the same reason: a cron that
    silently stops is exactly the failure this endpoint exists to prevent.

    The gap it closes: a subscription simply ended. services/buyers.py::_usable
    drops the dealer from every farmer-facing surface the moment `paid_until`
    passes, and until now nothing anywhere told him — his listing went dark and
    the first he would know was wondering why the calls stopped.
    """
    rows = dealers.for_owner(db, current_user["user_id"])
    if not rows:
        return {"success": True, "data": {"state": "none", "alerts": []}}

    now = datetime.utcnow()
    # One account, one subscription: every row renews together
    # (dealers.record_payment), so the account's window is the furthest of them.
    until = max((r.paid_until for r in rows if r.paid_until), default=None)
    verified = any(r.verified for r in rows)
    districts = len(rows)
    plan = dealers.plan_of(rows)
    crops = dealers.crops_of(rows)
    price = dealers.quote(districts, len(crops))

    if until is None:
        state, days = "unpaid", None
    else:
        days = (until - now).days
        if until <= now:
            state = "lapsed"
        elif days <= _EXPIRY_WARN_DAYS:
            state = "expiring"
        else:
            state = "active"

    # Only the states that need the dealer to DO something raise an alert.
    # "active" returns none on purpose: a badge that lights up for good news
    # teaches him to ignore the badge.
    alerts = []
    if state == "lapsed":
        alerts.append({
            "urgency": "now",
            "title_hi": "आपकी लिस्टिंग बंद हो गई है",
            "detail_hi": (
                f"सदस्यता {until.strftime('%d-%m-%Y')} को खत्म हो गई, इसलिए आपके प्रोडक्ट "
                f"अभी किसानों को नहीं दिख रहे। ₹{price}/सीज़न भरते ही {districts} "
                f"{'जिले' if districts > 1 else 'जिला'} में दोबारा दिखने लगेंगे।"),
        })
    elif state == "expiring":
        alerts.append({
            "urgency": "now" if days <= 2 else "soon",
            "title_hi": (f"सदस्यता {days} दिन में खत्म हो रही है"
                         if days > 0 else "सदस्यता आज खत्म हो रही है"),
            "detail_hi": (
                f"{until.strftime('%d-%m-%Y')} के बाद आपके प्रोडक्ट भाव पेज से हट जाएंगे। "
                f"₹{price}/सीज़न ({_SEASON} महीने) — नवीनीकरण के लिए हमें WhatsApp करें, "
                f"लिंक भेज देंगे।"),
        })
    elif state == "unpaid" and verified:
        # Called, approved, but never paid — the close that was never made.
        alerts.append({
            "urgency": "soon",
            "title_hi": "भुगतान बाकी है — लिस्टिंग अभी लाइव नहीं",
            "detail_hi": (
                f"आपकी दुकान सत्यापित हो चुकी है। ₹{price}/सीज़न भरते ही आपके प्रोडक्ट "
                f"{districts} {'जिलों' if districts > 1 else 'जिले'} के भाव पेज पर दिखने लगेंगे।"),
        })

    return {"success": True, "data": {
        "state":          state,
        "days_left":      days,
        "paid_until":     until.isoformat() if until else None,
        "district_count": districts,
        "crop_count":     len(crops),
        "plan":           plan,
        "plan_label":     placements.plan_label(plan),
        "price":          price,
        "verified":       verified,
        "alerts":         alerts,
        # Drives the 📒 badge, same contract as /crop-calendar/nudges.
        "now_count":      sum(1 for a in alerts if a["urgency"] == "now"),
    }}


@router.get("/product-image/{product_id}.webp")
def product_image(product_id: int, db: Session = Depends(get_db)):
    """A product photo, served as bytes.

    Public and unauthenticated — it renders on the /bhav cards a farmer sees.
    Served from here rather than inlined as a data URI so the high-traffic bhav
    HTML stays small and the browser caches the photo across pages; the blob is
    deferred() on the model and this is its only reader.

    Cached hard: the URL is keyed by an id that never changes, so a replaced
    photo relies on the ?v= cache-buster the card appends from `updated_at`.
    """
    pack = dealer_products.image_of(db, product_id)
    if not pack:
        raise HTTPException(404, "no image")
    b64, mime = pack
    try:
        raw = base64.b64decode(b64)
    except Exception:
        raise HTTPException(404, "no image")
    return Response(content=raw, media_type=mime,
                    headers={"Cache-Control": "public, max-age=604800"})


# ── The dealer's own catalogue ────────────────────────────────
# He types what he sells; the admin puts the photos on (see routes/admin.py).
# That split is deliberate: an image accepted from a public form is a
# moderation queue nobody has time to run, on a surface where a bad picture
# goes out under our own verified tick.

class ProductIn(BaseModel):
    name_hi: str = ""
    name_en: Optional[str] = ""
    price: Optional[float] = None
    mrp: Optional[float] = None
    unit_hi: Optional[str] = ""
    badge: Optional[str] = ""


def _my_listing(db, user_id):
    """The caller's own account, or None. Products hang off the account, so any
    of his rows will do — the first is as good as the last."""
    rows = dealers.for_owner(db, user_id)
    return rows[0] if rows else None


@router.get("/products")
async def my_products(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _my_listing(db, current_user["user_id"])
    if not row:
        return {"success": True, "data": {"products": [], "max": dealer_products.MAX_PER_DEALER}}
    return {"success": True, "data": {
        "products": dealer_products.for_buyer(db, row.slug, row.owner_user_id,
                                              only_active=False),
        "max": dealer_products.MAX_PER_DEALER,
    }}


@router.post("/products")
async def add_product(
    payload: ProductIn,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _my_listing(db, current_user["user_id"])
    if not row:
        raise HTTPException(400, "पहले अपनी दुकान लिस्ट करें")
    data = payload.model_dump()
    problem = dealer_products.validate(data)
    if problem:
        raise HTTPException(400, problem)
    try:
        created = dealer_products.create(db, row.slug, row.owner_user_id, data)
    except Exception as e:
        if is_read_only_error(e):
            raise HTTPException(503, READ_ONLY)
        raise HTTPException(500, "प्रोडक्ट सेव नहीं हो पाया।")
    if not created:
        raise HTTPException(400, f"ज्यादा से ज्यादा {dealer_products.MAX_PER_DEALER} प्रोडक्ट जोड़ सकते हैं")
    return {"success": True, "data": dealer_products.as_dict(created)}


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ownership is checked here, not in the service — dealer_products.delete()
    is also the admin's tool and must not grow an auth check of its own."""
    row = _my_listing(db, current_user["user_id"])
    product = dealer_products.get(db, product_id)
    if not row or not product:
        raise HTTPException(404, "प्रोडक्ट नहीं मिला")
    owns = (product.owner_user_id and product.owner_user_id == row.owner_user_id) \
        or product.buyer_slug == row.slug
    if not owns:
        raise HTTPException(404, "प्रोडक्ट नहीं मिला")
    dealer_products.delete(db, product_id)
    return {"success": True, "data": {}}


@router.delete("/listings/{slug}")
async def delete_listing(
    slug: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Drop one district. Ownership-checked here, not in the service layer —
    dealers.delete() is also the admin's tool and must not gain an auth check
    that would then apply to admin calls too."""
    row = db.query(Buyer).filter(Buyer.slug == slug).first()
    if not row or row.owner_user_id != current_user["user_id"]:
        raise HTTPException(404, "लिस्टिंग नहीं मिली")
    dealers.delete(db, slug)
    return {"success": True, "data": {}}
