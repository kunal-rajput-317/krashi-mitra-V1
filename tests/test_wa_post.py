"""आज की पोस्ट — the daily bhav message each state's WhatsApp channel gets.

The post is the only thing a follower ever sees, and it is written once and
pasted 31 times a morning, so a wrong line here is wrong everywhere. What has
to hold: the numbers are the same ones /bhav shows, a mill's output is never
printed as a farmer's crop, and the day-on-day move is computed on a paired
basis rather than against a different set of mandis.
"""

import pytest

from backend.services import wa_channels, wa_post


@pytest.fixture(autouse=True)
def no_db(monkeypatch):
    """Nothing in this file may touch Neon — every test supplies its own rows."""
    def _boom():
        raise AssertionError("_snapshot() should have been stubbed")
    monkeypatch.setattr(wa_post, "_snapshot", _boom)
    monkeypatch.setattr(wa_post, "_cache", {})
    monkeypatch.setattr(wa_post, "_cache_ts", 0.0)


def agg(modals, prev=None, mandis=None, ages=None):
    """One commodity's rows: modal prices, optional (today, yesterday) pairs.

    `ages` is how old each row's arrival_date is, in days. It feeds the
    confidence score and nothing else — no printed price can move because of
    it — and defaults to today's, so a test that is not about freshness does
    not have to think about it."""
    return {"modals": list(modals),
            "prev_pairs": list(prev or []),
            "mandis": set(mandis or [f"m{i}" for i in range(len(modals))]),
            "ages": list(ages) if ages is not None else [0] * len(modals)}


class TestFarmGate:
    @pytest.mark.parametrize("name", [
        "Rice", "Broken Rice", "Beaten Rice", "Wheat Atta", "Maida Atta",
        "Masur Dal", "Dal Mix", "Bengal Gram Dal(Chana Dal)", "Sugar",
        "Mustard Oil", "Coconut Oil",
    ])
    def test_mill_output_is_excluded(self, name):
        assert not wa_post._farm_gate(name)

    @pytest.mark.parametrize("name", [
        "Paddy(Dhan)(Common)",      # the grain the rice is made from
        "Wheat",
        "Cinamon(Dalchini)",        # "dal" is not a word inside "Dalchini"
        "Mentha Oil",               # distilled on the farm — a real farm-gate sale
        "Bengal Gram(Gram)",        # whole gram, not the split dal
        "Gur(Jaggery)",
    ])
    def test_farm_gate_crops_survive(self, name):
        assert wa_post._farm_gate(name)


class TestMove:
    def test_no_move_says_so(self):
        assert wa_post._move(None) == "— कल जैसा"
        assert wa_post._move(0) == "— कल जैसा"

    def test_arrow_carries_the_sign(self):
        """A '-' after a ▼ is the same word twice."""
        assert wa_post._move(-1.2) == "▼ 1.2%"
        assert wa_post._move(2.5) == "▲ 2.5%"


class TestCropLines:
    def test_thin_crops_are_dropped(self):
        """Two mandis is a quote, not a state average."""
        rows = {"Wheat": agg([2000, 2100], mandis=["a", "b"])}
        assert wa_post._crop_lines(rows) == []

    def test_average_and_paired_delta(self):
        rows = {"Wheat": agg([2000, 2200, 2400], mandis=["a", "b", "c"],
                             prev=[(2000, 1000), (2200, 1200)])}
        line, = wa_post._crop_lines(rows)
        assert line["avg"] == 2200                     # (2000+2200+2400)/3
        assert line["pct"] == 90.9                     # (4200-2200)/2200
        assert line["mandis"] == 3

    def test_delta_ignores_rows_with_no_previous_price(self):
        """A mandi reporting for the first time has no move — counting its
        price on one side of the ratio and nothing on the other invents one."""
        rows = {"Wheat": agg([1000, 1000, 5000], mandis=["a", "b", "c"],
                             prev=[(1000, 1000), (1000, 1000)])}
        line, = wa_post._crop_lines(rows)
        assert line["pct"] == 0

    def test_staples_come_first(self):
        rows = {"Wheat":  agg([2000] * 4, mandis=list("abcd")),
                "Tomato": agg([1500] * 9, mandis=list("abcdefghi"))}
        names = [l["commodity"] for l in wa_post._crop_lines(rows)]
        assert names[0] == "Wheat", "tile order, not row count, decides the top line"

    def test_one_line_per_hindi_name(self):
        """Three pumpkins are all कद्दू; a post listing कद्दू three times at
        three prices reads like a mistake."""
        rows = {"Pumpkin":       agg([900] * 4, mandis=list("abcd")),
                "Sweet Pumpkin": agg([1200] * 5, mandis=list("abcde")),
                "Wheat":         agg([2000] * 4, mandis=list("wxyz"))}
        his = [l["hi"] for l in wa_post._crop_lines(rows)]
        assert len(his) == len(set(his))

    def test_caps_at_five(self):
        rows = {c: agg([1000] * 4, mandis=list("abcd"))
                for c in ["Wheat", "Paddy(Dhan)(Common)", "Onion", "Potato",
                          "Tomato", "Maize", "Soyabean"]}
        assert len(wa_post._crop_lines(rows)) == wa_post._CROPS_PER_POST

    def test_mill_output_never_reaches_a_post(self):
        rows = {"Rice":  agg([3300] * 9, mandis=list("abcdefghi")),
                "Wheat": agg([2500] * 4, mandis=list("wxyz"))}
        assert [l["commodity"] for l in wa_post._crop_lines(rows)] == ["Wheat"]


