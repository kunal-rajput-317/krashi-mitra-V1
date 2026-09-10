"""आज की पोस्ट — the daily bhav message each state's WhatsApp channel gets.

The post is the only thing a follower ever sees, and it is written once and
pasted 31 times a morning, so a wrong line here is wrong everywhere. What has
to hold: the numbers are the same ones /bhav shows, a mill's output is never
printed as a farmer's crop, and the day-on-day move is computed on a paired
basis rather than against a different set of mandis.
"""

import re

import pytest

from backend.services import wa_channels, wa_post, wa_style


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

    def test_the_pool_is_wider_than_the_post(self):
        """_crop_lines returns a POOL, not the post. The formats pick their own
        lines out of it — सबसे बड़ी हलचल wants the day's biggest mover, which is
        often the ninth staple — and the panel's chips swap one for another.
        Both need more crops than the five that get printed."""
        rows = {c: agg([1000] * 4, mandis=list("abcd"))
                for c in ["Wheat", "Paddy(Dhan)(Common)", "Onion", "Potato",
                          "Tomato", "Maize", "Soyabean"]}
        pool = wa_post._crop_lines(rows)
        assert len(pool) == 7 > wa_post._CROPS_PER_POST

    def test_the_pool_itself_is_capped(self):
        rows = {f"Crop{i}": agg([1000] * 4, mandis=list("abcd")) for i in range(40)}
        assert len(wa_post._crop_lines(rows)) <= wa_post._POOL

    def test_mill_output_never_reaches_a_post(self):
        rows = {"Rice":  agg([3300] * 9, mandis=list("abcdefghi")),
                "Wheat": agg([2500] * 4, mandis=list("wxyz"))}
        assert [l["commodity"] for l in wa_post._crop_lines(rows)] == ["Wheat"]


class TestText:
    """What every post must carry, whatever shape the rotation gave it.

    These used to test one function that built one shape. There are now thirty
    shapes, so each of these asserts across all of them — which is the stronger
    claim anyway: it is not "the post has a link", it is "there is no format
    and no tone that can drop the link".
    """

    def _ctx(self, mandis=251, market=""):
        return {"state": "उत्तर प्रदेश", "slug": "uttar-pradesh", "lang": "hi",
                "bhav": "मंडी भाव", "date": "9 सितंबर 2026",
                "mandis": mandis, "market": market,
                "url": f"{wa_post.SITE}/bhav/rajya/uttar-pradesh{wa_post._LINK_Q}"}

    def _lines(self):
        return [{"name": "गेहूं", "hi": "गेहूं", "avg": 2501, "pct": -0.2,
                 "move": "▼ 0.2%", "rank": 0, "top_market": "कानपुर", "p_hi": 2600,
                 "w_lo": 2400, "w_hi": 2600},
                {"name": "धान", "hi": "धान", "avg": 2609, "pct": 0.8,
                 "move": "▲ 0.8%", "rank": 1, "top_market": "गोरखपुर", "p_hi": 2700,
                 "w_lo": 2500, "w_hi": 2700}]

    def _every(self, ctx=None, lines=None):
        ctx, lines = ctx or self._ctx(), lines or self._lines()
        for f in wa_style.FORMATS:
            for t in wa_style.TONES:
                yield f["id"], t["id"], wa_style.compose(ctx, lines, f["id"], t["id"])

    def test_every_post_carries_price_and_exactly_one_deep_link(self):
        for fid, tid, txt in self._every():
            # The number is IN the post — a post that withholds it to force a
            # click is the kind that gets muted.
            assert "₹2,501" in txt, (fid, tid)
            assert txt.count("https://") == 1, (fid, tid)
            assert "/bhav/rajya/uttar-pradesh?utm_source=wa" in txt, (fid, tid)

    def test_every_post_says_how_many_mandis_are_behind_it(self):
        for fid, tid, txt in self._every():
            assert "251" in txt, (fid, tid)

    def test_link_is_tagged_for_ga4(self):
        """WhatsApp in-app clicks arrive with no referrer; without utm they are
        indistinguishable from direct traffic and the channel cannot be judged."""
        for fid, tid, txt in self._every():
            assert "utm_source=wa" in txt and "utm_medium=channel" in txt, (fid, tid)

    def test_no_format_or_tone_can_change_a_price(self):
        """The whole reason services/wa_style is a separate module: it may
        arrange words around the figures, never recompute one. If this ever
        fails, the channel and the /bhav page have stopped agreeing — which is
        the single thing wa_post exists to prevent.

        Two halves, and the second is the one that bites. Every combination
        must print every headline average — and it must print NOTHING ELSE
        that wa_post did not put in the line. दायरा and हफ़्ता legitimately
        carry extra figures (a top market's price, a week's band), so the test
        is not "the same numbers" but "no invented ones": every ₹ in the post
        has to be traceable to a field of a line dict."""
        allowed = set()
        for line in self._lines():
            for k in ("avg", "p_hi", "p_lo", "w_lo", "w_hi"):
                if line.get(k):
                    allowed.add(f"₹{line[k]:,}")
        for fid, tid, txt in self._every():
            for line in self._lines():
                assert f"₹{line['avg']:,}" in txt, (fid, tid, line["name"])
            printed = set(re.findall(r"₹[\d,]+", txt))
            assert printed <= allowed, (fid, tid, printed - allowed)


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
        # The wording is a tone's business and rotates; that the market is
        # NAMED and that the word औसत is nowhere near it are this module's,
        # and hold in every voice.
        for t in wa_style.TONES:
            txt = wa_post.recompose("NCT of Delhi", tone=t["id"])["text"]
            assert "APMC Azadpur" in txt, t["id"]
            assert "औसत" not in txt, (t["id"], "one trader's quote is not a state average")

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


