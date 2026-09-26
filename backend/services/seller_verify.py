# ============================================================
# backend/services/seller_verify.py
# The blue tick: a paid membership, and nothing more than that.
# ============================================================
# WHAT THE TICK CLAIMS — NOTHING ABOUT THE SELLER. Changed 2026-09-18. It used
# to mean "KrashiMitra ने फ़ोन पर इस विक्रेता की पहचान जाँची है", and the ₹ fee
# bought that phone call. That is a claim about a named person, published by
# this site, on a page where money changes hands, and keeping it true cost a
# call per seller.
#
# The tick now means what X's blue check means: this account pays for
# KrashiMitra प्रीमियम. So payment IS the grant — `record_payment()` sets
# users.seller_verified, because paying is the entire content of the badge and
# there is nothing left for a human to check.
#
# THE LEGAL GUARD MOVED, IT DID NOT GO AWAY. The old rule protected a claim.
# The new rule protects the absence of one: no user-facing string may read the
# tick as सत्यापित / verified / identity / a guarantee of the crop, the price
# or the deal. The moment one does, the site is publishing a claim it never
# checked — the exact exposure the never-a-legal-exposure rule exists to stop,
# arrived from the other direction. tests/test_seller_verification.py sweeps
# /verify, the feed copy and the admin WhatsApp template for those words.
#
# PAYING IS NOT SAYING YOU PAID. A upi:// hand-off reports nothing back
# (services/upi.py), so `claim_payment()` — the farmer's own "मैंने भेज दिया"
# button — writes `payment_claimed_at` and grants nothing. It exists to push
# his row to the top of the admin queue. Only a human who saw the credit calls
# `record_payment()`. If that ever inverts, the badge is free to anyone who can
# tap a button, and a test pins it.
#
# ADMIN STILL HAS A KILL SWITCH. `revoke()` clears the flag — for the one thing
# a paid badge still has to answer for, which is impersonation. X keeps the
# same power for the same reason: selling a checkmark to someone posing as
# someone else is not a neutral act just because the badge claims nothing.
#
# THE TICK EXPIRES, because a membership is a term, not a state.
# `expire_due()` clears the flag; idempotent, safe on a timer.
#
# TWO PLANS, AND NO STRUCK PRICE. ₹199/महीना and ₹499/3 महीने. Until
# 2026-09-25 each card showed a crossed-out "MRP" (₹399, ₹699) that was never
# a price anyone paid — which the CCPA's 2023 dark-pattern guidelines treat as
# a false reference price. Removed, and the env variables that could bring it
# back are gone with it. The only saving shown is a real one: three months
# for ₹499 against ₹597 for three single months — save_pct is computed from
# the monthly plan, never typed.
#
# CONFIG. Each price is env-overridable per plan — KM_VERIFY_M1_PRICE,
# KM_VERIFY_M3_PRICE — because the first
# real negotiation may not land on ₹199 and re-deploying to change a price is
# exactly the manual seam the everything-must-be-automatic rule bans.
# KM_VERIFY_FEE still overrides the monthly price, so the variable already set
# on Render keeps working; KM_VERIFY_MONTHS is retired, because the term now
# comes from the plan the farmer picked and not from the environment.
# ============================================================

import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from backend.database.db import SellerVerification, User

log = logging.getLogger(__name__)

# Statuses. The strings are unchanged from the phone-check era on purpose —
# renaming them would need a data migration on a free-tier Postgres that goes
# read-only without warning — but two of them now mean something new:
#
#   applied   → signed up, money not in the bank yet  (tick OFF)
#   paid      → membership running, paid for           (tick ON)
#   approved  → membership running, given free by the owner (tick ON)
#   rejected  → revoked, e.g. for impersonation        (tick OFF)
#   expired   → the term ran out                       (tick OFF)
#   declined  → the application was refused before any tick (tick was never ON)
#
# `declined` is new (2026-09-26) and is NOT `rejected`: a rejected row had a
# tick taken away and may be owed a refund; a declined one never had a tick
# and no confirmed money, so /verify tells him "आवेदन स्वीकार नहीं हुआ" and
# lets him apply again instead of "आपका टिक हटा दिया गया".
APPLIED, PAID, APPROVED, REJECTED, EXPIRED, DECLINED = (
    "applied", "paid", "approved", "rejected", "expired", "declined")
