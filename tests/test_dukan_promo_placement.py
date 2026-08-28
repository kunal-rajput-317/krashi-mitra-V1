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


# ── The same block on the articles ─────────────────────────────────────────
#
# An article earns the promo on the /bhav test, not on traffic: has the reader
# just been told he needs to BUY something? So it goes on pest, disease,
# fertiliser, seed, weed and crop-guide pages and stays off schemes, livestock,
# forestry and the selling side. The two ways that goes wrong are both silent —
# the block quietly stops being emitted, or it turns up on a page it argues
# with — so both are asserted here.

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

PLACEHOLDER = "<div data-dukan-promo></div>"
PROMO_JS = '<script src="../dukan-promo.js" defer></script>'


def _articles():
    """(ARTICLE dict, built html path) for every content module."""
    import article_builder as ab

    out = []
    for f in sorted((REPO / "tools" / "articles").glob("*.py")):
        if f.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f.stem, f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out.append((mod.ARTICLE, ab.ARTICLES / f"{mod.ARTICLE['slug']}.html"))
    return out


class TestArticlePromoSelection:
    def test_the_promo_reaches_a_real_number_of_articles(self):
        """A rule that silently matches nothing still passes every other test
        here — the pages just quietly stop carrying the site's only
        supply-side ask."""
        import article_builder as ab

        picked = [a for a, _ in _articles() if ab.wants_dukan_promo(a)]
        assert len(picked) >= 30, f"only {len(picked)} articles carry the promo"

    def test_never_on_a_page_written_in_another_language(self):
        """dukan-promo.js ships one hardcoded Hindi string set, and
        /dukanlisting behind its button is Hindi-only. An untranslated ad on a
        Kannada or Tamil page undoes the reason those pages were rewritten."""
        import article_builder as ab

        for a, _ in _articles():
            if a.get("lang", "hi") != "hi":
                assert not ab.wants_dukan_promo(a), a["slug"]

    def test_never_where_it_argues_with_the_article(self):
        """A सरकारी योजना reader wants a subsidy; a पशुपालन reader wants a vet;
        पेड़ व वानिकी is a ten-year cycle; मंडी और बिक्री is the opposite trade;
        and जैविक व प्राकृतिक खेती tells him to make his inputs at home."""
        import article_builder as ab

        banned = {"सरकारी योजना", "पशुपालन", "पेड़ व वानिकी",
                  "मंडी और बिक्री", "जैविक व प्राकृतिक खेती"}
        for a, _ in _articles():
            if a.get("section") in banned:
                assert not ab.wants_dukan_promo(a), a["slug"]


class TestArticlePromoIsActuallyOnDisk:
    def test_every_selected_article_carries_the_block_exactly_once(self):
        """Built pages, not the render function: the selection can be right
        while the pages on disk were never rebuilt, and it is the files that
        ship."""
        import article_builder as ab

        for a, page in _articles():
            if not (ab.wants_dukan_promo(a) and page.is_file()):
                continue
            doc = page.read_text(encoding="utf-8")
            assert doc.count(PLACEHOLDER) == 1, a["slug"]
            assert doc.count(PROMO_JS) == 1, a["slug"]

    def test_unselected_articles_carry_neither(self):
        import article_builder as ab

        for a, page in _articles():
            if ab.wants_dukan_promo(a) or not page.is_file():
                continue
            doc = page.read_text(encoding="utf-8")
            assert PLACEHOLDER not in doc, a["slug"]
            assert "dukan-promo.js" not in doc, a["slug"]

    def test_the_block_sits_between_the_advice_and_the_faq(self):
        """Same reasoning as the /bhav placement: "कहां से लूं?" occurs to the
        reader when the article has just told him what he needs, not after a
        FAQ he may never reach."""
        import article_builder as ab

        checked = 0
        for a, page in _articles():
            if not (ab.wants_dukan_promo(a) and page.is_file()):
                continue
            doc = page.read_text(encoding="utf-8")
            faq = doc.find(a.get("faq_h2", "अक्सर पूछे जाने वाले सवाल"))
            assert 0 < doc.find(PLACEHOLDER) < faq, a["slug"]
            checked += 1
        assert checked, "no built promo articles were checked"

    def test_the_script_it_loads_is_committed(self):
        """A missing static file answers 200 with HTML on this site, so a bad
        path would leave an empty placeholder on 40 pages and 404 nowhere."""
        js = REPO / "frontend" / "dukan-promo.js"
        assert js.is_file()
        assert "data-dukan-promo" in js.read_text(encoding="utf-8")