class TestWeekBand:
    """हफ़्ते का हाल — ₹2,645 means one thing after a week at ₹2,600 and the
    opposite after a week at ₹2,900, and a single-day post never said which.
    The band is the state average recomputed on earlier reports, so it is the
    same kind of number as the headline and can be printed beside it."""

    def test_a_flat_week_reports_a_flat_band(self):
        """Equal ends are honest here; it is the FORMAT that declines to print
        'हफ़्ते में ₹4,450–₹4,450', which would read as a bug."""
        assert wa_post._week(["4450,4450,4450,4450"] * 3) == (4450, 4450)

    def test_one_mandi_is_not_a_week(self):
        assert wa_post._week(["2600,2610,2620,2630"]) == (None, None)

    def test_two_points_are_not_a_week(self):
        assert wa_post._week(["2600,2610", "2650,2660"]) == (None, None)

    def test_the_band_is_the_state_average_not_the_widest_mandi(self):
        """Min/max across every mandi's every reading would print the spread
        BETWEEN markets as if it were movement over TIME — Madhya Pradesh onion
        would claim a ₹700–₹5,000 'week'."""
        assert wa_post._week(["1000,1000,1000,1000",
                              "3000,3000,3000,3000"]) == (2000, 2000)

    def test_it_tracks_the_average_moving(self):
        lo, hi = wa_post._week(["2400,2500,2600,2700", "2600,2700,2800,2900"])
        assert (lo, hi) == (2500, 2800)

    def test_junk_in_a_spark_cannot_reach_a_price(self):
        assert wa_post._week(["a,b,c,d", "x,y,z,w"]) == (None, None)


