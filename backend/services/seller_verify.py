# ============================================================
# backend/services/seller_verify.py
# The blue tick: what it costs, and what it is allowed to mean.
# ============================================================
# WHAT THE TICK CLAIMS. krashi_bajar.html tells every buyer, in Hindi, that a
# ticked seller "KrashiMitra द्वारा सत्यापित है" — verified BY US. That is a
# claim about a person, published by this site, on a page where money changes
# hands. It is the exact shape of thing the project's never-a-legal-exposure
# rule exists to stop, and it is only safe while it is true.
#
# SO THE FEE BUYS THE CHECK, NOT THE TICK. Paying moves an application to
# `paid` and no further. `approve()` — a human, after a phone call that
# confirms the name, the number and the village — is the only thing in this
# codebase that sets users.seller_verified. Nothing in the payment path may
# call it, and a test pins that.
#
# This is the same split the dealer rail already runs on: dealers.record_payment
# explicitly does NOT flip active/verified for a self-serve account, because
# "the phone-verification call stays a hard gate". A farmer's badge is a
# stronger claim than a dealer's listing, not a weaker one.
#
# REJECTED MEANS REFUNDED. If the call does not check out, the badge is refused
# and the fee goes back (`reject()` marks the refund due; the admin sends it and
# records it). Keeping money for a service not rendered is a consumer-law
# argument this site cannot afford to have.
#
# THE TICK EXPIRES. A seller checked once is not "verified" forever — the claim
# goes stale, and an expiring badge is also what creates the renewal call.
# `expire_due()` clears the flag; it is idempotent and safe to run on a timer.
#
# CONFIG. KM_VERIFY_FEE (₹, default 199) and KM_VERIFY_MONTHS (default 12).
# Both env, for the same reason the listing fee is: re-deploying to change a
# price is exactly the manual seam the everything-must-be-automatic rule bans.
# ============================================================

import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from backend.database.db import SellerVerification, User

log = logging.getLogger(__name__)

# Statuses, in the only order they may be reached.
APPLIED, PAID, APPROVED, REJECTED, EXPIRED = (
    "applied", "paid", "approved", "rejected", "expired")
STATUSES = {APPLIED, PAID, APPROVED, REJECTED, EXPIRED}

# What a farmer can offer as proof on the call. Free text would be unusable in
# a queue; "other" keeps the list from becoming a gate.
ID_KINDS = ["aadhaar", "kcc", "shop_licence", "land_record", "other"]

ID_KIND_HI = {
    "aadhaar":      "आधार कार्ड",
    "kcc":          "किसान क्रेडिट कार्ड",
    "shop_licence": "दुकान / व्यापार लाइसेंस",
    "land_record":  "खतौनी / ज़मीन का कागज़",
    "other":        "कोई और पहचान",
}


def fee() -> int:
    try:
        return max(1, int(os.getenv("KM_VERIFY_FEE", "199") or 199))
    except (TypeError, ValueError):
        return 199


def months() -> int:
    try:
        return max(1, int(os.getenv("KM_VERIFY_MONTHS", "12") or 12))
    except (TypeError, ValueError):
        return 12


