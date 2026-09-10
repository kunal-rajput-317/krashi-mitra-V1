"""Per-state page language for /bhav — Marathi on Maharashtra pages.

The change is worth nothing if it cannot be trusted not to leak, so four things
have to hold and each is a class below.

SILENCE IS THE FALLBACK, ALWAYS. A missing file, a corrupt file, an unknown
state, an untranslated crop or a typo'd placeholder must all resolve to the
Hindi the caller already built. The whole design bets that being silent in
Marathi costs a click while being wrong in Marathi costs the farmer's trust in
the number too — so nothing here may ever invent, and nothing may raise.

DEVANAGARI ONLY, ENFORCED. Expanding /bhav into more languages was rejected on
evidence that no query used a non-Devanagari Indic script. Marathi slips that
net because it IS Devanagari. A Tamil or Kannada block added to the JSON later
by a well-meaning hand must be dropped on load, not served — otherwise this
module quietly becomes the multi-language expansion that was turned down.

MAHARASHTRA ONLY. Every other state must come back byte-for-byte as before.
This is the regression that would be invisible in review and obvious in GSC.

AND THE COPY MUST FIT THE SERP. Marathi titles are longer than Hindi ones for
the same fact, and a title Google truncates is the defect this set out to fix.
"""

import json

import pytest

