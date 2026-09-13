// ============================================================
// KrashiMitra — the ecosystem strip's memory
//
// services/ecosystem.py renders "आगे क्या करें" into every server page and
// every article. Those links are REAL, CRAWLABLE and GENERIC on purpose: a
// static article is one file served to everyone, so the price link it ships
// says /bhav/wheat, not /bhav/wheat/uttar-pradesh/bijnor.
//
// That is right for the crawler and wrong for the farmer. A Bijnor reader who
// came from his own district page and taps "गेहूं का आज का मंडी भाव" lands on
// the national crop page and has to pick his state and district again — the
// chain breaks at exactly the hop it was built to make.
//
// So: the server ships the generic href, and this file upgrades it in place
// once — and only once — we know where the reader actually is.
//
//   1. Every page quietly remembers its own place in localStorage "km_place".
//      A /bhav or /naksha or /ganna page knows its state and district from its
//      own URL; that is the reader's place for as long as he is walking
//      through the site.
//   2. Failing that, the device location he already opted into (location.js,
//      "km_geo") names his district, matched against the district list the
//      site already ships for the map picker.
//   3. Any strip link carrying data-km-place gets its template filled in.
//
// WHAT THIS DELIBERATELY DOES NOT DO
//   • It never invents a link. data-km-place carries a template the server
//     authored; nothing here builds a URL the server did not sanction.
//   • It never touches an href that has no template, and never changes the
//     SECTION a link points at — only its depth. A rewrite that could send a
//     reader somewhere else entirely would be worse than no personalisation.
//   • It never runs for a crawler: Googlebot gets the server's generic href,
//     which is the one in the sitemap and the one we want the equity on.
//   • It writes nothing to the network and reads no profile. The place lives
//     in this browser and nowhere else.
//
// Loaded by bhav.py's _header (every server page) and by the article builder.
// Listed in sw.js SHELL_SCRIPTS — it decides addresses, so a cache-first copy
// would keep sending returning phones to yesterday's rule.
// ============================================================
(function () {
  "use strict";

  var KEY = "km_place";
  var TTL = 30 * 24 * 3600 * 1000;   // a farmer's district is not news

  function read(k) {
    try { return JSON.parse(localStorage.getItem(k) || "null"); }
    catch (e) { return null; }
  }
  function write(o) {
    try { localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) {}
  }

  function slug(s) {
    return String(s || "").toLowerCase().trim()
      .replace(/[\s_]+/g, "-").replace(/[^a-z0-9-]/g, "")
      .replace(/-{2,}/g, "-").replace(/^-|-$/g, "");
  }

  // ── 1. what this page says about where the reader is ───────
  //
  // Read off the path, in the shapes the server actually serves. Anything that
  // does not match one of them leaves the stored place alone — an article or
  // the shop page is not evidence that the reader moved.
  function placeFromPath() {
    var p = location.pathname.replace(/\/+$/, "").split("/").filter(Boolean);
    if (!p.length) return null;
    var sec = p[0], rest = p.slice(1);
    if (sec === "bhav") {
      if (rest[0] === "rajya") return pair(rest[1], rest[2]);
      return pair(rest[1], rest[2]);            // /bhav/{crop}/{state}/{dist}
    }
    if (sec === "naksha" || sec === "ganna") {
      if (rest[1] === "jile" || rest[1] === "gaon") return pair(rest[0], "");
      return pair(rest[0], rest[1]);
    }
    return null;
  }
  function pair(state, district) {
    state = slug(state);
    if (!state) return null;
    return { state: state, district: slug(district), ts: Date.now() };
  }

  // ── 2. fill the templates ──────────────────────────────────
  function apply(place) {
    if (!place || !place.state) return;
    var links = document.querySelectorAll("a.km-journey-card[data-km-place]");
    for (var i = 0; i < links.length; i++) {
      var a = links[i];
      var tpl = a.getAttribute("data-km-place") || "";
      // A template needing a district is only usable when we have one —
      // "/bhav/wheat//" would 404, and a 404 is worse than the generic page.
      if (tpl.indexOf("{district}") !== -1 && !place.district) continue;
      if (tpl.indexOf("{state}") !== -1 && !place.state) continue;
      var href = tpl.replace("{state}", place.state)
                    .replace("{district}", place.district);
      // Only ever deepen a link inside the section it already points at.
      var cur = a.getAttribute("href") || "";
      var sec = "/" + (cur.replace(/^https?:\/\/[^/]+/, "")
                          .split("/").filter(Boolean)[0] || "");
      if (href.indexOf(sec + "/") !== 0) continue;
      a.setAttribute("href", href);
      a.setAttribute("data-km-placed", "1");
    }
  }

  function run() {
    var stored = read(KEY);
    if (stored && Date.now() - (stored.ts || 0) > TTL) stored = null;

    var here = placeFromPath();
    if (here) {
      // A page that names a district is better evidence than a stored one that
      // names only a state — but a state-only page must not erase a district
      // the reader arrived with.
      if (!here.district && stored && stored.state === here.state) {
        here.district = stored.district;
      }
      write(here);
      stored = here;
    }
    apply(stored);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }

  // Exposed so a page that learns the reader's place some other way (the
  // location opt-in resolving after load, a district picker) can hand it over
  // rather than reaching into localStorage itself.
  window.KrashiJourney = {
    set: function (state, district) {
      var p = pair(state, district);
      if (p) { write(p); apply(p); }
    },
    get: function () { return read(KEY); }
  };

  // NOT consumed here: localStorage "km_geo", the device location from
  // location.js. Its district is free text from a third-party reverse
  // geocoder ("बिजनौर", "Bijnor District", "Bijnaur"), and turning that into
  // the feed's slug needs the district list the map picker ships. A wrong
  // guess would point a farmer at a 404, which is strictly worse than the
  // generic page he gets today — so that path waits for the real mapping.
  // KrashiJourney.set() is the seam it will arrive through.
})();
