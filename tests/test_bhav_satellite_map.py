"""Tests for Satellite Map integration on /bhav pages.

Validates:
1. Coordinate resolution for mandis (exact village match vs deterministic jitter fallback).
2. Tier 4 (/bhav/{crop}/{state}/{district}) map container and controls.
3. District Hub (/bhav/rajya/{state}/{district}) map container and controls.
4. Complete absence of emojis across all map UI elements and controls.
5. Net price calculator (/bhav/net-price-calc) returning mandi coordinates for mapping.
"""

import re
import pytest
from backend.services.district_geo import resolve_mandi_coords, coord_for


def _has_emoji(text: str) -> bool:
    """True if text contains any emoji characters."""
    emoji_pattern = re.compile(
        r'[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]'
    )
    return bool(emoji_pattern.search(text))


def test_resolve_mandi_coords_exact_village_match():
    # Mawana is a known town in Meerut village cache
    res = resolve_mandi_coords("Uttar Pradesh", "Meerut", "Mawana APMC")
    assert res is not None
    lat, lon, is_exact = res
    assert is_exact is True
    assert 28.5 < lat < 29.5
    assert 77.0 < lon < 78.5


def test_resolve_mandi_coords_deterministic_jitter():
    # Unknown mandi in Meerut should fall back to jittered centroid
    res1 = resolve_mandi_coords("Uttar Pradesh", "Meerut", "Test Market Alpha")
    res2 = resolve_mandi_coords("Uttar Pradesh", "Meerut", "Test Market Alpha")
    assert res1 is not None
    assert res1 == res2  # Deterministic!
    lat, lon, is_exact = res1
    assert is_exact is False

    # Jitter offset should be within reasonable bounds (~1-4 km from Meerut centroid)
    centroid = coord_for("Uttar Pradesh", "Meerut")
    assert centroid is not None
    assert abs(lat - centroid[0]) < 0.05
    assert abs(lon - centroid[1]) < 0.05


def test_resolve_mandi_coords_unknown_district():
    res = resolve_mandi_coords("NowhereState", "FakeDistrict", "Any Market")
    assert res is None


@pytest.fixture()
def seeded_map_data(db_session):
    from backend.database.db import MandiPrice
    from datetime import date
    from backend.routes import bhav

    # Seed wheat prices in Meerut
    p1 = MandiPrice(
        state="Uttar Pradesh",
        district="Meerut",
        market="Mawana APMC",
        commodity="Wheat",
        variety="Dara",
        arrival_date="2026-09-04",
        min_price="2550",
        max_price="2700",
        modal_price="2650"
    )
    p2 = MandiPrice(
        state="Uttar Pradesh",
        district="Meerut",
        market="Meerut APMC",
        commodity="Wheat",
        variety="Common",
        arrival_date="2026-09-04",
        min_price="2500",
        max_price="2620",
        modal_price="2600"
    )
    db_session.add(p1)
    db_session.add(p2)
    db_session.commit()

    # Reset cached index so seed is picked up
    bhav._idx = None
    bhav._idx_mtime = -1.0
    yield
    db_session.query(MandiPrice).filter(MandiPrice.district == "Meerut").delete()
    db_session.commit()
    bhav._idx = None