def _new_ref() -> str:
    """Short, unambiguous, and safe in a UPI `tr` field and a URL.

    No 0/O or 1/I: this gets read off a phone screen and typed into a bank
    statement search by someone matching a credit to an application.
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "KMV" + "".join(secrets.choice(alphabet) for _ in range(7))


def get(db, user_id: int) -> Optional[SellerVerification]:
    return (db.query(SellerVerification)
              .filter(SellerVerification.user_id == user_id).first())


def by_ref(db, ref: str) -> Optional[SellerVerification]:
    ref = (ref or "").strip().upper()
    if not ref:
        return None
    return (db.query(SellerVerification)
              .filter(SellerVerification.ref == ref).first())


# ── The farmer's side ────────────────────────────────────────

def apply(db, user_id: int, data: dict) -> SellerVerification:
    """Record an application. Structurally cannot approve, pay or tick.

    Mirrors dealers.from_signup: everything on this path arrives from a public
    form, so this function only ever writes the claim fields. If a future edit
    makes it able to set `status` from `data`, the badge becomes purchasable by
    anyone who can craft a request body.
    """
    row = get(db, user_id)
    now = datetime.utcnow()
    if row is None:
        row = SellerVerification(user_id=user_id, ref=_new_ref(), created_at=now)
        db.add(row)

    # Re-applying after a rejection is allowed and starts clean; re-applying
    # while approved just refreshes the details on file.
    if row.status in (REJECTED, EXPIRED, None, ""):
        row.status = APPLIED
        row.reject_reason = None
        row.reviewed_at = None
        row.reviewed_by = None
    elif row.status not in (PAID, APPROVED):
        row.status = APPLIED

    row.full_name = (data.get("full_name") or "").strip()[:120] or None
    row.phone     = (data.get("phone") or "").strip()[:20] or None
    row.village   = (data.get("village") or "").strip()[:80] or None
    row.district  = (data.get("district") or "").strip()[:80] or None
    row.state     = (data.get("state") or "").strip()[:80] or None
    kind = (data.get("id_kind") or "").strip().lower()
    row.id_kind   = kind if kind in ID_KINDS else "other"
    row.note      = (data.get("note") or "").strip()[:500] or None
    row.fee_amount = row.fee_amount or fee()
    row.updated_at = now

    db.commit()
    db.refresh(row)
    return row


# ── The owner's side — every one of these implies a human ────

def record_payment(db, ref: str, amount: int, paid_ref: str = "",
                   ) -> Optional[SellerVerification]:
    """Money arrived. Typed in by hand, and that is the design.

    A upi:// link hands off to the farmer's own app and reports nothing back,
    so `paid_at` means one thing: a human saw the credit. And note what this
    does NOT do — it never touches users.seller_verified. Paying buys the
    review; only approve() grants the badge.
    """
    row = by_ref(db, ref)
    if not row:
        return None
    now = datetime.utcnow()
    row.paid_at = now
    row.paid_ref = (paid_ref or "").strip()[:64] or None
    try:
        row.fee_amount = max(1, int(amount))
    except (TypeError, ValueError):
        row.fee_amount = row.fee_amount or fee()
    # An already-approved row paying again is a renewal, not a downgrade.
    if row.status != APPROVED:
        row.status = PAID
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def approve(db, ref: str, by: str = "admin") -> Optional[SellerVerification]:
    """The one call that sets the tick. Named for the phone call it implies.

    Callable from any status on purpose — the owner may want to verify someone
    who has not paid, and refusing that would put a rule in the code that the
    business does not actually have. What is NOT allowed is anything automatic
    reaching this, which is why it lives here and not in record_payment.
    """
    row = by_ref(db, ref)
    if not row:
        return None
    now = datetime.utcnow()
    row.status = APPROVED
    row.approved_at = now
    row.reviewed_at = now
    row.reviewed_by = (by or "admin")[:60]
    row.reject_reason = None
    # Renewing extends from whichever is later, so an early renewal does not
    # cost the seller the days he already paid for.
    base = row.valid_until if (row.valid_until and row.valid_until > now) else now
    row.valid_until = base + timedelta(days=30 * months())
    row.updated_at = now

    user = db.query(User).filter(User.id == row.user_id).first()
    if user:
        user.seller_verified = True
    db.commit()
    db.refresh(row)
    return row


def reject(db, ref: str, reason: str = "", by: str = "admin"
           ) -> Optional[SellerVerification]:
    """Refused after the check. Takes the badge away and marks a refund due.

    The fee bought a review; the review happened and the answer was no, so the
    money goes back. `refunded_at` stays None until a human sends it — the same
    rule as paid_at, for the same reason.
    """
    row = by_ref(db, ref)
    if not row:
        return None
    now = datetime.utcnow()
    row.status = REJECTED
    row.reviewed_at = now
    row.reviewed_by = (by or "admin")[:60]
    row.reject_reason = (reason or "").strip()[:200] or None
    row.valid_until = None
    row.approved_at = None
    row.updated_at = now

    user = db.query(User).filter(User.id == row.user_id).first()
    if user:
        user.seller_verified = False
    db.commit()
    db.refresh(row)
    return row


def record_refund(db, ref: str) -> Optional[SellerVerification]:
    row = by_ref(db, ref)
    if not row:
        return None
    row.refunded_at = datetime.utcnow()
    row.updated_at = row.refunded_at
    db.commit()
    db.refresh(row)
    return row


def refund_due(row: Optional[SellerVerification]) -> bool:
    """Rejected, paid, and not yet sent back."""
    return bool(row and row.status == REJECTED and row.paid_at and not row.refunded_at)


# ── Expiry ───────────────────────────────────────────────────

def expire_due(db, now: Optional[datetime] = None) -> int:
    """Clear the tick on every window that has run out. Idempotent.

    Safe to call from a scheduler or a request path: it only ever moves
    approved→expired, so running it twice a minute changes nothing the second
    time.
    """
    now = now or datetime.utcnow()
    rows = (db.query(SellerVerification)
              .filter(SellerVerification.status == APPROVED,
                      SellerVerification.valid_until.isnot(None),
                      SellerVerification.valid_until <= now).all())
    if not rows:
        return 0
    for row in rows:
        row.status = EXPIRED
        row.updated_at = now
        user = db.query(User).filter(User.id == row.user_id).first()
        if user:
            user.seller_verified = False
    db.commit()
    log.info("[seller_verify] expired %d badge(s)", len(rows))
    return len(rows)


def days_left(row: Optional[SellerVerification], now: Optional[datetime] = None) -> Optional[int]:
    if not row or row.status != APPROVED or not row.valid_until:
        return None
    return max(0, (row.valid_until - (now or datetime.utcnow())).days)


def to_dict(row: Optional[SellerVerification], now: Optional[datetime] = None) -> dict:
    """What the farmer's own page is allowed to see about his application."""
    if not row:
        return {"status": None, "fee": fee(), "months": months()}
    return {
        "status":       row.status,
        "ref":          row.ref,
        "fee":          row.fee_amount or fee(),
        "months":       months(),
        "paid":         bool(row.paid_at),
        "full_name":    row.full_name,
        "phone":        row.phone,
        "village":      row.village,
        "district":     row.district,
        "state":        row.state,
        "id_kind":      row.id_kind,
        "reject_reason": row.reject_reason,
        "refunded":     bool(row.refunded_at),
        "valid_until":  row.valid_until.isoformat() if row.valid_until else None,
        "days_left":    days_left(row, now),
        "applied_at":   row.created_at.isoformat() if row.created_at else None,
    }
