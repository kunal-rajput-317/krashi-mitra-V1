"""The news auto-pilot keeps running, and keeps what it publishes.

Two faults stopped /krashi_news on 5 Sep 2026, and nothing new appeared for
four weeks:

1. A deadlock. Discovery skips after day 3 of a cycle, and only publishing
   started a new cycle. A cycle that reached day 4 with nothing staged could
   never move again.
2. The store was a JSON file on Render's disk, which every deploy replaces
   with the copy in git. Every live post was lost, and the stuck cycle came
   back with each deploy.

Also pinned here: the Google News sitemap and the story page's large image.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.services import news_auto_service as news


@pytest.fixture(autouse=True)
def isolated_funnel(tmp_path, db_engine):
    with patch.object(news, "DATA_FILE", tmp_path / "news_funnel.json"), \
         patch.object(news, "_mem", {"data": None}), \
         patch.object(news, "_DB_KEY", f"test.news_pipeline.{tmp_path.name}"):
        yield


def _stuck_funnel(days_ago=27, staged=()):
    start = (datetime.utcnow() - timedelta(days=days_ago)).isoformat()
    return {"current_cycle": 2, "cycle_start_date": start,
            "staged_posts": list(staged), "published_posts": []}


def _run_discovery(raw):
    async def fake_fetch():
        return raw

    async def fake_format(title, content, url, language="hi"):
        return {"id": "km-auto-test-" + str(abs(hash(title)) % 10**6),
                "title": title, "excerpt": content, "full_story": content,
                "bullets": [], "category": "scheme", "created_at": datetime.utcnow().isoformat(),
                "status": "staged"}

    with patch.object(news, "fetch_external_agri_stories", fake_fetch), \
         patch.object(news, "format_agri_post_with_ai", fake_format), \
         patch.object(news, "is_duplicate_story", lambda *a, **k: (False, "")):
        return asyncio.run(news.run_discovery_and_stage(target_count=3, check_cycle=True))


RAW = [{"title": "PIB: कृषि मंत्रालय ने खरीफ की समीक्षा की", "content": "समीक्षा बैठक हुई।",
        "url": "https://pib.gov.in/x"}]


def test_a_stalled_cycle_with_nothing_staged_starts_a_new_one():
    news._save_data(_stuck_funnel())
    staged = _run_discovery(RAW)
    assert len(staged) == 1
    data = news._load_data()
    assert data["current_cycle"] == 3
    assert news._parse_iso_dt(data["cycle_start_date"]) > datetime.utcnow() - timedelta(minutes=5)


def test_posts_held_for_review_do_not_stall_the_cycle():
    held = {"id": "km-auto-held", "title": "x", "held_for_review": True,
            "created_at": datetime.utcnow().isoformat()}
    news._save_data(_stuck_funnel(staged=[held]))
    assert len(_run_discovery(RAW)) == 1
    ids = [p["id"] for p in news._load_data()["staged_posts"]]
    assert "km-auto-held" in ids, "a held post stays for the human reviewer"


def test_an_unreviewed_batch_still_waits_for_the_day5_watchdog():
    waiting = {"id": "km-auto-wait", "title": "x", "created_at": datetime.utcnow().isoformat()}
    news._save_data(_stuck_funnel(days_ago=3, staged=[waiting]))
    assert _run_discovery(RAW) == []


def test_unreachable_feeds_stage_nothing_invented():
    """The old fallback published two hard-coded claims with no source."""
    class Down:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise OSError("offline")

    with patch.object(news.httpx, "AsyncClient", Down):
        assert asyncio.run(news.fetch_external_agri_stories()) == []


def test_the_funnel_survives_losing_the_file(tmp_path):
    """A deploy replaces the file. The database copy must win."""
    data = _stuck_funnel(days_ago=0)
    data["published_posts"] = [{"id": "km-auto-kept", "title": "रखी गई खबर"}]
    assert news._save_data(data) is True

    (tmp_path / "news_funnel.json").write_text('{"published_posts": []}', encoding="utf-8")
    news._mem["data"] = None                    # a fresh process after the deploy
    assert [p["id"] for p in news.get_published_posts()] == ["km-auto-kept"]


def test_load_hands_out_a_copy():
    news._save_data(_stuck_funnel(days_ago=0))
    news._load_data()["published_posts"].append({"id": "km-auto-stray"})
    assert news._load_data()["published_posts"] == []


# ── Discover / Google News ───────────────────────────────────

def _story(pid, title, published):
    return {"id": pid, "title": title, "is_gemini_post": True, "link": f"#story-{pid}",
            "published_at": published, "image": "/images/articles/kisan-credit-card-card.webp"}


def test_news_sitemap_lists_only_the_last_two_days():
    from backend.routes.sitemap import build_news_sitemap
    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    fresh = _story("km-auto-fresh", "ताज़ा खबर & अपडेट", "2026-10-01T09:00:00")
    old = _story("km-auto-old", "पुरानी खबर", "2026-09-25T09:00:00")
    with patch("backend.routes.news_page._all_stories", return_value=[fresh, old]):
        xml = build_news_sitemap(now)
    assert xml.count("<url>") == 1
    assert "<news:publication_date>2026-10-01T09:00:00+00:00</news:publication_date>" in xml
    assert "<news:language>hi</news:language>" in xml
    assert "ताज़ा खबर &amp; अपडेट" in xml
    assert "पुरानी" not in xml


def test_news_sitemap_is_served_and_declared(client):
    from tests.test_news_no_fake_likes import REPO_ROOT
    r = client.get("/news-sitemap.xml")
    assert r.status_code == 200
    assert "sitemap-news/0.9" in r.text
    robots = (REPO_ROOT / "frontend/robots.txt").read_text(encoding="utf-8")
    assert "Sitemap: https://krashimitra.in/news-sitemap.xml" in robots


def test_story_page_uses_the_large_cover_and_dated_schema(client):
    from backend.routes import news_page
    s = _story("km-auto-big", "बड़ी तस्वीर वाली खबर", "2026-10-01T09:00:00.123456")
    with patch.object(news_page, "_all_stories", return_value=[s]):
        slug = news_page._story_slug(s)
        r = client.get(f"/krashi_news/{slug}")
    assert r.status_code == 200
    assert "/images/articles/kisan-credit-card.webp" in r.text
    assert "kisan-credit-card-card.webp" not in r.text
    assert '"datePublished": "2026-10-01T09:00:00+00:00"' in r.text
    assert "max-image-preview:large" in r.text


def test_large_image_keeps_the_card_when_no_full_size_exists():
    from backend.routes.news_page import _large_image
    assert _large_image("/images/articles/no-such-thing-card.webp") == \
        "/images/articles/no-such-thing-card.webp"
    assert _large_image("/images/og-banner.webp") == "/images/og-banner.webp"


# ── Paused by the owner, 2 Oct 2026 ──────────────────────────

def test_autopilot_is_paused_by_default():
    """No new stories unless NEWS_AUTOPILOT_ENABLED=true. The hub stays up."""
    from backend.config import get_setting
    from backend.services import news_auto_scheduler as sched
    assert get_setting("news_autopilot_enabled") is False
    asyncio.run(sched.start_scheduler())
    assert not sched.scheduler.running
    assert sched.scheduler.get_jobs() == []


def test_the_hub_still_renders_while_paused(client):
    r = client.get("/krashi_news")
    assert r.status_code == 200