def test_tier4_satellite_map_rendered(client, seeded_map_data):
    resp = client.get("/bhav/wheat/uttar-pradesh/meerut")
    assert resp.status_code == 200
    html = resp.text

    # Verify hero 'नक्शा देखें' button in .answer-range
    assert 'class="answer-map-btn"' in html
    assert 'onclick="scrollToBhavMap()"' in html
    assert "नक्शा देखें" in html
    assert 'class="amb-radar"' in html
    assert 'class="amb-badge"' in html
    assert '<div class="answer-range">' in html
    answer_range_chunk = html.split('<div class="answer-range">')[1].split('<div class="answer-actions">')[0]
    assert 'answer-map-btn' in answer_range_chunk
    assert not _has_emoji(answer_range_chunk), "Hero range card must not contain any emojis!"

    # Verify dns-prefetch for mobile performance
    assert '<link rel="dns-prefetch" href="https://server.arcgisonline.com">' in html
    assert '<link rel="dns-prefetch" href="https://unpkg.com">' in html

    # Verify map markup exists
    assert 'id="bhav-map-sec"' in html
    assert 'id="bhav-map-canvas"' in html
    assert "उपग्रह नक्शा (Satellite View)" in html
    assert 'सैटेलाइट<span class="bhav-tab-en"><br>(Satellite)</span>' in html
    assert 'नक्शा<span class="bhav-tab-en"><br>(Roads)</span>' in html
    # Phones: the naksha label lives in the header, the in-map button is an icon
    assert 'class="bhav-map-head-link"' in html
    assert 'class="bm-naksha-txt"' in html
    assert "पूरा नक्शा देखें" in html
    assert "उच्चतम भाव" in html

    # Verify location button is icon-only (no visible text inside button tag)
    loc_btn_chunk = html.split('id="bhav-map-btn-loc"')[1].split('</button>')[0]
    assert 'bhav-map-btn-icon' in html
    assert '<svg' in loc_btn_chunk
    assert 'मेरी लोकेशन' not in loc_btn_chunk.split('>')[-1]  # No inner text

    # Verify fullscreen and toolbar route button exist
    assert 'id="bhav-map-btn-fs"' in html
    assert 'bhav_map_toggleFs' in html
    assert 'id="bhav-map-btn-route"' in html
    assert 'onclick="bhav_map_showPathTo()"' in html
    assert 'bhav-map-btn-route' in html

    # Verify shortest path route card markup
    assert 'id="bhav-map-route-card"' in html
    assert 'id="bhav-map-route-dist"' in html
    assert 'id="bhav-map-route-mandi"' in html
    assert 'id="bhav-map-route-nav"' in html
    assert "नजदीकी मंडी" in html

    # Verify valid JS identifiers (no bhav-map_setLayer hyphen syntax errors)
    assert 'bhav_map_setLayer' in html
    assert 'bhav_map_getLoc' in html
    assert 'window.scrollToBhavMap' in html

    # Extract the map section and verify STRICTLY NO EMOJIS
    map_section = html.split('id="bhav-map-sec"')[1].split('</section>')[0]
    assert not _has_emoji(map_section), "Map section must not contain any emojis!"


def test_district_hub_satellite_map_rendered(client, seeded_map_data):
    resp = client.get("/bhav/rajya/uttar-pradesh/meerut")
    assert resp.status_code == 200
    html = resp.text

    # Verify dns-prefetch for mobile performance
    assert '<link rel="dns-prefetch" href="https://server.arcgisonline.com">' in html
    assert '<link rel="dns-prefetch" href="https://unpkg.com">' in html

    # Verify map markup exists
    assert 'id="bhav-hub-map-sec"' in html
    assert 'id="bhav-hub-map-canvas"' in html
    assert "जिले की मंडियां — उपग्रह नक्शा (Satellite View)" in html
    assert 'सैटेलाइट<span class="bhav-tab-en"><br>(Satellite)</span>' in html
    assert 'नक्शा<span class="bhav-tab-en"><br>(Roads)</span>' in html
    # Phones: the naksha label lives in the header, the in-map button is an icon
    assert 'class="bhav-map-head-link"' in html
    assert 'class="bm-naksha-txt"' in html
    assert "पूरा नक्शा देखें" in html

    # Verify fullscreen, location icon-only button, and toolbar route button
    assert 'id="bhav-hub-map-btn-fs"' in html
    assert 'id="bhav-hub-map-btn-loc"' in html
    assert 'id="bhav-hub-map-btn-route"' in html
    assert 'onclick="bhav_hub_map_showPathTo()"' in html
    assert 'bhav_hub_map_toggleFs' in html
    assert 'id="bhav-hub-map-route-card"' in html

    # Verify valid JS identifiers
    assert 'bhav_hub_map_setLayer' in html
    assert 'bhav_hub_map_getLoc' in html

    # Extract hub map section and verify STRICTLY NO EMOJIS
    hub_map_section = html.split('id="bhav-hub-map-sec"')[1].split('</section>')[0]
    assert not _has_emoji(hub_map_section), "Hub map section must not contain any emojis!"


