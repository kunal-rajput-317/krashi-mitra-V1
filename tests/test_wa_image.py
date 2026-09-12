"""तस्वीर और वह एक लाइन — the picture and the extra line on the channel post.

Both of these let something into the daily post that did not come out of
services/wa_post: a picture from an image model, and a sentence a language
model wrote. Everything else on that page is arithmetic the tests can check.
These two are not, so what is tested here is not that they are good — it is
that neither of them can carry a number, a link or a contact detail into a
broadcast going to a state's farmers.

  • The image model is NEVER asked for text. Not by the automatic prompts, and
    not by one the owner typed asking for exactly that. It cannot spell
    Devanagari, and a price painted into a JPEG is outside every check this
    codebase has.
  • The extra line may only re-say facts we supplied. A figure in it that is
    not in those facts is a fabrication and is refused, not flagged-and-sent.
  • The post keeps exactly one link, whatever is appended to it. That link is
    the only measurement we have of whether the channel works at all.
"""

import re
from datetime import date, timedelta

import pytest

from backend.services import wa_extra, wa_image, wa_style

DAY = date(2026, 9, 11)

POST = {
    "state": "Madhya Pradesh", "key": "madhya_pradesh", "hi_state": "मध्य प्रदेश",
    "slug": "madhya-pradesh", "lang": "hi", "mandis": 336,
    "crops": [
        {"commodity": "Soyabean", "hi": "सोयाबीन", "name": "सोयाबीन", "avg": 4520,
         "pct": 2.1, "move": "▲ 2.1%"},
        {"commodity": "Wheat", "hi": "गेहूं", "name": "गेहूं", "avg": 2280,
         "pct": -0.8, "move": "▼ 0.8%"},
    ],
}


def ctx(**kw):
    base = {"state": "मध्य प्रदेश", "slug": "madhya-pradesh", "lang": "hi",
            "bhav": "मंडी भाव", "date": "11 सितंबर 2026", "mandis": 336,
            "market": "",
            "url": "https://krashimitra.in/bhav/rajya/madhya-pradesh?utm_source=wa"}
    return {**base, **kw}


class TestThePromptNeverAsksForText:
    """The one rule the whole picture feature rests on."""

    @pytest.mark.parametrize("mode", ["scene", "random", "custom"])
    def test_every_mode_bans_lettering(self, mode):
        full = wa_image.build_prompt(POST, mode, custom="a wheat field", day=DAY)["full"]
        low = full.lower()
        for banned in ("no text", "no letters", "no numbers", "no watermark"):
            assert banned in low, f"{mode} lost the ban on {banned!r}"

    def test_a_typed_request_for_text_still_gets_the_ban(self):
        """The field where the owner would ask for lettering is the field that
        appends the refusal. Asking harder must not get further."""
        b = wa_image.build_prompt(
            POST, "custom",
            custom="wheat field with the price ₹2280 written in big Hindi letters",
            day=DAY)
        assert "no text" in b["full"].lower()
        assert "no numbers" in b["full"].lower()
        assert b["warnings"], "the owner was not told his lettering will not appear"

    def test_the_ban_is_not_editable(self):
        """`prompt` is what the panel shows and lets him edit; `full` is what is
        sent. The ban lives only in the second, so no amount of editing the
        textarea can remove it."""
        b = wa_image.build_prompt(POST, "custom", custom="a mandi at dawn", day=DAY)
        assert "no text" not in b["prompt"].lower()
        assert b["full"].startswith(b["prompt"])
        assert "no text" in b["full"].lower()

    def test_a_long_prompt_cannot_bury_the_ban(self):
        """A ban appended after three paragraphs is a ban the model skims past."""
        b = wa_image.build_prompt(POST, "custom", custom="field. " * 400, day=DAY)
        assert len(b["prompt"]) <= wa_image._MAX_PROMPT
        assert "no text" in b["full"].lower()


