# ============================================================
# services/account_delete.py
# "खाता हटाएँ" — a farmer erasing his own account.
#
# THE ROW STAYS; THE PERSON GOES. Hard-deleting the users row would take the
# gapless account numbers with it — deleting a user_profiles row opens a hole
# the boot-time compaction pass closes by RENUMBERING every later account — and
# the DB refuses to un-verify an account that still has a profile. So nothing
# here deletes either row or touches is_verified / user_id. It overwrites the
# personal fields on both, which no trigger watches:
#
#   users           name → "हटाया गया खाता", email → deleted-<id>@deleted.invalid
#                   (frees the real address for a fresh signup, and is the marker
#                   resolve_token_user() uses to kill every token already issued),
#                   password → unusable, Google link / OTP / place → NULL
#   user_profiles   every personal field → NULL / default
#
# Everything that is only his is deleted (posts + their media, chats, crop
# calendar, alerts, push, likes, follows, cart, appeals). Comments on OTHER
# people's posts keep their place in the thread with the text replaced, so a
# reply to him still reads as a reply. Money records stay: the payments ledger
# (8 years, income tax / GST) and a paid blue-tick row's name, phone and
# amount. What he registered with is copied to account_deletions for 180 days
# (IT Rules 2021 r.3(1)(h)) and erased by purge_expired().
#
# Only ever called for the account that proved it is his (password and/or
# OTP) — see routes/account_delete.py. Nothing here runs in bulk.
# ============================================================
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from backend.database.db import (AccountDeletion, BazarComment, BazarCommentLike,
                                 BazarFollow, BazarLike,
                                 BazarPost, Buyer, ChatHistory, CropAppeal,
                                 DealerProduct, DukanShop, MandiAlert, Order,
                                 PushSubscription, RentalProvider,
                                 SellerVerification, User, UserCrop, UserProfile)

log = logging.getLogger("krishi.account_delete")

DELETED_NAME = "हटाया गया खाता"
DELETED_DOMAIN = "@deleted.invalid"          # RFC 2606: can never be a real inbox
REMOVED_COMMENT = "यह कमेंट हटा दिया गया।"
HOLD_DAYS = 180
REASONS = {
    "not_needed": "अब ज़रूरत नहीं",
    "privacy":    "गोपनीयता की चिंता",
    "messages":   "बहुत ज़्यादा सूचनाएँ",
    "other_app":  "दूसरा ऐप / वेबसाइट",
    "problem":    "वेबसाइट में दिक्कत",
    "other":      "अन्य",
}

# user_profiles columns that are NOT personal and must keep their value.
_PROFILE_KEEP = {"id", "user_id", "name", "language", "created_at", "updated_at"}


def is_deleted(user: User | None) -> bool:
    return bool(user and (user.email or "").endswith(DELETED_DOMAIN))


def has_password(user: User) -> bool:
    """A Google-only account never chose a password, so it confirms with OTP
    alone. Anything that signed up by email confirms with both."""
    return (user.auth_provider or "email") != "google" and \
        (user.hashed_password or "").startswith("$2")


def _wipe_profile(profile: UserProfile) -> None:
    for col in UserProfile.__table__.columns:
        if col.name in _PROFILE_KEEP:
            continue
        default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
        setattr(profile, col.name, default)
    profile.name = DELETED_NAME
    profile.updated_at = datetime.utcnow()


def _drop_posts(db, uid: int) -> int:
    from backend.routes.bazar import purge_post   # the one removal path for a post
    posts = db.query(BazarPost).filter(BazarPost.users_id == uid).all()
    for p in posts:
        purge_post(db, p)
    return len(posts)


def _undo_likes(db, uid: int) -> int:
    n = 0
    for like in db.query(BazarLike).filter(BazarLike.users_id == uid).all():
        post = db.query(BazarPost).filter(BazarPost.id == like.post_id).first()
        if post:
            post.likes_count = max(0, (post.likes_count or 0) - 1)
        db.delete(like)
        n += 1
    for like in db.query(BazarCommentLike).filter(BazarCommentLike.users_id == uid).all():
        c = db.query(BazarComment).filter(BazarComment.id == like.comment_id).first()
        if c:
            c.likes_count = max(0, (c.likes_count or 0) - 1)
        db.delete(like)
        n += 1
    return n