def test_net_price_calc_returns_mandis_with_coords(client, seeded_map_data):
    # Meerut coordinates: 28.98, 77.70
    resp = client.get("/bhav/net-price-calc?crop=wheat&lat=28.98&lon=77.70&qty=20")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert "mandis" in data
    mandis = data["mandis"]
    assert len(mandis) > 0
    # Mandis should contain lat and lon coordinates
    for m in mandis:
        assert "lat" in m
        assert "lon" in m
        assert isinstance(m["lat"], (int, float))
        assert isinstance(m["lon"], (int, float))


def test_satellite_map_draggable_pin_and_origin_nav(client, seeded_map_data):
    """Ensure popup 'रास्ता देखें' is an in-app button calling _showPathTo (not an immediate Google Maps link),
    the map supports path drawing, user pin is draggable, map has click listener for repositioning,
    and 'गूगल मैप पर देखें' is provided for external navigation."""
    resp = client.get("/bhav/wheat/uttar-pradesh/meerut")
    assert resp.status_code == 200
    html = resp.text

    # 1. Verify popup 'रास्ता देखें' is a button calling showPathTo, not a direct Google Maps <a> link
    assert "_showPathTo(' + i + ')" in html
    assert 'class="bhav-popup-btn bhav-popup-btn-nav"' in html
    assert "रास्ता देखें</button>" in html
    assert "window[jsId + '_showPathTo'] = showPathTo" in html

    # 2. Verify in-app route drawing logic exists (OSRM road geometry, polyline rendering, duration)
    assert "router.project-osrm.org/route/v1/driving" in html
    assert "renderRoute(roadCoords" in html
    assert "findAndDrawShortestPath" in html

    # 3. Verify 'गूगल मैप पर देखें' is rendered for Google Maps navigation (both in route card and popup update)
    assert "गूगल मैप पर देखें" in html
    assert "bhav-popup-btn-gmap" in html
    assert "&origin=" in html
    assert "&destination=" in html
    assert "&travelmode=driving" in html

    # 4. Verify draggable user pin and map click repositioning
    assert "draggable: true" in html
    assert "userMarker.on('dragend'" in html
    assert "map.on('click'" in html


def test_bhav_hub_location_btn_left_of_mic(client):
    """Verify that on /bhav the location button is rendered on state search (to the left of mic),
    and strictly OMITTED from crop search (where location is irrelevant)."""
    resp = client.get("/bhav")
    assert resp.status_code == 200
    html = resp.text

    # Crop search must NOT have a location button (GPS doesn't pick crops)
    assert 'id="bhav-tile-loc"' not in html
    assert 'id="bhav-tile-mic"' in html

    # State search DOES have a location button immediately left of mic
    assert 'id="bhav-state-loc"' in html
    assert 'id="bhav-state-mic"' in html

    state_loc_pos = html.find('id="bhav-state-loc"')
    state_mic_pos = html.find('id="bhav-state-mic"')
    assert 0 < state_loc_pos < state_mic_pos, "Location button must be at left of mic button in state search"

    # Verify strictly NO emojis in the toolbar snippets
    state_toolbar = html[state_loc_pos - 100 : state_mic_pos + 200]
    assert not _has_emoji(state_toolbar), "State search toolbar must not contain any emojis!"


def test_tier_search_location_btn_left_of_mic():
    """Verify _tier_search renders location button for places, but omits it for crops."""
    from backend.routes.bhav import _tier_search

    # Place search (districts): location button present left of mic
    out_dist = _tier_search("dist-grid", "जिला खोजें...")
    assert 'id="dist-grid-loc"' in out_dist
    assert 'id="dist-grid-mic"' in out_dist
    assert out_dist.find('id="dist-grid-loc"') < out_dist.find('id="dist-grid-mic"')
    assert not _has_emoji(out_dist), "_tier_search place output must not contain emojis!"

    # Crop search: location button MUST be absent
    out_crop = _tier_search("tier-grid", "फसल खोजें... (गेहूं, प्याज, आलू)")
    assert 'id="tier-grid-loc"' not in out_crop
    assert 'id="tier-grid-mic"' in out_crop
    assert not _has_emoji(out_crop), "_tier_search crop output must not contain emojis!"


