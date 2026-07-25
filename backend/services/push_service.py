# ============================================================
# backend/services/push_service.py
# KrashiMitra — Web Push sender + mandi-alert evaluation pass
#
# Runs right after each mandi fetch sweep: every active 🔔 alert is compared
# against the freshly-merged price for its crop+mandi and pushed at most once
# a day, and only when the price actually moved (last_notified_on + last_price
# dedupe) — a farmer should never get the same number twice.
#
# Fully degrades to a no-op when VAPID keys aren't configured, and prunes
# subscriptions the push service reports as gone (404/410).
# ============================================================

import json
import logging
import os
from datetime import datetime, timedelta

from backend.database.db import MandiAlert, MandiPrice, PushSubscription, SessionLocal

log = logging.getLogger("krishi.push")

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
VAPID_PUBLIC_KEY  = os.getenv("VAPID_PUBLIC_KEY", "").strip()
VAPID_SUBJECT     = os.getenv("VAPID_SUBJECT", "mailto:krdhmp13@gmail.com").strip()

SITE = "https://krashimitra.in"


def push_enabled() -> bool:
    return bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)


def _today_ist():
    return (datetime.utcnow() + timedelta(hours=5, minutes=30)).date()


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def send_push(db, sub: PushSubscription, payload: dict) -> bool:
    """One push. Marks the subscription inactive when the push service says the
    endpoint is gone, so dead devices stop being retried forever."""
    if not push_enabled():
        return False
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        log.warning("pywebpush not installed — push disabled")
        return False

    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_SUBJECT},
            timeout=10,
        )
        return True
    except WebPushException as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code in (404, 410):                     # endpoint permanently gone
            sub.active = False
            sub.updated_at = datetime.utcnow()
            log.info("push: pruned dead endpoint (%s)", code)
        else:
            log.warning("push failed (%s): %s", code, e)
        return False
    except Exception as e:                          # never let one device break the sweep
        log.warning("push error: %s", e)
        return False


def _price_for(db, commodity: str, state, district):
    """Average modal price + day-on-day move for a crop in one district —
    the same figure the /bhav page leads with."""
    q = db.query(MandiPrice).filter(MandiPrice.commodity.ilike(commodity))
    if state:
        q = q.filter(MandiPrice.state.ilike(state))
    if district:
        q = q.filter(MandiPrice.district.ilike(district))
    rows = q.all()
    modals = [m for m in (_num(r.modal_price) for r in rows) if m]
    if not modals:
        return None, None, 0
    avg = round(sum(modals) / len(modals))
    changes = [r.change_pct for r in rows if r.change_pct is not None]
    change = round(sum(changes) / len(changes), 1) if changes else None
    return avg, change, len(rows)


def run_mandi_alerts() -> dict:
    """Evaluate every active 🔔 mandi alert and push the ones whose price moved."""
    if not push_enabled():
        log.info("push: VAPID not configured — skipping alert pass")
        return {"sent": 0, "skipped": 0, "enabled": False}

    from backend.routes.bhav import _hindi_name, _slugify   # lazy: avoids import cycle

    today = _today_ist()
    sent = skipped = failed = 0
    db = SessionLocal()
    try:
        pairs = (db.query(MandiAlert, PushSubscription)
                   .join(PushSubscription, PushSubscription.id == MandiAlert.subscription_id)
                   .filter(MandiAlert.active.is_(True), PushSubscription.active.is_(True))
                   .all())

        for alert, sub in pairs:
            if alert.last_notified_on == today:      # at most one push a day
                skipped += 1
                continue

            avg, change, n = _price_for(db, alert.commodity, alert.state, alert.district)
            if not avg:
                skipped += 1
                continue

            price_str = str(avg)
            if alert.last_price == price_str:        # unchanged since last push
                skipped += 1
                continue

            hi    = _hindi_name(alert.commodity) or alert.commodity
            where = alert.district or alert.state or ""
            move  = f" · कल से {change:+g}%" if change else ""
            url   = f"{SITE}/bhav/{_slugify(alert.commodity)}"
            if alert.state:
                url += f"/{_slugify(alert.state)}"
                if alert.district:
                    url += f"/{_slugify(alert.district)}"

            ok = send_push(db, sub, {
                "title": f"{hi} भाव — {where}".strip(" —"),
                "body":  f"₹{avg:,}/क्विंटल{move}",
                "url":   url,
                "tag":   f"bhav-{alert.id}",
            })
            if ok:
                alert.last_notified_on = today
                alert.last_price = price_str
                alert.updated_at = datetime.utcnow()
                sent += 1
            else:
                failed += 1

        db.commit()
        log.info("🔔 mandi alerts — sent %s | skipped %s | failed %s", sent, skipped, failed)
        return {"sent": sent, "skipped": skipped, "failed": failed, "enabled": True}
    except Exception as e:
        db.rollback()
        log.error("mandi alert pass failed: %s", e)
        return {"sent": sent, "skipped": skipped, "error": str(e), "enabled": True}
    finally:
        db.close()


if __name__ == "__main__":       # manual run: python -m backend.services.push_service
    logging.basicConfig(level=logging.INFO)
    print(run_mandi_alerts())
