# ============================================================
# backend/services/push_service.py
# KrashiMitra — Web Push sender + mandi-alert evaluation pass
#
# Runs right after each mandi fetch sweep: every active 🔔 alert is compared
# against the freshly-merged price for its crop+mandi and pushed at most once
# a day, never between 11:30pm-4am IST, and only when the price moved by more
# than sample noise (last_notified_on + MIN_MOVE dedupe) — a farmer should
# never get the same number twice, buzzed at 2am, or notified over a ₹1
# rounding wobble.
#
# Fully degrades to a no-op when VAPID keys aren't configured, and prunes
# subscriptions the push service reports as gone (404/410).
# ============================================================

import json
import logging
import os
from datetime import date, datetime, timedelta

from sqlalchemy import func

from backend.database.db import MandiAlert, MandiPrice, PushSubscription, SessionLocal

log = logging.getLogger("krishi.push")

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
VAPID_PUBLIC_KEY  = os.getenv("VAPID_PUBLIC_KEY", "").strip()
VAPID_SUBJECT     = os.getenv("VAPID_SUBJECT", "mailto:krashimitra038@gmail.com").strip()

SITE = "https://krashimitra.in"

# No push between 11:30pm and 4am IST — narrow enough that the 23:11 final
# sweep can still push normally, only the dead-of-night stretch after it is
# silenced. A price that would have fired in that window simply waits for the
# 08:00 run instead: last_notified_on for today is still unset, so nothing is lost.
QUIET_START_MIN_IST = 23 * 60 + 30   # 23:30
QUIET_END_MIN_IST   = 4  * 60        # 04:00

# A push is only worth interrupting someone's day for if the price actually
# moved, not if a partially-reported feed rounded differently than last time.
# data.gov fills in through the day (2 rows at 06:30 → ~18k by evening, see
# mandi_scheduler.py), so the average can drift a rupee or two from sample
# noise alone between two runs on the same day. Require the move to clear
# BOTH a flat floor and a relative floor — small prices (₹50 onion) shouldn't
# need a ₹50 swing, and large ones (₹3000 wheat) shouldn't fire on ₹10 noise.
MIN_MOVE_RS  = 10
MIN_MOVE_PCT = 1.0


def push_enabled() -> bool:
    """Can this deployment send a push at all?

    Both VAPID keys are required: the public one identifies us to the push
    service, the private one signs. One without the other silently fails at
    send time, which is worse than not trying.

    This function was deleted by 1c175c5 (2026-07-27) while both of its call
    sites stayed, so run_mandi_alerts() raised NameError on its first line and
    mandi_scheduler's `except Exception` logged it as non-fatal. 74 farmers
    subscribed over the following 57 days and not one push was ever sent —
    every mandi_alerts row still had last_notified_on NULL. tests/
    test_push_alerts.py::test_alert_pass_runs now fails if it goes missing
    again."""
    return bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)


def _now_ist():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)


def _in_quiet_hours(now_ist) -> bool:
    mins = now_ist.hour * 60 + now_ist.minute
    return mins >= QUIET_START_MIN_IST or mins < QUIET_END_MIN_IST


def _is_meaningful_move(avg: int, last_price: str,
                        min_rs: float = MIN_MOVE_RS,
                        min_pct: float = MIN_MOVE_PCT) -> bool:
    """False if this is the same price already sent, or a move too small to be
    worth a notification. True (send) when there is no prior price at all —
    the first alert for a newly-subscribed crop is never noise.

    The floors are passed in because the admin panel can retune them without a
    deploy; the module constants remain the defaults."""
    last = _num(last_price)
    if last is None:
        return True
    moved = abs(avg - last)
    if moved == 0:
        return False
    return moved >= min_rs or (moved / last) * 100 >= min_pct


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


def _devices_for(db, alert: MandiAlert):
    """Every live push endpoint an alert should be delivered to.

    Account alerts fan out across all of the farmer's signed-in devices, which
    is what makes a 🔔 survive a new phone. Alerts predating the login gate have
    no account, so they stay pinned to the endpoint that created them."""
    if alert.user_id is not None:
        return (db.query(PushSubscription)
                  .filter(PushSubscription.user_id == alert.user_id,
                          PushSubscription.active.is_(True))
                  .all())
    return (db.query(PushSubscription)
              .filter(PushSubscription.id == alert.subscription_id,
                      PushSubscription.active.is_(True))
              .all())


def _price_for(db, commodity: str, state, district):
    """Average modal price + day-on-day move for a crop in one district —
    the same figure the /bhav page leads with.

    func.lower(col) == value.lower(), NOT .ilike(value) — this runs once per
    active alert on every fetch cycle, and mandi_prices_csd_lower_idx (db.py)
    only matches a literal `lower(col) = ...` clause, never an ILIKE predicate
    even without wildcards. Written as .ilike(), this was a full table scan of
    mandi_prices per alert. Same fix as _rows_for() in routes/bhav.py and
    get_mandi_prices() in mandi_service.py."""
    q = db.query(MandiPrice).filter(func.lower(MandiPrice.commodity) == commodity.lower())
    if state:
        q = q.filter(func.lower(MandiPrice.state) == state.lower())
    if district:
        q = q.filter(func.lower(MandiPrice.district) == district.lower())
    rows = q.all()
    modals = [m for m in (_num(r.modal_price) for r in rows) if m]
    if not modals:
        return None, None, 0, ""
    avg = round(sum(modals) / len(modals))
    changes = [r.change_pct for r in rows if r.change_pct is not None]
    change = round(sum(changes) / len(changes), 1) if changes else None
    return avg, change, len(rows), _newest_iso(rows)