STATUSES = {APPLIED, PAID, APPROVED, REJECTED, EXPIRED, DECLINED}

# The two that mean "the badge is on right now". Anything reading the row
# instead of the flag must go through this, not compare to PAID by hand.
ACTIVE_STATUSES = {PAID, APPROVED}

# Kept because the signup form still asks — a member's own name and village are
# what the owner needs to reach him about a renewal, and a shop licence tells
# him whether he is talking to a farmer or a trader. It is NOT checked, and
# nothing on the site says it was.
ID_KINDS = ["aadhaar", "kcc", "shop_licence", "land_record", "other"]

ID_KIND_HI = {
    "aadhaar":      "आधार कार्ड",
    "kcc":          "किसान क्रेडिट कार्ड",
    "shop_licence": "दुकान / व्यापार लाइसेंस",
    "land_record":  "खतौनी / ज़मीन का कागज़",
    "other":        "कोई और पहचान",
}


# ── The price table ──────────────────────────────────────────

# code → (months, price). The order here is the order the cards are
# drawn in, cheapest entry first, because that is the one a farmer who has
# never paid for anything on this site will read first.
PLAN_DEFS = [
    ("m1", 1, 199),
    ("m3", 3, 499),
]
DEFAULT_PLAN = "m1"

PLAN_TERM_HI = {1: "1 महीने के लिए", 3: "3 महीने के लिए"}


def _rupees(env: str, fallback: int) -> int:
    try:
        return max(1, int(os.getenv(env, "") or fallback))
    except (TypeError, ValueError):
        return fallback


def plans() -> list:
    """The cards /verify draws, priced from env. Never an f-string of literals.

    `price` is what he pays. `mrp` is always None — kept only so an older
    cached page that still reads it draws no struck price. `per_month` is
    computed rather than stored so the two can never disagree — a card that
    said ₹499 / 3 महीने next to a hand-typed "₹150/महीना" would be wrong the
    first time a price moved.
    """
    out = []
    monthly = None
    for code, mon, price in PLAN_DEFS:
        # KM_VERIFY_FEE is the legacy single-price variable; it only ever meant
        # the monthly rate, so it applies to m1 and nothing else.
        legacy = _rupees("KM_VERIFY_FEE", price) if code == "m1" else price
        rupee = _rupees(f"KM_VERIFY_{code.upper()}_PRICE", legacy)
        if mon == 1:
            monthly = rupee
        # The real saving against paying month by month — never a typed figure.
        full = monthly * mon if (monthly and mon > 1) else None
        real = bool(full and full > rupee)
        out.append({
            "code":      code,
            "months":    mon,
            "price":     rupee,
            "mrp":       None,
            "per_month": round(rupee / mon),
            "term_hi":   PLAN_TERM_HI.get(mon, f"{mon} महीने के लिए"),
            "save_pct":  round((1 - rupee / full) * 100) if real else None,
            "save_vs":   full if real else None,
        })
    return out


def plan(code: str = "") -> dict:
    """One plan by code, falling back to the monthly one.

    Every caller that turns a farmer's choice into money goes through here, so
    an unknown code out of a request body buys the cheapest term rather than
    a free one or a crash.
    """
    code = (code or "").strip().lower()
    table = plans()
    for row in table:
        if row["code"] == code:
            return row
    for row in table:
        if row["code"] == DEFAULT_PLAN:
            return row
    return table[0]


def plan_codes() -> list:
    return [c for c, _m, _p, _q in PLAN_DEFS]


def fee(code: str = "") -> int:
    """What this plan costs. No argument = the monthly plan, which is what the
    admin queue and the collect message mean when they say "the fee"."""
    return plan(code)["price"]


def months(code: str = "") -> int:
    """The term this plan buys. Was env-wide and 12; now it comes from the plan."""
    return plan(code)["months"]


