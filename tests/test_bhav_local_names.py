"""The crop and district names /bhav puts in front of a farmer.

Both halves of this file pin the same defect, found in Search Console on
6 Sep 2026: a page that ranks fine but is titled in a script its reader did
not search in.

  • Crop — _hindi_name falls back to the raw Agmarknet string, so 215 of the
    323 commodities that earned an impression were titled in English ("Sugar
    का भाव आज Mumbai मंडी में"). They clicked at 0.54% against 0.74% for the
    crops that had a Hindi name — same template, same positions.

  • District — the title said "Sehore" to everyone. The searchers who typed
    Latin ("sehore mandi lahsun bhav") clicked at 0.97%; the ones who typed
    Devanagari ("सीहोर मंडी लहसुन भाव आज का") clicked at 0.36%, at the same
    average position of 7.7. Two-thirds of the traffic was the second group.

The risk both fixes carry is a WRONG name rather than an English one, which
is why most of what follows is collision tests: the keyword scan and the
district fold are both deliberately loose, and each has already produced a
confidently mislabelled page once (Turnip → अरहर).
"""

from datetime import date

import pytest

from backend.routes.bhav import (_dist_hi_map, _dist_key, _hindi_district,
                                 _hindi_name, _title_names)


class TestCropNames:
    @pytest.mark.parametrize("commodity,hindi", [
        ("Sugar", "चीनी"),
        ("Khandsari(Desi Khand)", "खांडसारी (देसी खांड)"),
        ("Mentha Oil", "मेंथा तेल"),
        ("Guar", "ग्वार"),
        ("Cucumbar(Kheera)", "खीरा"),
        ("Gur(Jaggery)", "गुड़"),
        ("Ragi (Finger Millet)", "रागी"),
        ("Makhana(Foxnut)", "मखाना"),
        ("Pointed gourd (Parval)", "परवल"),
        ("Amla(Nelli Kai)", "आंवला"),
        ("Cummin Seed(Jeera)", "जीरा"),
        ("Arecanut(Betelnut/Supari)", "सुपारी"),
    ])
    def test_named(self, commodity, hindi):
        assert _hindi_name(commodity) == hindi

    @pytest.mark.parametrize("commodity,hindi", [
        # Every pair here is a keyword that sits inside another commodity's
        # name. The specific entry has to be inserted BEFORE the general one,
        # because the fallback scan returns the first match it finds.
        ("Sugarcane", "गन्ना"),                       # not चीनी
        ("Sugar Beet", "चुकंदर"),                     # not चीनी
        ("Guar Seed(Cluster Beans Seed)", "ग्वार बीज"),  # not ग्वार, not सेम
        ("Elephant Yam (Suran)", "सूरन (जिमीकंद)"),   # not रतालू
        ("Methi Seeds", "मेथी दाना"),                  # not मेथी
        ("French Beans (Frasbean)", "फ्रेंच बीन्स"),   # not सेम
        ("Firewood", "जलाऊ लकड़ी"),                    # not लकड़ी
        # and the ones an earlier round of this same bug produced
        ("Turnip", "शलजम"),
        ("Peach", "आड़ू"),
        ("Mustard Oil", "सरसों तेल"),
        ("Wheat Atta", "गेहूं आटा"),
        ("Mousambi(Sweet Lime)", "मौसंबी"),
    ])
    def test_no_collision(self, commodity, hindi):
        assert _hindi_name(commodity) == hindi

    def test_unknown_crop_keeps_english_and_collapses(self):
        """No invented names: an unmapped crop stays English, and _title_names
        collapses both slots so the template cannot print it twice."""
        assert _hindi_name("Zzz Unknown Crop") == "Zzz Unknown Crop"
        hi, en, same = _title_names("Zzz Unknown Crop")
        assert same and hi == en


