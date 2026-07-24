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
    if (els.results) els.results.setAttribute("aria-busy", "true");
    fetch(url, { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (myId !== reqId) return;                 // superseded — ignore
        if (els.results) els.results.removeAttribute("aria-busy");
        if (d && d.ok && d.html && els.results) {
          els.results.innerHTML = d.html;
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