from backend.services import state_lang


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Point the loader at a throwaway JSON and clear its mtime cache."""
    def _write(payload) -> None:
        p = tmp_path / "state_lang.json"
        p.write_text(
            payload if isinstance(payload, str)
            else json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(state_lang, "_PATH", p)
        monkeypatch.setattr(state_lang, "_cache", None)
        monkeypatch.setattr(state_lang, "_mtime", -1.0)
    return _write


MR = {
    "languages": {
        "mr": {
            "label": "मराठी",
            "script": "Devanagari",
            "html_lang": "mr",
            "og_locale": "mr_IN",
            "states": ["Maharashtra"],
            "months": ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून",
                       "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"],
            "titles": {"crop_district": ["{place} {crop} बाजार भाव आजचे",
                                         "{crop} बाजार भाव"]},
            "h1": {"crop_district": "{place} — {crop} बाजार भाव आजचे"},
            "words": {"bhav": "बाजार भाव", "price_avg": "सरासरी ₹{avg}/क्विंटल"},
            "faqs": {"crop_district": [["{district} {crop} भाव किती?", "उत्तर {price}."],
                                       ["किमान आणि कमाल?", "₹{lo} ते ₹{hi}."]]},
            "crops": {"गेहूं": "गहू", "प्याज": "कांदा"},
        }
    }
}

VALS = {"place": "जालना", "crop": "सोयाबीन", "district": "जालना"}


class TestSilenceIsTheFallback:
    def test_missing_file_leaves_everything_hindi(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state_lang, "_PATH", tmp_path / "gone.json")
        monkeypatch.setattr(state_lang, "_cache", None)
        monkeypatch.setattr(state_lang, "_mtime", -1.0)
        assert state_lang.lang_for("Maharashtra") == "hi"
        assert state_lang.crop("गेहूं", "mr") == "गेहूं"
        assert state_lang.h1("crop_district", "mr", VALS, "HINDI") == "HINDI"
        assert state_lang.variants("titles", "crop_district", "mr", VALS) == []

    def test_corrupt_file_leaves_everything_hindi(self, cfg):
        cfg("{ this is not json")
        assert state_lang.lang_for("Maharashtra") == "hi"
        assert state_lang.h1("crop_district", "mr", VALS, "HINDI") == "HINDI"

    def test_unknown_crop_keeps_its_hindi_name(self, cfg):
        cfg(MR)
        assert state_lang.crop("कालीमिर्च", "mr") == "कालीमिर्च"

    def test_known_crop_is_translated(self, cfg):
        cfg(MR)
        assert state_lang.crop("गेहूं", "mr") == "गहू"

    def test_typo_in_a_template_drops_that_variant_only(self, cfg):
        """A stray placeholder is a copy edit gone wrong, not an outage."""
        cfg({"languages": {"mr": {**MR["languages"]["mr"], "titles": {
            "crop_district": ["{crp} बाजार भाव", "{crop} बाजार भाव"]}}}})
        got = state_lang.variants("titles", "crop_district", "mr", VALS)
        assert got == ["सोयाबीन बाजार भाव"]

    def test_h1_falls_back_when_its_template_cannot_fill(self, cfg):
        cfg({"languages": {"mr": {**MR["languages"]["mr"],
                                  "h1": {"crop_district": "{nope}"}}}})
        assert state_lang.h1("crop_district", "mr", VALS, "HINDI") == "HINDI"

    def test_page_type_with_no_translation_yields_nothing(self, cfg):
        """A tier nobody has translated keeps its Hindi rather than half-fills."""
        cfg(MR)
        assert state_lang.variants("titles", "state_all", "mr", VALS) == []
        assert state_lang.faqs("state_all", "mr", VALS) == []

    def test_no_accessor_raises_on_garbage_input(self, cfg):
        cfg(MR)
        for lang in ("", "zz", None):
            assert state_lang.crop("गेहूं", lang) == "गेहूं"
            assert state_lang.variants("titles", "crop_district", lang, {}) == []
            assert state_lang.h1("crop_district", lang, {}, "H") == "H"
            assert state_lang.faqs("crop_district", lang, {}) == []


class TestDevanagariOnly:
    @pytest.mark.parametrize("marker, name", [
        ("தமிழ்", "Tamil"), ("ಕನ್ನಡ", "Kannada"), ("తెలుగు", "Telugu"),
        ("മലയാളം", "Malayalam"), ("বাংলা", "Bengali"), ("ਪੰਜਾਬੀ", "Gurmukhi"),
        ("ગુજરાતી", "Gujarati"), ("ଓଡ଼ିଆ", "Odia"),
    ])
    def test_a_non_devanagari_language_is_refused(self, cfg, marker, name):
        cfg({"languages": {"xx": {
            "label": name, "script": "Devanagari", "states": ["Tamil Nadu"],
            "titles": {"crop_district": [marker + " {crop}"]}}}})
        assert state_lang.loaded() == {}
        assert state_lang.lang_for("Tamil Nadu") == "hi"

    def test_a_block_declaring_another_script_is_refused(self, cfg):
        cfg({"languages": {"xx": {"label": "x", "script": "Tamil",
                                  "states": ["Tamil Nadu"]}}})
        assert state_lang.lang_for("Tamil Nadu") == "hi"

    def test_the_guard_finds_it_buried_deep(self, cfg):
        """One bad crop name inside an otherwise plausible block still fails it."""
        bad = {**MR["languages"]["mr"], "crops": {"गेहूं": "கோதுமை"}}
        cfg({"languages": {"mr": bad}})
        assert state_lang.loaded() == {}

    def test_the_shipped_file_passes_its_own_guard(self):
        """The real data file, not a fixture — mr must actually be live."""
        assert "mr" in state_lang.loaded()
        assert state_lang.lang_for("Maharashtra") == "mr"


class TestMaharashtraOnly:
    @pytest.mark.parametrize("state", [
        "Uttar Pradesh", "Madhya Pradesh", "Karnataka", "Tamil Nadu",
        "Rajasthan", "Bihar", "Punjab", "Gujarat", "Goa", "",
    ])
    def test_every_other_state_stays_hindi(self, cfg, state):
        cfg(MR)
        lang = state_lang.lang_for(state)
        assert lang == "hi"
        assert state_lang.crop("गेहूं", lang) == "गेहूं"
        assert state_lang.html_lang(lang) == "hi"
        assert state_lang.og_locale(lang) == "hi_IN"
        assert state_lang.variants("titles", "crop_district", lang, VALS) == []

    def test_maharashtra_declares_itself_marathi_in_the_markup(self, cfg):
        """The tag has to move with the prose — Google believes the tag."""
        cfg(MR)
        assert state_lang.html_lang("mr") == "mr"
        assert state_lang.og_locale("mr") == "mr_IN"

    def test_hindi_never_localises_a_date(self, cfg):
        cfg(MR)
        assert state_lang.date_str(8, 9, 2026, "hi", "8 सितंबर 2026") == "8 सितंबर 2026"

    def test_marathi_month_names_replace_hindi_ones(self, cfg):
        cfg(MR)
        assert state_lang.date_str(8, 9, 2026, "mr", "8 सितंबर 2026") == "8 सप्टेंबर 2026"

    def test_a_short_month_table_is_refused_rather_than_half_used(self, cfg):
        cfg({"languages": {"mr": {**MR["languages"]["mr"], "months": ["जानेवारी"]}}})
        assert state_lang.date_str(8, 9, 2026, "mr", "8 सितंबर 2026") == "8 सितंबर 2026"


class TestFaqsAndFit:
    def test_a_pair_is_dropped_whole_when_its_data_is_missing(self, cfg):
        """No min/max reported means two questions, never a vague third."""
        cfg(MR)
        got = state_lang.faqs("crop_district", "mr", {**VALS, "price": "₹4,750"})
        assert len(got) == 1
        assert got[0][0] == "जालना सोयाबीन भाव किती?"

    def test_both_pairs_render_when_the_data_is_there(self, cfg):
        cfg(MR)
        got = state_lang.faqs("crop_district", "mr",
                              {**VALS, "price": "₹4,750", "lo": "4,200", "hi": "5,100"})
        assert len(got) == 2
        assert "₹4,200 ते ₹5,100." == got[1][1]

    def test_fill_chooses_wording_but_not_presence(self, cfg):
        cfg(MR)
        assert state_lang.fill("price_avg", "mr", {"avg": "4,750"}) == "सरासरी ₹4,750/क्विंटल"
        assert state_lang.fill("absent", "mr", {}, "D") == "D"

    def test_shipped_marathi_titles_fit_the_serp_window(self):
        """68 chars for a title, 162 for a description — the site's own budget.

        Checked against the longest real inputs rather than a typical one: the
        crop with the longest Marathi name in a district with a long one, which
        is where a template silently overflows.
        """
        vals = {"crop": "ढोबळी मिरची", "en": "Capsicum", "place": "छत्रपती संभाजीनगर",
                "district": "छत्रपती संभाजीनगर", "district_en": "Chhatrapati Sambhajinagar",
                "en_d": "Chhatrapati Sambhajinagar", "state": "महाराष्ट्र",
                "state_en": "Maharashtra", "date": "8 सप्टेंबर 2026", "n": 12,
                "n_dist": 36, "year": 2026, "avg": "सरासरी ₹4,750/क्विंटल. "}
        for page in ("crop_district", "crop_state", "district_all",
                     "state_all", "kharidar"):
            titles = state_lang.variants("titles", page, "mr", vals)
            assert titles, f"no Marathi titles for {page}"
            assert min(len(t) for t in titles) <= 68, (
                f"every {page} title variant overflows the SERP window: {titles}")
            descs = state_lang.variants("descs", page, "mr", vals)
            if descs:
                assert min(len(d) for d in descs) <= 162, (
                    f"every {page} description overflows: {descs}")

    def test_shipped_crop_table_translates_the_state_top_crops(self):
        """The crops Maharashtra actually reports, by GSC impressions.

        Not an exhaustive list — an untranslated crop is a supported outcome —
        but these are the ones carrying the traffic, so a silent regression in
        the table should fail here rather than in next month's numbers.
        """
        for hindi, marathi in [("गेहूं", "गहू"), ("प्याज", "कांदा"),
                               ("ज्वार", "ज्वारी"), ("मक्का", "मका"),
                               ("हल्दी", "हळद"), ("अनार", "डाळिंब"),
                               ("अदरक", "आले"), ("मूंग", "मूग"),
                               ("भिंडी", "भेंडी"), ("लहसुन", "लसूण")]:
            assert state_lang.crop(hindi, "mr") == marathi

    def test_coriander_is_left_untranslated_on_purpose(self):
        """Marathi splits leaf (कोथिंबीर) from seed (धणे) where Hindi merges both
        into धनिया, and /bhav maps Coriander and Coriander(Leaves) to the same
        Hindi word. Translating would assert 'leaf' on the seed page."""
        assert state_lang.crop("धनिया", "mr") == "धनिया"

    def test_a_compound_follows_the_word_it_is_built_from(self):
        """प्याज→कांदा and मिर्च→मिरची were in the table while हरी प्याज and
        हरी मिर्च were not — so Maharashtra's WhatsApp post headlined a Hindi
        crop name in an otherwise Marathi message, and /bhav's हरी मिर्च pages
        (66 reporting mandis) did the same."""
        for hindi, marathi in [("हरी प्याज", "हिरवा कांदा"),
                               ("हरी मिर्च", "हिरवी मिरची"),
                               ("लाल मिर्च", "लाल मिरची"),
                               ("शकरकंद", "रताळे")]:
            assert state_lang.crop(hindi, "mr") == marathi

    def test_crops_identical_in_both_languages_stay_out_of_the_table(self):
        """The fallback already returns them unchanged, and an entry that
        restates its own key is one more line to keep true for no gain."""
        for same in ("सोयाबीन", "मसूर", "गाजर", "पालक"):
            assert state_lang.crop(same, "mr") == same


class TestPack:
    """pack() hands a whole named block over at once — for the WhatsApp post,
    which needs two dozen wordings and resolves its own per-key fallbacks."""

    def test_it_returns_the_block(self):
        wa = state_lang.pack("wa", "mr")
        assert wa and wa["label.up"] == "📈 वाढले"

    def test_hindi_gets_nothing_so_the_caller_falls_back_to_its_own(self):
        assert state_lang.pack("wa", "hi") == {}

    def test_an_unknown_language_or_block_is_empty_not_an_error(self):
        assert state_lang.pack("wa", "xx") == {}
        assert state_lang.pack("no_such_block", "mr") == {}

    def test_the_caller_cannot_mutate_the_cache_through_it(self):
        """_load() caches the parsed file; handing out the live dict would let
        one caller's edit reach every page on the site."""
        got = state_lang.pack("wa", "mr")
        got["label.up"] = "tampered"
        assert state_lang.pack("wa", "mr")["label.up"] == "📈 वाढले"


