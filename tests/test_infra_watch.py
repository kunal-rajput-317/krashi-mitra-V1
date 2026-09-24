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

This file has already been lost once. It shipped on 21 Sep 2026 in 3c31404 and
was deleted that night by 7629f06, which re-committed an older copy of
infra_service.py over the new one and took the watch, the hibernate fix and the
Netlify retirement with it. Nothing failed, because the only thing that proved
any of it existed was this file. If it disappears again, so does all of that.
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
    def test_probe_list_does_not_include_netlify(self):
        keys = [k for k, _fn in infra._PROBES]
        assert "netlify" not in keys, (
            "Netlify was retired on 16 Sep 2026 — polling it puts a permanently "
            "unconfigured card on a page whose job is to be scanned quickly")
        assert set(keys) == {"render", "neon", "r2"}, keys


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


# ── Cloudflare R2, added 22 Sep 2026 ─────────────────────────
# R2 became the store for every listing photo on 18 Sep and nothing watched any
# of its three free allowances. When storage or Class A fills, uploads start
# failing — which is the one breakage a farmer notices the same minute.

R2_ENV = {
    "R2_ACCOUNT_ID":        "acct123",
    "R2_ACCESS_KEY_ID":     "AKIAEXAMPLE",
    "R2_SECRET_ACCESS_KEY": "s3cret-example-key",
    "R2_BUCKET":            "krashimitra-media",
    "R2_PUBLIC_BASE":       "https://media.krashimitra.in",
}


@pytest.fixture()
def r2_env(monkeypatch):
    for k, v in R2_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("R2_ENDPOINT", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    # The Postgres fallback meter reaches into the database; this file must not.
    monkeypatch.setattr(infra, "_media_db_meter", lambda: None)
    monkeypatch.setattr(infra, "_cloudflare_status_fact", lambda: None)


class TestR2IsWatched:
    def test_r2_is_polled(self):
        assert "r2" in [k for k, _fn in infra._PROBES], (
            "every farmer's photo lives in R2 and no meter was reading it")

    def test_storage_is_measured_without_a_cloudflare_token(self, monkeypatch, r2_env):
        """The storage meter must work on the credentials already set.

        Requiring a second, differently-shaped credential before the panel can
        say anything is how NEON_API_KEY went unset for a month while the cliff
        it guards stayed invisible. Storage is the allowance that stops uploads,
        and the S3 keys can already count a bucket.
        """
        monkeypatch.setattr(infra, "_media_db_meter", lambda: None)
        from backend.services import media_store
        monkeypatch.setattr(media_store, "usage", lambda prefix="": {
            "ok": True, "objects": 12, "bytes": 5 * 1024 ** 3,
            "truncated": False, "error": ""})
        card = infra._r2()
        storage = next(m for m in card["meters"] if m["key"] == "storage")
        assert storage["pct"] == 50.0, storage
        assert card["setup"]["env"] == "CLOUDFLARE_API_TOKEN", (
            "the ops meters are missing and the card did not say which variable "
            "would produce them")

    def test_a_full_bucket_reads_as_down(self, monkeypatch, r2_env):
        from backend.services import media_store
        monkeypatch.setattr(media_store, "usage", lambda prefix="": {
            "ok": True, "objects": 50000, "bytes": 11 * 1024 ** 3,
            "truncated": False, "error": ""})
        card = infra._r2()
        assert card["status"] == "down", (
            "the bucket is over its 10 GB allowance and uploads are failing, "
            "but the card was not red")

    def test_an_unconfigured_r2_offers_the_five_variables(self, monkeypatch):
        """A dead end is worse than a gap: the card has to name what to paste.

        `configured`, not `status`, is the flag to read — _roll_up() ranks "off"
        alongside "ok" (an unconfigured provider is not a broken one), so every
        card in this state comes back green and the UI distinguishes them by
        this field.
        """
        for k in R2_ENV:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr(infra, "_media_db_meter", lambda: None)
        card = infra._r2()
        assert card["configured"] is False
        for var in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                    "R2_BUCKET", "R2_PUBLIC_BASE"):
            assert var in card["setup"]["env"], f"{var} was not named"
        assert card["setup"]["where"] and card["setup"]["how"]

    def test_photos_falling_back_into_postgres_is_a_warning(self, monkeypatch):
        """R2 off does not mean uploads stop — it means they go into Neon.

        That is the interim store from the weeks R2 was deferred, and it is
        still wired. Silently filling a 60 MB slice of a 0.5 GB database that
        turns the WHOLE site read-only when full is the more dangerous of the
        two states, so it may never read as a quiet "off".
        """
        for k in R2_ENV:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr(infra, "_media_db_meter", lambda: infra._meter(
            "media_db", "Postgres fallback", 30 * 1024 ** 2, 60 * 1024 ** 2,
            "bytes", None))
        card = infra._r2()
        assert card["status"] == "warn", card["status"]
        assert any(m["key"] == "media_db" for m in card["meters"])


