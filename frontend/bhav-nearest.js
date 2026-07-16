// ============================================================
// KrashiMitra — Nearest-mandi panel swap (bhav tier 2 & 3)
//
// The /bhav pages are one cached HTML shared by everyone, so they always
// server-render the highest-price "best rate" panel. When the device has a
// stored location (localStorage km_geo, set by location.js), we ask the
// backend for the NEAREST mandi for this crop and swap it into that panel.
// No location, or nothing near enough with known coordinates → the page keeps
// its highest-price panel untouched. See routes/bhav.py `bhav_nearest`.
// ============================================================
(function () {
  "use strict";

  function readGeo() {
    try { return JSON.parse(localStorage.getItem("km_geo") || "null"); }
    catch (e) { return null; }
  }

  var done = false;   // only swap once per page view

  function run() {
    if (done) return;
    var panel = document.getElementById("km-near-panel");
    if (!panel) return;

    var geo = readGeo();
    if (!geo || geo.status !== "granted" ||
        typeof geo.lat !== "number" || typeof geo.lon !== "number") return;

    var crop = panel.getAttribute("data-crop");
    if (!crop) return;
    var state = panel.getAttribute("data-state") || "";

    // Relative URL: the page itself was served from /bhav/... on this origin
    // (Netlify proxies /bhav/* to the backend), so this reaches the same API
    // with no CORS. Query varies by coords, and the endpoint sends no-store.
    var url = "/bhav/nearest?crop=" + encodeURIComponent(crop) +
              "&lat=" + encodeURIComponent(geo.lat) +
              "&lon=" + encodeURIComponent(geo.lon) +
              (state ? "&state=" + encodeURIComponent(state) : "");

    done = true;
    fetch(url, { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d && d.ok && d.html) {
          panel.innerHTML = d.html;
          panel.setAttribute("data-km-nearest", "1");
        } else {
          done = false;   // let a later km:location retry
        }
      })
      .catch(function () { done = false; });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
  // Farmer grants location mid-visit → upgrade the panel live.
  document.addEventListener("km:location", run);
})();