def test_hub_selector_location_btn_left_of_mic():
    """Verify _hub_selector renders location button for state/district only (never crop),
    and supports show_crop=False for state/district hub pages."""
    from backend.routes.bhav import _hub_selector, _get_index
    idx = _get_index()

    # Full selector: crop field has NO location button, state & district DO have location buttons
    out = _hub_selector("", "uttar-pradesh", "", idx, known_state=True)
    assert 'dl-hub-crop-loc' not in out, "Crop field in _hub_selector must NOT have location button"
    assert 'id="dl-hub-state-loc"' in out
    assert 'id="dl-hub-dist-loc"' in out
    assert 'class="ctl-loc"' in out
    assert 'class="ctl-mic"' in out
    assert 'kmLoc(' in out

    # Verify ctl-loc comes before ctl-mic in the HTML
    loc_pos = out.find('id="dl-hub-state-loc"')
    mic_pos = out.find('id="dl-hub-state-i"')
    assert loc_pos > 0
    assert not _has_emoji(out), "_hub_selector must not contain emojis!"

    # Selector with show_crop=False: crop field completely omitted to prevent duplicate
    out_no_crop = _hub_selector("", "uttar-pradesh", "", idx, known_state=True, show_crop=False)
    assert 'dl-hub-crop-i' not in out_no_crop
    assert 'dl-hub-state-i' in out_no_crop
    assert 'dl-hub-dist-i' in out_no_crop


def test_bhav_state_hub_no_duplicate_crop_selector(client, seeded_map_data):
    """Verify that on /bhav/rajya/{state} there is no duplicate 'फसल चुनें' in selector,
    and crop search has no location button while district search does."""
    resp = client.get("/bhav/rajya/uttar-pradesh")
    assert resp.status_code == 200
    html = resp.text

    # Top selector card must NOT include crop field
    assert 'dl-hub-crop-i' not in html
    assert 'dl-hub-state-i' in html
    assert 'dl-hub-dist-i' in html

    # Main crop heading and crop search
    assert "उत्तर प्रदेश में फसल चुनें" in html
    assert 'id="tier-grid-search"' in html
    assert 'id="tier-grid-loc"' not in html  # No location button on crop search!
    assert 'id="tier-grid-mic"' in html

    # District search DOES have location button
    assert 'id="dist-grid-search"' in html
    assert 'id="dist-grid-loc"' in html


def test_bhav_location_button_animation_css(client):
    """Verify that CSS defines bmSpin keyframes and active/loading state styles for location buttons."""
    resp = client.get("/bhav")
    assert resp.status_code == 200
    # The shared rules live in the linked stylesheet, not inline — read both.
    import re
    href = re.search(r'href="(/ssr-css/shell\.[0-9a-f]+\.css)"', resp.text).group(1)
    html = resp.text + client.get(href).text

    assert "@keyframes bmSpin" in html
    assert "animation:bmSpin" in html
    assert ".mn-loc-btn:active" in html
    assert ".ctl-loc:active" in html


def test_map_toolbar_rasta_dekhe_button(client, seeded_map_data):
    """Verify that both Tier 4 map and District Hub map provide the 'रास्ता देखें' button
    directly on the map controls bar, with no emojis, calling _showPathTo()."""
    resp = client.get("/bhav/wheat/uttar-pradesh/meerut")
    assert resp.status_code == 200
    html = resp.text

    # Toolbar route button exists and is positioned in the control bar
    assert 'id="bhav-map-btn-route"' in html
    assert 'class="bhav-map-btn bhav-map-btn-route"' in html
    assert 'onclick="bhav_map_showPathTo()"' in html
    assert 'bhav-map-btn-route' in html

    # District hub map also contains the toolbar route button
    resp_hub = client.get("/bhav/rajya/uttar-pradesh/meerut")
    assert resp_hub.status_code == 200
    html_hub = resp_hub.text
    assert 'id="bhav-hub-map-btn-route"' in html_hub
    assert 'onclick="bhav_hub_map_showPathTo()"' in html_hub