class TestThePictureCarriesNoClaim:
    def test_the_scene_prompt_never_mentions_a_price(self):
        """A picture cannot carry "₹4,520, up 2.1%" honestly, and a prompt that
        tried — brighter light because the market rose — would be smuggling a
        claim past the machinery that checks claims."""
        p = wa_image.scene_prompt(POST, DAY)
        assert "4520" not in p and "4,520" not in p and "₹" not in p
        assert "2.1" not in p
        for word in ("rose", "fell", "up ", "down ", "high price", "low price"):
            assert word not in p.lower()

    def test_the_scene_prompt_names_the_state_and_the_crop_in_english(self):
        """The model was trained on "soybean", not सोयाबीन. Asking in
        Devanagari is how a Madhya Pradesh soya post gets a picture of wheat."""
        p = wa_image.scene_prompt(POST, DAY)
        assert "Madhya Pradesh" in p
        assert "soyabean" in p.lower()
        assert not re.search(r"[ऀ-ॿ]", p), "Devanagari reached the model"

    def test_a_state_with_no_crops_still_gets_a_prompt(self):
        p = wa_image.scene_prompt({**POST, "crops": []}, DAY)
        assert "Madhya Pradesh" in p and len(p) > 40


class TestTheRotationIsStable:
    def test_random_is_a_pure_function_of_state_and_date(self):
        """Same reason the format rotation is: a reload must not reshuffle a
        picture the owner was halfway through looking at."""
        a = wa_image.random_prompt("madhya_pradesh", DAY)
        b = wa_image.random_prompt("madhya_pradesh", DAY)
        assert a == b

    def test_no_one_scene_owns_the_morning(self):
        """The same bar test_wa_style sets for formats, and for the same
        reason: eight states drawing from twelve scenes collide by the birthday
        paradox alone, and demanding uniqueness would be demanding an
        impossible property of a finite pool. What must hold is that the
        channels are spread rather than bunched onto one photograph."""
        keys = ["uttar_pradesh", "maharashtra", "bihar", "punjab", "gujarat",
                "rajasthan", "karnataka", "west_bengal"]
        for i in range(60):
            d = date(2026, 9, 1) + timedelta(days=i)
            got = [wa_image.random_prompt(k, d) for k in keys]
            top = max(got.count(g) for g in set(got))
            assert len(set(got)) >= 4, (d, got)
            assert top <= len(keys) // 2, (d, "one photograph owns the morning")

    def test_a_state_does_not_get_the_same_scene_two_days_running(self):
        for i in range(12):
            d = date(2026, 9, 1)
            assert (wa_image.random_prompt("bihar", d.replace(day=1 + i))
                    != wa_image.random_prompt("bihar", d.replace(day=2 + i)))


class TestTheFreeFallback:
    def test_the_mark_is_bytes_not_a_url(self):
        """The panel draws it onto the same canvas it then calls toBlob() on.
        One cross-origin pixel taints that canvas and the copy button dies."""
        assert not wa_image.catalog()["logo"].startswith("http")

    def test_the_mark_travels_with_every_card(self):
        """Same rule the नक्शा downloads keep: a generated image that gets
        forwarded off WhatsApp with no mark on it is doing someone else's
        marketing."""
        assert wa_image.catalog()["logo"].startswith("data:image/png;base64,")

    def test_the_palette_matches_the_maps(self):
        """Copied rather than imported — make_state_maps pulls playwright in.
        This is the pin that keeps the copy honest."""
        src = (wa_image._ROOT / "make_state_maps.py").read_text(encoding="utf-8")
        for hexval in wa_image.PALETTE.values():
            assert hexval in src, f"{hexval} is no longer the brand's colour"


class TestTheExtraLineCannotLie:
    KNOWN = {"2425", "5950"}

    def test_a_figure_we_did_not_supply_is_refused(self):
        flags = wa_extra.check("गेहूं का MSP ₹3,100 है", self.KNOWN)
        assert flags and any("3100" in f for f in flags)

    def test_a_figure_we_did_supply_passes(self):
        assert wa_extra.check("गेहूं का MSP ₹2,425 है", self.KNOWN) == []

    def test_a_second_link_is_refused(self):
        """The post carries exactly one link. A second splits the click and
        breaks the only measurement of whether the channel works."""
        for bad in ("देखिए krashimitra.in पर", "https://example.com देखिए",
                    "www.agmarknet.gov.in"):
            assert any("लिंक" in f for f in wa_extra.check(bad, self.KNOWN))

    def test_a_phone_number_or_email_is_refused(self):
        for bad in ("कॉल करें 9870951001", "लिखिए krashimitra038@gmail.com"):
            assert wa_extra.check(bad, self.KNOWN)

    def test_a_paragraph_is_refused(self):
        assert wa_extra.check("क " * 200, self.KNOWN)

    def test_an_empty_line_is_refused(self):
        assert wa_extra.check("   ", self.KNOWN)

    def test_a_year_is_not_treated_as_a_claim(self):
        """Same reading the news generator takes: "2026" carries no claim, a
        rupee figure does."""
        assert wa_extra.check("रबी 2026 की बुवाई शुरू है", set()) == []


