"""The ईमेल / OTP health card must report delivery, not configuration.

Signups stall at the OTP screen every so often, and the old check could not
see it: it asserted that RESEND_API_KEY was a non-empty string and printed
"OTP मेल जा रहे हैं". A revoked key, an unverified sending domain and an
exhausted quota all leave that variable exactly as it was, so the card stayed
green through every one of them.

Two things fixed that, and both are guarded here: auth_utils now records the
outcome of every real send in `sync_log`, and the check probes Resend to see
whether the key still authenticates. The probe classification is the delicate
half — the production key is a *send-only* key, which Resend answers with a
401, and reading that as a failure would paint the card red on a setup that
works perfectly.

Nothing here touches the network: _classify_resend is pure, and the tests that
exercise the card stub the probe out.
"""

from datetime import datetime, timedelta

import pytest

from backend.services import health_service as hs


# ── the probe's verdicts ─────────────────────────────────────

class TestResendClassification:
    def test_send_only_key_is_live_not_broken(self):
        """The key this site actually runs on.

        Resend authenticates a restricted key and then refuses the scope. That
        refusal proves the key is live; treating the 401 as a failure would
        report every healthy deploy as down.
        """
        verdict = hs._classify_resend(401, {
            "statusCode": 401,
            "name": "restricted_api_key",
            "message": "This API key is restricted to only send emails",
        })
        assert verdict["state"] == "live"

    @pytest.mark.parametrize("status", [400, 401])
    def test_revoked_key_is_dead(self, status):
        """The silent killer: the variable is still set, the key is not."""
        verdict = hs._classify_resend(status, {
            "statusCode": status,
            "name": "validation_error",
            "message": "API key is invalid",
        })
        assert verdict["state"] == "dead"
        assert "API key is invalid" in verdict["note"]

    def test_full_access_key_reports_the_sending_domain(self):
        verdict = hs._classify_resend(
            200, {"data": [{"name": "krashimitra.in", "status": "verified"}]},
            "OTP@krashimitra.in")
        assert verdict["state"] == "live"
        assert "verified" in verdict["domain"]

    def test_unverified_sending_domain_is_called_out(self):
        """Resend accepts the key and then refuses to deliver — a failure mode
        no amount of checking the environment could ever see."""
        verdict = hs._classify_resend(
            200, {"data": [{"name": "krashimitra.in", "status": "pending"}]},
            "OTP@krashimitra.in")
        assert verdict["state"] == "domain_unverified"

    @pytest.mark.parametrize("status,body", [
        (429, {"name": "rate_limit_exceeded", "message": "Too many requests"}),
        (500, {}),
        (503, {"message": "upstream unavailable"}),
    ])
    def test_transient_failures_never_read_as_dead(self, status, body):
        """Resend being briefly unreachable from this box says nothing about
        whether OTPs are going out, so it must never colour the card red."""
        assert hs._classify_resend(status, body)["state"] == "unknown"


# ── the card ─────────────────────────────────────────────────

@pytest.fixture()
def mail_log(db_session):
    """Write sync_log rows the way auth_utils._record_mail does, and clear
    both the row set and the memoised probe around every test."""
    from backend.database.db import SyncLog
    from backend.utils.auth_utils import MAIL_LOG_SOURCE

    def _clear():
        db_session.query(SyncLog).filter(SyncLog.source == MAIL_LOG_SOURCE).delete()
        db_session.commit()

    def _add(status, detail="resend", minutes_ago=1):
        db_session.add(SyncLog(
            source=MAIL_LOG_SOURCE, status=status, rows=1 if status == "success" else 0,
            detail=detail,
            finished_at=datetime.utcnow() - timedelta(minutes=minutes_ago)))
        db_session.commit()

    _clear()
    hs._resend_probe_cache = None
    yield _add
    _clear()
    hs._resend_probe_cache = None


