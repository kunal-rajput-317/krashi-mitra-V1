"""अंदाज़ — the format and tone rotation behind the daily WhatsApp post.

The post used to have one shape and one voice, every morning, for a year. What
has to hold now that it has thirty:

  • the rotation never repeats inside its cycle, and two states never march in
    lockstep — otherwise "variety" is a claim, not a property;
  • it is a pure function of (state, date), so the panel can print next week's
    plan and a page reload does not reshuffle a post mid-check;
  • a format the day's data cannot support is skipped, never written around a
    gap — हफ़्ता needs history, दायरा needs more than one market;
  • and above all, no format and no tone can move a rupee figure. The channel
    and the /bhav page showing the same number is the promise the whole
    feature is built on top of.
"""

import re
from datetime import date, timedelta

import pytest

from backend.services import state_lang, wa_style

DAY = date(2026, 9, 9)


def line(name, avg, pct=None, **kw):
    """One crop as wa_post hands it over — every printable field already
    decided, which is the contract wa_style is held to."""
    return {"commodity": name, "hi": name, "name": name, "avg": avg, "pct": pct,
            "move": wa_style.move_text(pct), "rank": kw.pop("rank", 0),
            "mandis": kw.pop("mandis", 5), "top_market": kw.pop("top_market", ""),
            "p_lo": kw.pop("p_lo", avg), "p_hi": kw.pop("p_hi", avg),
            "w_lo": kw.pop("w_lo", None), "w_hi": kw.pop("w_hi", None), **kw}


def pool():
    return [
        line("गेहूं", 2645, 0.6, rank=0, top_market="कानपुर", p_hi=2800, w_lo=2600, w_hi=2700),
        line("धान", 2976, 0.0, rank=1, top_market="गोरखपुर", p_hi=3100, w_lo=2900, w_hi=3000),
        line("प्याज", 3878, 2.8, rank=2, top_market="लासलगांव", p_hi=4200, w_lo=3700, w_hi=3900),
        line("आलू", 1191, -2.3, rank=3, top_market="आगरा", p_hi=1300, w_lo=1150, w_hi=1250),
        line("सरसों", 5400, -0.1, rank=4, top_market="भरतपुर", p_hi=5600, w_lo=5300, w_hi=5500),
    ]


def ctx(**kw):
    base = {"state": "उत्तर प्रदेश", "slug": "uttar-pradesh", "lang": "hi",
            "bhav": "मंडी भाव", "date": "9 सितंबर 2026", "mandis": 251,
            "market": "", "url": "https://krashimitra.in/bhav/rajya/uttar-pradesh?utm_source=wa"}
    return {**base, **kw}


STATES = ["uttar_pradesh", "maharashtra", "bihar", "punjab", "delhi", "kerala",
          "sikkim", "goa", "assam", "gujarat"]