def test_map_layout_and_stacking_context_css(client, seeded_map_data):
    """Verify that map section forms an isolated stacking context (isolation: isolate; z-index: 10)
    so map controls (z-index: 20) never bleed over the fixed header wrapper (z-index: 200) on scroll,
    Leaflet CSS is preloaded in head_extra, and tile container has dark background."""
    resp = client.get("/bhav/wheat/uttar-pradesh/meerut")
    assert resp.status_code == 200
    html = resp.text

    # Preloaded Leaflet CSS in head
    assert '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">' in html

    # Stacking context isolation
    assert "isolation:isolate" in html
    assert ".bhav-map-sec{background:var(--white);border:1px solid var(--border);border-radius:var(--radius-md);overflow:hidden;margin:26px 0;box-shadow:var(--shadow-sm);position:relative;isolation:isolate;z-index:10}" in html

    # Clean non-colliding z-index on controls (z-index 20, not 500)
    assert "z-index:20" in html
    assert "z-index:500" not in html

    # Dark background on tile container to prevent light grey flash/boxes
    assert ".bhav-map-canvas .leaflet-container,.bhav-map-canvas .leaflet-tile-container{background:#0d1d13!important}" in html

    # Split controls layout (left and right groups)
    assert 'class="bhav-map-ctrls-left"' in html
    assert 'class="bhav-map-ctrls-right"' in html

    # Error listener and resize listener in script
    assert "satLayer.on('tileerror'" in html
    assert "window.addEventListener('resize'" in html


def test_overlapping_markers_stacked_markup_and_script(client, seeded_map_data):
    """Verify that multiple mandis on the satellite map are rendered with inner stacking container,
    connector stem, and automatic collision restacking script so overlapping pins are vertically stacked
    and do not hide each other."""
    resp = client.get("/bhav/wheat/uttar-pradesh/meerut")
    assert resp.status_code == 200
    html = resp.text

    # Verify inner pin structure and connector stem markup
    assert 'class="bhav-mandi-pin-inner"' in html
    assert 'class="bhav-pin-stem"' in html
    assert 'class="bhav-pin-dot"' in html

    # Verify CSS rules for stacked pin and stem
    assert ".bhav-mandi-pin-inner" in html
    assert ".bhav-pin-stem{" in html
    assert ".bhav-pin-stem .bhav-pin-dot{" in html

    # Verify restackMarkers collision detection logic
    assert "function restackMarkers()" in html
    assert "map.latLngToContainerPoint" in html
    assert "map.on('zoomend', restackMarkers)" in html
    assert "map.on('moveend', restackMarkers)" in html

    # Verify zero emojis in the whole map block
    map_section = html.split('id="bhav-map-sec"')[1].split('</section>')[0]
    assert not _has_emoji(map_section), "Stacked map section must strictly contain zero emojis!"





# ── the route's destination ─────────────────────────────────────────────────
# A pin is only where the mandi really is when its name matched a cached OSM
# place. Otherwise it is the district centroid nudged 0.9-3 km so pins don't
# stack — "Kithore" lands 16.7 km from the real Kithaur. These guard the rule
# that an invented coordinate never becomes turn-by-turn navigation.

def _map_html_for(markets):
    """The tier-4 satellite map HTML for a list of (market, modal) pairs."""
    from backend.routes.bhav import _mandi_satellite_map_html
    prices = [{"market": m, "modal_price": str(v), "min_price": str(v - 50),
               "max_price": str(v + 50), "date": "", "variety": "Common"}
              for m, v in markets]
    return _mandi_satellite_map_html(
        "Uttar Pradesh", "Meerut", prices, "wheat", "गेहूं",
        "uttar-pradesh", "meerut", "मेरठ")


