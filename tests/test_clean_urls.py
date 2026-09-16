"""Every canonical URL this site publishes must resolve on this origin.

The canonical form of a core page is extensionless: sitemap.py's CORE table
emits /krashi_bajar, _redirects 301s /krashi_bajar.html onto it, and every SSR
page the backend renders links to it that way. Netlify resolves those natively
from the .html file, so the site looked fine — but the origin behind it did
not: Starlette's StaticFiles never appends ".html", so ten canonical URLs
(/shop, /krashi_bajar, /chat, /khoj, /meri_fasal, /sarkari_yojana, /help,
/about, /privacy-policy, /terms) returned 404.html on this server.

That was invisible in production only for as long as Netlify stays up. It has
not (11 Aug 2026, usage_exceeded sitewide), and every one of those URLs is in
the sitemap Google crawls. It also meant local dev 404'd on half the site.

Driving this off CORE rather than a hand-written list is the point: a new page
added to the sitemap is covered here the day it lands.
"""

from pathlib import Path

import pytest

from backend.routes.sitemap import CORE

# routes/weather.py owns /weather on this origin — it is the JSON forecast API,
# and weather.html fetches `${KRASHIMITRA_API_BASE}/weather` to fill itself in.
# Netlify serves the page at that path, the origin serves the API, and making
# the origin serve the page instead would break the page. The one CORE row a
# clean-URL fallback cannot cover.
ROUTER_OWNED = {"/weather"}

CANONICAL_URLS = [url for _file, url, *_rest in CORE if url not in ROUTER_OWNED]


@pytest.fixture(scope="module")
def not_found_page(repo_root: Path) -> bytes:
    return (repo_root / "frontend" / "404.html").read_bytes()


class TestCanonicalURLsResolve:
    @pytest.mark.parametrize("url", CANONICAL_URLS)
    def test_canonical_url_serves_a_page(self, client, not_found_page, url):
        response = client.get(url)

        assert response.status_code == 200, f"{url} → {response.status_code}"
        # A missing static file still answers with HTML (it is 404.html), so
        # the status code alone proves nothing about which page came back.
        assert response.headers["content-type"].startswith("text/html"), (
            f"{url} served {response.headers['content-type']}, not a page"
        )
        assert response.content != not_found_page, (
            f"{url} fell through to 404.html — the clean-URL fallback in "
            f"backend/main.py did not resolve it to its .html file"
        )

    def test_the_extension_form_still_works(self, client):
        """Internal links and old bookmarks still say .html; prod 301s them,
        and this origin must keep serving them rather than break the link."""
        assert client.get("/krashi_bajar.html").status_code == 200

    def test_a_directory_still_wins(self, client, repo_root):
        """/dukanlisting is a real directory, not dukanlisting.html. The plain
        path is looked up first precisely so this keeps resolving natively."""
        response = client.get("/dukanlisting", follow_redirects=True)
        expected = repo_root / "frontend" / "dukanlisting" / "index.html"

        assert response.status_code == 200
        assert response.content == expected.read_bytes()


class TestNothingElseBecameReachable:
    """The fallback must only rescue URLs that name a real .html file."""

    def test_an_unknown_page_still_404s(self, client):
        assert client.get("/not-a-real-page").status_code == 404

    def test_a_missing_asset_still_404s(self, client):
        assert client.get("/assets/not-a-real-file.css").status_code == 404

    def test_it_does_not_climb_out_of_frontend(self, client):
        """`backend/main.py` exists; /backend/main must not serve it."""
        assert client.get("/backend/main").status_code == 404
