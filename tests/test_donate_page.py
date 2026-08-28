"""/donate — the public "support this site" page.

Four properties carry the weight here, and all four are honesty properties
rather than formatting ones.

**No VPA is ever invented.** Same rule as /pay: with `KM_UPI_ID` unset the page
must say so and hand out a phone number, never fall back to a guessed
destination that quietly routes a well-wisher's money to a stranger.

**The button's label and its link move together.** A chip reading "₹501 दें"
that opens a ₹101 request is the one bug a money page cannot have, and the two
only stay in sync because each chip carries a finished server-built link rather
than a client-side edit of `&am=`.

**The QR names no amount.** It is scanned off someone else's screen, where a
figure we picked has no business being — so it must carry no `am=` at all and
let the payer's own app ask.

**The page never claims a receipt, a tax exemption, or anything bought.** A
upi:// hand-off reports nothing back, कृषि मित्र is not a registered trust, and
a donation buys no listing or better भाव. Those three sentences are why the page
is not the kind of solicitation a farmer has been taught to distrust; they are
asserted here so an edit cannot quietly drop them.

Everything goes through the real route rather than donate_page() directly: the
shared page shell reads the mandi index for its footer, so calling the function
bare fails on a missing table for reasons that have nothing to do with donating.
"""

import re

import pytest

from backend.routes import donate as donate_mod

VPA = "kunal@okhdfcbank"


@pytest.fixture()
def html(client, monkeypatch):
    """The page as served, with a known VPA. No module reload: upi.vpa() and
    upi.configured() read the environment on every call."""
    monkeypatch.setenv("KM_UPI_ID", VPA)
    monkeypatch.setenv("KM_UPI_NAME", "KrashiMitra")
    r = client.get("/donate")
    assert r.status_code == 200
    return r.text


class TestNoInventedDestination:
    def test_unconfigured_vpa_offers_a_phone_number_not_a_guess(
            self, client, monkeypatch):
        monkeypatch.delenv("KM_UPI_ID", raising=False)
        page = client.get("/donate").text

        assert "upi://pay" not in page
        assert "9870951001" in page

    def test_configured_page_renders_the_real_vpa(self, html):
        assert VPA in html


class TestAmountAndLabelAgree:
    def test_every_chip_ships_a_finished_link_matching_its_own_label(self, html):
        chips = re.findall(r'data-link="([^"]+)"\s+data-btn="([^"]+)"', html)
        assert len(chips) == len(donate_mod._AMOUNTS)

        for link, label in chips:
            # Either both name the same figure, or neither names one.
            assert re.findall(r"am=(\d+)", link) == re.findall(r"₹(\d+)", label)

    def test_exactly_one_chip_carries_no_am_at_all(self, html):
        links = re.findall(r'data-link="([^"]+)"', html)
        assert sum("am=" not in link for link in links) == 1

    def test_the_default_button_href_matches_the_default_chip(self, html):
        href = re.search(r'id="dn-btn" href="([^"]+)"', html).group(1)
        assert f"am={donate_mod._DEFAULT}" in href


def _qr_boxes(html):
    """[(classes, data-amt, svg)] for every QR on the page, in document order."""
    return re.findall(
        r'<div class="dn-qrbox([^"]*)" data-amt="([^"]*)">.*?(<svg.*?</svg>)',
        html, re.S)


class TestTheQrFollowsTheChip:
    def test_there_is_one_qr_per_chip_keyed_the_same_way(self, html):
        chips = re.findall(
            r'<button type="button" class="dn-chip[^"]*" data-amt="([^"]*)"', html)
        assert [amt for _, amt, _ in _qr_boxes(html)] == chips

    def test_exactly_one_qr_is_visible_and_it_is_the_default_chips(self, html):
        visible = [amt for cls, amt, _ in _qr_boxes(html) if "on" in cls]
        assert visible == [str(donate_mod._DEFAULT)]

    def test_each_qr_really_encodes_its_own_chips_link(self, html):
        """The proof that switching chips changes the code, not just the caption.

        A QR is opaque to a string search, so each one is re-encoded here from
        the link its own chip carries and compared byte for byte. A ₹251 chip
        showing the ₹101 code would take the giver's money at the wrong amount
        with nothing on screen to reveal it.
        """
        from backend.services import upi as upi_mod

        links = dict(zip(
            [amt for _, amt, _ in _qr_boxes(html)],
            re.findall(r'data-link="([^"]+)"', html)))
        for _, amt, svg in _qr_boxes(html):
            expected = upi_mod.qr_svg(links[amt].replace("&amp;", "&"))
            assert svg in expected, f"QR for {amt or 'open amount'} is not its own link's"

    def test_the_open_amount_qr_names_no_figure(self, html):
        """It is the code scanned off someone else's screen — a number we picked
        has no business being in it."""
        boxes = _qr_boxes(html)
        open_amount = [amt for _, amt, _ in boxes if amt == ""]
        assert open_amount == [""]

    def test_a_qr_that_will_not_render_does_not_take_the_page_with_it(
            self, client, monkeypatch):
        from backend.services import upi as upi_mod

        monkeypatch.setenv("KM_UPI_ID", VPA)
        monkeypatch.setattr(upi_mod, "qr_svg", lambda *a, **k: "")
        page = client.get("/donate")

        assert page.status_code == 200
        assert not _qr_boxes(page.text)     # no empty frames left behind
        assert 'id="dn-btn"' in page.text   # the real rail is still there
        assert VPA in page.text


class TestTheHonestyClaimsSurvive:
    @pytest.mark.parametrize("claim", [
        "80G",                        # no tax-exemption receipt is offered
        "किसान हैं तो दान मत कीजिए",   # the site is free for the farmer
        "रजिस्टर्ड NGO",               # we are not a registered trust
        "कोई लिस्टिंग",                # a donation buys nothing
        "कोई रसीद नहीं",               # UPI tells us nothing, so we claim nothing
    ])
    def test_claim_is_on_the_page(self, html, claim):
        assert claim in html

    def test_page_never_says_the_money_arrived(self, html):
        for invented_receipt in ("पैसा मिल गया", "पेमेंट हो गया", "भुगतान सफल"):
            assert invented_receipt not in html


class TestItIsAnOrdinaryPageOfTheSite:
    def test_indexable_and_canonical(self, html):
        assert 'rel="canonical" href="https://krashimitra.in/donate"' in html
        assert 'name="robots"' not in html   # /pay is noindex; this one is not

    def test_sitemap_lists_it(self):
        from backend.routes import sitemap
        assert "<loc>https://krashimitra.in/donate</loc>" in sitemap._build()

    def test_netlify_proxies_it_to_the_backend(self, repo_root):
        """Without the _redirects line the page 404s on krashimitra.in while
        answering 200 on Render — exactly how /ganna shipped once already."""
        rules = (repo_root / "frontend" / "_redirects").read_text(encoding="utf-8")
        assert re.search(r"^/donate\s+https://\S+/donate\s+200", rules, re.M)

    def test_it_is_reachable_from_the_shared_footer(self, html):
        assert '/donate">सहयोग करें' in html