class RefundPending(ValueError):
    """His removed tick's fee has not been sent back yet — refund first."""


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
    """Sign up for the membership. Structurally cannot pay or tick.

    Mirrors dealers.from_signup: everything on this path arrives from a public
    form, so this function only ever writes the contact fields. If a future
    edit makes it able to set `status` or `paid_at` from `data`, the badge
    becomes free to anyone who can craft a request body — the fee is now the
    only thing between a farmer and a tick, so this is the whole gate.
    """
    row = get(db, user_id)
    now = datetime.utcnow()
    if row is None:
        row = SellerVerification(user_id=user_id, ref=_new_ref(), created_at=now)
        db.add(row)

    # A removed tick whose fee has not gone back yet: re-applying would move
    # the row off `rejected`, and refund_due() — the only thing that puts the
    # owed refund in front of the owner — would silently go False. So the
    # refund goes first; the /verify terms already promise it within 7 days.
    if refund_due(row):
        raise RefundPending(row.ref)

    # After a removal or a decline the money of that round is settled (never
    # paid, or paid and refunded), so the new application starts with none of
    # it — otherwise the queue shows "₹ मिला" on a signup that has paid nothing.
    if row.status in (REJECTED, DECLINED):
        row.paid_at = None
        row.paid_ref = None
        row.refunded_at = None
        row.payment_claimed_at = None
        row.valid_until = None
        row.approved_at = None

    # Re-applying after a rejection is allowed and starts clean; re-applying
    # while approved just refreshes the details on file.
    if row.status in (REJECTED, EXPIRED, DECLINED, None, ""):
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
    # The plan is the one thing on this form that costs money, so it is read
    # through plan(): an unknown code buys the monthly term, never a free one.
    chosen = plan(data.get("plan") or row.plan or "")
    row.plan = chosen["code"]
    # Re-priced on every signup on purpose. An application that sat unpaid for
    # a month must be collected at today's price, not at the one it was drawn
    # at — otherwise the struck figure on the card and the amount in the UPI
    # link disagree, and the farmer is looking at both.
    row.fee_amount = chosen["price"]
    row.updated_at = now

    db.commit()
    db.refresh(row)
    return row


# ── The owner's side — every one of these implies a human ────

def record_payment(db, ref: str, amount: int, paid_ref: str = "", *,
                   received_at=None, method: Optional[str] = None,
                   payer: str = "", note: str = "",
                   tds: int = 0) -> Optional[SellerVerification]:
    """Money arrived — so the tick goes on. Typed in by hand, and that is the design.

    A upi:// link hands off to the farmer's own app and reports nothing back,
    so `paid_at` means one thing: a human saw the credit. What is new since
    2026-09-18 is that this is also where the badge is granted. Under the old
    phone-check tick this function was forbidden from touching the flag; under
    a paid membership, payment is the whole of what the badge says, and making
    the farmer wait for a call he is no longer owed would just be a delay.

    Renewing extends from whichever end date is later, so paying early does not
    cost him the days he already has.
    """
    row = by_ref(db, ref)
    if not row:
        return None
    from backend.services import ledger
    now = datetime.utcnow()
    paid_on = received_at or now
    # Exactly what arrived: never bumped up to ₹1, never replaced by the plan's
    # list price. The ledger row goes first, so a refused one grants nothing.
    ledger.record(db, "verify", int(amount), payer=payer or row.full_name or "",
                  contact=row.phone or "", ref=paid_ref, method=method, note=note,
                  source_key=row.ref, received_at=paid_on, tds=tds)
    row.paid_at = paid_on
    row.paid_ref = (paid_ref or "").strip()[:64] or None
    row.fee_amount = int(amount)
    # A complimentary badge paying for itself stays `approved` — the owner gave
    # it, and that is worth still being able to see in the queue.
    if row.status != APPROVED:
        row.status = PAID
    row.reject_reason = None
    base = row.valid_until if (row.valid_until and row.valid_until > now) else now
    # The term he chose, not a site-wide constant: a ₹499 credit has to buy 3
    # months and a ₹199 one has to buy 1, or the cheaper plan is the better deal.
    row.valid_until = base + timedelta(days=30 * months(row.plan))
    row.updated_at = now

    user = db.query(User).filter(User.id == row.user_id).first()
    if user:
        user.seller_verified = True
    db.commit()
    db.refresh(row)
    return row


