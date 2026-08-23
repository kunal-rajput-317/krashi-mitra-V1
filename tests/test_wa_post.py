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


def agg(modals, prev=None, mandis=None):
    """One commodity's rows: modal prices, optional (today, yesterday) pairs."""
    return {"modals": list(modals),
            "prev_pairs": list(prev or []),
            "mandis": set(mandis or [f"m{i}" for i in range(len(modals))])}


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
        wondering whether the page is broken."""
        monkeypatch.setattr(wa_post, "_snapshot", lambda: {
            "Uttar Pradesh": {"Wheat": agg([2500] * 4, mandis=list("abcd"))},
            "Bihar":         {"Wheat": agg([2500], mandis=["a"])},
        })
        cov = wa_post.coverage(refresh=True)
        assert [p["state"] for p in cov["posts"]] == ["Uttar Pradesh"]
        assert [q["state"] for q in cov["quiet"]] == ["Bihar"]

    def test_post_for_takes_agmarknet_spellings(self, monkeypatch, wired):
        monkeypatch.setattr(wa_post, "_snapshot", lambda: {
            "Uttar Pradesh": {"Wheat": agg([2500] * 4, mandis=list("abcd"))},
        })
        wa_post.posts(refresh=True)
        assert wa_post.post_for("uttar-pradesh") is not None