class TestText:
    def test_post_carries_price_date_and_one_deep_link(self):
        lines = [{"hi": "गेहूं", "avg": 2501, "pct": -0.2},
                 {"hi": "धान", "avg": 2609, "pct": 0.8}]
        txt = wa_post._text("उत्तर प्रदेश", "uttar-pradesh", lines, 251)
        assert "उत्तर प्रदेश मंडी भाव" in txt
        assert "गेहूं — ₹2,501 ▼ 0.2%" in txt
        assert "251 मंडियों" in txt
        # The number is IN the post — a post that withholds it to force a click
        # is the kind that gets muted.
        assert txt.count("https://") == 1
        assert "/bhav/rajya/uttar-pradesh?utm_source=wa" in txt

    def test_link_is_tagged_for_ga4(self):
        """WhatsApp in-app clicks arrive with no referrer; without utm they are
        indistinguishable from direct traffic and the channel cannot be judged."""
        txt = wa_post._text("बिहार", "bihar", [{"hi": "धान", "avg": 2000, "pct": None}], 10)
        assert "utm_source=wa" in txt and "utm_medium=channel" in txt


class TestPosts:
    @pytest.fixture
    def wired(self, monkeypatch, tmp_path):
        import json
        p = tmp_path / "wa_channels.json"
        p.write_text(json.dumps({"channels": {
            "uttar_pradesh": {"state": "Uttar Pradesh", "name": "krashimitra_up",
                              "url": "https://whatsapp.com/channel/UP"},
            "bihar": {"state": "Bihar", "name": "krashimitra_bihar",
                      "url": "https://whatsapp.com/channel/BR"},
        }}, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(wa_channels, "_PATH", p)
        monkeypatch.setattr(wa_channels, "_cache", None)
        monkeypatch.setattr(wa_channels, "_mtime", -1.0)

    def test_only_states_with_a_channel_get_a_post(self, monkeypatch, wired):
        monkeypatch.setattr(wa_post, "_snapshot", lambda: {
            "Uttar Pradesh": {"Wheat": agg([2500] * 4, mandis=list("abcd"))},
            "Punjab":        {"Wheat": agg([2600] * 4, mandis=list("abcd"))},
        })
        assert [p["state"] for p in wa_post.posts(refresh=True)] == ["Uttar Pradesh"]

    def test_biggest_state_first(self, monkeypatch, wired):
        monkeypatch.setattr(wa_post, "_snapshot", lambda: {
            "Bihar":         {"Wheat": agg([2500] * 9, mandis=list("abcdefghi"))},
            "Uttar Pradesh": {"Wheat": agg([2500] * 4, mandis=list("abcd"))},
        })
        assert [p["state"] for p in wa_post.posts(refresh=True)] == ["Bihar", "Uttar Pradesh"]

    def test_a_state_with_nothing_to_say_is_reported_not_faked(self, monkeypatch, wired):
        """A channel with no post today must be named, or the owner is left
        wondering whether the page is broken. Bihar here reports only a cow —
        markets did report, but nothing a farmer grows."""
        monkeypatch.setattr(wa_post, "_snapshot", lambda: {
            "Uttar Pradesh": {"Wheat": agg([2500] * 4, mandis=list("abcd"))},
            "Bihar":         {"Cow": agg([30000] * 4, mandis=list("abcd"))},
        })
        cov = wa_post.coverage(refresh=True)
        assert [p["state"] for p in cov["posts"]] == ["Uttar Pradesh"]
        assert [q["state"] for q in cov["quiet"]] == ["Bihar"]

    def test_a_quiet_channel_still_carries_its_link_and_its_reason(self, monkeypatch, wired):
        """The panel lists every channel, posting or not, so a quiet row has to
        be openable and has to say WHY — 'no market reported' and 'markets
        reported, but no crops' are different mornings."""
        monkeypatch.setattr(wa_post, "_snapshot", lambda: {
            "Uttar Pradesh": {"Wheat": agg([2500] * 4, mandis=list("abcd"))},
        })
        quiet, = wa_post.coverage(refresh=True)["quiet"]
        assert quiet["state"] == "Bihar"
        assert quiet["url"].startswith("https://")
        assert quiet["why"] == "no_rows" and quiet["why_hi"]

    def test_every_channel_is_in_one_list_or_the_other(self, monkeypatch, wired):
        monkeypatch.setattr(wa_post, "_snapshot", lambda: {
            "Uttar Pradesh": {"Wheat": agg([2500] * 4, mandis=list("abcd"))},
        })
        cov = wa_post.coverage(refresh=True)
        assert len(cov["posts"]) + len(cov["quiet"]) == cov["channels"] == 2

    def test_post_for_takes_agmarknet_spellings(self, monkeypatch, wired):
        monkeypatch.setattr(wa_post, "_snapshot", lambda: {
            "Uttar Pradesh": {"Wheat": agg([2500] * 4, mandis=list("abcd"))},
        })
        wa_post.posts(refresh=True)
        assert wa_post.post_for("uttar-pradesh") is not None


class TestThinStates:
    """Delhi has one grain mandi — Azadpur, one of the largest in the country —
    and the >=3-mandi bar silenced its channel entirely. A state that cannot
    clear the bar gets its post rebuilt at one mandi, and the post stops using
    the word 'average'."""

    @pytest.fixture
    def wired(self, monkeypatch, tmp_path):
        import json
        p = tmp_path / "wa_channels.json"
        p.write_text(json.dumps({"channels": {
            # keyed "delhi", not "nct_of_delhi": wa_channels._ALIASES folds
            # Agmarknet's spelling onto one key, same as the live file does.
            "delhi": {"state": "NCT of Delhi", "name": "krashimitra_delhi",
                      "url": "https://whatsapp.com/channel/DL"},
        }}, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(wa_channels, "_PATH", p)
        monkeypatch.setattr(wa_channels, "_cache", None)
        monkeypatch.setattr(wa_channels, "_mtime", -1.0)

    def test_a_one_mandi_state_gets_a_post_instead_of_silence(self, monkeypatch, wired):
        monkeypatch.setattr(wa_post, "_snapshot", lambda: {
            "NCT of Delhi": {"Onion": agg([2500], mandis=["APMC Azadpur"])},
        })
        post, = wa_post.posts(refresh=True)
        assert post["thin"] is True
        assert "प्याज" in post["text"]

    def test_the_thin_post_names_the_mandi_rather_than_claiming_an_average(self, monkeypatch, wired):
        monkeypatch.setattr(wa_post, "_snapshot", lambda: {
            "NCT of Delhi": {"Onion": agg([2500], mandis=["APMC Azadpur"])},
        })
        post, = wa_post.posts(refresh=True)
        assert "APMC Azadpur की सरकारी रिपोर्ट" in post["text"]
        assert "औसत" not in post["text"], "one trader's quote is not a state average"

    def test_the_strict_bar_still_wins_where_the_state_can_clear_it(self, monkeypatch, wired):
        """The fallback is a last resort, not a second opinion: a crop with 3
        mandis must never be dropped in favour of a 1-mandi crop."""
        monkeypatch.setattr(wa_post, "_snapshot", lambda: {
            "NCT of Delhi": {"Wheat":  agg([2500] * 3, mandis=list("abc")),
                             "Onion":  agg([2500],     mandis=["z"])},
        })
        post, = wa_post.posts(refresh=True)
        assert post["thin"] is False
        assert [l["commodity"] for l in post["crops"]] == ["Wheat"]


class TestLivestockGate:
    """Mizoram's only two reporting rows were Cow and Pigs. At the thin bar
    they built a 🌾 मंडी भाव post quoting livestock in ₹/क्विंटल."""

    @pytest.mark.parametrize("name", [
        "Cow", "Calf", "Ox", "Pigs", "Goat", "Sheep", "She Buffalo",
        "He Buffalo", "Egg", "Fish", "Hen", "Cock",
    ])
    def test_livestock_never_reaches_a_bhav_post(self, name):
        assert not wa_post._farm_gate(name)

    @pytest.mark.parametrize("name", ["Cowpea(Lobia/Karamani)", "Cowpea(Veg)"])
    def test_cowpea_is_still_a_pulse(self, name):
        assert wa_post._farm_gate(name)


class TestConfidenceScore:
    """One wrong number costs more trust than a week of right ones buys, so
    every post carries a score out of 100 that the owner sees before pasting.
    It never changes a printed price — it only says how sure we are of it."""

    def line(self, **kw):
        rows = {"Wheat": agg(**kw)}
        got = wa_post._crop_lines(rows, min_mandis=1)
        assert got, "the fixture should always produce one line"
        return got[0]

    def test_fresh_broad_agreeing_data_scores_full_marks(self):
        l = self.line(modals=[2000] * 10, prev=[(2000, 1990)] * 10, ages=[0] * 10)
        assert l["score"] == 100
        assert l["flags"] == []

    def test_stale_prices_cost_more_than_thin_ones(self):
        """mandi_prices keeps a market's last price for ~7 days. A five-day-old
        number printed under today's date is confidently wrong, which is worse
        than a number that is merely weak — the weights have to say so."""
        stale = self.line(modals=[2000] * 10, prev=[(2000, 1990)] * 10, ages=[5] * 10)
        thin = self.line(modals=[2000], mandis=["a"], prev=[(2000, 1990)], ages=[0])
        assert stale["score"] < thin["score"]
        assert any("5 दिन पुराना" in f for f in stale["flags"])

    def test_one_mandi_scores_below_many(self):
        one = self.line(modals=[2000], mandis=["a"], prev=[(2000, 1990)])
        many = self.line(modals=[2000] * 10, prev=[(2000, 1990)] * 10)
        assert one["score"] < many["score"]
        assert any("सिर्फ़ 1 मंडी" in f for f in one["flags"])

    def test_a_wild_spread_is_flagged(self):
        """Madhya Pradesh onion ran ₹700–₹5,000 on one day. That average is
        describing two different markets, not one price."""
        split = self.line(modals=[700] * 5 + [5000] * 5, prev=[(700, 700)] * 10)
        agreed = self.line(modals=[2850] * 10, prev=[(2850, 2850)] * 10)
        assert any("अलग-अलग" in f for f in split["flags"])
        assert split["score"] < agreed["score"]

    def test_an_absurd_overnight_move_is_flagged(self):
        """A 200% jump is a variety switch or a kg/quintal slip, not a move."""
        l = self.line(modals=[3000] * 4, prev=[(3000, 1000)] * 4)
        assert any("रिपोर्ट की गलती" in f for f in l["flags"])

    def test_kal_jaisa_with_no_previous_price_is_flagged(self):
        """'— कल जैसा' tells a farmer nothing moved. With no previous price
        behind it, that is a claim we cannot back."""
        l = self.line(modals=[2000] * 10, prev=None)
        assert l["pct"] is None
        assert any("कल जैसा" in f for f in l["flags"])

    def test_undated_rows_are_not_assumed_fresh(self):
        l = self.line(modals=[2000] * 10, prev=[(2000, 1990)] * 10, ages=[None] * 10)
        assert l["score"] < 100
        assert any("तारीख़" in f for f in l["flags"])

    def test_a_post_is_pulled_toward_its_worst_line(self):
        """A follower does not average five lines; he remembers the wrong one."""
        good = [{"score": 100}] * 4
        assert wa_post._score_post(good) == 100
        assert wa_post._score_post(good + [{"score": 20}]) < 84   # the plain mean

    def test_the_band_names_the_action(self):
        assert wa_post.band(92)["key"] == "good"
        assert wa_post.band(75)["key"] == "ok"
        assert wa_post.band(60)["key"] == "check"
        assert wa_post.band(30)["key"] == "risky"
        assert all(wa_post.band(s)["hi"] for s in (92, 75, 60, 30))

    def test_one_complaint_from_every_line_is_said_once(self):
        """Goa's card listed 'सिर्फ़ 1 मंडी से' five times — that is one fact
        about the state printed five ways, and it buries the line under it."""
        rows = {c: agg([2000], mandis=["Mapusa APMC"], prev=[(2000, 2000)])
                for c in ("Wheat", "Onion", "Potato", "Tomato", "Brinjal")}
        flags = wa_post._flags(wa_post._crop_lines(rows, min_mandis=1))
        assert sum("मंडी रिपोर्ट कर रही है" in f for f in flags) == 1
        assert not any("सिर्फ़ 1 मंडी से" in f for f in flags)

    def test_a_price_range_is_never_rolled_up(self):
        """Each spread line names a specific range to go and look at on /bhav,
        which is the whole use of it — a count would throw that away."""
        rows = {c: agg([500] * 3 + [5000] * 3, mandis=list("abcdef"),
                       prev=[(500, 500)] * 6)
                for c in ("Wheat", "Onion", "Potato")}
        flags = wa_post._flags(wa_post._crop_lines(rows))
        assert sum("अलग-अलग" in f for f in flags) == 3

    def test_the_score_never_moves_a_printed_price(self, monkeypatch):
        """The whole point of building the post from the same snapshot /bhav
        reads is that the channel and the page can never disagree. Scoring a
        line badly must not silently drop or adjust it."""
        rows = {"Wheat": agg([2000, 2200, 2400], mandis=list("abc"), ages=[6, 6, 6])}
        l, = wa_post._crop_lines(rows)
        assert l["avg"] == 2200 and l["score"] < 70

