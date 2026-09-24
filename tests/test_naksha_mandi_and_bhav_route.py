"""Tests for Naksha Mandi Explorer and Bhav Flowing Route Animation / Fullscreen Cross Button.
"""

import pytest
from backend.routes.naksha import _mandi_cache


@pytest.fixture()
def seeded_meerut_mandi(db_session):
    from backend.database.db import MandiPrice
    from backend.routes import bhav

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
        commodity="Mustard",
        variety="Black",
        arrival_date="2026-09-04",
        min_price="5100",
        max_price="5400",
        modal_price="5300"
    )
    db_session.add(p1)
    db_session.add(p2)
    db_session.commit()

    _mandi_cache.clear()
    bhav._idx = None
    bhav._idx_mtime = -1.0
    yield
    db_session.query(MandiPrice).filter(MandiPrice.district == "Meerut").delete()
    db_session.commit()
    _mandi_cache.clear()
    bhav._idx = None


def test_naksha_mandi_api_endpoint(client, seeded_meerut_mandi):
    resp = client.get("/api/naksha/mandis?state=uttar-pradesh&district=meerut")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["state"] == "Uttar Pradesh"
    assert data["district"] == "Meerut"
    mandis = data["mandis"]
    assert len(mandis) >= 2

    # Verify mandi payload properties
    mawana = next((m for m in mandis if "Mawana" in m["market"]), None)
    assert mawana is not None
    assert "lat" in mawana and "lon" in mawana
    assert isinstance(mawana["lat"], float)
    assert isinstance(mawana["lon"], float)
    assert mawana["is_exact"] is True
    assert "top_crops" in mawana
    assert len(mawana["top_crops"]) > 0
    assert "bhav_url" in mawana
    assert mawana["bhav_url"].startswith("/bhav/")


def test_naksha_page_contains_mandi_toggle_and_stacking_isolation(client):
    resp = client.get("/naksha/uttar-pradesh/meerut")
    assert resp.status_code == 200
    html = resp.text

    # Verify mandi explorer toggle button exists
    assert 'id="nk-mandi-toggle-btn"' in html
    assert 'मंडी देखें' in html
    assert 'toggleMandis()' in html
    assert 'renderMandiMarkers' in html

    # Verify stacking context isolation to avoid bleeding over site header
    assert 'isolation: isolate' in html or 'isolation:isolate' in html
    assert '.nk-app-map-wrap' in html


def test_bhav_flowing_route_animation_and_lifted_card(client, seeded_meerut_mandi):
    resp = client.get("/bhav/wheat/uttar-pradesh/meerut")
    assert resp.status_code == 200
    html = resp.text

    # Verify route flow CSS animation
    assert ".bhav-route-flow" in html
    assert "animation:bhavRouteFlow" in html
    assert "@keyframes bhavRouteFlow" in html

    # Verify lifted route card bottom margin
    assert ".bhav-map-route-card{position:absolute;bottom:26px" in html
    assert "z-index:35" in html

    # Verify routeFlowLayer in JS
    assert "routeFlowLayer = L.polyline(coords" in html
    assert "className: 'bhav-route-flow'" in html
    assert "if (routeFlowLayer && map) map.removeLayer(routeFlowLayer);" in html


def test_bhav_route_flow_is_smooth_and_one_time(client, seeded_meerut_mandi):
    """The reveal is rAF-driven, waits for the fitBounds zoom, and runs once.

    A CSS transition fired before the map settled used to stutter: Leaflet
    reprojects the path on every zoom step, which left the dash pattern stale.
    """
    html = client.get("/bhav/wheat/uttar-pradesh/meerut").text

    # Starts only after the fitBounds zoom has settled (with a fallback kick)
    assert "map.on('moveend', kickFlow);" in html
    assert "setTimeout(kickFlow, 3000);" in html
    # The view flies to the route instead of teleporting, and the reveal
    # only starts once that flight lands.
    assert "map.flyToBounds(routeBounds, fitOpts);" in html
    # Nothing is painted before the reveal begins
    assert "el.style.visibility = 'hidden';" in html
    # Frame-by-frame off the live path length, not a fixed CSS transition
    assert "routeAnimRaf = requestAnimationFrame(frame);" in html
    assert "probe.getTotalLength() || len0" in html
    # One time: the comet fades out and its layer is removed
    assert "classList.add('is-done')" in html
    assert "@keyframes bhavRouteFlow{from{opacity:.95}to{opacity:0}}" in html
    # Honours reduced motion
    assert "prefers-reduced-motion: reduce" in html


