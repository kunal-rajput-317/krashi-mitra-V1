"""App-level smoke tests: it boots, the health probes answer, and the
middleware contract holds.

`/health` in particular has an operational contract, not just a shape: the
keep-alive workflow pings it every 10 minutes to stop Render's free dyno
sleeping, and it must never touch the database — a Neon cold start would
otherwise make a healthy dyno look down.
"""


class TestHealth:
    def test_health_is_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_does_not_touch_the_database(self, client, monkeypatch):
        """Guards the keep-alive contract described in .github/workflows."""
        import backend.database.db as db

        def _explode(*args, **kwargs):
            raise AssertionError("/health opened a database session")

        monkeypatch.setattr(db, "SessionLocal", _explode)
        assert client.get("/health").status_code == 200

    def test_health_data_reports_freshness_shape(self, client):
        response = client.get("/health/data")
        assert response.status_code == 200
        body = response.json()
        # The monitor workflow keys off `stale`; renaming it silently breaks
        # the only alarm that catches a stopped mandi feed.
        assert "stale" in body
        assert isinstance(body["stale"], bool)


class TestServerRenderedPages:
    """The SEO surface must render even when the price table is empty.

    These pages are what Google crawls; a 500 on an empty database would
    deindex them. Introspecting `app.routes` cannot verify this — FastAPI
    wraps included routers, so the paths are not visible there — and rendering
    is the property that actually matters anyway.
    """

    import pytest as _pytest

    @_pytest.mark.parametrize(
        "path",
        ["/bhav/", "/naksha", "/sitemap.xml", "/llms.txt", "/find?q=gehu"],
    )
    def test_renders_without_data(self, client, path):
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
        assert len(response.content) > 500, f"{path} rendered a near-empty body"

    def test_sitemap_is_valid_xml(self, client):
        from xml.etree import ElementTree

        ElementTree.fromstring(client.get("/sitemap.xml").content)

    def test_unknown_path_is_404_not_500(self, client):
        assert client.get("/definitely-not-a-page").status_code == 404


class TestSecurityHeaders:
    def test_baseline_headers_present(self, client):
        headers = client.get("/health").headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "SAMEORIGIN"
        assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "geolocation=(self)" in headers["Permissions-Policy"]

    def test_hsts_absent_outside_production(self, client):
        """HSTS on a local http:// origin would pin the browser to https."""
        assert "Strict-Transport-Security" not in client.get("/health").headers


class TestRequestId:
    def test_response_carries_a_request_id(self, client):
        rid = client.get("/health").headers.get("X-Request-ID")
        assert rid and len(rid) >= 8

    def test_inbound_request_id_is_honoured(self, client):
        response = client.get("/health", headers={"X-Request-ID": "abc123trace"})
        assert response.headers["X-Request-ID"] == "abc123trace"

    def test_each_request_gets_a_distinct_id(self, client):
        first = client.get("/health").headers["X-Request-ID"]
        second = client.get("/health").headers["X-Request-ID"]
        assert first != second

    def test_log_records_carry_the_same_id_as_the_response(self, client, caplog):
        """The whole point of the middleware.

        Regression guard: an earlier version reset the context var in a
        `finally` that ran *before* the access line was emitted, so every
        access record logged "-" instead of the id — silently defeating the
        correlation it exists to provide.
        """
        import logging

        with caplog.at_level(logging.INFO, logger="krashimitra.access"):
            response = client.get("/bhav/", headers={"X-Request-ID": "corr-check-1"})

        assert response.headers["X-Request-ID"] == "corr-check-1"
        access = [r for r in caplog.records if r.name == "krashimitra.access"]
        assert access, "no access record was emitted"
        assert all(getattr(r, "request_id", None) == "corr-check-1" for r in access)


class TestUnhandledExceptionHandler:
    """Tested directly rather than through a route.

    A route added at test time cannot be reached: `app.mount("/", StaticFiles)`
    is registered last in main.py and swallows every unmatched path as a 404,
    so an injected /__boom never runs. The handler is a plain coroutine, so
    call it.
    """

    def _invoke(self, app):
        import asyncio
        import json

        from starlette.requests import Request

        from backend.main import unhandled_exception_handler

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/orders",
            "headers": [],
            "query_string": b"",
        }
        response = asyncio.run(
            unhandled_exception_handler(
                Request(scope), RuntimeError("mandi_prices.row_key leaked here")
            )
        )
        return response, json.loads(bytes(response.body))

    def test_returns_the_house_error_envelope(self, app):
        response, body = self._invoke(app)
        assert response.status_code == 500
        # README pins this contract: {success, message, data} on every response.
        assert set(body) == {"success", "message", "data"}
        assert body["success"] is False
        assert body["data"] == {}
        assert body["message"].strip()

    def test_does_not_leak_internals_to_the_client(self, app):
        _, body = self._invoke(app)
        assert "mandi_prices" not in body["message"]
        assert "RuntimeError" not in body["message"]

    def test_message_is_hindi_for_farmers(self, app):
        _, body = self._invoke(app)
        assert any("ऀ" <= ch <= "ॿ" for ch in body["message"])
