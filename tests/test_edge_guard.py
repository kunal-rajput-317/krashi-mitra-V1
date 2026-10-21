"""Origin lock, per-IP flood guard and the client-IP rule behind every rate limit.

See backend/utils/edge_guard.py. These run against a tiny app wrapped in the
middleware, so they do not depend on the full backend booting.
"""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.utils.edge_guard import EdgeGuardMiddleware, bucket_key
from backend.utils.security import client_ip


def _client(secret: str = "", per_minute: int = 0) -> TestClient:
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/bhav")
    def bhav():
        return {"page": "bhav"}

    @app.get("/static/app.js")
    def asset():
        return {"asset": True}

    @app.get("/ip")
    def ip(request: Request):
        return {"ip": client_ip(request)}

    app.add_middleware(EdgeGuardMiddleware, secret=secret, per_minute=per_minute)
    return TestClient(app)


# ── client IP ────────────────────────────────────────────────

def test_cloudflare_ip_wins_over_forwarded_for():
    c = _client()
    r = c.get("/ip", headers={"cf-connecting-ip": "1.1.1.1",
                              "x-forwarded-for": "6.6.6.6, 1.1.1.1"})
    assert r.json()["ip"] == "1.1.1.1"


def test_forwarded_for_is_only_the_fallback():
    c = _client()
    assert c.get("/ip", headers={"x-forwarded-for": "8.8.8.8, 10.0.0.1"}).json()["ip"] == "8.8.8.8"
    assert c.get("/ip").json()["ip"] == "testclient"


# ── origin lock ──────────────────────────────────────────────

def test_lock_off_by_default():
    assert _client().get("/bhav").status_code == 200


def test_lock_refuses_requests_that_skipped_cloudflare():
    c = _client(secret="s3cret-value")
    r = c.get("/bhav")
    assert r.status_code == 403
    assert r.headers["cache-control"] == "no-store"
    assert c.get("/bhav", headers={"x-origin-shield": "wrong"}).status_code == 403


def test_lock_lets_cloudflare_traffic_through():
    c = _client(secret="s3cret-value")
    assert c.get("/bhav", headers={"x-origin-shield": "s3cret-value"}).status_code == 200


def test_lock_keeps_health_open_for_render():
    assert _client(secret="s3cret-value").get("/health").status_code == 200


# ── flood guard ──────────────────────────────────────────────

def test_flood_guard_cuts_off_one_ip_and_spares_others():
    c = _client(per_minute=5)
    attacker = {"cf-connecting-ip": "1.2.3.4"}
    codes = [c.get("/bhav", headers=attacker).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5
    assert codes[5:] == [429, 429]
    blocked = c.get("/bhav", headers=attacker)
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["cache-control"] == "no-store"
    # A real farmer on another IP is unaffected.
    assert c.get("/bhav", headers={"cf-connecting-ip": "5.6.7.8"}).status_code == 200


def test_fake_forwarded_for_no_longer_dodges_the_limit():
    c = _client(per_minute=3)
    codes = [
        c.get("/bhav", headers={"cf-connecting-ip": "1.2.3.4",
                                "x-forwarded-for": f"9.9.9.{i}"}).status_code
        for i in range(5)
    ]
    assert codes.count(429) == 2


def test_flood_guard_skips_health_assets_and_local_traffic():
    c = _client(per_minute=1)
    ip = {"cf-connecting-ip": "1.2.3.4"}
    for _ in range(3):
        assert c.get("/health", headers=ip).status_code == 200
        assert c.get("/static/app.js", headers=ip).status_code == 200
        assert c.get("/bhav").status_code == 200   # "testclient": never counted


def test_flood_guard_zero_means_off():
    c = _client(per_minute=0)
    ip = {"cf-connecting-ip": "1.2.3.4"}
    assert all(c.get("/bhav", headers=ip).status_code == 200 for _ in range(20))


def test_ipv6_is_counted_per_64():
    assert bucket_key("2401:4900:1c2a:5d6e::1") == bucket_key("2401:4900:1c2a:5d6e:ffff::9")
    assert bucket_key("2401:4900:1c2a:5d6e::1") != bucket_key("2401:4900:1c2a:5d6f::1")
    assert bucket_key("127.0.0.1") is None
    assert bucket_key("10.0.0.5") is None
    assert bucket_key("unknown") is None