def _newest_iso(rows) -> str:
    """The newest arrival_date among these rows as 'YYYY-MM-DD', or ''.

    Roughly half of all mandi×crop pairs get no fresh report on any given day
    (see the /bhav staleness audit) and the snapshot carries the last known
    price forward, so the row being present says nothing about when the market
    actually traded. Everything that wants to say "आज" has to check this
    first."""
    from backend.routes.bhav import _row_date_iso     # lazy: avoids import cycle
    best = ""
    for r in rows:
        iso = _row_date_iso(r.arrival_date or "")
        if iso > best:
            best = iso
    return best


def _describe(alert: MandiAlert):
    """(hindi crop name, place label, this alert's /bhav url).

    The place is translated, not passed through raw. The feed names districts in
    English, so an untranslated label produced "आज Bijnor में गेहूं के भाव" —
    a notification in two scripts, which is the same defect that makes a
    wrong-script SERP title convert far worse. Both helpers fall back to the
    English name when they have no mapping, which is still better than nothing."""
    from backend.routes.bhav import (           # lazy: avoids import cycle
        _hindi_district, _hindi_name, _hindi_state, _slugify)

    hi = _hindi_name(alert.commodity) or alert.commodity
    if alert.district:
        where = _hindi_district(alert.state or "", alert.district) or alert.district
    elif alert.state:
        where = _hindi_state(alert.state) or alert.state
    else:
        where = ""
    url = f"{SITE}/bhav/{_slugify(alert.commodity)}"
    if alert.state:
        url += f"/{_slugify(alert.state)}"
        if alert.district:
            url += f"/{_slugify(alert.district)}"
    return hi, where, url


def _move_text(change, delta_rs):
    """'2.3% से बढ़े' / '₹200 से घटे' — the % is the source feed's own
    day-on-day change_pct when it reported one; the rupee figure is this
    alert's move since it was last notified (avg vs last_price), used
    whenever change_pct is missing (thin early-day data — see mandi_scheduler
    .py's fill-through-the-day comment). None when there is nothing to
    compare against yet (first notification for a brand-new subscribe)."""
    if change:
        return f"{abs(change):g}% से {'बढ़े' if change > 0 else 'घटे'}"
    if delta_rs:
        return f"₹{abs(round(delta_rs)):,} से {'बढ़े' if delta_rs > 0 else 'घटे'}"
    return None


def _when_word(data_iso: str, today) -> str:
    """"आज" / "कल" / "18 सितंबर" — the day this price was actually reported.

    Never say "आज" over a carried-forward number. About half of all mandi×crop
    pairs get no fresh report on a given day, so a notification that opens with
    "आज" when the last real trade was a week ago tells the farmer something
    false about his market, on his lock screen, in our name. An empty or
    unparseable date drops the time word entirely rather than guessing.

    Placement is the caller's job: "आज"/"कल" read naturally in front of the
    sentence, a date does not ("19 सितंबर का वाराणसी में…"), so a dated price
    is labelled at the end instead."""
    if not _iso_ok(data_iso):
        return ""
    from backend.routes.bhav import _hindi_data_date
    d = date.fromisoformat(data_iso)
    delta = (today - d).days
    if delta == 0:
        return "आज"
    if delta == 1:
        return "कल"
    return _hindi_data_date(f"{d.day:02d}/{d.month:02d}/{d.year}")