class TestDistrictNames:
    def test_state_scoped(self):
        """Sehore is Madhya Pradesh's; asking UP for it must not answer सीहोर."""
        assert _hindi_district("Madhya Pradesh", "Sehore") == "सीहोर"
        assert _hindi_district("Uttar Pradesh", "Sehore") == "Sehore"

    def test_shared_name_resolves_in_both_states(self):
        for state in ("Chattisgarh", "Himachal Pradesh"):
            assert _hindi_district(state, "Bilaspur") == "बिलासपुर"

    @pytest.mark.parametrize("state,district,hindi", [
        ("Rajasthan", "Jaipur", "जयपुर"),
        ("Maharashtra", "Mumbai", "मुंबई"),
        ("Uttar Pradesh", "Agra", "आगरा"),
        ("Uttar Pradesh", "Shahjahanpur", "शाहजहांपुर"),
        # Agmarknet's own spellings, reached by the fold
        ("Uttar Pradesh", "Pillibhit", "पीलीभीत"),
        ("Uttar Pradesh", "Bulandshahar", "बुलंदशहर"),
        # and by the alias table, where the fold cannot reach
        ("Haryana", "Gurgaon", "गुरुग्राम"),
        ("Uttar Pradesh", "Kanpur", "कानपुर"),
        ("Bihar", "Chhapra", "छपरा"),
    ])
    def test_resolves(self, state, district, hindi):
        assert _hindi_district(state, district) == hindi

    def test_unknown_district_keeps_latin(self):
        """The fallback is the name the page printed yesterday, never a guess."""
        assert _hindi_district("Uttar Pradesh", "Nowhereabad") == "Nowhereabad"
        assert _hindi_district("Atlantis", "Jaipur") == "Jaipur"

    def test_no_ambiguous_key_survives(self):
        """The fold is loose enough that two districts in one state can land on
        one key. Those are dropped when the map is built — if one ever leaks
        through, some district silently gets its neighbour's name."""
        seen = {}
        for (state, key), hindi in _dist_hi_map().items():
            assert (state, key) not in seen or seen[(state, key)] == hindi
            seen[(state, key)] = hindi
        assert len(_dist_hi_map()) > 700, "district map failed to load"

    def test_fold_is_spelling_insensitive(self):
        assert _dist_key("Pillibhit") == _dist_key("Pilibhit")
        assert _dist_key("Khiri (Lakhimpur)") == _dist_key("Khiri")


@pytest.fixture(scope="module")
def seeded(request):
    """One crop in one district, indexed — enough to render both page types."""
    from backend.database.db import MandiLastSeen, SessionLocal
    from backend.routes import bhav

    db = SessionLocal()
    row = MandiLastSeen(
        group_key="test-localnames-garlic-mp-sehore",
        commodity="Garlic", state="Madhya Pradesh", district="Sehore",
        market="Sehore", min_price="4000", max_price="6000", modal_price="5000",
        arrival_date="04/09/2026", arrival_dt=date(2026, 9, 4))
    db.add(row)
    db.commit()
    bhav._index, bhav._index_ts = {}, 0.0
    bhav._get_index()

    def _cleanup():
        db.delete(row)
        db.commit()
        db.close()
        bhav._index, bhav._index_ts = {}, 0.0

    request.addfinalizer(_cleanup)


class TestRenderedTitles:
    """Both spellings have to survive into the actual <title>, because both
    are real queries — this is the whole point of the change."""

    def test_district_page_title_carries_both_scripts(self, client, seeded):
        html = client.get("/bhav/garlic/madhya-pradesh/sehore").text
        title = html.split("<title>")[1].split("</title>")[0]
        assert "सीहोर" in title, title
        assert "Sehore" in title, title
        assert "लहसुन" in title, title

    def test_district_page_speaks_hindi_in_the_body(self, client, seeded):
        html = client.get("/bhav/garlic/madhya-pradesh/sehore").text
        h1 = html.split("<h1>")[1].split("</h1>")[0]
        assert "सीहोर" in h1 and "Sehore" not in h1, h1

    def test_place_hub_title_carries_both_scripts(self, client, seeded):
        html = client.get("/bhav/rajya/madhya-pradesh/sehore").text
        title = html.split("<title>")[1].split("</title>")[0]
        assert "सीहोर" in title and "Sehore" in title, title

    @pytest.mark.parametrize("url,hindi,latin", [
        ("/naksha/assam", "असम", "Assam Map"),
        ("/naksha/gujarat", "गुजरात", "Gujarat Map"),
        ("/naksha/gujarat/ahmedabad", "अहमदाबाद", "Ahmedabad District Map"),
        ("/naksha/madhya-pradesh/bhopal", "भोपाल", "Bhopal District Map"),
    ])
    def test_map_titles_carry_both_scripts(self, client, url, hindi, latin):
        """The mirror of the same defect: these titles were 100% Devanagari
        while "assam map" and "ahmedabad map" — the queries they rank 3rd and
        5th for — are Latin, and took no clicks at all."""
        html = client.get(url).text
        title = html.split("<title>")[1].split("</title>")[0]
        assert hindi in title, title
        assert latin in title, title
        assert len(title) <= 68, f"{len(title)} chars: {title}"

    def test_snippet_as_a_whole_names_both_spellings(self, client, seeded):
        """Roughly a third of titles are too long to hold both spellings; on
        those the description has to carry the Latin one, or the searchers who
        type "sehore mandi lahsun bhav" lose the only word they'd recognise."""
        html = client.get("/bhav/garlic/madhya-pradesh/sehore").text
        title = html.split("<title>")[1].split("</title>")[0]
        desc = html.split('name="description" content="')[1].split('"')[0]
        snippet = f"{title} {desc}"
        assert "सीहोर" in snippet, snippet
        assert "Sehore" in snippet, snippet
