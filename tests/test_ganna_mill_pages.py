"""The per-mill tier — /ganna/{state}/{district}/{mill}.

This tier was deliberately absent for a month, on the judgement that a name, a
capacity and a registration date cannot carry 234 pages. It exists now because
two of those premises turned out to be wrong, and the tests below are mostly
about not letting them become wrong again.

THE ADDRESS IS IN THE NAME. The register has no location column, but its names
are addresses — "...लि. परिते, ता. करवीर, जि.कोल्हापूर 416211". The taluka is
the unit a cane farmer picks a mill by, and 222 of 234 names carry one. The
parse is regex over free text written by someone else, so it is pinned hard: a
naive version produced 170 "talukas" including fragments like "ंदूळवाडी".

THE PAGE IS A COMPARISON, NOT A DESCRIPTION. What makes it worth having is
rank, share and neighbours — derived from rows already held. If a page ever
renders without them it has become the thin page the tier was held back over.

AND THE GATE HAS TO KEEP WORKING. Maharashtra's register clears it almost
everywhere, so the gate looks idle here. It is not idle: it is the rule the
next state's thinner register will meet, and a change that quietly makes it
pass everything would only show up as a demotion months later.
"""

import re

import pytest

from backend.services import ganna_mill_service as svc

STATE = "maharashtra"


@pytest.fixture(scope="module")
def register():
    data = svc.load()
    if not data:
        pytest.skip("no mill register cached — run svc.refresh() to seed it")
    return data


@pytest.fixture(scope="module")
def mills(register):
    return svc.all_mills(STATE)


