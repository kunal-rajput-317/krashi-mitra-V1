# ============================================================
# routes/admin_rental.py
# Admin API for किराये की मशीनें — /admin/rental/*
#
# A SEPARATE ROUTER FROM admin_dukan.py, on purpose, and for that module's own
# reason: those rows are shops selling goods over a counter (DukanShop /
# DukanItem), these are people hiring a machine out by the hour (RentalProvider
# / RentalListing). The auth and the read-only guard are shared because they
# are infrastructure; nothing else is. A fertiliser shop must never surface on
# a tractor-hire page just because both are "listings".
#
# THE PAYMENT MECHANICS ARE DELIBERATELY IDENTICAL to /admin/dukan's — the same
# services/upi.py collect link, the same hand-entered confirmation, the same
# "a upi:// link reports nothing back, so only a human who saw the credit may
# set paid_at" rule. Same rail, separate books.
#
# THERE IS NO CATALOGUE CRUD HERE, and that is the one real difference from
# admin_dukan.py. A machine is a row in backend/data/rental_equipment.json,
# carrying a summary, a "क्या जाँचें" checklist and tips — editorial prose that
# is written and reviewed in git, not typed into a form at 11pm. GET /equipment
# below serves that registry read-only so the panel can populate its dropdown
# and show the admin what the machine SHOULD cost while they key in what this
# owner actually charges.
#
# THE TERM IS ENFORCED BY THE READ PATHS, NOT BY A SWEEP. Nothing here expires
# an owner on a schedule; rental.is_live is consulted on every render, so a
# listing whose paid_until has passed is simply absent from the next request.
# That is why there is no "expire now" endpoint and why a renewal needs no
# repair step: recording the payment moves the date and the rows are back.
# ============================================================

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.routes.admin import admin_db, require_admin
from backend.services import free_month, rental

router = APIRouter(prefix="/admin/rental", tags=["admin-rental"])


