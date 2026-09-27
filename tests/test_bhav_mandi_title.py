"""Mandi names in the /bhav <title> (bhav._title_mandis, bhav._with_mandis).

Farmers search a mandi by its own name ("tundla mandi mein sarson ka bhav"),
and many mandis are not named after their district. Search Console for the
four weeks to 23 Sep 2026 showed those searches reaching our district pages,
some at position 1-3, with almost no clicks: the title named the district
and never the mandi. The fix adds the district's other mandis to the title
where there is room, as a trial behind bhav.MANDI_IN_TITLE.

What must hold, whatever the trial's result:
  • a title only ever GAINS a mandi name; it never loses a word to make room,
    and never grows past the 68-character SERP budget it already met;
  • switched off, every title is exactly what it was before;
  • no "APMC" or similar feed jargon reaches the title, so the page never
    reads like the mandi's own website (LEGAL_RULES §1, not the government).
"""

from datetime import date, datetime

import pytest

from backend.routes import bhav


def _rows(*markets):
    return [{"market": m} for m in markets]


class TestTitleMandis:
    def test_feed_jargon_is_stripped(self):
        assert bhav._title_mandis(_rows("Tundla APMC"), "Firozabad") == ["Tundla"]
        assert bhav._title_mandis(_rows("Barwala(Hisar) APMC"), "Hissar") == ["Barwala"]
        assert bhav._title_mandis(_rows("Vaniyamkulam VFPCK"), "Palakad") == ["Vaniyamkulam"]
        assert bhav._title_mandis(_rows("Mettupalayam(Uzhavar Sandhai )"),
                                  "Coimbatore") == ["Mettupalayam"]

    @pytest.mark.parametrize("market,district", [
        ("Aligarh APMC", "Aligarh"),
        ("Pilibhit APMC", "Pillibhit"),      # the feed's two spellings of one place
        ("Lashkar Gwalior", "Gwalior"),
        ("Kannauj APMC", "Kannuj"),
        ("Devariya APMC", "Deoria"),
        ("Bijnaur APMC", "Bijnor"),
        ("Tiruvallur(Uzhavar Sandhai )", "Thiruvellore"),
    ])
    def test_mandi_named_after_its_district_is_left_out(self, market, district):
        assert bhav._title_mandis(_rows(market), district) == []

    @pytest.mark.parametrize("market,district,name", [
        ("Baraut APMC", "Baghpat", "Baraut"),
        ("Jarar APMC", "Agra", "Jarar"),
        ("Khair APMC", "Aligarh", "Khair"),
    ])
    def test_a_different_place_with_a_similar_name_is_kept(self, market, district, name):
        assert bhav._title_mandis(_rows(market), district) == [name]

    def test_busiest_first_then_alphabetical(self):
        rows = _rows("Khair APMC", "Charra APMC", "Charra APMC", "Atrauli APMC",
                     "Aligarh APMC", "Aligarh APMC", "Aligarh APMC")
        assert bhav._title_mandis(rows, "Aligarh") == ["Charra", "Atrauli"]

    def test_two_spellings_of_one_mandi_count_once(self):
        rows = _rows("Manawar APMC", "Manawar(F&V) APMC", "Kukshi APMC")
        assert bhav._title_mandis(rows, "Dhar") == ["Manawar", "Kukshi"]

    def test_row_order_does_not_change_the_answer(self):
        a = _rows("Tilhar APMC", "Powayan APMC", "Jalalabad APMC")
        assert bhav._title_mandis(a, "Shahjahanpur") == \
               bhav._title_mandis(list(reversed(a)), "Shahjahanpur")

    def test_switched_off_names_nothing(self, monkeypatch):
        monkeypatch.setattr(bhav, "MANDI_IN_TITLE", False)
        assert bhav._title_mandis(_rows("Tundla APMC"), "Firozabad") == []


