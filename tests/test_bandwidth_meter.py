"""Render's outbound bandwidth: the meter that says where it goes, and the
image budget that keeps the biggest files from coming back.

Render suspends the workspace at 5 GB/month and has done so twice; on
24 Sep 2026 it was on course for a third time with no way to say which
responses were spending it. See backend/services/bandwidth_meter.py.
"""

from pathlib import Path

import pytest
from PIL import Image
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from backend.services import bandwidth_meter as bm

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clean_counters():
    with bm._lock:
        bm._pending.clear()
    yield
    with bm._lock:
        bm._pending.clear()


# ── classification ──────────────────────────────────────────────

@pytest.mark.parametrize("path,status,want", [
    ("/", 200, "home"),
    ("/bhav/wheat/uttar-pradesh", 200, "bhav"),
    ("/naksha/bihar", 200, "naksha"),
    ("/images/articles/jau-ki-kheti.webp", 200, "images/articles"),
    ("/images/up-ka-naksha-district-map.png", 200, "images"),
    ("/assets/logo.png", 200, "images/assets"),
    ("/uploads/bazar/abc.webp", 200, "uploads"),
    ("/drawer-menu.js", 200, "js/css"),
    ("/km-shell.css", 200, "js/css"),
    ("/data/bihar-districts.geojson", 200, "geojson"),
    ("/api/weather", 200, "api/weather"),
    ("/weather.html", 200, "weather"),
    ("/wp-admin/setup.php", 404, "404"),
    ("/bhav/x", 500, "5xx"),
])
def test_group_of(path, status, want):
    assert bm.group_of(path, status) == want


@pytest.mark.parametrize("ua,want", [
    ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "googlebot"),
    ("Googlebot-Image/1.0", "googlebot-image"),
    ("Mozilla/5.0 (compatible; bingbot/2.0)", "bingbot"),
    ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2)", "gptbot"),
    ("Mozilla/5.0 (compatible; AhrefsBot/7.0)", "seo-tools"),
    ("python-requests/2.32", "script"),
    ("Mozilla/5.0 (Linux; Android 13; SM-A145F) AppleWebKit/537.36 Chrome/128 Mobile Safari/537.36", "human"),
    ("", "no-ua"),
])
def test_agent_of(ua, want):
    assert bm.agent_of(ua) == want


# ── the middleware counts the bytes that actually went out ─────

def _app():
    async def big(request):
        return PlainTextResponse("x" * 5000)

    async def moved(request):
        return Response(status_code=301, headers={"location": "/bhav"})

    app = Starlette(routes=[Route("/bhav/wheat", big), Route("/old", moved)])
    app.add_middleware(bm.BandwidthMeterMiddleware)
    return app


def test_middleware_counts_body_and_headers_per_group_and_agent():
    c = TestClient(_app())
    c.get("/bhav/wheat", headers={"user-agent": "Googlebot/2.1"})
    c.get("/bhav/wheat", headers={"user-agent": "Googlebot/2.1"})
    c.get("/old", headers={"user-agent": "Mozilla/5.0 Chrome/128 Mobile"}, follow_redirects=False)
    snap = {(g, a): v for (_, g, a), v in bm.pending_snapshot().items()}
    n, b = snap[("bhav", "googlebot")]
    assert n == 2
    assert 2 * 5000 < b < 2 * 5000 + 1000        # body + a little header
    n, b = snap[("old", "human")]
    assert n == 1 and 0 < b < 500                  # a redirect is headers only


def test_flush_failure_keeps_the_counts():
    bm.record("/bhav/wheat", 200, "Googlebot", 1234)

    class Boom:
        def begin(self):
            raise RuntimeError("neon asleep")

    import backend.database.db as db
    real = db.engine
    db.engine = Boom()
    try:
        assert bm.flush() == 0
    finally:
        db.engine = real
    snap = {(g, a): v for (_, g, a), v in bm.pending_snapshot().items()}
    assert snap[("bhav", "googlebot")] == [1, 1234]


def test_report_includes_unflushed_counts():
    bm.record("/naksha/bihar", 200, "GPTBot", 9_000)
    r = bm.report(1)
    assert r["total_bytes"] >= 9_000
    assert any(p["group"] == "naksha" and p["agent"] == "gptbot" for p in r["top_pairs"])


def test_meter_is_the_outermost_middleware():
    """Inside gzip it would count uncompressed bytes Render never sends; inside
    the redirect middleware it would miss every 301."""
    from backend.main import app
    assert app.user_middleware[0].cls is bm.BandwidthMeterMiddleware


def test_admin_bandwidth_route_exists():
    from backend.main import app
    assert any(getattr(r, "path", "") == "/admin/bandwidth" for r in app.routes)


def test_hourly_flush_is_scheduled():
    src = (ROOT / "backend/services/mandi_scheduler.py").read_text(encoding="utf-8")
    assert 'id                 = "bandwidth_meter_flush"' in src


# ── the image budget ──────────────────────────────────────────

def test_heavy_photos_are_at_most_960_wide():
    """A photo over 150 KB must already be at the 960 px ceiling — anything
    wider is tools/shrink_images.py not having been run on it."""
    bad = []
    for d in ("frontend/images", "frontend/assets"):
        for p in (ROOT / d).rglob("*"):
            if p.suffix.lower() in (".webp", ".jpg", ".jpeg") and p.stat().st_size > 150_000:
                with Image.open(p) as im:
                    if im.width > 960:
                        bad.append(f"{p.relative_to(ROOT)} {im.width}px {p.stat().st_size // 1024} KB")
    assert not bad, "run python tools/shrink_images.py:\n" + "\n".join(bad)


def test_state_map_pngs_are_palette():
    maps = list((ROOT / "frontend/images").glob("*-ka-naksha-district-map.png"))
    assert maps
    rgb = [p.name for p in maps if Image.open(p).mode != "P"]
    assert not rgb, f"24-bit map PNGs (3x the bytes): {rgb}"


def test_article_hero_generator_writes_960():
    src = (ROOT / "tools/fetch_article_images.py").read_text(encoding="utf-8")
    assert "TARGET_W = 960" in src


# ── edge cache lifetimes ──────────────────────────────────────

def test_bhav_price_pages_hour_other_doc_pages_three_hours():
    from backend.routes import bhav
    assert "max-age=3600," in bhav._CACHE_HEADERS["CDN-Cache-Control"]
    assert "max-age=10800," in bhav._CACHE_HEADERS_SLOW["CDN-Cache-Control"]
    # _doc() reads the DB for its footer, so check the switch in its source.
    import inspect
    assert ('_CACHE_HEADERS if active == "bhav" else _CACHE_HEADERS_SLOW'
            in inspect.getsource(bhav._doc))