def _write(fn, *args, **kwargs):
    """Read-only guard, worded for this panel.

    Neon's free tier flips the compute read-only without warning and reads keep
    working throughout — so an owner typed in during an episode would otherwise
    die with a 500 after the admin keyed a whole address off a phone call. Say
    what happened and that nothing was saved.
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


def _provider_dict(db, row) -> dict:
    """One owner as the panel wants it: the row, plus what it can only learn by
    looking elsewhere — how many machines it lists, how long its paid term has
    left, and whether that term has already run out."""
    return {
        "slug": row.slug, "name": row.name, "kind": row.kind or "owner",
        "kind_label": rental.KIND_LABELS.get(row.kind or "owner", ""),
        "state": row.state or "", "district": row.district or "",
        "address": row.address or "", "phone": row.phone or "",
        "whatsapp": row.whatsapp or "", "since": row.since or "",
        "note": row.note or "", "lat": row.lat, "lon": row.lon,
        "plan": row.plan, "commission_pct": row.commission_pct,
        "plan_months": rental.plan_months_of(row),
        "verified": bool(row.verified), "active": bool(row.active),
        "status": row.status, "owner_user_id": row.owner_user_id,
        "called_at": row.called_at.isoformat() if row.called_at else None,
        "call_count": row.call_count or 0, "call_result": row.call_result or "",
        "paid_at": row.paid_at.isoformat() if row.paid_at else None,
        "paid_amount": row.paid_amount, "payment_ref": row.payment_ref or "",
        "paid_until": row.paid_until.isoformat() if row.paid_until else None,
        # None here is "no clock is running", NOT "0 days left" — an owner who
        # has never paid is live under the onboarding grace and the panel says
        # so differently. See rental.days_left.
        "days_left": rental.days_left(row),
        "expiring": rental.expiring_soon(row),
        # The free first month, and whether this owner can still be offered it.
        # `free_month` stays true after it runs out, so the panel can say "the
        # free month ended" instead of reporting a renewal on an owner who never
        # paid a rupee — a different call, with a different opening sentence.
        "free_month": rental.on_free_month(row),
        "may_free_month": rental.may_free_month(row),
        "live": rental.is_live(row), "lapsed": rental.is_lapsed(row),
        "listings": len(rental.listings_for_provider(db, row.slug, only_active=False)),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _listing_dict(row) -> dict:
    """One rate. `equipment_name` is resolved from the JSON registry rather
    than stored, so renaming a machine in the file renames it everywhere at
    once — and a listing pointing at a machine that has since been dropped
    reads as its slug instead of crashing the panel."""
    item = rental.by_slug(row.equipment_slug)
    return {
        "id": row.id, "equipment_slug": row.equipment_slug,
        "equipment_name": (item or {}).get("name_hi") or row.equipment_slug,
        "equipment_emoji": (item or {}).get("emoji") or "🚜",
        "known": bool(item),
        "rate": row.rate, "rate_unit_hi": row.rate_unit_hi or "",
        "min_charge": row.min_charge,
        "with_operator": bool(row.with_operator),
        "fuel_included": bool(row.fuel_included),
        "available": bool(row.available), "active": bool(row.active),
        "note": row.note or "", "sort_order": row.sort_order or 0,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# ── the equipment registry, read-only ───────────────────────

@router.get("/equipment")
async def list_equipment(_: str = Depends(require_admin)):
    """The JSON registry, for the panel's machine dropdown.

    Each row carries its editorial rate range and the units that machine is
    normally hired by, so the form can pre-fill the unit and show the admin
    what is normal while they type what this owner actually charges. Read-only
    on purpose — see the module header on why the catalogue is not CRUD.
    """
    out = []
    for e in rental.equipment():
        rates = rental.rates(e)
        out.append({
            "slug": e["slug"], "name_hi": e["name_hi"],
            "name_en": e.get("name_en") or "", "emoji": e.get("emoji") or "🚜",
            "cat": e["cat"],
            "cat_label": rental.category_of(e).get("label_hi") or "",
            # The units this machine is actually quoted in — the dropdown the
            # panel offers, so two owners of the same machine cannot end up
            # with rates in units that do not compare.
            "units": [r["unit_hi"] for r in rates],
            "typical": [{"unit_hi": r["unit_hi"], "min": r["min"], "max": r["max"]}
                        for r in rates],
        })
    return {"success": True, "equipment": out,
            "categories": rental.categories(),
            "updated": rental.updated()}


# ── providers ───────────────────────────────────────────────

@router.get("/providers")
async def list_providers(
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    from backend.services import upi
    rows = rental.provider_all(db)
    return {"success": True,
            "providers": [_provider_dict(db, r) for r in rows],
            "counts": rental.counts(db),
            "plans": list(rental.PLANS),
            "kinds": [{"key": k, "label": rental.KIND_LABELS[k]} for k in rental.KINDS],
            # Sent rather than hardcoded in the HTML so the rate card and the
            # warning threshold have one home.
            "plan_months": list(rental.PLAN_MONTHS),
            "default_months": rental.SEASON_MONTHS,
            "expiring_soon_days": rental.EXPIRING_SOON_DAYS,
            "call_results": list(rental.CALL_RESULTS),
            # The public offer's own term, so the button in the panel and the
            # card on /rental can never advertise different months.
            "free_months": free_month.FREE_MONTHS,
            "upi_ready": upi.configured()}


@router.post("/providers")
async def create_provider(
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    problem = rental.validate_provider(payload)
    if problem:
        raise HTTPException(400, problem)
    row = _write(rental.provider_create, db, payload)
    return {"success": True, "provider": _provider_dict(db, row),
            "counts": rental.counts(db)}


@router.patch("/providers/{slug}")
async def update_provider(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Also the approve path and the plan switch: {"active": true} or
    {"plan": "commission", "commission_pct": 5}. Both are settable only from
    here — there is no public route into either."""
    current = rental.provider_get(db, slug)
    if not current:
        raise HTTPException(404, "Unknown provider")
    # Validate only when the payload carries a field validate_provider judges —
    # a lone {"active": true} must not be rejected for having no name in it.
    if any(k in payload for k in ("name", "district", "phone", "whatsapp",
                                  "kind", "plan", "commission_pct", "plan_months")):
        merged = _provider_dict(db, current)
        merged.update(payload)
        problem = rental.validate_provider(merged)
        if problem:
            raise HTTPException(400, problem)
    row = _write(rental.provider_update, db, slug, payload)
    if not row:
        raise HTTPException(404, "Unknown provider")
    return {"success": True, "provider": _provider_dict(db, row),
            "counts": rental.counts(db)}