class TestTheExtraLineInThePost:
    def test_the_post_still_keeps_exactly_one_link(self):
        t = wa_style.compose(ctx(), POST["crops"], "suchi", "seedha",
                             extra="⚖️ MSP से नीचे — गेहूं (MSP ₹2,425)।")
        assert t.count("http") == 1

    def test_every_price_still_prints(self):
        """The line is added beside the prices, never instead of one."""
        t = wa_style.compose(ctx(), POST["crops"], "suchi", "seedha",
                             extra="⚖️ MSP से नीचे — गेहूं।")
        for c in POST["crops"]:
            assert f"₹{c['avg']:,}" in t

    def test_it_sits_between_the_prices_and_the_source(self):
        """Not inside the crop rows, where it would read as a price, and not
        beside the attribution, where it would read as part of the source."""
        extra = "⚖️ MSP से नीचे — गेहूं।"
        t = wa_style.compose(ctx(), POST["crops"], "suchi", "seedha", extra=extra)
        assert t.index("₹2,280") < t.index(extra) < t.index("Agmarknet")

    def test_a_multi_line_extra_cannot_break_the_shape(self):
        """The structural guard, enforced in compose() where every format×tone
        test runs. Whatever it contains, it is one line."""
        t = wa_style.compose(ctx(), POST["crops"], "suchi", "seedha",
                             extra="पहली\nदूसरी\nतीसरी")
        assert "पहली दूसरी तीसरी" in t

    def test_it_is_truncated_at_the_length_the_panel_promised(self):
        """A suggestion the panel shows as acceptable must survive composition
        intact — the owner picking a line and getting a different one is worse
        than the line being too long."""
        assert wa_extra._MAX_LEN == wa_style.EXTRA_MAX
        t = wa_style.compose(ctx(), POST["crops"], "suchi", "seedha", extra="क" * 400)
        assert "क" * wa_style.EXTRA_MAX in t
        assert "क" * (wa_style.EXTRA_MAX + 1) not in t

    def test_no_extra_leaves_the_post_exactly_as_it_was(self):
        """The default is nothing, and nothing must be byte-identical to the
        post that went out before this feature existed."""
        assert (wa_style.compose(ctx(), POST["crops"], "suchi", "seedha")
                == wa_style.compose(ctx(), POST["crops"], "suchi", "seedha", extra=""))