class TestCloudflareStatusDoesNotColourTheCard:
    """Cloudflare's status page covers the whole global network and reports a
    minor incident somewhere on it most days. Letting that into _roll_up would
    hold the card at warn permanently and mail a false alarm — the exact way a
    panel teaches its owner to stop reading it. Caught on 22 Sep 2026, when the
    first run of this card came back warn for a WAF degradation in another
    continent."""

    def test_cloudflare_is_not_in_the_voting_status_pages(self):
        assert "r2" not in infra.STATUS_PAGES, (
            "a global-network incident must not be able to mark this bucket down")

    def test_a_healthy_bucket_stays_ok_during_a_cloudflare_incident(self, monkeypatch, r2_env):
        monkeypatch.setattr(infra, "_cloudflare_status_fact",
                            lambda: ["Cloudflare network", "⚠ Minor Service Outage"])
        from backend.services import media_store
        monkeypatch.setattr(media_store, "usage", lambda prefix="": {
            "ok": True, "objects": 3, "bytes": 350_000, "truncated": False, "error": ""})
        card = infra._r2()
        assert card["status"] == "ok", (
            "somebody else's PoP had a bad afternoon and this card went amber")
        assert ["Cloudflare network", "⚠ Minor Service Outage"] in card["facts"], (
            "the incident was hidden entirely — it should inform without voting")


class TestOperationClassesAreCountedCorrectly:
    """Cloudflare returns raw action types and bills them in two classes it does
    not name. A PutObject counted as Class B reads 0.01% against 10M while the
    1M write allowance that actually stops uploads quietly fills."""

    def _card(self, monkeypatch, groups):
        for k, v in R2_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
        monkeypatch.setattr(infra, "_media_db_meter", lambda: None)
        monkeypatch.setattr(infra, "_cloudflare_status_fact", lambda: None)
        from backend.services import media_store
        monkeypatch.setattr(media_store, "usage", lambda prefix="": {
            "ok": True, "objects": 3, "bytes": 350_000, "truncated": False, "error": ""})
        monkeypatch.setattr(infra, "_graphql", lambda *a, **k: (
            {"viewer": {"accounts": [{"r2OperationsAdaptiveGroups": groups}]}}, ""))
        return infra._r2()

    def _g(self, action, n):
        return {"dimensions": {"actionType": action}, "sum": {"requests": n}}

    def test_writes_land_on_class_a_and_reads_on_class_b(self, monkeypatch):
        card = self._card(monkeypatch, [
            self._g("PutObject", 400), self._g("CreateMultipartUpload", 100),
            self._g("GetObject", 7000), self._g("HeadObject", 3000),
        ])
        a = next(m for m in card["meters"] if m["key"] == "class_a")
        b = next(m for m in card["meters"] if m["key"] == "class_b")
        assert a["used"] == 500, a["used"]
        assert b["used"] == 10_000, b["used"]

    def test_a_free_delete_counts_against_neither(self, monkeypatch):
        card = self._card(monkeypatch, [self._g("DeleteObject", 250)])
        a = next(m for m in card["meters"] if m["key"] == "class_a")
        b = next(m for m in card["meters"] if m["key"] == "class_b")
        assert a["used"] == 0 and b["used"] == 0, (
            "DeleteObject is free on R2 and must not consume either allowance")

    def test_an_unrecognised_action_is_named_not_swallowed(self, monkeypatch):
        """Cloudflare adds action types. One folded silently into a class is a
        meter that reads low for a reason nobody would go looking for."""
        card = self._card(monkeypatch, [self._g("SomeFutureOp", 900)])
        labels = {f[0] for f in card["facts"]}
        assert "वर्गीकृत नहीं" in labels, card["facts"]
        assert any("SomeFutureOp" in str(f[1]) for f in card["facts"])

    def test_a_refused_token_does_not_fake_a_zero(self, monkeypatch):
        """GraphQL answers 200 with an `errors` array. Reading that as an empty
        result paints both ops meters at 0% — a panel confidently reporting
        that nothing has been written all month."""
        for k, v in R2_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
        monkeypatch.setattr(infra, "_media_db_meter", lambda: None)
        monkeypatch.setattr(infra, "_cloudflare_status_fact", lambda: None)
        from backend.services import media_store
        monkeypatch.setattr(media_store, "usage", lambda prefix="": {
            "ok": True, "objects": 3, "bytes": 350_000, "truncated": False, "error": ""})
        monkeypatch.setattr(infra, "_graphql",
                            lambda *a, **k: (None, "HTTP 403 — the API token was refused"))
        card = infra._r2()
        assert not [m for m in card["meters"] if m["key"] in ("class_a", "class_b")], (
            "a refused token produced operation meters anyway")
        assert any("403" in str(f[1]) for f in card["facts"]), card["facts"]
