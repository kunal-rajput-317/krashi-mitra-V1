"""The free-tier panel has to work without anyone opening it.

`/admin/infra` was built on 17 Aug 2026 after the third quota outage, and then
went unread — which is the failure mode of every dashboard you have to open.
Nothing called infra_service outside the admin route, so the check only ran
when someone happened to look. These tests pin the three things that changed:
the probe is scheduled, it stays quiet on a normal day, and it speaks when a
meter is genuinely about to run out.

Also pinned: Netlify is no longer polled. It was retired on 16 Sep 2026 when
Cloudflare DNS moved to Render as the single origin, and a card that can only
say "set NETLIFY_AUTH_TOKEN" for a service we do not use is noise.
"""

import pytest

from backend.services import infra_service as infra


def _payload(status="ok", at_risk=()):
    return {"verdict": {"status": status, "headline": "h", "sub": "s",
                        "at_risk": list(at_risk)}, "providers": []}


def _risk(days, provider="Neon", meter="Compute", pct=88.0):
    return {"provider": provider, "meter": meter, "days_left": days, "pct": pct}


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    """No real probes, no real mail."""
    sent = []
    monkeypatch.setattr(infra, "_mail", lambda subj, body: sent.append((subj, body)))
    monkeypatch.setattr(infra, "_last_alert", "")
    return sent


class TestNetlifyIsNoLongerPolled:
    def test_probe_list_has_only_render_and_neon(self):
        keys = [k for k, _fn in infra._PROBES]
        assert "netlify" not in keys, (
            "Netlify was retired on 16 Sep 2026 — polling it puts a permanently "
            "unconfigured card on a page whose job is to be scanned quickly")
        assert keys == ["render", "neon"] or set(keys) == {"render", "neon"}, keys


class TestItStaysQuietOnANormalDay:
    def test_no_mail_when_nothing_is_running_out(self, monkeypatch, _quiet):
        monkeypatch.setattr(infra, "run", lambda use_cache=True: _payload())
        infra.run_check()
        assert _quiet == [], "an alert fired on a healthy day — that is how alerts get ignored"

    def test_a_distant_runway_is_not_an_alert(self, monkeypatch, _quiet):
        far = infra.ALERT_DAYS_LEFT + 30
        monkeypatch.setattr(infra, "run", lambda use_cache=True: _payload(at_risk=[_risk(far)]))
        infra.run_check()
        assert _quiet == [], f"{far:.0f} days of runway is not worth an email"


class TestItSpeaksWhenItMatters:
    def test_a_near_exhausted_meter_mails(self, monkeypatch, _quiet):
        near = max(1.0, infra.ALERT_DAYS_LEFT - 1)
        monkeypatch.setattr(infra, "run", lambda use_cache=True: _payload(at_risk=[_risk(near)]))
        infra.run_check()
        assert len(_quiet) == 1, "a meter about to run out sent nothing"
        assert "Neon" in _quiet[0][1] and "Compute" in _quiet[0][1]

    def test_a_service_already_down_mails_even_with_no_meter(self, monkeypatch, _quiet):
        monkeypatch.setattr(infra, "run", lambda use_cache=True: _payload(status="down"))
        infra.run_check()
        assert len(_quiet) == 1, "a provider reported down but nobody was told"

    def test_a_standing_problem_mails_once_not_daily(self, monkeypatch, _quiet):
        near = max(1.0, infra.ALERT_DAYS_LEFT - 1)
        monkeypatch.setattr(infra, "run", lambda use_cache=True: _payload(at_risk=[_risk(near)]))
        infra.run_check()
        infra.run_check()
        infra.run_check()
        assert len(_quiet) == 1, (
            "the same unresolved warning mailed every run — a daily repeat is "
            "how an alert stops being read")

    def test_a_new_problem_after_one_resolves_still_mails(self, monkeypatch, _quiet):
        near = max(1.0, infra.ALERT_DAYS_LEFT - 1)
        monkeypatch.setattr(infra, "run", lambda use_cache=True: _payload(at_risk=[_risk(near)]))
        infra.run_check()
        monkeypatch.setattr(infra, "run", lambda use_cache=True: _payload())
        infra.run_check()                                  # recovered, silent
        monkeypatch.setattr(infra, "run",
                            lambda use_cache=True: _payload(at_risk=[_risk(near, "Render", "Bandwidth")]))
        infra.run_check()
        assert len(_quiet) == 2, "a different meter running out was suppressed as a repeat"


class TestItIsActuallyScheduled:
    def test_the_daily_job_is_registered(self):
        """The whole point — without this the panel is a page nobody opens."""
        import backend.services.mandi_scheduler as ms
        src = __import__("inspect").getsource(ms._register_job)
        assert "infra_runway_check" in src, (
            "infra_service.run_check is not on the scheduler, so the free-tier "
            "meters are only read when someone opens /admin")


class TestASleepingInstanceIsNotAnOutage:
    """Render's free instance hibernates after ~15 idle minutes. Waking it
    returns 503 with `x-render-routing: hibernate-pending-wake` — caught live
    on 21 Sep 2026, when the panel read "Render बंद है" for a backend that was
    merely spinning up. The timeout branch already refused to call that an
    outage; the 503 path did not, and since run_check() mails on a `down`
    verdict it would have turned every cold start into an alarm."""

    def _probe(self, monkeypatch, status, routing):
        class _R:
            status_code = status
            headers = {"x-render-routing": routing, "content-encoding": "gzip"}
            content = b"x" * 900
        monkeypatch.setattr(infra.requests, "get", lambda *a, **k: _R())
        return infra._render_origin_probe()

    def test_hibernate_pending_wake_is_not_down(self, monkeypatch):
        _facts, status, _detail = self._probe(monkeypatch, 503, "hibernate-pending-wake")
        assert status != "down", (
            "a waking free instance was reported as an outage — this fires the "
            "daily alert email on an ordinary cold start")

    def test_a_real_suspension_is_still_down(self, monkeypatch):
        _facts, status, _detail = self._probe(monkeypatch, 503, "suspend-by-user")
        assert status == "down", "a bandwidth suspension must still read as down"

    def test_an_unexplained_500_is_still_down(self, monkeypatch):
        _facts, status, _detail = self._probe(monkeypatch, 500, "")
        assert status == "down", "a 500 with no routing header is a real failure"