# ── Route level ──────────────────────────────────────────────
# The classes above test the module. These test the five pages, because the
# thing that would actually hurt is not a wrong lookup — it is a Maharashtra
# page that stayed Hindi, or a Uttar Pradesh page that did not.

@pytest.fixture(scope="module")
def seeded(request, db_engine):
    """One crop in one district of Maharashtra and of Uttar Pradesh.

    Wheat because it is the crop whose two names differ most visibly
    (गेहूं / गहू), and the two states because the whole change is the claim
    that one of them renders differently from the other.
    """
    from datetime import date

    from backend.database.db import MandiLastSeen, SessionLocal
    from backend.routes import bhav

    db = SessionLocal()
    made = []
    for commodity, state, district in [
        ("Wheat", "Maharashtra", "Solapur"),
        ("Onion", "Maharashtra", "Solapur"),
        ("Wheat", "Uttar Pradesh", "Meerut"),
    ]:
        r = MandiLastSeen(
            group_key=f"mrtest-{commodity}-{state}-{district}".lower(),
            commodity=commodity, state=state, district=district, market=district,
            min_price="2590", max_price="2610", modal_price="2600",
            arrival_date="04/09/2026", arrival_dt=date(2026, 9, 4))
        db.add(r)
        made.append(r)
    db.commit()

    bhav._index, bhav._index_ts = {}, 0.0
    bhav._get_index()

    def _cleanup():
        for r in made:
            db.delete(r)
        db.commit()
        db.close()
        bhav._index, bhav._index_ts = {}, 0.0

    request.addfinalizer(_cleanup)


