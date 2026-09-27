"""Kitchen staples on /bhav show the mandi price per kilo, labelled as a
wholesale approximation.

Households and shopkeepers search "chini ka rate" and think in ₹ per kilo;
the page answered in ₹ per quintal only. The kilo figure is the same mandi
number divided by 100. It must never read as a shop price, so it always
says थोक and लगभग, and says the shop price differs.
"""

from backend.routes import bhav


def test_per_kilo_is_the_quintal_price_over_100():
    assert bhav._per_kilo(5550) == "₹55.50"
    assert bhav._per_kilo(1450) == "₹14.50"


def test_line_only_for_staples_with_a_price():
    assert "प्रति किलो" in bhav._kilo_line("sugar", 5550)
    assert bhav._kilo_line("wheat", 2550) == "", "a farmer's crop keeps ₹/quintal only"
    assert bhav._kilo_line("sugar", None) == ""


def test_line_is_labelled_wholesale_and_approximate():
    line = bhav._kilo_line("onion", 1450)
    assert "थोक" in line and "लगभग" in line
    assert "खुदरा दाम इससे अलग" in line


def test_faq_answer_carries_both_units_and_the_caveat():
    [(q, a)] = bhav._kilo_faqs("sugar", "चीनी", "जयपुर", "24 सितंबर 2026", 5550)
    assert "1 किलो" in q
    assert "₹5,550 प्रति क्विंटल" in a and "₹55.50 प्रति किलो" in a
    assert "खुदरा दाम इससे अलग" in a


def test_no_faq_for_other_crops():
    assert bhav._kilo_faqs("wheat", "गेहूं", "आगरा", "24 सितंबर 2026", 2550) == []


def test_every_staple_slug_is_a_real_slug_shape():
    """Slugs, not display names: lowercase, hyphenated, as the URL has them."""
    for cs in bhav._KITCHEN_STAPLES:
        assert cs == cs.lower() and " " not in cs