def title_of(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return m.group(1) if m else ""


def desc_of(html: str) -> str:
    m = re.search(r'<meta name="description" content="(.*?)">', html, re.S)
    return m.group(1) if m else ""


# ── the address hiding in the name ──────────────────────────────────────────

class TestSplitName:
    @pytest.mark.parametrize("raw, taluka", [
        ("भोगावती सहकारी साखर कारखाना लि. परिते, ता. करवीर, जि.कोल्हापूर 416211", "करवीर"),
        ("दूधगंगा वेदगंगा सहकारी साखर कारखाना लि.बिद्री, ता. कागल , जि.कोल्हापूर 416208", "कागल"),
        # No comma before जि — the taluka must still stop at it.
        ("श्री दत्त सहकारी साखर कारखाना लि.असूर्लेपोर्ले,ता. पन्हाळा जि.कोल्हापूर 416229", "पन्हाळा"),
        # ता. sits right after "लि." with no space or comma.
        ("सुधाकरराव नाईक सहकारी साखर कारखाना लि.ता.पुसद, जि.यवतमाळ", "पुसद"),
        # "जिल्हा" spelled out rather than abbreviated.
        ("हूतात्मा किसन आहिर सहकारी साखर कारखाना लि. वाळवा जिल्हा-सांगली", ""),
    ])
    def test_taluka_is_pulled_out(self, raw, taluka):
        assert svc.split_name(raw, "कोल्हापूर")["taluka"] == taluka

    def test_ta_ji_written_once_means_taluka_equals_district(self):
        """"ता.जि.सातारा" — one word doing duty for both."""
        raw = "अजिंक्यतारा सहकारी साखर कारखाना लि. शाहूनगर,पो.शेंद्रे, ता.जि.सातारा-415 519"
        assert svc.split_name(raw, "सातारा")["taluka"] == "सातारा"

    @pytest.mark.parametrize("raw", [
        # ता inside an ordinary word must never be read as the marker. This is
        # the bug that produced "ंदूळवाडी" and "ंभाळे" as talukas.
        "श्री.तात्यासाहेब कोरे वारणा सहकारी साखर कारखाना लि. वारणानगर",
        "फलटण तालुका सहकारी साखर कारखाना, साखरवाडी",
        "तुळजाभवानीदेवी सहकारी साखर कारखाना",
    ])
    def test_ta_inside_a_word_is_not_a_taluka(self, raw):
        got = svc.split_name(raw, "पुणे")["taluka"]
        assert got in ("", "साखरवाडी") or len(got) >= 3
        assert "ंदूळवाडी" not in got and "ंभाळे" not in got

    def test_a_pin_split_by_a_space_is_still_a_pin(self):
        raw = "सागर सहकारी साखर कारखाना लि., पो. तिर्थपुरी, ता,घनसावंगी , जि.जालना-431 209"
        assert svc.split_name(raw, "जालना")["pin"] == "431209"

    def test_a_four_digit_year_is_not_a_pin(self):
        assert svc.split_name("कोणतीही मिल 1955", "पुणे")["pin"] == ""

    def test_never_raises_on_junk(self):
        for raw in ("", None, "ता.", "जि.", "%%%", "ता.जि."):
            svc.split_name(raw, "")          # must not raise

    def test_the_shipped_register_parses_at_the_measured_rate(self, mills):
        """222 of 234. A refactor that drops this is a regression even if every
        individual case above still passes."""
        got = sum(1 for m in mills if m.get("taluka"))
        assert got >= 220, f"taluka coverage fell to {got}/{len(mills)}"

    def test_no_parsed_taluka_is_obvious_garbage(self, mills):
        for m in mills:
            t = m.get("taluka") or ""
            if not t:
                continue
            assert not re.search(r"जि\.|जिल्हा|\d", t), f"{t!r} from {m['name']!r}"
            assert 2 <= len(t) <= 22, f"{t!r} from {m['name']!r}"


class TestAgeAndSeason:
    def test_age_from_a_register_date(self):
        import datetime
        assert svc.age_years("27-09-1955", datetime.date(2026, 9, 8)) == 70

    def test_the_day_before_the_anniversary_has_not_ticked_over(self):
        import datetime
        assert svc.age_years("27-09-1955", datetime.date(2026, 9, 26)) == 70
        assert svc.age_years("27-09-1955", datetime.date(2026, 9, 27)) == 71

    @pytest.mark.parametrize("bad", ["", "  ", "1955", "31-31-1955", "27-09-1200",
                                     "not a date", None])
    def test_an_unreadable_date_is_none_not_a_guess(self, bad):
        assert svc.age_years(bad) is None

    def test_season_tonnes_is_capacity_times_days_and_nothing_more(self):
        assert svc.season_tonnes(12000, 150) == 1_800_000
        assert svc.season_tonnes(0) == 0


# ── the gate ────────────────────────────────────────────────────────────────

class TestIndexGate:
    def test_no_capacity_means_no_index_claim(self):
        m = {"tcd": 0, "registered": "27-09-1955", "taluka": "करवीर"}
        assert not svc.indexable(m, [m, m])

    def test_a_lone_mill_has_nothing_to_be_ranked_against(self):
        m = {"tcd": 5000, "registered": "27-09-1955", "taluka": "करवीर"}
        assert not svc.indexable(m, [m])

    def test_a_name_and_a_number_alone_is_not_enough(self):
        """The thin page the tier was held back over: no place, no date."""
        m = {"tcd": 5000, "registered": "", "taluka": ""}
        assert not svc.indexable(m, [m, m])

    @pytest.mark.parametrize("extra", [{"registered": "27-09-1955"}, {"taluka": "करवीर"}])
    def test_one_fact_of_its_own_is_enough(self, extra):
        m = {"tcd": 5000, "registered": "", "taluka": "", **extra}
        assert svc.indexable(m, [m, m])

    def test_the_shipped_register_is_gated_not_waved_through(self, mills):
        """Maharashtra's register is good, so this excludes only a handful —
        but it must exclude them, and it must not exclude most of the state."""
        import collections
        byd = collections.defaultdict(list)
        for m in mills:
            byd[m["district_slug"]].append(m)
        ok = [m for m in mills if svc.indexable(m, byd[m["district_slug"]])]
        assert 0 < len(mills) - len(ok) <= 15, f"{len(ok)}/{len(mills)} indexable"


# ── the pages ───────────────────────────────────────────────────────────────

class TestMillPage:
    def test_every_mill_renders(self, client, mills):
        for m in mills:
            url = f"/ganna/{STATE}/{m['district_slug']}/{m['slug']}"
            assert client.get(url).status_code == 200, url

    def test_the_page_is_a_comparison_not_a_description(self, client, mills):
        """Rank, share and a neighbour list are the reason the tier exists."""
        m = next(x for x in mills if x["tcd"] and x["taluka"])
        html = client.get(f"/ganna/{STATE}/{m['district_slug']}/{m['slug']}").text
        assert "जिले में क्रम" in html
        assert "कुल सहकारी क्षमता" in html
        assert "राज्य में क्रम" in html
        assert "जिले की बड़ी सहकारी मिलें" in html

    def test_the_season_estimate_shows_its_arithmetic(self, client, mills):
        """A derived number a farmer cannot check is a number he should not be
        given. The page prints the multiplication and calls it an अनुमान."""
        m = next(x for x in mills if x["tcd"])
        html = client.get(f"/ganna/{STATE}/{m['district_slug']}/{m['slug']}").text
        assert "अनुमान" in html
        assert f"{m['tcd']:,} TCD × 150 दिन" in html

    def test_it_never_claims_to_know_arrears(self, client, mills):
        """Arrears are the fortnightly scanned PDF, and are NOT in this
        register. A mill page says what the mill is, never what it has paid."""
        m = mills[0]
        html = client.get(f"/ganna/{STATE}/{m['district_slug']}/{m['slug']}").text
        assert "बकाया, पर्ची या तौल का रिकॉर्ड उस रजिस्टर में नहीं होता" in html

    def test_it_says_the_register_is_co_operatives_only(self, client, mills):
        m = mills[0]
        html = client.get(f"/ganna/{STATE}/{m['district_slug']}/{m['slug']}").text
        assert "सहकारी" in html

    def test_serp_copy_fits_the_window(self, client, mills):
        """68 and 162 — the site's own budget. One name in the register is long
        enough that every title variant overflows; _fit returns the shortest,
        which is the documented behaviour, so one is tolerated and two are not.
        """
        over_t = over_d = 0
        for m in mills:
            html = client.get(f"/ganna/{STATE}/{m['district_slug']}/{m['slug']}").text
            over_t += len(title_of(html)) > 68
            over_d += len(desc_of(html)) > 162
        assert over_t <= 1, f"{over_t} titles over 68"
        assert over_d == 0, f"{over_d} descriptions over 162"

    def test_the_title_drops_the_boilerplate_not_the_place(self, client, mills):
        """"सहकारी साखर कारखाना लि." is on all 234 names and is 25 characters of
        a 68-character budget. The taluka is what differs."""
        m = next(x for x in mills
                 if x["taluka"] and "सहकारी साखर कारखाना" in x["name"] and x["tcd"])
        t = title_of(client.get(f"/ganna/{STATE}/{m['district_slug']}/{m['slug']}").text)
        assert m["taluka"] in t
        assert "सहकारी साखर कारखाना लि." not in t

    def test_most_descriptions_carry_the_capacity(self, client, mills):
        """The capacity and rank are the half not shared with 233 other pages,
        so they are the last thing _fit should give up."""
        with_cap = sum(
            1 for m in mills
            if "TCD" in desc_of(
                client.get(f"/ganna/{STATE}/{m['district_slug']}/{m['slug']}").text))
        assert with_cap >= len(mills) - 10, f"only {with_cap}/{len(mills)}"

    def test_hindi_ordinals_read_as_words_for_the_first_ten(self, client, mills):
        from backend.routes.ganna import _ord_hi
        assert _ord_hi(1) == "पहले" and _ord_hi(3) == "तीसरे" and _ord_hi(10) == "दसवें"
        assert _ord_hi(12) == "12वें"
        m = next(x for x in mills if x["tcd"])
        html = client.get(f"/ganna/{STATE}/{m['district_slug']}/{m['slug']}").text
        assert not re.search(r"[1-9]वें नंबर", html), "single-digit ordinal left as a digit"


class TestRoutingAndDiscovery:
    def test_a_wrong_district_redirects_to_the_right_one(self, client, mills):
        """The slug carries its own district, so the canonical URL is knowable
        and a stale link should land rather than die."""
        m = mills[0]
        wrong = "pune" if m["district_slug"] != "pune" else "satara"
        r = client.get(f"/ganna/{STATE}/{wrong}/{m['slug']}", follow_redirects=False)
        assert r.status_code == 301
        assert r.headers["location"].endswith(f"/{m['district_slug']}/{m['slug']}")

    def test_an_unknown_mill_falls_back_to_the_district(self, client):
        r = client.get(f"/ganna/{STATE}/kolhapur/kolhapur-deadbeef", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"].endswith("/kolhapur")

    def test_the_district_page_links_every_mill(self, client, mills):
        """A mill slug is an opaque hash — nothing discovers one that the
        district list does not point at."""
        html = client.get(f"/ganna/{STATE}/kolhapur").text
        for m in (x for x in mills if x["district_slug"] == "kolhapur"):
            assert f"/ganna/{STATE}/kolhapur/{m['slug']}" in html

    def test_the_sitemap_carries_indexable_mills_only(self, client, mills):
        import collections
        byd = collections.defaultdict(list)
        for m in mills:
            byd[m["district_slug"]].append(m)
        xml = client.get("/ganna/sitemap.xml").text
        for m in mills:
            url = f"/ganna/{STATE}/{m['district_slug']}/{m['slug']}"
            assert (url in xml) is svc.indexable(m, byd[m["district_slug"]]), url

    def test_a_gated_mill_still_renders_but_is_not_advertised(self, client, mills):
        import collections
        byd = collections.defaultdict(list)
        for m in mills:
            byd[m["district_slug"]].append(m)
        gated = [m for m in mills if not svc.indexable(m, byd[m["district_slug"]])]
        if not gated:
            pytest.skip("this register gates nothing")
        for m in gated:
            r = client.get(f"/ganna/{STATE}/{m['district_slug']}/{m['slug']}")
            assert r.status_code == 200
            assert 'content="noindex,follow"' in r.text

    def test_the_district_list_is_not_one_short(self, client, mills):
        """Slicing the top 12 and then dropping this mill leaves eleven. The
        slice has to come after the exclusion."""
        m = next(x for x in mills
                 if len([y for y in mills if y["district_slug"] == x["district_slug"]]) > 14)
        html = client.get(f"/ganna/{STATE}/{m['district_slug']}/{m['slug']}").text
        panel = html.split("जिले की बड़ी सहकारी मिलें")[1]
        assert panel.count("gn-bar-link") == 12