MH_PAGES = [
    "/bhav/rajya/maharashtra",
    "/bhav/rajya/maharashtra/solapur",
    "/bhav/wheat/maharashtra",
    "/bhav/wheat/maharashtra/solapur",
]
UP_PAGES = [
    "/bhav/rajya/uttar-pradesh",
    "/bhav/rajya/uttar-pradesh/meerut",
    "/bhav/wheat/uttar-pradesh",
    "/bhav/wheat/uttar-pradesh/meerut",
]


def title_of(html: str) -> str:
    import re
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return m.group(1) if m else ""


@pytest.mark.usefixtures("seeded")
class TestMaharashtraPagesSpeakMarathi:
    @pytest.mark.parametrize("url", MH_PAGES)
    def test_title_says_bajar_bhav_not_mandi_bhav(self, client, url):
        """The defect in one assertion: the searcher types बाजार भाव."""
        t = title_of(client.get(url).text)
        assert "बाजार भाव" in t, t
        assert "मंडी भाव" not in t, t

    @pytest.mark.parametrize("url", MH_PAGES)
    def test_the_lang_tag_moves_with_the_prose(self, client, url):
        html = client.get(url).text
        assert '<html lang="mr">' in html
        assert '<meta property="og:locale" content="mr_IN">' in html

    def test_the_crop_is_named_in_marathi(self, client):
        html = client.get("/bhav/wheat/maharashtra/solapur").text
        assert "गहू" in title_of(html)
        assert "गेहूं" not in title_of(html)

    def test_the_h1_agrees_with_the_title(self, client):
        """A Marathi title that opens onto a Hindi headline spends the click
        telling the farmer he is in the wrong place."""
        html = client.get("/bhav/wheat/maharashtra/solapur").text
        h1 = html.split("<h1>")[1].split("</h1>")[0]
        assert "बाजार भाव" in h1 and "मंडी" not in h1, h1

    def test_the_month_name_is_marathi(self, client):
        html = client.get("/bhav/wheat/maharashtra/solapur").text
        assert "सितंबर" not in html.split("</head>")[0]