def test_naksha_route_panel_takes_both_ends(client):
    """/naksha asks for a start AND a destination — /bhav's map cannot.

    On /bhav the destination is the mandi the page is about, so one tap is
    enough. A state map has no such implied destination.
    """
    html = client.get("/naksha/uttar-pradesh").text

    # A side panel with two fields, not a one-tap route
    assert 'id="nk-route-panel"' in html
    assert 'id="nk-rp-from"' in html
    assert 'id="nk-rp-to"' in html
    assert 'id="nk-rp-swap"' in html
    assert "if(isOpen) {{ nkPanelOpen(false); return; }}" not in html  # f-string braces are resolved
    assert "nkPanelOpen(true);" in html

    # Four ways to fill a field: GPS, map tap, district suggestion, free text
    assert 'data-from="gps"' in html
    assert 'data-pick="from"' in html and 'data-pick="to"' in html
    assert 'data-to="mandi"' in html
    assert "function nkSuggest(which)" in html
    assert "nominatim.openstreetmap.org/search" in html
    # The picker is an overlay so district/measure handlers stay out of it
    assert 'id="nk-pick-overlay"' in html
    assert "map.containerPointToLatLng(L.point(ev.clientX - r.left" in html

    # Routing itself is unchanged: OSRM, straight-line fallback, one-time flow
    assert "router.project-osrm.org/route/v1/driving/" in html
    assert "function nkFallback(a, b, straight)" in html
    # Google-style result: casing + line, a marker at each end, and the
    # alternates OSRM returns left on the map in grey with their travel time
    assert "color: '#1967d2', weight: 9" in html
    assert "color: '#4285f4', weight: 5.5" in html
    assert 'class="nk-rt-start"' in html
    assert "function nkSelectRoute(idx)" in html
    assert "&alternatives=true" in html
    assert "nk-rt-alt-label" in html
    assert "className: 'nk-route-flow'" in html
    assert "nkRouteRaf = requestAnimationFrame(frame);" in html
    assert ".nk-bottom-drawer.active ~ .nk-route-card { display: none; }" in html


def test_route_geometry_detail_scales_with_distance(client, seeded_meerut_mandi):
    """Long hauls ask OSRM for simplified geometry — 69KB vs 1.5KB at ~490km.

    The extra points are invisible at the zoom a long route fits into, and the
    bytes land on a rural connection.
    """
    bhav = client.get("/bhav/wheat/uttar-pradesh/meerut").text
    assert "var ovDetail = straightDist > 60 ? 'simplified' : 'full';" in bhav
    assert "'?overview=' + ovDetail + '&geometries=geojson'" in bhav

    naksha = client.get("/naksha/uttar-pradesh").text
    assert "var ovDetail = straight > 60 ? 'simplified' : 'full';" in naksha


def test_locate_button_shows_a_busy_ring(client, seeded_meerut_mandi):
    """A spinning crosshair looks static (90° symmetry) — spin a ring instead.

    And the busy state has to end: the cached-fix path used to leave the /bhav
    button in .loading forever, because only the error branch cleared it.
    """
    bhav = client.get("/bhav/wheat/uttar-pradesh/meerut").text
    assert ".bhav-map-btn-icon.loading::after{content:'';position:absolute" in bhav
    assert "animation:bmSpin .8s linear infinite" in bhav
    # The containing block sits on the base rule, so .loading cannot outrank
    # .bhav-map-btn-loc and knock the button out of its corner.
    assert ".bhav-map-btn{position:relative;display:inline-flex" in bhav
    assert ".bhav-map-btn-icon.loading{position:relative}" not in bhav
    # Cleared on every outcome, including a cached fix
    assert "function setLocBtnBusy(on)" in bhav
    assert bhav.count("setLocBtnBusy(false)") >= 4

    naksha = client.get("/naksha/uttar-pradesh").text
    assert ".nk-my-loc-btn.loading::after {" in naksha
    assert "animation: nkSpin 0.8s linear infinite;" in naksha
    # The route button waits on the same fix, so the GPS button shows it
    assert "if(fabGps) fabGps.classList.add('loading');" in naksha


def test_naksha_locate_btn_clears_zoom_stack(client):
    """The locate button stacks above Leaflet's zoom, not on top of the + key.

    Leaflet's bottom-right zoom control ends 91px above the wrap's bottom once
    the attribution strip is counted, so the old bottom:80px put the button
    straight over the + button.
    """
    html = client.get("/naksha/uttar-pradesh").text
    assert "bottom: 102px;" in html and "right: 10px;" in html
    assert ".nk-my-loc-btn { bottom: 100px; right: 10px;" in html