def claim_payment(db, user_id: int, paid_ref: str = "") -> Optional[SellerVerification]:
    """"मैंने पैसे भेज दिए" — his word for it, which grants nothing.

    Deliberately keyed on user_id, not ref: this is called from his own logged-in
    page, so the row is the one that belongs to him and cannot be another
    member's. It moves no status and never touches the flag — a upi:// hand-off
    reports nothing back, so the only thing a tap can honestly record is that he
    says he sent it. What it buys him is position: `pending_first` sorts claimed
    rows to the top of the admin queue, so the confirmation is minutes away
    rather than whenever someone next scrolls the list.
    """
    row = get(db, user_id)
    if not row:
        return None
    now = datetime.utcnow()
    row.payment_claimed_at = now
    # His UTR, if he typed one. Overwritten by the real one on confirmation.
    ref = (paid_ref or "").strip()[:64]
    if ref and not row.paid_at:
        row.paid_ref = ref
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def approve(db, ref: str, by: str = "admin") -> Optional[SellerVerification]:
    """Give the badge without a payment — the owner's comp.

    Under the phone-check tick this was the ONLY call allowed to set the flag.
    It is now the unusual path, not the normal one: record_payment grants the
    ordinary paid membership, and this exists for the ones the owner hands out
    — the first sellers on a new district page, someone he already knows, a
    goodwill month after a bad week. X does the same for accounts it wants on
    the platform.

    Still admin-only, and still nothing automatic may reach it: a code path
    that could call this is a code path that gives the badge away.
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
    # Extends from whichever end date is later, so a comp on top of a live
    # membership adds to it rather than replacing what he paid for.
    base = row.valid_until if (row.valid_until and row.valid_until > now) else now
    row.valid_until = base + timedelta(days=30 * months(row.plan))
    row.updated_at = now

    user = db.query(User).filter(User.id == row.user_id).first()
    if user:
        user.seller_verified = True
    db.commit()
    db.refresh(row)
    return row


def revoke(db, ref: str, reason: str = "", by: str = "admin"
           ) -> Optional[SellerVerification]:
    """Take the badge away. The kill switch a paid badge still needs.

    A membership that claims nothing about its holder still cannot be sold to
    someone posing as someone else, so this is the answer to impersonation, to
    a member using the tick to push a scam, and to a chargeback. X keeps the
    same power over a paid check for the same reason.

    It marks the money refundable, because a term that was cut short was not
    delivered. `refunded_at` stays None until a human sends it — the same rule
    as paid_at, for the same reason: no UPI rail here reports anything back.
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


# The old name, from when refusal came after a phone check. Kept because the
# admin endpoint, its button and the queue's status string all read "reject",
# and renaming a status would need a migration on a Postgres that goes
# read-only at its quota without warning.
reject = revoke


class NotDeclinable(ValueError):
    """Only an application still waiting on money can be declined."""


def decline(db, ref: str, reason: str, by: str = "admin"
            ) -> Optional[SellerVerification]:
    """Refuse an application that never got a tick. Not the kill switch.

    Only an `applied` row qualifies — money not confirmed, tick never on. A
    live membership goes through revoke(), which owes the refund; a declined
    application owes nothing, because record_payment() moves a row off
    `applied` the moment a human confirms money, so an `applied` row has no
    confirmed payment for this application.

    It never touches users.seller_verified: the flag is already off on an
    `applied` row, and a fifth writer of that flag is exactly what
    test_only_four_places_write_the_flag exists to stop.

    His "मैंने भेज दिया" claim is cleared, so a fresh application starts
    clean and does not jump the queue on a claim that was already looked at.
    """
    row = by_ref(db, ref)
    if not row:
        return None
    if row.status != APPLIED:
        raise NotDeclinable(row.status)
    now = datetime.utcnow()
    row.status = DECLINED
    row.reject_reason = (reason or "").strip()[:200] or None
    row.reviewed_at = now
    row.reviewed_by = (by or "admin")[:60]
    row.payment_claimed_at = None
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


CONTACT_HI = "+91 9870951001 (WhatsApp) या krashimitra038@gmail.com"
NOT_A_CHECK_HI = ("नीला टिक प्रीमियम सदस्यता का निशान है — यह पहचान की जाँच या "
                  "फसल, भाव या सौदे की गारंटी नहीं है।")


