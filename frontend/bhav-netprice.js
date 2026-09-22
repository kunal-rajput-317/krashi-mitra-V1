// ============================================================
// KrashiMitra — Net-price-after-transport calculator (/bhav/net-price)
//
// Ranks the mandis around the farmer's location for a crop by NET भाव
// (mandi modal price − estimated freight). The page ships static explainer +
// FAQ (crawlable, ranks for "कौन सी मंडी में बेचें / नेट भाव"); this script adds
// the live, personalised part: read device location (shared km_geo via
// location.js), then fetch /bhav/net-price-calc and render the ranked list.
// Re-ranks whenever the crop, quantity or vehicle changes — server-side, so the
// freight maths stays in one place (backend/services/freight.py). No location
// → the page just shows a prompt and works fine.
// ============================================================
(function () {
  "use strict";

  var els = {};
  var lastGeo = null;
  var timer = null;
  var reqId = 0;         // only the newest request may paint (guards stale results)
  var MAX_QTY = 100000;  // hard ceiling — must match the server-side clamp
  var lastMandis = [];
  var lastUserCoords = null;
  var npMap = null;

  // What the wait looks like: the answer's own shape — the headline mandi,
  // the net-in-hand block, then the freight rows under it. .km-sk comes from
  // km-skeleton.css, which every /bhav page links in <head>.
  var SKELETON =
    '<div role="status" aria-live="polite">' +
      '<span class="km-sk-label">गणना हो रही है…</span>' +
      '<div class="km-sk km-sk-line lg" style="width:56%"></div>' +
      '<div class="km-sk" style="height:74px;border-radius:14px;margin:14px 0"></div>' +
      '<div class="km-sk km-sk-line" style="width:92%;margin-bottom:9px"></div>' +
      '<div class="km-sk km-sk-line" style="width:84%;margin-bottom:9px"></div>' +
      '<div class="km-sk km-sk-line" style="width:62%"></div>' +
    '</div>';

  function $(id) { return document.getElementById(id); }

  function readGeo() {
    // Prefer the shared helper from location.js; fall back to raw storage.
    try {
      if (window.KrashiLocation && window.KrashiLocation.get) {
        return window.KrashiLocation.get();
      }
      return JSON.parse(localStorage.getItem("km_geo") || "null");
    } catch (e) { return null; }
  }

  function goodGeo(g) {
    return g && g.status === "granted" &&
      typeof g.lat === "number" && typeof g.lon === "number";
  }

  function setStatus(txt) {
    if (els.status) els.status.textContent = txt;
  }

  function currentQty() {
    // The exact quantity that will drive the calc — so the panel can never claim
    // a number different from the box. Empty / 0 / negative → null (we prompt,
    // instead of silently guessing 20). Above the ceiling → clamp AND write it
    // back into the field, so what's shown and what's computed always agree.
    var q = parseFloat(els.qty ? els.qty.value : "");
    if (!isFinite(q) || q <= 0) return null;
    if (q > MAX_QTY) { q = MAX_QTY; if (els.qty) els.qty.value = q; }
    return q;
  }

  function fetchRanked() {
    var g = lastGeo;
    if (!goodGeo(g)) return;
    var crop = els.crop && els.crop.value;
    if (!crop) return;
    var qty = currentQty();
    if (qty === null) {                    // empty / 0 / invalid — don't guess
      reqId++;                             // cancel any in-flight paint
      if (els.results) {
        els.results.removeAttribute("aria-busy");
        els.results.innerHTML =
          '<p class="np-hint">कृपया मात्रा (क्विंटल) भरें — कितना माल बेचना है।</p>';
      }
      return;
    }
    var tier = (els.tier && els.tier.value) || "";

    var url = "/bhav/net-price-calc?crop=" + encodeURIComponent(crop) +
      "&lat=" + encodeURIComponent(g.lat) +
      "&lon=" + encodeURIComponent(g.lon) +
      "&qty=" + encodeURIComponent(qty) +
      (tier ? "&tier=" + encodeURIComponent(tier) : "");

    // Stamp this request. If the farmer changes a field again before the
    // response lands, a newer request bumps reqId and this (now stale) response
    // is dropped — so what's shown always matches the current crop/qty/vehicle,
    // never an out-of-order older answer.
    var myId = ++reqId;
    if (els.results) {
      els.results.setAttribute("aria-busy", "true");
      // First calculation: the box is empty and the aria-busy overlay has
      // nothing to sit on top of, so the farmer watched a spinner over blank
      // space. Paint the answer's own shape instead — the freight rows and the
      // net-in-hand line. A RE-calculation keeps the previous numbers under the
      // overlay, which is more useful than replacing them with grey blocks.
      if (!els.results.querySelector(".np-take, .np-row")) {
        els.results.innerHTML = SKELETON;
      }
    }
    fetch(url, { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (myId !== reqId) return;                 // superseded — ignore
        if (els.results) els.results.removeAttribute("aria-busy");
        if (d && d.ok && d.html && els.results) {
          lastMandis = d.mandis || [];
          lastUserCoords = (typeof d.user_lat === "number" && typeof d.user_lon === "number") ? [d.user_lat, d.user_lon] : null;
          els.results.innerHTML = d.html;
          var wrap = $("np-map-container");
          if (wrap && wrap.style.display !== "none") {
            ensureLeaflet().then(renderNpMap);
          }
        }
      })
      .catch(function () {
        if (myId === reqId && els.results) els.results.removeAttribute("aria-busy");
      });
  }

  // Debounce the control changes (typing a quantity fires many events).
  function schedule() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(fetchRanked, 320);
  }

  function useGeo(g) {
    lastGeo = g;
    setStatus(g.location ? ("📍 " + g.location) : "📍 आपकी लोकेशन सेट है");
    if (els.btn) els.btn.style.display = "none";
    fetchRanked();
  }

  function onLocBtn() {
    setStatus("प्रतीक्षा करें…");
    if (window.KrashiLocation && window.KrashiLocation.ask) {
      window.KrashiLocation.ask();   // opens the friendly opt-in card
      // km:location fires on grant (handled below); if the card is dismissed
      // the status just stays — a later tap re-opens it.
      return;
    }
    // Fallback: no location.js on the page → ask the browser directly.
    if (!navigator.geolocation) { setStatus("इस डिवाइस पर लोकेशन उपलब्ध नहीं है।"); return; }
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        useGeo({ status: "granted",
                 lat: +pos.coords.latitude.toFixed(5),
                 lon: +pos.coords.longitude.toFixed(5) });
      },
      function () { setStatus("लोकेशन नहीं मिली। कृपया ब्राउज़र में अनुमति दें।"); },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 }
    );
  }

  // Pre-fill from the link the farmer arrived on. A /bhav tier page sends
  // ?crop=<slug> (the crop they were viewing) and, from a district page,
  // &lat=&lon=&place=<district> (its centroid) so the calculator opens ready.
  function prefillFromUrl() {
    var p;
    try { p = new URLSearchParams(window.location.search); }
    catch (e) { return; }

    var crop = p.get("crop");
    if (crop && els.crop) {
      // Only accept it if the dropdown actually offers this crop.
      for (var i = 0; i < els.crop.options.length; i++) {
        if (els.crop.options[i].value === crop) { els.crop.value = crop; break; }
      }
    }

    var lat = parseFloat(p.get("lat")), lon = parseFloat(p.get("lon"));
    if (isFinite(lat) && isFinite(lon)) {
      // Seed the district's location unless the farmer's real, previously
      // granted location is already known — a genuine GPS fix wins.
      var g = readGeo();
      if (!goodGeo(g)) {
        useGeo({ status: "granted", lat: lat, lon: lon,
                 location: p.get("place") || "" });
        // Seeded from a district centroid, not a real fix — keep the button so
        // the farmer can switch to their own location if they're elsewhere.
        if (els.btn) els.btn.style.display = "";
        return true;
      }
    }
    return false;
  }

  function loadAsset(u, isCss) {
    return new Promise(function(res, rej) {
      if (isCss) {
        if (document.querySelector('link[href="' + u + '"]')) return res();
        var l = document.createElement('link');
        l.rel = 'stylesheet'; l.href = u;
        l.onload = res; l.onerror = rej;
        document.head.appendChild(l);
      } else {
        if (window.L || document.querySelector('script[src="' + u + '"]')) return res();
        var s = document.createElement('script');
        s.src = u; s.async = true;
        s.onload = res; s.onerror = rej;
        document.head.appendChild(s);
      }
    });
  }

  function ensureLeaflet() {
    if (window.L) return Promise.resolve();
    return Promise.all([
      loadAsset('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css', true),
      loadAsset('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js', false)
    ]);
  }

  function renderNpMap() {
    var c = $("np-map-canvas");
    if (!c || !lastMandis || !lastMandis.length || !window.L) return;

    if (!npMap) {
      npMap = L.map(c, { zoomControl: false, zoomSnap: 0.25 }).setView([22.9, 79.0], 5);
      L.control.zoom({ position: 'bottomright' }).addTo(npMap);
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles © Esri World Imagery', maxNativeZoom: 18, maxZoom: 20
      }).addTo(npMap);
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
        attribution: '© Esri', maxNativeZoom: 18, maxZoom: 20
      }).addTo(npMap);
    }

    if (window.npMarkerGroup) {
      npMap.removeLayer(window.npMarkerGroup);
    }
    window.npMarkerGroup = L.layerGroup().addTo(npMap);

    var bounds = L.latLngBounds([]);
    if (lastUserCoords) {
      bounds.extend(lastUserCoords);
      var uIcon = L.divIcon({
        className: 'bhav-user-pin-wrap',
        html: '<div class="bhav-user-pin"></div>',
        iconSize: [16, 16],
        iconAnchor: [8, 8]
      });
      L.marker(lastUserCoords, { icon: uIcon }).addTo(window.npMarkerGroup)
        .bindPopup('<div style="font-weight:700;font-size:12px;color:#1e40af">आपकी लोकेशन</div>');
    }

    lastMandis.forEach(function(m, idx) {
      if (typeof m.lat !== 'number' || typeof m.lon !== 'number') return;
      var pos = [m.lat, m.lon];
      bounds.extend(pos);

      var isTop = (idx === 0);
      var pinHtml = '<div class="bhav-pin-card">' +
        (isTop ? '<span class="bhav-pin-tag">उच्चतम नेट</span>' : '') +
        '<span class="bhav-pin-name">' + m.market + '</span>' +
        '<span class="bhav-pin-price">₹' + m.net_per_q.toLocaleString() + '</span>' +
        '</div><div class="bhav-pin-arrow"></div>';

      var icon = L.divIcon({
        className: 'bhav-mandi-pin' + (isTop ? ' bhav-pin-top' : ''),
        html: pinHtml,
        iconSize: null,
        iconAnchor: null
      });

      var pop = '<div class="bhav-popup">' +
        '<div class="bhav-popup-title"><span>' + m.market + ' (' + m.district + ')</span>' +
        (isTop ? '<span class="bhav-popup-tag">उच्चतम नेट भाव</span>' : '') + '</div>' +
        '<div class="bhav-popup-price">₹' + m.net_per_q.toLocaleString() + ' <small>नेट/क्विंटल</small></div>' +
        '<div class="bhav-popup-range">मंडी रेट: ₹' + m.modal.toLocaleString() + ' · भाड़ा: ~₹' + m.freight_per_q.toLocaleString() + '/क्विं.</div>' +
        '<div class="bhav-popup-dist">' + m.distance_km + ' किमी दूर</div>' +
        '<div class="bhav-popup-actions">' +
        '<a href="https://www.google.com/maps/dir/?api=1&destination=' + m.lat + ',' + m.lon + '" target="_blank" rel="noopener" class="bhav-popup-btn bhav-popup-btn-nav">' +
        '<svg class="bm-icon" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/></svg> रास्ता देखें</a>' +
        '</div></div>';

      L.marker(pos, { icon: icon }).addTo(window.npMarkerGroup).bindPopup(pop);
    });

    if (bounds.isValid()) {
      npMap.fitBounds(bounds, { padding: [45, 45], maxZoom: 13 });
    }
    setTimeout(function() { npMap && npMap.invalidateSize(); }, 100);
    setTimeout(function() { npMap && npMap.invalidateSize(); }, 350);
  }

  window.toggleNpMap = function() {
    var wrap = $("np-map-container");
    if (!wrap) return;
    var open = wrap.style.display !== 'none';
    if (open) {
      wrap.style.display = 'none';
    } else {
      wrap.style.display = 'block';
      ensureLeaflet().then(renderNpMap);
    }
  };

  function init() {
    els = {
      crop: $("np-crop"), qty: $("np-qty"), tier: $("np-tier"),
      btn: $("np-loc-btn"), status: $("np-loc-status"), results: $("np-results"),
    };
    if (!els.results) return;

    if (els.btn) els.btn.addEventListener("click", onLocBtn);
    ["change", "input"].forEach(function (ev) {
      if (els.crop) els.crop.addEventListener(ev, schedule);
      if (els.qty) els.qty.addEventListener(ev, schedule);
      if (els.tier) els.tier.addEventListener(ev, schedule);
    });

    // Mobile: collapse the intro to one line behind a "और देखें" toggle so the
    // calculator itself is reachable without scrolling. The full text stays in
    // the DOM (SEO + no-JS readers see all of it); only the CSS clamp hides it.
    var wrap = $("np-lede-wrap"), more = $("np-lede-more");
    if (wrap && more) {
      wrap.classList.add("clamp");
      more.hidden = false;
      more.addEventListener("click", function () {
        var open = wrap.classList.toggle("open");
        more.textContent = open ? "कम देखें" : "और देखें";
        more.setAttribute("aria-expanded", open ? "true" : "false");
      });
    }

    // Same collapse for the explainer block below the calculator — a wall of
    // text on a phone; full copy stays in the DOM (SEO), only visually clamped.
    var exBody = $("np-ex-body"), exMore = $("np-ex-more");
    if (exBody && exMore) {
      exMore.hidden = false;
      exMore.addEventListener("click", function () {
        var open = exBody.classList.toggle("open");
        exMore.textContent = open ? "कम देखें" : "और देखें";
        exMore.setAttribute("aria-expanded", open ? "true" : "false");
      });
    }

    // location.js broadcasts this the moment a grant resolves (this page or the
    // shell card), carrying {lat, lon, location}.
    document.addEventListener("km:location", function (e) {
      var d = (e && e.detail) || {};
      if (typeof d.lat === "number" && typeof d.lon === "number") {
        useGeo({ status: "granted", lat: d.lat, lon: d.lon, location: d.location });
      }
    });

    // Carry over the crop + district the farmer came from. If it seeded a
    // location, results are already loading; otherwise fall back to a stored
    // grant from a previous visit.
    var seeded = prefillFromUrl();
    if (!seeded) {
      var g = readGeo();
      if (goodGeo(g)) useGeo(g);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