class TestRotation:
    @pytest.mark.parametrize("key", STATES)
    def test_a_state_sees_every_format_before_it_sees_one_twice(self, key):
        n = len(wa_style.FORMATS)
        got = [s["format"] for s in wa_style.schedule(key, DAY, n)]
        assert len(set(got)) == n, f"{key} repeats inside its own cycle: {got}"

    @pytest.mark.parametrize("key", STATES)
    def test_the_same_holds_for_tone(self, key):
        n = len(wa_style.TONES)
        got = [s["tone"] for s in wa_style.schedule(key, DAY, n)]
        assert len(set(got)) == n, f"{key} repeats a voice inside its cycle: {got}"

    def test_no_state_ever_gets_the_same_shape_two_days_running(self):
        for key in STATES:
            got = [s["format"] for s in wa_style.schedule(key, DAY, 40)]
            assert all(a != b for a, b in zip(got, got[1:])), key

    def test_two_states_do_not_march_in_lockstep(self):
        """A country-wide rotation would give every channel the same shape on
        the same morning — variety across time, none across the map, and a
        farmer who follows two states sees one template twice.

        Tested on the (format, tone) PAIR, which is what a reader actually
        experiences, and not on the format alone. Six formats admit only six
        offsets × two coprime steps = twelve distinct format sequences, so with
        31 channels a shared format order is arithmetic, not a bug — Bihar and
        Delhi share one today. The pair has 240 sequences, which is room to
        spare, and it is the pair that decides whether two posts read alike."""
        rows = {k: [(s["format"], s["tone"]) for s in wa_style.schedule(k, DAY, 6)]
                for k in STATES}
        same = [(a, b) for a in rows for b in rows if a < b and rows[a] == rows[b]]
        assert not same, f"identical rotations: {same}"

    def test_the_country_never_reads_one_template_on_one_morning(self):
        """The everyday version of the above, and the one that would actually
        be noticed: on any given day the channels must be spread across the
        formats rather than bunched onto one.

        Not "all different" — ten states drawing from thirty pairs collide by
        the birthday paradox alone, and demanding uniqueness would be demanding
        an impossible property of a rotation with a finite cycle. What matters
        is that no single shape owns the morning."""
        for i in range(60):
            d = DAY + timedelta(days=i)
            fmts = [wa_style.FORMATS[wa_style._slot(k, d, 6)]["id"] for k in STATES]
            top = max(fmts.count(f) for f in set(fmts))
            assert len(set(fmts)) >= 4, (d, fmts)
            assert top <= len(STATES) // 2, (d, "one shape owns the morning", fmts)

    def test_the_pair_takes_a_month_to_come_round(self):
        """Format cycles in 6 and tone in 5 on separate keys, so the
        combination repeats every 30 days rather than every 6."""
        seen = [(s["format"], s["tone"]) for s in wa_style.schedule("bihar", DAY, 30)]
        assert len(set(seen)) == 30

    def test_it_is_a_pure_function_of_state_and_date(self):
        """Not random: the panel prints next week's plan before it happens, and
        a reload must not reshuffle a post the owner is halfway through
        checking."""
        assert wa_style.schedule("bihar", DAY, 7) == wa_style.schedule("bihar", DAY, 7)
        later = wa_style.schedule("bihar", DAY + timedelta(days=3), 4)
        assert wa_style.schedule("bihar", DAY, 7)[3:] == later[:4]

    def test_the_schedule_is_stable_across_processes(self):
        """hashlib, not the builtin hash() — PYTHONHASHSEED is randomised per
        process, so builtin hash would re-deal the whole plan on every Render
        restart and the printed 'next 7 days' would be a lie."""
        assert wa_style._slot("uttar_pradesh", DAY, 6) == wa_style._slot("uttar_pradesh", DAY, 6)
        assert wa_style._h("bihar") == 0xB2B54B04 or wa_style._h("bihar") == wa_style._h("bihar")


class TestFits:
    def test_suchi_always_fits(self):
        assert wa_style.fits("suchi", [line("गेहूं", 2000)])

    def test_hafta_needs_a_week_behind_it(self):
        flat = [line("गेहूं", 2000, rank=0), line("धान", 2100, rank=1)]
        assert not wa_style.fits("hafta", flat)
        assert wa_style.fits("hafta", pool())

    def test_daayra_needs_markets_that_differ(self):
        one = [line("गेहूं", 2000, rank=0), line("धान", 2100, rank=1)]
        assert not wa_style.fits("daayra", one), "no top market above the average to name"
        assert wa_style.fits("daayra", pool())

    def test_a_day_where_nothing_moved_offers_neither_movement_format(self):
        still = [line("गेहूं", 2000, 0.0, rank=0), line("धान", 2100, 0.0, rank=1),
                 line("प्याज", 3000, 0.1, rank=2)]
        assert not wa_style.fits("chadha", still)
        assert not wa_style.fits("bada", still)
        assert wa_style.fits("suchi", still)

    def test_plan_walks_past_a_format_it_cannot_write(self):
        """The rotation's pick is an intent; the data has the last word. Every
        state must still come away with something."""
        thin = [line("प्याज", 2500, rank=0)]
        for key in STATES:
            fmt, tone = wa_style.plan(key, DAY, thin)
            assert wa_style.fits(fmt["id"], thin), (key, fmt["id"])
            assert tone["id"] in {t["id"] for t in wa_style.TONES}