class TestWithMandis:
    VARIANTS = [
        "सरसों का भाव आज फिरोजाबाद मंडी में — Mustard Price Firozabad",
        "सरसों का भाव आज फिरोजाबाद मंडी में — Mustard Price Today",
        "फिरोजाबाद में सरसों भाव — Mustard",
    ]

    def test_name_goes_beside_the_latin_district(self):
        assert bhav._fit(*bhav._with_mandis(self.VARIANTS, "Firozabad", ["Tundla"])) == \
               "सरसों का भाव आज फिरोजाबाद मंडी में — Mustard Price Firozabad, Tundla"

    @pytest.mark.parametrize("names", [["Tundla"], ["Tundla", "Shikohabad"],
                                       ["Averyveryverylongmandiname", "Another"]])
    def test_title_only_ever_gains(self, names):
        """Whatever fits, the new title is the old one with ", <mandis>" put in
        after the district, or the old one unchanged."""
        for cut in range(len(self.VARIANTS)):
            old_list = self.VARIANTS[cut:]
            old = bhav._fit(*old_list)
            new = bhav._fit(*bhav._with_mandis(old_list, "Firozabad", names))
            assert len(new) <= 68 or new == old
            if new != old:
                i = old.index("Firozabad") + len("Firozabad")
                added = new[i:len(new) - len(old[i:])]
                assert new[:i] == old[:i] and new.endswith(old[i:])
                assert added in {", " + ", ".join(names[:k]) for k in (1, 2)}

    def test_no_latin_district_no_copy(self):
        v = ["फिरोजाबाद मंडी भाव आज — सभी फसलों के ताजा रेट"]
        assert bhav._with_mandis(v, "Firozabad", ["Tundla"]) == v

    def test_whole_word_only(self):
        """Bhindi (okra) must not be taken for Bhind (the district)."""
        v = ["भिंडी का भाव आज भिंड मंडी में — Bhindi Price Bhind"]
        assert bhav._fit(*bhav._with_mandis(v, "Bhind", ["Alampur"])) == \
               "भिंडी का भाव आज भिंड मंडी में — Bhindi Price Bhind, Alampur"

    def test_district_called_mandi(self):
        """Himachal's Mandi district: the name goes after the district, not
        after the word "Mandi" that follows it."""
        v = ["मंडी मंडी भाव आज — Mandi Mandi Bhav 2026"]
        assert bhav._fit(*bhav._with_mandis(v, "Mandi", ["Sundarnagar"])) == \
               "मंडी मंडी भाव आज — Mandi, Sundarnagar Mandi Bhav 2026"

    def test_nothing_to_add_changes_nothing(self):
        assert bhav._with_mandis(self.VARIANTS, "Firozabad", []) == self.VARIANTS


# ── the rendered pages ───────────────────────────────────────

STATE = "Uttar Pradesh"


@pytest.fixture()
def seed(db_session):
    """Snapshot rows for one district: one mandi named after it and one not."""
    from backend.database.db import MandiPrice
    made = []

    def go(district: str, markets: list[str]) -> None:
        for mkt in markets:
            row = MandiPrice(
                state=STATE, district=district, market=mkt,
                commodity="Wheat", variety="Dara", grade="FAQ",
                min_price="2500", max_price="2600", modal_price="2550",
                arrival_date=date.today().strftime("%d/%m/%Y"),
                fetched_at=datetime.utcnow())
            db_session.add(row)
            made.append(row)
        db_session.commit()
        bhav._index, bhav._index_ts = {}, 0.0
        bhav._board_cache.clear()

    yield go
    for row in made:
        db_session.delete(row)
    db_session.commit()
    bhav._index, bhav._index_ts = {}, 0.0
    bhav._board_cache.clear()


def _title(html: str) -> str:
    import re
    return re.search(r"<title>([^<]*)</title>", html).group(1)


class TestPages:
    def test_crop_page_names_the_other_mandi(self, seed, client):
        seed("Tundlaxpur", ["Tundlaxpur APMC", "Khairgarh APMC"])
        title = _title(client.get("/bhav/wheat/uttar-pradesh/tundlaxpur").text)
        assert "Tundlaxpur, Khairgarh" in title
        assert len(title) <= 68
        assert "APMC" not in title

    def test_district_board_names_the_other_mandi(self, seed, client):
        seed("Boardxpur", ["Boardxpur APMC", "Charragarh APMC"])
        title = _title(client.get("/bhav/rajya/uttar-pradesh/boardxpur").text)
        assert "Charragarh" in title and len(title) <= 68
        assert "APMC" not in title

    def test_switched_off_is_the_old_title(self, seed, client, monkeypatch):
        monkeypatch.setattr(bhav, "MANDI_IN_TITLE", False)
        seed("Offxpur", ["Offxpur APMC", "Khairgarh APMC"])
        title = _title(client.get("/bhav/wheat/uttar-pradesh/offxpur").text)
        assert "Khairgarh" not in title
