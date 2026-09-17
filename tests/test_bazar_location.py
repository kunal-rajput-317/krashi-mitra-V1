"""A listing has to say WHERE the crop is.

Before 2026-09-17 the composer never asked. A listing inherited whatever
address the poster's profile carried, and most farmers never fill that in, so
cards showed no place and bazar.place_posts() — the query behind /bhav's
district slice of this feed — could never match a row.

What is pinned here is the part that is easy to break later:

  * the composer's place beats the profile's, because the crop may be lying
    somewhere other than where he registered;
  * an omitted field still falls back to the profile, so an older client (and
    the /bhav panel, which sends only state/district) keeps working;
  * `location` is DERIVED from village + district in exactly one place, so the
    string on the card can never disagree with the columns /bhav filters on;
  * a listing posted with a place is findable by place — the whole point;
  * a nonsense pin is dropped without taking the listing down with it.
"""

from datetime import datetime

import pytest


EMAIL = "bazar-place-kisan@example.com"


@pytest.fixture()
def seller(db_session):
    """A profiled account whose profile says Hardoi, Uttar Pradesh.

    The profile's place matters here: half these tests are about when it is
    used as a fallback and when the composer's own answer overrides it.
    """
    from sqlalchemy import func

    from backend.database.db import BazarPost, User, UserProfile
    from backend.utils.auth_utils import create_access_token

    def _wipe():
        rows = db_session.query(User).filter(User.email == EMAIL).all()
        stale = [u.id for u in rows]
        accts = [u.user_id for u in rows if u.user_id is not None]
        if stale:
            db_session.query(BazarPost).filter(BazarPost.users_id.in_(stale)).delete()
            if accts:
                db_session.query(UserProfile).filter(
                    UserProfile.user_id.in_(accts)).delete()
            db_session.query(User).filter(User.id.in_(stale)).delete()
            db_session.commit()

    _wipe()
    user = User(name="Place Kisan", email=EMAIL, hashed_password="x",
                is_verified=True, created_at=datetime.utcnow())
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    n = (db_session.query(func.max(UserProfile.id)).scalar() or 0) + 1
    user.user_id = n
    db_session.commit()
    db_session.add(UserProfile(
        id=n, user_id=n, name="Place Kisan", phone_number="9876500001",
        state="Uttar Pradesh", district="Hardoi", village="Rampur"))
    db_session.commit()
    yield user, {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}
    _wipe()


def _post(client, headers, **over):
    data = {"post_type": "sell", "crop": "गेहूं", "text": "20 क्विंटल गेहूं"}
    data.update(over)
    r = client.post("/bazar/posts", headers=headers, data=data)
    assert r.status_code == 200, r.text
    return r.json()["data"]


class TestCreate:
    def test_the_composers_place_beats_the_profiles(self, client, seller):
        """He registered in Hardoi; this crop is sitting in Sitapur."""
        _, headers = seller
        d = _post(client, headers, state="Uttar Pradesh", district="Sitapur",
                  village="Biswan")
        assert d["district"] == "Sitapur"
        assert d["village"] == "Biswan"
        assert d["location"] == "Biswan, Sitapur"

    def test_an_omitted_place_still_falls_back_to_the_profile(self, client, seller):
        """The /bhav panel sends no village, an old cached page sends nothing at
        all, and neither may start posting place-less rows."""
        _, headers = seller
        d = _post(client, headers)
        assert (d["state"], d["district"], d["village"]) == \
               ("Uttar Pradesh", "Hardoi", "Rampur")
        assert d["location"] == "Rampur, Hardoi"

    def test_a_new_district_does_not_borrow_the_profiles_village(self, client, seller):
        """His profile says Rampur village, Hardoi district. This lot is in
        Sitapur. "Rampur, Sitapur" would be a village that is not in that
        district — a place that does not exist, printed on the card."""
        _, headers = seller
        d = _post(client, headers, state="Uttar Pradesh", district="Sitapur")
        assert d["district"] == "Sitapur"
        assert d["village"] is None
        assert d["location"] == "Sitapur"

    def test_the_pin_is_stored_and_rounded(self, client, seller):
        _, headers = seller
        d = _post(client, headers, lat="27.4123456", lon="80.1298765")
        assert (d["lat"], d["lon"]) == (27.41235, 80.12988)

    def test_a_nonsense_pin_is_dropped_not_fatal(self, client, seller):
        """A bad coordinate must not cost the farmer his crop, price and photo.

        It is an extra on a listing whose text and price are the point, so it is
        dropped and the post goes through.
        """
        _, headers = seller
        d = _post(client, headers, lat="991", lon="80.12")
        assert d["lat"] is None and d["lon"] is None
        assert d["text"] == "20 क्विंटल गेहूं"

    def test_a_placed_listing_is_findable_by_place(self, client, seller, db_session):
        """The reason the field exists: place_posts() is the shared query behind
        /bhav/{crop}/{state}/{district}/kharidar."""
        from backend.routes import bazar

        _, headers = seller
        _post(client, headers, crop_slug="wheat", state="Uttar Pradesh",
              district="Sitapur", village="Biswan")

        found = bazar.place_posts(db_session, "sell", "wheat",
                                  "uttar pradesh", "  SITAPUR ")
        assert [p.village for p in found] == ["Biswan"]


