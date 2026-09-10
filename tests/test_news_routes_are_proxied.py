"""Every server-rendered कृषि न्यूज़ route must be reachable on the apex domain.

The news section is served from two places at once, and that is the whole
problem this file guards. The hub at /krashi_news is a static Netlify file
(frontend/krashi_news.html). The story pages are server-rendered by
backend/routes/news_page.py and exist ONLY on the backend host — so they reach
a farmer only if _redirects proxies them.

For a while it didn't. `/krashi_news/<slug>` and `/news` had no rule, fell
through to the `/* -> /404.html 404` catch-all at the bottom of _redirects, and
answered 404 on krashimitra.in while returning 200 on the Render host. Nothing
caught it, because everything that could have looked was pointed at the host
where it worked: sitemap.py generated the URLs from the same code that serves
them, each canonical to itself, and the admin panel called the API directly.
Google was handed 15 story URLs that all 404'd.

These tests read _redirects the way Netlify does — first matching rule wins —
so a route that is only reached by the catch-all fails here instead of in GSC.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
REDIRECTS = REPO / "frontend" / "_redirects"

# The SSR paths that must resolve on the apex domain. The hub is deliberately
# absent: Netlify serves the static file there, which is a real page, not a 404.
SSR_NEWS_PATHS = [
    "/krashi_news/kathuaa-men-pm-kisaana-yojanaa-se-khetee-ko-milee",
    "/krashi_news/some-other-story-slug",
    "/news",
]


def rules():
    """(source, target, status) for each rule, in file order."""
    out = []
    for line in REDIRECTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 3:
            out.append((parts[0], parts[1], parts[2]))
    return out


def resolve(path: str):
    """The first rule that matches `path`, as Netlify would pick it."""
    for src, target, status in rules():
        if src.endswith("/*"):
            if path.startswith(src[:-1]):
                return src, target, status
        elif src == path:
            return src, target, status
    return None


@pytest.mark.parametrize("path", SSR_NEWS_PATHS)
def test_ssr_news_path_is_proxied_not_404ed(path):
    match = resolve(path)
    assert match is not None, f"{path} matches no rule at all"

    src, target, status = match
    assert src != "/*", (
        f"{path} is server-rendered and reaches only the catch-all, so it "
        f"serves /404.html on krashimitra.in. Add a proxy rule for it."
    )
    assert target.startswith("http"), f"{path} must proxy to the backend, got {target}"
    assert status.startswith("200"), (
        f"{path} must be a 200 proxy (the URL is canonical to itself), got {status}"
    )


def test_story_splat_covers_every_published_slug():
    """The rule is a splat, so it has to cover slugs nobody has written yet."""
    from backend.routes.news_page import _story_url
    from backend.services.news_auto_service import get_published_posts

    checked = 0
    for post in get_published_posts():
        url = _story_url(post)
        if not url.startswith("/krashi_news/"):
            continue  # master story: points at its own /articles/ page
        checked += 1
        match = resolve(url)
        assert match and match[0] != "/*", f"published story 404s on the apex domain: {url}"

    assert checked, "no auto-pilot story pages found to check"


def test_hub_aliases_agree_on_one_address():
    """/krashi_news.html must not be a second live address for the hub."""
    match = resolve("/krashi_news.html")
    assert match, "/krashi_news.html has no rule; it would 404"
    assert match[2].startswith("301"), (
        "/krashi_news.html must 301 to the extensionless canonical, not serve a page"
    )
    assert match[1] == "/krashi_news"
