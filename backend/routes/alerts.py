# ============================================================
# backend/routes/alerts.py
# KrashiMitra — Mandi price alerts (Web Push)
#
# The 🔔 toggle on a /bhav page subscribes THIS device to that one
# crop+mandi. /bhav pages are anonymous and edge-cached, so a subscription
# is keyed on the browser's push endpoint, not on a login — and the toggle
# state is hydrated client-side (never baked into the cached HTML).
#
#   GET  /alerts/vapid-key      → public key for pushManager.subscribe()
#   GET  /alerts/mandi/status   → is this device subscribed to this mandi?
#   POST /alerts/mandi          → subscribe (upserts the push subscription too)
#   POST /alerts/mandi/off      → unsubscribe
# ============================================================

import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.db import MandiAlert, PushSubscription, get_db

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
    endpoint:  str           = Query(...),
    commodity: str           = Query(...),
    state:     Optional[str] = Query(None),
    district:  Optional[str] = Query(None),
    db:        Session       = Depends(get_db),
):
    sub = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    on = False
    if sub:
        on = db.query(MandiAlert).filter(
            MandiAlert.subscription_id == sub.id,
            MandiAlert.commodity == commodity.strip(),
            MandiAlert.state     == _norm(state),
            MandiAlert.district  == _norm(district),
            MandiAlert.active.is_(True),
        ).first() is not None
    return {"success": True, "message": "", "data": {"subscribed": on}}


# ── POST /alerts/mandi — turn the bell ON ────────────────────

@router.post("/mandi")
def mandi_alert_on(body: MandiAlertOn, db: Session = Depends(get_db)):
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(503, "पुश सूचना अभी उपलब्ध नहीं है।")

    commodity = body.commodity.strip()
    if not commodity:
        raise HTTPException(400, "फसल का नाम चाहिए।")

    # Upsert the device's push subscription (endpoint is unique).
    sub = (db.query(PushSubscription)
             .filter(PushSubscription.endpoint == body.subscription.endpoint)
             .first())
    if sub:
        sub.p256dh     = body.subscription.keys.p256dh
        sub.auth       = body.subscription.keys.auth
        sub.active     = True
        sub.updated_at = datetime.utcnow()
    else:
        sub = PushSubscription(
            endpoint   = body.subscription.endpoint,
            p256dh     = body.subscription.keys.p256dh,
            auth       = body.subscription.keys.auth,
            user_agent = (body.user_agent or "")[:300] or None,
        )
        db.add(sub)
    db.flush()   # need sub.id

    state, district = _norm(body.state), _norm(body.district)
    alert = db.query(MandiAlert).filter(
        MandiAlert.subscription_id == sub.id,
        MandiAlert.commodity == commodity,
        MandiAlert.state     == state,
        MandiAlert.district  == district,
    ).first()
    if alert:
        alert.active     = True
        alert.updated_at = datetime.utcnow()
    else:
        db.add(MandiAlert(subscription_id=sub.id, commodity=commodity,
                          state=state, district=district))
    db.commit()

    where = district or state or "इस मंडी"
    return {"success": True,
            "message": f"{where} के {commodity} भाव की सूचना चालू। 🔔",
            "data": {"subscribed": True}}


# ── POST /alerts/mandi/off — turn the bell OFF ───────────────

@router.post("/mandi/off")
def mandi_alert_off(body: MandiAlertOff, db: Session = Depends(get_db)):
    sub = (db.query(PushSubscription)
             .filter(PushSubscription.endpoint == body.endpoint)
             .first())
    if sub:
        (db.query(MandiAlert)
           .filter(MandiAlert.subscription_id == sub.id,
                   MandiAlert.commodity == body.commodity.strip(),
                   MandiAlert.state     == _norm(body.state),
                   MandiAlert.district  == _norm(body.district))
           .update({"active": False, "updated_at": datetime.utcnow()}))
        db.commit()
    return {"success": True, "message": "सूचना बंद कर दी गई।", "data": {"subscribed": False}}