def notice(row: SellerVerification) -> tuple:
    """(subject, body) of the email for a declined application or a removed
    tick. Plain text, Hindi. None for any other status.

    Every refund sentence restates a term /verify already prints (money
    arrived but no tick, or a tick removed mid-term → the whole fee back
    within 7 days); nothing here may invent a new one. Both end by saying he
    can apply again, because he can — see apply().
    """
    name = (row.full_name or "").strip() or "किसान भाई"
    why = f"कारण: {row.reject_reason}\n" if row.reject_reason else ""
    again = "आप फिर से आवेदन कर सकते हैं — वही तरीका: https://krashimitra.in/bluetick\n\n"

    if row.status == DECLINED:
        subject = f"कृषि मित्र प्रीमियम — आपका आवेदन {row.ref}"
        middle = (
            f"कृषि मित्र प्रीमियम (नीला टिक) के लिए आपका आवेदन {row.ref} "
            f"स्वीकार नहीं हुआ है।\n{why}\n"
            "हमारे रिकॉर्ड में इस आवेदन का कोई भुगतान दर्ज नहीं है। अगर आपने शुल्क "
            f"भेजा था और आपके खाते से कट गया है, तो UTR / स्क्रीनशॉट के साथ {CONTACT_HI} "
            "पर बताइए — पैसा हमारे खाते में पहुँचा होगा तो पूरा शुल्क 7 दिन के अंदर "
            "वापस भेजा जाएगा।\n\n" + again)
    elif row.status == REJECTED:
        subject = f"कृषि मित्र प्रीमियम — आपका नीला टिक हटाया गया ({row.ref})"
        if refund_due(row):
            money = (f"आपका पूरा शुल्क ₹{row.fee_amount} 7 दिन के अंदर उसी UPI / खाते "
                     "में वापस भेजा जाएगा। रिफंड पहुँचने के बाद आप फिर से आवेदन कर "
                     "सकते हैं — वही तरीका: https://krashimitra.in/bluetick\n\n")
        else:
            money = again
        middle = (
            f"आपके खाते ({row.ref}) से कृषि मित्र प्रीमियम का नीला टिक हटा दिया गया है।\n"
            f"{why}\n{money}"
            f"कोई गलतफ़हमी लगे तो {CONTACT_HI} पर बताइए।\n\n")
    else:
        return None
    body = f"नमस्ते {name},\n\n{middle}{NOT_A_CHECK_HI}\n\n— कृषि मित्र"
    return subject, body


def notify(db, row: SellerVerification) -> bool:
    """Email him that his application was declined or his tick removed.
    True only if it was sent.

    One message, to his own account address, about his own membership — a
    service notice, not a campaign. Resend is already named in the privacy
    policy for "सूचना वाले ईमेल". An anonymised account (@deleted.invalid) is
    never written to. A failed send never undoes the action: the panel is
    told, and offers WhatsApp instead. The same reason also shows in his
    KrashiBook सूचनाएं, on /verify and on his profile, read from the row.
    """
    msg = notice(row)
    if not msg:
        return False
    user = db.query(User).filter(User.id == row.user_id).first()
    email = (user.email or "").strip() if user else ""
    if not email or email.endswith("@deleted.invalid"):
        return False
    from backend.utils import auth_utils
    try:
        return bool(auth_utils._send_with_resend(email, *msg))
    except Exception as e:                      # never let mail break the admin call
        log.warning("[seller_verify] notice failed for %s: %s", row.ref, e)
        return False


def record_refund(db, ref: str, *, sent_at=None, method: Optional[str] = None,
                  refund_ref: str = "", payer: str = "",
                  note: str = "") -> Optional[SellerVerification]:
    """The refund went out. `sent_at`/`method`/`refund_ref` are the outgoing
    transfer's own date and bank reference, so it matches the statement."""
    row = by_ref(db, ref)
    if not row:
        return None
    if row.refunded_at:
        return row          # already refunded — a second click must not refund twice
    when = sent_at or datetime.utcnow()
    if row.paid_at and row.fee_amount:
        from backend.services import ledger
        ledger.record(db, "verify", -int(row.fee_amount),
                      payer=payer or row.full_name or "",
                      contact=row.phone or "", source_key=row.ref, ref=refund_ref,
                      method=method, received_at=when,
                      note=("refund" + (f" — {note}" if note else "")))
    row.refunded_at = when
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def refund_due(row: Optional[SellerVerification]) -> bool:
    """Revoked, paid, and not yet sent back."""
    return bool(row and row.status == REJECTED and row.paid_at and not row.refunded_at)


