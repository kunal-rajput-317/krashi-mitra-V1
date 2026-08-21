# ============================================================
# backend/routes/alerts.py
# KrashiMitra — Mandi price alerts (Web Push)
#
# The 🔔 toggle on a /bhav page subscribes a farmer to one crop+mandi. /bhav
# pages are anonymous and edge-cached, so the toggle state is hydrated
# client-side, never baked into the cached HTML.
#
#   GET  /alerts/vapid-key      → public key for pushManager.subscribe()
#   GET  /alerts/mandi/status   → is this user (or this device) subscribed?
#   POST /alerts/mandi          → subscribe — no login required
#   POST /alerts/mandi/off      → unsubscribe
#
# Subscribing needed a login until 2026-08-21, on the reasoning that an alert
# should belong to an account rather than to a browser a cache-clear can erase.
# In practice it erased the feature instead: the whole site had ONE subscriber,
# because the bell sits on the /bhav pages Google traffic lands on and asking a
# stranger for an email OTP before his first price alert loses him.
#
# The reasoning was also weaker than it looked. A push subscription is bound to
# the browser no matter who owns the row — clear it and the endpoint dies with
# it, account or no account — and a new phone has to grant permission and
# subscribe again regardless. So the gate protected almost nothing real.
#
# An account still helps once there IS one: /auth/claim-guest adopts this
# browser's user_id-NULL alerts on the farmer's next login, after which they
# fan out to all of his devices (see _devices_for in push_service). Anonymous
# alerts stay pinned to the endpoint that created them, which is exactly where
# the farmer who set one is standing.
# ============================================================

import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.db import (
    MandiAlert, PushSubscription, User, UserProfile, get_db, acct,
)
from backend.utils.auth_utils import resolve_token_user_id

router = APIRouter(prefix="/alerts", tags=["alerts"])

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()



class PushKeys(BaseModel):
    p256dh: str
    auth:   str


class PushSub(BaseModel):
    endpoint: str
    keys:     PushKeys


class MandiAlertOn(BaseModel):
    subscription: PushSub
    commodity:    str
    state:        Optional[str] = None
    district:     Optional[str] = None
    user_agent:   Optional[str] = None


class MandiAlertOff(BaseModel):
    endpoint:  str
    commodity: str
    state:     Optional[str] = None
    district:  Optional[str] = None


def _norm(v: Optional[str]) -> Optional[str]:
    v = (v or "").strip()
    return v or None