@router.delete("/providers/{slug}")
async def delete_provider(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Deletes the owner AND every rate they listed — see rental.provider_delete
    for why that cascade is hand-rolled."""
    if not _write(rental.provider_delete, db, slug):
        raise HTTPException(404, "Unknown provider")
    return {"success": True, "counts": rental.counts(db)}


@router.post("/providers/{slug}/free-month")
async def start_free_month(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Give this owner the free first month — the offer /rental advertises.

    NOT A PAYMENT ROUTE. It never touches `paid_at`, so the panel's `paying`
    count keeps meaning "money actually arrived" and a gifted month can never
    be mistaken for a sale. What it does set is `paid_until`, which is what
    turns the offer into an actual month rather than an open-ended freebie:
    `rental.is_live` reads that date on every render, so the month ends itself
    and hands the caller a reason to ring back.

    Once per owner, refused with a sentence rather than a 500 — see
    free_month.may_grant on why re-granting is not an option.
    """
    row = rental.provider_get(db, slug)
    if not row:
        raise HTTPException(404, "Unknown provider")
    if not rental.may_free_month(row):
        raise HTTPException(
            400,
            "इनका मुफ़्त महीना पहले ही शुरू हो चुका है (या ये पैसे दे चुके हैं) — "
            "आगे बढ़ाने के लिए पेमेंट दर्ज करें।"
        )
    row = _write(rental.start_free_month, db, slug)
    if not row:
        raise HTTPException(404, "Unknown provider")
    return {"success": True, "provider": _provider_dict(db, row),
            "counts": rental.counts(db)}


@router.post("/providers/{slug}/call")
async def log_call(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    row = _write(rental.log_call, db, slug,
                 (payload.get("result") or ""), (payload.get("note") or ""))
    if not row:
        raise HTTPException(404, "Unknown provider")
    return {"success": True, "provider": _provider_dict(db, row),
            "counts": rental.counts(db)}


@router.get("/providers/{slug}/collect")
async def collect(
    slug:    str,
    amount:  str = "",
    purpose: str = "",
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """UPI QR + deep link + a ready-to-send WhatsApp message for one owner.

    A request to pay, never a record of one. The payment is only real once a
    human sees it in the bank app and posts it to /payment below. `amount`
    stays editable per request because a first-season price is a real
    negotiation, not a constant.
    """
    from backend.services import upi
    row = rental.provider_get(db, slug)
    if not row:
        raise HTTPException(404, "Unknown provider")
    if not upi.configured():
        raise HTTPException(
            503,
            "UPI is not configured — set KM_UPI_ID and KM_UPI_NAME in the "
            "environment, then restart. Nothing is hardcoded on purpose: a "
            "wrong VPA sends an owner's money to a stranger."
        )
    pack = upi.collect(row.name or "", row.district or "",
                       amount or None, purpose or "किराये की मशीन लिस्टिंग")
    pack["plan"] = row.plan
    pack["commission_pct"] = row.commission_pct
    return {"success": True, "collect": pack}


@router.post("/providers/{slug}/payment")
async def record_payment(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    """Mark an owner paid. Hand-entered from the bank app, by design — there is
    no callback that could do it, so this is the only thing that sets paid_at."""
    from backend.services import upi
    amount = upi.clean_amount(payload.get("amount"), default=0)
    if amount < upi.MIN_AMOUNT:
        raise HTTPException(
            400,
            f"Enter the amount actually received (₹{upi.MIN_AMOUNT}–₹{upi.MAX_AMOUNT})")
    # None on purpose when nothing was sent: record_payment then extends by the
    # owner's own agreed term, which is what a plain renewal means. A number
    # here is a one-off override for this payment only.
    months = payload.get("months")
    months = rental.clean_months(months) if str(months or "").strip() else None
    row = _write(rental.record_payment, db, slug, amount,
                 (payload.get("ref") or ""), months)
    if not row:
        raise HTTPException(404, "Unknown provider")
    return {"success": True, "provider": _provider_dict(db, row),
            "counts": rental.counts(db)}


# ── listings ────────────────────────────────────────────────

@router.get("/providers/{slug}/listings")
async def list_listings(
    slug: str,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    if not rental.provider_get(db, slug):
        raise HTTPException(404, "Unknown provider")
    rows = rental.listings_for_provider(db, slug, only_active=False)
    return {"success": True, "listings": [_listing_dict(r) for r in rows]}


@router.post("/providers/{slug}/listings")
async def create_listing(
    slug:    str,
    payload: dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    if not rental.provider_get(db, slug):
        raise HTTPException(404, "Unknown provider")
    problem = rental.validate_listing(payload)
    if problem:
        raise HTTPException(400, problem)
    row = _write(rental.listing_create, db, slug, payload)
    if not row:
        # The unique constraint, turned into a sentence rather than a 500.
        raise HTTPException(400, "यह मशीन इस मालिक के लिए पहले से जुड़ी है")
    return {"success": True, "listing": _listing_dict(row),
            "counts": rental.counts(db)}


@router.patch("/listings/{listing_id}")
async def update_listing(
    listing_id: int,
    payload:    dict,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    current = rental.listing_get(db, listing_id)
    if not current:
        raise HTTPException(404, "Unknown listing")
    if any(k in payload for k in ("rate", "rate_unit_hi", "min_charge")):
        merged = _listing_dict(current)
        merged.update(payload)
        problem = rental.validate_listing(merged)
        if problem:
            raise HTTPException(400, problem)
    row = _write(rental.listing_update, db, listing_id, payload)
    if not row:
        raise HTTPException(404, "Unknown listing")
    return {"success": True, "listing": _listing_dict(row),
            "counts": rental.counts(db)}


@router.delete("/listings/{listing_id}")
async def delete_listing(
    listing_id: int,
    _:  str     = Depends(require_admin),
    db: Session = Depends(admin_db),
):
    if not _write(rental.listing_delete, db, listing_id):
        raise HTTPException(404, "Unknown listing")
    return {"success": True, "counts": rental.counts(db)}
