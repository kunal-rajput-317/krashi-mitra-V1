"""The खरीदार directory's index gate, in both directions.

`_has_kharidar()` is deliberately the single source of truth for two separate
decisions: whether `/bhav/.../kharidar` ships `noindex`, and whether it appears
in `/bhav/sitemap.xml`. Wiring both to one function means they cannot disagree
by construction — but nothing exercised that, because `buyers.json` ships with
one `active:false` example row, so the seeded branch has never actually run.

The half everybody remembers is "empty districts must not be indexed". The half
that decides whether the directory earns anything is the reverse: the day a
dealer is seeded, that district has to *become* discoverable. A silent failure
there looks exactly like success — the page renders, the dealer is on it, and
Google is never told it exists.
"""

import json

import pytest

from backend.routes import bhav
from backend.services import buyers

SEEDED = ("wheat", "up", "hardoi")          # gets a live dealer
EMPTY = ("wheat", "up", "sitapur")          # deliberately left bare


def _index() -> dict:
    """A two-district index, matching the shape `_get_index()` returns."""
    return {
        "crops": {"wheat": "Wheat"},
        "states": {"wheat": {"up": "Uttar Pradesh"}},
        "dists": {"wheat": {"up": {"hardoi": "Hardoi", "sitapur": "Sitapur"}}},
        "dates": {"wheat": {"up": {"hardoi": "2026-07-30", "sitapur": "2026-07-30"}}},
    }


def _dealer(district: str) -> dict:
    return {
        "id": f"test-{district.lower()}",
        "active": True,
        "name": "Test Traders",
        "kind": "trader",
        "state": "Uttar Pradesh",
        "district": district,
        "commodities": [],          # buys everything
        "phone": "9876543210",
        "verified": True,
    }


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    """One live dealer in Hardoi and nothing in Sitapur.

    Points `buyers._PATH` at a temp file rather than editing the real
    `data/buyers.json`, and clears the mtime cache on both sides so the module
    re-reads it. Krashi Bazar is stubbed empty so the assertions below are
    about the *dealer* branch of `_has_kharidar()` and nothing else.
    """
    path = tmp_path / "buyers.json"
    path.write_text(json.dumps({"buyers": [_dealer("Hardoi")]}), encoding="utf-8")

    monkeypatch.setattr(buyers, "_PATH", path)
    monkeypatch.setattr(buyers, "_cache", None)
    monkeypatch.setattr(buyers, "_mtime", -1.0)
    monkeypatch.setattr(buyers, "_place_idx", {})

    monkeypatch.setattr(bhav, "_index", _index())
    monkeypatch.setattr(bhav, "_index_ts", float("inf"))
    monkeypatch.setattr(bhav, "_kharidar_places", lambda: set())
    monkeypatch.setattr(bhav, "_bazar_slice", lambda *a, **k: [])
    monkeypatch.setattr(bhav, "_sell_intent", lambda *a, **k: 0)
    yield


def _url(combo: tuple) -> str:
    return "/bhav/{}/{}/{}/kharidar".format(*combo)


class TestSeededDistrictBecomesDiscoverable:
    """The direction that has never run in production."""

    def test_gate_opens_for_the_seeded_district(self, seeded):
        assert bhav._has_kharidar("wheat", "Uttar Pradesh", "Hardoi") is True

    def test_kharidar_url_enters_the_sitemap(self, seeded, client):
        body = client.get("/bhav/sitemap.xml").text
        assert f"{bhav.SITE}{_url(SEEDED)}</loc>" in body

    def test_seeded_page_is_indexable(self, seeded, client):
        response = client.get(_url(SEEDED))
        assert response.status_code == 200
        assert "noindex" not in response.text

    def test_seeded_page_shows_the_dealer(self, seeded, client):
        assert "Test Traders" in client.get(_url(SEEDED)).text


class TestEmptyDistrictStaysOut:
    """The guard that keeps a 14k-page surface from becoming 14k thin pages."""

    def test_gate_stays_shut(self, seeded):
        assert bhav._has_kharidar("wheat", "Uttar Pradesh", "Sitapur") is False

    def test_empty_url_is_absent_from_the_sitemap(self, seeded, client):
        assert _url(EMPTY) not in client.get("/bhav/sitemap.xml").text

    def test_empty_page_still_renders_but_noindex(self, seeded, client):
        """It must render: a dealer has to be able to see the page he'd join."""
        response = client.get(_url(EMPTY))
        assert response.status_code == 200
        assert '<meta name="robots" content="noindex,follow">' in response.text


