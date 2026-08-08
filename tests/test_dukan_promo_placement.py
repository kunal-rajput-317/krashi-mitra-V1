"""Where the दुकान promo sits on a /bhav page, and how often.

The block is the site's only supply-side ask — the one thing on the price tree
that is addressed to a shopkeeper rather than a farmer — so its position is a
business decision, not styling. It goes directly under the MSP card: the farmer
has just read today's rate, and the question that follows a price is "खाद-बीज
कहां से लूं?". Down by the footer, where it used to live, it was below the fold
on a phone and 98% of this traffic is a phone.

Two things break silently and are asserted here:

* **It stops appearing on a tier.** Every tier calls `_dukan_pitch()` from its
  own template string; a tier that loses the call still renders a perfectly
  good page, and nothing else in the suite would notice.
* **It appears twice.** Tier 3 has a second caller — `_dealer_teaser_html()`
  used to fall back to the same block when a state had no paying dealer — so
  the duplicate only showed on the states that had not sold yet, which is
  exactly where nobody was looking.
"""

import pytest

from backend.routes import bhav
from backend.services import buyers

# The rendered promo, and the MSP card it must follow.
PROMO = 'class="kmdp"'
MSP = 'class="msp-box'
FAQ = "अक्सर पूछे जाने वाले सवाल"

TIERS = [
    pytest.param("/bhav/wheat", id="tier2-crop"),
    pytest.param("/bhav/wheat/up", id="tier3-crop-state"),
    pytest.param("/bhav/wheat/up/hardoi", id="tier4-district"),
]


@pytest.fixture()
def priced(monkeypatch):
    """A one-district index, with Krashi Bazar and the dealer list both empty.

    Empty on purpose: an empty state is the case where the promo used to render
    a second time.
    """
    monkeypatch.setattr(bhav, "_index", {
        "crops": {"wheat": "Wheat"},
        "states": {"wheat": {"up": "Uttar Pradesh"}},
        "dists": {"wheat": {"up": {"hardoi": "Hardoi"}}},
        "dates": {"wheat": {"up": {"hardoi": "2026-08-05"}}},
    })
    monkeypatch.setattr(bhav, "_index_ts", float("inf"))
    monkeypatch.setattr(bhav, "_kharidar_places", lambda: set())
    monkeypatch.setattr(bhav, "_bazar_slice", lambda *a, **k: [])
    monkeypatch.setattr(bhav, "_sell_intent", lambda *a, **k: 0)
    monkeypatch.setattr(buyers, "for_bhav_panel", lambda *a, **k: [])
    yield


class TestPromoSitsUnderTheMSPCard:
    @pytest.mark.parametrize("url", TIERS)
    def test_every_tier_carries_it(self, priced, client, url):
        assert PROMO in client.get(url).text

    @pytest.mark.parametrize("url", TIERS)
    def test_exactly_once(self, priced, client, url):
        """A second copy is the failure mode nobody sees: it needs an empty
        state to show up, and an empty state is what a new crop always is."""
        assert client.get(url).text.count(PROMO) == 1

    @pytest.mark.parametrize("url", TIERS)
    def test_directly_below_the_msp_price(self, priced, client, url):
        body = client.get(url).text
        assert MSP in body, "wheat lost its MSP card — this test proves nothing now"
        assert body.index(MSP) < body.index(PROMO), "promo rendered above the MSP card"
        # Nothing but the MSP card between the two: anything that lands in the
        # gap has pushed the ask back down the page.
        gap = body[body.index(MSP):body.index(PROMO)]
        assert gap.count("<section") <= 1, "a block wedged in between MSP and the promo"

    @pytest.mark.parametrize("url", TIERS)
    def test_stays_above_the_faq(self, priced, client, url):
        """It used to sit next to the FAQ, near the footer — below the fold on
        every phone."""
        body = client.get(url).text
        if FAQ in body:
            assert body.index(PROMO) < body.index(FAQ)


class TestPromoCopy:
    def test_names_the_district_it_is_shown_on(self, priced, client):
        """"Hardoi के किसान" beats "हजारों किसान": a trader recognises his own
        district, and that recognition is the whole click."""
        assert "Hardoi के किसान" in client.get("/bhav/wheat/up/hardoi").text

    def test_asks_for_the_shop_not_the_product(self, priced, client):
        body = client.get("/bhav/wheat/up").text
        assert "अपनी दुकान किसानों तक पहुंचाएं" in body
        assert "अपनी दुकान लिस्ट करें" in body

    def test_carries_the_price_so_nobody_clicks_to_find_it(self, priced, client):
        """Both halves of the metered rate, read from the rate card rather than
        typed in — the last time these were hardcoded, every one of them broke
        on the first reprice and taught nothing."""
        from backend.services import placements

        body = client.get("/bhav/wheat").text
        assert f"₹{placements.PRICE_DISTRICT}" in body
        assert f"₹{placements.PRICE_CROP}" in body

    def test_sample_card_photo_is_a_file_that_exists(self, priced, client):
        """A missing static file on this site answers 200 with HTML, so a
        broken path here would fail silently on ~10,000 pages — nothing would
        404, the card would just render empty. Assert the file, not the tag."""
        from pathlib import Path

        body = client.get("/bhav/wheat/up").text
        src = "/images/seeds/wheat-seed-hd2967-card.webp"
        assert f'src="{src}"' in body
        on_disk = Path(__file__).resolve().parents[1] / "frontend" / src.lstrip("/")
        assert on_disk.is_file(), f"{src} is referenced but not committed"
        assert on_disk.read_bytes()[:4] == b"RIFF", "not a real WebP"
