"""कृषि न्यूज़ shows real like counts only (LEGAL_RULES §1, fake social proof).

Until 2 Oct 2026 every story started from an invented "seed": 260-580 likes
from the API and the hub's JavaScript, 12-45 on the server-rendered page, and
a random 260-580 stored on each auto-pilot post. The comment in the hub said
why: "so the website feels active". An invented count is a dark pattern under
the Consumer Protection Act, so these tests fail the build if one comes back.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

NEWS_SOURCES = [
    "backend/routes/news_page.py",
    "backend/routes/news_curate.py",
    "backend/services/news_auto_service.py",
    "frontend/krashi_news.html",
    "admin/index.html",
]

# The shapes the seed took. A real count is a DB row count; nothing about a
# like number should ever be random, hashed or "seeded".
FORBIDDEN = [
    r"seed_likes",
    r"getSeedLikes",
    r"_calc_seed_likes",
    r"base_seed",
    r"Seed Likes",
    r"लाइक्स सीड",
]


def test_no_invented_like_count_in_news_code():
    hits = []
    for rel in NEWS_SOURCES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for pat in FORBIDDEN:
            for m in re.finditer(pat, text):
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{rel}:{line} {pat}")
    assert not hits, "invented like counts are back:\n" + "\n".join(hits)


def test_stored_posts_carry_no_seed():
    text = (REPO_ROOT / "backend/data/news_funnel.json").read_text(encoding="utf-8")
    assert "seed_likes" not in text


def test_like_api_counts_only_real_rows(client):
    """A story nobody has liked reports 0, not a seeded number."""
    r = client.get("/api/news/social/batch", params={"ids": "km-auto-never-liked"})
    assert r.status_code == 200
    assert r.json()["km-auto-never-liked"]["likes"] == 0

    r = client.get("/api/news/km-auto-never-liked/social")
    assert r.status_code == 200
    assert r.json()["total_likes"] == 0