class TestSitemapAndRobotsCannotDisagree:
    def test_every_kharidar_url_in_the_sitemap_is_indexable(self, seeded, client):
        """The invariant both callers of `_has_kharidar()` exist to preserve.

        Asserted over the rendered sitemap rather than the helper, because a
        future refactor that inlines the gate on one side only would still pass
        a helper-level test.
        """
        import re

        listed = re.findall(rf"{re.escape(bhav.SITE)}(/bhav/\S+?/kharidar)</loc>",
                            client.get("/bhav/sitemap.xml").text)
        assert listed, "sitemap advertised no kharidar URLs — fixture did not seed"
        for path in listed:
            assert "noindex" not in client.get(path).text, \
                f"{path} is in the sitemap but renders noindex"


class TestSellIntentIsWiredIntoTheKharidarPage:
    """The other half of the page: "who will buy it" AND "I have it".

    The खरीदार page is the one place where a farmer's sell intent *is* the
    product — a dealer pays because there is a queue of sellers behind the
    listing. So the appeal panel has to be on this page, not only on the price
    page, and it has to know it is here (`here=True`), or the confirmation
    offers a link to the page the farmer is already standing on.
    """

    def test_panel_is_present_on_an_empty_district(self, seeded, client):
        """Especially here: an empty directory has nothing else to collect."""
        body = client.get(_url(EMPTY)).text
        assert 'id="ap-ov"' in body, "appeal panel missing from the kharidar page"
        assert "openCropAppeal()" in body, "nothing opens the appeal panel"

    def test_panel_knows_it_is_on_the_kharidar_page(self, seeded, client):
        assert '"here": true' in client.get(_url(SEEDED)).text

    def test_price_page_panel_does_not_claim_to_be_here(self, seeded, client):
        """Same helper, other caller — the flag must actually vary."""
        assert '"here": false' in client.get("/bhav/wheat/up/hardoi").text

    def test_empty_district_does_not_promise_buyers_it_lacks(self, seeded, client):
        """An honest empty state. Promising a farmer his crop goes in front of
        buyers who are not there is the one thing this page must not do."""
        body = client.get(_url(EMPTY)).text
        assert "खरीदार जुड़ते ही" in body

    def test_sell_intent_count_renders_when_appeals_exist(self, seeded, client,
                                                          monkeypatch):
        """The number the directory is actually sold on."""
        monkeypatch.setattr(bhav, "_sell_intent", lambda *a, **k: 14)
        assert "14 किसानों" in client.get(_url(SEEDED)).text

    def test_sell_intent_line_is_absent_at_zero(self, seeded, client):
        """`0 किसानों ने ... कहा है` is worse than saying nothing."""
        assert "0 किसानों" not in client.get(_url(SEEDED)).text


class TestDealerAcquisitionRoute:
    """The supply side: a trader who lands on a district page must be able to
    get himself listed. Both doors are asserted because they fail differently —
    the form can 404 after a rename, the WhatsApp number can go stale."""

    def test_empty_district_still_pitches_the_dealer(self, seeded, client):
        """Most important here: an empty page's only job is recruiting supply."""
        body = client.get(_url(EMPTY)).text
        assert "/dukan" in body, "no signup link on the page that needs it most"
        assert "wa.me/919870951001" in body

    def test_seeded_district_pitches_too(self, seeded, client):
        """A competitor already being listed is the strongest pitch there is."""
        assert "/dukan" in client.get(_url(SEEDED)).text

    def test_dukan_page_exists_and_is_wired_into_the_sitemap(self, client, repo_root):
        """Guards the whole chain: file present, redirect rule, sitemap entry.
        A link to a page Netlify does not serve is worse than no link."""
        assert (repo_root / "frontend" / "dukan.html").is_file()
        redirects = (repo_root / "frontend" / "_redirects").read_text(encoding="utf-8")
        assert "/dukan.html" in redirects, "no .html→/dukan canonical redirect"
        assert f"{bhav.SITE}/dukan</loc>" in client.get("/sitemap.xml").text

    def test_dukan_form_posts_to_a_route_that_exists(self, repo_root, client):
        """The form's endpoint is a string in HTML — nothing else type-checks it."""
        page = (repo_root / "frontend" / "dukan.html").read_text(encoding="utf-8")
        assert "/dukan/signup" in page
        # 422 (bad body), not 404 (no such route). Either proves it is registered.
        assert client.post("/dukan/signup", json={}).status_code != 404


class TestUnseededRepoDefault:
    """No fixture: this is the shipped `data/buyers.json` as it stands today."""

    def test_directory_is_dormant_until_a_dealer_is_seeded(self):
        assert buyers.live_places() == set(), (
            "buyers.json has a live row — if that is intentional, this test "
            "should be updated to name the seeded district")