def _iso_ok(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except (TypeError, ValueError):
        return False


def _payload_for_group(items, today):
    """One push payload for everything due for a single recipient this run.

    items: [(alert, avg, change, data_iso), ...]. A farmer with several 🔔s can have
    several move on the same fetch — sending one notification per alert would
    read as a burst/spam, so 2+ due alerts for the same recipient are folded
    into a single digest instead. The common case (one alert due) keeps the
    original single-crop copy, since that is more specific than a 1-item digest.

    The body leads with the MOVE, not the absolute price — "आज गेहूं के भाव
    2.3% से बढ़े", not "₹2,150/क्विंटल". A subscriber already knows roughly
    what the crop sells for; what earns a notification is that it moved, and
    by how much. The absolute number is one tap away on the /bhav page."""
    if len(items) == 1:
        alert, avg, change, data_iso = items[0]
        hi, where, url = _describe(alert)
        delta_rs = None
        last = _num(alert.last_price)
        if last is not None:
            delta_rs = avg - last
        place = f"{where} में " if where else ""
        when  = _when_word(data_iso, today)
        lead  = f"{when} " if when in ("आज", "कल") else ""
        tail  = f" — {when} का भाव" if when and not lead else ""
        move  = _move_text(change, delta_rs)
        body = (f"{lead}{place}{hi} के भाव {move}{tail}" if move
                else f"{lead}{place}{hi} का भाव ₹{avg:,}/क्विंटल है{tail}")
        return {
            "title": f"{hi} भाव — {where}".strip(" —"),
            "body":  body,
            "url":   url,
            "tag":   f"bhav-{alert.id}",
        }

    # Biggest mover first — both as the headline line and the click-through
    # target, since that is the one most worth a look. Capped at 4 lines so
    # the notification stays readable instead of turning into a wall of text.
    ranked = sorted(items, key=lambda t: abs(t[2] or 0), reverse=True)
    lines, url = [], None
    for alert, avg, change, data_iso in ranked[:4]:
        hi, where, u = _describe(alert)
        last = _num(alert.last_price)
        delta_rs = (avg - last) if last is not None else None
        move  = _move_text(change, delta_rs) or f"₹{avg:,}/क्विंटल"
        # Each line carries its own date when that line is not today's — the
        # rows in one digest can easily come from different report days.
        when  = _when_word(data_iso, today)
        if when and when != "आज":
            move = f"{move} ({when})"
        label = f"{hi} ({where})" if where else hi
        lines.append(f"{label}: {move}")
        if url is None:
            url = u
    if len(ranked) > 4:
        lines.append(f"+{len(ranked) - 4} और भाव अपडेट")

    first = items[0][0]
    recipient = first.user_id if first.user_id is not None else first.subscription_id
    return {
        "title": f"{len(items)} फसलों के भाव बदले 🔔",
        "body":  "\n".join(lines),
        "url":   url,
        "tag":   f"bhav-digest-{recipient}",
    }


def run_mandi_alerts() -> dict:
    """Evaluate every active 🔔 mandi alert and push the ones whose price moved."""
    if not push_enabled():
        log.info("push: VAPID not configured — skipping alert pass")
        return {"sent": 0, "skipped": 0, "enabled": False}

    # Operator kill switch. Like quiet hours this touches no alert row, so
    # switching sending back on resumes from exactly where it stopped rather
    # than replaying a backlog of prices that are no longer today's.
    from backend.services.app_settings import get_all
    cfg = get_all()
    if not cfg["alerts.sending_enabled"]:
        log.info("push: sending switched off in admin — skipping alert pass")
        return {"sent": 0, "skipped": 0, "enabled": True, "deferred": "admin_off"}

    now_ist = _now_ist()
    if _in_quiet_hours(now_ist):
        # Don't send, but don't touch any alert either — leaving last_notified_on
        # unset for today means the 08:00 run picks up right where this left off.
        log.info("push: quiet hours (%02d:%02d IST) — deferring to the next daytime run", now_ist.hour, now_ist.minute)
        return {"sent": 0, "skipped": 0, "enabled": True, "deferred": "quiet_hours"}

    today = now_ist.date()
    sent = skipped = failed = 0
    db = SessionLocal()
    try:
        alerts = (db.query(MandiAlert)
                    .filter(MandiAlert.active.is_(True))
                    .all())

        # Pass 1 — find what's due, grouped by recipient (account, or device
        # for pre-login legacy alerts) so several crops moving the same day
        # reach a farmer as ONE notification instead of one push per alert.
        groups, devices_by_key = {}, {}
        for alert in alerts:
            if alert.last_notified_on == today:      # at most one push a day
                skipped += 1
                continue

            # Where to send. An account alert goes to every phone the farmer has
            # signed in on — that is the whole point of tying alerts to a login
            # rather than a browser. Legacy alerts (user_id NULL, created before
            # the gate) still go to the single device that created them.
            devices = _devices_for(db, alert)
            if not devices:
                skipped += 1
                continue

            avg, change, n, data_iso = _price_for(db, alert.commodity,
                                                  alert.state, alert.district)
            if not avg:
                skipped += 1
                continue

            if not _is_meaningful_move(avg, alert.last_price,
                                       cfg["alerts.min_move_rs"],
                                       cfg["alerts.min_move_pct"]):
                skipped += 1
                continue

            key = ("user", alert.user_id) if alert.user_id is not None else ("device", alert.subscription_id)
            groups.setdefault(key, []).append((alert, avg, change, data_iso))
            devices_by_key[key] = devices

        # Pass 2 — one push per recipient, covering everything of theirs due this run.
        for key, items in groups.items():
            payload = _payload_for_group(items, today)
            # One device accepting is enough to call the alert delivered — a
            # farmer's old tablet being unreachable must not make him miss the
            # price on the phone in his hand tomorrow.
            ok = False
            for device in devices_by_key[key]:
                if send_push(db, device, payload):
                    ok = True
            for alert, avg, change, _iso in items:
                if ok:
                    alert.last_notified_on = today
                    alert.last_price = str(avg)
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
    log.info(run_mandi_alerts())