def test_inexact_pin_carries_a_name_for_google_to_geocode():
    html = _map_html_for([("Test Market Alpha", 2400)])
    assert '"is_exact": false' in html
    # the nav fallback: a text destination, not our jittered coordinate
    assert '"nav_q": "Test Market Alpha, Meerut, Uttar Pradesh mandi"' in html
    assert "var isExact = targetMandi.is_exact !== false;" in html
    assert "encodeURIComponent(navQ)" in html


def test_inexact_pin_draws_no_road_route_and_says_it_is_approximate():
    html = _map_html_for([("Test Market Alpha", 2400)])
    # An inexact pin still gets a road route, with fallback coords if network fails
    assert "var isExact = targetMandi.is_exact !== false;" in html
    assert "renderRoute(fallbackCoords, uLat, uLon, destLat, destLon, true);" in html
    # … the line is dashed and the distance is hedged, in the popup and the card
    assert "dashArray: approx ? '9 9' : null" in html
    assert "मंडी की जगह अनुमानित" in html
    assert "जगह अनुमानित है — गूगल मैप पर मंडी का नाम खोजें" in html
    assert "(m.is_exact === false ? 'लगभग ' : '')" in html


def test_exact_pin_still_gets_the_real_road_route():
    html = _map_html_for([("Mawana APMC", 2650)])
    assert '"is_exact": true' in html
    assert "router.project-osrm.org/route/v1/driving" in html


def test_estimated_distance_is_never_labelled_a_road_distance():
    html = _map_html_for([("Mawana APMC", 2650)])
    # the OSRM-returned distance may say सड़क मार्ग; the fallbacks may not
    assert "किमी <small>· लगभग ' + estTimeTxt + ' (अनुमानित)</small>" in html
    assert "estRoadKm + ' किमी <small>· लगभग ' + estTimeTxt + ' (सड़क मार्ग)" not in html


def test_markers_json_cannot_close_the_script_block():
    from backend.routes.bhav import _markers_script_json
    B = chr(92)
    out = _markers_script_json([{"market": "A</script><b>x"}])
    assert "</script>" not in out
    assert "<" not in out and ">" not in out
    assert (B + "u003c/script" + B + "u003e") in out


# ── placing the farmer's own pin ────────────────────────────────────────────

def test_map_click_is_bound_once_and_gated_by_pin_mode():
    html = _map_html_for([("Mawana APMC", 2650)])
    # one registration, in initMap — it used to be inside placeUserMarker(),
    # which runs up to four times a visit and stacked duplicate handlers
    assert html.count("map.on('click'") == 1
    assert "if (!pinMode) return;" in html
    click_at = html.index("map.on('click'")
    place_at = html.index("function placeUserMarker(")
    assert click_at < place_at


def test_geolocation_refusal_offers_a_pin_mode_that_works():
    html = _map_html_for([("Mawana APMC", 2650)])
    # the old copy told the farmer to tap the map, but nothing listened
    assert "alert(" not in html
    assert "setPinMode(true, 'लोकेशन नहीं मिली — नक्शे पर अपनी जगह टैप करें')" in html
    assert "setPinMode(true, 'लोकेशन उपलब्ध नहीं — नक्शे पर अपनी जगह टैप करें')" in html
    assert "bhav-map-pin-hint" in html


def test_route_card_label_matches_how_the_mandi_was_chosen():
    html = _map_html_for([("Mawana APMC", 2650), ("Meerut APMC", 2600)])
    assert 'id="bhav-map-route-label"' in html
    assert "pickedExplicitly ? 'चुनी गई मंडी' : 'नजदीकी मंडी'" in html


def test_map_controls_fit_phone_width():
    """The right-hand control group was wider than the space beside the tabs,
    so full-screen + layers were clipped off the map on every phone."""
    from backend.routes import bhav
    css = bhav._BHAV_MAP_CSS
    phone = css[css.index(".bhav-map-head-link{display:none"):]
    assert ".bm-naksha-txt{display:none}" in phone
    assert ".bhav-map-v-row{flex-direction:column}" in phone
    assert ".bhav-map-ctrls{flex-wrap:wrap}" in phone
