# ============================================================
# backend/services/ganna_alerts.py
# कृषि मित्र — "SAP घोषित होते ही बताएं" for the /ganna pages
#
# A state's cane SAP is announced once a year (UP's came on 29 Oct last
# season), and that one day is the /ganna cluster's traffic peak. A farmer who
# turns this bell on in September is a visitor who comes BACK in November —
# exactly the returning audience the site is short of.
#
# It rides the 🔔 mandi-alert rail rather than a table of its own: a
# MandiAlert row with commodity = COMMODITY and state = the /ganna state slug.
# That inherits, unchanged, the consent flow in routes/alerts.py, the signed
# one-tap 🔕 stop on the notification (services/alert_stop.py, LEGAL_RULES §7),
# account claim on login and the ON DELETE CASCADE from users. No new kind of
# personal data — privacy-policy.html already lists push subscriptions and
# "आपकी चुनी हुई फसल / मंडी".
#
# The trigger is ganna_sap.json itself. The rates there are hand-verified from
# the government order (routes/ganna.py explains why that file is not a
# scraper), so the moment someone records the new season's SAP, the next run
# of this job rings every waiting subscriber — nobody has to remember to send
# anything. Each alert rings at most once per season: last_price holds the
# season string it was last told about.
#
# run_mandi_alerts() skips these rows (it has no price to look up for them);
# this module is their only sender. Called from mandi_scheduler after the
# mandi alert pass, so it shares that job's quiet hours and admin kill switch.
# ============================================================

import logging
from datetime import datetime

log = logging.getLogger("krishi.ganna_alerts")

# Reserved commodity key. Not a crop name anyone can type on /bhav, so it can
# never collide with a real mandi alert.
COMMODITY = "ganna-sap"


def _payload(st: dict, season: str, alert_ids: list[int]) -> dict:
    from backend.routes.bhav import SITE
    from backend.services import alert_stop
    rates = " · ".join(f'{r["hi"].replace(" प्रजाति", "")} ₹{r["rate"]:,.0f}'
                       for r in st.get("rates", []))
    payload = {
        "title": f'{st["hi"]} में गन्ने का SAP {season} घोषित',
        "body":  f"{rates} प्रति क्विंटल — पूरा रेट और पेमेंट कैलकुलेटर देखें।",
        "url":   f'{SITE}/ganna/{st["slug"]}',
        "tag":   f'ganna-sap-{st["slug"]}-{season}',
    }
    stop = alert_stop.token(alert_ids)
    if stop:
        payload["stop"] = stop
    return payload


def due(alerts, states: dict, season: str):
    """Pure selection, kept separate so it can be tested without a database.

    Yields (alert, state) for every alert whose state has now declared its SAP
    for `season` and that has not already been told about that season."""
    for a in alerts:
        st = states.get(a.state or "")
        if not st or st.get("kind") != "sap" or not st.get("rates"):
            continue
        if st.get("season") != season:        # still the old season's number
            continue
        if (a.last_price or "") == season:    # already rung for this season
            continue
        yield a, st


def run_ganna_alerts() -> dict:
    from backend.database.db import MandiAlert, SessionLocal
    from backend.routes import ganna
    from backend.services import push_service as ps
    from backend.services.app_settings import get_all

    if not ps.push_enabled():
        return {"sent": 0, "enabled": False}
    if not get_all()["alerts.sending_enabled"]:
        return {"sent": 0, "deferred": "admin_off"}
    now_ist = ps._now_ist()
    if ps._in_quiet_hours(now_ist):
        return {"sent": 0, "deferred": "quiet_hours"}

    season, _frp = ganna.current_season(now_ist.date())
    states = {s["slug"]: s for s in ganna._states()}
    sent = failed = 0
    db = SessionLocal()
    try:
        alerts = (db.query(MandiAlert)
                    .filter(MandiAlert.active.is_(True),
                            MandiAlert.commodity == COMMODITY)
                    .all())
        for alert, st in list(due(alerts, states, season)):
            devices = ps._devices_for(db, alert)
            ok = False
            payload = _payload(st, season, [alert.id])
            for device in devices:
                if ps.send_push(db, device, payload):
                    ok = True
            if ok:
                alert.last_price = season
                alert.last_notified_on = now_ist.date()
                alert.updated_at = datetime.utcnow()
                sent += 1
            elif devices:
                failed += 1
        db.commit()
        if sent or failed:
            log.info("🔔 ganna SAP alerts — sent %s | failed %s", sent, failed)
        return {"sent": sent, "failed": failed}
    except Exception as e:
        db.rollback()
        log.error("ganna SAP alert pass failed: %s", e)
        return {"sent": sent, "error": str(e)}
    finally:
        db.close()
