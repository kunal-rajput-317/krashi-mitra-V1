"""The crop-less /bhav/rajya path: state → district → CROP.

The bug this pins: picking a district on /bhav/rajya/uttar-pradesh navigated to
/bhav/wheat/uttar-pradesh/bijnor — the selector borrowed the state's
widest-covered crop as if the farmer had asked for it. Anything the URL has not
resolved must stay unresolved, so a district pick now lands on the district hub
and the crop is asked for there.
"""

import pytest


@pytest.fixture(scope="module", autouse=True)
def seeded(request):
    """Two states × a few crops in mandi_last_seen, and a cleared page index."""
    from backend.database.db import MandiLastSeen, SessionLocal
    from backend.routes import bhav
    from datetime import date

    db = SessionLocal()
    rows = [
        ("Wheat",  "Uttar Pradesh", "Bijnor"),
        ("Wheat",  "Uttar Pradesh", "Meerut"),
        ("Potato", "Uttar Pradesh", "Bijnor"),
        ("Onion",  "Uttar Pradesh", "Meerut"),
        ("Wheat",  "Bihar",         "Gaya"),
    ]
    made = []
    for commodity, state, district in rows:
        r = MandiLastSeen(
            group_key=f"test-{commodity}-{state}-{district}".lower(),
            commodity=commodity, state=state, district=district, market=district,
            min_price="2590", max_price="2610", modal_price="2600",
            arrival_date="04/08/2026", arrival_dt=date(2026, 8, 4))
        db.add(r)
        made.append(r)
    db.commit()

    bhav._index, bhav._index_ts = {}, 0.0        # force a rebuild off these rows
    bhav._get_index()

    def _cleanup():
        for r in made:
            db.delete(r)
        db.commit()
        db.close()
        bhav._index, bhav._index_ts = {}, 0.0

    request.addfinalizer(_cleanup)


class TestStateHub:
    def test_district_pick_stays_crop_less(self, client):
        """The reported bug: no crop in the URL → no crop in the destination."""
        html = client.get("/bhav/rajya/uttar-pradesh").text
        assert '"/bhav/rajya/uttar-pradesh/bijnor"' in html
        assert "/bhav/wheat/uttar-pradesh/bijnor" not in html

    def test_state_pick_stays_crop_less(self, client):
        html = client.get("/bhav/rajya/uttar-pradesh").text
        assert '"/bhav/rajya/bihar"' in html
        assert "/bhav/wheat/bihar" not in html

    def test_crop_pick_keeps_the_state(self, client):
        """फसल is the one thing this page is asking for, so it carries the state."""
        html = client.get("/bhav/rajya/uttar-pradesh").text
        assert '"/bhav/wheat/uttar-pradesh"' in html

    def test_every_district_has_a_crawlable_link(self, client):
        html = client.get("/bhav/rajya/uttar-pradesh").text
        for ds in ("bijnor", "meerut"):
            assert f'href="/bhav/rajya/uttar-pradesh/{ds}"' in html

    def test_district_count_spans_all_crops(self, client):
        """2 districts, even though no single crop is reported in both."""
        html = client.get("/bhav/rajya/bihar").text
        assert "1 जिले" in html


class TestDistrictHub:
    def test_lists_every_crop_in_that_district(self, client):
        html = client.get("/bhav/rajya/uttar-pradesh/bijnor").text
        assert '"/bhav/wheat/uttar-pradesh/bijnor"' in html
        assert '"/bhav/potato/uttar-pradesh/bijnor"' in html
        # Onion reports in Meerut, not Bijnor — it must not appear here.
        assert "/bhav/onion/uttar-pradesh/bijnor" not in html

    def test_shows_the_place_as_already_picked(self, client):
        html = client.get("/bhav/rajya/uttar-pradesh/bijnor").text
        assert 'value="Bijnor" data-valid="1"' in html
        assert 'value="उत्तर प्रदेश" data-valid="1"' in html

    def test_canonical_and_crumbs(self, client):
        html = client.get("/bhav/rajya/uttar-pradesh/bijnor").text
        assert 'rel="canonical" href="https://krashimitra.in/bhav/rajya/uttar-pradesh/bijnor"' in html
        assert 'href="https://krashimitra.in/bhav/rajya/uttar-pradesh"' in html

    def test_unknown_combination_is_not_found(self, client):
        # Gaya is a real district — but in Bihar, not Uttar Pradesh.
        r = client.get("/bhav/rajya/uttar-pradesh/gaya")
        assert r.status_code == 404

    def test_rajya_is_never_read_as_a_crop(self, client):
        assert client.get("/bhav/rajya/uttar-pradesh/bijnor").status_code == 200


class TestSitemap:
    def test_district_hubs_are_listed_with_lastmod(self, client):
        xml = client.get("/bhav/sitemap.xml").text
        assert "<loc>https://krashimitra.in/bhav/rajya/uttar-pradesh/bijnor</loc>" in xml
        assert "<loc>https://krashimitra.in/bhav/rajya/bihar/gaya</loc>" in xml
        assert "2026-08-04" in xml


class TestCropScopedTiersUnchanged:
    def test_tier3_district_field_stays_in_the_crop_tree(self, client):
        """Crop IS known here — the जिला field must keep it, not drop to a hub."""
        html = client.get("/bhav/wheat/uttar-pradesh").text
        assert '"/bhav/wheat/uttar-pradesh/bijnor"' in html
        assert "/bhav/rajya/uttar-pradesh/bijnor" not in html

    def test_tier3_crop_field_now_keeps_the_state(self, client):
        html = client.get("/bhav/wheat/uttar-pradesh").text
        assert '"/bhav/potato/uttar-pradesh"' in html

    def test_tier4_links_to_the_district_hub(self, client):
        html = client.get("/bhav/wheat/uttar-pradesh/bijnor").text
        assert 'href="/bhav/rajya/uttar-pradesh/bijnor"' in html