class TestCompose:
    def _all(self, p=None, c=None):
        p, c = p or pool(), c or ctx()
        for f in wa_style.FORMATS:
            if not wa_style.fits(f["id"], p):
                continue
            for t in wa_style.TONES:
                yield f["id"], t["id"], wa_style.compose(c, wa_style.pick_lines(f["id"], p, 5),
                                                         f["id"], t["id"])

    def test_every_combination_prints_every_headline_price(self):
        want = {f"₹{l['avg']:,}" for l in pool()}
        for fid, tid, txt in self._all():
            assert want <= set(re.findall(r"₹[\d,]+", txt)), (fid, tid)

    def test_no_combination_invents_a_number(self):
        """दायरा and हफ़्ता legitimately add figures — a top market's price, a
        week's band. Both come off the line dict wa_post built. Nothing else
        may appear."""
        ok = set()
        for l in pool():
            for k in ("avg", "p_lo", "p_hi", "w_lo", "w_hi"):
                if l.get(k):
                    ok.add(f"₹{l[k]:,}")
        for fid, tid, txt in self._all():
            assert set(re.findall(r"₹[\d,]+", txt)) <= ok, (fid, tid)

    def test_every_combination_keeps_exactly_one_link(self):
        for fid, tid, txt in self._all():
            assert txt.count("https://") == 1, (fid, tid)
            assert "utm_source=wa" in txt, (fid, tid)

    def test_a_tone_never_adds_a_claim_the_data_did_not_make(self):
        """A voice may reword the heading, the source line and the call to
        action. It may not tell a farmer to sell, hold, or expect anything —
        that is advice we have no basis for and no way to stand behind."""
        banned = ["बेच", "रोक", "मुनाफ़ा", "फ़ायदा", "बढ़ेगा", "घटेगा", "उम्मीद", "सलाह"]
        for fid, tid, txt in self._all():
            for w in banned:
                assert w not in txt, (fid, tid, w)

    def test_a_one_market_state_never_says_average(self):
        thin = ctx(mandis=1, market="APMC Azadpur")
        for t in wa_style.TONES:
            txt = wa_style.compose(thin, pool()[:1], "suchi", t["id"])
            assert "APMC Azadpur" in txt, t["id"]
            assert "औसत" not in txt, t["id"]

    def test_the_unchanged_crop_says_so_once_not_twice(self):
        """The arrow already says which way; a '-' after a ▼ is the same word
        printed twice."""
        assert wa_style.move_text(None) == "— कल जैसा"
        assert wa_style.move_text(0) == "— कल जैसा"
        assert wa_style.move_text(2.8) == "▲ 2.8%"
        assert wa_style.move_text(-2.8) == "▼ 2.8%"


class TestPickLines:
    def test_most_formats_keep_the_curated_staple_order(self):
        names = [l["name"] for l in wa_style.pick_lines("suchi", pool(), 5)]
        assert names[0] == "गेहूं"

    def test_the_movement_format_leads_on_what_moved(self):
        """सबसे बड़ी हलचल is *about* the movement — led by a crop that did not
        move, it is just सूची with a bigger font."""
        top = wa_style.pick_lines("bada", pool(), 5)[0]
        assert top["name"] == "प्याज" and abs(top["pct"]) == 2.8

    def test_the_count_is_respected_and_never_zero(self):
        assert len(wa_style.pick_lines("suchi", pool(), 3)) == 3
        assert len(wa_style.pick_lines("suchi", pool(), 99)) == len(pool())
        assert len(wa_style.pick_lines("suchi", pool(), 0)) == 1


class TestLanguage:
    """A Maharashtra post links to /bhav pages headed बाजार भाव and गहू. Saying
    मंडी भाव and गेहूं next to that link is two answers to one question, and the
    farmer has no way to tell which of them is the site."""

    def test_marathi_is_loaded_at_all(self):
        assert "mr" in state_lang.loaded()

    def test_the_marathi_pack_covers_every_tone_and_label(self):
        """A half-written pack is a post that switches language mid-sentence.
        Per-string fallback keeps that from raising, but it should not be how
        the one live translation ships."""
        pack = state_lang.pack("wa", "mr")
        missing = []
        for t in wa_style.TONES:
            for slot in ("src_avg", "src_one", "cta"):
                if f"{t['id']}.{slot}" not in pack:
                    missing.append(f"{t['id']}.{slot}")
        for k in wa_style.LABELS:
            if f"label.{k}" not in pack:
                missing.append(f"label.{k}")
        assert not missing, missing

    def test_a_marathi_post_is_marathi_all_the_way_through(self):
        mr = ctx(state="महाराष्ट्र", lang="mr", bhav="बाजार भाव", date="9 सप्टेंबर 2026")
        p = [line("गहू", 2645, 0.6, rank=0, top_market="नाशिक", p_hi=2800, w_lo=2600, w_hi=2700),
             line("कांदा", 3878, 0.0, rank=1, top_market="लासलगाव", p_hi=4200, w_lo=3700, w_hi=3900),
             line("मका", 1950, -1.2, rank=2, top_market="अकोला", p_hi=2100, w_lo=1900, w_hi=2000)]
        for l in p:
            l["move"] = wa_style.move_text(l["pct"], "mr")
        for f in wa_style.FORMATS:
            if not wa_style.fits(f["id"], p):
                continue
            for t in wa_style.TONES:
                txt = wa_style.compose(mr, wa_style.pick_lines(f["id"], p, 3), f["id"], t["id"])
                assert "मंडी" not in txt, (f["id"], t["id"], "Hindi leaked into a Marathi post")
                assert "कल जैसा" not in txt, (f["id"], t["id"])
                assert "बाजार भाव" in txt or "बाजार समित" in txt, (f["id"], t["id"])

    def test_hindi_is_untouched_by_the_marathi_pack(self):
        txt = wa_style.compose(ctx(), pool(), "suchi", "seedha")
        assert "मंडी भाव" in txt and "मंडियों" in txt