class TestTopMarket:
    """कहाँ सबसे ऊँचा — the only thing on the card that answers "so where do I
    take it?". An average never can."""

    def test_it_names_the_market_paying_most(self):
        rows = {"Wheat": agg([2500, 2600, 2700], mandis=["a", "b", "Kanpur"])}
        rows["Wheat"]["top"] = (2700, "Kanpur")
        line, = wa_post._crop_lines(rows)
        assert line["top_market"] == "Kanpur" and line["p_hi"] == 2700

    def test_it_stays_quiet_when_the_mandis_disagree(self):
        """On a crop whose prices run ₹700 to ₹5,000 the "highest" market is a
        different variety under the same name. Naming it sends a farmer 200km
        for a premium his sack does not qualify for — so the EXTRA fact is
        withheld, while the average, which /bhav also prints, is not."""
        rows = {"Onion": agg([700, 900, 5000], mandis=["a", "b", "Lasalgaon"])}
        rows["Onion"]["top"] = (5000, "Lasalgaon")
        line, = wa_post._crop_lines(rows)
        assert line["top_market"] == ""
        assert line["avg"] == 2200, "the average itself is untouched"


class TestNovelty:
    """भरोसा asks whether the numbers are right. नयापन asks the other question:
    whether there is any reason to send this at all."""

    def test_a_day_where_nothing_moved_says_so(self):
        n = wa_post.novelty([{"pct": 0.0}, {"pct": None}, {"pct": 0.2}])
        assert n["moved"] == 0 and n["key"] == "same"

    def test_an_unverifiable_move_counts_as_no_move(self):
        """A crop with no yesterday to compare against cannot be reported as
        having moved — the same care 'कल जैसा' takes elsewhere in this module."""
        assert wa_post.novelty([{"pct": None}] * 5)["moved"] == 0

    def test_a_real_move_is_counted(self):
        n = wa_post.novelty([{"pct": 2.8}, {"pct": -3.1}, {"pct": 0.0}])
        assert n["moved"] == 2 and n["key"] == "fresh"

    def test_it_agrees_with_what_the_format_calls_a_move(self):
        """चढ़े–गिरे and नयापन must not disagree on one card about which crops
        moved — two thresholds would be two answers to one question."""
        lines = [{"pct": 0.4}, {"pct": 0.6}]
        assert wa_post.novelty(lines)["moved"] == len(wa_style.moved(lines)) == 1