@pytest.mark.usefixtures("seeded")
class TestEveryOtherStateIsUntouched:
    @pytest.mark.parametrize("url", UP_PAGES)
    def test_title_still_says_mandi_bhav(self, client, url):
        t = title_of(client.get(url).text)
        assert "बाजार भाव" not in t, t

    @pytest.mark.parametrize("url", UP_PAGES)
    def test_still_declares_hindi(self, client, url):
        html = client.get(url).text
        assert '<html lang="hi">' in html
        assert '<meta property="og:locale" content="hi_IN">' in html

    def test_the_crop_is_still_named_in_hindi(self, client):
        assert "गेहूं" in title_of(client.get("/bhav/wheat/uttar-pradesh/meerut").text)


@pytest.mark.usefixtures("seeded")
class TestTheUrlsDidNotChange:
    """The 23 Aug decision was that the site has too many URLs, not too few.

    A language layer that added /mr/ or ?lang= would double 14,000 of them and
    make the diagnosed problem worse, so the canonical must be the same address
    the Hindi page would have claimed.
    """

    @pytest.mark.parametrize("url", MH_PAGES)
    def test_canonical_is_the_plain_url(self, client, url):
        html = client.get(url).text
        assert f'<link rel="canonical" href="https://krashimitra.in{url}">' in html

    @pytest.mark.parametrize("url", MH_PAGES)
    def test_no_language_variant_is_advertised(self, client, url):
        html = client.get(url).text
        assert "hreflang" not in html
        assert "?lang=" not in html


class TestDistrictSpelling:
    """Devanagari is not enough — the vowel and the ळ have to match too.

    GSC carries "गहू बाजार भाव आजचे सोलापूर" while the page said "सोलापुर".
    Both are Devanagari; only one is what the farmer typed.
    """

    @pytest.mark.parametrize("hindi, marathi", [
        ("सोलापुर", "सोलापूर"), ("कोल्हापुर", "कोल्हापूर"),
        ("नागपुर", "नागपूर"), ("चंद्रपुर", "चंद्रपूर"),
        ("जलगांव", "जळगाव"), ("धुले", "धुळे"), ("यवतमाल", "यवतमाळ"),
        ("नासिक", "नाशिक"), ("गड़चिरोली", "गडचिरोली"),
        ("नांदेड़", "नांदेड"), ("रायगढ़", "रायगड"),
        ("छत्रपति संभाजीनगर", "छत्रपती संभाजीनगर"),
    ])
    def test_the_thirteen_that_differ(self, hindi, marathi):
        assert state_lang.district(hindi, "mr") == marathi

    @pytest.mark.parametrize("same", [
        "पुणे", "जालना", "लातूर", "अकोला", "अमरावती", "सांगली", "सातारा",
        "बीड", "ठाणे", "मुंबई", "धाराशिव", "वाशिम",
    ])
    def test_the_ones_that_match_are_left_alone(self, same):
        """Omitted from the table on purpose — the fallback returns them."""
        assert state_lang.district(same, "mr") == same

    def test_hindi_pages_keep_the_hindi_spelling(self):
        assert state_lang.district("सोलापुर", "hi") == "सोलापुर"

    def test_an_unlisted_district_is_never_invented(self):
        assert state_lang.district("मेरठ", "mr") == "मेरठ"


@pytest.mark.usefixtures("seeded")
class TestDistrictSpellingReachesThePage:
    def test_the_title_uses_the_marathi_spelling(self, client):
        t = title_of(client.get("/bhav/wheat/maharashtra/solapur").text)
        assert "सोलापूर" in t and "सोलापुर" not in t, t

    def test_the_district_hub_too(self, client):
        t = title_of(client.get("/bhav/rajya/maharashtra/solapur").text)
        assert "सोलापूर" in t and "सोलापुर" not in t, t