class TestTheSuretyMeter:
    """पक्कापन — how much of an AI line came from our facts.

    The gate (check()) is pass/fail. This is the meter beside it, and it exists
    for the lines that clear every hard rule and are still subtly wrong."""

    FACTS = [
        {"text": "⚖️ MSP से नीचे — सोयाबीन (MSP ₹5,328), गेहूं (MSP ₹2,585)। "
                 "सरकारी खरीद केंद्र पर इससे कम नहीं मिलना चाहिए।",
         "numbers": {"5328", "2585"}},
        {"text": "📰 आज की खबर — कठुआ में PM किसान योजना से खेती को मिली नई उड़ान",
         "numbers": set()},
    ]

    def test_a_fact_scores_full_marks_against_itself(self):
        """The top of the scale has to be reachable, or nobody learns what a
        good number looks like. A पक्की line IS the facts, so it reads 100."""
        m = wa_extra.surety(self.FACTS[0]["text"], self.FACTS)
        assert m["score"] == 100 and m["band"] == "sure"

    def test_the_dropped_label_is_caught(self):
        """The failure this meter was built for, observed in a real run: every
        figure is ours, so check() passes it — but MSP has moved off the
        figures and ₹5,328 now reads as what सोयाबीन is selling for."""
        line = "सोयाबीन (₹5,328) और गेहूं (₹2,585) MSP से नीचे न बेचें।"
        assert wa_extra.check(line, {"5328", "2585"}) == [], "the gate should pass this"
        m = wa_extra.surety(line, self.FACTS)
        assert m["score"] < 70, "the meter did not notice the label move"
        assert any("5328" in r for r in m["reasons"])

    def test_keeping_the_label_scores_higher_than_dropping_it(self):
        kept = wa_extra.surety(
            "⚖️ सोयाबीन और गेहूं MSP (₹5,328 / ₹2,585) से नीचे बिक रहे हैं।", self.FACTS)
        dropped = wa_extra.surety(
            "सोयाबीन (₹5,328) और गेहूं (₹2,585) MSP से नीचे न बेचें।", self.FACTS)
        assert kept["score"] > dropped["score"]

    def test_a_line_with_no_figures_cannot_mislabel_one(self):
        m = wa_extra.surety(
            "⚖️ सोयाबीन और गेहूं आज MSP से नीचे हैं — खरीद केंद्र देख लीजिए।", self.FACTS)
        assert m["score"] >= 85

    def test_invented_prose_scores_low_and_names_the_stray_words(self):
        m = wa_extra.surety(
            "किसान भाइयों आज मौसम बढ़िया है, खेत की जुताई कर लीजिए और पानी दे दीजिए।",
            self.FACTS)
        assert m["score"] < 70
        assert any("हमारी बातों में नहीं" in r for r in m["reasons"])

    @pytest.mark.parametrize("line", [
        "⚖️ MSP से नीचे सोयाबीन — खरीद केंद्र पर गारंटी से पूरा दाम मिलेगा।",
        "⚖️ MSP से नीचे सोयाबीन है, कांग्रेस ने कुछ नहीं किया।",
    ])
    def test_a_promise_or_a_party_caps_the_meter_and_blocks_the_line(self, line):
        """Not a proportional fault a well-grounded sentence can outweigh: a
        well-written profit guarantee is worse than a clumsy one."""
        m = wa_extra.surety(line, self.FACTS)
        assert m["score"] <= 45 and m["band"] == "thin"
        assert wa_extra.check(line, {"5328", "2585"}), "the gate let it through"

    def test_the_meter_is_not_the_models_own_confidence(self):
        """Every point is computed from the line against the facts, so the same
        sentence scores the same however it was produced — there is nowhere for
        a model to report an opinion of itself."""
        line = "⚖️ सोयाबीन और गेहूं MSP से नीचे हैं।"
        assert (wa_extra.surety(line, self.FACTS)
                == wa_extra.surety(line, self.FACTS))

    def test_it_never_raises_on_junk(self):
        for junk in ("", "   ", "!!!", "12345", "x" * 500):
            m = wa_extra.surety(junk, self.FACTS)
            assert 0 <= m["score"] <= 100 and m["hi"]

    def test_it_survives_an_empty_fact_list(self):
        m = wa_extra.surety("⚖️ कुछ भी", [])
        assert 0 <= m["score"] <= 100


class TestTheTokeniserHandlesIndicScripts:
    """The grounding score is word overlap, so the word boundaries have to be
    real. Python's \\w is "alphanumeric" and an Indic vowel sign is a combining
    mark — \\w+ chops किसान into क, स, न and every comparison is between
    shards. This is the regression pin for that."""

    def test_devanagari_words_survive_their_matras(self):
        got = wa_extra._content("सोयाबीन और गेहूं किसान भाइयों")
        assert "सोयाबीन" in got and "किसान" in got and "गेहूं" in got

    @pytest.mark.parametrize("word", [
        "விவசாயி",        # Tamil
        "ರೈತರು",           # Kannada
        "শস্য",            # Bengali
        "ખેડૂત",           # Gujarati
        "ਕਿਸਾਨ",           # Gurmukhi
        "రైతు",            # Telugu
    ])
    def test_every_script_a_post_can_be_written_in(self, word):
        """services/state_lang can put a post in any of these, and the meter
        has to mean the same thing on all of them."""
        assert word in wa_extra._content(f"{word} MSP")

    def test_a_word_is_not_split_into_shards(self):
        assert all(len(w) > 1 for w in wa_extra._content("किसान भाइयों की फसल"))


class TestTheFactsAreOurs:
    def test_facts_never_raise_on_a_state_with_nothing(self):
        """The button has to do something on a quiet morning, including saying
        there is nothing."""
        assert isinstance(wa_extra.facts({**POST, "crops": []}), list)

    def test_every_fact_declares_its_own_numbers(self):
        """`numbers` is what the model's rewordings are checked against, so a
        fact that under-declares its figures would let one through."""
        for f in wa_extra.facts(POST):
            assert set(f["numbers"]) == set(wa_extra._numbers(f["text"]))
            assert f["kind"] and f["source"]

    def test_a_fact_is_short_enough_to_use(self):
        for f in wa_extra.facts(POST):
            assert len(f["text"]) <= wa_extra._MAX_LEN
            assert wa_extra.check(f["text"], set(f["numbers"])) == []