class TestRecompose:
    """The panel's controls. Each overrides one of the rotation's decisions and
    nothing else, and none of them may touch a price."""

    @pytest.fixture
    def wired(self, monkeypatch, tmp_path):
        import json
        p = tmp_path / "wa_channels.json"
        p.write_text(json.dumps({"channels": {
            "uttar_pradesh": {"state": "Uttar Pradesh", "name": "km_up",
                              "url": "https://whatsapp.com/channel/UP"},
        }}, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(wa_channels, "_PATH", p)
        monkeypatch.setattr(wa_channels, "_cache", None)
        monkeypatch.setattr(wa_channels, "_mtime", -1.0)
        monkeypatch.setattr(wa_post, "_snapshot", lambda: {"Uttar Pradesh": {
            "Wheat":  agg([2500, 2550, 2600], mandis=list("abc"),
                          prev=[(2500, 2400), (2550, 2450), (2600, 2500)]),
            "Onion":  agg([3800, 3900, 4000], mandis=list("def"),
                          prev=[(3800, 3800), (3900, 3900), (4000, 4000)]),
            "Potato": agg([1100, 1150, 1200], mandis=list("ghi"),
                          prev=[(1100, 1200), (1150, 1250), (1200, 1300)]),
            "Maize":  agg([1900, 1950, 2000], mandis=list("jkl"),
                          prev=[(1900, 1900), (1950, 1950), (2000, 2000)]),
        }})

    def test_sending_nothing_gives_back_the_rotation(self, wired):
        auto = wa_post.post_for("Uttar Pradesh", refresh=True)
        again = wa_post.recompose("Uttar Pradesh")
        assert (again["format"], again["tone"], again["text"]) == \
               (auto["format"], auto["tone"], auto["text"])

    def test_the_crop_count_is_clamped_to_something_readable(self, wired):
        wa_post.posts(refresh=True)
        assert wa_post.recompose("Uttar Pradesh", n=99)["n"] == wa_post._MAX_CROPS
        assert wa_post.recompose("Uttar Pradesh", n=1)["n"] == wa_post._MIN_CROPS

    def test_a_format_the_data_cannot_carry_is_refused_not_faked(self, wired):
        """The panel greys these out, but the service is the boundary that has
        to hold: asking for हफ़्ता on a state with no history must fall back to
        the rotation's choice rather than print an empty band."""
        r = wa_post.recompose("Uttar Pradesh", fmt="hafta")
        assert r["format"] != "hafta" and "हफ़्ते में" not in r["text"]

    def test_an_unknown_format_falls_back_rather_than_raising(self, wired):
        wa_post.posts(refresh=True)
        r = wa_post.recompose("Uttar Pradesh", fmt="nonsense", tone="nonsense")
        assert r["format"] in {f["id"] for f in wa_style.FORMATS}
        assert r["tone"] in {t["id"] for t in wa_style.TONES}

    def test_dropping_a_crop_takes_it_out_and_fills_the_gap(self, wired):
        """The sharpest control on the page, and it has to be honest: the score
        comes back recomputed on the lines that survive, or it is decoration."""
        wa_post.posts(refresh=True)
        before = wa_post.recompose("Uttar Pradesh", fmt="suchi", n=3)
        names = [l["commodity"] for l in before["crops"]]
        after = wa_post.recompose("Uttar Pradesh", fmt="suchi", n=3, drop={names[0]})
        assert names[0] not in [l["commodity"] for l in after["crops"]]
        assert after["dropped"] == [names[0]]
        assert len(after["crops"]) == 3, "the gap is filled from the pool"

    def test_dropping_every_crop_still_returns_a_post(self, wired):
        """A control that can empty the message is a control that can hand the
        owner a post with no prices in it. Falling back to the whole pool is
        the honest floor — better a post he did not ask for than a blank one he
        pastes without looking."""
        wa_post.posts(refresh=True)
        every = {l["commodity"] for l in wa_post.post_for("Uttar Pradesh")["pool"]}
        r = wa_post.recompose("Uttar Pradesh", drop=every)
        assert r and r["crops"] and "₹" in r["text"]

    def test_an_unknown_state_is_no_post_not_an_error(self, wired):
        wa_post.posts(refresh=True)
        assert wa_post.recompose("Atlantis") is None

    def test_no_override_can_change_a_price(self, wired):
        """The invariant the whole panel rests on, driven through the real
        override path rather than through wa_style directly."""
        wa_post.posts(refresh=True)
        base = {l["commodity"]: l["avg"]
                for l in wa_post.recompose("Uttar Pradesh", n=8)["crops"]}
        for f in wa_style.FORMATS:
            for t in wa_style.TONES:
                r = wa_post.recompose("Uttar Pradesh", fmt=f["id"], tone=t["id"], n=8)
                for l in r["crops"]:
                    assert l["avg"] == base[l["commodity"]], (f["id"], t["id"])

    def test_dropping_the_movers_drops_the_movement_format(self, wired):
        """सबसे बड़ी हलचल built on a pool that no longer moves would headline
        "कल से 0% ऊपर" — an announcement that nothing happened. The format has
        to fit what is LEFT, not what the morning started with."""
        wa_post.posts(refresh=True)
        movers = {l["commodity"] for l in wa_post._cache["pools"]["uttar_pradesh"]
                  if l["pct"] and abs(l["pct"]) >= wa_style._REAL_MOVE}
        assert movers, "fixture must have something that moved"
        r = wa_post.recompose("Uttar Pradesh", fmt="bada", drop=movers)
        assert r["format"] not in ("bada", "chadha")
        assert "0% ऊपर" not in r["text"] and "0% नीचे" not in r["text"]