def test_bhav_map_control_layout(client, seeded_meerut_mandi):
    """Controls sit where the design puts them, not all in one top row.

    Top-left: the two-line satellite/roads toggle. Top-right: the full-map link
    with fullscreen beside it, and the overflow menu stacked under them.
    Bottom-left: the route button. Bottom-right: locate, above Leaflet's zoom.
    """
    html = client.get("/bhav/wheat/uttar-pradesh/meerut").text

    # Route and locate are anchored to the map, not to the top control row
    ctrls = html.split('class="bhav-map-ctrls"')[1].split('bhav-map-route-card')[0]
    route_at = ctrls.index("bhav-map-btn-route")
    loc_at = ctrls.index("bhav-map-btn-loc")
    ctrls_end = ctrls.index("</div>\n    <button")
    assert route_at > ctrls_end and loc_at > route_at
    assert ".bhav-map-btn-route{position:absolute;bottom:16px;left:14px" in html
    assert ".bhav-map-btn-loc{position:absolute;bottom:20px;right:68px" in html

    # Right side is a stack: [full map][fullscreen] over [overflow]
    assert ".bhav-map-v-stack{display:flex;flex-direction:column;align-items:flex-end" in html
    assert 'id="bhav-map-btn-more"' in html
    assert 'class="bhav-map-more-wrap"' in html

    # The overflow menu's items are real actions, wired to the map
    assert "_menuAct('reset')" in html
    assert "_menuAct('pin')" in html
    assert "_menuAct('hide')" in html
    assert "if (what === 'reset') resetViewFn();" in html


def test_bhav_fullscreen_cross_button_transformation(client, seeded_meerut_mandi):
    resp = client.get("/bhav/wheat/uttar-pradesh/meerut")
    assert resp.status_code == 200
    html = resp.text

    # Fullscreen button exists
    assert 'id="bhav-map-btn-fs"' in html
    assert 'id="bhav-map-fs-icon"' in html

    # The glyph is stroke-drawn, so the button needs .bm-icon-stroke — over the
    # fill-only .bm-icon these lines rendered an empty button in fullscreen.
    assert ".bm-icon-stroke{fill:none;stroke:currentColor" in html
    assert 'class="bm-icon bm-icon-stroke" id="bhav-map-fs-icon"' in html
    assert "fsIcon.innerHTML = '<line x1=\"18\" y1=\"6\" x2=\"6\" y2=\"18\"/>" in html
    assert "फुल स्क्रीन बंद करें (Esc)" in html

    # Esc key listener exists
    assert "e.key === 'Escape'" in html


def test_progressive_3tier_lod_map_loading(client, seeded_meerut_mandi):
    # 1. Bhav satellite map contains low-poly instant base (z=7) and optimized mid/high layers
    resp_bhav = client.get("/bhav/wheat/uttar-pradesh/meerut")
    assert resp_bhav.status_code == 200
    html_bhav = resp_bhav.text

    assert "lowSatLayer = L.tileLayer" in html_bhav
    assert "maxNativeZoom: 7" in html_bhav
    assert "updateWhenIdle: true" in html_bhav
    assert "keepBuffer: 1" in html_bhav

    # The tiers are staged, not stacked: high-res waits for the z7 base, labels
    # wait for the high-res, so the instant base is not queued behind them.
    assert "lowSatLayer.once('load', addHiResTier);" in html_bhav
    assert "setTimeout(addHiResTier, 500);" in html_bhav
    assert "satLayer.once('load', addLabelTier);" in html_bhav

    # Leaflet is fetched with the page, and both hosts are connected early
    assert '<link rel="preload" as="script" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js">' in html_bhav
    assert '<link rel="preconnect" href="https://server.arcgisonline.com">' in html_bhav

    # 2. Naksha map contains lowSatLayer and dynamic boundary zoom LOD
    resp_naksha = client.get("/naksha/uttar-pradesh/meerut")
    assert resp_naksha.status_code == 200
    html_naksha = resp_naksha.text

    assert "var lowSatLayer = L.tileLayer" in html_naksha
    assert "updateWhenIdle: true" in html_naksha
    assert "map.on('zoomend'" in html_naksha


def test_mandi_3tier_lod_and_cluster_badges(client):
    resp = client.get("/naksha/uttar-pradesh")
    assert resp.status_code == 200
    html = resp.text

    # 1. Verify CSS rules for all 3 LOD tiers
    assert ".nk-mandi-cluster-badge" in html
    assert ".nk-mandi-compact-badge" in html
    assert ".nk-mandi-marker-wrap" in html

    # 2. Verify JS LOD engine functions
    assert "buildDistrictClusters" in html
    assert "refreshMandiLOD" in html
    assert "nk-mandi-cluster-badge" in html
    assert "nk-mandi-compact-badge" in html
    assert "onMandiMapMove" in html


