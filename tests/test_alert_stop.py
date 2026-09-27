"""The "🔕 बंद करें" button on a भाव अलर्ट notification (LEGAL_RULES §7).

The service worker cannot see the farmer's login, so each push carries a
signed token naming the alerts it reports on, and POST /alerts/mandi/stop
switches off those and only those. A forged or edited token must do nothing.
"""

from pathlib import Path

import pytest

from backend.services import alert_stop

REPO = Path(__file__).resolve().parents[1]


class TestToken:
    def test_round_trip(self):
        tok = alert_stop.token([40, 12, 12])
        assert alert_stop.ids_from(tok) == [12, 40]

    def test_edited_ids_are_refused(self):
        tok = alert_stop.token([12])
        body, sig = tok.split(".")
        assert alert_stop.ids_from(f"13.{sig}") is None
        assert alert_stop.ids_from(f"12,13.{sig}") is None

    def test_garbage_is_refused(self):
        for bad in ("", "12", "12.", ".abc", "a,b.c", None):
            assert alert_stop.ids_from(bad) is None

    def test_no_real_secret_means_no_token(self, monkeypatch):
        """The public repo default must never sign anything: anyone could
        forge a token with it."""
        monkeypatch.setenv("JWT_SECRET", "change_this_secret_in_production")
        assert alert_stop.token([1]) is None
        monkeypatch.setenv("JWT_SECRET", "")
        assert alert_stop.token([1]) is None


class TestPayload:
    def test_push_carries_a_stop_token_for_its_own_alerts(self):
        from datetime import date
        from backend.services import push_service as ps

        class _A:
            id, commodity, state, district = 77, "Wheat", "Uttar Pradesh", "Agra"
            last_price, user_id, subscription_id = None, None, 5

        payload = ps._payload_for_group([(_A(), 2500, 1.2, "2026-09-28")], date(2026, 9, 28))
        assert alert_stop.ids_from(payload["stop"]) == [77]


@pytest.fixture()
def alerts(db_session):
    from backend.database.db import MandiAlert, PushSubscription
    sub = PushSubscription(endpoint="https://push.example/alert-stop-test", p256dh="k", auth="a")
    db_session.add(sub)
    db_session.commit()
    rows = [MandiAlert(subscription_id=sub.id, commodity="Wheat", state="Uttar Pradesh",
                       district=f"Stoppur{i}", active=True) for i in range(3)]
    db_session.add_all(rows)
    db_session.commit()
    yield rows
    for r in rows:
        db_session.delete(r)
    db_session.delete(sub)
    db_session.commit()


class TestEndpoint:
    def test_stops_only_the_named_alerts(self, client, alerts, db_session):
        tok = alert_stop.token([alerts[0].id, alerts[1].id])
        r = client.post("/alerts/mandi/stop", json={"t": tok})
        assert r.status_code == 200
        for a in alerts:
            db_session.refresh(a)
        assert [a.active for a in alerts] == [False, False, True]

    def test_forged_token_changes_nothing(self, client, alerts, db_session):
        r = client.post("/alerts/mandi/stop", json={"t": f"{alerts[2].id}.forged"})
        assert r.status_code == 400
        db_session.refresh(alerts[2])
        assert alerts[2].active is True


def test_service_worker_offers_the_button():
    sw = (REPO / "frontend" / "sw.js").read_text(encoding="utf-8")
    assert "action: 'stop'" in sw and "/alerts/mandi/stop" in sw