# ── Expiry ───────────────────────────────────────────────────

def expire_due(db, now: Optional[datetime] = None) -> int:
    """Clear the tick on every window that has run out. Idempotent.

    Safe to call from a scheduler or a request path: it only ever moves a live
    membership→expired, so running it twice a minute changes nothing the second
    time. It sweeps `paid` as well as `approved` — a lapsed paid membership is
    the common case now, and filtering on `approved` alone would have left
    every paying member ticked forever.
    """
    now = now or datetime.utcnow()
    rows = (db.query(SellerVerification)
              .filter(SellerVerification.status.in_(tuple(ACTIVE_STATUSES)),
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


def is_active(row: Optional[SellerVerification]) -> bool:
    """Is the badge on, according to the row? Both paid and comped count.

    Anything reading this table instead of users.seller_verified must come
    through here — `row.status == PAID` was correct while paid was the only way
    to hold a live badge, and stopped being correct the day approve() became
    the owner's comp.
    """
    return bool(row and row.status in ACTIVE_STATUSES)


def days_left(row: Optional[SellerVerification], now: Optional[datetime] = None) -> Optional[int]:
    if not is_active(row) or not row.valid_until:
        return None
    return max(0, (row.valid_until - (now or datetime.utcnow())).days)


def payment_claimed(row: Optional[SellerVerification]) -> bool:
    """He says he sent the money and nobody has confirmed it yet.

    This is the queue's only urgent state: a farmer sitting on a payment he has
    made, with no badge, waiting on a human. It is also the one state a member
    can create himself, so it grants nothing — see claim_payment().
    """
    return bool(row and row.payment_claimed_at and not row.paid_at)


def pending_first(rows: list) -> list:
    """Order the admin queue by who is actually waiting on somebody.

    Claimed-but-unconfirmed first (he has paid and has no badge), then
    unpaid signups, then everything settled — newest within each group.
    """
    def key(r):
        if payment_claimed(r):
            group = 0
        elif r.status == APPLIED:
            group = 1
        else:
            group = 2
        stamp = r.updated_at or r.created_at or datetime.min
        return (group, -stamp.timestamp())
    return sorted(rows, key=key)


def to_dict(row: Optional[SellerVerification], now: Optional[datetime] = None) -> dict:
    """What the farmer's own page is allowed to see about his membership."""
    if not row:
        return {"status": None, "plan": None, "fee": fee(), "months": months(),
                "plans": plans()}
    chosen = plan(row.plan)
    return {
        "status":       row.status,
        "active":       is_active(row),
        "ref":          row.ref,
        "plan":         chosen["code"],
        "fee":          row.fee_amount or chosen["price"],
        "mrp":          chosen["mrp"],
        "months":       chosen["months"],
        "term_hi":      chosen["term_hi"],
        "plans":        plans(),
        "paid":         bool(row.paid_at),
        # Two different facts, and the page says different things for each:
        # "we have not seen the money yet" vs "send the money".
        "payment_claimed": payment_claimed(row),
        "claimed_at":   (row.payment_claimed_at.isoformat()
                         if row.payment_claimed_at else None),
        "full_name":    row.full_name,
        "phone":        row.phone,
        "village":      row.village,
        "district":     row.district,
        "state":        row.state,
        "id_kind":      row.id_kind,
        "reject_reason": row.reject_reason,
        "refunded":     bool(row.refunded_at),
        # Removed tick, fee not back yet — he cannot re-apply until it is.
        "refund_pending": refund_due(row),
        # When the owner declined / removed it. KrashiBook keys "seen" on it,
        # so a second removal lights the 📒 badge again.
        "reviewed_at":  row.reviewed_at.isoformat() if row.reviewed_at else None,
        "valid_until":  row.valid_until.isoformat() if row.valid_until else None,
        "days_left":    days_left(row, now),
        "applied_at":   row.created_at.isoformat() if row.created_at else None,
    }