def _user_id(authorization: Optional[str]) -> Optional[int]:
    """user_id from a Bearer token, or None. Never raises — callers decide
    whether anonymous is acceptable for their endpoint.

    Goes through resolve_token_user_id() rather than decoding the JWT here: a
    valid signature does not prove the account still exists, is still verified,
    or that the id was not recycled to somebody else."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return resolve_token_user_id(authorization.split(" ", 1)[1].strip())


def display_name(db: Session, user_id: int) -> Optional[str]:
    """The farmer's name for the mandi_alerts.user_name convenience copy.

    Prefers user_profiles.name — that is the name he actually filled in — and
    falls back to the signup name on users, which for a Google login is whatever
    Google supplied. Returns None rather than a placeholder: an empty cell reads
    as "no name on file", where "Unknown" reads like a real answer."""
    profile = (db.query(UserProfile)
                 .filter(UserProfile.user_id == acct(user_id))
                 .first())
    if profile and (profile.name or "").strip():
        return profile.name.strip()[:120]
    user = db.query(User).filter(User.id == user_id).first()
    if user and (user.name or "").strip():
        return user.name.strip()[:120]
    return None


# ── GET /alerts/vapid-key ────────────────────────────────────

@router.get("/vapid-key")
def vapid_key():
    """The browser needs this to call pushManager.subscribe(). When push isn't
    configured we say so plainly so the UI can hide the bell instead of
    offering a toggle that could never deliver anything."""
    return {
        "success": bool(VAPID_PUBLIC_KEY),
        "message": "" if VAPID_PUBLIC_KEY else "push not configured",
        "data":    {"key": VAPID_PUBLIC_KEY, "enabled": bool(VAPID_PUBLIC_KEY)},
    }


# ── GET /alerts/mandi/status ─────────────────────────────────

@router.get("/mandi/status")
def mandi_status(
    endpoint:      str           = Query(...),
    commodity:     str           = Query(...),
    state:         Optional[str] = Query(None),
    district:      Optional[str] = Query(None),
    db:            Session       = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """Paint the bell. A signed-in farmer's alert is found by account, so it
    shows as ON even on a phone he has never subscribed from. Legacy
    device-only alerts are still matched by endpoint so their owner can see —
    and switch off — what they turned on before the gate existed."""
    commodity = commodity.strip()
    state, district = _norm(state), _norm(district)

    base = db.query(MandiAlert).filter(
        MandiAlert.commodity == commodity,
        MandiAlert.state     == state,
        MandiAlert.district  == district,
        MandiAlert.active.is_(True),
    )

    uid = _user_id(authorization)
    if uid is not None and base.filter(MandiAlert.user_id == uid).first():
        # The row says active, but a device that changed hands (shared phone,
        # new owner) or got pruned as dead (404/410) leaves it undeliverable —
        # match _devices_for()'s own definition of "reachable" rather than
        # trusting the row alone, or the bell would say ON forever with
        # nothing ever arriving again.
        has_device = db.query(PushSubscription).filter(
            PushSubscription.user_id == uid,
            PushSubscription.active.is_(True),
        ).first() is not None
        return {"success": True, "message": "", "data": {"subscribed": has_device}}

    sub = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    on = bool(sub) and base.filter(
        MandiAlert.subscription_id == sub.id,
        MandiAlert.user_id.is_(None),
    ).first() is not None
    return {"success": True, "message": "", "data": {"subscribed": on}}


# ── POST /alerts/mandi — turn the bell ON ────────────────────

@router.post("/mandi")
def mandi_alert_on(
    body:          MandiAlertOn,
    db:            Session       = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """Turn the bell on, with or without an account.

    Anonymous is the common case by design: this is the first thing a farmer who
    arrived from a Google search is asked to do, and it has to cost him one tap.
    The row is pinned to his push endpoint and delivers exactly the same way; if
    he ever logs in, /auth/claim-guest walks it over to the account."""
    uid = _user_id(authorization)

    if not VAPID_PUBLIC_KEY:
        raise HTTPException(503, "पुश सूचना अभी उपलब्ध नहीं है।")

    commodity = body.commodity.strip()
    if not commodity:
        raise HTTPException(400, "फसल का नाम चाहिए।")

    # Upsert the device's push subscription (endpoint is unique) and bind it to
    # the account, so later alerts fan out to every phone this farmer uses.
    sub = (db.query(PushSubscription)
             .filter(PushSubscription.endpoint == body.subscription.endpoint)
             .first())
    if sub:
        sub.p256dh     = body.subscription.keys.p256dh
        sub.auth       = body.subscription.keys.auth
        # Only ever ADD an owner here. An anonymous call on a device that is
        # already signed in means the token expired between page load and tap,
        # not that the farmer stopped owning his phone — writing None back would
        # orphan every other alert that fans out through this endpoint.
        if uid is not None:
            sub.user_id = uid
        sub.active     = True
        sub.updated_at = datetime.utcnow()
    else:
        sub = PushSubscription(
            endpoint   = body.subscription.endpoint,
            p256dh     = body.subscription.keys.p256dh,
            auth       = body.subscription.keys.auth,
            user_id    = uid,
            user_agent = (body.user_agent or "")[:300] or None,
        )
        db.add(sub)
    db.flush()   # need sub.id

    state, district = _norm(body.state), _norm(body.district)
    target = (MandiAlert.commodity == commodity,
              MandiAlert.state     == state,
              MandiAlert.district  == district)

    # Reuse this account's existing alert for the crop+mandi if there is one —
    # subscribing again from a second phone must not create a second row, or the
    # farmer gets the same price pushed to him twice.
    alert = (db.query(MandiAlert).filter(MandiAlert.user_id == uid, *target).first()
             if uid is not None else None)
    if alert is None:
        # Otherwise adopt whatever row already occupies this (device, crop, mandi)
        # slot — a legacy pre-login alert (user_id NULL), or one left behind by
        # whoever subscribed from this device before. Not scoped to NULL only:
        # the Push API allows exactly one subscriber per endpoint, so a shared
        # device that changes hands genuinely can't go on alerting its previous
        # owner from here, and scoping to NULL would instead try to INSERT a
        # second row and 500 on the (subscription_id, crop, mandi) unique
        # constraint the first owner's row already holds.
        alert = db.query(MandiAlert).filter(
            MandiAlert.subscription_id == sub.id,
            *target,
        ).first()

    # Rewritten on every subscribe, not just on create — that keeps the copy
    # current for anyone who renamed themselves and toggled the bell since.
    name = display_name(db, uid) if uid is not None else None

    if alert:
        # Same rule as the device above: an anonymous tap re-arms the row it
        # finds, it never un-owns one that already has a farmer behind it.
        if uid is not None:
            alert.user_id   = uid
            alert.user_name = name
        alert.subscription_id = sub.id
        alert.active          = True
        alert.updated_at      = datetime.utcnow()
    else:
        db.add(MandiAlert(subscription_id=sub.id, user_id=uid, user_name=name,
                          commodity=commodity, state=state, district=district))
    db.commit()

    where = district or state or "इस मंडी"
    return {"success": True,
            "message": f"{where} के {commodity} भाव की सूचना चालू। 🔔",
            "data": {"subscribed": True}}


# ── POST /alerts/mandi/off — turn the bell OFF ───────────────

@router.post("/mandi/off")
def mandi_alert_off(
    body:          MandiAlertOff,
    db:            Session       = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """Turn the bell off. Deliberately NOT login-gated: a legacy alert created
    before the gate has no account behind it, and refusing to cancel it would
    leave its owner receiving pushes with no way to stop them. Anonymous callers
    can only switch off alerts that belong to no one (user_id NULL) on their own
    device — never someone else's."""
    target = (MandiAlert.commodity == body.commodity.strip(),
              MandiAlert.state     == _norm(body.state),
              MandiAlert.district  == _norm(body.district))
    stamp = {"active": False, "updated_at": datetime.utcnow()}
    changed = 0

    uid = _user_id(authorization)
    if uid is not None:
        changed = (db.query(MandiAlert)
                     .filter(MandiAlert.user_id == uid, *target)
                     .update(stamp, synchronize_session=False))

    if not changed:
        sub = (db.query(PushSubscription)
                 .filter(PushSubscription.endpoint == body.endpoint)
                 .first())
        if sub:
            (db.query(MandiAlert)
               .filter(MandiAlert.subscription_id == sub.id,
                       MandiAlert.user_id.is_(None),
                       *target)
               .update(stamp, synchronize_session=False))

    db.commit()
    return {"success": True, "message": "सूचना बंद कर दी गई।", "data": {"subscribed": False}}
