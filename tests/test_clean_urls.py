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

# /weather was the one CORE row this file used to skip: routes/weather.py owned
# the bare path and answered it with JSON, which was survivable only while
# Netlify served the page and a separate host served the API. Netlify went
# (16 Sep 2026), one origin began serving both, and the router won — every
# मौसम देखें button on the site opened raw JSON. The forecast API moved to
# /api/weather, so the page resolves through the same fallback as every other
# canonical URL and this list no longer needs an exception.
CANONICAL_URLS = [url for _file, url, *_rest in CORE]


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


class TestRulesNetlifyUsedToAnswer:
    """The /international subtree, once this origin owned it.

    Until 16 Sep 2026 Netlify served frontend/international/*.html straight off
    disk. When the site moved to Cloudflare DNS → Render, routes/international.py
    owned the whole subtree, and its deliberate two-letter guard turned every
    .html form into a hard 404 — including /international/index.html, which is
    where both the `/global` and `/international/*` rules in frontend/_redirects
    land. So those rules resolved onto a 404 and the hub was unreachable by
    either of its two aliases.
    """

    @pytest.mark.parametrize("url,target", [
        ("/international/us.html", "/international/us"),
        ("/international/bd.html", "/international/bd"),
        ("/international/index.html", "/international"),
    ])
    def test_the_html_form_folds_onto_the_canonical_url(self, client, url, target):
        response = client.get(url, follow_redirects=False)
        assert response.status_code == 301, url
        assert response.headers["location"] == target

    def test_the_hub_aliases_resolve(self, client):
        for url in ("/global", "/international"):
            response = client.get(url, follow_redirects=True)
            assert response.status_code == 200, url

    def test_the_two_letter_guard_still_holds(self, client):
        """The .html branch must not become a way around the shape check —
        `code` is user input and the guard is the only thing between it and
        the filesystem."""
        for url in ("/international/zzzz.html", "/international/..%2Fsecret.html"):
            response = client.get(url, follow_redirects=False)
            assert response.status_code != 200, url
            assert "secret" not in response.headers.get("location", "")

    def test_no_indexed_url_redirects_twice(self, client, repo_root):
        """A 301 has to land on something that answers, not on another 301.

        The seven legacy country bookmarks (/us.html, /bd.html …) pointed at
        /international/{code}.html, which now redirects again — a two-hop chain
        from a URL Google still has indexed.
        """
        # The one accepted chain. routes/articles.py canonicalises any .html
        # slug to its extensionless form before a rule is consulted, so a rule
        # retiring an article that is ALSO reachable at .html gets its turn on
        # the second hop, not the first. Two hops, terminating, on a slug that
        # no longer has a page — not worth special-casing article routing for.
        ACCEPTED = {"/articles/tomato-guide-up.html"}

        rules = (repo_root / "frontend" / "_redirects").read_text(encoding="utf-8")
        chains = []
        for line in rules.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) != 3 or not parts[2].startswith("301"):
                continue
            source, target, _status = parts
            # A wildcard source is a pattern, not a URL anyone can request.
            if target.startswith("http") or "*" in source or source in ACCEPTED:
                continue
            first = client.get(source, follow_redirects=False)
            if first.status_code != 301:
                continue
            second = client.get(first.headers["location"], follow_redirects=False)
            if second.status_code in (301, 302, 307, 308):
                chains.append(
                    f"{source} -> {first.headers['location']} -> "
                    f"{second.headers.get('location')}")
        assert not chains, "redirect chains:\n  " + "\n  ".join(chains)