class TestEdit:
    def test_a_wrong_district_can_be_fixed(self, client, seller):
        _, headers = seller
        pid = _post(client, headers, state="Uttar Pradesh",
                    district="Sitapur", village="Biswan")["id"]

        r = client.patch(f"/bazar/posts/{pid}", headers=headers,
                         json={"district": "Hardoi"})
        assert r.status_code == 200, r.text
        post = r.json()["data"]["post"]
        assert post["district"] == "Hardoi"
        # Derived, never sent — the card's line follows the column.
        assert post["location"] == "Biswan, Hardoi"

    def test_an_edit_that_leaves_the_place_out_leaves_it_alone(self, client, seller):
        """Same model_fields_set rule as the numbers: absent is not null. A
        farmer fixing a price must not lose the district he set."""
        _, headers = seller
        pid = _post(client, headers, state="Uttar Pradesh",
                    district="Sitapur", village="Biswan")["id"]

        r = client.patch(f"/bazar/posts/{pid}", headers=headers, json={"price": 2400})
        post = r.json()["data"]["post"]
        assert (post["district"], post["village"]) == ("Sitapur", "Biswan")

    def test_a_place_only_edit_still_counts_as_a_change(self, client, seller):
        """It must not fall through to the "कुछ बदला नहीं" branch, which returns
        success without saving anything."""
        _, headers = seller
        pid = _post(client, headers)["id"]

        r = client.patch(f"/bazar/posts/{pid}", headers=headers,
                         json={"village": "Biswan"})
        assert r.json()["data"]["post"]["village"] == "Biswan"
        assert client.get(f"/bazar/posts/{pid}",
                          headers=headers).json()["data"]["village"] == "Biswan"


class TestPlacesApi:
    def test_the_pickers_are_fed_from_the_mandi_index(self, client):
        """The composer's राज्य/ज़िला options and bazar.place_posts() have to
        agree about how a district is spelled, so the options come from the
        index the /bhav pages are built from — not a second hand-kept list."""
        r = client.get("/bhav/api/places")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert isinstance(body["places"], list)
        for st in body["places"]:
            assert st["n"] and isinstance(st["d"], list)
            # [what we store, what he reads] — the Hindi label may fall back to
            # the English name, but the pair itself is the contract.
            assert all(len(pair) == 2 and pair[0] for pair in st["d"])


def _page():
    import io as _io
    from pathlib import Path
    return _io.open(Path(__file__).resolve().parents[1] / "frontend" / "krashi_bajar.html",
                    encoding="utf-8").read()


class TestPickerChrome:
    """The composer's own markup. Cheap to assert, and each one of these is a
    decision that cost a round of real-device feedback to arrive at."""

    def test_the_map_is_satellite_with_esris_zoom_ceiling_split(self):
        """Imagery, not a street map — a farmer finds his खेत by looking at
        the shape of the plot.

        maxNativeZoom 18 / maxZoom 20 is NOT decoration: over most of rural
        India Esri holds no picture past z18 and answers z19 with a grey "Map
        data not yet available" PNG under HTTP 200, so nothing errors and
        Leaflet paints grey over the field. naksha.py carries the identical
        split; if one moves, both must.
        """
        html = _page()
        assert "World_Imagery/MapServer" in html
        assert "World_Boundaries_and_Places" in html, "labels: bare imagery cannot be navigated"
        assert "maxNativeZoom: 18" in html and "maxZoom: 20" in html
        assert "tile.openstreetmap.org" not in html, "the picker went back to a street map"

    def test_the_composers_close_button_lives_in_the_sticky_header(self):
        """It used to be position:absolute inside .bz-modal — which is itself
        the scrolling box — so on a form this long the way out scrolled off the
        screen. Measured at 390px: it now moves 0px between the top of the form
        and the bottom."""
        html = _page()
        i_title = html.index('<div class="bz-modal-title">\n      <span id="cmp-title"')
        i_close = html.index('onclick="closeComposer()"')
        i_end = html.index("</div>", i_title)
        assert i_title < i_close < i_end, "the ✕ is outside the sticky title row again"
        assert "#composer-overlay .bz-modal-title {" in html
        assert "position: sticky" in html

    def test_photos_are_downscaled_in_the_phone(self):
        """A 4000x3000 phone JPEG is 4-8MB and nothing here ever shows it wider
        than a 760px column. Verified in Edge: 10.9MB -> 532KB WebP at
        1600x1200. The 5GB egress overrun that suspended this site once is the
        reason the number matters."""
        html = _page()
        assert "UPLOAD_MAX_EDGE = 2048" in html, "photos got smaller than a buyer can judge"
        assert "UPLOAD_QUALITY  = 0.88" in html
        assert "async function shrinkImage(file)" in html
        # EXIF: canvas.drawImage ignores rotation, so a portrait photo would be
        # stored on its side unless the decode applies it.
        assert "imageOrientation: 'from-image'" in html
        # A failed shrink must fall back to the original, never to no upload.
        assert "return file;" in html

    def test_the_slow_buttons_say_they_are_working(self):
        """A GPS fix takes seconds on a weak signal and a button that only
        greys out reads as broken."""
        html = _page()
        assert "@keyframes bz-loc-spin" in html
        assert ".bz-loc-btn.busy::before" in html
        assert "function locBusy(" in html