@pytest.fixture()
def live_resend(monkeypatch):
    """Configured, key authenticates — the healthy baseline. Also the guard
    that keeps this file off the network."""
    monkeypatch.setattr("backend.utils.auth_utils.RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr("backend.utils.auth_utils.RESEND_FROM_EMAIL", "OTP@krashimitra.in")
    monkeypatch.setattr("backend.utils.auth_utils.SMTP_EMAIL", "")
    monkeypatch.setattr("backend.utils.auth_utils.SMTP_PASSWORD", "")
    monkeypatch.setattr(hs, "_resend_probe",
                        lambda: {"state": "live", "note": "ok", "domain": None})


class TestEmailCard:
    def test_a_failed_last_send_takes_the_card_down(self, db_session, mail_log, live_resend):
        """The whole point. Every key is set, the connection is fine, and mail
        is still not arriving — only the send record can show that."""
        mail_log("failed", "resend · HTTP 403 — domain is not verified")
        card = hs._chk_email(db_session, detailed=False)
        assert card["status"] == "down"

    def test_a_later_success_clears_an_earlier_failure(self, db_session, mail_log, live_resend):
        mail_log("failed", minutes_ago=90)
        mail_log("success", minutes_ago=2)
        card = hs._chk_email(db_session, detailed=False)
        assert card["status"] == "warn", "recent failures are still worth saying out loud"

    def test_clean_recent_sends_are_ok(self, db_session, mail_log, live_resend):
        mail_log("success", minutes_ago=5)
        assert hs._chk_email(db_session, detailed=False)["status"] == "ok"

    def test_old_failures_age_out(self, db_session, mail_log, live_resend):
        mail_log("failed", minutes_ago=60 * 40)
        mail_log("success", minutes_ago=3)
        assert hs._chk_email(db_session, detailed=False)["status"] == "ok"

    def test_dead_key_is_down_before_anyone_tries_to_sign_up(
            self, db_session, mail_log, monkeypatch, live_resend):
        """No failed send has been recorded yet — the next farmer would have
        been the one to discover it. The probe gets there first."""
        monkeypatch.setattr(hs, "_resend_probe",
                            lambda: {"state": "dead", "note": "API key is invalid",
                                     "domain": None})
        assert hs._chk_email(db_session, detailed=False)["status"] == "down"

    def test_dead_key_with_smtp_left_is_only_a_warning(
            self, db_session, mail_log, monkeypatch, live_resend):
        monkeypatch.setattr("backend.utils.auth_utils.SMTP_EMAIL", "bot@example.com")
        monkeypatch.setattr("backend.utils.auth_utils.SMTP_PASSWORD", "app-password")
        monkeypatch.setattr(hs, "_resend_probe",
                            lambda: {"state": "dead", "note": "API key is invalid",
                                     "domain": None})
        assert hs._chk_email(db_session, detailed=False)["status"] == "warn"

    def test_no_mail_route_at_all_is_down(self, db_session, mail_log, monkeypatch):
        for name in ("RESEND_API_KEY", "RESEND_FROM_EMAIL", "SMTP_EMAIL", "SMTP_PASSWORD"):
            monkeypatch.setattr(f"backend.utils.auth_utils.{name}", "")
        assert hs._chk_email(db_session, detailed=False)["status"] == "down"

    def test_public_card_withholds_the_send_volume(self, db_session, mail_log, live_resend):
        """Signup volume is a business number; the file's rule keeps those
        behind the admin password."""
        mail_log("success", minutes_ago=5)
        assert hs._chk_email(db_session, detailed=False)["facts"] == []
        labels = [f[0] for f in hs._chk_email(db_session, detailed=True)["facts"]]
        assert "कनेक्शन" in labels and "24 घंटे में" in labels


class TestSendsAreRecorded:
    def test_a_resend_failure_writes_the_reason(self, monkeypatch):
        """auth_utils must keep the Resend `message` — "domain is not verified"
        is the whole diagnosis, and Render's log is gone by the time anybody
        looks."""
        from backend.utils import auth_utils

        recorded = {}
        monkeypatch.setattr(auth_utils, "_record_mail",
                            lambda p, ok, reason="": recorded.update(
                                provider=p, ok=ok, reason=reason))
        monkeypatch.setattr(auth_utils, "RESEND_API_KEY", "re_test_key")
        monkeypatch.setattr(auth_utils, "RESEND_FROM_EMAIL", "OTP@krashimitra.in")

        class _Resp:
            status_code = 403
            text = '{"message":"The krashimitra.in domain is not verified."}'

            def json(self):
                return {"statusCode": 403, "name": "validation_error",
                        "message": "The krashimitra.in domain is not verified."}

        monkeypatch.setattr(auth_utils.httpx, "post", lambda *a, **k: _Resp())
        assert auth_utils._send_with_resend("x@example.com", "s", "b") is False
        assert recorded["ok"] is False
        assert "domain is not verified" in recorded["reason"]

    def test_a_successful_send_is_recorded_without_the_recipient(self, monkeypatch):
        """The row must never carry the farmer's address."""
        from backend.utils import auth_utils

        recorded = {}
        monkeypatch.setattr(auth_utils, "_record_mail",
                            lambda p, ok, reason="": recorded.update(
                                provider=p, ok=ok, reason=reason))
        monkeypatch.setattr(auth_utils, "RESEND_API_KEY", "re_test_key")
        monkeypatch.setattr(auth_utils, "RESEND_FROM_EMAIL", "OTP@krashimitra.in")

        class _Resp:
            status_code = 200
            text = "{}"

            def json(self):
                return {"id": "abc"}

        monkeypatch.setattr(auth_utils.httpx, "post", lambda *a, **k: _Resp())
        assert auth_utils._send_with_resend("farmer@example.com", "s", "b") is True
        assert recorded == {"provider": "resend", "ok": True, "reason": ""}