def erase(db, user: User, verified_by: str, reason: str = "") -> AccountDeletion:
    """Erase one account's personal data. Commits. Idempotent-safe: a second
    call on an already-deleted account is refused by the caller."""
    uid = user.id
    now = datetime.utcnow()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.user_id).first() \
        if user.user_id is not None else None

    # The 180-day hold — taken BEFORE anything is overwritten.
    hold = AccountDeletion(
        users_id=uid, account_no=user.user_id, deleted_at=now,
        verified_by=verified_by[:40],
        reason=REASONS.get(reason) if reason in REASONS else None,
        reg_name=(profile.name if profile and profile.name else user.name),
        reg_email=user.email,
        reg_phone=(profile.phone_number if profile else None),
        purge_after=now + timedelta(days=HOLD_DAYS),
    )

    erased: dict[str, int] = {}
    erased["posts"] = _drop_posts(db, uid)
    erased["likes"] = _undo_likes(db, uid)

    comments = db.query(BazarComment).filter(BazarComment.users_id == uid).all()
    for c in comments:
        c.text = REMOVED_COMMENT
        c.offer_amount = None
        c.kind = "comment"
    erased["comments_blanked"] = len(comments)

    erased["follows"] = db.query(BazarFollow).filter(
        (BazarFollow.follower_id == uid) | (BazarFollow.following_id == uid)
    ).delete(synchronize_session=False)
    erased["chats"] = db.query(ChatHistory).filter(ChatHistory.user_id == uid) \
        .delete(synchronize_session=False)
    erased["crops"] = db.query(UserCrop).filter(UserCrop.user_id == uid) \
        .delete(synchronize_session=False)
    erased["alerts"] = db.query(MandiAlert).filter(MandiAlert.user_id == uid) \
        .delete(synchronize_session=False)
    erased["push"] = db.query(PushSubscription).filter(PushSubscription.user_id == uid) \
        .delete(synchronize_session=False)
    erased["appeals"] = db.query(CropAppeal).filter(CropAppeal.user_id == uid) \
        .delete(synchronize_session=False)
    try:
        from backend.routes.cart import CartItem
        erased["cart"] = db.query(CartItem).filter(CartItem.user_id == uid) \
            .delete(synchronize_session=False)
    except Exception:
        pass

    # Orders are a dealer's record of a quote — keep what was asked for, drop who.
    orders = db.query(Order).filter(Order.user_id == uid).all()
    for o in orders:
        o.user_name = None
        o.user_email = None
        o.customer_name = None
        o.phone = ""
        o.pincode = None
    erased["orders_anonymised"] = len(orders)

    # Blue tick: a paid row is a tax record (name, phone, amount stay); an
    # unpaid application is nothing but personal data.
    for v in db.query(SellerVerification).filter(SellerVerification.user_id == uid).all():
        if v.paid_at:
            v.village = v.district = v.state = v.id_kind = v.note = None
            v.valid_until = None
            v.updated_at = now
        else:
            db.delete(v)

    # His listings go dark rather than vanish — they carry payment history.
    n = 0
    for M in (Buyer, DukanShop, RentalProvider, DealerProduct):
        for row in db.query(M).filter(M.owner_user_id == uid).all():
            if getattr(row, "active", False):
                row.active = False
                n += 1
    erased["listings_off"] = n

    # And last, the two identity rows — overwritten, never deleted.
    if profile:
        _wipe_profile(profile)
    user.name = DELETED_NAME
    user.email = f"deleted-{uid}{DELETED_DOMAIN}"
    user.hashed_password = "!deleted"          # not a bcrypt hash: verify_password() fails closed
    user.google_id = None
    user.otp = None
    user.otp_expiry = None
    user.village = user.district = user.primary_crop = None
    user.seller_verified = False

    hold.erased = json.dumps(erased)
    db.add(hold)
    db.commit()
    db.refresh(hold)
    log.info("account %s erased by its owner: %s", uid, erased)
    return hold


def purge_expired(db) -> int:
    """Daily: drop the registration details once the 180-day hold is over."""
    now = datetime.utcnow()
    rows = db.query(AccountDeletion).filter(
        AccountDeletion.purge_after <= now, AccountDeletion.purged_at.is_(None)).all()
    for r in rows:
        r.reg_name = r.reg_email = r.reg_phone = None
        r.purged_at = now
    if rows:
        db.commit()
    return len(rows)
